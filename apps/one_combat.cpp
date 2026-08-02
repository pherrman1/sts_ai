// one_combat.cpp
//
// "An agent plays one combat" for sts_lightspeed, with two policies:
//   * random    -- uniformly random legal action (baseline)
//   * mcts      -- wraps the built-in BattleScumSearcher2 (Monte Carlo tree search)
// plus a benchmark harness that plays N seeds with each and reports win rate
// and HP retained.
//
// Usage:
//   one_combat mcts   [sims] [seed]     # one verbose combat, MCTS policy
//   one_combat random [seed]            # one verbose combat, random policy
//   one_combat bench  [sims] [nSeeds]   # MCTS(sims) vs random over nSeeds
//
// NOTE ON THE SEARCHER: BattleScumSearcher2 is a *known-RNG* solver -- its
// rollouts see the same upcoming draws the real combat will get, so it plays
// with hidden-information it wouldn't have in a live game. That makes it a
// strong baseline / upper bound, not a fair-play agent. (Fair search over
// unknown RNG is a "planned feature" per the repo README.) It also hardcodes
// evaluateEndState internally, so the EvalFnc ctor arg is currently ignored.

#include <algorithm>
#include <chrono>
#include <functional>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <iostream>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <tuple>
#include <vector>

#include "game/GameContext.h"
#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatPVNet.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/GameAction.h"
#include "sim/search/ExpertKnowledge.h"
#include "game/Map.h"
#include "ooc_checkpoint_net.h"
#include "ooc_strategic_net.h"

#ifdef _OPENMP
#include <omp.h>
#endif

#ifndef _WIN32
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#endif
#include <atomic>
#include <set>
#include <unordered_map>

// ---------------------------------------------------------------------------
// Live progress line for long parallel benches. Threads call tick() as each run
// finishes; it prints an in-place (\r) status to stderr -- completed/total,
// running win%/floor/HP, elapsed + ETA -- throttled to ~4 Hz. Only draws when
// stderr is a TTY, so redirected A/B logs stay clean. Call done() at the end.
struct BenchProgress {
    int total; const char *label;
    std::atomic<int> n{0}, wins{0};
    std::atomic<long long> floor{0}, hp{0};
    std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
    std::atomic<double> lastDraw{-1.0};
    bool tty = isatty(fileno(stderr));
    BenchProgress(int total_, const char *label_) : total(total_), label(label_) {}
    void tick(bool won, int fl, int h) {
        int d = ++n; wins += won; floor += fl; hp += h;
        if (!tty) return;
        double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        double last = lastDraw.load();
        if (d != total && (el - last) < 0.25) return;         // throttle
        if (!lastDraw.compare_exchange_strong(last, el)) return;
        double eta = d ? el / d * (total - d) : 0;
        std::fprintf(stderr, "\r  %s [%d/%d] %.0f%%  win%%=%.1f floor=%.1f hp=%.1f  %.0fs eta %.0fs      ",
                     label, d, total, 100.0 * d / total,
                     100.0 * wins / d, (double)floor / d, (double)hp / d, el, eta);
        std::fflush(stderr);
    }
    void done() { if (tty) std::fprintf(stderr, "\r\033[K"); }  // clear the line
};

static int numThreads() {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

using namespace sts;

using Policy = std::function<search::Action(const BattleContext &)>;

static MonsterEncounter g_encounter = MonsterEncounter::JAW_WORM;

// ---------------------------------------------------------------------------
// Enumerate legal actions in the current player-choice state
// (mirrors BattleScumSearcher2::enumerateActionsForNode; potions omitted).
// ---------------------------------------------------------------------------
static std::vector<search::Action> legalActions(const BattleContext &bc) {
    using search::Action;
    using search::ActionType;
    std::vector<Action> actions;

    if (bc.inputState == InputState::PLAYER_NORMAL) {
        if (bc.isCardPlayAllowed()) {
            for (int h = 0; h < bc.cards.cardsInHand; ++h) {
                const auto &c = bc.cards.hand[h];
                if (!c.canUseOnAnyTarget(bc)) continue;
                if (c.requiresTarget()) {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            actions.push_back(Action(ActionType::CARD, h, t));
                } else {
                    actions.push_back(Action(ActionType::CARD, h));
                }
            }
        }
        actions.push_back(Action(ActionType::END_TURN));
    } else if (bc.inputState == InputState::CARD_SELECT) {
        actions = Action::enumerateCardSelectActions(bc);
    }
    return actions;
}

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------
static search::Action randomPolicy(const BattleContext &bc) {
    static thread_local std::mt19937 rng(0xC0FFEE);
    auto actions = legalActions(bc);
    if (actions.empty()) return search::Action(search::ActionType::END_TURN);
    std::uniform_int_distribution<int> dist(0, (int)actions.size() - 1);
    return actions[dist(rng)];
}

static Policy makeMctsPolicy(int sims) {
    return [sims](const BattleContext &bc) -> search::Action {
        search::BattleScumSearcher2 searcher(bc);
        searcher.search(sims);
        if (!searcher.bestActionSequence.empty())
            return searcher.bestActionSequence.front();
        return randomPolicy(bc); // fallback (shouldn't trigger in a live state)
    };
}

// ---------------------------------------------------------------------------
// Play a single combat to completion.
// ---------------------------------------------------------------------------
struct Result { bool won; int hpStart, hpEnd, maxHp, turns; };

static Result runCombat(std::uint64_t seed, const Policy &policy, bool verbose) {
    GameContext gc(CharacterClass::IRONCLAD, seed, /*ascension=*/0);
    BattleContext bc;
    bc.init(gc, g_encounter);

    const int hpStart = bc.player.curHp;
    int step = 0;
    // Terminate on a decided outcome (isBattleOver lags a step behind).
    while (bc.outcome == Outcome::UNDECIDED) {
        search::Action a = policy(bc);
        if (verbose) {
            std::cout << "step " << step++ << "  hp=" << bc.player.curHp
                      << "  hand=" << bc.cards.cardsInHand << "  -> ";
            a.printDesc(std::cout, bc) << "\n";
        }
        a.execute(bc);
    }
    return { bc.outcome == Outcome::PLAYER_VICTORY,
             hpStart, bc.player.curHp, bc.player.maxHp, bc.turn };
}

// ---------------------------------------------------------------------------
// Benchmark: N seeds, both policies, aggregate.
// ---------------------------------------------------------------------------
static void benchmark(int sims, int nSeeds) {
    struct Agg { int wins = 0; long long hpRetained = 0; long long turns = 0; double ms = 0; };
    Agg r, m;
    Policy randp = &randomPolicy;
    Policy mctsp = makeMctsPolicy(sims);

    std::cout << "encounter: JawWorm   seeds: 0.." << nSeeds - 1
              << "   mcts sims/decision: " << sims << "\n\n";

    for (std::uint64_t seed = 0; seed < (std::uint64_t)nSeeds; ++seed) {
        auto t0 = std::chrono::steady_clock::now();
        Result rr = runCombat(seed, randp, false);
        auto t1 = std::chrono::steady_clock::now();
        Result mr = runCombat(seed, mctsp, false);
        auto t2 = std::chrono::steady_clock::now();

        r.wins += rr.won; r.hpRetained += rr.hpEnd; r.turns += rr.turns;
        r.ms += std::chrono::duration<double, std::milli>(t1 - t0).count();
        m.wins += mr.won; m.hpRetained += mr.hpEnd; m.turns += mr.turns;
        m.ms += std::chrono::duration<double, std::milli>(t2 - t1).count();
    }

    auto row = [&](const char *name, const Agg &a) {
        std::printf("%-8s  win%%=%5.1f   avg_hp_end=%5.1f   avg_turns=%4.1f   avg_ms=%7.2f\n",
                    name, 100.0 * a.wins / nSeeds,
                    (double)a.hpRetained / nSeeds,
                    (double)a.turns / nSeeds,
                    a.ms / nSeeds);
    };
    row("random", r);
    row("mcts", m);
}

// ---------------------------------------------------------------------------
// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via its out-of-combat policy).
// ---------------------------------------------------------------------------
struct RunResult { bool won; int floor; int act; int hpEnd, maxHp; int fightsLost; double sec; int deathCombat = -1; int deathEncounter = -1; };

static RunResult runFullRun(std::uint64_t seed, int sims, int ascension, bool verbose) {
    GameContext gc(CharacterClass::IRONCLAD, seed, ascension);

    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;    // MCTS sims per in-combat decision
    agent.printLogs = verbose;           // dump GameContext at each out-of-combat step
    agent.rng = std::default_random_engine(seed); // reproducible out-of-combat choices

    auto t0 = std::chrono::steady_clock::now();
    agent.playout(gc);                   // runs until gc.outcome is decided
    auto t1 = std::chrono::steady_clock::now();

    return { gc.outcome == GameOutcome::PLAYER_VICTORY,
             gc.floorNum, gc.act, gc.curHp, gc.maxHp,
             std::chrono::duration<double>(t1 - t0).count() };
}

static void runBenchmark(int sims, int nSeeds, int ascension) {
    std::cout << "whole-run benchmark   seeds: 0.." << nSeeds - 1
              << "   ascension: " << ascension
              << "   mcts sims/decision: " << sims
              << "   threads: " << numThreads() << "\n\n";

    int wins = 0;
    long long floorSum = 0, hpSum = 0;
    double secSum = 0;
    #pragma omp parallel for reduction(+:wins,floorSum,hpSum,secSum) schedule(dynamic)
    for (int seed = 0; seed < nSeeds; ++seed) {
        RunResult r = runFullRun((std::uint64_t)seed, sims, ascension, false);
        wins += r.won; floorSum += r.floor; hpSum += r.hpEnd; secSum += r.sec;
        std::printf("seed %2d  %-4s  floor %2d (act %d)  hp %3d/%-3d  %6.2fs\n",
                    seed, r.won ? "WIN" : "DEAD",
                    r.floor, r.act, r.hpEnd, r.maxHp, r.sec);
    }
    std::printf("\nwin%%=%.1f   avg_floor=%.1f   avg_hp_end=%.1f   avg_sec/run=%.2f\n",
                100.0 * wins / nSeeds,
                (double)floorSum / nSeeds,
                (double)hpSum / nSeeds,
                secSum / nSeeds);
}

// ---------------------------------------------------------------------------
// LOOKAHEAD CARD-REWARD POLICY: for each choice (each card + skip), copy the
// run, apply the choice, play the next N fights with a cheap agent, and keep
// the choice that leaves us best off. Common Random Numbers come for free: the
// copied GameContext carries all game RNG streams, so the only difference
// between branches is the deck. (Like the combat searcher, this peeks at the
// run's fixed future RNG.)
// ---------------------------------------------------------------------------
static double scoreLookaheadState(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -1e6 + gc.floorNum;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return  1e6 + gc.curHp;
    return gc.curHp * 100.0 + gc.floorNum;   // survived the N fights: HP is the discriminator
}

// Bounded, regression-friendly score (HP scale) for causal labels -- unlike
// scoreLookaheadState's +/-1e6 outcome bonuses which would swamp any regression.
static double labelScore(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -100.0;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return gc.maxHp + 200.0;
    return gc.curHp;   // survived the N fights: remaining HP is the signal
}

static double rolloutChoice(const GameContext &base, int rIdx, int cardIdx,
                            int N, int innerSims, std::uint64_t seed, bool useLabelScore = false) {
    GameContext gc = base;                              // shares seeded RNG streams (CRN)
    gc.map = std::make_shared<Map>(*base.map);          // isolate map from the real run
    search::ScumSearchAgent2 inner;
    inner.simulationCountBase = innerSims;
    inner.rng = std::default_random_engine(seed);

    search::GameAction(search::GameAction::RewardsActionType::CARD, rIdx, cardIdx).execute(gc);

    int fights = 0;
    while (gc.outcome == GameOutcome::UNDECIDED && fights < N) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            inner.playoutBattle(bc);
            bc.exitBattle(gc);
            ++fights;
        } else {
            inner.stepOutOfCombatPolicy(gc);
        }
    }
    return useLabelScore ? labelScore(gc) : scoreLookaheadState(gc);
}

static void lookaheadCardPolicy(GameContext &gc, int N, int innerSims, int futures) {
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();

        double bestScore = -1e18;
        int bestIdx = 5;                         // 5 == skip
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = (cand < nCards) ? cand : 5;
            double acc = 0;
            for (int f = 0; f < futures; ++f) {
                std::uint64_t seed = gc.seed ^ (0x9e3779b97f4a7c15ULL * (f + 1));
                acc += rolloutChoice(gc, rIdx, cardIdx, N, innerSims, seed);
            }
            const double score = acc / futures;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        search::GameAction(search::GameAction::RewardsActionType::CARD, rIdx, bestIdx).execute(gc);
    }
}

// Whole run where the card-reward decision is either the weighted table or lookahead.
static RunResult runFullRunDraft(std::uint64_t seed, int outerSims, bool lookahead,
                                 int N, int innerSims, int futures, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;         // mirror stepRewardsPolicy ordering
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (lookahead)             lookaheadCardPolicy(gc, N, innerSims, futures);
            else                            agent.weightedCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void draftBench(int outerSims, int nSeeds, int N, int innerSims, int asc) {
    std::cout << "draft A/B   seeds 0.." << nSeeds - 1 << "   outerSims: " << outerSims
              << "   lookahead(N=" << N << ", innerSims=" << innerSims << ", CRN)"
              << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool lookahead = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunDraft((std::uint64_t)s, outerSims, lookahead, N, innerSims, 1, asc);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    lookahead ? "lookahead" : "weighted-table",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// GREEDY CARD-REWARD POLICY: a deterministic alternative to the built-in
// weightedCardRewardPolicy (which roulette-wheel samples over the weights and
// skips probabilistically). Here we take the argmax card and skip only when the
// best card isn't better than our current deck by a tunable ratio -- so the
// deck's average quality improves monotonically and stays leaner.
// ---------------------------------------------------------------------------
static double avgDeckObtain(const GameContext &gc) {
    long sum = 0;
    for (const auto &c : gc.deck.cards) {
        sum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    return gc.deck.size() > 0 ? (double)sum / gc.deck.size() : 0.0;
}

static void greedyCardRewardPolicy(GameContext &gc, double skipRatio) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();

        int bestIdx = 0, bestRaw = -1;
        double bestW = -1.0;
        for (int i = 0; i < n; ++i) {
            const auto &c = r.cardRewards[rIdx][i];
            const int raw = search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
            double w = std::pow((double)raw, 1.2);                 // same shaping as the baseline
            if (gc.act == 1 && c.getType() == CardType::ATTACK) {  // act-1 attack bias
                w *= 1.4;
            }
            if (w > bestW) { bestW = w; bestIdx = i; bestRaw = raw; }
        }

        // Take the best card unless it's not meaningfully better than our average
        // deck card (skipRatio=0 => never skip; higher => pickier / leaner deck).
        const bool skip = (double)bestRaw < skipRatio * avgDeckObtain(gc);
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// ---------------------------------------------------------------------------
// STATE-AWARE CARD VALUE FUNCTION: score a candidate card given the full run
// state (deck composition, relics, HP, act, ascension, upcoming fights). This
// generalises the flat getObtainWeight table -- picking among 3 cards is then
// just argmax(value), and "skip" is value-vs-a-state-dependent-bar.
// ---------------------------------------------------------------------------

// Rows until the nearest reachable ELITE from the current map position (99 if none
// remain on any reachable path). Used to gauge how soon a hard fight arrives.
static int rowsToNextElite(const GameContext &gc) {
    const Map &map = *gc.map;
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return 99;
        const MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        bool eliteHere = false;
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::ELITE) eliteHere = true;
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
        }
        if (eliteHere) return y - base;
        reach = nxt;
    }
    return 99;
}

// Forward-map features: ONE reachability sweep from the current node giving, for the
// remaining map, the min rows-to-next {elite,rest,shop,boss} and the count of reachable
// rooms of each type ahead. The map is deterministic/known, so this is free information
// the value model should have (it previously saw only pv* history + the next few fights).
struct FwdMap {
    int dElite = 99, dRest = 99, dShop = 99, dBoss = 0;
    int cElite = 0, cRest = 0, cShop = 0, cEvent = 0, cMonster = 0, cTreasure = 0;
};
static FwdMap forwardMapFeatures(const GameContext &gc) {
    FwdMap fm;
    fm.dBoss = 14 - std::max(gc.curMapNodeY, 0);
    if (gc.map == nullptr) return fm;
    const Map &map = *gc.map;
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return fm;
        const MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const MapNode &n = map.getNode(x, y);
            const int d = y - base;
            switch (n.room) {
                case Room::ELITE:    ++fm.cElite;    fm.dElite = std::min(fm.dElite, d); break;
                case Room::REST:     ++fm.cRest;     fm.dRest  = std::min(fm.dRest,  d); break;
                case Room::SHOP:     ++fm.cShop;     fm.dShop  = std::min(fm.dShop,  d); break;
                case Room::EVENT:    ++fm.cEvent;    break;
                case Room::MONSTER:  ++fm.cMonster;  break;
                case Room::TREASURE: ++fm.cTreasure; break;
                default: break;
            }
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
        }
        reach = nxt;
    }
    return fm;
}

static double evalCardValue(const GameContext &gc, const Card &c) {
    const CardType t = c.getType();
    if (t == CardType::CURSE || t == CardType::STATUS) return -1e9;   // never draft these

    double v = (double)search::Expert::getObtainWeight(c.getId(), c.isUpgraded());  // base prior

    const int act = gc.act;
    const int asc = gc.ascension;
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;

    // deck composition (ignore curses/status)
    int nAtk = 0, nSkill = 0, nPow = 0, nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt == CardType::CURSE || dt == CardType::STATUS) continue;
        ++nReal;
        if (dt == CardType::ATTACK) ++nAtk;
        else if (dt == CardType::SKILL) ++nSkill;
        else if (dt == CardType::POWER) ++nPow;
    }
    const double atkFrac = nReal > 0 ? (double)nAtk / nReal : 0.5;

    // (1) curve: aim ~48% attacks; reward the under-represented role.
    const double targetAtk = 0.48;
    if (t == CardType::ATTACK)     v += 25.0 * (targetAtk - atkFrac);
    else if (t == CardType::SKILL) v += 25.0 * (atkFrac - targetAtk);

    // (2) scaling / win-condition: powers scale and you need one by act 2-3;
    //     diminishing once the deck already has a couple.
    if (t == CardType::POWER) {
        v += 8.0 * act;
        if (nPow >= 3) v -= 10.0 * (nPow - 2);
    }

    // (3) raw impact (proxy: base damage of attacks).
    v += 0.4 * c.getBaseDamage();

    // (4) defensive lean when hurt or at high ascension.
    if ((hpFrac < 0.5 || asc >= 15) && t == CardType::SKILL) v += 8.0;

    // (5) upcoming-fight pressure: value power spikes / big hits before a wall.
    const int d = std::min(rowsToNextElite(gc), 15 - gc.curMapNodeY);
    if (d <= 2) {
        if (t == CardType::POWER) v += 6.0;
        v += 0.2 * c.getBaseDamage();
    }
    return v;
}

// Value bar below which we skip: rises with deck size and ascension (avoid
// diluting a big / high-ascension deck), and drops in act 1 (you need cards).
static double evalSkipBar(const GameContext &gc) {
    int nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt != CardType::CURSE && dt != CardType::STATUS) ++nReal;
    }
    double bar = 8.0 + 0.7 * nReal + 1.0 * gc.ascension;
    if (gc.act == 1) bar *= 0.5;
    return bar;
}

static void evalCardRewardPolicy(GameContext &gc, bool allowSkip = true) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestV = -1e18;
        for (int i = 0; i < n; ++i) {
            const double val = evalCardValue(gc, r.cardRewards[rIdx][i]);
            if (val > bestV) { bestV = val; bestIdx = i; }
        }
        const bool skip = allowSkip && (bestV < evalSkipBar(gc));
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// ---------------------------------------------------------------------------
// CAUSAL PER-CARD ADVANTAGE TABLE: offline-learned mean CRN take-vs-skip HP
// advantage per card id (build/card_adv_table.txt, from causalgen + shrinkage).
// Pure tempo signal: loves immediate damage/AoE, undervalues synergy/engine
// cards (it cannot see deck context). Used standalone (policy 5) and fused into
// the expert eval (policy 4).
// ---------------------------------------------------------------------------
static double g_cardAdv[512];
static bool   g_cardAdvSet[512] = {false};
static double g_cardAdvMean = 0.0;
static bool   g_cardAdvLoaded = false;
static double g_tableAlpha = 1.0;      // fusion weight of centered advantage

static void loadCardAdvTable(const std::string &path) {
    std::ifstream f(path);
    if (!f) { std::cerr << "WARNING: could not open card adv table: " << path << "\n"; return; }
    std::string line; double sum = 0; int cnt = 0;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream is(line);
        int id; double val;
        if (!(is >> id >> val)) continue;
        if (id >= 0 && id < 512) { g_cardAdv[id] = val; g_cardAdvSet[id] = true; sum += val; ++cnt; }
    }
    g_cardAdvMean = cnt ? sum / cnt : 0.0;
    g_cardAdvLoaded = true;
    std::cout << "loaded card-adv table (" << cnt << " cards, mean "
              << g_cardAdvMean << ", alpha " << g_tableAlpha << ") from " << path << "\n";
}

// raw learned advantage for a card (falls back to table mean if unseen)
static double cardAdvRaw(const Card &c) {
    int id = (int)c.getId();
    return (id >= 0 && id < 512 && g_cardAdvSet[id]) ? g_cardAdv[id] : g_cardAdvMean;
}
// centered advantage: unseen cards contribute ~0 (treated as average)
static double cardAdvCentered(const Card &c) { return cardAdvRaw(c) - g_cardAdvMean; }

// policy 4: expert eval + alpha * centered causal advantage
static void fusedCardRewardPolicy(GameContext &gc, bool allowSkip = true) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestV = -1e18;
        for (int i = 0; i < n; ++i) {
            const Card &c = r.cardRewards[rIdx][i];
            const double val = evalCardValue(gc, c) + g_tableAlpha * cardAdvCentered(c);
            if (val > bestV) { bestV = val; bestIdx = i; }
        }
        const bool skip = allowSkip && (bestV < evalSkipBar(gc));
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// policy 5: pure causal table; causally-correct skip rule (take iff adv > 0)
static void tableCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestRaw = -1e18;
        for (int i = 0; i < n; ++i) {
            const Card &c = r.cardRewards[rIdx][i];
            const CardType t = c.getType();
            if (t == CardType::CURSE || t == CardType::STATUS) continue;
            const double raw = cardAdvRaw(c);
            if (raw > bestRaw) { bestRaw = raw; bestIdx = i; }
        }
        const bool skip = bestRaw <= 0.0;
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

static std::string featureRow(const GameContext &gc);      // defined below
static std::string deckCountsCsv(const GameContext &gc);   // defined below

// Accumulates room-type visit counts along the taken path (pv* features). Defined
// here (not just before datagen) because the deployment run loop tracks it too, so
// V queries carry the same path-history features the model was trained on.
struct PathHistory {
    std::array<int, 10> roomVisits{};   // indexed by (int)Room
    long lastNodeKey = -1;
    void update(const GameContext &gc) {
        if (gc.curMapNodeY < 0 || gc.curMapNodeY >= 15 || gc.curMapNodeX < 0 || gc.curMapNodeX >= 7)
            return;
        const long key = (long)gc.act * 100000 + (long)gc.curMapNodeY * 100 + gc.curMapNodeX;
        if (key == lastNodeKey) return;
        lastNodeKey = key;
        const int ri = (int)gc.getCurMapNode().room;
        if (ri >= 0 && ri < 10) ++roomVisits[ri];
    }
};
// Current run's path history, so vFeatCsv() can emit pv* features (nullptr = none).
static thread_local const PathHistory *t_curPath = nullptr;
static std::string richRow(const GameContext &gc, const PathHistory &path);  // defined below
static std::string vFeatCsv(const GameContext &gc);                          // defined below
static std::string richHeader();                                             // defined below

// ---------------------------------------------------------------------------
// DECK-AWARE V VIA PYTHON BRIDGE: card picks are rare (~13/run) so we query the
// exact trained GBM held in v_server.py over a TCP socket. Card value =
// V(deck+card) - V(deck); the server returns the chosen index (or 5 = skip).
// One persistent connection per thread.
// ---------------------------------------------------------------------------
static int g_vPort = 5555;
static thread_local int t_vSock = -1;

// A benchmark run must not inherit a persistent server session from a previous
// seed in the same worker.  The protocol is request/response, but closing at a
// run boundary gives repeated-seed checks a clean, independently handled server
// connection and avoids any accidental socket-buffer/session carry-over.
static void vDisconnect() {
#ifndef _WIN32
    if (t_vSock >= 0) close(t_vSock);
#endif
    t_vSock = -1;
}
// Skip a card reward when the best candidate's marginal V(deck+card)-V(deck)
// (final-floor units) is below this. Default -0.5 (RICH V2): take a card unless it
// looks clearly diluting, skip only if marginal < -0.5. Re-swept @512 seeds asc0 on
// V2 -> best band -1.0..-0.25 (win 41-42%), peak -0.5=42.4% vs skip@0=38.7%; V2
// marginals read slightly pessimistic so a fuller deck wins. Positive thresholds
// still fall off a cliff. (Old deck-only V best was 0.0.) Override via STS_SKIP_THR.
static double g_cardSkipThresh = -0.5;
// A/B: route card picks through the WIN model (P(win) marginal) instead of V_floor.
// Own skip scale (win-prob units, ~0..0.05) so g_cardSkipThresh (floor units) doesn't apply.
static bool g_cardWin = false;          // env STS_CARD_WIN=1
static double g_cardWinSkip = 0.0;      // env STS_CARD_WIN_SKIP: skip iff best P(win) marginal < this
static bool g_shopWin = false;          // env STS_SHOP_WIN=1: score shop bundles by P(win) not V_floor
static bool g_nativeOoc = false;
static bool g_oocActionNN = false;          // env STS_OOC_ACTION_NN=1
static double g_oocStrategicMargin = 1.0;   // env STS_OOC_STRATEGIC_MARGIN: one-ply gate in V units
static int nativeFloorCardPick(GameContext &, int);
static double nativeFloorValue(GameContext &);
static bool oocOnePlyCardRewardPolicy(GameContext &);
static std::string nativeShopPlan(GameContext &);
// A/B: route card picks through the deck-set NN (P(win) marginal), optionally blended with
// the v_win GBM: marg = w*NN + (1-w)*GBM. Own skip scale (P(win) units).
static bool   g_cardNN     = false;     // env STS_CARD_NN=1
static double g_cardNNW    = 1.0;       // env STS_CARD_NN_W: blend weight on NN (1=pure NN)
static double g_cardNNSkip = 0.0;       // env STS_CARD_NN_SKIP: skip iff best P(win) marginal < this
// Direct paired action-value model (offered cards + skip), optionally with the
// full map graph. Unlike marginal value models, it learns its own skip action.
static bool   g_cardAction = false;     // env STS_CARD_ACTION=1 (CA server op)
// Datagen exploration: softmax temperature over card marginals (final-floor
// units; higher = more spread). The uniform-floor prob is datagen2's `epsilon`.
static double g_dgTemp = 2.0;   // env STS_DG_TEMP (swept: 1-2 good spread+quality, >=3 over-randomizes)
// Per-fight combat sim budget by difficulty (env STS_SIMS_NORMAL/ELITE/BOSS; <=0 or
// unset = use the run's base sims). Deaths cluster at elites/bosses, so we can search
// those deep and skimp on trivial hallway fights for the same win% at far less compute.
static int g_simsNormal = -1, g_simsElite = -1, g_simsBoss = -1;
// Pick the sim budget for the fight in the current room (falls back to base).
static int fightSims(const GameContext &gc, int base) {
    if (gc.curRoom == Room::BOSS || gc.curRoom == Room::BOSS_TREASURE) return g_simsBoss  > 0 ? g_simsBoss  : base;
    if (gc.curRoom == Room::ELITE)                                     return g_simsElite > 0 ? g_simsElite : base;
    return g_simsNormal > 0 ? g_simsNormal : base;   // MONSTER / event fights
}

// --- boss-aware drafting: for card picks near a hard fight, lean on a boss signal
// (either a rollout, or the boss-survival value model v_boss blended with v_rich).
// The gate is factored so the hard-fight set can later become DYNAMIC (learned from
// where we die); boss-only for now.
static int    g_bossDraft        = 0;      // STS_BOSS_DRAFT: rollout-based near-boss draft (experimental; hurt in A/B)
static int    g_bossDraftRows    = 3;      // trigger when a hard fight is within this many map rows
static int    g_bossDraftN       = 4;      // rollout: fights to simulate forward
static int    g_bossDraftSims    = 150;    // rollout: inner combat sim budget
static int    g_bossDraftFutures = 2;      // rollout: sampled futures per candidate
static int    g_bossV            = 0;      // STS_BOSS_V: blend v_boss marginal into near-boss server picks
static double g_bossVW           = 0.5;    // STS_BOSS_V_W: blend weight on the boss model (0..1)

