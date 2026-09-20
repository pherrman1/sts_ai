//
// Created by gamerpuppy on 7/8/2021.
//

#include <iostream>
#include <chrono>
#include <cstdint>
#include <thread>
#include <memory>
#include <mutex>
#include <set>
#include <algorithm>
#include <cstdlib>
#include <csignal>
#include <fstream>
#include <initializer_list>
#include <sstream>
#include <sys/wait.h>
#include <unistd.h>

#include "data_structure/fixed_list.h"
#include "constants/Cards.h"
#include "constants/Events.h"
#include "constants/CardPools.h"
#include "constants/Potions.h"
#include "game/Game.h"
#include "game/Map.h"
#include "game/Neow.h"
#include "game/SaveFile.h"
#include "combat/BattleContext.h"
#include "sim/ConsoleSimulator.h"
#include "sim/PrintHelpers.h"
#include "sim/RandomAgent.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SimpleAgent.h"

#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/SimHealth.h"
#include "sim/search/TrainingIntegrity.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/OocSemanticAction.h"
#include "combat/BattleContextBinary.h"
#include "one_combat/combat_transition.h"
#include "ooc_test_state.h"
#include "constants/MonsterMoves.h"
#include "test_belief.h"

int runOocRewardContinuationTests();
int runOocSemanticTests();
int runOocSemanticPipelineTests();
int runOocSemanticTransactionsTests();

using namespace sts;

int testIroncladCombatCardCoverage() {
    const GameContext game(CharacterClass::IRONCLAD, 0xC0DEu, 0);
    const int expected = TrulyRandomCardPool::getPoolSizeForClass(CharacterClass::IRONCLAD);
    int covered = 0;
    for (int i = 0; i < expected; ++i) {
        const auto id = TrulyRandomCardPool::getPoolForClass(CharacterClass::IRONCLAD)[i];
        BattleContext battle;
        battle.init(game, MonsterEncounter::CULTIST);
        battle.actionQueue.clear();
        battle.cards.cardsInHand = 0;
        battle.player.energy = 99;
        battle.curCardQueueItem.card = CardInstance(id);
        battle.curCardQueueItem.card.uniqueId = 0;
        battle.curCardQueueItem.target = 0;
        battle.curCardQueueItem.energyOnUse = 3;
        const int before = battle.actionQueue.size;
        const bool beforeBarricade = battle.player.hasStatus<PS::BARRICADE>();
        switch (id == CardId::INVALID ? CardType::INVALID : getCardType(id)) {
        case CardType::ATTACK: battle.useAttackCard(); break;
        case CardType::SKILL: battle.useSkillCard(); break;
        case CardType::POWER: battle.usePowerCard(); break;
        default: break;
        }
        if (battle.actionQueue.size > before
            || beforeBarricade != battle.player.hasStatus<PS::BARRICADE>()) {
            ++covered;
        } else {
            std::cerr << "uncovered Ironclad combat card: " << getCardEnumName(id) << '\n';
        }
    }
    std::cout << "ironclad combat card dispatcher coverage: " << covered << '/' << expected << '\n';
    return covered == expected ? 0 : 1;
}

void printSizes() {
    std::cout << "sizeof Map:" << sizeof(Map) << '\n';
    std::cout << "sizeof Player: " << sizeof(Player) << '\n';
    std::cout << "sizeof Monster: " << sizeof(Monster) << '\n';
    std::cout << "sizeof MonsterGroup : " << sizeof(MonsterGroup) << '\n';
    std::cout << "sizeof CardInstance: " << sizeof(CardInstance) << '\n';
    std::cout << "sizeof CardManager : " << sizeof(CardManager) << '\n';
    std::cout << "sizeof ActionFunction : " << sizeof(ActionFunction) << '\n';
    std::cout << "sizeof ActionQueue<40> : " << sizeof(ActionQueue<40>) << '\n';
    std::cout << "sizeof BattleContext: " << sizeof(BattleContext) << '\n';

    std::cout << "sizeof GameContext: " << sizeof(GameContext) << '\n';
    std::cout << "sizeof Deck: " << sizeof(Deck) << '\n';
    std::cout << "sizeof Card: " << sizeof(Card) << '\n';
    std::cout << "sizeof SelectScreenCard: " << sizeof(SelectScreenCard) << '\n';
}

void playFromSaveFile(const std::string &fname, const std::string &actionFile) {
    CharacterClass cc;
    switch (tolower(fname[0])) {
        case 'i':
            cc = sts::CharacterClass::IRONCLAD;
        default:
            cc = sts::CharacterClass::IRONCLAD;
    }

    SaveFile saveFile = SaveFile::loadFromPath(fname, cc);

    ConsoleSimulator sim;
    sim.setupGameFromSaveFile(saveFile);
    SimulatorContext simContext;
    simContext.quitOnTestFailed = false;



    std::ifstream actionListInputStream(actionFile);

    sim.play(actionListInputStream, std::cout, simContext);
    actionListInputStream.close();

//    simContext.printFirstLine = true;
    simContext.quitCommandGiven = false;
    sim.play(std::cin, std::cout, simContext);
}

void replayActionFile(const GameContext &startState, const std::string &fname) {
    std::ifstream ifs(fname);
    GameContext gc(startState);
    BattleContext bc;


    bool inBattle = false;

    int lineNum = 0;
    std::uint32_t actionBits;
    while (true) {
        if (inBattle) {
            if (bc.outcome != sts::Outcome::UNDECIDED) {
                bc.exitBattle(gc);
                inBattle = false;

            } else {
                ++lineNum;
                ifs >> std::hex >> actionBits;
                search::Action a(actionBits);
                a.printDesc(std::cout, bc) << std::endl;
                a.execute(bc);
            }

        } else {
            if (gc.outcome != GameOutcome::UNDECIDED) {
                break;
            }
            if (gc.screenState == sts::ScreenState::BATTLE) {
                bc = {};
                bc.init(gc);
                inBattle = true;

            } else {
                ++lineNum;
                ifs >> std::hex >> actionBits;
                search::GameAction a(actionBits);
                a.printDesc(std::cout, gc) << std::endl;
                a.execute(gc);
            }
        }
    }
}

struct AgentMtInfo {
    std::mutex m;

    std::uint64_t curSeed;
    std::uint64_t seedStart;
    std::uint64_t seedEnd;

    std::int64_t winCount = 0;
    std::int64_t lossCount = 0;
    std::int64_t floorSum = 0;
    std::int64_t totalSimulations = 0;
};

static int g_searchAscension = 0;
static int g_simulationCount = 5;
static int g_print_level = 0;

void agentMtRunner(AgentMtInfo *info) {
    std::uint64_t seed;
    {
        std::scoped_lock lock(info->m);
        seed = info->curSeed++;
    }

    while(true) {
        if (seed >= info->seedEnd) {
            break;
        }

        GameContext gc(CharacterClass::IRONCLAD, seed, g_searchAscension);
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = g_simulationCount;
        agent.rng = std::default_random_engine(gc.seed);

        agent.printActions = g_print_level & 0x1;
        agent.printLogs = g_print_level & 0x2;

        agent.playout(gc);

        printOutcome(std::cout, gc);

        {
            std::scoped_lock lock(info->m);
            info->floorSum += gc.floorNum;
            if (gc.outcome == sts::GameOutcome::PLAYER_VICTORY) {
                ++info->winCount;
            } else {
                ++info->lossCount;
            }
            info->totalSimulations += agent.simulationCountTotal;

            seed = info->curSeed++;
        }
    }
}

void agentMt(int threadCount, std::uint64_t startSeed, int playoutCount) {
    auto startTime = std::chrono::high_resolution_clock::now();
    std::vector<std::unique_ptr<std::thread>> threads;

    AgentMtInfo info;
    info.curSeed = startSeed;
    info.seedStart = startSeed;
    info.seedEnd = startSeed + playoutCount;


    if (threadCount == 1) { // doing this for more consistency when benchmarking
        agentMtRunner(&info);

    } else {
        for (int tid = 0; tid < threadCount; ++tid) {
            threads.emplace_back(new std::thread(agentMtRunner, &info));
        }
    }

    for (int tid = 0; tid < threadCount; ++tid) {
        if (threadCount > 1) {
            threads[tid]->join();
        }
    }

    auto endTime = std::chrono::high_resolution_clock::now();
    double duration = std::chrono::duration<double>(endTime-startTime).count();

    std::cout << "w/l: (" << info.winCount  << ", " << info.lossCount << ")"
        << " percentWin: " << static_cast<double>(info.winCount) / playoutCount * 100 << "%"
        << " avgFloorReached: " << static_cast<double>(info.floorSum) / playoutCount << '\n'
        << " totalSimulations: " << info.totalSimulations
        << " avgPerFloor: " << (double)info.totalSimulations/info.floorSum << '\n';

    std::cout << "threads: " << threadCount
              << " playoutCount: " << playoutCount
              << " depth: " << g_simulationCount
        << " asc: " << g_searchAscension
        << " elapsed: " << duration
        << std::endl;
}

// Happy Flower counter arithmetic across battles: the run-level relic counter
// (relic data) ticks once at battle start (initRelics) plus once per turn
// start; ending a fight on a chosen turn leaves the counter at
// (entry counter + 1 + bc.turn) mod 3, exitBattle writes it back, and a
// counter of 2 at battle start charges +1 energy immediately in the next
// combat. This is the mechanical basis of cross-combat "setup".
int testHappyFlowerCounter(std::uint64_t seed) {
    auto fail = [&](const char *msg) {
        std::cout << "happy_flower FAIL: " << msg << '\n';
        return 1;
    };
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    gc.relics.add({RelicId::HAPPY_FLOWER, 1});
    {
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        if (bc.player.happyFlowerCounter != 2) return fail("battle-start tick from run counter 1");
        if (bc.player.energy != 3) return fail("no trigger on battle-start tick 2");
        search::Action a1(search::ActionType::END_TURN);
        a1.execute(bc);
        // turn 1 start: counter 2 -> 3 -> trigger (+1 energy), counter resets to 0
        if (bc.player.happyFlowerCounter != 0) return fail("turn-1 tick trigger did not reset counter");
        if (bc.player.energy != 4) return fail("turn-1 tick trigger energy missing");
        search::Action a2(search::ActionType::END_TURN);
        a2.execute(bc);
        if (bc.player.happyFlowerCounter != 1) return fail("turn-2 tick");
        search::Action a3(search::ActionType::END_TURN);
        a3.execute(bc);
        // 4 player turns total (bc.turn == 3): end counter = (1 + 1 + 3) mod 3 == 2
        if (bc.player.happyFlowerCounter != 2) return fail("end counter (1+1+3) mod 3 != 2");
        bc.updateRelicsOnExit(gc);   // the exitBattle transfer the terminal bonus mirrors
        if (gc.relics.getRelicValue(RelicId::HAPPY_FLOWER) != 2) return fail("updateRelicsOnExit write-back");
    }
    {
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        if (bc.player.happyFlowerCounter != 0) return fail("charged battle start resets counter");
        if (bc.player.energy != 4) return fail("charged battle start grants energy");
    }
    {
        GameContext gc2(CharacterClass::IRONCLAD, seed + 1, 0);
        gc2.relics.add({RelicId::HAPPY_FLOWER, 0});
        BattleContext bc;
        bc.init(gc2, MonsterEncounter::CULTIST);
        if (bc.player.happyFlowerCounter != 1) return fail("battle-start tick from run counter 0");
        if (bc.player.energy != 3) return fail("no trigger from run counter 0");
    }
    std::cout << "happy_flower PASS\n";
    return 0;
}

// Regression tests for issues #56 (Liquid Memories zero-cost), #66 (Omamori
// counter underflow), #68 (stale multi-select validation outside CARD_SELECT
// input state), and Smoke Bomb combat semantics.
static BattleContext cardSelectFixture(CardSelectTask task, int pickCount, bool largeHand);

static void setupRelicRewardFixture(GameContext &gc,
                                    std::initializer_list<RelicId> relics,
                                    bool sapphireKey) {
    gc.screenState = ScreenState::REWARDS;
    gc.info.rewardsContainer.clear();
    for (const RelicId relic : relics) {
        gc.info.rewardsContainer.addRelic(relic);
    }
    gc.info.rewardsContainer.sapphireKey = sapphireKey;
}

static bool hasRewardAction(const GameContext &gc,
                            search::GameAction::RewardsActionType type,
                            int idx1 = 0) {
    for (const auto action : search::GameAction::getAllActionsInState(gc)) {
        if (action.getRewardsActionType() == type && action.getIdx1() == idx1) {
            return true;
        }
    }
    return false;
}

int testRelicRewardSapphire() {
    using RewardsActionType = search::GameAction::RewardsActionType;
    auto fail = [&](const char *msg) {
        std::cout << "relic_reward_sapphire FAIL: " << msg << '\n';
        return 1;
    };

    // The Sapphire-paired relic is the last relic before any reward mutation.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {RelicId::AKABEKO}, true);
        if (!hasRewardAction(gc, RewardsActionType::RELIC)
            || !hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("one-relic Sapphire fixture did not expose relic and key");
        }
        search::GameAction(RewardsActionType::RELIC, 0).execute(gc);
        if (!gc.relics.has(RelicId::AKABEKO)
            || gc.info.rewardsContainer.relicCount != 0
            || gc.info.rewardsContainer.sapphireKey
            || hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("taking the only Sapphire-paired relic kept the key option");
        }
    }

    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {RelicId::AKABEKO, RelicId::ART_OF_WAR}, true);
        search::GameAction(RewardsActionType::RELIC, 1).execute(gc);
        const auto &rewards = gc.info.rewardsContainer;
        if (!gc.relics.has(RelicId::ART_OF_WAR)
            || rewards.relicCount != 1
            || rewards.relics[0] != RelicId::AKABEKO
            || rewards.sapphireKey
            || !hasRewardAction(gc, RewardsActionType::RELIC, 0)
            || hasRewardAction(gc, RewardsActionType::RELIC, 1)
            || hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("taking the paired last relic did not remove the key option");
        }
    }

    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {RelicId::AKABEKO, RelicId::ART_OF_WAR}, true);
        search::GameAction(RewardsActionType::RELIC, 0).execute(gc);
        const auto &rewards = gc.info.rewardsContainer;
        if (!gc.relics.has(RelicId::AKABEKO)
            || rewards.relicCount != 1
            || rewards.relics[0] != RelicId::ART_OF_WAR
            || !rewards.sapphireKey
            || !hasRewardAction(gc, RewardsActionType::RELIC, 0)
            || !hasRewardAction(gc, RewardsActionType::KEY)
            || hasRewardAction(gc, RewardsActionType::RELIC, 1)) {
            return fail("taking the first unpaired relic removed its paired option");
        }
    }

    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {
            RelicId::AKABEKO, RelicId::ART_OF_WAR, RelicId::BIRD_FACED_URN
        }, true);
        search::GameAction(RewardsActionType::RELIC, 1).execute(gc);
        const auto &rewards = gc.info.rewardsContainer;
        if (!gc.relics.has(RelicId::ART_OF_WAR)
            || rewards.relicCount != 2
            || rewards.relics[0] != RelicId::AKABEKO
            || rewards.relics[1] != RelicId::BIRD_FACED_URN
            || !rewards.sapphireKey
            || !hasRewardAction(gc, RewardsActionType::RELIC, 0)
            || !hasRewardAction(gc, RewardsActionType::RELIC, 1)
            || !hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("taking a non-paired middle relic removed the key option");
        }
    }

    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {RelicId::AKABEKO, RelicId::ART_OF_WAR}, true);
        if (!hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("Sapphire key action was not legal");
        }
        search::GameAction(RewardsActionType::KEY).execute(gc);
        const auto &rewards = gc.info.rewardsContainer;
        if (!gc.blueKey
            || rewards.relicCount != 1
            || rewards.relics[0] != RelicId::AKABEKO
            || rewards.sapphireKey
            || !hasRewardAction(gc, RewardsActionType::RELIC, 0)
            || hasRewardAction(gc, RewardsActionType::KEY)) {
            return fail("taking Sapphire key did not remove the paired last relic");
        }
    }

    {
        GameContext gc(CharacterClass::IRONCLAD, 0xA11CEu, 0);
        setupRelicRewardFixture(gc, {RelicId::AKABEKO, RelicId::ART_OF_WAR}, false);
        search::GameAction(RewardsActionType::RELIC, 0).execute(gc);
        const auto &rewards = gc.info.rewardsContainer;
        if (!gc.relics.has(RelicId::AKABEKO)
            || rewards.relicCount != 1
            || rewards.relics[0] != RelicId::ART_OF_WAR
            || rewards.sapphireKey
            || hasRewardAction(gc, RewardsActionType::KEY)
            || !hasRewardAction(gc, RewardsActionType::RELIC, 0)) {
            return fail("no-Sapphire relic reward behavior changed");
        }
    }

    std::cout << "relic_reward_sapphire PASS\n";
    return 0;
}

