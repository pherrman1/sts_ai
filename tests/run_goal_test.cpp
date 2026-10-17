#include "sim/search/RunGoal.h"
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace sts::search;
static void require(bool ok, const char *what) { if (!ok) throw std::runtime_error(what); }
int main() {
    try {
        GameContext gc{};
        gc.cc = CharacterClass::IRONCLAD; gc.keysEnabled = true;
        gc.act = 3; gc.outcome = GameOutcome::PLAYER_VICTORY;
        require(!runGoalVictory(gc, true), "Act 3 is not a Heart kill");
        require(runGoalVictory(gc, false), "keys-off historical victory");
        require(runGoalVictory(gc, true, 3), "explicit Act-3 horizon");
        require(!runGoalVictory(gc, true, 4), "Act-4 horizon not cleared");
        gc.act = 4;
        require(runGoalVictory(gc, true), "Heart victory");
        gc.outcome = GameOutcome::PLAYER_LOSS;
        require(!runGoalVictory(gc, true), "Heart death");
        gc.outcome = GameOutcome::UNDECIDED;
        require(!runGoalVictory(gc, true), "unresolved run");
        gc.act = 3; gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer.sapphireKey = true;
        gc.info.rewardsContainer.addRelic(RelicId::ANCHOR);
        gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
        require(!heartKeyAction(gc, false), "keys-off must not force a key");
        auto action = heartKeyAction(gc, true);
        require(action && action->getRewardsActionType() == GameAction::RewardsActionType::KEY,
            "Sapphire before paired relic");
        action->execute(gc);
        require(gc.blueKey && gc.info.rewardsContainer.relicCount == 0, "Sapphire consumes its relic");
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer.emeraldKey = true;
        heartKeyAction(gc, true)->execute(gc);
        require(gc.greenKey, "Emerald acquired");
        gc.screenState = ScreenState::REST_ROOM;
        require(heartKeyAction(gc, true).has_value(), "Act-3 Recall forced");
        heartKeyAction(gc, true)->execute(gc);
        require(gc.redKey && !heartKeyAction(gc, true), "Ruby acquired once");
        gc.redKey = false; gc.screenState = ScreenState::REST_ROOM; gc.act = 2;
        require(!heartKeyAction(gc, true), "earlier rest remains a decision");
        gc.act = 3; gc.keysEnabled = false;
        require(!heartKeyAction(gc, true), "disabled keys");

        // Synthetic public map: the legal left route misses the burning elite.
        gc.keysEnabled = true; gc.greenKey = false; gc.screenState = ScreenState::MAP_SCREEN;
        gc.curMapNodeX = 0; gc.curMapNodeY = 0; gc.map = std::make_shared<Map>();
        auto &start = gc.map->getNode(0, 0);
        start.edgeCount = 2; start.edges[0] = 0; start.edges[1] = 1;
        auto &left = gc.map->getNode(0, 1); left.room = Room::REST;
        left.edgeCount = 1; left.edges[0] = 0;
        auto &right = gc.map->getNode(1, 1); right.room = Room::REST;
        right.edgeCount = 1; right.edges[0] = 2;
        gc.map->getNode(2, 2).room = Room::ELITE;
        gc.map->burningEliteX = 2; gc.map->burningEliteY = 2;
        action = heartKeyAction(gc, true);
        require(action && action->getIdx1() == 1, "retain route to burning elite");
        gc.greenKey = true;
        require(!heartKeyAction(gc, true), "owned Emerald restores path choice");
        gc.greenKey = false; right.edges[0] = 0;
        require(!heartKeyAction(gc, true), "unreachable Emerald has no fabricated action");
        gc.act = 2; right.edges[0] = 2;
        require(!heartKeyAction(gc, true), "early-act path choice preserved");

        // Opt-in variants (STS_KEY_*); the defaults above are the ADR-0041 rules.
        auto &rules = heartKeyRules();
        require(rules.isDefault(), "ADR-0041 rules by default");
        gc.act = 3; gc.greenKey = false; right.edges[0] = 2; left.edges[0] = 2;
        require(heartKeyAction(gc, true)->getIdx1() == 0, "first reaching edge by default");
        rules.emerald = HeartKeyRules::Emerald::MASK;
        require(!heartKeyAction(gc, true), "mask leaves a choice between reaching edges");
        left.edges[0] = 0;
        action = heartKeyAction(gc, true);
        require(action && action->getIdx1() == 1, "mask forces the only reaching edge");
        require(!heartKeyActionAllowed(gc, true, GameAction(0)) && heartKeyActionAllowed(gc, true, GameAction(1)),
            "mask forbids the edge that misses the burning elite");
        require(heartKeyActionAllowed(gc, false, GameAction(0)), "keys off: no mask");
        rules.emerald = HeartKeyRules::Emerald::FIRST;
        require(heartKeyActionAllowed(gc, true, GameAction(0)), "no mask by default");

        gc.screenState = ScreenState::REWARDS; gc.info.rewardsContainer = {};
        gc.info.rewardsContainer.sapphireKey = true;
        gc.info.rewardsContainer.addRelic(RelicId::ANCHOR);
        gc.blueKey = false; gc.act = 1;
        rules.sapphire = HeartKeyRules::Sapphire::ACT3;
        require(!heartKeyAction(gc, true), "act3: Act-1 chest keeps its relic");
        require(!heartKeyActionAllowed(gc, true, GameAction(GameAction::RewardsActionType::KEY, 0))
            && heartKeyActionAllowed(gc, true, GameAction(GameAction::RewardsActionType::RELIC, 0)),
            "act3: Sapphire forbidden before Act 3");
        gc.act = 3; gc.curMapNodeY = 3;
        require(heartKeyAction(gc, true).has_value(), "act3: first Act-3 chest takes Sapphire");
        rules.sapphire = HeartKeyRules::Sapphire::POLICY;
        require(!heartKeyAction(gc, true), "policy: early Act-3 chest is a decision");
        require(heartKeyActionAllowed(gc, true, GameAction(GameAction::RewardsActionType::KEY, 0)),
            "policy: Sapphire allowed");
        gc.curMapNodeY = 8;
        require(heartKeyAction(gc, true).has_value(), "policy: Act-3 treasure row backstop");
        gc.info.rewardsContainer.sapphireKey = false; gc.info.rewardsContainer.emeraldKey = true; gc.act = 1;
        require(heartKeyAction(gc, true).has_value(), "Emerald is always taken");
        rules.sapphire = HeartKeyRules::Sapphire::FIRST;

        gc.screenState = ScreenState::REST_ROOM; gc.redKey = false; gc.act = 3; gc.curMapNodeY = 5;
        gc.maxHp = 80; gc.curHp = 30;
        rules.ruby = HeartKeyRules::Ruby::HP;
        require(!heartKeyAction(gc, true), "hp: low-HP campfire defers Recall");
        gc.curHp = 40;
        require(heartKeyAction(gc, true).has_value(), "hp: Recall at the threshold");
        gc.curHp = 10; gc.curMapNodeY = 14;
        require(heartKeyAction(gc, true).has_value(), "hp: pre-boss campfire backstop");
        rules.ruby = HeartKeyRules::Ruby::POLICY; gc.curHp = 80; gc.curMapNodeY = 5;
        require(!heartKeyAction(gc, true), "policy: Recall is a decision before the last row");
        gc.curMapNodeY = 14;
        require(heartKeyAction(gc, true).has_value(), "policy: pre-boss campfire backstop");
        rules = HeartKeyRules{};
        std::cout << "PASS Heart goal, key pairing, Recall and public burning-elite route, key variants\n";
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
