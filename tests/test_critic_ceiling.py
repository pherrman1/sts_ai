"""Offline critic ceiling check (tools/heart1/critic_ceiling.py): metrics, bootstrap, field coverage and a tiny
fit-net / fit-gbm / evaluate round trip on the committed cov8 smoke trajectories; skipped without torch/xgboost."""
import gzip
import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "heart1"))
COV8 = os.path.join(HERE, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
try:
    import torch  # noqa: F401
    import xgboost  # noqa: F401
except ImportError:
    torch = None


class CriticCeilingArithmetic(unittest.TestCase):
    def test_gae_matches_the_learner(self):
        import critic_ceiling as cc
        v = np.array([0.2, 0.3, 0.1, 0.6])
        a1 = cc.gae_adv(1.0, v, 1.0)
        self.assertTrue(np.allclose(a1, 1.0 - v))   # lambda 1: outcome minus value
        a0 = cc.gae_adv(1.0, v, 0.0)
        self.assertTrue(np.allclose(a0, [0.3 - 0.2, 0.1 - 0.3, 0.6 - 0.1, 1.0 - 0.6]))
        try:
            import ppo_train
        except ImportError:   # ppo_train needs torch
            return
        for lam in (0.0, 0.5, 0.97, 1.0):
            want, _ = ppo_train.gae([0, 0, 0, 1.0], list(v), 1.0, lam)
            self.assertTrue(np.allclose(cc.gae_adv(1.0, v, lam), want))

    def test_auc_ev_logloss(self):
        import critic_ceiling as cc
        y = np.array([0, 0, 1, 1, 0, 1.0])
        self.assertEqual(cc.auc(y, np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7])), 1.0)
        self.assertEqual(cc.auc(y, np.full(6, 0.5)), 0.5)
        self.assertAlmostEqual(cc.ev(y, y), 1.0)
        self.assertAlmostEqual(cc.ev(y, np.full(6, 0.3)), 0.0)   # a constant explains nothing
        self.assertAlmostEqual(float(cc.logloss(np.array([1.0]), np.array([0.5]))[0]), np.log(2))

    def test_bootstrap_point_equals_direct_and_verdict(self):
        import critic_ceiling as cc
        rng = np.random.default_rng(0)
        G, per = 400, 10
        gid = np.repeat(np.arange(G), per)
        p = np.repeat(rng.uniform(0.05, 0.6, G), per)
        y = (rng.uniform(size=G) < p[::per]).astype(float)[gid]
        online = np.full(len(y), y.mean())
        good = p
        b = cc.bootstrap_diff(gid, y, online, good, G, 300, 1)
        self.assertAlmostEqual(b["logloss_diff"], float(cc.logloss(y, good).mean() - cc.logloss(y, online).mean()))
        self.assertAlmostEqual(b["ev_diff"], cc.ev(y, good) - cc.ev(y, online), places=9)
        self.assertLess(b["logloss_ci975"][1], 0)
        v = cc.verdict({"net": {"act1": b, "all": b}}, 0.02)
        self.assertEqual(v["decision"], "GO")
        same = cc.bootstrap_diff(gid, y, online, online, G, 50, 1)
        self.assertEqual(cc.verdict({"net": {"act1": same, "all": same}}, 0.02)["decision"], "NO_GO")

    def test_every_record_field_has_a_flat_encoding(self):
        import critic_ceiling as cc
        try:
            import ppo_model  # noqa: F401  (flat_features uses its map/deck helpers)
        except ImportError:
            self.skipTest("ppo_model needs torch")
        seen, rec = set(), None
        with gzip.open(COV8, "rt") as f:
            for line in f:
                row = json.loads(line)
                if row["type"] == "decision" and "record" in row:
                    rec = row["record"]
                    seen |= set(rec)
                    x = cc.flat_features(rec)
                    self.assertTrue(all(np.isfinite(v) for v in x.values()))
        self.assertEqual(seen - set(cc.RECORD_FIELDS), set())
        with self.assertRaises(ValueError):
            cc.flat_features(dict(rec, **{"obs.new_field": 1}))


