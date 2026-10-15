import unittest

import numpy as np

try:
    from tools.combat_transition_attention_hpo import (
        BASELINE_CANDIDATE, DEFAULT_CANDIDATES, selection_score, validate_candidates,
        validate_split_arrays,
    )
except ModuleNotFoundError:
    from combat_transition_attention_hpo import (
        BASELINE_CANDIDATE, DEFAULT_CANDIDATES, selection_score, validate_candidates,
        validate_split_arrays,
    )


class AttentionHpoTest(unittest.TestCase):
    def test_default_candidates_are_valid_and_unique(self):
        validate_candidates(DEFAULT_CANDIDATES)
        self.assertEqual(len(DEFAULT_CANDIDATES), 8)
        self.assertEqual(DEFAULT_CANDIDATES[0]["name"], "baseline")

    def test_invalid_attention_shape_fails_closed(self):
        candidate = dict(DEFAULT_CANDIDATES[1], name="bad", width=65)
        with self.assertRaisesRegex(ValueError, "divisible"):
            validate_candidates([BASELINE_CANDIDATE, candidate])

    def test_mutated_or_missing_baseline_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "exact frozen baseline"):
            validate_candidates([dict(BASELINE_CANDIDATE, heads=2)])
        with self.assertRaisesRegex(ValueError, "exact frozen baseline"):
            validate_candidates([DEFAULT_CANDIDATES[1]])

    def test_selection_score_matches_frozen_composite(self):
        metrics = {
            "survival": {"brier": 0.02},
            "winningHp": {"mae": 0.07},
            "jointAliveHp": {"mae": 0.08},
        }
        self.assertAlmostEqual(selection_score(metrics), 0.17)

    def test_split_arrays_require_exact_rows_and_sources(self):
        arrays = {"sourceSeed": np.asarray([10, 11, 12]),
                  "split_id": np.asarray([0, 1, 2])}
        split = {"members": {"train": [10], "validation": [11], "test": [12]}}
        prepared = {"counts": {"0": 1, "1": 1, "2": 1}}
        validate_split_arrays(arrays, split, prepared)
        with self.assertRaisesRegex(ValueError, "validation sources"):
            validate_split_arrays({**arrays, "sourceSeed": np.asarray([10, 99, 12])},
                                  split, prepared)
        with self.assertRaisesRegex(ValueError, "unknown split"):
            validate_split_arrays({"sourceSeed": np.asarray([10, 11, 12, 13]),
                                   "split_id": np.asarray([0, 1, 2, 3])},
                                  split, prepared)


if __name__ == "__main__":
    unittest.main()
