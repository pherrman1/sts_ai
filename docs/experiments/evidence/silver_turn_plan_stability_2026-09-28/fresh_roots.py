"""Plan agreement split by whether the next decision reused the retained tree.

Reused (rerooted) roots compare exact action bits on the same node. Roots the
32,768-node cap forced to restart compare a copy-insensitive key (card id,
upgrade, target; potion slot; End Turn; selection successor hash) because
state hashes include card unique ids. Needs profile steps with `card` fields.
"""
import statistics
import sys
from collections import Counter

from analyze_plan import END_TURN, load, share


def key(s):
    t = s["action_type"]
    if t == 0:
        return ("card", s["card"], s["upgraded"], s["target"])
    if t == 1:
        return ("potion", s["action"])
    if t == END_TURN:
        return ("end",)
    return ("select", s.get("hash"))


for path in sys.argv[1:]:
    rows, combats = load(path)
    total = sum(r["completed_simulations"] for r in rows)
    res = {"rerooted": Counter(), "fresh": Counter()}
    curve = {"rerooted": Counter(), "fresh": Counter()}
    sims = Counter()
    visits = {"agree": [], "flip": []}
    kinds = Counter()
    for v in combats.values():
        for a, b in zip(v, v[1:]):
            pa, pb = a["turn_plan"], b["turn_plan"]
            if not pa or "hash" not in pa[0] or a["turn"] != b["turn"] or b["root_hash"] != pa[0]["hash"]:
                continue
            if b["singleton_skip"] or len(pa) < 2 or not pb:
                continue
            kind = "rerooted" if b["inherited_visits"] > 0 else "fresh"
            p, q = pa[1], pb[0]
            if kind == "rerooted":
                ok = p["action"] == q["action"]
            else:
                kp, kq = key(p), key(q)
                if kp[0] == "select" and (kp[1] is None or kq[1] is None):
                    res[kind]["incomparable"] += 1
                    continue
                ok = kp == kq
            res[kind]["agree" if ok else "flip"] += 1
            for t in (0.6, 0.8, 0.9):
                if share(p) >= t:
                    curve[kind][f"{t}:{'agree' if ok else 'flip'}"] += 1
            if share(p) >= 0.8:
                sims[kind] += b["completed_simulations"]
                if kind == "fresh":
                    visits["agree" if ok else "flip"].append(p["visits"])
                    if not ok:
                        kinds["end->play" if p["action_type"] == END_TURN else
                              "play->end" if q["action_type"] == END_TURN else "card->card"] += 1
                        kinds["fresh_top_share>=0.5"] += share(q) >= 0.5
    print("==", path)
    for k in res:
        print(k, dict(res[k]), dict(sorted(curve[k].items())),
              "sims_at_share>=0.8_frac", round(sims[k] / total, 4))
    for o, vs in visits.items():
        if vs:
            print(f"fresh share>=0.8 {o}: n={len(vs)} planned visits median={statistics.median(vs)} min={min(vs)}")
    print("fresh share>=0.8 flip kinds", dict(kinds))
