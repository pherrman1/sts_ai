#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "train_silver_prefix_learning_curve", ROOT / "tools/train_silver_prefix_learning_curve.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ScaleValidationContracts(unittest.TestCase):
    @staticmethod
    def synthetic_seed_manifest():
        return {
            "existing_20": list(range(20)),
            "new_expansion_training": {
                "source_seeds": list(range(20, 60)),
                "primary_first_20": list(range(20, 40)),
            },
            "new_locked_validation": {"source_seeds": list(range(60, 100))},
        }

    def test_preregistered_roles_are_disjoint_and_sized(self):
        manifest = __import__("json").loads(
            (ROOT / "docs/experiments/evidence/silver_prefix_scorer_scale_20260920/source-seed-manifest.json").read_text())
        base = {str(x) for x in manifest["existing_20"]}
        expansion = {str(x) for x in manifest["new_expansion_training"]["source_seeds"]}
        locked = {str(x) for x in manifest["new_locked_validation"]["source_seeds"]}
        self.assertEqual((len(base), len(expansion), len(locked)), (20, 40, 40))
        self.assertFalse(base & expansion)
        self.assertFalse(base & locked)
        self.assertFalse(expansion & locked)

    def test_deterministic_primary_train40_assignment(self):
        manifest = __import__("json").loads(
            (ROOT / "docs/experiments/evidence/silver_prefix_scorer_scale_20260920/source-seed-manifest.json").read_text())
        expansion = manifest["new_expansion_training"]["source_seeds"]
        self.assertEqual(expansion[:20], manifest["new_expansion_training"]["primary_first_20"])
        self.assertEqual(len(set(manifest["new_expansion_training"]["primary_first_20"])), 20)

    def test_validate_partition_rejects_locked_training_overlap(self):
        config = {"roles": {
            "base_training_pool": {"source_seeds": [1] * 20},
            "expansion_training_pool": {"source_seeds": list(range(20, 60)), "primary_first_20": list(range(20, 40))},
            "locked_validation": {"source_seeds": list(range(60, 100))},
        }}
        packets = {role: {"rows": [{"source_seed": str(seed)} for seed in spec["source_seeds"]]}
                   for role, spec in config["roles"].items()}
        with self.assertRaises(SystemExit):
            MODULE.validate_partition(config, packets, self.synthetic_seed_manifest())

    def test_training_counts_are_exact_and_locked_is_not_in_them(self):
        config = {"roles": {
            "base_training_pool": {"source_seeds": list(range(20))},
            "expansion_training_pool": {"source_seeds": list(range(20, 60)), "primary_first_20": list(range(20, 40))},
            "locked_validation": {"source_seeds": list(range(60, 100))},
        }}
        packets = {role: {"rows": [{"source_seed": str(seed)} for seed in spec["source_seeds"]]}
                   for role, spec in config["roles"].items()}
        partition = MODULE.validate_partition(config, packets, self.synthetic_seed_manifest())
        base = MODULE.rows_for_sources(packets["base_training_pool"]["rows"], set(partition["base_training_pool"]))
        expansion = packets["expansion_training_pool"]["rows"]
        train40 = base + MODULE.rows_for_sources(expansion, set(partition["expansion_training_pool"]) & set(map(str, range(20, 40))))
        train60 = base + expansion
        locked = set(partition["locked_validation"])
        self.assertEqual(len({row["source_seed"] for row in base}), 20)
        self.assertEqual(len({row["source_seed"] for row in train40}), 40)
        self.assertEqual(len({row["source_seed"] for row in train60}), 60)
        self.assertFalse({row["source_seed"] for row in train60} & locked)

    def test_validate_partition_rejects_role_reassignment_against_preregistration(self):
        manifest = self.synthetic_seed_manifest()
        config = {"roles": {
            "base_training_pool": {"source_seeds": list(range(20))},
            "expansion_training_pool": {"source_seeds": list(range(20, 60)), "primary_first_20": list(range(20, 40))},
            "locked_validation": {"source_seeds": list(range(59, 99))},
        }}
        packets = {role: {"rows": [{"source_seed": str(seed)} for seed in spec["source_seeds"]]}
                   for role, spec in config["roles"].items()}
        with self.assertRaises(SystemExit):
            MODULE.validate_partition(config, packets, manifest)

    def test_prediction_selection_does_not_require_q32(self):
        rows = [
            {"prefix_key": '["a"]', "predicted_MLP_FLAT_V1": 1.0},
            {"prefix_key": '["b"]', "predicted_MLP_FLAT_V1": 2.0},
        ]
        self.assertEqual(MODULE.choose(rows, "MLP_FLAT_V1")["prefix_key"], '["b"]')

    def test_frozen_model_parameter_count(self):
        model = MODULE.FROZEN.FlatMLP(2116)
        self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 75809)

    def test_committed_manifest_binds_frozen_scorer_implementation(self):
        manifest_path = ROOT / "docs/experiments/evidence/silver_prefix_scorer_scale_20260920/source-seed-manifest.json"
        manifest = __import__("json").loads(manifest_path.read_text())
        self.assertEqual(
            MODULE.sha256(ROOT / manifest["frozen_scorer"]["path"]),
            manifest["frozen_scorer"]["sha256"],
        )

    def test_analysis_config_must_hash_bind_committed_seed_manifest(self):
        manifest_path = ROOT / "docs/experiments/evidence/silver_prefix_scorer_scale_20260920/source-seed-manifest.json"
        config = {
            "source_seed_manifest": str(manifest_path),
            "source_seed_manifest_sha256": MODULE.sha256(manifest_path),
        }
        manifest, binding = MODULE.load_preregistered_manifest(config)
        self.assertEqual(manifest["schema"], "silver_prefix_scorer_scale_source_seed_manifest_v2")
        self.assertEqual(binding["sha256"], config["source_seed_manifest_sha256"])
        config["source_seed_manifest_sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            MODULE.load_preregistered_manifest(config)

    def test_intended_leaf_coverage_fails_closed(self):
        with self.assertRaises(SystemExit):
            MODULE.validate_intended_leaf_coverage(
                "locked_validation", {"leaf-a", "leaf-b"}, {"leaf-a"},
                {"leaf-a", "leaf-b"}, {"leaf-a", "leaf-b"}, set())
        with self.assertRaises(SystemExit):
            MODULE.validate_intended_leaf_coverage(
                "locked_validation", {"leaf-a", "leaf-b"}, {"leaf-a", "leaf-b"},
                {"leaf-a", "leaf-b"}, {"leaf-a", "leaf-b"}, {"leaf-b"})

    def test_concentration_gate_is_not_a_source_count_proxy(self):
        self.assertTrue(MODULE.concentration_passes(38, 0.10, 0.01))
        self.assertFalse(MODULE.concentration_passes(38, 0.10, 0.0))

    def test_source_contributions_report_singleton_sources_without_crashing(self):
        rows = [{"source_seed": "1", "group_id": "g", "baseline_value": 1.0,
                 "value": 2.0, "teacher_a": 3.0}]
        report = MODULE.source_contributions(rows)
        self.assertEqual(report[0]["comparable_sibling_group_count"], 0)
        self.assertIsNone(report[0]["difference"])
        self.assertFalse(MODULE.concentration_passes(2, 0.10, 0.01))

    def test_concentration_ranks_global_influence_not_per_source_mean(self):
        # A's per-source mean looks larger, but B's 20 leaves make its
        # leave-one-source-out effect larger on the global locked result.
        per_source_means = [
            {"source_seed": "A", "leaf_count": 1, "difference": 5.0},
            {"source_seed": "B", "leaf_count": 20, "difference": 4.0},
        ]
        global_influence = [
            {"omitted_source_seed": "A", "leaf_count": 1,
             "absolute_improvement_influence": 0.10},
            {"omitted_source_seed": "B", "leaf_count": 20,
             "absolute_improvement_influence": 1.25},
        ]
        self.assertEqual(per_source_means[0]["difference"] > per_source_means[1]["difference"], True)
        self.assertEqual(
            MODULE.top_positive_influence_sources(global_influence, count=1)[0]["omitted_source_seed"],
            "B",
        )

    def test_bootstrap_floor_is_preregistered(self):
        self.assertEqual(MODULE.MIN_BOOTSTRAP_ITERATIONS, 5000)


if __name__ == "__main__":
    unittest.main()
