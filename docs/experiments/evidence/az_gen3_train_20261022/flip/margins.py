#!/usr/bin/env python3
"""Root Q margins at decision flips (review of #814). For every validation-fold policy row of flip/build.py, find the
raw capture's root (same seed and decisionIndex), map each net's top token to its search candidate, and compare the
candidates' root q (completed: unvisited -> rootMeanQ) and what the search played (root selectedId).
dp = calibrated P(Heart kill) difference, sigmoid(A + B logit q) with the gen-3 root_v calibration (training folds).
usage: margins.py FLIPDIR RAW_TAR...   (tars holding on-SEED / A-SEED / B-SEED / E-SEED captures)"""
import gzip, io, json, math, re, sys, tarfile, statistics as st
A, B = -1.6115816831588745, 0.5970583558082581   # gen3/logs/calibration.json root_v
D = sys.argv[1]; tars = sys.argv[2:]
meta = [json.loads(l) for l in open(D + "/meta.jsonl")]
outs = {k: [json.loads(l)["logits"] for l in open(f"{D}/out_{k}.jsonl")] for k in ("sel", "g2", "g3")}
def key(m): return "E" if m["src"] == "explore" else "on" if m["src"] == "gen0" else "B" if m["src"].endswith("_B") else "A"
need = {(key(m), m["seed"]) for m in meta}
pat = re.compile(r"(?:^|/)(on|A|B|E)-(\d+)\.jsonl(?:\.gz)?$")
roots, per_run = {}, []
for p in tars:
    with tarfile.open(p) as t:
        for mem in t:
            h = pat.search(mem.name)
            if not h or not mem.isfile() or (h.group(1), int(h.group(2))) not in need: continue
            raw = t.extractfile(mem).read()
            if mem.name.endswith(".gz"): raw = gzip.decompress(raw)
            ds = [d for d in map(json.loads, io.StringIO(raw.decode())) if d.get("type") == "decision"]
            roots[(h.group(1), int(h.group(2)))] = {d["decisionIndex"]: d for d in ds}
            srch = [d for d in ds if d.get("searched") and d.get("root") and not d["root"].get("singleton")]
            per_run.append((len(srch), sum(bool(d["root"].get("fullBudget")) for d in srch)))
print(f"runs {len(roots)} of {len(need)}; searched non-singleton roots per run {st.mean(x for x, _ in per_run):.1f}, "
      f"full-budget {st.mean(y for _, y in per_run):.1f}")
cal = lambda q: 1 / (1 + math.exp(-(A + B * math.log(min(max(q, 1e-4), 1 - 1e-4) / (1 - min(max(q, 1e-4), 1 - 1e-4))))))
def am(xs, ok): return max((j for j in range(len(ok)) if ok[j]), key=lambda j: xs[j])
res = {"flip_g3": [], "flip_g2": [], "override": [], "top2": []}
for i, m in enumerate(meta):
    d = roots[(key(m), m["seed"])][m["decision"]]; root = d["root"]; c = root["candidates"]
    L = m["logits"]; ok = [x is not None for x in L]
    tok2c = {t: ci for ci, x in enumerate(c) for t in (x.get("heart1Tokens") or [])}
    cq = [x["q"] if x["visits"] > 0 else root["rootMeanQ"] for x in c]
    played = next(ci for ci, x in enumerate(c) if x["id"] == root["selectedId"])
    ch = {k: tok2c[am(v, ok)] for k, v in (("sel", outs["sel"][i]), ("g2", outs["g2"][i]), ("g3", outs["g3"][i]), ("pi", L))}
    vis = sorted((x["q"] for x in c if x["visits"] > 0), reverse=True)
    if len(vis) >= 2: res["top2"].append(vis[0] - vis[1])
    for net in ("g3", "g2", "pi"):
        if ch[net] == ch["sel"]: continue
        a, b = ch[net], ch["sel"]
        res["override" if net == "pi" else "flip_" + net].append({
            "dq": cq[a] - cq[b], "dp": cal(cq[a]) - cal(cq[b]), "n_new": c[a]["visits"], "n_sel": c[b]["visits"],
            "played": "new" if played == a else "sel" if played == b else "other", "src": m["src"]})
qt = lambda xs, k: st.quantiles(xs, n=20)[k]
t2 = res["top2"]
print(f"all {len(t2)} roots: q gap between the two best visited candidates: median {st.median(t2):.4f} (p25 {qt(t2,4):.4f}, p75 {qt(t2,14):.4f})")
for name, lab in (("flip_g3", "gen 3 vs student_sel"), ("flip_g2", "gen 2 vs student_sel"), ("override", "pi' vs student_sel")):
    xs = res[name]; g = [abs(x["dq"]) for x in xs]; pl = [x["played"] for x in xs]
    print(f"{lab}: {len(xs)} roots ({len(xs)/len(meta):.2%}) | |dq| median {st.median(g):.4f} p75 {qt(g,14):.4f} | "
          f"mean dq new-minus-sel {st.mean(x['dq'] for x in xs):+.4f} (new higher at {sum(x['dq'] > 0 for x in xs)/len(xs):.0%}) | "
          f"mean dp {st.mean(x['dp'] for x in xs):+.4f} | search played new {pl.count('new')}, sel {pl.count('sel')}, other {pl.count('other')} | "
          f"median visits new {st.median(x['n_new'] for x in xs):.0f}, sel {st.median(x['n_sel'] for x in xs):.0f}")
json.dump(res, open(D + "/margins.json", "w"))
