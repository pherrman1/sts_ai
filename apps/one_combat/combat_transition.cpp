#include "combat_transition.h"

#include <stdexcept>
#include <sstream>
#include <utility>

namespace one_combat {
namespace {

using namespace sts;
using J = nlohmann::json;

CombatTransitionRandomState randomState(const Random &r) {
    return {r.counter, r.seed0, r.seed1};
}

void restoreRandom(Random &r, const CombatTransitionRandomState &s) {
    r.counter = s.counter;
    r.seed0 = s.seed0;
    r.seed1 = s.seed1;
}

J randomJson(const CombatTransitionRandomState &s) {
    return {{"counter", s.counter}, {"seed0", s.seed0}, {"seed1", s.seed1}};
}

J cardJson(const CombatTransitionCardState &c) {
    return {{"id", c.id}, {"misc", c.misc}, {"upgraded", c.upgraded}};
}

J relicJson(const CombatTransitionRelicState &r) {
    return {{"id", r.id}, {"data", r.data}};
}

} // namespace

CombatTransitionPersistentState captureCombatTransitionState(const GameContext &gc) {
    CombatTransitionPersistentState state;
    state.curHp = gc.curHp;
    state.maxHp = gc.maxHp;
    state.gold = gc.gold;
    state.potionCount = gc.potionCount;
    state.potionCapacity = gc.potionCapacity;
    for (std::size_t i = 0; i < state.potions.size(); ++i)
        state.potions[i] = static_cast<int>(gc.potions[i]);
    state.smokeBombUsed = gc.smokeBombUsed;
    state.stolenGold = gc.info.stolenGold;

    state.relicBits = {gc.relics.relicBits0, gc.relics.relicBits1, gc.relics.relicBits2};
    state.relics.reserve(gc.relics.relics.size());
    for (const auto &r : gc.relics.relics)
        state.relics.push_back({static_cast<int>(r.id), r.data});

    state.deck.reserve(gc.deck.cards.size());
    for (const auto &c : gc.deck.cards)
        state.deck.push_back({static_cast<int>(c.id), c.misc, c.upgraded});
    state.cardTypeCounts = gc.deck.cardTypeCounts;
    state.bottleIdxs = gc.deck.bottleIdxs;
    state.upgradeableCount = gc.deck.upgradeableCount;
    state.transformableCount = gc.deck.transformableCount;

    state.combatRng = {randomState(gc.aiRng), randomState(gc.cardRandomRng),
                       randomState(gc.miscRng), randomState(gc.monsterHpRng),
                       randomState(gc.potionRng), randomState(gc.shuffleRng)};
    return state;
}

void applyCombatTransitionState(GameContext &gc,
                                const CombatTransitionPersistentState &state) {
    gc.curHp = state.curHp;
    gc.maxHp = state.maxHp;
    gc.gold = state.gold;
    gc.potionCount = state.potionCount;
    gc.potionCapacity = state.potionCapacity;
    for (std::size_t i = 0; i < state.potions.size(); ++i)
        gc.potions[i] = static_cast<Potion>(state.potions[i]);
    gc.smokeBombUsed = state.smokeBombUsed;
    gc.info.stolenGold = state.stolenGold;

    gc.relics.relics.clear();
    for (const auto &r : state.relics)
        gc.relics.relics.push_back({static_cast<RelicId>(r.id), r.data});
    gc.relics.relicBits0 = state.relicBits[0];
    gc.relics.relicBits1 = state.relicBits[1];
    gc.relics.relicBits2 = state.relicBits[2];

    gc.deck.cards.clear();
    for (const auto &c : state.deck) {
        Card card(static_cast<CardId>(c.id));
        card.misc = c.misc;
        card.upgraded = c.upgraded;
        gc.deck.cards.push_back(card);
    }
    gc.deck.cardTypeCounts = state.cardTypeCounts;
    gc.deck.bottleIdxs = state.bottleIdxs;
    gc.deck.upgradeableCount = state.upgradeableCount;
    gc.deck.transformableCount = state.transformableCount;

    restoreRandom(gc.aiRng, state.combatRng[0]);
    restoreRandom(gc.cardRandomRng, state.combatRng[1]);
    restoreRandom(gc.miscRng, state.combatRng[2]);
    restoreRandom(gc.monsterHpRng, state.combatRng[3]);
    restoreRandom(gc.potionRng, state.combatRng[4]);
    restoreRandom(gc.shuffleRng, state.combatRng[5]);
}

CombatTransitionRecord captureCombatTransition(const GameContext &pre,
                                               const BattleContext &bc,
                                               const GameContext &rawPost) {
    return {bc.outcome, rawPost.outcome, captureCombatTransitionState(pre),
            captureCombatTransitionState(rawPost)};
}

J combatTransitionStateJson(const CombatTransitionPersistentState &state) {
    J relics = J::array();
    for (const auto &r : state.relics) relics.push_back(relicJson(r));
    J deck = J::array();
    for (const auto &c : state.deck) deck.push_back(cardJson(c));
    J rng = J::array();
    for (const auto &r : state.combatRng) rng.push_back(randomJson(r));
    return {
        {"curHp", state.curHp}, {"maxHp", state.maxHp}, {"gold", state.gold},
        {"potionCount", state.potionCount}, {"potionCapacity", state.potionCapacity},
        {"potions", state.potions}, {"smokeBombUsed", state.smokeBombUsed},
        {"stolenGold", state.stolenGold}, {"relics", std::move(relics)},
        {"relicBits", state.relicBits}, {"deck", std::move(deck)},
        {"cardTypeCounts", state.cardTypeCounts}, {"bottleIdxs", state.bottleIdxs},
        {"upgradeableCount", state.upgradeableCount},
        {"transformableCount", state.transformableCount}, {"combatRng", std::move(rng)}
    };
}

CombatTransitionPersistentState combatTransitionStateFromJson(const J &value) {
    static const std::array<const char *, 16> keys = {
        "curHp", "maxHp", "gold", "potionCount", "potionCapacity", "potions",
        "smokeBombUsed", "stolenGold", "relics", "relicBits", "deck",
        "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount",
        "combatRng"
    };
    if (!value.is_object() || value.size() != keys.size())
        throw std::runtime_error("combat transition snapshot has an invalid object shape");
    for (const auto *key : keys)
        if (!value.contains(key))
            throw std::runtime_error(std::string("combat transition snapshot missing ") + key);

    CombatTransitionPersistentState state;
    state.curHp = value.at("curHp").get<int>();
    state.maxHp = value.at("maxHp").get<int>();
    state.gold = value.at("gold").get<int>();
    state.potionCount = value.at("potionCount").get<int>();
    state.potionCapacity = value.at("potionCapacity").get<int>();
    state.potions = value.at("potions").get<std::array<int, 5>>();
    state.smokeBombUsed = value.at("smokeBombUsed").get<bool>();
    state.stolenGold = value.at("stolenGold").get<int>();
    state.relicBits = value.at("relicBits").get<std::array<std::uint64_t, 3>>();
    state.cardTypeCounts = value.at("cardTypeCounts").get<std::array<int, 4>>();
    state.bottleIdxs = value.at("bottleIdxs").get<std::array<int, 3>>();
    state.upgradeableCount = value.at("upgradeableCount").get<int>();
    state.transformableCount = value.at("transformableCount").get<int>();

    if (!value.at("relics").is_array() || !value.at("deck").is_array()
        || !value.at("combatRng").is_array() || value.at("combatRng").size() != 6)
        throw std::runtime_error("combat transition snapshot has invalid array fields");
    for (const auto &relic : value.at("relics")) {
        if (!relic.is_object() || relic.size() != 2 || !relic.contains("id")
            || !relic.contains("data"))
            throw std::runtime_error("combat transition snapshot has an invalid relic");
        state.relics.push_back({relic.at("id").get<int>(), relic.at("data").get<int>()});
    }
    for (const auto &card : value.at("deck")) {
        if (!card.is_object() || card.size() != 3 || !card.contains("id")
            || !card.contains("misc") || !card.contains("upgraded"))
            throw std::runtime_error("combat transition snapshot has an invalid card");
        state.deck.push_back({card.at("id").get<int>(), card.at("misc").get<std::int16_t>(),
                              card.at("upgraded").get<bool>()});
    }
    for (std::size_t i = 0; i < state.combatRng.size(); ++i) {
        const auto &rng = value.at("combatRng").at(i);
        if (!rng.is_object() || rng.size() != 3 || !rng.contains("counter")
            || !rng.contains("seed0") || !rng.contains("seed1"))
            throw std::runtime_error("combat transition snapshot has an invalid RNG state");
        state.combatRng[i] = {
            rng.at("counter").get<std::int32_t>(),
            rng.at("seed0").get<std::uint64_t>(),
            rng.at("seed1").get<std::uint64_t>()
        };
    }
    return state;
}

J combatTransitionRecordJson(const CombatTransitionRecord &record) {
    return {{"schemaVersion", CombatTransitionRecord::SCHEMA},
            {"combatOutcome", static_cast<int>(record.combatOutcome)},
            {"rawGameOutcome", static_cast<int>(record.rawGameOutcome)},
            {"pre", combatTransitionStateJson(record.pre)},
            {"post", combatTransitionStateJson(record.post)}};
}

std::string combatTransitionFingerprint(const GameContext &gc) {
    return combatTransitionStateJson(captureCombatTransitionState(gc)).dump();
}

CombatTransitionRawObserverScope::CombatTransitionRawObserverScope(
    const std::function<void(const BattleContext &, GameContext &)> &observer)
    : previous_(std::move(g_onBattleExitRaw)) {
    g_onBattleExitRaw = [previous = previous_, observer](const BattleContext &bc,
                                                          GameContext &gc) {
        if (previous) previous(bc, gc);
        if (observer) observer(bc, gc);
    };
}

CombatTransitionRawObserverScope::~CombatTransitionRawObserverScope() {
    g_onBattleExitRaw = std::move(previous_);
}

} // namespace one_combat
