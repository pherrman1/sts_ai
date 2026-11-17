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


def check_progress(tc, e):
    """Invariants of one ascension's run progress counters (driver progress_asc / selfplay progress_window)."""
    n = e["runs"]
    for k in ("ruby", "emerald", "sapphire", "act4", "heart", "keyless_victories"):
        tc.assertLessEqual(0, e[k], k)
        tc.assertLessEqual(e[k], n, k)
    tc.assertLessEqual(e["all_keys"], min(e["ruby"], e["emerald"], e["sapphire"]))
    tc.assertEqual(e["campfires"], e["rest"] + e["smith"] + e["recall"] + e["other_campfire"])
    tc.assertLessEqual(e["recall"], e["recall_offered"])
    tc.assertLessEqual(e["recall_offered"], e["campfires"])
    tc.assertLessEqual(e["recall"], e["ruby"])          # Recall gives the Ruby key (one per run at most)
    tc.assertLessEqual(e["burning_elites"], e["elites"])
    tc.assertLessEqual(e["emerald"], e["burning_elites"])
    tc.assertLessEqual(e["heart"], e["act4"])
    tc.assertLessEqual(e["act4"], e["all_keys"])        # Act 4 needs all three keys
    tc.assertLessEqual(e["keyless_victories"] + e["act4"], n)


@unittest.skipUnless(HAVE_TORCH, "torch missing")
class ProgressWindowTest(unittest.TestCase):
    def test_deltas_per_ascension(self):
        sp = load()
        z = [0] * 21
        a = {"runs_done_asc": z[:], "progress_asc": {"ruby": z[:], "recall": z[:]}}
        b = {"runs_done_asc": z[:], "progress_asc": {"ruby": z[:], "recall": z[:]}}
        a["runs_done_asc"][0] = 10; a["progress_asc"]["ruby"][0] = 3
        b["runs_done_asc"][0] = 15; b["progress_asc"]["ruby"][0] = 5; b["progress_asc"]["recall"][0] = 2
        b["runs_done_asc"][1] = 4; b["progress_asc"]["ruby"][1] = 1
        self.assertEqual(sp.progress_window(b, a), {"0": {"runs": 5, "ruby": 2, "recall": 2},
                                                    "1": {"runs": 4, "ruby": 1, "recall": 0}})
        self.assertEqual(sp.progress_window(a, a), {})


class DashboardProgressTest(unittest.TestCase):
    def test_panel(self):
        spec = importlib.util.spec_from_file_location(
            "selfplay_dashboard", os.path.join(ROOT, "tools", "az_bench", "selfplay_dashboard.py"))
        dash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dash)
        e = dict.fromkeys(dash.PROGRESS_KEYS, 0)
        e.update(runs=100, ruby=40, emerald=10, sapphire=20, all_keys=5, campfires=200, recall_offered=150,
                 rest=120, smith=50, recall=30, elites=150, burning_elites=30, act4=5, heart=4, keyless_victories=20)
        base = {"time": "2026-11-17 18:00:00", "hours": 1, "positions_per_s": 1, "moves_per_s": 1, "runs_window": 100,
                "win_rate_window": 0, "mean_floor_window": 20, "wins_total": 0, "train_steps": 1, "samples_added": 1,
                "stalls": 0, "ascension": 0, "asc_runs_window": 100, "asc_win_rate_window": 0,
                "asc_mean_floor_window": 20, "asc_win_rate_rolling": 0, "asc_rolling_runs": 100}
        old = dict(base, runs_done=100)                                  # a row from before the counters
        rows = [old, dict(base, runs_done=200, progress_window={"0": e}),
                dict(base, runs_done=300, progress_window={"0": e})]
        self.assertEqual(dash.progress_sum(rows)[0]["runs"], 200)
        page = dash.page(rows, "t", "")
        self.assertIn("Keys, Recall, elites, Act 4", page)
        self.assertIn("<td>A0</td><td>200</td><td>40.0</td><td>10.0</td><td>20.0</td><td>5.0</td><td>20.0</td>", page)
        self.assertNotIn("Keys, Recall, elites", dash.page([old], "t", ""))


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
            prog = {}
            for r in rows:
                for a, e in r["progress_window"].items():
                    t = prog.setdefault(a, dict.fromkeys(e, 0))
                    for k, v in e.items():
                        t[k] += v
            self.assertEqual(sum(e["runs"] for e in prog.values()), rows[-1]["runs_done"])
            for e in prog.values():
                check_progress(self, e)
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

    def test_search_flags(self):
        """--no-fast-noise / --q-rescale / --c-scale reach the driver; the OOC search diagnostics are logged."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "700", "--max-runs", "8",
                "--no-fast-noise", "--q-rescale", "--c-scale", "0.1"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertEqual(len(last["ooc_searched"]), 2)
            self.assertGreater(sum(last["ooc_searched"]), 0)
            self.assertTrue(all(0 <= b <= a for a, b in zip(last["ooc_searched"], last["ooc_not_best_q"])))
            self.assertTrue(all(0 <= x <= 1 for x in last["ooc_q_spread_mean"]))
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            a = torch.load(ck)["args"]
            self.assertTrue(a["no_fast_noise"] and a["q_rescale"])
            self.assertEqual(a["c_scale"], 0.1)

    def test_progress_counters_late_floors(self):
        """With a huge max HP, A0 runs reach campfires and elites: the driver counts them per ascension and the
        counters are consistent (Recall gives the Ruby key, Act 4 needs all keys, the Heart needs Act 4)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "3",
                "--full-sims", "4", "--fast-sims", "2", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "1000000", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1300", "--max-runs", "6",
                "--ascension", "0", "--test-max-hp", "3000"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
        e = {}
        for r in rows:
            for k, v in r["progress_window"].get("0", {}).items():
                e[k] = e.get(k, 0) + v
        self.assertGreaterEqual(e["runs"], 6)
        check_progress(self, e)
        self.assertGreater(e["campfires"], 0)
        self.assertGreater(e["elites"], 0)

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
