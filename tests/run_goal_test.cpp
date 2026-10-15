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
        std::cout << "PASS Heart goal, key pairing, Recall and public burning-elite route\n";
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
