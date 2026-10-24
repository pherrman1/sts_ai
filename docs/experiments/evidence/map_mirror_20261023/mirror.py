#!/usr/bin/env python3
"""Horizontal map-mirror invariance check of a heart1/student net (offline, no gameplay).

usage: mirror.py prep OUT_DIR CAPTURE.jsonl.gz ...      -> OUT_DIR/{orig,mirror}.jsonl + meta.jsonl
       mirror.py stats OUT_DIR TAG                      -> reads OUT_DIR/{orig,mirror}.TAG.scores.jsonl
       mirror.py startcols OUT_DIR TAG                  -> absolute start column picked on act-start map rows
       mirror.py mapstats OUT_DIR                       -> column histogram of distinct act 1-3 maps (left/right skew)

The mirror maps every map column x to 6 - x (-1 = "no column" is kept): node xs, the burning elite, the
current node and the offered paths. obs.map.pathXs is buildRecord's [left, straight, right] edge triple, so it
becomes [6-right, 6-straight, 6-left]. Map tokens are re-sorted by (y, x) as buildRecord emits them, so a
mirrored record is the record the engine would build for the mirrored map. On floor 14 the only path action is
the boss move (idx 0, GameContext::mapMoveCost), which is an action id, not a column: it is kept. Everything else
(deck, relics, potions, HP, gold, keys, act, screen) is unchanged. Path logits stay index-aligned.
"""
import gzip, json, math, os, sys

def mx(x): return 6 - x if x >= 0 else x

def mirror(rec):
    r = dict(rec)
    n = len(rec["obs.map.xs"])
    xs = [mx(x) for x in rec["obs.map.xs"]]
    px = [[mx(p[2]), mx(p[1]), mx(p[0])] for p in rec["obs.map.pathXs"]]
    order = sorted(range(n), key=lambda j: (rec["obs.map.ys"][j], xs[j]))
    r["obs.map.xs"] = [xs[j] for j in order]
    r["obs.map.ys"] = [rec["obs.map.ys"][j] for j in order]
    r["obs.map.roomTypes"] = [rec["obs.map.roomTypes"][j] for j in order]
    r["obs.map.pathXs"] = [px[j] for j in order]
    r["obs.map.burningEliteX"] = mx(rec.get("obs.map.burningEliteX", -1))
    r["obs.mapX"] = mx(rec["obs.mapX"])
    if rec["obs.mapY"] != 14: r["paths_offered"] = [mx(p) for p in rec["paths_offered"]]
    return r

def prep(out, files):
    os.makedirs(out, exist_ok=True)
    fo, fm, fmeta = (open(os.path.join(out, f), "w") for f in ("orig.jsonl", "mirror.jsonl", "meta.jsonl"))
    n = 0
    for f in files:
        for line in gzip.open(f, "rt"):
            row = json.loads(line)
            rec = row["record"]
            m = mirror(rec)
            assert mirror(m) == rec, (f, n)
            fo.write(json.dumps(rec) + "\n"); fm.write(json.dumps(m) + "\n")
            fmeta.write(json.dumps({"file": os.path.basename(f), "screen": rec["screen_state"],
                                    "act": rec.get("obs.act", row.get("act")), "mapY": rec["obs.mapY"],
                                    "npath": len(rec["paths_offered"]), "teacher": row.get("logits"),
                                    "symmetric": m == rec}) + "\n")
            n += 1
    print("rows", n)

def softmax(v):
    m = max(v); e = [math.exp(x - m) for x in v]; s = sum(e); return [x / s for x in e]

def kl(p, q): return sum(a * (math.log(a) - math.log(b)) for a, b in zip(p, q) if a > 0)

