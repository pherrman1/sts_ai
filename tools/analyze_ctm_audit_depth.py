#!/usr/bin/env python3
"""Re-slice #884 / §709 CTM-audit rows by imagined-fight index x act (no new compute).

Inputs are the STS_OOC_CTM_AUDIT rows of §709 (share ctm-audit-884/ctm-audit-884-replays-98e7d0c.tar.gz,
cohort/A-*.audit.jsonl). Each imagined combat carries `combat`, its index inside one leaf rollout (0 = the first fight
after the root action), the act and room of the fight, the CTM forecast of its entry (pDeath, hpWinMean) and, in the
"silver" arm, production Silver's drawn outcome.

Reports
  * calibration (silver arm): CTM death forecast vs Silver outcome by act x room x index, and HP-given-win bias;
  * trend: slope of (observed - forecast) deaths over index within each act (elite+boss and boss only);
  * arm drift: entry HP / potions / CTM forecast at the same act x room x index, CTM arm minus Silver arm (both arms
    share the leaf policy and streams; only who plays the earlier imagined fights differs);
  * rho: per-rollout correlation of the leaf value between arms (same root, action, stream), raw and within
    root-action, by root act.
CIs: percentile bootstrap over the 16 seeds (fights and roots of one game are correlated), 2,000 draws, seed 709.

usage: analyze_ctm_audit_depth.py OUT.json AUDIT.jsonl [AUDIT.jsonl ...]
"""
import itertools
import json
import math
import random
import sys
from collections import defaultdict

ROOMS = {2: "event", 3: "elite", 4: "monster", 6: "boss"}
REPS = 2000


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def load(paths):
    roots = []
    for p in paths:
        with open(p) as f:
            for line in f:
                r = json.loads(line)
                a = r.get("audit") or {}
                arms = a.get("arms") or {}
                if "error" in a or "ctm" not in arms or "silver" not in arms:
                    continue
                roots.append(r)
    return roots


def fights(roots):
    out = []
    for r in roots:
        for arm, data in r["audit"]["arms"].items():
            for c in data.get("combats", []):
                if not c.get("ctmSupported") or c.get("outcome") not in ("death", "victory"):
                    continue
                out.append({"seed": r["seed"], "rootAct": r["act"], "arm": arm, "act": c["act"],
                            "room": ROOMS.get(c["room"], str(c["room"])), "idx": min(c["combat"], 3),
                            "y": 1.0 if c["outcome"] == "death" else 0.0,
                            "p": min(max(float(c["pDeath"]), 1e-6), 1 - 1e-6), "hp": c["hp"], "maxHp": c["maxHp"],
                            "potions": c.get("potions", 0), "deck": c.get("deck"),
                            "postHp": c.get("postHp"), "hpWinMean": c.get("hpWinMean")})
    return out


def boot(seeds, stat, rng):
    """stat(list_of_seeds_with_multiplicity) -> float; returns point, lo, hi."""
    point = stat(seeds)
    vals = []
    for _ in range(REPS):
        s = [rng.choice(seeds) for _ in seeds]
        v = stat(s)
        if v == v:
            vals.append(v)
    vals.sort()
    if not vals:
        return point, float("nan"), float("nan")
    return point, vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def by_seed(rows):
    d = defaultdict(list)
    for x in rows:
        d[x["seed"]].append(x)
    return d


def pooled(groups, seeds, f):
    rows = [x for s in seeds for x in groups.get(s, [])]
    return f(rows)


def calib_cell(rows, rng):
    g = by_seed(rows)
    seeds = sorted(g)
    n = len(rows)
    obs = mean([x["y"] for x in rows])
    pred = mean([x["p"] for x in rows])
    diff = boot(seeds, lambda s: pooled(g, s, lambda r: mean([x["y"] - x["p"] for x in r])), rng)
    ratio = boot(seeds, lambda s: pooled(g, s, lambda r: (mean([x["p"] for x in r]) / mean([x["y"] for x in r]))
                                         if r and mean([x["y"] for x in r]) > 0 else float("nan")), rng)
    wins = [x for x in rows if x["y"] == 0.0 and x["postHp"] is not None]
    hpb = mean([x["postHp"] - x["hpWinMean"] for x in wins])
    return {"n": n, "deaths": int(sum(x["y"] for x in rows)), "forecastDeaths": sum(x["p"] for x in rows),
            "observed": obs, "predicted": pred, "obsMinusPred": diff, "predOverObs": ratio,
            "hpWinBiasSilverMinusCtm": hpb}


