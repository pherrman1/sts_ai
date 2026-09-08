//
// BattleScumSearcher3.cpp: ISMCTS searcher with particle determinization
//
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatPVNet.h"
#include "combat/BattleContext.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <atomic>
#include <cmath>
#include <fstream>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <iomanip>
#include <unordered_set>
#include <unordered_map>

using namespace sts;

namespace sts::search {

extern double g_vnetAlpha;   // from BattleScumSearcher2.cpp

bool g_useSearcher3 = false;
bool g_s3Belief = true;
// Real-boundary posterior filtering is experimental and opt-in.
bool g_s3RealBeliefFilter = false;
// Rebuild a fresh visible-state-consistent prior only on filter collapse.
bool g_s3RealBeliefCollapseFresh = false;
// Replace a fresh searcher's initial belief with the filtered real-boundary
// posterior; tree state remains fresh.
bool g_s3PersistFilteredBelief = false;
// STS_S3_INTERNAL_BELIEF_UPDATE: when 0, simulated observations inside step()
// do NOT permanently mutate the root belief. The root belief represents
// uncertainty at the real information state; imagined trajectories are
// hypothetical and must not condition it across simulations.
// Default 0 (issue #58): the default-on internal update was historical
// (broken) behavior — the root belief was destroyed within ~60 simulations
// and all subsequent sampling was uniform. No resampling/rebirth exists yet,
// so the update must not be the default.
bool g_s3InternalBeliefUpdate = false;
bool g_s3Prune = true;
bool g_s3Chain = true;
bool g_s3Live = true;
bool g_s3Crn = false;

// ── Tree reuse control ─────────────────────────────────────────────────────
// Default: obs-stable N=1 reuse (fair S3 candidate, §2026-08-09).
// STS_REUSE_MAX_SEARCHES=0 restores fresh-tree behaviour.
int g_reuseMaxSearches = 1;     // STS_REUSE_MAX_SEARCHES (0 = fresh every decision)
int g_reuseStatsMode = 0;       // STS_REUSE_STATS_MODE: 0=keep, 1=recursive_reset
bool g_reuseAlwaysQ = false;    // STS_REUSE_ALWAYS_Q: always use Q on carried trees
bool g_s3AlwaysQ = false;       // STS_S3_ALWAYS_Q: use Q from the first fresh-tree simulation
bool g_reuseDiag = false;       // STS_REUSE_DIAG: print reuse diagnostics
bool g_reuseObsStable = true;   // STS_REUSE_OBS_STABLE: only promote obs-stable children
bool g_reuseReconcileRoot = false; // STS_REUSE_RECONCILE_ROOT: add missing root edges
bool g_reuseCarryDiag = false;  // STS_REUSE_CARRY_DIAG: detailed per-carry diagnostic
bool g_s3UnionExpand = false;   // STS_S3_UNION_EXPAND: add missing edges at internal nodes
bool g_reuseCpuDiag = false;       // STS_REUSE_CPU_DIAG: per-search CPU CSV
std::string g_reuseCpuDiagFile;    // STS_REUSE_CPU_DIAG_FILE: output path
bool g_s3PoolRedirect = false; // STS_S3_POOL_REDIRECT: forced-move budget pool redirect (opt-in)
// A2 dynamic alpha by rollout length (STS_VNET_ALPHA_LEN, opt-in):
// replaces the flat g_vnetAlpha at the leaf blend site with a lookup
// over the rollout's action count. Pre-registered table (§3 plan):
// {≤2:0.1, 3-5:0.2, 6-10:0.4, >10:0.6} — short rollout = trustworthy
// terminal → low alpha; long rollout = noisy → high alpha (trust leaf).
bool g_vnetAlphaLen = false;
std::vector<std::pair<int,double>> g_vnetAlphaLenTable = {{2,0.1},{5,0.2},{10,0.4},{999,0.6}};
int g_s3Particles = 64;
static std::atomic<int> g_s3CollapseSensitivityEvents{0};
double g_riskLambda = 0.5;
bool g_s3Expand = false;
int g_s3ExpandMaxNew = 32;
bool g_s3ExpandSimple = false; // like g_s3Expand but picks deterministically with uniform prior
bool g_s3SemanticCardEdges = false;
bool g_s3RngExposureDiag = false;
std::string g_s3RngExposureDiagFile;

namespace {
std::mutex &rngExposureMutex() {
    static std::mutex m;
    return m;
}

void writeRngExposureRows(const std::vector<std::string> &rows) {
    if (g_s3RngExposureDiagFile.empty()) return;
    std::lock_guard<std::mutex> lock(rngExposureMutex());
    std::ifstream probe(g_s3RngExposureDiagFile);
    const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    std::ofstream out(g_s3RngExposureDiagFile, std::ios::app);
    if (!out) return;
    if (empty) {
        out << "seed,encounter,floor,source_filter_decision_idx,search_decision_idx,turn,"
               "root_observation_hash,compatible,action_bits,"
               "simulations,ai_exposed,ai_fraction,ai_advances,ai_first_0,ai_first_1,"
               "ai_first_2,ai_first_3,ai_first_4plus,ai_never,card_exposed,card_fraction,"
               "card_advances,card_first_0,card_first_1,card_first_2,card_first_3,"
               "card_first_4plus,card_never\n";
    }
    for (const auto &row : rows) out << row << '\n';
}
}

// ── Outcome-bucket diagnostic (STS_S3_OUTCOME_BUCKET_DIAG) ────────────
// Measures how many distinct visible outcomes different hidden particles
// produce from the same pre-state + action (primarily END_TURN → next hand).
// Off by default; zero cost when disabled. CSV rows written per measured
// stochastic transition.
bool g_s3OutcomeBucketDiag = false;
std::string g_s3OutcomeBucketDiagFile;
int g_s3OutcomeBucketDiagParticles = 64; // particles to sample per transition

// ── Bucket-value diagnostic (STS_S3_BUCKET_VALUE_DIAG) ───────────────
// Measures within-bucket value homogeneity: when multiple particles produce
// the same visible observation after END_TURN, do they have similar
// downstream continuation values? Critical for outcome aggregation.
bool g_s3BucketValueDiag = false;
std::string g_s3BucketValueDiagFile;
int g_s3BucketValueDiagRollouts = 4;     // K rollouts per bucket member
int g_s3BucketValueDiagMaxTransitions = 1000; // cap on measured transitions
int g_s3BucketValueDiagSampleMembers = 8;     // max members sampled per bucket

// ── Strategy-fusion shadow diagnostic ──────────────────────────
bool g_s3StrategyFusionDiag = false;
std::string g_s3StrategyFusionDiagFile = "build/s3_strategy_fusion_diag.csv";
int g_s3StrategyFusionDiagParticles = 64;
int g_s3StrategyFusionDiagMaxTransitions = 100;
int g_s3StrategyFusionDiagMinChildVisits = 32;
int g_s3StrategyFusionDiagFreshSims = 500;
int g_s3StrategyFusionDiagReferenceSims = 3000;

// ── END_TURN marginalization (STS_S3_ENDTURN_MARGINALIZE) ──────────────
// Prototype: at eligible leaf-expansion END_TURN boundaries, generate
// N particles, bucket by visible outcome, evaluate one rep per bucket,
// and backpropagate the weighted expectation. Off by default.
bool g_s3EndTurnMarginalize = false;
int g_s3EndTurnMarginalizeParticles = 16;
int g_s3EndTurnMarginalizeMaxPile = 8;
bool g_s3PersistentEndTurnChance = false;
int g_s3PersistentEndTurnMaxPile = 8;

static std::atomic<std::int64_t> g_pcEligible{0};
static std::atomic<std::int64_t> g_pcIneligible{0};
static std::atomic<std::int64_t> g_pcContainersCreated{0};
static std::atomic<std::int64_t> g_pcContainerVisits{0};
static std::atomic<std::int64_t> g_pcOutcomeChildrenCreated{0};
static std::atomic<std::int64_t> g_pcOutcomeExistingHits{0};
static std::atomic<std::int64_t> g_pcOutcomeNewMisses{0};
static std::atomic<std::int64_t> g_pcMaxOutcomesPerContainer{0};
static std::atomic<std::int64_t> g_pcContainersWithPreObservationMismatch{0};
static std::atomic<std::int64_t> g_pcMaxOutcomesAfterPreObservationMismatch{0};
static std::atomic<std::int64_t> g_pcMaxContainerPreObservationVisits{0};
static std::atomic<std::int64_t> g_pcMaxContainerPreObservationMismatches{0};
static std::mutex g_pcMaxContainerMutex;
static std::array<std::atomic<std::int64_t>, 9> g_pcOutcomeCountHistogram{};

// ── Draw-probability diagnostic (STS_S3_DRAW_PROB_DIAG) ───────────────
// Computes exact hypergeometric draw probabilities for tactical features
// (lethal outs, attack/block draws) at END_TURN pre-draw states.
bool g_s3DrawProbDiag = false;
std::string g_s3DrawProbDiagFile;

// ── Leaf-value residual diagnostic (STS_S3_LEAFVALUE_DIAG) ────────────
// Captures unique pre-END_TURN states and runs 1k + 4k fresh searches
// on each to measure whether pLethal explains Q_4k - Q_1k residuals.
bool g_s3LeafValueDiag = false;
std::string g_s3LeafValueDiagFile;
int g_s3LeafValueDiagNormalSims = 1000;
int g_s3LeafValueDiagDeepSims = 4000;
int g_s3LeafValueDiagMaxStates = 120;

// ── Belief audit diagnostic (STS_S3_BELIEF_AUDIT) ─────────────────────
bool g_s3BeliefAudit = false;
std::string g_s3BeliefAuditFile;
bool g_s3RootRaceDiag = false;
std::string g_s3RootRaceDiagFile;
int g_s3RootRaceDiagMaxStates = 32;
bool g_s3GateTimingDiag = false;
std::string g_s3GateTimingDiagFile;
thread_local std::int64_t t_baUpdatesDuringSearch = 0;
thread_local std::int64_t t_baParticlesZeroed = 0;
thread_local std::int64_t t_baAllZeroEvents = 0;
thread_local std::int64_t t_baUniformEqualCalls = 0;
thread_local std::int64_t t_baUniformAllZeroCalls = 0;
thread_local std::int64_t t_baApplyExactOrder = 0;
thread_local std::int64_t t_baApplyFallbackShuffle = 0;

// Cross-thread dedup: protocol is write-then-check under mutex.
static std::mutex g_drawProbMutex;
static std::unordered_set<std::uint64_t> g_drawProbSeen;
static bool g_drawProbHeaderWritten = false;
static int g_drawProbRowCount = 0;
static constexpr int kMaxDrawProbRows = 5000;

// ── Exact hypergeometric: P(draw >= 1 from K outs | N total, D drawn) ─
double hypergeometricAtLeastOne(int N, int K, int D) {
    if (K <= 0 || N <= 0 || D <= 0) return 0.0;
    if (D >= N) return (K > 0) ? 1.0 : 0.0;
    if (K > N - D) return 1.0;  // more outs than cards left undrawn
    // 1 - C(N-K, D) / C(N, D) = 1 - product_{i=0}^{D-1} (N-K-i)/(N-i)
    double pMiss = 1.0;
    for (int i = 0; i < D; ++i) {
        pMiss *= (double)(N - K - i) / (double)(N - i);
    }
    return 1.0 - pMiss;
}

// ── Expected count: E[cards drawn from category] = D * K / N ──────────
double expectedCount(int N, int K, int D) {
    if (N <= 0 || D <= 0) return 0.0;
    return (double)(D * K) / (double)N;
}

// Marginalization diagnostic counters (per-searcher lifetime).
thread_local std::int64_t t_margEligible = 0;
thread_local std::int64_t t_margApplied = 0;
thread_local std::int64_t t_margParticlesSampled = 0;
thread_local std::int64_t t_margUniqueBuckets = 0;
thread_local std::int64_t t_margContEvals = 0;
thread_local std::int64_t t_margTermBuckets = 0;
thread_local double t_margSeconds = 0.0;

// Shadow-comparison counters (1% sample).
thread_local std::int64_t t_margShadowCount = 0;
thread_local double t_margShadowOrdinary = 0.0;
thread_local double t_margShadowMarginal = 0.0;

// Thread-local diagnostic state: per-thread RNG, per-thread output file,
// and per-thread dedup set (visibleHash of pre-state). Each unique
// (preState, END_TURN) pair is measured at most once per thread.
static thread_local std::mt19937_64 t_diagRng;
static thread_local bool t_diagRngSeeded = false;
static thread_local std::ofstream t_diagOut;
static thread_local bool t_diagOutOpen = false;
static thread_local std::unordered_set<std::uint64_t> t_diagSeen;
static thread_local int t_diagRowCount = 0;
static constexpr int kMaxDiagRows = 2000;  // hard cap per thread

// Bucket-value diag thread-local state.
static thread_local std::unordered_set<std::uint64_t> t_bvdSeen;
static thread_local int t_bvdRowCount = 0;
static thread_local std::mt19937_64 t_bvdRng;
static thread_local bool t_bvdRngSeeded = false;
static thread_local std::ofstream t_bvdOut;
static thread_local bool t_bvdOutOpen = false;

bool g_s3RolloutPolicy = false;
int g_s3RolloutK = 1;
int g_s3RolloutTurnStop = 0;
// B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT, opt-in; see header).
// Defaults: beam width 8; scorer weights w1=ΔHP_enemy, w2=ΔHP_player,
// w3=kills, w4=persistent setup, w5=potion penalty.
bool g_s3TurnRollout = false;
int g_s3TurnBeamWidth = 8;
double g_s3TurnScoreW1 = 1.0;
double g_s3TurnScoreW2 = 1.0;
double g_s3TurnScoreW3 = 50.0;
double g_s3TurnScoreW4 = 10.0;
double g_s3TurnScoreW5 = 30.0;
bool g_vnetCondBossOnly = false;
bool g_vnetCondAct3 = false;
thread_local std::function<double(const BattleContext &)> g_terminalBonus;
thread_local std::function<void(const S3LeafDiagnostic &)> g_onS3LeafQuery;
thread_local bool g_s3LeafTraceActions = false;    // particle_posterior_probe-only: record per-action semantic checkpoints

// Phase 6 PVNet deployment-speed knobs (see header; STS_PVNET_* parse in
// apps/one_combat.cpp). The leaf cache is behavior-preserving (deterministic
// given the visible state) and on by default; the COND_* gates are off by
// default, preserving the pre-phase-6 per-expansion blend behavior.
bool g_pvnetCache = true;
int g_pvnetCondMinTurn = 0;
int g_pvnetCondMinDepth = 0;
bool g_pvnetCondBossOnly = false;
extern double g_vnetAlpha;

// ---- Particle application: 6 RNG streams + draw pile order -----------------
static bool sameCardMultiset(const std::vector<CardInstance> &a,
                             const std::vector<CardInstance> &b) {
    if (a.size() != b.size()) return false;
    // Exact multiset equality over card ids, allocation-free: fixed-size
    // counts over the dense CardId range. Same identity domain as the previous
    // sort-and-compare (id only — upgrade state is outside this comparison,
    // exactly as before; duplicates count per occurrence).
    std::array<int, sizeof(cardEnumStrings) / sizeof(cardEnumStrings[0])> counts{};
    for (const auto &c : a) ++counts[static_cast<std::size_t>(c.getId())];
    for (const auto &c : b)
        if (--counts[static_cast<std::size_t>(c.getId())] < 0) return false;
    return true;
}

// Diagnostic-only identity check. Gameplay particle application intentionally
// retains the historical CardId-only predicate; posterior-valid diagnostics
// must also distinguish upgrades, temporary cost, specialData, and
// freeToPlayOnce.
static bool sameDiagnosticCardMultiset(const std::vector<CardInstance> &a,
                                       const std::vector<CardInstance> &b) {
    if (a.size() != b.size()) return false;
    std::vector<FullHiddenCardId> as, bs;
    as.reserve(a.size()); bs.reserve(b.size());
    for (const auto &c : a) as.emplace_back(c);
    for (const auto &c : b) bs.emplace_back(c);
    std::sort(as.begin(), as.end());
    std::sort(bs.begin(), bs.end());
    return as == bs;
}

// Shared implementation: install particle RNG seeds + draw order.
// The fallbackRng is used only when the particle's draw-pile order doesn't
// match the current state (stale particle after tree reuse).
static void applyParticleImpl(BattleContext &state,
                              const HiddenBattleState &particle,
                              std::mt19937_64 &fallbackRng) {
    state.shuffleRng.seed0    = particle.shuffleRngSeed0;
    state.shuffleRng.seed1    = particle.shuffleRngSeed1;
    state.shuffleRng.counter  = particle.shuffleRngCounter;
    state.cardRandomRng.seed0 = particle.cardRandomRngSeed0;
    state.cardRandomRng.seed1 = particle.cardRandomRngSeed1;
    state.cardRandomRng.counter = particle.cardRandomRngCounter;
    state.aiRng.seed0    = particle.aiRngSeed0;
    state.aiRng.seed1    = particle.aiRngSeed1;
    state.aiRng.counter  = particle.aiRngCounter;
    state.miscRng.seed0  = particle.miscRngSeed0;
    state.miscRng.seed1  = particle.miscRngSeed1;
    state.miscRng.counter = particle.miscRngCounter;
    state.monsterHpRng.seed0 = particle.monsterHpRngSeed0;
    state.monsterHpRng.seed1 = particle.monsterHpRngSeed1;
    state.monsterHpRng.counter = particle.monsterHpRngCounter;
    state.potionRng.seed0   = particle.potionRngSeed0;
    state.potionRng.seed1   = particle.potionRngSeed1;
    state.potionRng.counter = particle.potionRngCounter;
    // Install the sampled draw order when it still matches the copied pile;
    // stale particles (tree reuse across decisions) fall back to a shuffle.
    if (particle.drawPileOrder.size() == (size_t)state.cards.drawPile.size()
        && sameCardMultiset(particle.drawPileOrder, state.cards.drawPile)) {
        std::copy(particle.drawPileOrder.begin(), particle.drawPileOrder.end(),
                  state.cards.drawPile.begin());
    } else {
        std::shuffle(state.cards.drawPile.begin(), state.cards.drawPile.end(),
                     fallbackRng);
    }
}

void BattleScumSearcher3::applyParticle(BattleContext &state,
                                        const HiddenBattleState &particle) {
    const bool exact = particle.drawPileOrder.size() == state.cards.drawPile.size()
        && sameCardMultiset(particle.drawPileOrder, state.cards.drawPile);
    applyParticleImpl(state, particle, rng);
    diagnosticParticleAppliedExactly = exact;
    diagnosticParticleUsedFallback = !exact;
}

void applyHiddenState(BattleContext &state, const HiddenBattleState &particle,
                      std::mt19937_64 &fallbackRng) {
    applyParticleImpl(state, particle, fallbackRng);
}

bool applyHiddenStateExact(BattleContext &state,
                           const HiddenBattleState &particle) {
    if (particle.drawPileOrder.size() != state.cards.drawPile.size()
        || !sameDiagnosticCardMultiset(particle.drawPileOrder, state.cards.drawPile))
        return false;
    state.shuffleRng.seed0 = particle.shuffleRngSeed0;
    state.shuffleRng.seed1 = particle.shuffleRngSeed1;
    state.shuffleRng.counter = particle.shuffleRngCounter;
    state.cardRandomRng.seed0 = particle.cardRandomRngSeed0;
    state.cardRandomRng.seed1 = particle.cardRandomRngSeed1;
    state.cardRandomRng.counter = particle.cardRandomRngCounter;
    state.aiRng.seed0 = particle.aiRngSeed0;
    state.aiRng.seed1 = particle.aiRngSeed1;
    state.aiRng.counter = particle.aiRngCounter;
    state.miscRng.seed0 = particle.miscRngSeed0;
    state.miscRng.seed1 = particle.miscRngSeed1;
    state.miscRng.counter = particle.miscRngCounter;
    state.monsterHpRng.seed0 = particle.monsterHpRngSeed0;
    state.monsterHpRng.seed1 = particle.monsterHpRngSeed1;
    state.monsterHpRng.counter = particle.monsterHpRngCounter;
    state.potionRng.seed0 = particle.potionRngSeed0;
    state.potionRng.seed1 = particle.potionRngSeed1;
    state.potionRng.counter = particle.potionRngCounter;
    state.cards.drawPile = particle.drawPileOrder;
    return true;
}

bool isDrawPileIndexSensitiveCardSelect(const BattleContext &bc) {
    if (bc.inputState != InputState::CARD_SELECT) return false;
    switch (bc.cardSelectInfo.cardSelectTask) {
        case CardSelectTask::SECRET_TECHNIQUE:
        case CardSelectTask::SECRET_WEAPON:
        case CardSelectTask::SEEK:
            return true;
        default:
            return false;
    }
}

RealBeliefFilterStats BattleScumSearcher3::filterRealTransition(
    const BattleContext &preState, const Action &action,
    const BattleContext &realPostState) {
    const auto filterStart = std::chrono::steady_clock::now();
    RealBeliefFilterStats stats;
    stats.previousParticles = static_cast<int>(belief.particles.size());
    stats.actionBits = action.bits;
    stats.actionType = static_cast<int>(action.getActionType());
    stats.comparisonExact = true;
    stats.reshuffleObserved = preState.cards.drawPile.empty()
        && !preState.cards.discardPile.empty()
        && !realPostState.cards.drawPile.empty();
    const auto realObs = CombatObservation::fromBattleContext(realPostState);
    stats.realObservationHash = realObs.visibleHash();
    const auto oldParticles = belief.particles;
    std::unordered_map<std::uint64_t, int> predictedCounts;
    std::mt19937_64 fallbackRng(agentSeed ^
        (static_cast<std::uint64_t>(decisionIndex) * 0x9e3779b97f4a7c15ULL));

    for (size_t i = 0; i < belief.particles.size(); ++i) {
        auto &particle = belief.particles[i];
        if (particle.weight <= 0.0) continue;
        ++stats.attempted;
        if (particle.drawPileOrder.size() != preState.cards.drawPile.size()
            || !sameCardMultiset(particle.drawPileOrder, preState.cards.drawPile)) {
            ++stats.propagationFailures;
            ++stats.drawPileMismatch;
            ++stats.fallbackShuffles;
            particle.weight = 0.0;
            continue;
        }

        BattleContext predicted = preState;
        applyParticleImpl(predicted, particle, fallbackRng);
        if (!action.isValidAction(predicted)) {
            ++stats.actionIllegal;
            ++stats.propagationFailures;
            particle.weight = 0.0;
            continue;
        }
        action.execute(predicted);
        const auto predictedObs = CombatObservation::fromBattleContext(predicted);
        ++predictedCounts[predictedObs.visibleHash()];
        const bool compatible = predictedObs == realObs
            && predicted.outcome == realPostState.outcome;
        if (!compatible) {
            ++stats.incompatible;
            particle.weight = 0.0;
            continue;
        }

        ++stats.compatible;
        particle.weight = 1.0;
        particle.drawPileOrder = predicted.cards.drawPile;
        particle.shuffleRngSeed0 = predicted.shuffleRng.seed0;
        particle.shuffleRngSeed1 = predicted.shuffleRng.seed1;
        particle.shuffleRngCounter = predicted.shuffleRng.counter;
        particle.cardRandomRngSeed0 = predicted.cardRandomRng.seed0;
        particle.cardRandomRngSeed1 = predicted.cardRandomRng.seed1;
        particle.cardRandomRngCounter = predicted.cardRandomRng.counter;
        particle.aiRngSeed0 = predicted.aiRng.seed0;
        particle.aiRngSeed1 = predicted.aiRng.seed1;
        particle.aiRngCounter = predicted.aiRng.counter;
        particle.miscRngSeed0 = predicted.miscRng.seed0;
        particle.miscRngSeed1 = predicted.miscRng.seed1;
        particle.miscRngCounter = predicted.miscRng.counter;
        particle.monsterHpRngSeed0 = predicted.monsterHpRng.seed0;
        particle.monsterHpRngSeed1 = predicted.monsterHpRng.seed1;
        particle.monsterHpRngCounter = predicted.monsterHpRng.counter;
        particle.potionRngSeed0 = predicted.potionRng.seed0;
        particle.potionRngSeed1 = predicted.potionRng.seed1;
        particle.potionRngCounter = predicted.potionRng.counter;
    }

    int dominantCount = 0;
    for (const auto &kv : predictedCounts) {
        if (kv.second > dominantCount) {
            dominantCount = kv.second;
            stats.dominantPredictedObservationHash = kv.first;
        }
    }
    stats.distinctPredictedObservations = static_cast<int>(predictedCounts.size());
    stats.dominantPredictedObservationCount = dominantCount;
    if (stats.attempted > 0) {
        for (const auto &kv : predictedCounts) {
            const double p = static_cast<double>(kv.second) / stats.attempted;
            if (p > 0.0) stats.predictedObservationEntropy -= p * std::log(p);
        }
    }

    if (stats.compatible == 0 && g_s3BeliefAudit) {
        const int ticket = g_s3CollapseSensitivityEvents.fetch_add(1);
        if (ticket < 64) {
            const auto sensitivityStart = std::chrono::steady_clock::now();
            stats.sensitivityProbed = true;
            auto probeCount = [&](int count) {
                std::mt19937_64 probeRng(agentSeed ^
                    (static_cast<std::uint64_t>(decisionIndex + count) * 0xd1b54a32d192ed03ULL));
                Belief probe = Belief::initial(preState, count, probeRng);
                int survivors = 0;
                for (auto &probeParticle : probe.particles) {
                    BattleContext probeState = preState;
                    applyParticleImpl(probeState, probeParticle, probeRng);
                    if (!action.isValidAction(probeState)) continue;
                    action.execute(probeState);
                    const auto probeObs = CombatObservation::fromBattleContext(probeState);
                    if (probeObs == realObs && probeState.outcome == realPostState.outcome)
                        ++survivors;
                }
                return survivors;
            };
            stats.sensitivity64 = probeCount(64);
            stats.sensitivity128 = probeCount(128);
            stats.sensitivity256 = probeCount(256);
            stats.sensitivity512 = probeCount(512);
            stats.sensitivityCpuMs = std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - sensitivityStart).count();
        }
    }
    if (stats.compatible == 0) {
        stats.posteriorCollapse = true;
        if (stats.propagationFailures == stats.attempted) {
            stats.collapseCategory = "PROPAGATION_FAILURE";
        } else if (stats.actionIllegal > 0 && stats.propagationFailures == stats.actionIllegal) {
            stats.collapseCategory = "ACTION_ILLEGAL_UNDER_PARTICLES";
        } else if (stats.reshuffleObserved) {
            stats.collapseCategory = "RESHUFFLE_OR_DRAW_TRANSITION";
        } else if (action.getActionType() == ActionType::END_TURN) {
            stats.collapseCategory = "STOCHASTIC_END_TURN_OR_PARTICLE_DEPRIVATION";
        } else if (action.getActionType() == ActionType::CARD) {
            stats.collapseCategory = "CARD_EFFECT_OR_AUTOMATIC_QUEUE_OR_PARTICLE_DEPRIVATION";
        } else {
            stats.collapseCategory = "PARTICLE_DEPRIVATION_OR_HIDDEN_STATE_MISMATCH";
        }
        if (g_s3RealBeliefCollapseFresh) {
            belief = Belief::initial(realPostState, stats.previousParticles, fallbackRng);
            stats.freshBeliefRebuilt = true;
        } else {
            // Preserve gameplay execution without pretending that the posterior
            // is valid. Restore the prior particle set and use an explicit
            // uniform fallback; the collapse remains in diagnostics.
            belief.particles = oldParticles;
            const double w = belief.particles.empty()
                ? 0.0 : 1.0 / static_cast<double>(belief.particles.size());
            for (auto &p : belief.particles) p.weight = w;
        }
    } else {
        const double w = 1.0 / static_cast<double>(stats.compatible);
        for (auto &p : belief.particles)
            if (p.weight > 0.0) p.weight = w;
    }
    stats.configuredParticleCount = static_cast<int>(particleSampleCounts.size());
    stats.simulations = lastSearchSimulations;
    stats.searchCpuMs = lastSearchCpuMs;
    stats.beliefInitializationCpuMs = beliefInitializationCpuMs;
    int sampled = 0;
    std::vector<int> used;
    used.reserve(particleSampleCounts.size());
    for (const int count : particleSampleCounts) {
        if (count > 0) { ++sampled; used.push_back(count); }
    }
    stats.distinctParticlesSampled = sampled;
    stats.neverSampledParticles = stats.configuredParticleCount - sampled;
    stats.sampledParticleFraction = stats.configuredParticleCount > 0
        ? static_cast<double>(sampled) / stats.configuredParticleCount : 0.0;
    if (!used.empty()) {
        std::sort(used.begin(), used.end());
        stats.minSamplesPerParticle = used.front();
        stats.maxSamplesPerParticle = used.back();
        double totalUsed = 0.0;
        for (const int count : used) totalUsed += count;
        stats.meanSamplesPerSampledParticle = totalUsed / used.size();
        stats.medianSamplesPerSampledParticle = (used.size() % 2 == 0)
            ? 0.5 * (used[used.size() / 2 - 1] + used[used.size() / 2])
            : used[used.size() / 2];
        if (stats.simulations > 0) {
            double entropy = 0.0;
            for (const int count : used) {
                const double q = static_cast<double>(count) / stats.simulations;
                if (q > 0.0) entropy -= q * std::log(q);
            }
            stats.particleUsageEntropy = entropy;
        }
    }
    stats.incompatible = stats.attempted - stats.compatible;
    stats.cpuMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - filterStart).count();
    return stats;
}
// ---- Observation caching: compute once per node, reuse on subsequent visits
void BattleScumSearcher3::ensureObservation(Node &node, const BattleContext &state) {
    if (!node.obsCached) {
        node.obs = CombatObservation::fromBattleContext(state);
        node.obsHash = node.obs.visibleHash();
        node.obsCached = true;
    } else {
        // When the observation is already cached from a previous
        // determinization, the current state's visibleHash may differ from
        // the node's stored obsHash — track these mismatches for reuse
        // diagnostics.
        if (g_reuseDiag) {
            std::uint64_t curHash = CombatObservation::fromBattleContext(state).visibleHash();
            if (curHash != node.obsHash)
                ++obsMismatchCount;
        }
    }
}

