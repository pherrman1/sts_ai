import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_round2 as r2


def root(index, executed=True, keys=('a', 'b'), visits=(3, 1)):
    total = sum(visits)
    return {'schema': 'ooc-root-trace-v1', 'seed': 7, 'decisionIndex': index, 'searchSeed': 1,
            'snapshot': {'schema': 'screen-leaf-full-state-v1'}, 'record': {'screen_state': 5},
            'singletonBypass': False, 'executed': executed, 'reason': '', 'selectedId': 0,
            'selectedKey': keys[0], 'rootActions': [{'id': i, 'key': k, 'prior': .5, 'visits': v, 'q': .1,
                'visitShare': v/total} for i, (k, v) in enumerate(zip(keys, visits))]}


def action(row):
    return {'seed': 7, 'decisionIndex': row['decisionIndex'], 'selectedId': row['selectedId'],
            'selectedKey': row['selectedKey'], 'executed': row['executed']}


class Round2Tests(unittest.TestCase):
    def check(self, rows, actions=None):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'roots.jsonl', Path(d)/'actions.jsonl'
            a.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            b.write_text(''.join(json.dumps(x)+'\n' for x in (actions or [action(r) for r in rows])))
            return r2.root_trace(a, b, 7)

    def test_assignments_are_disjoint_balanced_and_after_canaries(self):
        sources = r2.assignments(45, (34, 10, 20))
        seeds = [s['seed'] for s in sources]
        self.assertEqual(len(set(seeds)), 2880)
        self.assertEqual(seeds, list(range(r2.FIRST, r2.FIRST+2880)))
        self.assertTrue(max(max(c) for c in r2.CANARIES.values()) < r2.FIRST)
        for w in range(45):
            mine = [s['split'] for s in sources if s['worker'] == w]
            self.assertEqual([mine.count(x) for x in r2.SPLITS], [34, 10, 20])
        self.assertEqual([s['split'] for s in sources[-900:]], ['confirm']*900)

    def test_valid_trace_counts(self):
        self.assertEqual(self.check([root(0), root(3)]), {'roots': 2, 'searched': 2, 'snapshots': 2, 'records': 2, 'snapshotErrorsByScreen': {}})

    def test_misaligned_or_reordered_trace_refused(self):
        rows = [root(0), root(3)]
        for bad in ([rows[0]], [rows[1], rows[0]]):
            with self.assertRaises(ValueError):
                self.check(bad, [action(r) for r in rows])
        changed = action(rows[1]); changed['selectedKey'] = 'b'
        with self.assertRaises(ValueError):
            self.check(rows, [action(rows[0]), changed])

    def test_match_and_keep_hypothetical_roots_accepted(self):
        # w08 seed 111101200: real 138, hypothetical (140 << 12) ^ bits ..., then real 149.
        rows = [root(138), root((140 << 12) ^ 50), root((146 << 12) ^ 20), root(149)]
        self.assertEqual(self.check(rows)['hypotheticalRoots'], 2)
        # w21 seed 111102173: one card valued twice under the same base index.
        again = [root(119), root((120 << 12) ^ 546), root((120 << 12) ^ 138), root((120 << 12) ^ 546), root(122)]
        self.assertEqual(self.check(again)['hypotheticalRoots'], 3)
        for bad in ([root(138), root((138 << 12) ^ 2)], [root(138), root((140 << 12) ^ 2), root(139)],
                    [root(138), root(138)]):
            with self.assertRaises(ValueError):
                self.check(bad)

    def test_requalify_only_root_trace_order_censoring(self):
        rows = [root(138), root((140 << 12) ^ 50), root(149)]
        good = {'returncode': 65, 'processReturncode': 0, 'contractError': r2.ROOT_TRACE_MISMATCH,
                'states': 3, 'policy': {'a': 1}, 'modelUse': {}}
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'roots.jsonl', Path(d)/'actions.jsonl'
            a.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            b.write_text(''.join(json.dumps(action(r))+'\n' for r in rows))
            self.assertTrue(r2.requalify(good, a, b, 7))
            for change in ({'processReturncode': 124}, {'contractError': 'other'}, {'returncode': 0}):
                self.assertFalse(r2.requalify({**good, **change}, a, b, 7))
            self.assertFalse(r2.requalify({k: v for k, v in good.items() if k != 'modelUse'}, a, b, 7))

    def test_bad_visits_duplicate_keys_and_leaks_refused(self):
        bad = root(0); bad['rootActions'][0]['visitShare'] = .9
        dup = root(0, keys=('a', 'a'))
        leak = root(0); leak['record']['rng'] = 1
        silent = root(0); del silent['snapshot']
        for row in (bad, dup, leak, silent):
            with self.assertRaises(ValueError):
                self.check([row])

    def test_snapshot_failure_is_counted_not_fatal(self):
        row = root(0); row['snapshot'] = None; row['snapshotError'] = 'unsupported continuation'
        row['screen'] = 2
        counts = self.check([row])
        self.assertEqual((counts['snapshots'], counts['snapshotErrorsByScreen']), (0, {'2': 1}))


if __name__ == '__main__':
    unittest.main()
