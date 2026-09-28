#!/usr/bin/env python3
"""Paired, source-seed-clustered analysis for #347 Stage 1 boss replays."""

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


ARMS = {"A": 10000, "B100": 100000, "B30": 30000}
STATES_HEADER = ["stateId", "sourceSeed", "fightIdx", "act", "floor", "roomClass",
                 "encounter", "sourceWon", "sourceSignedOutcome", "sourceTerminalHp",
                 "sourcePostAfterBattleHp", "sourceFirstActionBits", "trajectoryValid"]
ARMS_HEADER = ["stateId", "sourceSeed", "fightIdx", "act", "encounter", "arm", "budget",
               "outcome", "won", "signedOutcome", "terminalHp", "postAfterBattleHp",
               "firstActionBits", "firstDecisionAgreement", "cpuSeconds", "simulations",
               "decisions", "valid", "sourceReplayMatch", "quarantineReason"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return math.nan
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _paired_cluster_bootstrap(states: list[dict[str, Any]], arm: str, metric: str,
                              replicates: int, seed: int) -> tuple[float, float]:
    clusters: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for state in states:
        if state.get(arm) is not None:
            clusters[int(state["sourceSeed"])].append(state)
    seeds = sorted(clusters)
    if not seeds:
        raise AnalysisError(f"no paired states for {arm}")
    rng = random.Random(seed)
    differences = []
    for _ in range(replicates):
        sampled = [rng.choice(seeds) for _ in seeds]
        paired = [state for source_seed in sampled for state in clusters[source_seed]]
        diffs = [float(state[arm][metric]) - float(state["A"][metric]) for state in paired]
        differences.append(sum(diffs) / len(diffs))
    return _percentile(differences, 0.025), _percentile(differences, 0.975)


def _mean(states: list[dict[str, Any]], arm: str, metric: str) -> float | None:
    values = [float(state[arm][metric]) for state in states if state.get(arm) is not None]
    return sum(values) / len(values) if values else None


def _paired(states: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    return [state for state in states if state.get("A") is not None
            and state["A"]["sourceMatch"] and state.get(arm) is not None]


def _arm_metrics(states: list[dict[str, Any]], arm: str, replicates: int,
                 bootstrap_seed: int) -> dict[str, Any] | None:
    pairs = _paired(states, arm)
    if not pairs:
        return None
    win_delta = _mean(pairs, arm, "won") - _mean(pairs, "A", "won")
    signed_delta = _mean(pairs, arm, "signedOutcome") - _mean(pairs, "A", "signedOutcome")
    win_ci = _paired_cluster_bootstrap(pairs, arm, "won", replicates, bootstrap_seed)
    signed_ci = _paired_cluster_bootstrap(pairs, arm, "signedOutcome", replicates,
                                           bootstrap_seed + 1)
    both_won = [state for state in pairs if state["A"]["won"] == 1.0
                and state[arm]["won"] == 1.0]
    hp_delta = (sum(state[arm]["postAfterBattleHp"] - state["A"]["postAfterBattleHp"]
                    for state in both_won) / len(both_won)) if both_won else None
    prefix = arm
    return {
        "pairedStates": len(pairs),
        "uniqueSourceSeeds": len({state["sourceSeed"] for state in pairs}),
        "AWinRate": _mean(pairs, "A", "won"),
        f"{prefix}WinRate": _mean(pairs, arm, "won"),
        f"{prefix}MinusAWinRate": win_delta,
        f"{prefix}MinusAWinRateClusterBootstrap95CI": list(win_ci),
        "ASignedOutcome": _mean(pairs, "A", "signedOutcome"),
        f"{prefix}SignedOutcome": _mean(pairs, arm, "signedOutcome"),
        f"{prefix}MinusASignedOutcome": signed_delta,
        f"{prefix}MinusASignedOutcomeClusterBootstrap95CI": list(signed_ci),
        "postBossHpDeltaWhenBothWin": hp_delta,
        "AFirstDecisionAgreement": _mean(pairs, "A", "firstDecisionAgreement"),
        f"{prefix}FirstDecisionAgreement": _mean(pairs, arm, "firstDecisionAgreement"),
        "ACpuSeconds": _mean(pairs, "A", "cpuSeconds"),
        f"{prefix}CpuSeconds": _mean(pairs, arm, "cpuSeconds"),
        "ASimulations": _mean(pairs, "A", "simulations"),
        f"{prefix}Simulations": _mean(pairs, arm, "simulations"),
        "ADecisions": _mean(pairs, "A", "decisions"),
        f"{prefix}Decisions": _mean(pairs, arm, "decisions"),
    }


def _verified_baselines(rows: list[dict[str, str]],
                        state_rows: list[dict[str, str]]) -> dict[str, bool]:
    """Recompute replay admission from source states, never from a match flag alone."""
    states = {}
    for state in state_rows:
        state_id = state.get("stateId")
        if not state_id or state_id in states:
            raise AnalysisError("empty or duplicate source stateId")
        if state.get("trajectoryValid") != "1" or state.get("sourceWon") not in {"0", "1"}:
            raise AnalysisError(f"{state_id}: source state must be valid and resolved")
        try:
            hp = int(state["sourceTerminalHp"])
        except (KeyError, ValueError, TypeError) as exc:
            raise AnalysisError(f"{state_id}: invalid source terminal HP") from exc
        if hp < 0:
            raise AnalysisError(f"{state_id}: negative source terminal HP")
        states[state_id] = state
    baselines = {}
    seen = set()
    for row in rows:
        state_id, arm = row.get("stateId"), row.get("arm")
        if state_id not in states:
            raise AnalysisError("arm has no source state join")
        state = states[state_id]
        if any(row.get(field) != state.get(field)
               for field in ("sourceSeed", "fightIdx", "act", "encounter")):
            raise AnalysisError(f"{state_id}: source-state identity mismatch")
        if arm not in ARMS or (state_id, arm) in seen:
            raise AnalysisError(f"{state_id}: unsupported or duplicate arm")
        seen.add((state_id, arm))
        if row.get("valid") not in {"0", "1"}:
            raise AnalysisError(f"{state_id}: arm valid must be 0/1")
        outcome_won = {"PLAYER_VICTORY": "1", "PLAYER_LOSS": "0", "UNDECIDED": "-1"}
        if row.get("outcome") not in outcome_won or row.get("won") != outcome_won[row["outcome"]]:
            raise AnalysisError(f"{state_id}: arm outcome disagrees with won")
        if arm == "A":
            try:
                terminal_hp = int(row["terminalHp"])
            except (KeyError, ValueError, TypeError) as exc:
                raise AnalysisError(f"{state_id}: invalid A terminal HP") from exc
            matches = (row["valid"] == "1" and row["won"] == state["sourceWon"]
                       and terminal_hp == int(state["sourceTerminalHp"]))
            if row.get("sourceReplayMatch") != str(int(matches)):
                raise AnalysisError(f"{state_id}: sourceReplayMatch contradicts A outcome/terminal HP/validity")
            if row["valid"] == "1" and not matches:
                raise AnalysisError(f"{state_id}: valid A does not match source outcome/terminal HP")
            baselines[state_id] = matches
        elif row.get("sourceReplayMatch") != "-1":
            raise AnalysisError(f"{state_id}: non-A sourceReplayMatch must be -1")
    if set(baselines) != set(states):
        raise AnalysisError("each source state requires an A replay")
    for row in rows:
        if row["arm"] != "A" and row["valid"] == "1" and not baselines[row["stateId"]]:
            raise AnalysisError(f"{row['stateId']}: valid B arm requires a matching valid A replay")
    return baselines


def _load_and_validate_manifest(arms_path: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    if not arms_path.name.endswith(".arms.csv"):
        raise AnalysisError("arms file must end in .arms.csv so its manifest can be resolved")
    prefix = arms_path.name[:-len(".arms.csv")]
    manifest_path = arms_path.with_name(prefix + ".manifest.json")
    states_path = arms_path.with_name(prefix + ".states.csv")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with arms_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            arms_header = list(reader.fieldnames or [])
            rows = list(reader)
        with states_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            states_header = list(reader.fieldnames or [])
            state_rows = list(reader)
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisError(f"cannot read Track B bundle: {exc}") from exc
    if manifest.get("schemaVersion") != "boss_headroom_347_stage1_v1":
        raise AnalysisError("unsupported Track B manifest schema")
    git_sha = manifest.get("producerGitSha", "")
    if not isinstance(git_sha, str) or len(git_sha) != 40 or any(c not in "0123456789abcdef" for c in git_sha):
        raise AnalysisError("manifest producerGitSha is invalid")
    for field in ("producerExecutableSha256", "teacherManifestSha256"):
        value = manifest.get(field, "")
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise AnalysisError(f"manifest {field} is invalid")
    if not manifest.get("teacherId"):
        raise AnalysisError("manifest teacherId is missing")
    if arms_header != ARMS_HEADER or states_header != STATES_HEADER:
        raise AnalysisError("Track B CSV header mismatch")
    outputs = manifest.get("outputs", {})
    if outputs.get("armsSha256") != _sha256(arms_path):
        raise AnalysisError("arms.csv SHA-256 mismatch")
    if outputs.get("statesSha256") != _sha256(states_path):
        raise AnalysisError("states.csv SHA-256 mismatch")
    if manifest.get("arms") != ARMS:
        raise AnalysisError("manifest arm budgets mismatch")
    seed_spec = manifest.get("seedSpec", {})
    start, count = seed_spec.get("start"), seed_spec.get("count")
    if (type(start) is not int or type(count) is not int or count < 1
            or seed_spec.get("ascension") != 0):
        raise AnalysisError("manifest seedSpec is invalid")
    allowed_seeds = set(range(start, start + count))
    state_by_id: dict[str, dict[str, str]] = {}
    for index, row in enumerate(state_rows, 2):
        state_id = row.get("stateId", "")
        if not state_id or state_id in state_by_id:
            raise AnalysisError(f"states.csv:{index}: empty or duplicate stateId")
        try:
            source_seed = int(row["sourceSeed"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisError(f"states.csv:{index}: invalid sourceSeed") from exc
        if source_seed not in allowed_seeds:
            raise AnalysisError(f"states.csv:{index}: seed outside manifest range")
        state_by_id[state_id] = row
    arm_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, 2):
        state_id, arm = row.get("stateId", ""), row.get("arm", "")
        if state_id not in state_by_id:
            raise AnalysisError(f"arms.csv:{index}: no source state join")
        key = (state_id, arm)
        if arm not in ARMS or key in arm_keys:
            raise AnalysisError(f"arms.csv:{index}: unsupported or duplicate state/arm")
        arm_keys.add(key)
        state = state_by_id[state_id]
        if (row["sourceSeed"] != state["sourceSeed"] or row["fightIdx"] != state["fightIdx"]
                or row["act"] != state["act"] or row["encounter"] != state["encounter"]):
            raise AnalysisError(f"arms.csv:{index}: source-state identity mismatch")
    expected_arm_keys = {(state_id, arm) for state_id in state_by_id for arm in ARMS}
    if arm_keys != expected_arm_keys:
        raise AnalysisError("each selected state must have exactly A, B100 and B30 rows")
    integrity = manifest.get("integrity", {})
    if integrity.get("selectedStates") != len(state_by_id):
        raise AnalysisError("manifest selected state count mismatch")
    _verified_baselines(rows, state_rows)
    return manifest, rows, state_rows


def analyze_rows(rows: list[dict[str, str]], state_rows: list[dict[str, str]],
                 replicates: int = 2000,
                 bootstrap_seed: int = 347334) -> dict[str, Any]:
    if replicates < 100:
        raise AnalysisError("use at least 100 bootstrap replicates")
    baselines = _verified_baselines(rows, state_rows)
    by_state: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, 2):
        arm = row.get("arm")
        if arm not in ARMS:
            raise AnalysisError(f"row {index}: unsupported arm {arm!r}")
        if int(row.get("budget", -1)) != ARMS[arm]:
            raise AnalysisError(f"row {index}: {arm} budget mismatch")
        state_id = row.get("stateId", "")
        if not state_id:
            raise AnalysisError(f"row {index}: missing stateId")
        try:
            source_seed = int(row["sourceSeed"])
            act = int(row["act"])
            encounter = row["encounter"]
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisError(f"row {index}: invalid source-state identity") from exc
        state = by_state.setdefault(state_id, {"stateId": state_id,
            "sourceSeed": source_seed, "act": act, "encounter": encounter})
        if state["sourceSeed"] != source_seed:
            raise AnalysisError(f"row {index}: stateId crosses source seeds")
        if state["act"] != act or state["encounter"] != encounter:
            raise AnalysisError(f"row {index}: stateId crosses boss groups")
        if arm in state:
            raise AnalysisError(f"row {index}: duplicate {arm} row for {state_id}")
        valid = row.get("valid") == "1"
        source_match = baselines[state_id]
        def number(name: str) -> float:
            try:
                value = float(row[name])
            except (KeyError, TypeError, ValueError) as exc:
                raise AnalysisError(f"row {index}: invalid {name}") from exc
            if not math.isfinite(value):
                raise AnalysisError(f"row {index}: non-finite {name}")
            return value
        result = {
            "valid": valid,
            "sourceMatch": source_match,
            "won": number("won"),
            "signedOutcome": number("signedOutcome"),
            "terminalHp": number("terminalHp"),
            "postAfterBattleHp": number("postAfterBattleHp"),
            "firstDecisionAgreement": number("firstDecisionAgreement"),
            "cpuSeconds": number("cpuSeconds"),
            "simulations": number("simulations"),
            "decisions": number("decisions"),
        }
        if valid and result["won"] not in {0.0, 1.0}:
            raise AnalysisError(f"row {index}: resolved arm outcome must be 0/1")
        state[arm] = result if valid else None
        if arm == "A" and not source_match:
            state["sourceMismatch"] = True

    states = list(by_state.values())
    primary = [state for state in states if state.get("A") is not None
               and state["A"]["sourceMatch"] and state.get("B100") is not None]
    secondary = [state for state in states if state.get("A") is not None
                 and state["A"]["sourceMatch"] and state.get("B30") is not None]
    if not primary:
        raise AnalysisError("no complete valid A/B100 pairs with source-matching A replay")

    win_delta = _mean(primary, "B100", "won") - _mean(primary, "A", "won")
    signed_delta = _mean(primary, "B100", "signedOutcome") - _mean(primary, "A", "signedOutcome")
    win_ci = _paired_cluster_bootstrap(primary, "B100", "won", replicates, bootstrap_seed)
    signed_ci = _paired_cluster_bootstrap(primary, "B100", "signedOutcome", replicates,
                                           bootstrap_seed + 1)
    combat_headroom = ((win_delta >= 0.10 and win_ci[0] > 0.0)
                       or (signed_delta >= 0.05 and signed_ci[0] > 0.0))
    classification = "COMBAT_HEADROOM" if combat_headroom else "NO_COMBAT_HEADROOM_AT_SMOKE_SCALE"
    extend = not combat_headroom and win_delta >= 0.05 and win_ci[0] <= 0.0 <= win_ci[1]

    both_won = [state for state in primary if state["A"]["won"] == 1.0
                and state["B100"]["won"] == 1.0]
    hp_delta = (sum(state["B100"]["postAfterBattleHp"] - state["A"]["postAfterBattleHp"]
                    for state in both_won) / len(both_won)) if both_won else None

    def grouped_report(field: str) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for state in states:
            groups[str(state[field])].append(state)
        result: dict[str, Any] = {}
        for group_index, key in enumerate(sorted(groups)):
            arm_results: dict[str, Any] = {}
            for arm_index, arm in enumerate(("B100", "B30")):
                metrics = _arm_metrics(groups[key], arm, replicates,
                    bootstrap_seed + 17 * (group_index + 1) + arm_index * 100003)
                if metrics is not None:
                    arm_results[arm] = metrics
            if arm_results:
                result[key] = arm_results
        return result

    report = {
        "schema": "boss_headroom_347_analysis_v1",
        "primary": {
            "pairedStates": len(primary),
            "uniqueSourceSeeds": len({state["sourceSeed"] for state in primary}),
            "AWinRate": _mean(primary, "A", "won"),
            "B100WinRate": _mean(primary, "B100", "won"),
            "B100MinusAWinRate": win_delta,
            "B100MinusAWinRateClusterBootstrap95CI": list(win_ci),
            "ASignedOutcome": _mean(primary, "A", "signedOutcome"),
            "B100SignedOutcome": _mean(primary, "B100", "signedOutcome"),
            "B100MinusASignedOutcome": signed_delta,
            "B100MinusASignedOutcomeClusterBootstrap95CI": list(signed_ci),
            "postBossHpDeltaWhenBothWin": hp_delta,
            "AFirstDecisionAgreement": _mean(primary, "A", "firstDecisionAgreement"),
            "B100FirstDecisionAgreement": _mean(primary, "B100", "firstDecisionAgreement"),
            "ACpuSeconds": _mean(primary, "A", "cpuSeconds"),
            "B100CpuSeconds": _mean(primary, "B100", "cpuSeconds"),
            "ASimulations": _mean(primary, "A", "simulations"),
            "B100Simulations": _mean(primary, "B100", "simulations"),
        },
        "secondaryB30": {
            "pairedStates": len(secondary),
            "AWinRate": _mean(secondary, "A", "won") if secondary else None,
            "B30WinRate": _mean(secondary, "B30", "won") if secondary else None,
            "B30MinusAWinRate": (_mean(secondary, "B30", "won") - _mean(secondary, "A", "won"))
                if secondary else None,
            "AFirstDecisionAgreement": _mean(secondary, "A", "firstDecisionAgreement") if secondary else None,
            "B30FirstDecisionAgreement": _mean(secondary, "B30", "firstDecisionAgreement") if secondary else None,
            "ACpuSeconds": _mean(secondary, "A", "cpuSeconds") if secondary else None,
            "B30CpuSeconds": _mean(secondary, "B30", "cpuSeconds") if secondary else None,
        },
        "classification": classification,
        "extensionToAllPilotBossStatesRecommended": extend,
        "byAct": grouped_report("act"),
        "byBoss": grouped_report("encounter"),
        "bootstrap": {"replicates": replicates, "cluster": "sourceSeed", "seed": bootstrap_seed},
    }
    return report


def _self_test() -> None:
    rows: list[dict[str, str]] = []
    for seed, a_won, b_won in ((10, 0, 1), (11, 0, 1), (12, 0, 1), (13, 0, 1)):
        for arm, budget, won in (("A", 10000, a_won), ("B100", 100000, b_won),
                                 ("B30", 30000, b_won)):
            rows.append({"stateId": f"s{seed}", "sourceSeed": str(seed), "arm": arm,
                "budget": str(budget), "fightIdx": "2", "act": "1", "encounter": "TEST_BOSS",
                "won": str(won), "signedOutcome": str(won * 0.8 - (1-won)*0.4),
                "outcome": "PLAYER_VICTORY" if won else "PLAYER_LOSS",
                "terminalHp": "40" if won else "0", "postAfterBattleHp": "42" if won else "0", "firstDecisionAgreement": "1",
                "cpuSeconds": "1.5", "simulations": str(budget), "decisions": "3",
                "valid": "1", "sourceReplayMatch": "1" if arm == "A" else "-1"})
    def source_states(arms):
        return [{"stateId": row["stateId"], "sourceSeed": row["sourceSeed"],
                 "fightIdx": row["fightIdx"], "act": row["act"], "floor": "16",
                 "roomClass": "BOSS", "encounter": row["encounter"],
                 "sourceWon": row["won"], "sourceSignedOutcome": row["signedOutcome"],
                 "sourceTerminalHp": row["terminalHp"],
                 "sourcePostAfterBattleHp": row["postAfterBattleHp"],
                 "sourceFirstActionBits": "1", "trajectoryValid": "1"}
                for row in arms if row["arm"] == "A"]

    state_rows = source_states(rows)
    result = analyze_rows(rows, state_rows, replicates=500, bootstrap_seed=1)
    if result["classification"] != "COMBAT_HEADROOM":
        raise AssertionError("positive paired smoke evidence was not classified as headroom")
    if result["primary"]["pairedStates"] != 4:
        raise AssertionError("paired state count mismatch")
    if "1" not in result["byAct"] or "TEST_BOSS" not in result["byBoss"]:
        raise AssertionError("per-act/per-boss paired metrics missing")

    with tempfile.TemporaryDirectory(prefix="boss_headroom_347_") as temp_dir:
        prefix = Path(temp_dir) / "fixture"
        states_path = Path(str(prefix) + ".states.csv")
        arms_path = Path(str(prefix) + ".arms.csv")
        manifest_path = Path(str(prefix) + ".manifest.json")
        with states_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=STATES_HEADER)
            writer.writeheader()
            writer.writerows(state_rows)
        with arms_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=ARMS_HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in ARMS_HEADER})
        manifest = {"schemaVersion": "boss_headroom_347_stage1_v1",
            "producerGitSha": "a" * 40, "producerExecutableSha256": "b" * 64,
            "teacherManifestSha256": "c" * 64, "teacherId": "fixture", "arms": ARMS,
            "seedSpec": {"start": 10, "count": 4, "ascension": 0},
            "integrity": {"selectedStates": 4},
            "outputs": {"armsSha256": _sha256(arms_path),
                        "statesSha256": _sha256(states_path)}}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        _, loaded_rows, loaded_states = _load_and_validate_manifest(arms_path)
        if len(loaded_rows) != len(rows):
            raise AssertionError("manifest-validated arm row count mismatch")
        if analyze_rows(loaded_rows, loaded_states, replicates=500, bootstrap_seed=1) != result:
            raise AssertionError("loaded analysis differs from direct joined analysis")

        def reject(mutated, expected):
            # Keep hashes correct so every rejection proves the semantic gate.
            with arms_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=ARMS_HEADER)
                writer.writeheader()
                writer.writerows({field: row.get(field, "") for field in ARMS_HEADER}
                                 for row in mutated)
            manifest["outputs"]["armsSha256"] = _sha256(arms_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            for check in (lambda: _load_and_validate_manifest(arms_path),
                          lambda: analyze_rows(mutated, state_rows, replicates=100)):
                try:
                    check()
                except AnalysisError as exc:
                    if expected not in str(exc):
                        raise
                else:
                    raise AssertionError(f"did not reject {expected}")

        for change in ({"terminalHp": "40"},
                       {"won": "1", "outcome": "PLAYER_VICTORY"},
                       {"sourceReplayMatch": "0"},
                       {"valid": "0"}):
            mutated = [dict(row) for row in rows]
            mutated[0].update(change)
            reject(mutated, "sourceReplayMatch contradicts")
        for b_arm in ("B100", "B30"):
            mutated = [dict(row) for row in rows]
            mutated[0].update(valid="0", sourceReplayMatch="0", terminalHp="40")
            for row in mutated[1:3]:
                row["valid"] = "1" if row["arm"] == b_arm else "0"
            reject(mutated, "valid B arm requires")
        # A quarantined state excludes both B arms from every analysis group.
        quarantined = [dict(row) for row in rows]
        for row in quarantined[:3]:
            row["valid"] = "0"
        quarantined[0].update(sourceReplayMatch="0", terminalHp="40")
        filtered = analyze_rows(quarantined, state_rows, replicates=100)
        if filtered["primary"]["pairedStates"] != 3 or filtered["secondaryB30"]["pairedStates"] != 3:
            raise AssertionError("invalid A admitted B pairs")
        with arms_path.open("a", encoding="utf-8") as stream:
            stream.write("tampered\n")
        try:
            _load_and_validate_manifest(arms_path)
        except AnalysisError as exc:
            if "SHA-256 mismatch" not in str(exc):
                raise
        else:
            raise AssertionError("bundle hash mismatch was not rejected")
    ambiguous_rows: list[dict[str, str]] = []
    for seed, a_won, b_won in ((20, 0, 1), (21, 0, 0)):
        for arm, budget, won in (("A", 10000, a_won), ("B100", 100000, b_won)):
            ambiguous_rows.append({"stateId": f"s{seed}", "sourceSeed": str(seed), "arm": arm,
                "budget": str(budget), "fightIdx": "2", "act": "2", "encounter": "AMBIGUOUS_BOSS",
                "won": str(won), "signedOutcome": str(won * 0.8 - (1-won)*0.4),
                "outcome": "PLAYER_VICTORY" if won else "PLAYER_LOSS",
                "terminalHp": "40" if won else "0", "postAfterBattleHp": "42" if won else "0", "firstDecisionAgreement": "1",
                "cpuSeconds": "1.5", "simulations": str(budget), "decisions": "3",
                "valid": "1", "sourceReplayMatch": "1" if arm == "A" else "-1"})
    uncertain = analyze_rows(ambiguous_rows, source_states(ambiguous_rows), replicates=500, bootstrap_seed=9)
    if (uncertain["classification"] != "NO_COMBAT_HEADROOM_AT_SMOKE_SCALE"
            or not uncertain["extensionToAllPilotBossStatesRecommended"]):
        raise AssertionError("uncertain +5pp-style result did not recommend extension")
    print("boss headroom #347 analyzer selftest: PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arms_csv", nargs="?")
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=347334)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            _self_test()
            return 0
        if not args.arms_csv:
            parser.error("arms_csv is required unless --self-test is used")
        _, rows, states = _load_and_validate_manifest(Path(args.arms_csv))
        report = analyze_rows(rows, states, args.replicates, args.bootstrap_seed)
    except (OSError, AnalysisError) as exc:
        print(f"boss headroom #347: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