// ---- Constructor -----------------------------------------------------------
BattleScumSearcher3::BattleScumSearcher3(const BattleContext &bc, int particleCount)
    : BattleScumSearcher3(bc, 0, 0, particleCount) {}

BattleScumSearcher3::BattleScumSearcher3(const BattleContext &bc,
                                         std::uint64_t agentSeed,
                                         int decisionIndex,
                                         int particleCount)
    : rootBc(std::make_unique<const BattleContext>(bc))
    , maxParticles(particleCount)
    , agentSeed(agentSeed)
    , decisionIndex(decisionIndex)
    , riskLambda(g_riskLambda)
    , crnParticleCount(std::min(particleCount, 128))
{
    rankCorrValues.clear();   // per-search accumulator; empty until the correction model is loaded
    rootObs = CombatObservation::fromBattleContext(bc);
    root.obs = rootObs;
    root.obsHash = rootObs.visibleHash();
    root.obsCached = true;

    reseed();

    const auto beliefStart = std::chrono::steady_clock::now();
    belief = Belief::initial(bc, maxParticles, rng);
    beliefInitializationCpuMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - beliefStart).count();
    particleSampleCounts.assign(belief.particles.size(), 0);
    prepareCRNParticles();
}

void BattleScumSearcher3::resetParticleUsage() {
    particleSampleCounts.assign(belief.particles.size(), 0);
    lastSearchSimulations = 0;
    lastSearchCpuMs = 0.0;
    strategyFusionCandidates.clear();
    strategyFusionFinalVisitRecords.clear();
}

void BattleScumSearcher3::enableRngExposureDiagnostic(
    std::uint64_t seed, int encounter, int floor, int sourceFilterDecisionIdx,
    int searchDecisionIdx, int turn, std::uint64_t rootObservationHash, int compatible) {
    rngExposureEnabled = g_s3RngExposureDiag && !g_s3RngExposureDiagFile.empty();
    if (!rngExposureEnabled) return;
    rngExposureSeed = seed;
    rngExposureEncounter = encounter;
    rngExposureFloor = floor;
    rngExposureSourceFilterDecisionIndex = sourceFilterDecisionIdx;
    rngExposureSearchDecisionIndex = searchDecisionIdx;
    rngExposureTurn = turn;
    rngExposureRootObservationHash = rootObservationHash;
    rngExposureCompatible = compatible;
    rngExposureAll = {};
    rngExposureByAction.clear();
    rngExposureActionIndex = 0;
}

void BattleScumSearcher3::observeRngExposureAction(const Action &action, BattleContext &state) {
    BattleContext preState;
    const bool trace = diagnosticTraceActive;
    if (trace) preState = state;
    if (!rngExposureEnabled) {
        action.execute(state);
        if (trace) recordDiagnosticAction(action, preState, state);
        return;
    }
    const int index = rngExposureActionIndex;
    if (index == 0) rngExposureCurrentRootActionBits = action.bits;
    action.execute(state);
    if (trace) recordDiagnosticAction(action, preState, state);
    ++rngExposureActionIndex;
    const int aiDelta = state.aiRng.counter - rngExposureAiBaseline;
    const int cardDelta = state.cardRandomRng.counter - rngExposureCardBaseline;
    auto observe = [&](int delta, bool &seen, int &first) {
        if (delta > 0 && !seen) { seen = true; first = index; }
    };
    observe(aiDelta, rngExposureAiSeen, rngExposureAiFirst);
    observe(cardDelta, rngExposureCardSeen, rngExposureCardFirst);
    rngExposureAiTotalDelta = aiDelta;
    rngExposureCardTotalDelta = cardDelta;
}

void BattleScumSearcher3::recordDiagnosticAction(const Action &action,
                                                 const BattleContext &preState,
                                                 const BattleContext &postState) {
    if (!diagnosticTraceActive) return;
    S3LeafActionCheckpoint checkpoint;
    checkpoint.action = action;
    if (action.getActionType() == ActionType::CARD) {
        const int hi = action.getSourceIdx();
        if (hi >= 0 && hi < preState.cards.cardsInHand) {
            const auto &card = preState.cards.hand[hi];
            checkpoint.sourceUniqueId = card.uniqueId;
            checkpoint.sourceCost = card.cost;
            checkpoint.sourceRetain = card.retain;
            checkpoint.cardId = card.getId();
            checkpoint.upgradeCount = card.getUpgradeCount();
            checkpoint.costForTurn = card.costForTurn;
            checkpoint.freeToPlayOnce = card.freeToPlayOnce;
            checkpoint.specialData = card.specialData;
            checkpoint.target = action.getTargetIdx();
            checkpoint.hasCardKey = true;
        }
    }
    checkpoint.observation = CombatObservation::fromBattleContext(postState);
    checkpoint.outcome = postState.outcome;
    std::uint64_t fingerprint = checkpoint.observation.visibleHash();
    fingerprint ^= static_cast<std::uint64_t>(postState.shuffleRng.counter) * 0x9e3779b97f4a7c15ULL;
    fingerprint ^= static_cast<std::uint64_t>(postState.cardRandomRng.counter) * 0xbf58476d1ce4e5b9ULL;
    fingerprint ^= static_cast<std::uint64_t>(postState.aiRng.counter) * 0x94d049bb133111ebULL;
    fingerprint ^= static_cast<std::uint64_t>(postState.miscRng.counter) * 0x369dea0f31a53f85ULL;
    checkpoint.hiddenFingerprint = fingerprint;
    diagnosticActionCheckpoints.push_back(std::move(checkpoint));
}

void BattleScumSearcher3::finishRngExposureSimulation() {
    if (!rngExposureEnabled) return;
    auto add = [&](RngExposureAggregate &a) {
        ++a.simulations;
        if (rngExposureAiSeen) {
            ++a.aiExposed;
            a.aiFirst[rngExposureAiFirst < 4 ? rngExposureAiFirst : 4]++;
        } else ++a.aiFirst[5];
        a.aiAdvances += rngExposureAiTotalDelta;
        if (rngExposureCardSeen) {
            ++a.cardExposed;
            a.cardFirst[rngExposureCardFirst < 4 ? rngExposureCardFirst : 4]++;
        } else ++a.cardFirst[5];
        a.cardAdvances += rngExposureCardTotalDelta;
    };
    add(rngExposureAll);
    add(rngExposureByAction[rngExposureCurrentRootActionBits]);
    rngExposureAiSeen = rngExposureCardSeen = false;
    rngExposureAiFirst = rngExposureCardFirst = -1;
    rngExposureAiTotalDelta = rngExposureCardTotalDelta = 0;
    rngExposureActionIndex = 0;
}

void BattleScumSearcher3::flushRngExposureDiagnostic() {
    if (!rngExposureEnabled) return;
    std::vector<std::string> rows;
    auto emit = [&](std::uint32_t bits, const RngExposureAggregate &a) {
        auto frac = [](std::int64_t n, std::int64_t d) {
            return d ? std::to_string(static_cast<double>(n) / d) : "0";
        };
        std::ostringstream o;
        o << rngExposureSeed << ',' << rngExposureEncounter << ',' << rngExposureFloor << ','
          << rngExposureSourceFilterDecisionIndex << ',' << rngExposureSearchDecisionIndex << ','
          << rngExposureTurn << ',' << rngExposureRootObservationHash << ',' << rngExposureCompatible << ','
          << bits << ',' << a.simulations << ',' << a.aiExposed << ',' << frac(a.aiExposed, a.simulations)
          << ',' << a.aiAdvances;
        for (auto n : a.aiFirst) o << ',' << n;
        o << ',' << a.cardExposed << ',' << frac(a.cardExposed, a.simulations) << ',' << a.cardAdvances;
        for (auto n : a.cardFirst) o << ',' << n;
        rows.push_back(o.str());
    };
    emit(0xFFFFFFFFu, rngExposureAll);
    for (const auto &p : rngExposureByAction) emit(p.first, p.second);
    writeRngExposureRows(rows);
    rngExposureEnabled = false;
}
void BattleScumSearcher3::reseed() {
    // Seed RNG from composite: agentSeed ^ visibleHash ^ decisionIdx.
    // Same agent seed + same observation + same decision index = same search.
    // Different agent seeds / decision indices = different particle samples.
    uint64_t h = root.obsHash;
    h ^= agentSeed + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    h ^= (uint64_t)decisionIndex + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    rng.seed(h ? h : 1);
}

// ---- Recursive stats reset (STS_REUSE_STATS_MODE=recursive_reset) ---------
void BattleScumSearcher3::recursiveResetStats(Node &node) {
    node.simulationCount = 0;
    node.evaluationSum = 0;
    node.dist.n = 0;
    node.dist.loQ20 = 0;
    node.dist.loQ05 = 0;
    for (auto &edge : node.edges) {
        recursiveResetStats(edge.child);
        for (auto &outcome : edge.outcomeChildren)
            recursiveResetStats(outcome.child);
    }
}

// ---- Semantic card-edge resolution -----------------------------------------
std::optional<int> resolveCardKeyInHand(
    const BattleScumSearcher3::CardActionKey &key, const BattleContext &state) {
    for (int hi = 0; hi < state.cards.cardsInHand; ++hi) {
        const auto &c = state.cards.hand[hi];
        if (c.getId() == key.id
            && c.getUpgradeCount() == key.upgradeCount
            && c.costForTurn == key.costForTurn
            && c.freeToPlayOnce == key.freeToPlayOnce
            && c.specialData == key.specialData) {
            return hi;
        }
    }
    return std::nullopt;
}

std::optional<Action> resolveSemanticCardEdge(
    const BattleScumSearcher3::Edge &edge, const BattleContext &state) {
    if (!edge.hasCardKey) return edge.action;
    const auto hi = resolveCardKeyInHand(edge.cardKey, state);
    if (!hi) return std::nullopt;
    if (edge.cardKey.target >= 0)
        return Action(ActionType::CARD, *hi, edge.cardKey.target);
    return Action(ActionType::CARD, *hi);
}

// ---- Hand-only multiset key (same identity fields as CombatObservation) -----
// Used to measure hand compression independent of the full visible state.
static std::uint64_t handMultisetHash(const BattleContext &bc) {
    // Same card-identity hash as CombatObservation::visibleHash uses for piles.
    // Mirrors cardIdentityHash from CombatObservation.cpp.
    auto cardHash = [](const CardInstance &c) -> std::uint64_t {
        std::uint64_t h = static_cast<std::uint64_t>(c.getId()) * 6364136223846793005ULL;
        h += static_cast<std::uint64_t>(c.specialData) * 2654435761ULL;
        h += static_cast<std::uint64_t>(c.costForTurn) * 40503ULL;
        h += (c.isUpgraded() ? 1ULL : 0ULL) * 0x9e3779b97f4a7c15ULL;
        h += (c.freeToPlayOnce ? 1ULL : 0ULL) * 15461ULL;
        return h;
    };
    std::uint64_t acc = 0;
    for (int i = 0; i < bc.cards.cardsInHand; ++i)
        acc += cardHash(bc.cards.hand[i]);
    // Also mix in hand size so [Strike] != [Strike,Strike].
    acc ^= static_cast<std::uint64_t>(bc.cards.cardsInHand) * 0x9e3779b97f4a7c15ULL;
    return acc ? acc : 1;
}

// ── Outcome-bucket diagnostic ────────────────────────────────────────────
// For a pre-state + action at a stochastic boundary (END_TURN / card draw),
// replay the same transition under N fresh particles, bucket identical
// visible outcomes, and write one CSV row. This measures how many distinct
// observable futures a single decision actually produces — the fundamental
// number for local exact/chance outcome aggregation.
static void runOutcomeBucketDiag(
    const BattleContext &preState, const Action &action,
    int nParticles, std::mt19937_64 &diagRng,
    std::uint64_t seed, int encounter, int floorNum,
    int turn, int decisionIndex,
    std::ostream &out)
{
    // Generate fresh particles from the current observation.
    auto obs = CombatObservation::fromBattleContext(preState);
    auto particles = HiddenBattleState::sampleParticles(obs, preState, diagRng, nParticles);

    // Determine transition metadata.
    const char *transType = "END_TURN";
    const char *actionType = "END_TURN";
    int cardId = -1;
    if (action.getActionType() == ActionType::CARD) {
        transType = "CARD";
        actionType = "CARD";
        int hi = action.getSourceIdx();
        if (hi >= 0 && hi < preState.cards.cardsInHand)
            cardId = static_cast<int>(preState.cards.hand[hi].getId());
    }

    // Draw-pile metadata before transition.
    const int drawSizeBefore = (int)preState.cards.drawPile.size();
    const int discardSizeBefore = (int)preState.cards.discardPile.size();
    const int handSizeBefore = preState.cards.cardsInHand;

    // Replay under each particle, bucket by visibleHash and handHash.
    std::unordered_map<std::uint64_t, int> fullBucket;   // visibleHash → count
    std::unordered_map<std::uint64_t, int> handBucket;   // hand-only → count
    int reshuffleCount = 0;
    int cardsDrawn = 0;
    int handSizeAfter = 0;
    int lethalCount = 0;  // particles producing an immediately lethal hand

    for (const auto &p : particles) {
        BattleContext state = preState;
        applyParticleImpl(state, p, diagRng);

        // Detect reshuffle: if the draw pile was empty and discard was non-empty
        // before the action, the game reshuffles on draw.
        bool reshuffled = false;
        if (action.getActionType() == ActionType::END_TURN) {
            if (drawSizeBefore == 0 && discardSizeBefore > 0)
                reshuffled = true;
        }
        if (reshuffled) ++reshuffleCount;

        state.executeActions(); // process any queued actions
        action.execute(state);
        state.executeActions(); // finish the transition (monster turn, etc.)

        if (cardsDrawn == 0 && action.getActionType() == ActionType::END_TURN) {
            cardsDrawn = state.cards.cardsInHand; // new hand after draw
            handSizeAfter = state.cards.cardsInHand;
        }

        // Full visible-state hash.
        auto postObs = CombatObservation::fromBattleContext(state);
        std::uint64_t vh = postObs.visibleHash();
        ++fullBucket[vh];

        // Hand-only multiset hash.
        std::uint64_t hh = handMultisetHash(state);
        ++handBucket[hh];

        // Lethal check: does any legal CARD action immediately kill all monsters?
        if (state.inputState == InputState::PLAYER_NORMAL
            && state.outcome == Outcome::UNDECIDED
            && state.isCardPlayAllowed()) {
            bool lethal = false;
            for (int hi = 0; hi < state.cards.cardsInHand && !lethal; ++hi) {
                const auto &c = state.cards.hand[hi];
                if (c.getType() != CardType::ATTACK || !c.canUseOnAnyTarget(state))
                    continue;
                Action ca(ActionType::CARD, hi);
                if (!ca.isValidAction(state)) continue;
                BattleContext check = state;
                ca.execute(check);
                check.executeActions();
                bool allDead = true;
                for (int mi = 0; mi < check.monsters.monsterCount; ++mi)
                    if (check.monsters.arr[mi].curHp > 0) { allDead = false; break; }
                if (allDead) { lethal = true; break; }
            }
            if (lethal) ++lethalCount;
        }
    }

    // Sort bucket counts descending for compact representation.
    std::vector<int> fullCounts, handCounts;
    for (const auto &kv : fullBucket) fullCounts.push_back(kv.second);
    for (const auto &kv : handBucket) handCounts.push_back(kv.second);
    std::sort(fullCounts.begin(), fullCounts.end(), std::greater<int>());
    std::sort(handCounts.begin(), handCounts.end(), std::greater<int>());

    const int nFull = (int)fullBucket.size();
    const int nHand = (int)handBucket.size();
    const double comprFull = nFull > 0 ? (double)nParticles / nFull : 0.0;
    const double comprHand = nHand > 0 ? (double)nParticles / nHand : 0.0;
    const int largestFull = fullCounts.empty() ? 0 : fullCounts[0];
    const double largestFrac = nParticles > 0 ? (double)largestFull / nParticles : 0.0;
    const int singletonsFull = (int)std::count(fullCounts.begin(), fullCounts.end(), 1);
    const int singletonsHand = (int)std::count(handCounts.begin(), handCounts.end(), 1);

    // Entropy of the outcome distribution (in bits).
    double entropyFull = 0.0;
    for (int c : fullCounts) {
        double p = (double)c / nParticles;
        if (p > 0) entropyFull -= p * std::log2(p);
    }

    // Compact bucket representation: "21;14;10;..."
    auto fmtBuckets = [](const std::vector<int> &v) -> std::string {
        if (v.empty()) return "";
        std::ostringstream oss;
        for (size_t i = 0; i < v.size() && i < 12; ++i) {
            if (i) oss << ';';
            oss << v[i];
        }
        if (v.size() > 12) oss << ";...";
        return oss.str();
    };

    // Write CSV row (header protected by mutex for thread safety).
    static std::mutex headerMutex;
    static bool headerWritten = false;
    {
        std::lock_guard<std::mutex> lk(headerMutex);
        if (!headerWritten) {
            out << "seed,floor,encounter,turn,decisionIndex,"
                << "transitionType,actionType,cardId,"
                << "particlesSampled,drawPileBefore,discardBefore,handBefore,"
                << "cardsDrawn,handAfter,reshuffleOccurred,"
                << "uniqueFullObs,uniqueHandObs,"
                << "comprFull,comprHand,"
                << "largestBucket,largestBucketFrac,"
                << "singletonsFull,singletonsHand,"
                << "entropyFull,"
                << "lethalCount,lethalFrac,"
                << "bucketCountsFull,bucketCountsHand\n";
            headerWritten = true;
        }
    }

    // Protect the write with the same mutex so rows don't interleave.
    {
        std::lock_guard<std::mutex> lk(headerMutex);
        out << seed << ',' << floorNum << ',' << encounter << ','
            << turn << ',' << decisionIndex << ','
            << transType << ',' << actionType << ',' << cardId << ','
            << nParticles << ',' << drawSizeBefore << ',' << discardSizeBefore
            << ',' << handSizeBefore << ','
            << cardsDrawn << ',' << handSizeAfter << ',' << (reshuffleCount > 0 ? 1 : 0) << ','
            << nFull << ',' << nHand << ','
            << comprFull << ',' << comprHand << ','
            << largestFull << ',' << largestFrac << ','
            << singletonsFull << ',' << singletonsHand << ','
            << entropyFull << ','
            << lethalCount << ',' << (nParticles > 0 ? (double)lethalCount / nParticles : 0.0) << ','
            << '"' << fmtBuckets(fullCounts) << '"' << ','
            << '"' << fmtBuckets(handCounts) << '"' << '\n';
        out.flush();
    }
}

