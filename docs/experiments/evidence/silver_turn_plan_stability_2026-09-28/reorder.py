import json, sys
from collections import Counter, defaultdict
sys.path.insert(0, '.')
from analyze_plan import load, share, END_TURN
def last_hash(plan):
    h = [s["hash"] for s in plan if "hash" in s]
    return h[-1] if h else None
for path in sys.argv[1:]:
    rows, combats = load(path)
    c = Counter(); sims = Counter()
    for v in combats.values():
        for a, b in zip(v, v[1:]):
            pa, pb = a["turn_plan"], b["turn_plan"]
            if not pa or "hash" not in pa[0] or a["turn"] != b["turn"] or b["root_hash"] != pa[0]["hash"] \
               or b["inherited_visits"] == 0 or len(pa) < 2 or not pb or b["singleton_skip"]:
                continue
            if pa[1]["action"] == pb[0]["action"]:
                continue
            kind = "planned_end->played" if pa[1]["action_type"] == END_TURN else "card->end" if pb[0]["action_type"] == END_TURN else "card->card"
            if kind == "card->card" and a["turn_plan_stop"] == "end_turn" and b["turn_plan_stop"] == "end_turn":
                kind += "|same_end_state" if last_hash(pa) == last_hash(pb) else "|different_end_state"
            elif kind == "card->card":
                kind += "|plan_hits_chance_or_terminal"
            c[kind] += 1; sims[kind] += b["completed_simulations"]
    print(path, dict(c))
