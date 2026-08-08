#!/usr/bin/env python3
"""Blend-α sweep over the leafdiag/leafref corpus.

For each α ∈ [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7] (or a user-supplied
list), computes within-decision-group pairwise ranking accuracy, top-1, and
regret of the blended value α·model_pred + (1−α)·rawRolloutEval against the
leafref high-budget reference.

Answers (EXPERIMENTS.md §140):
- Does endHp achieve peak ranking at α ≈ 0.2–0.3 (the deployed sweet spot)?
- Does utilityR ranking monotonically degrade with any α > 0?
- Is there ANY α where utilityR's blend-ranking approaches endHp's?

Usage:
  python3 tools/leaf_blend_sweep.py \
    --leafdiag build/leafdiag_slim.csv \
    --leafref build/leafref_gate_64_4k.csv \
    --alphas 0,0.05,0.1,0.15,0.2,0.3,0.5,0.7 \
    --json build/leaf_blend_sweep.json
"""
import argparse
import csv
import json
import math
import random
import sys
import time

BOOTSTRAP_SEED = 20260808
PAIR_EPS = 1e-6
MODELS = ("endHp", "utilityR")
MODEL_COLS = {"endHp": "endHp_pred", "utilityR": "utilityR_pred"}


def _f(x):
    try: return float(x)
    except: return float("nan")


def load_data(leafdiag_path, leafref_path):
    """Return (rows, refs_avg, groups)."""
    t0 = time.time()
    rows = list(csv.DictReader(open(leafdiag_path, newline="")))
    print(f"Loaded {len(rows)} leafdiag rows in {time.time()-t0:.1f}s", flush=True)

    refs_avg = {}
    with open(leafref_path, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["seed"], row["fightIdx"], row["decIdx"], row["obsHash"])
            v = _f(row["referenceValue"])
            if not math.isnan(v):
                refs_avg[key] = v
    print(f"Loaded {len(refs_avg)} references in {time.time()-t0:.1f}s", flush=True)

    groups = {}
    for r in rows:
        groups.setdefault(
            (r["seed"], r["fightIdx"], r["decIdx"]), []
        ).append(r)

    valid = {}
    for key, lst in groups.items():
        seen = set()
        uniq = []
        for r in lst:
            oh = r["obsHash"]
            if oh in seen:
                continue
            seen.add(oh)
            uniq.append(r)
        if len(uniq) >= 2:
            valid[key] = uniq
    print(f"{len(valid)} decision groups in {time.time()-t0:.1f}s", flush=True)
    return rows, refs_avg, valid


def group_metrics_blend(group, refs_avg, model_col, alpha):
    """Per-group pairwise accuracy using blended value = α·pred + (1-α)·rollout."""
    preds, ref_vals = [], []
    for r in group:
        key = (r["seed"], r["fightIdx"], r["decIdx"], r["obsHash"])
        ref = refs_avg.get(key)
        model_pred = _f(r.get(model_col, "nan"))
        rollout = _f(r.get("rawRolloutEval", "nan"))
        if ref is None or math.isnan(model_pred) or math.isnan(rollout):
            continue
        blended = alpha * model_pred + (1.0 - alpha) * rollout
        preds.append(blended)
        ref_vals.append(ref)

    if len(preds) < 2:
        return None

    n = len(preds)
    correct = total = 0
    for i in range(n):
        for j in range(i + 1, n):
            dref = ref_vals[i] - ref_vals[j]
            if abs(dref) <= PAIR_EPS:
                continue
            total += 1
            if (preds[i] > preds[j]) == (ref_vals[i] > ref_vals[j]):
                correct += 1

    if total == 0:
        return None

    imax_ref = ref_vals.index(max(ref_vals))
    imax_pred = preds.index(max(preds))
    return {
        "pairwiseAcc": correct / total,
        "top1": 1.0 if imax_pred == imax_ref else 0.0,
        "regret": max(ref_vals) - ref_vals[imax_pred],
        "nLeaves": len(preds),
    }


