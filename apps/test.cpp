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

#include "sim/search/CombatObservation.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/SimHealth.h"
#include "sim/search/TrainingIntegrity.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/OocSemanticAction.h"
#include "combat/BattleContextBinary.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireState.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SearchRng.h"
#include "one_combat/combat_transition.h"
#include "ooc_test_state.h"
#include "constants/MonsterMoves.h"

int runOocRewardContinuationTests();
int runOocSemanticTests();
int runOocSemanticPipelineTests();
int runOocSemanticTransactionsTests();

using namespace sts;

int testCardPile() {
    int failures = 0;
    auto check = [&](bool ok, const char *what) {
        if (!ok) {
            std::cerr << "card_pile FAIL: " << what << '\n';
            ++failures;
        }
    };
    auto card = [](CardId id, int uid) {
        CardInstance c(id);
        c.uniqueId = static_cast<std::int16_t>(uid);
        return c;
    };
    const auto strike = card(CardId::STRIKE_RED, 1);
    const auto defend = card(CardId::DEFEND_RED, 2);
    const auto bash = card(CardId::BASH, 3);
    const auto anger = card(CardId::ANGER, 4);
    const auto wound = card(CardId::WOUND, 5);

    // Concrete mode reproduces the original vector operations.
    {
        CardPile pile {strike, defend, bash};
        std::vector<CardInstance> legacy {strike, defend, bash};
        Random a(7);
        Random b(7);
        pile.shuffleIn(a, wound);
        const int idx = b.random(static_cast<int>(legacy.size()) - 1);
        legacy.insert(legacy.begin() + idx, wound);
        check(std::equal(pile.begin(), pile.end(), legacy.begin(), legacy.end()) && a == b,
              "concrete shuffleIn matches legacy insert");
        Random c(9);
        const auto top = pile.drawTop(c);
        check(top == legacy.back() && c == Random(9), "concrete draw pops the top without RNG");
        pile.addToBottom(anger);
        check(pile.front() == anger && pile.isConcrete() && pile.knownTop() == 0, "concrete addToBottom");
    }

    // Information-set piles compare equal regardless of the unknown order.
    {
        CardPile x;
        CardPile y;
        x.assignInformationState({}, {strike, defend, bash}, {});
        y.assignInformationState({}, {bash, strike, defend}, {});
        check(x == y && !x.isConcrete(), "unknown region is canonical");
        CardPile z;
        z.assignInformationState({}, {strike, defend}, {bash});
        check(!(x == z), "known top differs from unknown");
    }

    // A known top draws without RNG; the unknown region samples with RNG.
    {
        CardPile pile;
        pile.assignInformationState({anger}, {strike, defend}, {bash});
        Random rng(11);
        const auto first = pile.drawTop(rng);
        check(first == bash && rng.counter == 0 && pile.knownTop() == 0, "known top pops first");
        const auto second = pile.drawTop(rng);
        check((second == strike || second == defend) && rng.counter == 1, "unknown draw uses RNG");
        const auto third = pile.drawTop(rng);
        check((third == strike || third == defend) && !(third == second) && rng.counter == 1,
              "last unknown card draws without RNG");
        const auto fourth = pile.drawTop(rng);
        check(fourth == anger && pile.empty() && rng.counter == 1, "known bottom drawn last");
    }

    // Unknown draws are uniform.
    {
        int counts[3] = {};
        for (int seed = 1; seed <= 3000; ++seed) {
            CardPile pile;
            pile.assignInformationState({}, {strike, defend, bash}, {});
            Random rng(static_cast<std::uint64_t>(seed));
            const auto c = pile.drawTop(rng);
            counts[c == strike ? 0 : c == defend ? 1 : 2]++;
        }
        check(counts[0] > 900 && counts[1] > 900 && counts[2] > 900, "unknown draw distribution");
    }

    // Placement, removal, reshuffle and mutation keep the invariants.
    {
        CardPile pile;
        pile.assignInformationState({}, {strike, defend, bash}, {});
        pile.addToTop(anger);
        pile.addToBottom(wound);
        check(pile.knownTop() == 1 && pile.knownBottom() == 1 && pile.back() == anger
              && pile.front() == wound, "known placements");
        pile.removeAt(pile.size() - 1);
        pile.removeAt(0);
        check(pile.knownTop() == 0 && pile.knownBottom() == 0 && pile.size() == 3, "removal bookkeeping");
        std::vector<CardInstance> discard {wound, anger};
        pile.absorbUnordered(discard);
        check(discard.empty() && pile.size() == 5 && std::is_sorted(pile.begin(), pile.end()),
              "absorb forgets order");
        Random rng(3);
        pile.addToTop(strike);
        pile.reshuffleSelf(rng);
        check(rng.counter == 0 && pile.knownTop() == 0 && std::is_sorted(pile.begin(), pile.end()),
              "information-set reshuffle uses no RNG");
        pile.mutateAll([](CardInstance &c) { c.upgrade(); });
        check(std::is_sorted(pile.begin(), pile.end()), "mutation keeps unknown region sorted");
    }

    // Shuffling into a pile with no known top promotes a sampled top card.
    {
        CardPile pile;
        pile.assignInformationState({}, {strike, defend, bash}, {});
        Random rng(5);
        pile.shuffleIn(rng, wound);
        check(pile.size() == 4 && pile.knownTop() == 1 && rng.counter >= 1, "shuffleIn promotes the next draw");
    }

    std::cout << "card_pile " << (failures == 0 ? "PASS" : "FAIL") << '\n';
    return failures == 0 ? 0 : 1;
}

