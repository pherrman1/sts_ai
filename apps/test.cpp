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
#include <filesystem>
#include <fstream>
#include <iterator>
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
#include "sim/search/MatchAndKeepPolicy.h"
#include "combat/BattleContextBinary.h"
#include "combat/PublicDamageBelief.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverUselessAction.h"
#include "sim/search/SilverWireState.h"
#include "sim/search/SilverWireJson.h"
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

    SilverBattleResult playBattleWithSilverSearcher(std::uint64_t seed, MonsterEncounter encounter, int sims, bool profileEnabled = false, bool diagnose = false) {
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
            if (diagnose) (void)search::proveSilverUselessBlock(bc, action);
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

// A constructed free draw/reshuffle cycle exercises the playout boundary
// without replaying the expensive historical self-play campaign (#544).
int testSilverRolloutLimit() {
    const GameContext gc(CharacterClass::IRONCLAD, 0x544u, 0);
    BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
    while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED)
        bc.executeActions();
    bc.cards.cardsInHand = 1;
    bc.cards.hand[0] = CardInstance(CardId::FLASH_OF_STEEL); bc.cards.hand[0].uniqueId = 101;
    CardInstance other(CardId::FLASH_OF_STEEL); other.uniqueId = 102;
    bc.cards.drawPile.clear(); bc.cards.drawPile.addToTop(other);
    bc.cards.discardPile.clear(); bc.cards.exhaustPile.clear();
    bc.monsters.arr[0].buff<MS::INVINCIBLE>(1);
    bc.monsters.arr[0].setStatus<MS::INVINCIBLE>(0);
    search::SilverSearcher searcher(bc, {});
    searcher.rolloutConfig = {};
    search::SilverTreeProfile profile; searcher.profile = &profile;
    const double value = searcher.rolloutValue(bc);
    if (!std::isfinite(value) || searcher.stats.rolloutActions != 1000
            || searcher.stats.rolloutActionLimitHits != 1
            || profile.endpoints[search::SilverTreeProfile::NONTERMINAL].total[1000] != 1
            || bc.outcome != Outcome::UNDECIDED || bc.player.cardsPlayedThisTurn != 0) {
        std::cerr << "silver_rollout_limit FAIL actions=" << searcher.stats.rolloutActions << '\n';
        return 1;
    }
    // A terminating playout still takes its lethal action and records victory.
    bc.monsters.arr[0].removeStatus<MS::INVINCIBLE>(); bc.monsters.arr[0].curHp = 1;
    search::SilverSearcher lethal(bc, {}); lethal.rolloutConfig = {};
    search::SilverTreeProfile lethalProfile; lethal.profile = &lethalProfile;
    (void)lethal.rolloutValue(bc);
    if (lethal.stats.rolloutActions != 1 || lethal.stats.rolloutActionLimitHits != 0
            || lethalProfile.endpoints[search::SilverTreeProfile::VICTORY].total[1] != 1) return 1;
    // STS_SILVER_ROLLOUT_ACTION_CAP sets the bound (0 = uncapped, not exercised here).
    bc.monsters.arr[0].buff<MS::INVINCIBLE>(1); bc.monsters.arr[0].setStatus<MS::INVINCIBLE>(0);
    bc.monsters.arr[0].curHp = bc.monsters.arr[0].maxHp;
    search::SilverSearcher custom(bc, {}); custom.rolloutConfig = {}; custom.rolloutConfig.actionCap = 37;
    (void)custom.rolloutValue(bc);
    if (custom.stats.rolloutActions != 37 || custom.stats.rolloutActionLimitHits != 1) {
        std::cerr << "silver_rollout_limit FAIL custom cap actions=" << custom.stats.rolloutActions << '\n';
        return 1;
    }
    std::cout << "silver_rollout_limit PASS: bounded free draw cycle; terminal path preserved; cap configurable\n";
    return 0;
}

