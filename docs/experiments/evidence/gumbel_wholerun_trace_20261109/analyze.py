#!/usr/bin/env python3
"""Traced replay of the §775 whole-run Gumbel test, arms D and G16 (PREREG.md). Descriptive, not a gate.

    python3 analyze.py OUT_ROOT REF_ROOT result.json
    python3 analyze.py --self-test

OUT_ROOT: one directory per unit (pNNN_<seeds>/) with ARM-SEED.{done,log,err,env,trace.jsonl.gz} from run_unit.sh
(verify_campaign.py --extract DIR writes DIR/out/units/<unit>/). REF_ROOT: the extracted §775 units
(<seed>_low/ARM-SEED.{done,log,err}).
1. Reproduction (validity): a game reproduces if rc 0 in both runs and the final BEST line (win, floor, hp_end), the
   [heart1_ppo] game line and, for G16, the [silver] whole-run Gumbel roots/sims line equal §775's. Only seeds whose two
   games both reproduce are analysed; the others are listed. More than 10 non-reproducing games = REPRO_FAIL in the
   output (the tables are still written, on the reproducing seeds).
2. Per fight class (act x room; Act 4: Shield and Spear, Heart): fights, deaths per fight, HP lost per won fight
   (pre HP - post HP; post includes on-victory heals such as Burning Blood), potions used per fight (held before -
   held after, at least 0), turns. Arm means over all their fights; G16 - D with a seed-cluster bootstrap (10,000
   resamples, seed 20261110) of the ratio of sums.
3. State at entry of each boss fight (Acts 1-3, both Act 3 bosses), Shield and Spear and the Heart: HP, HP / max HP,
   potions held, deck size, among runs that reach it; G16 - D as in 2.
4. Death cause: the fight that ends each lost run (act, room, encounter); counts per arm and on discordant seeds.
5. First divergence (paired on identical states): fights before a seed's first fight with a different post state
   were played from identical states by both arms. The first divergent fight starts from the same state in both arms:
   per room class and act, G16 - D in post HP (a death counts as post HP 0) and in deaths, paired over seeds.
"""
import gzip
import json
import re
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ARMS = ("D", "G16")
SEEDS = range(111378256, 111379280)
WIN = re.compile(r"^BEST\s+win%=\s*([\d.]+)\s+avg_floor=\s*([\d.]+)\s+avg_hp_end=\s*([\d.]+)", re.M)
PPO = re.compile(r"^\[heart1_ppo\] seed=\d+ .*$", re.M)
GUM = re.compile(r"^\[silver\] whole-run Gumbel roots=\d+ sims=\d+.*$", re.M)
B = 10000
warnings.simplefilter("ignore", RuntimeWarning)   # classes without won fights give all-NaN HP resamples


def summary(d, arm, seed):
    done = d / f"{arm}-{seed}.done"
    if not done.exists():
        return None
    kv = dict(x.split("=", 1) for x in done.read_text().split())
    if kv.get("rc") != "0":
        return None
    log = (d / f"{arm}-{seed}.log").read_text()
    err = (d / f"{arm}-{seed}.err").read_text()
    m = WIN.search(log)
    if not m:
        return None
    p = PPO.findall(log + "\n" + err)
    g = GUM.findall(err)
    return (m.groups(), p[-1] if p else None, g[-1] if g else None)