int testIssueFixes() {
    auto fail = [&](const char *msg) {
        std::cout << "issue_fixes FAIL: " << msg << '\n';
        return 1;
    };

    // #56: chooseDiscardToHandCard must honor its forZeroCost parameter, not
    // the stale cardSelectInfo.cardSelectTask field.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.cards.cardsInHand = 0;
        bc.cards.discardPile.clear();
        bc.cards.discardPile.push_back(CardInstance(CardId::BASH));
        // Stale task left over from a prior (non-Liquid-Memories) select.
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::HOLOGRAM;
        bc.chooseDiscardToHandCard(0, true); // Liquid Memories zero-cost
        if (bc.cards.hand[0].costForTurn != 0) {
            return fail("liquid memories did not zero-cost with stale cardSelectTask");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.cards.cardsInHand = 0;
        bc.cards.discardPile.clear();
        bc.cards.discardPile.push_back(CardInstance(CardId::BASH));
        // Stale task left over from a prior Liquid Memories select: a Hologram
        // pickup must NOT be zero-cost.
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::LIQUID_MEMORIES_POTION;
        bc.chooseDiscardToHandCard(0, false); // Hologram pickup
        if (bc.cards.hand[0].costForTurn == 0) {
            return fail("hologram pickup wrongly zero-costed by stale cardSelectTask");
        }
    }

    // #66: exitBattle must not underflow a 0-charge Omamori counter.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.relics.add({RelicId::OMAMORI, 0});
        BattleContext bc;
        bc.init(gc, MonsterEncounter::WRITHING_MASS);
        bc.monsters.arr[0].miscInfo = 1; // Implant move was used
        bc.exitBattle(gc);
        if (gc.relics.getRelicValue(RelicId::OMAMORI) < 0) {
            return fail("omamori counter underflowed below 0");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.relics.add({RelicId::OMAMORI, 1});
        BattleContext bc;
        bc.init(gc, MonsterEncounter::WRITHING_MASS);
        bc.monsters.arr[0].miscInfo = 1;
        bc.exitBattle(gc);
        if (gc.relics.getRelicValue(RelicId::OMAMORI) != 0) {
            return fail("omamori counter not decremented from 1");
        }
    }

    // An eligible hallway Smoke Bomb is a legal action, is enumerated by both
    // searchers, and exits through normal bookkeeping without rewards.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.potionCapacity = 3;
        bc.potions[0] = Potion::SMOKE_BOMB;
        bc.potionCount = 1;
        gc.curRoom = Room::MONSTER;
        gc.screenState = ScreenState::BATTLE;
        gc.info.encounter = MonsterEncounter::CULTIST;
        gc.regainControlAction = [](GameContext &g) { g.afterBattle(); };
        const search::Action useSmoke(search::ActionType::POTION, 0);
        if (!useSmoke.isValidAction(bc)) {
            return fail("eligible smoke bomb use was invalid");
        }
        search::BattleScumSearcher2 s2(bc);
        s2.enumerateActionsForNode(s2.root, bc);
        if (std::none_of(s2.root.edges.begin(), s2.root.edges.end(),
                         [](const auto &e) { return e.action == search::Action(search::ActionType::POTION, 0); })) {
            return fail("Searcher2 omitted eligible smoke bomb");
        }
        search::BattleScumSearcher3 s3(bc, 1);
        search::enumerateActionsForNode(s3.root, bc);
        if (std::none_of(s3.root.edges.begin(), s3.root.edges.end(),
                         [](const auto &e) { return e.action == search::Action(search::ActionType::POTION, 0); })) {
            return fail("Searcher3 omitted eligible smoke bomb");
        }
        useSmoke.execute(bc);
        if (bc.potions[0] != Potion::EMPTY_POTION_SLOT || bc.potionCount != 0
            || bc.outcome != Outcome::PLAYER_VICTORY) {
            return fail("eligible smoke bomb did not consume and terminate");
        }
        bc.exitBattle(gc);
        if (gc.screenState != ScreenState::MAP_SCREEN || gc.smokeBombUsed
            || gc.outcome != GameOutcome::UNDECIDED) {
            return fail("smoke bomb did not return to map without reward");
        }
    }
    // Face of Cleric still runs on a Smoke Bomb exit, while the reward screen
    // and event-specific continuation are skipped.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.curRoom = Room::MONSTER;
        gc.screenState = ScreenState::BATTLE;
        gc.relics.add({RelicId::FACE_OF_CLERIC, 0});
        gc.curHp = 50;
        gc.maxHp = 80;
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.potions[0] = Potion::SMOKE_BOMB;
        bc.potionCount = 1;
        gc.regainControlAction = [](GameContext &g) { g.afterBattle(); };
        search::Action(search::ActionType::POTION, 0).execute(bc);
        const int maxHpBeforeExit = gc.maxHp;
        const int curHpBeforeExit = bc.player.curHp;
        bc.exitBattle(gc);
        if (gc.maxHp != maxHpBeforeExit + 1 || gc.curHp != curHpBeforeExit + 7
            || gc.screenState != ScreenState::MAP_SCREEN) {
            return fail("Smoke Bomb skipped normal combat-exit bookkeeping");
        }
    }
    // Boss and SURROUNDED fights reject use, preserve the potion on direct
    // execution, and still expose the independent discard action.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext boss;
        boss.init(gc, MonsterEncounter::HEXAGHOST);
        boss.potions[0] = Potion::SMOKE_BOMB;
        boss.potionCount = 1;
        const search::Action useSmoke(search::ActionType::POTION, 0);
        const search::Action discardSmoke(search::ActionType::POTION, 0, -1);
        if (!boss.smokeBombEscapeBlocked() || useSmoke.isValidAction(boss)
            || !discardSmoke.isValidAction(boss)) {
            return fail("boss Smoke Bomb legality was incorrect");
        }
        boss.drinkPotion(0); // defensive direct call must not consume it
        if (boss.potions[0] != Potion::SMOKE_BOMB || boss.potionCount != 1) {
            return fail("boss Smoke Bomb was consumed by direct execution");
        }
        search::BattleScumSearcher2 s2(boss);
        s2.enumerateActionsForNode(s2.root, boss);
        if (std::any_of(s2.root.edges.begin(), s2.root.edges.end(),
                        [](const auto &e) { return e.action == search::Action(search::ActionType::POTION, 0); })) {
            return fail("Searcher2 exposed blocked Smoke Bomb use");
        }
        search::BattleScumSearcher3 s3(boss, 1);
        search::enumerateActionsForNode(s3.root, boss);
        if (std::any_of(s3.root.edges.begin(), s3.root.edges.end(),
                        [](const auto &e) { return e.action == search::Action(search::ActionType::POTION, 0); })) {
            return fail("Searcher3 exposed blocked Smoke Bomb use");
        }
        discardSmoke.execute(boss);
        if (boss.potions[0] != Potion::EMPTY_POTION_SLOT || boss.potionCount != 0) {
            return fail("blocked Smoke Bomb discard did not consume only the discard");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext surrounded;
        surrounded.init(gc, MonsterEncounter::CULTIST);
        surrounded.player.buff<PS::SURROUNDED>();
        surrounded.potions[0] = Potion::SMOKE_BOMB;
        surrounded.potionCount = 1;
        const search::Action useSmoke(search::ActionType::POTION, 0);
        if (!surrounded.smokeBombEscapeBlocked() || useSmoke.isValidAction(surrounded)) {
            return fail("SURROUNDED Smoke Bomb use was valid");
        }
        surrounded.drinkPotion(0);
        if (surrounded.potions[0] != Potion::SMOKE_BOMB || surrounded.potionCount != 1) {
            return fail("SURROUNDED Smoke Bomb was consumed by direct use");
        }
    }
    // SimpleAgent must use the same live eligibility contract; an ordinary
    // potion remains a normal combat action.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.potions[0] = Potion::BLOCK_POTION;
        bc.potionCount = 1;
        const int oldBlock = bc.player.block;
        search::SimpleAgent agent;
        if (agent.playPotion(bc) || bc.player.block <= oldBlock || bc.potionCount != 0) {
            return fail("ordinary potion path changed");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.potions[0] = Potion::SMOKE_BOMB;
        bc.potionCount = 1;
        search::SimpleAgent agent;
        agent.playPotion(bc);
        if (bc.outcome != Outcome::PLAYER_VICTORY || bc.potionCount != 0) {
            return fail("SimpleAgent did not use eligible Smoke Bomb");
        }
    }

    // #53: Fairy in a Bottle + Sacred Bark must revive at 60% max HP, not 1.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.maxHp = 100;
        gc.curHp = 0;
        gc.potions[0] = Potion::FAIRY_POTION;
        gc.potionCount = 1;
        gc.relics.add({RelicId::SACRED_BARK, 0});
        gc.playerOnDie();
        if (gc.curHp != 60) {
            return fail("fairy+bark revive did not restore 60% max HP");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.maxHp = 100;
        gc.curHp = 0;
        gc.potions[0] = Potion::FAIRY_POTION;
        gc.potionCount = 1;
        gc.playerOnDie();
        if (gc.curHp != 30) {
            return fail("fairy revive without bark did not restore 30% max HP");
        }
    }

    // #63: Peace Pipe TOKE must keep the remove card-select screen open so a
    // pick can be made (regainControl is invoked when the pick is resolved).
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        gc.screenState = ScreenState::REST_ROOM;
        // Equivalent of the internal returnToMapAction: what a prior floor's
        // resolution leaves installed. Old TOKE code would invoke it eagerly.
        gc.regainControlAction = [](GameContext &gs) {
            gs.screenState = ScreenState::MAP_SCREEN;
            gs.regainControlAction = nullptr;
        };
        gc.chooseCampfireOption(4); // TOKE
        if (gc.screenState != ScreenState::CARD_SELECT
            || gc.info.selectScreenType != CardSelectScreenType::REMOVE) {
            return fail("toke did not open and keep the remove card-select screen");
        }
    }

    // #64: an event-fight regainControlAction lambda inherited by a branch
    // copy must consume the branch's RNG, never the captured original's.
    {
        GameContext live(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        live.curEvent = Event::DESIGNER_IN_SPIRE;
        live.screenState = ScreenState::EVENT_SCREEN;
        live.chooseEventOption(4); // remove + random upgrade; sets the lambda
        const int liveMiscCounter = live.miscRng.counter;
        GameContext branch = live; // branch copy inherits the pending lambda
        branch.chooseSelectCardScreenOption(0); // resolve the remove select
        if (live.miscRng.counter != liveMiscCounter) {
            return fail("branch event lambda advanced the original's miscRng");
        }
    }

    // #68: multi-select validation must require CARD_SELECT input state. After
    // a select resolves, cardSelectInfo.cardSelectTask is stale (EXHAUST_MANY /
    // GAMBLE masks are re-validated against it in fair-mode edge re-checks), so
    // MULTI_CARD_SELECT actions must not validate once inputState leaves
    // CARD_SELECT -- matching isValidSingleCardSelectAction's guard.
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::EXHAUST_MANY, 2, false);
        search::Action valid(search::ActionType::MULTI_CARD_SELECT, 0b11); // hand idx {0,1}
        if (!valid.isValidAction(bc)) {
            return fail("multi-select EXHAUST_MANY mask invalid in CARD_SELECT state");
        }
        bc.inputState = InputState::PLAYER_NORMAL; // stale task remains installed
        if (valid.isValidAction(bc)) {
            return fail("multi-select EXHAUST_MANY validated with stale task outside CARD_SELECT");
        }
    }
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::GAMBLE, 1, false);
        search::Action valid(search::ActionType::MULTI_CARD_SELECT, 0b101); // hand idx {0,2}
        if (!valid.isValidAction(bc)) {
            return fail("multi-select GAMBLE mask invalid in CARD_SELECT state");
        }
        bc.inputState = InputState::PLAYER_NORMAL; // stale task remains installed
        if (valid.isValidAction(bc)) {
            return fail("multi-select GAMBLE validated with stale task outside CARD_SELECT");
        }
    }

    // #67: default-constructed GameContext/BattleContext potion slots must be
    // EMPTY_POTION_SLOT (1), not Potion::INVALID (0), so obtainPotion does not
    // silently drop potions on an uninitialized context.
    {
        GameContext gc;
        for (int i = 0; i < 5; ++i) {
            if (gc.potions[i] != Potion::EMPTY_POTION_SLOT) {
                return fail("default GameContext potion slot is INVALID");
            }
        }
        BattleContext bc;
        for (int i = 0; i < 5; ++i) {
            if (bc.potions[i] != Potion::EMPTY_POTION_SLOT) {
                return fail("default BattleContext potion slot is INVALID");
            }
        }
    }

    // #84: anyCardBottled must be true when ANY bottle slot is active (a
    // bottled card exists), and remove() must keep the bottle indices aligned
    // when a card is removed from below a bottled card.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        Deck d;
        d.obtainRaw(Card(CardId::STRIKE_RED));   // idx 0 (attack)
        d.obtainRaw(Card(CardId::DEFEND_RED));   // idx 1 (skill)
        d.obtainRaw(Card(CardId::IRON_WAVE));    // idx 2 (attack)
        d.obtainRaw(Card(CardId::DEMON_FORM));   // idx 3 (power)
        if (d.anyCardBottled()) {
            return fail("anyCardBottled true with no bottled cards");
        }
        d.bottleCard(1, CardType::SKILL);        // Bottled Lightning on idx 1
        if (!d.anyCardBottled()) {
            return fail("anyCardBottled false with one bottled card");
        }
        d.bottleCard(3, CardType::POWER);        // Bottled Tornado on idx 3
        d.bottleCard(0, CardType::ATTACK);       // Bottled Flame on idx 0
        if (!d.anyCardBottled()) {
            return fail("anyCardBottled false with three bottled cards");
        }
        d.remove(gc, 2);                         // remove the card between bottled cards
        if (!d.isCardBottled(2)) {
            return fail("bottle index not shifted after removal");
        }
        if (d.isCardBottled(3)) {
            return fail("bottle index stale after removal");
        }
    }

    // #72: reuseSearchCount must track tree promotion so STS_REUSE_ALWAYS_Q
    // (always use Q on carried trees) is not dead: -1 on a fresh searcher,
    // 0 right after advanceRoot promotes the tree, then per-search counts.
    {
        if (search::g_s3AlwaysQ) {
            return fail("STS_S3_ALWAYS_Q default is not off");
        }
        search::g_reuseAlwaysQ = false;
        if (search::s3ShouldExploitQ(false, -1)
            || !search::s3ShouldExploitQ(true, -1)) {
            return fail("legacy Q exploit gating changed");
        }
        search::g_s3AlwaysQ = true;
        if (!search::s3ShouldExploitQ(false, -1)
            || !search::s3ShouldExploitQ(true, -1)) {
            return fail("S3 always-Q did not enable fresh-tree exploitation");
        }
        search::g_s3AlwaysQ = false;
        search::g_reuseAlwaysQ = true;
        if (search::s3ShouldExploitQ(false, -1)
            || !search::s3ShouldExploitQ(false, 0)) {
            return fail("reuse always-Q semantics changed");
        }
        search::g_reuseAlwaysQ = false;

        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::BattleScumSearcher3 s3(bc, bc.seed, 0, 8);
        if (s3.reuseSearchCount != -1) {
            return fail("fresh searcher reuseSearchCount != -1");
        }
        s3.search(64);
        if (s3.root.edges.empty()) {
            return fail("no root edges after search");
        }
        std::int64_t maxVisits = -1;
        search::Action best;
        for (const auto &e : s3.root.edges) {
            if (e.child.simulationCount > maxVisits) {
                maxVisits = e.child.simulationCount;
                best = e.action;
            }
        }
        if (!s3.advanceRoot(best, bc)) {
            return fail("advanceRoot did not reuse a searched child");
        }
        if (s3.reuseSearchCount != 0) {
            return fail("reuseSearchCount not reset on promotion");
        }
        s3.search(16);
        if (s3.reuseSearchCount != 1) {
            return fail("reuseSearchCount not incremented after promoted search");
        }
    }

    // Searcher3 Q-gate timing: the default gate is initially closed, opens
    // from a positive nonterminal backpropagation, and is recorded once.  The
    // ordinary and LIVE_VALID selectors must use the same baseline predicate.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0x13579Bu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::g_s3AlwaysQ = false;
        search::g_reuseAlwaysQ = false;
        search::BattleScumSearcher3 legacy(bc, bc.seed, 0, 8);
        if (legacy.firstQExploitSimulation != -1) {
            return fail("firstQExploitSimulation was not initially unset");
        }
        search::g_s3AlwaysQ = true;
        if (!search::s3ShouldExploitQ(false, -1)) {
            return fail("ALWAYS_Q global predicate did not remain immediate");
        }
        search::g_s3AlwaysQ = false;

        search::BattleScumSearcher3::Node legal;
        search::enumerateActionsForNode(legal, bc);
        if (legal.edges.size() < 2) return fail("Q-gate selector fixture has <2 actions");
        search::BattleScumSearcher3::Node node;
        node.simulationCount = 100;
        node.edges.resize(2);
        node.edges[0].action = legal.edges[0].action;
        node.edges[1].action = legal.edges[1].action;
        node.edges[0].child.simulationCount = 10;
        node.edges[1].child.simulationCount = 10;
        node.edges[0].child.evaluationSum = 0.0;
        node.edges[1].child.evaluationSum = 100.0;
        if (legacy.selectBestEdgePUCT(node) != 0
            || legacy.selectBestValidEdgePUCT(node, bc) != 0) {
            return fail("ordinary/LIVE_VALID selectors opened Q gate too early");
        }
        std::vector<search::Action> winningLine{legal.edges[0].action};
        // A positive nonterminal rollout/VNet-style evaluation opens the
        // existing gate because it populates bestActionSequence; no terminal
        // win is required by this mechanism.
        legacy.backpropagate({}, -1.0, {});
        if (search::s3ShouldExploitQ(false, legacy.reuseSearchCount)
            || legacy.firstQExploitSimulation != -1) {
            return fail("negative/nonterminal pre-gate backprop opened Q gate");
        }
        legacy.searchSimulationOrdinal = 1;
        legacy.backpropagate({}, 1.0, winningLine);
        if (!search::s3ShouldExploitQ(!legacy.bestActionSequence.empty(), legacy.reuseSearchCount)
            || legacy.firstQExploitSimulation != 1) {
            return fail("firstQExploitSimulation did not record first gate opening");
        }
        if (legacy.selectBestEdgePUCT(node) != 1
            || legacy.selectBestValidEdgePUCT(node, bc) != 1) {
            return fail("ordinary/LIVE_VALID selectors did not open together");
        }
        legacy.backpropagate({}, 2.0, winningLine);
        if (legacy.firstQExploitSimulation != 1) {
            return fail("firstQExploitSimulation was not first-only telemetry");
        }
        search::g_s3AlwaysQ = false;
        search::g_reuseAlwaysQ = false;
    }

    std::cout << "issue_fixes PASS\n";
    return 0;
}

int testSeedContract(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::BattleScumSearcher3 a(bc, seed, 0, 8);
    search::BattleScumSearcher3 b(bc, seed, 1, 8);       // different decision index
    search::BattleScumSearcher3 c(bc, seed, 0, 8);       // same inputs as a
    search::BattleScumSearcher3 d(bc, seed + 1, 0, 8);   // different agent seed
    const std::uint64_t da = a.rng();
    if (da != c.rng()) {
        std::cout << "seed_contract FAIL: same inputs diverge\n";
        return 1;
    }
    if (da == b.rng()) {
        std::cout << "seed_contract FAIL: decision index ignored\n";
        return 1;
    }
    if (da == d.rng()) {
        std::cout << "seed_contract FAIL: agent seed ignored\n";
        return 1;
    }

    // Full-search determinism: two identical searchers must produce identical
    // root edges (action + obsHash key) and visit counts after a fixed budget.
    search::BattleScumSearcher3 s1(bc, seed, 0, 8);
    search::BattleScumSearcher3 s2(bc, seed, 0, 8);
    s1.search(200);
    s2.search(200);
    if (s1.root.edges.size() != s2.root.edges.size()) {
        std::cout << "seed_contract FAIL: search edge count diverged\n";
        return 1;
    }
    for (size_t i = 0; i < s1.root.edges.size(); ++i) {
        const auto &e1 = s1.root.edges[i], &e2 = s2.root.edges[i];
        if (e1.action != e2.action || e1.child.obsHash != e2.child.obsHash
            || e1.child.simulationCount != e2.child.simulationCount) {
            std::cout << "seed_contract FAIL: search tree diverged at edge " << i << "\n";
            return 1;
        }
    }
    std::cout << "seed_contract PASS\n";
    return 0;
}

int testDrawpile(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::BattleScumSearcher3 s3(bc, seed, 0, 8);
    const auto &particle = s3.belief.particles[0];
    BattleContext copy = bc;
    s3.applyParticle(copy, particle);
    if (copy.cards.drawPile.size() != (int)particle.drawPileOrder.size()) {
        std::cout << "drawpile FAIL: pile size changed\n";
        return 1;
    }
    for (int i = 0; i < copy.cards.drawPile.size(); ++i) {
        if (copy.cards.drawPile[i].getId() != particle.drawPileOrder[i].getId()) {
            std::cout << "drawpile FAIL: sampled order not installed\n";
            return 1;
        }
    }
    std::cout << "drawpile PASS\n";
    return 0;
}

int testObsIdentity(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    CombatObservation a = CombatObservation::fromBattleContext(bc);
    CombatObservation b = CombatObservation::fromBattleContext(bc);
    if (!(a == b) || a.visibleHash() != b.visibleHash()) {
        std::cout << "obs_identity FAIL: identical observations diverge\n";
        return 1;
    }
    if (a.hand.size() >= 2) {
        CombatObservation c = a;
        CardInstance tmp = c.hand[0]; c.hand[0] = c.hand[1]; c.hand[1] = tmp;
        if (!(a == c)) {
            std::cout << "obs_identity FAIL: hand multiset order not equal\n";
            return 1;
        }
        if (a.visibleHash() != c.visibleHash()) {
            std::cout << "obs_identity FAIL: equal observations hash differently\n";
            return 1;
        }
        CombatObservation d = a;
        d.hand[0] = CardInstance(d.hand[0].getId() == CardId::STRIKE_RED
                                     ? CardId::DEFEND_RED : CardId::STRIKE_RED, false);
        if (a == d) {
            std::cout << "obs_identity FAIL: different hand contents compare equal\n";
            return 1;
        }
    }

    // Decision context must be part of identity: a PLAYER_NORMAL state and a
    // CARD_SELECT state with otherwise identical fields are different decisions.
    CombatObservation e = a;
    e.inputState = InputState::CARD_SELECT;
    e.cardSelectTask = CardSelectTask::WARCRY;
    e.pickCount = 1;
    e.canPickZero = false;
    e.canPickAnyNumber = false;
    if (a == e || a.visibleHash() == e.visibleHash()) {
        std::cout << "obs_identity FAIL: decision context (inputState/task) ignored\n";
        return 1;
    }
    CombatObservation f = e;
    f.cardSelectTask = CardSelectTask::SEEK;
    if (e == f || e.visibleHash() == f.visibleHash()) {
        std::cout << "obs_identity FAIL: different card-select tasks conflated\n";
        return 1;
    }
    CombatObservation g = e;
    g.cardSelectOffers = {CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::STRIKE_RED};
    if (e == g || e.visibleHash() == g.visibleHash()) {
        std::cout << "obs_identity FAIL: different card-select offers conflated\n";
        return 1;
    }
    CombatObservation h = e;
    h.pickCount = 2;
    if (e == h || e.visibleHash() == h.visibleHash()) {
        std::cout << "obs_identity FAIL: different pickCount conflated\n";
        return 1;
    }
    std::cout << "obs_identity PASS\n";
    return 0;
}

int testS3StrategyFusionDiag(std::uint64_t seed) {
    int failures = 0;
    auto check = [&](bool ok, const char *message) {
        if (!ok) {
            std::cout << "s3_strategy_fusion_diag FAIL: " << message << '\n';
            ++failures;
        }
    };

    check(!search::g_s3StrategyFusionDiag, "diagnostic is not off by default");

    search::BattleScumSearcher3::Node stableParent;
    stableParent.nodeObsVisits = 1;
    check(stableParent.isObsStable(), "stable END_TURN parent was rejected");
    stableParent.nodeObsMismatches = 1;
    check(!stableParent.isObsStable(), "unstable END_TURN parent was accepted");

    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    CombatObservation visible = CombatObservation::fromBattleContext(bc);

    // Hidden draw order/RNG may differ while the full visible observation
    // remains equal; a visible change must not compare equal.
    BattleContext hiddenVariant = bc;
    std::reverse(hiddenVariant.cards.drawPile.begin(), hiddenVariant.cards.drawPile.end());
    hiddenVariant.shuffleRng.counter += 11;
    hiddenVariant.cardRandomRng.counter += 7;
    CombatObservation sameVisible = CombatObservation::fromBattleContext(hiddenVariant);
    check(visible == sameVisible && visible.visibleHash() == sameVisible.visibleHash(),
          "bucket identity includes hidden order or RNG");
    hiddenVariant.player.curHp -= 1;
    check(visible != CombatObservation::fromBattleContext(hiddenVariant),
          "bucket identity ignored a visible change");

    // Recreate the equal-visible fixture and prove fresh beliefs are sampled
    // from that observation rather than inheriting the hidden representative.
    hiddenVariant.player.curHp = bc.player.curHp;
    std::sort(hiddenVariant.cards.drawPile.begin(), hiddenVariant.cards.drawPile.end(),
              [](const CardInstance &a, const CardInstance &b) {
                  return FullHiddenCardId(a) < FullHiddenCardId(b);
              });
    BattleContext canonical = bc;
    std::sort(canonical.cards.drawPile.begin(), canonical.cards.drawPile.end(),
              [](const CardInstance &a, const CardInstance &b) {
                  return FullHiddenCardId(a) < FullHiddenCardId(b);
              });
    search::BattleScumSearcher3 a(canonical, seed, 0, 8);
    search::BattleScumSearcher3 b(hiddenVariant, seed, 0, 8);
    check(a.rootObs == b.rootObs, "equal visible inputs got different observations");
    check(a.belief.particles.size() == b.belief.particles.size(),
          "equal visible inputs got different particle counts");
    if (a.belief.particles.size() == b.belief.particles.size()) {
        for (size_t i = 0; i < a.belief.particles.size(); ++i)
            check(fullHiddenStateKey(a.belief.particles[i])
                      == fullHiddenStateKey(b.belief.particles[i]),
                  "fresh belief inherited hidden future state");
    }

    // Semantic CARD identity includes target, but never uses raw hand index
    // as the comparison key.
    if (bc.cards.cardsInHand > 0) {
        const auto first = search::semanticActionIdentity(
            search::Action(search::ActionType::CARD, 0, 0), bc);
        const auto otherTarget = search::semanticActionIdentity(
            search::Action(search::ActionType::CARD, 0, 1), bc);
        check(first != otherTarget, "CARD target was omitted from identity");
        if (bc.cards.cardsInHand > 1) {
            BattleContext duplicateHand = bc;
            duplicateHand.cards.hand[1] = duplicateHand.cards.hand[0];
            const auto firstPosition = search::semanticActionIdentity(
                search::Action(search::ActionType::CARD, 0, 0), duplicateHand);
            const auto secondPosition = search::semanticActionIdentity(
                search::Action(search::ActionType::CARD, 1, 0), duplicateHand);
            check(firstPosition == secondPosition,
                  "equivalent CARD instances were compared by hand position");
        }
    }

    // Policy extraction is read-only: it cannot mutate the live shared node.
    a.search(64);
    const size_t edgeCount = a.root.edges.size();
    std::vector<std::int64_t> visits;
    for (const auto &edge : a.root.edges) visits.push_back(edge.child.simulationCount);
    (void)search::pickSearchAction(a.root, bc);
    check(a.root.edges.size() == edgeCount, "read-only extraction changed topology");
    for (size_t i = 0; i < a.root.edges.size(); ++i)
        check(a.root.edges[i].child.simulationCount == visits[i],
              "read-only extraction changed visits");

    // Regression: strategy-fusion candidates are only recorded during step(),
    // but side searches must wait for the normal search to finish and use the
    // final child statistics. Use one particle so no multi-bucket side probe
    // is eligible; this test inspects only the lifecycle provenance.
    const bool oldStrategyDiag = search::g_s3StrategyFusionDiag;
    const std::string oldStrategyDiagFile = search::g_s3StrategyFusionDiagFile;
    const int oldStrategyParticles = search::g_s3StrategyFusionDiagParticles;
    const int oldStrategyMaxTransitions = search::g_s3StrategyFusionDiagMaxTransitions;
    const int oldStrategyMinVisits = search::g_s3StrategyFusionDiagMinChildVisits;
    const int oldStrategyFreshSims = search::g_s3StrategyFusionDiagFreshSims;
    const int oldStrategyReferenceSims = search::g_s3StrategyFusionDiagReferenceSims;
    search::g_s3StrategyFusionDiag = true;
    search::g_s3StrategyFusionDiagFile.clear();
    search::g_s3StrategyFusionDiagParticles = 1;
    search::g_s3StrategyFusionDiagMaxTransitions = 1;
    search::g_s3StrategyFusionDiagMinChildVisits = 8;
    search::g_s3StrategyFusionDiagFreshSims = 0;
    search::g_s3StrategyFusionDiagReferenceSims = 0;
    search::BattleScumSearcher3 lifecycleProbe(canonical, seed, 0, 8);
    lifecycleProbe.search(128);
    const auto &visitRecords = lifecycleProbe.strategyFusionFinalVisitRecordsForTest();
    check(!visitRecords.empty(),
          "no stable-parent strategy-fusion candidate was finalized");
    bool observedPostSearchGrowth = false;
    for (const auto &record : visitRecords)
        observedPostSearchGrowth = observedPostSearchGrowth || record.second > record.first;
    check(observedPostSearchGrowth,
          "strategy-fusion used threshold-time rather than final child visits");
    search::g_s3StrategyFusionDiag = oldStrategyDiag;
    search::g_s3StrategyFusionDiagFile = oldStrategyDiagFile;
    search::g_s3StrategyFusionDiagParticles = oldStrategyParticles;
    search::g_s3StrategyFusionDiagMaxTransitions = oldStrategyMaxTransitions;
    search::g_s3StrategyFusionDiagMinChildVisits = oldStrategyMinVisits;
    search::g_s3StrategyFusionDiagFreshSims = oldStrategyFreshSims;
    search::g_s3StrategyFusionDiagReferenceSims = oldStrategyReferenceSims;

    if (failures == 0) {
        std::cout << "s3_strategy_fusion_diag PASS\n";
        return 0;
    }
    return 1;
}

