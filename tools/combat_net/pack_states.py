#!/usr/bin/env python3
"""Pack silverazgen root rows into training rows for the combat net (combat plan stage 0, 2026-11-08).

usage: pack_states.py OUT.jsonl.gz ROWS.jsonl.gz [ROWS.jsonl.gz ...]

One output row per searched root (rows with "skipped": true, one-action roots, are kept with an empty policy):

  seed, fight, decision, act, floor, room, encounter, turn
  x        - wire_encoder.encode(wire)
  edges    - per root edge: parsed semantic action (wire_encoder.parse_semantic), visits, q
  policy   - visit shares of the edges (Silver's root distribution; the plan's policy target)
  chosen   - index of the edge Silver played (-1 if it is not among the edges)
  value    - the fight's real outcome: won, endHp, preHp, preMaxHp (from the fight row), and the fight's own
             Silver end score `score`
  aux      - realized HP loss (HP now minus HP at the first root of a later turn, or the fight's end HP when the fight
             ends first) to turn+1 and turn+2: the plan's "incoming damage" heads, measured on the played line

A root whose wire is missing (wireError) or whose fight row is missing or invalid is dropped and counted. Every wire
goes through wire_encoder.encode, which raises on a field it does not know: the pack fails rather than drop it.
Prints counts as JSON on stdout.
"""

import gzip
import importlib.util
import json
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("wire_encoder", os.path.join(_here, "wire_encoder.py"))
we = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(we)


def fights_of(path):
    """Yields (fight row, [root rows]) in file order."""
    roots = []
    with gzip.open(path, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") == "root":
                roots.append(r)
            elif r.get("kind") == "fight":
                mine = [x for x in roots if x["seed"] == r["seed"] and x["fight"] == r["fight"]]
                roots = [x for x in roots if not (x["seed"] == r["seed"] and x["fight"] == r["fight"])]
                yield r, mine
    if roots:
        yield None, roots


def hp_loss_after(roots, i, turns, end_hp):
    t = roots[i]["turn"] + turns
    for r in roots[i + 1:]:
        if r["turn"] >= t:
            return roots[i]["hp"] - r["hp"]
    return roots[i]["hp"] - end_hp


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    counts = {"files": 0, "fights": 0, "rows": 0, "multiEdgeRows": 0, "droppedNoWire": 0,
              "droppedNoFight": 0, "droppedInvalidFight": 0}
    with gzip.open(argv[1], "wt") as out:
        for path in argv[2:]:
            counts["files"] += 1
            for fight, roots in fights_of(path):
                if fight is None:
                    counts["droppedNoFight"] += len(roots)
                    continue
                if not fight.get("valid", False):
                    counts["droppedInvalidFight"] += len(roots)
                    continue
                counts["fights"] += 1
                end_hp = fight["endHp"] if fight["won"] else 0
                for i, r in enumerate(roots):
                    if not r.get("wire"):
                        counts["droppedNoWire"] += 1
                        continue
                    edges = r["edges"]
                    total = sum(e["visits"] for e in edges)
                    chosen = next((j for j, e in enumerate(edges) if e["semantic"] == r["chosen"]), -1)
                    row = {
                        "seed": r["seed"], "fight": r["fight"], "decision": r["decision"], "act": r["act"],
                        "floor": r["floor"], "room": r["room"], "encounter": r["encounter"], "turn": r["turn"],
                        "x": we.encode(r["wire"]),
                        "edges": [{"a": we.parse_semantic(e["semantic"]), "visits": e["visits"], "q": e["q"]}
                                  for e in edges],
                        "policy": [e["visits"] / total for e in edges] if total > 0 and len(edges) > 1 else [],
                        "chosen": chosen,
                        "value": {"won": fight["won"], "endHp": end_hp, "preHp": fight["preHp"],
                                  "preMaxHp": fight["preMaxHp"], "score": fight["score"]},
                        "aux": {"hpLoss1": hp_loss_after(roots, i, 1, end_hp),
                                "hpLoss2": hp_loss_after(roots, i, 2, end_hp)},
                    }
                    out.write(json.dumps(row, separators=(",", ":")) + "\n")
                    counts["rows"] += 1
                    counts["multiEdgeRows"] += len(edges) > 1
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
