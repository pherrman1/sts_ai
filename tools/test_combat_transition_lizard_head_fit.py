import unittest
import numpy as np

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_head_fit as fit


class LizardHeadFitTests(unittest.TestCase):
    def row(self, pre_data, post_data):
        lizard = composed.base._RELIC_IDS['LIZARD_TAIL']
        return {'transition': {
            'pre': {'relics': [{'id': lizard, 'data': pre_data}]},
            'post': {'relics': [{'id': lizard, 'data': post_data}]},
        }}

    def test_consumed_and_retained_labels(self):
        self.assertEqual(fit.labels_for_row(self.row(1, 0)), 1)
        self.assertEqual(fit.labels_for_row(self.row(1, 1)), 0)

    def test_spent_lizard_is_not_an_active_head_training_row(self):
        with self.assertRaisesRegex(ValueError, 'invalid RAW state'):
            fit.labels_for_row(self.row(0, 0))

    def test_proper_score_classification_requires_ci_excludes_zero(self):
        self.assertEqual(fit.classify([-0.2, -0.01], 0), 'LIZARD_HEAD_QUALIFIED_OFFLINE')
        self.assertEqual(fit.classify([0.01, 0.2], 0), 'LIZARD_HEAD_REJECTED_PROPER_SCORE')
        self.assertEqual(fit.classify([-0.1, 0.1], 0), 'LIZARD_HEAD_INCONCLUSIVE')
        self.assertEqual(fit.classify([-0.2, -0.01], 1), 'LIZARD_HEAD_REJECTED_HARD_VALIDITY')
        self.assertEqual(fit.classify(None, 0), 'LIZARD_HEAD_INCONCLUSIVE')

    def test_ancestral_test_cohort_includes_supported_test_losses(self):
        split = np.asarray(['train', 'validation', 'test', 'test', 'test'])
        support = np.asarray([1, 1, 1, 1, 0], dtype=bool)
        wins = np.asarray([1, 1, 1, 0, 1], dtype=bool)
        train, validation, test_wins, test_ancestral = fit.select_rows(split, support, wins)
        np.testing.assert_array_equal(train, [0])
        np.testing.assert_array_equal(validation, [1])
        np.testing.assert_array_equal(test_wins, [2])
        np.testing.assert_array_equal(test_ancestral, [2, 3])


if __name__ == '__main__':
    unittest.main()
