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

        arch = ["--extra-blocks", "1", "--critic", "separate", "--aux-heads", "floor,act4", "--value-sparse", "3"]

        def run(micro, value_clip, flags=()):
            ap = argparse.ArgumentParser()
            ppo_train.add_hparams(ap)
            args = ap.parse_args(["--minibatch", "64", "--epochs", "1", "--kl-coef", "0.1", "--entropy-coef", "0.01",
                                  "--micro-batch", str(micro), "--value-clip", str(value_clip)] + list(flags))
            st = ppo_train.structure_of(args)
            start = ppo_model.construct(net, st["extra_blocks"], st["critic"], st["aux"], seed=0) if flags else net
            learner = ppo_train.Learner(copy.deepcopy(start), copy.deepcopy(net), args, torch.device("cpu"))
            stats = learner.update(copy.deepcopy(games), log=lambda line: None)
            return learner.net.state_dict(), stats

        for value_clip, flags in ((0, ()), (0.2, ()), (0, arch), (0.2, arch)):
            ref, s_ref = run(0, value_clip, flags)
            same, s_same = run(64, value_clip, flags)
            chunked, s_ch = run(23, value_clip, flags)
            for k in ref:
                self.assertTrue(torch.equal(ref[k], same[k]), k)
                self.assertTrue(torch.allclose(ref[k], chunked[k], atol=1e-6, rtol=1e-5), k)
            for k in ("policy", "value", "entropy", "kl_anchor", "clipfrac", "approx_kl", "aux"):
                self.assertAlmostEqual(s_ref[k], s_ch[k], places=5)
                self.assertEqual(s_ref[k], s_same[k])
            self.assertEqual(s_ref["minibatches"], s_ch["minibatches"])

    def test_phi_potentials(self):
        """heart_phi: potentials computed while loading (both loader paths), telescoping, and the fit's floor table."""
        import csv
        import json
        import ppo_model
        import ppo_phi
        import ppo_phi_fit
        import ppo_train
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        traj = os.path.join(root, "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        with tempfile.TemporaryDirectory() as d:
            rows = [("A", 0, 1, 1, 56), ("A", 0, 2, 0, 16), ("A", 0, 3, 0, 33), ("A", 0, 4, 0, "")]
            with open(os.path.join(d, "games-0000.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["arm", "iteration", "seed", "heart_kill", "floor", "net"])
                for r in rows:
                    w.writerow(list(r) + ["net-0000"])
            out = os.path.join(d, "phi.json")
            ppo_phi_fit.cmd_floor_table(["--games", os.path.join(d, "games-*.csv"), "--out", out])
            t = json.load(open(out))["table"]
            # 3 games with a floor, 1 kill: P(kill | reached f) = 1/3 up to 16, 1/2 on 17..33, 1 on 34..56.
            self.assertAlmostEqual(t[16], 1 / 3, places=5)
            self.assertAlmostEqual(t[17], 1 / 2, places=5)
            self.assertAlmostEqual(t[34], 1.0, places=5)
            m = ppo_phi.load(out)
            trim = ppo_model.PolicyNet(16, 2, 32, 1, {**{k: 8 for k in ppo_model.TABLES},
                                                        "fixed_action": ppo_model.FA_COUNT}).trim_map
            for trim_map, workers in ((None, 1), (trim, 2)):
                games = ppo_train.load_games([traj], trim_map, workers=workers, phi_model=m)
                for g in games:
                    self.assertTrue(g["steps"])
                    for s in g["steps"]:
                        self.assertEqual(s["phi_py"], ppo_phi.value(m, s, None))
                    r = ppo_train.step_rewards(g, "heart_phi", 1.0)
                    heart = 1.0 if g["outcome"].get("heart_kill") else 0.0
                    self.assertAlmostEqual(sum(r), heart - g["steps"][0]["phi_py"], places=9)
            with self.assertRaises(ValueError):
                ppo_phi.load(out, sha256="0" * 64)

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
            again.keep_state = {2}   # serve --keep-state 2: the fork point after update 2
            self.assertTrue(again.step(s.names("")))
            loc = os.path.join(d, "local", "A")
            self.assertFalse(os.path.exists(os.path.join(loc, "state-0001.pt")))
            self.assertEqual(torch.load(os.path.join(loc, "state-0002.pt"), weights_only=False)["iteration"], 2)
            with open(os.path.join(loc, "loop-0002.json")) as f:
                self.assertEqual(len(json.load(f)["iterations"]), 2)
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

    def test_arch_constructions_preserve_the_policy(self):
        """Arch screen arms: extra identity blocks, a separate critic and zero-init aux heads leave the logits (and,
        untrained, the value) bit-identical; the native export keeps the depth; the policy trunk gets no value
        gradient with a separate critic."""
        import ppo_model
        import ppo_train
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(1)
        net = ppo_model.PolicyNet(16, 2, 32, 2, rows, False)
        with torch.no_grad():
            for p in net.parameters():
                p.copy_(0.3 * torch.randn_like(p))
        games = ppo_train.load_games([traj], net.trim_map)[:3]
        batch = ppo_model.collate([s["feat"] for g in games for s in g["steps"]])
        with torch.no_grad():
            ref_logits, ref_value = net(batch)
        for kw in ({"extra_blocks": 2}, {"critic": "separate"}, {"aux": ("floor", "act4")},
                   {"extra_blocks": 1, "critic": "separate", "aux": ("act4",)}):
            arm = ppo_model.construct(net, seed=3, **kw)
            with torch.no_grad():
                out = arm(batch)
            self.assertTrue(torch.equal(out[0], ref_logits), kw)
            self.assertTrue(torch.equal(out[1], ref_value), kw)
            self.assertEqual(len(out), 3 if "aux" in kw else 2)
            if "aux" in kw:
                self.assertEqual(int(torch.count_nonzero(out[2])), 0)
            self.assertEqual(len(arm.blocks), 2 + kw.get("extra_blocks", 0))
            with tempfile.TemporaryDirectory() as d:   # the native export: policy net, depth included
                path = os.path.join(d, "a.bin")
                arm.to_bin(path)
                back = ppo_model.PolicyNet.from_bin(path)
                self.assertEqual(len(back.blocks), len(arm.blocks))
                with torch.no_grad():
                    self.assertTrue(torch.equal(back(batch)[0], ref_logits), kw)
            restored = ppo_train.net_from_shape(ppo_train.shape_of(arm))
            restored.load_state_dict(arm.state_dict())
            with torch.no_grad():
                self.assertTrue(torch.equal(restored(batch)[0], ref_logits), kw)
        sep = ppo_model.construct(net, critic="separate")
        sep(batch)[1].sum().backward()
        for name, p in sep.named_parameters():
            if name.startswith("critic_net."):
                continue
            self.assertTrue(p.grad is None or int(torch.count_nonzero(p.grad)) == 0, name)
        self.assertGreater(sum(int(torch.count_nonzero(p.grad)) for n, p in sep.named_parameters()
                               if n.startswith("critic_net.") and p.grad is not None), 0)
        with self.assertRaises(ValueError):
            ppo_model.construct(net, aux=("hp",))
        with self.assertRaises(ValueError):
            ppo_model.construct(sep, extra_blocks=1)   # constructions apply to a plain net once

    def test_x3_deck_input(self):
        """IN_DECK: deck_aggregates on a known deck; an x3_deck net keeps the logits until trained, survives the .bin
        and state round trips, and a net without it ignores the emitted feature (old nets unchanged)."""
        import ppo_model
        import ppo_train
        cards = {c["name"]: c["id"] for c in ppo_model._cards()}
        rec = {"obs.deck.cards": [cards["STRIKE_RED"]] * 5 + [cards["DEFEND_RED"]] * 4
               + [cards["BASH"], cards["POMMEL_STRIKE"], cards["INFLAME"], cards["TRUE_GRIT"], cards["REGRET"]],
               "obs.deck.upgrades": [0] * 9 + [1, 0, 0, 1, 0]}
        # attacks 7, skills 5, powers 1, starter 9, exhaust 1 (True Grit+ only exhausts... per table), draws 1,
        # upgraded 2/14 -> 14 %, size 14, curses 1
        agg = ppo_model.deck_aggregates(rec)
        tab = {c["id"]: c for c in ppo_model._cards()}
        self.assertEqual(agg[:4], [7, 5, 1, 9])
        self.assertEqual(agg[5], 1)
        self.assertEqual(agg[6], 14)
        self.assertEqual(agg[8:], [14, 1])
        self.assertEqual(agg[4], sum(1 for i, c in enumerate(rec["obs.deck.cards"])
                                     if tab[c]["exhaust"][rec["obs.deck.upgrades"][i]]))
        costs = [tab[c]["cost"][u] for c, u in zip(rec["obs.deck.cards"], rec["obs.deck.upgrades"])
                 if tab[c]["cost"][u] >= 0]
        self.assertEqual(agg[7], (200 * sum(costs) + len(costs)) // (2 * len(costs)))
        self.assertEqual(ppo_model.deck_aggregates({"obs.deck.cards": [], "obs.deck.upgrades": []}), [0] * 10)
        here = os.path.dirname(os.path.abspath(__file__))
        traj = os.path.join(here, "..", "docs", "experiments", "evidence", "ppo_s0_smoke_20261101", "cov8.jsonl.gz")
        rows = {k: 4096 for k in ppo_model.TABLES}
        rows["fixed_action"] = ppo_model.FA_COUNT
        torch.manual_seed(2)
        net = ppo_model.PolicyNet(16, 2, 32, 1, rows, False)
        with torch.no_grad():
            for p in net.parameters():
                p.copy_(0.3 * torch.randn_like(p))
        games = ppo_train.load_games([traj], net.trim_map)[:3]
        feats = [st["feat"] for g in games for st in g["steps"]]
        self.assertIn("x3_deck", feats[0]["fv"])
        batch = ppo_model.collate(feats)
        self.assertEqual(ppo_model.FeatureStore(feats).batch(range(len(feats)))["fv"].keys(), batch["fv"].keys())
        with torch.no_grad():
            ref = net(batch)[0]
            arm = ppo_model.construct(net, inputs=("x3_deck",))
            self.assertTrue(torch.equal(arm(batch)[0], ref))
            self.assertEqual(arm.extra_inputs, ("x3_deck",))
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "x3.bin")
                arm.fixedvecs["x3_deck"].proj.weight.normal_(0, 0.05)   # trained: must change the logits
                arm.to_bin(path)
                back = ppo_model.PolicyNet.from_bin(path)
                self.assertEqual(back.extra_inputs, ("x3_deck",))
                self.assertTrue(torch.equal(back(batch)[0], arm(batch)[0]))
                self.assertFalse(torch.equal(back(batch)[0], ref))
                plain = os.path.join(d, "plain.bin")
                net.to_bin(plain)
                self.assertNotIn("x3_deck.proj.weight", ppo_model.read_bin(plain))
            restored = ppo_train.net_from_shape(ppo_train.shape_of(arm))
            restored.load_state_dict(arm.state_dict())
            self.assertTrue(torch.equal(restored(batch)[0], arm(batch)[0]))

    def test_value_sparse_mask(self):
        import ppo_train
        games = [{"seed": "5", "steps": [{"act": a} for a in (1, 1, 1, 2, 2, 2, 2, 3, 3, 3)]},
                 {"seed": "6", "steps": [{"act": 1}, {"act": 1}]}]
        m = ppo_train.value_sparse_mask(games, 3, 0, 7)
        self.assertEqual(len(m), 12)
        self.assertTrue(m[0] and m[3] and m[7])            # each act's first decision
        self.assertEqual(sum(m[:10]), 6)                    # plus 3 others
        self.assertEqual(m[10:], [True, True])              # fewer than k left: all
        self.assertEqual(m, ppo_train.value_sparse_mask(games, 3, 0, 7))
        self.assertNotEqual(m, ppo_train.value_sparse_mask(games, 3, 0, 8))

    def test_cloud_fork(self):
        """init --fork-dir: a flags-off fork reproduces the source arm's next update bit for bit (the arch screen's
        learner check); an arm fork keeps the policy, Adam moments of old tensors, and starts its actors at N+1."""
        import gzip
        import json
        import ppo_cloud
        import ppo_model
        import ppo_train
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
            local = os.path.join(d, "local")
            common = ["--env-file", env, "--one-combat-sha", "0" * 64, "--games", "8", "--parts", "2",
                      "--seed-base", "1", "--value-warmup", "0"]
            ppo_cloud.cmd_init([store, "A", "--init", init, "--iterations", "4"] + common + ["--", "--epochs", "1"])
            with gzip.open(traj, "rt") as f:
                lines = [l for l in f if l.strip()]
            seeds = sorted({json.loads(l)["seed"] for l in lines if '"type":"game"' in l})
            s = ppo_cloud.open_store(store)
            parts = []
            for k, part in enumerate((seeds[:4], seeds[4:])):
                p = os.path.join(d, f"p{k}.jsonl.gz")
                with gzip.open(p, "wt") as f:
                    f.writelines(l for l in lines if json.loads(l)["seed"] in part)
                parts.append(p)
            a = ppo_cloud.ArmLearner(s, local, "A", "cpu")
            a.keep_state = {2}

            def feed(arm, it, net_name):
                sha = ppo_cloud.sha256(os.path.join(local, arm, f"{net_name}.bin"))
                for k, p in enumerate(parts):
                    s.put(f"{arm}/traj-{it:04d}-p{k}", p, {"games": 4, "sha256": ppo_cloud.sha256(p),
                                                           "net": net_name, "net_sha256": sha, "actor_s": 1.0,
                                                           "seed_first": 1})
            for it in range(4):   # pipeline 1: iteration i played by net-(i-1)
                feed("A", it, f"net-{max(it - 1, 0):04d}")
                self.assertTrue(a.step(s.names("")))
            src = os.path.join(local, "A")
            hp = ["--epochs", "1"]
            fork = [store, "B", "--fork-dir", src, "--fork-at", "2", "--local", local, "--iterations", "4"] + common
            with self.assertRaises(SystemExit):   # the source's seeds and layout are binding
                ppo_cloud.cmd_init([x if x != "8" else "16" for x in fork] + ["--"] + hp)
            ppo_cloud.cmd_init(fork + ["--"] + hp)
            b = ppo_cloud.ArmLearner(s, local, "B", "cpu")
            self.assertEqual(b.next_it, 2)
            self.assertEqual(sorted(n for n in s.names("B/")),
                             ["B/config", "B/net-0002", "B/stats-0002", "B/traj-0002-p0", "B/traj-0002-p1"])
            self.assertTrue(b.step(s.names("")))   # trains on A's reused iteration-2 parts
            self.assertEqual(ppo_cloud.sha256(os.path.join(local, "B", "net-0003.bin")),
                             ppo_cloud.sha256(os.path.join(src, "net-0003.bin")))
            sb = torch.load(os.path.join(local, "B", "state.pt"), weights_only=False)
            self.assertEqual(sb["iteration"], 3)
            cfg = json.load(open(os.path.join(local, "B", "config.json")))
            self.assertEqual(cfg["start_iteration"], 3)
            self.assertEqual(cfg["fork"]["at"], 2)
            # An arm with every structural flag: same policy at the fork, old Adam moments kept, new tensors none.
            hc = ["--epochs", "1", "--extra-blocks", "1", "--critic", "separate", "--aux-heads", "floor,act4",
                  "--value-sparse", "2"]
            ppo_cloud.cmd_init([store, "C", "--fork-dir", src, "--fork-at", "2", "--local", local,
                                "--iterations", "4"] + common + ["--"] + hc)
            games = ppo_train.load_games([parts[0]], False)
            batch = ppo_model.collate([st["feat"] for g in games for st in g["steps"]])
            with torch.no_grad():
                ref = ppo_model.PolicyNet.from_bin(os.path.join(src, "net-0002.bin"))(batch)[0]
                got = ppo_model.PolicyNet.from_bin(os.path.join(local, "C", "net-0002.bin"))(batch)[0]
            self.assertTrue(torch.equal(ref, got))
            ap = __import__("argparse").ArgumentParser()
            ppo_train.add_hparams(ap)

            def args_for(argv, state):
                ns = ap.parse_args(argv)
                ns.state, ns.init = state, None
                return ns
            cl = ppo_train.make_learner(args_for(hc, os.path.join(local, "C", "state.pt")), torch.device("cpu"))
            src_l = ppo_train.make_learner(args_for(hp, os.path.join(src, "state-0002.pt")), torch.device("cpu"))
            old = dict(src_l.net.named_parameters())
            n_old = n_new = 0
            for name, p in cl.net.named_parameters():
                if name in old:
                    n_old += 1
                    self.assertTrue(torch.equal(cl.opt.state[p]["exp_avg"], src_l.opt.state[old[name]]["exp_avg"]))
                else:
                    n_new += 1
                    self.assertNotIn(p, cl.opt.state)
            self.assertGreater(n_old, 0)
            self.assertGreater(n_new, 0)
            with self.assertRaises(SystemExit):   # a running arm's structure is fixed: flags must match its state
                ppo_train.make_learner(args_for(hp, os.path.join(local, "C", "state.pt")), torch.device("cpu"))
            c = ppo_cloud.ArmLearner(s, local, "C", "cpu")
            self.assertTrue(c.step(s.names("")))
            st = json.load(open(os.path.join(local, "C", "loop.json")))["iterations"][-1]
            self.assertLess(st["value_decisions"], st["decisions"])
            self.assertGreater(st["aux"], 0)

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
