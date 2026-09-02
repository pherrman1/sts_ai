#!/usr/bin/env python3
"""Fail-closed contract for the V1 pre-combat combat evaluator corpus."""
from __future__ import annotations

import csv, hashlib, json, math, argparse
from pathlib import Path

SCHEMA_VERSION = "combat_evaluator_v1"
EPSILON = 1e-3
PREFIX = ["sourceSeed", "fightIdx", "act", "floor", "roomClass", "encounter", "teacherId"]
LABELS = ["won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous", "labelValid",
          "terminalCombatHp", "terminalCombatMaxHp", "terminalNonMinionCurHp", "terminalNonMinionMaxHp", "winHpFrac",
          "lossRemainingFrac", "signedOutcome", "quarantineReason"]

FROZEN_TEACHER = {
    "combat_backend": "silver_uct", "rng_regime": "project_fair",
    "search_configuration": {
        "simulation_budgets": [10000], "exploration_parameter": 25.0,
        "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
        "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
        "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
        "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
        "learned_visit_puct": False, "direct_learned_leaf": False, "adaptive": False,
    },
}

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
    keys, seeds, valid = set(), set(), 0; counts = {k: 0 for k in ("valid", "invalid", "ambiguous", "wins", "deaths")}
    for line, row in enumerate(rows, 2):
        key = (int(row["sourceSeed"]), int(row["fightIdx"]))
        if key in keys: raise ValueError(f"duplicate sourceSeed/fightIdx at line {line}")
        keys.add(key); seeds.add(key[0])
        for name in features: _finite(row, name)
        bits = {k: int(row[k]) for k in ("won", "trueDeath", "escaped", "turnCapLoss", "progressAmbiguous", "labelValid")}
        if any(v not in (0, 1) for v in bits.values()): raise ValueError(f"non-binary mask at line {line}")
        if bits["won"] and bits["trueDeath"]: raise ValueError("won and trueDeath both set")
        if bits["escaped"] and bits["trueDeath"]: raise ValueError("escaped true death")
        if bits["turnCapLoss"] and bits["trueDeath"]: raise ValueError("turn-cap true death")
        for name in LABELS[6:-1]: _finite(row, name)
        for name in ("winHpFrac", "lossRemainingFrac"):
            value = float(row[name])
            if not EPSILON <= value <= 1: raise ValueError(f"{name} outside [{EPSILON},1]")
        signed = _finite(row, "signedOutcome")
        if not -1 <= signed <= 1: raise ValueError("signedOutcome outside [-1,1]")
        is_valid = bits["labelValid"] == 1
        if is_valid and not (bits["won"] ^ bits["trueDeath"]): raise ValueError("valid row is not exactly one outcome")
        if is_valid:
            expected = float(row["winHpFrac"]) if bits["won"] else -float(row["lossRemainingFrac"])
            if abs(signed - expected) > 1e-6: raise ValueError("signedOutcome formula mismatch")
        elif abs(signed) > 1e-12: raise ValueError("invalid row has nonzero signedOutcome")
        if is_valid: valid += 1; counts["valid"] += 1
        else: counts["invalid"] += 1
        counts["ambiguous"] += bits["progressAmbiguous"]
        counts["wins"] += bits["won"] and is_valid
        counts["deaths"] += bits["trueDeath"] and is_valid
    quarantined = {int(row["sourceSeed"]) for row in rows if int(row["labelValid"]) == 0}
    return {"rows": len(rows), "source_seeds": len(seeds), "quarantined_source_seeds": len(quarantined),
            "feature_count": len(features),
            "features": features, "counts": counts, "csv_sha256": sha256(path)}

def _validate_teacher(teacher):
    if not isinstance(teacher, dict): raise ValueError("teacher must be an object")
    for key, expected in FROZEN_TEACHER.items():
        if key == "search_configuration":
            actual = teacher.get(key)
            if not isinstance(actual, dict) or any(actual.get(k) != v for k, v in expected.items()): raise ValueError("teacher is not exact frozen Silver")
        elif teacher.get(key) != expected: raise ValueError("teacher backend/RNG mismatch")
    for key in ("teacher_id", "git_sha", "executable_sha256"):
        if not isinstance(teacher.get(key), str) or not teacher[key]: raise ValueError("teacher missing " + key)
    if len(teacher["git_sha"]) != 40 or len(teacher["executable_sha256"]) != 64: raise ValueError("invalid teacher hashes")

