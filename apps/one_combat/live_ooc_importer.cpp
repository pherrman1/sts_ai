#include "live_ooc_importer.h"

#include <limits>

#include "constants/SaveFileMappings.h"

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

} // namespace one_combat::advisor
