"""heart1 PPO learner arithmetic and the torch mirror's .bin round trip (tools/heart1/ppo_*.py); skipped without torch."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "heart1"))
try:
    import torch  # noqa: F401
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "torch not installed")
class Heart1PpoTest(unittest.TestCase):
    def test_learner_arithmetic(self):
        import ppo_train
        ppo_train.cmd_selftest([])

    def test_bin_round_trip_and_zero_extension(self):
        import ppo_model
        rows = {k: 8 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows)
        with torch.no_grad():
            for p in net.parameters():
                p.copy_(torch.randn_like(p))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "n.bin")
            net.to_bin(path)
            back = ppo_model.PolicyNet.from_bin(path)
            a, b = net.native_state(), back.native_state()
            self.assertEqual(set(a), set(b))
            for k in a:
                self.assertTrue(torch.equal(a[k], b[k]), k)
            # Dropping the optional inputs and reloading restores them as exact zeros.
            ppo_model.write_bin(path, {k: v for k, v in a.items() if not k.startswith("x")})
            z = ppo_model.PolicyNet.from_bin(path)
            self.assertTrue(torch.count_nonzero(z.tables["x_act"]) == 0)
            self.assertTrue(torch.count_nonzero(z.fixedvecs["x2_price"].proj.weight) == 0)

    def test_feature_store_matches_collate(self):
        import random
        import ppo_model
        import ppo_train
        traj = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                            "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        games = ppo_train.load_games([traj], False)[:2]
        feats = [s["feat"] for g in games for s in g["steps"]]
        store = ppo_model.FeatureStore(feats)
        idx = list(range(len(feats)))
        random.Random(0).shuffle(idx)
        for i in range(0, len(idx), 37):
            mb = idx[i:i + 37]
            a, b = ppo_model.collate([feats[j] for j in mb]), store.batch(mb)
            self.assertEqual((a["B"], a["T"]), (b["B"], b["T"]))
            for k in ("pad", "choice_index", "choice_mask"):
                self.assertTrue(torch.equal(a[k], b[k]), k)
            for d in ("emb", "fv"):
                self.assertEqual(list(a[d]), list(b[d]))
                for k in a[d]:
                    self.assertTrue(torch.equal(a[d][k][0], b[d][k][0]) and torch.equal(a[d][k][1], b[d][k][1]), k)

    def test_load_games_pool_errors_do_not_hang(self):
        """Parent-side (bad schema) and worker-side (broken JSON) errors with 8 workers must raise, not deadlock the
        pool (review of #952)."""
        import gzip
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        with gzip.open(traj, "rt") as src:
            lines = [l for l in src if l.strip()]
        with tempfile.TemporaryDirectory() as d:
            schema = os.path.join(d, "schema.jsonl")
            broken = os.path.join(d, "broken.jsonl")
            with open(schema, "w") as f:
                for line in lines * 16:
                    f.write(line.replace('"heart1-ppo-traj-v1"', '"not-the-schema"'))
            with open(broken, "w") as f:
                big = lines * 16
                big[300] = big[300][:50] + "\n"   # truncated JSON early in a long file
                f.writelines(big)
            for path in (schema, broken):
                code = ("import sys; sys.path.insert(0, %r); import ppo_train\n"
                        "try:\n    ppo_train.load_games([%r], False, workers=8)\nexcept ValueError:\n    sys.exit(3)\n"
                        % (os.path.join(here, "..", "tools", "heart1"), path))
                rc = subprocess.run([sys.executable, "-c", code], timeout=300).returncode
                self.assertEqual(rc, 3, path)

    def test_cloud_store_round_trip(self):
        """ppo_cloud: two actor parts in a dir store -> one serve step -> next net and stats published, parts gone."""
        import gzip
        import json
        import ppo_cloud
        import ppo_model
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(0)
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False)
        with tempfile.TemporaryDirectory() as d:
            init = os.path.join(d, "init.bin")
            net.to_bin(init)
            env = os.path.join(d, "a.env")
            with open(env, "w") as f:
                f.write("STS_FAIR=1\n")
            store = "dir:" + os.path.join(d, "store")
            ppo_cloud.cmd_init([store, "A", "--init", init, "--env-file", env, "--one-combat-sha", "0" * 64,
                                "--iterations", "2", "--games", "8", "--parts", "2", "--seed-base", "1",
                                "--value-warmup", "0", "--", "--epochs", "1"])
            with self.assertRaises(SystemExit):   # frozen once
                ppo_cloud.cmd_init([store, "A", "--init", init, "--env-file", env, "--one-combat-sha", "0" * 64,
                                    "--iterations", "2", "--games", "8", "--seed-base", "1"])
            with gzip.open(traj, "rt") as f:
                lines = [l for l in f if l.strip()]
            seeds = sorted({json.loads(l)["seed"] for l in lines if '"type":"game"' in l})
            s = ppo_cloud.open_store(store)
            s.get("A/net-0000", os.path.join(d, "n0.bin"))
            n0 = ppo_cloud.sha256(os.path.join(d, "n0.bin"))
            for k, part in enumerate((seeds[:4], seeds[4:])):
                p = os.path.join(d, f"p{k}.jsonl.gz")
                with gzip.open(p, "wt") as f:
                    f.writelines(l for l in lines if json.loads(l)["seed"] in part)
                s.put(f"A/traj-0000-p{k}", p, {"games": 4, "sha256": ppo_cloud.sha256(p), "net": "net-0000",
                                                "net_sha256": n0, "actor_s": 1.0, "seed_first": part[0]})
            learner = ppo_cloud.ArmLearner(s, os.path.join(d, "local"), "A", "cpu")
            self.assertFalse(learner.step(s.names("A/traj-0000-p0")))   # part 1 missing from the listing
            real_put = s.put

            def failing_put(name, path, meta):   # the learner dies while publishing net-0001
                if name == "A/net-0001":
                    raise RuntimeError("push failed")
                real_put(name, path, meta)
            s.put = failing_put
            with self.assertRaises(RuntimeError):
                learner.step(s.names(""))
            s.put = real_put
            self.assertNotIn("A/net-0001", s.names(""))
            again = ppo_cloud.ArmLearner(s, os.path.join(d, "local"), "A", "cpu")   # restart republishes
            self.assertEqual(again.next_it, 1)
            names = s.names("")
            self.assertIn("A/net-0001", names)
            self.assertIn("A/stats-0001", names)
            self.assertFalse([n for n in names if "traj" in n])
            with open(os.path.join(d, "local", "A", "loop.json")) as f:
                self.assertEqual(len(json.load(f)["iterations"]), 1)
            for k in range(2):   # iteration 1 (pipeline: still played by net-0000); every name is written once
                p = os.path.join(d, f"p{k}.jsonl.gz")
                s.put(f"A/traj-0001-p{k}", p, {"games": 4, "sha256": ppo_cloud.sha256(p), "net": "net-0000",
                                                "net_sha256": n0, "actor_s": 1.0, "seed_first": 1})
            self.assertTrue(again.step(s.names("")))
            self.assertEqual(sorted(s.names("")), ["A/config", "A/net-0001", "A/net-0002", "A/stats-0001",
                                                   "A/stats-0002"])
            import csv
            with open(os.path.join(d, "local", "A", "games-0001.csv")) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(sorted(r["seed"] for r in rows), sorted(str(x) for x in seeds))
            self.assertEqual(sum(int(r["heart_kill"]) for r in rows),
                             sum(1 for l in lines if '"type":"game"' in l and '"heart_kill":true' in l))
            self.assertEqual(len(os.listdir(os.path.join(d, "local", "A", "parts"))), 4)
            self.assertTrue(again.done())
            with self.assertRaises(ValueError):   # size cap
                big = os.path.join(d, "big")
                with open(big, "wb") as f:
                    f.truncate((ppo_cloud.MAX_PUT_MB + 1) * 2**20)
                s.put("A/big", big, {})
            self.assertEqual(ppo_cloud.trained_iterations(s, "A", d), 2)


if __name__ == "__main__":
    unittest.main()
