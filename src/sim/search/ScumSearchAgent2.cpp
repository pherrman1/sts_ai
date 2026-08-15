//
// Created by keega on 9/19/2021.
//

#include "sim/search/ScumSearchAgent2.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <cmath>
#include <chrono>
#include <limits>
#include <mutex>
#include <sim/search/ExpertKnowledge.h>
#include <game/Game.h>
#include "sim/PrintHelpers.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/SimHealth.h"

bool g_collectKeys = false;  // STS_COLLECT_KEYS=1: collect act-4 keys

// Stall guard: a battle exceeding this many search decisions is treated as a
// loss. StS has no stall timer, so a fight can in principle last forever, and
// the search can exploit that (e.g. blocking forever against a boss instead of
// finishing) — spinning playoutBattle* at one core with zero progress and no
// rows written (observed on datagen seed 300865, 2026-08-08). Normal battles
// finish in well under 100 decisions.
static constexpr int kMaxBattleDecisions = 1000;
#include "sim/search/BattleScumSearcher3.h"

using namespace sts;

namespace sts::search {
    thread_local std::function<void(const BattleContext&)> g_onCombatDecision = nullptr;
    thread_local std::function<void(const BattleContext&, const BattleScumSearcher2&)> g_onSearchComplete = nullptr;
    thread_local std::function<void(const BattleContext&, const BattleScumSearcher3&)> g_onSearchComplete3 = nullptr;
}

namespace {
// Root-action pick for Searcher3. Default (g_s3Live): most-visited live-valid
// edge. Ablation (g_s3Live=0): Searcher2-style most-visited edge with no
// live-valid filter; an invalid most-visited edge yields no action, ending the
// battle exactly like the Searcher2 loop breaks out.
search::Action s3PickRootAction(const search::BattleScumSearcher3 &s3,
                                const BattleContext &bc, bool &have) {
    have = false;
    if (search::g_s3Live) {
        std::int64_t bestVisits = -1;
        search::Action bestAction;
        for (const auto &e : s3.root.edges) {
            if (e.child.simulationCount > bestVisits && e.action.isValidAction(bc)) {
                bestVisits = e.child.simulationCount; bestAction = e.action; have = true;
            }
        }
        return bestAction;
    }
    std::int64_t maxVisits = -1;
    search::Action bestAction;
    for (const auto &e : s3.root.edges) {
        if (e.child.simulationCount > maxVisits) {
            maxVisits = e.child.simulationCount; bestAction = e.action; have = true;
        }
    }
    if (!have || !bestAction.isValidAction(bc)) { have = false; return {}; }
    return bestAction;
}
} // namespace

void search::ScumSearchAgent2::takeAction(GameContext &gc, search::GameAction a) {
    if (printActions) {
        gameActionHistory.emplace_back(a.bits);
        std::cout << std::hex << a.bits << std::endl;
    }
    a.execute(gc);
}

void search::ScumSearchAgent2::takeAction(BattleContext &bc, search::Action a) {
    if (printActions) {
        gameActionHistory.emplace_back(a.bits);
        std::cout << std::hex << a.bits << std::endl;
    }
    // Simulator health: an action committed to the live battle state must be
    // legal on that exact state. Detection-only (the action still executes),
    // so normal behavior is unchanged; this catches an invalid live commit in
    // release builds where the sts_asserts validity check is compiled out.
    if (bc.outcome == Outcome::UNDECIDED && !a.isValidAction(bc)) {
        reportSimHealthFailure(bc, SimHealthFailure::INVALID_LIVE_ACTION,
                               SimHealthMeta{-1, a.bits, true});
    }
//    a.printDesc(std::cout, bc);
    a.execute(bc);
}

