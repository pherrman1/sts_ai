import importlib.util
import unittest

import numpy as np

try:
    from tools import combat_transition_attention_ablation as ablation
    from tools import combat_transition_surrogate as base
except ModuleNotFoundError:
    import combat_transition_attention_ablation as ablation
    import combat_transition_surrogate as base


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


class TestCombatTransitionAttentionAblation(unittest.TestCase):
    def _inputs(self):
        import torch

        batch = 2
        globals_continuous = torch.zeros(
            batch, len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=torch.float32
        )
        global_categories = torch.zeros((batch, 4), dtype=torch.int64)
        cards = torch.zeros((batch, base.MAX_CARDS, 4), dtype=torch.int16)
        cards[:, 0, 0] = 10
        cards[:, 0, 1] = 1
        cards[:, 1, 0] = 20
        cards[:, 1, 2] = 3
        card_mask = torch.zeros((batch, base.MAX_CARDS), dtype=torch.bool)
        card_mask[:, :2] = True
        relics = torch.zeros((batch, base.MAX_RELICS, 3), dtype=torch.int16)
        relics[:, 0, 0] = 26
        relics[:, 0, 2] = 1
        relic_mask = torch.zeros((batch, base.MAX_RELICS), dtype=torch.bool)
        relic_mask[:, 0] = True
        potions = torch.zeros((batch, 5, 2), dtype=torch.int16)
        potions[:, :, 0] = torch.arange(5)
        potions[:, :, 1] = base.EMPTY_POTION_SLOT_ID
        return [
            globals_continuous,
            global_categories,
            cards,
            relics,
            potions,
            card_mask,
            relic_mask,
        ]

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_attention_models_have_expected_heads_and_shapes(self):
        import torch

        torch.manual_seed(7)
        target_spec = {"maxHpDeltaValues": [0, 3], "relicDeltaValues": [0, 1]}
        inputs = self._inputs()
        phase2 = ablation.AttentionPhase2Net(
            torch,
            target_spec,
            np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
            np.ones(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
        )
        point = ablation.AttentionPointControlNet(
            torch,
            np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
            np.ones(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
        )
        phase2.net.eval()
        point.net.eval()
        with torch.no_grad():
            outputs = phase2.net(*inputs)
            point_outputs = point.net(*inputs)
        self.assertEqual([tuple(value.shape) for value in outputs], [
            (2,), (2, 2), (2, 2, 101), (2, 5, 48), (2, base.MAX_RELICS, 2)
        ])
        self.assertEqual([tuple(value.shape) for value in point_outputs], [(2,), (2,)])
        self.assertTrue(all(torch.isfinite(value).all() for value in outputs))
        self.assertTrue(all(torch.isfinite(value).all() for value in point_outputs))
        self.assertFalse(any("position_embedding" in name for name, _ in phase2.net.named_parameters()))

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_exchangeable_card_tokens_are_permutation_invariant(self):
        import torch

        torch.manual_seed(11)
        model = ablation.AttentionPointControlNet(
            torch,
            np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
            np.ones(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
        )
        model.net.eval()
        inputs = self._inputs()
        permuted = list(inputs)
        permuted[2] = inputs[2].clone()
        permuted[5] = inputs[5].clone()
        permuted[2][:, :2] = inputs[2][:, [1, 0]]
        permuted[5][:, :2] = inputs[5][:, [1, 0]]
        with torch.no_grad():
            original = model.net(*inputs)
            exchanged = model.net(*permuted)
        self.assertTrue(torch.allclose(original[0], exchanged[0], atol=1e-6, rtol=1e-6))
        self.assertTrue(torch.allclose(original[1], exchanged[1], atol=1e-6, rtol=1e-6))

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_relic_order_field_is_in_the_attention_input(self):
        import torch

        torch.manual_seed(13)
        model = ablation.AttentionPointControlNet(
            torch,
            np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
            np.ones(len(base.CONTINUOUS_GLOBAL_FIELDS), dtype=np.float32),
        )
        model.net.eval()
        inputs = self._inputs()
        inputs[3][:, 1, 0] = 27
        inputs[3][:, 1, 2] = 2
        inputs[6][:, 1] = True
        changed_order = list(inputs)
        changed_order[3] = inputs[3].clone()
        changed_order[3][:, 0, 2] = 2
        changed_order[3][:, 1, 2] = 1
        with torch.no_grad():
            original = model.net(*inputs)
            changed = model.net(*changed_order)
        self.assertFalse(torch.allclose(original[0], changed[0]))

    def _arrays(self):
        keys = ("globals_continuous", "global_categories", "cards", "relics",
                "potions", "card_mask", "relic_mask")
        arrays = {key: value.numpy() for key, value in zip(keys, self._inputs())}
        arrays.update(
            y_win=np.array([1, 0], dtype=np.int8),
            y_hp=np.array([.4, np.nan], dtype=np.float32),
            delta_index=np.array([1, 0], dtype=np.int16),
            y_hp_bin=np.array([40, 0], dtype=np.int16),
            potionCapacity=np.array([5, 3], dtype=np.int8),
            y_potions=np.full((2, 5), base.EMPTY_POTION_SLOT_ID, dtype=np.int16),
            y_relic_mask=arrays["relic_mask"].copy(),
            relic_delta_index=np.zeros((2, base.MAX_RELICS), dtype=np.int16),
        )
        arrays["relic_delta_index"][0, 0] = 1
        return arrays

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_trimmed_inputs_preserve_tokens_and_alignment(self):
        import torch

        arrays = self._arrays()
        for card_width, relic_width in ((2, 1), (0, 0),
                                        (base.MAX_CARDS, 1), (2, base.MAX_RELICS)):
            with self.subTest(cards=card_width, relics=relic_width):
                arrays["card_mask"][:] = False
                arrays["relic_mask"][:] = False
                arrays["card_mask"][0, :card_width] = True
                arrays["relic_mask"][1, :relic_width] = True
                # A gap must not cause the last valid token to be discarded.
                if card_width > 2:
                    arrays["card_mask"][0, 1] = False
                values = base._torch_inputs(arrays, np.arange(2), "cpu", torch,
                                            trim_padding=True)
                for data_index, mask_index, data, mask, width in (
                    (2, 5, "cards", "card_mask", card_width),
                    (3, 6, "relics", "relic_mask", relic_width),
                ):
                    self.assertEqual(values[data_index].shape[1], width)
                    torch.testing.assert_close(values[data_index], torch.from_numpy(arrays[data][:, :width]))
                    torch.testing.assert_close(values[mask_index], torch.from_numpy(arrays[mask][:, :width]))
                    self.assertEqual(int(values[mask_index].sum()), int(arrays[mask].sum()))
                for index, key in ((0, "globals_continuous"), (1, "global_categories"), (4, "potions")):
                    torch.testing.assert_close(values[index], torch.from_numpy(arrays[key]))
                self.assertEqual(values[4].shape[1], 5)

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_padded_trimmed_forward_loss_and_gradient_parity(self):
        import argparse
        import torch

        torch.set_num_threads(1)
        args = argparse.Namespace(threads=1, training_seed=17)
        spec = {"maxHpDeltaValues": [0, 3], "relicDeltaValues": [0, 1]}
        for name in ("phase2", "point"):
            for widths in ((2, 1), (0, 0), (base.MAX_CARDS, 1), (2, base.MAX_RELICS)):
                with self.subTest(model=name, widths=widths):
                    arrays = self._arrays()
                    for key, width in zip(("card_mask", "relic_mask"), widths):
                        arrays[key][:] = False
                        arrays[key][0, :width] = True
                    arrays["y_relic_mask"] = arrays["relic_mask"].copy()
                    # Nontrivial last relic label detects target misalignment.
                    if widths[1]:
                        arrays["relic_delta_index"][0, widths[1] - 1] = 1
                    ids = np.arange(2)
                    model = ablation._new_model(name, arrays, spec, ids, args, "cpu")
                    model.net.eval()  # Disable dropout; gradients remain enabled.
                    padded = base._torch_inputs(arrays, ids, "cpu", torch)
                    trimmed = base._torch_inputs(arrays, ids, "cpu", torch, trim_padding=True)
                    with torch.no_grad():
                        torch.testing.assert_close(model.net.encoder(*padded), model.net.encoder(*trimmed), atol=1e-6, rtol=1e-6)
                        reference = model.net(*padded)
                        actual = model.net(*trimmed)
                        for index, (left, right) in enumerate(zip(reference, actual)):
                            if name == "phase2" and index == 4:
                                left = left[:, :widths[1]]
                            torch.testing.assert_close(left, right, atol=1e-6, rtol=1e-6)
                    losses = []
                    gradients = []
                    for trim in (False, True):
                        model.net.zero_grad(set_to_none=True)
                        loss = (base._phase2_loss(model, arrays, ids, args, trim_padding=trim)
                                if name == "phase2" else
                                base._point_loss(model, arrays, ids, trim_padding=trim))
                        loss.backward()
                        losses.append(loss.detach())
                        gradients.append({key: param.grad.clone() for key, param in model.net.named_parameters() if param.grad is not None})
                    torch.testing.assert_close(*losses, atol=1e-6, rtol=1e-6)
                    self.assertEqual(gradients[0].keys(), gradients[1].keys())
                    for key in gradients[0]:
                        torch.testing.assert_close(gradients[0][key], gradients[1][key], atol=1e-6, rtol=1e-5, msg=key)

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_trim_rejects_active_relic_target_outside_input(self):
        import argparse

        arrays = self._arrays()
        args = argparse.Namespace(threads=1, training_seed=17)
        spec = {"maxHpDeltaValues": [0, 3], "relicDeltaValues": [0, 1]}
        ids = np.arange(2)
        model = ablation._new_model("phase2", arrays, spec, ids, args, "cpu")
        arrays["y_relic_mask"][0, -1] = True
        with self.assertRaisesRegex(ValueError, "active relic target outside"):
            base._phase2_loss(model, arrays, ids, args, trim_padding=True)

    def test_source_bootstrap_reports_phase2_minus_control(self):
        arrays = {
            "y_win": np.asarray([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int8),
            "y_hp": np.asarray([np.nan, .4, np.nan, .5, np.nan, .6, np.nan, .7], dtype=np.float32),
            "sourceSeed": np.asarray([1, 1, 2, 2, 3, 3, 4, 4], dtype=np.int64),
        }
        phase2 = {
            "pWin": np.asarray([.1, .8, .2, .7, .3, .6, .4, .5]),
            "expectedHpFraction": np.asarray([0, .4, 0, .5, 0, .6, 0, .7]),
        }
        point = {
            "pWin": np.asarray([.2, .9, .1, .8, .2, .7, .3, .6]),
            "expectedHpFraction": np.asarray([0, .5, 0, .6, 0, .7, 0, .8]),
        }
        result = ablation._source_bootstrap_core_deltas(
            arrays, np.arange(8), phase2, point, repetitions=100, seed=19
        )
        self.assertEqual(result["sourceGroups"], 4)
        self.assertEqual(result["repetitions"], 100)
        self.assertIn("survivalBrier", result["metrics"])
        self.assertIn("sourceBootstrap95", result["metrics"]["survivalLogLoss"])


if __name__ == "__main__":
    unittest.main()
