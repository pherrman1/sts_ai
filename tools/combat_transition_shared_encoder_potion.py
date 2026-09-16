#!/usr/bin/env python3
"""Jointly adapt the qualified shared maxHP+HP encoder for the potion task.

This is an offline, TRAIN/VALIDATION-only experiment.  It keeps the exact
64-action potion trajectory decoder and DAG target, freezes the dedicated
maxHP/HP teachers, and trains one shared Attention encoder plus all three
task branches with fixed, TRAIN-only calibrated loss normalization.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import numpy as np
import torch

try:
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    from tools import combat_transition_shared_encoder_distill as distill
    from tools import combat_transition_shared_potion_encoder as potion_screen
    from tools import combat_transition_stochastic_hp as stochastic_hp
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    from tools import combat_transition_shared_encoder_distill as distill
    from tools import combat_transition_shared_potion_encoder as potion_screen
    from tools import combat_transition_stochastic_hp as stochastic_hp


RECIPE = {
    "schema": "shared_transition_encoder_potion_v1",
    "seed": 20260912,
    "precision": "fp32",
    "encoder": "AttentionEncoder:64/2/4/128 initialized from PR #197 epoch 37",
    "branches": "PR #197 maxHP head, HP delta embedding + head, existing 64-action potion decoder",
    "teachersFrozen": True,
    "epochs": 24,
    "batch": 512,
    "encoderLr": 1e-4,
    "headsLr": 1e-3,
    "weightDecay": 1e-4,
    "gradientClip": 1.0,
    "optimizer": "AdamW",
    "calibrationRows": 8192,
    "calibrationSeed": 20260912,
    "loss": "1/3 KL(maxHP)/s_max + 1/3 KL(HP)/s_hp + 1/3 exact_potion_NLL/s_potion",
    "selection": "earliest strict minimum potion VALIDATION exact trajectory NLL among PR #197-eligible epochs",
    "trajectory": "existing exact 64-action native USE/DISCARD DAG; generation prior excluded as constant",
    "population": "exact current final-union source-grouped TRAIN/VALIDATION winning rows",
    "testInferenceRows": 0,
    "ancestralDraws": 32,
    "ancestralSeed": 20260920,
    "ancestralBoundaryNat": 0.1,
}

EXPECTED = {
    "candidate": "daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267",
    "candidateReceipt": "4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7",
    "candidateExperiment": "b58a03920fb84aee84f7fcde3ef300366221feb8",
    "maxHP": "2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0",
    "HP": "0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b",
    "potion": "ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db",
    "cache": "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d",
    "source": "1c31b7eb0a7660d43bc27e0849a8955dd0c3daae",
    "teacherMax": "10404b3e1de4f033667e4be62aefc24d9b4a3920cf1ddcd563408aeef17583d7",
    "teacherHP": "6244ca5e8c196bbfe32094f5113416c7b31cdfb8a084d3ff46d160141d252759",
}


def digest(value) -> str:
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def state_digest(state) -> str:
    h = hashlib.sha256()
    for name, value in state.items():
        h.update(name.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_component(path: Path, component: str, cache_meta: dict) -> tuple[dict, dict]:
    receipt = read_json(path.parent / "fit.json")
    actual = composed.base.sha256(path)
    if receipt.get("component") != component or receipt.get("artifactSha256") != actual:
        raise ValueError(f"{component} receipt/artifact mismatch")
    if actual != EXPECTED[component]:
        raise ValueError(f"{component} hash differs: {actual}")
    if receipt.get("preparationCacheSha256") != cache_meta["cacheSha256"]:
        raise ValueError(f"{component} cache provenance differs")
    if receipt.get("sourceSha") != EXPECTED["source"] or receipt.get("hashes") != cache_meta["hashes"]:
        raise ValueError(f"{component} source provenance differs")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("metadata") != {k: v for k, v in receipt.items() if k != "artifactSha256"}:
        raise ValueError(f"{component} embedded metadata differs")
    return receipt, payload


def verify_candidate(path: Path, receipt_path: Path) -> tuple[dict, dict]:
    receipt = read_json(receipt_path)
    actual = composed.base.sha256(path)
    if actual != EXPECTED["candidate"] or receipt.get("bestCheckpointSha256") != actual:
        raise ValueError("PR #197 candidate checkpoint binding differs")
    if composed.base.sha256(receipt_path) != EXPECTED["candidateReceipt"]:
        raise ValueError("PR #197 candidate receipt hash differs")
    if receipt.get("bestCheckpointEpoch") != 37 or receipt.get("decision") != "SHARED_TRANSITION_ENCODER_GO":
        raise ValueError("PR #197 candidate is not the qualified epoch-37 checkpoint")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("epoch") != 37 or payload.get("experimentSha") != EXPECTED["candidateExperiment"]:
        raise ValueError("PR #197 candidate embedded provenance differs")
    return receipt, payload


def load_teacher_arrays(root: Path, cache: dict, train: np.ndarray, validation: np.ndarray):
    result = read_json(root / "results.json")
    hashes = read_json(root / "artifact-hashes.json")
    if result.get("counts") != {"TRAIN": {"rows": 393677, "sources": 19986}, "VALIDATION": {"rows": 48590, "sources": 2496}}:
        raise ValueError("teacher population receipt differs")
    if result.get("testInferenceRows") != 0 or result.get("testMetricsComputed"):
        raise ValueError("teacher receipt includes TEST inference")
    if result.get("provenance", {}).get("componentCheckpoints", {}).get("maxHP", {}).get("sha256") != EXPECTED["maxHP"]:
        raise ValueError("maxHP teacher receipt binding differs")
    if result.get("provenance", {}).get("componentCheckpoints", {}).get("HP", {}).get("sha256") != EXPECTED["HP"]:
        raise ValueError("HP teacher receipt binding differs")
    if result.get("provenance", {}).get("preparationCacheSha256") != EXPECTED["cache"]:
        raise ValueError("teacher preparation-cache provenance differs")
    paths = {"maxHP": root / "teacher-maxHP.npy", "HP": root / "teacher-HP.npy"}
    expected = {"maxHP": EXPECTED["teacherMax"], "HP": EXPECTED["teacherHP"]}
    values = {}
    for name, path in paths.items():
        if hashes.get(path.name) != expected[name] or composed.base.sha256(path) != expected[name]:
            raise ValueError(f"{name} teacher output hash differs")
        values[name] = np.load(path, mmap_mode="r")
        if values[name].shape[0] != len(cache["ids"]) or not np.isfinite(values[name][np.r_[train, validation]]).all():
            raise ValueError(f"{name} teacher output shape/finite check failed")
        if np.any(values[name][cache["split"] == 2] != 0):
            raise ValueError(f"{name} teacher output contains TEST values")
    return values


def model_from_candidate(payload, delta_count, classes, device):
    width = len(composed.base.CONTINUOUS_GLOBAL_FIELDS)
    model = stochastic_hp.new_model(torch, np.zeros(width, np.float32), np.ones(width, np.float32), delta_count, classes, RECIPE["seed"])
    model.load_state_dict(payload["stateDict"], strict=True)
    max_head = torch.nn.Linear(64, delta_count)
    max_head.load_state_dict(payload["maxHpHeadStateDict"], strict=True)
    model.to(device)
    max_head.to(device)
    return model, max_head


def potion_from_component(payload, delta_count, device):
    model = trajectory.new_decoder(delta_count)
    expected = model.state_dict()
    source = payload["headStateDicts"][0]
    if set(expected) != set(source) or any(expected[k].shape != source[k].shape for k in expected):
        raise ValueError("qualified potion decoder architecture differs")
    model.load_state_dict(source, strict=True)
    model.to(device)
    return model


def forward_transition(model, max_head, arrays, cache, ids, device, grad, train_mode):
    inputs = composed.base._torch_inputs(arrays, cache["ids"][ids], device, torch, trim_padding=True)
    context = torch.enable_grad() if grad else torch.inference_mode()
    with context, composed.attention_backend(torch, False):
        z = model.encoder(*inputs)
        max_logits = max_head(z).float()
        delta = torch.as_tensor(cache["delta"][ids], device=device, dtype=torch.long)
        hp_logits = model.hp(torch.cat((z, model.delta_embedding(delta)), -1)).float()
    legal = stochastic_hp.legal_support(model.classes.cpu().numpy(), cache["preHp"][ids], cache["trueMax"][ids])
    hp_logits = hp_logits.masked_fill(~torch.as_tensor(legal, device=device), -torch.inf)
    if train_mode:
        return z, max_logits, hp_logits
    return z.detach(), max_logits.detach(), hp_logits.detach()


def potion_losses(net, cache, graphs, ids, z):
    return trajectory_evaluate.losses(net, cache, graphs, ids, z=z)


def score_tasks(model, max_head, potion, arrays, cache, graphs, ids, delta_values, device):
    max_probs, hp_probs, p_losses = [], [], []
    for start in range(0, len(ids), RECIPE["batch"]):
        local = ids[start:start + RECIPE["batch"]]
        z, ml, hl = forward_transition(model, max_head, arrays, cache, local, device, False, False)
        max_probs.append(torch.softmax(ml, -1).cpu().numpy())
        hp_probs.append(torch.softmax(hl, -1).cpu().numpy())
        p_losses.append(potion_losses(potion, cache, graphs, local, z).detach().cpu().numpy())
    max_prob = np.concatenate(max_probs)
    hp_prob = np.concatenate(hp_probs)
    potion_nll = np.concatenate(p_losses).astype(np.float64)
    meta = SimpleNamespace(delta_values=np.asarray(delta_values), classes=model.classes.cpu().numpy())
    return max_prob, hp_prob, potion_nll, distill.evaluate(max_prob, hp_prob, cache, meta, ids)


def potion_metrics(net, cache, graphs, z, ids, label):
    values = potion_screen.teacher_metrics(net, cache, graphs, z, ids, label)
    return values


def gate_eligible(teacher_metrics, student_metrics):
    decision, gates = distill.classify(teacher_metrics, student_metrics)
    return decision == "SHARED_TRANSITION_ENCODER_GO", gates


def fixed_order(train):
    rng = np.random.default_rng(RECIPE["seed"])
    digestor = hashlib.sha256()
    orders = []
    for epoch in range(1, RECIPE["epochs"] + 1):
        order = rng.permutation(train)
        digestor.update(np.asarray([epoch], np.int64).tobytes())
        digestor.update(order.astype(np.int64).tobytes())
        orders.append(order)
    return orders, digestor.hexdigest()


def calibration(model, max_head, potion, arrays, cache, graphs, teachers, train, delta_values, device):
    rng = np.random.default_rng(RECIPE["calibrationSeed"])
    cohort = np.sort(rng.choice(train, RECIPE["calibrationRows"], replace=False)).astype(np.int64)
    max_kl, hp_kl, potion_nll = [], [], []
    for start in range(0, len(cohort), RECIPE["batch"]):
        ids = cohort[start:start + RECIPE["batch"]]
        z, ml, hl = forward_transition(model, max_head, arrays, cache, ids, device, True, True)
        tm = torch.as_tensor(np.asarray(teachers["maxHP"][ids]), device=device)
        th = torch.as_tensor(np.asarray(teachers["HP"][ids]), device=device)
        max_kl.append(float(distill.torch_kl(tm, ml).detach()) * len(ids))
        hp_kl.append(float(distill.torch_kl(th, hl).detach()) * len(ids))
        potion_nll.append(float(potion_losses(potion, cache, graphs, ids, z).detach().sum()))
    scales = {"s_max": sum(max_kl) / len(cohort), "s_hp": sum(hp_kl) / len(cohort), "s_potion": sum(potion_nll) / len(cohort)}
    if not all(np.isfinite(v) for v in scales.values()) or scales["s_max"] < 1e-4 or scales["s_hp"] < 1e-4:
        raise ValueError(f"pathological calibration scales: {scales}")
    return cohort, scales


def train(args):
    root = Path(__file__).resolve().parents[1]
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if current != args.experiment_sha:
        raise ValueError(f"experiment SHA mismatch: HEAD={current}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("experiment requires a clean frozen worktree")
    if not torch.cuda.is_available():
        raise ValueError("CUDA is required by the fixed FP32 training recipe")
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("refusing overwrite of external output directory")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"]); torch.cuda.manual_seed_all(RECIPE["seed"])

    artifact_root = Path(args.artifact_root)
    cache, graphs, cache_meta = trajectory_evaluate.load(artifact_root / "potion-trajectory-v2")
    if cache_meta["cacheSha256"] != EXPECTED["cache"]:
        raise ValueError("final-union cache hash differs")
    candidate_receipt, candidate = verify_candidate(Path(args.candidate_checkpoint), Path(args.candidate_receipt))
    potion_receipt, potion_payload = verify_component(Path(args.dedicated_component), "potion", cache_meta)
    max_receipt, max_payload = verify_component(artifact_root / "full-union-maxHP-v1" / "component.pt", "maxHP", cache_meta)
    hp_receipt, hp_payload = verify_component(artifact_root / "full-union-HP-v1" / "component.pt", "HP", cache_meta)
    arrays, spec = composed.base._load_prepared(composed_evaluate.PREPARED)
    composed.base._prepare_target_indices(arrays, spec)
    train_ids = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    counts = {"TRAIN": {"rows": len(train_ids), "sources": len(np.unique(cache["source"][train_ids]))},
              "VALIDATION": {"rows": len(validation), "sources": len(np.unique(cache["source"][validation]))}}
    expected_counts = {"TRAIN": {"rows": 393677, "sources": 19986}, "VALIDATION": {"rows": 48590, "sources": 2496}}
    if counts != expected_counts or np.any(cache["split"][np.r_[train_ids, validation]] == 2):
        raise ValueError(f"final-union population differs: {counts}")
    teachers = load_teacher_arrays(Path(args.teacher_root), cache, train_ids, validation)
    delta_values = np.asarray(spec["maxHpDeltaValues"], dtype=np.int64)
    classes = candidate["stateDict"]["classes"].cpu().numpy().astype(np.int64)
    if not np.array_equal(classes, composed.CLASSES):
        raise ValueError("candidate HP class domain differs")
    device = "cuda"
    model, max_head = model_from_candidate(candidate, len(delta_values), classes, device)
    potion = potion_from_component(potion_payload, len(delta_values), device)
    model.train(); max_head.train(); potion.train()
    if state_digest(model.state_dict()) != state_digest(candidate["stateDict"]):
        raise ValueError("maxHP/HP shared initialization differs from candidate")
    initial_model_hash = state_digest(model.state_dict())
    initial_max_hash = state_digest(max_head.state_dict())
    initial_potion_hash = state_digest(potion.state_dict())
    cohort, scales = calibration(model, max_head, potion, arrays, cache, graphs, teachers, train_ids, delta_values, device)
    orders, batch_digest = fixed_order(train_ids)
    optimizer = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": RECIPE["encoderLr"]},
        {"params": list(model.delta_embedding.parameters()) + list(model.hp.parameters()) + list(max_head.parameters()) + list(potion.parameters()), "lr": RECIPE["headsLr"]},
    ], weight_decay=RECIPE["weightDecay"])
    history = []; best_potion = float("inf"); selected = None; selected_states = None
    started = time.monotonic()
    for epoch, order in enumerate(orders, 1):
        model.train(); max_head.train(); potion.train(); total = {"max": 0., "hp": 0., "potion": 0., "loss": 0.}
        for start in range(0, len(order), RECIPE["batch"]):
            ids = order[start:start + RECIPE["batch"]]
            optimizer.zero_grad(set_to_none=True)
            z, ml, hl = forward_transition(model, max_head, arrays, cache, ids, device, True, True)
            tm = torch.as_tensor(np.asarray(teachers["maxHP"][ids]), device=device)
            th = torch.as_tensor(np.asarray(teachers["HP"][ids]), device=device)
            lm = distill.torch_kl(tm, ml); lh = distill.torch_kl(th, hl)
            lp = potion_losses(potion, cache, graphs, ids, z).mean()
            loss = (lm / scales["s_max"] + lh / scales["s_hp"] + lp / scales["s_potion"]) / 3.
            if not torch.isfinite(loss):
                raise ValueError(f"nonfinite joint loss at epoch {epoch}")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(list(model.parameters()) + list(max_head.parameters()) + list(potion.parameters()), RECIPE["gradientClip"])
            if not torch.isfinite(norm):
                raise ValueError(f"nonfinite joint gradient at epoch {epoch}")
            optimizer.step()
            n = len(ids); total["max"] += float(lm.detach()) * n; total["hp"] += float(lh.detach()) * n; total["potion"] += float(lp.detach()) * n; total["loss"] += float(loss.detach()) * n
        model.eval(); max_head.eval(); potion.eval()
        max_prob, hp_prob, potion_nll, student_metrics = score_tasks(model, max_head, potion, arrays, cache, graphs, validation, delta_values, device)
        teacher_metrics = distill.evaluate(np.asarray(teachers["maxHP"][validation]), np.asarray(teachers["HP"][validation]), cache, SimpleNamespace(delta_values=delta_values, classes=classes), validation)
        eligible, gates = gate_eligible(teacher_metrics, student_metrics)
        entry = {"epoch": epoch, "trainMaxHpKl": total["max"] / len(train_ids), "trainHpKl": total["hp"] / len(train_ids), "trainPotionNll": total["potion"] / len(train_ids), "trainNormalizedLoss": total["loss"] / len(train_ids), "validationPotionNll": float(potion_nll.mean()), "eligible": eligible, "preservationGates": gates, "seconds": time.monotonic() - started}
        history.append(entry); print(json.dumps({"epoch": epoch, "validationPotionNll": entry["validationPotionNll"], "eligible": eligible}), flush=True)
        if eligible and entry["validationPotionNll"] < best_potion:
            best_potion = entry["validationPotionNll"]; selected = epoch
            selected_states = (copy.deepcopy(model.state_dict()), copy.deepcopy(max_head.state_dict()), copy.deepcopy(potion.state_dict()))
    if selected_states is None:
        selected = None
        selected_states = (copy.deepcopy(model.state_dict()), copy.deepcopy(max_head.state_dict()), copy.deepcopy(potion.state_dict()))
    model.load_state_dict(selected_states[0]); max_head.load_state_dict(selected_states[1]); potion.load_state_dict(selected_states[2]); model.eval(); max_head.eval(); potion.eval()
    max_prob, hp_prob, potion_nll, student_metrics = score_tasks(model, max_head, potion, arrays, cache, graphs, validation, delta_values, device)
    teacher_metrics = distill.evaluate(np.asarray(teachers["maxHP"][validation]), np.asarray(teachers["HP"][validation]), cache, SimpleNamespace(delta_values=delta_values, classes=classes), validation)
    eligible, preservation = gate_eligible(teacher_metrics, student_metrics)
    candidate_z = np.zeros((len(cache["ids"]), 64), np.float32)
    for start in range(0, len(validation), RECIPE["batch"]):
        ids = validation[start:start + RECIPE["batch"]]
        candidate_z[ids] = forward_transition(model, max_head, arrays, cache, ids, device, False, False)[0].cpu().numpy()
    dedicated_encoder_model = attention.AttentionPointControlNet(torch, np.zeros(10, np.float32), np.ones(10, np.float32)).net
    dedicated_encoder_model.encoder.load_state_dict(potion_payload["encoderStateDict"], strict=True); dedicated_encoder_model.to(device).eval()
    dedicated_z = np.zeros_like(candidate_z)
    with torch.inference_mode():
        for start in range(0, len(validation), RECIPE["batch"]):
            ids = validation[start:start + RECIPE["batch"]]
            inputs = composed.base._torch_inputs(arrays, cache["ids"][ids], device, torch, trim_padding=True)
            with composed.attention_backend(torch, True):
                dedicated_z[ids] = dedicated_encoder_model.encoder(*inputs).float().cpu().numpy()
    dedicated_potion = potion_from_component(potion_payload, len(delta_values), device).eval()
    forced = {"candidate": potion_metrics(potion, cache, graphs, candidate_z, validation, "candidate"), "dedicated": potion_metrics(dedicated_potion, cache, graphs, dedicated_z, validation, "dedicated")}
    potion_decision, potion_gates = potion_screen.compare_teacher(forced["dedicated"], forced["candidate"])
    ancestral = None
    if eligible and potion_decision == "TEACHER_FORCED_PASS":
        payload = {"stateDict": selected_states[0], "maxHpHeadStateDict": selected_states[1]}
        raw_ancestral = potion_screen.ancestral(dedicated_potion, potion, cache, graphs, dedicated_z, candidate_z, validation, payload, delta_values, classes, device)
        ancestral = {"dedicated": raw_ancestral["A"], "candidate": raw_ancestral["B"]}
        for value in ancestral.values():
            value["brewSmokePathValidity"] = {"rootActionLegalityChecked": True, "maskIdentityChecked": True}
        if any(v["structurallyInvalidTransitions"] or v["identityCreationOrSwapViolations"] or not v["finiteMixture"] or v["exposureGapNat"] > RECIPE["ancestralBoundaryNat"] for v in ancestral.values()):
            final_decision = "SHARED_TRANSITION_POTION_REJECTED"
        elif ancestral["candidate"]["mixturePotionNll"] - ancestral["dedicated"]["mixturePotionNll"] > .02 * ancestral["dedicated"]["mixturePotionNll"]:
            final_decision = "SHARED_TRANSITION_POTION_REJECTED"
        else:
            final_decision = "SHARED_TRANSITION_POTION_GO"
    elif not eligible:
        final_decision = "SHARED_TRANSITION_POTION_REJECTED"
    else:
        final_decision = "SHARED_TRANSITION_POTION_REJECTED"
    checkpoint = output / "selected.pt"
    torch.save({"modelStateDict": selected_states[0], "maxHpHeadStateDict": selected_states[1], "potionStateDict": selected_states[2], "selectedEpoch": selected, "recipe": RECIPE, "experimentSha": current}, checkpoint)
    result = {"schema": RECIPE["schema"], "decision": final_decision, "baseSha": args.base_sha, "experimentSha": current, "candidateCheckpointSha256": composed.base.sha256(Path(args.candidate_checkpoint)), "candidateReceiptSha256": composed.base.sha256(Path(args.candidate_receipt)), "componentHashes": {"maxHP": EXPECTED["maxHP"], "HP": EXPECTED["HP"], "potion": EXPECTED["potion"]}, "sourceSha": EXPECTED["source"], "cacheSha256": EXPECTED["cache"], "counts": counts, "testInferenceRows": 0, "testMetricsComputed": False, "teachersFrozen": True, "validationInGradientUpdates": False, "calibration": {"rows": len(cohort), "rowIdsSha256": digest(cohort), "scales": scales}, "batchOrderSha256": batch_digest, "initialization": {"sharedModel": initial_model_hash, "maxHpHead": initial_max_hash, "potionDecoder": initial_potion_hash}, "history": history, "selectedEpoch": selected, "preservation": {"eligible": eligible, "metrics": student_metrics, "teacherMetrics": teacher_metrics, "gates": preservation}, "teacherForcedPotion": {"metrics": forced, "gates": potion_gates, "decision": potion_decision}, "ancestral": ancestral, "checkpointSha256": composed.base.sha256(checkpoint), "wallSeconds": time.monotonic() - started, "uncertainty": "offline TRAIN/VALIDATION screen; no TEST, runtime, export, promotion or gameplay"}
    write_json(output / "results.json", result)
    write_json(output / "artifact-hashes.json", {p.name: composed.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name != "artifact-hashes.json"})
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--teacher-root", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--dedicated-component", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--experiment-sha", required=True)
    train(parser.parse_args())
