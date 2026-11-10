#!/usr/bin/env python3
"""Gumbel budget curve in whole runs (PREREG.md): G2, G4, G8 against combat B (B1) and G1 of the 1k test.

usage: python3 -I analyze.py UNITS_DIR UNITS_1K_DIR REF_UNITS_DIR OUT.json | --self-test
  UNITS_DIR: this campaign's extracted out/units (G2, G4, G8); UNITS_1K_DIR: the 1k test's (B1, G1);
  REF_UNITS_DIR: §775's (D, G16), read with ../gumbel_tuning_20261109/wholerun/analyze.py's loader.

A game counts if its .done has rc 0, the log has the BEST line with its seed and sims, and its .env has the arm's
values; otherwise it is a drop. Each contrast uses the seeds where both of its games count.
Primary: Gk - B1 Heart kill for k = 2, 4, 8, paired by seed, seed bootstrap (10,000 resamples, seed 20261109) at
98.33% (Bonferroni over the three): Gk_BETTER if lo > 0, Gk_WORSE if hi < 0, else NO_DIFFERENCE_SHOWN; every verdict
NOT_EVALUABLE if more than 10 of this campaign's seeds have a drop.
Secondary: 95% intervals of Gk - B1, Gk - G1, Gk - D, Gk - G16, G8 - G4, G4 - G2; per arm Heart, Act-4 reach, final
floor, CPU per run; aborts per arm; Gumbel roots and simulations per run.
"""
import importlib.util, json, re, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


K1 = module(HERE.parent / "gumbel_1k_wholerun_20261109" / "analyze.py", "g1k")
SEEDS = K1.SEEDS
NEW = {"G2": 2000, "G4": 4000, "G8": 8000}
MAX_DROPPED = 10
LEVEL = 100 - 5 / 3


def load_new(root):
    games, drops, seen = {}, [], set()
    for done in sorted(Path(root).glob("*/*.done")):
        d = dict(kv.split("=", 1) for kv in done.read_text().split())
        arm, seed = d["tag"].rsplit("-", 1)
        if arm not in NEW:
            raise ValueError(f"unknown arm in {d['tag']}")
        if (arm, int(seed)) in seen:
            raise ValueError(f"{d['tag']} twice")
        seen.add((arm, int(seed)))
        log = done.with_suffix(".log").read_text() if done.with_suffix(".log").exists() else ""
        err = done.with_suffix(".err").read_text() if done.with_suffix(".err").exists() else ""
        m = K1.WIN.search(log) if d["rc"] == "0" else None
        s = K1.SIMS_LINE.search(log)
        if (not m or not s or int(s.group(2)) != NEW[arm] or int(s.group(1)) != int(seed)
                or K1.env_of(done.with_suffix(".env")) != K1.ENV["G1"]):
            drops.append(d["tag"])
            continue
        g = K1.ROOTS.search(err)
        floor = float(m.group(2))
        games[(arm, int(seed))] = (int(float(m.group(1)) == 100.0), int(floor >= 52), floor, float(m.group(3)),
                                   int(d.get("abort", "0")), int(g.group(1)) if g else None, int(g.group(2)) if g else None)
    return games, drops, seen


def boot_level(x, level, seed=20261109):
    i = np.random.default_rng(seed).integers(0, len(x), size=(10000, len(x)))
    bs = x[i].mean(1)
    t = (100.0 - level) / 2
    return [float(np.percentile(bs, t)), float(np.percentile(bs, 100.0 - t))]


