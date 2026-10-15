import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.combat_transition_remaining_census import trace_census
from tools import combat_transition_gold_audit as gold


class TraceCensusTest(unittest.TestCase):
    def fixture(self, folder):
        official = folder / 'official'
        official.mkdir()
        summaries = [dict(seed=s, reasons={'gold_mutating_encounter': 2}) for s in range(980000, 980064)]
        path = official / 'treatment.csv.mcts.csv.support.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in summaries))
        (official / 'treatment.csv.mcts.csv').write_text('seed,unsupportedCombats,mctsSupportAborts\n' + ''.join(f'{s},2,2\n' for s in range(980000, 980064)))
        return path, summaries

    def test_first_reason_counts_and_missing_states(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.fixture(folder)
            result = trace_census(folder)
            self.assertEqual(result['reasons'], {'gold_mutating_encounter': 128})
            self.assertEqual(result['supportAbortedRoots'], 128)
            self.assertFalse(result['stateReplayAvailable'])

    def test_reject_missing_duplicate_and_bad_counts(self):
        for corruption in ('missing', 'duplicate', 'count', 'negative'):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                path, summaries = self.fixture(folder)
                if corruption == 'missing':
                    summaries.pop()
                elif corruption == 'duplicate':
                    summaries[-1] = summaries[0]
                else:
                    summaries[0]['reasons']['gold_mutating_encounter'] = -1 if corruption == 'negative' else 3
                path.write_text(''.join(json.dumps(r) + '\n' for r in summaries))
                with self.assertRaises(ValueError):
                    trace_census(folder)

    def test_reject_duplicate_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.fixture(folder)
            path = folder / 'official/treatment.csv.mcts.csv'
            path.write_text(path.read_text() + '980000,2,2\n')
            with self.assertRaises(ValueError):
                trace_census(folder)

    def test_gold_gate_audit_restores_original_and_preserves_other_reasons(self):
        from unittest.mock import patch
        with patch.object(gold.c.base, 'supported_reasons', return_value=['gold_mutating_card', 'ritual_dagger']) as original:
            with self.assertRaises(RuntimeError):
                with gold.audit_without_gold_gate():
                    self.assertEqual(gold.c.base.supported_reasons({}, {}), ['ritual_dagger'])
                    raise RuntimeError('audit failed')
            self.assertIs(gold.c.base.supported_reasons, original)

    def test_branch_presence_counts_whole_corpus_and_upgrade(self):
        import numpy as np
        arrays = dict(cards=np.array([[[343, 1]], [[343, 0]], [[343, 1]]]),
                      sourceSeed=np.array([1, 2, 3]), fightIdx=np.array([4, 5, 6]),
                      split_id=np.array([0, 1, 2]), y_win=np.array([1, 1, 0]))
        result = gold.branch_presence(arrays, 343, True)
        self.assertEqual(result['countsBySplit'], dict(train=1, validation=0, test=1))
        self.assertEqual(result['sourceSeeds'], [1, 3])
        self.assertEqual(result['fightIndices'], [4, 6])


if __name__ == '__main__':
    unittest.main()
