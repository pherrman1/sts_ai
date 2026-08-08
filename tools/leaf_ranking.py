#!/usr/bin/env python3
"""Ranking diagnostics for the Searcher3 leaf-state dataset (leafdiag/leafref).

Reads a leafdiag CSV (produced by `one_combat leafdiag`; the
search::g_onS3LeafQuery hook records actual Searcher3 leaf-expansion states at
the value/rollout blend site) and optionally a leafref CSV of high-budget
reference values (`one_combat leafref`), then measures how well the deployed
end-HP vnet and a secondary diagnostic vnet rank the recorded leaves.

The central question (handover 2026-08-08, EXPERIMENTS.md §134): does the
deployed end-HP model rank actual Searcher3 candidate/leaf states better than
the direct utility-R model despite fitting terminal utility worse offline?

Reference semantics: referenceValue is a HIGH-BUDGET Searcher3 root mean
evaluation at the leaf (CRN-paired within the decision group) — an
approximation, never ground truth. All ranking comparisons are WITHIN a
(seed, fightIdx, decIdx) decision group only (leaf states of one decision's
search). When no leafref file is given, the raw rollout outcome
(rawRolloutEval) is used as a weak single-sample reference and the report
says so.

Stratification: player-HP band (from the canonical curHp/maxHp features), fight
won/lost, act, encounter difficulty, turn, tree depth, number of legal
actions, model-disagreement bin, and (optionally) an out-of-distribution flag
from tools/leaf_distribution_shift.py --write-ood.

Bootstrap confidence intervals over groups use one fixed-seed generator, so
repeated analysis of identical inputs produces identical intervals.

Output: human-readable report on stdout; machine-readable summary with
--json PATH.
"""
import argparse
import csv
import json
import math
import random
import sys

try:
    import numpy as np
except ImportError:                     # numpy is optional for --self-test only
    np = None

BOOTSTRAP_SEED = 20260808
PAIR_EPS = 1e-6          # |ref_a - ref_b| below this counts as a tie (skipped)
MODELS = ("endHp", "utilityR")

# Canonical encounter difficulty tables (mirror of include/constants/MonsterEncounters.h).
BOSSES = {
    "SLIME_BOSS", "THE_GUARDIAN", "HEXAGHOST", "CHAMP", "COLLECTOR",
    "AUTOMATON", "DONU_AND_DECA", "TIME_EATER", "AWAKENED_ONE", "THE_HEART",
}
ELITES = {
    "GREMLIN_NOB", "LAGAVULIN", "THREE_SENTRIES", "GREMLIN_LEADER",
    "SLAVERS", "BOOK_OF_STABBING", "GIANT_HEAD", "NEMESIS", "REPTOMANCER",
}


def _f(x):
    """Parse a CSV cell to float, NaN when blank/unparsable."""
    try:
        v = float(x)
        return v
    except (TypeError, ValueError):
        return float("nan")


