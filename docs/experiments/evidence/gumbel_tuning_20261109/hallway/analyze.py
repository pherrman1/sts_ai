#!/usr/bin/env python3
"""Gumbel tuning, hallway test (PREREG.md): c2 against the control on hallway fights.

usage: python3 -I analyze.py SCOUT_DIR UNITS_DIR OUT.json [--self-test]
  SCOUT_DIR: the scout's units (S-<seed>-a3-scout.*), UNITS_DIR: this campaign's units (S-<seed>-a3-hall.*); tars are
  read in place, extracted files work too (../analyze.py's loader).

HP lost by a copy = entry HP - exit HP, the entry HP on a loss; a fight's value for an arm = mean over its 4 copies,
likewise potions used and losses. Arm fights = fights carrying both arms with 4 valid copies each; a fight missing a
copy is dropped and counted. Hallway fights = room M, acts 1-3 (primary); '?' rooms are secondary.
Reproduction: every unit's fights through act 3 are the scout's (floor and encounter, in order), and every main-line
copy 0 equals the scout's copy 0 at the same position (won, exitHp, exitMaxHp, turns, decisions, simulations,
potionsUsed; fights matched by floor and order on the floor). Both shares >= 99% = PAIRED, otherwise every verdict is
NOT_PAIRED. Units whose .done rc != 0 are excluded and listed.
Primary: d = c2 - ctl HP lost per hallway fight, mean over fights, 95% seed-clustered bootstrap (10,000 resamples,
seed 20261109): C2_HALLWAY_WORSE if lo > 0, C2_HALLWAY_BETTER if hi < 0, else NO_DIFFERENCE_SHOWN.
Secondary (not gates): per act; '?' fights; potions used per fight; HP + 3.7 HP per potion (§766's price); losses per
copy; CPU ratio; per encounter with >= 10 fights.
"""
import collections, copy, importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("tuning_analyze", HERE.parent / "analyze.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
CTL = "gsh16+flat16000+mb4"
C2 = "gsh16+flat16000+mb4+ucb12.5+pw100+tp32+wet14.8+wch1.85"
REPS, SEED, GATE, POTION_HP = 10000, 20261109, 0.99, 3.7


def by_floor(fights):
    out = collections.defaultdict(list)
    for f in fights:
        out[f["floor"]].append(f)
    return out


def copy0(f):
    return next((r for r in f.get("replicates", []) if r["r"] == 0), None)


def arm_value(f, token):
    cs = {c["r"]: c for c in f.get("arms", {}).get(token, [])}
    if sorted(cs) != list(range(T.K)) or not all(c["valid"] for c in cs.values()):
        return None
    hp = f["hp"]
    return dict(hp=float(np.mean([hp - (c["exitHp"] if c["won"] else 0) for c in cs.values()])),
                pot=float(np.mean([len(c["potionsUsed"]) for c in cs.values()])),
                loss=float(np.mean([not c["won"] for c in cs.values()])),
                cpu=float(np.mean([c["cpu"] for c in cs.values()])))


def clustered(rows, fn, rng):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["seed"]].append(fn(r))
    groups = list(by.values())
    if not groups:
        return None
    sums, cnt = np.array([sum(g) for g in groups]), np.array([len(g) for g in groups])
    i = rng.integers(0, len(groups), size=(REPS, len(groups)))
    est = sums[i].sum(1) / cnt[i].sum(1)
    return dict(mean=float(sums.sum() / cnt.sum()), ci95=[float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))],
                fights=len(rows), seeds=len(groups))


