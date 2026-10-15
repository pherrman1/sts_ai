import tempfile
import unittest
from pathlib import Path

try:
    from tools import ctm_capabilities as capabilities, ctm_escape as e
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_capabilities as capabilities
    import ctm_escape as e

ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'


class TestWrithingRitual(unittest.TestCase):
    def test_lifts_only_the_intersection_exclusion(self):
        metadata, tensors = e.read_artifact(STANDARD)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with self.assertRaises(ValueError):
                capabilities.writhing_ritual(STANDARD, d / 'production.native')
            candidate = d / 'candidate.native'
            e.write_artifact(candidate, dict(metadata, researchCandidate={'candidateId': 'x'}), tensors)
            result = capabilities.writhing_ritual(candidate, d / 'out.native')
            lifted, same = e.read_artifact(d / 'out.native')
            self.assertEqual(lifted['capabilities'], {'writhingRitual': {}})
            self.assertEqual(lifted['supportExclusions'], ['smoke_bomb', 'pre_smoke_bomb_used'])
            self.assertEqual(result['artifactSha256'], e.sha256(d / 'out.native'))
            self.assertEqual(result['baseArtifactSha256'], e.sha256(candidate))
            self.assertEqual(sorted(same), sorted(tensors))
            with self.assertRaises(ValueError):
                capabilities.writhing_ritual(d / 'out.native', d / 'twice.native')


if __name__ == '__main__':
    unittest.main()