int testS3PersistentEndTurnChance(std::uint64_t seed) {
    int failures = 0;
    auto check = [&](bool ok, const char *message) {
        if (!ok) {
            std::cout << "s3_persistent_endturn_chance FAIL: " << message << '\n';
            ++failures;
        }
    };

    check(!search::g_s3PersistentEndTurnChance,
          "treatment is not off by default");
    check(search::g_s3PersistentEndTurnMaxPile == 8,
          "persistent chance max-pile default is not 8");
    check(search::s3PersistentChanceFlagsCompatible(false, false, false)
              && search::s3PersistentChanceFlagsCompatible(true, false, false)
              && search::s3PersistentChanceFlagsCompatible(false, true, true)
              && !search::s3PersistentChanceFlagsCompatible(true, true, false)
              && !search::s3PersistentChanceFlagsCompatible(true, false, true)
              && !search::s3PersistentChanceFlagsCompatible(true, true, true),
          "flag-conflict contract is wrong");

    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext pre;
    pre.init(gc, MonsterEncounter::CULTIST);
    const search::Action endTurn(search::ActionType::END_TURN);

    // Make the hidden order decision-bearing: seven cards remain, so drawing
    // five from opposite orders leaves different visible hands/remainders.
    pre.cards.drawPile.push_back(CardInstance(CardId::BASH, false));
    pre.cards.drawPile.push_back(CardInstance(CardId::ANGER, false));
    const int savedMarginalMaxPile = search::g_s3EndTurnMarginalizeMaxPile;
    const int savedPersistentMaxPile = search::g_s3PersistentEndTurnMaxPile;
    search::g_s3EndTurnMarginalizeMaxPile = 0;
    check(search::BattleScumSearcher3::persistentEndTurnEligible(pre, endTurn),
          "chance eligibility still depends on marginalization max-pile");
    search::g_s3PersistentEndTurnMaxPile = 6;
    check(!search::BattleScumSearcher3::persistentEndTurnEligible(pre, endTurn),
          "independent persistent chance max-pile was ignored");
    search::g_s3PersistentEndTurnMaxPile = savedPersistentMaxPile;
    search::g_s3EndTurnMarginalizeMaxPile = savedMarginalMaxPile;
    BattleContext reshuffle = pre;
    reshuffle.cards.drawPile.clear();
    reshuffle.cards.discardPile.push_back(CardInstance(CardId::STRIKE_RED, false));
    check(!search::BattleScumSearcher3::persistentEndTurnEligible(
              reshuffle, endTurn),
          "immediate reshuffle boundary was accepted");

    BattleContext postA = pre;
    BattleContext postB = pre;
    std::reverse(postB.cards.drawPile.begin(), postB.cards.drawPile.end());
    endTurn.execute(postA);
    endTurn.execute(postB);
    const auto obsA = CombatObservation::fromBattleContext(postA);
    const auto obsB = CombatObservation::fromBattleContext(postB);
    const auto preObservationHash =
        CombatObservation::fromBattleContext(pre).visibleHash();
    check(obsA != obsB, "opposite hidden orders did not produce split observations");

    search::BattleScumSearcher3 searcher(pre, seed, 0, 8);
    search::BattleScumSearcher3::Edge edge{endTurn};
    searcher.dispatchPersistentEndTurnOutcome(edge, preObservationHash, obsA);
    searcher.dispatchPersistentEndTurnOutcome(edge, preObservationHash, obsB);
    check(edge.persistentChanceContainer && edge.outcomeChildren.size() == 2,
          "different observations did not create two persistent children");

    auto &childA = searcher.dispatchPersistentEndTurnOutcome(
        edge, preObservationHash, obsA);
    auto &childB = searcher.dispatchPersistentEndTurnOutcome(
        edge, preObservationHash, obsB);
    check(&childA != &childB,
          "sampled observations dispatched to the same decision child");
    check(searcher.outcomeExistingHits == 2
              && searcher.outcomeNewMisses == 2,
          "hit/miss diagnostics are inconsistent");

    // Hidden RNG/counters are deliberately absent from CombatObservation.
    BattleContext hiddenVariant = postA;
    hiddenVariant.shuffleRng.counter += 17;
    hiddenVariant.cardRandomRng.counter += 9;
    const auto sameVisible = CombatObservation::fromBattleContext(hiddenVariant);
    check(sameVisible == obsA,
          "fixture unexpectedly exposed hidden RNG through observation identity");
    auto &sameChild = searcher.dispatchPersistentEndTurnOutcome(
        edge, preObservationHash, sameVisible);
    check(&sameChild == &childA && edge.outcomeChildren.size() == 2,
          "same visible outcome did not reuse its persistent child");

    // One aggregate stream backs the parent action; conditioned nodes also
    // receive their own statistics. Outcome Q is never consulted by dispatch.
    searcher.backpropagate({&edge.child, &childA}, 10.0, {endTurn});
    searcher.backpropagate({&edge.child, &childB}, 30.0, {endTurn});
    childA.evaluationSum = -1000.0; // must not redirect obsA to childB
    auto &stillA = searcher.dispatchPersistentEndTurnOutcome(
        edge, preObservationHash, obsA);
    check(&stillA == &childA,
          "outcome dispatch selected by Q rather than sampled observation");
    check(edge.child.simulationCount == 2 && edge.child.evaluationSum == 40.0,
          "aggregate END_TURN action backup is incorrect");
    check(childA.simulationCount == 1 && childB.simulationCount == 1,
          "conditioned child visits did not accumulate independently");
    check(edge.child.edges.empty(),
          "aggregate chance container became a policy decision node");

    BattleContext differentVisiblePre = pre;
    ++differentVisiblePre.player.block;
    const auto differentPreHash =
        CombatObservation::fromBattleContext(differentVisiblePre).visibleHash();
    check(differentPreHash != preObservationHash,
          "pre-observation mismatch fixture did not change the visible hash");
    searcher.dispatchPersistentEndTurnOutcome(edge, differentPreHash, obsA);
    check(edge.persistentPreObservationMismatches == 1,
          "legacy-container pre-observation mixing was not diagnosed");

    if (failures == 0) {
        std::cout << "s3_persistent_endturn_chance PASS\n";
        return 0;
    }
    return 1;
}

int testPrune(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    if (search::BattleScumSearcher3::canPruneAsDead(bc)) {
        std::cout << "prune FAIL: pruned while player can act\n";
        return 1;
    }
    BattleContext lethal = bc;
    lethal.inputState = InputState::EXECUTING_ACTIONS;   // player cannot act
    lethal.player.curHp = 1;
    lethal.player.block = 0;
    lethal.cards.handNormalityCount = 1;                 // card play disallowed
    lethal.player.cardsPlayedThisTurn = 3;
    lethal.monsters.arr[0].curHp = 1;
    lethal.monsters.arr[0].moveHistory[0] = MMID::LOOTER_MUG;
    if (!search::BattleScumSearcher3::canPruneAsDead(lethal)) {
        std::cout << "prune FAIL: lethal enemy-turn state not pruned\n";
        return 1;
    }
    lethal.inputState = InputState::PLAYER_NORMAL;
    if (search::BattleScumSearcher3::canPruneAsDead(lethal)) {
        std::cout << "prune FAIL: pruned in PLAYER_NORMAL\n";
        return 1;
    }
    lethal.inputState = InputState::EXECUTING_ACTIONS;
    lethal.monsters.arr[0].moveHistory[0] = MMID::CULTIST_INCANTATION;   // not an attack
    if (search::BattleScumSearcher3::canPruneAsDead(lethal)) {
        std::cout << "prune FAIL: pruned without incoming attack\n";
        return 1;
    }
    std::cout << "prune PASS\n";
    return 0;
}

// ---- CARD_SELECT action-parity contract -------------------------------------
// Ground truth for a CARD_SELECT state is exactly the action set the simulator
// validates (search::Action::isValidAction): in this input mode only
// SINGLE_CARD_SELECT and MULTI_CARD_SELECT actions can validate. Every
// enumerator -- the canonical search::Action::enumerateCardSelectActions and
// both searchers' CARD_SELECT branches -- must match it exactly, or the search
// can be blind to legal selections (see knowledge-base issues tracker).

static std::vector<std::uint32_t> cardSelectGroundTruth(const BattleContext &bc) {
    std::set<std::uint32_t> s;
    for (int idx = 0; idx < 64; ++idx) {
        search::Action a(search::ActionType::SINGLE_CARD_SELECT, idx);
        if (a.isValidAction(bc)) s.insert(a.bits);
    }
    const int n = bc.cards.cardsInHand;
    if (n >= 0 && n <= 10) {
        for (std::uint32_t mask = 0; mask < (1u << n); ++mask) {
            search::Action a(search::ActionType::MULTI_CARD_SELECT, (int)mask);
            if (a.isValidAction(bc)) s.insert(a.bits);
        }
    }
    return std::vector<std::uint32_t>(s.begin(), s.end());
}

// Canonical PLAYER_NORMAL action spec: playable hand cards (adjacent duplicates
// collapsed, one action per targetable monster for targeted cards), usable
// potions (fairy excluded), and END_TURN. Must equal both searchers' output.
static std::vector<std::uint32_t> playerNormalGroundTruth(const BattleContext &bc) {
    std::set<std::uint32_t> s;
    for (int h = 0; h < bc.cards.cardsInHand; ++h) {
        const auto &c = bc.cards.hand[h];
        if (!c.canUseOnAnyTarget(bc)) continue;
        if (h > 0) {
            const auto &p = bc.cards.hand[h - 1];
            if (c.getId() == p.getId() && c.getUpgradeCount() == p.getUpgradeCount()
                && c.costForTurn == p.costForTurn && c.freeToPlayOnce == p.freeToPlayOnce
                && c.specialData == p.specialData) continue;
        }
        if (c.requiresTarget()) {
            for (int t = 0; t < bc.monsters.monsterCount; ++t) {
                search::Action a(search::ActionType::CARD, h, t);
                if (a.isValidAction(bc)) s.insert(a.bits);
            }
        } else {
            search::Action a(search::ActionType::CARD, h);
            if (a.isValidAction(bc)) s.insert(a.bits);
        }
    }
    for (int p = 0; p < bc.potionCapacity; ++p) {
        const auto pot = bc.potions[p];
        if (pot == Potion::INVALID || pot == Potion::EMPTY_POTION_SLOT
            || pot == Potion::FAIRY_POTION || pot == Potion::SMOKE_BOMB) continue;
        if (potionRequiresTarget(pot)) {
            for (int t = 0; t < bc.monsters.monsterCount; ++t) {
                search::Action a(search::ActionType::POTION, p, t);
                if (a.isValidAction(bc)) s.insert(a.bits);
            }
        } else {
            search::Action a(search::ActionType::POTION, p);
            if (a.isValidAction(bc)) s.insert(a.bits);
        }
    }
    search::Action end(search::ActionType::END_TURN);
    if (end.isValidAction(bc)) s.insert(end.bits);
    return std::vector<std::uint32_t>(s.begin(), s.end());
}

static BattleContext cardSelectFixture(CardSelectTask task, int pickCount, bool largeHand) {
    GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    const CardInstance handCards[] = {
        CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED),        // duplicate of [0]
        CardInstance(CardId::DEFEND_RED),
        CardInstance(CardId::BASH),              // requires target
        CardInstance(CardId::ARMAMENTS),         // upgradable skill
        CardInstance(CardId::ARMAMENTS, true),   // already upgraded
        CardInstance(CardId::INFLAME),           // power
        CardInstance(CardId::EXHUME),            // skill
        CardInstance(CardId::DEFEND_RED),
        CardInstance(CardId::STRIKE_RED, true),
    };
    bc.cards.cardsInHand = largeHand ? 10 : 5;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) bc.cards.hand[i] = handCards[i];
    bc.cards.drawPile.clear();
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.drawPile.push_back(CardInstance(CardId::BASH));
    bc.cards.drawPile.push_back(CardInstance(CardId::STRIKE_RED));
    bc.cards.discardPile.clear();
    bc.cards.discardPile.push_back(CardInstance(CardId::BASH));
    bc.cards.discardPile.push_back(CardInstance(CardId::STRIKE_RED));
    bc.cards.discardPile.push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.exhaustPile.clear();
    bc.cards.exhaustPile.push_back(CardInstance(CardId::EXHUME));   // excluded by EXHUME legality
    bc.cards.exhaustPile.push_back(CardInstance(CardId::STRIKE_RED));
    bc.inputState = InputState::CARD_SELECT;
    bc.cardSelectInfo.cardSelectTask = task;
    bc.cardSelectInfo.pickCount = pickCount;
    return bc;
}

static BattleContext playerNormalFixture(std::uint64_t seed, int energy) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    const CardInstance handCards[] = {
        CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED),        // duplicate of [0]
        CardInstance(CardId::DEFEND_RED),
        CardInstance(CardId::BASH),              // requires target
        CardInstance(CardId::ARMAMENTS),
        CardInstance(CardId::STRIKE_RED, true),
    };
    bc.cards.cardsInHand = 6;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) bc.cards.hand[i] = handCards[i];
    bc.player.energy = energy;
    bc.potionCapacity = 3;
    bc.potions[0] = Potion::FIRE_POTION;      // requires target
    bc.potions[1] = Potion::STRENGTH_POTION;  // no target
    bc.potions[2] = Potion::FAIRY_POTION;     // never offer
    bc.inputState = InputState::PLAYER_NORMAL;
    return bc;
}

// E2c observer scoping: the BattleContext persistent-exit hook must be inert by
// default. A deliberately executed non-live exitBattle (outside the E2c run-loop
// scope) never arms it, so it cannot produce a RAW row. Only an explicitly armed
// live victory exit invokes the observer, exactly once, before regainControl.
int testE2cObserverScope() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };
    check(!sts::g_onBattleExitPersistent, "hook must be null by default (inert)");

    GameContext gc(CharacterClass::IRONCLAD, 0xE2C1u, 0);
    gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    int fired = 0;
    const auto obs = [&fired](const BattleContext &, GameContext &) { ++fired; };

    // Non-live exit (observer NOT armed): must not fire, even on victory.
    {
        BattleContext bc = playerNormalFixture(0xE2C1u, 3);
        bc.outcome = Outcome::PLAYER_VICTORY;
        check(!sts::g_onBattleExitPersistent, "non-live path must not arm the hook");
        fired = 0;
        bc.exitBattle(gc);
        check(fired == 0, "unarmed non-live exitBattle must not invoke the observer");
    }

    // Live-scope armed victory exit: fires exactly once, before regainControl.
    {
        BattleContext bc = playerNormalFixture(0xE2C2u, 3);
        bc.outcome = Outcome::PLAYER_VICTORY;
        sts::g_onBattleExitPersistent = obs;
        fired = 0;
        gc.screenState = ScreenState::BATTLE;
        bc.exitBattle(gc);
        check(fired == 1, "armed victory exit must invoke the observer exactly once");
        sts::g_onBattleExitPersistent = nullptr;
    }
    check(!sts::g_onBattleExitPersistent, "hook reset to null after use");

    if (failures == 0) { std::cout << "e2c_observer_scope PASS\n"; return 0; }
    std::cout << "e2c_observer_scope FAIL (" << failures << " cases)\n";
    return 1;
}

// The transition hook is a separate all-outcome RAW boundary.  The oracle
// path applies the captured persistent successor to an untouched copy and
// lets the native afterBattle continuation consume reward RNG exactly once.
int testCombatTransitionOracle() {
    using one_combat::CombatTransitionRawObserverScope;
    using one_combat::CombatTransitionRecord;
    using one_combat::applyCombatTransitionState;
    using one_combat::captureCombatTransition;
    using one_combat::combatTransitionFingerprint;
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };
    check(!sts::g_onBattleExitRaw, "RAW hook must be null by default (inert)");

    GameContext source(CharacterClass::IRONCLAD, 0xC0FFEEu, 0);
    source.screenState = ScreenState::BATTLE;
    source.curRoom = Room::MONSTER;
    source.info.encounter = MonsterEncounter::CULTIST;
    source.regainControlAction = [](GameContext &g) { g.afterBattle(); };
    source.curHp = 51;
    source.maxHp = 80;
    source.gold = 123;
    source.relics.add({RelicId::HAPPY_FLOWER, 1});

    GameContext actual = sts::test::cloneOocTestState(source);
    GameContext oracle = sts::test::cloneOocTestState(source);
    BattleContext bc;
    bc.init(actual, MonsterEncounter::CULTIST);
    bc.player.curHp = 23;
    bc.player.maxHp = 83;
    bc.player.gold = 177;
    bc.potionCapacity = 3;
    bc.potions[0] = Potion::FIRE_POTION;
    bc.potions[1] = Potion::EMPTY_POTION_SLOT;
    bc.smokeBombUsed = false;
    bc.outcome = Outcome::PLAYER_VICTORY;

    bool observed = false;
    CombatTransitionRecord record;
    {
        CombatTransitionRawObserverScope scope([&](const BattleContext &ended,
                                                     GameContext &raw) {
            check(!observed, "RAW hook fired more than once");
            observed = true;
            record = captureCombatTransition(source, ended, raw);
            check(raw.screenState == ScreenState::BATTLE,
                  "RAW hook ran after screen continuation");
            check(raw.outcome == GameOutcome::UNDECIDED,
                  "RAW hook saw a post-continuation GameOutcome");
        });
        bc.exitBattle(actual);
    }
    check(observed, "victory did not invoke RAW hook");
    check(!sts::g_onBattleExitRaw, "RAW hook was not restored after scope");
    check(actual.screenState == ScreenState::REWARDS,
          "native victory continuation did not reach rewards");

    applyCombatTransitionState(oracle, record.post);
    oracle.regainControl();
    check(sts::test::oocStateFingerprint(actual) == sts::test::oocStateFingerprint(oracle),
          "oracle persistent apply plus native continuation diverged");
    check(combatTransitionFingerprint(actual) == combatTransitionFingerprint(oracle),
          "oracle combat persistent/RNG fingerprint diverged");
    check(record.combatOutcome == Outcome::PLAYER_VICTORY,
          "recorded combat outcome is not victory");

    GameContext death = sts::test::cloneOocTestState(source);
    BattleContext losing;
    losing.init(death, MonsterEncounter::CULTIST);
    losing.player.curHp = 0;
    losing.outcome = Outcome::PLAYER_LOSS;
    int deathHooks = 0;
    {
        CombatTransitionRawObserverScope scope([&](const BattleContext &ended,
                                                     GameContext &raw) {
            ++deathHooks;
            check(ended.outcome == Outcome::PLAYER_LOSS,
                  "loss RAW hook did not expose combat loss");
            check(raw.outcome == GameOutcome::UNDECIDED,
                  "loss RAW hook ran after GameContext loss assignment");
        });
        losing.exitBattle(death);
    }
    check(deathHooks == 1, "true death did not invoke RAW hook exactly once");
    check(death.outcome == GameOutcome::PLAYER_LOSS,
          "native loss continuation changed outcome unexpectedly");

    if (failures == 0) { std::cout << "combat_transition_oracle PASS\n"; return 0; }
    std::cout << "combat_transition_oracle FAIL (" << failures << " cases)\n";
    return 1;
}

