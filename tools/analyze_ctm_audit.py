#!/usr/bin/env python3
"""Analyze STS_OOC_CTM_AUDIT rows (#884): does the active CTM change OOC root rankings?

Each row is one searched real root. For every root action it holds N rollouts of the search's own leaf
(rollout3 + calibrated X2-B) in two arms: imagined combats drawn by the search's CTM stack ("ctm") and played by
production Silver ("silver"), stream r shared by actions and arms. Every imagined combat also carries the CTM's
forecast of its entry.

Reports
  * decision level: per root, Q by arm, CTM-best vs Silver-best, the Silver-measured regret of the CTM's pick with
    its paired SE, sibling-difference error E = D_ctm - D_silver per action pair with SE, and a split-half noise
    null (how often two independent halves of the same arm disagree on the best action);
  * combat level (silver arm): CTM death and HP forecasts against the Silver outcome, by room, with the observed
    error variance against the CTM's own predictive variance (stochastic spread vs model error).
Pooled CIs bootstrap over seeds (roots of one game are correlated).

usage: analyze_ctm_audit.py OUT.json AUDIT.jsonl [AUDIT.jsonl ...]
"""
import json
import math
import random
import sys
from collections import defaultdict

ROOMS = {0: "shop", 1: "rest", 2: "event", 3: "elite", 4: "monster", 5: "treasure", 6: "boss", 7: "boss_treasure", 8: "none"}


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def se(xs):
    return sd(xs) / math.sqrt(len(xs)) if len(xs) > 1 else float("nan")


def values(arm, action):
    out = []
    for v in arm["values"][str(action)]:
        out.append(v.get("value"))
    return out


def best(qs):
    return max(qs, key=lambda a: (qs[a], -a))


def root_stats(row):
    audit = row.get("audit") or {}
    arms = audit.get("arms") or {}
    if "ctm" not in arms or "silver" not in arms or "error" in audit:
        return None
    actions = [a["id"] for a in row["actions"] if not a.get("pruned")]
    actions = [a for a in row.get("audited", actions) if all(str(a) in arms[arm]["values"] for arm in ("ctm", "silver"))]
    vals = {arm: {a: values(arms[arm], a) for a in actions} for arm in ("ctm", "silver")}
    # A rollout that failed in either arm drops that stream r for every action (keeps the pairing).
    n = row["n"]
    keep = [r for r in range(n) if all(vals[arm][a][r] is not None for arm in vals for a in actions)]
    if len(keep) < 4 or len(actions) < 2:
        return None
    v = {arm: {a: [vals[arm][a][r] for r in keep] for a in actions} for arm in vals}
    q = {arm: {a: mean(v[arm][a]) for a in actions} for arm in v}
    best_ctm, best_sil = best(q["ctm"]), best(q["silver"])
    # Silver-measured regret of the CTM's pick, stream-paired within the Silver arm.
    regret_d = [v["silver"][best_sil][i] - v["silver"][best_ctm][i] for i in range(len(keep))]
    pairs = []
    for i, a in enumerate(actions):
        for b in actions[i + 1:]:
            dc = [v["ctm"][a][k] - v["ctm"][b][k] for k in range(len(keep))]
            ds = [v["silver"][a][k] - v["silver"][b][k] for k in range(len(keep))]
            e = [x - y for x, y in zip(dc, ds)]
            pairs.append({"a": a, "b": b, "dCtm": mean(dc), "seCtm": se(dc), "dSilver": mean(ds), "seSilver": se(ds),
                          "e": mean(e), "seE": se(e),
                          "signFlip": (mean(dc) > 0) != (mean(ds) > 0) and mean(dc) != 0 and mean(ds) != 0,
                          "silverSeparable": abs(mean(ds)) > 2 * se(ds) if se(ds) > 0 else mean(ds) != 0})
    # Split-half null: do two disjoint halves of one arm agree on the best action?
    half = len(keep) // 2
    split = {}
    for arm in v:
        h1 = {a: mean(v[arm][a][:half]) for a in actions}
        h2 = {a: mean(v[arm][a][half:2 * half]) for a in actions}
        split[arm] = best(h1) != best(h2)
    # Cross-fitted regret (primary, #884 PLAN): pick each arm's best action on one half of the streams and score the
    # two picks on the other half of the Silver arm; average both directions. Zero in expectation when the CTM arm's
    # choices are as good as the Silver arm's, so selection noise does not inflate it. Cross-fitted E: orient each
    # pair by the CTM's sign on one half and measure D_ctm - D_silver on the other.
    halves = [list(range(half)), list(range(half, 2 * half))]
    xregret, xe = [], []
    for pick, score in ((0, 1), (1, 0)):
        qp = {arm: {a: mean([v[arm][a][i] for i in halves[pick]]) for a in actions} for arm in v}
        bc, bs = best(qp["ctm"]), best(qp["silver"])
        xregret.append(mean([v["silver"][bs][i] - v["silver"][bc][i] for i in halves[score]]))
        for i, a in enumerate(actions):
            for b in actions[i + 1:]:
                sign = 1 if qp["ctm"][a] >= qp["ctm"][b] else -1
                xe.append(sign * mean([(v["ctm"][a][k] - v["ctm"][b][k]) - (v["silver"][a][k] - v["silver"][b][k])
                                       for k in halves[score]]))
    selected = row.get("selectedId")
    labels = {a["id"]: a.get("label", "") for a in row["actions"]}
    return {"seed": row["seed"], "decision": row["decisionIndex"], "act": row["act"], "floor": row["floor"],
            "n": len(keep), "actions": actions, "labels": labels, "qCtm": q["ctm"], "qSilver": q["silver"],
            "bestCtm": best_ctm, "bestSilver": best_sil, "selected": selected,
            "reversal": best_ctm != best_sil, "regret": mean(regret_d), "regretSe": se(regret_d),
            "xRegret": mean(xregret), "xOrientedE": mean(xe) if xe else float("nan"),
            "materialReversal": best_ctm != best_sil and mean(regret_d) > 2 * se(regret_d) if se(regret_d) > 0 else False,
            "searchRegret": (mean([v["silver"][best_sil][i] - v["silver"][selected][i] for i in range(len(keep))])
                             if selected in v["silver"] else None),
            "splitFlipCtm": split["ctm"], "splitFlipSilver": split["silver"], "pairs": pairs,
            "cpuCtm": arms["ctm"].get("cpuSeconds"), "cpuSilver": arms["silver"].get("cpuSeconds")}


