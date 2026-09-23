import unittest

import numpy as np
import torch

from tools import combat_transition_deepset_potion_specialist as specialist
from tools import combat_transition_potion_trajectory as trajectory
from tools.combat_transition_model_experiment import CONTINUOUS_GLOBAL_FIELDS


class DeepSetPotionSpecialistTests(unittest.TestCase):
    def test_frozen_source_accepts_only_pinned_head_and_cli_assertions(self):
        expected_head = specialist.EXPECTED["experimentCommit"]
        expected_base = specialist.EXPECTED["baselineCommit"]
        specialist.validate_frozen_source(expected_head, expected_base, expected_head)

        caller_head = "f" * 40
        with self.assertRaisesRegex(ValueError, "experiment SHA assertion mismatch"):
            specialist.validate_frozen_source(caller_head, expected_base, caller_head)
        with self.assertRaisesRegex(ValueError, "baseline SHA mismatch"):
            specialist.validate_frozen_source(expected_head, caller_head, expected_head)
        with self.assertRaisesRegex(ValueError, "checkout mismatch"):
            specialist.validate_frozen_source(caller_head, expected_base, expected_head)

    def arrays(self, rows=4):
        return {
            "globals_continuous": np.zeros((rows, len(CONTINUOUS_GLOBAL_FIELDS)), np.float32),
            "global_categories": np.zeros((rows, 4), np.int64),
            "cards": np.zeros((rows, 1, 4), np.int16),
            "relics": np.zeros((rows, 1, 3), np.int16),
            "potions": np.zeros((rows, 5, 2), np.int16),
            "card_mask": np.zeros((rows, 1), np.bool_),
            "relic_mask": np.zeros((rows, 1), np.bool_),
        }

    def test_trainable_encoder_and_decoder_get_finite_nonzero_gradients(self):
        arrays = self.arrays()
        arrays["potions"][:, :, 0] = np.arange(5, dtype=np.int16)
        arrays["potions"][:, :, 1] = 1
        arrays["potions"][:, 0, 1] = 39
        encoder = specialist.new_encoder(arrays, np.arange(4))
        decoder = trajectory.new_decoder(3)
        cache = {
            "ids": np.arange(4, dtype=np.int64),
            "mask": np.zeros(4, dtype=np.int64),
            "potions": np.asarray([[39, 1, 1, 1, 1]] * 4, dtype=np.int64),
            "capacity": np.full(4, 3, dtype=np.int64),
            "delta": np.zeros(4, dtype=np.int64),
            "trueHp": np.ones(4, dtype=np.float32),
            "trueMax": np.ones(4, dtype=np.float32),
            "boss": np.zeros(4, dtype=bool),
        }
        loss = specialist.row_losses(encoder, decoder, arrays, cache, {}, np.arange(2), "cpu").mean()
        loss.backward()
        for name, module in (("encoder", encoder), ("decoder", decoder)):
            grads = [p.grad for p in module.parameters() if p.grad is not None]
            self.assertTrue(grads, name)
            self.assertTrue(all(torch.isfinite(g).all() for g in grads), name)
            self.assertTrue(any(torch.any(g != 0) for g in grads), name)

    def test_warm_encoder_load_is_exact(self):
        arrays = self.arrays()
        encoder = specialist.new_encoder(arrays, np.arange(4))
        source = {f"encoder.{key}": value.clone() for key, value in encoder.state_dict().items()}
        expected_encoder = specialist.module_sha(encoder.state_dict())
        decoder = trajectory.new_decoder(3)
        decoder_source = {key: value.clone() for key, value in decoder.state_dict().items()}
        expected_decoder = specialist.module_sha(decoder_source)
        warm_encoder = {"stateDict": source}
        warm_decoder = {"stateDict": decoder_source}
        with torch.no_grad():
            for parameter in encoder.parameters():
                parameter.add_(1)
        warm_e, warm_d = specialist.make_arm("W", arrays, np.arange(4), 3,
                                             warm_encoder, warm_decoder, "cpu")
        self.assertEqual(specialist.module_sha(warm_e.state_dict()), expected_encoder)
        self.assertEqual(specialist.module_sha(warm_d.state_dict()), expected_decoder)

    def test_scratch_initialization_and_batch_orders_are_deterministic(self):
        arrays = self.arrays()
        first, _ = specialist.make_arm("S", arrays, np.arange(4), 3, {}, {}, "cpu")
        second, _ = specialist.make_arm("S", arrays, np.arange(4), 3, {}, {}, "cpu")
        self.assertEqual(specialist.module_sha(first.state_dict()), specialist.module_sha(second.state_dict()))
        train = np.arange(32, dtype=np.int64)
        orders_a, hash_a = specialist.fixed_orders(train)
        orders_b, hash_b = specialist.fixed_orders(train)
        self.assertEqual(hash_a, hash_b)
        self.assertEqual(len(orders_a), specialist.RECIPE["maximumEpochs"])
        for left, right in zip(orders_a, orders_b):
            np.testing.assert_array_equal(left, right)

    def test_frozen_population_selects_only_winning_train_and_validation_rows(self):
        cache = {"win": np.asarray([1, 1, 1, 1, 0, 1], dtype=bool),
                 "split": np.asarray([0, 1, 2, 2, 0, 1], dtype=np.int8)}
        train, validation = specialist.frozen_population(cache)
        np.testing.assert_array_equal(train, np.asarray([0]))
        np.testing.assert_array_equal(validation, np.asarray([1, 5]))
        self.assertFalse(np.isin(np.concatenate((train, validation)), [2, 3]).any())

    def test_native_input_adapter_preserves_entity_and_slot_contract(self):
        arrays = self.arrays()
        arrays["cards"][0, 0] = [17, 1, 2, 0]
        arrays["card_mask"][0, 0] = True
        arrays["relics"][0, 0] = [26, 2, 0]
        arrays["relic_mask"][0, 0] = True
        arrays["potions"][0] = np.asarray([[0, 39], [1, 21], [2, 1], [3, 1], [4, 1]])
        cache = {"ids": np.arange(4, dtype=np.int64)}
        encoder = specialist.new_encoder(arrays, np.arange(4)).eval()
        actual = specialist.encode(encoder, arrays, cache, np.asarray([0]), "cpu")
        inputs = specialist.composed.base._torch_inputs(arrays, np.asarray([0]), "cpu", torch,
                                                        trim_padding=True)
        with torch.inference_mode():
            expected = encoder(*inputs)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)

    def test_legal_probabilities_are_normalized_and_illegal_mass_is_zero(self):
        net = trajectory.new_decoder(3).eval()
        z = torch.zeros((2, 64))
        inventory = np.asarray([[39, 1, 1, 1, 1], [21, 1, 1, 1, 1]], np.int64)
        capacity = np.asarray([3, 3])
        delta = np.zeros(2, np.int64)
        hp = np.ones(2, np.float32)
        boss = np.asarray([False, True])
        with torch.inference_mode():
            probabilities = trajectory.log_probabilities(net, z, inventory, capacity, delta, hp, boss).exp().numpy()
        for row in range(2):
            mask = trajectory.decoder.legal_masks(inventory[row:row + 1], capacity[row:row + 1])[0]
            trigger = np.isin(inventory[row], [trajectory.BREW, trajectory.SMOKE])
            trigger_count = (trajectory.decoder.BITS & trigger).sum(-1)
            expected = mask & (trigger_count <= 1)
            use = expected & ((trajectory.decoder.BITS & trigger).sum(-1) > 0)
            if boss[row] and trajectory.SMOKE in inventory[row]:
                use &= ~np.any(trajectory.decoder.BITS & (inventory[row] == trajectory.SMOKE), axis=-1)
            legal = np.concatenate((expected, use))
            np.testing.assert_array_equal(trajectory.legal_actions(inventory[row], int(capacity[row]), bool(boss[row])), legal)
            self.assertTrue(np.array_equal(probabilities[row, ~legal], np.zeros(np.sum(~legal))))
            self.assertAlmostEqual(float(probabilities[row].sum()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
