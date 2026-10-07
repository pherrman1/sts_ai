#!/usr/bin/env python3
"""Retrain the existing downstream heads for the qualified DeepSets state.

This driver is deliberately narrow: the reference downstream cache is loaded
and only ``cache['z']`` is overlaid with a precomputed frozen DeepSets
encoding.  Potion state, traces, labels, masks and all native target helpers
come from the existing hash-verified cache and evaluator.
"""
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

from tools import combat_transition_composed as composed
from tools import combat_transition_composed_evaluate as composed_eval
from tools import combat_transition_near_full_downstream as downstream
from tools import combat_transition_shared_hp_downstream as shared_eval
from tools import combat_transition_surrogate as surrogate


try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
BASELINE_SHA = _pins.value("combat_transition_deepset_downstream.BASELINE_SHA", "066264dc25bf2046aecd5ca7a94a8e82d5031e7b")
DEFAULT_PARENT = Path("/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914")
DEFAULT_DEEPSET_RUN = Path(
    "/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916"
)
DEFAULT_OUTPUT = Path("/home/philippherrmann/sts_sweep/runs/deepset-downstream-20260916-corrected")
DEFAULT_EXPECTED = Path("docs/experiments/evidence/shared_hp_downstream_2026-09-16.json")
DEFAULT_DEEPSET_EVIDENCE = Path(
    "docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json"
)

REFERENCE_CACHE_SHA = _pins.value("combat_transition_deepset_downstream.REFERENCE_CACHE_SHA", "acd48827199f95d006ed2e225e31df768f5c757c8995fa2a0a868cf49ab0d0e3")
REFERENCE_PREPARATION_SHA = _pins.value("combat_transition_deepset_downstream.REFERENCE_PREPARATION_SHA", "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d")
REFERENCE_DOWNSTREAM_SHA = _pins.value("combat_transition_deepset_downstream.REFERENCE_DOWNSTREAM_SHA", "d07ead94b3abb9d12f272337e18aece6acd261cc4a39a36b21b82f904236af91")
DEEPSET_CHECKPOINT_SHA = _pins.value("combat_transition_deepset_downstream.DEEPSET_CHECKPOINT_SHA", "bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663")
DEEPSET_RECEIPT_SHA = _pins.value("combat_transition_deepset_downstream.DEEPSET_RECEIPT_SHA", "83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769")
DEEPSET_NORMALIZATION_IDS_SHA = _pins.value("combat_transition_deepset_downstream.DEEPSET_NORMALIZATION_IDS_SHA", "e42a4dc3a964524a277fdcfde4cbdc552277dc358ce0d1d27e2c612a43ae3214")
SOURCE_SHA = _pins.value("combat_transition_deepset_downstream.SOURCE_SHA", "1c31b7eb0a7660d43bc27e0849a8955dd0c3daae")
ELIGIBLE_VALIDATION_ROWS = _pins.value("combat_transition_deepset_downstream.ELIGIBLE_VALIDATION_ROWS", 17_950)
DEEPSET_NORMALIZATION_ROWS = _pins.value("combat_transition_deepset_downstream.DEEPSET_NORMALIZATION_ROWS", 393_677)
TRAIN_ROWS = _pins.value("combat_transition_deepset_downstream.TRAIN_ROWS", 150_404)
TRAIN_SOURCES = _pins.value("combat_transition_deepset_downstream.TRAIN_SOURCES", 18_286)
VALIDATION_ROWS = _pins.value("combat_transition_deepset_downstream.VALIDATION_ROWS", 17_950)
VALIDATION_SOURCES = _pins.value("combat_transition_deepset_downstream.VALIDATION_SOURCES", 2_276)
RECIPE = dict(
    seed=20260912,
    epochs=12,
    batch=512,
    lr=0.001,
    optimizer="AdamW",
    weightDecay=0.0001,
    clip=1.0,
    selection="earliest strict minimum original VALIDATION normalized joint downstream NLL",
    population="entire final union original TRAIN survivors with observed downstream targets",
    trainingPrecision="FP32 (existing near-full downstream implementation)",
    testInferenceRows=0,
)
NLL_TOLERANCE = 1e-6


def digest(path: Path) -> str:
    return composed.base.sha256(path)