// ── Continuation-value evaluator (self-contained, no searcher needed) ───
// This hook observes an existing shared
// END_TURN child after one concrete particle transition, but only uses fresh
// searchers and copied states for all measurements. It never mutates the live
// tree, belief, RNG, or selected action.
namespace {

thread_local bool t_strategyFusionSuppressed = false;
thread_local std::unordered_set<std::uint64_t> t_strategyFusionSeen;
static std::atomic<int> g_strategyFusionTransitions{0};
static std::mutex g_strategyFusionOutputMutex;

std::uint64_t strategyFusionMix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

std::uint64_t strategyFusionSeed(std::uint64_t sourceSeed,
                                 std::uint64_t preObsHash,
                                 std::uint64_t postObsHash,
                                 int decisionIndex, int simulationIndex,
                                 int bucketIndex, std::uint64_t slot) {
    std::uint64_t seed = strategyFusionMix(sourceSeed ^ slot);
    seed = strategyFusionMix(seed ^ preObsHash);
    seed = strategyFusionMix(seed ^ postObsHash);
    seed = strategyFusionMix(seed ^ static_cast<std::uint64_t>(decisionIndex));
    seed = strategyFusionMix(seed ^ static_cast<std::uint64_t>(simulationIndex));
    seed = strategyFusionMix(seed ^ static_cast<std::uint64_t>(bucketIndex));
    return seed ? seed : 1;
}

double actionRootValue(const BattleScumSearcher3 &searcher,
                       const BattleContext &state,
                       const std::string &identity) {
    for (const auto &edge : searcher.root.edges) {
        if (semanticActionIdentity(edge.action, state) != identity) continue;
        if (edge.child.simulationCount <= 0)
            return std::numeric_limits<double>::quiet_NaN();
        return edge.child.evaluationSum / edge.child.simulationCount;
    }
    return std::numeric_limits<double>::quiet_NaN();
}

void writeStrategyFusionRow(
    std::uint64_t sourceSeed, int encounter, int floor, int turn,
    int decisionIndex, int simulationIndex, std::uint64_t preObsHash,
    std::uint64_t sharedChildCachedObsHash, std::uint64_t postObsHash,
    int drawPileBefore, int discardBefore, int particleCount, int bucketCount,
    double bucketProbability, int distinctBucketCount,
    std::int64_t parentObsVisits, std::int64_t parentObsMismatches,
    std::int64_t sharedChildVisits, const std::string &sharedAction,
    const std::string &conditionedAction,
    const std::string &matchedConditionedAction,
    const std::string &referenceAction, int sharedConditionedAgree,
    int sharedMatchedConditionedAgree, int referenceSharedAgree,
    int referenceConditionedAgree, int referenceMatchedConditionedAgree,
    int freshSims, int matchedSims, int referenceSims,
    double referenceValueShared, double referenceValueConditioned,
    double referenceValueMatched, double referenceMargin,
    double referenceMarginMatched, int sharedActionValid) {
    constexpr const char *header =
        "sourceSeed,encounter,floor,turn,decisionIdx,searchSimulationIndex,"
        "preObsHash,sharedChildCachedObsHash,postObsHash,drawPileSizeBefore,"
        "discardPileSizeBefore,particleCount,bucketCount,bucketProbability,"
        "distinctBucketCount,parentObsVisits,parentObsMismatches,"
        "sharedChildVisits,sharedAction,conditionedAction,"
        "matchedConditionedAction,referenceAction,sharedConditionedAgree,"
        "sharedMatchedConditionedAgree,referenceSharedAgree,"
        "referenceConditionedAgree,referenceMatchedConditionedAgree,"
        "freshSimBudget,matchedSimBudget,referenceSimBudget,"
        "referenceValueShared,referenceValueConditioned,referenceValueMatched,"
        "referenceMargin,referenceMarginMatched,sharedActionValid\n";
    std::lock_guard<std::mutex> lock(g_strategyFusionOutputMutex);
    if (g_s3StrategyFusionDiagFile.empty()) {
        static bool stderrHeader = false;
        if (!stderrHeader) { std::cerr << header; stderrHeader = true; }
        std::ostream &out = std::cerr;
        out << sourceSeed << ',' << encounter << ',' << floor << ',' << turn << ','
            << decisionIndex << ',' << simulationIndex << ',' << preObsHash << ','
            << sharedChildCachedObsHash << ',' << postObsHash << ','
            << drawPileBefore << ',' << discardBefore << ',' << particleCount << ','
            << bucketCount << ',' << bucketProbability << ',' << distinctBucketCount
            << ',' << parentObsVisits << ',' << parentObsMismatches << ','
            << sharedChildVisits << ',' << sharedAction << ','
            << conditionedAction << ',' << matchedConditionedAction << ','
            << referenceAction << ',' << sharedConditionedAgree << ','
            << sharedMatchedConditionedAgree << ',' << referenceSharedAgree << ','
            << referenceConditionedAgree << ',' << referenceMatchedConditionedAgree
            << ',' << freshSims << ',' << matchedSims << ',' << referenceSims
            << ',' << referenceValueShared << ',' << referenceValueConditioned << ','
            << referenceValueMatched << ',' << referenceMargin << ','
            << referenceMarginMatched << ',' << sharedActionValid << '\n';
        return;
    }
    std::ifstream probe(g_s3StrategyFusionDiagFile);
    const bool empty = !probe.good()
        || probe.peek() == std::ifstream::traits_type::eof();
    std::ofstream out(g_s3StrategyFusionDiagFile, std::ios::app);
    if (!out) return;
    if (empty) {
        out << header;
        std::ofstream meta(g_s3StrategyFusionDiagFile + ".meta.json");
        if (meta) {
            meta << "{\n"
                 << "  \"schema\": \"s3_strategy_fusion_diag_v3\",\n"
                 << "  \"diagnostic\": \"shadow-only; END_TURN shared-child strategy fusion\",\n"
                 << "  \"particleCount\": " << g_s3StrategyFusionDiagParticles << ",\n"
                 << "  \"maxTransitions\": " << g_s3StrategyFusionDiagMaxTransitions << ",\n"
                 << "  \"minChildVisits\": " << g_s3StrategyFusionDiagMinChildVisits << ",\n"
                 << "  \"freshSimBudget\": " << g_s3StrategyFusionDiagFreshSims << ",\n"
                 << "  \"matchedSimFormula\": \"max(1, round(sharedChildVisits * bucketProbability))\",\n"
                 << "  \"referenceSimBudget\": " << g_s3StrategyFusionDiagReferenceSims << ",\n"
                 << "  \"primaryComparison\": \"shared child vs matched-compute conditioned\",\n"
                 << "  \"secondaryComparison\": \"shared child vs configured fresh conditioned\",\n"
                 << "  \"parentObservationGate\": \"nodeObsMismatches == 0 at END_TURN parent\",\n"
                 << "  \"sideSearchLifecycle\": \"candidates recorded during step; side searches after normal search with final child statistics\",\n"
                 << "  \"normalSearchParticles\": " << g_s3Particles << ",\n"
                 << "  \"liveValid\": " << (g_liveValid ? 1 : 0) << ",\n"
                 << "  \"semanticCardEdges\": " << (g_s3SemanticCardEdges ? 1 : 0) << ",\n"
                 << "  \"bucketIdentity\": \"CombatObservation equality and visibleHash\",\n"
                 << "  \"freshBelief\": \"fresh Searcher3; canonicalized draw-pile multiset template\",\n"
                 << "  \"referenceInterpretation\": \"deeper Searcher3 reference, not ground truth\"\n"
                 << "}\n";
        }
    }
    out << sourceSeed << ',' << encounter << ',' << floor << ',' << turn << ','
        << decisionIndex << ',' << simulationIndex << ',' << preObsHash << ','
        << sharedChildCachedObsHash << ',' << postObsHash << ','
        << drawPileBefore << ',' << discardBefore << ',' << particleCount << ','
        << bucketCount << ',' << bucketProbability << ',' << distinctBucketCount
        << ',' << parentObsVisits << ',' << parentObsMismatches << ','
        << sharedChildVisits << ',' << sharedAction << ','
        << conditionedAction << ',' << matchedConditionedAction << ','
        << referenceAction << ',' << sharedConditionedAgree << ','
        << sharedMatchedConditionedAgree << ',' << referenceSharedAgree << ','
        << referenceConditionedAgree << ',' << referenceMatchedConditionedAgree
        << ',' << freshSims << ',' << matchedSims << ',' << referenceSims
        << ',' << referenceValueShared << ',' << referenceValueConditioned << ','
        << referenceValueMatched << ',' << referenceMargin << ','
        << referenceMarginMatched << ',' << sharedActionValid << '\n';
}

void runStrategyFusionDiag(const BattleScumSearcher3::Node &parentNode,
                           const BattleContext &preState,
                           const BattleScumSearcher3::Edge &sharedEdge,
                           std::uint64_t sourceSeed, int encounter, int floor,
                           int turn, int decisionIndex, int simulationIndex) {
    if (!g_s3StrategyFusionDiag || t_strategyFusionSuppressed
        || sharedEdge.action.getActionType() != ActionType::END_TURN
        || !parentNode.isObsStable()
        || g_strategyFusionTransitions.load() >= g_s3StrategyFusionDiagMaxTransitions)
        return;

    const auto preObs = CombatObservation::fromBattleContext(preState);
    const std::uint64_t seenKey = strategyFusionSeed(
        sourceSeed, preObs.visibleHash(), 0, decisionIndex, 0, 0,
        sharedEdge.action.bits);

    const int nParticles = std::max(1, g_s3StrategyFusionDiagParticles);
    std::mt19937_64 diagnosticRng(strategyFusionSeed(
        sourceSeed, preObs.visibleHash(), 0, decisionIndex, simulationIndex,
        0, 0x535446444941475FULL));
    const auto particles = HiddenBattleState::sampleParticles(
        preObs, preState, diagnosticRng, nParticles);
    struct Bucket {
        CombatObservation observation;
        std::vector<BattleContext> states;
    };
    std::unordered_map<CombatObservation, Bucket> buckets;
    for (const auto &particle : particles) {
        BattleContext state = preState;
        applyHiddenState(state, particle, diagnosticRng);
        if (!sharedEdge.action.isValidAction(state)) continue;
        sharedEdge.action.execute(state);
        const auto observation = CombatObservation::fromBattleContext(state);
        auto it = buckets.find(observation);
        if (it == buckets.end()) {
            Bucket bucket;
            bucket.observation = observation;
            bucket.states.push_back(std::move(state));
            buckets.emplace(observation, std::move(bucket));
        } else {
            it->second.states.push_back(std::move(state));
        }
    }
    if (buckets.size() < 2) return;
    if (!t_strategyFusionSeen.insert(seenKey).second) return;
    int transitionSlot = g_strategyFusionTransitions.load();
    for (;;) {
        if (transitionSlot >= g_s3StrategyFusionDiagMaxTransitions) return;
        if (g_strategyFusionTransitions.compare_exchange_weak(
                transitionSlot, transitionSlot + 1))
            break;
    }

    std::vector<Bucket *> ordered;
    ordered.reserve(buckets.size());
    for (auto &entry : buckets) ordered.push_back(&entry.second);
    std::sort(ordered.begin(), ordered.end(), [](const Bucket *a, const Bucket *b) {
        return a->observation.visibleHash() < b->observation.visibleHash();
    });

    const std::uint64_t sharedChildObsHash = sharedEdge.child.obsCached
        ? sharedEdge.child.obsHash : 0;

    for (size_t bucketIndex = 0; bucketIndex < ordered.size(); ++bucketIndex) {
        Bucket &bucket = *ordered[bucketIndex];
        const BattleContext &representative = bucket.states.front();
        const auto postObs = bucket.observation;
        const std::uint64_t postObsHash = postObs.visibleHash();
        const auto sharedAction = pickSearchAction(sharedEdge.child, representative);
        const std::string sharedId = sharedAction
            ? semanticActionIdentity(*sharedAction, representative) : std::string();
        std::optional<Action> conditionedAction;
        std::optional<Action> matchedConditionedAction;
        std::optional<Action> referenceAction;
        double valueShared = std::numeric_limits<double>::quiet_NaN();
        double valueConditioned = std::numeric_limits<double>::quiet_NaN();
        double valueMatched = std::numeric_limits<double>::quiet_NaN();
        const int matchedSims = std::max(
            1, static_cast<int>(std::lround(
                   static_cast<double>(sharedEdge.child.simulationCount)
                   * static_cast<double>(bucket.states.size()) / nParticles)));
        const int sharedValid = sharedAction
            ? (sharedAction->isValidAction(representative) ? 1 : 0) : -1;

        if (representative.outcome == Outcome::UNDECIDED) {
            const std::uint64_t freshSeed = strategyFusionSeed(
                sourceSeed, preObs.visibleHash(), postObsHash, decisionIndex,
                simulationIndex, static_cast<int>(bucketIndex),
                0x465245534853494DULL);
            const std::uint64_t referenceSeed = strategyFusionSeed(
                sourceSeed, preObs.visibleHash(), postObsHash, decisionIndex,
                simulationIndex, static_cast<int>(bucketIndex),
                0x5245464552454E43ULL);
            const std::uint64_t matchedSeed = strategyFusionSeed(
                sourceSeed, preObs.visibleHash(), postObsHash, decisionIndex,
                simulationIndex, static_cast<int>(bucketIndex),
                0x4D41544348454400ULL);
            const bool previousSuppressed = t_strategyFusionSuppressed;
            t_strategyFusionSuppressed = true;
            // CombatObservation equality intentionally treats drawPileContents
            // as a multiset. The current Belief::initial implementation keeps
            // that vector order as the input to std::shuffle, so make the
            // copied fair template canonical before constructing side
            // searchers. This removes representative hidden-order influence
            // without changing normal Searcher3 belief construction.
            BattleContext fairTemplate = representative;
            std::sort(fairTemplate.cards.drawPile.begin(),
                      fairTemplate.cards.drawPile.end(),
                      [](const CardInstance &a, const CardInstance &b) {
                          return FullHiddenCardId(a) < FullHiddenCardId(b);
                      });
            BattleScumSearcher3 fresh(
                fairTemplate, freshSeed, decisionIndex, std::max(1, g_s3Particles));
            fresh.search(std::max(0, g_s3StrategyFusionDiagFreshSims));
            conditionedAction = pickSearchAction(fresh.root, fairTemplate);
            BattleScumSearcher3 matched(
                fairTemplate, matchedSeed, decisionIndex, std::max(1, g_s3Particles));
            matched.search(matchedSims);
            matchedConditionedAction = pickSearchAction(matched.root, fairTemplate);
            BattleScumSearcher3 reference(
                fairTemplate, referenceSeed, decisionIndex, std::max(1, g_s3Particles));
            reference.search(std::max(0, g_s3StrategyFusionDiagReferenceSims));
            referenceAction = pickSearchAction(reference.root, fairTemplate);
            const std::string conditionedId = conditionedAction
                ? semanticActionIdentity(*conditionedAction, fairTemplate) : std::string();
            const std::string matchedId = matchedConditionedAction
                ? semanticActionIdentity(*matchedConditionedAction, fairTemplate) : std::string();
            const std::string referenceId = referenceAction
                ? semanticActionIdentity(*referenceAction, fairTemplate) : std::string();
            valueShared = sharedId.empty()
                ? std::numeric_limits<double>::quiet_NaN()
                : actionRootValue(reference, fairTemplate, sharedId);
            valueConditioned = conditionedId.empty()
                ? std::numeric_limits<double>::quiet_NaN()
                : actionRootValue(reference, fairTemplate, conditionedId);
            valueMatched = matchedId.empty()
                ? std::numeric_limits<double>::quiet_NaN()
                : actionRootValue(reference, fairTemplate, matchedId);
            t_strategyFusionSuppressed = previousSuppressed;
            const int sharedConditionedAgree =
                (!sharedId.empty() && !conditionedId.empty())
                    ? (sharedId == conditionedId ? 1 : 0) : -1;
            const int sharedMatchedConditionedAgree =
                (!sharedId.empty() && !matchedId.empty())
                    ? (sharedId == matchedId ? 1 : 0) : -1;
            const int referenceSharedAgree =
                (!referenceId.empty() && !sharedId.empty())
                    ? (referenceId == sharedId ? 1 : 0) : -1;
            const int referenceConditionedAgree =
                (!referenceId.empty() && !conditionedId.empty())
                    ? (referenceId == conditionedId ? 1 : 0) : -1;
            const int referenceMatchedConditionedAgree =
                (!referenceId.empty() && !matchedId.empty())
                    ? (referenceId == matchedId ? 1 : 0) : -1;
            const double margin = (std::isnan(valueShared)
                                   || std::isnan(valueConditioned))
                ? std::numeric_limits<double>::quiet_NaN()
                : valueConditioned - valueShared;
            const double matchedMargin = (std::isnan(valueShared)
                                          || std::isnan(valueMatched))
                ? std::numeric_limits<double>::quiet_NaN()
                : valueMatched - valueShared;
            writeStrategyFusionRow(
                sourceSeed, encounter, floor, turn, decisionIndex, simulationIndex,
                preObs.visibleHash(), sharedChildObsHash, postObsHash,
                static_cast<int>(preState.cards.drawPile.size()),
                static_cast<int>(preState.cards.discardPile.size()), nParticles,
                static_cast<int>(bucket.states.size()),
                static_cast<double>(bucket.states.size()) / nParticles,
                static_cast<int>(buckets.size()), parentNode.nodeObsVisits,
                parentNode.nodeObsMismatches, sharedEdge.child.simulationCount,
                sharedId, conditionedId, matchedId, referenceId,
                sharedConditionedAgree, sharedMatchedConditionedAgree,
                referenceSharedAgree, referenceConditionedAgree,
                referenceMatchedConditionedAgree,
                g_s3StrategyFusionDiagFreshSims,
                matchedSims, g_s3StrategyFusionDiagReferenceSims, valueShared,
                valueConditioned, valueMatched, margin, matchedMargin, sharedValid);
        } else {
            writeStrategyFusionRow(
                sourceSeed, encounter, floor, turn, decisionIndex, simulationIndex,
                preObs.visibleHash(), sharedChildObsHash, postObsHash,
                static_cast<int>(preState.cards.drawPile.size()),
                static_cast<int>(preState.cards.discardPile.size()), nParticles,
                static_cast<int>(bucket.states.size()),
                static_cast<double>(bucket.states.size()) / nParticles,
                static_cast<int>(buckets.size()), parentNode.nodeObsVisits,
                parentNode.nodeObsMismatches, sharedEdge.child.simulationCount,
                sharedId, "", "", "", -1, -1, -1, -1, -1,
                g_s3StrategyFusionDiagFreshSims,
                matchedSims, g_s3StrategyFusionDiagReferenceSims,
                std::numeric_limits<double>::quiet_NaN(),
                std::numeric_limits<double>::quiet_NaN(),
                std::numeric_limits<double>::quiet_NaN(),
                std::numeric_limits<double>::quiet_NaN(),
                std::numeric_limits<double>::quiet_NaN(), sharedValid);
        }
    }
}

} // namespace

void BattleScumSearcher3::recordStrategyFusionCandidate(
    const Node &parentNode, const BattleContext &preState,
    const Edge &sharedEdge, const std::vector<Node *> &path,
    std::uint64_t sourceSeed, int encounter, int floor, int turn,
    int simulationIndex) {
    if (!g_s3StrategyFusionDiag || t_strategyFusionSuppressed
        || sharedEdge.action.getActionType() != ActionType::END_TURN
        || !parentNode.isObsStable()
        || sharedEdge.child.simulationCount < g_s3StrategyFusionDiagMinChildVisits
        || g_strategyFusionTransitions.load() >= g_s3StrategyFusionDiagMaxTransitions)
        return;

    StrategyFusionCandidate candidate;
    candidate.preState = preState;
    candidate.action = sharedEdge.action;
    candidate.sourceSeed = sourceSeed;
    candidate.encounter = encounter;
    candidate.floor = floor;
    candidate.turn = turn;
    candidate.decisionIndex = decisionIndex;
    candidate.simulationIndex = simulationIndex;
    candidate.seenKey = strategyFusionSeed(
        sourceSeed, CombatObservation::fromBattleContext(preState).visibleHash(),
        0, decisionIndex, 0, 0, sharedEdge.action.bits);
    candidate.thresholdSharedChildVisits = sharedEdge.child.simulationCount;

    for (const auto &existing : strategyFusionCandidates)
        if (existing.seenKey == candidate.seenKey)
            return;

    for (size_t depth = 0; depth + 1 < path.size(); ++depth) {
        const Node *from = path[depth];
        const Node *to = path[depth + 1];
        int childIndex = -1;
        for (size_t edgeIndex = 0; edgeIndex < from->edges.size(); ++edgeIndex) {
            if (&from->edges[edgeIndex].child == to) {
                childIndex = static_cast<int>(edgeIndex);
                break;
            }
        }
        if (childIndex < 0)
            return;
        candidate.parentEdgePath.push_back(childIndex);
    }

    for (size_t edgeIndex = 0; edgeIndex < parentNode.edges.size(); ++edgeIndex) {
        if (&parentNode.edges[edgeIndex] == &sharedEdge) {
            candidate.edgeIndex = static_cast<int>(edgeIndex);
            break;
        }
    }
    if (candidate.edgeIndex < 0)
        return;

    strategyFusionCandidates.push_back(std::move(candidate));
}

void BattleScumSearcher3::finalizeStrategyFusionDiag() {
    if (!g_s3StrategyFusionDiag || t_strategyFusionSuppressed)
        return;

    for (const auto &candidate : strategyFusionCandidates) {
        if (g_strategyFusionTransitions.load()
                >= g_s3StrategyFusionDiagMaxTransitions)
            break;

        Node *parent = &root;
        bool pathValid = true;
        for (int edgeIndex : candidate.parentEdgePath) {
            if (edgeIndex < 0
                || edgeIndex >= static_cast<int>(parent->edges.size())) {
                pathValid = false;
                break;
            }
            parent = &parent->edges[edgeIndex].child;
        }
        if (!pathValid || candidate.edgeIndex < 0
            || candidate.edgeIndex >= static_cast<int>(parent->edges.size()))
            continue;

        Edge &sharedEdge = parent->edges[candidate.edgeIndex];
        if (sharedEdge.action.bits != candidate.action.bits
            || sharedEdge.action.getActionType() != ActionType::END_TURN
            || !parent->isObsStable()
            || sharedEdge.child.simulationCount < g_s3StrategyFusionDiagMinChildVisits)
            continue;

        // This snapshot is intentionally taken immediately before the side
        // searches. It is the final post-search child count, not the count at
        // which the candidate first crossed the eligibility threshold.
        strategyFusionFinalVisitRecords.emplace_back(
            candidate.thresholdSharedChildVisits,
            sharedEdge.child.simulationCount);
        runStrategyFusionDiag(
            *parent, candidate.preState, sharedEdge,
            candidate.sourceSeed, candidate.encounter, candidate.floor,
            candidate.turn, candidate.decisionIndex, candidate.simulationIndex);
    }
}

// Continuation-value evaluator (self-contained, no searcher needed): runs K
// weighted-random rollouts from a post-END_TURN state, evaluates each
// with the learned leaf (vnet) or terminal outcome. Returns mean value.
// The rng is reseeded per rollout-slot for CRN pairing across members.
static double evalContinuation(const BattleContext &startState,
                                int kRollouts, std::mt19937_64 &rng) {
    double sum = 0.0;
    for (int k = 0; k < kRollouts; ++k) {
        BattleContext bc = startState;
        for (int steps = 0; steps < 200 && bc.outcome == Outcome::UNDECIDED; ++steps) {
            BattleScumSearcher3::Node tmp;
            enumerateActionsForNode(tmp, bc);
            if (tmp.edges.empty()) break;
            int totalW = 0;
            for (const auto &e : tmp.edges) {
                if (e.action.getActionType() == ActionType::CARD) {
                    auto t = bc.cards.hand[e.action.getSourceIdx()].getType();
                    if (t == CardType::ATTACK) totalW += 8;
                    else if (t == CardType::POWER) totalW += 3;
                    else totalW += 2;
                } else {
                    totalW += 1;
                }
            }
            if (totalW <= 0) break;
            int pick = std::uniform_int_distribution<int>(0, totalW - 1)(rng);
            int running = 0, chosen = -1;
            for (int i = 0; i < (int)tmp.edges.size(); ++i) {
                int w = 1;
                if (tmp.edges[i].action.getActionType() == ActionType::CARD) {
                    auto t = bc.cards.hand[tmp.edges[i].action.getSourceIdx()].getType();
                    if (t == CardType::ATTACK) w = 8;
                    else if (t == CardType::POWER) w = 3;
                    else w = 2;
                }
                running += w;
                if (pick < running) { chosen = i; break; }
            }
            if (chosen < 0) break;
            const auto &a = tmp.edges[chosen].action;
            if (!a.isValidAction(bc)) break;
            a.execute(bc);
        }
        if (bc.outcome == Outcome::PLAYER_VICTORY) sum += 100.0;
        else if (bc.outcome == Outcome::PLAYER_LOSS) sum += 0.0;
        else if (g_useVNet && g_combatVNet.loaded())
            sum += g_combatVNet.predict(bc);
        else
            sum += (double)bc.player.curHp;
    }
    return sum / kRollouts;
}

