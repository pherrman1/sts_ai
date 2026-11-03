#!/usr/bin/env python3
"""G1: CRIT_PRE's net-0060 (GC) vs heart1 (GH), policy alone (PREREG.md). Frozen before any campaign game ran.

    python3 analyze.py OUT_ROOT result.json [pairs.csv]

OUT_ROOT holds one directory per seed with ARM-SEED.{done,log} from run_unit.sh (the unpacked worker tars).
A seed counts only if both of its games finished rc 0 (after the lead's one local rerun of each failed unit);
dropped seeds are listed in result.json, never imputed. More than 1% dropped (> 20 seeds) = INCOMPLETE, no verdict.
The gate gets the analysed seeds gap-free (key = rank in ascending seed order), so a dropped seed cannot stall it.
Primary: the standard sequential gate (tools/sprt_gate.py, variant gainer, look 64, cap 2,048) on d = kill GC - kill GH
in ascending seed order. If it ends at CAP, the fixed-sample reading decides: 95% seed bootstrap of the mean d
(10,000 resamples, seed 20261103). Secondary: Act-3 clears and mean floor, paired the same way.
"""
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+).*?cpu_sec/run=\s*([\d.]+)", re.M)
SEEDS = range(111520000, 111522048)
REPO = Path(__file__).resolve().parents[4]
MAX_DROPPED = len(SEEDS) // 100   # 20 seeds = 1%


def load(root):
    games, bad = {}, []
    for done in Path(root).glob("*/*.done"):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        m = WIN.search(done.with_suffix(".log").read_text()) if d["rc"] == "0" else None
        if not m:
            bad.append(d["tag"])
            continue
        floor = float(m.group(2))
        key = (arm, int(seed))
        if key in games:
            raise ValueError(f"{d['tag']} twice")
        games[key] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)))
    return games, sorted(bad)


def boot(x, seed=20261103):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main(root, out, pairs_path=None):
    games, bad = load(root)
    seeds = [s for s in SEEDS if ("GH", s) in games and ("GC", s) in games]
    missing = [s for s in SEEDS if s not in set(seeds)]
    h = np.array([games[("GH", s)] for s in seeds], float)
    c = np.array([games[("GC", s)] for s in seeds], float)
    pairs_path = pairs_path or os.path.join(os.path.dirname(out) or ".", "pairs.csv")
    with open(pairs_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "a", "b"])
        for k, (a, b) in enumerate(zip(h[:, 0], c[:, 0])):
            w.writerow([k, int(a), int(b)])
    gate = subprocess.run([sys.executable, str(REPO / "tools" / "sprt_gate.py"), pairs_path, "--variant", "gainer",
                           "--look", "64", "--cap", "2048"], capture_output=True, text=True)
    if gate.returncode != 0:
        raise RuntimeError(f"sprt_gate failed: {gate.stderr.strip()}")
    d = c[:, 0] - h[:, 0]
    lo, hi = boot(d)
    res = {"n": len(seeds), "missing": missing, "bad": bad, "heart_gh": h[:, 0].mean(), "heart_gc": c[:, 0].mean(),
           "D": d.mean(), "lo": lo, "hi": hi,
           "act3_D": float((c[:, 1] - h[:, 1]).mean()), "act3_ci": boot(c[:, 1] - h[:, 1]),
           "floor_D": float((c[:, 2] - h[:, 2]).mean()), "floor_ci": boot(c[:, 2] - h[:, 2]),
           "cpu_gh": h[:, 3].mean(), "cpu_gc": c[:, 3].mean(),
           "sprt": json.loads(gate.stdout)}
    sv = res["sprt"].get("verdict")
    if len(missing) > MAX_DROPPED:
        res["verdict"] = "INCOMPLETE"
    elif sv == "PASS":
        res["verdict"] = "GO"
    elif sv == "NOT_SHOWN":
        res["verdict"] = "NOT_SHOWN"
    elif sv == "CAP":
        res["verdict"] = "GO" if lo > 0 else ("STOP" if d.mean() <= 0 else "INCONCLUSIVE")
    else:
        res["verdict"] = "PARTIAL"
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"n {len(seeds)} (missing {len(missing)}, bad {len(bad)}): heart1 {100 * res['heart_gh']:.2f}% "
          f"CRIT_PRE {100 * res['heart_gc']:.2f}%  D {100 * res['D']:+.2f} [{100 * lo:+.2f}, {100 * hi:+.2f}] pp")
    print(f"act3 D {100 * res['act3_D']:+.2f} pp, floor D {res['floor_D']:+.2f}, cpu {res['cpu_gh']:.1f} / {res['cpu_gc']:.1f} s")
    print("sprt", {k: v for k, v in res["sprt"].items() if k != "looks"})
    print("verdict", res["verdict"])


def self_test():
    """Synthetic campaign with dropped seeds in the middle: the gate still sees a gap-free run and gives a verdict."""
    import random
    import tempfile
    t = tempfile.mkdtemp()
    rng = random.Random(1)
    drop = {111520500, 111521000}
    for s in SEEDS:
        d = os.path.join(t, str(s))
        os.makedirs(d)
        for arm, p in (("GH", 0.09), ("GC", 0.12)):
            k = rng.random() < p
            rc = 1 if (s in drop and arm == "GC") else 0
            Path(d, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=1")
            Path(d, f"{arm}-{s}.log").write_text(
                f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  x cpu_sec/run= 20.0\n")
    main(t, os.path.join(t, "r.json"))
    r = json.load(open(os.path.join(t, "r.json")))
    assert r["missing"] == sorted(drop) and r["n"] == len(SEEDS) - 2, r["missing"]
    assert r["sprt"]["pairs"]["gap_after"] is None and r["sprt"]["verdict"] != "PARTIAL", r["sprt"]
    assert r["verdict"] in ("GO", "NOT_SHOWN", "STOP", "INCONCLUSIVE"), r["verdict"]
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:])
