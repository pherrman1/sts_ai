import unittest

import numpy as np

try:
    from tools.combat_transition_model_experiment import (
        _flat_names, _flatten, persistent_change_flags, split_for_seed,
    )
except ModuleNotFoundError:
    from combat_transition_model_experiment import (
        _flat_names, _flatten, persistent_change_flags, split_for_seed,
    )


class TestCombatTransitionModelExperiment(unittest.TestCase):
    def test_split_is_stable_and_disjoint(self):
        assignments = [split_for_seed(seed) for seed in range(4100000, 4101000)]
        self.assertEqual(assignments, [split_for_seed(seed) for seed in range(4100000, 4101000)])
        self.assertEqual(set(assignments), {"train", "validation", "test"})

    def test_flat_schema_is_unique_and_relic_zero_is_not_lost(self):
        names = _flat_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 2846)
        globals_value = np.zeros(14, dtype=np.float32)
        cards = np.zeros((128, 4), dtype=np.int16)
        relics = np.zeros((64, 3), dtype=np.int16)
        potions = np.zeros((5, 2), dtype=np.int16)
        card_mask = np.zeros(128, dtype=bool)
        relic_mask = np.zeros(64, dtype=bool)
        relic_mask[0] = True  # AKABEKO is RelicId 0, not padding.
        flat = _flatten(globals_value, cards, relics, potions, card_mask, relic_mask)
        self.assertEqual(flat[names.index("relic_present.0")], 1.0)
        self.assertEqual(flat[names.index("relic_present.1")], 0.0)

    def test_persistent_change_flags_separate_misc_from_structure(self):
        pre = {
            "curHp": 40, "maxHp": 80, "gold": 99, "potionCount": 0,
            "potions": [0, 0, 0, 0, 0], "smokeBombUsed": False,
            "stolenGold": 0, "relics": [{"id": 0, "data": 1}],
            "deck": [{"id": 10, "misc": 0, "upgraded": False, "bottleBinding": -1}],
            "cardTypeCounts": [1, 0, 0, 0], "bottleIdxs": [-1, -1, -1],
            "upgradeableCount": 1, "transformableCount": 1,
            "relicBits": [0, 0, 0], "potionCapacity": 3,
            "combatRng": [],
        }
        post = {**pre, "relics": [{"id": 0, "data": 2}],
                "deck": [{"id": 10, "misc": 1, "upgraded": False, "bottleBinding": -1}]}
        flags, relics, cards = persistent_change_flags(pre, post)
        self.assertTrue(flags["relic_data_changed"])
        self.assertTrue(flags["deck_misc_changed"])
        self.assertFalse(flags["card_upgrade_or_deck_structure_changed"])
        self.assertEqual(relics[0], 1)
        self.assertEqual(cards[10], 1)


if __name__ == "__main__":
    unittest.main()
