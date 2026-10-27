#!/usr/bin/env python3
"""STS_OOC_MCTS_ROOT_COMPARE rows with a 16@2048cap row -> how often each root method leaves the prior argmax,
and its regret against the row's uniform 8192-simulation reference (same leaf, own seed).

usage: analyze.py CMP.jsonl...
Methods: prior argmax, PUCT 4096 (the played search), Gumbel SH M16@2048 uncapped (the §635 B rule) and capped
(STS_OOC_MCTS_GUMBEL_QCAP, same seed as the uncapped row). Regret = Q_ref(best) - Q_ref(pick); paired differences
between methods are unbiased (the max over noisy reference Q inflates all methods equally)."""
import json, random, sys
rows = [json.loads(l) for p in sys.argv[1:] for l in open(p)]
names = ["prior", "puct4096", "sh16@2048", "sh16@2048cap"]
recs = {n: {"off": [], "regret": [], "agree": []} for n in names}
pairs = []
for r in rows:
    if r["reference"]["aborted"] or r["main"]["aborted"] or "16@2048cap" not in r["gumbel"]: continue
    c = r["candidates"]
    if len(c) < 2: continue
    ref = {a[0]: a[2] for a in r["reference"]["actions"] if a[1] and not a[3]}
    if len(ref) < 2: continue
    best = max(ref, key=ref.get); worst = min(ref.values())
    pa = max(c, key=lambda x: x["prior"])["id"]
    picks = {"prior": pa, "puct4096": r["main"]["selectedId"], "sh16@2048": r["gumbel"]["16@2048"]["selectedId"],
             "sh16@2048cap": r["gumbel"]["16@2048cap"]["selectedId"]}
    reg = {}
    for n, s in picks.items():
        reg[n] = ref[best] - ref.get(s, worst)
        recs[n]["off"].append(s != pa); recs[n]["regret"].append(reg[n]); recs[n]["agree"].append(s == best)
    pairs.append((reg, max(x["prior"] for x in c), r["seed"], r["decisionIndex"], picks))
n = len(pairs)
def boot(xs, B=2000):
    rnd = random.Random(1); m = len(xs)
    ms = sorted(sum(xs[rnd.randrange(m)] for _ in range(m)) / m for _ in range(B))
    return ms[int(.025 * B)], ms[int(.975 * B) - 1]
print(f"roots={n} runs={len({p[2] for p in pairs})}")
print(f"{'method':14s} {'!=prior':>8s} {'agree ref':>9s} {'regret*1e3':>10s}")
for k in names:
    v = recs[k]
    if n: print(f"{k:14s} {sum(v['off'])/n:8.3f} {sum(v['agree'])/n:9.3f} {1e3*sum(v['regret'])/n:10.2f}")
for a, b in [("sh16@2048cap", "sh16@2048"), ("sh16@2048cap", "puct4096"), ("sh16@2048", "puct4096")]:
    d = [p[0][a] - p[0][b] for p in pairs]
    if d:
        lo, hi = boot(d)
        print(f"regret {a} - {b}: {1e3*sum(d)/len(d):+.2f}e-3 [{1e3*lo:+.2f}, {1e3*hi:+.2f}]")
hi = [p for p in pairs if p[1] >= .9]
print(f"roots with top prior >= .9: {len(hi)}; left prior argmax: "
      + ", ".join(f"{k} {sum(p[4][k] != p[4]['prior'] for p in hi)}" for k in names[1:]))
