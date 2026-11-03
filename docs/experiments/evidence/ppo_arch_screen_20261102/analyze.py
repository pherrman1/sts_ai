"""Architecture screen analysis (design B), as pre-registered (PREREG.md "Binding under B", cost rule, critic
secondary).

    python3 analyze.py ARCH_RUN SCREEN2_RUN result.json [--critic CRITIC_DIR]

ARCH_RUN/<ARM> and SCREEN2_RUN/{BASE,BASE_S1} are serve learner directories (or copies): games-NNNN.csv
(arm,iteration,seed,heart_kill,floor,net) as the learner writes them, stalled_seeds.txt (9-digit numbers are read)
and loop.json (per-iteration stats; "actor_s" = the slowest part's actor seconds, "seed_first" its first seed).

Primary: Heart-kill rate over iterations 40-59 (seeds 111490480-111500719), D = arm - BASE paired by seed, 95% seed
bootstrap (10,000 resamples, seed 20261103). Noise floor = |BASE_S1 - BASE| on the same window. PROMISING if the CI
lower bound > 0 and D > noise; WORSE if the CI upper bound < 0; else NOT_SHOWN. An arm missing a window seed is
INCOMPLETE. Stalled games count as losses (as played); the sensitivity D drops every seed stalled in any arm or
control (bootstrap seed 20261104).

Cost rule: per iteration of the window, arm actor_s / BASE actor_s (both are 128-game parts); reported as median
and quartiles. adoption_cost_ok = median ratio <= 1.3. The native ms/record of each start net is measured before
launch and lives in screen.manifest, not here.

Critic secondary (--critic): CRITIC_DIR/<ARM>/gates.json for BASE, CRITIC_SEP, AUX and VAL_SPARSE, written by
heart1_value_leaf_teacher_20261102/gates.py on `ppo_train.py score <final state.pt>` values. Group "postfight",
V = the raw value (gates.py mode "raw"): the PPO critic is trained by MSE on a 0/1 Heart return, so its output is
already on the probability scale (amendment after review K; heart1's §747 check used sigmoid). CRITIC_BETTER if T1 (share of states where -3 HP lowers V) is >= 5 pp
above BASE's and T5 (median |1-HP price - 1| in secant units) is below BASE's; else NOT_BETTER. It does not change
the primary verdict.
"""
import csv
import glob
import json
import os
import re
import sys

import numpy as np

SEED_BASE, GAMES = 111470000, 512
WINDOW = (40, 60)
ARMS = ("IN_DECK", "DEPTH6", "CRITIC_SEP", "AUX", "VAL_SPARSE")
CRITIC_ARMS = ("CRITIC_SEP", "AUX", "VAL_SPARSE")
COST_BAR = 1.3
CRITIC_MODE = "raw"
T1_KEY, T5_KEY = "T1_minus3HpLowersV>=0.95", "T5_median|hp1-1|<=1/3"


def window_seeds():
    return SEED_BASE + GAMES * WINDOW[0], SEED_BASE + GAMES * WINDOW[1] - 1


def load(d, lo, hi):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "games-*.csv"))):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                s = int(r["seed"])
                if lo <= s <= hi:
                    if s in out:
                        raise ValueError(f"{d}: seed {s} twice")
                    out[s] = int(r["heart_kill"])
    return out


def stalls(d):
    p = os.path.join(d, "stalled_seeds.txt")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return sorted(int(x) for x in re.findall(r"\d{9}", f.read()))


def actor_seconds(d):
    """iteration -> actor_s from loop.json (records without seed_first, e.g. lost stats, are skipped)."""
    p = os.path.join(d, "loop.json")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        its = json.load(f)["iterations"]
    return {(r["seed_first"] - SEED_BASE) // GAMES: r["actor_s"] for r in its
            if "seed_first" in r and r.get("actor_s")}


def boot(dd, seed):
    i = np.random.default_rng(seed).integers(0, len(dd), size=(10000, len(dd)))
    bs = dd[i].mean(1)
    return float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))


def verdict_of(d, ci, noise):
    if ci[0] > 0 and d > noise:
        return "PROMISING"
    if ci[1] < 0:
        return "WORSE"
    return "NOT_SHOWN"


def cost(arm_dir, base_s):
    a = actor_seconds(arm_dir)
    r = [a[i] / base_s[i] for i in range(*WINDOW) if i in a and i in base_s]
    if not r:
        return {"iterations": 0}
    q = np.percentile(r, [25, 50, 75])
    return {"iterations": len(r), "ratio_p25": float(q[0]), "ratio_median": float(q[1]), "ratio_p75": float(q[2]),
            "adoption_cost_ok": bool(q[1] <= COST_BAR)}