void search::ScumSearchAgent2::playout(GameContext &gc) {
    paused = false;
    BattleContext bc{};
    const auto seedStr = std::string(SeedHelper::getString(gc.seed));

    while (gc.outcome == GameOutcome::UNDECIDED && !paused) {
        if (gc.screenState == ScreenState::BATTLE) {
            bc = BattleContext();
            bc.init(gc);

            playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        if (printLogs) {
            std::cout << gc << std::endl;
        }
        stepOutOfCombatPolicy(gc);
    }
}

static void printHelper(const BattleContext &bc, const search::Action &a) {
    a.printDesc(std::cout, bc) << " ";
    std::cout
            << " turn: " << bc.turn
            << " energy: " << bc.player.energy
            << " cardsPlayedThisTurn: " << bc.player.cardsPlayedThisTurn
            << " state: " << (bc.inputState == InputState::PLAYER_NORMAL ? "normal" : " probably card select")
            << std::endl;
    std::cout << bc << std::endl;
}

static double rootActionQ(const search::BattleScumSearcher3::Edge &edge) {
    return edge.child.simulationCount > 0
        ? edge.child.evaluationSum / edge.child.simulationCount
        : std::numeric_limits<double>::quiet_NaN();
}

static void writeS3BeliefBoundaryDiag(
    const BattleContext &bc, const search::BattleScumSearcher3 &s3,
    std::uint64_t seed, int decisionIdx, bool carried, bool boundaryUpdated,
    const search::RealBeliefFilterStats *filterStats = nullptr)
{
    if (!search::g_s3BeliefAudit || search::g_s3BeliefAuditFile.empty()) return;
    const auto obs = CombatObservation::fromBattleContext(bc);
    const int n = static_cast<int>(s3.belief.particles.size());
    const int compatible = s3.belief.compatibleCount(obs);
    const int fallback = s3.belief.fallbackShuffleCount(bc);
    double sumW = 0.0, sumW2 = 0.0;
    for (const auto &p : s3.belief.particles) {
        sumW += p.weight;
        sumW2 += p.weight * p.weight;
    }
    const double ess = sumW2 > 0.0 ? sumW * sumW / sumW2
                                   : std::numeric_limits<double>::quiet_NaN();

    static std::mutex mutex;
    static bool header = false;
    std::lock_guard<std::mutex> lock(mutex);
    std::ofstream out(search::g_s3BeliefAuditFile, std::ios::app);
    if (!out) return;
    if (!header) {
        out << "seed,floor,encounter,turn,decision_index,particles,compatible_particles,compatible_fraction,distinct_draw_orders,distinct_rng_signatures,ess,fallback_shuffles,fallback_fraction,stale_fraction,boundary_update_applied,belief_carried,belief_rebuilt,previous_particle_count,propagated_particles_attempted,propagation_failures,draw_pile_mismatch_particles,action_illegal_particles,filter_compatible,filter_compatible_fraction,filter_incompatible,posterior_collapse,distinct_surviving_draw_orders,distinct_surviving_rng_signatures,unique_hypotheses,filter_fallback_shuffles,reshuffle_observed,comparison_exact,filter_cpu_ms,weight_ess,action_bits,action_type,real_observation_hash,dominant_predicted_observation_hash,distinct_predicted_observations,dominant_predicted_observation_count,predicted_observation_entropy,collapse_category,fresh_belief_rebuilt,sensitivity_probed,sensitivity_64,sensitivity_128,sensitivity_256,sensitivity_512,sensitivity_cpu_ms,configured_particle_count,simulations,distinct_particles_sampled,sampled_particle_fraction,min_samples_per_sampled_particle,mean_samples_per_sampled_particle,median_samples_per_sampled_particle,max_samples_per_particle,never_sampled_particles,particle_usage_entropy,belief_initialization_cpu_ms,search_cpu_ms\n";
        header = true;
    }
    out << seed << ',' << bc.floorNum << ',' << static_cast<int>(bc.encounter)
        << ',' << bc.turn << ',' << decisionIdx << ',' << n << ','
        << compatible << ',' << (n > 0 ? static_cast<double>(compatible) / n : 0.0)
        << ',' << s3.belief.distinctCompatibleDrawOrders(obs)
        << ',' << s3.belief.distinctCompatibleRngSignatures(obs)
        << ',' << ess << ',' << fallback << ','
        << (n > 0 ? static_cast<double>(fallback) / n : 0.0) << ','
        << (n > 0 ? static_cast<double>(n - compatible) / n : 0.0) << ','
        << (boundaryUpdated ? 1 : 0) << ',' << (carried ? 1 : 0) << ','
        << (carried ? 0 : 1) << ','
        << (filterStats ? filterStats->previousParticles : n) << ','
        << (filterStats ? filterStats->attempted : 0) << ','
        << (filterStats ? filterStats->propagationFailures : 0) << ','
        << (filterStats ? filterStats->drawPileMismatch : 0) << ','
        << (filterStats ? filterStats->actionIllegal : 0) << ','
        << (filterStats ? filterStats->compatible : 0) << ','
        << (filterStats && filterStats->previousParticles > 0 ? static_cast<double>(filterStats->compatible) / filterStats->previousParticles : 0.0) << ','
        << (filterStats ? filterStats->incompatible : 0) << ','
        << (filterStats && filterStats->posteriorCollapse ? 1 : 0) << ','
        << (filterStats ? s3.belief.distinctPositiveDrawOrders() : 0) << ','
        << (filterStats ? s3.belief.distinctPositiveRngSignatures() : 0) << ','
        << (filterStats ? s3.belief.distinctPositiveHypotheses() : 0) << ','
        << (filterStats ? filterStats->fallbackShuffles : 0) << ','
        << (filterStats && filterStats->reshuffleObserved ? 1 : 0) << ','
        << (filterStats && filterStats->comparisonExact ? 1 : 0) << ','
        << (filterStats ? filterStats->cpuMs : 0.0) << ','
        << (filterStats ? static_cast<double>(s3.belief.positiveCount()) : ess) << ','
        << (filterStats ? filterStats->actionBits : 0) << ','
        << (filterStats ? filterStats->actionType : -1) << ','
        << (filterStats ? filterStats->realObservationHash : 0) << ','
        << (filterStats ? filterStats->dominantPredictedObservationHash : 0) << ','
        << (filterStats ? filterStats->distinctPredictedObservations : 0) << ','
        << (filterStats ? filterStats->dominantPredictedObservationCount : 0) << ','
        << (filterStats ? filterStats->predictedObservationEntropy : 0.0) << ','
        << (filterStats ? filterStats->collapseCategory : std::string()) << ','
        << (filterStats && filterStats->freshBeliefRebuilt ? 1 : 0) << ','
        << (filterStats && filterStats->sensitivityProbed ? 1 : 0) << ','
        << (filterStats ? filterStats->sensitivity64 : -1) << ','
        << (filterStats ? filterStats->sensitivity128 : -1) << ','
        << (filterStats ? filterStats->sensitivity256 : -1) << ','
        << (filterStats ? filterStats->sensitivity512 : -1) << ','
        << (filterStats ? filterStats->sensitivityCpuMs : 0.0) << ','
        << (filterStats ? filterStats->configuredParticleCount : n) << ','
        << (filterStats ? filterStats->simulations : 0) << ','
        << (filterStats ? filterStats->distinctParticlesSampled : 0) << ','
        << (filterStats ? filterStats->sampledParticleFraction : 0.0) << ','
        << (filterStats ? filterStats->minSamplesPerParticle : 0) << ','
        << (filterStats ? filterStats->meanSamplesPerSampledParticle : 0.0) << ','
        << (filterStats ? filterStats->medianSamplesPerSampledParticle : 0.0) << ','
        << (filterStats ? filterStats->maxSamplesPerParticle : 0) << ','
        << (filterStats ? filterStats->neverSampledParticles : 0) << ','
        << (filterStats ? filterStats->particleUsageEntropy : 0.0) << ','
        << (filterStats ? filterStats->beliefInitializationCpuMs : 0.0) << ','
        << (filterStats ? filterStats->searchCpuMs : 0.0) << '\n';
}

enum class S3NextSearchBeliefSource {
    UNRESOLVED,
    FRESH_INITIAL,
    TRANSFERRED_FILTERED_POSTERIOR,
};

struct S3FilteredBoundary {
    std::uint64_t seed;
    int floor;
    int encounter;
    int decisionIndex;
    bool collapseFresh;
    S3NextSearchBeliefSource source = S3NextSearchBeliefSource::UNRESOLVED;
};

static void writeS3NextSearchBeliefDiag(
    const std::vector<S3FilteredBoundary> &boundaries, bool nextSearch) {
    if (!search::g_s3BeliefAudit || search::g_s3BeliefAuditFile.empty()) return;

    static std::mutex mutex;
    static bool header = false;
    std::lock_guard<std::mutex> lock(mutex);
    std::ofstream out(search::g_s3BeliefAuditFile + ".next_search.csv", std::ios::app);
    if (!out) return;
    if (!header) {
        out << "seed,floor,encounter,decision_index,next_search_belief_source\n";
        header = true;
    }
    for (const auto &boundary : boundaries) {
        const char *source = "no_next_search";
        if (nextSearch) {
            if (boundary.source == S3NextSearchBeliefSource::FRESH_INITIAL)
                source = "fresh_initial";
            else if (boundary.source == S3NextSearchBeliefSource::TRANSFERRED_FILTERED_POSTERIOR)
                source = "transferred_filtered_posterior";
            else
                source = boundary.collapseFresh ? "collapse_fresh"
                                                 : "existing_filtered_posterior";
        }
        out << boundary.seed << ',' << boundary.floor << ',' << boundary.encounter
            << ',' << boundary.decisionIndex << ',' << source << '\n';
    }
}

static void writeS3RootRaceDiag(const BattleContext &bc,
                                std::uint64_t seed, int decisionIdx)
{
    if (!search::g_s3RootRaceDiag || search::g_s3RootRaceDiagFile.empty()) return;
    static thread_local std::uint64_t capturedSeed = std::numeric_limits<std::uint64_t>::max();
    static thread_local int capturedStates = 0;
    if (capturedSeed != seed) { capturedSeed = seed; capturedStates = 0; }
    if (capturedStates >= search::g_s3RootRaceDiagMaxStates) return;
    ++capturedStates;

    constexpr std::array<int,4> budgets = {250, 500, 1000, 4000};
    struct Row {
        std::array<std::int64_t,4> visits{};
        std::array<double,4> q{};
        double prior = 0.0;
        int availability = -1;
    };
    std::map<std::uint32_t, Row> rows;
    std::array<std::uint32_t,4> chosen{};
    for (auto &v : chosen) v = std::numeric_limits<std::uint32_t>::max();

    for (size_t bi = 0; bi < budgets.size(); ++bi) {
        search::BattleScumSearcher3 probe(
            bc, bc.seed, decisionIdx, search::g_s3Particles);
        probe.search(budgets[bi]);
        probe.computeEdgeAvailability(bc);
        bool have = false;
        const auto picked = s3PickRootAction(probe, bc, have);
        if (have) chosen[bi] = picked.bits;
        for (size_t ei = 0; ei < probe.root.edges.size(); ++ei) {
            const auto &edge = probe.root.edges[ei];
            auto &row = rows[edge.action.bits];
            row.visits[bi] = edge.child.simulationCount;
            row.q[bi] = rootActionQ(edge);
            row.prior = edge.prior;
            if (ei < probe.edgeAvailability.size())
                row.availability = probe.edgeAvailability[ei];
        }
    }

    const auto bestBits = chosen[3];
    double bestQ = std::numeric_limits<double>::quiet_NaN();
    auto bestIt = rows.find(bestBits);
    if (bestIt != rows.end()) bestQ = bestIt->second.q[3];

    static std::mutex mutex;
    static bool header = false;
    std::lock_guard<std::mutex> lock(mutex);
    std::ofstream out(search::g_s3RootRaceDiagFile, std::ios::app);
    if (!out) return;
    if (!header) {
        out << "seed,floor,encounter,turn,decision_index,input_state,"
               "particle_count,n_actions,action_bits,legal_now,availability,"
               "chosen_250,chosen_500,chosen_1000,chosen_4000,best_4000,"
               "visits_250,q_250,visits_500,q_500,visits_1000,q_1000,"
               "visits_4000,q_4000,deep_regret\n";
        header = true;
    }
    for (const auto &kv : rows) {
        const auto &row = kv.second;
        const double regret = (std::isnan(bestQ) || std::isnan(row.q[3]))
            ? std::numeric_limits<double>::quiet_NaN() : bestQ - row.q[3];
        out << seed << ',' << bc.floorNum << ',' << static_cast<int>(bc.encounter)
            << ',' << bc.turn << ',' << decisionIdx
            << ',' << static_cast<int>(bc.inputState)
            << ',' << search::g_s3Particles << ',' << rows.size() << ','
            << kv.first << ',' << (search::Action(kv.first).isValidAction(bc) ? 1 : 0)
            << ',' << row.availability << ','
            << chosen[0] << ',' << chosen[1] << ',' << chosen[2] << ','
            << chosen[3] << ',' << bestBits << ','
            << row.visits[0] << ',' << row.q[0] << ','
            << row.visits[1] << ',' << row.q[1] << ','
            << row.visits[2] << ',' << row.q[2] << ','
            << row.visits[3] << ',' << row.q[3] << ',' << regret << '\n';
    }
}
// Fair-play / determinized battle: each search re-randomizes the hidden draw
// order per simulation, so the recommended line is world-specific -- we can only
// commit the ONE most-visited root move, then re-search as the real draw reveals.
namespace {

using namespace sts::search;

void playoutBattleFairSearcher3(search::ScumSearchAgent2 &agent, BattleContext &bc) {
        int decisionIdx = 0;
        int fightPool = 0;
        int stallCount = 0;
        // Reuse-frequency tracking.
        int reuseAttempts = 0, reuseAccepted = 0;
        int reuseRejObsMismatch = 0, reuseRejHashMismatch = 0, reuseRejOther = 0;
        int combatDecisions = 0;
        // Per-agent carried-search counter (fixes STS_REUSE_MAX_SEARCHES).
        // Incremented after every search; reset only on fresh-searcher
        // construction. Checked against g_reuseMaxSearches BEFORE searching.
        int carriedSearchesSinceFresh = 0;
        // Generation histogram for cascade mode.
        int maxCarriedGen = 0;
        std::map<int,int> genHistogram;
        std::vector<S3FilteredBoundary> pendingFilteredBoundaries;

        BattleScumSearcher3 s3(bc, bc.seed, decisionIdx, search::g_s3Particles);
        bool searcherValid = true;
        while (bc.outcome == Outcome::UNDECIDED) {
            if (g_onCombatDecision) g_onCombatDecision(bc);
            ++combatDecisions;
            if (++stallCount > kMaxBattleDecisions) {
                std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                          << " exceeded " << kMaxBattleDecisions
                          << " search decisions (fair S3); treating battle as LOSS\n";
                bc.outcome = Outcome::PLAYER_LOSS;
                break;
            }
            // Reuse gate: rebuild when searcher invalid, or when the
            // carried-search counter exceeds the configured maximum.
            if (!searcherValid) {
                s3 = BattleScumSearcher3(bc, bc.seed, decisionIdx, search::g_s3Particles);
                for (auto &boundary : pendingFilteredBoundaries)
                    boundary.source = S3NextSearchBeliefSource::FRESH_INITIAL;
                carriedSearchesSinceFresh = 0;
                maxCarriedGen = 0;
                searcherValid = true;
            } else if (search::g_reuseMaxSearches >= 0
                       && carriedSearchesSinceFresh > search::g_reuseMaxSearches) {
                s3 = BattleScumSearcher3(bc, bc.seed, decisionIdx, search::g_s3Particles);
                for (auto &boundary : pendingFilteredBoundaries)
                    boundary.source = S3NextSearchBeliefSource::FRESH_INITIAL;
                carriedSearchesSinceFresh = 0;
                maxCarriedGen = 0;
            }
            const std::int64_t sims = isBossEncounter(bc.encounter)
                ? (agent.bossSimulationMultiplier * agent.simulationCountBase) : agent.simulationCountBase;
            // Forced-action contraction: exactly one legal action -> commit
            // directly. No search runs, so no tree to carry forward — rebuild.
            search::Action forced;
            if (search::g_forcedMoveSkip && s3.onlyLegalAction(forced)) {
                if (search::g_s3PoolRedirect) fightPool += sims;
                BattleContext preState = bc;
                agent.takeAction(bc, forced);
                search::RealBeliefFilterStats filterStats;
                const bool filtered = search::g_s3RealBeliefFilter;
                if (filtered) filterStats = s3.filterRealTransition(preState, forced, bc);
                writeS3BeliefBoundaryDiag(bc, s3, bc.seed, decisionIdx, false, filtered, filtered ? &filterStats : nullptr);
                if (filtered) {
                    pendingFilteredBoundaries.push_back({bc.seed, bc.floorNum,
                        static_cast<int>(bc.encounter), decisionIdx,
                        filterStats.freshBeliefRebuilt});
                }
                ++decisionIdx;
                searcherValid = false;
                continue;
            }
            // STS_S3_POOL_REDIRECT (opt-in).
            std::int64_t spend = sims;
            if (search::g_s3PoolRedirect && fightPool > 0) {
                constexpr double poolFrac = 1.0;
                const std::int64_t extra = std::min<std::int64_t>(
                    fightPool, static_cast<std::int64_t>(std::llround(sims * poolFrac)));
                fightPool -= static_cast<int>(extra);
                spend += extra;
            }
            const std::int64_t before = s3.root.simulationCount;
            writeS3NextSearchBeliefDiag(pendingFilteredBoundaries, true);
            pendingFilteredBoundaries.clear();
            // Per-search CPU diagnostic snapshot.
            BattleScumSearcher3::DiagSnapshot diagBefore;
            const char *searchKind = (carriedSearchesSinceFresh > 0) ? "carried" : "fresh";
            if (search::g_reuseCpuDiag) {
                diagBefore = s3.snapshotDiag();
            }
            s3.search(spend);
            if (search::g_reuseCpuDiag) {
                auto diagAfter = s3.snapshotDiag();
                s3.writeCpuDiagRow(
                    bc.seed, (int)bc.floorNum, (int)bc.encounter,
                    0, decisionIdx, searchKind, s3.reuseGeneration,
                    carriedSearchesSinceFresh, spend,
                    diagBefore, diagAfter,
                    before, s3.root.simulationCount,
                    s3.retainedNodeCount, (int)s3.root.edges.size(),
                    bc.player.curHp, bc.turn, bc.cards.cardsInHand,
                    (int)bc.cards.drawPile.size(),
                    (int)bc.cards.discardPile.size());
            }
            // Increment carried-search counter after every search.
            ++carriedSearchesSinceFresh;
            agent.simulationCountTotal += s3.root.simulationCount - before;
            if (g_onSearchComplete3) g_onSearchComplete3(bc, s3);
            writeS3RootRaceDiag(bc, bc.seed, decisionIdx);
            s3.clampRankCorrAtRoot();
            s3.rankCorrValues.clear();
            // Edge-availability and reuse diagnostics.
            if (search::g_reuseDiag || search::g_s3SemanticCardEdges || search::g_s3BeliefAudit) {
                s3.computeEdgeAvailability(bc);
                s3.printReuseDiagnostics();
            }
            // Belief audit: print per-search belief stats.
            if (search::g_s3BeliefAudit) {
                double ess = 0.0;
                double sumW = 0.0, sumW2 = 0.0;
                int nonzero = 0;
                for (const auto &p : s3.belief.particles) {
                    if (p.weight > 0) { ++nonzero; sumW += p.weight; sumW2 += p.weight * p.weight; }
                }
                if (sumW2 > 0) ess = sumW * sumW / sumW2;
                std::cerr << "[belief-audit] nonzero=" << nonzero
                          << "/" << s3.belief.particles.size()
                          << " ESS=" << ess
                          << " updates=" << t_baUpdatesDuringSearch
                          << " zeroed=" << t_baParticlesZeroed
                          << " allZeroCalls=" << t_baAllZeroEvents
                          << " unifAllZero=" << t_baUniformAllZeroCalls
                          << " unifEqual=" << t_baUniformEqualCalls
                          << " applyExact=" << t_baApplyExactOrder
                          << " applyFallback=" << t_baApplyFallbackShuffle
                          << "\n";
                // Reset counters for next search.
                t_baUpdatesDuringSearch = 0;
                t_baParticlesZeroed = 0;
                t_baAllZeroEvents = 0;
                t_baUniformAllZeroCalls = 0;
                t_baUniformEqualCalls = 0;
                t_baApplyExactOrder = 0;
                t_baApplyFallbackShuffle = 0;
            }
            bool have = false;
            search::Action bestAction = s3PickRootAction(s3, bc, have);
            if (!have) {
                if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                    std::cerr << "[battle-break] state=" << (int)bc.inputState
                              << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                              << " pickCount=" << bc.cardSelectInfo.pickCount
                              << " hand=" << bc.cards.cardsInHand
                              << " outcome=" << (int)bc.outcome << "\n";
                // Simulator health: root selection returned no usable action.
                // `have=false` alone does not prove the live state is stuck
                // (with g_s3Live=0 the most-visited stored edge can be invalid
                // while other live actions are legal), so classify against the
                // canonical live action set.
                reportSimHealthFailure(bc, classifySelectionFailure(bc),
                                       SimHealthMeta{decisionIdx});
                break;
            }
            // Snapshot pre-state for carry diagnostic.
            BattleContext preState = bc;
            // Snap all 6 RNG counters.
            std::array<std::int32_t,6> rngSnaps = {{
                bc.shuffleRng.counter, bc.cardRandomRng.counter,
                bc.aiRng.counter, bc.miscRng.counter,
                bc.monsterHpRng.counter, bc.potionRng.counter}};
            agent.takeAction(bc, bestAction);
            search::RealBeliefFilterStats filterStats;
            const bool filtered = search::g_s3RealBeliefFilter;
            if (filtered) filterStats = s3.filterRealTransition(preState, bestAction, bc);
            bool rngSafe = (bc.aiRng.counter       == rngSnaps[2])
                        && (bc.cardRandomRng.counter == rngSnaps[1])
                        && (bc.miscRng.counter     == rngSnaps[3])
                        && (bc.monsterHpRng.counter == rngSnaps[4])
                        && (bc.potionRng.counter   == rngSnaps[5])
                        && (bc.shuffleRng.counter  == rngSnaps[0]);

            // Look up the promoted child for diagnostics and obs-stable check.
            const BattleScumSearcher3::Node *promotedChild = nullptr;
            for (const auto &e : s3.root.edges) {
                if (e.action == bestAction) { promotedChild = &e.child; break; }
            }

            // ── Carry diagnostics ─────────────────────────────────────
            if (search::g_reuseCarryDiag)
                s3.printCarryDiagnostic(bestAction, preState, bc, promotedChild, rngSnaps);

            // ── Observation-stable reuse gate ─────────────────────────
            bool obsStable = false;
            if (promotedChild && search::g_reuseObsStable) {
                std::uint64_t newHash =
                    CombatObservation::fromBattleContext(bc).visibleHash();
                obsStable = promotedChild->isObsStable()
                         && promotedChild->firstObsHash == newHash;
            }
            bool reuseAllowed;
            if (search::g_reuseObsStable) {
                reuseAllowed = obsStable;
                ++reuseAttempts;
                if (!reuseAllowed) {
                    if (promotedChild && !promotedChild->isObsStable())
                        ++reuseRejObsMismatch;
                    else if (promotedChild)
                        ++reuseRejHashMismatch;
                    else
                        ++reuseRejOther;
                }
            } else {
                reuseAllowed = rngSafe;
            }

            bool carriedAtBoundary = false;
            if (reuseAllowed && s3.advanceRoot(bestAction, bc)) {
                carriedAtBoundary = true;
                if (search::g_reuseObsStable) ++reuseAccepted;
                // ── Root reconciliation ────────────────────────────────
                if (search::g_reuseReconcileRoot)
                    s3.reconcileRoot(bc);

                // ── Generation tracking for cascade mode ───────────────
                int gen = s3.reuseGeneration;
                if (gen > maxCarriedGen) maxCarriedGen = gen;
                if (gen > 0) ++genHistogram[gen];

                ++decisionIdx;
                s3.decisionIndex = decisionIdx;
                s3.reseed();
                // Keep the promoted tree. The counter check at the top of
                // the loop will rebuild when the budget is exhausted.
                searcherValid = true;
            } else {
                ++decisionIdx;
                searcherValid = false;
            }
            writeS3BeliefBoundaryDiag(bc, s3, bc.seed, decisionIdx - 1, carriedAtBoundary, filtered, filtered ? &filterStats : nullptr);
            if (filtered) {
                pendingFilteredBoundaries.push_back({bc.seed, bc.floorNum,
                    static_cast<int>(bc.encounter), decisionIdx - 1,
                    filterStats.freshBeliefRebuilt});
            }
        }
        writeS3NextSearchBeliefDiag(pendingFilteredBoundaries, false);
        // Simulator health: the loop exited while the battle was still
        // UNDECIDED. The stall guard converts stalls to PLAYER_LOSS before
        // breaking, so only an unintentional unresolved exit reaches this.
        if (bc.outcome == Outcome::UNDECIDED) {
            reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT,
                                   SimHealthMeta{decisionIdx});
        }
        // Print reuse diagnostics at end of battle.
        if (search::g_reuseDiag || (search::g_reuseObsStable && combatDecisions > 0)) {
            std::cerr << "[reuse-generation] fresh=" << (combatDecisions - reuseAttempts)
                      << " carriedSearchesSinceFresh=" << carriedSearchesSinceFresh
                      << " maxGen=" << maxCarriedGen;
            if (search::g_reuseObsStable) {
                std::cerr << " attempted=" << reuseAttempts
                          << " accepted=" << reuseAccepted
                          << " rej-obsMismatch=" << reuseRejObsMismatch
                          << " rej-hashMismatch=" << reuseRejHashMismatch
                          << " rej-other=" << reuseRejOther;
            }
            if (!genHistogram.empty()) {
                std::cerr << " genHist=[";
                bool first = true;
                for (auto &p : genHistogram) {
                    if (!first) std::cerr << ",";
                    std::cerr << "g" << p.first << ":" << p.second;
                    first = false;
                }
                std::cerr << "]";
            }
            std::cerr << "\n";
        }

}

void playoutBattleFairSearcher2(search::ScumSearchAgent2 &agent, BattleContext &bc) {
std::int64_t fightPool = 0;   // STS_CONV_ROOT: per-fight sim credit pool (budget-neutral reinvestment)
    int stallCount = 0;
    while (bc.outcome == Outcome::UNDECIDED) {
        if (g_onCombatDecision) g_onCombatDecision(bc);   // snapshot state (fair-play value datagen)
        if (++stallCount > kMaxBattleDecisions) {
            std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                      << " exceeded " << kMaxBattleDecisions
                      << " search decisions (fair S2); treating battle as LOSS\n";
            bc.outcome = Outcome::PLAYER_LOSS;
            break;
        }
        const std::int64_t simulationCount = isBossEncounter(bc.encounter) ?
                                             (agent.bossSimulationMultiplier * agent.simulationCountBase) : agent.simulationCountBase;
        search::BattleScumSearcher2 searcher(bc);
        // Forced-action contraction (default ON in the fair path; inside the
        // STS_CONV_ROOT arm it also fires on g_convRootStop): exactly one legal
        // action -> commit directly, no search. Enumerated on the live root
        // state, so it fires only when the move is truly forced in every
        // determinization. Decision-neutral (fresh searcher per decision);
        // two independent 256-seed gates confirm exact outcome equality at
        // −16-18% cpu (§120/§121). Note: forced decisions skip the search, so
        // g_onSearchComplete (searchdiag A rows) does not fire for them.
        search::Action forced;
        if (search::g_forcedMoveSkip || search::g_convRootStop) {
            if (searcher.onlyLegalAction(forced)) { agent.takeAction(bc, forced); continue; }
        }
        if (search::g_convRootStop) {
            // Root-stability adaptive budget (STS_CONV_ROOT): each decision credits
            // its flat budget to a per-fight pool; forced moves skip the search and
            // obvious decisions stop early, so ambiguous ones can escalate up to
            // g_convRootMaxFrac x the flat target without exceeding flat total cpu
            // (see BattleScumSearcher2::searchToTotalRootStable).
            fightPool += simulationCount;
            const std::int64_t cap = std::min(fightPool,
                static_cast<std::int64_t>(std::llround(simulationCount * search::g_convRootMaxFrac)));
            searcher.searchToTotalRootStable(cap, search::g_convRootMinSims, search::g_convRootPatience);
            fightPool -= searcher.root.simulationCount;
        } else {
            searcher.search(simulationCount);
        }
        agent.simulationCountTotal += searcher.root.simulationCount;

        // policy-target datagen: log this root's edge visit distribution (fair-play prior)
        if (g_onSearchComplete) g_onSearchComplete(bc, searcher);

        // Experimental STS_VNET_RANK_CORR: zero-mean clamp at search-complete
        // (before the root action pick). Same semantics as the Searcher3 fair
        // path: subtract the mean per-search correction from each root edge's
        // stored mean value; visit counts are untouched, so the most-visited
        // root action is unchanged. No-op when the correction model is not
        // loaded (rankCorrValues empty).
        searcher.clampRankCorrAtRoot();

        // Robust ISMCTS move = the most-visited root child (best averaged over worlds).
        std::int64_t maxSim = -1;
        search::Action best;
        bool have = false;
        for (const auto &e : searcher.root.edges) {
            if (e.node.simulationCount > maxSim) { maxSim = e.node.simulationCount; best = e.action; have = true; }
        }
        if (!have) {
            if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                std::cerr << "[battle-break:s2] state=" << (int)bc.inputState
                          << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                          << " pickCount=" << bc.cardSelectInfo.pickCount << "\n";
            // Simulator health: the fair-S2 root is enumerated on the live
            // visible state (determinization changes only hidden draw order /
            // RNG, never the visible state that action legality depends on),
            // so an empty search root is equivalent to zero canonical live
            // legal actions; classify via the canonical check for uniformity.
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;   // no legal move (shouldn't happen pre-terminal)
        }
        if (!best.isValidAction(bc)) {
            if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                std::cerr << "[battle-break:s2] state=" << (int)bc.inputState
                          << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                          << " pickCount=" << bc.cardSelectInfo.pickCount << "\n";
            // Simulator health: the chosen (most-visited) root action cannot
            // execute on the live state. Nothing is committed here, so this is
            // a selection failure (ACTION_SELECTION_FAILED when legal live
            // actions exist, NO_LEGAL_PROGRESSION otherwise) -- not an
            // INVALID_LIVE_ACTION commit.
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;   // no legal move (shouldn't happen pre-terminal)
        }

        if (agent.printLogs) printHelper(bc, best);
        agent.takeAction(bc, best);
    }
    // Simulator health: the loop exited while the battle was still UNDECIDED
    // (the stall guard sets PLAYER_LOSS first, so this is an unresolved exit).
    if (bc.outcome == Outcome::UNDECIDED) {
        reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT);
    }

}

} // namespace

