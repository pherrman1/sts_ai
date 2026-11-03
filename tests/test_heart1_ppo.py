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

    def test_micro_batch_accumulation(self):
        """--micro-batch: chunked forward/backward + one step == the whole minibatch (rounding); >= minibatch: bitwise."""
        import argparse
        import copy
        import ppo_model
        import ppo_train
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(0)
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False)
        games = ppo_train.load_games([traj], net.trim_map)

        def run(micro, value_clip):
            ap = argparse.ArgumentParser()
            ppo_train.add_hparams(ap)
            args = ap.parse_args(["--minibatch", "64", "--epochs", "1", "--kl-coef", "0.1", "--entropy-coef", "0.01",
                                  "--micro-batch", str(micro), "--value-clip", str(value_clip)])
            learner = ppo_train.Learner(copy.deepcopy(net), copy.deepcopy(net), args, torch.device("cpu"))
            stats = learner.update(copy.deepcopy(games), log=lambda line: None)
            return learner.net.state_dict(), stats

        for value_clip in (0, 0.2):
            ref, s_ref = run(0, value_clip)
            same, s_same = run(64, value_clip)
            chunked, s_ch = run(23, value_clip)
            for k in ref:
                self.assertTrue(torch.equal(ref[k], same[k]), k)
                self.assertTrue(torch.allclose(ref[k], chunked[k], atol=1e-6, rtol=1e-5), k)
            for k in ("policy", "value", "entropy", "kl_anchor", "clipfrac", "approx_kl"):
                self.assertAlmostEqual(s_ref[k], s_ch[k], places=5)
                self.assertEqual(s_ref[k], s_same[k])
            self.assertEqual(s_ref["minibatches"], s_ch["minibatches"])

    def test_stalled_game_lines(self):
        """ppo_cloud actor: bestbench stall failures become loss game lines; anything else stops the actor."""
        import json
        import ppo_cloud
        import ppo_train
        err = ("[bestbench-seed-failure] seed=111403638 error=native Silver backend: stall: exceeded 1000 decisions "
               "floor=45 encounter=47\nbestbench: FAILED requested=256 completed=255 failed=1\n")
        lines = ppo_cloud.stalled_game_lines(err, 256)
        self.assertEqual(len(lines), 1)
        self.assertIn('"type":"game"', lines[0])
        row = json.loads(lines[0])
        self.assertEqual((row["seed"], row["schema"], row["outcome"]["floor"], row["outcome"]["heart_kill"]),
                         ("111403638", ppo_train.SCHEMA, 45, False))
        with tempfile.TemporaryDirectory() as d:   # the learner loads it as a game without decisions
            p = os.path.join(d, "t.jsonl")
            with open(p, "w") as f:
                f.write(lines[0] + "\n")
            games = ppo_train.load_games([p], workers=1)
            self.assertEqual((len(games), games[0]["steps"]), (1, []))
            self.assertEqual(ppo_train.step_rewards(games[0], "original", 1.0), [])
        other = err.replace("stall: exceeded 1000 decisions", "knowledge tracker lost consistency")
        self.assertIsNone(ppo_cloud.stalled_game_lines(other, 256))
        self.assertIsNone(ppo_cloud.stalled_game_lines(err.replace("failed=1", "failed=2"), 256))
        self.assertIsNone(ppo_cloud.stalled_game_lines(err, 50))       # count mismatch with the part
        self.assertIsNone(ppo_cloud.stalled_game_lines("Segmentation fault\n", 256))
        many = "".join(f"[bestbench-seed-failure] seed={i} error=stall: exceeded 1000 decisions floor=1\n"
                       for i in range(4)) + "bestbench: FAILED requested=256 completed=252 failed=4\n"
        self.assertIsNone(ppo_cloud.stalled_game_lines(many, 256))     # > 1% of the part

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

    def test_load_games_seed_order_and_minibatches(self):
        """load_games: the same games in another line order (bestbench writes each game when its thread finishes)
        give the same game and step sequence and the same minibatch index sequences; a seed in two files raises."""
        import argparse
        import gzip
        import json
        import random
        import ppo_train
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        blocks = {}   # seed -> its lines (decisions, then the game line), as the actor writes them
        with gzip.open(traj, "rt") as f:
            for line in f:
                if line.strip():
                    blocks.setdefault(json.loads(line)["seed"], []).append(line)
        seeds = list(blocks)
        self.assertGreater(len(seeds), 3)
        rng = random.Random(1)

        def write(path, order, shuffle_steps):
            with open(path, "w") as f:
                for s in order:
                    lines = blocks[s][:-1]
                    if shuffle_steps:
                        rng.shuffle(lines)
                    f.writelines(lines + blocks[s][-1:])

        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.jsonl"), os.path.join(d, "b.jsonl")
            write(a, seeds, False)
            write(b, seeds[::-1], True)
            ga = ppo_train.load_games([a], False, workers=1)
            gb = ppo_train.load_games([b], False, workers=1)
            self.assertEqual([g["seed"] for g in ga], sorted(seeds, key=ppo_train.seed_key))
            ids = [[(g["seed"], s["idx"]) for g in gs for s in g["steps"]] for gs in (ga, gb)]
            self.assertEqual(ids[0], ids[1])
            self.assertEqual([g["outcome"] for g in ga], [g["outcome"] for g in gb])
            ap = argparse.ArgumentParser()
            ppo_train.add_hparams(ap)
            for extra in ([], ["--bucket", "2"]):
                args = ap.parse_args(["--minibatch", "64", "--epochs", "2"] + extra)
                plans = [ppo_train.plan_minibatches(args, [s["feat"] for g in gs for s in g["steps"]], 3)
                         for gs in (ga, gb)]
                self.assertEqual(plans[0], plans[1])
                self.assertEqual(sum(len(mb) for mb in plans[0]), 2 * len(ids[0]))
            with self.assertRaises(ValueError):   # the same seeds in two files
                ppo_train.load_games([a, b], None, workers=1)
            half = len(seeds) // 2
            c, e = os.path.join(d, "c.jsonl"), os.path.join(d, "e.jsonl")
            write(c, seeds[half:], True)
            write(e, seeds[:half], True)
            gce = ppo_train.load_games([c, e], None, workers=1)   # disjoint files: seed order across files
            self.assertEqual([g["seed"] for g in gce], [g["seed"] for g in ga])

    def test_heads_fp32_under_autocast(self):
        """heads_out: the choice-logit and value Linears run in fp32 inside a bf16 autocast region, bitwise the
        fp32 heads on the same trunk output (the actor's behaviour log-probs are fp32)."""
        import ppo_model
        import ppo_train
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(0)
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False).eval()
        games = ppo_train.load_games([traj], net.trim_map, workers=1)[:1]
        batch = ppo_model.collate([s["feat"] for s in games[0]["steps"]][:8])
        with torch.no_grad():
            with torch.autocast("cpu", dtype=torch.bfloat16):
                x = net.trunk(batch)
                self.assertEqual(net.choice_logits(net.norm(x)).dtype, torch.bfloat16)   # autocast is live
                logits, value, _ = net.heads_out(x, batch)
            self.assertEqual((logits.dtype, value.dtype), (torch.float32, torch.float32))
            ref_logits, ref_value, _ = net.heads_out(x, batch)
            self.assertTrue(torch.equal(logits, ref_logits) and torch.equal(value, ref_value))

    def test_heart_pbrs_needs_phi_and_expect_games(self):
        """--reward heart_pbrs refuses trajectories without any "phi" (it would equal heart); update --expect-games
        fails on a game-count mismatch (a file cut at a line boundary loses games without a parse error)."""
        import argparse
        import copy
        import ppo_model
        import ppo_train
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(0)
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False)
        games = ppo_train.load_games([traj], net.trim_map, workers=1)[:2]
        ap = argparse.ArgumentParser()
        ppo_train.add_hparams(ap)
        args = ap.parse_args(["--reward", "heart_pbrs", "--minibatch", "64", "--epochs", "1"])
        learner = ppo_train.Learner(copy.deepcopy(net), None, args, torch.device("cpu"))
        with self.assertRaises(ValueError):
            learner.update(copy.deepcopy(games), log=lambda line: None)
        with_phi = copy.deepcopy(games)
        with_phi[0]["steps"][0]["phi"] = 0.3
        self.assertEqual(learner.update(with_phi, log=lambda line: None)["games"], 2)
        with tempfile.TemporaryDirectory() as d:
            init = os.path.join(d, "init.bin")
            net.to_bin(init)
            argv = ["--state", os.path.join(d, "state.pt"), "--init", init, "--traj", traj, "--device", "cpu",
                    "--out-bin", os.path.join(d, "out.bin"), "--expect-games", str(len(ppo_train.load_games([traj], None, workers=1)) + 1)]
            with self.assertRaises(SystemExit):
                ppo_train.cmd_update(argv)
            self.assertFalse(os.path.exists(os.path.join(d, "state.pt")))


if __name__ == "__main__":
    unittest.main()
