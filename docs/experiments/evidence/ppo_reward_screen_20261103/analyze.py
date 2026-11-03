"""Reward screen 2 analysis, as pre-registered (PREREG.md).

    python3 analyze.py RUN_DIR result.json              final: last third, iterations 40-59
    python3 analyze.py RUN_DIR futility.json --futility interim at iteration 30: iterations 20-29

RUN_DIR/<ARM>/games-NNNN.csv (arm,iteration,seed,heart_kill,floor,net) as the learner writes them, and
RUN_DIR/<ARM>/stalled_seeds.txt (seeds of stalled games, any format; 9-digit numbers are read).
Control C = (BASE + BASE_S1) / 2 per seed. D = arm - C, 95% seed bootstrap (10,000 resamples, seed 20261103).
PROMISING needs D > sqrt(3)/2 * |BASE_S1 - BASE|: with run noise sd s per run, |BASE_S1 - BASE| estimates sqrt(2) s
and D's run noise is sqrt(1 + 1/2) s, so the bar is one run-noise sd of D (screen 1's bar was one sd of its D).
The final analysis reads RUN_DIR/futility.json (written by the futility look) and reports its stopped arms as FUTILE.
"""
import csv
import glob
import json
import os
import re
import sys

import numpy as np

NOISE_FACTOR = 3 ** 0.5 / 2

SEED_BASE, GAMES = 111470000, 512
FINAL = (40, 60)       # iterations of the primary window
INTERIM = (20, 30)     # iterations of the futility look
ARMS = ("BASE", "BASE_S1", "PBRS_FLOOR", "PBRS_STATE", "CRIT_PRE", "ACT_BONUS")


def window(its):
    return SEED_BASE + GAMES * its[0], SEED_BASE + GAMES * its[1] - 1


def load(run, arm, lo, hi):
    d = {}
    for f in sorted(glob.glob(os.path.join(run, arm, "games-*.csv"))):
        for r in csv.DictReader(open(f)):
            s = int(r["seed"])
            if lo <= s <= hi:
                if s in d:
                    raise ValueError(f"{arm}: seed {s} twice")
                d[s] = int(r["heart_kill"])
    return d


def stalls(run, arm):
    p = os.path.join(run, arm, "stalled_seeds.txt")
    return sorted(int(x) for x in re.findall(r"\d{9}", open(p).read())) if os.path.exists(p) else []


def boot(dd, seed):
    i = np.random.default_rng(seed).integers(0, len(dd), size=(10000, len(dd)))
    bs = dd[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def main(run, out, futility=False):
    its = INTERIM if futility else FINAL
    lo, hi = window(its)
    arms = [a for a in ARMS if os.path.isdir(os.path.join(run, a))]
    data = {a: load(run, a, lo, hi) for a in arms}
    seeds = sorted(data["BASE"])
    expect = GAMES * (its[1] - its[0])
    complete = {a: sorted(data[a]) == seeds and len(seeds) == expect for a in arms}
    if not (complete["BASE"] and complete["BASE_S1"]):
        sys.exit("BASE or BASE_S1 incomplete in the window: no verdicts")
    B = np.array([data["BASE"][s] for s in seeds], float)
    S1 = np.array([data["BASE_S1"][s] for s in seeds], float)
    C = (B + S1) / 2
    noise = abs(S1.mean() - B.mean())
    stall_all = {a: stalls(run, a) for a in arms}
    drop = {s for a in arms for s in stall_all[a] if lo <= s <= hi}
    keep = np.array([s not in drop for s in seeds])
    futile = set()
    fpath = os.path.join(run, "futility.json")
    if not futility and os.path.exists(fpath):
        futile = {r["arm"] for r in json.load(open(fpath))["arms"] if r.get("verdict") == "FUTILE"}

    def verdict_of(d, ci):
        if futility:
            return "FUTILE" if ci[1] < 0 else "CONTINUE"
        if ci[0] > 0 and d > NOISE_FACTOR * noise:
            return "PROMISING"
        if ci[1] < 0:
            return "WORSE"
        return "NOT_SHOWN"
    rows = []
    for a in ARMS:
        if a in futile:
            rows.append({"arm": a, "complete": False, "verdict": "FUTILE"})
            continue
        if a not in arms or a in ("BASE", "BASE_S1") or not complete[a]:
            rows.append({"arm": a, "complete": complete.get(a, False),
                         **({} if a in ("BASE", "BASE_S1") else {"verdict": "INCOMPLETE"})})
            continue
        x = np.array([data[a][s] for s in seeds], float)
        dd = x - C
        ci = boot(dd, 20261103)
        ci_s = boot(dd[keep], 20261104)
        rows.append({"arm": a, "complete": True, "rate": x.mean(), "D": dd.mean(), "lo": ci[0], "hi": ci[1],
                     "verdict": verdict_of(dd.mean(), ci),
                     "D_sens": dd[keep].mean(), "lo_sens": ci_s[0], "hi_sens": ci_s[1],
                     "verdict_sens": verdict_of(dd[keep].mean(), ci_s), "stalls": len(stall_all[a]),
                     "stalls_window": sum(1 for s in stall_all[a] if lo <= s <= hi)})
    res = {"window_iterations": list(its), "seeds": [lo, hi], "n": len(seeds), "base": B.mean(),
           "base_s1": S1.mean(), "control": C.mean(), "noise_abs_s1_minus_base": noise,
           "promising_bar": NOISE_FACTOR * noise,
           "stall_seeds_window": sorted(drop), "arms": rows}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"window it {its[0]}-{its[1] - 1}, n {len(seeds)}: BASE {100 * B.mean():.2f}% BASE_S1 {100 * S1.mean():.2f}% "
          f"noise {100 * noise:.2f} pp")
    for r in rows:
        if "D" in r:
            print(f"{r['arm']:11s} {100 * r['rate']:6.2f}%  D {100 * r['D']:+.2f} [{100 * r['lo']:+.2f}, "
                  f"{100 * r['hi']:+.2f}]  {r['verdict']}  sens {100 * r['D_sens']:+.2f} [{100 * r['lo_sens']:+.2f}, "
                  f"{100 * r['hi_sens']:+.2f}] {r['verdict_sens']}")
        else:
            print(f"{r['arm']:11s} {r.get('verdict', 'control')}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--futility" in sys.argv[3:])
