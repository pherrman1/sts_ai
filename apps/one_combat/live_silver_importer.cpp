#include "live_silver_importer.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>

#include "constants/CharacterClasses.h"
#include "constants/MonsterIds.h"
#include "constants/MonsterMoves.h"
#include "constants/SaveFileMappings.h"
#include "constants/Potions.h"
#include "combat/CardInstance.h"

namespace one_combat::advisor {
namespace {

using json = nlohmann::json;

struct CardRecord {
    std::string uuid;
    silver_bridge::CardWire wire;
};

std::string fail(const char *reason) { return reason; }

std::uint64_t fnv1a(const std::string &value, std::uint64_t hash = 1469598103934665603ULL) {
    for (unsigned char c : value) { hash ^= c; hash *= 1099511628211ULL; }
    return hash;
}

bool requiredInt(const json &object, const char *name, int &out) {
    if (!object.contains(name) || !object.at(name).is_number_integer()) return false;
    out = object.at(name).get<int>();
    return true;
}

bool requiredBool(const json &object, const char *name, bool &out) {
    if (!object.contains(name) || !object.at(name).is_boolean()) return false;
    out = object.at(name).get<bool>();
    return true;
}

bool hasForbiddenRngField(const json &object) {
    for (const char *name : {"rng", "aiRng", "cardRandomRng", "miscRng", "monsterHpRng",
                             "potionRng", "shuffleRng", "seed"})
        if (object.contains(name)) return true;
    return false;
}

bool parseCard(const json &item, const std::string &location, CardRecord &out) {
    if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
        || !item.contains("uuid") || !item.at("uuid").is_string()
        || !item.contains("misc") || !item.at("misc").is_number_integer()
        || !item.contains("cost") || !item.at("cost").is_number_integer()
        || !item.contains("costForTurn") || !item.at("costForTurn").is_number_integer()
        || !item.contains("upgraded") || !item.at("upgraded").is_boolean()
        || !item.contains("freeToPlayOnce") || !item.at("freeToPlayOnce").is_boolean()
        || !item.contains("retain") || !item.at("retain").is_boolean()) return false;
    try {
        const auto cardId = item.at("id").get<sts::CardId>();
        if (cardId == sts::CardId::INVALID) return false;
        out.uuid = item.at("uuid").get<std::string>();
        out.wire.id = static_cast<std::int16_t>(cardId);
        out.wire.specialData = item.at("misc").get<std::int16_t>();
        out.wire.cost = item.at("cost").get<std::int16_t>();
        out.wire.costForTurn = item.at("costForTurn").get<std::int16_t>();
        out.wire.upgraded = item.at("upgraded").get<bool>();
        out.wire.freeToPlayOnce = item.at("freeToPlayOnce").get<bool>();
        out.wire.retain = item.at("retain").get<bool>();
        return location == "HAND" || location == "DRAW" || location == "DISCARD" || location == "EXHAUST";
    } catch (...) { return false; }
}

int monsterId(const std::string &id) {
    static const std::map<std::string, sts::MonsterId> ids = {
        {"Cultist", sts::MonsterId::CULTIST}, {"JawWorm", sts::MonsterId::JAW_WORM},
        {"Gremlin Nob", sts::MonsterId::GREMLIN_NOB}, {"GremlinNob", sts::MonsterId::GREMLIN_NOB},
    };
    const auto it = ids.find(id); return it == ids.end() ? 0 : static_cast<int>(it->second);
}

int moveId(const std::string &id, int nextMove) {
    // These values are the explicit first-action mappings from the vanilla
    // AbstractMonster nextMove field; no damage or localized intent text is used.
    if (id == "Cultist")
        return nextMove == 3 ? static_cast<int>(sts::MonsterMoveId::CULTIST_INCANTATION) : 0;
    if (id == "JawWorm") {
        if (nextMove == 1) return static_cast<int>(sts::MonsterMoveId::JAW_WORM_CHOMP);
    }
    if (id == "Gremlin Nob" || id == "GremlinNob") {
        if (nextMove == 3) return static_cast<int>(sts::MonsterMoveId::GREMLIN_NOB_BELLOW);
    }
    return 0;
}

bool cardLess(const silver_bridge::CardWire &a, const silver_bridge::CardWire &b) {
    if (a.id != b.id) return a.id < b.id;
    if (a.uniqueId != b.uniqueId) return a.uniqueId < b.uniqueId;
    if (a.specialData != b.specialData) return a.specialData < b.specialData;
    if (a.cost != b.cost) return a.cost < b.cost;
    if (a.costForTurn != b.costForTurn) return a.costForTurn < b.costForTurn;
    if (a.upgraded != b.upgraded) return a.upgraded < b.upgraded;
    if (a.freeToPlayOnce != b.freeToPlayOnce) return a.freeToPlayOnce < b.freeToPlayOnce;
    return a.retain < b.retain;
}

bool isStrike(const silver_bridge::CardWire &wire) {
    sts::CardInstance card(static_cast<sts::CardId>(wire.id));
    return card.isStrikeCard();
}

bool isBlood(const silver_bridge::CardWire &wire) {
    sts::CardInstance card(static_cast<sts::CardId>(wire.id));
    return card.isBloodCard();
}

bool isNormality(const silver_bridge::CardWire &wire) {
    return wire.id == static_cast<std::int16_t>(sts::CardId::NORMALITY);
}

bool isPain(const silver_bridge::CardWire &wire) {
    return wire.id == static_cast<std::int16_t>(sts::CardId::PAIN);
}

bool parseCards(const json &array, const std::string &location, std::vector<CardRecord> &out) {
    if (!array.is_array()) return false;
    for (const auto &item : array) { CardRecord record; if (!parseCard(item, location, record)) return false; out.push_back(std::move(record)); }
    return true;
}

} // namespace

