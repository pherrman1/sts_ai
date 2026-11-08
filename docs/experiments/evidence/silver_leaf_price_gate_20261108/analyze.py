#!/usr/bin/env python3
"""Silver leaf price gate (PREREG.md): arms D (default leaf), P1 (stage-4 global prices) and PF (P1 with every
non-Fairy potion at 11), net-0420 policy alone, flat Silver 1,000, new seeds 111820000-111822047, all three arms on
every seed.

    python3 analyze.py OUT_ROOT result.json
    python3 analyze.py --self-test

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log,err} from run_unit.sh (verify_campaign.py --extract
DIR writes DIR/out/units/<seed>/).
1. Primary, two contrasts X - D for X in (P1, PF): d = Heart kill X - D per seed. A seed counts for a contrast if both
   of its games finished rc 0 with all log checks and an ARM-SEED.env whose three leaf flags match the arm (review
   G-N1, added 2026-11-08 before any game of the block was read; a mismatch is listed under env_mismatch and the
   game counts as failed) (a combat abort is a counted loss, listed); dropped seeds are listed,
   never imputed; more than 20 dropped seeds in a contrast = INCOMPLETE. The gate per contrast
   (tools/sprt_gate.py gainer, alpha 0.025 = Bonferroni over the two contrasts, beta 0.05, look 64, cap = number of
   analysed seeds, at most 2,048) gets the seeds gap-free (key = rank in ascending seed order). PASS = GO;
   NOT_SHOWN = NOT_SHOWN; at CAP the 97.5% seed bootstrap of the mean d decides (10,000 resamples, seed 20261108):
   GO if lo > 0, STOP if mean <= 0, else INCONCLUSIVE. The 95% CI is reported in every case.
2. Candidate rule: only one contrast GO -> that arm; both GO -> P1 only if the 95% CI of P1 - PF is above 0, else PF;
   neither -> none.
3. Secondary (pre-registered, not a gate): each contrast through sprt_gate nonregression (d0 -1.5 pp, alpha = beta =
   0.05) and the bootstrap reading NOT_WORSE if the 95% lo > -1.5 pp; P1 - PF with its 95% CI.
4. Descriptive: Act-3 clears, mean floor, cpu_sec/run per arm and ratio to D, combat aborts, games with wall > 300 s.
"""
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SEEDS = range(111820000, 111822048)
ARMS = ("D", "P1", "PF")
MAX_DROPPED = 20
LEAF_KEYS = ("STS_SILVER_POTION_WEIGHTS", "STS_SILVER_MAXHP_WEIGHT", "STS_SILVER_GOLD_WEIGHT")
LEAF_ENV = {"D": (None, None, None), "P1": ("*=3.7,FAIRY_POTION=47.6", "2.4", "0.12"),
            "PF": ("*=11,FAIRY_POTION=47.6", "2.4", "0.12")}
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)


def leaf_env(path):
    if not path.exists():
        return None
    env = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return tuple(env.get(k) for k in LEAF_KEYS)


def load(root):
    games, bad, aborts, mismatch = {}, [], [], []
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm not in ARMS:
            raise ValueError(f"unknown arm in {d['tag']}")
        log = done.with_suffix(".log").read_text()
        m = WIN.search(log) if d["rc"] == "0" else None
        if not m:
            bad.append(d["tag"])
            continue
        if leaf_env(done.with_suffix(".env")) != LEAF_ENV[arm]:
            mismatch.append(d["tag"])
            bad.append(d["tag"])
            continue
        key = (arm, int(seed))
        if key in games:
            raise ValueError(f"{d['tag']} twice")
        if d.get("abort") == "1":
            aborts.append(d["tag"])
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)), int(d["wall"]))
    return games, sorted(bad), sorted(aborts), sorted(mismatch)


def boot(x, level=95.0, seed=20261108):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))


