#!/usr/bin/env python3
"""Rollout prior stage 2 (issue #1053, 2026-11-15): G16-trained playout priors vs g7f_E at boss / Act-4 roots.

Copy of ../cheap_rollouts_ladder_20261113/analyze.py (§798) with this campaign's arms. Per searched multi-edge
prior-playout root of §797's 256 games, the loss of an arm = the played G16 tree's best max-backed Q among visited
edges minus the max-backed Q of the arm's pick (Silver score units, §798's definition). Arms (this campaign):
asplayed:4000 (g7f_E playouts, control), st:4000 / st:16000 (candidate V), ste:4000 (candidate X-B); from §797's
ladder of the same roots: p1:1000 ... p1:16000 (g7f_E playouts).

Primary (PREREG-stage2.md): mean paired difference st:4000 - asplayed:4000 (V) and ste:4000 - asplayed:4000 (X-B),
99 % run-clustered bootstrap CI: BETTER if the CI is below 0, WORSE if above 0, else NOT_SHOWN. Secondary:
st:16000 - p1:16000, each arm's distance to the P1 CPU frontier, per group (Act 1-2 bosses, Act 3 bosses,
Act-4 elite, Heart), fold 4 (seed % 5 == 4).

usage: analyze.py NEW_UNITS_DIR REF_UNITS_DIR OUT.json [--s798 S798_UNITS_DIR] [--boot 10000]
"""
import argparse
import collections
import glob
import gzip
import hashlib
import json
import os
import re

import numpy as np

NEW_ARMS = ["asplayed:4000", "st:4000", "ste:4000", "st:16000"]
CONTRASTS = {"V@4k": ("st:4000", "asplayed:4000"), "XB@4k": ("ste:4000", "asplayed:4000"),
             "V@16k": ("st:16000", "p1:16000"), "asplayed4k_vs_p1_4k": ("asplayed:4000", "p1:4000")}
PRIMARY = ["V@4k", "XB@4k"]
P1 = [1000, 2000, 4000, 8000, 16000]
FOLD4 = lambda seed: seed % 5 == 4  # noqa: E731
SEEDS = range(111980000, 111980256)
HERE = os.path.dirname(os.path.abspath(__file__))


def student_shas():
    out = {}
    for f in glob.glob(os.path.join(HERE, "students", "*.txt")):
        out[os.path.basename(f)] = hashlib.sha256(open(f, "rb").read()).hexdigest()
    return out


def manifest_students_ok(jsonl_path, want):
    """The run's manifest names the frozen students: generalist rp_V, all 11 encounters rp_X-B (name + sha256)."""
    mf = jsonl_path[: -len(".jsonl.gz")] + ".manifest.json"
    try:
        st = json.load(open(mf))["rolloutLadder"]["students"]
    except (OSError, KeyError, ValueError):
        return False
    g = st["generalist"]
    if os.path.basename(g["path"]) != "rp_V.txt" or g["sha256"] != want.get("rp_V.txt"):
        return False
    enc = st.get("encounters", {})
    return len(enc) == 11 and all(os.path.basename(v["path"]) == "rp_X-B.txt" and v["sha256"] == want.get("rp_X-B.txt")
                                  for v in enc.values())


def units(d):
    out = {}
    if not d:
        return out
    for done in glob.glob(os.path.join(d, "**", "natural-*.done"), recursive=True):
        if not re.search(r"\brc=0\b", open(done).read()):
            continue
        seed = int(re.search(r"natural-(\d+)\.done", done).group(1))
        path = done[: -len(".done")] + ".jsonl.gz"
        if seed in SEEDS and os.path.exists(path):
            out[seed] = path
    return out