void search::ScumSearchAgent2::playoutBattleFair(BattleContext &bc) {
    if (search::g_useSearcher3) {
        playoutBattleFairSearcher3(*this, bc);
        return;
    }
    playoutBattleFairSearcher2(*this, bc);
}

void search::ScumSearchAgent2::playoutBattle(BattleContext &bc) {
    if (bc.outcome != Outcome::UNDECIDED) {
        return;
    }
    if (search::g_fairPlay) {
        playoutBattleFair(bc);
        return;
    }
    if (search::g_useSearcher3) {
        int decisionIdx = 0;
        int stallCount = 0;
        BattleScumSearcher3 s3(bc, bc.seed, decisionIdx, search::g_s3Particles);
        while (bc.outcome == Outcome::UNDECIDED) {
            if (g_onCombatDecision) g_onCombatDecision(bc);
            if (++stallCount > kMaxBattleDecisions) {
                std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                          << " exceeded " << kMaxBattleDecisions
                          << " search decisions (non-fair S3); treating battle as LOSS\n";
                bc.outcome = Outcome::PLAYER_LOSS;
                break;
            }
            const std::int64_t sims = isBossEncounter(bc.encounter)
                ? (bossSimulationMultiplier * simulationCountBase) : simulationCountBase;
            const std::int64_t before = s3.root.simulationCount;
            s3.searchToTotal(sims);
            simulationCountTotal += s3.root.simulationCount - before;
            if (g_onSearchComplete3) g_onSearchComplete3(bc, s3);
            writeS3RootRaceDiag(bc, bc.seed, decisionIdx);
            bool have = false;
            search::Action bestAction = s3PickRootAction(s3, bc, have);
            if (!have) {
                if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                    std::cerr << "[battle-break:s3] state=" << (int)bc.inputState
                              << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                              << " pickCount=" << bc.cardSelectInfo.pickCount << "\n";
                // Simulator health: classify the root-selection failure
                // against the canonical live action set (see fair-S3 site).
                reportSimHealthFailure(bc, classifySelectionFailure(bc),
                                       SimHealthMeta{decisionIdx});
                break;
            }
            BattleContext preState = bc;
            takeAction(bc, bestAction);
            search::RealBeliefFilterStats filterStats;
            const bool filtered = search::g_s3RealBeliefFilter;
            if (filtered) filterStats = s3.filterRealTransition(preState, bestAction, bc);
            s3.advanceRoot(bestAction, bc);
            // Live belief update at the agent boundary: the real observation
            // after the committed action reweights the particles. The fair
            // S3 path skips this update: it carries the same searcher/belief
            // across decisions (advanceRoot + reuse gate) rather than
            // rebuilding fresh each decision, and does no boundary
            // reweighting, so the carried belief can go stale (issue #58).
            if (search::g_s3Belief)
                s3.belief.update(CombatObservation::fromBattleContext(bc));
            writeS3BeliefBoundaryDiag(bc, s3, bc.seed, decisionIdx, true, filtered || search::g_s3Belief, filtered ? &filterStats : nullptr);
            ++decisionIdx;
            s3.decisionIndex = decisionIdx;
            s3.reseed();
        }
        // Simulator health: the loop exited while the battle was still
        // UNDECIDED (the stall guard sets PLAYER_LOSS first, so this is an
        // unintentional unresolved exit).
        if (bc.outcome == Outcome::UNDECIDED) {
            reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT,
                                   SimHealthMeta{decisionIdx});
        }
        return;
    }

    std::vector<search::Action> bestActions;
    int bestOutcomePlayerHp = -1;

    // One searcher for the whole battle: after each action we re-root it onto the
    // played child (advanceRoot) instead of rebuilding, so the next decision reuses
    // the subtree we already searched. searchToTotal then only runs the shortfall.
    search::BattleScumSearcher2 searcher(bc);
    std::int64_t fightPool = 0;   // STS_CONV_ROOT: per-fight sim credit pool (budget-neutral reinvestment)
    int stallCount = 0;

    while (bc.outcome == Outcome::UNDECIDED) {
        if (g_onCombatDecision) g_onCombatDecision(bc);   // snapshot state for value-fn training
        if (++stallCount > kMaxBattleDecisions) {
            std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                      << " exceeded " << kMaxBattleDecisions
                      << " search decisions (non-fair S2); treating battle as LOSS\n";
            bc.outcome = Outcome::PLAYER_LOSS;
            break;
        }
        const std::int64_t simulationCount = isBossEncounter(bc.encounter) ?
                                              (bossSimulationMultiplier * simulationCountBase) : simulationCountBase;

        const std::int64_t before = searcher.root.simulationCount;
        // Forced-action contraction in the NON-FAIR path is scoped to the
        // STS_CONV_ROOT arm only. Standalone STS_FORCED_MOVE is not applied
        // here: the persistent searcher reuses the tree across decisions, so
        // skipping a forced-node search changes later trees and the shared RNG
        // stream (measured: 3/8 known-RNG diagnostic seeds diverge, §120
        // follow-up) — not decision-neutral, and the cpu saving is negligible
        // (non-fair makes ~2 decisions/fight). The fair path builds a fresh
        // searcher per decision, which is why the flag is neutral there.
        if (search::g_convRootStop) {
            // Forced move shortcut: exactly one legal action -> commit directly, no
            // search. Otherwise credit the flat budget to the fight pool and let the
            // root-stability search escalate ambiguous decisions up to the pool
            // (bounded by g_convRootMaxFrac x flat target); pool accounting keeps
            // total sims at or below the flat total.
            search::Action forced;
            if (searcher.onlyLegalAction(forced)) {
                takeAction(bc, forced);
                searcher.advanceRoot(forced, bc);
                // The search was skipped, so the cached winning line (bestActions /
                // bestOutcomePlayerHp) no longer starts at this root; reset it so the
                // next search re-derives a line from the new root. Without this, a
                // stale bestOutcomePlayerHp keeps stepThroughSolution running on an
                // empty action list forever (observed hang, seed 10 floor 11).
                bestActions.clear();
                bestOutcomePlayerHp = -1;
                continue;
            }
            fightPool += simulationCount;
            const std::int64_t cap = std::min(fightPool,
                static_cast<std::int64_t>(std::llround(simulationCount * search::g_convRootMaxFrac)));
            searcher.searchToTotalRootStable(cap, search::g_convRootMinSims, search::g_convRootPatience);
            fightPool -= searcher.root.simulationCount - before;
        } else
            searcher.searchToTotal(simulationCount);
        simulationCountTotal += searcher.root.simulationCount - before;   // only newly-run sims

        // policy-target datagen: log this root's edge visit distribution (if hooked)
        if (g_onSearchComplete) g_onSearchComplete(bc, searcher);

        if (searcher.outcomePlayerHp > bestOutcomePlayerHp)
        {
            bestActions = std::vector(
                    searcher.bestActionSequence.rbegin(),
                    searcher.bestActionSequence.rend());
            bestOutcomePlayerHp = searcher.outcomePlayerHp;
        }

        bool madeProgress = true;
        if (bestOutcomePlayerHp > 0) {
            madeProgress = stepThroughSolution(bc, bestActions, searcher);
        } else {
            madeProgress = stepThroughSearchTree(bc, searcher);
        }

        // Simulator health: a decision in which the tree-stepping machinery
        // committed zero actions while the battle is unresolved. Classify
        // against the canonical live action set so a genuinely stuck state is
        // diagnosed immediately instead of silently cycling to the 1000-
        // decision stall guard (which would become a synthetic PLAYER_LOSS
        // with no NO_LEGAL_PROGRESSION / UNDECIDED_BATTLE_EXIT diagnostic).
        // Non-fair S2 zero-progress rule: canonical actions == 0 →
        // NO_LEGAL_PROGRESSION; canonical actions > 0 → ACTION_SELECTION_FAILED.
        if (bc.outcome == Outcome::UNDECIDED && !madeProgress) {
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;
        }
    }
    // Simulator health: safety net for an unresolved exit of the non-fair S2
    // loop (the stall guard sets PLAYER_LOSS first, so this is unintentional).
    if (bc.outcome == Outcome::UNDECIDED) {
        reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT);
    }
}