int testSilverSearcher() {
    int failures = 0;
    auto check = [&](bool ok, const char *what) {
        if (!ok) {
            std::cerr << "silver_searcher FAIL: " << what << '\n';
            ++failures;
        }
    };

    // Campaign opt-in: after the final A0 boss only actual victory matters.
    // Terminal constructors expose the evaluator through the root's value;
    // these fixtures do not run combat search or consume a live future.
    {
        GameContext gc(CharacterClass::IRONCLAD, 91, 0);
        BattleContext ended; ended.init(gc, MonsterEncounter::TIME_EATER);
        ended.player.curHp = 1;
        ended.potionCount = 0;
        ended.turn = 20;
        ended.outcome = Outcome::PLAYER_VICTORY;
        search::SilverSearchContext finalBoss;
        finalBoss.act = 3;
        finalBoss.actBossRoom = true;
        finalBoss.finalBossBinary = true;
        const auto value = [](const BattleContext &bc, const search::SilverSearchContext &ctx) {
            search::SilverSearcher s(bc, ctx);
            return s.rootNode().evaluationSum;
        };
        const double lowResourceWin = value(ended, finalBoss);
        check(lowResourceWin == 100.0, "final boss low-HP resource-empty victory scores 100");
        ended.player.curHp = ended.player.maxHp;
        ended.potionCount = 3;
        ended.player.gold += 1000;
        ended.turn = 1;
        check(value(ended, finalBoss) == lowResourceWin,
              "final boss unspent resources and winning speed have no terminal utility");
        ended.outcome = Outcome::PLAYER_LOSS;
        ended.player.curHp = 0;
        ended.turn = 100;
        ended.cardsDrawn = 10000;
        for (int i = 0; i < ended.monsters.monsterCount; ++i)
            ended.monsters.arr[i].curHp = 1;
        check(value(ended, finalBoss) == 0.0 && lowResourceWin > value(ended, finalBoss),
              "final boss victory dominates long near-lethal resource-rich loss");

        // Both the context and A0 restriction are checked at the evaluator.
        for (const auto setting : {std::pair<int, bool>{1, true}, {2, true}, {3, false}}) {
            auto scoped = finalBoss;
            scoped.act = setting.first;
            scoped.actBossRoom = setting.second;
            auto original = scoped; original.finalBossBinary = false;
            check(value(ended, scoped) == value(ended, original),
                  "final-boss opt-in leaves earlier and non-boss combat values unchanged");
        }
        ended.ascension = 1;
        auto original = finalBoss; original.finalBossBinary = false;
        check(value(ended, finalBoss) == value(ended, original),
              "final-boss opt-in is restricted to A0");
        ended.ascension = 0;
        ended.outcome = Outcome::PLAYER_VICTORY;
        ended.player.curHp = 1;
        ended.potionCount = 0;
        ended.turn = 20;
        search::SilverSearcher defaultSearcher(ended, original);
        const double legacyExpected = 53.0 + ended.player.maxHp - 20 * 0.4;
        check(defaultSearcher.rootNode().evaluationSum == legacyExpected,
              "default final-boss evaluator retains handcrafted score");
    }

    // Research opt-in (STS_SILVER_FINAL_FIGHT_LEAF): in a run-ending fight
    // every victory scores the same and a loss earns no potion credit.
    {
        GameContext gc(CharacterClass::IRONCLAD, 91, 0);
        BattleContext ended; ended.init(gc, MonsterEncounter::TIME_EATER);
        search::SilverSearchContext finalFight;
        finalFight.act = 3;
        finalFight.actBossRoom = true;
        finalFight.finalFightLeaf = true;
        const auto value = [](const BattleContext &bc, const search::SilverSearchContext &ctx) {
            search::SilverSearcher s(bc, ctx);
            return s.rootNode().evaluationSum;
        };
        ended.outcome = Outcome::PLAYER_VICTORY;
        ended.player.curHp = 1; ended.potionCount = 0; ended.turn = 20;
        const double lowWin = value(ended, finalFight);
        check(lowWin == 53.0 + ended.player.maxHp, "final-fight leaf victory scores win bonus plus max HP");
        ended.player.curHp = ended.player.maxHp; ended.potionCount = 3; ended.turn = 1;
        ended.player.gold += 1000;
        check(value(ended, finalFight) == lowWin, "final-fight leaf ignores HP, potions, gold and speed");
        ended.outcome = Outcome::PLAYER_LOSS;
        ended.player.curHp = 0; ended.turn = 10;
        auto noPotions = ended; noPotions.potionCount = 0;
        check(value(ended, finalFight) == value(noPotions, finalFight), "final-fight leaf loss has no potion credit");
        auto original = finalFight; original.finalFightLeaf = false;
        check(value(ended, original) > value(noPotions, original), "default loss keeps potion credit");
        check(value(ended, original) - value(ended, finalFight) == 3 * 11.0 / 2,
              "final-fight leaf loss differs from default only by the potion credit");
        check(lowWin > value(ended, finalFight), "final-fight leaf victory dominates a loss");
    }

    // Research opt-ins STS_SILVER_RELIC_HEAL_LEAF / STS_SILVER_NO_LOSS_POTION_CREDIT
    // and the A20 first act-3 boss heal fix (actHealFollows).
    {
        const auto value = [](const BattleContext &bc, const search::SilverSearchContext &ctx) {
            search::SilverSearcher s(bc, ctx);
            return s.rootNode().evaluationSum;
        };
        GameContext gc(CharacterClass::IRONCLAD, 91, 0);
        BattleContext won; won.init(gc, MonsterEncounter::JAW_WORM);
        won.outcome = Outcome::PLAYER_VICTORY;
        won.potionCount = 0; won.turn = 5;
        won.player.curHp = won.player.maxHp - 2;   // Burning Blood would heal to full
        search::SilverSearchContext plain, relic; relic.relicHealLeaf = true;
        check(value(won, relic) - value(won, plain) == 2.0, "relic heal leaf credits the Burning Blood heal up to max HP");
        won.player.curHp = 20;
        check(value(won, relic) - value(won, plain) == 6.0, "relic heal leaf credits the full Burning Blood heal");

        BattleContext lost = won; lost.outcome = Outcome::PLAYER_LOSS; lost.player.curHp = 0; lost.potionCount = 2;
        search::SilverSearchContext noCredit; noCredit.noLossPotionCredit = true;
        check(value(lost, plain) - value(lost, noCredit) == 11.0, "no-loss-potion-credit drops 5.5 per held potion");
        check(value(won, noCredit) == value(won, plain), "no-loss-potion-credit leaves victories unchanged");

        GameContext gc20(CharacterClass::IRONCLAD, 91, 20);
        BattleContext boss; boss.init(gc20, MonsterEncounter::TIME_EATER);
        boss.outcome = Outcome::PLAYER_VICTORY; boss.potionCount = 0; boss.turn = 10;
        boss.player.curHp = 20;
        search::SilverSearchContext heal; heal.act = 3; heal.actBossRoom = true;
        auto noHeal = heal; noHeal.actHealFollows = false;
        const int healed = 20 + static_cast<int>(std::round((boss.player.maxHp - 20) * 0.75f));
        check(value(boss, heal) - value(boss, noHeal) == healed - 20,
              "first A20 act-3 boss earns no act-transition heal credit");
    }

    // Final choice is edge visits only; even Q ties keep enumeration order.
    {
        GameContext gc(CharacterClass::IRONCLAD, 91, 0);
        BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
        search::SilverSearcher searcher(silverSearchRoot(bc), {});
        searcher.prepareRootActions();
        auto *root = &const_cast<search::SilverSearcher::Node &>(searcher.rootNode());
        check(root && root->edges.size() >= 2, "root selection fixture has two actions");
        if (root && root->edges.size() >= 2) {
            root->edges.resize(2);
            search::SilverSearcher::Node low, high;
            low.simulationCount = high.simulationCount = 10;
            low.evaluationSum = 1; high.evaluationSum = 1000;
            root->edges[0].node = &low; root->edges[1].node = &high;
            root->edges[0].visitCount = 20; root->edges[1].visitCount = 10;
            check(searcher.bestAction().bits == root->edges[0].action.bits,
                  "more visits beats higher mean Q");
            root->edges[1].visitCount = 20;
            check(searcher.bestAction().bits == root->edges[0].action.bits,
                  "visit tie ignores Q and keeps first edge");
            std::swap(root->edges[0], root->edges[1]);
            check(searcher.bestAction().bits == root->edges[0].action.bits,
                  "tie follows enumeration order rather than action identity");
        }
    }
    {
        GameContext gc(CharacterClass::IRONCLAD, 0x5EEDu, 0);
        BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
        bc.cards.cardsInHand = 1;
        bc.cards.hand[0] = CardInstance(CardId::DEFEND_RED);
        bc.cards.hand[0].uniqueId = 81;
        bc.potionCount = 0;
        for (auto &p : bc.potions) p = Potion::EMPTY_POTION_SLOT;
        const search::Action defend(search::ActionType::CARD, 0, 0);
        const auto before = bc;
        const auto proof = search::proveSilverUselessBlock(bc, defend);
        if (!proof.verified) std::cerr << "useless block fixture rejected: " << proof.reason << '\n';
        check(proof.verified && proof.energySpent == 1 && proof.blockGained == 5
              && proof.energyWasteDelta == -1 && !proof.snapshot.empty(),
              "last-card temporary block has an equivalent forced End Turn continuation");
        check(bc == before, "diagnostic never changes live state or RNG");
        auto changed = bc;
        changed.player.setHasStatus<PlayerStatus::BARRICADE>(true);
        check(!search::proveSilverUselessBlock(changed, defend).verified, "retained block fails closed");
        changed = bc; changed.player.buff<PlayerStatus::JUGGERNAUT>(5);
        check(!search::proveSilverUselessBlock(changed, defend).verified, "block damage trigger fails closed");
        changed = bc; changed.player.setHasRelic<RelicId::INK_BOTTLE>(true);
        check(!search::proveSilverUselessBlock(changed, defend).verified, "card-play relic fails closed");
        changed = bc; changed.monsters.arr[0].moveHistory[0] = MMID::CULTIST_DARK_STRIKE;
        check(!search::proveSilverUselessBlock(changed, defend).verified, "incoming damage fails closed");
        changed = bc; changed.cards.cardsInHand = 2;
        check(!search::proveSilverUselessBlock(changed, defend).verified, "unforced continuation fails closed");
        changed = bc; changed.cards.hand[0] = CardInstance(CardId::SHRUG_IT_OFF);
        check(!search::proveSilverUselessBlock(changed, defend).verified, "draw effect is outside qualified class");
        const auto off = playBattleWithSilverSearcher(123, MonsterEncounter::CULTIST, 200);
        const auto on = playBattleWithSilverSearcher(123, MonsterEncounter::CULTIST, 200, false, true);
        check(off.actions == on.actions && off.rng == on.rng && off.hp == on.hp
            && off.turn == on.turn && off.outcome == on.outcome,
            "diagnostics preserve every full-fight action, RNG stream, and result");

    }

    // Leaf sampling (silversynthgen) is observational: the search is unchanged.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x51A7u, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        search::SilverSearcher plain(silverSearchRoot(bc), {});
        search::SilverSearcher sampled(silverSearchRoot(bc), {});
        search::SilverLeafSamples leaves;
        leaves.stride = 7;
        leaves.max = 5;
        sampled.leafSamples = &leaves;
        plain.search(500);
        sampled.search(500);
        const auto &a = plain.rootNode(), &b = sampled.rootNode();
        bool same = a.simulationCount == b.simulationCount && a.evaluationSum == b.evaluationSum
            && a.edges.size() == b.edges.size();
        for (std::size_t i = 0; same && i < a.edges.size(); ++i) {
            same = a.edges[i].visitCount == b.edges[i].visitCount && a.edges[i].action.bits == b.edges[i].action.bits;
        }
        check(same && plain.nodeCount() == sampled.nodeCount(), "leaf sampling leaves the search unchanged");
        check(leaves.samples.size() == 5 && leaves.counter >= 35, "leaf sampling keeps every stride-th start up to max");
        bool startsValid = true;
        for (const auto &leaf : leaves.samples) {
            startsValid = startsValid && leaf.start.outcome == Outcome::UNDECIDED && leaf.pathNodes >= 2;
        }
        check(startsValid, "sampled leaves are nonterminal rollout starts below the root");
        check(sampled.scoreEndState(bc) == plain.scoreEndState(bc), "terminal score is searcher independent");
    }

    // Root prior bonus (silversynthreplay): weight 0 or a uniform prior over
    // the root is today's search; a prior on one edge moves visits to it.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x51A7u, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        auto run = [&](std::vector<double> prior, double weight) {
            search::SilverSearcher s(silverSearchRoot(bc), {});
            const auto n = s.prepareRootActions();
            if (!prior.empty()) prior.resize(n, prior.back());
            s.rootPrior = prior;
            s.rootPriorWeight = weight;
            s.search(400);
            std::vector<std::int32_t> visits;
            for (const auto &e : s.rootNode().edges) visits.push_back(e.visitCount);
            return visits;
        };
        const auto plain = run({}, 0);
        check(plain.size() >= 3, "root prior fixture has three actions");
        check(run({1.0}, 0) == plain, "zero prior weight leaves the search unchanged");
        auto last = std::vector<double>(plain.size(), 0.0);
        last.back() = 1.0;
        const auto pushed = run(last, 400);
        check(pushed.back() > plain.back(), "root prior bonus adds visits to the favored edge");
        bool tried = true;
        for (const auto v : pushed) tried = tried && v >= 1;
        check(tried, "root prior bonus still tries every root action");

        // combat_policy_trees_v1 (the exported root prior) reads the policy layout.
        const auto path = std::filesystem::temp_directory_path() / "silver_root_prior_test.txt";
        std::ofstream(path) << "combat_policy_trees_v1\nnfeat 1\nfeat aIsEndTurn\nbase_score 0.25\n"
                               "ntrees 1\ntree 0 3\nS 0 0.5 1 2\nL -1\nL 2\n";
        search::CombatValueNet net;
        check(net.load(path.string()) && net.isPolicy, "policy trees load against the policy layout");
        search::SilverSearcher s(silverSearchRoot(bc), {});
        s.prepareRootActions();
        bool sawEnd = false, sawOther = false;
        for (const auto &e : s.rootNode().edges) {
            const double v = net.predictAction(s.rootSearchState(), e.action);
            const bool end = e.action.getActionType() == search::ActionType::END_TURN;
            sawEnd = sawEnd || (end && v == 2.25);
            sawOther = sawOther || (!end && v == -0.75);
        }
        check(sawEnd && sawOther, "policy trees score each root action from its action features");
        std::filesystem::remove(path);

        // predictPolicyActions (batched, state prefix walked once) equals
        // predictVec bit for bit, on the flattened path and on the fallback
        // used when a tree's children do not follow their parent.
        const auto mixed = std::filesystem::temp_directory_path() / "silver_policy_batch_test.txt";
        auto batchMatches = [&](const std::string &trees) {
            std::ofstream(mixed) << "combat_policy_trees_v1\nnfeat 3\nfeat curHp\nfeat aCardCost\nfeat turn\n"
                                    "base_score 0.1\n" << trees;
            search::CombatValueNet m;
            if (!m.load(mixed.string())) return std::make_pair(false, false);
            const int stateCount = search::combatFeatureCount();
            const int actionCount = search::combatPolicyFeatureCount() - stateCount;
            std::vector<float> state(search::combatPolicyFeatureCount(), 0.f), actions(4 * actionCount, 0.f);
            bool same = true;
            for (int trial = 0; trial < 64; ++trial) {
                state[3] = static_cast<float>(trial % 9) * 10.f;     // curHp
                state[2] = static_cast<float>(trial % 4);            // turn
                for (int i = 0; i < 4; ++i) actions[i * actionCount + 5] = static_cast<float>((trial + i) % 4);
                double batch[4];
                m.predictPolicyActions(state.data(), actions.data(), 4, batch);
                for (int i = 0; i < 4; ++i) {
                    std::copy(actions.begin() + i * actionCount, actions.begin() + (i + 1) * actionCount,
                              state.begin() + stateCount);
                    same = same && batch[i] == m.predictVec(state.data());
                }
            }
            return std::make_pair(same, !m.flatRoots.empty());
        };
        const auto flat = batchMatches("ntrees 4\n"
            "tree 0 5\nS 0 40 1 2\nS 1 2 3 4\nL 0.3\nL -0.7\nL 1.1\n"
            "tree 1 5\nS 1 1 1 2\nS 2 1.5 3 4\nL 0.01\nL 0.2\nL -0.4\n"
            "tree 2 1\nL 0.125\n"
            "tree 3 3\nS 2 2.5 1 2\nL 0.9\nL -0.33\n");
        check(flat.first && flat.second, "batched policy trees match predictVec on the flattened path");
        const auto fallback = batchMatches("ntrees 1\ntree 0 3\nS 1 1.5 2 1\nL 0.75\nS 0 40 1 1\n");
        check(fallback.first && !fallback.second, "batched policy trees fall back to predictVec for unordered trees");
        std::filesystem::remove(mixed);
    }

    // Tree prior (§452, research): an unreachable visit threshold is today's
    // search; at K = 1 internal decision nodes get a prior sized like their
    // edges, and the root's first try follows the root prior.
    {
        const GameContext gc(CharacterClass::IRONCLAD, 0x51A7u, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        auto visitsOf = [](const search::SilverSearcher &s) {
            std::vector<std::int32_t> visits;
            for (const auto &e : s.rootNode().edges) visits.push_back(e.visitCount);
            return visits;
        };
        search::SilverSearcher plain(silverSearchRoot(bc), {});
        plain.search(400);
        int calls = 0;
        bool sized = true;
        auto uniform = [&](const BattleContext &, const std::vector<search::SilverSearcher::Edge> &edges) {
            ++calls;
            sized = sized && edges.size() >= 2;
            return std::vector<double>(edges.size(), 1.0 / static_cast<double>(edges.size()));
        };
        search::SilverSearcher unreachable(silverSearchRoot(bc), {});
        unreachable.nodePrior = uniform;
        unreachable.treePriorMinVisits = 1 << 30;
        unreachable.search(400);
        check(visitsOf(unreachable) == visitsOf(plain) && unreachable.nodeCount() == plain.nodeCount() && calls == 0,
              "tree prior with an unreachable threshold leaves the search unchanged");

        search::SilverSearcher tree(silverSearchRoot(bc), {});
        const auto n = tree.prepareRootActions();
        std::vector<double> last(n, 0.0);
        last.back() = 1.0;
        tree.rootPrior = last;
        tree.rootPriorWeight = 400;
        tree.nodePrior = uniform;
        tree.treePriorMinVisits = 1;
        tree.search(1);
        check(visitsOf(tree).back() == 1, "tree prior tries the highest-prior root action first");
        tree.search(399);
        check(calls > 0 && sized, "tree prior scores internal decision nodes with two or more edges");
        bool tried = true;
        for (const auto v : visitsOf(tree)) tried = tried && v >= 1;
        check(tried, "tree prior still tries every root action");

        // Silver AZ self-play teacher: without the root bonus and without a
        // tree prior, a root prior changes nothing; with the tree prior the
        // root still tries its highest-prior action first.
        search::SilverSearcher noBonus(silverSearchRoot(bc), {});
        noBonus.prepareRootActions();
        noBonus.rootPrior = last;
        noBonus.rootPriorWeight = 400;
        noBonus.rootPriorBonus = false;
        noBonus.search(400);
        check(visitsOf(noBonus) == visitsOf(plain), "root prior without its bonus leaves the search unchanged");
        search::SilverSearcher noBonusTree(silverSearchRoot(bc), {});
        noBonusTree.prepareRootActions();
        noBonusTree.rootPrior = last;
        noBonusTree.rootPriorWeight = 400;
        noBonusTree.rootPriorBonus = false;
        noBonusTree.nodePrior = uniform;
        noBonusTree.search(1);
        check(visitsOf(noBonusTree).back() == 1, "tree prior without the root bonus keeps prior-ordered first tries");
    }

    // combat_policy_mlp_v1 (Silver AZ MLP prior): one hand-computed edge with
    // a state weight, the action block, the card table and the target gather,
    // and one edge without card or target.
    {
        const auto &names = search::combatPolicyFeatureNames();
        const int S = search::combatFeatureCount(), A = static_cast<int>(names.size()) - S;
        const auto path = std::filesystem::temp_directory_path() / "sts_policy_mlp_test.txt";
        {
            std::ofstream f(path);
            f << "combat_policy_mlp_v1\nh1 2\nh2 1\nnstate " << S << "\nnaction " << A << "\nncard 372\nntarget 9\n";
            for (const auto &n : names) f << "feat " << n << '\n';
            auto rows = [&](const char *key, int nrows, std::map<int, std::pair<float, float>> set) {
                f << key << '\n';
                for (int r = 0; r < nrows; ++r) {
                    const auto it = set.find(r);
                    f << (it == set.end() ? 0.f : it->second.first) << ' ' << (it == set.end() ? 0.f : it->second.second) << ' ';
                }
                f << '\n';
            };
            rows("state_w", S, {{3, {0.01f, 0.f}}});
            rows("action_w", A, {{0, {1.f, -1.f}}});
            rows("card", 372, {{6, {0.5f, 0.f}}});
            rows("target_w", 9, {{1, {0.1f, 0.f}}});
            f << "b1\n0 2\nw2\n1 1\nb2\n0\nw3\n2\nb3\n0.25\n";
        }
        search::CombatValueNet mlp;
        const bool loaded = mlp.load(path.string()) && mlp.isPolicyMlp && mlp.isPolicy;
        check(loaded, "combat_policy_mlp_v1 loads");
        std::vector<float> state(S, 0.f), actions(2 * A, 0.f);
        state[3] = 10.f;                                       // curHp
        state[search::combatMonsterSlotOffset() + search::kCombatMonsterSlotFeatures + 1] = 7.f;   // m1Hp
        actions[0] = 1.f; actions[4] = 5.f;                    // aIsCard, aCardId 5 -> card row 6
        actions[A + 4] = -1.f;                                 // no card -> card row 0
        const int targets[2] = {1, -1};
        double out[2] = {0, 0};
        if (loaded) mlp.predictPolicyMlp(state.data(), actions.data(), targets, 2, out);
        check(std::abs(out[0] - 6.85) < 1e-5 && std::abs(out[1] - 4.45) < 1e-5,
              "combat_policy_mlp_v1 logits match the hand computation");
        // combat_policy_mlp_v2 embedding tables: encounter 5 -> enc row 5, m0 id 7
        // -> mon_id row 8, m0 incoming damage 3 -> mon_dmg row 3; the empty slot
        // m1 (id -1, damage 9) must add nothing, so rows 0 and 9 carry large
        // poison values. The same tables under the v1 header must not load.
        {
            std::ofstream f(path, std::ios::app);
            auto table = [&](const char *key, std::map<int, std::pair<float, float>> set) {
                f << key << " 128\n";
                for (int r = 0; r < 128; ++r) {
                    const auto it = set.find(r);
                    f << (it == set.end() ? 0.f : it->second.first) << ' ' << (it == set.end() ? 0.f : it->second.second) << ' ';
                }
                f << '\n';
            };
            table("enc", {{5, {1.f, 0.f}}});
            table("mon_id", {{0, {100.f, 100.f}}, {8, {0.5f, 0.f}}});
            table("mon_dmg", {{3, {0.f, 0.25f}}, {9, {100.f, 100.f}}});
        }
        search::CombatValueNet v1Tables;
        check(!v1Tables.load(path.string()), "combat_policy_mlp_v1 with embedding tables is rejected");
        {
            std::ifstream in(path);
            std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
            text.replace(0, std::string("combat_policy_mlp_v1").size(), "combat_policy_mlp_v2");
            std::ofstream(path) << text;
        }
        search::CombatValueNet emb;
        const bool embLoaded = emb.load(path.string()) && emb.isPolicyMlp;
        check(embLoaded, "combat_policy_mlp_v2 with embedding tables loads");
        const int mon = search::combatMonsterSlotOffset(), mf = search::kCombatMonsterSlotFeatures;
        state[1] = 5.f;                                        // encounter
        state[mon] = 7.f; state[mon + 4] = 3.f;                // m0Id, m0 incoming damage
        state[mon + mf] = -1.f; state[mon + mf + 4] = 9.f;     // m1: empty slot
        if (embLoaded) emb.predictPolicyMlp(state.data(), actions.data(), targets, 2, out);
        check(std::abs(out[0] - 10.35) < 1e-5 && std::abs(out[1] - 7.95) < 1e-5,
              "policy MLP embedding tables add per node and skip empty slots");
        std::filesystem::remove(path);
    }

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
        const auto both = playBattleWithSilverSearcher(123, MonsterEncounter::CULTIST, 200, true, true);
        check(off.actions == both.actions && off.rng == both.rng && off.hp == both.hp
              && off.turn == both.turn && off.outcome == both.outcome && off.reroots == both.reroots,
              "combined tree profiling and useless-action proof preserve fight and RNG");
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

// Throughput profile of native Silver search (issue #350). Collects the
// decision roots of a mid-run Ironclad deck fighting encounters from all three
// acts (played at 100 simulations a decision), then times a search of `sims`
// simulations from every `stride`-th root, one searcher per combat as in
// production. Output is deterministic apart from the timings; `digest`
// fingerprints every root's edge visits.
int silverProfile(std::int64_t sims, int stride) {
    const std::pair<MonsterEncounter, int> encounters[] = {
        {MonsterEncounter::JAW_WORM, 1}, {MonsterEncounter::GREMLIN_NOB, 1},
        {MonsterEncounter::LAGAVULIN, 1}, {MonsterEncounter::THE_GUARDIAN, 1},
        {MonsterEncounter::HEXAGHOST, 1}, {MonsterEncounter::CHOSEN, 2},
        {MonsterEncounter::BOOK_OF_STABBING, 2}, {MonsterEncounter::AUTOMATON, 2},
        {MonsterEncounter::CHAMP, 2}, {MonsterEncounter::THREE_DARKLINGS, 3},
        {MonsterEncounter::NEMESIS, 3}, {MonsterEncounter::TIME_EATER, 3},
    };
    const CardId extraCards[] = {
        CardId::INFLAME, CardId::SHRUG_IT_OFF, CardId::POMMEL_STRIKE, CardId::CARNAGE,
        CardId::BATTLE_TRANCE, CardId::UPPERCUT, CardId::FEEL_NO_PAIN, CardId::TWIN_STRIKE,
        CardId::HEADBUTT, CardId::TRUE_GRIT, CardId::METALLICIZE, CardId::HEMOKINESIS,
    };
    struct Combat {
        search::SilverSearchContext context;
        std::vector<BattleContext> roots;
    };
    std::vector<Combat> combats;
    std::size_t rootCount = 0;
    int decisions = 0;
    for (const auto &[encounter, act] : encounters) {
        GameContext gc(CharacterClass::IRONCLAD, 7, 0);
        gc.act = act;
        gc.curHp = gc.maxHp = 80;
        for (const auto id : extraCards) gc.deck.obtainRaw(Card(id));
        gc.obtainRelic(RelicId::VAJRA);
        gc.obtainRelic(RelicId::ORICHALCUM);
        gc.potions[0] = Potion::FIRE_POTION;
        gc.potions[1] = Potion::BLOCK_POTION;
        gc.potionCount = 2;

        BattleContext bc;
        search::CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(bc);
        knowledge.beginCombatInitialization();
        search::g_combatKnowledgeObserver = &knowledge;
        bc.init(gc, encounter);
        knowledge.synchronizeAfterCombatInitialization(bc);
        search::SilverSearchContext context;
        context.act = act;
        combats.push_back({context, {}});
        int steps = 0;
        while (bc.outcome == Outcome::UNDECIDED && ++steps < 400) {
            knowledge.reconcilePublicDrawPileCardinality(bc);
            BattleContext root;
            if (!search::nativeSilverSearchRoot(bc, knowledge, root).empty()) break;
            if (decisions++ % stride == 0) {
                combats.back().roots.push_back(root);
                ++rootCount;
            }
            search::g_combatKnowledgeObserver = nullptr;
            search::SilverSearcher searcher(root, context);
            searcher.search(100);
            search::g_combatKnowledgeObserver = &knowledge;
            const auto action = search::SilverSearcher::translateAction(
                searcher.bestAction(), searcher.rootSearchState(), bc);
            if (!action.isValidAction(bc)) break;
            action.execute(bc);
        }
        search::g_combatKnowledgeObserver = nullptr;
    }

    // As in production: one searcher per combat, re-rooted at each decision.
    std::int64_t totalSims = 0;
    std::int64_t totalNodes = 0;
    std::uint64_t digest = 0;
    double seconds = 0.0;
    for (const auto &combat : combats) {
        if (combat.roots.empty()) continue;
        search::SilverSearcher searcher(combat.roots.front(), combat.context);
        for (const auto &root : combat.roots) {
            const auto start = std::chrono::steady_clock::now();
            searcher.setRoot(root);
            searcher.search(sims);
            seconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            totalSims += searcher.rootNode().simulationCount;
            // Search outcome fingerprint: parity checks for speed changes.
            for (const auto &edge : searcher.rootNode().edges) {
                digest = digest * 1000003 + static_cast<std::uint64_t>(edge.visitCount);
            }
            digest = digest * 1000003 + static_cast<std::uint64_t>(search::hashBattleState(root));
        }
        totalNodes += searcher.stats.nodesCreated;
    }
    std::cout << "silver_profile roots=" << rootCount << " decisions=" << decisions
              << " sims=" << totalSims << " nodes=" << totalNodes << " digest=" << digest
              << " seconds=" << seconds
              << " sims_per_s=" << (seconds > 0 ? static_cast<double>(totalSims) / seconds : 0.0) << '\n';
    return 0;
}

// The wire path used by the live advisor (live state -> wire -> search root)
// gives the same search state as the native backend's own search root, and
// actions chosen on it map back onto the live state.
int testPersistentLatentDamage() {
    int failures=0;
    auto check=[&](bool ok,const char *what) { if(!ok) { std::cerr<<"persistent_latent_damage FAIL: "<<what<<'\n'; ++failures; } };
    const auto lice=Monster::latentDamagePrior(MonsterId::RED_LOUSE,0);
    check(lice==((1u<<5)|(1u<<6)|(1u<<7)),"constructor uniform louse support");
    check(Monster::latentDamagePrior(MonsterId::GREEN_LOUSE,2)==((1u<<6)|(1u<<7)|(1u<<8)),"ascended louse support");
    check(Monster::latentDamagePrior(MonsterId::DARKLING,0)==0xf80,"Darkling support");
    check(Monster::latentDamagePrior(MonsterId::DARKLING,2)==0x3e00,"ascended Darkling support");
    GameContext gc(CharacterClass::IRONCLAD,11,0);
    BattleContext base; base.init(gc,MonsterEncounter::JAW_WORM);
    base.intentsHidden=true;
    auto &m=base.monsters.arr[0];
    m.id=MonsterId::RED_LOUSE; m.latentDamageMask=lice; m.latentDamageMaterialized=false;
    m.miscInfo=0; m.pendingMoveRolls=0; m.pendingRollInputs={}; m.pendingRollInputHistory.clear();
    m.moveHistory[0]=MMID::RED_LOUSE_BITE; m.moveHistory[1]=MMID::INVALID;
    base.actionQueue.clear(); base.cardQueue.clear();
    base.player.curHp=50; base.player.maxHp=80; base.player.block=0;
    auto sampled=base; sampled.monsters.arr[0].materializePendingMove(sampled);
    const int value=sampled.monsters.arr[0].miscInfo;
    check(value>=5 && value<=7 && sampled.monsters.arr[0].latentDamageMaterialized,"one-time sample in support");
    std::uint16_t observedSamples=0;
    for(int k=0;k<64;++k) {
        auto particle=base; particle.monsterHpRng=Random(k);
        particle.monsters.arr[0].materializePendingMove(particle);
        observedSamples|=std::uint16_t(1u<<particle.monsters.arr[0].miscInfo);
    }
    check(observedSamples==lice,"fresh worlds retain all prior candidates");
    search::SilverSearchContext nodeContext;
    search::SilverSearcher cached(sampled,nodeContext);
    check(cached.rootSearchState().monsters.arr[0].miscInfo==0 && !cached.rootSearchState().monsters.arr[0].latentDamageMaterialized,
        "cached root stores public belief rather than first sampled world");
    cached.setRoot(sampled);
    check(!cached.rootSearchState().monsters.arr[0].latentDamageMaterialized,"repeated root reuse resamples world from posterior");
    const auto sampledRng=sampled.monsterHpRng;
    sampled.monsters.arr[0].halfDead=true;
    sampled.monsters.arr[0].materializePendingMove(sampled);
    check(sampled.monsters.arr[0].miscInfo==value && sampled.monsterHpRng==sampledRng,"sample persists through half-dead/revival and repeated moves");
    auto other=sampled; other.monsters.arr[0].miscInfo=value==5?6:5;
    check(CombatObservation::fromBattleContext(sampled)==CombatObservation::fromBattleContext(other),"public observation excludes private scalar");
    check(CombatObservation::fromBattleContext(sampled).visibleHash()==CombatObservation::fromBattleContext(other).visibleHash(),"public observation hash excludes private scalar");
    check(sampled.equalForSearch(other),"private sampled scalar does not split public node");
    check(!(sampled==other),"ordinary simulator equality retains private scalar");
    check(search::hashBattleState(sampled)==search::hashBattleState(other),"public hash excludes sampled scalar");
    other.monsters.arr[0].latentDamageMask=1u<<5;
    check(!sampled.equalForSearch(other) && search::hashBattleState(sampled)!=search::hashBattleState(other),"posterior changes public identity");
    auto hit=[&](BattleContext before,int concrete) {
        before.monsters.arr[0].miscInfo=concrete; before.monsters.arr[0].latentDamageMaterialized=true;
        const int damage=before.monsters.arr[0].calculateDamageToPlayer(before,concrete);
        ActData_AttackPlayer{0,damage}(before);
        return before;
    };
    PublicDamageObservation observation;
    observation.maxHp=80; observation.beforeHp=50; observation.afterHp=44;
    check(filterPublicDamageBelief(lice,observation)==(1u<<6),"public scalar history filter matches native clone outcome");
    observation.afterHp=50; observation.beforeBuffer=1; observation.afterBuffer=1;
    check(filterPublicDamageBelief(lice,observation)==lice,"scalar Buffer history retains indistinguishable support");
    observation.beforeBuffer=0; observation.afterBuffer=0; observation.intangible=true; observation.afterHp=49;
    check(filterPublicDamageBelief(lice,observation)==lice,"scalar Intangible history retains indistinguishable support");
    observation.intangible=false; observation.beforeHp=1; observation.afterHp=0;
    check(filterPublicDamageBelief(lice,observation)==lice,"scalar overkill history retains indistinguishable support");
    observation.reviveHp=40; observation.afterHp=40;
    check(filterPublicDamageBelief(lice,observation)==lice,"scalar resurrection history retains indistinguishable support");
    auto exact=hit(base,6);
    check(exact.monsters.arr[0].latentDamageMask==(1u<<6),"unblocked hit identifies exact candidate");
    auto weak=base; weak.monsters.arr[0].buff<MonsterStatus::WEAK>(1);
    weak=hit(weak,6); check(weak.monsters.arr[0].latentDamageMask==(1u<<6),"Weak floor-conditioned outcome");
    auto buffer=base; buffer.player.buff<PlayerStatus::BUFFER>(1);
    buffer=hit(buffer,6); check(buffer.monsters.arr[0].latentDamageMask==lice,"Buffer-censored outcomes retain every candidate");
    auto intangible=base; intangible.player.buff<PlayerStatus::INTANGIBLE>(1);
    intangible=hit(intangible,6); check(intangible.monsters.arr[0].latentDamageMask==lice,"Intangible retains indistinguishable candidates");
    auto overkill=base; overkill.player.curHp=1;
    overkill=hit(overkill,6); check(overkill.monsters.arr[0].latentDamageMask==lice,"overkill-censored HP retains every candidate");
    auto fairy=base; fairy.player.curHp=1;
    fairy.potionCapacity=1; fairy.potionCount=1; fairy.potions[0]=Potion::FAIRY_POTION;
    const auto fairy5=hit(fairy,5), fairy7=hit(fairy,7);
    check(fairy5.player.lastAttackUnblockedDamage==1 && fairy7.player.lastAttackUnblockedDamage==1,
        "public last damage caps lethal loss before Fairy revival");
    check(fairy5.monsters.arr[0].latentDamageMask==lice && fairy7.monsters.arr[0].latentDamageMask==lice
        && fairy5.equalForSearch(fairy7),"censored lethal Fairy worlds retain equal public state");
    auto tail=base; tail.player.curHp=1; tail.player.setHasRelic<RelicId::LIZARD_TAIL>(true);
    const auto tail5=hit(tail,5), tail7=hit(tail,7);
    check(tail5.player.curHp==40 && tail5.player.lastAttackUnblockedDamage==1 && tail5.equalForSearch(tail7),
        "censored lethal Lizard Tail worlds retain equal public state");
    auto blocked=base; blocked.player.block=20;
    blocked=hit(blocked,6); check(blocked.monsters.arr[0].latentDamageMask==(1u<<6),"public block consumption conditions exact candidate");
    search::CombatKnowledgeState knowledge;
    knowledge.configureHiddenMonsterIntents(true); knowledge.beginCombatInitialization();
    auto *saved=search::g_combatKnowledgeObserver; search::g_combatKnowledgeObserver=&knowledge;
    search::emitMonsterOccupantReset(0,1); search::emitMonsterLatentDamagePrior(0,lice);
    search::emitHiddenMonsterIntentRollStarted(0,{},0,0,6);
    search::g_combatKnowledgeObserver=saved;
    check(knowledge.publicMonsterMiscInfo[0]==0 && knowledge.pendingHiddenIntentInputs[0].miscInfo==0,"observer redacts constructor sample at roll site");
    knowledge.initializationInProgress=false;
    search::g_combatKnowledgeObserver=&knowledge;
    search::emitMonsterOccupantReset(0,2);
    search::g_combatKnowledgeObserver=saved;
    check(knowledge.monsterOccupantGeneration[0]==2 && knowledge.latentDamageMasks[0]==0 && knowledge.pendingHiddenIntentRolls[0]==0,"replacement clears prior occupant knowledge");
    search::SilverSearchContext context;
    const auto wire=search::wireFromSearchState(base,context);
    auto visible=base; visible.intentsHidden=false;
    visible.monsters.arr[0].miscInfo=6; visible.monsters.arr[0].latentDamageMaterialized=true;
    search::CombatKnowledgeState visibleKnowledge;
    visibleKnowledge.initializeFromLiveBattle(visible);
    const auto visibleConversion=search::makeSilverBattleStateConversion(visible,visibleKnowledge,search::makeSilverRunContext(gc),11);
    check(visibleConversion.wire.monsters[0].latentDamageMask==0 && visibleConversion.wire.monsters[0].miscInfo==6,
        "visible conversion canonicalizes belief metadata while preserving public scalar");
    const auto visibleWire=search::wireFromSearchState(visible,context);
    check(visibleWire.monsters[0].latentDamageMask==0 && visibleWire.monsters[0].miscInfo==6,
        "visible native wire canonicalizes belief metadata while preserving public scalar");
    BattleContext visibleRoot;
    check(search::nativeSilverSearchRoot(visible,visibleKnowledge,visibleRoot).empty(),"visible native root is supported");
    check(visibleRoot.monsters.arr[0].latentDamageMask==0 && !visibleRoot.monsters.arr[0].latentDamageMaterialized
        && visibleRoot.monsters.arr[0].miscInfo==6 && visibleRoot.equalForSearch(search::battleContextFromWire(visibleConversion.wire)),
        "visible root and imported wire agree on canonical constructor state");
    check(visible.monsters.arr[0].latentDamageMask==lice && visible.monsters.arr[0].latentDamageMaterialized,
        "public conversion preserves raw simulator constructor metadata");
    const auto restored=search::battleContextFromWire(wire);
    check(restored.monsters.arr[0].latentDamageMask==lice && !restored.monsters.arr[0].latentDamageMaterialized,"wire restores belief without private sample");
    nlohmann::json j=wire;
    const auto jsonWire=j.get<silver_bridge::BattleStateWire>();
    check(jsonWire.monsters[0].latentDamageMask==lice,"JSON posterior survives roundtrip");
    auto rejects=[&](silver_bridge::BattleStateWire bad) {
        try { (void)search::battleContextFromWire(bad); return false; } catch(const std::exception &) { return true; }
    };
    auto bad=wire; bad.monsters[0].latentDamageMask=0; check(rejects(bad),"missing latent prior rejects");
    bad=wire; bad.monsters[0].latentDamageMask=1u<<8; check(rejects(bad),"out-of-prior damage rejects");
    bad=wire; bad.monsters[0].miscInfo=6; check(rejects(bad),"private scalar rejects");
    bad=wire; bad.monsters[0].pendingRollInputs.miscInfo=6; check(rejects(bad),"private roll scalar rejects");
    for(const auto &invalid: {nlohmann::json(-1),nlohmann::json(65536),nlohmann::json(3.5),nlohmann::json(true)}) {
        auto malformed=j; malformed["monsters"][0]["latentDamageMask"]=invalid;
        bool rejected=false; try { (void)malformed.get<silver_bridge::BattleStateWire>(); } catch(const std::exception &) { rejected=true; }
        check(rejected,"malformed JSON damage mask rejects before narrowing");
    }
    const auto bytes=serializeBattleContext(sampled);
    const auto binary=deserializeBattleContext(bytes.data(),bytes.size());
    check(binary.monsters.arr[0].latentDamageMask==lice && binary.monsters.arr[0].miscInfo==value
        && binary.monsters.arr[0].latentDamageMaterialized,"binary preserves persistent particle and public belief");
    auto read32=[](const std::vector<std::uint8_t> &b,std::size_t at) { return std::uint32_t(b[at]) | (std::uint32_t(b[at+1])<<8) | (std::uint32_t(b[at+2])<<16) | (std::uint32_t(b[at+3])<<24); };
    std::size_t persistentOffset=0;
    for(std::size_t at=16;at+5<=bytes.size();) {
        const auto length=read32(bytes,at+1);
        if(bytes[at]==8) { persistentOffset=at+5; break; }
        at+=5+length;
    }
    check(persistentOffset!=0,"v4 includes required persistent metadata group");
    if(persistentOffset) {
        auto malformed=bytes;
        for(int i=0;i<4;++i) malformed[persistentOffset+4+i]=0;
        check(!deserializeBattleContext(malformed.data(),malformed.size()).intentsHidden,"binary hidden constructor without posterior rejects");
        malformed=bytes; malformed[persistentOffset+8]=false;
        check(!deserializeBattleContext(malformed.data(),malformed.size()).intentsHidden,"binary unmaterialized private scalar rejects");
    }
    std::cout<<"persistent_latent_damage "<<(failures?"FAIL":"PASS")<<'\n'; return failures?1:0;
}

int testSilverWireState() {
    int failures = 0;
    auto check = [&](bool ok, const std::string &what) {
        if (!ok) {
            if (failures < 20) std::cerr << "silver_wire_state FAIL: " << what << '\n';
            ++failures;
        }
    };
    {
        // Toolbox can stop before opening draws and another relic's effects.
        // The exact typed tail must survive both public/native wire paths,
        // preserving order, action parameters and victory flags.
        GameContext gc(CharacterClass::IRONCLAD, 11, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        bc.inputState = InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::DISCOVERY;
        bc.cardSelectInfo.cards = {CardId::FINESSE,CardId::FLASH_OF_STEEL,CardId::PANACEA};
        bc.cardSelectInfo.pickCount = 1;
        bc.curCardQueueItem = CardQueueItem{};
        bc.actionQueue.clear();
        bc.addToBot(Actions::GainBlock(7));
        bc.addToBot(Actions::GainEnergy(1));
        bc.addToBot(Actions::BuffPlayer<PlayerStatus::ARTIFACT>(1));
        bc.addToBot(Actions::DebuffPlayer<PlayerStatus::LOSE_STRENGTH>(2,false));
        bc.addToBot(Actions::DamageAllEnemy(3));
        bc.addToBot(Actions::DamageRandomEnemy(1));
        bc.addToBot(Actions::UpgradeRandomCardAction());
        bc.addToBot(Actions::DrawCards(2));
        bc.addToBot(Actions::GambleAction());
        bc.addToBot(Actions::DebuffAllEnemy<MonsterStatus::VULNERABLE>(1,false));
        bc.addToBot(Actions::MakeTempCardInDrawPile(CardInstance(CardId::WOUND),2,true));
        bc.addToBot(Actions::DebuffPlayer<PlayerStatus::WEAK>(1,false));
        bc.addToBot(Actions::BuffPlayer<PlayerStatus::PEN_NIB>(1));
        bc.addToBot(Actions::RemoveStatus<PlayerStatus::PEN_NIB>());
        bc.addToBot(Actions::RemovePlayerDebuffs());
        bc.addToBot(Actions::HealPlayer(5,true));
        search::CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(bc);
        auto wire=search::makeSilverBattleStateWire(bc,knowledge,search::makeSilverRunContext(gc),0x5eedu);
        check(wire.pendingActionQueueObserved && wire.pendingActionQueue.size()==16,
              "typed selector tail must be observed completely");
        auto restored=search::battleContextFromWire(wire);
        check(restored.actionQueue==bc.actionQueue,"typed selector tail changed order or parameters");
        const auto context=search::searchContextFromWire(wire);
        auto second=search::wireFromSearchState(restored,context);
        check(second.pendingActionQueueObserved && search::battleContextFromWire(second).actionQueue==bc.actionQueue,
              "typed selector tail must survive search-state wire round trip");
        const auto persisted=silver_bridge::battleStateWireFromEnvelope(silver_bridge::battleStateWireEnvelope(wire));
        check(persisted.pendingActionQueueObserved && search::battleContextFromWire(persisted).actionQueue==bc.actionQueue,
              "typed selector tail must survive persisted JSON envelope round trip");
        const auto reject=[&](silver_bridge::BattleStateWire bad,const char *message) {
            bool threw=false;
            try { (void)search::battleContextFromWire(bad); }
            catch(const std::invalid_argument &) { threw=true; }
            check(threw,message);
        };
        auto bad=wire; bad.pendingActionQueue[0].kind=silver_bridge::PendingActionKind::INVALID;
        reject(bad,"unknown pending action must reject");
        bad=wire; bad.pendingActionQueue[0].amount=-1; reject(bad,"negative pending amount must reject");
        bad=wire; bad.pendingActionQueue[0].status=1; reject(bad,"extraneous pending status must reject");
        bad=wire; bad.pendingActionQueue[2].status=static_cast<int>(PlayerStatus::ARTIFACT)+256;
        reject(bad,"wrapped status must reject");
        bad=wire; bad.pendingActionQueue[3].sourceMonster=true; reject(bad,"unqualified debuff source must reject");
        bad=wire; bad.pendingActionQueue[9].status=static_cast<int>(MonsterStatus::STRENGTH);
        reject(bad,"unqualified enemy power must reject");
        bad=wire; bad.pendingActionQueue[10].amount=1; reject(bad,"unqualified Wound count must reject");
        bad=wire; bad.pendingActionQueue[12].amount=2; reject(bad,"unqualified Pen Nib amount must reject");
        bad=wire; bad.pendingActionQueue[13].amount=1; reject(bad,"Pen Nib removal cannot carry amount");
        bad=wire; bad.pendingActionQueue[14].status=static_cast<int>(PlayerStatus::WEAK);
        reject(bad,"Pellets cleanup cannot carry arbitrary status");
        bad=wire; bad.pendingActionQueue[15].amount=0; reject(bad,"Toy heal tail needs a positive amount");
        bad=wire; bad.pendingActionQueue[0]={silver_bridge::PendingActionKind::USE_CARD,0,0,false};
        reject(bad,"card cleanup without physical owner must reject");
        bad=wire; bad.pendingActionQueue.resize(129); reject(bad,"oversized pending queue must reject");
        bad=wire; bad.pendingActionQueueObserved=false; reject(bad,"unobserved nonempty pending queue must reject");
        bad=wire; bad.inputState=static_cast<int>(InputState::PLAYER_NORMAL); reject(bad,"normal root cannot carry selector tail");
        bc.actionQueue.clear(); bc.addToBot(Actions::NoOpRollMove());
        search::capturePendingActionQueue(bc,wire);
        check(!wire.pendingActionQueueObserved && wire.pendingActionQueue.empty(),"unknown native tails stay unobserved");
        bc.actionQueue.clear(); auto block=Actions::GainBlock(2); block.clearOnCombatVictory=true; bc.addToBot(block);
        search::capturePendingActionQueue(bc,wire);
        check(!wire.pendingActionQueueObserved,"changed native victory flags cannot be discarded");
        bc.actionQueue.clear(); bc.addToBot(Actions::HealPlayer(5)); search::capturePendingActionQueue(bc,wire);
        check(!wire.pendingActionQueueObserved,"only the victory-surviving Toy heal maps to HEAL_PLAYER");
        bc.actionQueue.clear(); search::capturePendingActionQueue(bc,wire);
        check(wire.pendingActionQueueObserved && wire.pendingActionQueue.empty(),"observed empty tail must stay exact");
        auto envelope=silver_bridge::battleStateWireEnvelope(persisted);
        envelope["state"]["pendingActionQueue"][0]["kind"]=257;
        bool invalidKind=false;
        try { (void)silver_bridge::battleStateWireFromEnvelope(envelope); }
        catch(const std::invalid_argument &) { invalidKind=true; }
        check(invalidKind,"JSON pending action kind cannot wrap to a known enum");
    }
    {
        // A Headbutt played under Double Tap stops at its discard selection
        // with the Double Tap copy in the card queue. The replay cannot
        // rebuild that copy (the status is spent), so the wire carries the
        // observed card queue.
        GameContext gc(CharacterClass::IRONCLAD, 11, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        for (int played = 0; played < 2;) {
            int idx = 0;
            while (idx < bc.cards.cardsInHand && bc.cards.hand[idx].id != CardId::DEFEND_RED
                   && bc.cards.hand[idx].id != CardId::STRIKE_RED) ++idx;
            check(idx < bc.cards.cardsInHand, "double tap fixture: no Strike or Defend in hand");
            if (idx == bc.cards.cardsInHand) break;
            search::Action(search::ActionType::CARD, idx, 0).execute(bc);
            ++played;
        }
        CardInstance headbutt(CardId::HEADBUTT);
        headbutt.uniqueId = 900;
        bc.cards.moveToHand(headbutt);
        bc.player.buff<PlayerStatus::DOUBLE_TAP>(1);
        search::Action(search::ActionType::CARD, bc.cards.cardsInHand - 1, 0).execute(bc);
        check(bc.inputState == InputState::CARD_SELECT
                  && bc.cardSelectInfo.cardSelectTask == CardSelectTask::HEADBUTT
                  && bc.cardQueue.size == 1 && bc.cardQueue.front().purgeOnUse,
              "double tap fixture: Headbutt did not stop at its selection with a queued copy");

        search::CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(bc);
        const auto wire = search::makeSilverBattleStateWire(bc, knowledge, search::makeSilverRunContext(gc), 0x5eedu);
        check(wire.valid && wire.pendingCardQueueObserved && wire.pendingCardQueue.size() == 1,
              "double tap fixture: wire did not observe the card queue");
        const BattleContext root = search::battleContextFromWire(wire);
        check(root.cardQueue == bc.cardQueue, "double tap fixture: search root lost the Double Tap copy");
        check(root.actionQueue.size == bc.actionQueue.size, "double tap fixture: action queue differs");
        check(search::battleContextFromWire(silver_bridge::battleStateWireFromEnvelope(
                  silver_bridge::battleStateWireEnvelope(wire))).cardQueue == bc.cardQueue,
              "double tap fixture: observed card queue lost in JSON envelope");
        const auto context = search::searchContextFromWire(wire);
        check(search::battleContextFromWire(search::wireFromSearchState(root, context)).cardQueue == root.cardQueue,
              "double tap fixture: card queue lost in the search-state wire round trip");
        auto unobserved = wire;
        unobserved.pendingCardQueueObserved = false;
        unobserved.pendingCardQueue.clear();
        check(search::battleContextFromWire(unobserved).cardQueue.size == 0,
              "double tap fixture: without an observed queue the replay is expected to miss the copy");
    }

    {
        // A Headbutt whose hit exhausts the Guardian's Mode Shift opens its
        // selection with the shift applied and its 20 block queued behind the
        // card. Vanilla defers the shift, so the live view at that selection
        // still shows Mode Shift at or below zero and the pre-hit move; the
        // search root built from that view must match the engine's.
        GameContext gc(CharacterClass::IRONCLAD, 11, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::THE_GUARDIAN);
        for (int played = 0; played < 2;) {
            int idx = 0;
            while (idx < bc.cards.cardsInHand && bc.cards.hand[idx].id != CardId::DEFEND_RED) ++idx;
            if (idx == bc.cards.cardsInHand) {
                idx = 0;
                while (idx < bc.cards.cardsInHand && bc.cards.hand[idx].id != CardId::STRIKE_RED) ++idx;
            }
            check(idx < bc.cards.cardsInHand, "mode shift fixture: no Strike or Defend in hand");
            if (idx == bc.cards.cardsInHand) break;
            search::Action(search::ActionType::CARD, idx, 0).execute(bc);
            ++played;
        }
        auto &guardian = bc.monsters.arr[0];
        guardian.block = 0;
        guardian.setStatus<MonsterStatus::MODE_SHIFT>(1);
        const std::array<MonsterMoveId, 2> preHitMoves {guardian.moveHistory[0], guardian.moveHistory[1]};
        CardInstance headbutt(CardId::HEADBUTT);
        headbutt.uniqueId = 901;
        bc.cards.moveToHand(headbutt);
        const int hpBefore = guardian.curHp;
        search::Action(search::ActionType::CARD, bc.cards.cardsInHand - 1, 0).execute(bc);
        const int damage = hpBefore - bc.monsters.arr[0].curHp;
        check(bc.inputState == InputState::CARD_SELECT && damage > 0
                  && !bc.monsters.arr[0].hasStatus<MonsterStatus::MODE_SHIFT>()
                  && bc.monsters.arr[0].moveHistory[0] == MonsterMoveId::THE_GUARDIAN_DEFENSIVE_MODE
                  && bc.actionQueue.size == 2,
              "mode shift fixture: Headbutt did not shift the Guardian at its selection");

        search::CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(bc);
        auto wire = search::makeSilverBattleStateWire(bc, knowledge, search::makeSilverRunContext(gc), 0x5eedu);
        // Java form: the shift (and its 20 block) is still queued as a
        // ChangeStateAction, which the wire settles itself.
        if (wire.pendingActionQueueObserved) {
            check(!wire.pendingActionQueue.empty()
                      && wire.pendingActionQueue.back().kind == silver_bridge::PendingActionKind::MONSTER_GAIN_BLOCK
                      && wire.pendingActionQueue.back().amount == 20,
                  "mode shift fixture: native tail lacks the Mode Shift block");
            wire.pendingActionQueue.pop_back();
        }
        auto &live = wire.monsters[0];
        live.statusBits |= 1ULL << static_cast<int>(MonsterStatus::MODE_SHIFT);
        live.uniquePower0 = 1 - damage;
        live.moveHistory = {static_cast<std::int16_t>(preHitMoves[0]), static_cast<std::int16_t>(preHitMoves[1])};
        const BattleContext root = search::battleContextFromWire(wire);
        check(root.actionQueue == bc.actionQueue, "mode shift fixture: Mode Shift block not queued behind the card");
        check(!root.monsters.arr[0].hasStatus<MonsterStatus::MODE_SHIFT>()
                  && root.monsters.arr[0].moveHistory[0] == bc.monsters.arr[0].moveHistory[0]
                  && root.monsters.arr[0].moveHistory[1] == bc.monsters.arr[0].moveHistory[1],
              "mode shift fixture: deferred shift not settled");
        BattleContext nativeRoot;
        check(search::nativeSilverSearchRoot(bc, knowledge, nativeRoot).empty(), "mode shift fixture: native root");
        nativeRoot.seed = root.seed;
        std::sort(nativeRoot.cards.discardPile.begin(), nativeRoot.cards.discardPile.end());
        std::sort(nativeRoot.cards.exhaustPile.begin(), nativeRoot.cards.exhaustPile.end());
        check(root.equalForSearch(nativeRoot), "mode shift fixture: settled root differs from the native root");
        auto unshifted = wire;
        unshifted.monsters[0].uniquePower0 = 5;
        check(search::battleContextFromWire(unshifted).monsters.arr[0].hasStatus<MonsterStatus::MODE_SHIFT>(),
              "mode shift fixture: a positive Mode Shift must not be settled");
    }

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
                    // Known limit: monster reactions queued by the card's own
                    // pre-selection hit (here a Mode Shift, already applied in
                    // the engine state this wire comes from) are not rebuilt.
                    // Such a root may lack queued actions but must match
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

// Card colors, Dolly's Mirror and Orrery: simulator fidelity fixes for the
// Ironclad A0 domain.
int testSimulatorRelicFidelity() {
    auto fail = [&](const std::string &msg) {
        std::cout << "simulator_relic_fidelity FAIL: " << msg << '\n';
        return 1;
    };

    // Every class transform-pool card carries its class color.
    const CardColor classColors[4] {CardColor::RED, CardColor::GREEN, CardColor::BLUE, CardColor::PURPLE};
    for (int cc = 0; cc < 4; ++cc) {
        for (int i = 0; i < TransformCardPool::cardPoolSize[cc]; ++i) {
            const CardId id = TransformCardPool::colorCardPool[cc][i];
            if (getCardColor(id) != classColors[cc]) {
                return fail(std::string("wrong color for ") + cardEnumStrings[static_cast<int>(id)]);
            }
        }
    }

    // A red card is excluded from its own Ironclad transform.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        Random rng(42);
        for (int i = 0; i < 500; ++i) {
            for (CardId exclude : {CardId::BRUTALITY, CardId::COMBUST}) {
                if (gc.getTransformedCard(rng, exclude, false).getId() == exclude) {
                    return fail("transform returned its own red source card");
                }
            }
        }
    }

    // Dolly's Mirror opens a whole-deck duplicate selector and copies the pick.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        const int deckSize = gc.deck.size();
        if (!gc.obtainRelic(RelicId::DOLLYS_MIRROR)) return fail("Dolly's Mirror opened no screen");
        if (gc.screenState != ScreenState::CARD_SELECT
                || gc.info.selectScreenType != CardSelectScreenType::DUPLICATE
                || gc.info.toSelectCount != 1
                || static_cast<int>(gc.info.toSelectCards.size()) != deckSize) {
            return fail("Dolly's Mirror selector is not a one-pick whole-deck duplicate");
        }
        const CardId picked = gc.info.toSelectCards[deckSize - 1].card.getId();
        gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
        gc.chooseSelectCardScreenOption(deckSize - 1);
        if (gc.deck.size() != deckSize + 1 || gc.deck.cards[deckSize].getId() != picked) {
            return fail("Dolly's Mirror did not add a copy of the picked card");
        }
    }

    // Necronomicon adds Necronomicurse on equip (#406); Omamori blocks it, and
    // removing the curse from the master deck returns it.
    {
        auto countCurse = [](const GameContext &gc) {
            int n = 0;
            for (const auto &c : gc.deck.cards) n += c.getId() == CardId::NECRONOMICURSE;
            return n;
        };
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        const int deckSize = gc.deck.size();
        if (gc.obtainRelic(RelicId::NECRONOMICON)) return fail("Necronomicon opened a screen");
        if (gc.deck.size() != deckSize + 1 || countCurse(gc) != 1) {
            return fail("Necronomicon did not add exactly one Necronomicurse");
        }
        gc.deck.remove(gc, gc.deck.size() - 1);
        if (gc.deck.size() != deckSize + 1 || countCurse(gc) != 1) {
            return fail("removing Necronomicurse did not return it to the deck");
        }

        GameContext warded(CharacterClass::IRONCLAD, 123456789, 0);
        warded.obtainRelic(RelicId::OMAMORI);
        warded.obtainRelic(RelicId::NECRONOMICON);
        if (countCurse(warded) != 0 || warded.relics.getRelicValue(RelicId::OMAMORI) != 1) {
            return fail("Omamori did not block Necronomicurse");
        }
    }

    // Orrery opens five ordinary card rewards.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        gc.curRoom = Room::SHOP;
        if (!gc.obtainRelic(RelicId::ORRERY)) return fail("Orrery opened no screen");
        const auto &r = gc.info.rewardsContainer;
        if (gc.screenState != ScreenState::REWARDS || r.cardRewardCount != 5
                || r.goldRewardCount != 0 || r.relicCount != 0 || r.potionCount != 0) {
            return fail("Orrery did not open exactly five card rewards");
        }
        for (int i = 0; i < 5; ++i) {
            if (r.cardRewards[i].size() != 3) return fail("Orrery card reward is not three cards");
        }
    }

    // Colosseum: a reward-less slaver fight reopens the event; Victory adds
    // rare+uncommon relics, 100 gold, a potion roll and a card reward.
    {
        auto colosseum = [](GameContext &gc) {
            gc.act = 2;
            gc.floorNum = 25;
            gc.curMapNodeY = 9;
            gc.curRoom = Room::EVENT;
            gc.curEvent = Event::COLOSSEUM;
            gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
            gc.setupEvent();
            gc.chooseEventOption(0);
            return gc.screenState == ScreenState::BATTLE
                && gc.info.encounter == MonsterEncounter::COLOSSEUM_EVENT_SLAVERS;
        };

        GameContext leave(CharacterClass::IRONCLAD, 123456789, 0);
        if (!colosseum(leave)) return fail("Colosseum did not enter the slaver fight");
        leave.regainControl(); // BattleContext::exitBattle hands back control
        if (leave.screenState != ScreenState::EVENT_SCREEN || leave.info.eventData != 1
                || search::GameAction::getValidEventSelectBits(leave) != 0x3) {
            return fail("Colosseum did not reopen with Cowardice/Victory");
        }
        leave.chooseEventOption(0);
        if (leave.screenState != ScreenState::MAP_SCREEN) return fail("Colosseum Cowardice did not leave");

        GameContext fight(CharacterClass::IRONCLAD, 123456789, 0);
        if (!colosseum(fight)) return fail("Colosseum did not enter the slaver fight");
        fight.regainControl();
        fight.chooseEventOption(1);
        if (fight.screenState != ScreenState::BATTLE
                || fight.info.encounter != MonsterEncounter::COLOSSEUM_EVENT_NOBS) {
            return fail("Colosseum Victory did not enter the Nob fight");
        }
        fight.regainControl();
        const auto &r = fight.info.rewardsContainer;
        if (fight.screenState != ScreenState::REWARDS || r.goldRewardCount != 1 || r.gold[0] != 100
                || r.relicCount != 2 || getRelicTier(r.relics[0]) != RelicTier::RARE
                || getRelicTier(r.relics[1]) != RelicTier::UNCOMMON || r.cardRewardCount != 1) {
            return fail("Colosseum Victory rewards are wrong");
        }

        // Black Star adds nothing to Colosseum's fixed two-relic reward.
        GameContext star(CharacterClass::IRONCLAD, 123456789, 0);
        star.obtainRelic(RelicId::BLACK_STAR);
        if (!colosseum(star)) return fail("Colosseum did not enter the slaver fight");
        star.regainControl();
        star.chooseEventOption(1);
        star.regainControl();
        if (star.info.rewardsContainer.relicCount != 2) return fail("Black Star changed Colosseum rewards");

        // eliteTrigger: the Nob and Dead Adventurer fights are elites for
        // combat relics; the slaver fight and ordinary event fights are not.
        auto slingStrength = [](Room room, Event event, MonsterEncounter encounter) {
            GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
            gc.obtainRelic(RelicId::SLING_OF_COURAGE);
            gc.curRoom = room;
            gc.curEvent = event;
            gc.info.encounter = encounter;
            BattleContext bc;
            bc.init(gc, encounter);
            return bc.player.strength;
        };
        if (slingStrength(Room::EVENT, Event::COLOSSEUM, MonsterEncounter::COLOSSEUM_EVENT_NOBS) != 2
                || slingStrength(Room::EVENT, Event::DEAD_ADVENTURER, MonsterEncounter::GREMLIN_NOB) != 2
                || slingStrength(Room::ELITE, Event::INVALID, MonsterEncounter::GREMLIN_NOB) != 2) {
            return fail("Sling of Courage did not trigger in an elite-trigger fight");
        }
        if (slingStrength(Room::EVENT, Event::COLOSSEUM, MonsterEncounter::COLOSSEUM_EVENT_SLAVERS) != 0
                || slingStrength(Room::EVENT, Event::MASKED_BANDITS, MonsterEncounter::MASKED_BANDITS_EVENT) != 0) {
            return fail("Sling of Courage triggered outside an elite-trigger fight");
        }

        // Black Star and the Dead Adventurer fight.
        auto adventurerRelics = [](bool blackStar) {
            GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
            if (blackStar) gc.obtainRelic(RelicId::BLACK_STAR);
            gc.curRoom = Room::EVENT;
            gc.curEvent = Event::DEAD_ADVENTURER;
            gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
            gc.setupEvent();
            for (int i = 0; i < 3 && gc.screenState == ScreenState::EVENT_SCREEN; ++i) {
                gc.chooseEventOption(0);
            }
            if (gc.screenState != ScreenState::BATTLE) return -1;
            gc.regainControl();
            return gc.screenState == ScreenState::REWARDS ? gc.info.rewardsContainer.relicCount : -1;
        };
        // The game reads Black Star only in MonsterRoomElite.dropReward, so the
        // default (STS_ENGINE_FIDELITY_FIX) adds nothing; =0 keeps the legacy relic.
        unsetenv("STS_ENGINE_FIDELITY_FIX");
        const int withoutStar = adventurerRelics(false);
        if (withoutStar < 0 || adventurerRelics(true) != withoutStar) {
            return fail("Dead Adventurer fight added a Black Star relic");
        }
        setenv("STS_ENGINE_FIDELITY_FIX", "0", 1);
        const int legacyWithStar = adventurerRelics(true);
        unsetenv("STS_ENGINE_FIDELITY_FIX");
        if (legacyWithStar != adventurerRelics(false) + 1) {
            return fail("legacy: Dead Adventurer fight did not add the Black Star relic");
        }

        // The Nob fight continues the same-floor streams; other fights reseed.
        GameContext a(CharacterClass::IRONCLAD, 123456789, 0);
        GameContext b = a;
        b.aiRng = Random(777, 5);
        b.monsterHpRng = Random(778, 6);
        b.shuffleRng = Random(779, 7);
        b.cardRandomRng = Random(780, 8);
        BattleContext nobsA, nobsB, slaversA, slaversB;
        nobsA.init(a, MonsterEncounter::COLOSSEUM_EVENT_NOBS);
        nobsB.init(b, MonsterEncounter::COLOSSEUM_EVENT_NOBS);
        slaversA.init(a, MonsterEncounter::COLOSSEUM_EVENT_SLAVERS);
        slaversB.init(b, MonsterEncounter::COLOSSEUM_EVENT_SLAVERS);
        if (nobsA.shuffleRng == nobsB.shuffleRng || nobsA.cardRandomRng == nobsB.cardRandomRng
                || nobsA.aiRng == nobsB.aiRng) {
            return fail("Colosseum Nob fight reseeded same-floor streams");
        }
        if (!(slaversA.shuffleRng == slaversB.shuffleRng) || !(slaversA.aiRng == slaversB.aiRng)
                || !(slaversA.cardRandomRng == slaversB.cardRandomRng)) {
            return fail("ordinary fight did not reseed from seed+floor");
        }
    }

    std::cout << "simulator_relic_fidelity PASS\n";
    return 0;
}

// Ironclad card properties and effects audited against the pinned STS1 V2.3.4
// reference: each case is a card where the simulator differed.
int testIroncladCardJavaParity() {
    auto fail = [&](const std::string &msg) {
        std::cout << "ironclad_card_java_parity FAIL: " << msg << '\n';
        return 1;
    };

    // Costs: Rage is 0; Infernal Blade is 1, 0 when upgraded.
    if (CardInstance(CardId::RAGE).cost != 0 || CardInstance(CardId::RAGE, true).cost != 0) {
        return fail("Rage does not cost 0");
    }
    if (CardInstance(CardId::INFERNAL_BLADE).cost != 1 || CardInstance(CardId::INFERNAL_BLADE, true).cost != 0) {
        return fail("Infernal Blade cost is not 1/0");
    }

    // Seeing Red exhausts when played.
    if (!CardInstance(CardId::SEEING_RED).doesExhaust() || !CardInstance(CardId::SEEING_RED, true).doesExhaust()) {
        return fail("Seeing Red does not exhaust");
    }

    // Live parity problem 48 (seed 111200438, floor 32, release 0582219a):
    // Java's MummifiedHand.onUseCard drops every cardQueue card from its
    // candidates, and the played Power's queue item is still in cardQueue, so
    // the Power itself is never a candidate. Game picks: Inflame+ zeroed
    // Sentinel, then Metallicize zeroed the first Defend.
    // STS_MUMMIFIED_HAND_PLAYED_CARD_FIX=0 keeps the legacy candidate set.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_MUMMIFIED_HAND_PLAYED_CARD_FIX");
        else setenv("STS_MUMMIFIED_HAND_PLAYED_CARD_FIX", "0", 1);
        auto zeroedAfterPlay = [](std::initializer_list<CardInstance> hand, int playIdx, int rngCounter) {
            BattleContext bc = simulatorCorrectnessBattle({RelicId::MUMMIFIED_HAND}, Card(CardId::DEFEND_RED), 10);
            while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
                bc.executeActions();
            }
            while (bc.cards.cardsInHand > 0) bc.cards.removeFromHandAtIdx(bc.cards.cardsInHand - 1);
            for (const auto &c : hand) bc.cards.createTempCardInHand(c);
            bc.player.energy = 10;
            bc.cardRandomRng = Random(111200438ULL + 32, rngCounter);
            std::vector<std::int16_t> before;
            for (int i = 0; i < bc.cards.cardsInHand; ++i) {
                if (bc.cards.hand[i].costForTurn > 0) before.push_back(bc.cards.hand[i].getUniqueId());
            }
            simulatorCorrectnessPlay(bc, playIdx, 0);
            while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
                bc.executeActions();
            }
            for (int i = 0; i < bc.cards.cardsInHand; ++i) {
                const auto &c = bc.cards.hand[i];
                if (c.costForTurn == 0 && std::find(before.begin(), before.end(), c.getUniqueId()) != before.end()) {
                    return i;
                }
            }
            return -1;
        };
        CardInstance sentinelFree(CardId::SENTINEL);
        sentinelFree.setCostForTurn(0);
        const int first = zeroedAfterPlay({CardInstance(CardId::DEFEND_RED), CardInstance(CardId::DEFEND_RED),
                                           CardInstance(CardId::SENTINEL), CardInstance(CardId::SECOND_WIND),
                                           CardInstance(CardId::INFLAME, true), CardInstance(CardId::METALLICIZE)}, 4, 0);
        const int second = zeroedAfterPlay({CardInstance(CardId::DEFEND_RED), CardInstance(CardId::DEFEND_RED),
                                            sentinelFree, CardInstance(CardId::SECOND_WIND),
                                            CardInstance(CardId::METALLICIZE)}, 4, 1);
        unsetenv("STS_MUMMIFIED_HAND_PLAYED_CARD_FIX");
        // The legacy pick at the first step is the live native one (the
        // second Defend); at the second it zeroes the played Metallicize.
        if (fix ? (first != 2 || second != 0) : (first != 1 || second != -1)) {
            return fail("Mummified Hand did not reproduce the game's picks");
        }
    }

    // Live parity problem 64b (seed 111200459, Colosseum Nobs): Gremlin Nob
    // with Anger 3 sits in slot 1 behind the Taskmaster; a played Skill gave
    // it Strength 3 in the game, 0 natively. STS_ENRAGE_ALL_MONSTERS_FIX=0
    // keeps the legacy slot-0-only check.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_ENRAGE_ALL_MONSTERS_FIX");
        else setenv("STS_ENRAGE_ALL_MONSTERS_FIX", "0", 1);
        BattleContext bc = simulatorCorrectnessBattle({}, Card(CardId::DEFEND_RED), 10,
                                                      MonsterEncounter::COLOSSEUM_EVENT_NOBS);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        Monster &nob = bc.monsters.arr[1];
        const bool layout = bc.monsters.arr[0].id == MonsterId::TASKMASTER && nob.id == MonsterId::GREMLIN_NOB;
        nob.buff<MS::ENRAGE>(3);
        const int before = nob.getStatus<MS::STRENGTH>();
        bc.player.energy = 10;
        simulatorCorrectnessPlay(bc, 0, 0);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        const int gained = nob.getStatus<MS::STRENGTH>() - before;
        unsetenv("STS_ENRAGE_ALL_MONSTERS_FIX");
        if (!layout || gained != (fix ? 3 : 0)) {
            return fail(fix ? "Gremlin Nob in slot 1 did not gain Anger Strength from a Skill"
                            : "STS_ENRAGE_ALL_MONSTERS_FIX=0 did not restore the slot-0-only check");
        }
    }

    // Disarm+ removes 3 Strength.
    {
        BattleContext bc = simulatorCorrectnessBattle({}, Card(CardId::DISARM, 1), 10);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        const int strengthBefore = bc.monsters.arr[0].strength;
        simulatorCorrectnessPlay(bc, 0, 0);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        if (bc.monsters.arr[0].strength != strengthBefore - 3) return fail("Disarm+ did not remove 3 Strength");
    }

    // Brutality and Pain lose HP as self-damage, which triggers Rupture.
    for (const bool pain : {false, true}) {
        BattleContext bc = simulatorCorrectnessBattle({}, Card(CardId::DEFEND_RED), 10);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        bc.player.buff<PS::RUPTURE>(1);
        const int strengthBefore = bc.player.getStatus<PS::STRENGTH>();
        if (pain) {
            bc.cards.handPainCount = 1;
            bc.triggerOnOtherCardPlayed(CardInstance(CardId::DEFEND_RED));
        } else {
            bc.player.buff<PS::BRUTALITY>(1);
            bc.player.applyStartOfTurnPostDrawPowers(bc);
        }
        while (!bc.actionQueue.isEmpty()) bc.actionQueue.popFront()(bc);
        if (bc.player.getStatus<PS::STRENGTH>() != strengthBefore + 1) {
            return fail(pain ? "Pain HP loss did not trigger Rupture" : "Brutality HP loss did not trigger Rupture");
        }
    }

    // Monster Intangible (Nemesis) caps card damage at 1, keeps 0 at 0, and
    // also caps thorns-type damage (Nemesis.damage override).
    {
        BattleContext bc = simulatorCorrectnessBattle({}, Card(CardId::DEFEND_RED), 10);
        Monster &m = bc.monsters.arr[0];
        m.buff<MS::INTANGIBLE>(1);
        m.block = 0;
        if (bc.calculateCardDamage(CardInstance(CardId::STRIKE_RED), 0, 10) != 1
                || bc.calculateCardDamage(CardInstance(CardId::STRIKE_RED), 0, 0) != 0) {
            return fail("Intangible card damage is not capped at 1 (with 0 kept)");
        }
        const int hpBefore = m.curHp;
        Actions::DamageAllEnemy(5)(bc);
        if (hpBefore - m.curHp != 1) return fail("Intangible did not cap thorns-type damage at 1");
    }

    // Save loading retains both Wing Boots charges and the Tea Set's charged
    // sentinel when the relics are present together.
    for (int teaCounter : {-2, -1}) {
        SaveFile save;
        save.relics = {RelicId::WING_BOOTS, RelicId::ANCIENT_TEA_SET};
        save.relic_counters = {2, teaCounter};
        GameContext restored(CharacterClass::IRONCLAD, 100123, 0);
        restored.initRelicsFromSave(save);
        if (restored.wingBootsCharges != 2
                || restored.relics.getRelicValue(RelicId::WING_BOOTS) != 0
                || restored.relics.getRelicValue(RelicId::ANCIENT_TEA_SET) != (teaCounter == -2 ? 1 : 0)) {
            return fail("save loading lost Wing Boots or Ancient Tea Set state");
        }
    }

    // Ancient Tea Set: charged on entering any rest site, spent by the next
    // combat's first turn, even with other rooms in between.
    {
        GameContext gc(CharacterClass::IRONCLAD, 100123, 0);
        gc.relics.add({RelicId::ANCIENT_TEA_SET, 0});
        gc.map->getNode(0, gc.curMapNodeY + 1).room = Room::REST;
        gc.transitionToMapNode(0);
        if (gc.relics.getRelicValue(RelicId::ANCIENT_TEA_SET) != 1) {
            return fail("Ancient Tea Set was not charged by a rest site");
        }
        gc.curRoom = Room::MONSTER;
        gc.lastRoom = Room::EVENT;
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        if (bc.player.energy != bc.player.energyPerTurn + 2) {
            return fail("charged Ancient Tea Set did not give 2 energy after a non-rest room");
        }
        bc.updateRelicsOnExit(gc);
        if (gc.relics.getRelicValue(RelicId::ANCIENT_TEA_SET) != 0) {
            return fail("Ancient Tea Set charge was not spent by combat");
        }
        BattleContext again;
        again.init(gc, MonsterEncounter::JAW_WORM);
        if (again.player.energy != again.player.energyPerTurn) {
            return fail("spent Ancient Tea Set still gave energy");
        }
    }

    std::cout << "ironclad_card_java_parity PASS\n";
    return 0;
}

