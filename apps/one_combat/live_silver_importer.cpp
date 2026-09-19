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

bool parseCard(const json &item, const std::string &location, CardRecord &out) {
    if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
        || !item.contains("uuid") || !item.at("uuid").is_string()) return false;
    try {
        const auto cardId = item.at("id").get<sts::CardId>();
        if (cardId == sts::CardId::INVALID) return false;
        out.uuid = item.at("uuid").get<std::string>();
        out.wire.id = static_cast<std::int16_t>(cardId);
        out.wire.specialData = item.value("misc", 0);
        out.wire.cost = item.value("cost", 0);
        out.wire.costForTurn = item.value("costForTurn", out.wire.cost);
        out.wire.upgraded = item.value("upgraded", false);
        out.wire.freeToPlayOnce = item.value("freeToPlayOnce", false);
        out.wire.retain = item.value("retain", false);
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
    if (id == "Cultist") return static_cast<int>(sts::MonsterMoveId::CULTIST_INCANTATION);
    if (id == "JawWorm") {
        if (nextMove == 1) return static_cast<int>(sts::MonsterMoveId::JAW_WORM_CHOMP);
        if (nextMove == 2) return static_cast<int>(sts::MonsterMoveId::JAW_WORM_THRASH);
        if (nextMove == 3) return static_cast<int>(sts::MonsterMoveId::JAW_WORM_BELLOW);
    }
    if (id == "Gremlin Nob" || id == "GremlinNob") {
        if (nextMove == 1) return static_cast<int>(sts::MonsterMoveId::GREMLIN_NOB_BELLOW);
        if (nextMove == 2) return static_cast<int>(sts::MonsterMoveId::GREMLIN_NOB_RUSH);
        if (nextMove == 3) return static_cast<int>(sts::MonsterMoveId::GREMLIN_NOB_SKULL_BASH);
    }
    return 0;
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
    if (root.value("schemaVersion", 0) != 1) return unsupported("silver_schema_version");
    if (!root.value("firstDecision", false)) return unsupported("silver_not_first_decision");
    if (observation.value("character", std::string()) != "IRONCLAD") return unsupported("silver_character");
    const auto &combat = root.at("combat");
    if (!combat.is_object()) return unsupported("silver_combat_missing");
    if (combat.value("runicDome", false)) return unsupported("silver_runic_dome");
    if (combat.value("frozenEye", false)) return unsupported("silver_frozen_eye");
    if (combat.value("cardsPlayedThisTurn", 0) != 0) return unsupported("silver_not_first_decision");
    if (combat.value("cardSelect", false) || combat.value("resolving", false)) return unsupported("silver_card_select");
    int turn = 0, energy = 0, block = 0;
    if (!requiredInt(combat, "turn", turn) || !requiredInt(combat, "energy", energy) || !requiredInt(combat, "block", block) || turn != 1)
        return unsupported("silver_first_turn_invariant");

    std::vector<CardRecord> cards;
    if (!parseCards(combat.value("hand", json::array()), "HAND", cards)
        || !parseCards(combat.value("draw", json::array()), "DRAW", cards)
        || !parseCards(combat.value("discard", json::array()), "DISCARD", cards)
        || !parseCards(combat.value("exhaust", json::array()), "EXHAUST", cards)) return unsupported("silver_unknown_card");
    std::sort(cards.begin(), cards.end(), [](const CardRecord &a, const CardRecord &b) { return a.uuid < b.uuid; });
    std::set<std::string> uuids;
    for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
        if (!uuids.insert(cards[i].uuid).second || cards[i].uuid.empty()) return unsupported("silver_card_identity");
        cards[i].wire.uniqueId = static_cast<std::int16_t>(i + 1);
    }
    wire.nextUniqueCardId = static_cast<int>(cards.size()) + 1;
    // Reparse by source so the UUID mapping above is applied without exposing pile order.
    std::unordered_map<std::string, silver_bridge::CardWire> byUuid;
    for (const auto &card : cards) byUuid.emplace(card.uuid, card.wire);
    const auto appendPile = [&](const char *name, std::vector<silver_bridge::CardWire> &target) {
        for (const auto &item : combat.value(name, json::array())) {
            const auto uuid = item.value("uuid", std::string());
            target.push_back(byUuid.at(uuid));
        }
        std::sort(target.begin(), target.end(), [](const auto &a, const auto &b) { return a.uniqueId < b.uniqueId; });
    };
    appendPile("hand", wire.hand); appendPile("draw", wire.drawPile.unknown);
    appendPile("discard", wire.discardPile.unknown); appendPile("exhaust", wire.exhaustPile.unknown);
    wire.drawPile.valid = wire.discardPile.valid = wire.exhaustPile.valid = true;
    wire.drawPile.fullOrderObserved = wire.discardPile.fullOrderObserved = wire.exhaustPile.fullOrderObserved = false;

    wire.version = silver_bridge::BattleStateWire::kVersion;
    wire.valid = true; wire.fullDrawOrderObserved = false; wire.intentsHidden = false;
    wire.floorNum = root.value("floor", 0); wire.act = root.value("act", 1);
    wire.ascension = root.value("ascension", 0); wire.turn = turn; wire.outcome = 0; wire.inputState = 1; // PLAYER_NORMAL
    wire.potionCapacity = root.value("potionCapacity", 0); wire.potionCount = 0;
    wire.potions.fill(static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT));
    wire.monsterTurnIdx = 0; wire.endTurnQueued = false; wire.turnHasEnded = false; wire.skipMonsterTurn = false;
    wire.player.characterClass = static_cast<std::int16_t>(sts::CharacterClass::IRONCLAD);
    wire.player.curHp = root.value("hp", 0); wire.player.maxHp = root.value("maxHp", 0);
    wire.player.gold = root.value("gold", 0); wire.player.energy = energy; wire.player.energyPerTurn = 3;
    wire.player.cardDrawPerTurn = 5; wire.player.block = block;
    const int burningBlood = static_cast<int>(sts::RelicId::BURNING_BLOOD);
    wire.player.relicBits0 = burningBlood < 64 ? (1ULL << burningBlood) : 0;
    wire.player.relicBits1 = burningBlood >= 64 ? (1ULL << (burningBlood - 64)) : 0;
    for (const auto &relic : combat.value("relics", json::array()))
        if (relic.value("id", std::string()) != "Burning Blood") return unsupported("silver_unmapped_relic_state");
    for (const auto &potion : combat.value("potions", json::array()))
        if (potion.value("id", std::string()) != "Potion Slot") return unsupported("silver_unmapped_potion_state");

    const auto monsters = combat.value("monsters", json::array());
    if (!monsters.is_array() || monsters.empty() || monsters.size() > wire.monsters.size()) return unsupported("silver_unknown_monster");
    wire.monsterCount = wire.monstersAlive = static_cast<int>(monsters.size());
    for (std::size_t i = 0; i < monsters.size(); ++i) {
        const auto &item = monsters[i]; const auto id = item.value("id", std::string());
        const int canonical = monsterId(id), move = moveId(id, item.value("nextMove", 0));
        if (canonical == 0) return unsupported("silver_unknown_monster");
        if (move == 0) return unsupported("silver_unknown_move");
        auto &monster = wire.monsters[i]; monster.idx = static_cast<int>(i); monster.id = canonical;
        monster.curHp = item.value("hp", 0); monster.maxHp = item.value("maxHp", monster.curHp);
        monster.block = item.value("block", 0); monster.moveHistory = {static_cast<std::int16_t>(move), 0};
    }
    if (monsters.size() == 1) {
        const auto id = monsters.front().value("id", std::string());
        if (id == "Cultist") wire.encounter = static_cast<int>(sts::MonsterEncounter::CULTIST);
        else if (id == "JawWorm") wire.encounter = static_cast<int>(sts::MonsterEncounter::JAW_WORM);
        else if (id == "Gremlin Nob" || id == "GremlinNob") wire.encounter = static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB);
    }
    wire.isolatedSearchSeed = fnv1a(observation.value("observationHash", std::string()) + ":silver-root-v1");
    wire.observedGeneration = 1;
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
