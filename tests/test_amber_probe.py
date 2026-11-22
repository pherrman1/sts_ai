"""Tests for the decision-explainability search (RunDriver probe roots, tools/az_bench/amber_probe.py), the live
advisor proxy (tools/az_bench/amber_advisor.py) and the explanation of one decision (explain_live.py).

With a built az_bench_native module and torch: probe roots are searched once each with the full budget, nothing is
played, the per-edge numbers are consistent (visits sum to the root's, the improved policy and each searched
edge's outcome distribution sum to 1, the pick is a candidate), a noise-free probe is reproducible, and captured
search roots of a normal run (capture_rate) are valid probe roots. With az_bench_live too: a captured live
observation (tests/fixtures) is imported, searched and its actions lowered to live actions. The proxy's NDJSON
plumbing is tested with a stub advisor and a stub evaluator (no module needed)."""

import glob
import importlib
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools", "az_bench")
sys.path.insert(0, TOOLS)
NATIVE = sorted(glob.glob(os.path.join(ROOT, "build", "*", "az_bench_native*.so")),
                key=lambda p: ("debug" in p, p))   # an optimized module first: self-play on a Debug module is far slower
LIVE = sorted(glob.glob(os.path.join(ROOT, "build", "*", "az_bench_live*.so")))

try:
    import torch
    HAVE_TORCH = True
except ImportError:
    HAVE_TORCH = False


def module(paths, name):
    sys.path.insert(0, os.path.dirname(paths[0]))
    m = importlib.import_module(name)
    return m if hasattr(m, "GameState") else None


def small_net():
    import amber_net
    torch.manual_seed(0)
    net = amber_net.AmberNet(d=32, layers=1, hp_floors=56)
    return net.eval()


@unittest.skipUnless(HAVE_TORCH and (NATIVE or LIVE), "needs torch and a built az_bench_native / az_bench_live")
class ProbeSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nat = (module(NATIVE, "az_bench_native") if NATIVE else None) or (
            module(LIVE, "az_bench_live") if LIVE else None)
        if cls.nat is None:
            raise unittest.SkipTest("az_bench_native without probe roots (rebuild)")
        import amber_probe
        cls.ap = amber_probe
        cls.net = small_net()

    def check(self, r):
        self.assertEqual(r["status"], "searched")
        n = np.asarray(r["n"])
        self.assertEqual(int(n.sum()) + 1, int(r["root_n"]))   # the root's own evaluation counts once
        self.assertGreaterEqual(int(r["root_n"]), 16)
        self.assertAlmostEqual(float(np.sum(r["policy"])), 1.0, places=5)
        self.assertTrue(bool(r["candidate"][r["pick"]]))
        self.assertEqual(int(r["bits"][r["pick"]]), int(r["pick_bits"]))
        for i in np.flatnonzero(n):
            self.assertAlmostEqual(float(np.sum(r["dist"][i])), 1.0, places=3)
            self.assertTrue(0.0 <= float(r["pwin"][i]) <= 1.0)
            self.assertTrue(0.0 <= float(r["ehp"][i]) <= 255.0)
        self.assertTrue(np.all(np.isnan(np.asarray(r["pwin"])[n == 0])))
        self.assertAlmostEqual(float(np.sum(r["search_dist"])), 1.0, places=3)
        s = r["sample"]
        self.assertEqual(len(s["a_type"]), len(r["bits"]))
        self.assertAlmostEqual(float(np.sum(s["policy"])), 1.0, places=4)

    def test_neow_probes(self):
        states = [self.nat.GameState.new_run(160100040 + i, 20, True) for i in range(3)]
        self.assertEqual(states[0].floor, 0)
        res = self.ap.probe_states(self.nat, self.net, states, full_sims=16, games=2)
        self.assertEqual([r["probe"] for r in res], [0, 1, 2])
        for r in res:
            self.check(r)
        again = self.ap.probe_states(self.nat, self.net, states[:1], full_sims=16, games=1)[0]
        first = self.ap.probe_states(self.nat, self.net, states[:1], full_sims=16, games=1)[0]
        self.assertEqual(list(again["n"]), list(first["n"]))   # one root per driver: same search
        self.assertEqual(int(again["pick"]), int(first["pick"]))

    def test_captures_are_probe_roots(self):
        drv = self.nat.RunDriver(workers=1, games=1, seed_base=160100050, max_runs=1, ascension=20, full_sims=8,
                                 fast_sims=4, full_candidates=4, fast_candidates=2, keep_full=0.0, sim_help=True,
                                 capture_rate=1.0)
        bufs = self.ap._buffers(64)
        caps = []
        drv.start()
        try:
            while len(caps) < 4 and drv.stats()["runs_done"] < 1:
                got = drv.next_flat(8, 1, 20, self.ap.ROW_BUCKETS, self.ap.TOK_BUCKETS, self.ap.ACT_BUCKETS, bufs)
                if got is None:
                    continue
                tickets, rows, Rp, Tp, Ap = got
                lg, F, ehp, hpf, p, ph = self.ap.evaluate_flat(self.net, bufs, Rp, Tp, Ap)
                drv.submit(tickets, lg[:rows].contiguous().numpy(), F[:rows].numpy(), ehp[:rows].numpy())
                caps += drv.take_captures()
        finally:
            drv.stop()
        caps += drv.take_captures()
        self.assertGreaterEqual(len(caps), 2)
        self.assertEqual(caps[0]["seed"], 160100050)
        res = self.ap.probe_states(self.nat, self.net, [c["state"] for c in caps[:3]], full_sims=16)
        for r, c in zip(res, caps):
            self.assertEqual(r["floor"], c["floor"])
            if r["status"] == "searched":
                self.check(r)

    def test_probe_needs_distributions(self):
        st = [self.nat.GameState.new_run(160100060, 20, True)]
        with self.assertRaises(Exception):
            self.nat.RunDriver(workers=1, games=1, probe_roots=st, sim_help=True)


