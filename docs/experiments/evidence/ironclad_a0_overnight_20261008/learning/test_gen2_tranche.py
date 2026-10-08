#!/usr/bin/env python3
"""Synthetic stage and source-cluster checks; no source collection or outcome data."""
import tempfile
from pathlib import Path
import unittest
import analyze_gen2_tranche as analysis


class TrancheTest(unittest.TestCase):
    def test_fixed_disjoint_allocation(self):
        self.assertEqual(analysis.SEEDS, list(range(610084100, 610084132)))
        self.assertEqual(analysis.SELECTION_K, [0, 1, 2, 3])
        self.assertEqual(analysis.EVALUATION_K, [4, 5, 6, 7])
        self.assertFalse(set(analysis.SEEDS) & set(range(610083000, 610083512)))

    def test_stage_does_not_interpret_other_block(self):
        with tempfile.TemporaryDirectory(dir=analysis.E, prefix='synthetic-tranche-') as temp:
            path = Path(temp) / 'labels.csv'
            path.write_text('k,finalWon\n0,1\n1,0\n2,1\n3,0\n4,DO_NOT_INTERPRET\n5,DO_NOT_INTERPRET\n6,DO_NOT_INTERPRET\n7,DO_NOT_INTERPRET\n')
            self.assertEqual([r['finalWon'] for r in analysis.read_rows(path, analysis.SELECTION_K)], ['1', '0', '1', '0'])

    def test_equal_source_weight_not_state_weight(self):
        result = analysis.source_cluster_summary({1: [1.0, 1.0], 2: [-1.0]}, [1, 2])
        self.assertEqual(result['equal_source_mean_paired_gain'], 0)
        self.assertEqual(result['per_source_mean_paired_gain'], {'1': 1, '2': -1})

    def test_duplicating_within_source_states_does_not_inflate_precision(self):
        a = analysis.source_cluster_summary({1: [.5, 1.0], 2: [-.5], 3: [0]}, [1, 2, 3])
        b = analysis.source_cluster_summary({1: [.5, 1.0] * 20, 2: [-.5] * 20, 3: [0] * 20}, [1, 2, 3])
        self.assertEqual(a['source_cluster_bootstrap_ci95'], b['source_cluster_bootstrap_ci95'])
        self.assertEqual(a['equal_source_mean_paired_gain'], b['equal_source_mean_paired_gain'])

    def test_valid_no_state_source_retained_as_zero(self):
        result = analysis.source_cluster_summary({1: [1.0]}, [1, 2])
        self.assertEqual(result['equal_source_mean_paired_gain'], .5)
        self.assertEqual(result['observed_source_clusters'], 1)
        self.assertEqual(result['allocated_source_clusters'], 2)
        self.assertEqual(result['per_source_state_count'], {'1': 1, '2': 0})

    def test_empty_coverage_has_zero_gain_and_no_positive_signal(self):
        result = analysis.source_cluster_summary({}, list(range(32)))
        self.assertEqual(result['equal_source_mean_paired_gain'], 0)
        self.assertEqual(result['source_cluster_bootstrap_ci95'], [0, 0])

    def test_tie_and_invalid_gain_fail_closed(self):
        self.assertEqual(analysis.choose({'a': .5, 'z': .5}, 'z'), 'z')
        with self.assertRaises(ValueError):
            analysis.source_cluster_summary({1: [float('nan')]}, [1])


if __name__ == '__main__':
    unittest.main()
