#!/usr/bin/env python3
"""Strict analyzer for the frozen 512-pair DeepSets CTM confirmation.

This is intentionally separate from the earlier exploratory 64-pair analyzer.
It accepts only the predeclared seed block, arms, artifacts, configuration,
trace schema, and paired bootstrap decision rule in the handoff.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import platform
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np


FROZEN_SHA = "c9ecfb2041f8061d89bd728b8dccded2e8e12adf"
SEED_START = 990000
SEED_COUNT = 512
ASCENSION = 0
COMBAT_BUDGET = 10000
OOC_SIMULATIONS = 2048
THREADS = 24
NONINFERIORITY_MARGIN = -0.05
BOOTSTRAP_REPLICATES = 500_000
BOOTSTRAP_SEED = 20260924
SILVER_SHA = "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff"
FROZEN_BINARY_SHA256 = "c08bdd7e37a26c0ad47d3b6e75c0e08dcc729fc49191553e0fcbbc169d10d244"

ARTIFACT_SHAS = {
    "standard_ctm": "e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd",
    "fast_ctm": "a23c0f86593fef2380c3efee3cf75783bf2b5e714395ec93237fac19376bfd1a",
    "v4_policy": "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c",
    "floor_model": "3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3",
    "win_model": "fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70",
}

RESULT_FIELDS = ("seed", "won", "floor", "act", "hpEnd", "maxHp", "fightsLost", "sec")
TRACE_FIELDS = (
    "seed", "oocDecisions", "mctsOwned", "mctsFallback", "simulations",
    "mctsWallSec", "mctsCpuSec", "realCombats", "imaginedCombats",
    "unsupportedCombats", "mctsSupportAborts", "preparedCombats",
    "hybridPreparations", "hybridFastPreparations", "hybridFallbackPreparations",
    "hybridFastSamples", "hybridFallbackSamples", "hybridFallbackRate",
    "hybridUniqueBrewStates", "hybridFastSupportFailures",
    "hybridFallbackSupportFailures", "continuationLimitAborts",
)
HYBRID_COUNTERS = (
    "hybridPreparations", "hybridFastPreparations", "hybridFallbackPreparations",
    "hybridFastSamples", "hybridFallbackSamples", "hybridUniqueBrewStates",
    "hybridFastSupportFailures", "hybridFallbackSupportFailures",
)
SUPPORT_FAILURE_FIELDS = (
    "conversion_failures", "semantic_resolution_failures",
    "transaction_failures", "knowledge_failures",
)
TREATMENT_ENV_KEYS = {
    "STS_OOC_MCTS_COMBAT_MODEL",
    "STS_OOC_MCTS_BREW_FALLBACK_MODEL",
    "STS_OOC_MCTS_TRACE",
}


class EvidenceError(ValueError):
    """An integrity, provenance, configuration, or schema error."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv_keyed(path: Path, required: Iterable[str]) -> dict[int, dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames is not None, f"{path}: missing CSV header")
            missing = sorted(set(required) - set(reader.fieldnames))
            require(not missing, f"{path}: missing columns {missing}")
            rows = list(reader)
    except OSError as exc:
        raise EvidenceError(f"cannot read {path}: {exc}") from exc
    keyed: dict[int, dict[str, str]] = {}
    for row in rows:
        try:
            seed = int(row["seed"])
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"{path}: malformed seed {row.get('seed')!r}") from exc
        require(seed not in keyed, f"{path}: duplicate seed {seed}")
        keyed[seed] = row
    return keyed


def read_one_json(path: Path) -> dict[str, Any]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot parse {path}: {exc}") from exc
    require(len(values) == 1 and isinstance(values[0], dict), f"{path}: expected one JSON object")
    return values[0]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot parse {path}: {exc}") from exc
    require(all(isinstance(row, dict) for row in rows), f"{path}: each JSONL record must be an object")
    return rows


def read_log(path: Path) -> str:
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    except OSError as exc:
        raise EvidenceError(f"cannot read run log {path}: {exc}") from exc


def expected_common_environment(v4_path: str) -> dict[str, str]:
    return {
        "HOME": "/home/philippherrmann",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "OMP_NUM_THREADS": str(THREADS),
        "STS_EXECUTABLE_GIT_SHA": FROZEN_SHA,
        "STS_FAIR": "1",
        "STS_SILVER_SEARCH": "1",
        "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
        "STS_SILVER_REUSE_CAP": "32768",
        "STS_SILVER_REUSE_CAP_MODE": "allocated",
        "STS_SILVER_ADAPTIVE": "0",
        "STS_SILVER_VNET_LEAF_DIRECT": "0",
        "STS_SILVER_TELEMETRY": "1",
        "STS_NATIVE_OOC": "1",
        "STS_OOC_STRATEGIC_TOK_NN": v4_path,
        "STS_OOC_STRATEGIC_REST": "1",
        "STS_OOC_STRATEGIC_EVENT": "1",
        "STS_OOC_STRATEGIC_SHOP": "1",
        "STS_OOC_STRATEGIC_TREASURE": "1",
        "STS_OOC_STRATEGIC_BOSS_RELIC": "1",
        "STS_OOC_STRATEGIC_MARGIN": "1.0",
        "STS_STOP_AFTER_ACT": "3",
        "STS_COLLECT_KEYS": "0",
        "STS_OOC_MCTS": "1",
        "STS_OOC_MCTS_SIMS": str(OOC_SIMULATIONS),
        "STS_OOC_MCTS_PRIOR": "policy",
        "STS_OOC_MCTS_LEAF_VALUE": "native",
        "STS_OOC_MCTS_LEAF_POLICY": "v4",
        "STS_OOC_MCTS_EARLY_STOP": "1",
        "STS_OOC_MCTS_GAP_STOP_20": "0",
        "STS_OOC_MCTS_ROOT_SELECTION": "visits",
        "STS_OOC_MCTS_TEMPERATURE": "1",
        "STS_OOC_MCTS_CPUCT": "1.5",
        "STS_OOC_MCTS_WIDEN_K": "2",
        "STS_OOC_MCTS_WIDEN_ALPHA": "0.5",
        "STS_OOC_MCTS_MAX_DEPTH": "32",
        "STS_OOC_MCTS_LEAF_COMBATS": "0",
    }


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot parse run manifest {path}: {exc}") from exc
    require(isinstance(payload, dict), "run manifest must be a JSON object")
    return payload


