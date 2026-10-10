#!/usr/bin/env python3
"""#396 Stage 1: forward-map block and `bossId` ablation for rich `v_win`.

Offline only on the frozen #334 corpus: TRAIN/VALIDATION MAP rows, no gameplay
seeds, no C++ build, no TEST rows (the dataset adapter blocks TEST reads).

Question: does the current compact map block (`fmD*` distances, `fmC*`
counts, `curMapX/Y`) carry held-out run-win signal on the public-safe
baseline, separately from the public act-boss identity `bossId`?

Preregistered comparison (frozen before any arm was trained):
- Baseline P: the #397 Stage 1 public-safe set (A3 TRAIN-variable mask minus
  `nextEliteId`, `nextFight0..2`; 457 features), as in §374-§376.
- M: P minus the 12 map fields present in P (`MAP_FIELDS`); `bossId` kept.
- Bz: P minus `bossId`; map fields kept.
- P2: P again with XGBoost seeds 5..9 (null control: retraining noise of a
  5-seed ensemble with an unchanged feature set).
- Inverse diagnostic (secondary): S = TRAIN-variable basic scalars
  (`BASIC_SCALARS`) + `bossId`; O = S + map fields.
- Recipe: frozen A3 X1 parameters (depth 6, eta 0.06, min_child_weight 30,
  subsample 0.8, colsample 0.7, early stopping on VALIDATION), XGBoost seeds
  0..4 per arm; arm prediction = mean probability of its five seeds.
- Gates (STOP on failure): the full A3 set at seed 0 reproduces the frozen X1
  VALIDATION NLL within 1e-9 and its tree count; the P ensemble NLL matches
  the §374 report value 0.44338 within 5e-6 (ledger rounding).
- Primary per ablation X in {M, Bz}: ensemble VALIDATION NLL delta X - P
  with the source-clustered paired 95% CI (2,000 replicates, seed 0), and the
  null delta P2 - P.
  `<X>_MATTERS` if delta >= 0.002, CI lower > 0, delta - |null| >= 0.002,
  and at least 4 of 5 per-seed paired deltas are > 0;
  `<X>_LOW_VALUE` if CI upper < 0.002; otherwise `<X>_INCONCLUSIVE`.
- #396 outcome from M: LOW_VALUE -> CURRENT_MAP_FEATURES_LOW_VALUE;
  MATTERS -> MAP_BLOCK_MATTERS_STAGE2_JUSTIFIED (Stage 2 then decides between
  CURRENT_MAP_SUMMARY_SUFFICIENT and RICHER_MAP_ENCODING_JUSTIFIED);
  otherwise MAP_STAGE1_INCONCLUSIVE.
- Secondary: per-seed deltas, Brier/AUC/ECE, act/pre-boss slices, sibling
  ranking by decision type (MAP has < 30 discordant pairs, §368), O - S,
  field variability on TRAIN, XGBoost gain/weight and TreeSHAP mean |phi|
  (10,000 VALIDATION rows, rng seed 0) of the map fields and `bossId` in the
  P seed-0 model. Importance is descriptive; the ablation decides.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAP_FIELDS = ("fmDElite", "fmDRest", "fmDShop", "fmDBoss",
              "fmCElite", "fmCRest", "fmCShop", "fmCEvent", "fmCMonster", "fmCTreasure",
              "curMapX", "curMapY")
BOSS_FIELD = "bossId"
BASIC_SCALARS = ("ascension", "act", "floor", "curHp", "maxHp", "gold")
SEEDS = (0, 1, 2, 3, 4)
NULL_SEEDS = (5, 6, 7, 8, 9)
MATERIAL_NLL = 0.002
REPRO_TOLERANCE = 1e-9
P_ENSEMBLE_374 = 0.44338
P_ENSEMBLE_TOLERANCE = 5e-6
SHAP_ROWS = 10_000
OUTCOMES = {"LOW_VALUE": "CURRENT_MAP_FEATURES_LOW_VALUE",
            "MATTERS": "MAP_BLOCK_MATTERS_STAGE2_JUSTIFIED",
            "INCONCLUSIVE": "MAP_STAGE1_INCONCLUSIVE"}


class MapAuditError(ValueError):
    pass


def arm_features(base):
    """Feature lists per arm; fails closed if P lacks a field under test."""
    missing = [f for f in MAP_FIELDS + (BOSS_FIELD,) if f not in base]
    if missing:
        raise MapAuditError(f"fields under test not TRAIN-variable in P: {missing}")
    basic = [f for f in BASIC_SCALARS if f in base]
    small = basic + [BOSS_FIELD]
    return {"P": list(base),
            "M": [f for f in base if f not in MAP_FIELDS],
            "Bz": [f for f in base if f != BOSS_FIELD],
            "S": small,
            "O": small + list(MAP_FIELDS)}


def verdict(name, delta, null_delta, per_seed):
    mean, (lo, hi) = delta["mean"], delta["ci95"]
    positive = sum(d > 0 for d in per_seed)
    if (mean >= MATERIAL_NLL and lo > 0 and mean - abs(null_delta) >= MATERIAL_NLL
            and positive >= 4):
        label = "MATTERS"
    elif hi < MATERIAL_NLL:
        label = "LOW_VALUE"
    else:
        label = "INCONCLUSIVE"
    return {"label": f"{name}_{label}", "class": label, "delta_nll": mean, "ci95": [lo, hi],
            "null_delta_nll": null_delta, "per_seed_positive": positive,
            "materiality": MATERIAL_NLL}


def variability(X, names, fields, selected):
    out = {}
    for f in fields:
        col = X[:, names.index(f)]
        values, counts = np.unique(col, return_counts=True)
        out[f] = {"in_a3_selected": f in selected, "distinct": int(len(values)),
                  "non_modal_fraction": float(1 - counts.max() / len(col)),
                  "min": float(col.min()), "max": float(col.max()), "mean": float(col.mean())}
    return out


def importance(predictor, Xv_sample, features, fields):
    booster = predictor.booster
    gain = booster.get_score(importance_type="gain")
    total = booster.get_score(importance_type="total_gain")
    weight = booster.get_score(importance_type="weight")
    import xgboost as xgb
    contrib = booster.predict(xgb.DMatrix(Xv_sample, feature_names=list(features)),
                              pred_contribs=True)
    mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)
    rank = {features[i]: r + 1 for r, i in enumerate(np.argsort(-mean_abs, kind="stable"))}
    total_sum = float(sum(total.values())) or 1.0
    return {f: {"gain": gain.get(f, 0.0), "total_gain": total.get(f, 0.0),
                "total_gain_share": total.get(f, 0.0) / total_sum,
                "splits": int(weight.get(f, 0)),
                "shap_mean_abs": float(mean_abs[features.index(f)]),
                "shap_rank": rank[f], "of": len(features)} for f in fields}


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def run(index, a3_run, output, threads):
    from tools.vwin_refresh_dataset import validated_dataset
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking, clustered_delta
    from tools.vwin_refresh_model import sha256, tool_identity
    from tools.vwin_refresh_training import train_xgb_fixed, versions
    from tools.analyze_vwin_public_info_397 import arms as info_arms
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    a3_run = Path(a3_run)
    frozen = json.loads((a3_run / "validation.json").read_text())["X1"]["training"]["selected"]
    preflight = json.loads((a3_run / "preflight.json").read_text())
    data = validated_dataset(index)
    names = list(data.feature_names)
    selected = preflight["selected_feature_names"]
    base = info_arms(selected)["B"]
    features = arm_features(base)
    xt, yt, _ = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    branches = data.branches("VALIDATION")
    seeds_v = np.array([int(m["sourceSeed"]) for m in mv])
    params = dict(frozen["params"], nthread=threads)

    def fit(feats, seed):
        cols = [names.index(f) for f in feats]
        model, report = train_xgb_fixed(xt[:, cols], yt, xv[:, cols], yv, feats,
                                        params=dict(params, seed=seed))
        return model, report, model.predict(xv[:, cols])

    # Gate 1: the frozen A3 X1 reproduces exactly.
    _, gate, _ = fit(list(selected), 0)
    drift = abs(gate["validation_nll"] - frozen["validation_nll"])
    if drift > REPRO_TOLERANCE or gate["tree_count"] != frozen["tree_count"]:
        write_json(output / "stop.json", {"reason": "A seed 0 does not reproduce frozen X1",
                                          "drift": drift, "trees": gate["tree_count"]})
        raise MapAuditError("STOP: frozen X1 not reproduced")
    print("gate X1", gate["tree_count"], gate["validation_nll"], flush=True)

    plan = [("P", features["P"], SEEDS), ("P2", features["P"], NULL_SEEDS),
            ("M", features["M"], SEEDS), ("Bz", features["Bz"], SEEDS),
            ("S", features["S"], SEEDS), ("O", features["O"], SEEDS)]
    results, predictions, p_seed0 = {}, {}, None
    for arm, feats, seeds in plan:
        per_seed = []
        for seed in seeds:
            model, report, p = fit(feats, seed)
            if arm == "P" and seed == 0:
                p_seed0 = model
            predictions[f"{arm}_seed{seed}"] = p
            per_seed.append({"seed": seed, "tree_count": report["tree_count"],
                             "validation_nll": report["validation_nll"]})
            print(arm, seed, len(feats), report["tree_count"], report["validation_nll"], flush=True)
        ensemble = np.mean([predictions[f"{arm}_seed{s}"] for s in seeds], axis=0)
        predictions[f"{arm}_ensemble"] = ensemble
        results[arm] = {"feature_count": len(feats), "seeds": list(seeds), "per_seed": per_seed,
                        "validation": evaluate_predictions(yv, ensemble, mv),
                        "siblings": sibling_ranking(mv, ensemble, branches)}
        if arm == "P":
            p_nll = results["P"]["validation"]["overall"]["nll"]
            if abs(p_nll - P_ENSEMBLE_374) > P_ENSEMBLE_TOLERANCE:
                write_json(output / "stop.json", {"reason": "P ensemble does not match §374",
                                                  "nll": p_nll, "expected": P_ENSEMBLE_374})
                raise MapAuditError("STOP: P ensemble differs from §374")
    np.savez_compressed(output / "validation_predictions.npz", labels=yv, source_seeds=seeds_v,
                        **predictions)

    def delta(a, b):
        return clustered_delta(yv, predictions[a], predictions[b], seeds_v)
    null = delta("P_ensemble", "P2_ensemble")
    deltas, verdicts = {"P2": {"ensemble": null}}, {}
    for arm in ("M", "Bz"):
        per_seed = {str(s): delta(f"P_seed{s}", f"{arm}_seed{s}")["nll"] for s in SEEDS}
        deltas[arm] = {"ensemble": delta("P_ensemble", f"{arm}_ensemble"), "per_seed": per_seed}
        verdicts[arm] = verdict("MAP" if arm == "M" else "BOSSID", deltas[arm]["ensemble"]["nll"],
                                null["nll"]["mean"], [v["mean"] for v in per_seed.values()])
    deltas["O_minus_S"] = {"ensemble": delta("S_ensemble", "O_ensemble")}
    rng = np.random.default_rng(0)
    sample = np.sort(rng.choice(len(yv), size=min(SHAP_ROWS, len(yv)), replace=False))
    p_cols = [names.index(f) for f in features["P"]]
    report = {
        "schema": "vwin_map_396_stage1_v1", "issue": 396, "tooling": tool_identity(),
        "versions": versions(), "threads": threads,
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "a3_run": str(a3_run.resolve()),
        "a3_hashes": {n: sha256(a3_run / n) for n in ("validation.json", "preflight.json")},
        "gate_x1": {"tree_count": gate["tree_count"], "validation_nll": gate["validation_nll"],
                    "drift": drift},
        "arms": features, "rows": {"train": int(len(yt)), "validation": int(len(yv))},
        "variability_train": variability(xt, names, MAP_FIELDS + (BOSS_FIELD,), selected),
        "importance_P_seed0": importance(p_seed0, xv[sample][:, p_cols], features["P"],
                                         MAP_FIELDS + (BOSS_FIELD,)),
        "results": results, "paired_deltas": deltas, "verdicts": verdicts,
        "issue_396_outcome": OUTCOMES[verdicts["M"]["class"]],
        "test_rows_read": False, "elapsed_seconds": time.time() - started}
    write_json(output / "report.json", report)
    print(json.dumps({"verdicts": verdicts, "issue_396_outcome": report["issue_396_outcome"],
                      "null_delta": null["nll"], "O_minus_S": deltas["O_minus_S"]["ensemble"]["nll"]},
                     indent=2))
    return report


def _self_test():
    base = ["act", "floor", "curHp", "maxHp", "gold", "bossId", "d0", "r5"] + list(MAP_FIELDS)
    a = arm_features(base)
    assert set(base) - set(a["M"]) == set(MAP_FIELDS) and "bossId" in a["M"]
    assert set(base) - set(a["Bz"]) == {"bossId"}
    assert a["S"] == ["act", "floor", "curHp", "maxHp", "gold", "bossId"]  # ascension not variable
    assert a["O"] == a["S"] + list(MAP_FIELDS) and a["P"] == base
    try:
        arm_features([f for f in base if f != "curMapY"])
        raise AssertionError("missing map field must fail closed")
    except MapAuditError:
        pass
    ci = lambda m, lo, hi: {"mean": m, "ci95": [lo, hi]}
    up = [.004, .003, .005, .002, -.001]
    assert verdict("MAP", ci(.004, .001, .007), .001, up)["label"] == "MAP_MATTERS"
    assert verdict("MAP", ci(.004, .001, .007), .003, up)["label"] == "MAP_INCONCLUSIVE"  # null too big
    assert verdict("MAP", ci(.004, .001, .007), .0, [.004, -.001, .005, -.002, .003])["class"] == "INCONCLUSIVE"
    assert verdict("MAP", ci(.004, -.001, .009), .0, up)["class"] == "INCONCLUSIVE"
    assert verdict("MAP", ci(-.001, -.004, .0015), .0, up)["class"] == "LOW_VALUE"
    assert verdict("BOSSID", ci(.0, -.003, .003), .0, up)["label"] == "BOSSID_INCONCLUSIVE"
    assert OUTCOMES[verdict("MAP", ci(-.001, -.004, .0015), 0, up)["class"]] == "CURRENT_MAP_FEATURES_LOW_VALUE"
    X = np.array([[0, 1], [0, 2], [1, 2], [0, 2]], dtype=np.float32)
    v = variability(X, ["a", "b"], ("a", "b"), ["a"])
    assert v["a"]["distinct"] == 2 and v["a"]["non_modal_fraction"] == .25 and v["a"]["in_a3_selected"]
    assert not v["b"]["in_a3_selected"] and v["b"]["max"] == 2
    print("vwin map #396 Stage 1 self-test: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--index", help="frozen #334 corpus index JSON")
    parser.add_argument("--a3-run", help="frozen A3 selected/ run directory")
    parser.add_argument("--output", help="new evidence directory (refuses overwrite)")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not (args.index and args.a3_run and args.output):
        parser.error("--index, --a3-run and --output are required")
    run(args.index, args.a3_run, args.output, args.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
