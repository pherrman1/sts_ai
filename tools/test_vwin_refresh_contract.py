#!/usr/bin/env python3
"""Self-tests for the vwin-refresh bundle validator."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import shutil
import unittest
from pathlib import Path

from tools.vwin_refresh_contract import (ContractError, OUTPUTS, validate_bundle,
                                         DECISION_SINK_PREFIX, DECISION_SINK_TAIL, compare_bundles)


FEATURES = [f"feature_{index}" for index in range(1017)]
FEATURE_HEADER = ",".join(FEATURES)
SEED = 13000000


def _write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _row(header: list[str], **values: str) -> dict[str, str]:
    return {field: str(values.get(field, "0")) for field in header}


def _make_bundle(directory: Path, option_keys: list[str] | None = None) -> Path:
    option_keys = option_keys or ["a", "b"]
    prefix = directory / "pilot"
    feature_sha = hashlib.sha256(FEATURE_HEADER.encode()).hexdigest()
    map_header = ["sourceSeed", "branchId", "deviationIdx", "rowIdx", "act", "floor",
                  "mapX", "mapY", "teacherId"] + FEATURES
    raw_tail = ["roomClass", "actBoss", "encounter", "preHp", "preMaxHp", "prePotions",
                "preGold", "postAfterBattleHp"]
    raw_header = map_header + raw_tail
    decision_header = ["sourceSeed", "branchId", "deviationIdx", "decisionIdx", "type",
        "act", "floor", "screen", "optionCount", "chosenKey", "supported", "complete",
        "sampled", "candidateKeysJson", "error"]
    branch_header = ["sourceSeed", "decisionIdx", "type", "optionKey", "chosen", "branchId",
        "won", "finalFloor", "finalHp", "valid"]
    combat_prefix = ["sourceSeed", "branchId", "deviationIdx", "fightIdx", "act", "floor",
        "roomClass", "encounter", "teacherId"]
    label_fields = ["won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous",
        "labelValid", "terminalCombatHp", "terminalCombatMaxHp", "terminalNonMinionCurHp",
        "terminalNonMinionMaxHp", "winHpFrac", "lossRemainingFrac", "signedOutcome",
        "quarantineReason"]
    combat_header = combat_prefix + FEATURES + label_fields
    runout_header = ["sourceSeed", "branchId", "deviationIdx", "finalOutcome", "finalWon",
        "finalFloor", "finalHp", "fightCount", "trajectoryComplete", "trajectoryValid",
        "combatRows", "invalidCombatRows", "teacherId", "simulatorHealthFailures",
        "fatalFailure", "branchParity"]

    source_map = _row(map_header, sourceSeed=SEED, branchId="source", deviationIdx=0,
                      rowIdx=0, act=1, floor=1, mapX=0, mapY=0, teacherId="teacher")
    source_raw = _row(raw_header, sourceSeed=SEED, branchId="source", deviationIdx=0,
        rowIdx=0, act=1, floor=1, mapX=0, mapY=0, teacherId="teacher", roomClass="BOSS",
        actBoss=1, encounter="THE_GUARDIAN", preHp=70, preMaxHp=80, prePotions=1,
        preGold=100, postAfterBattleHp=65)
    source_keys = json.dumps(option_keys, separators=(",", ":"))
    decisions = [_row(decision_header, sourceSeed=SEED, branchId="source", deviationIdx=0,
        decisionIdx=0, type="MAP", act=1, floor=1, screen=5, optionCount=len(option_keys),
        chosenKey=option_keys[0], supported=1, complete=1, sampled=1,
        candidateKeysJson=source_keys, error="")]
    branches = []
    runouts = []
    map_rows = [source_map]
    raw_rows = [source_raw]
    combat_rows = []
    branch_ids = ["source"]
    for index, option in enumerate(option_keys):
        chosen = index == 0
        branch_id = f"s{SEED}-d0-{option}"
        branch_ids.append(branch_id)
        branches.append(_row(branch_header, sourceSeed=SEED, decisionIdx=0, type="MAP",
            optionKey=option, chosen=int(chosen), branchId=branch_id, won=1, finalFloor=50,
            finalHp=65, valid=1))
        decisions.append(_row(decision_header, sourceSeed=SEED, branchId=branch_id,
            deviationIdx=1, decisionIdx=0, type="MAP", act=1, floor=1, screen=5,
            optionCount=len(option_keys), chosenKey=option, supported=1, complete=1,
            sampled=0, candidateKeysJson=source_keys, error=""))
        map_rows.append(_row(map_header, sourceSeed=SEED, branchId=branch_id,
            deviationIdx=1, rowIdx=0, act=1, floor=1, mapX=0, mapY=0, teacherId="teacher"))
        raw_rows.append(_row(raw_header, sourceSeed=SEED, branchId=branch_id,
            deviationIdx=1, rowIdx=0, act=1, floor=1, mapX=0, mapY=0, teacherId="teacher",
            roomClass="BOSS", actBoss=1, encounter="THE_GUARDIAN", preHp=70,
            preMaxHp=80, prePotions=1, preGold=100, postAfterBattleHp=65))
    for index, branch_id in enumerate(branch_ids):
        parity = "NA" if branch_id == "source" else "PASS" if index == 1 else "NA"
        runouts.append(_row(runout_header, sourceSeed=SEED, branchId=branch_id,
            deviationIdx=0 if branch_id == "source" else 1, finalOutcome="PLAYER_VICTORY",
            finalWon=1, finalFloor=50, finalHp=65, fightCount=1, trajectoryComplete=1,
            trajectoryValid=1, combatRows=1, invalidCombatRows=0, teacherId="teacher",
            simulatorHealthFailures=0, fatalFailure=0, branchParity=parity))
        combat = _row(combat_header, sourceSeed=SEED, branchId=branch_id,
            deviationIdx=0 if branch_id == "source" else 1, fightIdx=0, act=1, floor=17,
            roomClass="BOSS", encounter="THE_GUARDIAN", teacherId="teacher", won=1,
            labelValid=1, signedOutcome=0.8, quarantineReason="")
        combat_rows.append(combat)

    data = {
        "map.csv": (map_header, map_rows),
        "win_raw.csv": (raw_header, raw_rows),
        "decisions.csv": (decision_header, decisions),
        "branches.csv": (branch_header, branches),
        "combat.csv": (combat_header, combat_rows),
        "runout.csv": (runout_header, runouts),
    }
    hashes = {}
    for name, (header, rows) in data.items():
        suffix = OUTPUTS[name]
        path = Path(str(prefix) + suffix)
        _write_csv(path, header, rows)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schemaVersion": "vwin_refresh_334_v1",
        "producerGitSha": "c" * 40,
        "producerExecutableSha256": "a" * 64,
        "teacherManifestSha256": "b" * 64,
        "teacherId": "teacher",
        "seedSpec": {"start": SEED, "count": 1, "ascension": 0},
        "split": {"rule": "source_seed_sha256_prefix_v1",
                  "domain": "vwin-refresh-334-v1:{seed}", "prefixBytes": 4,
                  "trainLt": 0.70, "validationLt": 0.85,
                  "branchesInheritSourceSeed": True},
        "branchParity": {"percent": 100, "checks": 1, "failures": 0,
            "rule": "sha256_bucket_decision_v1",
            "domain": "vwin-branch-parity-334-v1:{seed}:{decisionIdx}"},
        "branchRows": [{"sourceSeed": SEED, "decisionIdx": 0, "type": "MAP",
            "optionKey": row["optionKey"], "chosen": row["chosen"] == "1",
            "branchId": row["branchId"], "trajectoryValid": True,
            "chosenReplayParity": True if row["chosen"] == "1" else None,
            "cpuSeconds": 1.0} for row in branches],
        "stateFeatures": {"schema": "rich_state_v1", "header": FEATURE_HEADER,
                          "headerSha256": feature_sha, "count": 1017},
        "outputs": hashes,
        "integrity": {"completedSources": 1, "validSources": 1,
            "sourceMapRows": 1, "sourceWinRawRows": 1,
            "branchMapRows": len(option_keys), "branchWinRawRows": len(option_keys),
            "decisionRows": len(decisions), "branches": len(branches),
            "chosenReplayChecks": 1, "chosenReplayFailures": 0},
    }
    manifest_path = Path(str(prefix) + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _add_decision_sink(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    prefix = str(manifest_path)[:-len(".manifest.json")]
    with Path(prefix + ".runout.csv").open(newline="") as stream:
        runouts = list(csv.DictReader(stream))
    with Path(prefix + ".decisions.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        legacy_header, legacy = reader.fieldnames, list(reader)
    keys = ["ooc:v1:effect=26:source=5:event=8:option=0",
            "ooc:v1:effect=26:source=5:event=8:option=1"]
    header = DECISION_SINK_PREFIX + FEATURES + DECISION_SINK_TAIL
    sink_rows, trajectories = [], []
    by_screen = {"source": {}, "branch": {}}
    for run in runouts:
        branch = run["branchId"]
        legacy.append(_row(legacy_header, sourceSeed=SEED, branchId=branch,
            deviationIdx=run["deviationIdx"], decisionIdx=1, type="EVENT", act=1, floor=2,
            screen=1, optionCount=2, chosenKey=keys[0], supported=1, complete=1, sampled=0,
            candidateKeysJson=json.dumps(keys), error=""))
        sink_rows.append(_row(header, sourceSeed=SEED, branchId=branch,
            deviationIdx=run["deviationIdx"], rowIdx=0, decisionIdx=1, act=1, floor=2,
            screen="event", teacherId="teacher", won=run["finalWon"],
            screenContents=json.dumps({"screen": "event", "screenState": 1,
                                       "eventId": 8, "optionIds": [0, 1]}),
            candidates=json.dumps({"optionKeys": keys, "chosenKey": keys[0],
                                   "supported": True, "complete": True})))
        trajectories.append({"sourceSeed": SEED, "branchId": branch,
            "deviationIdx": int(run["deviationIdx"]), "rows": 1,
            "decisionLog": [{"rowIdx": 0, "decisionIdx": 1, "screen": "event", "optionCount": 2},
                            {"rowIdx": -1, "decisionIdx": -1, "screen": "rewards", "optionCount": 1}]})
        kind = "source" if branch == "source" else "branch"
        by_screen[kind]["event"] = by_screen[kind].get("event", 0) + 1
    _write_csv(Path(prefix + ".decisions.csv"), legacy_header, legacy)
    sink_path = Path(prefix + ".decision.csv")
    _write_csv(sink_path, header, sink_rows)
    size = sink_path.stat().st_size
    manifest["decisionSink"] = {"schema": "vwin_decision_334_v1", "enabled": True,
        "rows": len(sink_rows), "trajectories": trajectories, "byScreen": by_screen,
        "bytes": size, "bytesPerRow": size / len(sink_rows), "projectedA2Bytes": size * 4096,
        "projectionSourceSeeds": 1, "projectionTargetSeeds": 4096}
    manifest["integrity"]["decisionRows"] = len(legacy)
    manifest["integrity"]["decisionSinkRows"] = len(sink_rows)
    for name in ("decisions.csv", "decision.csv"):
        manifest["outputs"][name] = hashlib.sha256(Path(prefix + "." + name).read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


class VwinRefreshContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.manifest = _make_bundle(self.directory)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rewrite_hash(self, name: str) -> None:
        manifest = json.loads(self.manifest.read_text())
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS[name])
        manifest["outputs"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(manifest))

    def test_valid_bundle(self) -> None:
        result = validate_bundle(self.manifest)
        self.assertEqual(result["seeds"], 1)
        self.assertEqual(result["branches"], 2)
        self.assertEqual(result["sampled_decisions"], 1)

    def _mutate_table(self, name, change):
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS[name])
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        change(rows)
        _write_csv(path, header, rows)
        self._rewrite_hash(name)

    def _mutate_manifest(self, change):
        manifest = json.loads(self.manifest.read_text())
        change(manifest)
        self.manifest.write_text(json.dumps(manifest))

    def test_required_replay_na_with_zero_checks_rejected(self):
        self._mutate_table("runout.csv", lambda rows: rows[1].update(branchParity="NA"))
        def change(m):
            m["branchParity"]["checks"] = 0
            m["integrity"]["chosenReplayChecks"] = 0
            m["branchRows"][0]["chosenReplayParity"] = None
        self._mutate_manifest(change)
        with self.assertRaisesRegex(ContractError, "required chosen replay must be PASS"):
            validate_bundle(self.manifest)

    def test_replay_fail_with_zero_failures_rejected(self):
        self._mutate_table("runout.csv", lambda rows: rows[1].update(branchParity="FAIL"))
        self._mutate_table("branches.csv", lambda rows: rows[0].update(valid="0"))
        self._mutate_manifest(lambda m: m["branchRows"][0].update(chosenReplayParity=False))
        with self.assertRaisesRegex(ContractError, "failures disagrees"):
            validate_bundle(self.manifest)
        def reported_failures(m):
            m["branchParity"]["failures"] = 1
            m["integrity"]["chosenReplayFailures"] = 1
        self._mutate_manifest(reported_failures)
        with self.assertRaisesRegex(ContractError, "bundle contains FAIL"):
            validate_bundle(self.manifest)

    def test_replay_summary_contradictions_rejected(self):
        cases = [
            (lambda m: m["branchRows"][0].update(chosenReplayParity=False), "chosenReplayParity"),
            (lambda m: m["branchRows"][1].update(chosenReplayParity=True), "chosenReplayParity"),
            (lambda m: m["branchRows"].pop(), "one-to-one"),
            (lambda m: m["branchRows"].append(m["branchRows"][0]), "duplicate identity"),
            (lambda m: m["branchParity"].update(checks=0), "checks disagrees"),
            (lambda m: m["integrity"].update(chosenReplayChecks=0), "chosenReplayChecks disagrees"),
            (lambda m: m["integrity"].update(chosenReplayFailures=1), "chosenReplayFailures disagrees"),
            (lambda m: m["branchParity"].update(domain="wrong"), "parity contract"),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                self.manifest = _make_bundle(self.directory)
                self._mutate_manifest(change)
                with self.assertRaisesRegex(ContractError, message):
                    validate_bundle(self.manifest)

    def test_parity_hash_bucket_boundary(self):
        bucket = int(hashlib.sha256(f"vwin-branch-parity-334-v1:{SEED}:0".encode()).hexdigest()[:8], 16) % 100
        for percent in (0, bucket, bucket + 1, 100):
            with self.subTest(percent=percent):
                self.manifest = _make_bundle(self.directory)
                required = bucket < percent
                self._mutate_table("runout.csv", lambda rows: rows[1].update(
                    branchParity="PASS" if required else "NA"))
                def change(m):
                    m["branchParity"].update(percent=percent, checks=int(required))
                    m["integrity"]["chosenReplayChecks"] = int(required)
                    m["branchRows"][0]["chosenReplayParity"] = True if required else None
                self._mutate_manifest(change)
                self.assertEqual(validate_bundle(self.manifest)["chosen_replay_checks"], int(required))

    def test_inapplicable_branch_or_source_parity_rejected(self):
        for index, message in ((0, "source branchParity"), (2, "inapplicable chosen replay")):
            with self.subTest(index=index):
                self.manifest = _make_bundle(self.directory)
                self._mutate_table("runout.csv", lambda rows: rows[index].update(branchParity="PASS"))
                with self.assertRaisesRegex(ContractError, message):
                    validate_bundle(self.manifest)

    def test_outcome_label_mapping_rejected(self):
        for outcome, wrong in (("PLAYER_VICTORY", "0"), ("PLAYER_LOSS", "1"), ("UNDECIDED", "0")):
            with self.subTest(outcome=outcome):
                self.manifest = _make_bundle(self.directory)
                self._mutate_table("runout.csv", lambda rows: rows[0].update(finalOutcome=outcome, finalWon=wrong))
                with self.assertRaisesRegex(ContractError, "finalWon disagrees"):
                    validate_bundle(self.manifest)

    def test_source_totals_recomputed(self):
        for field in ("completedSources", "validSources"):
            with self.subTest(field=field):
                self.manifest = _make_bundle(self.directory)
                self._mutate_manifest(lambda m: m["integrity"].update({field: 999}))
                with self.assertRaisesRegex(ContractError, "integrity." + field):
                    validate_bundle(self.manifest)

    def test_trajectory_flags_reconciled(self):
        for change in ({"trajectoryComplete": "0"}, {"trajectoryValid": "0"},
                       {"simulatorHealthFailures": "1"}, {"fatalFailure": "1"},
                       {"finalOutcome": "UNDECIDED", "finalWon": "-1"}):
            with self.subTest(change=change):
                self.manifest = _make_bundle(self.directory)
                self._mutate_table("runout.csv", lambda rows: rows[0].update(change))
                with self.assertRaisesRegex(ContractError, "trajectory flags contradict"):
                    validate_bundle(self.manifest)

    def test_invalid_sources_exempt_replay_and_chosen_branch_validity(self):
        for outcome, won, complete, fatal, health in (
                ("UNDECIDED", "-1", "0", "0", "0"),
                ("UNDECIDED", "-1", "0", "1", "1"),
                ("PLAYER_LOSS", "0", "1", "0", "1")):
            with self.subTest(outcome=outcome, fatal=fatal):
                self.manifest = _make_bundle(self.directory)
                def runouts(rows):
                    rows[0].update(finalOutcome=outcome, finalWon=won, trajectoryComplete=complete,
                                   trajectoryValid="0", fatalFailure=fatal, simulatorHealthFailures=health)
                    rows[1]["branchParity"] = "NA"
                self._mutate_table("runout.csv", runouts)
                self._mutate_table("branches.csv", lambda rows: rows[0].update(valid="0"))
                def change(m):
                    m["branchParity"]["checks"] = 0
                    m["integrity"].update(chosenReplayChecks=0, validSources=0, completedSources=int(complete))
                    m["branchRows"][0]["chosenReplayParity"] = None
                self._mutate_manifest(change)
                self.assertEqual(validate_bundle(self.manifest)["valid_source_trajectories"], 0)
                self._mutate_table("branches.csv", lambda rows: rows[0].update(valid="1"))
                with self.assertRaisesRegex(ContractError, "branch valid disagrees"):
                    validate_bundle(self.manifest)

    def _mutate_sink(self, change) -> None:
        _add_decision_sink(self.manifest)
        path = Path(str(self.manifest)[:-len(".manifest.json")] + ".decision.csv")
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        change(rows)
        _write_csv(path, header, rows)
        self._rewrite_hash("decision.csv")

    def test_decision_sink_valid(self) -> None:
        _add_decision_sink(self.manifest)
        result = validate_bundle(self.manifest)
        self.assertEqual(result["decision_sink_rows"], 3)
        self.assertEqual(result["decision_rows_by_screen"],
                         {"source": {"event": 1}, "branch": {"event": 2}})
        self.assertGreater(result["decision_projected_a2_bytes"], 0)

    def _add_capture_error(self, error: str, supported: bool, complete: bool,
                           option_count: int) -> None:
        _add_decision_sink(self.manifest)
        manifest = json.loads(self.manifest.read_text())
        trajectory = manifest["decisionSink"]["trajectories"][0]
        trajectory["decisionLog"].append({
            "rowIdx": -1, "decisionIdx": 2, "screen": "event", "optionCount": option_count,
            "supported": supported, "complete": complete, "error": error})
        path = Path(str(self.manifest)[:-len(".manifest.json")] + ".decisions.csv")
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        rows.append(_row(header, sourceSeed=SEED, branchId=trajectory["branchId"],
            deviationIdx=trajectory["deviationIdx"], decisionIdx=2, type="EVENT", act=1, floor=2,
            screen=1, optionCount=option_count, chosenKey="", supported=int(supported),
            complete=int(complete), sampled=0, error=error,
            candidateKeysJson=json.dumps([f"ooc:v1:skip-fixture:{i}" for i in range(option_count)])))
        _write_csv(path, header, rows)
        manifest["integrity"]["decisionRows"] = len(rows)
        self.manifest.write_text(json.dumps(manifest))
        self._rewrite_hash("decisions.csv")

    def test_decision_sink_capture_errors_are_reported(self) -> None:
        for error, supported, complete, count in (
            ("semantic_option_enumeration_unsupported_or_incomplete", False, False, 0),
            ("semantic_option_enumeration_unsupported_or_incomplete", True, False, 1),
            ("semantic_option_enumeration_unsupported_or_incomplete", True, False, 2),
            ("chosen_primitive_binding_unresolved", True, True, 2),
            ("compound_selector_semantic_binding_unresolved", True, True, 2),
        ):
            with self.subTest(error=error, count=count):
                self.manifest = _make_bundle(self.directory)
                self._add_capture_error(error, supported, complete, count)
                result = validate_bundle(self.manifest)
                self.assertEqual(result["decision_sink_rows"], 3)
                self.assertEqual(result["decision_capture_errors"],
                                 {"source": {"event": 1}, "branch": {}})

    def test_decision_sink_capture_only_error(self) -> None:
        _add_decision_sink(self.manifest)
        manifest = json.loads(self.manifest.read_text())
        manifest["decisionSink"]["trajectories"][0]["decisionLog"].append({
            "rowIdx": -1, "decisionIdx": -1, "screen": "selector", "optionCount": 2,
            "supported": True, "complete": True, "error": "chosen_primitive_binding_unresolved"})
        self.manifest.write_text(json.dumps(manifest))
        result = validate_bundle(self.manifest)
        self.assertEqual(result["decision_capture_errors"]["source"], {"selector": 1})

    def test_decision_sink_capture_error_cannot_hide_resolved_legacy(self) -> None:
        self._add_capture_error("chosen_primitive_binding_unresolved", True, True, 2)
        path = Path(str(self.manifest)[:-len(".manifest.json")] + ".decisions.csv")
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        rows[-1]["chosenKey"] = json.loads(rows[-1]["candidateKeysJson"])[0]
        _write_csv(path, header, rows)
        self._rewrite_hash("decisions.csv")
        with self.assertRaisesRegex(ContractError, "cannot omit a resolved legacy"):
            validate_bundle(self.manifest)

    def test_decision_sink_capture_error_contract_rejected(self) -> None:
        for mutation, message in (
            ({"rowIdx": 3}, "no sink row"),
            ({"error": ""}, "rowIdx is not contiguous"),
            ({"error": "invented"}, "unknown capture error"),
            ({"decisionIdx": 99}, "missing or mismatched legacy join"),
            ({"complete": False}, "invalid candidate status"),
        ):
            with self.subTest(mutation=mutation):
                self.manifest = _make_bundle(self.directory)
                self._add_capture_error("chosen_primitive_binding_unresolved", True, True, 2)
                manifest = json.loads(self.manifest.read_text())
                manifest["decisionSink"]["trajectories"][0]["decisionLog"][-1].update(mutation)
                self.manifest.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ContractError, message):
                    validate_bundle(self.manifest)

    def test_decision_sink_json_rejected(self) -> None:
        self._mutate_sink(lambda rows: rows[0].update(screenContents="{"))
        with self.assertRaisesRegex(ContractError, "invalid JSON"):
            validate_bundle(self.manifest)

    def test_decision_sink_screen_mismatch_rejected(self) -> None:
        self._mutate_sink(lambda rows: rows[0].update(screenContents=json.dumps(
            {"screen": "shop", "screenState": 8})))
        with self.assertRaisesRegex(ContractError, "screen type"):
            validate_bundle(self.manifest)

    def test_decision_sink_absent_chosen_rejected(self) -> None:
        def change(rows):
            candidates = json.loads(rows[0]["candidates"])
            candidates["chosenKey"] = "absent"
            rows[0]["candidates"] = json.dumps(candidates)
        self._mutate_sink(change)
        with self.assertRaisesRegex(ContractError, "chosen key is absent"):
            validate_bundle(self.manifest)

    def test_decision_sink_singleton_rejected(self) -> None:
        def change(rows):
            candidates = json.loads(rows[0]["candidates"])
            candidates["optionKeys"] = candidates["optionKeys"][:1]
            rows[0]["candidates"] = json.dumps(candidates)
        self._mutate_sink(change)
        with self.assertRaisesRegex(ContractError, "more than one"):
            validate_bundle(self.manifest)

    def test_decision_sink_missing_row_rejected(self) -> None:
        self._mutate_sink(lambda rows: rows.pop())
        with self.assertRaisesRegex(ContractError, "row counts do not match"):
            validate_bundle(self.manifest)

    def test_decision_sink_outcome_mismatch_rejected(self) -> None:
        self._mutate_sink(lambda rows: rows[0].update(won="0"))
        with self.assertRaisesRegex(ContractError, "won disagrees"):
            validate_bundle(self.manifest)

    def test_decision_sink_missing_legacy_join_rejected(self) -> None:
        self._mutate_sink(lambda rows: rows[0].update(decisionIdx="99"))
        with self.assertRaisesRegex(ContractError, "decision join"):
            validate_bundle(self.manifest)

    def test_decision_sink_header_rejected(self) -> None:
        _add_decision_sink(self.manifest)
        path = Path(str(self.manifest)[:-len(".manifest.json")] + ".decision.csv")
        path.write_text(path.read_text().replace("screenContents", "contents", 1))
        self._rewrite_hash("decision.csv")
        with self.assertRaisesRegex(ContractError, "header mismatch"):
            validate_bundle(self.manifest)

    def test_comparison_ignores_only_timing(self) -> None:
        _add_decision_sink(self.manifest)
        other_dir = self.directory / "repeat"
        other_dir.mkdir()
        for path in self.directory.glob("pilot.*"):
            shutil.copyfile(path, other_dir / path.name)
        second = other_dir / self.manifest.name
        changed = json.loads(second.read_text())
        changed["branchRows"][0]["cpuSeconds"] = 2.0
        second.write_text(json.dumps(changed))
        original = json.loads(self.manifest.read_text())
        original["branchRows"][0]["cpuSeconds"] = 1.0
        self.manifest.write_text(json.dumps(original))
        self.assertIn("decision.csv", compare_bundles(self.manifest, second)["identical_non_timing_outputs"])
        changed["producerGitSha"] = "d" * 40
        second.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ContractError, "non-timing manifest differs"):
            compare_bundles(self.manifest, second)

    def test_comparison_accepts_sink_toggle_only_explicitly(self) -> None:
        _add_decision_sink(self.manifest)
        other_dir = self.directory / "without"
        other_dir.mkdir()
        for path in self.directory.glob("pilot.*"):
            shutil.copyfile(path, other_dir / path.name)
        second = other_dir / self.manifest.name
        changed = json.loads(second.read_text())
        changed.pop("decisionSink")
        changed["outputs"].pop("decision.csv")
        changed["integrity"].pop("decisionSinkRows")
        second.write_text(json.dumps(changed))
        result = compare_bundles(self.manifest, second, allow_sink_toggle=True)
        self.assertEqual(len(result["identical_non_timing_outputs"]), 6)
        with self.assertRaisesRegex(ContractError, "non-timing output differs"):
            compare_bundles(self.manifest, second)

    def test_hash_mismatch_is_rejected(self) -> None:
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS["map.csv"])
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ContractError, "SHA-256 mismatch"):
            validate_bundle(self.manifest)

    def test_missing_chosen_branch_is_rejected(self) -> None:
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS["branches.csv"])
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        _write_csv(path, list(rows[0]), [row for row in rows if row["chosen"] != "1"])
        self._rewrite_hash("branches.csv")
        with self.assertRaisesRegex(ContractError, "exactly one chosen branch"):
            validate_bundle(self.manifest)

    def test_win_raw_count_mismatch_is_rejected(self) -> None:
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS["win_raw.csv"])
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        _write_csv(path, list(rows[0]), rows[:-1])
        self._rewrite_hash("win_raw.csv")
        with self.assertRaisesRegex(ContractError, "WIN_RAW count"):
            validate_bundle(self.manifest)

    def test_nonfinite_feature_is_rejected(self) -> None:
        path = Path(str(self.manifest)[:-len(".manifest.json")] + OUTPUTS["map.csv"])
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0][FEATURES[0]] = "nan"
        _write_csv(path, list(rows[0]), rows)
        self._rewrite_hash("map.csv")
        with self.assertRaisesRegex(ContractError, "non-finite"):
            validate_bundle(self.manifest)

    def test_option_cap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as nested:
            over_cap = _make_bundle(Path(nested), list("abcdefg"))
            with self.assertRaisesRegex(ContractError, "six-option cap"):
                validate_bundle(over_cap)

    def test_split_contract_mismatch_is_rejected(self) -> None:
        manifest = json.loads(self.manifest.read_text())
        manifest["split"]["trainLt"] = 0.75
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ContractError, "split contract mismatch"):
            validate_bundle(self.manifest)


if __name__ == "__main__":
    unittest.main()