def summary(rows, rng):
    if not rows:
        return dict(fights=0)
    return dict(fights=len(rows), seeds=len({r["seed"] for r in rows}),
                ctl_hp=float(np.mean([r["ctl"]["hp"] for r in rows])), c2_hp=float(np.mean([r["c2"]["hp"] for r in rows])),
                d_hp=clustered(rows, lambda r: r["c2"]["hp"] - r["ctl"]["hp"], rng),
                ctl_potions=float(np.mean([r["ctl"]["pot"] for r in rows])),
                c2_potions=float(np.mean([r["c2"]["pot"] for r in rows])),
                d_potions=clustered(rows, lambda r: r["c2"]["pot"] - r["ctl"]["pot"], rng),
                d_hp_plus_potions=clustered(rows, lambda r: (r["c2"]["hp"] - r["ctl"]["hp"])
                                            + POTION_HP * (r["c2"]["pot"] - r["ctl"]["pot"]), rng),
                ctl_loss_share=float(np.mean([r["ctl"]["loss"] for r in rows])),
                c2_loss_share=float(np.mean([r["c2"]["loss"] for r in rows])),
                cpu_ratio=float(sum(r["c2"]["cpu"] for r in rows) / max(1e-9, sum(r["ctl"]["cpu"] for r in rows))))


def analyze(scout, units, bad_units):
    rng = np.random.default_rng(SEED)
    repro = collections.Counter()
    rows, dropped = [], collections.Counter()
    for tag, x in sorted(units.items()):
        seed = int(tag.split("-")[1])
        sc = scout.get(seed)
        mine = [(f["floor"], f["encounter"]) for f in x["fights"] if f["act"] <= 3]
        theirs = [(f["floor"], f["encounter"]) for f in (sc["fights"] if sc else []) if f["act"] <= 3]
        repro["units_same_fights" if mine == theirs else "units_other_fights"] += 1
        sf = by_floor(sc["fights"]) if sc else {}
        for floor, fs in by_floor(x["fights"]).items():
            for j, f in enumerate(fs):
                c0 = copy0(f)
                s0 = copy0(sf[floor][j]) if floor in sf and j < len(sf[floor]) else None
                if c0 is not None and s0 is not None:
                    repro["copy0_same" if T.sig(c0) == T.sig(s0) else "copy0_differ"] += 1
                elif c0 is not None:
                    repro["copy0_no_scout"] += 1
                if "arms" not in f or f["act"] > 3:
                    continue
                a, b = arm_value(f, CTL), arm_value(f, C2)
                if a is None or b is None:
                    dropped["missing_or_invalid_copy"] += 1
                    continue
                rows.append(dict(seed=seed, floor=floor, act=f["act"], room=f["room"], enc=f["encounter"], ctl=a, c2=b))
    n0 = repro["copy0_same"] + repro["copy0_differ"] + repro["copy0_no_scout"]
    nu = repro["units_same_fights"] + repro["units_other_fights"]
    r0 = repro["copy0_same"] / n0 if n0 else None
    ru = repro["units_same_fights"] / nu if nu else None
    paired = r0 is not None and ru is not None and r0 >= GATE and ru >= GATE
    hall = [r for r in rows if r["room"] == "M"]
    prim = summary(hall, rng)
    d = prim.get("d_hp")
    verdict = ("NOT_PAIRED" if not paired else "NO_DATA" if not d else "C2_HALLWAY_WORSE" if d["ci95"][0] > 0
               else "C2_HALLWAY_BETTER" if d["ci95"][1] < 0 else "NO_DIFFERENCE_SHOWN")
    encs = collections.defaultdict(list)
    for r in hall:
        encs[r["enc"]].append(r)
    return dict(units=len(units), bad_units=bad_units, dropped=dict(dropped),
                reproduction=dict(repro, copy0_rate=r0, units_rate=ru, threshold=GATE,
                                  verdict="PAIRED" if paired else "NOT_PAIRED"),
                primary=dict(prim, verdict=verdict),
                by_act={str(a): summary([r for r in hall if r["act"] == a], rng) for a in (1, 2, 3)},
                question_rooms=summary([r for r in rows if r["room"] == "?"], rng),
                other_rooms=sorted({r["room"] for r in rows} - {"M", "?"}),
                by_encounter={e: summary(v, rng) for e, v in sorted(encs.items()) if len(v) >= 10})