// The live draw vector is simulator-private. This test exercises the explicit
// observer metadata plus the converter boundary; it never gives that boundary
// a draw-pile index or any combat RNG state.
int testCombatKnowledgeBoundary() {
    using search::CombatKnowledgeEventType;
    int failures = 0;
    const auto check = [&failures](bool ok, const char *msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };
    const auto makeCards = [](BattleContext &bc) {
        CardInstance strike(CardId::STRIKE_RED), defend(CardId::DEFEND_RED), bash(CardId::BASH);
        strike.uniqueId = 11; defend.uniqueId = 12; bash.uniqueId = 13;
        bc.cards.drawPile = {strike, defend, bash}; // concrete order is intentionally secret
    };

    GameContext gc(CharacterClass::IRONCLAD, 0x51A7u, 0);
    BattleContext first;
    first.init(gc, MonsterEncounter::CULTIST);
    makeCards(first);
    BattleContext permuted = first;
    std::swap(permuted.cards.drawPile[0], permuted.cards.drawPile[2]);

    search::CombatKnowledgeState firstKnowledge, permutedKnowledge;
    firstKnowledge.initializeFromLiveBattle(first);
    permutedKnowledge.initializeFromLiveBattle(permuted);
    const auto firstView = search::makeSilverDrawPileObservation(first, firstKnowledge);
    const auto permutedView = search::makeSilverDrawPileObservation(permuted, permutedKnowledge);
    check(search::sameSilverDrawPileObservation(firstView, permutedView),
          "unobserved concrete draw permutations must produce the same Silver pile observation");
    check(firstView.knownTop.empty() && firstView.knownBottom.empty() && firstView.unknown.size() == 3,
          "normal conversion must keep every unpositioned card unknown");
    check(search::makeSilverCardPile(first, firstKnowledge)
          == search::makeSilverCardPile(permuted, permutedKnowledge),
          "unobserved concrete draw permutations must construct the same Silver CardPile");
    auto sampledUnknown = search::makeSilverCardPile(first, firstKnowledge);
    silver::Random silverRng(0x9001u);
    (void)sampledUnknown.drawTop(silverRng);
    check(silverRng.counter == 1,
          "Silver unknown draw must consume its isolated single-model RNG exactly once");

    // The six live RNG fields are deliberately not an input to conversion.
    BattleContext alteredRng = first;
    alteredRng.aiRng = Random(1); alteredRng.cardRandomRng = Random(2);
    alteredRng.miscRng = Random(3); alteredRng.monsterHpRng = Random(4);
    alteredRng.potionRng = Random(5); alteredRng.shuffleRng = Random(6);
    search::CombatKnowledgeState alteredRngKnowledge;
    alteredRngKnowledge.initializeFromLiveBattle(alteredRng);
    check(search::sameSilverDrawPileObservation(firstView,
          search::makeSilverDrawPileObservation(alteredRng, alteredRngKnowledge)),
          "live combat RNG changes must not change the Silver pile observation");

    // Known top: later placement is the next draw (back of knownTop).
    auto topKnowledge = firstKnowledge;
    const CardInstance topA = first.cards.drawPile[0];
    const CardInstance topB = first.cards.drawPile[1];
    topKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::KNOWN_TOP_PLACED, topA, true});
    topKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::KNOWN_TOP_PLACED, topB, true});
    BattleContext topLive = first;
    topLive.cards.drawPile = {first.cards.drawPile[2], topA, topB};
    const auto topView = search::makeSilverDrawPileObservation(topLive, topKnowledge);
    check(topView.knownTop.size() == 2 && topView.knownTop[0].uniqueId == topA.uniqueId
          && topView.knownTop[1].uniqueId == topB.uniqueId,
          "multiple known top placements must retain actual stack order");
    auto deterministicTop = search::makeSilverCardPile(topLive, topKnowledge);
    silver::Random knownTopRng(0x9002u);
    const CardInstance poppedTop = deterministicTop.drawTop(knownTopRng);
    check(poppedTop.uniqueId == topB.uniqueId && knownTopRng.counter == 0,
          "Silver known-top draw must be deterministic and consume no model RNG");
    topKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::DRAW_OCCURRED, topB, true});
    check(topKnowledge.knownTop.size() == 1 && topKnowledge.knownTop.back().uniqueId == topA.uniqueId,
          "drawing a known top card must pop only that card");

    // Known bottom: later placement is lower/deader-last (front of knownBottom).
    auto bottomKnowledge = firstKnowledge;
    bottomKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED, topA, true});
    bottomKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED, topB, true});
    check(bottomKnowledge.knownBottom.size() == 2 && bottomKnowledge.knownBottom[0].uniqueId == topB.uniqueId
          && bottomKnowledge.knownBottom[1].uniqueId == topA.uniqueId,
          "multiple known bottom placements must retain actual stack order");
    // There is one unknown card above the two known-bottom cards. Its draw
    // must not erase a bottom fact; only the later deterministic draw may.
    bottomKnowledge.observedDrawPileSize = 3;
    bottomKnowledge.observeCombatKnowledgeEvent(
        {CombatKnowledgeEventType::DRAW_OCCURRED, first.cards.drawPile[2], true});
    check(bottomKnowledge.knownBottom.size() == 2,
          "unknown-region draw must not consume known-bottom knowledge");
    bottomKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::DRAW_OCCURRED, topA, true});
    check(bottomKnowledge.knownBottom.size() == 1 && bottomKnowledge.knownBottom.back().uniqueId == topB.uniqueId,
          "known bottom must become deterministic only after unknown cards are gone");

    bottomKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::SHUFFLE_OCCURRED});
    check(bottomKnowledge.knownTop.empty() && bottomKnowledge.knownBottom.empty()
          && !bottomKnowledge.fullDrawPileOrderObserved,
          "ordinary shuffle must invalidate positional knowledge");
    topKnowledge.observeCombatKnowledgeEvent({CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT, topA, true});
    check(topKnowledge.knownTop.empty() && topKnowledge.knownBottom.empty(),
          "unknown insertion must conservatively erase position knowledge");

    // The default-null callback is behavior-neutral. Compare one actual live
    // top placement with and without an installed observer.
    BattleContext noObserver = first, withObserver = first;
    CardInstance moved = noObserver.cards.drawPile[0];
    search::g_combatKnowledgeObserver = nullptr;
    noObserver.cards.moveToDrawPileTop(moved);
    search::CombatKnowledgeState observed;
    observed.initializeFromLiveBattle(withObserver);
    search::g_combatKnowledgeObserver = &observed;
    withObserver.cards.moveToDrawPileTop(moved);
    search::g_combatKnowledgeObserver = nullptr;
    const bool sameLiveResult = noObserver.cards.drawPile.size() == withObserver.cards.drawPile.size()
        && noObserver.cards.cardsInHand == withObserver.cards.cardsInHand
        && noObserver.cards.drawPileBloodCardCount == withObserver.cards.drawPileBloodCardCount
        && std::equal(noObserver.cards.drawPile.begin(), noObserver.cards.drawPile.end(),
                      withObserver.cards.drawPile.begin(), [](const CardInstance &a, const CardInstance &b) {
                          return a.id == b.id && a.uniqueId == b.uniqueId && a.specialData == b.specialData
                              && a.cost == b.cost && a.costForTurn == b.costForTurn
                              && a.upgraded == b.upgraded && a.freeToPlayOnce == b.freeToPlayOnce
                              && a.retain == b.retain;
                      });
    check(sameLiveResult, "observer callback must not change live BattleContext behavior");
    check(observed.knownTop.size() == 1 && observed.knownTop.back().uniqueId == moved.uniqueId,
          "live top-placement hook must emit the selected card only");

    // Frozen Eye makes the concrete order observable; without it the preceding
    // permutations compared equal, while with it their order must be retained.
    GameContext eyeGc(CharacterClass::IRONCLAD, 0x51A8u, 0);
    eyeGc.obtainRelic(RelicId::FROZEN_EYE);
    BattleContext eyeA, eyeB;
    eyeA.init(eyeGc, MonsterEncounter::CULTIST);
    makeCards(eyeA);
    eyeB = eyeA;
    std::swap(eyeB.cards.drawPile[0], eyeB.cards.drawPile[2]);
    search::CombatKnowledgeState eyeAKnowledge, eyeBKnowledge;
    eyeAKnowledge.initializeFromLiveBattle(eyeA);
    eyeBKnowledge.initializeFromLiveBattle(eyeB);
    const auto eyeAView = search::makeSilverDrawPileObservation(eyeA, eyeAKnowledge);
    const auto eyeBView = search::makeSilverDrawPileObservation(eyeB, eyeBKnowledge);
    check(eyeAView.fullOrderObserved && eyeBView.fullOrderObserved,
          "Frozen Eye must explicitly mark full draw-order visibility");
    check(!search::sameSilverDrawPileObservation(eyeAView, eyeBView),
          "Frozen Eye conversion must preserve legitimately visible concrete order");
    check(!(search::makeSilverCardPile(eyeA, eyeAKnowledge)
          == search::makeSilverCardPile(eyeB, eyeBKnowledge)),
          "Frozen Eye must retain the actual visible order in Silver CardPile state");

    GameContext domeGc(CharacterClass::IRONCLAD, 0x51A9u, 0);
    domeGc.obtainRelic(RelicId::RUNIC_DOME);
    BattleContext dome;
    dome.init(domeGc, MonsterEncounter::CULTIST);
    check(!search::liveMonsterIntentIsObservable(dome),
          "Runic Dome must prohibit copying live monster intent into Silver");
    check(search::liveMonsterIntentIsObservable(first),
          "visible-intent combat must permit an intent conversion");

    if (failures == 0) { std::cout << "combat_knowledge PASS\n"; return 0; }
    std::cout << "combat_knowledge FAIL (" << failures << " cases)\n";
    return 1;
}

int testSilverRandomBridge() {
    const auto fromBridge = silver_bridge::probeReferenceRandom(0x51A9u);
    Random reference(0x51A9u);
    const auto first = reference.random(999);
    const auto second = reference.random(-3, 7);
    const auto third = reference.randomLong();
    const bool equal = fromBridge.firstRange == first && fromBridge.secondRange == second
        && fromBridge.randomLong == third && fromBridge.counter == reference.counter
        && fromBridge.seed0 == reference.seed0 && fromBridge.seed1 == reference.seed1;
    if (!equal) {
        std::cout << "silver_random_bridge FAIL\n";
        return 1;
    }
    std::cout << "silver_random_bridge PASS\n";
    return 0;
}

int testSilverSemanticActionResolution() {
    int failures = 0;
    const auto check = [&failures](bool ok, const char *msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };
    BattleContext bc = playerNormalFixture(0x5151u, 3);
    CardInstance strike(CardId::STRIKE_RED), defend(CardId::DEFEND_RED);
    strike.uniqueId = 71; defend.uniqueId = 72;
    bc.cards.cardsInHand = 2;
    bc.cards.hand[0] = strike;
    bc.cards.hand[1] = defend;
    bc.inputState = InputState::CARD_SELECT;
    bc.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    bc.cardSelectInfo.canPickAnyNumber = true;

    const auto wire = [](const CardInstance &c) {
        return silver_bridge::CardWire{static_cast<std::int16_t>(c.id), c.uniqueId, c.specialData,
                                       c.cost, c.costForTurn, c.upgraded, c.freeToPlayOnce, c.retain};
    };
    // Ordinary player actions: identities are values, never Silver indices.
    BattleContext normal = playerNormalFixture(0x5152u, 3);
    for (int i = 0; i < normal.cards.cardsInHand; ++i) normal.cards.hand[i].uniqueId = static_cast<std::int16_t>(100 + i);
    silver_bridge::SemanticAction cardPlay;
    cardPlay.type = silver_bridge::SemanticActionType::CARD;
    cardPlay.source = silver_bridge::CardSource::HAND;
    cardPlay.card = wire(normal.cards.hand[0]);
    cardPlay.target = 0;
    auto normalResolved = search::resolveSilverSemanticAction(normal, cardPlay);
    check(normalResolved.ok && normalResolved.action.getActionType() == search::ActionType::CARD
          && normalResolved.action.getSourceIdx() == 0 && normalResolved.action.getTargetIdx() == 0,
          "targeted semantic card play must lower to the matching legal live action");
    normal.cards.hand[1] = normal.cards.hand[0];
    normal.cards.cardsInHand = 2;
    normalResolved = search::resolveSilverSemanticAction(normal, cardPlay);
    check(normalResolved.ok && normalResolved.action.getActionType() == search::ActionType::CARD
          && normalResolved.action.getSourceIdx() == 0,
          "indistinguishable duplicate hand cards must lower deterministically for ordinary play");
    // The bridge exports absent targets as -1, whereas native Action stores
    // an unsigned packed target and uses zero for untargeted plays.
    auto untargeted = normal;
    untargeted.cards.cardsInHand = 1;
    untargeted.cards.hand[0] = defend;
    auto defendPlay = cardPlay;
    defendPlay.card = wire(defend);
    defendPlay.target = -1;
    const auto loweredDefend = search::resolveSilverSemanticAction(untargeted, defendPlay);
    check(loweredDefend.ok
          && loweredDefend.action == search::Action(search::ActionType::CARD, 0),
          "absent semantic card target must lower to canonical native untargeted action");
    if (loweredDefend.ok) {
        auto actual = untargeted, expected = untargeted;
        loweredDefend.action.execute(actual);
        search::Action(search::ActionType::CARD, 0).execute(expected);
        check(actual.player.block == expected.player.block && actual.player.block > untargeted.player.block
              && actual.player.energy == expected.player.energy,
              "lowered untargeted card must execute native block and energy effects");
    }
    auto invalidTargetedCard = cardPlay; invalidTargetedCard.target = -1;
    check(!search::resolveSilverSemanticAction(normal, invalidTargetedCard).ok,
          "targeted card with absent semantic target must fail closed");
    silver_bridge::SemanticAction end; end.type = silver_bridge::SemanticActionType::END_TURN;
    check(search::resolveSilverSemanticAction(normal, end).ok,
          "semantic END_TURN must lower to a legal live action");
    silver_bridge::SemanticAction fire;
    fire.type = silver_bridge::SemanticActionType::POTION; fire.potionSlot = 0;
    fire.potionId = static_cast<std::int16_t>(normal.potions[0]); fire.target = 0;
    check(search::resolveSilverSemanticAction(normal, fire).ok,
          "targeted semantic potion must lower to a legal live action");
    fire.discardPotion = true;
    check(search::resolveSilverSemanticAction(normal, fire).ok,
          "semantic potion discard must lower to a legal live action");

    auto strengthState = normal;
    strengthState.potions[0] = Potion::STRENGTH_POTION;
    auto strength = fire;
    strength.potionId = static_cast<std::int16_t>(Potion::STRENGTH_POTION);
    strength.target = -1; strength.discardPotion = false;
    const auto loweredStrength = search::resolveSilverSemanticAction(strengthState, strength);
    check(loweredStrength.ok
          && loweredStrength.action == search::Action(search::ActionType::POTION, 0),
          "absent semantic potion target must mean use rather than packed discard");
    if (loweredStrength.ok) {
        const auto beforeStrength = strengthState.player.getStatus<PlayerStatus::STRENGTH>();
        loweredStrength.action.execute(strengthState);
        check(strengthState.player.getStatus<PlayerStatus::STRENGTH>() == beforeStrength + 2
              && strengthState.potions[0] == Potion::EMPTY_POTION_SLOT,
              "untargeted potion must apply its effect before consuming the slot");
    }
    for (int invalidTarget : {-1, 5, 6, 8192}) {
        auto invalidPotion = fire; invalidPotion.discardPotion = false; invalidPotion.target = invalidTarget;
        check(!search::resolveSilverSemanticAction(normal, invalidPotion).ok,
              "targeted potion invalid target must not alias discard or a packed target");
    }
    auto explicitDiscardState = normal;
    explicitDiscardState.potions[0] = Potion::STRENGTH_POTION;
    strength.discardPotion = true;
    const auto loweredDiscard = search::resolveSilverSemanticAction(explicitDiscardState, strength);
    check(loweredDiscard.ok && loweredDiscard.action.getTargetIdx() == 6,
          "explicit semantic discard must retain native discard encoding");

    const auto selectCase = [&](CardSelectTask task, silver_bridge::CardSource source, const CardInstance &chosen,
                                const char *message) {
        BattleContext select = cardSelectFixture(task, 1, false);
        for (int i = 0; i < select.cards.cardsInHand; ++i) select.cards.hand[i].uniqueId = static_cast<std::int16_t>(200 + i);
        for (int i = 0; i < static_cast<int>(select.cards.drawPile.size()); ++i) select.cards.drawPile[i].uniqueId = static_cast<std::int16_t>(300 + i);
        for (int i = 0; i < static_cast<int>(select.cards.discardPile.size()); ++i) select.cards.discardPile[i].uniqueId = static_cast<std::int16_t>(400 + i);
        for (int i = 0; i < static_cast<int>(select.cards.exhaustPile.size()); ++i) select.cards.exhaustPile[i].uniqueId = static_cast<std::int16_t>(500 + i);
        CardInstance actual = chosen;
        if (source == silver_bridge::CardSource::HAND) actual = select.cards.hand[0];
        if (source == silver_bridge::CardSource::DRAW) actual = select.cards.drawPile[0];
        if (source == silver_bridge::CardSource::DISCARD) actual = select.cards.discardPile[0];
        if (source == silver_bridge::CardSource::EXHAUST) actual = select.cards.exhaustPile[1];
        silver_bridge::SemanticAction semantic;
        semantic.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
        semantic.source = source; semantic.card = wire(actual);
        semantic.cardSelectTask = static_cast<std::int16_t>(task);
        check(search::resolveSilverSemanticAction(select, semantic).ok, message);
    };
    selectCase(CardSelectTask::EXHAUST_ONE, silver_bridge::CardSource::HAND, {},
               "hand single-card-select must lower by visible instance identity");
    selectCase(CardSelectTask::HEADBUTT, silver_bridge::CardSource::DISCARD, {},
               "discard single-card-select must lower by visible instance identity");
    selectCase(CardSelectTask::EXHUME, silver_bridge::CardSource::EXHAUST, {},
               "exhaust single-card-select must lower by visible instance identity");
    selectCase(CardSelectTask::SEEK, silver_bridge::CardSource::DRAW, {},
               "draw-pile single-card-select must lower by visible instance identity");

    BattleContext duplicateDiscard = cardSelectFixture(CardSelectTask::HEADBUTT, 1, false);
    duplicateDiscard.cards.discardPile[1] = duplicateDiscard.cards.discardPile[0];
    silver_bridge::SemanticAction duplicateDiscardSelection;
    duplicateDiscardSelection.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
    duplicateDiscardSelection.source = silver_bridge::CardSource::DISCARD;
    duplicateDiscardSelection.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::HEADBUTT);
    duplicateDiscardSelection.card = wire(duplicateDiscard.cards.discardPile[0]);
    auto duplicateDiscardResolved =
        search::resolveSilverSemanticAction(duplicateDiscard, duplicateDiscardSelection);
    check(duplicateDiscardResolved.ok && duplicateDiscardResolved.action.getSourceIdx() == 0,
          "duplicate discard identity must lower deterministically for a single-card select");

    BattleContext discovery = cardSelectFixture(CardSelectTask::DISCOVERY, 1, false);
    discovery.cardSelectInfo.cards = {CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::BASH};
    silver_bridge::SemanticAction offer;
    offer.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
    offer.source = silver_bridge::CardSource::CARD_SELECT_OPTION;
    offer.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::DISCOVERY);
    offer.optionCardId = static_cast<std::int16_t>(CardId::DEFEND_RED);
    check(search::resolveSilverSemanticAction(discovery, offer).ok,
          "Discovery offer must lower by offered card identity");
    BattleContext codex = cardSelectFixture(CardSelectTask::CODEX, 1, false);
    silver_bridge::SemanticAction skip;
    skip.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
    skip.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::CODEX);
    skip.skipCardSelect = true;
    check(search::resolveSilverSemanticAction(codex, skip).ok,
          "Codex skip must lower to its live-valid explicit skip action");
    silver_bridge::SemanticAction selection;
    selection.type = silver_bridge::SemanticActionType::MULTI_CARD_SELECT;
    selection.source = silver_bridge::CardSource::HAND;
    selection.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::GAMBLE);
    selection.selectedCards = {wire(defend)};
    auto resolved = search::resolveSilverSemanticAction(bc, selection);
    check(resolved.ok && resolved.action.getActionType() == search::ActionType::MULTI_CARD_SELECT
          && resolved.action.getSelectedIdxs().size() == 1 && resolved.action.getSelectedIdxs()[0] == 1,
          "semantic multi-select must resolve its visible card identity to a legal live subset");

    std::swap(bc.cards.hand[0], bc.cards.hand[1]);
    resolved = search::resolveSilverSemanticAction(bc, selection);
    check(resolved.ok && resolved.action.getSelectedIdxs().size() == 1
          && resolved.action.getSelectedIdxs()[0] == 0,
          "hand-vector permutation must not change semantic selected-card identity");

    // Multi-select must reject a malformed duplicate visible identity instead
    // of using the first hidden vector index. Real card instances have distinct
    // uids; single-card selection intentionally chooses the first equivalent
    // live entry.
    bc.cards.hand[1] = bc.cards.hand[0];
    selection.selectedCards = {wire(bc.cards.hand[0])};
    resolved = search::resolveSilverSemanticAction(bc, selection);
    check(!resolved.ok && !resolved.error.empty(),
          "ambiguous semantic card identity must fail closed");

    selection.selectedCards = {wire(strike)};
    resolved = search::resolveSilverSemanticAction(bc, selection);
    check(!resolved.ok && !resolved.error.empty(),
          "missing semantic card identity must fail closed");

    if (failures == 0) { std::cout << "silver_semantic_action PASS\n"; return 0; }
    std::cout << "silver_semantic_action FAIL (" << failures << " cases)\n";
    return 1;
}

static int compareEnumerator(const char *label, const std::vector<std::uint32_t> &truth,
                             std::vector<std::uint32_t> got) {
    std::sort(got.begin(), got.end());
    got.erase(std::unique(got.begin(), got.end()), got.end());
    std::vector<std::uint32_t> missing, extra;
    std::set_difference(truth.begin(), truth.end(), got.begin(), got.end(),
                        std::back_inserter(missing));
    std::set_difference(got.begin(), got.end(), truth.begin(), truth.end(),
                        std::back_inserter(extra));
    if (missing.empty() && extra.empty()) return 0;
    std::cout << "    " << label << ": MISMATCH (truth " << truth.size() << ", got "
              << got.size() << "): missing " << missing.size() << ", extra " << extra.size() << '\n';
    return 1;
}

int testCardSelectParity() {
    int failures = 0;

    // The parity test pins the full validity contract (`all`): restricted
    // deployment modes intentionally prune the action space, so they must
    // not leak into this check via STS_MULTISELECT_MODE.
    setenv("STS_MULTISELECT_MODE", "all", 1);

    std::cout << "cardselect_parity: CARD_SELECT tasks\n";
    for (int t = 0; t <= (int)CardSelectTask::WARCRY; ++t) {
        const auto task = (CardSelectTask)t;
        const std::string name = cardSelectTaskStrings[t];
        const int pickCounts[] = {0, 2};
        for (int pickCount : pickCounts) {
            const BattleContext bc = cardSelectFixture(task, pickCount, false);
            const auto truth = cardSelectGroundTruth(bc);
            for (auto b : truth) {
                const auto at = search::Action(b).getActionType();
                if (at != search::ActionType::SINGLE_CARD_SELECT
                    && at != search::ActionType::MULTI_CARD_SELECT) {
                    std::cout << "    " << name << ": ground truth contains non-select action type "
                              << (int)at << '\n';
                    ++failures;
                    break;
                }
            }
            std::vector<std::uint32_t> canonical;
            for (const auto &a : search::Action::enumerateCardSelectActions(bc)) canonical.push_back(a.bits);
            search::BattleScumSearcher2 s2(bc);
            search::BattleScumSearcher2::Node n2;
            s2.enumerateCardSelectActions(n2, bc);
            std::vector<std::uint32_t> s2Actions;
            for (const auto &e : n2.edges) s2Actions.push_back(e.action.bits);
            search::BattleScumSearcher3::Node n3;
            search::enumerateActionsForNode(n3, bc);
            std::vector<std::uint32_t> s3Actions;
            for (const auto &e : n3.edges) s3Actions.push_back(e.action.bits);

            const bool cOk = compareEnumerator("canonical", truth, canonical) == 0;
            const bool s2Ok = compareEnumerator("s2", truth, s2Actions) == 0;
            const bool s3Ok = compareEnumerator("s3", truth, s3Actions) == 0;
            if (!cOk || !s2Ok || !s3Ok) {
                ++failures;
                std::cout << "  " << name << " (pickCount=" << pickCount << "): "
                          << (cOk ? "canonical OK" : "canonical FAIL")
                          << " " << (s2Ok ? "s2 OK" : "s2 FAIL")
                          << " " << (s3Ok ? "s3 OK" : "s3 FAIL") << '\n';
            }
        }
        {
            const BattleContext bc = cardSelectFixture(task, 10, true);
            const auto truth = cardSelectGroundTruth(bc);
            std::vector<std::uint32_t> canonical;
            for (const auto &a : search::Action::enumerateCardSelectActions(bc)) canonical.push_back(a.bits);
            search::BattleScumSearcher2 s2(bc);
            search::BattleScumSearcher2::Node n2;
            s2.enumerateCardSelectActions(n2, bc);
            std::vector<std::uint32_t> s2Actions;
            for (const auto &e : n2.edges) s2Actions.push_back(e.action.bits);
            search::BattleScumSearcher3::Node n3;
            search::enumerateActionsForNode(n3, bc);
            std::vector<std::uint32_t> s3Actions;
            for (const auto &e : n3.edges) s3Actions.push_back(e.action.bits);
            const bool cOk = compareEnumerator("canonical", truth, canonical) == 0;
            const bool s2Ok = compareEnumerator("s2", truth, s2Actions) == 0;
            const bool s3Ok = compareEnumerator("s3", truth, s3Actions) == 0;
            if (!cOk || !s2Ok || !s3Ok) {
                ++failures;
                std::cout << "  " << name << " (large hand): "
                          << (cOk ? "canonical OK" : "canonical FAIL")
                          << " " << (s2Ok ? "s2 OK" : "s2 FAIL")
                          << " " << (s3Ok ? "s3 OK" : "s3 FAIL") << '\n';
            }
        }
    }

    std::cout << "cardselect_parity: PLAYER_NORMAL\n";
    for (std::uint64_t seed : {0x1111u, 0x2222u}) {
        const BattleContext bc = playerNormalFixture(seed, 3);
        const auto truth = playerNormalGroundTruth(bc);
        search::BattleScumSearcher2 s2(bc);
        search::BattleScumSearcher2::Node n2;
        s2.enumerateActionsForNode(n2, bc);
        std::vector<std::uint32_t> s2Actions;
        for (const auto &e : n2.edges) s2Actions.push_back(e.action.bits);
        search::BattleScumSearcher3::Node n3;
        search::enumerateActionsForNode(n3, bc);
        std::vector<std::uint32_t> s3Actions;
        for (const auto &e : n3.edges) s3Actions.push_back(e.action.bits);
        if (compareEnumerator("s2", truth, s2Actions) != 0 || compareEnumerator("s3", truth, s3Actions) != 0) {
            ++failures;
            std::cout << "  player_normal energy=3 seed=" << seed << ": FAIL\n";
        }
    }
    {
        const BattleContext bc = playerNormalFixture(0x3333u, 0);
        const auto truth = playerNormalGroundTruth(bc);
        search::BattleScumSearcher2 s2(bc);
        search::BattleScumSearcher2::Node n2;
        s2.enumerateActionsForNode(n2, bc);
        std::vector<std::uint32_t> s2Actions;
        for (const auto &e : n2.edges) s2Actions.push_back(e.action.bits);
        search::BattleScumSearcher3::Node n3;
        search::enumerateActionsForNode(n3, bc);
        std::vector<std::uint32_t> s3Actions;
        for (const auto &e : n3.edges) s3Actions.push_back(e.action.bits);
        if (compareEnumerator("s2", truth, s2Actions) != 0 || compareEnumerator("s3", truth, s3Actions) != 0) {
            ++failures;
            std::cout << "  player_normal energy=0: FAIL\n";
        }
    }

    if (failures == 0) {
        std::cout << "cardselect_parity PASS\n";
        return 0;
    }
    std::cout << "cardselect_parity FAIL (" << failures << " states)\n";
    return 1;
}

