import unittest

import numpy as np

from tools.vwin_e1_focal import arm_weights, focal_rows, focal_weights, selection_gain


def _branch(seed, d, typ, bid, chosen, won):
    return dict(sourceSeed=seed, decisionIdx=d, type=typ, branchId=bid, chosen=chosen, won=won)


class FocalTest(unittest.TestCase):
    def setUp(self):
        # Rows: source trajectory, two CARD_REWARD siblings, two MAP siblings.
        self.seed = np.array([1] * 9)
        self.branch = np.array(["source", "source", "a", "a", "b", "m1", "m1", "m2", "m2"], dtype=object)
        self.row = np.array([0, 1, 0, 1, 0, 0, 1, 0, 1])
        self.branches = [_branch(1, 0, "CARD_REWARD", "a", 1, 1), _branch(1, 0, "CARD_REWARD", "b", 0, 0),
                         _branch(1, 3, "MAP", "m1", 0, 1), _branch(1, 3, "MAP", "m2", 1, 0)]

    def test_focal_join_skips_map_predecision_row(self):
        idx = focal_rows(self.seed, self.branch, self.row, self.branches)
        self.assertEqual(idx.tolist(), [2, 4, 6, 8])

    def test_weights(self):
        idx = focal_rows(self.seed, self.branch, self.row, self.branches)
        f1 = focal_weights(self.branches, idx, len(self.row))
        self.assertEqual(np.flatnonzero(f1).tolist(), [2, 4, 6, 8])
        self.assertAlmostEqual(f1[f1 > 0].mean(), 1.0)
        f2 = arm_weights("F2", f1)
        focal = f1 > 0
        self.assertAlmostEqual(f2[focal].sum(), f2[~focal].sum())
        self.assertTrue(np.all(arm_weights("P0", f1) == 1))

    def test_selection_gain_and_ties(self):
        idx = focal_rows(self.seed, self.branch, self.row, self.branches)
        scores = np.zeros(len(self.row))
        scores[[2, 4, 6, 8]] = [0.2, 0.9, 0.5, 0.5]
        rows, skipped = selection_gain(self.branches, idx, scores)
        by_type = {r["type"]: r for r in rows}
        self.assertEqual(by_type["CARD_REWARD"]["gain"], -1.0)   # picks b (lost) over chosen a (won)
        self.assertEqual(by_type["MAP"]["gain"], 0.5)            # tie averages won 1 and 0, chosen lost
        self.assertEqual(by_type["MAP"]["oracle"], 1.0)
        self.assertFalse(by_type["MAP"]["agrees"])
        self.assertEqual(skipped, {})


if __name__ == "__main__":
    unittest.main()
