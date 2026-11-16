#!/usr/bin/env python3
"""Order dominance pilot analysis (#1057, PREREG.md).

usage: analyze.py NEW_UNITS_DIR REF_UNITS_DIR OUT.json [--boot 10000]

NEW_UNITS_DIR: extracted pilot units (natural-<seed>.jsonl.gz + .done, any depth); REF_UNITS_DIR: the same for §797
(budget_ladder_roots_20261112). Only rc 0 units count. Every pick is scored as in §797: loss = Q_ref(best) -
Q_ref(pick), Q_ref the played 16k tree's max-backed Q (edges[].qBacked), best its maximum over visited edges.
"""
import argparse
import collections
import glob
import gzip
import json
import os
import re

import numpy as np

P1 = [1000, 2000, 4000, 8000, 16000]
SLOT = {b: i + 1 for i, b in enumerate(P1)}
SEEDS = range(111980000, 111980256)


def units(d):
    out = {}
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


def group(r):
    enc, room = r["encounter"], r["room"]
    if enc == "THE_HEART":
        return "heart"
    if enc == "SHIELD_AND_SPEAR":
        return "act4_elite"
    return {"BOSS": "boss", "ELITE": "elite"}.get(room, "hallway")


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
    ap.add_argument("--boot", type=int, default=10000)
    a = ap.parse_args()
    new_u, ref_u = units(a.new), units(a.ref)
    drops = collections.Counter()
    sentinel_bad, recs, audit = [], [], collections.defaultdict(lambda: collections.Counter())
    pairs = []
    dom_budgets = None
    for seed in sorted(new_u):
        if seed not in ref_u:
            drops["no_ref_unit"] += 1
            continue
        nr, rr = roots(new_u[seed]), roots(ref_u[seed])
        if set(nr) != set(rr) or any(nr[k]["chosen"] != rr[k]["chosen"] for k in nr):
            sentinel_bad.append(seed)
            continue
        keys = [k for k, r in nr.items() if r.get("mainCpu", -1) > 0 and rr[k].get("mainCpu", -1) > 0]
        main_new, main_ref = sum(nr[k]["mainCpu"] for k in keys), sum(rr[k]["mainCpu"] for k in keys)
        scale = main_new / main_ref if main_ref > 0 else 1.0
        for k, r in nr.items():
            g = group(r)
            au = r.get("domAudit")
            if au:
                c = audit[g]
                c["roots"] += 1
                c["rootsWithDominated"] += au["dominated"] > 0
                for f in ("nodes", "guarded", "tests", "dominated", "domVisits", "rootSims", "depth1Nodes",
                          "depth1Dominated"):
                    c[f] += au[f]
                c["auditSeconds"] += au["seconds"]
                for v, q, dv, dq in au["pairs"]:
                    pairs.append((seed, g, v, q, dv, dq))
            lad = [e for e in r.get("ladder", []) if e.get("dominance")]
            if not lad:
                continue
            qb = [e.get("qBacked") for e in r["edges"]]
            vis = [e.get("visits", 0) for e in r["edges"]]
            finite = [q for q, v in zip(qb, vis) if q is not None and v > 0]
            if not finite:
                drops["no_q"] += 1
                continue
            best = max(finite)
            loss, cpu, dom, ok = {}, {}, {}, True
            for e in lad:
                ed = e["edge"]
                if ed < 0 or qb[ed] is None or vis[ed] <= 0:
                    ok = False; drops["pick_dom_%d" % e["budget"]] += 1; break
                arm = "dom:%d" % e["budget"]
                loss[arm], cpu[arm] = best - qb[ed], e["cpu"]
                dom[arm] = (e["domNodes"], e["domGuarded"], e["domTests"], e["domPruned"], e["domSeconds"],
                            e["slot"], e["budget"])
            for e in rr[k].get("ladder", []):
                if "policy" in e or e.get("dominance"):
                    continue
                ed = e["edge"]
                if ed < 0 or qb[ed] is None or vis[ed] <= 0:
                    ok = False; drops["pick_p1_%d" % e["budget"]] += 1; break
                loss["p1:%d" % e["budget"]], cpu["p1:%d" % e["budget"]] = best - qb[ed], e["cpu"] * scale
            pri = [e.get("prior") for e in r["edges"]]
            if ok and None not in pri:
                top = int(np.argmax(pri))
                loss["prior"] = best - qb[top] if qb[top] is not None and vis[top] > 0 else np.nan
            if not ok or any("p1:%d" % b not in loss for b in P1):
                if ok:
                    drops["missing_arm"] += 1
                continue
            dom_budgets = sorted(int(x.split(":")[1]) for x in dom)
            recs.append((seed, g, loss, cpu, dom))
    dom_arms = ["dom:%d" % b for b in (dom_budgets or [])]
    arms = dom_arms + ["p1:%d" % b for b in P1]
    seeds = np.array([s for s, *_ in recs])
    groups = np.array([g for _, g, *_ in recs])
    L = {arm: np.array([l[arm] for _, _, l, _, _ in recs]) for arm in arms}
    C = {arm: np.array([c[arm] for _, _, _, c, _ in recs]) for arm in arms}
    L["prior"] = np.array([l.get("prior", np.nan) for _, _, l, _, _ in recs])
    useq = sorted(set(seeds.tolist()))
    idx_of = {s: np.flatnonzero(seeds == s) for s in useq}
    rng = np.random.default_rng(20261115)

    def stats(mask):
        def point(rows):
            m = {arm: (L[arm][rows].mean(), C[arm][rows].mean()) for arm in arms}
            h = hull([(0.0, np.nanmean(L["prior"][rows]))] + [m["p1:%d" % b][::-1] for b in P1])
            res = {}
            for arm in dom_arms:
                b = int(arm.split(":")[1])
                lc, cc = m[arm]
                pl, pc = m["p1:%d" % b] if b in P1 else (np.nan, np.nan)
                res[arm] = {"delta": lc - frontier(h, cc), "paired": lc - pl, "cpuRatio": cc / pc,
                            "r": cc / m["p1:16000"][1]}
            return m, res
        rows_all = np.flatnonzero(mask)
        if len(rows_all) == 0:
            return None
        m, res = point(rows_all)
        sub = [s for s in useq if mask[idx_of[s]].any()]
        boots = []
        for _ in range(a.boot):
            pick = rng.choice(len(sub), len(sub))
            rows = np.concatenate([idx_of[sub[i]][mask[idx_of[sub[i]]]] for i in pick])
            boots.append(point(rows)[1])
        out = {"roots": int(mask.sum()), "runs": len(sub),
               "arms": {arm: {"loss": float(v[0]), "cpu": float(v[1])} for arm, v in m.items()}}
        for arm in dom_arms:
            d = {k: float(v) for k, v in res[arm].items()}
            for k in ("delta", "paired"):
                d[k + "CI95"] = [float(np.percentile([bb[arm][k] for bb in boots], q)) for q in (2.5, 97.5)]
            out[arm] = d
        return out

    def prune_stats(rows):
        out = {}
        for arm in dom_arms:
            n = g_ = t = p = 0
            sec = 0.0
            cpu = 0.0
            for i in rows:
                dn, dg, dt, dp, ds, *_ = recs[i][4][arm]
                n += dn; g_ += dg; t += dt; p += dp; sec += ds; cpu += recs[i][3][arm]
            out[arm] = {"nodes": n, "guardedNodes": g_, "tests": t, "pruned": p,
                        "prunedPerNode": p / max(1, n - g_), "testSecondsShareOfCpu": sec / cpu if cpu else None}
        return out

    sound = {}
    for minv in (64, 256):
        sel = [(v, q, dv, dq) for _, _, v, q, dv, dq in pairs if v >= minv and dv >= minv]
        diffs = np.array([q - dq for v, q, dv, dq in sel]) if sel else np.array([])
        sound[str(minv)] = {"pairs": len(sel), "prunedQAbove": int((diffs > 0).sum()),
                            "prunedQAboveBy1": int((diffs > 1).sum()),
                            "meanDiff": float(diffs.mean()) if len(diffs) else None,
                            "medianDiff": float(np.median(diffs)) if len(diffs) else None}
    aud = {}
    for g, c in sorted(audit.items()):
        aud[g] = dict(c)
        aud[g]["dominatedPerTest"] = c["dominated"] / c["tests"] if c["tests"] else None
        aud[g]["wasteShare"] = c["domVisits"] / c["rootSims"] if c["rootSims"] else None
        aud[g]["rootsWithDominatedShare"] = c["rootsWithDominated"] / c["roots"] if c["roots"] else None
    tot = collections.Counter()
    for c in audit.values():
        tot.update(c)
    aud["all"] = dict(tot)
    if tot["rootSims"]:
        aud["all"]["wasteShare"] = tot["domVisits"] / tot["rootSims"]
        aud["all"]["dominatedPerTest"] = tot["dominated"] / max(1, tot["tests"])
        aud["all"]["rootsWithDominatedShare"] = tot["rootsWithDominated"] / tot["roots"]
    everything = np.ones(len(recs), bool)
    result = {"runsNew": len(new_u), "runsRef": len(ref_u), "sentinelBad": sentinel_bad, "drops": dict(drops),
              "rows": len(recs), "runsWithRows": len(useq), "audit": aud, "soundness": sound,
              "pruning": prune_stats(range(len(recs))),
              "all": stats(everything),
              "byGroup": {g: stats(groups == g) for g in sorted(set(groups.tolist()))},
              "pruningByGroup": {g: prune_stats(np.flatnonzero(groups == g)) for g in sorted(set(groups.tolist()))}}
    json.dump(result, open(a.out, "w"), indent=1)
    print(json.dumps({k: result[k] for k in ("rows", "runsWithRows", "sentinelBad", "drops", "soundness")}))
    print(json.dumps(result["audit"].get("all")))
    print(json.dumps(result["pruning"]))
    for arm in dom_arms:
        print(arm, json.dumps(result["all"][arm]))


if __name__ == "__main__":
    main()
