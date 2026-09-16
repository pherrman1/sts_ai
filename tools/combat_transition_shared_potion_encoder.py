#!/usr/bin/env python3
"""Frozen shared maxHP+HP encoder -> potion decoder screen.

This is an offline, TRAIN/VALIDATION-only representation substitution test.
It deliberately reuses the near-full 64-action potion trajectory machinery;
the only learned variable is the fresh potion decoder, and both encoders stay
frozen.  Large arrays/checkpoints are written to the external run directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import torch

try:
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_near_full_refit as near_full
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    from tools import combat_transition_surrogate as surrogate
    from tools import combat_transition_stochastic_hp as stochastic_hp
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_composed as composed
    from tools import combat_transition_composed_evaluate as composed_evaluate
    from tools import combat_transition_near_full_refit as near_full
    from tools import combat_transition_potion_trajectory as trajectory
    from tools import combat_transition_potion_trajectory_evaluate as trajectory_evaluate
    import combat_transition_surrogate as surrogate
    from tools import combat_transition_stochastic_hp as stochastic_hp


RECIPE = {
    "schema": "shared_potion_encoder_screen_v1",
    "seed": 20260912,
    "precision": "fp32",
    "epochs": 12,
    "batch": 512,
    "lr": 1e-3,
    "weightDecay": 1e-4,
    "gradientClip": 1.0,
    "selection": "earliest strict minimum identical VALIDATION exact trajectory NLL",
    "training": "decoder-only; frozen encoder representations cached once",
    "trajectory": "existing 64-action native USE/DISCARD DAG with exact observed generation-body prior",
    "population": "current final-union source-grouped TRAIN/VALIDATION winning rows",
    "testInferenceRows": 0,
    "ancestralDraws": 32,
    "ancestralSeed": 20260920,
    "ancestralBoundaryNat": 0.1,
}

EXPECTED = {
    "candidateCheckpoint": "daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267",
    "candidateDecision": "SHARED_TRANSITION_ENCODER_GO",
    "dedicatedPotionComponent": "ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db",
    "maxHPTeacher": "2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0",
    "HPTeacher": "0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b",
    "cacheSha256": "e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d",
    "sourceSha": "1c31b7eb0a7660d43bc27e0849a8955dd0c3daae",
}


def digest(value) -> str:
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def module_digest(module) -> str:
    h = hashlib.sha256()
    for name, value in module.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_checkpoint(path: Path, receipt: dict) -> dict:
    actual = composed.base.sha256(path)
    if actual != EXPECTED["candidateCheckpoint"]:
        raise ValueError(f"candidate checkpoint hash differs: {actual}")
    if receipt["bestCheckpointSha256"] != actual or receipt["selectedEpoch"] != 37:
        raise ValueError("candidate checkpoint receipt differs")
    if receipt["decision"] != EXPECTED["candidateDecision"]:
        raise ValueError("candidate was not qualified by PR #197's frozen decision")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("epoch") != 37 or payload.get("experimentSha") != "b58a03920fb84aee84f7fcde3ef300366221feb8":
        raise ValueError("candidate embedded provenance differs")
    return payload


def verify_potion_component(path: Path, cache_meta: dict) -> tuple[dict, dict]:
    receipt = load_json(path.parent / "fit.json")
    actual = composed.base.sha256(path)
    if receipt.get("component") != "potion" or receipt.get("artifactSha256") != actual:
        raise ValueError("dedicated potion component receipt differs")
    if actual != EXPECTED["dedicatedPotionComponent"]:
        raise ValueError(f"dedicated potion component hash differs: {actual}")
    if receipt.get("preparationCacheSha256") != cache_meta["cacheSha256"]:
        raise ValueError("dedicated potion/cache provenance differs")
    if receipt.get("hashes") != cache_meta["hashes"]:
        raise ValueError("dedicated potion/source-data provenance differs")
    if receipt.get("sourceSha") != EXPECTED["sourceSha"]:
        raise ValueError("dedicated potion source provenance differs")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if len(payload.get("headStateDicts", [])) != 1 or "encoderStateDict" not in payload:
        raise ValueError("dedicated potion component shape differs")
    return receipt, payload


def verify_teacher_component(path: Path, component: str) -> str:
    receipt = load_json(path.parent / "fit.json")
    actual = composed.base.sha256(path)
    if receipt.get("component") != component or receipt.get("artifactSha256") != actual:
        raise ValueError(f"{component} teacher receipt differs")
    expected = EXPECTED["maxHPTeacher"] if component == "maxHP" else EXPECTED["HPTeacher"]
    if actual != expected:
        raise ValueError(f"{component} teacher hash differs: {actual}")
    return actual


def load_encoder(payload: dict, candidate: bool, device: str):
    model = attention.AttentionPointControlNet(
        torch, np.zeros(10, np.float32), np.ones(10, np.float32)
    ).net
    if candidate:
        source = {k[len("encoder."):]: v for k, v in payload["stateDict"].items() if k.startswith("encoder.")}
    else:
        source = payload["encoderStateDict"]
    if set(source) != set(model.encoder.state_dict()):
        raise ValueError("encoder state-dict keys differ")
    model.encoder.load_state_dict(source, strict=True)
    model.to(device).eval().requires_grad_(False)
    return model.encoder


def cache_encodings(cache, arrays, encoder, ids, device, label):
    z = np.zeros((len(cache["ids"]), 64), np.float32)
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE["batch"]):
            local = ids[start:start + RECIPE["batch"]]
            inputs = composed.base._torch_inputs(
                arrays, cache["ids"][local], device, torch, trim_padding=True
            )
            with composed.attention_backend(torch, True):
                values = encoder(*inputs)
            values = values.float().cpu().numpy()
            if not np.isfinite(values).all():
                raise ValueError(f"nonfinite {label} representation")
            z[local] = values
    return z, time.monotonic() - started


def fixed_orders(train: np.ndarray) -> tuple[list[np.ndarray], str]:
    rng = np.random.default_rng(RECIPE["seed"])
    h = hashlib.sha256()
    orders = []
    for epoch in range(1, RECIPE["epochs"] + 1):
        order = rng.permutation(train)
        h.update(np.asarray([epoch], np.int64).tobytes())
        h.update(order.astype(np.int64).tobytes())
        orders.append(order)
    return orders, h.hexdigest()


def score(net, cache, graphs, z, ids) -> np.ndarray:
    values = []
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE["batch"]):
            local = ids[start:start + RECIPE["batch"]]
            values.append(trajectory_evaluate.losses(net, cache, graphs, local, z=z[local]))
    return torch.cat(values).cpu().numpy().astype(np.float64)


def fit_arm(initial_state, delta_count, cache, graphs, z, train, validation, orders, device, label, output):
    net = trajectory.new_decoder(delta_count)
    net.load_state_dict(copy.deepcopy(initial_state), strict=True)
    net.to(device).train()
    if module_digest(net) != module_digest_from_state(initial_state):
        raise ValueError(f"{label} decoder initialization changed")
    optimizer = torch.optim.AdamW(net.parameters(), lr=RECIPE["lr"], weight_decay=RECIPE["weightDecay"])
    history = []
    best = float("inf")
    selected = None
    selected_state = None
    started = time.monotonic()
    for epoch, order in enumerate(orders, 1):
        net.train()
        for start in range(0, len(order), RECIPE["batch"]):
            local = order[start:start + RECIPE["batch"]]
            optimizer.zero_grad(set_to_none=True)
            loss = trajectory_evaluate.losses(net, cache, graphs, local, z=z[local]).mean()
            if not torch.isfinite(loss):
                raise ValueError(f"{label} nonfinite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), RECIPE["gradientClip"])
            if not all(p.grad is None or torch.isfinite(p.grad).all() for p in net.parameters()):
                raise ValueError(f"{label} nonfinite decoder gradient")
            optimizer.step()
        validation_loss = score(net, cache, graphs, z, validation)
        value = float(validation_loss.mean())
        history.append({"epoch": epoch, "validationTrajectoryNll": value})
        print(json.dumps({"arm": label, **history[-1]}), flush=True)
        if value < best:
            best = value
            selected = epoch
            selected_state = copy.deepcopy(net.state_dict())
    if selected_state is None:
        raise ValueError(f"{label} did not select a checkpoint")
    net.load_state_dict(selected_state, strict=True)
    torch.save({"stateDict": selected_state, "selectedEpoch": selected, "recipe": RECIPE}, output / f"{label}.pt")
    return net.eval(), {
        "label": label,
        "selectedEpoch": selected,
        "history": history,
        "validationNllByRow": score(net, cache, graphs, z, validation),
        "trainingSeconds": time.monotonic() - started,
        "checkpointSha256": composed.base.sha256(output / f"{label}.pt"),
        "encoderFrozen": True,
        "decoderOnly": True,
    }


def module_digest_from_state(state) -> str:
    h = hashlib.sha256()
    for name, value in state.items():
        h.update(name.encode())
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def root_logp(net, cache, z, ids) -> np.ndarray:
    values = []
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE["batch"]):
            local = ids[start:start + RECIPE["batch"]]
            values.append(trajectory.log_probabilities(
                net, z[local], cache["potions"][local], cache["capacity"][local],
                cache["delta"][local], cache["trueHp"][local] / cache["trueMax"][local], cache["boss"][local]
            ).cpu().numpy())
    return np.concatenate(values).astype(np.float64)


def teacher_metrics(net, cache, graphs, z, ids, label) -> dict:
    nll = score(net, cache, graphs, z, ids)
    root = root_logp(net, cache, z, ids)
    normal = np.asarray([int(i) not in graphs for i in ids])
    if not normal.any():
        raise ValueError("no normal potion rows for action metrics")
    simple = ids[normal]
    root_simple = root[normal, :32]
    target = cache["mask"][simple]
    mode = root_simple.argmax(-1)
    counts = trajectory.decoder.BITS.sum(-1)
    count_probability = np.stack([np.exp(root_simple)[:, counts == n].sum(-1) for n in range(6)], -1)
    target_counts = counts[target]
    legal = np.asarray([
        trajectory.legal_actions(cache["potions"][i], int(cache["capacity"][i]), bool(cache["boss"][i]))
        for j, i in enumerate(ids)
    ])
    probabilities = np.exp(root)
    illegal_probability = probabilities[~legal]
    result = {
        "label": label,
        "rows": int(len(ids)),
        "trajectoryNll": float(nll.mean()),
        "normalRows": int(normal.sum()),
        "normalActionModeAccuracy": float(np.mean(mode == target)),
        "normalNoChangeBrier": float(np.mean((np.exp(root_simple[:, 0]) - (target == 0)) ** 2)),
        "normalCountAccuracy": float(np.mean(counts[mode] == target_counts)),
        "normalChangedRows": int(np.sum(target != 0)),
        "normalChangedActionModeAccuracy": float(np.mean(mode[target != 0] == target[target != 0])) if np.any(target != 0) else None,
        "normalUnchangedActionModeAccuracy": float(np.mean(mode[target == 0] == target[target == 0])) if np.any(target == 0) else None,
        "countCalibration": [
            {"count": n, "meanProbability": float(count_probability[:, n].mean()),
             "observedFrequency": float(np.mean(target_counts == n)),
             "brier": float(np.mean((count_probability[:, n] - (target_counts == n)) ** 2))}
            for n in range(6)
        ],
        "illegalProbabilityMax": float(illegal_probability.max()) if len(illegal_probability) else 0.0,
        "normalizationErrorMax": float(np.max(np.abs(np.exp(root).sum(-1) - 1))),
    }
    for name, selected in {
        "brew": np.any(cache["potions"][ids] == trajectory.BREW, -1),
        "smoke": np.any(cache["potions"][ids] == trajectory.SMOKE, -1),
        "recursiveBrew": np.asarray([i in graphs and graphs[i].rounds > 1 for i in ids]),
        "trajectorySpecial": ~normal.astype(bool),
    }.items():
        if np.any(selected):
            result.setdefault("slices", {})[name] = {"rows": int(selected.sum()), "trajectoryNll": float(nll[selected].mean())}
    if result["normalizationErrorMax"] > 1e-6 or not np.isfinite(nll).all():
        raise ValueError(f"{label} invalid potion distributions")
    # The masked log-softmax is the exact legality proof; no illegal category
    # is allowed to have positive probability, including trigger USE/DISCARD.
    if np.any(probabilities[~legal] != 0):
        raise ValueError(f"{label} illegal probability is not exactly zero")
    return result


def compare_teacher(a: dict, b: dict) -> tuple[str, dict]:
    gates = {
        "trajectoryNllRelative": (b["trajectoryNll"] - a["trajectoryNll"]) / a["trajectoryNll"],
        "noChangeBrierDelta": b["normalNoChangeBrier"] - a["normalNoChangeBrier"],
        "actionModeAccuracyDrop": a["normalActionModeAccuracy"] - b["normalActionModeAccuracy"],
        "countAccuracyDrop": a["normalCountAccuracy"] - b["normalCountAccuracy"],
        "illegalProbabilityMax": max(a["illegalProbabilityMax"], b["illegalProbabilityMax"]),
        "normalizationErrorMax": max(a["normalizationErrorMax"], b["normalizationErrorMax"]),
    }
    clear_slice = {}
    for name in sorted(set(a.get("slices", {})) | set(b.get("slices", {}))):
        if name not in a.get("slices", {}) or name not in b.get("slices", {}):
            continue
        av, bv = a["slices"][name]["trajectoryNll"], b["slices"][name]["trajectoryNll"]
        clear_slice[name] = {"relative": (bv - av) / av, "delta": bv - av}
    gates["slices"] = clear_slice
    # Slice output is retained for review.  A very large (>10%) NLL movement
    # is an obvious regression for this screen; smaller movements remain
    # visible but do not invent a second primary acceptance criterion.
    gates["obviousSliceRegression"] = any(v["relative"] > 0.10 for v in clear_slice.values())
    passed = (
        gates["trajectoryNllRelative"] <= 0.02
        and gates["noChangeBrierDelta"] <= 0.01
        and gates["actionModeAccuracyDrop"] <= 0.01
        and not gates["obviousSliceRegression"]
        and gates["illegalProbabilityMax"] == 0.0
        and gates["normalizationErrorMax"] <= 1e-6
    )
    return ("TEACHER_FORCED_PASS" if passed else "TEACHER_FORCED_REJECTED"), gates


def candidate_upstream(payload, classes, delta_values, device, representation="attention"):
    width = len(composed.base.CONTINUOUS_GLOBAL_FIELDS)
    student = stochastic_hp.new_model(torch, np.zeros(width, np.float32), np.ones(width, np.float32), len(delta_values), classes, RECIPE["seed"])
    if representation == "deepsets":
        student.encoder = surrogate.DeepSetsEncoder(
            torch.nn, torch, np.zeros(width, np.float32), np.ones(width, np.float32)
        ).net
    elif representation != "attention":
        raise ValueError(f"unknown candidate representation: {representation}")
    student.load_state_dict(payload["stateDict"], strict=True)
    student.to(device).eval().requires_grad_(False)
    head = torch.nn.Linear(64, len(delta_values), device=device)
    head.load_state_dict(payload["maxHpHeadStateDict"], strict=True)
    head.eval().requires_grad_(False)
    if any(parameter.requires_grad for parameter in student.parameters()) or any(parameter.requires_grad for parameter in head.parameters()):
        raise ValueError("candidate upstream is not frozen")
    return student, head


def sample_categories(prob, rng):
    cdf = np.cumsum(prob, -1)
    cdf /= cdf[:, -1:]
    return np.asarray([np.searchsorted(cdf[i], rng.random(), side="right") for i in range(len(prob))], np.int64)


def upstream_distributions(student, max_head, cache, z, ids, delta_values, classes, device):
    with torch.inference_mode():
        zt = torch.as_tensor(z[ids], device=device)
        max_prob = torch.softmax(max_head(zt).float(), -1).cpu().numpy().astype(np.float64)
        hp_prob = np.empty((len(ids), len(delta_values), len(classes)), np.float64)
        for delta in range(len(delta_values)):
            d = torch.full((len(ids),), delta, device=device, dtype=torch.long)
            raw = student.hp(torch.cat((zt, student.delta_embedding(d)), -1)).float()
            maximum = cache["preMax"][ids] + int(delta_values[delta])
            legal = stochastic_hp.legal_support(classes, cache["preHp"][ids], maximum)
            hp_prob[:, delta] = torch.softmax(raw.masked_fill(~torch.as_tensor(legal, device=device), -torch.inf), -1).cpu().numpy()
    if not np.isfinite(max_prob).all() or not np.isfinite(hp_prob).all():
        raise ValueError("candidate upstream distribution is nonfinite")
    if not np.allclose(max_prob.sum(-1), 1, atol=1e-6) or not np.allclose(hp_prob.sum(-1), 1, atol=1e-6):
        raise ValueError("candidate upstream distribution does not normalize")
    return max_prob, hp_prob


def ancestral(net_a, net_b, cache, graphs, z_a, z_b, ids, candidate_payload, delta_values, classes, device,
              candidate_representation="attention"):
    student, max_head = candidate_upstream(candidate_payload, classes, delta_values, device, candidate_representation)
    max_prob, hp_prob = upstream_distributions(student, max_head, cache, z_b, ids, delta_values, classes, device)
    rng = np.random.default_rng(RECIPE["ancestralSeed"])
    log_masses = [[], []]
    mode_changes = [[], []]
    invalid = [0, 0]
    identity = [0, 0]
    teacher_modes = [root_logp(net_a, cache, z_a, ids).argmax(-1), root_logp(net_b, cache, z_b, ids).argmax(-1)]
    for draw in range(RECIPE["ancestralDraws"]):
        delta = sample_categories(max_prob, rng)
        maximum = cache["preMax"][ids] + delta_values[delta]
        hp = np.empty(len(ids), np.int64)
        for row in range(len(ids)):
            hp[row] = sample_categories(hp_prob[row, delta[row]][None], rng)[0]
        fraction = (cache["preHp"][ids] + classes[hp]) / maximum
        for arm, (net, z) in enumerate(((net_a, z_a), (net_b, z_b))):
            logp = root_logp_conditioned(net, cache, z, ids, delta, fraction)
            log_masses[arm].append(-trajectory_evaluate.losses(net, cache, graphs, ids, z=z[ids], delta=delta, hp=fraction).cpu().numpy().astype(np.float64))
            mode_changes[arm].append(float(np.mean(logp.argmax(-1) != teacher_modes[arm])))
            actions = sample_categories(np.exp(logp), np.random.default_rng(RECIPE["ancestralSeed"] + draw * 17 + arm))
            masks = actions & 31
            action_legal = np.asarray([
                bool(trajectory.legal_actions(cache["potions"][i], int(cache["capacity"][i]), bool(cache["boss"][i])))[actions[j]]
                for j, i in enumerate(ids)
            ])
            invalid[arm] += int((~action_legal).sum())
            post = trajectory.decoder.decode_masks(cache["potions"][ids], cache["capacity"][ids], masks)
            try:
                encoded = trajectory.decoder.encode_masks(cache["potions"][ids], post, cache["capacity"][ids])
                identity[arm] += int((encoded != masks).sum())
            except ValueError:
                identity[arm] += len(ids)
        print(json.dumps({"stage": "ancestral", "draw": draw + 1}), flush=True)
    result = {}
    for arm, label in enumerate(("A", "B")):
        stacked = np.stack(log_masses[arm])
        max_log = stacked.max(0)
        mixture = max_log + np.log(np.exp(stacked - max_log).mean(0))
        teacher = -score(net_a if arm == 0 else net_b, cache, graphs, (z_a if arm == 0 else z_b), ids)
        gap = mixture - teacher
        result[label] = {
            "rows": int(len(ids)), "draws": RECIPE["ancestralDraws"],
            "mixturePotionNll": float(-mixture.mean()),
            "teacherForcedPotionNll": float(-teacher.mean()),
            "exposureGapNat": float(gap.mean()),
            "exposureGapMaxNat": float(np.max(gap)),
            "modeChangeFraction": float(np.mean(mode_changes[arm])),
            "structurallyInvalidTransitions": int(invalid[arm]),
            "identityCreationOrSwapViolations": int(identity[arm]),
            "finiteMixture": bool(np.isfinite(mixture).all()),
        }
    return result


def root_logp_conditioned(net, cache, z, ids, delta, fraction):
    with torch.inference_mode():
        return trajectory.log_probabilities(
            net, z[ids], cache["potions"][ids], cache["capacity"][ids], delta, fraction, cache["boss"][ids]
        ).cpu().numpy().astype(np.float64)


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
    cache, graphs, cache_meta = near_full.trajectory.load(artifact_root / "potion-trajectory-v2")
    if cache_meta["cacheSha256"] != EXPECTED["cacheSha256"]:
        raise ValueError("current final-union cache hash differs")
    candidate_path = Path(args.candidate_checkpoint)
    candidate_receipt = load_json(Path(args.candidate_receipt))
    candidate_payload = verify_checkpoint(candidate_path, candidate_receipt)
    potion_receipt, potion_payload = verify_potion_component(Path(args.dedicated_component), cache_meta)
    maxhp_teacher = verify_teacher_component(artifact_root / "full-union-maxHP-v1" / "component.pt", "maxHP")
    hp_teacher = verify_teacher_component(artifact_root / "full-union-HP-v1" / "component.pt", "HP")
    arrays, spec = composed.base._load_prepared(composed_evaluate.PREPARED)
    composed.base._prepare_target_indices(arrays, spec)
    ids = np.flatnonzero(cache["win"] & (cache["split"] < 2))
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    expected_counts = {"TRAIN": {"rows": 393677, "sources": 19986}, "VALIDATION": {"rows": 48590, "sources": 2496}}
    counts = {"TRAIN": {"rows": len(train), "sources": len(np.unique(cache["source"][train]))}, "VALIDATION": {"rows": len(validation), "sources": len(np.unique(cache["source"][validation]))}}
    if counts != expected_counts:
        raise ValueError(f"final-union population differs: {counts}")
    if np.any(cache["split"][ids] == 2):
        raise ValueError("TEST rows entered experiment")
    order_rows = np.concatenate((train, validation))
    provenance = {
        "baseSha": args.base_sha,
        "experimentSha": args.experiment_sha,
        "candidateCheckpointSha256": composed.base.sha256(candidate_path),
        "candidateReceiptSha256": composed.base.sha256(Path(args.candidate_receipt)),
        "candidateEpoch": int(candidate_payload["epoch"]),
        "candidateDecision": candidate_receipt["decision"],
        "dedicatedPotionComponentSha256": composed.base.sha256(Path(args.dedicated_component)),
        "dedicatedPotionSourceSha": potion_receipt["sourceSha"],
        "maxHPTeacherSha256": maxhp_teacher,
        "HPTeacherSha256": hp_teacher,
        "cacheMetaSha256": composed.base.sha256(artifact_root / "potion-trajectory-v2" / "preparation.json"),
        "cacheSha256": cache_meta["cacheSha256"],
        "sourceDataHashes": cache_meta["hashes"],
        "rowSequenceSha256": digest(cache["ids"][order_rows]),
        "sourceSequenceSha256": digest(cache["source"][order_rows]),
        "splitSequenceSha256": digest(cache["split"][order_rows]),
        "sourceGroupSequenceSha256": digest(cache["source"][ids]),
        "counts": counts,
        "testInferenceRows": 0,
    }
    device = "cuda"
    dedicated_encoder = load_encoder(potion_payload, False, device)
    candidate_encoder = load_encoder(candidate_payload, True, device)
    z_a, time_a = cache_encodings(cache, arrays, dedicated_encoder, ids, device, "dedicated")
    z_b, time_b = cache_encodings(cache, arrays, candidate_encoder, ids, device, "shared")
    z_digest_a, z_digest_b = digest(z_a[ids]), digest(z_b[ids])
    orders, batch_digest = fixed_orders(train)
    provenance.update({"dedicatedEncodingSha256": z_digest_a, "sharedEncodingSha256": z_digest_b,
                       "encodingWallSeconds": {"A": time_a, "B": time_b}, "batchOrderSha256": batch_digest,
                       "decoderInitialStateSha256": None, "encodersFrozen": True,
                       "decoderInitialStatesByteIdentical": True, "validationInGradientUpdates": False})
    torch.manual_seed(RECIPE["seed"])
    initial = trajectory.new_decoder(len(spec["maxHpDeltaValues"])).state_dict()
    provenance["decoderInitialStateSha256"] = module_digest_from_state(initial)
    initial_copy = copy.deepcopy(initial)
    if module_digest_from_state(initial) != module_digest_from_state(initial_copy):
        raise ValueError("decoder initial states are not byte-identical")
    started = time.monotonic()
    delta_count = len(spec["maxHpDeltaValues"])
    net_a, fit_a = fit_arm(initial, delta_count, cache, graphs, z_a, train, validation, orders, device, "A", output)
    net_b, fit_b = fit_arm(initial_copy, delta_count, cache, graphs, z_b, train, validation, orders, device, "B", output)
    fit_wall = time.monotonic() - started
    metrics_a = teacher_metrics(net_a, cache, graphs, z_a, validation, "A")
    metrics_b = teacher_metrics(net_b, cache, graphs, z_b, validation, "B")
    decision, gates = compare_teacher(metrics_a, metrics_b)
    ancestral_result = None
    if decision == "TEACHER_FORCED_PASS":
        ancestral_result = ancestral(net_a, net_b, cache, graphs, z_a, z_b, validation, candidate_payload,
                                     np.asarray(spec["maxHpDeltaValues"], np.int64),
                                     candidate_payload["stateDict"]["classes"].cpu().numpy().astype(np.int64), device)
        if any(v["structurallyInvalidTransitions"] or v["identityCreationOrSwapViolations"] or not v["finiteMixture"] or v["exposureGapNat"] > RECIPE["ancestralBoundaryNat"] for v in ancestral_result.values()):
            decision = "SHARED_ENCODER_POTION_REJECTED"
        elif ancestral_result["B"]["mixturePotionNll"] - ancestral_result["A"]["mixturePotionNll"] > 0.02 * ancestral_result["A"]["mixturePotionNll"]:
            decision = "SHARED_ENCODER_POTION_REJECTED"
        else:
            decision = "SHARED_ENCODER_POTION_GO"
    else:
        decision = "SHARED_ENCODER_POTION_REJECTED"
    result = {"schema": RECIPE["schema"], "decision": decision, "recipe": RECIPE,
              "provenance": provenance, "teacherForced": {"A": metrics_a, "B": metrics_b, "gates": gates},
              "fit": {"A": {k: v for k, v in fit_a.items() if k != "validationNllByRow"},
                      "B": {k: v for k, v in fit_b.items() if k != "validationNllByRow"}, "wallSeconds": fit_wall},
              "ancestral": ancestral_result,
              "uncertainty": "offline validation screen; no TEST, runtime, export, promotion or gameplay"}
    write_json(output / "results.json", result)
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--dedicated-component", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--experiment-sha", required=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
