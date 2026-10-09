#!/usr/bin/env python3
"""Score CTM and low-sim Silver as combat-outcome forecasters (ledger §407).

usage: python3 tools/analyze_ctm_vs_silver.py OUT.json PREFIX [PREFIX ...]
Each PREFIX names one ``one_combat ctmsilvergen`` shard (PREFIX.states.csv,
PREFIX.arms.csv). Ground truth is the source fight (exact-10k Silver, real
hidden future): d = 1 on a loss, y = terminal HP on a win and 0 on a loss.
A forecast is (p, h): CTM gives p = P(death), h = (1 - p) * E[HP | win];
a Silver arm with K redrawn replicates gives the loss fraction and mean y.
Losses are death Brier (p - d)^2 and HP squared error (h - y)^2. Paired
differences use a bootstrap over source seeds (10,000 resamples, seed 0).
"""
import csv, json, sys
import numpy as np

ARMS = ("prior256", "prior64", "plain256", "teacher10k")
MARGIN = 0.10   # non-inferiority margin, fraction of the CTM loss


def load(prefixes):
    states, arms = {}, {}
    for p in prefixes:
        with open(p + ".states.csv") as f:
            for r in csv.DictReader(f):
                states[r["stateId"]] = r
        with open(p + ".arms.csv") as f:
            for r in csv.DictReader(f):
                arms.setdefault(r["stateId"], []).append(r)
    return states, arms


def forecasts(states, arms):
    rows = []
    for sid, s in states.items():
        if s["sourceValid"] != "1" or int(s["sourceWon"]) not in (0, 1):
            continue
        rs = arms.get(sid, [])
        if not rs or any(r["valid"] != "1" for r in rs):
            continue
        d = 1 - int(s["sourceWon"])
        y = int(s["sourceTerminalHp"]) if d == 0 else 0
        row = {"seed": int(s["sourceSeed"]), "act": int(s["act"]), "room": s["roomClass"],
               "d": d, "y": y, "ctm": s["ctmSupported"] == "1"}
        if row["ctm"]:
            row["ctm_p"] = float(s["ctmPDeath"]); row["ctm_h"] = float(s["ctmExpectedHp"])
            row["ctm_us"] = float(s["ctmForecastCpuUs"]); row["ctm_sample_us"] = float(s["ctmSampleCpuUs"])
        for a in ARMS:
            reps = sorted((r for r in rs if r["arm"] == a), key=lambda r: int(r["k"]))
            if not reps:
                continue
            dd = np.array([1 - int(r["won"]) for r in reps], float)
            yy = np.array([int(r["terminalHp"]) if r["won"] == "1" else 0 for r in reps], float)
            row[a + "_p"], row[a + "_h"] = dd.mean(), yy.mean()
            row[a + "1_p"], row[a + "1_h"] = dd[0], yy[0]
            row[a + "_cpu"] = sum(float(r["cpuSeconds"]) for r in reps)
            row[a + "1_cpu"] = float(reps[0]["cpuSeconds"])
            row[a + "_k"] = len(reps)
        rows.append(row)
    return rows


def losses(rows, name):
    p = np.array([r[name + "_p"] for r in rows]); h = np.array([r[name + "_h"] for r in rows])
    d = np.array([r["d"] for r in rows], float); y = np.array([r["y"] for r in rows], float)
    return (p - d) ** 2, (h - y) ** 2, p - d, h - y


def boot_diff(rows, a, b, rng, n=10000):
    seeds = sorted({r["seed"] for r in rows})
    idx = {s: [i for i, r in enumerate(rows) if r["seed"] == s] for s in seeds}
    la, lb = losses(rows, a), losses(rows, b)
    out = {}
    for j, m in ((0, "brier"), (1, "hp_mse")):
        diff = la[j] - lb[j]
        per = np.array([[diff[idx[s]].sum(), len(idx[s])] for s in seeds])
        draws = rng.integers(0, len(seeds), size=(n, len(seeds)))
        num = per[draws, 0].sum(1); den = per[draws, 1].sum(1)
        stats = num / den
        out[m] = {"diff": float(diff.mean()), "ci95": [float(np.quantile(stats, .025)), float(np.quantile(stats, .975))],
                  "rel_to_b": float(diff.mean() / lb[j].mean())}
    return out