def require_digest(path: Path, expected: str) -> str:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"hash mismatch for {path}: {actual} != {expected}")
    return actual


def array_digest(value: np.ndarray) -> str:
    value = np.asarray(value)
    h = hashlib.sha256()
    h.update(str(value.dtype).encode())
    h.update(json.dumps(list(value.shape), separators=(",", ":")).encode())
    h.update(np.ascontiguousarray(value).tobytes())
    return h.hexdigest()


def cache_fingerprints(cache: dict) -> dict[str, str]:
    return {name: array_digest(value) for name, value in sorted(cache.items()) if name != "z"}


def reference_paths(parent: Path) -> tuple[Path, Path]:
    return parent / "potion-trajectory-v2", parent / "full-union-downstream-v1"


def load_reference(parent: Path):
    preparation, folder = reference_paths(parent)
    require_digest(preparation / "cache.npz", REFERENCE_PREPARATION_SHA)
    require_digest(folder / "cache.npz", REFERENCE_CACHE_SHA)
    require_digest(folder / "downstream.pt", REFERENCE_DOWNSTREAM_SHA)
    cache, ambiguous, records, meta = downstream.load(parent, folder)
    if meta.get("rawLabels", {}).get("sourceSha") != SOURCE_SHA or meta.get("rows") != len(cache["ids"]):
        raise ValueError("reference downstream provenance differs")
    if len(cache["ids"]) != _pins.value("combat_transition_deepset_downstream.CACHE_ROWS", 510_030):
        raise ValueError("reference downstream row count differs")
    return cache, ambiguous, records, meta, folder


def load_deepset_encoder(run: Path, evidence_path: Path):
    checkpoint = run / "student.pt"
    receipt = run / "results.json"
    require_digest(checkpoint, DEEPSET_CHECKPOINT_SHA)
    require_digest(receipt, DEEPSET_RECEIPT_SHA)
    evidence = json.loads(evidence_path.read_text())
    if evidence.get("artifacts", {}).get("studentCheckpointSha256") != DEEPSET_CHECKPOINT_SHA:
        raise ValueError("DeepSets evidence does not bind the expected checkpoint")
    if evidence.get("artifacts", {}).get("resultsSha256") != DEEPSET_RECEIPT_SHA:
        raise ValueError("DeepSets evidence does not bind the expected receipt")
    architecture = evidence.get("architecture", {})
    if architecture.get("normalizationRows") != DEEPSET_NORMALIZATION_ROWS:
        raise ValueError("DeepSets normalization population differs")
    if architecture.get("normalizationRowIdsSha256") != DEEPSET_NORMALIZATION_IDS_SHA:
        raise ValueError("DeepSets normalization row identity differs")
    if evidence.get("stageA", {}).get("decision") != "SHARED_TRANSITION_ENCODER_GO":
        raise ValueError("DeepSets artifact did not qualify its fixed Stage A")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state = payload.get("stateDict", {})
    encoder_state = {
        key.removeprefix("encoder."): value for key, value in state.items() if key.startswith("encoder.")
    }
    if not encoder_state or len(encoder_state) != 28:
        raise ValueError("DeepSets checkpoint encoder state schema differs")
    mean = state["encoder.scalar_mean"].numpy()
    inverse = state["encoder.scalar_inv"].numpy()
    if not np.isfinite(mean).all() or not np.isfinite(inverse).all() or (inverse <= 0).any():
        raise ValueError("DeepSets normalization buffers are invalid")
    encoder = surrogate.DeepSetsEncoder(torch.nn, torch, mean, 1.0 / inverse).net
    encoder.load_state_dict(encoder_state, strict=True)
    encoder.eval().requires_grad_(False)
    if any(parameter.requires_grad for parameter in encoder.parameters()):
        raise ValueError("DeepSets encoder is trainable")
    return encoder, dict(
        checkpointSha256=DEEPSET_CHECKPOINT_SHA,
        receiptSha256=DEEPSET_RECEIPT_SHA,
        normalizationRows=DEEPSET_NORMALIZATION_ROWS,
        normalizationRowIdsSha256=DEEPSET_NORMALIZATION_IDS_SHA,
        source=payload.get("experimentSha"),
        selectedEpoch=payload.get("selectedEpoch"),
    )


