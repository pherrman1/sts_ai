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
