"""Tests for tools/az_bench/selfplay.py (stage 1 self-play loop): the replay window returns exactly the stored
samples in forward_flat's layout and evicts FIFO; the heads -> (F, E[HP]) conversion; the EMA outcome labels
(--value-ema-halflife: recursion, soft-target ring, loss); and, with a built
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

    def test_packed_batch_same_loss_and_grads(self):
        """sample(packed=True) holds the same rows as the padded batch, and forward_packed gives the same losses and
        gradients (fp32, float rounding only), with and without trash entries (pack_step)."""
        sp = load()
        rng = np.random.default_rng(4)
        rep = sp.Replay(2000)
        rep.add(chunk(rng, 400))
        torch.manual_seed(0)
        net = sp.amber_net.jitter_1d_params(sp.amber_net.AmberNet(64, 2))
        net.sdpa = True
        for step in (1, 64):
            b = rep.sample(np.random.default_rng(5), 48)
            p = rep.sample(np.random.default_rng(5), 48, packed=True, pack_step=step)
            B, T = b["mask"].shape
            n = int(b["mask"].sum())
            np.testing.assert_array_equal(p["mask"], b["mask"])
            np.testing.assert_array_equal(p["pack_idx"][:n], np.flatnonzero(b["mask"]))
            self.assertTrue((p["pack_idx"][n:] == B * T).all())
            np.testing.assert_array_equal(p["f"][:n], b["f"].reshape(B * T, -1)[np.flatnonzero(b["mask"])])
            res = []
            for x in (b, p):
                net.zero_grad()
                loss, parts = sp.losses(net, sp.to_torch(x, torch.device("cpu")), 1.0, 1.0, 1.0)
                loss.backward()
                res.append((float(loss), [torch.zeros_like(q) if q.grad is None else q.grad.clone() for q in net.parameters()]))
            self.assertAlmostEqual(res[0][0], res[1][0], places=5)
            for g0, g1 in zip(res[0][1], res[1][1]):
                self.assertLess(float((g0 - g1).abs().max()), 1e-5 + 1e-4 * float(g0.abs().max()))

    def test_soft_policy_head(self):
        """--w-soft-policy (Amber Eye / KataGo): target p^(1/4) renormalised over the legal actions; the soft head is a
        5th output in training mode only; its loss is the masked cross-entropy on policy rows, weighted into the total;
        w = 0 builds no head and gives the old loss."""
        sp = load()
        pol = torch.tensor([[0.81, 0.16, 0.03, 0.0], [0.0, 0.0, 0.0, 0.0]])
        mask = torch.tensor([[True, True, True, False], [True, True, False, False]])
        t = sp.soft_policy_target(pol, mask)
        r = np.array([0.81, 0.16, 0.03]) ** 0.25
        np.testing.assert_allclose(t[0, :3].numpy(), r / r.sum(), rtol=1e-6)
        self.assertEqual(float(t[0, 3]), 0.0)
        self.assertEqual(float(t[1].sum()), 0.0)
        rng = np.random.default_rng(9)
        rep = sp.Replay(2000)
        rep.add(chunk(rng, 300))
        bt = sp.to_torch(rep.sample(np.random.default_rng(1), 40), torch.device("cpu"))
        torch.manual_seed(0)
        plain = sp.amber_net.AmberNet(64, 2)
        torch.manual_seed(0)
        soft = sp.amber_net.AmberNet(64, 2, soft_policy=True)
        self.assertFalse(any(k.startswith("pol_soft") for k in plain.state_dict()))
        self.assertEqual(len(soft.eval()(bt)), 4)
        soft.train()
        out = soft(bt)
        self.assertEqual(len(out), 5)
        soft.load_state_dict({**soft.state_dict(), **plain.state_dict()})
        l0, p0 = sp.losses(plain, bt, 1.0, 1.0, 1.0)
        l1, p1 = sp.losses(soft, bt, 1.0, 1.0, 1.0)   # weight 0: soft output ignored
        self.assertAlmostEqual(float(l0), float(l1), places=6)
        self.assertNotIn("soft_policy", p1)
        l8, p8 = sp.losses(soft, bt, 1.0, 1.0, 1.0, 0.0, 8.0)
        slogit = soft(bt)[4]
        slogp = torch.log_softmax(slogit.float().masked_fill(~bt["a_mask"], -1e4), -1)
        has = bt["has_policy"].bool()
        ce = -(sp.soft_policy_target(bt["policy"], bt["a_mask"]) * slogp).sum(-1)
        want = float(ce[has].mean())
        self.assertAlmostEqual(float(p8["soft_policy"]), want, places=5)
        self.assertAlmostEqual(float(l8), float(l1) + 8.0 * want, places=4)
        gs, gp = torch.autograd.grad(ce[has].mean(), [soft.pol_soft[2].weight, soft.pol[2].weight], allow_unused=True)
        self.assertGreater(float(gs.abs().sum()), 0)   # the soft term moves the soft head, not the normal policy head
        self.assertIsNone(gp)

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


@unittest.skipUnless(HAVE_TORCH, "torch missing")
class ValueEmaTest(unittest.TestCase):
    def test_targets_by_hand(self):
        sp = load()
        C, lam = 4, 0.5
        dist = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [.25, .25, .25, .25], [0, 0, 0, 1]], np.float32)
        outcome = np.array([3, 3, 3, 1, 1])
        run = np.array([7, 7, 7, 9, 9])
        tgt, w = sp.ema_outcome_targets(dist, outcome, run, lam)
        oh = np.eye(C, dtype=np.float32)
        t2 = (1 - lam) * dist[2] + lam * oh[3]
        t1 = (1 - lam) * dist[1] + lam * t2
        t0 = (1 - lam) * dist[0] + lam * t1
        t4 = (1 - lam) * dist[4] + lam * oh[1]
        t3 = (1 - lam) * dist[3] + lam * t4
        np.testing.assert_allclose(tgt, np.stack([t0, t1, t2, t3, t4]), atol=1e-6)
        np.testing.assert_allclose(w, [lam ** 3, lam ** 2, lam, lam ** 2, lam], atol=1e-7)
        np.testing.assert_allclose(tgt.sum(1), 1.0, atol=1e-6)
        # The final outcome's share of each target is its weight (dist rows with no mass on it).
        self.assertAlmostEqual(float(tgt[0, 3]), lam ** 3, places=6)

    def test_limits_and_contiguity(self):
        sp = load()
        rng = np.random.default_rng(4)
        S, C = 50, 57
        dist = rng.dirichlet(np.ones(C), S).astype(np.float32)
        run = np.repeat([1, 2, 3], [20, 1, 29])
        outcome = np.repeat([0, 5, 33], [20, 1, 29])
        # lam -> 1: every target is the final outcome (the label without EMA).
        tgt, w = sp.ema_outcome_targets(dist, outcome, run, 1.0)
        np.testing.assert_allclose(tgt, np.eye(C)[outcome], atol=1e-6)
        np.testing.assert_allclose(w, 1.0)
        # lam = 0: the net's own distribution.
        tgt, _ = sp.ema_outcome_targets(dist, outcome, run, 0.0)
        np.testing.assert_allclose(tgt, dist, atol=1e-6)
        with self.assertRaises(ValueError):
            sp.ema_outcome_targets(dist[:3], outcome[:3], np.array([1, 2, 1]), 0.5)

    def test_replay_soft_ring_and_loss(self):
        sp = load()
        rng = np.random.default_rng(5)
        rep = sp.Replay(120, tokens_per_sample=12, actions_per_sample=6, soft_outcome=True)
        first_id, firsts = 0, []
        for _ in range(5):   # 5 x 40 samples into 120: wraps and evicts
            c = chunk(rng, 40, first_id)
            first = rep.add(c)
            self.assertEqual(first, first_id)
            # Until set: the final outcome.
            b = rep.rows(first, 40)
            np.testing.assert_array_equal(b["soft_outcome"].argmax(1), c["outcome"])
            np.testing.assert_array_equal(b["ids"][:, 0, 0], np.arange(first_id, first_id + 40) % 30000)
            tgt = rng.dirichlet(np.ones(57), 40).astype(np.float32)
            rep.set_soft_outcome(first, tgt)
            np.testing.assert_allclose(rep.rows(first, 40)["soft_outcome"], tgt, atol=2e-3)   # float16 storage
            firsts.append((first, tgt))
            first_id += 40
        with self.assertRaises(ValueError):
            rep.rows(0, 10)   # evicted
        # A random batch carries each sample's own target.
        b = rep.sample(np.random.default_rng(6), 64)
        by_id = {f + i: t[i] for f, t in firsts for i in range(40)}
        for r in range(64):
            np.testing.assert_allclose(b["soft_outcome"][r], by_id[int(b["ids"][r, 0, 0])], atol=2e-3)
        # Setting targets of partly evicted samples writes only the live ones.
        rep.set_soft_outcome(first_id - 160, np.full((80, 57), 1 / 57, np.float32))
        self.assertTrue(np.allclose(rep.rows(first_id - 120, 40)["soft_outcome"], 1 / 57, atol=1e-3))
        # Loss: a one-hot soft target gives the plain cross-entropy; "outcome" is always the final-outcome CE.
        net = sp.amber_net.AmberNet(d=32, layers=1)
        bt = sp.to_torch(rep.sample(np.random.default_rng(7), 16), "cpu")
        _, parts0 = sp.losses(net, {k: v for k, v in bt.items() if k != "soft_outcome"}, 1, 1, 1)
        bt["soft_outcome"] = torch.nn.functional.one_hot(bt["outcome"].long(), 57).float()
        total1, parts1 = sp.losses(net, bt, 1, 1, 1)
        self.assertAlmostEqual(float(parts1["outcome_ema"]), float(parts1["outcome"]), places=4)
        self.assertAlmostEqual(float(parts0["outcome"]), float(parts1["outcome"]), places=5)
        bt["soft_outcome"] = torch.full_like(bt["soft_outcome"], 1 / 57)
        total2, parts2 = sp.losses(net, bt, 1, 1, 1)
        self.assertNotAlmostEqual(float(total1.detach()), float(total2.detach()), places=3)
        self.assertAlmostEqual(float(parts2["outcome"]), float(parts1["outcome"]), places=5)


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

    def test_soft_policy_run(self):
        """--w-soft-policy trains the soft head in a real run (loss logged, head in the checkpoint); the inference copy
        and the EMA / eval calls take the 4 usual outputs."""
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2", "--max-runs", "16"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(common + ["--out-dir", d, "--seed-base", "900", "--w-soft-policy", "8",
                                               "--value-ema-halflife", "20"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertTrue(any(r["loss"] and r["loss"].get("soft_policy", 0) > 0 for r in rows))
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertIn("pol_soft.2.weight", torch.load(ck)["net"])

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

    def test_value_ema_run(self):
        """--value-ema-halflife trains on EMA targets; take_samples in 1-sample chunks never splits a run."""
        sp = load()
        sp.TAKE_CHUNK = 1
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "700", "--max-runs", "16",
                "--value-ema-halflife", "8"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            last = rows[-1]
            self.assertGreater(last["train_steps"], 0)
            self.assertEqual(last["value_ema"]["labelled"], last["samples_added"])
            self.assertGreater(last["value_ema"]["real_weight_mean"], 0)
            self.assertLess(last["value_ema"]["real_weight_mean"], 1)
            self.assertTrue(any(r["loss"] and "outcome_ema" in r["loss"] for r in rows))

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

    def test_eval_cache_run(self):
        """--eval-cache plays and trains as usual and answers some leaves from the cache (exactness: ctest
        az_eval_cache)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "1000000", "--seed-base", "1300", "--max-runs", "16", "--eval-cache"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 16)
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertGreater(sum(r["cache_hits_per_s"] for r in rows), 0)

    def test_packed_h2d_run(self):
        """--packed-h2d (live tokens packed by the driver) plays and trains as usual (bit-identical forward:
        tests/test_amber_net_flat.py, packing: ctest az_pack_packed_tokens)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1400", "--max-runs", "16", "--packed-h2d"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 16)
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertEqual(rows[-1]["invalid_actions"], 0)

    def test_train_packed_run(self):
        """--train-packed trains on packed batches (same loss: ReplayTest.test_packed_batch_same_loss_and_grads)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1500", "--max-runs", "16", "--train-packed"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 16)
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertTrue(any(r["loss"] for r in rows))   # some report has a training loss

    def test_merge_cards_run(self):
        """--merge-cards (card stacks in the net input; property test: ctest az_merge_cards) plays and trains."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1600", "--max-runs", "16", "--merge-cards"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 16)
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertEqual(rows[-1]["invalid_actions"], 0)

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
