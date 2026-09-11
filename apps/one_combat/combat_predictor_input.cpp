#include "combat_predictor_input.h"

#include <algorithm>
#include <iomanip>
#include <sstream>
#include <tuple>

namespace one_combat {
namespace {

using namespace sts;
using J = nlohmann::json;

std::uint64_t fnv1a64(const std::string &value) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char byte : value) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }
    return hash;
}

bool isBurningElite(const GameContext &gc) {
    return gc.map != nullptr && gc.map->burningEliteX == gc.curMapNodeX
        && gc.map->burningEliteY == gc.curMapNodeY;
}

J globalsJson(const CombatPredictorGlobalsV1 &g) {
    return {
        {"characterClass", g.characterClass}, {"ascension", g.ascension},
        {"act", g.act}, {"floor", g.floor}, {"curHp", g.curHp},
        {"maxHp", g.maxHp}, {"gold", g.gold}, {"encounter", g.encounter},
        {"roomClass", g.roomClass}, {"lastRoom", g.lastRoom},
        {"potionCount", g.potionCount}, {"potionCapacity", g.potionCapacity},
        {"potionKeepValue", g.potionKeepValue},
        {"isBurningElite", g.isBurningElite}
    };
}

J cardJson(const CombatPredictorCardTokenV1 &c) {
    return {{"cardId", c.cardId}, {"upgraded", c.upgraded}, {"misc", c.misc},
            {"bottleBinding", c.bottleBinding}};
}

J relicJson(const CombatPredictorRelicTokenV1 &r) {
    return {{"relicId", r.relicId}, {"data", r.data}, {"orderIndex", r.orderIndex}};
}

J potionJson(const CombatPredictorPotionTokenV1 &p) {
    return {{"slot", p.slot}, {"potionId", p.potionId}};
}

} // namespace

CombatPredictorInputV1 captureCombatPredictorInput(const GameContext &gc,
                                                   MonsterEncounter encounter,
                                                   double potionKeepValue) {
    CombatPredictorInputV1 input;
    input.globals = {
        static_cast<int>(gc.cc), gc.ascension, gc.act, gc.floorNum, gc.curHp,
        gc.maxHp, gc.gold, static_cast<int>(encounter), static_cast<int>(gc.curRoom),
        static_cast<int>(gc.lastRoom), gc.potionCount, gc.potionCapacity,
        potionKeepValue, isBurningElite(gc)
    };

    input.cards.reserve(gc.deck.cards.size());
    for (int i = 0; i < gc.deck.size(); ++i) {
        int bottleBinding = -1;
        for (int binding = 0; binding < static_cast<int>(gc.deck.bottleIdxs.size()); ++binding) {
            if (gc.deck.bottleIdxs[binding] == i) {
                bottleBinding = binding;
                break;
            }
        }
        const auto &card = gc.deck.cards[i];
        input.cards.push_back({static_cast<int>(card.id), card.upgraded, card.misc,
                               bottleBinding});
    }
    std::sort(input.cards.begin(), input.cards.end(), [](const auto &lhs, const auto &rhs) {
        return std::tie(lhs.cardId, lhs.upgraded, lhs.misc, lhs.bottleBinding)
             < std::tie(rhs.cardId, rhs.upgraded, rhs.misc, rhs.bottleBinding);
    });

    input.relics.reserve(gc.relics.relics.size());
    for (int i = 0; i < static_cast<int>(gc.relics.relics.size()); ++i) {
        const auto &relic = gc.relics.relics[i];
        input.relics.push_back({static_cast<int>(relic.id), relic.data, i});
    }

    input.potions.reserve(gc.potions.size());
    for (int slot = 0; slot < static_cast<int>(gc.potions.size()); ++slot)
        input.potions.push_back({slot, static_cast<int>(gc.potions[slot])});
    return input;
}

nlohmann::json combatPredictorInputJson(const CombatPredictorInputV1 &input) {
    J cards = J::array();
    for (const auto &card : input.cards) cards.push_back(cardJson(card));
    J relics = J::array();
    for (const auto &relic : input.relics) relics.push_back(relicJson(relic));
    J potions = J::array();
    for (const auto &potion : input.potions) potions.push_back(potionJson(potion));
    return {{"schemaVersion", CombatPredictorInputV1::SCHEMA},
            {"fieldSchemaHash", combatPredictorInputFieldSchemaHash()},
            {"globals", globalsJson(input.globals)}, {"cards", std::move(cards)},
            {"relics", std::move(relics)}, {"potions", std::move(potions)}};
}

std::string combatPredictorInputFieldSchemaHash() {
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0')
        << fnv1a64(CombatPredictorInputV1::FIELD_SCHEMA);
    return out.str();
}

} // namespace one_combat
