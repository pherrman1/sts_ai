"""Tests for tools/az_bench/selfplay.py (stage 1 self-play loop): the replay window returns exactly the stored
samples in forward_flat's layout and evicts FIFO; the heads -> (F, E[HP]) conversion; the EMA outcome labels
(--value-ema-halflife: recursion, soft-target ring, loss); and, with a built
az_bench_native module, a short CPU run plays runs, trains, writes metrics and a checkpoint, and resumes with the
next seeds. Skipped when torch (or, for the run, the module) is missing."""

import contextlib
import glob
import gzip
import importlib.util
import io
import json
import os
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


def native():
    sys.path.insert(0, os.path.dirname(MODULES[0]))
    import az_bench_native
    return az_bench_native


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

    @staticmethod
    def compactify(c):
        """The compact form of a chunk (as take_samples gives it with --compact-samples): each run's distinct tokens
        once (order of first use), samples refer to them by index."""
        nt = np.diff(c["tok_off"])
        S = len(nt)
        rows = np.concatenate([c["tok_type"].astype(np.int16)[:, None].view(np.uint16), c["ids"].view(np.uint16),
                               c["f"].view(np.uint16)], 1)
        tt, ids, f, idx, base = [], [], [], [], np.zeros(S, np.int64)
        n_dict, i = 0, 0
        while i < S:
            j = i
            while j < S and c["run"][j] == c["run"][i]:
                j += 1
            lo, hi = c["tok_off"][i], c["tok_off"][j]
            seen = {}
            for t in range(lo, hi):
                seen.setdefault(rows[t].tobytes(), len(seen))
            order = sorted(seen, key=seen.get)
            first = [lo + next(t - lo for t in range(lo, hi) if rows[t].tobytes() == k) for k in order]
            tt.append(c["tok_type"][first]); ids.append(c["ids"][first]); f.append(c["f"][first])
            idx.append(np.array([seen[rows[t].tobytes()] for t in range(lo, hi)], np.uint16))
            base[i:j] = n_dict
            n_dict += len(order)
            i = j
        out = dict(c, tok_type=np.concatenate(tt), ids=np.concatenate(ids), f=np.concatenate(f),
                   tok_idx=np.concatenate(idx), tok_base=base)
        return out

    @unittest.skipUnless(MODULES, "az_bench_native not built")
    def test_compact_same_batches(self):
        """--compact-samples: a compact Replay (one global token dictionary) fed compact chunks (run dictionaries +
        indices) returns exactly the batches of a plain one fed the copied chunks; Replay.expand_chunk undoes
        compactify; a plain Replay takes compact chunks (expanded) and a compact one copied chunks; with a small
        dictionary every live sample still reads its own tokens; tokens shared across runs are stored once; the
        dictionary's reference counts equal the live samples' references, and freed slots are reused; the compact
        window takes less memory."""
        sp = load()
        TS = native().TokenStore
        rng = np.random.default_rng(6)
        plain = sp.Replay(300, tokens_per_sample=48, actions_per_sample=12)
        comp = sp.Replay(300, tokens_per_sample=48, actions_per_sample=12, compact=True, dict_tokens_per_sample=48,
                         token_store=TS)
        tight = sp.Replay(300, tokens_per_sample=24, actions_per_sample=12, compact=True, dict_tokens_per_sample=3,
                          token_store=TS)
        mixed = sp.Replay(300, tokens_per_sample=48, actions_per_sample=12)   # gets compact chunks
        mixed2 = sp.Replay(300, tokens_per_sample=48, actions_per_sample=12, compact=True, dict_tokens_per_sample=48,
                           token_store=TS)
        shared = c0 = None
        flat, first = [], 0
        for _ in range(10):
            S = int(rng.integers(20, 60))
            c = chunk(rng, S, first)
            c["run"] = (np.arange(S) // 5 + first).astype(np.uint64)
            if c0 is None:
                c0 = c
            # Tokens shared across runs (a card in every deck): each sample's last token is the same one.
            last = c["tok_off"][1:] - 1
            for key in ("tok_type", "ids", "f"):
                c[key][last] = c0[key][0]
            # Runs share tokens: every sample of a run repeats some of the run's first sample's tokens.
            for i in range(S):
                r0 = c["tok_off"][i - i % 5]
                lo, hi = c["tok_off"][i], c["tok_off"][i + 1]
                k = min(hi - lo, c["tok_off"][i - i % 5 + 1] - r0) // 2
                for key in ("tok_type", "ids", "f"):
                    c[key][lo:lo + k] = c[key][r0:r0 + k]
            cc = self.compactify(c)
            self.assertLess(len(cc["tok_type"]), len(c["tok_type"]))
            back = sp.Replay.expand_chunk(cc)
            for key in ("tok_type", "ids", "f"):
                np.testing.assert_array_equal(back[key], c[key])
            plain.add(c); comp.add(cc); tight.add(cc); mixed.add(cc); mixed2.add(c)
            flat.append(c)
            first += S
            for r in (comp, tight, mixed2):   # reference counts = the live samples' token references
                live = (r.s_tail + np.arange(len(r))) % r.cs
                nt = r.ntok[live].astype(np.int64)
                cols = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
                refs = r.tok_idx[(np.repeat(r.idx_start[live], nt) + cols) % r.ci]
                want = np.bincount(refs, minlength=r.store.capacity)
                np.testing.assert_array_equal(r.store.refs(), want)
                self.assertEqual(r.store.used, int((want > 0).sum()))
                self.assertEqual(len(set(refs[np.cumsum(nt) - 1].tolist())), 1)   # the shared token: one slot
        self.assertEqual(len(plain), len(comp))
        self.assertEqual(len(plain), len(mixed))
        self.assertEqual(len(plain), len(mixed2))
        lo = plain.s_tail
        a, b, m, m2 = (r.rows(lo, len(plain)) for r in (plain, comp, mixed, mixed2))
        for key in a:
            np.testing.assert_array_equal(a[key], b[key], key)
            np.testing.assert_array_equal(a[key], m[key], key)
            np.testing.assert_array_equal(a[key], m2[key], key)
        # The tight window keeps fewer samples (dictionary ring full), each read exactly.
        self.assertLess(len(tight), len(plain))
        t = tight.rows(tight.s_tail, len(tight))
        p = plain.rows(tight.s_tail, len(tight))
        for key in t:
            if key in p and p[key].shape == t[key].shape:
                np.testing.assert_array_equal(p[key], t[key], key)
        b1 = comp.sample(np.random.default_rng(9), 64, packed=True)
        b0 = plain.sample(np.random.default_rng(9), 64, packed=True)
        for key in b0:
            np.testing.assert_array_equal(b0[key], b1[key], key)
        self.assertGreater(tight.store.used, 0)
        big_p = sp.Replay(10000)
        big_c = sp.Replay(10000, compact=True, token_store=TS)
        self.assertLess(big_c.nbytes(), 0.5 * big_p.nbytes())

    @unittest.skipUnless(MODULES, "az_bench_native not built")
    def test_save_load_roundtrip(self):
        """--replay-save / --replay-load (2026-11-20): a window saved and loaded into a fresh Replay of the same
        layout gives the same rows, batches and dictionary reference counts, and stays identical while both take
        more chunks (wrap-around, eviction, reused dictionary slots); a different layout or a non-empty window is
        refused."""
        sp = load()
        TS = native().TokenStore
        configs = [dict(tokens_per_sample=24, actions_per_sample=12),
                   dict(tokens_per_sample=24, actions_per_sample=12, compact=True, dict_tokens_per_sample=6,
                        token_store=TS),
                   dict(tokens_per_sample=24, actions_per_sample=12, hp_floors=56, soft_outcome=True, compact=True,
                        dict_tokens_per_sample=6, token_store=TS, compress_targets=True, soft_bytes_per_sample=40,
                        hp_runs_per_sample=0.5)]
        for ci, kw in enumerate(configs):
            rng = np.random.default_rng(40 + ci)
            pool = 300   # shared tokens across chunks: freed and reused dictionary slots
            ptt = rng.integers(0, 9, pool).astype(np.int8)
            pids = rng.integers(0, 50, (pool, 4)).astype(np.int16)
            pf = rng.normal(0, 1, (pool, 64)).astype(np.float16)
            state = {"first": 0}

            def mk():
                S = int(rng.integers(10, 30))
                first = state["first"]
                c = chunk(rng, S, first)
                k = rng.integers(0, pool, len(c["tok_type"]))
                c["tok_type"], c["ids"], c["f"] = ptt[k], pids[k], pf[k]
                c["run"] = (np.arange(S) // 5 + first).astype(np.uint64)
                if kw.get("hp_floors"):
                    c["floor"] = (np.arange(S) % 5 + 1).astype(np.int16)
                    fl = c["floor"].astype(np.int64)
                    hp = rng.integers(0, 80, (S, 56)).astype(np.int16)
                    for i in range(S):   # one HP vector per run
                        hp[i] = hp[i - i % 5]
                    c["hp_floor"] = np.where(np.arange(1, 57)[None, :] >= fl[:, None], hp, -1).astype(np.int16)
                state["first"] += S
                t = rng.dirichlet(np.full(57, 0.3), S).astype(np.float32) if kw.get("soft_outcome") else None
                return (self.compactify(c) if kw.get("compact") else c), t

            def feed(reps, n):
                for _ in range(n):
                    c, t = mk()
                    for r in reps:
                        f0 = r.add(c)
                        if t is not None:
                            r.set_soft_outcome(f0, t)

            def same(a, b):
                self.assertEqual((a.s_tail, a.s_head, a.added), (b.s_tail, b.s_head, b.added))
                ra, rb = a.rows(a.s_tail, len(a)), b.rows(b.s_tail, len(b))
                for key in ra:
                    np.testing.assert_array_equal(np.asarray(ra[key]), np.asarray(rb[key]), err_msg=f"{ci} {key}")
                ba = a.sample(np.random.default_rng(7), 32, 0.5)
                bb = b.sample(np.random.default_rng(7), 32, 0.5)
                for key in ba:
                    np.testing.assert_array_equal(np.asarray(ba[key]), np.asarray(bb[key]), err_msg=f"{ci} {key}")
                if a.compact:
                    np.testing.assert_array_equal(a.store.refs(), b.store.refs())
                    self.assertEqual(a.store.used, b.store.used)

            src = sp.Replay(200, **kw)
            feed([src], 25)   # several times the window: wrapped rings, evicted samples
            self.assertGreater(src.s_tail, 0)
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "replay")
                src.save(path, extra={"step": 5})
                dst = sp.Replay(200, **kw)
                self.assertEqual(dst.load(path), {"step": 5})
                same(src, dst)
                feed([src, dst], 15)   # both continue identically (dictionary free slots and lookups rebuilt)
                same(src, dst)
                with self.assertRaises(ValueError):   # loading into a non-empty window
                    dst.load(path)
                with self.assertRaises(ValueError):   # another layout (--window)
                    sp.Replay(150, **kw).load(path)

    def test_compact_eviction_fuzz(self):
        """Compact Replay with a small dictionary and tokens drawn from a small pool (heavy sharing across chunks,
        so evicting old samples frees tokens the incoming chunk uses): every add either fits or, only for a chunk
        with more distinct tokens than the whole dictionary, raises ValueError; reference counts stay equal to the
        live samples' references and every live sample reads its own tokens."""
        sp = load()
        TS = native().TokenStore
        for seed in range(12):   # seeds 1, 6, 7, 9, 11 hit the stale count_new of the first global version
            rng = np.random.default_rng(seed)
            cs, per = int(rng.integers(40, 200)), int(rng.integers(1, 4))
            pool = int(rng.integers(cs * per // 2, cs * per * 2))   # about the dictionary's size
            ptt = rng.integers(0, 9, pool).astype(np.int8)
            pids = rng.integers(0, 50, (pool, 4)).astype(np.int16)
            pf = rng.normal(0, 1, (pool, 64)).astype(np.float16)
            rep = sp.Replay(cs, tokens_per_sample=24, actions_per_sample=12, compact=True,
                            dict_tokens_per_sample=per, token_store=TS)
            plain = sp.Replay(4000, tokens_per_sample=24, actions_per_sample=12)   # every sample, for the check
            first = 0
            for _ in range(40):
                S = int(rng.integers(5, 40))
                c = chunk(rng, S, first)
                k = rng.integers(0, pool, len(c["tok_type"]))
                c["tok_type"], c["ids"], c["f"] = ptt[k], pids[k], pf[k]
                c["run"] = (np.arange(S) // 4 + first).astype(np.uint64)
                cc = self.compactify(c)
                try:
                    rep.add(cc)
                except ValueError:
                    self.assertGreater(len(np.unique(k)), rep.store.capacity - 16)
                    break
                plain.add(c)
                first += S
                live = (rep.s_tail + np.arange(len(rep))) % rep.cs
                nt = rep.ntok[live].astype(np.int64)
                cols = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
                refs = rep.tok_idx[(np.repeat(rep.idx_start[live], nt) + cols) % rep.ci]
                np.testing.assert_array_equal(rep.store.refs(), np.bincount(refs, minlength=rep.store.capacity))
                if len(rep):
                    got = rep.rows(rep.s_tail, len(rep))
                    want = plain.rows(rep.s_tail, len(rep))
                    for key in ("tok_type", "ids", "f", "mask", "a_type", "outcome"):
                        np.testing.assert_array_equal(got[key], want[key], key)

    @unittest.skipUnless(MODULES, "az_bench_native not built")
    def test_compress_targets(self):
        """--compress-targets: a compressed compact Replay returns the batches of an uncompressed one (per-floor HP
        labels identical: kept once per run; tokens, actions, policy identical), and EMA outcome targets within
        8-bit quantization (|q/255 renormalised - p| < 1/255 + renorm); unset targets are the final outcome; the
        losses agree except the EMA term, which moves only within quantization noise; tight byte / run rings evict
        early but every live sample stays exact; less memory."""
        sp = load()
        TS = native().TokenStore
        rng = np.random.default_rng(21)
        kw = dict(tokens_per_sample=48, actions_per_sample=12, hp_floors=56, soft_outcome=True, compact=True,
                  dict_tokens_per_sample=48, token_store=TS)
        ref = sp.Replay(400, **kw)
        cmp_ = sp.Replay(400, compress_targets=True, soft_bytes_per_sample=60, hp_runs_per_sample=1.0, **kw)
        tight = sp.Replay(400, compress_targets=True, soft_bytes_per_sample=16, hp_runs_per_sample=0.05, **kw)
        # Only the byte ring tight (HP run ring roomy): every eviction comes from overwritten soft bytes.
        tbyte = sp.Replay(400, compress_targets=True, soft_bytes_per_sample=12, hp_runs_per_sample=1.0, **kw)
        tq = []   # (first, exact uint8 quantization) of each set chunk, for an independent check
        first, chunks = 0, []
        for n in range(8):
            S = int(rng.integers(20, 60))
            c = chunk(rng, S, first)
            c["run"] = (np.arange(S) // 6 + first).astype(np.uint64)
            # Per-floor HP as the driver writes it: the run's HP per floor, masked before the sample's floor.
            runs = np.asarray(c["run"])
            c["floor"] = np.zeros(S, np.int16)
            vec = {}
            for i in range(S):
                r = int(runs[i])
                if r not in vec:
                    vec[r] = (rng.integers(0, 120, 56).astype(np.int16), int(rng.integers(0, 40)))
                c["floor"][i] = vec[r][1] + i % 6
            fl = np.clip(c["floor"].astype(np.int64), 1, 56)
            c["hp_floor"] = np.where(np.arange(1, 57)[None, :] >= fl[:, None],
                                     np.stack([vec[int(r)][0] for r in runs]), -1).astype(np.int16)
            cc = self.compactify(c)
            fr = [r.add(cc) for r in (ref, cmp_, tight, tbyte)]
            if n % 3 != 2:   # some chunks keep their final-outcome targets (set_soft_outcome not called)
                t = rng.dirichlet(np.full(57, 0.3), S).astype(np.float32)
                for r, f0 in zip((ref, cmp_, tight), fr):
                    r.set_soft_outcome(f0, t)
            # tbyte: every chunk set, intervals ~57 bytes > 12 per sample, so the byte ring wraps repeatedly.
            tb = rng.dirichlet(np.full(57, 0.3), S).astype(np.float32)
            tbyte.set_soft_outcome(fr[3], tb)
            q = np.rint(tb.astype(np.float64) * 255.0)
            tq.append((fr[3], q / q.sum(-1, keepdims=True)))
            first += S
        self.assertEqual(len(ref), len(cmp_))
        a = ref.rows(ref.s_tail, len(ref))
        b = cmp_.rows(ref.s_tail, len(ref))
        for key in a:
            if key != "soft_outcome":
                np.testing.assert_array_equal(a[key], b[key], key)
        np.testing.assert_allclose(b["soft_outcome"].sum(-1), 1.0, atol=1e-5)
        self.assertLess(float(np.abs(a["soft_outcome"] - b["soft_outcome"]).max()), 0.02)
        unset = a["soft_outcome"].max(-1) == 1.0
        self.assertTrue(unset.any())
        np.testing.assert_array_equal(a["soft_outcome"][unset], b["soft_outcome"][unset])
        self.assertLess(cmp_.soft_stats[1] / cmp_.soft_stats[0], 57)   # the nonzero interval only
        # Tight rings: fewer samples, each exact.
        self.assertLess(len(tight), len(ref))
        t = tight.rows(tight.s_tail, len(tight))
        u = cmp_.rows(tight.s_tail, len(tight))
        for key in t:
            np.testing.assert_array_equal(t[key], u[key], key)
        # Tight byte ring: evicted through overwritten soft bytes only; every live sample's EMA target is exactly its
        # own quantized target (an under-evicted sample would decode another sample's bytes).
        self.assertLess(len(tbyte), len(ref) // 2)   # bounded by the byte ring (12 of ~57 bytes per sample)
        v = tbyte.rows(tbyte.s_tail, len(tbyte))
        want = np.concatenate([q for _, q in tq])[-len(tbyte):]
        np.testing.assert_allclose(v["soft_outcome"], want, rtol=0, atol=1e-6)
        # Losses: equal but for the EMA term, which moves within quantization noise.
        torch.manual_seed(0)
        net = sp.amber_net.AmberNet(64, 2, hp_floors=56)
        la = sp.losses(net, sp.to_torch(a, torch.device("cpu")), 1.0, 1.0, 1.0, 1.0)[1]
        lb = sp.losses(net, sp.to_torch(b, torch.device("cpu")), 1.0, 1.0, 1.0, 1.0)[1]
        for k in la:
            if k == "outcome_ema":
                self.assertLess(abs(float(la[k]) - float(lb[k])), 0.02 * float(la[k]) + 1e-3, k)
            else:
                self.assertEqual(float(la[k]), float(lb[k]), k)
        self.assertLess(cmp_.nbytes(), ref.nbytes())

    @unittest.skipUnless(MODULES, "az_bench_native not built")
    def test_token_store(self):
        """TokenStore (the global dictionary): random intern / release against a model. Equal tokens share a slot
        while referenced, reference counts and used slots match, released slots are reused, a full store throws and
        the slots' contents are the tokens (many deletions exercise the table's backward-shift deletion)."""
        TS = native().TokenStore
        rng = np.random.default_rng(11)
        pool = 300
        tt = rng.integers(0, 9, pool).astype(np.int8)
        ids = rng.integers(0, 50, (pool, 4)).astype(np.int16)
        f = rng.normal(0, 1, (pool, 64)).astype(np.float16)
        st = TS(120)
        vt, vi, vf = st.views()
        slot_of, refs = {}, {}
        held = []   # slots referenced, one entry per reference
        for step in range(400):
            if rng.random() < 0.55 or not held:
                k = rng.choice(pool, int(rng.integers(1, 12)), replace=True)
                uk, cnt = np.unique(k, return_counts=True)
                new = sum(1 for x in uk if x not in slot_of)
                if new > st.free:
                    with self.assertRaises(RuntimeError):
                        st.intern(tt[uk], ids[uk], f[uk].view(np.uint16), cnt.astype(np.int64))
                    break
                self.assertGreaterEqual(st.count_new(tt[uk], ids[uk], f[uk].view(np.uint16), cnt.astype(np.int64)), new)
                sl = st.intern(tt[uk], ids[uk], f[uk].view(np.uint16), cnt.astype(np.int64))
                for x, s_, c in zip(uk, sl, cnt):
                    if x in slot_of:
                        self.assertEqual(s_, slot_of[x])
                    slot_of[x] = int(s_)
                    refs[x] = refs.get(x, 0) + int(c)
                    held += [int(x)] * int(c)
            else:
                drop = rng.choice(len(held), int(rng.integers(1, min(len(held), 20) + 1)), replace=False)
                xs = [held[i] for i in drop]
                st.release(np.array([slot_of[x] for x in xs], np.int32))
                for i in sorted(drop, reverse=True):
                    held.pop(i)
                for x in xs:
                    refs[x] -= 1
                    if refs[x] == 0:
                        del refs[x], slot_of[x]
            self.assertEqual(st.used, len(slot_of))
            r = st.refs()
            for x, s_ in slot_of.items():
                self.assertEqual(r[s_], refs[x])
                self.assertEqual(vt[s_], tt[x])
                np.testing.assert_array_equal(vi[s_], ids[x])
                np.testing.assert_array_equal(vf[s_], f[x])
            self.assertEqual(int(r.sum()), len(held))
        self.assertGreater(len(slot_of), 0)
        with self.assertRaises(RuntimeError):   # a slot without references cannot be released
            st.release(np.array([-1], np.int32))

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
    if "relics_sum" in e:   # every run ends with its starter relic and a non-empty deck
        tc.assertGreaterEqual(e["relics_sum"], n)
        tc.assertGreaterEqual(e["deck_size_sum"], n)
    if "chests" in e:   # economy counters (2026-11-19)
        tc.assertLessEqual(e["chests_skipped"], e["chests"])
        tc.assertGreater(e["gold_gained"], 0)   # reward gold
        for k in ("gold_lost", "relics_taken_elite", "relics_taken_chest", "relics_taken_other", "relics_left_elite",
                  "relics_left_other", "sapphire_relic_forfeits", "shops", "shop_cards", "shop_relics", "shop_potions", "shop_removes",
                  "boss_relic_skips"):
            tc.assertGreaterEqual(e[k], 0)


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

    def test_per_run_means(self):
        sp = load()
        pw = {"0": {"runs": 3, "relics_sum": 9, "deck_size_sum": 60}, "1": {"runs": 1, "relics_sum": 7, "deck_size_sum": 20}}
        self.assertEqual(sp.per_run_means(pw), (4.0, 20.0))
        self.assertEqual(sp.per_run_means({}), (None, None))
        self.assertEqual(sp.per_run_means({"0": {"runs": 2, "ruby": 1}}), (None, None))   # driver without the counters

    def test_economy_per_run(self):
        sp = load()
        e0 = {k: 2 for k in sp.ECONOMY_KEYS}; e0["runs"] = 1
        e1 = {k: 4 for k in sp.ECONOMY_KEYS}; e1["runs"] = 2
        self.assertEqual(sp.economy_per_run({"0": e0, "1": e1}), {k: 2.0 for k in sp.ECONOMY_KEYS})
        self.assertIsNone(sp.economy_per_run({}))
        self.assertIsNone(sp.economy_per_run({"0": {"runs": 2, "ruby": 1}}))   # driver without the counters


class MallocTrimTest(unittest.TestCase):
    def test_trim_and_rss(self):
        sp = load()
        if not sys.platform.startswith("linux"):
            self.skipTest("glibc only")
        self.assertTrue(sp.malloc_trim())
        self.assertGreater(sp.rss_gb(), 0)


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
        self.assertNotIn("Forced key moves", page)
        fk = dict(rows[-1], force_keys={"active": True, "sapphire": 3, "ruby": 2, "emerald": 4, "route_masked": 5})
        page = dash.page(rows[:-1] + [fk], "t", "")
        self.assertIn("Forced key moves", page)
        self.assertIn("Sapphire 3 / Ruby 2 / Emerald 4; routes narrowed 5; on (until the first step-up)", page)
        self.assertNotIn("Relic sources and relics left behind", page)
        sp = load()
        eco = dict(rows[-1], economy_per_run={k: 1.0 for k in sp.ECONOMY_KEYS})
        page = dash.page(rows[:-1] + [eco], "t", "")
        self.assertIn("Relic sources and relics left behind (per run, from run 300)", page)
        self.assertIn("relics not picked up (left + chests not opened)", page)


class DashboardRecentTest(unittest.TestCase):
    def test_recent_cut_after_curriculum_trim(self):
        """The top charts cover the last RECENT_RUNS runs of the charted (curriculum) rows, also when A20 rows precede
        the curriculum: x values come from the trimmed rows."""
        spec = importlib.util.spec_from_file_location(
            "selfplay_dashboard", os.path.join(ROOT, "tools", "az_bench", "selfplay_dashboard.py"))
        dash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dash)
        rows = []
        for i in range(300):   # 100 A20 rows, then 200 curriculum rows at A1; 1,000 runs per row
            m, sec = divmod(i * 30, 60)
            h, m = divmod(m, 60)
            rows.append({"time": f"2026-11-19 {10 + h:02d}:{m:02d}:{sec:02d}", "runs_done": 1000 * (i + 1),
                         "samples_added": 1000 * (i + 1), "mean_floor_window": 40.0, "win_rate_window": 0.05,
                         "runs_window": 300, "positions_per_s": 140000, "train_steps": i,
                         "ascension": 20 if i < 100 else 1})
        page = dash.page(rows, "t", "")
        self.assertIn("Last 100,000 runs", page)
        self.assertIn("Full history", page)
        # top grid: x axis starts at 200,000 (last 100k of 300,000); full grid: at the first curriculum row, 101,000
        top, full = page.split("Full history", 1)
        # tick labels: top grid starts at 200000 (last 100k of 300k), full grid at the first curriculum row, 101000
        self.assertIn('class="tick">200000</text>', top)
        self.assertNotIn('class="tick">101000</text>', top)
        self.assertIn('class="tick">101000</text>', full)

    def test_forced_by_class_tile(self):
        spec = importlib.util.spec_from_file_location(
            "selfplay_dashboard", os.path.join(ROOT, "tools", "az_bench", "selfplay_dashboard.py"))
        dash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dash)
        row = {"time": "2026-11-19 23:00:00", "runs_done": 1000, "samples_added": 1000, "mean_floor_window": 40.0,
               "win_rate_window": 0.05, "runs_window": 300, "positions_per_s": 140000, "train_steps": 1,
               "ascension": 1, "forced_picks": 7, "explore_roots": 9, "ooc_roots": 90,
               "forced_by_class": [3, 0, 2, 0, 1, 1, 0, 0]}
        page = dash.page([row], "t", "")
        self.assertIn("Forced by class", page)
        self.assertIn("card 3 / relic 2 / event 1 / rest 1", page)
        self.assertNotIn("Forced by class", dash.page([dict(row, forced_by_class=None)], "t", ""))


class DashboardSettlingTest(unittest.TestCase):
    def test_restart_windows_left_out(self):
        spec = importlib.util.spec_from_file_location(
            "selfplay_dashboard", os.path.join(ROOT, "tools", "az_bench", "selfplay_dashboard.py"))
        dash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dash)
        rows, added = [], 0
        for i in range(60):   # two processes, one row per 30 s; the second starts at row 40
            if i == 40:
                added = 0
            added += 1000
            m, sec = divmod(i * 30, 60)
            rows.append({"time": f"2026-11-19 13:{m:02d}:{sec:02d}", "samples_added": added})
        mask = dash.settling(rows, minutes=15)
        # first row at 13:00:00 counts from 12:59:30: rows up to 13:14:00 settle (29 rows), then 13:14:30 is kept
        self.assertEqual(mask[:30], [True] * 29 + [False])
        self.assertFalse(any(mask[30:40]))
        self.assertTrue(all(mask[40:60]))   # 13:20 .. 13:29:30, all within 15 min of the restart
        self.assertEqual(dash.settling([{"time": "bad"}]), [False])
        self.assertEqual(dash.SETTLE_MINUTES, 5)
        # the mask only blanks the floor / win-rate curves: the death-floor histogram keeps settling rows
        base = {"positions_per_s": 1, "moves_per_s": 1, "runs_window": 10, "win_rate_window": 0.5,
                "mean_floor_window": 30, "wins_total": 0, "train_steps": 1, "stalls": 0, "runs_done": 10}
        page = dash.page([dict(base, time="2026-11-19 13:00:00", samples_added=1, death_floors_window={"7": 3})],
                         "t", "")
        self.assertIn("restart (1)", page)
        self.assertIn('height="192.0"', page)   # the death-floor bar of the settling row (full height)
        self.assertIn("<h2>Mean final floor per window</h2><p class=\"empty\">No data yet.", page)


@unittest.skipUnless(HAVE_TORCH and MODULES, "torch or the az_bench_native module (cmake target) missing")
class SelfplaySmoke(unittest.TestCase):
    def test_replay_save_load_and_ascension_file(self):
        """--replay-save at the final stop, --replay-load on resume from that checkpoint: the window continues
        (replay_loaded, samples_added carried on); a window saved at another step is not loaded (empty window, the run
        continues); an ASCENSION file sets the ascension of later runs and is renamed .applied."""
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2", "--seed-base", "520", "--ascension", "1"]
        with tempfile.TemporaryDirectory() as d:
            rep = os.path.join(d, "replay")
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "12", "--replay-save", rep]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            with open(os.path.join(rep, "state.json")) as f:
                st = json.load(f)
            ck = st["extra"]["checkpoint"]
            n_saved = st["scalars"]["s_head"] - st["scalars"]["s_tail"]
            self.assertGreater(n_saved, 0)
            with open(os.path.join(d, "ASCENSION"), "w") as f:
                f.write("3\n")
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "20", "--resume", ck,
                                               "--replay-load", rep]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows2 = [json.loads(l) for l in f][len(rows):]
            self.assertEqual(rows2[0]["replay_loaded"], n_saved)
            self.assertGreaterEqual(rows2[0]["samples_added"], st["scalars"]["added"])
            self.assertTrue(os.path.exists(os.path.join(d, "ASCENSION.applied")))
            self.assertFalse(os.path.exists(os.path.join(d, "ASCENSION")))
            self.assertEqual(rows2[-1]["ascension"], 3)
            self.assertEqual(torch.load(sorted(glob.glob(os.path.join(d, "ckpt_*.pt")),
                                               key=os.path.getmtime)[-1])["counters"]["ascension"], 3)
            # the saved window is from the first run's final step: resuming the second run's checkpoint skips it
            ck2 = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "24", "--resume", ck2,
                                               "--replay-load", rep]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows3 = [json.loads(l) for l in f][len(rows) + len(rows2):]
            self.assertEqual(rows3[0]["replay_loaded"], 0)
            self.assertGreater(rows3[-1]["samples_added"], 0)   # the run trains on with a fresh window
            # another layout (--window): refused before any array is written
            ck3 = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            other = os.path.join(d, "replay_other")
            sp.Replay(4000).save(other, extra={"step": torch.load(ck3)["counters"]["step"]})
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "28", "--resume", ck3,
                                               "--replay-load", other]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows4 = [json.loads(l) for l in f][len(rows) + len(rows2) + len(rows3):]
            self.assertEqual(rows4[0]["replay_loaded"], 0)

    def test_utility_amber2_switch_keeps_replay(self):
        """--utility amber2 (2026-11-20): a run trained with --utility amber resumes with amber2 and its saved replay
        window (same heads and layout), plays and trains."""
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2", "--seed-base", "540"]
        with tempfile.TemporaryDirectory() as d:
            rep = os.path.join(d, "replay")
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "12", "--utility", "amber",
                                               "--replay-save", rep]), 0)
            with open(os.path.join(rep, "state.json")) as f:
                st = json.load(f)
            n_saved = st["scalars"]["s_head"] - st["scalars"]["s_tail"]
            with open(os.path.join(d, "metrics.jsonl")) as f:
                n0 = len(f.readlines())
            self.assertEqual(sp.main(common + ["--out-dir", d, "--max-runs", "24", "--utility", "amber2",
                                               "--resume", st["extra"]["checkpoint"], "--replay-load", rep]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f][n0:]
            self.assertEqual(rows[0]["replay_loaded"], n_saved)
            self.assertGreaterEqual(rows[-1]["runs_done"], 24)
            self.assertGreater(rows[-1]["train_steps"], rows[0]["train_steps"])
            self.assertTrue(any(r["loss"] and r["loss"].get("hp_floor", 0) > 0 for r in rows))

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

    def test_soft_policy_and_explore_amber_run(self):
        """--w-soft-policy trains the soft head in a real run (loss logged, head in the checkpoint; the inference copy
        and the EMA / eval calls take the 4 usual outputs); --explore-amber explores and forces picks in the same run
        and is refused together with --explore-c."""
        sp = load()
        common = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                  "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                  "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                  "--report", "1", "--sync-steps", "2", "--max-runs", "16"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(common + ["--out-dir", d, "--seed-base", "900", "--w-soft-policy", "8",
                                               "--value-ema-halflife", "20", "--explore-amber",
                                               "--pick-target", "0.2"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreater(rows[-1]["train_steps"], 0)
            self.assertTrue(any(r["loss"] and r["loss"].get("soft_policy", 0) > 0 for r in rows))
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertIn("pol_soft.2.weight", torch.load(ck)["net"])
            self.assertGreater(rows[-1]["explore_roots"], 0)
            self.assertGreater(rows[-1]["forced_picks"], 0)
            # per-class counters (2026-11-19) partition the forced picks
            self.assertEqual(len(rows[-1]["forced_by_class"]), 8)
            self.assertEqual(sum(rows[-1]["forced_by_class"]), rows[-1]["forced_picks"])
            ex = rows[-1]["explore_amber"]
            self.assertGreater(ex["attempts"], 0)
            self.assertEqual(ex["natural_unplayed"], 0)   # only items the search played count as natural
            # c = 0 needs natural >= need while the item counts as under target: only a cross-thread read race
            self.assertLessEqual(ex["c_zero"], max(1, ex["attempts"] // 20))
        with tempfile.TemporaryDirectory() as d, self.assertRaises(Exception):
            sp.main(common + ["--out-dir", d, "--seed-base", "950", "--explore-amber", "--explore-c", "0.5"])

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

    def test_candidate_flags(self):
        """--full-candidates / --fast-candidates reach RunDriver (defaults 16 / 4 when not given)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "1", "--games", "2",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "710", "--max-runs", "2"]
        sys.path.insert(0, os.path.dirname(MODULES[0]))
        import az_bench_native
        real, seen = az_bench_native.RunDriver, []

        def spy(*a, **kw):
            seen.append(kw)
            return real(*a, **kw)
        az_bench_native.RunDriver = spy
        try:
            for extra, want in (([], (16, 4)), (["--full-candidates", "8", "--fast-candidates", "2"], (8, 2))):
                seen.clear()
                with tempfile.TemporaryDirectory() as d:
                    self.assertEqual(sp.main(args + extra + ["--out-dir", d]), 0)
                self.assertEqual((seen[0]["full_candidates"], seen[0]["fast_candidates"]), want)
        finally:
            az_bench_native.RunDriver = real

    def test_amber_search_flags(self):
        """--chance-on-reveal / --cross-combat / --sim-help / --max-pending 0 reach the driver, play and train; the
        driver's counters show each rule acting (deterministic and chance OOC edges, fights inside the search,
        reward gold taken automatically)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1700", "--max-runs", "8", "--test-max-hp", "900",
                "--chance-on-reveal", "--cross-combat", "--sim-help", "--max-pending", "0"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertGreaterEqual(last["runs_done"], 8)
            self.assertGreater(last["train_steps"], 0)
            det, chance = last["ooc_edges_det_chance"]
            self.assertGreater(det, 0)
            self.assertGreater(chance, 0)
            self.assertGreater(last["tree_fight_starts"], 0)
            self.assertGreater(last["tree_fight_exits"], 0)
            self.assertGreater(last["auto_gold"], 0)
            a = torch.load(sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1])["args"]
            self.assertTrue(a["chance_on_reveal"] and a["cross_combat"] and a["sim_help"])
            self.assertEqual(a["max_pending"], 0)

    def test_compact_samples_run(self):
        """--compact-samples with --max-pending 0: the driver hands out compact chunks (indices inside their run
        dictionaries, a dictionary shared by many samples), the run plays, trains and reports the window's memory."""
        sp = load()
        import importlib
        sys.path.insert(0, os.path.dirname(MODULES[0]))
        nat = importlib.import_module("az_bench_native")
        drv = nat.RunDriver(workers=1, games=2, seed_base=1950, max_runs=2, ascension=20, full_sims=8, fast_sims=4,
                            full_candidates=4, fast_candidates=2, max_pending=0, sim_help=True,
                            compact_samples=True)
        R, T, A = 8, 212, 96
        views = {"tok_type": np.zeros(R * T, np.int8), "ids": np.zeros(R * T * 4, np.int16),
                 "f": np.zeros(R * T * 64, np.float16), "mask": np.zeros(R * T, np.bool_),
                 "a_type": np.zeros(R * A, np.int16), "a_src": np.zeros(R * A, np.int16),
                 "a_tgt": np.zeros(R * A, np.int16), "a_f": np.zeros(R * A * 8, np.float16),
                 "a_mask": np.zeros(R * A, np.bool_)}
        rng = np.random.default_rng(0)
        chunks = []
        drv.start()
        try:
            while drv.stats()["runs_done"] < 2:
                got = drv.next_flat(R, 1, 5, [R], [T], [A], views)
                if got is None:
                    continue
                ticket, rows, _, _, Ap = got
                drv.submit(ticket, rng.normal(0, 1, (rows, Ap)).astype(np.float32), rng.random(rows).astype(np.float32),
                           np.full(rows, 40, np.float32))
                c = drv.take_samples()
                if c is not None:
                    chunks.append(c)
        finally:
            drv.stop()
        c = drv.take_samples()
        if c is not None:
            chunks.append(c)
        self.assertTrue(chunks)
        for c in chunks:
            self.assertIn("tok_idx", c)
            nt = np.diff(c["tok_off"])
            src = np.repeat(c["tok_base"], nt) + c["tok_idx"].astype(np.int64)
            self.assertTrue((src < len(c["tok_type"])).all())
            self.assertLess(len(c["tok_type"]), int(nt.sum()))   # tokens shared across a run's samples
            self.assertEqual(len(c["ids"]), len(c["tok_type"]))
            e = sp.Replay.expand_chunk(c)
            self.assertEqual(len(e["tok_type"]), int(nt.sum()))
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1960", "--max-runs", "8", "--test-max-hp", "900",
                "--sim-help", "--max-pending", "0", "--compact-samples"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertGreaterEqual(last["runs_done"], 8)
            self.assertGreater(last["train_steps"], 0)
            self.assertGreater(last["replay"], 0)
            self.assertLess(last["replay_gb"], sp.Replay(5000, hp_floors=0).nbytes() / 2 ** 30)
            self.assertGreater(last["replay_dict_used"], 0)
        # With Amber's target compression (EMA targets 8-bit, per-floor HP once per run) and a smaller ring layout.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d, "--seed-base", "1970", "--utility", "amber",
                                             "--value-ema-halflife", "20", "--value-ema-search", "--compress-targets",
                                             "--replay-tokens-per-sample", "40", "--replay-actions-per-sample", "8"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertGreater(last["train_steps"], 0)
            self.assertGreater(last["replay_soft_bytes_mean"], 0)
            self.assertLess(last["replay_soft_bytes_mean"], 57)
            self.assertIn("outcome_ema", last["loss"])
            rr = last["replay_rings"]
            self.assertTrue(0 < rr["tok_mean"] <= rr["tok_max"] and 0 < rr["act_mean"] <= rr["act_max"])   # max may
            # exceed the per-sample ring share (the rings are shared; the mean decides)
            self.assertTrue(0 < rr["tok_ring_fill"] <= 1 and 0 < rr["act_ring_fill"] <= 1)

    def test_savescum(self):
        """--savescum reaches the driver: runs play it and every checked search child equals the real next state; a
        file SAVESCUM_OFF turns it off for new runs and is recorded, so a resume stays off."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1800", "--max-runs", "8",
                "--chance-on-reveal", "--cross-combat", "--sim-help", "--savescum"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            ss = last["savescum"]
            self.assertTrue(ss["active"])
            self.assertGreaterEqual(ss["runs"], 8)
            self.assertGreater(ss["checks"], 0)
            self.assertEqual(ss["mismatches"], 0)
            self.assertEqual(last["ooc_edges_det_chance"], [0, 0])   # nothing tested or resampled
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertFalse(torch.load(ck)["counters"].get("savescum_off", False))
            # SAVESCUM_OFF before the resume: off from the first report, kept in the counters.
            open(os.path.join(d, "SAVESCUM_OFF"), "w").close()
            self.assertEqual(sp.main(args[:-5] + ["12", "--chance-on-reveal", "--cross-combat", "--sim-help",
                                                  "--savescum", "--out-dir", d, "--resume", ck]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertFalse(last["savescum"]["active"])
            self.assertEqual(last["savescum"]["runs"], 0)   # the file was there at start: no run played savescum
            ck2 = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertTrue(torch.load(ck2)["counters"]["savescum_off"])
            # A resume from that checkpoint starts with savescum off.
            os.remove(os.path.join(d, "SAVESCUM_OFF"))
            self.assertEqual(sp.main(args[:-5] + ["14", "--chance-on-reveal", "--cross-combat", "--sim-help",
                                                  "--savescum", "--out-dir", d, "--resume", ck2]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                last = [json.loads(l) for l in f][-1]
            self.assertFalse(last["savescum"]["active"])
            self.assertEqual(last["savescum"]["runs"], 0)

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

    def test_value_ema_search_run(self):
        """--value-ema-search: the driver hands out search-backed distributions and EMA targets; the replay trains
        on them (no net forward for D_t)."""
        sp = load()
        sp.TAKE_CHUNK = 1
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "750", "--max-runs", "16",
                "--value-ema-halflife", "8", "--value-ema-search", "--eval-cache", "--merge-cards", "--packed-h2d",
                "--utility", "amber"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            last = rows[-1]
            self.assertGreater(last["train_steps"], 0)
            self.assertTrue(last["value_ema"]["search"])
            self.assertEqual(last["value_ema"]["moves"], "full")
            self.assertEqual(last["value_ema"]["labelled"], last["samples_added"])
            self.assertGreater(last["value_ema"]["real_weight_mean"], 0)
            self.assertLess(last["value_ema"]["real_weight_mean"], 1)
            self.assertTrue(any(r["loss"] and "outcome_ema" in r["loss"] for r in rows))
        with self.assertRaises(SystemExit):   # needs a half-life
            sp.main(args[:args.index("--value-ema-halflife")] + ["--value-ema-search", "--out-dir", "/nonexistent"])

    def test_value_ema_search_driver(self):
        """Driver level (every searched move kept): the EMA targets are the recursion of ema_outcome_targets over
        the chain moves' search-backed distributions (full moves only, or all searched moves), a fast move outside
        the full-only chain takes the next full move's target, the final outcome's weight is lam ** (chain moves
        after + 1), and with hp weights 0 each search value is F of its search-backed distribution."""
        for full_only in (True, False):
            with self.subTest(full_only=full_only):
                self._ema_search_driver(full_only)

    def _ema_search_driver(self, full_only):
        sp = load()
        import importlib
        sys_path = os.path.dirname(MODULES[0])
        import sys
        sys.path.insert(0, sys_path)
        nat = importlib.import_module("az_bench_native")
        lam = 0.8
        drv = nat.RunDriver(workers=1, games=2, seed_base=760, max_runs=3, ascension=20, full_sims=8, fast_sims=4,
                            full_candidates=4, fast_candidates=2, keep_full=1.0, keep_fast=1.0,
                            hp_weight_combat=0.0, hp_weight_ooc=0.0, search_ema_lambda=lam,
                            search_ema_full_only=full_only)
        R, T, A = 8, 212, 96
        views = {"tok_type": np.zeros(R * T, np.int8), "ids": np.zeros(R * T * 4, np.int16),
                 "f": np.zeros(R * T * 64, np.float16), "mask": np.zeros(R * T, np.bool_),
                 "a_type": np.zeros(R * A, np.int16), "a_src": np.zeros(R * A, np.int16),
                 "a_tgt": np.zeros(R * A, np.int16), "a_f": np.zeros(R * A * 8, np.float16),
                 "a_mask": np.zeros(R * A, np.bool_)}
        rng = np.random.default_rng(0)
        fv = np.arange(57, dtype=np.float64)
        fv[0] = 57.0
        fv /= 57.0
        chunks = []
        drv.start()
        try:
            while drv.stats()["runs_done"] < 3:
                got = drv.next_flat(R, 1, 5, [R], [T], [A], views)
                if got is None:
                    continue
                ticket, rows, _, _, Ap = got
                p = rng.random((rows, 57)) + 1e-3
                p /= p.sum(1, keepdims=True)
                drv.submit(ticket, rng.normal(0, 1, (rows, Ap)).astype(np.float32), (p @ fv).astype(np.float32),
                           np.full(rows, 40, np.float32), None, 0, p.astype(np.float32))
                c = drv.take_samples()
                if c is not None:
                    chunks.append(c)
        finally:
            drv.stop()
        c = drv.take_samples()
        if c is not None:
            chunks.append(c)
        cat = {k: np.concatenate([x[k] for x in chunks]) for k in ("search_dist", "outcome_target", "outcome",
                                                                     "run", "search_value", "ema_real_weight",
                                                                     "has_policy")}
        self.assertGreater(len(cat["run"]), 10)
        np.testing.assert_allclose(cat["search_dist"].sum(1), 1, atol=1e-5)
        np.testing.assert_allclose(cat["search_dist"].astype(np.float64) @ fv, cat["search_value"], atol=1e-5)
        # Reference: the chain moves (full = has a policy target), then off-chain moves take the next chain target.
        chain = cat["has_policy"].astype(bool) if full_only else np.ones(len(cat["run"]), bool)
        self.assertTrue(chain.any() and (not full_only or not chain.all()))
        ct, cw = sp.ema_outcome_targets(cat["search_dist"][chain], cat["outcome"][chain], cat["run"][chain], lam)
        tgt = np.zeros_like(cat["outcome_target"])
        real_w = np.zeros(len(tgt), np.float32)
        nxt_t, nxt_w, nxt_run = None, None, None
        ci = int(chain.sum())
        for i in range(len(tgt) - 1, -1, -1):
            if nxt_run != cat["run"][i]:   # a new run (from its end): the final outcome
                nxt_run = cat["run"][i]
                nxt_t = np.eye(57, dtype=np.float32)[int(cat["outcome"][i])]
                nxt_w = 1.0
            if chain[i]:
                ci -= 1
                nxt_t, nxt_w = ct[ci], cw[ci]
            tgt[i], real_w[i] = nxt_t, nxt_w
        # float16 chain distributions: ~1e-3 relative error per term.
        np.testing.assert_allclose(cat["outcome_target"], tgt, atol=2e-3)
        np.testing.assert_allclose(cat["ema_real_weight"], real_w, rtol=1e-4)

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
        self.assertGreater(e["chests"], 0)   # economy counters: every act has a treasure row and shops are common
        self.assertGreater(e["shops"], 0)
        self.assertLessEqual(e["sapphire_relic_forfeits"], e["sapphire"])   # one Sapphire key per run
        self.assertGreater(e["elites"], 0)

    def test_heart_log(self):
        """--heart-log 1 (diagnostic): every run that fought the Heart leaves one record in heart_runs.jsonl.gz with
        its entry state and the net's / search's values per act and at the Heart; the count matches the progress
        counter `heart`. One worker, no training (--min-replay above the runs' samples) and a fixed --seed make the
        play deterministic; in this setting seed 1301 reaches the Heart (review of PR #1111)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "1", "--games", "3",
                "--full-sims", "4", "--fast-sims", "2", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "1000000", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1300", "--max-runs", "6", "--seed", "3",
                "--ascension", "0", "--test-max-hp", "3000", "--utility", "amber", "--value-ema-halflife", "20",
                "--value-ema-search", "--curriculum", "--force-keys", "curriculum"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--heart-log", "1", "--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            path = os.path.join(d, "heart_runs.jsonl.gz")
            recs = []
            if os.path.exists(path):
                with gzip.open(path, "rt") as f:
                    recs = [json.loads(l) for l in f]
        heart = sum(r["progress_window"].get("0", {}).get("heart", 0) for r in rows)
        self.assertGreater(heart, 0, "the test setting should reach the Heart")
        self.assertEqual(len(recs), heart)
        self.assertEqual(rows[-1]["heart_log"]["records"], heart)
        self.assertEqual(len({r["seed"] for r in recs}), len(recs))
        for r in recs:
            self.assertEqual(r["asc"], 0)
            self.assertIn(r["win"], (0, 1))
            self.assertEqual(r["root_floor"][4], r["floor"])   # the Heart fight's first searched move
            self.assertTrue(all(0 <= f <= r["floor"] for f in r["root_floor"]))
            self.assertEqual(r["root_floor"], sorted(r["root_floor"]))
            for k in ("net_p_win", "net_p_heart_death", "search_p_win"):
                self.assertEqual(len(r[k]), 5)
                self.assertTrue(all(0.0 <= x <= 1.0 for x in r[k]), k)
            self.assertTrue(all(1.0 <= x <= 57.0 for x in r["net_e_floor"]))
            self.assertGreater(r["entry_hp"], 0)
            self.assertLessEqual(r["entry_hp"], r["entry_max_hp"])
            self.assertEqual(r["floor_hp"][r["floor"] - 2], r["entry_hp"])   # HP at the end of the floor before
            self.assertEqual(r["heart_hp"] == 0, r["win"] == 1)
            self.assertEqual(r["end_hp"] > 0, r["win"] == 1)
            self.assertGreater(len(r["deck"]), 0)
            self.assertGreater(len(r["relics"]), 0)
            self.assertEqual(len(r["floor_hp"]), 56)

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

    def test_nonfinite_step_skipped(self):
        """A training step with a NaN loss is skipped (no optimizer step): the weights stay finite, the skip is
        counted in metrics and checkpoint counters, and grad_norm is logged for the finite steps."""
        sp = load()
        real = sp.losses
        calls = {"n": 0}

        def poisoned(*a, **k):
            loss, parts = real(*a, **k)
            calls["n"] += 1
            if calls["n"] in (2, 5):
                loss = loss * float("nan")
            return loss, parts

        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1500", "--max-runs", "16"]
        sp.losses = poisoned
        try:
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
                with open(os.path.join(d, "metrics.jsonl")) as f:
                    rows = [json.loads(l) for l in f]
                ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
                c = torch.load(ck)
        finally:
            sp.losses = real
        self.assertGreater(rows[-1]["train_steps"], 0)
        self.assertEqual(rows[-1]["nonfinite_skips"], 2)
        self.assertEqual(c["counters"]["nonfinite_skips"], 2)
        for v in c["net"].values():
            self.assertTrue(bool(torch.isfinite(v.float()).all()))
        g = [r["grad_norm"] for r in rows if r.get("grad_norm")]
        self.assertTrue(g and all(x["max"] >= x["mean"] > 0 for x in g))

    def test_nonfinite_abort_after(self):
        """Only non-finite steps: after --nonfinite-abort-after consecutive skips the run stops (exit 1, an error
        naming the streak) and its final checkpoint still holds finite weights."""
        sp = load()
        real = sp.losses

        def poisoned(*a, **k):
            loss, parts = real(*a, **k)
            return loss * float("nan"), parts

        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1600", "--max-runs", "40",
                "--nonfinite-abort-after", "5"]
        sp.losses = poisoned
        out = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(out):
                rc = sp.main(args + ["--out-dir", d])
                ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
                c = torch.load(ck)
        finally:
            sp.losses = real
        self.assertEqual(rc, 1)
        final = json.loads([l for l in out.getvalue().splitlines() if l.startswith('{"final_checkpoint"')][-1])
        self.assertTrue(any("5 consecutive non-finite" in e for e in final["errors"]))
        self.assertEqual(c["counters"]["step"], 0)
        self.assertEqual(c["counters"]["nonfinite_skips"], 5)
        for v in c["net"].values():
            self.assertTrue(bool(torch.isfinite(v.float()).all()))

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

    @unittest.skipUnless(os.environ.get("TRITON_INTERPRET") == "1", "needs TRITON_INTERPRET=1 (fused-net kernel on CPU)")
    def test_fused_net_run(self):
        """--fused-net (whole net as one Triton kernel, tools/az_bench/fused_net.py) plays and trains (the kernel's weight
        refresh after a sync is unit-tested in tests/test_fused_net.py); --gpu-timing is accepted (no CUDA streams on a CPU)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "8", "--fast-sims", "4", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "50", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1400", "--max-runs", "16", "--packed-h2d",
                "--fused-net", "--gpu-timing", "--utility", "amber"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["runs_done"], 16)
            self.assertGreater(rows[-1]["train_steps"], 0)   # weight syncs may not land before the last run ends;
            # refresh() after a sync: tests/test_fused_net.py test_refresh_after_weight_change
            self.assertEqual(rows[-1]["invalid_actions"], 0)
            self.assertIn("gpu_ms_per_s", rows[-1])
            self.assertIn("fused_long_rows", rows[-1])

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

    def test_force_keys_curriculum(self):
        """--force-keys curriculum: the key backstops are on for the first runs, off from the first curriculum step-up,
        and stay off on resume; without --curriculum the flag is refused; off by default (no metrics field)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "4", "--fast-sims", "2", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "1000000", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1400", "--test-max-hp", "5000",
                "--max-fight-moves", "2000", "--ascension", "0"]
        with self.assertRaises(SystemExit):
            sp.main(args + ["--out-dir", "unused", "--max-runs", "1", "--force-keys", "curriculum"])
        cur = ["--curriculum", "--curriculum-runs", "4", "--curriculum-winrate", "0", "--force-keys", "curriculum"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + cur + ["--out-dir", d, "--max-runs", "16"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertTrue(all("force_keys" in r for r in rows))
            self.assertTrue(rows[0]["force_keys"]["active"])
            self.assertGreaterEqual(rows[-1]["ascension"], 1)
            self.assertFalse(rows[-1]["force_keys"]["active"])
            act = [r["force_keys"]["active"] for r in rows]
            self.assertEqual(act, sorted(act, reverse=True))   # on, then off for good
            self.assertTrue(all(r["ascension"] == 0 for r in rows if r["force_keys"]["active"]))
            ck = sorted(glob.glob(os.path.join(d, "ckpt_*.pt")), key=os.path.getmtime)[-1]
            self.assertTrue(torch.load(ck)["counters"]["curriculum_stepped"])
            self.assertEqual(sp.main(args + cur + ["--out-dir", d, "--max-runs", "20", "--resume", ck]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows2 = [json.loads(l) for l in f][len(rows):]
            self.assertTrue(rows2 and not any(r["force_keys"]["active"] for r in rows2))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d, "--max-runs", "4"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                self.assertFalse(any("force_keys" in json.loads(l) for l in f))

    def test_force_keys_on(self):
        """--force-keys on: the key backstops stay on across curriculum step-ups (Philipp 2026-11-19)."""
        sp = load()
        args = ["--module-dir", os.path.dirname(MODULES[0]), "--device", "cpu", "--workers", "2", "--games", "4",
                "--full-sims", "4", "--fast-sims", "2", "--batch", "32", "--row-buckets", "32", "--pack-step", "32",
                "--pack-threads", "1", "--min-replay", "1000000", "--train-batch", "32", "--window", "5000",
                "--report", "1", "--sync-steps", "2", "--seed-base", "1400", "--test-max-hp", "5000",
                "--max-fight-moves", "2000", "--ascension", "0",
                "--curriculum", "--curriculum-runs", "4", "--curriculum-winrate", "0", "--force-keys", "on"]
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sp.main(args + ["--out-dir", d, "--max-runs", "16"]), 0)
            with open(os.path.join(d, "metrics.jsonl")) as f:
                rows = [json.loads(l) for l in f]
            self.assertGreaterEqual(rows[-1]["ascension"], 1)
            self.assertTrue(all(r["force_keys"]["active"] for r in rows))


if __name__ == "__main__":
    unittest.main()