// Whole battles run with the draw pile in information-set mode: every engine
// path that touches the draw pile must work there (no crash, battles finish,
// card counts are conserved apart from cards created or removed in combat).
int testCardPileEngine() {
    int failures = 0;
    const MonsterEncounter encounters[] = {
        MonsterEncounter::JAW_WORM, MonsterEncounter::CULTIST,
        MonsterEncounter::GREMLIN_NOB, MonsterEncounter::LAGAVULIN,
        MonsterEncounter::THE_GUARDIAN, MonsterEncounter::HEXAGHOST,
        MonsterEncounter::SLIME_BOSS, MonsterEncounter::BOOK_OF_STABBING,
        MonsterEncounter::AUTOMATON, MonsterEncounter::CHAMP,
        MonsterEncounter::THREE_SENTRIES, MonsterEncounter::CHOSEN,
        MonsterEncounter::NEMESIS, MonsterEncounter::TIME_EATER,
        MonsterEncounter::WRITHING_MASS, MonsterEncounter::AWAKENED_ONE,
    };
    // Cards that place, shuffle in, draw from, reshuffle or search the draw pile.
    const CardId extras[] = {
        CardId::HEADBUTT, CardId::WARCRY, CardId::HAVOC, CardId::WILD_STRIKE,
        CardId::RECKLESS_CHARGE, CardId::POWER_THROUGH, CardId::BATTLE_TRANCE,
        CardId::POMMEL_STRIKE, CardId::SHRUG_IT_OFF, CardId::TRUE_GRIT,
        CardId::SECOND_WIND, CardId::EXHUME, CardId::DEEP_BREATH,
        CardId::FORETHOUGHT, CardId::MASTER_OF_STRATEGY, CardId::SECRET_TECHNIQUE,
        CardId::SECRET_WEAPON, CardId::VIOLENCE, CardId::APOTHEOSIS, CardId::EVOLVE,
    };
    int finished = 0;
    int wins = 0;
    long long turns = 0;
    for (std::uint64_t seed = 1; seed <= 60; ++seed) {
        for (const auto encounter : encounters) {
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            for (int i = 0; i < 6; ++i) {
                gc.deck.obtainRaw(Card(extras[(seed * 7 + i * 3) % std::size(extras)]));
            }
            BattleContext bc;
            bc.init(gc, encounter);
            std::vector<CardInstance> unknown(bc.cards.drawPile.begin(), bc.cards.drawPile.end());
            bc.cards.drawPile.assignInformationState({}, unknown, {});
            search::SimpleAgent agent;
            agent.curGameContext = &gc;
            agent.playoutBattle(bc);
            if (bc.outcome == Outcome::UNDECIDED) {
                std::cerr << "card_pile_engine FAIL: unfinished battle seed " << seed << '\n';
                ++failures;
                continue;
            }
            ++finished;
            wins += bc.outcome == Outcome::PLAYER_VICTORY;
            turns += bc.turn;
            if (bc.cards.drawPile.isConcrete()) {
                std::cerr << "card_pile_engine FAIL: pile became concrete, seed " << seed << '\n';
                ++failures;
            }
        }
    }
    std::cout << "card_pile_engine battles=" << finished << " wins=" << wins << " turns=" << turns << ' '
              << (failures == 0 ? "PASS" : "FAIL") << '\n';
    return failures == 0 ? 0 : 1;
}

namespace {

    BattleContext silverSearchRoot(const BattleContext &real) {
        BattleContext root = real;
        std::vector<CardInstance> unknown(real.cards.drawPile.begin(), real.cards.drawPile.end());
        root.cards.drawPile.assignInformationState({}, unknown, {});
        search::seedSearchRng(root, real.seed ^ 0x5EA5C4u);   // never the live streams
        return root;
    }

    struct SilverBattleResult {
        Outcome outcome = Outcome::UNDECIDED;
        int hp = 0;
        int turn = 0;
        int decisions = 0;
        int reroots = 0;
        std::vector<std::uint32_t> actions;
        std::vector<search::SearchRngState> rng;
    };

    SilverBattleResult playBattleWithSilverSearcher(std::uint64_t seed, MonsterEncounter encounter, int sims, bool profileEnabled = false) {
        GameContext gc(CharacterClass::IRONCLAD, seed, 0);
        BattleContext bc;
        bc.init(gc, encounter);
        search::SilverSearchContext context;
        context.act = gc.act;
        std::unique_ptr<search::SilverSearcher> searcher;
        SilverBattleResult result;
        while (bc.outcome == Outcome::UNDECIDED && result.decisions < 2000) {
            const auto root = silverSearchRoot(bc);
            search::SilverSearcher::Node *node = searcher ? searcher->findNode(root) : nullptr;
            if (node != nullptr && !node->isRandomNode) {
                searcher->rerootAt(node, searcher->nodeCount() >= 32768);
                ++result.reroots;
            } else if (searcher) {
                searcher->setRoot(root);
            } else {
                searcher = std::make_unique<search::SilverSearcher>(root, context);
            }
            search::SilverTreeProfile profile;
            searcher->profile = profileEnabled ? &profile : nullptr;
            searcher->search(sims);
            searcher->profile = nullptr;
            if (profileEnabled && profile.completed != sims)
                throw std::runtime_error("profile denominator includes inherited visits or misses simulations");
            const auto action = search::SilverSearcher::translateAction(
                searcher->bestAction(), searcher->rootSearchState(), bc);
            if (!action.isValidAction(bc)) {
                std::cerr << "silver_searcher: invalid action chosen\n";
                break;
            }
            result.actions.push_back(action.bits);
            action.execute(bc);
            result.rng.push_back(search::captureSearchRng(bc));
            ++result.decisions;
        }
        result.outcome = bc.outcome;
        result.hp = bc.player.curHp;
        result.turn = bc.turn;
        return result;
    }

}

