#!/usr/bin/env python3
"""Validate RAW combat-transition JSONL corpora.

The producer stores full pre/post persistent-transfer snapshots rather than
inventing a scalar delta target.  This contract is deliberately independent
of model training: a validated corpus is evidence that can be audited, not an
authorization to replace native combat or continuation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from tools.ooc_pipeline_contract import validate_teacher
    from tools.combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH as PREDICTOR_FIELD_SCHEMA_HASH,
        SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION,
        validate_predictor_input,
    )
except ModuleNotFoundError:  # direct invocation from the tools directory
    from ooc_pipeline_contract import validate_teacher
    from combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH as PREDICTOR_FIELD_SCHEMA_HASH,
        SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION,
        validate_predictor_input,
    )

SCHEMA_VERSION = "combat_transition_v1"
ROW_SCHEMA_VERSION = "combat_transition_row_v2"

STATE_KEYS = {
    "curHp", "maxHp", "gold", "potionCount", "potionCapacity", "potions",
    "smokeBombUsed", "stolenGold", "relics", "relicBits", "deck",
    "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount",
    "combatRng",
}
RNG_KEYS = {"counter", "seed0", "seed1"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _finite(value, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def validate_state(state: dict, label: str) -> None:
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
        missing = sorted(STATE_KEYS - set(state)) if isinstance(state, dict) else sorted(STATE_KEYS)
        extra = sorted(set(state) - STATE_KEYS) if isinstance(state, dict) else []
        raise ValueError(f"{label} state keys mismatch; missing={missing}, extra={extra}")
    for key in ("curHp", "maxHp", "gold", "potionCount", "potionCapacity",
                "stolenGold", "upgradeableCount", "transformableCount"):
        _integer(state[key], f"{label}.{key}")
    if not isinstance(state["smokeBombUsed"], bool):
        raise ValueError(f"{label}.smokeBombUsed must be boolean")
    if len(state["potions"]) != 5 or any(not isinstance(v, int) or isinstance(v, bool) for v in state["potions"]):
        raise ValueError(f"{label}.potions must contain five integer slots")
    if len(state["relicBits"]) != 3 or any(not isinstance(v, int) or isinstance(v, bool) for v in state["relicBits"]):
        raise ValueError(f"{label}.relicBits must contain three integers")
    if len(state["cardTypeCounts"]) != 4 or len(state["bottleIdxs"]) != 3:
        raise ValueError(f"{label}.deck metadata has the wrong width")
    for i, relic in enumerate(state["relics"]):
        if set(relic) != {"id", "data"}:
            raise ValueError(f"{label}.relics[{i}] keys mismatch")
        _integer(relic["id"], f"{label}.relics[{i}].id")
        _integer(relic["data"], f"{label}.relics[{i}].data")
    for i, card in enumerate(state["deck"]):
        if set(card) != {"id", "misc", "upgraded"}:
            raise ValueError(f"{label}.deck[{i}] keys mismatch")
        _integer(card["id"], f"{label}.deck[{i}].id")
        _integer(card["misc"], f"{label}.deck[{i}].misc")
        if not isinstance(card["upgraded"], bool):
            raise ValueError(f"{label}.deck[{i}].upgraded must be boolean")
    if len(state["combatRng"]) != 6:
        raise ValueError(f"{label}.combatRng must contain six streams")
    for i, rng in enumerate(state["combatRng"]):
        if set(rng) != RNG_KEYS:
            raise ValueError(f"{label}.combatRng[{i}] keys mismatch")
        for key in RNG_KEYS:
            _integer(rng[key], f"{label}.combatRng[{i}].{key}")


def validate_manifest(manifest: dict, verify_data: bool = True) -> dict:
    required = {"schemaVersion", "rowSchemaVersion", "predictorInputSchemaVersion",
                "predictorInputFieldSchemaHash", "format", "producerGitSha",
                "producerExecutableSha256", "combatTeacher", "seedSpec", "csv", "integrity"}
    missing = sorted(required - set(manifest))
    if missing:
        raise ValueError("transition manifest missing: " + ", ".join(missing))
    if manifest["schemaVersion"] != SCHEMA_VERSION or manifest["rowSchemaVersion"] != ROW_SCHEMA_VERSION:
        raise ValueError("unsupported transition schema")
    if (manifest["predictorInputSchemaVersion"] != PREDICTOR_SCHEMA_VERSION
            or manifest["predictorInputFieldSchemaHash"] != PREDICTOR_FIELD_SCHEMA_HASH):
        raise ValueError("predictor input schema binding mismatch")
    if manifest["format"] != "jsonl":
        raise ValueError("transition format must be jsonl")
    if len(manifest["producerGitSha"]) != 40 or len(manifest["producerExecutableSha256"]) != 64:
        raise ValueError("producer Git/executable identities must be full hashes")
    teacher = manifest["combatTeacher"]
    if not isinstance(teacher, dict) or not teacher.get("teacher_id"):
        raise ValueError("combatTeacher.teacher_id is required")
    if manifest.get("testFixture") is True:
        expected = {
            "teacher_id": "test-only-deterministic-transition-fixture",
            "combat_backend": "deterministic_fixture",
            "rng_regime": "deterministic_fixture",
        }
        for key, value in expected.items():
            if teacher.get(key) != value:
                raise ValueError(f"test fixture teacher {key} is invalid")
        if teacher.get("search_configuration") != {} or teacher.get("environment") != {}:
            raise ValueError("test fixture teacher must not carry production configuration")
        if teacher.get("model_artifacts") != []:
            raise ValueError("test fixture teacher must not carry model artifacts")
    else:
        # Keep the production teacher contract unchanged and strict.  The
        # deterministic fixture is accepted only through the explicit,
        # testFixture-marked branch above.
        validate_teacher(teacher)
    intervention = manifest.get("lizardIntervention")
    if intervention is None:
        if teacher.get("git_sha") != manifest["producerGitSha"]:
            raise ValueError("producer Git SHA disagrees with combat teacher")
        if teacher.get("executable_sha256") != manifest["producerExecutableSha256"]:
            raise ValueError("producer executable hash disagrees with combat teacher")
    else:
        required_intervention = {
            "schema", "activeLizard", "baselineGitSha", "collectorGitSha",
            "collectorExecutableSha256", "teacherId", "teacherGitSha",
            "teacherExecutableSha256", "teacherManifestSha256", "teacherModelArtifacts",
            "predictorInputFieldSchemaHash", "sourceSeedStart", "sourceSeedCount",
            "activeLizardRows", "sourceTrajectory", "markOfBloomRows",
        }
        if not isinstance(intervention, dict) or set(intervention) != required_intervention:
            raise ValueError("lizardIntervention keys mismatch")
        if intervention["schema"] != "active_lizard_shadow_intervention_v1" or intervention["activeLizard"] is not True:
            raise ValueError("unsupported active Lizard intervention")
        if intervention["collectorGitSha"] != manifest["producerGitSha"]:
            raise ValueError("collector Git SHA disagrees with producer")
        if intervention["collectorExecutableSha256"] != manifest["producerExecutableSha256"]:
            raise ValueError("collector executable hash disagrees with producer")
        if intervention["teacherId"] != teacher.get("teacher_id"):
            raise ValueError("intervention teacher ID disagrees with combat teacher")
        if intervention["teacherGitSha"] != teacher.get("git_sha") or intervention["teacherExecutableSha256"] != teacher.get("executable_sha256"):
            raise ValueError("intervention frozen teacher identity mismatch")
        if intervention["teacherModelArtifacts"] != teacher.get("model_artifacts"):
            raise ValueError("intervention frozen model artifacts mismatch")
        if intervention["predictorInputFieldSchemaHash"] != manifest["predictorInputFieldSchemaHash"]:
            raise ValueError("intervention predictor schema mismatch")
        if (intervention["teacherId"] != "silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77"
                or intervention["sourceTrajectory"] != "untouched_normal_policy"
                or intervention["markOfBloomRows"] != "excluded"):
            raise ValueError("active Lizard corpus teacher or intervention contract mismatch")
        if intervention["baselineGitSha"] != "aa09f75e6be837f7f39a2e31dde234bfd2c2ef08":
            raise ValueError("active Lizard corpus baseline differs from accepted handoff")
        for key, length in (("baselineGitSha", 40), ("collectorGitSha", 40),
                            ("collectorExecutableSha256", 64), ("teacherGitSha", 40),
                            ("teacherExecutableSha256", 64), ("teacherManifestSha256", 64)):
            value = intervention[key]
            if not isinstance(value, str) or len(value) != length or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"lizardIntervention.{key} must be a full lowercase hash")
        if (intervention["sourceSeedStart"] != manifest["seedSpec"]["start"]
                or intervention["sourceSeedCount"] != manifest["seedSpec"]["count"]):
            raise ValueError("intervention source seed block mismatch")
    path = Path(manifest["csv"]["path"])
    if verify_data and (not path.is_file() or sha256(path) != manifest["csv"].get("sha256")):
        raise ValueError("JSONL is missing or its SHA256 disagrees with manifest")
    return manifest


def validate_corpus(manifest: dict, verify_data: bool = True) -> dict:
    validate_manifest(manifest, verify_data)
    intervention = manifest.get("lizardIntervention")
    path = Path(manifest["csv"]["path"])
    teacher_id = manifest["combatTeacher"]["teacher_id"]
    seed_spec = manifest["seedSpec"]
    if not isinstance(seed_spec, dict) or set(seed_spec) != {"start", "count"}:
        raise ValueError("seedSpec must contain exactly start and count")
    seed_start = _integer(seed_spec["start"], "seedSpec.start")
    requested = _integer(seed_spec["count"], "seedSpec.count")
    if requested < 0:
        raise ValueError("seedSpec.count must be non-negative")
    expected_seeds = set(range(seed_start, seed_start + requested))
    integrity = manifest["integrity"]
    if not isinstance(integrity, dict):
        raise ValueError("integrity must be an object")
    requested_integrity = _integer(integrity.get("requestedSeeds"), "integrity.requestedSeeds")
    completed_integrity = _integer(integrity.get("completedSeeds"), "integrity.completedSeeds")
    quarantined_integrity = _integer(integrity.get("quarantinedSeeds"), "integrity.quarantinedSeeds")
    for value, name in ((requested_integrity, "requestedSeeds"),
                        (completed_integrity, "completedSeeds"),
                        (quarantined_integrity, "quarantinedSeeds")):
        if value < 0:
            raise ValueError(f"integrity.{name} must be non-negative")
    if requested_integrity != requested:
        raise ValueError("integrity requestedSeeds disagrees with seedSpec.count")
    if completed_integrity + quarantined_integrity != requested:
        raise ValueError("source seed accounting does not reconcile")
    rows = 0
    seeds = set()
    keys = set()
    intervention_keys = set()
    outcomes = {0: 0, 1: 0, 2: 0}
    quarantined = 0
    if not path.is_file():
        raise ValueError("transition JSONL is missing")
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank transition row at line {line_number}")
            try:
                row = json.loads(line)
                if set(row) != {"schemaVersion", "rowSchemaVersion", "sourceSeed", "fightIdx",
                                 "act", "floor", "roomClass", "encounter", "teacherId",
                                 "runValid", "quarantineReason", "captureCount",
                                 "captureStatus", "predictorInput", "transition"}:
                    raise ValueError("row keys mismatch")
                if row["schemaVersion"] != SCHEMA_VERSION or row["rowSchemaVersion"] != ROW_SCHEMA_VERSION:
                    raise ValueError("row schema mismatch")
                seed = _integer(row["sourceSeed"], "sourceSeed")
                fight = _integer(row["fightIdx"], "fightIdx")
                key = (seed, fight)
                if key in keys:
                    raise ValueError("duplicate sourceSeed/fightIdx")
                if seed not in expected_seeds:
                    raise ValueError("sourceSeed is outside seedSpec")
                keys.add(key); seeds.add(seed)
                if row["teacherId"] != teacher_id:
                    raise ValueError("teacherId mismatch")
                if not isinstance(row["runValid"], bool) or not isinstance(row["quarantineReason"], str):
                    raise ValueError("runValid/quarantineReason types invalid")
                capture_count = _integer(row["captureCount"], "captureCount")
                if capture_count < 0:
                    raise ValueError("captureCount must be non-negative")
                expected_status = ("missing" if capture_count == 0 else
                                   "exactly_one" if capture_count == 1 else "repeated")
                if row["captureStatus"] != expected_status:
                    raise ValueError("captureCount/captureStatus mismatch")
                predictor_input = row["predictorInput"]
                validate_predictor_input(predictor_input)
                if (predictor_input["schemaVersion"] != manifest["predictorInputSchemaVersion"]
                        or predictor_input["fieldSchemaHash"] != manifest["predictorInputFieldSchemaHash"]):
                    raise ValueError("predictor input does not match manifest schema binding")
                globals_value = predictor_input["globals"]
                if intervention is not None:
                    try:
                        from tools.combat_transition_surrogate import _RELIC_IDS
                    except ModuleNotFoundError:
                        from combat_transition_surrogate import _RELIC_IDS
                    lizard_id = _RELIC_IDS["LIZARD_TAIL"]
                    if not any(r["relicId"] == lizard_id and r["data"] == 1
                               for r in predictor_input["relics"]):
                        raise ValueError("active Lizard predictor input is missing data=1")
                    if any(r["relicId"] == _RELIC_IDS["MARK_OF_THE_BLOOM"]
                           for r in predictor_input["relics"]):
                        raise ValueError("Mark of the Bloom contaminated active Lizard corpus")
                    intervention_keys.add((seed, fight))
                    pre_relics = row["transition"]["pre"]["relics"] if row["transition"] else []
                    if row["transition"] is not None:
                        if not any(r["id"] == lizard_id and r["data"] == 1 for r in pre_relics):
                            raise ValueError("active Lizard RAW pre-state is not active")
                        post_relics = row["transition"]["post"]["relics"]
                        if not any(r["id"] == lizard_id and r["data"] in (0, 1) for r in post_relics):
                            raise ValueError("active Lizard RAW post-state is missing or invalid")
                for field in ("act", "floor", "encounter"):
                    if globals_value[field] != row[field]:
                        raise ValueError(f"predictor input {field} disagrees with row")
                expected_room_class = {
                    3: "ELITE", 4: "NORMAL", 6: "BOSS",
                }.get(globals_value["roomClass"], "OTHER")
                if expected_room_class != row["roomClass"]:
                    raise ValueError("predictor input roomClass disagrees with row")
                transition = row["transition"]
                if transition is None:
                    if row["runValid"] or capture_count == 1:
                        raise ValueError("missing full transition snapshot")
                    if row["quarantineReason"] not in {"missing_raw_capture", "repeated_raw_capture", "missing_raw_record"}:
                        raise ValueError("capture failure has the wrong quarantine reason")
                    quarantined += 1
                    rows += 1
                    continue
                if not isinstance(transition, dict) or set(transition) != {"schemaVersion", "combatOutcome", "rawGameOutcome", "pre", "post"}:
                    raise ValueError("missing full transition snapshot")
                if transition["schemaVersion"] != SCHEMA_VERSION:
                    raise ValueError("transition snapshot schema mismatch")
                combat_outcome = _integer(transition["combatOutcome"], "combatOutcome")
                raw_outcome = _integer(transition["rawGameOutcome"], "rawGameOutcome")
                # exitBattle invokes the RAW observer before it assigns a
                # loss or calls regainControl for a victory.  Native
                # GameOutcome::UNDECIDED is therefore the only valid RAW
                # boundary value, and its enum value is 1.
                if combat_outcome not in outcomes or raw_outcome != 1:
                    raise ValueError("invalid combat/raw GameOutcome")
                validate_state(transition["pre"], f"line {line_number} pre")
                validate_state(transition["post"], f"line {line_number} post")
                if row["runValid"] and (combat_outcome == 0 or row["quarantineReason"]):
                    raise ValueError("valid row has unresolved outcome or quarantine reason")
                if not row["runValid"] and not row["quarantineReason"]:
                    raise ValueError("invalid row is missing quarantine reason")
                if capture_count != 1 or row["captureStatus"] != "exactly_one":
                    raise ValueError("full transition snapshot requires exactly one capture")
                outcomes[combat_outcome] += 1
                quarantined += not row["runValid"]
                rows += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid transition row at line {line_number}: {exc}") from exc
    if rows != _integer(integrity["rows"], "integrity.rows"):
        raise ValueError("manifest row count mismatch")
    if not seeds.issubset(expected_seeds):
        raise ValueError("corpus contains a seed outside seedSpec")
    if len(seeds) != completed_integrity:
        raise ValueError("completed source seed count does not match corpus")
    if intervention is not None:
        declared_rows = intervention["activeLizardRows"]
        if not isinstance(declared_rows, list):
            raise ValueError("activeLizardRows must be an array")
        declared_keys = set()
        for item in declared_rows:
            if (not isinstance(item, dict) or set(item) != {"sourceSeed", "fightIdx", "activeLizard"}
                    or item["activeLizard"] is not True):
                raise ValueError("activeLizardRows entry is malformed")
            key = (_integer(item["sourceSeed"], "activeLizardRows.sourceSeed"),
                   _integer(item["fightIdx"], "activeLizardRows.fightIdx"))
            if key in declared_keys:
                raise ValueError("duplicate active Lizard intervention identity")
            declared_keys.add(key)
        if declared_keys != intervention_keys:
            raise ValueError("activeLizardRows do not exactly cover the emitted intervention rows")
    if quarantined > rows:
        raise ValueError("quarantine accounting is impossible")
    return {"rows": rows, "sourceSeeds": len(seeds),
            "requestedSeeds": requested_integrity,
            "completedSeeds": completed_integrity,
            "quarantinedSeeds": quarantined_integrity,
            "outcomes": outcomes, "quarantinedRows": quarantined,
            "teacherId": teacher_id}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--no-data-check", action="store_true")
    args = parser.parse_args()
    result = validate_corpus(json.loads(Path(args.manifest).read_text(encoding="utf-8")),
                             verify_data=not args.no_data_check)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