// ── Bucket-value diagnostic ─────────────────────────────────────────────
// For each unique (preState, END_TURN) pair: generate particles, bucket by
// post-transition visibleHash, sample members from each bucket, evaluate
// continuation value per member, compute within/between-bucket statistics.
static void runBucketValueDiag(
    const BattleContext &preState, const Action &action,
    std::uint64_t seed, int encounter, int floor, int turn, int decIdx,
    std::mt19937_64 &diagRng, std::ostream &out)
{
    const int nParticles = 64;
    const int kRollouts = g_s3BucketValueDiagRollouts;
    const int maxSample = g_s3BucketValueDiagSampleMembers;

    // 1. Generate particles and execute END_TURN.
    auto obs = CombatObservation::fromBattleContext(preState);
    auto particles = HiddenBattleState::sampleParticles(obs, preState, diagRng, nParticles);

    struct Member {
        BattleContext state;
        int particleIdx;
        std::uint64_t visHash;
        // Hidden-state RNG seeds for stratification.
        std::uint64_t shuffleSeed0, cardRandomSeed0, aiSeed0;
    };
    std::unordered_map<std::uint64_t, std::vector<Member>> buckets;

    const int drawSizeBefore = (int)preState.cards.drawPile.size();
    const int discardBefore = (int)preState.cards.discardPile.size();
    int reshuffle = 0, cardsDrawn = 0, handAfter = 0;

    for (int pi = 0; pi < nParticles; ++pi) {
        BattleContext state = preState;
        applyParticleImpl(state, particles[pi], diagRng);
        if (drawSizeBefore == 0 && discardBefore > 0) reshuffle = 1;
        state.executeActions();
        action.execute(state);
        state.executeActions();
        if (cardsDrawn == 0) { cardsDrawn = state.cards.cardsInHand; handAfter = cardsDrawn; }

        Member m;
        m.state = state;
        m.particleIdx = pi;
        m.visHash = CombatObservation::fromBattleContext(state).visibleHash();
        m.shuffleSeed0 = particles[pi].shuffleRngSeed0;
        m.cardRandomSeed0 = particles[pi].cardRandomRngSeed0;
        m.aiSeed0 = particles[pi].aiRngSeed0;
        buckets[m.visHash].push_back(std::move(m));
    }

    // 2. For each bucket, sample members and evaluate.
    struct BucketRow {
        std::uint64_t visHash;
        int bucketSize, sampledMembers;
        double meanVal, stdVal, minVal, maxVal;
        std::vector<double> memberValues;
        // Hidden-state agreement flags.
        bool allSameShuffleSeed, allSameCardRandSeed, allSameAiSeed;
        bool allSameDrawPrefix; // first card of draw pile same?
    };
    std::vector<BucketRow> bucketRows;

    for (auto &kv : buckets) {
        auto &members = kv.second;
        if ((int)members.size() < 2) continue; // skip singletons

        BucketRow br;
        br.visHash = kv.first;
        br.bucketSize = (int)members.size();

        // Sample members (shuffle so first N are random).
        std::shuffle(members.begin(), members.end(), diagRng);
        int nSample = std::min((int)members.size(), maxSample);
        br.sampledMembers = nSample;

        // Check hidden-state agreement.
        std::uint64_t ss0 = members[0].shuffleSeed0;
        std::uint64_t cr0 = members[0].cardRandomSeed0;
        std::uint64_t ai0 = members[0].aiSeed0;
        CardId firstCard = CardId::INVALID;
        if (members[0].state.cards.drawPile.size() > 0)
            firstCard = members[0].state.cards.drawPile[0].getId();
        br.allSameShuffleSeed = true;
        br.allSameCardRandSeed = true;
        br.allSameAiSeed = true;
        br.allSameDrawPrefix = true;
        for (int i = 1; i < nSample; ++i) {
            if (members[i].shuffleSeed0 != ss0) br.allSameShuffleSeed = false;
            if (members[i].cardRandomSeed0 != cr0) br.allSameCardRandSeed = false;
            if (members[i].aiSeed0 != ai0) br.allSameAiSeed = false;
            if (br.allSameDrawPrefix && members[i].state.cards.drawPile.size() > 0) {
                if (members[i].state.cards.drawPile[0].getId() != firstCard)
                    br.allSameDrawPrefix = false;
            }
        }

        // Evaluate each sampled member.
        br.memberValues.reserve(nSample);
        double sumV = 0.0;
        br.minVal = 1e30; br.maxVal = -1e30;
        for (int i = 0; i < nSample; ++i) {
            // Use a fixed per-slot RNG for CRN pairing across members.
            // Seed from visHash + member index so each "member slot" gets
            // reproducible rollout RNG.
            std::mt19937_64 slotRng;
            std::uint64_t slotSeed = br.visHash ^ (std::uint64_t)(i * 2654435761ULL);
            slotRng.seed(slotSeed ? slotSeed : 1);

            double v = evalContinuation(members[i].state, kRollouts, slotRng);
            br.memberValues.push_back(v);
            sumV += v;
            if (v < br.minVal) br.minVal = v;
            if (v > br.maxVal) br.maxVal = v;
        }
        br.meanVal = sumV / nSample;
        double varSum = 0.0;
        for (double v : br.memberValues) varSum += (v - br.meanVal) * (v - br.meanVal);
        br.stdVal = nSample > 1 ? std::sqrt(varSum / (nSample - 1)) : 0.0;

        bucketRows.push_back(br);
    }

    if (bucketRows.empty()) return;

    // 3. Compute transition-level statistics.
    // Between-bucket variance: variance of bucket means.
    double grandMean = 0.0;
    double totalMass = 0.0;
    for (const auto &br : bucketRows) {
        grandMean += br.meanVal * br.bucketSize;
        totalMass += br.bucketSize;
    }
    grandMean /= totalMass;

    double betweenVar = 0.0;
    double withinVarSum = 0.0;
    double withinMass = 0.0;
    for (const auto &br : bucketRows) {
        double diff = br.meanVal - grandMean;
        betweenVar += br.bucketSize * diff * diff;
        if (br.sampledMembers > 1) {
            double varEst = br.stdVal * br.stdVal;
            withinVarSum += varEst * (br.bucketSize - 1);
            withinMass += (br.bucketSize - 1);
        }
    }
    betweenVar /= (totalMass - 1);
    double withinVar = withinMass > 0 ? withinVarSum / withinMass : 0.0;
    double wbRatio = betweenVar > 1e-9 ? withinVar / betweenVar : 0.0;

    // 4. Representative error: one random member per bucket.
    // Use the first sampled member as the representative (already shuffled).
    double vBucketed = 0.0, vAll = 0.0;
    double absErrSum = 0.0;
    int bucketCount = (int)bucketRows.size();
    for (const auto &br : bucketRows) {
        double bucketMean = br.meanVal;
        double repVal = br.memberValues[0]; // first (random) member
        double weight = (double)br.bucketSize / nParticles;
        vBucketed += weight * repVal;
        vAll += weight * bucketMean;
        absErrSum += std::abs(repVal - bucketMean);
    }
    double repMAE = bucketCount > 0 ? absErrSum / bucketCount : 0.0;

    // Lethal fraction: what fraction of particle mass is in terminal states?
    int lethalMass = 0;
    for (const auto &kv : buckets) {
        for (const auto &m : kv.second) {
            if (m.state.outcome == Outcome::PLAYER_VICTORY
                || m.state.outcome == Outcome::PLAYER_LOSS)
                ++lethalMass;
        }
    }
    double lethalFrac = (double)lethalMass / nParticles;

    // 5. Write CSV rows (header written once).
    static std::mutex bvMutex;
    static bool bvHeaderWritten = false;
    {
        std::lock_guard<std::mutex> lk(bvMutex);
        if (!bvHeaderWritten) {
            out << "seed,floor,encounter,turn,decIdx,visHash,"
                << "drawPileBefore,discardBefore,reshuffle,cardsDrawn,handAfter,lethalFrac,"
                << "bucketSize,sampledMembers,"
                << "meanVal,stdVal,minVal,maxVal,rangeVal,"
                << "allSameShuffleSeed,allSameCardRandSeed,allSameAiSeed,allSameDrawPrefix,"
                << "transition_nBuckets,transition_betweenVar,transition_withinVar,transition_wbRatio,"
                << "transition_vAll,transition_vBucketed,transition_vBias,transition_repMAE,"
                << "memberValues\n";
            bvHeaderWritten = true;
        }
    }

    for (const auto &br : bucketRows) {
        std::ostringstream mv;
        for (size_t i = 0; i < br.memberValues.size(); ++i) {
            if (i) mv << ';';
            mv << br.memberValues[i];
        }
        std::lock_guard<std::mutex> lk(bvMutex);
        out << seed << ',' << floor << ',' << encounter << ','
            << turn << ',' << decIdx << ',' << br.visHash << ','
            << drawSizeBefore << ',' << discardBefore << ',' << reshuffle << ','
            << cardsDrawn << ',' << handAfter << ',' << lethalFrac << ','
            << br.bucketSize << ',' << br.sampledMembers << ','
            << br.meanVal << ',' << br.stdVal << ',' << br.minVal << ',' << br.maxVal
            << ',' << (br.maxVal - br.minVal) << ','
            << (br.allSameShuffleSeed ? 1 : 0) << ','
            << (br.allSameCardRandSeed ? 1 : 0) << ','
            << (br.allSameAiSeed ? 1 : 0) << ','
            << (br.allSameDrawPrefix ? 1 : 0) << ','
            << bucketCount << ',' << betweenVar << ',' << withinVar << ',' << wbRatio << ','
            << vAll << ',' << vBucketed << ',' << (vBucketed - vAll) << ',' << repMAE << ','
            << '"' << mv.str() << '"' << '\n';
        out.flush();
    }
}

// ── Helper: maybe run bucket VALUE diagnostic before executing an action ──
static void maybeBucketValueDiag(
    const BattleContext &preState, const Action &action,
    std::uint64_t seed, int encounter, int floor, int turn, int decIdx)
{
    if (!g_s3BucketValueDiag) return;
    if (action.getActionType() != ActionType::END_TURN) return;
    if (t_bvdRowCount >= g_s3BucketValueDiagMaxTransitions) return;

    auto obs = CombatObservation::fromBattleContext(preState);
    std::uint64_t key = obs.visibleHash();
    if (!t_bvdSeen.insert(key).second) return;

    if (!t_bvdRngSeeded) {
        std::uint64_t h = key ^ seed;
        t_bvdRng.seed(h ? h : 1);
        t_bvdRngSeeded = true;
    }
    if (!t_bvdOutOpen && !g_s3BucketValueDiagFile.empty()) {
        t_bvdOut.open(g_s3BucketValueDiagFile, std::ios::app);
        t_bvdOutOpen = true;
    }
    std::ostream &out = t_bvdOutOpen ? t_bvdOut : std::cerr;

    ++t_bvdRowCount;
    runBucketValueDiag(preState, action, seed, encounter, floor, turn, decIdx,
                       t_bvdRng, out);
}

// ── Card classification for draw-probability diagnostic ────────────────
// Classify cards in the draw pile by their tactical role for the next turn.
static void classifyDrawPile(
    const BattleContext &preState,
    int &attackOuts, int &playableAttackOuts,
    int &blockOuts, int &enoughBlockOuts,
    int &singleCardLethalOuts,
    std::string &skipLethalReason)
{
    attackOuts = 0;
    playableAttackOuts = 0;
    blockOuts = 0;
    enoughBlockOuts = 0;
    singleCardLethalOuts = 0;
    skipLethalReason.clear();

    // Try to determine the post-monster-turn state for lethal checking.
    // Copy the pre-state and advance through END_TURN + monster actions.
    BattleContext postState = preState;

    // Apply a neutral particle for determinism.
    HiddenBattleState neutralP;
    neutralP.randomize(t_diagRng);
    applyParticleImpl(postState, neutralP, t_diagRng);

    // Advance through END_TURN.
    Action endTurn(ActionType::END_TURN);
    endTurn.execute(postState);
    postState.executeActions();

    // Now postState is the post-monster-turn, pre-draw state.
    // Check for effects that make the post-turn state nondeterministic.
    bool monsterRngSafe = true;

    // Skip if Ink Bottle would trigger (random draw on turn start).
    if (postState.player.hasRelicRuntime(RelicId::INK_BOTTLE) &&
        postState.player.inkBottleCounter == 9) {
        if (!skipLethalReason.empty()) skipLethalReason += ";";
        skipLethalReason += "inkBottle";
        monsterRngSafe = false;
    }
    // Skip if there are random-target effects or unknown intents.
    // For this diagnostic, most standard enemies have deterministic attack
    // patterns; multi-hit attacks in this engine have fixed per-hit damage.

    // Total enemy HP and incoming damage.
    int enemyHpTotal = 0;
    int incomingDamage = 0;
    for (int mi = 0; mi < postState.monsters.monsterCount; ++mi) {
        const auto &m = postState.monsters.arr[mi];
        if (m.curHp > 0) {
            enemyHpTotal += m.curHp + m.block;
            if (m.isAttacking()) {
                auto di = m.getMoveBaseDamage(postState);
                incomingDamage += m.calculateDamageToPlayer(postState, di.damage) * di.attackCount;
            }
        }
    }

    // For each card in the draw pile, classify.
    for (const auto &c : preState.cards.drawPile) {
        CardType ct = c.getType();
        bool isAttack = (ct == CardType::ATTACK);
        bool isSkill = (ct == CardType::SKILL);

        if (isAttack) ++attackOuts;
        if (isSkill) ++blockOuts;  // approximate: most skills provide block/utility

        // Check playability: cost and targeting.
        bool playable = (c.costForTurn <= postState.player.energy || c.costForTurn == -1);
        // Check targeting: need at least one targetable enemy.
        bool hasTarget = false;
        for (int mi = 0; mi < postState.monsters.monsterCount; ++mi)
            if (postState.monsters.arr[mi].curHp > 0 && postState.monsters.arr[mi].isTargetable())
                { hasTarget = true; break; }

        if (isAttack && playable && (hasTarget || !c.requiresTarget()))
            ++playableAttackOuts;

        // Enough block: one playable block card covers all incoming damage.
        if (isSkill && playable) {
            // Simple heuristic: if the card provides block greater than incoming damage
            // minus current block after enemy turn.
            int currentBlock = postState.player.block;
            // We don't know the exact block amount without executing the card.
            // Use a rough estimate: Defend provides 5(8) block.
            int approxBlock = 5 + (c.isUpgraded() ? 3 : 0);
            if (currentBlock + approxBlock >= incomingDamage)
                ++enoughBlockOuts;
        }

        // Single-card lethal check.
        if (monsterRngSafe && isAttack && playable) {
            // Simulate playing this one card from the post-monster-turn state.
            BattleContext lethalCheck = postState;
            // Add the card to hand and try to play it.
            int hi = lethalCheck.cards.cardsInHand;
            if (hi < CardManager::MAX_HAND_SIZE) {
                lethalCheck.cards.hand[hi] = c;
                lethalCheck.cards.cardsInHand = hi + 1;
                Action ca(ActionType::CARD, hi);
                // Check each targetable monster.
                for (int t = lethalCheck.monsters.monsterCount - 1; t >= 0; --t) {
                    if (lethalCheck.monsters.arr[t].curHp <= 0 ||
                        !lethalCheck.monsters.arr[t].isTargetable()) continue;
                    BattleContext check = lethalCheck;
                    Action targeted(ActionType::CARD, hi, t);
                    if (!targeted.isValidAction(check)) continue;
                    targeted.execute(check);
                    check.executeActions();
                    bool allDead = true;
                    for (int mi = 0; mi < check.monsters.monsterCount; ++mi)
                        if (check.monsters.arr[mi].curHp > 0) { allDead = false; break; }
                    if (allDead) {
                        ++singleCardLethalOuts;
                        break;  // card counted once
                    }
                }
            }
        }
    }

    if (!monsterRngSafe && skipLethalReason.empty())
        skipLethalReason = "unknown";
}

// ── Draw-probability diagnostic hook ───────────────────────────────────
static void maybeDrawProbDiag(
    const BattleContext &preState,
    std::uint64_t seed, int encounter, int floor, int turn, int decIdx,
    std::int64_t endTurnVisits, double endTurnQ, float endTurnPrior)
{
    if (!g_s3DrawProbDiag) return;
    if (preState.cards.drawPile.empty()) return;  // nothing to draw

    // Pre-state identity for cross-thread dedup.
    auto obs = CombatObservation::fromBattleContext(preState);
    std::uint64_t vh = obs.visibleHash();

    // Global dedup under mutex.
    {
        std::lock_guard<std::mutex> lk(g_drawProbMutex);
        if (g_drawProbRowCount >= kMaxDrawProbRows) return;
        if (!g_drawProbSeen.insert(vh).second) return;
    }

    // Determine draw count D by simulating END_TURN on a copy.
    BattleContext simState = preState;
    // Use a neutral particle for determinism.
    HiddenBattleState neutralParticle;
    neutralParticle.randomize(t_diagRng);
    applyParticleImpl(simState, neutralParticle, t_diagRng);
    simState.executeActions();
    Action endTurn(ActionType::END_TURN);
    endTurn.execute(simState);
    simState.executeActions();

    const int handAfter = simState.cards.cardsInHand;
    const int handBefore = preState.cards.cardsInHand;
    int cardsToDraw = handAfter;  // hand is discarded then D new cards drawn
    if (preState.player.hasRelicRuntime(RelicId::RUNIC_PYRAMID))
        cardsToDraw = handAfter - handBefore;  // retain hand

    const int N = (int)preState.cards.drawPile.size();
    const int discardBefore = (int)preState.cards.discardPile.size();
    const bool reshuffle = (N == 0 && discardBefore > 0);
    if (reshuffle) return;  // skip reshuffles
    if (cardsToDraw <= 0 || N <= 0) return;

    // Classify draw pile.
    int attackOuts, playableAttackOuts, blockOuts, enoughBlockOuts, lethalOuts;
    std::string skipLethalReason;
    classifyDrawPile(preState, attackOuts, playableAttackOuts, blockOuts,
                     enoughBlockOuts, lethalOuts, skipLethalReason);

    // Compute probabilities.
    // pLethal = -1: skipped/unclassifiable (RNG issues)
    // pLethal = 0: classified, zero lethal outs
    // pLethal > 0: has lethal outs
    double pLethal;
    if (!skipLethalReason.empty())
        pLethal = -1.0;  // unclassifiable
    else if (lethalOuts > 0)
        pLethal = hypergeometricAtLeastOne(N, lethalOuts, cardsToDraw);
    else
        pLethal = 0.0;  // classified, no lethal outs
    double pAnyAttack = hypergeometricAtLeastOne(N, attackOuts, cardsToDraw);
    double pAnyPlayableAttack = hypergeometricAtLeastOne(N, playableAttackOuts, cardsToDraw);
    double pAnyBlock = hypergeometricAtLeastOne(N, blockOuts, cardsToDraw);
    double pEnoughBlock = hypergeometricAtLeastOne(N, enoughBlockOuts, cardsToDraw);
    double expAttacks = expectedCount(N, attackOuts, cardsToDraw);
    double expBlock = expectedCount(N, blockOuts, cardsToDraw);

    // Player/enemy summary.
    int enemyHpTotal = 0, incomingDamage = 0;
    for (int mi = 0; mi < preState.monsters.monsterCount; ++mi) {
        const auto &m = preState.monsters.arr[mi];
        if (m.curHp > 0) enemyHpTotal += m.curHp + m.block;
        if (m.isAttacking()) {
            auto di = m.getMoveBaseDamage(preState);
            incomingDamage += m.calculateDamageToPlayer(preState, di.damage) * di.attackCount;
        }
    }

    // Write CSV (mutex-guarded).
    {
        std::lock_guard<std::mutex> lk(g_drawProbMutex);
        ++g_drawProbRowCount;

        // Open file lazily.
        static std::ofstream dpOut;
        static bool dpOutOpen = false;
        if (!dpOutOpen && !g_s3DrawProbDiagFile.empty()) {
            dpOut.open(g_s3DrawProbDiagFile, std::ios::app);
            dpOutOpen = true;
        }
        std::ostream &out = dpOutOpen ? dpOut : std::cerr;

        if (!g_drawProbHeaderWritten) {
            out << "seed,floor,encounter,turn,decIdx,visibleHash,"
                << "playerHp,playerBlock,energy,handSize,drawPileSize,discardPileSize,cardsToDraw,"
                << "enemyHpTotal,incomingDamage,reshuffle,"
                << "attackOuts,playableAttackOuts,blockOuts,enoughBlockOuts,lethalOuts,"
                << "pLethal,pAnyAttack,pAnyPlayableAttack,pAnyBlock,pEnoughBlock,"
                << "expAttacks,expBlock,"
                << "endTurnVisits,endTurnQ,endTurnPrior,skipLethalReason\n";
            g_drawProbHeaderWritten = true;
        }

        out << seed << ',' << floor << ',' << encounter << ','
            << turn << ',' << decIdx << ',' << vh << ','
            << preState.player.curHp << ',' << preState.player.block << ','
            << preState.player.energy << ',' << handBefore << ','
            << N << ',' << discardBefore << ',' << cardsToDraw << ','
            << enemyHpTotal << ',' << incomingDamage << ',' << (reshuffle ? 1 : 0) << ','
            << attackOuts << ',' << playableAttackOuts << ','
            << blockOuts << ',' << enoughBlockOuts << ',' << lethalOuts << ','
            << pLethal << ',' << pAnyAttack << ',' << pAnyPlayableAttack << ','
            << pAnyBlock << ',' << pEnoughBlock << ','
            << expAttacks << ',' << expBlock << ','
            << endTurnVisits << ',' << endTurnQ << ',' << endTurnPrior << ','
            << '"' << skipLethalReason << '"' << '\n';
        out.flush();
    }

    // ── Leaf-value residual: if enabled, run 1k+4k fresh searches ────
    if (g_s3LeafValueDiag && g_drawProbRowCount <= g_s3LeafValueDiagMaxStates) {
        // Stratified sampling: aim for ~30 p=0, ~10 (0,0.5), ~15 [0.5,0.9), ~15 [0.9,1), ~30 p=1
        // Only run deep search for states that fit within bin quotas.
        static std::mutex lvMutex;
        static int lvCountP0 = 0, lvCountLow = 0, lvCountMed = 0, lvCountHigh = 0, lvCountP1 = 0;
        static constexpr int lvQuotaP0 = 30, lvQuotaLow = 10, lvQuotaMed = 15, lvQuotaHigh = 15, lvQuotaP1 = 30;

        bool shouldRun = false;
        {
            std::lock_guard<std::mutex> lk(lvMutex);
            if (pLethal < 0) { /* skip: unclassified */ }
            else if (pLethal == 0.0 && lvCountP0 < lvQuotaP0) { ++lvCountP0; shouldRun = true; }
            else if (pLethal > 0 && pLethal < 0.5 && lvCountLow < lvQuotaLow) { ++lvCountLow; shouldRun = true; }
            else if (pLethal >= 0.5 && pLethal < 0.9 && lvCountMed < lvQuotaMed) { ++lvCountMed; shouldRun = true; }
            else if (pLethal >= 0.9 && pLethal < 1.0 && lvCountHigh < lvQuotaHigh) { ++lvCountHigh; shouldRun = true; }
            else if (pLethal >= 1.0 && lvCountP1 < lvQuotaP1) { ++lvCountP1; shouldRun = true; }
        }
        if (!shouldRun) return;

        // ── Run fresh searcher: 1k then continue to 4k ──────────────
        auto t0 = std::chrono::steady_clock::now();

        // Use a fixed diagnostic seed based on state hash.
        std::uint64_t diagSeed = vh ^ 0x9e3779b97f4a7c15ULL;
        BattleContext stateCopy = preState;

        BattleScumSearcher3 refSearcher(stateCopy, diagSeed, 0, 64);

        // Search 1000 sims.
        refSearcher.searchToTotal(g_s3LeafValueDiagNormalSims);

        // Extract END_TURN Q at 1k.
        double q1k = 0.0;
        std::int64_t visits1k = 0;
        double visitFrac1k = 0.0;
        int bestAction1k = -1;
        bool endTurnBest1k = false;
        {
            std::int64_t totalVisits = refSearcher.root.simulationCount;
            for (size_t i = 0; i < refSearcher.root.edges.size(); ++i) {
                const auto &e = refSearcher.root.edges[i];
                if (e.action.getActionType() == ActionType::END_TURN) {
                    visits1k = e.child.simulationCount;
                    q1k = visits1k > 0 ? e.child.evaluationSum / visits1k : 0.0;
                    visitFrac1k = totalVisits > 0 ? (double)visits1k / totalVisits : 0.0;
                    if (e.child.simulationCount > 0)
                        endTurnBest1k = true;
                }
                // Track best action at 1k.
                if ((int)e.child.simulationCount > bestAction1k)
                    bestAction1k = (int)i;
            }
            if (bestAction1k >= 0 && refSearcher.root.edges[bestAction1k].action.getActionType() == ActionType::END_TURN)
                endTurnBest1k = true;
        }

        // Continue to 4k.
        refSearcher.searchToTotal(g_s3LeafValueDiagDeepSims);

        // Extract END_TURN Q at 4k.
        double q4k = 0.0;
        std::int64_t visits4k = 0;
        double visitFrac4k = 0.0;
        int bestAction4k = -1;
        bool endTurnBest4k = false;
        double rootValue1k = refSearcher.root.simulationCount > 0
            ? refSearcher.root.evaluationSum / refSearcher.root.simulationCount : 0.0;
        // Note: rootValue includes ALL sims (1k+3k=4k); we want 4k root value.
        // The root eval after searchToTotal(4000) includes all 4000 sims.
        double rootValue4k = rootValue1k; // same thing — includes all 4k
        // Actually need to capture 1k snapshot. Let me recompute:
        // Can't easily get 1k-only root value from cumulative stats.
        // Use 4k root value as the deep root value; 1k root value not separately available.
        {
            std::int64_t totalVisits = refSearcher.root.simulationCount;
            for (size_t i = 0; i < refSearcher.root.edges.size(); ++i) {
                const auto &e = refSearcher.root.edges[i];
                if (e.action.getActionType() == ActionType::END_TURN) {
                    visits4k = e.child.simulationCount;
                    q4k = visits4k > 0 ? e.child.evaluationSum / visits4k : 0.0;
                    visitFrac4k = totalVisits > 0 ? (double)visits4k / totalVisits : 0.0;
                }
                if ((int)e.child.simulationCount > bestAction4k)
                    bestAction4k = (int)i;
            }
            if (bestAction4k >= 0 && refSearcher.root.edges[bestAction4k].action.getActionType() == ActionType::END_TURN)
                endTurnBest4k = true;
        }

        double residualQ = q4k - q1k;
        double absResidualQ = std::abs(residualQ);

        auto t1 = std::chrono::steady_clock::now();
        double elapsed = std::chrono::duration<double>(t1 - t0).count();

        // Write CSV row.
        static std::mutex lvOutMutex;
        static bool lvHeaderWritten = false;
        static std::ofstream lvOut;
        static bool lvOutOpen = false;
        {
            std::lock_guard<std::mutex> lk(lvOutMutex);
            if (!lvOutOpen && !g_s3LeafValueDiagFile.empty()) {
                lvOut.open(g_s3LeafValueDiagFile, std::ios::app);
                lvOutOpen = true;
            }
            std::ostream &out = lvOutOpen ? lvOut : std::cerr;
            if (!lvHeaderWritten) {
                out << "seed,floor,encounter,turn,decIdx,visibleHash,"
                    << "playerHp,playerBlock,energy,enemyHpTotal,incomingDamage,"
                    << "drawPileSize,cardsToDraw,handSize,"
                    << "lethalOuts,pLethal,pAnyAttack,pEnoughBlock,"
                    << "expAttacks,expBlock,"
                    << "q1k,visits1k,visitFrac1k,"
                    << "q4k,visits4k,visitFrac4k,"
                    << "residualQ,absResidualQ,"
                    << "endTurnBest1k,endTurnBest4k,"
                    << "rootValue4k,elapsedSec\n";
                lvHeaderWritten = true;
            }

            out << seed << ',' << floor << ',' << encounter << ','
                << turn << ',' << decIdx << ',' << vh << ','
                << preState.player.curHp << ',' << preState.player.block << ','
                << preState.player.energy << ','
                << enemyHpTotal << ',' << incomingDamage << ','
                << N << ',' << cardsToDraw << ',' << handBefore << ','
                << lethalOuts << ',' << pLethal << ',' << pAnyAttack << ',' << pEnoughBlock << ','
                << expAttacks << ',' << expBlock << ','
                << q1k << ',' << visits1k << ',' << visitFrac1k << ','
                << q4k << ',' << visits4k << ',' << visitFrac4k << ','
                << residualQ << ',' << absResidualQ << ','
                << (endTurnBest1k ? 1 : 0) << ',' << (endTurnBest4k ? 1 : 0) << ','
                << rootValue4k << ',' << elapsed << '\n';
            out.flush();
        }
    }
}

