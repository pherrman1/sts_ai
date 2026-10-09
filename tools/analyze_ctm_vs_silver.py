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

Post-state fields (PREFIX.samples.csv): every forecaster leaves samples of the
RAW post-combat state (CTM: 32 draws; Silver arms: their replicates); the
control replay is the truth. Per field, the Brier loss of the sample
distribution, 1 - 2 P(truth) + sum_v P(v)^2, is estimated without bias from
the match fraction and the matching fraction of distinct sample pairs. A dead
sample has the value DEATH in every field.
"""
import csv, json, sys
import numpy as np

ARMS = ("prior256", "prior64", "plain256", "teacher10k")
FIELDS = ("outcome", "hp", "maxHp", "gold", "potions", "relics", "deck", "stolenGold", "nonhp_joint", "joint")
SAMPLERS = ("ctm",) + ARMS
MARGIN = 0.10   # non-inferiority margin, fraction of the CTM loss


def sample_fields(r):
    if r["outcome"] == "DEATH":
        return {f: "DEATH" for f in FIELDS} | {"outcome": "DEATH"}
    v = {"outcome": r["outcome"], "hp": r["curHp"], "maxHp": r["maxHp"], "gold": r["gold"],
         "potions": r["potionCount"] + "|" + r["potions"], "relics": r["relics"], "deck": r["deckHash"],
         "stolenGold": r["stolenGold"]}
    v["nonhp_joint"] = "|".join(v[f] for f in ("maxHp", "gold", "potions", "relics", "deck", "stolenGold"))
    v["joint"] = v["hp"] + "|" + v["nonhp_joint"]
    return v


def field_scores(prefixes, valid_ids, ctm_ids):
    """Per state and sampler: Brier loss and match probability per field."""
    by = {}
    for p in prefixes:
        try:
            f = open(p + ".samples.csv")
        except FileNotFoundError:
            return None
        for r in csv.DictReader(f):
            if r["stateId"] in valid_ids:
                by.setdefault(r["stateId"], {}).setdefault(r["forecaster"], []).append(sample_fields(r))
    out = []
    for sid, fs in by.items():
        if sid not in ctm_ids or "control" not in fs or any(a not in fs for a in SAMPLERS):
            continue
        truth = fs["control"][0]
        row = {"seed": int(sid[1:].split("-")[0])}
        for name in SAMPLERS:
            xs = fs[name]; k = len(xs)
            for fld in FIELDS:
                vals = [x[fld] for x in xs]
                p_t = sum(v == truth[fld] for v in vals) / k
                counts = {}
                for v in vals:
                    counts[v] = counts.get(v, 0) + 1
                sq = sum(c * (c - 1) for c in counts.values()) / (k * (k - 1)) if k > 1 else float("nan")
                row[f"{name}:{fld}:brier"] = 1 - 2 * p_t + sq
                row[f"{name}:{fld}:match"] = p_t
        out.append(row)
    return out


def boot_field(rows, a, b, fld, rng, n=10000):
    seeds = sorted({r["seed"] for r in rows})
    per = {s: [0.0, 0] for s in seeds}
    for r in rows:
        per[r["seed"]][0] += r[f"{a}:{fld}:brier"] - r[f"{b}:{fld}:brier"]; per[r["seed"]][1] += 1
    arr = np.array([per[s] for s in seeds])
    draws = rng.integers(0, len(seeds), size=(n, len(seeds)))
    stats = arr[draws, 0].sum(1) / arr[draws, 1].sum(1)
    base = float(np.mean([r[f"{b}:{fld}:brier"] for r in rows]))
    d = float(arr[:, 0].sum() / arr[:, 1].sum())
    ci = [float(np.quantile(stats, .025)), float(np.quantile(stats, .975))]
    lab = ("SILVER_BETTER" if ci[1] < 0 else "CTM_BETTER" if ci[0] > 0
           else "SILVER_NONINFERIOR" if ci[1] < MARGIN * base else "INCONCLUSIVE")
    return {"diff": d, "ci95": ci, "label": lab}


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
        row = {"sid": sid, "seed": int(s["sourceSeed"]), "act": int(s["act"]), "room": s["roomClass"],
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
    valid_ids = {r["sid"] for r in rows}
    ctm_ids = {sid for sid, s in states.items() if s["ctmSupported"] == "1"}
    fr = field_scores(prefixes, valid_ids, ctm_ids)
    if fr:
        res["fields"] = {"n": len(fr), "brier": {}, "match": {}, "paired_vs_ctm": {}}
        for name in SAMPLERS:
            res["fields"]["brier"][name] = {f: float(np.mean([r[f"{name}:{f}:brier"] for r in fr])) for f in FIELDS}
            res["fields"]["match"][name] = {f: float(np.mean([r[f"{name}:{f}:match"] for r in fr])) for f in FIELDS}
        for name in ARMS:
            res["fields"]["paired_vs_ctm"][name] = {f: boot_field(fr, name, "ctm", f, rng) for f in FIELDS}
    json.dump(res, open(out, "w"), indent=2)
    print(json.dumps({"primary": res["primary"], "supported": {n: {k: round(v, 4) for k, v in res["supported"][n].items()} for n in names},
                      "labels": {n: res["paired_vs_ctm"][n]["label"] for n in names[1:]},
                      "field_brier": res.get("fields", {}).get("brier"),
                      "field_labels_prior256": {f: v["label"] for f, v in res.get("fields", {}).get("paired_vs_ctm", {}).get("prior256", {}).items()}},
                     indent=1))


if __name__ == "__main__":
    main()
