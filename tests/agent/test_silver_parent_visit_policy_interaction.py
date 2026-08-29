import importlib.util
import io
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_rank4_interaction", ROOT / "tools" / "train_silver_parent_visit_policy_interaction.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Rank4InteractionPolicyTest(unittest.TestCase):
    def parents(self):
        # Two legal siblings, with the frozen state/action split retained.
        x = np.zeros((2, 1788), dtype=np.float64)
        x[:, 0] = 1.0
        x[0, 1766] = 1.0
        x[1, 1767] = 1.0
        return [("root", x, np.asarray([.75, .25]))]

    def test_zero_interaction_exactly_reproduces_grouped_linear(self):
        parents = self.parents()
        weights = np.zeros(1788)
        reference = MODULE.interaction_probabilities(parents, weights, np.zeros((1766, 4)), np.zeros((22, 4)))
        audit = MODULE.assert_zero_interaction_parity(parents, weights, reference)
        self.assertEqual(audit["max_absolute_probability_error"], 0.0)
        self.assertEqual(float(reference["root"].sum()), 1.0)

    def test_state_changes_fixed_sibling_ordering(self):
        x = np.zeros((2, 1788), dtype=np.float64)
        x[:, 0] = 1.0
        x[0, 1766], x[1, 1767] = 1.0, 1.0
        weights = np.zeros(1788)
        u, v = np.zeros((1766, 4)), np.zeros((22, 4))
        u[0, 0], v[0, 0], v[1, 0] = 1.0, 1.0, -1.0
        first = MODULE.interaction_probabilities([("a", x, np.asarray([.5, .5]))], weights, u, v)["a"]
        x[:, 0] = -1.0
        second = MODULE.interaction_probabilities([("b", x, np.asarray([.5, .5]))], weights, u, v)["b"]
        self.assertGreater(first[0], first[1])
        self.assertLess(second[0], second[1])

    def test_both_blocks_are_required_and_parent_macro_objective(self):
        x = np.zeros((2, 1788), dtype=np.float64)
        x[:, 0], x[0, 1766], x[1, 1767] = 1.0, 1.0, 1.0
        weights = MODULE.torch.zeros(1788, dtype=MODULE.torch.float64)
        u = MODULE.torch.zeros((1766, 4), dtype=MODULE.torch.float64, requires_grad=True)
        v = MODULE.torch.zeros((22, 4), dtype=MODULE.torch.float64, requires_grad=True)
        u.data[0, 0] = 1.0
        v.data[0, 0], v.data[1, 0] = 1.0, -1.0
        loss = MODULE.objective(MODULE.tensor_parents([("short", x, np.asarray([1., 0.])),
            ("long", np.vstack([x, x]), np.asarray([1., 0., 0., 0.]))]), weights, u, v)
        self.assertTrue(MODULE.torch.isfinite(loss))
        loss.backward()
        self.assertNotEqual(float(u.grad[0, 0]), 0.0)
        self.assertNotEqual(float(v.grad[0, 0]), 0.0)

    def test_unequal_sibling_counts_receive_equal_parent_weight(self):
        short = np.zeros((2, 1788), dtype=np.float64)
        long = np.zeros((4, 1788), dtype=np.float64)
        weights = MODULE.torch.zeros(1788, dtype=MODULE.torch.float64)
        u = MODULE.torch.zeros((1766, 4), dtype=MODULE.torch.float64)
        v = MODULE.torch.zeros((22, 4), dtype=MODULE.torch.float64)
        loss = MODULE.objective(MODULE.tensor_parents([
            ("short", short, np.asarray([1., 0.])),
            ("long", long, np.asarray([1., 0., 0., 0.])),
        ]), weights, u, v)
        self.assertAlmostEqual(float(loss), (np.log(2) + np.log(4)) / 2)

    def test_fixed_seed_rerun_reproduces_arrays_and_predictions(self):
        parents = self.parents()
        # The two nonzero action columns allow the V-first-gradient contract.
        weights = np.zeros(1788, dtype=np.float64)
        u, v, _, parity = MODULE.fit_twice_and_require_parity(parents, weights, parents)
        self.assertEqual(u.shape, (1766, 4))
        self.assertEqual(v.shape, (22, 4))
        self.assertTrue(parity["model_arrays_byte_equal"])
        self.assertTrue(parity["anchor_predictions_byte_equal"])

    def test_serialization_round_trip(self):
        with io.BytesIO() as stream:
            arrays = {"u": np.ones((1766, 4)), "v": np.ones((22, 4)), "rank": np.asarray([4])}
            np.savez(stream, **arrays)
            stream.seek(0)
            with np.load(stream, allow_pickle=False) as restored:
                self.assertTrue(np.array_equal(restored["u"], arrays["u"]))
                self.assertTrue(np.array_equal(restored["v"], arrays["v"]))
                self.assertEqual(int(restored["rank"][0]), 4)


if __name__ == "__main__":
    unittest.main()
