// Heart-key backstops of the stage 1 run driver (RunConfig::forceKeys, azbench::keyBackstopActions): on synthetic
// states, the ADR-0063 rules restrict the legal out-of-combat actions. Sapphire: the Act-3 treasure-row chest
// (row >= 8) offers only the key; Ruby: the last Act-3 campfire (row 14) offers only Recall; Emerald: on the Act-3 map
// only edges that still reach the burning elite, a single such edge is forced. Elsewhere nothing changes. The driver
// refuses forceKeys under non-default STS_KEY_* rules. Key holes (STS_AZ_KEY_HOLES, default closed): the act-3 Secret
// Portal offers only its leave option while a key is missing, and Smoke Bomb is not enumerated at the act-3 burning elite
// without the Emerald Key.
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <vector>

#include "az_run_driver.h"
#include "sim/search/RunGoal.h"
#include "sim/search/SilverSearcher.h"
#include "combat/BattleContext.h"

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
    if (std::getenv("STS_KEY_SAPPHIRE") || std::getenv("STS_KEY_RUBY") || std::getenv("STS_KEY_EMERALD")) {
        std::printf("skipped: STS_KEY_* set\n");
        return 0;
    }
    using RT = GameAction::RewardsActionType;
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.keysEnabled = true;
    gc.outcome = GameOutcome::UNDECIDED;
    gc.maxHp = 80;
    gc.curHp = 40;

    // Sapphire: a chest's key and its paired relic.
    gc.act = 3; gc.curMapNodeY = 8; gc.screenState = ScreenState::REWARDS;
    gc.info.rewardsContainer.sapphireKey = true;
    gc.info.rewardsContainer.addRelic(RelicId::ANCHOR);
    auto v = GameAction::getAllActionsInState(gc);
    require(v.size() >= 2 && has(v, GameAction(RT::KEY, 0)), "chest offers key and relic");
    require(azbench::keyBackstopActions(gc, v) == 0 && v.size() == 1 && v[0].bits == GameAction(RT::KEY, 0).bits,
            "Act-3 treasure row: only the Sapphire");
    gc.curMapNodeY = 3;
    v = GameAction::getAllActionsInState(gc);
    auto n = v.size();
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == n, "early Act-3 chest: a decision");
    gc.act = 2; gc.curMapNodeY = 8;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == n, "Act-2 chest: a decision");
    gc.info.rewardsContainer = {};

    // Ruby: the last campfire before the Act-3 boss.
    gc.screenState = ScreenState::REST_ROOM; gc.act = 3; gc.curMapNodeY = 14; gc.redKey = false;
    v = GameAction::getAllActionsInState(gc);
    require(v.size() >= 2 && has(v, GameAction(2)), "campfire offers Recall and more");
    require(azbench::keyBackstopActions(gc, v) == 1 && v.size() == 1 && v[0].bits == GameAction(2).bits,
            "pre-boss Act-3 campfire: only Recall");
    gc.curMapNodeY = 5;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == n, "earlier Act-3 campfire: a decision");
    gc.curMapNodeY = 14; gc.act = 2;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == n, "Act-2 campfire: a decision");

    // Emerald: synthetic Act-3 map, start (0,0) with edges to (0,1), (1,1), (2,1); the burning elite at (1,2).
    gc.act = 3; gc.greenKey = false; gc.screenState = ScreenState::MAP_SCREEN;
    gc.curMapNodeX = 0; gc.curMapNodeY = 0; gc.map = std::make_shared<Map>();
    auto &start = gc.map->getNode(0, 0);
    start.edgeCount = 3; start.edges[0] = 0; start.edges[1] = 1; start.edges[2] = 2;
    for (int x = 0; x < 3; ++x) { auto &m = gc.map->getNode(x, 1); m.room = Room::MONSTER; m.edgeCount = 1; }
    gc.map->getNode(0, 1).edges[0] = 1;   // reaches the elite
    gc.map->getNode(1, 1).edges[0] = 1;   // reaches the elite
    gc.map->getNode(2, 1).edges[0] = 2;   // misses it
    gc.map->getNode(1, 2).room = Room::ELITE;
    gc.map->getNode(2, 2).room = Room::MONSTER;
    gc.map->burningEliteX = 1; gc.map->burningEliteY = 2;
    v = GameAction::getAllActionsInState(gc);
    require(v.size() == 3, "three map edges");
    require(azbench::keyBackstopActions(gc, v) == 3 && v.size() == 2 && v[0].getIdx1() == 0 && v[1].getIdx1() == 1,
            "route narrowed to the two edges reaching the burning elite");
    gc.map->getNode(0, 1).edges[0] = 0;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == 2 && v.size() == 1 && v[0].getIdx1() == 1,
            "single reaching edge forced");
    gc.greenKey = true;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 3, "Emerald owned: free route");
    gc.greenKey = false; gc.act = 2;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 3, "Act-2 map: free route");
    gc.act = 3; gc.keysEnabled = false;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 3, "keys disabled: free route");

    // Secret Portal (act 3): accept (option 0) jumps to the boss; with a key missing only the leave option stays.
    gc.screenState = ScreenState::EVENT_SCREEN; gc.curEvent = Event::SECRET_PORTAL; gc.keysEnabled = true;
    gc.act = 3; gc.blueKey = true; gc.redKey = false; gc.greenKey = true;
    v = GameAction::getAllActionsInState(gc);
    require(v.size() == 2 && v[0].getIdx1() == 0 && v[1].getIdx1() == 1, "portal offers accept and leave");
    if (azbench::keyHolesClosed()) {
        require(azbench::keyBackstopActions(gc, v) == 3 && v.size() == 1 && v[0].getIdx1() == 1,
                "portal with Ruby missing: only leave");
    } else {
        require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 2, "STS_AZ_KEY_HOLES=0: portal open");
    }
    gc.redKey = true;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 2, "portal with all keys: a decision");
    gc.redKey = false; gc.keysEnabled = false;
    v = GameAction::getAllActionsInState(gc);
    require(azbench::keyBackstopActions(gc, v) == -1 && v.size() == 2, "portal, keys disabled: a decision");
    gc.keysEnabled = true; gc.curEvent = Event::INVALID;

    // Smoke Bomb at the act-3 burning elite (1,2) without the Emerald Key: the fight's context drops the escape.
    gc.screenState = ScreenState::MAP_SCREEN; gc.greenKey = false; gc.curMapNodeX = 1; gc.curMapNodeY = 2;
    gc.curRoom = Room::ELITE;
    const bool holes = azbench::keyHolesClosed();
    require(azbench::keyEscapeForfeitsEmerald(gc, true) == holes, "burning act-3 elite, no Emerald: escape forfeits");
    require(!azbench::keyEscapeForfeitsEmerald(gc, false), "forceKeys off: escape allowed");
    gc.greenKey = true;
    require(!azbench::keyEscapeForfeitsEmerald(gc, true), "Emerald owned: escape allowed");
    gc.greenKey = false; gc.curMapNodeX = 2; gc.curRoom = Room::MONSTER;
    require(!azbench::keyEscapeForfeitsEmerald(gc, true), "other room: escape allowed");
    gc.curMapNodeX = 1; gc.curRoom = Room::ELITE; gc.act = 2;
    require(!azbench::keyEscapeForfeitsEmerald(gc, true), "act-2 burning elite: a later map has one again");
    gc.act = 3;
    {   // the enumeration rule itself: a held Smoke Bomb in an elite fight
        BattleContext bc{};
        bc.encounter = MonsterEncounter::GREMLIN_LEADER;
        bc.potionCount = 1; bc.potionCapacity = 3; bc.potions[0] = Potion::SMOKE_BOMB;
        bc.inputState = InputState::PLAYER_NORMAL;
        auto smoke = [](const std::vector<search::Action> &acts) {
            for (const auto &a : acts) if (a.getActionType() == search::ActionType::POTION && a.getSourceIdx() == 0) return true;
            return false;
        };
        search::SilverSearchContext open{}, closed{};
        closed.escapeForfeitsRun = true;
        search::SilverSearcher so(bc, open), sc(bc, closed);
        require(smoke(so.enumerateActions(bc)), "elite fight: Smoke Bomb offered");
        require(!smoke(sc.enumerateActions(bc)), "escapeForfeitsRun: Smoke Bomb not offered");
    }

    // The driver needs the ADR-0063 default rules.
    azbench::RunConfig cfg;
    cfg.workers = 1;
    cfg.gamesPerWorker = 1;
    cfg.forceKeys = true;
    { azbench::RunDriver ok(cfg); require(ok.forceKeys(), "forceKeys on at construction"); ok.setForceKeys(false); require(!ok.forceKeys(), "setForceKeys(false)"); }
    auto &rules = search::heartKeyRules();
    const auto saved = rules;
    rules = search::HeartKeyRules{};   // ADR-0041 (STS_KEY_*=first)
    bool threw = false;
    try { azbench::RunDriver bad(cfg); } catch (const std::invalid_argument &) { threw = true; }
    require(threw, "forceKeys refused under non-default key rules");
    cfg.forceKeys = false;
    { azbench::RunDriver off(cfg); require(!off.forceKeys(), "forceKeys off: no rule check"); }
    rules = saved;

    std::printf("force-keys test: %s\n", fails ? "FAIL" : "ok");
    return fails ? 1 : 0;
}
