#!/usr/bin/env python3
"""E2c: exact RAW / POST combat-terminal run-win critic analysis.

Input is the matched long-format dataset produced by ``one_combat e2cgen``:
each survived ordinary/elite/act-1-2-boss combat contributes exactly one RAW row
(immediately after persistent combat transfer, before regainControl()/rewards)
and one POST row (after all non-card rewards, before the first card pick/skip),
sharing ``(seed, fight_index)`` and the same eventual ``won`` label.

Uses the same XGBoost recipe and seed-grouped split methodology as E2/E2b so the
conceptual variable is the state boundary/features, not the learner. Held-out
seeds are identical across every arm; bootstrap resamples by held-out seed with
validation seed IDs reindexed contiguously.
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import train_postcombat_runwin as e2  # XGB recipe, ece/metrics/calibration/bootstrap helpers

B1_FEATURES = ["hpFrac", "curHp", "maxHp", "act", "floor"]
SPLIT = {"method": "GroupShuffleSplit", "test_size": 0.15, "random_state": 0}
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 0

META = {"seed", "fight_index", "boundary", "room_type", "encounter_id"}
LABELS = {"won", "finalFloor", "endHp"}

# Hidden-future / simulator-internal information that a legitimate run critic
# cannot know.
HIDDEN_FUTURE = {"nextEliteId", "nextFight0", "nextFight1", "nextFight2",
                 "remElites", "remFights", "monOffset", "eliteOffset"}

# Every other rich state column is player-observable or trackable. Any column
# that is not recognized below is classified ambiguous (fail-closed) and is
# excluded from the fair T-raw/T-post feature set.
OBSERVABLE_EXACT = {"ascension", "act", "floor", "curHp", "maxHp", "gold",
                    "deckSize", "potionChance", "cardRarityFactor", "blueKey",
                    "greenKey", "redKey", "potionCount", "potionCapacity", "bossId",
                    "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure",
                    "bottledAtkId", "bottledSkillId", "bottledPowId", "curMapX",
                    "curMapY", "room_type", "encounter_id", "hpFrac"}
import re as _re


def _is_observable(name):
    if name in OBSERVABLE_EXACT:
        return True
    if _re.fullmatch(r"(d|u|pot)[0-9]+", name):
        return True
    if name.startswith(("fmD", "fmC", "relic_has_", "relic_data_")):
        return True
    return False


def manifest(header):
    """Classify every column; unknown columns fail closed as ambiguous."""
    out = []
    hidden = set()
    for name in header:
        if name in META:
            fam = "metadata/control"
        elif name in LABELS:
            fam = "label"
        elif name in HIDDEN_FUTURE:
            fam = "hidden_rng_or_true_future"
            hidden.add(name)
        elif _is_observable(name):
            fam = "observable_or_trackable"
        else:
            fam = "ambiguous"
        out.append({"feature": name, "family": fam})
    return out, hidden


def load(csv):
    header = pd.read_csv(csv, nrows=0).columns.tolist()
    df = pd.read_csv(csv)
    df["room_type"] = df["room_type"].map({"MONSTER": 0, "ELITE": 1, "BOSS": 2}).fillna(-1).astype(int)
    df["encounter_id"] = df["encounter_id"].astype(int)
    df["hpFrac"] = df["curHp"] / df["maxHp"].replace(0, np.nan)
    df["hpFrac"] = df["hpFrac"].fillna(0.0)
    return df, header


def t_features(header, use_counter=True):
    """Observable state + room/encounter context; hidden/future/ambiguous excluded."""
    man, hidden = manifest(header)
    fams = {"observable_or_trackable", "metadata/control"}
    feats = []
    for rec in man:
        name = rec["feature"]
        if rec["family"] not in fams or name in hidden:
            continue
        if name in META and name not in ("room_type", "encounter_id"):
            continue  # pairing key/control columns are never features
        if name.startswith("relic_data_") and not use_counter:
            continue
        if _re.fullmatch(r"r[0-9]+", name):
            continue  # legacy ownership+counter encoding is invalid for E2c arms
        feats.append(name)
    return feats


def post_boundary_ready(screen_state, rewards, collect_keys):
    """Mirror e2cCapturePost's reward-drain predicate for self-testability."""
    return (screen_state == "REWARDS" and rewards["gold"] == 0 and
            rewards["relic"] == 0 and rewards["potion"] == 0 and
            (not collect_keys or (not rewards["emerald"] and not rewards["sapphire"])) and
            rewards["cards"] > 0)


