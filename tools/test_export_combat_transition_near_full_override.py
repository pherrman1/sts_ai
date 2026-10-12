"""The near-full export accepts a FAIL exposure report only through a bound ctm_gate_override_v1."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent))
from tools import export_combat_transition_near_full as export  # noqa: E402


def entry(gate, diagnostic=False, zero=0):
    return dict(rows=3, gate=gate, diagnosticOnly=diagnostic, zeroExactMassRows=zero)


def report(classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL'):
    return dict(classification=classification, finalSupport=True, components=dict(
        hp=dict(all=entry(True), recursiveBrew=entry(False)),
        writhing=dict(transmutationPlus=entry(False)),
        relic=dict(brewGeneratedEscape=entry(False, diagnostic=True))))


class TestExposureOverride(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.gate = report()
        self.qualification = self.root / 'exposure.json'
        self.qualification.write_text(json.dumps(self.gate))

    def tearDown(self):
        self.directory.cleanup()

    def override(self, **changes):
        body = dict(schema='ctm_gate_override_v1', stage='final-support-exposure',
                    exposureSha256=hashlib.sha256(self.qualification.read_bytes()).hexdigest(),
                    waivedEntries=['hp.recursiveBrew', 'writhing.transmutationPlus'],
                    approval='Philipp, 2026-10-12', reason='tiny cohorts, CI includes 0',
                    evidence=dict(rows={'hp.recursiveBrew': 10}))
        body.update(changes)
        path = self.root / 'override.json'
        path.write_text(json.dumps(body))
        return path

    def test_failing_entries_skip_diagnostics(self):
        self.assertEqual(export.failing_entries(self.gate), ['hp.recursiveBrew', 'writhing.transmutationPlus'])

    def test_accepts_exact_override(self):
        path = self.override()
        sha, waived = export.exposure_override(self.qualification, self.gate, path)
        self.assertEqual(sha, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(waived, ['hp.recursiveBrew', 'writhing.transmutationPlus'])

    def test_refuses_partial_or_extra_entries(self):
        for waived in (['hp.recursiveBrew'], ['hp.recursiveBrew', 'hp.all', 'writhing.transmutationPlus'], []):
            with self.assertRaisesRegex(ValueError, 'exactly the failing'):
                export.exposure_override(self.qualification, self.gate, self.override(waivedEntries=waived))

    def test_refuses_unbound_report(self):
        with self.assertRaisesRegex(ValueError, 'does not bind'):
            export.exposure_override(self.qualification, self.gate, self.override(exposureSha256='0' * 64))

    def test_refuses_wrong_schema_stage_or_missing_fields(self):
        for changes, message in ((dict(schema='other'), 'ctm_gate_override_v1'),
                                 (dict(stage='downstream'), 'ctm_gate_override_v1'),
                                 (dict(approval=' '), 'approval and reason'),
                                 (dict(evidence={}), 'evidence')):
            with self.assertRaisesRegex(ValueError, message):
                export.exposure_override(self.qualification, self.gate, self.override(**changes))

    def test_refuses_pass_report(self):
        gate = report('FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS')
        with self.assertRaisesRegex(ValueError, 'only to a FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL'):
            export.exposure_override(self.qualification, gate, self.override())

    def test_export_refuses_fail_without_override_and_zero_mass_with_it(self):
        parent = self.root / 'parent'
        parent.mkdir()
        (parent / 'final-support-census-v1.json').write_text('{}')
        validity = self.root / 'validity.json'
        validity.write_text(json.dumps(dict(finalSupport=True)))
        with self.assertRaisesRegex(ValueError, 'not qualified'):
            export.export(parent, self.qualification, validity, self.root / 'out.native')
        self.gate['components']['hp']['all']['zeroExactMassRows'] = 1
        self.qualification.write_text(json.dumps(self.gate))
        with self.assertRaisesRegex(ValueError, 'slice exposure gate failed'):
            export.export(parent, self.qualification, validity, self.root / 'out.native', self.override())


if __name__ == '__main__':
    unittest.main()