// Experimental full-act draft evaluator.  For the immediate card decision only,
// it samples the *possible remaining encounter queues* in the current act and
// plays every fight on the selected route through the boss.  Its utility is an
// expectation over survival and a nonlinear post-fight HP safety margin, with a
// modest floor-distance discount.  It intentionally makes no V/card-model query
// for the card being picked; the regular OOC policy is used only inside a sampled
// continuation to resolve later choices.
static bool   g_actFightProbeDraft = false; // STS_ACT_FIGHT_PROBE_DRAFT=1
static int    g_actFightProbeSims = 100;    // STS_ACT_FIGHT_PROBE_SIMS
static int    g_actFightProbeFutures = 4;   // STS_ACT_FIGHT_PROBE_FUTURES
static double g_actFightProbeFloorDecay = 0.985; // STS_ACT_FIGHT_PROBE_FLOOR_DECAY
// Optional inner-search base budgets by reached checkpoint, e.g. 400,200,100.
// The live run's combat budget is unaffected; room-tier overrides still take
// precedence through fightSims().
static std::vector<int> g_actFightProbeCheckpointSims; // STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS
// -1 scores every remaining fight in the current act; a positive value scores only the
// next N combat checkpoints.  This is a horizon in fights, not map nodes, so
// routes with shops/events are not given a structurally different objective.
static int    g_actFightProbeMaxCheckpoints = -1; // STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS
static bool   g_actFightProbeTrace = false; // STS_ACT_FIGHT_PROBE_TRACE=1
// Parallelize the independent immediate-action × sampled-future branches of a
// single OOC decision.  Off by default so ordinary multi-seed benches retain
// their existing outer OpenMP scheduling.
static bool   g_actFightProbeParallelBranches = false; // STS_ACT_FIGHT_PROBE_PARALLEL=1
// Broader version used only for a deliberately expensive Act-1 experiment:
// evaluate every legal OOC action (map, rewards, events, shop, rest, selects),
// not just cards.  This is separate so the card-only oracle remains available.
static bool   g_actFightProbeAllOoc = false; // STS_ACT_FIGHT_PROBE_ALL_OOC=1
// Score and advance checkpoint fights with the entity combat model instead of
// running MCTS.  This is deliberately separate from STS_VNET: the latter is a
// leaf evaluator inside real combat search, while this one supplies both heads
// needed for a virtual post-combat transition.
static bool   g_actFightProbePredict = false; // STS_ACT_FIGHT_PROBE_PREDICT=1
static bool   g_actFightProbeEncounterNN = false; // STS_ACT_FIGHT_PROBE_ENCOUNTER_NN=1
static double g_actFightProbePredictWinThreshold = 0.5;
static std::string g_actFightProbePredictNetPath = "selfplay/models/v_combat_entity_iter34.txt";
static search::CombatValueNet g_actFightProbePredictNet;
static int    g_stopAfterAct = 0;            // STS_STOP_AFTER_ACT=N, benchmark horizon
// Optional durable per-action teacher data for the all-OOC oracle.  The file
// is append-only because benchmark runs may be stopped and resumed.
static std::string g_actFightProbeLogPath;   // STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv
static std::ofstream g_actFightProbeLog;
static std::mutex g_actFightProbeLogMutex;
static thread_local int t_actFightProbeDecisionIdx = 0;
static thread_local int t_actFightProbeActionIdx = -1;
static thread_local int t_actFightProbeFutureIdx = -1;

static int actFightProbeCheckpointSims(int defaultSims, int checkpointIdx) {
    if (checkpointIdx >= 0 && checkpointIdx < (int)g_actFightProbeCheckpointSims.size())
        return g_actFightProbeCheckpointSims[checkpointIdx];
    return defaultSims;
}

static std::string actFightProbeCheckpointSimsCsv() {
    std::ostringstream out;
    for (int i = 0; i < (int)g_actFightProbeCheckpointSims.size(); ++i) {
        if (i) out << ';';
        out << g_actFightProbeCheckpointSims[i];
    }
    return out.str();
}

// --- V-informed pathing: the next-fight features are a shared encounter QUEUE
// (route-independent at a decision), so V(state) is ~flat across immediate map
// children -> per-child V scoring gives no signal. Instead use V(state) as a
// deck-STRENGTH scalar (predicted final floor) to MODULATE the heuristic's
// aggression: a strong deck routes harder into elites/fights (farm relics while
// you can), a weak deck routes to rest/shop/event (recover). One V query/floor.
static int    g_vPath  = 0;      // STS_VPATH=1: enable V-strength path modulation
static double g_vPathK = 0.4;    // STS_VPATH_K: modulation gain (0=off .. ~1 strong)
// aggression for the current map decision, in [-1,+1]; set once per chooseMapAction
// call, read by roomValue. 0 = neutral (= plain heuristic).
static thread_local double t_pathAggr = 0.0;
// Act boss floors (finalFloor at which each act's boss sits) — the deck-strength
// anchor: predFloor - bossFloor[act] = how comfortably you clear this act.
static int bossFloorForAct(int act) { return act <= 1 ? 17 : act == 2 ? 34 : 50; }

// Map rows until the next hard fight. Boss sits just past the last map row (14),
// so rows-to-boss = 14 - curMapNodeY. (Extend to fold in elites / learned high-death
// floors for the dynamic version.)
static int rowsToHardFight(const GameContext &gc) {
    return 14 - std::max(gc.curMapNodeY, 0);
}

// --- potion-saving policy: the combat search is per-fight MYOPIC (optimizes THIS
// fight's end HP), so it spends potions on easy fights with no incentive to bank
// them for elites/bosses -- where we actually die. evaluateEndState already values
// a KEPT potion at g_potionKeepValue HP-equiv (drinking costs that much), so we make
// that value DYNAMIC per fight: high in easy fights when a hard fight is near (hoard),
// low in the hard fight itself (spend). Modulated by the potion DROP chance -- if we'll
// likely refill before the hard fight (high potionChance / White Beast Statue = 100%),
// there's less need to save the current one.
static int    g_potionSave    = 0;      // STS_POTION_SAVE=1: enable dynamic potion keep-value
static int    g_potionWindow  = 5;      // STS_POTION_WINDOW: only save when a hard fight is <= this many rows away
static double g_potionBonus   = 18.0;   // STS_POTION_BONUS: extra HP-equiv keep-value at max urgency
static double g_potionSpend   = 1.0;    // STS_POTION_SPEND: keep-value DURING an elite/boss (low = spend)
static double g_potionDesired = 2.5;    // STS_POTION_DESIRED: potions we'd like entering a hard fight
static const double kPotionBaseKeep = 4.0;   // the engine's original constant (neutral default)

// Per-fight potion keep-value (HP-equiv), set into search::g_potionKeepValue before combat.
static double potionKeepValue(const GameContext &gc) {
    if (!g_potionSave) return kPotionBaseKeep;
    const Room r = gc.curRoom;
    if (r == Room::ELITE || r == Room::BOSS || r == Room::BOSS_TREASURE)
        return g_potionSpend;                       // the hard fight itself -> spend freely
    const int hardDist = std::min(rowsToNextElite(gc), rowsToHardFight(gc));  // rows to nearest elite/boss
    if (hardDist <= 0 || hardDist > g_potionWindow) return kPotionBaseKeep;   // nothing hard soon
    const double p = gc.hasRelic(RelicId::WHITE_BEAST_STATUE)
                       ? 1.0 : std::clamp((double)gc.potionChance / 100.0, 0.0, 1.0);
    const double expDrops  = hardDist * p;          // potions we'll likely gain before the hard fight
    const double scarcity  = std::clamp(1.0 - expDrops / g_potionDesired, 0.0, 1.0);  // less save if refilling
    const double proximity = (double)(g_potionWindow - hardDist + 1) / g_potionWindow; // closer = more urgent
    return kPotionBaseKeep + g_potionBonus * proximity * scarcity;
}

static int vConnect() {
    if (t_vSock >= 0) return t_vSock;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)g_vPort);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    if (connect(fd, (sockaddr *)&addr, sizeof(addr)) < 0) { close(fd); return -1; }
    t_vSock = fd;
    return fd;
}

// Inference requests are idempotent.  Never turn a transient socket failure or
// short write into a strategic fallback (card skip, empty shop plan, etc.):
// reconnect and replay the complete request.  The old one-shot send() path
// silently changed decisions when a persistent connection was dropped.
static std::string vRequestLine(const std::string &requestWithNewline) {
    // Model loading (especially the optional Torch model) can take several
    // seconds.  A fixed launcher sleep previously let the first benchmark run
    // race server readiness and silently use fallbacks, while later runs used
    // the real policy.  Wait through cold start as well as retrying dropped
    // persistent connections.
    constexpr int maxAttempts = 50;
    for (int attempt = 0; attempt < maxAttempts; ++attempt) {
        int fd = vConnect();
        if (fd < 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        std::size_t sent = 0;
        while (sent < requestWithNewline.size()) {
            const ssize_t n = send(fd, requestWithNewline.data() + sent,
                                   requestWithNewline.size() - sent, 0);
            if (n <= 0) break;
            sent += static_cast<std::size_t>(n);
        }
        if (sent != requestWithNewline.size()) {
            vDisconnect();
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        char buf[8192];
        std::string response;
        while (response.find('\n') == std::string::npos) {
            const ssize_t n = recv(fd, buf, sizeof(buf), 0);
            if (n <= 0) break;
            response.append(buf, static_cast<std::size_t>(n));
        }
        const auto newline = response.find('\n');
        if (newline != std::string::npos) {
            response.resize(newline + 1);
            return response;
        }
        vDisconnect();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return {};
}

static std::string mapGraphCsv(const GameContext &gc, bool rooms) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const MapNode &node = gc.map->getNode(x, y);
        if (rooms) {
            out << static_cast<int>(node.room);
        } else {
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << edgeMask;
        }
    }
    return out.str();
}

static std::string mapSpecialCsv(const GameContext &gc) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const bool burning = !gc.greenKey && x == gc.map->burningEliteX && y == gc.map->burningEliteY;
        out << (burning ? 1 : 0);
    }
    return out.str();
}

// send a tagged candidate/state query and read back the chosen index.
// bossW >= 0 routes the pick through the boss-survival blend "CB;<w>;..." (the
// server returns the chosen card's v_rich marginal, so the skip logic is unchanged).
static int vQuery(GameContext &gc, int rIdx, double bossW = -1.0) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    if (g_nativeOoc && bossW < 0.0 && !g_cardWin && !g_cardNN && !g_cardAction)
        return nativeFloorCardPick(gc, rIdx);
    std::string req;
    if (g_cardAction) req += "CA;";                           // direct card/skip action value
    else if (bossW >= 0.0) { req += "CB;"; req += std::to_string(bossW); req += ';'; }  // boss-V blend
    else if (g_cardNN) { req += "CN;"; req += std::to_string(g_cardNNW); req += ';'; }  // deck-set NN marginal
    else if (g_cardWin) req += "CW;";   // route card pick through the win model (P(win) marginal)
    for (int i = 0; i < n; ++i) {
        if (i) req += ',';
        const Card &card = r.cardRewards[rIdx][i];
        req += std::to_string((int)card.getId());
        if (g_cardAction) { req += ':'; req += card.isUpgraded() ? '1' : '0'; }
    }
    req += ';';
    if (g_cardAction) {
        req += mapGraphCsv(gc, true); req += ';';
        req += mapGraphCsv(gc, false); req += ';';
        req += mapSpecialCsv(gc); req += ';';
    }
    req += vFeatCsv(gc);        // full rich feature vector (richRow schema)
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return 5;
    // server returns "<best_idx> <best_marginal>"; apply the skip threshold here
    int idx = 5; double marg = -1e9;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &marg) < 1) return 5;
    if (idx < 0 || (idx >= n && idx != 5)) return 5;
    if (g_actFightProbeTrace) {
        std::cerr << "[card-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " candidates=";
        for (int i = 0; i < n; ++i)
            std::cerr << (i ? ";" : "") << (int)r.cardRewards[rIdx][i].getId();
        std::cerr << " reqHash=" << std::hash<std::string>{}(req)
                  << " response=" << idx << ':' << marg << "]\n";
    }
    // boss blend returns a floor-scale v_rich marginal, so use the floor skip bar there
    const double skipThr = (bossW >= 0.0) ? g_cardSkipThresh
                         : g_cardNN        ? g_cardNNSkip
                         : (g_cardWin ? g_cardWinSkip : g_cardSkipThresh);
    if (!g_cardAction && idx != 5 && marg < skipThr) return 5; // direct action model selects skip itself
    return idx;
}

// Raw V(state) = predicted final floor for the current state (server "VS" op).
// Used as a deck-strength scalar for V-informed pathing. Returns a large sentinel
// (so aggr clamps to neutral-ish) if the server is unreachable.
static double vStateRaw(GameContext &gc) {
    if (g_nativeOoc) return nativeFloorValue(gc);
    std::string req = "VS;";
    req += vFeatCsv(gc);
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return -1e9;
    double v = -1e9;
    if (std::sscanf(resp.c_str(), "%lf", &v) < 1) return -1e9;
    return v;
}

// Generic one-line request/response to the value server (for trace tooling).
static std::string vSendRecv(const std::string &reqNoNl) {
    std::string req = reqNoNl; req += '\n';
    return vRequestLine(req);
}

// forward decls (native V_win helpers are defined below with the WinNet struct)
static const std::unordered_map<std::string,int> &richIdxMap();
static std::vector<float> richFeatureVec(GameContext &gc);
static bool   winNetOk();
static double winNetPredict(const std::vector<float> &raw);

// Native win-model card pick (P(win) marginal), mirrors server decide_win but socket-free.
static int nativeWinCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int nc = r.cardRewards[rIdx].size();
    const auto &idx = richIdxMap();
    const std::vector<float> base = richFeatureVec(gc);
    const double b = winNetPredict(base);
    const int dsz = idx.at("deckSize");
    int barg = 0; double bmarg = -1e18;
    for (int i = 0; i < nc; ++i) {
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        std::vector<float> v = base;
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) v[it->second] += 1.0f;
        v[dsz] += 1.0f;
        const double m = winNetPredict(v) - b;
        if (m > bmarg) { bmarg = m; barg = i; }
    }
    return bmarg < g_cardWinSkip ? 5 : barg;    // skip if best marginal below the win-scale bar
}

// policy 6: query the deck-aware GBM server for each card reward
static void serverCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        // near a hard fight, blend the boss-survival marginal into the pick
        const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
        // native win-model card pick when available (self-play unified policy) -> no socket
        const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                  : vQuery(gc, rIdx, bossW);
        search::GameAction(RT::CARD, rIdx, idx).execute(gc);
    }
}

// --- BOSS-RELIC + NEOW choice via V_win: pick the option whose RESULTING state has the
// highest P(win). Same "which resulting state is best" frame as shop/rest, now applied to two
// high-impact decisions the default heuristic used to own. Each candidate is applied to a COPY
// (real relic/Neow transition, RNG untouched on the real gc), evaluated with V_win, argmax'd.
static int g_bossRelicV = 0;   // STS_BOSS_RELIC=1
static int g_neowV      = 0;   // STS_NEOW_V=1

// --- NATIVE V_win: compact XGBoost tree-walk on the rich feature vector, to kill the
// v_server socket for OOC V_win decisions (esp. the unbatched per-candidate ones:
// boss-relic/Neow/pathing). Loaded from build/v_win_trees.txt (export_win_model.py).
struct WinNet {
    struct Node { int feat; float thr; int yes, no; };   // feat<0 => leaf (value in thr)
    std::vector<std::vector<Node>> trees;
    std::vector<int> sel;                                  // model feat i -> rich raw index
    double baseMargin = 0.0; bool logistic = true, ok = false;
    std::string path;                                      // loaded-tree source path

    bool load(const std::string &path, const std::unordered_map<std::string,int> &richIdx) {
        this->path = path;
        std::ifstream f(path); if (!f) return false;
        std::string tok; int nfeat = 0, ntrees = 0; double baseScore = 0.5;
        f >> tok >> nfeat;                                 // "nfeat N"
        sel.resize(nfeat);
        for (int i = 0; i < nfeat; ++i) { std::string kw, name; f >> kw >> name;
            auto it = richIdx.find(name);
            if (it == richIdx.end()) { std::cerr << "WinNet: feat not in rich layout: " << name << "\n"; return false; }
            sel[i] = it->second; }
        f >> tok >> logistic;                              // "logistic 0/1"
        f >> tok >> baseScore;                             // "base_score X"
        f >> tok >> ntrees;                                // "ntrees N"
        baseMargin = logistic ? std::log(baseScore / (1.0 - baseScore)) : baseScore;
        trees.resize(ntrees);
        for (int t = 0; t < ntrees; ++t) {
            std::string kw; int ti, nn; f >> kw >> ti >> nn;   // "tree t count"
            trees[t].resize(nn);
            for (int i = 0; i < nn; ++i) {
                std::string type; f >> type;
                if (type == "L") { double v; f >> v; trees[t][i] = { -1, (float)v, 0, 0 }; }
                else { int fi, y, no; float th; f >> fi >> th >> y >> no; trees[t][i] = { fi, th, y, no }; }
            }
        }
        ok = true;
        std::cout << "[native V_win: " << ntrees << " trees, " << nfeat << " feats from " << path << "]\n";
        return true;
    }
    double predict(const std::vector<float> &raw) const {
        double m = baseMargin;
        for (const auto &tr : trees) { int i = 0;
            while (tr[i].feat >= 0) i = (raw[sel[tr[i].feat]] < tr[i].thr) ? tr[i].yes : tr[i].no;
            m += tr[i].thr; }
        return logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
    }
};
static WinNet g_winNet;
static WinNet g_floorNet;
static bool   winNetOk() { return g_winNet.ok; }
static double winNetPredict(const std::vector<float> &raw) { return g_winNet.predict(raw); }

// rich feature NAME -> raw index (from richHeader minus the seed prefix and the 3 labels).
static const std::unordered_map<std::string,int> &richIdxMap() {
    static std::unordered_map<std::string,int> m;
    if (m.empty()) {
        std::string h = richHeader(); std::vector<std::string> names; std::string cur;
        for (char c : h) { if (c == ',') { names.push_back(cur); cur.clear(); } else cur += c; }
        names.push_back(cur);
        // drop "seed" (front) and won/finalFloor/endHp (back) -> raw layout
        for (int i = 1; i + 3 < (int)names.size(); ++i) m[names[i]] = i - 1;
    }
    return m;
}
// rich feature vector as floats (parse of vFeatCsv -> exactly the raw layout).
static std::vector<float> richFeatureVec(GameContext &gc) {
    const std::string s = vFeatCsv(gc);
    std::vector<float> v; v.reserve(1024); std::string cur;
    for (char c : s) { if (c == ',') { v.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); } else cur += c; }
    if (!cur.empty()) v.push_back(std::strtof(cur.c_str(), nullptr));
    return v;
}

static double nativeFloorValue(GameContext &gc) {
    return g_floorNet.ok ? g_floorNet.predict(richFeatureVec(gc)) : 0.0;
}

static int nativeFloorCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const std::vector<float> base = richFeatureVec(gc);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    double best = -1e100; int bestIdx = 5;
    const double v0 = g_floorNet.predict(base);
    for (int i = 0; i < r.cardRewards[rIdx].size(); ++i) {
        std::vector<float> row = base;
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) row[it->second] += 1.0f;
        row[dsz] += 1.0f;
        const double marginal = g_floorNet.predict(row) - v0;
        if (marginal > best) { best = marginal; bestIdx = i; }
    }
    return best < g_cardSkipThresh ? 5 : bestIdx;
}

static std::string nativeShopPlan(GameContext &gc) {
    const Shop &sh = gc.info.shop;
    const auto &idx = richIdxMap();
    const int goldIdx = idx.at("gold"), dsz = idx.at("deckSize");
    const std::vector<float> base = richFeatureVec(gc);
    struct Item { char kind; int slot, price, id; };
    std::vector<Item> items;
    for (int i = 0; i < 7; ++i) if (sh.cardPrice(i) >= 0)
        items.push_back({'c', i, sh.cardPrice(i), (int)sh.cards[i].getId()});
    for (int i = 0; i < 3; ++i) if (sh.relicPrice(i) >= 0)
        items.push_back({'r', i, sh.relicPrice(i), (int)sh.relics[i]});
    if (items.size() > 16) items.resize(16);
    int removeId = -1; double removeGain = 0.0;
    if (sh.removeCost >= 0) {
        double v0 = g_floorNet.predict(base);
        for (int id = 0; id < 372; ++id) {
            auto it = idx.find("d" + std::to_string(id));
            if (it == idx.end() || base[it->second] <= 0) continue;
            auto row = base; row[it->second] -= 1.0f; row[dsz] -= 1.0f;
            double gain = g_floorNet.predict(row) - v0;
            if (removeId < 0 || gain > removeGain) { removeId = id; removeGain = gain; }
        }
    }
    double best = -1e100; unsigned bestMask = 0; bool bestRemove = false;
    const unsigned total = 1u << items.size();
    for (unsigned mask = 0; mask < total; ++mask) {
        int spend = 0, adds = 0;
        for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) { spend += items[k].price; ++adds; }
        for (int rem = 0; rem <= 1; ++rem) {
            if (rem && (sh.removeCost < 0 || removeId < 0)) continue;
            if (spend + (rem ? sh.removeCost : 0) > gc.gold) continue;
            auto row = base; row[goldIdx] -= spend + (rem ? sh.removeCost : 0); row[dsz] += adds;
            for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
                if (items[k].kind == 'c') {
                    auto it = idx.find("d" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] += 1.0f;
                } else {
                    auto it = idx.find("r" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] = std::max(row[it->second], 1.0f);
                }
            }
            if (rem) { auto it = idx.find("d" + std::to_string(removeId)); if (it != idx.end()) row[it->second] -= 1.0f; }
            const double value = g_floorNet.predict(row);
            if (value > best) { best = value; bestMask = mask; bestRemove = rem != 0; }
        }
    }
    std::ostringstream out;
    for (unsigned k = 0; k < items.size(); ++k) if (bestMask & (1u << k)) out << items[k].kind << items[k].slot << ' ';
    if (bestRemove) out << 'x';
    return out.str();
}

static double vStateWin(GameContext &gc) {
    if (g_winNet.ok) return g_winNet.predict(richFeatureVec(gc));   // native path
    double v = 0.5;
    std::sscanf(vSendRecv("VW;" + vFeatCsv(gc)).c_str(), "%lf", &v);
    return v;
}
static void bossRelicVPolicy(GameContext &gc) {
    int best = -1; double bestV = -1e18;
    for (int i = 0; i < 3; ++i) {
        if (gc.info.bossRelics[i] == RelicId::INVALID) continue;
        GameContext g2 = gc; g2.chooseBossRelic(i);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseBossRelic(best < 0 ? 0 : best);
}
static void neowVPolicy(GameContext &gc) {
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)gc.info.neowRewards.size(); ++i) {
        GameContext g2 = gc; g2.chooseNeowOption(g2.info.neowRewards[i]);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseNeowOption(gc.info.neowRewards[best]);
}

static int g_pathV  = 0;   // STS_PATH_V:  model-driven pathing
static int g_pathGraph = 0; // STS_PATH_GRAPH: full-map graph NN child scoring
static int g_pathAction = 0;// STS_PATH_ACTION: direct paired route-action NN
static int g_pathActionMax = -1;
static double g_pathActionMargin = 0.0;
static bool g_pathActionTrace = false;
static thread_local int t_pathActionUses = 0;
static int g_eventV = 0;   // STS_EVENT_V: model-driven events
static int chooseMapAction(const GameContext &gc);   // heuristic pathing (defined below)

// Model-driven pathing: pick the immediate child whose position maximizes V_win. Position now
// affects V only through the forward-map features (fm*), so V responds to "what's ahead this way".
// Old models not trained on fm* are ~flat here -> payoff after self-play retraining on fm data.
static void pathVPolicy(GameContext &gc) {
    const Map &map = *gc.map;
    std::vector<int> cands;
    const int childRow = gc.curMapNodeY + 1;
    if (gc.curMapNodeY < 0) { for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) cands.push_back(n.x); }
    else { const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY); for (int i = 0; i < n.edgeCount; ++i) cands.push_back(n.edges[i]); }
    if (cands.empty()) { search::GameAction(chooseMapAction(gc)).execute(gc); return; }
    if (g_pathAction) {
        const int heuristic = chooseMapAction(gc);
        std::ostringstream req;
        req << "PA;";
        for (int i = 0; i < (int)cands.size(); ++i) { if (i) req << ','; req << cands[i]; }
        req << ';' << heuristic << ';' << mapGraphCsv(gc, true) << ';' << mapGraphCsv(gc, false) << ';'
            << mapSpecialCsv(gc) << ';' << vFeatCsv(gc);
        int chosen = -1; double advantage = -1e9;
        const std::string response = vSendRecv(req.str());
        std::sscanf(response.c_str(), "%d %lf", &chosen, &advantage);
        const bool capacity = g_pathActionMax < 0 || t_pathActionUses < g_pathActionMax;
        if (g_pathActionTrace) {
            #pragma omp critical(path_action_trace)
            std::cerr << "[path-action] seed=" << gc.seed << " pos=" << gc.curMapNodeX << ','
                      << gc.curMapNodeY << " heuristic=" << heuristic << " chosen=" << chosen
                      << " advantage=" << advantage << " uses=" << t_pathActionUses
                      << " capacity=" << capacity << " response='" << response << "'\n";
        }
        if (capacity && advantage >= g_pathActionMargin
            && std::find(cands.begin(), cands.end(), chosen) != cands.end()) {
            search::GameAction(chosen).execute(gc);
            if (chosen != heuristic) ++t_pathActionUses;
            return;
        }
        search::GameAction(heuristic).execute(gc); // conservative/server-failure fallback
        return;
    }
    int bestX = cands[0]; double bestV = -1e18;
    for (int x : cands) {
        double v;
        if (g_pathGraph) {
            std::string req = "PG;" + std::to_string(x) + ';' + mapGraphCsv(gc, true) + ';'
                            + mapGraphCsv(gc, false) + ';' + mapSpecialCsv(gc) + ';' + vFeatCsv(gc);
            v = 0.5;
            std::sscanf(vSendRecv(req).c_str(), "%lf", &v);
        } else {
            const int oX = gc.curMapNodeX, oY = gc.curMapNodeY;
            gc.curMapNodeX = x; gc.curMapNodeY = childRow; // old forward-summary child evaluation
            v = vStateWin(gc);
            gc.curMapNodeX = oX; gc.curMapNodeY = oY;
        }
        if (v > bestV) { bestV = v; bestX = x; }
    }
    search::GameAction(bestX).execute(gc);
}

// Model-driven events: enumerate the event's options, evaluate V_win of each resulting state,
// pick the best. Returns false (caller falls back to default) if no options are available.
static bool eventVPolicy(GameContext &gc) {
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext g2 = gc; actions[i].execute(g2);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    actions[best].execute(gc);
    return true;
}

// ---------------------------------------------------------------------------
// REST-SITE VALUE POLICY: use the same deck-aware GBM (curHp is a live feature)
// to decide heal-vs-upgrade by their effect on expected final floor.
//   heal  value = V(deck, hp+restHeal) - V(deck, hp)              (server "H")
//   upgrade target = argmax V(deck) - V(deck-card) over deck cards (server "U")
// Rest iff heal value >= g_restVThreshold, else upgrade the deck's most-valued
// card. Only overrides the genuine heal-vs-smith choice (both available); every
// other campfire option (keys/dig/lift/toke) is left to the default agent so
// this stays a clean A/B of exactly the heal/upgrade tradeoff.
// ---------------------------------------------------------------------------
static double g_restVThreshold = 0.15;  // heal iff healGain (final-floor units) >= this;
                                        // swept best band 0.1-0.25 @512 seeds (STS_REST_V_THRESH to override)

// send an already-built request line, return the response line (empty on error)
static std::string vTransact(const std::string &req) {
    int fd = vConnect();
    if (fd < 0) return "";
    if (send(fd, req.data(), req.size(), 0) < 0) { close(fd); t_vSock = -1; return ""; }
    char buf[64]; std::string resp;
    while (resp.find('\n') == std::string::npos) {
        ssize_t k = recv(fd, buf, sizeof(buf), 0);
        if (k <= 0) { close(fd); t_vSock = -1; return ""; }
        resp.append(buf, k);
    }
    return resp;
}

