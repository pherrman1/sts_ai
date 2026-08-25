#!/usr/bin/env python3
"""E3c: isolate the conditional E2c critic on frozen E3a shadow data.

This is an offline, exploratory analysis.  It consumes the published M=16
shadow/reference artifacts and does not run the simulator, train a model, or
change gameplay.  The primary unit is the same sibling-pair/future event used
by E3b, restricted to direct-reference leaves for which both combats survive.

The input reader keeps every identity and CRN seed as decimal strings.  This
is intentional: several are uint64 values and converting them through a
floating-point pandas inference path can silently change a join key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from analyze_e3b_paired_discordance import (
    FUTURES,
    REFERENCE_REQUIRED,
    _validate_and_collapse_reference,
    _validate_and_collapse_shadow,
)
from analyze_runwin_shadow import LEAF_IDENTITY, ROOT_IDENTITY, _validate_shadow


BOOTSTRAP_SEED = 0
BOOTSTRAP_DRAWS = 10_000
SUPPORTS = (1, 2, 3, 4)
BASELINES = ("blendedEval", "vnetPred", "rawRolloutEval")
PRIMARY_SCORE = "conditional_mean"
RISK_SCORES = (
    "conditional_mean",
    "conditional_min",
    "conditional_worst_half",
    "conditional_mean_minus_0.5_std",
    "conditional_mean_minus_1.0_std",
)
ALL_RANKING_SCORES = (PRIMARY_SCORE, *BASELINES)
IDENTITY_STRING_COLUMNS = tuple(LEAF_IDENTITY) + (
    "seed",
    "combatRolloutSeed",
    "downstreamAgentSeed",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_mean(values: Iterable[float]) -> float | None:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    return None if len(values) == 0 else float(values.mean())


def _as_float(value) -> float | None:
    value = float(value)
    return None if not np.isfinite(value) else value


def _json_safe(value):
    """Convert numpy scalars and intentional statistical NaNs to JSON values."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def _json_key(value) -> str:
    return str(value)


def _identity_tuple(row, columns=LEAF_IDENTITY) -> tuple[str, ...]:
    return tuple(str(row[column]) for column in columns)


def _count_by(frame: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    if frame.empty:
        return {}
    result = {}
    for key, value in frame.groupby(columns, dropna=False, sort=True).size().items():
        if not isinstance(key, tuple):
            key = (key,)
        label = "|".join(f"{column}={_json_key(part)}" for column, part in zip(columns, key))
        result[label] = int(value)
    return result


def _sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def _accuracy(score_delta: float, outcome_delta: int) -> float | None:
    if not np.isfinite(score_delta):
        return None
    if _sign(score_delta) == 0:
        return 0.5
    return float(_sign(score_delta) == _sign(outcome_delta))


def _summary(values: Iterable[float]) -> dict:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"count": 0, "mean": None, "std": None, "min": None,
                "max": None, "median": None, "range": None}
    return {
        "count": int(len(values)),
        "mean": float(values.mean()),
        # A one-observation conditional c-vector has no defined empirical
        # spread.  z always has R=4, while c can have support one.
        "std": None if len(values) < 2 else float(values.std(ddof=0)),
        "min": float(values.min()),
        "max": float(values.max()),
        "median": float(np.median(values)),
        "range": float(values.max() - values.min()),
    }


def _worst_half(values: Iterable[float]) -> float | None:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return None
    # For R=4 this is exactly the mean of the two smallest values.  For a
    # conditional c-vector of length 2 or 3, ceil(n/2) is the finite-sample
    # lower-half analogue; it is never presented as population CVaR.
    count = int(math.ceil(len(values) / 2.0))
    return float(np.sort(values)[:count].mean())


def _mean_minus_std(values: Iterable[float], multiplier: float) -> float | None:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return None
    return float(values.mean() - multiplier * values.std(ddof=0))


def _risk_values(z_values: list[float], c_values: list[float]) -> dict:
    z = np.asarray(z_values, dtype=float)
    c = np.asarray(c_values, dtype=float)
    return {
        "z": {
            "worst_1": float(z.min()),
            "worst_half_mean": _worst_half(z),
            "mean_minus_0.5_std": float(z.mean() - 0.5 * z.std(ddof=0)),
            "mean_minus_1.0_std": float(z.mean() - z.std(ddof=0)),
        },
        "c": {
            "min": None if len(c) < 1 else float(c.min()),
            "worst_half_mean": _worst_half(c),
            "mean_minus_0.5_std": _mean_minus_std(c, 0.5),
            "mean_minus_1.0_std": _mean_minus_std(c, 1.0),
        },
    }


def _reconstruct_leaf_distributions(
    shadow: pd.DataFrame, primary: pd.DataFrame
) -> tuple[dict[tuple[str, ...], dict], dict[tuple[str, ...], dict]]:
    """Reconstruct z_r and c_r from raw rows, retaining missing c exactly."""
    raw_by_leaf = {
        _identity_tuple(group.iloc[0]): group.sort_values("replicate", kind="stable")
        for _, group in shadow.groupby(LEAF_IDENTITY, dropna=False, sort=False)
    }
    records = {}
    for _, leaf in primary.iterrows():
        key = _identity_tuple(leaf)
        group = raw_by_leaf[key]
        z = [float(value) for value in group.runwin_probability]
        survived = [int(value) for value in group.survived]
        c = [z[index] for index, value in enumerate(survived) if value == 1]
        if len(z) != 4 or set(group.replicate.astype(int)) != {0, 1, 2, 3}:
            raise ValueError("E3c requires exactly four replicates per primary leaf")
        if int(leaf.survivedCount) != len(c):
            raise ValueError("reconstructed survivedCount disagrees with shadow aggregate")
        conditional = _as_float(leaf.conditional_survival_critic_mean)
        if len(c) == 0 and conditional is not None:
            raise ValueError("zero-survivor leaf has a conditional score")
        if len(c) and not np.isclose(conditional, np.mean(c), rtol=0, atol=1e-12):
            raise ValueError("conditional critic was not reconstructed from surviving rows")
        item = {
            "identity": {column: str(leaf[column]) for column in LEAF_IDENTITY},
            "seed": str(leaf.seed),
            "fightIdx": int(leaf.fightIdx),
            "decIdx": int(leaf.decIdx),
            "act": int(leaf.act),
            "encounter": int(leaf.encounter),
            "hp_band": str(leaf.hp_band),
            "treeDepth": int(leaf.treeDepth),
            "z_values": z,
            "c_values": c,
            "survivedCount": int(len(c)),
            "z": _summary(z),
            "c": _summary(c),
            "risk": _risk_values(z, c),
            "scores": {
                "conditional_mean": conditional,
                "blendedEval": float(leaf.blendedEval),
                "vnetPred": float(leaf.vnetPred),
                "rawRolloutEval": float(leaf.rawRolloutEval),
                "diagnostic_survival_rate": float(leaf.diagnostic_survival_rate),
            },
        }
        records[key] = item
    return records, raw_by_leaf


