#!/usr/bin/env python3
"""Resumable, source-sharded collector for the frozen Lizard Stage-C cohort.

Each worker runs one source in its own one-thread process.  A completed source
has its own JSONL, C++ manifest, provenance sidecar, and log.  Aggregation only
reads validated shards and publishes deterministic, source-ordered corpora.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone


STAGE_COHORT_SIZE = 320
WORKERS = 8
SIMULATIONS = 10000
ASCENSION = 0
PAIR_SCHEMA = "lizard_tail_targeted_paired_transition_pilot_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes, *, replace_existing: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == payload:
            return
        if not replace_existing:
            raise RuntimeError(f"refusing to overwrite different frozen output: {path}")
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}.{time.time_ns()}")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_json(path: Path, value: object, *, replace_existing: bool = False) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
                 replace_existing=replace_existing)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def validate_common(root: Path, plan_path: Path, plan: dict) -> tuple[list[int], dict, Path, Path, Path]:
    if plan.get("schema") not in (
            "active_lizard_mechanical_q_stage_c_sharded_plan_v1",
            "active_lizard_mechanical_q_stage_c_pair_plan_v1"):
        raise ValueError("unrecognized Stage-C collection plan")
    if plan.get("stage") != "C" or plan.get("status") != "FROZEN_PREOUTCOME":
        raise ValueError("Stage-C plan is not frozen pre-outcome")
    if plan.get("workerTopology") != {
            "maxConcurrentProcesses": WORKERS,
            "ompThreadsPerProcess": 1,
            "totalWorkerThreads": WORKERS,
            "resumeUnit": "one sourceSeed per independently manifested subprocess"}:
        raise ValueError("Stage-C worker topology differs from the frozen 8-worker plan")
    if plan.get("simulationBudget") != SIMULATIONS or plan.get("ascension") != ASCENSION:
        raise ValueError("Stage-C simulation or ascension configuration changed")

    assignment_path = resolve(root, plan["sourceAssignmentPath"])
    teacher_path = resolve(root, plan["nativeTeacherManifestPath"])
    candidate_path = resolve(root, plan["candidatePath"])
    binary_path = resolve(root, plan["executablePath"])
    for required in (assignment_path, teacher_path, candidate_path, binary_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    if sha256(assignment_path) != plan["sourceAssignmentSha256"]:
        raise ValueError("frozen source assignment SHA-256 mismatch")
    if sha256(candidate_path) != plan["candidateSha256"]:
        raise ValueError("frozen candidate SHA-256 mismatch")
    stage_b = plan.get("stageBTransferEvidence", {})
    stage_b_path = resolve(root, stage_b.get("analysisPath", ""))
    if (not stage_b_path.is_file()
            or sha256(stage_b_path) != stage_b.get("analysisSha256")):
        raise ValueError("Stage-B proceed-gate analysis is missing or changed")
    stage_b_analysis = load_json(stage_b_path)
    if (not stage_b.get("passedProceedGate")
            or stage_b_analysis.get("nativeTeacherTransferAssessment", {}).get("pass") is not True
            or stage_b_analysis.get("nativeTeacherTransferAssessment", {}).get("decision")
                != "PROCEED_TO_FRESH_NATIVE_QUALIFICATION"
            or stage_b_analysis.get("executionValidity", {}).get("expectedRows") != 119
            or stage_b_analysis.get("supportAudit", {}).get("exactSupportRows") != 119
            or stage_b_analysis.get("executionValidity", {}).get("mechanicalQParityEveryRow") is not True):
        raise ValueError("the exact current-main Stage-B 119-state proceed gate did not pass")
    if sha256(binary_path) != plan["executableSha256"]:
        raise ValueError("frozen executable SHA-256 mismatch")
    if sha256(teacher_path) != plan["nativeTeacherManifestSha256"]:
        raise ValueError("frozen native teacher manifest SHA-256 mismatch")
    script_path = Path(__file__).resolve()
    if sha256(script_path) != plan["collectorScriptSha256"]:
        raise ValueError("Stage-C shard collector source hash mismatch")
    amendment = plan.get("operationalAmendment")
    if amendment is not None:
        previous_plan_path = resolve(root, amendment["supersededPlanPath"])
        attempt_path = resolve(root, amendment["attemptRecordPath"])
        if (not previous_plan_path.is_file()
                or sha256(previous_plan_path) != amendment["supersededPlanSha256"]
                or not attempt_path.is_file()
                or sha256(attempt_path) != amendment["attemptRecordSha256"]):
            raise ValueError("Stage-C operational amendment provenance mismatch")
        attempt = load_json(attempt_path)
        if (attempt.get("schema") != "active_lizard_stage_c_attempt_record_v1"
                or attempt.get("status") != "ABORTED_INDEX_WRITE_FAILURE"
                or attempt.get("planSha256") != amendment["supersededPlanSha256"]
                or attempt.get("candidateScoringOrSelectionRun") is not False
                or attempt.get("candidateShardSeedsRevalidated")
                    != amendment.get("reusedCandidateShardSeeds")):
            raise ValueError("Stage-C operational amendment attempt record is inconsistent")
    for relative, expected_sha in plan.get("frozenRepositoryFiles", {}).items():
        frozen_path = resolve(root, relative)
        if not frozen_path.is_file() or sha256(frozen_path) != expected_sha:
            raise ValueError(f"frozen analysis/selection source changed: {relative}")

    candidate = load_json(candidate_path)
    if (candidate.get("candidateId") != "active-lizard-mechanical-q-learned-r-t2"
            or candidate.get("qDefinition") != "q = 1 - pOrdinaryWin; exactly the B1 mechanical consumption probability"
            or candidate.get("rMode") != "frozen_learned_r"
            or candidate.get("rArtifact", {}).get("sha256") != plan.get("rArtifactSha256")
            or candidate.get("t2Rule") != plan.get("t2Rule")):
        raise ValueError("candidate identity, frozen r artifact, or T2 rule differs from Stage-C plan")

    assignment = load_json(assignment_path)
    expected_seeds = list(range(4202000, 4202320))
    if (assignment.get("schema") != "active_lizard_mechanical_q_source_assignment_v1"
            or assignment.get("sourceSeedRange") != {
                "start": expected_seeds[0], "endInclusive": expected_seeds[-1],
                "count": STAGE_COHORT_SIZE}
            or assignment.get("cohorts", {}).get("HARD288") != expected_seeds[:288]
            or assignment.get("cohorts", {}).get("BROAD32") != expected_seeds[288:]
            or assignment.get("broad32Salt") != plan.get("broad32Salt")
            or assignment.get("mechanicalRiskRule") != plan.get("selectionRule")):
        raise ValueError("assignment differs from the exact frozen Stage-C source contract")

    teacher = load_json(teacher_path)
    if (teacher != plan.get("nativeTeacher")
            or teacher.get("combat_backend") != "native_silver"
            or teacher.get("rng_regime") != "project_fair"
            or teacher.get("search_configuration", {}).get("simulation_budgets") != [SIMULATIONS]
            or teacher.get("git_sha") != plan.get("collectorGitSha")
            or teacher.get("executable_sha256") != plan.get("executableSha256")
            or teacher.get("environment", {}).get("OMP_NUM_THREADS") != "1"
            or teacher.get("environment", {}).get("STS_EXECUTABLE_GIT_SHA") != teacher.get("git_sha")):
        raise ValueError("Stage-C native teacher provenance/configuration mismatch")
    for model in teacher["model_artifacts"]:
        model_path = resolve(root, model["path"])
        if not model_path.is_file() or sha256(model_path) != model["sha256"]:
            raise ValueError(f"native teacher model artifact mismatch: {model.get('role')}")

    seeds = expected_seeds
    return seeds, teacher, assignment_path, teacher_path, binary_path


def shard_paths(shard_root: Path, phase: str, seed: int) -> dict[str, Path]:
    stem = f"source_{seed}"
    base = shard_root / phase / stem
    return {
        "data": base.with_suffix(".jsonl"),
        "manifest": Path(str(base) + ".jsonl.manifest.json"),
        "provenance": Path(str(base) + ".jsonl.provenance.json"),
        "log": base.with_suffix(".log"),
    }


def quarantine_invalid(paths: dict[str, Path], shard_root: Path, phase: str, seed: int) -> None:
    present = [path for path in paths.values() if path.exists()]
    if not present:
        return
    destination = shard_root / "quarantine" / phase / f"source_{seed}_{time.time_ns()}"
    destination.mkdir(parents=True, exist_ok=False)
    for path in present:
        shutil.move(str(path), str(destination / path.name))


def candidate_shard_valid(paths: dict[str, Path], seed: int, plan: dict, teacher: dict) -> dict | None:
    try:
        manifest = load_json(paths["manifest"])
        if (manifest.get("schemaVersion") != "combat_transition_v1"
                or manifest.get("rowSchemaVersion") != "combat_transition_row_v2"
                or manifest.get("seedSpec") != {"start": seed, "count": 1}
                or manifest.get("producerGitSha") != plan["collectorGitSha"]
                or manifest.get("producerExecutableSha256") != plan["executableSha256"]
                or manifest.get("combatTeacher") != teacher
                or manifest.get("integrity") != {
                    "requestedSeeds": 1, "completedSeeds": 1,
                    "quarantinedSeeds": 0, "rows": manifest.get("integrity", {}).get("rows")}):
            return None
        spec = manifest.get("csv", {})
        if (spec.get("sha256") != sha256(paths["data"])
                or Path(spec.get("path", "")).resolve() != paths["data"].resolve()):
            return None
        rows = [json.loads(line) for line in paths["data"].read_text().splitlines() if line]
        if (len(rows) != int(manifest["integrity"].get("rows", -1)) or not rows
                or any(int(row.get("sourceSeed", -1)) != seed
                       or row.get("runValid") is not True
                       or row.get("schemaVersion") != "combat_transition_v1"
                       or row.get("rowSchemaVersion") != "combat_transition_row_v2"
                       for row in rows)
                or len({int(row["fightIdx"]) for row in rows}) != len(rows)):
            return None
        if not paths["provenance"].is_file() or not paths["log"].is_file():
            return None
        return {"seed": seed, "rows": len(rows),
                "dataSha256": sha256(paths["data"]),
                "manifestSha256": sha256(paths["manifest"]),
                "provenanceSha256": sha256(paths["provenance"]),
                "logSha256": sha256(paths["log"])}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def pair_shard_valid(paths: dict[str, Path], seed: int, target: dict,
                     subset_path: Path, plan: dict, teacher: dict) -> dict | None:
    try:
        manifest = load_json(paths["manifest"])
        spec = manifest.get("jsonl", {})
        if (manifest.get("schema") != PAIR_SCHEMA
                or manifest.get("seedSpec") != {"start": seed, "count": 1}
                or manifest.get("sourceSeeds") != [seed]
                or manifest.get("producerGitSha") != plan["collectorGitSha"]
                or manifest.get("producerExecutableSha256") != plan["executableSha256"]
                or manifest.get("baselineGitSha") != plan["baselineGitSha"]
                or manifest.get("combatTeacher") != teacher
                or manifest.get("combatTeacherManifestSha256") != plan["nativeTeacherManifestSha256"]
                or Path(manifest.get("targetSelection", {}).get("path", "")).resolve()
                    != subset_path.resolve()
                or manifest.get("targetSelection", {}).get("sha256") != sha256(subset_path)
                or manifest.get("integrity") != {
                    "requestedSeeds": 1, "completedSeeds": 1,
                    "quarantinedSeeds": 0, "pairs": 1}
                or spec.get("sha256") != sha256(paths["data"])
                or Path(spec.get("path", "")).resolve() != paths["data"].resolve()):
            return None
        rows = [json.loads(line) for line in paths["data"].read_text().splitlines() if line]
        if len(rows) != 1 or set(rows[0]) != {"pair", "noTail", "activeTail"}:
            return None
        pair = rows[0]
        meta = pair["pair"]
        if (int(meta.get("sourceSeed", -1)) != seed
                or int(meta.get("fightIdx", -1)) != int(target["fightIdx"])
                or meta.get("targetRiskBand") != target.get("riskBand")
                or abs(float(meta.get("targetPDeath", -1.0)) - float(target["pDeath"])) > 1e-12):
            return None
        for side in ("noTail", "activeTail"):
            row = pair[side]
            if (int(row.get("sourceSeed", -1)) != seed
                    or int(row.get("fightIdx", -1)) != int(target["fightIdx"])
                    or row.get("runValid") is not True
                    or row.get("captureCount") != 1
                    or row.get("captureStatus") != "exactly_one"
                    or row.get("teacherId") != teacher.get("teacher_id")):
                return None
        if not paths["provenance"].is_file() or not paths["log"].is_file():
            return None
        return {"seed": seed, "fightIdx": int(target["fightIdx"]),
                "dataSha256": sha256(paths["data"]),
                "manifestSha256": sha256(paths["manifest"]),
                "provenanceSha256": sha256(paths["provenance"]),
                "logSha256": sha256(paths["log"])}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def write_index(path: Path, phase: str, plan_path: Path, teacher_path: Path,
                entries: dict[int, dict]) -> None:
    atomic_json(path, {
        "schema": "active_lizard_stage_c_shard_index_v1",
        "phase": phase,
        "planSha256": sha256(plan_path),
        "nativeTeacherManifestSha256": sha256(teacher_path),
        "workerCount": WORKERS,
        "ompThreadsPerProcess": 1,
        "completedSources": len(entries),
        "entries": [entries[seed] for seed in sorted(entries)],
    }, replace_existing=True)


def run_task(root: Path, phase: str, seed: int, paths: dict[str, Path],
             plan: dict, teacher_path: Path, binary_path: Path,
             target: dict | None = None) -> dict:
    paths["data"].parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith("STS_") or name.startswith("OMP_"):
            environment.pop(name, None)
        environment.update(load_json(teacher_path)["environment"])
    environment["OMP_NUM_THREADS"] = "1"
    environment["STS_EXECUTABLE_GIT_SHA"] = plan["collectorGitSha"]
    if environment.get("OMP_NUM_THREADS") != "1":
        raise RuntimeError("each Stage-C subprocess must use exactly one OpenMP thread")

    if phase == "candidates":
        command = [str(binary_path), "combattransitionlizardtargetcandidategen",
                   "1", str(SIMULATIONS), str(ASCENSION), str(paths["data"]),
                   str(seed), str(teacher_path)]
    else:
        assert target is not None
        subset_path = paths["data"].with_suffix(".targets.json")
        subset = load_json(resolve(root, plan["targetSelectionPath"]))
        subset["targets"] = [target]
        atomic_json(subset_path, subset)
        command = [str(binary_path), "combattransitionlizardtargetpairgen",
                   "1", str(SIMULATIONS), str(ASCENSION), str(paths["data"]),
                   str(subset_path), str(teacher_path), plan["baselineGitSha"],
                   plan["collectorGitSha"]]

    guarded = ["bash", str(root / "tools/seed_guard.sh"), *command]
    started = datetime.now(timezone.utc).isoformat()
    with paths["log"].open("wb") as log:
        log.write(("started_utc=" + started + "\ncommand=" + " ".join(guarded) +
                   "\nOMP_NUM_THREADS=1\n").encode())
        log.flush()
        os.fsync(log.fileno())
        completed = subprocess.run(guarded, cwd=root, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
        log.write(("\nexit_code=" + str(completed.returncode) +
                   "\nfinished_utc=" + datetime.now(timezone.utc).isoformat() + "\n").encode())
        log.flush()
        os.fsync(log.fileno())
    if completed.returncode != 0:
        raise RuntimeError(f"seed {seed} exited {completed.returncode}; see {paths['log']}")
    if phase == "candidates":
        result = candidate_shard_valid(paths, seed, plan, load_json(teacher_path))
    else:
        assert target is not None
        subset_path = paths["data"].with_suffix(".targets.json")
        result = pair_shard_valid(paths, seed, target, subset_path,
                                  plan, load_json(teacher_path))
        if result is not None:
            result["targetSubsetSha256"] = sha256(subset_path)
    if result is None:
        raise RuntimeError(f"seed {seed} exited successfully but its shard failed provenance validation")
    return result


def schedule(root: Path, phase: str, todo: list[int], paths_by_seed: dict[int, dict[str, Path]],
             plan: dict, teacher_path: Path, binary_path: Path,
             entries: dict[int, dict], targets_by_seed: dict[int, dict] | None,
             index_path: Path, plan_path: Path) -> None:
    pending = iter(todo)
    errors: list[str] = []
    active = {}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="lizard-stage-c") as pool:
        def start_next() -> bool:
            try:
                seed = next(pending)
            except StopIteration:
                return False
            target = targets_by_seed.get(seed) if targets_by_seed else None
            future = pool.submit(run_task, root, phase, seed, paths_by_seed[seed],
                                 plan, teacher_path, binary_path, target)
            active[future] = seed
            return True

        for _ in range(min(WORKERS, len(todo))):
            start_next()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                seed = active.pop(future)
                try:
                    entry = future.result()
                    entries[seed] = entry
                    write_index(index_path, phase, plan_path, teacher_path, entries)
                    elapsed = int(time.monotonic() - started)
                    print(f"completed={len(entries)}/{STAGE_COHORT_SIZE} source={seed} "
                          f"elapsed_s={elapsed} workers={WORKERS} omp_per_worker=1",
                          flush=True)
                except Exception as error:  # all active jobs are drained and preserved
                    errors.append(f"source={seed}: {error}")
                    print(f"FAILED source={seed} error={error}", flush=True)
            if not errors:
                for _ in range(len(done)):
                    if not start_next():
                        break
    if errors:
        raise RuntimeError("Stage-C shard collection stopped after worker failure: "
                           + "; ".join(errors))


def aggregate_candidates(root: Path, seeds: list[int], paths_by_seed: dict[int, dict[str, Path]],
                         plan: dict, teacher: dict, out_data: Path, out_manifest: Path) -> None:
    first = load_json(paths_by_seed[seeds[0]]["manifest"])
    payload = b"".join(paths_by_seed[seed]["data"].read_bytes() for seed in seeds)
    rows = sum(int(load_json(paths_by_seed[seed]["manifest"])["integrity"]["rows"])
               for seed in seeds)
    manifest = copy.deepcopy(first)
    manifest["producerGitSha"] = plan["collectorGitSha"]
    manifest["producerExecutableSha256"] = plan["executableSha256"]
    manifest["combatTeacher"] = teacher
    manifest["seedSpec"] = {"start": seeds[0], "count": len(seeds)}
    manifest["csv"] = {"path": out_data.name,
                       "sha256": hashlib.sha256(payload).hexdigest()}
    manifest["integrity"] = {"requestedSeeds": len(seeds),
                             "completedSeeds": len(seeds),
                             "quarantinedSeeds": 0, "rows": rows}
    atomic_write(out_data, payload)
    atomic_json(out_manifest, manifest)


def aggregate_pairs(root: Path, seeds: list[int], paths_by_seed: dict[int, dict[str, Path]],
                    plan: dict, teacher: dict, selection_path: Path,
                    out_data: Path, out_manifest: Path) -> None:
    from tools.combat_transition_lizard_pair_pilot import validate_pair_corpus

    first = load_json(paths_by_seed[seeds[0]]["manifest"])
    payload = b"".join(paths_by_seed[seed]["data"].read_bytes() for seed in seeds)
    manifest = copy.deepcopy(first)
    manifest["schema"] = PAIR_SCHEMA
    manifest["producerGitSha"] = plan["collectorGitSha"]
    manifest["producerExecutableSha256"] = plan["executableSha256"]
    manifest["baselineGitSha"] = plan["baselineGitSha"]
    manifest["combatTeacher"] = teacher
    manifest["combatTeacherManifestSha256"] = plan["nativeTeacherManifestSha256"]
    manifest["seedSpec"] = {"start": seeds[0], "count": len(seeds)}
    manifest["sourceSeeds"] = seeds
    manifest["targetSelection"] = {
        "path": selection_path.name, "sha256": sha256(selection_path)}
    manifest["jsonl"] = {"path": out_data.name,
                         "sha256": hashlib.sha256(payload).hexdigest()}
    manifest["integrity"] = {"requestedSeeds": len(seeds),
                             "completedSeeds": len(seeds),
                             "quarantinedSeeds": 0, "pairs": len(seeds)}
    atomic_write(out_data, payload)
    atomic_json(out_manifest, manifest)
    validated, rows = validate_pair_corpus(out_manifest)
    if len(rows) != STAGE_COHORT_SIZE or validated["sourceSeeds"] != seeds:
        raise ValueError("aggregated Stage-C pair corpus did not validate as the exact 320-source cohort")


def run_phase(root: Path, phase: str, plan_path: Path) -> None:
    plan = load_json(plan_path)
    seeds, teacher, assignment_path, teacher_path, binary_path = validate_common(
        root, plan_path, plan)
    shard_root = resolve(root, plan["shardRoot"])
    lock_path = shard_root / ".stage_c_collection.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"another Stage-C collector holds {lock_path}") from error

        targets_by_seed = None
        selection_path = None
        if phase == "pairs":
            if plan.get("schema") != "active_lizard_mechanical_q_stage_c_pair_plan_v1":
                raise ValueError("pair collection requires a separate frozen pre-outcome pair plan")
            selection_path = resolve(root, plan["targetSelectionPath"])
            if sha256(selection_path) != plan["targetSelectionSha256"]:
                raise ValueError("frozen Stage-C target selection hash mismatch")
            selection = load_json(selection_path)
            if (selection.get("schema") != "lizard_tail_risk_target_selection_v1"
                    or selection.get("candidateManifestSha256") != plan["candidateManifestSha256"]
                    or selection.get("candidateJsonlSha256") != plan["candidateJsonlSha256"]
                    or selection.get("sourceAssignmentSha256") != plan["sourceAssignmentSha256"]
                    or selection.get("nativeTeacherManifestSha256") != plan["nativeTeacherManifestSha256"]
                    or len(selection.get("targets", [])) != STAGE_COHORT_SIZE):
                raise ValueError("selection artifact does not bind the frozen Stage-C candidate and teacher")
            targets_by_seed = {int(target["sourceSeed"]): target
                               for target in selection["targets"]}
            if sorted(targets_by_seed) != seeds or len(targets_by_seed) != STAGE_COHORT_SIZE:
                raise ValueError("Stage-C selected targets do not cover the exact 320 sources")
        elif phase != "candidates" or plan.get("schema") != "active_lizard_mechanical_q_stage_c_sharded_plan_v1":
            raise ValueError("unknown Stage-C shard phase")

        paths_by_seed = {seed: shard_paths(shard_root, phase, seed) for seed in seeds}
        index_path = shard_root / f"{phase}_shard_index.json"
        entries: dict[int, dict] = {}
        if index_path.is_file():
            old_index = load_json(index_path)
            if (old_index.get("schema") != "active_lizard_stage_c_shard_index_v1"
                    or old_index.get("phase") != phase
                    or old_index.get("planSha256") != sha256(plan_path)
                    or old_index.get("nativeTeacherManifestSha256") != sha256(teacher_path)):
                raise ValueError("existing shard index belongs to a different frozen plan")

        todo = []
        for seed in seeds:
            paths = paths_by_seed[seed]
            target = targets_by_seed[seed] if targets_by_seed else None
            subset_path = paths["data"].with_suffix(".targets.json") if phase == "pairs" else None
            if phase == "pairs":
                subset = copy.deepcopy(load_json(selection_path))
                subset["targets"] = [target]
                atomic_json(subset_path, subset)
                entry = pair_shard_valid(paths, seed, target, subset_path, plan, teacher)
            else:
                entry = candidate_shard_valid(paths, seed, plan, teacher)
            if entry is None:
                quarantine_invalid(paths, shard_root, phase, seed)
                if subset_path and subset_path.exists():
                    quarantine_invalid({"targets": subset_path}, shard_root, phase, seed)
                todo.append(seed)
            else:
                if phase == "pairs":
                    entry["targetSubsetSha256"] = sha256(subset_path)
                entries[seed] = entry
        write_index(index_path, phase, plan_path, teacher_path, entries)
        print(f"phase={phase} complete_shards={len(entries)}/{STAGE_COHORT_SIZE} "
              f"remaining={len(todo)} worker_limit={WORKERS} omp_per_worker=1 "
              f"plan_sha256={sha256(plan_path)}", flush=True)
        schedule(root, phase, todo, paths_by_seed, plan, teacher_path, binary_path,
                 entries, targets_by_seed, index_path, plan_path)
        if len(entries) != STAGE_COHORT_SIZE:
            raise RuntimeError("Stage-C source shard set is incomplete")

        if phase == "candidates":
            out_data = resolve(root, plan["candidateJsonlPath"])
            out_manifest = resolve(root, plan["candidateManifestPath"])
            aggregate_candidates(root, seeds, paths_by_seed, plan, teacher,
                                 out_data, out_manifest)
        else:
            assert selection_path is not None
            out_data = resolve(root, plan["pairJsonlPath"])
            out_manifest = resolve(root, plan["pairManifestPath"])
            aggregate_pairs(root, seeds, paths_by_seed, plan, teacher,
                            selection_path, out_data, out_manifest)
        print(f"phase={phase} aggregate_rows={STAGE_COHORT_SIZE} "
              f"jsonl={out_data} sha256={sha256(out_data)} "
              f"manifest={out_manifest} sha256={sha256(out_manifest)}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("candidates", "pairs"))
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--preflight-only", action="store_true",
                        help="validate frozen files, teacher, binary, and seed-guard argv without launching a seed")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    try:
        plan_path = plan_path.resolve()
        if args.preflight_only:
            plan = load_json(plan_path)
            seeds, teacher, _, teacher_path, binary_path = validate_common(root, plan_path, plan)
            mode = ("combattransitionlizardtargetcandidategen" if args.phase == "candidates"
                    else "combattransitionlizardtargetpairgen")
            guard = subprocess.run(
                ["bash", str(root / "tools/seed_guard.sh"), "guard-only",
                 str(binary_path), mode, "1", str(SIMULATIONS), str(ASCENSION),
                 "/tmp/lizard_stage_c_guard_only.jsonl", str(seeds[0]), str(teacher_path)],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False)
            if guard.returncode:
                raise RuntimeError("repository seed guard rejected the planned per-source command: "
                                   + guard.stdout.strip())
            print(f"PREFLIGHT_PASS phase={args.phase} sources={len(seeds)} "
                  f"workers={WORKERS} omp_per_worker=1 teacher={teacher['teacher_id']} "
                  f"executable_sha256={plan['executableSha256']} "
                  f"plan_sha256={sha256(plan_path)}", flush=True)
        else:
            run_phase(root, args.phase, plan_path)
    except Exception as error:
        print(f"STAGE_C_COLLECTION_ERROR: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