def combat_rows(row):
    arms = ((row.get("audit") or {}).get("arms")) or {}
    for arm, data in arms.items():
        for c in data.get("combats", []):
            c = dict(c)
            c["arm"] = arm
            c["seed"] = row["seed"]
            yield c


def combat_summary(rows):
    """CTM forecast vs drawn outcome for rows of one arm and group."""
    scored = [c for c in rows if c.get("ctmSupported") and c.get("outcome") in ("death", "victory")]
    if not scored:
        return {"n": 0}
    death = [1.0 if c["outcome"] == "death" else 0.0 for c in scored]
    p = [min(max(float(c["pDeath"]), 1e-6), 1 - 1e-6) for c in scored]
    brier = mean([(x - y) ** 2 for x, y in zip(p, death)])
    logloss = mean([-(y * math.log(x) + (1 - y) * math.log(1 - x)) for x, y in zip(p, death)])
    wins = [c for c in scored if c["outcome"] == "victory"]
    hp_err = [c["postHp"] - c["hpWinMean"] for c in wins]
    # Observed squared error vs the CTM's own predictive variance (given a win): ratio ~1 means the error is the
    # fight's own randomness at the CTM's stated spread; >1 means extra (model) error.
    pred_var = [c["hpWinSd"] ** 2 for c in wins]
    # PIT of the drawn HP under the CTM's win histogram: uniform (mean 0.5, sd 0.289) when calibrated.
    pit = [c["hpPit"] for c in wins if "hpPit" in c]
    bins = [0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0001]
    calibration = []
    for lo, hi in zip(bins, bins[1:]):
        cell = [(x, y) for x, y in zip(p, death) if lo <= x < hi]
        if cell:
            calibration.append({"bin": [lo, min(hi, 1)], "n": len(cell), "predicted": mean([x for x, _ in cell]),
                                "observed": mean([y for _, y in cell])})
    return {"n": len(scored), "deathObserved": mean(death), "deathPredicted": mean(p), "brier": brier,
            "logLoss": logloss, "deathCalibration": calibration, "wins": len(wins),
            "hpWinBias": mean(hp_err), "hpWinBiasSe": se(hp_err),
            "hpWinRmse": math.sqrt(mean([e * e for e in hp_err])) if hp_err else float("nan"),
            "hpWinPredSd": math.sqrt(mean(pred_var)) if pred_var else float("nan"),
            "hpVarianceRatio": (mean([e * e for e in hp_err]) / mean(pred_var)) if pred_var and mean(pred_var) > 0
            else float("nan"), "hpPitMean": mean(pit), "hpPitSd": sd(pit)}


