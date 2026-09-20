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
            MODULE.validate_partition(config, packets)

    def test_training_counts_are_exact_and_locked_is_not_in_them(self):
        config = {"roles": {
            "base_training_pool": {"source_seeds": list(range(20))},
            "expansion_training_pool": {"source_seeds": list(range(20, 60)), "primary_first_20": list(range(20, 40))},
            "locked_validation": {"source_seeds": list(range(60, 100))},
        }}
        packets = {role: {"rows": [{"source_seed": str(seed)} for seed in spec["source_seeds"]]}
                   for role, spec in config["roles"].items()}
        partition = MODULE.validate_partition(config, packets)
        base = MODULE.rows_for_sources(packets["base_training_pool"]["rows"], set(partition["base_training_pool"]))
        expansion = packets["expansion_training_pool"]["rows"]
        train40 = base + MODULE.rows_for_sources(expansion, set(partition["expansion_training_pool"]) & set(map(str, range(20, 40))))
        train60 = base + expansion
        locked = set(partition["locked_validation"])
        self.assertEqual(len({row["source_seed"] for row in base}), 20)
        self.assertEqual(len({row["source_seed"] for row in train40}), 40)
        self.assertEqual(len({row["source_seed"] for row in train60}), 60)
        self.assertFalse({row["source_seed"] for row in train60} & locked)

    def test_prediction_selection_does_not_require_q32(self):
        rows = [
            {"prefix_key": '["a"]', "predicted_MLP_FLAT_V1": 1.0},
            {"prefix_key": '["b"]', "predicted_MLP_FLAT_V1": 2.0},
        ]
        self.assertEqual(MODULE.choose(rows, "MLP_FLAT_V1")["prefix_key"], '["b"]')

    def test_frozen_model_parameter_count(self):
        model = MODULE.FROZEN.FlatMLP(2116)
        self.assertEqual(sum(parameter.numel() for parameter in model.parameters()), 75809)


if __name__ == "__main__":
    unittest.main()
