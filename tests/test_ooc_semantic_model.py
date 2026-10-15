"""Focused pure-Python checks for the frozen semantic OOC model tool."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools import train_ooc_semantic_model as model


def row(seed, action, q, card_id=10):
    return {
        "sourceSeed": str(seed),
        "decisionIdx": "0",
        "semanticEffect": "5",
        "semanticSource": "7",
        "semanticPayload": json.dumps({
            "type": "reward",
            "entity": {"type": "card", "value": {"id": card_id, "misc": 0, "upgraded": False}},
            "cardGroup": [], "groupOccurrence": 0, "occurrence": action,
            "sapphirePaired": False,
        }),
        "executedPrimitiveBits": json.dumps([action]),
        "semanticActionIdx": str(action),
        "qProduct": str(q),
        "richRow": "0,0",
    }


class SemanticModelTests(unittest.TestCase):
    def test_grouped_delta_is_centered_per_decision(self):
        rows = [row(1, 0, 0.2), row(1, 1, 0.8), row(2, 0, 0.1), row(2, 1, 0.3)]
        for item in rows:
            item["_group"] = (int(item["sourceSeed"]), 0)
        delta = model.grouped_delta(rows)
        np.testing.assert_allclose(delta, [-.3, .3, -.1, .1])
        self.assertAlmostEqual(float(delta[[0, 1]].mean()), 0.0)
        self.assertAlmostEqual(float(delta[[2, 3]].mean()), 0.0)

    def test_frozen_vocabulary_zeros_unseen_category_without_shape_change(self):
        train = [row(1, 0, 0.2, card_id=10), row(1, 1, 0.8, card_id=11)]
        holdout = [row(2, 0, 0.2, card_id=99), row(2, 1, 0.8, card_id=11)]
        for item in train + holdout:
            item["_group"] = (int(item["sourceSeed"]), 0)
        semantic_keys, primitive_keys = model.feature_keys(train)
        counts = model.unseen_feature_counts(holdout, set(semantic_keys))
        self.assertEqual(counts["categorical_distinct"], 2)
        self.assertIn("cat:card_id=99", counts["categorical"])
        matrix = model.matrices(holdout, ["x", "y"], semantic_keys, primitive_keys)
        self.assertEqual(matrix["SEMANTIC"].shape, (2, 2 + len(semantic_keys)))
        unknown_index = semantic_keys.index("cat:card_id=99") if "cat:card_id=99" in semantic_keys else None
        self.assertIsNone(unknown_index)

    def test_model_parameters_are_frozen_recipe(self):
        self.assertEqual(model.MODEL_PARAMS["n_estimators"], 160)
        self.assertEqual(model.MODEL_PARAMS["max_depth"], 3)
        self.assertEqual(model.MODEL_PARAMS["random_state"], 20260910)
        self.assertEqual(model.MODEL_PARAMS["objective"], "reg:squarederror")

    def test_evaluation_rejects_changed_semantic_encoder(self):
        frozen = {"semantic_encoder": {"sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "semantic encoder SHA256 differs"):
            model.validate_frozen_encoder(frozen)

    def test_write_json_rejects_nonfinite_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            model.write_json(path, {"value": float("nan")})
            self.assertEqual(json.loads(path.read_text())["value"], None)


if __name__ == "__main__":
    unittest.main()
