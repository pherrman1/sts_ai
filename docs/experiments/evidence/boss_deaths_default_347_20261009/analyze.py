#!/usr/bin/env python3
"""Classify #347 default-stack boss deaths by fresh-planner replay wins (PLAN.md).

Usage: analyze.py SELECTION.json RUN_DIR [--out report.json]
Only VALID entries (entry.json status) are classified; invalid ones are listed.
"""
import argparse, csv, json, os, random, sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
BOOT_REPS, BOOT_SEED = 10000, 20261009


def entry_class(wins, reps):
    if wins == 0:
        return "DOOMED"
    return "WINNABLE" if 2 * wins >= reps else "MARGINAL"


def summary_field(summary, key):
    for part in summary.split(";"):
        if part.startswith(key + "="):
            return part[len(key) + 1:]
    return ""


def bootstrap_mean(values):
    rng = random.Random(BOOT_SEED)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT_REPS))
    return [means[int(0.025 * BOOT_REPS)], means[int(0.975 * BOOT_REPS) - 1]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("selection")
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    sel = json.load(open(a.selection))
    reps = sel["plannerReps"]
    entries, invalid = [], []
    for spec in sel["selected"]:
        sid = spec["stateId"]
        ej_path = os.path.join(a.run_dir, sid + ".entry.json")
        if not os.path.exists(ej_path):
            invalid.append({"stateId": sid, "failures": ["missing_output"]})
            continue
        ej = json.load(open(ej_path))
        if ej["status"] != "VALID":
            invalid.append({"stateId": sid, "failures": ej["failures"]})
            continue
        rows = list(csv.DictReader(open(os.path.join(a.run_dir, sid + ".rows.csv"), newline="")))
        fresh = [r for r in rows if r["kind"] == "fresh"]
        if sorted(int(r["rep"]) for r in fresh) != list(range(reps)):
            sys.exit(f"{sid}: fresh reps incomplete")
        wins = sum(int(r["won"]) for r in fresh)
        summary = ej["entrySummary"]
        deck = [c for c in summary_field(summary, "deck").split("|") if c]
        potions = [p for p in summary_field(summary, "potions").split("|") if p and p != "EMPTY_POTION_SLOT"]
        won_hp = [int(r["terminalHp"]) for r in fresh if r["won"] == "1"]
        entries.append({
            "stateId": sid, "seed": spec["seed"], "act": spec["act"], "boss": spec["boss"],
            "floor": ej["floor"], "hp": int(summary_field(summary, "hp")),
            "maxHp": int(summary_field(summary, "maxHp")), "potions": potions,
            "relics": len([r for r in summary_field(summary, "relics").split("|") if r]),
            "deck": len(deck), "upgraded": sum(c.endswith("+") for c in deck),
            "freshWins": wins, "reps": reps, "class": entry_class(wins, reps),
            "meanTerminalHpWhenWon": sum(won_hp) / len(won_hp) if won_hp else None,
            "freshCpuSeconds": sum(float(r["cpuSeconds"]) for r in fresh)})
    n = len(entries)
    if n == 0:
        sys.exit("no valid entries")
    rates = [e["freshWins"] / reps for e in entries]
    classes = {c: sum(e["class"] == c for e in entries) for c in ("DOOMED", "MARGINAL", "WINNABLE")}
    if classes["WINNABLE"] * 2 >= n:
        verdict = "COMBAT_VARIANCE_DOMINANT"
    elif classes["DOOMED"] * 2 >= n:
        verdict = "PREPARATION_DOMINANT"
    else:
        verdict = "MIXED"

    def group(key):
        g = defaultdict(list)
        for e in entries:
            g[e[key]].append(e)
        return {str(k): {"entries": len(v), "freshWins": sum(e["freshWins"] for e in v),
                         "freshRuns": len(v) * reps,
                         "classes": {c: sum(e["class"] == c for e in v) for c in classes}}
                for k, v in sorted(g.items())}

    report = {
        "schema": "boss_deaths_default_347_report_v1", "verdict": verdict,
        "validEntries": n, "invalidEntries": invalid, "selected": len(sel["selected"]),
        "census": sel.get("census"), "plannerReps": reps,
        "meanFreshWinRate": sum(rates) / n,
        "meanFreshWinRateBootstrap95": bootstrap_mean(rates),
        "bootstrap": {"replicates": BOOT_REPS, "seed": BOOT_SEED, "unit": "entry"},
        "classes": classes, "winDistribution": {str(w): sum(e["freshWins"] == w for e in entries)
                                                 for w in range(reps + 1)},
        "byAct": group("act"), "byBoss": group("boss"), "entries": entries,
    }
    text = json.dumps(report, indent=1) + "\n"
    if a.out:
        open(a.out, "w").write(text)
    print(json.dumps({k: report[k] for k in ("verdict", "validEntries", "meanFreshWinRate",
                                             "meanFreshWinRateBootstrap95", "classes",
                                             "winDistribution")}, indent=1))
    for e in entries:
        print(f"{e['stateId']:22s} {e['boss']:14s} hp {e['hp']:3d}/{e['maxHp']:3d} "
              f"deck {e['deck']:2d}({e['upgraded']:2d}) relics {e['relics']:2d} "
              f"pot {len(e['potions'])} wins {e['freshWins']}/{reps} {e['class']}")
    for i in invalid:
        print("INVALID", i)


if __name__ == "__main__":
    main()
