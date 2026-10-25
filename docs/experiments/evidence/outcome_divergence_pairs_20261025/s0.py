#!/usr/bin/env python3
"""Offline first-divergence test of an outcome-label value head (PREREG.md in this directory).

  s0.py extract OUT CAMPAIGN_DIR...   unit tars -> OUT/{rows.npz, rows_meta.npz, pairs.json, extract.json}
  s0.py fit OUT                       head G on TRAIN (early stop on VALIDATION) -> OUT/head.json, fit.json
  s0.py rho OUT                       child outcome correlation, all splits (no head)
  s0.py test OUT                      primary A_h and secondaries on TEST pairs -> OUT/test.json

Splits by seed: TEST seed % 4 == 3, VALIDATION == 2, TRAIN in {0, 1}. TEST rows are never written to rows.npz.
"""
import glob
import gzip
import hashlib
import io
import itertools
import json
import os
import sys
import tarfile
from array import array

import numpy as np
import scipy.sparse as sp

N_CARDS, N_RELICS, N_POTIONS, N_ROOMS = 372, 181, 48, 8
OFF = {}
_o = 0
for name, n in [("fixed", 10), ("deck", N_CARDS), ("deckUp", N_CARDS), ("relic", N_RELICS), ("potion", N_POTIONS),
                ("roomsAhead", N_ROOMS), ("mapXY", 2), ("actFloor", 2), ("screen", 9), ("select", 16),
                ("offered", 4)]:
    OFF[name] = (_o, n)
    _o += n
N_FEAT = _o


def split_of(seed):
    return {3: "test", 2: "validation"}.get(seed % 4, "train")


def features(state):
    """Sparse (cols, vals) of one state row; public record only."""
    r = state["record"]
    cols, vals = [], []

    def put(block, i, v):
        o, n = OFF[block]
        if 0 <= i < n and v:
            cols.append(o + i)
            vals.append(float(v))

    for i, v in enumerate(r["obs.fixed_observation"][:10]):
        put("fixed", i, v)
    for block, ids in (("deck", [c for c, u in zip(r["obs.deck.cards"], r["obs.deck.upgrades"])]),
                       ("deckUp", [c for c, u in zip(r["obs.deck.cards"], r["obs.deck.upgrades"]) if u]),
                       ("potion", r["obs.potions"])):
        cnt = {}
        for c in ids:
            cnt[c] = cnt.get(c, 0) + 1
        for c, v in cnt.items():
            put(block, c, v)
    for c in set(r["obs.relics.relics"]):
        put("relic", c, 1)
    y0 = r["obs.mapY"]
    ahead = [0] * N_ROOMS
    for y, t in zip(r["obs.map.ys"], r["obs.map.roomTypes"]):
        if y > y0 and 0 <= t < N_ROOMS:
            ahead[t] += 1
    for i, v in enumerate(ahead):
        put("roomsAhead", i, v)
    put("mapXY", 0, r["obs.mapX"] + 1)
    put("mapXY", 1, y0 + 2)
    put("actFloor", 0, state["act"])
    put("actFloor", 1, state["floor"] + 1)
    put("screen", min(r["screen_state"], 8), 1)
    put("select", min(r["select_screen_type"], 15), 1)
    for i, k in enumerate(("cards_offered.cards", "relics_offered", "potions_offered", "paths_offered")):
        put("offered", i, len(r[k]))
    return cols, vals


def read_unit(path):
    """arm -> (states, outcome) for every valid arm game in one unit tar."""
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


