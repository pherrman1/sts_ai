#include "combat_transition.h"

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
