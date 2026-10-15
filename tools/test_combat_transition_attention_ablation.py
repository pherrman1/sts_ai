import importlib.util
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import sys

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

    @unittest.skipUnless(TORCH_AVAILABLE, "optional research dependency torch is not installed")
    def test_cuda_amp_optimizer_smoke(self):
        import torch
        import argparse

        if not torch.cuda.is_available():
            self.skipTest("CUDA is unavailable")
        args = argparse.Namespace(threads=1, training_seed=17)
        spec = {"maxHpDeltaValues": [0, 3], "relicDeltaValues": [0, 1]}
        arrays = self._arrays()
        ids = np.arange(2)
        for family in ("phase2", "point"):
            with self.subTest(family=family):
                wrapper = ablation._new_model(family, arrays, spec, ids, args, "cuda")
                wrapper.net.train()
                before = {name: value.detach().clone() for name, value in wrapper.net.named_parameters()}
                optimizer = torch.optim.AdamW(wrapper.net.parameters(), lr=1e-3, weight_decay=1e-4)
                step = ablation._TrainingStep(torch, "amp-fp16", "cuda")
                loss = step(family, wrapper, optimizer, arrays, ids, args)
                self.assertTrue(bool(torch.isfinite(loss)))
                self.assertTrue(all(bool(torch.isfinite(p.grad).all()) for p in wrapper.net.parameters() if p.grad is not None))
                self.assertTrue(any(not torch.equal(before[name], value) for name, value in wrapper.net.named_parameters()))
                self.assertTrue(all(int(state["step"]) == 1 for state in optimizer.state.values()))
                self.assertEqual(step.scaler.get_scale(), 16384)
                self.assertEqual(step.scaler.state_dict()["_growth_tracker"], 1)

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