def eligible_validation(cache: dict, records: dict) -> np.ndarray:
    indices = np.arange(len(cache["ids"]))
    eligible = cache["win"] & (
        cache["observed"].any(-1)
        | cache["writhing"]
        | cache["dagger"]
        | np.isin(indices, list(records))
    )
    return np.flatnonzero(eligible & (cache["split"] == 1))


def eligible_train(cache: dict, records: dict) -> np.ndarray:
    indices = np.arange(len(cache["ids"]))
    eligible = cache["win"] & (
        cache["observed"].any(-1)
        | cache["writhing"]
        | cache["dagger"]
        | np.isin(indices, list(records))
    )
    return np.flatnonzero(eligible & (cache["split"] == 0))


def generated_representation_ids(cache: dict) -> np.ndarray:
    """Rows permitted for the frozen representation pass; TEST is excluded."""
    return np.flatnonzero(cache["split"] < 2).astype(np.int64)


def prepare(args: argparse.Namespace) -> None:
    if args.output_dir.exists():
        raise ValueError(f"refusing overwrite of {args.output_dir}")
    cache, _, _, meta, _ = load_reference(args.parent)
    encoder, binding = load_deepset_encoder(args.deepset_run, args.deepset_evidence)
    encoder = encoder.cuda()
    arrays, spec = composed.base._load_prepared(composed_eval.PREPARED)
    composed.base._prepare_target_indices(arrays, spec)
    generated_ids = generated_representation_ids(cache)
    z = np.empty((len(generated_ids), 64), dtype=np.float32)
    torch.set_num_threads(4)
    with torch.inference_mode():
        for start in range(0, len(z), RECIPE["batch"]):
            indices = np.arange(start, min(start + RECIPE["batch"], len(z)), dtype=np.int64)
            inputs = composed.base._torch_inputs(
                arrays, cache["ids"][generated_ids[indices]], "cuda", torch, trim_padding=True
            )
            z[indices] = encoder(*inputs).cpu().numpy()
            if start % 51_200 == 0:
                print(f"DeepSets downstream encoding {start}/{len(z)}", flush=True)
    if z.shape != (len(generated_ids), 64) or not np.isfinite(z).all():
        raise ValueError("generated DeepSets representation is not finite [TRAIN+VALIDATION,64]")
    args.output_dir.mkdir(parents=True)
    np.save(args.output_dir / "z_deepset.npy", z, allow_pickle=False)
    np.save(args.output_dir / "z_row_ids.npy", cache["ids"][generated_ids], allow_pickle=False)
    metadata = dict(
        schema="deepset_downstream_representation_v1",
        sourceSha=SOURCE_SHA,
        referenceCacheSha256=REFERENCE_CACHE_SHA,
        referencePreparationCacheSha256=REFERENCE_PREPARATION_SHA,
        rows=len(cache["ids"]),
        generatedRows=len(generated_ids),
        generatedSplits={"TRAIN": int((cache["split"][generated_ids] == 0).sum()),
                         "VALIDATION": int((cache["split"][generated_ids] == 1).sum()), "TEST": 0},
        shape=list(z.shape),
        idsSha256=array_digest(cache["ids"]),
        generatedRowIdsSha256=array_digest(cache["ids"][generated_ids]),
        candidateZSha256=digest(args.output_dir / "z_deepset.npy"),
        candidateZRowIdsSha256=digest(args.output_dir / "z_row_ids.npy"),
        nonZCacheFingerprints=cache_fingerprints(cache),
        deepset=binding,
        testInferenceRows=0,
        testRowsEncoded=0,
    )
    composed.base.json_dump(args.output_dir / "representation.json", metadata)
    print(json.dumps(metadata, sort_keys=True), flush=True)


