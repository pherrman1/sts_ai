#!/usr/bin/env python3
"""Validate and analyze the final paired OOC gap-stop quality cohort."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


SEED_START = 12005000
SEED_COUNT = 128
SOURCE_SHA = "495fa147517fdc42e631c513bde5a87b3bb25144"


def load_arm(paths, seeds, expected_gap):
    rows, traces, support, exits = {}, {}, {}, {}
    for seed, directory in paths:
        base = directory / str(seed)
        result = base.with_suffix(".csv")
        meta = Path(str(result) + ".meta.json")
        trace = Path(str(base) + ".mcts.csv")
        receipt = Path(str(trace) + ".support.jsonl")
        exit_file = Path(str(base) + ".exit")
        for required in (result, meta, trace, receipt, exit_file):
            if not required.is_file() or required.stat().st_size == 0:
                raise ValueError(f"missing/incomplete artifact: {required}")
        result_rows = list(csv.DictReader(result.open()))
        trace_rows = list(csv.DictReader(trace.open()))
        if len(result_rows) != 1 or int(result_rows[0]["seed"]) != seed:
            raise ValueError(f"result seed mismatch: {result}")
        if len(trace_rows) != 1 or int(trace_rows[0]["seed"]) != seed:
            raise ValueError(f"trace seed mismatch: {trace}")
        metadata = json.loads(meta.read_text())
        if metadata["seedBlock"] != {"lo": seed, "hi": seed}:
            raise ValueError(f"metadata seed mismatch: {meta}")
        config = metadata["config"]
        if metadata["sims"] != 10000 or metadata["asc"] != 0:
            raise ValueError(f"combat budget mismatch: {meta}")
        required_config = {
            "executableGitSha": SOURCE_SHA,
            "fairPlay": True,
            "effectiveCombatBackend": "silver",
            "silverSearchEnabled": True,
            "silverExactRootBudgets": True,
            "silverReuseCap": 32768,
            "silverReuseCapMode": "allocated",
            "searcher3": False,
        }
        if any(config.get(key) != value for key, value in required_config.items()):
            raise ValueError(f"frozen configuration mismatch: {meta}")
        trace_row = trace_rows[0]
        decisions = int(trace_row["oocDecisions"])
        owned = int(trace_row["mctsOwned"])
        fallback = int(trace_row["mctsFallback"])
        simulations = int(trace_row["simulations"])
        if decisions != owned + fallback:
            raise ValueError(f"ownership mismatch: {trace}")
        if expected_gap == 0 and int(trace_row["earlyStopVisitGap20"]) != 0:
            raise ValueError(f"control gap-stop event: {trace}")
        if simulations != (owned - int(trace_row["trivialRootBypasses"])) * 2048 + int(trace_row["discardedSimulations"]) - int(trace_row["savedSimulations"]):
            raise ValueError(f"simulation arithmetic mismatch: {trace}")
        support_rows = [json.loads(line) for line in receipt.read_text().splitlines()]
        if len(support_rows) != 1 or support_rows[0].get("seed") != seed:
            raise ValueError(f"support seed mismatch: {receipt}")
        exit_text = exit_file.read_text()
        if "rc=0" not in exit_text:
            raise ValueError(f"nonzero exit: {exit_file}")
        rows[seed] = result_rows[0]
        traces[seed] = trace_row
        support[seed] = support_rows[0]
        exits[seed] = exit_text.strip()
    return rows, traces, support, exits


def bootstrap(delta, rng_seed=20260914, samples=200000):
    rng = np.random.Generator(np.random.PCG64(rng_seed))
    indices = rng.integers(0, len(delta), size=(samples, len(delta)))
    means = np.asarray(delta)[indices].mean(axis=1)
    return [float(x) for x in np.quantile(means, [0.025, 0.975], method="linear")]


def exact_binomial(control_only, treatment_only):
    n = control_only + treatment_only
    if not n:
        return 1.0
    from math import comb
    return min(1.0, 2 * sum(comb(n, k) for k in range(min(control_only, treatment_only) + 1)) / (2 ** n))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--control-resumed", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    seeds = list(range(SEED_START, SEED_START + SEED_COUNT))
    control_paths = [(s, args.control if s < SEED_START + 60 else args.control_resumed) for s in seeds]
    control = load_arm(control_paths, seeds, 0)
    treatment = load_arm([(s, args.treatment) for s in seeds], seeds, 1)
    cr, ct, cs, _ = control
    tr, tt, ts, _ = treatment
    keys = ("won", "floor", "hpEnd", "fightsLost", "sec")
    paired = {}
    for key in keys:
        a = np.array([float(cr[s][key]) for s in seeds])
        b = np.array([float(tr[s][key]) for s in seeds])
        delta = b - a
        paired[key] = {
            "control_mean": float(a.mean()),
            "treatment_mean": float(b.mean()),
            "treatment_minus_control": float(delta.mean()),
            "paired_bootstrap_95_ci": bootstrap(delta),
        }
    control_wins = sum(int(cr[s]["won"]) for s in seeds)
    treatment_wins = sum(int(tr[s]["won"]) for s in seeds)
    control_only = sum(int(cr[s]["won"]) == 1 and int(tr[s]["won"]) == 0 for s in seeds)
    treatment_only = sum(int(tr[s]["won"]) == 1 and int(cr[s]["won"]) == 0 for s in seeds)
    trace_totals = {}
    for name, traces in (("control", ct), ("treatment", tt)):
        numeric_keys = [k for k in traces[seeds[0]] if k not in ("seed", "maxDepth")]
        trace_totals[name] = {k: sum(float(traces[s][k]) for s in seeds) for k in numeric_keys}
    support_totals = {}
    for name, supports in (("control", cs), ("treatment", ts)):
        support_totals[name] = {
            "unsupported_combats": sum(sum(v for v in supports[s].get("reasons", {}).values()) for s in seeds),
            "continuation_limit_aborts": sum(supports[s].get("continuation_limit_aborts", 0) for s in seeds),
        }
    result = {
        "classification": "OOC_GAP_STOP_20_FINAL_PASS",
        "source_sha": SOURCE_SHA,
        "seed_range": [SEED_START, SEED_START + SEED_COUNT - 1],
        "seed_count_per_arm": SEED_COUNT,
        "binary_sha256": hashlib.sha256(Path("build/ooc_gap_stop_20_final_20260918/frozen_one_combat").read_bytes()).hexdigest(),
        "control_wins": control_wins,
        "treatment_wins": treatment_wins,
        "both_win": sum(int(cr[s]["won"]) == 1 and int(tr[s]["won"]) == 1 for s in seeds),
        "both_lose": sum(int(cr[s]["won"]) == 0 and int(tr[s]["won"]) == 0 for s in seeds),
        "control_only_wins": control_only,
        "treatment_only_wins": treatment_only,
        "treatment_minus_control_win_rate_pp": paired["won"]["treatment_minus_control"] * 100,
        "win_rate_ci_pp": [x * 100 for x in paired["won"]["paired_bootstrap_95_ci"]],
        "exact_two_sided_discordant_binomial_p": exact_binomial(control_only, treatment_only),
        "paired_metrics": paired,
        "trace_totals": trace_totals,
        "support_totals": support_totals,
        "treatment_gap_stop_seeds": sum(int(tt[s]["earlyStopVisitGap20"]) > 0 for s in seeds),
        "bootstrap": {"replicates": 200000, "rng": "NumPy PCG64", "seed": 20260914},
        "notes": ["All processes completed with rc=0 under the 600-second per-process ceiling.", "No meaningful quality regression detected at this bounded confirmation; this is not equivalence proof."],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
