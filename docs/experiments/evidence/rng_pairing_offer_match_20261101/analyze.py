#!/usr/bin/env python3
"""Outcome correlation of §685 first-divergence pairs, split by whether the children's next offer coincides.

  analyze.py OUT CAMPAIGN_DIR...    unit tars -> OUT/pairs.csv.gz, OUT/result.json

Pairs are built exactly as s0.py extract (§685): per seed, every arm pair of valid games, first state index k whose
public record differs. The root is state k-1. "Next offer" of a child = the first combat-reward screen (screen 2)
with a non-empty card offer whose floor is strictly above the root floor (or the next act). Primary: MATCH iff both
children have one and the card lists (ids + upgrades) are identical. rho = Pearson (phi) of the Heart-kill outcomes.
CIs by bootstrap over (campaign, seed) clusters, 2,000 draws, numpy seed 0.
"""
import csv
import glob
import gzip
import io
import itertools
import json
import os
import sys
import tarfile

import numpy as np


def read_unit(path):
    games = {}
    with tarfile.open(path) as tf:
        for m in tf.getmembers():
            b = os.path.basename(m.name)
            if not b.endswith(".jsonl.gz") or b.endswith(".ctm.jsonl.gz"):
                continue
            arm = b.split("-")[0]
            rows = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(m).read()), "rt")]
            out = [x for x in rows if x["type"] == "outcome"]
            if not out or not out[-1].get("complete") or not out[-1].get("integrityPassed"):
                continue
            games[arm] = ([x for x in rows if x["type"] == "state"], out[-1])
    return games


def next_offer(states, k, root_act, root_floor, field="card"):
    for s in states[k:]:
        if (s["act"], s["floor"]) <= (root_act, root_floor):
            continue
        r = s["record"]
        if s["screen"] != 2:
            continue
        if field == "card" and r["cards_offered.cards"]:
            return (s["act"], s["floor"], tuple(r["cards_offered.cards"]), tuple(r["cards_offered.upgrades"]))
        if field == "relic" and r["relics_offered"]:
            return (s["act"], s["floor"], tuple(r["relics_offered"]))
        if field == "potion" and r["potions_offered"]:
            return (s["act"], s["floor"], tuple(r["potions_offered"]))
    return None


def extract(dirs):
    pairs = []
    for d in dirs:
        camp = os.path.basename(os.path.normpath(d))
        seen = set()
        for t in sorted(glob.glob(os.path.join(d, "units", "*.tar"))):
            seed = int(os.path.basename(t).split(".")[0])
            if seed in seen:
                continue
            seen.add(seed)
            games = read_unit(t)
            for a, b in itertools.combinations(sorted(games), 2):
                sa, sb = games[a][0], games[b][0]
                k = 0
                while k < min(len(sa), len(sb)) and sa[k]["record"] == sb[k]["record"]:
                    k += 1
                if k == min(len(sa), len(sb)):
                    continue
                root = sa[k - 1]
                p = {"campaign": camp, "seed": seed, "a": a, "b": b, "k": k, "rootAct": root["act"],
                     "rootFloor": root["floor"], "rootScreen": root["screen"],
                     "ya": int(games[a][1]["heartKilled"]), "yb": int(games[b][1]["heartKilled"]),
                     "a4a": int(games[a][1]["finalAct"] == 4), "a4b": int(games[b][1]["finalAct"] == 4)}
                for f in ("card", "relic", "potion"):
                    oa = next_offer(sa, k, root["act"], root["floor"], f)
                    ob = next_offer(sb, k, root["act"], root["floor"], f)
                    p[f + "Status"] = ("missing" if oa is None or ob is None else
                                       "match" if oa == ob else
                                       "sameFloorDiffer" if oa[:2] == ob[:2] else "otherFloor")
                    p[f + "SameFloor"] = int(oa is not None and ob is not None and oa[:2] == ob[:2])
                pairs.append(p)
        print(camp, len(seen), len(pairs), file=sys.stderr, flush=True)
    return pairs


def rho(ya, yb):
    if len(ya) < 3 or ya.std() == 0 or yb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ya, yb)[0, 1])