def slope(rows):
    xs = [x["idx"] for x in rows]
    es = [x["y"] - x["p"] for x in rows]
    if len(set(xs)) < 2:
        return float("nan")
    mx, me = mean(xs), mean(es)
    sxx = sum((a - mx) ** 2 for a in xs)
    return sum((a - mx) * (b - me) for a, b in zip(xs, es)) / sxx


def corr(a, b):
    if len(a) < 3:
        return float("nan")
    ma, mb = mean(a), mean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def rho_pairs(roots):
    """Per seed: list of (rootAct, rootKey, ctmValue, silverValue)."""
    out = defaultdict(list)
    for r in roots:
        arms = r["audit"]["arms"]
        for act_id, cv in arms["ctm"]["values"].items():
            sv = arms["silver"]["values"].get(act_id)
            if not sv:
                continue
            for i, (a, b) in enumerate(zip(cv, sv)):
                if a.get("value") is None or b.get("value") is None:
                    continue
                out[r["seed"]].append((r["act"], (r["seed"], r["decisionIndex"], act_id), a["value"], b["value"]))
    return out


def rho_stats(pairs):
    raw = corr([p[2] for p in pairs], [p[3] for p in pairs])
    g = defaultdict(list)
    for p in pairs:
        g[p[1]].append(p)
    a, b = [], []
    for key, ps in g.items():
        ma, mb = mean([p[2] for p in ps]), mean([p[3] for p in ps])
        a += [p[2] - ma for p in ps]
        b += [p[3] - mb for p in ps]
    return raw, corr(a, b)


