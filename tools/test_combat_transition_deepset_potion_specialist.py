import unittest
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import torch

from tools import combat_transition_deepset_potion_specialist as specialist
from tools import reproduce_combat_transition_deepset_potion_blind as potion_blind_reproduce
from tools import reproduce_combat_transition_deepset_potion_specialist as reproduce
from tools import combat_transition_potion_trajectory as trajectory
from tools.combat_transition_model_experiment import CONTINUOUS_GLOBAL_FIELDS


class DeepSetPotionSpecialistTests(unittest.TestCase):
    def test_reproduction_wrapper_checks_actual_git_checkout(self):
        repo_root = Path(__file__).resolve().parents[1]
        actual_head = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
        ).strip()
        self.assertNotEqual(actual_head, reproduce.EXPECTED_EXPERIMENT_SHA)
        with self.assertRaisesRegex(ValueError, "experiment source worktree must be checked out"):
            reproduce.validate_source_worktree(repo_root)

    def test_reproduction_command_supplies_fixed_provenance(self):
        args = type("Args", (), {
            "artifact_root": Path("/tmp/artifacts"),
            "output_dir": Path("/tmp/output"),
            "encoder_checkpoint": Path("/tmp/encoder.pt"),
            "decoder_checkpoint": Path("/tmp/decoder.pt"),
            "dedicated_component": Path("/tmp/component.pt"),
            "reference_receipt": Path("/tmp/reference.json"),
        })()
        command = reproduce.build_command(Path("/tmp/frozen-source"), args)
        self.assertEqual(command[-4:], [
            "--base-sha", reproduce.EXPECTED_BASE_SHA,
            "--experiment-sha", reproduce.EXPECTED_EXPERIMENT_SHA,
        ])
        self.assertEqual(command[1], "-s")

    def test_potion_blind_wrapper_pins_baseline_and_source_checkout(self):
        args = type("Args", (), {
            "artifact_root": Path("/tmp/artifacts"),
            "output_dir": Path("/tmp/output"),
            "encoder_checkpoint": Path("/tmp/encoder.pt"),
            "decoder_checkpoint": Path("/tmp/decoder.pt"),
            "dedicated_component": Path("/tmp/component.pt"),
            "reference_receipt": Path("/tmp/reference.json"),
            "reference_decoder": Path("/tmp/reference.pt"),
        })()
        command = potion_blind_reproduce.build_command(
            Path("/tmp/source"), "reviewed-sha", args)
        self.assertEqual(command[-4:], [
            "--base-sha", potion_blind_reproduce.EXPECTED_BASE_SHA,
            "--experiment-sha", "reviewed-sha"])
        self.assertEqual(command[command.index("--reference-decoder") + 1],
                         "/tmp/reference.pt")

    def test_reproduction_child_imports_validated_tree_despite_bogus_pythonpath(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            validated_root = temp_root / "validated"
            bogus_root = temp_root / "bogus"
            for root, marker in ((validated_root, "validated"), (bogus_root, "bogus")):
                tools = root / "tools"
                tools.mkdir(parents=True)
                (tools / "__init__.py").write_text("")
                (tools / "path_probe.py").write_text(f"SOURCE = {marker!r}\n")

            env = reproduce.child_environment(validated_root, {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(bogus_root),
                "PYTHONHOME": str(bogus_root),
            })
            self.assertEqual(env["PYTHONPATH"], str(validated_root))
            self.assertEqual(env["PYTHONNOUSERSITE"], "1")
            self.assertNotIn("PYTHONHOME", env)
            loaded = subprocess.check_output(
                [sys.executable, "-s", "-c",
                 "import tools.path_probe as p; print(p.__file__); print(p.SOURCE)"],
                cwd=temp_root, env=env, text=True,
            ).splitlines()
            self.assertEqual(Path(loaded[0]).resolve(), validated_root / "tools/path_probe.py")
            self.assertEqual(loaded[1], "validated")

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
        control_e, control_d = specialist.make_arm("C", arrays, np.arange(4), 3,
                                                    warm_encoder, warm_decoder, "cpu")
        blind_e, blind_d = specialist.make_arm("P", arrays, np.arange(4), 3,
                                                warm_encoder, warm_decoder, "cpu")
        self.assertEqual(specialist.module_sha(control_e.state_dict()),
                         specialist.module_sha(blind_e.state_dict()))
        self.assertEqual(specialist.module_sha(control_d.state_dict()),
                         specialist.module_sha(blind_d.state_dict()))

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

    def test_potion_blind_encoder_is_invariant_only_to_potion_inventory(self):
        arrays = self.arrays(rows=2)
        arrays["globals_continuous"][:, 0] = [10, 10]
        arrays["cards"][:, 0] = np.asarray([[17, 1, 2, 0], [17, 1, 2, 0]])
        arrays["card_mask"][:, 0] = True
        arrays["relics"][:, 0] = np.asarray([[26, 2, 0], [26, 2, 0]])
        arrays["relic_mask"][:, 0] = True
        arrays["potions"][:, :, 0] = np.arange(5, dtype=np.int16)
        arrays["potions"][:, :, 1] = 1
        arrays["potions"][0, 0, 1] = 17
        arrays["potions"][1, 0, 1] = 27
        ordinary = specialist.new_encoder(arrays, np.arange(2)).eval()
        blind = specialist.new_encoder(arrays, np.arange(2), potion_blind=True).eval()
        blind.load_state_dict(ordinary.state_dict(), strict=True)
        cache = {"ids": np.arange(2, dtype=np.int64)}
        with torch.inference_mode():
            z = specialist.encode(blind, arrays, cache, np.arange(2), "cpu")
            ordinary_z = specialist.encode(ordinary, arrays, cache, np.arange(2), "cpu")
        torch.testing.assert_close(z[0], z[1], rtol=1e-6, atol=1e-7)
        self.assertFalse(torch.equal(ordinary_z[0], ordinary_z[1]))

        changed = {key: value.copy() for key, value in arrays.items()}
        changed["cards"][1, 0, 0] = 18
        changed_cache = {"ids": np.arange(2, dtype=np.int64)}
        with torch.inference_mode():
            card_changed = specialist.encode(blind, changed, changed_cache,
                                              np.asarray([1]), "cpu")
        self.assertFalse(torch.equal(z[0], card_changed[0]))

        changed = {key: value.copy() for key, value in arrays.items()}
        changed["relics"][1, 0, 0] = 27
        with torch.inference_mode():
            relic_changed = specialist.encode(blind, changed, changed_cache,
                                               np.asarray([1]), "cpu")
        self.assertFalse(torch.equal(z[0], relic_changed[0]))

        changed = {key: value.copy() for key, value in arrays.items()}
        changed["globals_continuous"][1, 0] += 1
        with torch.inference_mode():
            global_changed = specialist.encode(blind, changed, changed_cache,
                                                np.asarray([1]), "cpu")
        self.assertFalse(torch.equal(z[0], global_changed[0]))

        with torch.no_grad():
            for parameter in list(blind.potion_id.parameters()) + list(blind.potion_slot.parameters()) + list(blind.potion_mlp.parameters()):
                parameter.add_(100)
            bypassed_changed = specialist.encode(blind, arrays, cache,
                                                  np.asarray([0]), "cpu")
        torch.testing.assert_close(z[:1], bypassed_changed, rtol=1e-6, atol=1e-7)

    def test_potion_blind_arm_excludes_only_bypassed_encoder_parameters(self):
        arrays = self.arrays()
        arrays["globals_continuous"][:] = 0
        source = specialist.new_encoder(arrays, np.arange(4))
        warm = {"stateDict": {f"encoder.{key}": value.clone()
                              for key, value in source.state_dict().items()}}
        decoder = trajectory.new_decoder(3)
        warm_decoder = {"stateDict": {key: value.clone()
                                      for key, value in decoder.state_dict().items()}}
        candidate, _ = specialist.make_arm("P", arrays, np.arange(4), 3,
                                           warm, warm_decoder, "cpu")
        bypassed = {"potion_id", "potion_slot", "potion_mlp"}
        for name, parameter in candidate.named_parameters():
            if name.split(".", 1)[0] in bypassed:
                self.assertFalse(parameter.requires_grad, name)
            else:
                self.assertTrue(parameter.requires_grad, name)

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

    def test_decoder_keeps_current_inventory_dependence_for_fixed_z(self):
        net = trajectory.new_decoder(3).eval()
        z = torch.zeros((1, 64))
        capacity = np.asarray([3])
        delta = np.zeros(1, np.int64)
        hp = np.ones(1, np.float32)
        boss = np.zeros(1, dtype=bool)
        ordinary = np.asarray([[21, 1, 1, 1, 1]], np.int64)
        recursive_brew_node = np.asarray([[27, 17, 1, 1, 1]], np.int64)
        with torch.inference_mode():
            ordinary_p = trajectory.log_probabilities(
                net, z, ordinary, capacity, delta, hp, boss).exp()
            brew_p = trajectory.log_probabilities(
                net, z, recursive_brew_node, capacity, delta, hp, boss).exp()
        self.assertFalse(torch.equal(ordinary_p, brew_p))
        legal = trajectory.legal_actions(recursive_brew_node[0], int(capacity[0]), False)
        self.assertEqual(float(brew_p[0, ~torch.as_tensor(legal)].sum()), 0.0)


if __name__ == "__main__":
    unittest.main()
