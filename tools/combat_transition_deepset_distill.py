#!/usr/bin/env python3
"""Distill the frozen maxHP/HP teachers through the historical DeepSets encoder.

This is a one-candidate, offline experiment.  It reuses the exact teacher
probability cache from the 40-epoch shared-Attention control and never reads
TEST rows for inference or metrics.
"""
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

from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as composed_evaluate
from tools import combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_shared_encoder_distill as reference
from tools import combat_transition_stochastic_hp as stochastic_hp
from tools import combat_transition_surrogate as surrogate


RECIPE = dict(
    schema="shared_transition_deepset_distillation_v1", seed=20260912,
    encoder=("historical DeepSetsEncoder: card 48->64->64, relic 48->64->64, "
             "potion 40->64->64, global 42->64, sum pooling, 256->128->64 trunk"),
    encoderSource="tools/combat_transition_surrogate.py::DeepSetsEncoder",
    encoderNormalization=(
        "TRAIN-only mean/std for the 10 continuous globals, indexed by "
        "cache['ids'][train] original row IDs"
    ),
    hpBranch="existing maxHP-delta embedding and 72/64/304 ReLU head",
    maxHpBranch="fresh Linear(64,11)",
    loss="0.5 KL(maxHP teacher||student) + 0.5 KL(HP teacher||student)",
    temperature=1, epochs=40, batch=512, encoderLr=1e-4, headLr=1e-3,
    optimizer="AdamW", weightDecay=1e-4, clip=1.0,
    trainingPrecision="AMP-FP16 matched shared-Attention recipe",
    teacherPrecision="FP32", overflowHandling=(
        "nonfinite gradient norm -> scaler.step/update skip; "
        "nonfinite forward loss aborts"),
    selection="earliest strict minimum 0.5 VALIDATION maxHP KL + 0.5 VALIDATION HP KL",
    population="exact current final-union source-grouped TRAIN/VALIDATION victories",
)

try:
    from tools import ctm_pins as _pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins as _pins
EXPECTED_TEACHERS = _pins.value("combat_transition_deepset_distill.EXPECTED_TEACHERS", {
    "maxHP": "2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0",
    "HP": "0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b",
})
EXPECTED_TEACHER_OUTPUTS = _pins.value("combat_transition_deepset_distill.EXPECTED_TEACHER_OUTPUTS", {
    "maxHP": "10404b3e1de4f033667e4be62aefc24d9b4a3920cf1ddcd563408aeef17583d7",
    "HP": "6244ca5e8c196bbfe32094f5113416c7b31cdfb8a084d3ff46d160141d252759",
})
EXPECTED_COUNTS = _pins.value("combat_transition_deepset_distill.EXPECTED_COUNTS", {
    "TRAIN": {"rows": 393677, "sources": 19986},
    "VALIDATION": {"rows": 48590, "sources": 2496},
})
EXPECTED_HP_CLASS_COUNT = _pins.value("combat_transition_deepset_distill.EXPECTED_HP_CLASS_COUNT", 304)
EXPECTED_CONTROL = _pins.value("combat_transition_deepset_distill.EXPECTED_CONTROL", {
    "experimentSha": "b58a03920fb84aee84f7fcde3ef300366221feb8",
    "resultSha256": "4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7",
    "bestCheckpointSha256": "daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267",
    "selectedEpoch": 37,
})


def digest_array(value):
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def normalization_row_ids(cache, train):
    """Return and validate the original prepared-row IDs used for TRAIN stats."""
    cache_ids = np.asarray(cache["ids"])
    row_ids = np.asarray(cache_ids[np.asarray(train)], dtype=np.int64)
    if not np.array_equal(row_ids, cache_ids[np.asarray(train)]):
        raise ValueError("normalization row IDs differ from cache['ids'][train]")
    return row_ids


def normalization_stats(cache, arrays, train):
    """Compute TRAIN-only scalar statistics in original-row order."""
    row_ids = normalization_row_ids(cache, train)
    selected = arrays["globals_continuous"][row_ids]
    return selected.mean(0), selected.std(0), row_ids


def parameter_count(module):
    return int(sum(value.numel() for value in module.parameters()))


