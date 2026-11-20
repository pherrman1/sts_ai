#!/usr/bin/env python3
"""tools/az_bench/infer_profile.py on a small CPU self-play run: the inference batch it builds from replay rows
gives the same net outputs as the replay's own batch layout, and the tool runs end to end.

Run: python3 tests/test_infer_profile.py
"""

import glob
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = sorted(glob.glob(os.path.join(ROOT, "build", "*", "az_bench_native*.so")))

try:
    import torch
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", "az_bench", name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(HAVE_TORCH and MODULES, "torch or the az_bench_native module (cmake target) missing")
class InferProfileSmoke(unittest.TestCase):
    def test_layout_and_run(self):
        mod_dir = os.path.dirname(MODULES[0])
        sys.path.insert(0, mod_dir)
        sp, ip = load("selfplay"), load("infer_profile")
        import az_bench_native
        with tempfile.TemporaryDirectory() as d:
            rep = os.path.join(d, "replay")
            self.assertEqual(sp.main([
                "--module-dir", mod_dir, "--device", "cpu", "--workers", "2", "--games", "4", "--full-sims", "8",
                "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32", "--pack-threads", "1",
                "--min-replay", "50", "--train-batch", "32", "--window", "5000", "--report", "1", "--sync-steps", "2",
                "--seed-base", "520", "--ascension", "1", "--utility", "amber", "--compact-samples",
                "--compress-targets", "--packed-h2d", "--value-ema-halflife", "6", "--value-ema-search",
                "--w-soft-policy", "8", "--out-dir", d, "--max-runs", "12", "--replay-save", rep]), 0)
            with open(os.path.join(rep, "state.json")) as f:
                ck_path = json.load(f)["extra"]["checkpoint"]
            ck = torch.load(ck_path, map_location="cpu", weights_only=False)
            a = ck["args"]

            # The inference layout (row / token / action buckets, driver dtypes, trash entries) against the
            # replay's own packed batch: same outputs on the live rows and actions.
            replay = sp.Replay(a["window"], hp_floors=56, soft_outcome=True, compact=True,
                               dict_tokens_per_sample=a["replay_dict_tokens"], token_store=az_bench_native.TokenStore,
                               tokens_per_sample=a["replay_tokens_per_sample"],
                               actions_per_sample=a["replay_actions_per_sample"], compress_targets=True,
                               soft_bytes_per_sample=a["replay_soft_bytes"], hp_runs_per_sample=a["replay_hp_runs"])
            replay.load(rep)
            b = replay.sample(np.random.default_rng(1), 24, 0.0, packed=True)
            d_net, layers = ck["net_size"]
            net = sp.amber_net.AmberNet(d=d_net, layers=layers, hp_floors=56, soft_policy=True).eval()
            net.load_state_dict(ck["net"])
            r = ip.split_rows(b)
            self.assertEqual(int(r["nt"].sum()), int(b["mask"].sum()))
            h, info = ip.flat_input(r, 32, ip.bucket([32, 64, 128, 212], int(r["nt"].max())), 16, 32)
            self.assertEqual(info["rows"], 24)
            self.assertEqual(info["npad"] % 32, 0)
            # 8 padding rows with one token each (packFlat), then trash entries
            n = info["live_tokens"]
            self.assertEqual(h["pack_idx"][n:n + 8].tolist(), [r_ * info["Tp"] for r_ in range(24, 32)])
            self.assertTrue((h["pack_idx"][n + 8:] == info["Rp"] * info["Tp"]).all())
            self.assertEqual(int(h["seq_off"][24]), n)
            self.assertEqual(int(h["seq_off"][32]), n + 8)
            self.assertEqual(int(h["mask"].sum()), n + 8)

            def as_torch(x, drop=()):
                out = {}
                for k, v in x.items():
                    if k in drop or not isinstance(v, np.ndarray):
                        continue
                    t = torch.from_numpy(v)
                    if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt", "pack_idx"):
                        t = t.long()
                    elif t.dtype == torch.float16:
                        t = t.float()
                    out[k] = t
                return out
            keys = ("tok_type", "ids", "f", "pack_idx", "mask", "a_type", "a_src", "a_tgt", "a_f", "a_mask")
            with torch.inference_mode():
                want = net({k: v for k, v in as_torch(b).items() if k in keys})
                got = net(as_torch(h, drop=("seq_off",)))
            A = b["a_mask"].shape[1]
            live = torch.from_numpy(b["a_mask"])
            self.assertTrue(torch.allclose(got[0][:24, :A][live], want[0][live], atol=1e-4))
            for i in (1, 2, 3):
                self.assertTrue(torch.allclose(got[i][:24], want[i], atol=1e-4))

            # the variants keep the tokens: short = the rows of at most 64 tokens, uniform = rows of the mean length
            short = ip.take_rows(r, r["nt"] <= 20)
            self.assertEqual(len(short["tok_type"]), int(r["nt"][r["nt"] <= 20].sum()))
            uni = ip.uniform_rows(r)
            self.assertEqual(len(set(uni["nt"].tolist())), 1)
            self.assertLessEqual(int(uni["a_src"].max()), int(uni["nt"][0]) - 1)

            # --packed-heads inputs: the live actions of the live rows, trash-padded; padding rows at length 0
            la = np.flatnonzero(h["a_mask"][:24].reshape(-1))
            self.assertEqual(info["live_actions"], la.size)
            self.assertEqual(h["act_idx"][:la.size].tolist(), la.tolist())
            self.assertTrue((h["act_idx"][la.size:] == info["Rp"] * info["Ap"]).all())
            self.assertEqual(h["act_idx"].size % 1024, 0)
            self.assertEqual(h["seq_off_live"][:25].tolist(), h["seq_off"][:25].tolist())
            self.assertTrue((h["seq_off_live"][25:] == n).all())

            out = os.path.join(d, "prof.json")
            self.assertEqual(ip.main(["--module-dir", mod_dir, "--ckpt", ck_path, "--replay", rep, "--batches", "2",
                                      "--iters", "2", "--warmup", "1", "--device", "cpu", "--out", out]), 0)
            with open(out) as f:
                res = json.load(f)
            self.assertEqual(set(res["summary"]), {"real", "real_Rtight", "short_T64", "short_Tbig", "uniform"})
            self.assertEqual(res["window"]["samples"], len(replay))
            for x in res["results"]:
                self.assertGreater(x["ms_per_batch"], 0)
                self.assertLessEqual(x["tokens_max"], x["Tp"])

            # The three settings of the kernel path (Triton's interpreter on a CPU, fp32): row bounds give the same
            # outputs, the packed heads the same up to rounding.
            if importlib.util.find_spec("triton") is None:
                return
            # its own process: triton reads TRITON_INTERPRET when it is first imported
            run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "az_bench", "infer_profile.py"),
                                  "--module-dir", mod_dir, "--ckpt", ck_path, "--replay", rep, "--batches", "1",
                                  "--iters", "1", "--warmup", "0", "--device", "cpu", "--variants", "real,uniform",
                                  "--out", out], env=dict(os.environ, TRITON_INTERPRET="1"), capture_output=True,
                                 text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-3000:])
            with open(out) as f:
                res = json.load(f)
            self.assertEqual(len(res["results"]), 2)
            for x in res["results"]:
                self.assertTrue(x["row_bounds_equal"])
                self.assertTrue(x["packed_heads_finite"])
                self.assertLess(max(x["packed_heads_max_diff"].values()), 1e-3)
                self.assertEqual(x["packed_heads_same_argmax"], 1.0)


if __name__ == "__main__":
    unittest.main()
