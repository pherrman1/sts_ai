#!/usr/bin/env python3
"""Paired visible-only vs draw-order Searcher3 leaf probe.

The CSV is produced by ``one_combat particle_leaf_probe``.  All variants of a
source leaf are kept together; the primary split is by seed.  The script is
deliberately offline-only and never changes the native combat feature schema.
"""
import argparse
import csv
import itertools
import json
import math
import random
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
    feature_names = fields[fields.index("drawOrder") + 1:]
    return rows, feature_names


def groups(rows):
    out = defaultdict(list)
    for r in rows:
        out[r["groupId"]].append(r)
    return {k: v for k, v in out.items() if len(v) >= 2}


def metrics(y, p):
    return {"rmse": float(mean_squared_error(y, p) ** 0.5),
            "mae": float(mean_absolute_error(y, p)),
            "r2": float(r2_score(y, p)) if len(set(y)) > 1 else float("nan")}


def bootstrap(values, rng, n=2000):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return [float("nan")] * 3
    means = [values[rng.integers(len(values), size=len(values))].mean() for _ in range(n)]
    return [float(values.mean()), float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--json", default="")
    ap.add_argument("--model-alpha", type=float, default=1.0)
    args = ap.parse_args()
    rows, feature_names = load(args.csv)
    raw_row_count = len(rows)
    invariant_dropped = sum(int(r["invariantOk"]) != 1 for r in rows)
    nonterminal_dropped = sum(int(r["invariantOk"]) == 1 and int(r["terminal"]) != 1 for r in rows)
    rows = [r for r in rows if int(r["invariantOk"]) == 1 and int(r["terminal"]) == 1]
    gs = groups(rows)
    seeds = sorted({int(v[0]["seed"]) for v in gs.values()})
    rng = np.random.default_rng(SPLIT_SEED)
    shuffled = list(seeds); rng.shuffle(shuffled)
    split_method = "seed"
    if len(seeds) >= 2:
        n_train = max(1, int(.8 * len(shuffled)))
        train_seeds = set(shuffled[:n_train]); val_seeds = set(shuffled[n_train:])
        train = [r for v in gs.values() if int(v[0]["seed"]) in train_seeds for r in v]
        val = [r for v in gs.values() if int(v[0]["seed"]) in val_seeds for r in v]
    else:
        split_method = "source_leaf_group_smoke_fallback"
        gids = sorted(gs); rng.shuffle(gids)
        cut = max(1, int(.8 * len(gids)))
        train_ids, val_ids = set(gids[:cut]), set(gids[cut:])
        if not val_ids: val_ids = set(train_ids)
        if not train_ids: train_ids = set(val_ids)
        train = [r for gid in train_ids for r in gs[gid]]
        val = [r for gid in val_ids for r in gs[gid]]
        train_seeds = val_seeds = set(seeds)
    train_groups = {r["groupId"] for r in train}; val_groups = {r["groupId"] for r in val}
    if split_method == "seed":
        assert train_groups.isdisjoint(val_groups)

    def visible(r): return sparse.csr_matrix(np.asarray([[float(r[k]) for k in feature_names]], dtype=np.float32))
    card_ids = sorted({int(x) for r in rows for x in r["drawOrder"].split(";") if x})
    card_index = {x: i for i, x in enumerate(card_ids)}
    def treatment(r):
        x = sparse.lil_matrix((1, len(feature_names) + 10 * (len(card_ids) + 1)), dtype=np.float32)
        x[0, :len(feature_names)] = visible(r)
        cards = [int(x) for x in r["drawOrder"].split(";") if x][:10]
        for pos in range(10):
            idx = card_index.get(cards[pos], len(card_ids)) if pos < len(cards) else len(card_ids)
            x[0, len(feature_names) + pos * (len(card_ids) + 1) + idx] = 1.0
        return x.tocsr()
    ytr = np.asarray([float(r["target"]) for r in train]); yva = np.asarray([float(r["target"]) for r in val])
    xv_tr = sparse.vstack([visible(r) for r in train]); xv_va = sparse.vstack([visible(r) for r in val])
    xp_tr = sparse.vstack([treatment(r) for r in train]); xp_va = sparse.vstack([treatment(r) for r in val])
    control = Ridge(alpha=args.model_alpha).fit(xv_tr, ytr)
    particle = Ridge(alpha=args.model_alpha).fit(xp_tr, ytr)
    pv = control.predict(xv_va); pp = particle.predict(xp_va)
    vmap = {r["groupId"]: ([], [], []) for r in val for _ in [0]}
    for r, a, b in zip(val, pv, pp):
        vmap[r["groupId"]][0].append(float(r["target"])); vmap[r["groupId"]][1].append(a); vmap[r["groupId"]][2].append(b)
    spreads = []; ranges = []; centered_v = []; centered_p = []; pair_v = []; pair_p = []
    raw_curve = defaultdict(list); model_curve = defaultdict(list)
    seed_pair_deltas = defaultdict(list)
    for gid, (ys, vs, ps) in vmap.items():
        if len(ys) < 2: continue
        ys, vs, ps = map(np.asarray, (ys, vs, ps)); spreads.append(ys.std()); ranges.append(ys.max() - ys.min())
        centered_v.extend(vs - vs.mean()); centered_p.extend(ps - ps.mean())
        for i, j in itertools.combinations(range(len(ys)), 2):
            if ys[i] == ys[j]: continue
            sign = ys[i] > ys[j]
            cv = (vs[i] > vs[j]) == sign; cp = (ps[i] > ps[j]) == sign
            pair_v.append(cv); pair_p.append(cp)
            seed_pair_deltas[int(next(r["seed"] for r in val if r["groupId"] == gid))].append(float(cp) - .5)
        if len(ys) >= 8:
            for k in (1, 2, 4, 8):
                raw_curve[k].append(float(np.mean(ys[:k]) - ys.mean()))
                model_curve[k].append(float(np.mean(ps[:k]) - ys.mean()))
    centered_v = np.asarray(centered_v); centered_p = np.asarray(centered_p)
    result = {
        "rows": len(rows), "raw_rows": raw_row_count,
        "invariant_rows_dropped": invariant_dropped, "nonterminal_rows_dropped": nonterminal_dropped,
        "groups": len(gs), "train_rows": len(train), "validation_rows": len(val),
        "train_seeds": sorted(train_seeds), "validation_seeds": sorted(val_seeds),
        "split_seed": SPLIT_SEED, "split_method": split_method,
        "group_split_leak": bool(train_groups & val_groups) if split_method == "seed" else False,
        "draw_pile": {"length_mean": float(np.mean([int(r["drawPileSize"]) for r in rows])),
                      "length_median": float(np.median([int(r["drawPileSize"]) for r in rows])),
                      "fraction_le_10": float(np.mean([int(r["drawPileSize"]) <= 10 for r in rows]))},
        "spread": {"mean_std": float(np.mean(spreads)), "median_std": float(np.median(spreads)),
                    "mean_range": float(np.mean(ranges)), "median_range": float(np.median(ranges)),
                    "global_std": float(np.std(yva))},
        "control": metrics(yva, pv), "particle": metrics(yva, pp),
        "centered_rmse": {"control": float(np.sqrt(np.mean(centered_v ** 2))),
                          "particle": float(np.sqrt(np.mean(centered_p ** 2)))},
        "pairwise": {"control": float(np.mean(pair_v)) if pair_v else float("nan"),
                     "particle": float(np.mean(pair_p)) if pair_p else float("nan"),
                     "pairs": len(pair_p), "groups": len(vmap)},
        "averaging_curve": {str(k): {"raw_rollout_rmse": float(np.sqrt(np.mean(np.asarray(raw_curve[k]) ** 2))),
                                      "particle_model_rmse": float(np.sqrt(np.mean(np.asarray(model_curve[k]) ** 2)))}
                            for k in raw_curve},
    }
    b_rng = np.random.default_rng(BOOTSTRAP_SEED)
    group_deltas = []
    seed_rmse_deltas = defaultdict(list)
    for gid, (ys, vs, ps) in vmap.items():
        ys, vs, ps = map(np.asarray, (ys, vs, ps))
        delta = float(np.sqrt(np.mean((ps - ys) ** 2))
                      - np.sqrt(np.mean((vs - ys) ** 2)))
        group_deltas.append(delta)
        seed = next(r["seed"] for r in val if r["groupId"] == gid)
        seed_rmse_deltas[int(seed)].append(delta)
    seed_rmse = [np.mean(v) for v in seed_rmse_deltas.values()]
    seed_pairs = [np.mean(v) for v in seed_pair_deltas.values() if v]
    result["bootstrap"] = {
        "particle_minus_control_rmse_by_seed": bootstrap(seed_rmse, b_rng),
        "particle_minus_chance_pairwise_by_seed": bootstrap(seed_pairs, b_rng),
    }
    print(json.dumps(result, indent=2, allow_nan=True))
    if args.json:
        with open(args.json, "w") as f: json.dump(result, f, indent=2, allow_nan=True)


if __name__ == "__main__": main()