def manifest_arm(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [arm for arm in manifest.get("arms", []) if arm.get("name") == name]
    require(len(matches) == 1, f"run manifest must contain exactly one arm {name}")
    return matches[0]


def validate_manifest(manifest: dict[str, Any], local_files: dict[str, Path], expected_hashes: dict[str, str],
                      seed_start: int = SEED_START, seed_count: int = SEED_COUNT) -> dict[str, dict[str, Any]]:
    require(manifest.get("schema_version") == 2, "confirmation requires run manifest schema_version 2")
    require(manifest.get("environment_policy") == "clean", "run manifest must use a clean process environment")
    require(manifest.get("frozen_sha") == FROZEN_SHA, "run manifest frozen SHA mismatch")
    command = manifest.get("command")
    require(command == [manifest.get("binary", {}).get("remote_path"), "bestbench",
                        str(COMBAT_BUDGET), str(seed_count), str(ASCENSION), str(seed_start), "{results}"],
            f"run manifest command does not match the frozen {seed_count}-seed bestbench protocol")
    require(manifest.get("expect_silver_telemetry") is True, "run manifest must require Silver telemetry")
    common = manifest.get("common_env")
    require(isinstance(common, dict), "run manifest common_env must be an object")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list), "run manifest artifacts must be a list")
    artifact_by_path: dict[str, dict[str, str]] = {}
    for item in artifacts:
        require(isinstance(item, dict) and set(item) == {"remote_path", "sha256"}, "malformed artifact entry")
        require(item["remote_path"] not in artifact_by_path, f"duplicate artifact path {item['remote_path']}")
        artifact_by_path[item["remote_path"]] = item

    require(set(local_files) == set(expected_hashes), "internal local artifact map is incomplete")
    for role, expected in expected_hashes.items():
        local = local_files[role]
        require(local.is_file(), f"missing local {role} artifact: {local}")
        actual = sha256(local)
        require(actual == expected, f"wrong local {role} SHA256: {actual} != {expected}")

    c = manifest_arm(manifest, "C")
    h = manifest_arm(manifest, "H")
    env_c = {**common, **c.get("env", {})}
    env_h = {**common, **h.get("env", {})}
    v4_path = common.get("STS_OOC_STRATEGIC_TOK_NN")
    require(isinstance(v4_path, str) and v4_path, "V4 model path is missing from common_env")
    expected_common = expected_common_environment(v4_path)
    require(common == expected_common, "common environment differs from the frozen confirmation configuration")
    require(not any("SEARCHER2" in key or "SEARCHER3" in key
                    for key in (*env_c.keys(), *env_h.keys())),
            "removed Searcher2/Searcher3 environment variables must not be restored")
    require(set(c.get("env", {})) == {"STS_OOC_MCTS_COMBAT_MODEL", "STS_OOC_MCTS_TRACE"},
            "C arm contains unexpected treatment variables")
    require(set(h.get("env", {})) == TREATMENT_ENV_KEYS,
            "H arm contains unexpected treatment variables")
    standard_path = c["env"]["STS_OOC_MCTS_COMBAT_MODEL"]
    fast_path = h["env"]["STS_OOC_MCTS_COMBAT_MODEL"]
    trace_c = c["env"]["STS_OOC_MCTS_TRACE"]
    trace_h = h["env"]["STS_OOC_MCTS_TRACE"]
    require(env_c.get("STS_OOC_MCTS_BREW_FALLBACK_MODEL") is None,
            "standard C must leave the Brew fallback model unset")
    require(h["env"].get("STS_OOC_MCTS_BREW_FALLBACK_MODEL") == standard_path,
            "H Brew fallback must point to the standard artifact path")
    require(standard_path != fast_path and trace_c != trace_h,
            "arm CTM models and trace paths must be distinct")
    for arm_name, arm, trace in (("C", c, trace_c), ("H", h, trace_h)):
        outputs = arm.get("fresh_outputs")
        required_outputs = {trace, trace + ".support.jsonl", trace + ".actions.jsonl"}
        require(isinstance(outputs, list) and set(outputs) == required_outputs
                and len(outputs) == len(required_outputs),
                f"{arm_name} fresh_outputs must include trace, support JSONL, and action JSONL")
    all_output_paths: list[str] = []
    for arm in (c, h):
        results = arm.get("results")
        log = arm.get("log")
        require(isinstance(results, str) and isinstance(log, str), "arm results/log path is missing")
        all_output_paths.extend([results, results + ".meta.json", log, *arm["fresh_outputs"]])
    require(len(all_output_paths) == len(set(all_output_paths)), "result, log, or trace output paths collide")

    model_paths = {
        "standard_ctm": standard_path,
        "fast_ctm": fast_path,
        "v4_policy": v4_path,
        "floor_model": "models/v_rich_trees.txt",
        "win_model": "models/v_win_trees.txt",
    }
    for role, remote_path in model_paths.items():
        item = artifact_by_path.get(remote_path)
        require(item is not None, f"manifest is missing loaded {role} artifact {remote_path}")
        require(item["sha256"] == expected_hashes[role],
                f"wrong manifest {role} SHA256: {item['sha256']} != {expected_hashes[role]}")
    binary = manifest.get("binary")
    require(isinstance(binary, dict) and binary.get("sha256") == expected_hashes["binary"],
            "manifest binary SHA256 differs from the pinned executable")
    return {"C": c, "H": h}


def parse_arm_log(path: Path, arm_name: str, env: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, int]]]:
    content = read_log(path)
    require(f"[ooc-strat-tok-net] loaded {env['STS_OOC_STRATEGIC_TOK_NN']}" in content,
            f"{arm_name}: V4 token model did not load from the manifest path")
    require("models/v_win_trees.txt" in content and "models/v_rich_trees.txt" in content,
            f"{arm_name}: native floor/win models did not load from their pinned paths")
    require("[bestbench-seed-failure]" not in content and "bestbench: FAILED" not in content,
            f"{arm_name}: run log records a failed seed or incomplete cohort")
    config_lines = [line.partition("[ooc-mcts-config] ")[2]
                    for line in content.splitlines() if "[ooc-mcts-config] " in line]
    require(len(config_lines) == 1, f"{arm_name}: expected exactly one effective OOC MCTS config log")
    try:
        config = json.loads(config_lines[0])
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{arm_name}: malformed effective OOC config log: {exc}") from exc
    expected = {
        "noncombatOutcomes": "sampled", "prior": "policy", "temperature": 1,
        "cPuct": 1.5, "wideningK": 2, "wideningAlpha": 0.5, "maxDepth": 32,
        "rootSelection": "visits", "earlyStop": True, "gapStop20": False,
        "leafValue": "native", "leafCombats": 0, "leafPolicy": "v4",
        "simulations": OOC_SIMULATIONS,
        "combatModel": env["STS_OOC_MCTS_COMBAT_MODEL"],
    }
    for key, value in expected.items():
        require(config.get(key) == value, f"{arm_name}: effective OOC setting {key}={config.get(key)!r}, expected {value!r}")
    if arm_name == "C":
        require(config.get("brewFallbackModel") is None
                and config.get("dispatchRule") == "single_artifact",
                "C: standard CTM unexpectedly configured a Brew fallback")
    else:
        require(config.get("brewFallbackModel") == env["STS_OOC_MCTS_BREW_FALLBACK_MODEL"]
                and config.get("dispatchRule") == "precombat_entropic_brew_to_standard",
                "H: effective Brew fallback path or dispatch rule mismatch")

    silver_rows: list[dict[str, int]] = []
    for line in content.splitlines():
        if not line.startswith("[silver-combat]"):
            continue
        fields: dict[str, int] = {}
        for token in line.partition("]")[2].split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if re.fullmatch(r"-?\d+", value):
                fields[key] = int(value)
        silver_rows.append(fields)
    require(silver_rows, f"{arm_name}: missing Silver telemetry")
    for key in SUPPORT_FAILURE_FIELDS:
        require(all(row.get(key) == 0 for row in silver_rows), f"{arm_name}: Silver telemetry {key} is nonzero or missing")
    lowered = content.lower()
    require(not re.search(r"brew[^\n]*(contract violation|artifact mismatch|fallback mismatch)", lowered),
            f"{arm_name}: run log reports a Brew fallback contract violation")
    return config, silver_rows


