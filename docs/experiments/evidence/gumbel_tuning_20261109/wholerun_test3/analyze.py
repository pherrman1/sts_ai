#!/usr/bin/env python3
"""Whole-run Test 3 (PREREG.md): §775's G16 + mb4 without tree reuse (G16NR, node reuse cap 1024) against §775's
G16 + mb4, seeds 111378256-111379279, with Test 2's G16CAP (cap 262144) as the third point.

    python3 -I analyze.py NEW_ROOT REF_ROOT result.json [CLAIMS_LIST]
    python3 -I analyze.py --self-test

NEW_ROOT is one directory with the extracted units of Test 1 (its 32 sentinel G16 games), Test 2 (G16CAP) and this
campaign (G16NR); REF_ROOT §775's units (D, G16, G32, G64); CLAIMS_LIST this campaign's claims snapshot. Loading,
log checks, env checks, pairing and the bootstrap are ../wholerun/analyze.py's (frozen with Test 1's PREREG), with
the arm G16NR added.
1. Sentinel: Test 1's 32 G16 games against §775's (as ../wholerun/analyze.py). Not REUSE_VALID = CONTROL_INVALID.
2. Primary, d = Heart kill G16NR - G16 per seed, G16 = §775's game; universe = seeds whose G16NR unit was claimed;
   dropped seeds listed, never imputed; more than 20 dropped = INCOMPLETE. 95% seed bootstrap (10,000 resamples, seed
   20261109): NO_REUSE_BETTER if lo > 0, NO_REUSE_WORSE if hi < 0, else NO_DIFFERENCE_SHOWN.
3. Secondary (not gates, 95%): G16NR - G16CAP, G16CAP - G16 (Test 2 again), G16NR - D; per arm Heart kill, act-4
   reach, mean final floor, CPU per run, games over 1 h, and the tree reuse counters (kept reroots, cap resets,
   inherited visits as a share of all simulations).
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("wholerun_analyze", HERE.parent / "wholerun" / "analyze.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
W.NEW_ARMS = W.NEW_ARMS + ("G16NR",)
W.ENV["new"]["G16NR"] = W._G + (None, None, None, "400", "8", "1024")
W.SIMS["G16NR"] = 16000


def verdict(r, valid):
    if not valid:
        return "CONTROL_INVALID"
    if len(r["dropped"]) > W.MAX_DROPPED or not r["n"]:
        return "INCOMPLETE"
    lo, hi = r["ci95"]
    return "NO_REUSE_BETTER" if lo > 0 else "NO_REUSE_WORSE" if hi < 0 else "NO_DIFFERENCE_SHOWN"


def per_arm(new, ref):
    out = {}
    g16cpu = np.mean([v[3] for (a, s), v in ref.items() if a == "G16"]) if any(a == "G16" for a, _ in ref) else None
    for side, games, arms in (("new", new, ("G16", "G16CAP", "G16NR")), ("ref", ref, W.REF_ARMS)):
        for arm in arms:
            vals = [v for (a, s), v in games.items() if a == arm and s in W.SEEDS]
            if not vals:
                continue
            g = np.array([v[:5] for v in vals], float)
            row = {"games": len(g), "heart": float(g[:, 0].mean()), "act4": float(g[:, 1].mean()),
                   "floor": float(g[:, 2].mean()), "cpu_sec": float(g[:, 3].mean()),
                   "cpu_ratio_to_ref_G16": float(g[:, 3].mean() / g16cpu) if g16cpu else None,
                   "long_games": int((g[:, 4] > 3600).sum()), "max_wall": int(g[:, 4].max())}
            ru = [v[5] for v in vals if v[5] is not None]
            sims = sum(v[6] for v in vals if v[5] is not None and v[6] is not None)
            if ru:
                t = np.array(ru, np.int64).sum(0)
                rer, inh, fresh, caps, lost = (int(t[i]) for i in range(5))
                row["reuse"] = {"games": len(ru), "reroots": rer, "inherited": inh, "fresh": fresh,
                                "cap_resets": caps, "cap_lost": lost,
                                "kept_share_of_kept_or_reset": rer / (rer + caps) if rer + caps else None,
                                "inherited_share_of_sims": inh / sims if sims else None}
            out[f"{side}:{arm}"] = row
    return out


def main(new_root, ref_root, out, claims=None):
    new, bad_n, ab_n, mm_n, pr_n, attempted = W.load(new_root, "new", claims)
    ref, bad_r, ab_r, mm_r, pr_r, _ = W.load(ref_root, "ref")
    outdir = os.path.dirname(out) or "."
    sent = W.sentinel(pr_n, pr_r)
    valid = sent["verdict"] == "REUSE_VALID"
    res = {"bad": bad_n + bad_r, "aborts": ab_n + ab_r, "env_mismatch": mm_n + mm_r, "sentinel": sent}
    p = W.contrast(new, ref, attempted, ("ref", "G16"), ("new", "G16NR"), outdir, "G16NR", gated=False)
    p["verdict"] = verdict(p, valid)
    res["primary"] = p
    sec = {"G16NR_minus_G16CAP": (("new", "G16CAP"), ("new", "G16NR")),
           "G16CAP_minus_G16": (("ref", "G16"), ("new", "G16CAP")),
           "G16NR_minus_D": (("ref", "D"), ("new", "G16NR"))}
    res["secondary"] = {k: W.contrast(new, ref, attempted | {f"{s}_G16CAP" for s in W.SEEDS}, a, b, outdir, k, False)
                        for k, (a, b) in sec.items()}
    res["per_arm"] = per_arm(new, ref)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(f"bad {len(res['bad'])} (env mismatch {len(res['env_mismatch'])}) aborts {len(res['aborts'])}  sentinel "
          f"{sent['identical']}/{sent['of']} {sent['verdict']}")
    for name, r in [("G16NR - G16", p)] + list(res["secondary"].items()):
        if not r["n"]:
            print(f"{name}: no analysable seed -> {r.get('verdict')}")
            continue
        print(f"{name}: n {r['n']} dropped {len(r['dropped'])}  heart {100 * r['heart_control']:.2f}% -> "
              f"{100 * r['heart_arm']:.2f}%  d {100 * r['d']:+.2f} [{100 * r['ci95'][0]:+.2f}, "
              f"{100 * r['ci95'][1]:+.2f}] pp  act4 d {100 * r['act4_d']:+.2f} pp  cpu ratio {r['cpu_ratio']:.2f}"
              + (f"  verdict {r['verdict']}" if r.get("verdict") else ""))
    for k, row in res["per_arm"].items():
        if "reuse" in row:
            u = row["reuse"]
            print(f"{k} reuse: {u['games']} games  kept {u['reroots']} of {u['reroots'] + u['cap_resets']} "
                  f"kept-or-reset reroots ({100 * (u['kept_share_of_kept_or_reset'] or 0):.2f}%), carried "
                  f"{100 * (u['inherited_share_of_sims'] or 0):.2f}% of sims")
    return res


def self_test():
    """Synthetic campaign: gain / no gain / loss, drops, a differing sentinel -> verdicts."""
    import random
    t = tempfile.mkdtemp()
    rng = random.Random(3)
    newr, refr = os.path.join(t, "new"), os.path.join(t, "ref")

    def write(root, side, unit, arm, s, k, rc=0, reuse=""):
        d = os.path.join(root, unit)
        os.makedirs(d, exist_ok=True)
        Path(d, f"{arm}-{s}.done").write_text(f"tag={arm}-{s} rc={rc} start=x wall=20 abort=0")
        Path(d, f"{arm}-{s}.env").write_text("STS_FAIR=1\n" + "".join(
            f"{k_}={v}\n" for k_, v in zip(W.KEYS, W.ENV[side][arm]) if v is not None))
        Path(d, f"{arm}-{s}.log").write_text(
            f"BEST stack config: x  seeds {s}..{s}  asc 20  sims {W.SIMS[arm]}  threads 1\n"
            f"BEST  win%= {100.0 if k else 0.0}  avg_floor= {56 if k else 30}  avg_hp_end= 0.0   "
            f"cpu_sec/run=20.00   wall=20.0s\n")
        Path(d, f"{arm}-{s}.err").write_text(f"[heart1_ppo] seed={s} decisions={k + 3}\n"
                                             f"[silver] whole-run Gumbel roots=10 sims=1000 (all)\n" + reuse)

    def campaign(rate_nr, drop=(), sentinel_ok=True):
        shutil.rmtree(t, ignore_errors=True)
        out = {}
        for s in W.SEEDS:
            for arm, rate in (("D", 0.3), ("G16", 0.4), ("G32", 0.4), ("G64", 0.4)):
                out[(arm, s)] = int(rng.random() < rate)
                write(refr, "ref", f"{s}_{'G64' if arm == 'G64' else 'low'}", arm, s, out[(arm, s)])
            write(newr, "new", f"{s}_G16CAP", "G16CAP", s, int(rng.random() < 0.4),
                  reuse="[silver] whole-run tree reuse: reroots=9 inherited=500 fresh=1 cap_resets=0 cap_lost=0 "
                        "reuse_cap=262144\n")
            write(newr, "new", f"{s}_G16NR", "G16NR", s, int(rng.random() < rate_nr), rc=1 if s in drop else 0,
                  reuse="[silver] whole-run tree reuse: reroots=1 inherited=50 fresh=1 cap_resets=8 cap_lost=400 "
                        "reuse_cap=1024\n")
        for s in W.SENTINEL:
            k = out[("G16", s)] if sentinel_ok or s != W.SENTINEL[5] else 1 - out[("G16", s)]
            write(newr, "new", f"{s}_G16", "G16", s, k)
        return main(newr, refr, os.path.join(t, "r.json"))

    r = campaign(0.52)
    assert r["sentinel"]["verdict"] == "REUSE_VALID" and r["primary"]["verdict"] == "NO_REUSE_BETTER", r["primary"]
    assert r["per_arm"]["new:G16NR"]["reuse"]["kept_share_of_kept_or_reset"] == 1 / 9
    assert r["secondary"]["G16NR_minus_G16CAP"]["n"] == 1024
    r = campaign(0.40, drop=(111378300, 111378301))
    assert r["primary"]["verdict"] == "NO_DIFFERENCE_SHOWN" and r["primary"]["dropped"] == [111378300, 111378301]
    assert r["bad"] == ["new:G16NR-111378300", "new:G16NR-111378301"], r["bad"]
    r = campaign(0.28)
    assert r["primary"]["verdict"] == "NO_REUSE_WORSE", r["primary"]
    r = campaign(0.52, drop=tuple(range(111378400, 111378421)))
    assert r["primary"]["verdict"] == "INCOMPLETE", r["primary"]["verdict"]
    r = campaign(0.52, sentinel_ok=False)
    assert r["primary"]["verdict"] == "CONTROL_INVALID", r["sentinel"]
    shutil.rmtree(t, ignore_errors=True)
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:5])
