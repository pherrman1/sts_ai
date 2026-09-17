#!/usr/bin/env python3
"""Z-scored, unregularized linear survival probe over frozen embeddings."""
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


BASELINE_SHA = "ada2b7ca13b374881c2594aaee937437ea3204f4"
SCREEN_OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-survival-screen-20260916-final")
S1_OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-survival-lbfgs-20260916")
REPRESENTATION = Path("/home/philippherrmann/sts_sweep/runs/deepset-downstream-20260916-corrected")
OUTPUT = Path("/tmp/deepset-survival-s1b-20260917")
SEED = 20260912


def normalize_representation(representation: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    normalized = (np.asarray(representation, dtype=np.float32) - mean.astype(np.float32)) / std.astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError("normalized representation is not finite")
    return normalized


def objective(head: torch.nn.Module, features: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    return torch.nn.functional.binary_cross_entropy_with_logits(head(features).flatten(), labels)


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
            raise ValueError(f"nonfinite {name} S1b objective")
        loss.backward()
        closure_calls += 1
        return loss

    started = time.monotonic()
    optimizer.step(closure)
    optimizer.zero_grad(set_to_none=True)
    final_train_nll = objective(head, features, labels)
    final_train_nll.backward()
    gradient_norm = torch.sqrt(sum(parameter.grad.square().sum() for parameter in head.parameters()))
    head_norm = torch.sqrt(sum(parameter.square().sum() for parameter in head.parameters()))
    if not all(torch.isfinite(value) for value in (final_train_nll, gradient_norm, head_norm)):
        raise ValueError(f"nonfinite {name} S1b fit state")
    checkpoint = output / f"head_{name.lower()}.pt"
    torch.save(
        {"stateDict": head.state_dict(), "recipe": {"regularization": "none", "seed": SEED}},
        checkpoint,
    )
    head.zero_grad(set_to_none=True)
    return {
        "name": name,
        "checkpoint": str(checkpoint),
        "checkpointSha256": screen.digest(checkpoint),
        "stateSha256": screen.state_digest(head.state_dict()),
        "closureCalls": closure_calls,
        "trainNll": float(final_train_nll.detach().cpu()),
        "finalGradientNorm": float(gradient_norm.detach().cpu()),
        "headL2Norm": float(head_norm.detach().cpu()),
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
    row_ids = np.load(args.screen_output / "z_row_ids.npy", mmap_mode="r")
    attention_z = np.load(args.screen_output / "z_attention.npy", mmap_mode="r")
    if not np.array_equal(row_ids, cache["ids"][target]) or tuple(attention_z.shape) != (len(target), 64):
        raise ValueError("saved Attention representation identity or shape differs")
    deepset_z, representation = screen.load_candidate_representation(args, cache, target)
    means = {}
    standard_deviations = {}
    scales = {}
    constant_dimensions = {}
    normalized = {}
    for name, values in (("A", attention_z), ("B", deepset_z)):
        train_values = np.asarray(values[train_positions], dtype=np.float64)
        mean = train_values.mean(axis=0)
        standard_deviation = train_values.std(axis=0)
        if not np.isfinite(mean).all() or not np.isfinite(standard_deviation).all() or (standard_deviation < 0).any():
            raise ValueError(f"{name} TRAIN representation statistics are invalid")
        constants = np.flatnonzero(standard_deviation == 0).astype(np.int64)
        scale = np.where(standard_deviation > 0, standard_deviation, 1.0)
        means[name] = mean
        standard_deviations[name] = standard_deviation
        scales[name] = scale
        constant_dimensions[name] = constants
        normalized[name] = normalize_representation(values, mean, scale)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    initial_head = torch.nn.Linear(64, 1)
    initial_state = copy.deepcopy(initial_head.state_dict())
    initial_digest = screen.state_digest(initial_state)
    labels = torch.from_numpy(cache["win"][train].astype(np.float32)).to(device)
    features_a = torch.from_numpy(normalized["A"][train_positions]).to(device)
    features_b = torch.from_numpy(normalized["B"][train_positions]).to(device)
    arm_a = fit_arm("A", initial_state, features_a, labels, args.output)
    arm_b = fit_arm("B", initial_state, features_b, labels, args.output)
    metrics_a = screen.metrics(arm_a["head"], normalized["A"], cache, validation, device, validation_positions)
    metrics_b = screen.metrics(arm_b["head"], normalized["B"], cache, validation, device, validation_positions)
    slices = screen.validation_slices(arm_a["head"], arm_b["head"], normalized["A"], normalized["B"],
                                      cache, target, validation, device)
    result = {
        "schema": "deepset_survival_s1b_v1",
        "decision": "S1B_LINEAR_SCALE_DIAGNOSTIC",
        "interpretation": "TRAIN-only per-representation z-scoring plus unregularized full-batch linear probes; no acceptance gate",
        "baselineSha": args.base_sha,
        "sourceSha": screen.SOURCE_SHA,
        "corpusSha256": screen.CORPUS_SHA,
        "provenance": {
            "preparationCacheSha256": screen.PREPARATION_CACHE_SHA,
            "preparation": preparation,
            "screenOutput": str(args.screen_output),
            "s1Output": str(args.s1_output),
            "representation": representation,
            "attentionRepresentationSha256": screen.digest(args.screen_output / "z_attention.npy"),
            "attentionRowIdsSha256": screen.digest(args.screen_output / "z_row_ids.npy"),
        },
        "population": {
            "TRAIN": {"rows": len(train), "sources": int(np.unique(cache["source"][train]).size)},
            "VALIDATION": {"rows": len(validation), "sources": int(np.unique(cache["source"][validation]).size)},
            "TEST": {"rows": int((cache["split"] == 2).sum()), "encodedRows": 0, "inferenceRows": 0, "scoredRows": 0},
        },
        "recipe": {
            "optimizer": "full-batch L-BFGS strong-Wolfe",
            "regularization": "none",
            "zScore": "per representation; TRAIN mean/std applied to TRAIN and VALIDATION",
            "maxIter": 500,
            "maxEval": 1000,
            "toleranceGrad": 1e-9,
            "toleranceChange": 1e-12,
            "historySize": 20,
            "seed": SEED,
            "validationEpochSelection": False,
            "encoderTraining": False,
            "testInferenceRows": 0,
        },
        "normalization": {
            name: {
                "trainMean": means[name].tolist(),
                "trainStd": standard_deviations[name].tolist(),
                "scaleStd": scales[name].tolist(),
                "constantDimensions": constant_dimensions[name].tolist(),
                "meanSha256": screen.array_digest(means[name]),
                "stdSha256": screen.array_digest(standard_deviations[name]),
                "scaleStdSha256": screen.array_digest(scales[name]),
                "trainMeanAbsError": float(abs(normalized[name][train_positions].mean(axis=0)).max()),
                "trainNonconstantStdAbsError": float(abs(normalized[name][train_positions][:, standard_deviations[name] > 0].std(axis=0) - 1.0).max()) if (standard_deviations[name] > 0).any() else 0.0,
            }
            for name in ("A", "B")
        },
        "initialization": {"headSha256": initial_digest, "byteIdentical": True},
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
        "uncertainty": "One fixed offline TRAIN/VALIDATION scale-neutral linear-probe comparison; no tuning, nonlinear decoder, encoder fine-tuning, TEST, runtime, gameplay, OOC MCTS or promotion.",
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
    parser.add_argument("--s1-output", type=Path, default=S1_OUTPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
