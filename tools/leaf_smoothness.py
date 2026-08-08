#!/usr/bin/env python3
"""Delta-V smoothness / shaping diagnostics for the two combat V-nets (Task 6).

Consumes a rollouttrace CSV (`one_combat rollouttrace`): for every recorded
Searcher3 leaf, one actual search-policy rollout was run inside
BattleScumSearcher3 (search::g_onRolloutStep fires after every executed
rollout action), so each (seed, fightIdx, decIdx, obsHash) key is a real
rollout trajectory with consecutive states. This script compares how the
deployed end-HP vnet and the direct utility-R vnet behave along those
trajectories:

  * smoothness: variance/std of delta V = V(s_{t+1}) - V(s_t), and the
    scale-free lag-1 autocorrelation of V within trajectories (higher =
    smoother);
  * sign consistency with obvious combat progress: delta V > 0 when enemy HP
    (monSumHp) fell while the player took no damage (curHp not down);
  * response to player HP loss: delta V < 0 when curHp fell;
  * response to setup/scaling: delta V distribution on steps where strength
    increased (scaling powers like Demon Form/Inflame raise strength; the
    trace records strength but not individual power flags — a documented
    limitation);
  * behavior near the survival/death boundary: steps with hpFrac < 0.25.

Caveat: delta V is on each model's own scale (endHp on HP scale, utilityR on
the 0|50+HP terminal scale), so raw std(delta V) is NOT directly comparable
across models — the autocorrelation and sign-consistency fractions are the
scale-free comparisons.

Output: human-readable comparison table; JSON summary with --json.
"""
import argparse
import csv
import json
import math
import random
import sys

from collections import defaultdict


def _f(x):
    try:
        v = float(x)
        return v
    except (TypeError, ValueError):
        return float("nan")


def load_traces(path):
    """Group rollouttrace rows into trajectories keyed by
    (seed, fightIdx, decIdx, obsHash), ordered by step."""
    trajs = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            key = (r["seed"], r["fightIdx"], r["decIdx"], r["obsHash"])
            trajs[key].append(r)
    out = {}
    for key, rows in trajs.items():
        rows.sort(key=lambda r: int(_f(r.get("step", "nan"))))
        out[key] = rows
    return out


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: (xs[i], i))
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(a, b):
    if len(a) < 2:
        return float("nan")
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa == 0 or sb == 0:
        return float("nan")
    return cov / (sa * sb)


def lag1_autocorr(vals):
    """Pearson(V_t, V_{t+1}) along one trajectory; NaN when too short/flat."""
    if len(vals) < 3:
        return float("nan")
    a = vals[:-1]
    b = vals[1:]
    if len(set(a)) == 1 or len(set(b)) == 1:
        return float("nan")
    return pearson(a, b)


def per_model_metrics(traces, col):
    """Pooled step-level metrics for one model over all trajectories."""
    deltas = []            # (traj_key, t, deltaV, curHp, monSumHp, prevMon, prevHp, hpFrac, strength, prevStrength, isTerminalTo)
    autocorrs = []
    for key, rows in traces.items():
        vals = []
        for r in rows:
            v = _f(r.get(col, "nan"))
            vals.append(v)
        a = lag1_autocorr(vals)
        if not math.isnan(a):
            autocorrs.append(a)
        for t in range(1, len(rows)):
            v_prev = vals[t - 1]
            v_cur = vals[t]
            if math.isnan(v_prev) or math.isnan(v_cur):
                continue
            r0 = rows[t - 1]
            r1 = rows[t]
            deltas.append({
                "traj": key, "t": t, "deltaV": v_cur - v_prev,
                "curHp": _f(r1.get("curHp")), "prevHp": _f(r0.get("curHp")),
                "monSumHp": _f(r1.get("monSumHp")), "prevMon": _f(r0.get("monSumHp")),
                "maxHp": _f(r1.get("maxHp")),
                "strength": _f(r1.get("strength")), "prevStrength": _f(r0.get("strength")),
                "terminal": _f(r1.get("isTerminal")),
            })
    m = {"nDeltas": len(deltas)}
    if not deltas:
        return m
    dv = [d["deltaV"] for d in deltas]
    m["meanDelta"] = float(sum(dv) / len(dv))
    m["stdDelta"] = float(math.sqrt(sum((x - m["meanDelta"]) ** 2 for x in dv) / len(dv)))
    m["lag1Autocorr"] = (float(sum(a for a in autocorrs) / len(autocorrs))
                         if autocorrs else float("nan"))
    m["nTrajAutocorr"] = len(autocorrs)

    def frac(cond):
        sel = [d for d in deltas if cond(d)]
        if not sel:
            return float("nan"), 0
        pos = sum(1 for d in sel if d["deltaV"] > 0)
        return pos / len(sel), len(sel)

    # enemy HP fell, player took no damage
    m["signConsistentProgress"] = frac(
        lambda d: d["monSumHp"] < d["prevMon"] and d["curHp"] >= d["prevHp"])
    # player HP fell
    m["negOnHpLoss"] = frac(lambda d: d["curHp"] < d["prevHp"])
    # strength increased (scaling/setup powers)
    m["onStrengthUp"] = frac(lambda d: d["strength"] > d["prevStrength"])
    # near the survival boundary (hpFrac < 0.25) — both entering and leaving
    low = [d for d in deltas if d["maxHp"] > 0 and d["curHp"] / d["maxHp"] < 0.25]
    m["nNearDeath"] = len(low)
    if low:
        ldv = [d["deltaV"] for d in low]
        m["nearDeathMeanDelta"] = float(sum(ldv) / len(ldv))
        m["nearDeathStdDelta"] = float(
            math.sqrt(sum((x - m["nearDeathMeanDelta"]) ** 2 for x in ldv) / len(ldv)))
    else:
        m["nearDeathMeanDelta"] = float("nan")
        m["nearDeathStdDelta"] = float("nan")
    # terminal-step transitions (delta into the terminal state)
    term = [d for d in deltas if d["terminal"] == 1]
    m["nTerminalSteps"] = len(term)
    if term:
        td = [d["deltaV"] for d in term]
        m["terminalMeanDelta"] = float(sum(td) / len(td))
    else:
        m["terminalMeanDelta"] = float("nan")
    return m


