import json, sys, collections
S = sys.argv[1]
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
meta = [json.loads(l) for l in open(S + "/meta.jsonl")]
outs = {k: [json.loads(l) for l in open(f"{S}/out_{k}.jsonl")] for k in ("sel", "g2", "g3")}
def am(xs, ok): 
    best = None
    for i, x in enumerate(xs):
        if ok[i] and (best is None or x > xs[best]): best = i
    return best
rows = []
bad = 0
for i, m in enumerate(meta):
    L = m["logits"]; ok = [x is not None for x in L]
    if sum(ok) < 2: continue
    r = {"src": m["src"], "screen": SCREENS.get(m["screen"], str(m["screen"])), "pi": am(L, ok)}
    for k in outs:
        nl = outs[k][i]["logits"]
        if len(nl) != len(L): bad += 1
        r[k] = am(nl[:len(L)], ok)
    rows.append(r)
print("rows with >=2 options", len(rows), "length mismatches", bad)
def report(rs, title):
    n = len(rs)
    if not n: return
    t = lambda k: sum(r[k] == r["pi"] for r in rs) / n
    flip3 = [r for r in rs if r["g3"] != r["sel"]]; flip2 = [r for r in rs if r["g2"] != r["sel"]]
    ov = [r for r in rs if r["pi"] != r["sel"]]
    f = lambda xs, cond: (sum(cond(r) for r in xs), len(xs))
    print(f"{title}: n {n} | top1 vs pi: sel {t('sel'):.3f} g2 {t('g2'):.3f} g3 {t('g3'):.3f} | "
          f"g3!=sel {len(flip3)/n:.3%} (g3 right {f(flip3, lambda r: r['g3']==r['pi'])[0]}, sel right {f(flip3, lambda r: r['sel']==r['pi'])[0]}) | "
          f"g2!=sel {len(flip2)/n:.3%} | overrides (pi!=sel) {len(ov)/n:.2%}: g3 gets {f(ov, lambda r: r['g3']==r['pi'])[0]}/{len(ov)}, g2 gets {f(ov, lambda r: r['g2']==r['pi'])[0]}/{len(ov)}")
report(rows, "ALL")
for s in sorted({r["src"] for r in rows}): report([r for r in rows if r["src"] == s], "src " + s)
for s in sorted({r["screen"] for r in rows}): report([r for r in rows if r["screen"] == s], "screen " + s)