// Act 1 monster behavior audited against the pinned STS1 V2.3.4 reference
// (#348): each case reproduces a move roll or monster turn where the simulator differed.
int testMonsterAiJavaParity() {
    auto fail = [&](const std::string &msg) {
        std::cout << "monster_ai_java_parity FAIL: " << msg << '\n';
        return 1;
    };
    auto roll = [](int ascension, MonsterEncounter encounter, MonsterId id,
                   MMID last, MMID beforeLast, int miscInfo, int r) {
        GameContext gc(CharacterClass::IRONCLAD, 100123, ascension);
        gc.curRoom = Room::MONSTER;
        BattleContext bc;
        bc.init(gc, encounter);
        Monster &m = bc.monsters.arr[0];
        m.id = id;
        m.miscInfo = miscInfo;
        m.moveHistory[0] = last;
        m.moveHistory[1] = beforeLast;
        int monsterData = miscInfo;
        return m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, r);
    };

    // Red Slaver repeats Stab after Entangle only on a roll of at least 55.
    for (const int asc : {0, 20}) {
        if (roll(asc, MonsterEncounter::RED_SLAVER, MonsterId::RED_SLAVER,
                 MMID::RED_SLAVER_STAB, MMID::RED_SLAVER_SCRAPE, 1, 52) != MMID::RED_SLAVER_SCRAPE) {
            return fail("Red Slaver stabbed on a roll below 55");
        }
    }

    // A17 slavers never repeat Scrape/Rake; below A17 only a third repeat is blocked.
    const struct { MonsterEncounter enc; MonsterId id; MMID repeat; MMID other; int misc; } slavers[] {
        {MonsterEncounter::RED_SLAVER, MonsterId::RED_SLAVER, MMID::RED_SLAVER_SCRAPE, MMID::RED_SLAVER_STAB, 1},
        {MonsterEncounter::BLUE_SLAVER, MonsterId::BLUE_SLAVER, MMID::BLUE_SLAVER_RAKE, MMID::BLUE_SLAVER_STAB, 0},
    };
    for (const auto &s : slavers) {
        if (roll(17, s.enc, s.id, s.repeat, s.other, s.misc, 10) != s.other) {
            return fail("A17 slaver repeated its debuff attack");
        }
        if (roll(16, s.enc, s.id, s.repeat, s.other, s.misc, 10) != s.repeat) {
            return fail("A16 slaver did not repeat its debuff attack once");
        }
    }

    // A18 Gremlin Nob: Skull Bash whenever neither of the last two moves was one.
    if (roll(18, MonsterEncounter::GREMLIN_NOB, MonsterId::GREMLIN_NOB,
             MMID::GREMLIN_NOB_BELLOW, MMID::INVALID, 0, 50) != MMID::GREMLIN_NOB_SKULL_BASH) {
        return fail("A18 Nob did not Skull Bash after Bellow");
    }
    if (roll(18, MonsterEncounter::GREMLIN_NOB, MonsterId::GREMLIN_NOB,
             MMID::GREMLIN_NOB_RUSH, MMID::GREMLIN_NOB_SKULL_BASH, 0, 50) != MMID::GREMLIN_NOB_RUSH) {
        return fail("A18 Nob Skull Bashed with one in its last two moves");
    }
    if (roll(18, MonsterEncounter::GREMLIN_NOB, MonsterId::GREMLIN_NOB,
             MMID::GREMLIN_NOB_RUSH, MMID::GREMLIN_NOB_RUSH, 0, 50) != MMID::GREMLIN_NOB_SKULL_BASH) {
        return fail("A18 Nob did not Skull Bash after two Rushes");
    }

    // A17 Acid Slime (L) never uses Corrosive Spit three times in a row.
    for (int r = 0; r < 40; ++r) {
        if (roll(17, MonsterEncounter::LARGE_SLIME, MonsterId::ACID_SLIME_L,
                 MMID::ACID_SLIME_L_CORROSIVE_SPIT, MMID::ACID_SLIME_L_CORROSIVE_SPIT, 0, r)
                == MMID::ACID_SLIME_L_CORROSIVE_SPIT) {
            return fail("A17 Acid Slime (L) used Corrosive Spit three times in a row");
        }
    }

    // Monster turns (takeTurn) checked against the same reference.
    auto battle = [](MonsterEncounter encounter, int ascension = 0) {
        GameContext gc(CharacterClass::IRONCLAD, 100123, ascension);
        gc.curRoom = Room::MONSTER;
        BattleContext bc;
        bc.init(gc, encounter);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        return bc;
    };
    auto drain = [](BattleContext &bc) {
        while (!bc.actionQueue.isEmpty()) {
            bc.actionQueue.popFront()(bc);
        }
    };

    // Entangle marks the Red Slaver so it never entangles again.
    {
        BattleContext bc = battle(MonsterEncounter::RED_SLAVER);
        Monster &m = bc.monsters.arr[0];
        m.moveHistory[0] = MMID::RED_SLAVER_ENTANGLE;
        m.miscInfo = 0;
        m.takeTurn(bc);
        drain(bc);
        m.moveHistory[0] = MMID::RED_SLAVER_STAB;
        m.moveHistory[1] = MMID::RED_SLAVER_ENTANGLE;
        int monsterData = m.miscInfo;
        if (m.miscInfo != 1
                || m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, 80) != MMID::RED_SLAVER_STAB) {
            return fail("Red Slaver did not record its Entangle");
        }
    }

    // Lagavulin waking on its third sleeping turn loses Metallicize.
    {
        BattleContext bc = battle(MonsterEncounter::LAGAVULIN);
        Monster &m = bc.monsters.arr[0];
        if (!m.hasStatus<MS::ASLEEP>() || m.getStatus<MS::METALLICIZE>() != 8) {
            return fail("Lagavulin did not start asleep with Metallicize 8");
        }
        bc.turn = 2;
        m.moveHistory[0] = MMID::LAGAVULIN_SLEEP;
        m.takeTurn(bc);
        drain(bc);
        if (m.hasStatus<MS::ASLEEP>() || m.getStatus<MS::METALLICIZE>() != 0
                || !m.lastMove(MMID::LAGAVULIN_ATTACK)) {
            return fail("Lagavulin kept its sleeping Metallicize after waking");
        }
    }

    // Hexaghost Inferno upgrades Burns in the draw and discard piles (not the
    // hand) and adds three upgraded Burns to the discard pile.
    {
        BattleContext bc = battle(MonsterEncounter::HEXAGHOST);
        Monster &m = bc.monsters.arr[0];
        bc.cards.drawPile.addToTop(CardInstance(CardId::BURN));
        bc.cards.discardPile.clear();
        bc.cards.discardPile.push_back(CardInstance(CardId::BURN));
        bc.cards.hand[bc.cards.cardsInHand++] = CardInstance(CardId::BURN);
        m.moveHistory[0] = MMID::HEXAGHOST_INFERNO;
        m.takeTurn(bc);
        drain(bc);
        int discardBurns = 0;
        for (const auto &c : bc.cards.discardPile) {
            if (c.getId() != CardId::BURN) continue;
            ++discardBurns;
            if (!c.isUpgraded()) return fail("Inferno left a discard-pile Burn unupgraded");
        }
        for (const auto &c : bc.cards.drawPile) {
            if (c.getId() == CardId::BURN && !c.isUpgraded()) {
                return fail("Inferno left a draw-pile Burn unupgraded");
            }
        }
        if (discardBurns != 4) return fail("Inferno did not add three Burns to the discard pile");
        if (bc.cards.hand[bc.cards.cardsInHand - 1].isUpgraded()) {
            return fail("Inferno upgraded a Burn in hand");
        }
    }

    // ---- Act 2 (monsters.city) ----

    // Mystic heals on the summed missing HP of living monsters (> 15 at A0),
    // but not after healing on each of its last two moves.
    {
        BattleContext bc = battle(MonsterEncounter::CENTURION_AND_HEALER);
        Monster &centurion = bc.monsters.arr[0];
        Monster &mystic = bc.monsters.arr[1];
        centurion.curHp = centurion.maxHp - 10;
        mystic.curHp = mystic.maxHp - 10;
        int monsterData = 0;
        mystic.moveHistory[0] = MMID::MYSTIC_BUFF;
        mystic.moveHistory[1] = MMID::MYSTIC_ATTACK_DEBUFF;
        if (mystic.getMoveForRoll(bc, mystic.captureRollInputs(bc), monsterData, 10) != MMID::MYSTIC_HEAL) {
            return fail("Mystic did not heal on 20 combined missing HP");
        }
        mystic.moveHistory[0] = MMID::MYSTIC_HEAL;
        mystic.moveHistory[1] = MMID::MYSTIC_HEAL;
        if (mystic.getMoveForRoll(bc, mystic.captureRollInputs(bc), monsterData, 10) == MMID::MYSTIC_HEAL) {
            return fail("Mystic healed three times in a row");
        }
    }

    // Centurion Defend gives a random other monster block, or itself if none.
    {
        BattleContext bc = battle(MonsterEncounter::CENTURION_AND_HEALER);
        Monster &centurion = bc.monsters.arr[0];
        bc.monsters.arr[1].curHp = 0;
        bc.monsters.monstersAlive = 1;
        const int blockBefore = centurion.block;
        centurion.moveHistory[0] = MMID::CENTURION_DEFEND;
        centurion.takeTurn(bc);
        drain(bc);
        if (centurion.block != blockBefore + 15) {
            return fail("Centurion Defend did not fall back to blocking itself");
        }
    }
    {
        BattleContext bc = battle(MonsterEncounter::CENTURION_AND_HEALER);
        Monster &centurion = bc.monsters.arr[0];
        Monster &mystic = bc.monsters.arr[1];
        const int blockBefore = mystic.block;
        const auto counterBefore = bc.aiRng.counter;
        centurion.moveHistory[0] = MMID::CENTURION_DEFEND;
        centurion.takeTurn(bc);
        drain(bc);
        // One draw picks the block target, one rolls the next move.
        if (mystic.block != blockBefore + 15 || bc.aiRng.counter != counterBefore + 2) {
            return fail("Centurion Defend did not pick its target with aiRng");
        }
    }

    // Book of Stabbing at A18 counts a single stab toward the multi-stab.
    for (const int asc : {0, 18}) {
        BattleContext bc = battle(MonsterEncounter::BOOK_OF_STABBING, asc);
        Monster &m = bc.monsters.arr[0];
        m.moveHistory[0] = MMID::BOOK_OF_STABBING_MULTI_STAB;
        m.moveHistory[1] = MMID::BOOK_OF_STABBING_MULTI_STAB;
        int stabCount = 2;
        const auto move = m.getMoveForRoll(bc, m.captureRollInputs(bc), stabCount, 50);
        if (move != MMID::BOOK_OF_STABBING_SINGLE_STAB || stabCount != (asc >= 18 ? 3 : 2)) {
            return fail("Book of Stabbing single stab miscounted at A" + std::to_string(asc));
        }
    }

    // Gremlin Leader with one gremlin after a Stab re-rolls 0..80, and 80 rolls again.
    {
        std::uint64_t seed = 0;
        for (std::uint64_t s = 1; s < 100000 && seed == 0; ++s) {
            Random r(s);
            if (r.random(0, 80) == 80 && r.random(0, 80) < 50) seed = s;
        }
        if (seed == 0) return fail("no Gremlin Leader test seed");
        BattleContext bc = battle(MonsterEncounter::GREMLIN_LEADER);
        Monster &leader = bc.monsters.arr[3];
        bc.monsters.arr[2].curHp = 0;
        --bc.monsters.monstersAlive;
        leader.moveHistory[0] = MMID::GREMLIN_LEADER_STAB;
        leader.moveHistory[1] = MMID::GREMLIN_LEADER_ENCOURAGE;
        bc.aiRng = Random(seed);
        int monsterData = 0;
        if (leader.getMoveForRoll(bc, leader.captureRollInputs(bc), monsterData, 90) != MMID::GREMLIN_LEADER_RALLY
                || bc.aiRng.counter != 2) {
            return fail("Gremlin Leader did not re-roll a nested 80");
        }
    }

    // Gremlin Leader Encourage gives minions 6 block below A18.
    {
        BattleContext bc = battle(MonsterEncounter::GREMLIN_LEADER, 3);
        Monster &leader = bc.monsters.arr[3];
        const int blockBefore = bc.monsters.arr[1].block;
        leader.moveHistory[0] = MMID::GREMLIN_LEADER_ENCOURAGE;
        leader.takeTurn(bc);
        drain(bc);
        if (bc.monsters.arr[1].block != blockBefore + 6) {
            return fail("A3 Gremlin Leader Encourage did not give 6 block");
        }
    }

    // Shelled Parasite: the re-roll after Fell decides the rest of the choice.
    {
        std::uint64_t seed = 0;
        for (std::uint64_t s = 1; s < 1000 && seed == 0; ++s) {
            Random r(s);
            if (r.random(20, 99) >= 60) seed = s;
        }
        if (seed == 0) return fail("no Shelled Parasite test seed");
        BattleContext bc = battle(MonsterEncounter::SHELL_PARASITE);
        Monster &m = bc.monsters.arr[0];
        m.moveHistory[0] = MMID::SHELLED_PARASITE_FELL;
        m.moveHistory[1] = MMID::SHELLED_PARASITE_DOUBLE_STRIKE;
        bc.aiRng = Random(seed);
        int monsterData = 0;
        if (m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, 10) != MMID::SHELLED_PARASITE_SUCK) {
            return fail("Shelled Parasite ignored its re-roll after Fell");
        }
    }

    // A17 Snake Plant never Spores with Spores in either of its last two moves.
    if (roll(17, MonsterEncounter::SNAKE_PLANT, MonsterId::SNAKE_PLANT,
             MMID::SNAKE_PLANT_CHOMP, MMID::SNAKE_PLANT_ENFEEBLING_SPORES, 0, 80) != MMID::SNAKE_PLANT_CHOMP) {
        return fail("A17 Snake Plant used Spores one move after Spores");
    }

    // A19 Bronze Automaton: the Boost after Hyper Beam does not advance the cycle.
    {
        BattleContext bc = battle(MonsterEncounter::AUTOMATON, 19);
        Monster &m = bc.monsters.arr[1];
        m.moveHistory[0] = MMID::BRONZE_AUTOMATON_BOOST;
        m.moveHistory[1] = MMID::BRONZE_AUTOMATON_HYPER_BEAM;
        m.miscInfo = 0;
        m.takeTurn(bc);
        drain(bc);
        if (!m.lastMove(MMID::BRONZE_AUTOMATON_FLAIL) || m.miscInfo != 1) {
            return fail("A19 Automaton next Flail counter is not one");
        }
    }

    // Champ Gloat gains 2 Strength at A0.
    {
        BattleContext bc = battle(MonsterEncounter::CHAMP);
        Monster &m = bc.monsters.arr[0];
        const int strengthBefore = m.strength;
        m.moveHistory[0] = MMID::THE_CHAMP_GLOAT;
        m.takeTurn(bc);
        drain(bc);
        if (m.strength != strengthBefore + 2) return fail("Champ Gloat Strength is not 2 at A0");
    }

    // Collector Buff block is 15 below A9; Mega Debuff applies 5 at A19.
    {
        BattleContext bc = battle(MonsterEncounter::COLLECTOR, 4);
        Monster &m = bc.monsters.arr[2];
        const int blockBefore = m.block;
        m.moveHistory[0] = MMID::THE_COLLECTOR_BUFF;
        m.takeTurn(bc);
        drain(bc);
        if (m.block != blockBefore + 15) return fail("A4 Collector Buff block is not 15");
    }
    {
        BattleContext bc = battle(MonsterEncounter::COLLECTOR, 19);
        Monster &m = bc.monsters.arr[2];
        m.moveHistory[0] = MMID::THE_COLLECTOR_MEGA_DEBUFF;
        m.takeTurn(bc);
        drain(bc);
        if (bc.player.getStatus<PS::WEAK>() != 5 || bc.player.getStatus<PS::FRAIL>() != 5) {
            return fail("A19 Collector Mega Debuff is not 5");
        }
    }

    // A17 Romeo repeats Cross Slash once before Agonizing Slash.
    {
        BattleContext bc = battle(MonsterEncounter::MASKED_BANDITS_EVENT, 17);
        Monster &m = bc.monsters.arr[1];
        m.moveHistory[0] = MMID::ROMEO_CROSS_SLASH;
        m.moveHistory[1] = MMID::ROMEO_AGONIZING_SLASH;
        m.takeTurn(bc);
        drain(bc);
        if (!m.lastMove(MMID::ROMEO_CROSS_SLASH)) return fail("A17 Romeo did not repeat Cross Slash");
        m.takeTurn(bc);
        drain(bc);
        if (!m.lastMove(MMID::ROMEO_AGONIZING_SLASH)) return fail("A17 Romeo used Cross Slash three times");
    }

    // Torch Head consumes a discarded HP roll before its real one.
    {
        Random actual(7), expected(7);
        Monster m;
        m.id = MonsterId::TORCH_HEAD;
        m.initHp(actual, 0);
        expected.random(38, 40);
        const int hp = expected.random(38, 40);
        if (m.curHp != hp || actual.counter != expected.counter) {
            return fail("Torch Head HP did not discard the constructor roll");
        }
    }

    // HP ranges.
    if (monsterHpRange[static_cast<int>(MonsterId::BEAR)][0][1] != 42
            || monsterHpRange[static_cast<int>(MonsterId::CENTURION)][1][0] != 78) {
        return fail("Bear or Centurion HP range differs from the game");
    }

    // ---- Act 3 (monsters.beyond) ----

    // Spire Growth falls through to Constrict after two Quick Tackles.
    if (roll(0, MonsterEncounter::SPIRE_GROWTH, MonsterId::SPIRE_GROWTH,
             MMID::SPIRE_GROWTH_QUICK_TACKLE, MMID::SPIRE_GROWTH_QUICK_TACKLE, 0, 30)
            != MMID::SPIRE_GROWTH_CONSTRICT) {
        return fail("Spire Growth did not Constrict after two Quick Tackles");
    }

    // Writhing Mass after Flail on a high roll re-rolls 0..69.
    {
        std::uint64_t seed = 0;
        for (std::uint64_t s = 1; s < 1000 && seed == 0; ++s) {
            Random r(s);
            const int v = r.random(0, 69);
            if (v >= 40) seed = s;
        }
        if (seed == 0) return fail("no Writhing Mass test seed");
        BattleContext bc = battle(MonsterEncounter::WRITHING_MASS);
        Monster &m = bc.monsters.arr[0];
        m.moveHistory[0] = MMID::WRITHING_MASS_FLAIL;
        m.moveHistory[1] = MMID::WRITHING_MASS_WITHER;
        m.miscInfo = 1;
        bc.aiRng = Random(seed);
        int monsterData = 1;
        if (m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, 80) != MMID::WRITHING_MASS_MULTI_STRIKE) {
            return fail("Writhing Mass did not re-roll after Flail");
        }
    }

    // Writhing Mass Flail block equals its damage (15 at A0).
    {
        BattleContext bc = battle(MonsterEncounter::WRITHING_MASS);
        Monster &m = bc.monsters.arr[0];
        const int blockBefore = m.block;
        m.moveHistory[0] = MMID::WRITHING_MASS_FLAIL;
        m.takeTurn(bc);
        drain(bc);
        if (m.block != blockBefore + 15) return fail("Writhing Mass Flail block is not 15 at A0");
    }

    // Nemesis may Scythe again once a different move came in between.
    if (roll(0, MonsterEncounter::NEMESIS, MonsterId::NEMESIS,
             MMID::NEMESIS_ATTACK, MMID::NEMESIS_SCYTHE, 0, 10) != MMID::NEMESIS_SCYTHE) {
        return fail("Nemesis Scythe was blocked two moves after the last Scythe");
    }
    {
        std::uint64_t seed = 0;
        for (std::uint64_t s = 1; s < 1000 && seed == 0; ++s) {
            Random r(s);
            if (r.randomBoolean()) seed = s;
        }
        if (seed == 0) return fail("no Nemesis test seed");
        BattleContext bc = battle(MonsterEncounter::NEMESIS);
        Monster &m = bc.monsters.arr[0];
        m.moveHistory[0] = MMID::NEMESIS_DEBUFF;
        m.moveHistory[1] = MMID::NEMESIS_SCYTHE;
        bc.aiRng = Random(seed);
        int monsterData = 0;
        if (m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, 80) != MMID::NEMESIS_SCYTHE) {
            return fail("Nemesis high-roll Scythe was blocked two moves after the last Scythe");
        }
    }

    // Nemesis Debuff adds 3 Burns below A18.
    {
        BattleContext bc = battle(MonsterEncounter::NEMESIS, 3);
        Monster &m = bc.monsters.arr[0];
        bc.cards.discardPile.clear();
        m.moveHistory[0] = MMID::NEMESIS_DEBUFF;
        m.takeTurn(bc);
        drain(bc);
        int burns = 0;
        for (const auto &c : bc.cards.discardPile) burns += c.getId() == CardId::BURN;
        if (burns != 3) return fail("A3 Nemesis Debuff did not add 3 Burns");
    }

    // Reptomancer can summon with three daggers alive; at A18 it fills the one free slot.
    {
        for (const int asc : {0, 18}) {
            BattleContext bc = battle(MonsterEncounter::REPTOMANCER, asc);
            Monster &repto = bc.monsters.arr[2];
            bc.monsters.arr[0] = Monster();
            bc.monsters.arr[0].construct(bc, MonsterId::DAGGER, 0);
            ++bc.monsters.monstersAlive;
            repto.moveHistory[0] = MMID::REPTOMANCER_SNAKE_STRIKE;
            repto.moveHistory[1] = MMID::REPTOMANCER_BIG_BITE;
            int monsterData = 0;
            if (repto.getMoveForRoll(bc, repto.captureRollInputs(bc), monsterData, 50) != MMID::REPTOMANCER_SUMMON) {
                return fail("Reptomancer did not summon with three daggers alive");
            }
            repto.moveHistory[0] = MMID::REPTOMANCER_SUMMON;
            repto.takeTurn(bc);
            drain(bc);
            if (bc.monsters.monstersAlive != 5 || bc.monsters.arr[3].id != MonsterId::DAGGER
                    || !bc.monsters.arr[3].isAlive()) {
                return fail("Reptomancer did not fill the last free dagger slot");
            }
        }
    }

    // Darkling Chomp hits twice; Nip hits for its rolled damage.
    {
        BattleContext bc = battle(MonsterEncounter::THREE_DARKLINGS);
        Monster &m = bc.monsters.arr[0];
        bc.player.block = 0;
        const int hpBefore = bc.player.curHp;
        m.moveHistory[0] = MMID::DARKLING_CHOMP;
        m.takeTurn(bc);
        drain(bc);
        if (hpBefore - bc.player.curHp != 16) return fail("Darkling Chomp did not hit 8 twice");
        m.moveHistory[0] = MMID::DARKLING_CHOMP;
        const auto intent = m.getMoveBaseDamage(bc);
        if (intent.damage != 8 || intent.attackCount != 2) return fail("Darkling Chomp intent is not 8x2");
    }
    {
        BattleContext bc = battle(MonsterEncounter::THREE_DARKLINGS, 2);
        Monster &m = bc.monsters.arr[0];
        bc.player.block = 0;
        const int hpBefore = bc.player.curHp;
        m.moveHistory[0] = MMID::DARKLING_NIP;
        m.takeTurn(bc);
        drain(bc);
        if (hpBefore - bc.player.curHp != m.miscInfo || m.miscInfo < 9 || m.miscInfo > 13) {
            return fail("A2 Darkling Nip did not hit for its rolled damage");
        }
    }

    // A18 Giant Head counts down one turn sooner.
    {
        BattleContext bc = battle(MonsterEncounter::GIANT_HEAD, 18);
        Monster &m = bc.monsters.arr[0];
        bc.turn = 2;
        m.moveHistory[0] = MMID::GIANT_HEAD_COUNT;
        m.moveHistory[1] = MMID::GIANT_HEAD_GLARE;
        int monsterData = 0;
        if (m.getMoveForRoll(bc, m.captureRollInputs(bc), monsterData, 10) != MMID::GIANT_HEAD_IT_IS_TIME) {
            return fail("A18 Giant Head did not start It Is Time on turn 4");
        }
        bc.turn = 3;
        m.moveHistory[0] = MMID::GIANT_HEAD_IT_IS_TIME;
        if (m.getMoveBaseDamage(bc).damage != 40) return fail("A18 Giant Head first It Is Time is not 40");
        bc.player.block = 0;
        const int hpBefore = bc.player.curHp;
        m.takeTurn(bc);
        drain(bc);
        if (hpBefore - bc.player.curHp != 40) return fail("A18 Giant Head first It Is Time did not hit for 40");
    }

    // Deca and Donu end each turn with a move roll (one aiRng draw).
    {
        BattleContext bc = battle(MonsterEncounter::DONU_AND_DECA);
        Monster &donu = bc.monsters.arr[1];
        donu.moveHistory[0] = MMID::DONU_CIRCLE_OF_POWER;
        const auto counterBefore = bc.aiRng.counter;
        donu.takeTurn(bc);
        drain(bc);
        if (bc.aiRng.counter != counterBefore + 1 || !donu.lastMove(MMID::DONU_BEAM)) {
            return fail("Donu did not roll at the end of its turn");
        }
    }
    {
        BattleContext bc = battle(MonsterEncounter::DONU_AND_DECA);
        Monster &deca = bc.monsters.arr[0];
        for (const MMID move : {MMID::DECA_BEAM, MMID::DECA_SQUARE_OF_PROTECTION}) {
            deca.moveHistory[0] = move;
            const auto counterBefore = bc.aiRng.counter;
            deca.takeTurn(bc);
            drain(bc);
            if (bc.aiRng.counter != counterBefore + 1) return fail("Deca did not roll at the end of its turn");
        }
    }

    // Awakened One A9 HP is exactly 320; Jaw Worm Horde Bellow block is 6 at A0.
    if (monsterHpRange[static_cast<int>(MonsterId::AWAKENED_ONE)][1][0] != 320) {
        return fail("Awakened One A9 HP range differs from the game");
    }
    {
        BattleContext bc = battle(MonsterEncounter::JAW_WORM_HORDE);
        if (bc.monsters.arr[0].block != 6) return fail("Jaw Worm Horde block is not 6 at A0");
    }

    // Live problem 56 (seed 111200445, A20): Donu died during the player's
    // turn; Deca's Square of Protection then gave only Deca block and Plated
    // Armor (game: Donu block 0, no powers). STS_DEAD_ALLY_BLOCK_FIX=0
    // restores the legacy block on the dead ally.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_DEAD_ALLY_BLOCK_FIX");
        else setenv("STS_DEAD_ALLY_BLOCK_FIX", "0", 1);
        BattleContext bc = battle(MonsterEncounter::DONU_AND_DECA, 20);
        Monster &deca = bc.monsters.arr[0], &donu = bc.monsters.arr[1];
        donu.curHp = 0;
        deca.block = 1;
        deca.moveHistory[0] = MMID::DECA_SQUARE_OF_PROTECTION;
        deca.takeTurn(bc);
        drain(bc);
        const int donuBlock = fix ? 0 : 16, donuPlated = fix ? 0 : 3;
        if (deca.block != 17 || deca.getStatus<MS::PLATED_ARMOR>() != 3
                || donu.block != donuBlock || donu.getStatus<MS::PLATED_ARMOR>() != donuPlated) {
            unsetenv("STS_DEAD_ALLY_BLOCK_FIX");
            return fail(fix ? "Deca's Square of Protection shielded a dead Donu"
                            : "STS_DEAD_ALLY_BLOCK_FIX=0 did not restore the legacy dead-Donu block");
        }
    }
    unsetenv("STS_DEAD_ALLY_BLOCK_FIX");

    // Donu's Circle of Power skips a dead Deca's Strength (ApplyPowerAction on
    // a dead target); STS_DEAD_ALLY_STRENGTH_FIX=0 restores the legacy buff.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");
        else setenv("STS_DEAD_ALLY_STRENGTH_FIX", "0", 1);
        BattleContext bc = battle(MonsterEncounter::DONU_AND_DECA, 20);
        Monster &deca = bc.monsters.arr[0], &donu = bc.monsters.arr[1];
        deca.curHp = 0;
        const int decaBefore = deca.getStatus<MS::STRENGTH>(), donuBefore = donu.getStatus<MS::STRENGTH>();
        donu.moveHistory[0] = MMID::DONU_CIRCLE_OF_POWER;
        donu.takeTurn(bc);
        drain(bc);
        if (donu.getStatus<MS::STRENGTH>() != donuBefore + 3
                || deca.getStatus<MS::STRENGTH>() != decaBefore + (fix ? 0 : 3)) {
            unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");
            return fail(fix ? "Donu's Circle of Power buffed a dead Deca"
                            : "STS_DEAD_ALLY_STRENGTH_FIX=0 did not restore the legacy dead-Deca Strength");
        }
    }
    unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");

    // ---- Act 4 (monsters.ending) ----

    // Spire Shield's Fortify skips a dead Spear (GainBlockAction on a dying
    // target); STS_DEAD_ALLY_BLOCK_FIX=0 restores the legacy block.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_DEAD_ALLY_BLOCK_FIX");
        else setenv("STS_DEAD_ALLY_BLOCK_FIX", "0", 1);
        BattleContext bc = battle(MonsterEncounter::SHIELD_AND_SPEAR, 20);
        Monster &shield = bc.monsters.arr[0], &spear = bc.monsters.arr[1];
        spear.curHp = 0;
        shield.block = 0;
        spear.block = 0;
        shield.moveHistory[0] = MMID::SPIRE_SHIELD_FORTIFY;
        shield.takeTurn(bc);
        drain(bc);
        if (shield.block != 30 || spear.block != (fix ? 0 : 30)) {
            unsetenv("STS_DEAD_ALLY_BLOCK_FIX");
            return fail(fix ? "Spire Shield's Fortify shielded a dead Spear"
                            : "STS_DEAD_ALLY_BLOCK_FIX=0 did not restore the legacy dead-Spear block");
        }
    }
    unsetenv("STS_DEAD_ALLY_BLOCK_FIX");

    // Spire Spear's Piercer skips a dead Shield's Strength (same shape).
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");
        else setenv("STS_DEAD_ALLY_STRENGTH_FIX", "0", 1);
        BattleContext bc = battle(MonsterEncounter::SHIELD_AND_SPEAR, 20);
        Monster &shield = bc.monsters.arr[0], &spear = bc.monsters.arr[1];
        shield.curHp = 0;
        const int shieldBefore = shield.getStatus<MS::STRENGTH>(), spearBefore = spear.getStatus<MS::STRENGTH>();
        spear.moveHistory[0] = MMID::SPIRE_SPEAR_PIERCER;
        spear.takeTurn(bc);
        drain(bc);
        if (spear.getStatus<MS::STRENGTH>() != spearBefore + 2
                || shield.getStatus<MS::STRENGTH>() != shieldBefore + (fix ? 0 : 2)) {
            unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");
            return fail(fix ? "Spire Spear's Piercer buffed a dead Shield"
                            : "STS_DEAD_ALLY_STRENGTH_FIX=0 did not restore the legacy dead-Shield Strength");
        }
    }
    unsetenv("STS_DEAD_ALLY_STRENGTH_FIX");

    // A18 Spire Spear Burn Strike puts two Burns on top of the draw pile.
    {
        BattleContext bc = battle(MonsterEncounter::SHIELD_AND_SPEAR, 18);
        Monster &spear = bc.monsters.arr[1];
        const int drawBefore = bc.cards.drawPile.size();
        spear.moveHistory[0] = MMID::SPIRE_SPEAR_BURN_STRIKE;
        spear.takeTurn(bc);
        drain(bc);
        const auto &pile = bc.cards.drawPile;
        if (pile.size() != drawBefore + 2 || pile[pile.size() - 1].getId() != CardId::BURN
                || pile[pile.size() - 2].getId() != CardId::BURN) {
            return fail("A18 Spire Spear did not put two Burns on top of the draw pile");
        }
    }

    std::cout << "monster_ai_java_parity PASS\n";
    return 0;
}

