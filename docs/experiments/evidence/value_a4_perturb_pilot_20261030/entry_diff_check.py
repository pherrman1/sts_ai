#!/usr/bin/env python3
"""Verify: each child's Act-4 entry record differs from the control's (child 0) only in its operator's fields.

  entry_diff_check.py A4P_JSON...      (a4p-SEED.json files written by a4_perturb.py)

Prints one line per violation and a JSON summary; exit 1 if any child changes a field outside its operator's.
"""
import json, sys

ALLOWED = [  # (op prefix, allowed record-key prefix), first match wins
    ("relic_counter", ("obs.relics.relic_counters",)),
    # Searing Blow keeps its upgrade count in obs.deck.misc
    ("upgrade", ("obs.deck.upgrades", "obs.deck.misc")), ("unupgrade", ("obs.deck.upgrades", "obs.deck.misc")),
    ("card", ("obs.deck.",)), ("relic", ("obs.relics.",)), ("potion", ("obs.potions",)),
    ("hp", ("obs.fixed_observation",)), ("max_hp", ("obs.fixed_observation",)), ("maxhp", ("obs.fixed_observation",)),
    ("gold", ("obs.fixed_observation",)),
]


def allowed(op):
    for p, keys in ALLOWED:
        if op.startswith(p):
            return keys
    return None


def main(paths):
    bad = n = unchanged = 0; ops = {}
    for path in paths:
        r = json.load(open(path)); ch = {c["child"]: c for c in r["children"]}
        base = ch[0]["entryRecord"]
        for k, c in sorted(ch.items()):
            if k == 0:
                continue
            n += 1; ops[c["op"]] = ops.get(c["op"], 0) + 1
            diff = sorted(x for x in set(base) | set(c["entryRecord"]) if base.get(x) != c["entryRecord"].get(x))
            keys = allowed(c["op"])
            if keys is None or any(not x.startswith(keys) for x in diff):
                bad += 1; print(r["seed"], k, c["op"], "changes", diff)
            if not diff:
                unchanged += 1
    print(json.dumps({"children": n, "violations": bad, "no_change": unchanged, "ops": ops}))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
