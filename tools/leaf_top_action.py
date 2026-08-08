#!/usr/bin/env python3
"""Top-action agreement analysis for the leafdiag/leafref corpus.

For each decision group, identifies which leaf each model picks as "best"
(using the blended value at the deployed α), and compares against the
reference's choice.

Answers (EXPERIMENTS.md §141):
- How often do the two models agree on the best leaf?
- When they disagree, which model matches the reference?
- Are disagreements concentrated in won/lost fights, HP bands, depth bands?
- Can per-fight agreement scores predict fight outcomes?

Usage:
  python3 tools/leaf_top_action.py \
    --leafdiag build/leafdiag_slim.csv \
    --leafref build/leafref_gate_64_4k.csv \
    --alpha-endhp 0.3 \
    --alpha-utilityr 0.1 \
    --json build/leaf_top_action.json
"""
import argparse
import csv
import json
import math
import random
import sys
import time

BOOTSTRAP_SEED = 20260808


def _f(x):
    try: return float(x)
    except: return float("nan")


def load_data(leafdiag_path, leafref_path):
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
    return refs_avg, valid


def blended_value(r, model_col, alpha):
    """α·model_pred + (1−α)·rawRolloutEval."""
    model_pred = _f(r.get(model_col, "nan"))
    rollout = _f(r.get("rawRolloutEval", "nan"))
    if math.isnan(model_pred) or math.isnan(rollout):
        return float("nan")
    return alpha * model_pred + (1.0 - alpha) * rollout


def top_action(group, refs_avg, model_col, alpha):
    """Return obsHash of the leaf with highest blended value, plus all blended values."""
    best_hash = None
    best_val = float("-inf")
    vals = []
    for r in group:
        key = (r["seed"], r["fightIdx"], r["decIdx"], r["obsHash"])
        bv = blended_value(r, model_col, alpha)
        ref = refs_avg.get(key, float("nan"))
        if math.isnan(bv) or math.isnan(ref):
            continue
        vals.append((bv, ref, r["obsHash"]))
        if bv > best_val:
            best_val = bv
            best_hash = r["obsHash"]
    return best_hash, vals


def hp_band(r):
    cur, mx = _f(r.get("curHp", "nan")), _f(r.get("maxHp", "nan"))
    frac = cur / mx if mx > 0 and not math.isnan(cur) else float("nan")
    if math.isnan(frac): return "na"
    if frac < 0.30: return "low"
    if frac < 0.70: return "mid"
    return "high"


