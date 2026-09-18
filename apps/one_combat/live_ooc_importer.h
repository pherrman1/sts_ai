#pragma once

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "game/Card.h"

namespace one_combat::advisor {

struct PublicCard {
    sts::Card card;
};

struct PublicOocState {
    std::string boundary;
    std::string character;
    int ascension = 0;
    int act = 0;
    int floor = 0;
    int hp = 0;
    int maxHp = 0;
    int gold = 0;
    std::vector<PublicCard> deck;
    std::vector<PublicCard> candidates;
};

struct ImportResult {
    bool ok = false;
    std::string code;
    std::string message;
};

ImportResult importPublicOoc(const nlohmann::json &observation, PublicOocState &out);

} // namespace one_combat::advisor
