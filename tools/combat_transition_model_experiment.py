#!/usr/bin/env python3
"""Audit and compare models for the frozen combat-transition corpus.

This is an offline research tool.  It deliberately keeps the raw transition
corpus out of Git and never consumes a seed or simulator executable.  The
workflow is:

  audit  -> corpus_audit.json + split_manifest.json
  prepare -> prepared.npz (TRAIN-only split metadata is already frozen)
  fit    -> validation selection, equal TRAIN+VALIDATION refits, corrected TEST rerun

The split is by source seed.  The only model inputs are the fields in
combat_predictor_input_v1; transition.post is used only to form labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

try:
    from tools.combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA, validate_predictor_input,
    )
    from tools.combat_transition_contract import validate_corpus
except ModuleNotFoundError:  # direct invocation from tools/
    from combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA, validate_predictor_input,
    )
    from combat_transition_contract import validate_corpus


SCRIPT_SCHEMA = "combat_transition_model_experiment_v1"
SPLIT_SCHEMA = "combat_transition_model_split_v1"
MODEL_SCHEMA = "combat_transition_model_evidence_v1"
TRANSITION_SCHEMA = "combat_transition_v1"
ROW_SCHEMA = "combat_transition_row_v2"
WIN = 1
DEATH = 2
MAX_CARDS = 128
MAX_RELICS = 64
GLOBAL_FIELDS = (
    "characterClass", "ascension", "act", "floor", "curHp", "maxHp", "gold",
    "encounter", "roomClass", "lastRoom", "potionCount", "potionCapacity",
    "potionKeepValue", "isBurningElite",
)
CATEGORICAL_GLOBAL_FIELDS = ("characterClass", "encounter", "roomClass", "lastRoom")
CONTINUOUS_GLOBAL_FIELDS = tuple(
    field for field in GLOBAL_FIELDS if field not in CATEGORICAL_GLOBAL_FIELDS
)
ROOM_NAMES = {
    0: "SHOP", 1: "REST", 2: "EVENT", 3: "ELITE", 4: "NORMAL",
    5: "TREASURE", 6: "BOSS", 7: "BOSS_TREASURE", 8: "NONE", 9: "INVALID",
}
EXCLUDED_RNG_FIELDS = {"combatRng"}


def _canonical_constant(header: Path, name: str) -> int:
    text = header.read_text(encoding="utf-8")
    match = re.search(rf"\bconstexpr\s+int\s+{re.escape(name)}\s*=\s*(\d+)\s*;", text)
    if match is None:
        raise RuntimeError(f"canonical constant {name} not found in {header}")
    return int(match.group(1))


def _canonical_enum_count(header: Path, enum_name: str) -> int:
    text = header.read_text(encoding="utf-8")
    match = re.search(rf"enum\s+class\s+{re.escape(enum_name)}\b[^{{]*{{(.*?)}}\s*;", text, re.S)
    if match is None:
        raise RuntimeError(f"canonical enum {enum_name} not found in {header}")
    members = re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*(?:=\s*(-?\d+))?\s*,?\s*(?://.*)?$", match.group(1), re.M)
    if not members:
        raise RuntimeError(f"canonical enum {enum_name} has no members in {header}")
    values: list[int] = []
    next_value = 0
    for _, explicit in members:
        if explicit:
            next_value = int(explicit)
        values.append(next_value)
        next_value += 1
    if values != list(range(len(values))):
        raise RuntimeError(f"canonical enum {enum_name} is not contiguous from zero")
    return len(values)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUN_FEATURES_HEADER = _REPO_ROOT / "apps/one_combat/run_features.h"
CARD_COUNT = _canonical_constant(_RUN_FEATURES_HEADER, "kNumCardIds")
RELIC_COUNT = _canonical_constant(_RUN_FEATURES_HEADER, "kNumRelics")
POTION_COUNT = _canonical_constant(_RUN_FEATURES_HEADER, "kNumPotions")
_CHARACTER_CLASS_COUNT = _canonical_enum_count(
    _REPO_ROOT / "include/constants/CharacterClasses.h", "CharacterClass"
) - 1  # INVALID is the terminal sentinel, not a playable class.
_ENCOUNTER_COUNT = _canonical_enum_count(
    _REPO_ROOT / "include/constants/MonsterEncounters.h", "MonsterEncounter"
)
_ROOM_COUNT = _canonical_enum_count(_REPO_ROOT / "include/constants/Rooms.h", "Room")
GLOBAL_CATEGORY_COUNTS = {
    "characterClass": _CHARACTER_CLASS_COUNT,
    "encounter": _ENCOUNTER_COUNT,
    "roomClass": _ROOM_COUNT,
    "lastRoom": _ROOM_COUNT,
}
# These are historical implementation bounds, retained only to quantify the
# reviewer-requested impact of the stale representation.  They are not model
# domains and must not be used for encoding or validation.
PREVIOUS_ENTITY_COUNTS = {"cards": 371, "relics": 128, "potions": 44}


def _validate_entity_domains(predictor_input: dict) -> None:
    """Reject IDs outside the canonical producer/model domains."""
    for token in predictor_input["cards"]:
        value = int(token["cardId"])
        if not 0 <= value < CARD_COUNT:
            raise ValueError(f"cardId {value} is outside canonical domain [0, {CARD_COUNT})")
    for token in predictor_input["relics"]:
        value = int(token["relicId"])
        if not 0 <= value < RELIC_COUNT:
            raise ValueError(f"relicId {value} is outside canonical domain [0, {RELIC_COUNT})")
    for token in predictor_input["potions"]:
        value = int(token["potionId"])
        if not 0 <= value < POTION_COUNT:
            raise ValueError(f"potionId {value} is outside canonical domain [0, {POTION_COUNT})")
    globals_value = predictor_input["globals"]
    for field, count in GLOBAL_CATEGORY_COUNTS.items():
        value = int(globals_value[field])
        if not 0 <= value < count:
            raise ValueError(f"{field} {value} is outside canonical category domain [0, {count})")


def _entity_domain_impact() -> dict:
    return {
        name: {
            "observedMin": None,
            "observedMax": None,
            "previousFlatTruncatedTokens": 0,
            "previousFlatTruncatedRows": set(),
            "previousNeuralClampedTokens": 0,
            "previousNeuralClampedRows": set(),
        }
        for name in PREVIOUS_ENTITY_COUNTS
    }


def _record_entity_domain_impact(impact: dict, row_number: int, name: str,
                                 values: Iterable[int]) -> None:
    values = [int(value) for value in values]
    if not values:
        return
    item = impact[name]
    item["observedMin"] = min(values) if item["observedMin"] is None else min(item["observedMin"], min(values))
    item["observedMax"] = max(values) if item["observedMax"] is None else max(item["observedMax"], max(values))
    affected = [value for value in values if value >= PREVIOUS_ENTITY_COUNTS[name]]
    item["previousFlatTruncatedTokens"] += len(affected)
    item["previousNeuralClampedTokens"] += len(affected)
    if affected:
        item["previousFlatTruncatedRows"].add(row_number)
        item["previousNeuralClampedRows"].add(row_number)


def _finalize_entity_domain_impact(impact: dict) -> dict:
    result = {}
    for name, item in impact.items():
        result[name] = {
            "canonicalDomainSize": {"cards": CARD_COUNT, "relics": RELIC_COUNT,
                                     "potions": POTION_COUNT}[name],
            "previousDomainSize": PREVIOUS_ENTITY_COUNTS[name],
            "observedMin": item["observedMin"],
            "observedMax": item["observedMax"],
            "previousImplementation": {
                "flatTruncatedTokens": item["previousFlatTruncatedTokens"],
                "flatTruncatedRows": len(item["previousFlatTruncatedRows"]),
                "neuralClampedTokensThatCollided": item["previousNeuralClampedTokens"],
                "neuralClampedRows": len(item["previousNeuralClampedRows"]),
            },
        }
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"blank row at {path}:{line_number}")
            yield json.loads(line)


def split_for_seed(seed: int) -> str:
    """Stable 80/10/10 bucket; source seed is the only split input."""
    digest = hashlib.sha256(f"combat-transition-model-v1:{int(seed)}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    return "train" if bucket < 80 else "validation" if bucket < 90 else "test"


def split_manifest(seeds: Iterable[int], corpus_manifest: dict) -> dict:
    groups = {str(int(seed)): split_for_seed(int(seed)) for seed in sorted(set(seeds))}
    by_split = {name: sorted(int(seed) for seed, split in groups.items() if split == name)
                for name in ("train", "validation", "test")}
    return {
        "schemaVersion": SPLIT_SCHEMA,
        "rule": 'SHA256("combat-transition-model-v1:" + sourceSeed); first 8 bytes interpreted big-endian modulo 100; <80 train, <90 validation, else test',
        "groupKey": "sourceSeed",
        "sourceSeedSpec": corpus_manifest["seedSpec"],
        "excludedQuarantinedSeeds": sorted(
            int(seed) for seed in corpus_manifest.get("quarantined", [])
        ),
        "members": by_split,
        "counts": {name: len(values) for name, values in by_split.items()},
    }


def _range_set(seed_spec: dict) -> set[int]:
    return set(range(int(seed_spec["start"]), int(seed_spec["start"]) + int(seed_spec["count"])))


def shard_inventory(shard_root: Path, final_manifest: dict) -> tuple[list[dict], set[int], set[int]]:
    """Validate every retained shard and reconcile its source ranges.

    The block-17 process failure has no valid block manifest; the runner's
    single-seed salvage manifests cover all recoverable sources, while the
    final provenance records the one quarantined source.
    """
    manifests = sorted(
        list((shard_root / "blocks").glob("*.jsonl.manifest.json"))
        + list((shard_root / "seeds").glob("*.jsonl.manifest.json"))
    )
    if not manifests:
        raise ValueError(f"no shard manifests under {shard_root}")
    entries: list[dict] = []
    covered: set[int] = set()
    requested_ranges: set[int] = set()
    identities: set[tuple] = set()
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validate_corpus(manifest)
        seed_set = _range_set(manifest["seedSpec"])
        if seed_set & requested_ranges:
            overlap = sorted(seed_set & requested_ranges)[:8]
            raise ValueError(f"overlapping shard source seeds near {overlap}")
        requested_ranges.update(seed_set)
        actual_path = Path(manifest["csv"]["path"])
        if not actual_path.is_file():
            raise ValueError(f"missing shard data {actual_path}")
        if set(result["outcomes"]) != {0, 1, 2}:
            raise ValueError(f"unexpected outcome keys in {manifest_path}")
        teacher = manifest["combatTeacher"]
        identity = (
            manifest["producerGitSha"], manifest["producerExecutableSha256"],
            teacher["teacher_id"], manifest["predictorInputSchemaVersion"],
            manifest["predictorInputFieldSchemaHash"], manifest["rowSchemaVersion"],
        )
        identities.add(identity)
        if result["quarantinedRows"]:
            raise ValueError(f"shard has quarantined rows: {manifest_path}")
        covered.update(seed_set)
        entries.append({
            "manifest": str(manifest_path.resolve()),
            "manifestSha256": sha256(manifest_path),
            "data": str(actual_path.resolve()),
            "dataSha256": manifest["csv"]["sha256"],
            "seedSpec": manifest["seedSpec"],
            "rows": result["rows"],
            "completedSeeds": result["completedSeeds"],
            "quarantinedSeeds": result["quarantinedSeeds"],
            "outcomes": result["outcomes"],
            "teacherId": teacher["teacher_id"],
        })
    if len(identities) != 1:
        raise ValueError(f"mixed shard provenance identities: {len(identities)}")
    final_requested = _range_set(final_manifest["seedSpec"])
    quarantined = set(int(x) for x in final_manifest.get("quarantined", []))
    # The merged manifest has no quarantine list; its companion provenance does.
    if not quarantined:
        provenance = Path(final_manifest["csv"]["path"]).with_suffix(".jsonl.provenance.json")
        if provenance.is_file():
            p = json.loads(provenance.read_text(encoding="utf-8"))
            quarantined = {int(x) for x in p.get("quarantined", {})}
    expected_completed = final_requested - quarantined
    if covered != expected_completed:
        missing = sorted(expected_completed - covered)[:8]
        extra = sorted(covered - expected_completed)[:8]
        raise ValueError(f"shard coverage mismatch missing={missing} extra={extra}")
    if requested_ranges - final_requested:
        raise ValueError("shard source range exceeds final manifest")
    return entries, covered, quarantined


def union_inventory(final_manifest: dict) -> tuple[list[dict], set[int], set[int]]:
    """Validate the scopes of a `ctm_corpus_adapter.py union` corpus (#418 retrain).

    A union has no shards of its own: each assembled scope keeps its shard
    manifests under its own blocks/. Requested sources are the scopes' seed
    ranges (not the gaps between scopes); covered sources are the seeds the
    scopes' shards completed. `audit` derives the completed sources from the
    union rows, since the union drops unsupported rows, and quarantines every
    other requested source (generator stalls and seeds whose rows were all
    dropped).
    """
    entries: list[dict] = []
    requested: set[int] = set()
    covered: set[int] = set()
    identity = (final_manifest["producerGitSha"], final_manifest["producerExecutableSha256"],
                final_manifest["combatTeacher"]["teacher_id"])
    for scope, info in sorted(final_manifest["ctmCorpusAdapter"]["union"].items()):
        path = Path(info["manifest"])
        if sha256(path) != info["manifestSha256"]:
            raise ValueError(f"union scope {scope} manifest changed")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("forcedSetup") != scope or manifest["seedSpec"] != info["seedSpec"]:
            raise ValueError(f"union scope {scope} manifest differs from the union record")
        if (manifest["producerGitSha"], manifest["producerExecutableSha256"],
                manifest["combatTeacher"]["teacher_id"]) != identity:
            raise ValueError(f"union scope {scope} has another producer/teacher identity")
        scope_entries, scope_covered, _ = shard_inventory(path.parent, manifest)
        seeds = _range_set(manifest["seedSpec"])
        if seeds & requested:
            raise ValueError(f"union scope {scope} overlaps another scope")
        requested |= seeds
        covered |= scope_covered
        entries += [dict(entry, scope=scope) for entry in scope_entries]
    return entries, requested, covered


def _band(value: float, edges: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def _floor_band(floor: int) -> str:
    return _band(float(floor), (16, 31, 46), ("1-15", "16-30", "31-45", "46+"))


def _hp_band(frac: float) -> str:
    return _band(frac, (0.25, 0.50, 0.75, 1.01), ("<25%", "25-49%", "50-74%", "75-100%"))


def _deck_band(size: int) -> str:
    return _band(float(size), (11, 16, 21, 31), ("0-10", "11-15", "16-20", "21-30", "31+"))


def _inc(table: dict, key: object, amount: int = 1) -> None:
    key = str(key)
    table[key] = int(table.get(key, 0)) + amount


def _stats(values: list[int]) -> dict:
    if not values:
        return {"min": None, "median": None, "mean": None, "p95": None, "max": None}
    values = sorted(values)
    return {
        "min": int(values[0]), "median": float(statistics.median(values)),
        "mean": float(statistics.fmean(values)),
        "p95": float(np.percentile(values, 95, method="linear")), "max": int(values[-1]),
    }


def persistent_change_flags(pre: dict, post: dict) -> tuple[dict, Counter, Counter]:
    flags = {
        "hp_changed": pre["curHp"] != post["curHp"],
        "max_hp_changed": pre["maxHp"] != post["maxHp"],
        "gold_changed": pre["gold"] != post["gold"],
        "potion_count_changed": pre["potionCount"] != post["potionCount"],
        "any_potion_slot_changed": pre["potions"] != post["potions"],
        "relic_data_changed": False,
        "multiple_relic_counters_changed": False,
        "deck_misc_changed": False,
        "card_upgrade_or_deck_structure_changed": False,
        "stolen_gold_changed": pre["stolenGold"] != post["stolenGold"],
        "smoke_bomb_used": (not pre["smokeBombUsed"]) and post["smokeBombUsed"],
        "other_persistent_field_changed": False,
    }
    relic_ids: Counter = Counter()
    for before, after in zip(pre["relics"], post["relics"]):
        if before["id"] == after["id"] and before["data"] != after["data"]:
            flags["relic_data_changed"] = True
            relic_ids[int(before["id"])] += 1
    flags["multiple_relic_counters_changed"] = sum(relic_ids.values()) >= 2
    before_tokens = Counter((c["id"], c["upgraded"], c.get("bottleBinding", -1), c["misc"]) for c in pre["deck"])
    after_tokens = Counter((c["id"], c["upgraded"], c.get("bottleBinding", -1), c["misc"]) for c in post["deck"])
    before_structure = Counter((c["id"], c["upgraded"], c.get("bottleBinding", -1)) for c in pre["deck"])
    after_structure = Counter((c["id"], c["upgraded"], c.get("bottleBinding", -1)) for c in post["deck"])
    before_misc = defaultdict(Counter)
    after_misc = defaultdict(Counter)
    for card in pre["deck"]: before_misc[int(card["id"])][int(card["misc"])] += 1
    for card in post["deck"]: after_misc[int(card["id"])][int(card["misc"])] += 1
    flags["deck_misc_changed"] = any(
        sum(before_misc[item_id].values()) == sum(after_misc[item_id].values())
        and before_misc[item_id] != after_misc[item_id]
        for item_id in set(before_misc) | set(after_misc)
    )
    flags["card_upgrade_or_deck_structure_changed"] = before_structure != after_structure
    card_ids = Counter()
    changed_card_ids = {int(key[0]) for key in (after_tokens - before_tokens)}
    changed_card_ids.update(
        int(item_id)
        for item_id in set(before_misc) | set(after_misc)
        if before_misc[item_id] != after_misc[item_id]
    )
    for item_id in changed_card_ids:
        card_ids[item_id] += 1
    excluded = {"curHp", "maxHp", "gold", "potionCount", "potions", "relics", "deck", "stolenGold", "smokeBombUsed"}
    for key in set(pre) | set(post):
        if key in excluded or key in EXCLUDED_RNG_FIELDS:
            continue
        if pre.get(key) != post.get(key):
            flags["other_persistent_field_changed"] = True
    return flags, relic_ids, card_ids


def audit(args: argparse.Namespace) -> None:
    final_manifest = json.loads(Path(args.corpus_manifest).read_text(encoding="utf-8"))
    corpus_path = Path(final_manifest["csv"]["path"])
    if not corpus_path.is_file():
        raise ValueError(f"corpus does not exist: {corpus_path}")
    union = final_manifest.get("forcedSetup") == "union"
    # act4_fork shards cover seeds that ended before Act 4 and wrote no rows.
    rows_define_completed = union or final_manifest.get("forcedSetup") == "act4_fork"
    if union:
        # Each union scope names its own shards; --shard-root is not used.
        shard_entries, expected, covered = union_inventory(final_manifest)
    else:
        if not args.shard_root:
            raise ValueError("--shard-root is required")
        shard_entries, completed_seeds, quarantined = shard_inventory(Path(args.shard_root), final_manifest)
        expected = _range_set(final_manifest["seedSpec"])
        if completed_seeds | quarantined != expected or completed_seeds & quarantined:
            raise ValueError("final source accounting does not reconcile")
    source_rows: Counter = Counter()
    source_changes: dict[str, set[int]] = defaultdict(set)
    coverage = {name: Counter() for name in (
        "act", "roomClass", "encounter", "floorBand", "startingHpFractionBand",
        "burningElite", "potionCount", "deckSizeBand")}
    changes = Counter()
    relic_changes: Counter = Counter()
    card_changes: Counter = Counter()
    outcomes: Counter = Counter()
    death_sources: set[int] = set()
    entity_impact = _entity_domain_impact()
    rows = 0
    max_cards = 0
    max_relics = 0
    capture_status = Counter()
    run_valid = Counter()
    for row in iter_rows(corpus_path):
        rows += 1
        seed = int(row["sourceSeed"])
        source_rows[seed] += 1
        outcomes[str(row["transition"]["combatOutcome"])] += 1
        capture_status[row["captureStatus"]] += 1
        run_valid[str(bool(row["runValid"]))] += 1
        pi = row["predictorInput"]
        validate_predictor_input(pi)
        _validate_entity_domains(pi)
        _record_entity_domain_impact(
            entity_impact, rows, "cards", (card["cardId"] for card in pi["cards"])
        )
        _record_entity_domain_impact(
            entity_impact, rows, "relics", (relic["relicId"] for relic in pi["relics"])
        )
        _record_entity_domain_impact(
            entity_impact, rows, "potions", (potion["potionId"] for potion in pi["potions"])
        )
        g = pi["globals"]
        hp_frac = float(g["curHp"]) / max(float(g["maxHp"]), 1.0)
        deck_size = len(pi["cards"])
        max_cards = max(max_cards, deck_size)
        max_relics = max(max_relics, len(pi["relics"]))
        _inc(coverage["act"], g["act"])
        _inc(coverage["roomClass"], ROOM_NAMES.get(int(g["roomClass"]), str(g["roomClass"])))
        _inc(coverage["encounter"], g["encounter"])
        _inc(coverage["floorBand"], _floor_band(int(g["floor"])))
        _inc(coverage["startingHpFractionBand"], _hp_band(hp_frac))
        _inc(coverage["burningElite"], g["isBurningElite"])
        _inc(coverage["potionCount"], g["potionCount"])
        _inc(coverage["deckSizeBand"], _deck_band(deck_size))
        if int(row["transition"]["combatOutcome"]) == DEATH:
            death_sources.add(seed)
        flags, relic_ids, card_ids = persistent_change_flags(
            row["transition"]["pre"], row["transition"]["post"])
        for name, changed in flags.items():
            changes[name] += int(bool(changed))
            if changed: source_changes[name].add(seed)
        relic_changes.update(relic_ids)
        card_changes.update(card_ids)
    if rows != int(final_manifest["integrity"]["rows"]):
        raise ValueError(f"merged row count mismatch {rows}")
    if rows_define_completed:
        if not union:
            covered = completed_seeds
        completed_seeds = set(source_rows)
        if not completed_seeds <= covered or len(completed_seeds) != int(final_manifest["integrity"]["completedSeeds"]):
            raise ValueError("union rows do not reconcile with the scopes' validated shards")
        quarantined = expected - completed_seeds
    split = split_manifest(completed_seeds, final_manifest | {"quarantined": sorted(quarantined)})
    if set(source_rows) != completed_seeds:
        raise ValueError("merged corpus sources do not equal validated shard sources")
    if max_cards > MAX_CARDS or max_relics > MAX_RELICS:
        raise ValueError(f"entity padding too small cards={max_cards} relics={max_relics}")
    audit_report = {
        "schemaVersion": SCRIPT_SCHEMA,
        "corpus": {
            "manifest": str(Path(args.corpus_manifest).resolve()),
            "manifestSha256": sha256(Path(args.corpus_manifest)),
            "path": str(corpus_path.resolve()),
            "sha256": sha256(corpus_path),
            "bytes": corpus_path.stat().st_size,
            "producerGitSha": final_manifest["producerGitSha"],
            "producerExecutableSha256": final_manifest["producerExecutableSha256"],
            "teacherId": final_manifest["combatTeacher"]["teacher_id"],
            "predictorInputSchemaVersion": final_manifest["predictorInputSchemaVersion"],
            "predictorInputFieldSchemaHash": final_manifest["predictorInputFieldSchemaHash"],
            "rowSchemaVersion": final_manifest["rowSchemaVersion"],
            "seedSpec": final_manifest["seedSpec"],
            "collectionIntegrity": final_manifest["integrity"],
        },
        "shards": {
            "count": len(shard_entries),
            "validated": len(shard_entries),
            "entries": shard_entries,
        },
        "sourcesRows": {
            "requestedSources": len(expected), "completedSources": len(completed_seeds),
            "validSources": len(completed_seeds), "quarantinedSources": len(quarantined),
            "quarantinedSeedIds": sorted(quarantined), "totalFights": rows,
            "rowsPerSource": _stats(list(source_rows.values())),
            "wins": int(outcomes[str(WIN)]), "deaths": int(outcomes[str(DEATH)]),
            "distinctSourcesContainingDeath": len(death_sources),
            "captureStatus": dict(capture_status), "runValid": dict(run_valid),
        },
        "stateCoverage": {key: dict(sorted(value.items())) for key, value in coverage.items()},
        "entityDomains": {
            "canonicalSource": str(_RUN_FEATURES_HEADER.resolve()),
            "canonicalDomainSizes": {"cards": CARD_COUNT, "relics": RELIC_COUNT,
                                      "potions": POTION_COUNT},
            "observed": _finalize_entity_domain_impact(entity_impact),
        },
        "persistentChanges": {
            "definitions": {
                "relic_data_changed": "at least one same-id, same-order relic has a changed data value",
                "multiple_relic_counters_changed": "at least two relic data values changed",
                "deck_misc_changed": "multiset of (card id, misc) changed",
                "card_upgrade_or_deck_structure_changed": "multiset of (card id, upgraded, bottleBinding) changed",
                "smoke_bomb_used": "pre false and post true",
                "other_persistent_field_changed": "any non-RNG state key outside the listed direct/deck/relic/potion fields changed",
            },
            "rowCounts": dict(changes),
            "sourceCounts": {name: len(values) for name, values in sorted(source_changes.items())},
            "mostCommonChangedRelicIds": [{"id": int(k), "rows": int(v)} for k, v in relic_changes.most_common(20)],
            "mostCommonChangedCardIds": [{"id": int(k), "rows": int(v)} for k, v in card_changes.most_common(20)],
            "maxEntityLengths": {"cards": max_cards, "relics": max_relics},
        },
        "split": split,
        "notes": [
            "All rows are valid decided combats; transition.post is used only for labels and audit deltas.",
            "combatRng is intentionally excluded from persistent-change counts because it is an oracle-only hidden field.",
            "No TEST performance is computed by audit.",
        ],
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_dump(out / "corpus_audit.json", audit_report)
    json_dump(out / "split_manifest.json", split)
    (out / "split_manifest.sha256").write_text(sha256(out / "split_manifest.json") + "\n", encoding="utf-8")
    print(json.dumps({
        "validatedShards": len(shard_entries), "requestedSources": len(expected),
        "completedSources": len(completed_seeds), "quarantinedSources": len(quarantined),
        "rows": rows, "wins": int(outcomes[str(WIN)]), "deaths": int(outcomes[str(DEATH)]),
        "output": str(out.resolve()),
    }, indent=2))


def _flat_names() -> list[str]:
    names = [f"global.{field}" for field in CONTINUOUS_GLOBAL_FIELDS]
    names += [f"global_cat.{field}.{value}"
              for field in CATEGORICAL_GLOBAL_FIELDS
              for value in range(GLOBAL_CATEGORY_COUNTS[field])]
    names += [f"card_count.{i}" for i in range(CARD_COUNT)]
    names += [f"card_upgraded_count.{i}" for i in range(CARD_COUNT)]
    names += [f"card_misc_sum.{i}" for i in range(CARD_COUNT)]
    names += [f"bottle.{slot}.card.{i}" for slot in range(3) for i in range(CARD_COUNT)]
    names += [f"relic_present.{i}" for i in range(RELIC_COUNT)]
    names += [f"relic_data.{i}" for i in range(RELIC_COUNT)]
    names += [f"relic_order.{i}" for i in range(RELIC_COUNT)]
    names += [f"potion.{slot}.id.{i}" for slot in range(5) for i in range(POTION_COUNT)]
    names += ["derived.deck_size", "derived.relic_count"]
    return names


def _encode_row(row: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, float, dict]:
    pi = row["predictorInput"]
    validate_predictor_input(pi)
    _validate_entity_domains(pi)
    g = pi["globals"]
    globals_continuous = np.asarray([
        float(g[field]) for field in CONTINUOUS_GLOBAL_FIELDS
    ], dtype=np.float32)
    global_categories = np.asarray([
        int(g[field]) for field in CATEGORICAL_GLOBAL_FIELDS
    ], dtype=np.int64)
    # The fixed padding is a contract-domain bound; canonical token order is retained.
    cards = np.zeros((MAX_CARDS, 4), dtype=np.int16)
    card_mask = np.zeros(MAX_CARDS, dtype=np.bool_)
    for i, card in enumerate(pi["cards"]):
        cards[i] = (int(card["cardId"]), int(bool(card["upgraded"])), int(card["misc"]), int(card["bottleBinding"]) + 1)
        card_mask[i] = True
    relics = np.zeros((MAX_RELICS, 3), dtype=np.int16)
    relic_mask = np.zeros(MAX_RELICS, dtype=np.bool_)
    for i, relic in enumerate(pi["relics"]):
        relics[i] = (int(relic["relicId"]), int(relic["data"]), int(relic["orderIndex"]))
        relic_mask[i] = True
    potions = np.asarray([[int(p["slot"]), int(p["potionId"])] for p in pi["potions"]], dtype=np.int16)
    outcome = int(row["transition"]["combatOutcome"])
    post = row["transition"]["post"]
    y_hp = float(post["curHp"]) / max(float(post["maxHp"]), 1.0) if outcome == WIN else np.nan
    context = {
        "sourceSeed": int(row["sourceSeed"]), "fightIdx": int(row["fightIdx"]),
        "act": int(g["act"]), "roomClass": int(g["roomClass"]), "encounter": int(g["encounter"]),
        "floor": int(g["floor"]), "preHpFrac": float(g["curHp"]) / max(float(g["maxHp"]), 1.0),
        "isBurningElite": int(bool(g["isBurningElite"])), "potionCount": int(g["potionCount"]),
        "deckSize": len(pi["cards"]), "split": split_for_seed(int(row["sourceSeed"])),
    }
    return (globals_continuous, global_categories, cards, relics, potions,
            card_mask, relic_mask, int(outcome == WIN), y_hp, context)


def _flatten(globals_continuous: np.ndarray, global_categories: np.ndarray,
             cards: np.ndarray, relics: np.ndarray, potions: np.ndarray,
             card_mask: np.ndarray, relic_mask: np.ndarray) -> np.ndarray:
    out = np.zeros(len(_flat_names()), dtype=np.float32)
    cursor = 0
    out[cursor:cursor + len(CONTINUOUS_GLOBAL_FIELDS)] = globals_continuous
    cursor += len(CONTINUOUS_GLOBAL_FIELDS)
    for field, value in zip(CATEGORICAL_GLOBAL_FIELDS, global_categories):
        if not 0 <= int(value) < GLOBAL_CATEGORY_COUNTS[field]:
            raise ValueError(f"{field} {value} is outside canonical category domain")
        out[cursor + int(value)] = 1.0
        cursor += GLOBAL_CATEGORY_COUNTS[field]
    card_ids = cards[:, 0]; valid = card_mask
    for card_id in card_ids[valid]:
        if 0 <= card_id < CARD_COUNT: out[cursor + int(card_id)] += 1
    cursor += CARD_COUNT
    for card_id, upgraded in cards[valid, :2]:
        if 0 <= card_id < CARD_COUNT and upgraded: out[cursor + int(card_id)] += 1
    cursor += CARD_COUNT
    for card_id, misc in cards[valid][:, (0, 2)]:
        if 0 <= card_id < CARD_COUNT: out[cursor + int(card_id)] += misc
    cursor += CARD_COUNT
    for card_id, _, _, bottle in cards[valid]:
        if bottle and 0 <= card_id < CARD_COUNT:
            out[cursor + (int(bottle) - 1) * CARD_COUNT + int(card_id)] = 1
    cursor += 3 * CARD_COUNT
    rvalid = relic_mask
    for relic_id, data, order in relics[rvalid]:
        if 0 <= relic_id < RELIC_COUNT:
            out[cursor + int(relic_id)] = 1
            out[cursor + RELIC_COUNT + int(relic_id)] = data
            out[cursor + 2 * RELIC_COUNT + int(relic_id)] = order
    cursor += 3 * RELIC_COUNT
    for slot, potion_id in potions:
        if 0 <= slot < 5 and 0 <= potion_id < POTION_COUNT:
            out[cursor + int(slot) * POTION_COUNT + int(potion_id)] = 1
    cursor += 5 * POTION_COUNT
    out[cursor] = float(valid.sum()); out[cursor + 1] = float(rvalid.sum())
    return out


def prepare(args: argparse.Namespace) -> None:
    audit_report = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    split = audit_report["split"]
    corpus_path = Path(audit_report["corpus"]["path"])
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    globals_list: list[np.ndarray] = []; global_categories_list: list[np.ndarray] = []
    cards_list: list[np.ndarray] = []; card_masks: list[np.ndarray] = []
    relics_list: list[np.ndarray] = []; relic_masks: list[np.ndarray] = []; potions_list: list[np.ndarray] = []
    flat_list: list[np.ndarray] = []; y_win: list[int] = []; y_hp: list[float] = []
    contexts: dict[str, list[int]] = defaultdict(list)
    for row in iter_rows(corpus_path):
        g, gc, c, r, p, cm, rm, win, hp, context = _encode_row(row)
        globals_list.append(g); global_categories_list.append(gc)
        cards_list.append(c); card_masks.append(cm); relics_list.append(r); relic_masks.append(rm); potions_list.append(p)
        flat_list.append(_flatten(g, gc, c, r, p, cm, rm)); y_win.append(win); y_hp.append(hp)
        for key, value in context.items():
            if key != "split": contexts[key].append(value)
        contexts["split_id"].append({"train": 0, "validation": 1, "test": 2}[context["split"]])
    arrays = {
        "globals_continuous": np.stack(globals_list), "global_categories": np.stack(global_categories_list),
        "cards": np.stack(cards_list), "card_mask": np.stack(card_masks),
        "relics": np.stack(relics_list), "relic_mask": np.stack(relic_masks), "potions": np.stack(potions_list),
        "flat": np.stack(flat_list), "y_win": np.asarray(y_win, dtype=np.int8),
        "y_hp": np.asarray(y_hp, dtype=np.float32),
    }
    arrays.update({key: np.asarray(value) for key, value in contexts.items()})
    np.savez(out / "prepared.npz", **arrays)
    prepared_manifest = {
        "schemaVersion": SCRIPT_SCHEMA, "audit": str(Path(args.audit).resolve()),
        "auditSha256": sha256(Path(args.audit)), "corpusSha256": audit_report["corpus"]["sha256"],
        "splitManifest": split, "featureSchema": {"flatNames": _flat_names(), "flatCount": len(_flat_names()),
        "globalsContinuous": list(CONTINUOUS_GLOBAL_FIELDS),
        "globalsCategorical": {field: list(range(GLOBAL_CATEGORY_COUNTS[field]))
                                for field in CATEGORICAL_GLOBAL_FIELDS},
        "cards": "cardId/upgraded/misc/bottleBinding padded in canonical order",
        "relics": "relicId/data/orderIndex padded in acquisition order", "potions": "slot/potionId"},
        "rows": int(len(y_win)), "counts": {str(i): int((arrays["split_id"] == i).sum()) for i in range(3)},
        "entityPadding": {"cards": MAX_CARDS, "relics": MAX_RELICS},
        "entityDomains": {"cards": CARD_COUNT, "relics": RELIC_COUNT, "potions": POTION_COUNT},
    }
    json_dump(out / "prepared_manifest.json", prepared_manifest)
    print(json.dumps({"rows": len(y_win), "flatFeatures": len(_flat_names()), "output": str(out.resolve())}, indent=2))


def _binary_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    if len(y) == 0: return {"n": 0, "brier": None, "logloss": None, "auc": None}
    return {"n": int(len(y)), "brier": float(brier_score_loss(y, p)),
            "logloss": float(log_loss(y, p, labels=[0, 1])),
            "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None}


def _reg_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    if len(y) == 0: return {"n": 0, "mae": None, "rmse": None, "bias": None}
    e = p - y
    return {"n": int(len(y)), "mae": float(np.mean(np.abs(e))),
            "rmse": float(np.sqrt(np.mean(e * e))), "bias": float(np.mean(e))}


def _calibration(y: np.ndarray, p: np.ndarray) -> list[dict]:
    out = []
    for low in np.linspace(0, .9, 10):
        high = low + .1
        mask = (p >= low) & ((p < high) if high < 1 else (p <= high))
        if mask.any(): out.append({"bin": f"{low:.1f}-{high:.1f}", "n": int(mask.sum()),
                                   "predicted": float(p[mask].mean()), "observed": float(y[mask].mean())})
    return out


def _slice_metrics(data: dict[str, np.ndarray], p: np.ndarray, hp: np.ndarray, minimum: int = 50) -> dict:
    result: dict = {}
    for field in ("act", "roomClass", "encounter", "preHpFrac"):
        groups: dict[str, np.ndarray] = {}
        if field == "preHpFrac":
            labels = np.asarray([_hp_band(float(v)) for v in data[field]])
        else:
            labels = data[field].astype(str)
        for value in sorted(set(labels.tolist())):
            mask = labels == value
            if int(mask.sum()) < minimum: continue
            win_mask = mask & (data["y_win"] >= 1)
            result.setdefault(field, {})[value] = {
                "n": int(mask.sum()), "survival": _binary_metrics(data["y_win"][mask], p[mask]),
                "winningHp": _reg_metrics(data["y_hp"][win_mask], hp[win_mask]),
                "jointAliveHp": _reg_metrics(data["y_win"][mask] * np.nan_to_num(data["y_hp"][mask], nan=0.0),
                                               p[mask] * hp[mask]),
            }
    return result


class DeepSetsModel:
    def __init__(self, torch, max_cards: int, max_relics: int, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn
        self.torch = torch
        self.nn = nn
        self.max_cards = max_cards; self.max_relics = max_relics
        self.scalar_mean = torch.tensor(scalar_mean, dtype=torch.float32)
        self.scalar_inv = torch.tensor(1 / np.maximum(scalar_std, 1e-6), dtype=torch.float32)
        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__(); self.outer = outer
                self.card_id = nn.Embedding(CARD_COUNT, 48); self.relic_id = nn.Embedding(RELIC_COUNT, 48)
                self.potion_id = nn.Embedding(POTION_COUNT, 32); self.potion_slot = nn.Embedding(5, 8)
                self.global_category = nn.ModuleList(
                    nn.Embedding(GLOBAL_CATEGORY_COUNTS[field], 8)
                    for field in CATEGORICAL_GLOBAL_FIELDS
                )
                self.card_mlp = nn.Sequential(nn.Linear(48 + 3, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.relic_mlp = nn.Sequential(nn.Linear(48 + 2, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.potion_mlp = nn.Sequential(nn.Linear(32 + 8, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.global_mlp = nn.Sequential(
                    nn.Linear(len(CONTINUOUS_GLOBAL_FIELDS) + 8 * len(CATEGORICAL_GLOBAL_FIELDS), 64),
                    nn.ReLU(),
                )
                self.trunk = nn.Sequential(nn.Linear(256, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU())
                self.win = nn.Linear(64, 1); self.hp = nn.Linear(64, 1)
            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.outer.torch
                cfields = t.cat((c[:, :, 1:2].float(), c[:, :, 2:3].float().clamp(-20, 20) / 20,
                                 c[:, :, 3:4].float() / 3), -1)
                cvec = self.card_mlp(t.cat((self.card_id(c[:, :, 0].long()), cfields), -1))
                cpool = (cvec * cmask.unsqueeze(-1)).sum(1)
                rfields = t.cat((r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1)
                rvec = self.relic_mlp(t.cat((self.relic_id(r[:, :, 0].long()), rfields), -1))
                rpool = (rvec * rmask.unsqueeze(-1)).sum(1)
                pvec = self.potion_mlp(t.cat((self.potion_id(p[:, :, 1].long()),
                                              self.potion_slot(p[:, :, 0].long())), -1)).sum(1)
                global_categories = t.cat(
                    [embedding(gc[:, index].long())
                     for index, embedding in enumerate(self.global_category)], -1
                )
                gs = (g - self.outer.scalar_mean.to(g.device)) * self.outer.scalar_inv.to(g.device)
                z = self.trunk(t.cat((cpool, rpool, pvec, self.global_mlp(t.cat((gs, global_categories), -1))), -1))
                return self.win(z).squeeze(-1), self.hp(z).squeeze(-1)
        self.net = Net(self)


class AttentionModel:
    def __init__(self, torch, max_cards: int, max_relics: int, scalar_mean: np.ndarray,
                 scalar_std: np.ndarray, config: dict | None = None):
        import torch.nn as nn
        self.torch = torch; self.nn = nn; self.max_cards = max_cards; self.max_relics = max_relics
        self.config = {
            "width": 64, "heads": 4, "layers": 2, "feedforward": 128,
            "dropout": 0.1, "trunkWidth": 64,
            **(config or {}),
        }
        if self.config["width"] % self.config["heads"]:
            raise ValueError("attention width must be divisible by heads")
        self.scalar_mean = torch.tensor(scalar_mean, dtype=torch.float32)
        self.scalar_inv = torch.tensor(1 / np.maximum(scalar_std, 1e-6), dtype=torch.float32)
        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__(); self.outer = outer; d = int(outer.config["width"])
                self.card_id = nn.Embedding(CARD_COUNT, d); self.relic_id = nn.Embedding(RELIC_COUNT, d)
                self.potion_id = nn.Embedding(POTION_COUNT, d); self.type_embedding = nn.Embedding(4, d)
                self.global_category = nn.ModuleList(
                    nn.Embedding(GLOBAL_CATEGORY_COUNTS[field], 8)
                    for field in CATEGORICAL_GLOBAL_FIELDS
                )
                self.global_proj = nn.Linear(len(CONTINUOUS_GLOBAL_FIELDS) + 8 * len(CATEGORICAL_GLOBAL_FIELDS), d)
                self.card_fields = nn.Linear(3, d); self.relic_fields = nn.Linear(2, d)
                self.potion_slot = nn.Embedding(5, d)
                layer = nn.TransformerEncoderLayer(
                    d_model=d, nhead=int(outer.config["heads"]),
                    dim_feedforward=int(outer.config["feedforward"]),
                    dropout=float(outer.config["dropout"]), batch_first=True,
                    activation="gelu",
                )
                self.encoder = nn.TransformerEncoder(
                    layer, num_layers=int(outer.config["layers"])
                )
                trunk_width = int(outer.config["trunkWidth"])
                self.trunk = nn.Sequential(nn.Linear(d, trunk_width), nn.ReLU())
                self.win = nn.Linear(trunk_width, 1); self.hp = nn.Linear(trunk_width, 1)
            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.outer.torch
                gs = (g - self.outer.scalar_mean.to(g.device)) * self.outer.scalar_inv.to(g.device)
                global_categories = t.cat(
                    [embedding(gc[:, index].long())
                     for index, embedding in enumerate(self.global_category)], -1
                )
                gt = self.global_proj(t.cat((gs, global_categories), -1)).unsqueeze(1) + self.type_embedding.weight[0]
                cf = t.cat((c[:, :, 1:2].float(), c[:, :, 2:3].float().clamp(-20, 20) / 20,
                            c[:, :, 3:4].float() / 3), -1)
                ct = self.card_id(c[:, :, 0].long()) + self.card_fields(cf) + self.type_embedding.weight[1]
                rf = t.cat((r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1)
                rt = self.relic_id(r[:, :, 0].long()) + self.relic_fields(rf) + self.type_embedding.weight[2]
                pt = self.potion_id(p[:, :, 1].long()) + self.potion_slot(p[:, :, 0].long()) + self.type_embedding.weight[3]
                tokens = t.cat((gt, ct[:, :self.outer.max_cards], rt[:, :self.outer.max_relics], pt), 1)
                mask = t.cat((t.zeros((g.shape[0], 1), dtype=t.bool, device=g.device), ~cmask[:, :self.outer.max_cards],
                              ~rmask[:, :self.outer.max_relics], t.zeros((g.shape[0], 5), dtype=t.bool, device=g.device)), 1)
                z = self.encoder(tokens, src_key_padding_mask=mask)[:, 0]
                z = self.trunk(z)
                return self.win(z).squeeze(-1), self.hp(z).squeeze(-1)
        self.net = Net(self)


def _resolve_device(torch, requested: str) -> str:
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested but CUDA is unavailable")
        return "cuda"
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cpu"


def _new_torch_model(name: str, arrays: dict, train_indices: np.ndarray,
                     args: argparse.Namespace, device: str):
    import torch
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.training_seed)
    if device == "cuda": torch.cuda.manual_seed_all(args.training_seed)
    # Use the fixed contract padding from preparation for every split.  The
    # observed training maximum is not a valid tensor-shape contract: a held
    # out source may legitimately contain more cards or relics.
    max_cards = MAX_CARDS
    max_relics = MAX_RELICS
    scalar_mean = arrays["globals_continuous"][train_indices].mean(0)
    scalar_std = arrays["globals_continuous"][train_indices].std(0)
    wrapper = DeepSetsModel(torch, max_cards, max_relics, scalar_mean, scalar_std) if name == "deepsets" else AttentionModel(torch, max_cards, max_relics, scalar_mean, scalar_std)
    wrapper.device = torch.device(device)
    wrapper.net = wrapper.net.to(wrapper.device)
    return wrapper


def _torch_values(wrapper, arrays: dict, ids: np.ndarray) -> list:
    torch = wrapper.torch
    return [torch.from_numpy(arrays[key][ids]).to(wrapper.device, non_blocking=True)
            for key in ("globals_continuous", "global_categories", "cards", "relics",
                        "potions", "card_mask", "relic_mask")]


def _torch_train_epoch(wrapper, arrays: dict, order: np.ndarray, batch: int,
                       optimizer, bce) -> None:
    torch = wrapper.torch
    net = wrapper.net
    net.train()
    for lo in range(0, len(order), batch):
        ids = order[lo:lo + batch]
        values = _torch_values(wrapper, arrays, ids)
        wl, hl = net(*values)
        target = torch.from_numpy(arrays["y_win"][ids].astype(np.float32)).to(
            wrapper.device, non_blocking=True
        )
        htarget = torch.from_numpy(
            np.nan_to_num(arrays["y_hp"][ids], nan=0.0).astype(np.float32)
        ).to(wrapper.device, non_blocking=True)
        winmask = target > 0.5
        loss = bce(wl, target)
        if bool(winmask.any()):
            loss = loss + torch.nn.functional.mse_loss(
                torch.sigmoid(hl)[winmask], htarget[winmask]
            )
        optimizer.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        optimizer.step()


def _torch_eval(wrapper, arrays: dict, indices: np.ndarray, batch: int) -> tuple[dict, np.ndarray, np.ndarray]:
    torch = wrapper.torch
    net = wrapper.net
    net.eval(); ps = []; hs = []
    with torch.no_grad():
        for lo in range(0, len(indices), batch):
            ids = indices[lo:lo + batch]
            wl, hl = net(*_torch_values(wrapper, arrays, ids))
            ps.append(torch.sigmoid(wl).cpu().numpy())
            hs.append(torch.sigmoid(hl).cpu().numpy())
    p = np.concatenate(ps); h = np.concatenate(hs)
    yy = arrays["y_win"][indices]; hp = arrays["y_hp"][indices]
    winmask = yy == 1; alive = yy * np.nan_to_num(hp, nan=0.0)
    metrics = {
        "survival": _binary_metrics(yy, p),
        "winningHp": _reg_metrics(hp[winmask], h[winmask]),
        "jointAliveHp": _reg_metrics(alive, p * h),
        "calibration": _calibration(yy, p),
    }
    return metrics, p, h


def _torch_train(name: str, arrays: dict, tr: np.ndarray, va: np.ndarray, args: argparse.Namespace,
                 device: str):
    import torch
    wrapper = _new_torch_model(name, arrays, tr, args, device)
    net = wrapper.net
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss()
    best_state = None; best_score = math.inf; stale = 0; best_epoch = 0
    batch = args.nn_batch
    rng = np.random.default_rng(args.training_seed)
    for epoch in range(1, args.nn_epochs + 1):
        _torch_train_epoch(wrapper, arrays, rng.permutation(tr), batch, opt, bce)
        metrics, _, _ = _torch_eval(wrapper, arrays, va, batch)
        score=metrics["survival"]["brier"]+metrics["winningHp"]["mae"]+metrics["jointAliveHp"]["mae"]
        if score < best_score:
            best_score=score
            best_state={key:value.detach().cpu().clone() for key,value in net.state_dict().items()}
            best_epoch = epoch; stale=0
        else: stale += 1
        if stale >= args.nn_patience: break
    if best_state is not None: net.load_state_dict(best_state)
    val_metrics, _, _ = _torch_eval(wrapper, arrays, va, batch)
    return wrapper, val_metrics, int(sum(v.numel() for v in net.parameters())), best_epoch


def _torch_refit(name: str, arrays: dict, train_indices: np.ndarray, epochs: int,
                 args: argparse.Namespace, device: str):
    import torch
    if epochs < 1:
        raise ValueError(f"selected {name} epoch count must be positive")
    wrapper = _new_torch_model(name, arrays, train_indices, args, device)
    net = wrapper.net
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    bce = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(args.training_seed)
    for _ in range(epochs):
        _torch_train_epoch(wrapper, arrays, rng.permutation(train_indices), args.nn_batch, opt, bce)
    return wrapper, int(sum(v.numel() for v in net.parameters()))


def _predict_torch(wrapper, arrays: dict, indices: np.ndarray, batch: int) -> tuple[np.ndarray, np.ndarray]:
    torch = wrapper.torch; net=wrapper.net; net.eval(); ps=[]; hs=[]
    with torch.no_grad():
        for lo in range(0,len(indices),batch):
            ids=indices[lo:lo+batch]; wl,hl=net(*_torch_values(wrapper, arrays, ids))
            ps.append(torch.sigmoid(wl).cpu().numpy()); hs.append(torch.sigmoid(hl).cpu().numpy())
    return np.concatenate(ps),np.concatenate(hs)


def _metrics_for_predictions(arrays: dict, indices: np.ndarray, p: np.ndarray, hp: np.ndarray) -> dict:
    y=arrays["y_win"][indices]; yh=arrays["y_hp"][indices]; win=y==1; alive=y*np.nan_to_num(yh,nan=0.0)
    return {"survival": {**_binary_metrics(y,p), "calibration": _calibration(y,p)},
            "winningHp": _reg_metrics(yh[win],hp[win]), "jointAliveHp": _reg_metrics(alive,p*hp),
            "slices": _slice_metrics({key:arrays[key][indices] for key in ("y_win","y_hp","act","roomClass","encounter","preHpFrac")},p,hp)}


def _xgb_fit(Xtr, ytr, Xva, yva, config, objective, rounds, threads, device, seed):
    import xgboost as xgb
    params={"objective":objective,"eval_metric":"logloss" if objective=="binary:logistic" else "mae",
            "max_depth":config["max_depth"],"learning_rate":config["learning_rate"],"min_child_weight":config["min_child_weight"],
            "subsample":.8,"colsample_bytree":.8,"tree_method":"hist","device":device,
            "n_jobs":threads,"random_state":seed}
    model=xgb.XGBClassifier(n_estimators=rounds,**params,early_stopping_rounds=30) if objective=="binary:logistic" else xgb.XGBRegressor(n_estimators=rounds,**params,early_stopping_rounds=30)
    model.fit(Xtr,ytr,eval_set=[(Xva,yva)],verbose=False)
    return model, int(getattr(model,"best_iteration",rounds-1)+1)


def _xgb_refit(X, y, config, objective, rounds, threads, device, seed):
    import xgboost as xgb
    params={"objective":objective,"eval_metric":"logloss" if objective=="binary:logistic" else "mae",
            "max_depth":config["max_depth"],"learning_rate":config["learning_rate"],"min_child_weight":config["min_child_weight"],
            "subsample":.8,"colsample_bytree":.8,"tree_method":"hist","device":device,
            "n_jobs":threads,"random_state":seed}
    model=xgb.XGBClassifier(n_estimators=rounds,**params) if objective=="binary:logistic" else xgb.XGBRegressor(n_estimators=rounds,**params)
    model.fit(X,y,verbose=False); return model


def _xgb_metrics(arrays, indices, win_model, hp_model, feature_mask):
    X=arrays["flat"][indices][:,feature_mask]; p=np.asarray(win_model.predict_proba(X)[:,1]); hp=np.clip(np.asarray(hp_model.predict(X)),0,1)
    return _metrics_for_predictions(arrays,indices,p,hp),p,hp


def _bootstrap_diffs(arrays: dict, indices: np.ndarray, predictions: dict[str, tuple[np.ndarray,np.ndarray]], reps: int, seed: int) -> dict:
    groups=arrays["sourceSeed"][indices]; unique=np.asarray(sorted(set(groups.tolist()))); by={int(s):np.flatnonzero(groups==s) for s in unique}; rng=np.random.default_rng(seed)
    metrics={name:[] for name in predictions}
    for _ in range(reps):
        sampled=rng.choice(unique,size=len(unique),replace=True); positions=np.concatenate([by[int(s)] for s in sampled])
        for name,(p,hp) in predictions.items():
            y=arrays["y_win"][indices][positions]; yh=arrays["y_hp"][indices][positions]; win=y==1; alive=y*np.nan_to_num(yh,nan=0.0)
            metrics[name].append((float(np.mean((p[positions]-y)**2)),float(np.mean(np.abs(hp[positions][win]-yh[win]))),float(np.mean(np.abs(p[positions]*hp[positions]-alive)))))
    out={}
    for left,right in (("deepsets","xgboost"),("attention","xgboost"),("attention","deepsets")):
        delta=np.asarray(metrics[left])-np.asarray(metrics[right]); out[f"{left}_minus_{right}"]={
            "brier95":[float(np.quantile(delta[:,0],.025)),float(np.quantile(delta[:,0],.975))],
            "winningHpMae95":[float(np.quantile(delta[:,1],.025)),float(np.quantile(delta[:,1],.975))],
            "jointAliveHpMae95":[float(np.quantile(delta[:,2],.025)),float(np.quantile(delta[:,2],.975))],
        }
    return out


def _bootstrap_interval(bootstrap: dict, left: str, right: str, metric: str) -> list[float]:
    if left == right:
        return [0.0, 0.0]
    key = f"{left}_minus_{right}"
    if key in bootstrap:
        return bootstrap[key][metric]
    reverse = bootstrap[f"{right}_minus_{left}"][metric]
    return [-float(reverse[1]), -float(reverse[0])]


def _is_clear_winner(bootstrap: dict, finalist: str) -> bool:
    """Require the validation finalist to separate from every other family."""
    metrics = ("brier95", "winningHpMae95", "jointAliveHpMae95")
    return all(
        all(_bootstrap_interval(bootstrap, finalist, other, metric)[1] < 0
            for metric in metrics)
        for other in ("xgboost", "deepsets", "attention") if other != finalist
    )


def fit(args: argparse.Namespace) -> None:
    import xgboost  # noqa: F401
    import torch
    device = _resolve_device(torch, args.device)
    prepared_dir = Path(args.prepared_dir)
    arrays = {key: value for key, value in np.load(prepared_dir / "prepared.npz", allow_pickle=False).items()}
    tr = np.flatnonzero(arrays["split_id"] == 0)
    va = np.flatnonzero(arrays["split_id"] == 1)
    te = np.flatnonzero(arrays["split_id"] == 2)
    if not len(tr) or not len(va) or not len(te): raise ValueError("all three source-grouped splits must be non-empty")
    variance = arrays["flat"][tr].var(0)
    feature_mask = variance > 1e-12
    prepared_manifest = json.loads((prepared_dir / "prepared_manifest.json").read_text())
    feature_names = np.asarray(prepared_manifest["featureSchema"]["flatNames"])[feature_mask].tolist()
    xgb_configs = [
        {"name": "depth4", "max_depth": 4, "learning_rate": .05, "min_child_weight": 1},
        {"name": "depth6", "max_depth": 6, "learning_rate": .05, "min_child_weight": 1},
    ]
    xtr = arrays["flat"][tr][:, feature_mask]; xva = arrays["flat"][va][:, feature_mask]
    win_train = arrays["y_win"][tr]; win_val = arrays["y_win"][va]
    hp_train = arrays["y_hp"][tr]; hp_val = arrays["y_hp"][va]
    xgb_candidates=[]
    for config in xgb_configs:
        wm,wr=_xgb_fit(xtr,win_train,xva,win_val,config,"binary:logistic",args.xgb_rounds,args.threads,device,args.training_seed)
        tr_win=win_train==1; va_win=win_val==1
        hm,hr=_xgb_fit(xtr[tr_win],hp_train[tr_win],xva[va_win],hp_val[va_win],config,"reg:squarederror",args.xgb_rounds,args.threads,device,args.training_seed)
        metrics,p,hp=_xgb_metrics(arrays,va,wm,hm,feature_mask)
        score=metrics["survival"]["brier"]+metrics["winningHp"]["mae"]+metrics["jointAliveHp"]["mae"]
        xgb_candidates.append({"config":config,"survival":wm,"hp":hm,"rounds":{"survival":wr,"hp":hr},"validation":metrics,"selectionScore":score})
    xgb_choice=min(xgb_candidates,key=lambda item:item["selectionScore"])
    chosen=xgb_choice["config"]
    xgb_validation={"candidates":[{"config":c["config"],"metrics":c["validation"],"selectionScore":c["selectionScore"],"rounds":c["rounds"]} for c in xgb_candidates],"selected":chosen}
    # These are the only neural fits that see VALIDATION.  Their best epoch is
    # frozen before the combined refit; TEST remains untouched until below.
    _, deepsets_val, deepsets_params, deepsets_epochs = _torch_train("deepsets", arrays, tr, va, args, device)
    _, attention_val, attention_params, attention_epochs = _torch_train("attention", arrays, tr, va, args, device)
    families={"xgboost":xgb_choice["validation"],"deepsets":deepsets_val,"attention":attention_val}
    val_scores={name:float(metrics["survival"]["brier"]+metrics["winningHp"]["mae"]+metrics["jointAliveHp"]["mae"]) for name,metrics in families.items()}
    finalist=min(val_scores,key=val_scores.get)
    selection_lengths = {
        "xgboost": {"survivalRounds": int(xgb_choice["rounds"]["survival"]),
                    "winningHpRounds": int(xgb_choice["rounds"]["hp"])},
        "deepsetsEpochs": int(deepsets_epochs),
        "attentionEpochs": int(attention_epochs),
    }
    print(json.dumps({"phase":"validation_selection_complete", "validationSelection":finalist,
                      "selectedTrainingLengths":selection_lengths}, sort_keys=True), flush=True)
    # Final comparison refits every family from scratch on TRAIN+VALIDATION.
    # The lengths/configurations above were frozen without inspecting TEST.
    combined=np.concatenate((tr,va))
    xcombined=arrays["flat"][combined][:,feature_mask]
    ycombined=arrays["y_win"][combined]
    hpcombined=arrays["y_hp"][combined]
    combined_win=ycombined==1
    xgb_win=_xgb_refit(xcombined,ycombined,chosen,"binary:logistic",xgb_choice["rounds"]["survival"],args.threads,device,args.training_seed)
    xgb_hp=_xgb_refit(xcombined[combined_win],hpcombined[combined_win],chosen,"reg:squarederror",xgb_choice["rounds"]["hp"],args.threads,device,args.training_seed)
    deepsets, deepsets_final_params = _torch_refit("deepsets", arrays, combined, deepsets_epochs, args, device)
    attention, attention_final_params = _torch_refit("attention", arrays, combined, attention_epochs, args, device)
    # TEST is intentionally first touched by predictions from these equal
    # TRAIN+VALIDATION refits.
    xgb_test,xgb_p,xgb_hp_pred=_xgb_metrics(arrays,te,xgb_win,xgb_hp,feature_mask)
    ds_p,ds_hp=_predict_torch(deepsets,arrays,te,args.nn_batch); ds_test=_metrics_for_predictions(arrays,te,ds_p,ds_hp)
    at_p,at_hp=_predict_torch(attention,arrays,te,args.nn_batch); at_test=_metrics_for_predictions(arrays,te,at_p,at_hp)
    test_predictions={"xgboost":(xgb_p,xgb_hp_pred),"deepsets":(ds_p,ds_hp),"attention":(at_p,at_hp)}
    output=Path(args.output_dir); output.mkdir(parents=True,exist_ok=True)
    xgb_win.save_model(output/"xgboost_survival.json"); xgb_hp.save_model(output/"xgboost_winning_hp.json")
    torch.save(deepsets.net.state_dict(),output/"deepsets.pt"); torch.save(attention.net.state_dict(),output/"attention.pt")
    np.save(output/"test_source_seeds.npy",arrays["sourceSeed"][te])
    if getattr(args, "save_test_predictions", False):
        # Per-row TEST predictions for offline comparison with other predictors;
        # rowIndex is the corpus line index (prepare keeps every row in order).
        np.savez(output/"test_predictions.npz",rowIndex=te,sourceSeed=arrays["sourceSeed"][te],
                 fightIdx=arrays["fightIdx"][te],y_win=arrays["y_win"][te],y_hp=arrays["y_hp"][te],
                 **{f"{name}_{kind}":values for name,(p,hp) in test_predictions.items()
                    for kind,values in (("p",p),("hp",hp))})
    bootstrap=_bootstrap_diffs(arrays,te,test_predictions,args.bootstrap_reps,args.training_seed)
    final_fit = {
        "data": "TRAIN+VALIDATION only",
        "xgboost": {"config": chosen, "survivalRounds": int(xgb_choice["rounds"]["survival"]),
                    "winningHpRounds": int(xgb_choice["rounds"]["hp"])},
        "deepsets": {"epochs": int(deepsets_epochs), "parameters": deepsets_final_params},
        "attention": {"epochs": int(attention_epochs), "parameters": attention_final_params},
        "seed": int(args.training_seed),
    }
    evidence={"schemaVersion":MODEL_SCHEMA,"preparedManifest":str((prepared_dir/"prepared_manifest.json").resolve()),"preparedManifestSha256":sha256(prepared_dir/"prepared_manifest.json"),"corpusSha256":prepared_manifest["corpusSha256"],"split": {"trainSources":int(len(set(arrays["sourceSeed"][tr].tolist()))),"validationSources":int(len(set(arrays["sourceSeed"][va].tolist()))),"testSources":int(len(set(arrays["sourceSeed"][te].tolist())))},"featureProcessing":{"flatFeaturesBeforeVariance":int(len(arrays["flat"][0])),"flatFeaturesRetainedTrainVariance":int(feature_mask.sum()),"retainedNames":feature_names,"continuousGlobals":list(CONTINUOUS_GLOBAL_FIELDS),"categoricalGlobals":{field:list(range(GLOBAL_CATEGORY_COUNTS[field])) for field in CATEGORICAL_GLOBAL_FIELDS}},"validation":{"families":families,"selectionScores":val_scores,"selectedFinalist":finalist,"xgboost":xgb_validation,"deepsets":{"parameters":deepsets_params,"epochs":deepsets_epochs},"attention":{"parameters":attention_params,"epochs":attention_epochs},"selectedTrainingLengths":selection_lengths},"finalFit":final_fit,"test":{"evaluation":"Corrected rerun of the frozen TEST split after independent review; not an untouched first TEST.","xgboost":xgb_test,"deepsets":ds_test,"attention":at_test,"sourceBootstrap95":bootstrap},"modelArtifacts":{"xgboostSurvivalSha256":sha256(output/"xgboost_survival.json"),"xgboostWinningHpSha256":sha256(output/"xgboost_winning_hp.json"),"deepsetsSha256":sha256(output/"deepsets.pt"),"attentionSha256":sha256(output/"attention.pt")},"config":{"device":device,"requestedDevice":args.device,"xgbRounds":args.xgb_rounds,"threads":args.threads,"nnBatch":args.nn_batch,"nnEpochs":args.nn_epochs,"nnPatience":args.nn_patience,"trainingSeed":args.training_seed,"bootstrapReps":args.bootstrap_reps,"seedProtocol":"numpy.default_rng and torch.manual_seed use this seed for each family; XGBoost random_state uses this seed; no TEST-based tuning.","entityDomains":{"cards":CARD_COUNT,"relics":RELIC_COUNT,"potions":POTION_COUNT}},"interpretation":{"testRule":"Corrected rerun of the frozen TEST split after independent review; source-seed bootstrap intervals; negative model-minus-model deltas favor the left model on all listed errors.","familyDecision":"Finalist and all training lengths/configurations selected using TRAIN/VALIDATION only; all three families were refit from scratch on TRAIN+VALIDATION before TEST evaluation.","clearNeuralWinRule":"A validation finalist must have a 95% source-bootstrap upper bound below zero on all three listed error metrics against every other family; this reporting rule was applied once after the frozen corrected run and was not a preregistered practical-improvement threshold.","classification":"UNSET"}}
    # A clear neural win requires a validation finalist plus an upper bootstrap
    # bound below zero on all listed errors.  Otherwise preserve a tie.
    best=finalist
    if best!="xgboost":
        clear = _is_clear_winner(bootstrap, best)
        classification="DEEPSETS_WINS" if best=="deepsets" and clear else "ATTENTION_WINS" if best=="attention" and clear else "NO_CLEAR_DIFFERENCE"
    else:
        classification="XGBOOST_SUFFICIENT"
    evidence["interpretation"]["classification"]=classification
    json_dump(output/"model_evidence.json",evidence)
    print(json.dumps({"validationSelection":finalist,"testClassification":classification,"validationScores":val_scores,"selectedTrainingLengths":selection_lengths,"output":str(output.resolve())},indent=2))


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("audit"); p.add_argument("--corpus-manifest",required=True); p.add_argument("--shard-root",help="required unless the corpus is a ctm_corpus_adapter union"); p.add_argument("--output-dir",required=True); p.set_defaults(func=audit)
    p=sub.add_parser("prepare"); p.add_argument("--audit",required=True); p.add_argument("--output-dir",required=True); p.set_defaults(func=prepare)
    p=sub.add_parser("fit"); p.add_argument("--prepared-dir",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--device",choices=("auto","cpu","cuda"),default="auto"); p.add_argument("--threads",type=int,default=8); p.add_argument("--xgb-rounds",type=int,default=400); p.add_argument("--nn-batch",type=int,default=2048); p.add_argument("--nn-epochs",type=int,default=12); p.add_argument("--nn-patience",type=int,default=3); p.add_argument("--training-seed",type=int,default=20260911); p.add_argument("--bootstrap-reps",type=int,default=1000); p.add_argument("--save-test-predictions",action="store_true"); p.set_defaults(func=fit)
    args=parser.parse_args(); args.func(args)


if __name__ == "__main__": main()