def critic(cdir):
    if not cdir:
        return None
    vals = {}
    for a in ("BASE",) + CRITIC_ARMS:
        p = os.path.join(cdir, a, "gates.json")
        if os.path.exists(p):
            with open(p) as f:
                g = json.load(f)[CRITIC_MODE]["postfight"]["gates"]
            vals[a] = {"T1": g[T1_KEY][0], "T5": g[T5_KEY][0]}
    if "BASE" not in vals:
        sys.exit(f"{cdir}/BASE/gates.json missing: no critic verdicts")
    b = vals["BASE"]
    rows = [{"arm": "BASE", **b}]
    for a in CRITIC_ARMS:
        if a not in vals:
            rows.append({"arm": a, "verdict": "MISSING"})
            continue
        v = vals[a]
        better = v["T1"] - b["T1"] >= 0.05 and v["T5"] < b["T5"]
        rows.append({"arm": a, **v, "dT1": v["T1"] - b["T1"], "dT5": v["T5"] - b["T5"],
                     "verdict": "CRITIC_BETTER" if better else "NOT_BETTER"})
    return rows


def main(arch, screen2, out, cdir=None):
    lo, hi = window_seeds()
    expect = GAMES * (WINDOW[1] - WINDOW[0])
    ctrl = {a: os.path.join(screen2, a) for a in ("BASE", "BASE_S1")}
    dirs = {a: os.path.join(arch, a) for a in ARMS if os.path.isdir(os.path.join(arch, a))}
    data = {a: load(d, lo, hi) for a, d in {**ctrl, **dirs}.items()}
    seeds = list(range(lo, hi + 1))
    complete = {a: sorted(v) == seeds for a, v in data.items()}
    if len(seeds) != expect or not (complete["BASE"] and complete["BASE_S1"]):
        sys.exit("BASE or BASE_S1 incomplete in the window: no verdicts")
    B = np.array([data["BASE"][s] for s in seeds], float)
    S1 = np.array([data["BASE_S1"][s] for s in seeds], float)
    noise = abs(S1.mean() - B.mean())
    stall_all = {a: stalls(d) for a, d in {**ctrl, **dirs}.items()}
    drop = {s for v in stall_all.values() for s in v if lo <= s <= hi}
    keep = np.array([s not in drop for s in seeds])
    base_s = actor_seconds(ctrl["BASE"])
    rows = []
    for a in ARMS:
        if a not in dirs or not complete[a]:
            rows.append({"arm": a, "complete": False, "verdict": "INCOMPLETE"})
            continue
        x = np.array([data[a][s] for s in seeds], float)
        dd = x - B
        ci, ci_s = boot(dd, 20261103), boot(dd[keep], 20261104)
        rows.append({"arm": a, "complete": True, "rate": x.mean(), "D": dd.mean(), "lo": ci[0], "hi": ci[1],
                     "verdict": verdict_of(dd.mean(), ci, noise),
                     "D_sens": dd[keep].mean(), "lo_sens": ci_s[0], "hi_sens": ci_s[1],
                     "verdict_sens": verdict_of(dd[keep].mean(), ci_s, noise),
                     "stalls": len(stall_all[a]), "stalls_window": sum(1 for s in stall_all[a] if lo <= s <= hi),
                     "cost": cost(dirs[a], base_s)})
    res = {"window_iterations": list(WINDOW), "seeds": [lo, hi], "n": len(seeds), "base": B.mean(),
           "base_s1": S1.mean(), "noise_abs_s1_minus_base": noise, "stall_seeds_window": sorted(drop),
           "cost_bar": COST_BAR, "critic_mode": CRITIC_MODE, "arms": rows, "critic": critic(cdir)}
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"window it {WINDOW[0]}-{WINDOW[1] - 1}, n {len(seeds)}: BASE {100 * B.mean():.2f}% "
          f"BASE_S1 {100 * S1.mean():.2f}% noise {100 * noise:.2f} pp")
    for r in rows:
        if "D" not in r:
            print(f"{r['arm']:11s} {r['verdict']}")
            continue
        c = r["cost"]
        cs = f"cost x{c['ratio_median']:.2f} [{c['ratio_p25']:.2f}, {c['ratio_p75']:.2f}]" if c["iterations"] else "cost n/a"
        print(f"{r['arm']:11s} {100 * r['rate']:6.2f}%  D {100 * r['D']:+.2f} [{100 * r['lo']:+.2f}, "
              f"{100 * r['hi']:+.2f}]  {r['verdict']}  sens {100 * r['D_sens']:+.2f} {r['verdict_sens']}  {cs}")
    for r in res["critic"] or []:
        print(f"critic {r['arm']:11s} " + (f"T1 {r['T1']:.3f} T5 {r['T5']:.3f} {r.get('verdict', '')}"
                                           if "T1" in r else r["verdict"]))


if __name__ == "__main__":
    av = sys.argv[1:]
    cd = None
    if "--critic" in av:
        i = av.index("--critic")
        cd = av[i + 1]
        del av[i:i + 2]
    if len(av) != 3:
        sys.exit(__doc__)
    main(*av, cdir=cd)