@unittest.skipUnless(HAVE_TORCH and LIVE, "needs torch and a built az_bench_live")
class LiveProbe(unittest.TestCase):
    def test_live_fixture(self):
        nat = module(LIVE, "az_bench_live")
        self.assertTrue(nat.GameState.live_import)
        import amber_probe as ap
        import explain as ex
        import explain_live as el
        obs = open(os.path.join(ROOT, "tests", "fixtures", "live_act1_boss_card_reward.json")).read()
        st = nat.GameState.from_live(obs)
        self.assertTrue(st.is_live)
        self.assertEqual(st.floor, 16)
        net = small_net()
        r = ap.probe_states(nat, net, [st], full_sims=16)[0]
        self.assertEqual(r["status"], "searched")
        lowered = [json.loads(st.lower_action(int(b))) for b in r["bits"]]
        self.assertIn({"kind": "skip"}, lowered)
        self.assertTrue(any(a.get("kind") == "choose" for a in lowered))
        row = ap.row_of(r["sample"])
        rep = el.explain_decision(net, row, ex.Vocab(), int(r["pick"]), int(np.argsort(-np.asarray(r["score"]))[1]))
        self.assertEqual(len(rep["options"]), len(r["bits"]))
        self.assertIn("pair", rep)
        with self.assertRaises(ValueError):
            nat.GameState.from_live('{"boundary": "ooc", "ooc": {"schemaVersion": 99}}')


class AdvisorProxy(unittest.TestCase):
    STUB = ("import json,sys\n"
            "for line in sys.stdin:\n"
            "    q=json.loads(line)\n"
            "    if q.get('kind')=='hello':\n"
            "        print(json.dumps({'protocol':'sts_model_inspector_v1','kind':'hello','status':'READY','evaluators':[]}),flush=True)\n"
            "    else:\n"
            "        print(json.dumps({'kind':'analysis','status':'OK','session':q['session'],'sequence':q['sequence'],"
            "'observationHash':q['observationHash'],'evaluators':[{'id':'inner','b':q['observation']['boundary']}]}),flush=True)\n")

    def run_proxy(self, lines, mode):
        import amber_advisor as aa
        with tempfile.TemporaryDirectory() as d:
            stub = os.path.join(d, "stub_advisor")
            with open(stub, "w") as f:
                f.write("#!" + sys.executable + "\n" + self.STUB)
            os.chmod(stub, 0o755)
            out = io.StringIO()
            calls = []
            aa.serve(io.StringIO("".join(json.dumps(x) + "\n" for x in lines)), out, stub,
                     lambda obs: calls.append(obs) or {"id": aa.EVALUATOR, "status": "OK", "x": 1}, mode)
            return [json.loads(x) for x in out.getvalue().splitlines()], calls

    def test_modes(self):
        req = lambda i, b: {"protocol": "sts_model_inspector_v1", "kind": "observation", "session": "s",  # noqa: E731
                            "sequence": i, "observationHash": f"h{i}", "observation": {"boundary": b}}
        lines = [{"protocol": "sts_model_inspector_v1", "kind": "hello"}, req(1, "combat"), req(2, "ooc")]
        out, calls = self.run_proxy(lines, "only")
        self.assertEqual([o["kind"] for o in out], ["hello", "analysis", "analysis"])
        self.assertEqual(out[1]["evaluators"], [{"id": "inner", "b": "combat"}])
        self.assertEqual([e["id"] for e in out[2]["evaluators"]], ["amber_explain_v1"])
        self.assertEqual((out[2]["session"], out[2]["sequence"], out[2]["observationHash"]), ("s", 2, "h2"))
        self.assertEqual(len(calls), 1)
        out, calls = self.run_proxy(lines, "both")
        self.assertEqual([e["id"] for e in out[2]["evaluators"]], ["inner", "amber_explain_v1"])
        self.assertEqual(out[1]["evaluators"], [{"id": "inner", "b": "combat"}])


if __name__ == "__main__":
    unittest.main()
