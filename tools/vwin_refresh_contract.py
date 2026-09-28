#!/usr/bin/env python3
"""Strict integrity checks for a vwin-refresh-334 collector bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


class ContractError(ValueError):
    pass


OUTPUTS = {
    "map.csv": ".map.csv",
    "win_raw.csv": ".win_raw.csv",
    "decisions.csv": ".decisions.csv",
    "decision.csv": ".decision.csv",
    "branches.csv": ".branches.csv",
    "combat.csv": ".combat.csv",
    "runout.csv": ".runout.csv",
}

PREFIX = ["sourceSeed", "branchId", "deviationIdx"]
MAP_PREFIX = PREFIX + ["rowIdx", "act", "floor", "mapX", "mapY", "teacherId"]
DECISION_SINK_PREFIX = PREFIX + ["rowIdx", "decisionIdx", "act", "floor", "screen", "teacherId"]
DECISION_SINK_TAIL = ["screenContents", "candidates", "won"]
SCREEN_IDS = {"event": 1, "rewards": 2, "boss_relic": 3, "selector": 4,
              "treasure": 6, "rest": 7, "shop": 8}
RAW_TAIL = ["roomClass", "actBoss", "encounter", "preHp", "preMaxHp",
            "prePotions", "preGold", "postAfterBattleHp"]
DECISION_HEADER = ["sourceSeed", "branchId", "deviationIdx", "decisionIdx", "type",
                   "act", "floor", "screen", "optionCount", "chosenKey", "supported",
                   "complete", "sampled", "candidateKeysJson", "error"]
BRANCH_HEADER = ["sourceSeed", "decisionIdx", "type", "optionKey", "chosen", "branchId",
                 "won", "finalFloor", "finalHp", "valid"]
RUNOUT_HEADER = ["sourceSeed", "branchId", "deviationIdx", "finalOutcome", "finalWon",
                 "finalFloor", "finalHp", "fightCount", "trajectoryComplete", "trajectoryValid",
                 "combatRows", "invalidCombatRows", "teacherId", "simulatorHealthFailures",
                 "fatalFailure", "branchParity"]
COMBAT_PREFIX = PREFIX + ["fightIdx", "act", "floor", "roomClass", "encounter", "teacherId"]


def _fail(message: str) -> None:
    raise ContractError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                _fail(f"{path.name}: missing header")
            rows = list(reader)
            for index, row in enumerate(rows, 2):
                if None in row:
                    _fail(f"{path.name}:{index}: row has more fields than the header")
                if any(value is None for value in row.values()):
                    _fail(f"{path.name}:{index}: row has fewer fields than the header")
            return list(reader.fieldnames), rows
    except OSError as exc:
        _fail(f"cannot read {path}: {exc}")


def _is_finite(value: str, where: str) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        _fail(f"{where}: expected a finite number, got {value!r}")
    if not math.isfinite(number):
        _fail(f"{where}: non-finite value {value!r}")


def _check_finite(rows: Iterable[dict[str, str]], fields: Iterable[str], name: str) -> None:
    for row_number, row in enumerate(rows, 2):
        for field in fields:
            _is_finite(row[field], f"{name}:{row_number}:{field}")


def _check_header(actual: list[str], expected: list[str], name: str) -> None:
    if actual != expected:
        _fail(f"{name}: header mismatch; got {len(actual)} columns, expected {len(expected)}")


def _json_object(value: str, where: str) -> dict:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        _fail(f"{where}: invalid JSON")
    if not isinstance(parsed, dict):
        _fail(f"{where}: expected JSON object")
    return parsed


def _validate_decision_sink(manifest: dict, rows: dict, runouts: dict,
                            path: Path) -> dict:
    spec = manifest["decisionSink"]
    logs = spec.get("trajectories")
    if not isinstance(logs, list):
        _fail("DECISION sink has no per-trajectory decision log")
    logged = {}
    expected_rows = {}
    for trajectory in logs:
        key = trajectory.get("sourceSeed"), trajectory.get("branchId")
        if key not in runouts or key in logged:
            _fail("DECISION log has a missing or duplicate trajectory join")
        if trajectory.get("deviationIdx") != int(runouts[key]["deviationIdx"]):
            _fail("DECISION log deviationIdx disagrees with trajectory")
        decisions = trajectory.get("decisionLog")
        if not isinstance(decisions, list):
            _fail("DECISION log must be an array")
        count = 0
        for item in decisions:
            if (not isinstance(item, dict) or item.get("screen") not in SCREEN_IDS
                    or type(item.get("optionCount")) is not int or item["optionCount"] < 0
                    or type(item.get("decisionIdx")) is not int or item["decisionIdx"] < -1):
                _fail("DECISION log entry is malformed")
            if item["optionCount"] > 1:
                if item.get("rowIdx") != count:
                    _fail("DECISION log rowIdx is not contiguous")
                expected_rows[(key, count)] = item
                count += 1
            elif item.get("rowIdx") != -1:
                _fail("DECISION log singleton unexpectedly has a sink row")
        if trajectory.get("rows") != count:
            _fail("DECISION log row count mismatch")
        logged[key] = count
    if set(logged) != set(runouts):
        _fail("DECISION log must cover every trajectory")

    legacy = {}
    expected_legacy = set()
    for decision in rows["decisions.csv"]:
        key = (int(decision["sourceSeed"]), decision["branchId"], int(decision["decisionIdx"]))
        if key in legacy:
            _fail("decisions.csv: duplicate trajectory decision index")
        legacy[key] = decision
        if int(decision["screen"]) != 5 and int(decision["optionCount"]) > 1:
            expected_legacy.add(key)
    seen = set()
    joined_legacy = set()
    screens = {"source": Counter(), "branch": Counter()}
    required = {
        "event": {"eventId": int, "optionIds": list},
        "rewards": {"gold": list, "cardRewards": list, "relics": list, "potions": list,
                    "emeraldKey": bool, "sapphireKey": bool},
        "boss_relic": {"relics": list},
        "selector": {"selectorType": str, "selectorTypeId": int, "cards": list,
                     "requiredPicks": int, "completedPicks": int},
        "treasure": {"chestSize": int, "availableOptions": list},
        "rest": {"availableOptions": list},
        "shop": {"cards": list, "relics": list, "potionSlots": list, "removeCost": int,
                 "policyBuyableRelics": list},
    }
    for line, row in enumerate(rows["decision.csv"], 2):
        where = f"decision.csv:{line}"
        key = int(row["sourceSeed"]), row["branchId"]
        identity = key, int(row["rowIdx"])
        if identity not in expected_rows or identity in seen:
            _fail(f"{where}: row count/index disagrees with decision log")
        seen.add(identity)
        log = expected_rows[identity]
        screen = row["screen"]
        if screen != log["screen"] or int(row["decisionIdx"]) != log["decisionIdx"]:
            _fail(f"{where}: screen/decision join disagrees with decision log")
        contents = _json_object(row["screenContents"], f"{where}:screenContents")
        if (screen not in SCREEN_IDS or contents.get("screen") != screen
                or contents.get("screenState") != SCREEN_IDS[screen]):
            _fail(f"{where}: screen type does not match screenContents")
        for field, expected_type in required[screen].items():
            if type(contents.get(field)) is not expected_type:
                _fail(f"{where}: malformed {screen} screenContents.{field}")
        candidates = _json_object(row["candidates"], f"{where}:candidates")
        keys = candidates.get("optionKeys")
        if (not isinstance(keys, list) or len(keys) <= 1
                or any(not isinstance(k, str) or not k.startswith("ooc:v1:") for k in keys)
                or len(set(keys)) != len(keys)):
            _fail(f"{where}: candidates must contain more than one unique semantic key")
        if len(keys) != log["optionCount"]:
            _fail(f"{where}: candidate count disagrees with decision log")
        chosen = candidates.get("chosenKey")
        if chosen not in keys:
            _fail(f"{where}: chosen key is absent from candidates")
        if candidates.get("supported") is not True or candidates.get("complete") is not True:
            _fail(f"{where}: unsupported/incomplete semantic candidates")
        outcome = runouts[key]
        if int(row["won"]) != int(outcome["finalWon"]):
            _fail(f"{where}: won disagrees with trajectory outcome")
        if row["teacherId"] != manifest["teacherId"] or row["teacherId"] != outcome["teacherId"]:
            _fail(f"{where}: teacherId disagrees with trajectory")
        if int(row["deviationIdx"]) != int(outcome["deviationIdx"]):
            _fail(f"{where}: deviationIdx disagrees with trajectory")
        idx = int(row["decisionIdx"])
        if idx >= 0:
            legacy_key = key + (idx,)
            decision = legacy.get(legacy_key)
            if not decision or legacy_key in joined_legacy:
                _fail(f"{where}: missing or duplicate legacy decision join")
            joined_legacy.add(legacy_key)
            if (decision["chosenKey"] != chosen or int(decision["screen"]) != SCREEN_IDS[screen]
                    or decision["act"] != row["act"] or decision["floor"] != row["floor"]
                    or not set(json.loads(decision["candidateKeysJson"])).issubset(keys)):
                _fail(f"{where}: contents disagree with legacy decision log")
        screens["source" if key[1] == "source" else "branch"][screen] += 1
    if seen != set(expected_rows):
        _fail("DECISION row counts do not match decision log")
    if not expected_legacy.issubset(joined_legacy):
        _fail("DECISION sink is missing a multi-option legacy decision")
    count = len(seen)
    if spec.get("rows") != count or manifest.get("integrity", {}).get("decisionSinkRows") != count:
        _fail("manifest DECISION row count mismatch")
    actual_screens = {kind: dict(counts) for kind, counts in screens.items()}
    if spec.get("byScreen") != actual_screens:
        _fail("manifest DECISION byScreen count mismatch")
    byte_count = path.stat().st_size
    if spec.get("bytes") != byte_count:
        _fail("manifest DECISION byte count mismatch")
    expected_size = byte_count / count if count else 0.0
    if not math.isclose(spec.get("bytesPerRow", -1), expected_size, rel_tol=1e-6):
        _fail("manifest DECISION bytesPerRow mismatch")
    source_count = manifest["seedSpec"]["count"]
    if (spec.get("projectionSourceSeeds") != source_count
            or spec.get("projectionTargetSeeds") != 4096
            or not math.isclose(spec.get("projectedA2Bytes", -1), byte_count * 4096 / source_count,
                                rel_tol=1e-6)):
        _fail("manifest DECISION A2 size projection mismatch")
    return {"decision_sink_rows": count, "decision_rows_by_screen": actual_screens,
            "decision_bytes_per_row": expected_size, "decision_projected_a2_bytes": spec["projectedA2Bytes"]}


def validate_bundle(manifest_path: str | Path) -> dict[str, object]:
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read manifest: {exc}")
    if manifest.get("schemaVersion") != "vwin_refresh_334_v1":
        _fail("unsupported manifest schema")
    for key in ("producerExecutableSha256", "teacherManifestSha256"):
        value = manifest.get(key, "")
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            _fail(f"manifest {key} is not a lowercase SHA-256")
    producer_git = manifest.get("producerGitSha", "")
    if not isinstance(producer_git, str) or not re.fullmatch(r"[0-9a-f]{40}", producer_git):
        _fail("manifest producerGitSha is not a lowercase Git SHA")
    if not manifest.get("teacherId"):
        _fail("manifest teacherId is missing")

    feature_spec = manifest.get("stateFeatures", {})
    feature_header = feature_spec.get("header")
    if not isinstance(feature_header, str):
        _fail("manifest has no state feature header")
    features = feature_header.split(",")
    if len(features) != 1017 or feature_spec.get("count") != 1017:
        _fail("rich feature contract must contain exactly 1,017 columns")
    if hashlib.sha256(feature_header.encode()).hexdigest() != feature_spec.get("headerSha256"):
        _fail("rich feature header SHA-256 mismatch")

    seed_spec = manifest.get("seedSpec", {})
    seed_start, seed_count = seed_spec.get("start"), seed_spec.get("count")
    if not isinstance(seed_start, int) or not isinstance(seed_count, int) or seed_count < 1:
        _fail("manifest seedSpec is invalid")
    allowed_seeds = set(range(seed_start, seed_start + seed_count))
    split = manifest.get("split", {})
    if (split.get("rule") != "source_seed_sha256_prefix_v1"
            or split.get("domain") != "vwin-refresh-334-v1:{seed}"
            or split.get("prefixBytes") != 4 or split.get("trainLt") != 0.70
            or split.get("validationLt") != 0.85
            or split.get("branchesInheritSourceSeed") is not True):
        _fail("manifest source-seed 70/15/15 split contract mismatch")
    parity = manifest.get("branchParity", {})
    if (not isinstance(parity.get("percent"), int) or parity["percent"] < 0
            or parity["percent"] > 100 or parity.get("failures") != 0):
        _fail("manifest chosen-replay parity contract is invalid or contains failures")
    prefix = str(manifest_path)
    if not prefix.endswith(".manifest.json"):
        _fail("manifest filename must end in .manifest.json")
    prefix = prefix[: -len(".manifest.json")]

    decision_sink = manifest.get("decisionSink")
    if decision_sink is not None and (not isinstance(decision_sink, dict)
            or decision_sink.get("enabled") is not True
            or decision_sink.get("schema") != "vwin_decision_334_v1"):
        _fail("unsupported DECISION sink schema/configuration")
    if decision_sink is None and "decision.csv" in manifest.get("outputs", {}):
        _fail("DECISION output is present without a sink manifest")
    tables: dict[str, tuple[list[str], list[dict[str, str]]]] = {}
    for key, suffix in OUTPUTS.items():
        if key == "decision.csv" and decision_sink is None:
            continue
        path = Path(prefix + suffix)
        expected_hash = manifest.get("outputs", {}).get(key)
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            _fail(f"manifest has no valid hash for {key}")
        if _sha256(path) != expected_hash:
            _fail(f"{key}: SHA-256 mismatch")
        tables[key] = _read_csv(path)

    headers = {key: value[0] for key, value in tables.items()}
    rows = {key: value[1] for key, value in tables.items()}
    _check_header(headers["map.csv"], MAP_PREFIX + features, "map.csv")
    _check_header(headers["win_raw.csv"], MAP_PREFIX + features + RAW_TAIL, "win_raw.csv")
    _check_header(headers["decisions.csv"], DECISION_HEADER, "decisions.csv")
    if decision_sink is not None:
        _check_header(headers["decision.csv"], DECISION_SINK_PREFIX + features + DECISION_SINK_TAIL,
                      "decision.csv")
    _check_header(headers["branches.csv"], BRANCH_HEADER, "branches.csv")
    if headers["combat.csv"][: len(COMBAT_PREFIX)] != COMBAT_PREFIX:
        _fail("combat.csv: prefix mismatch")
    if headers["combat.csv"][len(COMBAT_PREFIX):len(COMBAT_PREFIX) + len(features)] != features:
        _fail("combat.csv: rich feature block mismatch")
    label_fields = headers["combat.csv"][len(COMBAT_PREFIX) + len(features):]
    if "won" not in label_fields or "labelValid" not in label_fields:
        _fail("combat.csv: missing V1 terminal label fields")
    _check_header(headers["runout.csv"], RUNOUT_HEADER, "runout.csv")

    expected_numeric = {
        "map.csv": ["sourceSeed", "deviationIdx", "rowIdx", "act", "floor", "mapX", "mapY"] + features,
        "win_raw.csv": ["sourceSeed", "deviationIdx", "rowIdx", "act", "floor", "mapX", "mapY"]
            + features + ["actBoss", "preHp", "preMaxHp", "prePotions", "preGold", "postAfterBattleHp"],
        "combat.csv": ["sourceSeed", "deviationIdx", "fightIdx", "act", "floor"] + features
            + [field for field in label_fields if field not in {"quarantineReason"}],
        "runout.csv": [field for field in RUNOUT_HEADER if field not in
            {"branchId", "finalOutcome", "teacherId", "branchParity"}],
        "branches.csv": ["sourceSeed", "decisionIdx", "chosen", "won", "finalFloor", "finalHp", "valid"],
        "decisions.csv": ["sourceSeed", "deviationIdx", "decisionIdx", "act", "floor", "screen",
                          "optionCount", "supported", "complete", "sampled"],
    }
    if decision_sink is not None:
        expected_numeric["decision.csv"] = ["sourceSeed", "deviationIdx", "rowIdx", "decisionIdx",
                                              "act", "floor", "won"] + features
    for name, fields in expected_numeric.items():
        _check_finite(rows[name], fields, name)

    runout_by_key: dict[tuple[int, str], dict[str, str]] = {}
    for index, row in enumerate(rows["runout.csv"], 2):
        seed = int(row["sourceSeed"])
        if seed not in allowed_seeds:
            _fail(f"runout.csv:{index}: seed {seed} is outside seedSpec")
        key = seed, row["branchId"]
        if key in runout_by_key:
            _fail(f"runout.csv:{index}: duplicate branch outcome for {key}")
        if row["finalOutcome"] not in {"PLAYER_VICTORY", "PLAYER_LOSS", "UNDECIDED"}:
            _fail(f"runout.csv:{index}: unknown final outcome")
        runout_by_key[key] = row
    for seed in allowed_seeds:
        if (seed, "source") not in runout_by_key:
            _fail(f"missing source runout for seed {seed}")

    def check_rows_joined(name: str) -> None:
        for index, row in enumerate(rows[name], 2):
            seed = int(row["sourceSeed"])
            if seed not in allowed_seeds:
                _fail(f"{name}:{index}: seed {seed} is outside seedSpec")
            if (seed, row["branchId"]) not in runout_by_key:
                _fail(f"{name}:{index}: row has no runout outcome")

    for name in ("map.csv", "win_raw.csv", "decisions.csv", "combat.csv"):
        check_rows_joined(name)

    sink_summary = {}
    if decision_sink is not None:
        check_rows_joined("decision.csv")
        sink_summary = _validate_decision_sink(manifest, rows, runout_by_key,
                                              Path(prefix + ".decision.csv"))

    source_decisions: dict[tuple[int, int], dict[str, str]] = {}
    sampled_groups: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows["decisions.csv"], 2):
        if row["branchId"] != "source":
            continue
        seed, decision_idx = int(row["sourceSeed"]), int(row["decisionIdx"])
        key = seed, decision_idx
        if key in source_decisions:
            _fail(f"decisions.csv:{index}: duplicate source decision index")
        source_decisions[key] = row
        try:
            candidate_keys = json.loads(row["candidateKeysJson"])
        except json.JSONDecodeError:
            _fail(f"decisions.csv:{index}: candidateKeysJson is invalid")
        if not isinstance(candidate_keys, list) or len(candidate_keys) != int(row["optionCount"]):
            _fail(f"decisions.csv:{index}: candidate key count does not match optionCount")
        if row["sampled"] == "1":
            if row["supported"] != "1" or row["complete"] != "1" or len(candidate_keys) < 2:
                _fail(f"decisions.csv:{index}: unsupported/incomplete decision was sampled")
            if row["chosenKey"] not in candidate_keys:
                _fail(f"decisions.csv:{index}: sampled chosen option is absent")
            sampled_groups[key] = []

    branch_table_keys: set[tuple[int, str]] = set()
    branch_groups: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows["branches.csv"], 2):
        seed, decision_idx = int(row["sourceSeed"]), int(row["decisionIdx"])
        if seed not in allowed_seeds:
            _fail(f"branches.csv:{index}: seed is outside seedSpec")
        branch_key = (seed, row["branchId"])
        if branch_key in branch_table_keys:
            _fail(f"branches.csv:{index}: duplicate branch table entry")
        branch_table_keys.add(branch_key)
        if branch_key not in runout_by_key:
            _fail(f"branches.csv:{index}: branch has no runout outcome")
        decision_key = (seed, decision_idx)
        source_decision = source_decisions.get(decision_key)
        if source_decision is None or source_decision["sampled"] != "1":
            _fail(f"branches.csv:{index}: no sampled source decision join")
        candidates = json.loads(source_decision["candidateKeysJson"])
        if row["optionKey"] not in candidates:
            _fail(f"branches.csv:{index}: option is absent from source candidate set")
        branch_groups[decision_key].append(row)
        run = runout_by_key[branch_key]
        if (int(row["won"]) != int(run["finalWon"])
                or int(row["finalFloor"]) != int(run["finalFloor"])
                or int(row["finalHp"]) != int(run["finalHp"])):
            _fail(f"branches.csv:{index}: branch result disagrees with runout")

    for decision_key, group in sampled_groups.items():
        branches = branch_groups.get(decision_key, [])
        if not branches:
            _fail(f"sampled decision {decision_key} has no branches")
        if len(branches) > 6:
            _fail(f"sampled decision {decision_key} exceeds the six-option cap")
        if sum(int(row["chosen"]) for row in branches) != 1:
            _fail(f"sampled decision {decision_key} does not have exactly one chosen branch")
        chosen_key = source_decisions[decision_key]["chosenKey"]
        if not any(row["optionKey"] == chosen_key and row["chosen"] == "1" for row in branches):
            _fail(f"sampled decision {decision_key} chosen branch is missing")

    all_branch_keys = {(int(row["sourceSeed"]), row["branchId"]) for row in rows["branches.csv"]}
    non_source_keys = {key for key in runout_by_key if key[1] != "source"}
    if all_branch_keys != non_source_keys:
        _fail("runout branches and branch table do not join one-to-one")

    win_field = "won"
    combat_win_counts: Counter[tuple[int, str]] = Counter()
    for row in rows["combat.csv"]:
        key = (int(row["sourceSeed"]), row["branchId"])
        if row[win_field] == "1":
            combat_win_counts[key] += 1
    raw_win_counts = Counter((int(row["sourceSeed"]), row["branchId"])
                             for row in rows["win_raw.csv"])
    for key, run in runout_by_key.items():
        if run["trajectoryValid"] == "1" and raw_win_counts[key] != combat_win_counts[key]:
            _fail(f"{key}: WIN_RAW count {raw_win_counts[key]} != combat victory count {combat_win_counts[key]}")

    for table in ("map.csv", "win_raw.csv"):
        grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
        for row in rows[table]:
            grouped[(int(row["sourceSeed"]), row["branchId"])].append(int(row["rowIdx"]))
        for key, indices in grouped.items():
            if sorted(indices) != list(range(len(indices))):
                _fail(f"{table}: rowIdx is not contiguous for {key}")

    integrity = manifest.get("integrity", {})
    for field, actual in (("sourceMapRows", sum(r["branchId"] == "source" for r in rows["map.csv"])),
                          ("sourceWinRawRows", sum(r["branchId"] == "source" for r in rows["win_raw.csv"])),
                          ("branchMapRows", sum(r["branchId"] != "source" for r in rows["map.csv"])),
                          ("branchWinRawRows", sum(r["branchId"] != "source" for r in rows["win_raw.csv"])),
                          ("decisionRows", len(rows["decisions.csv"])),
                          ("branches", len(rows["branches.csv"]))):
        if integrity.get(field) != actual:
            _fail(f"manifest integrity.{field} does not match output rows")
    return {
        **sink_summary,
        "seeds": seed_count,
        "source_map_rows": integrity["sourceMapRows"],
        "source_win_raw_rows": integrity["sourceWinRawRows"],
        "branch_map_rows": integrity["branchMapRows"],
        "branch_win_raw_rows": integrity["branchWinRawRows"],
        "sampled_decisions": len(sampled_groups),
        "branches": len(rows["branches.csv"]),
        "valid_source_trajectories": integrity.get("validSources"),
    }


def compare_bundles(first: str | Path, second: str | Path, *, allow_sink_toggle: bool = False) -> dict:
    """Validate both bundles, then compare every non-timing output and manifest field."""
    validate_bundle(first)
    validate_bundle(second)
    manifests = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (first, second)]
    for manifest in manifests:
        for branch in manifest.get("branchRows", []):
            branch.pop("cpuSeconds", None)
        for summary in manifest.get("perType", {}).values():
            summary.pop("branchCpuSeconds", None)
            summary.pop("meanBranchCpuSeconds", None)
        if allow_sink_toggle:
            manifest.pop("decisionSink", None)
            manifest["integrity"].pop("decisionSinkRows", None)
            manifest["outputs"].pop("decision.csv", None)
    if manifests[0].get("outputs") != manifests[1].get("outputs"):
        different = sorted(key for key in set(manifests[0]["outputs"]) | set(manifests[1]["outputs"])
                           if manifests[0]["outputs"].get(key) != manifests[1]["outputs"].get(key))
        _fail("non-timing output differs: " + ", ".join(different))
    if manifests[0] != manifests[1]:
        different = sorted(key for key in set(manifests[0]) | set(manifests[1])
                           if manifests[0].get(key) != manifests[1].get(key))
        _fail("non-timing manifest differs: " + ", ".join(different))
    return {"identical_non_timing_outputs": sorted(manifests[0]["outputs"]),
            "seeds": manifests[0]["seedSpec"]["count"], "sink_toggle_allowed": allow_sink_toggle}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="vwin refresh .manifest.json")
    parser.add_argument("--compare", help="second bundle for exact non-timing comparison")
    parser.add_argument("--allow-sink-toggle", action="store_true",
                        help="compare legacy outputs when DECISION capture is toggled")
    args = parser.parse_args(argv)
    if args.allow_sink_toggle and not args.compare:
        parser.error("--allow-sink-toggle requires --compare")
    try:
        result = (compare_bundles(args.manifest, args.compare,
                                 allow_sink_toggle=args.allow_sink_toggle)
                  if args.compare else validate_bundle(args.manifest))
    except ContractError as exc:
        print(f"vwin refresh contract: FAIL: {exc}", file=sys.stderr)
        return 1
    print("vwin refresh contract: PASS " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
