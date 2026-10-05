import unittest

from screen_leaf_metrics_379 import calibration_gate, qualification, transition_report


class GateTests(unittest.TestCase):
    def test_requires_every_act(self):
        with self.assertRaises(ValueError):
            calibration_gate({}, {'1': {}})

    def test_probability_scale_gate(self):
        metadata = [{'act': act, 'screen': 'shop', 'sourceSeed': seed}
                    for act in (1, 2, 3) for seed in (1, 2)]
        tolerances = {str(a): {'absolute_signed_mean': .05, 'mae': .08,
                              'p95_absolute_delta': .15, 'minimum_sources': 2} for a in (1, 2, 3)}
        near = transition_report([.71] * 6, [.70] * 6, metadata, reps=10)
        shifted = transition_report([.9] * 6, [.7] * 6, metadata, reps=10)
        self.assertTrue(calibration_gate(near, tolerances)['pass'])
        self.assertFalse(calibration_gate(shifted, tolerances)['pass'])

    def test_every_replaced_family_must_improve(self):
        rows = [{'screen': 'shop'}, {'screen': 'rest'}]
        self.assertEqual(qualification([1, 0], [.9, .4], [.8, .2], rows,
                         ['shop', 'rest'], {'pass': True})['classification'],
                         'SCREEN_LEAF_OFFLINE_NOT_QUALIFIED')
        self.assertEqual(qualification([1, 0], [.9, .1], [.8, .2], rows,
                         ['shop', 'rest'], {'pass': True})['classification'],
                         'SCREEN_LEAF_OFFLINE_QUALIFIED')
        with self.assertRaises(ValueError):
            qualification([1, 0], [.9, .1, .8], [.8, .2], rows, ['shop'], {'pass': True})


if __name__ == '__main__':
    unittest.main()