// Silver escape valuation (#370): a Smoke Bomb escape forfeits rewards.
int testSilverEscapePenalty() {
    auto fail = [&](const std::string &msg) {
        std::cout << "silver_escape_penalty FAIL: " << msg << '\n';
        return 1;
    };
    // Whether Silver's first action is to drink the Smoke Bomb in slot 0.
    auto flees = [](int hp, MonsterEncounter encounter, bool elite, double penalty, bool forfeitsRun = false) {
        GameContext gc(CharacterClass::IRONCLAD, 424242, 0);
        gc.curRoom = elite ? Room::ELITE : Room::MONSTER;
        gc.curHp = hp;
        gc.potions[0] = Potion::SMOKE_BOMB;
        gc.potionCount = 1;
        BattleContext bc;
        bc.init(gc, encounter);
        search::SilverSearchContext context;
        context.act = 1;
        context.eliteRewards = elite;
        context.escapeForfeitsRun = forfeitsRun;
        search::SilverSearcher searcher(silverSearchRoot(bc), context);
        searcher.evalWeights.escapePenalty = elite ? 0 : penalty;
        searcher.evalWeights.eliteEscapePenalty = elite ? penalty : 0;
        searcher.search(3000);
        const auto action = searcher.bestAction();
        return action.getActionType() == search::ActionType::POTION && action.getSourceIdx() == 0;
    };
    // Historical valuation: an escape counts as a full victory, so Silver
    // flees even an easy normal fight at full HP.
    if (!flees(80, MonsterEncounter::CULTIST, false, 0)) return fail("fixture: no escape without penalty");
    // Forfeited rewards make Silver fight easy normal fights with HP to spare.
    for (auto encounter : {MonsterEncounter::CULTIST, MonsterEncounter::JAW_WORM}) {
        for (int hp : {40, 80}) {
            if (flees(hp, encounter, false, 15)) return fail("penalty still flees an easy fight");
        }
    }
    // The HP cap keeps a low-HP emergency escape preferred.
    if (!flees(10, MonsterEncounter::GREMLIN_NOB, true, 40)) return fail("low-HP elite escape suppressed");
    if (!flees(10, MonsterEncounter::JAW_WORM, false, 15)) return fail("low-HP escape suppressed");
    // ADR-0041: escaping the act-3 burning elite without the Emerald Key rules out the Heart.
    if (flees(10, MonsterEncounter::GREMLIN_NOB, true, 40, true)) return fail("run-forfeiting escape still taken");
    if (flees(80, MonsterEncounter::CULTIST, false, 0, true)) return fail("run-forfeiting escape still taken at full HP");
    // The live wire path has no room: elite-trigger fights come from the encounter.
    auto wireElite = [](Room room, MonsterEncounter encounter) {
        GameContext gc(CharacterClass::IRONCLAD, 424242, 0);
        gc.curRoom = room;
        BattleContext bc;
        bc.init(gc, encounter);
        search::CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(bc);
        const auto wire = search::makeSilverBattleStateWire(bc, knowledge, search::makeSilverRunContext(gc), 0x5eedu);
        return search::searchContextFromWire(wire).eliteRewards;
    };
    if (!wireElite(Room::ELITE, MonsterEncounter::GREMLIN_NOB)) return fail("wire elite fight not elite");
    if (wireElite(Room::MONSTER, MonsterEncounter::JAW_WORM)) return fail("wire normal fight marked elite");
    if (!wireElite(Room::EVENT, MonsterEncounter::LAGAVULIN_EVENT)) return fail("wire Dead Adventurer fight not elite");
    std::cout << "silver_escape_penalty PASS\n";
    return 0;
}