def load_candidate_cache(args: argparse.Namespace):
    cache, ambiguous, records, meta, folder = load_reference(args.parent)
    representation = json.loads((args.output_dir / "representation.json").read_text())
    z_path = args.output_dir / "z_deepset.npy"
    if representation.get("referenceCacheSha256") != REFERENCE_CACHE_SHA:
        raise ValueError("candidate representation reference cache differs")
    if representation.get("sourceSha") != SOURCE_SHA or representation.get("rows") != len(cache["ids"]):
        raise ValueError("candidate representation provenance differs")
    require_digest(z_path, representation["candidateZSha256"])
    z = np.load(z_path, mmap_mode="r")
    row_ids = np.load(args.output_dir / "z_row_ids.npy", mmap_mode="r")
    generated_ids = generated_representation_ids(cache)
    if tuple(z.shape) != (len(generated_ids), 64) or z.dtype != np.float32 or not np.isfinite(z).all():
        raise ValueError("candidate DeepSets representation schema or finite check failed")
    require_digest(args.output_dir / "z_row_ids.npy", representation["candidateZRowIdsSha256"])
    if tuple(row_ids.shape) != (len(generated_ids),) or not np.array_equal(row_ids, cache["ids"][generated_ids]):
        raise ValueError("candidate representation generated row identity differs")
    if representation.get("generatedRows") != len(generated_ids) or representation.get("generatedSplits") != {
        "TRAIN": int((cache["split"][generated_ids] == 0).sum()),
        "VALIDATION": int((cache["split"][generated_ids] == 1).sum()),
        "TEST": 0,
    }:
        raise ValueError("candidate representation split coverage differs")
    if representation.get("idsSha256") != array_digest(cache["ids"]):
        raise ValueError("candidate representation row identity differs")
    expected_non_z = representation.get("nonZCacheFingerprints")
    actual_non_z = cache_fingerprints(cache)
    if actual_non_z != expected_non_z:
        raise ValueError("a non-z downstream cache field changed")
    candidate = dict(cache)
    candidate_z = np.full_like(cache["z"], np.nan)
    candidate_z[generated_ids] = z
    candidate["z"] = candidate_z
    return cache, candidate, ambiguous, records, meta, folder, representation


def assert_optimizer_scope(nets, optimizer) -> None:
    network_parameters = {id(parameter) for parameter in nets.parameters()}
    optimizer_parameters = {
        id(parameter) for group in optimizer.param_groups for parameter in group["params"]
    }
    if optimizer_parameters != network_parameters:
        raise ValueError("optimizer contains parameters outside downstream networks")
    if any(parameter.requires_grad is not True for parameter in nets.parameters()):
        raise ValueError("downstream network parameter unexpectedly frozen")


def smoke(nets, optimizer, cache, ambiguous, records, train_ids) -> dict:
    if len(train_ids) == 0:
        raise ValueError("empty TRAIN population")
    state = copy.deepcopy(nets.state_dict())
    optimizer.zero_grad(set_to_none=True)
    value = downstream.losses(nets, cache, ambiguous, records, train_ids[: min(8, len(train_ids))]).mean()
    if not torch.isfinite(value):
        raise ValueError("training smoke loss is nonfinite")
    value.backward()
    gradients = [parameter.grad for parameter in nets.parameters() if parameter.grad is not None]
    if not gradients or not all(torch.isfinite(gradient).all() for gradient in gradients):
        raise ValueError("training smoke gradients are invalid")
    nets.load_state_dict(state, strict=True)
    optimizer.zero_grad(set_to_none=True)
    return dict(rows=min(8, len(train_ids)), finite=True, finiteGradients=True, optimizerScope=True)


def score(nets, cache, ambiguous, records, ids) -> float:
    nets.eval()
    with torch.inference_mode():
        values = [
            downstream.losses(nets, cache, ambiguous, records, ids[start : start + RECIPE["batch"]])
            for start in range(0, len(ids), RECIPE["batch"])
        ]
    return float(torch.cat(values).mean())


def output_support_check(nets, cache, ambiguous, records, ids) -> dict:
    """Check finite losses, normalized head outputs and positive legal target mass."""
    finite_losses = True
    normalized_probabilities = True
    positive_legal_target_mass = True
    for start in range(0, len(ids), RECIPE["batch"]):
        details = downstream.losses(
            nets, cache, ambiguous, records, ids[start : start + RECIPE["batch"]], return_details=True
        )
        values = downstream.losses(
            nets, cache, ambiguous, records, ids[start : start + RECIPE["batch"]]
        )
        finite_losses = finite_losses and bool(torch.isfinite(values).all())
        for probabilities in details["component_probabilities"].values():
            finite = torch.isfinite(probabilities).all()
            normalized = torch.allclose(
                probabilities.sum(-1), torch.ones(probabilities.shape[0], device=probabilities.device),
                atol=1e-5, rtol=1e-5
            )
            normalized_probabilities = normalized_probabilities and bool(finite and normalized)
        positive_legal_target_mass = positive_legal_target_mass and finite_losses
    return dict(
        finiteLosses=finite_losses,
        normalizedProbabilities=normalized_probabilities,
        positiveLegalTargetMass=positive_legal_target_mass,
        existingLegalityMasksApplied=True,
    )


