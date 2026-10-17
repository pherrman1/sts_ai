#!/usr/bin/env python3
"""A20 Silver budget test (docs/experiments/evidence/silver_budget_a20_20261017/PLAN.md).

usage: analyze_silver_budget_a20.py report OUT_DIR [OUT_DIR ...]   (extracted worker tars: */out)
       analyze_silver_budget_a20.py selftest

Arms F (flat 10k, control), L (learned stopping), LP (L + gen-6 prior). A seed counts only when all three
arms finished with rc=0 and wrote its CSV row. Primary: reached Act 4 (act >= 4 or won), paired difference
L-F and LP-F with the Newcombe (1998, method 10) 95% interval; "non-inferior" when the lower bound > -0.05,
"loss shown" when the upper bound < 0, else NOT_SHOWN.
"""
import csv
import glob
import json
import math
import os
import re
import sys

ARMS = ("F", "L", "LP")
MARGIN = 0.05
Z = 1.959963984540054


def wilson(k, n):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return centre - half, centre + half


def newcombe_paired(a, b, c, d):
    """a: both, b: arm only, c: control only, d: neither. Returns (delta, lo, hi) for arm - control."""
    n = a + b + c + d
    p1, p2 = (a + b) / n, (a + c) / n
    l1, u1 = wilson(a + b, n)
    l2, u2 = wilson(a + c, n)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    phi = (a * d - b * c) / math.sqrt(den) if den > 0 else 0.0
    delta = p1 - p2
    lo = delta - math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    hi = delta + math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    return delta, max(-1.0, lo), min(1.0, hi)


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def verdict(lo, hi):
    if lo > -MARGIN:
        return "NON_INFERIOR"
    if hi < 0:
        return "LOSS_SHOWN"
    return "NOT_SHOWN"


def load(out_dirs):
    runs, problems, ooc = {}, [], {arm: {} for arm in ARMS}
    for out in out_dirs:
        for done in glob.glob(os.path.join(out, "*.done")):
            text = open(done).read()
            m = re.search(r"tag=(F|L|LP)-(\d+) rc=(-?\d+)", text)
            if not m:
                problems.append(f"bad done line {done}")
                continue
            arm, seed, rc = m.group(1), int(m.group(2)), int(m.group(3))
            base = done[:-5]
            row = None
            if rc == 0 and os.path.exists(base + ".csv"):
                for r in csv.DictReader(open(base + ".csv")):
                    if int(r["seed"]) == seed:
                        row = r
            if row is None:
                problems.append(f"{arm}-{seed} rc={rc} without a result row")
            runs[(arm, seed)] = row
            if os.path.exists(base + ".ooc.jsonl"):
                for line in open(base + ".ooc.jsonl"):
                    rec = json.loads(line)
                    if rec.get("kind") == "ooc":
                        ooc[arm][rec["by"]] = ooc[arm].get(rec["by"], 0) + 1
    return runs, problems, ooc


def summarize(runs):
    seeds = sorted({s for (_, s) in runs})
    valid = [s for s in seeds if all(runs.get((a, s)) is not None for a in ARMS)]

    def act4(r):
        return int(r["won"]) == 1 or int(r["act"]) >= 4

    res = {"seeds_seen": len(seeds), "seeds_valid": len(valid), "arms": {}, "comparisons": {}}
    for arm in ARMS:
        rows = [runs[(arm, s)] for s in valid]
        n = len(rows) or 1
        res["arms"][arm] = {
            "reached_act4": sum(act4(r) for r in rows),
            "heart_kills": sum(int(r["won"]) for r in rows),
            "mean_floor": sum(int(r["floor"]) for r in rows) / n,
            "mean_cpu_sec": sum(float(r["sec"]) for r in rows) / n,
        }
    for arm in ("L", "LP"):
        for name, f in (("reached_act4", act4), ("heart_kill", lambda r: int(r["won"]) == 1)):
            a = b = c = d = 0
            for s in valid:
                x, y = f(runs[(arm, s)]), f(runs[("F", s)])
                a += x and y
                b += x and not y
                c += y and not x
                d += not x and not y
            if not valid:
                continue
            delta, lo, hi = newcombe_paired(a, b, c, d)
            entry = {"table": [a, b, c, d], "delta": delta, "ci95": [lo, hi], "mcnemar_p": mcnemar_exact(b, c)}
            if name == "reached_act4":
                entry["verdict"] = verdict(lo, hi)
            res["comparisons"][f"{arm}-F {name}"] = entry
    return res


def selftest():
    # Wilson against a textbook value (k=81, n=263: 0.2553..0.3662, Newcombe 1998 single-proportion example).
    lo, hi = wilson(81, 263)
    assert abs(lo - 0.2553) < 5e-4 and abs(hi - 0.3662) < 5e-4, (lo, hi)
    # Paired: interval contains delta, sign-symmetric, and equal tables give 0 inside.
    for t in [(12, 9, 2, 21), (100, 20, 10, 382), (0, 0, 0, 5), (5, 0, 0, 0), (3, 4, 4, 9)]:
        d, l, h = newcombe_paired(*t)
        d2, l2, h2 = newcombe_paired(t[0], t[2], t[1], t[3])
        assert l <= d <= h and abs(d + d2) < 1e-12 and abs(l + h2) < 1e-12 and abs(h + l2) < 1e-12, t
    d, l, h = newcombe_paired(3, 4, 4, 9)
    assert d == 0 and l < 0 < h
    # (12, 9, 2, 21): 0.1591 (0.0182, 0.2892) from this implementation; not checked against a published value.
    d, l, h = newcombe_paired(12, 9, 2, 21)
    assert abs(d - 0.1591) < 5e-4 and abs(l - 0.0182) < 5e-4 and abs(h - 0.2892) < 5e-4, (d, l, h)
    assert abs(mcnemar_exact(9, 2) - 0.0654) < 5e-4
    assert verdict(-0.04, 0.03) == "NON_INFERIOR" and verdict(-0.09, -0.01) == "LOSS_SHOWN"
    assert verdict(-0.07, 0.02) == "NOT_SHOWN"
    print("selftest ok")


def main(argv):
    if len(argv) >= 2 and argv[1] == "selftest":
        selftest()
        return 0
    if len(argv) >= 3 and argv[1] == "report":
        runs, problems, ooc = load(argv[2:])
        res = summarize(runs)
        res["problems"] = problems
        res["ooc_decisions_by_policy"] = ooc
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
