// Fixed OOC rules shared by the run driver, the OOC MCTS tree and rollouts,
// and the live advisor root (ADR-0031, ADR-0041). Kept apart from
// run_driver.cpp so the live advisor links the same rules.
#include "run_driver.h"

#include "sim/search/GameAction.h"
#include "sim/search/PotionRewardPolicy.h"
#include "sim/search/RunGoal.h"

extern bool g_collectKeys;

using namespace sts;

// Opening a treasure chest is free unless Cursed Key turns it into a curse,
// so every OOC policy opens it without Cursed Key (#347: live OOC MCTS left
// every chest closed). With Cursed Key the ordinary decision runs.
std::optional<search::GameAction> treasureChestRuleAction(const GameContext &gc) {
    if (gc.screenState != ScreenState::TREASURE_ROOM || gc.relics.has(RelicId::CURSED_KEY)) return std::nullopt;
    return search::GameAction(0);
}

// Every offered reward relic (elites, event elites, chests) is taken first,
// except Philipp's listed exceptions (2026-10-07), which go to the ordinary
// decision. Live OOC MCTS left most chest relics because its leaf value prices
// them near zero (#347, ledger §390). The Heart key rule runs first to preserve Sapphire pairing.
static bool reviewedRewardRelic(RelicId id) {
    switch (id) {
        case RelicId::BOTTLED_FLAME: case RelicId::BOTTLED_LIGHTNING: case RelicId::BOTTLED_TORNADO:
        case RelicId::DEAD_BRANCH: case RelicId::TUNGSTEN_ROD: case RelicId::UNCEASING_TOP:
        case RelicId::JUZU_BRACELET: return true;
        default: return false;
    }
}
std::optional<search::GameAction> rewardRelicRuleAction(const GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState != ScreenState::REWARDS) return std::nullopt;
    const auto &r = gc.info.rewardsContainer;
    // Under a key rule that leaves Sapphire as a choice (STS_KEY_SAPPHIRE=policy, the ADR-0063 default),
    // taking the paired relic would remove the key offer.
    if (r.sapphireKey && !search::heartKeyRules().isAdr0041() && g_collectKeys && gc.keysEnabled
            && search::heartKeyActionAllowed(gc, g_collectKeys, search::GameAction(RT::KEY, 0)))
        return std::nullopt;
    for (int i = 0; i < r.relicCount; ++i) {
        if (reviewedRewardRelic(r.relics[i]) || !search::GameAction(RT::RELIC, i).isValidAction(gc)) continue;
        return search::GameAction(RT::RELIC, i);
    }
    return std::nullopt;
}

std::optional<search::GameAction> oocTreeRuleAction(const GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    if (const auto key = search::heartKeyAction(gc, g_collectKeys)) return key;
    if (const auto chest = treasureChestRuleAction(gc)) return chest;
    if (const auto relic = rewardRelicRuleAction(gc)) return relic;
    if (gc.screenState != ScreenState::REWARDS) return std::nullopt;
    const auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount > 0) return search::GameAction(RT::GOLD, 0);
    if (!gc.hasRelic(RelicId::SOZU)) {
        if (const auto potion = search::potionRewardAction(gc)) return potion;
    }
    // Nothing left (keys only count when STS_COLLECT_KEYS is on): leaving is the only sensible action.
    // STS_POTION_REWARD_DECLINE_LEAVE=1: a potion the pickup declined counts as nothing left, so
    // search cannot swap a held potion for it by discarding (a uniform-prior root, fixed-rules audit).
    const bool potionsLeft = r.potionCount > 0
        && !(search::potionRewardDeclineLeaveEnabled() && search::potionRewardDeclined(gc));
    if (r.cardRewardCount == 0 && r.relicCount == 0 && !potionsLeft
        && !(g_collectKeys && (r.emeraldKey || r.sapphireKey)))
        return search::GameAction(RT::SKIP);
    return std::nullopt;
}

bool oocTreeRuleStep(GameContext &gc) {
    const auto action = oocTreeRuleAction(gc);
    if (!action) return false;
    action->execute(gc);
    return true;
}
