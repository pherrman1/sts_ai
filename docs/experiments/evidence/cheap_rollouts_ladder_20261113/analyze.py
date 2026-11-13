#!/usr/bin/env python3
"""Cheap rollouts stage 2 analysis (PREREG.md).

usage: analyze.py NEW_UNITS_DIR REF_UNITS_DIR OUT.json [--boot 10000]

NEW_UNITS_DIR / REF_UNITS_DIR: extracted unit dirs (any depth) holding natural-<seed>.jsonl.gz and .done files of this
campaign and of §797 (budget_ladder_roots_20261112). Only rc 0 units count.
"""
import argparse
import collections
import glob
import gzip
import json
import os
import re

import numpy as np

CANDIDATES = ["tt:16000", "ft1:16000", "st:16000", "sttt:16000", "ste:16000"]
NEW_ARMS = ["asplayed:4000", "greedy:16000", "greedy:64000"] + CANDIDATES
P1 = [1000, 2000, 4000, 8000, 16000]
FOLD4 = lambda seed: seed % 5 == 4  # noqa: E731


def units(d):
    out = {}
    for done in glob.glob(os.path.join(d, "**", "natural-*.done"), recursive=True):
        line = open(done).read()
        if not re.search(r"\brc=0\b", line):
            continue
        seed = int(re.search(r"natural-(\d+)\.done", done).group(1))
        path = done[: -len(".done")] + ".jsonl.gz"
        if os.path.exists(path):
            out[seed] = path
    return out


def roots(path):
    rows = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            if '"kind":"root"' not in line:
                continue
            r = json.loads(line)
            rows[(r["fight"], r["decision"])] = r
    return rows


def group(enc, act):
    if enc == "THE_HEART":
        return "heart"
    if enc == "SHIELD_AND_SPEAR":
        return "act4_elite"
    return "act3_boss" if int(act) == 3 else "act12_boss"


def hull(points):
    """Lower convex hull of (cpu, loss) points sorted by cpu, starting at (0, loss0)."""
    pts = sorted(points)
    h = []
    for p in pts:
        while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
            h.pop()
        h.append(p)
    return h


