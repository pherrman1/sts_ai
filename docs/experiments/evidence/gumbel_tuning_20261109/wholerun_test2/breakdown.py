#!/usr/bin/env python3
"""Descriptive breakdown behind RESULT.md's "Where G16CAP loses" (not pre-registered, not a gate).

usage: python3 -I breakdown.py NEW_UNITS REF_UNITS OUT.json
  NEW_UNITS / REF_UNITS: as for ../wholerun/analyze.py (Test 1 + Test 2 extracted out/units; §775's units).

G16CAP vs §775's G16 on seeds where both finished: deaths by section of the final floor exactly as
../wholerun/breakdown.py (hazard = deaths among runs reaching the section, arm - G16, seed bootstrap, 4,000
resamples, seed 20261109, 95%).
"""
import collections, importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B = module(HERE.parent / "wholerun" / "breakdown.py", "wholerun_breakdown")
W = B.W
ARM = "G16CAP"


def whole_runs(new_units, ref_units, rng):
    new = W.load(new_units, "new")[0]
    ref = W.load(ref_units, "ref")[0]
    seeds = [s for s in W.SEEDS if (ARM, s) in new and ("G16", s) in ref]
    sec = {ARM: np.array([B.section(new[(ARM, s)][2], new[(ARM, s)][0]) for s in seeds]),
           "G16": np.array([B.section(ref[("G16", s)][2], ref[("G16", s)][0]) for s in seeds])}

    def hazard(arm, idx):
        x, alive, out = sec[arm][idx], len(idx), {}
        for k, _ in B.SECTIONS:
            d = int((x == k).sum())
            out[k] = (d, alive)
            alive -= d
        return out

    every = np.arange(len(seeds))
    base = {a: hazard(a, every) for a in sec}
    boot = collections.defaultdict(list)
    for _ in range(B.REPS):
        i = rng.integers(0, len(seeds), len(seeds))
        h1, h2 = hazard(ARM, i), hazard("G16", i)
        for k, _ in B.SECTIONS:
            boot[k].append(h1[k][0] / h1[k][1] - h2[k][0] / h2[k][1])
    win = {a: sec[a] == "win" for a in sec}
    rows = []
    for k, label in B.SECTIONS:
        c, g = base[ARM][k], base["G16"][k]
        lo, hi = np.percentile(boot[k], [2.5, 97.5])
        rows.append(dict(section=k, label=label, arm_deaths=c[0], arm_reached=c[1], g16_deaths=g[0], g16_reached=g[1],
                         hazard_d_pp=100 * (c[0] / c[1] - g[0] / g[1]), ci95_pp=[100 * lo, 100 * hi],
                         only_g16_kills_arm_died_here=int(((sec[ARM] == k) & win["G16"]).sum()),
                         only_arm_kills_g16_died_here=int(((sec["G16"] == k) & win[ARM]).sum())))
    return dict(arm=ARM, seeds=len(seeds), sections=rows,
                both_kill=int((win[ARM] & win["G16"]).sum()), neither=int((~win[ARM] & ~win["G16"]).sum()),
                only_arm=int((win[ARM] & ~win["G16"]).sum()), only_g16=int((~win[ARM] & win["G16"]).sum()))


def main(new_units, ref_units, out):
    rng = np.random.default_rng(B.SEED)
    res = dict(whole_runs=whole_runs(new_units, ref_units, rng))
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    w = res["whole_runs"]
    print(f"seeds {w['seeds']}: only {ARM} {w['only_arm']}, only G16 {w['only_g16']}")
    for r in w["sections"]:
        print(f"{r['label']:22s} {r['arm_deaths']:4d}/{r['arm_reached']:4d}  {r['g16_deaths']:4d}/{r['g16_reached']:4d}"
              f"  {r['hazard_d_pp']:+.1f} [{r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}]"
              f"  lostHere {r['only_g16_kills_arm_died_here']} wonHere {r['only_arm_kills_g16_died_here']}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
