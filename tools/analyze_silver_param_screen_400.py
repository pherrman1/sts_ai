#!/usr/bin/env python3
"""Pre-registered analysis for the #400 Stage 1 Silver search-parameter screen.

Input: one or more `silverparams400gen` output prefixes (shards). Every real
fight is replayed under each arm from the same pre-battle state; the control
arm reproduces the source fight. The question is whether a per-context choice
of search constants beats the single best global choice on held-out fights.

Decision rule (frozen before any cohort ran):
- Q = signedOutcome per fight (win: terminal HP / max HP; loss: -enemy HP left).
- Source seeds split by sha256("silver-param-400-v1:{seed}") into DISCOVERY
  (< 0.5) and CONFIRMATION halves.
- Context cell = room class x act. On DISCOVERY pick global* (best pooled mean
  Q) and, per cell with at least MIN_CELL_STATES states, cell* (best mean Q in
  that cell); smaller cells use global*.
- On CONFIRMATION, D = mean over fights of Q[cell*] - Q[global*], 95%
  source-seed-clustered bootstrap CI (2,000 replicates, seed 0).
- ADAPTIVE_SEARCH_PARAMS_SIGNAL if D >= MATERIAL_D, CI lower > 0 and the
  per-cell policy's CPU is at most CPU_RATIO_LIMIT x global*'s;
  ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED if every cell picks global* or the CI
  upper bound is below MATERIAL_D; otherwise INCONCLUSIVE.
- Reported separately: global* vs control on CONFIRMATION (a global retune is a
  different question and not this issue's verdict).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


class AnalysisError(ValueError):
    pass


ARMS = ["control", "c12", "c50", "wa040", "wa065"]
SPLIT_DOMAIN = "silver-param-400-v1"
MIN_CELL_STATES = 20
MATERIAL_D = 0.01
CPU_RATIO_LIMIT = 1.10
REPLICATES = 2000
BOOTSTRAP_SEED = 0
STATES_HEADER = ["stateId", "sourceSeed", "fightIdx", "act", "floor", "roomClass", "encounter",
                 "preHp", "preMaxHp", "prePotions", "deckSize", "relicCount", "sourceWon",
                 "sourceSignedOutcome", "sourceTerminalHp", "sourcePostAfterBattleHp",
                 "sourceFirstActionBits", "trajectoryValid"]
ARMS_HEADER = ["stateId", "sourceSeed", "fightIdx", "arm", "exploration", "explorationChance",
               "chanceWideningC", "chanceWideningAlpha", "endTurnWideningC", "endTurnWideningAlpha",
               "outcome", "won", "signedOutcome", "terminalHp", "postAfterBattleHp", "potionsAfter",
               "firstActionBits", "cpuSeconds", "simulations", "decisions", "valid",
               "controlReplayMatch", "quarantineReason"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_of(seed: int) -> str:
    value = int(hashlib.sha256(f"{SPLIT_DOMAIN}:{seed}".encode()).hexdigest()[:8], 16) / 2**32
    return "discovery" if value < 0.5 else "confirmation"


def _read_csv(path: Path, header: list[str]) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != header:
            raise AnalysisError(f"{path}: unexpected header {reader.fieldnames}")
        return list(reader)


def load(prefixes: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one record per fight with every arm valid, plus integrity counts."""
    identities: set[tuple[str, str, str]] = set()
    seen_seeds: set[int] = set()
    fights: list[dict[str, Any]] = []
    counts = defaultdict(int)
    shards = []
    for prefix in prefixes:
        manifest_path = Path(prefix + ".manifest.json")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("schemaVersion") != "silver_param_screen_400_stage1_v1":
            raise AnalysisError(f"{manifest_path}: wrong schema")
        if sorted(manifest["arms"]) != sorted(ARMS):
            raise AnalysisError(f"{manifest_path}: arm set differs from the frozen grid")
        states_path, arms_path = Path(prefix + ".states.csv"), Path(prefix + ".arms.csv")
        if _sha256(states_path) != manifest["outputs"]["statesSha256"] \
                or _sha256(arms_path) != manifest["outputs"]["armsSha256"]:
            raise AnalysisError(f"{prefix}: output hash mismatch")
        identities.add((manifest["producerGitSha"], manifest["producerExecutableSha256"],
                        manifest["teacherId"]))
        start, count = manifest["seedSpec"]["start"], manifest["seedSpec"]["count"]
        seeds = set(range(start, start + count))
        if seeds & seen_seeds:
            raise AnalysisError(f"{prefix}: overlapping source seeds")
        seen_seeds |= seeds
        shards.append({"prefix": prefix, "start": start, "count": count,
                       "integrity": manifest["integrity"]})
        rows_by_state: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
        for row in _read_csv(arms_path, ARMS_HEADER):
            if row["arm"] in rows_by_state[row["stateId"]]:
                raise AnalysisError(f"{prefix}: duplicate arm row {row['stateId']}/{row['arm']}")
            rows_by_state[row["stateId"]][row["arm"]] = row
        for state in _read_csv(states_path, STATES_HEADER):
            counts["states"] += 1
            arms = rows_by_state.get(state["stateId"], {})
            if sorted(arms) != sorted(ARMS):
                raise AnalysisError(f"{prefix}: state {state['stateId']} lacks arm rows")
            if not all(arms[a]["valid"] == "1" for a in ARMS):
                counts["excluded_states"] += 1
                counts["excluded_" + (arms["control"]["quarantineReason"] or "arm_invalid")] += 1
                continue
            seed = int(state["sourceSeed"])
            fights.append({
                "stateId": state["stateId"], "sourceSeed": seed, "split": split_of(seed),
                "cell": f"{state['roomClass']}-A{state['act']}", "roomClass": state["roomClass"],
                "act": int(state["act"]), "encounter": state["encounter"],
                "q": {a: float(arms[a]["signedOutcome"]) for a in ARMS},
                "won": {a: int(arms[a]["won"]) for a in ARMS},
                "potionsUsed": {a: int(state["prePotions"]) - int(arms[a]["potionsAfter"]) for a in ARMS},
                "cpu": {a: float(arms[a]["cpuSeconds"]) for a in ARMS},
            })
    if len(identities) != 1:
        raise AnalysisError(f"shards disagree on producer/teacher identity: {sorted(identities)}")
    counts["valid_states"] = len(fights)
    return fights, {"counts": dict(counts), "shards": shards,
                    "identity": dict(zip(["producerGitSha", "producerExecutableSha256", "teacherId"],
                                         next(iter(identities))))}


