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

if __name__ == "__main__":
    unittest.main()
