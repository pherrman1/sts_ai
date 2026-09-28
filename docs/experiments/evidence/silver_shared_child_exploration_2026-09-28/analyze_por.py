"""Stage 0 partial-order-reduction opportunity from tree-profile rows with `por`."""
import glob
import gzip
import json
import statistics
import sys
from collections import defaultdict


def rows_of(paths):
    for p in paths:
        with (gzip.open(p, "rt") if p.endswith(".gz") else open(p)) as f:
            for line in f:
                yield json.loads(line)


def summarize(rows, scope):
    agg = defaultdict(int)
    shares_c, shares_u = [], []
    for r in rows:
        c = r["por"][scope]
        for k, v in c.items():
            agg[k] += v
        if c["edge_visits"]:
            shares_c.append(c["confirmed_pruned_visits"] / c["edge_visits"])
            shares_u.append(c["candidate_pruned_visits"] / c["edge_visits"])
    n = agg["decision_nodes"]
    return {
        "decisions": len(rows),
        "pooled_confirmed_visit_share": round(agg["confirmed_pruned_visits"] / agg["edge_visits"], 4),
        "pooled_candidate_visit_share": round(agg["candidate_pruned_visits"] / agg["edge_visits"], 4),
        "median_confirmed_share": round(statistics.median(shares_c), 4),
        "p75_confirmed_share": round(statistics.quantiles(shares_c, n=4)[2], 4),
        "median_candidate_share": round(statistics.median(shares_u), 4),
        "edges_per_decision_node": round(agg["edges"] / n, 3),
        "after_confirmed_pruning": round((agg["edges"] - agg["confirmed_pruned_edges"]) / n, 3),
        "after_candidate_pruning": round((agg["edges"] - agg["candidate_pruned_edges"]) / n, 3),
        "confirmed_edge_share": round(agg["confirmed_pruned_edges"] / agg["edges"], 4),
        "candidate_edge_share": round(agg["candidate_pruned_edges"] / agg["edges"], 4),
    }


for label, pattern in (a.split("=", 1) for a in sys.argv[1:]):
    rows = [r for r in rows_of(sorted(glob.glob(pattern))) if not r["singleton_skip"] and not r["error"]]
    first = {}
    for r in sorted(rows, key=lambda r: (r["seed"], r["combat_id"], r["decision"])):
        first.setdefault((r["seed"], r["combat_id"], r["turn"]), r)
    firsts = list(first.values())
    print("==", label)
    print(" first searched decision per turn, root-turn nodes:", json.dumps(summarize(firsts, "root_turn")))
    print(" first searched decision per turn, all reachable:  ", json.dumps(summarize(firsts, "all")))
    print(" every searched decision, root-turn nodes:          ", json.dumps(summarize(rows, "root_turn")))
    # By number of distinct playable moves at the root.
    buckets = defaultdict(list)
    for r in firsts:
        buckets[min(r["root_actions"], 8)].append(r)
    for k in sorted(buckets):
        s = summarize(buckets[k], "root_turn")
        print(f"  root_actions {k}{'+' if k == 8 else ''}: n={s['decisions']} confirmed={s['pooled_confirmed_visit_share']} candidate={s['pooled_candidate_visit_share']}")