// Returns true when at least one action was committed this call (the caller
// re-searches when the battle is still unresolved); false when the cached
// winning line was already empty/exhausted at entry (a zero-progress
// decision, classified by playoutBattle against the canonical live action
// set).
bool search::ScumSearchAgent2::stepThroughSolution(BattleContext &bc, std::vector<search::Action> &actions, search::BattleScumSearcher2 &searcher) {
    bool committed = false;
    for (int i = 0; i < stepsWithSolution; ++i) {
        if (actions.empty()) {
            break;
        }

        auto a = actions.back();
        if (printLogs) {
            printHelper(bc, a);
        }

        takeAction(bc, a);
        searcher.advanceRoot(a, bc);   // keep the subtree under the action we just played
        actions.pop_back();
        committed = true;

        if (bc.outcome != Outcome::UNDECIDED) {
            break;
        }
    }
    return committed;
}

// Returns true when at least one action was committed this call (or the
// battle finished); false when the persistent tree root has no edges at an
// unresolved decision (zero-progress, classified by playoutBattle against the
// canonical live action set).
bool search::ScumSearchAgent2::stepThroughSearchTree(BattleContext &bc, search::BattleScumSearcher2 &searcher) {
    bool committed = false;
    for (int actionCount = 0; actionCount < stepsNoSolution; ++actionCount) {
        if (bc.outcome != Outcome::UNDECIDED) {
            break;
        }

        // Most-visited child of the current (re-rooted) root -- equivalent to walking
        // down the tree, but done via advanceRoot so the subtree carries forward.
        std::int64_t maxSimulations = -1;
        search::Action maxAction;
        bool haveAction = false;

        for (const auto &edge : searcher.root.edges) {
            if (edge.node.simulationCount > maxSimulations) {
                maxSimulations = edge.node.simulationCount;
                maxAction = edge.action;
                haveAction = true;
            }
        }

        if (!haveAction) {
            break;
        }

        if (printLogs) {
            printHelper(bc, maxAction);
        }

        takeAction(bc, maxAction);
        searcher.advanceRoot(maxAction, bc);
        committed = true;
    }
    return committed;
}