def gate(pairs, variant, cap, alpha):
    g = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs, "--variant", variant,
                        "--look", "64", "--cap", str(cap), "--alpha", str(alpha), "--beta", "0.05"],
                       capture_output=True, text=True)
    if g.returncode != 0:
        raise RuntimeError(f"sprt_gate failed: {g.stderr.strip()}")
    return json.loads(g.stdout)


def contrast(games, arm, outdir):
    seeds = [s for s in SEEDS if ("D", s) in games and (arm, s) in games]
    dropped = [s for s in SEEDS if s not in set(seeds)]
    if not seeds:
        return {"n": 0, "dropped": dropped, "verdict": "INCOMPLETE", "nonregression_reading": "NOT_SHOWN"}
    a = np.array([games[("D", s)] for s in seeds], float)
    b = np.array([games[(arm, s)] for s in seeds], float)
    d = b[:, 0] - a[:, 0]
    lo95, hi95 = boot(d)
    lo975, hi975 = boot(d, 97.5)
    pairs = os.path.join(outdir, f"pairs_{arm}.csv")
    with open(pairs, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "a", "b"])
        for k, (x, y) in enumerate(zip(a[:, 0], b[:, 0])):
            w.writerow([k, int(x), int(y)])
    cap = min(2048, len(seeds))
    r = {"n": len(seeds), "dropped": dropped, "heart_D": a[:, 0].mean(), "heart_X": b[:, 0].mean(),
         "d": d.mean(), "ci95": [lo95, hi95], "ci975": [lo975, hi975],
         "act3_d": float((b[:, 1] - a[:, 1]).mean()), "act3_ci95": boot(b[:, 1] - a[:, 1]),
         "floor_d": float((b[:, 2] - a[:, 2]).mean()), "floor_ci95": boot(b[:, 2] - a[:, 2]),
         "cpu_ratio": b[:, 3].mean() / a[:, 3].mean(),
         "sprt": gate(pairs, "gainer", cap, 0.025), "sprt_nonregression": gate(pairs, "nonregression", cap, 0.05)}
    sv = r["sprt"].get("verdict")
    if len(dropped) > MAX_DROPPED:
        v = "INCOMPLETE"
    elif sv == "PASS":
        v = "GO"
    elif sv == "NOT_SHOWN":
        v = "NOT_SHOWN"
    elif sv == "CAP":
        v = "GO" if lo975 > 0 else ("STOP" if d.mean() <= 0 else "INCONCLUSIVE")
    else:
        v = "PARTIAL"
    r["verdict"] = v
    r["nonregression_reading"] = "NOT_WORSE" if lo95 > -0.015 else "NOT_SHOWN"
    return r


def main(root, out):
    games, bad, aborts, mismatch = load(root)
    outdir = os.path.dirname(out) or "."
    res = {"bad": bad, "aborts": aborts, "env_mismatch": mismatch, "contrasts": {arm: contrast(games, arm, outdir) for arm in ("P1", "PF")}}
    both = [s for s in SEEDS if all((arm, s) in games for arm in ("P1", "PF"))]
    x = np.array([games[("P1", s)][0] - games[("PF", s)][0] for s in both], float)
    res["P1_minus_PF"] = {"n": len(both), "d": float(x.mean()) if len(x) else None,
                          "ci95": boot(x) if len(x) else [None, None]}
    per_arm = {}
    for arm in ARMS:
        g = np.array([v for (a_, s), v in games.items() if a_ == arm and s in SEEDS], float)
        if not len(g):
            continue
        per_arm[arm] = {"games": len(g), "heart": float(g[:, 0].mean()), "act3": float(g[:, 1].mean()),
                        "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean()),
                        "long_games": int((g[:, 4] > 300).sum()), "max_wall": int(g[:, 4].max())}
    res["per_arm"] = per_arm
    vp, vf = res["contrasts"]["P1"]["verdict"], res["contrasts"]["PF"]["verdict"]
    if vp == "GO" and vf == "GO":
        cand = "P1" if (res["P1_minus_PF"]["ci95"][0] or 0) > 0 else "PF"
    else:
        cand = "P1" if vp == "GO" else ("PF" if vf == "GO" else None)
    res["candidate"] = cand
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(bad)} (env mismatch {len(mismatch)}) aborts {len(aborts)}")
    for arm, r in res["contrasts"].items():
        if not r["n"]:
            print(f"{arm} - D: no analysable seed -> {r['verdict']}")
            continue
        print(f"{arm} - D: n {r['n']} dropped {len(r['dropped'])}  heart D {100 * r['heart_D']:.2f}% "
              f"{arm} {100 * r['heart_X']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  floor d {r['floor_d']:+.2f}  cpu ratio {r['cpu_ratio']:.3f}  "
              f"verdict {r['verdict']} (sprt {r['sprt'].get('verdict')}), nonregression reading "
              f"{r['nonregression_reading']} (sprt {r['sprt_nonregression'].get('verdict')})")
    p = res["P1_minus_PF"]
    if p["n"]:
        print(f"P1 - PF: n {p['n']} d {100 * p['d']:+.2f} [{100 * p['ci95'][0]:+.2f}, {100 * p['ci95'][1]:+.2f}] pp")
    print("candidate", cand)
    return res