int testSilverSearcher() {
    int failures = 0;
    auto check = [&](bool ok, const char *what) {
        if (!ok) {
            std::cerr << "silver_searcher FAIL: " << what << '\n';
            ++failures;
        }
    };

    // Exact endpoint/depth fixtures and opt-in observational parity.
    {
        using Profile = search::SilverTreeProfile;
        const GameContext gc(CharacterClass::IRONCLAD, 0x5EEDu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        bc.monsters.arr[0].curHp = 1;
        bc.monsters.arr[0].block = 0;
        bc.cards.cardsInHand = 1;
        bc.cards.hand[0] = CardInstance(CardId::STRIKE_RED);
        bc.cards.hand[0].uniqueId = 81;
        search::SilverSearcher searcher(silverSearchRoot(bc), {});
        check(searcher.profile == nullptr, "profiling defaults off");
        Profile profile;
        searcher.profile = &profile;
        searcher.search(1);
        check(profile.completed == 1 && profile.endpoints[Profile::VICTORY].tree[1] == 1
              && profile.endpoints[Profile::VICTORY].total[1] == 1,
              "one lethal action ends at tree/total depth one");
        BattleContext stochastic;
        stochastic.init(gc, MonsterEncounter::CULTIST);
        stochastic.player.energy = 0;
        search::SilverSearcher chanceSearcher(silverSearchRoot(stochastic), {});
        Profile chanceProfile;
        chanceSearcher.profile = &chanceProfile;
        chanceSearcher.search(1);
        std::int64_t depthOne = 0;
        for (const auto &endpoint : chanceProfile.endpoints) {
            const auto it = endpoint.tree.find(1);
            if (it != endpoint.tree.end()) depthOne += it->second;
        }
        check(chanceSearcher.stats.chanceOutcomesSampled > 0 && depthOne == 1,
              "chance outcome edge does not add another action to tree depth");
        bc.inputState = InputState::CHOOSE_STANCE_ACTION;
        searcher.setRoot(silverSearchRoot(bc));
        profile = {};
        searcher.search(3);
        searcher.search(4);
        check(profile.completed == 7 && profile.endpoints[Profile::NONTERMINAL].tree[0] == 7
              && profile.endpoints[Profile::NONTERMINAL].total[0] == 7,
              "no-action nonterminal root and chunked denominator are exact");
        bc.outcome = Outcome::PLAYER_LOSS;
        bc.player.curHp = 0;
        profile = {};
        profile.record(bc, 2, 3);
        check(profile.endpoints[Profile::DEATH].tree[2] == 1
              && profile.endpoints[Profile::DEATH].total[5] == 1, "death depths separate tree and rollout");
        bc.player.curHp = 20;
        profile.record(bc, 4, 0);
        check(profile.endpoints[Profile::ENGINE_STOP].tree[4] == 1, "non-death engine loss stays separate");
        bc.turn = 501;
        profile.record(bc, 5, 1);
        check(profile.endpoints[Profile::TURN_LIMIT].total[6] == 1, "turn limit stays separate");
        searcher.setRoot(silverSearchRoot(bc));
        profile = {};
        searcher.search(7);
        check(profile.completed == 0, "terminal-root initialization is not a completed simulation");

        const auto off = playBattleWithSilverSearcher(123, MonsterEncounter::CULTIST, 200);
        const auto on = playBattleWithSilverSearcher(123, MonsterEncounter::CULTIST, 200, true);
        check(off.actions == on.actions && off.rng == on.rng && off.hp == on.hp
              && off.turn == on.turn && off.outcome == on.outcome && off.reroots == on.reroots,
              "profile on/off preserves every action, all six RNG streams, and final result");
        check(on.reroots > 0, "profile parity fixture exercises rerooted searches");
    }

    // Lethal is found: a nearly dead Cultist and a Strike in hand.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x5EEDu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::SimpleAgent agent;
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        bc.monsters.arr[0].curHp = 3;
        bc.monsters.arr[0].block = 0;
        bc.cards.cardsInHand = 2;
        bc.cards.hand[0] = CardInstance(CardId::DEFEND_RED);
        bc.cards.hand[0].uniqueId = 80;
        bc.cards.hand[1] = CardInstance(CardId::STRIKE_RED);
        bc.cards.hand[1].uniqueId = 81;
        search::SilverSearcher searcher(silverSearchRoot(bc), {});
        searcher.search(300);
        const auto action = search::SilverSearcher::translateAction(
            searcher.bestAction(), searcher.rootSearchState(), bc);
        check(action.getActionType() == search::ActionType::CARD && action.getSourceIdx() == 1,
              "plays the lethal Strike");
    }

    // Playing a different physical copy of an equivalent card finds the node
    // the search expanded for the other copy, and its actions map back.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x5EEFu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        bc.cards.cardsInHand = 3;
        bc.cards.hand[0] = CardInstance(CardId::STRIKE_RED);
        bc.cards.hand[0].uniqueId = 90;
        bc.cards.hand[1] = CardInstance(CardId::STRIKE_RED);
        bc.cards.hand[1].uniqueId = 91;
        bc.cards.hand[2] = CardInstance(CardId::DEFEND_RED);
        bc.cards.hand[2].uniqueId = 92;
        const BattleContext root = silverSearchRoot(bc);
        search::SilverSearcher searcher(root, {});
        searcher.search(400);
        // The search expanded one Strike (the deduplicated edge); play the other.
        int expanded = -1;
        for (const auto &edge : searcher.rootNode().edges) {
            if (edge.action.getActionType() == search::ActionType::CARD
                    && root.cards.hand[edge.action.getSourceIdx()].id == CardId::STRIKE_RED) {
                expanded = edge.action.getSourceIdx();
            }
        }
        check(expanded >= 0, "search expanded a Strike");
        BattleContext played = root;
        search::Action(search::ActionType::CARD, expanded == 0 ? 1 : 0, 0).execute(played);
        check(searcher.findNode(played) == nullptr, "the other copy is a different exact state");
        auto *node = searcher.findNodeUpToEquivalentCopy(played);
        check(node != nullptr && node->simulationCount > 0, "equivalent-copy lookup finds the expanded child");
        if (node != nullptr) {
            searcher.rerootAt(node, false);
            searcher.search(50);
            const auto action = search::SilverSearcher::translateAction(
                searcher.bestAction(), searcher.rootSearchState(), played);
            check(action.isValidAction(played), "retained action maps onto the played state");
        }
        BattleContext changed = root;
        search::Action(search::ActionType::CARD, expanded == 0 ? 1 : 0, 0).execute(changed);
        for (int i = 0; i < changed.cards.cardsInHand; ++i) {
            if (changed.cards.hand[i].id == CardId::DEFEND_RED) changed.cards.hand[i].costForTurn = 0;
        }
        check(searcher.findNodeUpToEquivalentCopy(changed) == nullptr,
              "a non-equivalent card difference is not remapped");
    }

    // A root with one legal action exposes it without any simulation.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x5EEEu, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        bc.cards.cardsInHand = 0;
        for (auto &p : bc.potions) p = Potion::EMPTY_POTION_SLOT;
        bc.potionCount = 0;
        search::SilverSearcher searcher(silverSearchRoot(bc), {});
        check(searcher.prepareRootActions() == 1, "empty hand leaves one root action");
        check(searcher.rootNode().simulationCount == 0, "preparing root actions runs no simulation");
        check(searcher.bestAction().getActionType() == search::ActionType::END_TURN,
              "the sole root action is END_TURN");
        searcher.search(50);
        check(searcher.rootNode().edges.size() == 1 && searcher.rootNode().simulationCount == 50,
              "search after preparing root actions keeps the same edge");
    }

    // Whole battles: the search wins clearly more than the greedy rollout policy alone.
    const MonsterEncounter encounters[] = {
        MonsterEncounter::JAW_WORM, MonsterEncounter::GREMLIN_NOB, MonsterEncounter::LAGAVULIN,
        MonsterEncounter::THE_GUARDIAN, MonsterEncounter::HEXAGHOST, MonsterEncounter::SLIME_BOSS,
    };
    int searchWins = 0;
    int greedyWins = 0;
    int battles = 0;
    int decisions = 0;
    int reroots = 0;
    for (std::uint64_t seed = 1; seed <= 4; ++seed) {
        for (const auto encounter : encounters) {
            const auto r = playBattleWithSilverSearcher(seed, encounter, 200);
            check(r.outcome != Outcome::UNDECIDED, "battle finished");
            searchWins += r.outcome == Outcome::PLAYER_VICTORY;
            decisions += r.decisions;
            reroots += r.reroots;
            ++battles;

            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            BattleContext bc;
            bc.init(gc, encounter);
            search::SimpleAgent greedy;
            greedy.curGameContext = &gc;
            greedy.playoutBattle(bc);
            greedyWins += bc.outcome == Outcome::PLAYER_VICTORY;
        }
    }
    std::cout << "silver_searcher battles=" << battles << " searchWins=" << searchWins
              << " greedyWins=" << greedyWins << " decisions=" << decisions
              << " reroots=" << reroots << '\n';
    check(searchWins > greedyWins, "search beats the greedy policy");

    // Hidden intents (Runic Dome search mode): a pending roll is part of the
    // search state, search does not resolve it at the root, and materializing
    // it rolls a move.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0xD0E5u, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        BattleContext root = silverSearchRoot(bc);
        root.intentsHidden = true;
        auto &worm = root.monsters.arr[0];
        worm.pendingRollInputs = worm.captureRollInputs(root);
        worm.pendingMoveRolls = 1;
        BattleContext rolled = root;
        rolled.monsters.arr[0].materializePendingMove(rolled);
        check(rolled.monsters.arr[0].pendingMoveRolls == 0 && !root.equalForSearch(rolled),
              "pending and rolled intents are different search states");
        search::SilverSearcher searcher(root, {});
        searcher.search(300);
        check(searcher.rootSearchState().monsters.arr[0].pendingMoveRolls == 1,
              "search keeps the root intent hidden");
        check(search::SilverSearcher::translateAction(searcher.bestAction(), searcher.rootSearchState(), bc)
                  .isValidAction(bc), "hidden-intent search returns a valid action");
    }

    std::cout << "silver_searcher " << (failures == 0 ? "PASS" : "FAIL") << '\n';
    return failures == 0 ? 0 : 1;
}

