#!/usr/bin/env python3
"""Compare a refit Phase-1 survival model with the production CTM stack on TEST rows.

Inputs:
- `test_predictions.npz` from `combat_transition_model_experiment.py fit --save-test-predictions`;
- the production stack's scores for the same rows, from
  `one_combat ctmscorerows TEST_ROWS.jsonl SCORES.csv`. Write TEST_ROWS.jsonl with `extract-test`.

Metrics are on rows the production stack supports: survival log loss and Brier, and
the winning-HP fraction MAE and bias on wins. Each metric is reported overall, for
boss fights, and per act. Differences are refit minus production, with a paired
source-seed bootstrap; negative favours the refit.

usage:
  ctm_survival_compare.py extract-test --corpus CORPUS.jsonl --predictions NPZ --out TEST_ROWS.jsonl
  ctm_survival_compare.py compare --predictions NPZ --production-scores SCORES.csv --out RESULT.json
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

EPS = 1e-6


def extract_test(corpus: Path, predictions: Path, out: Path) -> int:
    data = np.load(predictions)
    wanted = data["rowIndex"].astype(np.int64)
    if np.any(np.diff(wanted) <= 0):
        raise ValueError("rowIndex must be strictly increasing")
    keys = list(zip(data["sourceSeed"].tolist(), data["fightIdx"].tolist()))
    k = 0
    with corpus.open(encoding="utf-8") as src, out.open("w", encoding="utf-8") as sink:
        for i, line in enumerate(src):
            if k < len(wanted) and i == wanted[k]:
                row = json.loads(line)
                if (row["sourceSeed"], row["fightIdx"]) != keys[k]:
                    raise ValueError(f"corpus row {i} does not match prediction key {keys[k]}")
                sink.write(line); k += 1
    if k != len(wanted):
        raise ValueError(f"corpus ended after {k} of {len(wanted)} TEST rows")
    return k


def _metrics(y, p, yh, hp):
    p = np.clip(p, EPS, 1 - EPS)
    win = y == 1
    return {
        "n": int(len(y)), "wins": int(win.sum()),
        "logloss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "brier": float(np.mean((p - y) ** 2)),
        "meanPredWin": float(p.mean()), "observedWin": float(y.mean()),
        "winHpMae": float(np.mean(np.abs(hp[win] - yh[win]))) if win.any() else None,
        "winHpBias": float(np.mean(hp[win] - yh[win])) if win.any() else None,
    }


def compare(predictions: Path, scores: Path, out: Path, model: str, reps: int, seed: int) -> dict:
    data = np.load(predictions)
    keys = list(zip(data["sourceSeed"].tolist(), data["fightIdx"].tolist()))
    prod = {}
    with scores.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prod[(int(r["source_seed"]), int(r["fight_idx"]))] = r
    if set(prod) != set(keys):
        raise ValueError("production scores do not cover exactly the TEST rows")
    rows = [prod[k] for k in keys]
    supported = np.asarray([r["scored"] == "1" for r in rows])
    boss = np.asarray([r["room_class"] == "BOSS" for r in rows])
    act = np.asarray([int(r["act"]) for r in rows])
    p_prod = np.asarray([1 - float(r["p_death"]) if r["scored"] == "1" else np.nan for r in rows])
    hp_prod = np.asarray([float(r["win_hp_fraction"]) if r["scored"] == "1" else np.nan for r in rows])
    y = data["y_win"].astype(np.float64); yh = np.nan_to_num(data["y_hp"].astype(np.float64), nan=0.0)
    p_new = data[f"{model}_p"].astype(np.float64); hp_new = data[f"{model}_hp"].astype(np.float64)
    seeds = data["sourceSeed"]

    def table(mask):
        a = _metrics(y[mask], p_new[mask], yh[mask], hp_new[mask])
        b = _metrics(y[mask], p_prod[mask], yh[mask], hp_prod[mask])
        return {"refit": a, "production": b}

    slices = {"all": supported, "boss": supported & boss}
    for a in sorted(set(act.tolist())):
        slices[f"act{a}"] = supported & (act == a)
    result = {"schema": "ctm_survival_compare_v1", "model": model,
              "rows": int(len(keys)), "productionSupported": int(supported.sum()),
              "unsupportedRefitOnly": _metrics(y[~supported], p_new[~supported], yh[~supported], hp_new[~supported])
              if (~supported).any() else None,
              "slices": {name: table(mask) for name, mask in slices.items() if mask.any()}}
    # Paired source-seed bootstrap of refit minus production on supported rows.
    rng = np.random.default_rng(seed)
    boot = {}
    for name, mask in slices.items():
        idx = np.flatnonzero(mask)
        if not len(idx):
            continue
        groups = {}
        for i in idx:
            groups.setdefault(int(seeds[i]), []).append(i)
        members = [np.asarray(v) for v in groups.values()]
        draws = {"logloss": [], "brier": [], "winHpMae": []}
        for _ in range(reps):
            pick = np.concatenate([members[j] for j in rng.integers(0, len(members), len(members))])
            a = _metrics(y[pick], p_new[pick], yh[pick], hp_new[pick])
            b = _metrics(y[pick], p_prod[pick], yh[pick], hp_prod[pick])
            for m in draws:
                if a[m] is not None and b[m] is not None:
                    draws[m].append(a[m] - b[m])
        boot[name] = {m: {"mean": float(np.mean(v)), "ci95": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]}
                      for m, v in draws.items() if v}
    result["refitMinusProductionBootstrap"] = {"reps": reps, "seed": seed, "slices": boot}
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("rows", "productionSupported")} |
                     {"all": boot.get("all"), "boss": boot.get("boss")}, indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("extract-test")
    p.add_argument("--corpus", required=True, type=Path)
    p.add_argument("--predictions", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("compare")
    p.add_argument("--predictions", required=True, type=Path)
    p.add_argument("--production-scores", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--model", default="deepsets", choices=("deepsets", "attention", "xgboost"))
    p.add_argument("--bootstrap-reps", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20261007)
    args = parser.parse_args()
    if args.command == "extract-test":
        print(json.dumps({"testRows": extract_test(args.corpus, args.predictions, args.out)}))
    else:
        compare(args.predictions, args.production_scores, args.out, args.model, args.bootstrap_reps, args.seed)


if __name__ == "__main__":
    main()