// Regression (BattleScumSearcher2 non-fair empty-edge guard): a deterministic
// (non-fair) enumeration that yields zero legal actions must resolve as a
// direct leaf evaluation instead of reaching selectFirstActionForLeafNode's
// uniform_int_distribution(0,-1) (UB/assert). The zero-option state below is
// artificial -- PLAYER_NORMAL always adds END_TURN -- but a future enumerator
// change could produce it, and fair mode already defends the same way.
int testScumNonFairEmptyEdges() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    // CARD_SELECT with no selectable options: SECRET_WEAPON picks attacks from
    // the draw pile; an all-skill draw pile leaves zero legal actions.
    BattleContext bc = cardSelectFixture(CardSelectTask::SECRET_WEAPON, 1, false);
    bc.cards.drawPile.clear();
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));

    check(search::Action::enumerateCardSelectActions(bc).empty(),
          "fixture should have zero selectable options");

    search::BattleScumSearcher2 s2(bc);

    // playoutRandom: stop softly with NO_LEGAL_ACTION instead of asserting.
    {
        BattleContext rollState = bc;
        std::vector<search::Action> stack;
        search::RolloutStop stop = search::RolloutStop::TERMINAL;
        s2.playoutRandom(rollState, stack, stop);
        check(stop == search::RolloutStop::NO_LEGAL_ACTION,
              "rollout should stop with NO_LEGAL_ACTION, got " + std::to_string(static_cast<int>(stop)));
        check(stack.empty(), "rollout should not execute any action");
    }

    // step(): every simulation resolves as a direct leaf evaluation (no
    // rollout; the node is recorded as a defeat).
    s2.search(8);
    check(s2.diag.consistent(),
          "diagnostics invariant simulations == terminalInsideTree + rolloutCalls + leafDirectEval");
    check(s2.diag.simulations == 8,
          "expected 8 simulations, got " + std::to_string(s2.diag.simulations));
    check(s2.diag.leafDirectEval == 8,
          "expected all 8 simulations as direct leaf evals, got " + std::to_string(s2.diag.leafDirectEval));
    check(s2.diag.rolloutCalls == 0,
          "no rollout should run, got " + std::to_string(s2.diag.rolloutCalls));
    check(s2.root.outcome == 2,
          "no-legal-action node should be marked a defeat (2), got " + std::to_string(static_cast<int>(s2.root.outcome)));

    if (failures == 0) {
        std::cout << "scum_nonfair_empty_edges PASS\n";
        return 0;
    }
    std::cout << "scum_nonfair_empty_edges FAIL (" << failures << " cases)\n";
    return 1;
}

// Regression (issue #54 + #70, BattleScumSearcher2): (a) searchToTotalRootStable
// must not hang when STS_CONV_ROOT_START=0 or STS_CONV_ROOT_GROW<=1.0 -- a
// zero-growth budget makes the chunk loop run 0 steps, so the outer loop must
// force the full budget instead of spinning forever; (b) step() must clear a
// stale terminal outcome when re-expanding a node that was terminal in another
// world (fair-mode determinization), preserving "outcome != 0 implies
// edges.empty()" so collectFrontierStats does not misclassify the node.
int testScumConvRootStaleOutcome() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    // --- issue #54: zero-growth budget must still reach the target ----------
    const std::int64_t savedStart = search::g_convRootStart;
    const double savedGrow = search::g_convRootGrow;
    {
        // start == 0: budget never grows; without the guard the outer loop spins.
        search::g_convRootStart = 0;
        search::g_convRootGrow = 2.0;
        {
            BattleContext bc = playerNormalFixture(0x51u, 3);
            search::BattleScumSearcher2 s2(bc);
            s2.searchToTotalRootStable(16, 0, 1000000);   // patience huge -> no early stop
            check(s2.root.simulationCount >= 16,
                  "convroot start=0: expected >=16 sims, got " + std::to_string(s2.root.simulationCount));
        }
        // grow == 1.0: chunkEnd == budget after the first round; without the
        // guard the outer loop spins once the budget stops growing.
        search::g_convRootStart = 8;
        search::g_convRootGrow = 1.0;
        {
            BattleContext bc = playerNormalFixture(0x52u, 3);
            search::BattleScumSearcher2 s2(bc);
            s2.searchToTotalRootStable(16, 0, 1000000);
            check(s2.root.simulationCount >= 16,
                  "convroot grow=1.0: expected >=16 sims, got " + std::to_string(s2.root.simulationCount));
        }
    }
    search::g_convRootStart = savedStart;
    search::g_convRootGrow = savedGrow;

    // --- issue #70: re-expansion clears a stale terminal outcome ------------
    {
        BattleContext bc = playerNormalFixture(0x53u, 3);
        search::BattleScumSearcher2 s2(bc);
        // Simulate a node that was terminal (victory, outcome=1, no edges) in a
        // previous world and is now reached in a non-terminal world: step() must
        // clear the stale outcome when re-enumerating edges.
        s2.root.outcome = 1;
        s2.step();
        check(s2.root.outcome == 0,
              "stale-outcome re-expansion: expected outcome reset to 0 (UNDECIDED), got "
                  + std::to_string(static_cast<int>(s2.root.outcome)));
        check(!s2.root.edges.empty(),
              "stale-outcome re-expansion: expected edges re-enumerated");
        check(s2.root.outcome == 0 || s2.root.edges.empty(),
              "stale-outcome re-expansion: invariant 'outcome != 0 implies edges.empty()' violated");
    }

    if (failures == 0) {
        std::cout << "scum_convroot_stale_outcome PASS\n";
        return 0;
    }
    std::cout << "scum_convroot_stale_outcome FAIL (" << failures << " cases)\n";
    return 1;
}

// ---- CARD_SELECT multi-select mask canonicalization -------------------------
// With STS_MULTISELECT_CANONICAL=1, masks that select the same multiset of
// identical hand cards collapse to the first-encountered mask; masks whose
// selected cards differ in any identity-relevant field (upgrade, costForTurn,
// freeToPlayOnce, specialData) must all remain. The oracle below is an
// independent reimplementation of the key; the hardcoded expected counts pin
// the contract even if oracle and implementation share a bug.

namespace {
// Test-local reimplementation of Action.cpp's cardIdentityKey (must stay in
// sync: (id, upgradeCount, costForTurn, freeToPlayOnce, specialData)).
std::uint64_t testCardKey(const CardInstance &c) {
    std::uint64_t k = static_cast<std::uint64_t>(static_cast<std::uint16_t>(c.getId()));
    k |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.getUpgradeCount())) << 16;
    k |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.costForTurn)) << 24;
    k |= static_cast<std::uint64_t>(c.freeToPlayOnce ? 1u : 0u) << 32;
    k |= static_cast<std::uint64_t>(static_cast<std::uint16_t>(c.specialData)) << 33;
    return k;
}
}

// Canonical ground truth: the full validity contract (every valid mask),
// deduped by selected-card multiset key keeping the first (smallest) mask.
static std::vector<std::uint32_t> canonicalGroundTruth(const BattleContext &bc) {
    std::set<std::uint32_t> result;
    std::set<std::vector<std::uint64_t>> seen;
    const int n = bc.cards.cardsInHand;
    if (n <= 0 || n > 10) return {};
    for (std::uint32_t mask = 0; mask < (1u << n); ++mask) {
        const search::Action a(search::ActionType::MULTI_CARD_SELECT, (int)mask);
        if (!a.isValidAction(bc)) continue;
        std::vector<std::uint64_t> key;
        for (int idx : a.getSelectedIdxs()) key.push_back(testCardKey(bc.cards.hand[idx]));
        std::sort(key.begin(), key.end());
        if (seen.insert(std::move(key)).second) result.insert(a.bits);
    }
    return std::vector<std::uint32_t>(result.begin(), result.end());
}

static BattleContext gambleFixture(const CardInstance *handCards, int n) {
    GameContext gc(CharacterClass::IRONCLAD, 0xBEEFu, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.cards.cardsInHand = n;
    for (int i = 0; i < n; ++i) bc.cards.hand[i] = handCards[i];
    bc.inputState = InputState::CARD_SELECT;
    bc.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    return bc;
}

int testCardSelectCanonical() {
    setenv("STS_MULTISELECT_MODE", "all", 1);
    setenv("STS_MULTISELECT_CANONICAL", "1", 1);

    int failures = 0;
    std::cout << "cardselect_canonical: GAMBLE mask canonicalization\n";

    // 3 identical Strikes + 3 identical Defends + 4 distinct cards (10-card
    // hand): full contract 2^10 = 1024 masks; canonical = 4*4*16 = 256.
    const CardInstance A[] = {
        CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::DEFEND_RED), CardInstance(CardId::DEFEND_RED), CardInstance(CardId::DEFEND_RED),
        CardInstance(CardId::BASH), CardInstance(CardId::CLOTHESLINE),
        CardInstance(CardId::IRON_WAVE), CardInstance(CardId::POMMEL_STRIKE),
    };
    const BattleContext bcA = gambleFixture(A, 10);
    std::vector<std::uint32_t> gotA;
    for (const auto &a : search::Action::enumerateCardSelectActions(bcA)) gotA.push_back(a.bits);
    if (gotA.size() != 256) {
        std::cout << "    duplicate-heavy GAMBLE: expected 256 canonical masks, got " << gotA.size() << '\n';
        ++failures;
    }
    if (compareEnumerator("duplicate-heavy GAMBLE vs canonical oracle", canonicalGroundTruth(bcA), gotA) != 0) {
        ++failures;
    }

    // 10 identical Strikes: full contract 1023 non-empty masks; canonical = 11.
    const CardInstance C[] = {
        CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED), CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED),
    };
    const BattleContext bcC = gambleFixture(C, 10);
    std::vector<std::uint32_t> gotC;
    for (const auto &a : search::Action::enumerateCardSelectActions(bcC)) gotC.push_back(a.bits);
    // Masks are encoded as MULTI_CARD_SELECT actions: bits = (type<<29)|mask.
    const auto enc = [](int mask) { return search::Action(search::ActionType::MULTI_CARD_SELECT, mask).bits; };
    const std::vector<std::uint32_t> expectC = {enc(0), enc(1), enc(3), enc(7), enc(15), enc(31), enc(63), enc(127), enc(255), enc(511), enc(1023)};
    if (compareEnumerator("10 identical Strikes", expectC, gotC) != 0) {
        ++failures;
    }

    // Upgraded copies are distinct effects: hand [Strike, Strike, Strike+,
    // Defend] must keep {0,1} (two normal) and {0,2} (normal + upgraded)
    // as separate actions; {1,2} collapses into {0,2}.
    const CardInstance B[] = {
        CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED),
        CardInstance(CardId::STRIKE_RED, true),
        CardInstance(CardId::DEFEND_RED),
    };
    const BattleContext bcB = gambleFixture(B, 4);
    std::vector<std::uint32_t> gotB;
    for (const auto &a : search::Action::enumerateCardSelectActions(bcB)) gotB.push_back(a.bits);
    const std::vector<std::uint32_t> expectB = {enc(0), enc(1), enc(3), enc(4), enc(5), enc(7), enc(8), enc(9), enc(11), enc(12), enc(13), enc(15)};
    if (compareEnumerator("upgraded-copy GAMBLE", expectB, gotB) != 0) {
        ++failures;
    }

    if (failures == 0) {
        std::cout << "cardselect_canonical PASS (1024->256, 1023->11, upgraded copies distinct)\n";
        return 0;
    }
    std::cout << "cardselect_canonical FAIL (" << failures << " checks)\n";
    return 1;
}


int mcts(int argc, const char *argv[]) {
    const auto saveFilePath = argv[2];
    const auto simulationCount = std::stoll(argv[3]);

    SaveFile saveFile = SaveFile::loadFromPath(saveFilePath, sts::CharacterClass::IRONCLAD);
    GameContext gc;
    gc.initFromSave(saveFile);

    std::cout << SeedHelper::getString(gc.seed) << std::endl;

    BattleContext bc = BattleContext();
    bc.init(gc);

    search::BattleScumSearcher2 searcher(bc);

    auto startTime = std::chrono::high_resolution_clock::now();
    searcher.search(simulationCount);
    auto endTime = std::chrono::high_resolution_clock::now();
    double duration = std::chrono::duration<double>(endTime-startTime).count();

    std::cout << "steps: " << simulationCount << " search time: " << duration << "s\n";
    std::cout << "best search value: " << searcher.bestActionValue << " depth: " << searcher.bestActionSequence.size() << '\n';
    if (searcher.bestActionSequence.empty()) {
        std::cout << "bestActionSequenceIsEmpty" << std::endl;
        return 0;
    }

    for (auto bestAction : searcher.bestActionSequence) {
        bestAction.printDesc(std::cout, bc) << '\n';
        bestAction.execute(bc);
    }

    std::cout << "ending hp: " << bc.player.curHp << '\n';

    searcher.printSearchTree(std::cout, 3);

    std::cout.flush();
    return 0;
}

// BattleContext binary round-trip contract. The serializer captures the visible
// state + 6 RNG streams (skipping the transient ActionQueue/CardQueue and
// execution flags), and the round-trip correctness contract is
// combatExtractFeatures identity:
//   combatExtractFeatures(bc) == combatExtractFeatures(deserialize(serialize(bc)))
// Byte-for-byte feature equality plus RNG-stream equality across multiple
// seeds, encounters, and several executed turns of play.
int testBattleContextRoundtrip() {
    search::g_richCombatFeatures = true;   // the 1766-feature rich path
    const MonsterEncounter encounters[] = {
        MonsterEncounter::JAW_WORM, MonsterEncounter::CULTIST,
        MonsterEncounter::GREMLIN_NOB, MonsterEncounter::SLIME_BOSS,
    };
    const int nf = search::combatFeatureCount();
    int failures = 0;
    for (std::uint64_t seed = 0; seed < 4; ++seed) {
        for (MonsterEncounter enc : encounters) {
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            BattleContext bc;
            bc.init(gc, enc);
            // Execute several turns of random legal play (cards + END_TURN,
            // card-select actions included) so the round-trip is exercised on
            // a non-trivial, action-advanced state.
            std::mt19937 rng(seed * 2654435761u + (std::uint32_t)enc + 1);
            int guard = 0;
            while (bc.outcome == Outcome::UNDECIDED && bc.turn < 3 && guard++ < 300) {
                search::BattleScumSearcher3::Node tmp;
                search::enumerateActionsForNode(tmp, bc);
                if (tmp.edges.empty()) break;
                const auto &a = tmp.edges[rng() % tmp.edges.size()].action;
                if (!a.isValidAction(bc)) break;
                a.execute(bc);
            }

            const std::vector<std::uint8_t> bytes = sts::serializeBattleContext(bc);
            const BattleContext restored =
                sts::deserializeBattleContext(bytes.data(), bytes.size());

            std::vector<float> f1(nf), f2(nf);
            search::combatExtractFeatures(bc, f1.data());
            search::combatExtractFeatures(restored, f2.data());
            bool same = true;
            int badIdx = -1;
            for (int i = 0; i < nf; ++i) {
                if (f1[i] != f2[i]) { same = false; badIdx = i; break; }
            }
            const bool stateSame = bc.inputState == restored.inputState
                && bc.turn == restored.turn && bc.player.curHp == restored.player.curHp
                && bc.cards.cardsInHand == restored.cards.cardsInHand
                && (int)bc.cards.drawPile.size() == (int)restored.cards.drawPile.size()
                && bc.cardSelectInfo.cardSelectTask == restored.cardSelectInfo.cardSelectTask;
            const bool rngSame = bc.aiRng.counter == restored.aiRng.counter
                && bc.aiRng.seed0 == restored.aiRng.seed0
                && bc.aiRng.seed1 == restored.aiRng.seed1
                && bc.cardRandomRng.counter == restored.cardRandomRng.counter
                && bc.cardRandomRng.seed0 == restored.cardRandomRng.seed0
                && bc.cardRandomRng.seed1 == restored.cardRandomRng.seed1
                && bc.miscRng.counter == restored.miscRng.counter
                && bc.miscRng.seed0 == restored.miscRng.seed0
                && bc.miscRng.seed1 == restored.miscRng.seed1
                && bc.monsterHpRng.counter == restored.monsterHpRng.counter
                && bc.monsterHpRng.seed0 == restored.monsterHpRng.seed0
                && bc.monsterHpRng.seed1 == restored.monsterHpRng.seed1
                && bc.potionRng.counter == restored.potionRng.counter
                && bc.potionRng.seed0 == restored.potionRng.seed0
                && bc.potionRng.seed1 == restored.potionRng.seed1
                && bc.shuffleRng.counter == restored.shuffleRng.counter
                && bc.shuffleRng.seed0 == restored.shuffleRng.seed0
                && bc.shuffleRng.seed1 == restored.shuffleRng.seed1;
            if (!same || !rngSame || !stateSame || restored.actionQueue.size != 0) {
                ++failures;
                std::cout << "battlecontext_roundtrip FAIL: seed " << seed
                          << " encounter " << monsterEncounterEnumNames[(int)enc]
                          << " turn " << bc.turn
                          << (same ? "" : " features differ at index " + std::to_string(badIdx))
                          << (rngSame ? "" : " RNG streams differ")
                          << (stateSame ? "" : " decision-state fields differ (inputState/turn/hp/hand/task)")
                          << (restored.actionQueue.size == 0 ? "" : " action queue non-empty")
                          << '\n';
            }
        }
    }
    if (failures == 0) {
        std::cout << "battlecontext_roundtrip PASS\n";
        return 0;
    }
    std::cout << "battlecontext_roundtrip FAIL (" << failures << " cases)\n";
    return 1;
}

// Simulator-health monitor: issue-87 regression. Empty-hand multi-select tasks
// have one canonical legal action: MULTI_CARD_SELECT mask=0. Executing it must
// resolve CARD_SELECT normally without producing a zero-progression diagnostic.
int testSimHealthGambleEmptyHand() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    const auto nlpBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION];
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::GAMBLE, 1, false);
        bc.cards.cardsInHand = 0;   // issue-87 shape: empty hand at GAMBLE
        const auto actions = search::Action::enumerateCardSelectActions(bc);
        check(actions.size() == 1, "empty-hand GAMBLE must enumerate one action");
        if (actions.size() == 1) {
            check(actions[0].getActionType() == search::ActionType::MULTI_CARD_SELECT,
                  "empty-hand GAMBLE action must be MULTI_CARD_SELECT");
            check(actions[0].getSelectedIdxs().empty(),
                  "empty-hand GAMBLE action must select no cards");
            check(actions[0].isValidAction(bc),
                  "empty-hand GAMBLE mask=0 must validate");
            actions[0].execute(bc);
            check(bc.inputState != InputState::CARD_SELECT,
                  "empty-hand GAMBLE execution must leave CARD_SELECT");
        }
    }
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::EXHAUST_MANY, 2, false);
        bc.cards.cardsInHand = 0;   // empty-hand multi-select regression
        const auto actions = search::Action::enumerateCardSelectActions(bc);
        check(actions.size() == 1, "empty-hand EXHAUST_MANY must enumerate one action");
        if (actions.size() == 1) {
            check(actions[0].getActionType() == search::ActionType::MULTI_CARD_SELECT,
                  "empty-hand EXHAUST_MANY action must be MULTI_CARD_SELECT");
            check(actions[0].getSelectedIdxs().empty(),
                  "empty-hand EXHAUST_MANY action must select no cards");
            check(actions[0].isValidAction(bc),
                  "empty-hand EXHAUST_MANY mask=0 must validate");
            actions[0].execute(bc);
            check(bc.inputState != InputState::CARD_SELECT,
                  "empty-hand EXHAUST_MANY execution must leave CARD_SELECT");
        }
    }
    const int nlpFired = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION] - nlpBefore;
    check(nlpFired == 0,
          "empty-hand GAMBLE must not fire NO_LEGAL_PROGRESSION (got "
          + std::to_string(nlpFired) + ")");

    if (failures == 0) {
        std::cout << "simhealth_gamble_empty_hand PASS\n";
        return 0;
    }
    std::cout << "simhealth_gamble_empty_hand FAIL (" << failures << " cases)\n";
    return 1;
}

// Gambler's Brew is not a legal PLAYER_NORMAL action when the hand is empty:
// using it would open GAMBLE with no selectable cards. A non-empty hand must
// retain the normal potion-use legality.
int testGamblersBrewLegality() {
    GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.inputState = InputState::PLAYER_NORMAL;
    bc.potions[0] = Potion::GAMBLERS_BREW;
    bc.potionCount = 1;
    const search::Action useBrew(search::ActionType::POTION, 0, 0);

    bc.cards.cardsInHand = 0;
    if (useBrew.isValidAction(bc)) {
        std::cout << "gamblers_brew_legality FAIL: empty-hand use was legal\n";
        return 1;
    }

    bc.cards.cardsInHand = 1;
    bc.cards.hand[0] = CardInstance(CardId::STRIKE_RED);
    if (!useBrew.isValidAction(bc)) {
        std::cout << "gamblers_brew_legality FAIL: non-empty-hand use was illegal\n";
        return 1;
    }

    std::cout << "gamblers_brew_legality PASS\n";
    return 0;
}

// Simulator-health monitor: non-fair Searcher2 coverage (Test B). A
// deterministic unresolved CARD_SELECT state with zero legal actions must be
// diagnosed immediately through the AGENT control path as NO_LEGAL_PROGRESSION
// instead of silently cycling to the 1000-decision stall guard (which
// converts the battle to PLAYER_LOSS with no health diagnostic). On baseline
// 9770856 this state degrades to a stall -> PLAYER_LOSS, so this test fails
// there. The state shape reuses testScumNonFairEmptyEdges (SECRET_WEAPON with
// an all-skill draw pile).
int testSimHealthNonFairS2Empty() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    const bool savedFair = search::g_fairPlay;
    const bool savedS3 = search::g_useSearcher3;
    search::g_fairPlay = false;    // non-fair (known-RNG) Searcher2
    search::g_useSearcher3 = false;

    const auto nlpBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION];
    BattleContext bc = cardSelectFixture(CardSelectTask::SECRET_WEAPON, 1, false);
    bc.cards.drawPile.clear();
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));   // no attacks -> zero selectable
    check(search::Action::enumerateCardSelectActions(bc).empty(),
          "fixture must have zero selectable actions");
    check(!search::hasLegalProgressionAction(bc),
          "canonical live action check must report zero legal actions");

    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = 1;   // keep the (futile) search cheap on baseline
    agent.playoutBattle(bc);

    const int nlpFired = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION] - nlpBefore;
    check(nlpFired >= 1,
          "non-fair S2 must report NO_LEGAL_PROGRESSION immediately (got "
          + std::to_string(nlpFired) + ")");
    // The battle must NOT have been converted by the stall guard: the monitor
    // breaks out of the loop while UNDECIDED instead of cycling to PLAYER_LOSS.
    check(bc.outcome == Outcome::UNDECIDED,
          "battle must exit UNDECIDED (not a stall-converted PLAYER_LOSS), got "
          + std::to_string((int)bc.outcome));

    search::g_fairPlay = savedFair;
    search::g_useSearcher3 = savedS3;

    if (failures == 0) {
        std::cout << "simhealth_nonfair_s2_empty PASS\n";
        return 0;
    }
    std::cout << "simhealth_nonfair_s2_empty FAIL (" << failures << " cases)\n";
    return 1;
}

