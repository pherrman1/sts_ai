"""Contracts for the offline Silver terminal-value audit."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_terminal_value", ROOT / "tools" / "analyze_silver_terminal_value.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def features(**overrides):
    result = {name: 0.0 for name in MODULE.FEATURES}
    result["victory"] = 1.0
    result.update(overrides)
    return result


class SilverTerminalValueContracts(unittest.TestCase):
    def test_compatible_potion_coefficient_is_tied_between_outcomes(self):
        victory = features(victory_potion_count=1.0)
        loss = features(victory=0.0, loss_potion_count=1.0)
        vector = MODULE.parameter_features(victory)
        loss_vector = MODULE.parameter_features(loss)
        potion_index = MODULE.PARAMETERS.index("potion_weight")
        self.assertEqual(vector[potion_index], 1.0)
        self.assertEqual(loss_vector[potion_index], 0.5)

    def test_mixed_replicates_are_linearized_without_branch_loss(self):
        mixed = features(victory=0.5, victory_potion_count=0.5,
                         loss_potion_count=0.5, loss_monsters_alive=0.5)
        vector = MODULE.parameter_features(mixed)
        self.assertEqual(vector[MODULE.PARAMETERS.index("win_bonus")], 0.5)
        self.assertEqual(vector[MODULE.PARAMETERS.index("potion_weight")], 0.75)
        self.assertEqual(vector[MODULE.PARAMETERS.index("alive_weight")], -0.5)

    def test_root_correction_is_kept_separate_from_leaf_features(self):
        leaf = features(max_hp_delta=2.0)
        original = features(max_hp_delta=3.0)
        vector = MODULE.corrected_parameter_features(leaf, original)
        self.assertEqual(vector[MODULE.PARAMETERS.index("max_hp_weight")], 5.0)

    def test_equal_source_group_pair_weighting(self):
        def leaf(source, group, name):
            return {"source_seed": source, "group_id": group,
                    "leaf_snapshot_id": name, "features": features(),
                    "original_root_features": features(), "teacher_a": 0.0,
                    "teacher_b": 0.0}
        rows = [leaf("a", "g1", "a1"), leaf("a", "g1", "a2"),
                leaf("a", "g2", "a3"), leaf("a", "g2", "a4"),
                leaf("b", "g3", "b1"), leaf("b", "g3", "b2")]
        pairs = MODULE.weighted_pairs(rows)
        # Recover the intended source/group totals directly: each source gets
        # unit total weight, and each of its groups shares it equally.
        self.assertEqual(len(pairs), 3)
        self.assertAlmostEqual(sum(weight * weight for weight, _, _ in pairs), 2.0)

    def test_fit_is_deterministic_and_sign_constrained(self):
        rows = []
        for index in range(4):
            row = {"source_seed": str(index // 2), "group_id": f"g{index // 2}",
                   "leaf_snapshot_id": f"l{index}", "features": features(
                       victory=1.0 if index % 2 == 0 else 0.0,
                       victory_potion_count=1.0 if index % 2 == 0 else 0.0,
                       loss_monsters_alive=1.0 if index % 2 else 0.0),
                   "original_root_features": features(),
                   "teacher_a": float(index), "teacher_b": float(-index)}
            rows.append(row)
        first, first_result = MODULE.fit_compatible(rows, 1.0)
        second, second_result = MODULE.fit_compatible(rows, 1.0)
        self.assertTrue(first_result.success and second_result.success)
        self.assertEqual(first, second)
        self.assertTrue(all(value >= -1e-12 for value in first.values()))

    def test_teacher_b_is_not_an_implicit_fit_input(self):
        rows = []
        for index in range(4):
            rows.append({"source_seed": str(index // 2), "group_id": f"g{index // 2}",
                         "leaf_snapshot_id": f"l{index}", "features": features(
                             victory=1.0, victory_turn=float(index)),
                         "original_root_features": features(),
                         "teacher_a": float(index), "teacher_b": float(100 - index)})
        a, _ = MODULE.fit_compatible(rows, 1.0, "teacher_a")
        a_changed_b = [dict(row, teacher_b=row["teacher_b"] * 1000) for row in rows]
        a_again, _ = MODULE.fit_compatible(a_changed_b, 1.0, "teacher_a")
        self.assertEqual(a, a_again)

    def test_source_bootstrap_clones_duplicate_occurrences(self):
        def leaf(source, group, name):
            return {"source_seed": source, "group_id": group,
                    "leaf_snapshot_id": name, "features": features(),
                    "original_root_features": features(), "teacher_a": 0.0,
                    "teacher_b": 0.0}

        by_source = {
            "a": [(leaf("a", "g", "l"), 1.0, 2.0)],
            "b": [(leaf("b", "h", "m"), 3.0, 4.0)],
        }

        class AlwaysFirst:
            def choice(self, values):
                return values[0]

        sample = MODULE.bootstrap_source_sample(
            by_source, ["a", "b"], AlwaysFirst(), replicate=7)
        self.assertEqual(len(sample), 2)
        self.assertEqual(len({row[0]["group_id"] for row in sample}), 2)
        self.assertEqual(len({row[0]["leaf_snapshot_id"] for row in sample}), 2)

    def test_untied_crossfit_selects_lambda_inside_each_training_partition(self):
        rows = []
        for source in range(5):
            for suffix, turn in enumerate((source, source + 1)):
                rows.append({
                    "source_seed": str(source), "group_id": f"g{source}",
                    "leaf_snapshot_id": f"l{source}-{suffix}",
                    "features": features(victory_turn=float(turn)),
                    "original_root_features": features(),
                    "teacher_a": float(source + suffix), "teacher_b": float(source),
                })
        _, folds, _ = MODULE.crossfit_untied(rows)
        self.assertEqual(len(folds), 5)
        self.assertTrue(all(fold["lambda"] in MODULE.LAMBDAS for fold in folds))


if __name__ == "__main__":
    unittest.main()