def extract(out, dirs):
    os.makedirs(out, exist_ok=True)
    indptr, indices, data, meta, pairs = array('q', [0]), array('i'), array('f'), [], []
    stats = {"tars": 0, "duplicateSeeds": 0, "invalidArmGames": 0, "games": 0, "identicalPairs": 0, "pairs": 0}
    gid = 0
    for d in dirs:
        camp = os.path.basename(os.path.normpath(d))
        seen = set()
        for t in sorted(glob.glob(os.path.join(d, "units", "*.tar"))):
            seed = int(os.path.basename(t).split(".")[0])
            stats["tars"] += 1
            if seed in seen:
                stats["duplicateSeeds"] += 1
                continue
            seen.add(seed)
            games = read_unit(t)
            split = split_of(seed)
            for arm, (states, outc) in sorted(games.items()):
                stats["games"] += 1
                gid += 1
                if split == "test":
                    continue
                w = 1.0 / len(states)
                for s in states:
                    c, v = features(s)
                    indices.extend(c)
                    data.extend(v)
                    indptr.append(len(indices))
                    meta.append((gid, seed, s["act"], int(split == "train"), int(outc["heartKilled"]), w))
            for a, b in itertools.combinations(sorted(games), 2):
                sa, sb = games[a][0], games[b][0]
                k = 0
                while k < min(len(sa), len(sb)) and sa[k]["record"] == sb[k]["record"]:
                    k += 1
                if k == min(len(sa), len(sb)):
                    stats["identicalPairs"] += 1
                    continue
                if k == 0:
                    raise SystemExit(f"{t}: arms {a},{b} differ at the first state")
                stats["pairs"] += 1
                oa, ob = games[a][1], games[b][1]
                pairs.append({"campaign": camp, "seed": seed, "split": split, "a": a, "b": b, "k": k,
                              "rootAct": sa[k - 1]["act"], "rootFloor": sa[k - 1]["floor"],
                              "rootScreen": sa[k - 1]["screen"], "fa": features(sa[k]), "fb": features(sb[k]),
                              "ya": int(oa["heartKilled"]), "yb": int(ob["heartKilled"]),
                              "a4a": int(oa["finalAct"] == 4), "a4b": int(ob["finalAct"] == 4)})
        stats[camp + "Seeds"] = len(seen)
    X = sp.csr_matrix((np.frombuffer(data, np.float32), np.frombuffer(indices, np.int32), np.frombuffer(indptr, np.int64)),
                      shape=(len(indptr) - 1, N_FEAT))
    sp.save_npz(os.path.join(out, "rows.npz"), X)
    m = np.array(meta, dtype=np.float64)
    np.savez(os.path.join(out, "rows_meta.npz"), gid=m[:, 0].astype(np.int64), seed=m[:, 1].astype(np.int64),
             act=m[:, 2].astype(np.int64), train=m[:, 3].astype(bool), y=m[:, 4], w=m[:, 5])
    with open(os.path.join(out, "pairs.json"), "w") as f:
        json.dump(pairs, f)
    stats["rows"] = X.shape[0]
    json.dump(stats, open(os.path.join(out, "extract.json"), "w"), indent=1)
    print(json.dumps(stats))


def dense(pairs, key):
    X = np.zeros((len(pairs), N_FEAT), np.float32)
    for i, p in enumerate(pairs):
        c, v = p[key]
        X[i, c] = v
    return X


