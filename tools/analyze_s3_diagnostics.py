#!/usr/bin/env python3
"""Summarize opt-in Searcher3 belief-boundary and root-race CSV diagnostics."""
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict

def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def f(row, key):
    try:
        value = float(row[key])
        return value if math.isfinite(value) else None
    except (KeyError, ValueError):
        return None

def summarize_belief(path):
    data = rows(path)
    if not data:
        print("belief: no rows")
        return
    def mean(k):
        v = [x for r in data if (x := f(r, k)) is not None]
        return statistics.mean(v) if v else float("nan")
    print(f"belief rows={len(data)} seeds={len({r['seed'] for r in data})}")
    print("metric,mean,min,max")
    for k in ("compatible_fraction", "distinct_draw_orders",
              "distinct_rng_signatures", "ess", "fallback_fraction",
              "stale_fraction"):
        v = [x for r in data if (x := f(r, k)) is not None]
        if v:
            print(f"{k},{statistics.mean(v):.4f},{min(v):.4f},{max(v):.4f}")
    print("carried_boundaries,", sum(r["belief_carried"] == "1" for r in data))
    print("rebuilt_boundaries,", sum(r["belief_rebuilt"] == "1" for r in data))
    print("boundary_updates,", sum(r["boundary_update_applied"] == "1" for r in data))

def summarize_race(path):
    data = rows(path)
    if not data:
        print("root: no rows")
        return
    states = {(r["seed"], r["floor"], r["encounter"], r["turn"],
               r["decision_index"]) for r in data}
    by_state = defaultdict(list)
    for r in data:
        by_state[(r["seed"], r["floor"], r["encounter"], r["turn"],
                  r["decision_index"])].append(r)
    print(f"root rows={len(data)} states={len(states)} seeds={len({r['seed'] for r in data})}")
    print("budget,disagreement_rate,disagreements,states")
    for budget in ("250", "500", "1000"):
        disagreements = 0
        for group in by_state.values():
            chosen = group[0][f"chosen_{budget}"]
            if chosen != group[0]["chosen_4000"]:
                disagreements += 1
        print(f"{budget},{disagreements / len(states):.4f},{disagreements},{len(states)}")
    disagreements = []
    for group in by_state.values():
        base = group[0]
        for budget in ("250", "500", "1000"):
            if base[f"chosen_{budget}"] == base["chosen_4000"]:
                continue
            selected = next((r for r in group
                             if r["action_bits"] == base[f"chosen_{budget}"]), None)
            disagreements.append((base, budget, selected))
    if disagreements:
        end_turn = sum(((int(base[f"chosen_{budget}"]) >> 29) & 7) == 4
                       for base, budget, selected in disagreements)
        large = sum(int(base["n_actions"]) >= 8
                    for base, budget, selected in disagreements)
        avail = sum(selected is not None and f(selected, "availability") is not None
                    and f(selected, "availability") < f(selected, "particle_count")
                    for base, budget, selected in disagreements)
        print("disagreement_context,total,end_turn,large_action_set,availability_mismatch")
        print(f"all,{len(disagreements)},{end_turn},{large},{avail}")
    print("regret_band,count,fraction")
    regrets = []
    for group in by_state.values():
        base = group[0]
        for budget in ("250", "500", "1000"):
            if base[f"chosen_{budget}"] == base["chosen_4000"]:
                continue
            selected = next((r for r in group
                             if r["action_bits"] == base[f"chosen_{budget}"]), None)
            x = f(selected, "deep_regret") if selected else None
            if x is not None:
                regrets.append(x)
    bands = (("<0.5", lambda x: x < .5),
             ("0.5-2", lambda x: .5 <= x < 2),
             ("2-5", lambda x: 2 <= x < 5),
             (">=5", lambda x: x >= 5))
    for label, pred in bands:
        n = sum(pred(x) for x in regrets)
        print(f"{label},{n},{n / len(regrets) if regrets else 0:.4f}")
    if regrets:
        print(f"disagreement_regret_mean,{statistics.mean(regrets):.4f}")
        print(f"disagreement_regret_median,{statistics.median(regrets):.4f}")

def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: analyze_s3_diagnostics.py belief.csv root.csv")
    summarize_belief(sys.argv[1])
    print()
    summarize_race(sys.argv[2])

if __name__ == "__main__":
    main()