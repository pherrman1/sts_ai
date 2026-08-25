#!/usr/bin/env python3
"""Exploratory E3b paired-discordant-future analysis.

This consumes the frozen E3a M=16 shadow and direct-reference CSVs.  It does
not change the producer, the E3a analyzer, or any gameplay code.  The unit of
the primary statistic is an informative pair/future event, averaged within a
root and then averaged equally over roots.  Source seeds are the outer
bootstrap unit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from analyze_runwin_shadow import (  # frozen source-leaf contract
    LEAF_IDENTITY,
    ROOT_IDENTITY,
    _collapse_source_leaves,
    _validate_shadow,
)


FUTURES = 16
BOOTSTRAP_SEED = 0
SCORES = (
    "runwin_mean",
    "blendedEval",
    "diagnostic_survival_rate",
    "vnetPred",
    "rawRolloutEval",
)
COMPARISONS = (
    ("runwin_mean", "blendedEval"),
    ("runwin_mean", "diagnostic_survival_rate"),
    ("diagnostic_survival_rate", "blendedEval"),
)
STRATA = ("ALL_DISCORDANT", "COMBAT_DRIVEN", "DOWNSTREAM_DISCORDANT")
REFERENCE_REQUIRED = set(
    LEAF_IDENTITY
    + [
        "referenceFutureIdx",
        "combatRolloutSeed",
        "downstreamAgentSeed",
        "combatSurvived",
        "runWon",
        "valid",
        "finalFloor",
        "endHp",
        "healthStatus",
    ]
)


def _finite_mean(values: Iterable[float]) -> float | None:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values)]
    return None if len(values) == 0 else float(values.mean())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_key(value) -> str:
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.floating, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _tuple_key(row, columns):
    return tuple(row[column] for column in columns)


def _identity_set(frame: pd.DataFrame, columns: list[str]) -> set[tuple]:
    return {tuple(row) for row in frame[columns].itertuples(index=False, name=None)}


def _require_no_nulls(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    if frame[columns].isna().any().any():
        bad = [column for column in columns if frame[column].isna().any()]
        raise ValueError(f"{label} identity contains null fields: {bad}")


def _validate_reference(reference: pd.DataFrame) -> None:
    missing = REFERENCE_REQUIRED - set(reference.columns)
    if missing:
        raise ValueError(f"reference missing required columns: {sorted(missing)}")
    _require_no_nulls(reference, LEAF_IDENTITY + ["referenceFutureIdx"], "reference")
    if reference.duplicated(LEAF_IDENTITY + ["referenceFutureIdx"]).any():
        raise ValueError("duplicate direct-reference leaf/future identity")
    indices = reference["referenceFutureIdx"]
    if (~indices.eq(indices.astype(int))).any():
        raise ValueError("referenceFutureIdx must be integral")
    if (~indices.isin(range(FUTURES))).any():
        raise ValueError("referenceFutureIdx outside the required 0..15 range")
    for column in ("combatSurvived", "runWon", "valid"):
        if (~reference[column].isin((0, 1))).any():
            raise ValueError(f"{column} must be exactly 0 or 1")
    if reference["valid"].ne(1).any():
        raise ValueError("invalid reference future encountered; E3b requires all M=16 futures valid")
    if reference.loc[reference.combatSurvived.eq(0), "runWon"].ne(0).any():
        raise ValueError("direct combat loss must be exactly runWon=0")
    if reference.loc[reference.runWon.eq(1), "combatSurvived"].ne(1).any():
        raise ValueError("runWon=1 requires combatSurvived=1")


def _validate_and_collapse_shadow(shadow: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # These are exact public contracts, not merely a subset of fields.
    if list(LEAF_IDENTITY) != [
        "seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits",
        "leafObsHash", "searchSimulation", "particleIndex",
    ]:
        raise AssertionError("frozen LEAF_IDENTITY contract changed")
    if list(ROOT_IDENTITY) != [
        "seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits",
    ]:
        raise AssertionError("frozen ROOT_IDENTITY contract changed")
    _validate_shadow(shadow)
    _require_no_nulls(shadow, LEAF_IDENTITY + ["replicate"], "shadow")
    all_leaves, primary, exclusions = _collapse_source_leaves(shadow.copy())
    if exclusions:
        raise ValueError(f"shadow leaves failed the frozen primary collapse: {exclusions}")
    if len(all_leaves) != len(primary):
        raise ValueError("shadow collapse retained non-primary leaves")
    for _, group in shadow.groupby(LEAF_IDENTITY, dropna=False, sort=False):
        if len(group) != 4 or int(group["replicates"].iloc[0]) != 4:
            raise ValueError("shadow does not satisfy the frozen R=4 contract")
        if set(group.replicate.astype(int)) != {0, 1, 2, 3}:
            raise ValueError("shadow replicate indices are not exactly 0..3")
    for score in ("runwin_mean", "blendedEval", "diagnostic_survival_rate"):
        if (~np.isfinite(primary[score].astype(float))).any():
            raise ValueError(f"shadow score {score} contains a non-finite value")
    for frame in (all_leaves, primary):
        frame["hp_band"] = pd.cut(
            frame.leaf_hpFrac,
            [-np.inf, 0.30, 0.70, np.inf],
            labels=["low", "mid", "high"],
        )
    return all_leaves.reset_index(drop=True), primary.reset_index(drop=True)


def _validate_and_collapse_reference(
    reference: pd.DataFrame, source_leaves: pd.DataFrame
) -> pd.DataFrame:
    _validate_reference(reference)
    source_ids = _identity_set(source_leaves, LEAF_IDENTITY)
    reference_ids = _identity_set(reference, LEAF_IDENTITY)
    missing = source_ids - reference_ids
    extra = reference_ids - source_ids
    if missing:
        raise ValueError(f"missing complete reference group for {len(missing)} source leaves")
    if extra:
        raise ValueError(f"extra reference leaf identity/identities: {len(extra)}")

    rows = []
    for identity, group in reference.groupby(LEAF_IDENTITY, dropna=False, sort=False):
        got = set(group.referenceFutureIdx.astype(int))
        if len(group) != FUTURES or got != set(range(FUTURES)):
            raise ValueError("each reference leaf must contain exactly futures 0..15")
        rows.append(
            {
                **dict(zip(LEAF_IDENTITY, identity)),
                "reference_futures": FUTURES,
            }
        )
    collapsed = pd.DataFrame(rows)
    if len(collapsed) != len(source_leaves):
        raise ValueError("reference collapse did not retain exactly one row per source leaf")

    # The CRN contract is checked at the sibling/future level before the
    # long-form rows are collapsed into eventual-run outcomes.
    for root, root_group in reference.groupby(ROOT_IDENTITY, dropna=False, sort=False):
        for future, future_group in root_group.groupby("referenceFutureIdx", sort=False):
            if future_group["combatRolloutSeed"].nunique(dropna=False) != 1:
                raise ValueError(f"combat CRN violation for root={root}, future={future}")
            if future_group["downstreamAgentSeed"].nunique(dropna=False) != 1:
                raise ValueError(f"downstream CRN violation for root={root}, future={future}")
    return collapsed


def _sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def _accuracy(score_delta: float, outcome_delta: int) -> float:
    if not np.isfinite(score_delta):
        return None
    score_sign = _sign(score_delta)
    outcome_sign = _sign(outcome_delta)
    return 0.5 if score_sign == 0 else float(score_sign == outcome_sign)


def _margin_band(margin: int) -> str:
    magnitude = abs(int(margin))
    if magnitude == 1:
        return "1"
    if magnitude in (2, 3):
        return "2-3"
    if magnitude >= 4:
        return ">=4"
    return "0"


def _make_pairs_and_events(
    leaves: pd.DataFrame, reference: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    ref = reference.set_index(LEAF_IDENTITY + ["referenceFutureIdx"])
    pair_rows: list[dict] = []
    event_rows: list[dict] = []
    pair_id = 0
    root_records = []
    for root, group in leaves.groupby(ROOT_IDENTITY, sort=False, dropna=False):
        group = group.sort_values(LEAF_IDENTITY, kind="stable").reset_index(drop=True)
        root_records.append({**dict(zip(ROOT_IDENTITY, root)), "seed": int(root[0])})
        for left in range(len(group)):
            for right in range(left + 1, len(group)):
                left_leaf = group.iloc[left]
                right_leaf = group.iloc[right]
                record = {
                    **dict(zip(ROOT_IDENTITY, root)),
                    "seed": int(root[0]),
                    "pair_id": pair_id,
                    "leaf_i": left_leaf["leafObsHash"],
                    "leaf_k": right_leaf["leafObsHash"],
                }
                for score in SCORES:
                    record[f"{score}_delta"] = float(left_leaf[score] - right_leaf[score])
                outcomes = []
                for future in range(FUTURES):
                    left_row = ref.loc[tuple(left_leaf[c] for c in LEAF_IDENTITY) + (future,)]
                    right_row = ref.loc[tuple(right_leaf[c] for c in LEAF_IDENTITY) + (future,)]
                    d = int(left_row.runWon) - int(right_row.runWon)
                    outcomes.append(d)
                    event = {
                        **record,
                        "referenceFutureIdx": future,
                        "D": d,
                        "combatSurvived_i": int(left_row.combatSurvived),
                        "combatSurvived_k": int(right_row.combatSurvived),
                        "act": left_leaf["act"],
                        "encounter": left_leaf["encounter"],
                        "hp_band_i": str(left_leaf["hp_band"]),
                        "hp_band_k": str(right_leaf["hp_band"]),
                        "treeDepth_i": left_leaf["treeDepth"],
                        "treeDepth_k": right_leaf["treeDepth"],
                    }
                    if d != 0:
                        event["stratum"] = (
                            "COMBAT_DRIVEN"
                            if left_row.combatSurvived != right_row.combatSurvived
                            else "DOWNSTREAM_DISCORDANT"
                        )
                        for score in SCORES:
                            event[f"{score}_accuracy"] = _accuracy(
                                record[f"{score}_delta"], d
                            )
                        event_rows.append(event)
                n_plus = outcomes.count(1)
                n_minus = outcomes.count(-1)
                pair_rows.append(
                    {
                        **record,
                        "n_plus": n_plus,
                        "n_minus": n_minus,
                        "n_zero": outcomes.count(0),
                        "directional_margin": n_plus - n_minus,
                        "directional_margin_abs": abs(n_plus - n_minus),
                        "directional_margin_band": _margin_band(n_plus - n_minus),
                        "informative_events": n_plus + n_minus,
                    }
                )
                pair_id += 1
    return pd.DataFrame(pair_rows), pd.DataFrame(event_rows), root_records


def _root_metric_frame(
    events: pd.DataFrame, roots: pd.DataFrame, mask: pd.Series
) -> pd.DataFrame:
    selected = events.loc[mask]
    rows = []
    for root, root_group in roots.groupby(ROOT_IDENTITY, sort=False, dropna=False):
        matching = selected
        for column, value in zip(ROOT_IDENTITY, root):
            matching = matching[matching[column].eq(value)]
        item = {**dict(zip(ROOT_IDENTITY, root)), "seed": int(root[0])}
        item["event_count"] = int(len(matching))
        item["pair_count"] = int(matching.pair_id.nunique()) if len(matching) else 0
        for score in SCORES:
            item[f"{score}_accuracy"] = (
                float(matching[f"{score}_accuracy"].mean()) if len(matching) else None
            )
        rows.append(item)
    return pd.DataFrame(rows)


def _root_equal(root_metrics: pd.DataFrame) -> dict:
    informative = root_metrics[root_metrics.event_count > 0]
    result = {
        "roots_total": int(len(root_metrics)),
        "roots_with_informative_events": int(len(informative)),
        "roots_with_zero_informative_events": int((root_metrics.event_count == 0).sum()),
        "informative_events": int(root_metrics.event_count.sum()),
        "informative_pairs": int(informative.pair_count.sum()),
        "accuracy": {},
    }
    for score in SCORES:
        values = informative[f"{score}_accuracy"].dropna()
        result["accuracy"][score] = {
            "roots": int(len(values)),
            "root_equal_event_accuracy": _finite_mean(values),
        }
    result["deltas"] = _root_equal_deltas(root_metrics)
    return result


def _root_equal_deltas(root_metrics: pd.DataFrame) -> dict:
    informative = root_metrics[root_metrics.event_count > 0]
    result = {}
    for treatment, baseline in COMPARISONS:
        values = (
            informative[f"{treatment}_accuracy"]
            - informative[f"{baseline}_accuracy"]
        )
        result[f"{treatment}_minus_{baseline}"] = _finite_mean(values)
    return result


def _root_metrics_by_stratum(
    events: pd.DataFrame, roots: pd.DataFrame, extra_masks: dict[str, pd.Series] | None = None
) -> dict[str, tuple[pd.DataFrame, dict]]:
    masks = {"ALL_DISCORDANT": events.D.ne(0)}
    masks.update(extra_masks or {})
    result = {}
    for name in STRATA:
        metrics = _root_metric_frame(events, roots, masks[name])
        result[name] = (metrics, _root_equal(metrics))
    return result


def _seed_rows(root_metrics: pd.DataFrame) -> dict[str, dict]:
    result = {}
    for seed, group in root_metrics.groupby("seed", sort=True, dropna=False):
        result[_json_key(seed)] = _root_equal(group.reset_index(drop=True))
    return result


def _bootstrap(
    root_metrics_by_stratum: dict[str, pd.DataFrame],
    seeds: list[int],
    draws: int,
) -> dict:
    if draws < 1:
        raise ValueError("bootstrap draws must be positive")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    output = {
        "unit": "source_seed",
        "rng_seed": BOOTSTRAP_SEED,
        "draws": int(draws),
        "root_weighting": "equal root after source-seed resampling",
        "source_seeds": len(seeds),
        "resamples_with_duplicate_source_seed": 0,
        "strata": {},
    }
    chosen_samples = []
    for _ in range(draws):
        chosen = rng.choice(np.asarray(seeds), len(seeds), replace=True)
        chosen_samples.append(chosen)
        output["resamples_with_duplicate_source_seed"] += int(
            len(set(chosen.tolist())) < len(chosen)
        )
    for stratum in STRATA:
        metrics = root_metrics_by_stratum[stratum]
        point = _root_equal(metrics)["deltas"]
        samples = {key: [] for key in point}
        # Precompute the root-level deltas once.  Resampling then only
        # concatenates tiny NumPy arrays, preserving the exact hierarchy while
        # avoiding 30,000 repeated pandas filters/concatenations.
        per_seed_deltas = {comparison: [] for comparison in point}
        for seed in seeds:
            seed_metrics = metrics[metrics.seed.eq(seed) & metrics.event_count.gt(0)]
            for comparison in point:
                treatment, baseline = comparison.split("_minus_", 1)
                per_seed_deltas[comparison].append(
                    (seed_metrics[f"{treatment}_accuracy"] - seed_metrics[f"{baseline}_accuracy"])
                    .to_numpy(dtype=float)
                )
        for chosen in chosen_samples:
            for comparison in samples:
                selected = [per_seed_deltas[comparison][seeds.index(int(seed))] for seed in chosen]
                values = np.concatenate(selected) if selected else np.asarray([], dtype=float)
                samples[comparison].append(_finite_mean(values))
        output["strata"][stratum] = {"point": point, "deltas": {}}
        for comparison, values in samples.items():
            finite = np.asarray([value for value in values if value is not None], dtype=float)
            output["strata"][stratum]["deltas"][comparison] = {
                "estimate": point[comparison],
                "bootstrap_mean": _finite_mean(finite),
                "ci95": (
                    None
                    if len(finite) == 0
                    else [float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))]
                ),
                "finite_resamples": int(len(finite)),
            }
    return output


def _leave_one_out(
    root_metrics_by_stratum: dict[str, pd.DataFrame], seeds: list[int]
) -> dict:
    result = {"unit": "source_seed", "strata": {}}
    for stratum in STRATA:
        metrics = root_metrics_by_stratum[stratum]
        rows = {}
        for seed in seeds:
            rows[_json_key(seed)] = _root_equal(metrics[metrics.seed.ne(seed)].reset_index(drop=True))["deltas"]
        summary = {}
        for comparison in (f"{a}_minus_{b}" for a, b in COMPARISONS):
            values = [row[comparison] for row in rows.values() if row[comparison] is not None]
            summary[comparison] = {
                "min": None if not values else float(min(values)),
                "max": None if not values else float(max(values)),
                "range": None if not values else float(max(values) - min(values)),
                "finite_estimates": len(values),
            }
        result["strata"][stratum] = {"per_omitted_seed": rows, "range": summary}
    return result


def _counts_by(frame: pd.DataFrame, columns: list[str]) -> dict:
    if frame.empty:
        return {}
    grouped = frame.groupby(columns, dropna=False, sort=True).size()
    result = {}
    for key, value in grouped.items():
        if not isinstance(key, tuple):
            key = (key,)
        label = "|".join(f"{column}={_json_key(part)}" for column, part in zip(columns, key))
        result[label] = int(value)
    return result


def _event_coverage(events: pd.DataFrame) -> dict:
    # HP band and depth are leaf properties, so these are two-sided leaf-event
    # incidences (each informative sibling event contributes one incidence per
    # sibling). Act and encounter are also reported at the event level.
    incidences = []
    for _, event in events.iterrows():
        for side in ("i", "k"):
            incidences.append(
                {
                    "act": event.act,
                    "encounter": event.encounter,
                    "hp_band": event[f"hp_band_{side}"],
                    "treeDepth": event[f"treeDepth_{side}"],
                }
            )
    incidence_frame = pd.DataFrame(incidences)
    return {
        "event_unit": "informative pair/future event",
        "leaf_metadata_unit": "two-sided informative event incidence",
        "by_source_seed": _counts_by(events, ["seed"]),
        "by_act": _counts_by(events, ["act"]),
        "by_encounter": _counts_by(events, ["encounter"]),
        "by_hp_band": _counts_by(incidence_frame, ["hp_band"]),
        "by_tree_depth": _counts_by(incidence_frame, ["treeDepth"]),
    }


def _pair_secondary(pairs: pd.DataFrame, events: pd.DataFrame) -> dict:
    result = {
        "total_pairs": int(len(pairs)),
        "margin_distribution": {
            _json_key(key): int(value)
            for key, value in pairs.directional_margin_band.value_counts(sort=False).items()
        },
        "directional_margin_zero_pairs": int(pairs.directional_margin.eq(0).sum()),
        "by_score": {},
        "event_accuracy_by_directional_margin": {},
    }
    ordered = pairs[pairs.directional_margin.ne(0)]
    for score in SCORES:
        score_ordered = ordered[np.isfinite(ordered[f"{score}_delta"].astype(float))]
        agreements = [
            _sign(row[f"{score}_delta"]) == _sign(row.directional_margin)
            for _, row in score_ordered.iterrows()
        ]
        result["by_score"][score] = {
            "ordered_pairs": int(len(score_ordered)),
            "unordered_margin_zero_pairs_excluded": int(len(pairs) - len(ordered)),
            "nonfinite_score_pairs_excluded": int(len(ordered) - len(score_ordered)),
            "strict_sign_agreements": int(sum(agreements)),
            "strict_sign_agreement_fraction": _finite_mean(agreements),
            "score_ties_among_ordered_pairs": int(
                score_ordered[f"{score}_delta"].eq(0).sum()
            ),
        }
    for band in ("1", "2-3", ">=4"):
        selected = pairs[pairs.directional_margin_band.eq(band)]
        event_mask = events.pair_id.isin(selected.pair_id)
        result["event_accuracy_by_directional_margin"][band] = {
            "pairs": int(len(selected)),
            "informative_events": int(event_mask.sum()),
            "root_equal": _root_equal(
                _root_metric_frame(
                    events,
                    events[ROOT_IDENTITY].drop_duplicates().assign(_dummy=1),
                    event_mask,
                )
            )
            if len(selected)
            else None,
        }
    return result


def _margin_analysis(pairs: pd.DataFrame, events: pd.DataFrame) -> dict:
    result = {}
    for score in SCORES:
        valid_pairs = pairs[np.isfinite(pairs[f"{score}_delta"].astype(float))].copy()
        separation = valid_pairs[f"{score}_delta"].abs().to_numpy(float)
        if not len(valid_pairs):
            result[score] = {"quartile_edges": None, "bins": {}}
            continue
        edges = np.quantile(separation, [0, 0.25, 0.5, 0.75, 1]).tolist()
        labels = np.searchsorted(np.asarray(edges[1:-1]), separation, side="right") + 1
        pair_quartiles = valid_pairs[["pair_id"]].copy()
        pair_quartiles["quartile"] = labels
        joined = events.merge(pair_quartiles, on="pair_id", how="inner", validate="many_to_one")
        bins = {}
        for quartile in range(1, 5):
            selected = joined[joined.quartile.eq(quartile)]
            accuracy = selected[f"{score}_accuracy"]
            by_root = selected.groupby(ROOT_IDENTITY, sort=False, dropna=False).agg(
                event_count=("pair_id", "size"), accuracy=(f"{score}_accuracy", "mean")
            )
            bins[f"Q{quartile}"] = {
                "score_separation_min": float(min(edges[quartile - 1], edges[quartile])),
                "score_separation_max": float(max(edges[quartile - 1], edges[quartile])),
                "pairs": int(selected.pair_id.nunique()),
                "informative_events": int(len(selected)),
                "roots": int(len(by_root)),
                "root_equal_event_accuracy": _finite_mean(by_root.accuracy),
                "pooled_event_accuracy": _finite_mean(accuracy),
            }
        result[score] = {"quartile_edges": [float(value) for value in edges], "bins": bins}
    return result


def _root_identity_records(roots: pd.DataFrame, root_metrics: pd.DataFrame) -> list[dict]:
    zero = root_metrics[root_metrics.event_count.eq(0)]
    result = []
    for _, row in zero.iterrows():
        result.append({column: int(row[column]) if column != "rootObsHash" else int(row[column]) for column in ROOT_IDENTITY})
    return result


def _classify(bootstrap_report: dict, loo: dict) -> tuple[str, str]:
    def estimate(stratum, comparison):
        return bootstrap_report["strata"][stratum]["deltas"][comparison]["estimate"]

    def lower(stratum, comparison):
        ci = bootstrap_report["strata"][stratum]["deltas"][comparison]["ci95"]
        return None if ci is None else ci[0]

    rb = "runwin_mean_minus_blendedEval"
    rs = "runwin_mean_minus_diagnostic_survival_rate"
    strong = (
        estimate("DOWNSTREAM_DISCORDANT", rb) is not None
        and estimate("DOWNSTREAM_DISCORDANT", rs) is not None
        and estimate("DOWNSTREAM_DISCORDANT", rb) > 0
        and estimate("DOWNSTREAM_DISCORDANT", rs) > 0
        and lower("DOWNSTREAM_DISCORDANT", rb) > 0
        and lower("DOWNSTREAM_DISCORDANT", rs) > 0
        and all(
            value is not None and value > 0
            for value in loo["strata"]["DOWNSTREAM_DISCORDANT"]["per_omitted_seed"].values()
            for value in [value[rb], value[rs]]
        )
    )
    survival_only = (
        estimate("ALL_DISCORDANT", rb) is not None
        and estimate("COMBAT_DRIVEN", rb) is not None
        and estimate("ALL_DISCORDANT", rb) > 0
        and estimate("COMBAT_DRIVEN", rb) > 0
        and not strong
        and (
            estimate("DOWNSTREAM_DISCORDANT", rs) is None
            or estimate("DOWNSTREAM_DISCORDANT", rs) <= 0
            or lower("DOWNSTREAM_DISCORDANT", rs) <= 0
        )
    )
    all_rb = estimate("ALL_DISCORDANT", rb)
    if strong:
        return "E3B_STRONG_SIGNAL", "Both downstream treatment deltas are positive with bootstrap lower bounds above zero and remain positive under every leave-one-source-seed-out estimate."
    if survival_only:
        return "E3B_SURVIVAL_ONLY", "runwin_mean is positive versus blendedEval overall and in combat-driven discordance, but there is no downstream advantage over the survival ablation."
    if all_rb is not None and all_rb <= 0:
        return "E3B_NO_SIGNAL", "runwin_mean does not outperform blendedEval in the root-equal informative-event estimate."
    return "E3B_INCONCLUSIVE", "The observed direction does not satisfy the strong, survival-only, or no-signal rules without adding a post-hoc effect threshold."


def _markdown(report: dict) -> str:
    fmt = lambda value: "—" if value is None else f"{value:.6f}"
    cov = report["coverage"]
    ranking = report["ranking"]
    lines = [
        "# E3b paired-discordant-future analysis",
        "",
        "Exploratory analysis of the published frozen E3a M=16 artifacts. This is not a replacement for E3a, does not reinterpret its failed reference gate, and makes no gameplay-promotion claim.",
        "",
        "## Result",
        "",
        f"**Classification: `{report['classification']['label']}`.** {report['classification']['reason']}",
        "",
        "The estimand is the accuracy of a static leaf score in predicting the winning sibling on a paired realized-world continuation, conditional on the two leaves producing different eventual outcomes. It is not a test of which score estimates information-set expected run value: `V_direct` holds the copied latent GameContext future fixed, while E2c, blendedEval, and VNet do not observe that exact downstream future.",
        "",
        "## Frozen input and coverage",
        "",
        f"- Source seeds: **{cov['source_seeds']}**; roots: **{cov['roots']}**; roots with at least one informative event: **{cov['roots_with_informative_events']}**; zero-informative roots: **{cov['roots_with_zero_informative_events']}**.",
        f"- Sibling pairs: **{cov['total_sibling_pairs']}**; pair/future events: **{cov['total_pair_future_events']}**; informative events (`D != 0`): **{cov['informative_events']}**.",
        f"- Combat-driven discordance: **{cov['combat_driven_events']}**; downstream discordance: **{cov['downstream_discordant_events']}**.",
        f"- Complete valid M=16 reference coverage: **{cov['complete_reference_leaves']} leaves / {cov['reference_future_rows']} rows**; invalid rows rejected: **{cov['invalid_reference_future_rows']}**.",
        "",
        "Roots with zero informative events:",
        "",
    ]
    if report["zero_informative_roots"]:
        lines.extend(f"- `{item}`" for item in report["zero_informative_roots"])
    else:
        lines.append("- None")
    lines.extend(["", "## Root-equal event accuracy", "", "Each score is evaluated on events within each root, then roots with events in that stratum receive equal weight. Pair/future events are not treated as independent bootstrap units.", ""])
    lines.append("| Stratum | Events | Roots | runwin_mean | blendedEval | survival | vnetPred | rawRolloutEval | runwin−blended | runwin−survival |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in STRATA:
        item = ranking[name]
        acc = item["accuracy"]
        score_fmt = lambda score: "—" if acc[score]["root_equal_event_accuracy"] is None else f"{acc[score]['root_equal_event_accuracy']:.6f}"
        lines.append(f"| {name} | {item['informative_events']} | {item['roots_with_informative_events']} | {score_fmt('runwin_mean')} | {score_fmt('blendedEval')} | {score_fmt('diagnostic_survival_rate')} | {score_fmt('vnetPred')} | {score_fmt('rawRolloutEval')} | {item['deltas']['runwin_mean_minus_blendedEval']:.6f} | {item['deltas']['runwin_mean_minus_diagnostic_survival_rate']:.6f} |")
    lines.extend(["", "The primary statistic is the `ALL_DISCORDANT` `runwin_mean - blendedEval` delta. The downstream row is the key mechanism check.", "", "## Source-seed bootstrap", "", f"Deterministic percentile bootstrap: **{report['seed_bootstrap']['draws']}** resamples, RNG seed **{report['seed_bootstrap']['rng_seed']}**, source seed as the outer unit, equal roots after resampling.", ""])
    lines.append("| Stratum | Comparison | Point estimate | Bootstrap mean | 95% percentile CI |")
    lines.append("|---|---|---:|---:|---:|")
    for name in STRATA:
        for comparison, value in report["seed_bootstrap"]["strata"][name]["deltas"].items():
            ci = value["ci95"]
            ci_text = "—" if ci is None else f"[{ci[0]:.6f}, {ci[1]:.6f}]"
            lines.append(f"| {name} | {comparison} | {value['estimate']:.6f} | {value['bootstrap_mean']:.6f} | {ci_text} |")
    lines.extend(["", "## Per-source-seed deltas", "", "The rows below are root-equal within each source seed; a null means the omitted/selected seed has no informative root in that stratum.", ""])
    lines.append("| Seed | ALL runwin−blend | ALL runwin−survival | Combat runwin−blend | Downstream runwin−blend | Downstream runwin−survival |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    for seed, rows in report["per_seed_deltas"].items():
        vals = []
        for stratum, comparison in (("ALL_DISCORDANT", "runwin_mean_minus_blendedEval"), ("ALL_DISCORDANT", "runwin_mean_minus_diagnostic_survival_rate"), ("COMBAT_DRIVEN", "runwin_mean_minus_blendedEval"), ("DOWNSTREAM_DISCORDANT", "runwin_mean_minus_blendedEval"), ("DOWNSTREAM_DISCORDANT", "runwin_mean_minus_diagnostic_survival_rate")):
            value = rows[stratum][comparison]
            vals.append("—" if value is None else f"{value:.6f}")
        lines.append(f"| {seed} | " + " | ".join(vals) + " |")
    lines.extend(["", "## Leave-one-source-seed-out sensitivity", "", "| Stratum | Comparison | Min | Max | Range |", "|---|---|---:|---:|---:|"])
    for name in STRATA:
        for comparison, value in report["leave_one_source_seed_out"]["strata"][name]["range"].items():
            lines.append(f"| {name} | {comparison} | {value['min']:.6f} | {value['max']:.6f} | {value['range']:.6f} |")
    lines.extend(["", "## Pair-level secondary analysis", "", f"There are {report['pair_secondary']['directional_margin_zero_pairs']} pairs with directional margin zero; these are reported as unordered and excluded from strict sign agreement.", ""])
    lines.append("| Score | Ordered pairs | Strict sign agreement | Score ties among ordered |")
    lines.append("|---|---:|---:|---:|")
    for score, item in report["pair_secondary"]["by_score"].items():
        lines.append(f"| {score} | {item['ordered_pairs']} | {item['strict_sign_agreement_fraction']:.6f} | {item['score_ties_among_ordered_pairs']} |")
    lines.extend(["", "Event accuracy by directional-margin magnitude:", "", "| Margin | Pairs | Events | runwin_mean | blendedEval | survival |", "|---|---:|---:|---:|---:|---:|"])
    for band, item in report["pair_secondary"]["event_accuracy_by_directional_margin"].items():
        if item is None:
            continue
        acc = item["root_equal"]["accuracy"]
        lines.append(f"| {band} | {item['pairs']} | {item['informative_events']} | {acc['runwin_mean']['root_equal_event_accuracy']:.6f} | {acc['blendedEval']['root_equal_event_accuracy']:.6f} | {acc['diagnostic_survival_rate']['root_equal_event_accuracy']:.6f} |")
    lines.extend(["", "## Score-separation margin analysis", "", "Quartiles are defined separately for each score using absolute sibling score separation across all complete sibling pairs. Accuracy is then computed only on informative events and aggregated equally over roots.", ""])
    for score, item in report["margin_analysis"].items():
        lines.append(f"### `{score}`")
        lines.append("")
        lines.append("| Quartile | Separation range | Pairs | Events | Root-equal accuracy | Pooled accuracy |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for quartile, bin_item in item["bins"].items():
            lines.append(f"| {quartile} | [{bin_item['score_separation_min']:.6g}, {bin_item['score_separation_max']:.6g}] | {bin_item['pairs']} | {bin_item['informative_events']} | {fmt(bin_item['root_equal_event_accuracy'])} | {fmt(bin_item['pooled_event_accuracy'])} |")
        lines.append("")
    lines.extend(["## Decision boundary", "", "This is post-hoc exploratory evidence. It cannot authorize gameplay integration, change E3a thresholds, or reinterpret E3a GO/STOP. No deployment threshold was tuned. A strong signal would motivate a new preregistered confirmatory experiment on unused source seeds; survival-only would not promote E2c; no-signal would stop this leaf-ranking line absent an independent target.", "", "## Reproducibility", "", f"```text\n{report['reproducibility']['command']}\n```", "", "Input hashes and contract checks are recorded in the JSON artifact.", ""])
    return "\n".join(lines)


def analyze(shadow: pd.DataFrame, reference: pd.DataFrame, bootstrap: int = 10000) -> dict:
    all_leaves, primary = _validate_and_collapse_shadow(shadow)
    _validate_and_collapse_reference(reference, primary)
    direct = reference.copy()
    pair_table, events, root_records = _make_pairs_and_events(primary, direct)
    roots = pd.DataFrame(root_records).drop_duplicates(ROOT_IDENTITY).reset_index(drop=True)
    roots = roots.sort_values(ROOT_IDENTITY, kind="stable").reset_index(drop=True)
    if pair_table.empty:
        raise ValueError("no sibling pairs found")
    root_keys = set(_identity_set(roots, ROOT_IDENTITY))
    if set(_identity_set(pair_table, ROOT_IDENTITY)) != root_keys:
        raise ValueError("pair roots do not match source roots")

    combat_mask = events.D.ne(0) & (
        events.combatSurvived_i.ne(events.combatSurvived_k)
    )
    downstream_mask = events.D.ne(0) & events.combatSurvived_i.eq(1) & events.combatSurvived_k.eq(1)
    strata_metrics = _root_metrics_by_stratum(
        events,
        roots,
        {"COMBAT_DRIVEN": combat_mask, "DOWNSTREAM_DISCORDANT": downstream_mask},
    )
    root_metrics = {name: value[0] for name, value in strata_metrics.items()}
    ranking = {name: value[1] for name, value in strata_metrics.items()}
    seeds = sorted(int(seed) for seed in primary.seed.unique())
    per_seed = {
        seed: {name: _root_equal(root_metrics[name][root_metrics[name].seed.eq(seed)].reset_index(drop=True))["deltas"] for name in STRATA}
        for seed in seeds
    }
    per_seed = {_json_key(seed): value for seed, value in per_seed.items()}
    loo = _leave_one_out(root_metrics, seeds)
    bootstrap_report = _bootstrap(root_metrics, seeds, bootstrap)

    informative = events[events.D.ne(0)]
    all_pair_events = len(pair_table) * FUTURES
    zero_roots = _root_identity_records(roots, root_metrics["ALL_DISCORDANT"])
    source_leaf_coverage = {
        "leaves_by_act": {_json_key(k): int(v) for k, v in primary.act.value_counts().sort_index().items()},
        "leaves_by_encounter": {_json_key(k): int(v) for k, v in primary.encounter.value_counts().sort_index().items()},
        "leaves_by_hp_band": {_json_key(k): int(v) for k, v in primary.hp_band.value_counts().sort_index().items()},
        "leaves_by_tree_depth": {_json_key(k): int(v) for k, v in primary.treeDepth.value_counts().sort_index().items()},
    }
    report = {
        "analysis": {
            "name": "E3b paired-discordant-future analysis",
            "status": "exploratory",
            "version": 1,
            "futures": FUTURES,
            "scores": SCORES,
            "primary_treatment": "runwin_mean",
            "primary_baseline": "blendedEval",
            "mechanism_ablation": "diagnostic_survival_rate",
            "event_definition": "D = runWon_i - runWon_k; informative iff D != 0",
            "root_aggregation": "mean event accuracy within root, then equal mean over roots with informative events in the stratum",
            "bootstrap": "source seed outer unit; root equal after source-seed resampling",
            "bootstrap_rng_seed": BOOTSTRAP_SEED,
        },
        "target_mismatch_caveat": {
            "same_world_conditional": "V_direct holds the copied latent GameContext future fixed across sibling leaves and M futures.",
            "estimand": "static-score prediction of the winner of a paired realized-world continuation conditional on different eventual outcomes",
            "not_estimand": "perfect estimation of information-set expected run value",
            "unobserved_by_static_scores": "the exact latent downstream future is not observed by E2c, blendedEval, or VNet",
        },
        "coverage": {
            "source_seeds": int(primary.seed.nunique()),
            "roots": int(len(roots)),
            "roots_with_informative_events": int((root_metrics["ALL_DISCORDANT"].event_count > 0).sum()),
            "roots_with_zero_informative_events": int((root_metrics["ALL_DISCORDANT"].event_count == 0).sum()),
            "total_sibling_pairs": int(len(pair_table)),
            "total_pair_future_events": int(all_pair_events),
            "informative_events": int(len(informative)),
            "combat_driven_events": int(combat_mask.sum()),
            "downstream_discordant_events": int(downstream_mask.sum()),
            "reference_future_rows": int(len(reference)),
            "complete_reference_leaves": int(len(reference) // FUTURES),
            "invalid_reference_future_rows": 0,
            "source_leaf_coverage": source_leaf_coverage,
            "event_coverage": _event_coverage(informative),
            "events_by_source_seed": _counts_by(informative, ["seed"]),
            "events_by_act": _counts_by(informative, ["act"]),
            "events_by_encounter": _counts_by(informative, ["encounter"]),
        },
        "zero_informative_roots": zero_roots,
        "ranking": ranking,
        "per_seed_deltas": per_seed,
        "seed_bootstrap": bootstrap_report,
        "leave_one_source_seed_out": loo,
        "pair_secondary": _pair_secondary(pair_table, informative),
        "margin_analysis": _margin_analysis(pair_table, informative),
        "contracts": {
            "leaf_identity": LEAF_IDENTITY,
            "root_identity": ROOT_IDENTITY,
            "reference_identity": LEAF_IDENTITY + ["referenceFutureIdx"],
            "shadow_replicates": 4,
            "reference_futures": FUTURES,
            "reference_invalid_rows_rejected": True,
            "sibling_crn_seed_equality_verified": True,
        },
    }
    label, reason = _classify(bootstrap_report, loo)
    report["classification"] = {
        "label": label,
        "reason": reason,
        "no_posthoc_effect_threshold": True,
        "gameplay_promotion_authorized": False,
    }
    return report


def _default_paths(repo: Path) -> tuple[Path, Path]:
    base = repo / "build" / "e3a_designated_a93b3c6_m16_artifacts" / "sts_sweep" / "build"
    return base / "e3a_designated_a93b3c6_m16.csv", base / "e3a_designated_a93b3c6_m16.csv.reference.csv"


def _artifact_provenance(repo: Path, shadow_path: Path, reference_path: Path) -> dict:
    bundle = repo / "build" / "e3a_designated_a93b3c6_m16_artifacts" / "e3a_designated_a93b3c6_m16_artifacts.tar.gz"
    analysis = repo / "build" / "e3a_designated_a93b3c6_m16_artifacts" / "e3a_designated_a93b3c6_m16.analysis.json"
    files = {"shadow_csv": shadow_path, "reference_csv": reference_path}
    for label, path in (("published_bundle_tar_gz", bundle), ("published_frozen_analysis_json", analysis)):
        if path.exists():
            files[label] = path
    return {
        label: {"path": str(path), "sha256": _sha256(path), "size": path.stat().st_size}
        for label, path in files.items()
    }


def _read_csv_preserving_identity(path: Path) -> pd.DataFrame:
    # Several identity fields are uint64 hashes.  Letting pandas infer a
    # mixed shadow column as float silently rounds hashes above 2**53 and
    # makes an otherwise valid shadow/reference join appear empty.
    return pd.read_csv(path, dtype={column: "string" for column in LEAF_IDENTITY})


def _run_self_test() -> None:
    rows = []
    # Three roots: root A has downstream and combat discordance; root B has
    # more events and reverses the treatment; root C has no informative event.
    specs = [
        (1, 0, [([1, 1, 1, 1], [1, 1, 1, 1]), ([0, 0, 0, 0], [1, 1, 1, 1]), ([0, 0, 0, 0], [0, 0, 0, 0])]),
        (1, 1, [([1, 1, 1, 1], [1, 1, 1, 1]), ([0, 0, 0, 0], [0, 0, 0, 0]), ([0, 0, 0, 0], [0, 0, 0, 0]), ([0, 0, 0, 0], [0, 0, 0, 0])]),
        (2, 0, [([0, 0, 0, 0], [1, 1, 1, 1]), ([0, 0, 0, 0], [1, 1, 1, 1]), ([0, 0, 0, 0], [1, 1, 1, 1])]),
    ]
    for seed, dec, leaf_specs in specs:
        for leaf, (wins, survives) in enumerate(leaf_specs):
            q = {0: 3.0, 1: 2.0, 2: 1.0, 3: 0.0}[leaf]
            diagnostic_survives = [1, 1, 1, 1]
            probabilities = np.asarray([q / 3.0 for _ in range(4)])
            values = [dict(seed=seed, fightIdx=0, decIdx=dec, rootObsHash=100 + dec,
                           rootActionBits=7, leafObsHash=10 + leaf, searchSimulation=20 + leaf,
                           particleIndex=0, replicate=r, floor=1, act=1, room=0, encounter=1,
                           treeDepth=leaf + 1, leaf_curHp=30 + leaf, leaf_maxHp=100,
                           leaf_hpFrac=.3 + .01 * leaf, particleWeight=1., particleExact=1,
                           particleFallback=0, rootCarried=0, reuseGeneration=0, reuseSearchCount=0,
                           rolloutSteps=4, vnetPred=-q, rawRolloutEval=q,
                           blendedEval=-q, runwin_probability=float(probabilities[r]), terminal=1,
                           survived=diagnostic_survives[r], projectionFailure=0, inferenceFailure=0,
                           replicates=4, survivedCount=sum(diagnostic_survives),
                           diagnostic_survival_rate=float(np.mean(diagnostic_survives)),
                           conditional_survival_critic_mean=q / 3. if sum(diagnostic_survives) else float("nan"),
                           runwin_mean=float(probabilities.mean()),
                           runwin_std=float(probabilities.std(ddof=0)),
                           runwin_min=float(probabilities.min()), runwin_max=float(probabilities.max())) for r in range(4)]
            rows.extend(values)
    shadow = pd.DataFrame(rows)
    ref_rows = []
    for _, leaf in shadow.drop_duplicates(LEAF_IDENTITY).iterrows():
        seed, dec, leaf_no = int(leaf.seed), int(leaf.decIdx), int(leaf.leafObsHash - 10)
        spec = next(item for item in specs if item[0] == seed and item[1] == dec)[2][leaf_no]
        for future in range(4):
            ref_rows.append({**{key: leaf[key] for key in LEAF_IDENTITY}, "referenceFutureIdx": future,
                             "combatRolloutSeed": 1000 + future, "downstreamAgentSeed": 2000 + future,
                             "combatSurvived": spec[1][future], "runWon": spec[0][future], "valid": 1,
                             "finalFloor": 1, "endHp": 10, "healthStatus": "ok"})
        for future in range(4, FUTURES):
            ref_rows.append({**{key: leaf[key] for key in LEAF_IDENTITY}, "referenceFutureIdx": future,
                             "combatRolloutSeed": 1000 + future, "downstreamAgentSeed": 2000 + future,
                             "combatSurvived": spec[1][future % 4], "runWon": spec[0][future % 4], "valid": 1,
                             "finalFloor": 1, "endHp": 10, "healthStatus": "ok"})
    reference = pd.DataFrame(ref_rows)
    # The treatment is a known perfect ordering for the two informative roots;
    # the baseline is its strict reversal.  A separate score-tie check below
    # exercises the required 0.5 convention.
    report = analyze(shadow, reference, bootstrap=64)
    assert report["coverage"]["total_sibling_pairs"] == 12
    assert report["coverage"]["total_pair_future_events"] == 192
    assert report["coverage"]["roots_with_zero_informative_events"] == 1
    assert report["coverage"]["informative_events"] > 0
    assert report["ranking"]["ALL_DISCORDANT"]["accuracy"]["runwin_mean"]["root_equal_event_accuracy"] == 1.0
    assert report["ranking"]["ALL_DISCORDANT"]["accuracy"]["blendedEval"]["root_equal_event_accuracy"] == 0.0
    assert report["ranking"]["DOWNSTREAM_DISCORDANT"]["informative_events"] > 0
    assert report["ranking"]["COMBAT_DRIVEN"]["informative_events"] > 0
    assert report["pair_secondary"]["directional_margin_zero_pairs"] > 0
    assert report["seed_bootstrap"]["resamples_with_duplicate_source_seed"] > 0
    assert report["seed_bootstrap"]["unit"] == "source_seed"
    assert _accuracy(0.0, 1) == 0.5
    equal_root = pd.DataFrame(
        {
            "seed": [1, 2],
            "event_count": [1, 99],
            "pair_count": [1, 99],
            **{f"{score}_accuracy": [1.0, 0.0] for score in ("runwin_mean", "diagnostic_survival_rate", "vnetPred", "rawRolloutEval")},
            **{f"{score}_accuracy": [0.0, 1.0] for score in ("blendedEval",)},
        }
    )
    equal_root["runwin_mean_accuracy"] = [1.0, 0.0]
    equal_root["blendedEval_accuracy"] = [0.0, 1.0]
    for column in ROOT_IDENTITY:
        equal_root[column] = [1, 2]
    equal_summary = _root_equal(equal_root)
    assert equal_summary["accuracy"]["runwin_mean"]["root_equal_event_accuracy"] == 0.5
    assert equal_summary["accuracy"]["blendedEval"]["root_equal_event_accuracy"] == 0.5
    # Missing/duplicate futures, invalid futures, and CRN violations are hard
    # errors rather than partial-data exclusions.
    for bad_reference, message in [
        (reference.iloc[:-1], "missing future"),
        (pd.concat([reference, reference.iloc[[0]]]), "duplicate future"),
        (reference.assign(valid=lambda frame: frame.valid.mask(frame.index == 0, 0)), "invalid future"),
        (reference.assign(combatRolloutSeed=lambda frame: frame.combatRolloutSeed.mask(frame.index == 1, 9999)), "CRN violation"),
    ]:
        try:
            analyze(shadow, bad_reference, bootstrap=4)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{message} was not rejected")
    # A root with one pair's event count cannot dominate a root with many
    # events: root aggregation is deliberately not pooled-event aggregation.
    assert report["ranking"]["ALL_DISCORDANT"]["roots_with_informative_events"] == 2
    print("e3b paired discordance self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shadow", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/e3b_paired_discordance_analysis.json"))
    parser.add_argument("--markdown", type=Path, default=Path("build/e3b_paired_discordance_analysis.md"))
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _run_self_test()
        return
    repo = Path(__file__).resolve().parents[1]
    default_shadow, default_reference = _default_paths(repo)
    shadow_path = (args.shadow or default_shadow).resolve()
    reference_path = (args.reference or default_reference).resolve()
    if not shadow_path.exists() or not reference_path.exists():
        raise SystemExit(f"missing input artifact: {shadow_path} / {reference_path}")
    if args.bootstrap < 1:
        raise SystemExit("--bootstrap must be positive")
    report = analyze(
        _read_csv_preserving_identity(shadow_path),
        _read_csv_preserving_identity(reference_path),
        args.bootstrap,
    )
    report["artifact_provenance"] = _artifact_provenance(repo, shadow_path, reference_path)
    report["reproducibility"] = {
        "command": "python tools/analyze_e3b_paired_discordance.py --bootstrap 10000",
        "shadow": str(shadow_path),
        "reference": str(reference_path),
        "script_sha256": _sha256(Path(__file__).resolve()),
    }
    report["report_markdown"] = _markdown(report)
    output = (repo / args.output).resolve()
    markdown = (repo / args.markdown).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    serializable = {key: value for key, value in report.items() if key != "report_markdown"}
    output.write_text(json.dumps(serializable, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    markdown.write_text(report["report_markdown"], encoding="utf-8")
    print(json.dumps(report["classification"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