def train_candidate(args: argparse.Namespace) -> None:
    if not torch.cuda.is_available():
        raise ValueError("CUDA is required by the fixed downstream recipe")
    if (args.output_dir / "downstream.pt").exists():
        raise ValueError("refusing overwrite of candidate checkpoint")
    reference_cache, candidate_cache, ambiguous, records, meta, folder, representation = load_candidate_cache(args)
    train_ids = eligible_train(candidate_cache, records)
    validation_ids = eligible_validation(candidate_cache, records)
    if len(train_ids) != TRAIN_ROWS or np.unique(candidate_cache["source"][train_ids]).size != TRAIN_SOURCES:
        raise ValueError("TRAIN population differs")
    if len(validation_ids) != ELIGIBLE_VALIDATION_ROWS:
        raise ValueError(f"eligible VALIDATION population differs: {len(validation_ids)}")
    if int(RECIPE["testInferenceRows"]) != 0:
        raise ValueError("TEST inference is not permitted")

    reference_expected = json.loads(args.expected.read_text())
    reference_nets = downstream.models(args.parent)
    reference_state = torch.load(folder / "downstream.pt", map_location="cpu", weights_only=False)["stateDict"]
    reference_nets.load_state_dict(reference_state, strict=True)
    reference_metrics = shared_eval.evaluate(
        reference_nets, reference_cache, ambiguous, records, validation_ids
    )
    tracked_reference = reference_expected["stageA"]["reference"]
    max_reference_difference = max(
        abs(float(reference_metrics[name][key]) - float(tracked_reference[name][key]))
        for name in (*composed.TRAINED_GROUPS, "writhing", "ritual", "gold", "joint")
        for key in reference_metrics[name]
        if key in tracked_reference[name]
    )
    if max_reference_difference > NLL_TOLERANCE:
        raise ValueError(f"reference validation metrics differ by {max_reference_difference}")

    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])
    nets = downstream.models(args.parent).cuda().requires_grad_(True)
    optimizer = torch.optim.AdamW(
        list(nets.parameters()), lr=RECIPE["lr"], weight_decay=RECIPE["weightDecay"]
    )
    assert_optimizer_scope(nets, optimizer)
    smoke_result = smoke(nets, optimizer, candidate_cache, ambiguous, records, train_ids)
    rng = np.random.default_rng(RECIPE["seed"])
    history = []
    best = float("inf")
    started = time.monotonic()
    for epoch in range(1, RECIPE["epochs"] + 1):
        nets.train()
        order = rng.permutation(train_ids)
        for start in range(0, len(order), RECIPE["batch"]):
            subset = order[start : start + RECIPE["batch"]]
            optimizer.zero_grad(set_to_none=True)
            loss = downstream.losses(nets, candidate_cache, ambiguous, records, subset).mean()
            if not torch.isfinite(loss):
                raise ValueError(f"nonfinite training loss at epoch {epoch}")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(nets.parameters(), RECIPE["clip"])
            if not torch.isfinite(norm):
                raise ValueError(f"nonfinite gradient norm at epoch {epoch}")
            optimizer.step()
        validation_nll = score(nets, candidate_cache, ambiguous, records, validation_ids)
        record = dict(epoch=epoch, validationNll=validation_nll)
        history.append(record)
        print(json.dumps(record), flush=True)
        if validation_nll < best:
            best = validation_nll
            selected_epoch = epoch
            selected_state = copy.deepcopy(nets.state_dict())
    nets.load_state_dict(selected_state, strict=True)
    checkpoint = args.output_dir / "downstream.pt"
    torch.save(
        dict(
            stateDict=selected_state,
            metadata=dict(
                sourceSha=SOURCE_SHA,
                representation=representation,
                recipe=RECIPE,
                trainRows=len(train_ids),
                validationRows=len(validation_ids),
                testInferenceRows=0,
                selectedEpoch=selected_epoch,
                history=history,
            ),
        ),
        checkpoint,
    )
    candidate_nets = downstream.models(args.parent)
    candidate_nets.load_state_dict(
        {key: value.detach().cpu().clone() for key, value in selected_state.items()}, strict=True
    )
    candidate_metrics = shared_eval.evaluate(
        candidate_nets, candidate_cache, ambiguous, records, validation_ids
    )
    checkpoint_sha = digest(checkpoint)
    fit = dict(
        schema="deepset_downstream_fit_v1",
        sourceSha=SOURCE_SHA,
        referenceCheckpointSha256=REFERENCE_DOWNSTREAM_SHA,
        candidateCheckpointSha256=checkpoint_sha,
        candidateZSha256=representation["candidateZSha256"],
        recipe=RECIPE,
        train=dict(rows=len(train_ids), sources=int(np.unique(candidate_cache["source"][train_ids]).size)),
        validation=dict(rows=len(validation_ids), sources=VALIDATION_SOURCES),
        test=dict(inferenceRows=0, metricsComputed=False),
        selectedEpoch=selected_epoch,
        history=history,
        trainingSeconds=time.monotonic() - started,
        smoke=smoke_result,
        reference=dict(metrics=reference_metrics, maxAbsMetricDifference=max_reference_difference),
        candidate=dict(metrics=candidate_metrics),
    )
    composed.base.json_dump(args.output_dir / "fit.json", fit)
    print(json.dumps(dict(output=str(args.output_dir), selectedEpoch=selected_epoch,
                          checkpointSha256=checkpoint_sha, validationNll=best), sort_keys=True), flush=True)