def validate_meta(meta: dict[str, Any], arm_name: str, expected_seed_start: int,
                  expected_seed_count: int, binary_sha: str,
                  expected_results_path: str) -> None:
    require(meta.get("objective") == "bestbench", f"{arm_name}: objective is not bestbench")
    expected_argv = ["bestbench", str(COMBAT_BUDGET), str(expected_seed_count),
                     str(ASCENSION), str(expected_seed_start), expected_results_path]
    require(meta.get("argv") == expected_argv,
            f"{arm_name}: metadata command/output path differs from the manifest")
    require(meta.get("seedBlock") == {"lo": expected_seed_start,
                                      "hi": expected_seed_start + expected_seed_count - 1},
            f"{arm_name}: wrong seed block")
    require((meta.get("nSeeds"), meta.get("sims"), meta.get("asc"), meta.get("threads"))
            == (expected_seed_count, COMBAT_BUDGET, ASCENSION, THREADS),
            f"{arm_name}: bestbench budget/ascension/thread metadata mismatch")
    config = meta.get("config", {})
    require(config.get("executableGitSha") == FROZEN_SHA,
            f"{arm_name}: executable Git SHA mismatch")
    require(config.get("effectiveCombatBackend") == "silver"
            and config.get("silverSearchEnabled") is True
            and config.get("stsSilverSearchEffective") is True,
            f"{arm_name}: effective combat backend is not Silver")
    require(config.get("fairPlay") is True, f"{arm_name}: fair-play regime mismatch")
    require(config.get("silverReuseCapMode") == "allocated"
            and config.get("silverReuseCap") == 32768,
            f"{arm_name}: Silver reuse cap configuration mismatch")
    require(config.get("silverAdaptiveEnabled") is False
            and config.get("silverExactRootBudgets") is True,
            f"{arm_name}: adaptive/exact-root Silver configuration mismatch")
    require(config.get("silverUpstreamSha") == SILVER_SHA,
            f"{arm_name}: Silver pinned SHA mismatch")
    require(config.get("collectKeys") is False,
            f"{arm_name}: key collection must be disabled")
    if "searcher3" in config:
        require(config["searcher3"] is False, f"{arm_name}: legacy Searcher3 became effective")
    models = meta.get("models", {})
    require(models.get("floor") == "models/v_rich_trees.txt"
            and models.get("win") == "models/v_win_trees.txt",
            f"{arm_name}: floor/win model paths mismatch")
    require(models.get("policyNet") == "ON" and models.get("combatVNet") == "off" and models.get("pvNet") == "off"
            and models.get("distVNet") == "off",
            f"{arm_name}: unexpected extra value-network artifacts")
    require(bool(binary_sha), f"{arm_name}: missing verified binary SHA256")


def validate_arm(directory: Path, arm_name: str, seeds: list[int], env: dict[str, str],
                 binary_sha: str, expected_results_path: str) -> dict[str, Any]:
    expected = set(seeds)
    results = read_csv_keyed(directory / "results.csv", RESULT_FIELDS)
    traces = read_csv_keyed(directory / "mcts.csv", TRACE_FIELDS)
    require(set(results) == expected, f"{arm_name}: results seeds are missing or outside the frozen block")
    require(set(traces) == expected, f"{arm_name}: trace seeds are missing or outside the frozen block")
    meta = read_one_json(directory / "results.csv.meta.json")
    validate_meta(meta, arm_name, seeds[0], len(seeds), binary_sha, expected_results_path)
    config, silver_rows = parse_arm_log(directory / "run.log.gz" if (directory / "run.log.gz").exists()
                                        else directory / "run.log", arm_name, env)
    action_trace = directory / "mcts.csv.actions.jsonl"
    action_rows = read_jsonl(action_trace)
    require(action_rows, f"{arm_name}: expected fresh MCTS action trace has no records")
    action_counts: Counter[int] = Counter()
    action_executed_counts: Counter[int] = Counter()
    action_indices: dict[int, set[int]] = {}
    action_keys = {"seed", "decisionIndex", "screen", "selector", "selectedId",
                   "selectedKey", "semantic", "compound", "executed", "reason"}
    action_ids: set[tuple[int, int]] = set()
    for row in action_rows:
        require(action_keys <= set(row), f"{arm_name}: malformed action-trace record")
        try:
            seed = int(row["seed"])
            decision_index = int(row["decisionIndex"])
            int(row["screen"])
            int(row["selector"])
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"{arm_name}: malformed action-trace numeric field") from exc
        require(seed in expected, f"{arm_name}: action trace contains out-of-block seed {seed}")
        require(decision_index >= 0, f"{arm_name} seed {seed}: negative action decision index")
        require(isinstance(row["selectedKey"], str) and isinstance(row["reason"], str)
                and all(isinstance(row[key], bool) for key in ("semantic", "compound", "executed")),
                f"{arm_name} seed {seed}: malformed action-trace field types")
        action_id = (seed, decision_index)
        require(action_id not in action_ids,
                f"{arm_name}: duplicate action trace seed/decision {action_id}")
        action_ids.add(action_id)
        action_indices.setdefault(seed, set()).add(decision_index)
        action_counts[seed] += 1
        action_executed_counts[seed] += int(row["executed"])
    support_path = directory / "mcts.csv.support.jsonl"
    support_rows = read_jsonl(support_path)
    support_by_seed: dict[int, dict[str, Any]] = {}
    for row in support_rows:
        try:
            seed = int(row["seed"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceError(f"{arm_name}: malformed support trace seed") from exc
        require(seed not in support_by_seed, f"{arm_name}: duplicate support trace seed {seed}")
        support_by_seed[seed] = row
    require(set(support_by_seed) == expected, f"{arm_name}: support trace seeds are missing or outside the frozen block")

    for seed in seeds:
        result = results[seed]
        try:
            won = int(result["won"])
            require(won in (0, 1), f"{arm_name} seed {seed}: won must be 0 or 1")
            require(0 <= int(result["act"]) <= 3,
                    f"{arm_name} seed {seed}: result exceeded the Act-3 stop horizon")
            for field in ("floor", "act", "hpEnd", "maxHp", "fightsLost"):
                int(result[field])
            run_seconds = float(result["sec"])
            require(math.isfinite(run_seconds) and run_seconds >= 0,
                    f"{arm_name} seed {seed}: invalid whole-run elapsed time")
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"{arm_name} seed {seed}: malformed bestbench metric") from exc

        trace = traces[seed]
        try:
            integers = {key: int(trace[key]) for key in TRACE_FIELDS if key not in ("mctsWallSec", "mctsCpuSec", "hybridFallbackRate")}
            for key in ("mctsWallSec", "mctsCpuSec", "hybridFallbackRate"):
                value = float(trace[key])
                require(math.isfinite(value) and value >= 0, f"{arm_name} seed {seed}: invalid {key}")
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"{arm_name} seed {seed}: malformed MCTS trace metric") from exc
        require(integers["oocDecisions"] == integers["mctsOwned"] + integers["mctsFallback"],
                f"{arm_name} seed {seed}: OOC decision accounting does not reconcile")
        require(all(value >= 0 for key, value in integers.items() if key != "seed"),
                f"{arm_name} seed {seed}: negative OOC trace count")
        require(integers["simulations"] <= OOC_SIMULATIONS * integers["oocDecisions"],
                f"{arm_name} seed {seed}: simulations exceed the configured per-decision budget")
        reasons = support_by_seed[seed]
        reason_counts = reasons.get("reasons")
        continuation_counts = reasons.get("continuation_reasons", {})
        require(isinstance(reason_counts, dict) and isinstance(continuation_counts, dict),
                f"{arm_name} seed {seed}: malformed support-reason maps")
        for mapping in (reason_counts, continuation_counts):
            require(all(isinstance(n, int) and n >= 0 for n in mapping.values()),
                    f"{arm_name} seed {seed}: support reason counts must be nonnegative integers")
        observer_skips = int(reason_counts.get("semantic_observer_active", 0))
        require(observer_skips <= integers["mctsFallback"],
                f"{arm_name} seed {seed}: semantic observer skips exceed MCTS fallbacks")
        require(sum(reason_counts.values()) - observer_skips >= integers["unsupportedCombats"],
                f"{arm_name} seed {seed}: support reason receipts are fewer than unsupported combats")
        require(action_counts[seed] == integers["oocDecisions"] - observer_skips,
                f"{arm_name} seed {seed}: action receipts are incomplete after accounting for observer skips")
        require(all(index < integers["oocDecisions"] for index in action_indices.get(seed, set())),
                f"{arm_name} seed {seed}: action trace decision index exceeds OOC decision count")
        require(action_executed_counts[seed] == integers["mctsOwned"],
                f"{arm_name} seed {seed}: executed action receipts do not reconcile with MCTS-owned decisions")
        require(int(reasons.get("continuation_limit_aborts", -1))
                == integers["continuationLimitAborts"],
                f"{arm_name} seed {seed}: continuation-limit abort counts do not reconcile")
        if arm_name == "H":
            require("entropic_brew_requires_standard_ctm" not in reason_counts
                    and "entropic_brew_requires_standard_ctm" not in continuation_counts,
                    f"H seed {seed}: entropic_brew_requires_standard_ctm escaped as unsupported")
            preps = integers["hybridPreparations"]
            fast = integers["hybridFastPreparations"]
            fallback = integers["hybridFallbackPreparations"]
            require(preps == fast + fallback,
                    f"H seed {seed}: hybrid preparation counters do not reconcile")
            rate = float(trace["hybridFallbackRate"])
            expected_rate = fallback / preps if preps else 0.0
            require(math.isclose(rate, expected_rate, rel_tol=1e-8, abs_tol=1e-10),
                    f"H seed {seed}: hybrid fallback rate does not reconcile")
        else:
            require(all(integers[key] == 0 for key in HYBRID_COUNTERS),
                    f"C seed {seed}: standard arm unexpectedly recorded hybrid counters")

    return {"results": results, "traces": traces, "support": support_by_seed,
            "meta": meta, "silverTelemetryRows": silver_rows, "oocConfig": config}


