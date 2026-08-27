#!/usr/bin/env python3
"""Aggregate the OOC survival x continuation-value diagnostic.

The fixed and marginal encounter-resampling regimes are analyzed separately;
sibling actions share continuation seeds within either regime.  The script
fails loudly on incomplete action/replicate groups or on the factorization
identity.
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


DECISION = ("seed", "decIdx", "act", "floor", "screen")
SCREEN_NAMES = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select",
                5: "map", 6: "treasure", 7: "rest", 8: "shop", 9: "battle"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--raw-extra", action="append", default=[],
                    help="additional disjoint producer CSV (repeatable)")
    ap.add_argument("--replicates", type=int, required=True)
    ap.add_argument("--regime", choices=("fixed", "marg"), default="fixed")
    ap.add_argument("--max-discordant", type=int, default=32)
    ap.add_argument("--min-survival-delta", type=float,
                    help="minimum |p_survive difference| for adjudication; "
                         "default is one replicate (use 0 only for an explicit continuation-only audit)")
    ap.add_argument("--adjudication", help="optional oocfactoreval CSV")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    grouped = defaultdict(list)
    raw_paths = [args.raw_csv] + args.raw_extra
    for raw_path in raw_paths:
        with open(raw_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = set(DECISION) | {"regime", "actionIdx", "actionBits", "utility",
                                        "survivedH", "continuationValue", "qSample",
                                        "continuationSeed", "labelBootstrap"}
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise SystemExit(f"missing columns in {raw_path}: {sorted(missing)}")
            for row in reader:
                if row["regime"] != args.regime:
                    continue
                key = tuple(int(row[x]) for x in DECISION) + (int(row["actionIdx"]),)
                grouped[key].append(row)

    decisions = defaultdict(list)
    max_error = 0.0
    for key, rows in grouped.items():
        if len(rows) != args.replicates:
            raise SystemExit(f"incomplete replicate group {key}: {len(rows)} != {args.replicates}")
        if len({int(r["continuationSeed"]) for r in rows}) != args.replicates:
            raise SystemExit(f"duplicate continuation seed in {key}")
        alive = [int(r["survivedH"]) for r in rows]
        values = [float(r["continuationValue"]) for r in rows]
        if any(int(float(r["labelBootstrap"])) < 0 for r in rows):
            raise SystemExit(f"invalid producer branch in {key}")
        for r, i, v in zip(rows, alive, values):
            if not math.isclose(float(r["qSample"]), i * v,
                                rel_tol=1e-12, abs_tol=1e-12):
                raise SystemExit(f"qSample mismatch in {key}")
        p_survive = sum(alive) / len(rows)
        v_alive = (sum(v for i, v in zip(alive, values) if i) / sum(alive)
                   if sum(alive) else 0.0)
        q_factor = p_survive * v_alive
        q_direct = sum(i * v for i, v in zip(alive, values)) / len(rows)
        max_error = max(max_error, abs(q_factor - q_direct))
        if not math.isclose(q_factor, q_direct, rel_tol=1e-12, abs_tol=1e-12):
            raise SystemExit(f"factorization identity failed for {key}: {q_factor} vs {q_direct}")
        decisions[key[:-1]].append({
            "actionIdx": key[-1], "actionBits": int(rows[0]["actionBits"]),
            "currentScore": sum(float(r["utility"]) for r in rows) / len(rows),
            "pSurvive": p_survive, "vAlive": v_alive, "qFactor": q_factor,
        })

    discordant = []
    action_count = 0
    coverage = []
    for dkey, actions in sorted(decisions.items()):
        action_count += len(actions)
        min_p = min(a["pSurvive"] for a in actions)
        max_p = max(a["pSurvive"] for a in actions)
        # A genuine safety-vs-strength tradeoff requires an action pair whose
        # survival and conditional-survivor-value orderings oppose each other.
        tradeoff = any(
            (a["pSurvive"] - b["pSurvive"]) * (a["vAlive"] - b["vAlive"]) < -1e-12
            for i, a in enumerate(actions) for b in actions[i + 1:]
        )
        coverage.append({**dict(zip(DECISION, dkey)),
                         "screenName": SCREEN_NAMES.get(dkey[-1], "unknown"),
                         "actions": len(actions),
                         "actionsPSurviveUnderOne": sum(a["pSurvive"] < 1.0 - 1e-12
                                                        for a in actions),
                         "minPSurvive": min_p, "maxPSurvive": max_p,
                         "survivalDifference": max_p - min_p,
                         "safetyStrengthTradeoff": int(tradeoff)})
        current = max(actions, key=lambda a: (a["currentScore"], -a["actionIdx"]))
        factor = max(actions, key=lambda a: (a["qFactor"], -a["actionIdx"]))
        if current["actionIdx"] != factor["actionIdx"]:
            row = dict(zip(DECISION, dkey))
            row.update({"currentIdx": current["actionIdx"], "currentBits": current["actionBits"],
                        "currentScore": current["currentScore"],
                        "currentPSurvive": current["pSurvive"], "currentVAlive": current["vAlive"],
                        "currentQFactor": current["qFactor"],
                        "factorIdx": factor["actionIdx"], "factorBits": factor["actionBits"],
                        "factorScore": factor["currentScore"],
                        "factorPSurvive": factor["pSurvive"], "factorVAlive": factor["vAlive"],
                        "factorQFactor": factor["qFactor"]})
            discordant.append(row)

    # Gate expensive adjudication on actually observing the mechanism under
    # test.  With R replicates the smallest measurable nonzero delta is 1/R.
    min_survival_delta = (args.min_survival_delta if args.min_survival_delta is not None
                          else 1.0 / args.replicates)
    if min_survival_delta < 0 or min_survival_delta > 1:
        raise SystemExit("--min-survival-delta must be in [0,1]")
    survival_discordant = [
        r for r in discordant
        if abs(r["factorPSurvive"] - r["currentPSurvive"]) > 1e-12
    ]
    eligible = [
        r for r in discordant
        if (min_survival_delta == 0
            or abs(r["factorPSurvive"] - r["currentPSurvive"])
               >= min_survival_delta - 1e-12)
    ]

    # Prefer the clearest safety-vs-strength disagreements, deterministically.
    discordant.sort(key=lambda r: (-abs(r["factorPSurvive"] - r["currentPSurvive"]),
                                   r["seed"], r["decIdx"]))
    eligible.sort(key=lambda r: (-abs(r["factorPSurvive"] - r["currentPSurvive"]),
                                 r["seed"], r["decIdx"]))
    selected = eligible[:args.max_discordant]

    adjud_summary = None
    if args.adjudication:
        adj = defaultdict(lambda: defaultdict(dict))
        with open(args.adjudication, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if int(row["valid"]) != 1:
                    raise SystemExit(f"invalid adjudication row: {row}")
                key = tuple(int(row[x]) for x in ("seed", "decIdx"))
                role = row["role"]
                if role not in ("C", "F"):
                    raise SystemExit(f"unknown adjudication role: {role}")
                future_key = (int(row["future"]), int(row["continuationSeed"]))
                if future_key in adj[key][role]:
                    raise SystemExit(f"duplicate adjudication replicate: {key} {role} {future_key}")
                adj[key][role][future_key] = row
        utility_metrics = {
            "terminalWin": {"currentWins": 0, "factorWins": 0, "ties": 0,
                            "currentRegrets": [], "factorRegrets": []},
            "denseTerminal": {"currentWins": 0, "factorWins": 0, "ties": 0,
                              "currentRegrets": [], "factorRegrets": []},
        }
        for row in selected:
            roles = adj.get((row["seed"], row["decIdx"]))
            if (not roles or set(roles["C"]) != set(roles["F"])
                    or len(roles["C"]) != args.replicates):
                raise SystemExit(f"missing/unpaired adjudication for seed={row['seed']} decIdx={row['decIdx']}")
            expected_meta = (row["act"], row["floor"], row["screen"])
            for role, expected_bits in (("C", row["currentBits"]), ("F", row["factorBits"])):
                for ar in roles[role].values():
                    if ((int(ar["act"]), int(ar["floor"]), int(ar["screen"])) != expected_meta
                            or int(ar["actionBits"]) != expected_bits):
                        raise SystemExit(f"adjudication identity mismatch: {ar}")
            values = {
                "terminalWin": (
                    sum(int(r["won"]) for r in roles["C"].values()) / len(roles["C"]),
                    sum(int(r["won"]) for r in roles["F"].values()) / len(roles["F"])),
                "denseTerminal": (
                    sum(float(r["adjudicatedValue"]) for r in roles["C"].values()) / len(roles["C"]),
                    sum(float(r["adjudicatedValue"]) for r in roles["F"].values()) / len(roles["F"])),
            }
            for name, (cval, fval) in values.items():
                metrics = utility_metrics[name]
                best = max(cval, fval)
                metrics["currentRegrets"].append(best - cval)
                metrics["factorRegrets"].append(best - fval)
                if cval > fval: metrics["currentWins"] += 1; winner = "current"
                elif fval > cval: metrics["factorWins"] += 1; winner = "factor"
                else: metrics["ties"] += 1; winner = "tie"
                prefix = "win" if name == "terminalWin" else "dense"
                row.update({f"{prefix}CurrentAdjudicated": cval,
                            f"{prefix}FactorAdjudicated": fval,
                            f"{prefix}AdjudicatedWinner": winner,
                            f"{prefix}CurrentRegret": best - cval,
                            f"{prefix}FactorRegret": best - fval})
        def median(xs):
            ys = sorted(xs); n = len(ys)
            return (ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2)
        adjud_summary = {"decisions": len(selected),
                         "replicatesPerAction": args.replicates}
        for name, metrics in utility_metrics.items():
            cw, fw = metrics["currentWins"], metrics["factorWins"]
            cr, fr = metrics["currentRegrets"], metrics["factorRegrets"]
            adjud_summary[name] = {
                "currentWins": cw, "factorWins": fw, "ties": metrics["ties"],
                "factorWinFractionExcludingTies": fw / (cw + fw) if cw + fw else 0.0,
                "currentMeanRegret": sum(cr) / len(cr) if cr else 0.0,
                "factorMeanRegret": sum(fr) / len(fr) if fr else 0.0,
                "currentMedianRegret": median(cr) if cr else 0.0,
                "factorMedianRegret": median(fr) if fr else 0.0,
            }
    all_fields = list(discordant[0]) if discordant else list(DECISION) + ["currentBits", "factorBits"]
    with open(out_dir / "all_discordant.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, all_fields); w.writeheader(); w.writerows(discordant)
    fields = list(selected[0]) if selected else all_fields
    with open(out_dir / "discordant.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields); w.writeheader(); w.writerows(selected)
    manifest_fields = list(DECISION) + ["currentBits", "factorBits"]
    with open(out_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, manifest_fields); w.writeheader()
        w.writerows({k: r[k] for k in manifest_fields} for r in selected)
    coverage_fields = list(coverage[0]) if coverage else list(DECISION)
    with open(out_dir / "survival_coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, coverage_fields); w.writeheader(); w.writerows(coverage)
    positive_differences = [r["survivalDifference"] for r in coverage
                            if r["survivalDifference"] > 1e-12]
    screen_breakdown = {}
    for screen in sorted({r["screen"] for r in coverage}):
        rows = [r for r in coverage if r["screen"] == screen]
        screen_breakdown[f"{screen}:{SCREEN_NAMES.get(screen, 'unknown')}"] = {
            "decisions": len(rows),
            "actions": sum(r["actions"] for r in rows),
            "actionsPSurviveUnderOne": sum(r["actionsPSurviveUnderOne"] for r in rows),
            "decisionsWithSurvivalSpread": sum(r["survivalDifference"] > 1e-12 for r in rows),
            "safetyStrengthTradeoffs": sum(r["safetyStrengthTradeoff"] for r in rows),
            "maxSurvivalDifference": max((r["survivalDifference"] for r in rows), default=0.0),
        }
    summary = {"rawCsv": [str(Path(p)) for p in raw_paths], "regime": args.regime,
               "replicates": args.replicates,
               "decisions": len(decisions), "actions": action_count,
               "actionsPSurviveUnderOne": sum(r["actionsPSurviveUnderOne"] for r in coverage),
               "decisionsWithAnyPSurviveUnderOne": sum(r["actionsPSurviveUnderOne"] > 0
                                                       for r in coverage),
               "decisionsWithSurvivalSpread": len(positive_differences),
               "minPositiveSurvivalDifference": min(positive_differences)
                                                if positive_differences else 0.0,
               "maxSurvivalDifference": max(positive_differences)
                                        if positive_differences else 0.0,
               "safetyStrengthTradeoffs": sum(r["safetyStrengthTradeoff"] for r in coverage),
               "screenBreakdown": screen_breakdown,
               "discordantTotal": len(discordant),
               "survivalDiscordantTotal": len(survival_discordant),
               "minSurvivalDelta": min_survival_delta,
               "adjudicationEligible": len(eligible),
               "discordantSelected": len(selected),
               "adjudicationAuthorized": bool(selected),
               "maxFactorizationAbsError": max_error}
    if adjud_summary is not None:
        summary["adjudication"] = adjud_summary
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if discordant and not selected:
        raise SystemExit(
            "no ranking discordance meets the survival-delta gate; "
            "do not launch adjudication (use --min-survival-delta 0 only for "
            "an explicitly scoped continuation-only audit)"
        )


if __name__ == "__main__":
    main()
