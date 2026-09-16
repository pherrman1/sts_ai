#!/usr/bin/env python3
"""Screen the qualified frozen DeepSets representation for survival."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_composed as composed
from tools import combat_transition_composed_evaluate as composed_eval
from tools import combat_transition_deepset_downstream as deepset_downstream
from tools import combat_transition_surrogate as surrogate


BASELINE_SHA = "4c8ff3fe044626c6d18226e5f4091a0d1cb842d1"
CORPUS_SHA = "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde"
SOURCE_SHA = "1c31b7eb0a7660d43bc27e0849a8955dd0c3daae"
PREPARATION_CACHE_SHA = "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d"
DEEPSER_CHECKPOINT_SHA = "bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663"
DEEPSER_RECEIPT_SHA = "83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769"
REFERENCE_COMPONENT_SHA = "e150180a9112f52a94cfa60770adb6c0a48517a7d94a4c26f6e5896e85269c18"
REFERENCE_NLL = 0.05949442833662033
TRAIN_ROWS = 408_183
VALIDATION_ROWS = 50_406
TEST_ROWS = 51_441
REPRESENTATION_ROWS = TRAIN_ROWS + VALIDATION_ROWS

RECIPE = {
    "schema": "deepset_survival_screen_v1",
    "seed": 20260912,
    "epochs": 12,
    "batch": 512,
    "precision": "fp32",
    "optimizer": "AdamW",
    "lr": 1e-3,
    "weightDecay": 1e-4,
    "gradientClip": 1.0,
    "loss": "BCE-with-logits survival loss",
    "selection": "earliest strict minimum VALIDATION log loss",
    "training": "fresh survival head only; both encoders frozen and cached",
    "testInferenceRows": 0,
}


def digest(path: Path) -> str:
    return composed.base.sha256(path)


def array_digest(value: np.ndarray) -> str:
    value = np.asarray(value)
    hasher = hashlib.sha256()
    hasher.update(str(value.dtype).encode())
    hasher.update(json.dumps(list(value.shape), separators=(",", ":")).encode())
    hasher.update(np.ascontiguousarray(value).tobytes())
    return hasher.hexdigest()


def state_digest(state: dict) -> str:
    hasher = hashlib.sha256()
    for key in sorted(state):
        value = state[key].detach().cpu().contiguous()
        hasher.update(key.encode())
        hasher.update(str(value.dtype).encode())
        hasher.update(json.dumps(list(value.shape), separators=(",", ":")).encode())
        hasher.update(value.numpy().tobytes())
    return hasher.hexdigest()


def current_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def load_cache(args: argparse.Namespace) -> tuple[dict, dict]:
    cache_path = args.cache / "cache.npz"
    if digest(cache_path) != PREPARATION_CACHE_SHA:
        raise ValueError("survival preparation cache hash differs")
    preparation = json.loads((args.cache / "preparation.json").read_text(encoding="utf-8"))
    if preparation.get("cacheSha256") != PREPARATION_CACHE_SHA:
        raise ValueError("survival preparation metadata does not bind cache")
    with np.load(cache_path, allow_pickle=False) as source:
        cache = {key: source[key] for key in source.files}
    required = {"ids", "source", "split", "win", "preHp", "preMax"}
    if not required <= set(cache):
        raise ValueError(f"survival cache is missing fields: {sorted(required - set(cache))}")
    if len(cache["ids"]) != TRAIN_ROWS + VALIDATION_ROWS + TEST_ROWS:
        raise ValueError("survival cache row count differs")
    if not np.array_equal(cache["ids"], np.arange(len(cache["ids"]), dtype=np.int64)):
        raise ValueError("survival cache ids are not the original row ids")
    counts = {
        "TRAIN": int((cache["split"] == 0).sum()),
        "VALIDATION": int((cache["split"] == 1).sum()),
        "TEST": int((cache["split"] == 2).sum()),
    }
    if counts != {"TRAIN": TRAIN_ROWS, "VALIDATION": VALIDATION_ROWS, "TEST": TEST_ROWS}:
        raise ValueError(f"survival population differs: {counts}")
    return cache, preparation


def load_prepared() -> tuple[dict, dict]:
    arrays, spec = surrogate._load_prepared(composed_eval.PREPARED)
    if len(arrays["y_win"]) != len(arrays["sourceSeed"]):
        raise ValueError("prepared arrays have inconsistent row identity")
    manifest = json.loads((composed_eval.PREPARED / "prepared_manifest.json").read_text())
    if manifest.get("corpusSha256") != CORPUS_SHA:
        raise ValueError("prepared corpus hash differs")
    if int(manifest.get("rows", -1)) != len(arrays["y_win"]):
        raise ValueError("prepared corpus row count differs")
    return arrays, spec


def load_reference(args: argparse.Namespace):
    component = args.reference_component
    fit = json.loads((component.parent / "fit.json").read_text(encoding="utf-8"))
    if digest(component) != REFERENCE_COMPONENT_SHA:
        raise ValueError("reference survival component hash differs")
    for key, expected in {
        "sourceSha": SOURCE_SHA,
        "preparationCacheSha256": PREPARATION_CACHE_SHA,
        "trainRows": TRAIN_ROWS,
        "validationRows": VALIDATION_ROWS,
        "testRows": TEST_ROWS,
        "selectedEpoch": 1,
    }.items():
        if fit.get(key) != expected:
            raise ValueError(f"reference survival provenance differs for {key}")
    payload = torch.load(component, map_location="cpu", weights_only=False)
    model = attention.AttentionPointControlNet(
        torch, np.zeros(10, dtype=np.float32), np.ones(10, dtype=np.float32)
    ).net
    model.encoder.load_state_dict(payload["encoderStateDict"], strict=True)
    head = torch.nn.Linear(64, 1)
    head.load_state_dict(payload["headStateDicts"][0], strict=True)
    model.eval().requires_grad_(False)
    head.eval().requires_grad_(False)
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("reference survival encoder is trainable")
    if any(parameter.requires_grad for parameter in head.parameters()):
        raise ValueError("reference survival head is trainable")
    return model.encoder, head, fit


def load_candidate_encoder(args: argparse.Namespace):
    checkpoint = args.deepset_run / "student.pt"
    receipt = args.deepset_run / "results.json"
    if digest(checkpoint) != DEEPSER_CHECKPOINT_SHA:
        raise ValueError("DeepSets checkpoint hash differs")
    if digest(receipt) != DEEPSER_RECEIPT_SHA:
        raise ValueError("DeepSets result receipt hash differs")
    encoder, binding = deepset_downstream.load_deepset_encoder(
        args.deepset_run, args.deepset_evidence
    )
    return encoder, binding


def load_candidate_representation(args, cache: dict, target: np.ndarray) -> tuple[np.ndarray, dict]:
    metadata = json.loads((args.representation / "representation.json").read_text())
    z_path = args.representation / "z_deepset.npy"
    row_path = args.representation / "z_row_ids.npy"
    expected_z = "9232027d8331fd2157727276410161e3c12816b6680cb116ebc2b3afd37352af"
    expected_rows = "3dfecd1df38856c3069b1efdc3ed6cf6f6ad1c792afcbf368b3badb7b112e437"
    if digest(z_path) != expected_z or digest(row_path) != expected_rows:
        raise ValueError("DeepSets representation hash differs")
    z = np.load(z_path, mmap_mode="r")
    row_ids = np.load(row_path, mmap_mode="r")
    if tuple(z.shape) != (REPRESENTATION_ROWS, 64) or z.dtype != np.float32:
        raise ValueError("DeepSets representation shape differs")
    if tuple(row_ids.shape) != (REPRESENTATION_ROWS,) or not np.array_equal(row_ids, cache["ids"][target]):
        raise ValueError("DeepSets representation row mapping differs")
    if not np.isfinite(z).all():
        raise ValueError("DeepSets representation is not finite")
    expected_splits = {"TRAIN": TRAIN_ROWS, "VALIDATION": VALIDATION_ROWS, "TEST": 0}
    if metadata.get("generatedSplits") != expected_splits or metadata.get("generatedRows") != REPRESENTATION_ROWS:
        raise ValueError("DeepSets representation population differs")
    positions = np.searchsorted(row_ids, cache["ids"][target])
    if not np.array_equal(row_ids[positions], cache["ids"][target]):
        raise ValueError("DeepSets representation cannot be bound by original row id")
    return np.asarray(z[positions]), metadata


def encode(encoder, arrays: dict, row_ids: np.ndarray, device: str) -> np.ndarray:
    output = np.empty((len(row_ids), 64), dtype=np.float32)
    encoder = encoder.to(device).eval().requires_grad_(False)
    with torch.inference_mode(), composed.attention_backend(torch, True):
        for start in range(0, len(row_ids), RECIPE["batch"]):
            batch = row_ids[start : start + RECIPE["batch"]]
            inputs = surrogate._torch_inputs(arrays, batch, device, torch, trim_padding=True)
            output[start : start + len(batch)] = encoder(*inputs).float().cpu().numpy()
    if not np.isfinite(output).all():
        raise ValueError("generated frozen representation is not finite")
    return output


def assert_optimizer_scope(head: torch.nn.Module, optimizer: torch.optim.Optimizer) -> None:
    expected = {id(parameter) for parameter in head.parameters()}
    actual = {id(parameter) for group in optimizer.param_groups for parameter in group["params"]}
    if actual != expected:
        raise ValueError("optimizer contains parameters outside the survival head")
    if any(parameter.requires_grad is not True for parameter in head.parameters()):
        raise ValueError("survival head parameter unexpectedly frozen")


def smoke(head: torch.nn.Module, z: np.ndarray, labels: np.ndarray, device: str) -> dict:
    head.train()
    head.zero_grad(set_to_none=True)
    features = torch.from_numpy(np.asarray(z[:8])).to(device)
    target = torch.from_numpy(labels[:8].astype(np.float32)).to(device)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(head(features).flatten(), target)
    if not torch.isfinite(loss):
        raise ValueError("survival smoke loss is nonfinite")
    loss.backward()
    gradients = [parameter.grad for parameter in head.parameters()]
    if not all(gradient is not None and torch.isfinite(gradient).all() for gradient in gradients):
        raise ValueError("survival smoke gradients are invalid")
    head.zero_grad(set_to_none=True)
    return {"rows": 8, "finite": True, "finiteGradients": True}


def logits_for(head: torch.nn.Module, z: np.ndarray, ids: np.ndarray, device: str) -> np.ndarray:
    head.eval()
    values = []
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE["batch"]):
            batch = ids[start : start + RECIPE["batch"]]
            values.append(head(torch.from_numpy(np.asarray(z[batch])).to(device)).flatten().cpu().numpy())
    return np.concatenate(values)


def auc_score(labels: np.ndarray, probabilities: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=np.int8)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    positives = labels == 1
    negatives = labels == 0
    if not positives.any() or not negatives.any():
        return float("nan")
    order = np.argsort(probabilities, kind="mergesort")
    sorted_probabilities = probabilities[order]
    ranks = np.arange(1, len(labels) + 1, dtype=np.float64)
    start = 0
    while start < len(labels):
        end = start + 1
        while end < len(labels) and sorted_probabilities[end] == sorted_probabilities[start]:
            end += 1
        ranks[start:end] = (ranks[start] + ranks[end - 1]) / 2.0
        start = end
    positive_ranks = ranks[order][positives]
    negative_count = float(negatives.sum())
    positive_count = float(positives.sum())
    return float((positive_ranks.sum() - positive_count * (positive_count + 1.0) / 2.0) / (positive_count * negative_count))


def calibration(probabilities: np.ndarray, labels: np.ndarray) -> list[dict]:
    bins = []
    for index in range(10):
        lower = index / 10.0
        upper = (index + 1) / 10.0
        mask = (probabilities >= lower) & (probabilities < upper if index < 9 else probabilities <= upper)
        bins.append({
            "bin": index,
            "lower": lower,
            "upper": upper,
            "rows": int(mask.sum()),
            "meanPredicted": float(probabilities[mask].mean()) if mask.any() else None,
            "observedSurvival": float(labels[mask].mean()) if mask.any() else None,
        })
    return bins


def metrics(head: torch.nn.Module, z: np.ndarray, cache: dict, ids: np.ndarray,
            device: str, positions: np.ndarray | None = None) -> dict:
    labels = cache["win"][ids].astype(np.int8)
    if positions is None:
        positions = ids
    logits = logits_for(head, z, positions, device)
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    losses = np.maximum(logits, 0.0) - logits * labels + np.log1p(np.exp(-np.abs(logits)))
    return {
        "rows": int(len(ids)),
        "nll": float(losses.mean()),
        "brier": float(np.mean((probabilities - labels) ** 2)),
        "rocAuc": auc_score(labels, probabilities),
        "accuracyAt05": float(np.mean((probabilities >= 0.5) == labels)),
        "meanPredictedSurvival": float(probabilities.mean()),
        "observedSurvivalRate": float(labels.mean()),
        "calibration": calibration(probabilities, labels),
        "finiteLogits": bool(np.isfinite(logits).all()),
        "finiteProbabilities": bool(np.isfinite(probabilities).all()),
        "probabilitiesInUnitInterval": bool(((probabilities >= 0.0) & (probabilities <= 1.0)).all()),
    }


def slice_metrics(head: torch.nn.Module, z: np.ndarray, cache: dict, ids: np.ndarray,
                  device: str, positions: np.ndarray | None = None) -> dict:
    if positions is None:
        positions = ids
    logits = logits_for(head, z, positions, device)
    labels = cache["win"][ids].astype(np.int8)
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    losses = np.maximum(logits, 0.0) - logits * labels + np.log1p(np.exp(-np.abs(logits)))
    return {
        "rows": int(len(ids)),
        "deaths": int((labels == 0).sum()),
        "nll": float(losses.mean()) if len(ids) else None,
        "brier": float(np.mean((probabilities - labels) ** 2)) if len(ids) else None,
    }


def train_arm(name: str, initial_state: dict, z: np.ndarray, cache: dict, train: np.ndarray,
              train_positions: np.ndarray, validation: np.ndarray, validation_positions: np.ndarray,
              orders: list[np.ndarray], device: str, output: Path) -> dict:
    head = torch.nn.Linear(64, 1).to(device)
    head.load_state_dict(copy.deepcopy(initial_state), strict=True)
    optimizer = torch.optim.AdamW(head.parameters(), lr=RECIPE["lr"], weight_decay=RECIPE["weightDecay"])
    assert_optimizer_scope(head, optimizer)
    smoke_result = smoke(head, z[train_positions], cache["win"][train], device)
    smoke_result["optimizerScope"] = True
    history = []
    best = float("inf")
    selected_epoch = None
    selected_state = None
    started = time.monotonic()
    labels = cache["win"]
    for epoch, order in enumerate(orders, start=1):
        head.train()
        training_losses = []
        for start in range(0, len(order), RECIPE["batch"]):
            batch = order[start : start + RECIPE["batch"]]
            features = torch.from_numpy(np.asarray(z[train_positions[batch]])).to(device)
            target = torch.from_numpy(labels[train[batch]].astype(np.float32)).to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(head(features).flatten(), target)
            if not torch.isfinite(loss):
                raise ValueError(f"nonfinite {name} training loss at epoch {epoch}")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(head.parameters(), RECIPE["gradientClip"])
            if not torch.isfinite(norm):
                raise ValueError(f"nonfinite {name} gradient norm at epoch {epoch}")
            optimizer.step()
            training_losses.append(float(loss.detach().cpu()))
        validation_metrics = metrics(head, z, cache, validation, device, validation_positions)
        record = {
            "epoch": epoch,
            "trainingNll": float(np.mean(training_losses)),
            "validationNll": validation_metrics["nll"],
        }
        history.append(record)
        print(json.dumps({"arm": name, **record}, sort_keys=True), flush=True)
        if record["validationNll"] < best:
            best = record["validationNll"]
            selected_epoch = epoch
            selected_state = copy.deepcopy(head.state_dict())
    if selected_state is None:
        raise RuntimeError(f"{name} produced no selected head")
    checkpoint = output / f"head_{name.lower()}.pt"
    torch.save({"stateDict": selected_state, "selectedEpoch": selected_epoch, "recipe": RECIPE}, checkpoint)
    head.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=False)["stateDict"], strict=True)
    return {
        "name": name,
        "selectedEpoch": selected_epoch,
        "history": history,
        "trainingSeconds": time.monotonic() - started,
        "smoke": smoke_result,
        "checkpoint": str(checkpoint),
        "checkpointSha256": digest(checkpoint),
        "stateSha256": state_digest(selected_state),
        "head": head,
    }


def run(args: argparse.Namespace) -> dict:
    if current_head() != args.base_sha:
        raise ValueError(f"current baseline differs: {current_head()} != {args.base_sha}")
    if args.output.exists():
        raise ValueError(f"refusing overwrite of {args.output}")
    args.output.mkdir(parents=True)
    cache, preparation = load_cache(args)
    arrays, _ = load_prepared()
    if not np.array_equal(cache["source"], arrays["sourceSeed"]):
        raise ValueError("cache source ids do not match prepared source ids")
    target = np.flatnonzero(cache["split"] < 2).astype(np.int64)
    train = np.flatnonzero(cache["split"] == 0).astype(np.int64)
    validation = np.flatnonzero(cache["split"] == 1).astype(np.int64)
    if len(target) != REPRESENTATION_ROWS or len(train) != TRAIN_ROWS or len(validation) != VALIDATION_ROWS:
        raise ValueError("TRAIN/VALIDATION representation population differs")
    train_positions = np.searchsorted(target, train)
    validation_positions = np.searchsorted(target, validation)
    if not np.array_equal(target[train_positions], train) or not np.array_equal(target[validation_positions], validation):
        raise ValueError("TRAIN/VALIDATION row-id mapping differs")
    reference_encoder, reference_head, reference_fit = load_reference(args)
    deepset_encoder, deepset_binding = load_candidate_encoder(args)
    z_b, representation = load_candidate_representation(args, cache, target)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.set_num_threads(4)
    z_a = encode(reference_encoder, arrays, target, device)
    np.save(args.output / "z_attention.npy", z_a, allow_pickle=False)
    np.save(args.output / "z_row_ids.npy", cache["ids"][target], allow_pickle=False)
    if digest(args.output / "z_row_ids.npy") != digest(args.representation / "z_row_ids.npy"):
        raise ValueError("A/B representation row identity files differ")
    sample_positions = np.asarray([0, len(target) // 2, len(target) - 1, 12345], dtype=np.int64)
    regenerated = encode(deepset_encoder, arrays, target[sample_positions], device)
    max_error = float(np.max(np.abs(regenerated - z_b[sample_positions])))
    if max_error > 1e-5:
        raise ValueError(f"saved DeepSets sample does not regenerate: maxAbsError={max_error}")
    reference_metrics = metrics(reference_head.to(device), z_a, cache, validation, device, validation_positions)
    if abs(reference_metrics["nll"] - REFERENCE_NLL) > 1e-5:
        raise ValueError(f"reference validation NLL not reproduced: {reference_metrics['nll']}")
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"]) if torch.cuda.is_available() else None
    fresh = torch.nn.Linear(64, 1)
    initial_state = copy.deepcopy(fresh.state_dict())
    initial_digest = state_digest(initial_state)
    second = torch.nn.Linear(64, 1)
    second.load_state_dict(copy.deepcopy(initial_state), strict=True)
    if state_digest(second.state_dict()) != initial_digest:
        raise ValueError("A/B fresh head initial states are not byte-identical")
    rng = np.random.default_rng(RECIPE["seed"])
    orders = [rng.permutation(len(train)).astype(np.int64) for _ in range(RECIPE["epochs"])]
    order_hasher = hashlib.sha256()
    for order in orders:
        order_hasher.update(np.ascontiguousarray(order).tobytes())
    batch_order_sha = order_hasher.hexdigest()
    arm_a = train_arm("A", initial_state, z_a, cache, train, train_positions, validation, validation_positions, orders, device, args.output)
    arm_b = train_arm("B", initial_state, z_b, cache, train, train_positions, validation, validation_positions, orders, device, args.output)
    metrics_a = metrics(arm_a.pop("head"), z_a, cache, validation, device, validation_positions)
    metrics_b = metrics(arm_b.pop("head"), z_b, cache, validation, device, validation_positions)
    def load_head(path: str) -> torch.nn.Module:
        head = torch.nn.Linear(64, 1).to(device)
        head.load_state_dict(torch.load(path, map_location=device, weights_only=False)["stateDict"], strict=True)
        return head
    head_a = load_head(arm_a["checkpoint"])
    head_b = load_head(arm_b["checkpoint"])
    reloaded_metrics_a = metrics(head_a, z_a, cache, validation, device, validation_positions)
    reloaded_metrics_b = metrics(head_b, z_b, cache, validation, device, validation_positions)
    reload_verification = {
        "A": {
            "metricsMatch": reloaded_metrics_a == metrics_a,
            "checkpointSha256": digest(Path(arm_a["checkpoint"])),
        },
        "B": {
            "metricsMatch": reloaded_metrics_b == metrics_b,
            "checkpointSha256": digest(Path(arm_b["checkpoint"])),
        },
    }
    if not all(value["metricsMatch"] for value in reload_verification.values()):
        raise ValueError("reloaded selected checkpoint metrics differ")
    slices = {}
    for label, mask in {
        "victories": cache["win"][validation],
        "deaths": ~cache["win"][validation],
        "lowPreHp": (cache["preHp"][validation] / np.maximum(cache["preMax"][validation], 1)) <= 0.25,
        "normal": ~cache.get("boss", np.zeros(len(cache["ids"]), dtype=bool))[validation],
        "boss": cache.get("boss", np.zeros(len(cache["ids"]), dtype=bool))[validation],
    }.items():
        ids = validation[mask]
        positions = np.searchsorted(target, ids)
        slices[label] = {
            "A": slice_metrics(head_a, z_a, cache, ids, device, positions),
            "B": slice_metrics(head_b, z_b, cache, ids, device, positions),
        }
    deltas = {
        "nllRelative": metrics_b["nll"] / metrics_a["nll"] - 1.0,
        "brierRelative": metrics_b["brier"] / metrics_a["brier"] - 1.0,
        "deathNllRelative": slices["deaths"]["B"]["nll"] / slices["deaths"]["A"]["nll"] - 1.0,
        "lowPreHpNllRelative": slices["lowPreHp"]["B"]["nll"] / slices["lowPreHp"]["A"]["nll"] - 1.0,
    }
    gates = {
        "coreNllRelativeMax": 0.02,
        "coreBrierRelativeMax": 0.05,
        "deathNllRelativeMax": 0.10,
        "lowPreHpNllRelativeMax": 0.10,
        "lowPreHpMinimumRows": 100,
        "lowPreHpMinimumDeaths": 1,
        "lowPreHpSupportSufficient": slices["lowPreHp"]["B"]["rows"] >= 100 and slices["lowPreHp"]["B"]["deaths"] >= 1,
    }
    failures = []
    if deltas["nllRelative"] > gates["coreNllRelativeMax"]:
        failures.append("core NLL degradation exceeds 2%")
    if deltas["brierRelative"] > gates["coreBrierRelativeMax"]:
        failures.append("core Brier degradation exceeds 5%")
    if deltas["deathNllRelative"] > gates["deathNllRelativeMax"]:
        failures.append("observed-death NLL degradation exceeds 10%")
    if gates["lowPreHpSupportSufficient"] and deltas["lowPreHpNllRelative"] > gates["lowPreHpNllRelativeMax"]:
        failures.append("low-pre-HP NLL degradation exceeds 10%")
    valid = all(metrics_x[key] for metrics_x in (metrics_a, metrics_b) for key in ("finiteLogits", "finiteProbabilities", "probabilitiesInUnitInterval"))
    if not valid:
        failures.append("finite probability validity failed")
    decision = "DEEPSET_SURVIVAL_GO" if not failures else "DEEPSET_SURVIVAL_REJECTED"
    result = {
        "schema": RECIPE["schema"],
        "decision": decision,
        "baselineSha": args.base_sha,
        "sourceSha": SOURCE_SHA,
        "corpusSha256": CORPUS_SHA,
        "provenance": {
            "preparationCacheSha256": PREPARATION_CACHE_SHA,
            "preparation": preparation,
            "referenceComponentSha256": REFERENCE_COMPONENT_SHA,
            "referenceFit": reference_fit,
            "deepSetsCheckpointSha256": DEEPSER_CHECKPOINT_SHA,
            "deepSetsReceiptSha256": DEEPSER_RECEIPT_SHA,
            "deepSetsBinding": deepset_binding,
            "representation": representation,
            "attentionRepresentationSha256": digest(args.output / "z_attention.npy"),
            "attentionRowIdsSha256": digest(args.output / "z_row_ids.npy"),
            "savedDeepSetsSampleMaxAbsError": max_error,
        },
        "population": {
            "TRAIN": {"rows": TRAIN_ROWS, "sources": int(np.unique(cache["source"][train]).size)},
            "VALIDATION": {"rows": VALIDATION_ROWS, "sources": int(np.unique(cache["source"][validation]).size)},
            "TEST": {"rows": TEST_ROWS, "encodedRows": 0, "inferenceRows": 0, "scoredRows": 0},
            "rowIdsSha256": array_digest(cache["ids"]),
            "trainValidationRowIdsSha256": array_digest(cache["ids"][target]),
        },
        "recipe": RECIPE,
        "initialization": {"headSha256": initial_digest, "byteIdentical": True},
        "batchOrderSha256": batch_order_sha,
        "reference": {"metrics": reference_metrics, "expectedValidationNll": REFERENCE_NLL},
        "fit": {"A": arm_a, "B": arm_b},
        "reloadVerification": reload_verification,
        "metrics": {"A": metrics_a, "B": metrics_b},
        "slices": slices,
        "deltas": deltas,
        "gates": gates,
        "failures": failures,
        "validity": {"finite": valid, "encodersFrozen": True, "testInferenceRows": 0},
        "uncertainty": "One fixed offline TRAIN/VALIDATION screen; no TEST, runtime, native, gameplay, OOC MCTS, promotion, or encoder fine-tuning.",
        "knowledgeImpact": "experiment evidence and current research status only; runtime defaults unchanged",
    }
    composed.base.json_dump(args.output / "results.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/potion-trajectory-v2"))
    parser.add_argument("--reference-component", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/full-union-survival-v1/component.pt"))
    parser.add_argument("--deepset-run", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"))
    parser.add_argument("--deepset-evidence", type=Path, default=ROOT / "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json")
    parser.add_argument("--representation", type=Path, default=Path("/home/philippherrmann/sts_sweep/runs/deepset-downstream-20260916-corrected"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-sha", default=BASELINE_SHA)
    main_args = parser.parse_args()
    run(main_args)


if __name__ == "__main__":
    main()