// The wire path used by the live advisor (live state -> wire -> search root)
// gives the same search state as the native backend's own search root, and
// actions chosen on it map back onto the live state.
int testSilverWireState() {
    int failures = 0;
    auto check = [&](bool ok, const std::string &what) {
        if (!ok) {
            if (failures < 20) std::cerr << "silver_wire_state FAIL: " << what << '\n';
            ++failures;
        }
    };
    enum class Variant { PLAIN, RUNIC_DOME, FROZEN_EYE, PLAY_COUNT_RELICS };
    const MonsterEncounter encounters[] = {
        MonsterEncounter::JAW_WORM, MonsterEncounter::LOOTER, MonsterEncounter::GREMLIN_NOB,
        MonsterEncounter::THREE_SENTRIES, MonsterEncounter::THE_GUARDIAN, MonsterEncounter::SLIME_BOSS,
    };
    const CardId extraCards[] = {
        CardId::ARMAMENTS, CardId::HEADBUTT, CardId::TRUE_GRIT, CardId::WARCRY,
        CardId::BURNING_PACT, CardId::EXHUME, CardId::SECRET_WEAPON, CardId::POMMEL_STRIKE,
    };
    int decisions = 0;
    int hiddenRoots = 0;
    int edgesChecked = 0;
    int queuedRoots = 0;
    int missedReactionRoots = 0;
    for (const auto variant : {Variant::PLAIN, Variant::RUNIC_DOME, Variant::FROZEN_EYE,
                               Variant::PLAY_COUNT_RELICS}) {
        for (std::uint64_t seed = 11; seed <= 12; ++seed) {
            for (const auto encounter : encounters) {
                GameContext gc(CharacterClass::IRONCLAD, seed, 0);
                for (const auto id : extraCards) gc.deck.obtainRaw(Card(id));
                gc.potions[0] = Potion::FIRE_POTION;
                gc.potions[1] = Potion::BLOCK_POTION;
                gc.potionCount = 2;
                if (variant == Variant::RUNIC_DOME) gc.obtainRelic(RelicId::RUNIC_DOME);
                if (variant == Variant::FROZEN_EYE) gc.obtainRelic(RelicId::FROZEN_EYE);
                if (variant == Variant::PLAY_COUNT_RELICS) {
                    for (const auto relic : {RelicId::KUNAI, RelicId::SHURIKEN, RelicId::PEN_NIB,
                                             RelicId::NUNCHAKU, RelicId::INK_BOTTLE, RelicId::LETTER_OPENER,
                                             RelicId::ORNAMENTAL_FAN}) {
                        gc.obtainRelic(relic);
                    }
                }

                BattleContext bc;
                search::CombatKnowledgeState knowledge;
                knowledge.configureHiddenMonsterIntents(variant == Variant::RUNIC_DOME);
                knowledge.initializeFromLiveBattle(bc);
                knowledge.beginCombatInitialization();
                search::g_combatKnowledgeObserver = &knowledge;
                bc.init(gc, encounter);
                knowledge.synchronizeAfterCombatInitialization(bc);

                const auto runContext = search::makeSilverRunContext(gc);
                int steps = 0;
                while (bc.outcome == Outcome::UNDECIDED && ++steps < 400) {
                    knowledge.reconcilePublicDrawPileCardinality(bc);
                    BattleContext nativeRoot;
                    const auto error = search::nativeSilverSearchRoot(bc, knowledge, nativeRoot);
                    const auto conversion = search::makeSilverBattleStateConversion(
                        bc, knowledge, runContext, search::nativeSilverBattleSeed(bc));
                    if (!error.empty() || !conversion.wire.valid) {
                        check(false, "root not representable: " + error + " / " + conversion.failureReason);
                        break;
                    }
                    const BattleContext wireRoot = search::battleContextFromWire(conversion.wire);
                    // The wire carries only the public search seed, not the live one.
                    nativeRoot.seed = wireRoot.seed;
                    // The wire carries discard and exhaust piles as sorted multisets
                    // (their order is compared when the draw pile is concrete).
                    std::sort(nativeRoot.cards.discardPile.begin(), nativeRoot.cards.discardPile.end());
                    std::sort(nativeRoot.cards.exhaustPile.begin(), nativeRoot.cards.exhaustPile.end());
                    const std::string where = " seed=" + std::to_string(seed) + " encounter="
                        + std::to_string(static_cast<int>(encounter)) + " variant="
                        + std::to_string(static_cast<int>(variant)) + " step=" + std::to_string(steps);
                    // The wire has no queues; an interrupted card play's pending
                    // work is rebuilt by replaying the card.
                    queuedRoots += nativeRoot.actionQueue.size + nativeRoot.cardQueue.size > 1;
                    // Known limit: monster reactions queued while the card's own
                    // pre-selection effects ran (Sharp Hide, Mode Shift) are not
                    // rebuilt. Such a root may lack queued actions but must match
                    // otherwise.
                    bool missingReactions = false;
                    if (!wireRoot.equalForSearch(nativeRoot)) {
                        BattleContext withNativeQueue = wireRoot;
                        withNativeQueue.actionQueue = nativeRoot.actionQueue;
                        std::vector<int> wireTypes, nativeTypes;
                        for (int k = 0; k < wireRoot.actionQueue.size; ++k) {
                            wireTypes.push_back(static_cast<int>(wireRoot.actionQueue.arr[(wireRoot.actionQueue.front + k) % 128].type));
                        }
                        for (int k = 0; k < nativeRoot.actionQueue.size; ++k) {
                            nativeTypes.push_back(static_cast<int>(nativeRoot.actionQueue.arr[(nativeRoot.actionQueue.front + k) % 128].type));
                        }
                        std::size_t matched = 0;
                        for (const int type : nativeTypes) {
                            if (matched < wireTypes.size() && wireTypes[matched] == type) ++matched;
                        }
                        missingReactions = withNativeQueue.equalForSearch(nativeRoot)
                            && matched == wireTypes.size() && wireTypes.size() < nativeTypes.size();
                        missedReactionRoots += missingReactions;
                    }
                    if (!missingReactions) {
                        check(wireRoot.equalForSearch(nativeRoot), "wire root differs from native root" + where);
                        check(search::hashBattleState(wireRoot) == search::hashBattleState(nativeRoot),
                              "wire root hash differs" + where);
                    }
                    const auto context = search::searchContextFromWire(conversion.wire);
                    check(search::battleContextFromWire(search::wireFromSearchState(wireRoot, context))
                              .equalForSearch(wireRoot), "search-state wire round trip" + where);
                    hiddenRoots += wireRoot.intentsHidden;

                    search::g_combatKnowledgeObserver = nullptr;
                    search::SilverSearcher searcher(wireRoot, context);
                    searcher.search(40);
                    search::g_combatKnowledgeObserver = &knowledge;
                    for (const auto &edge : searcher.rootNode().edges) {
                        const auto semantic = search::semanticFromSearchAction(searcher.rootSearchState(), edge.action);
                        const auto translated = search::SilverSearcher::translateAction(
                            edge.action, searcher.rootSearchState(), bc);
                        check(search::semanticFingerprint(semantic)
                                  == search::semanticFingerprint(search::semanticFromSearchAction(bc, translated)),
                              "semantic identity changes under translation" + where);
                        const auto resolved = search::resolveSilverSemanticAction(bc, semantic);
                        check(resolved.ok && resolved.action.isValidAction(bc),
                              "semantic action does not resolve on the live state: " + resolved.error + where);
                        ++edgesChecked;
                    }
                    const auto action = search::SilverSearcher::translateAction(
                        searcher.bestAction(), searcher.rootSearchState(), bc);
                    if (!action.isValidAction(bc)) {
                        check(false, "invalid translated action" + where);
                        break;
                    }
                    action.execute(bc);
                    ++decisions;
                }
                search::g_combatKnowledgeObserver = nullptr;
                check(bc.outcome != Outcome::UNDECIDED, "battle finished");
            }
        }
    }
    std::cout << "silver_wire_state decisions=" << decisions << " hiddenRoots=" << hiddenRoots
              << " edges=" << edgesChecked
              << " queuedRoots=" << queuedRoots << " missedReactionRoots=" << missedReactionRoots << ' ' << (failures == 0 ? "PASS" : "FAIL") << '\n';
    return failures == 0 ? 0 : 1;
}

