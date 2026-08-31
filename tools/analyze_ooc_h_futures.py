#!/usr/bin/env python3
"""Fail-closed H-futures analysis over the preserved PR-104 Stage-B evidence."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

try:
    from tools.analyze_ooc_k_budget import KEY, contrast, metric_rows, summarize
except ModuleNotFoundError:
    from analyze_ooc_k_budget import KEY, contrast, metric_rows, summarize


A_FUTURES = (10, 11, 12, 13)
B_FUTURES = (100, 101, 102, 103)
H_VALUES = (1, 2, 4)


def _load(paths: list[Path]) -> pd.DataFrame:
    frame = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)
    if frame.empty or (frame.valid != 1).any():
        raise ValueError("all H-analysis rows must be valid")
    identity = [*KEY, "side", "futureIdentity", "prefixFight", "rowKind", "schedule"]
    if frame.duplicated(identity).any():
        raise ValueError("duplicate H-analysis identity")
    frame["schedule"] = frame.schedule.astype(str)
    return frame


def _input_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _expected_keys(manifest: dict) -> set[tuple[int, int, int]]:
    if manifest.get("schema") != "ooc_k_budget_manifest_v1":
        raise ValueError("frozen manifest schema mismatch")
    decisions = manifest.get("decisions", [])
    if len(decisions) != 32:
        raise ValueError("H analysis requires exactly 32 frozen decisions")
    if sorted(row["sourceSeed"] for row in decisions) != list(range(982100, 982132)):
        raise ValueError("frozen source-seed cohort mismatch")
    keys = {
        (row["sourceSeed"], row["decisionIdx"], action_idx)
        for row in decisions
        for action_idx, _ in enumerate(row["actions"])
    }
    if len(keys) != 157:
        raise ValueError("H analysis requires exactly 157 sibling actions")
    return keys


def _require_coverage(frame: pd.DataFrame, expected: set[tuple[int, int, int]]) -> None:
    actual = set(map(tuple, frame[KEY].drop_duplicates().itertuples(index=False, name=None)))
    if actual != expected:
        raise ValueError("action coverage differs from the frozen manifest")


def _average_subset_metrics(a_rows: pd.DataFrame, truth: pd.Series, h: int) -> tuple[pd.DataFrame, list[dict]]:
    subset_frames = []
    subset_reports = []
    for subset in itertools.combinations(A_FUTURES, h):
        scores = (
            a_rows[a_rows.futureIdentity.isin(subset)]
            .groupby(KEY)
            .qProduct.mean()
        )
        rows = metric_rows(scores, truth)
        subset_frames.append(rows.set_index(["sourceSeed", "decisionIdx"]))
        subset_reports.append({"futures": list(subset), "metrics": summarize(rows)})
    combined = pd.concat(subset_frames, keys=range(len(subset_frames)), names=["subset"])
    averaged = combined.groupby(["sourceSeed", "decisionIdx"]).mean().reset_index()
    return averaged, subset_reports


def analyze(a_paths: list[Path], b_paths: list[Path], manifest_path: Path, spec_path: Path,
            bootstrap: int, seed: int, expected_a_digest: str, expected_b_digest: str) -> dict:
    if bootstrap <= 0:
        raise ValueError("bootstrap replicates must be positive")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema") != "ooc_k_budget_experiment_v1":
        raise ValueError("frozen experiment spec schema mismatch")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != spec.get("manifest", {}).get("sha256"):
        raise ValueError("manifest hash differs from frozen experiment spec")
    if spec.get("A", {}).get("stageB", {}).get("futureIdentities") != list(A_FUTURES) or spec.get("B", {}).get("futureIdentities") != list(B_FUTURES):
        raise ValueError("future identities differ from frozen experiment spec")
    if [10000] not in spec.get("A", {}).get("stageB", {}).get("schedules", []) or spec.get("B", {}).get("schedule") != [10000]:
        raise ValueError("K1/B schedules differ from frozen experiment spec")
    expected = _expected_keys(json.loads(manifest_path.read_text(encoding="utf-8")))
    a_digest, b_digest = _input_digest(a_paths), _input_digest(b_paths)
    if a_digest != expected_a_digest or b_digest != expected_b_digest:
        raise ValueError("A/B input bytes differ from the frozen digest")
    a_rows = _load(a_paths)
    b_rows = _load(b_paths)
    if set(a_rows.side) != {"A"} or not set(a_rows.rowKind).issubset({"prefix", "terminal"}):
        raise ValueError("A inputs contain an unexpected side or row kind")
    a_rows = a_rows[a_rows.rowKind == "prefix"].copy()
    if set(a_rows.schedule) != {"10000"} or set(a_rows.prefixFight) != {1}:
        raise ValueError("A inputs must be frozen K1 [10000] rows")
    if set(map(int, a_rows.futureIdentity.unique())) != set(A_FUTURES):
        raise ValueError("A future identities must be exactly 10,11,12,13")
    if set(b_rows.side) != {"B"} or set(b_rows.rowKind) != {"terminal"}:
        raise ValueError("B inputs must contain only terminal rows")
    if set(b_rows.schedule) != {"10000"}:
        raise ValueError("B truth must use the frozen ordinary Silver 10k schedule")
    if set(map(int, b_rows.futureIdentity.unique())) != set(B_FUTURES):
        raise ValueError("B future identities must be exactly 100,101,102,103")
    for frame, futures, label in ((a_rows, A_FUTURES, "A"), (b_rows, B_FUTURES, "B")):
        _require_coverage(frame, expected)
        complete = frame.groupby(KEY).futureIdentity.apply(lambda values: set(map(int, values)) == set(futures))
        if not complete.all():
            raise ValueError(f"incomplete {label} action/future coverage")

    truth = b_rows.groupby(KEY).terminalWon.mean()
    metrics = {}
    averaged = {}
    subsets = {}
    for h in H_VALUES:
        averaged[h], subsets[h] = _average_subset_metrics(a_rows, truth, h)
        metrics[f"H{h}"] = summarize(averaged[h])
        metrics[f"H{h}"]["subsetCount"] = len(subsets[h])
        metrics[f"H{h}"]["relativeLabelCost"] = h

    contrasts = {
        "H2-H1": contrast(averaged[2], averaged[1], bootstrap, seed),
        "H4-H2": contrast(averaged[4], averaged[2], bootstrap, seed + 1),
    }
    return {
        "schema": "ooc_h_futures_analysis_v1",
        "configuration": {
            "decisions": 32,
            "actions": 157,
            "A_futures": list(A_FUTURES),
            "B_terminal_futures": list(B_FUTURES),
            "subsetSemantics": "enumerated sensitivity subsets, not independent replicates",
            "bootstrap": {"clusters": "sourceSeed", "replicates": bootstrap, "seed": seed},
            "A_input_digest": a_digest,
            "B_input_digest": b_digest,
        },
        "metrics": metrics,
        "contrasts": contrasts,
        "subsetMetrics": {f"H{h}": subsets[h] for h in H_VALUES},
    }


def self_test() -> None:
    assert list(itertools.combinations(A_FUTURES, 1)) == [(10,), (11,), (12,), (13,)]
    assert len(list(itertools.combinations(A_FUTURES, 2))) == 6
    assert len(list(itertools.combinations(A_FUTURES, 4))) == 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", nargs="+", type=Path)
    parser.add_argument("--b", nargs="+", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--expected-a-digest", required=False)
    parser.add_argument("--expected-b-digest", required=False)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test PASS")
        return
    if not args.a or not args.b or not args.manifest or not args.spec or not args.output or not args.expected_a_digest or not args.expected_b_digest:
        parser.error("--a, --b, --manifest, --spec, --output, and both frozen input digests are required")
    report = analyze(args.a, args.b, args.manifest, args.spec, args.bootstrap, args.seed,
                     args.expected_a_digest, args.expected_b_digest)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
