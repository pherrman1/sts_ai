#!/usr/bin/env python3
"""Arithmetic and provenance fixtures only; no game seeds or numerical labels."""
import unittest
from verify_gen2 import expected_profile_seeds, mt19937_64_first, verify_profile_root


class ProfileSeedTest(unittest.TestCase):
    def test_std_mt19937_64_known_vectors(self):
        # Independently produced by mt19937_64_vectors.cpp using system libstdc++.
        expected = {0: 2947667278772165694, 1: 2469588189546311528,
                    5489: 14514284786278117030, (1 << 64)-1: 478026398904862820}
        for seed, output in expected.items():
            self.assertEqual(mt19937_64_first(seed), output)

    def test_declared_future_domain_and_source_are_exact(self):
        options = [{'sourceSeed': '610084000', 'decisionIdx': '71'}]
        allowed = expected_profile_seeds(610084000, options, 4)
        self.assertEqual(allowed, {610084000, 3657778262599658452, 2269033397931363382,
                                  17566836546589453598, 247032420270830382})
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            expected_profile_seeds(610084001, options, 4)

    def test_valid_source_and_future_profiles_pass(self):
        for seed in (610084000, 3657778262599658452):
            verify_profile_root(dict(seed=str(seed), adaptive=False, error='',
                                     configured_simulations=10000, completed_simulations=4000),
                                {610084000, 3657778262599658452})

    def test_unexpected_seed_rejected(self):
        root = dict(seed='123', adaptive=False, error='', configured_simulations=10000, completed_simulations=4000)
        with self.assertRaisesRegex(ValueError, 'unexpected root'):
            verify_profile_root(root, {610084000})

    def test_adaptive_error_and_negative_budgets_still_rejected(self):
        baseline = dict(seed='610084000', adaptive=False, error='', configured_simulations=10000, completed_simulations=4000)
        for field, value in [('adaptive', True), ('error', 'engine_error'),
                             ('configured_simulations', -1), ('completed_simulations', -1)]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    verify_profile_root(dict(baseline, **{field: value}), {610084000})


if __name__ == '__main__':
    unittest.main()