def self_test():
    """Synthetic campaign: drops, an abort and a wrong .env -> verdicts; 21 dropped in one contrast -> INCOMPLETE."""
    import random
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    root = os.path.join(t, "units")
    drop = {111820500: "P1", 111821000: "PF"}
    rate = {"D": 0.24, "P1": 0.30, "PF": 0.24}
    for s in SEEDS:
        dd = os.path.join(root, str(s))
        os.makedirs(dd)
        for arm in ARMS:
            k = int(rng.random() < rate[arm])
            rc = 1 if drop.get(s) == arm else 0
            ab = int(s == 111820700 and arm == "PF")
            k = k and not ab
            Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort={ab}")
            env_arm = "P1" if (s == 111820600 and arm == "PF") else arm
            Path(dd, f"{arm}-{s}.env").write_text("STS_FAIR=1\n" + "".join(
                f"{k}={v}\n" for k, v in zip(LEAF_KEYS, LEAF_ENV[env_arm]) if v is not None))
            Path(dd, f"{arm}-{s}.log").write_text(
                f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  x cpu_sec/run= 20.0\n")
    r = main(root, os.path.join(t, "r.json"))
    assert r["contrasts"]["P1"]["dropped"] == [111820500], r["contrasts"]["P1"]["dropped"]
    assert r["contrasts"]["PF"]["dropped"] == [111820600, 111821000], r["contrasts"]["PF"]["dropped"]
    assert r["env_mismatch"] == ["PF-111820600"], r["env_mismatch"]
    assert r["aborts"] == ["PF-111820700"], r["aborts"]
    assert r["P1_minus_PF"]["n"] == 2045
    for arm in ("P1", "PF"):
        c = r["contrasts"][arm]
        assert c["sprt"]["pairs"]["gap_after"] is None and c["verdict"] in ("GO", "NOT_SHOWN", "STOP", "INCONCLUSIVE")
    assert r["contrasts"]["P1"]["verdict"] == "GO", r["contrasts"]["P1"]["verdict"]   # +6 pp synthetic gain
    assert r["candidate"] in ("P1", "PF")
    for s in range(111821100, 111821120):
        Path(root, str(s), f"D-{s}.done").write_text(f"tag=D-{s} rc=1 start=x wall=1 abort=0")
    r = main(root, os.path.join(t, "r2.json"))
    assert r["contrasts"]["P1"]["verdict"] == "INCOMPLETE", r["contrasts"]["P1"]["verdict"]
    assert r["contrasts"]["PF"]["verdict"] == "INCOMPLETE", r["contrasts"]["PF"]["verdict"]
    assert r["candidate"] is None
    empty = os.path.join(t, "empty")
    os.makedirs(empty)
    r = main(empty, os.path.join(t, "r3.json"))
    assert r["contrasts"]["P1"]["verdict"] == r["contrasts"]["PF"]["verdict"] == "INCOMPLETE" and r["candidate"] is None
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:3])
