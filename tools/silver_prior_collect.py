#!/usr/bin/env python3
"""Reviewed-SHA collection driver. Run full phases only on designated GCP.

Durable layout: binding.json, sources/<seed>.json.gz, selection.json,
jobs/<role>/<root hash>.json, raw/<role>/<root hash>.json.gz,
shards/L/<root hash>.json.gz, failures/, release.json, report.json.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import silver_prior_dataset as d
from silver_prior_projection import canonical, digest, project, require


def git(*args):
    return subprocess.check_output(["git", *args], cwd=d.ROOT, text=True).strip()


def durable(path):
    path = Path(path).resolve()
    require(not str(path).startswith("/tmp/") and "/.codex/worktrees/" not in str(path)
            and path != d.ROOT and d.ROOT not in path.parents,
            "corpus storage must be durable and outside temporary/source worktrees")
    return path


def bind(plan, vocab, review, source_binary, label_binary, corpus):
    d.validate_plan(plan)
    require(plan["vocabulary_sha256"] == vocab["sha256"], "plan vocabulary")
    from ironclad_reachable_domain_census import build_census
    require(d.vocabulary(build_census()) == vocab, "execution-source census changed")
    sha = git("rev-parse", "HEAD")
    require(review["reviewed_sha"] == sha and review["implementation_review"] == "PASS"
            and review["reviewer"] and review["evidence_reference"], "independent reviewed SHA required")
    require(not git("status", "--porcelain", "--untracked-files=no"), "dirty execution source")
    binding = d.seal({"schema": "silver_prior_execution_v1", "plan_sha256": plan["sha256"],
                      "vocabulary_sha256": vocab["sha256"], "review": review,
                      "executable_git_sha": sha,
                      "source_binary": {"path": str(Path(source_binary).resolve()),
                                        "sha256": d.file_hash(source_binary)},
                      "label_binary": {"path": str(Path(label_binary).resolve()),
                                       "sha256": d.file_hash(label_binary)},
                      "models": {p: d.file_hash(d.ROOT / p) for p in
                                 ("models/v_rich_trees.txt", "models/v_win_trees.txt")},
                      "source_environment": {**d.ENV, "OMP_NUM_THREADS": "1"}, "silver_upstream_sha": d.SILVER,
                      "source_worktree": str(d.ROOT)})
    d.publish(corpus / "binding.json", binding)
    d.publish(corpus / "plan.json", plan)
    d.publish(corpus / "vocabulary.json", vocab)
    return binding


def check_binding(corpus):
    binding, plan, vocab = [d.read(corpus / name) for name in
                             ("binding.json", "plan.json", "vocabulary.json")]
    d.check_seal(binding)
    d.validate_plan(plan)
    require(binding["schema"] == "silver_prior_execution_v1"
            and binding["plan_sha256"] == plan["sha256"]
            and binding["vocabulary_sha256"] == vocab["sha256"], "binding contract")
    require(git("rev-parse", "HEAD") == binding["executable_git_sha"]
            and not git("status", "--porcelain", "--untracked-files=no"), "changed execution checkout")
    for name in ("source_binary", "label_binary"):
        require(d.file_hash(binding[name]["path"]) == binding[name]["sha256"], "changed executable")
    for path, expected in binding["models"].items():
        require(d.file_hash(d.ROOT / path) == expected, "changed model")
    return binding, plan, vocab


def execution_env(binding):
    env = {k: v for k, v in os.environ.items() if not k.startswith("STS_")}
    env.update(d.ENV, STS_EXECUTABLE_GIT_SHA=binding["executable_git_sha"])
    env["OMP_NUM_THREADS"] = "1"
    return env


def guard_command(command, env):
    # Guard validates each native call. Aggregate full-run authorization is
    # separately confined by require_execution_host(), never split into local batches.
    return subprocess.run(["bash", str(d.ROOT / "tools/seed_guard.sh"), *map(str, command)],
                          cwd=d.ROOT, env=env, capture_output=True, text=True)


def require_execution_host(pilot):
    if not pilot:
        require(socket.gethostname() == "sts-test"
                and os.environ.get("STS_GCP_RESEARCH_CONTEXT") == "sts-test"
                and Path.cwd() == Path("/home/philippherrmann/sts_sweep"),
                "full collection requires designated tools/agent/gcp_benchmark.py run path (research guard)")


def source_seeds(plan, pilot):
    return plan["pilot_sources"] if pilot else [s["seed"] for s in plan["sources"]]


@contextmanager
def attempt(corpus, prefix):
    # Durable attempt files survive process interruption and malformed output.
    # Successful roots are separately compressed and atomically published.
    directory = corpus / "attempts"
    directory.mkdir(parents=True, exist_ok=True)
    yield Path(tempfile.mkdtemp(prefix=prefix, dir=directory))


def capture(corpus, pilot):
    require_execution_host(pilot)
    binding, plan, _ = check_binding(corpus)
    for seed in source_seeds(plan, pilot):
        target = corpus / "sources" / f"{seed}.json.gz"
        failure = corpus / "failures" / f"source-{seed}.json"
        if target.exists():
            saved = d.read(target)
            d.check_seal(saved)
            require(saved["binding_sha256"] == binding["sha256"] and saved["seed"] == seed,
                    "resumed capture binding")
            continue
        require(not failure.exists(), f"preserved source failure needs review: {failure}")
        with attempt(corpus, f"capture-{seed}-") as temp:
            tmp = Path(temp)
            env = execution_env(binding)
            env["STS_SILVER_ROOT_MECHANISM_CAPTURE"] = str(tmp / "roots.jsonl")
            started = time.monotonic()
            result = guard_command([binding["source_binary"]["path"], "bestbench", "10000", "1", "0",
                                    str(seed), str(tmp / "run.csv")], env)
            # Keep stdout/stderr and partial observations even on source failure.
            saved = {"schema": "silver_prior_source_v1", "binding_sha256": binding["sha256"],
                     "seed": seed, "seconds": time.monotonic() - started,
                     "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                     "capture": [], "attempt": str(tmp.relative_to(corpus)),
                     "files": {p.name: p.read_text() for p in tmp.iterdir() if p.name != "roots.jsonl"}}
            try:
                captures = d.rows(tmp / "roots.jsonl") if (tmp / "roots.jsonl").exists() else []
                saved["capture"] = captures
                from agent.check_benchmark_canary import validate
                log = tmp / "canary.log"
                log.write_text(result.stdout + result.stderr)
                saved["canary"] = validate(argparse.Namespace(
                    results=tmp / "run.csv", meta=tmp / "run.csv.meta.json", log=log,
                    expect_asc=0, expect_threads=1, expect_fair=True, expect_searcher3=False,
                    binary=Path(binding["source_binary"]["path"]),
                    expect_binary_sha256=binding["source_binary"]["sha256"],
                    expect_seeds=1, expect_sims=10000, expect_seed_lo=seed,
                    expect_backend="silver", expect_executable_sha=binding["executable_git_sha"],
                    expect_silver_reuse_cap_mode="allocated"))
                require(result.returncode == 0 and
                        "[native OOC floor/win GBMs ON; no v_server required]" in result.stdout,
                        "native OOC load or process failure")
                d.select(plan, captures, binding["executable_git_sha"], pilot)
                require(all(r["source_seed"] == seed for r in captures), "source identity mismatch")
            except (ValueError, KeyError, OSError) as error:
                saved["validation_failure"] = str(error)
                d.publish(failure, d.seal(saved))
                raise ValueError(f"source failed; retained {failure}") from error
            d.publish(target, d.seal(saved))


def select(corpus, pilot):
    binding, plan, _ = check_binding(corpus)
    captures = []
    for seed in source_seeds(plan, pilot):
        path = corpus / "sources" / f"{seed}.json.gz"
        require(path.exists(), f"missing source completion record {seed}")
        saved = d.read(path)
        d.check_seal(saved)
        require(saved["binding_sha256"] == binding["sha256"] and saved["seed"] == seed,
                "source completion binding")
        captures.extend(saved["capture"])
    selection = d.select(plan, captures, binding["executable_git_sha"], pilot)
    d.publish(corpus / ("pilot-selection.json" if pilot else "selection.json"), selection)
    return selection


def label(corpus, pilot):
    require_execution_host(pilot)
    binding, plan, vocab = check_binding(corpus)
    selection = d.read(corpus / ("pilot-selection.json" if pilot else "selection.json"))
    d.check_seal(selection)
    require(selection["plan_sha256"] == plan["sha256"]
            and selection["executable_git_sha"] == binding["executable_git_sha"], "selection binding")
    for entry in selection["entries"]:
        key = d.identity_hash(entry["root"])
        for role in (["L", "J"] if entry["judge_selected"] else ["L"]):
            job = d.job_for(entry, plan, binding["executable_git_sha"], role)
            job_path = corpus / "jobs" / role / f"{key}.json"
            raw_path = corpus / "raw" / role / f"{key}.json.gz"
            failure = corpus / "failures" / f"{role}-{key}.json"
            d.publish(job_path, job)
            if raw_path.exists():
                raw = d.read(raw_path)
                d.validate_raw(raw, job)
            else:
                require(not failure.exists(), f"preserved label failure needs review: {failure}")
                with attempt(corpus, f"label-{role}-{key}-") as temp:
                    output = Path(temp) / "raw.json"
                    started = time.monotonic()
                    result = guard_command([binding["label_binary"]["path"], job_path, output],
                                           execution_env(binding))
                    measurement = {"seconds": time.monotonic() - started, "returncode": result.returncode,
                                   "stdout": result.stdout, "stderr": result.stderr, "job_sha256": digest(job),
                                   "attempt": str(Path(temp).relative_to(corpus))}
                    raw = None
                    try:
                        raw = d.read(output) if output.exists() else None
                        require(result.returncode == 0 and raw is not None, "native label failure")
                        d.validate_raw(raw, job)
                    except (ValueError, KeyError, OSError) as error:
                        d.publish(failure, {"job": job, "raw": raw, "measurement": measurement,
                                            "failure": str(error)})
                        raise
                    raw["measurement"] = measurement
                    d.publish(raw_path, raw)
            d.publish(corpus / "timing" / role / f"{key}.json", raw["measurement"])
            if role == "L":
                try:
                    stored = d.shard(raw, job, vocab)
                    d.publish(corpus / "shards" / "L" / f"{key}.json.gz", stored)
                except (ValueError, KeyError) as error:
                    d.publish(failure, {"job": job, "stage": "projection", "failure": str(error),
                                        "raw_sha256": d.file_hash(raw_path)})
                    raise


def finalize(corpus, pilot):
    binding, plan, vocab = check_binding(corpus)
    selection = d.read(corpus / ("pilot-selection.json" if pilot else "selection.json"))
    d.check_seal(selection)
    shards, files, l_seconds, actual_sims, j_roots, failures = [], [], 0.0, 0, 0, []
    j_actions = j_replicates = j_simulations = 0
    for entry in selection["entries"]:
        key = d.identity_hash(entry["root"])
        for role in (["L", "J"] if entry["judge_selected"] else ["L"]):
            raw_path = corpus / "raw" / role / f"{key}.json.gz"
            if not raw_path.exists():
                failures.append({"root_id": entry["root"]["root_id"], "role": role, "reason": "missing raw root"})
                continue
            job = d.job_for(entry, plan, binding["executable_git_sha"], role)
            raw = d.read(raw_path)
            d.validate_raw(raw, job)
            files.append({"path": str(raw_path.relative_to(corpus)), "sha256": d.file_hash(raw_path)})
            if role == "J":
                j_roots += 1
                j_actions += len(raw["actions"])
                j_replicates += sum(len(a["replicates"]) for a in raw["actions"])
                j_simulations += sum(r["simulations"] for a in raw["actions"] for r in a["replicates"])
                continue
            path = corpus / "shards" / "L" / f"{key}.json.gz"
            stored = d.read(path)
            require(stored == d.shard(raw, job, vocab), "invalid shard")
            shards.append(stored)
            files.append({"path": str(path.relative_to(corpus)), "sha256": d.file_hash(path)})
            timing = d.read(corpus / "timing" / "L" / f"{key}.json")
            l_seconds += timing["seconds"]
            actual_sims += sum(r["simulations"] for a in raw["actions"] for r in a["replicates"])
    report = d.audit(shards, selection["entries"])
    report.update(pilot=pilot, failures=failures, judge_roots=j_roots,
                  source_seeds_completed=len(source_seeds(plan, pilot)),
                  source_seeds_intended=512, selected_sources_with_roots=report["source_seeds"],
                  requested_L_simulations=40000 * report.get("legal_actions", 0),
                  actual_L_simulations=actual_sims, measured_L_seconds=l_seconds,
                  judge_legal_actions=j_actions, judge_replicate_rows=j_replicates,
                  requested_J_simulations=80000 * j_actions, actual_J_simulations=j_simulations,
                  locked_test_integrity_only=True)
    report["training_ready"] = (not pilot and report["training_ready"]
                                and not failures and not report["missing_roots"])
    if pilot and shards:
        # Extrapolation is explicit, based on measured pilot costs, never an ETA.
        capture_seconds = sum(d.read(corpus / "sources" / f"{s}.json.gz")["seconds"]
                              for s in plan["pilot_sources"])
        report["forecast"] = {"measured_capture_seconds": capture_seconds,
                              "capture_serial_seconds_512": capture_seconds * 512 / 16,
                              "L_serial_seconds_per_selected_root": l_seconds / len(shards),
                              "L_serial_seconds_12288_root_ceiling": l_seconds / len(shards) * 12288,
                              "J": "80,000 per judged legal action; J throughput unmeasured in TRAIN pilot",
                              "compressed_bytes_per_root": sum((corpus / f["path"]).stat().st_size
                                                                for f in files) / len(shards),
                              "limitation": "pilot is early/later coverage, at most 2 roots per act; serial extrapolation, no parallel wall-time claim"}
    overlaps = {r["root_id"] for group in report["cross_split_duplicates"] for r in group}
    release = d.seal({"schema": "silver_prior_release_v1", "binding_sha256": binding["sha256"],
                      "selection_sha256": selection["sha256"], "files": files,
                      "quarantined_roots": sorted(overlaps), "training_ready": report["training_ready"]})
    prefix = "pilot-" if pilot else ""
    # Incomplete reports are attempts, never immutable release markers blocking a resume.
    if failures or report["missing_roots"]:
        d.publish(corpus / "reports" / f"{prefix}incomplete-{digest(report)}.json", report)
    else:
        d.publish(corpus / f"{prefix}release.json", release)
        d.publish(corpus / f"{prefix}report.json", report)
    print(canonical(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("bind", "capture", "select", "label", "finalize"))
    parser.add_argument("corpus", type=durable)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--plan")
    parser.add_argument("--vocabulary")
    parser.add_argument("--review")
    parser.add_argument("--source-binary")
    parser.add_argument("--label-binary")
    args = parser.parse_args()
    if args.phase == "bind":
        require(all((args.plan, args.vocabulary, args.review, args.source_binary, args.label_binary)),
                "bind requires plan, vocabulary, review and both binaries")
        bind(d.read(args.plan), d.read(args.vocabulary), d.read(args.review),
             args.source_binary, args.label_binary, args.corpus)
    else:
        {"capture": capture, "select": select, "label": label, "finalize": finalize}[args.phase](args.corpus, args.pilot)


if __name__ == "__main__":
    main()
