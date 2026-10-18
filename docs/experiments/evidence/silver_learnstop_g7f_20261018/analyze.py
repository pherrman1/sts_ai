#!/usr/bin/env python3
"""Learned stopping + gen-7f table/prior at A20 (PREREG.md in this folder).

usage: analyze.py report UNIT_OUT_ROOT [...]   (extracted worker tars; *.done files are found recursively)
       analyze.py selftest

Arms F10 (flat 10k, control), F25 (flat 2.5k), L (learned stopping, checkpoints to 10k). A seed counts only
when all three arms finished with rc=0 and wrote its CSV row. Primary: reached Act 4 (act >= 4 or won),
paired L-F10 with the Newcombe (1998, method 10) 95% interval and the verdict rule of
tools/analyze_silver_budget_a20.py (NON_INFERIOR when the lower bound > -5 pp, LOSS_SHOWN when the upper bound
< 0, else NOT_SHOWN). F25-F10 gets the same rule (secondary); L-F25 is descriptive.
"""
import csv
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools"))
from analyze_silver_budget_a20 import mcnemar_exact, newcombe_paired, selftest as stats_selftest, verdict  # noqa: E402

ARMS = ("F10", "F25", "L")
COMPARISONS = (("L", "F10", True), ("F25", "F10", True), ("L", "F25", False))


def load(roots):
    runs, problems, ooc = {}, [], {arm: {} for arm in ARMS}
    for root in roots:
        for done in sorted(glob.glob(os.path.join(root, "**", "*.done"), recursive=True)):
            m = re.search(r"tag=(F10|F25|L)-(\d+) rc=(-?\d+)", open(done).read())
            if not m:
                problems.append(f"bad done line {done}")
                continue
            arm, seed, rc = m.group(1), int(m.group(2)), int(m.group(3))
            if (arm, seed) in runs:
                problems.append(f"duplicate unit {arm}-{seed}")
            base, row = done[:-5], None
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


def act4(r):
    return int(r["won"]) == 1 or int(r["act"]) >= 4


def won(r):
    return int(r["won"]) == 1


def summarize(runs):
    seeds = sorted({s for (_, s) in runs})
    valid = [s for s in seeds if all(runs.get((a, s)) is not None for a in ARMS)]
    res = {"seeds_seen": len(seeds), "seeds_valid": len(valid),
           "seeds_dropped": [s for s in seeds if s not in valid], "arms": {}, "comparisons": {}}
    n = len(valid) or 1
    for arm in ARMS:
        rows = [runs[(arm, s)] for s in valid]
        res["arms"][arm] = {
            "reached_act4": sum(act4(r) for r in rows),
            "heart_kills": sum(won(r) for r in rows),
            "mean_floor": sum(int(r["floor"]) for r in rows) / n,
            "mean_cpu_sec": sum(float(r["sec"]) for r in rows) / n,
        }
    if not valid:
        return res
    for arm, ctl, gated in COMPARISONS:
        for name, f in (("reached_act4", act4), ("heart_kill", won)):
            a = b = c = d = 0
            for s in valid:
                x, y = f(runs[(arm, s)]), f(runs[(ctl, s)])
                a += x and y
                b += x and not y
                c += y and not x
                d += not x and not y
            delta, lo, hi = newcombe_paired(a, b, c, d)
            entry = {"table": [a, b, c, d], "delta": delta, "ci95": [lo, hi], "mcnemar_p": mcnemar_exact(b, c)}
            if gated and name == "reached_act4":
                entry["verdict"] = verdict(lo, hi)
            res["comparisons"][f"{arm}-{ctl} {name}"] = entry
        res["comparisons"][f"{arm}/{ctl} cpu_ratio"] = res["arms"][arm]["mean_cpu_sec"] / max(
            1e-9, res["arms"][ctl]["mean_cpu_sec"])
    return res


def selftest():
    stats_selftest()
    row = lambda act, w: {"won": str(w), "act": str(act), "floor": "40", "sec": "10"}
    runs = {("F10", 1): row(4, 1), ("F25", 1): row(3, 0), ("L", 1): row(4, 0),
            ("F10", 2): row(2, 0), ("F25", 2): row(4, 0), ("L", 2): None}
    res = summarize(runs)
    assert res["seeds_valid"] == 1 and res["seeds_dropped"] == [2], res
    assert res["comparisons"]["L-F10 reached_act4"]["table"] == [1, 0, 0, 0]
    assert res["comparisons"]["F25-F10 reached_act4"]["table"] == [0, 0, 1, 0]
    print("campaign selftest ok")


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