// V(deck, hp+healAmt) - V(deck, hp), in expected-final-floor units (0 on error)
static double vQueryHeal(GameContext &gc, int healAmt) {
    std::string req = "H;" + std::to_string(healAmt) + ";"
                    + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// index (into candIds) of the deck's most-valued card to upgrade (0 on error)
static int vQueryUpgrade(GameContext &gc, const std::vector<int> &candIds) {
    std::string req = "U;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// Marginal V(deck+card)-V(deck) for each card reward candidate (empty on error).
static std::vector<double> vQueryMarginals(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    std::string req = "M;";
    for (int i = 0; i < n; ++i) { if (i) req += ','; req += std::to_string((int)r.cardRewards[rIdx][i].getId()); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    std::vector<double> out;
    std::istringstream is(resp);
    double m;
    while (is >> m) out.push_back(m);
    return out;
}

// Softmax-sample WHICH card to take (0..n-1) among the n candidates by marginal V
// (temp; higher = more spread). With prob uniformEps pick a uniformly-random card
// (coverage floor so V's blind spots still get sampled). The take-vs-skip decision
// is handled by the caller (skip@g_cardSkipThresh on the BEST marginal), so deck
// sizes match the exploit policy and we only diversify the card choice.
static int sampleCardSoftmax(const std::vector<double> &marg, double temp, double uniformEps,
                             std::default_random_engine &ex) {
    const int n = (int)marg.size();
    if (n <= 1) return 0;
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    if (ur(ex) < uniformEps) return std::uniform_int_distribution<int>(0, n - 1)(ex);
    const double mx = *std::max_element(marg.begin(), marg.end());
    const double t = temp > 1e-6 ? temp : 1e-6;
    double sum = 0.0; std::vector<double> w(n);
    for (int i = 0; i < n; ++i) { w[i] = std::exp((marg[i] - mx) / t); sum += w[i]; }
    double rnd = ur(ex) * sum, acc = 0.0;
    for (int i = 0; i < n; ++i) { acc += w[i]; if (rnd <= acc) return i; }
    return n - 1;
}

// Handle a REST_ROOM screen with the value policy. Returns true if it acted;
// false = defer to the default agent (only the heal-vs-smith case is handled).
static bool restVPolicy(GameContext &gc) {
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;      // keys/dig/lift/single-option -> default agent
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    const double healGain = vQueryHeal(gc, healAmt);
    search::GameAction(healGain >= g_restVThreshold ? 0 : 1, 0).execute(gc);  // 0=rest, 1=smith
    return true;
}

// Handle the UPGRADE card-select opened by SMITH: pick the deck's most-valued card.
static void upgradeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryUpgrade(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

// ---------------------------------------------------------------------------
// WIN-RATE REST POLICY: decide heal-vs-upgrade in P(win) units (win model),
// where HP's effect on survival is sharp and nonlinear (unlike expected floor).
// Both options are scored as a P(win) gain and compared directly (no threshold):
//   heal    gain = P(win, hp+restHeal) - P(win, hp)              (server "HW")
//   upgrade gain = max_c P(win, u{c}+1) - P(win)                 (server "UW")
// Rest iff healGain >= best upgradeGain, else smith (upgrading that best card).
// ---------------------------------------------------------------------------
// Default ON: win-rate rest policy beats the default agent by +4.9pp @512 (47.3 vs
// 42.4, floor+HP also up). Needs the win model loaded in v_server (VWIN); set
// STS_REST_WIN=0 to disable (falls back to the sim default rest agent).
static bool g_restWin = true;

// P(win, hp+healAmt) - P(win, hp) from the win model (0 on error).
static double vQueryHealWin(GameContext &gc, int healAmt) {
    if (g_nativeOoc && g_winNet.ok) {
        const int old = gc.curHp;
        const double before = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = std::min(gc.maxHp, old + healAmt);
        const double after = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = old;
        return after - before;
    }
    std::string req = "HW;" + std::to_string(healAmt) + ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// Best upgrade by P(win): returns index into candIds and sets *gain to its win gain.
static int vQueryUpgradeWin(GameContext &gc, const std::vector<int> &candIds, double *gain) {
    if (g_nativeOoc && g_winNet.ok) {
        const auto &idx = richIdxMap(); auto base = richFeatureVec(gc);
        const double before = g_winNet.predict(base); double best = -1e100; int bestIdx = 0;
        for (int i = 0; i < (int)candIds.size(); ++i) {
            auto row = base; auto it = idx.find("u" + std::to_string(candIds[i]));
            if (it != idx.end()) row[it->second] += 1.0f;
            const double d = g_winNet.predict(row) - before;
            if (d > best) { best = d; bestIdx = i; }
        }
        // Mirror v_server.py's deterministic fallback: the deployed win model
        // has no useful upgrade head for some cards, so choose the card whose
        // removal most improves the current state in that case.
        if (std::abs(best) < 1e-6) {
            best = -1e100; bestIdx = 0;
            for (int i = 0; i < (int)candIds.size(); ++i) {
                auto row = base; auto it = idx.find("d" + std::to_string(candIds[i]));
                if (it != idx.end()) row[it->second] -= 1.0f;
                auto ds = idx.find("deckSize"); if (ds != idx.end()) row[ds->second] -= 1.0f;
                const double d = before - g_winNet.predict(row);
                if (d > best) { best = d; bestIdx = i; }
            }
        }
        if (gain) *gain = best;
        return bestIdx;
    }
    std::string req = "UW;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = 0; double g = 0.0;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &g) < 1) { idx = 0; g = 0.0; }
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    if (gain) *gain = g;
    return idx;
}

// Direct paired counterfactual rest-vs-smith model. Returns false when no model is
// deployed (server replies NA), preserving the proven V_win marginal fallback.
static bool vQueryRestCounterfactual(GameContext &gc, double *delta) {
    if (g_nativeOoc) return false;
    const std::string resp = vTransact("RC;" + vFeatCsv(gc) + "\n");
    double d = 0.0;
    if (resp.empty() || resp.rfind("NA", 0) == 0
        || std::sscanf(resp.c_str(), "%lf", &d) != 1 || !std::isfinite(d)) return false;
    if (delta) *delta = d;
    return true;
}

// Deduped ids of the deck's upgradeable cards (candidates for a smith).
static std::vector<int> upgradeableIds(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        const int id = (int)gc.deck.cards[i].getId();
        if (std::find(ids.begin(), ids.end(), id) == ids.end()) ids.push_back(id);
    }
    return ids;
}

// Handle a REST_ROOM screen by win-rate: rest iff heal raises P(win) more than the
// best upgrade does. Returns false (defer to default agent) if it's not a genuine
// heal-vs-smith choice (keys/dig/single-option).
static bool restWinPolicy(GameContext &gc) {
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    double pairedDelta = 0.0;
    if (vQueryRestCounterfactual(gc, &pairedDelta)) {
        search::GameAction(pairedDelta >= 0.0 ? 0 : 1, 0).execute(gc);
        return true;
    }
    const double healGain = vQueryHealWin(gc, healAmt);
    std::vector<int> ids = upgradeableIds(gc);
    double upGain = 0.0;
    if (!ids.empty()) vQueryUpgradeWin(gc, ids, &upGain);
    search::GameAction(healGain >= upGain ? 0 : 1, 0).execute(gc);  // 0=rest, 1=smith
    return true;
}

// Handle the UPGRADE card-select opened by SMITH: pick the card with the best P(win) upgrade.
static void upgradeSelectWinPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    double g = 0.0;
    const int idx = ids.empty() ? 0 : vQueryUpgradeWin(gc, ids, &g);
    search::GameAction(idx, 0).execute(gc);
}

// index (into candIds) of the card whose REMOVAL most raises V (0 on error)
static int vQueryRemove(GameContext &gc, const std::vector<int> &candIds) {
    std::string req = "X;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// ---------------------------------------------------------------------------
// SHOP VALUE POLICY: ask the server for the V-maximizing affordable bundle of
// {card buys, card removal, relic buys} and execute it. Card buys and removal
// are well-modeled (deck-aware V); relics get a generic nRelics delta (can't
// rank relic identity); potions are not modeled (never bought here). Returns
// true if it acted on the shop screen.
// ---------------------------------------------------------------------------
static std::string vQueryShop(GameContext &gc) {
    if (g_nativeOoc && !g_shopWin) return nativeShopPlan(gc);
    const Shop &sh = gc.info.shop;
    std::string cardsCsv, relicsCsv;
    for (int i = 0; i < 7; ++i) {
        if (i) cardsCsv += ',';
        cardsCsv += std::to_string((int)sh.cards[i].getId()) + ":" + std::to_string(sh.cardPrice(i));
    }
    for (int j = 0; j < 3; ++j) {
        if (j) relicsCsv += ',';
        relicsCsv += std::to_string((int)sh.relics[j]) + ":" + std::to_string(sh.relicPrice(j));
    }
    std::string req = std::string(g_shopWin ? "SW;" : "S;") + std::to_string(sh.removeCost)
                    + ";" + cardsCsv + ";" + relicsCsv + ";" + vFeatCsv(gc) + "\n";
    return vTransact(req);
}

// Execute ONE purchase from the V-optimal plan, then return. Re-entry re-optimizes
// on the updated state, so a buy that opens a follow-up screen (e.g. a bottling
// relic, or the removal card-select) can't desync a multi-buy sequence. Empty
// plan -> leave the shop. Each buy strictly spends gold, so this terminates.
static void shopVPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    const std::string requestState = g_actFightProbeTrace ? vFeatCsv(gc) : std::string{};
    std::string plan = vQueryShop(gc);
    if (g_actFightProbeTrace) {
        const Shop &sh = gc.info.shop;
        std::cerr << "[shop-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " gold=" << gc.gold
                  << " cardRng=" << gc.cardRng.seed0 << ':' << gc.cardRng.seed1
                  << " merchantRng=" << gc.merchantRng.seed0 << ':' << gc.merchantRng.seed1
                  << " potionRng=" << gc.potionRng.seed0 << ':' << gc.potionRng.seed1
                  << " remove=" << sh.removeCost << " cards=";
        for (int i = 0; i < 7; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.cards[i].getId() << ':' << sh.cardPrice(i);
        std::cerr << " relics=";
        for (int i = 0; i < 3; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.relics[i] << ':' << sh.relicPrice(i);
        std::cerr << " featHash=" << std::hash<std::string>{}(requestState)
                  << " plan=" << plan << "]\n";
    }
    std::istringstream is(plan);
    std::string tok;
    if (!(is >> tok) || tok.empty()) { search::GameAction(RT::SKIP).execute(gc); return; }
    const int idx = tok.size() > 1 ? std::atoi(tok.c_str() + 1) : 0;
    if (tok[0] == 'c')      search::GameAction(RT::CARD,  idx).execute(gc);
    else if (tok[0] == 'r') search::GameAction(RT::RELIC, idx).execute(gc);
    else if (tok[0] == 'x') search::GameAction(RT::CARD_REMOVE).execute(gc);   // opens REMOVE select
    else                    search::GameAction(RT::SKIP).execute(gc);
}

// Pick the removal target on a shop REMOVE card-select: the worst card by V.
static void removeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryRemove(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

// ---------------------------------------------------------------------------
// LEARNED VALUE FUNCTION: V(state)=sigmoid(bias + sum w_i*feature_i), weights
// trained offline (logistic regression, train_value.py). Card value is the
// marginal V(deck+card) - V(deck); skip if no card has positive marginal value.
// Feature definitions MUST match featureRow() above.
// ---------------------------------------------------------------------------
static std::map<std::string, double> g_valWeights;
static double g_valBias = 0.0;
static bool g_valLoaded = false;
static bool g_learnedNeverSkip = false;   // diagnostic: always take best card, never skip

static void loadValueModel(const std::string &path) {
    std::ifstream f(path);
    if (!f) { std::cerr << "WARNING: could not open value model: " << path << "\n"; return; }
    std::string name; double w;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream is(line);
        is >> name >> w;
        if (name == "bias") g_valBias = w;
        else g_valWeights[name] = w;
    }
    g_valLoaded = true;
    std::cout << "loaded value model (" << g_valWeights.size() << " weights) from " << path << "\n";
}

static double sigmoid(double z) { return 1.0 / (1.0 + std::exp(-z)); }

// current-state features (same definitions as featureRow)
static std::map<std::string, double> stateFeats(const GameContext &gc) {
    std::map<std::string, double> m;
    int nAtk=0,nSkill=0,nPow=0,nCurse=0,nStatus=0,nUpg=0,nStarter=0,nCommon=0,nUncommon=0,nRare=0;
    long obtainSum = 0;
    for (const auto &c : gc.deck.cards) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::SKILL:  ++nSkill; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::CURSE:  ++nCurse; break;
            case CardType::STATUS: ++nStatus; break;
            default: break;
        }
        if (c.isUpgraded()) ++nUpg;
        if (c.isStarterStrikeOrDefend()) ++nStarter;
        switch (c.getRarity()) {
            case CardRarity::COMMON:   ++nCommon; break;
            case CardRarity::UNCOMMON: ++nUncommon; break;
            case CardRarity::RARE:     ++nRare; break;
            default: break;
        }
        obtainSum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    const int deckSize = gc.deck.size();
    m["act"]=gc.act; m["floor"]=gc.floorNum; m["curHp"]=gc.curHp; m["maxHp"]=gc.maxHp;
    m["gold"]=gc.gold; m["deckSize"]=deckSize;
    m["nAttack"]=nAtk; m["nSkill"]=nSkill; m["nPower"]=nPow; m["nCurse"]=nCurse; m["nStatus"]=nStatus;
    m["nUpgraded"]=nUpg; m["nStarter"]=nStarter;
    m["nCommon"]=nCommon; m["nUncommon"]=nUncommon; m["nRare"]=nRare;
    m["obtainSum"]=(double)obtainSum; m["obtainAvg"]= deckSize? (double)obtainSum/deckSize : 0.0;
    m["nRelics"]=(double)gc.relics.relics.size();
    return m;
}

static double logitOf(const std::map<std::string, double> &feats) {
    double z = g_valBias;
    for (const auto &kv : g_valWeights) {
        auto it = feats.find(kv.first);
        if (it != feats.end()) z += kv.second * it->second;
    }
    return z;
}

static void learnedCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();

        const auto base = stateFeats(gc);
        const double vBase = sigmoid(logitOf(base));

        int bestIdx = -1;
        double bestVal = g_learnedNeverSkip ? -1e18 : 0.0;   // 0.0 => skip unless a card has positive marginal value
        for (int i = 0; i < n; ++i) {
            const auto &c = r.cardRewards[rIdx][i];
            auto f = base;
            f["deckSize"] += 1;
            switch (c.getType()) {
                case CardType::ATTACK: f["nAttack"] += 1; break;
                case CardType::SKILL:  f["nSkill"]  += 1; break;
                case CardType::POWER:  f["nPower"]  += 1; break;
                case CardType::CURSE:  f["nCurse"]  += 1; break;
                case CardType::STATUS: f["nStatus"] += 1; break;
                default: break;
            }
            if (c.isUpgraded()) f["nUpgraded"] += 1;
            switch (c.getRarity()) {
                case CardRarity::COMMON:   f["nCommon"]   += 1; break;
                case CardRarity::UNCOMMON: f["nUncommon"] += 1; break;
                case CardRarity::RARE:     f["nRare"]     += 1; break;
                default: break;
            }
            f["obtainSum"] += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
            f["obtainAvg"] = f["obtainSum"] / f["deckSize"];

            const double val = sigmoid(logitOf(f)) - vBase;
            if (val > bestVal) { bestVal = val; bestIdx = i; }
        }
        search::GameAction(RT::CARD, rIdx, bestIdx >= 0 ? bestIdx : 5).execute(gc);
    }
}

// Whole run where the card-reward decision is the built-in weighted table
// (policyId 0), greedy argmax (1), the hand state-aware value function (2), or
// the learned logistic value function (3).
static RunResult runFullRunCards(std::uint64_t seed, int sims, int asc, int policyId, double skipRatio) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;                  // mirror stepRewardsPolicy ordering
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (policyId == 0)         agent.weightedCardRewardPolicy(gc);
            else if (policyId == 1)         greedyCardRewardPolicy(gc, skipRatio);
            else if (policyId == 2)         evalCardRewardPolicy(gc);
            else if (policyId == 3)         learnedCardRewardPolicy(gc);
            else if (policyId == 4)         fusedCardRewardPolicy(gc);
            else if (policyId == 5)         tableCardRewardPolicy(gc);
            else                            serverCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void cardBench(int sims, int nSeeds, int asc, double skipRatio, int onlyPolicy = -1) {
    std::cout << "card-policy A/B   seeds 0.." << nSeeds - 1 << "   ascension: " << asc
              << "   sims/decision: " << sims << "   greedy skipRatio: " << skipRatio
              << "   threads: " << numThreads() << "\n\n";
    if (!g_valLoaded) loadValueModel("build/value_model.txt");
    if (!g_cardAdvLoaded) loadCardAdvTable("build/card_adv_table.txt");
    const char *names[] = {"weighted-table", "greedy-argmax", "eval-function",
                           "learned-logistic", "eval+causal", "causal-table", "gbm-server"};
    for (int policyId = 0; policyId < 7; ++policyId) {
        if (onlyPolicy >= 0 && policyId != onlyPolicy) continue;
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunCards((std::uint64_t)s, sims, asc, policyId, skipRatio);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    names[policyId],
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// HEURISTIC PATHING: pick the map route by scoring each room and taking the
// child that leads to the best-scoring remaining path to the boss.
//
// Spec (from the player's intuition):
//   * elites & rest sites are great; elites more so the LATER you fight them
//     (you're stronger, and you get healed at act end anyway);
//   * shops are worth it only if you can afford them;
//   * fights build the deck and are good when you have HP, especially act 1;
//   * events balance out a fight-heavy path;
//   * in general take the HARDEST path you can still survive -- reward density
//     beats HP hoarding because the act-transition heals you.
//
// HP-awareness is implicit: the policy re-plans every floor with live curHp,
// and elite/monster values are gated by current HP, so a healthy hero routes
// into elites/fights and a hurt one routes to rests/events.
// ---------------------------------------------------------------------------
static double roomValue(Room r, int y, const GameContext &gc) {
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;
    const int act = gc.act;
    double v;
    switch (r) {
        case Room::ELITE: {
            const double base  = 14.0;             // relic + strong card/gold: top-value room
            const double later = 0.5 * y;          // prefer fighting elites later
            // HP gate, like monsters but demanding MORE health (elites are high-variance):
            // ramps 0 -> 1 as HP goes 40% -> 90% of max, so an elite is only worth
            // routing into when you're near-full. Below 40% it's ~worthless.
            const double gate  = std::clamp((hpFrac - 0.40) / 0.50, 0.0, 1.0);
            v = (base + later) * gate;
            break;
        }
        case Room::REST:
            v = 9.0 + (hpFrac < 0.5 ? 5.0 : 0.0);   // heal/upgrade; more valuable when hurt
            break;
        case Room::SHOP:
            v = gc.gold >= 120 ? 7.0 : gc.gold >= 75 ? 4.0 : 1.5;
            break;
        case Room::MONSTER: {
            const double actMul = act == 1 ? 1.0 : 0.55;   // fights build the deck, esp. act 1
            const double hpMul  = 0.4 + 0.9 * hpFrac;      // good when you have HP
            v = 3.2 * actMul * hpMul;
            break;
        }
        case Room::EVENT:
            v = 3.8;                                // wildcard; balances fight-heavy paths
            break;
        case Room::TREASURE:
            v = 6.0;                                // free relic
            break;
        default:
            return 0.0;                             // BOSS / NONE / INVALID (never modulated)
    }
    // V-informed deck-strength modulation (STS_VPATH): scale AGGRESSIVE rooms up
    // and RECOVERY rooms down when the value model thinks the deck is strong
    // (t_pathAggr > 0), and vice-versa. Neutral aggr (0) leaves the heuristic exact.
    if (g_vPath && t_pathAggr != 0.0) {
        const double a = g_vPathK * t_pathAggr;     // signed gain
        switch (r) {
            case Room::ELITE:   v *= (1.0 + a);        break;  // strong deck -> farm elites/relics
            case Room::MONSTER: v *= (1.0 + 0.75 * a); break;  // ... and fights (deck-building)
            case Room::REST:    v *= (1.0 - 0.75 * a); break;  // weak deck -> value recovery
            case Room::SHOP:    v *= (1.0 - 0.50 * a); break;
            case Room::EVENT:   v *= (1.0 - 0.25 * a); break;
            default: break;
        }
    }
    return v;
}

// Returns the child x-column to move into (== the map GameAction index).
static int chooseMapAction(const GameContext &gc) {
    const Map &map = *gc.map;

    // V-informed deck-strength: one V(state) query -> predicted final floor, turned
    // into an aggression signal in [-1,+1] via the act-boss anchor. Comfortably
    // clearing the act (predFloor >> bossFloor) => aggr>0 => farm elites/fights;
    // barely surviving => aggr<0 => route to recovery. Scale 8 floors ~= full swing.
    t_pathAggr = 0.0;
    if (g_vPath) {
        const double pf = vStateRaw(const_cast<GameContext &>(gc));
        if (pf > -1e8)   // server reachable
            t_pathAggr = std::clamp((pf - bossFloorForAct(gc.act)) / 8.0, -1.0, 1.0);
    }

    // Bottom-up DP: best[y][x] = best total room value from entering (x,y) to boss.
    static thread_local double best[15][7];
    for (int x = 0; x < 7; ++x) {
        best[14][x] = roomValue(map.getNode(x, 14).room, 14, gc);   // then the boss
    }
    for (int y = 13; y >= 0; --y) {
        for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.edgeCount == 0) { best[y][x] = -1e9; continue; }   // unused / dead node
            double bestChild = -1e18;
            for (int i = 0; i < n.edgeCount; ++i) {
                bestChild = std::max(bestChild, best[y + 1][n.edges[i]]);
            }
            best[y][x] = roomValue(n.room, y, gc) + bestChild;
        }
    }

    // Candidate children (mirrors getAllMapActions).
    const int childRow = gc.curMapNodeY + 1;
    int bestX = -1;
    double bestScore = -1e18;
    auto consider = [&](int x) {
        if (best[childRow][x] > bestScore) { bestScore = best[childRow][x]; bestX = x; }
    };
    if (gc.curMapNodeY == -1) {
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) consider(n.x);
    } else {
        const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < n.edgeCount; ++i) consider(n.edges[i]);
    }
    return bestX;
}

// Whole run where the map route is either the built-in random policy or our heuristic.
static RunResult runFullRunPath(std::uint64_t seed, int sims, int asc, bool heuristicPath) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (heuristicPath && gc.screenState == ScreenState::MAP_SCREEN
                   && gc.curMapNodeY < 14) {                    // y==14 is forced to boss
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void pathBench(int sims, int nSeeds, int asc) {
    std::cout << "pathing A/B   seeds 0.." << nSeeds - 1 << "   ascension: " << asc
              << "   mcts sims/decision: " << sims
              << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool heuristic = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunPath((std::uint64_t)s, sims, asc, heuristic);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    heuristic ? "heuristic-path" : "random-path",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// COMBINED POLICY: greedy never-skip drafting (exp 8) + heuristic pathing
// (exp 6b) together, vs. the stock baseline (built-in weighted table + random
// path). Everything else identical.
// ---------------------------------------------------------------------------
static RunResult runFullRunCombo(std::uint64_t seed, int sims, int asc, bool combo, double skipRatio) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (combo && gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);            // heuristic pathing
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (combo)                 evalCardRewardPolicy(gc, false);         // eval ranking, never skip
            else                            agent.weightedCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void comboBench(int sims, int nSeeds, int asc, double skipRatio) {
    std::cout << "combo A/B (greedy-draft + heuristic-path)   seeds 0.." << nSeeds - 1
              << "   ascension: " << asc << "   sims/decision: " << sims
              << "   skipRatio: " << skipRatio << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool combo = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunCombo((std::uint64_t)s, sims, asc, combo, skipRatio);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-22s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    combo ? "combo(eval+path)" : "baseline(table+rand)",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// BOSS-GATED ROLLOUT DRAFT: deaths cluster at act bosses, so for card rewards
// picked within a few rows of the upcoming boss we DON'T trust the myopic 1-ply
// server V. Instead, for each candidate (each card + skip) we copy the run,
// apply the pick, and roll the next few fights forward -- INCLUDING the boss --
// scoring by end-state (HP / win). The inner rollouts reuse rolloutChoice, which
// already respects fair-play and the V_combat leaf, so each is cheap. Falls back
// to the server pick when no hard fight is close.
//   The "how close is a hard fight" gate is deliberately factored out
// (rowsToHardFight, defined above) so the hard-fight set can later become DYNAMIC
// (wherever we die often); for now it is boss-only.
// ---------------------------------------------------------------------------
// Returns true iff it handled the card reward(s); false => caller uses server V.
static bool bossGatedDraftPolicy(GameContext &gc) {
    if (!g_bossDraft) return false;
    if (rowsToHardFight(gc) > g_bossDraftRows) return false;   // no hard fight close -> server pick
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx   = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e18;
        int    bestIdx   = 5;                                  // 5 == skip
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = (cand < nCards) ? cand : 5;
            double acc = 0;
            for (int f = 0; f < g_bossDraftFutures; ++f) {
                // seed depends only on f -> every candidate faces the SAME sampled
                // futures (common random numbers -> low-variance A/B between picks).
                std::uint64_t s = gc.seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1));
                acc += rolloutChoice(gc, rIdx, cardIdx, g_bossDraftN, g_bossDraftSims, s);
            }
            const double score = acc / g_bossDraftFutures;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    return true;
}

// Defined after the counterfactual runner below.  Keeping it out of that runner
// prevents recursive rollout drafting: only the live, immediate card pick is
// simulation-scored; subsequent simulated rewards use the ordinary server policy.
static bool actFightProbeDraftPolicy(GameContext &gc);
static bool actFightProbeAllOocPolicy(GameContext &gc);
static bool oocActionNNPolicy(GameContext &gc);

// ---------------------------------------------------------------------------
// REST-SITE A/B: best card policy (server V) + heuristic path, with the rest
// site driven either by the default agent heuristic or by the value policy
// (restVPolicy / upgradeSelectVPolicy). Isolates exactly the heal/upgrade change.
// Requires v_server.py running (server card picks + rest queries).
// ---------------------------------------------------------------------------
static RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV) {
    vDisconnect();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    PathHistory path;                // pv* features for V queries (train/serve parity)
    t_pathActionUses = 0;
    t_actFightProbeDecisionIdx = 0;
    t_curPath = &path;
    bool clearedStopActBoss = false;
    int fightsLost = 0, fightsTotal = 0, deathCombat = -1, deathEncounter = -1;
    auto t0 = std::chrono::steady_clock::now();
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            search::g_potionKeepValue = potionKeepValue(gc);           // dynamic potion-saving
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) { ++fightsLost; if (deathCombat < 0) { deathCombat = fightsTotal; deathEncounter = (int)bc.encounter; } }
            bc.exitBattle(gc);
            if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                break;
            }
        } else if (oocActionNNPolicy(gc)) {
            // The action-conditioned next-combat NN is reapplied at every OOC
            // decision, giving a cheap multi-step policy over the whole run.
        } else if (actFightProbeAllOocPolicy(gc)) {
            // Every legal out-of-combat action is ranked by the all-act fight
            // rollout.  The copied continuations themselves use the normal OOC
            // policy, preventing recursive exponential search.
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            if (g_pathV) pathVPolicy(gc);                              // model-driven pathing
            else search::GameAction(chooseMapAction(gc)).execute(gc);  // heuristic pathing
        } else if (g_eventV && gc.screenState == ScreenState::EVENT_SCREEN
                   && gc.curEvent != Event::NEOW && eventVPolicy(gc)) {
            // model-driven event choice
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;                          // take non-card rewards first,
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);   // else the screen
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);  // never clears
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (actFightProbeDraftPolicy(gc)) { /* all-act, encounter-weighted rollout draft */ }
            else if (bossGatedDraftPolicy(gc)) { /* rollout draft near a hard fight */ }
            else if (oocOnePlyCardRewardPolicy(gc)) { /* one-ply NN card pick (Phase 5) */ }
            else                            serverCardRewardPolicy(gc);  // best card policy (server V)
        } else if (shopV && gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);                                            // V-knapsack shop buys
        } else if (shopV && inRemoveSelect) {
            removeSelectVPolicy(gc);                                    // shop removal target
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // win-rate rest policy (heal vs upgrade in P(win) units)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);                                 // smith target by P(win)
        } else if (restV && gc.screenState == ScreenState::REST_ROOM && restVPolicy(gc)) {
            // handled by the value policy
        } else if (restV && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectVPolicy(gc);                                    // smith target
        } else if (g_bossRelicV && gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            bossRelicVPolicy(gc);                                       // boss relic by P(win)
        } else if (g_neowV && gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::NEOW) {
            neowVPolicy(gc);                                           // Neow bonus by P(win)
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    const RunResult result { clearedStopActBoss || gc.outcome == GameOutcome::PLAYER_VICTORY,
                              gc.floorNum, gc.act, gc.curHp, gc.maxHp,
                              fightsLost,
                              std::chrono::duration<double>(t1 - t0).count(),
                              deathCombat, deathEncounter };
    vDisconnect();
    return result;
}

