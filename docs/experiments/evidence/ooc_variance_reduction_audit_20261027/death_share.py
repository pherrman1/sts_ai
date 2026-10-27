"""Offline death-share decomposition of rollout3 leaf and sibling-difference variance (#883 phase 1).
Input: §644 sibling capture units (common seeds, 32 repeats). Descriptive only."""
import gzip, json, sys, glob, math, collections, random
root = sys.argv[1]; split = sys.argv[2] if len(sys.argv) > 2 else "VALIDATION"
leaf_stats = []  # (q, mean_surv, var_surv, var_total, n)
pairs = []       # per pair: (var_d, var_d_bothsurv, frac_disc, ss_disc_share, n)
by_screen = collections.defaultdict(list)
for f in sorted(glob.glob(f"{root}/out/units/*/S-*.sib.jsonl.gz")):
    seed = int(f.split("S-")[1].split(".")[0])
    if (split == "VALIDATION") != (seed % 4 == 3): continue
    roots = collections.defaultdict(list)
    for line in gzip.open(f, "rt"):
        r = json.loads(line)
        if r.get("depth") != 1 or "extra" not in r: continue
        reps = r["extra"].get("repeats", [])
        if len(reps) != 32 or any("value" not in x for x in reps): continue
        v = [x["value"] for x in reps]
        dead = [bool(x["terminal"]) and x["value"] == 0 for x in reps]
        roots[(r["decision"], r.get("searchSeed"))].append((r["actionKey"], r["parentScreen"], v, dead))
    for key, leaves in roots.items():
        for ak, scr, v, dead in leaves:
            n = len(v); q = sum(dead) / n
            surv = [x for x, d in zip(v, dead) if not d]
            m = sum(v) / n; vt = sum((x - m) ** 2 for x in v) / (n - 1)
            ms = sum(surv) / len(surv) if surv else 0
            vs = sum((x - ms) ** 2 for x in surv) / (len(surv) - 1) if len(surv) > 1 else 0
            vp = vt * (n - 1) / n  # population variance, same scale as q(1-q)m^2
            leaf_stats.append((q, ms, vs, vt, scr, vp))
        for i in range(len(leaves)):
            for j in range(i + 1, len(leaves)):
                a, b = leaves[i], leaves[j]
                if a[0] == b[0]: continue
                d = [x - y for x, y in zip(a[2], b[2])]
                n = len(d); md = sum(d) / n
                ss = [(x - md) ** 2 for x in d]
                vd = sum(ss) / (n - 1)
                disc = [da != db for da, db in zip(a[3], b[3])]
                both = [dd for dd, da, db in zip(d, a[3], b[3]) if not da and not db]
                vb = (sum((x - sum(both) / len(both)) ** 2 for x in both) / (len(both) - 1)) if len(both) > 1 else float("nan")
                ua = sum((x - sum(a[2]) / n) ** 2 for x in a[2]) / (n - 1); ub = sum((x - sum(b[2]) / n) ** 2 for x in b[2]) / (n - 1)
                pairs.append((vd, vb, sum(disc) / n, (sum(s for s, k in zip(ss, disc) if k) / sum(ss)) if vd > 0 else 0.0, ua + ub, a[1]))
# leaf level
tot = sum(l[3] for l in leaf_stats)
death_term = sum(l[0] * (1 - l[0]) * l[1] ** 2 for l in leaf_stats)
rb = sum((1 - l[0]) ** 2 * l[2] for l in leaf_stats)
print(f"split={split} leaves={len(leaf_stats)} mean death rate={sum(l[0] for l in leaf_stats)/len(leaf_stats):.4f} leaves with any death={sum(l[0]>0 for l in leaf_stats)/len(leaf_stats):.3f}")
print(f"leaf var pooled={tot/len(leaf_stats):.5f}; death term q(1-q)m^2 share={death_term/tot:.3f} (vs ddof=1 variance; vs population variance {death_term/sum(l[5] for l in leaf_stats):.3f}); one-event RB approx var ratio={rb/tot:.3f}")
print(f"pairs with var(d)=0 (perfectly coupled, kept)={sum(p[0]==0 for p in pairs)}")
# pair level
P = len(pairs); svd = sum(p[0] for p in pairs); sind = sum(p[4] for p in pairs)
print(f"pairs={P} CRN ratio var(d)/(var_i+var_j) pooled={svd/sind:.3f}")
print(f"mean frac repeats with discordant death={sum(p[2] for p in pairs)/P:.4f}; pairs with any discordant death={sum(p[2]>0 for p in pairs)/P:.3f}")
print(f"pooled share of sibling-diff SS from discordant-death repeats={sum(p[0]*p[3] for p in pairs)/svd:.3f}")
ok = [p for p in pairs if not math.isnan(p[1])]
print(f"pooled var(d | both survive)/var(d) (proxy for death-free noise)={sum(p[1] for p in ok)/sum(p[0] for p in ok):.3f}")
for scr in sorted(set(p[5] for p in pairs)):
    sub = [p for p in pairs if p[5] == scr]
    print(f"  parentScreen={scr}: pairs={len(sub)} CRN ratio={sum(p[0] for p in sub)/sum(p[4] for p in sub):.3f} disc-death SS share={sum(p[0]*p[3] for p in sub)/sum(p[0] for p in sub):.3f}")
