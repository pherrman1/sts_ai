#!/usr/bin/env python3
"""Focused fixtures for the battle-start run-out contract."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools import battle_start_runout_contract as contract
except ModuleNotFoundError:
    import battle_start_runout_contract as contract


class BattleStartRunoutContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = self.root / "leaf.txt"
        self.model.write_text("fixture model\n", encoding="utf-8")
        self.teacher = {
            "teacher_id": "silver-fixture",
            "git_sha": "a" * 40,
            "executable_sha256": "b" * 64,
            "combat_backend": "silver_uct",
            "rng_regime": "project_fair",
            "search_configuration": dict(contract.FROZEN_TEACHER["search_configuration"]),
            "environment": {
                "STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
                "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
                "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
                "STS_SILVER_TELEMETRY": "1",
            },
            "model_artifacts": [{
                "role": "combat_value_or_leaf", "path": str(self.model),
                "sha256": contract.sha256(self.model),
            }],
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_pair(self, *, escape=False, ambiguous=False, fatal=False):
        combat = self.root / "combat.csv"
        runout = self.root / "runout.csv"
        seeds = list(range(1000, 1010))
        with combat.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(contract.EXPECTED_HEADER)
            for index, seed in enumerate(seeds):
                won = int(index % 2 == 0)
                death = int(not won)
                escaped = int(escape and index == 0)
                amb = int(ambiguous and index == 3)
                valid = int(not escaped)
                if escaped:
                    won, death = 0, 0
                if amb:
                    won, death, valid = 0, 1, 1
                features = [0.0] * len(contract.RICH_NAMES)
                features[contract.RICH_NAMES.index("act")] = 1
                features[contract.RICH_NAMES.index("floor")] = 8 + index
                features[contract.RICH_NAMES.index("curHp")] = 50
                features[contract.RICH_NAMES.index("maxHp")] = 80
                labels = [won, death, escaped, 0, amb, valid, 50 if won else 0, 80,
                          0 if won else 20, 100, .625 if won else .001,
                          .001 if won else .2, 0 if escaped else (.625 if won else -.2),
                          "" if valid else "escape"]
                writer.writerow([seed, 0, 1, 8 + index, "NORMAL", "Cultist",
                                 self.teacher["teacher_id"], *features, *labels])
        with runout.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(contract.RUNOUT_HEADER)
            for index, seed in enumerate(seeds):
                outcome = "PLAYER_VICTORY" if index % 2 == 0 else "PLAYER_LOSS"
                health = int(fatal and index == 2)
                writer.writerow([seed, outcome if not health else "UNDECIDED",
                                 1 if outcome == "PLAYER_VICTORY" and not health else 0 if not health else -1,
                                 10, 50, 1, int(not health), int(not health), 1,
                                 int(escape and index == 0), self.teacher["teacher_id"], health, health])
        return combat, runout

    def manifest(self, combat, runout):
        shard = {
            "seed_spec": {"offset": 1000, "count": 10, "ascension": 0},
            "combat_csv": {"path": str(combat), "sha256": contract.sha256(combat)},
            "runout_csv": {"path": str(runout), "sha256": contract.sha256(runout)},
        }
        manifest = contract._manifest(self.teacher, "a" * 40, "b" * 64, [shard], {
            "machine": "fixture", "cpu": "fixture", "omp_num_threads": 16,
            "worker_count": 16, "command": "fixture",
        })
        # Compute the same compact aggregate integrity written by the builder.
        report = contract.validate_shard(shard, self.teacher, "a" * 40, "b" * 64)
        coverage = report["coverage"]
        manifest["integrity"] = {
            "requested_sources": 10, "completed_sources": 10,
            "trajectory_valid_sources": coverage["trajectory_valid_sources"],
            "final_wins": coverage["source_trajectories"]["final_wins"],
            "final_losses": coverage["source_trajectories"]["final_losses"],
            "combat_rows": len(report["combat_rows"]),
            "v_win_eligible_rows": coverage["v_win"]["eligible_battle_start_rows"],
            "v_win_unique_sources": coverage["v_win"]["unique_source_seeds"],
            "l_eligible_deaths": coverage["l"]["eligible_nonambiguous_deaths"],
            "l_unique_death_sources": coverage["l"]["unique_death_source_seeds"],
            "invalid_combat_rows": coverage["invalid_combat_rows"],
            "ambiguous_deaths": coverage["ambiguous_deaths"],
            "escaped_combat_rows": coverage["escaped_combat_rows"],
        }
        return manifest

    def test_wins_losses_escape_and_ambiguous_death_masks(self):
        combat, runout = self.write_pair(escape=True, ambiguous=True)
        result = contract.validate_manifest(self.manifest(combat, runout))
        coverage = result["coverage"]
        self.assertEqual(coverage["source_trajectories"]["final_wins"], 5)
        self.assertEqual(coverage["source_trajectories"]["final_losses"], 5)
        self.assertEqual(coverage["v_win"]["eligible_battle_start_rows"], 10)
        self.assertEqual(coverage["l"]["eligible_nonambiguous_deaths"], 4)
        self.assertEqual(coverage["invalid_combat_rows"], 1)
        self.assertEqual(coverage["ambiguous_deaths"], 1)
        self.assertEqual(coverage["escaped_combat_rows"], 1)

    def test_fatal_health_failure_is_rejected(self):
        combat, runout = self.write_pair(fatal=True)
        with self.assertRaisesRegex(ValueError, "fatal simulator-health"):
            contract.validate_manifest(self.manifest(combat, runout))

    def test_missing_duplicate_identity_and_hash_corruption_fail_closed(self):
        combat, runout = self.write_pair()
        manifest = self.manifest(combat, runout)
        broken = json.loads(json.dumps(manifest))
        broken["shards"][0]["runout_csv"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            contract.validate_manifest(broken)
        with runout.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        rows.append(rows[-1])
        duplicate = self.root / "duplicate.csv"
        with duplicate.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        broken = self.manifest(combat, runout)
        broken["shards"][0]["runout_csv"] = {
            "path": str(duplicate), "sha256": contract.sha256(duplicate)
        }
        with self.assertRaisesRegex(ValueError, "duplicate source run identity"):
            contract.validate_manifest(broken)


if __name__ == "__main__":
    unittest.main()
