"""V1 blended-leaf offline gate (PREREG: docs/experiments/evidence/silver_blend_leaf_20261017/PREREG.md).

usage: python3 -I blend_gate.py REPO FEATURES_DIR MODELS_DIR OUT_JSON
"""
import json
import os
import sys

REPO, FEAT, MODELS, OUT = sys.argv[1:5]
sys.path.insert(0, os.path.join(REPO, "tools"))
import numpy as np  # noqa: E402
import lightgbm as lgb  # noqa: E402
import silver_synth_gates as g  # noqa: E402

ALPHAS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
MODEL_NAMES = ["vcont-natpert", "vroll-natpert"]

X, metas, _ = g.load(FEAT)
groups = {}
for i, m in enumerate(metas):
    if m["k"] == "child":
        groups.setdefault(g.root_id(m), {}).setdefault(m["e"], {})[m["role"] + str(m.get("rep", ""))] = i
probes = sorted({e["probe"] for edges in groups.values() for e in edges.values() if "probe" in e})
preds = {}
for name in MODEL_NAMES:
    booster = lgb.Booster(model_file=os.path.join(MODELS, name + ".txt"))
    preds[name] = dict(zip(probes, booster.predict(X[probes])))


def collect(variant, fold):
    out = []
    for rid, edges in groups.items():
        if rid[0] != variant or (rid[1] - g.BASE[variant]) % 5 != fold or len(edges) < 2:
            continue
        es = sorted(edges)
        labs = [[metas[edges[e][f"label{r}"]] for r in (0, 1)] for e in es]
        if any(not lab["valid"] for ls in labs for lab in ls):
            continue
        L = np.array([np.mean([lab["value"] for lab in ls]) for ls in labs])
        probe = [metas[edges[e]["probe"]] for e in es]
        exact = [p["exact"] if p["terminal"] else None for p in probe]
        sc = {"R1": np.array([p["rollouts"][0] for p in probe], float),
              "R2": np.array([np.mean(p["rollouts"][:2]) for p in probe], float),
              "R4": np.array([np.mean(p["rollouts"]) for p in probe], float)}
        for name in MODEL_NAMES:
            v = np.array([ex if ex is not None else preds[name][edges[e]["probe"]]
                          for e, ex in zip(es, exact)], float)
            sc["V:" + name] = v
            for a in ALPHAS:
                b = (1 - a) * sc["R1"] + a * v
                # terminal probe children keep their exact score for every predictor
                b = np.array([ex if ex is not None else bb for bb, ex in zip(b, exact)], float)
                sc[f"B:{name}:{a}"] = b
        out.append({"seed": rid[1], "L": L, "sc": sc})
    return out


def regret(rows, key):
    return np.array([r["L"].max() - r["L"][int(np.argmax(r["sc"][key]))] for r in rows])


def conc(rows, key):
    a = t = 0.0
    for r in rows:
        x, y = g.concordance(r["sc"][key], r["L"])
        a += x
        t += y
    return a / t


rng = np.random.default_rng(7)
result = {}
val = collect("natural", g.VAL)
chosen = {}
for name in MODEL_NAMES:
    regs = {a: float(regret(val, f"B:{name}:{a}").mean()) for a in ALPHAS}
    best = min(ALPHAS, key=lambda a: (round(regs[a], 9), a))
    chosen[name] = best
    result.setdefault("validation", {})[name] = {"regretByAlpha": regs, "alpha": best,
                                                 "R1": float(regret(val, "R1").mean()),
                                                 "groups": len(val)}
for variant in ("natural", "perturbed"):
    rows = collect(variant, g.TEST)
    seeds = np.array([r["seed"] for r in rows])
    r1 = regret(rows, "R1")
    r2 = regret(rows, "R2")
    res = {"groups": len(rows), "seeds": len(set(seeds.tolist()))}
    keys = ["R1", "R2", "R4"] + [f"V:{n}" for n in MODEL_NAMES] + [f"B:{n}:{chosen[n]}" for n in MODEL_NAMES]
    for k in keys:
        reg = regret(rows, k)
        res[k] = {"regret": float(reg.mean()), "concordance": conc(rows, k)}
        if k != "R1":
            res[k]["minusR1"] = g.boot_mean(reg - r1, seeds, rng)
        if k.startswith("B:"):
            res[k]["minusR2"] = g.boot_mean(reg - r2, seeds, rng)
    result[variant] = res
nat = result["natural"]
p = nat[f"B:vcont-natpert:{chosen['vcont-natpert']}"]
result["gate"] = {"pass": p["minusR1"][2] < 0 and p["concordance"] > nat["R1"]["concordance"],
                  "blendAtLeastR2": p["minusR2"][2] <= 0.1}
json.dump(result, open(OUT, "w"), indent=2)
print(json.dumps(result, indent=2))
