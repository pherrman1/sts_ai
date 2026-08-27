#!/usr/bin/env python3
"""Aggregate the OOC survival x continuation-value diagnostic.

Only ``regime=fixed`` rows are used: sibling actions share each continuation
seed, matching the existing Tier-B counterfactual contract.  The script fails
loudly on incomplete action/replicate groups or on the factorization identity.
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


DECISION = ("seed", "decIdx", "act", "floor", "screen")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--raw-extra", action="append", default=[],
                    help="additional disjoint producer CSV (repeatable)")
    ap.add_argument("--replicates", type=int, required=True)
    ap.add_argument("--max-discordant", type=int, default=32)
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
                if row["regime"] != "fixed":
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
    for dkey, actions in sorted(decisions.items()):
        action_count += len(actions)
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

    # Prefer the clearest safety-vs-strength disagreements, deterministically.
    discordant.sort(key=lambda r: (-abs(r["factorPSurvive"] - r["currentPSurvive"]),
                                   r["seed"], r["decIdx"]))
    selected = discordant[:args.max_discordant]

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
        current_wins = factor_wins = ties = 0
        current_regrets, factor_regrets = [], []
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
            cval = sum(float(r["adjudicatedValue"]) for r in roles["C"].values()) / len(roles["C"])
            fval = sum(float(r["adjudicatedValue"]) for r in roles["F"].values()) / len(roles["F"])
            best = max(cval, fval)
            current_regrets.append(best - cval)
            factor_regrets.append(best - fval)
            if cval > fval: current_wins += 1; winner = "current"
            elif fval > cval: factor_wins += 1; winner = "factor"
            else: ties += 1; winner = "tie"
            row.update({"currentAdjudicated": cval, "factorAdjudicated": fval,
                        "adjudicatedWinner": winner,
                        "currentRegret": best - cval, "factorRegret": best - fval})
        def median(xs):
            ys = sorted(xs); n = len(ys)
            return (ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2)
        adjud_summary = {
            "decisions": len(selected), "replicatesPerAction": args.replicates,
            "currentWins": current_wins, "factorWins": factor_wins, "ties": ties,
            "factorWinFractionExcludingTies": (factor_wins / (current_wins + factor_wins)
                                                if current_wins + factor_wins else 0.0),
            "currentMeanRegret": sum(current_regrets) / len(current_regrets) if current_regrets else 0.0,
            "factorMeanRegret": sum(factor_regrets) / len(factor_regrets) if factor_regrets else 0.0,
            "currentMedianRegret": median(current_regrets) if current_regrets else 0.0,
            "factorMedianRegret": median(factor_regrets) if factor_regrets else 0.0,
        }
    fields = list(selected[0]) if selected else list(DECISION) + ["currentBits", "factorBits"]
    with open(out_dir / "discordant.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fields); w.writeheader(); w.writerows(selected)
    manifest_fields = list(DECISION) + ["currentBits", "factorBits"]
    with open(out_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, manifest_fields); w.writeheader()
        w.writerows({k: r[k] for k in manifest_fields} for r in selected)
    summary = {"rawCsv": [str(Path(p)) for p in raw_paths], "replicates": args.replicates,
               "decisions": len(decisions), "actions": action_count,
               "discordantTotal": len(discordant), "discordantSelected": len(selected),
               "maxFactorizationAbsError": max_error}
    if adjud_summary is not None:
        summary["adjudication"] = adjud_summary
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