METRIC_GETTERS = {
    "win": lambda r, t: int(r["won"]),
    "finalFloor": lambda r, t: int(r["floor"]),
    "finalAct": lambda r, t: int(r["act"]),
    "endHp": lambda r, t: int(r["hpEnd"]),
    "maxHp": lambda r, t: int(r["maxHp"]),
    "fightsLost": lambda r, t: int(r["fightsLost"]),
    "wholeRunSeconds": lambda r, t: float(r["sec"]),
    "oocDecisions": lambda r, t: int(t["oocDecisions"]),
    "mctsSimulations": lambda r, t: int(t["simulations"]),
    "imaginedCombats": lambda r, t: int(t["imaginedCombats"]),
    "realCombats": lambda r, t: int(t["realCombats"]),
    "ctmPreparations": lambda r, t: int(t["preparedCombats"]),
    "supportAborts": lambda r, t: int(t["mctsSupportAborts"]),
    "mctsCpuSeconds": lambda r, t: float(t["mctsCpuSec"]),
    "mctsWallSeconds": lambda r, t: float(t["mctsWallSec"]),
}


def bootstrap_intervals(deltas: dict[str, np.ndarray], replicates: int = BOOTSTRAP_REPLICATES,
                        seed: int = BOOTSTRAP_SEED, batch_size: int = 4096) -> dict[str, list[float]]:
    require(replicates > 0 and batch_size > 0, "bootstrap size must be positive")
    lengths = {len(values) for values in deltas.values()}
    require(len(lengths) == 1 and lengths, "bootstrap metrics must have equal nonzero lengths")
    n = next(iter(lengths))
    estimates = {name: np.empty(replicates, dtype=np.float64) for name in deltas}
    rng = np.random.Generator(np.random.PCG64(seed))
    for start in range(0, replicates, batch_size):
        count = min(batch_size, replicates - start)
        indices = rng.integers(0, n, size=(count, n), endpoint=False)
        for name, values in deltas.items():
            estimates[name][start:start + count] = values[indices].mean(axis=1)
    return {name: [float(x) for x in np.quantile(values, [0.025, 0.975], method="linear")]
            for name, values in estimates.items()}


def classify(lower: float, upper: float) -> str:
    if lower > NONINFERIORITY_MARGIN:
        return "OOC_HYBRID_QUALITY_CONFIRMED"
    if upper < NONINFERIORITY_MARGIN:
        return "OOC_HYBRID_QUALITY_REJECTED"
    return "OOC_HYBRID_QUALITY_INCONCLUSIVE"


def exact_discordant_binomial_p(h_only: int, c_only: int) -> float:
    n = h_only + c_only
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(h_only, c_only) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def aggregate_support(rows: dict[int, dict[str, Any]], field: str = "reasons") -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows.values():
        for key, value in row.get(field, {}).items():
            counts[key] += int(value)
    return dict(sorted(counts.items()))


