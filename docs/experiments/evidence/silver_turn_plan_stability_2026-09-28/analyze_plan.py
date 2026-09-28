"""Within-turn plan stability of native Silver from tree-profile rows with turn_plan."""
import gzip
import json
import sys
from collections import Counter, defaultdict

END_TURN = 4


def load(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        rows = [json.loads(l) for l in f]
    assert all(not r["error"] for r in rows)
    combats = defaultdict(list)
    for r in rows:
        combats[(r["seed"], r["combat_id"])].append(r)
    for v in combats.values():
        v.sort(key=lambda r: r["decision"])
    return rows, combats


def share(step):
    return step["visits"] / step["total"] if step["total"] else 0.0


def analyze(path):
    rows, combats = load(path)
    out = {"rows": len(rows), "combats": len(combats)}
    searched = [r for r in rows if not r["singleton_skip"]]
    out["searched_decisions"] = len(searched)
    out["singleton_decisions"] = len(rows) - len(searched)
    out["simulations"] = sum(r["completed_simulations"] for r in rows)
    out["plan_stop"] = dict(Counter(r["turn_plan_stop"] for r in searched))

    # Turn-level compute split.
    turns = defaultdict(list)
    for key, v in combats.items():
        for r in v:
            turns[key + (r["turn"],)].append(r)
    first_sims = later_sims = 0
    later_searched = 0
    per_turn_searched = Counter()
    for t in turns.values():
        s = [r for r in t if not r["singleton_skip"]]
        per_turn_searched[len(s)] += 1
        if s:
            first_sims += s[0]["completed_simulations"]
            later_sims += sum(r["completed_simulations"] for r in s[1:])
            later_searched += len(s) - 1
    out["turns"] = len(turns)
    out["searched_decisions_per_turn"] = dict(sorted(per_turn_searched.items()))
    out["sims_first_decision_of_turn"] = first_sims
    out["sims_later_decisions_of_turn"] = later_sims
    out["later_decision_share_of_sims"] = later_sims / (first_sims + later_sims)

    # Next-step agreement: decision i planned step 2; decision i+1 (rerooted on
    # step 1's node, same turn, searched) chooses its own first step.
    pairs = []
    sanity = Counter()
    for v in combats.values():
        for a, b in zip(v, v[1:]):
            pa = a["turn_plan"]
            if not pa or "hash" not in pa[0]:
                continue  # first step stochastic, End Turn or unvisited
            if a["turn"] != b["turn"]:
                continue
            sanity["deterministic_step"] += 1
            if b["root_hash"] != pa[0]["hash"]:
                sanity["root_hash_mismatch"] += 1
                continue
            if b["inherited_visits"] == 0:
                sanity["not_rerooted"] += 1
                continue
            if len(pa) < 2 or not b["turn_plan"]:
                sanity["no_second_step"] += 1
                continue
            pred, act = pa[1], b["turn_plan"][0]
            pairs.append({
                "agree": pred["action"] == act["action"],
                "singleton": b["singleton_skip"],
                "share": share(pred),
                "visits": pred["visits"],
                "pred_end": pred["action_type"] == END_TURN,
                "act_end": act["action_type"] == END_TURN,
                "sims": b["completed_simulations"],
            })
    out["pair_sanity"] = dict(sanity)
    sp = [p for p in pairs if not p["singleton"]]
    out["next_step_pairs_searched"] = len(sp)
    out["next_step_agreement"] = sum(p["agree"] for p in sp) / len(sp)
    flips = [p for p in sp if not p["agree"]]
    out["flip_kinds"] = dict(Counter(
        ("planned_end->played" if p["pred_end"] else "planned_card->end" if p["act_end"] else "card->other_card")
        for p in flips))
    curve = []
    total_sims = out["simulations"]
    for t in (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        sel = [p for p in sp if p["share"] >= t]
        if not sel:
            continue
        curve.append({
            "min_share": t,
            "pairs": len(sel),
            "frac_of_pairs": len(sel) / len(sp),
            "agreement": sum(p["agree"] for p in sel) / len(sel),
            "flips": sum(not p["agree"] for p in sel),
            "sims_skippable": sum(p["sims"] for p in sel),
            "frac_total_sims": sum(p["sims"] for p in sel) / total_sims,
        })
    out["commit_curve"] = curve
    buckets = defaultdict(list)
    for p in sp:
        lo = min(int(p["share"] * 10), 9) / 10
        buckets[lo].append(p["agree"])
    out["agreement_by_share_decile"] = {f"{k:.1f}": [len(v), round(sum(v) / len(v), 3)]
                                        for k, v in sorted(buckets.items())}

    # Whole-turn adherence to the first searched decision's plan.
    outcome = Counter()
    matched_steps = Counter()
    for t in turns.values():
        s = [r for r in t]
        f = next((i for i, r in enumerate(s) if not r["singleton_skip"]), None)
        if f is None:
            continue
        plan = s[f]["turn_plan"]
        k = 0
        result = None
        while True:
            step = plan[k]
            if step["action_type"] == END_TURN:
                result = "followed_to_end_turn"
                break
            if "hash" not in step:
                result = "followed_to_chance_or_unvisited"
                break
            if k + 1 >= len(plan):
                result = "plan_ended_" + s[f]["turn_plan_stop"]
                break
            j = f + k + 1
            if j >= len(s) or s[j]["root_hash"] != step["hash"] or s[j]["inherited_visits"] == 0:
                result = "state_mismatch"
                break
            if s[j]["turn_plan"][0]["action"] != plan[k + 1]["action"]:
                result = "diverged_end_turn" if plan[k + 1]["action_type"] == END_TURN or \
                    s[j]["turn_plan"][0]["action_type"] == END_TURN else "diverged_card"
                break
            k += 1
        outcome[result] += 1
        matched_steps[k] += 1
    out["turn_plan_outcome"] = dict(outcome)
    out["turn_plan_steps_matched_before_stop"] = dict(sorted(matched_steps.items()))
    if any(r["adaptive"] for r in rows):
        ret = [r for r in searched if r["inherited_visits"] > 0]
        out["adaptive_retained_roots"] = len(ret)
        out["adaptive_retained_stopped_at_500"] = sum(r["completed_simulations"] == 500 for r in ret)
    return out


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print("==", path)
        print(json.dumps(analyze(path), indent=1))