void search::ScumSearchAgent2::stepRandom(GameContext &gc) {
    std::vector<search::GameAction> possibleActions(search::GameAction::getAllActionsInState(gc));
    std::uniform_int_distribution<int> distr(0, static_cast<int>(possibleActions.size())-1);
    const int randomChoice = distr(rng);
    auto a = possibleActions[randomChoice];
    takeAction(gc, a);
}

void search::ScumSearchAgent2::stepOutOfCombatPolicy(GameContext &gc) {
    ++stepCount;

    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN:
            stepEventPolicy(gc);
            break;

        case ScreenState::REWARDS:
            stepRewardsPolicy(gc);
            break;

        case ScreenState::TREASURE_ROOM: {
            bool openChest = true;
            if (gc.relics.has(RelicId::CURSED_KEY)) {
                openChest = gc.info.chestSize != ChestSize::LARGE;
            }
            takeAction(gc, !openChest);
            break;
        }

        case ScreenState::SHOP_ROOM: {
            bool purchased = false;
            for (int i = 0; i < 3; ++i) {
                if (gc.info.shop.relicPrice(i) != -1 &&  gc.gold >= gc.info.shop.relicPrice(i)) {
                    takeAction(gc, GameAction(GameAction::RewardsActionType::RELIC, i));
                    purchased = true;
                    break;
                }
            }
            if (!purchased) {
                stepRandom(gc);
                return;
            }
            break;
        }

        case ScreenState::CARD_SELECT: {
            cardSelectPolicy(gc);
            break;
        }

        case ScreenState::BOSS_RELIC_REWARDS: {
            int best = 10000;
            int bestIdx = 0;

            for (int i = 0; i < 3; ++i) {
                int value = search::Expert::getBossRelicOrdering(gc.info.bossRelics[i]);
                if (value < best) {
                    best = value;
                    bestIdx = i;
                }
            }
            takeAction(gc, bestIdx);
            break;
        }

        case ScreenState::REST_ROOM: {
            if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
                takeAction(gc, 2);   // recall: take the ruby key (act 3+)
            } else if (gc.curHp > 50 && gc.deck.getUpgradeableCount() > 0 && !gc.hasRelic(RelicId::FUSION_HAMMER)) {
                takeAction(gc, 1);
            } else if (gc.curHp < 15 && !gc.relics.has(RelicId::COFFEE_DRIPPER)){
                takeAction(gc, 0);
            } else {
                stepRandom(gc);
                return;
            }
            break;
        }

        case ScreenState::BATTLE:
        case ScreenState::INVALID:
            assert(false);
            break;

        case ScreenState::MAP_SCREEN:
        default:
            stepRandom(gc);
            return;
    }
}