def run_analysis(standard_dir: Path, hybrid_dir: Path, manifest_path: Path,
                 local_files: dict[str, Path], summary_path: Path, per_seed_path: Path,
                 expected_hashes: dict[str, str] = ARTIFACT_SHAS,
                 expected_binary_sha256: str = FROZEN_BINARY_SHA256,
                 replicates: int = BOOTSTRAP_REPLICATES) -> dict[str, Any]:
    manifest = read_manifest(manifest_path)
    validation_hashes = {**expected_hashes, "binary": expected_binary_sha256}
    arms = validate_manifest(manifest, local_files, validation_hashes)
    binary_hash = sha256(local_files["binary"])
    c_env = {**manifest["common_env"], **arms["C"]["env"]}
    h_env = {**manifest["common_env"], **arms["H"]["env"]}
    require(arms["C"]["results"] != arms["H"]["results"]
            and arms["C"]["log"] != arms["H"]["log"], "arm results/log paths must differ")
    seeds = list(range(SEED_START, SEED_START + SEED_COUNT))
    c = validate_arm(standard_dir, "C", seeds, c_env, binary_hash, arms["C"]["results"])
    h = validate_arm(hybrid_dir, "H", seeds, h_env, binary_hash, arms["H"]["results"])
    require(c["meta"]["config"]["executableGitSha"] == h["meta"]["config"]["executableGitSha"],
            "arms used different executable Git SHAs")
    require(c["meta"].get("models") == h["meta"].get("models"),
            "arms differ in common loaded model metadata")
    paired: dict[str, dict[str, float | list[float]]] = {}
    deltas: dict[str, np.ndarray] = {}
    for name, get in METRIC_GETTERS.items():
        control = np.asarray([get(c["results"][seed], c["traces"][seed]) for seed in seeds], dtype=np.float64)
        treatment = np.asarray([get(h["results"][seed], h["traces"][seed]) for seed in seeds], dtype=np.float64)
        delta = treatment - control
        deltas[name] = delta
        paired[name] = {
            "standardMean": float(control.mean()),
            "hybridMean": float(treatment.mean()),
            "hybridMinusStandardMean": float(delta.mean()),
        }
    cis = bootstrap_intervals(deltas, replicates=replicates)
    for name, interval in cis.items():
        paired[name]["pairedBootstrap95CI"] = interval

    c_wins = sum(int(c["results"][seed]["won"]) for seed in seeds)
    h_wins = sum(int(h["results"][seed]["won"]) for seed in seeds)
    h_only = sum(int(h["results"][seed]["won"]) == 1 and int(c["results"][seed]["won"]) == 0 for seed in seeds)
    c_only = sum(int(c["results"][seed]["won"]) == 1 and int(h["results"][seed]["won"]) == 0 for seed in seeds)
    both_win = sum(
        int(c["results"][seed]["won"]) == 1 and int(h["results"][seed]["won"]) == 1
        for seed in seeds
    )
    both_lose = len(seeds) - both_win - h_only - c_only
    require(both_win + c_only == c_wins and both_win + h_only == h_wins
            and both_win + h_only + c_only + both_lose == len(seeds),
            "paired outcome contingency cells do not reconcile with marginal win counts")
    win_ci = cis["win"]
    delta = float(deltas["win"].mean())
    lower, upper = win_ci

    hybrid_traces = h["traces"]
    totals = {key: sum(int(hybrid_traces[s][key]) for s in seeds) for key in HYBRID_COUNTERS}
    prep_total = totals["hybridPreparations"]
    fallback_total = totals["hybridFallbackPreparations"]
    hybrid_diagnostics = {
        "preparations": prep_total,
        "fastPreparations": totals["hybridFastPreparations"],
        "brewFallbackPreparations": fallback_total,
        "fallbackRate": fallback_total / prep_total if prep_total else 0.0,
        "fastSamples": totals["hybridFastSamples"],
        "fallbackSamples": totals["hybridFallbackSamples"],
        "sumPerSeedUniqueBrewPredictorStates": totals["hybridUniqueBrewStates"],
        "uniqueBrewPredictorStatesAggregation": "sum of per-seed unique counts; no cross-seed deduplication",
        "fastSupportFailures": totals["hybridFastSupportFailures"],
        "fallbackSupportFailures": totals["hybridFallbackSupportFailures"],
    }

    summary = {
        "classification": classify(lower, upper),
        "analysisToolSha256": sha256(Path(__file__).resolve()),
        "frozenExecutableGitSha": FROZEN_SHA,
        "binarySha256": binary_hash,
        "artifactSha256": expected_hashes,
        "seedRange": [seeds[0], seeds[-1]],
        "seedCount": len(seeds),
        "primaryEndpoint": {
            "metric": "paired whole-run Act-3 win difference",
            "hybridMinusStandard": delta,
            "hybridMinusStandardPercentagePoints": delta * 100,
            "pairedBootstrap95CI": [lower, upper],
            "pairedBootstrap95CIPercentagePoints": [lower * 100, upper * 100],
            "nonInferiorityMargin": NONINFERIORITY_MARGIN,
            "nonInferiorityMarginPercentagePoints": NONINFERIORITY_MARGIN * 100,
        },
        "wins": {
            "standard": c_wins,
            "hybrid": h_wins,
            "hybridOnly": h_only,
            "standardOnly": c_only,
            "bothWin": both_win,
            "bothLose": both_lose,
            "exactTwoSidedDiscordantBinomialP": exact_discordant_binomial_p(h_only, c_only),
        },
        "pairedMetrics": paired,
        "hybridDiagnostics": hybrid_diagnostics,
        "supportReasons": {
            "standard": aggregate_support(c["support"]),
            "hybrid": aggregate_support(h["support"]),
        },
        "supportReasonCounterInterpretation": (
            "Counts include unsupported-combat causes and other recorded decision/search fallbacks; "
            "totals can exceed unsupportedCombats."
        ),
        "continuationReasons": {
            "standard": aggregate_support(c["support"], "continuation_reasons"),
            "hybrid": aggregate_support(h["support"], "continuation_reasons"),
        },
        "configuration": {
            "combatBudget": COMBAT_BUDGET,
            "oocMctsSimulations": OOC_SIMULATIONS,
            "ascension": ASCENSION,
            "stopAfterAct": 3,
            "keys": False,
            "threads": THREADS,
            "fairPlay": True,
            "combatBackend": "Silver",
            "silverPinnedSha": SILVER_SHA,
            "environmentPolicy": "clean",
            "standardEnvironment": c_env,
            "hybridEnvironment": h_env,
        },
        "bootstrap": {
            "replicates": replicates,
            "rng": "NumPy PCG64",
            "numpyVersion": np.__version__,
            "pythonVersion": platform.python_version(),
            "seed": BOOTSTRAP_SEED,
            "resamplingUnit": "paired seed rows",
            "interval": "two-sided percentile 95%, linear interpolation",
        },
        "timingInterpretation": "Observed whole-run and MCTS time are operational diagnostics; different decisions/search work prevent a per-call causal interpretation.",
        "screeningCohort": {
            "range": [980000, 980063],
            "includedInPrimary": False,
            "reason": "independent exploratory screen; excluded from the 512-pair confirmation statistic",
        },
    }

    per_seed_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["seed"]
    for prefix in ("standard", "hybrid"):
        fields.extend(f"{prefix}_{key}" for key in ("won", "floor", "act", "hpEnd", "maxHp", "fightsLost", "sec"))
        fields.extend(f"{prefix}_{key}" for key in ("oocDecisions", "simulations", "imaginedCombats", "realCombats", "preparedCombats", "mctsSupportAborts", "mctsCpuSec", "mctsWallSec"))
    fields.extend(["hybrid_only_win", "standard_only_win"])
    with per_seed_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for seed in seeds:
            row: dict[str, Any] = {"seed": seed}
            for prefix, arm in (("standard", c), ("hybrid", h)):
                for key in ("won", "floor", "act", "hpEnd", "maxHp", "fightsLost", "sec"):
                    row[f"{prefix}_{key}"] = arm["results"][seed][key]
                for key in ("oocDecisions", "simulations", "imaginedCombats", "realCombats", "preparedCombats", "mctsSupportAborts", "mctsCpuSec", "mctsWallSec"):
                    row[f"{prefix}_{key}"] = arm["traces"][seed][key]
            row["hybrid_only_win"] = int(h["results"][seed]["won"]) == 1 and int(c["results"][seed]["won"]) == 0
            row["standard_only_win"] = int(c["results"][seed]["won"]) == 1 and int(h["results"][seed]["won"]) == 0
            writer.writerow(row)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def synthetic_fixture(root: Path, outcomes: str,
                      expected_hashes: dict[str, str] = ARTIFACT_SHAS) -> tuple[Path, Path, Path, dict[str, Path]]:
    standard = root / "standard"
    hybrid = root / "hybrid"
    standard.mkdir(parents=True, exist_ok=True)
    hybrid.mkdir(parents=True, exist_ok=True)
    file_bytes = {
        "binary": b"frozen one_combat binary",
        "standard_ctm": b"standard CTM",
        "fast_ctm": b"fast CTM",
        "v4_policy": b"V4 policy",
        "floor_model": b"floor model",
        "win_model": b"win model",
    }
    local_files = {name: root / name for name in file_bytes}
    for name, path in local_files.items():
        path.write_bytes(file_bytes[name])
    dynamic_hashes = {name: sha256(path) for name, path in local_files.items() if name != "binary"}
    dynamic_hashes["binary"] = sha256(local_files["binary"])
    standard_path = "artifacts/confirmation/standard.native"
    fast_path = "artifacts/confirmation/fast.native"
    v4_path = "artifacts/confirmation/ooc-v4.native"
    trace_c = "results/confirmation/standard/mcts.csv"
    trace_h = "results/confirmation/hybrid/mcts.csv"
    common = expected_common_environment(v4_path)
    c_env = {"STS_OOC_MCTS_COMBAT_MODEL": standard_path, "STS_OOC_MCTS_TRACE": trace_c}
    h_env = {"STS_OOC_MCTS_COMBAT_MODEL": fast_path, "STS_OOC_MCTS_BREW_FALLBACK_MODEL": standard_path,
             "STS_OOC_MCTS_TRACE": trace_h}
    arms = [
        {"name": "C", "results": "results/confirmation/standard/results.csv", "log": "logs/confirmation/standard.log",
         "env": c_env, "fresh_outputs": [trace_c, trace_c + ".support.jsonl", trace_c + ".actions.jsonl"]},
        {"name": "H", "results": "results/confirmation/hybrid/results.csv", "log": "logs/confirmation/hybrid.log",
         "env": h_env, "fresh_outputs": [trace_h, trace_h + ".support.jsonl", trace_h + ".actions.jsonl"]},
    ]
    manifest = {
        "schema_version": 2, "environment_policy": "clean", "experiment_id": "synthetic-confirmation",
        "frozen_sha": FROZEN_SHA, "checkout": "checkouts/synthetic-confirmation",
        "build_dir": "checkouts/synthetic-confirmation/build/linux-gcc-release",
        "binary": {"remote_path": "checkouts/synthetic-confirmation/build/linux-gcc-release/one_combat",
                   "sha256": dynamic_hashes["binary"]},
        "artifacts": [
            {"remote_path": standard_path, "sha256": dynamic_hashes["standard_ctm"]},
            {"remote_path": fast_path, "sha256": dynamic_hashes["fast_ctm"]},
            {"remote_path": v4_path, "sha256": dynamic_hashes["v4_policy"]},
            {"remote_path": "models/v_rich_trees.txt", "sha256": dynamic_hashes["floor_model"]},
            {"remote_path": "models/v_win_trees.txt", "sha256": dynamic_hashes["win_model"]},
        ],
        "common_env": common,
        "required_env": ["HOME", "PATH", "OMP_NUM_THREADS", "STS_EXECUTABLE_GIT_SHA", "STS_SILVER_TELEMETRY"],
        "expect_silver_telemetry": True,
        "command": ["checkouts/synthetic-confirmation/build/linux-gcc-release/one_combat", "bestbench",
                    str(COMBAT_BUDGET), str(SEED_COUNT), str(ASCENSION), str(SEED_START), "{results}"],
        "arms": arms,
    }
    manifest_path = root / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    model_paths = {"standard_ctm": standard_path, "fast_ctm": fast_path, "v4_policy": v4_path,
                   "floor_model": "models/v_rich_trees.txt", "win_model": "models/v_win_trees.txt"}
    for arm_name, directory, arm_env in (("C", standard, c_env), ("H", hybrid, h_env)):
        results_rows: list[dict[str, Any]] = []
        trace_rows: list[dict[str, Any]] = []
        support_rows: list[dict[str, Any]] = []
        for i, seed in enumerate(range(SEED_START, SEED_START + SEED_COUNT)):
            if outcomes == "pass":
                c_win, h_win = 1, 1
            elif outcomes == "fail":
                c_win, h_win = 1, 0
            elif outcomes == "mixed":
                if i < 100:
                    c_win, h_win = 1, 1
                elif i < 120:
                    c_win, h_win = 0, 1
                elif i < 150:
                    c_win, h_win = 1, 0
                else:
                    c_win, h_win = 0, 0
            else:
                c_win, h_win = (1, 0) if i < SEED_COUNT // 2 else (0, 1)
            won = c_win if arm_name == "C" else h_win
            results_rows.append({"seed": seed, "won": won, "floor": 51, "act": 3,
                                 "hpEnd": 20, "maxHp": 80, "fightsLost": 0, "sec": 1.0})
            trace = {key: 0 for key in TRACE_FIELDS}
            trace.update({"seed": seed, "oocDecisions": 1, "mctsOwned": 1, "simulations": OOC_SIMULATIONS,
                          "mctsWallSec": 1.0, "mctsCpuSec": 0.5, "realCombats": 1,
                          "preparedCombats": 1, "hybridFallbackRate": 0.0})
            if arm_name == "H":
                trace.update({"hybridPreparations": 1, "hybridFastPreparations": 1,
                              "hybridFastSamples": 1, "hybridUniqueBrewStates": 3})
            trace_rows.append(trace)
            support_rows.append({"seed": seed, "reasons": {}, "continuation_reasons": {}, "continuation_limit_aborts": 0})
        for filename, rows in (("results.csv", results_rows), ("mcts.csv", trace_rows)):
            with (directory / filename).open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        (directory / "mcts.csv.support.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in support_rows), encoding="utf-8")
        (directory / "mcts.csv.actions.jsonl").write_text(
            "".join(json.dumps({"seed": seed, "decisionIndex": 0, "screen": 0,
                               "selector": 0, "selectedId": 0, "selectedKey": "fixture",
                               "semantic": False, "compound": False, "executed": True,
                               "reason": ""}) + "\n"
                    for seed in range(SEED_START, SEED_START + SEED_COUNT)), encoding="utf-8")
        config = {"simulations": OOC_SIMULATIONS, "combatModel": arm_env["STS_OOC_MCTS_COMBAT_MODEL"],
                  "brewFallbackModel": arm_env.get("STS_OOC_MCTS_BREW_FALLBACK_MODEL"),
                  "dispatchRule": "single_artifact" if arm_name == "C" else "precombat_entropic_brew_to_standard",
                  "noncombatOutcomes": "sampled", "prior": "policy", "temperature": 1,
                  "cPuct": 1.5, "wideningK": 2, "wideningAlpha": 0.5, "maxDepth": 32,
                  "rootSelection": "visits", "earlyStop": True, "gapStop20": False,
                  "leafValue": "native", "leafCombats": 0, "leafPolicy": "v4"}
        log = f"[ooc-strat-tok-net] loaded {common['STS_OOC_STRATEGIC_TOK_NN']}\n"
        log += "[CompactTreeNet: 1060 trees, 448 feats from models/v_win_trees.txt]\n"
        log += "[CompactTreeNet: 1256 trees, 448 feats from models/v_rich_trees.txt]\n"
        log += "[ooc-mcts-config] " + json.dumps(config) + "\n"
        log += "[silver-combat] decisions=1 simulations=10000 conversion_failures=0 semantic_resolution_failures=0 transaction_failures=0 knowledge_failures=0\n"
        (directory / "run.log").write_text(log, encoding="utf-8")
        meta = {"objective": "bestbench", "seedBlock": {"lo": SEED_START, "hi": SEED_START + SEED_COUNT - 1},
                "nSeeds": SEED_COUNT, "sims": COMBAT_BUDGET, "asc": ASCENSION, "threads": THREADS,
                "argv": ["bestbench", str(COMBAT_BUDGET), str(SEED_COUNT), str(ASCENSION),
                         str(SEED_START), arms[0 if arm_name == "C" else 1]["results"]],
                "config": {"executableGitSha": FROZEN_SHA, "effectiveCombatBackend": "silver",
                           "silverSearchEnabled": True, "stsSilverSearchEffective": True, "fairPlay": True,
                           "silverReuseCapMode": "allocated", "silverReuseCap": 32768,
                           "silverAdaptiveEnabled": False, "silverExactRootBudgets": True,
                           "silverUpstreamSha": SILVER_SHA, "searcher3": False,
                           "collectKeys": False},
                "models": {"floor": "models/v_rich_trees.txt", "win": "models/v_win_trees.txt",
                           "combatVNet": "off", "policyNet": "ON", "pvNet": "off", "distVNet": "off"}}
        (directory / "results.csv.meta.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    # Return the actual file hashes so integrity-path tests do not need synthetic
    # byte strings whose digests match production artifacts.
    return standard, hybrid, manifest_path, local_files


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="deepset-hybrid-confirmation-") as temp:
        root = Path(temp)
        local_hashes: dict[str, str] = {}
        standard, hybrid, manifest_path, files = synthetic_fixture(root, "pass")
        manifest = read_manifest(manifest_path)
        local_hashes = {key: sha256(path) for key, path in files.items()}
        artifact_roles = ("standard_ctm", "fast_ctm", "v4_policy", "floor_model", "win_model")
        for item, role in zip(manifest["artifacts"], artifact_roles):
            item["sha256"] = local_hashes[role]
        manifest["binary"]["sha256"] = local_hashes["binary"]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        synthetic_hashes = {role: local_hashes[role] for role in (*artifact_roles, "binary")}

        expected_artifact_hashes = {role: local_hashes[role] for role in artifact_roles}
        summary_path = root / "end-to-end-summary.json"
        per_seed_path = root / "end-to-end-per-seed.csv"
        summary = run_analysis(
            standard, hybrid, manifest_path, files, summary_path, per_seed_path,
            expected_hashes=expected_artifact_hashes,
            expected_binary_sha256=local_hashes["binary"], replicates=4096,
        )
        assert summary["classification"] == "OOC_HYBRID_QUALITY_CONFIRMED"
        assert summary["hybridDiagnostics"]["sumPerSeedUniqueBrewPredictorStates"] == SEED_COUNT * 3
        assert "no cross-seed deduplication" in summary["hybridDiagnostics"]["uniqueBrewPredictorStatesAggregation"]
        assert summary_path.is_file() and per_seed_path.is_file()

        def load_and_classify(mode: str) -> str:
            standard, hybrid, manifest_path, _ = synthetic_fixture(root, mode, synthetic_hashes)
            data = read_manifest(manifest_path)
            validate_manifest(data, files, synthetic_hashes)
            seeds = list(range(SEED_START, SEED_START + SEED_COUNT))
            c_manifest_arm = manifest_arm(data, "C")
            h_manifest_arm = manifest_arm(data, "H")
            c = validate_arm(standard, "C", seeds,
                             {**data["common_env"], **c_manifest_arm["env"]},
                             sha256(files["binary"]), c_manifest_arm["results"])
            h = validate_arm(hybrid, "H", seeds,
                             {**data["common_env"], **h_manifest_arm["env"]},
                             sha256(files["binary"]), h_manifest_arm["results"])
            win_deltas = np.asarray([int(h["results"][s]["won"]) - int(c["results"][s]["won"]) for s in seeds], dtype=np.float64)
            ci = bootstrap_intervals({"win": win_deltas}, replicates=4096)["win"]
            return classify(*ci)

        assert load_and_classify("pass") == "OOC_HYBRID_QUALITY_CONFIRMED"
        assert load_and_classify("fail") == "OOC_HYBRID_QUALITY_REJECTED"
        assert load_and_classify("inconclusive") == "OOC_HYBRID_QUALITY_INCONCLUSIVE"

        standard, hybrid, mixed_manifest, mixed_files = synthetic_fixture(
            root, "mixed", synthetic_hashes
        )
        mixed_summary = run_analysis(
            standard, hybrid, mixed_manifest, mixed_files,
            root / "mixed-summary.json", root / "mixed-per-seed.csv",
            expected_hashes=expected_artifact_hashes,
            expected_binary_sha256=local_hashes["binary"], replicates=4096,
        )
        assert mixed_summary["wins"]["standard"] == 130
        assert mixed_summary["wins"]["hybrid"] == 120
        assert mixed_summary["wins"]["bothWin"] == 100
        assert mixed_summary["wins"]["hybridOnly"] == 20
        assert mixed_summary["wins"]["standardOnly"] == 30
        assert mixed_summary["wins"]["bothLose"] == 362

        # Missing and duplicate rows are detected before any partial-pair analysis.
        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        with (standard / "results.csv").open(encoding="utf-8") as stream:
            lines = stream.readlines()
        (standard / "results.csv").write_text("".join(lines[:-1]), encoding="utf-8")
        try:
            data = read_manifest(manifest_path)
            seeds = list(range(SEED_START, SEED_START + SEED_COUNT))
            validate_arm(standard, "C", seeds,
                         {**data["common_env"], **manifest_arm(data, "C")["env"]},
                         sha256(files["binary"]), manifest_arm(data, "C")["results"])
        except EvidenceError as exc:
            assert "results seeds are missing" in str(exc)
        else:
            raise AssertionError("missing seed self-test did not fail")

        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        with (standard / "results.csv").open(encoding="utf-8") as stream:
            lines = stream.readlines()
        (standard / "results.csv").write_text("".join(lines) + lines[-1], encoding="utf-8")
        try:
            read_csv_keyed(standard / "results.csv", RESULT_FIELDS)
        except EvidenceError as exc:
            assert "duplicate seed" in str(exc)
        else:
            raise AssertionError("duplicate seed self-test did not fail")

        data = read_manifest(manifest_path)
        data["common_env"]["OMP_NUM_THREADS"] = "23"
        try:
            validate_manifest(data, files, synthetic_hashes)
        except EvidenceError as exc:
            assert "common environment differs" in str(exc)
        else:
            raise AssertionError("common-config mismatch self-test did not fail")

        data = read_manifest(manifest_path)
        data["arms"][1]["env"]["STS_UNEXPECTED_TREATMENT"] = "1"
        try:
            validate_manifest(data, files, synthetic_hashes)
        except EvidenceError as exc:
            assert "unexpected treatment variables" in str(exc)
        else:
            raise AssertionError("common-config mismatch self-test did not fail")

        data = read_manifest(manifest_path)
        data["artifacts"][0]["sha256"] = "0" * 64
        try:
            validate_manifest(data, files, synthetic_hashes)
        except EvidenceError as exc:
            assert "wrong manifest standard_ctm SHA256" in str(exc)
        else:
            raise AssertionError("artifact mismatch self-test did not fail")

        data = read_manifest(manifest_path)
        data["binary"]["sha256"] = local_hashes["binary"]
        try:
            validate_manifest(data, files, {**synthetic_hashes, "binary": FROZEN_BINARY_SHA256})
        except EvidenceError as exc:
            assert "wrong local binary SHA256" in str(exc)
        else:
            raise AssertionError("pinned executable SHA self-test did not fail")

        # The full confirmation rejects a truncated action receipt, while the
        # explicit observer early-return is accepted when its counter reconciles.
        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        action_path = standard / "mcts.csv.actions.jsonl"
        action_rows = action_path.read_text(encoding="utf-8").splitlines()
        action_path.write_text("\n".join(action_rows[1:]) + "\n", encoding="utf-8")
        data = read_manifest(manifest_path)
        c_arm = manifest_arm(data, "C")
        try:
            validate_arm(standard, "C", list(range(SEED_START, SEED_START + SEED_COUNT)),
                         {**data["common_env"], **c_arm["env"]}, sha256(files["binary"]), c_arm["results"])
        except EvidenceError as exc:
            assert "action receipts are incomplete" in str(exc)
        else:
            raise AssertionError("truncated action-trace self-test did not fail")

        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        action_path = standard / "mcts.csv.actions.jsonl"
        action_rows = [json.loads(line) for line in action_path.read_text(encoding="utf-8").splitlines()]
        action_rows = [row for row in action_rows if int(row["seed"]) != SEED_START]
        action_path.write_text("".join(json.dumps(row) + "\n" for row in action_rows), encoding="utf-8")
        trace_path = standard / "mcts.csv"
        with trace_path.open(newline="", encoding="utf-8") as stream:
            trace_reader = csv.DictReader(stream)
            trace_fields = trace_reader.fieldnames
            trace_rows = list(trace_reader)
        assert trace_fields is not None
        trace_rows[0]["mctsOwned"] = "0"
        trace_rows[0]["mctsFallback"] = "1"
        trace_rows[0]["simulations"] = "0"
        with trace_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=trace_fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(trace_rows)
        support_path = standard / "mcts.csv.support.jsonl"
        support_rows = [json.loads(line) for line in support_path.read_text(encoding="utf-8").splitlines()]
        support_rows[0]["reasons"] = {"semantic_observer_active": 1}
        support_path.write_text("".join(json.dumps(row) + "\n" for row in support_rows), encoding="utf-8")
        data = read_manifest(manifest_path)
        c_arm = manifest_arm(data, "C")
        validate_arm(standard, "C", list(range(SEED_START, SEED_START + SEED_COUNT)),
                     {**data["common_env"], **c_arm["env"]}, sha256(files["binary"]), c_arm["results"])

        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        action_path = standard / "mcts.csv.actions.jsonl"
        action_rows = [json.loads(line) for line in action_path.read_text(encoding="utf-8").splitlines()]
        action_rows[0]["executed"] = False
        action_rows[0]["reason"] = "semantic_execution:synthetic_abort"
        action_path.write_text("".join(json.dumps(row) + "\n" for row in action_rows), encoding="utf-8")
        trace_path = standard / "mcts.csv"
        with trace_path.open(newline="", encoding="utf-8") as stream:
            trace_reader = csv.DictReader(stream)
            trace_fields = trace_reader.fieldnames
            trace_rows = list(trace_reader)
        assert trace_fields is not None
        trace_rows[0]["mctsOwned"] = "0"
        trace_rows[0]["mctsFallback"] = "1"
        with trace_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=trace_fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(trace_rows)
        support_path = standard / "mcts.csv.support.jsonl"
        support_rows = [json.loads(line) for line in support_path.read_text(encoding="utf-8").splitlines()]
        support_rows[0]["reasons"] = {"semantic_execution:synthetic_abort": 1}
        support_path.write_text("".join(json.dumps(row) + "\n" for row in support_rows), encoding="utf-8")
        data = read_manifest(manifest_path)
        c_arm = manifest_arm(data, "C")
        validate_arm(standard, "C", list(range(SEED_START, SEED_START + SEED_COUNT)),
                     {**data["common_env"], **c_arm["env"]}, sha256(files["binary"]), c_arm["results"])

        standard, hybrid, _, _ = synthetic_fixture(root, "pass", synthetic_hashes)
        trace_path = standard / "mcts.csv"
        with trace_path.open(newline="", encoding="utf-8") as stream:
            trace_reader = csv.DictReader(stream)
            trace_fields = trace_reader.fieldnames
            trace_rows = list(trace_reader)
        assert trace_fields is not None
        trace_rows[0]["simulations"] = str(OOC_SIMULATIONS + 1)
        with trace_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=trace_fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(trace_rows)
        data = read_manifest(manifest_path)
        c_arm = manifest_arm(data, "C")
        try:
            validate_arm(standard, "C", list(range(SEED_START, SEED_START + SEED_COUNT)),
                         {**data["common_env"], **c_arm["env"]}, sha256(files["binary"]), c_arm["results"])
        except EvidenceError as exc:
            assert "simulations exceed" in str(exc)
        else:
            raise AssertionError("MCTS simulation-budget self-test did not fail")
    print("deepset hybrid confirmation analyzer self-test PASS (quality and provenance cases)")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--standard", type=Path)
    result.add_argument("--hybrid", type=Path)
    result.add_argument("--manifest", type=Path)
    result.add_argument("--binary", type=Path)
    result.add_argument("--standard-ctm", type=Path)
    result.add_argument("--fast-ctm", type=Path)
    result.add_argument("--v4-policy", type=Path)
    result.add_argument("--floor-model", type=Path)
    result.add_argument("--win-model", type=Path)
    result.add_argument("--summary", type=Path)
    result.add_argument("--per-seed", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    required = ("standard", "hybrid", "manifest", "binary", "standard_ctm", "fast_ctm",
                "v4_policy", "floor_model", "win_model", "summary", "per_seed")
    missing = [key for key in required if getattr(args, key) is None]
    if missing:
        raise SystemExit("missing required arguments: " + ", ".join(missing))
    files = {
        "binary": args.binary,
        "standard_ctm": args.standard_ctm,
        "fast_ctm": args.fast_ctm,
        "v4_policy": args.v4_policy,
        "floor_model": args.floor_model,
        "win_model": args.win_model,
    }
    try:
        summary = run_analysis(args.standard, args.hybrid, args.manifest, files,
                               args.summary, args.per_seed)
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"confirmation analysis FAIL: {exc}") from exc
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