def arm_predictions(dfb, feats, val_pairs, dev):
    """Fit one arm on one boundary; return aligned val predictions + best_iter + counter gain."""
    y = dfb["won"].astype(float)
    X = dfb[feats].astype(float)
    tr = ~dfb.index.get_level_values("seed").isin(val_pairs.get_level_values("seed"))
    b, best, p = e2.fit(X[tr].values, y[tr].values, X[~tr].values, y[~tr].values, feats, dev)
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    s = pd.Series(p, index=dfb.index[~tr]).reindex(val_pairs)
    if s.isna().any():
        raise AssertionError("missing validation pair for an arm; pair integrity broken")
    gain = 0.0
    for name in feats:
        if name.startswith("relic_data_"):
            gain += float(b.get_score(importance_type="gain").get(name, 0.0))
    return s.values, best, gain


def classify_verdict(checks, gain_post):
    if gain_post <= 0:
        return "E2C INCONCLUSIVE"
    if not checks["T-raw_logloss_below_B2-raw"] or not checks["bootstrap_logloss_ci_below_zero"]:
        return "E2C NEGATIVE"
    if all(checks.values()):
        return "E2C SUPPORTED"
    if (checks["T-raw_logloss_below_B2-raw"] and
            checks["T-raw_brier_below_B2-raw"] and
            checks["T-raw_auc_above_B2-raw"] and
            (not checks["raw_retention_ge_0.50"] or not checks["T-raw_ece_le_0.10"])):
        return "E2C PARTIAL"
    return "E2C INCONCLUSIVE"


