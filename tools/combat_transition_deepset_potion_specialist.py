#!/usr/bin/env python3
"""Paired warm-start fit of potion-aware and potion-blind DeepSets encoders.

This is a frozen TRAIN/VALIDATION-only experiment. It reuses the established
potion cache, exact trajectory loss, evaluator and teacher gate. TEST rows are
identified for the receipt but are never encoded or scored. For the reviewed
historical run, use reproduce_combat_transition_deepset_potion_specialist.py;
that wrapper validates the pinned source worktree and supplies fixed provenance
arguments. This low-level trainer CLI alone is not a provenance guard.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import time

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
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    from tools import combat_transition_shared_potion_encoder as shared
    from tools import combat_transition_surrogate as surrogate


RECIPE = {
    "schema": "deepset_potion_blind_v1", "seed": 20260912,
    "precision": "fp32", "batch": 512, "optimizer": "AdamW",
    "encoderLearningRate": 1e-4, "decoderLearningRate": 1e-3,
    "weightDecay": 1e-4, "gradientClip": 1.0,
    "minimumEpochs": 12, "maximumEpochs": 40, "patience": 6,
    "selection": "earliest strict minimum VALIDATION exact trajectory NLL",
    "loss": "existing exact potion trajectory NLL with hidden-trajectory marginalization",
    "population": "frozen final-union source-grouped TRAIN/VALIDATION winning rows",
    "testEncodedRows": 0, "testInferenceRows": 0,
}
try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
CONTROL_REPRODUCTION_REFERENCE_NLL = _pins.value("combat_transition_deepset_potion_specialist.CONTROL_REPRODUCTION_REFERENCE_NLL", 0.487162724)
CONTROL_REPRODUCTION_ABS_TOLERANCE = 0.005
EXPECTED = _pins.value("combat_transition_deepset_potion_specialist.EXPECTED", {
    "encoder": "bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663",
    "decoder": "06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1",
    "component": "ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db",
    "cache": "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d",
    "rowSequence": "2cb23f2eac81cd30f0200c49d42f090873b5452b265bb47410d67c46d6745809",
    "sourceSequence": "d843fcf1f106e8985aef32087c12745da9dfca6f050c64bcca44837578718b32",
    "splitSequence": "607782399125f7785c3a33f65934c9461b8b1e86f053637e8110f51a2294f3ca",
    "attentionReferenceReceipt": "1ba8b78524b8b6fc97c00a41eb33fc178cd6f36fa79a6b0af7dcad107ab45363",
    "attentionReferenceDecoder": "dad2df4a0d0d8a31c4707ee21bf92adf9b76c77deb520b49653b5eb789c3d48e",
})
ACCESS_COUNTERS = None


def record_access(cache: dict, ids: np.ndarray, operation: str) -> None:
    """Count rows passed to model encoding/scoring and fail on TEST access."""
    if ACCESS_COUNTERS is None or "split" not in cache:
        return
    split = np.asarray(cache["split"][np.asarray(ids, np.int64)])
    if np.any(split == 2):
        ACCESS_COUNTERS[operation]["TEST"] += int(np.sum(split == 2))
        raise ValueError(f"TEST rows reached {operation}")
    for split_id, name in ((0, "TRAIN"), (1, "VALIDATION")):
        ACCESS_COUNTERS[operation][name] += int(np.sum(split == split_id))
    if np.any(~np.isin(split, (0, 1))):
        raise ValueError(f"unknown split reached {operation}")


def sha(path: Path) -> str:
    return composed.base.sha256(path)


def module_sha(state: dict) -> str:
    h = hashlib.sha256()
    for key, value in state.items():
        h.update(key.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def verify_artifact(path: Path, expected: str, label: str) -> dict:
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"{label} SHA256 mismatch: {actual}")
    return torch.load(path, map_location="cpu", weights_only=False)


def new_encoder(arrays: dict, train_rows: np.ndarray, potion_blind: bool = False):
    width = len(composed.base.CONTINUOUS_GLOBAL_FIELDS)
    mean = arrays["globals_continuous"][train_rows].mean(0)
    std = arrays["globals_continuous"][train_rows].std(0)
    return surrogate.DeepSetsEncoder(torch.nn, torch, mean, std,
                                     potion_blind=potion_blind).net


def load_warm_encoder(encoder, payload: dict) -> None:
    state = payload.get("stateDict", {})
    source = {key[len("encoder."):]: value for key, value in state.items()
              if key.startswith("encoder.")}
    if set(source) != set(encoder.state_dict()):
        raise ValueError("warm-start DeepSets encoder keys differ")
    encoder.load_state_dict(source, strict=True)


def make_arm(label: str, arrays: dict, train_rows: np.ndarray, delta_count: int,
             warm_encoder: dict, warm_decoder: dict, device: str):
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])
    potion_blind = label == "P"
    encoder = new_encoder(arrays, train_rows, potion_blind=potion_blind)
    decoder = trajectory.new_decoder(delta_count)
    if label in ("W", "C", "P"):
        load_warm_encoder(encoder, warm_encoder)
        decoder.load_state_dict(warm_decoder["stateDict"], strict=True)
    elif label != "S":
        raise ValueError(f"unknown arm {label}")
    encoder.to(device).train().requires_grad_(True)
    if potion_blind:
        # Preserve strict warm-start keys while explicitly freezing the bypassed block.
        for name, parameter in encoder.named_parameters():
            if name.startswith(("potion_id.", "potion_slot.", "potion_mlp.")):
                parameter.requires_grad_(False)
    decoder.to(device).train().requires_grad_(True)
    return encoder, decoder


def trainable_parameters(encoder, decoder):
    return [parameter for module in (encoder, decoder)
            for parameter in module.parameters() if parameter.requires_grad]


def encode(encoder, arrays: dict, cache: dict, ids: np.ndarray, device: str) -> torch.Tensor:
    record_access(cache, ids, "encodedRows")
    inputs = composed.base._torch_inputs(arrays, cache["ids"][ids], device, torch,
                                         trim_padding=True)
    return encoder(*inputs)


def row_losses(encoder, decoder, arrays, cache, graphs, ids, device):
    z = encode(encoder, arrays, cache, ids, device)
    return trajectory_evaluate.losses(decoder, cache, graphs, ids, z=z)


def fixed_orders(train: np.ndarray):
    rng = np.random.default_rng(RECIPE["seed"])
    h = hashlib.sha256()
    orders = []
    for epoch in range(1, RECIPE["maximumEpochs"] + 1):
        order = rng.permutation(train).astype(np.int64)
        h.update(np.asarray([epoch], np.int64).tobytes())
        h.update(order.tobytes())
        orders.append(order)
    return orders, h.hexdigest()


def frozen_population(cache: dict):
    """Select exactly winning TRAIN/VALIDATION cache rows; never return TEST."""
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    return train, validation


def _score(encoder, decoder, arrays, cache, graphs, ids, device):
    record_access(cache, ids, "scoredRows")
    pieces = []
    encoder.eval(); decoder.eval()
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE["batch"]):
            batch = ids[start:start + RECIPE["batch"]]
            pieces.append(row_losses(encoder, decoder, arrays, cache, graphs, batch, device))
    return torch.cat(pieces).cpu().numpy().astype(np.float64)


def fit_arm(label, encoder, decoder, arrays, cache, graphs, train, validation,
            orders, device, output):
    trainable = trainable_parameters(encoder, decoder)
    optimizer = torch.optim.AdamW([
        {"params": [p for p in encoder.parameters() if p.requires_grad],
         "lr": RECIPE["encoderLearningRate"]},
        {"params": list(decoder.parameters()), "lr": RECIPE["decoderLearningRate"]},
    ], weight_decay=RECIPE["weightDecay"])
    optimizer_ids = {id(p) for group in optimizer.param_groups for p in group["params"]}
    expected_ids = {id(p) for p in trainable}
    if optimizer_ids != expected_ids:
        raise ValueError(f"{label} optimizer differs from the explicit trainable parameter set")
    if label == "P":
        bypassed = [p for name, p in encoder.named_parameters()
                    if name.startswith(("potion_id.", "potion_slot.", "potion_mlp."))]
        if not bypassed or any(p.requires_grad or id(p) in optimizer_ids for p in bypassed):
            raise ValueError("P potion parameters must remain checkpoint-compatible but excluded")
    history, best, selected, best_state, stale = [], float("inf"), None, None, 0
    started = time.monotonic()
    for epoch, order in enumerate(orders, 1):
        encoder.train(); decoder.train()
        for start in range(0, len(order), RECIPE["batch"]):
            batch = order[start:start + RECIPE["batch"]]
            optimizer.zero_grad(set_to_none=True)
            loss = row_losses(encoder, decoder, arrays, cache, graphs, batch, device).mean()
            if not torch.isfinite(loss):
                raise ValueError(f"{label} nonfinite training loss at epoch {epoch}")
            loss.backward()
            grads = [p.grad for p in trainable]
            if any(g is None or not torch.isfinite(g).all() for g in grads):
                raise ValueError(f"{label} missing or nonfinite trainable gradient")
            torch.nn.utils.clip_grad_norm_(trainable, RECIPE["gradientClip"])
            if any(not torch.isfinite(p.grad).all() for p in trainable):
                raise ValueError(f"{label} nonfinite clipped gradient")
            optimizer.step()
        nll = float(_score(encoder, decoder, arrays, cache, graphs, validation, device).mean())
        history.append({"epoch": epoch, "validationTrajectoryNll": nll})
        print(json.dumps({"arm": label, **history[-1]}), flush=True)
        if nll < best:
            best, selected, stale = nll, epoch, 0
            best_state = (copy.deepcopy(encoder.state_dict()), copy.deepcopy(decoder.state_dict()))
        else:
            stale += 1
        if epoch >= RECIPE["minimumEpochs"] and stale >= RECIPE["patience"]:
            break
    encoder.load_state_dict(best_state[0], strict=True)
    decoder.load_state_dict(best_state[1], strict=True)
    checkpoint = output / f"{label}.pt"
    torch.save({"encoderStateDict": best_state[0], "decoderStateDict": best_state[1],
                "selectedEpoch": selected, "recipe": RECIPE}, checkpoint)
    trainable_names = ([f"encoder.{name}" for name, p in encoder.named_parameters() if p.requires_grad]
                       + [f"decoder.{name}" for name, p in decoder.named_parameters() if p.requires_grad])
    return {"selectedEpoch": selected, "history": history,
            "trainingSeconds": time.monotonic() - started,
            "checkpointSha256": sha(checkpoint),
            "checkpointBytes": checkpoint.stat().st_size,
            "parameterCountTotal": sum(p.numel() for p in encoder.parameters()) +
                                   sum(p.numel() for p in decoder.parameters()),
            "trainableParameterCount": sum(p.numel() for p in trainable),
            "trainableParameterNames": trainable_names,
            "frozenEncoderParameterNames": [name for name, p in encoder.named_parameters()
                                             if not p.requires_grad]}


def slice_diagnostics(net, encoder, arrays, cache, graphs, ids, device):
    keys = ("potions", "capacity", "boss")
    missing = [key for key in keys if key not in cache]
    if missing:
        raise ValueError(f"potion cache misses required slice columns: {missing}")
    groups = {
        "noChange": np.asarray([int(i) not in graphs for i in ids]),
        "requiresAction": np.asarray([int(i) in graphs for i in ids]),
        "multipleTrajectories": np.asarray([int(i) in graphs and _trajectory_count(graphs[int(i)]) > 1 for i in ids]),
        "brewPresent": np.any(cache["potions"][ids] == trajectory.BREW, axis=1),
        "smokePresent": np.any(cache["potions"][ids] == trajectory.SMOKE, axis=1),
        "multipleOccupiedSlots": (cache["potions"][ids] > 1).sum(axis=1) > 1,
        "boss": cache["boss"][ids].astype(bool),
        "nonBoss": ~cache["boss"][ids].astype(bool),
    }
    # Act is a native contract input and is present in the categorical globals.
    act_column = composed.base.CONTINUOUS_GLOBAL_FIELDS.index("act")
    act_values = arrays["globals_continuous"][cache["ids"][ids], act_column]
    for value in sorted(np.unique(act_values)):
        groups[f"act_{int(value)}"] = act_values == value
    for value in sorted(np.unique(cache["capacity"][ids])):
        groups[f"capacity_{int(value)}"] = cache["capacity"][ids] == value
    for value in sorted(np.unique((cache["potions"][ids] > 1).sum(axis=1))):
        groups[f"potionCount_{int(value)}"] = (cache["potions"][ids] > 1).sum(axis=1) == value
    nll = _score(encoder, net, arrays, cache, graphs, ids, device)
    all_results = {}
    for name, selected in groups.items():
        if selected.any():
            all_results[name] = {"rows": int(selected.sum()),
                                 "trajectoryNll": float(nll[selected].mean())}
    return all_results


def recursive_validation_rows(encoder, decoder, arrays, cache, graphs, ids, device,
                              attention_nll=None):
    selected = np.asarray([int(i) for i in ids
                           if int(i) in graphs and graphs[int(i)].rounds > 1], np.int64)
    if not len(selected):
        return []
    nll = _score(encoder, decoder, arrays, cache, graphs, selected, device)
    rows = []
    for position, index in enumerate(selected):
        graph = graphs[int(index)]
        record = {"cacheIndex": int(index), "sourceSeed": int(cache["source"][index]),
                  "initialInventory": cache["potions"][index].tolist(),
                  "capacity": int(cache["capacity"][index]),
                  "boss": bool(cache["boss"][index]), "brewRounds": int(graph.rounds),
                  "graphNodes": int(len(graph.inventories)),
                  "graphEdges": int(len(graph.edges)),
                  "targetEdges": int(len(graph.target_edges)),
                  "compatibleTargetTrajectories": int(_trajectory_count(graph)),
                  "trajectoryNll": float(nll[position])}
        if attention_nll is not None:
            record["attentionReferenceNll"] = float(attention_nll[position])
            record["nllMinusAttention"] = float(nll[position] - attention_nll[position])
        rows.append(record)
    return rows


def _trajectory_count(graph) -> int:
    paths = [0] * len(graph.inventories)
    if not paths:
        return 0
    paths[0] = 1
    for owner, _action, child in sorted(graph.edges, key=lambda edge: edge[2]):
        paths[child] += paths[owner]
    return sum(paths[owner] for owner, _action in graph.target_edges)


def run(args):
    global ACCESS_COUNTERS
    ACCESS_COUNTERS = {key: {split: 0 for split in ("TRAIN", "VALIDATION", "TEST")}
                       for key in ("encodedRows", "scoredRows", "teacherMetricRows")}
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != args.experiment_sha:
        raise ValueError(f"experiment SHA assertion mismatch: {head}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("experiment requires clean frozen source")
    if not torch.cuda.is_available():
        raise ValueError("fixed experiment requires CUDA")
    output = args.output_dir
    if output.exists():
        raise ValueError("refusing to overwrite external experiment output")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"]); torch.cuda.manual_seed_all(RECIPE["seed"])
    cache, graphs, cache_meta = shared.near_full.trajectory.load(args.artifact_root / "potion-trajectory-v2")
    if cache_meta["cacheSha256"] != EXPECTED["cache"]:
        raise ValueError("frozen potion cache SHA differs")
    encoder_payload = verify_artifact(args.encoder_checkpoint, EXPECTED["encoder"], "warm encoder")
    decoder_payload = verify_artifact(args.decoder_checkpoint, EXPECTED["decoder"], "warm decoder")
    component_payload = verify_artifact(args.dedicated_component, EXPECTED["component"], "dedicated component")
    attention_decoder_payload = verify_artifact(
        args.reference_decoder, EXPECTED["attentionReferenceDecoder"], "Attention reference decoder"
    )
    arrays, spec = composed.base._load_prepared(composed_evaluate.PREPARED)
    composed.base._prepare_target_indices(arrays, spec)
    train, validation = frozen_population(cache)
    counts = {"TRAIN": {"rows": int(len(train)), "sources": int(len(np.unique(cache["source"][train])))},
              "VALIDATION": {"rows": int(len(validation)), "sources": int(len(np.unique(cache["source"][validation])))}}
    expected_counts = _pins.value("combat_transition_deepset_potion_specialist.UNION_COUNTS",
                                  {"TRAIN": {"rows": 393677, "sources": 19986},
                                   "VALIDATION": {"rows": 48590, "sources": 2496}})
    if counts != expected_counts:
        raise ValueError(f"frozen population counts differ: {counts}")
    target = np.concatenate((train, validation))
    sequences = {"rowSequenceSha256": shared.digest(cache["ids"][target]),
                 "sourceSequenceSha256": shared.digest(cache["source"][target]),
                 "splitSequenceSha256": shared.digest(cache["split"][target])}
    if sequences != {"rowSequenceSha256": EXPECTED["rowSequence"],
                     "sourceSequenceSha256": EXPECTED["sourceSequence"],
                     "splitSequenceSha256": EXPECTED["splitSequence"]}:
        raise ValueError(f"frozen row identities differ: {sequences}")
    recursive_validation = np.asarray(
        [int(i) for i in validation if int(i) in graphs and graphs[int(i)].rounds > 1],
        np.int64)
    attention_encoder = shared.load_encoder(component_payload, candidate=False, device="cuda")
    attention_decoder = trajectory.new_decoder(len(spec["maxHpDeltaValues"])).to("cuda").eval()
    attention_decoder.load_state_dict(attention_decoder_payload["stateDict"], strict=True)
    with torch.inference_mode():
        record_access(cache, recursive_validation, "encodedRows")
        attention_inputs = composed.base._torch_inputs(
            arrays, cache["ids"][recursive_validation], "cuda", torch, trim_padding=True)
        with composed.attention_backend(torch, True):
            attention_z = attention_encoder(*attention_inputs).float()
        record_access(cache, recursive_validation, "scoredRows")
        attention_recursive_nll = trajectory_evaluate.losses(
            attention_decoder, cache, graphs, recursive_validation, z=attention_z
        ).cpu().numpy().astype(np.float64)
    if len(attention_recursive_nll) != 12:
        raise ValueError("frozen recursive-Brew VALIDATION slice changed")
    orders, batch_hash = fixed_orders(train)
    results, nets, fit = {}, {}, {}
    starting_states = {}
    for label in ("C", "P"):
        encoder, decoder = make_arm(label, arrays, cache["ids"][train],
            len(spec["maxHpDeltaValues"]), encoder_payload, decoder_payload, "cuda")
        initial_hash = {"encoder": module_sha(encoder.state_dict()),
                        "decoder": module_sha(decoder.state_dict())}
        starting_states[label] = initial_hash
        if label == "P" and starting_states["C"] != initial_hash:
            raise ValueError("C/P warm-start states are not byte-identical")
        occupied = np.any(cache["potions"][train] > 1, axis=1)
        # This checks generic gradient flow; it does not promise Brew/Smoke DAG coverage.
        gradient_probe_ids = train[occupied][:8]
        if len(gradient_probe_ids) != 8:
            raise ValueError("frozen TRAIN population lacks eight occupied-potion gradient-smoke rows")
        gradient_probe_loss = row_losses(
            encoder, decoder, arrays, cache, graphs, gradient_probe_ids, "cuda"
        ).mean()
        gradient_probe_loss.backward()
        for name, module in (("encoder", encoder), ("decoder", decoder)):
            params = [p for p in module.parameters() if p.requires_grad]
            grads = [p.grad for p in params]
            if (not grads or any(g is None or not torch.isfinite(g).all() for g in grads)
                    or not any(torch.any(g != 0) for g in grads)):
                raise ValueError(f"{label} {name} smoke gradient is missing, zero or nonfinite")
        fit[label] = fit_arm(label, encoder, decoder, arrays, cache, graphs,
                             train, validation, orders, "cuda", output)
        if label == "C":
            reproduced = min(row["validationTrajectoryNll"] for row in fit[label]["history"])
            if abs(reproduced - CONTROL_REPRODUCTION_REFERENCE_NLL) > CONTROL_REPRODUCTION_ABS_TOLERANCE:
                raise ValueError(
                    "C control failed PR #298 warm-start reproduction precondition: "
                    f"NLL={reproduced:.9f}, expected={CONTROL_REPRODUCTION_REFERENCE_NLL:.9f} "
                    f"±{CONTROL_REPRODUCTION_ABS_TOLERANCE:.6f}; stopping before P"
                )
        nets[label] = (encoder, decoder)
        fit[label]["initialStateSha256"] = initial_hash
    for label, (encoder, decoder) in nets.items():
        z = np.zeros((len(cache["ids"]), 64), np.float32)
        with torch.inference_mode():
            for start in range(0, len(validation), RECIPE["batch"]):
                ids = validation[start:start + RECIPE["batch"]]
                z[ids] = encode(encoder, arrays, cache, ids, "cuda").float().cpu().numpy()
        record_access(cache, validation, "teacherMetricRows")
        metrics = shared.teacher_metrics(decoder, cache, graphs, z, validation, label)
        reloaded = torch.load(output / f"{label}.pt", map_location="cpu", weights_only=False)
        encoder2, decoder2 = make_arm(label, arrays, cache["ids"][train], len(spec["maxHpDeltaValues"]),
                                      encoder_payload, decoder_payload, "cpu")
        encoder2.load_state_dict(reloaded["encoderStateDict"], strict=True)
        decoder2.load_state_dict(reloaded["decoderStateDict"], strict=True)
        z2 = np.zeros_like(z)
        with torch.inference_mode():
            for start in range(0, len(validation), RECIPE["batch"]):
                ids = validation[start:start + RECIPE["batch"]]
                z2[ids] = encode(encoder2, arrays, cache, ids, "cpu").float().cpu().numpy()
        record_access(cache, validation, "teacherMetricRows")
        metrics2 = shared.teacher_metrics(decoder2, cache, graphs, z2, validation, label)
        for key in ("trajectoryNll", "normalNoChangeBrier", "normalActionModeAccuracy", "normalCountAccuracy"):
            if not np.isclose(metrics[key], metrics2[key], rtol=1e-6, atol=1e-7):
                raise ValueError(f"{label} reload changes {key}")
        results[label] = {"metrics": metrics, "reloadMetrics": metrics2,
                          "reloadReproduced": True,
                          "slices": slice_diagnostics(decoder, encoder, arrays, cache, graphs, validation, "cuda"),
                          "recursiveBrewValidationRows": recursive_validation_rows(
                              encoder, decoder, arrays, cache, graphs, recursive_validation,
                              "cuda", attention_recursive_nll)}
    # Compare each candidate to the qualified dedicated Attention reference recorded by the prior experiment.
    if sha(args.reference_receipt) != EXPECTED["attentionReferenceReceipt"]:
        raise ValueError("dedicated Attention reference receipt SHA differs")
    prior = json.loads(Path(args.reference_receipt).read_text())
    attention = prior.get("teacherForced", {}).get("A")
    if not attention:
        raise ValueError("reference receipt does not contain dedicated Attention metrics")
    if any(ACCESS_COUNTERS[operation]["TEST"] for operation in ACCESS_COUNTERS):
        raise ValueError(f"TEST access counter is nonzero: {ACCESS_COUNTERS}")
    classifications = {label: shared.compare_teacher(attention, value["metrics"])
                       for label, value in results.items()}
    decision = "POTION_DEEPSET_POTION_BLIND_REJECTED"
    if classifications["P"][0] == "TEACHER_FORCED_PASS":
        decision = "POTION_DEEPSET_SPECIALIST_GO"
    receipt = {"schema": RECIPE["schema"], "decision": decision,
        "decisionScope": "existing teacher-forced validation gate; a pass authorizes conditional export/parity/latency follow-up only",
        "recipe": RECIPE,
        "executionEnvironment": {"python": platform.python_version(),
            "torch": torch.__version__, "cudaRuntime": torch.version.cuda,
            "cudaDevice": torch.cuda.get_device_name(0),
            "cudaDeviceCount": torch.cuda.device_count(), "torchThreads": torch.get_num_threads()},
        "controlReproduction": {"referenceTrajectoryNll": CONTROL_REPRODUCTION_REFERENCE_NLL,
                                "absoluteTolerance": CONTROL_REPRODUCTION_ABS_TOLERANCE,
                                "stopsBeforeCandidateOnFailure": True},
        "provenance": {"baselineSha": args.base_sha, "implementationSha": args.experiment_sha,
            "cacheSha256": cache_meta["cacheSha256"], "cachePreparationSha256": sha(args.artifact_root / "potion-trajectory-v2" / "preparation.json"),
            "inputArtifactHashes": {"encoder": sha(args.encoder_checkpoint), "decoder": sha(args.decoder_checkpoint),
                                    "dedicatedComponent": sha(args.dedicated_component),
                                    "attentionReferenceReceipt": sha(args.reference_receipt),
                                    "attentionReferenceDecoder": sha(args.reference_decoder)},
            "counts": counts, "testRowsTouched": 0, **sequences, "batchOrderSha256": batch_hash,
            "testAccessCounters": ACCESS_COUNTERS,
            "sourceArtifactHashes": cache_meta["hashes"]},
        "fit": fit, "results": results,
        "classifications": {k: {"decision": v[0], "gates": v[1]} for k,v in classifications.items()},
        "attentionReference": attention,
        "knowledgeImpact": "experiment evidence and current research status only; runtime defaults unchanged"}
    (output / "results.json").write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps(receipt, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--encoder-checkpoint", type=Path, required=True)
    parser.add_argument("--decoder-checkpoint", type=Path, required=True)
    parser.add_argument("--dedicated-component", type=Path, required=True)
    parser.add_argument("--reference-receipt", type=Path, required=True)
    parser.add_argument("--reference-decoder", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--experiment-sha", required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