def bootstrap(roots, stat, reps=2000, seed=884):
    by_seed = defaultdict(list)
    for r in roots:
        by_seed[r["seed"]].append(r)
    seeds = sorted(by_seed)
    rng = random.Random(seed)
    out = []
    for _ in range(reps):
        sample = [r for s in (rng.choice(seeds) for _ in seeds) for r in by_seed[s]]
        x = stat(sample)
        if x == x:
            out.append(x)
    out.sort()
    if not out:
        return [float("nan"), float("nan")]
    return [out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rows = []
    for path in sys.argv[2:]:
        with open(path) as f:
            rows += [json.loads(line) for line in f if line.strip()]
    roots = [s for s in (root_stats(r) for r in rows) if s]
    combats = [c for r in rows for c in combat_rows(r)]
    pairs = [dict(p, seed=r["seed"]) for r in roots for p in r["pairs"]]

    def rate(key):
        return lambda rs: mean([1.0 if r[key] else 0.0 for r in rs])

    def oriented_e(rs):
        # E oriented on the CTM's preferred side: positive means the CTM over-states the gap it acts on.
        es = [(p["e"] if p["dCtm"] >= 0 else -p["e"]) for r in rs for p in r["pairs"]]
        return mean(es)

    def slope(rs):
        xs = [p["dSilver"] for r in rs for p in r["pairs"]]
        ys = [p["dCtm"] for r in rs for p in r["pairs"]]
        mx, my = mean(xs), mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 0 else float("nan")

    decision = {
        "roots": len(roots), "seeds": len({r["seed"] for r in roots}), "pairs": len(pairs),
        "reversalRate": mean([1.0 if r["reversal"] else 0.0 for r in roots]),
        "reversalRateCi": bootstrap(roots, rate("reversal")),
        "materialReversalRate": mean([1.0 if r["materialReversal"] else 0.0 for r in roots]),
        "materialReversalRateCi": bootstrap(roots, rate("materialReversal")),
        "splitHalfFlipCtm": mean([1.0 if r["splitFlipCtm"] else 0.0 for r in roots]),
        "splitHalfFlipSilver": mean([1.0 if r["splitFlipSilver"] else 0.0 for r in roots]),
        "crossFitRegret": mean([r["xRegret"] for r in roots]),
        "crossFitRegretCi": bootstrap(roots, lambda rs: mean([r["xRegret"] for r in rs])),
        "crossFitOrientedE": mean([r["xOrientedE"] for r in roots]),
        "crossFitOrientedECi": bootstrap(roots, lambda rs: mean([r["xOrientedE"] for r in rs])),
        "meanRegret": mean([r["regret"] for r in roots]),
        "meanRegretCi": bootstrap(roots, lambda rs: mean([r["regret"] for r in rs])),
        "meanSearchRegret": mean([r["searchRegret"] for r in roots if r["searchRegret"] is not None]),
        "pairSignFlipRate": mean([1.0 if p["signFlip"] else 0.0 for p in pairs]),
        "pairSignFlipRateSilverSeparable": mean([1.0 if p["signFlip"] else 0.0 for p in pairs if p["silverSeparable"]]),
        "silverSeparablePairs": sum(1 for p in pairs if p["silverSeparable"]),
        "orientedE": oriented_e(roots), "orientedECi": bootstrap(roots, oriented_e),
        "slopeDctmOnDsilver": slope(roots), "slopeCi": bootstrap(roots, slope),
        "medianAbsDSilver": sorted(abs(p["dSilver"]) for p in pairs)[len(pairs) // 2] if pairs else None,
        "medianSeDSilver": sorted(p["seSilver"] for p in pairs)[len(pairs) // 2] if pairs else None,
        "cpuCtm": sum(r["cpuCtm"] or 0 for r in roots), "cpuSilver": sum(r["cpuSilver"] or 0 for r in roots),
    }
    by_room = defaultdict(list)
    for c in combats:
        by_room[(c["arm"], ROOMS.get(c.get("room"), str(c.get("room"))))].append(c)
    combat = {"silver": combat_summary([c for c in combats if c["arm"] == "silver"]),
              "ctmSelfCheck": combat_summary([c for c in combats if c["arm"] == "ctm"]),
              "byRoom": {f"{arm}:{room}": combat_summary(cs) for (arm, room), cs in sorted(by_room.items())},
              "unsupportedSilverArm": sum(1 for c in combats if c["arm"] == "silver" and not c.get("ctmSupported")),
              "outcomes": {arm: {o: sum(1 for c in combats if c["arm"] == arm and c.get("outcome") == o)
                                 for o in ("death", "victory", "escape", "unsupported")} for arm in ("ctm", "silver")}}
    report = {"schema": "ctm-audit-report-v1", "inputs": sys.argv[2:], "decision": decision, "combat": combat,
              "roots": roots}
    with open(sys.argv[1], "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({"decision": decision, "combat": {k: combat[k] for k in ("silver", "ctmSelfCheck",
                                                                                 "unsupportedSilverArm", "outcomes")}},
                     indent=1))


if __name__ == "__main__":
    main()
