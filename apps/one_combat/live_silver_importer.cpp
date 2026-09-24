#include "live_silver_importer.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>
#include <limits>
#include <iterator>
#include <optional>

#include "constants/CharacterClasses.h"
#include "constants/Relics.h"
#include "constants/MonsterIds.h"
#include "constants/MonsterMoves.h"
#include "constants/SaveFileMappings.h"
#include "constants/Potions.h"
#include "combat/CardSelectInfo.h"
#include "combat/InputState.h"
#include "combat/CardInstance.h"
#include "live_silver_mapping.h"

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
    const auto mapped = live_silver::monsterId(id);
    return mapped ? static_cast<int>(*mapped) : 0;
}

int moveId(const std::string &id, int nextMove) {
    const auto mapped = live_silver::monsterMove(id, nextMove);
    return mapped ? static_cast<int>(*mapped) : 0;
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

bool isOffColorIroncladCard(sts::CardId id) {
    const auto color = sts::getCardColor(id);
    return color == sts::CardColor::GREEN || color == sts::CardColor::BLUE
        || color == sts::CardColor::PURPLE;
}
bool isOffColorIroncladCard(const silver_bridge::CardWire &wire) {
    return isOffColorIroncladCard(static_cast<sts::CardId>(wire.id));
}

bool parseCards(const json &array, const std::string &location, std::vector<CardRecord> &out) {
    if (!array.is_array()) return false;
    for (const auto &item : array) { CardRecord record; if (!parseCard(item, location, record)) return false; out.push_back(std::move(record)); }
    return true;
}

bool optionalInt(const json &object, const char *name, int &out) {
    if (!object.contains(name)) return false;
    if (!object.at(name).is_number_integer()) return false;
    out = object.at(name).get<int>();
    return true;
}

bool optionalBool(const json &object, const char *name, bool &out) {
    if (!object.contains(name)) return false;
    if (!object.at(name).is_boolean()) return false;
    out = object.at(name).get<bool>();
    return true;
}

bool parseGenericCard(const json &item, CardRecord &out) {
    if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
        || !item.contains("uuid") || !item.at("uuid").is_string()) return false;
    try {
        const auto id = item.at("id").get<sts::CardId>();
        if (id == sts::CardId::INVALID) return false;
        out.uuid = item.at("uuid").get<std::string>();
        if (out.uuid.empty()) return false;
        out.wire.id = static_cast<std::int16_t>(id);
        out.wire.specialData = static_cast<std::int16_t>(item.value("misc", item.value("specialData", 0)));
        out.wire.cost = static_cast<std::int16_t>(item.value("cost", 0));
        out.wire.costForTurn = static_cast<std::int16_t>(item.value("costForTurn", out.wire.cost));
        out.wire.upgraded = item.value("upgraded", false);
        out.wire.freeToPlayOnce = item.value("freeToPlayOnce", false);
        out.wire.retain = item.value("retain", false);
        if (!item.value("upgraded", false) && (!item.contains("upgraded") || !item.at("upgraded").is_boolean())) return false;
        return item.value("cost", 0) >= -2 && item.value("costForTurn", item.value("cost", 0)) >= -2;
    } catch (...) { return false; }
}

struct GenericPile {
    std::vector<CardRecord> bottom, unknown, 