def main():
    csv = sys.argv[1] if len(sys.argv) > 1 else "build/e2c_raw_terminal.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "build/e2c_raw_terminal"
    os.makedirs(out, exist_ok=True)
    dev = e2.device()
    print(f"loading {csv} ...", flush=True)
    df, header = load(csv)
    man, hidden = manifest(header)

    # ── Pairing invariants (producer contract) ────────────────────────────
    key = ["seed", "fight_index", "boundary"]
    if df.duplicated(key).any():
        raise AssertionError("duplicate (seed, fight_index, boundary) rows")
    piv = df.pivot_table(index=["seed", "fight_index"], columns="boundary",
                         values="won", aggfunc="first")
    missing = piv[(~piv["RAW"].notna()) | (~piv["POST"].notna())]
    if not missing.empty:
        raise AssertionError(f"pairs with a missing boundary: {len(missing)}")
    if not (piv["RAW"] == piv["POST"]).all():
        raise AssertionError("RAW/POST labels differ within a pair")
    meta_raw = df[df.boundary == "RAW"].set_index(["seed", "fight_index"])[["room_type", "encounter_id"]]
    meta_post = df[df.boundary == "POST"].set_index(["seed", "fight_index"])[["room_type", "encounter_id"]]
    if not (meta_raw == meta_post).all().all():
        raise AssertionError("RAW/POST pair metadata disagree")

    pairs = piv.index.to_frame(index=False)
    y_all = piv["RAW"].astype(float)
    seeds = np.array(sorted(pairs.seed.unique()))
    tr, va = e2.grouped_split(seeds)
    tr_seeds = set(seeds[tr]); va_seeds = set(seeds[va])

    dfr = df[df.boundary == "RAW"].set_index(["seed", "fight_index"])
    dfp = df[df.boundary == "POST"].set_index(["seed", "fight_index"])
    val_pairs = dfr.index[dfr.index.get_level_values("seed").isin(va_seeds)]
    yv = y_all.reindex(val_pairs).values
    _, run = np.unique(val_pairs.get_level_values("seed"), return_inverse=True)

    B1 = B1_FEATURES
    B2 = B1 + ["room_type", "encounter_id"]
    T = t_features(header, use_counter=True)
    Tn = t_features(header, use_counter=False)

    arms = {
        "B1-raw": (dfr, B1), "B2-raw": (dfr, B2), "T-raw": (dfr, T),
        "B1-post": (dfp, B1), "B2-post": (dfp, B2), "T-post": (dfp, T),
        "T-raw-no-counter": (dfr, Tn),
    }
    results = {}
    for name, (dfb, feats) in arms.items():
        p, best, gain = arm_predictions(dfb, feats, val_pairs, dev)
        results[name] = {"p": p, "best": best, "count_gain": gain,
                         "metrics": e2.metrics(yv, p), "feats": feats}

    train_pairs = dfr.index[dfr.index.get_level_values("seed").isin(tr_seeds)]
    yt = y_all.reindex(train_pairs).values
    b0p = float(yt.mean())
    b0pred = np.full(len(yv), b0p)
    b0 = {"n": int(len(yv)), "seeds": int(len(np.unique(train_pairs.get_level_values("seed")))),
          "training_prevalence": b0p, "metrics": e2.metrics(yv, b0pred)}
    for k, v in results.items():
        print(f"{k}: {v['metrics']} best_iter={v['best']}", flush=True)
    print(f"B0 (val prevalence): {b0}", flush=True)

    # Primary seed-bootstrap comparisons (T - baseline log loss/Brier/AUC)
    comparisons = {}
    comps = [
        ("T-raw", "B1-raw"), ("T-raw", "B2-raw"),
        ("T-post", "B1-post"), ("T-post", "B2-post"),
        ("T-raw", "T-post"), ("T-raw-no-counter", "T-raw"),
    ]
    for a, b in comps:
        boot = e2.bootstrap_deltas(yv, results[a]["p"], results[b]["p"], run,
                                   n=BOOTSTRAP_N, seed=BOOTSTRAP_SEED)
        comparisons[f"{a} - {b}"] = {k: {"mean": float(np.mean(v)), "ci95": e2.ci(v)}
                                     for k, v in boot.items()}

    # Signal retention (information-matched, same fights)
    def _ll(name):
        return results[name]["metrics"]["logloss"]

    gain_raw = _ll("B2-raw") - _ll("T-raw")
    gain_post = _ll("B2-post") - _ll("T-post")
    raw_retention = (gain_raw / gain_post) if gain_post > 0 else None
    reward_gap = _ll("T-raw") - _ll("T-post")

    # Preregistered decision rule
    Tr, B2r = results["T-raw"], results["B2-raw"]
    boot_raw = comparisons["T-raw - B2-raw"]["logloss"]
    checks = {
        "T-raw_logloss_below_B2-raw": _ll("T-raw") < _ll("B2-raw"),
        "T-raw_brier_below_B2-raw": Tr["metrics"]["brier"] < B2r["metrics"]["brier"],
        "T-raw_auc_above_B2-raw": Tr["metrics"]["auc"] > B2r["metrics"]["auc"],
        "bootstrap_logloss_ci_below_zero": boot_raw["ci95"][1] < 0,
        "T-raw_ece_le_0.10": Tr["metrics"]["ece"] <= 0.10,
        "raw_retention_ge_0.50": raw_retention is not None and raw_retention >= 0.50,
    }
    primary = all(checks[k] for k in ("T-raw_logloss_below_B2-raw",
                                      "T-raw_brier_below_B2-raw", "T-raw_auc_above_B2-raw"))
    significant_raw = checks["bootstrap_logloss_ci_below_zero"]
    verdict = classify_verdict(checks, gain_post)

    # Counter diagnostic
    boot_ctr = comparisons["T-raw-no-counter - T-raw"]["logloss"]
    counter_sensitive = (Tr["count_gain"] > 0.0 and
                         _ll("T-raw-no-counter") > _ll("T-raw") and
                         boot_ctr["ci95"][0] > 0.0)
    counter_verdict = ("COUNTER-SENSITIVE" if counter_sensitive
                       else ("NOT TESTABLE" if not any(c.startswith("relic_data_") for c in T)
                             else "NO EVIDENCE OF COUNTER SENSITIVITY"))


    result = {
        "experiment": "E2c exact raw/post combat-terminal run-win critic",
        "dataset": os.path.abspath(csv), "dataset_sha256": e2.sha256(csv),
        "schema_version": "e2c-v1", "column_count": len(header),
        "pairs": int(len(val_pairs)), "val_rows": int(len(yv)),
        "val_seeds": int(len(np.unique(val_pairs.get_level_values("seed")))),
        "prev": b0,
        "arms": {k: {"features": v["feats"], "best_iteration": v["best"],
                     "metrics": v["metrics"], "counter_feature_gain": v["count_gain"]}
                 for k, v in results.items()},
        "feature_manifest": man, "hidden_excluded": sorted(hidden),
        "comparisons": comparisons,
        "retention": {"gain_raw": gain_raw, "gain_post": gain_post,
                      "raw_retention": raw_retention, "reward_information_gap": reward_gap},
        "checks": checks, "verdict": verdict,
        "counter": {"verdict": counter_verdict, "gain": Tr["count_gain"],
                    "T-raw_no_counter_vs_T_logloss_delta": boot_ctr["mean"]},
        "split": SPLIT,
        "xgb_params": e2.XGB_PARAMS,
        "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "unit": "held-out seed"},
        "provenance": {"git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                          text=True).strip()},
    }
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(result, f, indent=2)

    with open(os.path.join(out, "calibration_deciles.csv"), "w") as f:
        f.write("arm,bin_lo,bin_hi,n,mean_pred,observed\n")
        for name in results:
            for row in e2.calibration(yv, results[name]["p"]):
                f.write(name + "," + ",".join(str(row[k]) for k in
                        ("bin_lo", "bin_hi", "n", "mean_pred", "observed")) + "\n")

    np.savez_compressed(os.path.join(out, "validation_predictions.npz"),
                        seed=val_pairs.get_level_values("seed").values,
                        fight_index=val_pairs.get_level_values("fight_index").values,
                        y=yv, run=run,
                        **{k.replace("-", "_"): v["p"] for k, v in results.items()})

    print(json.dumps({"verdict": verdict, "checks": checks, "retention": result["retention"],
                      "comparisons": comparisons, "counter": result["counter"]}, indent=2))


if __name__ == "__main__":
    main()
