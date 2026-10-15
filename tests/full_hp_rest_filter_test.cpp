#include "sim/search/ScumSearchAgent2.h"

#include <array>
#include <cstdlib>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

extern bool g_collectKeys;
using namespace sts;
using namespace sts::search;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// Direct public campfire fixture: no generated run, map, fight or game seed.
static GameContext campfire(int hp = 40, int maximum = 40) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 12;
    gc.curHp = hp;
    gc.maxHp = maximum;
    gc.screenState = ScreenState::REST_ROOM;
    gc.curRoom = Room::REST;
    gc.keysEnabled = false;
    gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static std::vector<int> indices(const std::vector<GameAction> &actions) {
    std::vector<int> result;
    for (const auto action : actions) result.push_back(action.getIdx1());
    return result;
}

static void expectFiltered(const GameContext &gc, const std::vector<int> &expected) {
    auto actions = GameAction::getAllActionsInState(gc);
    filterFullHpRestActions(gc, actions);
    require(indices(actions) == expected, "full-health filter changed unexpected actions/order");
    for (const auto action : actions)
        require(action.isValidAction(gc), "full-health filter retained an illegal action");
}

static void unchanged(const GameContext &gc) {
    require(!oocFullHpRestExclusionApplies(gc), "out-of-scope full-health predicate applied");
    const auto before = GameAction::getAllActionsInState(gc);
    auto after = before;
    filterFullHpRestActions(gc, after);
    require(indices(after) == indices(before), "out-of-scope actions changed");
}

static void randomMatches(GameContext gc, const char *flag, const std::vector<int> &expected,
                          std::default_random_engine engine) {
    if (flag) setenv("STS_OOC_SKIP_FULL_HP_REST", flag, 1);
    else unsetenv("STS_OOC_SKIP_FULL_HP_REST");
    auto expectedEngine = engine;
    const int chosen = expected[std::uniform_int_distribution<int>(0, int(expected.size()) - 1)(expectedEngine)];
    require(GameAction(chosen).isValidAction(gc), "uniform oracle expected an illegal action");
    ScumSearchAgent2 agent;
    agent.recordActions = true;
    agent.rng = engine;
    agent.stepRandom(gc);
    require(agent.gameActionHistory == std::vector<int>{chosen}, "fallback action differs from ordered uniform oracle");
    require(agent.rng == expectedEngine, "fallback must use exactly one distribution invocation");
}

