#!/usr/bin/env python3
"""Paired visible-only vs draw-order Searcher3 leaf probe analysis."""
import argparse
import csv
import itertools
import json
from collections import defaultdict

import numpy as np
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BOOTSTRAP_SEED = 20260816
SPLIT_SEED = 20260816


def load(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("probe CSV is empty")
    fields = list(rows[0])
    return rows, fields[fields.index("drawOrder") + 1:]


def groups(rows):
    out = defaultdict(list)
    for row in rows:
        out[(row["seed"], row["sourceLeafId"])].append(row)
    deduped = {}
    for key, value in out.items():
        seen = set()
        unique = []
        for row in value:
            if row["drawOrder"] not in seen:
                seen.add(row["drawOrder"])
                unique.append(row)
        if unique:
            deduped[key] = unique
    return deduped


def eligible_counts(vmap, k):
    eligible = [key for key, values in vmap.items() if len(values[0]) >= k]
    return {"groupsEligible": len(eligible),
            "seedsEligible": len({int(key[0]) for key in eligible})}


def grouped_metrics(vmap):
    centered_y = []; centered_control = []; centered_particle = []
    pair_control = []; pair_particle = []
    for ys, vcs, vps in vmap.values():
        ys, vcs, vps = map(np.asarray, (ys, vcs, vps))
        centered_y.extend(ys - ys.mean())
        centered_control.extend(vcs - vcs.mean())
        centered_particle.extend(vps - vps.mean())
        for i, j in itertools.combinations(range(len(ys)), 2):
            if ys[i] == ys[j]: continue
            truth_sign = ys[i] > ys[j]
            for pred, result in ((vcs, pair_control), (vps, pair_particle)):
                delta = pred[i] - pred[j]
                result.append(.5 if delta == 0 else float((delta > 0) == truth_sign))
    return {
        "centeredRMSE": {
            "control": float(np.sqrt(np.mean((np.asarray(centered_y) - np.asarray(centered_control)) ** 2))) if centered_y else float("nan"),
            "treatment": float(np.sqrt(np.mean((np.asarray(centered_y) - np.asarray(centered_particle)) ** 2))) if centered_y else float("nan"),
        },
        "pairwise": {
            "control": float(np.mean(pair_control)) if pair_control else float("nan"),
            "treatment": float(np.mean(pair_particle)) if pair_particle else float("nan"),
            "pairs": len(pair_particle),
        },
    }


def split_by_seed(rows, rng):
    seeds = sorted({int(row["seed"]) for row in rows})
    shuffled = list(seeds); rng.shuffle(shuffled)
    if len(seeds) >= 2:
        cut = max(1, int(.8 * len(shuffled)))
        train_seeds, val_seeds = set(shuffled[:cut]), set(shuffled[cut:])
        train = [row for row in rows if int(row["seed"]) in train_seeds]
        val = [row for row in rows if int(row["seed"]) in val_seeds]
        return train, val, train_seeds, val_seeds, "seed"
    return [], [], set(seeds), set(seeds), "source_leaf_group_smoke_fallback"


def self_test():
    def row(order, target, seed="900001"):
        return {"seed": seed, "sourceLeafId": "1", "drawOrder": order,
                "target": str(target), "drawPileSize": "3", "invariantOk": "1", "terminal": "1"}
    deduped = groups([row("a", 1), row("a", 99), row("b", 2), row("c", 3)])
    assert len(deduped) == 1 and len(deduped[("900001", "1")]) == 3
    vmap = {key: ([r["target"] for r in value], [], []) for key, value in deduped.items()}
    assert eligible_counts(vmap, 1) == {"groupsEligible": 1, "seedsEligible": 1}
    assert eligible_counts(vmap, 2) == {"groupsEligible": 1, "seedsEligible": 1}
    assert eligible_counts(vmap, 4) == {"groupsEligible": 0, "seedsEligible": 0}
    assert eligible_counts(vmap, 8) == {"groupsEligible": 0, "seedsEligible": 0}
    tie = grouped_metrics({
        ("900001", "1"): ([1.0, 2.0], [0.0, 0.0], [1.0, 1.0]),
    })
    assert tie["pairwise"]["control"] == .5 and tie["pairwise"]["treatment"] == .5
    split_rows = [row("a", 1, "900001"), row("b", 2, "900002"),
                  row("c", 3, "900003"), row("d", 4, "900004")]
    train, val, train_seeds, val_seeds, method = split_by_seed(split_rows, np.random.default_rng(SPLIT_SEED))
    assert method == "seed" and train_seeds.isdisjoint(val_seeds)
    assert {r["seed"] for r in train}.isdisjoint({r["seed"] for r in val})
    print("train_particle_leaf_probe self-test: PASS")


def metrics(y, pred):
    return {"rmse": float(mean_squared_error(y, pred) ** 0.5),
            "mae": float(mean_absolute_error(y, pred)),
            "r2": float(r2_score(y, pred)) if len(set(y)) > 1 else float("nan")}


def bootstrap(values, rng, n=2000):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return [float("nan")] * 3
    means = [values[rng.integers(len(values), size=len(values))].mean() for _ in range(n)]
    return [float(values.mean()), float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--json", default="")
    ap.add_argument("--model-alpha", type=float, default=1.0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    raw_rows, feature_names = load(args.csv)
    invariant_dropped = sum(int(r["invariantOk"]) != 1 for r in raw_rows)
    nonterminal_dropped = sum(int(r["invariantOk"]) == 1 and int(r["terminal"]) != 1 for r in raw_rows)
    rows = [r for r in raw_rows if int(r["invariantOk"]) == 1 and int(r["terminal"]) == 1]
    gs = groups(rows)
    rng = np.random.default_rng(SPLIT_SEED)
    deduped_rows = [row for value in gs.values() for row in value]
    train, val, train_seeds, val_seeds, split_method = split_by_seed(deduped_rows, rng)
    if split_method != "seed":
        split_method = "source_leaf_group_smoke_fallback"
        keys = list(gs); rng.shuffle(keys)
        cut = max(1, int(.8 * len(keys)))
        train_keys, val_keys = set(keys[:cut]), set(keys[cut:])
        if not val_keys: val_keys = set(train_keys)
        if not train_keys: train_keys = set(val_keys)
        train = [r for key in train_keys for r in gs[key]]
        val = [r for key in val_keys for r in gs[key]]
        train_seeds = val_seeds = set(seeds)
    train_groups = {(r["seed"], r["sourceLeafId"]) for r in train}
    val_groups = {(r["seed"], r["sourceLeafId"]) for r in val}
    if split_method == "seed": assert train_groups.isdisjoint(val_groups)

    def visible(row):
        return sparse.csr_matrix(np.asarray([[float(row[k]) for k in feature_names]], dtype=np.float32))
    card_ids = sorted({int(x) for r in rows for x in r["drawOrder"].split(";") if x})
    card_index = {card: i for i, card in enumerate(card_ids)}

    def treatment(row):
        width = len(feature_names) + 10 * (len(card_ids) + 1)
        out = sparse.lil_matrix((1, width), dtype=np.float32)
        out[0, :len(feature_names)] = visible(row)
        cards = [int(x) for x in row["drawOrder"].split(";") if x][:10]
        for pos in range(10):
            idx = card_index.get(cards[pos], len(card_ids)) if pos < len(cards) else len(card_ids)
            out[0, len(feature_names) + pos * (len(card_ids) + 1) + idx] = 1.0
        return out.tocsr()

    y_train = np.asarray([float(r["target"]) for r in train])
    y_val = np.asarray([float(r["target"]) for r in val])
    control = Ridge(alpha=args.model_alpha).fit(sparse.vstack([visible(r) for r in train]), y_train)
    particle = Ridge(alpha=args.model_alpha).fit(sparse.vstack([treatment(r) for r in train]), y_train)
    control_pred = control.predict(sparse.vstack([visible(r) for r in val]))
    particle_pred = particle.predict(sparse.vstack([treatment(r) for r in val]))
    vmap = defaultdict(lambda: [[], [], []])
    for row, vc, vp in zip(val, control_pred, particle_pred):
        key = (row["seed"], row["sourceLeafId"])
        vmap[key][0].append(float(row["target"]))
        vmap[key][1].append(float(vc)); vmap[key][2].append(float(vp))

    spreads = []; ranges = []; centered_y = []; centered_control = []; centered_particle = []
    pair_control = []; pair_particle = []; seed_pair = defaultdict(list)
    raw_curve_by_seed = defaultdict(list); model_curve_by_seed = defaultdict(list)
    for key, (ys, vcs, vps) in vmap.items():
        ys, vcs, vps = map(np.asarray, (ys, vcs, vps))
        spreads.append(float(ys.std())); ranges.append(float(ys.max() - ys.min()))
        centered_y.extend(ys - ys.mean())
        centered_control.extend(vcs - vcs.mean()); centered_particle.extend(vps - vps.mean())
        for i, j in itertools.combinations(range(len(ys)), 2):
            if ys[i] == ys[j]: continue
            truth_sign = ys[i] > ys[j]
            for pred, result in ((vcs, pair_control), (vps, pair_particle)):
                delta = pred[i] - pred[j]
                score = .5 if delta == 0 else float((delta > 0) == truth_sign)
                result.append(score)
                if result is pair_particle: seed_pair[int(key[0])].append(score - .5)
        for k in (1, 2, 4, 8):
            if len(ys) >= k:
                raw_errors = []; model_errors = []
                for indexes in itertools.combinations(range(len(ys)), k):
                    raw_errors.append(float((np.mean(ys[list(indexes)]) - ys.mean()) ** 2))
                    model_errors.append(float((np.mean(vps[list(indexes)]) - ys.mean()) ** 2))
                raw_curve_by_seed[k].append((int(key[0]), float(np.mean(raw_errors))))
                model_curve_by_seed[k].append((int(key[0]), float(np.mean(model_errors))))

    seed_rmse = defaultdict(list)
    for key, (ys, vcs, vps) in vmap.items():
        ys, vcs, vps = map(np.asarray, (ys, vcs, vps))
        seed_rmse[int(key[0])].append(float(np.sqrt(np.mean((vps - ys) ** 2)) -
                                           np.sqrt(np.mean((vcs - ys) ** 2))))
    size_strata = {}
    for name, predicate in (("le10", lambda r: int(r["drawPileSize"]) <= 10),
                            ("gt10", lambda r: int(r["drawPileSize"]) > 10)):
        stratum_rows = [r for r in rows if predicate(r)]
        stratum_groups = groups(stratum_rows)
        size_strata[name] = {
            "rows": len(stratum_rows), "groups": len(stratum_groups),
            "seeds": len({int(key[0]) for key in stratum_groups}),
            "fractionRows": float(len(stratum_rows) / len(rows)) if rows else float("nan"),
        }
    validation_strata = {}
    for name, predicate in (("le10", lambda r: int(r["drawPileSize"]) <= 10),
                            ("gt10", lambda r: int(r["drawPileSize"]) > 10)):
        keys = {key for key, value in vmap.items()
                if value[0] and predicate(next(r for r in val if (r["seed"], r["sourceLeafId"]) == key))}
        validation_strata[name] = grouped_metrics({key: vmap[key] for key in keys})
        validation_strata[name].update({"groups": len(keys), "seeds": len({int(key[0]) for key in keys})})
    result = {
        "rows": len(rows), "raw_rows": len(raw_rows), "invariant_rows_dropped": invariant_dropped,
        "nonterminal_rows_dropped": nonterminal_dropped, "groups": len(gs),
        "train_rows": len(train), "validation_rows": len(val),
        "train_seeds": sorted(train_seeds), "validation_seeds": sorted(val_seeds),
        "split_seed": SPLIT_SEED, "split_method": split_method,
        "group_split_leak": bool(train_groups & val_groups),
        "draw_pile": {"length_mean": float(np.mean([int(r["drawPileSize"]) for r in rows])),
                      "length_median": float(np.median([int(r["drawPileSize"]) for r in rows])),
                      "fraction_le_10": float(np.mean([int(r["drawPileSize"]) <= 10 for r in rows])),
                      "unique_variants_sampled_mean": float(np.mean([int(r["uniqueVariantsSampled"]) for r in rows])),
                      "sizeStrata": size_strata},
        "spread": {"mean_std": float(np.mean(spreads)), "median_std": float(np.median(spreads)),
                    "mean_range": float(np.mean(ranges)), "median_range": float(np.median(ranges)),
                    "global_std": float(np.std(y_val))},
        "control": metrics(y_val, control_pred), "particle": metrics(y_val, particle_pred),
        "centered_rmse": {"control": float(np.sqrt(np.mean((np.asarray(centered_y) - np.asarray(centered_control)) ** 2))),
                          "particle": float(np.sqrt(np.mean((np.asarray(centered_y) - np.asarray(centered_particle)) ** 2)))},
        "pairwise": {"control": float(np.mean(pair_control)) if pair_control else float("nan"),
                     "particle": float(np.mean(pair_particle)) if pair_particle else float("nan"),
                     "pairs": len(pair_particle), "groups": len(vmap)},
        "averaging_curve": {str(k): {"raw_rollout_rmse": float(np.sqrt(np.mean([np.mean([v for seed, v in raw_curve_by_seed[k] if seed == s]) for s in {seed for seed, v in raw_curve_by_seed[k]}]))) if raw_curve_by_seed[k] else float("nan"),
                                      "particle_model_rmse": float(np.sqrt(np.mean([np.mean([v for seed, v in model_curve_by_seed[k] if seed == s]) for s in {seed for seed, v in model_curve_by_seed[k]}]))) if model_curve_by_seed[k] else float("nan"),
                                      **eligible_counts(vmap, k)}
                            for k in (1, 2, 4, 8)},
        "validation_strata": validation_strata,
    }
    b_rng = np.random.default_rng(BOOTSTRAP_SEED)
    result["bootstrap"] = {
        "particle_minus_control_rmse_by_seed": bootstrap([np.mean(v) for v in seed_rmse.values()], b_rng),
        "particle_minus_chance_pairwise_by_seed": bootstrap([np.mean(v) for v in seed_pair.values()], b_rng),
    }
    print(json.dumps(result, indent=2, allow_nan=True))
    if args.json:
        with open(args.json, "w") as f: json.dump(result, f, indent=2, allow_nan=True)


if __name__ == "__main__":
    main()