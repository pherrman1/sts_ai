import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools.combat_transition_contract import (
        ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256, validate_corpus,
    )
except ModuleNotFoundError:  # direct invocation from the tools directory
    from combat_transition_contract import (
        ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256, validate_corpus,
    )

try:
    from tools.combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION,
    )
except ModuleNotFoundError:
    from combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION,
    )


def state():
    return {
        "curHp": 40, "maxHp": 80, "gold": 99, "potionCount": 0,
        "potionCapacity": 3, "potions": [0, 0, 0, 0, 0],
        "smokeBombUsed": False, "stolenGold": 0,
        "relics": [{"id": 1, "data": 2}], "relicBits": [1, 2, 3],
        "deck": [{"id": 10, "misc": 0, "upgraded": False}],
        "cardTypeCounts": [1, 0, 0, 0], "bottleIdxs": [-1, -1, -1],
        "upgradeableCount": 1, "transformableCount": 1,
        "combatRng": [{"counter": i, "seed0": i + 10, "seed1": i + 20} for i in range(6)],
    }


def teacher():
    search = {
        "simulation_budgets": [10000], "exploration_parameter": 25.0,
        "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
        "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
        "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
        "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
        "learned_visit_puct": False, "direct_learned_leaf": False, "adaptive": False,
    }
    environment = {
        "STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
        "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
        "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
    }
    return {
        "teacher_id": "teacher", "git_sha": "a" * 40,
        "executable_sha256": "b" * 64, "combat_backend": "native_silver",
        "rng_regime": "project_fair", "search_configuration": search,
        "environment": environment,
        "model_artifacts": [{"role": "floor", "path": "floor", "sha256": "c" * 64}],
    }


def predictor_input(floor=1):
    return {
        "schemaVersion": PREDICTOR_SCHEMA_VERSION,
        "fieldSchemaHash": FIELD_SCHEMA_HASH,
        "globals": {
            "characterClass": 0, "ascension": 0, "act": 1, "floor": floor,
            "curHp": 40, "maxHp": 80, "gold": 99, "encounter": 1,
            "roomClass": 4, "lastRoom": 1, "potionCount": 0,
            "potionCapacity": 3, "potionKeepValue": 4.0,
            "isBurningElite": False,
        },
        "cards": [{"cardId": 10, "misc": 0, "upgraded": False, "bottleBinding": -1}],
        "relics": [{"relicId": 1, "data": 2, "orderIndex": 0}],
        "potions": [{"slot": i, "potionId": 0} for i in range(5)],
    }