int testBattleEquality() {
    int failures = 0;
    auto check = [&](bool ok, const char *what) {
        if (!ok) {
            std::cerr << "battle_equality FAIL: " << what << '\n';
            ++failures;
        }
    };
    const GameContext game(CharacterClass::IRONCLAD, 0xE0A1u, 0);
    BattleContext base;
    base.init(game, MonsterEncounter::JAW_WORM);
    base.cards.cardsInHand = 3;
    base.cards.hand[0] = CardInstance(CardId::STRIKE_RED);
    base.cards.hand[0].uniqueId = 90;
    base.cards.hand[1] = CardInstance(CardId::DEFEND_RED);
    base.cards.hand[1].uniqueId = 91;
    base.cards.hand[2] = CardInstance(CardId::BASH);
    base.cards.hand[2].uniqueId = 92;

    auto same = [&](const BattleContext &x, bool exact, bool search, const char *what) {
        check((x == base) == exact, what);
        check(x.equalForSearch(base) == search, what);
        check(base.equalForSearch(x) == search, what);
        if (search) {
            check(search::hashBattleState(x) == search::hashBattleState(base), what);
        }
    };

    same(base, true, true, "copy");

    BattleContext rng = base;
    rng.aiRng.random(5);
    rng.shuffleRng.randomLong();
    same(rng, false, true, "rng-only difference");

    BattleContext permuted = base;
    std::swap(permuted.cards.hand[0], permuted.cards.hand[2]);
    same(permuted, false, true, "hand permutation");

    BattleContext stale = base;
    stale.cards.hand[5] = CardInstance(CardId::ANGER);
    stale.monsters.arr[4].curHp = 77;
    same(stale, true, true, "unused slots");

    BattleContext hp = base;
    hp.player.curHp -= 1;
    same(hp, false, false, "player hp");

    BattleContext status = base;
    status.player.buff<PS::STRENGTH>(1);
    same(status, false, false, "player status");

    BattleContext move = base;
    move.monsters.arr[0].setMove(MMID::JAW_WORM_THRASH);
    same(move, false, false, "monster move");

    BattleContext handCard = base;
    handCard.cards.hand[1].upgrade();
    same(handCard, false, false, "hand card upgrade");

    if (base.cards.drawPile.size() >= 2) {
        BattleContext draw = base;
        std::swap(draw.cards.drawPile.concreteCards().front(), draw.cards.drawPile.concreteCards().back());
        same(draw, false, false, "draw pile order");
    } else {
        check(false, "draw pile has fewer than two cards");
    }

    BattleContext q1 = base;
    BattleContext q2 = base;
    q1.addToBot(Actions::GainEnergy(1));
    q2.addToBot(Actions::GainEnergy(2));
    check(!(q1 == q2) && !q1.equalForSearch(q2), "queued action parameter");
    q2 = base;
    q2.addToBot(Actions::GainEnergy(1));
    check(q1 == q2 && q1.equalForSearch(q2), "equal queued actions");

    check(Actions::DebuffEnemy<MS::WEAK>(0, 1) == Actions::DebuffEnemy<MS::WEAK>(0, 1), "action equal");
    check(!(Actions::DebuffEnemy<MS::WEAK>(0, 1) == Actions::DebuffEnemy<MS::WEAK>(0, 2)), "action amount");
    check(!(Actions::DebuffEnemy<MS::WEAK>(0, 1) == Actions::DebuffEnemy<MS::VULNERABLE>(0, 1)), "action status");
    check(!(Actions::HealPlayer(1, true) == Actions::HealPlayer(1, false)), "action victory flag");

    std::cout << "battle_equality " << (failures == 0 ? "PASS" : "FAIL") << '\n';
    return failures == 0 ? 0 : 1;
}

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
    std::cout << "sizeof Action : " << sizeof(Action) << '\n';
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