def _validate_reference_crn(reference: pd.DataFrame) -> None:
    # The imported frozen validator performs this check.  Keep a local explicit
    # assertion because E3c's scientific unit is the same-world CRN event.
    for root, root_group in reference.groupby(ROOT_IDENTITY, dropna=False, sort=False):
        for future, future_group in root_group.groupby("referenceFutureIdx", sort=False):
            if future_group.combatRolloutSeed.nunique(dropna=False) != 1:
                raise ValueError(f"combat CRN violation for root={root}, future={future}")
            if future_group.downstreamAgentSeed.nunique(dropna=False) != 1:
                raise ValueError(f"downstream CRN violation for root={root}, future={future}")


def _build_pairs_and_events(
    primary: pd.DataFrame,
    distributions: dict[tuple[str, ...], dict],
    reference: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ref = reference.copy()
    for column in LEAF_IDENTITY:
        ref[column] = ref[column].astype(str)
    ref = ref.set_index(LEAF_IDENTITY + ["referenceFutureIdx"])
    pair_rows, event_rows = [], []
    root_rows = []
    pair_id = 0
    for root, group in primary.groupby(ROOT_IDENTITY, dropna=False, sort=False):
        group = group.sort_values(LEAF_IDENTITY, kind="stable").reset_index(drop=True)
        root_rows.append({column: str(value) for column, value in zip(ROOT_IDENTITY, root)})
        for left_index in range(len(group)):
            for right_index in range(left_index + 1, len(group)):
                left = group.iloc[left_index]
                right = group.iloc[right_index]
                left_key, right_key = _identity_tuple(left), _identity_tuple(right)
                left_dist, right_dist = distributions[left_key], distributions[right_key]
                pair = {
                    "pair_id": int(pair_id),
                    "seed": str(root[0]),
                    "leaf_i": str(left.leafObsHash),
                    "leaf_k": str(right.leafObsHash),
                    "leaf_i_key": left_key,
                    "leaf_k_key": right_key,
                    "act_i": int(left.act), "act_k": int(right.act),
                    "encounter_i": int(left.encounter), "encounter_k": int(right.encounter),
                    "hp_band_i": str(left.hp_band), "hp_band_k": str(right.hp_band),
                    "treeDepth_i": int(left.treeDepth), "treeDepth_k": int(right.treeDepth),
                }
                for score in ALL_RANKING_SCORES + RISK_SCORES[1:]:
                    if score == "conditional_mean":
                        left_value = left_dist["scores"][score]
                        right_value = right_dist["scores"][score]
                    elif score in BASELINES:
                        left_value = left_dist["scores"][score]
                        right_value = right_dist["scores"][score]
                    else:
                        left_value = left_dist["risk"]["c"][{
                            "conditional_min": "min",
                            "conditional_worst_half": "worst_half_mean",
                            "conditional_mean_minus_0.5_std": "mean_minus_0.5_std",
                            "conditional_mean_minus_1.0_std": "mean_minus_1.0_std",
                        }[score]]
                        right_value = right_dist["risk"]["c"][{
                            "conditional_min": "min",
                            "conditional_worst_half": "worst_half_mean",
                            "conditional_mean_minus_0.5_std": "mean_minus_0.5_std",
                            "conditional_mean_minus_1.0_std": "mean_minus_1.0_std",
                        }[score]]
                    pair[f"{score}_delta"] = (
                        np.nan if left_value is None or right_value is None
                        else float(left_value - right_value)
                    )
                n_all = n_combat = n_downstream = 0
                for future in range(FUTURES):
                    left_row = ref.loc[left_key + (future,)]
                    right_row = ref.loc[right_key + (future,)]
                    outcome_delta = int(left_row.runWon) - int(right_row.runWon)
                    combat_discordant = int(left_row.combatSurvived) != int(right_row.combatSurvived)
                    downstream = (
                        outcome_delta != 0
                        and int(left_row.combatSurvived) == 1
                        and int(right_row.combatSurvived) == 1
                    )
                    if outcome_delta != 0:
                        n_all += 1
                        n_combat += int(combat_discordant)
                        n_downstream += int(downstream)
                        event = {
                            "pair_id": int(pair_id),
                            "seed": str(root[0]),
                            **{column: str(value) for column, value in zip(ROOT_IDENTITY, root)},
                            "referenceFutureIdx": int(future),
                            "D": int(outcome_delta),
                            "combatSurvived_i": int(left_row.combatSurvived),
                            "combatSurvived_k": int(right_row.combatSurvived),
                            "downstream": bool(downstream),
                            "combat_driven": bool(combat_discordant),
                            "act_i": int(left.act), "act_k": int(right.act),
                            "encounter_i": int(left.encounter), "encounter_k": int(right.encounter),
                            "hp_band_i": str(left.hp_band), "hp_band_k": str(right.hp_band),
                            "treeDepth_i": int(left.treeDepth), "treeDepth_k": int(right.treeDepth),
                        }
                        for score in ALL_RANKING_SCORES + RISK_SCORES[1:]:
                            event[f"{score}_delta"] = pair[f"{score}_delta"]
                            event[f"{score}_accuracy"] = _accuracy(
                                pair[f"{score}_delta"], outcome_delta
                            )
                        event_rows.append(event)
                pair.update({
                    "n_all_discordant": int(n_all),
                    "n_combat_driven": int(n_combat),
                    "n_downstream_discordant": int(n_downstream),
                    "no_direct_outcome_discordance": bool(n_all == 0),
                })
                pair_rows.append(pair)
                pair_id += 1
    return pd.DataFrame(pair_rows), pd.DataFrame(event_rows), pd.DataFrame(root_rows).drop_duplicates(ROOT_IDENTITY)


def _root_metrics(events: pd.DataFrame, roots: pd.DataFrame, scores: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for root, _ in roots.groupby(ROOT_IDENTITY, dropna=False, sort=False):
        matching = events
        for column, value in zip(ROOT_IDENTITY, root):
            matching = matching[matching[column].eq(value)]
        item = {column: str(value) for column, value in zip(ROOT_IDENTITY, root)}
        item["seed"] = str(root[0])
        item["event_count"] = int(len(matching))
        item["pair_count"] = int(matching.pair_id.nunique()) if len(matching) else 0
        for score in scores:
            values = pd.to_numeric(matching[f"{score}_accuracy"], errors="coerce")
            item[f"{score}_accuracy"] = _finite_mean(values)
        rows.append(item)
    return pd.DataFrame(rows)


def _root_equal(metrics: pd.DataFrame, scores: tuple[str, ...]) -> dict:
    if metrics.empty:
        return {
            "roots_total": 0,
            "roots_with_informative_events": 0,
            "roots_with_zero_informative_events": 0,
            "informative_events": 0,
            "informative_pairs": 0,
            "accuracy": {
                score: {"roots": 0, "root_equal_event_accuracy": None}
                for score in scores
            },
            "deltas_vs_blendedEval": {
                score: None for score in scores if score != "blendedEval"
            },
        }
    informative = metrics[metrics.event_count > 0]
    result = {
        "roots_total": int(len(metrics)),
        "roots_with_informative_events": int(len(informative)),
        "roots_with_zero_informative_events": int((metrics.event_count == 0).sum()),
        "informative_events": int(metrics.event_count.sum()),
        "informative_pairs": int(informative.pair_count.sum()),
        "accuracy": {},
        "deltas_vs_blendedEval": {},
    }
    for score in scores:
        values = informative[f"{score}_accuracy"].dropna()
        result["accuracy"][score] = {
            "roots": int(len(values)),
            "root_equal_event_accuracy": _finite_mean(values),
        }
        if score != "blendedEval" and "blendedEval_accuracy" in informative.columns:
            delta = informative[f"{score}_accuracy"] - informative["blendedEval_accuracy"]
            result["deltas_vs_blendedEval"][score] = _finite_mean(delta)
    return result


def _per_seed_deltas(metrics: pd.DataFrame, scores: tuple[str, ...]) -> dict[str, dict]:
    result = {}
    for seed, group in metrics.groupby("seed", sort=True, dropna=False):
        item = _root_equal(group.reset_index(drop=True), scores)
        result[str(seed)] = {
            score: item["deltas_vs_blendedEval"].get(score)
            for score in scores if score != "blendedEval"
        }
    return result


def _bootstrap(
    metrics: pd.DataFrame,
    seeds: list[str],
    scores: tuple[str, ...],
    draws: int = BOOTSTRAP_DRAWS,
) -> dict:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    point = _root_equal(metrics, scores)
    comparisons = [score for score in scores if score != "blendedEval"]
    per_seed = {score: [] for score in comparisons}
    for seed in seeds:
        selected = metrics[metrics.seed.eq(seed) & metrics.event_count.gt(0)]
        for score in comparisons:
            delta = selected[f"{score}_accuracy"] - selected["blendedEval_accuracy"]
            per_seed[score].append(delta.dropna().to_numpy(dtype=float))
    samples = {score: [] for score in comparisons}
    duplicate_count = 0
    for _ in range(draws):
        choices = rng.integers(0, len(seeds), size=len(seeds)) if seeds else np.asarray([], dtype=int)
        duplicate_count += int(len(set(choices.tolist())) < len(choices))
        for score in comparisons:
            selected = [per_seed[score][int(index)] for index in choices]
            values = np.concatenate(selected) if selected else np.asarray([], dtype=float)
            samples[score].append(_finite_mean(values))
    result = {
        "unit": "source_seed",
        "rng_seed": BOOTSTRAP_SEED,
        "draws": int(draws),
        "root_weighting": "equal root after source-seed resampling",
        "source_seeds": int(len(seeds)),
        "resamples_with_duplicate_source_seed": int(duplicate_count),
        "estimate": point["deltas_vs_blendedEval"],
        "comparisons": {},
    }
    for score in comparisons:
        finite = np.asarray([value for value in samples[score] if value is not None], dtype=float)
        result["comparisons"][score] = {
            "point": point["deltas_vs_blendedEval"].get(score),
            "bootstrap_mean": _finite_mean(finite),
            "ci95": None if len(finite) == 0 else [
                float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))
            ],
            "finite_resamples": int(len(finite)),
        }
    return result


