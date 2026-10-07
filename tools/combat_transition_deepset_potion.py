#!/usr/bin/env python3
"""Frozen qualified DeepSets representation screen for potion trajectories.

This is a TRAIN/VALIDATION-only representation substitution test.  The
corrected PR #205 DeepSets encoder, its maxHP head, HP delta embedding and HP
head remain frozen.  Only two freshly and byte-identically initialized potion
decoders are trained, using the exact trajectory machinery from the
historical shared-potion screen.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

try:
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    from tools import combat_transition_shared_potion_encoder as shared
    from tools import combat_transition_surrogate as surrogate
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import combat_transition_composed as composed
    import combat_transition_composed_evaluate as composed_evaluate
    import combat_transition_potion_trajectory as trajectory
    import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    import combat_transition_shared_potion_encoder as shared
    import combat_transition_surrogate as surrogate


RECIPE = {
    "schema": "deepset_potion_screen_v1",
    "seed": 20260912,
    "precision": "fp32",
    "epochs": 12,
    "batch": 512,
    "lr": 1e-3,
    "weightDecay": 1e-4,
    "gradientClip": 1.0,
    "selection": "earliest strict minimum VALIDATION exact trajectory NLL",
    "training": "decoder-only; frozen encoder representations cached once",
    "trajectory": shared.RECIPE["trajectory"],
    "population": "current final-union source-grouped TRAIN/VALIDATION winning rows",
    "testInferenceRows": 0,
    "ancestralDraws": 32,
    "ancestralSeed": 20260920,
    "ancestralBoundaryNat": 0.1,
}

try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
EXPECTED = _pins.value("combat_transition_deepset_potion.EXPECTED", {
    "baseline": "b0704c755a78fc139c6859781ce899c230919a44",
    "candidateCheckpoint": "bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663",
    "candidateReceipt": "83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769",
    "candidateZ": "9232027d8331fd2157727276410161e3c12816b6680cb116ebc2b3afd37352af",
    "candidateRows": 458589,
    "rowSequence": "2cb23f2eac81cd30f0200c49d42f090873b5452b265bb47410d67c46d6745809",
    "sourceSequence": "d843fcf1f106e8985aef32087c12745da9dfca6f050c64bcca44837578718b32",
    "splitSequence": "607782399125f7785c3a33f65934c9461b8b1e86f053637e8110f51a2294f3ca",
    "dedicatedPotionComponent": "ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db",
    "cache": "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d",
    "sourceSha": "1c31b7eb0a7660d43bc27e0849a8955dd0c3daae",
})


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_candidate(checkpoint: Path, receipt_path: Path) -> dict:
    checkpoint_sha = composed.base.sha256(checkpoint)
    receipt_sha = composed.base.sha256(receipt_path)
    if checkpoint_sha != EXPECTED["candidateCheckpoint"]:
        raise ValueError(f"DeepSets checkpoint hash differs: {checkpoint_sha}")
    if receipt_sha != EXPECTED["candidateReceipt"]:
        raise ValueError(f"DeepSets receipt hash differs: {receipt_sha}")
    receipt = load_json(receipt_path)
    if receipt.get("decision") != "SHARED_TRANSITION_ENCODER_GO":
        raise ValueError("DeepSets checkpoint was not qualified")
    if receipt.get("checkpointSha256") != checkpoint_sha or receipt.get("selectedEpoch") != 40:
        raise ValueError("DeepSets checkpoint receipt differs")
    if receipt.get("provenance", {}).get("preparationCacheSha256") != EXPECTED["cache"] or receipt.get("testInferenceRows") != 0:
        raise ValueError("DeepSets result provenance differs")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if payload.get("selectedEpoch") != 40 or payload.get("experimentSha") != "b192275ca0584a0c1eee8916176613b428a5e1b4":
        raise ValueError("DeepSets embedded provenance differs")
    if not {"stateDict", "maxHpHeadStateDict"} <= set(payload):
        raise ValueError("DeepSets checkpoint schema differs")
    return payload


def load_deepset_encoder(payload: dict, device: str):
    width = len(composed.base.CONTINUOUS_GLOBAL_FIELDS)
    encoder = surrogate.DeepSetsEncoder(
        torch.nn, torch, np.zeros(width, np.float32), np.ones(width, np.float32)
    ).net
    source = {key[len("encoder."):]: value for key, value in payload["stateDict"].items() if key.startswith("encoder.")}
    if set(source) != set(encoder.state_dict()):
        raise ValueError("DeepSets encoder state-dict keys differ")
    encoder.load_state_dict(source, strict=True)
    encoder.to(device).eval().requires_grad_(False)
    if any(parameter.requires_grad for parameter in encoder.parameters()):
        raise ValueError("DeepSets encoder is not frozen")
    return encoder


def map_candidate_z(representation_dir: Path, cache: dict, train: np.ndarray, validation: np.ndarray):
    metadata = load_json(representation_dir / "representation.json")
    z_path = representation_dir / "z_deepset.npy"
    row_ids_path = representation_dir / "z_row_ids.npy"
    z_sha = composed.base.sha256(z_path)
    row_ids_sha = composed.base.sha256(row_ids_path)
    if metadata.get("candidateZSha256") != z_sha or z_sha != EXPECTED["candidateZ"]:
        raise ValueError("DeepSets representation hash differs")
    if metadata.get("generatedRows") != EXPECTED["candidateRows"] or metadata.get("testRowsEncoded") != 0 or metadata.get("testInferenceRows") != 0:
        raise ValueError("DeepSets representation population differs")
    if metadata.get("referencePreparationCacheSha256") != EXPECTED["cache"] or metadata.get("sourceSha") != EXPECTED["sourceSha"]:
        raise ValueError("DeepSets representation provenance differs")
    z = np.load(z_path, allow_pickle=False)
    row_ids = np.load(row_ids_path, allow_pickle=False)
    if z.shape != (EXPECTED["candidateRows"], 64) or row_ids.shape != (EXPECTED["candidateRows"],):
        raise ValueError("DeepSets representation shape differs")
    if row_ids.dtype.kind not in "iu" or len(np.unique(row_ids)) != len(row_ids):
        raise ValueError("DeepSets row IDs are not unique integers")
    positions = {int(row_id): index for index, row_id in enumerate(row_ids)}
    cache_positions = {int(row_id): index for index, row_id in enumerate(cache["ids"])}
    missing_cache = [int(row_id) for row_id in row_ids if int(row_id) not in cache_positions]
    if missing_cache:
        raise ValueError(f"DeepSets representation has unknown potion rows: {missing_cache[:3]}")
    target = np.concatenate((train, validation))
    target_row_ids = cache["ids"][target]
    missing = [int(row_id) for row_id in target_row_ids if int(row_id) not in positions]
    if missing:
        raise ValueError(f"DeepSets representation misses potion rows: {missing[:3]}")
    compact = np.asarray([positions[int(row_id)] for row_id in target_row_ids], dtype=np.int64)
    candidate_cache_indices = np.asarray([cache_positions[int(row_id)] for row_id in row_ids], dtype=np.int64)
    if np.any(cache["split"][target] == 2) or np.any(cache["split"][candidate_cache_indices] == 2):
        raise ValueError("TEST row entered DeepSets representation")
    candidate_splits = cache["split"][candidate_cache_indices]
    generated_splits = {
        "TRAIN": int(np.sum(candidate_splits == 0)),
        "VALIDATION": int(np.sum(candidate_splits == 1)),
        "TEST": int(np.sum(candidate_splits == 2)),
    }
    if generated_splits != metadata.get("generatedSplits"):
        raise ValueError(f"DeepSets split census differs: {generated_splits}")
    mapped = np.zeros((len(cache["ids"]), 64), dtype=np.float32)
    mapped[target] = z[compact]
    return mapped, {"candidateZSha256": z_sha, "candidateZRowIdsSha256": row_ids_sha,
                    "generatedRows": int(len(row_ids)), "generatedSplits": generated_splits,
                    "mappedPotionRows": int(len(target)), "mappedRowIdsSha256": shared.digest(target_row_ids)}


def verify_cached_sample(encoder, arrays: dict, cache: dict, target: np.ndarray, z: np.ndarray, device: str) -> float:
    sample = target[:8]
    compact = z[sample]
    inputs = composed.base._torch_inputs(arrays, cache["ids"][sample], device, torch, trim_padding=True)
    with torch.inference_mode():
        actual = encoder(*inputs).float().cpu().numpy()
    error = float(np.max(np.abs(actual - compact)))
    if error > 1e-5:
        raise ValueError(f"cached DeepSets representation does not reproduce checkpoint: {error}")
    return error


def decoder_smoke(initial_state: dict, cache: dict, graphs: dict, z: np.ndarray, train: np.ndarray, delta_count: int, device: str) -> dict:
    net = trajectory.new_decoder(delta_count)
    net.load_state_dict(copy.deepcopy(initial_state), strict=True)
    net.to(device).train()
    sample = train[:8]
    loss = trajectory_evaluate.losses(net, cache, graphs, sample, z=z[sample]).mean()
    if not torch.isfinite(loss):
        raise ValueError("nonfinite decoder smoke loss")
    loss.backward()
    gradients = [parameter.grad for parameter in net.parameters() if parameter.grad is not None]
    if not gradients or not all(torch.isfinite(gradient).all() for gradient in gradients):
        raise ValueError("nonfinite decoder smoke gradient")
    with torch.inference_mode():
        logp = trajectory.log_probabilities(
            net, z[sample], cache["potions"][sample], cache["capacity"][sample],
            cache["delta"][sample], cache["trueHp"][sample] / cache["trueMax"][sample], cache["boss"][sample]
        ).cpu().numpy()
    legal = np.asarray([
        trajectory.legal_actions(cache["potions"][index], int(cache["capacity"][index]), bool(cache["boss"][index]))
        for index in sample
    ])
    probability = np.exp(logp)
    if np.any(probability[~legal] != 0) or np.max(np.abs(probability.sum(-1) - 1)) > 1e-6:
        raise ValueError("decoder legality mask normalization failed")
    return {"finite": True, "finiteGradients": True, "legalMaskExact": True,
            "normalizationErrorMax": float(np.max(np.abs(probability.sum(-1) - 1))), "rows": int(len(sample))}


def reload_metrics(output: Path, initial_state: dict, delta_count: int, cache: dict, graphs: dict,
                   z_a: np.ndarray, z_b: np.ndarray, validation: np.ndarray, metrics_a: dict, metrics_b: dict, device: str) -> dict:
    values = {}
    for label, expected, z in (("A", metrics_a, z_a), ("B", metrics_b, z_b)):
        net = trajectory.new_decoder(delta_count)
        payload = torch.load(output / f"{label}.pt", map_location="cpu", weights_only=False)
        net.load_state_dict(payload["stateDict"], strict=True)
        net.to(device).eval().requires_grad_(False)
        actual = shared.teacher_metrics(net, cache, graphs, z, validation, label)
        # CUDA reductions can differ by a few ulps after a CPU checkpoint round trip.
        for key in ("trajectoryNll", "normalNoChangeBrier", "normalActionModeAccuracy", "normalCountAccuracy", "illegalProbabilityMax", "normalizationErrorMax"):
            if not np.isclose(actual[key], expected[key], rtol=1e-7, atol=1e-8):
                raise ValueError(f"reloaded {label} metric differs: {key}")
        for name in expected.get("slices", {}):
            if not np.isclose(actual["slices"][name]["trajectoryNll"], expected["slices"][name]["trajectoryNll"], rtol=1e-7, atol=1e-8):
                raise ValueError(f"reloaded {label} slice differs: {name}")
        values[label] = {"checkpointSha256": composed.base.sha256(output / f"{label}.pt"), "metricsReproduced": True}
    return values


def run(args):
    root = Path(__file__).resolve().parents[1]
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if current != args.experiment_sha:
        raise ValueError(f"experiment SHA mismatch: HEAD={current}, requested={args.experiment_sha}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("experiment requires a clean frozen worktree")
    if not torch.cuda.is_available():
        raise ValueError("CUDA is required by the fixed potion recipe")
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("refusing overwrite of external output directory")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])

    artifact_root = Path(args.artifact_root)
    cache, graphs, cache_meta = shared.near_full.trajectory.load(artifact_root / "potion-trajectory-v2")
    if cache_meta["cacheSha256"] != EXPECTED["cache"]:
        raise ValueError("current final-union potion cache hash differs")
    candidate_payload = verify_candidate(Path(args.candidate_checkpoint), Path(args.candidate_receipt))
    potion_receipt, potion_payload = shared.verify_potion_component(Path(args.dedicated_component), cache_meta)
    arrays, spec = composed.base._load_prepared(composed_evaluate.PREPARED)
    composed.base._prepare_target_indices(arrays, spec)
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    test = np.flatnonzero(cache["win"] & (cache["split"] == 2))
    counts = {
        "TRAIN": {"rows": int(len(train)), "sources": int(len(np.unique(cache["source"][train])))},
        "VALIDATION": {"rows": int(len(validation)), "sources": int(len(np.unique(cache["source"][validation])))},
    }
    expected_counts = _pins.value("combat_transition_deepset_potion.UNION_COUNTS", {"TRAIN": {"rows": 393677, "sources": 19986}, "VALIDATION": {"rows": 48590, "sources": 2496}})
    if counts != expected_counts:
        raise ValueError(f"final-union population differs: {counts}")
    target = np.concatenate((train, validation))
    sequence_hashes = {
        "rowSequenceSha256": shared.digest(cache["ids"][target]),
        "sourceSequenceSha256": shared.digest(cache["source"][target]),
        "splitSequenceSha256": shared.digest(cache["split"][target]),
    }
    if sequence_hashes != {
        "rowSequenceSha256": EXPECTED["rowSequence"],
        "sourceSequenceSha256": EXPECTED["sourceSequence"],
        "splitSequenceSha256": EXPECTED["splitSequence"],
    }:
        raise ValueError(f"potion population sequence hashes differ: {sequence_hashes}")
    z_b, representation = map_candidate_z(Path(args.representation_dir), cache, train, validation)
    candidate_encoder = load_deepset_encoder(candidate_payload, "cuda")
    cached_error = verify_cached_sample(candidate_encoder, arrays, cache, target, z_b, "cuda")
    dedicated_encoder = shared.load_encoder(potion_payload, False, "cuda")
    if any(parameter.requires_grad for parameter in dedicated_encoder.parameters()):
        raise ValueError("dedicated potion encoder is not frozen")
    z_a, time_a = shared.cache_encodings(cache, arrays, dedicated_encoder, target, "cuda", "dedicated")
    orders, batch_digest = shared.fixed_orders(train)
    torch.manual_seed(RECIPE["seed"])
    initial = trajectory.new_decoder(len(spec["maxHpDeltaValues"])).state_dict()
    initial_copy = copy.deepcopy(initial)
    initial_digest = shared.module_digest_from_state(initial)
    if initial_digest != shared.module_digest_from_state(initial_copy):
        raise ValueError("decoder initial states are not byte-identical")
    smoke = decoder_smoke(initial, cache, graphs, z_a, train, len(spec["maxHpDeltaValues"]), "cuda")
    net_a, fit_a = shared.fit_arm(initial, len(spec["maxHpDeltaValues"]), cache, graphs, z_a, train, validation,
                                  orders, "cuda", "A", output)
    net_b, fit_b = shared.fit_arm(initial_copy, len(spec["maxHpDeltaValues"]), cache, graphs, z_b, train, validation,
                                  orders, "cuda", "B", output)
    metrics_a = shared.teacher_metrics(net_a, cache, graphs, z_a, validation, "A")
    metrics_b = shared.teacher_metrics(net_b, cache, graphs, z_b, validation, "B")
    reload = reload_metrics(output, initial, len(spec["maxHpDeltaValues"]), cache, graphs, z_a, z_b, validation,
                            metrics_a, metrics_b, "cuda")
    stage_a, gates = shared.compare_teacher(metrics_a, metrics_b)
    ancestral_result = None
    final_decision = "DEEPSET_POTION_REJECTED"
    if stage_a == "TEACHER_FORCED_PASS":
        ancestral_result = shared.ancestral(
            net_a, net_b, cache, graphs, z_a, z_b, validation, candidate_payload,
            np.asarray(spec["maxHpDeltaValues"], np.int64),
            candidate_payload["stateDict"]["classes"].cpu().numpy().astype(np.int64), "cuda",
            candidate_representation="deepsets",
        )
        if any(v["structurallyInvalidTransitions"] or v["identityCreationOrSwapViolations"] or not v["finiteMixture"] or v["exposureGapNat"] > RECIPE["ancestralBoundaryNat"] for v in ancestral_result.values()):
            final_decision = "DEEPSET_POTION_REJECTED"
        elif ancestral_result["B"]["mixturePotionNll"] - ancestral_result["A"]["mixturePotionNll"] > 0.02 * ancestral_result["A"]["mixturePotionNll"]:
            final_decision = "DEEPSET_POTION_REJECTED"
        else:
            final_decision = "DEEPSET_POTION_GO"
    result = {
        "schema": RECIPE["schema"], "decision": final_decision, "stageADecision": stage_a,
        "recipe": RECIPE,
        "provenance": {
            "baselineSha": args.base_sha, "implementationSha": args.experiment_sha,
            "candidateCheckpointSha256": composed.base.sha256(Path(args.candidate_checkpoint)),
            "candidateReceiptSha256": composed.base.sha256(Path(args.candidate_receipt)),
            "candidateSelectedEpoch": int(candidate_payload["selectedEpoch"]),
            "candidateDecision": load_json(Path(args.candidate_receipt))["decision"],
            "dedicatedPotionComponentSha256": composed.base.sha256(Path(args.dedicated_component)),
            "dedicatedPotionSourceSha": potion_receipt["sourceSha"],
            "preparationCacheSha256": composed.base.sha256(artifact_root / "potion-trajectory-v2" / "preparation.json"),
            "cacheSha256": cache_meta["cacheSha256"], "sourceDataHashes": cache_meta["hashes"],
            "counts": counts, "testEncodedRows": 0, "testInferenceRows": 0,
            **sequence_hashes,
            "candidateRepresentation": representation, "cachedRepresentationSampleMaxAbsError": cached_error,
            "dedicatedEncodingSha256": shared.digest(z_a[target]), "candidateEncodingSha256": shared.digest(z_b[target]),
            "encodingWallSeconds": {"A": time_a}, "batchOrderSha256": batch_digest,
            "decoderInitialStateSha256": initial_digest, "decoderInitialStatesByteIdentical": True,
            "encodersFrozen": True, "maxHpHpHeadsFrozen": True, "validationInGradientUpdates": False,
        },
        "smoke": smoke,
        "fit": {"A": {key: value for key, value in fit_a.items() if key != "validationNllByRow"},
                "B": {key: value for key, value in fit_b.items() if key != "validationNllByRow"}},
        "teacherForced": {"A": metrics_a, "B": metrics_b, "gates": gates},
        "reloadVerification": reload, "ancestral": ancestral_result,
        "uncertainty": "offline TRAIN/VALIDATION screen; no TEST, runtime, export, promotion or gameplay",
        "knowledgeImpact": "experiment evidence and current research status only; runtime defaults unchanged",
    }
    (output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--representation-dir", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--dedicated-component", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--experiment-sha", required=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
