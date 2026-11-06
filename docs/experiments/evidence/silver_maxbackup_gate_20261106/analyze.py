#!/usr/bin/env python3
"""STS_SILVER_MAX_BACKUP=4 gate (PREREG.md): arms D (default) and M (max backup 4), net-0220 policy alone, flat Silver
1,000, on new seeds 111760000-111762047, both arms played on every seed.

    python3 analyze.py OUT_ROOT result.json
    python3 analyze.py --self-test

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log,err} from run_unit.sh (verify_campaign.py --extract
DIR writes DIR/out/units/<seed>/).
1. Primary: d = Heart kill M - D per seed. A seed counts if both games finished rc 0 with all log checks (a combat
   abort is a counted loss, listed); dropped seeds are listed, never imputed; > 20 dropped = INCOMPLETE. The gate
   (tools/sprt_gate.py gainer, look 64, cap = number of analysed seeds, at most 2,048) gets the seeds gap-free
   (key = rank in ascending seed order). PASS = GO; NOT_SHOWN = NOT_SHOWN; at CAP the 95% seed bootstrap of the mean d
   decides (10,000 resamples, seed 20261106): GO if lo > 0, STOP if mean <= 0, else INCONCLUSIVE.
2. Secondary reading (pre-registered, not a gate): the same pairs through sprt_gate nonregression (d0 = -1.5 pp) and
   the bootstrap: NOT_WORSE if lo > -1.5 pp.
3. Descriptive: Act-3 clears, mean floor, cpu_sec/run per arm and M/D ratio, combat aborts, games with wall > 300 s.
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
SEEDS = range(111760000, 111762048)
MAX_DROPPED = len(SEEDS) // 100
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)


def load(root):
    games, bad, aborts = {}, [], []
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        log = done.with_suffix(".log").read_text()
        m = WIN.search(log) if d["rc"] == "0" else None
        if not m:
            bad.append(d["tag"])
            continue
        key = (arm, int(seed))
        if key in games:
            raise ValueError(f"{d['tag']} twice")
        if d.get("abort") == "1":
            aborts.append(d["tag"])
        floor = float(m.group(2))
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)), int(d["wall"]))
    return games, sorted(bad), sorted(aborts)


def boot(x, seed=20261106):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def gate(pairs, variant, cap):
    g = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs, "--variant", variant,
                        "--look", "64", "--cap", str(cap)], capture_output=True, text=True)
    if g.returncode != 0:
        raise RuntimeError(f"sprt_gate failed: {g.stderr.strip()}")
    return json.loads(g.stdout)


def main(root, out):
    games, bad, aborts = load(root)
    seeds = [s for s in SEEDS if ("D", s) in games and ("M", s) in games]
    dropped = [s for s in SEEDS if s not in set(seeds)]
    a = np.array([games[("D", s)][:5] for s in seeds], float)
    b = np.array([games[("M", s)][:5] for s in seeds], float)
    d = b[:, 0] - a[:, 0]
    lo, hi = boot(d)
    res = {"bad": bad, "aborts": aborts, "dropped": dropped, "n": len(seeds),
           "heart_D": a[:, 0].mean(), "heart_M": b[:, 0].mean(), "D": d.mean(), "lo": lo, "hi": hi,
           "act3_D": float((b[:, 1] - a[:, 1]).mean()), "act3_ci": boot(b[:, 1] - a[:, 1]),
           "floor_D": float((b[:, 2] - a[:, 2]).mean()), "floor_ci": boot(b[:, 2] - a[:, 2]),
           "cpu_D": a[:, 3].mean(), "cpu_M": b[:, 3].mean(), "cpu_ratio": b[:, 3].mean() / a[:, 3].mean(),
           "long_games": {"D": int((a[:, 4] > 300).sum()), "M": int((b[:, 4] > 300).sum())},
           "max_wall": {"D": int(a[:, 4].max()), "M": int(b[:, 4].max())}}
    pairs = os.path.join(os.path.dirname(out) or ".", "pairs.csv")
    with open(pairs, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["key", "a", "b"])
        for k, (x, y) in enumerate(zip(a[:, 0], b[:, 0])):
            w.writerow([k, int(x), int(y)])
    cap = min(2048, len(seeds))
    res["sprt"] = gate(pairs, "gainer", cap)
    res["sprt_nonregression"] = gate(pairs, "nonregression", cap)
    sv = res["sprt"].get("verdict")
    if len(dropped) > MAX_DROPPED:
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
    res["nonregression_reading"] = "NOT_WORSE" if lo > -0.015 else "NOT_SHOWN"
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"n {len(seeds)} dropped {len(dropped)} bad {len(bad)} aborts {len(aborts)}")
    print(f"heart D {100 * res['heart_D']:.2f}% M {100 * res['heart_M']:.2f}%  d {100 * d.mean():+.2f} "
          f"[{100 * lo:+.2f}, {100 * hi:+.2f}] pp  floor d {res['floor_D']:+.2f}  cpu M/D {res['cpu_ratio']:.3f}")
    print("sprt", {k: x for k, x in res["sprt"].items() if k != "looks"})
    print("verdict", v, "| nonregression reading", res["nonregression_reading"])
    return res


def self_test():
    """Synthetic campaign: two dropped seeds, one abort -> a verdict; 21 dropped -> INCOMPLETE."""
    import random
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    root = os.path.join(t, "units")
    drop = {111760500, 111761000}
    for s in SEEDS:
        dd = os.path.join(root, str(s))
        os.makedirs(dd)
        for arm in ("D", "M"):
            k = int(rng.random() < (0.24 if arm == "D" else 0.27))
            rc = 1 if (s in drop and arm == "M") else 0
            ab = int(s == 111760700 and arm == "M")
            k = k and not ab
            Path(dd, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort={ab}")
            Path(dd, f"{arm}-{s}.log").write_text(
                f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  x cpu_sec/run= 20.0\n")
    r = main(root, os.path.join(t, "r.json"))
    assert r["dropped"] == sorted(drop), r["dropped"]
    assert r["aborts"] == ["M-111760700"], r["aborts"]
    assert r["sprt"]["pairs"]["gap_after"] is None and r["verdict"] in ("GO", "NOT_SHOWN", "STOP", "INCONCLUSIVE")
    for s in range(111761100, 111761119):
        Path(root, str(s), f"D-{s}.done").write_text(f"tag=D-{s} rc=1 start=x wall=1 abort=0")
    r = main(root, os.path.join(t, "r2.json"))
    assert r["verdict"] == "INCOMPLETE", r["verdict"]
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:3])
