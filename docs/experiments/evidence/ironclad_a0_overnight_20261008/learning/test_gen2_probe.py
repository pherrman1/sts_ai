#!/usr/bin/env python3
"""Focused split and coupling tests; synthetic rows only, no game commands."""
import csv
import hashlib
from pathlib import Path
import tempfile
import unittest
import analyze_gen2_probe as probe


class ProbeTest(unittest.TestCase):
    def test_ties_preserve_actual_source_action(self):
        self.assertEqual(probe.choose({'a': .5, 'b': .5}, 'b'), 'b')
        self.assertEqual(probe.choose({'z': .1, 'b': .5, 'a': .5}, 'z'), 'a')

    def test_nonfinite_selection_is_not_ranked(self):
        with self.assertRaises(ValueError):
            probe.choose({'a': float('nan')}, 'a')

    def test_stage_filter_ignores_opposite_outcomes(self):
        with tempfile.TemporaryDirectory(dir=probe.E, prefix='synthetic-gen2-') as temp:
            path = Path(temp) / 'labels.csv'
            with path.open('w') as f:
                f.write('k,finalWon\n0,1\n1,0\n2,DO_NOT_INTERPRET\n3,DO_NOT_INTERPRET\n')
            self.assertEqual([r['finalWon'] for r in probe.read_rows(path, [0, 1])], ['1', '0'])

    def test_coupling_and_missing_branch_fail_closed(self):
        state = (610084000, 7, 'CARD_REWARD')
        options = {state: {'baseline': {'optionIdx': '0', 'chosen': '1'}}}
        with tempfile.TemporaryDirectory(dir=probe.E, prefix='synthetic-gen2-') as temp:
            path = Path(temp) / 'labels.csv'
            rows = []
            for k in (0, 1):
                rows.append(dict(sourceSeed=str(state[0]), decisionIdx='7', type=state[2],
                                 optionKey='baseline', optionIdx='0', chosen='1', k=str(k),
                                 valid='1', error='', finalWon='1',
                                 futureSeed=str(int(hashlib.sha256(f'ooc-cf-pilot-v2-future:{state[0]}:7:{k}'.encode()).hexdigest()[:16], 16))))
            def write(data):
                with path.open('w', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(data)
            write(rows)
            got, _ = probe.stage_tables({'labels.csv': [path]}, options, [0, 1], False)
            self.assertEqual(len(got), 2)
            rows[1]['futureSeed'] = '123'
            write(rows)
            with self.assertRaisesRegex(ValueError, 'coupling'):
                probe.stage_tables({'labels.csv': [path]}, options, [0, 1], False)
            write(rows[:1])
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                probe.stage_tables({'labels.csv': [path]}, options, [0, 1], False)


if __name__ == '__main__':
    unittest.main()
