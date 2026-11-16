"""Smoke test for tools/az_bench/e2e_bench.py: with a built az_bench_native module, a short CPU run (fake net and
the real AmberNet) evaluates positions and plays moves. Skipped when torch or the module is missing."""

import glob
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = sorted(glob.glob(os.path.join(ROOT, "build", "*", "az_bench_native*.so")))

try:
    import torch  # noqa: F401
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


@unittest.skipUnless(HAVE_TORCH and MODULES, "torch or the az_bench_native module (cmake target) missing")
class E2EBenchSmoke(unittest.TestCase):
    def run_bench(self, *extra):
        spec = importlib.util.spec_from_file_location("e2e_bench", os.path.join(ROOT, "tools", "az_bench", "e2e_bench.py"))
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "e2e.json")
            rc = bench.main(["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--dtype", "fp32",
                             "--workers", "2", "--games", "8", "--batch", "16", "--batchers", "1", "--seconds", "1.5",
                             "--warmup", "0.5", "--report", "1", "--out", out, *extra])
            self.assertEqual(rc, 0)
            return json.load(open(out))

    def test_fake_net(self):
        r = self.run_bench("--fake-net")
        self.assertGreater(r["positions_per_s"], 0)
        self.assertGreater(r["moves_per_s"], 0)

    def test_amber_net_cpu(self):
        r = self.run_bench("--net", "32x1")
        self.assertNotIn("errors", r)
        self.assertGreater(r["positions_per_s"], 0)


if __name__ == "__main__":
    unittest.main()