def _load_control(control_dir: Path):
    result_path = control_dir / "results.json"
    actual_result_sha = c.base.sha256(result_path)
    result = json.loads(result_path.read_text())
    if actual_result_sha != EXPECTED_CONTROL["resultSha256"]:
        raise ValueError("shared-Attention control receipt hash differs")
    for key in ("experimentSha", "selectedEpoch"):
        if result.get(key) != EXPECTED_CONTROL[key]:
            raise ValueError(f"shared-Attention control {key} differs")
    if result.get("bestCheckpointSha256") != EXPECTED_CONTROL["bestCheckpointSha256"]:
        raise ValueError("shared-Attention control checkpoint differs")
    if result.get("decision") != "SHARED_TRANSITION_ENCODER_GO":
        raise ValueError("shared-Attention control did not qualify")
    if result.get("counts") != EXPECTED_COUNTS:
        raise ValueError("shared-Attention control population differs")
    return result, actual_result_sha


def _load_teacher_cache(reference_dir: Path, cache: dict, meta: dict):
    receipt = json.loads((reference_dir / "results.json").read_text())
    if receipt.get("counts") != EXPECTED_COUNTS:
        raise ValueError("teacher cache receipt population differs")
    provenance = receipt.get("provenance", {})
    if provenance.get("preparationCacheSha256") != meta["cacheSha256"]:
        raise ValueError("teacher cache preparation hash differs")
    if provenance.get("sourceHashes") != meta["hashes"]:
        raise ValueError("teacher cache source hashes differ")
    ids = np.flatnonzero(cache["win"] & (cache["split"] < 2))
    if provenance.get("rowIdsSha256") != digest_array(cache["ids"][ids]):
        raise ValueError("teacher cache row identity differs")
    if provenance.get("sourceGroupsSha256") != digest_array(cache["source"][ids]):
        raise ValueError("teacher cache source identity differs")

    paths = {name: reference_dir / f"teacher-{name}.npy" for name in ("maxHP", "HP")}
    outputs = {}
    for name, path in paths.items():
        actual = c.base.sha256(path)
        if actual != EXPECTED_TEACHER_OUTPUTS[name] or provenance["teacherOutputs"].get(name) != actual:
            raise ValueError(f"{name} teacher-output hash differs")
        outputs[name] = np.load(path, mmap_mode="r")
    if outputs["maxHP"].shape != (len(cache["ids"]), 11):
        raise ValueError("maxHP teacher cache shape differs")
    if outputs["HP"].shape != (len(cache["ids"]), EXPECTED_HP_CLASS_COUNT):
        raise ValueError("HP teacher cache shape differs")
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    counts = {
        name: {"rows": int(len(selected)), "sources": int(np.unique(cache["source"][selected]).size)}
        for name, selected in (("TRAIN", train), ("VALIDATION", validation))
    }
    if counts != EXPECTED_COUNTS:
        raise ValueError("final-union population differs")
    valid_max = outputs["maxHP"][ids]
    valid_hp = outputs["HP"][ids]
    validity = dict(
        allFinite=bool(np.isfinite(valid_max).all() and np.isfinite(valid_hp).all()),
        maxHpNormalizationError=float(np.max(np.abs(valid_max.sum(1) - 1))),
        hpNormalizationError=float(np.max(np.abs(valid_hp.sum(1) - 1))),
    )
    if not validity["allFinite"] or max(validity["maxHpNormalizationError"], validity["hpNormalizationError"]) > 1e-6:
        raise ValueError("teacher probability validity failed")
    return outputs, train, validation, counts, validity, ids


