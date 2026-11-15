"""tools/heart1/ppo_signals.py: fight extraction, per-screen signals and the report on synthetic trajectories.

Skipped without torch (ppo_signals reuses ppo_train's loader, rewards and GAE, and ppo_train imports torch)."""
import gzip
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools", "heart1", "ppo_signals.py")
sys.path.insert(0, os.path.join(HERE, "..", "tools", "heart1"))
try:
    import torch  # noqa: F401
except ImportError:
    torch = None

# MonsterEncounter ids (include/constants/MonsterEncounters.h)
JAW_WORM, CULTIST, GREMLIN_NOB, SLIME_BOSS, AUTOMATON = 2, 1, 15, 18, 37
AWAKENED_ONE, TIME_EATER, THE_HEART = 53, 54, 57


def decision(seed, idx, act, floor, screen, hp, fought, boss, logits=(0.0, 0.0), chosen=0, value=0.5, max_hp=80):
    z = list(logits)
    m = max(z)
    lse = m + math.log(sum(math.exp(x - m) for x in z))
    return {"type": "decision", "seed": seed, "idx": idx, "act": act, "floor": floor, "screen": screen,
            "source": "heart1_ppo" if len(z) > 1 else "heart1_ppo_single", "n": len(z), "chosen": chosen,
            "logits": z, "logp": z[chosen] - lse, "temp": 1.0, "value": value,
            "record": {"obs.fixed_observation": [hp, max_hp, 99, floor, boss, 0, 20, 0, 0, 0],
                       "obs.v2.fought": list(fought)}}


def game_line(seed, outcome):
    return {"type": "game", "schema": "heart1-ppo-traj-v1", "seed": seed, "outcome": outcome}


def game_a(seed):
    """Act 1: Jaw Worm (-10), Cultist and Nob between two decisions (no HP), Slime Boss on floor 16 (-20);
    act 2: dies to Automaton at 30 HP. Map decisions carry two choices, rewards one."""
    d = [decision(seed, 0, 1, 0, 5, 80, [], 0, logits=(1.0, 0.0), chosen=1),
         decision(seed, 1, 1, 1, 2, 70, [JAW_WORM], 0, logits=(0.0,)),
         decision(seed, 2, 1, 3, 2, 60, [JAW_WORM, CULTIST, GREMLIN_NOB], 0, logits=(0.0,)),
         decision(seed, 3, 1, 15, 5, 50, [JAW_WORM, CULTIST, GREMLIN_NOB], 0, logits=(0.0, 0.0)),
         decision(seed, 4, 1, 16, 2, 30, [JAW_WORM, CULTIST, GREMLIN_NOB], 0, logits=(0.0,)),
         decision(seed, 5, 2, 17, 5, 30, [], 4, logits=(2.0, 0.0), chosen=0)]
    return d, game_line(seed, {"act": 2, "floor": 33, "heart_kill": False, "hp": 0, "fights": 5,
                               "death_encounter": AUTOMATON})


def game_b(seed):
    """Act 3 to the Heart: act 3 ends by an act change (first boss Awakened One, A20 second boss, no HP),
    then the Heart is killed from 60 HP to 45."""
    d = [decision(seed, 0, 3, 49, 5, 70, [], 8, logits=(0.0, 0.0)),
         decision(seed, 1, 4, 52, 5, 60, [], 9, logits=(0.0, 0.0))]
    return d, game_line(seed, {"act": 4, "floor": 56, "heart_kill": True, "hp": 45, "fights": 3,
                               "death_encounter": -1})


def game_c(seed):
    """Dies to Time Eater on floor 51: the A20 second boss after winning Awakened One."""
    d = [decision(seed, 0, 3, 49, 5, 70, [], 8, logits=(0.0, 0.0))]
    return d, game_line(seed, {"act": 3, "floor": 51, "heart_kill": False, "hp": 0, "fights": 2,
                               "death_encounter": TIME_EATER})


def game_d(seed):
    """Dies to the first Act 3 boss (Awakened One) on floor 50: no HP loss (wins of it are never measurable)."""
    d = [decision(seed, 0, 3, 49, 5, 70, [], 8, logits=(0.0, 0.0))]
    return d, game_line(seed, {"act": 3, "floor": 50, "heart_kill": False, "hp": 0, "fights": 1,
                               "death_encounter": AWAKENED_ONE})


