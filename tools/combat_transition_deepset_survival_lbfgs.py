#!/usr/bin/env python3
"""Converged linear survival probes over existing frozen embeddings."""
from __future__ import annotations

import argparse
import copy
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


BASELINE_SHA = "e82810f8486d4ad47b62b074ebcfdcb307fa9f17"
SCREEN_OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-survival-screen-20260916-final")
REPRESENTATION = Path("/home/philippherrmann/sts_sweep/runs/deepset-downstream-20260916-corrected")
OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-survival-lbfgs-20260917")
L2 = 1e-4
SEED = 20260912


def objective(head: torch.nn.Module, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    logits = head(features).flatten()
    nll = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
    penalty = 0.5 * L2 * sum(parameter.square().sum() for parameter in head.parameters())
    return nll + penalty


def fit_arm(name: str, initial_state: dict, features: torch.Tensor,
            labels: torch.Tensor, output: Path) -> dict:
    head = torch.nn.Linear(features.shape[1], 1, device=features.device)
    head.load_state_dict(copy.deepcopy(initial_state), strict=True)
    optimizer = torch.optim.LBFGS(
        head.parameters(),
        lr=1.0,
        max_iter=500,
        max_eval=1000,
        tolerance_grad=1e-9,
        tolerance_change=1e-12,
        history_size=20,
        line_search_fn="strong_wolfe",
    )
    closure_calls = 0

    def closure() -> torch.Tensor:
        nonlocal closure_calls
        optimizer.zero_grad(set_to_none=True)
        loss = objective(head, features, labels)
        if not torch.isfinite(loss):
            raise ValueError(f"nonfinite {name} L-BFGS objective")
        loss.backward()
        closure_calls += 1
        return loss

    started = time.monotonic()
    optimizer.step(closure)
    optimizer.zero_grad(set_to_none=True)
    final_objective = objective(head, features, labels)
    final_objective.backward()
    gradient_norm = torch.sqrt(sum(parameter.grad.square().sum() for parameter in head.parameters()))
    if not torch.isfinite(final_objective) or not torch.isfinite(gradient_norm):
        raise ValueError(f"nonfinite {name} converged state")
    checkpoint = output / f"head_{name.lower()}.pt"
    torch.save({"stateDict": head.state_dict(), "recipe": {"l2": L2, "seed": SEED}}, checkpoint)
    head.zero_grad(set_to_none=True)
    return {
        "name": name,
        "checkpoint": str(checkpoint),
        "checkpointSha256": screen.digest(checkpoint),
        "stateSha256": screen.state_digest(head.state_dict()),
        "closureCalls": closure_calls,
        "finalTrainObjective": float(final_objective.detach().cpu()),
        "finalGradientNorm": float(gradient_norm.detach().cpu()),
        "trainingSeconds": time.monotonic() - started,
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
    screen_output = args.screen_output
    row_ids = np.load(screen_output / "z_row_ids.npy", mmap_mode="r")
    attention_z = np.load(screen_output / "z_attention.npy", mmap_mode="r")
    if not np.array_equal(row_ids, cache["ids"][target]) or tuple(attention_z.shape) != (len(target), 64):
        raise ValueError("saved Attention representation identity or shape differs")
    deepset_z, representation = screen.load_candidate_representation(args, cache, target)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    initial_head = torch.nn.Linear(64, 1)
    initial_state = copy.deepcopy(initial_head.state_dict())
    initial_digest = screen.state_digest(initial_state)
    features_a = torch.from_numpy(np.asarray(attention_z[train_positions])).to(device)
    features_b = torch.from_numpy(np.asarray(deepset_z[train_positions])).to(device)
    labels = torch.from_numpy(cache["win"][train].astype(np.float32)).to(device)
    arm_a = fit_arm("A", initial_state, features_a, labels, args.output)
    arm_b = fit_arm("B", initial_state, features_b, labels, args.output)
    metrics_a = screen.metrics(arm_a["head"], attention_z, cache, validation, device, validation_positions)
    metrics_b = screen.metrics(arm_b["head"], deepset_z, cache, validation, device, validation_positions)
    slices = screen.validation_slices(arm_a["head"], arm_b["head"], attention_z, deepset_z,
                                      cache, target, validation, device)
    previous = json.loads((screen_output / "results.json").read_text(encoding="utf-8"))
    old_relative = previous["deltas"]["nllRelative"]
    new_relative = metrics_b["nll"] / metrics_a["nll"] - 1.0
    result = {
        "schema": "deepset_survival_lbfgs_probe_v1",
        "decision": "S1_LINEAR_PROBE_DIAGNOSTIC",
        "interpretation": "converged full-batch linear probes; no preregistered acceptance gate",
        "baselineSha": args.base_sha,
        "sourceSha": screen.SOURCE_SHA,
        "corpusSha256": screen.CORPUS_SHA,
        "provenance": {
            "preparationCacheSha256": screen.PREPARATION_CACHE_SHA,
            "preparation": preparation,
            "screenOutput": str(screen_output),
            "screenOutputResultsSha256": screen.digest(screen_output / "results.json"),
            "representation": representation,
            "attentionRepresentationSha256": screen.digest(screen_output / "z_attention.npy"),
            "attentionRowIdsSha256": screen.digest(screen_output / "z_row_ids.npy"),
        },
        "population": {
            "TRAIN": {"rows": len(train), "sources": int(np.unique(cache["source"][train]).size)},
            "VALIDATION": {"rows": len(validation), "sources": int(np.unique(cache["source"][validation]).size)},
            "TEST": {"rows": int((cache["split"] == 2).sum()), "encodedRows": 0, "inferenceRows": 0, "scoredRows": 0},
        },
        "recipe": {
            "optimizer": "full-batch L-BFGS strong-Wolfe",
            "maxIter": 500,
            "maxEval": 1000,
            "toleranceGrad": 1e-9,
            "toleranceChange": 1e-12,
            "historySize": 20,
            "l2": L2,
            "seed": SEED,
            "validationEpochSelection": False,
            "encoderTraining": False,
            "testInferenceRows": 0,
        },
        "initialization": {"headSha256": initial_digest, "byteIdentical": True},
        "fit": {"A": {key: value for key, value in arm_a.items() if key != "head"},
                "B": {key: value for key, value in arm_b.items() if key != "head"}},
        "metrics": {"A": metrics_a, "B": metrics_b},
        "slices": slices,
        "comparison": {
            "previousScreenNllRelative": old_relative,
            "lbfgsNllRelative": new_relative,
            "relativeGapReduction": old_relative - new_relative,
            "brierRelative": metrics_b["brier"] / metrics_a["brier"] - 1.0,
            "deathNllRelative": slices["deaths"]["B"]["nll"] / slices["deaths"]["A"]["nll"] - 1.0,
            "lowPreHpNllRelative": slices["lowPreHp"]["B"]["nll"] / slices["lowPreHp"]["A"]["nll"] - 1.0,
        },
        "validity": {
            "finite": all(metrics_x["finiteLogits"] and metrics_x["finiteProbabilities"] for metrics_x in (metrics_a, metrics_b)),
            "encodersFrozen": True,
            "testInferenceRows": 0,
        },
        "uncertainty": "One converged offline TRAIN/VALIDATION linear-probe comparison; no encoder fine-tuning, nonlinear decoder, TEST, runtime, gameplay, OOC MCTS or promotion.",
        "knowledgeImpact": "experiment evidence and current research status only; runtime defaults unchanged",
    }
    screen.composed.base.json_dump(args.output / "results.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/potion-trajectory-v2"))
    parser.add_argument("--reference-component", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/full-union-survival-v1/component.pt"))
    parser.add_argument("--deepset-run", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"))
    parser.add_argument("--deepset-evidence", type=Path, default=screen.ROOT / "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json")
    parser.add_argument("--representation", type=Path, default=REPRESENTATION)
    parser.add_argument("--screen-output", type=Path, default=SCREEN_OUTPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