void search::ScumSearchAgent2::cardSelectPolicy(GameContext &gc) {
    fixed_list<std::pair<int,int>, Deck::MAX_SIZE> selectOrder;

    for (int i = 0; i < gc.info.toSelectCards.size(); ++i) {
        const auto &c = gc.info.toSelectCards[i].card;

        auto playOrder = search::Expert::getPlayOrdering(c.getId());
        auto obtainWeight = search::Expert::getObtainWeight(c.getId());

        switch (gc.info.selectScreenType) {
            case CardSelectScreenType::TRANSFORM:
            case CardSelectScreenType::TRANSFORM_UPGRADE:
                if (c.getType() == CardType::CURSE) {
                    selectOrder.push_back( {i, playOrder} );
                } else {
                    selectOrder.push_back( {i, obtainWeight} );
                }
                break;

            case CardSelectScreenType::BONFIRE_SPIRITS:
            case CardSelectScreenType::REMOVE:
                selectOrder.push_back( {i, -obtainWeight} );
                break;

            case CardSelectScreenType::UPGRADE:
            case CardSelectScreenType::DUPLICATE:
            case CardSelectScreenType::OBTAIN:
            case CardSelectScreenType::BOTTLE:
                selectOrder.push_back( {i, -obtainWeight} );
                break;

            case CardSelectScreenType::INVALID:
            default:
                selectOrder.push_back({i, 0});
                break;
        }
    }
    std::sort(selectOrder.begin(), selectOrder.end(), [](auto a, auto b) { return a.second < b.second; });
    takeAction(gc, selectOrder.front().first);
}

