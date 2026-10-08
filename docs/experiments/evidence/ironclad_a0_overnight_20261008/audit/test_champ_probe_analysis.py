#!/usr/bin/env python3
"""Adversarial synthetic custody/health/allocation checks; no simulator calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import analyze_champ_probe as analyze
import run_champ_probe as run


SPEC = {'future_domain': 'champ-d13-public-pair-v1-environment',
        'baseline_fingerprint': 'synthetic-end', 'alternative_fingerprint': 'synthetic-shrug'}


def pair(k=2):
    future = str(int(hashlib.sha256(f"{SPEC['future_domain']}:{run.ROW_SHA}:{k}".encode()).hexdigest()[:16], 16))
    rows = []
    for arm, fingerprint in [('END', 'synthetic-end'), ('SHRUG', 'synthetic-shrug')]:
        rows.append(dict(kind='branch', k=k, arm=arm, valid=True, combat_won=False,
            environment_seed=future, forced_fingerprint=fingerprint, action_fingerprints=[fingerprint, 'next'],
            decisions=2, continuation_simulations=10000, search_endpoints=dict(victory=2000, death=8000,
                turn_limit=0, engine_stop=0, nonterminal=0), terminal_outcome=2, terminal_hp=0,
            terminal_turn=7, terminal_potion_count=0, endpoint_sha256='0'*64, cpu_seconds=1.0, wall_seconds=1.1))
    return rows


class ProbeTest(unittest.TestCase):
    def test_valid_conditional_pair_and_fixed_allocation(self):
        analyze.validate_branches(pair(), 2, SPEC)
        for stage, k in [('evaluation', 1), ('evaluation', 64), ('canary', 2), ('check', 0)]:
            with self.assertRaises(ValueError):
                run.prefix(stage, k)

    def test_absent_or_duplicated_contrast_rejected(self):
        for rows in [pair()[:1], [pair()[0], pair()[0]]]:
            with self.assertRaises(ValueError):
                analyze.validate_branches(rows, 2, SPEC)

    def test_health_stop_cannot_be_a_loss(self):
        rows = pair()
        rows[1]['search_endpoints']['death'] -= 1
        rows[1]['search_endpoints']['engine_stop'] = 1
        with self.assertRaisesRegex(ValueError, 'health'):
            analyze.validate_branches(rows, 2, SPEC)

    def test_uncoupled_future_and_budget_drift_rejected(self):
        rows = pair(); rows[0]['environment_seed'] = '123'
        with self.assertRaisesRegex(ValueError, 'coupling'):
            analyze.validate_branches(rows, 2, SPEC)
        rows = pair(); rows[1]['continuation_simulations'] = 5000
        with self.assertRaisesRegex(ValueError, 'budget'):
            analyze.validate_branches(rows, 2, SPEC)

    def test_failed_receipt_without_output_is_accounted_for(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(run, 'RAW', Path(temp)):
            Path(temp, 'evaluation-02.receipt.json').write_text(json.dumps({'status': 'timeout', 'exit_code': 124}))
            result = analyze.analyze({'source_sha': 'synthetic', 'binary_sha256': 'synthetic'}, 'f', 't', 'evaluation')
            self.assertEqual(result['status'], 'INVALID_STOP_LANE')
            self.assertEqual(result['allocated_k'], list(range(2, 64)))
            self.assertTrue(any(x.get('k') == 2 and 'incomplete' in x['error'] for x in result['failures']))
            self.assertNotIn('wins', result)


if __name__ == '__main__':
    unittest.main()
