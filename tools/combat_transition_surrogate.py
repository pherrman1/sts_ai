#!/usr/bin/env python3
"""Train and evaluate the offline stochastic combat-transition surrogate.

This tool is deliberately separate from ``combat_transition_model_experiment``
because the Phase-1 representation comparison is a frozen result.  It reads
the already-collected RAW transition corpus, applies a predictor-visible
support predicate, and trains a small DeepSets multitask model on supported
rows only.  It never invokes the simulator, consumes combat RNG as an input,
or exports a runtime artifact.

The command sequence is::

    prepare --corpus-manifest ... --output-dir ...
    fit --prepared-dir ... --output-dir ... --device cuda

``prepare`` performs the complete support/copy-through audit before writing
prepared arrays.  ``fit`` freezes validation-selected epoch counts, refits
from scratch on TRAIN+VALIDATION, evaluates once on the fixed TEST split, and
writes machine-readable evidence plus external model checkpoints.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

try:
    from tools.combat_predictor_input_contract import (
        validate_predictor_input,
    )
    from tools.combat_transition_contract import validate_corpus
    from tools.combat_transition_model_experiment import (
        CARD_COUNT,
        CONTINUOUS_GLOBAL_FIELDS,
        GLOBAL_CATEGORY_COUNTS,
        MAX_CARDS,
        MAX_RELICS,
        POTION_COUNT,
        RELIC_COUNT,
        _encode_row,
        _validate_entity_domains,
        persistent_change_flags,
        split_for_seed,
    )
except ModuleNotFoundError:  # direct invocation from tools/
    from combat_predictor_input_contract import validate_predictor_input
    from combat_transition_contract import validate_corpus
    from combat_transition_model_experiment import (
        CARD_COUNT,
        CONTINUOUS_GLOBAL_FIELDS,
        GLOBAL_CATEGORY_COUNTS,
        MAX_CARDS,
        MAX_RELICS,
        POTION_COUNT,
        RELIC_COUNT,
        _encode_row,
        _validate_entity_domains,
        persistent_change_flags,
        split_for_seed,
    )


SCRIPT_SCHEMA = "combat_transition_surrogate_phase2_v1"
PREPARED_SCHEMA = "combat_transition_surrogate_prepared_v1"
MODEL_SCHEMA = "combat_transition_surrogate_model_v1"
HP_BIN_COUNT = 101
WIN = 1
DEATH = 2
PERSISTENT_KEYS = (
    "curHp", "maxHp", "gold", "potionCount", "potionCapacity", "potions",
    "smokeBombUsed", "stolenGold", "relics", "relicBits", "deck",
    "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount",
)
COPY_THROUGH_KEYS = (
    "gold", "stolenGold", "potionCapacity", "relicBits", "deck",
    "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount",
)

_ROOT = Path(__file__).resolve().parents[1]


def _enum_values(header: Path, enum_name: str) -> dict[str, int]:
    text = header.read_text(encoding="utf-8")
    match = re.search(rf"enum\s+class\s+{re.escape(enum_name)}\b[^{{]*{{(.*?)}}\s*;", text, re.S)
    if match is None:
        raise RuntimeError(f"canonical enum {enum_name} not found in {header}")
    values: dict[str, int] = {}
    next_value = 0
    for line in match.group(1).splitlines():
        line = line.split("//", 1)[0].strip()
        if not line:
            continue
        item = re.match(r"([A-Z][A-Z0-9_]*)\s*(?:=\s*(-?\d+))?\s*,?", line)
        if item is None:
            continue
        if item.group(2) is not None:
            next_value = int(item.group(2))
        values[item.group(1)] = next_value
        next_value += 1
    if not values or sorted(values.values()) != list(range(len(values))):
        raise RuntimeError(f"canonical enum {enum_name} is not contiguous from zero")
    return values


_CARD_IDS = _enum_values(_ROOT / "include/constants/Cards.h", "CardId")
_POTION_IDS = _enum_values(_ROOT / "include/constants/Potions.h", "Potion")
_CHARACTER_CLASS_IDS = _enum_values(
    _ROOT / "include/constants/CharacterClasses.h", "CharacterClass"
)
_ENCOUNTER_IDS = _enum_values(
    _ROOT / "include/constants/MonsterEncounters.h", "MonsterEncounter"
)
_RELIC_IDS = _enum_values(_ROOT / "include/constants/Relics.h", "RelicId")
RITUAL_DAGGER_ID = _CARD_IDS["RITUAL_DAGGER"]
HAND_OF_GREED_ID = _CARD_IDS["HAND_OF_GREED"]
SMOKE_BOMB_ID = _POTION_IDS["SMOKE_BOMB"]
ENTROPIC_BREW_ID = _POTION_IDS["ENTROPIC_BREW"]
EMPTY_POTION_SLOT_ID = _POTION_IDS["EMPTY_POTION_SLOT"]
IRONCLAD_ID = _CHARACTER_CLASS_IDS["IRONCLAD"]
WRITHING_MASS_ID = _ENCOUNTER_IDS["WRITHING_MASS"]
GOLD_MUTATING_ENCOUNTER_NAMES = ("LOOTER", "TWO_THIEVES")
GOLD_MUTATING_ENCOUNTER_IDS = frozenset(
    _ENCOUNTER_IDS[name] for name in GOLD_MUTATING_ENCOUNTER_NAMES
)
GOLD_MUTATING_CARD_NAMES = ("HAND_OF_GREED",)
GOLD_MUTATING_CARD_IDS = frozenset(_CARD_IDS[name] for name in GOLD_MUTATING_CARD_NAMES)
POTION_NAMES_BY_ID = {value: name for name, value in _POTION_IDS.items()}


def _mutable_relic_audit() -> tuple[dict[str, int], set[int]]:
    """Return the bounded source audit and its canonical relic IDs.

    ``updateRelicsOnExit`` is the maintained direct write-back list.  Omamori
    is the one additional RAW exit mutation in ``exitBattle`` and is excluded
    by the Writhing Mass support rule.  This is intentionally a bounded source
    audit, not a heuristic scan of every combat implementation.
    """
    source = (_ROOT / "src/combat/BattleContext.cpp").read_text(encoding="utf-8")
    body_match = re.search(
        r"void\s+BattleContext::updateRelicsOnExit\s*\(.*?\n}\n",
        source,
        re.S,
    )
    if body_match is None:
        raise RuntimeError("could not locate BattleContext::updateRelicsOnExit")
    case_names = re.findall(r"case\s+RelicId::([A-Z][A-Z0-9_]*):", body_match.group(0))
    raw_exit_names = re.findall(
        r"getRelicValueRef\(RelicId::([A-Z][A-Z0-9_]*)\)", source[: source.index("void BattleContext::updateRelicsOnExit")]
    )
    names = sorted(set(case_names) | set(raw_exit_names))
    ids = {name: _RELIC_IDS[name] for name in names if name in _RELIC_IDS}
    if not ids:
        raise RuntimeError("bounded mutable-relic audit found no relics")
    return ids, set(ids.values())


MUTABLE_RELIC_NAMES, CODE_AUDITED_MUTABLE_RELIC_IDS = _mutable_relic_audit()


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
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc


def supported_reasons(predictor_input: dict, pre_state: dict) -> list[str]:
    """Return fallback reasons for input plus non-learned adapter eligibility state.

    ``pre_state.smokeBombUsed`` is deliberately an adapter/support-gate field,
    not a learned feature.  The learned input remains exactly
    ``combat_predictor_input_v1``.
    """
    validate_predictor_input(predictor_input)
    _validate_entity_domains(predictor_input)
    if not isinstance(pre_state, dict) or not isinstance(pre_state.get("smokeBombUsed"), bool):
        raise ValueError("support eligibility requires boolean pre_state.smokeBombUsed")
    reasons: list[str] = []
    if int(predictor_input["globals"]["characterClass"]) != IRONCLAD_ID:
        reasons.append("non_ironclad")
    if int(predictor_input["globals"]["encounter"]) == WRITHING_MASS_ID:
        reasons.append("writhing_mass")
    if any(int(card["cardId"]) == RITUAL_DAGGER_ID for card in predictor_input["cards"]):
        reasons.append("ritual_dagger")
    if int(predictor_input["globals"]["encounter"]) in GOLD_MUTATING_ENCOUNTER_IDS:
        reasons.append("gold_mutating_encounter")
    if any(int(card["cardId"]) in GOLD_MUTATING_CARD_IDS for card in predictor_input["cards"]):
        reasons.append("gold_mutating_card")
    if any(int(potion["potionId"]) == SMOKE_BOMB_ID for potion in predictor_input["potions"]):
        reasons.append("smoke_bomb")
    if any(int(potion["potionId"]) == ENTROPIC_BREW_ID for potion in predictor_input["potions"]):
        reasons.append("entropic_brew")
    if pre_state["smokeBombUsed"]:
        reasons.append("pre_smoke_bomb_used")
    return reasons


def supported_for_surrogate(predictor_input: dict, pre_state: dict) -> bool:
    """The Phase-2 support predicate; aliases the contract wording in Python."""
    return not supported_reasons(predictor_input, pre_state)


def _round_half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def hp_fraction_bin(cur_hp: int, max_hp: int) -> int:
    if max_hp <= 0:
        raise ValueError(f"maxHp must be positive for HP binning, got {max_hp}")
    return max(0, min(100, _round_half_up(100.0 * cur_hp / max_hp)))


def _state_structural_equal(pre: dict, post: dict, key: str) -> bool:
    if key == "relics":
        return [(int(x["id"]), int(x["data"])) for x in pre[key]] == [
            (int(x["id"]), int(x["data"])) for x in post[key]
        ]
    return pre[key] == post[key]


def _copy_through_violations(pre: dict, post: dict) -> list[str]:
    violations = [key for key in COPY_THROUGH_KEYS if not _state_structural_equal(pre, post, key)]
    if [(int(x["id"]), i) for i, x in enumerate(pre["relics"])] != [
        (int(x["id"]), i) for i, x in enumerate(post["relics"])
    ]:
        violations.append("relic_id_or_order")
    if not _state_structural_equal(pre, post, "smokeBombUsed"):
        violations.append("smokeBombUsed")
    return violations


def _mutation_names(flags: dict) -> tuple[str, ...]:
    names = []
    if flags["card_upgrade_or_deck_structure_changed"]:
        names.append("deck_structure")
    if flags["deck_misc_changed"]:
        names.append("card_misc")
    if flags["smoke_bomb_used"]:
        names.append("smoke_bomb")
    return tuple(names)


def _inc_nested(table: dict, key: object, supported: bool) -> None:
    item = table.setdefault(str(key), {"total": 0, "supported": 0, "fallback": 0})
    item["total"] += 1
    if supported:
        item["supported"] += 1
    else:
        item["fallback"] += 1


def _support_rate(item: dict) -> float | None:
    return None if not item["total"] else float(item["supported"] / item["total"])


def _finalize_support_table(table: dict) -> dict:
    return {
        key: {**value, "supportRate": _support_rate(value)}
        for key, value in sorted(table.items(), key=lambda pair: pair[0])
    }


def _audit_summary(
    manifest: dict,
    rows: int,
    support_rows: int,
    support_by_act: dict,
    support_by_room: dict,
    support_by_encounter: dict,
    support_by_death: dict,
    reasons: Counter,
    mutations: Counter,
    mutation_covered: Counter,
    gold_mutation_rows: Counter,
    gold_mutation_covered: Counter,
    copy_through_violations: Counter,
    smoke_mutation_without_visible_total: int,
    smoke_mutation_without_visible_supported: int,
    smoke_mutation_without_visible_potion_ids: Counter,
    smoke_mutation_without_visible_examples: list[dict],
    smoke_copy_through_directions: Counter,
    train_values: dict,
) -> dict:
    total = {"total": rows, "supported": support_rows, "fallback": rows - support_rows}
    return {
        "schemaVersion": SCRIPT_SCHEMA,
        "status": "PASS" if not copy_through_violations and not any(mutation_covered.values()) and not any(gold_mutation_covered.values()) else "FAIL",
        "corpus": {
            "path": str(Path(manifest["csv"]["path"]).resolve()),
            "sha256": manifest["csv"]["sha256"],
            "seedSpec": manifest["seedSpec"],
            "rows": int(manifest["integrity"]["rows"]),
            "completedSeeds": int(manifest["integrity"]["completedSeeds"]),
            "quarantinedSeeds": int(manifest["integrity"]["quarantinedSeeds"]),
            "producerGitSha": manifest["producerGitSha"],
            "producerExecutableSha256": manifest["producerExecutableSha256"],
            "teacherId": manifest["combatTeacher"]["teacher_id"],
        },
        "supportBoundary": {
            "predicate": (
                "globals.characterClass == IRONCLAD and globals.encounter != WRITHING_MASS "
                "and globals.encounter not in (LOOTER, TWO_THIEVES) "
                "and no deck card in (RITUAL_DAGGER, HAND_OF_GREED) and no active potion "
                "(SMOKE_BOMB or ENTROPIC_BREW) and pre.smokeBombUsed == false"
            ),
            "ids": {
                "ironcladCharacterClass": IRONCLAD_ID,
                "writhingMassEncounter": WRITHING_MASS_ID,
                "goldMutatingEncounters": {
                    name: int(_ENCOUNTER_IDS[name]) for name in GOLD_MUTATING_ENCOUNTER_NAMES
                },
                "ritualDaggerCard": RITUAL_DAGGER_ID,
                "goldMutatingCards": {
                    name: int(_CARD_IDS[name]) for name in GOLD_MUTATING_CARD_NAMES
                },
                "smokeBombPotion": SMOKE_BOMB_ID,
                "entropicBrewPotion": ENTROPIC_BREW_ID,
            },
            "learnedInputSchema": "combat_predictor_input_v1",
            "adapterOnlyPreCombatFields": {
                "pre.smokeBombUsed": "eligibility/support gate only; not a learned feature"
            },
            "rows": {**total, "supportRate": support_rows / rows if rows else None},
            "fallbackReasons": dict(sorted(reasons.items())),
            "byAct": _finalize_support_table(support_by_act),
            "byRoomClass": _finalize_support_table(support_by_room),
            "byEncounter": _finalize_support_table(support_by_encounter),
            "amongDeaths": {**support_by_death, "supportRate": _support_rate(support_by_death)},
        },
        "goldMutationSourceAudit": {
            "scope": [
                "src/combat/MonsterSpecific.cpp",
                "src/combat/Actions.cpp",
                "src/combat/Player.cpp",
                "src/combat/BattleContext.cpp",
                "src/combat/MonsterGroup.cpp",
                "include/constants/MonsterEncounters.h",
                "include/constants/Cards.h",
            ],
            "mechanisms": [
                {
                    "name": "looter_mugger_theft",
                    "source": "Monster::stealGoldFromPlayer called by Looter and Mugger MUG/LUNGE moves",
                    "visibleEncounterNames": list(GOLD_MUTATING_ENCOUNTER_NAMES),
                    "visibleEncounterIds": sorted(int(value) for value in GOLD_MUTATING_ENCOUNTER_IDS),
                    "effect": "subtracts player.gold and records the stolen amount in the monster misc counter",
                },
                {
                    "name": "hand_of_greed",
                    "source": "Actions::HandOfGreedAction calls Player::gainGold on its qualifying lethal branch",
                    "visibleCardNames": list(GOLD_MUTATING_CARD_NAMES),
                    "visibleCardIds": sorted(int(value) for value in GOLD_MUTATING_CARD_IDS),
                    "effect": "adds 20/25 to player.gold; Ectoplasm can suppress the gain but is not a support prerequisite",
                },
            ],
            "negativeAudit": "No other src/combat card or relic path writes persistent player gold or stolenGold; BattleContext exit code only copies and derives the recorded theft value.",
            "guardCoverage": {
                "fullCorpusMutationRows": dict(sorted(gold_mutation_rows.items())),
                "supportedRowsWithMutation": dict(sorted(gold_mutation_covered.items())),
                "allCovered": not any(gold_mutation_covered.values()),
            },
        },
        "intentionalOmittedMutationCoverage": {
            "definitions": {
                "deck_structure": "pre/post deck multiset of (id, upgraded) differs",
                "card_misc": "pre/post deck multiset of (id, misc) differs while card structure is retained",
                "smoke_bomb": "smokeBombUsed changes false -> true",
            },
            "fullCorpusMutationRows": dict(sorted(mutations.items())),
            "supportedRowsWithMutation": dict(sorted(mutation_covered.items())),
            "allCovered": not any(mutation_covered.values()),
        },
        "uncoveredMechanisms": {
            "smokeBombGeneratedFromInvisiblePrePotion": {
                "fullCorpusRows": int(smoke_mutation_without_visible_total),
                "supportedRows": int(smoke_mutation_without_visible_supported),
                "prePotionIdsSeenByRow": dict(sorted(smoke_mutation_without_visible_potion_ids.items())),
                "prePotionNamesSeenByRow": {
                    POTION_NAMES_BY_ID.get(int(potion_id), f"UNKNOWN_{potion_id}"): int(count)
                    for potion_id, count in sorted(smoke_mutation_without_visible_potion_ids.items())
                },
                "sourceExamples": smoke_mutation_without_visible_examples,
                "codeEvidence": (
                    "BattleContext::drinkPotion(Potion::ENTROPIC_BREW) calls "
                    "returnRandomPotion and obtainPotion; the bounded corpus audit "
                    "observes the resulting SMOKE_BOMB mutation without a visible "
                    "pre-state SMOKE_BOMB slot."
                ),
                "entropicBrewPotionId": ENTROPIC_BREW_ID,
            }
        },
        "boundedMutableRelicAudit": {
            "source": "BattleContext::updateRelicsOnExit plus direct Omamori RAW exit write",
            "relics": {name: int(value) for name, value in sorted(MUTABLE_RELIC_NAMES.items())},
            "ids": sorted(CODE_AUDITED_MUTABLE_RELIC_IDS),
            "trainObservedDeltaValuesByRelic": train_values.get("relicDeltaValuesById", {}),
        },
        "copyThroughAudit": {
            "keys": list(COPY_THROUGH_KEYS) + ["relic_id_or_order", "smokeBombUsed"],
            "supportedWinningRowsWithViolation": dict(sorted(copy_through_violations.items())),
            "smokeBombUsedDirections": dict(sorted(smoke_copy_through_directions.items())),
            "allExact": not bool(copy_through_violations),
        },
        "targetSupportPreview": train_values,
        "notes": [
            "The combatRng[6] streams are intentionally absent from model inputs and outputs.",
            "Deaths contribute to survival only; persistent transition heads train on supported wins.",
            "Unsupported states are intended to fall back to native Silver in a future adapter.",
        ],
    }


def _target_values_from_row(pre: dict, post: dict, outcome: int) -> dict:
    if len(post["potions"]) != 5 or any(
        not EMPTY_POTION_SLOT_ID <= int(value) < POTION_COUNT for value in post["potions"]
    ):
        raise ValueError("post potion state contains an invalid or non-canonical potion ID")
    delta_max = int(post["maxHp"]) - int(pre["maxHp"])
    post_hp_bin = hp_fraction_bin(int(post["curHp"]), int(post["maxHp"]))
    relic_delta = [0] * MAX_RELICS
    relic_mask = [False] * MAX_RELICS
    if len(pre["relics"]) != len(post["relics"]):
        raise ValueError("relic count changed before copy-through audit")
    for index, (before, after) in enumerate(zip(pre["relics"], post["relics"])):
        if before["id"] != after["id"]:
            raise ValueError("relic identity changed before copy-through audit")
        if index >= MAX_RELICS:
            raise ValueError("relic padding contract is too small")
        relic_delta[index] = int(after["data"]) - int(before["data"])
        relic_mask[index] = int(before["id"]) in CODE_AUDITED_MUTABLE_RELIC_IDS
    return {
        "maxHpDelta": delta_max,
        "hpBin": post_hp_bin,
        "postHp": int(post["curHp"]),
        "postMaxHp": int(post["maxHp"]),
        "postHpFraction": float(post["curHp"] / max(post["maxHp"], 1)),
        "potions": [int(x) for x in post["potions"]],
        "relicDelta": relic_delta,
        "relicMask": relic_mask,
        "outcome": int(outcome),
    }


def _target_preview(target_rows: list[dict], split_rows: list[str], train_split: str = "train") -> dict:
    train = [row for row, split in zip(target_rows, split_rows) if split == train_split and row["outcome"] == WIN]
    if not train:
        raise ValueError("TRAIN has no supported winning rows")
    max_values = sorted({int(row["maxHpDelta"]) for row in train})
    relic_values: dict[str, list[int]] = defaultdict(list)
    for row in train:
        for index, (delta, active) in enumerate(zip(row["relicDelta"], row["relicMask"])):
            if active:
                relic_values[str(index)].append(int(delta))
    # The train rows above have token positions, so the actual ID map is filled
    # during preparation below.  This helper is retained for small unit tests.
    return {
        "maxHpDeltaValues": max_values,
        "relicDeltaValuesByPosition": {
            key: sorted(set(values)) for key, values in sorted(relic_values.items())
        },
    }


def prepare(args: argparse.Namespace) -> None:
    manifest_path = Path(args.corpus_manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus_path = Path(manifest["csv"]["path"])
    if not corpus_path.is_file():
        raise ValueError(f"corpus does not exist: {corpus_path}")
    if manifest["csv"].get("sha256") != args.expected_corpus_sha256:
        raise ValueError("corpus manifest SHA256 does not match the frozen Phase-2 precondition")
    # This validates the merged row contract and exact corpus hash before the
    # support audit.  Shard inventory was already independently validated for
    # the frozen corpus; no data is collected here.
    corpus_result = validate_corpus(manifest)
    expected_rows = int(corpus_result["rows"])
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    globals_continuous = np.empty((expected_rows, len(CONTINUOUS_GLOBAL_FIELDS)), dtype=np.float32)
    global_categories = np.empty((expected_rows, 4), dtype=np.int64)
    cards = np.empty((expected_rows, MAX_CARDS, 4), dtype=np.int16)
    card_mask = np.zeros((expected_rows, MAX_CARDS), dtype=np.bool_)
    relics = np.empty((expected_rows, MAX_RELICS, 3), dtype=np.int16)
    relic_mask = np.zeros((expected_rows, MAX_RELICS), dtype=np.bool_)
    potions = np.empty((expected_rows, 5, 2), dtype=np.int16)
    y_win = np.empty(expected_rows, dtype=np.int8)
    y_hp = np.empty(expected_rows, dtype=np.float32)
    y_hp_bin = np.empty(expected_rows, dtype=np.int8)
    y_post_hp = np.empty(expected_rows, dtype=np.int16)
    y_post_max_hp = np.empty(expected_rows, dtype=np.int16)
    y_max_hp_delta = np.empty(expected_rows, dtype=np.int16)
    y_potions = np.empty((expected_rows, 5), dtype=np.int16)
    y_relic_delta = np.zeros((expected_rows, MAX_RELICS), dtype=np.int16)
    y_relic_mask = np.zeros((expected_rows, MAX_RELICS), dtype=np.bool_)
    supported = np.zeros(expected_rows, dtype=np.bool_)
    source_seed = np.empty(expected_rows, dtype=np.int64)
    fight_idx = np.empty(expected_rows, dtype=np.int16)
    act = np.empty(expected_rows, dtype=np.int8)
    room_class = np.empty(expected_rows, dtype=np.int8)
    encounter = np.empty(expected_rows, dtype=np.int16)
    pre_hp_frac = np.empty(expected_rows, dtype=np.float32)
    pre_max_hp = np.empty(expected_rows, dtype=np.int16)
    potion_capacity = np.empty(expected_rows, dtype=np.int8)
    split_id = np.empty(expected_rows, dtype=np.int8)

    support_by_act: dict = {}
    support_by_room: dict = {}
    support_by_encounter: dict = {}
    support_by_death = {"total": 0, "supported": 0, "fallback": 0}
    reasons: Counter = Counter()
    mutations: Counter = Counter()
    mutation_covered: Counter = Counter()
    gold_mutation_rows: Counter = Counter()
    gold_mutation_covered: Counter = Counter()
    copy_through_violations: Counter = Counter()
    smoke_mutation_without_visible_total = 0
    smoke_mutation_without_visible_supported = 0
    smoke_mutation_without_visible_potion_ids: Counter = Counter()
    smoke_mutation_without_visible_examples: list[dict] = []
    smoke_copy_through_directions: Counter = Counter()
    target_rows: list[dict] = []
    split_rows: list[str] = []
    sampling_fixtures: list[dict] = []
    train_relic_delta_values: dict[str, set[int]] = defaultdict(set)
    train_max_delta_values: set[int] = set()
    row_count = 0
    support_count = 0
    for row in iter_rows(corpus_path):
        if row_count >= expected_rows:
            raise ValueError("corpus has more rows than its manifest")
        pi = row["predictorInput"]
        pre = row["transition"]["pre"]
        post = row["transition"]["post"]
        validate_predictor_input(pi)
        _validate_entity_domains(pi)
        encoded = _encode_row(row)
        g, gc, c, r, p, cm, rm, win, hp, context = encoded
        globals_continuous[row_count] = g
        global_categories[row_count] = gc
        cards[row_count] = c
        card_mask[row_count] = cm
        relics[row_count] = r
        relic_mask[row_count] = rm
        potions[row_count] = p
        outcome = int(row["transition"]["combatOutcome"])
        target = _target_values_from_row(pre, post, outcome)
        y_win[row_count] = int(win)
        y_hp[row_count] = hp if math.isfinite(hp) else np.nan
        y_hp_bin[row_count] = target["hpBin"]
        y_post_hp[row_count] = target["postHp"]
        y_post_max_hp[row_count] = target["postMaxHp"]
        y_max_hp_delta[row_count] = target["maxHpDelta"]
        y_potions[row_count] = target["potions"]
        y_relic_delta[row_count] = target["relicDelta"]
        y_relic_mask[row_count] = target["relicMask"]
        source_seed[row_count] = int(row["sourceSeed"])
        fight_idx[row_count] = int(row["fightIdx"])
        act[row_count] = int(context["act"])
        room_class[row_count] = int(context["roomClass"])
        encounter[row_count] = int(context["encounter"])
        pre_hp_frac[row_count] = context["preHpFrac"]
        pre_max_hp[row_count] = int(pre["maxHp"])
        potion_capacity[row_count] = int(pi["globals"]["potionCapacity"])
        split = split_for_seed(int(row["sourceSeed"]))
        split_rows.append(split)
        split_id[row_count] = {"train": 0, "validation": 1, "test": 2}[split]

        row_reasons = supported_reasons(pi, pre)
        row_supported = not row_reasons
        supported[row_count] = row_supported
        if row_supported:
            support_count += 1
        reasons.update(row_reasons)
        _inc_nested(support_by_act, context["act"], row_supported)
        _inc_nested(support_by_room, context["roomClass"], row_supported)
        _inc_nested(support_by_encounter, context["encounter"], row_supported)
        if outcome == DEATH:
            support_by_death["total"] += 1
            support_by_death["supported"] += int(row_supported)
            support_by_death["fallback"] += int(not row_supported)

        flags, _, _ = persistent_change_flags(pre, post)
        mutation_names = _mutation_names(flags)
        mutations.update(mutation_names)
        if flags["gold_changed"]:
            gold_mutation_rows["gold"] += 1
            if row_supported:
                gold_mutation_covered["gold"] += 1
        if flags["stolen_gold_changed"]:
            gold_mutation_rows["stolenGold"] += 1
            if row_supported:
                gold_mutation_covered["stolenGold"] += 1
        if "smoke_bomb" in mutation_names and not any(
            int(potion["potionId"]) == SMOKE_BOMB_ID for potion in pi["potions"]
        ):
            smoke_mutation_without_visible_total += 1
            if row_supported:
                smoke_mutation_without_visible_supported += 1
            pre_potion_ids = sorted({
                int(potion["potionId"])
                for potion in pi["potions"]
                if int(potion["potionId"]) > 1
            })
            for potion_id in pre_potion_ids:
                smoke_mutation_without_visible_potion_ids[potion_id] += 1
            if len(smoke_mutation_without_visible_examples) < 8:
                smoke_mutation_without_visible_examples.append({
                    "sourceSeed": int(row["sourceSeed"]),
                    "fightIdx": int(row["fightIdx"]),
                    "act": int(context["act"]),
                    "roomClass": int(context["roomClass"]),
                    "encounter": int(context["encounter"]),
                    "prePotionIds": pre_potion_ids,
                    "supported": bool(row_supported),
                })
        if row_supported:
            mutation_covered.update(mutation_names)
            if outcome == WIN:
                violations = _copy_through_violations(pre, post)
                copy_through_violations.update(violations)
                if "smokeBombUsed" in violations:
                    direction = f"{int(bool(pre['smokeBombUsed']))}->{int(bool(post['smokeBombUsed']))}"
                    smoke_copy_through_directions[direction] += 1

        if row_supported and split == "train" and outcome == WIN:
            train_max_delta_values.add(target["maxHpDelta"])
            for relic, delta, active in zip(pre["relics"], target["relicDelta"], target["relicMask"]):
                if active:
                    train_relic_delta_values[str(int(relic["id"]))].add(int(delta))
        if row_supported and split == "test" and outcome == WIN and len(sampling_fixtures) < 128:
            sampling_fixtures.append({"rowIndex": row_count, "pre": pre})
        target_rows.append(target)
        row_count += 1

    if row_count != expected_rows:
        raise ValueError(f"corpus row count mismatch: read {row_count}, expected {expected_rows}")
    preview = {
        "maxHpDeltaValues": sorted(train_max_delta_values),
        "relicDeltaValuesById": {
            key: sorted(values) for key, values in sorted(train_relic_delta_values.items())
        },
    }
    support_report = _audit_summary(
        manifest, row_count, support_count, support_by_act, support_by_room,
        support_by_encounter, support_by_death, reasons, mutations,
        mutation_covered, gold_mutation_rows, gold_mutation_covered,
        copy_through_violations,
        smoke_mutation_without_visible_total,
        smoke_mutation_without_visible_supported,
        smoke_mutation_without_visible_potion_ids,
        smoke_mutation_without_visible_examples,
        smoke_copy_through_directions,
        preview,
    )
    json_dump(out / "support_audit.json", support_report)
    if gold_mutation_covered:
        support_report["status"] = "FAIL"
        support_report["stopReason"] = (
            "predictor-visible support leaves persistent gold mutations supported "
            + json.dumps(dict(gold_mutation_covered), sort_keys=True)
        )
        json_dump(out / "support_audit.json", support_report)
        raise ValueError(support_report["stopReason"])
    if mutation_covered:
        support_report["stopReason"] = (
            "predictor-visible support leaves intentionally omitted mutations "
            + json.dumps(dict(mutation_covered), sort_keys=True)
        )
        json_dump(out / "support_audit.json", support_report)
        raise ValueError(
            "support predicate leaves intentionally omitted mutation rows supported: "
            + json.dumps(dict(mutation_covered), sort_keys=True)
        )
    if copy_through_violations:
        support_report["stopReason"] = (
            "supported victory mutates declared copy-through fields: "
            + json.dumps(dict(copy_through_violations), sort_keys=True)
        )
        json_dump(out / "support_audit.json", support_report)
        raise ValueError(
            "supported victory mutates a declared copy-through field: "
            + json.dumps(dict(copy_through_violations), sort_keys=True)
        )

    # The support mask is included for auditability, but model indices always
    # apply it together with a source split.  Unavailable potion slots are
    # copied/empty at inference and are not learned as transition targets.
    arrays = {
        "globals_continuous": globals_continuous,
        "global_categories": global_categories,
        "cards": cards,
        "card_mask": card_mask,
        "relics": relics,
        "relic_mask": relic_mask,
        "potions": potions,
        "y_win": y_win,
        "y_hp": y_hp,
        "y_hp_bin": y_hp_bin,
        "y_post_hp": y_post_hp,
        "y_post_max_hp": y_post_max_hp,
        "y_max_hp_delta": y_max_hp_delta,
        "y_potions": y_potions,
        "y_relic_delta": y_relic_delta,
        "y_relic_mask": y_relic_mask,
        "supported": supported,
        "sourceSeed": source_seed,
        "fightIdx": fight_idx,
        "act": act,
        "roomClass": room_class,
        "encounter": encounter,
        "preHpFrac": pre_hp_frac,
        "preMaxHp": pre_max_hp,
        "potionCapacity": potion_capacity,
        "split_id": split_id,
    }
    np.savez(out / "prepared.npz", **arrays)
    target_spec = {
        "schemaVersion": PREPARED_SCHEMA,
        "maxHpDeltaValues": sorted(train_max_delta_values),
        "hpBins": list(range(HP_BIN_COUNT)),
        "relicDeltaValues": sorted({value for values in train_relic_delta_values.values() for value in values} | {0}),
        "relicDeltaValuesById": {
            key: sorted(values | {0}) for key, values in sorted(train_relic_delta_values.items())
        },
        "mutableRelicIds": sorted(CODE_AUDITED_MUTABLE_RELIC_IDS),
        "codeAuditedMutableRelicIds": sorted(CODE_AUDITED_MUTABLE_RELIC_IDS),
        "potionCapacityRule": "slot >= pre potionCapacity copies pre slot; active slots use a shared slot-conditioned categorical head",
        "goldRule": "supported gold and stolenGold are exact copy-through fields; gold-changing combats use native fallback",
    }
    json_dump(out / "target_spec.json", target_spec)
    json_dump(out / "sampling_fixtures.json", sampling_fixtures)
    prepared_manifest = {
        "schemaVersion": PREPARED_SCHEMA,
        "supportAudit": str((out / "support_audit.json").resolve()),
        "supportAuditSha256": sha256(out / "support_audit.json"),
        "targetSpec": str((out / "target_spec.json").resolve()),
        "targetSpecSha256": sha256(out / "target_spec.json"),
        "corpusManifest": str(manifest_path.resolve()),
        "corpusManifestSha256": sha256(manifest_path),
        "corpusSha256": manifest["csv"]["sha256"],
        "sourceSplitRule": 'split_for_seed from combat_transition_model_experiment.py; groupKey=sourceSeed',
        "rows": row_count,
        "counts": {
            "all": row_count,
            "supported": int(supported.sum()),
            "fallback": int((~supported).sum()),
            "supportedTrain": int((supported & (split_id == 0)).sum()),
            "supportedValidation": int((supported & (split_id == 1)).sum()),
            "supportedTest": int((supported & (split_id == 2)).sum()),
            "supportedWins": int((supported & (y_win == 1)).sum()),
            "supportedDeaths": int((supported & (y_win == 0)).sum()),
        },
        "encoderInput": {
            "globalsContinuous": list(CONTINUOUS_GLOBAL_FIELDS),
            "globalsCategorical": {field: list(range(GLOBAL_CATEGORY_COUNTS[field])) for field in (
                "characterClass", "encounter", "roomClass", "lastRoom")},
            "cards": {"shape": [MAX_CARDS, 4], "fields": ["cardId", "upgraded", "misc", "bottleBindingPlusOne"], "domain": CARD_COUNT},
            "relics": {"shape": [MAX_RELICS, 3], "fields": ["relicId", "data", "orderIndex"], "domain": RELIC_COUNT},
            "potions": {"shape": [5, 2], "fields": ["slot", "potionId"], "domain": POTION_COUNT},
            "width": 64,
        },
        "eligibilityGuard": {
            "learnedInputSchema": "combat_predictor_input_v1",
            "adapterOnlyPreCombatFields": ["pre.smokeBombUsed"],
            "statement": "pre.smokeBombUsed is a support-gate field and is not learned or encoded",
        },
        "rng": {"included": False, "reason": "combatRng[6] is oracle/provenance state and is not an input or learned output"},
    }
    json_dump(out / "prepared_manifest.json", prepared_manifest)
    print(json.dumps({
        "status": support_report["status"], "rows": row_count,
        "supported": int(supported.sum()), "fallback": int((~supported).sum()),
        "supportedTrain": prepared_manifest["counts"]["supportedTrain"],
        "supportedValidation": prepared_manifest["counts"]["supportedValidation"],
        "supportedTest": prepared_manifest["counts"]["supportedTest"],
        "output": str(out.resolve()),
    }, indent=2, sort_keys=True))


def _binary_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    if len(y) == 0:
        return {"n": 0, "brier": None, "logloss": None, "auc": None}
    return {
        "n": int(len(y)),
        "brier": float(brier_score_loss(y, p)),
        "logloss": float(log_loss(y, p, labels=[0, 1])),
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
    }


def _reg_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    if len(y) == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    error = p - y
    return {
        "n": int(len(y)), "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error * error))), "bias": float(np.mean(error)),
    }


def _core_metrics(arrays: dict, indices: np.ndarray, p_win: np.ndarray,
                  expected_hp_frac: np.ndarray, expected_hp_raw: np.ndarray) -> dict:
    y = arrays["y_win"][indices].astype(np.int8)
    target_frac = np.nan_to_num(arrays["y_hp"][indices], nan=0.0)
    target_raw = arrays["y_post_hp"][indices].astype(np.float32)
    win = y == 1
    return {
        "survival": _binary_metrics(y, p_win),
        "winningExpectedHpFraction": _reg_metrics(target_frac[win], expected_hp_frac[win]),
        "jointAliveHpFraction": _reg_metrics(y * target_frac, p_win * expected_hp_frac),
        "winningExpectedHp": _reg_metrics(target_raw[win], expected_hp_raw[win]),
        "jointAliveHp": _reg_metrics(y * target_raw, p_win * expected_hp_raw),
    }


def _discrete_crps(probabilities: np.ndarray, targets: np.ndarray) -> float:
    cdf = np.cumsum(probabilities, axis=-1)
    bins = np.arange(probabilities.shape[-1])[None, :]
    target_cdf = (bins >= targets[:, None]).astype(np.float32)
    return float(np.mean((cdf - target_cdf) ** 2))


def _quantile_bin(cdf: np.ndarray, quantile: float) -> np.ndarray:
    return np.argmax(cdf >= quantile, axis=-1)


def _hp_distribution_metrics(arrays: dict, indices: np.ndarray, p_bins: np.ndarray,
                              point_fraction: np.ndarray | None = None) -> dict:
    win = arrays["y_win"][indices] == 1
    targets = arrays["y_hp_bin"][indices][win].astype(np.int64)
    probs = p_bins[win]
    if not len(targets):
        return {"n": 0}
    eps = 1e-8
    nll = -np.log(np.maximum(probs[np.arange(len(targets)), targets], eps)).mean()
    cdf = np.cumsum(probs, axis=-1)
    intervals = {}
    for level in (0.50, 0.80, 0.95):
        lower = _quantile_bin(cdf, (1.0 - level) / 2.0)
        upper = _quantile_bin(cdf, 1.0 - (1.0 - level) / 2.0)
        intervals[f"{int(level * 100)}%"] = {
            "coverage": float(np.mean((targets >= lower) & (targets <= upper))),
            "meanWidthBins": float(np.mean(upper - lower)),
        }
    result = {
        "n": int(len(targets)),
        "categoricalNll": float(nll),
        "discreteCrps": _discrete_crps(probs, targets),
        "expectedHpFractionMae": float(np.mean(np.abs((probs @ (np.arange(HP_BIN_COUNT) / 100.0)) - targets / 100.0))),
        "intervals": intervals,
    }
    if point_fraction is not None:
        point_bins = np.clip(_round_half_up_vector(point_fraction[win] * 100.0), 0, 100)
        point_probs = np.zeros_like(probs)
        point_probs[np.arange(len(point_bins)), point_bins] = 1.0
        result["pointControlDegenerateCrps"] = _discrete_crps(point_probs, targets)
        result["crpsImprovementVsPointControl"] = float(result["pointControlDegenerateCrps"] - result["discreteCrps"])
    return result


def _round_half_up_vector(values: np.ndarray) -> np.ndarray:
    return np.floor(values + 0.5).astype(np.int64)


def _phase2_expected(p_delta: np.ndarray, hp_cond: np.ndarray,
                     delta_values: np.ndarray, pre_max_hp: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hp_bins = np.arange(HP_BIN_COUNT, dtype=np.float32) / 100.0
    p_bins = np.einsum("nd,ndb->nb", p_delta, hp_cond)
    expected_frac = p_bins @ hp_bins
    post_max = np.maximum(pre_max_hp[:, None].astype(np.float32) + delta_values[None, :], 1.0)
    expected_raw = np.sum(p_delta * (hp_cond @ (np.arange(HP_BIN_COUNT, dtype=np.float32) / 100.0)) * post_max, axis=1)
    return p_bins, expected_frac, expected_raw


def _safe_state_dict(net) -> dict:
    return {key: value.detach().cpu().clone() for key, value in net.state_dict().items()}


class DeepSetsEncoder:
    """Corrected PR #161 DeepSets representation, returning a width-64 run vector."""

    def __init__(self, nn, torch, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        self.torch = torch
        self.nn = nn
        self.scalar_mean = torch.tensor(scalar_mean, dtype=torch.float32)
        self.scalar_inv = torch.tensor(1.0 / np.maximum(scalar_std, 1e-6), dtype=torch.float32)

        class Encoder(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.outer = outer
                self.register_buffer("scalar_mean", outer.scalar_mean)
                self.register_buffer("scalar_inv", outer.scalar_inv)
                self.card_id = nn.Embedding(CARD_COUNT, 48)
                self.relic_id = nn.Embedding(RELIC_COUNT, 48)
                self.potion_id = nn.Embedding(POTION_COUNT, 32)
                self.potion_slot = nn.Embedding(5, 8)
                self.global_category = nn.ModuleList(
                    nn.Embedding(GLOBAL_CATEGORY_COUNTS[field], 8)
                    for field in ("characterClass", "encounter", "roomClass", "lastRoom")
                )
                self.card_mlp = nn.Sequential(nn.Linear(48 + 3, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.relic_mlp = nn.Sequential(nn.Linear(48 + 2, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.potion_mlp = nn.Sequential(nn.Linear(32 + 8, 64), nn.ReLU(), nn.Linear(64, 64), nn.ReLU())
                self.global_mlp = nn.Sequential(
                    nn.Linear(len(CONTINUOUS_GLOBAL_FIELDS) + 8 * 4, 64), nn.ReLU()
                )
                self.trunk = nn.Sequential(nn.Linear(256, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU())

            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.outer.torch
                cfields = t.cat((c[:, :, 1:2].float(), c[:, :, 2:3].float().clamp(-20, 20) / 20,
                                 c[:, :, 3:4].float() / 3), -1)
                cvec = self.card_mlp(t.cat((self.card_id(c[:, :, 0].long()), cfields), -1))
                cpool = (cvec * cmask.unsqueeze(-1)).sum(1)
                rfields = t.cat((r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1)
                rvec = self.relic_mlp(t.cat((self.relic_id(r[:, :, 0].long()), rfields), -1))
                rpool = (rvec * rmask.unsqueeze(-1)).sum(1)
                pvec = self.potion_mlp(t.cat((self.potion_id(p[:, :, 1].long()), self.potion_slot(p[:, :, 0].long())), -1)).sum(1)
                cats = t.cat([embedding(gc[:, index].long()) for index, embedding in enumerate(self.global_category)], -1)
                gs = (g - self.scalar_mean.to(g.device)) * self.scalar_inv.to(g.device)
                global_vec = self.global_mlp(t.cat((gs, cats), -1))
                return self.trunk(t.cat((cpool, rpool, pvec, global_vec), -1))

        self.net = Encoder(self)


class Phase2Net:
    def __init__(self, torch, target_spec: dict, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn
        self.torch = torch
        self.nn = nn
        self.encoder = DeepSetsEncoder(nn, torch, scalar_mean, scalar_std)
        delta_count = len(target_spec["maxHpDeltaValues"])
        relic_delta_count = len(target_spec["relicDeltaValues"])
        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.torch = outer.torch
                self.encoder = outer.encoder.net
                self.survival = nn.Linear(64, 1)
                self.max_hp_delta = nn.Linear(64, delta_count)
                self.hp_delta_embedding = nn.Embedding(delta_count, 8)
                self.hp = nn.Sequential(nn.Linear(64 + 8, 64), nn.ReLU(), nn.Linear(64, HP_BIN_COUNT))
                self.potion_slot = nn.Embedding(5, 8)
                self.potion = nn.Linear(64 + 8, POTION_COUNT)
                self.relic_token_id = nn.Embedding(RELIC_COUNT, 16)
                self.relic = nn.Sequential(nn.Linear(64 + 16 + 2, 64), nn.ReLU(), nn.Linear(64, relic_delta_count))

            def forward(self, g, gc, c, r, p, cmask, rmask):
                t = self.torch
                z = self.encoder(g, gc, c, r, p, cmask, rmask)
                survival = self.survival(z).squeeze(-1)
                delta = self.max_hp_delta(z)
                hp_inputs = t.cat((z[:, None, :].expand(-1, delta_count, -1),
                                   self.hp_delta_embedding.weight[None, :, :].expand(z.shape[0], -1, -1)), -1)
                hp = self.hp(hp_inputs)
                slot = self.potion_slot.weight[None, :, :].expand(z.shape[0], -1, -1)
                potion = self.potion(t.cat((z[:, None, :].expand(-1, 5, -1), slot), -1))
                rid = r[:, :, 0].long()
                rdata = t.cat((r[:, :, 1:2].float() / 10, r[:, :, 2:3].float() / 64), -1)
                rinputs = t.cat((z[:, None, :].expand(-1, r.shape[1], -1), self.relic_token_id(rid), rdata), -1)
                relic = self.relic(rinputs)
                return survival, delta, hp, potion, relic

        self.net = Net(self)


class PointControlNet:
    def __init__(self, torch, scalar_mean: np.ndarray, scalar_std: np.ndarray):
        import torch.nn as nn
        self.torch = torch
        self.nn = nn
        self.encoder = DeepSetsEncoder(nn, torch, scalar_mean, scalar_std)
        class Net(nn.Module):
            def __init__(self, outer):
                super().__init__()
                self.encoder = outer.encoder.net
                self.survival = nn.Linear(64, 1)
                self.hp = nn.Linear(64, 1)

            def forward(self, g, gc, c, r, p, cmask, rmask):
                z = self.encoder(g, gc, c, r, p, cmask, rmask)
                return self.survival(z).squeeze(-1), self.hp(z).squeeze(-1)
        self.net = Net(self)


def _resolve_device(torch, requested: str) -> str:
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested but CUDA is unavailable")
        return "cuda"
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cpu"


def _load_prepared(prepared_dir: Path) -> tuple[dict, dict]:
    manifest = json.loads((prepared_dir / "prepared_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != PREPARED_SCHEMA:
        raise ValueError("unsupported Phase-2 prepared schema")
    if manifest.get("corpusSha256") != "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde":
        raise ValueError("prepared corpus is not the frozen Phase-2 corpus")
    target_spec = json.loads((prepared_dir / "target_spec.json").read_text(encoding="utf-8"))
    arrays = {key: value for key, value in np.load(prepared_dir / "prepared.npz", allow_pickle=False).items()}
    if len(arrays["y_win"]) != int(manifest["rows"]):
        raise ValueError("prepared array row count disagrees with manifest")
    return arrays, target_spec


def _torch_inputs(arrays: dict, indices: np.ndarray, device: str, torch) -> list:
    return [torch.from_numpy(arrays[key][indices]).to(device, non_blocking=True)
            for key in ("globals_continuous", "global_categories", "cards", "relics", "potions", "card_mask", "relic_mask")]


def _class_index(values: Iterable[int | tuple[int, int]]) -> dict:
    return {value: index for index, value in enumerate(values)}


def _validate_target_support(arrays: dict, target_spec: dict, indices: np.ndarray, label: str) -> dict:
    issues: dict[str, list] = {}
    max_values = set(target_spec["maxHpDeltaValues"])
    observed = sorted(set(int(x) for x in arrays["y_max_hp_delta"][indices][arrays["y_win"][indices] == 1]))
    missing = sorted(set(observed) - max_values)
    if missing:
        issues["maxHpDelta"] = missing
    class_values = set(target_spec["relicDeltaValues"])
    active = arrays["y_relic_mask"][indices] & (arrays["y_win"][indices, None] == 1)
    observed_relic = sorted(set(int(x) for x in arrays["y_relic_delta"][indices][active]))
    missing_relic = sorted(set(observed_relic) - class_values)
    if missing_relic:
        issues["relicDeltaValues"] = missing_relic
    return {"split": label, "unseen": issues, "ok": not issues}


def _new_model(name: str, arrays: dict, target_spec: dict, train_indices: np.ndarray,
               args: argparse.Namespace, device: str):
    import torch
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.training_seed)
    if device == "cuda":
        torch.cuda.manual_seed_all(args.training_seed)
    scalar_mean = arrays["globals_continuous"][train_indices].mean(0)
    scalar_std = arrays["globals_continuous"][train_indices].std(0)
    wrapper = Phase2Net(torch, target_spec, scalar_mean, scalar_std) if name == "phase2" else PointControlNet(torch, scalar_mean, scalar_std)
    wrapper.device = torch.device(device)
    wrapper.net = wrapper.net.to(wrapper.device)
    return wrapper


def _phase2_loss(wrapper, arrays: dict, indices: np.ndarray, args: argparse.Namespace):
    import torch
    values = _torch_inputs(arrays, indices, wrapper.device, torch)
    survival, delta, hp, potion, relic = wrapper.net(*values)
    y_win = torch.from_numpy(arrays["y_win"][indices].astype(np.int64)).to(wrapper.device)
    win = y_win == 1
    if not bool(win.any()):
        raise ValueError("training batch has no victories")
    delta_index = torch.from_numpy(arrays["delta_index"][indices].astype(np.int64)).to(wrapper.device)
    hp_bin = torch.from_numpy(arrays["y_hp_bin"][indices].astype(np.int64)).to(wrapper.device)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(survival, y_win.float())
    loss = loss + torch.nn.functional.cross_entropy(delta[win], delta_index[win])
    hp_rows = hp[torch.arange(len(indices), device=wrapper.device), delta_index.clamp_min(0)]
    loss = loss + torch.nn.functional.cross_entropy(hp_rows[win], hp_bin[win])
    active_potions = torch.from_numpy(
        (np.arange(5)[None, :] < arrays["potionCapacity"][indices, None]) & win.detach().cpu().numpy()[:, None]
    ).to(wrapper.device)
    potion_targets = torch.from_numpy(arrays["y_potions"][indices].astype(np.int64)).to(wrapper.device)
    if bool(active_potions.any()):
        loss = loss + torch.nn.functional.cross_entropy(potion[active_potions], potion_targets[active_potions])
    relic_active = torch.from_numpy(arrays["y_relic_mask"][indices] & win.detach().cpu().numpy()[:, None]).to(wrapper.device)
    relic_targets = torch.from_numpy(
        arrays["relic_delta_index"][indices].astype(np.int64)
    ).to(wrapper.device)
    if bool(relic_active.any()):
        loss = loss + torch.nn.functional.cross_entropy(relic[relic_active], relic_targets[relic_active])
    return loss


def _point_loss(wrapper, arrays: dict, indices: np.ndarray):
    import torch
    values = _torch_inputs(arrays, indices, wrapper.device, torch)
    survival, hp = wrapper.net(*values)
    y_win = torch.from_numpy(arrays["y_win"][indices].astype(np.float32)).to(wrapper.device)
    y_hp = torch.from_numpy(np.nan_to_num(arrays["y_hp"][indices], nan=0.0).astype(np.float32)).to(wrapper.device)
    win = y_win > 0.5
    loss = torch.nn.functional.binary_cross_entropy_with_logits(survival, y_win)
    if bool(win.any()):
        loss = loss + torch.nn.functional.mse_loss(torch.sigmoid(hp)[win], y_hp[win])
    return loss


def _batches(indices: np.ndarray, batch: int, rng: np.random.Generator) -> Iterator[np.ndarray]:
    order = rng.permutation(indices)
    for lo in range(0, len(order), batch):
        yield order[lo:lo + batch]


def _point_predict(wrapper, arrays: dict, indices: np.ndarray, batch: int) -> tuple[np.ndarray, np.ndarray]:
    import torch
    wrapper.net.eval(); ps = []; hs = []
    with torch.no_grad():
        for ids in (indices[lo:lo + batch] for lo in range(0, len(indices), batch)):
            survival, hp = wrapper.net(*_torch_inputs(arrays, ids, wrapper.device, torch))
            ps.append(torch.sigmoid(survival).cpu().numpy()); hs.append(torch.sigmoid(hp).cpu().numpy())
    return np.concatenate(ps), np.concatenate(hs)


def _phase2_predict(wrapper, arrays: dict, indices: np.ndarray, batch: int) -> tuple[np.ndarray, ...]:
    import torch
    wrapper.net.eval(); outputs = [[] for _ in range(5)]
    with torch.no_grad():
        for ids in (indices[lo:lo + batch] for lo in range(0, len(indices), batch)):
            values = wrapper.net(*_torch_inputs(arrays, ids, wrapper.device, torch))
            for out, value in zip(outputs, values):
                out.append(value.cpu().numpy())
    return tuple(np.concatenate(out, axis=0) for out in outputs)


def _prepare_target_indices(arrays: dict, target_spec: dict) -> None:
    delta_index = _class_index(target_spec["maxHpDeltaValues"])
    relic_index = _class_index(target_spec["relicDeltaValues"])
    arrays["delta_index"] = np.asarray([delta_index.get(int(x), -1) for x in arrays["y_max_hp_delta"]], dtype=np.int16)
    arrays["relic_delta_index"] = np.asarray([
        [relic_index.get(int(value), -1) for value in row]
        for row in arrays["y_relic_delta"]
    ], dtype=np.int16)
    supported_wins = arrays["supported"] & (arrays["y_win"] == 1)
    if np.any(arrays["delta_index"][supported_wins] < 0):
        raise ValueError("prepared categorical labels are outside TRAIN target support")
    active_relic = arrays["y_relic_mask"] & supported_wins[:, None]
    if np.any(arrays["relic_delta_index"][active_relic] < 0):
        raise ValueError("prepared relic delta label is outside target support")


def _train_one(name: str, arrays: dict, target_spec: dict, train_indices: np.ndarray,
               val_indices: np.ndarray, args: argparse.Namespace, device: str):
    import torch
    wrapper = _new_model(name, arrays, target_spec, train_indices, args, device)
    optimizer = torch.optim.AdamW(wrapper.net.parameters(), lr=1e-3, weight_decay=1e-4)
    rng = np.random.default_rng(args.training_seed)
    best_state = None
    best_score = math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, args.nn_epochs + 1):
        wrapper.net.train()
        losses = []
        for batch_ids in _batches(train_indices, args.nn_batch, rng):
            loss = _phase2_loss(wrapper, arrays, batch_ids, args) if name == "phase2" else _point_loss(wrapper, arrays, batch_ids)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(wrapper.net.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        metrics = _evaluate_core(wrapper, arrays, target_spec, val_indices, args.nn_batch, name)
        score = metrics["survival"]["brier"] + metrics["winningExpectedHpFraction"]["mae"] + metrics["jointAliveHpFraction"]["mae"]
        print(json.dumps({"family": name, "epoch": epoch, "loss": float(np.mean(losses)), "validationScore": score}, sort_keys=True), flush=True)
        if score < best_score:
            best_state = _safe_state_dict(wrapper.net)
            best_score = score
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
            if stale >= args.nn_patience:
                break
    if best_state is None:
        raise RuntimeError(f"{name} produced no validation checkpoint")
    wrapper.net.load_state_dict(best_state)
    return wrapper, _evaluate_core(wrapper, arrays, target_spec, val_indices, args.nn_batch, name), best_epoch


def _refit_one(name: str, arrays: dict, target_spec: dict, train_indices: np.ndarray,
               epochs: int, args: argparse.Namespace, device: str):
    import torch
    wrapper = _new_model(name, arrays, target_spec, train_indices, args, device)
    optimizer = torch.optim.AdamW(wrapper.net.parameters(), lr=1e-3, weight_decay=1e-4)
    rng = np.random.default_rng(args.training_seed)
    for _ in range(epochs):
        for batch_ids in _batches(train_indices, args.nn_batch, rng):
            loss = _phase2_loss(wrapper, arrays, batch_ids, args) if name == "phase2" else _point_loss(wrapper, arrays, batch_ids)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(wrapper.net.parameters(), 1.0)
            optimizer.step()
    return wrapper


def _evaluate_core(wrapper, arrays: dict, target_spec: dict, indices: np.ndarray,
                   batch: int, name: str) -> dict:
    if name == "point":
        p, h = _point_predict(wrapper, arrays, indices, batch)
        metrics = _core_metrics(arrays, indices, p, h, h * arrays["preMaxHp"][indices])
        metrics["hpDistribution"] = _hp_distribution_metrics(
            arrays, indices,
            np.eye(HP_BIN_COUNT, dtype=np.float32)[np.clip(_round_half_up_vector(h * 100), 0, 100)],
            point_fraction=h,
        )
        return metrics
    survival, delta, hp, potion, relic = _phase2_predict(wrapper, arrays, indices, batch)
    p_win = 1.0 / (1.0 + np.exp(-survival))
    p_delta = _softmax(delta)
    hp_cond = _softmax(hp)
    delta_values = np.asarray(target_spec["maxHpDeltaValues"], dtype=np.float32)
    p_bins, expected_frac, expected_raw = _phase2_expected(p_delta, hp_cond, delta_values, arrays["preMaxHp"][indices])
    metrics = _core_metrics(arrays, indices, p_win, expected_frac, expected_raw)
    # Marginalized HP bins are the distribution used by a rollout sampler when
    # it samples delta first and then the corresponding conditional HP head.
    metrics["hpDistribution"] = _hp_distribution_metrics(
        arrays, indices, p_bins,
        point_fraction=None,
    )
    metrics["predictions"] = {
        "pWin": p_win, "pDelta": p_delta, "hpConditional": hp_cond,
        "potionLogits": potion, "relicLogits": relic,
        "pHpBins": p_bins, "expectedHpFraction": expected_frac, "expectedHp": expected_raw,
    }
    return metrics


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    values = np.exp(shifted)
    return values / np.sum(values, axis=-1, keepdims=True)


def _valid_potion_probabilities(logits: np.ndarray) -> np.ndarray:
    """Mask INVALID while retaining the canonical empty-slot class (ID 1)."""
    probabilities = _softmax(logits).copy()
    probabilities[..., 0] = 0.0
    normalizer = probabilities.sum(axis=-1, keepdims=True)
    fallback = np.zeros_like(probabilities)
    fallback[..., EMPTY_POTION_SLOT_ID] = 1.0
    return np.divide(probabilities, normalizer, out=fallback, where=normalizer > 0)


def _accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    if y_true.ndim != 1 or y_pred.ndim != 1:
        raise ValueError("_accuracy requires one scalar/boolean value per row; use _exact_accuracy for structured states")
    return None if len(y_true) == 0 else float(np.mean(y_true == y_pred))


def _exact_accuracy(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Average one structured exact-match boolean per row."""
    actual = np.asarray(actual)
    predicted = np.asarray(predicted)
    if actual.shape != predicted.shape:
        raise ValueError(f"structured exact-match shapes differ: {actual.shape} != {predicted.shape}")
    if actual.ndim == 0:
        raise ValueError("structured exact-match inputs must contain rows")
    row_exact = actual == predicted if actual.ndim == 1 else np.all(
        actual == predicted, axis=tuple(range(1, actual.ndim))
    )
    return _accuracy(row_exact, np.ones(len(row_exact), dtype=bool))


def _masked_relic_probabilities(logits: np.ndarray, arrays: dict, indices: np.ndarray,
                                target_spec: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    probs = _softmax(logits)
    class_values = np.asarray(target_spec["relicDeltaValues"], dtype=np.int64)
    mode = np.zeros(logits.shape[:2], dtype=np.int16)
    target = arrays["y_relic_delta"][indices]
    for row in range(len(indices)):
        for token in range(logits.shape[1]):
            if not arrays["y_relic_mask"][indices[row], token]:
                continue
            rid = int(arrays["relics"][indices[row], token, 0])
            allowed = set(target_spec["relicDeltaValuesById"].get(str(rid), [0]))
            mask = np.asarray([int(value) in allowed for value in class_values])
            local = logits[row, token].copy()
            local[~mask] = -np.inf
            local_prob = _softmax(local[None, :])[0]
            probs[row, token] = local_prob
            mode[row, token] = class_values[int(np.argmax(local_prob))]
    return probs, mode, target


def _transition_metrics(arrays: dict, target_spec: dict, indices: np.ndarray,
                        predictions: dict, test_rows: int) -> dict:
    win_mask = arrays["y_win"][indices] == 1
    ids = indices[win_mask]
    if not len(ids):
        raise ValueError("TEST has no supported victories for transition evaluation")
    local = np.flatnonzero(win_mask)
    p_delta = predictions["pDelta"][local]
    delta_values = np.asarray(target_spec["maxHpDeltaValues"], dtype=np.int16)
    mode_delta = delta_values[np.argmax(p_delta, axis=1)]
    hp_cond = predictions["hpConditional"][local]
    mode_delta_index = np.argmax(p_delta, axis=1)
    mode_hp_bin = np.argmax(hp_cond[np.arange(len(ids)), mode_delta_index], axis=1).astype(np.int16)
    actual_hp_bin = arrays["y_hp_bin"][ids]
    pre_hp_bin = _round_half_up_vector(
        arrays["preHpFrac"][ids].astype(np.float64) * 100.0
    ).astype(np.int16)
    predicted_max_hp = arrays["preMaxHp"][ids].astype(np.int32) + mode_delta.astype(np.int32)
    predicted_hp = np.clip(_round_half_up_vector(mode_hp_bin / 100.0 * predicted_max_hp), 1, predicted_max_hp)
    actual_max_hp = arrays["y_post_max_hp"][ids]
    actual_hp = arrays["y_post_hp"][ids]
    hp_pair = {
        "predictedModeMaxHpAccuracy": _accuracy(actual_max_hp, predicted_max_hp),
        "predictedModeHpAccuracy": _accuracy(actual_hp, predicted_hp),
        "predictedModeHpMaxHpExactAccuracy": _exact_accuracy(
            np.stack((actual_hp, actual_max_hp), axis=1),
            np.stack((predicted_hp, predicted_max_hp), axis=1),
        ),
        "copyThroughBaseline": {
            "maxHpAccuracy": _accuracy(actual_max_hp, arrays["preMaxHp"][ids]),
            "hpAccuracy": _accuracy(actual_hp, np.clip(_round_half_up_vector(arrays["preHpFrac"][ids] * arrays["preMaxHp"][ids]), 1, arrays["preMaxHp"][ids])),
            "hpMaxHpExactAccuracy": _exact_accuracy(
                np.stack((actual_hp, actual_max_hp), axis=1),
                np.stack((np.clip(_round_half_up_vector(arrays["preHpFrac"][ids] * arrays["preMaxHp"][ids]), 1, arrays["preMaxHp"][ids]), arrays["preMaxHp"][ids]), axis=1),
            ),
        },
    }

    # Potions: active slots are learned; unavailable slots retain their input
    # value (valid source states are empty there).
    potion_probs = _valid_potion_probabilities(predictions["potionLogits"][local])
    predicted_potions = np.zeros((len(ids), 5), dtype=np.int16)
    for row, original in enumerate(ids):
        cap = int(arrays["potionCapacity"][original])
        for slot in range(5):
            predicted_potions[row, slot] = (
                int(np.argmax(potion_probs[row, slot]))
                if slot < cap else int(arrays["potions"][original, slot, 1])
            )
    actual_potions = arrays["y_potions"][ids]
    slot_metrics = {}
    for slot in range(5):
        active = arrays["potionCapacity"][ids] > slot
        target = actual_potions[:, slot]
        logloss = float(-np.log(np.maximum(potion_probs[active, slot, target[active]], 1e-8)).mean()) if active.any() else None
        slot_metrics[str(slot)] = {
            "n": int(active.sum()), "active": bool(active.any()), "logLoss": logloss,
            "accuracy": _accuracy(target[active], predicted_potions[active, slot]),
            "forcedUnavailableAccuracy": _accuracy(target[~active], predicted_potions[~active, slot]),
        }
    potion_changed = np.any(actual_potions != arrays["potions"][ids, :, 1], axis=1)
    potion_exact = np.all(predicted_potions == actual_potions, axis=1)
    potion_baseline = arrays["potions"][ids, :, 1]
    potion_count = np.sum(predicted_potions > EMPTY_POTION_SLOT_ID, axis=1)
    actual_count = np.sum(actual_potions > EMPTY_POTION_SLOT_ID, axis=1)
    potion_metrics = {
        "perSlot": slot_metrics,
        "exactFullVectorAccuracy": _exact_accuracy(actual_potions, predicted_potions),
        "changedRowCount": int(potion_changed.sum()),
        "changedRowAccuracy": _accuracy(potion_exact[potion_changed], np.ones(int(potion_changed.sum()), dtype=bool)),
        "potionCountAccuracy": _accuracy(actual_count, potion_count),
        "copyThroughBaseline": {
            "exactFullVectorAccuracy": _exact_accuracy(actual_potions, potion_baseline),
            "changedRowAccuracy": _accuracy(np.all(potion_baseline[potion_changed] == actual_potions[potion_changed], axis=1), np.ones(int(potion_changed.sum()), dtype=bool)),
            "potionCountAccuracy": _accuracy(actual_count, np.sum(potion_baseline > EMPTY_POTION_SLOT_ID, axis=1)),
        },
    }

    relic_probs, predicted_relic_delta, actual_relic_delta = _masked_relic_probabilities(
        predictions["relicLogits"][local], arrays, ids, target_spec
    )
    actual_relic_vector = arrays["relics"][ids, :, 1]
    predicted_relic_vector = actual_relic_vector + predicted_relic_delta
    active_relic = arrays["y_relic_mask"][ids]
    changed_relic = active_relic & (actual_relic_delta != 0)
    target_indices = np.asarray([
        [_class_index(target_spec["relicDeltaValues"]).get(int(value), -1) for value in row]
        for row in actual_relic_delta
    ])
    token_logloss_values = []
    token_accuracy_values = []
    for row in range(len(ids)):
        for token in range(MAX_RELICS):
            if not active_relic[row, token]:
                continue
            token_logloss_values.append(-math.log(max(float(relic_probs[row, token, target_indices[row, token]]), 1e-8)))
            token_accuracy_values.append(bool(predicted_relic_delta[row, token] == actual_relic_delta[row, token]))
    relic_exact = np.all(predicted_relic_vector == actual_relic_vector, axis=1)
    relic_baseline_exact = np.all(arrays["relics"][ids, :, 1] == actual_relic_vector, axis=1)
    changed_values = np.abs(predicted_relic_delta[changed_relic] - actual_relic_delta[changed_relic])
    relic_metrics = {
        "mutableTokenCount": int(active_relic.sum()),
        "perTokenLogLoss": float(np.mean(token_logloss_values)) if token_logloss_values else None,
        "perTokenAccuracy": float(np.mean(token_accuracy_values)) if token_accuracy_values else None,
        "exactAllCounterVectorAccuracy": _accuracy(relic_exact, np.ones(len(relic_exact), dtype=bool)),
        "changedCounterTokenCount": int(changed_relic.sum()),
        "changedCounterAccuracy": float(np.mean(predicted_relic_delta[changed_relic] == actual_relic_delta[changed_relic])) if changed_relic.any() else None,
        "changedCounterMae": float(np.mean(changed_values)) if changed_values.size else None,
        "copyThroughBaseline": {
            "exactAllCounterVectorAccuracy": _accuracy(relic_baseline_exact, np.ones(len(relic_baseline_exact), dtype=bool)),
            "changedCounterAccuracy": 0.0 if changed_relic.any() else None,
            "changedCounterMae": float(np.mean(np.abs(actual_relic_delta[changed_relic]))) if changed_relic.any() else None,
        },
    }

    # Compare one boolean per supported TEST victory. Structured vectors are
    # exact only when every modeled field matches on that row.
    joint_exact = (
        (predicted_max_hp == actual_max_hp) & (predicted_hp == actual_hp)
        & np.all(predicted_potions == actual_potions, axis=1)
        & np.all(predicted_relic_vector == actual_relic_vector, axis=1)
    )
    copy_joint = (
        (arrays["preMaxHp"][ids] == actual_max_hp)
        & (np.clip(_round_half_up_vector(arrays["preHpFrac"][ids] * arrays["preMaxHp"][ids]), 1, arrays["preMaxHp"][ids]) == actual_hp)
        & np.all(potion_baseline == actual_potions, axis=1)
        & np.all(arrays["relics"][ids, :, 1] == actual_relic_vector, axis=1)
    )
    return {
        "nSupportedTestVictories": int(len(ids)),
        "hpMaxHp": hp_pair,
        "potions": potion_metrics,
        "relicCounters": relic_metrics,
        "allModeledPersistentFieldsExactAccuracy": _accuracy(joint_exact, np.ones(len(joint_exact), dtype=bool)),
        "copyThroughBaseline": {
            "allModeledPersistentFieldsExactAccuracy": _accuracy(copy_joint, np.ones(len(copy_joint), dtype=bool)),
        },
        "modeDetails": {
            "maxHpDeltaValues": delta_values.tolist(),
            "predictedHpBinRange": [int(mode_hp_bin.min()), int(mode_hp_bin.max())],
        },
    }


def _sample_persistent_transition(pre: dict, prediction: dict, target_spec: dict,
                                  rng: np.random.Generator) -> dict | None:
    if float(rng.random()) >= float(prediction["pWin"]):
        return None
    delta_values = np.asarray(target_spec["maxHpDeltaValues"], dtype=np.int32)
    delta_index = int(rng.choice(len(delta_values), p=np.asarray(prediction["pDelta"], dtype=np.float64)))
    post = {key: copy.deepcopy(pre[key]) for key in PERSISTENT_KEYS if key != "combatRng"}
    post_max = int(pre["maxHp"]) + int(delta_values[delta_index])
    if post_max <= 0:
        raise ValueError("sampled maxHp is not positive")
    hp_probs = np.asarray(prediction["hpConditional"][delta_index], dtype=np.float64)
    hp_bin = int(rng.choice(HP_BIN_COUNT, p=hp_probs))
    post["maxHp"] = post_max
    sampled_hp = _round_half_up((hp_bin / 100.0) * post_max)
    post["curHp"] = max(1, min(post_max, sampled_hp))
    # Gold-changing combats are outside support; supported states copy both
    # persistent gold fields exactly rather than sampling a TRAIN-derived class.
    post["gold"] = int(pre["gold"])
    post["stolenGold"] = int(pre["stolenGold"])
    potion_probs = np.asarray(prediction["potionProbs"], dtype=np.float64)
    capacity = int(pre["potionCapacity"])
    for slot in range(5):
        if slot < capacity:
            probabilities = potion_probs[slot].copy()
            probabilities[0] = 0.0  # Potion::INVALID is not a valid persistent slot value.
            if probabilities.sum() <= 0:
                probabilities[EMPTY_POTION_SLOT_ID] = 1.0
            probabilities /= probabilities.sum()
            post["potions"][slot] = int(rng.choice(POTION_COUNT, p=probabilities))
        else:
            post["potions"][slot] = int(pre["potions"][slot])
    post["potionCount"] = int(sum(value > EMPTY_POTION_SLOT_ID for value in post["potions"]))
    relic_values = np.asarray(target_spec["relicDeltaValues"], dtype=np.int32)
    relic_probs = prediction.get("relicDeltaProbs", {})
    for index, relic in enumerate(post["relics"]):
        rid = int(relic["id"])
        allowed = set(target_spec["relicDeltaValuesById"].get(str(rid), [0]))
        if rid not in CODE_AUDITED_MUTABLE_RELIC_IDS:
            continue
        probs = np.asarray(relic_probs.get(str(rid), np.eye(1, len(relic_values), int(np.flatnonzero(relic_values == 0)[0]))[0]), dtype=np.float64)
        mask = np.asarray([int(value) in allowed for value in relic_values])
        probs = np.where(mask, probs, 0.0)
        if probs.sum() <= 0:
            probs = mask.astype(np.float64)
        probs /= probs.sum()
        relic["data"] = int(relic["data"]) + int(rng.choice(relic_values, p=probs))
    return post


def validate_sampled_state(pre: dict, sampled: dict, target_spec: dict) -> None:
    if "combatRng" in sampled:
        raise ValueError("sampled surrogate state must not invent or copy combatRng")
    if sampled["smokeBombUsed"] != pre["smokeBombUsed"]:
        raise ValueError("sampled smokeBombUsed is not copy-through")
    if not (1 <= int(sampled["curHp"]) <= int(sampled["maxHp"])):
        raise ValueError("sampled HP is outside [1, maxHp]")
    if int(sampled["gold"]) < 0 or int(sampled["stolenGold"]) < 0:
        raise ValueError("sampled gold state is negative")
    if len(sampled["potions"]) != 5 or any(not EMPTY_POTION_SLOT_ID <= int(value) < POTION_COUNT for value in sampled["potions"]):
        raise ValueError("sampled potion ID is outside the canonical domain")
    if int(sampled["potionCount"]) != sum(int(value) > EMPTY_POTION_SLOT_ID for value in sampled["potions"]):
        raise ValueError("sampled potionCount is not derived from potion slots")
    if int(sampled["potionCount"]) > int(sampled["potionCapacity"]):
        raise ValueError("sampled potionCount exceeds potionCapacity")
    for slot in range(int(sampled["potionCapacity"]), 5):
        if int(sampled["potions"][slot]) != int(pre["potions"][slot]):
            raise ValueError("sampled unavailable potion slot was not copy-through")
    if int(sampled["potionCapacity"]) != int(pre["potionCapacity"]):
        raise ValueError("sampled potionCapacity is not copy-through")
    for key in COPY_THROUGH_KEYS:
        if sampled[key] != pre[key]:
            raise ValueError(f"sampled copy-through field mutated: {key}")
    if [(x["id"], i) for i, x in enumerate(sampled["relics"])] != [(x["id"], i) for i, x in enumerate(pre["relics"])]:
        raise ValueError("sampled relic identity/order mutated")
    for index, relic in enumerate(sampled["relics"]):
        rid = int(relic["id"])
        if rid not in CODE_AUDITED_MUTABLE_RELIC_IDS and relic["data"] != pre["relics"][index]["data"]:
            raise ValueError("sampled immutable relic counter mutated")
        if rid in CODE_AUDITED_MUTABLE_RELIC_IDS:
            delta = int(relic["data"]) - int(pre["relics"][index]["data"])
            if delta not in set(target_spec["relicDeltaValuesById"].get(str(rid), [0])):
                raise ValueError("sampled relic counter used an unsupported delta class")


def _sampled_state_check(arrays: dict, target_spec: dict, fixtures: list[dict],
                         test_indices: np.ndarray, predictions: dict,
                         args: argparse.Namespace) -> dict:
    rng = np.random.default_rng(args.sampling_seed)
    samples = 0
    attempts = 0
    invalid = []
    test_position = {int(index): position for position, index in enumerate(test_indices)}
    for fixture in fixtures[: min(len(fixtures), 128)]:
        if samples >= 16:
            break
        row_index = int(fixture["rowIndex"])
        if row_index not in test_position:
            raise ValueError("sampling fixture is not a supported TEST row")
        local = test_position[row_index]
        attempts += 1
        prediction = {
            "pWin": float(predictions["pWin"][local]),
            "pDelta": predictions["pDelta"][local],
            "hpConditional": predictions["hpConditional"][local],
            "potionProbs": _valid_potion_probabilities(predictions["potionLogits"][local]),
            "relicDeltaProbs": {},
        }
        relic_logits = predictions["relicLogits"][local]
        relic_class_values = np.asarray(target_spec["relicDeltaValues"], dtype=np.int32)
        for token, relic in enumerate(arrays["relics"][row_index]):
            rid = int(relic[0])
            if rid in CODE_AUDITED_MUTABLE_RELIC_IDS:
                allowed = set(target_spec["relicDeltaValuesById"].get(str(rid), [0]))
                mask = np.asarray([int(value) in allowed for value in relic_class_values])
                logits = relic_logits[token].copy(); logits[~mask] = -np.inf
                prediction["relicDeltaProbs"][str(rid)] = _softmax(logits[None, :])[0]
        pre = fixture["pre"]
        sampled = _sample_persistent_transition(pre, prediction, target_spec, rng)
        if sampled is None:
            continue
        try:
            validate_sampled_state(pre, sampled, target_spec)
            samples += 1
        except ValueError as exc:
            invalid.append(str(exc))
    return {"attempts": attempts, "sampledStates": samples, "invalidStates": invalid, "valid": not invalid and samples >= 16}


def _measure_latency(wrapper, arrays: dict, index: int, args: argparse.Namespace) -> float:
    import torch
    wrapper.net.eval()
    ids = np.asarray([index], dtype=np.int64)
    values = _torch_inputs(arrays, ids, wrapper.device, torch)
    with torch.no_grad():
        for _ in range(10):
            wrapper.net(*values)
        if wrapper.device.type == "cuda":
            torch.cuda.synchronize(wrapper.device)
        start = time.perf_counter()
        for _ in range(50):
            wrapper.net(*values)
        if wrapper.device.type == "cuda":
            torch.cuda.synchronize(wrapper.device)
    return float((time.perf_counter() - start) * 1000 / 50)


def _decision_classification(core: dict, point: dict, transition: dict) -> dict:
    # The handoff did not preregister numerical materiality margins.  This
    # conservative reporting rule is explicit: allow at most 5% relative core
    # error increase (or 0.005 absolute Brier), require a strict HP CRPS gain,
    # and require both overall and changed-slice gains for each sparse head.
    def not_materially_worse(name: str) -> bool:
        a = core[name]["mae"]
        b = point[name]["mae"]
        if b is None or a is None:
            return False
        return a <= b * 1.05 + (0.005 if name == "survival" else 0.0)
    core_ok = (
        core["survival"]["brier"] <= point["survival"]["brier"] * 1.05 + 0.005
        and not_materially_worse("winningExpectedHpFraction")
        and not_materially_worse("jointAliveHpFraction")
    )
    hp_improves = core["hpDistribution"].get("discreteCrps", math.inf) < point["hpDistribution"].get("pointControlDegenerateCrps", math.inf)
    pot = transition["potions"]
    rel = transition["relicCounters"]
    sparse_ok = (
        pot["exactFullVectorAccuracy"] > pot["copyThroughBaseline"]["exactFullVectorAccuracy"]
        and (pot["changedRowAccuracy"] or 0.0) > (pot["copyThroughBaseline"]["changedRowAccuracy"] or 0.0)
        and rel["exactAllCounterVectorAccuracy"] > rel["copyThroughBaseline"]["exactAllCounterVectorAccuracy"]
        and (rel["changedCounterAccuracy"] or 0.0) > (rel["copyThroughBaseline"]["changedCounterAccuracy"] or 0.0)
    )
    if not core_ok:
        classification = "CORE_REGRESSION"
    elif not hp_improves or not sparse_ok:
        classification = "PHASE2_PARTIAL"
    else:
        classification = "PHASE2_PASS"
    return {
        "classification": classification,
        "rule": "core <= point-control plus 5% relative/0.005 Brier tolerance; HP CRPS strict improvement; potion and relic primary and changed-slice accuracy strictly beat copy-through; gold/stolenGold are support-gated copy-through fields",
        "coreNotMateriallyWorse": core_ok,
        "hpDistributionImproves": hp_improves,
        "sparseHeadsBeatCopyThrough": sparse_ok,
    }


def fit(args: argparse.Namespace) -> None:
    import torch
    arrays, target_spec = _load_prepared(Path(args.prepared_dir))
    _prepare_target_indices(arrays, target_spec)
    all_train = np.flatnonzero((arrays["split_id"] == 0) & arrays["supported"])
    all_val = np.flatnonzero((arrays["split_id"] == 1) & arrays["supported"])
    all_test = np.flatnonzero((arrays["split_id"] == 2) & arrays["supported"])
    for label, indices in (("train", all_train), ("validation", all_val), ("test", all_test)):
        support = _validate_target_support(arrays, target_spec, indices, label)
        if not support["ok"]:
            raise ValueError(f"unseen target support in {label}: {json.dumps(support['unseen'], sort_keys=True)}")
    device = _resolve_device(torch, args.device)
    print(json.dumps({"device": device, "supportedRows": {"train": len(all_train), "validation": len(all_val), "test": len(all_test)}}, sort_keys=True), flush=True)
    phase2_val_model, phase2_val, phase2_epochs = _train_one("phase2", arrays, target_spec, all_train, all_val, args, device)
    point_val_model, point_val, point_epochs = _train_one("point", arrays, target_spec, all_train, all_val, args, device)
    combined = np.concatenate((all_train, all_val))
    phase2 = _refit_one("phase2", arrays, target_spec, combined, phase2_epochs, args, device)
    point = _refit_one("point", arrays, target_spec, combined, point_epochs, args, device)
    phase2_test = _evaluate_core(phase2, arrays, target_spec, all_test, args.nn_batch, "phase2")
    point_test = _evaluate_core(point, arrays, target_spec, all_test, args.nn_batch, "point")
    phase2_predictions = phase2_test.pop("predictions")
    transition = _transition_metrics(arrays, target_spec, all_test, phase2_predictions, len(all_test))
    fixtures = json.loads((Path(args.prepared_dir) / "sampling_fixtures.json").read_text(encoding="utf-8"))
    sampling = _sampled_state_check(arrays, target_spec, fixtures, all_test, phase2_predictions, args)
    if not sampling["valid"]:
        raise ValueError("sampled surrogate states failed validity gate: " + json.dumps(sampling, sort_keys=True))
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    phase2_model_path = out / "phase2_deepsets.pt"
    point_model_path = out / "point_control_deepsets.pt"
    torch.save({"schemaVersion": MODEL_SCHEMA, "family": "phase2", "stateDict": _safe_state_dict(phase2.net), "targetSpec": target_spec}, phase2_model_path)
    torch.save({"schemaVersion": MODEL_SCHEMA, "family": "point_control", "stateDict": _safe_state_dict(point.net)}, point_model_path)
    latency_ms = _measure_latency(phase2, arrays, int(all_test[0]), args)
    evidence = {
        "schemaVersion": MODEL_SCHEMA,
        "baselineHeadSha": args.baseline_head_sha,
        "frozenCorpusSha256": "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde",
        "frozenSourceSplitSha256": "e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32",
        "preparedManifest": str((Path(args.prepared_dir) / "prepared_manifest.json").resolve()),
        "preparedManifestSha256": sha256(Path(args.prepared_dir) / "prepared_manifest.json"),
        "support": json.loads((Path(args.prepared_dir) / "support_audit.json").read_text(encoding="utf-8")),
        "targets": target_spec,
        "protocol": {
            "train": "supported TRAIN rows only",
            "validation": "supported VALIDATION rows only; early stopping and epoch freeze",
            "finalFit": "supported TRAIN+VALIDATION rows, exact frozen epoch count, from scratch",
            "test": "supported fixed TEST rows, evaluated once after final refit",
            "trainingSeed": int(args.training_seed), "samplingSeed": int(args.sampling_seed),
            "device": device, "threads": int(args.threads), "batch": int(args.nn_batch),
            "maxEpochs": int(args.nn_epochs), "patience": int(args.nn_patience),
            "noArchitectureSweep": True, "attentionRerun": False, "newData": False,
        },
        "counts": {
            "supportedTrain": int(len(all_train)), "supportedValidation": int(len(all_val)),
            "supportedTest": int(len(all_test)), "combinedFit": int(len(combined)),
        },
        "validation": {
            "phase2": {**phase2_val, "selectedEpochs": int(phase2_epochs)},
            "pointControl": {**point_val, "selectedEpochs": int(point_epochs)},
        },
        "test": {
            "phase2": phase2_test,
            "pointControl": point_test,
            "transition": transition,
            "testSplitNote": "fixed engineering TEST already used for Phase-1 representation work; not a fresh representation-selection holdout",
        },
        "artifacts": {
            "phase2Model": {"path": str(phase2_model_path.resolve()), "bytes": phase2_model_path.stat().st_size, "sha256": sha256(phase2_model_path)},
            "pointControlModel": {"path": str(point_model_path.resolve()), "bytes": point_model_path.stat().st_size, "sha256": sha256(point_model_path)},
            "batch1LatencyMsOnFitDevice": latency_ms,
        },
        "rngContract": {
            "combatRngIncluded": False,
            "statement": "A later runtime adapter requires a separate stochastic RNG-continuation contract before multi-fight surrogate rollouts are scientifically valid.",
        },
    }
    evidence["decision"] = _decision_classification(
        phase2_test, point_test, transition
    )
    evidence["sampling"] = sampling
    json_dump(out / "phase2_evidence.json", evidence)
    print(json.dumps({
        "classification": evidence["decision"]["classification"],
        "phase2Epochs": phase2_epochs, "pointControlEpochs": point_epochs,
        "phase2ModelBytes": phase2_model_path.stat().st_size,
        "pointControlModelBytes": point_model_path.stat().st_size,
        "batch1LatencyMsOnFitDevice": latency_ms,
        "output": str(out.resolve()),
    }, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--corpus-manifest", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--expected-corpus-sha256", default="74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde")
    p.set_defaults(func=prepare)
    p = sub.add_parser("fit")
    p.add_argument("--prepared-dir", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--nn-batch", type=int, default=2048)
    p.add_argument("--nn-epochs", type=int, default=12)
    p.add_argument("--nn-patience", type=int, default=3)
    p.add_argument("--training-seed", type=int, default=20260912)
    p.add_argument("--sampling-seed", type=int, default=20260913)
    p.add_argument("--baseline-head-sha", default="58250bdb2e93c2c69b6556f408eb54ef5230639c")
    p.set_defaults(func=fit)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
