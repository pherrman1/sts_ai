"""Exercise the pilot's command boundary without executing any game seeds."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SemanticSeedGuardTests(unittest.TestCase):
    def test_pilot_modes_reject_invalid_or_oversized_counts(self):
        for mode in ("oocsemanticcapture", "oocsemanticeval"):
            for count in ("", "0", "-1", "nonsense", "17", "129"):
                with self.subTest(mode=mode, count=count):
                    result = self.guard(mode, count)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("requires 1..16", result.stderr)

    def test_pilot_modes_accept_small_cohorts(self):
        for mode in ("oocsemanticcapture", "oocsemanticeval"):
            for count in ("1", "8", "16"):
                with self.subTest(mode=mode, count=count):
                    result = self.guard(mode, count)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_silver_replay_counts_snapshot_roots_and_accepts_independent_seed(self):
        rows = [
            {"case_id": f"case-{index}", "benchmark_seed": index,
             "isolated_search_seed": index + 1000}
            for index in range(128)
        ]
        result = self.guard_silver_replay(rows)
        self.assertEqual(result.returncode, 0, result.stderr)

        result = self.guard_silver_replay(rows + [
            {"case_id": "case-128", "benchmark_seed": 128,
             "isolated_search_seed": 1128}
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requests 129 snapshot roots", result.stderr)

    def test_silver_replay_requires_snapshot_seed_and_bounds_search_seed(self):
        for row in (
            {"case_id": "missing", "isolated_search_seed": 7},
            {"case_id": "bad-override", "benchmark_seed": 7,
             "isolated_search_seed": 1 << 64},
            {"case_id": "bad-seed", "benchmark_seed": True},
            {"case_id": "negative-seed", "benchmark_seed": -1},
            {"case_id": "negative-override", "benchmark_seed": 7,
             "isolated_search_seed": -1},
        ):
            with self.subTest(row=row):
                result = self.guard_silver_replay([row])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SEED_GUARD", result.stderr)

    def test_silver_replay_accepts_uint64_boundaries(self):
        result = self.guard_silver_replay([
            {"case_id": "boundaries", "benchmark_seed": 0,
             "isolated_search_seed": (1 << 64) - 1}
        ])
        self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def guard(mode, count):
        return subprocess.run(
            [str(ROOT / "tools/seed_guard.sh"), "guard-only",
             "./build/one_combat", mode, count],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    @staticmethod
    def guard_silver_replay(rows):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshots = Path(temp_dir) / "snapshots.jsonl"
            snapshots.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            return subprocess.run(
                [str(ROOT / "tools/seed_guard.sh"), "guard-only",
                 "./build/silver_hard_combat_replay", str(snapshots), "1000",
                 "--first-decision-only"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )


if __name__ == "__main__":
    unittest.main()
