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
# act_encounter_lists of cov8's 8 seeds at A20 (critic_ceiling.py encounters, slaythespire module of this commit)
COV8_ENC = os.path.join(HERE, "fixtures", "critic_encounters_cov8.json.gz")
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
        self.assertLess(b["logloss_ci9875"][1], 0)
        self.assertGreater(b["ev_ci9875"][0], 0)
        v = cc.verdict({"net": {"act1": b, "all": b}}, 0.02)
        self.assertEqual(v["decision"], "GO")
        same = cc.bootstrap_diff(gid, y, online, online, G, 50, 1)
        self.assertEqual(cc.verdict({"net": {"act1": same, "all": same}}, 0.02)["decision"], "NO_GO")

    def test_platt_recovers_a_logistic_link(self):
        import critic_ceiling as cc
        rng = np.random.default_rng(5)
        acts = rng.integers(1, 5, 20000)
        v = rng.normal(0.2, 0.15, 20000)
        true = {1: (-2.0, 3.0), 2: (-1.0, 2.0), 3: (-1.5, 5.0), 4: (0.0, 1.0)}
        y = (rng.uniform(size=20000) < cc.apply_platt(true, acts, v)).astype(float)
        cal = cc.fit_platt(acts, v, y)
        for act in cc.ACTS:
            self.assertAlmostEqual(cal[act][0], true[act][0], delta=0.25)
            self.assertAlmostEqual(cal[act][1], true[act][1], delta=0.8)
        # values <= 0 are mapped to a finite probability, unlike clipping to EPS
        self.assertGreater(float(cc.apply_platt(cal, [1], [-0.1])[0]), 0.01)

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
        with self.assertRaises(ValueError):   # nested fixed_actions keys are checked too
            cc.flat_features(dict(rec, fixed_actions=[{"action": 3, "new_key": 1}]))
        x = cc.flat_features(dict(rec, fixed_actions=[{"action": 3, "info": 7}]))
        self.assertEqual(x.get("fa3_info7"), 1.0)


def _cov8_decisions():
    with gzip.open(COV8, "rt") as f:
        return [r for r in map(json.loads, f) if r["type"] == "decision" and "record" in r]


