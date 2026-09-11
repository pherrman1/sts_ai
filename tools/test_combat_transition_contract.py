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
        "STS_SILVER_TELEMETRY": "1",
    }
    return {
        "teacher_id": "teacher", "git_sha": "a" * 40,
        "executable_sha256": "b" * 64, "combat_backend": "silver_uct",
        "rng_regime": "project_fair", "search_configuration": search,
        "environment": environment,
        "model_artifacts": [{"role": "floor", "path": "floor", "sha256": "c" * 64}],
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


if __name__ == "__main__":
    unittest.main()