// ── Helper: maybe run bucket diagnostic before executing an action ──────
// Called at each action-execution site in step(). No-op when diag is off.
// Deduplicates by pre-state visibleHash so each unique (state, END_TURN)
// pair is measured at most once. Hard-capped at kMaxDiagRows per thread.
static void maybeOutcomeBucketDiag(
    const BattleContext &preState, const Action &action,
    std::uint64_t seed, int encounter, int floor, int turn, int decIdx)
{
    if (action.getActionType() != ActionType::END_TURN) return;

    // ── Outcome-bucket diag (compression measurement) ──────────────
    if (g_s3OutcomeBucketDiag && t_diagRowCount < kMaxDiagRows) {
        auto obs = CombatObservation::fromBattleContext(preState);
        std::uint64_t key = obs.visibleHash();
        if (t_diagSeen.insert(key).second) {
            if (!t_diagRngSeeded) {
                std::uint64_t h = key ^ seed;
                t_diagRng.seed(h ? h : 1);
                t_diagRngSeeded = true;
            }
            if (!t_diagOutOpen && !g_s3OutcomeBucketDiagFile.empty()) {
                t_diagOut.open(g_s3OutcomeBucketDiagFile, std::ios::app);
                t_diagOutOpen = true;
            }
            std::ostream &out = t_diagOutOpen ? t_diagOut : std::cerr;
            ++t_diagRowCount;
            runOutcomeBucketDiag(preState, action, g_s3OutcomeBucketDiagParticles,
                                 t_diagRng, seed, encounter, floor, turn, decIdx, out);
        }
    }

    // ── Bucket-value diag (value homogeneity measurement) ──────────
    if (g_s3BucketValueDiag)
        maybeBucketValueDiag(preState, action, seed, encounter, floor, turn, decIdx);
}

// ---- Card action key (semantic identity independent of hand position) ------
bool BattleScumSearcher3::CardActionKey::operator==(const CardActionKey &o) const {
    return id == o.id && upgradeCount == o.upgradeCount
        && costForTurn == o.costForTurn && freeToPlayOnce == o.freeToPlayOnce
        && specialData == o.specialData && target == o.target;
}
bool BattleScumSearcher3::CardActionKey::operator<(const CardActionKey &o) const {
    if (id != o.id) return id < o.id;
    if (upgradeCount != o.upgradeCount) return upgradeCount < o.upgradeCount;
    if (costForTurn != o.costForTurn) return costForTurn < o.costForTurn;
    if (freeToPlayOnce != o.freeToPlayOnce) return !freeToPlayOnce && o.freeToPlayOnce;
    if (specialData != o.specialData) return specialData < o.specialData;
    return target < o.target;
}
BattleScumSearcher3::CardActionKey
BattleScumSearcher3::cardActionKey(const BattleContext &bc, const Action &a) {
    CardActionKey k;
    if (a.getActionType() == ActionType::CARD) {
        int hi = a.getSourceIdx();
        if (hi >= 0 && hi < bc.cards.cardsInHand) {
            const auto &c = bc.cards.hand[hi];
            k.id = c.getId();
            k.upgradeCount = c.getUpgradeCount();
            k.costForTurn = c.costForTurn;
            k.freeToPlayOnce = c.freeToPlayOnce;
            k.specialData = c.specialData;
            k.target = a.getTargetIdx();
        }
    } else if (a.getActionType() == ActionType::SINGLE_CARD_SELECT) {
        int si = a.getSelectIdx();
        if (si >= 0 && si < (int)bc.cardSelectInfo.cards.size()
            && bc.cardSelectInfo.cards[si] != CardId::INVALID) {
            k.id = bc.cardSelectInfo.cards[si];
            k.target = -1;
        }
    }
    return k;
}

std::optional<Action> pickSearchAction(
    const BattleScumSearcher3::Node &node, const BattleContext &bc) {
    // This is the same policy used by the fair Searcher3 agent at the live
    // root: most visits, optionally restricted to actions valid in the
    // concrete state. Keep this visit-based choice; the diagnostic must not
    // substitute a convenient max-Q policy.
    if (g_s3Live) {
        std::int64_t bestVisits = -1;
        std::optional<Action> best;
        for (const auto &edge : node.edges) {
            if (edge.child.simulationCount > bestVisits
                && edge.action.isValidAction(bc)) {
                bestVisits = edge.child.simulationCount;
                best = edge.action;
            }
        }
        return best;
    }

    std::int64_t maxVisits = -1;
    std::optional<Action> best;
    for (const auto &edge : node.edges) {
        if (edge.child.simulationCount > maxVisits) {
            maxVisits = edge.child.simulationCount;
            best = edge.action;
        }
    }
    if (!best || !best->isValidAction(bc)) return std::nullopt;
    return best;
}

std::string semanticActionIdentity(const Action &action,
                                   const BattleContext &state) {
    std::ostringstream out;
    switch (action.getActionType()) {
        case ActionType::CARD: {
            const auto key = BattleScumSearcher3::cardActionKey(state, action);
            if (key.id != CardId::INVALID) {
                out << "CARD:" << static_cast<int>(key.id)
                    << ':' << static_cast<int>(key.upgradeCount)
                    << ':' << static_cast<int>(key.costForTurn)
                    << ':' << (key.freeToPlayOnce ? 1 : 0)
                    << ':' << key.specialData << ':' << key.target;
                return out.str();
            }
            break;
        }
        case ActionType::POTION: {
            const int index = action.getSourceIdx();
            if (index >= 0 && index < 5) {
                out << "POTION:" << static_cast<int>(state.potions[index])
                    << ':' << action.getTargetIdx();
                return out.str();
            }
            break;
        }
        case ActionType::SINGLE_CARD_SELECT: {
            const int index = action.getSelectIdx();
            if (index >= 0 && index < static_cast<int>(state.cardSelectInfo.cards.size())) {
                out << "SINGLE_CARD_SELECT:"
                    << static_cast<int>(state.cardSelectInfo.cardSelectTask)
                    << ':' << static_cast<int>(state.cardSelectInfo.cards[index]);
                return out.str();
            }
            break;
        }
        case ActionType::MULTI_CARD_SELECT: {
            std::vector<int> ids;
            for (const int index : action.getSelectedIdxs()) {
                if (index >= 0 && index < static_cast<int>(state.cardSelectInfo.cards.size()))
                    ids.push_back(static_cast<int>(state.cardSelectInfo.cards[index]));
                else
                    ids.push_back(-1);
            }
            std::sort(ids.begin(), ids.end());
            out << "MULTI_CARD_SELECT:"
                << static_cast<int>(state.cardSelectInfo.cardSelectTask);
            for (const int id : ids) out << ':' << id;
            return out.str();
        }
        case ActionType::END_TURN:
            return "END_TURN";
        default:
            break;
    }
    out << "RAW:" << action.bits;
    return out.str();
}

// ---- Per-node observation tracking -----------------------------------------
void BattleScumSearcher3::trackNodeObservation(Node &node, const BattleContext &state) {
    std::uint64_t curHash = CombatObservation::fromBattleContext(state).visibleHash();
    if (node.nodeObsVisits == 0) {
        node.firstObsHash = curHash;
    } else if (curHash != node.firstObsHash) {
        ++node.nodeObsMismatches;
    }
    node.lastObsHash = curHash;
    ++node.nodeObsVisits;
}

void BattleScumSearcher3::prepareCRNParticles() {
    crnParticles.resize(crnParticleCount);
    for (auto &p : crnParticles) {
        p.randomize(rng);
        p.drawPileOrder = rootObs.drawPileContents;
        std::shuffle(p.drawPileOrder.begin(), p.drawPileOrder.end(), rng);
    }
}

void BattleScumSearcher3::warmStartRootCRN(const BattleContext &bc) {
    if (root.edges.empty())
        enumerateActionsForNode(root, bc);

    if (crnParticles.empty())
        prepareCRNParticles();

    std::vector<double> scores(root.edges.size(), 0.0);
    std::vector<int> counts(root.edges.size(), 0);

    for (const auto &p : crnParticles) {
        BattleContext state = bc;
        applyParticle(state, p);
        for (size_t i = 0; i < root.edges.size(); ++i) {
            if (!root.edges[i].action.isValidAction(state)) continue;
            BattleContext sc = state;
            root.edges[i].action.execute(sc);
            std::vector<Action> dummy;
            playoutRandom(sc, dummy);
            scores[i] += evaluateLeaf(sc);
            ++counts[i];
        }
    }

    for (size_t i = 0; i < root.edges.size(); ++i) {
        if (counts[i] > 0) {
            root.edges[i].child.evaluationSum = scores[i] / counts[i];
            // Don't increment simulationCount — CRN provides a Q prior
            // without reducing exploration budget.
        }
    }
}

// ---- Search -----------------------------------------------------------------
void BattleScumSearcher3::search(int64_t simulations) {
    resetParticleUsage();
    if (g_s3Crn && !rootCarried && !crnWarmStarted) { warmStartRootCRN(*rootBc); crnWarmStarted = true; }
    if (reuseSearchCount >= 0) ++reuseSearchCount;  // searches executed since last promotion
    auto t0 = std::chrono::steady_clock::now();
    for (int64_t i = 0; i < simulations; ++i) {
        searchSimulationOrdinal = static_cast<int>(i + 1);
        step();
    }
    lastSearchSimulations = static_cast<int>(simulations);
    lastSearchCpuMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    diag.simSeconds += lastSearchCpuMs / 1000.0;
    finalizeStrategyFusionDiag();
}

void BattleScumSearcher3::searchToTotal(int64_t targetSimulations) {
    resetParticleUsage();
    if (isTerminal(*rootBc)) { outcomePlayerHp = rootBc->player.curHp; return; }
    if (g_s3Crn && !rootCarried && !crnWarmStarted) { warmStartRootCRN(*rootBc); crnWarmStarted = true; }
    if (reuseSearchCount >= 0) ++reuseSearchCount;  // searches executed since last promotion
    auto t0 = std::chrono::steady_clock::now();
    int ordinal = 0;
    while (root.simulationCount < targetSimulations) {
        searchSimulationOrdinal = ++ordinal;
        step();
    }
    lastSearchSimulations = static_cast<int>(root.simulationCount);
    lastSearchCpuMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    diag.simSeconds += lastSearchCpuMs / 1000.0;
    finalizeStrategyFusionDiag();
}

bool BattleScumSearcher3::advanceRoot(const Action &action,
                                       const BattleContext &newRootState) {
    bool reused = false;
    // SINGLE_CARD_SELECT stores a physical draw-pile index.  The hidden
    // draw-pile order may differ even when the visible root observation is
    // unchanged, so never carry a subtree into these roots.
    if (!isDrawPileIndexSensitiveCardSelect(newRootState)) {
        // Match by raw action bits first, then by semantic card key (if
        // available) to handle hand-index remapping across tree reuse.
        for (auto &edge : root.edges) {
            if (edge.action == action) {
                if (g_s3PersistentEndTurnChance
                    && edge.persistentChanceContainer) {
                    const auto liveObservation =
                        CombatObservation::fromBattleContext(newRootState);
                    for (auto &outcome : edge.outcomeChildren) {
                        if (outcome.observation == liveObservation) {
                            root = std::move(outcome.child);
                            reused = true;
                            break;
                        }
                    }
                } else {
                    root = std::move(edge.child);
                    reused = true;
                }
                break;
            }
        }
        if (!reused && g_s3SemanticCardEdges
            && action.getActionType() == ActionType::CARD) {
            CardActionKey committedKey = cardActionKey(*rootBc, action);
            if (committedKey.id != CardId::INVALID) {
                for (auto &edge : root.edges) {
                    if (edge.hasCardKey && edge.cardKey == committedKey) {
                        root = std::move(edge.child);
                        reused = true;
                        break;
                    }
                }
            }
        }
    }
    if (!reused) root = Node{};
    rootCarried = reused;

    // Count retained nodes in the carried subtree and optionally reset stats.
    if (reused) {
        retainedNodeCount = 0;
        std::function<void(Node&)> countNodes = [&](Node &nd) {
            ++retainedNodeCount;
            for (auto &e : nd.edges) {
                countNodes(e.child);
                for (auto &outcome : e.outcomeChildren)
                    countNodes(outcome.child);
            }
        };
        countNodes(root);

        if (g_reuseStatsMode == 1)   // recursive_reset
            recursiveResetStats(root);
    }

    // Reuse generation tracking.
    reuseGeneration = reuseGeneration + (reused ? 1 : 0);
    if (reused) {
        // Tree promoted: the STS_REUSE_ALWAYS_Q exploit condition
        // (reuseSearchCount >= 0) becomes active. Reset the per-promotion
        // search counter; search()/searchToTotal() count searches since it.
        reuseSearchCount = 0;
    }
    // Snapshot tree depth at promotion time (max edge count along any path).
    reuseGenerationDepth = 0;
    if (reused) {
        std::function<int(const Node&)> maxDepth = [&](const Node &nd) -> int {
            int d = 0;
            for (const auto &e : nd.edges) {
                if (e.persistentChanceContainer) {
                    for (const auto &outcome : e.outcomeChildren)
                        d = std::max(d, 1 + maxDepth(outcome.child));
                } else {
                    d = std::max(d, 1 + maxDepth(e.child));
                }
            }
            return d;
        };
        reuseGenerationDepth = maxDepth(root);
    }

    rootBc = std::make_unique<const BattleContext>(newRootState);
    rootObs = CombatObservation::fromBattleContext(newRootState);
    root.obs = rootObs;
    root.obsHash = rootObs.visibleHash();
    root.obsCached = true;

    bestActionSequence.clear();
    bestActionValue = std::numeric_limits<double>::min();
    firstQExploitSimulation = -1;
    outcomePlayerHp = 0;
    obsMismatchCount = 0;
    parentChildViolations = 0;
    leafCache.clear();
    edgeAvailability.clear();
    return reused;
}

// ---- Lethal / death detection ----------------------------------------------
// Conservative pruning variant: only prune when the player cannot act.
// Guards against pruning states (PLAYER_NORMAL, CARD_SELECT) where the player
// might still defend; the unguarded equivalent was removed as unsound.
bool BattleScumSearcher3::canPruneAsDead(const BattleContext &bc) {
    if (bc.inputState == InputState::PLAYER_NORMAL) return false;
    if (bc.inputState == InputState::CARD_SELECT) return false;
    if (bc.isCardPlayAllowed()) return false;
    int incDmg = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        if (bc.monsters.arr[i].curHp > 0 && bc.monsters.arr[i].isAttacking()) {
            auto di = bc.monsters.arr[i].getMoveBaseDamage(bc);
            incDmg += bc.monsters.arr[i].calculateDamageToPlayer(bc, di.damage) * di.attackCount;
        }
    }
    return incDmg > 0 && (bc.player.curHp + bc.player.block) < incDmg;
}

bool BattleScumSearcher3::isGuaranteedLethal(const BattleContext &bc) const {
    if (!bc.isCardPlayAllowed()) return false;
    int totalDmg = 0, totalHp = 0;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        const auto &c = bc.cards.hand[i];
        if (c.getType() != CardType::ATTACK || !c.canUseOnAnyTarget(bc)) continue;
        totalDmg += bc.calculateCardDamage(c, 0, 6); // rough estimate
    }
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0) totalHp += bc.monsters.arr[i].curHp;
    return totalDmg > 0 && totalDmg >= totalHp;
}

// V_combat leaf conditioning (STS_VNET_COND_BOSS / STS_VNET_COND_ACT3):
// restricts the learned leaf to the rollout-dominant contexts measured by
// §117 (boss fights, act 3) where the random rollout would otherwise carry
// most of the search mass. Both unset = always on (byte-identical to the
// pre-conditioning vnet behavior).
static bool vnetCondAllowed(const BattleContext &bc) {
    if (g_vnetCondBossOnly && !isBossEncounter(bc.encounter)) return false;
    if (g_vnetCondAct3 && bc.floorNum < 34) return false;
    return true;
}

// ---- Alpha by rollout length (A2, STS_VNET_ALPHA_LEN) ---------------------
static double alphaForRolloutSteps(int steps) {
    for (const auto &p : g_vnetAlphaLenTable)
        if (steps <= p.first) return p.second;
    return g_vnetAlphaLenTable.back().second;
}

bool s3PersistentChanceFlagsCompatible(bool persistentChance,
                                       bool strategyFusionDiag,
                                       bool eagerMarginalization) {
    return !(persistentChance
             && (strategyFusionDiag || eagerMarginalization));
}

void printPersistentEndTurnChanceDiagnostics() {
    const auto visits = g_pcContainerVisits.load();
    const auto hits = g_pcOutcomeExistingHits.load();
    std::cerr << "S3_PERSISTENT_ENDTURN_CHANCE_DIAG {"
              << "\"eligible_endturn_count\":" << g_pcEligible.load() << ','
              << "\"ineligible_endturn_count\":" << g_pcIneligible.load() << ','
              << "\"chance_containers_created\":" << g_pcContainersCreated.load() << ','
              << "\"chance_container_visits\":" << visits << ','
              << "\"outcome_children_created\":" << g_pcOutcomeChildrenCreated.load() << ','
              << "\"outcome_existing_hits\":" << hits << ','
              << "\"outcome_new_misses\":" << g_pcOutcomeNewMisses.load() << ','
              << "\"outcome_reuse_rate\":"
              << (visits > 0 ? static_cast<double>(hits) / visits : 0.0) << ','
              << "\"max_outcomes_per_container\":"
              << g_pcMaxOutcomesPerContainer.load() << ','
              << "\"containers_with_pre_observation_hash_mismatch\":"
              << g_pcContainersWithPreObservationMismatch.load() << ','
              << "\"max_outcomes_after_pre_observation_hash_mismatch\":"
              << g_pcMaxOutcomesAfterPreObservationMismatch.load() << ','
              << "\"max_outcome_container_pre_observation_visits\":"
              << g_pcMaxContainerPreObservationVisits.load() << ','
              << "\"max_outcome_container_pre_observation_hash_mismatches\":"
              << g_pcMaxContainerPreObservationMismatches.load() << ','
              << "\"distinct_outcomes_per_container\":[";
    for (std::size_t i = 1; i < g_pcOutcomeCountHistogram.size(); ++i) {
        if (i > 1) std::cerr << ',';
        std::cerr << g_pcOutcomeCountHistogram[i].load();
    }
    std::cerr << "]}" << std::endl;
}

bool BattleScumSearcher3::persistentEndTurnEligible(
    const BattleContext &preState, const Action &action) {
    if (action.getActionType() != ActionType::END_TURN
        || preState.outcome != Outcome::UNDECIDED)
        return false;
    const int drawSize = static_cast<int>(preState.cards.drawPile.size());
    const int discardSize = static_cast<int>(preState.cards.discardPile.size());
    const bool immediateReshuffle = drawSize == 0 && discardSize > 0;
    return drawSize <= g_s3PersistentEndTurnMaxPile && !immediateReshuffle;
}

BattleScumSearcher3::Node &BattleScumSearcher3::dispatchPersistentEndTurnOutcome(
    Edge &edge, std::uint64_t preObservationHash,
    const CombatObservation &postObservation) {
    ++chanceContainerVisits;
    ++g_pcContainerVisits;
    if (!edge.persistentChanceContainer) {
        edge.persistentChanceContainer = true;
        ++chanceContainersCreated;
        ++g_pcContainersCreated;
    }
    ++edge.persistentPreObservationVisits;
    if (!edge.persistentPreObservationCached) {
        edge.persistentPreObservationCached = true;
        edge.persistentFirstPreObservationHash = preObservationHash;
    } else if (edge.persistentFirstPreObservationHash != preObservationHash) {
        ++edge.persistentPreObservationMismatches;
        if (edge.persistentPreObservationMismatches == 1) {
            ++g_pcContainersWithPreObservationMismatch;
            auto mixedMax = g_pcMaxOutcomesAfterPreObservationMismatch.load();
            while (mixedMax < static_cast<std::int64_t>(edge.outcomeChildren.size())
                   && !g_pcMaxOutcomesAfterPreObservationMismatch.compare_exchange_weak(
                       mixedMax,
                       static_cast<std::int64_t>(edge.outcomeChildren.size()))) {}
            std::lock_guard<std::mutex> lock(g_pcMaxContainerMutex);
            if (static_cast<std::int64_t>(edge.outcomeChildren.size())
                == g_pcMaxOutcomesPerContainer.load()) {
                g_pcMaxContainerPreObservationVisits.store(
                    edge.persistentPreObservationVisits);
                g_pcMaxContainerPreObservationMismatches.store(
                    edge.persistentPreObservationMismatches);
            }
        }
    }
    for (auto &outcome : edge.outcomeChildren) {
        if (outcome.observation == postObservation) {
            ++outcomeExistingHits;
            ++g_pcOutcomeExistingHits;
            return outcome.child;
        }
    }

    const std::size_t oldSize = edge.outcomeChildren.size();
    Edge::OutcomeChild outcome;
    outcome.observation = postObservation;
    outcome.child.obs = postObservation;
    outcome.child.obsHash = postObservation.visibleHash();
    outcome.child.obsCached = true;
    edge.outcomeChildren.push_back(std::move(outcome));
    ++outcomeChildrenCreated;
    ++outcomeNewMisses;
    ++g_pcOutcomeChildrenCreated;
    ++g_pcOutcomeNewMisses;

    const std::size_t newSize = edge.outcomeChildren.size();
    const std::size_t oldBin = std::min<std::size_t>(oldSize, 8);
    const std::size_t newBin = std::min<std::size_t>(newSize, 8);
    if (oldBin > 0) --g_pcOutcomeCountHistogram[oldBin];
    ++g_pcOutcomeCountHistogram[newBin];
    maxOutcomesPerContainer = std::max<std::int64_t>(
        maxOutcomesPerContainer, static_cast<std::int64_t>(newSize));
    if (edge.persistentPreObservationMismatches > 0) {
        auto mixedMax = g_pcMaxOutcomesAfterPreObservationMismatch.load();
        while (mixedMax < static_cast<std::int64_t>(newSize)
               && !g_pcMaxOutcomesAfterPreObservationMismatch.compare_exchange_weak(
                   mixedMax, static_cast<std::int64_t>(newSize))) {}
    }
    {
        std::lock_guard<std::mutex> lock(g_pcMaxContainerMutex);
        if (static_cast<std::int64_t>(newSize)
            > g_pcMaxOutcomesPerContainer.load()) {
            g_pcMaxOutcomesPerContainer.store(static_cast<std::int64_t>(newSize));
            g_pcMaxContainerPreObservationVisits.store(
                edge.persistentPreObservationVisits);
            g_pcMaxContainerPreObservationMismatches.store(
                edge.persistentPreObservationMismatches);
        }
    }
    return edge.outcomeChildren.back().child;
}

