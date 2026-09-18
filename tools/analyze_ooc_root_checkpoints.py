#!/usr/bin/env python3
"""Offline prefix agreement; hypothetical savings are not gameplay qualification."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

CHECKPOINTS = (128, 256, 512, 1024, 2048)
MARGINS = (0.05, 0.10, 0.20)


def leader(checkpoint):
    return sorted(checkpoint["actions"], key=lambda action: (-action["visits"], -action["q"], action["id"]))[0]["id"]


def gap(checkpoint):
    visits = sorted((action["visits"] for action in checkpoint["actions"]), reverse=True)
    return (visits[0] - (visits[1] if len(visits) > 1 else 0)) / checkpoint["simulations"]


def stable(checkpoints, budget):
    earlier = [value for value in CHECKPOINTS if value <= budget]
    return len(earlier) >= 2 and all(value in checkpoints for value in earlier) and len({leader(checkpoints[value]) for value in earlier}) == 1


def summarize(rows):
    identities = [(row["seed"], row["decisionIndex"]) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate roots")
    for row in rows:
        if row["requestedSimulations"] != 2048:
            raise ValueError("requires 2048 budget")
        checkpoints = row["checkpoints"]
        expected = [budget for budget in CHECKPOINTS if budget <= row["shadowSimulations"]]
        if [checkpoint["simulations"] for checkpoint in checkpoints] != expected:
            raise ValueError("missing or out-of-order checkpoints")
        for checkpoint in checkpoints:
            actions = checkpoint["actions"]
            if not actions or len({action["id"] for action in actions}) != len(actions):
                raise ValueError("invalid actions")
            if sum(action["visits"] for action in actions) != checkpoint["simulations"]:
                raise ValueError("visit accounting")
        if not row["shadowAborted"] and (row["shadowSimulations"] != 2048 or leader(checkpoints[-1]) != row["finalAction"]):
            raise ValueError("invalid final selection")
    eligible = [row for row in rows if not row["shadowAborted"]]
    multi = [row for row in eligible if len(row["checkpoints"][0]["actions"]) > 1]

    def agreement(group, budget):
        count = sum(leader(next(checkpoint for checkpoint in row["checkpoints"] if checkpoint["simulations"] == budget)) == row["finalAction"] for row in group)
        return {"roots": len(group), "agree": count, "agreement": count / len(group) if group else None}

    output = {"roots": len(rows), "seeds": sorted({row["seed"] for row in rows}),
              "aborts": dict(Counter(row["shadowAbortReason"] for row in rows if row["shadowAborted"])),
              "liveShadowActionDifferences": sum(not row["shadowAborted"] and row["liveAction"] != row["finalAction"] for row in rows),
              "lateShadowAbortsAfterLiveAction": sum(row["shadowAborted"] and row["liveAction"] is not None for row in rows),
              "cohorts": {}}
    for label, cohort in (("allCompleted", eligible), ("multiActionCompleted", multi)):
        by_budget = {}
        for budget in CHECKPOINTS:
            bins = {}
            for lower, upper in ((0, .05), (.05, .10), (.10, .20), (.20, 1.01)):
                subset = [row for row in cohort if lower <= gap(next(checkpoint for checkpoint in row["checkpoints"] if checkpoint["simulations"] == budget)) < upper]
                bins[f"{lower:.2f}..{upper:.2f}"] = agreement(subset, budget)
            stable_rows = [row for row in cohort if stable({checkpoint["simulations"]: checkpoint for checkpoint in row["checkpoints"]}, budget)]
            by_budget[str(budget)] = agreement(cohort, budget) | {"gapBins": bins, "stable": agreement(stable_rows, budget),
                "unstable": agreement([row for row in cohort if row not in stable_rows], budget)}
        rules = {}
        choices = [("fixed512", (512,), 0, False)]
        for margin in MARGINS:
            choices.extend([(f"512_if_gap>={margin}", (512,), margin, False),
                            (f"256_512_if_gap>={margin}", (256, 512), margin, False),
                            (f"stable_256_512_if_gap>={margin}", (256, 512), margin, True)])
        for name, budgets, margin, require_stable in choices:
            saved = incremental = disagreements = stops = late_aborts = 0
            stop_histogram = Counter()
            for row in cohort:
                checkpoints = {checkpoint["simulations"]: checkpoint for checkpoint in row["checkpoints"]}
                stop = next((budget for budget in budgets if gap(checkpoints[budget]) >= margin
                             and (not require_stable or stable(checkpoints, budget))), 2048)
                saved += 2048 - stop
                incremental += max(0, row["liveSimulations"] - stop)
                stops += stop < 2048
                stop_histogram[stop] += 1
                disagreements += leader(checkpoints[stop]) != row["finalAction"]
            for row in rows:
                if not row["shadowAborted"]:
                    continue
                checkpoints = {checkpoint["simulations"]: checkpoint for checkpoint in row["checkpoints"]}
                late_aborts += any(budget in checkpoints and gap(checkpoints[budget]) >= margin
                                  and (not require_stable or stable(checkpoints, budget)) for budget in budgets)
            rules[name] = {"roots": len(cohort), "earlyStops": stops, "stopBudgets": dict(stop_histogram),
                           "disagreements": disagreements, "agreement": 1 - disagreements / len(cohort) if cohort else None,
                           "savedVsFull2048": saved, "fractionVsFull2048": saved / (2048 * len(cohort)) if cohort else None,
                           "additionalSavedVsLiveEarlyStop": incremental,
                           "additionalFractionVsLive": incremental / sum(row["liveSimulations"] for row in cohort) if cohort else None,
                           "allAbortedRootsWouldStopBeforeAbort": late_aborts}
        output["cohorts"][label] = {"roots": len(cohort), "checkpoints": by_budget, "rules": rules}
    output["perSeedMultiAction"] = {str(seed): {str(budget): agreement([row for row in multi if row["seed"] == seed], budget)
                                               for budget in CHECKPOINTS} for seed in output["seeds"]}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in args.paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    args.output.write_text(json.dumps(summarize(rows), indent=2) + "\n")


if __name__ == "__main__":
    main()
