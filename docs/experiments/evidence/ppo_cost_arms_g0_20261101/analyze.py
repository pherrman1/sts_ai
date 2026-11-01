#!/usr/bin/env python3
"""PPO cost arms K1-K5 and G0 (PREREG.md). usage: analyze.py OUT_ROOT X1_GAMES_CSV [result.json]

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log} from run_unit.sh. X1_GAMES_CSV is
docs/experiments/evidence/cheap_combat_proxy_20261031/games.csv on main (§739). Frozen before any campaign game ran.
"""
import csv, json, random, re, sys
from pathlib import Path

P = 6.0546875  # §691, production combat
LO, HI = 0.5 * P, 1.5 * P
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
K_SEEDS = range(111382000, 111383024)
G_SEEDS = range(111372000, 111374048)


def load(root):
    games, bad = {}, []  # (arm, seed) -> (kill, act3, floor, cpu seconds from the BEST line)
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        m = WIN.search(done.with_suffix(".log").read_text()) if d["rc"] == "0" else None
        if not m:
            bad.append(d["tag"])
            continue
        floor = float(m.group(2))
        games[(arm, int(seed))] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)))
    return games, sorted(bad)


def boot(d, salt, reps=10000):
    n = len(d)
    rng = random.Random(salt)
    b = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return [100 * b[int(0.025 * reps)], 100 * b[int(0.975 * reps) - 1]]


def paired(games, a, b, seeds, idx=0, salt=20261101):
    s = [x for x in seeds if (a, x) in games and (b, x) in games]
    if not s:
        return None
    d = [games[(b, x)][idx] - games[(a, x)][idx] for x in s]
    return {"n": len(s), "rate_a_pct": 100 * sum(games[(a, x)][idx] for x in s) / len(s),
            "rate_b_pct": 100 * sum(games[(b, x)][idx] for x in s) / len(s),
            "diff_pp": 100 * sum(d) / len(s), "ci95_pp": boot(d, salt)}


def k_verdict(r):
    if r is None:
        return "MISSING"
    lo, hi = r["ci95_pp"]
    if lo > 0 and LO <= r["diff_pp"] <= HI:
        return "VALID"
    if hi < LO:
        return "INVALID"
    return "INCONCLUSIVE"


def main():
    games, bad = load(sys.argv[1])
    x1 = {int(r["seed"]): r for r in csv.DictReader(open(sys.argv[2]))}
    out = {"games": len(games), "bad_or_missing": bad, "reference_691_pp": P, "arms": {}}
    for k in ("K1", "K2", "K3", "K4", "K5"):
        r = paired(games, "R" + k, "F" + k, K_SEEDS)
        cs = [x for x in K_SEEDS if all((a, x) in games for a in ("R" + k, "F" + k, "FB"))]
        cost = (sum(games[("R" + k, x)][3] + games[("F" + k, x)][3] for x in cs)
                / (2 * sum(games[("FB", x)][3] for x in cs))) if cs else None
        ds = [x for x in K_SEEDS if ("R" + k, x) in games and ("F" + k, x) in games and x in x1]
        did = [(games[("F" + k, x)][0] - games[("R" + k, x)][0])
               - (int(x1[x]["F1000_kill"]) - int(x1[x]["R1000_kill"])) for x in ds]
        out["arms"][k] = {"heart": r, "verdict": k_verdict(r), "cost_vs_FB": cost,
                          "act3": paired(games, "R" + k, "F" + k, K_SEEDS, idx=1),
                          "did_vs_x1_1000_pp": {"n": len(ds), "did_pp": 100 * sum(did) / len(ds), "ci95_pp": boot(did, 7)}
                          if ds else None}
    admitted = [k for k, v in out["arms"].items() if v["verdict"] == "VALID" and v["cost_vs_FB"] is not None]
    out["admitted"] = admitted
    out["chosen"] = min(admitted, key=lambda k: out["arms"][k]["cost_vs_FB"]) if admitted else "B"
    fb = [x for x in K_SEEDS if ("FB", x) in games and x in x1]
    out["fb_vs_x1_f1000"] = {"n": len(fb), "same_kill": sum(games[("FB", x)][0] == int(x1[x]["F1000_kill"]) for x in fb),
                             "same_floor": sum(int(games[("FB", x)][2]) == int(x1[x]["F1000_floor"]) for x in fb)}
    g = paired(games, "GS", "GH", G_SEEDS)
    out["G0"] = {"heart": g, "act3": paired(games, "GS", "GH", G_SEEDS, idx=1),
                 "mean_floor_diff": (lambda s: sum(games[("GH", x)][2] - games[("GS", x)][2] for x in s) / len(s) if s else None)(
                     [x for x in G_SEEDS if ("GS", x) in games and ("GH", x) in games]),
                 "decision": "MISSING" if g is None else ("STUDENT_SEL" if g["ci95_pp"][1] < 0 else "HEART1")}
    print(json.dumps(out, indent=1))
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