def fit(out):
    import xgboost as xgb
    X = sp.load_npz(os.path.join(out, "rows.npz"))
    m = np.load(os.path.join(out, "rows_meta.npz"))
    tr, va = m["train"], ~m["train"]
    dtr = xgb.DMatrix(X[tr], label=m["y"][tr], weight=m["w"][tr])
    dva = xgb.DMatrix(X[va], label=m["y"][va], weight=m["w"][va])
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 6, "eta": 0.05,
              "subsample": 0.8, "colsample_bytree": 0.5, "min_child_weight": 1, "tree_method": "hist", "seed": 0,
              "nthread": 4}
    bst = xgb.train(params, dtr, 2000, evals=[(dva, "validation")], early_stopping_rounds=100, verbose_eval=100)
    path = os.path.join(out, "head.json")
    bst.save_model(path)
    p = bst.predict(dva, iteration_range=(0, bst.best_iteration + 1))
    rep = {"xgboost": xgb.__version__, "bestIteration": bst.best_iteration, "headSha256":
           hashlib.sha256(open(path, "rb").read()).hexdigest(), "trainRows": int(tr.sum()), "valRows": int(va.sum()),
           "trainGames": int(len(set(m["gid"][tr]))), "valGames": int(len(set(m["gid"][va])))}
    y, w, act = m["y"][va], m["w"][va], m["act"][va]
    const = np.average(m["y"][tr], weights=m["w"][tr])
    for a in (1, 2, 3, 4):
        s = act == a
        ll = lambda q: float(-np.average(y[s] * np.log(q) + (1 - y[s]) * np.log(1 - q), weights=w[s]))
        rep[f"valLogLossAct{a}"] = {"head": ll(np.clip(p[s], 1e-6, 1 - 1e-6)), "constant": ll(np.full(s.sum(), const))}
    json.dump(rep, open(os.path.join(out, "fit.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


def boot(seeds, vals, n=10000, rng=None):
    """Mean of vals (one row per pair) with a 95% CI over seed resamples."""
    rng = rng or np.random.default_rng(0)
    us, inv = np.unique(seeds, return_inverse=True)
    s, c = np.bincount(inv, vals, len(us)), np.bincount(inv, None, len(us))
    draws = rng.multinomial(len(us), np.full(len(us), 1 / len(us)), n)
    means = (draws @ s) / (draws @ c)
    return {"n": int(len(vals)), "seeds": int(len(us)), "mean": float(vals.mean()),
            "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]}


def rho(out):
    pairs = json.load(open(os.path.join(out, "pairs.json")))
    rep = {}
    groups = {"all": pairs}
    for p in pairs:
        groups.setdefault(p["campaign"], []).append(p)
        groups.setdefault(f"rootAct{p['rootAct']}", []).append(p)
    for g, ps in groups.items():
        for lab, ka, kb in (("heart", "ya", "yb"), ("act4", "a4a", "a4b")):
            ya, yb = np.array([p[ka] for p in ps], float), np.array([p[kb] for p in ps], float)
            seeds = np.array([p["seed"] for p in ps])
            r = np.corrcoef(ya, yb)[0, 1] if ya.std() > 0 and yb.std() > 0 else float("nan")
            one_minus = np.var(ya - yb) / (np.var(ya) + np.var(yb))
            rng = np.random.default_rng(1)
            us, inv = np.unique(seeds, return_inverse=True)
            bs = []
            for _ in range(2000):
                pick = np.concatenate([np.flatnonzero(inv == i) for i in rng.integers(0, len(us), len(us))])
                a, b = ya[pick], yb[pick]
                bs.append(1 - np.var(a - b) / (np.var(a) + np.var(b)))
            rep[f"{g}/{lab}"] = {"pairs": len(ps), "phi": float(r), "rhoVar": float(1 - one_minus),
                                 "rhoVarCi95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                                 "discordant": int((ya != yb).sum()), "meanY": float((ya.mean() + yb.mean()) / 2)}
    json.dump(rep, open(os.path.join(out, "rho.json"), "w"), indent=1)
    for k, v in rep.items():
        print(k, json.dumps(v))


def test(out):
    import xgboost as xgb
    bst = xgb.Booster()
    bst.load_model(os.path.join(out, "head.json"))
    best = json.load(open(os.path.join(out, "fit.json")))["bestIteration"]
    pairs = [p for p in json.load(open(os.path.join(out, "pairs.json"))) if p["split"] == "test"]
    ga = bst.predict(xgb.DMatrix(dense(pairs, "fa")), iteration_range=(0, best + 1))
    gb = bst.predict(xgb.DMatrix(dense(pairs, "fb")), iteration_range=(0, best + 1))
    sgn = np.sign(ga - gb)
    seeds = np.array([p["seed"] for p in pairs])
    ya, yb = np.array([p["ya"] for p in pairs], float), np.array([p["yb"] for p in pairs], float)
    a4a, a4b = np.array([p["a4a"] for p in pairs], float), np.array([p["a4b"] for p in pairs], float)
    rep = {"primary_A_h_heart": boot(seeds, (ya - yb) * sgn), "A_h_act4": boot(seeds, (a4a - a4b) * sgn),
           "ties": int((sgn == 0).sum())}
    disc = ya != yb
    rep["headAccuracyDiscordantHeart"] = boot(seeds[disc], ((ya - yb) * sgn > 0)[disc].astype(float))
    for key, f in (("campaign", lambda p: p["campaign"]), ("armPair", lambda p: f"{p['campaign']}:{p['a']}-{p['b']}"),
                   ("rootAct", lambda p: p["rootAct"]), ("rootScreen", lambda p: p["rootScreen"])):
        for g in sorted({f(p) for p in pairs}, key=str):
            s = np.array([f(p) == g for p in pairs])
            if s.sum() >= 20:
                rep[f"A_h_heart/{key}={g}"] = boot(seeds[s], ((ya - yb) * sgn)[s], 2000)
    # search vs OFF in §683: arms sorted, so OFF is b for D-OFF and MAP-OFF
    for arm in ("D", "MAP"):
        s = np.array([p["campaign"] == "ooc-map-only-search" and p["a"] == arm and p["b"] == "OFF" for p in pairs])
        if s.any():
            rep[f"A_s_heart/{arm}-OFF"] = boot(seeds[s], (ya - yb)[s], 2000)
            rep[f"A_h_minus_A_s_heart/{arm}-OFF"] = boot(seeds[s], ((ya - yb) * sgn - (ya - yb))[s], 2000)
    lo = rep["primary_A_h_heart"]["ci95"][0]
    rep["verdict"] = "SIGNAL" if lo > 0 else "NO_SIGNAL"
    json.dump(rep, open(os.path.join(out, "test.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "extract":
        extract(sys.argv[2], sys.argv[3:])
    else:
        {"fit": fit, "rho": rho, "test": test}[cmd](sys.argv[2])
