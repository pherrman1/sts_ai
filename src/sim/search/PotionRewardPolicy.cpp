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
    switch (p) {
        case Potion::FAIRY_POTION:          return 100;
        case Potion::FRUIT_JUICE:           return 95;
        case Potion::GHOST_IN_A_JAR:        return 90;
        case Potion::CULTIST_POTION:        return 85;
        case Potion::ENTROPIC_BREW:         return 80;
        case Potion::DISTILLED_CHAOS:       return 78;
        case Potion::STRENGTH_POTION:       return 76;
        case Potion::POWER_POTION:          return 74;
        case Potion::DUPLICATION_POTION:    return 72;
        case Potion::SMOKE_BOMB:            return 70;
        case Potion::HEART_OF_IRON:         return 68;
        case Potion::FEAR_POTION:           return 66;
        case Potion::ATTACK_POTION:         return 65;
        case Potion::REGEN_POTION:          return 64;
        case Potion::BLOOD_POTION:          return 63;
        case Potion::ENERGY_POTION:         return 62;
        case Potion::WEAK_POTION:           return 61;
        case Potion::FLEX_POTION:           return 60;
        case Potion::ESSENCE_OF_STEEL:      return 59;
        case Potion::LIQUID_MEMORIES:       return 58;
        case Potion::SKILL_POTION:          return 57;
        case Potion::SWIFT_POTION:          return 56;
        case Potion::ANCIENT_POTION:        return 55;
        case Potion::EXPLOSIVE_POTION:      return 54;
        case Potion::FIRE_POTION:           return 53;
        case Potion::DEXTERITY_POTION:      return 52;
        case Potion::SNECKO_OIL:            return 51;
        case Potion::COLORLESS_POTION:      return 50;
        case Potion::BLOCK_POTION:          return 49;
        case Potion::SPEED_POTION:          return 48;
        case Potion::LIQUID_BRONZE:         return 47;
        case Potion::BLESSING_OF_THE_FORGE: return 46;
        case Potion::ELIXIR_POTION:         return 45;
        case Potion::GAMBLERS_BREW:         return 44;
        case Potion::EMPTY_POTION_SLOT:
        case Potion::INVALID:               return -1;
        default:                            return 20;  // other classes' potions
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