def _student_model(torch_module, scalar_mean, scalar_std, delta_count, classes, seed):
    torch_module.manual_seed(seed)
    torch_module.cuda.manual_seed_all(seed)
    nn = torch_module.nn

    class DeepSetsStudent(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = surrogate.DeepSetsEncoder(
                nn, torch_module, scalar_mean, scalar_std
            ).net
            self.delta_embedding = nn.Embedding(delta_count, 8)
            self.hp = nn.Sequential(
                nn.Linear(72, 64), nn.ReLU(), nn.Linear(64, len(classes))
            )
            self.register_buffer("classes", torch_module.as_tensor(classes, dtype=torch_module.long))

        def forward(self, inputs, delta, pre, maximum):
            logits = self.hp(torch_module.cat((
                self.encoder(*inputs), self.delta_embedding(delta)
            ), -1)).float()
            post = pre[:, None] + self.classes[None, :]
            legal = (post >= 1) & (post <= maximum[:, None])
            if not bool(legal.any(1).all()):
                raise ValueError("empty legal support")
            return logits.masked_fill(~legal, float("-inf"))

    return DeepSetsStudent()


def _prepare(args):
    cache, _, meta = trajectory.load(Path(args.artifact_root) / "potion-trajectory-v2")
    max_fit, max_payload, max_hash = reference.verify_component(
        Path(args.artifact_root) / "full-union-maxHP-v1", "maxHP", meta
    )
    hp_fit, hp_payload, hp_hash = reference.verify_component(
        Path(args.artifact_root) / "full-union-HP-v1", "HP", meta
    )
    arrays, spec = c.base._load_prepared(composed_evaluate.PREPARED)
    c.base._prepare_target_indices(arrays, spec)
    outputs, train, validation, counts, validity, ids = _load_teacher_cache(
        Path(args.reference_dir), cache, meta
    )
    models = c.FrozenModels("cuda")
    models.max_net.encoder.load_state_dict(max_payload["encoderStateDict"])
    models.max_net.max_hp_delta.load_state_dict(max_payload["headStateDicts"][0])
    models.hp_net.encoder.load_state_dict(hp_payload["encoderStateDict"])
    models.hp_net.delta_embedding.load_state_dict(hp_payload["headStateDicts"][0])
    models.hp_net.hp.load_state_dict(hp_payload["headStateDicts"][1])
    models.max_net.eval().requires_grad_(False)
    models.hp_net.eval().requires_grad_(False)
    if max_hash != EXPECTED_TEACHERS["maxHP"] or hp_hash != EXPECTED_TEACHERS["HP"]:
        raise ValueError("teacher checkpoint hash differs")
    return cache, arrays, models, outputs, train, validation, counts, validity, ids, meta, (max_fit, hp_fit), max_hash, hp_hash, hp_payload


def initialize_specialist_hp_branch(student, teachers):
    """Copy the HP branch from the verified specialist used by Attention."""
    specialist_delta_hash = reference.state_hash(teachers.hp_net.delta_embedding)
    specialist_hp_hash = reference.state_hash(teachers.hp_net.hp)
    student.delta_embedding.load_state_dict(teachers.hp_net.delta_embedding.state_dict())
    student.hp.load_state_dict(teachers.hp_net.hp.state_dict())
    student_delta_hash = reference.state_hash(student.delta_embedding)
    student_hp_hash = reference.state_hash(student.hp)
    if (student_delta_hash != specialist_delta_hash or
            student_hp_hash != specialist_hp_hash):
        raise ValueError("DeepSets HP branch initialization differs from specialist")
    return dict(
        source="verified HP specialist used by the Attention control",
        deltaEmbeddingSha256=student_delta_hash,
        hpHeadSha256=student_hp_hash,
        matchesSpecialist=True,
    )


def _evaluate(prob_max, prob_hp, cache, models, ids):
    return reference.evaluate(prob_max, prob_hp, cache, models, ids)


def run(args, *, recipe=RECIPE, student_factory=_student_model,
        hp_initializer=initialize_specialist_hp_branch, latent_width=64):
    RECIPE = recipe
    root = Path(__file__).resolve().parents[1]
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    if current != args.experiment_sha or status:
        raise ValueError("fit requires clean frozen experiment SHA")
    if not torch.cuda.is_available():
        raise ValueError("CUDA required by fixed recipe")
    output = Path(args.output_dir)
    if output.exists():
        raise ValueError("refusing overwrite")
    output.mkdir(parents=True)
    torch.set_num_threads(4)
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])
    control, control_sha = _load_control(Path(args.control_dir))
    cache, arrays, teachers, teacher_outputs, train, validation, counts, teacher_validity, ids, meta, teacher_fits, max_hash, hp_hash, _ = _prepare(args)
    scalar_mean, scalar_std, normalization_ids = normalization_stats(cache, arrays, train)
    student = student_factory(torch, scalar_mean, scalar_std, len(teachers.delta_values), teachers.classes, RECIPE["seed"]).cuda()
    hp_initialization = hp_initializer(student, teachers)
    student.train().requires_grad_(True)
    initial_student_hash = reference.state_hash(student)
    max_head = torch.nn.Linear(latent_width, len(teachers.delta_values)).cuda()
    torch.manual_seed(RECIPE["seed"])
    torch.cuda.manual_seed_all(RECIPE["seed"])
    max_head.reset_parameters()
    initial_max_hash = reference.state_hash(max_head)
    encoder_parameters = parameter_count(student.encoder)
    student_parameters = parameter_count(student)
    groups = [
        dict(params=student.encoder.parameters(), lr=RECIPE["encoderLr"]),
        dict(params=list(student.delta_embedding.parameters()) + list(student.hp.parameters()) + list(max_head.parameters()), lr=RECIPE["headLr"]),
    ]
    optimizer = torch.optim.AdamW(groups, weight_decay=RECIPE["weightDecay"])
    scaler = torch.amp.GradScaler("cuda", init_scale=16384)
    rng = np.random.default_rng(RECIPE["seed"])
    batch_digest = hashlib.sha256()
    teacher_max = teacher_outputs["maxHP"]
    teacher_hp = teacher_outputs["HP"]
    pre = cache["preHp"].astype(np.int64)
    maximum = cache["trueMax"].astype(np.int64)

    def forward(local_ids, amp):
        inputs = c.base._torch_inputs(arrays, cache["ids"][local_ids], "cuda", torch, trim_padding=True)
        context = torch.autocast("cuda", dtype=torch.float16, enabled=amp)
        with c.attention_backend(torch, False), context:
            z = student.encoder(*inputs)
            max_logits = max_head(z).float()
            hp_logits = student.hp(torch.cat((z, student.delta_embedding(torch.as_tensor(cache["delta"][local_ids], device="cuda"))), -1)).float()
        legal = stochastic_hp.legal_support(teachers.classes, pre[local_ids], maximum[local_ids])
        return max_logits, hp_logits.masked_fill(~torch.as_tensor(legal, device="cuda"), -torch.inf)

    def score(score_ids):
        student.eval()
        max_out, hp_out = [], []
        total_max = total_hp = 0.0
        with torch.inference_mode():
            for start in range(0, len(score_ids), 1024):
                local = score_ids[start:start + 1024]
                logits_max, logits_hp = forward(local, False)
                tm = torch.as_tensor(np.array(teacher_max[local]), device="cuda")
                th = torch.as_tensor(np.array(teacher_hp[local]), device="cuda")
                total_max += float(reference.torch_kl(tm, logits_max)) * len(local)
                total_hp += float(reference.torch_kl(th, logits_hp)) * len(local)
                max_out.append(torch.softmax(logits_max, -1).cpu().numpy())
                hp_out.append(torch.softmax(logits_hp, -1).cpu().numpy())
        return np.concatenate(max_out), np.concatenate(hp_out), total_max / len(score_ids), total_hp / len(score_ids)

    history = []
    best = float("inf")
    skipped_updates = 0
    started = time.monotonic()
    overflow_log = (output / "overflow-events.jsonl").open("w")
    try:
        for epoch in range(1, RECIPE["epochs"] + 1):
            student.train(); max_head.train()
            order = rng.permutation(train)
            total_max = total_hp = 0.0
            epoch_skipped = 0
            for batch_index, start in enumerate(range(0, len(order), RECIPE["batch"]), 1):
                local = order[start:start + RECIPE["batch"]]
                batch_digest.update(local.tobytes())
                optimizer.zero_grad(set_to_none=True)
                logits_max, logits_hp = forward(local, True)
                tm = torch.as_tensor(np.array(teacher_max[local]), device="cuda")
                th = torch.as_tensor(np.array(teacher_hp[local]), device="cuda")
                lm = reference.torch_kl(tm, logits_max)
                lh = reference.torch_kl(th, logits_hp)
                loss = 0.5 * (lm + lh)
                if not torch.isfinite(loss):
                    c.base.json_dump(output / "failure.json", dict(kind="nonfinite_forward_loss", epoch=epoch, batch=batch_index, skippedUpdates=skipped_updates, lossScale=float(scaler.get_scale())))
                    raise ValueError("nonfinite distillation loss")
                total_max += float(lm.detach()) * len(local)
                total_hp += float(lh.detach()) * len(local)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                norm = torch.nn.utils.clip_grad_norm_(list(student.parameters()) + list(max_head.parameters()), RECIPE["clip"])
                before = float(scaler.get_scale())
                if not torch.isfinite(norm):
                    scaler.step(optimizer); scaler.update()
                    after = float(scaler.get_scale())
                    skipped_updates += 1; epoch_skipped += 1
                    event = dict(epoch=epoch, batch=batch_index, gradientNorm="nonfinite", lossScaleBefore=before, lossScaleAfter=after, skippedUpdates=skipped_updates)
                    overflow_log.write(json.dumps(event) + "\n"); overflow_log.flush()
                    print(json.dumps(dict(stage="overflow", **event)), flush=True)
                    continue
                scaler.step(optimizer); scaler.update()
            _, _, vm, vh = score(validation)
            entry = dict(epoch=epoch, trainMaxHpKl=total_max / len(train), trainHpKl=total_hp / len(train), validationMaxHpKl=vm, validationHpKl=vh, selectionLoss=0.5 * (vm + vh), skippedUpdatesEpoch=epoch_skipped, skippedUpdatesCumulative=skipped_updates, lossScale=float(scaler.get_scale()), seconds=time.monotonic() - started)
            history.append(entry); print(json.dumps(entry), flush=True)
            if entry["selectionLoss"] < best:
                best = entry["selectionLoss"]; selected = epoch
                student_state = copy.deepcopy(student.state_dict()); max_state = copy.deepcopy(max_head.state_dict())
                torch.save(dict(stateDict=student_state, maxHpHeadStateDict=max_state, optimizerStateDict=optimizer.state_dict(), scalerStateDict=scaler.state_dict(), epoch=epoch, validation=entry, skippedUpdates=skipped_updates, recipe=RECIPE, experimentSha=current), output / "best_epoch.pt")
            c.base.json_dump(output / "progress.json", dict(history=history, bestEpoch=selected if "selected" in locals() else None, bestSelectionLoss=best, skippedUpdates=skipped_updates, experimentSha=current))
    finally:
        overflow_log.close()

    student.load_state_dict(student_state); max_head.load_state_dict(max_state)
    student_max, student_hp, max_kl, hp_kl = score(validation)
    legal = stochastic_hp.legal_support(teachers.classes, pre[validation], maximum[validation])
    validity = dict(maxHpNormalizationError=float(np.max(np.abs(student_max.sum(1) - 1))), hpNormalizationError=float(np.max(np.abs(student_hp.sum(1) - 1))), hpUnsupportedProbability=float(np.max(np.where(legal, 0, student_hp))), allFinite=bool(np.isfinite(student_max).all() and np.isfinite(student_hp).all()))
    if not validity["allFinite"] or max(validity["maxHpNormalizationError"], validity["hpNormalizationError"]) > 1e-6 or validity["hpUnsupportedProbability"] != 0:
        raise ValueError("student probability validity failed")
    teacher_metrics = _evaluate(teacher_max[validation], teacher_hp[validation], cache, teachers, validation)
    student_metrics = _evaluate(student_max, student_hp, cache, teachers, validation)
    decision, gates = reference.classify(teacher_metrics, student_metrics)
    if selected == RECIPE["epochs"] and decision == "SHARED_TRANSITION_ENCODER_REJECTED" and reference.narrow_miss(gates):
        decision = "INCONCLUSIVE"
    checkpoint = output / "student.pt"
    torch.save(dict(stateDict=student_state, maxHpHeadStateDict=max_state, recipe=RECIPE, experimentSha=current, selectedEpoch=selected), checkpoint)
    result = dict(
        baselineSha=args.baseline_sha, experimentSha=current, recipe=RECIPE,
        control=dict(path=str(Path(args.control_dir).resolve()), resultSha256=control_sha, experimentSha=control["experimentSha"], bestCheckpointSha256=control["bestCheckpointSha256"], selectedEpoch=control["selectedEpoch"]),
        parameterCount=dict(encoder=encoder_parameters, studentWithoutMaxHpHead=student_parameters, maxHpHead=parameter_count(max_head), complete=student_parameters + parameter_count(max_head)),
        scalarNormalization=dict(mean=scalar_mean.tolist(), std=scalar_std.tolist(), rows=int(len(normalization_ids)), rowIdsSha256=digest_array(normalization_ids)),
        hpBranchInitialization=hp_initialization,
        teacherCheckpoints={"maxHP": max_hash, "HP": hp_hash},
        counts=counts, provenance=dict(sourceHashes=meta["hashes"], preparationCacheSha256=meta["cacheSha256"], rowIdsSha256=digest_array(cache["ids"][ids]), sourceGroupsSha256=digest_array(cache["source"][ids]), teacherOutputs=EXPECTED_TEACHER_OUTPUTS, teacherValidity=teacher_validity, teacherParametersFrozen=True, teacherCacheReused=True),
        testInferenceRows=0, testMetricsComputed=False, validationInGradientUpdates=False,
        initialStudentSha256=initial_student_hash, initialMaxHpHeadSha256=initial_max_hash,
        batchOrderSha256=batch_digest.hexdigest(), history=history, selectedEpoch=selected,
        studentToTeacherKl={"maxHP": max_kl, "HP": hp_kl}, specialistTeachers=teacher_metrics,
        deepSetsStudent=student_metrics, sharedAttentionControl=control["student"], gates=gates,
        validity=validity, skippedUpdates=skipped_updates, trainingSeconds=time.monotonic() - started,
        checkpointSha256=c.base.sha256(checkpoint), decision=decision,
    )
    c.base.json_dump(output / "results.json", result)
    np.savez_compressed(output / "validation_predictions.npz", rowIds=cache["ids"][validation], sourceGroups=cache["source"][validation], deltaValues=teachers.delta_values, classes=teachers.classes, studentMaxHP=student_max, studentHP=student_hp)
    c.base.json_dump(output / "artifact-hashes.json", {p.name: c.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name != "artifact-hashes.json"})
    print(json.dumps(dict(decision=decision, selectedEpoch=selected, gates=gates)), flush=True)
    return result


