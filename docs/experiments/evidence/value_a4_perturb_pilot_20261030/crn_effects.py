#!/usr/bin/env python3
"""Secondary (README): CRN effect per operator = Heart-kill(child) - Heart-kill(control) of the same entry.

  crn_effects.py OUT.json A4P_JSON...

Per operator: mean paired difference with a seed-cluster bootstrap 95% CI (2,000 draws, rng 7). For hp, max_hp and
gold also the slope per unit of the signed change (after - before), through the origin, with the same bootstrap.
"""
import json, sys
import numpy as np


def boot(seeds, vals, stat, nb=2000):
    us = sorted(set(seeds)); idx = {s: [i for i, x in enumerate(seeds) if x == s] for s in us}
    rng = np.random.default_rng(7); bs = []
    for _ in range(nb):
        pick = [i for s in rng.choice(us, len(us)) for i in idx[s]]
        bs.append(stat(pick))
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def main(out, paths):
    rows = []
    for p in paths:
        r = json.load(open(p)); ch = {c["child"]: c for c in r["children"]}; y0 = float(ch[0]["heartKilled"])
        for k, c in ch.items():
            if k == 0:
                continue
            pt = c["perturb"]; delta = None
            if c["op"] in ("hp", "max_hp", "gold") and "after" in pt:
                delta = pt["after"] - pt["before"]
            rows.append(dict(seed=r["seed"], op=c["op"], d=float(c["heartKilled"]) - y0, delta=delta))
    res = {"control_kill_rate": float(np.mean([json.load(open(p))["children"][0]["heartKilled"] for p in paths])),
           "child_kill_rate": float(np.mean([r["d"] for r in rows]) + 0), "ops": {}}
    for op in sorted({r["op"] for r in rows}):
        R = [r for r in rows if r["op"] == op]; s = [r["seed"] for r in R]; d = np.array([r["d"] for r in R])
        e = dict(n=len(R), mean_diff=float(d.mean()), ci=boot(s, d, lambda i: d[i].mean()))
        if all(r["delta"] is not None for r in R):
            x = np.array([r["delta"] for r in R], float)
            e["slope_per_unit"] = float((x * d).sum() / (x * x).sum())
            e["slope_ci"] = boot(s, d, lambda i: (x[i] * d[i]).sum() / max((x[i] * x[i]).sum(), 1e-9))
            e["mean_abs_delta"] = float(np.abs(x).mean())
        res["ops"][op] = e
    print(json.dumps(res, indent=1)); json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
