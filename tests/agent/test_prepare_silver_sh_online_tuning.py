import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "agent" / "prepare_silver_sh_online_tuning.py"


class SilverShManifestTest(unittest.TestCase):
    def run_tool(self, *extra: str) -> Path:
        (ROOT / "build").mkdir(exist_ok=True)
        output = ROOT / "build" / ("test-silver-sh-" + extra[0] + ".json")
        subprocess.run([
            sys.executable, str(SCRIPT), *extra,
            "--frozen-sha", "1" * 40,
            "--binary-remote", "checkouts/x/build/linux-gcc-release/one_combat",
            "--binary-sha256", "2" * 64,
            "--artifact", "models/v_rich_trees.txt:" + "3" * 64,
            "--artifact", "models/v_win_trees.txt:" + "4" * 64,
            "--artifact", "models/v_combat_7k_tuned.txt:" + "5" * 64,
            "--output", str(output),
        ], check=True, cwd=ROOT)
        return output

    def test_broad_is_full_predeclared_online_grid(self):
        payload = json.loads(self.run_tool("broad").read_text())
        self.assertEqual(payload["command"][2:6], ["3000", "16", "0", "933000"])
        self.assertEqual(len(payload["arms"]), 13)
        self.assertEqual(payload["common_env"]["OMP_NUM_THREADS"], "24")
        self.assertTrue(payload["clear_env"])
        self.assertEqual(payload["common_env"]["STS_VNET"], "0")
        self.assertEqual(payload["common_env"]["STS_POLICY"], "0")
        self.assertNotIn("STS_SILVER_SH_SHAPE", payload["arms"][0]["env"])

    def test_confirm_has_three_distinct_noncombined_arms(self):
        payload = json.loads(self.run_tool(
            "confirm", "--schedule", "gentle:cautious", "--budget", "3000").read_text())
        self.assertEqual(len(payload["arms"]), 3)
        c35 = payload["arms"][1]["env"]
        sh = payload["arms"][2]["env"]
        self.assertIn("STS_SILVER_ROOT_EXPLORATION", c35)
        self.assertNotIn("STS_SILVER_SH_SHAPE", c35)
        self.assertIn("STS_SILVER_SH_SHAPE", sh)
        self.assertNotIn("STS_SILVER_ROOT_EXPLORATION", sh)


if __name__ == "__main__":
    unittest.main()
