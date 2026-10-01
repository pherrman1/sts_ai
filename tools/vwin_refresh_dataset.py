"""Strict component-preserving numerical access for the #334 offline experiment.

No numerical cache is written. Inputs must remain immutable after validation.
TEST access is private to the frozen evaluator; preflight only checks its joins.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from tools.vwin_refresh_contract import ContractError, MAP_PREFIX, _sha256
from tools.vwin_refresh_corpus import validate_corpus

REAL_INDEX_SHA256 = "ca4b6e2bbcb29d10f83bd90944b991dd7f19eebdf5e19029e7ffac5a049cd87f"
REAL_SPLIT_COUNTS = {"TRAIN": 358, "VALIDATION": 77, "TEST": 77}
SPLIT_RULE = 'sha256("vwin-refresh-334-v1:{seed}")[:8] / 2^32; <0.70 TRAIN; <0.85 VALIDATION; else TEST'
HALF_TRAIN_RULE = "lowest floor(N/2) TRAIN seeds ranked by (sha256('vwin-refresh-334-half-train-v1:{seed}'), seed)"


def source_split(seed: int) -> str:
    value = int(hashlib.sha256(f"vwin-refresh-334-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32
    return "TRAIN" if value < .70 else "VALIDATION" if value < .85 else "TEST"


def half_train_sources(seeds) -> tuple[int, ...]:
    seeds = sorted(set(int(s) for s in seeds))
    if any(source_split(s) != "TRAIN" for s in seeds):
        raise ContractError("half TRAIN selection received non-TRAIN seed")
    ranked = sorted(seeds, key=lambda s: (hashlib.sha256(f"vwin-refresh-334-half-train-v1:{s}".encode()).hexdigest(), s))
    return tuple(sorted(ranked[:len(ranked) // 2]))


PREBOSS_RULE = "MAP: acts1-3 mapY=14; act4 mapY=2 (native transitionToMapNode/act4Map)"


def preboss_map_state(metadata):
    """Exact next-room boss states, not a floor-distance proxy.

    GameContext::transitionToMapNode increments Y and enters BOSS at Y=15.
    Map::act4Map fixes the elite at Y=2 and its sole boss successor at Y=3.
    Only call on recorded MAP states, never arbitrary WIN_RAW states.
    """
    act, y = int(metadata["act"]), int(metadata["mapY"])
    if act not in (1, 2, 3, 4):
        raise ContractError("unknown act for native pre-boss mapping")
    return int(y == (2 if act == 4 else 14))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _require(ok, message):
    if not ok:
        raise ContractError(message)


class Dataset:
    def __init__(self, index, expected_sha=REAL_INDEX_SHA256, expected_counts=None):
        path = Path(index).resolve()
        self.index_sha256 = _sha256(path)
        _require(self.index_sha256 == expected_sha, "corpus index SHA-256 mismatch")
        self.corpus = validate_corpus(path)  # Sole corpus entry point; full strict validation.
        _require(_sha256(path) == self.index_sha256, "corpus index changed during validation")
        self.split_counts = dict(Counter(source_split(s) for s in self.corpus.source_seeds))
        self.split_counts = {s: self.split_counts.get(s, 0) for s in REAL_SPLIT_COUNTS}
        expected_counts = REAL_SPLIT_COUNTS if expected_counts is None else expected_counts
        _require(self.split_counts == expected_counts, f"source split counts mismatch: {self.split_counts}")
        first = json.loads(self.corpus.components[0].manifest_path.read_text())["stateFeatures"]
        self.feature_names = tuple(first["header"].split(","))
        _require(len(set(self.feature_names)) == len(self.feature_names), "duplicate state feature names")
        self.feature_header_sha256 = first["headerSha256"]
        self._runouts = {}
        for table in self.corpus.tables("runout.csv"):
            joins = {}
            with table.path.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    key = (int(row["sourceSeed"]), row["branchId"])
                    _require(key not in joins, "duplicate runout trajectory")
                    _require(row["trajectoryValid"] == "1" and row["finalWon"] in ("0", "1"), "invalid trajectory/label")
                    joins[key] = int(row["finalWon"])
            self._runouts[table.component.manifest_path] = joins

    def _access(self, split, allow_test):
        _require(split in REAL_SPLIT_COUNTS, f"unknown split: {split}")
        _require(split != "TEST" or allow_test, "TEST access blocked before freeze")

    def _rows(self, kind, splits, numerical=True):
        _require(kind in ("MAP", "WIN_RAW"), "only MAP and WIN_RAW state tables are supported")
        n = len(self.feature_names)
        start, end = len(MAP_PREFIX), len(MAP_PREFIX) + n
        for table in self.corpus.tables("map.csv" if kind == "MAP" else "win_raw.csv"):
            if not any(source_split(s) in splits for s in table.component.source_seeds):
                continue
            joins = self._runouts[table.component.manifest_path]
            with table.path.open(newline="") as stream:
                reader = csv.reader(stream)
                header = next(reader)
                _require(tuple(header[start:end]) == self.feature_names, "feature header changed")
                for row in reader:
                    seed = int(row[0])
                    split = source_split(seed)
                    if split not in splits:
                        continue
                    key = seed, row[1]
                    _require(key in joins, f"missing MAP/runout label join: {key}")
                    metadata = dict(zip(header[:start], row[:start]))
                    metadata.update(zip(header[end:], row[end:]))
                    metadata.update(sourceSeed=seed, branchId=row[1], componentManifestSha256=table.component.manifest_sha256)
                    # Keep original metadata act/floor, even when rich block has names in common.
                    for field in ("rowIdx", "act", "floor", "deviationIdx"):
                        metadata[field] = int(metadata[field])
                    if kind == "MAP":
                        metadata.update(preBoss=preboss_map_state(metadata), preBossRule=PREBOSS_RULE)
                    x = np.asarray(row[start:end], dtype=np.float32) if numerical else None
                    if x is not None:
                        _require(np.isfinite(x).all(), "nonfinite state feature")
                    yield split, x, joins[key], metadata

    def read(self, split, kind="MAP", *, allow_test=False, row_limit=None):
        self._access(split, allow_test)
        if row_limit is not None and (split == "TEST" or row_limit < 1):
            raise ContractError("row limits are only for bounded TRAIN/VALIDATION smokes")
        rows, labels, metadata = [], [], []
        for _, x, y, meta in self._rows(kind, {split}):
            rows.append(x)
            labels.append(y)
            metadata.append(meta)
            if row_limit is not None and len(rows) >= row_limit:
                break
        x = np.asarray(rows, dtype=np.float32).reshape((-1, len(self.feature_names)))
        return x, np.asarray(labels, dtype=np.float32), metadata

    def branches(self, split, *, allow_test=False):
        self._access(split, allow_test)
        result = []
        for table in self.corpus.tables("branches.csv"):
            with table.path.open(newline="") as stream:
                for row in csv.DictReader(stream):
                    seed = int(row["sourceSeed"])
                    if source_split(seed) == split:
                        row.update(sourceSeed=seed, componentManifestSha256=table.component.manifest_sha256)
                        result.append(row)
        return result

    def preflight(self, b0_features):
        missing = sorted(set(b0_features) - set(self.feature_names))
        _require(not missing, f"B0 required features absent: {missing}")
        # Stable online variance (Welford), only TRAIN MAP feature vectors.
        count = 0
        mean = np.zeros(len(self.feature_names), dtype=np.float64)
        m2 = np.zeros_like(mean)
        counts = {s: 0 for s in REAL_SPLIT_COUNTS}
        for _, x, _, _ in self._rows("MAP", {"TRAIN"}):
            count += 1
            delta = x - mean
            mean += delta / count
            m2 += delta * (x - mean)
        counts["TRAIN"] = count
        for split, _, _, _ in self._rows("MAP", {"VALIDATION", "TEST"}, numerical=False):
            counts[split] += 1
        _require(count > 0, "empty TRAIN MAP data")
        variance = m2 / count
        mask = variance > 1e-12
        selected = [name for name, keep in zip(self.feature_names, mask) if keep]
        mask_hash = _digest({"feature_names": list(self.feature_names), "mask": mask.astype(int).tolist()})
        component_hashes = [c.manifest_sha256 for c in self.corpus.components]
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True).strip()
        return {
            "corpus_index_sha256": self.index_sha256,
            "component_manifest_sha256": component_hashes,
            "component_manifests_aggregate_sha256": _digest(component_hashes),
            "tooling_git_sha": git_sha,
            "feature_header_sha256": self.feature_header_sha256,
            "source_count": len(self.corpus.source_seeds), "split_rule": SPLIT_RULE,
            "split_counts": self.split_counts, "row_counts": counts,
            "label_join_checks": {"MAP_rows_checked": sum(counts.values()), "failures": 0, "trajectoryValid_required": 1, "labels": [0, 1]},
            "variance_split": "TRAIN", "variance_threshold": 1e-12,
            "feature_mask": mask.astype(int).tolist(),
            "selected_feature_indices": np.flatnonzero(mask).tolist(),
            "selected_feature_names": selected, "selected_feature_count": len(selected),
            "feature_mask_sha256": mask_hash, "mask_sha256": mask_hash,
            "ordered_selected_feature_names_sha256": _digest(selected),
            "real_test_predictions_opened": False,
        }


def validated_dataset(index, expected_sha=REAL_INDEX_SHA256, expected_counts=None):
    return Dataset(index, expected_sha=expected_sha, expected_counts=expected_counts)