def frontier(h, c):
    if c <= h[0][0]:
        return h[0][1]
    for a, b in zip(h, h[1:]):
        if c <= b[0]:
            return a[1] + (b[1] - a[1]) * (c - a[0]) / (b[0] - a[0])
    return h[-1][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("new"); ap.add_argument("ref"); ap.add_argument("out")
    ap.add_argument("--boot", type=int, default=10000)
    a = ap.parse_args()
    new_u, ref_u = units(a.new), units(a.ref)
    drops = collections.Counter()
    sentinel_bad = []
    recs = []   # per root: seed, group, loss[arm], cpu[arm]
    cpu_scale = {}
    for seed in sorted(new_u):
        if seed not in ref_u:
            drops["no_ref_unit"] += 1
            continue
        nr, rr = roots(new_u[seed]), roots(ref_u[seed])
        if set(nr) != set(rr) or any(nr[k]["chosen"] != rr[k]["chosen"] for k in nr):
            sentinel_bad.append(seed)
            continue
        main_new = sum(r["mainCpu"] for r in nr.values() if r.get("mainCpu", -1) > 0)
        main_ref = sum(r["mainCpu"] for r in rr.values() if r.get("mainCpu", -1) > 0)
        scale = main_new / main_ref if main_ref > 0 else 1.0
        cpu_scale[seed] = scale
        for k, r in nr.items():
            lad = [e for e in r.get("ladder", []) if "policy" in e]
            if not lad:
                continue
            ref = rr[k]
            qb = [e.get("qBacked") for e in r["edges"]]
            vis = [e.get("visits", 0) for e in r["edges"]]
            finite = [q for q, v in zip(qb, vis) if q is not None and v > 0]
            if not finite:
                drops["no_q"] += 1
                continue
            best = max(finite)
            loss, cpu, ok = {}, {}, True
            for e in lad:
                ed = e["edge"]
                if ed < 0 or qb[ed] is None or vis[ed] <= 0:
                    ok = False; drops["pick_" + e["policy"]] += 1; break
                loss[e["policy"]] = best - qb[ed]; cpu[e["policy"]] = e["cpu"]
            for e in ref.get("ladder", []):
                if "policy" in e:
                    continue
                ed = e["edge"]
                if ed < 0 or qb[ed] is None or vis[ed] <= 0:
                    ok = False; drops["pick_p1_%d" % e["budget"]] += 1; break
                loss["p1:%d" % e["budget"]] = best - qb[ed]; cpu["p1:%d" % e["budget"]] = e["cpu"] * scale
            pri = [e.get("prior") for e in r["edges"]]
            if ok and None not in pri:
                top = int(np.argmax(pri))
                loss["prior"] = best - qb[top] if qb[top] is not None and vis[top] > 0 else np.nan
                cpu["prior"] = 0.0
            if not ok or any(arm not in loss for arm in NEW_ARMS + ["p1:%d" % b for b in P1]):
                if ok:
                    drops["missing_arm"] += 1
                continue
            recs.append((seed, group(r["encounter"], r["act"]), loss, cpu))
    arms = NEW_ARMS + ["p1:%d" % b for b in P1]
    seeds = np.array([s for s, _, _, _ in recs])
    groups = np.array([g for _, g, _, _ in recs])
    L = {arm: np.array([l[arm] for _, _, l, _ in recs]) for arm in arms}
    C = {arm: np.array([c[arm] for _, _, _, c in recs]) for arm in arms}
    L["prior"] = np.array([l.get("prior", np.nan) for _, _, l, _ in recs])
    useq = sorted(set(seeds))
    idx_of = {s: np.flatnonzero(seeds == s) for s in useq}
    rng = np.random.default_rng(20261113)

    def stats(mask):
        def point(rows):
            m = {arm: (L[arm][rows].mean(), C[arm][rows].mean()) for arm in arms}
            l0 = np.nanmean(L["prior"][rows])
            h = hull([(0.0, l0)] + [m["p1:%d" % b][::-1] for b in P1])
            gap = m["greedy:16000"][0] - m["p1:16000"][0]
            res = {"gap": gap}
            for c in CANDIDATES + ["greedy:64000", "asplayed:4000"]:
                lc, cc = m[c]
                res[c] = {"delta": lc - frontier(h, cc), "r": cc / m["p1:16000"][1],
                          "vs16k": lc - m["p1:16000"][0], "g": (lc - m["p1:16000"][0]) / gap if gap else np.nan}
            return m, res
        rows_all = np.flatnonzero(mask)
        m, res = point(rows_all)
        sub = [s for s in useq if mask[idx_of[s]].any()]
        boots = []
        for _ in range(a.boot):
            pick = rng.choice(len(sub), len(sub))
            rows = np.concatenate([idx_of[sub[i]][mask[idx_of[sub[i]]]] for i in pick])
            boots.append(point(rows)[1])
        out = {"roots": int(mask.sum()), "runs": len(sub),
               "arms": {arm: {"loss": float(v[0]), "cpu": float(v[1])} for arm, v in m.items()},
               "gap": float(res["gap"]),
               "gapCI95": [float(np.percentile([b["gap"] for b in boots], q)) for q in (2.5, 97.5)]}
        for c in CANDIDATES + ["greedy:64000", "asplayed:4000"]:
            d = {k: float(res[c][k]) for k in ("delta", "r", "vs16k", "g")}
            for k in ("delta", "vs16k"):
                d[k + "CI99"] = [float(np.percentile([b[c][k] for b in boots], q)) for q in (0.5, 99.5)]
            up = d["vs16kCI99"][1]
            d["label"] = ("GATE_CANDIDATE" if d["r"] <= 0.35 and up <= 0.25 * res["gap"] and d["deltaCI99"][1] < 0
                          else "CHEAPER_EQUAL" if d["deltaCI99"][1] < 0 else "NOT_SHOWN")
            out[c] = d
        return out

    everything = np.ones(len(recs), bool)
    result = {"runsNew": len(new_u), "runsRef": len(ref_u), "sentinelBad": sentinel_bad, "drops": dict(drops),
              "rows": len(recs), "cpuScaleMedian": float(np.median(list(cpu_scale.values()))) if cpu_scale else None}
    n_drop = 256 - len(set(seeds))
    result["status"] = ("INVALID" if len(sentinel_bad) > 8 else "INCOMPLETE" if n_drop > 20 else "OK")
    result["all"] = stats(everything)
    result["calibration"] = "OK" if result["all"]["gapCI95"][0] > 0 else "INVALID_METRIC"
    result["byGroup"] = {g: stats(groups == g) for g in sorted(set(groups))}
    result["fold4"] = stats(np.array([FOLD4(s) for s in seeds]))
    json.dump(result, open(a.out, "w"), indent=1)
    print(json.dumps({k: result[k] for k in ("status", "calibration", "rows", "drops", "sentinelBad")}))
    for c in CANDIDATES + ["greedy:64000", "asplayed:4000"]:
        print(c, json.dumps(result["all"][c]))


if __name__ == "__main__":
    main()
