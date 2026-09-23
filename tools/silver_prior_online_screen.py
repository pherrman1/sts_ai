#!/usr/bin/env python3
"""Fail-closed parser and artifact preflight for the frozen Silver prior screen."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

EXPECTED_ARTIFACT_SHA256 = "b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb"
TELEMETRY_PREFIX = "[silver-combat] "
REQUIRED_COUNTERS = {
    "decisions", "simulations", "prior_model_loaded", "prior_eligible_decisions",
    "prior_evaluations", "prior_skipped_forced", "prior_skipped_non_player_normal",
    "prior_surface_failures", "prior_inference_micros", "root_puct_decisions",
    "transaction_decisions", "transaction_failures", "conversion_failures",
    "semantic_resolution_failures", "knowledge_failures",
}
GAUGES = {"prior_model_loaded"}
DERIVED = {
    "prior_inference_mean_micros", "prior_inference_p50_micros",
    "prior_inference_p95_micros", "rollout_fraction", "rollout_mean_micros",
    "rollout_p50_micros", "rollout_p90_micros", "rollout_p99_micros",
}
FAILURE_COUNTERS = {
    "prior_surface_failures", "transaction_failures", "conversion_failures",
    "semantic_resolution_failures", "knowledge_failures",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(path: Path, expected_sha256: str = EXPECTED_ARTIFACT_SHA256) -> str:
    if not path.is_file():
        raise ValueError(f"treatment artifact is not a regular file: {path}")
    actual = file_sha256(path)
    if actual != expected_sha256:
        raise ValueError(f"treatment artifact SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    return actual


def _number(raw: str, field: str):
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"non-numeric telemetry value for {field}: {raw}") from exc
    if not math.isfinite(value):
        raise ValueError(f"non-finite telemetry value for {field}: {raw}")
    return int(value) if value.is_integer() else value


def parse_telemetry(log_text: str, require_latency_samples: bool = False) -> dict:
    rows = []
    for line_number, line in enumerate(log_text.splitlines(), 1):
        if not line.startswith(TELEMETRY_PREFIX):
            continue
        fields = {}
        for item in line[len(TELEMETRY_PREFIX):].split():
            if "=" not in item:
                raise ValueError(f"malformed Silver telemetry token at log line {line_number}: {item}")
            key, raw = item.split("=", 1)
            if not key or key in fields:
                raise ValueError(f"duplicate or empty Silver telemetry key at log line {line_number}: {key}")
            fields[key] = raw
        absent = REQUIRED_COUNTERS - fields.keys()
        if absent:
            raise ValueError(f"missing required Silver telemetry counters at log line {line_number}: {sorted(absent)}")
        parsed = {}
        for key, raw in fields.items():
            if key == "prior_inference_samples_micros":
                parsed[key] = [] if raw == "" else [_number(x, key) for x in raw.split(",")]
            elif key in DERIVED or ":" in raw:
                continue
            else:
                parsed[key] = _number(raw, key)
        rows.append(parsed)
    if not rows:
        raise ValueError("run log contains no [silver-combat] telemetry lines")

    summary = {"combat_count": len(rows), "telemetry_lines": len(rows), "counters": {}}
    keys = set().union(*(row.keys() for row in rows)) - {"prior_inference_samples_micros"}
    for key in sorted(keys):
        values = [row[key] for row in rows if key in row]
        if key in GAUGES:
            if any(value != values[0] for value in values[1:]):
                raise ValueError(f"Silver telemetry gauge {key} changed within one process")
            summary["counters"][key] = values[0]
        else:
            summary["counters"][key] = sum(values)

    has_samples = all("prior_inference_samples_micros" in row for row in rows)
    samples = [x for row in rows for x in row.get("prior_inference_samples_micros", [])]
    if require_latency_samples and not has_samples:
        raise ValueError("latency samples required but the log lacks prior_inference_samples_micros")
    if has_samples and len(samples) != summary["counters"]["prior_evaluations"]:
        raise ValueError("prior inference sample count does not match prior_evaluations")
    summary["latency_samples_available"] = has_samples
    summary["prior_inference_samples_micros"] = samples if has_samples else []
    summary["prior_inference_mean_micros"] = (
        summary["counters"]["prior_inference_micros"] / summary["counters"]["prior_evaluations"]
        if summary["counters"]["prior_evaluations"] else None
    )
    if samples:
        ordered = sorted(samples)
        summary["prior_inference_median_micros"] = _percentile(ordered, 0.5)
        summary["prior_inference_p95_micros"] = _percentile(ordered, 0.95)
    else:
        summary["prior_inference_median_micros"] = None
        summary["prior_inference_p95_micros"] = None
    return summary


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    return sorted_values[math.ceil(fraction * len(sorted_values)) - 1]


def summarize_run(arm: str, seed: int, csv_path: Path, log_path: Path,
                  expected_git_sha: str | None = None,
                  require_latency_samples: bool = False) -> dict:
    if arm not in {"CONTROL", "LEARNED"}:
        raise ValueError("arm must be CONTROL or LEARNED")
    metadata_path = Path(str(csv_path) + ".meta.json")
    if not metadata_path.is_file():
        raise ValueError(f"missing bestbench metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text())
    cfg = metadata.get("config", {})
    git_sha = cfg.get("executableGitSha")
    if expected_git_sha and git_sha != expected_git_sha:
        raise ValueError(f"executableGitSha mismatch: expected {expected_git_sha}, got {git_sha}")
    if metadata.get("nSeeds") != 1 or metadata.get("asc") != 0 or metadata.get("sims") != 1000:
        raise ValueError("bestbench metadata does not match one-seed A0 1000-simulation protocol")
    if metadata.get("seedBlock", {}).get("lo") != seed or metadata.get("seedBlock", {}).get("hi") != seed:
        raise ValueError(f"bestbench metadata seed mismatch for {seed}")
    if cfg.get("effectiveCombatBackend") != "silver" or not cfg.get("fairPlay"):
        raise ValueError("bestbench metadata is not project-fair Silver combat")
    required_config = {
        "collectKeys": False, "searcher3": False, "silverReuseCapMode": "allocated",
        "silverReuseCap": 32768, "silverAdaptiveEnabled": False,
        "silverExactRootBudgets": True, "silverExactVisitLock": False,
        "silverRhoRacing": False,
    }

    mismatched = {key: (cfg.get(key), value) for key, value in required_config.items()
                  if cfg.get(key) != value}
    if mismatched:
        raise ValueError(f"bestbench metadata violates frozen Silver configuration: {mismatched}")
    if metadata.get("threads") != 1:
        raise ValueError("bestbench metadata is not single-threaded")

    log_text = log_path.read_text()
    if "[bestbench-seed-failure]" in log_text or re.search(r"^bestbench: FAILED\b", log_text, re.M):
        raise ValueError("bestbench log records a failed seed")
    if not re.search(r"^BEST\s+", log_text, re.M):
        raise ValueError("bestbench log has no successful BEST completion summary")
    with csv_path.open(newline="") as stream:
        outcomes = list(csv.DictReader(stream))
    if len(outcomes) != 1 or int(outcomes[0]["seed"]) != seed:
        raise ValueError(f"bestbench CSV must contain exactly one row for seed {seed}")
    outcome = outcomes[0]
    telemetry = parse_telemetry(log_text, require_latency_samples)
    counters = telemetry["counters"]
    if counters["simulations"] != 1000 * counters["decisions"]:
        raise ValueError("summed simulations do not equal 1000 times searched decisions")
    if any(counters[key] != 0 for key in FAILURE_COUNTERS):
        raise ValueError("one or more fail-closed runtime failure counters are nonzero")
    if arm == "LEARNED":
        if not counters["prior_model_loaded"] or counters["prior_evaluations"] <= 0:
            raise ValueError("LEARNED run did not load and evaluate the frozen prior")
        if counters["prior_evaluations"] != counters["root_puct_decisions"]:
            raise ValueError("LEARNED prior evaluations do not match root-PUCT decisions")
    elif counters["prior_evaluations"] != 0 or counters["root_puct_decisions"] != 0:
        raise ValueError("CONTROL run made learned-prior or root-PUCT calls")

    return {
        "arm": arm, "seed": seed, "outcome": {k: outcome[k] for k in outcome},
        "provenance": {"executable_git_sha": git_sha,
                       "expected_git_sha": expected_git_sha,
                       "metadata_path": str(metadata_path)},
        "telemetry": telemetry,
    }


def summarize_screen(summary_paths: list[Path], expected_git_sha: str) -> dict:
    """Require exactly one validated CONTROL/LEARNED pair for every frozen seed."""
    expected = {(arm, seed) for seed in range(24100000, 24100032)
                for arm in ("CONTROL", "LEARNED")}
    runs = {}
    artifact_hashes = set()
    for path in summary_paths:
        run = json.loads(path.read_text())
        key = (run.get("arm"), run.get("seed"))
        if key not in expected:
            raise ValueError(f"unexpected arm/seed in screen packet: {key}")
        if key in runs:
            raise ValueError(f"duplicate arm/seed in screen packet: {key}")
        if run.get("provenance", {}).get("executable_git_sha") != expected_git_sha:
            raise ValueError(f"summary executableGitSha mismatch for {key}")
        telemetry = run.get("telemetry", {})
        counters = telemetry.get("counters", {})
        if not telemetry.get("latency_samples_available"):
            raise ValueError(f"latency samples missing for {key}")
        if counters.get("simulations") != 1000 * counters.get("decisions", -1):
            raise ValueError(f"simulation budget mismatch for {key}")
        if any(counters.get(name) != 0 for name in FAILURE_COUNTERS):
            raise ValueError(f"runtime failure counter nonzero for {key}")
        if key[0] == "LEARNED":
            if counters.get("prior_evaluations", 0) <= 0:
                raise ValueError(f"LEARNED run has no prior evaluations for {key}")
            if counters.get("prior_evaluations") != counters.get("root_puct_decisions"):
                raise ValueError(f"prior evaluation/root-PUCT mismatch for {key}")
            if counters.get("prior_model_loaded") != 1:
                raise ValueError(f"LEARNED model was not loaded for {key}")
            artifact_hashes.add(run.get("artifact_sha256_prelaunch"))
        elif counters.get("prior_evaluations") != 0 or counters.get("root_puct_decisions") != 0:
            raise ValueError(f"CONTROL run invoked the learned prior for {key}")
        runs[key] = run
    missing = sorted(expected - runs.keys())
    if missing:
        raise ValueError(f"screen packet missing {len(missing)} arm/seed runs; first: {missing[:4]}")
    if artifact_hashes != {EXPECTED_ARTIFACT_SHA256}:
        raise ValueError(f"screen packet treatment artifact hashes differ from frozen artifact: {artifact_hashes}")

    totals = {}
    for arm in ("CONTROL", "LEARNED"):
        rows = [run for (row_arm, _), run in runs.items() if row_arm == arm]
        counters = {}
        for row in rows:
            for name, value in row["telemetry"]["counters"].items():
                if name not in GAUGES:
                    counters[name] = counters.get(name, 0) + value
        all_samples = []
        for row in rows:
            all_samples.extend(row["telemetry"].get("prior_inference_samples_micros", []))
        totals[arm] = {"seed_count": len(rows), "counters": counters,
                       "prior_inference_mean_micros": (
                           counters.get("prior_inference_micros", 0) / counters["prior_evaluations"]
                           if counters.get("prior_evaluations", 0) else None),
                       "prior_inference_median_micros": _percentile(sorted(all_samples), 0.5) if all_samples else None,
                       "prior_inference_p95_micros": _percentile(sorted(all_samples), 0.95) if all_samples else None}
    return {"schema": "silver_prior_online_screen_v1", "expected_git_sha": expected_git_sha,
            "seed_block": [24100000, 24100031], "pair_count": 32,
            "artifact_sha256": EXPECTED_ARTIFACT_SHA256,
            "runs": 64, "arms": totals}


def _run_pair(repo: Path, binary: Path, artifact: Path, output_dir: Path,
              seed: int, expected_git_sha: str) -> dict:
    if not 24100000 <= seed <= 24100031:
        raise ValueError("run-pair accepts only the frozen scientific block 24100000..24100031")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != expected_git_sha:
        raise ValueError(f"checkout SHA mismatch: expected {expected_git_sha}, got {head}")
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True,
                           capture_output=True, text=True).stdout
    if dirty:
        raise ValueError("checkout must be clean before a frozen run-pair")
    if not binary.is_file():
        raise ValueError(f"one_combat executable does not exist: {binary}")
    output_dir.mkdir(parents=True, exist_ok=True)
    arms = ("CONTROL", "LEARNED") if seed % 2 == 0 else ("LEARNED", "CONTROL")
    results = {}
    for arm in arms:
        csv_path = output_dir / f"{arm}-{seed}.csv"
        log_path = output_dir / f"{arm}-{seed}.log"
        summary_path = output_dir / f"{arm}-{seed}.summary.json"
        for path in (csv_path, Path(str(csv_path) + ".meta.json"), log_path, summary_path):
            if path.exists():
                raise ValueError(f"refusing to overwrite existing run evidence: {path}")

        # Hash immediately before each process launch; in particular, repeat
        # the check after CONTROL and immediately before the treatment batch.
        artifact_sha = verify_artifact(artifact)
        env = os.environ.copy()
        common = {
            "OMP_NUM_THREADS": "1", "STS_THREADS": "1", "STS_FAIR": "1",
            "STS_SEARCHER3": "0", "STS_NATIVE_OOC": "1", "STS_SILVER_SEARCH": "1",
            "STS_STOP_AFTER_ACT": "3", "STS_COLLECT_KEYS": "0",
            "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
            "STS_SILVER_REUSE_CAP": "32768", "STS_SILVER_REUSE_CAP_MODE": "allocated",
            "STS_SILVER_EXACT_VISIT_LOCK": "0", "STS_SILVER_RHO_RACING": "0",
            "STS_SILVER_VNET_LEAF_DIRECT": "0", "STS_SILVER_TELEMETRY": "1",
            "STS_SILVER_PRIOR_LATENCY_SAMPLES": "1", "STS_OOC_MCTS": "0",
            "STS_SIM_ADAPT": "0", "STS_CONVERGE": "0", "STS_CONV_ROOT": "0",
        }
        env.update(common)
        env.pop("STS_SILVER_ROOT_PRIOR_MODEL", None)
        if arm == "LEARNED":
            env["STS_SILVER_ROOT_PRIOR_MODEL"] = str(artifact.resolve())
        command = ["bash", "tools/seed_guard.sh", str(binary), "bestbench",
                   "1000", "1", "0", str(seed), str(csv_path)]
        with log_path.open("w") as log:
            completed = subprocess.run(command, cwd=repo, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, check=False)
        if completed.returncode != 0:
            raise ValueError(f"{arm} seed {seed} failed with exit code {completed.returncode}; inspect {log_path}")
        result = summarize_run(arm, seed, csv_path, log_path,
                               expected_git_sha, require_latency_samples=True)
        result["artifact_sha256_prelaunch"] = artifact_sha
        summary_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        results[arm] = result
    return {"seed": seed, "arm_order": list(arms), "runs": results}


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-artifact", help="hash the frozen treatment artifact before a batch")
    verify.add_argument("--artifact", type=Path, required=True)
    run = sub.add_parser("summarize-run", help="validate and aggregate one full-run log")
    run.add_argument("--arm", choices=("CONTROL", "LEARNED"), required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--csv", type=Path, required=True)
    run.add_argument("--log", type=Path, required=True)
    run.add_argument("--expected-git-sha")
    run.add_argument("--require-latency-samples", action="store_true")
    pair = sub.add_parser("run-pair", help="run one alternating, seed-guarded scientific pair")
    pair.add_argument("--repo", type=Path, default=Path(__file__).parents[1])
    pair.add_argument("--binary", type=Path, required=True)
    pair.add_argument("--artifact", type=Path, required=True)
    pair.add_argument("--output-dir", type=Path, required=True)
    pair.add_argument("--seed", type=int, required=True)
    pair.add_argument("--expected-git-sha", required=True)
    screen = sub.add_parser("summarize-screen", help="validate the complete 32-pair evidence packet")
    screen.add_argument("--expected-git-sha", required=True)
    screen.add_argument("summaries", nargs="+", type=Path,
                        help="64 per-run JSON summaries from run-pair")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-artifact":
            result = {"artifact": str(args.artifact),
                      "sha256": verify_artifact(args.artifact), "verified": True}
        elif args.command == "summarize-run":
            result = summarize_run(args.arm, args.seed, args.csv, args.log,
                                   args.expected_git_sha, args.require_latency_samples)
        elif args.command == "summarize-screen":
            result = summarize_screen(args.summaries, args.expected_git_sha)
        else:
            repo = args.repo.resolve()
            binary = args.binary if args.binary.is_absolute() else repo / args.binary
            artifact = args.artifact if args.artifact.is_absolute() else repo / args.artifact
            output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
            result = _run_pair(repo, binary.resolve(), artifact.resolve(), output_dir.resolve(),
                               args.seed, args.expected_git_sha)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"silver_prior_online_screen: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