// Research-only per-type potion weights (STS_SILVER_POTION_WEIGHTS).
int testSilverPotionWeights() {
    auto fail = [&](const std::string &msg) {
        std::cout << "silver_potion_weights FAIL: " << msg << '\n';
        return 1;
    };
    const auto w = search::parseSilverPotionWeights("ATTACK_POTION=20,SWIFT_POTION=0.5,*=7", 11);
    if (w[static_cast<int>(Potion::ATTACK_POTION)] != 20 || w[static_cast<int>(Potion::SWIFT_POTION)] != 0.5
        || w[static_cast<int>(Potion::BLOCK_POTION)] != 7) return fail("parse with default");
    if (search::parseSilverPotionWeights("FIRE_POTION=3", 11)[static_cast<int>(Potion::SMOKE_BOMB)] != 11)
        return fail("fallback weight");
    for (const char *bad : {"NOT_A_POTION=1", "FIRE_POTION", "FIRE_POTION=x", "FIRE_POTION=1x"}) {
        bool threw = false;
        try { search::parseSilverPotionWeights(bad, 11); } catch (const std::runtime_error &) { threw = true; }
        if (!threw) return fail(std::string("accepted ") + bad);
    }
    GameContext gc(CharacterClass::IRONCLAD, 424242, 0);
    gc.curRoom = Room::MONSTER;
    gc.potions[0] = Potion::ATTACK_POTION;
    gc.potions[1] = Potion::SWIFT_POTION;
    gc.potionCount = 2;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::SilverSearchContext context;
    context.act = 1;
    search::SilverSearcher searcher(silverSearchRoot(bc), context);
    BattleContext end = bc;
    end.outcome = Outcome::PLAYER_VICTORY;
    const double flat = searcher.scoreEndState(end);
    searcher.evalWeights.potionTypeWeightsOn = true;
    searcher.evalWeights.potionTypeWeights = w;
    const double typed = searcher.scoreEndState(end);
    if (std::abs((typed - flat) - (20.5 - 2 * 11)) > 1e-9) return fail("victory potion score not per type");
    std::cout << "silver_potion_weights PASS\n";
    return 0;
}