class TestTrainingPrecision(unittest.TestCase):
    def test_cli_default_and_explicit_precision(self):
        command = ["fit", "--prepared-dir", "unused", "--output-dir", "unused"]
        self.assertEqual(ablation._parser().parse_args(command).training_precision, "fp32")
        self.assertEqual(ablation._parser().parse_args(command + ["--training-precision", "amp-fp16"]).training_precision, "amp-fp16")

    def _torch(self, device="cuda", available=True):
        torch = MagicMock()
        torch.device.side_effect = lambda value: SimpleNamespace(type=value.split(":")[0])
        torch.cuda.is_available.return_value = available
        return torch

    def test_amp_requires_cuda(self):
        for device, available in (("cpu", True), ("cuda", False), ("cpu", False)):
            with self.subTest(device=device, available=available):
                torch = self._torch(device, available)
                with self.assertRaisesRegex(ValueError, "requires an available CUDA"):
                    ablation._TrainingStep(torch, "amp-fp16", device)
                torch.amp.GradScaler.assert_not_called()
        ablation._TrainingStep(self._torch(), "amp-fp16", "cuda:0")

    def test_step_order_and_fp32_isolation(self):
        for precision in ("fp32", "amp-fp16"):
            for family in ("phase2", "point"):
                with self.subTest(precision=precision, family=family):
                    torch = self._torch()
                    events = []
                    scaler = torch.amp.GradScaler.return_value
                    loss = MagicMock()
                    loss.backward.side_effect = lambda: events.append("backward")
                    scaler.scale.side_effect = lambda value: (events.append("scale") or value)
                    scaler.unscale_.side_effect = lambda opt: events.append("unscale")
                    scaler.step.side_effect = lambda opt: events.append("scaler_step")
                    scaler.update.side_effect = lambda: events.append("update")
                    torch.nn.utils.clip_grad_norm_.side_effect = lambda params, limit: events.append("clip")
                    optimizer = MagicMock()
                    optimizer.zero_grad.side_effect = lambda **kw: events.append("zero")
                    optimizer.step.side_effect = lambda: events.append("step")
                    wrapper = SimpleNamespace(net=MagicMock())
                    context = torch.autocast.return_value
                    context.__enter__.side_effect = lambda: events.append("autocast_enter")
                    context.__exit__.side_effect = lambda *a: events.append("autocast_exit")
                    def compute(*a, **kw):
                        events.append("loss")
                        self.assertTrue(kw["trim_padding"])
                        return loss
                    with patch.object(base, "_phase2_loss", side_effect=compute) as phase2, patch.object(base, "_point_loss", side_effect=compute) as point:
                        step = ablation._TrainingStep(torch, precision, "cuda")
                        self.assertIs(step(family, wrapper, optimizer, {}, np.arange(2), SimpleNamespace()), loss)
                        self.assertEqual(phase2.call_count, int(family == "phase2"))
                        self.assertEqual(point.call_count, int(family == "point"))
                    optimizer.zero_grad.assert_called_once_with(set_to_none=True)
                    torch.nn.utils.clip_grad_norm_.assert_called_once_with(wrapper.net.parameters.return_value, 1.0)
                    if precision == "fp32":
                        self.assertEqual(events, ["loss", "zero", "backward", "clip", "step"])
                        torch.amp.GradScaler.assert_not_called()
                        torch.autocast.assert_not_called()
                    else:
                        self.assertEqual(events, ["autocast_enter", "loss", "autocast_exit", "zero", "scale", "backward", "unscale", "clip", "scaler_step", "update"])
                        torch.amp.GradScaler.assert_called_once_with("cuda", init_scale=16384)
                        torch.autocast.assert_called_once_with(device_type="cuda", dtype=torch.float16)
                        scaler.unscale_.assert_called_once_with(optimizer)
                        scaler.step.assert_called_once_with(optimizer)
                        optimizer.step.assert_not_called()

    def test_selection_and_refit_share_precision_and_evaluation_stays_outside(self):
        arrays = {}
        ids = np.arange(2)
        metrics = {"survival": {"brier": .1}, "winningExpectedHpFraction": {"mae": .1}, "jointAliveHpFraction": {"mae": .1}}
        for precision in ("fp32", "amp-fp16"):
            for family in ("phase2", "point"):
                args = SimpleNamespace(training_precision=precision, training_seed=7, nn_epochs=1, nn_batch=2, nn_patience=1)
                torch = self._torch()
                wrapper = SimpleNamespace(net=MagicMock())
                with patch.dict(sys.modules, torch=torch), patch.object(ablation, "_new_model", return_value=wrapper), patch.object(ablation, "_TrainingStep") as step, patch.object(base, "_evaluate_core", return_value=metrics) as evaluate, patch.object(base, "_safe_state_dict", return_value={}):
                    step.return_value.return_value.detach.return_value.cpu.return_value = .5
                    ablation._train_one(family, arrays, {}, ids, ids, args, "cuda")
                    ablation._refit_one(family, arrays, {}, ids, 1, args, "cuda")
                    self.assertEqual(step.call_args_list, [unittest.mock.call(torch, precision, "cuda")] * 2)
                    self.assertEqual(step.return_value.call_count, 2)
                    self.assertEqual(evaluate.call_count, 2)
                    torch.autocast.assert_not_called()

    def test_precision_metadata(self):
        fp32 = ablation._training_protocol("fp32")
        self.assertEqual(fp32["trainingPrecision"], "fp32")
        self.assertFalse(fp32["gradScalerEnabled"])
        amp = ablation._training_protocol("amp-fp16")
        self.assertEqual(amp, {
            "trainingPrecision": "amp-fp16", "ampDtype": "float16",
            "gradScalerEnabled": True, "gradScalerInitialScale": 16384,
            "gradientUnscaleBeforeClipping": True, "evaluationPrecision": "fp32",
        })

    def test_fit_writes_precision_to_evidence_and_both_checkpoints(self):
        import json
        import tempfile
        from pathlib import Path
        from contextlib import ExitStack

        arrays = {"split_id": np.arange(3), "supported": np.ones(3, dtype=bool)}
        for precision in ("fp32", "amp-fp16"):
            with self.subTest(precision=precision), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "prepared_manifest.json").write_text(json.dumps({
                    "corpusSha256": ablation.EXPECTED_CORPUS_SHA256,
                    "counts": {"supported": ablation.EXPECTED_SUPPORTED_ROWS},
                }))
                for filename in ("sampling_fixtures.json", "support_audit.json"):
                    (root / filename).write_text("{}")
                args = ablation._parser().parse_args([
                    "fit", "--prepared-dir", directory, "--output-dir", directory,
                    "--training-precision", precision,
                ])
                torch = self._torch()
                torch.save.side_effect = lambda payload, path: path.write_bytes(b"checkpoint")
                wrapper = SimpleNamespace(net=MagicMock(), device=SimpleNamespace(type="cuda"))
                metrics = {"survival": {"brier": .1}, "winningExpectedHpFraction": {"mae": .1}, "jointAliveHpFraction": {"mae": .1}}
                predictions = {"pHpBins": np.zeros((1, 101)), "pWin": np.ones(1), "expectedHpFraction": np.ones(1)}
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(sys.modules, torch=torch))
                    replacements = {
                        "_load_prepared": (arrays, {}), "_prepare_target_indices": None,
                        "_validate_target_support": {"ok": True}, "_resolve_device": "cuda",
                        "_point_predict": (np.ones(1), np.ones(1)), "_hp_distribution_metrics": {},
                        "_transition_metrics": {}, "_sampled_state_check": {"valid": True},
                        "_safe_state_dict": {},
                    }
                    for name, value in replacements.items():
                        stack.enter_context(patch.object(base, name, return_value=value))
                    stack.enter_context(patch.object(base, "_evaluate_core", side_effect=lambda *a: {**metrics, "predictions": predictions.copy()}))
                    evidence = stack.enter_context(patch.object(base, "json_dump"))
                    train = stack.enter_context(patch.object(ablation, "_train_one", return_value=(wrapper, metrics, 1)))
                    refit = stack.enter_context(patch.object(ablation, "_refit_one", return_value=wrapper))
                    for name in ("_source_bootstrap_core_deltas", "_compact_support", "_core_decision"):
                        stack.enter_context(patch.object(ablation, name, return_value={"classification": "mock"}))
                    stack.enter_context(patch.object(ablation, "_measure_latency", return_value=1.0))
                    stack.enter_context(patch("builtins.print"))
                    ablation.fit(args)
                    protocol = ablation._training_protocol(precision)
                    written = evidence.call_args.args[1]["protocol"]
                    for key, value in protocol.items():
                        self.assertEqual(written[key], value)
                    self.assertEqual(torch.save.call_count, 2)
                    for call in torch.save.call_args_list:
                        self.assertEqual(call.args[0]["trainingProtocol"], protocol)
                        self.assertEqual(call.args[0]["schemaVersion"], ablation.MODEL_SCHEMA)
                    self.assertEqual(train.call_count, 2)
                    self.assertEqual(refit.call_count, 2)
                    for call in train.call_args_list + refit.call_args_list:
                        self.assertEqual(call.args[-2].training_precision, precision)

    def test_checkpoint_recovery_rejects_precision_mismatch(self):
        from pathlib import Path
        import tempfile
        torch = self._torch()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.pt"
            path.touch()
            for recorded in (None, "fp32", "amp-fp16"):
                for requested in ("fp32", "amp-fp16"):
                    payload = {"family": "point_control", "encoder": "phase1_attention", "stateDict": {}}
                    if recorded is not None:
                        payload["trainingProtocol"] = ablation._training_protocol(recorded)
                    torch.load.return_value = payload
                    with patch.dict(sys.modules, torch=torch), patch.object(ablation, "_new_model") as model:
                        if (recorded or "fp32") == requested:
                            ablation._load_checkpoint("point", path, {}, {}, np.arange(2), SimpleNamespace(training_precision=requested), "cuda")
                            model.return_value.net.load_state_dict.assert_called_once_with({})
                        else:
                            with self.assertRaisesRegex(ValueError, "precision/protocol differs"):
                                ablation._load_checkpoint("point", path, {}, {}, np.arange(2), SimpleNamespace(training_precision=requested), "cuda")
                            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