def _leave_one_out(metrics: pd.DataFrame, seeds: list[str], scores: tuple[str, ...]) -> dict:
    comparisons = [score for score in scores if score != "blendedEval"]
    rows = {}
    for omitted in seeds:
        rows[str(omitted)] = _root_equal(
            metrics[metrics.seed.ne(omitted)].reset_index(drop=True), scores
        )["deltas_vs_blendedEval"]
    ranges = {}
    for score in comparisons:
        values = [row.get(score) for row in rows.values() if row.get(score) is not None]
        ranges[score] = {
            "min": None if not values else float(min(values)),
            "max": None if not values else float(max(values)),
            "range": None if not values else float(max(values) - min(values)),
            "finite_estimates": int(len(values)),
        }
    return {"unit": "source_seed", "per_omitted_seed": rows, "range": ranges}


def _ranking_report(
    events: pd.DataFrame,
    roots: pd.DataFrame,
    eligible_leaves: pd.DataFrame,
    scores: tuple[str, ...],
    draws: int,
) -> dict:
    metrics = _root_metrics(events, roots, scores)
    seeds = sorted(str(value) for value in eligible_leaves.seed.unique())
    return {
        "point": _root_equal(metrics, scores),
        "per_source_seed": _per_seed_deltas(metrics, scores),
        "source_seeds_for_bootstrap": seeds,
        "bootstrap": _bootstrap(metrics, seeds, scores, draws),
        "leave_one_source_seed_out": _leave_one_out(metrics, seeds, scores),
    }


def _support_view(
    primary: pd.DataFrame,
    pairs: pd.DataFrame,
    events: pd.DataFrame,
    roots: pd.DataFrame,
    distributions: dict[tuple[str, ...], dict],
    support: int,
    draws: int,
) -> dict:
    available_keys = {
        key for key, item in distributions.items() if item["survivedCount"] >= support
    }
    eligible = primary[primary.apply(lambda row: _identity_tuple(row) in available_keys, axis=1)].copy()
    selected_pairs = pairs[
        pairs.apply(lambda row: row.leaf_i_key in available_keys and row.leaf_k_key in available_keys, axis=1)
    ].copy()
    selected_events = events[
        events.pair_id.isin(selected_pairs.pair_id) & events.downstream
    ].copy()
    selected_roots = roots[roots.apply(
        lambda row: any(
            _identity_tuple(leaf)[: len(ROOT_IDENTITY)] == tuple(str(row[column]) for column in ROOT_IDENTITY)
            for _, leaf in eligible.iterrows()
        ), axis=1
    )].copy()
    # The explicit roots construction above is readable but can be expensive
    # for a large future bundle; the frozen M=16 artifact is intentionally
    # small.  It also makes the definition "roots represented by eligible
    # leaves" unambiguous.
    if selected_roots.empty and not eligible.empty:
        selected_roots = eligible[ROOT_IDENTITY].drop_duplicates().copy()
    selected_roots = selected_roots.drop_duplicates(ROOT_IDENTITY).reset_index(drop=True)
    scores = ALL_RANKING_SCORES
    ranking = _ranking_report(selected_events, selected_roots, eligible, scores, draws)
    coverage = {
        "survivedCount_support": f">={support}" if support < 4 else "==4",
        "leaves_available": int(len(eligible)),
        "sibling_pairs_available": int(len(selected_pairs)),
        "downstream_discordant_events": int(len(selected_events)),
        "roots_represented_by_available_leaves": int(len(selected_roots)),
        "roots_with_downstream_events": int(selected_events[ROOT_IDENTITY].drop_duplicates().shape[0]) if len(selected_events) else 0,
        "source_seeds_represented_by_available_leaves": int(eligible.seed.nunique()),
        "source_seeds_with_downstream_events": int(selected_events.seed.nunique()) if len(selected_events) else 0,
    }
    return {"coverage": coverage, "ranking": ranking}