def main(scout_dir, units_dir, out):
    tally_s, tally_u = collections.Counter(), collections.Counter()
    scout = {int(t.split("-")[1]): x for t, x in T.load(scout_dir, tally_s).items()}
    units = T.load(units_dir, tally_u)
    bad = [k for k in tally_u if k != 0]
    res = analyze(scout, units, {str(k): v for k, v in tally_u.items() if k != 0})
    res["unit_rc"] = {str(k): v for k, v in tally_u.items()}
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    p = res["primary"]
    d = p.get("d_hp") or {}
    print(f"units {res['units']} (rc tally {res['unit_rc']}), dropped {res['dropped']}, reproduction "
          f"{res['reproduction']['verdict']} (copy0 {res['reproduction']['copy0_rate']}, units "
          f"{res['reproduction']['units_rate']})")
    if d:
        print(f"hallway fights {p['fights']} on {p['seeds']} seeds: ctl {p['ctl_hp']:.2f} c2 {p['c2_hp']:.2f} HP, d "
              f"{d['mean']:+.2f} [{d['ci95'][0]:+.2f}, {d['ci95'][1]:+.2f}] -> {p['verdict']}; potions d "
              f"{p['d_potions']['mean']:+.3f}; cpu x{p['cpu_ratio']:.2f}")
    if bad:
        print("units with rc != 0 excluded:", bad)


def self_test():
    def cp(r, won, exit_hp, pot=0):
        return dict(r=r, won=won, exitHp=exit_hp, exitMaxHp=80, turns=3, decisions=9, simulations=1000,
                    potionsUsed=["X"] * pot, valid=True, cpu=1.0)
    def fight(floor, room, enc, hp, ctl_exit, c2_exit, c2_pot=0):
        return dict(floor=floor, act=1, room=room, encounter=enc, hp=hp, replicates=[cp(0, True, ctl_exit[0])],
                    arms={CTL: [cp(r, True, e) for r, e in enumerate(ctl_exit)],
                          C2: [cp(r, e > 0, e, c2_pot) for r, e in enumerate(c2_exit)]})
    units, scout = {}, {}
    for s in range(6):
        fs = [fight(1, "M", "Jaw Worm", 70, [65, 66, 64, 65], [60, 61, 0, 62], 1),
              fight(30, "?", "Colosseum", 50, [40, 40, 40, 40], [40, 40, 40, 40]),
              fight(30, "?", "Colosseum Nobs", 40, [30, 30, 30, 30], [30, 30, 30, 30])]
        units[f"S-{s}-a3-hall"] = dict(fights=fs)
        scout[s] = copy.deepcopy(dict(fights=[dict(floor=f["floor"], act=1, encounter=f["encounter"], replicates=f["replicates"]) for f in fs]))
    r = analyze(scout, units, {})
    assert r["reproduction"]["verdict"] == "PAIRED", r["reproduction"]
    assert r["primary"]["fights"] == 6 and r["question_rooms"]["fights"] == 12
    # c2: losses 10, 9, 70 (death), 8 -> 24.25; ctl 5, 4, 6, 5 -> 5.0
    assert abs(r["primary"]["d_hp"]["mean"] - 19.25) < 1e-9, r["primary"]
    assert r["primary"]["verdict"] == "C2_HALLWAY_WORSE"
    assert abs(r["primary"]["d_potions"]["mean"] - 1.0) < 1e-9
    assert abs(r["primary"]["c2_loss_share"] - 0.25) < 1e-9
    units["S-0-a3-hall"]["fights"][0]["replicates"][0]["exitHp"] = 1   # one main-line copy 0 differs
    r = analyze(scout, units, {})
    assert r["reproduction"]["copy0_differ"] == 1 and r["reproduction"]["verdict"] == "NOT_PAIRED"
    assert r["primary"]["verdict"] == "NOT_PAIRED"
    print("self-test OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 4:
        main(*sys.argv[1:])
    else:
        sys.exit(__doc__)