def validate_manifest(manifest: dict, verify_csv=True) -> dict:
    required = ("schema_version", "producer_git_sha", "producer_executable_sha256", "teacher", "seed_spec", "csv", "feature_contract", "integrity")
    missing = [x for x in required if x not in manifest]
    if missing: raise ValueError("manifest missing: " + ", ".join(missing))
    if manifest["schema_version"] != SCHEMA_VERSION: raise ValueError("unsupported schema version")
    if len(str(manifest["producer_git_sha"])) != 40 or len(str(manifest["producer_executable_sha256"])) != 64: raise ValueError("invalid producer provenance hashes")
    _validate_teacher(manifest["teacher"])
    if manifest["teacher"]["git_sha"] != manifest["producer_git_sha"] or manifest["teacher"]["executable_sha256"] != manifest["producer_executable_sha256"]:
        raise ValueError("teacher/producer provenance mismatch")
    fc = manifest["feature_contract"]
    if fc.get("count") != 1017 or not fc.get("order_hash"): raise ValueError("incomplete feature contract")
    csv_info = manifest["csv"]; path = Path(csv_info["path"])
    if verify_csv and (not path.is_file() or sha256(path) != csv_info.get("sha256")): raise ValueError("CSV hash mismatch")
    result = validate_csv(path)
    if result["features"] != fc.get("state_names"): raise ValueError("feature names/order mismatch")
    order_hash = hashlib.sha256("\n".join(result["features"] + [f"encounter__{x}" for x in fc.get("encounters", [])]).encode()).hexdigest()
    if order_hash != fc.get("order_hash"): raise ValueError("feature order hash mismatch")
    expected_model_features = result["features"] + [f"encounter__{x}" for x in fc.get("encounters", [])]
    if sorted(fc.get("model_features", [])) != sorted(expected_model_features): raise ValueError("model feature contract mismatch")
    integrity = manifest["integrity"]
    for key in ("rows", "source_seeds", "quarantined_source_seeds"):
        if int(integrity.get(key, -1)) != result[key]: raise ValueError("manifest count mismatch: " + key)
    spec = manifest["seed_spec"]
    if int(spec.get("count", -1)) < 1 or int(spec.get("offset", spec.get("start", -1))) < 0: raise ValueError("invalid seed block")
    offset = int(spec.get("offset", spec.get("start")))
    count = int(spec["count"])
    with path.open(newline="", encoding="utf-8") as f:
        csv_seeds = {int(r["sourceSeed"]) for r in csv.DictReader(f)}
    if not csv_seeds.issubset(set(range(offset, offset + count))): raise ValueError("CSV source seed outside manifest block")
    return result

def build_manifest(csv_path, teacher_path, output, producer_git_sha, producer_executable_sha256,
                   seed_offset, seed_count, ascension):
    csv_path, teacher_path = Path(csv_path).resolve(), Path(teacher_path).resolve()
    teacher = json.loads(teacher_path.read_text())
    _validate_teacher(teacher)
    result = validate_csv(csv_path)
    encounters = sorted({r["encounter"] for r in csv.DictReader(csv_path.open(encoding="utf-8")) if r["labelValid"] == "1"})
    order_hash = hashlib.sha256("\n".join(result["features"] + [f"encounter__{x}" for x in encounters]).encode()).hexdigest()
    manifest = {"schema_version": SCHEMA_VERSION, "producer_git_sha": producer_git_sha,
        "producer_executable_sha256": producer_executable_sha256, "teacher": teacher,
        "seed_spec": {"offset": int(seed_offset), "count": int(seed_count), "ascension": int(ascension)},
        "csv": {"path": str(csv_path), "sha256": sha256(csv_path)},
        "feature_contract": {"count": 1017, "state_names": result["features"], "encounters": encounters,
            "model_features": result["features"] + [f"encounter__{x}" for x in encounters], "one_hot": True, "order_hash": order_hash},
        "integrity": {**result["counts"], "rows": result["rows"], "source_seeds": result["source_seeds"],
                      "quarantined_source_seeds": result["quarantined_source_seeds"]}}
    Path(output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    validate_manifest(manifest)
    return manifest

def validate(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix == ".json": return validate_manifest(json.loads(path.read_text()))
    return validate_csv(path)

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("path"); p.add_argument("--manifest", action="store_true")
    p.add_argument("--build", action="store_true"); p.add_argument("--teacher"); p.add_argument("--output")
    p.add_argument("--producer-git-sha"); p.add_argument("--producer-executable-sha256"); p.add_argument("--seed-offset", type=int); p.add_argument("--seed-count", type=int); p.add_argument("--ascension", type=int, default=0)
    a = p.parse_args()
    if a.build:
        print(json.dumps(build_manifest(a.path, a.teacher, a.output, a.producer_git_sha, a.producer_executable_sha256, a.seed_offset, a.seed_count, a.ascension), indent=2, sort_keys=True))
    else: print(json.dumps(validate_manifest(json.loads(Path(a.path).read_text())) if a.manifest else validate_csv(a.path), indent=2, sort_keys=True))
