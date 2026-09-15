#!/usr/bin/env python3
"""Targeted validation-only tuning for the Phase-1 combat-transition attention model."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np

try:
    from tools import combat_transition_model_experiment as base
except ModuleNotFoundError:
    import combat_transition_model_experiment as base


SCHEMA = "combat_transition_attention_hpo_v1"
EXPECTED_CORPUS_SHA256 = "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde"
EXPECTED_SPLIT_SHA256 = "e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32"
EXPECTED_PREPARED_MANIFEST_SHA256 = "fdf1ca760c971b212e60d9cb86beec78afae6b124958aa53c56a8aea5bb92f51"
EXPECTED_PREPARED_SHA256 = "a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9"
EXPECTED_BASELINE_SHA256 = "a4545c54c8b99afb059b64c6ee36523f472e2e636040e166b32ded4218614b6f"

BASELINE_CANDIDATE = {
    "name": "baseline", "width": 64, "heads": 4, "layers": 2,
    "feedforward": 128, "dropout": 0.1, "trunkWidth": 64,
    "learningRate": 1e-3, "weightDecay": 1e-4, "winningHpWeight": 1.0,
}

DEFAULT_CANDIDATES = [
    BASELINE_CANDIDATE,
    {"name": "no_dropout", "width": 64, "heads": 4, "layers": 2,
     "feedforward": 128, "dropout": 0.0, "trunkWidth": 64,
     "learningRate": 1e-3, "weightDecay": 1e-4, "winningHpWeight": 1.0},
    {"name": "lower_lr", "width": 64, "heads": 4, "layers": 2,
     "feedforward": 128, "dropout": 0.1, "trunkWidth": 64,
     "learningRate": 5e-4, "weightDecay": 1e-4, "winningHpWeight": 1.0},
    {"name": "higher_lr", "width": 64, "heads": 4, "layers": 2,
     "feedforward": 128, "dropout": 0.1, "trunkWidth": 64,
     "learningRate": 2e-3, "weightDecay": 1e-4, "winningHpWeight": 1.0},
    {"name": "hp_weight_2", "width": 64, "heads": 4, "layers": 2,
     "feedforward": 128, "dropout": 0.1, "trunkWidth": 64,
     "learningRate": 1e-3, "weightDecay": 1e-4, "winningHpWeight": 2.0},
    {"name": "ff256", "width": 64, "heads": 4, "layers": 2,
     "feedforward": 256, "dropout": 0.1, "trunkWidth": 64,
     "learningRate": 1e-3, "weightDecay": 1e-4, "winningHpWeight": 1.0},
    {"name": "depth3", "width": 64, "heads": 4, "layers": 3,
     "feedforward": 128, "dropout": 0.1, "trunkWidth": 64,
     "learningRate": 8e-4, "weightDecay": 1e-4, "winningHpWeight": 1.0},
    {"name": "width96", "width": 96, "heads": 4, "layers": 2,
     "feedforward": 192, "dropout": 0.1, "trunkWidth": 96,
     "learningRate": 8e-4, "weightDecay": 1e-4, "winningHpWeight": 1.0},
]


def selection_score(metrics: dict) -> float:
    return float(metrics["survival"]["brier"] + metrics["winningHp"]["mae"]
                 + metrics["jointAliveHp"]["mae"])


def validate_candidates(candidates: list[dict]) -> None:
    required = {"name", "width", "heads", "layers", "feedforward", "dropout",
                "trunkWidth", "learningRate", "weightDecay", "winningHpWeight"}
    names: set[str] = set()
    for candidate in candidates:
        missing = required - set(candidate)
        if missing:
            raise ValueError(f"candidate missing fields: {sorted(missing)}")
        if candidate["name"] in names:
            raise ValueError(f"duplicate candidate name {candidate['name']}")
        names.add(candidate["name"])
        if int(candidate["width"]) % int(candidate["heads"]):
            raise ValueError(f"candidate {candidate['name']} width is not divisible by heads")
        if min(float(candidate[k]) for k in ("learningRate", "winningHpWeight")) <= 0:
            raise ValueError(f"candidate {candidate['name']} has a non-positive tuning value")
        if not 0 <= float(candidate["dropout"]) < 1:
            raise ValueError(f"candidate {candidate['name']} dropout is outside [0,1)")
    baselines = [candidate for candidate in candidates if candidate["name"] == "baseline"]
    if baselines != [BASELINE_CANDIDATE]:
        raise ValueError("candidate list must contain the exact frozen baseline configuration")


def validate_split_arrays(arrays: dict, split_manifest: dict, prepared_manifest: dict) -> None:
    expected_rows = {0: int(prepared_manifest["counts"]["0"]),
                     1: int(prepared_manifest["counts"]["1"]),
                     2: int(prepared_manifest["counts"]["2"])}
    split_names = {0: "train", 1: "validation", 2: "test"}
    if not set(np.unique(arrays["split_id"]).tolist()) <= {0, 1, 2}:
        raise ValueError("prepared arrays contain an unknown split id")
    if len(arrays["sourceSeed"]) != sum(expected_rows.values()):
        raise ValueError("prepared row count does not match the frozen manifest")
    for split_id, split_name in split_names.items():
        positions = np.flatnonzero(arrays["split_id"] == split_id)
        if len(positions) != expected_rows[split_id]:
            raise ValueError(f"prepared {split_name} row count does not match the frozen manifest")
        actual_sources = set(int(value) for value in arrays["sourceSeed"][positions])
        expected_sources = set(int(value) for value in split_manifest["members"][split_name])
        if actual_sources != expected_sources:
            raise ValueError(f"prepared {split_name} sources do not match the frozen split")


def _new_model(torch, arrays: dict, indices: np.ndarray, candidate: dict,
               device: str, seed: int, threads: int):
    torch.set_num_threads(threads)
    torch.manual_seed(seed)
    if device == "cuda":
        torch.cuda.manual_seed_all(seed)
    values = arrays["globals_continuous"][indices]
    wrapper = base.AttentionModel(
        torch, base.MAX_CARDS, base.MAX_RELICS, values.mean(0), values.std(0), candidate
    )
    wrapper.device = torch.device(device)
    wrapper.net = wrapper.net.to(wrapper.device)
    return wrapper


def _train_epoch(wrapper, arrays: dict, order: np.ndarray, batch: int,
                 optimizer, hp_weight: float) -> None:
    torch = wrapper.torch
    wrapper.net.train()
    bce = torch.nn.BCEWithLogitsLoss()
    for lo in range(0, len(order), batch):
        ids = order[lo:lo + batch]
        win_logits, hp_logits = wrapper.net(*base._torch_values(wrapper, arrays, ids))
        target = torch.from_numpy(arrays["y_win"][ids].astype(np.float32)).to(wrapper.device)
        hp_target = torch.from_numpy(
            np.nan_to_num(arrays["y_hp"][ids], nan=0.0).astype(np.float32)
        ).to(wrapper.device)
        win_mask = target > 0.5
        loss = bce(win_logits, target)
        if bool(win_mask.any()):
            loss = loss + hp_weight * torch.nn.functional.mse_loss(
                torch.sigmoid(hp_logits)[win_mask], hp_target[win_mask]
            )
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(wrapper.net.parameters(), 1.0)
        optimizer.step()


def tune_candidate(torch, arrays: dict, train: np.ndarray, validation: np.ndarray,
                   candidate: dict, args, device: str) -> tuple[dict, int, int]:
    wrapper = _new_model(torch, arrays, train, candidate, device,
                         args.training_seed, args.threads)
    optimizer = torch.optim.AdamW(
        wrapper.net.parameters(), lr=float(candidate["learningRate"]),
        weight_decay=float(candidate["weightDecay"]),
    )
    rng = np.random.default_rng(args.training_seed)
    best_state = None
    best_metrics = None
    best_score = math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, args.epochs + 1):
        _train_epoch(wrapper, arrays, rng.permutation(train), args.batch, optimizer,
                     float(candidate["winningHpWeight"]))
        metrics, _, _ = base._torch_eval(wrapper, arrays, validation, args.batch)
        score = selection_score(metrics)
        if score < best_score:
            best_score = score
            best_metrics = metrics
            best_state = {key: value.detach().cpu().clone()
                          for key, value in wrapper.net.state_dict().items()}
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
        print(json.dumps({"candidate": candidate["name"], "epoch": epoch,
                          "validationScore": score, "bestScore": best_score}), flush=True)
        if stale >= args.patience:
            break
    if best_state is None or best_metrics is None:
        raise RuntimeError(f"candidate {candidate['name']} produced no checkpoint")
    return best_metrics, best_epoch, int(sum(v.numel() for v in wrapper.net.parameters()))


def refit(torch, arrays: dict, indices: np.ndarray, candidate: dict, epochs: int,
          args, device: str):
    wrapper = _new_model(torch, arrays, indices, candidate, device,
                         args.training_seed, args.threads)
    optimizer = torch.optim.AdamW(
        wrapper.net.parameters(), lr=float(candidate["learningRate"]),
        weight_decay=float(candidate["weightDecay"]),
    )
    rng = np.random.default_rng(args.training_seed)
    for epoch in range(1, epochs + 1):
        _train_epoch(wrapper, arrays, rng.permutation(indices), args.batch, optimizer,
                     float(candidate["winningHpWeight"]))
        print(json.dumps({"phase": "refit", "epoch": epoch, "epochs": epochs}), flush=True)
    return wrapper


def bootstrap_delta(arrays: dict, test: np.ndarray, tuned: tuple[np.ndarray, np.ndarray],
                    baseline: tuple[np.ndarray, np.ndarray], reps: int, seed: int) -> dict:
    groups = arrays["sourceSeed"][test]
    unique = np.asarray(sorted(set(groups.tolist())))
    by_source = {int(source): np.flatnonzero(groups == source) for source in unique}
    rng = np.random.default_rng(seed)
    deltas = []
    y = arrays["y_win"][test]
    hp = arrays["y_hp"][test]
    for _ in range(reps):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        pos = np.concatenate([by_source[int(source)] for source in sampled])
        win = y[pos] == 1
        alive = y[pos] * np.nan_to_num(hp[pos], nan=0.0)
        values = []
        for survival, winning_hp in (tuned, baseline):
            values.append((np.mean((survival[pos] - y[pos]) ** 2),
                           np.mean(np.abs(winning_hp[pos][win] - hp[pos][win])),
                           np.mean(np.abs(survival[pos] * winning_hp[pos] - alive))))
        deltas.append(np.asarray(values[0]) - np.asarray(values[1]))
    delta = np.asarray(deltas)
    y = arrays["y_win"][test]
    hp = arrays["y_hp"][test]
    win = y == 1
    alive = y * np.nan_to_num(hp, nan=0.0)
    point_values = []
    for survival, winning_hp in (tuned, baseline):
        point_values.append(np.asarray((np.mean((survival - y) ** 2),
                                        np.mean(np.abs(winning_hp[win] - hp[win])),
                                        np.mean(np.abs(survival * winning_hp - alive)))))
    point = point_values[0] - point_values[1]
    names = ("brier", "winningHpMae", "jointAliveHpMae")
    return {name: {"point": float(point[i]),
                   "sourceBootstrap95": [float(np.quantile(delta[:, i], 0.025)),
                                         float(np.quantile(delta[:, i], 0.975))]}
            for i, name in enumerate(names)}


def run(args) -> None:
    import torch

    repo_root = Path(__file__).resolve().parents[1]
    reviewed_commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if reviewed_commit != args.reviewed_commit:
        raise ValueError("current HEAD does not match --reviewed-commit")
    worktree_status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"], check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout
    if worktree_status:
        raise ValueError("repository worktree must be clean at the reviewed commit")

    prepared = Path(args.prepared_dir)
    manifest_path = prepared / "prepared_manifest.json"
    prepared_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if prepared_manifest_hash != EXPECTED_PREPARED_MANIFEST_SHA256:
        raise ValueError("prepared manifest hash does not match the frozen Phase-1 arrays")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("corpusSha256") != EXPECTED_CORPUS_SHA256:
        raise ValueError("prepared corpus hash does not match the frozen Phase-1 corpus")
    split_path = prepared / "split_manifest.json"
    if hashlib.sha256(split_path.read_bytes()).hexdigest() != EXPECTED_SPLIT_SHA256:
        raise ValueError("source-grouped split hash does not match the frozen Phase-1 split")
    prepared_path = prepared / "prepared.npz"
    if base.sha256(prepared_path) != EXPECTED_PREPARED_SHA256:
        raise ValueError("prepared array hash does not match the frozen Phase-1 arrays")
    baseline_checkpoint = Path(args.baseline_checkpoint)
    if base.sha256(baseline_checkpoint) != EXPECTED_BASELINE_SHA256:
        raise ValueError("baseline checkpoint hash does not match the frozen corrected attention model")
    output = Path(args.output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output directory {output}")
    candidates = (json.loads(Path(args.candidates).read_text(encoding="utf-8"))
                  if args.candidates else copy.deepcopy(DEFAULT_CANDIDATES))
    validate_candidates(candidates)
    arrays = {key: value for key, value in np.load(prepared_path, allow_pickle=False).items()}
    split_manifest = json.loads(split_path.read_text(encoding="utf-8"))
    validate_split_arrays(arrays, split_manifest, manifest)
    train = np.flatnonzero(arrays["split_id"] == 0)
    validation = np.flatnonzero(arrays["split_id"] == 1)
    test = np.flatnonzero(arrays["split_id"] == 2)
    device = base._resolve_device(torch, args.device)
    started = time.time()
    results = []
    for candidate in candidates:
        metrics, epochs, parameters = tune_candidate(
            torch, arrays, train, validation, candidate, args, device
        )
        results.append({"candidate": candidate, "selectedEpochs": epochs,
                        "parameters": parameters, "validation": metrics,
                        "selectionScore": selection_score(metrics)})
    winner = min(results, key=lambda item: item["selectionScore"])
    combined = np.concatenate((train, validation))
    tuned_model = refit(torch, arrays, combined, winner["candidate"],
                        winner["selectedEpochs"], args, device)
    tuned_p, tuned_hp = base._predict_torch(tuned_model, arrays, test, args.batch)
    tuned_metrics = base._metrics_for_predictions(arrays, test, tuned_p, tuned_hp)

    baseline_model = _new_model(torch, arrays, combined, BASELINE_CANDIDATE, device,
                                args.training_seed, args.threads)
    baseline_model.net.load_state_dict(torch.load(baseline_checkpoint,
                                                   map_location=baseline_model.device,
                                                   weights_only=True))
    baseline_p, baseline_hp = base._predict_torch(baseline_model, arrays, test, args.batch)
    baseline_metrics = base._metrics_for_predictions(arrays, test, baseline_p, baseline_hp)

    output.mkdir(parents=True, exist_ok=False)
    torch.save(tuned_model.net.state_dict(), output / "attention_tuned.pt")
    evidence = {
        "schemaVersion": SCHEMA,
        "reviewedCommit": reviewed_commit,
        "corpusSha256": EXPECTED_CORPUS_SHA256,
        "splitManifestSha256": EXPECTED_SPLIT_SHA256,
        "preparedManifestSha256": prepared_manifest_hash,
        "preparedSha256": EXPECTED_PREPARED_SHA256,
        "protocol": {"selection": "minimum validation Brier + winning-HP MAE + joint alive-HP MAE",
                     "testStatus": "historical frozen TEST; previously inspected, used only after HPO selection",
                     "trainingSeed": args.training_seed, "batch": args.batch,
                     "epochCap": args.epochs, "patience": args.patience,
                     "device": device, "candidates": len(candidates),
                     "determinism": "fixed NumPy/Torch seeds and matched row permutations; CUDA kernels not asserted bitwise deterministic"},
        "validationCandidates": results,
        "winner": winner,
        "test": {"tuned": tuned_metrics, "frozenBaseline": baseline_metrics,
                 "tunedMinusFrozenBaselineSourceBootstrap95": bootstrap_delta(
                     arrays, test, (tuned_p, tuned_hp), (baseline_p, baseline_hp),
                     args.bootstrap_reps, args.training_seed)},
        "artifacts": {"attentionTunedSha256": base.sha256(output / "attention_tuned.pt"),
                      "baselineCheckpointSha256": EXPECTED_BASELINE_SHA256},
        "elapsedSeconds": time.time() - started,
    }
    base.json_dump(output / "attention_hpo_evidence.json", evidence)
    print(json.dumps({"winner": winner["candidate"]["name"],
                      "validationScore": winner["selectionScore"],
                      "test": tuned_metrics,
                      "output": str(output.resolve())}, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-dir", required=True)
    parser.add_argument("--baseline-checkpoint", required=True)
    parser.add_argument("--reviewed-commit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--candidates")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch", type=int, default=2048)
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--training-seed", type=int, default=20260911)
    parser.add_argument("--bootstrap-reps", type=int, default=1000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