// Research-only concave-HP victory leaf (STS_SILVER_CONCAVE_HP_LEAF).
int testSilverConcaveHpLeaf() {
    auto fail = [&](const std::string &msg) {
        std::cout << "silver_concave_hp_leaf FAIL: " << msg << '\n';
        return 1;
    };
    GameContext gc(CharacterClass::IRONCLAD, 424243, 0);
    gc.curRoom = Room::MONSTER;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::SilverSearchContext context;
    context.act = 1;
    search::SilverSearcher searcher(silverSearchRoot(bc), context);
    const int m = bc.player.maxHp;
    auto score = [&](int hp, int potions) {
        BattleContext end = bc;
        end.outcome = Outcome::PLAYER_VICTORY;
        end.player.curHp = hp;
        for (int i = 0; i < potions; ++i) end.potions[i] = Potion::FIRE_POTION;
        end.potionCount = potions;
        return searcher.scoreEndState(end);
    };
    const double k = 2.7;
    auto u = [&](double hp) { return m / k * std::exp(0.75 * k) * (1 - std::exp(-k * hp / m)); };
    const int lo = m / 5, hi = m - 1;
    const double flatDiff = score(hi, 0) - score(lo, 0);
    if (std::abs(flatDiff - (hi - lo)) > 1e-9) return fail("off: HP not linear");
    searcher.evalWeights.concaveHpK = k;
    if (std::abs((score(hi, 0) - score(lo, 0)) - (u(hi) - u(lo))) > 1e-9) return fail("HP term is not u(h)");
    if (!(score(lo + 1, 0) - score(lo, 0) > 2.5 * (score(hi, 0) - score(hi - 1, 0))))
        return fail("low HP not worth more than high HP");
    for (const int hp : {lo, hi}) {
        const double pot = score(hp, 1) - score(hp, 0);
        const double want = 11 * std::exp(-0.5 * k * (static_cast<double>(hp) / m - 0.75));
        if (std::abs(pot - want) > 1e-9) return fail("potion term not scaled by sqrt(u')");
    }
    BattleContext loss = bc;
    loss.outcome = Outcome::PLAYER_LOSS;
    const double lossOn = searcher.scoreEndState(loss);
    searcher.evalWeights.concaveHpK = 0;
    if (lossOn != searcher.scoreEndState(loss)) return fail("loss branch changed");
    std::cout << "silver_concave_hp_leaf PASS\n";
    return 0;
}

