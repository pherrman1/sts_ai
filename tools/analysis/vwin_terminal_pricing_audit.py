#!/usr/bin/env python3
"""Offline audit of v_win prices at Silver combat-terminal states.

The main population must pass the separate name-aligned Python/native parity
gate before this script is run. All confidence intervals resample complete
source seeds; rows within a seed are never treated as independent runs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from vwin_tree_utils import load_trees, predict_rows, split_counts

BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20260924
HIDDEN_FUTURE = (
    "nextEliteId", "nextFight0", "nextFight1", "nextFight2",
    "remElites", "remFights", "monOffset", "eliteOffset",
)
POTION_RE = __import__("re").compile(r"^pot(\d+)$")
ROOM_NAMES = {"MONSTER": "monster", "ELITE": "elite", "BOSS": "boss"}
SILVER_REFERENCE = {"potion": 11.0, "gold_per_gold": 0.25, "max_hp": 2.0}
COUNTER_RELIC_FEATURES = {
    26: "Happy Flower", 30: "Incense Burner", 31: "Ink Bottle",
    32: "Inserter", 35: "Lizard Tail", 44: "Nunchaku",
    46: "Omamori", 52: "Pen Nib", 68: "Sundial",
    116: "Neow's Lament", 131: "Thread and Needle",
}


def longest_true_run(mask):
    best = current = 0
    for value in mask:
        if bool(value):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def sweep_shape(values, max_hp):
    """Return monotonicity and flat-step length for one 1..maxHp curve."""
    changes = np.diff(np.asarray(values, dtype=np.float64))
    limit = min(len(values), int(math.ceil(0.6 * max_hp)))
    flat_steps = np.abs(changes[:max(0, limit - 1)]) < 1e-6
    return bool(not np.any(changes < -0.005)), longest_true_run(flat_steps)


def rankdata(values):
    return pd.Series(np.asarray(values, dtype=np.float64)).rank(method="average").to_numpy()


def spearman(x, y):
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 3:
        return None, int(mask.sum())
    rx, ry = rankdata(x[mask]), rankdata(y[mask])
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None, int(mask.sum())
    return float(np.corrcoef(rx, ry)[0, 1]), int(mask.sum())


class SeedBootstrap:
    """Percentile bootstrap over seeds with row-weighted sample statistics."""

    def __init__(self, seed=BOOTSTRAP_SEED, reps=BOOTSTRAP_REPS):
        self.rng = np.random.default_rng(seed)
        self.reps = int(reps)

    def mean_interval(self, values, seeds):
        vals = np.asarray(values, dtype=np.float64)
        ids = np.asarray(seeds)
        keep = np.isfinite(vals)
        vals, ids = vals[keep], ids[keep]
        if len(vals) == 0:
            return {"mean": None, "ci95": None, "n": 0, "seeds": 0}
        uniq, inverse = np.unique(ids, return_inverse=True)
        sums = np.bincount(inverse, weights=vals, minlength=len(uniq))
        counts = np.bincount(inverse, minlength=len(uniq)).astype(np.float64)
        draws = self.rng.integers(0, len(uniq), size=(self.reps, len(uniq)))
        numer = sums[draws].sum(axis=1)
        denom = counts[draws].sum(axis=1)
        samples = numer / denom
        return {
            "mean": float(vals.mean()),
            "ci95": [float(v) for v in np.quantile(samples, [0.025, 0.975])],
            "n": int(len(vals)),
            "seeds": int(len(uniq)),
        }

    def seed_mean_interval(self, values_by_seed):
        vals = np.asarray(values_by_seed, dtype=np.float64)
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            return {"mean": None, "ci95": None, "seeds": 0}
        draws = self.rng.integers(0, len(vals), size=(self.reps, len(vals)))
        samples = vals[draws].mean(axis=1)
        return {
            "mean": float(vals.mean()),
            "ci95": [float(v) for v in np.quantile(samples, [0.025, 0.975])],
            "seeds": int(len(vals)),
        }

    def median_interval(self, values, seeds):
        """Row-weighted median interval with complete source-seed resampling."""
        vals = np.asarray(values, dtype=np.float64)
        ids = np.asarray(seeds)
        keep = np.isfinite(vals)
        vals, ids = vals[keep], ids[keep]
        if len(vals) == 0:
            return {"median": None, "ci95": None, "n": 0, "seeds": 0}
        uniq, inverse = np.unique(ids, return_inverse=True)
        draws = self.rng.integers(0, len(uniq), size=(self.reps, len(uniq)))
        order = np.argsort(vals, kind="stable")
        ordered = vals[order]
        samples = np.empty(self.reps, dtype=np.float64)
        for i, draw in enumerate(draws):
            seed_multiplicity = np.bincount(draw, minlength=len(uniq))
            row_weights = seed_multiplicity[inverse][order]
            cumulative = np.cumsum(row_weights)
            total = int(cumulative[-1])
            lo = int(np.searchsorted(cumulative, (total - 1) // 2, side="right"))
            hi = int(np.searchsorted(cumulative, total // 2, side="right"))
            samples[i] = (ordered[lo] + ordered[hi]) / 2.0
        return {
            "median": float(np.median(vals)),
            "ci95": [float(v) for v in np.quantile(samples, [0.025, 0.975])],
            "n": int(len(vals)),
            "seeds": int(len(uniq)),
        }


def _predict_state(X, feat_idx, feat_names, trees, logistic, base_margin):
    return predict_rows(X[:, [feat_idx[name] for name in feat_names]],
                        trees, logistic, base_margin)


def _matrix(frame, features, feat_idx):
    missing = [name for name in features if name not in frame.columns]
    if missing:
        raise ValueError(f"E2c rows are missing model features: {missing[:10]}")
    # The order here is the serialized v_win order and matches richIdxMap by
    # name; E2c's CSV column order is never assumed to be model order.
    return frame.loc[:, features].to_numpy(dtype=np.float32, copy=True)


def _group_values(values, seeds, mask=None):
    values = np.asarray(values, dtype=np.float64)
    seeds = np.asarray(seeds)
    use = np.isfinite(values)
    if mask is not None:
        use &= np.asarray(mask, dtype=bool)
    if not np.any(use):
        return np.array([], dtype=np.float64)
    tmp = pd.DataFrame({"seed": seeds[use], "value": values[use]})
    return tmp.groupby("seed", sort=True).value.mean().to_numpy(dtype=np.float64)


def _metric(values, seeds, boot):
    return boot.mean_interval(values, seeds)


def _split_threshold_counts(trees, features):
    counts = {name: Counter() for name in features}
    for nodes in trees:
        for node in nodes:
            if node[0] == "S":
                counts[features[node[1]]][float(node[2])] += 1
    return counts


def _ci_low(summary):
    return summary["ci95"][0] if summary.get("ci95") else None


def _ci_high(summary):
    return summary["ci95"][1] if summary.get("ci95") else None


def _mean_or_none(values):
    a = np.asarray(values, dtype=np.float64)
    a = a[np.isfinite(a)]
    return float(a.mean()) if len(a) else None


def _table_q1(raw, features, trees, logistic, base_margin, boot):
    feat_idx = {name: i for i, name in enumerate(features)}
    X = _matrix(raw, features, feat_idx)
    n = len(raw)
    base = predict_rows(X, trees, logistic, base_margin)
    hp = raw.curHp.to_numpy(dtype=np.int32)
    max_hp = raw.maxHp.to_numpy(dtype=np.int32)
    if np.any(max_hp <= 0) or np.any(hp < 1) or np.any(hp > max_hp):
        raise ValueError("RAW rows contain invalid current/max HP")

    # Complete integer-HP sweep for each recorded state.
    lengths = max_hp.astype(np.int64)
    repeated = np.repeat(np.arange(n, dtype=np.int64), lengths)
    hp_grid = np.concatenate([np.arange(1, int(m) + 1, dtype=np.float32)
                              for m in max_hp])
    sweep_X = X[repeated].copy()
    sweep_X[:, feat_idx["curHp"]] = hp_grid
    sweep_p = predict_rows(sweep_X, trees, logistic, base_margin)
    monotone = np.zeros(n, dtype=bool)
    flat = np.zeros(n, dtype=np.int32)
    offsets = np.concatenate(([0], np.cumsum(lengths)))
    for i in range(n):
        monotone[i], flat[i] = sweep_shape(sweep_p[offsets[i]:offsets[i + 1]], max_hp[i])

    # The preregistered local slope uses a fixed ten-HP denominator while both
    # evaluation points are clamped to the legal [1,maxHp] interval.
    lo_hp = np.maximum(1, hp - 5).astype(np.float32)
    hi_hp = np.minimum(max_hp, hp + 5).astype(np.float32)
    Xlo, Xhi = X.copy(), X.copy()
    Xlo[:, feat_idx["curHp"]] = lo_hp
    Xhi[:, feat_idx["curHp"]] = hi_hp
    slope = (predict_rows(Xhi, trees, logistic, base_margin)
             - predict_rows(Xlo, trees, logistic, base_margin)) / 10.0

    # Value of each held potion is V(with potion) - V(after removing one).
    potion_items = []
    potion_effect_by_row = [[] for _ in range(n)]
    if "potionCount" in feat_idx:
        potion_cols = []
        for col in raw.columns:
            match = POTION_RE.match(str(col))
            if match:
                potion_cols.append((int(match.group(1)), col))
        for pot_id, col in sorted(potion_cols):
            count = raw[col].to_numpy(dtype=np.int32)
            rows = np.flatnonzero(count > 0)
            if len(rows) == 0:
                continue
            minus = X[rows].copy()
            minus[:, feat_idx["potionCount"]] = np.maximum(
                0.0, minus[:, feat_idx["potionCount"]] - 1.0)
            feature_name = f"pot{pot_id}"
            if feature_name in feat_idx:
                minus[:, feat_idx[feature_name]] = np.maximum(
                    0.0, minus[:, feat_idx[feature_name]] - 1.0)
            without = predict_rows(minus, trees, logistic, base_margin)
            effect = base[rows] - without
            hp_eq = np.divide(effect, slope[rows], out=np.full(len(rows), np.nan),
                              where=slope[rows] > 0)
            item_seeds = raw.seed.to_numpy()[rows]
            potion_items.append({
                "potion_id": pot_id,
                "n": int(len(rows)),
                "mean_value_delta": _metric(effect, item_seeds, boot),
                "share_zero_value_delta": float(np.mean(effect == 0.0)),
                "share_zero_value_delta_ci95": _metric(
                    (effect == 0.0).astype(np.float64), item_seeds, boot)["ci95"],
                "mean_hp_equivalent": _metric(hp_eq, item_seeds, boot),
            })
            for row, delta, equiv in zip(rows, effect, hp_eq):
                potion_effect_by_row[row].append((float(delta), float(equiv)))

    potion_delta = np.full(n, np.nan, dtype=np.float64)
    potion_hp_eq = np.full(n, np.nan, dtype=np.float64)
    for i, values in enumerate(potion_effect_by_row):
        if values:
            potion_delta[i] = float(np.mean([item[0] for item in values]))
            equivs = [item[1] for item in values if np.isfinite(item[1])]
            if equivs:
                potion_hp_eq[i] = float(np.mean(equivs))

    # Central gold change, bounded at zero so negative gold is never created.
    gold = raw.gold.to_numpy(dtype=np.float32)
    gold_lo = np.maximum(0.0, gold - 25.0)
    gold_hi = gold + 25.0
    Xgold_lo, Xgold_hi = X.copy(), X.copy()
    Xgold_lo[:, feat_idx["gold"]] = gold_lo
    Xgold_hi[:, feat_idx["gold"]] = gold_hi
    p_gold_lo = predict_rows(Xgold_lo, trees, logistic, base_margin)
    p_gold_hi = predict_rows(Xgold_hi, trees, logistic, base_margin)
    gold_delta_per_unit = (p_gold_hi - p_gold_lo) / (gold_hi - gold_lo)
    gold_hp_eq = np.divide(gold_delta_per_unit, slope,
                           out=np.full(n, np.nan), where=slope > 0)

    # Feed-like intervention: one more max HP and one more current HP.
    Xmax = X.copy()
    Xmax[:, feat_idx["maxHp"]] += 1.0
    Xmax[:, feat_idx["curHp"]] += 1.0
    max_hp_delta = predict_rows(Xmax, trees, logistic, base_margin) - base
    max_hp_eq = np.divide(max_hp_delta, slope, out=np.full(n, np.nan), where=slope > 0)

    seeds = raw.seed.to_numpy()
    acts = raw.act.to_numpy(dtype=int)
    frac = hp / max_hp
    room = raw.room_type.astype(str).to_numpy()
    hp_band = np.where(frac < 0.3, "<0.3", np.where(frac <= 0.6, "0.3-0.6", ">0.6"))
    row_table = pd.DataFrame({
        "seed": seeds, "act": acts, "room": room, "hp_band": hp_band,
        "hp_frac": frac, "monotone": monotone, "flat_run": flat,
        "s_hp": slope, "potion_delta": potion_delta,
        "potion_hp_eq": potion_hp_eq, "gold_hp_eq": gold_hp_eq,
        "max_hp_hp_eq": max_hp_eq,
    })

    by_act = []
    for act in sorted(np.unique(acts)):
        mask = acts == act
        flat_summary = boot.median_interval(flat[mask], seeds[mask])
        by_act.append({
            "act": int(act), "n": int(mask.sum()),
            "share_monotone": float(np.mean(monotone[mask])),
            "share_monotone_ci95": _metric(
                monotone[mask].astype(np.float64), seeds[mask], boot)["ci95"],
            "median_longest_flat_run_hp": float(np.median(flat[mask])),
            "median_longest_flat_run_hp_ci95": flat_summary["ci95"],
            "share_s_hp_zero": float(np.mean(slope[mask] == 0.0)),
            "share_s_hp_zero_ci95": _metric(
                (slope[mask] == 0.0).astype(np.float64), seeds[mask], boot)["ci95"],
            "mean_s_hp": _metric(slope[mask], seeds[mask], boot),
            "mean_held_potion_delta": _metric(potion_delta[mask], seeds[mask], boot),
            "mean_potion_hp_equivalent": _metric(potion_hp_eq[mask], seeds[mask], boot),
            "mean_gold_hp_equivalent_per_gold": _metric(gold_hp_eq[mask], seeds[mask], boot),
            "mean_max_hp_hp_equivalent": _metric(max_hp_eq[mask], seeds[mask], boot),
        })

    strata = []
    for (act, band, room_name), group in row_table.groupby(
            ["act", "hp_band", "room"], sort=True, dropna=False):
        room_label = ROOM_NAMES.get(room_name, room_name.lower())
        flat_summary = boot.median_interval(group.flat_run, group.seed)
        strata.append({
            "act": int(act), "hp_fraction_band": str(band), "room_type": room_label,
            "n": int(len(group)),
            "share_monotone": float(group.monotone.mean()),
            "share_monotone_ci95": _metric(
                group.monotone.to_numpy(dtype=np.float64), group.seed, boot)["ci95"],
            "median_longest_flat_run_hp": float(group.flat_run.median()),
            "median_longest_flat_run_hp_ci95": flat_summary["ci95"],
            "share_s_hp_zero": float((group.s_hp == 0).mean()),
            "share_s_hp_zero_ci95": _metric(
                (group.s_hp.to_numpy() == 0).astype(np.float64), group.seed, boot)["ci95"],
            "mean_s_hp": _metric(group.s_hp, group.seed, boot),
            "mean_potion_hp_equivalent": _metric(group.potion_hp_eq, group.seed, boot),
            "mean_gold_hp_equivalent_per_gold": _metric(group.gold_hp_eq, group.seed, boot),
            "mean_max_hp_hp_equivalent": _metric(group.max_hp_hp_eq, group.seed, boot),
        })

    potion_summary = [row for row in potion_items if row["n"] >= 30]
    split_names = ["curHp", "maxHp", "gold", "potionCount", "potionCapacity"]
    split_names.extend(sorted(name for name in features if POTION_RE.match(name)))
    split_map = split_counts(trees, features)
    split_rows = [{"feature": name, "split_count": split_map.get(name, 0),
                   "total_gain": None} for name in split_names]
    result = {
        "n_raw_rows": int(n),
        "n_seeds": int(raw.seed.nunique()),
        "overall_share_monotone": float(monotone.mean()),
        "overall_share_monotone_ci95": _metric(
            monotone.astype(np.float64), seeds, boot)["ci95"],
        "overall_median_longest_flat_run_hp": float(np.median(flat)),
        "overall_median_longest_flat_run_hp_ci95": boot.median_interval(flat, seeds)["ci95"],
        "silver_reference_prices_score_points_per_unit": SILVER_REFERENCE,
        "silver_reference_note": "Silver scores are search points; comparison treats +1 post-battle HP as one point.",
        "by_act": by_act,
        "strata": strata,
        "potion_ids_n_at_least_30": potion_summary,
        "potion_ids_below_reporting_threshold": [
            {"potion_id": int(row["potion_id"]), "n": int(row["n"])}
            for row in potion_items if row["n"] < 30
        ],
        "split_counts": split_rows,
        "split_gain_note": "The tracked compact model stores split indices and thresholds but no gain values; total gain is unavailable.",
    }
    tables = {"q1_strata": pd.DataFrame(strata),
              "q1_potions": pd.DataFrame(potion_summary),
              "q1_split_counts": pd.DataFrame(split_rows)}
    return result, row_table, base, slope, tables


def _calibration(raw, predictions, boot):
    y = raw.won.to_numpy(dtype=np.float64)
    seeds = raw.seed.to_numpy()
    brier = (predictions - y) ** 2
    predicted = _metric(predictions, seeds, boot)
    brier_summary = _metric(brier, seeds, boot)
    seed_labels = raw.groupby("seed", sort=True).won.first().to_numpy(dtype=np.float64)
    observed_runs = boot.seed_mean_interval(seed_labels)
    row_observed = _metric(y, seeds, boot)
    return {
        "mean_predicted_probability_across_raw_rows": predicted,
        "observed_run_win_rate_equal_seed_weight": observed_runs,
        "observed_row_win_rate": row_observed,
        "brier_score_raw_rows": brier_summary,
        "baseline_brier_at_row_prevalence": float(row_observed["mean"]
                                                     * (1.0 - row_observed["mean"])),
        "warning": "128 run seeds provide weak calibration power; rows within a seed are correlated.",
    }


def _q4(raw_all, features, trees, logistic, base_margin, raw_row_table, boot):
    raw = raw_all[raw_all.boundary == "RAW"].copy()
    post = raw_all[raw_all.boundary == "POST"].copy()
    keys = ["seed", "fight_index"]
    if raw.duplicated(keys).any() or post.duplicated(keys).any():
        raise ValueError("E2c-v2 has duplicate (seed,fight_index,boundary) rows")
    pairs = raw.merge(post, on=keys, suffixes=("_raw", "_post"), how="inner", validate="one_to_one")
    if pairs.empty:
        raise ValueError("no matched RAW/POST E2c pairs")
    # Select each state's feature block in the frozen model order. E2c column
    # positions do not define native model order.
    raw_state = pairs[[f"{name}_raw" for name in features]].copy()
    raw_state.columns = features
    post_state = pairs[[f"{name}_post" for name in features]].copy()
    post_state.columns = features
    XR = raw_state.to_numpy(dtype=np.float32)
    XP = post_state.to_numpy(dtype=np.float32)
    delta = predict_rows(XP, trees, logistic, base_margin) - predict_rows(XR, trees, logistic, base_margin)

    rseed = pairs.seed.to_numpy()
    raw_hp = pairs.curHp_raw.to_numpy(dtype=np.float64)
    raw_pots = pairs.potionCount_raw.to_numpy(dtype=np.float64)
    raw_slack = pairs.potionCapacity_raw.to_numpy(dtype=np.float64) - raw_pots
    raw_gold = pairs.gold_raw.to_numpy(dtype=np.float64)
    terms = ["curHp", "potionCount", "potion_slot_slack", "gold"]
    columns = [np.ones(len(pairs)), raw_hp, raw_pots, raw_slack, raw_gold]
    design = np.column_stack(columns)
    beta, _, rank, _ = np.linalg.lstsq(design, delta, rcond=None)
    fitted = design @ beta
    ss_res = float(np.sum((delta - fitted) ** 2))
    ss_tot = float(np.sum((delta - delta.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    unique_seeds, inverse = np.unique(rseed, return_inverse=True)
    boot_beta = np.full((boot.reps, len(beta)), np.nan, dtype=np.float64)
    seed_draws = boot.rng.integers(0, len(unique_seeds), size=(boot.reps, len(unique_seeds)))
    counts = np.zeros((boot.reps, len(unique_seeds)), dtype=np.int16)
    rows_idx = np.arange(len(unique_seeds))
    for draw_i, draw in enumerate(seed_draws):
        counts[draw_i] = np.bincount(draw, minlength=len(unique_seeds))
    weights = counts[:, inverse].astype(np.float64)
    for b in range(boot.reps):
        w = np.sqrt(weights[b])
        boot_beta[b], _, _, _ = np.linalg.lstsq(design * w[:, None], delta * w, rcond=None)

    mean_slope = float(np.nanmean(raw_row_table.s_hp.to_numpy(dtype=np.float64)))
    xmap = {"curHp": raw_hp, "potionCount": raw_pots,
            "potion_slot_slack": raw_slack, "gold": raw_gold}
    coeffs = []
    for j, name in enumerate(["intercept"] + terms):
        values = boot_beta[:, j]
        coeffs.append({
            "term": name,
            "coefficient_delta_probability_per_unit": float(beta[j]),
            "ci95": [float(v) for v in np.nanquantile(values, [0.025, 0.975])],
            "observed_range": (None if name == "intercept" else
                               float(np.nanmax(xmap[name]) - np.nanmin(xmap[name]))),
            "max_absolute_hp_equivalent_range_from_ci": (
                None if name == "intercept" or mean_slope <= 0 else
                float(max(abs(np.nanquantile(values, 0.025)),
                          abs(np.nanquantile(values, 0.975)))
                      * (np.nanmax(xmap[name]) - np.nanmin(xmap[name])) / mean_slope)),
        })
    singular_values = np.linalg.svd(design, compute_uv=False)
    null_terms = []
    if int(rank) < design.shape[1]:
        _, _, vh = np.linalg.svd(design, full_matrices=True)
        for vector in vh[int(rank):]:
            scale = float(np.max(np.abs(vector)))
            null_terms.append({
                "linear_combination": [
                    {"term": name, "weight": float(weight)}
                    for name, weight in zip(["intercept"] + terms, vector)
                    if abs(float(weight)) >= max(1e-8, scale * 1e-5)
                ],
                "interpretation": "these coefficient directions are not separately identified",
            })

    # The slot-slack question is about the held potion's RAW value. Use the Q1
    # per-row potion HP-equivalent, not the RAW-to-POST reward shift above.
    raw_slack_all = (raw.potionCapacity.to_numpy(dtype=np.float64)
                     - raw.potionCount.to_numpy(dtype=np.float64))
    potion_eq_all = raw_row_table.potion_hp_eq.to_numpy(dtype=np.float64)
    all_seeds = raw.seed.to_numpy()
    full = (raw_slack_all == 0) & np.isfinite(potion_eq_all)
    available = (raw_slack_all >= 1) & np.isfinite(potion_eq_all)
    full_eq = potion_eq_all[full]
    available_eq = potion_eq_all[available]
    # Paired seed-cluster bootstrap over seeds represented in both strata.
    full_frame = pd.DataFrame({"seed": all_seeds[full], "value": full_eq}).groupby("seed", sort=True).value.mean()
    avail_frame = pd.DataFrame({"seed": all_seeds[available], "value": available_eq}).groupby("seed", sort=True).value.mean()
    common = np.intersect1d(full_frame.index.to_numpy(), avail_frame.index.to_numpy())
    if len(common) >= 2:
        fvals = full_frame.loc[common].to_numpy()
        avals = avail_frame.loc[common].to_numpy()
        draws = boot.rng.integers(0, len(common), size=(boot.reps, len(common)))
        contrast = avals[draws].mean(axis=1) - fvals[draws].mean(axis=1)
        slack_ci = [float(v) for v in np.quantile(contrast, [0.025, 0.975])]
        slack_mean = float(np.mean(avals - fvals))
    else:
        slack_ci = None
        slack_mean = None
    room_delta = []
    for room_type, label in [("MONSTER", "monster"), ("ELITE", "elite"), ("BOSS", "boss")]:
        mask = pairs.room_type_raw.astype(str).to_numpy() == room_type
        room_delta.append({
            "room_type": label, "n_pairs": int(mask.sum()),
            "mean_delta_probability_post_minus_raw": _metric(delta[mask], rseed[mask], boot),
            "sd_delta_probability": float(np.std(delta[mask], ddof=1)) if int(mask.sum()) > 1 else None,
        })
    return {
        "n_matched_pairs": int(len(pairs)),
        "pairs_by_room": room_delta,
        "delta_probability_regression": {
            "terms": coeffs, "r_squared": float(r2), "rank": int(rank),
            "design_columns": int(design.shape[1]),
            "design_rank_deficient": bool(int(rank) < design.shape[1]),
            "rank_deficient_linear_combinations": null_terms,
            "singular_values": [float(v) for v in singular_values],
            "capacity_values": sorted(int(v) for v in np.unique(pairs.potionCapacity_raw.to_numpy())),
            "coefficient_interpretation": "descriptive conditional on this cohort's observed potion-capacity mix; potionCount and slot slack are fit simultaneously as preregistered after capacities 3 and 5 were observed.",
            "hp_equivalent_reference_mean_s_hp": mean_slope,
        },
        "potion_hp_equivalent_by_slot_slack": {
            "slack_zero_n": int(full.sum()), "slack_zero_mean": _metric(full_eq, all_seeds[full], boot),
            "slack_at_least_one_n": int(available.sum()),
            "slack_at_least_one_mean": _metric(available_eq, all_seeds[available], boot),
            "difference_available_minus_full_mean": slack_mean,
            "difference_available_minus_full_ci95": slack_ci,
            "seeds_in_paired_bootstrap": int(len(common)),
        },
    }


def _q5(raw, features, trees, logistic, base_margin, recorded_slope,
        recorded_potion_eq, act_summary, boot):
    X = _matrix(raw, features, {name: i for i, name in enumerate(features)})
    base = predict_rows(X, trees, logistic, base_margin)
    fair_X = X.copy()
    found = []
    for name in HIDDEN_FUTURE:
        if name in features:
            fair_X[:, features.index(name)] = 0.0
            found.append(name)
    fair_base = predict_rows(fair_X, trees, logistic, base_margin)

    n = len(raw)
    hp = raw.curHp.to_numpy(dtype=np.int32)
    maxhp = raw.maxHp.to_numpy(dtype=np.int32)
    lo_hp = np.maximum(1, hp - 5).astype(np.float32)
    hi_hp = np.minimum(maxhp, hp + 5).astype(np.float32)
    fair_lo, fair_hi = fair_X.copy(), fair_X.copy()
    fair_lo[:, features.index("curHp")] = lo_hp
    fair_hi[:, features.index("curHp")] = hi_hp
    fair_slope = (predict_rows(fair_hi, trees, logistic, base_margin)
                  - predict_rows(fair_lo, trees, logistic, base_margin)) / 10.0

    pot_equivs = np.full(n, np.nan, dtype=np.float64)
    fair_equivs = np.full(n, np.nan, dtype=np.float64)
    if "potionCount" in features:
        feat_idx = {name: i for i, name in enumerate(features)}
        potion_cols = sorted(
            ((int(match.group(1)), col) for col in raw.columns
             if (match := POTION_RE.match(str(col)))), key=lambda item: item[0])
        if potion_cols:
            potion_counts = raw[[col for _, col in potion_cols]].to_numpy(dtype=np.int32)
            row_idx, potion_col_idx = np.nonzero(potion_counts > 0)
            if len(row_idx):
                minus = X[row_idx].copy()
                minus_fair = fair_X[row_idx].copy()
                count_idx = feat_idx["potionCount"]
                minus[:, count_idx] = np.maximum(0.0, minus[:, count_idx] - 1.0)
                minus_fair[:, count_idx] = np.maximum(0.0, minus_fair[:, count_idx] - 1.0)
                for j, (potion_id, _) in enumerate(potion_cols):
                    name = f"pot{potion_id}"
                    if name in feat_idx:
                        selected = np.flatnonzero(potion_col_idx == j)
                        minus[selected, feat_idx[name]] = np.maximum(
                            0.0, minus[selected, feat_idx[name]] - 1.0)
                        minus_fair[selected, feat_idx[name]] = np.maximum(
                            0.0, minus_fair[selected, feat_idx[name]] - 1.0)
                effects = base[row_idx] - predict_rows(minus, trees, logistic, base_margin)
                fair_effects = fair_base[row_idx] - predict_rows(
                    minus_fair, trees, logistic, base_margin)
                effect_sums = np.bincount(row_idx, weights=effects, minlength=n)
                fair_sums = np.bincount(row_idx, weights=fair_effects, minlength=n)
                effect_counts = np.bincount(row_idx, minlength=n)
                means = np.divide(effect_sums, effect_counts, out=np.zeros(n),
                                  where=effect_counts > 0)
                fair_means = np.divide(fair_sums, effect_counts, out=np.zeros(n),
                                       where=effect_counts > 0)
                valid_recorded = (effect_counts > 0) & (recorded_slope > 0)
                valid_fair = (effect_counts > 0) & (fair_slope > 0)
                pot_equivs[valid_recorded] = means[valid_recorded] / recorded_slope[valid_recorded]
                fair_equivs[valid_fair] = fair_means[valid_fair] / fair_slope[valid_fair]
    corr_slope, slope_n = spearman(recorded_slope, fair_slope)
    corr_potion, potion_n = spearman(recorded_potion_eq, fair_equivs)

    acts = raw.act.to_numpy(dtype=int)
    seeds = raw.seed.to_numpy()
    fair_by_act = []
    for act in sorted(np.unique(acts)):
        mask = acts == act
        fair_by_act.append({
            "act": int(act), "n": int(mask.sum()),
            "mean_s_hp": _metric(fair_slope[mask], seeds[mask], boot),
            "mean_potion_hp_equivalent": _metric(np.asarray(fair_equivs)[mask], seeds[mask], boot),
        })
    return {
        "substitute": "zero",
        "classification": "E2c T-fair HIDDEN_FUTURE set; bossId retained as observable/trackable",
        "hidden_fields_zeroed": found,
        "hidden_fields_absent_from_model": [name for name in HIDDEN_FUTURE if name not in features],
        "out_of_distribution_caveat": "Zeroing hidden future fields is the specified offline fallback, not the historical resampling substitute; these feature combinations may be out of distribution.",
        "spearman_recorded_vs_fair_s_hp": {"rho": corr_slope, "n": slope_n},
        "spearman_recorded_vs_fair_potion_hp_equivalent": {"rho": corr_potion, "n": potion_n},
        "act_exchange_rates": fair_by_act,
    }


def _verdict(q1, q4, q5):
    acts = q1["by_act"]
    signs_ok = bool(acts)
    for act in acts:
        slope = act["mean_s_hp"]
        potion = act["mean_held_potion_delta"]
        signs_ok &= bool(slope["mean"] is not None and slope["mean"] > 0
                         and _ci_low(slope) is not None and _ci_low(slope) > 0)
        signs_ok &= bool(potion["mean"] is not None and potion["mean"] > 0
                         and _ci_low(potion) is not None and _ci_low(potion) > 0)
    mono_ok = q1["overall_share_monotone"] >= 0.95
    flat_ok = q1["overall_median_longest_flat_run_hp"] <= 10
    regression = q4["delta_probability_regression"]
    effect_limit_ok = all(
        item["max_absolute_hp_equivalent_range_from_ci"] is None
        or item["max_absolute_hp_equivalent_range_from_ci"] <= 3.0
        for item in regression["terms"] if item["term"] != "intercept")
    q4_ok = regression["r_squared"] < 0.05 or (
        not regression["design_rank_deficient"] and effect_limit_ok)
    rho = q5["spearman_recorded_vs_fair_s_hp"]["rho"]
    q5_ok = rho is not None and rho >= 0.8
    if not signs_ok or not q4_ok or not q5_ok:
        verdict = "VWIN_W1_NOT_READY"
    elif not mono_ok or not flat_ok:
        verdict = "VWIN_W1_NEEDS_SMOOTHING"
    else:
        verdict = "VWIN_W1_READY"
    return {
        "verdict": verdict,
        "threshold_checks": {
            "at_least_95_percent_monotone": {"pass": bool(mono_ok), "observed": q1["overall_share_monotone"]},
            "median_flat_run_at_most_10_hp": {"pass": bool(flat_ok), "observed": q1["overall_median_longest_flat_run_hp"]},
            "positive_hp_and_potion_each_act_with_ci_above_zero": bool(signs_ok),
            "q4_low_effect": bool(q4_ok), "q4_r_squared": regression["r_squared"],
            "q5_hp_slope_spearman_at_least_0_8": bool(q5_ok), "q5_rho": rho,
        },
        "scope": "W1 input readiness only; no gameplay or runtime promotion claim.",
    }


def _write_csv(path, frame):
    if frame is None or frame.empty:
        path.write_text("\n", encoding="utf-8")
        return
    frame.to_csv(path, index=False, float_format="%.10g", lineterminator="\n")


def run_audit(csv_path, model_path, output_dir, latency_json=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    latency = None
    if latency_json:
        latency = json.loads(Path(latency_json).read_text(encoding="utf-8"))
    raw_all = pd.read_csv(csv_path, low_memory=False)
    if "boundary" not in raw_all or "seed" not in raw_all or "won" not in raw_all:
        raise ValueError("expected E2c-v2 rows with boundary, seed, and won columns")
    raw = raw_all[raw_all.boundary == "RAW"].copy().reset_index(drop=True)
    if raw.empty:
        raise ValueError("no RAW rows")
    if not raw.won.isin([0, 1]).all():
        raise ValueError("won labels must be binary")

    features, trees, logistic, base_score, base_margin = load_trees(model_path)
    # Fail closed if the E2c long-format rich block has a missing/duplicated
    # feature. Feature order is then explicitly rebuilt from serialized names.
    if len(set(features)) != len(features):
        raise ValueError("duplicate model feature names")
    if raw.columns.duplicated().any():
        raise ValueError("duplicate E2c column names")
    model_matrix = _matrix(raw, features, {name: i for i, name in enumerate(features)})
    predictions = predict_rows(model_matrix, trees, logistic, base_margin)

    boot = SeedBootstrap()
    q1, row_table, _, slope, q1_tables = _table_q1(
        raw, features, trees, logistic, base_margin, boot)
    q4 = _q4(raw_all, features, trees, logistic, base_margin, row_table, boot)
    q5 = _q5(raw, features, trees, logistic, base_margin, slope,
             row_table.potion_hp_eq.to_numpy(dtype=np.float64), q1["by_act"], boot)
    calibration = _calibration(raw, predictions, boot)
    verdict = _verdict(q1, q4, q5)
    split_thresholds = _split_threshold_counts(trees, features)
    counter_relic_splits = []
    for relic_id, relic_name in COUNTER_RELIC_FEATURES.items():
        feature = f"r{relic_id}"
        thresholds = split_thresholds.get(feature, Counter())
        counter_relic_splits.append({
            "relic_id": relic_id,
            "relic_name_current_enum": relic_name,
            "feature_present_in_model": feature in features,
            "split_count": int(sum(thresholds.values())),
            "counter_value_split_count_threshold_gt_1": int(
                sum(count for threshold, count in thresholds.items() if threshold > 1.0)),
            "split_threshold_counts": [
                {"threshold": float(threshold), "count": int(count)}
                for threshold, count in sorted(thresholds.items())
            ],
        })
    variable_groups = [
        {"reason": "combat HP is copied to GameContext and victory relics can heal at exit",
         "candidates": ["curHp"],
         "sources": ["third_party/silver_lightspeed/src/combat/BattleContext.cpp:494",
                     "third_party/silver_lightspeed/src/combat/BattleContext.cpp:598-613"]},
        {"reason": "Feed raises max HP when it kills a qualifying non-minion",
         "candidates": ["maxHp"],
         "sources": ["third_party/silver_lightspeed/src/combat/Actions.cpp:979-995",
                     "third_party/silver_lightspeed/src/combat/BattleContext.cpp:495"]},
        {"reason": "Hand of Greed can add gold during combat; combat gold is copied on exit",
         "candidates": ["gold"],
         "sources": ["third_party/silver_lightspeed/src/combat/Actions.cpp:1008-1026",
                     "third_party/silver_lightspeed/src/combat/BattleContext.cpp:496"]},
        {"reason": "consumed potion slots and their potion IDs are copied from BattleContext",
         "candidates": ["potionCount"] + sorted(name for name in features if POTION_RE.match(name)),
         "sources": ["third_party/silver_lightspeed/src/combat/BattleContext.cpp:488-489",
                     "apps/one_combat/run_features.cpp:95-100"]},
        {"reason": "Writhing Mass can add Parasite at exit; richRow derives deckSize and per-card counts",
         "candidates": ["deckSize", "d243"],
         "sources": ["third_party/silver_lightspeed/src/combat/BattleContext.cpp:479-484",
                     "apps/one_combat/run_features.cpp:77-80"]},
        {"reason": "exitBattle updates these relic counters/removals and their richRow r{id} values",
         "candidates": ["r26", "r30", "r31", "r35", "r44", "r46", "r52", "r68", "r116"],
         "sources": ["third_party/silver_lightspeed/src/combat/BattleContext.cpp:550-596",
                     "third_party/silver_lightspeed/src/combat/BattleContext.cpp:479-482",
                     "apps/one_combat/run_features.cpp:90-94"]},
    ]
    variable_groups = [dict(group, features=[name for name in group["candidates"] if name in features])
                       for group in variable_groups]
    variable_groups = [group for group in variable_groups if group["features"]]
    results = {
        "schema_version": "vwin-terminal-pricing-audit-1",
        "input": {"csv": str(Path(csv_path)), "model": str(Path(model_path)),
                  "model_sha256": _sha256(model_path),
                  "e2c_sha256": _sha256(csv_path)},
        "model": {"n_features": len(features), "n_trees": len(trees),
                  "logistic": int(logistic), "base_score": float(base_score),
                  "feature_order_source": "models/v_win_trees.txt; aligned to E2c columns by name"},
        "resampling": {"method": "percentile bootstrap over source seeds",
                       "replicates": BOOTSTRAP_REPS, "rng_seed": BOOTSTRAP_SEED},
        "q1": q1,
        "q2": {
            "conclusion": "Inference: No reviewed intervention directly identifies v_win's causal HP slope.",
            "existing_interventional_evidence_review": [
                {"item": "train_winrate.py synthetic +30%-maxHP probe", "finding": "The trainer reports model-space P(win) changes after increasing curHp by 30% of maxHp, clamped to maxHp, stratified by HP band.", "bounds_v_win_hp_slope": False, "reason": "It is a synthetic feature perturbation of the fitted model, not a held-out outcome intervention or a matched native continuation."},
                {"item": "datagen3 / rest_cf paired outcomes", "finding": "Verified repository path trains on paired downstream gate-score differences for out-of-combat actions.", "bounds_v_win_hp_slope": False, "reason": "Rest-versus-upgrade jointly changes HP and progression; it identifies an action contrast, not a controlled HP derivative of this classifier."},
                {"item": "TERM_WIN §109/§116", "finding": "Verified terminal bonus experiment was null on win rate and cost 3.1x at the recorded setup.", "bounds_v_win_hp_slope": False, "reason": "It intervenes on the search policy by adding a tree bonus; it does not perturb terminal HP while holding the other state fixed."},
                {"item": "pathcfgen §63", "finding": "Verified paired route-action continuations exist.", "bounds_v_win_hp_slope": False, "reason": "Route branches alter path, rewards, and later states together; they do not isolate terminal HP."},
                {"item": "Open question", "finding": "No repository artifact found that resumes matched captured states under only an HP offset.", "bounds_v_win_hp_slope": False, "reason": "A controlled continuation intervention remains to be run in a separate authorized study."},
            ],
            "tracked_model_counter_relic_splits": counter_relic_splits,
            "historical_split_claim_review": {
                "claim_location": "docs/experiments/ledger-04.md §§109-110",
                "finding": "The current tracked 1060-tree artifact has counter-value thresholds above 1.0 on multiple relic features; the historical zero-split statement does not describe this tracked artifact.",
                "current_enum_correction": "r116 is Neow's Lament; r131 is Thread and Needle.",
                "artifact_caveat": "The tracked model file matches the original exported build/v_win_trees.txt blob, but the exact model artifact used for the historical §109-110 run is not provenance-bound there. Do not rewrite that historical run's result from this audit.",
                "feature_encoding_source": "apps/one_combat/run_features.cpp:90-94 encodes relic fields as 1 + counter when present; thresholds above 1.0 therefore distinguish counter values for counter relics.",
            },
            "proposed_test": {"status": "Open question: proposed but not run",
                              "captured_states": 8, "hp_offsets": [-10, 0, 10],
                              "matched_continuation_seeds_per_state": 4,
                              "trajectories": 96,
                              "cpu_cost_upper_bound_minutes": 60.8,
                              "cost_basis": "Inference: 96 x 38 CPU-s per continuation using the §340 approx 38 CPU-s/run reference; exact replay cost is unmeasured.",
                              "execution": "seed_guard.sh only; do not execute as part of this audit"},
        },
        "q3_calibration": calibration,
        "q4": q4,
        "q5": q5,
        "q6": {
            "within_combat_vwin_inputs": variable_groups,
            "scope_note": "potionCapacity varies across runs (3 and 5 observed) but is not changed during BattleContext::exitBattle (copied into BattleContext at third_party/silver_lightspeed/src/combat/BattleContext.cpp:47 and omitted from its exit transfer at :488-502); static progression, hidden-future, path, and bottled-card features are unchanged between victorious endings of one combat.",
            "latency": latency,
            "latency_method": "Release -O3/-DNDEBUG direct CompactTreeNet::predict call on the same native class used by g_winNet; 20,000-call per-call timings.",
        },
        "verdict": verdict,
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2, allow_nan=False) + "\n",
                            encoding="utf-8")
    _write_csv(output_dir / "q1_strata.csv", q1_tables["q1_strata"])
    _write_csv(output_dir / "q1_potions.csv", q1_tables["q1_potions"])
    _write_csv(output_dir / "q1_split_counts.csv", q1_tables["q1_split_counts"])
    _write_csv(output_dir / "q2_counter_relic_splits.csv",
               pd.DataFrame(results["q2"]["tracked_model_counter_relic_splits"]))
    _write_csv(output_dir / "q4_regression.csv", pd.DataFrame(q4["delta_probability_regression"]["terms"]))
    print(json.dumps({"results": str(results_path), "verdict": verdict["verdict"],
                      "raw_rows": q1["n_raw_rows"], "matched_pairs": q4["n_matched_pairs"]},
                     sort_keys=True))
    return results


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_self_tests():
    # One monotone step curve has five initial flat steps within the low-HP
    # interval; a second curve has a drop greater than the 0.005 threshold.
    monotone, flat = sweep_shape([0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 10)
    assert monotone and flat == 5, (monotone, flat)
    nonmonotone, _ = sweep_shape([0.2, 0.4, 0.39, 0.7], 4)
    assert not nonmonotone

    # Shared parser's vector and scalar paths agree for a synthetic step tree.
    import tempfile
    from vwin_tree_utils import predict_row
    model_text = ("nfeat 1\nfeat curHp\nlogistic 0\nbase_score 0\nntrees 1\n"
                  "tree 0 3\nS 0 2.5 1 2\nL 0\nL 1\n")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as f:
        f.write(model_text)
        f.flush()
        features, trees, logistic, _, base = load_trees(f.name)
    x = np.asarray([[1], [2], [3]], dtype=np.float32)
    batch = predict_rows(x, trees, logistic, base)
    scalar = np.asarray([predict_row(x[i], trees, logistic, base) for i in range(3)])
    assert np.array_equal(batch, scalar) and np.array_equal(batch, [0, 0, 1])
    print("vwin_terminal_pricing_audit self-test: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--model", default="models/v_win_trees.txt")
    parser.add_argument("--output-dir")
    parser.add_argument("--latency-json")
    args = parser.parse_args()
    if args.self_test:
        run_self_tests()
        return
    if not args.csv or not args.output_dir:
        parser.error("csv and --output-dir are required unless --self-test is used")
    run_audit(args.csv, args.model, args.output_dir, args.latency_json)


if __name__ == "__main__":
    main()
