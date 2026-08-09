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
#include "combat/BattleContextBinary.h"
#include "constants/MonsterMoves.h"

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

static bool sameDrawOrder(const sts::HiddenBattleState &a, const sts::HiddenBattleState &b) {
    if (a.drawPileOrder.size() != b.drawPileOrder.size()) return false;
    for (size_t i = 0; i < a.drawPileOrder.size(); ++i)
        if (a.drawPileOrder[i].getId() != b.drawPileOrder[i].getId()) return false;
    return true;
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

int testBelief() {
    CombatObservation obs;
    obs.drawPileContents = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};

    Belief b;
    b.particles.resize(2);
    b.particles[0].drawPileOrder = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};
    b.particles[1].drawPileOrder = {CardInstance(CardId::DEFEND_RED), CardInstance(CardId::STRIKE_RED)};
    b.update(obs);
    if (b.particles[0].weight != 1.0 || b.particles[1].weight != 0.0) {
        std::cout << "belief FAIL: contradictory particle not zeroed\n";
        return 1;
    }
    std::mt19937_64 rng(12345);
    for (int i = 0; i < 1000; ++i) {
        const HiddenBattleState &s = b.sample(rng);
        if (sameDrawOrder(s, b.particles[1])) {
            std::cout << "belief FAIL: zero-weight particle sampled\n";
            return 1;
        }
    }

    // All particles contradictory: weighted sampling must fall back to uniform
    CombatObservation unobserved;
    unobserved.drawPileContents = {CardInstance(CardId::STRIKE_RED),
                                   CardInstance(CardId::DEFEND_RED),
                                   CardInstance(CardId::STRIKE_RED)};
    Belief u;
    u.particles.resize(2);
    u.particles[0].drawPileOrder = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};
    u.particles[1].drawPileOrder = {CardInstance(CardId::DEFEND_RED), CardInstance(CardId::STRIKE_RED)};
    u.update(unobserved);
    if (u.particles[0].weight != 0.0 || u.particles[1].weight != 0.0) {
        std::cout << "belief FAIL: unobservable draw not zeroed\n";
        return 1;
    }
    int seen0 = 0, seen1 = 0;
    for (int i = 0; i < 1000; ++i) {
        const HiddenBattleState &s = u.sample(rng);
        if (sameDrawOrder(s, u.particles[0])) ++seen0;
        else if (sameDrawOrder(s, u.particles[1])) ++seen1;
        else {
            std::cout << "belief FAIL: unknown particle sampled\n";
            return 1;
        }
    }
    if (seen0 == 0 || seen1 == 0) {
        std::cout << "belief FAIL: uniform fallback not uniform\n";
        return 1;
    }
    std::cout << "belief PASS\n";
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
    if (n > 0 && n <= 10) {
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
        if (pot == Potion::INVALID || pot == Potion::EMPTY_POTION_SLOT || pot == Potion::FAIRY_POTION) continue;
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
    } else if (command == "cardselect_parity") {
        return testCardSelectParity();
    } else if (command == "cardselect_canonical") {
        return testCardSelectCanonical();
    } else if (command == "battlecontext_roundtrip") {
        return testBattleContextRoundtrip();
    }

    //    printSizes();
//    std::cout << SeedHelper::getString(77) << '\n';
//    playRandom();
//    std::cout << getSeedWithGuardian();
//    replayActionList(argv[1]);

    return 0;
}