// ---------------------------------------------------------------------------
// RUN TRACE: replay ONE seed with the deployed OOC policy and print a
// human-readable line per MAP NODE (what it was, what we fought / which event,
// and the resulting state: HP, gold, deck delta, deck, relics, potions). For
// eyeballing the agent's decisions against human game knowledge. This is a
// DIAGNOSTIC trace, not a mirror of runFullRunOOC: it logs but does not use
// some event/treasure scores and omits some fallthrough policy layers.
// ---------------------------------------------------------------------------
static std::string tr_deck(const GameContext &gc) {
    std::map<std::string,int> m;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ++m[n]; }
    std::string s;
    for (auto &kv : m) { s += kv.first; if (kv.second > 1) s += " x" + std::to_string(kv.second); s += ", "; }
    return s;
}
static std::multiset<std::string> tr_deckMs(const GameContext &gc) {
    std::multiset<std::string> ms;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ms.insert(n); }
    return ms;
}
static std::string tr_relics(const GameContext &gc) {
    std::string s;
    for (const auto &ri : gc.relics.relics) { s += sts::relicNames[(int)ri.id]; s += ", "; }
    return s.empty() ? "-" : s;
}
static std::string tr_potions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        s += sts::getPotionName(gc.potions[i]); s += ", ";
    }
    return s.empty() ? "-" : s;
}
static std::string tr_event(Event e) {
    // enum-order names (matches include/constants/Events.h)
    static const char *const kEventNames[] = {
        "INVALID","MONSTER","REST","SHOP","TREASURE","NEOW","Ominous Forge","Pleading Vagrant",
        "Ancient Writing","Old Beggar","Big Fish","Bonfire Spirits","Colosseum","Cursed Tome",
        "Dead Adventurer","Designer in-Spire","Augmenter","Duplicator","Face Trader","Falling",
        "Forgotten Altar","The Divine Fountain","Ghosts","Golden Idol","Golden Shrine","Wing Statue",
        "Knowing Skull","Lab","The Ssssserpent","Living Wall","Masked Bandits","Match and Keep",
        "Mindbloom","Hypnotizing Mushrooms","Mysterious Sphere","The Nest","Nloth","Note For Yourself",
        "Purifier","Scrap Ooze","Secret Portal","Sensory Stone","Shining Light","The Cleric","The Joust",
        "The Library","The Mausoleum","The Moai Head","The Woman in Blue","Tomb of Lord Red Mask",
        "Transmogrifier","Upgrade Shrine","Vampires","We Meet Again","Wheel of Change","Winding Halls",
        "World of Goop" };
    const int i = (int)e;
    return (i >= 0 && i < (int)(sizeof(kEventNames)/sizeof(*kEventNames))) ? kEventNames[i]
                                                                           : "Event#" + std::to_string(i);
}
static std::string tr_deckDelta(const std::multiset<std::string> &prev, const std::multiset<std::string> &cur) {
    std::string s;
    for (const auto &n : cur) if (cur.count(n) > prev.count(n) && s.find("+" + n + " ") == std::string::npos) {
        int d = (int)cur.count(n) - (int)prev.count(n);
        s += "+" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    for (const auto &n : prev) if (prev.count(n) > cur.count(n) && s.find("-" + n + " ") == std::string::npos) {
        int d = (int)prev.count(n) - (int)cur.count(n);
        s += "-" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    return s;
}

// Log each pending card reward's OPTIONS + the model's marginal-V (final-floor units,
// via the server "M" op) so drafts can be graded, not just the pick. skip bar = g_cardSkipThresh.
// When the OOC action NN is active (STS_OOC_ACTION_NN=1), also query its OA endpoint and
// show the NN's utility score for each card.
static void tr_logDraft(GameContext &gc) {
    // The "M" marginals op is server-only. Skip the draft log cleanly when no
    // server is reachable (same vConnect()<0 fail-fast pattern as vTransact),
    // instead of letting vRequestLine retry ~50x per card reward.
    if (vConnect() < 0) return;
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = 0; rIdx < r.cardRewardCount; ++rIdx) {
        auto &cr = r.cardRewards[rIdx];
        if (cr.size() == 0) continue;

        // V_rich marginals (server M op)
        std::string req = "M;";
        for (int i = 0; i < cr.size(); ++i) { if (i) req += ','; req += std::to_string((int)cr[i].getId()); }
        req += ';'; req += vFeatCsv(gc);
        std::string resp = vSendRecv(req);
        std::vector<double> marg; { std::istringstream is(resp); double v; while (is >> v) marg.push_back(v); }

        // NN scores for each card option + skip
        std::vector<double> nnScores;
        if (g_oocCheckpointNet.ok) {
            const std::vector<float> state = richFeatureVec(gc);
            using RT = search::GameAction::RewardsActionType;
            for (int i = 0; i < cr.size(); ++i) {
                std::uint32_t abits = search::GameAction(RT::CARD, rIdx, i).bits;
                nnScores.push_back(g_oocCheckpointNet.predict(state.data(), abits, (int)gc.screenState, gc.act));
            }
            std::uint32_t sbits = search::GameAction(RT::SKIP).bits;
            nnScores.push_back(g_oocCheckpointNet.predict(state.data(), sbits, (int)gc.screenState, gc.act));
        }

        // One-ply strategic V(s') for each card option + the CARD(rIdx,5) skip
        std::vector<double> oneplyScores;
        if (g_oocStrategicNet.ok) {
            using RT = search::GameAction::RewardsActionType;
            for (int i = 0; i < cr.size(); ++i) {
                GameContext probe = gc;
                search::GameAction(RT::CARD, rIdx, i).execute(probe);
                oneplyScores.push_back(g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                                      (int)probe.screenState));
            }
            GameContext probe = gc;
            search::GameAction(RT::CARD, rIdx, 5).execute(probe);
            oneplyScores.push_back(g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                                  (int)probe.screenState));
        }

        std::string line = "         draft options [skip if <" + std::to_string(g_cardSkipThresh) + "]: ";
        int best = -1; double bestv = -1e18;
        for (int i = 0; i < cr.size(); ++i) {
            double m = i < (int)marg.size() ? marg[i] : 0.0;
            if (m > bestv) { bestv = m; best = i; }
            std::string nm = cr[i].getName(); if (cr[i].isUpgraded()) nm += "+";
            char buf[64];
            if (i < (int)nnScores.size()) {
                std::snprintf(buf, sizeof(buf), "%s(V:%+.2f NN:%.3f)", nm.c_str(), m, nnScores[i]);
                line += buf;
                if (i < (int)oneplyScores.size())
                    line += " 1ply:" + std::to_string(oneplyScores[i]);
                line += "  ";
            } else {
                std::snprintf(buf, sizeof(buf), "%s(%+.2f)  ", nm.c_str(), m);
                line += buf;
            }
        }
        line += "-> V_rich picks ";
        line += (bestv < g_cardSkipThresh) ? "SKIP" : (std::string)(cr[best].getName());
        if (!nnScores.empty()) {
            int nnBest = 0;
            for (int i = 1; i < (int)nnScores.size(); ++i)
                if (nnScores[i] > nnScores[nnBest]) nnBest = i;
            line += "  NN: skip=" + std::to_string(nnScores.back()) + " picks ";
            line += (nnBest < cr.size()) ? (std::string)(cr[nnBest].getName()) : "SKIP";
            if (nnBest > 0 && nnBest != best) line += " [DISAGREE]";
        }
        std::printf("%s\n", line.c_str());
    }
}

// Show NN scores for all legal OOC actions with action descriptions.
static void tr_logOocActions(const char *label, GameContext &gc) {
    if (!g_oocCheckpointNet.ok) return;
    const std::vector<float> state = richFeatureVec(gc);
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return;
    double best = -1e100; int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        double s = g_oocCheckpointNet.predict(state.data(), actions[i].bits, (int)gc.screenState, gc.act);
        std::string desc;
        if (gc.screenState == ScreenState::REST_ROOM) {
            int idx = actions[i].getIdx1();
            if (idx == 0) desc = "HEAL";
            else if (idx == 1) {
                int smithIdx = actions[i].getIdx2();
                if (smithIdx >= 0 && smithIdx < (int)gc.deck.cards.size())
                    desc = std::string("smith:") + gc.deck.cards[smithIdx].getName();
                else desc = "smith";
            } else if (idx == 2) desc = "DIG";
            else if (idx == 3) desc = "LIFT";
            else if (idx == 4) desc = "TOKE";
            else desc = "rest#" + std::to_string(idx);
        } else {
            desc = "#" + std::to_string(i);
        }
        std::printf("         [NN %s] %s = %.3f\n", label, desc.c_str(), s);
        if (s > best) { best = s; bestIdx = i; }
    }
    std::printf("         [NN %s] -> picks #%d (%.3f)\n", label, bestIdx, best);
}

// Refight the CURRENT battle K times from a copy of the pre-fight state, reseeding the
// battle RNGs each time so draw order + enemy moves vary -> separates a bad fight model
// from an unlucky single sample. Prints end-HP distribution, death rate, potions used.
static void tr_refight(const GameContext &gc, int sims, int K) {
    std::vector<int> hp; int deaths = 0, potUsed = 0;
    const int potBefore = gc.potionCount;
    for (int k = 0; k < K; ++k) {
        GameContext g2 = gc;
        BattleContext bc; bc.init(g2);
        bc.shuffleRng      = sts::Random(gc.seed * 2654435761u + k * 40503u + 1);
        bc.aiRng           = sts::Random(gc.seed * 2246822519u + k * 668265263u + 7);
        bc.cardRandomRng   = sts::Random(gc.seed * 3266489917u + k * 374761393u + 13);
        search::ScumSearchAgent2 ag; ag.simulationCountBase = fightSims(gc, sims);
        ag.rng = std::default_random_engine(gc.seed + 999u + k);
        ag.playoutBattle(bc);
        bc.exitBattle(g2);
        const bool died = g2.curHp <= 0 || g2.outcome == GameOutcome::PLAYER_LOSS;
        if (died) ++deaths; hp.push_back(std::max(0, g2.curHp));
        potUsed += potBefore - g2.potionCount;
    }
    std::sort(hp.begin(), hp.end());
    double mean = 0; for (int h : hp) mean += h; mean /= std::max(1, (int)hp.size());
    std::printf("         >> REFIGHT x%d: deaths %d/%d  endHP min %d / med %d / mean %.1f / max %d"
                "  avg potions used %.2f (had %d)\n",
                K, deaths, K, hp.front(), hp[hp.size()/2], mean, hp.back(),
                (double)potUsed / std::max(1, K), potBefore);
}

static void runTraceRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;

    std::printf("=== RUN TRACE seed %llu  asc %d  sims %d%s ===\n",
                (unsigned long long)seed, asc, sims, search::g_fairPlay ? "  [fair-play]" : "");
    std::printf("!!! DIAGNOSTIC TRACE: does NOT exactly reproduce runFullRunOOC policy !!!\n");

    const int refightFloor = std::getenv("STS_REFIGHT_FLOOR") ? std::atoi(std::getenv("STS_REFIGHT_FLOOR")) : -1;
    const int refightN     = std::getenv("STS_REFIGHT_N")     ? std::atoi(std::getenv("STS_REFIGHT_N"))     : 20;
    const int combatLogFloor = std::getenv("STS_COMBAT_LOG")  ? std::atoi(std::getenv("STS_COMBAT_LOG"))    : -1;
    int clLastTurn = -1;
    // Per-decision combat logger (via the g_onCombatDecision hook): one line per in-fight
    // decision -> turn, energy, player HP/block/str/dex, each alive monster's HP/block/intent, hand.
    auto combatLog = [&clLastTurn](const BattleContext &bc) {
        if (bc.turn != clLastTurn) { std::printf("   --- Turn %d ---\n", bc.turn); clLastTurn = bc.turn; }
        auto ps = [&](PlayerStatus s){ auto it = bc.player.statusMap.find(s); return it != bc.player.statusMap.end() ? (int)it->second : 0; };
        std::string mon;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const Monster &m = bc.monsters.arr[i];
            if (m.curHp <= 0 || !m.isTargetable()) continue;
            DamageInfo di = m.getMoveBaseDamage(bc);
            std::string intent = monsterMoveStrings[(int)m.moveHistory[0]];
            if (di.damage > 0) { intent += "(" + std::to_string(di.damage);
                                 if (di.attackCount > 1) intent += "x" + std::to_string(di.attackCount);
                                 intent += ")"; }
            char buf[160];
            std::snprintf(buf, sizeof(buf), "%s HP%d+%d[%s] ", m.getName(), m.curHp, m.block, intent.c_str());
            mon += buf;
        }
        std::string hand;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            std::string n = bc.cards.hand[i].getName(); if (bc.cards.hand[i].isUpgraded()) n += "+";
            hand += n; hand += " ";
        }
        std::printf("   [E%d] you HP%d+%dblk Str%d Dex%d Weak%d | %s| hand: %s\n",
                    bc.player.energy, bc.player.curHp, bc.player.block,
                    ps(PlayerStatus::STRENGTH), ps(PlayerStatus::DEXTERITY), ps(PlayerStatus::WEAK),
                    mon.c_str(), hand.c_str());
    };
    bool nodeActive = false; std::string label, desc; int preHp = gc.curHp;
    std::multiset<std::string> prevDeck = tr_deckMs(gc);

    auto flush = [&]() {
        if (!nodeActive) return;
        auto curDeck = tr_deckMs(gc);
        std::string delta = tr_deckDelta(prevDeck, curDeck);
        std::printf("[F%-2d A%d] %-9s %-22s  HP %d/%d (%+d)  gold %d\n",
                    gc.floorNum, gc.act, label.c_str(), desc.c_str(),
                    gc.curHp, gc.maxHp, gc.curHp - preHp, gc.gold);
        if (!delta.empty())          std::printf("         change: %s\n", delta.c_str());
        std::printf("         deck(%d): %s\n", (int)gc.deck.size(), tr_deck(gc).c_str());
        std::printf("         relics: %s\n", tr_relics(gc).c_str());
        std::printf("         potions: %s\n", tr_potions(gc).c_str());
        prevDeck = curDeck; preHp = gc.curHp; nodeActive = false; label.clear(); desc.clear();
    };
    auto roomName = [](Room r) -> const char * {
        switch (r) { case Room::MONSTER: return "MONSTER"; case Room::ELITE: return "ELITE";
            case Room::BOSS: case Room::BOSS_TREASURE: return "BOSS"; case Room::REST: return "REST";
            case Room::SHOP: return "SHOP"; case Room::TREASURE: return "TREASURE";
            case Room::EVENT: return "EVENT"; default: return "?"; }
    };

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            agent.simulationCountBase = fightSims(gc, sims);
            search::g_potionKeepValue = potionKeepValue(gc);
            BattleContext bc; bc.init(gc);
            flush();  // a battle always begins a fresh node (fixes forced rest/event -> boss merge)
            nodeActive = true; label = roomName(gc.curRoom);
            desc = sts::monsterEncounterStrings[(int)bc.encounter];
            if (gc.floorNum == refightFloor) {
                std::printf("[F%-2d A%d] %-9s %-22s  (pre-fight HP %d/%d)\n",
                            gc.floorNum, gc.act, label.c_str(), desc.c_str(), gc.curHp, gc.maxHp);
                tr_refight(gc, sims, refightN);
            }
            const bool doLog = gc.floorNum == combatLogFloor;
            if (doLog) {
                std::printf("[F%d A%d] === COMBAT LOG: %s (HP %d/%d) ===\n",
                            gc.floorNum, gc.act, desc.c_str(), gc.curHp, gc.maxHp);
                clLastTurn = -1; search::g_onCombatDecision = combatLog;
            }
            agent.playoutBattle(bc);
            if (doLog) { search::g_onCombatDecision = nullptr;
                         std::printf("   === end combat: you HP%d, %s ===\n", bc.player.curHp,
                                     bc.player.curHp > 0 ? "WON" : "DIED"); }
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            flush();
            tr_logOocActions("map", gc);
            if (!oocActionNNPolicy(gc))
                search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
            if (!nodeActive) { flush(); nodeActive = true; label = "EVENT"; desc = tr_event(gc.curEvent); }
            tr_logOocActions("event", gc);
            agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "REST"; }
            tr_logOocActions("rest", gc);
            if (!oocActionNNPolicy(gc)) {
                if (g_restWin && restWinPolicy(gc)) {}
                else agent.stepOutOfCombatPolicy(gc);
            }
        } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "TREASURE"; }
            tr_logOocActions("treasure", gc);
            agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "SHOP"; }
            tr_logOocActions("shop", gc);
            if (!oocActionNNPolicy(gc))
                shopVPolicy(gc);
        } else if (inRemoveSelect) {
            if (!oocActionNNPolicy(gc))
                removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else { tr_logDraft(gc); if (!oocActionNNPolicy(gc)) { if (!oocOnePlyCardRewardPolicy(gc)) serverCardRewardPolicy(gc); } }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            tr_logOocActions("upgrade", gc);
            if (!oocActionNNPolicy(gc))
                upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    flush();
    std::printf("=== %s  final floor %d act %d  HP %d/%d ===\n",
                gc.outcome == GameOutcome::PLAYER_VICTORY ? "VICTORY" : "DEATH",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp);
}

// A/B one out-of-combat policy toggle (rest or shop) against the default agent,
// holding server card picks + heuristic path fixed.
static void oocBench(const char *label, int sims, int nSeeds, int asc, bool isShop) {
    std::cout << label << "   seeds 0.." << nSeeds - 1
              << "   ascension: " << asc << "   sims/decision: " << sims
              << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool on = (mode == 1);
        const bool restV = on && !isShop, shopV = on && isShop;
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunOOC((std::uint64_t)s, sims, asc, restV, shopV);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        const char *name = isShop ? (on ? "shop-V(knapsack)" : "shop-agent(default)")
                                  : (on ? "rest-V(heal/upgrade)" : "rest-agent(default)");
        std::printf("%-22s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    name, 100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// Single-arm run (server cards + heuristic path, no shop/rest V) at the current
// STS_SKIP_THR. Isolates the card-skip threshold; sweep by re-invoking with env.
static void skipBench(int sims, int nSeeds, int asc) {
    std::cout << "card-skip run (server-cards + heuristic-path)   seeds 0.." << nSeeds - 1
              << "   ascension: " << asc << "   sims/decision: " << sims
              << "   skipThresh: " << g_cardSkipThresh << "   threads: " << numThreads() << "\n";
    int wins = 0; long long floor = 0, hp = 0; double sec = 0;
    auto wall0 = std::chrono::steady_clock::now();
    #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        RunResult r = runFullRunOOC((std::uint64_t)s, sims, asc, false, false);
        wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    std::printf("skip=%-8.3g  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                g_cardSkipThresh, 100.0 * wins / nSeeds, (double)floor / nSeeds,
                (double)hp / nSeeds, sec / nSeeds, wall);
}

// Single-arm readout of the CURRENT BEST out-of-combat stack: native floor-V
// card picks (skip@g_cardSkipThresh, default -0.5) + heuristic path + shop-V,
// with the default win-rate rest layer (g_restWin, heal-vs-upgrade in P(win)
// units) and optional legacy rest-V via STS_REST_V=1. Use this as the baseline
// arm for new experiments. Serverless under default native OOC.
static void bestBench(int sims, int nSeeds, int asc, std::uint64_t seedOffset = 0,
                      const std::string &resultsFile = "") {
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    std::cout << "BEST stack config: skip@" << g_cardSkipThresh
              << "  rest=" << (g_restWin ? "win-rate" : "default")
              << (restV ? "+legacy-rest-V" : "")
              << "  shop-V=ON  path=" << (g_pathV ? "model-driven" : "heuristic")
              << "  native-OOC=" << (g_nativeOoc ? "ON" : "OFF")
              << "  searcher=" << (search::g_useSearcher3 ? "Searcher3" : "Searcher2")
              << (search::g_fairPlay ? "  fair-play" : "")
              << "  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  asc " << asc << "  sims " << sims << "  threads " << numThreads() << "\n";
    std::cout << "BEST models: floor=" << (g_floorNet.ok ? g_floorNet.path : "MISSING")
              << "  win=" << (g_winNet.ok ? g_winNet.path : "not loaded")
              << "  combatVNet=" << (search::g_useVNet ? "ON" : "off")
              << "  policyNet=" << (search::g_usePolicyNet ? "ON" : "off")
              << "  PVNet=" << (search::g_usePVNet ? "ON" : "off")
              << "  distVNet=" << (search::g_useDistVNet ? "ON" : "off") << "\n";
    // Optional per-seed output powers the adaptive self-play gate. Rows are
    // flushed as runs finish, so the dashboard gets live progress and a killed
    // benchmark leaves valid results. The caller owns truncation; batches append.
    std::ofstream results;
    if (!resultsFile.empty()) {
        results.open(resultsFile, std::ios::app);
        if (results.tellp() == 0) {
            results << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n";
            results.flush();
        }
    }
    int wins = 0; long long floor = 0, hp = 0; double sec = 0;
    BenchProgress prog(nSeeds, "BEST");
    auto wall0 = std::chrono::steady_clock::now();
    // Do not create a one-iteration outer OpenMP team when the all-OOC oracle
    // is asked to parallelize its branches; that would otherwise serialize the
    // nested region. Multi-seed benches keep the proven outer parallelism.
    if (nSeeds == 1 && g_actFightProbeParallelBranches) {
        const std::uint64_t seed = seedOffset;
        RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
        wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        if (results.is_open()) {
            results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                    << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                    << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
            results.flush();
        }
        prog.tick(r.won, r.floor, r.hpEnd);
    } else {
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            const std::uint64_t seed = seedOffset + (std::uint64_t)s;
            RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
            #pragma omp critical(bestbench_results)
            if (results.is_open()) {
                results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                        << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                        << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
                results.flush();
            }
            prog.tick(r.won, r.floor, r.hpEnd);
        }
    }
    prog.done();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    std::printf("BEST                    win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                100.0 * wins / nSeeds, (double)floor / nSeeds, (double)hp / nSeeds, sec / nSeeds, wall);
}

static void restBench(int sims, int nSeeds, int asc) {
    oocBench("rest-site A/B (server-cards + heuristic-path)", sims, nSeeds, asc, false);
}
static void shopBench(int sims, int nSeeds, int asc) {
    oocBench("shop A/B (server-cards + heuristic-path)", sims, nSeeds, asc, true);
}

// A/B all-default vs (rest-V + shop-V together), holding server cards + path fixed.
static void allOOCBench(int sims, int nSeeds, int asc) {
    std::cout << "OOC A/B (rest-V + shop-V vs all-default; server-cards + heuristic-path)   seeds 0.."
              << nSeeds - 1 << "   ascension: " << asc << "   sims/decision: " << sims
              << "   healThresh: " << g_restVThreshold << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool on = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunOOC((std::uint64_t)s, sims, asc, on, on);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-22s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    on ? "rest+shop-V" : "all-default",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// DATA GENERATION for an offline value function V(state) ~= P(win). At each
// card-reward decision we log a feature vector of the current run state; the
// label is the eventual outcome of that run (Monte-Carlo return). Card picks
// use eps-greedy exploration so the logged decks are diverse.
// ---------------------------------------------------------------------------
// scalar feature names only; datagen appends d0..d(kNumCardIds-1) then won,finalFloor
static const char *kFeatureHeader =
    "ascension,act,floor,curHp,maxHp,gold,deckSize,nAttack,nSkill,nPower,nCurse,"
    "nStatus,nUpgraded,nStarter,nCommon,nUncommon,nRare,obtainSum,obtainAvg,nRelics";

// deck as per-card-id counts d0..d(kNumCardIds-1) — makes value models deck-aware
// (able to express card synergies), shared by datagen and causalgen.
static const int kNumCardIds = 372;

static std::string deckCountsCsv(const GameContext &gc) {
    std::array<int, kNumCardIds> cnt{};
    for (const auto &c : gc.deck.cards) {
        int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) ++cnt[id];
    }
    std::ostringstream o;
    for (int i = 0; i < kNumCardIds; ++i) { if (i) o << ','; o << cnt[i]; }
    return o.str();
}

static std::string featureRow(const GameContext &gc) {
    int nAtk=0,nSkill=0,nPow=0,nCurse=0,nStatus=0,nUpg=0,nStarter=0,nCommon=0,nUncommon=0,nRare=0;
    long obtainSum = 0;
    for (const auto &c : gc.deck.cards) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::SKILL:  ++nSkill; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::CURSE:  ++nCurse; break;
            case CardType::STATUS: ++nStatus; break;
            default: break;
        }
        if (c.isUpgraded()) ++nUpg;
        if (c.isStarterStrikeOrDefend()) ++nStarter;
        switch (c.getRarity()) {
            case CardRarity::COMMON:   ++nCommon; break;
            case CardRarity::UNCOMMON: ++nUncommon; break;
            case CardRarity::RARE:     ++nRare; break;
            default: break;
        }
        obtainSum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    const int deckSize = gc.deck.size();
    const double obtainAvg = deckSize ? (double)obtainSum / deckSize : 0.0;
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ','
      << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ',' << deckSize << ','
      << nAtk << ',' << nSkill << ',' << nPow << ',' << nCurse << ',' << nStatus << ','
      << nUpg << ',' << nStarter << ',' << nCommon << ',' << nUncommon << ',' << nRare << ','
      << obtainSum << ',' << obtainAvg << ',' << (int)gc.relics.relics.size();
    return o.str();
}

// ---------------------------------------------------------------------------
// RICH datagen v2: a comprehensive per-decision run-state snapshot for training
// value functions that are relic-aware, upgrade-aware, potion-aware, future-fight
// -aware, and path-aware. One row per card-reward decision; label = run outcome.
// Blocks: core, keys, potions-meta, future-fights/act, path-history, bottled
// cards, deck totals d{id}, deck upgrades u{id}, relics r{id} (0=absent /
// 1+counter), potions pot{id} (multi-hot). Wide but sparse. Append-capable.
// ---------------------------------------------------------------------------
static const int kNumRelics  = 181;   // RelicId enum cardinality
static const int kNumPotions = 48;    // Potion enum cardinality

// Accumulates room types visited so far this run (for path evaluation). Updated
// each loop iteration; counts a node once, when the map position first changes.
static std::string richHeader() {
    std::ostringstream h;
    h << "seed,ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor,"
         "blueKey,greenKey,redKey,potionCount,potionCapacity,"
         "bossId,nextEliteId,nextFight0,nextFight1,nextFight2,remElites,remFights,monOffset,eliteOffset,"
         "pvShop,pvRest,pvEvent,pvElite,pvMonster,pvTreasure,"
         "bottledAtkId,bottledSkillId,bottledPowId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    for (int i = 0; i < kNumCardIds; ++i) h << ",u" << i;
    for (int i = 0; i < kNumRelics;  ++i) h << ",r" << i;
    for (int i = 0; i < kNumPotions; ++i) h << ",pot" << i;
    h << ",fmDElite,fmDRest,fmDShop,fmDBoss,fmCElite,fmCRest,fmCShop,fmCEvent,fmCMonster,fmCTreasure";
    h << ",curMapX,curMapY";
    h << ",won,finalFloor,endHp";
    return h.str();
}

// State portion of a row (no seed prefix, no labels — those are added at run end).
static std::string richRow(const GameContext &gc, const PathHistory &path) {
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case CardType::ATTACK: botAtk = id; break;
                case CardType::SKILL:  botSkill = id; break;
                case CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);  // presence + counter
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const int nextElite = gc.eliteMonsterListOffset < gc.eliteMonsterList.size()
                        ? (int)gc.eliteMonsterList[gc.eliteMonsterListOffset] : 0;
    auto nf = [&](int k) -> int {
        const int idx = gc.monsterListOffset + k;
        return idx < gc.monsterList.size() ? (int)gc.monsterList[idx] : 0;
    };
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
      << gc.gold << ',' << gc.deck.size() << ',' << gc.potionChance << ',' << gc.cardRarityFactor << ','
      << (gc.blueKey ? 1 : 0) << ',' << (gc.greenKey ? 1 : 0) << ',' << (gc.redKey ? 1 : 0) << ','
      << gc.potionCount << ',' << gc.potionCapacity << ','
      << (int)gc.boss << ',' << nextElite << ',' << nf(0) << ',' << nf(1) << ',' << nf(2) << ','
      << (gc.eliteMonsterList.size() - gc.eliteMonsterListOffset) << ','
      << (gc.monsterList.size() - gc.monsterListOffset) << ','
      << gc.monsterListOffset << ',' << gc.eliteMonsterListOffset << ','
      << path.roomVisits[(int)Room::SHOP]  << ',' << path.roomVisits[(int)Room::REST]     << ','
      << path.roomVisits[(int)Room::EVENT] << ',' << path.roomVisits[(int)Room::ELITE]    << ','
      << path.roomVisits[(int)Room::MONSTER] << ',' << path.roomVisits[(int)Room::TREASURE] << ','
      << botAtk << ',' << botSkill << ',' << botPow;
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << d[i];
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << u[i];
    for (int i = 0; i < kNumRelics;  ++i) o << ',' << r[i];
    for (int i = 0; i < kNumPotions; ++i) o << ',' << pot[i];
    const FwdMap fm = forwardMapFeatures(gc);   // forward-map (appended last -> old models unaffected)
    o << ',' << fm.dElite << ',' << fm.dRest << ',' << fm.dShop << ',' << fm.dBoss
      << ',' << fm.cElite << ',' << fm.cRest << ',' << fm.cShop << ',' << fm.cEvent
      << ',' << fm.cMonster << ',' << fm.cTreasure;
    // Map position. Combined with seed+act (also stored) the FULL map graph is deterministically
    // reconstructable (see the `dumpmap` mode) -> the eventual GNN gets the whole node+edge structure
    // with NO per-row bloat. Trees ignore these; harmless.
    o << ',' << gc.curMapNodeX << ',' << gc.curMapNodeY;
    return o.str();
}

// Full rich feature vector for a V query — identical schema/order to richRow() so
// training (vrich.csv) and serving match exactly. Uses the current run's path
// history when set (t_curPath), else an empty one (pv* = 0).
static std::string vFeatCsv(const GameContext &gc) {
    static thread_local PathHistory emptyPath;
    return richRow(gc, t_curPath ? *t_curPath : emptyPath);
}

