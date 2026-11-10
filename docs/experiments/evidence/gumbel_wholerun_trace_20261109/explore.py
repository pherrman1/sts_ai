#!/usr/bin/env python3
"""Exploratory follow-ups to analyze.py (written after the data, NOT pre-registered; descriptive only).

    python3 explore.py OUT_ROOT explore.json [battles.csv.gz]

OUT_ROOT as for analyze.py (all 1,024 seeds reproduced §775, so no seed filter is applied here).
1. Funnel: runs reaching and winning each boss stage per arm, and a split of the Heart-kill difference into
   "more runs reach the Heart" (reach_G16 - reach_D at D's Heart win rate) and "more Heart fights won".
2. Entry HP versus boss death: within each arm, the least-squares slope of death (0/1) on entry HP at each boss
   stage, and the death change that D's slope predicts from G16's mean entry-HP shift, next to the observed change.
   Seed bootstrap (5,000 resamples, seed 20261111) for the observed change and the predicted one.
3. Death rate per boss encounter (fights, deaths per arm).
4. HP and potions per run by room type at D's fight counts: per-fight G16 - D (analyze.py's numbers) times D's
   fights per run, summed over acts 1-3.
5. Optional: one CSV row per traced fight (both arms, all seeds) for later analyses without the share tars.
"""
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import ARMS, dead, fclass, fights  # noqa: E402

STAGES = ("A1 boss", "A2 boss", "A3 boss 1", "A3 boss 2", "A4 Shield and Spear", "A4 Heart")


def stage(r, nb3):
    act = r["pre"]["act"]
    if act == 4:
        return fclass(r)
    if r["room"] == "BOSS":
        return f"A3 boss {nb3}" if act == 3 else f"A{act} boss"
    return None


def load(out_root):
    data = {}
    for done in Path(out_root).glob("*/*.done"):
        arm, seed = done.stem.rsplit("-", 1)
        if arm in ARMS:
            data.setdefault(int(seed), {})[arm] = fights(done.parent / f"{arm}-{seed}.trace.jsonl.gz")
    return {s: g for s, g in data.items() if len(g) == 2}


COLS = ("seed", "arm", "fight", "act", "floor", "room", "encounter", "won", "escaped", "turns", "hp_pre", "hp_post",
        "maxhp_pre", "maxhp_post", "potions_pre", "potions_post", "deck_pre", "gold_pre")


def write_battles(data, path):
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for s in sorted(data):
            for arm in ARMS:
                for r in data[s][arm]:
                    p, q = r["pre"], r["post"]
                    w.writerow((s, arm, r.get("fight"), p["act"], p.get("floor"), r["room"], r["encounter"],
                                int(bool(r["won"])), int(bool(r.get("escaped", False))), r["turns"], p["hp"], q["hp"],
                                p["maxHp"], q["maxHp"], len(p["potions"]), len(q["potions"]), len(p["deck"]),
                                p.get("gold")))