def stats(out, tag):
    meta = [json.loads(l) for l in open(os.path.join(out, "meta.jsonl"))]
    so = [json.loads(l) for l in open(os.path.join(out, f"orig.{tag}.scores.jsonl"))]
    sm = [json.loads(l) for l in open(os.path.join(out, f"mirror.{tag}.scores.jsonl"))]
    assert len(meta) == len(so) == len(sm)
    groups = {}
    def add(g, k, v): groups.setdefault(g, {}).setdefault(k, []).append(v)
    worst = []
    for i, (md, a, b) in enumerate(zip(meta, so, sm)):
        dv = abs(a["value"] - b["value"])
        dp = abs(1 / (1 + math.exp(-a["value"])) - 1 / (1 + math.exp(-b["value"])))
        scr = "map" if md["screen"] == 5 else "other"
        keys = ["all", scr] + ([f"map act{md['act']}", "map start-of-act" if md["mapY"] < 0 else "map mid-act"]
                               if scr == "map" else [])
        if md["symmetric"]: keys = ["symmetric (sanity)"]
        for g in keys:
            add(g, "dv", dv); add(g, "dp", dp)
        la, lb = a["logits"], b["logits"]
        if len(la) < 2 or md["symmetric"]: continue
        p, q = softmax(la), softmax(lb)
        mm = [(x + y) / 2 for x, y in zip(p, q)]
        js = 0.5 * kl(p, mm) + 0.5 * kl(q, mm)
        t1 = max(range(len(p)), key=p.__getitem__); t2 = max(range(len(q)), key=q.__getitem__)
        avg = [(x + y) / 2 for x, y in zip(la, lb)]
        ta = max(range(len(avg)), key=avg.__getitem__)
        for g in keys:
            add(g, "pol_n", 1); add(g, "flip", int(t1 != t2)); add(g, "kl", kl(p, q)); add(g, "js", js)
            add(g, "tv", 0.5 * sum(abs(x - y) for x, y in zip(p, q)))
            add(g, "dmax", max(abs(x - y) for x, y in zip(p, q)))
            if md["teacher"] is not None and len(md["teacher"]) == len(la):
                tt = max(range(len(la)), key=md["teacher"].__getitem__)
                add(g, "agree_orig", int(t1 == tt)); add(g, "agree_mirror", int(t2 == tt)); add(g, "agree_avg", int(ta == tt))
        if scr == "map":
            worst.append((js, i, md["file"], md["act"], md["mapY"], [round(x, 3) for x in p], [round(x, 3) for x in q],
                          round(a["value"], 3), round(b["value"], 3)))
    def q(v, f): v = sorted(v); return v[min(len(v) - 1, int(f * len(v)))]
    res = {}
    for g, d in groups.items():
        r = {"n": len(d["dv"]), "dv_mean": sum(d["dv"]) / len(d["dv"]), "dv_p99": q(d["dv"], .99), "dv_max": max(d["dv"]),
             "dp_mean": sum(d["dp"]) / len(d["dp"]), "dp_p99": q(d["dp"], .99), "dp_max": max(d["dp"])}
        if "pol_n" in d:
            n = len(d["pol_n"])
            r.update({"pol_n": n, "top1_flip": sum(d["flip"]) / n, "kl_mean": sum(d["kl"]) / n,
                      "js_mean": sum(d["js"]) / n, "js_p99": q(d["js"], .99), "js_max": max(d["js"]),
                      "tv_mean": sum(d["tv"]) / n, "tv_p99": q(d["tv"], .99), "dprob_max_p99": q(d["dmax"], .99)})
            if "agree_orig" in d:
                m = len(d["agree_orig"])
                r.update({k: sum(d[k]) / m for k in ("agree_orig", "agree_mirror", "agree_avg")})
        res[g] = r
    worst.sort(reverse=True)
    json.dump({"groups": res, "worst_map": worst[:25]}, open(os.path.join(out, f"stats.{tag}.json"), "w"), indent=1)
    for g in sorted(res): print(g, json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in res[g].items()}))

ROOMS = ["SHOP", "REST", "EVENT", "ELITE", "MONSTER", "TREASURE"]

def mapstats(out):
    seen, cnt, slots = set(), {}, [0, 0, 0]
    for line in open(os.path.join(out, "orig.jsonl")):
        r = json.loads(line)
        if r["screen_state"] != 5 or r["obs.mapY"] != -1 or r.get("obs.act", 0) == 4: continue
        key = (tuple(r["obs.map.xs"]), tuple(r["obs.map.ys"]), tuple(r["obs.map.roomTypes"]))
        if key in seen: continue
        seen.add(key)
        for x, y, t, p in zip(r["obs.map.xs"], r["obs.map.ys"], r["obs.map.roomTypes"], r["obs.map.pathXs"]):
            if y < 15: cnt.setdefault(t, [0] * 7)[x] += 1
            if y < 14:
                for k, e in enumerate(p): slots[k] += e >= 0
    res = {"maps": len(seen), "edge_slots_left_straight_right": slots,
           "rooms_by_x": {ROOMS[t]: {"by_x": v, "mean_x": sum(x * c for x, c in enumerate(v)) / sum(v)} for t, v in sorted(cnt.items())}}
    json.dump(res, open(os.path.join(out, "mapstats.json"), "w"), indent=1); print(json.dumps(res))

def startcols(out, tag):
    so = open(os.path.join(out, f"orig.{tag}.scores.jsonl")); sm = open(os.path.join(out, f"mirror.{tag}.scores.jsonl"))
    co, cm, ct = [0] * 7, [0] * 7, [0] * 7
    for o, m, md, a, b in zip(open(os.path.join(out, "orig.jsonl")), open(os.path.join(out, "mirror.jsonl")),
                              open(os.path.join(out, "meta.jsonl")), so, sm):
        md = json.loads(md)
        if md["screen"] != 5 or md["mapY"] != -1 or md["npath"] < 2 or md["symmetric"]: continue
        o, m = json.loads(o)["paths_offered"], json.loads(m)["paths_offered"]
        co[o[json.loads(a)["argmax"]]] += 1; cm[m[json.loads(b)["argmax"]]] += 1
        ct[o[max(range(len(o)), key=md["teacher"].__getitem__)]] += 1
    res = {"teacher_orig": ct, "student_orig": co, "student_mirror": cm, "equivariant_would_be": co[::-1]}
    json.dump(res, open(os.path.join(out, f"startcols.{tag}.json"), "w")); print(json.dumps(res))

if __name__ == "__main__":
    if sys.argv[1] == "startcols": startcols(sys.argv[2], sys.argv[3]); sys.exit()
    if sys.argv[1] == "prep": prep(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "mapstats": mapstats(sys.argv[2])
    else: stats(sys.argv[2], sys.argv[3])