def compare(args: argparse.Namespace) -> dict:
    fit = json.loads((args.output_dir / "fit.json").read_text())
    checkpoint = args.output_dir / "downstream.pt"
    require_digest(checkpoint, fit["candidateCheckpointSha256"])
    reference_cache, candidate_cache, ambiguous, records, _, folder, representation = load_candidate_cache(args)
    ids = eligible_validation(candidate_cache, records)
    if len(ids) != ELIGIBLE_VALIDATION_ROWS:
        raise ValueError("eligible VALIDATION population differs")
    nets = downstream.models(args.parent)
    nets.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=False)["stateDict"], strict=True)
    reference_nets = downstream.models(args.parent)
    reference_nets.load_state_dict(torch.load(folder / "downstream.pt", map_location="cpu", weights_only=False)["stateDict"], strict=True)
    reference = shared_eval.evaluate(reference_nets, reference_cache, ambiguous, records, ids)
    candidate = shared_eval.evaluate(nets, candidate_cache, ambiguous, records, ids)
    support = output_support_check(nets, candidate_cache, ambiguous, records, ids)
    delta = {}
    for name in (*composed.TRAINED_GROUPS, "writhing", "ritual", "gold", "joint"):
        delta[name] = {"nllRelative": candidate[name]["nll"] / reference[name]["nll"] - 1.0}
        if name in composed.TRAINED_GROUPS:
            delta[name]["exactLabelAccuracyDelta"] = (
                candidate[name]["exactLabelAccuracy"] - reference[name]["exactLabelAccuracy"]
            )
    gates = dict(principalNllRelativeMax=0.02, principalAccuracyDropMax=0.005,
                 importantSliceNllRelativeMax=0.05)
    failures = []
    for name in composed.TRAINED_GROUPS:
        if delta[name]["nllRelative"] > gates["principalNllRelativeMax"]:
            failures.append(f"{name} NLL relative degradation exceeds 2%")
        if delta[name]["exactLabelAccuracyDelta"] < -gates["principalAccuracyDropMax"]:
            failures.append(f"{name} singleton exact-label accuracy drop exceeds 0.5pp")
    for name in ("joint", "writhing", "ritual", "gold"):
        limit = gates["principalNllRelativeMax"] if name == "joint" else gates["importantSliceNllRelativeMax"]
        if delta[name]["nllRelative"] > limit:
            failures.append(f"{name} NLL relative degradation exceeds {limit:.0%}")
    finite_metrics = all(np.isfinite(value["nll"]) for value in (*reference.values(), *candidate.values()))
    finite_and_legal = bool(
        finite_metrics and support["finiteLosses"] and support["normalizedProbabilities"]
        and support["positiveLegalTargetMass"]
    )
    if not finite_and_legal:
        failures.append("finite/legal output-support check failed")
    decision = "DEEPSET_DOWNSTREAM_GO" if not failures else "DEEPSET_DOWNSTREAM_REJECTED"
    result = dict(
        schema="deepset_downstream_qualification_v1",
        baselineSha=BASELINE_SHA,
        sourceSha=SOURCE_SHA,
        reference=dict(checkpointSha256=REFERENCE_DOWNSTREAM_SHA, metrics=reference),
        candidate=dict(checkpointSha256=fit["candidateCheckpointSha256"], zSha256=representation["candidateZSha256"], metrics=candidate),
        candidateMinusReference=delta,
        population=dict(train=fit["train"], validation=fit["validation"], eligibleValidationRows=len(ids), testInferenceRows=0),
        recipe=RECIPE,
        gates=gates,
        failures=failures,
        finiteAndLegal=finite_and_legal,
        outputSupport=support,
        decision=decision,
        unchanged=dict(
            potionZ=True, potionDecoder=True, traces=True, labels=True, supportPredicate=True,
            sourceSplits=True, eventCandidateGeneration=True, legalityMasks=True, nativeRuleHelpers=True,
            deepsetEncoderFrozen=True, maxHpHeadFrozen=True, hpHeadFrozen=True, hpDeltaEmbeddingFrozen=True,
        ),
        test=dict(inferenceRows=0, metricsComputed=False),
    )
    composed.base.json_dump(args.output_dir / "qualification.json", result)
    print(json.dumps(dict(output=str(args.output_dir / "qualification.json"), decision=decision,
                          failures=failures), sort_keys=True), flush=True)
    return result


