"""tools/heart1/ppo_decision_sources.py on a synthetic trajectory part (#1055)."""
import gzip
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "heart1"))
import ppo_decision_sources as pds  # noqa: E402

NAMES = pds.relic_names()
JUZU, STRAWBERRY, CURSED_KEY = (NAMES.index(n) for n in ("JUZU_BRACELET", "STRAWBERRY", "CURSED_KEY"))
BLOOD_POTION = pds.potion_names().index("BLOOD_POTION")


def decision(seed, screen, act, chosen, cards=(), relics=(), potions=(), fixed=(), paths=(), held=()):
    n = len(cards) + len(relics) + len(potions) + len(fixed) + len(paths)
    return {"type": "decision", "seed": seed, "idx": 0, "act": act, "floor": 1, "screen": screen,
            "source": "heart1_ppo" if n > 1 else "heart1_ppo_single", "n": n, "chosen": chosen,
            "record": {"cards_offered.cards": list(cards), "relics_offered": list(relics),
                       "potions_offered": list(potions), "paths_offered": list(paths),
                       "fixed_actions": [{"action": a, **({"potion": BLOOD_POTION} if a == pds.FA_DISCARD else {})}
                                         for a in fixed], "obs.relics.relics": list(held)}}


class DecisionSourcesTest(unittest.TestCase):
    def test_counts(self):
        rows = [
            # rewards: card, Strawberry, Juzu, discard, leave -> leave leaves both relics
            decision("1", 2, 1, 4, cards=[5], relics=[STRAWBERRY, JUZU], fixed=[pds.FA_DISCARD, pds.FA_SKIP]),
            # rewards: Sapphire next to a relic, key taken (fixed index 0)
            decision("1", 2, 3, 1, relics=[STRAWBERRY], fixed=[pds.FA_TAKE_KEY, pds.FA_SKIP]),
            # chest with Cursed Key: opened
            decision("1", 6, 2, 0, fixed=[pds.FA_OPEN_CHEST, pds.FA_SKIP], held=[CURSED_KEY]),
            # first act-3 rest site with Recall: rest; the second one (recall) is not counted
            decision("1", 7, 3, 0, fixed=[4, pds.FA_RECALL]),
            decision("1", 7, 3, 1, fixed=[4, pds.FA_RECALL]),
            # rewards: a full belt, Blood Potion discarded for the offered potion (fixed index 0)
            decision("1", 2, 2, 1, potions=[9], fixed=[pds.FA_DISCARD, pds.FA_SKIP]),
            # single-choice map
            decision("1", 5, 1, 0, paths=[3]),
            # boss relic skipped
            decision("1", 3, 1, 3, relics=[1, 2, 3], fixed=[pds.FA_SKIP]),
            {"type": "fallback", "seed": "1", "screen": 1, "event": 7, "reason": "unmapped_event"},
            {"type": "game", "seed": "1", "auto_gold": 3, "outcome": {}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "traj-0000-p0.jsonl.gz")
            with gzip.open(path, "wt") as f:
                f.write("".join(json.dumps(r) + "\n" for r in rows))
            rep = pds.tally([tmp], NAMES)
        self.assertEqual(rep["games"], 1)
        self.assertEqual(rep["sources"], {"heart1_ppo": 7, "heart1_ppo_single": 1})
        self.assertEqual(rep["fallbacks"], {"unmapped_event": 1})
        self.assertEqual(rep["auto_gold"], 3)
        self.assertEqual(rep["tokens"]["discard_potion"], {"offered": 2, "chosen": 1})
        self.assertEqual(rep["discarded_potions"], {"BLOOD_POTION": 1})
        self.assertEqual(rep["tokens"]["take_key"], {"offered": 1, "chosen": 1})
        self.assertEqual(rep["tokens"]["recall"], {"offered": 2, "chosen": 1})
        self.assertEqual(rep["relics_left"], {"rule_would_take": 1, "reviewed_exception": 1})
        self.assertEqual(rep["relics_left_rule_would_take_by_relic"], {"STRAWBERRY": 1})
        self.assertEqual(rep["sapphire"], {"act3:taken": 1})
        self.assertEqual(rep["treasure"], {"cursed_key:open": 1})
        self.assertEqual(rep["boss_relic"], {"skip": 1})
        self.assertEqual(rep["ruby_first_act3_rest"], {"other": 1})
        self.assertEqual(rep["screens"]["map"], {"single": 1})


if __name__ == "__main__":
    unittest.main()