int main() {
    try {
        g_collectKeys = false;
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "0", 1);
        setenv("STS_OOC_SKIP_FULL_HP_REST", "1", 1);
        const auto ordinary = campfire();
        require(oocFullHpRestExclusionApplies(ordinary), "legal full-health REST/SMITH root was not recognized");
        expectFiltered(ordinary, {1});

        // Shared V4/fallback helper keeps all special actions in original order.
        auto special = campfire();
        special.keysEnabled = true;
        special.relics.add({RelicId::GIRYA, 1});
        special.relics.add({RelicId::PEACE_PIPE, 0});
        special.relics.add({RelicId::SHOVEL, 0});
        expectFiltered(special, {1, 2, 3, 4, 5});
        auto combined = GameAction::getAllActionsInState(special);
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
        filterOptionalRecallActions(special, combined);
        filterFullHpRestActions(special, combined);
        require(indices(combined) == std::vector<int>({1, 3, 4, 5}), "Recall/full-health filter composition changed ordering");
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "0", 1);

        // A supplied candidate subset must itself contain both legal alternatives.
        for (const auto &subset : std::vector<std::vector<GameAction>>{{}, {GameAction(0)},
                {GameAction(1)}, {GameAction(2)}, {GameAction(0), GameAction(3)}}) {
            auto result = subset;
            filterFullHpRestActions(special, result);
            require(indices(result) == indices(subset), "filter changed a forced/subset boundary");
        }

        unchanged(campfire(39, 40));
        unchanged(campfire(0, 0));
        unchanged(campfire(41, 40));
        auto dream = campfire(); dream.relics.add({RelicId::DREAM_CATCHER, 0}); unchanged(dream);
        auto hammer = campfire(); hammer.relics.add({RelicId::FUSION_HAMMER, 0}); unchanged(hammer);
        auto coffee = campfire(); coffee.relics.add({RelicId::COFFEE_DRIPPER, 0}); unchanged(coffee);
        auto upgraded = campfire(); upgraded.deck.upgrade(0); unchanged(upgraded);
        auto resolved = campfire(); resolved.restRoomResolved = true; unchanged(resolved);
        auto other = campfire(); other.screenState = ScreenState::REWARDS;
        other.info.rewardsContainer.clear(); unchanged(other);
        auto onlyRecall = hammer; onlyRecall.keysEnabled = true;
        onlyRecall.relics.add({RelicId::COFFEE_DRIPPER, 0}); unchanged(onlyRecall);

        // Tea Set and Feather already trigger on entering the site. Pillow's
        // extra healing is clamped. None adds a REST-choice benefit at full HP.
        for (const auto relic : {RelicId::ANCIENT_TEA_SET, RelicId::ETERNAL_FEATHER,
                                RelicId::REGAL_PILLOW, RelicId::MARK_OF_THE_BLOOM}) {
            auto gc = campfire(); gc.relics.add({relic, 1});
            const auto beforeRng = std::array{gc.aiRng, gc.cardRandomRng, gc.cardRng, gc.eventRng,
                gc.mathUtilRng, gc.merchantRng, gc.miscRng, gc.monsterHpRng, gc.monsterRng,
                gc.neowRng, gc.potionRng, gc.relicRng, gc.shuffleRng, gc.treasureRng};
            expectFiltered(gc, {1});
            require(gc.curHp == 40 && gc.maxHp == 40 && gc.deck.size() == 1
                && !gc.deck.cards[0].isUpgraded() && gc.relics.getRelicValue(relic) == 1,
                "eligibility filter mutated public state");
            require(beforeRng == std::array{gc.aiRng, gc.cardRandomRng, gc.cardRng, gc.eventRng,
                gc.mathUtilRng, gc.merchantRng, gc.miscRng, gc.monsterHpRng, gc.monsterRng,
                gc.neowRng, gc.potionRng, gc.relicRng, gc.shuffleRng, gc.treasureRng},
                "eligibility filter mutated game RNG");
        }

        // Exercise actual policy routing: a full maxHP below15 must not take
        // the deterministic low-HP REST branch before the shared filter runs.
        for (const char *flag : {static_cast<const char *>(nullptr), "0", "1"}) {
            if (flag) setenv("STS_OOC_SKIP_FULL_HP_REST", flag, 1);
            else unsetenv("STS_OOC_SKIP_FULL_HP_REST");
            auto gc = campfire(10, 10);
            ScumSearchAgent2 agent;
            agent.recordActions = true;
            agent.rng.seed(17);
            auto expectedRng = agent.rng;
            const bool enabled = flag && std::string(flag) == "1";
            if (enabled) (void)std::uniform_int_distribution<int>(0, 0)(expectedRng);
            agent.stepOutOfCombatPolicy(gc);
            require(agent.gameActionHistory == std::vector<int>{enabled ? 1 : 0}, "low-max-HP policy bypassed eligibility");
            require(agent.rng == expectedRng, "low-max-HP policy RNG contract changed");
            require(gc.screenState == (enabled ? ScreenState::CARD_SELECT : ScreenState::MAP_SCREEN),
                    "low-max-HP action did not execute expected legal transition");
        }
        setenv("STS_OOC_SKIP_FULL_HP_REST", "1", 1);
        auto damaged = campfire(9, 10);
        ScumSearchAgent2 low;
        low.recordActions = true;
        const auto lowRng = low.rng;
        low.stepOutOfCombatPolicy(damaged);
        require(low.gameActionHistory == std::vector<int>{0} && damaged.curHp == 10 && low.rng == lowRng,
                "ordinary damaged low-HP REST behavior changed");

        std::default_random_engine states(73);
        for (int i = 0; i < 64; ++i) {
            randomMatches(campfire(), nullptr, {0, 1}, states);
            randomMatches(campfire(), "0", {0, 1}, states);
            randomMatches(campfire(), "1", {1}, states);
            randomMatches(campfire(39, 40), "1", {0, 1}, states);
            randomMatches(hammer, "1", {0}, states);
            (void)states();
        }
        auto keyed = campfire(); keyed.keysEnabled = true;
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "1", 1);
        randomMatches(keyed, "0", {0, 1}, states);
        randomMatches(keyed, "1", {1}, states);
        setenv("STS_OOC_SKIP_OPTIONAL_RECALL", "0", 1);
        for (const char *invalid : {"", "2", "-1", "true", "01", " 1"}) {
            setenv("STS_OOC_SKIP_FULL_HP_REST", invalid, 1);
            bool rejected = false;
            try { (void)oocSkipFullHpRestEnabled(); }
            catch (const std::runtime_error &) { rejected = true; }
            require(rejected, "malformed full-health REST flag was accepted");
        }
        unsetenv("STS_OOC_SKIP_FULL_HP_REST");
        require(!oocSkipFullHpRestEnabled(), "unset full-health REST flag is enabled");
        setenv("STS_OOC_SKIP_FULL_HP_REST", "0", 1);
        require(!oocSkipFullHpRestEnabled(), "zero full-health REST flag is enabled");
        setenv("STS_OOC_SKIP_FULL_HP_REST", "1", 1);
        require(oocSkipFullHpRestEnabled(), "one full-health REST flag is disabled");
        unsetenv("STS_OOC_SKIP_FULL_HP_REST");
        std::cout << "full_hp_rest_filter PASS: legality, ordered special options, Recall composition, default-off RNG, damaged/Dream/forced boundaries, entry relics, low-max-HP policy\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
