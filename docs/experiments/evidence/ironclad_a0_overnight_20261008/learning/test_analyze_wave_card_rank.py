#!/usr/bin/env python3
"""Synthetic contract fixtures for the new analyzer; never executes game seeds."""
import importlib.util
import json
from pathlib import Path
import unittest
import test_analyze_wave_removal as prior

SCRIPT = Path(__file__).resolve().parents[1] / 'analyze_wave_card_rank.py'
spec = importlib.util.spec_from_file_location('analyze_wave_card_rank', SCRIPT)
card_rank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(card_rank)
# Route inherited fixture helpers to the new analyzer within this test process.
# Original test and active analyzer files remain untouched.
prior.base.aw = card_rank
prior.removal = card_rank
BANNER = '[native OOC card win ranking ON; public8 floor take/skip preserved]'


class CardRankEvidenceContractTest(prior.RemovalEvidenceContractTest):
    def declare_card_rank(self, value, trace=False):
        env = self.m['profiles']['arms']['Fprod']
        env['STS_OOC_CARD_WIN_RANK'] = value
        if trace:
            env['STS_OOC_CARD_WIN_RANK_TRACE'] = '1'
        self.save_manifest()
        for arm in ('Fprod', 'Candidate'):
            path = self.receipt_path(arm)
            receipt = json.loads(path.read_text())
            receipt['manifest_sha256'] = card_rank.digest(self.manifest)
            if arm == 'Fprod':
                receipt['environment']['STS_OOC_CARD_WIN_RANK'] = value
                if trace:
                    receipt['environment']['STS_OOC_CARD_WIN_RANK_TRACE'] = '1'
            path.write_text(json.dumps(receipt))

    def append_card_banner(self):
        with (self.run/'Fprod_shard0.log').open('a') as f:
            f.write(BANNER + '\n')
        self.rehash_output('log')

    def test_card_rank_enabled_banner_passes(self):
        self.declare_card_rank('1')
        self.append_card_banner()
        self.check()

    def test_card_rank_enabled_missing_banner_rejected(self):
        self.declare_card_rank('1')
        with self.assertRaisesRegex(ValueError, 'card win ranking banner'):
            self.check()

    def test_card_rank_disabled_unexpected_banner_rejected(self):
        self.declare_card_rank('0')
        self.append_card_banner()
        with self.assertRaisesRegex(ValueError, 'card win ranking banner'):
            self.check()

    def test_card_rank_unset_unexpected_banner_rejected(self):
        self.append_card_banner()
        with self.assertRaisesRegex(ValueError, 'card win ranking banner'):
            self.check()

    def test_card_rank_explicit_off_without_banner_passes(self):
        self.declare_card_rank('0')
        self.check()

    def test_card_rank_trace_preserves_policy_banner_requirement(self):
        self.declare_card_rank('1', trace=True)
        with self.assertRaisesRegex(ValueError, 'card win ranking banner'):
            self.check()
        self.append_card_banner()
        self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
