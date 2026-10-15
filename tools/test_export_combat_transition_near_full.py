"""§443: the final-support exposure override accepted by export_combat_transition_near_full.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import export_combat_transition_near_full as export  # noqa: E402


def entry(gate, mean=0.0, ci=(-0.01, 0.01), diagnostic=False, zero=0):
    return dict(gate=gate, diagnosticOnly=diagnostic, zeroExactMassRows=zero, rows=5,
                exposure=dict(mean=mean, sourceBootstrap95=list(ci)))


def report(**overrides):
    components = dict(hp=dict(entireFinalUnion=entry(True), recursiveBrew=entry(False, .25, (-1e-6, .6))),
                      relic=dict(brewGeneratedEscape=entry(False, 1.0, (.5, 2.0), diagnostic=True)),
                      writhing=dict(transmutationPlus=entry(False, .25, (-.1, .8))))
    for name, value in overrides.items():
        component, cohort = name.split('.')
        components[component][cohort] = value
    return dict(classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_FAIL', finalSupport=True, components=components)


class ExposureOverrideTest(unittest.TestCase):
    def write(self, directory, gate, **override):
        qualification = Path(directory) / 'exposure.json'
        qualification.write_text(json.dumps(gate))
        body = dict(schema='ctm_gate_override_v1', stage='final-support-exposure',
                    qualificationSha256=export.c.base.sha256(qualification),
                    failures=['hp.recursiveBrew', 'writhing.transmutationPlus'],
                    approval='test', reason='tiny cohorts', evidence=dict(rows=13))
        body.update(override)
        path = Path(directory) / 'override.json'
        path.write_text(json.dumps(body))
        return qualification, path

    def test_failed_gated_entries_skip_diagnostic_slices(self):
        self.assertEqual(export.failed_gated_entries(report()), ['hp.recursiveBrew', 'writhing.transmutationPlus'])

    def test_override_binds_exactly_the_failed_slices(self):
        with tempfile.TemporaryDirectory() as d:
            gate = report()
            qualification, path = self.write(d, gate)
            sha, waived = export.exposure_override(qualification, gate, path)
            self.assertEqual(sha, export.c.base.sha256(path))
            self.assertEqual(waived, ['hp.recursiveBrew', 'writhing.transmutationPlus'])
        cases = [
            (dict(failures=['hp.recursiveBrew']), 'exactly the failed'),
            (dict(qualificationSha256='0' * 64), 'does not bind'),
            (dict(stage='downstream'), 'final-support-exposure stage'),
            (dict(approval=' '), 'approval and reason'),
            (dict(evidence={}), 'evidence'),
        ]
        for change, message in cases:
            with tempfile.TemporaryDirectory() as d:
                gate = report()
                qualification, path = self.write(d, gate, **change)
                with self.assertRaisesRegex(ValueError, message):
                    export.exposure_override(qualification, gate, path)

    def test_override_refuses_slices_it_cannot_waive(self):
        for gate, message in ((report(**{'hp.recursiveBrew': entry(False, .25, (.01, .6))}), 'CI includes 0'),
                              (report(**{'hp.recursiveBrew': entry(False, .25, (-.1, .6), zero=1)}), 'CI includes 0'),
                              (dict(report(), classification='FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS'), 'applies only'),
                              (dict(report(), finalSupport=False), 'applies only')):
            with tempfile.TemporaryDirectory() as d:
                qualification, path = self.write(d, gate)
                with self.assertRaisesRegex(ValueError, message):
                    export.exposure_override(qualification, gate, path)


if __name__ == '__main__':
    unittest.main()
