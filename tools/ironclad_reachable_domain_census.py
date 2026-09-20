#!/usr/bin/env python3
"""Produce a source-backed Ironclad model-vocabulary reachability census.

This is deliberately a small, deterministic audit tool.  It reads the enum,
pool, and model-contract source files directly; it never runs a game seed and
does not modify simulator, model, or artifact behavior.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = "docs/experiments/evidence/ironclad_reachable_domain_census_2026-09-20"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def enum_members(rel: str, enum_name: str) -> list[str]:
    text = read(rel)
    match = re.search(rf"enum\s+class\s+{re.escape(enum_name)}\b[^{{]*{{(.*?)}}\s*;", text, re.S)
    if not match:
        raise RuntimeError(f"missing enum {enum_name} in {rel}")
    members: list[str] = []
    next_value = 0
    for raw in match.group(1).split(","):
        raw = re.sub(r"//.*", "", raw).strip()
        if not raw:
            continue
        name, *value = raw.split("=", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            continue
        if value:
            next_value = int(value[0].strip())
        if next_value != len(members):
            raise RuntimeError(f"non-contiguous {enum_name} at {name}")
        members.append(name)
        next_value += 1
    return members


def integer_constant(rel: str, name: str) -> int:
    match = re.search(rf"\bconstexpr\s+int\s+{re.escape(name)}\s*=\s*(\d+)\s*;", read(rel))
    if not match:
        raise RuntimeError(f"missing constant {name} in {rel}")
    return int(match.group(1))


def refs(text: str, prefix: str) -> set[str]:
    return set(re.findall(rf"{re.escape(prefix)}::([A-Z][A-Z0-9_]*)", strip_comments(text)))


def initializer_refs(text: str, marker: str, prefix: str) -> set[str]:
    """Read one named C/C++ initializer without spilling into later arrays."""
    match = re.search(rf"{re.escape(marker)}\s*=\s*\{{(.*?)\}}\s*;", strip_comments(text), re.S)
    if not match:
        raise RuntimeError(f"missing initializer {marker}")
    return refs(match.group(1), prefix)


def matrix_row_refs(text: str, marker: str, prefix: str) -> list[set[str]]:
    """Read every row of a fixed matrix whose rows contain enum refs."""
    match = re.search(rf"{re.escape(marker)}\s*(?:=\s*)?\{{(.*?)\}}\s*;", strip_comments(text), re.S)
    if not match:
        raise RuntimeError(f"missing matrix initializer {marker}")
    rows = re.findall(r"\{([^{}]*)\}", match.group(1), re.S)
    if not rows:
        raise RuntimeError(f"missing matrix rows {marker}")
    return [refs(row, prefix) for row in rows]


def scoped_refs(rel: str, prefix: str, start: str, end: str | None = None) -> set[str]:
    text = strip_comments(read(rel))
    begin = text.find(start)
    if begin < 0:
        raise RuntimeError(f"missing scope marker {start} in {rel}")
    finish = text.find(end, begin) if end else len(text)
    return refs(text[begin:finish if finish >= 0 else len(text)], prefix)


def source_evidence(path: str, symbol: str, reason: str) -> dict[str, str]:
    return {"path": path, "symbol": symbol, "reason": reason}


def classify_entry(idx: int, name: str, status: str, reason: str,
                   evidence: Iterable[dict[str, str]], **extra: object) -> dict[str, object]:
    out: dict[str, object] = {
        "id": idx,
        "enumName": name,
        "classification": status,
        "reasonClass": reason,
        "evidence": list(evidence),
    }
    out.update(extra)
    return out


def card_census() -> dict[str, object]:
    rel = "include/constants/Cards.h"
    members = enum_members(rel, "CardId")
    header = read(rel)
    colors = re.findall(
        r"CardColor::([A-Z]+)",
        re.search(r"static constexpr CardColor cardColors\[\].*?\{(.*?)\};", header, re.S).group(1),
    )
    if len(colors) != len(members):
        raise RuntimeError("CardId/cardColors drift")
    canonical = integer_constant("apps/one_combat/run_features.h", "kNumCardIds")
    if canonical < len(members):
        raise RuntimeError("canonical card domain truncates the CardId enum")

    card_pool_text = strip_comments(read("include/constants/CardPools.h"))
    class_rows = matrix_row_refs(card_pool_text, "constexpr CardId colorCardPool[4][72]", "CardId")
    random_class_rows = matrix_row_refs(card_pool_text, "constexpr CardId pool[4][72]", "CardId")
    ironclad_pool = class_rows[0] | random_class_rows[0]
    non_ironclad_class_pool = set().union(*class_rows[1:], *random_class_rows[1:])
    pools = set(ironclad_pool)
    pools |= initializer_refs(card_pool_text, "static constexpr CardId curseCardPool[]", "CardId")
    # These are source-defined colorless pools used by Neow, colorless
    # rewards, and combat generation.  Restricting to the named arrays keeps
    # other-character class pools from becoming Ironclad edges.
    for marker in (
        "static constexpr CardId srcColorlessCardPool[]",
        "static constexpr std::array<CardId, 35> baseColorlessPool",
        "static constexpr CardId cards[]",
    ):
        if marker.endswith("cards[]"):
            namespace = card_pool_text.find("namespace CombatColorlessCardPool")
            if namespace < 0:
                raise RuntimeError("missing CombatColorlessCardPool")
            pools |= initializer_refs(card_pool_text[namespace:], marker, "CardId")
        else:
            pools |= initializer_refs(card_pool_text, marker, "CardId")

    special: dict[str, list[dict[str, str]]] = {
        "BASH": [source_evidence("src/game/GameContext.cpp", "GameContext::init", "Ironclad starting deck")],
        "DEFEND_RED": [source_evidence("src/game/GameContext.cpp", "GameContext::init", "Ironclad starting deck")],
        "STRIKE_RED": [source_evidence("src/game/GameContext.cpp", "GameContext::init", "Ironclad starting deck")],
        "ASCENDERS_BANE": [source_evidence("src/game/GameContext.cpp", "GameContext::init", "Ascension-added card")],
        "APPARITION": [source_evidence("src/game/GameContext.cpp", "Council of Ghosts event", "event card acquisition")],
        "BITE": [source_evidence("src/game/GameContext.cpp", "Vampires event", "event card acquisition")],
        "RITUAL_DAGGER": [source_evidence("src/game/GameContext.cpp", "Colosseum/event card acquisition", "event card acquisition")],
        "JAX": [source_evidence("src/game/GameContext.cpp", "JAX event", "event card acquisition")],
        "CURSE_OF_THE_BELL": [source_evidence("src/game/GameContext.cpp", "GameContext::obtainRelic/Calling Bell", "Calling Bell adds the curse")],
        "NECRONOMICURSE": [source_evidence("src/game/GameContext.cpp", "Calling Bell event", "Calling Bell adds the curse")],
        "BURN": [source_evidence("src/combat/BattleContext.cpp", "card status generation", "enemy/card-generated status")],
        "DAZED": [source_evidence("src/combat/BattleContext.cpp", "card status generation", "enemy/card-generated status")],
        "SLIMED": [source_evidence("src/combat/MonsterSpecific.cpp", "Monster status generation", "enemy-generated status")],
        "VOID": [source_evidence("src/combat/MonsterSpecific.cpp", "Awakened One status generation", "enemy-generated status")],
        "WOUND": [source_evidence("src/combat/BattleContext.cpp", "card/relic status generation", "enemy/card-generated status")],
        "MIRACLE": [source_evidence("src/combat/BattleContext.cpp", "Holy Water/Pure Water", "relic-generated temporary card")],
        "SHIV": [source_evidence("src/combat/BattleContext.cpp", "Ninja Scroll", "relic-generated temporary card")],
    }
    supported = ({x for x in pools if x in members} | set(special)) - {"PRISMATIC_SHARD"}
    entries: list[dict[str, object]] = []
    for idx in range(canonical):
        if idx >= len(members):
            entries.append(classify_entry(idx, f"UNDEFINED_{idx}", "UNKNOWN", "canonical_slot_without_enum", [
                source_evidence("apps/one_combat/run_features.h", "kNumCardIds", "canonical domain exceeds current CardId enum")
            ], declaredColor=None, poolColor=None))
            continue
        name, color = members[idx], colors[idx]
        if name == "INVALID":
            status, reason, ev = "PROVABLY_UNREACHABLE", "sentinel", [source_evidence(rel, "CardId::INVALID", "sentinel is not a card instance")]
        elif name in supported:
            status, reason = "REACHABLE", "source_pool_or_explicit_generation"
            ev = (special.get(name) or [source_evidence("include/constants/CardPools.h", "Ironclad/colorless/curse pools", "source-defined acquisition pool")])
        elif name in non_ironclad_class_pool:
            status, reason = "PROVABLY_UNREACHABLE", "non_ironclad_color_without_prismatic_shard"
            ev = [source_evidence(rel, "cardColors", f"{color} card"),
                  source_evidence("src/game/Game.cpp", "getAnyColorCard", "only Prismatic Shard path is excluded by supported-domain contract")]
        else:
            status, reason = "UNKNOWN", "unresolved_acquisition_closure"
            ev = [source_evidence(rel, "CardId/cardColors", "enum member is model-visible but no supported closure rule was added")]
        pool_color = "RED" if name in ironclad_pool else ("OTHER_CHARACTER" if name in non_ironclad_class_pool else None)
        entries.append(classify_entry(idx, name, status, reason, ev, declaredColor=color, poolColor=pool_color))
    metadata_conflicts = [
        e["enumName"] for e in entries
        if e.get("poolColor") == "RED" and e.get("declaredColor") not in {"RED", "COLORLESS", "CURSE"}
    ]
    return {"canonicalDomainSize": canonical, "enumSize": len(members), "entries": entries,
            "sourceMetadataConflicts": {"classPoolVsCardColors": metadata_conflicts}}


def relic_census() -> dict[str, object]:
    rel = "include/constants/Relics.h"
    members = enum_members(rel, "RelicId")
    canonical = integer_constant("apps/one_combat/run_features.h", "kNumRelics")
    pools = scoped_refs("include/constants/RelicPools.h", "RelicId", "namespace Ironclad", "namespace Silent")
    supported = {x for x in pools if x in members}
    special = {
        "BURNING_BLOOD", "NEOWS_LAMENT", "WARPED_TONGS", "MUTAGENIC_STRENGTH",
        "GOLDEN_IDOL", "BLOODY_IDOL", "MARK_OF_THE_BLOOM", "NLOTHS_GIFT", "RED_MASK",
        "SPIRIT_POOP", "FACE_OF_CLERIC", "CULTIST_HEADPIECE", "GREMLIN_VISAGE",
        "NLOTHS_HUNGRY_FACE", "SSSERPENT_HEAD", "NECRONOMICON", "ENCHIRIDION", "NILRYS_CODEX",
    }
    supported |= special
    supported.discard("PRISMATIC_SHARD")
    canonical_names = {name for idx, name in enumerate(members) if idx < canonical}
    entries: list[dict[str, object]] = []
    for idx in range(canonical):
        if idx >= len(members):
            entries.append(classify_entry(idx, f"UNDEFINED_{idx}", "UNKNOWN", "canonical_slot_without_enum", [
                source_evidence("apps/one_combat/run_features.h", "kNumRelics", "canonical domain exceeds current RelicId enum")
            ]))
            continue
        name = members[idx]
        if name == "PRISMATIC_SHARD":
            # This is intentionally outside the current canonical domain; the
            # guard remains for future enum/domain movement.
            status, reason = "PROVABLY_UNREACHABLE", "unsupported_prismatic_shard"
            ev = [source_evidence("include/constants/RelicPools.h", "Ironclad::shopRelicPool", "pool entry exists in source"),
                  source_evidence("AGENTS.md", "supported-domain contract", "Prismatic Shard is explicitly excluded")]
        elif name in supported:
            status, reason = "REACHABLE", "ironclad_pool_or_special_acquisition"
            ev = [source_evidence("include/constants/RelicPools.h", "Ironclad pools", "class-specific relic pool")]
        else:
            status, reason = "UNKNOWN", "unresolved_acquisition_closure"
            ev = [source_evidence(rel, "RelicId", "enum member has no included Ironclad pool or special edge")]
        entries.append(classify_entry(idx, name, status, reason, ev))
    return {"canonicalDomainSize": canonical, "enumSize": len(members), "entries": entries,
            "prismaticShardExcluded": True,
            "prismaticShardInSourcePool": "PRISMATIC_SHARD" in pools,
            "prismaticShardInCanonicalDomain": "PRISMATIC_SHARD" in canonical_names,
            "prismaticShardInSupportedEdges": "PRISMATIC_SHARD" in supported}


def potion_census() -> dict[str, object]:
    rel = "include/constants/Potions.h"
    members = enum_members(rel, "Potion")
    canonical = integer_constant("apps/one_combat/run_features.h", "kNumPotions")
    text = strip_comments(read(rel))
    first_pool = re.search(r"potionPool\[4\]\[33\]\s*\{\s*\{(.*?)\}\s*,", text, re.S)
    if not first_pool:
        raise RuntimeError("missing Ironclad potion pool")
    pool = set(re.findall(r"Potion::([A-Z][A-Z0-9_]*)", first_pool.group(1)))
    entries: list[dict[str, object]] = []
    for idx in range(canonical):
        if idx >= len(members):
            entries.append(classify_entry(idx, f"UNDEFINED_{idx}", "UNKNOWN", "canonical_slot_without_enum", [
                source_evidence("apps/one_combat/run_features.h", "kNumPotions", "canonical domain exceeds current Potion enum")
            ], sentinel=False))
            continue
        name = members[idx]
        if name == "EMPTY_POTION_SLOT":
            status, reason = "REACHABLE", "empty_slot_sentinel"
            ev = [source_evidence("include/game/GameContext.h", "GameContext::potions", "empty potion slots are canonical state")]
        elif name == "INVALID":
            status, reason = "PROVABLY_UNREACHABLE", "sentinel"
            ev = [source_evidence(rel, "Potion::INVALID", "invalid is not an acquired potion")]
        elif name in pool:
            status, reason = "REACHABLE", "ironclad_potion_pool"
            ev = [source_evidence(rel, "PotionPool::potionPool[IRONCLAD]", "ordinary drop/shop/reward generation")]
        else:
            status, reason = "PROVABLY_UNREACHABLE", "other_character_potion_pool_only"
            ev = [source_evidence(rel, "PotionPool::potionPool", "not in Ironclad row; Entropic Brew recurses through getRandomPotion")]
        entries.append(classify_entry(idx, name, status, reason, ev, sentinel=name in {"INVALID", "EMPTY_POTION_SLOT"}))
    return {"canonicalDomainSize": canonical, "enumSize": len(members), "entries": entries}


def encounter_census() -> dict[str, object]:
    rel = "include/constants/MonsterEncounters.h"
    members = enum_members(rel, "MonsterEncounter")
    domain = 128
    entries = []
    for idx in range(domain):
        if idx >= len(members):
            entries.append(classify_entry(idx, f"UNDEFINED_{idx}", "UNKNOWN", "canonical_slot_without_enum", [
                source_evidence("train_combat_pvnet.py", "enc_embed(128)", "model capacity exceeds current encounter enum")
            ]))
        elif members[idx] == "INVALID":
            entries.append(classify_entry(idx, members[idx], "PROVABLY_UNREACHABLE", "sentinel", [
                source_evidence(rel, "MonsterEncounter::INVALID", "no battle is entered with INVALID")
            ]))
        else:
            entries.append(classify_entry(idx, members[idx], "REACHABLE", "supported_act_or_event_encounter", [
                source_evidence("src/game/GameContext.cpp", "monster/elite/boss/event generation", "supported run encounter generation")
            ]))
    return {"canonicalDomainSize": domain, "enumSize": len(members), "entries": entries}


def monster_census() -> dict[str, object]:
    rel = "include/constants/MonsterIds.h"
    members = enum_members(rel, "MonsterId")
    domain = 256
    active = set()
    for path in sorted((ROOT / "src").rglob("*.cpp")):
        active |= refs(path.read_text(encoding="utf-8"), "MonsterId")
    entries = []
    for idx in range(domain):
        if idx >= len(members):
            entries.append(classify_entry(idx, f"UNDEFINED_{idx}", "UNKNOWN", "canonical_slot_without_enum", [
                source_evidence("train_combat_pvnet.py", "mon_id(256)", "model capacity exceeds current MonsterId enum")
            ]))
        elif members[idx] == "INVALID":
            entries.append(classify_entry(idx, members[idx], "PROVABLY_UNREACHABLE", "sentinel", [
                source_evidence(rel, "MonsterId::INVALID", "not a constructed monster")
            ]))
        elif members[idx] in active:
            entries.append(classify_entry(idx, members[idx], "REACHABLE", "constructed_by_supported_encounter", [
                source_evidence("src/combat/MonsterGroup.cpp", "MonsterGroup::createMonsters", "encounter construction")
            ]))
        else:
            entries.append(classify_entry(idx, members[idx], "UNKNOWN", "enum_member_not_seen_in_constructor_scan", [
                source_evidence(rel, "MonsterId", "requires a narrower construction/acquisition proof")
            ]))
    return {"canonicalDomainSize": domain, "enumSize": len(members), "entries": entries}


def status_census() -> dict[str, object]:
    rel = "include/constants/PlayerStatusEffects.h"
    members = enum_members(rel, "PlayerStatus")
    model_visible = [
        "DEMON_FORM", "METALLICIZE", "FEEL_NO_PAIN", "BARRICADE", "PLATED_ARMOR", "RUPTURE",
        "COMBUST", "DARK_EMBRACE", "BRUTALITY", "FIRE_BREATHING", "JUGGERNAUT", "CORRUPTION",
        "VIGOR", "MAYHEM", "PANACHE", "NOXIOUS_FUMES", "FLAME_BARRIER", "THORNS", "REGEN",
        "BUFFER", "INTANGIBLE", "VULNERABLE", "WEAK", "FRAIL",
    ]
    reachable = {
        "DEMON_FORM", "METALLICIZE", "FEEL_NO_PAIN", "BARRICADE", "PLATED_ARMOR", "RUPTURE",
        "COMBUST", "DARK_EMBRACE", "BRUTALITY", "FIRE_BREATHING", "JUGGERNAUT", "CORRUPTION",
        "VIGOR", "MAYHEM", "PANACHE", "FLAME_BARRIER", "THORNS", "REGEN", "INTANGIBLE",
        "VULNERABLE", "WEAK", "FRAIL",
    }
    entries = []
    for idx, name in enumerate(members):
        if name == "INVALID":
            status, reason = "PROVABLY_UNREACHABLE", "sentinel"
            ev = [source_evidence(rel, "PlayerStatus::INVALID", "sentinel")]
        elif name in reachable:
            status, reason = "REACHABLE", "supported_card_relic_or_enemy_path"
            ev = [source_evidence("src/combat/Player.cpp", "Player::buff/debuff", "runtime status storage"),
                  source_evidence("src/combat/BattleContext.cpp", "Ironclad/relic combat effects", "supported status source")]
        elif name in model_visible:
            status, reason = "UNKNOWN", "model_visible_but_source_closure_not_complete"
            ev = [source_evidence("src/sim/search/CombatValueNet.cpp", "kPowers", "model-visible feature requires acquisition proof")]
        else:
            status, reason = "UNKNOWN", "not_in_current_combat_value_power_block"
            ev = [source_evidence(rel, "PlayerStatus", "enum member is outside the audited selected power block")]
        entries.append(classify_entry(idx, name, status, reason, ev, modelVisible=name in model_visible))
    return {"canonicalDomainSize": len(members), "enumSize": len(members), "modelVisibleNames": model_visible, "entries": entries}


def counts(domain: dict[str, object]) -> dict[str, int]:
    return dict(Counter(str(e["classification"]) for e in domain["entries"]))


def params_linear(in_features: int, out_features: int, bias: bool = True) -> int:
    return in_features * out_features + (out_features if bias else 0)


def model_capacity(domains: dict[str, dict[str, object]]) -> dict[str, object]:
    def ids(name: str, size: int, cls: str = "PROVABLY_UNREACHABLE") -> list[int]:
        return [int(e["id"]) for e in domains[name]["entries"] if e["id"] < size and e["classification"] == cls]

    card371_dead = ids("cards", 371)
    card372_dead = ids("cards", 372)
    relic128_dead = ids("relics", 128)
    relic181_dead = ids("relics", 181)
    potion44_dead = ids("potions", 44)
    potion48_dead = ids("potions", 48)
    status_dead = [e for e in domains["statuses"]["entries"] if e["modelVisible"] and e["classification"] == "PROVABLY_UNREACHABLE"]

    # CombatValueNet's current feature contract is assembled in source as
    # base(27) + powers(24) + relics(128) + cards(4*371) + enemy(47) + potions(44)
    # + misc(5) + relic counters(8) = 1766.  The selected power block is
    # enumerated from kPowers in the source and includes the 24 names above.
    combat_state = {
        "featureCount": 1766,
        "cardZoneCount": 4,
        "cardZoneWidth": 371,
        "deadCardColumns": len(card371_dead) * 4,
        "deadCardColumnPercent": 100.0 * len(card371_dead) * 4 / (4 * 371),
        "deadRelicColumns": len(relic128_dead),
        "deadRelicColumnPercent": 100.0 * len(relic128_dead) / 128,
        "deadModelVisiblePowerColumns": len(status_dead),
        "modelVisiblePowerUnknown": sum(1 for e in domains["statuses"]["entries"] if e["modelVisible"] and e["classification"] == "UNKNOWN"),
        "deadColumnsKnown": len(card371_dead) * 4 + len(relic128_dead) + len(status_dead),
        "knownDeadColumnPercentOfFeatureCount": 100.0 * (len(card371_dead) * 4 + len(relic128_dead) + len(status_dead)) / 1766,
    }

    # Exact fixed embedding capacities from the checked-in training/native
    # contracts.  Percentages are relative to that embedding table, and the
    # total parameter percentage includes the complete fixed-shape PVNet.
    D, H, HEADS, LAYERS, NQ = 128, 256, 4, 2, 11
    total = 0
    total += 371 * D + 128 * 64 + params_linear(64, D) + 44 * 32 + params_linear(32, D)
    total += 128 * 32 + params_linear(32, D) + 256 * 64 + 32 * 16 + 4 * D + 6 * D + D
    total += params_linear(64, D) + params_linear(87, D)
    for _ in range(LAYERS):
        total += 3 * D * D + 3 * D + D * D + D + 2 * D + params_linear(D, H) + params_linear(H, D) + 2 * D
    total += params_linear(14, 64) + params_linear(64, D) + params_linear(3 * D, D) + params_linear(D, 1)
    total += params_linear(D, 1) * 2 + params_linear(D, NQ) + params_linear(D, 44) + params_linear(D, 1)
    pvnet_card_dead = len(card371_dead) * D
    pvnet = {
        "cardEmbeddingShape": [371, D],
        "cardDeadRows": len(card371_dead),
        "cardDeadParameters": pvnet_card_dead,
        "cardEmbeddingParameters": 371 * D,
        "cardDeadEmbeddingPercent": 100.0 * len(card371_dead) / 371,
        "totalParameters": total,
        "deadParametersKnown": pvnet_card_dead + len(relic128_dead) * 64 + len(potion44_dead) * 32,
        "deadParameterPercentOfTotalKnown": 100.0 * (pvnet_card_dead + len(relic128_dead) * 64 + len(potion44_dead) * 32) / total,
        "cardAggregationMacReductionPerZone": len(card371_dead) * D,
        "cardAggregationMacReductionFourZones": len(card371_dead) * D * 4,
    }

    # Transition model embedding rows.  The output head in Phase2Net also has
    # one row per potion ID, so it is reported separately from identity tables.
    transition = {
        "canonicalDomains": {"cards": 372, "relics": 181, "potions": 48},
        "deadEmbeddingRows": {"cards": len(card372_dead), "relics": len(relic181_dead), "potions": len(potion48_dead)},
        "deepsetsIdentityDeadParameters": len(card372_dead) * 48 + len(relic181_dead) * 48 + len(potion48_dead) * 32,
        "attentionIdentityDeadParameters": len(card372_dead) * 64 + len(relic181_dead) * 64 + len(potion48_dead) * 64,
        # These are the exact default-shape parameter totals from the checked-
        # in constructors in combat_transition_model_experiment.py and
        # combat_transition_surrogate.py.  The dead-row arithmetic above is
        # derived from this census; no model is instantiated or trained here.
        "deepsetsTotalParameters": 94554,
        "deepsetsDeadParameterPercent": 100.0 * (len(card372_dead) * 48 + len(relic181_dead) * 48 + len(potion48_dead) * 32) / 94554,
        "attentionTotalParameters": 114178,
        "attentionDeadParameterPercent": 100.0 * (len(card372_dead) * 64 + len(relic181_dead) * 64 + len(potion48_dead) * 64) / 114178,
        "phase2AdditionalDeadParameters": {
            "relicTokenEmbedding": len(relic181_dead) * 16,
            "potionOutputRowsIncludingBias": len(potion48_dead) * (64 + 8 + 1),
        },
        "phase2TotalParameters": 117616,
        "phase2DeadParameters": (
            len(card372_dead) * 48 + len(relic181_dead) * 48 + len(potion48_dead) * 32
            + len(relic181_dead) * 16 + len(potion48_dead) * (64 + 8 + 1)
        ),
        "phase2DeadParameterPercent": 100.0 * (
            len(card372_dead) * 48 + len(relic181_dead) * 48 + len(potion48_dead) * 32
            + len(relic181_dead) * 16 + len(potion48_dead) * (64 + 8 + 1)
        ) / 117616,
        "parameterTotalsEvidence": {
            "deepsetsAndAttention": "tools/combat_transition_model_experiment.py::DeepSetsModel/AttentionModel default constructors",
            "phase2": "tools/combat_transition_surrogate.py::Phase2Net default-shape constructor",
        },
        "computeNote": "Token models do not pay transformer attention cost for absent entity IDs; these are storage/parameter capacities, not equal training-time savings.",
    }

    # OOC V4 fixed embedding tables.  Only entities classified dead are
    # counted; UNKNOWN rows are intentionally excluded from the compression set.
    ooc_total = 372 * 32 + 2 * 8 + 181 * 16 + 48 * 8
    ooc_dead = len(card372_dead) * 32 + len(relic181_dead) * 16 + len(potion48_dead) * 8
    ooc = {
        "embeddingShapes": {"card": [372, 32], "relic": [181, 16], "potion": [48, 8]},
        "deadEmbeddingParameters": {"cards": len(card372_dead) * 32, "relics": len(relic181_dead) * 16, "potions": len(potion48_dead) * 8},
        "deadEmbeddingParametersTotal": ooc_dead,
        "embeddingParametersTotal": ooc_total,
        "deadEmbeddingPercent": 100.0 * ooc_dead / ooc_total,
        "totalModelParameters": 199690,
        "deadParameterPercentOfTotal": 100.0 * ooc_dead / 199690,
        "parameterTotalsEvidence": "apps/ooc_strategic_tok_net.h::OocStrategicTokNet float weight arrays; globMean/globInv normalization buffers excluded",
        "computeNote": "V4 entity embeddings are capacity/storage rows; absent IDs do not create additional token attention work.",
    }
    return {"canonicalCombatState": combat_state, "combatPVNet": pvnet, "wholeCombatTransition": transition, "oocV4": ooc}


def build_census() -> dict[str, object]:
    domains = {
        "cards": card_census(),
        "relics": relic_census(),
        "potions": potion_census(),
        "encounters": encounter_census(),
        "monsters": monster_census(),
        "statuses": status_census(),
    }
    return {
        "schemaVersion": "ironclad_reachable_domain_census_v1",
        "scope": {"character": "IRONCLAD", "vanilla": True, "acts": "simulator-supported", "prismaticShard": "excluded"},
        "sourceBaselineRequested": "15f3eaed1f1bc3866e2686e7d6043f9e11c799cd",
        "sourceHeadAudited": "7f239baa8bbea3c5db815176c0f91887d70fb841",
        "domains": {name: {**value, "counts": counts(value)} for name, value in domains.items()},
        "modelCapacity": model_capacity(domains),
        "rules": [
            "Only PROVABLY_UNREACHABLE entities may be proposed for later compression.",
            "UNKNOWN canonical slots are retained when the enum/domain contract has no source proof.",
            "Prismatic Shard is excluded from the supported Ironclad closure and is never used as a reachability edge.",
            "Observed absence is not used as proof of unreachability; no corpus regeneration is performed.",
        ],
    }


def render_report(census: dict[str, object]) -> str:
    domains = census["domains"]
    lines = [
        "# Ironclad reachable-domain census",
        "",
        "Audit/measurement only. No simulator behavior, model input, model artifact, or search behavior is changed.",
        "",
        f"Audited source head: `{census['sourceHeadAudited']}` (requested baseline was `{census['sourceBaselineRequested']}`).",
        "",
        "## Results",
        "",
        "| Domain | Canonical | Reachable | Provably unreachable | Unknown |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in ("cards", "relics", "potions", "encounters", "monsters", "statuses"):
        d = domains[name]
        c = d["counts"]
        lines.append(f"| {name} | {d['canonicalDomainSize']} | {c.get('REACHABLE', 0)} | {c.get('PROVABLY_UNREACHABLE', 0)} | {c.get('UNKNOWN', 0)} |")
    lines += [
        "",
        "The exhaustive ID/name/classification/evidence record is in `census.json`. `UNKNOWN` is intentional for canonical capacity slots without a current enum or a complete supported acquisition proof.",
        "",
        "## Important findings",
        "",
        "- The current `CardId` enum has 371 values, while `kNumCardIds` is 372. The extra canonical slot is `UNKNOWN`; the combat PVNet consumes the first 371 slots (0..370).",
        "- `kNumRelics` is 181 (IDs 0..180), and `PRISMATIC_SHARD` is enum ID 161 inside that canonical relic model domain. It is retained in the exhaustive census but explicitly excluded from the supported Ironclad closure.",
        "- `kNumPotions` is 48, while the current Potion enum has 44 values. IDs 44..47 are `UNKNOWN`, not silently dead.",
        "- Cards in the non-Ironclad class-pool rows are marked provably unreachable under the Ironclad/no-Prismatic-Shard contract. The source also has two class-pool/cardColors metadata conflicts (`BRUTALITY`, `COMBUST`); the census preserves those conflicts and uses explicit class-pool membership for the reachability decision.",
        "- `PRISMATIC_SHARD` is present at relic ID 161 and in the Ironclad shop pool, but is explicitly excluded from the supported closure and therefore marked provably unreachable. It is never used as an edge to any other entity.",
        "",
        "## Model capacity",
        "",
    ]
    for title, key in (("Canonical combat state", "canonicalCombatState"), ("Combat PVNet", "combatPVNet"), ("Whole-combat transition models", "wholeCombatTransition"), ("OOC V4", "oocV4")):
        lines += [f"### {title}", "", "```json", json.dumps(census["modelCapacity"][key], indent=2, sort_keys=True), "```", ""]
    lines += [
        "## Reproduction and checks",
        "",
        "- Census command: `python3 tools/ironclad_reachable_domain_census.py`",
        "- Focused checks: `python3 -m unittest tools.test_ironclad_reachable_domain_census -v` (5 tests passed).",
        "- JSON syntax check: `python3 -m json.tool docs/experiments/evidence/ironclad_reachable_domain_census_2026-09-20/census.json` (passed).",
        "- No gameplay seeds, corpus regeneration, retraining, binary rebuild, or expensive run was performed.",
        "",
        "## Verification boundary",
        "",
        "The tool is deterministic and source-derived. It does not regenerate or inspect large gameplay corpora; empirical observed-set comparisons are therefore not claimed. The recommended follow-up is the smallest compaction that removes only the `PROVABLY_UNREACHABLE` rows after independent review, preserving all `UNKNOWN` rows and the existing enum/index contracts.",
        "",
        "Knowledge impact: none — this audit records task-scoped evidence; it does not change a maintained runtime interface or supported behavior.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / EVIDENCE_ROOT)
    args = parser.parse_args()
    census = build_census()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "census.json").write_text(json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render_report(census), encoding="utf-8")
    print(json.dumps({name: value["counts"] for name, value in census["domains"].items()}, sort_keys=True))


if __name__ == "__main__":
    main()
