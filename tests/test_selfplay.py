"""Tests for tools/az_bench/selfplay.py (stage 1 self-play loop): the replay window returns exactly the stored
samples in forward_flat's layout and evicts FIFO; the heads -> (F, E[HP]) conversion; and, with a built
az_bench_native module, a short CPU run plays runs, trains, writes metrics and a checkpoint, and resumes with the
next seeds. Skipped when torch (or, for the run, the module) is missing."""

import glob
import importlib.util
import json
import os
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


def load():
    spec = importlib.util.spec_from_file_location("selfplay", os.path.join(ROOT, "tools", "az_bench", "selfplay.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def chunk(rng, S, first_id=0):
    """A take_samples-shaped chunk: sample i has 2..20 tokens and 2..9 actions; ids encode (sample, position)."""
    nt = rng.integers(2, 21, S)
    na = rng.integers(2, 10, S)
    tok_off = np.concatenate([[0], np.cumsum(nt)]).astype(np.int64)
    act_off = np.concatenate([[0], np.cumsum(na)]).astype(np.int64)
    T, A = int(tok_off[-1]), int(act_off[-1])
    sid = np.repeat(np.arange(S) + first_id, nt)
    pos = np.arange(T) - np.repeat(tok_off[:-1], nt)
    ids = np.stack([sid % 30000, pos, sid // 30000, np.ones(T, int)], 1).astype(np.int16)
    pol = rng.random(A).astype(np.float32)
    has = (rng.random(S) < 0.5).astype(np.uint8)
    return {"tok_off": tok_off, "act_off": act_off, "tok_type": rng.integers(0, 9, T).astype(np.int8), "ids": ids,
            "f": rng.normal(0, 1, (T, 64)).astype(np.float16), "a_type": rng.integers(0, 16, A).astype(np.int16),
            "a_src": np.minimum(rng.integers(-1, 2, A), np.repeat(nt, na) - 1).astype(np.int16),
            "a_tgt": np.full(A, -1, np.int16), "a_f": rng.normal(0, 1, (A, 8)).astype(np.float16),
            "policy": pol * np.repeat(has, na), "search_value": rng.random(S).astype(np.float32),
            "outcome": rng.integers(0, 57, S).astype(np.int16), "hp_end": rng.integers(0, 90, S).astype(np.int16),
            "max_hp": np.full(S, 80, np.int16), "floor": rng.integers(0, 56, S).astype(np.int16),
            "combat": rng.integers(0, 2, S).astype(np.uint8), "has_policy": has,
            "run": np.arange(S, dtype=np.uint64)}


@unittest.skipUnless(HAVE_TORCH, "torch missing")
class ReplayTest(unittest.TestCase):
    def test_roundtrip_and_eviction(self):
        sp = load()
        rng = np.random.default_rng(0)
        rep = sp.Replay(300, tokens_per_sample=12, actions_per_sample=6)   # small rings: forces wrap and eviction
        chunks, first = [], 0
        for _ in range(12):
            S = int(rng.integers(20, 60))
            c = chunk(rng, S, first)
            rep.add(c)
            chunks.append(c)
            first += S
        self.assertLessEqual(len(rep), 300)
        self.assertEqual(rep.added, first)
        live_first = first - len(rep)
        # Every live sample is among the most recent ones (FIFO), and a batch reproduces them exactly.
        b = rep.sample(np.random.default_rng(1), 64)
        by_id = {}
        for c in chunks:
            S = len(c["outcome"])
            for i in range(S):
                sid = int(c["ids"][c["tok_off"][i], 0]) + 30000 * int(c["ids"][c["tok_off"][i], 2])
                by_id[sid] = (c, i)
        for r in range(64):
            n = int(b["mask"][r].sum())
            self.assertTrue(b["mask"][r, :n].all())
            sid = int(b["ids"][r, 0, 0]) + 30000 * int(b["ids"][r, 0, 2])
            self.assertGreaterEqual(sid, live_first)
            c, i = by_id[sid]
            t0, t1 = c["tok_off"][i], c["tok_off"][i + 1]
            a0, a1 = c["act_off"][i], c["act_off"][i + 1]
            self.assertEqual(n, t1 - t0)
            np.testing.assert_array_equal(b["tok_type"][r, :n], c["tok_type"][t0:t1])
            np.testing.assert_array_equal(b["ids"][r, :n], c["ids"][t0:t1])
            np.testing.assert_array_equal(b["f"][r, :n], c["f"][t0:t1])
            na = int(b["a_mask"][r].sum())
            self.assertEqual(na, a1 - a0)
            np.testing.assert_array_equal(b["a_type"][r, :na], c["a_type"][a0:a1])
            np.testing.assert_array_equal(b["a_src"][r, :na], c["a_src"][a0:a1])
            np.testing.assert_array_equal(b["a_f"][r, :na], c["a_f"][a0:a1])
            np.testing.assert_array_equal(b["policy"][r, :na], c["policy"][a0:a1])
            self.assertTrue((b["a_src"][r, na:] == -1).all())
            for k in ("outcome", "hp_end", "has_policy", "floor", "combat"):
                self.assertEqual(b[k][r], c[k][i], k)

    def test_policy_frac(self):
        sp = load()
        rng = np.random.default_rng(2)
        rep = sp.Replay(1000)
        rep.add(chunk(rng, 500))
        b = rep.sample(np.random.default_rng(3), 200, policy_frac=0.9)
        self.assertGreaterEqual(int(b["has_policy"].sum()), 180)


@unittest.skipUnless(HAVE_TORCH, "torch missing")
class HeadsTest(unittest.TestCase):
    def test_search_values(self):
        sp = load()
        out = torch.full((3, 57), -1e4)
        out[0, 0] = 0      # sure win -> F = 1
        out[1, 10] = 0     # sure death on floor 10 -> 10 / 57
        out[2, 0] = out[2, 57 // 1 - 1] = 0   # half win, half floor 56
        hp = torch.full((3, 256), -1e4)
        hp[:, 40] = 0
        hp[2, 40], hp[2, 60] = 0, 0
        F, ehp = sp.search_values(out, hp)
        self.assertAlmostEqual(float(F[0]), 1.0, places=5)
        self.assertAlmostEqual(float(F[1]), 10 / 57, places=5)
        self.assertAlmostEqual(float(F[2]), (1 + 56 / 57) / 2, places=5)
        self.assertAlmostEqual(float(ehp[0]), 40.0, places=3)
        self.assertAlmostEqual(float(ehp[2]), 50.0, places=3)


@unittest.skipUnless(HAVE_TORCH, "torch missing")
class AmberUtilityTest(unittest.TestCase):
    def test_amber_h(self):
        sp = load()
        hpf = torch.zeros(3, 56)
        hpf[0, 9:20] = 0.2           # floor 10: (9 + 11 * 0.2) / 56
        hpf[1] = 1.0                 # full HP everywhere: 1
        hpf[2, :5] = 7.0             # floor 6: past floors ignored, (5 + 0) / 56
        h = sp.amber_h(torch.tensor([10, 1, 6]), hpf)
        self.assertAlmostEqual(float(h[0]), (9 + 11 * 0.2) / 56, places=5)
        self.assertAlmostEqual(float(h[1]), 1.0, places=5)
        self.assertAlmostEqual(float(h[2]), 5 / 56, places=5)

    def test_hp_floor_loss_masks(self):
        sp = load()
        label = torch.full((2, 56), -1, dtype=torch.int16)
        label[0, 3:] = 51            # 0.2 of 255
        pred = torch.full((2, 56), 0.2)
        pred[:, :3] = 9.0            # masked slots do not count
        pred[1] = 9.0                # row 1 fully masked
        self.assertAlmostEqual(float(sp.hp_floor_loss(pred, label)), 0.0, places=6)
        pred[0, 10] = 0.7
        self.assertAlmostEqual(float(sp.hp_floor_loss(pred, label)), 0.25 / 53, places=6)

    def test_replay_carries_hp_floor(self):
        sp = load()
        rng = np.random.default_rng(4)
        rep = sp.Replay(500, hp_floors=56)
        c = chunk(rng, 100)
        c["hp_floor"] = rng.integers(-1, 90, (100, 56)).astype(np.int16)
        rep.add(c)
        b = rep.sample(np.random.default_rng(5), 50)
        self.assertEqual(b["hp_floor"].shape, (50, 56))
        rows = {tuple(r) for r in c["hp_floor"]}
        self.assertTrue(all(tuple(r) in rows for r in b["hp_floor"]))


@unittest.skipUnless(HAVE_TORCH and MODULES, "torch or the az_bench_native module (cmake target) missing")
class SelfplaySmoke(unittest.TestCase):
    def test_run_train_resume(self):
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2"]
        with tempfile.TemporaryDirectory() as d:
            rc = sp.main(common + ["--out-dir", d, "--seed-base", "500", "--max-runs", "24"])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 24)
            self.assertGreater(rows[-1]["samples_added"], 0)
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertGreater(rows[-1]["syncs"], 0)
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            c = torch.load(ck)["counters"]
            self.assertGreaterEqual(c["seeds_used"], 24)
            self.assertEqual(c["runs_done"], rows[-1]["runs_done"])
            # Resume: 8 more runs with the seeds after the first 24.
            # Resume as the continuation does: pick-rate exploration on.
            rc = sp.main(common + ["--out-dir", d, "--seed-base", "500", "--max-runs", "32", "--resume", ck,
                                   "--explore-c", "0.5", "--pick-target", "0.2"])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertGreater(last["ooc_roots"], 0)
            self.assertGreater(last["explore_roots"], 0)
            c2 = torch.load(sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1])["counters"]
            self.assertGreaterEqual(c2["seeds_used"], 32)
            self.assertGreater(c2["step"], c["step"])   # training resumes (the replay-ratio cap counts from the resume)
            self.assertGreaterEqual(c2["runs_done"], 32)

    def test_amber_utility_run_and_init_net(self):
        """--utility amber trains the per-floor HP head on the driver's labels; --init-net starts it from a floor-hp
        checkpoint (per-floor head fresh, the rest copied); --keyless-hp runs with the default utility."""
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2", "--max-runs", "16"]
        with tempfile.TemporaryDirectory() as d0, tempfile.TemporaryDirectory() as d1:
            self.assertEqual(sp.main(common + ["--out-dir", d0, "--seed-base", "700", "--keyless-hp"]), 0)
            ck0 = sorted(glob.glob(os.path.join(d0, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertEqual(tuple(torch.load(ck0)["net"]["hp_floor.2.weight"].shape)[0], 1)
            self.assertEqual(sp.main(common + ["--out-dir", d1, "--seed-base", "800", "--utility", "amber",
                                               "--init-net", ck0]), 0)
            with open(os.path.join(d1, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertTrue(any(r["loss"] and "hp_floor" in r["loss"] for r in rows))
            ck1 = sorted(glob.glob(os.path.join(d1, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            net1 = torch.load(ck1)["net"]
            self.assertEqual(tuple(net1["hp_floor.2.weight"].shape)[0], 56)

    def test_curriculum_switch(self):
        """With a 0 % threshold the curriculum moves up after --curriculum-runs runs and the checkpoint keeps it."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "900", "--max-runs", "24",
                "--ascension", "0", "--curriculum", "--curriculum-runs", "4", "--curriculum-winrate", "0"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertEqual(rows[0]["ascension"], 0)
            self.assertGreaterEqual(rows[-1]["ascension"], 1)
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            # The last report may have raised it once more.
            self.assertIn(torch.load(ck)["counters"]["ascension"], (rows[-1]["ascension"], rows[-1]["ascension"] + 1))


if __name__ == "__main__":
    unittest.main()
