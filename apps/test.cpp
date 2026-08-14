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
#include "combat/BattleContextBinary.h"
#include "constants/MonsterMoves.h"
#include "test_belief.h"

using namespace sts;

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
// counter underflow), #69 (Smoke Bomb drink no-op), and #68 (stale multi-select
// validation outside CARD_SELECT input state).
static BattleContext cardSelectFixture(CardSelectTask task, int pickCount, bool largeHand);
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

    // #69: drinking a Smoke Bomb must be refused without consuming it.
    {
        GameContext gc(CharacterClass::IRONCLAD, 0xABCDEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.potionCapacity = 3;
        bc.potions[0] = Potion::SMOKE_BOMB;
        bc.potionCount = 1;
        bc.drinkPotion(0);
        if (bc.potions[0] != Potion::SMOKE_BOMB || bc.potionCount != 1) {
            return fail("smoke bomb consumed despite combat-use guard");
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

// BattleContext binary round-trip contract (frontiergen/leafrelabel, plan
// "combat-value targets": phases 2-3). The serializer captures the visible
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
    }

    auto ordinary = cardSelectFixture(CardSelectTask::HOLOGRAM, 1, false);
    check(!search::isDrawPileIndexSensitiveCardSelect(ordinary),
          "unrelated card-select task classified as sensitive");
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

    } else if (command == "prune") {
        return testPrune(std::stoull(argv[2]));
    } else if (command == "happy_flower") {
        return testHappyFlowerCounter(std::stoull(argv[2]));
    } else if (command == "issue_fixes") {
        return testIssueFixes();
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

    return 0;
}