import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_parent_policy", ROOT / "tools" / "train_silver_parent_policy.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SilverParentPolicyTest(unittest.TestCase):
    def test_whole_parent_metrics_ties_and_regret(self):
        groups = {"g": [
            {"reference_q": 3.0, "action_fingerprint": "CARD|a"},
            {"reference_q": 1.0, "action_fingerprint": "END_TURN"},
            {"reference_q": 2.0, "action_fingerprint": "CARD|b"},
        ]}
        metrics, parent = MODULE.group_metrics(groups, {"g": [0.0, 0.0, 1.0]})
        self.assertEqual(metrics["reference_pairs"], 3)
        self.assertEqual(metrics["prediction_tie_count"], 1)
        self.assertEqual(metrics["pairwise_concordance"], 0.5)
        self.assertEqual(metrics["mean_regret"], 1.0)
        self.assertEqual(parent["g"]["pairs"], 3)

    def test_split_is_parent_grouped_deterministic_and_anchor_safe(self):
        groups = {f"g{i}" for i in range(100)}
        anchors = {"g1", "g7", "g19"}
        nonanchors = sorted(groups - anchors)
        first = {group for group in nonanchors if int(MODULE.hashlib.sha256(
            (MODULE.SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15}
        second = {group for group in nonanchors if int(MODULE.hashlib.sha256(
            (MODULE.SPLIT_SALT + group).encode()).hexdigest(), 16) % 100 < 15}
        self.assertEqual(first, second)
        self.assertFalse(first & anchors)
        self.assertFalse((set(nonanchors) - first) & anchors)

    def test_bootstrap_is_deterministic_whole_parent(self):
        model = {"a": {"concordant": 1, "pairs": 1, "top": 1, "regret": 0},
                 "b": {"concordant": 0, "pairs": 1, "top": 0, "regret": 2}}
        order = {"a": {"concordant": 0, "pairs": 1, "top": 0, "regret": 1},
                 "b": {"concordant": 0, "pairs": 1, "top": 0, "regret": 3}}
        self.assertEqual(MODULE.bootstrap(model, order, 100, 42),
                         MODULE.bootstrap(model, order, 100, 42))


if __name__ == "__main__":
    unittest.main()