// ---- ISMCTS step ------------------------------------------------------------
void BattleScumSearcher3::step() {
    ++diag.simulations;
    const size_t particleIndex = belief.sampleIndex(rng);
    if (particleIndex < particleSampleCounts.size()) ++particleSampleCounts[particleIndex];
    const auto &particle = belief.particles[particleIndex];

    BattleContext state = *rootBc;
    diagnosticParticleIndex = particleIndex;
    diagnosticParticleWeight = particle.weight;
    diagnosticParticleAppliedExactly = false;
    diagnosticParticleUsedFallback = false;
    diagnosticActionCheckpoints.clear();
    diagnosticTraceActive = g_s3LeafTraceActions && g_onS3LeafQuery;
    applyParticle(state, particle);
    if (rngExposureEnabled) {
        rngExposureAiBaseline = state.aiRng.counter;
        rngExposureCardBaseline = state.cardRandomRng.counter;
        rngExposureAiSeen = rngExposureCardSeen = false;
        rngExposureAiFirst = rngExposureCardFirst = -1;
        rngExposureAiTotalDelta = rngExposureCardTotalDelta = 0;
        rngExposureCurrentRootActionBits = 0xFFFFFFFFu;
        rngExposureActionIndex = 0;
    }

    std::vector<Node *> path;
    std::vector<Action> actionStack;
    Node *cur = &root;
    int depth = 0;

    while (++depth < maxSearchDepth) {
        path.push_back(cur);
        ensureObservation(*cur, state);
        // Per-node observation-stability tracking.
        // Only immediate root children (depth==2) can be promoted via
        // advanceRoot, so only they need obs-stability for the reuse
        // eligibility check. The strategy-fusion diagnostic tracks all
        // depths so an END_TURN parent can be gated independently of reuse.
        if (g_s3UnionExpand || g_reuseCarryDiag || (g_reuseObsStable && depth == 2)
            || g_s3StrategyFusionDiag)
            trackNodeObservation(*cur, state);
        diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(depth));

        if (isTerminal(state)) {
            ++diag.terminalInsideTree;
            backpropagate(path, evaluateTerminal(state), actionStack);
            finishRngExposureSimulation();
            return;
        }

        if (g_s3Prune && canPruneAsDead(state)) {
            ++diag.leafDirectEval;
            backpropagate(path, 0.0, actionStack);
            finishRngExposureSimulation();
            return;
        }

        if (!cur->isExpanded()) {
            enumerateActionsForNode(*cur, state);
            // Priors with either the GBM policy net or the PVNet policy head;
            // computeEdgePriors prefers the PVNet policy head when both exist.
            if ((g_usePolicyNet && g_policyNet.loaded())
                || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly))
                computeEdgePriors(*cur, state);

            if (cur->edges.empty()) {
                ++diag.leafDirectEval;
                backpropagate(path, evaluateLeaf(state, cur->obsHash), actionStack);
                finishRngExposureSimulation();
                return;
            }

            int selIdx = std::uniform_int_distribution<int>(
                0, (int)cur->edges.size() - 1)(rng);
            auto &edge = cur->edges[selIdx];

            if (!edge.action.isValidAction(state)) {
                ++diag.leafDirectEval;
                backpropagate(path, evaluateLeaf(state, cur->obsHash), actionStack);
                finishRngExposureSimulation();
                return;
            }

            // Save pre-state for possible END_TURN marginalization. The copy
            // is a full BattleContext per expansion, so only take it when the
            // opt-in feature (STS_S3_END_TURN_MARGINALIZE) can consume it.
            std::optional<BattleContext> preExecState;
            if (g_s3EndTurnMarginalize) preExecState = state;
            const bool persistentEndTurn = g_s3PersistentEndTurnChance
                && persistentEndTurnEligible(state, edge.action);
            const auto persistentPreObservationHash = persistentEndTurn
                ? CombatObservation::fromBattleContext(state).visibleHash() : 0;
            if (g_s3PersistentEndTurnChance
                && edge.action.getActionType() == ActionType::END_TURN) {
                if (persistentEndTurn) {
                    ++eligibleEndTurnCount;
                    ++g_pcEligible;
                } else {
                    ++ineligibleEndTurnCount;
                    ++g_pcIneligible;
                }
            }
            maybeOutcomeBucketDiag(state, edge.action,
                agentSeed, (int)rootBc->encounter, rootBc->floorNum,
                state.turn, decisionIndex);
            maybeDrawProbDiag(state,
                agentSeed, (int)rootBc->encounter, rootBc->floorNum,
                state.turn, decisionIndex,
                edge.child.simulationCount,
                edge.child.simulationCount > 0
                    ? edge.child.evaluationSum / edge.child.simulationCount : 0.0,
                edge.prior);
            observeRngExposureAction(edge.action, state);
            ++diag.treeActions;
            actionStack.push_back(edge.action);
            path.push_back(&edge.child);
            if (persistentEndTurn) {
                const auto postObservation =
                    CombatObservation::fromBattleContext(state);
                path.push_back(&dispatchPersistentEndTurnOutcome(
                    edge, persistentPreObservationHash, postObservation));
            }
            if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(CombatObservation::fromBattleContext(state));

            // ── END_TURN marginalization (leaf-expansion boundary only) ──
            if (preExecState
                && edge.action.getActionType() == ActionType::END_TURN
                && state.outcome == Outcome::UNDECIDED) {
                double margEval = endTurnMarginalEval(*preExecState, actionStack);
                if (!std::isnan(margEval)) {
                    // Skip chain compression + rollout + blend.
                    // backpropagate the marginal expectation with 1 visit.
                    backpropagate(path, margEval, actionStack);
                    finishRngExposureSimulation();
                    return;
                }
                // NaN = not eligible (large pile / reshuffle); fall through.
            }

        if (g_s3Prune && canPruneAsDead(state)) {
                backpropagate(path, 0.0, actionStack);
                finishRngExposureSimulation();
                return;
            }

            // Deterministic chain compression (2.2): play additional non-drawing
            // cards before rollout, as long as state stays in PLAYER_NORMAL.
            int compSteps = 0;
            if (g_s3Chain) {
                while (compSteps < 10 && state.inputState == InputState::PLAYER_NORMAL
                       && state.outcome == Outcome::UNDECIDED && state.isCardPlayAllowed()) {
                int handBefore = state.cards.cardsInHand;
                bool played = false;
                for (int hi = 0; hi < state.cards.cardsInHand && !played; ++hi) {
                    const auto &c = state.cards.hand[hi];
                    if (!c.canUseOnAnyTarget(state) || c.requiresTarget()) continue;
                    Action a(ActionType::CARD, hi);
                    if (!a.isValidAction(state)) continue;
                    observeRngExposureAction(a, state);
                    actionStack.push_back(a);
                    // If hand didn't decrease by exactly 1, something unexpected happened (draw, exhaust, etc.) — stop
                    if (state.cards.cardsInHand != handBefore - 1) { break; }
                    played = true;
                    ++compSteps;
                }
                if (!played) break;
                }
            }

            // Blend: capture leaf value, then rollout, then blend. Phase 6:
            // STS_PVNET_COND_* gates the PVNet leaf here — cheap/easy
            // continuations (early turn, shallow tree, non-boss rooms) use the
            // ordinary rollout only; the NN fires for the long/unresolved
            // continuations where the rollout would otherwise dominate.
            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                && state.outcome == Outcome::UNDECIDED && vnetCondAllowed(state)) {
                g_vnetTraceParent = cur->obsHash;
                g_vnetTraceDepth = depth;
                vLeaf = g_combatVNet.predict(state);
                // Experimental STS_VNET_RANK_CORR: add the zero-mean ranking
                // correction on top of the primary prediction here too — this
                // blend site is where the leaf value actually enters the MCTS
                // (the diagnostic leaf prediction is exactly this value), so
                // without it the correction could never improve within-group
                // ordering. Accumulated into rankCorrValues for the
                // search-complete zero-mean clamp (fair path).
                if (g_useVNetResidual && g_combatVNetResidual.loaded()) { const double res = g_combatVNetResidual.predict(state); vLeaf += g_vnetResidualBeta * res; } if (g_useVNetRankCorr && g_combatVNetRankCorr.loaded()) {
                    const double corr = g_combatVNetRankCorr.predict(state);
                    vLeaf += corr;
                    rankCorrValues.push_back(corr);
                }
            }
            else if (g_usePVNet && g_combatPVNet.loaded()
                     && state.outcome == Outcome::UNDECIDED
                     && pvnetCondAllowed(state, depth)) {
                vLeaf = g_combatPVNet.leafValue(state, riskLambda);
                if (g_useVNetResidual && g_combatVNetResidual.loaded()) { const double res = g_combatVNetResidual.predict(state); vLeaf += g_vnetResidualBeta * res; } if (g_useVNetRankCorr && g_combatVNetRankCorr.loaded()) {
                    const double corr = g_combatVNetRankCorr.predict(state);
                    vLeaf += corr;
                    rankCorrValues.push_back(corr);
                }
            }

            // The posterior prefix ends at the pre-rollout frontier. Rollout
            // actions are intentionally excluded from the semantic trace.
            diagnosticTraceActive = false;
            // The posterior prefix ends at the pre-rollout frontier. Rollout
            // actions are intentionally excluded from the semantic trace.
            diagnosticTraceActive = false;
            double eval = 0.0;
            const int rollSteps = multiRollout(state, actionStack, eval);
            const double rawEval = eval;   // pre-blend rollout outcome
            ++diag.rolloutCalls;
            ++diag.rolloutLeafCalls;
            diag.rolloutActions += rollSteps;
            if (g_usePVNet && g_combatPVNet.loaded() && !std::isnan(vLeaf)) {
                double alpha = g_vnetAlphaLen ? alphaForRolloutSteps(rollSteps) : g_pvnetAlpha;
                eval = alpha * vLeaf + (1.0 - alpha) * eval;
            }
            else if (!std::isnan(vLeaf)) {
                double alpha = g_vnetAlphaLen ? alphaForRolloutSteps(rollSteps) : g_vnetAlpha;
                eval = alpha * vLeaf + (1.0 - alpha) * eval;
            }
            // Leafdiag hook (nullptr by default; the leaf obsHash is computed
            // only when the hook is registered, so unset behavior is
            // unchanged). The leaf identity hash is the state's visibleHash —
            // computed fresh, NOT the parent node's cached obsHash (cur is the
            // expanded parent at this point, its observation predates the
            // committed action + chain compression).
            if (g_onS3LeafQuery) {
                const std::uint64_t leafObsHash =
                    CombatObservation::fromBattleContext(state).visibleHash();
                S3LeafDiagnostic diagnostic;
                diagnostic.searcher = this;
                diagnostic.bc = &state;
                diagnostic.treeDepth = depth;
                diagnostic.obsHash = leafObsHash;
                diagnostic.vnetPred = vLeaf;
                diagnostic.rawRolloutEval = rawEval;
                diagnostic.blendedEval = eval;
                diagnostic.rolloutSteps = rollSteps;
                diagnostic.frontierType = 0;
                diagnostic.particleIndex = diagnosticParticleIndex;
                diagnostic.particleWeight = diagnosticParticleWeight;
                diagnostic.particleAppliedExactly = diagnosticParticleAppliedExactly;
                diagnostic.particleUsedFallback = diagnosticParticleUsedFallback;
                diagnostic.rootCarried = rootCarried;
                diagnostic.reuseGeneration = reuseGeneration;
                diagnostic.reuseSearchCount = reuseSearchCount;
                diagnostic.searchSimulationOrdinal = searchSimulationOrdinal;
                diagnostic.outcome = state.outcome;
                diagnostic.actionCheckpoints = diagnosticActionCheckpoints;
                g_onS3LeafQuery(diagnostic);
            }
            // Deep-target capture
            if (const char *dtPath = std::getenv("STS_DEEP_TARGET_FILE")) {
                static std::mutex dtMutex;
                static std::ofstream dtFile;
                static double dtSample = []{
                    const char *s = std::getenv("STS_DEEP_TARGET_SAMPLE");
                    return s ? std::atof(s) : 0.005;
                }();
                static int dtSims = []{
                    const char *s = std::getenv("STS_DEEP_TARGET_SIMS");
                    return s ? std::atoi(s) : 4000;
                }();
                static int dtSeq = 0;
                static bool dtInit = false;
                if (!dtInit) {
                    std::lock_guard<std::mutex> lk(dtMutex);
                    if (!dtInit) {
                        dtFile.open(dtPath, std::ios::out);
                        if (dtFile.is_open()) {
                            dtFile << "seq,depth";
                            const auto &names = combatFeatureNames();
                            for (const auto &n : names) dtFile << ',' << n;
                            dtFile << ",xgbValue,deepEndHP,deepUtility,deepSims,encounter,hp,turn\n";
                        }
                        dtInit = true;
                    }
                }
                if (dtFile.is_open()) {
                    thread_local std::mt19937_64 dtRng(std::random_device{}());
                    if (dtSample >= 1.0 ||
                        std::uniform_real_distribution<double>(0.0,1.0)(dtRng) < dtSample) {
                        BattleContext bcCopy = state;
                        if (bcCopy.outcome == Outcome::UNDECIDED) {
                            double savedAlpha = g_vnetAlpha;
                            bool savedAlphaLen = g_vnetAlphaLen;
                            g_vnetAlpha = 1.0;
                            g_vnetAlphaLen = false;
                            BattleScumSearcher3 deepSearch(bcCopy, bcCopy.seed, 0,
                                                           g_s3Particles);
                            deepSearch.search(dtSims);
                            double deepEndHP = deepSearch.root.simulationCount > 0
                                ? deepSearch.root.evaluationSum
                                  / (double)deepSearch.root.simulationCount : 0.0;
                            g_vnetAlpha = savedAlpha;
                            g_vnetAlphaLen = savedAlphaLen;
                            BattleScumSearcher3 deepSearchU(bcCopy, bcCopy.seed, 0,
                                                            g_s3Particles);
                            deepSearchU.search(dtSims);
                            double deepUtility = deepSearchU.root.simulationCount > 0
                                ? deepSearchU.root.evaluationSum
                                  / (double)deepSearchU.root.simulationCount : 0.0;
                            double xv = !std::isnan(vLeaf) ? vLeaf : rawEval;
                            int nf = combatFeatureCount();
                            std::vector<float> feats(nf);
                            combatExtractFeatures(state, feats.data());
                            std::ostringstream o;
                            int seq = dtSeq++;
                            o << seq << ',' << depth;
                            for (int fi = 0; fi < nf; ++fi) o << ',' << feats[fi];
                            o << ',' << xv << ',' << deepEndHP << ',' << deepUtility
                              << ',' << dtSims << ',' << (int)state.encounter
                              << ',' << state.player.curHp << ',' << state.turn << '\n';
                            std::lock_guard<std::mutex> lk(dtMutex);
                            if (dtFile.is_open()) dtFile << o.str() << std::flush;
                        }
                    }
                }
            }
            // Terminal-endHP target capture (STS_ENDHP_TARGET_FILE=<path>,
            // STS_ENDHP_TARGET_SAMPLE=<prob>, STS_ENDHP_TARGET_K=<k>):
            // samples leaf states, clones BattleContext, plays to terminal via
            // playoutBattleFair, records final HP (0=loss, curHp=win).
            if (const char *ehPath = std::getenv("STS_ENDHP_TARGET_FILE")) {
                static std::mutex ehMutex;
                static std::ofstream ehFile;
                static double ehSample = []{
                    const char *s = std::getenv("STS_ENDHP_TARGET_SAMPLE");
                    return s ? std::atof(s) : 0.01;
                }();
                static int ehK = []{
                    const char *s = std::getenv("STS_ENDHP_TARGET_K");
                    return s ? std::atoi(s) : 1;
                }();
                static int ehSims = []{
                    const char *s = std::getenv("STS_ENDHP_TARGET_SIMS");
                    return s ? std::atoi(s) : 2000;
                }();
                static bool ehInit = false;
                if (!ehInit) {
                    std::lock_guard<std::mutex> lk(ehMutex);
                    if (!ehInit) {
                        ehFile.open(ehPath, std::ios::out);
                        if (ehFile.is_open())
                            ehFile << "seed,depth,encounter,hp,turn,teacherPred,endHP,K\n";
                        ehInit = true;
                    }
                }
                if (ehFile.is_open()) {
                    thread_local std::mt19937_64 ehRng(std::random_device{}());
                    if (ehSample >= 1.0 ||
                        std::uniform_real_distribution<double>(0.0,1.0)(ehRng) < ehSample) {
                        int k = std::max(1, ehK);
                        double sumEndHP = 0.0; int wins = 0;
                        for (int ki = 0; ki < k; ++ki) {
                            BattleContext bcCopy = state;
                            if (bcCopy.outcome == Outcome::UNDECIDED) {
                                // Drive combat to terminal using Searcher3 at each decision
                                int stall = 0;
                                while (bcCopy.outcome == Outcome::UNDECIDED && stall < 200) {
                                    ++stall;
                                    BattleScumSearcher3 s3(bcCopy, bcCopy.seed, 0, g_s3Particles);
                                    s3.search(ehSims);
                                    if (s3.root.edges.empty()) break;
                                    // Pick most-visited edge
                                    int best = 0;
                                    std::int64_t bestVisits = s3.root.edges[0].child.simulationCount;
                                    for (int e = 1; e < (int)s3.root.edges.size(); ++e) {
                                        if (s3.root.edges[e].child.simulationCount > bestVisits) {
                                            bestVisits = s3.root.edges[e].child.simulationCount;
                                            best = e;
                                        }
                                    }
                                    if (!s3.root.edges[best].action.isValidAction(bcCopy)) break;
                                    s3.root.edges[best].action.execute(bcCopy);
                                }
                                if (bcCopy.outcome == Outcome::PLAYER_VICTORY)
                                    sumEndHP += bcCopy.player.curHp;
                            }
                        }
                        double avgEndHP = k > 0 ? sumEndHP / (double)k : 0.0;
                        double xv = !std::isnan(vLeaf) ? vLeaf : rawEval;
                        std::ostringstream o;
                        o << state.seed << ',' << depth << ',' << (int)state.encounter
                          << ',' << state.player.curHp << ',' << state.turn
                          << ',' << xv << ',' << avgEndHP << ',' << k << '\n';
                        std::lock_guard<std::mutex> lk(ehMutex);
                        if (ehFile.is_open()) ehFile << o.str() << std::flush;
                    }
                }
            }
            backpropagate(path, eval, actionStack);
            finishRngExposureSimulation();
            return;
        }

        // Internal node
        // ── STS_S3_UNION_EXPAND: add legal actions missing from this node ──
        if (g_s3UnionExpand && cur->isExpanded()) {
            Node live;
            enumerateActionsForNode(live, state);
            if (!live.edges.empty()) {
                // Build set of semantic keys already present.
                std::set<CardActionKey> present;
                std::set<std::uint32_t> presentBits;
                for (const auto &e : cur->edges) {
                    if (e.action.getActionType() == ActionType::CARD
                        || e.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
                        if (g_s3SemanticCardEdges && e.hasCardKey)
                            present.insert(e.cardKey);
                        else
                            present.insert(cardActionKey(state, e.action));
                    }
                    else
                        presentBits.insert(e.action.bits);
                }
                for (auto &le : live.edges) {
                    bool dup = false;
                    if (le.action.getActionType() == ActionType::CARD
                        || le.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
                        auto key = cardActionKey(state, le.action);
                        if (key.id != CardId::INVALID && present.count(key)) dup = true;
                    } else {
                        if (presentBits.count(le.action.bits)) dup = true;
                    }
                    if (!dup) {
                        le.prior = 0.f;
                        cur->edges.push_back(Edge{le.action, Node{}, 0.f, 0});
                    }
                }
            }
        }

        int selIdx = selectBestEdgePUCT(*cur);
        auto &edge = cur->edges[selIdx];

        // ── Per-edge availability tracking ────────────────────────────
        if (g_s3UnionExpand)
            ++edge.availabilityCount;

        // ── Semantic CARD edge resolution ─────────────────────────────
        // Resolve the edge's semantic identity to a live-hand index before
        // the validity check; the edge's statistics (Q, visits) stay attached
        // to "play Bash on target 0", not to hand slot 1.
        Action effectiveAction = edge.action;
        bool edgeAvailable = true;
        if (g_s3SemanticCardEdges && edge.hasCardKey) {
            ++semanticCardEdgeVisits;
            // Diagnostic: does the raw index still point to the same card?
            if (edge.action.getSourceIdx() >= 0
                && edge.action.getSourceIdx() < state.cards.cardsInHand) {
                const auto &rawCard = state.cards.hand[edge.action.getSourceIdx()];
                if (rawCard.getId() != edge.cardKey.id
                    || rawCard.getUpgradeCount() != edge.cardKey.upgradeCount
                    || rawCard.costForTurn != edge.cardKey.costForTurn
                    || rawCard.freeToPlayOnce != edge.cardKey.freeToPlayOnce
                    || rawCard.specialData != edge.cardKey.specialData)
                    ++rawIndexSemanticMismatches;
            }
            auto resolved = resolveSemanticCardEdge(edge, state);
            if (resolved) {
                if (resolved->getSourceIdx() != edge.action.getSourceIdx())
                    ++semanticRebinds;
                effectiveAction = *resolved;
            } else {
                ++semanticResolutionFailures;
                edgeAvailable = false;
            }
        }

        if (!edgeAvailable || !effectiveAction.isValidAction(state)) {
            // Stored edges were enumerated in other determinizations; the chosen
            // action may be illegal in this world. STS_LIVE_VALID (Phase 4):
            // re-select among stored edges valid in THIS particle world (same
            // PUCT scoring) and continue descent; only when none are valid do we
            // fall back to a random rollout (the recorded §117 behavior).
            if (g_liveValid) {
                const int validIdx = selectBestValidEdgePUCT(*cur, state);
                if (validIdx >= 0) {
                    auto &validEdge = cur->edges[validIdx];
                    if (g_s3UnionExpand) ++validEdge.availabilityCount;
                    // Semantic CARD edge: resolve to live-hand index before execution.
                    Action execAction = validEdge.action;
                    if (g_s3SemanticCardEdges && validEdge.hasCardKey) {
                        auto resolved = resolveSemanticCardEdge(validEdge, state);
                        if (resolved) execAction = *resolved;
                    }
                    if (g_s3StrategyFusionDiag && !t_strategyFusionSuppressed
                        && cur->isObsStable()
                        && execAction.getActionType() == ActionType::END_TURN
                        && validEdge.child.simulationCount >= g_s3StrategyFusionDiagMinChildVisits)
                        recordStrategyFusionCandidate(
                            *cur, state, validEdge, path, rootBc->seed,
                            (int)rootBc->encounter, rootBc->floorNum,
                            state.turn, searchSimulationOrdinal);
                    maybeOutcomeBucketDiag(state, execAction,
                        agentSeed, (int)rootBc->encounter, rootBc->floorNum,
                        state.turn, decisionIndex);
                    const bool persistentEndTurn = g_s3PersistentEndTurnChance
                        && persistentEndTurnEligible(state, execAction);
                    const auto persistentPreObservationHash = persistentEndTurn
                        ? CombatObservation::fromBattleContext(state).visibleHash() : 0;
                    if (g_s3PersistentEndTurnChance
                        && execAction.getActionType() == ActionType::END_TURN) {
                        if (persistentEndTurn) {
                            ++eligibleEndTurnCount;
                            ++g_pcEligible;
                        } else {
                            ++ineligibleEndTurnCount;
                            ++g_pcIneligible;
                        }
                    }
                    observeRngExposureAction(execAction, state);
                    ++diag.treeActions;
                    actionStack.push_back(execAction);
                    cur = &validEdge.child;
                    if (persistentEndTurn) {
                        path.push_back(cur);
                        cur = &dispatchPersistentEndTurnOutcome(
                            validEdge, persistentPreObservationHash,
                            CombatObservation::fromBattleContext(state));
                    }
                    if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(CombatObservation::fromBattleContext(state));
                    continue;
                }
                // STS_S3_EXPAND (Phase 6): no stored edge is valid in this
                // particle world. Instead of a random rollout, enumerate the
                // live state's legal actions, add the ones not already stored
                // as new tree edges (priors computed on the new edges only —
                // stored edges may be invalid here, so their action features
                // cannot be filled safely), and descend into the PUCT-best
                // live-valid edge. Action-keyed tree: unchanged from §114's
                // falsified obs-keyed descent. Requires live-valid semantics
                // (g_liveValid); without it this branch is unreachable.
                // STS_S3_EXPAND_SIMPLE: same edge expansion but picks the
                // live-valid edge with the highest rolloutWeight instead of
                // computing PUCT priors and running selectBestValidEdgePUCT.
                // Hypothesis: the §125 penalty comes from PUCT over-committing
                // to the (stale) prior on zero-evidence edges; a deterministic
                // heuristic pick avoids both the GBM inference cost and the
                // prior-distribution risk.
                if (g_s3ExpandSimple) {
                    Node live;
                    enumerateActionsForNode(live, state);
                    if (!live.edges.empty()) {
                        std::vector<Action> newActs;
                        newActs.reserve(live.edges.size());
                        for (const auto &le : live.edges) {
                            bool dup = false;
                            for (const auto &se : cur->edges) {
                                if (se.action == le.action) { dup = true; break; }
                            }
                            if (!dup) newActs.push_back(le.action);
                        }
                        if ((int)newActs.size() > g_s3ExpandMaxNew) {
                            std::shuffle(newActs.begin(), newActs.end(), rng);
                            newActs.resize(g_s3ExpandMaxNew);
                        }
                        if (!newActs.empty()) {
                            // Add to tree with uniform prior so PUCT explores
                            // them on equal footing. No GBM inference needed.
                            double uniPrior = 1.0 / newActs.size();
                            for (const auto &a : newActs)
                                cur->edges.push_back(Edge{a, Node{}, uniPrior});
                            // Pick the first live-valid edge to descend into
                            // (deterministic; PUCT will sort out visit counts later)
                            int bestIdx = -1;
                            for (int i = 0; i < (int)cur->edges.size(); ++i) {
                                if (cur->edges[i].action.isValidAction(state)) {
                                    bestIdx = i; break;
                                }
                            }
                            if (bestIdx >= 0) {
                                auto &newEdge = cur->edges[bestIdx];
                                maybeOutcomeBucketDiag(state, newEdge.action,
                                    agentSeed, (int)rootBc->encounter, rootBc->floorNum,
                                    state.turn, decisionIndex);
                                const bool persistentEndTurn = g_s3PersistentEndTurnChance
                                    && persistentEndTurnEligible(state, newEdge.action);
                                const auto persistentPreObservationHash = persistentEndTurn
                                    ? CombatObservation::fromBattleContext(state).visibleHash() : 0;
                                if (g_s3PersistentEndTurnChance
                                    && newEdge.action.getActionType() == ActionType::END_TURN) {
                                    if (persistentEndTurn) {
                                        ++eligibleEndTurnCount;
                                        ++g_pcEligible;
                                    } else {
                                        ++ineligibleEndTurnCount;
                                        ++g_pcIneligible;
                                    }
                                }
                                observeRngExposureAction(newEdge.action, state);
                                ++diag.treeActions;
                                actionStack.push_back(newEdge.action);
                                cur = &newEdge.child;
                                if (persistentEndTurn) {
                                    path.push_back(cur);
                                    cur = &dispatchPersistentEndTurnOutcome(
                                        newEdge, persistentPreObservationHash,
                                        CombatObservation::fromBattleContext(state));
                                }
                                if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(CombatObservation::fromBattleContext(state));
                                continue;
                            }
                        }
                    }
                }
                if (g_s3Expand) {
                    Node live;
                    enumerateActionsForNode(live, state);
                    if (!live.edges.empty()) {
                        std::vector<Action> newActs;
                        newActs.reserve(live.edges.size());
                        for (const auto &le : live.edges) {
                            bool dup = false;
                            for (const auto &se : cur->edges) {
                                if (se.action == le.action) { dup = true; break; }
                            }
                            if (!dup) newActs.push_back(le.action);
                        }
                        if ((int)newActs.size() > g_s3ExpandMaxNew) {
                            std::shuffle(newActs.begin(), newActs.end(), rng);
                            newActs.resize(g_s3ExpandMaxNew);
                        }
                        if (!newActs.empty()) {
                            Node priors;
                            for (const auto &a : newActs)
                                priors.edges.push_back(Edge{a});
                            if ((g_usePolicyNet && g_policyNet.loaded())
                                || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly))
                                computeEdgePriors(priors, state);
                            for (size_t i = 0; i < newActs.size(); ++i)
                                cur->edges.push_back(Edge{newActs[i], Node{}, priors.edges[i].prior});
                            const int newIdx = selectBestValidEdgePUCT(*cur, state);
                            if (newIdx >= 0) {
                                auto &newEdge = cur->edges[newIdx];
                                maybeOutcomeBucketDiag(state, newEdge.action,
                                    agentSeed, (int)rootBc->encounter, rootBc->floorNum,
                                    state.turn, decisionIndex);
                                const bool persistentEndTurn = g_s3PersistentEndTurnChance
                                    && persistentEndTurnEligible(state, newEdge.action);
                                const auto persistentPreObservationHash = persistentEndTurn
                                    ? CombatObservation::fromBattleContext(state).visibleHash() : 0;
                                if (g_s3PersistentEndTurnChance
                                    && newEdge.action.getActionType() == ActionType::END_TURN) {
                                    if (persistentEndTurn) {
                                        ++eligibleEndTurnCount;
                                        ++g_pcEligible;
                                    } else {
                                        ++ineligibleEndTurnCount;
                                        ++g_pcIneligible;
                                    }
                                }
                                observeRngExposureAction(newEdge.action, state);
                                ++diag.treeActions;
                                actionStack.push_back(newEdge.action);
                                cur = &newEdge.child;
                                if (persistentEndTurn) {
                                    path.push_back(cur);
                                    cur = &dispatchPersistentEndTurnOutcome(
                                        newEdge, persistentPreObservationHash,
                                        CombatObservation::fromBattleContext(state));
                                }
                                if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(CombatObservation::fromBattleContext(state));
                                continue;
                            }
                        }
                    }
                }
            }
            ++diag.rolloutCalls;
            ++diag.fairIllegalStoredEdge;
            double eval = 0.0;
            const int rollSteps = multiRollout(state, actionStack, eval);
            diag.rolloutActions += rollSteps;
            backpropagate(path, eval, actionStack);
            finishRngExposureSimulation();
            return;
        }

        if (g_s3StrategyFusionDiag && !t_strategyFusionSuppressed
            && cur->isObsStable()
            && effectiveAction.getActionType() == ActionType::END_TURN
            && edge.child.simulationCount >= g_s3StrategyFusionDiagMinChildVisits)
            recordStrategyFusionCandidate(
                *cur, state, edge, path, rootBc->seed,
                (int)rootBc->encounter, rootBc->floorNum,
                state.turn, searchSimulationOrdinal);
        maybeOutcomeBucketDiag(state, effectiveAction,
            agentSeed, (int)rootBc->encounter, rootBc->floorNum,
            state.turn, decisionIndex);
        const bool persistentEndTurn = g_s3PersistentEndTurnChance
            && persistentEndTurnEligible(state, effectiveAction);
        const auto persistentPreObservationHash = persistentEndTurn
            ? CombatObservation::fromBattleContext(state).visibleHash() : 0;
        if (g_s3PersistentEndTurnChance
            && effectiveAction.getActionType() == ActionType::END_TURN) {
            if (persistentEndTurn) {
                ++eligibleEndTurnCount;
                ++g_pcEligible;
            } else {
                ++ineligibleEndTurnCount;
                ++g_pcIneligible;
            }
        }
        observeRngExposureAction(effectiveAction, state);
        ++diag.treeActions;
        actionStack.push_back(effectiveAction);
        cur = &edge.child;
        if (persistentEndTurn) {
            path.push_back(cur);
            cur = &dispatchPersistentEndTurnOutcome(
                edge, persistentPreObservationHash,
                CombatObservation::fromBattleContext(state));
        }
        if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(CombatObservation::fromBattleContext(state));

        if (g_s3Prune && canPruneAsDead(state)) {
            ++diag.leafDirectEval;
            backpropagate(path, 0.0, actionStack);
            finishRngExposureSimulation();
            return;
        }
    }

    // Depth cap: the final child node may never have been visited, so cache
    // its observation before the leaf eval. NOTE (issue #55): the node's
    // cached obsHash is set on first visit and never refreshed — under a
    // later determinization it is the FIRST world's hash while `state` is
    // the current world, so using cur->obsHash as the leaf-cache key could
    // serve a wrong-world value. Recompute the hash from the current state.
    ensureObservation(*cur, state);
    ++diag.leafDirectEval;
    const std::uint64_t leafObsHash =
        CombatObservation::fromBattleContext(state).visibleHash();
    const double leafEval = evaluateLeaf(state, leafObsHash);
    backpropagate(path, leafEval, actionStack);
    finishRngExposureSimulation();
}

