"""Exercise the pilot's command boundary without executing any game seeds."""
import subprocess
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

    @staticmethod
    def guard(mode, count):
        return subprocess.run(
            [str(ROOT / "tools/seed_guard.sh"), "guard-only",
             "./build/one_combat", mode, count],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