def depth_band(r):
    d = _f(r.get("treeDepth", "nan"))
    if math.isnan(d): return "na"
    d = int(d)
    if d < 5: return "shallow"
    if d < 15: return "mid"
    return "deep"


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leafdiag", required=True)
    ap.add_argument("--leafref", required=True)
    ap.add_argument("--alpha-endhp", type=float, default=0.3,
                    help="Blend α for endHp model (deployed default: 0.3)")
    ap.add_argument("--alpha-utilityr", type=float, default=0.1,
                    help="Blend α for utilityR model (§134 used α=0.1)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    refs_avg, valid = load_data(args.leafdiag, args.leafref)

    MODEL_COLS = {"endHp": "endHp_pred", "utilityR": "utilityR_pred"}
    ALPHAS = {"endHp": args.alpha_endhp, "utilityR": args.alpha_utilityr}

    # Per-group: which leaf does each model pick? Which does the reference pick?
    t0 = time.time()
    decisions = []  # list of dicts

    for (seed, fightIdx, decIdx), group in valid.items():
        ref_best_hash = None
        ref_best_val = float("-inf")
        for r in group:
            key = (seed, fightIdx, decIdx, r["obsHash"])
            ref = refs_avg.get(key, float("nan"))
            if math.isnan(ref):
                continue
            if ref > ref_best_val:
                ref_best_val = ref
                ref_best_hash = r["obsHash"]
        if ref_best_hash is None:
            continue

        endHp_hash, _ = top_action(group, refs_avg, MODEL_COLS["endHp"], ALPHAS["endHp"])
        utilR_hash, _ = top_action(group, refs_avg, MODEL_COLS["utilityR"], ALPHAS["utilityR"])

        if endHp_hash is None or utilR_hash is None:
            continue

        first_row = group[0]
        decisions.append({
            "seed": seed,
            "fightIdx": fightIdx,
            "decIdx": decIdx,
            "fightWon": first_row["fightWon"],
            "hp": hp_band(first_row),
            "depth": depth_band(first_row),
            "nLeaves": len(group),
            "refBest": ref_best_hash,
            "endHpBest": endHp_hash,
            "utilRBest": utilR_hash,
            "endHpMatchRef": endHp_hash == ref_best_hash,
            "utilRMatchRef": utilR_hash == ref_best_hash,
            "modelsAgree": endHp_hash == utilR_hash,
        })

    print(f"Analyzed {len(decisions)} decisions in {time.time()-t0:.1f}s", flush=True)

    # ---- OVERALL STATISTICS ----
    n = len(decisions)
    endHp_match = sum(1 for d in decisions if d["endHpMatchRef"])
    utilR_match = sum(1 for d in decisions if d["utilRMatchRef"])
    models_agree = sum(1 for d in decisions if d["modelsAgree"])
    both_match = sum(1 for d in decisions if d["endHpMatchRef"] and d["utilRMatchRef"])
    neither_match = sum(1 for d in decisions if not d["endHpMatchRef"] and not d["utilRMatchRef"])
    disagree = n - models_agree

    # When models disagree, who's right?
    disagree_decisions = [d for d in decisions if not d["modelsAgree"]]
    endHp_right_on_disagree = sum(1 for d in disagree_decisions if d["endHpMatchRef"])
    utilR_right_on_disagree = sum(1 for d in disagree_decisions if d["utilRMatchRef"])

    # ---- STRATIFICATION ----
    strata = {}
    for d in decisions:
        for key in [f"won={d['fightWon']}", f"hp={d['hp']}", f"depth={d['depth']}",
                     f"hp={d['hp']}|depth={d['depth']}",
                     f"won={d['fightWon']}|hp={d['hp']}",
                     f"won={d['fightWon']}|depth={d['depth']}"]:
            strata.setdefault(key, []).append(d)

    # ---- PER-FIGHT AGREEMENT ----
    # Aggregate per (seed, fightIdx): count decisions, model-ref matches
    per_fight = {}
    for d in decisions:
        fkey = (d["seed"], d["fightIdx"])
        per_fight.setdefault(fkey, {"nDecisions": 0, "endHpMatch": 0, "utilRMatch": 0,
                                     "modelsAgree": 0, "fightWon": d["fightWon"]})
        pf = per_fight[fkey]
        pf["nDecisions"] += 1
        pf["endHpMatch"] += d["endHpMatchRef"]
        pf["utilRMatch"] += d["utilRMatchRef"]
        pf["modelsAgree"] += d["modelsAgree"]

    # ---- PRINT REPORT ----
    print()
    print("=" * 70)
    print("EXPERIMENT C: Top-action agreement analysis")
    print(f"α_endHp={ALPHAS['endHp']}, α_utilityR={ALPHAS['utilityR']}")
    print("=" * 70)
    print()

    print("OVERALL:")
    print(f"  Total decisions:                {n}")
    print(f"  Models agree on best leaf:      {models_agree} ({100*models_agree/n:.1f}%)")
    print(f"  Models DISAGREE:                {disagree} ({100*disagree/n:.1f}%)")
    print(f"  endHp matches reference:        {endHp_match} ({100*endHp_match/n:.1f}%)")
    print(f"  utilityR matches reference:     {utilR_match} ({100*utilR_match/n:.1f}%)")
    print(f"  Both match reference:           {both_match} ({100*both_match/n:.1f}%)")
    print(f"  Neither matches reference:      {neither_match} ({100*neither_match/n:.1f}%)")
    print()

    if disagree > 0:
        print("WHEN MODELS DISAGREE:")
        print(f"  endHp is right:                 {endHp_right_on_disagree} "
              f"({100*endHp_right_on_disagree/disagree:.1f}%)")
        print(f"  utilityR is right:              {utilR_right_on_disagree} "
              f"({100*utilR_right_on_disagree/disagree:.1f}%)")
        both_wrong = disagree - endHp_right_on_disagree - utilR_right_on_disagree
        print(f"  both wrong:                     {both_wrong} "
              f"({100*both_wrong/disagree:.1f}%)")
        print()

    print("BY STRATUM:")
    print(f"  {'Stratum':<30s} {'n':>6s}  {'agree%':>7s}  "
          f"{'endHp=ref%':>10s}  {'utilR=ref%':>10s}  {'Δ(ref%)':>8s}  "
          f"{'endHpR_dis%':>11s}  {'utilRR_dis%':>11s}")
    print("  " + "-" * 100)

    for skey in sorted(strata.keys()):
        sd = strata[skey]
        sn = len(sd)
        if sn < 10:
            continue
        agree_pct = 100 * sum(1 for d in sd if d["modelsAgree"]) / sn
        e_match = 100 * sum(1 for d in sd if d["endHpMatchRef"]) / sn
        u_match = 100 * sum(1 for d in sd if d["utilRMatchRef"]) / sn
        sdis = [d for d in sd if not d["modelsAgree"]]
        sdis_n = len(sdis)
        if sdis_n > 0:
            er_dis = 100 * sum(1 for d in sdis if d["endHpMatchRef"]) / sdis_n
            ur_dis = 100 * sum(1 for d in sdis if d["utilRMatchRef"]) / sdis_n
        else:
            er_dis = ur_dis = float("nan")

        print(f"  {skey:<30s} {sn:6d}  {agree_pct:6.1f}%  "
              f"{e_match:9.1f}%  {u_match:9.1f}%  {e_match-u_match:+7.1f}%  "
              f"{er_dis:10.1f}%  {ur_dis:10.1f}%")

    # ---- PER-FIGHT CORRELATION ----
    print()
    print("PER-FIGHT ANALYSIS:")
    won_fights = [pf for pf in per_fight.values() if pf["fightWon"] == "1"]
    lost_fights = [pf for pf in per_fight.values() if pf["fightWon"] == "0"]

    for label, fights in [("WON", won_fights), ("LOST", lost_fights)]:
        if not fights:
            continue
        nf = len(fights)
        avg_dec = sum(pf["nDecisions"] for pf in fights) / nf
        avg_e_match = sum(pf["endHpMatch"] / pf["nDecisions"] for pf in fights) / nf
        avg_u_match = sum(pf["utilRMatch"] / pf["nDecisions"] for pf in fights) / nf
        avg_agree = sum(pf["modelsAgree"] / pf["nDecisions"] for pf in fights) / nf
        print(f"  {label} fights ({nf}): avg decisions={avg_dec:.1f}, "
              f"endHp=ref {100*avg_e_match:.1f}%, utilR=ref {100*avg_u_match:.1f}%, "
              f"agree {100*avg_agree:.1f}%")

    #  fights where endHp more often correct
    e_better = sum(1 for pf in per_fight.values()
                   if pf["endHpMatch"] > pf["utilRMatch"])
    u_better = sum(1 for pf in per_fight.values()
                   if pf["utilRMatch"] > pf["endHpMatch"])
    tie = sum(1 for pf in per_fight.values()
              if pf["endHpMatch"] == pf["utilRMatch"])
    print(f"  Per-fight winner: endHp {e_better}, utilityR {u_better}, tie {tie}")

    # ---- DECISIONS WHERE MODELS DISAGREE AND ONE IS RIGHT ----
    print()
    print("DISAGREEMENT BREAKDOWN:")
    e_only = sum(1 for d in disagree_decisions
                 if d["endHpMatchRef"] and not d["utilRMatchRef"])
    u_only = sum(1 for d in disagree_decisions
                 if d["utilRMatchRef"] and not d["endHpMatchRef"])
    both_wrong_d = disagree - e_only - u_only
    print(f"  endHp right, utilR wrong:  {e_only}")
    print(f"  utilR right, endHp wrong:  {u_only}")
    print(f"  both wrong:                {both_wrong_d}")
    if e_only + u_only > 0:
        print(f"  endHp wins {100*e_only/(e_only+u_only):.1f}% of resolvable disagreements")

    # Where do e_only vs u_only occur?
    if e_only + u_only > 0:
        print()
        print("  RESOLVABLE DISAGREEMENTS BY STRATUM:")
        for skey in sorted(strata.keys()):
            sd = strata[skey]
            if len(sd) < 10:
                continue
            se = sum(1 for d in sd if d["endHpMatchRef"] and not d["utilRMatchRef"])
            su = sum(1 for d in sd if d["utilRMatchRef"] and not d["endHpMatchRef"])
            if se + su == 0:
                continue
            print(f"    {skey:<30s} endHp:{se:4d}  utilR:{su:4d}  "
                  f"ratio={100*se/(se+su):.0f}% endHp")

    # ---- SUMMARY ----
    print()
    print("SUMMARY:")
    agree_pct = 100 * models_agree / n
    e_adv = endHp_match - utilR_match
    print(f"  Agreement rate: {agree_pct:.1f}%")
    print(f"  endHp advantage: {e_adv:+d} decisions ({100*e_adv/n:+.2f}pp)")
    if disagree > 0:
        print(f"  On disagreements: endHp right {100*endHp_right_on_disagree/disagree:.1f}% "
              f"vs utilR {100*utilR_right_on_disagree/disagree:.1f}%")

    if args.json:
        result = {
            "nDecisions": n,
            "modelsAgree": models_agree,
            "disagree": disagree,
            "endHpMatchRef": endHp_match,
            "utilRMatchRef": utilR_match,
            "bothMatchRef": both_match,
            "neitherMatchRef": neither_match,
            "endHpRightOnDisagree": endHp_right_on_disagree,
            "utilRRightOnDisagree": utilR_right_on_disagree,
            "endHpOnlyRight": e_only,
            "utilROnlyRight": u_only,
            "perFight": {
                "nFights": len(per_fight),
                "endHpBetterFights": e_better,
                "utilRBetterFights": u_better,
                "tieFights": tie,
            },
            "strata": {k: {
                "n": len(strata[k]),
                "modelsAgree": sum(1 for d in strata[k] if d["modelsAgree"]),
                "endHpMatchRef": sum(1 for d in strata[k] if d["endHpMatchRef"]),
                "utilRMatchRef": sum(1 for d in strata[k] if d["utilRMatchRef"]),
                "endHpOnlyRight": sum(1 for d in strata[k]
                                      if d["endHpMatchRef"] and not d["utilRMatchRef"]),
                "utilROnlyRight": sum(1 for d in strata[k]
                                      if d["utilRMatchRef"] and not d["endHpMatchRef"]),
            } for k in sorted(strata.keys()) if len(strata[k]) >= 10},
        }
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