void search::ScumSearchAgent2::stepRewardsPolicy(GameContext &gc) {
    auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount > 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::GOLD, 0));

    } else if (r.relicCount > 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::RELIC, 0));

    } else if (r.potionCount > 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::POTION, 0));

    } else if (g_collectKeys && r.emeraldKey) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::KEY));

    } else if (g_collectKeys && r.sapphireKey) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::KEY));

    } else if (r.cardRewardCount == 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::SKIP));

    } else {
        if (pauseOnCardReward) {
            paused = true;
            return;
        }
        weightedCardRewardPolicy(gc);
    }
}

double getAvgDeckWeight(const GameContext &gc) {
    int sum = 0;
    for (const auto &c : gc.deck.cards) {
        sum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    return (double) sum / gc.deck.size();
}

void search::ScumSearchAgent2::weightedCardRewardPolicy(GameContext &gc) {
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = r.cardRewardCount-1; rIdx >= 0; --rIdx) {

        const auto deckWeight = getAvgDeckWeight(gc);
        if (printLogs) {
            std::cout << "evaluating card reward " << rIdx << " avgDeckWeight: " << deckWeight << std::endl;
        }
        fixed_list<std::pair<int,double>,4> weights;
        double weightSum = 0;
        for (int cIdx = 0; cIdx < r.cardRewards[rIdx].size(); ++cIdx) {
            constexpr double act1AttackMultiplier = 1.4;

            const auto &c = r.cardRewards[rIdx][cIdx];
            double weight = std::pow(search::Expert::getObtainWeight(c.getId(), c.isUpgraded()), 1.2);
            if (gc.act == 1 && c.getType() == CardType::ATTACK) {
                weight *= act1AttackMultiplier;
            }

            weights.push_back({cIdx, weight});
            weightSum += weight;

            if (printLogs) {
                std::cout << "card:" << r.cardRewards[rIdx][cIdx] << " eval: " << weight << std::endl;
            }
        }

        // choose a weighted card
        int selection = 0;
        {
            std::uniform_real_distribution<double> distr(0,weightSum);
            double roll = distr(rng);
            double acc = 0;
            for (int i = 0; i < weights.size(); ++i) {
                acc += weights[i].second;
                if (roll <= acc) {
                    selection = weights[i].first;
                }
            }
        }

        bool skipCard = true;
        {
            std::uniform_real_distribution<double> distr(0,weights[selection].second + deckWeight*0.6);
            double roll = distr(rng);
            if (roll < weights[selection].second) {
                skipCard = false;
            }
        }

        if (skipCard) {
            takeAction(gc, GameAction(GameAction::RewardsActionType::CARD, rIdx, 5));

        } else {
            takeAction(gc, GameAction(GameAction::RewardsActionType::CARD, rIdx, weights[selection].first));
        }
    }
}