def _clustered_ci(fights: list[dict[str, Any]], value) -> tuple[float, float, float]:
    clusters: dict[int, list[float]] = defaultdict(list)
    for fight in fights:
        clusters[fight["sourceSeed"]].append(value(fight))
    if not clusters:
        return math.nan, math.nan, math.nan
    seeds = sorted(clusters)
    sums = {s: (sum(clusters[s]), len(clusters[s])) for s in seeds}
    total = sum(v for v, _ in sums.values()) / sum(n for _, n in sums.values())
    rng = random.Random(BOOTSTRAP_SEED)
    stats = []
    for _ in range(REPLICATES):
        draw = [sums[rng.choice(seeds)] for _ in seeds]
        stats.append(sum(v for v, _ in draw) / sum(n for _, n in draw))
    stats.sort()
    return total, stats[int(0.025 * (REPLICATES - 1))], stats[int(math.ceil(0.975 * (REPLICATES - 1)))]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def _best_arm(fights: list[dict[str, Any]]) -> str:
    # Ties go to the earlier arm in ARMS (control first).
    return max(ARMS, key=lambda a: (_mean([f["q"][a] for f in fights]), -ARMS.index(a)))


def analyze(fights: list[dict[str, Any]]) -> dict[str, Any]:
    discovery = [f for f in fights if f["split"] == "discovery"]
    confirmation = [f for f in fights if f["split"] == "confirmation"]
    if not discovery or not confirmation:
        raise AnalysisError("both DISCOVERY and CONFIRMATION fights are required")
    cells = sorted({f["cell"] for f in fights})
    global_best = _best_arm(discovery)
    cell_best = {}
    for cell in cells:
        members = [f for f in discovery if f["cell"] == cell]
        cell_best[cell] = _best_arm(members) if len(members) >= MIN_CELL_STATES else global_best
    policy = lambda f: cell_best.get(f["cell"], global_best)

    d, d_lo, d_hi = _clustered_ci(confirmation, lambda f: f["q"][policy(f)] - f["q"][global_best])
    g, g_lo, g_hi = _clustered_ci(confirmation, lambda f: f["q"][global_best] - f["q"]["control"])
    cpu_policy = sum(f["cpu"][policy(f)] for f in confirmation)
    cpu_global = sum(f["cpu"][global_best] for f in confirmation)
    cpu_ratio = cpu_policy / cpu_global if cpu_global > 0 else math.nan

    if all(arm == global_best for arm in cell_best.values()) or d_hi < MATERIAL_D:
        verdict = "ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED"
    elif d >= MATERIAL_D and d_lo > 0 and cpu_ratio <= CPU_RATIO_LIMIT:
        verdict = "ADAPTIVE_SEARCH_PARAMS_SIGNAL"
    else:
        verdict = "INCONCLUSIVE"

    def cell_table(subset: list[dict[str, Any]]) -> dict[str, Any]:
        table = {}
        for cell in ["ALL"] + cells:
            members = subset if cell == "ALL" else [f for f in subset if f["cell"] == cell]
            entry = {"states": len(members), "sources": len({f["sourceSeed"] for f in members}),
                     "controlMeanQ": _mean([f["q"]["control"] for f in members]),
                     "controlWinRate": _mean([f["won"]["control"] for f in members])}
            for arm in ARMS[1:]:
                mean, lo, hi = _clustered_ci(members, lambda f, a=arm: f["q"][a] - f["q"]["control"])
                entry[arm] = {
                    "deltaQ": mean, "ci95": [lo, hi],
                    "deltaWinRate": _mean([f["won"][arm] - f["won"]["control"] for f in members]),
                    "deltaPotionsUsed": _mean([f["potionsUsed"][arm] - f["potionsUsed"]["control"]
                                               for f in members]),
                    "cpuRatio": (sum(f["cpu"][arm] for f in members)
                                 / max(1e-12, sum(f["cpu"]["control"] for f in members))),
                }
            table[cell] = entry
        return table

    return {
        "verdict": verdict,
        "rule": {"metric": "signedOutcome", "minCellStates": MIN_CELL_STATES, "materialD": MATERIAL_D,
                 "cpuRatioLimit": CPU_RATIO_LIMIT, "replicates": REPLICATES,
                 "bootstrapSeed": BOOTSTRAP_SEED, "splitDomain": SPLIT_DOMAIN},
        "discovery": {"states": len(discovery), "globalBest": global_best, "cellBest": cell_best},
        "confirmation": {"states": len(confirmation),
                         "adaptiveMinusGlobal": {"mean": d, "ci95": [d_lo, d_hi]},
                         "globalMinusControl": {"mean": g, "ci95": [g_lo, g_hi]},
                         "cpuRatioAdaptiveOverGlobal": cpu_ratio},
        "descriptive": {"all": cell_table(fights), "discovery": cell_table(discovery),
                        "confirmation": cell_table(confirmation)},
    }


