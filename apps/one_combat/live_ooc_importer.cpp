#include "live_ooc_importer.h"

#include <algorithm>
#include <limits>
#include <tuple>

#include "constants/SaveFileMappings.h"
#include "constants/Rooms.h"

namespace one_combat::advisor {

namespace {

ImportResult bad(const char *code, const std::string &message) {
    return {false, code, message};
}

ImportResult number(const nlohmann::json &object, const char *name, int &out) {
    if (!object.contains(name) || !object.at(name).is_number_integer())
        return bad("SCHEMA_MISMATCH", std::string("observation.") + name + " must be an integer");
    const auto value = object.at(name).get<std::int64_t>();
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
        return bad("SCHEMA_MISMATCH", std::string("observation.") + name + " is out of range");
    out = static_cast<int>(value);
    return {true, {}, {}};
}

ImportResult cards(const nlohmann::json &object, const char *name,
                   std::vector<PublicCard> &out) {
    if (!object.contains(name) || !object.at(name).is_array())
        return bad("SCHEMA_MISMATCH", std::string("observation.") + name + " must be an array");
    for (const auto &wire : object.at(name)) {
        if (!wire.is_object() || !wire.contains("id") || !wire.at("id").is_string()
            || !wire.contains("upgraded") || !wire.at("upgraded").is_boolean()
            || !wire.contains("misc") || !wire.at("misc").is_number_integer())
            return bad("SCHEMA_MISMATCH", std::string("observation.") + name +
                       " contains an invalid card instance");
        sts::CardId id = sts::CardId::INVALID;
        try {
            id = nlohmann::json(wire.at("id").get<std::string>()).get<sts::CardId>();
        } catch (const nlohmann::json::exception &) {
            return bad("UNKNOWN_CARD_ID", "observation contains an unknown save-file card ID");
        }
        if (id == sts::CardId::INVALID)
            return bad("UNKNOWN_CARD_ID", "observation contains an unknown save-file card ID");
        const auto misc = wire.at("misc").get<std::int64_t>();
        if (misc < std::numeric_limits<std::int16_t>::min()
            || misc > std::numeric_limits<std::int16_t>::max())
            return bad("SCHEMA_MISMATCH", "card misc value is out of range");
        out.push_back({sts::Card(id, wire.at("upgraded").get<bool>() ? 1 : 0)});
        out.back().card.misc = static_cast<std::int16_t>(misc);
    }
    return {true, {}, {}};
}

} // namespace

ImportResult importPublicOoc(const nlohmann::json &observation, PublicOocState &out) {
    if (!observation.is_object())
        return bad("SCHEMA_MISMATCH", "observation must be an object");
    if (!observation.contains("boundary") || !observation.at("boundary").is_string())
        return bad("SCHEMA_MISMATCH", "observation.boundary must be a string");
    out.boundary = observation.at("boundary").get<std::string>();
    if (out.boundary != "card_reward" && out.boundary != "rest")
        return bad("UNSUPPORTED_BOUNDARY", "native OOC importer supports card_reward and rest only");
    if (!observation.contains("character") || !observation.at("character").is_string())
        return bad("SCHEMA_MISMATCH", "observation.character must be a string");
    out.character = observation.at("character").get<std::string>();
    if (out.character != "IRONCLAD")
        return bad("UNSUPPORTED_CHARACTER", "native OOC importer supports Ironclad only");
    for (const auto field : {"ascension", "act", "floor", "hp", "maxHp", "gold"}) {
        int value = 0;
        const auto result = number(observation, field, value);
        if (!result.ok) return result;
        if (field == std::string("ascension")) out.ascension = value;
        else if (field == std::string("act")) out.act = value;
        else if (field == std::string("floor")) out.floor = value;
        else if (field == std::string("hp")) out.hp = value;
        else if (field == std::string("maxHp")) out.maxHp = value;
        else out.gold = value;
    }
    if (out.ascension < 0 || out.act < 1 || out.floor < 0 || out.hp < 0
        || out.maxHp < 1 || out.hp > out.maxHp || out.gold < 0)
        return bad("SCHEMA_MISMATCH", "observation contains invalid run values");
    out.deck.clear();
    out.candidates.clear();
    auto result = cards(observation, "deck", out.deck);
    if (!result.ok) return result;
    return cards(observation, "candidates", out.candidates);
}

ImportResult importCombatPredictorInput(const nlohmann::json &o,
                                         CombatPredictorInputV1 &out) {
    if (!o.is_object() || o.value("boundary", std::string()) != "combat")
        return bad("UNSUPPORTED_BOUNDARY", "combat entry observation required");
    const auto &s = o.contains("combatEntry") && o.at("combatEntry").is_object()
        ? o.at("combatEntry") : o;
    if (s.value("character", std::string()) != "IRONCLAD")
        return bad("UNSUPPORTED_CHARACTER", "native forecast supports Ironclad only");
    for (const char *name : {"ascension", "act", "floor", "hp", "maxHp", "gold",
                             "potionCapacity"}) {
        int value = 0; auto r = number(s, name, value); if (!r.ok) return r;
        if (std::string(name) == "ascension") out.globals.ascension = value;
        else if (std::string(name) == "act") out.globals.act = value;
        else if (std::string(name) == "floor") out.globals.floor = value;
        else if (std::string(name) == "hp") out.globals.curHp = value;
        else if (std::string(name) == "maxHp") out.globals.maxHp = value;
        else if (std::string(name) == "gold") out.globals.gold = value;
        else out.globals.potionCapacity = value;
    }
    out.globals.characterClass = static_cast<int>(sts::CharacterClass::IRONCLAD);
    out.globals.potionKeepValue = s.value("potionKeepValue", 4.0);
    out.globals.isBurningElite = s.value("isBurningElite", false);
    auto room = s.value("roomClass", std::string());
    auto previous = s.value("previousRoomClass", std::string());
    auto encounter = s.value("encounter", std::string());
    auto enumId = [](const char *const *names, int n, const std::string &s) {
        for (int i = 0; i < n; ++i) if (s == names[i]) return i;
        return -1;
    };
    out.globals.roomClass = enumId(sts::roomStrings, 10, room);
    out.globals.lastRoom = enumId(sts::roomStrings, 10, previous);
    out.globals.encounter = enumId(sts::monsterEncounterEnumNames,
                                   static_cast<int>(sizeof(sts::monsterEncounterEnumNames) /
                                                    sizeof(*sts::monsterEncounterEnumNames)), encounter);
    if (out.globals.roomClass < 0 || out.globals.lastRoom < 0 || out.globals.encounter <= 0)
        return bad("UNSUPPORTED", "encounter or room identity is not canonical");
    out.cards.clear(); out.relics.clear(); out.potions.clear();
    if (!s.contains("deck") || !s.at("deck").is_array()) return bad("SCHEMA_MISMATCH", "deck must be an array");
    for (const auto &wire : s.at("deck")) {
        if (!wire.is_object() || !wire.contains("id") || !wire.contains("upgraded")
            || !wire.contains("misc") || !wire.contains("bottleBinding"))
            return bad("SCHEMA_MISMATCH", "invalid deck card instance");
        sts::CardId id = sts::CardId::INVALID;
        try { id = wire.at("id").get<sts::CardId>(); } catch (...) { id = sts::CardId::INVALID; }
        if (id == sts::CardId::INVALID) return bad("UNKNOWN_CARD_ID", "unknown save-file card ID");
        out.cards.push_back({static_cast<int>(id), wire.at("upgraded").get<bool>(),
                             wire.at("misc").get<int>(), wire.at("bottleBinding").get<int>()});
    }
    if (!s.contains("relics") || !s.at("relics").is_array()) return bad("SCHEMA_MISMATCH", "relics must be an array");
    int order = 0;
    for (const auto &wire : s.at("relics")) {
        if (!wire.is_object() || !wire.contains("id") || !wire.contains("data")) return bad("SCHEMA_MISMATCH", "invalid relic instance");
        sts::RelicId id = sts::RelicId::INVALID;
        try { id = wire.at("id").get<sts::RelicId>(); } catch (...) { id = sts::RelicId::INVALID; }
        if (id == sts::RelicId::INVALID) return bad("UNKNOWN_RELIC_ID", "unknown save-file relic ID");
        out.relics.push_back({static_cast<int>(id), wire.at("data").get<int>(), order++});
    }
    if (!s.contains("potions") || !s.at("potions").is_array() || s.at("potions").size() != 5)
        return bad("SCHEMA_MISMATCH", "potions must contain five native slots");
    int slot = 0;
    for (const auto &wire : s.at("potions")) {
        if (!wire.is_string()) return bad("SCHEMA_MISMATCH", "potion ID must be a string");
        sts::Potion id = sts::Potion::INVALID;
        try { id = wire.get<sts::Potion>(); } catch (...) { id = sts::Potion::INVALID; }
        if (id == sts::Potion::INVALID) return bad("UNKNOWN_POTION_ID", "unknown save-file potion ID");
        out.potions.push_back({slot++, static_cast<int>(id)});
    }
    out.globals.potionCount = 0;
    for (const auto &p : out.potions) out.globals.potionCount += p.potionId > 1;
    std::sort(out.cards.begin(), out.cards.end(), [](const auto &a, const auto &b) {
        return std::tie(a.cardId, a.upgraded, a.misc, a.bottleBinding) <
               std::tie(b.cardId, b.upgraded, b.misc, b.bottleBinding);
    });
    return {true, {}, {}};
}

} // namespace one_combat::advisor
