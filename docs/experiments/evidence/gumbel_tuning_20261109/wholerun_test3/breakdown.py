#!/usr/bin/env python3
"""Descriptive breakdown behind RESULT.md's "Where the arms lose" (not pre-registered, not a gate).

usage: python3 -I breakdown.py NEW_UNITS REF_UNITS OUT.json
  NEW_UNITS / REF_UNITS: as for analyze.py (Tests 1-3 extracted out/units; §775's units).

G16NR and G16CAP each against §775's G16 on seeds where both finished: deaths by section of the final floor exactly as
../wholerun_test2/breakdown.py (hazard = deaths among runs reaching the section, arm - G16, seed bootstrap, 4,000
resamples, seed 20261109, 95%), plus the joint Heart-kill pattern of G16, G16CAP and G16NR per seed.
"""
import importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T2 = module(HERE.parent / "wholerun_test2" / "breakdown.py", "test2_breakdown")
W = T2.W
W.NEW_ARMS = W.NEW_ARMS + ("G16NR",)
W.ENV["new"]["G16NR"] = W._G + (None, None, None, "400", "8", "1024")
W.SIMS["G16NR"] = 16000


def main(new_units, ref_units, out):
    res = {}
    for arm in ("G16NR", "G16CAP"):
        T2.ARM = arm
        res[arm] = T2.whole_runs(new_units, ref_units, np.random.default_rng(T2.B.SEED))
    new, ref = W.load(new_units, "new")[0], W.load(ref_units, "ref")[0]
    seeds = [s for s in W.SEEDS if ("G16NR", s) in new and ("G16CAP", s) in new and ("G16", s) in ref]
    pat = {}
    for s in seeds:
        k = f"G16 {ref[('G16', s)][0]} G16CAP {new[('G16CAP', s)][0]} G16NR {new[('G16NR', s)][0]}"
        pat[k] = pat.get(k, 0) + 1
    res["joint_heart_pattern"] = dict(seeds=len(seeds), counts=dict(sorted(pat.items())))
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    for arm in ("G16NR", "G16CAP"):
        w = res[arm]
        print(f"{arm}: seeds {w['seeds']}: only {arm} {w['only_arm']}, only G16 {w['only_g16']}")
        for r in w["sections"]:
            print(f"  {r['label']:22s} {r['arm_deaths']:4d}/{r['arm_reached']:4d}  {r['g16_deaths']:4d}/{r['g16_reached']:4d}"
                  f"  {r['hazard_d_pp']:+.1f} [{r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}]")
    for k, v in res["joint_heart_pattern"]["counts"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
