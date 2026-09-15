#!/usr/bin/env python3
import csv
import gzip
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("flat10k", "ctm_adaptive10k")


def rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def timing(label):
    text = (HERE / f"{label}-time.txt").read_text()
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1))
    return {"peakRssKiB": rss}


def arm(label):
    result = rows(HERE / f"{label}.csv")
    diag = rows(HERE / f"{label}-decisions.csv.gz")
    seeds = [int(row["seed"]) for row in result]
    assert len(result) == 16 and sorted(seeds) == list(range(48, 64)) and len(set(seeds)) == 16
    fights = {}
    for row in diag:
        key = (int(row["run_seed"]), int(row["floor"]), int(row["encounter"]))
        budget = int(row["configured_simulations"])
        assert key not in fights or fights[key] == budget
        fights[key] = budget
        assert row["configured_cap_mode"] == "allocated" and int(row["configured_cap"]) == 131072
    budgets = list(fights.values())
    cap_fallbacks = sum(row["fallback_reason"] == "allocated_cap" for row in diag)
    with gzip.open(HERE / f"{label}.log.gz", "rt") as stream:
        log = stream.read()
    assert ("[CTM adaptive sim budget ON:" in log) == (label == "ctm_adaptive10k")
    telemetry = [line for line in log.splitlines() if line.startswith("[silver-combat]")]
    assert len(telemetry) == len(fights)
    for line in telemetry:
        fields = dict(re.findall(r"(\w+)=([^ ]+)", line))
        for key in ("conversion_failures", "semantic_resolution_failures", "transaction_failures",
                    "knowledge_failures"):
            assert int(fields[key]) == 0
    return {
        "seeds": sorted(seeds),
        "wins": sum(int(row["won"]) for row in result),
        "meanFloor": statistics.mean(float(row["floor"]) for row in result),
        "meanFinalHp": statistics.mean(float(row["hpEnd"]) for row in result),
        "meanSecPerRun": statistics.mean(float(row["sec"]) for row in result),
        "decisionRows": len(diag),
        "telemetryRows": len(telemetry),
        "fights": len(fights),
        "simulationsAdded": sum(int(row["simulations_added"]) for row in diag),
        "budget": {
            "minimum": min(budgets), "median": statistics.median(budgets),
            "mean": statistics.mean(budgets), "maximum": max(budgets),
            "below10k": sum(value < 10000 for value in budgets),
            "equal10k": sum(value == 10000 for value in budgets),
            "above10k": sum(value > 10000 for value in budgets),
        },
        "capFallbacks": cap_fallbacks,
        "maxAllocatedAfterSearch": max(int(row["allocated_nodes_after_search"]) for row in diag),
        **timing(label),
        "bySeed": {int(row["seed"]): int(row["won"]) for row in result},
    }


summary = {label: arm(label) for label in ARMS}
a, b = (summary[label]["bySeed"] for label in ARMS)
a_only = sum(a[seed] > b[seed] for seed in a)
b_only = sum(b[seed] > a[seed] for seed in a)
discordant = a_only + b_only
tail = sum(math.comb(discordant, k) for k in range(min(a_only, b_only) + 1)) / 2**discordant
summary["paired"] = {
    "flatOnly": a_only, "ctmOnly": b_only,
    "exactTwoSidedP": min(1.0, 2 * tail),
    "winDeltaPercentagePoints": 100 * (summary["ctm_adaptive10k"]["wins"] - summary["flat10k"]["wins"]) / 16,
}
for value in summary.values():
    if isinstance(value, dict):
        value.pop("bySeed", None)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

manifest = {}
for path in sorted(HERE.iterdir()):
    if path.is_file() and path.name not in {"manifest.sha256", "summary.json"}:
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
(HERE / "manifest.sha256").write_text("".join(f"{digest}  {name}\n" for name, digest in manifest.items()))
print(json.dumps(summary, indent=2, sort_keys=True))