def summarize(pairs, mask_a, mask_b, ykey=("ya", "yb"), draws=2000):
    cl = np.array([hash((p["campaign"], p["seed"])) for p in pairs])
    ucl, inv = np.unique(cl, return_inverse=True)
    ya = np.array([p[ykey[0]] for p in pairs], float)
    yb = np.array([p[ykey[1]] for p in pairs], float)
    ma, mb = np.asarray(mask_a), np.asarray(mask_b)
    ra, rb = rho(ya[ma], yb[ma]), rho(ya[mb], yb[mb])
    rng = np.random.default_rng(0)
    idx_by = [np.flatnonzero(inv == i) for i in range(len(ucl))]
    ba, bb, bd = [], [], []
    for _ in range(draws):
        pick = np.concatenate([idx_by[i] for i in rng.integers(0, len(ucl), len(ucl))])
        x, y = rho(ya[pick][ma[pick]], yb[pick][ma[pick]]), rho(ya[pick][mb[pick]], yb[pick][mb[pick]])
        ba.append(x); bb.append(y); bd.append(x - y)
    q = lambda v: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))]
    return {"nA": int(ma.sum()), "nB": int(mb.sum()), "rhoA": ra, "ciA": q(ba), "rhoB": rb, "ciB": q(bb),
            "diff": ra - rb, "ciDiff": q(bd),
            "killA": float((ya[ma] + yb[ma]).mean() / 2), "killB": float((ya[mb] + yb[mb]).mean() / 2),
            "discordA": float((ya[ma] != yb[ma]).mean()), "discordB": float((ya[mb] != yb[mb]).mean())}


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    os.makedirs(out, exist_ok=True)
    cache = os.path.join(out, "pairs.csv.gz")
    if os.path.exists(cache):
        with gzip.open(cache, "rt") as f:
            pairs = [{k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in r.items()} for r in csv.DictReader(f)]
    else:
        pairs = extract(dirs)
        with gzip.open(cache, "wt", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(pairs[0]))
            w.writeheader()
            w.writerows(pairs)
    st = lambda f, v: np.array([p[f + "Status"] == v for p in pairs])
    res = {"pairs": len(pairs)}
    for f in ("card", "relic", "potion"):
        res[f + "Counts"] = {v: int(st(f, v).sum()) for v in ("match", "sameFloorDiffer", "otherFloor", "missing")}
    m, d = st("card", "match"), st("card", "sameFloorDiffer") | st("card", "otherFloor")
    res["primary_card_match_vs_differ"] = summarize(pairs, m, d)
    res["primary_card_match_vs_differ_act4arrival"] = summarize(pairs, m, d, ("a4a", "a4b"))
    res["card_match_vs_sameFloorDiffer"] = summarize(pairs, m, st("card", "sameFloorDiffer"))
    res["card_sameFloor_vs_otherFloor"] = summarize(pairs, st("card", "match") | st("card", "sameFloorDiffer"),
                                                    st("card", "otherFloor"))
    for f in ("relic", "potion"):
        res[f + "_match_vs_differ"] = summarize(pairs, st(f, "match"),
                                                st(f, "sameFloorDiffer") | st(f, "otherFloor"))
    allm = np.ones(len(pairs), bool)
    res["all"] = summarize(pairs, allm, allm)
    ra = np.array([p["rootAct"] for p in pairs])
    scr = np.array([p["rootScreen"] for p in pairs])
    res["byRootAct"] = {int(a): summarize(pairs, m & (ra == a), d & (ra == a)) for a in (1, 2, 3)}
    res["byRootScreen"] = {int(s): summarize(pairs, m & (scr == s), d & (scr == s)) for s in sorted(set(scr))
                           if (m & (scr == s)).sum() >= 30 and (d & (scr == s)).sum() >= 30}
    camp = np.array([p["campaign"] for p in pairs])
    res["byCampaign"] = {c: summarize(pairs, m & (camp == c), d & (camp == c)) for c in sorted(set(camp))}
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res["primary_card_match_vs_differ"], indent=1))


if __name__ == "__main__":
    main()
