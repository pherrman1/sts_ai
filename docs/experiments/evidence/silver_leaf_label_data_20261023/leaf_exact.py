#!/usr/bin/env python3
"""Heads on exact leaf values: the capacity test's 69,734 search leaves of first fights 111149600-649 (exact value v
under Silver's own objective). The native forward (policyMlpBase of a combat_policy_mlp trunk file, relu, the
silver_value_head_v1 head) in numpy. Reports, per head: RMSE and bias against v, RMSE with each group's mean
bias removed (group = seed, encounter, config, turn), and pairwise order agreement inside each group (pairs whose
exact values differ by at least 1 point), and the same for pairs from one fight and config at different leaf turns.
usage: leaf_exact.py LABELS.jsonl.gz NAME=TRUNK.txt:HEAD.txt [...]"""
import gzip
import json
import sys
from collections import defaultdict

import numpy as np

KMON_OFF, KMON_FEATS, KMON_DMG = 1664, 9, 4   # monster slot k: id at 1664 + 9k, incoming damage at +4


def load_trunk(path):
    lines = open(path).read().split("\n")
    out = {}
    for i, ln in enumerate(lines):
        k = ln.split(" ")[0]
        if k in ("state_w", "b1", "enc", "mon_id", "mon_dmg") and k not in out:
            out[k] = np.array(lines[i + 1].split(" "), np.float64)
    h1 = len(out["b1"])
    return {"state_w": out["state_w"].reshape(-1, h1), "b1": out["b1"], "enc": out["enc"].reshape(-1, h1),
            "mon_id": out["mon_id"].reshape(-1, h1), "mon_dmg": out["mon_dmg"].reshape(-1, h1)}


def load_head(path):
    d = {}
    for ln in open(path):
        p = ln.split()
        d[p[0]] = np.array(p[1:], np.float64) if len(p) > 1 else None
    hid, inn = int(d["hidden"][0]), int(d["in"][0])
    return {"mu": d["mu"], "inv": d["inv_sd"], "w1": d["w1"].reshape(hid, inn), "b1": d["b1"], "w2": d["w2"],
            "b2": d["b2"][0], "scale": d["scale"][0], "offset": d["offset"][0]}


def row(v, n):
    return int(min(max(round(v), 0), n - 1))


def value(s, t, h):
    base = t["b1"].copy()
    base += t["enc"][row(s.get(1, 0.0), len(t["enc"]))]
    for k in range(5):
        mid = s.get(KMON_OFF + k * KMON_FEATS, 0.0)
        if mid == 0 or round(mid) + 1 <= 0:
            continue
        base += t["mon_id"][row(mid + 1, len(t["mon_id"]))]
        base += t["mon_dmg"][row(s.get(KMON_OFF + k * KMON_FEATS + KMON_DMG, 0.0), len(t["mon_dmg"]))]
    idx = np.array(sorted(s), np.int64)
    base += np.array([s[i] for i in idx]) @ t["state_w"][idx]
    x = (np.maximum(base, 0) - h["mu"]) * h["inv"]
    a = np.maximum(h["w1"] @ x + h["b1"], 0)
    return h["scale"] * (h["w2"] @ a + h["b2"]) + h["offset"]


rows = [json.loads(l) for l in gzip.open(sys.argv[1])]
print(f"{len(rows)} leaves")
v = np.array([r["v"] for r in rows])
grp = [(r["seed"], r["encounter"], r["config"], r["turn"]) for r in rows]
gid = {g: i for i, g in enumerate(sorted(set(grp)))}
g = np.array([gid[x] for x in grp])
turn = np.array([r["turn"] for r in rows])
fby = defaultdict(list)
for i, r in enumerate(rows):
    fby[(r["seed"], r["encounter"], r["config"])].append(i)
for spec in sys.argv[2:]:
    name, paths = spec.split("=")
    tp, hp = paths.split(":")
    t, h = load_trunk(tp), load_head(hp)
    p = np.array([value({i: x for i, x in r["state"]}, t, h) for r in rows])
    e = p - v
    gb = np.zeros(len(gid)); gn = np.zeros(len(gid))
    np.add.at(gb, g, e); np.add.at(gn, g, 1)
    ed = e - (gb / gn)[g]
    agree = tot = 0
    by = defaultdict(list)
    for i, gi in enumerate(g):
        by[gi].append(i)
    for ix in by.values():
        ix = np.array(ix)
        if len(ix) < 2:
            continue
        dv = v[ix][:, None] - v[ix][None, :]
        dp = p[ix][:, None] - p[ix][None, :]
        m = np.triu(np.abs(dv) >= 1.0, 1)
        agree += int(((np.sign(dv) == np.sign(dp)) & m).sum()); tot += int(m.sum())
    xa = xt = 0  # pairs from the same fight and config at different leaf turns (what a multi-turn tree compares)
    for ix in fby.values():
        ix = np.array(ix)
        dv = v[ix][:, None] - v[ix][None, :]
        dp = p[ix][:, None] - p[ix][None, :]
        m = np.triu((np.abs(dv) >= 1.0) & (turn[ix][:, None] != turn[ix][None, :]), 1)
        xa += int(((np.sign(dv) == np.sign(dp)) & m).sum()); xt += int(m.sum())
    print(f"{name:10} RMSE {np.sqrt((e ** 2).mean()):6.2f}  bias {e.mean():+7.2f}  within-group RMSE "
          f"{np.sqrt((ed ** 2).mean()):6.2f}  pair order agreement {agree / tot:.3f} ({tot} pairs)"
          f"  cross-turn {xa / xt:.3f} ({xt} pairs)", flush=True)
    print(f"{'':10} bias by leaf turn: " + "  ".join(f"{k}: {e[turn == k].mean():+.2f} (n={int((turn == k).sum())})"
                                                for k in range(1, 7) if (turn == k).sum() >= 100), flush=True)
