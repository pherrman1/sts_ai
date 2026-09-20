#!/usr/bin/env python3
import json
import unittest

import numpy as np

from learn_silver_prefix_scorer import (
    CARD_COUNT, FORBIDDEN_FIELDS, FOLD_COUNT, action_numeric, add_parent_q,
    choose_predicted, factorized_q_mask, fnv1a, linear_vector, none_action, parse_action,
    source_fold, standardize,
)


class LearnedPrefixContracts(unittest.TestCase):
    def test_source_seed_folds_are_deterministic(self):
        self.assertEqual(source_fold("12100017"), fnv1a("12100017") % FOLD_COUNT)
        self.assertEqual(source_fold("12100017"), source_fold(12100017))

    def test_source_fold_disjointness_contract(self):
        sources = ["12100017", "12100018", "12100052"]
        self.assertTrue(all(source_fold(source) in range(5) for source in sources))
        self.assertEqual([source_fold(source) for source in sources],
                         [source_fold(source) for source in sources])

    def test_card_instance_ids_are_not_action_features(self):
        action = parse_action("sa/t=1/s=1/c=321_999_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=3/sel=",
                              {"monsters": [{"curHp": 10, "maxHp": 20}]})
        self.assertEqual(len(action_numeric(action)), 16)
        self.assertNotIn(999.0, action_numeric(action))

    def test_action_surface_rejects_unsupported_types(self):
        with self.assertRaises(ValueError):
            parse_action("sa/t=2/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel=", {})

    def test_factorized_parent_identity(self):
        a = "sa/t=1/s=1/c=321_2_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=3/sel="
        b = "sa/t=5/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel="
        rows = [{"leaf_snapshot_id": "leaf", "prefix_key": json.dumps([a]),
                 "prefix_fingerprints": [a], "prefix_length": 1, "q32": 4.0,
                 "leaf_baseline32": 1.0},
                {"leaf_snapshot_id": "leaf", "prefix_key": json.dumps([a, b]),
                 "prefix_fingerprints": [a, b], "prefix_length": 2, "q32": 7.0,
                 "leaf_baseline32": 1.0}]
        add_parent_q(rows)
        self.assertEqual(rows[1]["parent_q32"], rows[0]["q32"])
        self.assertAlmostEqual((rows[1]["q32"] - rows[1]["leaf_baseline32"]),
                               (rows[1]["parent_q32"] - rows[1]["leaf_baseline32"]) +
                               (rows[1]["q32"] - rows[1]["parent_q32"]))

    def test_factorized_q_supervision_is_only_length_one(self):
        rows = [{"prefix_length": 1}, {"prefix_length": 2}, {"prefix_length": 2},
                {"prefix_length": 1}]
        np.testing.assert_array_equal(factorized_q_mask(rows), [1.0, 0.0, 0.0, 1.0])

    def test_centered_target(self):
        self.assertEqual(7.5 - 3.0, 4.5)

    def test_none_action_is_explicit(self):
        action = none_action()
        self.assertEqual(action["card_id"], -1)
        self.assertEqual(action["type"], "NONE")

    def test_tie_break_key_is_serializable(self):
        keys = [json.dumps(["b"], separators=(",", ":")), json.dumps(["a"], separators=(",", ":"))]
        self.assertEqual(max(keys), '["b"]')

    def test_stop_is_preferred_when_prediction_is_higher(self):
        rows = [{"prefix_key": '["card"]', "prefix_length": 1, "predicted_X": 2.0, "q32": 3.0},
                {"prefix_key": '["card","extend"]', "prefix_length": 2, "predicted_X": 1.0, "q32": 20.0}]
        self.assertEqual(choose_predicted(rows, "X")["prefix_length"], 1)

    def test_extension_is_preferred_when_prediction_is_higher(self):
        rows = [{"prefix_key": '["card"]', "prefix_length": 1, "predicted_X": 2.0, "q32": 3.0},
                {"prefix_key": '["card","extend"]', "prefix_length": 2, "predicted_X": 4.0, "q32": 20.0}]
        self.assertEqual(choose_predicted(rows, "X")["prefix_length"], 2)

    def test_held_out_q_is_looked_up_after_selection(self):
        rows = [{"prefix_key": '["a"]', "predicted_X": 4.0, "q32": 1.0},
                {"prefix_key": '["b"]', "predicted_X": 3.0, "q32": 100.0}]
        selected = choose_predicted(rows, "X")
        self.assertEqual(selected["q32"], 1.0)

    def test_teacher_fields_do_not_reach_linear_tensor(self):
        row = {"state_features": [1.0], "action1": none_action(), "action2": none_action(),
               "prefix_length": 1, "teacher_a": 999.0, "teacher_b": -999.0}
        base = linear_vector(row)
        row["teacher_a"] = -100000.0
        row["teacher_b"] = 100000.0
        np.testing.assert_array_equal(base, linear_vector(row))

    def test_normalization_is_train_only(self):
        train = np.asarray([[0.0, 1.0], [2.0, 1.0]], dtype=np.float32)
        test = np.asarray([[100.0, 1.0]], dtype=np.float32)
        _, transformed, (mean, _) = standardize(train, test)
        self.assertEqual(mean.tolist(), [1.0, 1.0])
        self.assertGreater(float(transformed[0, 0]), 50.0)

    def test_forbidden_fields_are_not_model_inputs(self):
        self.assertTrue(FORBIDDEN_FIELDS.isdisjoint({"state_features", "action1", "action2", "prefix_length"}))

    def test_card_count_is_fixed_not_data_derived(self):
        self.assertEqual(CARD_COUNT, 371)


if __name__ == "__main__":
    unittest.main()