static BattleContext simulatorCorrectnessBattle(std::initializer_list<RelicId> relics,
                                                Card card = Card(CardId::FLEX),
                                                int cardCount = 10,
                                                MonsterEncounter encounter = MonsterEncounter::JAW_WORM) {
    GameContext gc(CharacterClass::IRONCLAD, 100123, 20);
    gc.curRoom = Room::MONSTER;
    gc.relics = {};
    for (const RelicId relic : relics) {
        gc.relics.add({relic, relic == RelicId::NEOWS_LAMENT ? 1 : 0});
    }
    gc.deck = {};
    for (int i = 0; i < cardCount; ++i) {
        gc.deck.obtainRaw(card);
    }

    BattleContext bc;
    bc.init(gc, encounter);
    return bc;
}

static void simulatorCorrectnessPlay(BattleContext &bc, int handIdx = 0, int targetIdx = 0) {
    search::Action(search::ActionType::CARD, handIdx, targetIdx).execute(bc);
}

// Focused semantic regressions for upstream gamerpuppy/sts_lightspeed PRs #9-#19.
// Each block is deliberately a small native fixture so the check fails on the
// pre-port behavior without depending on a gameplay sweep.
int testSimulatorCorrectnessPr9To19() {
    auto fail = [&](const char *msg) {
        std::cout << "simulator_correctness_pr9_19 FAIL: " << msg << '\n';
        return 1;
    };

    // #9: Iron Wave applies block modifiers exactly once.
    {
        auto bc = simulatorCorrectnessBattle({}, Card(CardId::IRON_WAVE), 10);
        bc.player.dexterity = 2;
        simulatorCorrectnessPlay(bc);
        if (bc.player.block != 7) return fail("#9 Iron Wave double-counted Dexterity");

        auto frail = simulatorCorrectnessBattle({}, Card(CardId::IRON_WAVE), 10);
        frail.player.debuff<PS::FRAIL>(1, false);
        simulatorCorrectnessPlay(frail);
        if (frail.player.block != 3) return fail("#9 Iron Wave double-applied Frail");
    }

    // #10: every relic-pool shuffle consumes one counted relic RNG draw.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        if (gc.relicRng.counter != 5) return fail("#10 relic pool shuffles did not advance the counter");
    }

    // #11: Red Mask's opening Weak is player-sourced and expires after one
    // enemy turn, while Artifact still consumes the attempted debuff.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::RED_MASK}, Card(CardId::FLEX), 10);
        if (bc.monsters.arr[0].getStatus<MS::WEAK>() != 1) {
            return fail("#11 Red Mask did not apply one Weak");
        }
        search::Action(search::ActionType::END_TURN).execute(bc);
        if (bc.monsters.arr[0].getStatus<MS::WEAK>() != 0) {
            return fail("#11 Red Mask Weak lasted an extra enemy turn");
        }
        auto artifact = simulatorCorrectnessBattle({RelicId::RED_MASK}, Card(CardId::FLEX), 10,
                                                   MonsterEncounter::THREE_SENTRIES);
        for (int i = 0; i < artifact.monsters.monsterCount; ++i) {
            if (artifact.monsters.arr[i].getStatus<MS::WEAK>() != 0 ||
                    artifact.monsters.arr[i].getStatus<MS::ARTIFACT>() != 0) {
                return fail("#11 Red Mask did not preserve Artifact handling");
            }
        }
    }

    // #12: Choker limits ordinary/autoplay queue entries but retains the
    // purge-on-use exception used by queued replay effects.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::VELVET_CHOKER}, Card(CardId::HAVOC, true), 20);
        simulatorCorrectnessPlay(bc);
        if (bc.player.cardsPlayedThisTurn != 6 || !bc.actionQueue.isEmpty() || !bc.cardQueue.isEmpty()) {
            return fail("#12 Velvet Choker allowed an autoplay chain past six cards");
        }

        auto replay = simulatorCorrectnessBattle({RelicId::VELVET_CHOKER}, Card(CardId::FLEX), 10);
        replay.player.cardsPlayedThisTurn = 6;
        CardQueueItem item(CardInstance(CardId::STRIKE_RED), 0, 0);
        item.purgeOnUse = true;
        item.autoplay = true;
        replay.playCardQueueItem(item);
        if (replay.player.cardsPlayedThisTurn != 7) {
            return fail("#12 Choker blocked a purge-on-use replay");
        }
    }

    // #13: Unceasing Top resolves the shuffle/draw work before returning control.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::UNCEASING_TOP}, Card(CardId::FLEX), 5);
        for (int i = 0; i < 5; ++i) simulatorCorrectnessPlay(bc);
        if (bc.cards.cardsInHand != 1 || bc.cards.drawPile.size() != 4 ||
                !bc.actionQueue.isEmpty() || !bc.cardQueue.isEmpty()) {
            return fail("#13 Unceasing Top returned before its queued draw resolved");
        }
    }

    // #14: Meat on the Bone settles before Burning/Black Blood regardless of
    // relic acquisition order, and never heals a defeat.
    auto combatExitHp = [](std::initializer_list<RelicId> relics, Outcome outcome) {
        GameContext gc(CharacterClass::IRONCLAD, 100123, 0);
        gc.curHp = 40;
        gc.maxHp = 80;
        gc.relics = {};
        for (const RelicId relic : relics) gc.relics.add({relic, 0});
        BattleContext bc;
        bc.outcome = outcome;
        bc.updateRelicsOnExit(gc);
        return gc.curHp;
    };
    if (combatExitHp({RelicId::BURNING_BLOOD, RelicId::MEAT_ON_THE_BONE}, Outcome::PLAYER_VICTORY) != 58 ||
            combatExitHp({RelicId::MEAT_ON_THE_BONE, RelicId::BURNING_BLOOD}, Outcome::PLAYER_VICTORY) != 58 ||
            combatExitHp({RelicId::BLACK_BLOOD, RelicId::MEAT_ON_THE_BONE}, Outcome::PLAYER_VICTORY) != 64 ||
            combatExitHp({RelicId::MEAT_ON_THE_BONE}, Outcome::PLAYER_LOSS) != 40) {
        return fail("#14 Meat on the Bone ordering or defeat guard is wrong");
    }

    // #15: crossing above half HP removes Red Skull strength.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::RED_SKULL});
        bc.player.maxHp = 80;
        bc.player.curHp = 40;
        bc.player.strength = 3;
        bc.player.heal(5);
        if (bc.player.curHp != 45 || bc.player.strength != 0) {
            return fail("#15 Red Skull added instead of removing Strength");
        }
    }

    // #16: Magic Flower rounds positive odd healing, rather than truncating it.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::MAGIC_FLOWER});
        bc.player.maxHp = 80;
        bc.player.curHp = 60;
        bc.player.heal(5);
        if (bc.player.curHp != 68) return fail("#16 Magic Flower truncated 7.5 healing");
    }

    // #17: Toy Ornithopter is routed through ordinary potion consumption.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::TOY_ORNITHOPTER});
        bc.player.maxHp = 80;
        bc.player.curHp = 70;
        bc.potions[0] = Potion::BLOCK_POTION;
        bc.potionCount = 1;
        search::Action(search::ActionType::POTION, 0, 0).execute(bc);
        if (bc.player.curHp != 75 || bc.potionCount != 0 ||
                bc.potions[0] != Potion::EMPTY_POTION_SLOT) {
            return fail("#17 Toy Ornithopter did not heal on potion use");
        }
    }

    // #17a: Smoke Bomb resolves Toy Ornithopter before its immediate escape.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::TOY_ORNITHOPTER});
        bc.player.maxHp = 80;
        bc.player.curHp = 70;
        bc.potions[0] = Potion::SMOKE_BOMB;
        bc.potionCount = 1;
        search::Action(search::ActionType::POTION, 0, 0).execute(bc);
        if (bc.player.curHp != 75 || bc.potionCount != 0 ||
                bc.potions[0] != Potion::EMPTY_POTION_SLOT ||
                bc.outcome != Outcome::PLAYER_VICTORY ||
                !bc.actionQueue.isEmpty()) {
            return fail("#17a Smoke Bomb abandoned Toy Ornithopter heal");
        }
    }

    // #17b: Ancient Potion's Artifact resolves before Toy Ornithopter crosses
    // Red Skull's half-HP threshold, so the debuff consumes Artifact.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::RED_SKULL,
                                               RelicId::TOY_ORNITHOPTER});
        bc.player.maxHp = 80;
        bc.player.curHp = 40;
        bc.player.strength = 3;
        bc.potions[0] = Potion::ANCIENT_POTION;
        bc.potionCount = 1;
        search::Action(search::ActionType::POTION, 0, 0).execute(bc);
        if (bc.player.curHp != 45 || bc.player.strength != 3 ||
                bc.player.hasStatus<PS::ARTIFACT>()) {
            return fail("#17b Ancient Potion resolved after Toy Ornithopter heal");
        }
    }

    // #17c: a lethal Fire Potion still completes the Toy trigger after the
    // potion effect wins the fight.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::TOY_ORNITHOPTER});
        bc.player.maxHp = 80;
        bc.player.curHp = 70;
        bc.monsters.arr[0].curHp = 1;
        bc.potions[0] = Potion::FIRE_POTION;
        bc.potionCount = 1;
        search::Action(search::ActionType::POTION, 0, 0).execute(bc);
        if (bc.outcome != Outcome::PLAYER_VICTORY || bc.player.curHp != 75 ||
                !bc.actionQueue.isEmpty()) {
            return fail("#17c lethal Fire Potion abandoned Toy Ornithopter heal");
        }
    }

    // #18: direct positive HP loss consumes Buffer before Tungsten Rod.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::FOSSILIZED_HELIX, RelicId::TUNGSTEN_ROD});
        const int before = bc.player.curHp;
        bc.player.loseHp(bc, 5, false);
        if (bc.player.curHp != before || bc.player.hasStatus<PS::BUFFER>()) {
            return fail("#18 Buffer did not intercept direct HP loss before Rod");
        }
        auto rodOnly = simulatorCorrectnessBattle({RelicId::TUNGSTEN_ROD});
        const int rodBefore = rodOnly.player.curHp;
        rodOnly.player.loseHp(rodOnly, 5, false);
        if (rodOnly.player.curHp != rodBefore - 4) {
            return fail("#18 Tungsten Rod direct-loss control changed");
        }
    }

    // #19: Neow's Lament only changes actual encounter entities, not the
    // reserved Gremlin Leader placeholder at slot zero.
    {
        auto bc = simulatorCorrectnessBattle({RelicId::NEOWS_LAMENT}, Card(CardId::FLEX), 10,
                                              MonsterEncounter::GREMLIN_LEADER);
        if (bc.monsters.monsterCount != 4 || bc.monsters.arr[0].idx != -1 ||
                bc.monsters.arr[0].curHp != 0) {
            return fail("#19 Neow's Lament assigned HP to a reserved monster slot");
        }
        for (int i = 1; i < bc.monsters.monsterCount; ++i) {
            if (bc.monsters.arr[i].idx < 0 || bc.monsters.arr[i].curHp != 1) {
                return fail("#19 Neow's Lament missed an actual monster");
            }
        }
    }

    std::cout << "simulator_correctness_pr9_19 PASS\n";
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

    std::cout << "issue_fixes PASS\n";
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

