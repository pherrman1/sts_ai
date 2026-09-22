#include "ooc_checkpoint_policy.h"

#include "sim/search/GameAction.h"
#include "ooc_v4_encoding.h"
#include "../ooc_strategic_tok_net.h"

#include <cmath>
#include <stdexcept>

namespace one_combat {

bool isForcedOrdinaryRelic(sts::RelicId relic) {
    using R = sts::RelicId;
    switch (relic) {
        case R::STRANGE_SPOON:
        case R::BOTTLED_FLAME:
        case R::BOTTLED_LIGHTNING:
        case R::BOTTLED_TORNADO:
        case R::UNCEASING_TOP:
        case R::INVALID:
            return false;
        default:
            return true;
    }
}

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
    if (rewards.potionCount > 0 && gc.potionCount < gc.potionCapacity) {
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

bool collectForcedRewardGold(sts::GameContext &gc) {
    if (gc.screenState != sts::ScreenState::REWARDS) return false;
    using RT = sts::search::GameAction::RewardsActionType;
    bool collected = false;
    while (gc.info.rewardsContainer.goldRewardCount > 0) {
        sts::search::GameAction(RT::GOLD, 0).execute(gc);
        collected = true;
    }
    return collected;
}

bool collectForcedOrdinaryRewards(sts::GameContext &gc) {
    bool collected = collectForcedRewardGold(gc);
    if (gc.screenState != sts::ScreenState::REWARDS) return collected;
    using RT = sts::search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (gc.screenState == sts::ScreenState::REWARDS && !r.sapphireKey) {
        int safe = -1;
        for (int i = 0; i < r.relicCount; ++i) {
            if (isForcedOrdinaryRelic(r.relics[i])) { safe = i; break; }
        }
        if (safe < 0) break;
        sts::search::GameAction(RT::RELIC, safe).execute(gc);
        collected = true;
    }
    if (gc.screenState == sts::ScreenState::REWARDS && r.potionCount == 1
        && gc.potionCount < gc.potionCapacity && !gc.hasRelic(sts::RelicId::SOZU)) {
        sts::search::GameAction(RT::POTION, 0).execute(gc);
        collected = true;
    }
    return collected;
}

bool takeQualifiedV4CardReward(sts::GameContext &gc, const PathHistory &path,
                               const OocStrategicTokNet &model, double margin) {
    if (!model.ok || gc.screenState != sts::ScreenState::REWARDS
        || gc.info.rewardsContainer.cardRewardCount == 0) return false;
    const auto actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    const TokState tokens = buildTokStatePure(gc, path);
    const auto prepared = model.prepareState(tokens.glob, tokens.nDk, tokens.dk,
        tokens.nRl, tokens.rl, tokens.nPt, tokens.pt);
    double best = -1e100, second = -1e100;
    int selected = -1;
    for (int i = 0; i < static_cast<int>(actions.size()); ++i) {
        int type, c1, c2, c3, cand1, cand2, cand3;
        strategicCands(gc, actions[i], type, c1, c2, c3, cand1, cand2, cand3);
        const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
        int entityType, entityId; float price;
        tokEntity(gc, actions[i], entityType, entityId, price);
        const float entity[4] = {float(entityType == 0), float(entityType == 1),
            float(entityType == 2), float(entityType == 3)};
        const double value = model.predictActionValue(prepared, actions[i].bits, cats,
            type, static_cast<int>(gc.screenState), entity, entityId, price);
        if (!std::isfinite(value)) throw std::runtime_error("nonfinite qualified card Q");
        if (value > best) { second = best; best = value; selected = i; }
        else if (value > second) second = value;
    }
    if (selected < 0 || best - second < margin) return false;
    actions[selected].execute(gc);
    return true;
}

} // namespace one_combat