class TestCombatTransitionContract(unittest.TestCase):
    def make_bundle(self, root):
        rows = []
        for fight, outcome, valid, reason in ((0, 1, True, ""), (1, 2, False, "invalid_run")):
            rows.append({
                "schemaVersion": SCHEMA_VERSION,
                "rowSchemaVersion": ROW_SCHEMA_VERSION,
                "sourceSeed": 123,
                "fightIdx": fight,
                "act": 1,
                "floor": fight + 1,
                "roomClass": "NORMAL",
                "encounter": 1,
                "teacherId": "teacher",
                "runValid": valid,
                "quarantineReason": reason,
                "captureCount": 1,
                "captureStatus": "exactly_one",
                "predictorInput": predictor_input(fight + 1),
                "transition": {
                    "schemaVersion": SCHEMA_VERSION,
                    "combatOutcome": outcome,
                    "rawGameOutcome": 1,
                    "pre": state(),
                    "post": state(),
                },
            })
        data = root / "transitions.jsonl"
        data.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "rowSchemaVersion": ROW_SCHEMA_VERSION,
            "predictorInputSchemaVersion": PREDICTOR_SCHEMA_VERSION,
            "predictorInputFieldSchemaHash": FIELD_SCHEMA_HASH,
            "format": "jsonl",
            "producerGitSha": "a" * 40,
            "producerExecutableSha256": "b" * 64,
            "combatTeacher": teacher(),
            "seedSpec": {"start": 123, "count": 1},
            "csv": {"path": str(data), "sha256": sha256(data)},
            "integrity": {"requestedSeeds": 1, "completedSeeds": 1,
                           "quarantinedSeeds": 0, "rows": 2},
        }
        return manifest, data

    def test_validates_full_snapshot_and_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, _ = self.make_bundle(Path(directory))
            result = validate_corpus(manifest)
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["quarantinedRows"], 1)
            self.assertEqual(result["outcomes"], {0: 0, 1: 1, 2: 1})
            self.assertEqual(result["requestedSeeds"], 1)
            self.assertEqual(result["completedSeeds"], 1)
            self.assertEqual(result["quarantinedSeeds"], 0)

    def test_rejects_duplicate_or_missing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, data = self.make_bundle(Path(directory))
            rows = [json.loads(line) for line in data.read_text().splitlines()]
            rows[1]["fightIdx"] = 0
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            with self.assertRaisesRegex(ValueError, "duplicate sourceSeed/fightIdx"):
                validate_corpus(manifest)

            rows[1]["fightIdx"] = 1
            rows[0]["transition"] = None
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            with self.assertRaisesRegex(ValueError, "missing full transition snapshot"):
                validate_corpus(manifest)

    def test_rejects_non_raw_game_outcome_enum_value(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, data = self.make_bundle(Path(directory))
            rows = [json.loads(line) for line in data.read_text().splitlines()]
            rows[0]["transition"]["rawGameOutcome"] = 0
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            with self.assertRaisesRegex(ValueError, "invalid combat/raw GameOutcome"):
                validate_corpus(manifest)

    def test_accepts_explicit_missing_and_repeated_capture_quarantine(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, data = self.make_bundle(Path(directory))
            rows = [json.loads(line) for line in data.read_text().splitlines()]
            for row, count, status, reason in (
                (rows[0], 0, "missing", "missing_raw_capture"),
                (rows[1], 2, "repeated", "repeated_raw_capture"),
            ):
                row["runValid"] = False
                row["quarantineReason"] = reason
                row["captureCount"] = count
                row["captureStatus"] = status
                row["transition"] = None
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            result = validate_corpus(manifest)
            self.assertEqual(result["quarantinedRows"], 2)

    def test_rejects_seed_membership_and_source_accounting_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, data = self.make_bundle(Path(directory))
            rows = [json.loads(line) for line in data.read_text().splitlines()]

            rows[0]["sourceSeed"] = 124
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            with self.assertRaisesRegex(ValueError, "outside seedSpec"):
                validate_corpus(manifest)

            rows[0]["sourceSeed"] = 123
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            manifest["integrity"]["requestedSeeds"] = 2
            with self.assertRaisesRegex(ValueError, "requestedSeeds disagrees"):
                validate_corpus(manifest)

            manifest["integrity"]["requestedSeeds"] = 1
            manifest["integrity"]["completedSeeds"] = 0
            manifest["integrity"]["quarantinedSeeds"] = 1
            with self.assertRaisesRegex(ValueError, "completed source seed count"):
                validate_corpus(manifest)

            manifest["integrity"]["completedSeeds"] = 1
            manifest["integrity"]["quarantinedSeeds"] = 1
            with self.assertRaisesRegex(ValueError, "source seed accounting"):
                validate_corpus(manifest)

    def test_active_lizard_intervention_binds_shadow_rows_and_frozen_teacher(self):
        try:
            from tools.combat_transition_surrogate import _RELIC_IDS
        except ModuleNotFoundError:
            from combat_transition_surrogate import _RELIC_IDS
        with tempfile.TemporaryDirectory() as directory:
            manifest, data = self.make_bundle(Path(directory))
            rows = [json.loads(line) for line in data.read_text().splitlines()]
            for row in rows:
                row["teacherId"] = "silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77"
                row["predictorInput"]["relics"] = [
                    {"relicId": _RELIC_IDS["LIZARD_TAIL"], "data": 1, "orderIndex": 0}
                ]
                row["transition"]["pre"]["relics"] = [
                    {"id": _RELIC_IDS["LIZARD_TAIL"], "data": 1}
                ]
                row["transition"]["post"]["relics"] = [
                    {"id": _RELIC_IDS["LIZARD_TAIL"], "data": 1}
                ]
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            manifest["combatTeacher"]["teacher_id"] = "silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77"
            manifest["combatTeacher"]["git_sha"] = "d" * 40
            manifest["combatTeacher"]["executable_sha256"] = "e" * 64
            manifest["lizardIntervention"] = {
                "schema": "active_lizard_shadow_intervention_v1", "activeLizard": True,
                "baselineGitSha": "aa09f75e6be837f7f39a2e31dde234bfd2c2ef08", "collectorGitSha": "a" * 40,
                "collectorExecutableSha256": "b" * 64,
                "teacherId": manifest["combatTeacher"]["teacher_id"],
                "teacherGitSha": "d" * 40, "teacherExecutableSha256": "e" * 64,
                "teacherManifestSha256": "1" * 64,
                "teacherModelArtifacts": manifest["combatTeacher"]["model_artifacts"],
                "predictorInputFieldSchemaHash": FIELD_SCHEMA_HASH,
                "sourceSeedStart": 123, "sourceSeedCount": 1,
                "activeLizardRows": [
                    {"sourceSeed": 123, "fightIdx": i, "activeLizard": True}
                    for i in (0, 1)
                ],
                "sourceTrajectory": "untouched_normal_policy", "markOfBloomRows": "excluded",
            }
            result = validate_corpus(manifest)
            self.assertEqual(result["rows"], 2)

            rows[0]["predictorInput"]["relics"][0]["data"] = 0
            data.write_text("".join(json.dumps(row) + "\n" for row in rows))
            manifest["csv"]["sha256"] = sha256(data)
            with self.assertRaisesRegex(ValueError, "active Lizard predictor input"):
                validate_corpus(manifest)


class TestLearnedStopTeacherContract(unittest.TestCase):
    def validate(self, t):
        try:
            from tools.ooc_pipeline_contract import validate_teacher
        except ModuleNotFoundError:
            from ooc_pipeline_contract import validate_teacher
        validate_teacher(t)

    def learned(self):
        t = teacher()
        t["search_configuration"].update({"budget_policy": "learned_stop",
                                          "learned_stop_model": "gbt-770201c31f7b",
                                          "learned_stop_threshold": 0.0323})
        t["environment"].update({"STS_SILVER_EXACT_ROOT_BUDGETS": "0", "STS_SILVER_LEARNED_STOP": "1"})
        return t

    def test_exact_and_learned_stop_teachers_pass(self):
        self.validate(teacher())
        explicit = teacher(); explicit["search_configuration"]["budget_policy"] = "flat_exact"
        self.validate(explicit)
        self.validate(self.learned())

    def test_learned_stop_rejects_inconsistent_declarations(self):
        bad = self.learned(); bad["environment"]["STS_SILVER_EXACT_ROOT_BUDGETS"] = "1"
        with self.assertRaisesRegex(ValueError, "EXACT_ROOT_BUDGETS"): self.validate(bad)
        bad = self.learned(); del bad["environment"]["STS_SILVER_LEARNED_STOP"]
        with self.assertRaisesRegex(ValueError, "LEARNED_STOP"): self.validate(bad)
        bad = self.learned(); del bad["search_configuration"]["learned_stop_model"]
        with self.assertRaisesRegex(ValueError, "learned_stop_model"): self.validate(bad)
        bad = self.learned(); bad["search_configuration"]["budget_policy"] = "adaptive"
        with self.assertRaisesRegex(ValueError, "unknown"): self.validate(bad)

    def test_exact_teacher_rejects_learned_stop_environment(self):
        bad = teacher(); bad["environment"]["STS_SILVER_LEARNED_STOP"] = "1"
        with self.assertRaisesRegex(ValueError, "must not enable"): self.validate(bad)
        bad = teacher(); bad["environment"]["STS_SILVER_EXACT_ROOT_BUDGETS"] = "0"
        with self.assertRaisesRegex(ValueError, "EXACT_ROOT_BUDGETS"): self.validate(bad)


if __name__ == "__main__":
    unittest.main()
