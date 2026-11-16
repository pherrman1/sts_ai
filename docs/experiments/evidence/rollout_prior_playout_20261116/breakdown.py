#!/usr/bin/env python3
"""Descriptive breakdown behind RESULT.md's "Where GP loses" (not pre-registered, not a gate).

usage: python3 -I breakdown.py NEW_UNITS REF_UNITS OUT.json
  NEW_UNITS / REF_UNITS: as for analyze.py (this campaign's extracted out/units; §775's units).

GP against §775's G16 on seeds where both finished (analyze.py's load and log checks):
1. Deaths by section of the final floor, sections as gumbel_tuning_20261109/wholerun/breakdown.py (hazard = deaths
   among runs reaching the section, arm - G16, seed bootstrap, 4,000 resamples, seed 20261116, 95%).
2. Act 4 by floor of death (Shield and Spear vs the Heart, from the final floor), and Heart kills on the seeds where
   both arms, only G16 or only GP reached Act 4 (final floor >= 52).
3. Heart kill difference on the two halves of the seed range (the budget curve's 512 seeds and the other 512).
"""
import collections, importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("s3_analyze", HERE / "analyze.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

REPS, SEED = 4000, 20261116
SECTIONS = [("a1", "act 1, floors 1-15"), ("b16", "act-1 boss (16)"), ("a2", "act 2, floors 17-32"),
            ("b33", "act-2 boss (33)"), ("a3", "act 3, floors 34-49"), ("b50", "act-3 boss 1 (50)"),
            ("b51", "act-3 boss 2 (51)"), ("a4", "act 4 (52-56)")]
FIRST, LAST, HALF = 111378256, 111379279, 111378767


def section(floor, won):
    f = int(floor)
    if won:
        return "win"
    return ("a1" if f <= 15 else "b16" if f == 16 else "a2" if f <= 32 else "b33" if f == 33 else "a3" if f <= 49
            else "b50" if f == 50 else "b51" if f == 51 else "a4")


def main(new_units, ref_units, out):
    new = A.load(new_units, "new")[0]
    ref = A.load(ref_units, "ref")[0]
    seeds = [s for s in range(FIRST, LAST + 1) if ("GP", s) in new and ("G16", s) in ref]
    g = {"GP": [new[("GP", s)] for s in seeds], "G16": [ref[("G16", s)] for s in seeds]}
    sec = {a: np.array([section(x[2], x[0]) for x in g[a]]) for a in g}
    win = {a: sec[a] == "win" for a in sec}
    floor = {a: np.array([int(x[2]) for x in g[a]]) for a in g}
    reach = {a: floor[a] >= 52 for a in g}

    def hazard(arm, idx):
        x, alive, res = sec[arm][idx], len(idx), {}
        for k, _ in SECTIONS:
            d = int((x == k).sum())
            res[k] = (d, alive)
            alive -= d
        return res

    every = np.arange(len(seeds))
    base = {a: hazard(a, every) for a in sec}
    rng, boot = np.random.default_rng(SEED), collections.defaultdict(list)
    for _ in range(REPS):
        i = rng.integers(0, len(seeds), len(seeds))
        h1, h2 = hazard("GP", i), hazard("G16", i)
        for k, _ in SECTIONS:
            boot[k].append(h1[k][0] / h1[k][1] - h2[k][0] / h2[k][1])
    rows = []
    for k, label in SECTIONS:
        c, b = base["GP"][k], base["G16"][k]
        lo, hi = np.percentile(boot[k], [2.5, 97.5])
        rows.append(dict(section=k, label=label, arm_deaths=c[0], arm_reached=c[1], g16_deaths=b[0], g16_reached=b[1],
                         hazard_d_pp=100 * (c[0] / c[1] - b[0] / b[1]), ci95_pp=[100 * lo, 100 * hi],
                         only_g16_kills_arm_died_here=int(((sec["GP"] == k) & win["G16"]).sum()),
                         only_arm_kills_g16_died_here=int(((sec["G16"] == k) & win["GP"]).sum())))
    act4_floor = {a: {str(f): int(((floor[a] == f) & ~win[a]).sum()) for f in range(52, 58)} for a in g}
    groups = {"both": reach["GP"] & reach["G16"], "only_G16": reach["G16"] & ~reach["GP"],
              "only_GP": reach["GP"] & ~reach["G16"]}
    act4_groups = {k: dict(seeds=int(m.sum()), G16_kills=int((win["G16"] & m).sum()),
                           GP_kills=int((win["GP"] & m).sum())) for k, m in groups.items()}
    halves = {}
    s = np.array(seeds)
    for name, m in (("first512", s <= HALF), ("second512", s > HALF)):
        d = win["GP"][m].astype(float) - win["G16"][m].astype(float)
        lo, hi = A.boot(d)
        halves[name] = dict(seeds=int(m.sum()), G16=float(win["G16"][m].mean()), GP=float(win["GP"][m].mean()),
                            d_pp=100 * float(d.mean()), ci95_pp=[100 * lo, 100 * hi])
    res = dict(seeds=len(seeds), sections=rows, act4_deaths_by_final_floor=act4_floor, act4_groups=act4_groups,
               halves=halves, both_kill=int((win["GP"] & win["G16"]).sum()),
               neither=int((~win["GP"] & ~win["G16"]).sum()),
               only_arm=int((win["GP"] & ~win["G16"]).sum()), only_g16=int((~win["GP"] & win["G16"]).sum()))
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"seeds {res['seeds']}: both {res['both_kill']}, neither {res['neither']}, only GP {res['only_arm']}, "
          f"only G16 {res['only_g16']}")
    for r in rows:
        print(f"{r['label']:22s} {r['arm_deaths']:4d}/{r['arm_reached']:4d}  {r['g16_deaths']:4d}/{r['g16_reached']:4d}"
              f"  {r['hazard_d_pp']:+.1f} [{r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}]"
              f"  lostHere {r['only_g16_kills_arm_died_here']} wonHere {r['only_arm_kills_g16_died_here']}")
    print("act-4 deaths by final floor:", act4_floor)
    print("act-4 groups:", act4_groups)
    print("halves:", json.dumps(halves))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
