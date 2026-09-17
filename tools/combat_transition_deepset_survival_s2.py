#!/usr/bin/env python3
"""Matched tiny nonlinear survival decoders over frozen S1b embeddings."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_deepset_survival as screen
from tools import combat_transition_deepset_survival_s1b as scale


BASELINE_SHA = "7370ccdd35a79e5b55991e646fe3587762f02718"
SCREEN_OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-survival-screen-20260916-final")
REPRESENTATION = Path("/home/philippherrmann/sts_sweep/runs/deepset-downstream-20260916-corrected")
S1B_EVIDENCE = ROOT / "docs/experiments/evidence/deepset_survival_s1b_2026-09-17.json"
OUTPUT = Path("/tmp/deepset-survival-s2-20260917")
RECIPE = {
    "seed": 20260912,
    "epochs": 12,
    "batch": 512,
    "precision": "fp32",
    "optimizer": "AdamW",
    "lr": 1e-3,
    "weightDecay": 1e-4,
    "gradientClip": 1.0,
    "selection": "earliest strict minimum VALIDATION log loss",
    "architecture": "Linear(64,64) -> ReLU -> Linear(64,1)",
    "testInferenceRows": 0,
}


def module_digest(module: torch.nn.Module) -> str:
    hasher = hashlib.sha256()
    for key, value in sorted(module.state_dict().items()):
        value = value.detach().cpu().contiguous()
        hasher.update(key.encode())
        hasher.update(str(value.dtype).encode())
        hasher.update(json.dumps(list(value.shape), separators=(",", ":")).encode())
        hasher.update(value.numpy().tobytes())
    return hasher.hexdigest()


def new_head() -> torch.nn.Module:
    return torch.nn.Sequential(
        torch.nn.Linear(64, 64),
        torch.nn.ReLU(),
        torch.nn.Linear(64, 1),
    )


def assert_optimizer_scope(head: torch.nn.Module, optimizer: torch.optim.Optimizer) -> None:
    expected = {id(parameter) for parameter in head.parameters()}
    actual = {id(parameter) for group in optimizer.param_groups for parameter in group["params"]}
    if actual != expected:
        raise ValueError("optimizer contains parameters outside the nonlinear survival head")


def objective(head: torch.nn.Module, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    return torch.nn.functional.binary_cross_entropy_with_logits(head(features).flatten(), labels)


def smoke(head: torch.nn.Module, features: torch.Tensor, labels: torch.Tensor) -> dict:
    head.train()
    head.zero_grad(set_to_none=True)
    loss = objective(head, features[:8], labels[:8])
    if not torch.isfinite(loss):
        raise ValueError("nonfinite S2 smoke loss")
    loss.backward()
    gradients = [parameter.grad for parameter in head.parameters()]
    if not all(gradient is not None and torch.isfinite(gradient).all() for gradient in gradients):
        raise ValueError("invalid S2 smoke gradients")
    head.zero_grad(set_to_none=True)
    return {"rows": min(8, len(features)), "finite": True, "finiteGradients": True, "optimizerScope": True}


def fit_arm(name: str, initial_state: dict, features: np.ndarray, labels: np.ndarray,
            validation_features: np.ndarray, validation_labels: np.ndarray,
            orders: list[np.ndarray], device: str, output: Path) -> dict:
    head = new_head().to(device)
    head.load_state_dict(copy.deepcopy(initial_state), strict=True)
    optimizer = torch.optim.AdamW(head.parameters(), lr=RECIPE["lr"], weight_decay=RECIPE["weightDecay"])
    assert_optimizer_scope(head, optimizer)
    train_features = torch.from_numpy(features).to(device)
    train_labels = torch.from_numpy(labels.astype(np.float32)).to(device)
    validation_features_tensor = torch.from_numpy(validation_features).to(device)
    validation_labels_tensor = torch.from_numpy(validation_labels.astype(np.float32)).to(device)
    smoke_result = smoke(head, train_features, train_labels)
    history = []
    best_nll = float("inf")
    selected_epoch = None
    selected_state = None
    started = time.monotonic()
    for epoch, order in enumerate(orders, start=1):
        head.train()
        train_losses = []
        for start in range(0, len(order), RECIPE["batch"]):
            batch = order[start : start + RECIPE["batch"]]
            optimizer.zero_grad(set_to_none=True)
            loss = objective(head, train_features[batch], train_labels[batch])
            if not torch.isfinite(loss):
                raise ValueError(f"nonfinite {name} S2 training loss at epoch {epoch}")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(head.parameters(), RECIPE["gradientClip"])
            if not torch.isfinite(norm):
                raise ValueError(f"nonfinite {name} S2 gradient norm at epoch {epoch}")
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        head.eval()
        with torch.inference_mode():
            validation_logits = head(validation_features_tensor).flatten()
            validation_nll = float(torch.nn.functional.binary_cross_entropy_with_logits(
                validation_logits, validation_labels_tensor
            ).cpu())
        record = {
            "epoch": epoch,
            "trainingNll": float(np.mean(train_losses)),
            "validationNll": validation_nll,
        }
        history.append(record)
        print(json.dumps({"arm": name, **record}, sort_keys=True), flush=True)
        if validation_nll < best_nll:
            best_nll = validation_nll
            selected_epoch = epoch
            selected_state = copy.deepcopy(head.state_dict())
    if selected_state is None:
        raise RuntimeError(f"{name} produced no selected S2 head")
    checkpoint = output / f"head_{name.lower()}.pt"
    torch.save({"stateDict": selected_state, "recipe": RECIPE, "selectedEpoch": selected_epoch}, checkpoint)
    head.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=False)["stateDict"], strict=True)
    return {
        "name": name,
        "selectedEpoch": selected_epoch,
        "history": history,
        "checkpoint": str(checkpoint),
        "checkpointSha256": screen.digest(checkpoint),
        "stateSha256": module_digest(head),
        "trainingSeconds": time.monotonic() - started,
        "smoke": smoke_result,
        "head": head,
    }


def run(args: argparse.Namespace) -> dict:
    if screen.current_head() != args.base_sha:
        raise ValueError(f"current baseline differs: {screen.current_head()} != {args.base_sha}")
    if args.output.exists():
        raise ValueError(f"refusing overwrite of {args.output}")
    args.output.mkdir(parents=True)
    cache, preparation = screen.load_cache(args)
    arrays, _ = screen.load_prepared()
    if not np.array_equal(cache["source"], arrays["sourceSeed"]):
        raise ValueError("cache source ids do not match prepared source ids")
    target = np.flatnonzero(cache["split"] < 2).astype(np.int64)
    train = np.flatnonzero(cache["split"] == 0).astype(np.int64)
    validation = np.flatnonzero(cache["split"] == 1).astype(np.int64)
    train_positions = np.searchsorted(target, train)
    validation_positions = np.searchsorted(target, validation)
    attention_z = np.load(args.screen_output / "z_attention.npy", mmap_mode="r")
    row_ids = np.load(args.screen_output / "z_row_ids.npy", mmap_mode="r")
    if not np.array_equal(row_ids, cache["ids"][target]) or tuple(attention_z.shape) != (len(target), 64):
        raise ValueError("saved Attention representation identity or shape differs")
    deepset_z, representation = screen.load_candidate_representation(args, cache, target)
    s1b = json.loads(args.s1b_evidence.read_text(encoding="utf-8"))
    normalized = {}
    for name, values in (("A", attention_z), ("B", deepset_z)):
        statistics = s1b["normalization"][name]
        mean = np.asarray(statistics["trainMean"], dtype=np.float64)
        scale_std = np.asarray(statistics["scaleStd"], dtype=np.float64)
        normalized[name] = scale.normalize_representation(values, mean, scale_std)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RECIPE["seed"])
    initial_head = new_head()
    initial_state = copy.deepcopy(initial_head.state_dict())
    initial_digest = module_digest(initial_head)
    orders_rng = np.random.default_rng(RECIPE["seed"])
    orders = [orders_rng.permutation(len(train)).astype(np.int64) for _ in range(RECIPE["epochs"])]
    order_hasher = hashlib.sha256()
    for order in orders:
        order_hasher.update(np.ascontiguousarray(order).tobytes())
    batch_order_sha = order_hasher.hexdigest()
    arm_a = fit_arm("A", initial_state, normalized["A"][train_positions], cache["win"][train],
                    normalized["A"][validation_positions], cache["win"][validation], orders, device, args.output)
    arm_b = fit_arm("B", initial_state, normalized["B"][train_positions], cache["win"][train],
                    normalized["B"][validation_positions], cache["win"][validation], orders, device, args.output)
    metrics_a = screen.metrics(arm_a["head"], normalized["A"], cache, validation, device, validation_positions)
    metrics_b = screen.metrics(arm_b["head"], normalized["B"], cache, validation, device, validation_positions)
    slices = screen.validation_slices(arm_a["head"], arm_b["head"], normalized["A"], normalized["B"],
                                      cache, target, validation, device)
    result = {
        "schema": "deepset_survival_s2_v1",
        "decision": "S2_NONLINEAR_DIAGNOSTIC",
        "interpretation": "one matched tiny nonlinear decoder over frozen S1b-normalized embeddings; no acceptance gate added",
        "baselineSha": args.base_sha,
        "sourceSha": screen.SOURCE_SHA,
        "corpusSha256": screen.CORPUS_SHA,
        "provenance": {
            "preparationCacheSha256": screen.PREPARATION_CACHE_SHA,
            "preparation": preparation,
            "s1bEvidence": str(args.s1b_evidence),
            "s1bEvidenceSha256": screen.digest(args.s1b_evidence),
            "screenOutput": str(args.screen_output),
            "representation": representation,
            "attentionRepresentationSha256": screen.digest(args.screen_output / "z_attention.npy"),
            "attentionRowIdsSha256": screen.digest(args.screen_output / "z_row_ids.npy"),
        },
        "population": {
            "TRAIN": {"rows": len(train), "sources": int(np.unique(cache["source"][train]).size)},
            "VALIDATION": {"rows": len(validation), "sources": int(np.unique(cache["source"][validation]).size)},
            "TEST": {"rows": int((cache["split"] == 2).sum()), "encodedRows": 0, "inferenceRows": 0, "scoredRows": 0},
        },
        "recipe": RECIPE,
        "initialization": {"headSha256": initial_digest, "byteIdentical": True},
        "batchOrderSha256": batch_order_sha,
        "fit": {"A": {key: value for key, value in arm_a.items() if key != "head"},
                "B": {key: value for key, value in arm_b.items() if key != "head"}},
        "metrics": {"A": metrics_a, "B": metrics_b},
        "slices": slices,
        "comparison": {
            "nllRelative": metrics_b["nll"] / metrics_a["nll"] - 1.0,
            "brierRelative": metrics_b["brier"] / metrics_a["brier"] - 1.0,
            "deathNllRelative": slices["deaths"]["B"]["nll"] / slices["deaths"]["A"]["nll"] - 1.0,
            "lowPreHpNllRelative": slices["lowPreHp"]["B"]["nll"] / slices["lowPreHp"]["A"]["nll"] - 1.0,
        },
        "validity": {
            "finite": all(metrics_x["finiteLogits"] and metrics_x["finiteProbabilities"] for metrics_x in (metrics_a, metrics_b)),
            "encodersFrozen": True,
            "testInferenceRows": 0,
        },
        "uncertainty": "One fixed offline TRAIN/VALIDATION nonlinear-decoder comparison; no encoder fine-tuning, TEST, runtime, gameplay, OOC MCTS or promotion.",
        "knowledgeImpact": "experiment evidence and current research status only; runtime defaults unchanged",
    }
    screen.composed.base.json_dump(args.output / "results.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/potion-trajectory-v2"))
    parser.add_argument("--deepset-run", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"))
    parser.add_argument("--deepset-evidence", type=Path, default=screen.ROOT / "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json")
    parser.add_argument("--representation", type=Path, default=REPRESENTATION)
    parser.add_argument("--screen-output", type=Path, default=SCREEN_OUTPUT)
    parser.add_argument("--s1b-evidence", type=Path, default=S1B_EVIDENCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