// Simulator-health monitor: ACTION_SELECTION_FAILED classification (Test C).
// When canonical live actions exist but root/action selection fails, the
// monitor must classify the failure as ACTION_SELECTION_FAILED, not
// NO_LEGAL_PROGRESSION. This is the classification contract used at every S3
// root-selection failure site (e.g. g_s3Live=0 picking a stale invalid
// most-visited edge while other live actions remain legal) and at the fair-S2
// invalid-pick guard. The contract is unit-tested here on controlled states,
// plus the reporter/counter wiring for the new reason.
int testSimHealthSelectionFailure() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    // (a) Genuinely empty canonical action set -> NO_LEGAL_PROGRESSION.
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::SECRET_WEAPON, 1, false);
        bc.cards.drawPile.clear();
        bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));
        check(!search::hasLegalProgressionAction(bc),
              "empty SECRET_WEAPON options must have no legal progression action");
        check(search::classifySelectionFailure(bc) == search::SimHealthFailure::NO_LEGAL_PROGRESSION,
              "empty canonical set must classify as NO_LEGAL_PROGRESSION");
    }

    // (b) Legal live actions exist -> a selection failure must classify as
    //     ACTION_SELECTION_FAILED, and the per-reason counter must count it.
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::GAMBLE, 1, false);  // 5-card hand -> subsets
        check(search::hasLegalProgressionAction(bc),
              "GAMBLE with a 5-card hand must have legal progression actions");
        check(search::classifySelectionFailure(bc) == search::SimHealthFailure::ACTION_SELECTION_FAILED,
              "legal actions present + selection failure must classify as ACTION_SELECTION_FAILED");
        const int asfBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::ACTION_SELECTION_FAILED];
        const int totalBefore = search::g_simHealthFailureCount;
        search::reportSimHealthFailure(bc, search::SimHealthFailure::ACTION_SELECTION_FAILED);
        check(search::g_simHealthFailureCounts[(int)search::SimHealthFailure::ACTION_SELECTION_FAILED] == asfBefore + 1,
              "ACTION_SELECTION_FAILED must be countable by the per-reason counter");
        check(search::g_simHealthFailureCount == totalBefore + 1,
              "total failure counter must also increment");
    }

    // (c) PLAYER_NORMAL always has a legal progression action (END_TURN).
    {
        BattleContext bc = playerNormalFixture(12345, 3);
        check(search::hasLegalProgressionAction(bc),
              "PLAYER_NORMAL must always have a legal progression action (END_TURN)");
        check(search::classifySelectionFailure(bc) == search::SimHealthFailure::ACTION_SELECTION_FAILED,
              "PLAYER_NORMAL selection failure must classify as ACTION_SELECTION_FAILED");
    }

    // (d) A decided battle is not an agent decision boundary.
    {
        BattleContext bc = cardSelectFixture(CardSelectTask::GAMBLE, 1, false);
        bc.outcome = Outcome::PLAYER_VICTORY;
        check(!search::hasLegalProgressionAction(bc),
              "a decided battle must not report legal progression actions");
    }

    if (failures == 0) {
        std::cout << "simhealth_selection_failure PASS\n";
        return 0;
    }
    std::cout << "simhealth_selection_failure FAIL (" << failures << " cases)\n";
    return 1;
}

// Simulator-health monitor: non-fair S2 ACTION_SELECTION_FAILED through agent
// control path with positive bestOutcomePlayerHp (Test D). The earlier
// correction (312c358) closed the zero-edge case but left the
// empty-cached-solution branch silent: when bestOutcomePlayerHp > 0 (a
// previously found winning line) and stepThroughSolution with
// stepsWithSolution=0 commits zero actions, the agent loop would silently
// retry instead of firing a health diagnostic. The detection-only rule
// completes: every unresolved non-fair S2 decision with zero committed
// actions now reports NO_LEGAL_PROGRESSION or ACTION_SELECTION_FAILED
// immediately, governed by the canonical live action set.
//
// The regression forces the branch via stepsWithSolution=0 on a
// PLAYER_NORMAL fixture where search finds a positive-HP winning line;
// with the fix, classifySelectionFailure(bc) fires ACTION_SELECTION_FAILED
// (legal live actions exist) followed by UNDECIDED_BATTLE_EXIT, and the
// 1000-decision stall guard never fires.
int testSimHealthNonFairS2SelectionFailed() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    const bool savedFair = search::g_fairPlay;
    const bool savedS3 = search::g_useSearcher3;
    search::g_fairPlay = false;    // non-fair (known-RNG) Searcher2
    search::g_useSearcher3 = false;

    BattleContext bc = playerNormalFixture(0xBEEFu, 3);
    check(bc.outcome == Outcome::UNDECIDED,
          "fixture must start UNDECIDED");
    check(search::hasLegalProgressionAction(bc),
          "PLAYER_NORMAL must have a legal progression action (END_TURN)");

    const auto nlpBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION];
    const auto asfBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::ACTION_SELECTION_FAILED];
    const auto ubeBefore = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::UNDECIDED_BATTLE_EXIT];

    search::ScumSearchAgent2 agent;
    agent.stepsWithSolution = 0;   // forces stepThroughSolution to commit zero actions
    agent.simulationCountBase = 200;
    agent.playoutBattle(bc);

    const int nlpFired = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::NO_LEGAL_PROGRESSION] - nlpBefore;
    const int asfFired = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::ACTION_SELECTION_FAILED] - asfBefore;
    const int ubeFired = search::g_simHealthFailureCounts[(int)search::SimHealthFailure::UNDECIDED_BATTLE_EXIT] - ubeBefore;

    check(asfFired >= 1,
          "ACTION_SELECTION_FAILED must fire as the primary failure (got "
          + std::to_string(asfFired) + ")");
    check(nlpFired == 0,
          "NO_LEGAL_PROGRESSION must not fire when legal live actions exist (got "
          + std::to_string(nlpFired) + ")");
    check(ubeFired >= 1,
          "UNDECIDED_BATTLE_EXIT must fire as the secondary safety net (got "
          + std::to_string(ubeFired) + ")");
    check(bc.outcome == Outcome::UNDECIDED,
          "battle must exit UNDECIDED (not a stall-converted PLAYER_LOSS), got "
          + std::to_string((int)bc.outcome));

    search::g_fairPlay = savedFair;
    search::g_useSearcher3 = savedS3;

    if (failures == 0) {
        std::cout << "simhealth_nonfair_s2_selection_failed PASS\n";
        return 0;
    }
    std::cout << "simhealth_nonfair_s2_selection_failed FAIL (" << failures << " cases)\n";
    return 1;
}

int testTrainingIntegrity() {
    int failures = 0;
    const auto check = [&failures](bool ok, const char *msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };
    check(search::isValidTrainingTerminal(true, 0, 0),
          "decided victory/loss with no health failure is valid");
    check(search::isValidTrainingTerminal(false, 0, 0, true),
          "clean unresolved bounded bootstrap is valid");
    check(!search::isValidTrainingTerminal(false, 0, 0),
          "unresolved ordinary label is invalid");
    check(!search::isValidTrainingTerminal(true, 0, 1),
          "health-failed decided label is invalid");
    check(!search::isValidTrainingTerminal(false, 0, 1, true),
          "health-failed bootstrap is invalid");
    check(!search::hasCompleteCounterfactualFutureSet(1, 2, 2),
          "one valid and one invalid future quarantines the label rather than averaging with zero");
    check(search::hasCompleteCounterfactualFutureSet(2, 2, 2),
          "all requested counterfactual futures permit a label");
    check(search::hasCompleteCounterfactualFutureSet(3, 3, 2),
          "adaptive extra futures remain valid when every evaluated future succeeded");
    {
        BattleContext bc = playerNormalFixture(0xFACEu, 3);
        const int totalBefore = search::g_simHealthFailureCount;
        const int reasonBefore = search::g_simHealthFailureCounts[
            (int)search::SimHealthFailure::ACTION_SELECTION_FAILED];
        search::reportSimHealthFailure(bc, search::SimHealthFailure::ACTION_SELECTION_FAILED);
        const int branchDelta = search::g_simHealthFailureCount - totalBefore;
        check(branchDelta == 1, "branch failure increments canonical total exactly once");
        check(search::g_simHealthFailureCounts[(int)search::SimHealthFailure::ACTION_SELECTION_FAILED]
              == reasonBefore + 1, "branch failure increments canonical per-reason count");
        int reasonSum = 0;
        for (const int count : search::g_simHealthFailureCounts) reasonSum += count;
        check(reasonSum == search::g_simHealthFailureCount,
              "canonical total remains consistent with per-reason counts");
        check(search::isValidTrainingTerminal(true, totalBefore,
                                              search::g_simHealthFailureCount - branchDelta),
              "excluding only branch-local failures preserves a clean source run");
        check(!search::isValidTrainingTerminal(true, totalBefore,
                                               search::g_simHealthFailureCount),
              "unexcluded health failure invalidates a source run");
    }
    if (failures == 0) {
        std::cout << "training_integrity PASS\n";
        return 0;
    }
    std::cout << "training_integrity FAIL (" << failures << " cases)\n";
    return 1;
}

// simhealth_load <path>: deserialize a sim-health capture .bin and print its
// key fields. Load-only proof that a captured snapshot round-trips (used to
// verify STS_SIM_HEALTH_CAPTURE_DIR outputs; no replay).
int simHealthLoad(const std::string &path) {
    std::ifstream bin(path, std::ios::binary);
    if (!bin) {
        std::cout << "simhealth_load FAIL: cannot open " << path << '\n';
        return 1;
    }
    std::vector<std::uint8_t> blob((std::istreambuf_iterator<char>(bin)),
                                   std::istreambuf_iterator<char>());
    const BattleContext bc = sts::deserializeBattleContext(blob.data(), blob.size());
    if (bc.encounter == MonsterEncounter::INVALID) {
        std::cout << "simhealth_load FAIL: malformed/corrupt blob " << path << '\n';
        return 1;
    }
    std::cout << "seed=" << bc.seed << '\n';
    std::cout << "floor=" << bc.floorNum << '\n';
    std::cout << "encounter=" << monsterEncounterEnumNames[(int)bc.encounter]
              << '(' << (int)bc.encounter << ")\n";
    std::cout << "turn=" << bc.turn << '\n';
    std::cout << "outcome=" << battleOutcomeStrings[(int)bc.outcome]
              << '(' << (int)bc.outcome << ")\n";
    std::cout << "inputState=" << (int)bc.inputState << '\n';
    std::cout << "cardSelectTask=" << cardSelectTaskStrings[(int)bc.cardSelectInfo.cardSelectTask]
              << '(' << (int)bc.cardSelectInfo.cardSelectTask << ")\n";
    std::cout << "pickCount=" << bc.cardSelectInfo.pickCount << '\n';
    std::cout << "cardsInHand=" << bc.cards.cardsInHand << '\n';
    std::cout << "playerHp=" << bc.player.curHp << '/' << bc.player.maxHp << '\n';
    std::cout << "drawPile=" << bc.cards.drawPile.size()
              << " discardPile=" << bc.cards.discardPile.size()
              << " exhaustPile=" << bc.cards.exhaustPile.size() << '\n';
    std::cout << "simhealth_load PASS\n";
    return 0;
}

// Regression: Designer In-Spire event options 3 and 4 must not fall through to
// the next case. Before the fix, option 3 also paid the option-4 gold cost,
// opened a REMOVE card select, and lost 5 HP; option 4 also lost 5 HP.
int testDesignerInSpireOptions() {
    int failures = 0;
    const auto check = [&failures](bool ok, const std::string &msg) {
        if (!ok) {
            std::cout << "    " << msg << '\n';
            ++failures;
        }
    };

    // Ascension 15 => unfavorable => option 3 costs 75 gold, option 4 costs
    // 110 gold, and the option-5 HP loss is 5.
    GameContext gc(sts::CharacterClass::IRONCLAD, 0xDE51u, 15);
    gc.curEvent = Event::DESIGNER_IN_SPIRE;
    gc.gold = 500;
    gc.curHp = 80;
    gc.deck.obtain(gc, CardId::STRIKE_RED, 3);
    gc.regainControlAction = [](auto &gs) { gs.screenState = ScreenState::MAP_SCREEN; };

    // Option 3: pay 75 gold, transform 2 cards, regain control immediately.
    gc.chooseEventOption(3);
    check(gc.gold == 425, "option 3: expected gold 425, got " + std::to_string(gc.gold));
    check(gc.curHp == 80, "option 3: expected hp 80, got " + std::to_string(gc.curHp));
    check(gc.screenState == ScreenState::MAP_SCREEN,
          "option 3: expected MAP_SCREEN (regain control), got " + std::to_string((int)gc.screenState));

    // Option 4: pay 110 gold, open a REMOVE card select (control not regained).
    gc.gold = 500;
    gc.curHp = 80;
    gc.screenState = ScreenState::EVENT_SCREEN;
    gc.chooseEventOption(4);
    check(gc.gold == 390, "option 4: expected gold 390, got " + std::to_string(gc.gold));
    check(gc.curHp == 80, "option 4: expected hp 80, got " + std::to_string(gc.curHp));
    check(gc.screenState == ScreenState::CARD_SELECT,
          "option 4: expected CARD_SELECT, got " + std::to_string((int)gc.screenState));
    check(gc.info.selectScreenType == CardSelectScreenType::REMOVE,
          "option 4: expected REMOVE card select, got " + std::to_string((int)gc.info.selectScreenType));
    check(gc.info.toSelectCount == 1,
          "option 4: expected 1 card to select, got " + std::to_string(gc.info.toSelectCount));

    if (failures == 0) {
        std::cout << "designer_in_spire PASS\n";
        return 0;
    }
    std::cout << "designer_in_spire FAIL (" << failures << " cases)\n";
    return 1;
}

// Regression test for the CardQueue overflow fix: the capacity assertions in
// CardQueue.cpp are guarded by sts_asserts (defined unconditionally in
// sts_common.h), so pushing an 11th item into the capacity-10 ring must abort
// in every build regime. A raw assert() would be compiled out under NDEBUG and
// the overflow would silently wrap and corrupt the ring buffer.
int testCardQueueOverflow() {
    pid_t pid = fork();
    if (pid == 0) {
        CardQueue q;
        for (int i = 0; i < CardQueue::capacity; ++i) {
            q.pushBack(CardQueueItem{});
        }
        q.pushBack(CardQueueItem{}); // must abort, not wrap
        _exit(0); // unreachable while the assertion fires
    }
    int status = 0;
    if (pid < 0 || waitpid(pid, &status, 0) != pid) {
        std::cout << "cardqueue_overflow FAIL (fork/waitpid error)\n";
        return 1;
    }
    if (WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT) {
        std::cout << "cardqueue_overflow PASS (overflow aborts)\n";
        return 0;
    }
    std::cout << "cardqueue_overflow FAIL (expected SIGABRT, status " << status << ")\n";
    return 1;
}
// Regression test for key collection in the default OOC policy chain: the
// rewards handlers must take the emerald (burning elite) and sapphire (chest)
// keys, and act-3+ rest rooms must take the ruby key (RECALL), otherwise
// Act 4 is unreachable. This pins the shared fallback behavior
// (ScumSearchAgent2::stepRewardsPolicy / REST_ROOM case and
// SimpleAgent::stepRestScreen); the apps/one_combat.cpp REWARDS/rest chains
// mirror these handlers.
extern bool g_collectKeys;
int testKeyCollection() {
    g_collectKeys = true;
    int failures = 0;
    auto check = [&](bool ok, const std::string &msg) {
        if (!ok) { std::cout << "    " << msg << '\n'; ++failures; }
    };

    // 1) Emerald key on the rewards screen is taken by stepRewardsPolicy.
    {
        GameContext gc(sts::CharacterClass::IRONCLAD, 1, 0);
        gc.screenState = ScreenState::REWARDS;
        gc.regainControlAction = [](auto &gs) { gs.screenState = ScreenState::MAP_SCREEN; };
        gc.info.rewardsContainer.emeraldKey = true;
        search::ScumSearchAgent2 agent;
        agent.rng = std::default_random_engine(1);
        agent.stepRewardsPolicy(gc);
        check(gc.hasKey(sts::Key::EMERALD_KEY),
              "stepRewardsPolicy: emerald key not taken");
    }

    // 2) Sapphire key on the rewards screen is taken by stepRewardsPolicy.
    {
        GameContext gc(sts::CharacterClass::IRONCLAD, 2, 0);
        gc.screenState = ScreenState::REWARDS;
        gc.regainControlAction = [](auto &gs) { gs.screenState = ScreenState::MAP_SCREEN; };
        gc.info.rewardsContainer.sapphireKey = true;
        search::ScumSearchAgent2 agent;
        agent.rng = std::default_random_engine(2);
        agent.stepRewardsPolicy(gc);
        check(gc.hasKey(sts::Key::SAPPHIRE_KEY),
              "stepRewardsPolicy: sapphire key not taken");
    }

    // 3) Ruby key is taken at an act-3 rest room (ScumSearchAgent2 fallback).
    {
        GameContext gc(sts::CharacterClass::IRONCLAD, 3, 0);
        gc.screenState = ScreenState::REST_ROOM;
        gc.regainControlAction = [](auto &gs) { gs.screenState = ScreenState::MAP_SCREEN; };
        gc.act = 3;
        search::ScumSearchAgent2 agent;
        agent.rng = std::default_random_engine(3);
        agent.stepOutOfCombatPolicy(gc);
        check(gc.hasKey(sts::Key::RUBY_KEY),
              "ScumSearchAgent2 REST_ROOM act 3: ruby key not taken");
    }

    // 4) Ruby key is taken at an act-3 rest room (SimpleAgent fallback).
    {
        GameContext gc(sts::CharacterClass::IRONCLAD, 4, 0);
        gc.screenState = ScreenState::REST_ROOM;
        gc.regainControlAction = [](auto &gs) { gs.screenState = ScreenState::MAP_SCREEN; };
        gc.act = 3;
        search::SimpleAgent agent;
        agent.stepRestScreen(gc);
        check(gc.hasKey(sts::Key::RUBY_KEY),
              "SimpleAgent::stepRestScreen act 3: ruby key not taken");
    }

    g_collectKeys = false;
    if (failures == 0) {
        std::cout << "keys_collect PASS\n";
        return 0;
    }
    std::cout << "keys_collect FAIL (" << failures << " cases)\n";
    return 1;
}

