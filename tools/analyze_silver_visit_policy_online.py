#!/usr/bin/env python3
"""Fail-closed paired analysis for frozen Silver visit-policy screens."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np


EXPECTED_HEAD = "0a8ec2087d5af7e9fec53323e84e5dc36a003f44"
EXPECTED_SOURCE = "a9f4ba81b200ec7ac7510970e7279ba7b46b1a0f53af521e5bebb98eba3986cf"
EXPECTED_MODEL_SUFFIX = "/models/silver_rank4_visit_policy_runtime_v1.bin"
FAILURE_KEYS = (
    "visit_policy_feature_failures",
    "visit_policy_semantic_failures",
    "visit_policy_nonfinite_failures",
    "visit_policy_normalization_failures",
    "conversion_failures",
    "semantic_resolution_failures",
    "transaction_failures",
    "knowledge_failures",
)
SUM_KEYS = (
    "simulations",
    "visit_policy_scored_roots",
    "visit_policy_scored_actions",
    "visit_policy_fresh_roots",
    "visit_policy_reused_roots",
    "visit_policy_inference_micros",
) + FAILURE_KEYS
FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=(-?[0-9]+)")


def percentile_interval(values: np.ndarray) -> list[float]:
    return [float(x) for x in np.percentile(values, [2.5, 97.5])]


def load_arm(results: Path, logs: Path, mode: str, seeds: list[int]) -> list[dict]:
    rows = []
    for seed in seeds:
        csv_path = results / f"{mode}_{seed}.csv"
        meta_path = results / f"{mode}_{seed}.csv.meta.json"
        log_path = logs / f"{mode}_{seed}.log"
        time_path = logs / f"{mode}_{seed}.time"
        for path in (csv_path, meta_path, log_path, time_path):
            if not path.is_file():
                raise ValueError(f"missing required file: {path}")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            parsed = list(csv.DictReader(handle))
        if len(parsed) != 1 or int(parsed[0]["seed"]) != seed:
            raise ValueError(f"expected exactly one row for {mode}/{seed}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        cfg = meta["config"]
        expected = {
            "nSeeds": 1,
            "asc": 0,
            "sims": 1000,
            "threads": 1,
        }
        for key, value in expected.items():
            if meta.get(key) != value:
                raise ValueError(f"{mode}/{seed}: {key}={meta.get(key)!r}, expected {value!r}")
        cfg_expected = {
            "fairPlay": True,
            "effectiveCombatBackend": "silver",
            "silverSearchEnabled": True,
            "silverReuseCapMode": "allocated",
            "silverReuseCap": 32768,
            "silverExactRootBudgets": True,
            "executableGitSha": EXPECTED_HEAD,
            "silverVisitPolicyMode": mode,
        }
        for key, value in cfg_expected.items():
            if cfg.get(key) != value:
                raise ValueError(f"{mode}/{seed}: config {key}={cfg.get(key)!r}, expected {value!r}")
        if meta.get("seedBlock") != {"lo": seed, "hi": seed}:
            raise ValueError(f"{mode}/{seed}: wrong sidecar seed block")
        if mode != "off":
            if cfg.get("silverVisitPolicySourceNpzSha256") != EXPECTED_SOURCE:
                raise ValueError(f"{mode}/{seed}: source NPZ provenance mismatch")
            if not cfg.get("silverVisitPolicyRuntimeModelPath", "").endswith(EXPECTED_MODEL_SUFFIX):
                raise ValueError(f"{mode}/{seed}: runtime model path mismatch")
        text = log_path.read_text(encoding="utf-8", errors="strict")
        load_marker = f"[Silver visit policy loaded: mode={mode} source_npz_sha256={EXPECTED_SOURCE}]"
        if mode != "off" and text.count(load_marker) != 1:
            raise ValueError(f"{mode}/{seed}: missing or duplicate model-load marker")
        if mode == "off" and "Silver visit policy loaded:" in text:
            raise ValueError(f"{mode}/{seed}: treatment model unexpectedly loaded")
        telemetry = {key: 0 for key in SUM_KEYS}
        telemetry_lines = 0
        for line in text.splitlines():
            if not line.startswith("[silver-combat]"):
                continue
            telemetry_lines += 1
            fields = {key: int(value) for key, value in FIELD_RE.findall(line)}
            for key in SUM_KEYS:
                if key not in fields:
                    raise ValueError(f"{mode}/{seed}: telemetry missing {key}")
                telemetry[key] += fields[key]
        if telemetry_lines == 0:
            raise ValueError(f"{mode}/{seed}: no Silver telemetry")
        if any(telemetry[key] != 0 for key in FAILURE_KEYS):
            raise ValueError(f"{mode}/{seed}: nonzero correctness failure: {telemetry}")
        if mode == "off" and any(telemetry[key] != 0 for key in (
            "visit_policy_scored_roots", "visit_policy_scored_actions",
            "visit_policy_fresh_roots", "visit_policy_reused_roots",
            "visit_policy_inference_micros",
        )):
            raise ValueError(f"{mode}/{seed}: off arm unexpectedly scored visit policy")
        if mode != "off" and telemetry["visit_policy_scored_roots"] <= 0:
            raise ValueError(f"{mode}/{seed}: treatment scored no roots")
        timing = {}
        for line in time_path.read_text(encoding="utf-8").splitlines():
            key, value = line.split("=", 1)
            timing[key] = int(value)
        if timing.get("exit_code") != 0:
            raise ValueError(f"{mode}/{seed}: nonzero wrapper exit")
        raw = parsed[0]
        rows.append({
            "seed": seed,
            "won": int(raw["won"]),
            "floor": int(raw["floor"]),
            "ending_hp": int(raw["hpEnd"]),
            "cpu_seconds": float(raw["sec"]),
            "wall_seconds": timing["wall_seconds"],
            "telemetry_lines": telemetry_lines,
            **telemetry,
        })
    return rows


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    total_cpu = sum(row["cpu_seconds"] for row in rows)
    total_sims = sum(row["simulations"] for row in rows)
    totals = {key: sum(row[key] for row in rows) for key in SUM_KEYS}
    return {
        "n": n,
        "wins": sum(row["won"] for row in rows),
        "win_rate": sum(row["won"] for row in rows) / n,
        "mean_floor": float(np.mean([row["floor"] for row in rows])),
        "median_floor": float(np.median([row["floor"] for row in rows])),
        "mean_ending_hp": float(np.mean([row["ending_hp"] for row in rows])),
        "mean_cpu_seconds": total_cpu / n,
        "total_cpu_seconds": total_cpu,
        "total_silver_simulations": total_sims,
        "cpu_seconds_per_1000_simulations": total_cpu / total_sims * 1000,
        "policy_inference_fraction_of_cpu": totals["visit_policy_inference_micros"] / 1e6 / total_cpu,
        "telemetry": totals,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--treatment", choices=("grouped", "rank4"), default="grouped")
    parser.add_argument("--seed-first", type=int, default=976032)
    parser.add_argument("--seed-count", type=int, default=32)
    args = parser.parse_args()
    seeds = list(range(args.seed_first, args.seed_first + args.seed_count))
    off = load_arm(args.results, args.logs, "off", seeds)
    treatment = load_arm(args.results, args.logs, args.treatment, seeds)
    if len({row["seed"] for row in off + treatment}) != args.seed_count:
        raise ValueError("seed set is incomplete or unexpected")
    paired = []
    for a, b in zip(off, treatment, strict=True):
        if a["seed"] != b["seed"]:
            raise ValueError("arm pairing mismatch")
        paired.append({
            "seed": a["seed"],
            "A_off": a,
            f"B_{args.treatment}": b,
            "B_minus_A": {
                "won": b["won"] - a["won"],
                "floor": b["floor"] - a["floor"],
                "ending_hp": b["ending_hp"] - a["ending_hp"],
                "cpu_seconds": b["cpu_seconds"] - a["cpu_seconds"],
            },
        })
    a_agg, b_agg = aggregate(off), aggregate(treatment)
    diffs = np.array([[p["B_minus_A"][key] for key in ("won", "floor", "ending_hp", "cpu_seconds")] for p in paired])
    rng = np.random.default_rng(20260830)
    indices = rng.integers(0, len(seeds), size=(10000, len(seeds)))
    samples = diffs[indices].mean(axis=1)
    names = ("win_rate", "mean_floor", "mean_ending_hp", "mean_cpu_seconds")
    bootstrap = {name: {"point_estimate": float(diffs[:, i].mean()), "ci95": percentile_interval(samples[:, i])} for i, name in enumerate(names)}
    normalized_ratio = (
        b_agg["total_cpu_seconds"] / b_agg["total_silver_simulations"]
    ) / (
        a_agg["total_cpu_seconds"] / a_agg["total_silver_simulations"]
    )
    net_wins = b_agg["wins"] - a_agg["wins"]
    all_zero = all(a_agg["telemetry"][key] == 0 and b_agg["telemetry"][key] == 0 for key in FAILURE_KEYS)
    if net_wins >= 3 and bootstrap["mean_floor"]["point_estimate"] >= 0 and normalized_ratio <= 1.50 and all_zero:
        decision = f"ADVANCE_{args.treatment.upper()}_VISIT_POLICY"
    elif net_wins <= -3:
        decision = f"{args.treatment.upper()}_VISIT_POLICY_ONLINE_SCREEN_NEGATIVE"
    else:
        decision = f"{args.treatment.upper()}_VISIT_POLICY_ONLINE_SCREEN_INCONCLUSIVE"
    report = {
        "schema": "silver_visit_policy_online_paired_analysis_v1",
        "valid": True,
        "provenance": {
            "implementation_sha": EXPECTED_HEAD,
            "source_npz_sha256": EXPECTED_SOURCE,
            "seed_block": [seeds[0], seeds[-1]],
            "treatment": args.treatment,
            "bootstrap_seed": 20260830,
            "bootstrap_resamples": 10000,
        },
        "A_off": a_agg,
        f"B_{args.treatment}": b_agg,
        "B_minus_A": {
            "net_wins": net_wins,
            "normalized_cpu_ratio": normalized_ratio,
            "bootstrap": bootstrap,
        },
        "correctness_counters_all_zero": all_zero,
        "decision": decision,
        "paired_rows": paired,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("A_off", f"B_{args.treatment}", "B_minus_A", "decision")}, indent=2))


if __name__ == "__main__":
    main()