SilverRootImportResult importSilverRoot(const json &observation) {
    SilverRootImportResult result;
    auto &wire = result.wire;
    const auto unsupported = [&](const char *reason) { result.reason = fail(reason); return result; };
    if (!observation.contains("silverRoot") || !observation.at("silverRoot").is_object()) return unsupported("silver_root_missing");
    const auto &root = observation.at("silverRoot");
    if (hasForbiddenRngField(observation) || hasForbiddenRngField(root)) return unsupported("silver_rng_field");
    int schema = 0, decisionOrdinal = -1, act = 0, floor = 0, ascension = 0, hp = 0, maxHp = 0, gold = 0, potionCapacity = 0;
    bool firstDecision = false, burningElite = false;
    if (!requiredInt(root, "schemaVersion", schema) || schema != 2) return unsupported("silver_schema_version");
    if (!requiredInt(root, "decisionOrdinal", decisionOrdinal)
        || (decisionOrdinal != 0 && decisionOrdinal != 1)) return unsupported("silver_decision_ordinal");
    if (!requiredBool(root, "firstDecision", firstDecision) || firstDecision != (decisionOrdinal == 0))
        return unsupported("silver_first_decision_flag");
    result.decisionOrdinal = decisionOrdinal;
    if (!requiredInt(root, "act", act) || act != 1) return unsupported("silver_act");
    if (!requiredInt(root, "floor", floor) || floor < 1) return unsupported("silver_floor");
    if (!requiredInt(root, "ascension", ascension) || !requiredInt(root, "hp", hp)
        || !requiredInt(root, "maxHp", maxHp) || !requiredInt(root, "gold", gold)
        || !requiredInt(root, "potionCapacity", potionCapacity)
        || !requiredBool(root, "burningElite", burningElite)) return unsupported("silver_root_state");
    if (burningElite) return unsupported("silver_burning_elite");
    if (!root.contains("roomClass") || !root.at("roomClass").is_string()) return unsupported("silver_room_class");
    if (observation.value("character", std::string()) != "IRONCLAD"
        || !root.contains("character") || !root.at("character").is_string()
        || root.at("character").get<std::string>() != "IRONCLAD") return unsupported("silver_character");
    if (!root.contains("combat") || !root.at("combat").is_object()) return unsupported("silver_combat_missing");
    const auto &combat = root.at("combat");
    if (hasForbiddenRngField(combat)) return unsupported("silver_rng_field");
    bool runicDome = false, frozenEye = false, cardSelect = false, resolving = false;
    int cardsPlayed = 0;
    if (!requiredBool(combat, "runicDome", runicDome) || runicDome) return unsupported("silver_runic_dome");
    if (!requiredBool(combat, "frozenEye", frozenEye) || frozenEye) return unsupported("silver_frozen_eye");
    if (!requiredInt(combat, "cardsPlayedThisTurn", cardsPlayed)
        || cardsPlayed != decisionOrdinal) return unsupported("silver_cards_played_history");
    if (!combat.contains("playedThisTurn") || !combat.at("playedThisTurn").is_array()
        || combat.at("playedThisTurn").size() != static_cast<std::size_t>(decisionOrdinal))
        return unsupported("silver_played_history");
    if (!combat.contains("playerPowers") || !combat.at("playerPowers").is_array()
        || !combat.at("playerPowers").empty()) return unsupported("silver_unmapped_player_power");
    if (!requiredBool(combat, "cardSelect", cardSelect) || !requiredBool(combat, "resolving", resolving)
        || cardSelect || resolving) return unsupported("silver_card_select");
    int turn = 0, energy = 0, block = 0;
    // Java's GameActionManager is one-based at the first actionable decision;
    // the native simulator's equivalent BattleContext root is zero-based.
    if (!requiredInt(combat, "turn", turn) || !requiredInt(combat, "energy", energy) || !requiredInt(combat, "block", block) || turn != 1)
        return unsupported("silver_first_turn_invariant");
    if (potionCapacity != 3 || !combat.contains("hand") || !combat.contains("draw")
        || !combat.contains("discard") || !combat.contains("exhaust") || !combat.contains("monsters")
        || !combat.contains("relics") || !combat.contains("potions")) return unsupported("silver_missing_state");

    std::vector<CardRecord> cards;
    if (!parseCards(combat.at("hand"), "HAND", cards)
        || !parseCards(combat.at("draw"), "DRAW", cards)
        || !parseCards(combat.at("discard"), "DISCARD", cards)
        || !parseCards(combat.at("exhaust"), "EXHAUST", cards)) return unsupported("silver_unknown_card");
    if (cards.size() < 5 || cards.size() > 50 || cards.size() != 10) return unsupported("silver_deck_size");
    std::sort(cards.begin(), cards.end(), [](const CardRecord &a, const CardRecord &b) { return a.uuid < b.uuid; });
    std::set<std::string> uuids;
    for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
        if (!uuids.insert(cards[i].uuid).second || cards[i].uuid.empty()) return unsupported("silver_card_identity");
        cards[i].wire.uniqueId = static_cast<std::int16_t>(i);
    }
    if (combat.at("hand").size() != static_cast<std::size_t>(5 - decisionOrdinal))
        return unsupported("silver_hand_size");
    wire.nextUniqueCardId = static_cast<int>(cards.size());
    // Reparse by source so the UUID mapping above is applied without exposing pile order.
    std::unordered_map<std::string, silver_bridge::CardWire> byUuid;
    for (const auto &card : cards) byUuid.emplace(card.uuid, card.wire);
    const auto appendPile = [&](const char *name, std::vector<silver_bridge::CardWire> &target,
                                bool canonicalize) {
        for (const auto &item : combat.value(name, json::array())) {
            const auto uuid = item.value("uuid", std::string());
            target.push_back(byUuid.at(uuid));
        }
        if (canonicalize) std::sort(target.begin(), target.end(), cardLess);
    };
    appendPile("hand", wire.hand, false);
    appendPile("draw", wire.drawPile.unknown, true);
    appendPile("discard", wire.discardPile.unknown, true); appendPile("exhaust", wire.exhaustPile.unknown, true);
    wire.drawPile.valid = wire.discardPile.valid = wire.exhaustPile.valid = true;
    wire.drawPile.fullOrderObserved = wire.discardPile.fullOrderObserved = wire.exhaustPile.fullOrderObserved = false;
    const auto countWire = [](const std::vector<silver_bridge::CardWire> &pile,
                              bool (*predicate)(const silver_bridge::CardWire &)) {
        int count = 0;
        for (const auto &card : pile) if (predicate(card)) ++count;
        return count;
    };
    wire.strikeCount = 0;
    for (const auto &card : cards) if (isStrike(card.wire)) ++wire.strikeCount;
    wire.handNormalityCount = countWire(wire.hand, isNormality);
    wire.handPainCount = countWire(wire.hand, isPain);
    wire.handBloodCardCount = countWire(wire.hand, isBlood);
    wire.drawPileBloodCardCount = countWire(wire.drawPile.unknown, isBlood);
    wire.discardPileBloodCardCount = countWire(wire.discardPile.unknown, isBlood);

    wire.version = silver_bridge::BattleStateWire::kVersion;
    wire.valid = true; wire.fullDrawOrderObserved = false; wire.intentsHidden = false;
    wire.floorNum = floor; wire.act = act; wire.ascension = ascension;
    // BattleContext::init reaches PLAYER_NORMAL after two executeActions loop
    // iterations: the initial draw and the final decision-boundary check.
    wire.turn = 0; wire.cardsDrawn = 5; wire.loopCount = decisionOrdinal == 0 ? 2 : 0; wire.energyWasted = 0;
    wire.outcome = 0; wire.inputState = 1; // PLAYER_NORMAL, proven by the live decision gate
    wire.monsterTurnIdx = 6; wire.endTurnQueued = false; wire.turnHasEnded = false; wire.skipMonsterTurn = false;
    wire.potionCapacity = potionCapacity; wire.potionCount = 0;
    wire.potions.fill(static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT));
    wire.player.characterClass = static_cast<std::int16_t>(sts::CharacterClass::IRONCLAD);
    wire.player.curHp = hp; wire.player.maxHp = maxHp; wire.player.gold = gold;
    wire.player.energy = energy; wire.player.energyPerTurn = 3; wire.player.cardDrawPerTurn = 5;
    wire.player.lastTargetedMonster = 1; wire.player.block = block;
    wire.player.cardsPlayedThisTurn = static_cast<std::int16_t>(decisionOrdinal);
    wire.player.attacksPlayedThisTurn = 0;
    wire.player.skillsPlayedThisTurn = 0; wire.player.cardsDiscardedThisTurn = 0;
    wire.player.lastAttackUnblockedDamage = 0; wire.player.timesDamagedThisCombat = 0;
    const int burningBlood = static_cast<int>(sts::RelicId::BURNING_BLOOD);
    wire.player.relicBits0 = burningBlood < 64 ? (1ULL << burningBlood) : 0;
    wire.player.relicBits1 = burningBlood >= 64 ? (1ULL << (burningBlood - 64)) : 0;
    if (!combat.at("relics").is_array() || combat.at("relics").size() != 1
        || !combat.at("relics")[0].is_object()
        || combat.at("relics")[0].value("id", std::string()) != "Burning Blood"
        || !combat.at("relics")[0].contains("counter")
        || !combat.at("relics")[0].at("counter").is_number_integer())
        return unsupported("silver_unmapped_relic_state");
    if (!combat.at("potions").is_array() || combat.at("potions").size() != static_cast<std::size_t>(potionCapacity))
        return unsupported("silver_unmapped_potion_state");
    for (std::size_t i = 0; i < combat.at("potions").size(); ++i) {
        const auto &potion = combat.at("potions")[i];
        if (!potion.is_object() || potion.value("slot", -1) != static_cast<int>(i)
            || potion.value("id", std::string()) != "Potion Slot") return unsupported("silver_unmapped_potion_state");
    }

    const auto monsters = combat.value("monsters", json::array());
    if (!monsters.is_array() || monsters.size() != 1) return unsupported("silver_unknown_monster");
    const std::string roomClass = root.at("roomClass").get<std::string>();
    wire.monsterCount = wire.monstersAlive = static_cast<int>(monsters.size());
    for (std::size_t i = 0; i < monsters.size(); ++i) {
        const auto &item = monsters[i];
        if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
            || !requiredInt(item, "hp", wire.monsters[i].curHp)
            || !requiredInt(item, "maxHp", wire.monsters[i].maxHp)
            || !requiredInt(item, "block", wire.monsters[i].block)
            || !item.contains("nextMove") || !item.at("nextMove").is_number_integer())
            return unsupported("silver_monster_state");
        const auto id = item.at("id").get<std::string>();
        const int canonical = monsterId(id), move = moveId(id, item.at("nextMove").get<int>());
        if (canonical == 0) return unsupported("silver_unknown_monster");
        if (move == 0) return unsupported("silver_unknown_move");
        if ((id == "Gremlin Nob" || id == "GremlinNob") ? roomClass != "ELITE" : roomClass != "MONSTER")
            return unsupported("silver_room_class");
        if (!item.contains("powers") || !item.at("powers").is_array() || !item.at("powers").empty())
            return unsupported("silver_unmapped_monster_power");
        auto &monster = wire.monsters[i]; monster.idx = static_cast<int>(i); monster.id = canonical;
        monster.moveHistory = {static_cast<std::int16_t>(move), 0};
    }
    if (monsters.size() == 1) {
        const auto id = monsters.front().value("id", std::string());
        if (id == "Cultist") wire.encounter = static_cast<int>(sts::MonsterEncounter::CULTIST);
        else if (id == "JawWorm") wire.encounter = static_cast<int>(sts::MonsterEncounter::JAW_WORM);
        else if (id == "Gremlin Nob" || id == "GremlinNob") wire.encounter = static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB);
    }
    for (auto &stasis : wire.stasisCards) {
        stasis.uniqueId = -1;
        // CardManager initializes the two inactive stasis slots with the
        // default card cost sentinel used by the native first root.
        stasis.cost = 1;
        stasis.costForTurn = 1;
    }
    // CardManager::limbo is a fixed ten-slot array, not a sized container;
    // native first-root conversion therefore carries ten default card slots.
    // Preserve that materialized invariant even though the public observer has
    // no meaningful limbo payload at PLAYER_NORMAL.
    wire.limbo.assign(10, silver_bridge::CardWire{});
    for (auto &card : wire.limbo) card.uniqueId = -1;
    wire.curCardQueueItem.card.uniqueId = -1;
    if (decisionOrdinal == 1) {
        const auto &played = combat.at("playedThisTurn")[0];
        if (!played.is_object() || !played.value("uuid", std::string()).size()
            || !played.contains("id") || !played.at("id").is_string()
            || played.value("upgraded", true))
            return unsupported("silver_played_card");
        const auto playedId = played.value("id", std::string());
        if (playedId != "Strike_R" && playedId != "Defend_R") return unsupported("silver_unsupported_continuation");
        const auto uuid = played.value("uuid", std::string());
        bool inDiscard = false;
        for (const auto &item : combat.at("discard"))
            if (item.is_object() && item.value("uuid", std::string()) == uuid) inDiscard = true;
        if (!inDiscard) return unsupported("silver_played_card");
        const auto it = byUuid.find(uuid);
        if (it == byUuid.end() || it->second.upgraded) return unsupported("silver_played_card");
        const auto &card = it->second;
        wire.curCardQueueItem.card = card;
        wire.curCardQueueItem.target = 0;
        wire.curCardQueueItem.energyOnUse = energy + 1;
        wire.player.energy = energy;
        wire.player.lastTargetedMonster = playedId == "Strike_R" ? 0 : 1;
        wire.player.lastAttackUnblockedDamage = 0;
        wire.player.attacksPlayedThisTurn = playedId == "Strike_R" ? 1 : 0;
        wire.player.skillsPlayedThisTurn = playedId == "Defend_R" ? 1 : 0;
        wire.player.block = block;
        wire.loopCount = playedId == "Strike_R" ? 6 : 0;
    }
    const auto combatEntryHash = observation.value("combatEntryHash", std::string());
    if (combatEntryHash.empty()) return unsupported("silver_combat_entry_hash");
    wire.isolatedSearchSeed = fnv1a(combatEntryHash + ":silver-live-v2");
    wire.observedGeneration = static_cast<std::uint64_t>(decisionOrdinal + 1);
    result.ok = true;
    return result;
}