// ---- CARD_SELECT action-parity contract -------------------------------------
// Ground truth for a CARD_SELECT state is exactly the action set the simulator
// validates (search::Action::isValidAction): in this input mode only
// SINGLE_CARD_SELECT and MULTI_CARD_SELECT actions can validate. The canonical
// search::Action::enumerateCardSelectActions must match it exactly, or a
// consumer can be blind to legal selections (see knowledge-base issues tracker).

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
// potions (fairy excluded), and END_TURN.
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
    bc.cards.drawPile.concreteCards().push_back(CardInstance(CardId::DEFEND_RED));
    bc.cards.drawPile.concreteCards().push_back(CardInstance(CardId::BASH));
    bc.cards.drawPile.concreteCards().push_back(CardInstance(CardId::STRIKE_RED));
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
    std::swap(permuted.cards.drawPile.concreteCards()[0], permuted.cards.drawPile.concreteCards()[2]);

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
    Random silverRng(0x9001u);
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
    Random knownTopRng(0x9002u);
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
    std::swap(eyeB.cards.drawPile.concreteCards()[0], eyeB.cards.drawPile.concreteCards()[2]);
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
    BattleContext nonTarget = normal;
    CardInstance nonTargetCard(CardId::DEFEND_RED);
    nonTargetCard.uniqueId = 171;
    nonTarget.cards.hand[0] = nonTargetCard;
    silver_bridge::SemanticAction nonTargetPlay = cardPlay;
    nonTargetPlay.card = wire(nonTargetCard);
    nonTargetPlay.target = -1;
    const auto nonTargetResolved = search::resolveSilverSemanticAction(nonTarget, nonTargetPlay);
    check(nonTargetResolved.ok && nonTargetResolved.action.getActionType() == search::ActionType::CARD
          && nonTargetResolved.action.getSourceIdx() == 0
          && nonTargetResolved.action.isValidAction(nonTarget),
          "non-target semantic card with target=-1 must lower to a legal live action");
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
        for (int i = 0; i < static_cast<int>(select.cards.drawPile.size()); ++i) select.cards.drawPile.concreteCards()[i].uniqueId = static_cast<std::int16_t>(300 + i);
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

            const bool cOk = compareEnumerator("canonical", truth, canonical) == 0;
            if (!cOk) {
                ++failures;
                std::cout << "  " << name << " (pickCount=" << pickCount << "): canonical FAIL\n";
            }
        }
        {
            const BattleContext bc = cardSelectFixture(task, 10, true);
            const auto truth = cardSelectGroundTruth(bc);
            std::vector<std::uint32_t> canonical;
            for (const auto &a : search::Action::enumerateCardSelectActions(bc)) canonical.push_back(a.bits);
            const bool cOk = compareEnumerator("canonical", truth, canonical) == 0;
            if (!cOk) {
                ++failures;
                std::cout << "  " << name << " (large hand): canonical FAIL\n";
            }
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
                const auto legal = bc.inputState == InputState::CARD_SELECT
                    ? cardSelectGroundTruth(bc) : playerNormalGroundTruth(bc);
                if (legal.empty()) break;
                const search::Action a(legal[rng() % legal.size()]);
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

// Simulator-health monitor: ACTION_SELECTION_FAILED classification (Test C).
// When canonical live actions exist but root/action selection fails, the
// monitor must classify the failure as ACTION_SELECTION_FAILED, not
// NO_LEGAL_PROGRESSION. This is the classification contract used at the
// fair-S2 invalid-pick guard. The contract is unit-tested here on controlled states,
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
        bc.cards.drawPile.concreteCards().push_back(CardInstance(CardId::DEFEND_RED));
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

    Actions::PoisonLoseHpAction(0)(bc);

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

    Actions::TimeEaterPlayCardQueueItem(replayed)(bc);

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

    } else if (command == "obs_identity") {
        return testObsIdentity(std::stoull(argv[2]));
    } else if (command == "happy_flower") {
        return testHappyFlowerCounter(std::stoull(argv[2]));
    } else if (command == "issue_fixes") {
        return testIssueFixes();
    } else if (command == "simulator_correctness_pr9_19") {
        return testSimulatorCorrectnessPr9To19();
    } else if (command == "relic_reward_sapphire") {
        return testRelicRewardSapphire();
    } else if (command == "cardselect_parity") {
        return testCardSelectParity();
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
    } else if (command == "simhealth_selection_failure") {
        return testSimHealthSelectionFailure();
    } else if (command == "training_integrity") {
        return testTrainingIntegrity();
    } else if (command == "e2c_observer_scope") {
        return testE2cObserverScope();
    } else if (command == "combat_transition_oracle") {
        return testCombatTransitionOracle();
    } else if (command == "combat_knowledge") {
        return testCombatKnowledgeBoundary();
    } else if (command == "card_pile_engine") {
        return testCardPileEngine();
    } else if (command == "silver_searcher") {
        return testSilverSearcher();
    } else if (command == "silver_wire_state") {
        return testSilverWireState();
    } else if (command == "card_pile") {
        return testCardPile();
    } else if (command == "battle_equality") {
        return testBattleEquality();
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