def _self_test() -> int:
    rng = random.Random(1)

    def synth(effect_by_cell: dict[str, dict[str, float]], seeds: int) -> list[dict[str, Any]]:
        fights = []
        for seed in range(seeds):
            for cell, effects in effect_by_cell.items():
                for k in range(6):
                    base = rng.uniform(0.2, 0.8)
                    q = {a: base + effects.get(a, 0.0) + rng.gauss(0, 0.02) for a in ARMS}
                    fights.append({"stateId": f"{seed}-{cell}-{k}", "sourceSeed": seed,
                                   "split": split_of(seed), "cell": cell, "roomClass": cell.split("-")[0],
                                   "act": 1, "encounter": "X", "q": q,
                                   "won": {a: 1 for a in ARMS}, "potionsUsed": {a: 0 for a in ARMS},
                                   "cpu": {a: 1.0 for a in ARMS}})
        return fights

    flat = analyze(synth({"NORMAL-A1": {}, "BOSS-A1": {}}, 40))
    assert flat["verdict"] in ("ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED", "INCONCLUSIVE"), flat["verdict"]
    hetero = analyze(synth({"NORMAL-A1": {"c12": 0.05}, "BOSS-A1": {"c50": 0.05, "c12": -0.05}}, 40))
    assert hetero["verdict"] == "ADAPTIVE_SEARCH_PARAMS_SIGNAL", hetero
    assert hetero["discovery"]["cellBest"] == {"BOSS-A1": "c50", "NORMAL-A1": "c12"}
    uniform = analyze(synth({"NORMAL-A1": {"c50": 0.05}, "BOSS-A1": {"c50": 0.05}}, 40))
    assert uniform["verdict"] == "ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED", uniform["verdict"]
    assert uniform["discovery"]["globalBest"] == "c50"
    assert uniform["confirmation"]["globalMinusControl"]["ci95"][0] > 0

    # Loader: header, hash, missing-arm and identity checks on a tiny shard.
    with tempfile.TemporaryDirectory() as tmp:
        prefix = str(Path(tmp) / "shard")
        with open(prefix + ".states.csv", "w", newline="") as s:
            w = csv.writer(s); w.writerow(STATES_HEADER)
            w.writerow(["s7-f0", 7, 0, 1, 1, "NORMAL", "X", 80, 80, 1, 10, 1, 1, 0.5, 40, 40, 3, 1])
        with open(prefix + ".arms.csv", "w", newline="") as a:
            w = csv.writer(a); w.writerow(ARMS_HEADER)
            for arm in ARMS:
                w.writerow(["s7-f0", 7, 0, arm, 25, 25, 3.7, 0.5, 3.7, 0.5, "PLAYER_VICTORY", 1, 0.5,
                            40, 40, 1, 3, 0.1, 10, 1, 1, 1 if arm == "control" else -1, ""])
        manifest = {"schemaVersion": "silver_param_screen_400_stage1_v1", "arms": {a: {} for a in ARMS},
                    "producerGitSha": "a" * 40, "producerExecutableSha256": "b" * 64, "teacherId": "t",
                    "seedSpec": {"start": 7, "count": 1}, "integrity": {},
                    "outputs": {"statesSha256": _sha256(Path(prefix + ".states.csv")),
                                "armsSha256": _sha256(Path(prefix + ".arms.csv"))}}
        Path(prefix + ".manifest.json").write_text(json.dumps(manifest))
        fights, info = load([prefix])
        assert len(fights) == 1 and info["counts"]["valid_states"] == 1
        with open(prefix + ".arms.csv", "a") as a:
            a.write("s7-f0,7,0,control,25,25,3.7,0.5,3.7,0.5,PLAYER_VICTORY,1,0.5,40,40,1,3,0.1,10,1,1,1,\n")
        try:
            load([prefix])
            raise AssertionError("hash mismatch not detected")
        except AnalysisError:
            pass
    print("silver param screen #400 analysis self-test: PASS")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prefixes", nargs="*", help="silverparams400gen output prefixes")
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.prefixes:
        parser.error("at least one prefix is required")
    fights, info = load(args.prefixes)
    report = {**info, **analyze(fights)}
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
