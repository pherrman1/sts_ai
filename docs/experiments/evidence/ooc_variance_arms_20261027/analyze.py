"""#883 phase 3: variance arms in the sibling capture. Usage: analyze.py OUT.json V-*.sib.jsonl...
Per root (depth-1 children, all arms valid), per arm: variance of the R-repeat mean sibling difference for every child
pair (per-repeat variance / R; repeats are independent across r in every arm), CPU per rollout, and a bias check of
each arm's child means against arm base. Pooled by screen; CIs by root bootstrap."""
import json, sys, gzip, random, math, collections
ARMS = ["base", "indep", "sw", "keyed", "swkeyed"]
SCREEN = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}

def mean(x): return sum(x) / len(x)
def var(x):
    m = mean(x); return sum((v - m) ** 2 for v in x) / (len(x) - 1)

roots = collections.defaultdict(list)
bad = 0
for f in sys.argv[2:]:
    op = gzip.open if f.endswith(".gz") else open
    for line in op(f, "rt"):
        r = json.loads(line)
        vr = r.get("extra", {}).get("vr")
        if r.get("depth") != 1 or not vr: continue
        if any(a not in vr or any(v is None for v in vr[a]["values"]) for a in ARMS): bad += 1; continue
        roots[(r["seed"], r["decision"])].append(r)

per_root = []   # (screen, {arm: (sum var of pair-diff means, sum cpu, n rollouts)}, bias rows)
bias = {a: [] for a in ARMS if a != "base"}
death = {a: [0, 0] for a in ARMS}
for key, leaves in sorted(roots.items()):
    leaves = [l for l in leaves]
    keys = [l["actionKey"] for l in leaves]
    if len(set(keys)) < 2: continue
    screen = SCREEN.get(leaves[0]["parentScreen"], str(leaves[0]["parentScreen"]))
    stats = {}
    for a in ARMS:
        vals = [l["extra"]["vr"][a]["values"] for l in leaves]
        R = len(vals[0])
        s = 0.0
        for i in range(len(leaves)):
            for j in range(i + 1, len(leaves)):
                if keys[i] == keys[j]: continue
                s += var([x - y for x, y in zip(vals[i], vals[j])]) / R
        cpu = sum(l["extra"]["vr"][a]["cpuSeconds"] for l in leaves)
        stats[a] = (s, cpu, R * len(leaves))
        for l in leaves:
            t = l["extra"]["vr"][a]["terminal"]; v = l["extra"]["vr"][a]["values"]
            death[a][0] += sum(1 for tt, vv in zip(t, v) if tt is True and vv == 0); death[a][1] += len(v)
    for a in bias:
        for l in leaves:
            b = l["extra"]["vr"]["base"]["values"]; x = l["extra"]["vr"][a]["values"]
            d = [p - q for p, q in zip(x, b)]
            se = math.sqrt(var(d) / len(d)) if var(d) > 0 else 0
            bias[a].append((key, mean(d), se))
    per_root.append((screen, stats))

def ratio(rows, a, cpu=False):
    num = sum(r[1][a][0] * (r[1][a][1] if cpu else 1) for r in rows)
    den = sum(r[1]["base"][0] * (r[1]["base"][1] if cpu else 1) for r in rows)
    return num / den if den else float("nan")

def boot(rows, a, cpu, n=2000):
    rng = random.Random(883); out = []
    for _ in range(n):
        s = [rows[rng.randrange(len(rows))] for _ in rows]
        out.append(ratio(s, a, cpu))
    out.sort(); return out[int(0.025 * n)], out[int(0.975 * n)]

report = {"roots": len(per_root), "rowsDroppedInvalid": bad, "deathRate": {a: death[a][0] / max(1, death[a][1]) for a in ARMS},
          "screens": {}, "bias": {}}
groups = collections.defaultdict(list)
for r in per_root: groups[r[0]].append(r); groups["all"].append(r)
for g, rows in sorted(groups.items()):
    if not any(r[1]["base"][0] > 0 for r in rows): continue
    e = {"roots": len(rows)}
    for a in ARMS:
        if a == "base": continue
        cpu_ratio = sum(r[1][a][1] for r in rows) / sum(r[1]["base"][1] for r in rows)
        v = ratio(rows, a); lo, hi = boot(rows, a, False)
        # variance x CPU (work-normalised; lower is better), as a ratio to base
        w = v * cpu_ratio
        e[a] = {"varRatio": v, "varRatioCI": [lo, hi], "cpuRatio": cpu_ratio, "workRatio": w}
    report["screens"][g] = e
for a, rows in bias.items():
    z = [m / se for _, m, se in rows if se > 0]
    # root-clustered pooled mean difference
    by = collections.defaultdict(list)
    for k, m, _ in rows: by[k].append(m)
    rm = [mean(v) for v in by.values()]
    pm = mean(rm); pse = math.sqrt(var(rm) / len(rm)) if len(rm) > 1 else float("nan")
    report["bias"][a] = {"children": len(rows), "fracAbsZgt2": sum(abs(x) > 2 for x in z) / max(1, len(z)),
                         "pooledMeanDiff": pm, "pooledSE": pse}
# Exploratory (added after the interim look, not pre-registered): sign split of the per-child z, and z against keyed
# instead of base. A survival-weighted arm paired with base shares base's draws until the first death, so its
# per-repeat difference is a small negative (W - 1) V almost everywhere plus rare large positive terms; with few
# deaths in R repeats the t statistic is skewed, which the sign split shows.
for a, rows in bias.items():
    z = [m / se for _, m, se in rows if se > 0]
    report["bias"][a]["zNegGt2"] = sum(x < -2 for x in z) / max(1, len(z))
    report["bias"][a]["zPosGt2"] = sum(x > 2 for x in z) / max(1, len(z))
alt = []
for key, leaves in sorted(roots.items()):
    for l in leaves:
        k = l["extra"]["vr"]["keyed"]["values"]; x = l["extra"]["vr"]["sw"]["values"]
        d = [p - q for p, q in zip(x, k)]
        if var(d) > 0: alt.append(mean(d) / math.sqrt(var(d) / len(d)))
report["exploratory_sw_vs_keyed_fracAbsZgt2"] = sum(abs(x) > 2 for x in alt) / max(1, len(alt))
json.dump(report, open(sys.argv[1], "w"), indent=1)
print(json.dumps(report, indent=1))