// ---- S3 semantic CARD edge regression tests ---------------------------------
// Verifies that edges carrying a semantic CardActionKey resolve to the
// correct live-hand index, independent of hand permutation — the core
// invariant that CombatObservation canonicalizes the hand as a multiset
// but Edge::action stores a position-dependent index.
int testSemanticCardEdges() {
    search::g_s3SemanticCardEdges = true;
    int failures = 0;

    // Helper: build a BattleContext with a specific hand + monster setup.
    auto makeContext = [](const std::vector<CardId> &handCards,
                          MonsterEncounter enc = MonsterEncounter::CULTIST) {
        GameContext gc(CharacterClass::IRONCLAD, 0x42, 0);
        BattleContext bc;
        bc.init(gc, enc);
        // Replace the hand with the desired cards.
        bc.cards.cardsInHand = (int)handCards.size();
        for (int i = 0; i < (int)handCards.size(); ++i)
            bc.cards.hand[i] = CardInstance(handCards[i]);
        // Ensure we have energy to play them.
        bc.player.energy = 3;
        return bc;
    };

    // ── Test 1: Hand [Strike, Bash, Strike] — resolve Bash to index 1 ──
    {
        auto bc = makeContext({CardId::STRIKE_RED, CardId::BASH, CardId::STRIKE_RED});
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        // Find the Bash edge (should have hasCardKey set).
        const search::BattleScumSearcher3::Edge *bashEdge = nullptr;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                bashEdge = &e;
                break;
            }
        }
        if (!bashEdge) {
            std::cout << "semantic_card_edges FAIL: no Bash edge with cardKey\n";
            ++failures;
        } else {
            auto resolved = search::resolveSemanticCardEdge(*bashEdge, bc);
            if (!resolved) {
                std::cout << "semantic_card_edges FAIL: Bash not resolved in [Strike,Bash,Strike]\n";
                ++failures;
            } else if (resolved->getSourceIdx() != 1) {
                std::cout << "semantic_card_edges FAIL: Bash resolved to idx "
                          << resolved->getSourceIdx() << ", expected 1\n";
                ++failures;
            }
        }
    }

    // ── Test 2: Hand [Bash, Strike, Strike] — resolve Bash to index 0 ──
    {
        auto bc = makeContext({CardId::BASH, CardId::STRIKE_RED, CardId::STRIKE_RED});
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        const search::BattleScumSearcher3::Edge *bashEdge = nullptr;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                bashEdge = &e;
                break;
            }
        }
        if (!bashEdge) {
            std::cout << "semantic_card_edges FAIL: no Bash edge from [Bash,Strike,Strike]\n";
            ++failures;
        } else {
            auto resolved = search::resolveSemanticCardEdge(*bashEdge, bc);
            if (!resolved) {
                std::cout << "semantic_card_edges FAIL: Bash not resolved in [Bash,Strike,Strike]\n";
                ++failures;
            } else if (resolved->getSourceIdx() != 0) {
                std::cout << "semantic_card_edges FAIL: Bash resolved to idx "
                          << resolved->getSourceIdx() << ", expected 0\n";
                ++failures;
            }
        }
    }

    // ── Test 3: same edge resolves Bash across different hand permutations ──
    {
        auto bcA = makeContext({CardId::STRIKE_RED, CardId::BASH, CardId::STRIKE_RED});
        search::BattleScumSearcher3::Node nodeA;
        search::enumerateActionsForNode(nodeA, bcA);

        const search::BattleScumSearcher3::Edge *bashA = nullptr;
        for (const auto &e : nodeA.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                bashA = &e;
                break;
            }
        }
        if (!bashA) {
            std::cout << "semantic_card_edges FAIL cross-perm: no Bash edge A\n";
            ++failures;
        } else {
            // Resolve in a DIFFERENT BattleContext with Bash at index 0.
            auto bcB = makeContext({CardId::BASH, CardId::STRIKE_RED, CardId::STRIKE_RED});
            auto resolvedB = search::resolveSemanticCardEdge(*bashA, bcB);
            if (!resolvedB) {
                std::cout << "semantic_card_edges FAIL cross-perm: Bash not resolved\n";
                ++failures;
            } else if (resolvedB->getSourceIdx() != 0) {
                std::cout << "semantic_card_edges FAIL cross-perm: Bash resolved to idx "
                          << resolvedB->getSourceIdx() << ", expected 0\n";
                ++failures;
            }
            // Resolve in original context.
            auto resolvedA = search::resolveSemanticCardEdge(*bashA, bcA);
            if (!resolvedA || resolvedA->getSourceIdx() != 1) {
                std::cout << "semantic_card_edges FAIL cross-perm: Bash back-resolve wrong\n";
                ++failures;
            }
        }
    }

    // ── Test 4: two identical Strikes — each has a cardKey (different idx, same key) ──
    // enumerateActionsForNode deduplicates consecutive identical cards, so only
    // one Strike edge is created for [Strike, Strike, Bash]. After resolution,
    // the edge maps to the first matching Strike.
    {
        auto bc = makeContext({CardId::STRIKE_RED, CardId::STRIKE_RED, CardId::BASH});
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        // Should have one STRIKE_RED CARD edge (deduped).
        int strikeEdges = 0;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::STRIKE_RED)
                ++strikeEdges;
        }
        if (strikeEdges != 1) {
            std::cout << "semantic_card_edges FAIL two-strikes: expected 1 Strike edge, got "
                      << strikeEdges << "\n";
            ++failures;
        } else {
            const auto &strikeEdge = node.edges[0]; // first CARD edge should be Strike
            // Resolve in hand [Bash, Strike, Strike] — should find Strike at idx 1
            auto bc2 = makeContext({CardId::BASH, CardId::STRIKE_RED, CardId::STRIKE_RED});
            auto resolved = search::resolveSemanticCardEdge(strikeEdge, bc2);
            if (!resolved) {
                std::cout << "semantic_card_edges FAIL two-strikes: Strike not resolved\n";
                ++failures;
            } else if (resolved->getSourceIdx() != 1) {
                std::cout << "semantic_card_edges FAIL two-strikes: resolved to idx "
                          << resolved->getSourceIdx() << ", expected 1\n";
                ++failures;
            }
        }
    }

    // ── Test 5: upgraded vs non-upgraded — distinct cardKeys ──
    {
        auto bc = makeContext({CardId::STRIKE_RED, CardId::BASH});
        // Manually upgrade the Bash.
        bc.cards.hand[1].upgrade();
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        int bashEdges = 0;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                ++bashEdges;
                if (e.cardKey.upgradeCount != 1) {
                    std::cout << "semantic_card_edges FAIL upgraded: Bash+ key upgradeCount="
                              << (int)e.cardKey.upgradeCount << ", expected 1\n";
                    ++failures;
                }
            }
        }
        if (bashEdges == 0) {
            std::cout << "semantic_card_edges FAIL upgraded: no Bash+ edge\n";
            ++failures;
        }

        // Unupgraded Bash in a fresh hand should NOT match the Bash+ key.
        auto bc2 = makeContext({CardId::BASH, CardId::STRIKE_RED});
        // bc2 has unupgraded Bash. Get its Bash edge.
        search::BattleScumSearcher3::Node node2;
        search::enumerateActionsForNode(node2, bc2);
        const search::BattleScumSearcher3::Edge *unupEdge = nullptr;
        for (const auto &e : node2.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH && e.cardKey.upgradeCount == 0)
                { unupEdge = &e; break; }
        }
        // Try to resolve the Bash+ edge against an unupgraded Bash hand — should fail.
        if (bashEdges > 0 && unupEdge) {
            auto resolved = search::resolveSemanticCardEdge(node.edges[1], bc2);
            // node.edges[1] should be Bash+ (idx 1 in [Strike, Bash+]).
            // bc2 has unupgraded Bash at idx 0. cardKey.upgradeCount=1 vs 0 → no match.
            if (resolved) {
                std::cout << "semantic_card_edges FAIL upgrade: Bash+ incorrectly matched unupgraded Bash\n";
                ++failures;
            }
        }
    }

    // ── Test 6: temporary cost difference (Madness / Mummified Hand) ──
    {
        auto bc = makeContext({CardId::STRIKE_RED, CardId::DEFEND_RED});
        bc.cards.hand[1].costForTurn = 0;  // Defend is free this turn
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::DEFEND_RED) {
                if (e.cardKey.costForTurn != 0) {
                    std::cout << "semantic_card_edges FAIL temp-cost: Defend costForTurn="
                              << (int)e.cardKey.costForTurn << ", expected 0\n";
                    ++failures;
                }
                break;
            }
        }

        // A standard Defend (cost=1) should NOT match.
        auto bc2 = makeContext({CardId::DEFEND_RED, CardId::STRIKE_RED});
        // Find the Defend-1 edge
        search::BattleScumSearcher3::Node node2;
        search::enumerateActionsForNode(node2, bc2);
        // Try to resolve a cost=0 Defend against cost=1 Defend hand — should fail.
        bool foundCostZeroEdge = false;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::DEFEND_RED && e.cardKey.costForTurn == 0) {
                auto resolved = search::resolveSemanticCardEdge(e, bc2);
                if (resolved) {
                    std::cout << "semantic_card_edges FAIL temp-cost: cost=0 Defend matched cost=1 Defend\n";
                    ++failures;
                }
                foundCostZeroEdge = true;
                break;
            }
        }
        if (!foundCostZeroEdge) {
            std::cout << "semantic_card_edges FAIL temp-cost: no cost=0 Defend edge\n";
            ++failures;
        }
    }

    // ── Test 7: targeted CARD edge stores and resolves target ──
    {
        // Use a fight with two targetable monsters (CULTIST has 1, use JAW_WORM with double)
        auto bc = makeContext({CardId::BASH}, MonsterEncounter::CULTIST);
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                if (e.cardKey.target != 0) {
                    std::cout << "semantic_card_edges FAIL target: Bash target="
                              << e.cardKey.target << ", expected 0\n";
                    ++failures;
                }
                // Resolve in same context — target should be preserved.
                auto resolved = search::resolveSemanticCardEdge(e, bc);
                if (!resolved) {
                    std::cout << "semantic_card_edges FAIL target: Bash not resolved\n";
                    ++failures;
                } else if (resolved->getTargetIdx() != 0) {
                    std::cout << "semantic_card_edges FAIL target: resolved target="
                              << resolved->getTargetIdx() << ", expected 0\n";
                    ++failures;
                }
                break;
            }
        }
    }

    // ── Test 8: missing semantic card — edge unavailable ──
    {
        auto bc = makeContext({CardId::STRIKE_RED, CardId::BASH, CardId::STRIKE_RED});
        search::BattleScumSearcher3::Node node;
        search::enumerateActionsForNode(node, bc);

        const search::BattleScumSearcher3::Edge *bashEdge = nullptr;
        for (const auto &e : node.edges) {
            if (e.hasCardKey && e.cardKey.id == CardId::BASH) {
                bashEdge = &e;
                break;
            }
        }
        if (!bashEdge) {
            std::cout << "semantic_card_edges FAIL missing-card: no Bash edge to test\n";
            ++failures;
        } else {
            // Resolve in a hand without Bash.
            auto bcNoBash = makeContext({CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::STRIKE_RED});
            auto resolved = search::resolveSemanticCardEdge(*bashEdge, bcNoBash);
            if (resolved) {
                std::cout << "semantic_card_edges FAIL missing-card: Bash incorrectly resolved in Bash-free hand\n";
                ++failures;
            }
        }
    }

    // ── Test 9: observation identity — permuted hands have same visibleHash ──
    {
        auto bcA = makeContext({CardId::STRIKE_RED, CardId::BASH, CardId::STRIKE_RED});
        auto bcB = makeContext({CardId::BASH, CardId::STRIKE_RED, CardId::STRIKE_RED});
        auto obsA = CombatObservation::fromBattleContext(bcA);
        auto obsB = CombatObservation::fromBattleContext(bcB);
        if (obsA.visibleHash() != obsB.visibleHash()) {
            std::cout << "semantic_card_edges FAIL obs-identity: permuted hands have different hash\n";
            ++failures;
        }
        if (obsA != obsB) {
            std::cout << "semantic_card_edges FAIL obs-identity: permuted hands != under operator==\n";
            ++failures;
        }
    }

    search::g_s3SemanticCardEdges = false;
    if (failures == 0) {
        std::cout << "semantic_card_edges PASS\n";
        return 0;
    }
    std::cout << "semantic_card_edges FAIL (" << failures << " checks)\n";
    return 1;
}

// ---- S3 draw-pile-index reuse boundary regression --------------------------
int testS3DrawPileIndexReuseBoundary() {
    int failures = 0;
    auto check = [&](bool ok, const char *message) {
        if (!ok) {
            std::cout << "s3_drawpile_reuse_boundary FAIL: " << message << '\n';
            ++failures;
        }
    };

    for (CardSelectTask task : {CardSelectTask::SECRET_TECHNIQUE,
                                CardSelectTask::SECRET_WEAPON,
                                CardSelectTask::SEEK}) {
        auto bc = cardSelectFixture(task, 1, false);
        check(search::isDrawPileIndexSensitiveCardSelect(bc),
              "draw-pile task not classified as sensitive");
        search::BattleScumSearcher3 s3(bc, 0x1234, 0, 1);
        s3.search(1);
        check(!s3.root.edges.empty(), "sensitive fixture produced no root edges");
        if (!s3.root.edges.empty()) {
            const auto action = s3.root.edges.front().action;
            check(!s3.advanceRoot(action, bc),
                  "sensitive card-select root retained a subtree");
            check(!s3.rootCarried && s3.reuseGeneration == 0,
                  "fresh sensitive boundary reported as carried");
        }

        // Root expansion can observe a different particle draw order than
        // the live state. Reconciliation must add the live raw-index action.
        auto stale = cardSelectFixture(task, 1, false);
        auto live = stale;
        std::swap(live.cards.drawPile[0], live.cards.drawPile[1]);
        search::BattleScumSearcher3 reconciler(stale, 0x4321, 0, 1);
        for (const auto &action : search::Action::enumerateCardSelectActions(stale)) {
            search::BattleScumSearcher3::Edge edge;
            edge.action = action;
            reconciler.root.edges.push_back(std::move(edge));
        }
        const auto liveActions = search::Action::enumerateCardSelectActions(live);
        reconciler.reconcileRoot(live);
        for (const auto &action : liveActions) {
            bool found = false;
            for (const auto &edge : reconciler.root.edges)
                found = found || edge.action.bits == action.bits;
            check(found, "reconciliation failed to add live draw-pile action");
            check(action.isValidAction(live), "canonical live draw-pile action invalid");
        }

        // Fair Searcher2 has the same raw-index boundary at root selection.
        // Two eligible cards deliberately exchange indices; the committed
        // action must follow the semantic card preferred in the determinized
        // state, not merely reuse a still-legal raw index.
        if (task == CardSelectTask::SECRET_TECHNIQUE) {
            stale.cards.drawPile = {CardInstance(CardId::DEFEND_RED),
                                    CardInstance(CardId::SHRUG_IT_OFF),
                                    CardInstance(CardId::STRIKE_RED)};
        } else if (task == CardSelectTask::SECRET_WEAPON) {
            stale.cards.drawPile = {CardInstance(CardId::BASH),
                                    CardInstance(CardId::ANGER),
                                    CardInstance(CardId::DEFEND_RED)};
        } else {
            stale.cards.drawPile = {CardInstance(CardId::BASH),
                                    CardInstance(CardId::DEFEND_RED),
                                    CardInstance(CardId::STRIKE_RED)};
        }
        live = stale;
        std::swap(live.cards.drawPile[0], live.cards.drawPile[1]);
        const CardId preferred = stale.cards.drawPile[0].getId();
        search::BattleScumSearcher2 s2(stale);
        s2.enumerateActionsForNode(s2.root, stale);
        for (auto &edge : s2.root.edges) {
            edge.node.simulationCount =
                stale.cards.drawPile[edge.action.getSelectIdx()].getId() == preferred
                    ? 100 : 1;
        }
        const auto preferredEdge = std::find_if(
            s2.root.edges.begin(), s2.root.edges.end(), [&](const auto &edge) {
                return stale.cards.drawPile[edge.action.getSelectIdx()].getId()
                    == preferred;
            });
        search::Action resolvedInParticle;
        check(preferredEdge != s2.root.edges.end()
                  && s2.resolveSelectedCardAction(*preferredEdge, live,
                                                  resolvedInParticle)
                  && live.cards.drawPile[resolvedInParticle.getSelectIdx()].getId()
                         == preferred,
              "S2 semantic edge did not rebind inside a new determinization");
        search::Action selected;
        check(s2.mostVisitedLiveRootAction(live, selected),
              "S2 reconciliation found no live draw-pile action");
        check(selected.isValidAction(live),
              "S2 reconciliation returned stale draw-pile action");
        check(live.cards.drawPile[selected.getSelectIdx()].getId() == preferred,
              "S2 reconciliation did not preserve selected-card identity");
    }

    // Identical copies form one semantic bucket. Their visits aggregate, and
    // deterministic live enumeration chooses the first equivalent copy.
    auto duplicate = cardSelectFixture(CardSelectTask::SEEK, 1, false);
    duplicate.cards.drawPile = {CardInstance(CardId::ANGER),
                                CardInstance(CardId::ANGER),
                                CardInstance(CardId::BASH)};
    auto duplicateLive = duplicate;
    std::swap(duplicateLive.cards.drawPile[1], duplicateLive.cards.drawPile[2]);
    search::BattleScumSearcher2 duplicateS2(duplicate);
    duplicateS2.enumerateActionsForNode(duplicateS2.root, duplicate);
    duplicateS2.root.edges[0].node.simulationCount = 40;
    duplicateS2.root.edges[1].node.simulationCount = 40;
    duplicateS2.root.edges[2].node.simulationCount = 70;
    search::Action duplicateSelected;
    check(duplicateS2.mostVisitedLiveRootAction(duplicateLive, duplicateSelected),
          "S2 duplicate reconciliation found no action");
    check(duplicateLive.cards.drawPile[duplicateSelected.getSelectIdx()].getId()
              == CardId::ANGER,
          "S2 duplicate visits were not aggregated by semantics");
    check(duplicateSelected.getSelectIdx() == 0,
          "S2 duplicate reconciliation was not deterministic");

    // If none of the stored semantic choices exists in a synthetic live root,
    // canonical live choices remain available with zero visits.
    auto fallbackLive = duplicate;
    fallbackLive.cards.drawPile = {CardInstance(CardId::DEFEND_RED)};
    search::Action fallbackSelected;
    check(duplicateS2.mostVisitedLiveRootAction(fallbackLive, fallbackSelected),
          "S2 live-only fallback found no action");
    check(fallbackSelected.isValidAction(fallbackLive)
              && fallbackLive.cards.drawPile[fallbackSelected.getSelectIdx()].getId()
                     == CardId::DEFEND_RED,
          "S2 live-only fallback did not return the canonical live action");

    auto ordinary = cardSelectFixture(CardSelectTask::HOLOGRAM, 1, false);
    check(!search::isDrawPileIndexSensitiveCardSelect(ordinary),
          "unrelated card-select task classified as sensitive");
    search::BattleScumSearcher2 ordinaryS2(ordinary);
    ordinaryS2.enumerateActionsForNode(ordinaryS2.root, ordinary);
    check(!ordinaryS2.root.edges.empty()
              && !ordinaryS2.root.edges.front().hasSelectedCardKey,
          "ordinary S2 root unexpectedly entered semantic draw-pile path");
    search::BattleScumSearcher3 ordinaryS3(ordinary, 0x5678, 0, 1);
    ordinaryS3.search(1);
    check(!ordinaryS3.root.edges.empty(), "ordinary fixture produced no root edges");
    if (!ordinaryS3.root.edges.empty()) {
        check(ordinaryS3.advanceRoot(ordinaryS3.root.edges.front().action, ordinary),
              "ordinary card-select root did not reuse");
    }

    if (failures == 0) {
        std::cout << "s3_drawpile_reuse_boundary PASS\n";
        return 0;
    }
    std::cout << "s3_drawpile_reuse_boundary FAIL (" << failures << " checks)\n";
    return 1;
}

// ---- Draw-probability unit tests -------------------------------------------
// Validates the exact hypergeometric draw-probability helper.

// Forward-declare the helper (defined in BattleScumSearcher3.cpp).
namespace sts::search {
    double hypergeometricAtLeastOne(int N, int K, int D);
    double expectedCount(int N, int K, int D);
}

int testDrawProbHelper() {
    using sts::search::hypergeometricAtLeastOne;
    using sts::search::expectedCount;
    int failures = 0;
    auto check = [&](bool ok, const std::string &msg) {
        if (!ok) { std::cout << "    FAIL: " << msg << '\n'; ++failures; }
    };

    // One lethal out: N=6, K=1, D=5 → P = 5/6
    double p = hypergeometricAtLeastOne(6, 1, 5);
    check(std::abs(p - 5.0/6.0) < 1e-9, "one lethal out: expected 0.8333, got " + std::to_string(p));

    // Two outs in 5: N=6, K=2, D=5 → P = 1.0 (drawing 5 of 6, can't miss both)
    p = hypergeometricAtLeastOne(6, 2, 5);
    check(std::abs(p - 1.0) < 1e-9, "two outs: expected 1.0, got " + std::to_string(p));

    // No outs: K=0 → P=0
    p = hypergeometricAtLeastOne(6, 0, 5);
    check(std::abs(p) < 1e-9, "no outs: expected 0, got " + std::to_string(p));

    // Draw whole pile: D >= N, K > 0 → P = 1
    p = hypergeometricAtLeastOne(3, 1, 3);
    check(std::abs(p - 1.0) < 1e-9, "draw all: expected 1.0, got " + std::to_string(p));
    p = hypergeometricAtLeastOne(3, 1, 5);  // D > N
    check(std::abs(p - 1.0) < 1e-9, "draw more than pile: expected 1.0, got " + std::to_string(p));

    // Half outs: N=10, K=5, D=5
    // P = 1 - C(5,5)/C(10,5) = 1 - 1/252 ≈ 0.99603
    p = hypergeometricAtLeastOne(10, 5, 5);
    check(std::abs(p - (1.0 - 1.0/252.0)) < 1e-6, "half outs: expected ~0.996, got " + std::to_string(p));

    // Expected count
    double e = expectedCount(10, 3, 5);
    check(std::abs(e - 1.5) < 1e-9, "expected attacks: expected 1.5, got " + std::to_string(e));

    e = expectedCount(6, 2, 5);
    check(std::abs(e - 10.0/6.0) < 1e-9, "expected: expected 1.667, got " + std::to_string(e));

    if (failures == 0) {
        std::cout << "draw_prob_helper PASS\n";
        return 0;
    }
    std::cout << "draw_prob_helper FAIL (" << failures << " checks)\n";
    return 1;
}

// Engine-level test: construct a state with known lethal outs and verify.
int testDrawProbEngine() {
    // This test verifies the integration: a simple constructed combat state
    // where the draw pile has one lethal card and several non-lethal cards.
    GameContext gc(CharacterClass::IRONCLAD, 0x12345, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);  // single cultist

    // Weaken the cultist so a single Strike is lethal.
    // Cultist has ~48-54 HP at A0. Set it to 6 HP so Strike (6 base dmg) kills.
    bc.monsters.arr[0].curHp = 6;
    bc.monsters.arr[0].maxHp = 6;

    // Set up draw pile: one Strike, three Defends.
    bc.cards.drawPile.clear();
    bc.cards.drawPile.push_back(CardInstance(CardId::STRIKE_RED));
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.drawPile.push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.cardsInHand = 0;
    bc.player.energy = 3;

    // Enumerate END_TURN edges and verify there is at least one.
    search::BattleScumSearcher3::Node node;
    search::enumerateActionsForNode(node, bc);
    bool hasEndTurn = false;
    for (const auto &e : node.edges)
        if (e.action.getActionType() == search::ActionType::END_TURN)
            hasEndTurn = true;
    if (!hasEndTurn) {
        std::cout << "draw_prob_engine FAIL: no END_TURN edge\n";
        return 1;
    }

    // The draw-prob diagnostic is tested via the CSV output.
    // This smoke test just confirms the state is constructable.
    std::cout << "draw_prob_engine PASS (state constructable)\n";
    return 0;
}

int testThornsRetaliationVictory() {
    int failures = 0;

    // Issue #50: player kills the last enemy with an attack while its Thorns
    // retaliation would be lethal. Real StS ends the fight on the killing blow:
    // the retaliation must never run and the outcome must stay PLAYER_VICTORY.
    GameContext gc(CharacterClass::IRONCLAD, 0x42, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);

    auto &m = bc.monsters.arr[0];
    m.curHp = 1;                 // one hit from death
    m.buff<MS::THORNS>(3);       // lethal retaliation for a 1 HP player
    bc.player.curHp = 1;

    bc.setState(InputState::EXECUTING_ACTIONS);
    bc.addToBot(Actions::AttackEnemy(0, 6)); // killing blow; Thorns queued to top
    bc.executeActions();

    if (bc.outcome != Outcome::PLAYER_VICTORY) {
        std::cout << "thorns_retaliation FAIL: outcome=" << (int)bc.outcome
                  << " (expected PLAYER_VICTORY=" << (int)Outcome::PLAYER_VICTORY << ")\n";
        ++failures;
    }

    if (failures == 0) {
        std::cout << "thorns_retaliation PASS\n";
        return 0;
    }
    std::cout << "thorns_retaliation FAIL (" << failures << " checks)\n";
    return 1;
}

int testAwakenedOneStage2() {
    int failures = 0;

    // Issue #51: Awakened One stage 1 dies first (half-dead, rebirth queued),
    // then both Cultists die in the same round. monstersAlive reaches 0 while
    // the boss is mid-revival; victory must NOT be granted yet and stage 2
    // (the rebirth turn) must still be reachable.
    GameContext gc(CharacterClass::IRONCLAD, 0x45, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::AWAKENED_ONE);

    bc.setState(InputState::EXECUTING_ACTIONS);
    bc.addToBot(Actions::DamageEnemy(2, 9999)); // Awakened One stage 1 dies first
    bc.addToBot(Actions::DamageEnemy(0, 9999)); // cultist
    bc.addToBot(Actions::DamageEnemy(1, 9999)); // cultist -> monstersAlive 0
    bc.executeActions();

    if (bc.outcome != Outcome::UNDECIDED) {
        std::cout << "awakened_one_stage2 FAIL: outcome=" << (int)bc.outcome
                  << " (expected UNDECIDED=" << (int)Outcome::UNDECIDED << ")\n";
        ++failures;
    }
    if (!bc.monsters.arr[2].isHalfDead()) {
        std::cout << "awakened_one_stage2 FAIL: Awakened One not half-dead after stage 1\n";
        ++failures;
    }
    if (bc.monsters.monstersAlive != 0) {
        std::cout << "awakened_one_stage2 FAIL: monstersAlive=" << bc.monsters.monstersAlive
                  << " (expected 0)\n";
        ++failures;
    }

    // Stage 2 must still be playable: run the Awakened One's rebirth turn.
    bc.monsters.arr[2].takeTurn(bc);
    if (bc.monsters.arr[2].isHalfDead()) {
        std::cout << "awakened_one_stage2 FAIL: still half-dead after rebirth turn\n";
        ++failures;
    }
    if (!bc.monsters.arr[2].hasStatus<MS::MINION_LEADER>()) {
        std::cout << "awakened_one_stage2 FAIL: no MINION_LEADER after rebirth (stage 2 missing)\n";
        ++failures;
    }
    if (bc.monsters.monstersAlive != 1) {
        std::cout << "awakened_one_stage2 FAIL: monstersAlive=" << bc.monsters.monstersAlive
                  << " after rebirth (expected 1)\n";
        ++failures;
    }

    if (failures == 0) {
        std::cout << "awakened_one_stage2 PASS\n";
        return 0;
    }
    std::cout << "awakened_one_stage2 FAIL (" << failures << " checks)\n";
    return 1;
}