def summary(rows, name):
    b, s, bd, bh = losses(rows, name)
    out = {"n": len(rows), "brier": float(b.mean()), "hp_mse": float(s.mean()), "hp_rmse": float(np.sqrt(s.mean())),
           "hp_mae": float(np.sqrt(s).mean()), "death_bias": float(bd.mean()), "hp_bias": float(bh.mean())}
    base = name[:-1] if name.endswith("1") and name[:-1] in ARMS else name
    if name == "ctm":
        out["cpu_ms_forecast"] = float(np.mean([r["ctm_us"] for r in rows]) / 1e3)
        out["cpu_ms_sample"] = float(np.mean([r["ctm_sample_us"] for r in rows]) / 1e3)
    else:
        key = name + "_cpu"
        out["cpu_ms_forecast"] = float(np.mean([r[key] for r in rows]) * 1e3)
        out["replicates"] = 1 if name.endswith("1") else int(rows[0][base + "_k"])
    return out


def label(d):
    b, m = d["brier"], d["hp_mse"]
    if b["ci95"][1] < 0 and m["ci95"][1] < 0:
        return "SILVER_BETTER"
    if b["ci95"][0] > 0 or m["ci95"][0] > 0:
        return "CTM_BETTER"
    if b["ci95"][1] < MARGIN * d["_ctm_brier"] and m["ci95"][1] < MARGIN * d["_ctm_hp_mse"]:
        return "SILVER_NONINFERIOR"
    return "INCONCLUSIVE"


def main():
    out, prefixes = sys.argv[1], sys.argv[2:]
    states, arms = load(prefixes)
    rows = forecasts(states, arms)
    sup = [r for r in rows if r["ctm"]]
    rng = np.random.default_rng(0)
    names = ["ctm"] + [a for a in ARMS] + [a + "1" for a in ARMS]
    res = {"states_total": len(states), "states_valid": len(rows), "states_ctm_supported": len(sup),
           "unsupported_reasons": {}, "supported": {n: summary(sup, n) for n in names},
           "all_valid": {n: summary(rows, n) for n in names if n != "ctm"}}
    for s in states.values():
        if s["ctmSupported"] != "1":
            res["unsupported_reasons"][s["ctmReason"]] = res["unsupported_reasons"].get(s["ctmReason"], 0) + 1
    ctm = res["supported"]["ctm"]
    res["paired_vs_ctm"] = {}
    for n in names[1:]:
        d = boot_diff(sup, n, "ctm", rng)
        d["_ctm_brier"], d["_ctm_hp_mse"] = ctm["brier"], ctm["hp_mse"]
        d["label"] = label(d)
        del d["_ctm_brier"], d["_ctm_hp_mse"]
        res["paired_vs_ctm"][n] = d
    res["primary"] = {"arm": "prior256", "label": res["paired_vs_ctm"]["prior256"]["label"],
                      "cpu_ratio_vs_ctm_forecast": res["supported"]["prior256"]["cpu_ms_forecast"] / ctm["cpu_ms_forecast"]}
    res["noise_floor_hp_mse"] = res["supported"]["teacher10k1"]["hp_mse"] / 2
    res["noise_floor_brier"] = res["supported"]["teacher10k1"]["brier"] / 2
    by_act = {}
    for act in sorted({r["act"] for r in sup}):
        sub = [r for r in sup if r["act"] == act]
        by_act[act] = {n: {k: summary(sub, n)[k] for k in ("n", "brier", "hp_rmse")} for n in ("ctm", "prior256", "teacher10k1")}
    res["by_act"] = by_act
    json.dump(res, open(out, "w"), indent=2)
    print(json.dumps({"primary": res["primary"], "supported": {n: {k: round(v, 4) for k, v in res["supported"][n].items()} for n in names},
                      "labels": {n: res["paired_vs_ctm"][n]["label"] for n in names[1:]}}, indent=1))


if __name__ == "__main__":
    main()