def report(metrics, args):
    print("=" * 78)
    print("Delta-V smoothness / shaping diagnostics (rollouttrace, Task 6)")
    print("=" * 78)
    print("reference: consecutive actual Searcher3 rollout states per recorded leaf")
    print("")
    hdr = (f"{'model':<10} {'nDeltas':>8} {'mean dV':>9} {'std dV':>8} "
           f"{'lag1AC':>8} {'progSign':>10} {'negOnHpLoss':>12} {'strUp':>8}")
    print(hdr)
    for model in ("endHp", "utilityR"):
        m = metrics[model]
        p_frac = lambda k: (f"{m[k][0]:.3f} (n={m[k][1]})" if m[k][1] else "n/a")
        print(f"{model:<10} {m['nDeltas']:>8} {m['meanDelta']:>9.3f} {m['stdDelta']:>8.3f} "
              f"{m['lag1Autocorr']:>8.3f} {p_frac('signConsistentProgress'):>10} "
              f"{p_frac('negOnHpLoss'):>12} {p_frac('onStrengthUp'):>8}")
    print("")
    print("  progSign    = fraction deltaV > 0 when enemy HP fell and the player")
    print("                took no damage (obvious combat progress)")
    print("  negOnHpLoss = fraction deltaV < 0 when the player lost HP")
    print("  strUp       = fraction deltaV > 0 when strength increased (scaling/setup)")
    print("  lag1AC      = mean lag-1 autocorrelation of V along trajectories")
    print("                (scale-free smoothness; higher = smoother)")
    print("  std dV is on each model's OWN scale (endHp vs 0|50+HP) — NOT")
    print("  directly comparable across models; use lag1AC and the sign fractions.")
    print("")
    for model in ("endHp", "utilityR"):
        m = metrics[model]
        print(f"{model}: near-death steps {m['nNearDeath']} "
              f"(mean dV {m['nearDeathMeanDelta']:.3f}, std {m['nearDeathStdDelta']:.3f}); "
              f"terminal steps {m['nTerminalSteps']} "
              f"(mean dV {m['terminalMeanDelta']:.3f})")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(metrics, f, indent=2, sort_keys=True)
        print(f"[leaf_smoothness] JSON summary -> {args.json}")


def self_test():
    """Synthetic trajectories: endHp model smooth + progress-consistent;
    utilityR model jumpy and anti-consistent."""
    rng = random.Random(11)
    trajs = {}
    for g in range(4):
        key = (str(2000 + g), "0", "0", str(g))
        rows = []
        mon = 50.0
        hp = 50.0
        for t in range(8):
            mon = max(5.0, mon - rng.uniform(0, 4))
            # endHp: smooth, tracks progress (enemy HP down -> value up)
            endhp = 10 + (50 - mon) * 0.8 + rng.gauss(0, 0.3)
            util = 60 + rng.gauss(0, 30)          # jumpy
            prev_mon = float(rows[-1]["monSumHp"]) if rows else mon + 1
            rows.append({
                "step": str(t), "curHp": f"{hp:.1f}", "prevHp": f"{hp:.1f}",
                "maxHp": "80", "monSumHp": f"{mon:.1f}", "prevMon": f"{prev_mon:.1f}",
                "strength": "0", "prevStrength": "0", "isTerminal": "0",
                "endHp_pred": f"{endhp:.4f}", "utilityR_pred": f"{util:.4f}",
            })
        trajs[key] = rows
    metrics = {m: per_model_metrics(trajs, m + "_pred") for m in ("endHp", "utilityR")}
    a = metrics["endHp"]["signConsistentProgress"][0]
    b = metrics["utilityR"]["signConsistentProgress"][0]
    ac_e = metrics["endHp"]["lag1Autocorr"]
    ac_u = metrics["utilityR"]["lag1Autocorr"]
    print(f"self-test: endHp prog-sign {a:.2f} lag1AC {ac_e:.2f}; "
          f"utilityR prog-sign {b:.2f} lag1AC {ac_u:.2f}")
    assert a > 0.8, f"smooth progress-tracking model should be sign-consistent, got {a}"
    assert b < 0.7, f"jumpy model should be less consistent, got {b}"
    assert ac_e > ac_u, f"smooth model should have higher lag-1 autocorrelation"
    print("leaf_smoothness self-test PASS")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", default="build/rollouttrace.csv",
                    help="rollouttrace CSV (default build/rollouttrace.csv)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    traces = load_traces(args.trace)
    if not traces:
        print(f"leaf_smoothness: no trajectories in {args.trace}", file=sys.stderr)
        return 2
    print(f"[leaf_smoothness] {len(traces)} trajectories from {args.trace}")
    metrics = {m: per_model_metrics(traces, m + "_pred") for m in ("endHp", "utilityR")}
    report(metrics, args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