// #544: a replayable zero-cost draw (two Finesse) must not trap Silver's
// rollout policy in a loop that never attacks. Before the fix every playout
// here ran ~142k actions to the engine's loop guard and scored that loss
// above a win through the per-draw bonus.
int testSilverRolloutZeroCostLoop() {
    auto fail = [&](const std::string &msg) {
        std::cout << "silver_rollout_zero_cost_loop FAIL: " << msg << '\n';
        return 1;
    };
    GameContext gc(CharacterClass::IRONCLAD, 111129000, 20);
    gc.curRoom = Room::MONSTER;
    gc.deck = {};
    for (int i = 0; i < 2; ++i) gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    for (int i = 0; i < 2; ++i) gc.deck.obtainRaw(Card(CardId::DEFEND_RED));
    for (int i = 0; i < 2; ++i) gc.deck.obtainRaw(Card(CardId::FINESSE));
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    search::SilverSearchContext context;
    context.act = 1;
    search::SilverSearcher searcher(silverSearchRoot(bc), context);
    const double value = searcher.rolloutValue(silverSearchRoot(bc));
    if (searcher.stats.rolloutPlayouts != 1) return fail("expected one playout");
    if (searcher.stats.rolloutActions > 2000)
        return fail("playout took " + std::to_string(searcher.stats.rolloutActions) + " actions");
    if (value < searcher.evalWeights.winBonus) return fail("playout did not win: value " + std::to_string(value));
    searcher.search(200);
    if (searcher.stats.rolloutActions > 200 * 2000) return fail("search playouts still loop");
    std::cout << "silver_rollout_zero_cost_loop PASS\n";
    return 0;
}

