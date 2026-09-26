import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('profile', Path(__file__).parents[1] / 'analyze_silver_tree_profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)

class ProfileTest(unittest.TestCase):
    def row(self):
        return dict(schema=1, error='', descent_aborts=0, completed_simulations=4,
                    heuristic_evaluations=4, neural_evaluations=0, configured_simulations=4,
                    nonterminal_rollout_starts=1, rollout_calls=2,
                    endpoints={k: dict(count=4 if k == 'victory' else 0,
                                tree_depth={'1': 2, '3': 2} if k == 'victory' else {},
                                total_depth={'2': 2, '7': 2} if k == 'victory' else {})
                               for k in profile.KINDS})

    def test_exact_summary(self):
        result = profile.summarize([profile.validate(self.row())])
        self.assertEqual(result['ordinary_terminal_share'], 1)
        self.assertEqual(result['depths']['all_total_depth']['p50'], 2)
        self.assertEqual(result['depths']['terminal_total_depth']['p90'], 7)

    def test_invalid_counts_and_abort_rejected(self):
        for key, value in [('completed_simulations', 5), ('error', 'abort'),
                           ('descent_aborts', 1), ('neural_evaluations', 1),
                           ('nonterminal_rollout_starts', 3)]:
            row = self.row()
            row[key] = value
            with self.assertRaises(ValueError):
                profile.validate(row)
        row = self.row()
        row['endpoints']['victory']['tree_depth']['1'] = -1
        with self.assertRaises(ValueError):
            profile.validate(row)

    def test_empty_search_share_unknown(self):
        result = profile.summarize([])
        self.assertIsNone(result['ordinary_terminal_share'])

if __name__ == '__main__':
    unittest.main()