// ---- Backpropagation --------------------------------------------------------
void BattleScumSearcher3::backpropagate(const std::vector<Node *> &path,
                                        double evaluation,
                                        const std::vector<Action> &actionStack) {
    if (evaluation > bestActionValue) {
        const bool wasEmpty = bestActionSequence.empty();
        bestActionSequence = actionStack;
        bestActionValue = evaluation;
        if (wasEmpty && !bestActionSequence.empty() && firstQExploitSimulation < 0)
            firstQExploitSimulation = searchSimulationOrdinal;
    }
    if (evaluation < minActionValue) {
        minActionValue = evaluation;
    }
    for (auto *node : path) {
        ++node->simulationCount;
        node->evaluationSum += evaluation;
        auto &d = node->dist;
        ++d.n;
        d.loQ20 += (evaluation - d.loQ20) * 0.02;
        d.loQ05 += (evaluation - d.loQ05) * 0.01;
    }
}

// ---- PUCT selection (AlphaZero formula: Q + c*P*sqrt(N)/(1+N_child)) -------
bool s3ShouldExploitQ(bool hasExploitableSequence, int reuseSearchCount) {
    return g_s3AlwaysQ || (g_reuseAlwaysQ ? reuseSearchCount >= 0 : hasExploitableSequence);
}

int BattleScumSearcher3::selectBestEdgePUCT(const Node &node) {
    const int n = (int)node.edges.size();
    if (n == 1) return 0;

    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
                       || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
    const double logParent  = usePuct ? 0.0 : std::log((double)(node.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt((double)(node.simulationCount + 1)) : 0.0;
    // STS_REUSE_ALWAYS_Q: on carried trees, always use Q from sim 1.
    // Otherwise (legacy): exploit only after bestActionSequence is non-empty.
    const bool exploit = s3ShouldExploitQ(!bestActionSequence.empty(), reuseSearchCount);
    const double evalRange = std::max(1.0, bestActionValue - minActionValue);

    int best = 0;
    double bestVal = -1e30;
    for (int i = 0; i < n; ++i) {
        const auto &e = node.edges[i];
        double q = 0.0;
        if (exploit) {
            double avg = e.child.evaluationSum / (e.child.simulationCount + 1);
            if (e.child.dist.n > 3) {
                double dn = e.child.dist.loQ05;
                avg = avg - riskLambda * (avg - dn);
            }
            q = avg / evalRange;
        }
        double explore = usePuct
            ? g_cPuct * e.prior * sqrtParent / (e.child.simulationCount + 1)
            : 3.0 * std::sqrt(2.0) * std::sqrt(logParent / (e.child.simulationCount + 1));
        double val = q + explore;
        if (i == 0 || val > bestVal) { best = i; bestVal = val; }
    }
    return best;
}

// STS_LIVE_VALID (Phase 4): same PUCT scoring as selectBestEdgePUCT, but
// restricted to edges whose action is valid in THIS determinization (particle
// world). Returns the best valid edge index, or -1 when none is valid.
int BattleScumSearcher3::selectBestValidEdgePUCT(const Node &node, const BattleContext &bc) {
    const int n = (int)node.edges.size();
    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
                       || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
    const double logParent  = usePuct ? 0.0 : std::log((double)(node.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt((double)(node.simulationCount + 1)) : 0.0;
    const bool exploit = s3ShouldExploitQ(!bestActionSequence.empty(), reuseSearchCount);
    const double evalRange = std::max(1.0, bestActionValue - minActionValue);

    int best = -1;
    double bestVal = -1e30;
    for (int i = 0; i < n; ++i) {
        const auto &e = node.edges[i];
        // Semantic CARD edge: resolve to live-hand index before validity check.
        Action effAction = e.action;
        if (g_s3SemanticCardEdges && e.hasCardKey) {
            auto resolved = resolveSemanticCardEdge(e, bc);
            if (!resolved) continue;  // card not in current hand
            effAction = *resolved;
        }
        if (!effAction.isValidAction(bc)) continue;
        double q = 0.0;
        if (exploit) {
            double avg = e.child.evaluationSum / (e.child.simulationCount + 1);
            if (e.child.dist.n > 3) {
                double dn = e.child.dist.loQ05;
                avg = avg - riskLambda * (avg - dn);
            }
            q = avg / evalRange;
        }
        double explore = usePuct
            ? g_cPuct * e.prior * sqrtParent / (e.child.simulationCount + 1)
            : 3.0 * std::sqrt(2.0) * std::sqrt(logParent / (e.child.simulationCount + 1));
        double val = q + explore;
        if (best == -1 || val > bestVal) { best = i; bestVal = val; }
    }
    return best;
}

// ---- Random rollout (attack-biased) -----------------------------------------
static int rolloutWeight(const Action &a, const BattleContext &bc) {
    switch (a.getActionType()) {
        case ActionType::CARD: {
            auto t = bc.cards.hand[a.getSourceIdx()].getType();
            if (t == CardType::ATTACK) return 8;
            if (t == CardType::POWER)  return 3;
            return 2;
        }
        case ActionType::END_TURN: return 1;
        case ActionType::POTION:   return 1;
        default:                   return 2;
    }
}

// ---- B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT, opt-in) ------------
// Beam-search a complete player turn: BFS over card/potion sequences to
// END_TURN, scoring only COMPLETE turns after the monster turn resolves (all
// candidates are copies of the same pre-turn state, so draw order and monster
// RNG are shared — common-random-numbers for free). Pruning between depths is
// simple first-N truncation (deterministic by enumeration order); there is no
// intermediate card-state scoring. The returned sequence is the best-scored
// complete turn and always contains at least END_TURN.
struct BeamCandidate {
    BattleContext bc;             // mid-turn state copy (PLAYER_NORMAL)
    std::vector<Action> actions;  // card/potion actions played so far this turn
    int powersPlayed = 0;
    int potionsUsed = 0;
};

struct TurnCandidate {
    std::vector<Action> actions;  // full turn: played actions + END_TURN
    double score = 0;
};

// S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
//     − w5·potion_use
// `pre` is the pre-turn state, `post` the state after the full turn resolved
// (monster turn included; block reset, next hand drawn). Uses only
// BattleContext fields plus the tracked powers/potion counts — no search RNG.
static double scoreCompleteTurn(const BattleContext &pre, const BattleContext &post,
                                int powersPlayed, int potionsUsed) {
    int enemyHpLoss = 0;
    int kills = 0;
    for (int i = 0; i < pre.monsters.monsterCount; ++i) {
        const int preHp = pre.monsters.arr[i].curHp;
        const int postHp = post.monsters.arr[i].curHp;
        if (preHp > 0 && postHp <= 0) ++kills;
        if (preHp > postHp) enemyHpLoss += preHp - postHp;
    }
    const int playerEffLoss = std::max(0,
        (pre.player.curHp + pre.player.block) - (post.player.curHp + post.player.block));
    const int setup = (post.player.strength - pre.player.strength)
                    + (post.player.dexterity - pre.player.dexterity)
                    + (post.player.focus - pre.player.focus)
                    + powersPlayed;
    return g_s3TurnScoreW1 * enemyHpLoss
         - g_s3TurnScoreW2 * playerEffLoss
         + g_s3TurnScoreW3 * kills
         + g_s3TurnScoreW4 * setup
         - g_s3TurnScoreW5 * potionsUsed;
}

static std::vector<Action> turnBeamSearch(const BattleContext &start) {
    const int beamWidth = std::max(1, g_s3TurnBeamWidth);
    const int maxDepth = std::max(1, start.cards.cardsInHand);

    std::vector<TurnCandidate> candidates;
    std::vector<BeamCandidate> beam;
    beam.emplace_back(BeamCandidate{start, {}, 0, 0});

    for (int depth = 0; depth < maxDepth; ++depth) {
        // Score a complete turn (END_TURN -> monster turn resolves) for every
        // beam state at this depth.
        for (const auto &c : beam) {
            BattleContext post = c.bc;
            const Action endTurn(ActionType::END_TURN);
            endTurn.execute(post);
            std::vector<Action> full = c.actions;
            full.push_back(endTurn);
            double score;
            if (post.outcome == Outcome::PLAYER_VICTORY) score = 1000.0;
            else if (post.outcome == Outcome::PLAYER_LOSS) score = -1000.0;
            else score = scoreCompleteTurn(start, post, c.powersPlayed, c.potionsUsed);
            candidates.push_back(TurnCandidate{std::move(full), score});
        }
        if (depth + 1 >= maxDepth) break;

        // Expand: play every valid non-END_TURN action on a copy. Sequences
        // that leave PLAYER_NORMAL (CARD_SELECT etc.) or lose the battle are
        // dropped; lethal (PLAYER_VICTORY) sequences are captured as +1000
        // candidates. The next level is pruned to beamWidth by first-N
        // truncation (no intermediate scoring).
        std::vector<BeamCandidate> next;
        BattleScumSearcher3::Node tmp;
        for (const auto &c : beam) {
            tmp.edges.clear();
            enumerateActionsForNode(tmp, c.bc);
            for (const auto &e : tmp.edges) {
                if (e.action.getActionType() == ActionType::END_TURN) continue;
                BattleContext child = c.bc;
                e.action.execute(child);
                if (child.outcome == Outcome::PLAYER_VICTORY) {
                    std::vector<Action> full = c.actions;
                    full.push_back(e.action);
                    candidates.push_back(TurnCandidate{std::move(full), 1000.0});
                    continue;
                }
                if (child.outcome == Outcome::PLAYER_LOSS) continue;
                if (child.inputState != InputState::PLAYER_NORMAL) continue;
                BeamCandidate nc;
                nc.bc = std::move(child);
                nc.actions = c.actions;
                nc.actions.push_back(e.action);
                nc.powersPlayed = c.powersPlayed;
                nc.potionsUsed = c.potionsUsed;
                if (e.action.getActionType() == ActionType::CARD
                    && c.bc.cards.hand[e.action.getSourceIdx()].getType() == CardType::POWER)
                    ++nc.powersPlayed;
                if (e.action.getActionType() == ActionType::POTION
                    && e.action.getTargetIdx() <= 5)
                    ++nc.potionsUsed;
                next.push_back(std::move(nc));
            }
        }
        if (next.empty()) break;
        if ((int)next.size() > beamWidth) next.resize(beamWidth);
        beam = std::move(next);
    }

    // Best complete turn; the depth-0 END_TURN candidate guarantees non-empty.
    const TurnCandidate *best = nullptr;
    for (const auto &c : candidates)
        if (!best || c.score > best->score) best = &c;
    if (best) return best->actions;
    return std::vector<Action>{Action(ActionType::END_TURN)};
}

int BattleScumSearcher3::multiRollout(BattleContext &state,
                                      std::vector<Action> &actionStack,
                                      double &evalOut) {
    const int k = std::max(1, g_s3RolloutK);
    int steps = 0;
    double sum = 0.0;
    std::vector<Action> scratch;
    for (int i = 0; i < k; ++i) {
        // Each rollout starts from the same pre-rollout state (independent
        // copy); the caller's `state` is left unmutated. The first rollout's
        // actions go into actionStack so bestActionSequence stays a valid,
        // replayable line.
        BattleContext sc = state;
        steps += playoutRandom(sc, i == 0 ? actionStack : scratch);
        sum += evaluateLeaf(sc);
    }
    evalOut = sum / k;
    return steps;
}

int BattleScumSearcher3::playoutRandom(BattleContext &state,
                                        std::vector<Action> &actionStack) {
    return playoutRandomWithRng(state, actionStack, rng);
}

int BattleScumSearcher3::diagnosticRollout(BattleContext &state,
                                            std::vector<Action> &actionStack,
                                            std::mt19937_64 &diagnosticRng,
                                            double &evalOut, bool &terminalOut) {
    const int steps = playoutRandomWithRng(state, actionStack, diagnosticRng);
    terminalOut = isTerminal(state);
    evalOut = evaluateLeaf(state);
    return steps;
}

int BattleScumSearcher3::playoutRandomWithRng(BattleContext &state,
                                               std::vector<Action> &actionStack,
                                               std::mt19937_64 &rolloutRng) {
    if ((g_useVNet && g_combatVNet.loaded() && g_vnetAlpha >= 1.0)
        || (g_useDistVNet && g_combatDistVNet.loaded())) return 0;

    Node tmp;
    int steps = 0;
    int turnsCompleted = 0;
    // STS_S3_ROLLOUT_POLICY (opt-in): sample rollout actions from the GBM
    // policy prior (the same distribution PUCT priors come from) instead of
    // the static rolloutWeight heuristic. Restricted to the GBM policy net —
    // a PVNet policy-head forward per rollout step would cost ~14-18x a sim.
    const bool usePrior = g_s3RolloutPolicy
        && g_usePolicyNet && g_policyNet.loaded()
        && !(g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
    while (!isTerminal(state) && steps < 200) {
        // B1 tactical turn-beam (STS_S3_TURN_ROLLOUT, opt-in): at PLAYER_NORMAL
        // states plan a complete turn by beam search and execute the best
        // sequence (cards/potions + END_TURN, monster turn included). Multi-turn
        // continuation is mandatory (A4 falsification, §133): after the beam
        // completes the turn the outer loop fires again on the next hand.
        // Non-PLAYER_NORMAL states (CARD_SELECT etc.) fall through to the
        // weighted random pick below; the whole branch is skipped when the env
        // gate is unset (byte-identical pre-B1 behavior).
        if (g_s3TurnRollout && state.inputState == InputState::PLAYER_NORMAL) {
            const std::vector<Action> seq = turnBeamSearch(state);
            for (const auto &a : seq) {
                if (steps >= 200 || isTerminal(state)) break;
                if (!a.isValidAction(state)) continue;
                const int turnBefore = state.turn;
                ++steps;
                actionStack.push_back(a);
                observeRngExposureAction(a, state);
                // STS_S3_ROLLOUT_TURN_STOP (A4): fires when the beam's END_TURN
                // completes the player turn (bc.turn incremented).
                if (g_s3RolloutTurnStop > 0 && state.turn != turnBefore
                    && ++turnsCompleted >= g_s3RolloutTurnStop)
                    return steps;
            }
            continue;
        }
        ++steps;
        enumerateActionsForNode(tmp, state);
        if (tmp.edges.empty()) break;

        int sel = 0;
        if (usePrior) {
            computeEdgePriors(tmp, state);
            double total = 0;
            for (const auto &e : tmp.edges) total += e.prior;
            double pick = std::uniform_real_distribution<double>(0.0, std::max(total, 1e-12))(rolloutRng);
            for (int i = 0; i < (int)tmp.edges.size(); ++i) {
                pick -= tmp.edges[i].prior;
                if (pick < 0) { sel = i; break; }
            }
        } else {
            int total = 0;
            for (const auto &e : tmp.edges) total += rolloutWeight(e.action, state);
            int pick = std::uniform_int_distribution<int>(0, total - 1)(rolloutRng);
            for (int i = 0; i < (int)tmp.edges.size(); ++i) {
                pick -= rolloutWeight(tmp.edges[i].action, state);
                if (pick < 0) { sel = i; break; }
            }
        }
        const auto &a = tmp.edges[sel].action;
        if (a.isValidAction(state)) {
            const int turnBefore = state.turn;
            actionStack.push_back(a);
            observeRngExposureAction(a, state);
            // STS_S3_ROLLOUT_TURN_STOP (A4): a player turn completed when the
            // action chain ran afterMonsterTurns (bc.turn incremented). Stop
            // after N completed turns; the non-terminal endpoint is then
            // evaluated by the learned leaf (n-step bootstrap).
            if (g_s3RolloutTurnStop > 0 && state.turn != turnBefore
                && ++turnsCompleted >= g_s3RolloutTurnStop)
                break;
        }
        tmp.edges.clear();
    }
    return steps;
}

// ── END_TURN marginalization ────────────────────────────────────────────
// At an eligible END_TURN leaf: generate N particles from the pre-END_TURN
// state, execute END_TURN on each, bucket by visibleHash, evaluate one
// representative per bucket, and return the weighted expectation.
double BattleScumSearcher3::endTurnMarginalEval(
    const BattleContext &preEndTurnState,
    std::vector<Action> &bestSeq)
{
    const int nP = g_s3EndTurnMarginalizeParticles;
    auto t0 = std::chrono::steady_clock::now();
    ++t_margEligible;

    // 1. Check eligibility.
    const int drawSize = (int)preEndTurnState.cards.drawPile.size();
    const int discardSize = (int)preEndTurnState.cards.discardPile.size();
    const bool reshuffle = (drawSize == 0 && discardSize > 0);
    if (drawSize > g_s3EndTurnMarginalizeMaxPile || reshuffle) {
        return std::numeric_limits<double>::quiet_NaN();
    }

    ++t_margApplied;

    // 2. Generate particles from the current visible observation.
    auto obs = CombatObservation::fromBattleContext(preEndTurnState);
    auto particles = HiddenBattleState::sampleParticles(obs, preEndTurnState, rng, nP);
    t_margParticlesSampled += nP;

    const Action endTurn(ActionType::END_TURN);

    // 3. Execute END_TURN under each particle, bucket by visibleHash.
    struct Mbucket {
        std::uint64_t visHash;
        int count = 0;
        BattleContext repState;
        std::vector<Action> repSeq;
        double repValue = 0.0;
    };
    std::unordered_map<std::uint64_t, Mbucket> buckets;

    for (const auto &p : particles) {
        BattleContext state = preEndTurnState;
        applyParticleImpl(state, p, rng);
        state.executeActions();
        endTurn.execute(state);
        state.executeActions();

        std::uint64_t vh = CombatObservation::fromBattleContext(state).visibleHash();
        auto &b = buckets[vh];
        if (b.count == 0) {
            b.visHash = vh;
            b.repState = state;
        }
        ++b.count;
    }

    const int nBuckets = (int)buckets.size();
    t_margUniqueBuckets += nBuckets;

    // 4. Evaluate each bucket's representative.
    double weightedSum = 0.0;
    double bestWeight = -1.0;
    const Mbucket *bestBucket = nullptr;

    for (auto &kv : buckets) {
        auto &b = kv.second;
        double weight = (double)b.count / nP;

        if (b.repState.outcome != Outcome::UNDECIDED) {
            b.repValue = evaluateTerminal(b.repState);
            ++t_margTermBuckets;
        } else {
            BattleContext &bc = b.repState;
            int compSteps = 0;
            if (g_s3Chain) {
                while (compSteps < 10 && bc.inputState == InputState::PLAYER_NORMAL
                       && bc.outcome == Outcome::UNDECIDED && bc.isCardPlayAllowed()) {
                    int handBefore = bc.cards.cardsInHand;
                    bool played = false;
                    for (int hi = 0; hi < bc.cards.cardsInHand && !played; ++hi) {
                        const auto &c = bc.cards.hand[hi];
                        if (!c.canUseOnAnyTarget(bc) || c.requiresTarget()) continue;
                        Action a(ActionType::CARD, hi);
                        if (!a.isValidAction(bc)) continue;
                        a.execute(bc);
                        b.repSeq.push_back(a);
                        if (bc.cards.cardsInHand != handBefore - 1) break;
                        played = true;
                        ++compSteps;
                    }
                    if (!played) break;
                }
            }

            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                && bc.outcome == Outcome::UNDECIDED && vnetCondAllowed(bc)) {
                vLeaf = g_combatVNet.predict(bc);
            } else if (g_usePVNet && g_combatPVNet.loaded()
                       && bc.outcome == Outcome::UNDECIDED
                       && pvnetCondAllowed(bc, 0)) {
                vLeaf = g_combatPVNet.leafValue(bc, riskLambda);
            }

            double rolloutEval = 0.0;
            std::vector<Action> dummyStack;
            multiRollout(bc, b.repSeq.empty() ? bestSeq : dummyStack, rolloutEval);
            if (!b.repSeq.empty())
                b.repSeq.insert(b.repSeq.end(), bestSeq.begin(), bestSeq.end());

            if (!std::isnan(vLeaf)) {
                double alpha = g_vnetAlphaLen ? 0.3 : g_vnetAlpha;
                b.repValue = alpha * vLeaf + (1.0 - alpha) * rolloutEval;
            } else {
                b.repValue = rolloutEval;
            }
            ++t_margContEvals;
        }

        weightedSum += weight * b.repValue;
        if (weight > bestWeight) {
            bestWeight = weight;
            bestBucket = &b;
        }
    }

    if (bestBucket && !bestBucket->repSeq.empty())
        bestSeq = bestBucket->repSeq;

    auto t1 = std::chrono::steady_clock::now();
    t_margSeconds += std::chrono::duration<double>(t1 - t0).count();

    // Shadow comparison (~1% sample).
    if (nBuckets > 0 && (rng() % 100) == 0) {
        BattleContext ordinaryState = preEndTurnState;
        applyParticleImpl(ordinaryState, particles[0], rng);
        ordinaryState.executeActions();
        endTurn.execute(ordinaryState);
        ordinaryState.executeActions();
        double ordinaryEval = 0.0;
        std::vector<Action> ordStack;
        if (ordinaryState.outcome != Outcome::UNDECIDED) {
            ordinaryEval = evaluateTerminal(ordinaryState);
        } else {
            multiRollout(ordinaryState, ordStack, ordinaryEval);
            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                && ordinaryState.outcome == Outcome::UNDECIDED)
                vLeaf = g_combatVNet.predict(ordinaryState);
            if (!std::isnan(vLeaf))
                ordinaryEval = g_vnetAlpha * vLeaf + (1.0 - g_vnetAlpha) * ordinaryEval;
        }
        ++t_margShadowCount;
        t_margShadowOrdinary += ordinaryEval;
        t_margShadowMarginal += weightedSum;
    }

    return weightedSum;
}

// ---- Terminal / leaf evaluation ---------------------------------------------
bool BattleScumSearcher3::isTerminal(const BattleContext &bc) const {
    return bc.outcome != Outcome::UNDECIDED;
}

double BattleScumSearcher3::evaluateTerminal(const BattleContext &bc) {
    double v;
    if (g_useDistVNet && g_combatDistVNet.loaded())
        v = g_combatDistVNet.predictFromBC(bc).riskAdjustedValue(
            riskLambda, bc.player.maxHp, g_combatDistVNet.winBonus);
    else
        v = bc.outcome == Outcome::PLAYER_VICTORY ? bc.player.curHp + 50.0 : 0.0;
    // Cross-combat pricing: the integration driver may add a run-level bonus
    // on victory leaves (post-combat HP/gold/potions/relic counters), so the
    // search can weigh e.g. stalling to align the Happy Flower counter.
    if (bc.outcome == Outcome::PLAYER_VICTORY && g_terminalBonus)
        v += g_terminalBonus(bc);
    return v;
}

double BattleScumSearcher3::evaluateLeaf(const BattleContext &bc, std::uint64_t obsHash) {
    if (isTerminal(bc)) return evaluateTerminal(bc);
    if (g_usePVNet && g_combatPVNet.loaded()) {
        // Phase 6: the direct-eval sites (no-legal-action, invalid-edge,
        // depth cap) re-evaluate the same visible state on repeated sims.
        // Cache by the node's obsHash — the transformer forward is the
        // dominant cost and the result is deterministic given the visible
        // state. obsHash == 0 disables caching (post-rollout states are
        // effectively unique).
        if (g_pvnetCache && obsHash != 0) {
            auto it = leafCache.find(obsHash);
            if (it != leafCache.end()) return it->second;
        }
        double v = g_combatPVNet.leafValue(bc, riskLambda);
        // Experimental STS_VNET_RANK_CORR: add the zero-mean ranking
        // correction on top of the primary prediction (same HP scale as the
        // vnet output; the model predicts approximately group-centered
        // residuals, and clampRankCorrAtRoot zeroes the per-search mean at
        // search-complete in the fair path).
        if (g_useVNetResidual && g_combatVNetResidual.loaded()) { const double res = g_combatVNetResidual.predict(bc); v += g_vnetResidualBeta * res; } if (g_useVNetRankCorr && g_combatVNetRankCorr.loaded()) {
            const double corr = g_combatVNetRankCorr.predict(bc);
            v += corr;
            rankCorrValues.push_back(corr);
        }
        if (g_pvnetCache && obsHash != 0) leafCache.emplace(obsHash, v);
        return v;
    }
    if (g_useDistVNet && g_combatDistVNet.loaded())
        return g_combatDistVNet.predictFromBC(bc).riskAdjustedValue(
            riskLambda, bc.player.maxHp, g_combatDistVNet.winBonus);
    if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha > 0.0
        && vnetCondAllowed(bc)) {
        g_vnetTraceParent = obsHash;   // parent node identity (from evaluateLeaf arg)
        g_vnetTraceDepth = 0;           // direct-eval site, not a tree leaf
        double v = g_combatVNet.predict(bc);
        // Experimental STS_VNET_RANK_CORR (see PVNet branch above).
        if (g_useVNetResidual && g_combatVNetResidual.loaded()) { const double res = g_combatVNetResidual.predict(bc); v += g_vnetResidualBeta * res; } if (g_useVNetRankCorr && g_combatVNetRankCorr.loaded()) {
            const double corr = g_combatVNetRankCorr.predict(bc);
            v += corr;
            rankCorrValues.push_back(corr);
        }
        return v;
    }
    double hpR = (double)bc.player.curHp / bc.player.maxHp;
    double eR = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0)
            eR += (double)bc.monsters.arr[i].curHp / bc.monsters.arr[i].maxHp;
    eR /= std::max(1, bc.monsters.monstersAlive);
    return 100.0 * (0.7 * hpR + 0.3 * (1.0 - eR));
}

void BattleScumSearcher3::clampRankCorrAtRoot() {
    if (rankCorrValues.empty()) return;   // correction model not loaded this search
    double sum = 0.0;
    for (const double c : rankCorrValues) sum += c;
    const double meanCorr = sum / (double)rankCorrValues.size();
    if (std::fabs(meanCorr) <= 0.1) return;   // below the zero-mean threshold: leave values untouched
    // Subtract the mean correction from every root edge's STORED MEAN value
    // (evaluationSum / simulationCount). Visit counts are unchanged, so the
    // root action choice (most-visited edge) is unchanged — this is a pure
    // scale-preservation adjustment so the correction cannot drift the HP
    // scale over the search.
    for (auto &e : root.edges)
        if (e.child.simulationCount > 0)
            e.child.evaluationSum -= meanCorr * (double)e.child.simulationCount;
}

bool BattleScumSearcher3::pvnetCondAllowed(const BattleContext &bc, int depth) const {
    if (g_pvnetCondMinTurn > 0 && bc.turn < g_pvnetCondMinTurn) return false;
    if (g_pvnetCondMinDepth > 0 && depth < g_pvnetCondMinDepth) return false;
    if (g_pvnetCondBossOnly && !isBossEncounter(bc.encounter)) return false;
    return true;
}

// ---- Action enumeration -----------------------------------------------------
void enumerateActionsForNode(BattleScumSearcher3::Node &node,
                             const BattleContext &bc) {
    switch (bc.inputState) {
        case InputState::PLAYER_NORMAL: {
            if (bc.isCardPlayAllowed()) {
                for (int hi = 0; hi < bc.cards.cardsInHand; ++hi) {
                    const auto &c = bc.cards.hand[hi];
                    if (!c.canUseOnAnyTarget(bc)) continue;
                    if (hi > 0) {
                        const auto &p = bc.cards.hand[hi - 1];
                        if (c.getId() == p.getId()
                            && c.getUpgradeCount() == p.getUpgradeCount()
                            && c.costForTurn == p.costForTurn
                            && c.freeToPlayOnce == p.freeToPlayOnce
                            && c.specialData == p.specialData)
                            continue;
                    }
                    if (c.requiresTarget()) {
                        for (int t = bc.monsters.monsterCount - 1; t >= 0; --t) {
                            if (bc.monsters.arr[t].isTargetable()) {
                                BattleScumSearcher3::Edge e{Action(ActionType::CARD, hi, t)};
                                if (g_s3SemanticCardEdges) {
                                    e.cardKey = BattleScumSearcher3::cardActionKey(bc, e.action);
                                    e.hasCardKey = (e.cardKey.id != CardId::INVALID);
                                }
                                node.edges.push_back(std::move(e));
                            }
                        }
                    } else {
                        BattleScumSearcher3::Edge e{Action(ActionType::CARD, hi)};
                        if (g_s3SemanticCardEdges) {
                            e.cardKey = BattleScumSearcher3::cardActionKey(bc, e.action);
                            e.hasCardKey = (e.cardKey.id != CardId::INVALID);
                        }
                        node.edges.push_back(std::move(e));
                    }
                }
            }
            for (int p = 0; p < bc.potionCapacity; ++p) {
                if (bc.potions[p] == Potion::EMPTY_POTION_SLOT
                    || bc.potions[p] == Potion::FAIRY_POTION) continue;
                if (bc.potions[p] == Potion::SMOKE_BOMB) {
                    if (!bc.smokeBombEscapeBlocked()) {
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p)});
                    } else {
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p, -1)});
                    }
                    continue;
                }
                if (!potionRequiresTarget(bc.potions[p])) {
                    node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p)});
                } else {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p, t)});
                }
            }
            node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::END_TURN)});
            break;
        }
        case InputState::CARD_SELECT: {
            // Single source of truth: search::Action::enumerateCardSelectActions
            // (the same contract the cardselect_parity test checks against
            // isValidAction).
            for (const auto &a : Action::enumerateCardSelectActions(bc)) {
                node.edges.push_back(BattleScumSearcher3::Edge{a});
            }
            break;
        }
        default:
            break;
    }
}