def load_leafdiag(path):
    """Return rows (dicts)."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_leafref(path):
    """Map (seed, fightIdx, decIdx, obsHash) -> mean reference value."""
    refs = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["seed"], row["fightIdx"], row["decIdx"], row["obsHash"])
            refs.setdefault(key, []).append(_f(row["referenceValue"]))
    out = {}
    for k, vals in refs.items():
        vals = [v for v in vals if not math.isnan(v)]
        if vals:
            out[k] = float(sum(vals) / len(vals))
    return out


def load_ood_flags(path):
    """Map (seed, fightIdx, decIdx, obsHash) -> ood probability (0..1)."""
    flags = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["seed"], row["fightIdx"], row["decIdx"], row["obsHash"])
            flags[key] = _f(row["ood_prob"])
    return flags


def encounter_difficulty(enc):
    enc = str(enc).strip().upper()
    if enc in BOSSES:
        return "boss"
    if enc in ELITES:
        return "elite"
    return "hallway"

def hp_band(row):
    cur = _f(row.get("curHp", "nan"))
    mx = _f(row.get("maxHp", "nan"))
    frac = cur / mx if mx > 0 and not math.isnan(cur) and not math.isnan(mx) else float("nan")
    if math.isnan(frac):
        return "na"
    if frac < 0.30:
        return "low<0.3"
    if frac < 0.70:
        return "mid<0.7"
    return "high>=0.7"


def tree_depth_band(d):
    if d < 5:
        return "d<5"
    if d < 15:
        return "d5-14"
    return "d>=15"


def turn_band(t):
    if t <= 3:
        return "t<=3"
    if t <= 6:
        return "t4-6"
    return "t>=7"


def legal_band(n):
    if n <= 3:
        return "n<=3"
    if n <= 8:
        return "n4-8"
    return "n>8"


def model_disagreement_band(row):
    """|endHp - utilityR| bin: the models live on different scales, so this is
    a raw-difference heuristic only (documented as such, not a calibrated
    disagreement measure)."""
    a = _f(row.get("endHp_pred", "nan"))
    b = _f(row.get("utilityR_pred", "nan"))
    if math.isnan(a) or math.isnan(b):
        return "na"
    d = abs(a - b)
    if d < 20:
        return "low<20"
    if d < 50:
        return "mid<50"
    return "high>=50"


def group_rows(rows, refs, ood):
    """Group rows by decision; attach reference and ood; dedupe by obsHash."""
    groups = {}
    for r in rows:
        key = (r["seed"], r["fightIdx"], r["decIdx"])
        if refs:
            ref = refs.get((r["seed"], r["fightIdx"], r["decIdx"], r["obsHash"]),
                           float("nan"))
        else:
            # No leafref file: the raw rollout outcome is the reference proxy.
            ref = _f(r.get("rawRolloutEval", "nan"))
        if refs and math.isnan(ref):
            continue  # leafref given: keep only leaves with a reference value
        o = ood.get((r["seed"], r["fightIdx"], r["decIdx"], r["obsHash"]),
                    float("nan")) if ood else float("nan")
        groups.setdefault(key, []).append((r, ref, o))
    out = {}
    for key, lst in groups.items():
        seen = set()
        uniq = []
        for item in lst:
            oh = item[0]["obsHash"]
            if oh in seen:
                continue
            seen.add(oh)
            uniq.append(item)
        if len(uniq) >= 2:
            out[key] = uniq
    return out


def group_pairwise(refs_list, preds_list):
    """Pairwise ranking correctness of preds vs refs within one group."""
    n = len(refs_list)
    correct = total = 0
    diffs = []
    for i in range(n):
        for j in range(i + 1, n):
            dref = refs_list[i] - refs_list[j]
            if abs(dref) <= PAIR_EPS:
                continue
            dmod = preds_list[i] - preds_list[j]
            total += 1
            if (dmod > 0) == (dref > 0):
                correct += 1
            diffs.append(abs(dref))
    return correct, total, diffs


def bootstrap_ci(values, n_boot=2000, ci=0.95):
    """Deterministic bootstrap 95% CI over the mean of per-group values."""
    vals = [float(v) for v in values if not math.isnan(v)]
    if not vals:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(vals)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += vals[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int((1 - ci) / 2 * n_boot)]
    hi = means[int((1 + ci) / 2 * n_boot)]
    return float(sum(vals) / n), float(lo), float(hi)


def _rank(xs):
    """Rank ties by average — deterministic, numpy-free."""
    order = sorted(range(len(xs)), key=lambda i: (xs[i], i))
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a, b):
    if len(a) < 3:
        return float("nan")
    ra = _rank(a)
    rb = _rank(b)
    if len(set(ra)) == 1 or len(set(rb)) == 1:
        return float("nan")
    return pearson(ra, rb)


def pearson(a, b):
    if len(a) < 2:
        return float("nan")
    na = len(a)
    ma = sum(a) / na
    mb = sum(b) / na
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa == 0 or sb == 0:
        return float("nan")
    return float(cov / (sa * sb))


def model_preds(group, model):
    """Finite model predictions for a group: list of (pred, ref, row, ood)."""
    out = []
    col = "endHp_pred" if model == "endHp" else "utilityR_pred"
    for (r, ref, o) in group:
        p = _f(r.get(col, "nan"))
        if math.isnan(p):
            continue
        out.append((p, ref, r, o))
    return out


def group_metrics(group, model):
    """Per-group metrics for one model. None when the group is unusable."""
    triples = model_preds(group, model)
    if len(triples) < 2:
        return None
    preds = [t[0] for t in triples]
    refs = [t[1] for t in triples]
    finite_refs = [r for r in refs if not math.isnan(r)]
    m = {
        "nLeaves": len(triples),
        "nRefs": len(finite_refs),
        "pairwiseAcc": float("nan"),
        "closeAcc": float("nan"),
        "largeGapAcc": float("nan"),
        "top1": float("nan"),
        "regret": float("nan"),
        "spearmanVsRef": float("nan"),
    }
    if len(finite_refs) >= 2:
        good = [not math.isnan(r) for r in refs]
        refs_g = [refs[i] for i in range(len(refs)) if good[i]]
        preds_g = [preds[i] for i in range(len(preds)) if good[i]]
        correct, total, diffs = group_pairwise(refs_g, preds_g)
        if total > 0:
            m["pairwiseAcc"] = correct / total
            if len(diffs) >= 4:
                ds = sorted(diffs)
                lo = ds[len(ds) // 4]
                hi = ds[(3 * len(ds)) // 4]
                c_c = t_c = c_l = t_l = 0
                n = len(refs_g)
                for i in range(n):
                    for j in range(i + 1, n):
                        dref = refs_g[i] - refs_g[j]
                        if abs(dref) <= PAIR_EPS:
                            continue
                        dmod = preds_g[i] - preds_g[j]
                        ok = (dmod > 0) == (dref > 0)
                        if abs(dref) <= lo:
                            c_c += ok
                            t_c += 1
                        if abs(dref) >= hi:
                            c_l += ok
                            t_l += 1
                m["closeAcc"] = c_c / t_c if t_c else float("nan")
                m["largeGapAcc"] = c_l / t_l if t_l else float("nan")
        if np is not None:
            m["top1"] = float(np.argmax(preds_g) == np.argmax(refs_g))
            m["regret"] = float(max(refs_g) - refs_g[np.argmax(preds_g)])
            m["spearmanVsRef"] = spearman(refs_g, preds_g)
        else:
            imax = refs_g.index(max(refs_g))
            m["top1"] = float(preds_g.index(max(preds_g)) == imax)
            m["regret"] = float(max(refs_g) - refs_g[preds_g.index(max(preds_g))])
    return m


def stratify_label(row, o):
    """Stratification labels for one row (first row of a group represents it)."""
    t = _f(row.get("turn", "nan"))
    d = _f(row.get("treeDepth", "nan"))
    n = _f(row.get("nLegalActions", "nan"))
    return {
        "hpBand": hp_band(row),
        "won": str(row.get("fightWon", "")),
        "act": str(row.get("act", "")),
        "difficulty": encounter_difficulty(
            row.get("encounterName", row.get("encounter", ""))),
        "turn": turn_band(int(t)) if not math.isnan(t) else "na",
        "treeDepth": tree_depth_band(int(d)) if not math.isnan(d) else "na",
        "nLegal": legal_band(int(n)) if not math.isnan(n) else "na",
        "disagree": model_disagreement_band(row),
        "ood": ("ood" if o >= 0.5 else "id") if not math.isnan(o) else "na",
    }


def agg_over_groups(groups, model, strat_keys):
    """Per-bucket mean + bootstrap CI of pairwise accuracy and regret."""
    buckets = {}
    for key, group in groups.items():
        m = group_metrics(group, model)
        if m is None or math.isnan(m["pairwiseAcc"]):
            continue
        row0, _, o0 = group[0]
        labels = stratify_label(row0, o0)
        buckets.setdefault("all", []).append(m)
        if strat_keys:
            bucket = "|".join(f"{k}={labels[k]}" for k in strat_keys)
            buckets.setdefault(bucket, []).append(m)
    results = {}
    for bucket, ms in buckets.items():
        accs = [m["pairwiseAcc"] for m in ms]
        regrets = [m["regret"] for m in ms if not math.isnan(m["regret"])]
        top1s = [m["top1"] for m in ms if not math.isnan(m["top1"])]
        results[bucket] = {
            "nGroups": len(ms),
            "acc": bootstrap_ci(accs),
            "top1": bootstrap_ci(top1s),
            "regret": bootstrap_ci(regrets),
            "closeAcc": bootstrap_ci([m["closeAcc"] for m in ms if not math.isnan(m["closeAcc"])]),
            "largeGapAcc": bootstrap_ci([m["largeGapAcc"] for m in ms if not math.isnan(m["largeGapAcc"])]),
        }
    return results


def pooled_absolute(groups, model):
    """Pooled MAE/RMSE/Pearson/Spearman of the model vs the reference (all leaves)."""
    preds, refs = [], []
    for key, group in groups.items():
        for (p, r, row, o) in model_preds(group, model):
            if not math.isnan(r):
                preds.append(p)
                refs.append(r)
    m = {"n": len(preds), "mae": float("nan"), "rmse": float("nan"),
         "pearson": float("nan"), "spearman": float("nan")}
    if len(preds) >= 2:
        errs = [abs(p - r) for p, r in zip(preds, refs)]
        m["mae"] = float(sum(errs) / len(errs))
        m["rmse"] = float(math.sqrt(sum(e * e for e in errs) / len(errs)))
        m["pearson"] = pearson(refs, preds)
        m["spearman"] = spearman(refs, preds)
    return m


def report(groups, refs_used, ood_used, model_report, args):
    lines = []
    lines.append("=" * 78)
    lines.append("Searcher3 leaf-state ranking diagnostics (leafdiag/leafref)")
    lines.append("=" * 78)
    lines.append(f"decision groups: {len(groups)}")
    if refs_used:
        lines.append("reference: leafref high-budget Searcher3 root mean evaluation "
                     "(approximation, NOT ground truth; CRN-paired within groups)")
    else:
        lines.append("reference: rawRolloutEval (single-sample rollout outcome; "
                     "no leafref file given)")
    if ood_used:
        lines.append("in-distribution flags: from tools/leaf_distribution_shift.py --write-ood")
    lines.append("")
    lines.append(f"{'model':<10} {'nLeaves':>8} {'MAE':>8} {'RMSE':>8} "
                 f"{'Pearson':>8} {'Spearman':>8}")
    for model in MODELS:
        m = model_report[model]["absolute"]
        lines.append(f"{model:<10} {m['n']:>8} {m['mae']:>8.3f} {m['rmse']:>8.3f} "
                     f"{m['pearson']:>8.3f} {m['spearman']:>8.3f}")
    lines.append("  (MAE/RMSE are on each model's own prediction scale — endHp "
                 "is on HP scale, utilityR on the 0|50+HP terminal scale — so "
                 "they are NOT directly comparable; ranking metrics below are)")
    lines.append("")
    lines.append(f"{'model':<10} {'pairs':>8} {'pairwiseAcc':>18} {'top1Acc':>18} "
                 f"{'regret':>18}")
    for model in MODELS:
        a = model_report[model]["overall"]
        lines.append(f"{model:<10} {a['pairs']:>8} "
                     f"{a['acc'][0]:>8.3f} [{a['acc'][1]:.3f},{a['acc'][2]:.3f}] "
                     f"{a['top1'][0]:>8.3f} [{a['top1'][1]:.3f},{a['top1'][2]:.3f}] "
                     f"{a['regret'][0]:>8.3f} [{a['regret'][1]:.3f},{a['regret'][2]:.3f}]")
    lines.append("")
    for model in MODELS:
        lines.append(f"--- stratified pairwise accuracy (mean [95% CI]) / regret: {model} ---")
        for bucket, v in sorted(model_report[model]["stratified"].items()):
            if bucket == "all":
                continue
            lines.append(f"  {bucket:<34} n={v['nGroups']:>4}  "
                         f"acc={v['acc'][0]:.3f} [{v['acc'][1]:.3f},{v['acc'][2]:.3f}]  "
                         f"regret={v['regret'][0]:.3f} [{v['regret'][1]:.3f},{v['regret'][2]:.3f}]")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(model_report, f, indent=2, sort_keys=True)
        print(f"[leaf_ranking] JSON summary -> {args.json}")


def self_test():
    """Synthetic dataset with a known ordering: the end-HP model ranks the
    reference almost perfectly, the utility-R model anti-correlated."""
    rng = random.Random(7)
    groups = {}
    for g in range(4):
        key = (str(1000 + g), "0", "0")
        refs = sorted(rng.gauss(50, 15) for _ in range(6))
        endhp = [r + rng.gauss(0, 0.2) for r in refs]   # near-perfect rank agreement
        util = [-r + 120 for r in refs]                  # anti-correlated
        rows = []
        for i, r_ in enumerate(refs):
            row = {
                "seed": str(1000 + g), "fightIdx": "0", "decIdx": "0",
                "obsHash": str(1000 + i), "curHp": "40", "maxHp": "80",
                "encounter": "CULTIST", "act": "1", "turn": "3",
                "treeDepth": "6", "nLegalActions": "5", "fightWon": "1",
                "endHp_pred": f"{endhp[i]:.4f}",
                "utilityR_pred": f"{util[i]:.4f}",
                "rawRolloutEval": f"{r_ + rng.gauss(0, 10):.4f}",
            }
            rows.append((row, r_, float("nan")))
        groups[key] = rows
    model_report = {}
    for model in MODELS:
        strat = agg_over_groups(groups, model, ())
        overall = strat["all"]
        model_report[model] = {
            "absolute": pooled_absolute(groups, model),
            "overall": {
                "pairs": None, "acc": overall["acc"], "top1": overall["top1"],
                "regret": overall["regret"],
            },
            "stratified": strat,
        }
    a = model_report["endHp"]["overall"]["acc"][0]
    b = model_report["utilityR"]["overall"]["acc"][0]
    print(f"self-test: endHp pairwise acc {a:.3f} vs utilityR {b:.3f}")
    assert a > 0.95, f"endHp model should rank the synthetic reference almost perfectly, got {a}"
    assert b < 0.2, f"anti-correlated utilityR model should rank poorly, got {b}"
    print("leaf_ranking self-test PASS")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leafdiag", required=False, default=None,
                    help="leafdiag CSV (default: build/leafdiag.csv)")
    ap.add_argument("--leafref", default=None, help="leafref CSV (optional)")
    ap.add_argument("--ood", default=None,
                    help="OOD-flags CSV from leaf_distribution_shift.py --write-ood (optional)")
    ap.add_argument("--json", default=None, help="write machine-readable JSON summary")
    ap.add_argument("--self-test", action="store_true", help="run the synthetic self-test")
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        return 0

    path = args.leafdiag or "build/leafdiag.csv"
    rows = load_leafdiag(path)
    if not rows:
        print(f"leaf_ranking: no rows in {path}", file=sys.stderr)
        return 2
    refs = load_leafref(args.leafref) if args.leafref else {}
    ood = load_ood_flags(args.ood) if args.ood else {}
    refs_used = bool(args.leafref)
    groups = group_rows(rows, refs, ood)
    if not groups:
        print("leaf_ranking: no usable decision groups (need >= 2 leaves per group "
              "with references); if you gave --leafref, check the join keys",
              file=sys.stderr)
        return 2

    strat_keys = ("hpBand", "won", "act", "difficulty", "turn", "treeDepth",
                  "nLegal", "disagree", "ood")
    model_report = {}
    for model in MODELS:
        overall = agg_over_groups(groups, model, ())["all"]
        # actual total pairwise comparisons contributing to the "all" bucket
        pair_total = 0
        for key, group in groups.items():
            m = group_metrics(group, model)
            if m is not None:
                n = len(model_preds(group, model))
                if n >= 2 and all(not math.isnan(t[1]) for t in model_preds(group, model)):
                    pair_total += n * (n - 1) // 2
        stratified = {}
        for k in strat_keys:
            stratified.update(agg_over_groups(groups, model, (k,)))
        model_report[model] = {
            "absolute": pooled_absolute(groups, model),
            "overall": {
                "nGroups": int(overall["nGroups"]),
                "pairs": int(pair_total),
                "acc": overall["acc"],
                "top1": overall["top1"],
                "regret": overall["regret"],
            },
            "stratified": stratified,
        }
    report(groups, refs_used, bool(args.ood), model_report, args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
