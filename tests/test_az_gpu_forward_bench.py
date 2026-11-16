"""Smoke test for tools/az_bench/gpu_forward_bench.py: a tiny CPU run writes one finite measurement per (net, batch)."""

import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import torch  # noqa: F401
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


@unittest.skipUnless(HAVE_TORCH, "torch not installed")
class GpuForwardBenchSmoke(unittest.TestCase):
    def test_cpu_fp32(self):
        spec = importlib.util.spec_from_file_location("gpu_forward_bench",
                                                      os.path.join(ROOT, "tools", "az_bench", "gpu_forward_bench.py"))
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "b.json")
            rc = bench.main(["--device", "cpu", "--dtype", "fp32", "--arch", "combat", "--nets", "32x1,64x4",
                             "--batches", "4,16",
                             "--warmup", "1", "--iters", "2", "--out", out])
            self.assertEqual(rc, 0)
            info = json.load(open(out))
        rows = info["results"]
        self.assertEqual([(r["net"], r["batch"]) for r in rows],
                         [("32x1x1", 4), ("32x1x1", 16), ("64x4x2", 4), ("64x4x2", 16)])
        for r in rows:
            self.assertNotIn("error", r)
            self.assertGreater(r["gpu_pos_per_s"], 0)
            self.assertGreater(r["h2d_pos_per_s"], 0)
            self.assertEqual(r["tokens_padded"], 1 + 30 + 5 + 8 + 1)
        self.assertEqual(rows[2]["params"], 413016)

    def test_cpu_amber_sizes(self):
        spec = importlib.util.spec_from_file_location("gpu_forward_bench",
                                                      os.path.join(ROOT, "tools", "az_bench", "gpu_forward_bench.py"))
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "b.json")
            rc = bench.main(["--device", "cpu", "--dtype", "fp32", "--batches", "4", "--warmup", "1", "--iters", "1",
                             "--live-frac", "0.5", "--out", out])
            self.assertEqual(rc, 0)
            rows = json.load(open(out))["results"]
        # Amber Eye's three sizes (~0.44M, ~1.2M, ~5.4M) within 10 %.
        for r, want in zip(rows, (0.44e6, 1.2e6, 5.4e6)):
            self.assertNotIn("error", r)
            self.assertLess(abs(r["params"] - want) / want, 0.10, r)
            self.assertEqual(r["tokens_padded"], 42)   # 40 tokens + one masked slot each for option and map
            self.assertLess(r["tokens_live"], 25)


if __name__ == "__main__":
    unittest.main()