def _distribution_strata(distributions: dict[tuple[str, ...], dict]) -> dict:
    rows = []
    for key, item in distributions.items():
        row = {
            "act": str(item["act"]),
            "encounter": str(item["encounter"]),
            "hp_band": item["hp_band"],
            "treeDepth": str(item["treeDepth"]),
            "conditional_mean": item["c"]["mean"],
            "conditional_std": item["c"]["std"],
            "conditional_min": item["c"]["min"],
            "conditional_max": item["c"]["max"],
            "conditional_range": item["c"]["range"],
            "survivedCount": item["survivedCount"],
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    fields = ("act", "encounter", "hp_band", "treeDepth")
    numeric = (
        "conditional_mean", "conditional_std", "conditional_min",
        "conditional_max", "conditional_range", "survivedCount",
    )
    result = {}
    for field in fields:
        groups = {}
        for value, group in frame.groupby(field, dropna=False, sort=True):
            groups[str(value)] = {
                "leaves": int(len(group)),
                "available_conditional_means": int(group.conditional_mean.notna().sum()),
                "summaries": {column: _summary(group[column].dropna()) for column in numeric},
                "conditional_mean_histogram_0_to_1": _histogram(group.conditional_mean.dropna()),
            }
        result[field] = groups
    return result


def _histogram(values: Iterable[float], bins: int = 10) -> dict:
    edges = np.linspace(0.0, 1.0, bins + 1)
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    counts, _ = np.histogram(values, bins=edges)
    return {
        "edges": [float(value) for value in edges],
        "counts": [int(value) for value in counts],
        "out_of_range": int(np.sum((values < 0) | (values > 1))),
    }


def _cohort_spread(
    pairs: pd.DataFrame, distributions: dict[tuple[str, ...], dict]
) -> dict:
    incidence_rows = []
    for _, pair in pairs.iterrows():
        categories = []
        if int(pair.n_downstream_discordant) > 0:
            categories.append("downstream_discordant")
        if int(pair.n_combat_driven) > 0:
            categories.append("combat_driven")
        if bool(pair.no_direct_outcome_discordance):
            categories.append("no_direct_outcome_discordance")
        for category in categories:
            for side, key in (("i", pair.leaf_i_key), ("k", pair.leaf_k_key)):
                item = distributions[key]
                incidence_rows.append({
                    "category": category,
                    "pair_id": int(pair.pair_id),
                    "critic_std": item["c"]["std"],
                    "critic_range": item["c"]["range"],
                    "survivedCount": item["survivedCount"],
                })
    incidence = pd.DataFrame(incidence_rows)
    result = {}
    for category in ("downstream_discordant", "combat_driven", "no_direct_outcome_discordance"):
        selected = incidence[incidence.category.eq(category)] if len(incidence) else incidence
        pair_level = selected.groupby("pair_id", sort=True).agg(
            critic_std=("critic_std", "mean"), critic_range=("critic_range", "mean")
        ) if len(selected) else pd.DataFrame()
        result[category] = {
            "pair_count": int(selected.pair_id.nunique()) if len(selected) else 0,
            "leaf_incidences": int(len(selected)),
            "critic_std_by_leaf_incidence": _summary(selected.critic_std if len(selected) else []),
            "critic_range_by_leaf_incidence": _summary(selected.critic_range if len(selected) else []),
            "survivedCount_by_leaf_incidence": _summary(selected.survivedCount if len(selected) else []),
            "pair_mean_critic_std": _summary(pair_level.critic_std if len(pair_level) else []),
            "pair_mean_critic_range": _summary(pair_level.critic_range if len(pair_level) else []),
        }
    return result


def _heterogeneity_correlation(
    pairs: pd.DataFrame, distributions: dict[tuple[str, ...], dict]
) -> dict:
    rows = []
    for _, pair in pairs.iterrows():
        disagree = bool(int(pair.n_all_discordant) > 0)
        for key in (pair.leaf_i_key, pair.leaf_k_key):
            item = distributions[key]
            rows.append({
                "direct_outcome_disagreement": disagree,
                "critic_std": item["c"]["std"],
                "critic_range": item["c"]["range"],
            })
    frame = pd.DataFrame(rows)
    groups = {}
    for label, group in frame.groupby("direct_outcome_disagreement", sort=True):
        groups[str(bool(label))] = {
            "leaf_incidences": int(len(group)),
            "critic_std": _summary(group.critic_std),
            "critic_range": _summary(group.critic_range),
        }
    result = {"unit": "leaf incidence within a sibling pair", "groups": groups, "correlations": {}}
    for column in ("critic_std", "critic_range"):
        valid = frame[["direct_outcome_disagreement", column]].dropna()
        if len(valid) < 2 or valid.direct_outcome_disagreement.nunique() < 2:
            result["correlations"][column] = {"pearson_with_disagreement": None, "spearman_with_disagreement": None}
        else:
            result["correlations"][column] = {
                "pearson_with_disagreement": _as_float(np.corrcoef(
                    valid.direct_outcome_disagreement.astype(float), valid[column].astype(float)
                )[0, 1]),
                "spearman_with_disagreement": _as_float(pd.Series(valid.direct_outcome_disagreement.astype(float)).corr(
                    pd.Series(valid[column].astype(float)), method="spearman"
                )),
            }
    return result


def _score_separation(
    pairs: pd.DataFrame, events: pd.DataFrame, distributions: dict[tuple[str, ...], dict]
) -> dict:
    usable = pairs[np.isfinite(pairs["conditional_mean_delta"].astype(float))].copy()
    usable = usable[usable.n_downstream_discordant > 0]
    if usable.empty:
        return {"pair_count": 0, "quartile_edges": None, "quartiles": {}, "descriptive_thresholds": {}}
    separation = usable.conditional_mean_delta.abs().to_numpy(dtype=float)
    edges = np.quantile(separation, [0, 0.25, 0.5, 0.75, 1]).tolist()
    labels = np.searchsorted(np.asarray(edges[1:-1]), separation, side="right") + 1
    usable = usable.copy()
    usable["quartile"] = labels
    selected_events = events[events.pair_id.isin(usable.pair_id) & events.downstream].copy()
    quartiles = {}
    for quartile in range(1, 5):
        selected_pairs = usable[usable.quartile.eq(quartile)]
        selected = selected_events[selected_events.pair_id.isin(selected_pairs.pair_id)]
        roots = selected[ROOT_IDENTITY].drop_duplicates() if len(selected) else pd.DataFrame(columns=ROOT_IDENTITY)
        metrics = _root_metrics(selected, roots, (PRIMARY_SCORE,))
        point = _root_equal(metrics, (PRIMARY_SCORE,))
        quartiles[f"Q{quartile}"] = {
            "score_separation_min": float(edges[quartile - 1]),
            "score_separation_max": float(edges[quartile]),
            "pairs": int(len(selected_pairs)),
            "events": int(len(selected)),
            "roots": int(point["roots_with_informative_events"]),
            "root_equal_event_accuracy": point["accuracy"][PRIMARY_SCORE]["root_equal_event_accuracy"],
        }
    thresholds = {}
    for index, quantile in (("Q25", 0.25), ("Q50", 0.50), ("Q75", 0.75)):
        threshold = float(np.quantile(separation, quantile))
        selected_pairs = usable[usable.conditional_mean_delta.abs() >= threshold]
        selected = selected_events[selected_events.pair_id.isin(selected_pairs.pair_id)]
        roots = selected[ROOT_IDENTITY].drop_duplicates() if len(selected) else pd.DataFrame(columns=ROOT_IDENTITY)
        point = _root_equal(_root_metrics(selected, roots, (PRIMARY_SCORE,)), (PRIMARY_SCORE,))
        thresholds[index] = {
            "empirical_threshold": threshold,
            "pairs": int(len(selected_pairs)),
            "events": int(len(selected)),
            "roots": int(point["roots_with_informative_events"]),
            "root_equal_event_accuracy": point["accuracy"][PRIMARY_SCORE]["root_equal_event_accuracy"],
        }
    return {"pair_count": int(len(usable)), "quartile_edges": [float(value) for value in edges],
            "quartiles": quartiles, "descriptive_thresholds": thresholds}


def _risk_summary_reports(
    pairs: pd.DataFrame,
    events: pd.DataFrame,
    roots: pd.DataFrame,
    primary: pd.DataFrame,
    distributions: dict[tuple[str, ...], dict],
    draws: int,
) -> dict:
    result = {}
    for support in SUPPORTS:
        available = {key for key, item in distributions.items() if item["survivedCount"] >= support}
        eligible = primary[primary.apply(lambda row: _identity_tuple(row) in available, axis=1)]
        selected_pairs = pairs[pairs.apply(
            lambda row: row.leaf_i_key in available and row.leaf_k_key in available, axis=1
        )]
        selected_events = events[events.pair_id.isin(selected_pairs.pair_id) & events.downstream]
        report = _ranking_report(selected_events, roots, eligible, RISK_SCORES + BASELINES, draws)
        report["support"] = ">=" + str(support) if support < 4 else "==4"
        report["risk_statistic_support_note"] = (
            "conditional min is available at support >=1; conditional worst-half and mean-minus-lambda-std "
            "are omitted for a leaf with fewer than two surviving replicates."
        )
        result[str(support)] = report
    return result


def _coverage_all(primary: pd.DataFrame, pairs: pd.DataFrame, events: pd.DataFrame) -> dict:
    downstream = events[events.downstream]
    combat = events[events.combat_driven]
    return {
        "primary_complete_leaves": int(len(primary)),
        "all_sibling_pairs": int(len(pairs)),
        "all_discordant_events": int(len(events)),
        "combat_driven_events": int(len(combat)),
        "downstream_discordant_events": int(len(downstream)),
        "roots": int(primary[ROOT_IDENTITY].drop_duplicates().shape[0]),
        "source_seeds": int(primary.seed.nunique()),
        "events_by_source_seed": _count_by(downstream, ["seed"]),
        "events_by_act": _count_by(downstream, ["act_i"]),
        "events_by_encounter": _count_by(downstream, ["encounter_i"]),
        "events_by_hp_band_i": _count_by(downstream, ["hp_band_i"]),
        "events_by_treeDepth_i": _count_by(downstream, ["treeDepth_i"]),
    }


def _classify(report: dict) -> tuple[str, str]:
    """A predeclared, deliberately conservative exploratory decision rule."""
    primary = report["support_thresholds"]["1"]["ranking"]
    primary_delta = primary["bootstrap"]["comparisons"].get(PRIMARY_SCORE, {})
    primary_loo = primary["leave_one_source_seed_out"]["range"].get(PRIMARY_SCORE, {})
    primary_robust = (
        primary_delta.get("point") is not None
        and primary_delta["point"] > 0
        and primary_delta.get("ci95") is not None
        and primary_delta["ci95"][0] > 0
        and primary_loo.get("min") is not None
        and primary_loo["min"] > 0
    )
    robust_risk = []
    for support, item in report["risk_summaries"].items():
        for score, comparison in item["bootstrap"]["comparisons"].items():
            if score not in RISK_SCORES or score == PRIMARY_SCORE:
                continue
            loo = item["leave_one_source_seed_out"]["range"].get(score, {})
            if (
                comparison.get("point") is not None and comparison["point"] > 0
                and comparison.get("ci95") is not None and comparison["ci95"][0] > 0
                and loo.get("min") is not None and loo["min"] > 0
            ):
                robust_risk.append(f"support {support}: {score}")
    if report["coverage"]["downstream_discordant_events"] == 0:
        return "E3C_INCONCLUSIVE", "No downstream-discordant events were available after the direct-reference survival restriction."
    if primary_robust and not robust_risk:
        return "E3C_CONDITIONAL_SIGNAL", "The conditional mean has a positive downstream delta with a bootstrap CI above zero and every leave-one-source-seed-out estimate positive; no conservative summary shows a separate robust effect."
    if not primary_robust and robust_risk:
        return "E3C_RISK_SIGNAL_ONLY", "The conditional mean does not meet the predeclared robust criterion, but a predeclared conservative summary does; this remains exploratory and needs confirmation."
    # A mixed-sign leave-one-seed-out range is instability; with adequate event
    # coverage it is more informative to label the result inconclusive than to
    # call a noisy estimate a null.
    if primary_loo.get("min") is not None and primary_loo.get("max") is not None and primary_loo["min"] <= 0 < primary_loo["max"]:
        return "E3C_INCONCLUSIVE", "The conditional mean changes sign under leave-one-source-seed-out sensitivity, so the downstream evidence is source-seed unstable."
    return "E3C_NO_CONDITIONAL_SIGNAL", "Neither the conditional mean nor the predeclared conservative conditional summaries shows a robust downstream advantage over blendedEval."


def _conceptual_assessment(report: dict) -> dict:
    label = report["classification"]["label"]
    robust = label in ("E3C_CONDITIONAL_SIGNAL", "E3C_RISK_SIGNAL_ONLY")
    return {
        "conditional_e2c_downstream_ranking_signal": (
            "supported only under the stated exploratory robustness rule" if robust else
            "not established by this frozen M=16 analysis"
        ),
        "alternative_explanations": [
            "post-combat training-distribution mismatch: open question; this analysis does not identify it",
            "scalar expectation insufficient: plausible if conditional c-vectors vary in decision-relevant ways, but R=4 cannot establish it",
            "omitted observable features: open question",
            "hidden-world target mismatch: important limitation because the reference is same-world CRN, not information-set marginalization",
            "weak local ranking objective: open question",
            "insufficient model capacity: open question",
            "no useful signal in these leaf differences: consistent with a null or unstable E3c result",
        ],
        "distributional_model_potential": (
            "A distributional model could help only if decision-relevant return-distribution variation exists and is represented by the features/target. Current R=4 same-world policy-RNG samples do not justify training one or claim that it would solve feature or target mismatch. A future confirmatory design could compare quantile regression, categorical distributional value, multiple quantiles, or mean-plus-variance/uncertainty; CVaR would then be derived from predicted quantiles rather than four raw Bernoulli samples."
        ),
        "research_direction_justified": (
            "Only as a future measurement/design direction, not as a deployment intervention: richer return targets and hidden-world particles should be evaluated before architecture work."
        ),
    }


def _markdown(report: dict) -> str:
    cov = report["coverage"]
    lines = [
        "# E3c conditional E2c run-win analysis",
        "",
        "Exploratory offline analysis of the frozen a93b3c6 published M=16 shadow/reference artifacts. No simulation, training, gameplay change, M=32 run, or threshold/lambda search was performed.",
        "",
        f"**Decision label: `{report['classification']['label']}`.** {report['classification']['reason']}",
        "",
        "## Frozen inputs and contracts",
        "",
        f"- Command: `{report['reproducibility']['command']}`",
        f"- Frozen producer SHA: `{report['analysis']['frozen_git_sha']}`; shadow SHA-256: `{report['artifact_provenance']['shadow_csv']['sha256']}`; reference SHA-256: `{report['artifact_provenance']['reference_csv']['sha256']}`.",
        "- Primary event: sibling leaves share a direct-reference future; both `combatSurvived=1` and `D=runWon_i-runWon_k != 0`.",
        "- Scores are tie-aware: a score tie receives accuracy 0.5. Accuracy is averaged within root, then roots receive equal weight. Source-seed bootstrap is the outer resampling unit.",
        "- `z_r` is the four-value `runwin_probability` vector, mixing survival and post-combat prediction. `c_r` contains only the surviving-replicate values and is never imputed when support is zero.",
        "",
        "## Coverage",
        "",
        f"- Complete primary leaves: **{cov['primary_complete_leaves']}**; all sibling pairs: **{cov['all_sibling_pairs']}**; roots: **{cov['roots']}**; source seeds: **{cov['source_seeds']}**.",
        f"- All direct outcome-discordant events: **{cov['all_discordant_events']}**; combat-driven: **{cov['combat_driven_events']}**; downstream-discordant: **{cov['downstream_discordant_events']}**.",
        "",
        "| Conditional support | Leaves | sibling pairs | downstream events | roots represented | source seeds represented |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for support in SUPPORTS:
        item = report["support_thresholds"][str(support)]["coverage"]
        lines.append(f"| `{item['survivedCount_support']}` | {item['leaves_available']} | {item['sibling_pairs_available']} | {item['downstream_discordant_events']} | {item['roots_represented_by_available_leaves']} | {item['source_seeds_represented_by_available_leaves']} |")
    lines.extend(["", "## Conditional-mean ranking", "", "The primary delta is conditional critic accuracy minus `blendedEval` accuracy.", "", "| Support | Conditional mean | blendedEval | vnetPred | rawRolloutEval | Δ conditional−blend | bootstrap mean | 95% CI |", "|---|---:|---:|---:|---:|---:|---:|---|"])
    for support in SUPPORTS:
        item = report["support_thresholds"][str(support)]["ranking"]
        acc = item["point"]["accuracy"]
        delta = item["bootstrap"]["comparisons"][PRIMARY_SCORE]
        ci = "—" if delta["ci95"] is None else f"[{delta['ci95'][0]:.6f}, {delta['ci95'][1]:.6f}]"
        lines.append(f"| `{support}` | {acc[PRIMARY_SCORE]['root_equal_event_accuracy']!s} | {acc['blendedEval']['root_equal_event_accuracy']!s} | {acc['vnetPred']['root_equal_event_accuracy']!s} | {acc['rawRolloutEval']['root_equal_event_accuracy']!s} | {delta['point']!s} | {delta['bootstrap_mean']!s} | {ci} |")
    lines.extend(["", "### Per-source-seed conditional-minus-blended values (`survivedCount >= 1`)", "", "| Source seed | Δ |", "|---|---:|"])
    for seed, value in report["support_thresholds"]["1"]["ranking"]["per_source_seed"].items():
        lines.append(f"| `{seed}` | {value.get(PRIMARY_SCORE)!s} |")
    loo = report["support_thresholds"]["1"]["ranking"]["leave_one_source_seed_out"]["range"][PRIMARY_SCORE]
    lines.extend(["", f"Leave-one-source-seed-out conditional Δ range at support `>=1`: **{loo['min']} to {loo['max']}** (range {loo['range']}).", ""])
    lines.extend(["## Conservative conditional risk summaries", "", "These are finite-sample tail-like summaries, not well-estimated population CVaR. `worst-half` uses the lower half of the available c-vector; with R=4 z this is the two smallest values. Conditional tail summaries are absent for fewer than two surviving replicates.", "", "| Support | Score | root-equal accuracy | Δ vs blend | bootstrap mean | 95% CI |", "|---|---|---:|---:|---:|---|"])
    for support in SUPPORTS:
        item = report["risk_summaries"][str(support)]
        for score in RISK_SCORES:
            acc = item["point"]["accuracy"].get(score, {})
            delta = item["bootstrap"]["comparisons"].get(score, {})
            ci = "—" if delta.get("ci95") is None else f"[{delta['ci95'][0]:.6f}, {delta['ci95'][1]:.6f}]"
            lines.append(f"| `{support}` | `{score}` | {acc.get('root_equal_event_accuracy')!s} | {delta.get('point')!s} | {delta.get('bootstrap_mean')!s} | {ci} |")
    lines.extend(["", "## Distribution and heterogeneity", "", "The JSON contains every primary leaf's reconstructed z/c vectors and summaries. The fixed-bin conditional-mean histogram is reported globally and by act, encounter, HP band, and tree depth.", "", f"- Global conditional-mean histogram: `{json.dumps(report['distribution']['conditional_mean_histogram_0_to_1'], sort_keys=True)}`", "", "| Pair cohort | pairs | leaf incidences | critic std mean | critic range mean |", "|---|---:|---:|---:|---:|"])
    for cohort, item in report["cohort_spread"].items():
        lines.append(f"| `{cohort}` | {item['pair_count']} | {item['leaf_incidences']} | {item['critic_std_by_leaf_incidence']['mean']!s} | {item['critic_range_by_leaf_incidence']['mean']!s} |")
    lines.extend(["", f"Correlation unit: **{report['heterogeneity']['unit']}**. These are descriptive associations, not causal tests. Critic-std Pearson/Spearman with direct outcome disagreement: `{report['heterogeneity']['correlations']['critic_std']}`; critic-range: `{report['heterogeneity']['correlations']['critic_range']}`.", ""])
    lines.extend(["## Confidence gating", "", "Quartiles and thresholds are descriptive empirical summaries of `|conditional_mean_i-conditional_mean_k|`; no deployment threshold was selected.", "", "| Bin/threshold | pairs | events | roots | root-equal accuracy |", "|---|---:|---:|---:|---:|"])
    separation = report["score_separation"]
    for name, item in separation["quartiles"].items():
        lines.append(f"| `{name}` | {item['pairs']} | {item['events']} | {item['roots']} | {item['root_equal_event_accuracy']!s} |")
    for name, item in separation["descriptive_thresholds"].items():
        lines.append(f"| `abs(delta) >= {name}` ({item['empirical_threshold']:.6g}) | {item['pairs']} | {item['events']} | {item['roots']} | {item['root_equal_event_accuracy']!s} |")
    lines.extend(["", "## CVaR / risk conceptual assessment", "", "For a binary run-win target, lower-tail CVaR is often degenerate: when loss probability exceeds alpha, the worst alpha tail is nearly all losses and gives little fine-grained ordering. The more useful future objects are conditional critic distributions, richer floor/HP/resource returns, or distributions over hidden-world particles.", "", "1. **Aleatoric combat/policy RNG:** the current R=4 continuation distribution probes this, conditional on one copied world.", "2. **Hidden-world uncertainty:** current same-world CRN does not marginalize unknown draw order, map, encounter, or reward worlds.", "3. **Strategic run-outcome uncertainty:** `z` mixes survival with post-combat prediction and is still a binary run-win proxy.", "4. **Model uncertainty:** current replicates do not measure uncertainty in the learned critic.", "", "Thus these empirical tails are not information-set CVaR. A future distributional evaluator should only be investigated with richer targets and/or hidden-world particles; R=4 is too small for reliable population CVaR estimation.", "", "## Model architecture assessment", "", f"- Conditional E2c downstream signal: {report['conceptual_assessment']['conditional_e2c_downstream_ranking_signal']}.", f"- Assessment: {report['conceptual_assessment']['distributional_model_potential']}", f"- Research direction: {report['conceptual_assessment']['research_direction_justified']}", "- The alternatives listed in the JSON remain open explanations; this analysis cannot distinguish training mismatch, insufficient scalar targets, omitted features, hidden-world mismatch, ranking objective, capacity, or no signal from these data alone.", "", "## Decision", "", f"`{report['classification']['label']}` — {report['classification']['reason']}", "", "No E3c label authorizes gameplay promotion. Recommended next scientific step: use this result to design a confirmatory offline study with a richer return target and explicit hidden-world particles, retaining the same root-equal/source-seed protocol; do not train or integrate a distributional model from these R=4 samples alone.", ""])
    return "\n".join(lines)


def analyze(shadow: pd.DataFrame, reference: pd.DataFrame, draws: int = BOOTSTRAP_DRAWS) -> dict:
    _validate_shadow(shadow)
    all_leaves, primary = _validate_and_collapse_shadow(shadow.copy())
    exclusions = {}
    _validate_and_collapse_reference(reference, primary)
    _validate_reference_crn(reference)
    distributions, raw_by_leaf = _reconstruct_leaf_distributions(shadow, primary)
    pairs, events, roots = _build_pairs_and_events(primary, distributions, reference)
    support_thresholds = {}
    for support in SUPPORTS:
        support_thresholds[str(support)] = _support_view(
            primary, pairs, events, roots, distributions, support, draws
        )
    risk_reports = _risk_summary_reports(pairs, events, roots, primary, distributions, draws)
    leaf_rows = list(distributions.values())
    report = {
        "analysis": {
            "name": "E3c conditional E2c run-win analysis",
            "version": 1,
            "status": "exploratory",
            "frozen_git_sha": "a93b3c68fc4efaaf9e9858d7aca571baac1a68d4",
            "event_definition": "D=runWon_i-runWon_k != 0 and both direct-reference combatSurvived values are 1",
            "primary_score": PRIMARY_SCORE,
            "primary_baseline": "blendedEval",
            "secondary_baselines": list(BASELINES[1:]),
            "root_aggregation": "mean event accuracy within root, then equal root weighting",
            "bootstrap": "source seed resampling; equal root weighting after resampling",
            "bootstrap_rng_seed": BOOTSTRAP_SEED,
            "bootstrap_draws": int(draws),
            "no_simulation_training_or_gameplay": True,
        },
        "artifact_provenance": {},
        "contracts": {
            "leaf_identity": list(LEAF_IDENTITY),
            "root_identity": list(ROOT_IDENTITY),
            "shadow_replicates": 4,
            "reference_futures": FUTURES,
            "conditional_score_missing_when_survivedCount_zero": True,
            "reference_invalid_rows_rejected": True,
            "same_world_crn_validated": True,
            "identity_parse": "decimal strings, including uint64 hashes and CRN seeds",
        },
        "coverage": _coverage_all(primary, pairs, events),
        "exclusions": {str(key): int(value) for key, value in exclusions.items()},
        "support_thresholds": support_thresholds,
        "risk_summaries": risk_reports,
        "distribution": {
            "leaf_count": int(len(leaf_rows)),
            "leaf_summaries": leaf_rows,
            "conditional_mean_histogram_0_to_1": _histogram([item["c"]["mean"] for item in leaf_rows]),
            "stratified_by": _distribution_strata(distributions),
        },
        "cohort_spread": _cohort_spread(pairs, distributions),
        "heterogeneity": _heterogeneity_correlation(pairs, distributions),
        "score_separation": _score_separation(pairs, events, distributions),
    }
    label, reason = _classify(report)
    report["classification"] = {
        "label": label,
        "reason": reason,
        "gameplay_promotion_authorized": False,
        "decision_rule": "robust means positive point, 95% source-seed bootstrap lower CI > 0, and every finite leave-one-source-seed-out estimate > 0; risk-only requires this for a predeclared conservative summary while the conditional mean fails it",
    }
    report["conceptual_assessment"] = _conceptual_assessment(report)
    return report


def _default_paths(repo: Path) -> tuple[Path, Path]:
    base = repo / "build" / "e3a_designated_a93b3c6_m16_artifacts" / "sts_sweep" / "build"
    return base / "e3a_designated_a93b3c6_m16.csv", base / "e3a_designated_a93b3c6_m16.csv.reference.csv"


def _read_csv_preserving_identity(path: Path) -> pd.DataFrame:
    dtype = {column: "string" for column in IDENTITY_STRING_COLUMNS}
    return pd.read_csv(path, dtype=dtype)


def _artifact_provenance(shadow_path: Path, reference_path: Path) -> dict:
    return {
        "shadow_csv": {"path": str(shadow_path), "sha256": _sha256(shadow_path), "bytes": int(shadow_path.stat().st_size)},
        "reference_csv": {"path": str(reference_path), "sha256": _sha256(reference_path), "bytes": int(reference_path.stat().st_size)},
    }


def _make_self_test_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, refs = [], []
    huge = "18446744073709551610"
    for root_index, seed in enumerate((huge, "18446744073709551611")):
        root_hash = str(18446744073709551500 + root_index)
        for leaf_index in range(2):
            leaf_hash = str(18446744073709551400 + root_index * 10 + leaf_index)
            support = 0 if (root_index == 1 and leaf_index == 1) else 4
            z = [0.0, 0.0, 0.0, 0.0] if support == 0 else [0.2 + 0.1 * leaf_index] * 4
            survived = [0, 0, 0, 0] if support == 0 else [1, 1, 1, 1]
            for replicate in range(4):
                rows.append({
                    "seed": seed, "fightIdx": 0, "decIdx": root_index,
                    "floor": 10, "act": 1, "room": 1, "encounter": 2,
                    "rootObsHash": root_hash, "rootActionBits": 1,
                    "leafObsHash": leaf_hash, "leaf_curHp": 50, "leaf_maxHp": 50,
                    "leaf_hpFrac": 1.0, "treeDepth": 3, "searchSimulation": 7 + leaf_index,
                    "particleIndex": leaf_index, "particleWeight": 1.0,
                    "particleExact": 1, "particleFallback": 0, "rootCarried": 0,
                    "reuseGeneration": 0, "reuseSearchCount": 0, "rolloutSteps": 1,
                    "vnetPred": float(leaf_index), "rawRolloutEval": float(leaf_index),
                    "blendedEval": float(1 - leaf_index), "replicate": replicate,
                    "terminal": 1, "survived": survived[replicate],
                    "runwin_probability": z[replicate], "replicates": 4,
                    "survivedCount": support, "diagnostic_survival_rate": support / 4,
                    "conditional_survival_critic_mean": np.nan if support == 0 else z[replicate],
                    "runwin_mean": float(np.mean(z)), "runwin_std": 0.0,
                    "runwin_min": float(min(z)), "runwin_max": float(max(z)),
                    "projectionFailure": 0, "inferenceFailure": 0,
                })
            for future in range(16):
                # Same CRN seeds within the root/future.  Future zero is an
                # informative downstream event for both roots; all others tie.
                left_win = int(future == 0)
                right_win = 0
                if root_index == 1:
                    left_win, right_win = 0, int(future == 0)
                for current_leaf, run_win in ((leaf_index, left_win if leaf_index == 0 else right_win),):
                    refs.append({
                        "seed": seed, "fightIdx": 0, "decIdx": root_index,
                        "rootObsHash": root_hash, "rootActionBits": 1,
                        "leafObsHash": leaf_hash, "searchSimulation": 7 + current_leaf,
                        "particleIndex": current_leaf, "referenceFutureIdx": future,
                        "combatRolloutSeed": str(10000000000000000000 + root_index * 100 + future),
                        "downstreamAgentSeed": str(11000000000000000000 + root_index * 100 + future),
                        "combatSurvived": 1, "runWon": run_win, "valid": 1,
                        "finalFloor": 20, "endHp": 40, "healthStatus": "alive",
                    })
    return pd.DataFrame(rows), pd.DataFrame(refs)


def _run_self_test() -> None:
    shadow, reference = _make_self_test_data()
    # This validates uint64 identity preservation through the complete parser
    # and analysis path, including the CRN reference join.
    report = analyze(shadow, reference, draws=64)
    assert report["coverage"]["primary_complete_leaves"] == 4
    assert report["support_thresholds"]["1"]["coverage"]["leaves_available"] == 3
    assert report["support_thresholds"]["4"]["coverage"]["leaves_available"] == 3
    assert report["distribution"]["leaf_summaries"][0]["c"]["mean"] == 0.2
    assert report["distribution"]["leaf_summaries"][0]["c"]["count"] == 4
    assert report["distribution"]["leaf_summaries"][-1]["c"]["count"] == 0
    assert report["distribution"]["leaf_summaries"][-1]["scores"]["conditional_mean"] is None
    assert report["distribution"]["leaf_summaries"][-1]["identity"]["seed"] == "18446744073709551611"
    assert report["support_thresholds"]["4"]["coverage"]["sibling_pairs_available"] == 1
    assert report["coverage"]["downstream_discordant_events"] == 2
    assert _accuracy(0.0, 1) == 0.5
    assert np.isclose(_worst_half([0.1, 0.2, 0.3, 0.4]), 0.15)
    assert _worst_half([0.1]) is None
    assert _mean_minus_std([0.1], 0.5) is None
    assert report["risk_summaries"]["1"]["point"]["accuracy"]["conditional_worst_half"]["root_equal_event_accuracy"] is not None
    assert report["risk_summaries"]["1"]["point"]["accuracy"]["conditional_mean_minus_0.5_std"]["root_equal_event_accuracy"] is not None
    assert report["support_thresholds"]["1"]["ranking"]["bootstrap"]["resamples_with_duplicate_source_seed"] > 0
    assert report["support_thresholds"]["1"]["ranking"]["bootstrap"]["unit"] == "source_seed"
    # Root equality: a one-event root and a many-event root have equal weight.
    metrics = pd.DataFrame({
        "seed": ["a", "b"], "event_count": [1, 99], "pair_count": [1, 99],
        "conditional_mean_accuracy": [1.0, 0.0], "blendedEval_accuracy": [0.0, 1.0],
    })
    assert _root_equal(metrics, ("conditional_mean", "blendedEval"))["deltas_vs_blendedEval"][PRIMARY_SCORE] == 0.0
    # A changed CRN seed is rejected rather than silently treated as a new
    # hidden-world sample.
    bad = reference.copy()
    bad.loc[bad.index[1], "combatRolloutSeed"] = "999"
    try:
        analyze(shadow, bad, draws=4)
    except ValueError:
        pass
    else:
        raise AssertionError("CRN identity violation was not rejected")
    print("e3c conditional run-win self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/e3c_conditional_runwin_analysis.json"))
    parser.add_argument("--markdown", type=Path, default=Path("build/e3c_conditional_runwin_analysis.md"))
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP_DRAWS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _run_self_test()
        return
    if args.bootstrap < 1:
        raise SystemExit("--bootstrap must be positive")
    repo = Path(__file__).resolve().parents[1]
    default_shadow, default_reference = _default_paths(repo)
    shadow_path = (args.shadow or default_shadow).resolve()
    reference_path = (args.reference or default_reference).resolve()
    if not shadow_path.exists() or not reference_path.exists():
        raise SystemExit(f"missing input artifact: {shadow_path} / {reference_path}")
    report = analyze(
        _read_csv_preserving_identity(shadow_path),
        _read_csv_preserving_identity(reference_path),
        args.bootstrap,
    )
    report["artifact_provenance"] = _artifact_provenance(shadow_path, reference_path)
    report["reproducibility"] = {
        "command": "python tools/analyze_e3c_conditional_runwin.py --bootstrap 10000",
        "shadow": str(shadow_path),
        "reference": str(reference_path),
        "script_sha256": _sha256(Path(__file__).resolve()),
    }
    report["report_markdown"] = _markdown(report)
    output = (repo / args.output).resolve()
    markdown = (repo / args.markdown).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    serializable = _json_safe({key: value for key, value in report.items() if key != "report_markdown"})
    output.write_text(json.dumps(serializable, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    markdown.write_text(report["report_markdown"], encoding="utf-8")
    print(json.dumps(report["classification"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
