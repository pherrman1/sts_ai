import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("rank4_replay", ROOT / "tools" / "analyze_silver_rank4_interaction_replay.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Rank4ReplayDecisionTest(unittest.TestCase):
    def means(self):
        return {"current_uct": {"mean_b_best_probability": .4, "mean_b_regret": 4.0},
                "oracle_visit_puct": {"mean_b_best_probability": .5, "mean_b_regret": 3.5}}

    def test_supported_and_rejected_boundaries(self):
        supported = {"mean_b_best_probability_delta": .02, "mean_frozen_b_regret_delta": -.15,
                     "b_best_probability_delta_ci95": [.001, .04], "mean_frozen_b_regret_delta_ci95": [-.3, .05]}
        self.assertEqual(MODULE.decision(supported, self.means())["classification"], "INTERACTION_SUPPORTED")
        rejected = {"mean_b_best_probability_delta": 0., "mean_frozen_b_regret_delta": 0.,
                    "b_best_probability_delta_ci95": [-.04, .01], "mean_frozen_b_regret_delta_ci95": [-.05, .02]}
        self.assertEqual(MODULE.decision(rejected, self.means())["classification"], "INTERACTION_REJECTED")

    def test_lf_crlf_variants_share_canonical_semantic_hash(self):
        lf = b'{"a":1,"b":2}\n{"x":"y"}\n'
        crlf = lf.replace(b"\n", b"\r\n")
        left, right = MODULE.newline_hashes_bytes(lf), MODULE.newline_hashes_bytes(crlf)
        self.assertNotEqual(left["observed_sha256"], right["observed_sha256"])
        self.assertEqual(left["canonical_semantic_sha256"], right["canonical_semantic_sha256"])
        self.assertTrue(MODULE.byte_hash_acceptance(right, left["observed_sha256"])[1])

    def test_byte_mismatch_requires_explicit_lf_crlf_proof_and_content_change_fails(self):
        original = MODULE.newline_hashes_bytes(b'{"value":1}\n')
        changed = MODULE.newline_hashes_bytes(b'{"value":2}\r\n')
        self.assertNotEqual(original["canonical_semantic_sha256"], changed["canonical_semantic_sha256"])
        self.assertEqual(MODULE.byte_hash_acceptance(changed, original["observed_sha256"]), (False, False))

    def test_shared_provenance_fails_but_independent_matching_metadata_passes(self):
        record = {"recorded_provenance_id": "interaction", "source_commit": "a", "executable_sha256": "b", "snapshots_sha256": "c", "relabels_sha256": "d"}
        proof = {"recorded": record, "root_replicate_set": [("g", 0)], "search_seeds": {("g", 0): 7}}
        rows = [{"group_id": "g", "replicate": 0, "arm": "current_uct", "selected_action_fingerprint": "x", "frozen_b_top_choice": True, "frozen_b_regret": 0.0},
                {"group_id": "g", "replicate": 0, "arm": "oracle_visit_puct", "selected_action_fingerprint": "x", "frozen_b_top_choice": True, "frozen_b_regret": 0.0}]
        header = {key: "v" for key in MODULE.HEADER_FIELDS}
        shared = MODULE.cross_provenance((proof, header, rows), (proof, header, rows))
        self.assertFalse(shared["pass"])
        independent = {**proof, "recorded": {**record, "recorded_provenance_id": "rankshape"}}
        self.assertTrue(MODULE.cross_provenance((proof, header, rows), (independent, header, rows))["pass"])


if __name__ == "__main__":
    unittest.main()
