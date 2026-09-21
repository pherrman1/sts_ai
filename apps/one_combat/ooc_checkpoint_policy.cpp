#include "ooc_checkpoint_policy.h"

#include "sim/search/GameAction.h"

namespace one_combat {

bool collectFreeOocReward(sts::GameContext &gc, bool collectKeys) {
    if (gc.screenState != sts::ScreenState::REWARDS) return false;
    using RT = sts::search::GameAction::RewardsActionType;
    auto &rewards = gc.info.rewardsContainer;
    if (rewards.goldRewardCount > 0) {
        sts::search::GameAction(RT::GOLD, 0).execute(gc);
        return true;
    }
    if (rewards.relicCount > 0) {
        sts::search::GameAction(RT::RELIC, 0).execute(gc);
        return true;
    }
    if (rewards.potionCount > 0) {
        sts::search::GameAction(RT::POTION, 0).execute(gc);
        return true;
    }
    if (collectKeys && rewards.emeraldKey) {
        sts::search::GameAction(RT::KEY, 0).execute(gc);
        return true;
    }
    if (collectKeys && rewards.sapphireKey) {
        sts::search::GameAction(RT::KEY, 0).execute(gc);
        return true;
    }
    if (rewards.cardRewardCount == 0) {
        sts::search::GameAction(RT::SKIP).execute(gc);
        return true;
    }
    return false;
}

} // namespace one_combat