// Rank every legal OOC action in one server request.  The model predicts the
// next-combat win probability and surviving HP fraction; the training score
// used for action selection is the same 10*P(win)+expected HP objective used
// by the offline transfer check.
static bool oocActionNNPolicy(GameContext &gc) {
    if (!g_oocActionNN || gc.act < 1 || gc.act > 3) return false;
    const auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;

    // Native checkpoint-distilled inference (no server)
    if (g_oocCheckpointNet.ok) {
        const std::vector<float> state = richFeatureVec(gc);
        double best = -1e100;
        int bestIdx = -1;
        for (int i = 0; i < (int)actions.size(); ++i) {
            const double score = g_oocCheckpointNet.predict(
                state.data(), actions[i].bits, (int)gc.screenState, gc.act);
            if (score > best) { best = score; bestIdx = i; }
        }
        if (bestIdx < 0) return false;
        actions[bestIdx].execute(gc);
        return true;
    }

    // Server fallback
    std::ostringstream req;
    req << "OA;";
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) req << ',';
        req << actions[i].bits;
    }
    req << ';' << (int)gc.screenState << ';' << gc.act << ';' << vFeatCsv(gc) << '\n';
    const std::string resp = vTransact(req.str());
    std::istringstream in(resp);
    double best = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        std::string tok;
        if (!(in >> tok)) break;
        const auto comma = tok.find(',');
        if (comma == std::string::npos) break;
        const double pwin = std::atof(tok.substr(0, comma).c_str());
        const double hpFrac = std::atof(tok.substr(comma + 1).c_str());
        const double score = 10.0 * pwin + hpFrac * gc.maxHp;
        if (score > best) { best = score; bestIdx = i; }
    }
    if (bestIdx < 0) return false;
    actions[bestIdx].execute(gc);
    return true;
}

// One-ply post-action value search for CARD REWARD decisions (Phase 5, 5.5.1).
// Every legal reward action is applied to a copied GameContext and the
// successor state is scored with the native strategic value head V(s'); the
// best action is executed only when its margin over the runner-up meets the
// gate (STS_OOC_STRATEGIC_MARGIN), otherwise the heuristic card policy stays
// in charge. Greedy un-gated deployment is a recorded failure mode (EXPERIMENTS
// §66m), so the gate is mandatory.
static bool oocOnePlyCardRewardPolicy(GameContext &gc) {
    if (!g_oocStrategicNet.ok) return false;
    if (gc.screenState != ScreenState::REWARDS) return false;
    auto &r = gc.info.rewardsContainer;
    if (r.cardRewardCount == 0) return false;
    using RT = search::GameAction::RewardsActionType;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    // The baseline skips a group via CARD(rIdx,5), which the enumerator omits.
    const int rIdx = r.cardRewardCount - 1;
    const search::GameAction skipCard(RT::CARD, rIdx, 5);
    bool have = false;
    for (const auto &a : actions) if (a.bits == skipCard.bits) { have = true; break; }
    if (!have) actions.push_back(skipCard);

    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext probe = gc;
        actions[i].execute(probe);
        const double v = g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                        (int)probe.screenState);
        if (v > best) { second = best; best = v; bestIdx = i; }
        else if (v > second) second = v;
    }
    if (bestIdx < 0 || best - second < g_oocStrategicMargin) return false;
    actions[bestIdx].execute(gc);
    return true;
}

struct OocCounterfactualResult {
    double won;
    double floor;
    double hp;
};

// Direct near-term survival supervision for out-of-combat action values.  These
// are deliberately *outcomes of the real counterfactual continuation*, rather
// than a hand-authored encounter tier.  `passed` means that the branch both
// reached and won the target fight; an elite can remain unseen when the chosen
// route avoids all remaining elites, while the next battle and current-act boss
// are normally mandatory unless the branch dies first.
struct FutureFightProbe {
    bool nextCombatSeen = false, nextCombatPassed = false;
    bool nextEliteSeen = false, nextElitePassed = false;
    bool nextBossSeen = false, nextBossPassed = false;
    bool completed = false;  // false only when a bounded rollout was censored
    struct Observation {
        Room room = Room::INVALID;
        MonsterEncounter encounter = MonsterEncounter::INVALID;
        int floor = 0;
        int hp = 0;
        int maxHp = 1;
        bool passed = false;
    };
    // One record for each fight actually reached.  Across encounter-queue
    // samples, reaching a record is precisely its estimated occurrence chance.
    std::vector<Observation> fights;
};

// Continue a copied run after any out-of-combat counterfactual action. Every
// branch in one decision uses the same agent seed and copied GameContext RNG
// state (common random numbers).  maxFights < 0 means finish the whole run.  A
// bounded branch resolves rewards/path choices after its last fight, stops at
// the next battle, then bootstraps expected final floor and P(win).
static OocCounterfactualResult
finishOocCounterfactual(GameContext gc, int sims, std::uint64_t agentSeed,
                        PathHistory path, int maxFights = -1, bool bootstrap = false,
                        FutureFightProbe *probe = nullptr, int stopAfterAct = 0) {
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    int fights = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if (maxFights >= 0 && fights >= maxFights) break;
            const Room room = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
            if (probe) {
                const bool passed = bc.outcome == Outcome::PLAYER_VICTORY;
                probe->fights.push_back({room, bc.encounter, gc.floorNum, gc.curHp,
                                         gc.maxHp, passed});
                if (!probe->nextCombatSeen) {
                    probe->nextCombatSeen = true;
                    probe->nextCombatPassed = passed;
                }
                if (room == Room::ELITE && !probe->nextEliteSeen) {
                    probe->nextEliteSeen = true;
                    probe->nextElitePassed = passed;
                }
                if (room == Room::BOSS && !probe->nextBossSeen) {
                    probe->nextBossSeen = true;
                    probe->nextBossPassed = passed;
                }
            }
            ++fights;
            // This is deliberately after recording the boss outcome: a full-act
            // evaluator stops at the current act's boss rather than leaking a
            // candidate's score into Act+1 rewards/fights.
            if (stopAfterAct > 0 && battleAct == stopAfterAct && room == Room::BOSS) break;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF later rest seed=" << gc.seed << " floor=" << gc.floorNum << "\n";
            if (!(g_restWin && restWinPolicy(gc))) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.empty()) break;
                actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    double won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : 0.0;
    double floor = gc.floorNum;
    if (bootstrap && gc.outcome == GameOutcome::UNDECIDED) {
        const double vf = vStateRaw(gc);
        const double vw = vStateWin(gc);
        if (std::isfinite(vf) && vf >= gc.floorNum && vf <= 60) floor = vf;
        if (std::isfinite(vw) && vw >= 0 && vw <= 1) won = vw;
    }
    if (probe) probe->completed = gc.outcome != GameOutcome::UNDECIDED;
    t_curPath = nullptr;
    return {won, floor, (double)gc.curHp};
}

// GameContext normally shares its Map through a shared_ptr. A counterfactual may
// reach the next act and regenerate that map; detach it so speculative branches
// cannot overwrite the live run's current-act map.
static GameContext detachedCounterfactualCopy(const GameContext &gc) {
    GameContext copy = gc;
    if (gc.map) copy.map = std::make_shared<Map>(*gc.map);
    return copy;
}

// Draw one encounter from the game pool.  We use this rather than an equal
// encounter average: Slay the Spire's pools are weighted, and the no-repeat
// rule makes a sequence's conditional distribution depend on its prior two
// encounters.
static MonsterEncounter sampleEncounterWeighted(const MonsterEncounter *pool,
                                                const float *weights, int count,
                                                Random &rng) {
    const float roll = rng.random();
    float cumulative = 0.0f;
    for (int i = 0; i < count; ++i) {
        cumulative += weights[i];
        if (roll < cumulative) return pool[i];
    }
    return pool[count - 1];
}

// Replace only the unseen normal/elite encounter queues in a copied run.  A
// live GameContext has a concrete queue for its seed, but that information is
// hidden from a player.  Sampling this conditional queue is therefore the
// appropriate information-set evaluation for a card pick.  The act boss is
// deliberately NOT resampled: it is chosen at act generation and visible to
// the player, so every candidate must evaluate the known gc.boss.  Map layout
// and all non-combat RNG stay fixed so alternatives differ principally in
// combat fit.
static void resampleRemainingActEncounters(GameContext &gc, std::uint64_t branchSeed) {
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    Random rng(branchSeed);
    const int weakCount = gc.act == 1 ? 3 : 2;
    for (int i = gc.monsterListOffset; i < (int)gc.monsterList.size(); ++i) {
        const bool weak = i < weakCount;
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        MonsterEncounter draw;
        do {
            draw = sampleEncounterWeighted(pool, weights, count, rng);
        } while ((i > 0 && draw == gc.monsterList[i - 1]) ||
                 (i > 1 && draw == gc.monsterList[i - 2]));
        gc.monsterList[i] = draw;
    }
    for (int i = gc.eliteMonsterListOffset; i < (int)gc.eliteMonsterList.size(); ++i) {
        MonsterEncounter draw;
        do {
            draw = MonsterEncounterPool::elites[actIdx][rng.random(2)];
        } while (i > 0 && draw == gc.eliteMonsterList[i - 1]);
        gc.eliteMonsterList[i] = draw;
    }
}

// Death itself is a discontinuity, and HP is most valuable near the danger
// boundary rather than linearly.  This utility is deliberately encounter-agnostic:
// a hard fight matters because it lowers survival/HP in the simulations, not
// because we gave it a hand-authored tier.
static double nonlinearHpSafety(int hp, int maxHp) {
    const double fraction = maxHp > 0 ? (double)hp / maxHp : 0.0;
    return 1.0 / (1.0 + std::exp(-(fraction - 0.35) / 0.10));
}

static double allActFightUtility(const FutureFightProbe &probe, int decisionFloor) {
    double utility = 0.0;
    for (const auto &f : probe.fights) {
        const int floorsAway = std::max(0, f.floor - decisionFloor);
        const double urgency = std::pow(g_actFightProbeFloorDecay, floorsAway);
        // Reaching this record is its occurrence indicator.  Averaging over
        // sampled queues thus estimates P(occurs) * P(survives | occurs), while
        // the sigmoid values a post-fight safety buffer without treating HP as
        // a linear resource.
        utility += urgency * (f.passed ? nonlinearHpSafety(f.hp, f.maxHp) : -1.0);
    }
    return utility;
}

// Full-act, encounter-distribution card policy.  Candidates are card offers
// plus Skip.  Every candidate sees the same sampled hidden encounter queues
// (common random numbers), follows the actual selected map route to the boss,
// and is ranked solely by allActFightUtility -- no V/card scorer is queried for
// this immediate decision.
static bool actFightProbeDraftPolicy(GameContext &gc) {
    if (!g_actFightProbeDraft) return false;
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e100;
        int bestIdx = 5;  // the simulator evaluates Skip as a normal candidate
        std::vector<double> candidateScores(nCards + 1, 0.0);
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = cand < nCards ? cand : 5;
            double total = 0.0;
            for (int f = 0; f < g_actFightProbeFutures; ++f) {
                // Depends on the decision/future but never on candidate: exact
                // same encounter possibilities for each offered card.
                const std::uint64_t branchSeed = gc.seed
                    ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                    ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(gc.floorNum + 31 * rIdx));
                GameContext branch = detachedCounterfactualCopy(gc);
                search::GameAction(RT::CARD, rIdx, cardIdx).execute(branch);
                resampleRemainingActEncounters(branch, branchSeed);
                FutureFightProbe probe;
                finishOocCounterfactual(std::move(branch), g_actFightProbeSims,
                                        branchSeed, basePath, -1, false, &probe, gc.act);
                total += allActFightUtility(probe, gc.floorNum);
            }
            const double score = total / std::max(1, g_actFightProbeFutures);
            candidateScores[cand] = score;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        if (g_actFightProbeTrace) {
            std::cerr << "[act-fight draft floor=" << gc.floorNum << " act=" << gc.act << "]";
            for (int cand = 0; cand <= nCards; ++cand) {
                if (cand == nCards) std::cerr << " skip=" << candidateScores[cand];
                else std::cerr << ' ' << r.cardRewards[rIdx][cand].getName()
                               << '=' << candidateScores[cand];
            }
            std::cerr << " -> " << (bestIdx == 5 ? "skip" : r.cardRewards[rIdx][bestIdx].getName()) << '\n';
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    t_curPath = savedPath;
    return true;
}

struct EncounterOption {
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
};

// Conditional enemy pools at a concrete combat checkpoint. Normal and elite
// entries retain the game's no-repeat constraints; event fights are fixed by
// their event option. This gives a probability distribution without a hand-made
// difficulty tier.
static std::vector<EncounterOption> possibleEncounterOptions(const GameContext &gc) {
    std::vector<EncounterOption> out;
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    if (gc.curRoom == Room::MONSTER) {
        const int used = gc.monsterListOffset - 1; // battle already consumed this queue slot
        const bool weak = used < (gc.act == 1 ? 3 : 2);
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        double total = 0.0;
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) total += weights[i];
        }
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) out.push_back({pool[i], weights[i] / total});
        }
    } else if (gc.curRoom == Room::ELITE) {
        const int used = gc.eliteMonsterListOffset - 1;
        const MonsterEncounter prev = used > 0 ? gc.eliteMonsterList[used - 1] : MonsterEncounter::INVALID;
        int count = 0;
        for (int i = 0; i < 3; ++i) if (MonsterEncounterPool::elites[actIdx][i] != prev) ++count;
        for (int i = 0; i < 3; ++i) {
            const MonsterEncounter e = MonsterEncounterPool::elites[actIdx][i];
            if (e != prev) out.push_back({e, 1.0 / count});
        }
    } else if (gc.curRoom == Room::BOSS) {
        // Unlike the normal and elite queues, the boss was selected when the
        // act was generated and is public information.  Do not average in
        // alternative bosses the player will never face.
        out.push_back({gc.boss, 1.0});
    } else {
        out.push_back({gc.info.encounter, 1.0});
    }
    return out;
}

// One sampled progression trunk per candidate/future provides realistic deck,
// relic and HP checkpoints. At each reached combat, every possible enemy is
// fought independently from that same pre-fight state; this avoids a recursive
// full-act continuation for each action/enemy combination.
struct CheckpointFightComponent {
    int floor = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
    bool passed = false;
    int hp = 0;
    int maxHp = 1;
    double safety = 0.0;
    double contribution = 0.0;
    int sims = 0;
};

struct PredictedCheckpointFight {
    double winProbability = 0.0;
    int endHpIfWin = 1;
    int maxHp = 1;
    bool predictedWin = false;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter) {
    BattleContext bc{};
    bc.init(gc, encounter);
    const auto prediction = g_actFightProbePredictNet.predictOutcome(bc);
    const int maxHp = std::max(1, bc.player.maxHp);
    return {
        std::max(0.0, std::min(1.0, prediction.winProbability)),
        std::max(1, std::min(maxHp, (int)std::lround(prediction.endHpFractionIfWin * maxHp))),
        maxHp,
        prediction.winProbability >= g_actFightProbePredictWinThreshold,
    };
}

// Complete a battle without a combat search.  BattleContext::exitBattle still
// takes the ordinary victory route (including Burning Blood and reward setup),
// but no cards, potions, or combat RNG are consumed.  That missing combat-side
// transition state is the known approximation of this fast benchmark mode.
static bool applyPredictedCheckpointFight(GameContext &gc, MonsterEncounter encounter,
                                          PredictedCheckpointFight *out = nullptr) {
    const auto prediction = predictCheckpointFight(gc, encounter);
    if (out) *out = prediction;
    if (!prediction.predictedWin) {
        gc.outcome = GameOutcome::PLAYER_LOSS;
        return false;
    }
    BattleContext virtualBattle{};
    virtualBattle.init(gc, encounter);
    virtualBattle.player.curHp = prediction.endHpIfWin;
    virtualBattle.outcome = Outcome::PLAYER_VICTORY;
    virtualBattle.exitBattle(gc);
    return gc.outcome == GameOutcome::UNDECIDED;
}

struct OocEncounterPrediction {
    double winProbability = -1.0;
    double hpFraction = 0.0;
};

static std::vector<OocEncounterPrediction> queryOocEncounterPredictions(
        const std::string &rootState, std::uint32_t actionBits, int screen, int act,
        const std::vector<MonsterEncounter> &encounters) {
    std::ostringstream req;
    req << "OE;" << actionBits << ';';
    for (int i = 0; i < (int)encounters.size(); ++i) {
        if (i) req << ',';
        req << (int)encounters[i];
    }
    req << ';' << screen << ';' << act << ';' << rootState << '\n';
    std::istringstream in(vTransact(req.str()));
    std::vector<OocEncounterPrediction> out;
    for (int i = 0; i < (int)encounters.size(); ++i) {
        std::string token;
        if (!(in >> token)) break;
        const auto comma = token.find(',');
        if (comma == std::string::npos) break;
        out.push_back({std::atof(token.substr(0, comma).c_str()),
                       std::atof(token.substr(comma + 1).c_str())});
    }
    return out;
}

static double checkpointedActFightUtility(GameContext gc, int sims, std::uint64_t agentSeed,
                                           PathHistory path, int decisionFloor,
                                           const std::string &rootState,
                                           std::uint32_t rootActionBits,
                                           int rootScreen, int rootAct,
                                           std::vector<CheckpointFightComponent> *components = nullptr) {
    search::ScumSearchAgent2 trunkAgent;
    trunkAgent.simulationCountBase = sims;
    trunkAgent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    double utility = 0.0;
    int steps = 0;
    int checkpointCount = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED && gc.act >= 1 && gc.act <= 3) {
        if (++steps > 160) {
            std::cerr << "[checkpoint trunk safety stop floor=" << gc.floorNum
                      << " screen=" << (int)gc.screenState << "]\n";
            break;
        }
        if (g_actFightProbeTrace)
            std::cerr << "[checkpoint trunk step=" << steps << " floor=" << gc.floorNum
                      << " room=" << (int)gc.curRoom << " screen=" << (int)gc.screenState << "]\n";
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;
            const Room room = gc.curRoom;
            const int floor = gc.floorNum;
            const int checkpointSims = actFightProbeCheckpointSims(sims, checkpointCount);
            double expected = 0.0;
            const auto options = possibleEncounterOptions(gc);
            std::vector<MonsterEncounter> optionEncounters;
            for (const auto &option : options) optionEncounters.push_back(option.encounter);
            const bool useEncounterNN = g_actFightProbeEncounterNN && checkpointCount == 0
                                     && !rootState.empty() && !optionEncounters.empty();
            const auto encounterPredictions = useEncounterNN
                ? queryOocEncounterPredictions(rootState, rootActionBits, rootScreen, rootAct,
                                               optionEncounters)
                : std::vector<OocEncounterPrediction>{};
            for (int i = 0; i < (int)options.size(); ++i) {
                GameContext local = detachedCounterfactualCopy(gc);
                bool passed = false;
                int hp = local.curHp, maxHp = local.maxHp;
                double safety = -1.0;
                if (useEncounterNN && i < (int)encounterPredictions.size()
                    && encounterPredictions[i].winProbability >= 0.0) {
                    const auto &prediction = encounterPredictions[i];
                    passed = prediction.winProbability >= g_actFightProbePredictWinThreshold;
                    hp = std::max(1, std::min(local.maxHp,
                        (int)std::lround(prediction.hpFraction * local.maxHp)));
                    maxHp = std::max(1, local.maxHp);
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else if (g_actFightProbePredict) {
                    const auto prediction = predictCheckpointFight(local, options[i].encounter);
                    passed = prediction.predictedWin;
                    hp = prediction.endHpIfWin;
                    maxHp = prediction.maxHp;
                    // The model heads predict P(win) and E[end HP | win].
                    // Keep the oracle's loss penalty in the expected utility.
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else {
                    search::ScumSearchAgent2 fightAgent;
                    fightAgent.simulationCountBase = fightSims(local, checkpointSims);
                    fightAgent.rng = std::default_random_engine(
                        agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1))
                                  ^ (0xa0761d6478bd642fULL * (std::uint64_t)(floor + 1)));
                    BattleContext bc{}; bc.init(local, options[i].encounter);
                    fightAgent.playoutBattle(bc); bc.exitBattle(local);
                    passed = bc.outcome == Outcome::PLAYER_VICTORY;
                    hp = local.curHp;
                    maxHp = local.maxHp;
                    safety = passed ? nonlinearHpSafety(hp, maxHp) : -1.0;
                }
                expected += options[i].probability * safety;
                if (components) components->push_back({
                    floor, room, options[i].encounter, options[i].probability, passed,
                    hp, maxHp, safety,
                    std::pow(g_actFightProbeFloorDecay, std::max(0, floor - decisionFloor))
                        * options[i].probability * safety,
                    (g_actFightProbePredict || useEncounterNN) ? 0 : fightSims(local, checkpointSims),
                });
            }
            utility += std::pow(g_actFightProbeFloorDecay, std::max(0, floor - decisionFloor)) * expected;
            ++checkpointCount;

            // The final scored checkpoint needs no actual trunk battle: no
            // later deck/HP state can contribute to a capped objective.
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;

            // Advance only this one sampled trunk; future checkpoints are then
            // naturally weighted by the probability that the trunk reaches them.
            if (g_actFightProbePredict) {
                if (!applyPredictedCheckpointFight(gc, gc.info.encounter)) break;
            } else {
                trunkAgent.simulationCountBase = fightSims(gc, checkpointSims);
                // g_potionKeepValue is process-global. With saving disabled (the
                // deployed/pilot setting) its default is the same fixed value, so
                // avoid a needless shared write while branches run in parallel.
                // Dynamic potion saving remains sequential until that setting is
                // made thread-local in the combat searcher.
                if (g_potionSave) search::g_potionKeepValue = potionKeepValue(gc);
                BattleContext actual{}; actual.init(gc); trunkAgent.playoutBattle(actual); actual.exitBattle(gc);
            }
            if (room == Room::BOSS) break;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.empty()) break;
            actions.front().execute(gc);
        } else {
            trunkAgent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return utility;
}

static std::string csvQuote(const std::string &s) {
    std::string out = "\"";
    for (const char c : s) {
        if (c == '\"') out += "\"\"";
        else out += c;
    }
    return out + "\"";
}

static std::string actionDescription(const search::GameAction &action, const GameContext &gc) {
    std::ostringstream out;
    action.printDesc(out, gc);
    // A few event actions have no human-readable printer; retain their stable
    // encoded action bits rather than silently logging an empty legal action.
    return out.str().empty() ? "bits=" + std::to_string(action.bits) : out.str();
}

static std::string joinLegalActions(const std::vector<search::GameAction> &actions,
                                    const GameContext &gc) {
    std::ostringstream out;
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) out << " | ";
        out << i << ':' << actionDescription(actions[i], gc);
    }
    return out.str();
}

// Paired OOC supervision at the next real combat.  Unlike the all-act future
// evaluator, this deliberately stops each counterfactual branch at its first
// battle.  The branch then has two labels: what the ordinary baseline does
// against the concrete encounter, and the weighted result of fighting every
// encounter still possible at that checkpoint.
static std::string oocNextCombatHeader() {
    return "seed,decisionIdx,actionIdx,actionBits,action,legalActions,screen,act,floor,futures,"
           "actualWin,actualHp,allEncounterWin,allEncounterHp,encounterLabels,stateFeatures";
}

struct EncounterLabel {
    double probability = 0.0;
    double weightedWin = 0.0;
    double weightedHp = 0.0;
};

struct NextCombatLabel {
    double actualWin = 0.0, actualHp = 0.0;
    double allWin = 0.0, allHp = 0.0;
    int seen = 0;
    std::map<int, EncounterLabel> encounterLabels;
};

static bool advanceOocToNextBattle(GameContext &gc, int sims, std::uint64_t agentSeed,
                                   PathHistory path) {
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    for (int steps = 0; steps < 180 && gc.outcome == GameOutcome::UNDECIDED; ++steps) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            t_curPath = nullptr;
            return true;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // handled by the deployed rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return false;
}

static NextCombatLabel labelNextCombat(GameContext branch, int branchSims,
                                       std::uint64_t agentSeed) {
    NextCombatLabel label;
    PathHistory emptyPath;
    if (!advanceOocToNextBattle(branch, branchSims, agentSeed, emptyPath)) return label;
    label.seen = 1;
    const auto options = possibleEncounterOptions(branch);
    double weight = 0.0;
    for (int i = 0; i < (int)options.size(); ++i) {
        GameContext local = detachedCounterfactualCopy(branch);
        search::ScumSearchAgent2 fightAgent;
        fightAgent.simulationCountBase = fightSims(local, branchSims);
        fightAgent.rng = std::default_random_engine(
            agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1)));
        BattleContext bc{};
        bc.init(local, options[i].encounter);
        fightAgent.playoutBattle(bc);
        bc.exitBattle(local);
        const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
        const double hp = won ? local.curHp : 0.0;
        const double p = options[i].probability;
        label.allWin += p * (won ? 1.0 : 0.0);
        label.allHp += p * hp;
        weight += p;
        auto &el = label.encounterLabels[(int)options[i].encounter];
        el.probability += p;
        el.weightedWin += p * (won ? 1.0 : 0.0);
        el.weightedHp += p * hp;
    }
    if (weight > 0.0) {
        label.allWin /= weight;
        label.allHp /= weight;
    }

    // Concrete-encounter label from the ordinary baseline continuation.  This
    // is intentionally separate from the encounter-distribution label above.
    GameContext actual = detachedCounterfactualCopy(branch);
    search::ScumSearchAgent2 actualAgent;
    actualAgent.simulationCountBase = fightSims(actual, branchSims);
    actualAgent.rng = std::default_random_engine(agentSeed ^ 0xa0761d6478bd642fULL);
    BattleContext actualBattle{};
    actualBattle.init(actual);
    actualAgent.playoutBattle(actualBattle);
    actualBattle.exitBattle(actual);
    label.actualWin = actualBattle.outcome == Outcome::PLAYER_VICTORY ? 1.0 : 0.0;
    label.actualHp = label.actualWin ? actual.curHp : 0.0;
    return label;
}

static std::string runOocNextCombatSeed(std::uint64_t seed, int outerSims, int asc,
                                         int branchSims, int futures) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);
    PathHistory path;
    t_curPath = &path;
    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<search::GameAction> sampledActions;
    int sampledDecision = -1;
    int eligible = 0, decisionIdx = 0;
    int fightsLost = 0, fightsTotal = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) ++fightsLost;
            bc.exitBattle(gc);
        } else {
            const auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledActions = actions;
                    sampledDecision = decisionIdx;
                }
                ++decisionIdx;
            }
            if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14)
                search::GameAction(chooseMapAction(gc)).execute(gc);
            else if (gc.screenState == ScreenState::REWARDS) {
                auto &r = gc.info.rewardsContainer;
                if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
                else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
                else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                else                            serverCardRewardPolicy(gc);
            } else if (gc.screenState == ScreenState::SHOP_ROOM) shopVPolicy(gc);
            else if (inRemoveSelect) removeSelectVPolicy(gc);
            else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {}
            else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                     && gc.info.selectScreenType == CardSelectScreenType::UPGRADE)
                upgradeSelectWinPolicy(gc);
            else agent.stepOutOfCombatPolicy(gc);
        }
    }
    std::ostringstream out;
    if (sampled) {
        const std::string state = richRow(*sampled, sampledPath);
        const std::string legal = joinLegalActions(sampledActions, *sampled);
        const int nf = std::max(1, futures);
        for (int a = 0; a < (int)sampledActions.size(); ++a) {
            NextCombatLabel total;
            for (int f = 0; f < nf; ++f) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                sampledActions[a].execute(branch);
                const auto label = labelNextCombat(
                    std::move(branch), branchSims,
                    seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                         ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(sampledDecision + 31)));
                total.seen += label.seen;
                total.actualWin += label.actualWin;
                total.actualHp += label.actualHp;
                total.allWin += label.allWin;
                total.allHp += label.allHp;
                for (const auto &[encounter, el] : label.encounterLabels) {
                    auto &dst = total.encounterLabels[encounter];
                    dst.probability += el.probability;
                    dst.weightedWin += el.weightedWin;
                    dst.weightedHp += el.weightedHp;
                }
            }
            std::ostringstream encounterLabels;
            for (const auto &[encounter, el] : total.encounterLabels) {
                if (encounterLabels.tellp() > 0) encounterLabels << '|';
                const double prob = el.probability / nf;
                const double win = el.probability > 0.0 ? el.weightedWin / el.probability : 0.0;
                const double hp = el.probability > 0.0 ? el.weightedHp / el.probability : 0.0;
                encounterLabels << encounter << ':' << prob << ':' << win << ':' << hp;
            }
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledActions[a].bits
                << ',' << csvQuote(actionDescription(sampledActions[a], *sampled)) << ','
                << csvQuote(legal) << ',' << (int)sampled->screenState << ',' << sampled->act << ','
                << sampled->floorNum << ',' << nf << ',' << total.actualWin/nf << ','
                << total.actualHp/nf << ',' << total.allWin/nf << ',' << total.allHp/nf << ','
                << csvQuote(encounterLabels.str()) << ','
                << csvQuote(state) << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void oocNextCombatGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                             std::uint64_t seedOffset, int branchSims, int futures) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << oocNextCombatHeader() << '\n'; out.flush(); }
    std::cout << "oocnextgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " -> " << outfile << '\n';
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string rows = runOocNextCombatSeed(seedOffset+s, outerSims, asc,
                                                       branchSims, futures);
        #pragma omp critical(ooc_next_write)
        { out << rows; out.flush(); }
    }
}

