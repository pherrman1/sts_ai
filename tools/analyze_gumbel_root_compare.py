#!/usr/bin/env python3
"""STS_OOC_MCTS_ROOT_COMPARE rows -> Gumbel sequential halving vs PUCT at matched simulations.

usage: analyze_gumbel_root_compare.py BETA CMP.jsonl...

The reference is the row's uniform search (8192 simulations split evenly over every root action, own seed),
so its per-action Q is independent of both methods. Per method and budget: KL(pi'_ref || pi'_method) of the
ADR-0043 improved policies (constant beta), NLL of the reference's best action under pi'_method, agreement
with the reference's best action, and regret = Q_ref(best) - Q_ref(played action). The max over noisy
reference Q inflates every method's regret by the same amount, so paired regret differences are unbiased.
PUCT at k simulations is the main 4096 search's k-simulation checkpoint (full roots run without stops)."""
import json, math, os, sys, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from heart1.az_targets import improved_policy
BETA = float(sys.argv[1]); rows = [json.loads(l) for p in sys.argv[2:] for l in open(p)]
def acts(a): return {x[0]: (x[1], x[2], x[3]) for x in a}
def best_visits(d):
    live = [(n, q, i) for i, (n, q, pr) in d.items() if not pr and n]
    return max(live)[2] if live else None
def target(cands, d):
    pri = [c["prior"] for c in cands]; ids = [c["id"] for c in cands]
    vis = [d[i][0] if i in d and not d[i][2] else 0 for i in ids]
    qs = [d.get(i, (0, 0, 0))[1] for i in ids]
    tot = sum(vis); rq = sum(n*q for n, q in zip(vis, qs)) / tot if tot else 0
    return improved_policy(pri, qs, vis, rq, BETA)
res = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    if r["reference"]["aborted"] or r["main"]["aborted"]: continue
    c = r["candidates"]; ids = [x["id"] for x in c]
    if len(ids) < 2: continue
    ref = acts(r["reference"]["actions"])
    refq = {i: ref[i][1] for i in ids if ref.get(i, (0,))[0] and not ref[i][2]}
    if len(refq) < 2: continue
    rb = max(refq, key=refq.get)
    pa = max(c, key=lambda x: x["prior"])["id"]
    res["prior-argmax"]["kl"].append(0); res["prior-argmax"]["agree"].append(pa == rb)
    res["prior-argmax"]["regret"].append(refq[rb] - refq.get(pa, min(refq.values()))); res["prior-argmax"]["nll"].append(0)
    pref = target(c, ref)
    meths = {f"puct@{cp['simulations']}": (acts(cp["actions"]), None, None) for cp in r["checkpoints"]}
    meths["puct@4096"] = (acts(r["main"]["actions"]), r["main"]["selectedId"], None)
    for k, g in r["gumbel"].items(): meths[f"sh{k}"] = (acts(g["actions"]), g["selectedId"], g["cpuSeconds"])
    for name, (d, sel, cpu) in meths.items():
        if sel is None: sel = best_visits(d)
        p = target(c, d)
        kl = sum(a * math.log(a / max(b, 1e-12)) for a, b in zip(pref, p) if a > 0)
        rec = res[name]
        rec["kl"].append(kl); rec["agree"].append(sel == rb)
        rec["regret"].append(refq[rb] - refq.get(sel, min(refq.values())))
        rec["nll"].append(-math.log(max(p[ids.index(rb)], 1e-12)))
        rec["root"].append(len(rec["root"]))
        if cpu is not None: rec["cpu"].append(cpu)
    res["ref"]["cpu"].append(r["reference"]["cpuSeconds"])
n = len(res["puct@4096"]["kl"])
def boot(xs, B=1000):
    rnd = random.Random(1); m = len(xs)
    ms = sorted(sum(xs[rnd.randrange(m)] for _ in range(m)) / m for _ in range(B))
    return ms[25], ms[974]
print(f"roots={n} runs={len({(r['seed']) for r in rows})} beta={BETA}  ref cpu/root {sum(res['ref']['cpu'])/max(1,len(res['ref']['cpu'])):.2f}s")
print(f"{'method':14s} {'KL(ref||pi)':>12s} {'95%':>17s} {'NLL refbest':>11s} {'agree':>6s} {'regret*1e3':>10s} {'cpu s':>6s}")
for name in sorted(res, key=lambda k: (k.split('@')[-1].zfill(6), k)):
    if name == "ref" or not res[name]["kl"]: continue
    d = res[name]; m = len(d["kl"]); lo, hi = boot(d["kl"])
    print(f"{name:14s} {sum(d['kl'])/m:12.4f} [{lo:7.4f},{hi:7.4f}] {sum(d['nll'])/m:11.3f} {sum(d['agree'])/m:6.3f} {1e3*sum(d['regret'])/m:10.2f} "
          f"{(sum(d['cpu'])/len(d['cpu'])) if d['cpu'] else float('nan'):6.2f}")
# paired SH - PUCT at matched sims
for k in (512, 1024, 2048):
    for m in (4, 16):
        a, b = res[f"sh{m}@{k}"]["kl"], res[f"puct@{k}"]["kl"]
        if len(a) != len(b) or not a: continue
        diff = [x - y for x, y in zip(a, b)]; lo, hi = boot(diff)
        print(f"paired KL sh{m}@{k} - puct@{k}: {sum(diff)/len(diff):+.4f} [{lo:+.4f},{hi:+.4f}]")
for k in (512, 1024, 2048, 4096):
    for m in (4, 16):
        if f"sh{m}@{k}" not in res: continue
        a, b = res[f"sh{m}@{k}"]["regret"], res[f"puct@{k}"]["regret"]
        diff = [x - y for x, y in zip(a, b)]; lo, hi = boot(diff)
        print(f"paired regret*1e3 sh{m}@{k} - puct@{k}: {1e3*sum(diff)/len(diff):+.2f} [{1e3*lo:+.2f},{1e3*hi:+.2f}]  vs puct@4096: "
              f"{1e3*sum(x-y for x,y in zip(a,res['puct@4096']['regret']))/len(a):+.2f}")