def analyze(new, drops, seen, old, ref=None):
    arm = {a: {s: v for (b, s), v in new.items() if b == a} for a in NEW}
    arm.update({a: {s: v for (b, s), v in old.items() if b == a} for a in ("B1", "G1")})
    if ref is not None:
        arm.update({a: {s: tuple(v[:4]) + (0, None, None) for (b, s), v in ref.items() if b == a} for a in ("D", "G16")})
    dropped = sorted({int(t.rsplit("-", 1)[1]) for t in drops} | {s for s in SEEDS if any((a, s) not in seen for a in NEW)})
    evaluable = len(dropped) <= MAX_DROPPED
    prim = {}
    for a in NEW:
        c = K1.contrast(arm["B1"], arm[a], list(SEEDS))
        if c.get("seeds"):
            s = [x for x in SEEDS if x in arm["B1"] and x in arm[a]]
            x = np.array([arm[a][k][0] - arm["B1"][k][0] for k in s], float) * 100
            c["heart_pp_ci_bonferroni"] = boot_level(x, LEVEL)
            lo, hi = c["heart_pp_ci_bonferroni"]
            c["verdict"] = ("NOT_EVALUABLE" if not evaluable else f"{a}_BETTER" if lo > 0 else f"{a}_WORSE" if hi < 0
                            else "NO_DIFFERENCE_SHOWN")
        else:
            c["verdict"] = "NOT_EVALUABLE"
        prim[f"{a} - B1"] = c
    sec = {}
    for a in NEW:
        for b in ("G1", "D", "G16"):
            if arm.get(b):
                sec[f"{a} - {b}"] = K1.contrast(arm[b], arm[a], list(SEEDS))
    sec["G4 - G2"] = K1.contrast(arm["G2"], arm["G4"], list(SEEDS))
    sec["G8 - G4"] = K1.contrast(arm["G4"], arm["G8"], list(SEEDS))
    per = {a: K1.per_arm(arm[a], list(SEEDS)) for a in arm}
    mean = lambda xs: float(np.mean(xs)) if xs else None
    gum = {a: dict(roots_per_run=mean([v[5] for v in arm[a].values() if v[5]]),
                   sims_per_run=mean([v[6] for v in arm[a].values() if v[6]]))
           for a in list(NEW) + ["G1"] if arm.get(a)}
    return dict(dropped_seeds=dropped, drops=sorted(drops), evaluable=evaluable, primary=prim, secondary=sec,
                per_arm=per, gumbel=gum)


def main(units, units_1k, ref_units, out):
    new, drops, seen = load_new(units)
    old, old_drops, _ = K1.load(units_1k)
    W = module(HERE.parent / "gumbel_tuning_20261109" / "wholerun" / "analyze.py", "wr")
    ref = W.load(ref_units, "ref")[0]
    res = analyze(new, drops, seen, old, ref)
    res["drops_1k"] = old_drops
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"dropped seeds {len(res['dropped_seeds'])}, evaluable {res['evaluable']}")
    for k, c in res["primary"].items():
        if c.get("seeds"):
            print(f"  {k}: {c['heart_pp']['mean']:+.2f} pp 95% [{c['heart_pp']['ci95'][0]:+.2f}, {c['heart_pp']['ci95'][1]:+.2f}]"
                  f" 98.3% [{c['heart_pp_ci_bonferroni'][0]:+.2f}, {c['heart_pp_ci_bonferroni'][1]:+.2f}] -> {c['verdict']}"
                  f" (seeds {c['seeds']}, cpu x{c['cpu_ratio']:.2f})")
    for a, v in res["per_arm"].items():
        if v.get("games"):
            print(f"  {a}: Heart {100 * v['heart']:.2f}%  Act4 {100 * v['act4']:.2f}%  floor {v['floor']:.2f}  "
                  f"cpu/run {v['cpu_per_run']:.1f} s  games {v['games']}")
    for k, v in res["secondary"].items():
        if v.get("seeds"):
            print(f"  {k}: {v['heart_pp']['mean']:+.2f} pp [{v['heart_pp']['ci95'][0]:+.2f}, {v['heart_pp']['ci95'][1]:+.2f}]"
                  f" cpu x{v['cpu_ratio']:.2f}")


def self_test():
    rng = np.random.default_rng(2)
    new, old, seen = {}, {}, set()
    for s in SEEDS:
        for a, p in (("B1", 0.2), ("G1", 0.2)):
            w = int(rng.random() < p)
            old[(a, s)] = (w, w, 40.0, 20.0, 0, None, None)
        for a, p in (("G2", 0.21), ("G4", 0.3), ("G8", 0.45)):
            w = int(rng.random() < p)
            new[(a, s)] = (w, w, 40.0, 40.0, 0, 400, 800000)
            seen.add((a, s))
    r = analyze(new, [], seen, old)
    assert r["primary"]["G8 - B1"]["verdict"] == "G8_BETTER", r["primary"]["G8 - B1"]
    assert r["primary"]["G2 - B1"]["verdict"] == "NO_DIFFERENCE_SHOWN", r["primary"]["G2 - B1"]
    lo95 = r["primary"]["G8 - B1"]["heart_pp"]["ci95"][0]
    assert r["primary"]["G8 - B1"]["heart_pp_ci_bonferroni"][0] < lo95
    r = analyze(new, [f"G4-{s}" for s in range(111378400, 111378411)], seen, old)
    assert all(c["verdict"] == "NOT_EVALUABLE" for c in r["primary"].values())
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 5:
        main(*sys.argv[1:])
    else:
        sys.exit(__doc__)
