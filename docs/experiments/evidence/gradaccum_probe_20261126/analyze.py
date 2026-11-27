import json, numpy as np
r = json.load(open(__import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "ga.json")); n = np.array(r["eval_n"], float); base = np.array(r["base_per"])
Lb = r["base"]["total"]; arms = r["arms"]
L = lambda x: float(np.dot(n, x) / n.sum())
rng = np.random.default_rng(0); B = rng.integers(0, len(n), (10000, len(n)))
def ci(a, b):   # paired bootstrap over runs of L(a) - L(b)
    d = np.array([np.dot(n[i], a[i] - b[i]) / n[i].sum() for i in B]); return float(np.quantile(d, .025)), float(np.quantile(d, .975))
out = {"L_base": Lb}
for k, v in arms.items():
    x = np.array(v["per"]); out[k] = {"L": L(x), "progress": Lb - L(x), "steps": v["steps"], "gn": v["grad_norm_mean"],
        "outcome_ce": v["end"]["outcome"], "policy": v["end"]["policy"], "mid_L": (v["mid"] or {}).get("total"),
        "ci_base_minus_X": ci(base, x)}
if "A" in arms:
    A = np.array(arms["A"]["per"]); PA = out["A"]["progress"]; delta = max(0.25 * abs(PA), 0.0005 * Lb)
    out["delta"] = delta
    for k in arms:
        if k != "A": out[k]["A_minus_X"] = L(A) - out[k]["L"]; out[k]["ci_A_minus_X"] = ci(A, np.array(arms[k]["per"]))
    if "D" in arms:
        Dp = np.array(arms["D"]["per"])
        for k in ("B", "C"):
            if k in arms: out[k]["ci_D_minus_X"] = ci(Dp, np.array(arms[k]["per"])); out[k]["D_minus_X"] = out["D"]["L"] - out[k]["L"]
print(json.dumps(out, indent=1))
