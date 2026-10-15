#include "sim/search/PotionRewardPolicy.h"

#include <cstdlib>
#include <stdexcept>
#include <string>

using namespace sts;

bool search::potionRewardSwapEnabled() {
    const char *value = std::getenv("STS_POTION_REWARD_SWAP");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_POTION_REWARD_SWAP must be 0 or 1");
}

int search::potionKeepRank(Potion p) {
    // Fitted keep values x100 (tools/potion_keep/, ADR-0039): HP-equivalent
    // fight outcome gain from holding the potion at fight start, with seed and
    // encounter fixed effects on the A20 and A0 CTM corpora; a death counts
    // SilverEvalWeights::winBonus (53). Mean of the two ascensions.
    switch (p) {
        case Potion::BLOOD_POTION:           return 1163;
        case Potion::SMOKE_BOMB:             return 1034;
        case Potion::FRUIT_JUICE:            return 924;
        case Potion::HEART_OF_IRON:          return 666;
        case Potion::ENTROPIC_BREW:          return 628;
        case Potion::REGEN_POTION:           return 596;
        case Potion::DISTILLED_CHAOS:        return 581;
        case Potion::FAIRY_POTION:           return 463;
        case Potion::LIQUID_MEMORIES:        return 455;
        case Potion::ATTACK_POTION:          return 443;
        case Potion::DUPLICATION_POTION:     return 440;
        case Potion::POWER_POTION:           return 419;
        case Potion::SNECKO_OIL:             return 413;
        case Potion::BLOCK_POTION:           return 405;
        case Potion::FIRE_POTION:            return 393;
        case Potion::COLORLESS_POTION:       return 392;
        case Potion::FLEX_POTION:            return 350;
        case Potion::STRENGTH_POTION:        return 346;
        case Potion::BLESSING_OF_THE_FORGE:  return 328;
        case Potion::CULTIST_POTION:         return 322;
        case Potion::ENERGY_POTION:          return 318;
        case Potion::FEAR_POTION:            return 295;
        case Potion::SKILL_POTION:           return 292;
        case Potion::EXPLOSIVE_POTION:       return 291;
        case Potion::ESSENCE_OF_STEEL:       return 278;
        case Potion::SWIFT_POTION:           return 224;
        case Potion::WEAK_POTION:            return 212;
        case Potion::GAMBLERS_BREW:          return 196;
        case Potion::ANCIENT_POTION:         return 168;
        case Potion::DEXTERITY_POTION:       return 113;
        case Potion::SPEED_POTION:           return 113;
        case Potion::LIQUID_BRONZE:          return 106;
        case Potion::ELIXIR_POTION:          return 47;
        case Potion::EMPTY_POTION_SLOT:
        case Potion::INVALID:                return -1;
        default:                             return 0;  // not fitted (other classes' potions)
    }
}

std::optional<search::GameAction> search::potionRewardAction(const GameContext &gc) {
    using RT = GameAction::RewardsActionType;
    if (gc.screenState != ScreenState::REWARDS) return std::nullopt;
    const auto &r = gc.info.rewardsContainer;
    if (r.potionCount <= 0) return std::nullopt;
    const bool freeSlot = gc.potionCount < gc.potionCapacity;
    // With Sozu a pickup obtains nothing, so it keeps the legacy behavior.
    if (!potionRewardSwapEnabled() || gc.hasRelic(RelicId::SOZU)) {
        if (freeSlot) return GameAction(RT::POTION, 0);
        return std::nullopt;
    }
    int best = 0;
    for (int i = 1; i < r.potionCount; ++i)
        if (potionKeepRank(r.potions[i]) > potionKeepRank(r.potions[best])) best = i;
    if (freeSlot) return GameAction(RT::POTION, best);
    int worst = -1;
    for (int slot = 0; slot < gc.potionCapacity; ++slot) {
        const auto held = gc.potions[slot];
        if (held == Potion::EMPTY_POTION_SLOT || held == Potion::INVALID) continue;
        if (worst < 0 || potionKeepRank(held) < potionKeepRank(gc.potions[worst])) worst = slot;
    }
    if (worst < 0 || potionKeepRank(r.potions[best]) <= potionKeepRank(gc.potions[worst])) return std::nullopt;
    const GameAction discard(0xC0000000u | static_cast<unsigned>(worst));
    if (!discard.isValidAction(gc)) return std::nullopt;
    return discard;
}