def main():
    out_path, paths = sys.argv[1], sys.argv[2:]
    rng = random.Random(709)
    roots = load(paths)
    fs = fights(roots)
    sil = [x for x in fs if x["arm"] == "silver"]
    ctm = [x for x in fs if x["arm"] == "ctm"]
    rep = {"schema": "ctm-audit-depth-v1", "inputs": paths, "roots": len(roots), "fightsSilver": len(sil),
           "fightsCtm": len(ctm), "bootstrap": {"unit": "seed", "reps": REPS, "rngSeed": 709}}

    cells = {}
    for act in (1, 2, 3, 4):
        for room in ("monster", "elite", "boss", "event", "elite+boss"):
            rooms = ("elite", "boss") if room == "elite+boss" else (room,)
            for idx in ("0", "1", "2", "3+", "0-1", "2-3+", "all"):
                ids = {"0": {0}, "1": {1}, "2": {2}, "3+": {3}, "0-1": {0, 1}, "2-3+": {2, 3},
                       "all": {0, 1, 2, 3}}[idx]
                rows = [x for x in sil if x["act"] == act and x["room"] in rooms and x["idx"] in ids]
                if len(rows) >= 20:
                    cells[f"act{act}:{room}:idx{idx}"] = calib_cell(rows, rng)
    for room in ("elite", "boss", "elite+boss"):
        rooms = ("elite", "boss") if room == "elite+boss" else (room,)
        for idx, ids in (("0-1", {0, 1}), ("2-3+", {2, 3}), ("all", {0, 1, 2, 3})):
            rows = [x for x in sil if x["act"] in (2, 3) and x["room"] in rooms and x["idx"] in ids]
            cells[f"act23:{room}:idx{idx}"] = calib_cell(rows, rng)
    rep["calibration"] = cells

    # Acts 2-3 bosses and elites: death calibration by forecast bin, and leave-one-seed-out pred/obs (one dying
    # game can carry most boss deaths).
    bins = [0, 0.05, 0.1, 0.2, 0.5, 1.0001]
    extra = {}
    for room in ("boss", "elite"):
        rows = [x for x in sil if x["act"] in (2, 3) and x["room"] == room]
        extra[f"act23:{room}:byForecastBin"] = [
            dict(calib_cell([x for x in rows if lo <= x["p"] < hi], rng), bin=[lo, min(hi, 1)])
            for lo, hi in zip(bins, bins[1:]) if any(lo <= x["p"] < hi for x in rows)]
        loo = {}
        for s in sorted(set(x["seed"] for x in rows)):
            r = [x for x in rows if x["seed"] != s]
            o = sum(x["y"] for x in r)
            loo[str(s)] = {"n": len(r), "forecastDeaths": sum(x["p"] for x in r), "deaths": int(o)}
        extra[f"act23:{room}:leaveOneSeedOut"] = loo
        # How often does a 4-game sample (the 2026-10-31 diagnostic's size) show a large over-forecast by chance?
        g = by_seed(rows)
        tot = ge2 = ge25 = 0
        for comb in itertools.combinations(sorted(g), 4):
            r = [x for sd in comb for x in g[sd]]
            p_, o_ = sum(x["p"] for x in r), sum(x["y"] for x in r)
            tot += 1
            ge2 += o_ == 0 or p_ / o_ >= 2.0
            ge25 += o_ == 0 or p_ / o_ >= 2.5
        extra[f"act23:{room}:fourSeedSubsets"] = {"subsets": tot, "predOverObsGe2": ge2, "predOverObsGe2.5": ge25,
                                                 "zeroDeathCountsAsExceeding": True}
    rep["acts23Detail"] = extra

    trend = {}
    for label, acts in (("act1", (1,)), ("act2", (2,)), ("act3", (3,)), ("act23", (2, 3)), ("acts1-3", (1, 2, 3))):
        for room in ("boss", "elite+boss"):
            rooms = ("elite", "boss") if room == "elite+boss" else (room,)
            rows = [x for x in sil if x["act"] in acts and x["room"] in rooms]
            g = by_seed(rows)
            # Within-act slope: demean nothing extra; acts pooled only when requested (act23, acts1-3 use act FE).
            def st(s, acts=acts):
                r = [x for sd in s for x in g.get(sd, [])]
                if len(acts) == 1:
                    return slope(r)
                num = den = 0.0
                for a in acts:
                    ra = [x for x in r if x["act"] == a]
                    if len(set(x["idx"] for x in ra)) < 2:
                        continue
                    mx = mean([x["idx"] for x in ra])
                    me = mean([x["y"] - x["p"] for x in ra])
                    num += sum((x["idx"] - mx) * (x["y"] - x["p"] - me) for x in ra)
                    den += sum((x["idx"] - mx) ** 2 for x in ra)
                return num / den if den > 0 else float("nan")
            trend[f"{label}:{room}"] = {"n": len(rows), "slopeObsMinusPredPerIndex": boot(sorted(g), st, rng)}
    rep["trend"] = trend

    drift = {}
    for act in (1, 2, 3):
        for room in ("elite", "boss"):
            for idx in (0, 1, 2, 3):
                cs = [x for x in ctm if x["act"] == act and x["room"] == room and x["idx"] == idx]
                ss = [x for x in sil if x["act"] == act and x["room"] == room and x["idx"] == idx]
                if len(cs) < 20 or len(ss) < 20:
                    continue
                cell = {"nCtm": len(cs), "nSilver": len(ss)}
                for k in ("hp", "potions", "p", "deck"):
                    cell[k] = {"ctm": mean([x[k] for x in cs]), "silver": mean([x[k] for x in ss])}
                gc, gs = by_seed(cs), by_seed(ss)
                seeds = sorted(set(gc) | set(gs))
                for k in ("potions", "p", "hp"):
                    cell[k]["ctmMinusSilver"] = boot(
                        seeds, lambda s, k=k: pooled(gc, s, lambda r: mean([x[k] for x in r]))
                        - pooled(gs, s, lambda r: mean([x[k] for x in r])), rng)
                drift[f"act{act}:{room}:idx{idx}"] = cell
    rep["armDrift"] = drift

    pairs = rho_pairs(roots)
    rho = {}
    for label, acts in (("all", (1, 2, 3)), ("act1", (1,)), ("act2", (2,)), ("act3", (3,))):
        g = {s: [p for p in ps if p[0] in acts] for s, ps in pairs.items()}
        seeds = sorted(s for s in g if g[s])
        allp = [p for s in seeds for p in g[s]]
        rw = boot(seeds, lambda s: rho_stats([p for sd in s for p in g[sd]])[0], rng)
        wr = boot(seeds, lambda s: rho_stats([p for sd in s for p in g[sd]])[1], rng)
        rho[label] = {"n": len(allp), "raw": rw, "withinRootAction": wr}
    rep["rho"] = rho

    with open(out_path, "w") as f:
        json.dump(rep, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
