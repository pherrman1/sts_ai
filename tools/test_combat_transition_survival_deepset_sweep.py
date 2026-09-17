import unittest
import copy
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import torch

from tools import combat_transition_survival_deepset_sweep as sweep


class SurvivalDeepSetsSweepTests(unittest.TestCase):
    def test_arms_and_order_are_exact(self):
        self.assertEqual(sweep.ARM_ORDER, ("baseline", "lowerLr", "muchLowerLr",
                                           "moreWd", "strongWd", "lowerLrWd"))
        self.assertEqual(sweep.ARMS, {
            "baseline": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-4),
            "lowerLr": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=1e-4),
            "muchLowerLr": dict(encoderLr=2e-5, headLr=2e-4, weightDecay=1e-4),
            "moreWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=5e-4),
            "strongWd": dict(encoderLr=1e-4, headLr=1e-3, weightDecay=1e-3),
            "lowerLrWd": dict(encoderLr=5e-5, headLr=5e-4, weightDecay=5e-4),
        })

    def test_each_required_gate_can_reject_selected_arm(self):
        gates = {name: True for name in (*sweep.GATES, "validity")}
        result = dict(selection=dict(selectedArm="baseline"),
                      arms=dict(baseline=dict(evaluation=dict(gatesPassed=gates))))
        self.assertEqual(sweep.compare_selected(result, {})["decision"], "SURVIVAL_DEEPSET_SWEEP_GO")
        for gate in gates:
            changed = copy.deepcopy(result)
            changed["arms"]["baseline"]["evaluation"]["gatesPassed"][gate] = False
            self.assertEqual(sweep.compare_selected(changed, {})["decision"], "SURVIVAL_DEEPSET_SWEEP_REJECTED")
        del gates["deathNllRelative"]
        with self.assertRaises(ValueError):
            sweep.compare_selected(result, {})

    def test_arm_recipe_does_not_mutate_settings(self):
        saved = copy.deepcopy(sweep.ARMS)
        recipe = sweep.arm_recipe("strongWd")
        recipe["encoderLr"] = 9.0
        self.assertEqual(sweep.ARMS, saved)

    def test_fixed_horizon_and_strict_selection_with_mocked_batches(self):
        for improving in (False, True):
            model = sweep.fit.SurvivalNet(torch.nn.Linear(10, 64))
            cache = dict(win=np.array([True, False]))
            captured = {}
            orders = []
            def update(model, optimizer, inputs, labels):
                captured["rates"] = [group["lr"] for group in optimizer.param_groups]
                captured["decay"] = [group["weight_decay"] for group in optimizer.param_groups]
                return 0.1, {}
            def inputs(arrays, cache, batch, device, split):
                self.assertEqual(split, 0)
                orders.append(batch.copy())
                return []
            def load(path, **kwargs):
                return real_load(path, map_location="cpu", weights_only=False)
            real_load = torch.load
            real_tensor = torch.as_tensor
            losses = iter([1.0 / epoch for epoch in range(1, 41)] if improving else [0.1] * 40)
            with tempfile.TemporaryDirectory() as folder, \
                 mock.patch.object(sweep.fit, "inputs_for", side_effect=inputs), \
                 mock.patch.object(sweep.fit, "update_batch", side_effect=update), \
                 mock.patch.object(sweep.fit, "predict", return_value=np.zeros(2)), \
                 mock.patch.object(sweep.fit, "summarize", side_effect=lambda *args: {"nll": next(losses)}), \
                 mock.patch.object(torch, "as_tensor", side_effect=lambda value, **kwargs: real_tensor(value, dtype=kwargs["dtype"])), \
                 mock.patch.object(torch, "load", side_effect=load), \
                 mock.patch("builtins.print"):
                result = sweep.fit_arm(model, {}, cache, np.arange(2), np.arange(2), Path(folder), "test", "lowerLrWd")
            self.assertEqual(len(result["history"]), 40 if improving else 12)
            self.assertEqual(result["selectedEpoch"], 40 if improving else 1)
            self.assertEqual(captured["rates"], [5e-5, 5e-4])
            self.assertEqual(captured["decay"], [5e-4, 5e-4])
            self.assertEqual([group["lr"] for group in result["optimizerScope"]["groups"]], captured["rates"])
            generator = np.random.default_rng(20260912)
            for order in orders:
                np.testing.assert_array_equal(order, generator.permutation(np.arange(2)))

    def test_sweep_uses_unmodified_survival_gates(self):
        self.assertEqual(sweep.GATES, dict(nllRelative=0.02, brierRelative=0.05,
                                           deathNllRelative=0.10, lowPreHpNllRelative=0.10))


if __name__ == "__main__":
    unittest.main()
