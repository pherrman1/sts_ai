import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "blend", ROOT / "tools" / "analyze_silver_m10_rollout_blend.py")
BLEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BLEND)


class SilverM10RolloutBlendTest(unittest.TestCase):
    def test_metrics_use_complete_sibling_ranking_and_centering(self):
        rows = [
            {"group_id": "a", "reference": 3.0, "p": 2.0},
            {"group_id": "a", "reference": 1.0, "p": 0.0},
            {"group_id": "b", "reference": 4.0, "p": 1.0},
            {"group_id": "b", "reference": 2.0, "p": 1.0},
        ]
        metric = BLEND.metrics(rows, lambda row: row["p"])
        self.assertEqual(metric["reference_pairs"], 2)
        self.assertEqual(metric["prediction_ties"], 1)
        self.assertEqual(metric["pairwise"], .75)
        self.assertEqual(metric["top_leaf"], 1.0)
        self.assertEqual(metric["mean_regret"], 0.0)

    def test_complete_drops_single_leaf_groups(self):
        rows = [{"group_id": "a", "corpus_group_size": 2, "x": 1},
                {"group_id": "a", "corpus_group_size": 2, "x": 2},
                {"group_id": "b", "corpus_group_size": 1, "x": 3}]
        self.assertEqual([row["x"] for row in BLEND.complete(rows)], [1, 2])

    def test_complete_drops_partial_corpus_groups(self):
        rows = [{"group_id": "a", "corpus_group_size": 3, "x": 1},
                {"group_id": "a", "corpus_group_size": 3, "x": 2}]
        self.assertEqual(BLEND.complete(rows), [])

    def test_exact_m10_tree_limit_is_frozen(self):
        self.assertEqual(BLEND.M10_TREES, 501)

    def test_lock_rejects_more_than_two_candidates(self):
        lock = {"schema": "silver_m10_rollout_blend_lock_v1", "input_hashes": {"x": "y"},
                "depth_edges": [4, 5], "selection_metrics": {"x": 1}, "decision_rule": "rule",
                "candidates": [{"kind": "fixed", "name": str(i), "alpha": .1} for i in range(3)]}
        with self.assertRaises(SystemExit):
            BLEND.validate_lock(lock, {"x": "y"})

    def test_lock_rejects_off_grid_depth_schedule(self):
        lock = {"schema": "silver_m10_rollout_blend_lock_v1", "input_hashes": {"x": "y"},
                "depth_edges": [4, 5], "selection_metrics": {"x": 1}, "decision_rule": "rule",
                "candidates": [{"kind": "depth", "name": "deep", "alpha_deep": .2,
                                "min_depth": 6}]}
        with self.assertRaises(SystemExit):
            BLEND.validate_lock(lock, {"x": "y"})

    def test_bootstrap_is_deterministic_and_group_resampled(self):
        rows = [
            {"group_id": group, "reference": reference, "rollout": rollout, "blend": blend}
            for group, values in (("a", ((2, 0, 2), (0, 2, 0))),
                                  ("b", ((3, 1, 3), (1, 3, 1))))
            for reference, rollout, blend in values
        ]
        candidates = {"rollout": lambda row: row["rollout"],
                      "blend": lambda row: row["blend"]}
        first = BLEND.bootstrap(rows, candidates, 100, 7)
        second = BLEND.bootstrap(rows, candidates, 100, 7)
        self.assertEqual(first, second)
        self.assertEqual(first["blend"]["pairwise"]["probability_improves"], 1.0)


if __name__ == "__main__":
    unittest.main()
