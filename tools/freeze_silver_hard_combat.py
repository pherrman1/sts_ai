#!/usr/bin/env python3
"""Classify and deterministically select the silver_hard_combat_v1 pool."""
import argparse, hashlib, json, pathlib
from collections import Counter, defaultdict

MATERIAL_HP_DELTA = 0.10
TARGET_PER_SET = 64

def load_jsonl(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines() if x.strip()]

def classify(source, one, ten):
    src = {x["case_id"]: x for x in load_jsonl(source)}
    one = {x["case_id"]: x for x in load_jsonl(one)}
    ten = {x["case_id"]: x for x in load_jsonl(ten)}
    if set(src) != set(one) or not set(ten) <= set(src):
        raise SystemExit("capture and screen case IDs do not match")
    rows = []
    for case_id, hi in ten.items():
        lo = one[case_id]
        if lo["status"] != "ok" or hi["status"] != "ok":
            raise SystemExit(f"technical replay failure for {case_id}")
        lo_frac = lo["hp_end"] / lo["max_hp"] if lo["max_hp"] else 0.0
        hi_frac = hi["hp_end"] / hi["max_hp"] if hi["max_hp"] else 0.0
        if not lo["won"] and hi["won"]:
            category = "A"
        elif lo["won"] and not hi["won"]:
            category = "anomalous"
        elif not lo["won"] and not hi["won"]:
            category = "C"
        elif hi_frac - lo_frac >= MATERIAL_HP_DELTA:
            category = "B"
        else:
            category = "easy"
        item = dict(src[case_id])
        item.update({"result_1k": lo, "result_10k": hi, "category": category,
                     "hp_fraction_1k": lo_frac, "hp_fraction_10k": hi_frac,
                     "hp_fraction_delta": hi_frac - lo_frac})
        rows.append(item)
    return rows

def rank(x):
    # A first, then meaningful B, then C only if needed; easy/anomalous are last.
    order = {"A": 0, "B": 1, "C": 2, "easy": 3, "anomalous": 4}
    return (order[x["category"]], -x["hp_fraction_delta"], x["source_seed"],
            x["fight_index"], x["state_hash"])

def select(rows):
    # First select globally by scientific category, with the per-source cap.
    # Easy wins and anomalies are deliberately ineligible for v1.
    chosen, per_seed = [], Counter()
    for x in sorted((x for x in rows if x["category"] in ("A", "B", "C")), key=rank):
        if per_seed[x["source_seed"]] >= 2: continue
        chosen.append(x); per_seed[x["source_seed"]] += 1
        if len(chosen) == TARGET_PER_SET * 2: break
    if len(chosen) != TARGET_PER_SET * 2:
        raise SystemExit(f"only selected {len(chosen)} cases")
    # Deterministic source-disjoint balanced assignment. A tiny subset-sum
    # chooses exactly 64 cases for DEV while keeping the source groups intact;
    # ties resolve by seed order and category score.
    groups = defaultdict(list)
    for x in chosen: groups[x["source_seed"]].append(x)
    states = {0: (0, tuple())}
    for seed in sorted(groups):
        n = len(groups[seed]); score = sum(category_score(x) for x in groups[seed])
        for total, (old_score, picked) in list(states.items()):
            if total + n <= TARGET_PER_SET and total + n not in states:
                states[total + n] = (old_score + score, picked + (seed,))
    if TARGET_PER_SET not in states:
        raise SystemExit("cannot partition selected source groups into 64-case cohorts")
    dev_seeds = set(states[TARGET_PER_SET][1])
    dev = [x for s in dev_seeds for x in sorted(groups[s], key=rank)]
    hold = [x for s in groups if s not in dev_seeds for x in sorted(groups[s], key=rank)]
    if len(dev) != TARGET_PER_SET or len(hold) != TARGET_PER_SET:
        raise SystemExit(f"unbalanced selection dev={len(dev)} holdout={len(hold)}")
    for cohort, xs in (("hard64-dev", dev), ("hard64-holdout", hold)):
        for x in xs:
            x["cohort"] = cohort
            x["selection_reason"] = {"A": "1k loss -> 10k win",
                "B": "both win; 10k improves terminal HP fraction",
                "C": "difficult unresolved; retained for diversity"}.get(x["category"], "fallback")
    return sorted(dev + hold, key=lambda x: (x["cohort"], x["source_seed"], x["fight_index"]))

def category_score(x): return {"A": 0, "B": 1, "C": 2}.get(x["category"], 3)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("screen_1k"); ap.add_argument("screen_10k")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = classify(args.source, args.screen_1k, args.screen_10k)
    selected = select(rows)
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "classification.jsonl").write_text("".join(json.dumps(x, sort_keys=True, separators=(",", ":")) + "\n" for x in rows))
    for cohort in ("hard64-dev", "hard64-holdout"):
        (out / f"{cohort}.jsonl").write_text("".join(json.dumps(x, sort_keys=True, separators=(",", ":")) + "\n" for x in selected if x["cohort"] == cohort))
    receipt = {"material_hp_delta": MATERIAL_HP_DELTA, "target_per_set": TARGET_PER_SET,
               "counts": dict(Counter(x["category"] for x in rows)),
               "selected_counts": {c: dict(Counter(x["category"] for x in selected if x["cohort"] == c)) for c in ("hard64-dev", "hard64-holdout")},
               "source_seeds": {c: sorted({x["source_seed"] for x in selected if x["cohort"] == c}) for c in ("hard64-dev", "hard64-holdout")}}
    (out / "selection-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))

if __name__ == "__main__": main()
