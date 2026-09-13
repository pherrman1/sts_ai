#!/usr/bin/env python3
"""Run the frozen Phase-1 attention ablation for the Phase-2 surrogate.

This is an offline, one-variable ablation of
``tools/combat_transition_surrogate.py``.  It reuses the prepared arrays,
target support, losses, transition metrics, sampler, and source-group split
from the merged DeepSets Phase-2 pipeline.  The only model change is the
corrected Phase-1 typed-token attention encoder:

* width 64, two Transformer encoder layers, four heads, FF width 128;
* GLOBAL, CARD, RELIC, and POTION typed tokens;
* categorical global embeddings, explicit relic order, and explicit potion
  slots;
* no arbitrary positional embeddings for exchangeable card tokens.

The runner never invokes the simulator, collects data, consumes combat RNG,
or writes deployable runtime artifacts.  Checkpoints and evidence are written
to the caller-provided external output directory.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import math
import time
from pathlib import Path

import numpy as np

try:
    from tools import combat_transition_surrogate as base
except ModuleNotFoundError:  # direct invocation from tools/
    import combat_transition_surrogate as base


SCRIPT_SCHEMA = "combat_transition_attention_ablation_v1"
MODEL_SCHEMA = "combat_transition_surrogate_attention_model_v1"
EXPECTED_CORPUS_SHA256 = "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde"
EXPECTED_SPLIT_SHA256 = "e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32"
EXPECTED_SUPPORTED_ROWS = 413_799


class AttentionEncoder:
    """The corrected PR #161 Phase-1 attention representation."""

    def __init__(self, torch, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn

        self.torch = torch
        self.nn = nn
        self.scalar_mean = torch.tensor(scalar_mean, dtype=torch.float32)
        self.scalar_inv = torch.tensor(1.0 / np.maximum(scalar_std, 1e-6), dtype=torch.float32)

        class Encoder(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.outer = outer
                self.register_buffer("scalar_mean", outer.scalar_mean)
                self.register_buffer("scalar_inv", outer.scalar_inv)
                d = 64
                self.card_id = nn.Embedding(base.CARD_COUNT, d)
                self.relic_id = nn.Embedding(base.RELIC_COUNT, d)
                self.potion_id = nn.Embedding(base.POTION_COUNT, d)
                self.type_embedding = nn.Embedding(4, d)
                self.global_category = nn.ModuleList(
                    nn.Embedding(base.GLOBAL_CATEGORY_COUNTS[field], 8)
                    for field in ("characterClass", "encounter", "roomClass", "lastRoom")
                )
                self.global_proj = nn.Linear(
                    len(base.CONTINUOUS_GLOBAL_FIELDS) + 8 * 4, d
                )
                self.card_fields = nn.Linear(3, d)
                self.relic_fields = nn.Linear(2, d)
                self.potion_slot = nn.Embedding(5, d)
                layer = nn.TransformerEncoderLayer(
                    d_model=d,
                    nhead=4,
                    dim_feedforward=128,
                    dropout=0.1,
                    batch_first=True,
                    activation="gelu",
                )
                self.encoder = nn.TransformerEncoder(layer, num_layers=2)
                self.trunk = nn.Sequential(nn.Linear(d, 64), nn.ReLU())

            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.outer.torch
                d = 64
                gs = (g - self.scalar_mean.to(g.device)) * self.scalar_inv.to(g.device)
                global_categories = t.cat(
                    [embedding(gc[:, index].long())
                     for index, embedding in enumerate(self.global_category)], -1
                )
                global_token = self.global_proj(
                    t.cat((gs, global_categories), -1)
                ).unsqueeze(1) + self.type_embedding.weight[0]

                card_fields = t.cat(
                    (
                        c[:, :, 1:2].float(),
                        c[:, :, 2:3].float().clamp(-20, 20) / 20,
                        c[:, :, 3:4].float() / 3,
                    ),
                    -1,
                )
                card_tokens = (
                    self.card_id(c[:, :, 0].long())
                    + self.card_fields(card_fields)
                    + self.type_embedding.weight[1]
                )

                relic_fields = t.cat(
                    (r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1
                )
                relic_tokens = (
                    self.relic_id(r[:, :, 0].long())
                    + self.relic_fields(relic_fields)
                    + self.type_embedding.weight[2]
                )

                potion_tokens = (
                    self.potion_id(p[:, :, 1].long())
                    + self.potion_slot(p[:, :, 0].long())
                    + self.type_embedding.weight[3]
                )
                tokens = t.cat((global_token, card_tokens, relic_tokens, potion_tokens), 1)
                padding = t.cat(
                    (
                        t.zeros((g.shape[0], 1), dtype=t.bool, device=g.device),
                        ~cmask,
                        ~rmask,
                        t.zeros((g.shape[0], 5), dtype=t.bool, device=g.device),
                    ),
                    1,
                )
                encoded = self.encoder(tokens, src_key_padding_mask=padding)[:, 0]
                return self.trunk(encoded)

        self.net = Encoder(self)


class AttentionPhase2Net:
    def __init__(self, torch, target_spec: dict, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn

        self.torch = torch
        self.nn = nn
        self.encoder = AttentionEncoder(torch, scalar_mean, scalar_std)
        delta_count = len(target_spec["maxHpDeltaValues"])
        relic_delta_count = len(target_spec["relicDeltaValues"])

        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.torch = outer.torch
                self.encoder = outer.encoder.net
                self.survival = nn.Linear(64, 1)
                self.max_hp_delta = nn.Linear(64, delta_count)
                self.hp_delta_embedding = nn.Embedding(delta_count, 8)
                self.hp = nn.Sequential(
                    nn.Linear(64 + 8, 64), nn.ReLU(), nn.Linear(64, base.HP_BIN_COUNT)
                )
                self.potion_slot = nn.Embedding(5, 8)
                self.potion = nn.Linear(64 + 8, base.POTION_COUNT)
                self.relic_token_id = nn.Embedding(base.RELIC_COUNT, 16)
                self.relic = nn.Sequential(
                    nn.Linear(64 + 16 + 2, 64),
                    nn.ReLU(),
                    nn.Linear(64, relic_delta_count),
                )

            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.torch
                z = self.encoder(g, gc, c, r, p, cmask, rmask)
                survival = self.survival(z).squeeze(-1)
                delta = self.max_hp_delta(z)
                hp_inputs = t.cat(
                    (
                        z[:, None, :].expand(-1, delta_count, -1),
                        self.hp_delta_embedding.weight[None, :, :].expand(
                            z.shape[0], -1, -1
                        ),
                    ),
                    -1,
                )
                hp = self.hp(hp_inputs)
                slot = self.potion_slot.weight[None, :, :].expand(z.shape[0], -1, -1)
                potion = self.potion(
                    t.cat((z[:, None, :].expand(-1, 5, -1), slot), -1)
                )
                relic_ids = r[:, :, 0].long()
                relic_data = t.cat(
                    (r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1
                )
                relic_inputs = t.cat(
                    (
                        z[:, None, :].expand(-1, r.shape[1], -1),
                        self.relic_token_id(relic_ids),
                        relic_data,
                    ),
                    -1,
                )
                relic = self.relic(relic_inputs)
                return survival, delta, hp, potion, relic

        self.net = Net(self)


class AttentionPointControlNet:
    def __init__(self, torch, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn

        self.torch = torch
        self.nn = nn
        self.encoder = AttentionEncoder(torch, scalar_mean, scalar_std)

        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.encoder = outer.encoder.net
                self.survival = nn.Linear(64, 1)
                self.hp = nn.Linear(64, 1)

            def forward(self, g, gc, c, r, p, cmask, rmask):
                z = self.encoder(g, gc, c, r, p, cmask, rmask)
                return self.survival(z).squeeze(-1), self.hp(z).squeeze(-1)

        self.net = Net(self)


def _new_model(name: str, arrays: dict, target_spec: dict,
               train_indices: np.ndarray, args: argparse.Namespace, device: str):
    import torch

    torch.set_num_threads(args.threads)
    torch.manual_seed(args.training_seed)
    if device == "cuda":
        torch.cuda.manual_seed_all(args.training_seed)
    scalar_mean = arrays["globals_continuous"][train_indices].mean(0)
    scalar_std = arrays["globals_continuous"][train_indices].std(0)
    if name == "phase2":
        wrapper = AttentionPhase2Net(torch, target_spec, scalar_mean, scalar_std)
    elif name == "point":
        wrapper = AttentionPointControlNet(torch, scalar_mean, scalar_std)
    else:
        raise ValueError(f"unknown attention model {name}")
    wrapper.device = torch.device(device)
    wrapper.net = wrapper.net.to(wrapper.device)
    return wrapper


AMP_INITIAL_SCALE = 16_384


def _training_protocol(precision: str) -> dict:
    if precision not in ("fp32", "amp-fp16"):
        raise ValueError(f"unknown training precision: {precision}")
    return {
        "trainingPrecision": precision,
        "ampDtype": "float16" if precision == "amp-fp16" else None,
        "gradScalerEnabled": precision == "amp-fp16",
        "gradScalerInitialScale": AMP_INITIAL_SCALE if precision == "amp-fp16" else None,
        "gradientUnscaleBeforeClipping": precision == "amp-fp16",
        "evaluationPrecision": "fp32",
    }


def _validate_training_precision(torch, precision: str, device: str) -> None:
    _training_protocol(precision)
    if precision == "amp-fp16" and (
        torch.device(device).type != "cuda" or not torch.cuda.is_available()
    ):
        raise ValueError("--training-precision amp-fp16 requires an available CUDA device")


class _TrainingStep:
    """Shared selection/refit step; FP32 never creates an AMP context or scaler."""

    def __init__(self, torch, precision: str, device: str):
        _validate_training_precision(torch, precision, device)
        self.torch = torch
        self.scaler = (
            torch.amp.GradScaler("cuda", init_scale=AMP_INITIAL_SCALE)
            if precision == "amp-fp16" else None
        )

    def __call__(self, name, wrapper, optimizer, arrays, batch_ids, args):
        context = (
            self.torch.autocast(device_type="cuda", dtype=self.torch.float16)
            if self.scaler is not None else nullcontext()
        )
        with context:
            loss = (
                base._phase2_loss(wrapper, arrays, batch_ids, args, trim_padding=True)
                if name == "phase2" else
                base._point_loss(wrapper, arrays, batch_ids, trim_padding=True)
            )
        optimizer.zero_grad(set_to_none=True)
        if self.scaler is None:
            loss.backward()
        else:
            self.scaler.scale(loss).backward()
            self.scaler.unscale_(optimizer)
        self.torch.nn.utils.clip_grad_norm_(wrapper.net.parameters(), 1.0)
        if self.scaler is None:
            optimizer.step()
        else:
            self.scaler.step(optimizer)
            self.scaler.update()
        return loss


def _train_one(name: str, arrays: dict, target_spec: dict,
               train_indices: np.ndarray, val_indices: np.ndarray,
               args: argparse.Namespace, device: str):
    import torch

    step = _TrainingStep(torch, getattr(args, "training_precision", "fp32"), device)
    wrapper = _new_model(name, arrays, target_spec, train_indices, args, device)
    optimizer = torch.optim.AdamW(wrapper.net.parameters(), lr=1e-3, weight_decay=1e-4)
    rng = np.random.default_rng(args.training_seed)
    best_state = None
    best_score = math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, args.nn_epochs + 1):
        wrapper.net.train()
        losses = []
        for batch_ids in base._batches(train_indices, args.nn_batch, rng):
            loss = step(name, wrapper, optimizer, arrays, batch_ids, args)
            losses.append(float(loss.detach().cpu()))
        metrics = base._evaluate_core(
            wrapper, arrays, target_spec, val_indices, args.nn_batch, name
        )
        score = (
            metrics["survival"]["brier"]
            + metrics["winningExpectedHpFraction"]["mae"]
            + metrics["jointAliveHpFraction"]["mae"]
        )
        print(
            json.dumps(
                {
                    "family": name,
                    "epoch": epoch,
                    "loss": float(np.mean(losses)),
                    "validationScore": score,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if score < best_score:
            best_state = base._safe_state_dict(wrapper.net)
            best_score = score
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
            if stale >= args.nn_patience:
                break
    if best_state is None:
        raise RuntimeError(f"{name} produced no validation checkpoint")
    wrapper.net.load_state_dict(best_state)
    return wrapper, base._evaluate_core(
        wrapper, arrays, target_spec, val_indices, args.nn_batch, name
    ), best_epoch


def _refit_one(name: str, arrays: dict, target_spec: dict,
               train_indices: np.ndarray, epochs: int,
               args: argparse.Namespace, device: str):
    import torch

    step = _TrainingStep(torch, getattr(args, "training_precision", "fp32"), device)
    wrapper = _new_model(name, arrays, target_spec, train_indices, args, device)
    optimizer = torch.optim.AdamW(wrapper.net.parameters(), lr=1e-3, weight_decay=1e-4)
    rng = np.random.default_rng(args.training_seed)
    for _ in range(epochs):
        for batch_ids in base._batches(train_indices, args.nn_batch, rng):
            loss = step(name, wrapper, optimizer, arrays, batch_ids, args)
    return wrapper


def _relative_delta(delta: float, control: float) -> float | None:
    return None if control == 0 else float(delta / control)


def _source_bootstrap_core_deltas(arrays: dict, indices: np.ndarray,
                                  phase2: dict, point: dict,
                                  repetitions: int, seed: int) -> dict:
    """Bootstrap Phase-2 minus point-control core errors by source seed."""
    from sklearn.metrics import roc_auc_score

    y = arrays["y_win"][indices].astype(np.int8)
    target_frac = np.nan_to_num(arrays["y_hp"][indices], nan=0.0)
    p2 = np.asarray(phase2["pWin"], dtype=np.float64)
    pc = np.asarray(point["pWin"], dtype=np.float64)
    h2 = np.asarray(phase2["expectedHpFraction"], dtype=np.float64)
    hc = np.asarray(point["expectedHpFraction"], dtype=np.float64)
    p2 = np.clip(p2, 1e-8, 1 - 1e-8)
    pc = np.clip(pc, 1e-8, 1 - 1e-8)
    row_values = {
        "survivalBrier": (
            (p2 - y) ** 2,
            (pc - y) ** 2,
        ),
        "survivalLogLoss": (
            -(y * np.log(p2) + (1 - y) * np.log1p(-p2)),
            -(y * np.log(pc) + (1 - y) * np.log1p(-pc)),
        ),
        "winningExpectedHpFractionMae": (
            np.abs(h2 - target_frac),
            np.abs(hc - target_frac),
        ),
        "jointAliveHpFractionMae": (
            np.abs(p2 * h2 - y * target_frac),
            np.abs(pc * hc - y * target_frac),
        ),
    }
    winning = y == 1
    group_values, group_index = np.unique(
        arrays["sourceSeed"][indices], return_inverse=True
    )
    if len(group_values) < 2:
        raise ValueError("source bootstrap requires at least two source groups")

    def auc_for(values: np.ndarray, weights: np.ndarray) -> float | None:
        if np.sum(weights[y == 0]) <= 0 or np.sum(weights[y == 1]) <= 0:
            return None
        return float(roc_auc_score(y, values, sample_weight=weights))

    rng = np.random.default_rng(seed)
    samples = {name: [] for name in row_values}
    samples["survivalAuc"] = []
    for _ in range(repetitions):
        selected = rng.integers(0, len(group_values), size=len(group_values))
        multiplicity = np.bincount(
            selected, minlength=len(group_values)
        ).astype(np.float64)
        weights = multiplicity[group_index]
        for name, (p2_values, pc_values) in row_values.items():
            if name == "winningExpectedHpFractionMae":
                mask = winning
            else:
                mask = np.ones(len(y), dtype=bool)
            denominator = float(weights[mask].sum())
            if denominator <= 0:
                continue
            samples[name].append(
                float(
                    np.sum(weights[mask] * p2_values[mask]) / denominator
                    - np.sum(weights[mask] * pc_values[mask]) / denominator
                )
            )
        p2_auc = auc_for(p2, weights)
        pc_auc = auc_for(pc, weights)
        if p2_auc is not None and pc_auc is not None:
            samples["survivalAuc"].append(p2_auc - pc_auc)

    point_values = {
        "survivalBrier": float(np.mean(row_values["survivalBrier"][0]) - np.mean(row_values["survivalBrier"][1])),
        "survivalLogLoss": float(np.mean(row_values["survivalLogLoss"][0]) - np.mean(row_values["survivalLogLoss"][1])),
        "survivalAuc": float(
            roc_auc_score(y, p2) - roc_auc_score(y, pc)
        ),
        "winningExpectedHpFractionMae": float(
            np.mean(row_values["winningExpectedHpFractionMae"][0][winning])
            - np.mean(row_values["winningExpectedHpFractionMae"][1][winning])
        ),
        "jointAliveHpFractionMae": float(
            np.mean(row_values["jointAliveHpFractionMae"][0])
            - np.mean(row_values["jointAliveHpFractionMae"][1])
        ),
    }
    control_values = {
        "survivalBrier": float(np.mean(row_values["survivalBrier"][1])),
        "survivalLogLoss": float(np.mean(row_values["survivalLogLoss"][1])),
        "survivalAuc": float(roc_auc_score(y, pc)),
        "winningExpectedHpFractionMae": float(
            np.mean(row_values["winningExpectedHpFractionMae"][1][winning])
        ),
        "jointAliveHpFractionMae": float(np.mean(row_values["jointAliveHpFractionMae"][1])),
    }
    result = {
        "sourceGroups": int(len(group_values)),
        "repetitions": int(repetitions),
        "seed": int(seed),
        "direction": "Phase-2 minus attention point-control; positive error deltas favor point-control",
        "metrics": {},
    }
    for name, delta in point_values.items():
        values = np.asarray(samples[name], dtype=np.float64)
        if len(values) < max(100, repetitions // 2):
            raise RuntimeError(f"insufficient bootstrap samples for {name}: {len(values)}")
        result["metrics"][name] = {
            "phase2MinusPointControl": delta,
            "relativeToPointControl": _relative_delta(delta, control_values.get(name, 0.0)),
            "sourceBootstrap95": {
                "lower": float(np.quantile(values, 0.025)),
                "upper": float(np.quantile(values, 0.975)),
            },
        }
    return result


def _core_decision(core_bootstrap: dict) -> dict:
    """Apply the handoff's conservative CI-based core-regression rule."""
    metrics = core_bootstrap["metrics"]
    primary = (metrics["survivalBrier"], metrics["survivalLogLoss"])
    hp = (
        metrics["winningExpectedHpFractionMae"],
        metrics["jointAliveHpFractionMae"],
    )
    primary_regression = any(item["sourceBootstrap95"]["lower"] > 0 for item in primary)
    hp_regression = any(item["sourceBootstrap95"]["lower"] > 0 for item in hp)
    primary_nonworse = all(item["sourceBootstrap95"]["upper"] <= 0 for item in primary)
    hp_nonworse = all(item["sourceBootstrap95"]["upper"] <= 0 for item in hp)
    if primary_regression or hp_regression:
        classification = "ATTENTION_CORE_REGRESSION"
    elif primary_nonworse and hp_nonworse:
        classification = "ATTENTION_AVOIDS_CORE_REGRESSION"
    else:
        classification = "ATTENTION_CORE_INCONCLUSIVE"
    return {
        "classification": classification,
        "rule": (
            "Classify regression when a source-seed 95% CI for any primary "
            "survival or HP error delta is strictly above zero; classify avoids "
            "only when all primary and HP error CIs are at or below zero; "
            "otherwise classify inconclusive. No absolute Brier offset is used."
        ),
        "primaryRegressionEvidence": primary_regression,
        "hpRegressionEvidence": hp_regression,
    }


def _compact_support(audit: dict) -> dict:
    boundary = audit["supportBoundary"]
    return {
        "rows": boundary["rows"],
        "amongDeaths": boundary["amongDeaths"],
        "byAct": boundary["byAct"],
        "byRoomClass": boundary["byRoomClass"],
        "fallbackReasons": boundary["fallbackReasons"],
        "mutationAudit": audit["intentionalOmittedMutationCoverage"],
        "goldMutationSourceAudit": audit["goldMutationSourceAudit"],
        "copyThroughAudit": audit["copyThroughAudit"],
        "predicate": boundary["predicate"],
        "learnedInputSchema": boundary["learnedInputSchema"],
        "adapterOnlyPreCombatFields": boundary["adapterOnlyPreCombatFields"],
    }


def _measure_latency(wrapper, arrays: dict, index: int) -> float:
    import torch

    wrapper.net.eval()
    ids = np.asarray([index], dtype=np.int64)
    values = base._torch_inputs(arrays, ids, wrapper.device, torch)
    with torch.no_grad():
        for _ in range(10):
            wrapper.net(*values)
        if wrapper.device.type == "cuda":
            torch.cuda.synchronize(wrapper.device)
        start = time.perf_counter()
        for _ in range(50):
            wrapper.net(*values)
        if wrapper.device.type == "cuda":
            torch.cuda.synchronize(wrapper.device)
    return float((time.perf_counter() - start) * 1000 / 50)


def _load_checkpoint(name: str, path: Path, arrays: dict, target_spec: dict,
                     train_indices: np.ndarray, args: argparse.Namespace,
                     device: str):
    import torch

    if not path.is_file():
        raise FileNotFoundError(f"checkpoint for recovery does not exist: {path}")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    expected_family = "phase2" if name == "phase2" else "point_control"
    if payload.get("family") != expected_family or payload.get("encoder") != "phase1_attention":
        raise ValueError(f"checkpoint is not the expected attention {expected_family} model: {path}")
    if name == "phase2" and payload.get("targetSpec") != target_spec:
        raise ValueError("Phase-2 recovery checkpoint target specification differs")
    # Historical attention checkpoints predate precision metadata and used FP32.
    recorded = payload.get("trainingProtocol", _training_protocol("fp32"))
    if recorded != _training_protocol(getattr(args, "training_precision", "fp32")):
        raise ValueError("recovery checkpoint training precision/protocol differs from requested precision")
    wrapper = _new_model(name, arrays, target_spec, train_indices, args, device)
    wrapper.net.load_state_dict(payload["stateDict"])
    return wrapper


def fit(args: argparse.Namespace) -> None:
    import torch

    device = base._resolve_device(torch, args.device)
    precision = getattr(args, "training_precision", "fp32")
    _validate_training_precision(torch, precision, device)
    training_protocol = _training_protocol(precision)
    prepared_dir = Path(args.prepared_dir)
    arrays, target_spec = base._load_prepared(prepared_dir)
    prepared_manifest = json.loads(
        (prepared_dir / "prepared_manifest.json").read_text(encoding="utf-8")
    )
    if prepared_manifest.get("corpusSha256") != EXPECTED_CORPUS_SHA256:
        raise ValueError("prepared artifact is not the frozen Phase-2 corpus")
    if prepared_manifest.get("counts", {}).get("supported") != EXPECTED_SUPPORTED_ROWS:
        raise ValueError("prepared artifact does not use the final Phase-2 support boundary")
    base._prepare_target_indices(arrays, target_spec)
    all_train = np.flatnonzero((arrays["split_id"] == 0) & arrays["supported"])
    all_val = np.flatnonzero((arrays["split_id"] == 1) & arrays["supported"])
    all_test = np.flatnonzero((arrays["split_id"] == 2) & arrays["supported"])
    for label, indices in (("train", all_train), ("validation", all_val), ("test", all_test)):
        support = base._validate_target_support(arrays, target_spec, indices, label)
        if not support["ok"]:
            raise ValueError(
                f"unseen target support in {label}: {json.dumps(support['unseen'], sort_keys=True)}"
            )
    print(
        json.dumps(
            {
                "device": device,
                "supportedRows": {
                    "train": len(all_train),
                    "validation": len(all_val),
                    "test": len(all_test),
                },
            },
            sort_keys=True,
        ),
        flush=True,
    )

    combined = np.concatenate((all_train, all_val))
    if args.reuse_checkpoints:
        required_recovery_args = {
            "--reuse-phase2-checkpoint": args.reuse_phase2_checkpoint,
            "--reuse-point-checkpoint": args.reuse_point_checkpoint,
            "--reuse-phase2-epochs": args.reuse_phase2_epochs,
            "--reuse-point-epochs": args.reuse_point_epochs,
            "--reuse-phase2-selection-score": args.reuse_phase2_selection_score,
            "--reuse-point-selection-score": args.reuse_point_selection_score,
        }
        missing = [name for name, value in required_recovery_args.items() if value is None]
        if missing:
            raise ValueError(
                "checkpoint recovery requires: " + ", ".join(missing)
            )
        phase2_epochs = int(args.reuse_phase2_epochs)
        point_epochs = int(args.reuse_point_epochs)
        phase2 = _load_checkpoint(
            "phase2", Path(args.reuse_phase2_checkpoint), arrays, target_spec,
            combined, args, device
        )
        point = _load_checkpoint(
            "point", Path(args.reuse_point_checkpoint), arrays, target_spec,
            combined, args, device
        )
        phase2_val_metrics = {
            "selectedEpochs": phase2_epochs,
            "selectionScore": args.reuse_phase2_selection_score,
            "selectionEvidence": "recovered from exact final refit checkpoint; no validation or TEST tuning",
        }
        point_val_metrics = {
            "selectedEpochs": point_epochs,
            "selectionScore": args.reuse_point_selection_score,
            "selectionEvidence": "recovered from exact final refit checkpoint; no validation or TEST tuning",
        }
    else:
        phase2_val_model, phase2_val, phase2_epochs = _train_one(
            "phase2", arrays, target_spec, all_train, all_val, args, device
        )
        point_val_model, point_val, point_epochs = _train_one(
            "point", arrays, target_spec, all_train, all_val, args, device
        )
        del phase2_val_model, point_val_model
        phase2_val_metrics = {key: value for key, value in phase2_val.items() if key != "predictions"}
        point_val_metrics = {key: value for key, value in point_val.items() if key != "predictions"}
        phase2 = _refit_one(
            "phase2", arrays, target_spec, combined, phase2_epochs, args, device
        )
        point = _refit_one(
            "point", arrays, target_spec, combined, point_epochs, args, device
        )
    phase2_test = base._evaluate_core(
        phase2, arrays, target_spec, all_test, args.nn_batch, "phase2"
    )
    point_test = base._evaluate_core(
        point, arrays, target_spec, all_test, args.nn_batch, "point"
    )
    phase2_predictions = phase2_test.pop("predictions")
    # Point-control predictions are intentionally obtained through the same
    # helper used by the merged Phase-2 evaluator.
    point_win, point_hp = base._point_predict(point, arrays, all_test, args.nn_batch)
    point_predictions = {
        "pWin": point_win,
        "expectedHpFraction": point_hp,
    }
    phase2_test["hpDistribution"] = base._hp_distribution_metrics(
        arrays,
        all_test,
        phase2_predictions["pHpBins"],
        point_fraction=point_hp,
    )
    core_bootstrap = _source_bootstrap_core_deltas(
        arrays,
        all_test,
        {
            "pWin": phase2_predictions["pWin"],
            "expectedHpFraction": phase2_predictions["expectedHpFraction"],
        },
        point_predictions,
        args.bootstrap_reps,
        args.bootstrap_seed,
    )
    transition = base._transition_metrics(
        arrays, target_spec, all_test, phase2_predictions, len(all_test)
    )
    fixtures = json.loads(
        (prepared_dir / "sampling_fixtures.json").read_text(encoding="utf-8")
    )
    sampling = base._sampled_state_check(
        arrays, target_spec, fixtures, all_test, phase2_predictions, args
    )
    if not sampling["valid"]:
        raise ValueError(
            "sampled surrogate states failed validity gate: "
            + json.dumps(sampling, sort_keys=True)
        )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    phase2_model_path = out / "phase2_attention.pt"
    point_model_path = out / "point_control_attention.pt"
    if not args.reuse_checkpoints:
        torch.save(
            {
                "schemaVersion": MODEL_SCHEMA,
                "family": "phase2",
                "encoder": "phase1_attention",
                "trainingProtocol": training_protocol,
                "stateDict": base._safe_state_dict(phase2.net),
                "targetSpec": target_spec,
            },
            phase2_model_path,
        )
        torch.save(
            {
                "schemaVersion": MODEL_SCHEMA,
                "family": "point_control",
                "encoder": "phase1_attention",
                "trainingProtocol": training_protocol,
                "stateDict": base._safe_state_dict(point.net),
            },
            point_model_path,
        )
    elif not phase2_model_path.is_file() or not point_model_path.is_file():
        raise FileNotFoundError(
            "checkpoint recovery expects the exact checkpoints in output-dir: "
            f"{phase2_model_path} and {point_model_path}"
        )
    phase2_latency = _measure_latency(phase2, arrays, int(all_test[0]))
    point_latency = _measure_latency(point, arrays, int(all_test[0]))
    attention_params = int(sum(value.numel() for value in phase2.net.parameters()))
    point_params = int(sum(value.numel() for value in point.net.parameters()))
    evidence = {
        "schemaVersion": SCRIPT_SCHEMA,
        "modelSchema": MODEL_SCHEMA,
        "baselineHeadSha": args.baseline_head_sha,
        "frozenCorpusSha256": EXPECTED_CORPUS_SHA256,
        "frozenSourceSplitSha256": EXPECTED_SPLIT_SHA256,
        "preparedManifest": str((prepared_dir / "prepared_manifest.json").resolve()),
        "preparedManifestSha256": base.sha256(prepared_dir / "prepared_manifest.json"),
        "support": _compact_support(
            json.loads((prepared_dir / "support_audit.json").read_text(encoding="utf-8"))
        ),
        "targets": target_spec,
        "encoder": {
            "name": "phase1_attention",
            "width": 64,
            "transformerLayers": 2,
            "heads": 4,
            "feedForwardWidth": 128,
            "typedTokens": ["GLOBAL", "CARD", "RELIC", "POTION"],
            "explicitRelicOrder": True,
            "explicitPotionSlot": True,
            "categoricalGlobalEmbeddings": True,
            "arbitraryPositionalEmbeddings": False,
            "learnedInputSchema": "combat_predictor_input_v1",
            "adapterOnlyPreCombatFields": ["pre.smokeBombUsed", "pre.stolenGold"],
        },
        "protocol": {
            **training_protocol,
            "train": "supported TRAIN rows only",
            "validation": "supported VALIDATION rows only; early stopping and epoch freeze",
            "finalFit": "supported TRAIN+VALIDATION rows, exact frozen epoch count, from scratch",
            "test": "supported fixed TEST rows, evaluated once after final refit",
            "trainingSeed": int(args.training_seed),
            "bootstrapSeed": int(args.bootstrap_seed),
            "samplingSeed": int(args.sampling_seed),
            "device": device,
            "threads": int(args.threads),
            "batch": int(args.nn_batch),
            "maxEpochs": int(args.nn_epochs),
            "patience": int(args.nn_patience),
            "optimizer": "AdamW(lr=1e-3, weight_decay=1e-4)",
            "loss": "merged Phase-2 losses and weights; no task balancing or schedules",
            "noTestTuning": True,
            "noNewData": True,
            "noRngInputs": True,
            "recoveredFromExactCheckpoints": bool(args.reuse_checkpoints),
        },
        "counts": {
            "supportedTrain": int(len(all_train)),
            "supportedValidation": int(len(all_val)),
            "supportedTest": int(len(all_test)),
            "combinedFit": int(len(combined)),
        },
        "validation": {
            "phase2": {**phase2_val_metrics, "selectedEpochs": int(phase2_epochs)},
            "pointControl": {**point_val_metrics, "selectedEpochs": int(point_epochs)},
        },
        "test": {
            "phase2": phase2_test,
            "pointControl": point_test,
            "transition": transition,
            "corePhase2MinusPointControl": core_bootstrap,
            "testSplitNote": "fixed engineering TEST; not a fresh representation-selection holdout",
        },
        "artifacts": {
            "phase2Model": {
                "path": str(phase2_model_path.resolve()),
                "bytes": phase2_model_path.stat().st_size,
                "sha256": base.sha256(phase2_model_path),
                "parameters": attention_params,
            },
            "pointControlModel": {
                "path": str(point_model_path.resolve()),
                "bytes": point_model_path.stat().st_size,
                "sha256": base.sha256(point_model_path),
                "parameters": point_params,
            },
            "batch1LatencyMsOnFitDevice": phase2_latency,
            "pointControlBatch1LatencyMsOnFitDevice": point_latency,
        },
        "sampling": sampling,
        "rngContract": {
            "combatRngIncluded": False,
            "statement": "combatRng[6] is neither an input nor a learned/copied output; a separate continuation contract remains required",
        },
        "frozenDeepSetsComparison": {
            "source": "PR #162 merged Phase-2 fit evidence",
            "phase2": {
                "survivalBrier": 0.020879680290818214,
                "survivalLogLoss": 0.07047025114297867,
                "winningExpectedHpFractionMae": 0.07184544950723648,
                "jointAliveHpFractionMae": 0.07917144894599915,
                "hpDiscreteCrps": 0.048483915627002716,
                "potionVectorExact": 0.4609834915704301,
                "relicVectorExact": 0.7739672837495929,
                "batch1LatencyMs": 0.3916,
            },
            "pointControl": {
                "survivalBrier": 0.018935929983854294,
                "survivalLogLoss": 0.06365569680929184,
                "winningExpectedHpFractionMae": 0.07250324636697769,
                "jointAliveHpFractionMae": 0.07893349975347519,
                "hpPointControlDegenerateCrps": 0.07182192802429199,
                "batch1LatencyMs": 0.2989,
            },
        },
    }
    evidence["decision"] = _core_decision(core_bootstrap)
    base.json_dump(out / "attention_ablation_evidence.json", evidence)
    print(
        json.dumps(
            {
                "classification": evidence["decision"]["classification"],
                "phase2Epochs": phase2_epochs,
                "pointControlEpochs": point_epochs,
                "phase2Parameters": attention_params,
                "pointControlParameters": point_params,
                "phase2ModelBytes": phase2_model_path.stat().st_size,
                "pointControlModelBytes": point_model_path.stat().st_size,
                "batch1LatencyMsOnFitDevice": phase2_latency,
                "pointControlBatch1LatencyMsOnFitDevice": point_latency,
                "output": str(out.resolve()),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fit_parser = sub.add_parser("fit")
    fit_parser.add_argument("--prepared-dir", required=True)
    fit_parser.add_argument("--output-dir", required=True)
    fit_parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    fit_parser.add_argument("--training-precision", choices=("fp32", "amp-fp16"), default="fp32")
    fit_parser.add_argument("--threads", type=int, default=8)
    fit_parser.add_argument("--nn-batch", type=int, default=2048)
    fit_parser.add_argument("--nn-epochs", type=int, default=12)
    fit_parser.add_argument("--nn-patience", type=int, default=3)
    fit_parser.add_argument("--training-seed", type=int, default=20260912)
    fit_parser.add_argument("--bootstrap-seed", type=int, default=20260913)
    fit_parser.add_argument("--bootstrap-reps", type=int, default=1000)
    fit_parser.add_argument("--sampling-seed", type=int, default=20260914)
    fit_parser.add_argument("--reuse-checkpoints", action="store_true")
    fit_parser.add_argument("--reuse-phase2-checkpoint")
    fit_parser.add_argument("--reuse-point-checkpoint")
    fit_parser.add_argument("--reuse-phase2-epochs", type=int)
    fit_parser.add_argument("--reuse-point-epochs", type=int)
    fit_parser.add_argument("--reuse-phase2-selection-score", type=float, default=None)
    fit_parser.add_argument("--reuse-point-selection-score", type=float, default=None)
    fit_parser.add_argument(
        "--baseline-head-sha",
        default="6ccad271eefa5d42ea0d2debe4ff6bed486aa3f9",
    )
    fit_parser.set_defaults(func=fit)
    return parser


def main() -> None:
    args = _parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
