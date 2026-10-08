#include "sim/search/ScumSearchAgent2.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

extern bool g_collectKeys;
using namespace sts;
using namespace sts::search;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// Construct a campfire directly: no generated run, map, fight or game seed.
static GameContext restFixture() {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 12;
    gc.curHp = 40;
    gc.maxHp = 101;
    gc.screenState = ScreenState::REST_ROOM;
    gc.curRoom = Room::REST;
    gc.keysEnabled = true;
    gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static std::default_random_engine recallEngine() {
    std::default_random_engine engine(1);
    for (int i = 0; i < 64; ++i) {
        auto probe = engine;
        if (std::uniform_int_distribution<int>(0, 2)(probe) == 2) return engine;
        (void)engine();
    }
    throw std::runtime_error("fixture could not select Recall");
}

static void matchesOrderedUniform(GameContext gc, bool enabled, bool collect,
                                  std::default_random_engine engine) {
    g_collectKeys = collect;
    if (enabled) setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
    else unsetenv("STS_OOC_SKIP_OPTIONAL_RECALL");
    auto actions = GameAction::getAllActionsInState(gc);
    if (enabled && !collect && gc.screenState == ScreenState::REST_ROOM && actions.size() > 1)
        actions.erase(std::remove_if(actions.begin(), actions.end(), [](GameAction action) {
            return action.getIdx1() == 2;
        }), actions.end());
    require(!actions.empty(), "fixture has no expected legal action");
    auto expectedEngine = engine;
    const auto expected = actions[std::uniform_int_distribution<int>(0, int(actions.size()) - 1)(expectedEngine)];
    require(expected.isValidAction(gc), "expected action is not simulator-legal");
    ScumSearchAgent2 agent;
    agent.recordActions = true;
    agent.rng = engine;
    agent.stepRandom(gc);
    require(agent.gameActionHistory.size() == 1 && agent.gameActionHistory[0] == int(expected.bits),
            "selected action differs from ordered legal uniform oracle");
    require(agent.rng == expectedEngine, "random fallback differs from one distribution invocation");
}

int main() {
    try {
        // The pre-fix executable ignores this flag and acquires Ruby here.
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
        g_collectKeys = false;
        auto gc = restFixture();
        auto original = GameAction::getAllActionsInState(gc);
        require(original.size() == 3 && original[0].getIdx1() == 0
                && original[1].getIdx1() == 1 && original[2].getIdx1() == 2,
                "fixture expected REST, SMITH, RECALL ordering");
        auto filtered = original;
        filterOptionalRecallActions(gc, filtered);
        require(filtered.size() == 2 && filtered[0].getIdx1() == 0 && filtered[1].getIdx1() == 1,
                "shared policy helper did not preserve REST/SMITH ordering");
        auto forced = std::vector<GameAction>{GameAction(2)};
        filterOptionalRecallActions(gc, forced);
        require(forced.size() == 1 && forced[0].getIdx1() == 2,
                "shared policy helper changed forced Recall");
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "0", 1);
        auto off = original;
        filterOptionalRecallActions(gc, off);
        require(off.size() == original.size() && std::equal(off.begin(), off.end(), original.begin(),
                    [](GameAction a, GameAction b) { return a.bits == b.bits; }),
                "shared policy helper changed flag-off actions");
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
        ScumSearchAgent2 agent;
        agent.recordActions = true;
        agent.rng = recallEngine();
        agent.stepOutOfCombatPolicy(gc);
        require(!gc.hasKey(Key::RUBY_KEY), "keys-off random REST fallback acquired optional Ruby Recall");
        require(agent.gameActionHistory.size() == 1 && agent.gameActionHistory[0] != 2,
                "enabled fallback did not exclude optional Recall");

        // Unset and explicit zero retain the exact legacy action and engine.
        for (const char *value : {static_cast<const char *>(nullptr), "0"}) {
            if (value) setenv("STS_OOC_SKIP_OPTIONAL_RECALL", value, 1);
            else unsetenv("STS_OOC_SKIP_OPTIONAL_RECALL");
            auto legacy = restFixture();
            auto expected = recallEngine();
            (void)std::uniform_int_distribution<int>(0, 2)(expected);
            ScumSearchAgent2 control;
            control.recordActions = true;
            control.rng = recallEngine();
            control.stepOutOfCombatPolicy(legacy);
            require(legacy.hasKey(Key::RUBY_KEY) && control.gameActionHistory == std::vector<int>{2},
                    "default-off legacy Recall action changed");
            require(control.rng == expected, "default-off legacy engine state changed");
        }

        std::default_random_engine states(73);
        for (int i = 0; i < 64; ++i) {
            auto ordinary = restFixture();
            matchesOrderedUniform(ordinary, true, false, states);
            matchesOrderedUniform(ordinary, false, false, states);
            matchesOrderedUniform(ordinary, true, true, states);
            ordinary.keysEnabled = false;
            matchesOrderedUniform(ordinary, true, false, states);
            ordinary.keysEnabled = true;
            ordinary.obtainKey(Key::RUBY_KEY);
            matchesOrderedUniform(ordinary, true, false, states);

            auto onlyRecall = restFixture();
            onlyRecall.relics.add({RelicId::COFFEE_DRIPPER, 0});
            onlyRecall.relics.add({RelicId::FUSION_HAMMER, 0});
            require(GameAction::getAllActionsInState(onlyRecall).size() == 1,
                    "only-Recall fixture must expose one legal action");
            matchesOrderedUniform(onlyRecall, true, false, states);

            auto resolved = restFixture();
            resolved.restRoomResolved = true;
            matchesOrderedUniform(resolved, true, false, states);
            auto rewards = restFixture();
            rewards.screenState = ScreenState::REWARDS;
            rewards.info.rewardsContainer.clear();
            matchesOrderedUniform(rewards, true, false, states);
            (void)states();
        }
        for (const char *invalid : {"", "2", "-1", "true", "01", " 1"}) {
            setenv("STS_OOC_SKIP_OPTIONAL_RECALL", invalid, 1);
            bool rejected = false;
            try { (void)oocSkipOptionalRecallEnabled(); }
            catch (const std::runtime_error &) { rejected = true; }
            require(rejected, "malformed optional Recall flag was accepted");
        }
        unsetenv("STS_OOC_SKIP_OPTIONAL_RECALL");
        require(!oocSkipOptionalRecallEnabled(), "unset optional Recall flag is enabled");
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "0", 1);
        require(!oocSkipOptionalRecallEnabled(), "zero optional Recall flag is enabled");
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
        require(oocSkipOptionalRecallEnabled(), "one optional Recall flag is disabled");
        unsetenv("STS_OOC_SKIP_OPTIONAL_RECALL");
        g_collectKeys = false;
        std::cout << "rest_recall_filter PASS: synthetic acquisition, default-off parity, ordered uniform, keys-on, no-key, non-rest, forced-Recall exception\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