static std::string serializeFightComponents(const std::vector<std::vector<CheckpointFightComponent>> &all) {
    std::ostringstream out;
    for (int future = 0; future < (int)all.size(); ++future) {
        if (future) out << ';';
        out << "f" << future << '=';
        for (int i = 0; i < (int)all[future].size(); ++i) {
            if (i) out << '|';
            const auto &c = all[future][i];
            out << c.floor << ':' << roomStrings[(int)c.room] << ':'
                << monsterEncounterStrings[(int)c.encounter]
                << ":p=" << c.probability << ":win=" << c.passed
                << ":hp=" << c.hp << '/' << c.maxHp
                << ":safety=" << c.safety << ":contrib=" << c.contribution
                << ":sims=" << c.sims;
        }
    }
    return out.str();
}

static bool initActFightProbeLog() {
    if (g_actFightProbeLogPath.empty()) return true;
    std::ifstream existing(g_actFightProbeLogPath);
    const bool needsHeader = !existing.good() || existing.peek() == std::ifstream::traits_type::eof();
    g_actFightProbeLog.open(g_actFightProbeLogPath, std::ios::app);
    if (!g_actFightProbeLog.is_open()) {
        std::cerr << "[all-acts checkpoint teacher log failed to open: " << g_actFightProbeLogPath << "]\n";
        return false;
    }
    if (needsHeader) {
        // stateFeatures is vFeatCsv(gc), whose stable schema is richStateHeader().
        g_actFightProbeLog
            << "seed,decisionIdx,act,floor,mapX,mapY,screen,knownBoss,maxCheckpoints,checkpointSims,actionIdx,action,legalActions,"
               "futures,futureSeeds,futureUtilities,meanUtility,sampleSd,standardError,"
               "checkpointComponents,stateFeatures\n";
        g_actFightProbeLog.flush();
    }
    std::cout << "[all-acts checkpoint teacher log: " << g_actFightProbeLogPath << "]\n";
    return true;
}

static void appendActFightProbeLog(const GameContext &gc, int decisionIdx,
                                   const std::vector<search::GameAction> &actions, int actionIdx,
                                   const std::vector<std::uint64_t> &futureSeeds,
                                   const std::vector<double> &utilities,
                                   const std::vector<std::vector<CheckpointFightComponent>> &components) {
    if (!g_actFightProbeLog.is_open()) return;
    double mean = 0.0;
    for (const double utility : utilities) mean += utility;
    mean /= std::max(1, (int)utilities.size());
    double sq = 0.0;
    for (const double utility : utilities) sq += (utility - mean) * (utility - mean);
    const double sampleSd = utilities.size() > 1 ? std::sqrt(sq / (utilities.size() - 1)) : 0.0;
    const double standardError = utilities.empty() ? 0.0 : sampleSd / std::sqrt((double)utilities.size());

    std::ostringstream seeds, values;
    for (int f = 0; f < (int)futureSeeds.size(); ++f) {
        if (f) { seeds << ';'; values << ';'; }
        seeds << futureSeeds[f];
        values << utilities[f];
    }
    const std::string action = actionDescription(actions[actionIdx], gc);
    std::lock_guard<std::mutex> lock(g_actFightProbeLogMutex);
    g_actFightProbeLog
        << gc.seed << ',' << decisionIdx << ',' << gc.act << ',' << gc.floorNum << ','
        << gc.curMapNodeX << ',' << gc.curMapNodeY << ',' << (int)gc.screenState << ','
        << csvQuote(monsterEncounterStrings[(int)gc.boss]) << ',' << g_actFightProbeMaxCheckpoints << ','
        << csvQuote(actFightProbeCheckpointSimsCsv()) << ',' << actionIdx << ','
        << csvQuote(action) << ',' << csvQuote(joinLegalActions(actions, gc)) << ','
        << utilities.size() << ',' << csvQuote(seeds.str()) << ',' << csvQuote(values.str()) << ','
        << mean << ',' << sampleSd << ',' << standardError << ','
        << csvQuote(serializeFightComponents(components)) << ',' << csvQuote(vFeatCsv(gc)) << '\n';
    g_actFightProbeLog.flush();
}

// All-acts experiment: extend the checkpointed objective from card rewards to
// every legal strategic action in Acts 1--3. This includes boss-relic choices:
// their resulting next-act state is scored at its next combat checkpoints.
static bool actFightProbeAllOocPolicy(GameContext &gc) {
    if (!g_actFightProbeAllOoc || gc.act < 1 || gc.act > 3) return false;
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;

    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    const int decisionIdx = t_actFightProbeDecisionIdx++;
    double bestScore = -1e100;
    int best = -1;
    std::vector<double> scores(actions.size(), -1e100);
    std::vector<bool> valid(actions.size(), false);
    for (int a = 0; a < (int)actions.size(); ++a) valid[a] = actions[a].isValidAction(gc);

    struct BranchResult {
        std::uint64_t seed = 0;
        double utility = 0.0;
        std::vector<CheckpointFightComponent> components;
    };
    const int futures = g_actFightProbeFutures;
    std::vector<BranchResult> branches(actions.size() * futures);
    const bool parallelBranches = g_actFightProbeParallelBranches && !g_actFightProbeTrace
                                  && !g_potionSave;

    // Each branch owns its GameContext, RNG, combat searchers, TCP connection
    // (t_vSock is thread-local), and output slot.  Candidate-independent seeds
    // preserve common random numbers exactly as in the serial oracle.
    #pragma omp parallel for schedule(dynamic) if(parallelBranches)
    for (int task = 0; task < (int)branches.size(); ++task) {
        const int a = task / futures;
        const int f = task % futures;
        t_actFightProbeActionIdx = a;
        t_actFightProbeFutureIdx = f;
        const std::uint64_t branchSeed = gc.seed
            ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
            ^ (0x94d049bb133111ebULL * (std::uint64_t)(gc.floorNum + 97 * gc.curMapNodeY));
        BranchResult &result = branches[task];
        result.seed = branchSeed;
        if (!valid[a]) continue;
        GameContext branch = detachedCounterfactualCopy(gc);
        // Resample before the immediate action: a map choice can create its
        // next battle immediately, and it is hidden information too.
        resampleRemainingActEncounters(branch, branchSeed);
        actions[a].execute(branch);
        result.utility = checkpointedActFightUtility(
            std::move(branch), g_actFightProbeSims, branchSeed, basePath, gc.floorNum,
            vFeatCsv(gc), actions[a].bits, (int)gc.screenState, gc.act,
            &result.components);
    }

    // A serial branch temporarily installs its copied path for server feature
    // parity and clears it on return. Restore the live path before emitting the
    // teacher state/log rows below.
    t_curPath = savedPath;

    // Reduce in fixed action/future order. This retains deterministic scores,
    // logs, and tie-breaking independent of OpenMP scheduling.
    for (int a = 0; a < (int)actions.size(); ++a) {
        if (!valid[a]) continue;
        double total = 0.0;
        std::vector<std::uint64_t> futureSeeds;
        std::vector<double> futureUtilities;
        std::vector<std::vector<CheckpointFightComponent>> components;
        for (int f = 0; f < futures; ++f) {
            const BranchResult &result = branches[a * futures + f];
            futureSeeds.push_back(result.seed);
            futureUtilities.push_back(result.utility);
            components.push_back(result.components);
            total += result.utility;
        }
        scores[a] = total / std::max(1, futures);
        appendActFightProbeLog(gc, decisionIdx, actions, a, futureSeeds, futureUtilities, components);
        if (scores[a] > bestScore) { bestScore = scores[a]; best = a; }
    }
    if (best < 0) { t_curPath = savedPath; return false; }
    if (g_actFightProbeTrace) {
        std::cerr << "[all-ooc act-fight floor=" << gc.floorNum << " screen="
                  << (int)gc.screenState << ']';
        for (int a = 0; a < (int)actions.size(); ++a) {
            std::ostringstream desc; actions[a].printDesc(desc, gc);
            std::cerr << ' ' << desc.str() << '=' << scores[a];
        }
        std::cerr << " -> "; actions[best].printDesc(std::cerr, gc); std::cerr << '\n';
    }
    actions[best].execute(gc);
    t_curPath = savedPath;
    return true;
}

// ---------------------------------------------------------------------------
// PAIRED PATH COUNTERFACTUALS: uniformly reservoir-sample one genuine branching
// map decision from each source run, then finish every legal child from the
// identical parent state with common agent/game RNG. This supplies direct route
// action values rather than trying to infer causal alternatives from trajectory
// state values generated by the heuristic policy.
static std::string richStateHeader();
static std::string pathCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateX,heuristicX," + richStateHeader()
         + ",branchWon,branchFloor,branchHp";
}

static std::string runPathCounterfactualSeed(std::uint64_t seed, int outerSims, int asc,
                                             int branchSims, int futures, std::uint64_t futureSalt) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 17);
    PathHistory path;
    t_curPath = &path;

    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<int> sampledCandidates;
    int sampledDecision = -1, sampledHeuristic = -1;
    int eligible = 0, decisionIdx = 0;
    using RT = search::GameAction::RewardsActionType;

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            std::vector<int> candidates;
            if (gc.curMapNodeY < 0) {
                for (const MapNode &node : gc.map->nodes[0]) if (node.edgeCount > 0) candidates.push_back(node.x);
            } else {
                const MapNode &node = gc.map->getNode(gc.curMapNodeX, gc.curMapNodeY);
                for (int i = 0; i < node.edgeCount; ++i) candidates.push_back(node.edges[i]);
            }
            const int heuristic = chooseMapAction(gc);
            if (candidates.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledCandidates = candidates;
                    sampledDecision = decisionIdx;
                    sampledHeuristic = heuristic;
                }
                ++decisionIdx;
            }
            search::GameAction(heuristic).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // current deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::ostringstream out;
    if (sampled) {
        const int na = static_cast<int>(sampledCandidates.size());
        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
        const int nf = std::max(1, futures);
        for (int f = 0; f < nf; ++f) {
            const std::uint64_t futureSeed = seed
                ^ (0xa24baed4963ee407ULL * static_cast<std::uint64_t>(sampledDecision * nf + f + 1))
                ^ (0x9e3779b97f4a7c15ULL * futureSalt);
            for (int a = 0; a < na; ++a) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                search::GameAction(sampledCandidates[a]).execute(branch);
                const OocCounterfactualResult result = finishOocCounterfactual(
                    branch, branchSims, futureSeed, sampledPath, -1, false);
                bw[a] += result.won; bf[a] += result.floor; bh[a] += result.hp;
            }
        }
        t_curPath = &sampledPath;
        const std::string state = richRow(*sampled, sampledPath);
        for (int a = 0; a < na; ++a) {
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledCandidates[a] << ','
                << sampledHeuristic << ',' << state << ',' << bw[a]/nf << ',' << bf[a]/nf << ','
                << bh[a]/nf << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void pathCounterfactualGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                                  std::uint64_t seedOffset, int branchSims, int futures,
                                  std::uint64_t futureSalt = 0) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << pathCounterfactualHeader() << '\n'; out.flush(); }
    std::cout << "pathcfgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " futureSalt " << futureSalt
              << " threads " << numThreads() << " -> " << outfile << '\n';
    auto start = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runPathCounterfactualSeed(seedOffset+s, outerSims, asc,
                                                                branchSims, futures, futureSalt);
        #pragma omp critical(path_cf_write)
        {
            out << generated; out.flush();
            rows += std::count(generated.begin(), generated.end(), '\n');
            ++done;
            if (done % 25 == 0 || done == nSeeds) {
                const double elapsed = std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-start).count();
                std::printf("  %d/%d runs, %lld action rows, %.0fs (%.2fs/run)\n",
                            done, nSeeds, rows, elapsed, elapsed/done);
                std::fflush(stdout);
            }
        }
    }
}

static bool genuineRestVsSmith(const GameContext &gc) {
    return !gc.hasRelic(RelicId::COFFEE_DRIPPER)
        && !gc.relics.has(RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
}

static std::string richStateHeader() {
    std::string h = richHeader();
    const std::string prefix = "seed,";
    if (h.rfind(prefix, 0) == 0) h.erase(0, prefix.size());
    const std::string labels = ",won,finalFloor,endHp";
    const size_t p = h.rfind(labels); if (p != std::string::npos) h.erase(p);
    return h;
}

static std::string restCounterfactualHeader() {
    return "seed,restIdx," + richStateHeader()
         + ",restWon,restFloor,restHp,smithWon,smithFloor,smithHp";
}

static std::string cardCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateId,candidateUpgraded," + richStateHeader()
         + ",branchFutures,branchWon,branchFloor,branchHp"
         + ",branchNextCombatSeen,branchNextCombatPassed"
         + ",branchNextEliteSeen,branchNextElitePassed"
         + ",branchNextBossSeen,branchNextBossPassed,branchFutureComplete";
}

struct DataGen2Rows {
    std::string meta;
    std::string rest;
    std::string card;
};

static DataGen2Rows
runDataGen2Seed(std::uint64_t seed, int sims, int asc, double epsilon,
                int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                int cardCfSims = 0, int cardCfFights = 3, int cardCfFutures = 1,
                int cardCfStride = 1, int cardCfMaxPerRun = 0,
                std::uint64_t cardCfFutureSalt = 0, int cardCfAdaptiveMaxFutures = 0,
                double cardCfAdaptiveGap = 5.0) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    PathHistory path;
    t_curPath = &path;
    std::vector<std::string> rows;
    std::vector<std::string> restRows;
    std::vector<std::string> cardRows;
    int restIdx = 0;
    int cardDecisionIdx = 0, cardCollected = 0;
    using RT = search::GameAction::RewardsActionType;
    // Data is generated with the CURRENT BEST play policy (server card picks
    // skip@g_cardSkipThresh + heuristic path + shop-V), so labels & the state
    // distribution match how we actually play. eps-greedy random card picks keep
    // deck coverage broad. Requires v_server.py running.
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(richRow(gc, path));                 // comprehensive snapshot
                // Softmax-sample each card reward by its V-marginal (temp g_dgTemp)
                // + uniform floor `epsilon`: data spreads over good-but-varied play
                // while every card still gets sampled sometimes (unbiased coverage).
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();

                    // Direct action labels: from the identical pre-choice state,
                    // finish the run after every offered card and after skip.  A
                    // deterministic hash samples decision positions uniformly;
                    // the per-run cap prevents one long run from dominating cost.
                    const int stride = std::max(1, cardCfStride);
                    const bool sampleCardCf = cardCfSims > 0 && cardCfMaxPerRun > 0
                        && cardCollected < cardCfMaxPerRun
                        && ((seed * 11400714819323198485ULL
                             + (std::uint64_t)cardDecisionIdx * 0x9e3779b97f4a7c15ULL)
                            % (std::uint64_t)stride) == 0;
                    if (sampleCardCf) {
                        const int na = nc + 1;                 // offered cards + skip
                        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
                        std::vector<double> ncs(na, 0.0), ncp(na, 0.0);
                        std::vector<double> nes(na, 0.0), nep(na, 0.0);
                        std::vector<double> nbs(na, 0.0), nbp(na, 0.0), nfc(na, 0.0);
                        const int futures = std::max(1, cardCfFutures);
                        const int maxFutures = std::max(futures, cardCfAdaptiveMaxFutures);
                        int usedFutures = 0;
                        for (int f = 0; f < maxFutures; ++f) {
                            const std::uint64_t futureSeed = seed
                                ^ (0xd1b54a32d192ed03ULL
                                   * (std::uint64_t)(cardDecisionIdx * futures + f + 1))
                                ^ (0x9e3779b97f4a7c15ULL * cardCfFutureSalt);
                            for (int a = 0; a < na; ++a) {
                                const int choice = a < nc ? a : 5;
                                GameContext branch = detachedCounterfactualCopy(gc);
                                search::GameAction(RT::CARD, rIdx, choice).execute(branch);
                                FutureFightProbe probe;
                                OocCounterfactualResult br = finishOocCounterfactual(
                                    branch, cardCfSims, futureSeed, path,
                                    std::max(1, cardCfFights), true, &probe);
                                t_curPath = &path;
                                bw[a] += br.won;
                                bf[a] += br.floor;
                                bh[a] += br.hp;
                                ncs[a] += probe.nextCombatSeen;
                                ncp[a] += probe.nextCombatPassed;
                                nes[a] += probe.nextEliteSeen;
                                nep[a] += probe.nextElitePassed;
                                nbs[a] += probe.nextBossSeen;
                                nbp[a] += probe.nextBossPassed;
                                nfc[a] += probe.completed;
                            }
                            usedFutures = f + 1;
                            if (usedFutures >= futures) {
                                std::vector<double> runningScore(na);
                                for (int a = 0; a < na; ++a)
                                    runningScore[a] = (bf[a] + 10.0 * bw[a]) / usedFutures;
                                std::nth_element(runningScore.begin(), runningScore.end()-2,
                                                 runningScore.end());
                                const double gap = runningScore.back()
                                                   - *(runningScore.end()-2);
                                if (usedFutures >= maxFutures || gap > cardCfAdaptiveGap) break;
                            }
                        }
                        const std::string state = richRow(gc, path);
                        for (int a = 0; a < na; ++a) {
                            const bool skip = a == nc;
                            const Card *card = skip ? nullptr : &r.cardRewards[rIdx][a];
                            std::ostringstream cr;
                            cr << seed << ',' << cardDecisionIdx << ',' << (skip ? 5 : a) << ','
                               << (skip ? -1 : (int)card->getId()) << ','
                               << (skip ? 0 : (card->isUpgraded() ? 1 : 0)) << ',' << state << ','
                               << usedFutures << ',' << bw[a]/usedFutures << ','
                               << bf[a]/usedFutures << ',' << bh[a]/usedFutures << ','
                               << ncs[a]/usedFutures << ',' << ncp[a]/usedFutures << ','
                               << nes[a]/usedFutures << ',' << nep[a]/usedFutures << ','
                               << nbs[a]/usedFutures << ',' << nbp[a]/usedFutures << ','
                               << nfc[a]/usedFutures;
                            cardRows.push_back(cr.str());
                        }
                        ++cardCollected;
                    }
                    ++cardDecisionIdx;

                    std::vector<double> marg = vQueryMarginals(gc, rIdx);
                    int action;
                    if ((int)marg.size() != nc) {                    // server error -> uniform incl skip
                        action = std::uniform_int_distribution<int>(0, nc)(ex);
                        if (action >= nc) action = 5;
                    } else if (*std::max_element(marg.begin(), marg.end()) < g_cardSkipThresh) {
                        action = 5;                                  // no card improves the deck -> skip (as exploit)
                    } else {
                        action = sampleCardSoftmax(marg, g_dgTemp, epsilon, ex);  // softmax which card
                    }
                    search::GameAction(RT::CARD, rIdx, action).execute(gc);
                }
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);                                       // best shop policy (V-knapsack)
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);                               // shop removal target
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF outer rest seed=" << seed << " idx=" << restIdx << " floor=" << gc.floorNum << "\n";
            if (restCfSims > 0 && genuineRestVsSmith(gc)
                && restCfStride > 0 && (seed % (std::uint64_t)restCfStride) == 0) {
                double rw = 0, rf = 0, rh = 0, sw = 0, sf = 0, sh = 0;
                const int futures = std::max(1, restCfFutures);
                for (int f = 0; f < futures; ++f) {
                    const std::uint64_t futureSeed = seed ^ (0x9e3779b97f4a7c15ULL
                                                    * (std::uint64_t)(restIdx * futures + f + 1));
                    GameContext gr = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply rest valid=" << search::GameAction(0, 0).isValidAction(gr) << "\n";
                    search::GameAction(0, 0).execute(gr);       // rest
                    OocCounterfactualResult rr = finishOocCounterfactual(
                        gr, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF rest branch done floor=" << rr.floor << "\n";
                    t_curPath = &path;
                    GameContext gs = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply smith valid=" << search::GameAction(1, 0).isValidAction(gs) << "\n";
                    search::GameAction(1, 0).execute(gs);       // smith
                    if (gs.screenState == ScreenState::CARD_SELECT
                        && gs.info.selectScreenType == CardSelectScreenType::UPGRADE)
                        upgradeSelectWinPolicy(gs);
                    OocCounterfactualResult sr = finishOocCounterfactual(
                        gs, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF smith branch done floor=" << sr.floor << "\n";
                    t_curPath = &path;
                    rw += rr.won; rf += rr.floor; rh += rr.hp;
                    sw += sr.won; sf += sr.floor; sh += sr.hp;
                }
                std::ostringstream cr;
                cr << seed << ',' << restIdx << ',' << richRow(gc, path)
                   << ',' << rw/futures << ',' << rf/futures << ',' << rh/futures
                   << ',' << sw/futures << ',' << sf/futures << ',' << sh/futures;
                restRows.push_back(cr.str());
                ++restIdx;
            }
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply deployed rest policy\n";
            if (!restWinPolicy(gc)) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (!actions.empty()) actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum, endHp = gc.curHp;
    std::ostringstream o, ro, co;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << ',' << endHp << '\n';
    for (const auto &rr : restRows) ro << rr << '\n';
    for (const auto &cr : cardRows) co << cr << '\n';
    return {o.str(), ro.str(), co.str()};
}

static void dataGen2(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                     long long seedOffset = 0, const std::string &restOut = "",
                     int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                     const std::string &cardOut = "", int cardCfSims = 0,
                     int cardCfFights = 3, int cardCfFutures = 1, int cardCfStride = 1,
                     int cardCfMaxPerRun = 0, std::uint64_t cardCfFutureSalt = 0,
                     int cardCfAdaptiveMaxFutures = 0, double cardCfAdaptiveGap = 5.0) {
    const bool append = seedOffset > 0;
    std::cout << "datagen2 (rich)  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << "  cardFutureSalt " << cardCfFutureSalt
              << (append ? "  [append]" : "") << "  threads " << numThreads() << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << richHeader() << '\n'; f.flush(); }
    std::ofstream rf;
    if (!restOut.empty()) {
        rf.open(restOut, append ? std::ios::app : std::ios::out);
        if (rf.tellp() == 0) { rf << restCounterfactualHeader() << '\n'; rf.flush(); }
    }
    std::ofstream cf;
    if (!cardOut.empty()) {
        cf.open(cardOut, append ? std::ios::app : std::ios::out);
        if (cf.tellp() == 0) { cf << cardCounterfactualHeader() << '\n'; cf.flush(); }
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0, cardRowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto generated = runDataGen2Seed((std::uint64_t)(seedOffset + s), sims, asc, epsilon,
                                         restCfSims, restCfFutures, restCfStride,
                                         cardCfSims, cardCfFights, cardCfFutures, cardCfStride,
                                         cardCfMaxPerRun, cardCfFutureSalt,
                                         cardCfAdaptiveMaxFutures, cardCfAdaptiveGap);
        #pragma omp critical
        {
            f << generated.meta; f.flush();
            if (rf.is_open()) { rf << generated.rest; rf.flush(); }
            if (cf.is_open()) { cf << generated.card; cf.flush(); }
            rowCount += std::count(generated.meta.begin(), generated.meta.end(), '\n');
            cardRowCount += std::count(generated.card.begin(), generated.card.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld meta rows, %lld card-CF rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, cardRowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld meta rows + %lld card-CF rows from %d runs in %.1fs\n",
                rowCount, cardRowCount, nSeeds, wall);
}

// ---------------------------------------------------------------------------
// COMBAT VALUE datagen: snapshot the live BattleContext at every in-fight
// decision (via search::g_onCombatDecision) and label each snapshot with that
// fight's eventual outcome (won, end HP). Trains V_combat(state) -> outcome, a
// learned leaf value to replace noisy random rollouts. Features are combat-only
// (player/monsters/available-cards), fixed length.
// Header/row now delegate to the library (search::combatFeatureNames /
// combatExtractFeatures) so combatgen training data and the C++ leaf-inference
// use the SAME feature extraction -- no train/serve drift.
static std::string combatHeaderStr() {
    const auto &names = search::combatFeatureNames();
    std::string h;
    for (size_t i = 0; i < names.size(); ++i) { if (i) h += ','; h += names[i]; }
    return h;
}

// Rich-label suffix (distributional model): endTurn + per-potion-ID consumption flags.
// Potion IDs 0..43 map to the Potion enum (0=EMPTY, 1=INVALID, 2..43=real potions).
static constexpr int kNumGenPotions = 44;
static std::string distLabelHeaderStr() {
    std::string h = ",endTurn,potionsConsumed";
    for (int i = 0; i < kNumGenPotions; ++i) { h += ",pUsed"; h += std::to_string(i); }
    return h;
}

// Snapshot of what's held at a decision so we can later determine consumption.
struct CombatDecisionSnapshot {
    std::string featureRow;
    std::bitset<kNumGenPotions> potionsHeld;
};
static std::string distLabelSuffix(const CombatDecisionSnapshot &snap,
                                   int endTurn,
                                   const std::bitset<kNumGenPotions> &finalPotions) {
    std::ostringstream o;
    o << ',' << endTurn;
    int consumed = 0;
    for (int i = 0; i < kNumGenPotions; ++i) {
        if (snap.potionsHeld[i] && !finalPotions[i]) ++consumed;
    }
    o << ',' << consumed;
    for (int i = 0; i < kNumGenPotions; ++i) {
        o << ',' << (snap.potionsHeld[i] && !finalPotions[i] ? 1 : 0);
    }
    return o.str();
}
static std::bitset<kNumGenPotions> getPotionBits(const BattleContext &bc) {
    std::bitset<kNumGenPotions> b;
    for (int i = 0; i < bc.potionCapacity && i < (int)bc.potions.size(); ++i) {
        int pid = (int)bc.potions[i];
        if (pid >= 0 && pid < kNumGenPotions) b.set(pid);
    }
    return b;
}

static std::string combatFeatureRow(const BattleContext &bc) {
    const int nf = search::combatFeatureCount();
    std::vector<float> feat(nf);
    search::combatExtractFeatures(bc, feat.data());
    std::ostringstream o;
    for (int i = 0; i < nf; ++i) {
        if (i) o << ',';
        const float v = feat[i];
        if (v == (float)(long)v) o << (long)v; else o << v;   // integers stay clean
    }
    return o.str();
}

// Play one full run; emit combat-state rows labeled with each fight's outcome.
static std::string runCombatGenSeed(std::uint64_t seed, int sims, int asc, double epsilon,
                                      bool richLabels = false) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    int fightIdx = 0;
    std::vector<CombatDecisionSnapshot> fightSnaps;
    search::g_onCombatDecision = [&](const BattleContext &bc) {
        CombatDecisionSnapshot s;
        s.featureRow = combatFeatureRow(bc);
        s.potionsHeld = getPotionBits(bc);
        fightSnaps.push_back(std::move(s));
    };
    // When richLabels=false: emit just won,endHp (backward-compatible).
    // When richLabels=true: also emit endTurn + per-potion consumption labels.

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            fightSnaps.clear();
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            const int won      = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp    = bc.player.curHp;
            const int endTurn  = bc.turn;
            auto finalPotions  = getPotionBits(bc);
            for (const auto &snap : fightSnaps) {
                out << seed << ',' << fightIdx << ',' << snap.featureRow
                    << ',' << won << ',' << endHp;
                if (richLabels)
                    out << distLabelSuffix(snap, endTurn, finalPotions);
                out << '\n';
            }
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    return out.str();
}

// forward decl
static std::string policyHeaderStr();
// ---------------------------------------------------------------------------
// FAIR-PLAY datagen: Searcher3 ISMCTS → value + policy CSVs with visit
// distributions. Policy rows: state+action features + visit count + total.
// ---------------------------------------------------------------------------
static std::tuple<std::string,std::string,std::string>
runFairGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    search::g_richCombatFeatures = true;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path; t_curPath = &path;

    std::ostringstream val, pol, ooc;
    int fightIdx = 0, decIdx = 0, oocDecIdx = 0;
    std::vector<std::string> fightRows;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    auto logOoc = [&](const char *screen, int actionId) {
        ooc << seed << ',' << oocDecIdx++ << ',' << screen << ','
            << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
            << (int)gc.deck.cards.size() << ',' << (int)gc.gold << ',' << actionId << '\n';
    };

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        fightRows.push_back(combatFeatureRow(bc));
    };
    search::g_onSearchComplete3 = [&](const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
        const int thisDecIdx = decIdx++;
        const auto &edges = s3.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.child.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v;
            }
            pol << ',' << e.child.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            fightRows.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            for (const auto &fr : fightRows)
                val << seed << ',' << fightIdx << ',' << fr << ',' << won << ',' << endHp << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            int action = chooseMapAction(gc); logOoc("MAP", action); search::GameAction(action).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int ridx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[ridx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, ridx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete3 = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str(), ooc.str() };
}