def roots(path):
    rows = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            if '"kind":"root"' in line:
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
    ap.add_argument("--s798", default=None, help="§798 units (asplayed:4000 has the same arm index and salt)")
    ap.add_argument("--boot", type=int, default=10000)
    a = ap.parse_args()
    new_u, ref_u, s798_u = units(a.new), units(a.ref), units(a.s798)
    drops = collections.Counter()
    sentinel_bad, student_bad = [], []
    same798 = collections.Counter()
    want = student_shas()
    recs, cpu_scale = [], {}
    p1arms = ["p1:%d" % b for b in P1]
    for seed in sorted(new_u):
        if seed not in ref_u:
            drops["no_ref_unit"] += 1
            continue
        if not manifest_students_ok(new_u[seed], want):
            student_bad.append(seed)
            continue
        nr, rr = roots(new_u[seed]), roots(ref_u[seed])
        if set(nr) != set(rr) or any(nr[k]["chosen"] != rr[k]["chosen"] for k in nr):
            sentinel_bad.append(seed)
            continue
        s7 = roots(s798_u[seed]) if seed in s798_u else {}
        keys = [k for k, r in nr.items() if r.get("mainCpu", -1) > 0 and rr[k].get("mainCpu", -1) > 0]
        main_new = sum(nr[k]["mainCpu"] for k in keys)
        main_ref = sum(rr[k]["mainCpu"] for k in keys)
        scale = main_new / main_ref if main_ref > 0 else 1.0
        cpu_scale[seed] = scale
        for k, r in nr.items():
            lad = [e for e in r.get("ladder", []) if "policy" in e]
            if not lad:
                continue
            if k in s7:
                old = {e["policy"]: e["edge"] for e in s7[k].get("ladder", []) if "policy" in e}
                mine = {e["policy"]: e["edge"] for e in lad}
                if "asplayed:4000" in old and "asplayed:4000" in mine:
                    same798["same" if old["asplayed:4000"] == mine["asplayed:4000"] else "diff"] += 1
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
            for e in ref.get("ladder", []) if ok else []:
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
            if not ok or any(arm not in loss for arm in NEW_ARMS + p1arms):
                if ok:
                    drops["missing_arm"] += 1
                continue
            recs.append((seed, group(r["encounter"], r["act"]), r["encounter"], loss, cpu))
    arms = NEW_ARMS + p1arms
    seeds = np.array([x[0] for x in recs])
    groups = np.array([x[1] for x in recs])
    encs = np.array([x[2] for x in recs])
    L = {arm: np.array([x[3][arm] for x in recs]) for arm in arms}
    C = {arm: np.array([x[4][arm] for x in recs]) for arm in arms}
    L["prior"] = np.array([x[3].get("prior", np.nan) for x in recs])
    useq = sorted(set(seeds.tolist()))
    idx_of = {s: np.flatnonzero(seeds == s) for s in useq}
    rng = np.random.default_rng(20261115)

    def point(rows):
        m = {arm: (float(L[arm][rows].mean()), float(C[arm][rows].mean())) for arm in arms}
        h = hull([(0.0, float(np.nanmean(L["prior"][rows])))] + [m[p][::-1] for p in p1arms])
        res = {"gap": m["p1:1000"][0] - m["p1:16000"][0]}
        for c, (x, y) in CONTRASTS.items():
            res[c] = m[x][0] - m[y][0]
        for arm in NEW_ARMS:
            res["frontier:" + arm] = m[arm][0] - frontier(h, m[arm][1])
        return m, res

    def stats(mask):
        rows_all = np.flatnonzero(mask)
        if len(rows_all) == 0:
            return {"roots": 0}
        m, res = point(rows_all)
        sub = [s for s in useq if mask[idx_of[s]].any()]
        boots = []
        for _ in range(a.boot):
            pick = rng.choice(len(sub), len(sub))
            rows = np.concatenate([idx_of[sub[i]][mask[idx_of[sub[i]]]] for i in pick])
            boots.append(point(rows)[1])
        ci = lambda k, lo, hi: [float(np.percentile([b[k] for b in boots], q)) for q in (lo, hi)]  # noqa: E731
        out = {"roots": int(mask.sum()), "runs": len(sub),
               "arms": {arm: {"loss": v[0], "cpu": v[1]} for arm, v in m.items()},
               "cpuRatioVsP1_16k": {arm: m[arm][1] / m["p1:16000"][1] for arm in NEW_ARMS},
               "gap": float(res["gap"]), "gapCI95": ci("gap", 2.5, 97.5)}
        for c in CONTRASTS:
            d = {"delta": float(res[c]), "CI99": ci(c, 0.5, 99.5), "CI95": ci(c, 2.5, 97.5)}
            d["label"] = "BETTER" if d["CI99"][1] < 0 else "WORSE" if d["CI99"][0] > 0 else "NOT_SHOWN"
            out[c] = d
        for arm in NEW_ARMS:
            k = "frontier:" + arm
            out[k] = {"delta": float(res[k]), "CI99": ci(k, 0.5, 99.5)}
        return out

    missing = [s for s in SEEDS if s not in new_u or s not in ref_u]
    n_drop = len(missing) + len(sentinel_bad) + len(student_bad)
    result = {"runsNew": len(new_u), "runsRef": len(ref_u), "missingOrFailed": missing, "sentinelBad": sentinel_bad,
              "studentManifestBad": student_bad, "droppedRuns": n_drop, "drops": dict(drops), "rows": len(recs),
              "runsWithRows": len(useq), "asplayed4000SameAs798": dict(same798),
              "cpuScaleMedian": float(np.median(list(cpu_scale.values()))) if cpu_scale else None}
    result["status"] = "INVALID" if len(sentinel_bad) > 8 else "INCOMPLETE" if n_drop > 20 else "OK"
    result["all"] = stats(np.ones(len(recs), bool))
    result["calibration"] = "OK" if result["all"].get("gapCI95", [0])[0] > 0 else "INVALID_METRIC"
    result["byGroup"] = {g: stats(groups == g) for g in sorted(set(groups.tolist()))}
    result["byEncounter"] = {e: stats(encs == e) for e in sorted(set(encs.tolist()))}
    result["fold4"] = stats(np.array([FOLD4(s) for s in seeds], bool))
    if result["status"] != "OK" or result["calibration"] != "OK":
        blocks = [result["all"], result["fold4"]] + list(result["byGroup"].values()) + list(result["byEncounter"].values())
        for block in blocks:
            for c in CONTRASTS:
                if c in block:
                    block[c]["label"] = None
    json.dump(result, open(a.out, "w"), indent=1)
    print(json.dumps({k: result[k] for k in ("status", "calibration", "rows", "droppedRuns", "drops", "sentinelBad",
                                             "studentManifestBad", "asplayed4000SameAs798")}))
    for c in CONTRASTS:
        print(c, json.dumps(result["all"].get(c)))


if __name__ == "__main__":
    main()