def bootstrap_ci(vals):
    vals = [float(v) for v in vals if not math.isnan(v)]
    if len(vals) < 5:
        return [float("nan")] * 3
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(vals)
    means = []
    for _ in range(2000):
        s = 0.0
        for _ in range(n):
            s += vals[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return [sum(vals) / n, means[49], means[1949]]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leafdiag", required=True, help="leafdiag CSV path")
    ap.add_argument("--leafref", required=True, help="leafref CSV path")
    ap.add_argument(
        "--alphas",
        default="0,0.05,0.1,0.15,0.2,0.3,0.5,0.7",
        help="comma-separated α values (default: 0,0.05,0.1,0.15,0.2,0.3,0.5,0.7)",
    )
    ap.add_argument("--json", default=None, help="write machine-readable JSON summary")
    args = ap.parse_args(argv)

    alphas = [float(a.strip()) for a in args.alphas.split(",") if a.strip()]

    _, refs_avg, valid = load_data(args.leafdiag, args.leafref)

    results = {}
    t0 = time.time()

    for alpha in alphas:
        for model_name, model_col in MODEL_COLS.items():
            accs, top1s, regrets = [], [], []
            for group in valid.values():
                m = group_metrics_blend(group, refs_avg, model_col, alpha)
                if m is None:
                    continue
                accs.append(m["pairwiseAcc"])
                top1s.append(m["top1"])
                regrets.append(m["regret"])

            n = len(accs)
            if n < 2:
                continue
            results[f"{model_name}|α={alpha}"] = {
                "nGroups": n,
                "pairwiseAcc": bootstrap_ci(accs),
                "top1": bootstrap_ci(top1s),
                "regret": bootstrap_ci(regrets),
                "mean_pairwiseAcc": sum(accs) / n,
                "mean_top1": sum(top1s) / n,
                "mean_regret": sum(regrets) / n,
            }
        print(f"  α={alpha} done in {time.time()-t0:.1f}s", flush=True)

    print(f"All α sweep completed in {time.time()-t0:.1f}s", flush=True)

    # Print table
    def fmt(ci):
        if math.isnan(ci[0]):
            return "NaN"
        return f"{ci[0]:.4f} [{ci[1]:.4f},{ci[2]:.4f}]"

    print()
    print(
        f"{'α':>6s}  {'endHp pairAcc':>22s}  {'utilR pairAcc':>22s}  "
        f"{'Δpair':>8s}  {'endHp top1':>12s}  {'utilR top1':>12s}  {'Δtop1':>8s}"
    )
    print("-" * 110)
    for alpha in alphas:
        ek = f"endHp|α={alpha}"
        uk = f"utilityR|α={alpha}"
        if ek not in results or uk not in results:
            continue
        e, u = results[ek], results[uk]
        dpair = e["pairwiseAcc"][0] - u["pairwiseAcc"][0]
        dtop1 = e["top1"][0] - u["top1"][0]
        print(
            f"{alpha:6.2f}  {fmt(e['pairwiseAcc']):>22s}  {fmt(u['pairwiseAcc']):>22s}  "
            f"{dpair:+8.4f}  {e['top1'][0]:>12.4f}  {u['top1'][0]:>12.4f}  {dtop1:+8.4f}"
        )

    # Key questions
    print()
    print("KEY QUESTIONS:")
    # Q1: Does endHp peak at moderate α?
    endHp_accs = [(a, results[f"endHp|α={a}"]["mean_pairwiseAcc"]) for a in alphas]
    endHp_best_alpha, endHp_best_acc = max(endHp_accs, key=lambda x: x[1])
    endHp_alpha0_acc = results[f"endHp|α=0.0"]["mean_pairwiseAcc"]
    print(
        f"  Q1: endHp peak at α={endHp_best_alpha} "
        f"(acc={endHp_best_acc:.4f} vs α=0: {endHp_alpha0_acc:.4f})"
    )

    # Q2: Does utilityR degrade monotonically?
    util_accs = [(a, results[f"utilityR|α={a}"]["mean_pairwiseAcc"]) for a in alphas]
    increasing = all(
        util_accs[i][1] >= util_accs[i + 1][1] for i in range(len(util_accs) - 1)
    )
    util_alpha0_acc = results[f"utilityR|α=0.0"]["mean_pairwiseAcc"]
    util_all_accs = [results[f"utilityR|α={a}"]["mean_pairwiseAcc"] for a in alphas]
    util_deltas = [
        util_all_accs[i] - util_alpha0_acc for i in range(1, len(util_all_accs))
    ]
    util_max_drop = min(util_deltas)
    util_max_drop_alpha = alphas[1 + util_deltas.index(util_max_drop)]
    print(
        f"  Q2: utilityR monotonically decreasing: {increasing} "
        f"(max drop {util_max_drop:+.4f} at α={util_max_drop_alpha})"
    )

    # Q3: Any α where utilityR ≈ endHp?
    min_gap = float("inf")
    min_gap_alpha = -1
    for alpha in alphas:
        gap = abs(
            results[f"endHp|α={alpha}"]["mean_pairwiseAcc"]
            - results[f"utilityR|α={alpha}"]["mean_pairwiseAcc"]
        )
        if gap < min_gap:
            min_gap = gap
            min_gap_alpha = alpha
    print(
        f"  Q3: Closest models at α={min_gap_alpha} "
        f"(gap={min_gap:.4f})"
    )

    # Q4: α=0 baseline (both models identical — sanity check)
    e0 = results["endHp|α=0.0"]
    u0 = results["utilityR|α=0.0"]
    print(
        f"  Q4: α=0 sanity — endHp={e0['mean_pairwiseAcc']:.4f} "
        f"utiliyR={u0['mean_pairwiseAcc']:.4f} "
        f"(should be equal: {abs(e0['mean_pairwiseAcc']-u0['mean_pairwiseAcc'])<1e-6})"
    )

    if args.json:
        # Convert tuple CIs to lists for JSON serialization
        serializable = {}
        for k, v in results.items():
            serializable[k] = {
                "nGroups": v["nGroups"],
                "pairwiseAcc": list(v["pairwiseAcc"]),
                "top1": list(v["top1"]),
                "regret": list(v["regret"]),
                "mean_pairwiseAcc": v["mean_pairwiseAcc"],
                "mean_top1": v["mean_top1"],
                "mean_regret": v["mean_regret"],
            }
        with open(args.json, "w") as f:
            json.dump(serializable, f, indent=2)
        print(f"\nSaved {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