static void fairGen(int nSeeds, int sims, int asc, double epsilon,
                    const std::string &valFile, const std::string &polFile,
                    const std::string &oocFile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fairgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << " + " << oocFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    std::ofstream of(oocFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }
    if (of.tellp() == 0) { of << "seed,decIdx,screen,act,floor,curHp,maxHp,deckSize,gold,action\n"; of.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0, oRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto [vr, pr, or_] = runFairGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << vr;  pf << pr;  of << or_;
            vf.flush(); pf.flush(); of.flush();
            vRows += std::count(vr.begin(), vr.end(), '\n');
            pRows += std::count(pr.begin(), pr.end(), '\n');
            oRows += std::count(or_.begin(), or_.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol + %lld ooc rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, oRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy + %lld ooc rows from %d runs in %.1fs\n",
                vRows, pRows, oRows, nSeeds, wall);
}

// ---------------------------------------------------------------------------
// STRATEGIC data generation: one CSV row per LEGAL action at each OOC decision,
// with full rich state, structured candidate fields, a chosen flag, and the
// terminal outcome. Feeds Phase 5 run-level model training.
// Row schema (strategicHeader()):
//   seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,
//   <1017 rich state>,won,endFloor,endHp
// - action: raw packed GameAction bits (uint32).
// - actionType: rewardsActionType (0..6) on REWARDS/SHOP, CardSelectScreenType
//   on CARD_SELECT, else -1.
// - c1..c3: raw GameAction indices (idx1..idx3), 0 when unused.
// - cand1..c3: screen-specific resolved candidate identities (-1 when N/A):
//   REWARDS: GOLD=gold amt; CARD=cardId,upgraded; RELIC=relicId; POTION=potionId;
//            KEY=2 (emerald) / 3 (sapphire).
//   SHOP:    CARD=cardId,price,upgraded; RELIC=relicId,price; POTION=potionId,price;
//            CARD_REMOVE=removeCost.
//   EVENT:   eventId, option index.  MAP: childX, childY, childRoom.
//   BOSS_RELIC_REWARDS: relicId.  CARD_SELECT: cardId, selectScreenType.
//   REST/TREASURE: -1 (option semantics live in c1 / screen state).
static std::string strategicStateCols() {
    std::string h = richHeader();                       // "seed,<state...>,curMapY,won,finalFloor,endHp"
    const auto comma = h.find(',');
    std::string rest = h.substr(comma + 1);             // drop the "seed," prefix
    const auto wonPos = rest.rfind(",won,finalFloor,endHp");
    return rest.substr(0, wonPos);                      // state columns only, in richRow() order
}

static std::string strategicHeader() {
    return "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,"
         + strategicStateCols() + ",won,endFloor,endHp\n";
}

// Successor-state fingerprint used to detect which legal action the policy
// actually executed. All fields are ints; two actions with identical
// fingerprints are indistinguishable at this decision.
struct StratFingerprint {
    int screen, act, floor, hp, maxHp, gold;
    int keys[3], potionCount, potions[5];
    int deckSize, relicCount;
    long long deckSum, deckUpSum, deckHash;   // deck-content digest (non-last cards)
    long long relicSum, relicHash;            // relic-identity digest
    long long selSum, selHash;                // info.haveSelectedCards digest (multi-select picks)
    int bottledLast;                          // last bottled card id (-1)
    int goldRew, cardRew, relicRew, potionRew;
    int emeraldKey, sapphireKey, mapX, mapY, selectSize;

    bool operator==(const StratFingerprint &o) const {
        if (screen != o.screen || act != o.act || floor != o.floor || hp != o.hp
            || maxHp != o.maxHp || gold != o.gold || potionCount != o.potionCount
            || deckSize != o.deckSize || relicCount != o.relicCount
            || deckSum != o.deckSum || deckUpSum != o.deckUpSum || deckHash != o.deckHash
            || relicSum != o.relicSum || relicHash != o.relicHash
            || selSum != o.selSum || selHash != o.selHash
            || bottledLast != o.bottledLast || goldRew != o.goldRew || cardRew != o.cardRew
            || relicRew != o.relicRew || potionRew != o.potionRew
            || emeraldKey != o.emeraldKey || sapphireKey != o.sapphireKey
            || mapX != o.mapX || mapY != o.mapY || selectSize != o.selectSize)
            return false;
        for (int i = 0; i < 3; ++i) if (keys[i] != o.keys[i]) return false;
        for (int i = 0; i < 5; ++i) if (potions[i] != o.potions[i]) return false;
        return true;
    }
};
static StratFingerprint stratFingerprint(const GameContext &gc) {
    StratFingerprint f{};
    f.screen = (int)gc.screenState; f.act = gc.act; f.floor = gc.floorNum;
    f.hp = gc.curHp; f.maxHp = gc.maxHp; f.gold = gc.gold;
    f.keys[0] = gc.blueKey ? 1 : 0; f.keys[1] = gc.greenKey ? 1 : 0; f.keys[2] = gc.redKey ? 1 : 0;
    f.potionCount = gc.potionCount;
    for (int i = 0; i < 5; ++i)
        f.potions[i] = (i < (int)gc.potions.size()) ? (int)gc.potions[i] : -1;
    f.deckSize = (int)gc.deck.size();
    f.bottledLast = -1;
    for (int i = 0; i < f.deckSize; ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        f.deckSum += id; f.deckUpSum += c.isUpgraded() ? id : 0;
        f.deckHash = f.deckHash * 31 + id * 2 + (c.isUpgraded() ? 1 : 0);
        if (gc.deck.isCardBottled(i)) f.bottledLast = id;
    }
    f.relicCount = (int)gc.relics.relics.size();
    for (const auto &ri : gc.relics.relics) {
        const int rid = (int)ri.id;
        f.relicSum += rid; f.relicHash = f.relicHash * 31 + rid + 1;
    }
    for (const auto &sc : gc.info.haveSelectedCards) {
        const int sid = (int)sc.card.getId();
        f.selSum += sid * 2 + (sc.card.isUpgraded() ? 1 : 0);
        f.selHash = f.selHash * 31 + sc.deckIdx + 1;
    }
    const auto &r = gc.info.rewardsContainer;
    f.goldRew = r.goldRewardCount; f.cardRew = r.cardRewardCount;
    f.relicRew = r.relicCount; f.potionRew = r.potionCount;
    f.emeraldKey = r.emeraldKey ? 1 : 0; f.sapphireKey = r.sapphireKey ? 1 : 0;
    f.mapX = gc.curMapNodeX; f.mapY = gc.curMapNodeY;
    f.selectSize = (int)gc.info.toSelectCards.size();
    return f;
}

// Resolved candidate identities for one legal action in the current screen.
static void strategicCands(const GameContext &gc, const search::GameAction &a,
                           int &actionType, int &c1, int &c2, int &c3,
                           int &cand1, int &cand2, int &cand3) {
    using RT = search::GameAction::RewardsActionType;
    actionType = -1; c1 = a.getIdx1(); c2 = a.getIdx2(); c3 = a.getIdx3();
    cand1 = cand2 = cand3 = -1;
    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &r = gc.info.rewardsContainer;
            switch (t) {
                case RT::GOLD:
                    if (c1 >= 0 && c1 < r.goldRewardCount) cand1 = r.gold[c1];
                    break;
                case RT::CARD:
                    if (c1 >= 0 && c1 < r.cardRewardCount
                        && c2 >= 0 && c2 < (int)r.cardRewards[c1].size()) {
                        const Card &card = r.cardRewards[c1][c2];
                        cand1 = (int)card.getId(); cand2 = card.isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < r.relicCount) cand1 = (int)r.relics[c1]; break;
                case RT::POTION: if (c1 >= 0 && c1 < r.potionCount) cand1 = (int)r.potions[c1]; break;
                case RT::KEY: cand1 = r.emeraldKey ? 2 : 3; break;
                default: break;
            }
            break;
        }
        case ScreenState::SHOP_ROOM: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &s = gc.info.shop;
            switch (t) {
                case RT::CARD:
                    if (c1 >= 0 && c1 < 7) {
                        cand1 = (int)s.cards[c1].getId(); cand2 = s.cardPrice(c1);
                        cand3 = s.cards[c1].isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.relics[c1]; cand2 = s.relicPrice(c1); } break;
                case RT::POTION: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.potions[c1]; cand2 = s.potionPrice(c1); } break;
                case RT::CARD_REMOVE: cand1 = s.removeCost; break;
                default: break;
            }
            break;
        }
        case ScreenState::EVENT_SCREEN:
            cand1 = (int)gc.curEvent; cand2 = c1;
            break;
        case ScreenState::MAP_SCREEN: {
            cand1 = c1;
            const int ty = (gc.curMapNodeY == -1) ? 0 : gc.curMapNodeY + 1;
            cand2 = ty;
            if (c1 >= 0 && ty >= 0 && ty < 15 && c1 < 7)
                cand3 = (int)gc.map->nodes[ty][c1].room;
            break;
        }
        case ScreenState::BOSS_RELIC_REWARDS:
            if (c1 >= 0 && c1 < 3) cand1 = (int)gc.info.bossRelics[c1];
            break;
        case ScreenState::CARD_SELECT: {
            actionType = (int)gc.info.selectScreenType;
            if (c1 >= 0 && c1 < (int)gc.info.toSelectCards.size()) {
                cand1 = (int)gc.info.toSelectCards[c1].card.getId();
                cand2 = (int)gc.info.selectScreenType;
            }
            break;
        }
        default: break;
    }
}

static std::string runStrategicGenSeed(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;

    std::vector<std::string> rows;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        const GameContext pre = gc;

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else Searcher2.
        if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        const int decIdx = (int)rows.size();
        for (const auto &a : actions) {
            GameContext probe = pre;
            a.execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, a, actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << a.bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, path);
            rows.push_back(r.str());
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, path);
            rows.push_back(r.str());
        }
    }
    t_curPath = nullptr;

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (const auto &row : rows)
        out << row << ',' << won << ',' << gc.floorNum << ',' << gc.curHp << '\n';
    return out.str();
}

static void strategicGen(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    const bool append = seedOffset > 0;
    std::cout << "strategicgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  -> " << outFile << "\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
}

// ---------------------------------------------------------------------------
// COMBINED value+policy datagen: one full-run play emits BOTH the V_combat value
// rows (g_onCombatDecision snapshot, labeled with fight endHp) AND the policy-target
// rows (g_onSearchComplete root visit-π). Halves self-play combat datagen cost vs
// running combatgen + policygen separately, and the two datasets are perfectly
// aligned (same play). Returns {valueRows, policyRows}.
static std::pair<std::string,std::string>
runFightGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path;
    t_curPath = &path;

    std::ostringstream val, pol;
    int fightIdx = 0, decIdx = 0;
    std::vector<std::string> fightRows;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        fightRows.push_back(combatFeatureRow(bc));
    };
    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        // Advance for every combat decision, including forced/single-edge roots.
        // This keeps decIdx exactly aligned with the value snapshot emitted by
        // g_onCombatDecision, while still omitting useless one-action policy rows.
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) { pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v; }
            pol << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            fightRows.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            for (const auto &fr : fightRows)
                val << seed << ',' << fightIdx << ',' << fr << ',' << won << ',' << endHp << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                serverCardRewardPolicy(gc);                    // deployed V_floor exploit policy
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str() };
}

// ---------------------------------------------------------------------------
// POLICY-TARGET datagen (AlphaZero-lite phase 1): at every in-combat decision,
// after the searcher has run its full budget, log each root edge as a row
// (state features ++ that action's features) with the edge's VISIT COUNT and the
// decision's TOTAL visits. Training normalizes visit/total -> the MCTS policy
// target π; the learned comparator net(state,action) then steers PUCT selection.
// Reuses g_onSearchComplete (fires once per agent decision, off the hot path).
static std::string policyHeaderStr() {
    const auto &names = search::combatPolicyFeatureNames();
    std::string h = "seed,fightIdx,decIdx";
    for (const auto &n : names) { h += ','; h += n; }
    h += ",visit,total";
    return h;
}

static std::string runPolicyGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    int fightIdx = 0, decIdx = 0;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        const int n = (int)edges.size();
        if (n < 2) return;                       // forced single move -> nothing to learn
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            out << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                out << ',';
                const float v = feat[i];
                if (v == (float)(long)v) out << (long)v; else out << v;
            }
            out << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onSearchComplete = nullptr;
    return out.str();
}

static std::string runDataGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::vector<std::string> rows;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(featureRow(gc) + ',' + deckCountsCsv(gc));  // state + deck ids
                if (ur(ex) < epsilon) {                          // explore: random pick among cards + skip
                    while (r.cardRewardCount > 0) {
                        const int rIdx = r.cardRewardCount - 1;
                        const int nc = r.cardRewards[rIdx].size();
                        const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                        search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);                     // exploit
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum;
    std::ostringstream o;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << '\n';  // seed = run id
    return o.str();
}

// ---------------------------------------------------------------------------
// CAUSAL LABELS: at each card reward, CRN-fork "take card i" vs "skip", play the
// next N fights with common random numbers, and label the card's ADVANTAGE =
// score(take) - score(skip). This measures the true causal effect of the card
// (not just "what losing decks look like"). One row per candidate card.
// ---------------------------------------------------------------------------
// Raw representation (no hand-crafted synergy features): deck as per-card-id
// counts d0..d(kNumCardIds-1) + the candidate card's id; the model (GBM) learns
// which (candidate, deck-card) combinations matter. Plus a few cheap scalars.
// (kNumCardIds / deckCountsCsv defined above featureRow for reuse by datagen.)

static std::string causalContextRow(const GameContext &gc, const Card &c) {
    long obtainSum = 0;
    for (const auto &d : gc.deck.cards) obtainSum += search::Expert::getObtainWeight(d.getId(), d.isUpgraded());
    const int deckSize = gc.deck.size();
    std::ostringstream o;
    o << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ','
      << deckSize << ',' << (int)gc.relics.relics.size() << ',' << obtainSum << ','
      << (deckSize ? (double)obtainSum / deckSize : 0.0) << ','
      << search::Expert::getObtainWeight(c.getId(), c.isUpgraded()) << ',' << c.getBaseDamage() << ','
      << (c.isUpgraded() ? 1 : 0) << ',' << (int)c.getId();
    return o.str();
}

static std::string causalHeader() {
    std::ostringstream h;
    h << "act,floor,curHp,maxHp,gold,deckSize,nRelics,obtainSum,obtainAvg,"
         "c_obtainWeight,c_baseDamage,c_isUpgraded,candidateId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    h << ",advantage";
    return h.str();
}

static std::string runCausalGenSeed(std::uint64_t seed, int sims, int asc, int N, int innerSims, int K, double epsilon) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 2862933555777941757ULL + 7);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    long decision = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                const int rIdx = r.cardRewardCount - 1;
                const int nc = r.cardRewards[rIdx].size();
                const std::uint64_t base = seed * 1000003ULL + (std::uint64_t)decision * 131ULL;
                const std::string dc = deckCountsCsv(gc);        // deck id-counts (same for all candidates)

                // K paired CRN worlds: skip baseline per world, then average card - skip.
                std::vector<double> sSkip(K);
                for (int k = 0; k < K; ++k)
                    sSkip[k] = rolloutChoice(gc, rIdx, 5, N, innerSims, base + k, /*useLabelScore=*/true);
                for (int i = 0; i < nc; ++i) {
                    double adv = 0.0;
                    for (int k = 0; k < K; ++k)
                        adv += rolloutChoice(gc, rIdx, i, N, innerSims, base + k, /*useLabelScore=*/true) - sSkip[k];
                    adv /= K;
                    out << causalContextRow(gc, r.cardRewards[rIdx][i]) << ',' << dc << ',' << adv << '\n';
                }
                ++decision;
                if (ur(ex) < epsilon) {                          // explore to diversify visited states
                    while (r.cardRewardCount > 0) {
                        const int ri = r.cardRewardCount - 1;
                        const int n2 = r.cardRewards[ri].size();
                        const int pick = std::uniform_int_distribution<int>(0, n2)(ex);
                        search::GameAction(RT::CARD, ri, pick < n2 ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    return out.str();
}

static void causalGen(int nSeeds, int sims, int asc, int N, int innerSims, int K, double eps, const std::string &outfile) {
    std::cout << "causalgen  seeds 0.." << nSeeds - 1 << "  outerSims " << sims << "  N " << N
              << "  innerSims " << innerSims << "  K " << K << "  eps " << eps
              << (search::g_fairPlay ? "  [fair-play]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::vector<std::string> per(nSeeds);
    auto t0 = std::chrono::steady_clock::now();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) per[s] = runCausalGenSeed((std::uint64_t)s, sims, asc, N, innerSims, K, eps);

    std::ofstream f(outfile);
    f << causalHeader() << '\n';
    long long rows = 0;
    for (int s = 0; s < nSeeds; ++s) { f << per[s]; rows += std::count(per[s].begin(), per[s].end(), '\n'); }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld causal rows from %d runs in %.1fs\n", rows, nSeeds, wall);
}

static void dataGen(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                    long long seedOffset = 0) {
    const bool append = seedOffset > 0;   // append onto an existing file; seeds are disjoint
    std::cout << "datagen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << "  eps " << epsilon << (search::g_fairPlay ? "  [fair-play]" : "")
              << (append ? "  [append]" : "")
              << "  threads " << numThreads() << "  -> " << outfile << "\n";
    // Incremental / interrupt-safe: write the header (fresh file only), then flush
    // each run's rows as it finishes (inside a critical section). Killing the
    // process at any time leaves a valid CSV of all completed runs. seedOffset lets
    // a follow-up run append DISJOINT seeds (no duplicate rows) onto prior output.
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (!append) {
        f << "seed," << kFeatureHeader;
        for (int i = 0; i < kNumCardIds; ++i) f << ",d" << i;
        f << ",won,finalFloor\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0;
    int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runDataGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows;
            f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
}

// Combat-value dataset: per-fight combat states labeled with the fight outcome.
// Interrupt-safe (per-run flush) and append-capable, same as dataGen.
static void combatGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "combatgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, false);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
}

// Policy-target dataset: per-decision root-edge visit distributions. Same
// interrupt-safe (per-run flush) + append pattern as combatGen.
static void policyGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "policygen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << policyHeaderStr() << "\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runPolicyGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld policy rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
}

// Combined value+policy datagen: ONE play pass writes both CSVs (see runFightGenSeed).
static void fightGen(int nSeeds, int sims, int asc, double epsilon,
                     const std::string &valFile, const std::string &polFile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fightgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto pr = runFightGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << pr.first;  pf << pr.second;  vf.flush(); pf.flush();
            vRows += std::count(pr.first.begin(),  pr.first.end(),  '\n');
            pRows += std::count(pr.second.begin(), pr.second.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy rows from %d runs in %.1fs\n", vRows, pRows, nSeeds, wall);
}

// ---------------------------------------------------------------------------
// DISTRIBUTIONAL COMBAT VALUE datagen: like combatgen but adds rich labels for
// the distributional model — endTurn (for turns-remaining prediction) and
// per-potion-ID consumption flags (for potion-use-probability prediction).
// The 1766 state features + won/endHp are identical to combatgen output.
// ---------------------------------------------------------------------------
static void distCombatGen(int nSeeds, int sims, int asc, double epsilon,
                          const std::string &outfile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "distgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp"
          << distLabelHeaderStr() << "\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, true);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld dist combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
}

// ---------------------------------------------------------------------------
// DECK DUMP: play one run with our best policy (eval draft + heuristic path)
// and print the final deck, relics and outcome.
// ---------------------------------------------------------------------------
static void dumpRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            evalCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::printf("=== seed %llu  %s  floor %d (act %d)  hp %d/%d  gold %d ===\n",
                (unsigned long long)seed,
                gc.outcome == GameOutcome::PLAYER_VICTORY ? "WIN" : "DEAD",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp, gc.gold);

    std::map<std::string, int> counts;
    for (const auto &c : gc.deck.cards) {
        std::string n = c.getName();
        if (c.isUpgraded()) n += "+";
        ++counts[n];
    }
    std::printf("\nDeck (%d cards):\n", gc.deck.size());
    for (const auto &kv : counts) std::printf("  %2dx %s\n", kv.second, kv.first.c_str());

    std::printf("\nRelics (%d):\n", (int)gc.relics.relics.size());
    for (const auto &ri : gc.relics.relics) std::printf("  - %s\n", getRelicName(ri.id));
}

// ---------------------------------------------------------------------------
// EVAL A/B: compare the baseline HP objective vs. the "devalue high HP" one,
// on identical seeds, for both a single hard combat and whole runs.
// ---------------------------------------------------------------------------
static void evalCombatBench(int sims, int nSeeds) {
    g_encounter = MonsterEncounter::GREMLIN_NOB; // an elite that punishes bad HP mgmt
    std::cout << "eval A/B (combat: GremlinNob)   seeds 0.." << nSeeds - 1
              << "   sims/decision: " << sims << "\n\n";

    for (bool devalue : {false, true}) {
        search::g_devalueHighHp = devalue;
        Policy p = makeMctsPolicy(sims);
        int wins = 0; long long hp = 0, turns = 0;
        #pragma omp parallel for reduction(+:wins,hp,turns) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            Result r = runCombat((std::uint64_t)s, p, false);
            wins += r.won; hp += r.hpEnd; turns += r.turns;
        }
        std::printf("%-16s  win%%=%5.1f   avg_hp_end=%5.1f   avg_turns=%4.1f\n",
                    devalue ? "devalue-high-hp" : "baseline",
                    100.0 * wins / nSeeds, (double)hp / nSeeds, (double)turns / nSeeds);
    }
}

static void evalRunBench(int sims, int nSeeds, int asc) {
    std::cout << "eval A/B (whole run)   seeds 0.." << nSeeds - 1
              << "   ascension: " << asc << "   sims/decision: " << sims << "\n\n";

    for (bool devalue : {false, true}) {
        search::g_devalueHighHp = devalue;
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRun((std::uint64_t)s, sims, asc, false);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   avg_sec=%.2f\n",
                    devalue ? "devalue-high-hp" : "baseline",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds);
    }
}

// Export one deterministic full-map graph per (seed, ascension, act) present
// in a card-counterfactual CSV.  The source CSV repeats the state once per
// available action; de-duplicating here keeps the companion graph table small.
// Each node stores its room id and a seven-bit mask of outgoing destination x
// coordinates.  Row/column are implicit in the fixed 15x7 layout.
static void exportCardCfMaps(const std::string &inputPath, const std::string &outputPath) {
    std::ifstream in(inputPath);
    if (!in) throw std::runtime_error("cannot open card-CF CSV: " + inputPath);
    std::ofstream out(outputPath);
    if (!out) throw std::runtime_error("cannot create map CSV: " + outputPath);

    std::string line;
    if (!std::getline(in, line)) throw std::runtime_error("empty card-CF CSV: " + inputPath);
    std::stringstream header(line);
    std::vector<std::string> columns;
    std::string headerField;
    while (std::getline(header, headerField, ',')) columns.push_back(headerField);
    auto columnIndex = [&](const char *name) {
        auto it = std::find(columns.begin(), columns.end(), name);
        if (it == columns.end()) throw std::runtime_error("map source CSV missing column " + std::string(name));
        return static_cast<int>(it - columns.begin());
    };
    const int seedCol = columnIndex("seed");
    const int ascCol = columnIndex("ascension");
    const int actCol = columnIndex("act");
    const int lastNeededCol = std::max({seedCol, ascCol, actCol});

    out << "seed,ascension,act,burningEliteX,burningEliteY,burningEliteBuff";
    for (int i = 0; i < 15 * 7; ++i) out << ",room" << i;
    for (int i = 0; i < 15 * 7; ++i) out << ",edges" << i;
    out << '\n';

    std::set<std::tuple<std::uint64_t, int, int>> seen;
    std::size_t rows = 0;
    while (std::getline(in, line)) {
        std::stringstream ss(line);
        std::string field;
        std::uint64_t seed = 0;
        int ascension = 0, act = 0;
        for (int col = 0; col <= lastNeededCol; ++col) {
            if (!std::getline(ss, field, ',')) {
                throw std::runtime_error("short row in map source CSV");
            }
            if (col == seedCol) seed = std::stoull(field);
            else if (col == ascCol) ascension = std::stoi(field);
            else if (col == actCol) act = std::stoi(field);
        }
        if (!seen.emplace(seed, ascension, act).second) continue;

        Map map = act == 4 ? Map::act4Map() : Map::fromSeed(seed, ascension, act, true);
        out << seed << ',' << ascension << ',' << act << ','
            << map.burningEliteX << ',' << map.burningEliteY << ',' << map.burningEliteBuff;
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            out << ',' << static_cast<int>(map.getNode(x, y).room);
        }
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &node = map.getNode(x, y);
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << ',' << edgeMask;
        }
        out << '\n';
        ++rows;
    }
    std::cout << "exported " << rows << " unique (seed, ascension, act) maps to "
              << outputPath << '\n';
}