def game_e(seed):
    """Wins both A20 Act 3 bosses without all keys: the game ends in the Act 3 victory room (floor 52)."""
    d = [decision(seed, 0, 3, 49, 5, 70, [], 8, logits=(0.0, 0.0))]
    return d, game_line(seed, {"act": 3, "floor": 52, "heart_kill": False, "hp": 40, "fights": 2,
                               "death_encounter": -1, "won": True})


def write_part(path, games):
    with gzip.open(path, "wt") as f:
        for steps, g in games:
            for s in steps:
                f.write(json.dumps(s) + "\n")
            f.write(json.dumps(g) + "\n")


@unittest.skipIf(torch is None, "torch not installed")
class PpoSignalsTest(unittest.TestCase):
    def test_game_fights(self):
        import ppo_signals as S
        import ppo_train
        names = S.encounter_names()
        self.assertEqual((names[JAW_WORM], names[SLIME_BOSS], names[THE_HEART]), ("JAW_WORM", "SLIME_BOSS",
                                                                                  "THE_HEART"))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl.gz")
            write_part(p, [game_a("1"), game_b("2"), game_c("3"), game_d("4"), game_e("5")])
            games = {g["seed"]: g for g in ppo_train.load_games([p])}
        got = [(names[e], died, loss, act) for e, died, loss, _, act in S.game_fights(games["1"], names)]
        self.assertEqual(got, [("JAW_WORM", False, 10, 1), ("CULTIST", False, None, 1),
                               ("GREMLIN_NOB", False, None, 1), ("SLIME_BOSS", False, 20, 1),
                               ("AUTOMATON", True, 30, 2)])
        got = [(names[e], died, loss, act) for e, died, loss, _, act in S.game_fights(games["2"], names)]
        self.assertEqual(got, [("AWAKENED_ONE", False, None, 3), (S.SECOND_BOSS, False, None, 3),
                               ("THE_HEART", False, 15, 4)])
        got = [(names[e], died) for e, died, *_ in S.game_fights(games["3"], names)]
        self.assertEqual(got, [("AWAKENED_ONE", False), (S.SECOND_BOSS, True)])
        got = [(names[e], died, loss) for e, died, loss, *_ in S.game_fights(games["4"], names)]
        self.assertEqual(got, [("AWAKENED_ONE", True, None)])
        got = [(names[e], died, loss) for e, died, loss, *_ in S.game_fights(games["5"], names)]
        self.assertEqual(got, [("AWAKENED_ONE", False, None), (S.SECOND_BOSS, False, None)])

    def test_extract_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            run = os.path.join(d, "ARM")
            os.makedirs(os.path.join(run, "parts"))
            with open(os.path.join(run, "config.json"), "w") as f:
                json.dump({"parts": 2, "pipeline": 1, "value_warmup": 1, "learner_argv": ["--lam", "1.0"]}, f)
            for it in range(3):
                base = 100 * it
                write_part(os.path.join(run, "parts", f"traj-{it:04d}-p0.jsonl.gz"),
                           [game_a(str(base + 1)), game_b(str(base + 2))])
                if it < 2:   # iteration 2 is incomplete: skipped
                    write_part(os.path.join(run, "parts", f"traj-{it:04d}-p1.jsonl.gz"), [game_c(str(base + 3))])
            out = os.path.join(d, "sig.jsonl")
            cmd = [sys.executable, TOOL, "extract", "--run", run, "--out", out]
            subprocess.run(cmd, check=True, capture_output=True)
            with open(out) as f:
                rows = [json.loads(line) for line in f]
            self.assertEqual([r["iteration"] for r in rows], [0, 1])
            r = rows[0]
            self.assertEqual((r["games"], r["outcome"]["heart"], r["outcome"]["act4"]), (3, 1, 1))
            self.assertEqual((r["behaviour_net"], r["value_only"], r["parts"]), ("net-0000", True, 2))
            self.assertEqual(rows[1]["behaviour_net"], "net-0000")
            self.assertEqual(r["coverage"], {"fights_seen": 10, "fights_reported": 10})
            self.assertEqual(r["act_fights"], {"1": {"fights": 4, "deaths": 0}, "2": {"fights": 1, "deaths": 1},
                                               "3": {"fights": 4, "deaths": 1}, "4": {"fights": 1, "deaths": 0}})
            enc = r["encounters"]
            self.assertEqual((enc["JAW_WORM"]["hp_n"], enc["JAW_WORM"]["hp_sum"]), (1, 10))
            self.assertEqual((enc["CULTIST"]["fights"], enc["CULTIST"]["hp_n"]), (1, 0))
            self.assertEqual((enc["AUTOMATON"]["deaths"], enc["AUTOMATON"]["kind"]), (1, "boss"))
            self.assertAlmostEqual(enc["THE_HEART"]["frac_sum"], 15 / 80)
            # Map decisions: game a (1,0) chose 1, (0,0), (2,0) chose 0; game b (0,0) twice; game c (0,0).
            m = r["screens"]["map"]
            self.assertEqual(m["n"], 6)
            h = lambda p: -sum(q * math.log(q) for q in p)   # noqa: E731
            p1 = [math.exp(1) / (math.exp(1) + 1), 1 / (math.exp(1) + 1)]
            p2 = [math.exp(2) / (math.exp(2) + 1), 1 / (math.exp(2) + 1)]
            self.assertAlmostEqual(m["entropy"], (h(p1) + h(p2) + 4 * math.log(2)) / 6, places=5)
            self.assertAlmostEqual(m["explore"], 1 / 6, places=5)
            # lam 1, gamma 1, heart reward: A = 1{heart} - V = -0.5 in games a and c, +0.5 in game b.
            self.assertAlmostEqual(m["adv_mean"], (3 * -0.5 + 2 * 0.5 - 0.5) / 6, places=5)
            self.assertAlmostEqual(m["adv_abs_share"], 1.0, places=5)   # every multi-choice decision is a map one
            self.assertEqual(set(r["screens"]), {"map"})
            # Re-running reads nothing new.
            again = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertIn("nothing new", again.stdout)
            rep = os.path.join(d, "rep.json")
            subprocess.run([sys.executable, TOOL, "report", "--signals", out, "--ref", "0", "--window", "1",
                            "--min-fights", "1", "--out", rep, "--md", os.path.join(d, "rep.md")],
                           check=True, capture_output=True)
            with open(rep) as f:
                rp = json.load(f)
            self.assertEqual(rp["ref_iterations"], [0])
            w = rp["latest"]
            self.assertEqual((w["first"], w["last"], w["rollback_net"]), (1, 1, "net-0000"))
            self.assertEqual(w["cmp"]["outcome"]["heart"]["diff"], 0.0)
            self.assertEqual(w["cmp"]["screens"]["map"]["d_entropy"], 0.0)
            self.assertEqual(rp["tipping"], {})
            jaw = [e for e in w["cmp"]["encounters"] if e["encounter"] == "JAW_WORM"]
            self.assertEqual((jaw[0]["fights"], jaw[0]["z_death"], "hp_loss" in jaw[0]), (1, 0.0, False))   # hp_n 1

    def test_tipping_direction(self):
        import ppo_signals as S

        def win(i, hz, dz):
            return {"first": i, "last": i, "rollback_net": f"net-{i - 1:04d}",
                    "cmp": {"outcome": {"heart": {"z": hz}, "act4": {"z": 0.0}}, "act_death": {"3": {"z": dz}}}}
        # Heart down twice in a row (worse, rollback); act-3 deaths down (better, no rollback); a sign flip resets.
        ws = [win(5, -3.5, 0.0), win(6, 3.2, -3.1), win(7, -3.4, -3.3), win(8, -3.6, 0.0)]
        t = S.tipping(ws, 3.0, 2)
        self.assertEqual((t["heart"]["window_first"], t["heart"]["direction"], t["heart"]["rollback_net"]),
                         (7, "worse", "net-0006"))
        self.assertEqual((t["death_act3"]["window_first"], t["death_act3"]["direction"],
                          t["death_act3"]["rollback_net"]), (6, "better", None))
        self.assertNotIn("act4", t)

    def test_z2(self):
        import ppo_signals as S
        self.assertIsNone(S._z2(1, 0, 1, 10))
        # 30/100 vs 20/100: pooled p 0.25, se sqrt(0.25*0.75*0.02)
        self.assertAlmostEqual(S._z2(30, 100, 20, 100), 0.1 / math.sqrt(0.25 * 0.75 * 0.02), places=3)


if __name__ == "__main__":
    unittest.main()