// Match and Keep: one click per action, pair resolution, and a fair
// fixed-pattern chooser that never reads unseen slots.
int testMatchAndKeep() {
    auto fail = [&](const std::string &msg) {
        std::cout << "match_and_keep FAIL: " << msg << '\n';
        return 1;
    };
    auto start = [](std::uint64_t seed) {
        GameContext gc(CharacterClass::IRONCLAD, seed, 0);
        gc.curRoom = Room::EVENT;
        gc.curEvent = Event::MATCH_AND_KEEP;
        gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
        gc.setupEvent();
        return gc;
    };
    using GC = GameContext;
    auto slotActions = [](const GameContext &gc) {
        return static_cast<int>(search::GameAction::getAllActionsInState(gc).size());
    };

    // Mechanics: the first click only turns a card face up.
    {
        auto gc = start(123456789);
        if (gc.info.toSelectCards.size() != 12 || gc.info.eventData != 5 || slotActions(gc) != 12) {
            return fail("setup is not 12 unseen slots with 5 attempts");
        }
        for (const auto &s : gc.info.toSelectCards) {
            if (s.deckIdx != GC::MATCH_AND_KEEP_UNSEEN) return fail("slot not unseen at setup");
        }
        const int deckSize = gc.deck.size();
        search::GameAction(0).execute(gc);
        if (gc.info.toSelectCards[0].deckIdx != GC::MATCH_AND_KEEP_FACE_UP || gc.info.eventData != 5
                || slotActions(gc) != 11 || search::GameAction(0).isValidAction(gc)) {
            return fail("first click did not only turn slot 0 face up");
        }
        int twin = -1, other = -1;
        for (int i = 1; i < 12; ++i) {
            if (gc.info.toSelectCards[i].card.id == gc.info.toSelectCards[0].card.id) twin = i;
            else if (other < 0) other = i;
        }
        GameContext mismatch = gc;
        search::GameAction(twin).execute(gc);
        if (gc.deck.size() != deckSize + 1 || gc.info.eventData != 4
                || gc.info.toSelectCards[0].deckIdx != GC::MATCH_AND_KEEP_MATCHED
                || gc.info.toSelectCards[twin].deckIdx != GC::MATCH_AND_KEEP_MATCHED
                || slotActions(gc) != 10) {
            return fail("matching pair was not added and removed");
        }
        search::GameAction(other).execute(mismatch);
        if (mismatch.deck.size() != deckSize || mismatch.info.eventData != 4
                || mismatch.info.toSelectCards[0].deckIdx != GC::MATCH_AND_KEEP_SEEN
                || mismatch.info.toSelectCards[other].deckIdx != GC::MATCH_AND_KEEP_SEEN) {
            return fail("mismatch did not leave both cards seen face down");
        }
    }

    // Five attempts end the event on the map.
    {
        auto gc = start(987654321);
        for (int click = 0; click < 10; ++click) {
            if (gc.screenState != ScreenState::EVENT_SCREEN) return fail("event ended early");
            search::GameAction(search::chooseMatchAndKeepSlot(gc, [](const Card &) { return false; })).execute(gc);
        }
        if (gc.screenState != ScreenState::MAP_SCREEN || !gc.info.toSelectCards.empty()) {
            return fail("event did not end after five attempts");
        }
    }

    // Fairness: permuting the hidden cards of unseen slots never changes a click.
    for (std::uint64_t seed : {11ULL, 22ULL, 33ULL, 44ULL}) {
        for (bool wantAll : {false, true}) {
            auto gc = start(seed);
            const auto want = [wantAll](const Card &) { return wantAll; };
            while (gc.screenState == ScreenState::EVENT_SCREEN) {
                auto shuffled = gc;
                std::vector<int> unseen;
                for (int i = 0; i < 12; ++i) {
                    if (shuffled.info.toSelectCards[i].deckIdx == GC::MATCH_AND_KEEP_UNSEEN) unseen.push_back(i);
                }
                for (std::size_t k = 1; k < unseen.size(); ++k) {
                    std::swap(shuffled.info.toSelectCards[unseen[0]].card, shuffled.info.toSelectCards[unseen[k]].card);
                }
                const int slot = search::chooseMatchAndKeepSlot(gc, want);
                if (search::chooseMatchAndKeepSlot(shuffled, want) != slot) {
                    return fail("chooser read a hidden card");
                }
                search::GameAction(slot).execute(gc);
            }
        }
    }

    // Declining: after the first attempt, an unwanted card is never matched.
    // Wanting: every pair seen before the last attempt is completed.
    for (std::uint64_t seed = 1; seed <= 40; ++seed) {
        auto gc = start(seed);
        search::GameAction(search::chooseMatchAndKeepSlot(gc, [](const Card &) { return false; })).execute(gc);
        search::GameAction(search::chooseMatchAndKeepSlot(gc, [](const Card &) { return false; })).execute(gc);
        const int afterFirst = gc.deck.size();
        while (gc.screenState == ScreenState::EVENT_SCREEN) {
            search::GameAction(search::chooseMatchAndKeepSlot(gc, [](const Card &) { return false; })).execute(gc);
        }
        if (gc.deck.size() != afterFirst) return fail("declining policy matched an unwanted card");

        auto greedy = start(seed);
        const int before = greedy.deck.size();
        while (greedy.screenState == ScreenState::EVENT_SCREEN) {
            search::GameAction(search::chooseMatchAndKeepSlot(greedy, [](const Card &) { return true; })).execute(greedy);
        }
        if (greedy.deck.size() < before + 1) return fail("wanting policy matched nothing in five attempts");
    }

    std::cout << "match_and_keep PASS\n";
    return 0;
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
    // Problem 46: Java DuVuDoll's counter is the master deck's CURSE-type card
    // count (Ascender's Bane included), set by onEquip and onMasterDeckChange;
    // atBattleStart grants that much Strength. STS_DU_VU_DOLL_COUNT_FIX=0
    // keeps the legacy data 0.
    for (const bool fix : {true, false}) {
        if (fix) unsetenv("STS_DU_VU_DOLL_COUNT_FIX");
        else setenv("STS_DU_VU_DOLL_COUNT_FIX", "0", 1);
        GameContext gc(CharacterClass::IRONCLAD, 464646464u, 20);
        gc.obtainRelic(RelicId::DU_VU_DOLL);
        const int equipped = gc.relics.getRelicValueRef(RelicId::DU_VU_DOLL);
        gc.deck.obtain(gc, Card(CardId::REGRET));
        gc.deck.obtain(gc, Card(CardId::INFLAME));
        const int withRegret = gc.relics.getRelicValueRef(RelicId::DU_VU_DOLL);
        int regretIdx = -1;
        for (int i = 0; i < gc.deck.size(); ++i)
            if (gc.deck.cards[i].getId() == CardId::REGRET) regretIdx = i;
        gc.deck.obtain(gc, Card(CardId::DOUBT));
        gc.deck.remove(gc, regretIdx);
        const int afterRemove = gc.relics.getRelicValueRef(RelicId::DU_VU_DOLL);
        gc.curRoom = Room::MONSTER;
        gc.screenState = ScreenState::BATTLE;
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        const int strength = bc.player.getStatus<PS::STRENGTH>();
        unsetenv("STS_DU_VU_DOLL_COUNT_FIX");
        const int expected[] = {1, 2, 2, 2};
        const int actual[] = {equipped, withRegret, afterRemove, strength};
        for (int i = 0; i < 4; ++i) {
            if (actual[i] != (fix ? expected[i] : 0)) {
                std::cerr << "fix=" << fix << " step " << i << " got " << actual[i] << '\n';
                return fail("Du-Vu Doll counter does not track the master-deck curse count");
            }
        }
    }
    // Issue #641: Java makes the reward RNG rolls even when no reward is
    // granted. A Smoke Bomb escape rolls gold (treasureRng), an elite relic
    // (relicRng, popped from its pool; Black Star adds a second) and a potion
    // (potionRng, potionChance) but no card reward; the reward-less Colosseum
    // slaver fight rolls a potion whether won or escaped.
    // STS_REWARDLESS_COMBAT_RNG_FIX=0 skips them (legacy).
    {
        struct RngState {
            int treasure, potion, relic, card, chance; std::size_t pools; ScreenState screen;
        };
        auto exitCombat = [](bool fix, Room room, MonsterEncounter encounter, bool smoke, bool blackStar) {
            if (fix) unsetenv("STS_REWARDLESS_COMBAT_RNG_FIX");
            else setenv("STS_REWARDLESS_COMBAT_RNG_FIX", "0", 1);
            GameContext gc(CharacterClass::IRONCLAD, 641641641u, 0);
            gc.curRoom = room;
            if (blackStar) gc.relics.add({RelicId::BLACK_STAR, 0});
            if (room == Room::EVENT) {
                gc.act = 2;
                gc.floorNum = 25;
                gc.curMapNodeY = 9;
                gc.curEvent = Event::COLOSSEUM;
                gc.setupEvent();
                gc.chooseEventOption(0);
            } else {
                gc.screenState = ScreenState::BATTLE;
                gc.regainControlAction = [](GameContext &g) { g.afterBattle(); };
            }
            BattleContext bc;
            bc.init(gc, encounter);
            if (smoke) {
                bc.potions[0] = Potion::SMOKE_BOMB;
                bc.potionCount = 1;
                search::Action(search::ActionType::POTION, 0).execute(bc);
            } else {
                bc.outcome = Outcome::PLAYER_VICTORY;
            }
            bc.exitBattle(gc);
            unsetenv("STS_REWARDLESS_COMBAT_RNG_FIX");
            return RngState{gc.treasureRng.counter, gc.potionRng.counter, gc.relicRng.counter,
                            gc.cardRng.counter, gc.potionChance,
                            gc.commonRelicPool.size() + gc.uncommonRelicPool.size() + gc.rareRelicPool.size(),
                            gc.screenState};
        };
        struct Case { Room room; MonsterEncounter encounter; bool smoke; bool blackStar; const char *name; };
        for (const Case c : {Case{Room::MONSTER, MonsterEncounter::CULTIST, true, false, "hallway escape"},
                             Case{Room::ELITE, MonsterEncounter::GREMLIN_NOB, true, false, "elite escape"},
                             Case{Room::ELITE, MonsterEncounter::GREMLIN_NOB, true, true, "elite escape with Black Star"},
                             Case{Room::EVENT, MonsterEncounter::COLOSSEUM_EVENT_SLAVERS, true, false, "slaver escape"},
                             Case{Room::EVENT, MonsterEncounter::COLOSSEUM_EVENT_SLAVERS, false, false, "slaver win"}}) {
            const RngState legacy = exitCombat(false, c.room, c.encounter, c.smoke, c.blackStar);
            const RngState fixed = exitCombat(true, c.room, c.encounter, c.smoke, c.blackStar);
            const bool elite = c.room == Room::ELITE;
            if (fixed.treasure - legacy.treasure != (c.room == Room::EVENT ? 0 : 1)
                    || fixed.potion - legacy.potion < 1
                    || std::abs(fixed.chance - legacy.chance) != 10
                    || (fixed.relic > legacy.relic) != elite
                    || fixed.relic - legacy.relic != (elite ? (c.blackStar ? 2 : 1) : 0)
                    || legacy.pools - fixed.pools != (elite ? (c.blackStar ? 2u : 1u) : 0u)
                    || fixed.card != legacy.card
                    || fixed.screen != legacy.screen) {
                std::cerr << c.name << '\n';
                return fail("reward-less combat end did not make exactly Java's reward RNG rolls");
            }
        }
    }
    // Colosseum's fight continuations bypass afterBattle(): a slaver escape
    // must still clear smokeBombUsed and reopen the event, and a Nob escape
    // must forfeit the Victory rewards and return to the map.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        gc.act = 2;
        gc.floorNum = 25;
        gc.curMapNodeY = 9;
        gc.curRoom = Room::EVENT;
        gc.curEvent = Event::COLOSSEUM;
        gc.setupEvent();
        auto escape = [&](MonsterEncounter encounter) {
            gc.chooseEventOption(encounter == MonsterEncounter::COLOSSEUM_EVENT_SLAVERS ? 0 : 1);
            if (gc.screenState != ScreenState::BATTLE || gc.info.encounter != encounter) return false;
            BattleContext bc;
            bc.init(gc, encounter);
            bc.potions[0] = Potion::SMOKE_BOMB;
            bc.potionCount = 1;
            const search::Action useSmoke(search::ActionType::POTION, 0);
            if (!useSmoke.isValidAction(bc)) return false;
            useSmoke.execute(bc);
            bc.exitBattle(gc);
            return !gc.smokeBombUsed && gc.outcome == GameOutcome::UNDECIDED;
        };
        if (!escape(MonsterEncounter::COLOSSEUM_EVENT_SLAVERS)
                || gc.screenState != ScreenState::EVENT_SCREEN || gc.info.eventData != 1) {
            return fail("Colosseum slaver Smoke Bomb escape left smokeBombUsed or skipped the event");
        }
        const int goldBefore = gc.gold;
        if (!escape(MonsterEncounter::COLOSSEUM_EVENT_NOBS)
                || gc.screenState != ScreenState::MAP_SCREEN || gc.gold != goldBefore) {
            return fail("Colosseum Nob Smoke Bomb escape left smokeBombUsed or granted rewards");
        }
    }
    // Dead Adventurer, Masked Bandits and the Mushrooms set their reward
    // screen as the fight continuation, bypassing afterBattle(): an escape
    // must forfeit those rewards, clear smokeBombUsed and return to the map.
    {
        struct Case { Event event; int act; int option; const char *name; };
        for (const Case c : {Case{Event::DEAD_ADVENTURER, 1, 0, "Dead Adventurer"},
                             Case{Event::MASKED_BANDITS, 2, 1, "Masked Bandits"},
                             Case{Event::HYPNOTIZING_COLORED_MUSHROOMS, 1, 0, "Mushrooms"}}) {
            bool fought = false;
            for (std::uint64_t seed = 123456789; seed < 123456789 + 64 && !fought; ++seed) {
                GameContext gc(CharacterClass::IRONCLAD, seed, 0);
                gc.act = c.act;
                gc.floorNum = c.act == 1 ? 8 : 25;
                gc.curMapNodeY = 7;
                gc.curRoom = Room::EVENT;
                gc.curEvent = c.event;
                gc.setupEvent();
                // Dead Adventurer may need several searches before the fight.
                for (int i = 0; i < 3 && gc.screenState == ScreenState::EVENT_SCREEN; ++i)
                    gc.chooseEventOption(c.option);
                if (gc.screenState != ScreenState::BATTLE) continue;
                fought = true;
                const int goldBefore = gc.gold;
                const auto relicsBefore = gc.relics.relics.size();
                BattleContext bc;
                bc.init(gc, gc.info.encounter);
                bc.potions[0] = Potion::SMOKE_BOMB;
                bc.potionCount = 1;
                const search::Action useSmoke(search::ActionType::POTION, 0);
                if (!useSmoke.isValidAction(bc)) return fail("event fight rejected Smoke Bomb");
                useSmoke.execute(bc);
                bc.exitBattle(gc);
                if (gc.smokeBombUsed || gc.outcome != GameOutcome::UNDECIDED
                        || gc.screenState != ScreenState::MAP_SCREEN || gc.gold != goldBefore
                        || gc.relics.relics.size() != relicsBefore) {
                    { std::cerr << c.name << '\n'; return fail("event Smoke Bomb escape granted rewards or kept smokeBombUsed"); }
                }
            }
            if (!fought) { std::cerr << c.name << '\n'; return fail("event Smoke Bomb test found no seed reaching the fight"); }
        }
    }
    // Face of Cleric (Java onVictory) gains exactly +1 max HP after every
    // won or escaped event fight, including those whose continuation
    // replaces afterBattle() (Colosseum, Dead Adventurer, Masked Bandits,
    // Mushrooms, Mind Bloom).
    {
        struct Case { Event event; int act; int option; const char *name; };
        for (const bool escapeFight : {false, true}) {
            for (const Case c : {Case{Event::COLOSSEUM, 2, 0, "Colosseum slavers"},
                                 Case{Event::COLOSSEUM, 2, 1, "Colosseum Nobs"},
                                 Case{Event::DEAD_ADVENTURER, 1, 0, "Dead Adventurer"},
                                 Case{Event::MASKED_BANDITS, 2, 1, "Masked Bandits"},
                                 Case{Event::HYPNOTIZING_COLORED_MUSHROOMS, 1, 0, "Mushrooms"},
                                 Case{Event::MINDBLOOM, 3, 0, "Mind Bloom"},
                                 Case{Event::MYSTERIOUS_SPHERE, 3, 0, "Mysterious Sphere"}}) {
                // Mind Bloom fights a boss, which blocks Smoke Bomb.
                if (escapeFight && c.event == Event::MINDBLOOM) continue;
                bool fought = false;
                for (std::uint64_t seed = 123456789; seed < 123456789 + 64 && !fought; ++seed) {
                    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
                    gc.act = c.act;
                    gc.floorNum = c.act == 1 ? 8 : (c.act == 2 ? 25 : 42);
                    gc.curMapNodeY = 9;
                    gc.curRoom = Room::EVENT;
                    gc.curEvent = c.event;
                    gc.setupEvent();
                    gc.relics.add({RelicId::FACE_OF_CLERIC, 0});
                    if (c.event == Event::COLOSSEUM && c.option == 1) {
                        // Win the slaver fight first to reach the Nob choice.
                        gc.chooseEventOption(0);
                        BattleContext slavers;
                        slavers.init(gc, gc.info.encounter);
                        slavers.outcome = Outcome::PLAYER_VICTORY;
                        slavers.exitBattle(gc);
                        if (gc.screenState != ScreenState::EVENT_SCREEN) return fail("Colosseum slaver win did not reopen the event");
                    }
                    for (int i = 0; i < 3 && gc.screenState == ScreenState::EVENT_SCREEN; ++i)
                        gc.chooseEventOption(c.option);
                    if (gc.screenState != ScreenState::BATTLE) continue;
                    fought = true;
                    BattleContext bc;
                    bc.init(gc, gc.info.encounter);
                    if (escapeFight) {
                        bc.potions[0] = Potion::SMOKE_BOMB;
                        bc.potionCount = 1;
                        const search::Action useSmoke(search::ActionType::POTION, 0);
                        if (!useSmoke.isValidAction(bc)) { std::cerr << c.name << '\n'; return fail("event fight rejected Smoke Bomb"); }
                        useSmoke.execute(bc);
                    } else {
                        bc.outcome = Outcome::PLAYER_VICTORY;
                    }
                    const int maxHpBefore = bc.player.maxHp;
                    bc.exitBattle(gc);
                    if (gc.maxHp != maxHpBefore + 1 || gc.outcome != GameOutcome::UNDECIDED) {
                        std::cerr << c.name << (escapeFight ? " escape" : " victory")
                                  << " maxHp " << maxHpBefore << " -> " << gc.maxHp << '\n';
                        return fail("Face of Cleric did not fire exactly once after an event fight");
                    }
                }
                if (!fought) { std::cerr << c.name << '\n'; return fail("Face of Cleric test found no seed reaching the fight"); }
            }
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

    // A new Ritual Dagger starts at 15 base damage (its misc), whether The
    // Nest or a direct obtain creates it, and a combat copy hits for 15.
    {
        GameContext gc(CharacterClass::IRONCLAD, 123456789, 0);
        gc.curRoom = Room::EVENT;
        gc.curEvent = Event::THE_NEST;
        gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
        gc.setupEvent();
        gc.chooseEventOption(1);
        const Card nestDagger = gc.deck.cards[gc.deck.size() - 1];
        if (nestDagger.getId() != CardId::RITUAL_DAGGER || nestDagger.misc != 15) {
            return fail("The Nest Ritual Dagger does not start at 15 damage");
        }
        gc.deck.obtain(gc, CardId::RITUAL_DAGGER);
        if (gc.deck.cards[gc.deck.size() - 1].misc != 15) {
            return fail("obtained Ritual Dagger does not start at 15 damage");
        }

        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) {
            bc.executeActions();
        }
        CardInstance dagger(nestDagger);
        dagger.uniqueId = 900;
        bc.cards.moveToHand(dagger);
        auto &cultist = bc.monsters.arr[0];
        cultist.block = 0;
        const int hpBefore = cultist.curHp;
        search::Action(search::ActionType::CARD, bc.cards.cardsInHand - 1, 0).execute(bc);
        if (hpBefore - cultist.curHp != 15) {
            return fail("new Ritual Dagger does not deal 15 damage");
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

// Violence scans the whole draw pile for attacks. The draw pile is unbounded,
// so the attack index list must not have the old 64-entry fixed capacity
// (#334 seed 13001491 stack overflow inside a native Silver rollout).
static std::string violenceDrawPileDigest(int attackCount, int skillCount) {
    GameContext gc(CharacterClass::IRONCLAD, 13001491, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.cards.cardsInHand = 0;
    bc.cards.drawPile.clear();
    std::int16_t uid = 1000;
    int attacksLeft = attackCount, skillsLeft = skillCount;
    while (attacksLeft + skillsLeft > 0) {
        // Interleave skills so attack indices are not contiguous.
        const bool attack = attacksLeft > 0 && (skillsLeft == 0 || uid % 3 != 2);
        --(attack ? attacksLeft : skillsLeft);
        CardInstance c(attack ? CardId::STRIKE_RED : CardId::DEFEND_RED);
        c.uniqueId = uid++;
        bc.cards.drawPile.concreteCards().push_back(c);
    }
    const int before = bc.cards.drawPile.size();
    const Action violence = Actions::ViolenceAction(3);
    violence(bc);
    std::ostringstream o;
    o << "hand=" << bc.cards.cardsInHand << ':';
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        if (bc.cards.hand[i].getType() != CardType::ATTACK) return "non-attack-in-hand";
        o << bc.cards.hand[i].uniqueId << ',';
    }
    // The remaining draw pile must be the original order minus the drawn cards.
    std::int16_t expectedUid = 1000;
    for (const auto &c : bc.cards.drawPile) {
        auto drawn = [&](std::int16_t id) {
            for (int i = 0; i < bc.cards.cardsInHand; ++i)
                if (bc.cards.hand[i].uniqueId == id) return true;
            return false;
        };
        while (drawn(expectedUid)) ++expectedUid;
        if (c.uniqueId != expectedUid++) return "draw-pile-order-changed";
    }
    o << ";draw=" << before << '>' << bc.cards.drawPile.size() << ";discard=" << bc.cards.discardPile.size()
      << ";card=" << bc.cardRandomRng.counter << ";shuffle=" << bc.shuffleRng.counter;
    return o.str();
}

static int testViolenceLargeDrawPile() {
    // Golden digests captured from the pre-fix fixed_list implementation (65
    // survived in the release layout); card choice and RNG use must not change.
    const std::pair<int, const char *> golden[] = {
        {40, "hand=3:1027,1056,1042,;draw=60>57;discard=0;card=39;shuffle=4"},
        {64, "hand=3:1002,1044,1024,;draw=74>71;discard=0;card=63;shuffle=4"},
        {65, "hand=3:1015,1006,1033,;draw=75>72;discard=0;card=64;shuffle=4"},
    };
    for (const auto &[attacks, expected] : golden) {
        const std::string d = violenceDrawPileDigest(attacks, attacks == 40 ? 20 : 10);
        if (d != expected) {
            std::cout << "violence_large_draw_pile: FAIL golden attacks=" << attacks << ' ' << d << '\n';
            return 1;
        }
    }
    for (const int attacks : {66, 70, 128, 200}) {
        const std::string d = violenceDrawPileDigest(attacks, 10);
        const std::string expected = "hand=3:";
        if (d.rfind(expected, 0) != 0) {
            std::cout << "violence_large_draw_pile: FAIL attacks=" << attacks << ' ' << d << '\n';
            return 1;
        }
        const auto drawPos = d.find(";draw=" + std::to_string(attacks + 10) + '>'
                                    + std::to_string(attacks + 7) + ';');
        if (drawPos == std::string::npos) {
            std::cout << "violence_large_draw_pile: FAIL draw count attacks=" << attacks << ' ' << d << '\n';
            return 1;
        }
    }
    std::cout << "violence_large_draw_pile: PASS\n";
    return 0;
}

// Bronze Orb Stasis picks one card of the highest rarity present from the draw
// pile (or the discard pile when the draw pile is empty). Like Violence, the
// candidate list must not have the old 64-entry fixed capacity.
static std::string stasisDigest(const std::vector<CardId> &pile, bool fromDiscard,
                                int *expectedPick = nullptr) {
    GameContext gc(CharacterClass::IRONCLAD, 13001491, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.cards.drawPile.clear();
    bc.cards.discardPile.clear();
    std::vector<CardInstance> cards;
    std::int16_t uid = 2000;
    for (const CardId id : pile) {
        CardInstance c(id);
        c.uniqueId = uid++;
        cards.push_back(c);
    }
    if (fromDiscard) {
        for (const auto &c : cards) bc.cards.discardPile.push_back(c);
    } else {
        bc.cards.drawPile.assignConcrete(cards);
    }
    if (expectedPick) {
        // Single-id target sets keep source order under the stable sort, so
        // the pick is the k-th target card for k drawn from a copied RNG.
        Random rng = bc.cardRandomRng;
        const CardRarity target = getCardRarity(pile[*expectedPick]);
        int targets = 0;
        for (const CardId id : pile) targets += getCardRarity(id) == target;
        int k = rng.random(targets - 1);
        for (int i = 0; i < static_cast<int>(pile.size()); ++i) {
            if (getCardRarity(pile[i]) == target && k-- == 0) { *expectedPick = i; break; }
        }
    }
    bc.monsters.arr[0].stasisAction(bc);
    const CardInstance taken = bc.cards.stasisCards[0];
    std::ostringstream o;
    o << "taken=" << taken.uniqueId << ':' << static_cast<int>(taken.id);
    // The remaining pile must be the original order minus the taken card.
    std::vector<std::int16_t> remaining;
    if (fromDiscard) for (const auto &c : bc.cards.discardPile) remaining.push_back(c.uniqueId);
    else for (const auto &c : bc.cards.drawPile) remaining.push_back(c.uniqueId);
    std::int16_t expectedUid = 2000;
    for (const auto id : remaining) {
        if (expectedUid == taken.uniqueId) ++expectedUid;
        if (id != expectedUid++) return "pile-order-changed";
    }
    o << ";left=" << remaining.size() << ";card=" << bc.cardRandomRng.counter;
    return o.str();
}

static int testStasisLargePile() {
    using C = CardId;
    std::vector<C> mixed;  // rares of several ids among uncommons/commons/basics
    const C rares[] = {C::BLUDGEON, C::IMPERVIOUS, C::OFFERING, C::DEMON_FORM, C::REAPER};
    const C uncommons[] = {C::CARNAGE, C::UPPERCUT, C::WHIRLWIND, C::SHOCKWAVE};
    const C commons[] = {C::CLEAVE, C::IRON_WAVE, C::ANGER, C::POMMEL_STRIKE};
    for (int i = 0; i < 40; ++i)
        mixed.push_back(i % 8 == 3 ? rares[i % 5] : i % 3 == 0 ? uncommons[i % 4]
                        : i % 3 == 1 ? commons[i % 4] : C::STRIKE_RED);
    std::vector<C> uncommonTop;  // no rares: uncommons of several ids
    for (int i = 0; i < 50; ++i) uncommonTop.push_back(i % 2 ? uncommons[i % 4] : commons[i % 4]);
    std::vector<C> common64;     // exactly the old capacity of commons
    for (int i = 0; i < 64; ++i) common64.push_back(commons[i % 4]);
    std::vector<C> basics(20, C::STRIKE_RED);  // no C/U/R: uniform random index
    std::vector<C> discardMix(uncommonTop.begin(), uncommonTop.begin() + 30);

    // Golden digests captured from the pre-fix fixed_list implementation.
    const std::tuple<const std::vector<C> *, bool, const char *> golden[] = {
        {&mixed, false, "taken=2003:107;left=39;card=1"},
        {&uncommonTop, false, "taken=2047:300;left=49;card=1"},
        {&common64, false, "taken=2013:198;left=63;card=1"},
        {&basics, false, "taken=2011:321;left=19;card=1"},
        {&discardMix, true, "taken=2017:349;left=29;card=1"},
    };
    bool goldenOk = true;
    for (const auto &[pile, discard, expected] : golden) {
        const std::string d = stasisDigest(*pile, discard);
        if (d != expected) {
            std::cout << "stasis_large_pile: FAIL golden " << d << '\n';
            goldenOk = false;
        }
    }
    if (!goldenOk) return 1;
    // More than 64 cards of the selected rarity: safe, and the pick matches
    // an independent computation of the same rule.
    for (const int targets : {65, 66, 100, 200}) {
        for (const bool discard : {false, true}) {
            std::vector<C> pile;  // `targets` rares with 10 commons interleaved
            int commonsLeft = 10;
            for (int i = 0; i < targets + 10; ++i) {
                const bool common = commonsLeft > 0 && i % 7 == 5;
                commonsLeft -= common;
                pile.push_back(common ? C::CLEAVE : C::DEMON_FORM);
            }
            int first = -1;
            for (int i = 0; i < static_cast<int>(pile.size()); ++i)
                if (pile[i] == C::DEMON_FORM) { first = i; break; }
            int pick = first;
            const std::string d = stasisDigest(pile, discard, &pick);
            const std::string want = "taken=" + std::to_string(2000 + pick) + ':'
                + std::to_string(static_cast<int>(C::DEMON_FORM)) + ";left="
                + std::to_string(pile.size() - 1) + ';';
            if (d.rfind(want, 0) != 0) {
                std::cout << "stasis_large_pile: FAIL targets=" << targets << " discard="
                          << discard << ' ' << d << " want " << want << '\n';
                return 1;
            }
        }
    }
    std::cout << "stasis_large_pile: PASS\n";
    return 0;
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
    // not leak into this check via STS_MULTISELECT_MODE. Canonicalization
    // (default on, ADR-0034) is checked by cardselect_canonical instead.
    setenv("STS_MULTISELECT_MODE", "all", 1);
    setenv("STS_MULTISELECT_CANONICAL", "0", 1);

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

    // Option 3: pay 75 gold, then choose two distinct public transform targets.
    const auto beforeTransform=gc.deck.cards;
    gc.chooseEventOption(3);
    check(gc.gold == 425, "option 3: expected gold 425, got " + std::to_string(gc.gold));
    check(gc.curHp == 80, "option 3: expected hp 80, got " + std::to_string(gc.curHp));
    check(gc.screenState == ScreenState::CARD_SELECT
            && gc.info.selectScreenType == CardSelectScreenType::TRANSFORM
            && gc.info.toSelectCount == 2 && gc.info.haveSelectedCards.empty(),
          "option 3: expected an unselected two-card transform grid");
    check(gc.deck.cards.size() == beforeTransform.size() && std::equal(gc.deck.cards.begin(),gc.deck.cards.end(),beforeTransform.begin()), "option 3: deck changed before target selection");
    if(gc.screenState == ScreenState::CARD_SELECT && gc.info.toSelectCards.size() >= 2) {
        const int firstTarget=gc.info.toSelectCards[0].deckIdx;
        gc.chooseSelectCardScreenOption(0);
        check(gc.screenState == ScreenState::CARD_SELECT && gc.info.haveSelectedCards.size() == 1,
              "option 3: first selection must leave one pick outstanding");
        check(gc.deck.cards.size() == beforeTransform.size() && std::equal(gc.deck.cards.begin(),gc.deck.cards.end(),beforeTransform.begin()), "option 3: deck changed before both targets were selected");
        check(gc.info.toSelectCards[0].deckIdx != firstTarget, "option 3: selected target remained available");
        gc.chooseSelectCardScreenOption(0);
        check(gc.screenState == ScreenState::MAP_SCREEN && gc.deck.cards.size() == beforeTransform.size(),
              "option 3: completed transforms must preserve deck size and return to map");
        check(gc.gold == 425 && gc.curHp == 80, "option 3: selection charged extra gold or HP");
    } else check(false, "option 3: insufficient selectable transform targets");

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

// #407: Java AbstractDungeon.populateFirstStrongEnemy re-rolls monsterRng
// until the draw is not in the act's generateExclusions() for the last weak
// encounter (STS1 V2.3.4 Exordium/TheCity/TheBeyond). The simulator must
// produce the same encounter and leave monsterRng at the same counter.
int testFirstStrongExclusions() {
    auto fail = [&](const std::string &msg) {
        std::cout << "first_strong_exclusions FAIL: " << msg << '\n';
        return 1;
    };
    typedef MonsterEncounter ME;
    struct Exclusion { ME lastWeak; ME excluded; };
    static const Exclusion javaTable[] = {
            {ME::SMALL_SLIMES, ME::LARGE_SLIME},
            {ME::SMALL_SLIMES, ME::LOTS_OF_SLIMES},
            {ME::TWO_LOUSE, ME::THREE_LOUSE},
            {ME::SPHERIC_GUARDIAN, ME::SENTRY_AND_SPHERE},
            {ME::THREE_BYRDS, ME::CHOSEN_AND_BYRDS},
            {ME::CHOSEN, ME::CHOSEN_AND_BYRDS},
            {ME::CHOSEN, ME::CULTIST_AND_CHOSEN},
            {ME::THREE_DARKLINGS, ME::THREE_DARKLINGS},
            {ME::ORB_WALKER, ME::ORB_WALKER},
            {ME::THREE_SHAPES, ME::FOUR_SHAPES},
    };
    auto excluded = [&](ME lastWeak, ME draw) {
        for (const auto &e : javaTable) {
            if (e.lastWeak == lastWeak && e.excluded == draw) return true;
        }
        return false;
    };
    auto javaRoll = [](float roll, const float *weights, int count) {
        float cur = 0.0f;
        for (int i = 0; i < count; ++i) {
            cur += weights[i];
            if (roll < cur) return i;
        }
        return count - 1;
    };

    int rerolls = 0;
    for (int act = 1; act <= 3; ++act) {
        const ME *strong = MonsterEncounterPool::strongEnemies[act-1];
        const float *weights = MonsterEncounterPool::strongWeights[act-1];
        const int count = MonsterEncounterPool::strongCount[act-1];
        for (int w = 0; w < MonsterEncounterPool::weakCount[act-1]; ++w) {
            const ME lastWeak = MonsterEncounterPool::weakEnemies[act-1][w];
            for (std::uint64_t s = 1; s <= 400; ++s) {
                GameContext gc(CharacterClass::IRONCLAD, 0x407u, 0);
                gc.act = act;
                gc.monsterList.clear();
                gc.monsterList.push_back(lastWeak);
                gc.monsterRng = Random(s * 7919u + act * 31u + w);
                Random ref = gc.monsterRng;

                ME expected;
                int draws = 0;
                do {
                    expected = strong[javaRoll(ref.random(), weights, count)];
                    ++draws;
                } while (excluded(lastWeak, expected));
                rerolls += draws - 1;

                gc.populateFirstStrongEnemy(strong, weights, count);
                if (gc.monsterList.size() != 2 || gc.monsterList.back() != expected) {
                    return fail(std::string("act ") + std::to_string(act) + " after "
                        + monsterEncounterStrings[static_cast<int>(lastWeak)] + ": got "
                        + monsterEncounterStrings[static_cast<int>(gc.monsterList.back())] + ", Java "
                        + monsterEncounterStrings[static_cast<int>(expected)]);
                }
                if (gc.monsterRng.counter != ref.counter) {
                    return fail(std::string("monsterRng counter diverged in act ") + std::to_string(act)
                        + " after " + monsterEncounterStrings[static_cast<int>(lastWeak)]);
                }
            }
        }
    }
    if (rerolls == 0) {
        return fail("no exclusion re-roll exercised");
    }
    std::cout << "first_strong_exclusions PASS (" << rerolls << " re-rolls)\n";
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
    } else if (command == "first_strong_exclusions") {
        return testFirstStrongExclusions();
    } else if (command == "simulator_correctness_pr9_19") {
        return testSimulatorCorrectnessPr9To19();
    } else if (command == "silver_escape_penalty") {
        return testSilverEscapePenalty();
    } else if (command == "silver_potion_weights") {
        return testSilverPotionWeights();
    } else if (command == "silver_concave_hp_leaf") {
        return testSilverConcaveHpLeaf();
    } else if (command == "silver_rollout_zero_cost_loop") {
        return testSilverRolloutZeroCostLoop();
    } else if (command == "match_and_keep") {
        return testMatchAndKeep();
    } else if (command == "simulator_relic_fidelity") {
        return testSimulatorRelicFidelity();
    } else if (command == "ironclad_card_java_parity") {
        return testIroncladCardJavaParity();
    } else if (command == "monster_ai_java_parity") {
        return testMonsterAiJavaParity();
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
    } else if (command == "silver_rollout_limit") {
        return testSilverRolloutLimit();
    } else if (command == "silver_searcher") {
        return testSilverSearcher();
    } else if (command == "persistent_latent_damage") {
        return testPersistentLatentDamage();
    } else if (command == "silver_wire_state") {
        return testSilverWireState();
    } else if (command == "silver_profile") {
        const std::int64_t sims = argc > 2 ? std::stoll(argv[2]) : 2000;
        const int stride = argc > 3 ? std::max(1, std::stoi(argv[3])) : 1;
        return silverProfile(sims, stride);
    } else if (command == "violence_large_draw_pile") {
        return testViolenceLargeDrawPile();
    } else if (command == "stasis_large_pile") {
        return testStasisLargePile();
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