def fights(path):
    out = []
    with gzip.open(path, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") == "battle":
                out.append(r)
    return out


def fclass(r):
    act, enc, room = r["pre"]["act"], r["encounter"], r["room"]
    if act == 4:
        return "A4 Shield and Spear" if enc == "SHIELD_AND_SPEAR" else "A4 Heart" if enc == "THE_HEART" else "A4 other"
    return f"A{act} {room}"


def ratio_boot(per_seed, rng):
    """per_seed: arm -> seed -> (num, den). Returns means per arm, diff, 95% CI of the diff over seed resamples."""
    seeds = sorted(set(per_seed["D"]) | set(per_seed["G16"]))
    if not seeds:
        return None
    a = {arm: np.array([per_seed[arm].get(s, (0.0, 0.0)) for s in seeds], float) for arm in ARMS}
    mean = {arm: (a[arm][:, 0].sum() / a[arm][:, 1].sum() if a[arm][:, 1].sum() else float("nan")) for arm in ARMS}
    idx = rng.integers(0, len(seeds), size=(B, len(seeds)))
    with np.errstate(invalid="ignore", divide="ignore"):
        bd = {arm: a[arm][idx, 0].sum(1) / a[arm][idx, 1].sum(1) for arm in ARMS}
    diff = bd["G16"] - bd["D"]
    lo, hi = np.nanpercentile(diff, [2.5, 97.5])
    n = {arm: int(a[arm][:, 1].sum()) for arm in ARMS}
    return dict(n=n, D=round(mean["D"], 4), G16=round(mean["G16"], 4), diff=round(mean["G16"] - mean["D"], 4),
                ci95=[round(float(lo), 4), round(float(hi), 4)])


def analyse(out_root, ref_root):
    out_root, ref_root = Path(out_root), Path(ref_root)
    repro_bad, data = [], {}
    where = {}
    for done in out_root.glob("*/*.done"):
        arm, seed = done.stem.rsplit("-", 1)
        if arm in ARMS:
            where.setdefault(int(seed), done.parent)
    for seed in SEEDS:
        d = where.get(seed)
        if d is None:
            continue
        ok = True
        for arm in ARMS:
            got, ref = summary(d, arm, seed), summary(ref_root / f"{seed}_low", arm, seed)
            if got is None or ref is None or got[0] != ref[0] or got[1] != ref[1] or (arm == "G16" and got[2] != ref[2]):
                repro_bad.append(f"{arm}-{seed}")
                ok = False
        if ok:
            data[seed] = {arm: dict(win=float(summary(d, arm, seed)[0][0]) > 50,
                                    fights=fights(d / f"{arm}-{seed}.trace.jsonl.gz")) for arm in ARMS}
    rng = np.random.default_rng(20261110)
    res = dict(seeds_replayed=len(where), seeds_analysed=len(data),
               non_reproducing=repro_bad, verdict="REPRO_FAIL" if len(repro_bad) > 10 else "REPRO_OK")
    # 2. per fight class
    acc = defaultdict(lambda: {m: {arm: {} for arm in ARMS} for m in ("death", "hp_lost", "potions", "turns")})
    for seed, g in data.items():
        for arm in ARMS:
            for r in g[arm]["fights"]:
                c = acc[fclass(r)]
                won = bool(r["won"])
                for m, num, den in (("death", 0.0 if won else 1.0, 1.0),
                                    ("hp_lost", r["pre"]["hp"] - r["post"]["hp"] if won else 0.0, 1.0 if won else 0.0),
                                    ("potions", max(0, len(r["pre"]["potions"]) - len(r["post"]["potions"])), 1.0),
                                    ("turns", r["turns"], 1.0)):
                    x = c[m][arm].get(seed, (0.0, 0.0))
                    c[m][arm][seed] = (x[0] + num, x[1] + den)
    res["fight_class"] = {k: {m: ratio_boot(v[m], rng) for m in v} for k, v in sorted(acc.items())}
    # 3. state at entry
    ent = defaultdict(lambda: {m: {arm: {} for arm in ARMS} for m in ("hp", "hp_frac", "potions", "deck")})
    for seed, g in data.items():
        for arm in ARMS:
            nb3 = 0
            for r in g[arm]["fights"]:
                act = r["pre"]["act"]
                if act == 4:
                    k = fclass(r)
                elif r["room"] == "BOSS":
                    if act == 3:
                        nb3 += 1
                        k = f"A3 boss {nb3}"
                    else:
                        k = f"A{act} boss"
                else:
                    continue
                p = r["pre"]
                for m, v in (("hp", p["hp"]), ("hp_frac", p["hp"] / p["maxHp"]), ("potions", len(p["potions"])),
                             ("deck", len(p["deck"]))):
                    ent[k][m][arm][seed] = (float(v), 1.0)
    res["entry_state"] = {k: {m: ratio_boot(v[m], rng) for m in v} for k, v in sorted(ent.items())}
    # 4. death cause
    cause = {arm: Counter() for arm in ARMS}
    disc = {arm: Counter() for arm in ARMS}
    for seed, g in data.items():
        for arm in ARMS:
            lost = [r for r in g[arm]["fights"] if not r["won"]]
            if not g[arm]["win"] and lost:
                key = f"{fclass(lost[-1])} {lost[-1]['encounter']}"
                cause[arm][key] += 1
                if g["G16" if arm == "D" else "D"]["win"]:
                    disc[arm][fclass(lost[-1])] += 1
    res["death_cause_top"] = {arm: cause[arm].most_common(25) for arm in ARMS}
    res["death_class_discordant"] = {arm: dict(disc[arm]) for arm in ARMS}
    # 5. first divergence
    fd = defaultdict(list)
    for seed, g in data.items():
        fa, fb = g["D"]["fights"], g["G16"]["fights"]
        for ra, rb in zip(fa, fb):
            if ra["pre"] != rb["pre"]:
                break   # states already differ (should not happen before a divergent post)
            if ra["post"] != rb["post"] or ra["won"] != rb["won"]:
                ha = ra["post"]["hp"] if ra["won"] else 0
                hb = rb["post"]["hp"] if rb["won"] else 0
                fd[fclass(ra)].append((hb - ha, int(not rb["won"]) - int(not ra["won"])))
                break
    out = {}
    for k, v in sorted(fd.items()):
        a = np.array(v, float)
        idx = rng.integers(0, len(a), size=(B, len(a)))
        bh = a[idx, 0].mean(1)
        out[k] = dict(n=len(a), post_hp_diff=round(a[:, 0].mean(), 3),
                      ci95=np.percentile(bh, [2.5, 97.5]).round(3).tolist(), death_diff=round(a[:, 1].mean(), 4))
    res["first_divergence"] = out
    return res


def self_test():
    r = {"pre": {"act": 1, "hp": 50}, "encounter": "JAW_WORM", "room": "NORMAL"}
    assert fclass(r) == "A1 NORMAL"
    assert fclass({"pre": {"act": 4}, "encounter": "THE_HEART", "room": "BOSS"}) == "A4 Heart"
    ps = {"D": {1: (10.0, 2.0), 2: (0.0, 1.0)}, "G16": {1: (3.0, 2.0), 2: (3.0, 1.0)}}
    x = ratio_boot(ps, np.random.default_rng(0))
    assert abs(x["D"] - 10 / 3) < 1e-3 and abs(x["G16"] - 2.0) < 1e-3
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    res = analyse(sys.argv[1], sys.argv[2])
    Path(sys.argv[3]).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("seeds_replayed", "seeds_analysed", "verdict")}), len(res["non_reproducing"]))
