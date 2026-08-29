import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_grouped_visit_export", ROOT / "tools" / "export_silver_grouped_visit_priors.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SilverGroupedVisitReplayArtifactTest(unittest.TestCase):
    def source_rows(self):
        return [
            {"group_id": "a", "action_fingerprint": "CARD|a", "silver_order": 0,
             "probability": .25, "a_visit_share": .0},
            {"group_id": "a", "action_fingerprint": "END_TURN", "silver_order": 1,
             "probability": .75, "a_visit_share": 1.0},
            {"group_id": "b", "action_fingerprint": "CARD|b", "silver_order": 0,
             "probability": 1.0, "a_visit_share": 1.0},
        ]

    def header(self):
        return {"schema": MODULE.EXPECTED_INPUT_SCHEMA,
                "feature_schema": "silver_parent_policy_features_v1",
                "feature_count": 1788, "parent_key": "group_id"}

    def test_replay_schema_and_probability_parity(self):
        expanded = []
        for parent in range(63):
            count = 6 if parent < 25 else 5
            values = [1.0 / count] * count
            for action, value in enumerate(values):
                expanded.append({"group_id": f"g{parent}", "action_fingerprint": f"A|{parent}|{action}",
                                 "silver_order": action, "probability": value, "a_visit_share": value})
        self.assertEqual(len(expanded), 340)
        MODULE.validate_probabilities(self.header(), expanded)
        replay_rows = MODULE.replay_rows(expanded)
        self.assertEqual([row["probability"] for row in expanded],
                         [row["normalized_visit_share"] for row in replay_rows])
        self.assertTrue(all(set(row) == {"group_id", "action_fingerprint", "silver_order", "normalized_visit_share"}
                            for row in replay_rows))

    def test_rejects_non_normalized_parent(self):
        rows = []
        for parent in range(63):
            count = 6 if parent < 25 else 5
            for action in range(count):
                rows.append({"group_id": f"g{parent}", "action_fingerprint": f"A|{parent}|{action}",
                             "silver_order": action, "probability": 1.0 / count, "a_visit_share": 0.0})
        rows[0]["probability"] = 0.5
        with self.assertRaises(ValueError):
            MODULE.validate_probabilities(self.header(), rows)