// Issue #52: PoisonLoseHpAction must not be an empty stub. A poisoned monster
// takes poison damage (ignoring block) at end of turn and its poison counter
// decreases by 1.
int testPoisonLoseHp() {
    int failures = 0;

    GameContext gc(CharacterClass::IRONCLAD, 0x45, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);

    Monster &m = bc.monsters.arr[0];
    m.curHp = 20;
    m.maxHp = 20;
    m.block = 10;
    m.addDebuff<MS::POISON>(5);

    Actions::PoisonLoseHpAction(0).actFunc(bc);

    if (m.curHp != 15) {
        std::cout << "poison_lose_hp FAIL: curHp=" << m.curHp
                  << " (expected 15; poison damage must be applied)\n";
        ++failures;
    }
    if (m.block != 10) {
        std::cout << "poison_lose_hp FAIL: block=" << m.block
                  << " (expected 10; poison damage must ignore block)\n";
        ++failures;
    }
    if (m.getStatus<MS::POISON>() != 4) {
        std::cout << "poison_lose_hp FAIL: poison=" << m.getStatus<MS::POISON>()
                  << " (expected 4 after tick)\n";
        ++failures;
    }

    if (failures == 0) {
        std::cout << "poison_lose_hp PASS\n";
        return 0;
    }
    std::cout << "poison_lose_hp FAIL (" << failures << " checks)\n";
    return 1;
}

// Issue #57: TimeEaterPlayCardQueueItem must use the replayed card's own
// exhaust property, not the triggering card's.
int testTimeEaterExhaust() {
    int failures = 0;

    GameContext gc(CharacterClass::IRONCLAD, 0x45, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::TIME_EATER);

    // Triggering card is a non-exhaust Strike; the replayed card is Fiend
    // Fire (exhausts). The replayed item must exhaust.
    bc.curCardQueueItem = CardQueueItem(CardInstance(CardId::STRIKE_RED), 0, 1);
    CardQueueItem replayed(CardInstance(CardId::FIEND_FIRE), 0, 1);
    replayed.exhaustOnUse = false;

    Actions::TimeEaterPlayCardQueueItem(replayed).actFunc(bc);

    if (!bc.curCardQueueItem.exhaustOnUse) {
        std::cout << "time_eater_exhaust FAIL: replayed Fiend Fire did not exhaust\n";
        ++failures;
    }
    if (bc.curCardQueueItem.card.getId() != CardId::FIEND_FIRE) {
        std::cout << "time_eater_exhaust FAIL: curCardQueueItem card is not the replayed card\n";
        ++failures;
    }
    if (bc.curCardQueueItem.triggerOnUse) {
        std::cout << "time_eater_exhaust FAIL: triggerOnUse not cleared for replay\n";
        ++failures;
    }

    if (failures == 0) {
        std::cout << "time_eater_exhaust PASS\n";
        return 0;
    }
    std::cout << "time_eater_exhaust FAIL (" << failures << " checks)\n";
    return 1;
}

int testDarklingVictory() {
    int failures = 0;

    // The last Darkling to die must NOT regrow: victory fires when all three
    // are dead even though the first two are half-dead (real StS
    // max-two-revives rule, pre-empted by victory at monstersAlive == 0). A
    // blanket "no monster half-dead" victory predicate would loop forever
    // here, so this guards the Awakened-One-only deferral in Monster::die.
    GameContext gc(CharacterClass::IRONCLAD, 0x46, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_DARKLINGS);

    bc.setState(InputState::EXECUTING_ACTIONS);
    bc.addToBot(Actions::DamageAllEnemy(9999)); // all 3 die; last one ends the fight
    bc.executeActions();

    if (bc.outcome != Outcome::PLAYER_VICTORY) {
        std::cout << "darkling_victory FAIL: outcome=" << (int)bc.outcome
                  << " (expected PLAYER_VICTORY=" << (int)Outcome::PLAYER_VICTORY << ")\n";
        ++failures;
    }

    if (failures == 0) {
        std::cout << "darkling_victory PASS\n";
        return 0;
    }
    std::cout << "darkling_victory FAIL (" << failures << " checks)\n";
    return 1;
}

namespace {

std::string oocSmithStateFingerprint(const GameContext &gc) {
    std::ostringstream out;
    out << static_cast<int>(gc.outcome) << ',' << static_cast<int>(gc.screenState) << ','
        << static_cast<int>(gc.info.selectScreenType) << ',' << gc.info.toSelectCount << ','
        << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ','
        << gc.blueKey << gc.greenKey << gc.redKey << ',' << gc.potionCount << ',';
    for (const auto potion : gc.potions) out << static_cast<int>(potion) << '/';
    out << '|';
    for (const auto &relic : gc.relics.relics) {
        out << static_cast<int>(relic.id) << ':' << relic.data << '/';
    }
    out << '|' << gc.deck.upgradeableCount << ',' << gc.deck.transformableCount << ',';
    for (const int bottle : gc.deck.bottleIdxs) out << bottle << '/';
    out << '|';
    for (const auto &card : gc.deck.cards) {
        out << static_cast<int>(card.id) << ':' << card.misc << ':' << card.upgraded << '/';
    }
    out << '|';
    for (const auto &candidate : gc.info.toSelectCards) {
        out << static_cast<int>(candidate.card.id) << ':' << candidate.card.misc << ':'
            << candidate.card.upgraded << ':' << candidate.deckIdx << '/';
    }
    out << '|';
    for (const auto &selected : gc.info.haveSelectedCards) {
        out << static_cast<int>(selected.card.id) << ':' << selected.card.misc << ':'
            << selected.card.upgraded << ':' << selected.deckIdx << '/';
    }
    const Random *rngs[] = {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
        &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
        &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
        &gc.shuffleRng, &gc.treasureRng};
    out << '|';
    for (const Random *rng : rngs) out << rng->counter << ':' << rng->seed0 << ':' << rng->seed1 << '/';
    const auto legal = search::GameAction::getAllActionsInState(gc);
    out << '|';
    for (const auto action : legal) out << action.bits << '/';
    return out.str();
}

GameContext oocSmithFixture() {
    GameContext gc(CharacterClass::IRONCLAD, 0x51514Du, 0);
    gc.screenState = ScreenState::REST_ROOM;
    gc.curRoom = Room::REST;
    gc.regainControlAction = [](GameContext &state) {
        state.screenState = ScreenState::MAP_SCREEN;
        state.regainControlAction = nullptr;
    };
    return gc;
}

const search::OocSemanticAction *findUpgradeAction(
        const std::vector<search::OocSemanticAction> &actions, CardId id, int bottleSlot = -1,
        int occurrence = 0) {
    for (const auto &action : actions) {
        const auto &target = std::get<search::OocCardTarget>(action.target);
        if (target.id == id && target.bottleSlot == bottleSlot
                && target.occurrence == occurrence) return &action;
    }
    return nullptr;
}

} // namespace

int testOocSemanticSmith() {
    auto fail = [](const std::string &message) {
        std::cout << "ooc_semantic_smith FAIL: " << message << '\n';
        return 1;
    };

    GameContext base = oocSmithFixture();
    base.deck.obtainRaw(Card(CardId::BASH, 1));
    const std::string beforeEnumeration = oocSmithStateFingerprint(base);
    const auto actions = search::enumerateCampfireUpgradeActions(base);
    const auto repeated = search::enumerateCampfireUpgradeActions(base);
    if (actions.size() < 3) return fail("normal campsite did not enumerate multiple targets");
    if (oocSmithStateFingerprint(base) != beforeEnumeration) return fail("enumeration mutated state or RNG");
    if (actions.size() != repeated.size()) return fail("repeated enumeration changed action count");
    for (std::size_t i = 0; i < actions.size(); ++i) {
        const auto key = search::canonicalOocSemanticActionKey(actions[i]);
        if (key != search::canonicalOocSemanticActionKey(repeated[i]))
            return fail("repeated enumeration changed canonical keys");
        if (i > 0 && search::canonicalOocSemanticActionKey(actions[i - 1]) >= key)
            return fail("canonical ordering is not deterministic and unique");
        if (std::get<search::OocCardTarget>(actions[i].target).upgraded) return fail("non-upgradeable card was enumerated");
    }
    const auto *bash = findUpgradeAction(actions, CardId::BASH);
    const auto *strike = findUpgradeAction(actions, CardId::STRIKE_RED);
    if (bash == nullptr || strike == nullptr) return fail("Bash or Strike target missing");
    if (search::canonicalOocSemanticActionKey(*bash)
            != "ooc:v1:effect=0:source=0:card=25:misc=0:upgraded=0:bottle=-1:occurrence=0") {
        return fail("canonical Bash key changed without a schema-version change");
    }

    {
        GameContext blocked = base;
        blocked.relics.add({RelicId::FUSION_HAMMER, 0});
        if (!search::enumerateCampfireUpgradeActions(blocked).empty())
            return fail("Fusion Hammer campsite enumerated Smith targets");
        const auto snapshot = oocSmithStateFingerprint(blocked);
        const auto result = search::executeOocSemanticAction(blocked, *bash);
        if (result.ok || !result.executedPrimitiveBits.empty()
                || oocSmithStateFingerprint(blocked) != snapshot)
            return fail("illegal Smith execution did not fail closed");
    }
    {
        GameContext wrong = base;
        wrong.screenState = ScreenState::MAP_SCREEN;
        const auto snapshot = oocSmithStateFingerprint(wrong);
        const auto result = search::executeOocSemanticAction(wrong, *bash);
        if (result.ok || oocSmithStateFingerprint(wrong) != snapshot)
            return fail("wrong-screen execution did not fail closed");
    }
    {
        GameContext stale = base;
        auto absent = *bash;
        std::get<search::OocCardTarget>(absent.target).id = CardId::DEMON_FORM;
        const auto snapshot = oocSmithStateFingerprint(stale);
        const auto result = search::executeOocSemanticAction(stale, absent);
        if (result.ok || !result.executedPrimitiveBits.empty()
                || oocSmithStateFingerprint(stale) != snapshot)
            return fail("absent target did not fail before primitive execution");
    }
    {
        GameContext stale = base;
        auto upgraded = *bash;
        std::get<search::OocCardTarget>(upgraded.target).upgraded = true;
        const auto snapshot = oocSmithStateFingerprint(stale);
        const auto result = search::executeOocSemanticAction(stale, upgraded);
        if (result.ok || oocSmithStateFingerprint(stale) != snapshot)
            return fail("already-upgraded target did not fail closed");
    }
    {
        GameContext stale = base;
        for (int i = 0; i < stale.deck.size(); ++i) {
            if (stale.deck.cards[i].id == CardId::BASH && !stale.deck.cards[i].upgraded) {
                stale.deck.upgrade(i);
                break;
            }
        }
        const auto snapshot = oocSmithStateFingerprint(stale);
        const auto result = search::executeOocSemanticAction(stale, *bash);
        if (result.ok || !result.executedPrimitiveBits.empty()
                || oocSmithStateFingerprint(stale) != snapshot)
            return fail("target upgraded after enumeration did not fail closed");
    }

    GameContext semanticBranch = base;
    GameContext manualBranch = base;
    const auto semanticResult = search::executeOocSemanticAction(semanticBranch, *bash);
    if (!semanticResult.ok) return fail("Bash semantic execution failed: " + semanticResult.error);
    if (semanticResult.executedPrimitiveBits.size() != 2
            || semanticResult.executedPrimitiveBits[0] != search::GameAction(1).bits)
        return fail("semantic execution did not record Smith then selection");
    const search::GameAction manualSmith(1);
    if (!manualSmith.isValidAction(manualBranch)) return fail("manual Smith primitive was not legal");
    manualSmith.execute(manualBranch);
    int manualBashIdx = -1;
    for (int i = 0; i < manualBranch.info.toSelectCards.size(); ++i) {
        if (manualBranch.info.toSelectCards[i].card.id == CardId::BASH
                && !manualBranch.info.toSelectCards[i].card.upgraded) {
            manualBashIdx = i;
            break;
        }
    }
    if (manualBashIdx < 0) return fail("manual branch could not resolve Bash");
    const search::GameAction manualSelect(manualBashIdx);
    if (!manualSelect.isValidAction(manualBranch)) return fail("manual Bash selection was not legal");
    manualSelect.execute(manualBranch);
    if (semanticResult.executedPrimitiveBits[1] != manualSelect.bits)
        return fail("recorded selection primitive differs from independent manual resolution");
    if (oocSmithStateFingerprint(semanticBranch) != oocSmithStateFingerprint(manualBranch))
        return fail("semantic and manual Smith successors differ");

    {
        GameContext different = base;
        const auto result = search::executeOocSemanticAction(different, *strike);
        if (!result.ok) return fail("different target execution failed: " + result.error);
        int upgradedStrikeCount = 0;
        int upgradedBashCount = 0;
        for (const auto &card : different.deck.cards) {
            upgradedStrikeCount += card.id == CardId::STRIKE_RED && card.upgraded;
            upgradedBashCount += card.id == CardId::BASH && card.upgraded;
        }
        if (upgradedStrikeCount != 1 || upgradedBashCount != 1)
            return fail("selecting Strike changed the wrong card");
    }

    {
        GameContext duplicates = oocSmithFixture();
        duplicates.deck.obtainRaw(Card(CardId::BASH));
        const auto equivalent = search::enumerateCampfireUpgradeActions(duplicates);
        int unbottledBashActions = 0;
        for (const auto &action : equivalent) {
            const auto &target = std::get<search::OocCardTarget>(action.target);
            unbottledBashActions += target.id == CardId::BASH && target.bottleSlot == -1;
        }
        if (unbottledBashActions != 2)
            return fail("duplicate Bash occurrences did not preserve distinct ordered successors");
        const auto *secondBash = findUpgradeAction(equivalent, CardId::BASH, -1, 1);
        if (secondBash == nullptr) return fail("second equivalent Bash occurrence is not addressable");
        GameContext secondBranch = duplicates;
        const auto secondResult = search::executeOocSemanticAction(secondBranch, *secondBash);
        if (!secondResult.ok || !secondBranch.deck.cards[secondBranch.deck.size() - 1].upgraded)
            return fail("second equivalent Bash occurrence resolved incorrectly");

        int extraBashIdx = -1;
        for (int i = duplicates.deck.size() - 1; i >= 0; --i) {
            if (duplicates.deck.cards[i].id == CardId::BASH) { extraBashIdx = i; break; }
        }
        duplicates.deck.bottleCard(extraBashIdx, CardType::ATTACK);
        const auto distinguishable = search::enumerateCampfireUpgradeActions(duplicates);
        const auto *plainBash = findUpgradeAction(distinguishable, CardId::BASH, -1);
        const auto *bottledBash = findUpgradeAction(distinguishable, CardId::BASH, 0);
        if (plainBash == nullptr || bottledBash == nullptr)
            return fail("bottled and unbottled duplicate Bash targets were not distinguished");
        const auto result = search::executeOocSemanticAction(duplicates, *bottledBash);
        if (!result.ok || !duplicates.deck.cards[extraBashIdx].upgraded
                || duplicates.deck.bottleIdxs[0] != extraBashIdx)
            return fail("bottled duplicate did not resolve to the bottled card");
    }

    std::cout << "ooc_semantic_smith PASS\n";
    return 0;
}

int main(int argc, const char* argv[]) {

    if (argc < 2) {
        std::cout << "incorrect arguments" << std::endl;
        return 0;
    }

    const std::string command(argv[1]);

    if (command == "replay") {
        const std::uint64_t seed = std::stoull(argv[2]);
        const int ascension = std::stoi(argv[3]);
        const std::string actionFile(argv[4]);
        replayActionFile(GameContext(sts::CharacterClass::IRONCLAD, seed, ascension), actionFile);

    } else if (command == "save") {
        playFromSaveFile(argv[2], argv[3]);

    } if (command == "agent_mt") { // actually doing tree search now
        const int threadCount(std::stoi(argv[2]));
        const int depthArg = std::stoi(argv[3]);
        const int ascensionIn = std::stoi(argv[4]);
        const std::uint64_t startSeedLong(std::stoull(argv[5]));
        const int playoutCount(std::stoi(argv[6]));
        const int printLevel = std::stoi(argv[7]);
        g_print_level = printLevel;
        g_searchAscension = ascensionIn;
        g_simulationCount = depthArg;

        agentMt(threadCount, startSeedLong, playoutCount);

    } if (command == "simple_agent_mt") { // actually doing tree search now
        const int threadCount(std::stoi(argv[2]));
        const std::uint64_t startSeedLong(std::stoull(argv[3]));
        const int playoutCount(std::stoi(argv[4]));

        bool print = false;
        if (argc > 5) {
            print = true;
        }

        search::SimpleAgent::runAgentsMt(threadCount, startSeedLong, playoutCount, print);

    } else if (command == "json") {
        const std::string saveFilePath(argv[2]);
        const std::string jsonOutPath(argv[3]);
        std::ofstream outFileStream(jsonOutPath);
        outFileStream << SaveFile::getJsonFromSaveFile(saveFilePath);
        outFileStream.close();

    } else if (command == "json_to_save") {
        const std::string jsonInPath(argv[2]);
        const std::string saveFileOutPath(argv[3]);

        std::ifstream jsonIfStream(jsonInPath);
        SaveFile::writeJsonToSaveFile(jsonIfStream, saveFileOutPath);

    }  else if (command == "scum_searcher") {
        const std::uint64_t startSeedLong(std::stoull(argv[2]));
        const int playoutCount(std::stoi(argv[3]));

        for (std::uint64_t seed = startSeedLong; seed < startSeedLong+playoutCount; ++seed) {
//            playRandom4(startSeedLong);
        }

    } else if (command == "mcts_save") {
        return mcts(argc, argv);

    } else if (command == "seed_contract") {
        return testSeedContract(std::stoull(argv[2]));

    } else if (command == "belief") {
        return testBelief();

    } else if (command == "drawpile") {
        return testDrawpile(std::stoull(argv[2]));

    } else if (command == "obs_identity") {
        return testObsIdentity(std::stoull(argv[2]));
    } else if (command == "s3_strategy_fusion_diag") {
        return testS3StrategyFusionDiag(std::stoull(argv[2]));
    } else if (command == "s3_persistent_endturn_chance") {
        return testS3PersistentEndTurnChance(std::stoull(argv[2]));

    } else if (command == "prune") {
        return testPrune(std::stoull(argv[2]));
    } else if (command == "happy_flower") {
        return testHappyFlowerCounter(std::stoull(argv[2]));
    } else if (command == "issue_fixes") {
        return testIssueFixes();
    } else if (command == "relic_reward_sapphire") {
        return testRelicRewardSapphire();
    } else if (command == "cardselect_parity") {
        return testCardSelectParity();
    } else if (command == "scum_nonfair_empty_edges") {
        return testScumNonFairEmptyEdges();
    } else if (command == "scum_convroot_stale_outcome") {
        return testScumConvRootStaleOutcome();
    } else if (command == "cardselect_canonical") {
        return testCardSelectCanonical();
    } else if (command == "battlecontext_roundtrip") {
        return testBattleContextRoundtrip();
    } else if (command == "designer_in_spire") {
        return testDesignerInSpireOptions();
    } else if (command == "cardqueue_overflow") {
        return testCardQueueOverflow();
    } else if (command == "keys_collect") {
        return testKeyCollection();
    } else if (command == "semantic_card_edges") {
        return testSemanticCardEdges();
    } else if (command == "s3_drawpile_reuse_boundary") {
        return testS3DrawPileIndexReuseBoundary();
    } else if (command == "draw_prob_helper") {
        return testDrawProbHelper();
    } else if (command == "draw_prob_engine") {
        return testDrawProbEngine();
    } else if (command == "belief_order_invariance") {
        return testBeliefOrderInvariance();
    } else if (command == "real_belief_filter") {
        return testRealBeliefFilter(std::stoull(argv[2]));
    } else if (command == "persistent_belief_transfer") {
        return testPersistentBeliefTransfer(std::stoull(argv[2]));
    } else if (command == "rng_state_propagation") {
        return testRngStatePropagation(std::stoull(argv[2]));
    } else if (command == "s3_rand64_prior_sampler") {
        return testS3Rand64PriorSampler();
    } else if (command == "rejuv_history_replay") {
        return testRejuvHistoryReplay(std::stoull(argv[2]));
    } else if (command == "rejuv_semantic_select") {
        return testRejuvSemanticSelect();
    } else if (command == "rejuv_noninterference") {
        return testRejuvNoninterference(std::stoull(argv[2]));
    } else if (command == "rejuv_conditional_blocks") {
        return testRejuvConditionalBlocks();
    } else if (command == "live_rejuv_attempt_gate") {
        return testLiveRejuvenationAttemptGate();
    } else if (command == "belief_immutability") {
        return testBeliefImmutability();
    } else if (command == "thorns_retaliation") {
        return testThornsRetaliationVictory();
    } else if (command == "awakened_one_stage2") {
        return testAwakenedOneStage2();
    } else if (command == "darkling_victory") {
        return testDarklingVictory();
    } else if (command == "poison_lose_hp") {
        return testPoisonLoseHp();
    } else if (command == "time_eater_exhaust") {
        return testTimeEaterExhaust();
    } else if (command == "simhealth_gamble_empty_hand") {
        return testSimHealthGambleEmptyHand();
    } else if (command == "gamblers_brew_legality") {
        return testGamblersBrewLegality();
    } else if (command == "simhealth_nonfair_s2_empty") {
        return testSimHealthNonFairS2Empty();
    } else if (command == "simhealth_selection_failure") {
        return testSimHealthSelectionFailure();
    } else if (command == "simhealth_nonfair_s2_selection_failed") {
        return testSimHealthNonFairS2SelectionFailed();
    } else if (command == "training_integrity") {
        return testTrainingIntegrity();
    } else if (command == "e2c_observer_scope") {
        return testE2cObserverScope();
    } else if (command == "combat_transition_oracle") {
        return testCombatTransitionOracle();
    } else if (command == "combat_knowledge") {
        return testCombatKnowledgeBoundary();
    } else if (command == "silver_random_bridge") {
        return testSilverRandomBridge();
    } else if (command == "silver_semantic_action") {
        return testSilverSemanticActionResolution();
    } else if (command == "ooc_semantic") {
        return runOocSemanticTests();
    } else if (command == "ooc_semantic_pipeline") {
        return runOocSemanticPipelineTests();
    } else if (command == "ooc_semantic_transactions") {
        return runOocSemanticTransactionsTests();
    } else if (command == "ironclad_card_coverage") {
        return testIroncladCombatCardCoverage();
    } else if (command == "ooc_reward_continuation") {
        return runOocRewardContinuationTests();
    } else if (command == "ooc_semantic_smith") {
        return testOocSemanticSmith();
    } else if (command == "simhealth_load") {
        if (argc < 3) {
            std::cout << "usage: test simhealth_load <capture.bin>\n";
            return 1;
        }
        return simHealthLoad(argv[2]);
    }

    //    printSizes();
//    std::cout << SeedHelper::getString(77) << '\n';
//    playRandom();
//    std::cout << getSeedWithGuardian();
//    replayActionList(argv[1]);

    if (command == "replay" || command == "save" || command == "agent_mt" ||
        command == "simple_agent_mt" || command == "json" ||
        command == "json_to_save" || command == "scum_searcher") {
        return 0;
    }

    std::cerr << "unknown test command: " << command << '\n';
    return 2;
}
