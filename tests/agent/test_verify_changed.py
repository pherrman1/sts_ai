"""Path classification and test selection of tools/agent/verify_changed.py."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_changed", ROOT / "tools" / "agent" / "verify_changed.py")
vc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vc)


class TierTest(unittest.TestCase):
    def test_tier_of(self):
        self.assertEqual(vc.tier_of("docs/experiments/ledger-06.md"), "docs")
        self.assertEqual(vc.tier_of("README.md"), "docs")
        self.assertEqual(vc.tier_of("tools/az_bench/selfplay.py"), "python")
        self.assertEqual(vc.tier_of("tests/test_selfplay.py"), "python")
        self.assertEqual(vc.tier_of("tools/seed_guard.sh"), "python")
        for p in ("src/sim/search/AmberEncoder.cpp", "include/combat/BattleContext.h", "apps/one_combat.cpp",
                  "apps/az_bench/az_run_driver.cpp", "bindings/slaythespire.cpp", "tests/rng_fix_test.cpp",
                  "CMakeLists.txt", "CMakePresets.json", "cmake/GccPgo.cmake", "json", "pybind11"):
            self.assertEqual(vc.tier_of(p), "native", p)

    def test_affected_test_modules(self):
        mods = vc.affected_test_modules(["tools/az_bench/selfplay.py"])
        self.assertIn("tests/test_selfplay.py", mods)
        self.assertEqual(vc.affected_test_modules(["tests/agent/test_build.py"]), ["tests/agent/test_build.py"])
        self.assertEqual(vc.affected_test_modules(["docs/knowledge-base/README.md"]), [])


if __name__ == "__main__":
    unittest.main()
