#!/usr/bin/env python3
"""LONG_B evaluation (../PREREG.md, "Evaluation"): LONG_B's checkpoints vs heart1 on G1's seeds, policy alone.

    python3 analyze.py OUT_ROOT result.json
    python3 analyze.py --self-test

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log,err} from run_unit.sh (verify_campaign.py --extract
DIR writes DIR/out/units/<seed>/). The control GH is G1's (../../ppo_g1_critpre_20261103/games.csv, §752), reused:
1. Sentinel: GH was replayed on seeds 111520000-111520031. Every replayed game must equal G1's (Heart kill, final
   floor and the [heart1_ppo] line's decisions=, sentinel_expected.csv). Any mismatch or missing sentinel game =
   CONTROL_INVALID: no verdict, GH must be replayed in full (PREREG).
2. Primary: d = Heart kill L220 - GH per seed, G1's rules: a seed counts if its L220 game finished rc 0 with all log
   checks (a combat abort is a counted loss, listed); dropped seeds are listed, never imputed; > 20 dropped =
   INCOMPLETE. The gate (tools/sprt_gate.py gainer, look 64, cap 2,048) gets the seeds gap-free (key = rank in
   ascending seed order); with dropped seeds the cap is the number of analysed seeds, so the gate can still reach
   CAP (with cap 2,048 and 2,046 rows it would stay PARTIAL); at CAP the 95% seed bootstrap of the mean d decides (10,000 resamples, seed 20261105):
   GO if lo > 0, STOP if D <= 0, else INCONCLUSIVE.
3. Secondary (descriptive, no gate): L070, L120, L170 vs GH, D with the same bootstrap; Act-3 clears and mean floor
   for every checkpoint.
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
REPO = HERE.parents[4]
G1 = HERE.parents[1] / "ppo_g1_critpre_20261103" / "games.csv"
SEEDS = range(111520000, 111522048)
SENTINEL = range(111520000, 111520032)
ARMS = ("L070", "L120", "L170", "L220")
MAX_DROPPED = len(SEEDS) // 100
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)


def load(root):
    games, bad, aborts = {}, [], []
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        log = done.with_suffix(".log").read_text()
        err_p = done.with_suffix(".err")
        err = err_p.read_text() if err_p.exists() else ""
        m = WIN.search(log) if d["rc"] == "0" else None
        if not m:
            bad.append(d["tag"])
            continue
        key = (arm, int(seed))
        if key in games:
            raise ValueError(f"{d['tag']} twice")
        if d.get("abort") == "1":
            aborts.append(d["tag"])
        dec = re.search(rf"^\[heart1_ppo\] seed={seed} decisions=(\d+)", log + err, re.M)
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)),
                      int(dec.group(1)) if dec else -1)
    return games, sorted(bad), sorted(aborts)


def load_g1(path=G1):
    gh = {}
    for r in csv.DictReader(open(path)):
        if r["arm"] == "GH":
            f = float(r["floor"])
            gh[int(r["seed"])] = (int(r["heart_kill"]), int(f >= 52), f, float(r["cpu_s"]))
    return gh


def sentinel(games, expected=HERE / "sentinel_expected.csv"):
    bad = []
    for r in csv.DictReader(open(expected)):
        s = int(r["seed"])
        g = games.get(("GH", s))
        want = (int(r["heart_kill"]), float(r["floor"]), int(r["decisions"]))
        got = (g[0], g[2], g[4]) if g else None
        if got != want:
            bad.append({"seed": s, "g1": want, "replay": got})
    return bad


def boot(x, seed=20261105):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main(root, out, g1_path=G1, expected=HERE / "sentinel_expected.csv"):
    games, bad, aborts = load(root)
    gh = load_g1(g1_path)
    res = {"bad": bad, "aborts": aborts, "sentinel_mismatch": sentinel(games, expected), "arms": {}}
    for arm in ARMS:
        seeds = [s for s in SEEDS if (arm, s) in games and s in gh]
        h = np.array([gh[s] for s in seeds], float)
        c = np.array([games[(arm, s)][:4] for s in seeds], float)
        d = c[:, 0] - h[:, 0]
        lo, hi = boot(d)
        res["arms"][arm] = {"n": len(seeds), "missing": [s for s in SEEDS if s not in set(seeds)],
                            "heart_gh": h[:, 0].mean(), "heart": c[:, 0].mean(), "D": d.mean(), "lo": lo, "hi": hi,
                            "act3_D": float((c[:, 1] - h[:, 1]).mean()), "act3_ci": boot(c[:, 1] - h[:, 1]),
                            "floor_D": float((c[:, 2] - h[:, 2]).mean()), "floor_ci": boot(c[:, 2] - h[:, 2]),
                            "cpu": c[:, 3].mean()}
        if arm == "L220":
            pairs = os.path.join(os.path.dirname(out) or ".", "pairs.csv")
            with open(pairs, "w", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["key", "a", "b"])
                for k, (a, b) in enumerate(zip(h[:, 0], c[:, 0])):
                    w.writerow([k, int(a), int(b)])
            gate = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs, "--variant", "gainer",
                                   "--look", "64", "--cap", str(min(2048, len(seeds)))], capture_output=True, text=True)
            if gate.returncode != 0:
                raise RuntimeError(f"sprt_gate failed: {gate.stderr.strip()}")
            res["sprt"] = json.loads(gate.stdout)
            sv = res["sprt"].get("verdict")
            if res["sentinel_mismatch"]:
                v = "CONTROL_INVALID"
            elif len(res["arms"][arm]["missing"]) > MAX_DROPPED:
                v = "INCOMPLETE"
            elif sv == "PASS":
                v = "GO"
            elif sv == "NOT_SHOWN":
                v = "NOT_SHOWN"
            elif sv == "CAP":
                v = "GO" if lo > 0 else ("STOP" if d.mean() <= 0 else "INCONCLUSIVE")
            else:
                v = "PARTIAL"
            res["verdict"] = v
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"sentinel mismatches {len(res['sentinel_mismatch'])}, bad {len(bad)}, aborts {len(aborts)}")
    for arm, a in res["arms"].items():
        print(f"{arm}: n {a['n']} heart {100 * a['heart']:.2f}% vs GH {100 * a['heart_gh']:.2f}%  "
              f"D {100 * a['D']:+.2f} [{100 * a['lo']:+.2f}, {100 * a['hi']:+.2f}] pp  floor D {a['floor_D']:+.2f}")
    print("sprt", {k: v for k, v in res["sprt"].items() if k != "looks"})
    print("verdict", res["verdict"])
    return res


def self_test():
    """Synthetic campaign: dropped L220 seeds in the middle, one abort, sentinel exact -> a verdict;
    one sentinel game off by one decision -> CONTROL_INVALID."""
    import random
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    gh = {s: int(rng.random() < 0.15) for s in SEEDS}
    g1 = os.path.join(t, "g1.csv")
    with open(g1, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["seed", "arm", "heart_kill", "floor", "cpu_s", "rc", "abort"])
        for s in SEEDS:
            w.writerow([s, "GH", gh[s], 56.0 if gh[s] else 30.0, 20.0, 0, 0])
    exp = os.path.join(t, "exp.csv")
    with open(exp, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["seed", "heart_kill", "floor", "decisions"])
        for s in SENTINEL:
            w.writerow([s, gh[s], 56.0 if gh[s] else 30.0, 100])
    drop = {111520500, 111521000}
    root = os.path.join(t, "units")
    for s in SEEDS:
        d = os.path.join(root, str(s))
        os.makedirs(d)
        arms = list(ARMS) + (["GH"] if s in SENTINEL else [])
        for arm in arms:
            k = gh[s] if arm == "GH" else int(rng.random() < 0.17)
            rc = 1 if (s in drop and arm == "L220") else 0
            ab = int(s == 111520700 and arm == "L220")
            k = k and not ab
            Path(d, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=1 abort={ab}")
            Path(d, f"{arm}-{s}.log").write_text(
                f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  x cpu_sec/run= 20.0\n")
            Path(d, f"{arm}-{s}.err").write_text("" if ab else f"[heart1_ppo] seed={s} decisions=100 single=1\n")
    r = main(root, os.path.join(t, "r.json"), g1, exp)
    assert r["sentinel_mismatch"] == [], r["sentinel_mismatch"]
    assert r["arms"]["L220"]["missing"] == sorted(drop), r["arms"]["L220"]["missing"]
    assert r["aborts"] == ["L220-111520700"], r["aborts"]
    assert r["sprt"]["pairs"]["gap_after"] is None and r["verdict"] in ("GO", "NOT_SHOWN", "STOP", "INCONCLUSIVE")
    Path(root, "111520003", "GH-111520003.err").write_text("[heart1_ppo] seed=111520003 decisions=99 single=1\n")
    r = main(root, os.path.join(t, "r2.json"), g1, exp)
    assert r["verdict"] == "CONTROL_INVALID" and r["sentinel_mismatch"][0]["seed"] == 111520003, r["sentinel_mismatch"]
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:3])