class EncounterFeatures(unittest.TestCase):
    """Privileged encounter lists (issue #1050 stage 0)."""

    def test_cov8_fought_is_the_consumed_prefix_and_boss_matches(self):
        import critic_ceiling as cc
        seeds, _ = cc.load_encounters(COV8_ENC)
        o = cc._check_part(COV8, seeds)
        self.assertEqual(o["checked"] + o["act4"], o["decisions"])
        self.assertGreater(o["checked"], 900)

    def test_mismatch_raises(self):
        import critic_ceiling as cc
        acts = [{"act": 1, "monsters": [1, 2, 3], "elites": [15, 16], "boss": 18, "second_boss": 0}] * 3
        rec = {"obs.act": 1, "obs.v2.fought": [1, 2, 15]}
        self.assertEqual(cc.consumed_prefix(rec, acts), (2, 1))
        self.assertEqual(cc.consumed_prefix(dict(rec, **{"obs.v2.fought": []}), acts), (0, 0))
        with self.assertRaises(ValueError):
            cc.consumed_prefix(dict(rec, **{"obs.v2.fought": [1, 3]}), acts)
        with self.assertRaises(ValueError):
            cc.consumed_prefix(dict(rec, **{"obs.v2.fought": [1, 16]}), acts)

    def test_features_are_the_remaining_lists_only(self):
        import critic_ceiling as cc
        a1 = {"act": 1, "monsters": [1, 2, 3, 4], "elites": [15, 16, 15], "boss": 18, "second_boss": 0}
        a2 = {"act": 2, "monsters": [22, 23], "elites": [34], "boss": 37, "second_boss": 0}
        a3 = {"act": 3, "monsters": [40], "elites": [50], "boss": 55, "second_boss": 53}
        acts = [a1, a2, a3]
        rec = {"obs.act": 1, "obs.v2.fought": [1, 2, 15]}
        x = cc.encounter_features(rec, acts, "act")
        self.assertEqual(x, {"enc_n0_3": 1.0, "enc_ncnt_3": 1.0, "enc_n1_4": 1.0, "enc_ncnt_4": 1.0,
                             "enc_e0_16": 1.0, "enc_ecnt_16": 1.0, "enc_e1_15": 1.0, "enc_ecnt_15": 1.0})
        r = cc.encounter_features(rec, acts, "run")
        self.assertTrue(set(x) < set(r))
        self.assertEqual(r["enc_a2_boss_37"], 1.0)
        self.assertEqual(r["enc_a3_boss2_53"], 1.0)
        self.assertNotIn("enc_boss2_53", r)   # the act-3 second boss is a later-act feature in act 1
        self.assertEqual(cc.encounter_features({"obs.act": 3, "obs.v2.fought": []}, acts, "act")["enc_boss2_53"], 1.0)
        self.assertEqual(cc.encounter_features({"obs.act": 4, "obs.v2.fought": []}, acts, "run"), {})
        with self.assertRaises(ValueError):
            cc.encounter_features(rec, acts, "future")

    def test_public_features_unchanged(self):
        import critic_ceiling as cc
        try:
            import ppo_model  # noqa: F401
        except ImportError:
            self.skipTest("ppo_model needs torch")
        seeds, sha = cc.load_encounters(COV8_ENC)
        enc = {"seeds": seeds, "sha256": sha, "scope": "run"}
        for row in _cov8_decisions()[::25]:
            pub = cc.flat_features(row["record"])
            both = cc.flat_with_encounters(row["record"], row["seed"], enc)
            self.assertEqual({k: v for k, v in both.items() if not k.startswith("enc_")}, pub)
            self.assertFalse(any(k.startswith("enc_") for k in pub))
            self.assertEqual(cc.flat_with_encounters(row["record"], row["seed"], None), pub)

    def test_verdict_encounters(self):
        import critic_ceiling as cc

        def c(d, lo):
            return {"act1": {"ev_diff": d, "ev_ci95": [lo, d + 0.01]}}
        go = cc.verdict_encounters({"gbm_enc-gbm": c(0.04, 0.02), "gbm_enc-online_cal": c(0.03, 0.01)}, 0.03)
        self.assertEqual(go["decision"], "GO")
        for a, b in (((0.025, 0.01), (0.03, 0.01)), ((0.04, -0.001), (0.03, 0.01)), ((0.04, 0.02), (0.01, -0.01))):
            v = cc.verdict_encounters({"gbm_enc-gbm": c(*a), "gbm_enc-online_cal": c(*b)}, 0.03)
            self.assertEqual(v["decision"], "NO_GO")
        with self.assertRaises(ValueError):
            cc.verdict_encounters({"gbm_enc-gbm": c(0.04, 0.02)}, 0.03)


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
            for k in ("online", "online_cal", "net", "gbm"):
                self.assertEqual(rep["estimators"][k]["all"]["n"], n_dec)
            self.assertEqual(set(rep["bootstrap"]), {"net", "gbm"})   # the rule compares with online_cal
            self.assertIn("platt_by_act", rep["meta"]["online_cal"])
            self.assertIn(rep["verdict"]["decision"], ("GO", "NO_GO"))
            # the gbm sees the planted gold signal (win 0.8 vs 0.1) that the random online critic cannot
            self.assertGreater(rep["estimators"]["gbm"]["all"]["auc"], 0.75)
            self.assertGreater(rep["estimators"]["gbm"]["all"]["auc"], rep["estimators"]["online"]["all"]["auc"])
            with self.assertRaises(subprocess.CalledProcessError):   # overlapping seeds are refused
                run("evaluate", "--test", *train[:1], "--train-seeds-from", *train, "--out", out)


