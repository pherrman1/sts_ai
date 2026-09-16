import unittest

import numpy as np

from tools import combat_transition_shared_hp_downstream as replay


class SharedHpDownstreamReplayTest(unittest.TestCase):
    def test_row_mass_preserves_trace_marginalization(self):
        values = np.log(np.asarray([.25, .75, .5]))
        owners = np.asarray([0, 0, 1])
        weights = np.asarray([.4, .6, 1.])
        np.testing.assert_allclose(replay.row_mass(values, owners, weights, 2), [.55, .5])

    def test_replay_driver_uses_recorded_baseline(self):
        self.assertEqual(replay.BASELINE_SHA, '27c8f7a0918b6ac684a3913436e30c54c0f5ff6c')
        self.assertEqual(replay.NLL_TOLERANCE, 1e-6)


if __name__ == '__main__':
    unittest.main()