def main(out_root, out_json, battles=None):
    data = load(out_root)
    if battles:
        write_battles(data, battles)
    seeds = sorted(data)
    # per seed, per arm, per stage: (entry hp, died) or absent
    st = {arm: {s: {} for s in seeds} for arm in ARMS}
    enc = defaultdict(lambda: {arm: [0, 0] for arm in ARMS})
    won_heart = {arm: {} for arm in ARMS}
    for s in seeds:
        for arm in ARMS:
            nb3 = 0
            won_heart[arm][s] = False
            for r in data[s][arm]:
                if r["pre"]["act"] == 3 and r["room"] == "BOSS":
                    nb3 += 1
                k = stage(r, nb3)
                if k is None:
                    continue
                st[arm][s][k] = (r["pre"]["hp"], int(dead(r)))
                if r["room"] == "BOSS" or r["pre"]["act"] == 4:
                    enc[r["encounter"]][arm][0] += 1
                    enc[r["encounter"]][arm][1] += int(dead(r))
                if k == "A4 Heart" and r["won"]:
                    won_heart[arm][s] = True
    res = {"seeds": len(seeds)}
    # 1. funnel
    fun = {}
    for k in STAGES:
        fun[k] = {arm: dict(reach=sum(k in st[arm][s] for s in seeds),
                            win=sum(k in st[arm][s] and not st[arm][s][k][1] for s in seeds)) for arm in ARMS}
    res["funnel"] = fun
    h = fun["A4 Heart"]
    pd = h["D"]["win"] / h["D"]["reach"]
    res["heart_split"] = dict(total=h["G16"]["win"] - h["D"]["win"],
                              from_reach=round((h["G16"]["reach"] - h["D"]["reach"]) * pd, 1),
                              from_conversion=round(h["G16"]["reach"] * (h["G16"]["win"] / h["G16"]["reach"] - pd), 1))
    # 2. entry HP vs death
    rng = np.random.default_rng(20261111)
    idx = rng.integers(0, len(seeds), size=(5000, len(seeds)))
    out = {}
    for k in STAGES:
        arr = {}
        for arm in ARMS:
            hp = np.array([st[arm][s][k][0] if k in st[arm][s] else np.nan for s in seeds])
            dd = np.array([st[arm][s][k][1] if k in st[arm][s] else np.nan for s in seeds])
            arr[arm] = (hp, dd)

        def stats(ix):
            o = {}
            for arm in ARMS:
                hp, dd = arr[arm][0][ix], arr[arm][1][ix]
                m = ~np.isnan(hp)
                x, y = hp[m], dd[m]
                slope = np.polyfit(x, y, 1)[0] if len(x) > 2 and x.std() > 0 else np.nan
                o[arm] = (x.mean(), y.mean(), slope)
            obs = o["G16"][1] - o["D"][1]
            pred = o["D"][2] * (o["G16"][0] - o["D"][0])
            return obs, pred, o
        obs, pred, o = stats(np.arange(len(seeds)))
        bo = np.array([stats(i)[:2] for i in idx])
        out[k] = dict(n={arm: int((~np.isnan(arr[arm][0])).sum()) for arm in ARMS},
                      entry_hp={arm: round(o[arm][0], 2) for arm in ARMS},
                      death={arm: round(o[arm][1], 4) for arm in ARMS},
                      slope_pp_per_hp={arm: round(100 * o[arm][2], 3) for arm in ARMS},
                      observed_death_diff_pp=round(100 * obs, 2),
                      observed_ci95=np.percentile(100 * bo[:, 0], [2.5, 97.5]).round(2).tolist(),
                      predicted_from_entry_hp_pp=round(100 * pred, 2),
                      predicted_ci95=np.percentile(100 * bo[:, 1], [2.5, 97.5]).round(2).tolist())
    res["entry_hp_vs_death"] = out
    # 3. per encounter
    res["boss_encounters"] = {e: {arm: dict(fights=v[arm][0], deaths=v[arm][1],
                                            rate=round(v[arm][1] / v[arm][0], 4) if v[arm][0] else None) for arm in ARMS}
                              for e, v in sorted(enc.items())}
    # 4. per-run totals by room type at D's fight counts
    per = defaultdict(lambda: {arm: [0.0, 0.0, 0.0, 0.0] for arm in ARMS})   # hp_lost_won, won, potions, fights
    for s in seeds:
        for arm in ARMS:
            for r in data[s][arm]:
                if r["pre"]["act"] == 4:
                    continue
                c = per[fclass(r)][arm]
                if r["won"]:
                    c[0] += r["pre"]["hp"] - r["post"]["hp"]
                    c[1] += 1
                c[2] += max(0, len(r["pre"]["potions"]) - len(r["post"]["potions"]))
                c[3] += 1
    tot = defaultdict(lambda: dict(hp_saved_per_run=0.0, potions_saved_per_run=0.0, d_fights_per_run=0.0))
    for k, v in per.items():
        room = k.split(" ", 1)[1]
        d, g = v["D"], v["G16"]
        hp_d, hp_g = d[0] / d[1], g[0] / g[1]
        po_d, po_g = d[2] / d[3], g[2] / g[3]
        t = tot[room]
        t["hp_saved_per_run"] += (hp_d - hp_g) * d[1] / len(seeds)
        t["potions_saved_per_run"] += (po_d - po_g) * d[3] / len(seeds)
        t["d_fights_per_run"] += d[3] / len(seeds)
    res["per_run_by_room_acts1to3"] = {k: {m: round(x, 3) for m, x in v.items()} for k, v in sorted(tot.items())}
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["heart_split"]), json.dumps(res["per_run_by_room_acts1to3"]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
