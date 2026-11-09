#!/usr/bin/env python3
"""Descriptive breakdown behind RESULT.md's "Where c2 loses" (not pre-registered, not a gate).

usage: python3 -I breakdown.py NEW_UNITS REF_UNITS COMBINE_TARS SCREEN_TARS OUT.json
  NEW_UNITS / REF_UNITS: extracted out/units of this campaign and of §775 (as for analyze.py);
  COMBINE_TARS / SCREEN_TARS: the unit tars of tuning stages 2 and 1 (share: combat-plan/gumbel-tuning-combine/units,
  combat-plan/gumbel-tuning-screen/units).

Whole runs (C2 vs §775's G16 on seeds where both finished): deaths by section of the final floor (act 1 = floors
1-15, bosses 16 / 33 / 50 / 51, act 2 = 17-32, act 3 = 34-49, act 4 = 52-56), hazard = deaths among runs reaching
the section, C2 - G16 with a seed bootstrap; the section where the loser died on seeds with different outcomes.
Stage 2 (c2 vs ctl, 4 copies per fight): HP lost as ../analyze.py (0 exit HP on a loss, floor 51's Act-4 heal taken
out) and potions used per fight, by act and room, seed-clustered bootstrap. Stage 1 (304 design fights): each of c2's
five factors' main effect by act and room, signed so that negative = c2's level loses less HP.
Bootstraps: 4,000 resamples, seed 20261109, 95%.
"""
import collections, importlib.util, json, sys, tarfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


W = module(HERE / "analyze.py", "wholerun_analyze")
T = module(HERE.parent / "analyze.py", "tuning_analyze")
REPS, SEED = 4000, 20261109
SECTIONS = [("a1", "act 1, floors 1-15"), ("b16", "act-1 boss (16)"), ("a2", "act 2, floors 17-32"),
            ("b33", "act-2 boss (33)"), ("a3", "act 3, floors 34-49"), ("b50", "act-3 boss 1 (50)"),
            ("b51", "act-3 boss 2 (51)"), ("a4", "act 4 (52-56)")]
CTL = "gsh16+flat16000+mb4"
C2 = "gsh16+flat16000+mb4+ucb12.5+pw100+tp32+wet14.8+wch1.85"
C2_DIR = {"F": -1, "G": -1, "H": 1, "J": 1, "K": -1}   # c2's side of each stage-1 factor


def section(floor, won):
    f = int(floor)
    if won:
        return "win"
    return ("a1" if f <= 15 else "b16" if f == 16 else "a2" if f <= 32 else "b33" if f == 33 else "a3" if f <= 49
            else "b50" if f == 50 else "b51" if f == 51 else "a4")


def whole_runs(new_units, ref_units, rng):
    new = W.load(new_units, "new")[0]
    ref = W.load(ref_units, "ref")[0]
    seeds = [s for s in W.SEEDS if ("C2", s) in new and ("G16", s) in ref]
    sec = {"C2": np.array([section(new[("C2", s)][2], new[("C2", s)][0]) for s in seeds]),
           "G16": np.array([section(ref[("G16", s)][2], ref[("G16", s)][0]) for s in seeds])}

    def hazard(arm, idx):
        x, alive, out = sec[arm][idx], len(idx), {}
        for k, _ in SECTIONS:
            d = int((x == k).sum())
            out[k] = (d, alive)
            alive -= d
        return out

    every = np.arange(len(seeds))
    base = {a: hazard(a, every) for a in sec}
    boot = collections.defaultdict(list)
    for _ in range(REPS):
        i = rng.integers(0, len(seeds), len(seeds))
        h1, h2 = hazard("C2", i), hazard("G16", i)
        for k, _ in SECTIONS:
            boot[k].append(h1[k][0] / h1[k][1] - h2[k][0] / h2[k][1])
    win = {a: sec[a] == "win" for a in sec}
    rows = []
    for k, label in SECTIONS:
        c, g = base["C2"][k], base["G16"][k]
        lo, hi = np.percentile(boot[k], [2.5, 97.5])
        rows.append(dict(section=k, label=label, c2_deaths=c[0], c2_reached=c[1], g16_deaths=g[0], g16_reached=g[1],
                         hazard_d_pp=100 * (c[0] / c[1] - g[0] / g[1]), ci95_pp=[100 * lo, 100 * hi],
                         only_g16_kills_c2_died_here=int(((sec["C2"] == k) & win["G16"]).sum()),
                         only_c2_kills_g16_died_here=int(((sec["G16"] == k) & win["C2"]).sum())))
    return dict(seeds=len(seeds), sections=rows,
                both_kill=int((win["C2"] & win["G16"]).sum()), neither=int((~win["C2"] & ~win["G16"]).sum()),
                only_c2=int((win["C2"] & ~win["G16"]).sum()), only_g16=int((~win["C2"] & win["G16"]).sum()))


