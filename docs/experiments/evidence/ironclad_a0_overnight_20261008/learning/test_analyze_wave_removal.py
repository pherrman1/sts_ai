#!/usr/bin/env python3
"""Run prior strict fixtures plus removal banner gates against the new immutable analyzer."""
import importlib.util
import json
from pathlib import Path
import unittest
import test_analyze_wave as base

SCRIPT = Path(__file__).resolve().parents[1] / 'analyze_wave_removal.py'
spec = importlib.util.spec_from_file_location('analyze_wave_removal', SCRIPT)
removal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(removal)
# Inherited fixtures resolve their module's analyzer global. Only this test
# process changes it; neither the active analyzer nor the original tests change.
base.aw = removal
BANNER = '[native OOC fallback REMOVE ranks low acquisition weight first; Bonfire unchanged]'


class RemovalEvidenceContractTest(base.EvidenceContractTest):
    def declare_removal(self, value):
        self.m['profiles']['arms']['Fprod']['STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT'] = value
        self.save_manifest()
        for arm in ('Fprod', 'Candidate'):
            path = self.receipt_path(arm)
            receipt = json.loads(path.read_text())
            receipt['manifest_sha256'] = removal.digest(self.manifest)
            if arm == 'Fprod':
                receipt['environment']['STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT'] = value
            path.write_text(json.dumps(receipt))

    def append_banner(self):
        path = self.run/'Fprod_shard0.log'
        with path.open('a') as f:
            f.write(BANNER + '\n')
        self.rehash_output('log')

    def test_removal_enabled_banner_passes(self):
        self.declare_removal('1')
        self.append_banner()
        self.check()

    def test_removal_enabled_missing_banner_rejected(self):
        self.declare_removal('1')
        with self.assertRaisesRegex(ValueError, 'fallback REMOVE acquisition-weight banner'):
            self.check()

    def test_removal_disabled_unexpected_banner_rejected(self):
        self.declare_removal('0')
        self.append_banner()
        with self.assertRaisesRegex(ValueError, 'fallback REMOVE acquisition-weight banner'):
            self.check()

    def test_removal_unset_unexpected_banner_rejected(self):
        self.append_banner()
        with self.assertRaisesRegex(ValueError, 'fallback REMOVE acquisition-weight banner'):
            self.check()

    def test_removal_explicit_off_without_banner_passes(self):
        self.declare_removal('0')
        self.check()

    def test_existing_fullhp_banner_gate_preserved(self):
        path = self.run/'Fprod_shard0.log'
        with path.open('a') as f:
            f.write('[native OOC full-HP REST excluded when Smith is legal and Dream Catcher is absent]\n')
        self.rehash_output('log')
        with self.assertRaisesRegex(ValueError, 'full-health REST filter banner'):
            self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
