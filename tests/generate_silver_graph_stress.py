#!/usr/bin/env python3
"""Deterministic synthetic retained-graph fixtures; not gameplay evidence."""
import json
import sys
from pathlib import Path


def generate(count):
    nodes = []
    edges = []
    for node_id in range(1, count + 1):
        depth = 0 if node_id == 1 else (node_id.bit_length() - 1)
        chance = node_id % 7 == 0
        n = max(0, count // (node_id + 1))
        nodes.append({"id": node_id, "parentId": node_id // 2 if node_id > 1 else 0,
                      "depth": depth, "isChanceNode": chance,
                      "hasState": not chance, "stateHash": 9007199254740993 + node_id,
                      "simulationCount": n, "victoryCount": n // 2,
                      "evaluationSum": n * .63,
                      **({} if chance else {"state": {
                          "turn": depth + 1, "player": {"curHp": max(1, 80-depth),
                          "maxHp": 80, "energy": node_id % 4},
                          "monsters": [{"id": "Cultist", "curHp": max(0, 48-depth),
                                        "maxHp": 48}]}})})
    for node_id in range(2, count + 1):
        parent = node_id // 2
        edges.append({"parentId": parent, "childId": node_id, "childCaptured": True,
                      "visitCount": max(0, count // (node_id + 1)),
                      "chanceOutcome": parent % 7 == 0, "rngAdvanceSteps": node_id % 3,
                      "actionLabel": "Synthetic action " + str(node_id) + " → Cultist",
                      "actionFingerprint": "synthetic:" + str(node_id)})
    for node_id in range(21, count, 23):
        edges.append({"parentId": node_id, "childId": node_id - 3,
                      "childCaptured": True, "visitCount": 1,
                      "chanceOutcome": False, "rngAdvanceSteps": 0,
                      "actionLabel": "Synthetic shared reference",
                      "actionFingerprint": "shared:" + str(node_id)})
    for node_id in range(31, count, 41):
        edges.append({"parentId": node_id, "childId": node_id,
                      "childCaptured": True, "visitCount": 1,
                      "chanceOutcome": False, "rngAdvanceSteps": 0,
                      "actionLabel": "Synthetic self loop",
                      "actionFingerprint": "loop:" + str(node_id)})
    return {"session": "synthetic-stress", "sequence": 1, "observationHash": "synthetic",
            "observation": {"boundary": "combat", "hp": 80, "maxHp": 80,
                            "silverRoot": {"encounter": "CULTIST"}},
            "response": {"ready": True, "session": "synthetic-stress", "sequence": 1,
                         "observationHash": "synthetic", "advisor": {"evaluators": [{
                             "id": "silver_player_decision_v2", "status": "OK",
                             "selectedAction": "synthetic:2", "selectedLabel": "Synthetic action 2",
                             "totalSimulations": count, "rootActionSummaries": [
                                 {"fingerprint": "synthetic:" + str(i),
                                  "edgeVisits": count // (i + 1),
                                  "visitShare": 1 / (i + 1), "selectionQValid": True,
                                  "selectionQ": .63} for i in (2, 3)],
                             "tree": {"accepted": True, "truncated": False, "rootId": 1,
                                      "retainedNodeCount": count, "retainedEdgeCount": len(edges),
                                      "nodes": nodes, "edges": edges}}]}}}


if __name__ == "__main__":
    count = int(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(generate(count), separators=(",", ":")))