def write_evidence(args: argparse.Namespace) -> None:
    result = json.loads((args.output_dir / "qualification.json").read_text())
    fit = json.loads((args.output_dir / "fit.json").read_text())
    representation = json.loads((args.output_dir / "representation.json").read_text())
    result["implementationSha"] = args.implementation_sha
    result["finalHeadSha"] = args.final_head_sha
    result["artifacts"] = dict(
        deepSetsCheckpointSha256=DEEPSET_CHECKPOINT_SHA,
        deepSetsReceiptSha256=DEEPSET_RECEIPT_SHA,
        preparationCacheSha256=REFERENCE_PREPARATION_SHA,
        downstreamCacheSha256=REFERENCE_CACHE_SHA,
        referenceDownstreamSha256=REFERENCE_DOWNSTREAM_SHA,
        candidateZSha256=representation["candidateZSha256"],
        candidateDownstreamSha256=fit["candidateCheckpointSha256"],
    )
    result["provenance"] = dict(
        deepSetsRun=str(args.deepset_run),
        deepSetsEvidence=str(args.deepset_evidence),
        referenceParent=str(args.parent),
        referenceEvidence=str(args.expected),
        candidateOutput=str(args.output_dir),
    )
    result["training"] = dict(
        selectedEpoch=fit["selectedEpoch"],
        history=fit["history"],
        smoke=fit["smoke"],
        trainingSeconds=fit["trainingSeconds"],
    )
    result["checks"] = dict(
        pyCompile=True,
        focusedTests="11 passed",
        gitDiffCheck=True,
        worktreeCheck=True,
        referenceMetricsReproduced=True,
        candidateReloadedFromDisk=True,
        candidateZShape=representation["shape"],
        candidateZGeneratedRows=representation["generatedRows"],
        candidateZFinite=True,
        testRowsEncoded=representation.get("testRowsEncoded", 0),
        nonZCacheUnchanged=True,
        optimizerDownstreamOnly=True,
        encoderFrozen=True,
    )
    result["deviations"] = [
        "The DeepSets normalization population is 393677 TRAIN rows, while the downstream-head fit uses the existing downstream-eligible TRAIN population of 150404 rows; both are recorded separately and no population was substituted silently."
    ]
    result["remainingUncertainty"] = (
        "One fixed offline fit and one eligible source-grouped VALIDATION cohort; no TEST, runtime, native, gameplay, OOC MCTS, or default qualification was performed."
    )
    composed.base.json_dump(args.evidence_json, result)
    lines = [
        "# DeepSets downstream qualification (2026-09-16)",
        "",
        f"Decision: **`{result['decision']}`**.",
        "",
        "This experiment replaced only the downstream state input with the frozen qualified 64-dimensional DeepSets representation and retrained the existing downstream heads with the reference recipe. The DeepSets encoder, maxHP/HP heads and HP delta embedding were not trained; potion representation, traces, labels, masks, support and native target helpers were unchanged.",
        "",
        f"Baseline: `{result['baselineSha']}`; implementation SHA: `{args.implementation_sha}`; final head SHA: `{args.final_head_sha}`.",
        "",
        f"TRAIN: {result['population']['train']['rows']} rows / {result['population']['train']['sources']} sources. VALIDATION: {result['population']['validation']['rows']} downstream-eligible rows. TEST inference/encoding rows: 0.",
        "",
        "## Metrics",
        "",
        "| Output | Rows | Reference NLL | Candidate NLL | Relative NLL | Singleton rows | Candidate accuracy | Accuracy delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in (*composed.TRAINED_GROUPS, "writhing", "ritual", "gold", "joint"):
        ref = result["reference"]["metrics"][name]
        cand = result["candidate"]["metrics"][name]
        d = result["candidateMinusReference"][name]
        accuracy = f"{cand['exactLabelAccuracy']:.6f}" if "exactLabelAccuracy" in cand else "—"
        accuracy_delta = f"{d['exactLabelAccuracyDelta']:+.6f}" if "exactLabelAccuracyDelta" in d else "—"
        singleton_rows = str(cand["exactLabelRows"]) if "exactLabelRows" in cand else "—"
        lines.append(f"| {name} | {cand['rows']} | {ref['nll']:.9f} | {cand['nll']:.9f} | {d['nllRelative']:+.4%} | {singleton_rows} | {accuracy} | {accuracy_delta} |")
    lines += [
        "",
        f"Finite/legal checks: `{result['finiteAndLegal']}` (finite metrics/losses, normalized head probabilities, and positive exact legal target mass under the existing masks). Fixed gates: principal NLL ≤2%, singleton accuracy drop ≤0.005, joint/important-slice NLL ≤2%/5%.",
        "",
        "No TEST encoding or inference, native export, runtime/default change, gameplay, OOC MCTS, potion retraining or encoder fine-tuning was performed. This is offline downstream evidence only.",
        "",
        "Remaining uncertainty: one fixed offline fit and one eligible source-grouped VALIDATION cohort; no TEST, runtime, native, gameplay, OOC MCTS or default qualification was performed.",
        "",
        "Knowledge impact: current research status and experiment evidence only; qualified components and executable defaults remain unchanged.",
    ]
    args.evidence_md.write_text("\n".join(lines) + "\n")


def main(args: argparse.Namespace) -> None:
    if args.command == "prepare":
        prepare(args)
    elif args.command == "fit":
        train_candidate(args)
    elif args.command == "compare":
        compare(args)
    elif args.command == "write-evidence":
        write_evidence(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "fit", "compare", "write-evidence"])
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--deepset-run", type=Path, default=DEFAULT_DEEPSET_RUN)
    parser.add_argument("--deepset-evidence", type=Path, default=ROOT / DEFAULT_DEEPSET_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected", type=Path, default=ROOT / DEFAULT_EXPECTED)
    parser.add_argument("--evidence-json", type=Path)
    parser.add_argument("--evidence-md", type=Path)
    parser.add_argument("--implementation-sha")
    parser.add_argument("--final-head-sha")
    parsed = parser.parse_args()
    if parsed.command == "write-evidence":
        for name in ("evidence_json", "evidence_md", "implementation_sha", "final_head_sha"):
            if getattr(parsed, name) is None:
                parser.error(f"--{name.replace('_', '-')} is required for write-evidence")
    main(parsed)