@unittest.skipIf(torch is None, "torch or xgboost not installed")
class CriticCeilingRoundTrip(unittest.TestCase):
    def _parts(self, d):
        """cov8's 8 games copied under 48 new seeds into 6 parts, with outcomes tied to the hp at the first decision
        plus noise, so the learnable signal is known to exist."""
        with gzip.open(COV8, "rt") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        games = {}
        for r in rows:
            games.setdefault(r["seed"], []).append(r)
        rng = np.random.default_rng(3)
        paths = []
        for part in range(6):
            p = os.path.join(d, f"traj-{part:04d}-p00.jsonl.gz")
            with gzip.open(p, "wt") as f:
                for k, (seed, lines) in enumerate(sorted(games.items())):
                    new = f"9{part}{k:02d}"
                    win = bool(rng.uniform() < (0.8 if k % 2 else 0.1))
                    for r in lines:
                        r = dict(r, seed=new)
                        if r["type"] == "game":
                            r["outcome"] = dict(r["outcome"], heart_kill=win)
                        elif "record" in r and k % 2:
                            rec = dict(r["record"]); fo = list(rec["obs.fixed_observation"]); fo[2] = 999
                            r["record"] = rec; rec["obs.fixed_observation"] = fo
                        f.write(json.dumps(r) + "\n")
            paths.append(p)
        return paths

    def test_fit_and_evaluate(self):
        import subprocess
        import ppo_model
        with tempfile.TemporaryDirectory() as d:
            parts = self._parts(d)
            rows = {k: 4096 for k in ppo_model.TABLES}
            rows["fixed_action"] = ppo_model.FA_COUNT
            torch.manual_seed(0)
            net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False)
            with torch.no_grad():
                for p in net.parameters():
                    p.copy_(0.1 * torch.randn_like(p))
            init = os.path.join(d, "init.bin")
            net.to_bin(init)
            tool = os.path.join(HERE, "..", "tools", "heart1", "critic_ceiling.py")
            train, test = parts[:4], parts[4:]

            def run(*args):
                return subprocess.run([sys.executable, tool, *args], check=True, capture_output=True, text=True)
            run("fit-net", "--init", init, "--train", *train, "--per-game", "4", "--epochs", "2", "--device", "cpu",
                "--workers", "1", "--out", os.path.join(d, "net.pt"))
            run("fit-gbm", "--train", *train, "--per-game", "8", "--rounds", "40", "--min-count", "1",
                "--workers", "1", "--out", os.path.join(d, "gbm.json"))
            out = os.path.join(d, "report.json")
            run("evaluate", "--test", *test, "--net", os.path.join(d, "net.pt"), "--gbm", os.path.join(d, "gbm.json"),
                "--boot", "100", "--train-seeds-from", *train, "--out", out)
            with open(out) as f:
                rep = json.load(f)
            self.assertEqual(rep["games"], 16)
            n_dec = sum(1 for p in test for l in gzip.open(p, "rt")
                        if json.loads(l)["type"] == "decision" and json.loads(l)["source"] in
                        ("heart1_ppo", "heart1_ppo_single"))
            for k in ("online", "net", "gbm"):
                self.assertEqual(rep["estimators"][k]["all"]["n"], n_dec)
            self.assertIn(rep["verdict"]["decision"], ("GO", "NO_GO"))
            # the gbm sees the planted gold signal (win 0.8 vs 0.1) that the random online critic cannot
            self.assertGreater(rep["estimators"]["gbm"]["all"]["auc"], 0.75)
            self.assertGreater(rep["estimators"]["gbm"]["all"]["auc"], rep["estimators"]["online"]["all"]["auc"])
            with self.assertRaises(subprocess.CalledProcessError):   # overlapping seeds are refused
                run("evaluate", "--test", *train[:1], "--train-seeds-from", *train, "--out", out)


if __name__ == "__main__":
    unittest.main()