// ---------------------------------------------------------------------------
int main(int argc, char **argv) {
    std::string mode = argc > 1 ? argv[1] : "bench";

    if (const char *d = std::getenv("VPORT")) g_vPort = std::atoi(d);

    if (const char *d = std::getenv("STS_ROLLOUT_DEPTH")) {   // cap combat rollout length
        search::g_maxRolloutDepth = std::atoi(d);
        std::cout << "[rollout depth cap = " << search::g_maxRolloutDepth << "]\n";
    }
    if (const char *d = std::getenv("STS_TURN_PENALTY")) {    // -turn*k on capped leaf: loop-breaker
        search::g_leafTurnPenalty = std::atof(d);
        std::cout << "[leaf turn penalty = " << search::g_leafTurnPenalty << "]\n";
    }
    if (const char *d = std::getenv("STS_TT")) {              // transposition table (value sharing)
        search::g_useTT = std::atoi(d) != 0;
        if (search::g_useTT) std::cout << "[transposition table ON]\n";
    }
    if (const char *d = std::getenv("STS_REST_V_THRESH")) {   // rest-site heal-gain threshold
        g_restVThreshold = std::atof(d);
        std::cout << "[rest-V heal threshold = " << g_restVThreshold << "]\n";
    }
    if (const char *d = std::getenv("STS_REST_WIN")) {        // win-rate rest policy (heal vs upgrade by P(win))
        g_restWin = std::atoi(d) != 0;
        if (g_restWin) std::cout << "[win-rate rest policy ON]\n";
    }
    if (const char *d = std::getenv("STS_CARD_WIN")) {       // A/B: card picks by P(win) instead of V_floor
        g_cardWin = std::atoi(d) != 0;
        if (const char *s = std::getenv("STS_CARD_WIN_SKIP")) g_cardWinSkip = std::atof(s);
        if (g_cardWin) std::cout << "[card picks via WIN model, skip<" << g_cardWinSkip << "]\n";
    }
    if (const char *d = std::getenv("STS_CARD_NN")) {        // A/B: card picks via deck-set NN (CN op)
        g_cardNN = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_CARD_NN_W"))    g_cardNNW    = std::atof(w);
        if (const char *s = std::getenv("STS_CARD_NN_SKIP")) g_cardNNSkip = std::atof(s);
        if (g_cardNN) std::cout << "[card picks via deck-set NN: w=" << g_cardNNW
                                << " (1=pure NN, <1 blend w/ v_win), skip<" << g_cardNNSkip
                                << " (needs v_deckset.pt in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_CARD_ACTION")) {    // direct paired card/skip action NN
        g_cardAction = std::atoi(d) != 0;
        if (g_cardAction) std::cout << "[card picks via paired action NN (CA op)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_ACTION_NN")) {
        g_oocActionNN = std::atoi(d) != 0;
        if (g_oocActionNN)
            std::cout << "[OOC decisions via next-combat action NN (OA op), reapplied every decision]\n";
    }
    if (const char *d = std::getenv("STS_OOC_CHECKPOINT_NN")) {
        if (g_oocCheckpointNet.load(d)) {
            g_oocActionNN = true;
            std::cout << "[OOC decisions via native checkpoint-distilled NN]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_NN")) {
        if (g_oocStrategicNet.load(d)) {
            std::cout << "[OOC one-ply strategic NN ON: card rewards gated at margin "
                      << g_oocStrategicMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN")) {
        g_oocStrategicMargin = std::atof(d);
    }
    if (const char *d = std::getenv("STS_BOSS_RELIC")) {    // boss relic pick via V_win (needs v_win in v_server)
        g_bossRelicV = std::atoi(d) != 0;
        if (g_bossRelicV) std::cout << "[boss-relic pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_NEOW_V")) {        // Neow bonus pick via V_win
        g_neowV = std::atoi(d) != 0;
        if (g_neowV) std::cout << "[Neow bonus pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_WIN_NET")) {       // native V_win tree-walk (no v_server socket)
        const std::string path = std::string(d) == "1" ? "build/v_win_trees.txt" : d;
        g_winNet.load(path, richIdxMap());
    }
    {
        // The baseline is serverless by default. Set STS_NATIVE_OOC=0 only
        // for an explicit legacy-server comparison.
        const char *d = std::getenv("STS_NATIVE_OOC");
        g_nativeOoc = !d || std::atoi(d) != 0;
        if (g_nativeOoc) {
            if (!g_winNet.ok) g_winNet.load("build/v_win_trees.txt", richIdxMap());
            g_floorNet.load("build/v_rich_trees.txt", richIdxMap());
            if (!g_floorNet.ok) {
                std::cerr << "[native OOC] failed to load build/v_rich_trees.txt\n";
                return 1;
            }
            std::cout << "[native OOC floor/win GBMs ON; no v_server required]\n";
        }
    }
    if (const char *d = std::getenv("STS_PATH_V")) {        // model-driven pathing (uses forward-map feats)
        g_pathV = std::atoi(d) != 0;
        if (g_pathV) std::cout << "[model-driven pathing via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_PATH_GRAPH")) {    // graph NN scores each legal child subtree
        g_pathGraph = std::atoi(d) != 0;
        if (g_pathGraph) {
            g_pathV = 1;
            std::cout << "[model-driven pathing via full-map graph NN ON]\n";
        }
    }
    if (const char *d = std::getenv("STS_PATH_ACTION")) {   // direct paired route-action model
        g_pathAction = std::atoi(d) != 0;
        if (const char *m = std::getenv("STS_PATH_ACTION_MAX"))
            g_pathActionMax = std::atoi(m);
        if (const char *m = std::getenv("STS_PATH_ACTION_MARGIN"))
            g_pathActionMargin = std::atof(m);
        g_pathActionTrace = std::getenv("STS_PATH_ACTION_TRACE")
                         && std::atoi(std::getenv("STS_PATH_ACTION_TRACE")) != 0;
        if (g_pathAction) {
            g_pathV = 1;
            std::cout << "[model-driven pathing via paired route-action NN ON: max="
                      << g_pathActionMax << " margin=" << g_pathActionMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_EVENT_V")) {       // model-driven event choices
        g_eventV = std::atoi(d) != 0;
        if (g_eventV) std::cout << "[model-driven events via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_POTION_SAVE")) {   // dynamic potion-saving (keep for elites/bosses)
        g_potionSave = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_POTION_WINDOW"))  g_potionWindow  = std::atoi(v);
        if (const char *v = std::getenv("STS_POTION_BONUS"))   g_potionBonus   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_SPEND"))   g_potionSpend   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_DESIRED")) g_potionDesired = std::atof(v);
        if (g_potionSave)
            std::cout << "[potion-saving ON: window=" << g_potionWindow << " bonus=" << g_potionBonus
                      << " spend=" << g_potionSpend << " desired=" << g_potionDesired << "]\n";
    }
    if (const char *d = std::getenv("STS_SHOP_WIN")) {       // A/B: shop bundles scored by P(win)
        g_shopWin = std::atoi(d) != 0;
        if (g_shopWin) std::cout << "[shop scored via WIN model]\n";
    }
    if (const char *d = std::getenv("STS_SIMS_NORMAL")) g_simsNormal = std::atoi(d);  // per-fight sim budgets
    if (const char *d = std::getenv("STS_SIMS_ELITE"))  g_simsElite  = std::atoi(d);
    if (const char *d = std::getenv("STS_SIMS_BOSS"))   g_simsBoss   = std::atoi(d);
    if (g_simsNormal > 0 || g_simsElite > 0 || g_simsBoss > 0)
        std::cout << "[tiered sims: normal=" << g_simsNormal << " elite=" << g_simsElite
                  << " boss=" << g_simsBoss << " (-1=base)]\n";
    if (const char *d = std::getenv("STS_CONVERGE")) {       // convergence-based early stopping
        search::g_convergeStop = std::atoi(d) != 0;
        if (const char *p = std::getenv("STS_CONV_PATIENCE")) search::g_convPatience = std::atoll(p);
        if (const char *m = std::getenv("STS_CONV_MIN"))      search::g_convMinSims  = std::atoll(m);
        if (search::g_convergeStop)
            std::cout << "[convergence stop ON: patience=" << search::g_convPatience
                      << " minSims=" << search::g_convMinSims << "]\n";
    }
    if (const char *d = std::getenv("STS_BOSS_DRAFT")) {      // boss-gated rollout drafting
        g_bossDraft = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS"))    g_bossDraftRows    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_N"))       g_bossDraftN       = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_SIMS"))    g_bossDraftSims    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_FUTURES")) g_bossDraftFutures = std::atoi(v);
        if (g_bossDraft)
            std::cout << "[boss-gated rollout draft ON: rows<=" << g_bossDraftRows
                      << " N=" << g_bossDraftN << " sims=" << g_bossDraftSims
                      << " futures=" << g_bossDraftFutures << "]\n";
    }
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_DRAFT")) {
        g_actFightProbeDraft = std::atoi(d) != 0;
        if (g_actFightProbeDraft)
            std::cout << "[all-act encounter rollout draft ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " floor-decay=" << g_actFightProbeFloorDecay
                      << "; immediate cards scored only by simulated fight utility]\n";
    }
    // Shared by both the card-only and every-OOC variants; parse independently
    // of the legacy card-only enable flag.
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_SIMS"))
        g_actFightProbeSims = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FUTURES"))
        g_actFightProbeFutures = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS")) {
        std::istringstream in(v);
        std::string token;
        while (std::getline(in, token, ',')) {
            const int parsed = std::atoi(token.c_str());
            if (parsed > 0) g_actFightProbeCheckpointSims.push_back(parsed);
        }
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FLOOR_DECAY"))
        g_actFightProbeFloorDecay = std::max(0.0, std::min(1.0, std::atof(v)));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS"))
        g_actFightProbeMaxCheckpoints = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_TRACE"))
        g_actFightProbeTrace = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PARALLEL"))
        g_actFightProbeParallelBranches = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT"))
        g_actFightProbePredict = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_ENCOUNTER_NN"))
        g_actFightProbeEncounterNN = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_NET"))
        g_actFightProbePredictNetPath = v;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_WIN_THRESHOLD"))
        g_actFightProbePredictWinThreshold = std::max(0.0, std::min(1.0, std::atof(v)));
    if (g_actFightProbePredict) {
        if (!g_actFightProbePredictNet.load(g_actFightProbePredictNetPath)
            || !g_actFightProbePredictNet.hasOutcomeHeads()) {
            std::cerr << "[all-acts checkpoint predictor load FAILED (needs combat_entity_v1): "
                      << g_actFightProbePredictNetPath << "]\n";
            return 2;
        }
        std::cout << "[all-acts checkpoint predictor ON: " << g_actFightProbePredictNetPath
                  << ", win threshold=" << g_actFightProbePredictWinThreshold << "]\n";
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_LOG"))
        g_actFightProbeLogPath = v;
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_ALL_OOC")) {
        g_actFightProbeAllOoc = std::atoi(d) != 0;
        if (g_actFightProbeAllOoc)
            std::cout << "[Acts 1-3 all-OOC checkpoint rollout ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " max-checkpoints=" << g_actFightProbeMaxCheckpoints
                      << (g_actFightProbeCheckpointSims.empty()
                          ? "" : " checkpoint-sims=" + actFightProbeCheckpointSimsCsv())
                      << (g_actFightProbeEncounterNN ? " predictor=ooc-encounter-NN(first-checkpoint)" : "")
                      << (g_actFightProbePredict ? " predictor=entity-transition" : "")
                      << "; every legal OOC action scored by fight-strength profile]\n";
    }
    if (g_actFightProbeParallelBranches) {
        if (g_potionSave)
            std::cout << "[all-acts branch parallelism disabled: dynamic potion saving writes shared combat state]\n";
        else if (g_actFightProbeTrace)
            std::cout << "[all-acts branch parallelism disabled: trace output must remain ordered]\n";
        else
            std::cout << "[all-acts branch parallelism ON: up to " << numThreads()
                      << " action-future branches at once]\n";
    }
    if (!g_actFightProbeLogPath.empty() && g_actFightProbeAllOoc && !initActFightProbeLog())
        return 2;
    if (const char *d = std::getenv("STS_STOP_AFTER_ACT")) {
        g_stopAfterAct = std::max(0, std::atoi(d));
        if (g_stopAfterAct > 0)
            std::cout << "[benchmark stops after Act " << g_stopAfterAct << " boss]\n";
    }
    if (const char *d = std::getenv("STS_BOSS_V")) {          // boss-survival V blended into near-boss picks
        g_bossV = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_BOSS_V_W"))       g_bossVW        = std::atof(w);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS")) g_bossDraftRows = std::atoi(v);
        if (g_bossV)
            std::cout << "[boss-V blend draft ON: w=" << g_bossVW
                      << " rows<=" << g_bossDraftRows << " (needs v_boss in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_SKIP_THR")) {        // card-reward skip threshold (marginal V)
        g_cardSkipThresh = std::atof(d);
        std::cout << "[card skip threshold = " << g_cardSkipThresh << "]\n";
    }
    if (const char *d = std::getenv("STS_VPATH")) {          // V-strength path modulation (needs v_server)
        g_vPath = std::atoi(d) != 0;
        if (const char *k = std::getenv("STS_VPATH_K")) g_vPathK = std::atof(k);
        if (g_vPath)
            std::cout << "[V-informed pathing ON: k=" << g_vPathK << " (needs v_server on :5555)]\n";
    }
    if (const char *d = std::getenv("STS_DG_TEMP")) {         // datagen softmax temperature (card marginals)
        g_dgTemp = std::atof(d);
        std::cout << "[datagen softmax temp = " << g_dgTemp << "]\n";
    }
    if (const char *d = std::getenv("STS_FAIR")) {            // determinized/ISMCTS combat (no future peeking)
        search::g_fairPlay = std::atoi(d) != 0;
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS ON]\n";
    }
    if (const char *d = std::getenv("STS_SEARCHER3")) {      // use enhanced BattleScumSearcher3 engine
        search::g_useSearcher3 = std::atoi(d) != 0;
        if (search::g_useSearcher3) std::cout << "[Searcher3 engine ON: particles + compression + dominance + CRN]\n";
    }
    if (const char *d = std::getenv("STS_RISK_LAMBDA")) {    // risk sensitivity for Searcher3 PUCT
        search::g_riskLambda = std::atof(d);
        std::cout << "[risk lambda = " << search::g_riskLambda << "]\n";
    }
    if (const char *d = std::getenv("STS_VNET")) {           // learned V_combat leaf value
        std::string path = std::string(d) == "1" ? "build/v_combat_trees.txt" : d;
        if (search::g_combatVNet.load(path)) {
            search::g_useVNet = true;
            if (const char *a = std::getenv("STS_VNET_ALPHA")) search::g_vnetAlpha = std::atof(a);
            if (const char *b = std::getenv("STS_COMBAT_WIN_BONUS"))
                search::g_combatVNet.setWinBonus(std::atof(b));
            std::cout << "[V_combat leaf value ON: " << path << ", "
                      << search::g_combatVNet.description() << ", alpha "
                      << search::g_vnetAlpha << "]\n";
        } else {
            std::cout << "[V_combat load FAILED: " << path << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_DIST_VNET")) {    // distributional V_combat (transformer, 5-head)
        std::string path = d;
        if (search::g_combatDistVNet.load(path)) {
            search::g_useDistVNet = true;
            std::cout << "[Dist V_combat ON: " << path << ", "
                      << search::g_combatDistVNet.description() << "]\n";
        } else {
            std::cout << "[Dist V_combat load FAILED: " << path << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_PVNET")) {        // shared policy-value network (AlphaZero-style)
        std::string path = d;
        if (search::g_combatPVNet.load(path)) {
            search::g_usePVNet = true;
            std::cout << "[PVNet ON: " << path << ", "
                      << search::g_combatPVNet.description() << "]\n";
        } else {
            std::cout << "[PVNet load FAILED: " << path << "]\n";
        }
    }
    if (search::g_usePVNet) {
        if (const char *a = std::getenv("STS_PVNET_ALPHA")) search::g_pvnetAlpha = std::atof(a);
        if (const char *v = std::getenv("STS_PVNET_VALUE_ONLY")) search::g_pvnetValueOnly = std::atoi(v) != 0;
        std::cout << "[PVNet alpha = " << search::g_pvnetAlpha;
        if (search::g_pvnetValueOnly) std::cout << ", value-only";
        std::cout << "]\n";
    }
    // AZ-lite policy-guided PUCT selection. DEFAULT ON (+4.3pp full-run win @512
    // vs plain UCB, §26): auto-loads the compact net if present. STS_POLICY=0
    // disables; STS_POLICY=<path> overrides the file; STS_POLICY=1 uses the full
    // 447-tree net. Skipped for policygen so base datasets stay UCB-generated
    // (set STS_POLICY explicitly there for AlphaZero-style self-play iteration).
    {
        const char *d = std::getenv("STS_POLICY");
        const bool disabled = d && std::string(d) == "0";
        if (!disabled && mode != "policygen") {
            std::string path = "build/policy_trees_c.txt";
            if (d && std::string(d) == "1")      path = "build/policy_trees.txt";
            else if (d)                          path = d;
            search::g_policyNet.isPolicy = true;
            if (search::g_policyNet.load(path)) {
                search::g_usePolicyNet = true;
                std::cout << "[policy PUCT ON: " << path << ", "
                          << search::g_policyNet.description() << "]\n";
            } else if (d) {                       // warn only if explicitly requested
                std::cout << "[policy net load FAILED: " << path << "]\n";
            }
        }
    }
    if (search::g_usePolicyNet || search::g_usePVNet) {
        if (const char *c = std::getenv("STS_CPUCT")) search::g_cPuct = std::atof(c);
        std::cout << "[c_puct = " << search::g_cPuct << "]\n";
    }

    if (mode == "bench") {
        int sims   = argc > 2 ? std::stoi(argv[2]) : 2000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 100;
        benchmark(sims, nSeeds);

    } else if (mode == "mcts") {
        int sims          = argc > 2 ? std::stoi(argv[2]) : 2000;
        std::uint64_t sd  = argc > 3 ? std::stoull(argv[3]) : 42;
        Result res = runCombat(sd, makeMctsPolicy(sims), true);
        std::printf("\n=== %s ===  hp %d/%d  turns %d\n",
                    res.won ? "WIN" : "LOSS", res.hpEnd, res.maxHp, res.turns);

    } else if (mode == "random") {
        std::uint64_t sd = argc > 2 ? std::stoull(argv[2]) : 42;
        Result res = runCombat(sd, &randomPolicy, true);
        std::printf("\n=== %s ===  hp %d/%d  turns %d\n",
                    res.won ? "WIN" : "LOSS", res.hpEnd, res.maxHp, res.turns);

    } else if (mode == "run") {          // one whole run, verbose
        int sims         = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t sd = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc          = argc > 4 ? std::stoi(argv[4]) : 0;
        RunResult r = runFullRun(sd, sims, asc, false);
        std::printf("=== %s ===  reached floor %d (act %d)  hp %d/%d  %.2fs\n",
                    r.won ? "WIN" : "DEAD", r.floor, r.act, r.hpEnd, r.maxHp, r.sec);

    } else if (mode == "runbench") {     // many whole runs
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 20;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        runBenchmark(sims, nSeeds, asc);

    } else if (mode == "evalcombat") {   // baseline vs devalue-high-hp, one hard combat
        int sims   = argc > 2 ? std::stoi(argv[2]) : 3000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 100;
        evalCombatBench(sims, nSeeds);

    } else if (mode == "evalrun") {       // baseline vs devalue-high-hp, whole runs
        int sims   = argc > 2 ? std::stoi(argv[2]) : 8000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 12;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        evalRunBench(sims, nSeeds, asc);

    } else if (mode == "draftbench") {    // weighted table vs lookahead drafting
        int outerSims = argc > 2 ? std::stoi(argv[2]) : 6000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 16;
        int N         = argc > 4 ? std::stoi(argv[4]) : 1;
        int innerSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int asc       = argc > 6 ? std::stoi(argv[6]) : 0;
        draftBench(outerSims, nSeeds, N, innerSims, asc);

    } else if (mode == "datagen") {       // CSV of (state features, run outcome) for offline V(state)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "data.csv";
        search::g_fairPlay = argc > 7 ? std::stoi(argv[7]) != 0 : false;
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        dataGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "datagen2") {      // RICH per-decision state (relics/upgrades/potions/future/path) + outcome
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "vrich.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "datagen3") {      // RICH outcomes + paired rest/card counterfactuals
        int nSeeds       = argc > 2  ? std::stoi(argv[2])  : 2000;
        int sims         = argc > 3  ? std::stoi(argv[3])  : 300;
        int asc          = argc > 4  ? std::stoi(argv[4])  : 0;
        double eps       = argc > 5  ? std::stod(argv[5])  : 0.05;
        std::string out  = argc > 6  ? argv[6] : "vrich.csv";
        std::string rout = argc > 7  ? argv[7] : "rest_cf.csv";
        long long seedOff= argc > 8  ? std::stoll(argv[8]) : 0;
        int restSims     = argc > 9  ? std::stoi(argv[9])  : sims;
        int restFutures  = argc > 10 ? std::stoi(argv[10]) : 1;
        int restStride   = argc > 11 ? std::stoi(argv[11]) : 4;
        std::string cardOut = argc > 12 ? argv[12] : "";
        int cardSims     = argc > 13 ? std::stoi(argv[13]) : 0;
        int cardFights   = argc > 14 ? std::stoi(argv[14]) : 3;
        int cardFutures  = argc > 15 ? std::stoi(argv[15]) : 1;
        int cardStride   = argc > 16 ? std::stoi(argv[16]) : 4;
        int cardMax      = argc > 17 ? std::stoi(argv[17]) : 1;
        std::uint64_t cardFutureSalt = argc > 18 ? std::stoull(argv[18]) : 0;
        int cardAdaptiveMax = argc > 19 ? std::stoi(argv[19]) : 0;
        double cardAdaptiveGap = argc > 20 ? std::stod(argv[20]) : 5.0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff, rout,
                 restSims, restFutures, restStride, cardOut,
                 cardSims, cardFights, cardFutures, cardStride, cardMax, cardFutureSalt,
                 cardAdaptiveMax, cardAdaptiveGap);

    } else if (mode == "pathcfgen") {     // one uniformly sampled paired route decision per run
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 100;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "path_cf.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 2;
        std::uint64_t salt= argc > 9 ? std::stoull(argv[9]) : 0;
        pathCounterfactualGen(nSeeds, outerSims, asc, out, off, branchSims, futures, salt);

    } else if (mode == "oocnextgen") {    // all legal OOC actions, labels at next combat
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "ooc_next_combat.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 1;
        oocNextCombatGen(nSeeds, outerSims, asc, out, off, branchSims, futures);

    } else if (mode == "vnettest") {      // validate C++ CombatValueNet vs Python predictions
        std::string trees = argc > 2 ? argv[2] : "build/v_combat_trees.txt";
        std::string val   = argc > 3 ? argv[3] : "build/v_combat_val.csv";
        if (!search::g_combatVNet.load(trees)) { std::cerr << "load failed: " << trees << "\n"; return 1; }
        std::ifstream vf(val);
        std::string line; std::getline(vf, line);                 // header
        const int nf = search::combatFeatureCount();
        double maxAbs = 0, sumAbs = 0; int n = 0;
        std::vector<float> canon(nf);
        while (std::getline(vf, line)) {
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < nf; ++i) { std::getline(ss, cell, ','); canon[i] = std::stof(cell); }
            double pyPred = 0;
            while (std::getline(ss, cell, ',')) pyPred = std::stod(cell); // final column
            double cpp = search::g_combatVNet.predictVec(canon.data());
            double d = std::fabs(cpp - pyPred); maxAbs = std::max(maxAbs, d); sumAbs += d; ++n;
            if (n <= 5) std::printf("  row %d: cpp=%.4f py=%.4f diff=%.6f\n", n, cpp, pyPred, d);
        }
        std::printf("VNET VALIDATION: %d rows, max|diff|=%.6f  mean|diff|=%.6f\n", n, maxAbs, sumAbs/n);
        std::printf("%s\n", maxAbs < 1e-2 ? "PASS (C++ matches Python)" : "FAIL");

    } else if (mode == "policynettest") { // validate entity policy logits vs Python
        std::string model = argc > 2 ? argv[2] : "build/policy_entity.txt";
        std::string val   = argc > 3 ? argv[3] : "build/policy_entity_val.csv";
        search::g_policyNet.isPolicy = true;
        if (!search::g_policyNet.load(model)) { std::cerr << "load failed: " << model << "\n"; return 1; }
        std::ifstream vf(val);
        std::string line; std::getline(vf, line);
        const int nf = search::combatPolicyFeatureCount();
        double maxAbs = 0, sumAbs = 0; int n = 0;
        std::vector<float> canon(nf);
        while (std::getline(vf, line)) {
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < nf; ++i) { std::getline(ss, cell, ','); canon[i] = std::stof(cell); }
            double pyPred = 0;
            while (std::getline(ss, cell, ',')) pyPred = std::stod(cell);
            double cpp = search::g_policyNet.predictVec(canon.data());
            double d = std::fabs(cpp - pyPred); maxAbs = std::max(maxAbs, d); sumAbs += d; ++n;
            if (n <= 5) std::printf("  row %d: cpp=%.5f py=%.5f diff=%.7f\n", n, cpp, pyPred, d);
        }
        std::printf("POLICY NET VALIDATION: %d rows, max|diff|=%.7f  mean|diff|=%.7f\n",
                    n, maxAbs, sumAbs/std::max(1, n));
        std::printf("%s\n", maxAbs < 1e-3 ? "PASS (C++ matches Python)" : "FAIL");

    } else if (mode == "speedtest") {     // single-fight Searcher3 speed measurement
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t seed = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        // Init a fight directly with a known encounter
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
        std::printf("speedtest: %s  hp=%d/%d  hand=%d  draw=%zu\n",
                    monsterEncounterStrings[(int)bc.encounter], bc.player.curHp,
                    bc.player.maxHp, bc.cards.cardsInHand, bc.cards.drawPile.size());
        for (int s : {100, 500, 1000, 2500}) {
            search::BattleScumSearcher3 s3(bc, 64);
            auto t0 = std::chrono::steady_clock::now();
            s3.search(s);
            auto t1 = std::chrono::steady_clock::now();
            double sec = std::chrono::duration<double>(t1 - t0).count();
            std::printf("  S3 %5d sims: %6.3fs  %6d sim/s  rootVisits=%lld\n",
                        s, sec, int(s/sec),
                        (long long)s3.root.simulationCount);
        }

    } else if (mode == "combatgen") {     // CSV of (combat state, fight outcome) for V_combat
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vcombat.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        combatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "distgen") {       // combatgen + rich distributional labels (endTurn, potion use)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vdist.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        distCombatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "fairgen") {       // Searcher3 ISMCTS: value + policy rows with visit distributions
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/fair_val.csv";
        std::string pout = argc > 7 ? argv[7] : "build/fair_pol.csv";
        std::string oout = argc > 8 ? argv[8] : "build/fair_ooc.csv";
        long long seedOff = argc > 9 ? std::stoll(argv[9]) : 0;
        // fairgen emits Searcher3 policy rows via g_onSearchComplete3; force the
        // project-fair Searcher3 regime here so callers cannot silently produce
        // data under the wrong producer (STS_FAIR=1 STS_SEARCHER3=1 no longer
        // required; the env vars still mean the same thing for other modes).
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[fairgen forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        fairGen(nSeeds, sims, asc, eps, vout, pout, oout, seedOff);

    } else if (mode == "strategicgen") {  // Phase 5: one row per OOC decision, full rich state
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/strategic.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        strategicGen(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "policygen") {     // CSV of (state, action, visit/total) MCTS policy targets (AZ-lite)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 10000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vpolicy.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        policyGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "mapbatch") {      // companion full-map graph table for rich/meta/card CSVs
        if (argc < 4) {
            std::cerr << "usage: one_combat mapbatch SOURCE.csv MAPS.csv\n";
            return 2;
        }
        exportCardCfMaps(argv[2], argv[3]);

    } else if (mode == "dumpmap") {       // dump a seed's map GRAPH (nodes+edges) for the future GNN
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int asc = argc > 3 ? std::stoi(argv[3]) : 0;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        const Map &map = *gc.map;
        std::printf("# seed %llu act %d  format: y x room edge_x...\n", (unsigned long long)seed, gc.act);
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::NONE || n.room == Room::INVALID) continue;
            std::printf("%d %d %d", y, x, (int)n.room);
            for (int i = 0; i < n.edgeCount; ++i) std::printf(" %d", n.edges[i]);
            std::printf("\n");
        }

    } else if (mode == "winnettest") {    // validate native V_win == server VW on identical vectors
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int asc = argc > 3 ? std::stoi(argv[3]) : 0;
        if (!g_winNet.ok && !g_winNet.load("build/v_win_trees.txt", richIdxMap())) { std::cerr << "load failed\n"; return 1; }
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent; agent.simulationCountBase = 200; agent.rng = std::default_random_engine(seed);
        PathHistory path; t_curPath = &path;
        double maxDiff = 0, sumDiff = 0; int n = 0;
        while (gc.outcome == GameOutcome::UNDECIDED && n < 300) {
            path.update(gc);
            if (gc.screenState != ScreenState::BATTLE) {
                const double nat = g_winNet.predict(richFeatureVec(gc));
                double srv = -1; std::sscanf(vSendRecv("VW;" + vFeatCsv(gc)).c_str(), "%lf", &srv);
                if (srv >= 0) { const double d = std::fabs(nat - srv); maxDiff = std::max(maxDiff, d); sumDiff += d; ++n; }
            }
            if (gc.screenState == ScreenState::BATTLE) { BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc); }
            else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) search::GameAction(chooseMapAction(gc)).execute(gc);
            else agent.stepOutOfCombatPolicy(gc);
        }
        std::printf("winnettest: %d samples  max|native-server| = %.6f  mean = %.6f\n", n, maxDiff, sumDiff / std::max(1, n));

    } else if (mode == "fightgen") {      // ONE pass -> BOTH value (endHp) + policy (visit-pi) CSVs
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/vcombat.csv";
        std::string pout = argc > 7 ? argv[7] : "build/vpolicy.csv";
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        fightGen(nSeeds, sims, asc, eps, vout, pout, seedOff);

    } else if (mode == "causalgen") {     // CSV of (state, card features, CRN advantage) for causal card value
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 200;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int N         = argc > 4 ? std::stoi(argv[4]) : 6;
        int innerSims = argc > 5 ? std::stoi(argv[5]) : 800;
        int K         = argc > 6 ? std::stoi(argv[6]) : 6;
        double eps    = argc > 7 ? std::stod(argv[7]) : 0.30;
        std::string out = argc > 8 ? argv[8] : "causal.csv";
        causalGen(nSeeds, sims, /*asc=*/0, N, innerSims, K, eps, out);

    } else if (mode == "carddump") {      // id,name,type,rarity,obtainWeight,baseDamage for all card ids
        std::cout << "id,name,type,rarity,obtainWeight,baseDamage\n";
        for (int i = 0; i < kNumCardIds; ++i) {
            Card c((CardId)i);
            std::cout << i << ',' << c.getName() << ',' << (int)c.getType() << ','
                      << (int)c.getRarity() << ',' << search::Expert::getObtainWeight((CardId)i)
                      << ',' << c.getBaseDamage() << '\n';
        }

    } else if (mode == "deck") {          // dump final deck+relics of one run (eval+path)
        std::uint64_t sd = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims         = argc > 3 ? std::stoi(argv[3]) : 4000;
        int asc          = argc > 4 ? std::stoi(argv[4]) : 0;
        dumpRun(sd, sims, asc);

    } else if (mode == "cardbench") {     // weighted table vs greedy argmax drafting
        int sims      = argc > 2 ? std::stoi(argv[2]) : 4000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 64;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double skipR  = argc > 5 ? std::stod(argv[5]) : 1.0;
        search::g_fairPlay = argc > 6 ? std::stoi(argv[6]) != 0 : false;
        int onlyPolicy = argc > 7 ? std::stoi(argv[7]) : -1;  // -1=all, else 0..5
        g_learnedNeverSkip = argc > 8 ? std::stoi(argv[8]) != 0 : false;
        g_tableAlpha = argc > 9 ? std::stod(argv[9]) : 1.0;   // eval+causal fusion weight
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS]\n";
        cardBench(sims, nSeeds, asc, skipR, onlyPolicy);

    } else if (mode == "combobench") {    // baseline vs (greedy draft + heuristic path)
        int sims      = argc > 2 ? std::stoi(argv[2]) : 4000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 128;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double skipR  = argc > 5 ? std::stod(argv[5]) : 0.0;
        search::g_fairPlay = argc > 6 ? std::stoi(argv[6]) != 0 : false;
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS]\n";
        comboBench(sims, nSeeds, asc, skipR);

    } else if (mode == "pathbench") {     // random path vs heuristic path
        int sims   = argc > 2 ? std::stoi(argv[2]) : 8000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 32;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        pathBench(sims, nSeeds, asc);

    } else if (mode == "restbench") {     // default rest heuristic vs value policy (needs v_server.py)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 2000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 96;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        restBench(sims, nSeeds, asc);

    } else if (mode == "shopbench") {     // default shop heuristic vs V-knapsack (needs v_server.py)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        shopBench(sims, nSeeds, asc);

    } else if (mode == "allbench") {      // all-default vs rest-V + shop-V together (needs v_server.py)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        allOOCBench(sims, nSeeds, asc);

    } else if (mode == "skipbench") {     // single-arm card-skip sweep point (env STS_SKIP_THR; needs v_server.py)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        skipBench(sims, nSeeds, asc);

    } else if (mode == "bestbench") {     // current best OOC stack, single arm (baseline for new experiments)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seedOffset = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        bestBench(sims, nSeeds, asc, seedOffset, resultsFile);

    } else if (mode == "reprobench") {    // repeat one full run in one process; audit determinism
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        int repeats = argc > 3 ? std::stoi(argv[3]) : 2;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seed = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        std::cout << "[reprobench: seed " << seed << ", repeats " << repeats << "]\n";
        for (int i = 0; i < repeats; ++i) bestBench(sims, 1, asc, seed, resultsFile);

    } else if (mode == "runtrace") {      // per-node human-readable trace of ONE seed (STS_FAIR for fair-play)
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc  = argc > 4 ? std::stoi(argv[4]) : 0;
        runTraceRun(seed, sims, asc);

    } else {
        std::cerr << "usage: one_combat [bench|mcts|random|run|runbench|evalcombat|evalrun|draftbench|pathbench|cardbench|combobench|datagen|deck] ...\n";
        return 1;
    }
    return 0;
}