void search::ScumSearchAgent2::stepEventPolicy(GameContext &gc) {
    switch (gc.curEvent) {

        case Event::NEOW:
            if (gc.info.neowRewards[1].d == Neow::Drawback::CURSE || gc.info.neowRewards[2].d == Neow::Drawback::CURSE) {
                takeAction(gc, 0);
            } else {
                stepRandom(gc);
            }
            break;

        case Event::NOTE_FOR_YOURSELF:
        case Event::THE_DIVINE_FOUNTAIN:
            takeAction(gc, 0);
            break;

        case Event::BIG_FISH:
            takeAction(gc, 1);
            break;

        case Event::GOLDEN_IDOL: {
            if (gc.hasRelic(RelicId::GOLDEN_IDOL)) {
                takeAction(gc, 4);
            } else {
                takeAction(gc, 0);
            }
            break;
        }


        case Event::GHOSTS:
            takeAction(gc, 0);
            break;

        case Event::MASKED_BANDITS:
            takeAction(gc, 1);  // fight (25-35 gold + Red Mask + card reward), not lose-all-gold
            break;

        case Event::CURSED_TOME:
            if (gc.info.eventData == 0) {
                takeAction(gc, 0);
            } else {
                takeAction(gc, gc.info.eventData+1);
            }
            break;

        case Event::KNOWING_SKULL:
            takeAction(gc, 3);
            break;

        default:
            stepRandom(gc);
            return;
    }
}