def fights(tar_dir):
    """(seed, floor) -> dict(act, room, hp, copies={token: {r: copy}}) over every unit tar."""
    out = {}
    for t in sorted(Path(tar_dir).glob("*.tar")):
        with tarfile.open(t) as tf:
            for m in tf.getmembers():
                if not m.name.endswith(".fights.json"):
                    continue
                x = json.loads(tf.extractfile(m).read())
                seed = int(Path(m.name).name.split("-")[1])
                for f in x["fights"]:
                    if "arms" not in f or f["room"] not in ("E", "B") or f["act"] > 3:
                        continue
                    d = out.setdefault((seed, f["floor"]), dict(act=f["act"], room=f["room"], hp=f["hp"], copies={}))
                    for tok, cs in f["arms"].items():
                        for c in cs:
                            d["copies"].setdefault(tok, {})[c["r"]] = c
    return out


def per_fight(fight, tok, floor):
    cs = fight["copies"].get(tok, {})
    if sorted(cs) != list(range(T.K)) or not all(c["valid"] for c in cs.values()):
        return None
    hp, final = fight["hp"], fight["act"] == 3 and floor == 51
    loss = [hp - ((T.before_act4_heal(c["exitHp"], c["exitMaxHp"]) if final else c["exitHp"]) if c["won"] else 0)
            for c in cs.values()]
    return float(np.mean(loss)), float(np.mean([len(c["potionsUsed"]) for c in cs.values()]))


def clustered(rows, key, rng):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["seed"]].append(r[key])
    groups = list(by.values())
    sums, cnt = np.array([sum(g) for g in groups]), np.array([len(g) for g in groups])
    i = rng.integers(0, len(groups), size=(REPS, len(groups)))
    est = sums[i].sum(1) / cnt[i].sum(1)
    return [float(sums.sum() / cnt.sum()), float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))]


def segments(rows):
    yield "all", rows
    for a in (1, 2, 3):
        for rm in ("E", "B"):
            yield f"act {a} {rm}", [r for r in rows if r["act"] == a and r["room"] == rm]


def stage2(tar_dir, rng):
    rows = []
    for (seed, floor), f in fights(tar_dir).items():
        a, b = per_fight(f, CTL, floor), per_fight(f, C2, floor)
        if a and b:
            rows.append(dict(seed=seed, act=f["act"], room=f["room"], d_hp=b[0] - a[0], d_pot=b[1] - a[1],
                             ctl_pot=a[1], c2_pot=b[1]))
    return {name: dict(fights=len(sub), d_hp=clustered(sub, "d_hp", rng), d_potions=clustered(sub, "d_pot", rng),
                       ctl_potions=float(np.mean([r["ctl_pot"] for r in sub])),
                       c2_potions=float(np.mean([r["c2_pot"] for r in sub])))
            for name, sub in segments(rows)}


def stage1(tar_dir, rng):
    design = {}
    for line in (HERE.parent / "arms.tsv").read_text().splitlines():
        p = line.split("\t")
        if p[0].startswith("d") and p[0][1:].isdigit():
            design[p[-1]] = dict(zip("ABCDEFGHJK", (int(v) for v in p[1:11])))
    rows = []
    for (seed, floor), f in fights(tar_dir).items():
        v = {tok: per_fight(f, tok, floor) for tok in design}
        if any(x is None for x in v.values()):
            continue
        row = dict(seed=seed, act=f["act"], room=f["room"])
        for fac, sign in C2_DIR.items():
            hi = np.mean([v[t][0] for t in design if design[t][fac] == 1])
            lo = np.mean([v[t][0] for t in design if design[t][fac] == -1])
            row[fac] = sign * (hi - lo)
        rows.append(row)
    return {name: dict(fights=len(sub), **{fac: clustered(sub, fac, rng) for fac in C2_DIR})
            for name, sub in segments(rows)}


def main(new_units, ref_units, combine_tars, screen_tars, out):
    rng = np.random.default_rng(SEED)
    res = dict(whole_runs=whole_runs(new_units, ref_units, rng), stage2_c2_minus_ctl=stage2(combine_tars, rng),
               stage1_c2_side_effects=stage1(screen_tars, rng))
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    w = res["whole_runs"]
    print(f"seeds {w['seeds']}: " + ", ".join(f"{r['section']} {r['hazard_d_pp']:+.1f}" for r in w["sections"]))
    s = res["stage2_c2_minus_ctl"]["all"]
    print(f"stage 2: {s['fights']} fights, d HP {s['d_hp'][0]:+.2f}, d potions {s['d_potions'][0]:+.3f}")
    print("stage 1 J by segment: " + ", ".join(f"{k} {v['J'][0]:+.2f}" for k, v in res["stage1_c2_side_effects"].items()))


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    main(*sys.argv[1:])
