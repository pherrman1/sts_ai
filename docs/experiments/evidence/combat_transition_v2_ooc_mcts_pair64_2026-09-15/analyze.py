#!/usr/bin/env python3
import csv
import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_results(name):
    with (ROOT / f"{name}.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    seeds = [int(row["seed"]) for row in rows]
    assert len(rows) == 64
    assert len(seeds) == len(set(seeds))
    return {seed: row for seed, row in zip(seeds, rows)}


def percentile(values, probability):
    return values[int(probability * (len(values) - 1))]


old = read_results("old_v2")
new = read_results("new_v2")
expected = set(range(12002032, 12002096))
assert set(old) == set(new) == expected

win_deltas = [int(new[s]["won"]) - int(old[s]["won"]) for s in sorted(expected)]
rng = random.Random(20260915)
bootstrap = sorted(
    sum(win_deltas[rng.randrange(64)] for _ in range(64)) / 64
    for _ in range(200_000)
)

summary = {
    "pairedSeeds": len(expected),
    "seedFirst": min(expected),
    "seedLast": max(expected),
    "bootstrap": {
        "replicates": 200_000,
        "seed": 20260915,
        "method": "paired empirical resampling with replacement",
        "newMinusOldWinRateDelta": statistics.mean(win_deltas),
        "percentile95": [percentile(bootstrap, 0.025), percentile(bootstrap, 0.975)],
    },
    "arms": {},
    "pairing": {
        "bothWin": sum(int(old[s]["won"]) and int(new[s]["won"]) for s in expected),
        "bothLose": sum(not int(old[s]["won"]) and not int(new[s]["won"]) for s in expected),
        "oldOnly": sum(int(old[s]["won"]) and not int(new[s]["won"]) for s in expected),
        "newOnly": sum(not int(old[s]["won"]) and int(new[s]["won"]) for s in expected),
    },
}

for name, rows in (("old_v2", old), ("new_v2", new)):
    summary["arms"][name] = {
        "wins": sum(int(row["won"]) for row in rows.values()),
        "winRate": statistics.mean(int(row["won"]) for row in rows.values()),
        "meanFloor": statistics.mean(float(row["floor"]) for row in rows.values()),
        "meanHpEnd": statistics.mean(float(row["hpEnd"]) for row in rows.values()),
        "meanSeconds": statistics.mean(float(row["sec"]) for row in rows.values()),
    }
    with (ROOT / f"{name}.mcts.csv").open() as handle:
        telemetry = list(csv.DictReader(handle))
    support = [json.loads(line) for line in (ROOT / f"{name}.mcts.csv.support.jsonl").read_text().splitlines()]
    assert len(telemetry) == len(support) == 64
    assert {int(row["seed"]) for row in telemetry} == expected
    assert {int(row["seed"]) for row in support} == expected
    reasons = sorted({reason for row in support for reason in row["reasons"]})
    summary["arms"][name]["telemetry"] = {
        "rows": len(telemetry),
        "oocDecisions": sum(int(row["oocDecisions"]) for row in telemetry),
        "mctsOwned": sum(int(row["mctsOwned"]) for row in telemetry),
        "mctsFallback": sum(int(row["mctsFallback"]) for row in telemetry),
        "unsupportedCombats": sum(int(row["unsupportedCombats"]) for row in telemetry),
        "mctsSupportAborts": sum(int(row["mctsSupportAborts"]) for row in telemetry),
        "discardedSimulations": sum(int(row["discardedSimulations"]) for row in telemetry),
        "continuationLimitAborts": sum(int(row["continuationLimitAborts"]) for row in telemetry),
        "supportReasons": {reason: sum(row["reasons"].get(reason, 0) for row in support) for reason in reasons},
    }

(ROOT / "analysis.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

excluded = {"manifest.sha256"}
entries = []
for path in sorted(ROOT.iterdir()):
    if path.is_file() and path.name not in excluded:
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
(ROOT / "manifest.sha256").write_text("\n".join(entries) + "\n")
print(json.dumps(summary, indent=2, sort_keys=True))
