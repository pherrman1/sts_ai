import unittest
from unittest.mock import patch

import numpy as np

from tools import combat_transition_survival_platt as calibration


class CalibrationTests(unittest.TestCase):
    def test_grouping_deterministic_and_order_invariant(self):
        sources = np.repeat(np.arange(20), 3)
        folds = calibration.source_folds(sources)
        np.testing.assert_array_equal(folds, calibration.source_folds(sources[::-1])[::-1])
        self.assertEqual(set(folds), set(range(5)))
        for source in np.unique(sources):
            self.assertEqual(len(np.unique(folds[sources == source])), 1)

    def test_crossfit_excludes_held_sources(self):
        sources = np.repeat(np.arange(20), 2)
        logits = sources.astype(float)
        labels = np.tile([0., 1.], 20)
        assignments = calibration.source_folds(sources)
        calls = []

        def fake_fit(values, targets):
            fold = len(calls)
            self.assertFalse(set(values) & set(logits[assignments == fold]))
            calls.append(values)
            return np.array([2., -1.]), {}

        with patch.object(calibration, 'fit_platt', side_effect=fake_fit):
            output, _, receipts = calibration.cross_fit(logits, labels, sources)
        np.testing.assert_array_equal(output, 2 * logits - 1)
        self.assertEqual(len(receipts), 5)

    def test_known_intercept_and_invalid_inputs(self):
        parameters, _ = calibration.fit_platt(np.zeros(100), np.r_[np.zeros(25), np.ones(75)])
        self.assertAlmostEqual(parameters[1], np.log(3), places=6)
        for logits, labels in [(np.zeros(3), np.zeros(3)), (np.array([0., np.nan]), np.array([0., 1.]))]:
            with self.assertRaises(ValueError):
                calibration.fit_platt(logits, labels)


if __name__ == '__main__':
    unittest.main()
