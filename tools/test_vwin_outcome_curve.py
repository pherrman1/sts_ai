import unittest

import numpy as np

from tools.vwin_outcome_curve import FRACTIONS, curve_order, decide, slope_rows, slope_weights


def _ci(mean, lo, hi):
    return {"pooled": {"mean": mean, "ci95": [lo, hi]}}


class OutcomeCurveTest(unittest.TestCase):
    def test_slope_weights_recover_log2_slope(self):
        x = np.log2(FRACTIONS)
        self.assertAlmostEqual(float(slope_weights() @ (0.3 + 0.02 * x)), 0.02)
        self.assertAlmostEqual(float(slope_weights().sum()), 0.0)

    def test_slope_rows_align_and_fit(self):
        rows = {f: [dict(seed=1, type="CARD_REWARD", gain=0.01 * np.log2(f)),
                    dict(seed=2, type="MAP", gain=0.0)] for f in FRACTIONS}
        out = slope_rows(rows)
        self.assertAlmostEqual(out[0]["slope"], 0.01)
        self.assertAlmostEqual(out[1]["slope"], 0.0)
        rows[0.5] = rows[0.5][::-1]
        with self.assertRaises(ValueError):
            slope_rows(rows)

    def test_curve_order_is_nested_and_deterministic(self):
        order = curve_order([5, 3, 9, 1])
        self.assertEqual(order, curve_order([1, 9, 3, 5]))
        self.assertEqual(sorted(order), [1, 3, 5, 9])

    def test_decision_rule(self):
        falls = {0.125: 0.3, 1.0: 0.2}
        rises = {0.125: 0.2, 1.0: 0.3}
        self.assertEqual(decide({"a": _ci(0.01, 0.002, 0.02), "b": _ci(0.0, -0.01, 0.01)}, falls), "GO")
        self.assertEqual(decide({"a": _ci(0.01, 0.002, 0.02), "b": _ci(0.0, -0.01, 0.01)}, rises), "INCONCLUSIVE")
        self.assertEqual(decide({"a": _ci(-0.002, -0.01, 0.004), "b": _ci(0.0, -0.004, 0.003)}, falls), "STOP")
        self.assertEqual(decide({"a": _ci(0.004, -0.004, 0.012), "b": _ci(0.0, -0.004, 0.003)}, falls),
                         "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
