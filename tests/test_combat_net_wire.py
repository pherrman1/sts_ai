"""Coverage test for tools/combat_net/wire_encoder.py (combat plan stage 0).

1. Every leaf path of the sample wires is listed in SPEC (encoded or ignored with a reason).
2. Changing any encoded leaf changes the encoding (the field reaches the encoder), except inside empty
   placeholder slots, which the encoder drops on purpose (an empty monster slot, an empty limbo slot, no card
   being played).
3. Changing an ignored leaf leaves the encoding unchanged.
4. A path missing from SPEC is an error, not a silent drop.
"""

import copy
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("wire_encoder", os.path.join(ROOT, "tools", "combat_net", "wire_encoder.py"))
we = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(we)

SAMPLE = os.path.join(ROOT, "tests", "data", "combat_net_wire_sample.jsonl")


def load():
    with open(SAMPLE) as f:
        return [json.loads(line)["wire"] for line in f]


def leaves_with_refs(x, p=""):
    """(collapsed path, container, key) for every scalar leaf."""
    if isinstance(x, dict):
        for k, v in x.items():
            q = f"{p}.{k}" if p else k
            if isinstance(v, (dict, list)):
                yield from leaves_with_refs(v, q)
            else:
                yield q, x, k
    elif isinstance(x, list):
        for i, v in enumerate(x):
            if isinstance(v, (dict, list)):
                yield from leaves_with_refs(v, p + "[]")
            else:
                yield p + "[]", x, i


def placeholder(wire, container):
    for m in wire["monsters"]:
        if (container is m or container is m.get("pendingRollInputs") or container is m.get("smallPowers")
                or container is m.get("moveHistory")):
            return int(m["id"]) == 0 and int(m["maxHp"]) == 0
    for c in wire["limbo"]:
        if container is c:
            return int(c["id"]) == 0
    if container is wire["curCardQueueItem"]["card"]:
        return int(container["id"]) == 0
    return False


def bump(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, float):
        return v + 1.5
    return v


class WireCoverage(unittest.TestCase):
    def test_every_path_listed(self):
        for wire in load():
            we.check_paths(wire)

    def test_encoded_leaves_reach_the_encoding(self):
        checked = 0
        for n, wire in enumerate(load()):
            base = we.encode(wire)
            refs = list(leaves_with_refs(wire))
            for i, (path, _, _) in enumerate(refs):
                w2 = copy.deepcopy(wire)
                path2, cont2, key2 = list(leaves_with_refs(w2))[i]
                assert path2 == path
                role = we.classify(path)
                hole = placeholder(w2, cont2)
                cont2[key2] = bump(cont2[key2])
                if hole:
                    continue
                if role.startswith(we.IGNORE):
                    self.assertEqual(we.encode(w2), base, f"ignored {path} changed the encoding (row {n})")
                else:
                    self.assertNotEqual(we.encode(w2), base, f"{path} does not reach the encoding (row {n})")
                    checked += 1
        self.assertGreater(checked, 500)

    def test_unknown_path_is_an_error(self):
        wire = copy.deepcopy(load()[0])
        wire["player"]["newField"] = 3
        with self.assertRaises(KeyError):
            we.encode(wire)

    def test_semantic_parse(self):
        p = we.parse_semantic("sa/t=1/s=1/c=25_10_0_2_2_0_0_0/o=0/p=0_-1/x=1/d=0/k=0/task=0/sel=")
        self.assertEqual(p["t"], [1])
        self.assertEqual(p["c"], [25, 10, 0, 2, 2, 0, 0, 0])
        self.assertEqual(p["p"], [0, -1])
        self.assertEqual(p["sel"], [])


if __name__ == "__main__":
    unittest.main()