@unittest.skipIf(torch is None, "torch or xgboost not installed")
class EncounterRoundTrip(unittest.TestCase):
    def test_fit_and_evaluate_with_encounters(self):
        """cov8's games under 48 new seeds; the outcome is planted in a not-yet-fought act-1 normal encounter of the
        table (marker id 98/99), which no public field shows: gbm_enc must find it, gbm must not."""
        import subprocess
        import critic_ceiling as cc
        seeds, _ = cc.load_encounters(COV8_ENC)
        with gzip.open(COV8, "rt") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        games = {}
        for r in rows:
            games.setdefault(r["seed"], []).append(r)
        rng = np.random.default_rng(4)
        tool = os.path.join(HERE, "..", "tools", "heart1", "critic_ceiling.py")
        with tempfile.TemporaryDirectory() as d:
            table, parts = {}, []
            for part in range(6):
                p = os.path.join(d, f"traj-{part:04d}-p00.jsonl.gz")
                with gzip.open(p, "wt") as f:
                    for k, (seed, lines) in enumerate(sorted(games.items())):
                        new = f"8{part}{k:02d}"
                        win = bool(rng.uniform() < 0.5)
                        acts = json.loads(json.dumps(seeds[seed]))
                        kmax = max(cc.consumed_prefix(r["record"], seeds[seed])[0] for r in lines
                                   if r["type"] == "decision" and "record" in r and r["record"]["obs.act"] == 1)
                        acts[0]["monsters"][kmax] = 99 if win else 98
                        table[new] = acts
                        for r in lines:
                            r = dict(r, seed=new)
                            if r["type"] == "game":
                                r["outcome"] = dict(r["outcome"], heart_kill=win)
                            f.write(json.dumps(r) + "\n")
                parts.append(p)
            enc = os.path.join(d, "enc.json.gz")
            with gzip.open(enc, "wt") as f:
                json.dump({"schema": "critic-encounters-v1", "seeds": table}, f)
            train, test = parts[:4], parts[4:]

            def run(*args):
                return subprocess.run([sys.executable, tool, *args], check=True, capture_output=True, text=True)
            common = ("--train", *train, "--per-game", "8", "--rounds", "300", "--eta", "0.3", "--min-count", "1", "--workers", "1")
            run("fit-gbm", *common, "--out", os.path.join(d, "gbm.json"))
            run("fit-gbm", *common, "--encounters", enc, "--enc-scope", "act", "--out", os.path.join(d, "gbm_enc.json"))
            out = os.path.join(d, "report.json")
            ev_args = ("evaluate", "--test", *test, "--gbm", os.path.join(d, "gbm.json"),
                       "--extra-gbm", "gbm_enc=" + os.path.join(d, "gbm_enc.json"), "--boot", "100",
                       "--train-seeds-from", *train, "--out", out)
            with self.assertRaises(subprocess.CalledProcessError):   # a model fitted with a table needs it
                run(*ev_args)
            run(*ev_args, "--encounters", enc, "--contrast", "gbm_enc:gbm", "--contrast", "gbm_enc:online_cal",
                "--rule", "encounters")
            with open(out) as f:
                rep = json.load(f)
            e = rep["estimators"]
            self.assertGreater(e["gbm_enc"]["act1"]["auc"], 0.9)
            self.assertLess(e["gbm"]["act1"]["auc"], 0.75)
            self.assertEqual(set(rep["contrasts"]), {"gbm_enc-gbm", "gbm_enc-online_cal"})
            self.assertEqual(set(rep["contrasts"]["gbm_enc-gbm"]), set(cc.CONTRAST_SCOPES))
            self.assertGreater(rep["contrasts"]["gbm_enc-gbm"]["act1"]["ev_diff"], 0.2)
            self.assertEqual(rep["verdict"]["decision"], "GO")
            self.assertEqual(rep["meta"]["gbm_enc"]["encounters"]["scope"], "act")


if __name__ == "__main__":
    unittest.main()