bool search::BattleScumSearcher3::onlyLegalAction(Action &out) {
    Node tmp;
    enumerateActionsForNode(tmp, *rootBc);
    if (tmp.edges.size() != 1) return false;
    out = tmp.edges[0].action;
    return true;
}

// ---- Policy priors ----------------------------------------------------------
void computeEdgePriors(BattleScumSearcher3::Node &node, const BattleContext &bc) {
    const int n = (int)node.edges.size();
    if (n <= 1) { if (n == 1) node.edges[0].prior = 1.f; return; }

    thread_local std::vector<float> feat, global, actionFeats;
    const int stateN = combatFeatureCount();
    const int actionN = combatPolicyFeatureCount() - stateN;
    if ((int)feat.size() < combatPolicyFeatureCount())
        feat.assign(combatPolicyFeatureCount(), 0.f);
    combatExtractFeatures(bc, feat.data());

    // ── PVNet policy (skipped when value-only so GBM provides priors) ──
    if (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly) {
        const int D = g_combatPVNet.entityDim;
        std::array<float,1766> stateArr{};
        for (int i=0;i<1766;++i) stateArr[i]=feat[i];
        global.resize(D);
        g_combatPVNet.encode(stateArr, global.data());

        const int actionN = combatPolicyFeatureCount() - combatFeatureCount();
        actionFeats.resize(n * actionN);
        for (int i = 0; i < n; ++i)
            combatFillActionFeatures(bc, node.edges[i].action, actionFeats.data() + i*actionN);

        // Score all actions at once
        thread_local std::vector<float> logitsCache;
        logitsCache.resize(n);
        float bestLogit = -1e30f;
        for (int i = 0; i < n; ++i) {
            float logit = g_combatPVNet.policyScore(global.data(), actionFeats.data() + i*actionN);
            if (logit > bestLogit) bestLogit = logit;
            logitsCache[i] = logit;
        }
        // Softmax
        float sum = 0.f;
        for (int i = 0; i < n; ++i) {
            logitsCache[i] = std::exp(logitsCache[i] - bestLogit);
            sum += logitsCache[i];
        }
        float inv = sum > 0.f ? 1.f / sum : 1.f / n;
        for (int i = 0; i < n; ++i)
            node.edges[i].prior = logitsCache[i] * inv;
        return;
    }

    // ── GBM policy (fallback) ──
    float entityState[64];
    if (g_policyNet.isEntityPolicy)
        g_policyNet.encodePolicyStateVec(feat.data(), entityState);

    std::vector<double> logits(n);
    double maxLog = -1e30;
    for (int i = 0; i < n; ++i) {
        combatFillActionFeatures(bc, node.edges[i].action, feat.data() + stateN);
        logits[i] = g_policyNet.isEntityPolicy
            ? g_policyNet.predictPolicyActionVec(feat.data(), entityState)
            : g_policyNet.predictVec(feat.data());
        if (logits[i] > maxLog) maxLog = logits[i];
    }
    double sum = 0;
    for (int i = 0; i < n; ++i) { logits[i] = std::exp(logits[i] - maxLog); sum += logits[i]; }
    double inv = sum > 0 ? 1.0 / sum : 1.0 / n;
    for (int i = 0; i < n; ++i) node.edges[i].prior = (float)(logits[i] * inv);
}

// ---- Root reconciliation (STS_REUSE_RECONCILE_ROOT) ------------------------
void BattleScumSearcher3::reconcileRoot(const BattleContext &liveRoot) {
    // 1. Enumerate all legal actions from the actual live root.
    Node fresh;
    enumerateActionsForNode(fresh, liveRoot);
    if (fresh.edges.empty()) return;

    // Draw-pile card-selection actions encode a raw draw-pile index, not a
    // stable card identity. Root expansion may have used a particle with a
    // different hidden draw order, so reconcile these actions by raw bits
    // against the actual live root.
    const bool rawIndexSensitive = isDrawPileIndexSensitiveCardSelect(liveRoot);

    // 2. Build a set of semantic card-action keys already present.
    std::set<CardActionKey> present;
    std::set<std::uint32_t> presentBits;  // for non-card actions (bits identity)
    for (const auto &e : root.edges) {
        if (rawIndexSensitive
            && e.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
            presentBits.insert(e.action.bits);
        } else if (e.action.getActionType() == ActionType::CARD
            || e.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
            // Use stored cardKey when available (stable identity across
            // hand-index remapping); otherwise fall back to positional.
            if (g_s3SemanticCardEdges && e.hasCardKey)
                present.insert(e.cardKey);
            else
                present.insert(cardActionKey(liveRoot, e.action));
        } else {
            presentBits.insert(e.action.bits);
        }
    }

    // 3. Add missing edges with zero prior and empty child.
    int added = 0;
    for (auto &fe : fresh.edges) {
        if (rawIndexSensitive
            && fe.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
            if (!presentBits.count(fe.action.bits)) {
                fe.prior = 0.f;
                root.edges.push_back(std::move(fe));
                presentBits.insert(root.edges.back().action.bits);
                ++added;
            }
        } else if (fe.action.getActionType() == ActionType::CARD
            || fe.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
            auto key = cardActionKey(liveRoot, fe.action);
            if (key.id == CardId::INVALID) continue;  // unresolvable
            if (!present.count(key)) {
                fe.prior = 0.f;
                root.edges.push_back(std::move(fe));
                present.insert(key);
                ++added;
            }
        } else {
            if (!presentBits.count(fe.action.bits)) {
                fe.prior = 0.f;
                root.edges.push_back(std::move(fe));
                presentBits.insert(fe.action.bits);
                ++added;
            }
        }
    }
    if (added > 0 && g_reuseDiag)
        std::cerr << "[reconcile-root] added " << added << " missing root edges\n";
}

// ---- Carry diagnostic (STS_REUSE_CARRY_DIAG) --------------------------------
void BattleScumSearcher3::printCarryDiagnostic(
    const Action &committedAction,
    const BattleContext &preState,
    const BattleContext &postState,
    const Node *promotedChild,
    const std::array<std::int32_t,6> &rngSnapshots) const {

    std::cerr << "\n[CARRY-DIAG] ===========================================\n";

    // Committed action
    std::cerr << "committed action: ";
    committedAction.printDesc(std::cerr, preState);
    std::cerr << "\n  type=" << (int)committedAction.getActionType();
    if (committedAction.getActionType() == ActionType::CARD) {
        int hi = committedAction.getSourceIdx();
        if (hi >= 0 && hi < preState.cards.cardsInHand) {
            const auto &c = preState.cards.hand[hi];
            std::cerr << " handIdx=" << hi
                      << " card=" << c.getName()
                      << " id=" << (int)c.getId()
                      << " upgraded=" << c.isUpgraded()
                      << " costForTurn=" << (int)c.costForTurn
                      << " freeToPlayOnce=" << c.freeToPlayOnce
                      << " specialData=" << (int)c.specialData
                      << " target=" << committedAction.getTargetIdx();
        }
    }
    std::cerr << "\n";

    // Observation hashes
    std::cerr << "observation hashes:\n"
              << "  old root obsHash    = " << rootObs.visibleHash() << "\n"
              << "  child cached obsHash = " << (promotedChild ? promotedChild->obsHash : 0ULL) << "\n"
              << "  new live root obsHash = "
              << CombatObservation::fromBattleContext(postState).visibleHash() << "\n";

    // Child observation stats
    if (promotedChild) {
        std::cerr << "child observation stability:\n"
                  << "  firstObsHash       = " << promotedChild->firstObsHash << "\n"
                  << "  nodeObsVisits      = " << promotedChild->nodeObsVisits << "\n"
                  << "  nodeObsMismatches  = " << promotedChild->nodeObsMismatches << "\n"
                  << "  total obs mismatch = " << obsMismatchCount << "\n";
    }

    // Hand before/after
    std::cerr << "hand before (" << preState.cards.cardsInHand << " cards):\n";
    for (int i = 0; i < preState.cards.cardsInHand; ++i) {
        const auto &c = preState.cards.hand[i];
        std::cerr << "  [" << i << "] " << c.getName()
                  << " id=" << (int)c.getId()
                  << " upg=" << c.isUpgraded() << "\n";
    }
    std::cerr << "hand after (" << postState.cards.cardsInHand << " cards):\n";
    for (int i = 0; i < postState.cards.cardsInHand; ++i) {
        const auto &c = postState.cards.hand[i];
        std::cerr << "  [" << i << "] " << c.getName()
                  << " id=" << (int)c.getId()
                  << " upg=" << c.isUpgraded() << "\n";
    }

    // Draw pile
    std::cerr << "drawPile: before=" << (int)preState.cards.drawPile.size()
              << " after=" << (int)postState.cards.drawPile.size() << "\n";
    std::cerr << "cardsDrawn: before=" << preState.cardsDrawn
              << " after=" << postState.cardsDrawn << "\n";

    // RNG deltas
    const char *names[6] = {"shuffle","cardRandom","ai","misc","monsterHp","potion"};
    std::int32_t cur[6] = {
        postState.shuffleRng.counter, postState.cardRandomRng.counter,
        postState.aiRng.counter, postState.miscRng.counter,
        postState.monsterHpRng.counter, postState.potionRng.counter};
    std::cerr << "RNG deltas:\n";
    for (int i = 0; i < 6; ++i)
        std::cerr << "  " << names[i] << "Rng: +" << (cur[i] - rngSnapshots[i]) << "\n";

    // Stored child edges
    if (promotedChild) {
        std::cerr << "stored child edges (" << promotedChild->edges.size() << "):\n";
        for (const auto &e : promotedChild->edges) {
            std::cerr << "  ";
            e.action.printDesc(std::cerr, postState);
            std::cerr << " bits=0x" << std::hex << e.action.bits << std::dec;
            std::cerr << " valid=" << (e.action.isValidAction(postState) ? "Y" : "N");
            if (e.action.getActionType() == ActionType::CARD) {
                int hi = e.action.getSourceIdx();
                std::cerr << " handIdx=" << hi;
                if (hi >= 0 && hi < postState.cards.cardsInHand) {
                    const auto &c = postState.cards.hand[hi];
                    std::cerr << " card=" << c.getName();
                } else {
                    std::cerr << " CARD-OUT-OF-BOUNDS";
                }
            }
            std::cerr << "\n";
        }
    }

    // Fresh live-root actions
    std::cerr << "fresh live-root actions:\n";
    Node freshRoot;
    enumerateActionsForNode(freshRoot, postState);
    for (const auto &e : freshRoot.edges) {
        std::cerr << "  ";
        e.action.printDesc(std::cerr, postState);
        if (e.action.getActionType() == ActionType::CARD) {
            std::cerr << " handIdx=" << e.action.getSourceIdx();
        }
        std::cerr << "\n";
    }

    // Flag stale positional card actions
    if (promotedChild) {
        for (const auto &se : promotedChild->edges) {
            if (se.action.getActionType() != ActionType::CARD) continue;
            int hi = se.action.getSourceIdx();
            // Find if same-indexed card in postState is different
            if (hi >= 0 && hi < preState.cards.cardsInHand
                && hi < postState.cards.cardsInHand) {
                const auto &preC = preState.cards.hand[hi];
                const auto &postC = postState.cards.hand[hi];
                if (preC.getId() != postC.getId()
                    || preC.getUpgradeCount() != postC.getUpgradeCount()
                    || preC.costForTurn != postC.costForTurn
                    || preC.freeToPlayOnce != postC.freeToPlayOnce
                    || preC.specialData != postC.specialData) {
                    std::cerr << "STALE: old CARD(idx=" << hi << "," << preC.getName()
                              << ") != new CARD(idx=" << hi << "," << postC.getName() << ")\n";
                }
            }
        }
    }

    std::cerr << "[CARRY-DIAG] ===========================================\n\n";
}

// ---- Reuse diagnostics ------------------------------------------------------
void BattleScumSearcher3::computeEdgeAvailability(const BattleContext &bc) {
    edgeAvailability.assign(root.edges.size(), 0);
    if (crnParticles.empty()) return;
    for (const auto &p : crnParticles) {
        BattleContext state = bc;
        applyParticle(state, p);
        for (size_t i = 0; i < root.edges.size(); ++i) {
            if (root.edges[i].action.isValidAction(state))
                ++edgeAvailability[i];
        }
    }
}

void BattleScumSearcher3::printReuseDiagnostics() const {
    std::cerr << "[reuse-diag] gen=" << reuseGeneration
              << " depth=" << reuseGenerationDepth
              << " searches=" << reuseSearchCount
              << " retained=" << retainedNodeCount
              << " obsMismatch=" << obsMismatchCount
              << " parentChildViol=" << parentChildViolations;
    if (!edgeAvailability.empty()) {
        std::cerr << " edgeAvail=[";
        for (size_t i = 0; i < edgeAvailability.size(); ++i) {
            if (i) std::cerr << ",";
            std::cerr << edgeAvailability[i];
        }
        std::cerr << "]";
    }
    if (g_s3SemanticCardEdges) {
        std::cerr << " semCardVisits=" << semanticCardEdgeVisits
                  << " semMismatches=" << rawIndexSemanticMismatches
                  << " semRebinds=" << semanticRebinds
                  << " semFailures=" << semanticResolutionFailures;
        if (semanticCardEdgeVisits > 0) {
            double rate = (double)rawIndexSemanticMismatches / semanticCardEdgeVisits;
            std::cerr << " mismatchRate=" << rate;
        }
    }
    if (g_s3EndTurnMarginalize) {
        std::cerr << " margElig=" << t_margEligible
                  << " margApplied=" << t_margApplied
                  << " margParts=" << t_margParticlesSampled
                  << " margBuckets=" << t_margUniqueBuckets
                  << " margContEvals=" << t_margContEvals
                  << " margTermBuckets=" << t_margTermBuckets
                  << " margSec=" << t_margSeconds;
        if (t_margApplied > 0) {
            std::cerr << " margAvgBuckets=" << ((double)t_margUniqueBuckets / t_margApplied);
        }
        if (t_margShadowCount > 0) {
            std::cerr << " shadowN=" << t_margShadowCount
                      << " shadowOrdMean=" << (t_margShadowOrdinary / t_margShadowCount)
                      << " shadowMargMean=" << (t_margShadowMarginal / t_margShadowCount);
        }
    }
    std::cerr << "\n";
}

// ---- Per-search CPU diagnostic (STS_REUSE_CPU_DIAG) ------------------------
BattleScumSearcher3::DiagSnapshot BattleScumSearcher3::snapshotDiag() const {
    return {diag.simulations, diag.terminalInsideTree, diag.rolloutCalls,
            diag.rolloutLeafCalls, diag.leafDirectEval, diag.rolloutActions,
            diag.treeActions, diag.maxTreeDepth, diag.simSeconds};
}

void BattleScumSearcher3::writeCpuDiagRow(
    std::uint64_t seed, int floor, int encounter, int combatIdx,
    int decisionIdx, const char *searchKind, int reuseGen,
    int carriedSearches, std::int64_t simsReq,
    const DiagSnapshot &before, const DiagSnapshot &after,
    std::int64_t rootSimBefore, std::int64_t rootSimAfter,
    int retainedNodes, int rootEdgeCount,
    int playerHp, int turn, int cardsInHand, int drawPile, int discardPile) {

    static bool headerWritten = false;
    static std::ofstream diagFile;
    std::ostream *out = &std::cerr;
    if (!g_reuseCpuDiagFile.empty()) {
        diagFile.open(g_reuseCpuDiagFile, headerWritten ? std::ios::app : std::ios::out);
        if (diagFile) out = &diagFile;
    }
    if (!headerWritten) {
        *out << "seed,floor,encounter,combatIdx,decisionIdx,"
             << "searchKind,reuseGen,carriedSearches,"
             << "simsReq,simsExec,simSeconds,"
             << "terminalInTree,rolloutCalls,rolloutLeafCalls,leafDirectEval,"
             << "rolloutActions,treeActions,maxTreeDepth,"
             << "rootSimBefore,rootSimAfter,"
             << "retainedNodes,rootEdgeCount,"
             << "playerHp,turn,cardsInHand,drawPile,discardPile\n";
        headerWritten = true;
    }
    std::int64_t simsExec = after.simulations - before.simulations;
    double s = after.simSeconds - before.simSeconds;
    *out << seed << "," << floor << "," << encounter << ","
         << combatIdx << "," << decisionIdx << ","
         << searchKind << "," << reuseGen << "," << carriedSearches << ","
         << simsReq << "," << simsExec << "," << s << ","
         << (after.terminalInsideTree - before.terminalInsideTree) << ","
         << (after.rolloutCalls - before.rolloutCalls) << ","
         << (after.rolloutLeafCalls - before.rolloutLeafCalls) << ","
         << (after.leafDirectEval - before.leafDirectEval) << ","
         << (after.rolloutActions - before.rolloutActions) << ","
         << (after.treeActions - before.treeActions) << ","
         << after.maxTreeDepth << ","
         << rootSimBefore << "," << rootSimAfter << ","
         << retainedNodes << "," << rootEdgeCount << ","
         << playerHp << "," << turn << "," << cardsInHand << ","
         << drawPile << "," << discardPile << "\n";
    if (!g_reuseCpuDiagFile.empty()) diagFile.close();
}

} // namespace sts::search
