"""Focused exact native parity and fail-closed audit tests (no gameplay)."""
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
try:
    from tools import combat_transition_rng_audit as audit
except ModuleNotFoundError:
    import combat_transition_rng_audit as audit

ROOT = Path(__file__).resolve().parents[1]


def rejection_state():
    # Invert x ^ (x >> 17), then x ^ (x << 23), to make first raw output UINT64_MAX.
    target = audit.MASK
    right = target
    for _ in range(4):
        right = target ^ (right >> 17)
    left = right
    for _ in range(3):
        left = right ^ ((left << 23) & audit.MASK)
    return {'counter': 0, 'seed0': left, 'seed1': 0}


class RngAuditTest(unittest.TestCase):
    def test_native_parity(self):
        source = r'''
#include <cstdint>
#include <iostream>
#include <algorithm>
#include "game/Random.h"
int main() {
    int c, action, argument; std::uint64_t a, b;
    while (std::cin >> c >> a >> b >> action >> argument) {
        sts::Random r; r.counter=c; r.seed0=a; r.seed1=b;
        if (action == 0) r.setCounter(argument);
        if (action == 1) r.nextLong();
        if (action == 2) r.random(argument);
        std::cout << r.counter << " " << r.seed0 << " " << r.seed1 << "\n";
    }
}'''
        states = [{'counter': 3, 'seed0': 7631492155157664035, 'seed1': 10358196924309181947},
                  {'counter': 0, 'seed0': 1, 'seed1': 2}, rejection_state()]
        cases = [(s, action, arg) for s in states for action, arg in ((0, 0), (0, 9), (1, 0), (2, 2), (2, 7), (2, 999))]
        expected = []
        for s, action, arg in cases:
            r = dict(s)
            if action == 0:
                r = audit.set_counter(r, arg)
            elif action == 1:
                audit.next_long(r)
            else:
                r['counter'] += 1
                audit.bounded_long(r, arg + 1)
            expected.append([r[k] for k in ('counter', 'seed0', 'seed1')])
        with tempfile.TemporaryDirectory() as tmp:
            cpp, exe = Path(tmp) / 'parity.cpp', Path(tmp) / 'parity'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++20', '-I', str(ROOT / 'include'), str(cpp), '-o', str(exe)], check=True, capture_output=True)
            payload = ''.join(f"{s['counter']} {s['seed0']} {s['seed1']} {action} {arg}\n" for s, action, arg in cases)
            result = subprocess.run([str(exe)], input=payload, text=True, capture_output=True, check=True)
        self.assertEqual([[int(x) for x in line.split()] for line in result.stdout.splitlines()], expected)

    def test_no_change(self):
        pre = {'counter': 7, 'seed0': 1, 'seed1': 2}
        self.assertEqual(audit.metrics(pre, pre)['exact_equal'], 1)
        self.assertEqual(audit.set_counter(pre, 7), pre)

    def test_counter_success_and_decrease(self):
        pre = {'counter': 0, 'seed0': 1, 'seed1': 2}
        post = dict(pre)
        for _ in range(4):
            audit.next_long(post)
            post['counter'] += 1
        self.assertEqual(audit.set_counter(pre, 4), post)
        self.assertEqual(audit.set_counter(post, 0), post)
        self.assertEqual(audit.metrics(post, pre)['counter_decreased'], 1)

    def test_raw_counter_failure(self):
        pre = {'counter': 0, 'seed0': 1, 'seed1': 2}
        post = dict(pre)
        audit.next_long(post)
        self.assertNotEqual(audit.set_counter(pre, post['counter']), post)
        self.assertEqual(audit.metrics(pre, post)['state_changed_counter_unchanged'], 1)

    def test_small_bound_rejection_failure(self):
        pre = rejection_state()
        self.assertEqual(audit.next_long(dict(pre)), audit.MASK)
        post = dict(pre)
        post['counter'] += 1
        audit.bounded_long(post, 3)  # actual combat random(2) bound
        self.assertNotEqual(audit.set_counter(pre, 1), post)

    def test_deterministic_misc_schedule_handles_rejection(self):
        pre = rejection_state()
        post = audit.replay_misc(pre, 'SPHERE_AND_TWO_SHAPES')
        self.assertEqual(post['counter'], 2)
        self.assertNotEqual(post, audit.set_counter(pre, 2))
        self.assertEqual(audit.replay_misc(pre, 'JAW_WORM'), pre)
        self.assertEqual(audit.replay_misc(pre, 'THREE_LOUSE'), audit.set_counter(pre, 3))
        self.assertEqual(audit.replay_misc(pre, 'GREMLIN_LEADER'), audit.set_counter(pre, 2))

    def test_missing_rng_entry_fails_native_corpus_contract(self):
        try:
            from tools.test_combat_transition_contract import state
            from tools.combat_transition_contract import validate_state
        except ModuleNotFoundError:
            from test_combat_transition_contract import state
            from combat_transition_contract import validate_state
        pre = state()
        pre['combatRng'].pop()
        with self.assertRaisesRegex(ValueError, 'six streams'):
            validate_state(pre, 'pre')
        pre = state()
        del pre['combatRng'][2]['seed1']
        with self.assertRaisesRegex(ValueError, 'keys mismatch'):
            validate_state(pre, 'pre')

    def test_ordering_uses_fight_index(self):
        a = {'fightIdx': 0, 'floor': 1, 'outcome': 1}
        b = {'fightIdx': 1, 'floor': 1, 'outcome': 1}
        self.assertEqual(list(audit.ordered_pairs({1: [b, a]})), [(a, b)])
        for bad in ({1: [b]}, {1: [a, a]}, {1: [a, b | {'floor': 0}]},
                    {1: [a | {'outcome': 2}, b]}):
            with self.assertRaises(ValueError):
                list(audit.ordered_pairs(bad))

    def test_compact_decision_fails_closed_on_inherited_mismatch(self):
        def result(misc_matches=2, potion_equal=2):
            values = {k: {'state_changed': 0, 'exact_equal': potion_equal} for k in audit.STREAMS}
            return {'supportedRows': 2, 'deterministicMiscReplay': {'supported_matches': misc_matches},
                    'sameFloor': {'same_floor_supported_origin': 0},
                    'summaries': {'supported': values, 'encounter:1': values}}
        good = audit.compact_result(result())
        self.assertEqual(good['decision']['classification'], 'RNG_COUNTER_DELTA_EXACT')
        self.assertEqual(good['decision']['minimalLearnedRngTargets'], [])
        self.assertNotIn('encounter:1', good['summaries'])
        for bad in (result(misc_matches=1), result(potion_equal=1)):
            self.assertEqual(audit.compact_result(bad)['decision']['classification'], 'RNG_CONTINUATION_UNRESOLVED')

    def test_supported_same_floor_pair_prevents_exact_classification(self):
        fights = [{'fightIdx': i, 'floor': 1, 'outcome': 1, 'supported': True}
                  for i in range(2)]
        same_floor_supported = sum(a['supported'] and a['floor'] == b['floor']
                                   for a, b in audit.ordered_pairs({1: fights}))
        self.assertEqual(same_floor_supported, 1)
        values = {k: {'state_changed': 0, 'exact_equal': 2} for k in audit.STREAMS}
        result = {'supportedRows': 2, 'deterministicMiscReplay': {'supported_matches': 2},
                  'sameFloor': {'same_floor_supported_origin': same_floor_supported},
                  'summaries': {'supported': values}}
        self.assertEqual(audit.compact_result(result)['decision']['classification'],
                         'RNG_CONTINUATION_UNRESOLVED')
        del result['sameFloor']['same_floor_supported_origin']
        with self.assertRaises(KeyError):
            audit.compact_result(result)

    def test_dropped_final_fight_fails_row_accounting(self):
        rng = {'counter': 0, 'seed0': 1, 'seed1': 2}
        row = {'sourceSeed': 1, 'fightIdx': 0, 'floor': 1, 'act': 1,
               'roomClass': 'NORMAL', 'encounter': 1, 'predictorInput': {},
               'transition': {'combatOutcome': 1, 'pre': {'combatRng': [rng] * 6},
                              'post': {'combatRng': [rng] * 6}}}
        # This remaining run still has its source and contiguous index zero.
        self.assertEqual(list(audit.ordered_pairs({1: [{'fightIdx': 0, 'floor': 1, 'outcome': 1}]})), [])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'corpus.jsonl'
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'csv': {'sha256': audit.FROZEN_SHA, 'path': str(data)},
                                            'producerGitSha': 'a' * 40, 'seedSpec': {'start': 1, 'count': 1}}))
            data.with_suffix('.jsonl.provenance.json').write_text(json.dumps({
                'dataset_path': str(data), 'git_sha': 'a' * 40, 'rows_written': 2,
                'completed_seeds': 1, 'requested_seeds': 1, 'seed_offset': 1,
                'invalid_or_quarantined_seeds': 0, 'generator': 'combattransitiongen',
                'quarantined': {}}))
            integrity = {'rows': 2, 'completedSeeds': 1, 'requestedSeeds': 1,
                         'quarantinedSeeds': 0, 'quarantinedRows': 0}
            with patch.object(audit, 'validate_corpus', return_value=integrity), \
                 patch.object(audit, 'iter_rows', return_value=iter([row])), \
                 patch.object(audit, 'supported_for_surrogate', return_value=True):
                with self.assertRaisesRegex(ValueError, 'audited row count.*1 != 2'):
                    audit.audit(manifest)

    def test_compaction_retains_only_inherited_aggregate_distributions(self):
        def values():
            return {k: {'state_changed': 0, 'exact_equal': 2,
                        'delta_counter_distribution': {'0': 2}} for k in audit.STREAMS}
        result = {'supportedRows': 2, 'deterministicMiscReplay': {'supported_matches': 2},
                  'sameFloor': {'same_floor_supported_origin': 0},
                  'summaries': {'all': values(), 'supported': values(), 'act:1': values()}}
        compact = audit.compact_result(result)
        for name, streams in compact['summaries'].items():
            for stream, counts in streams.items():
                self.assertEqual('delta_counter_distribution' in counts,
                                 name in ('all', 'supported') and stream in ('miscRng', 'potionRng'))
                self.assertEqual(counts['exact_equal'], 2)

    def test_companion_provenance_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'corpus.jsonl'
            provenance = data.with_suffix('.jsonl.provenance.json')
            provenance.write_text('{}')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'csv': {'sha256': audit.FROZEN_SHA, 'path': str(data)},
                                            'producerGitSha': 'a' * 40, 'seedSpec': {'start': 1}}))
            integrity = {'rows': 1, 'completedSeeds': 1, 'requestedSeeds': 1, 'quarantinedSeeds': 0}
            with patch.object(audit, 'validate_corpus', return_value=integrity):
                with self.assertRaisesRegex(ValueError, 'companion provenance'):
                    audit.audit(manifest)

    def test_frozen_hash_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manifest.json'
            path.write_text(json.dumps({'csv': {'sha256': 'wrong'}}))
            with self.assertRaisesRegex(ValueError, 'frozen'):
                audit.audit(path)


if __name__ == '__main__':
    unittest.main()