std::string silverActionLabel(const silver_bridge::SemanticAction &action,
                              const silver_bridge::BattleStateWire &state) {
    if (action.type == silver_bridge::SemanticActionType::END_TURN) return "End Turn";
    if (action.type == silver_bridge::SemanticActionType::POTION) return "Potion";
    if (action.type != silver_bridge::SemanticActionType::CARD) return "Card selection";
    static const std::map<int, std::string> cards = {{static_cast<int>(sts::CardId::BASH), "Bash"}, {static_cast<int>(sts::CardId::STRIKE_RED), "Strike"}, {static_cast<int>(sts::CardId::DEFEND_RED), "Defend"}};
    const auto it = cards.find(action.card.id); const std::string name = it == cards.end() ? "Card" : it->second;
    if (action.target >= 0 && action.target < state.monsterCount) {
        static const std::map<int, std::string> monsters = {
            {static_cast<int>(sts::MonsterId::CULTIST), "Cultist"},
            {static_cast<int>(sts::MonsterId::JAW_WORM), "Jaw Worm"},
            {static_cast<int>(sts::MonsterId::GREMLIN_NOB), "Gremlin Nob"},
        };
        const auto monster = monsters.find(state.monsters[action.target].id);
        return name + " -> " + (monster == monsters.end() ? "Monster " + std::to_string(action.target + 1) : monster->second);
    }
    return name;
}

} // namespace one_combat::advisor
