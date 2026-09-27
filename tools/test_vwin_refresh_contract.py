#!/usr/bin/env python3
"""Self-tests for the vwin-refresh bundle validator."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.vwin_refresh_contract import ContractError, OUTPUTS, validate_bundle


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
        decisionIdx=0, type="MAP", act=1, floor=1, screen=1, optionCount=len(option_keys),
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
            deviationIdx=1, decisionIdx=0, type="MAP", act=1, floor=1, screen=1,
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
        "branchParity": {"percent": 5, "checks": 0, "failures": 0},
        "stateFeatures": {"schema": "rich_state_v1", "header": FEATURE_HEADER,
                          "headerSha256": feature_sha, "count": 1017},
        "outputs": hashes,
        "integrity": {"completedSources": 1, "validSources": 1,
            "sourceMapRows": 1, "sourceWinRawRows": 1,
            "branchMapRows": len(option_keys), "branchWinRawRows": len(option_keys),
            "decisionRows": len(decisions), "branches": len(branches)},
    }
    manifest_path = Path(str(prefix) + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


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
