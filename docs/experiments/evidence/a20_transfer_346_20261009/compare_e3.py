"""Descriptive A20 vs A0 (E3) counterfactual option-spread comparison for #346.

usage: python3 compare_e3.py E3_ROOT A20_ROOT > report.json
E3_ROOT = /mnt/project-files/ooc-cf-pilot/e3, A20_ROOT = .../a20-transfer-346/cf-a20-5ba068e0.
Only parts with a manifest are read; signal is the per-state option-effect variance.
"""
import csv, glob, sys, random, statistics as st, json
from collections import defaultdict

TARGETS = ["finalWon", "act3Boss1", "horizonFloor"]
A20 = False

def load(root):
    states = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # state -> option -> target -> vals
    chosen = {}
    meta = {}
    for f in glob.glob(f"{root}/w*/chunk*/part*.labels.csv"):
        part = f[:-len(".labels.csv")]
        try: open(part + ".manifest.json").close()
        except OSError: continue                      # unfinished part
        for r in csv.DictReader(open(f)):
            if r["valid"] != "1": continue
            key = (r["sourceSeed"], r["decisionIdx"])
            meta[key] = (r["type"], int(r["act"]))
            # First Act-3 boss beaten: at A0 (keys off) that is the run win; at A20
            # the second boss is fought on floor 51.
            r["act3Boss1"] = (r["horizonFloor"] == "51") if A20 else r["finalWon"] == "1"
            for t in TARGETS: states[key][r["optionIdx"]][t].append(float(r[t]))
            if r["chosen"] == "1": chosen[key] = r["optionIdx"]
    return states, chosen, meta

def per_state(states, chosen, meta, t):
    # Futures are common random numbers across options (same futureSeed per k),
    # so the option effect is estimated with a two-way (option x future) ANOVA:
    # signal = var(option means) - MS_interaction / K, unbiased for the variance
    # of true option values within the state.
    rows = []
    for key, opts in states.items():
        mat = [d[t] for o, d in sorted(opts.items())]
        K = min(len(v) for v in mat)
        mat = [v[:K] for v in mat]
        O = len(mat)
        if O < 2 or K < 2 or key not in chosen or chosen[key] not in opts: continue
        om = [st.mean(v) for v in mat]
        fm = [st.mean(mat[o][k] for o in range(O)) for k in range(K)]
        g = st.mean(om)
        ms_int = sum((mat[o][k] - om[o] - fm[k] + g) ** 2 for o in range(O) for k in range(K)) / ((O - 1) * (K - 1))
        allv = [x for v in mat for x in v]
        cm = st.mean(opts[chosen[key]][t][:K])
        rows.append(dict(type=meta[key][0], act=meta[key][1], seed=key[0], mean=g,
                         signal=st.variance(om) - ms_int / K, noise=ms_int,
                         total=st.pvariance(allv), regret=max(om) - cm, nopt=O))
    return rows

def boot(rows, f, n=2000):
    seeds = sorted({r["seed"] for r in rows}); by = defaultdict(list)
    for r in rows: by[r["seed"]].append(r)
    rng = random.Random(346); out = []
    for _ in range(n):
        s = [x for sd in rng.choices(seeds, k=len(seeds)) for x in by[sd]]
        out.append(f(s))
    out.sort(); return out[int(.025*n)], out[int(.975*n)]

def summarize(rows):
    m = lambda key: (lambda rs: st.mean(r[key] for r in rs))
    res = {"states": len(rows)}
    for key in ["mean", "signal", "noise", "total", "regret"]:
        res[key] = round(m(key)(rows), 4); res[key + "_ci"] = [round(x, 4) for x in boot(rows, m(key))]
    return res

out = {}
for name, root in [("A0_E3", sys.argv[1]), ("A20", sys.argv[2])]:
    A20 = name == "A20"
    s, c, meta = load(root)
    out[name] = {}
    for t in TARGETS:
        rows = per_state(s, c, meta, t)
        out[name][t] = {ty: summarize([r for r in rows if r["type"] == ty]) for ty in ["CARD_REWARD", "BOSS_RELIC"]}
print(json.dumps(out, indent=1))