def finalize_existing(args):
    """Complete a fit whose selected checkpoint was written before receipt assembly."""
    if not torch.cuda.is_available():
        raise ValueError("CUDA required by fixed recipe")
    output = Path(args.output_dir)
    best_path = output / "best_epoch.pt"
    if not output.is_dir() or not best_path.is_file() or (output / "results.json").exists():
        raise ValueError("finalize requires an existing incomplete fit directory")
    control, control_sha = _load_control(Path(args.control_dir))
    cache, arrays, teachers, teacher_outputs, train, validation, counts, teacher_validity, ids, meta, teacher_fits, max_hash, hp_hash, _ = _prepare(args)
    scalar_mean, scalar_std, normalization_ids = normalization_stats(cache, arrays, train)
    student = _student_model(torch, scalar_mean, scalar_std, len(teachers.delta_values), teachers.classes, RECIPE["seed"]).cuda()
    hp_initialization = initialize_specialist_hp_branch(student, teachers)
    student.train().requires_grad_(True)
    initial_student_hash = reference.state_hash(student)
    max_head = torch.nn.Linear(64, len(teachers.delta_values)).cuda()
    torch.manual_seed(RECIPE["seed"]); torch.cuda.manual_seed_all(RECIPE["seed"]); max_head.reset_parameters()
    initial_max_hash = reference.state_hash(max_head)
    saved = torch.load(best_path, map_location="cuda", weights_only=False)
    student.load_state_dict(saved["stateDict"]); max_head.load_state_dict(saved["maxHpHeadStateDict"])
    selected = int(saved["epoch"])
    teacher_max = teacher_outputs["maxHP"]; teacher_hp = teacher_outputs["HP"]
    pre = cache["preHp"].astype(np.int64); maximum = cache["trueMax"].astype(np.int64)

    def score(score_ids):
        student.eval(); max_out, hp_out = [], []; total_max = total_hp = 0.0
        with torch.inference_mode():
            for start in range(0, len(score_ids), 1024):
                local = score_ids[start:start + 1024]
                inputs = c.base._torch_inputs(arrays, cache["ids"][local], "cuda", torch, trim_padding=True)
                with c.attention_backend(torch, False):
                    z = student.encoder(*inputs)
                    logits_max = max_head(z).float()
                    logits_hp = student.hp(torch.cat((z, student.delta_embedding(torch.as_tensor(cache["delta"][local], device="cuda"))), -1)).float()
                legal = stochastic_hp.legal_support(teachers.classes, pre[local], maximum[local])
                logits_hp = logits_hp.masked_fill(~torch.as_tensor(legal, device="cuda"), -torch.inf)
                tm = torch.as_tensor(np.array(teacher_max[local]), device="cuda")
                th = torch.as_tensor(np.array(teacher_hp[local]), device="cuda")
                total_max += float(reference.torch_kl(tm, logits_max)) * len(local)
                total_hp += float(reference.torch_kl(th, logits_hp)) * len(local)
                max_out.append(torch.softmax(logits_max, -1).cpu().numpy())
                hp_out.append(torch.softmax(logits_hp, -1).cpu().numpy())
        return np.concatenate(max_out), np.concatenate(hp_out), total_max / len(score_ids), total_hp / len(score_ids)

    student_max, student_hp, max_kl, hp_kl = score(validation)
    legal = stochastic_hp.legal_support(teachers.classes, pre[validation], maximum[validation])
    validity = dict(maxHpNormalizationError=float(np.max(np.abs(student_max.sum(1) - 1))), hpNormalizationError=float(np.max(np.abs(student_hp.sum(1) - 1))), hpUnsupportedProbability=float(np.max(np.where(legal, 0, student_hp))), allFinite=bool(np.isfinite(student_max).all() and np.isfinite(student_hp).all()))
    if not validity["allFinite"] or max(validity["maxHpNormalizationError"], validity["hpNormalizationError"]) > 1e-6 or validity["hpUnsupportedProbability"] != 0:
        raise ValueError("student probability validity failed")
    teacher_metrics = _evaluate(teacher_max[validation], teacher_hp[validation], cache, teachers, validation)
    student_metrics = _evaluate(student_max, student_hp, cache, teachers, validation)
    decision, gates = reference.classify(teacher_metrics, student_metrics)
    history = json.loads((output / "progress.json").read_text())["history"]
    checkpoint = output / "student.pt"
    torch.save(dict(stateDict=saved["stateDict"], maxHpHeadStateDict=saved["maxHpHeadStateDict"], recipe=RECIPE, experimentSha=args.experiment_sha, selectedEpoch=selected), checkpoint)
    result = dict(
        baselineSha=args.baseline_sha, experimentSha=args.experiment_sha, recipe=RECIPE,
        control=dict(path=str(Path(args.control_dir).resolve()), resultSha256=control_sha, experimentSha=control["experimentSha"], bestCheckpointSha256=control["bestCheckpointSha256"], selectedEpoch=control["selectedEpoch"]),
        parameterCount=dict(encoder=parameter_count(student.encoder), studentWithoutMaxHpHead=parameter_count(student), maxHpHead=parameter_count(max_head), complete=parameter_count(student) + parameter_count(max_head)),
        scalarNormalization=dict(mean=scalar_mean.tolist(), std=scalar_std.tolist(), rows=int(len(normalization_ids)), rowIdsSha256=digest_array(normalization_ids)),
        hpBranchInitialization=hp_initialization,
        teacherCheckpoints={"maxHP": max_hash, "HP": hp_hash}, counts=counts,
        provenance=dict(sourceHashes=meta["hashes"], preparationCacheSha256=meta["cacheSha256"], rowIdsSha256=digest_array(cache["ids"][ids]), sourceGroupsSha256=digest_array(cache["source"][ids]), teacherOutputs=EXPECTED_TEACHER_OUTPUTS, teacherValidity=teacher_validity, teacherParametersFrozen=True, teacherCacheReused=True),
        testInferenceRows=0, testMetricsComputed=False, validationInGradientUpdates=False,
        initialStudentSha256=initial_student_hash, initialMaxHpHeadSha256=initial_max_hash,
        history=history, selectedEpoch=selected, studentToTeacherKl={"maxHP": max_kl, "HP": hp_kl},
        specialistTeachers=teacher_metrics, deepSetsStudent=student_metrics, sharedAttentionControl=control["student"],
        gates=gates, validity=validity, skippedUpdates=int(json.loads((output / "progress.json").read_text())["skippedUpdates"]),
        overflowEventsSha256=c.base.sha256(output / "overflow-events.jsonl"), overflowHandling=RECIPE["overflowHandling"],
        trainingSeconds=float(history[-1]["seconds"]), checkpointSha256=c.base.sha256(checkpoint), decision=decision,
    )
    c.base.json_dump(output / "results.json", result)
    np.savez_compressed(output / "validation_predictions.npz", rowIds=cache["ids"][validation], sourceGroups=cache["source"][validation], deltaValues=teachers.delta_values, classes=teachers.classes, studentMaxHP=student_max, studentHP=student_hp)
    c.base.json_dump(output / "artifact-hashes.json", {p.name: c.base.sha256(p) for p in output.iterdir() if p.is_file() and p.name != "artifact-hashes.json"})
    print(json.dumps(dict(decision=decision, selectedEpoch=selected, gates=gates)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--reference-dir", required=True)
    parser.add_argument("--control-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--experiment-sha", required=True)
    parser.add_argument("--finalize-existing", action="store_true")
    parsed = parser.parse_args()
    if parsed.finalize_existing:
        finalize_existing(parsed)
    else:
        run(parsed)
