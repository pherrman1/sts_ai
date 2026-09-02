#!/usr/bin/env python3
"""Fail-closed contract for the V1 pre-combat combat evaluator corpus."""
from __future__ import annotations

import csv, hashlib, json, math
from pathlib import Path

SCHEMA_VERSION = "combat_evaluator_v1"
EPSILON = 1e-3
PREFIX = ["sourceSeed", "fightIdx", "act", "floor", "roomClass", "encounter", "teacherId"]
LABELS = ["won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous", "labelValid",
          "terminalCombatHp", "terminalCombatMaxHp", "terminalNonMinionCurHp", "terminalNonMinionMaxHp", "winHpFrac",
          "lossRemainingFrac", "signedOutcome", "quarantineReason"]

def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def _finite(row, name):
    try: value = float(row[name])
    except Exception as exc: raise ValueError(f"invalid {name}") from exc
    if not math.isfinite(value): raise ValueError(f"non-finite {name}")
    return value

def validate_csv(path: str | Path) -> dict:
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f)); header = rows[0].keys() if rows else (csv.DictReader(path.open()).fieldnames or [])
    header = list(header or [])
    if header[:len(PREFIX)] != PREFIX: raise ValueError("metadata prefix/order mismatch")
    if len(header) <= len(PREFIX) + len(LABELS): raise ValueError("missing state feature block")
    if header[-len(LABELS):] != LABELS: raise ValueError("label suffix/order mismatch")
    features = header[len(PREFIX):-len(LABELS)]
    if len(features) != 1017: raise ValueError(f"expected 1017 state features, got {len(features)}")
    keys, valid = set(), 0; counts = {k: 0 for k in ("valid", "invalid", "ambiguous", "wins", "deaths")}
    for line, row in enumerate(rows, 2):
        key = (int(row["sourceSeed"]), int(row["fightIdx"]))
        if key in keys: raise ValueError(f"duplicate sourceSeed/fightIdx at line {line}")
        keys.add(key)
        for name in features: _finite(row, name)
        bits = {k: int(row[k]) for k in ("won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous", "labelValid")}
        if any(v not in (0, 1) for v in bits.values()): raise ValueError(f"non-binary mask at line {line}")
        for name in LABELS[6:-1]: _finite(row, name)
        for name in ("winHpFrac", "lossRemainingFrac"):
            value = float(row[name])
            if not EPSILON <= value <= 1: raise ValueError(f"{name} outside [{EPSILON},1]")
        signed = _finite(row, "signedOutcome")
        if not -1 <= signed <= 1: raise ValueError("signedOutcome outside [-1,1]")
        is_valid = bits["labelValid"] == 1
        if is_valid and not (bits["won"] or bits["trueDeath"]): raise ValueError("valid row is neither win nor true death")
        if is_valid: valid += 1; counts["valid"] += 1
        else: counts["invalid"] += 1
        counts["ambiguous"] += bits["progressAmbiguous"]
        counts["wins"] += bits["won"] and is_valid
        counts["deaths"] += bits["trueDeath"] and is_valid
    return {"rows": len(rows), "source_seeds": len(keys), "feature_count": len(features),
            "features": features, "counts": counts, "csv_sha256": sha256(path)}

def validate_manifest(manifest: dict, verify_csv=True) -> dict:
    required = ("schema_version", "producer_git_sha", "teacher", "seed_spec", "csv", "feature_contract", "integrity")
    missing = [x for x in required if x not in manifest]
    if missing: raise ValueError("manifest missing: " + ", ".join(missing))
    if manifest["schema_version"] != SCHEMA_VERSION: raise ValueError("unsupported schema version")
    fc = manifest["feature_contract"]
    if fc.get("count") != 1017 or not fc.get("order_hash"): raise ValueError("incomplete feature contract")
    csv_info = manifest["csv"]; path = Path(csv_info["path"])
    if verify_csv and (not path.is_file() or sha256(path) != csv_info.get("sha256")): raise ValueError("CSV hash mismatch")
    return validate_csv(path)

def validate(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix == ".json": return validate_manifest(json.loads(path.read_text()))
    return validate_csv(path)
