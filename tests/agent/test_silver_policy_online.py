import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "silver_policy_online", ROOT / "tools" / "analyze_silver_policy_online.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SilverPolicyOnlineAnalyzerTest(unittest.TestCase):
    def test_paired_contrast_uses_seed_identity(self):
        left = {seed: {"seed": seed, "won": 0, "floor": 10, "hp": 2, "sec": 1.0}
                for seed in range(32)}
        right = {seed: {"seed": seed, "won": int(seed < 3), "floor": 11,
                        "hp": 4, "sec": 1.2} for seed in reversed(range(32))}
        indices = np.zeros((4, 32), dtype=int)
        result = MODULE.contrast(left, right, indices)
        self.assertEqual(result["win_delta_count"], 3)
        self.assertEqual(result["discordant"]["right_only"], 3)
        self.assertEqual(result["mean_floor_delta"], 1)
        self.assertAlmostEqual(result["cpu_ratio"], 1.2)

    def test_telemetry_sums_combats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arm.log"
            path.write_text(
                "[silver-combat] simulations=100 policy_inference_calls=2 "
                "policy_action_alignment_failures=0\n"
                "[silver-combat] simulations=120 policy_inference_calls=3 "
                "policy_action_alignment_failures=0\n", encoding="utf-8")
            totals = MODULE.load_telemetry(path)
            self.assertEqual(totals["simulations"], 220)
            self.assertEqual(totals["policy_inference_calls"], 5)


if __name__ == "__main__":
    unittest.main()
