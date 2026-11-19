// Forced reward choices of the stage 1 run driver (RunConfig::forceRewards, azbench::forcedRewardActions /
// forcedRewardBeforeLeave; Philipp 2026-11-19): on synthetic states, a chest is opened unless we hold Cursed Key; a
// reward relic outside the reviewed list is the only legal action (Ceramic Fish / eggs / Potion Belt first); Whetstone
// and War Paint wait while the card reward is open and are taken on leaving; the relic paired with a Sapphire Key, the
// reviewed relics and the boss relic screen stay decisions.
#include <cstdio>
#include <vector>

#include "az_run_driver.h"

using namespace sts;
using search::GameAction;

namespace {
    int fails = 0;
    void require(bool ok, const char *what) {
        if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); ++fails; }
    }
    bool has(const std::vector<GameAction> &v, const GameAction &a) {
        for (const auto &x : v) if (x.bits == a.bits) return true;
        return false;
    }
}

int main() {
    using RT = GameAction::RewardsActionType;
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.outcome = GameOutcome::UNDECIDED;
    gc.maxHp = 80;
    gc.curHp = 40;
    gc.act = 1;

    // Chest: opened unless Cursed Key.
    gc.screenState = ScreenState::TREASURE_ROOM;
    auto v = GameAction::getAllActionsInState(gc);
    require(azbench::forcedRewardActions(gc, v) == 0 && v.size() == 1 && v[0].bits == GameAction(0).bits,
            "chest: only open");
    gc.relics.add(RelicInstance{RelicId::CURSED_KEY, 0});
    v = GameAction::getAllActionsInState(gc);
    auto n = v.size();
    require(azbench::forcedRewardActions(gc, v) == -1 && v.size() == n, "chest with Cursed Key: a decision");
    gc.relics = {};

    CardReward cards;
    cards.push_back(Card(CardId::POMMEL_STRIKE));
    cards.push_back(Card(CardId::SHRUG_IT_OFF));
    auto rewards = [&](std::vector<RelicId> relics, bool card) {
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer = {};
        gc.info.rewardsContainer.addGold(25);
        for (auto r : relics) gc.info.rewardsContainer.addRelic(r);
        if (card) gc.info.rewardsContainer.addCardReward(cards);
        return GameAction::getAllActionsInState(gc);
    };

    // An ordinary relic: taken at once (before the card decision; the order does not change its outcome).
    v = rewards({RelicId::ANCHOR}, true);
    require(azbench::forcedRewardActions(gc, v) == 1 && v.size() == 1 && v[0].bits == GameAction(RT::RELIC, 0).bits,
            "elite relic: only take it");
    // Ceramic Fish before the other relic (and the card).
    v = rewards({RelicId::ANCHOR, RelicId::CERAMIC_FISH}, true);
    require(azbench::forcedRewardActions(gc, v) == 1 && v.size() == 1 && v[0].bits == GameAction(RT::RELIC, 1).bits,
            "Ceramic Fish first");
    v = rewards({RelicId::ANCHOR, RelicId::MOLTEN_EGG}, true);
    require(azbench::forcedRewardActions(gc, v) == 1 && v[0].bits == GameAction(RT::RELIC, 1).bits, "Molten Egg first");
    // Reviewed relic: a decision.
    v = rewards({RelicId::DEAD_BRANCH}, true);
    n = v.size();
    require(azbench::forcedRewardActions(gc, v) == -1 && v.size() == n && has(v, GameAction(RT::RELIC, 0)),
            "reviewed relic: a decision");
    require(!azbench::forcedRewardBeforeLeave(gc), "reviewed relic: not taken on leaving");
    // Whetstone: held back while the card reward is open, taken on leaving; forced once the card is decided.
    v = rewards({RelicId::WHETSTONE}, true);
    n = v.size();
    require(azbench::forcedRewardActions(gc, v) == 2 && v.size() == n - 1 && !has(v, GameAction(RT::RELIC, 0)) &&
            has(v, GameAction(RT::SKIP)) && has(v, GameAction(RT::CARD, 0, 0)), "Whetstone waits for the card");
    const auto leave = azbench::forcedRewardBeforeLeave(gc);
    require(leave && leave->bits == GameAction(RT::RELIC, 0).bits, "Whetstone taken on leaving");
    v = rewards({RelicId::WAR_PAINT, RelicId::ANCHOR}, true);
    require(azbench::forcedRewardActions(gc, v) == 1 && v.size() == 1 && v[0].bits == GameAction(RT::RELIC, 1).bits,
            "Anchor at once, War Paint after the card");
    v = rewards({RelicId::WHETSTONE}, false);
    require(azbench::forcedRewardActions(gc, v) == 1 && v.size() == 1 && v[0].bits == GameAction(RT::RELIC, 0).bits,
            "Whetstone without a card reward: only take it");
    // Sapphire Key and its paired relic: a decision (taking the relic would remove the key).
    v = rewards({RelicId::ANCHOR}, false);
    gc.info.rewardsContainer.sapphireKey = true;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::forcedRewardActions(gc, v) == -1 && v.size() == n, "Sapphire-paired relic: a decision");
    require(!azbench::forcedRewardBeforeLeave(gc), "Sapphire-paired relic: not taken on leaving");
    // No relic: nothing changes.
    v = rewards({}, true);
    n = v.size();
    require(azbench::forcedRewardActions(gc, v) == -1 && v.size() == n, "no relic: unchanged");
    // Boss relics stay learned.
    gc.info.rewardsContainer = {};
    gc.screenState = ScreenState::BOSS_RELIC_REWARDS;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::forcedRewardActions(gc, v) == -1 && v.size() == n, "boss relics: a decision");

    if (fails) { std::fprintf(stderr, "%d failure(s)\n", fails); return 1; }
    std::printf("az_force_rewards_test: ok\n");
    return 0;
}
