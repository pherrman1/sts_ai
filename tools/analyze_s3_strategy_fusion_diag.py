#!/usr/bin/env python3
"""Analyze Searcher3 strategy-fusion diagnostic CSV output.

The unit of bootstrap resampling is the source seed.  Bucket rows and
transitions within a source seed are first reduced with their sampled bucket
probabilities, so they are never treated as independent bootstrap samples.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA = [
    "sourceSeed",
    "encounter",
    "floor",
    "turn",
    "decisionIdx",
    "searchSimulationIndex",
    "preObsHash",
    "sharedChildCachedObsHash",
    "postObsHash",
    "drawPileSizeBefore",
    "discardPileSizeBefore",
    "particleCount",
    "bucketCount",
    "bucketProbability",
    "distinctBucketCount",
    "parentObsVisits",
    "parentObsMismatches",
    "sharedChildVisits",
    "sharedAction",
    "conditionedAction",
    "matchedConditionedAction",
    "referenceAction",
    "sharedConditionedAgree",
    "sharedMatchedConditionedAgree",
    "referenceSharedAgree",
    "referenceConditionedAgree",
    "referenceMatchedConditionedAgree",
    "freshSimBudget",
    "matchedSimBudget",
    "referenceSimBudget",
    "referenceValueShared",
    "referenceValueConditioned",
    "referenceValueMatched",
    "referenceMargin",
    "referenceMarginMatched",
    "sharedActionValid",
]

INT_FIELDS = {
    "sourceSeed",
    "encounter",
    "floor",
    "turn",
    "decisionIdx",
    "searchSimulationIndex",
    "preObsHash",
    "sharedChildCachedObsHash",
    "postObsHash",
    "drawPileSizeBefore",
    "discardPileSizeBefore",
    "particleCount",
    "bucketCount",
    "distinctBucketCount",
    "parentObsVisits",
    "parentObsMismatches",
    "sharedChildVisits",
    "freshSimBudget",
    "matchedSimBudget",
    "referenceSimBudget",
    "sharedConditionedAgree",
    "sharedMatchedConditionedAgree",
    "referenceSharedAgree",
    "referenceConditionedAgree",
    "referenceMatchedConditionedAgree",
    "sharedActionValid",
}

FLOAT_FIELDS = {
    "bucketProbability",
    "referenceValueShared",
    "referenceValueConditioned",
    "referenceValueMatched",
    "referenceMargin",
    "referenceMarginMatched",
}


def _float(value: str) -> float | None:
    if value is None or value == "" or value.lower() in {"nan", "null"}:
        return None
    return float(value)


def _transition_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["sourceSeed"],
        row["encounter"],
        row["floor"],
        row["turn"],
        row["decisionIdx"],
        row["searchSimulationIndex"],
        row["preObsHash"],
        row["sharedChildCachedObsHash"],
    )


def validate_rows(fieldnames: list[str] | None, rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    if fieldnames != SCHEMA:
        raise ValueError(
            "CSV schema mismatch; expected exactly "
            + ",".join(SCHEMA)
            + ", got "
            + ",".join(fieldnames or [])
        )

    parsed: list[dict[str, Any]] = []
    for line_number, raw in enumerate(rows, start=2):
        row: dict[str, Any] = {}
        try:
            for name in INT_FIELDS:
                row[name] = int(raw[name])
            for name in FLOAT_FIELDS:
                row[name] = _float(raw[name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid numeric value on CSV line {line_number}: {exc}") from exc

        row.update({
            name: raw[name]
            for name in SCHEMA
            if name not in INT_FIELDS and name not in FLOAT_FIELDS
        })
        probability = row["bucketProbability"]
        if probability is None or not math.isfinite(probability) or probability < 0:
            raise ValueError(f"invalid bucketProbability on CSV line {line_number}")
        if row["particleCount"] <= 0 or row["bucketCount"] < 0:
            raise ValueError(f"invalid particle count on CSV line {line_number}")
        if row["distinctBucketCount"] < 2:
            raise ValueError(f"non-measured row on CSV line {line_number}")
        if row["parentObsVisits"] <= 0 or row["parentObsMismatches"] != 0:
            raise ValueError(f"unstable END_TURN parent on CSV line {line_number}")
        parsed.append(row)

    if not parsed:
        raise ValueError("CSV contains no diagnostic rows")
    return parsed


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return validate_rows(reader.fieldnames, reader)


def _weighted(rows: list[dict[str, Any]], predicate) -> tuple[float, float]:
    numerator = 0.0
    denominator = 0.0
    for row in rows:
        probability = row["bucketProbability"]
        if predicate(row):
            numerator += probability
        denominator += probability
    return numerator, denominator


def _comparison_seed_summary(rows: list[dict[str, Any]], comparison: str) -> dict[str, Any]:
    if comparison == "matched":
        agree_field = "sharedMatchedConditionedAgree"
        reference_candidate_field = "referenceMatchedConditionedAgree"
        margin_field = "referenceMarginMatched"
    elif comparison == "fresh":
        agree_field = "sharedConditionedAgree"
        reference_candidate_field = "referenceConditionedAgree"
        margin_field = "referenceMargin"
    else:
        raise ValueError(f"unknown comparison: {comparison}")

    comparable = [row for row in rows if row[agree_field] in (0, 1)]
    total_mass = sum(row["bucketProbability"] for row in comparable)
    disagreement = sum(
        row["bucketProbability"] for row in comparable if row[agree_field] == 0
    )
    disagreement_rows = [row for row in comparable if row[agree_field] == 0]
    reference_mass = {
        "shared": sum(
            row["bucketProbability"]
            for row in disagreement_rows
            if row["referenceSharedAgree"] == 1
        ),
        "conditioned": sum(
            row["bucketProbability"]
            for row in disagreement_rows
            if row[reference_candidate_field] == 1
        ),
        "neither": sum(
            row["bucketProbability"]
            for row in disagreement_rows
            if row["referenceSharedAgree"] != 1
            and row[reference_candidate_field] != 1
        ),
    }
    finite_margin_rows = [
        row for row in comparable
        if row[margin_field] is not None and math.isfinite(row[margin_field])
    ]
    margin_mass = sum(row["bucketProbability"] for row in finite_margin_rows)
    margin_mean = (
        sum(row["bucketProbability"] * row[margin_field] for row in finite_margin_rows)
        / margin_mass
        if margin_mass
        else None
    )
    return {
        "rows": len(rows),
        "comparableRows": len(comparable),
        "probabilityMass": total_mass,
        "disagreementMass": disagreement,
        "disagreementFraction": disagreement / total_mass if total_mass else None,
        "referencePreferenceMass": reference_mass,
        "referencePreferenceFraction": {
            key: value / disagreement if disagreement else None
            for key, value in reference_mass.items()
        },
        "referenceMargin": margin_mean,
        "referenceMarginMass": margin_mass,
    }


def _source_summaries(rows: list[dict[str, Any]], comparison: str) -> list[dict[str, Any]]:
    by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_seed[row["sourceSeed"]].append(row)
    summaries = []
    for source_seed, seed_rows in sorted(by_seed.items()):
        summary = _comparison_seed_summary(seed_rows, comparison)
        summary["sourceSeed"] = source_seed
        summaries.append(summary)
    return summaries


def _mean(values: list[float | None]) -> float | None:
    finite = [value for value in values if value is not None and math.isfinite(value)]
    return sum(finite) / len(finite) if finite else None


def _bootstrap(values: list[float | None], samples: int, seed: int) -> list[float]:
    usable = [value for value in values if value is not None and math.isfinite(value)]
    if not usable or samples <= 0:
        return []
    rng = random.Random(seed)
    output = []
    for _ in range(samples):
        draw = [usable[rng.randrange(len(usable))] for _ in usable]
        output.append(sum(draw) / len(draw))
    return output


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def comparison_report(
    rows: list[dict[str, Any]], comparison: str, bootstrap_samples: int, seed: int
) -> dict[str, Any]:
    pooled = _comparison_seed_summary(rows, comparison)
    source = _source_summaries(rows, comparison)
    metrics = {
        "disagreementFraction": "disagreementFraction",
        "referenceSharedFraction": ("referencePreferenceFraction", "shared"),
        "referenceConditionedFraction": ("referencePreferenceFraction", "conditioned"),
        "referenceNeitherFraction": ("referencePreferenceFraction", "neither"),
        "referenceMargin": "referenceMargin",
    }
    source_seed_estimate = {}
    bootstrap_ci = {}
    for metric_index, (output_name, path) in enumerate(metrics.items()):
        values = []
        for summary in source:
            value = summary
            if isinstance(path, tuple):
                value = value[path[0]][path[1]]
            else:
                value = value[path]
            values.append(value)
        source_seed_estimate[output_name] = _mean(values)
        distribution = _bootstrap(
            values, bootstrap_samples, seed + metric_index * 1000
        )
        bootstrap_ci[output_name] = {
            "low": _percentile(distribution, 0.025),
            "high": _percentile(distribution, 0.975),
            "samples": bootstrap_samples if distribution else 0,
        }
    return {
        "comparison": comparison,
        "sourceSeeds": len(source),
        "pooledProbabilityWeighted": pooled,
        "sourceSeedMean": source_seed_estimate,
        "sourceSeedBootstrapCI95": bootstrap_ci,
    }


def _strata(rows: list[dict[str, Any]], field: str, comparison: str) -> list[dict[str, Any]]:
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    result = []
    for value, group in sorted(grouped.items(), key=lambda item: item[0]):
        summary = _comparison_seed_summary(group, comparison)
        summary["stratum"] = value
        summary["sourceSeeds"] = len({row["sourceSeed"] for row in group})
        result.append(summary)
    return result


def analyze(rows: list[dict[str, Any]], bootstrap_samples: int, seed: int) -> dict[str, Any]:
    transition_count = len({_transition_key(row) for row in rows})
    probability_sums = defaultdict(float)
    for row in rows:
        probability_sums[_transition_key(row)] += row["bucketProbability"]
    warnings = [
        f"transition {key} has probability sum {total:.6f}"
        for key, total in probability_sums.items()
        if abs(total - 1.0) > 1e-6
    ]
    return {
        "schema": "s3_strategy_fusion_diag_analyzer_v1",
        "rows": len(rows),
        "transitions": transition_count,
        "sourceSeeds": sorted({row["sourceSeed"] for row in rows}),
        "bootstrapSamples": bootstrap_samples,
        "primaryMatchedCompute": comparison_report(
            rows, "matched", bootstrap_samples, seed
        ),
        "secondaryFreshSearch": comparison_report(
            rows, "fresh", bootstrap_samples, seed + 1000
        ),
        "strata": {
            "distinctBucketCount": _strata(rows, "distinctBucketCount", "matched"),
            "drawPileSizeBefore": _strata(rows, "drawPileSizeBefore", "matched"),
            "encounter": _strata(rows, "encounter", "matched"),
        },
        "warnings": warnings,
    }


def self_test() -> None:
    def row(seed: int, probability: float, agree: int, ref_shared: int, ref_matched: int) -> dict[str, str]:
        values = {name: "0" for name in SCHEMA}
        values.update({
            "sourceSeed": str(seed),
            "bucketProbability": str(probability),
            "particleCount": "8",
            "bucketCount": "4",
            "distinctBucketCount": "2",
            "parentObsVisits": "1",
            "parentObsMismatches": "0",
            "sharedAction": "CARD:1",
            "conditionedAction": "CARD:2",
            "matchedConditionedAction": "CARD:3",
            "referenceAction": "CARD:1",
            "sharedMatchedConditionedAgree": str(agree),
            "referenceSharedAgree": str(ref_shared),
            "referenceMatchedConditionedAgree": str(ref_matched),
            "referenceMarginMatched": "2.0",
        })
        return values

    rows = validate_rows(
        list(SCHEMA),
        [
            row(1, 0.5, 0, 1, 0),
            row(1, 0.5, 1, 1, 1),
            row(2, 1.0, 1, 1, 1),
        ],
    )
    report = analyze(rows, bootstrap_samples=100, seed=7)
    estimate = report["primaryMatchedCompute"]["sourceSeedMean"]["disagreementFraction"]
    assert math.isclose(estimate, 0.25), estimate
    preference = report["primaryMatchedCompute"]["sourceSeedMean"]["referenceSharedFraction"]
    assert math.isclose(preference, 1.0), preference
    assert report["transitions"] == 2
    print("analyze_s3_strategy_fusion_diag self-test PASS")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.csv is None:
        parser.error("csv path is required unless --self-test is used")
    if args.bootstrap_samples < 0:
        parser.error("--bootstrap-samples must be non-negative")
    try:
        result = analyze(read_csv(args.csv), args.bootstrap_samples, args.seed)
    except (OSError, ValueError) as exc:
        print(f"analyzer error: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
