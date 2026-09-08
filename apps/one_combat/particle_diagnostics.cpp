#include "particle_diagnostics.h"

#include "combat/BattleContext.h"
#include "constants/MonsterEncounters.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatObservation.h"
#include "sim/search/ScumSearchAgent2.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <mutex>
#include <numeric>
#include <optional>
#include <random>
#include <sstream>
#include <string>
#include <tuple>
#include <unordered_set>
#include <utility>
#include <vector>

namespace one_combat {
using namespace sts;

static bool g_particleDiagnosticsActive = false;
static constexpr int kParticleDiagnosticStrata = 10;
static std::string g_particleLeafProbeFile;
static int g_particleLeafProbeK = 8;
static double g_particleLeafProbeRate = 0.05;
static int g_particleLeafProbeMaxGroups = 16;

// Phase 1b: posterior-valid particle sensitivity probe. K=0 (default)
// evaluates ALL unique compatible leaf hidden states from the current finite
// root belief; K>0 caps evaluation at the K highest-mass states (the source
// world is always included, no duplicate padding). MAX_GROUPS: -1 unlimited,
// 0 captures nothing (probe-OFF determinism arm), >0 per-seed group cap.
static std::string g_particlePosteriorProbeFile;
static int g_particlePosteriorProbeK = 0;
static int g_particlePosteriorProbeMaxGroups = 16;
static bool g_particlePosteriorAgeSplit = false;
static int g_particlePosteriorAgeEarlyStart = 100;
static int g_particlePosteriorAgeEarlyEnd = 300;
static int g_particlePosteriorAgeLateStart = 2800;
static int g_particlePosteriorAgeLateEnd = 3000;
static int g_particlePosteriorAgeMinPerStratum = 8;
static int g_particlePosteriorAgePerStratum = 16;
static std::string g_particlePosteriorReplayDebugFile;
static int g_particlePosteriorReplayCeiling = 128;
static std::string g_particlePosteriorReplayTraceFile;

struct ParticleLeafProbeRow {
    std::uint64_t seed = 0, obsHash = 0, sourceLeafId = 0;
    int fightIdx = -1, decIdx = -1, variant = -1, depth = 0, turn = 0;
    int curHp = 0, maxHp = 0, rolloutSteps = 0, terminal = 0;
    int invariantOk = 0, drawPileSize = 0;
    int uniqueVariantsSampled = 0;
    double target = std::numeric_limits<double>::quiet_NaN();
    double rawRolloutEval = std::numeric_limits<double>::quiet_NaN();
    std::string encounter, drawOrder;
    std::vector<float> feats;
};

struct ParticlePosteriorAgeCandidate {
    int stratum = -1;
    int ordinal = -1;
    BattleContext state;
    search::S3LeafDiagnostic diagnostic;
};

struct ParticleDiagnosticContext {
    std::uint64_t seed = 0;
    int fightIdx = 0, floor = 0, act = 0;
    std::string encounter;
    int decIdx = 0;
    std::mt19937_64 rng;
    std::vector<ParticleLeafProbeRow> particleProbeRows;
    int particleProbeGroups = 0;
    std::uint64_t particleProbeSourceLeafSeq = 0;
    std::vector<struct ParticlePosteriorProbeRow> particlePosteriorRows;
    int particlePosteriorGroups = 0;
    std::uint64_t particlePosteriorSourceLeafSeq = 0;
    bool particlePosteriorAgeBins[2][16]{};
    std::vector<ParticlePosteriorAgeCandidate> particlePosteriorAgeCandidates[2];
    std::vector<int> particlePosteriorAgeSelected[2];
    std::string actionFingerprint;
    void init(std::uint64_t sd) {
        seed = sd; fightIdx = 0; floor = 0; act = 0; encounter.clear(); decIdx = 0;
        rng.seed(sd ? sd : 1);
        particleProbeRows.clear(); particleProbeGroups = 0; particleProbeSourceLeafSeq = 0;
        particlePosteriorRows.clear(); particlePosteriorGroups = 0; particlePosteriorSourceLeafSeq = 0;
        for (auto &stratum : particlePosteriorAgeBins)
            for (bool &seen : stratum) seen = false;
        for (auto &candidates : particlePosteriorAgeCandidates) candidates.clear();
        for (auto &ordinals : particlePosteriorAgeSelected) ordinals.clear();
        actionFingerprint.clear();
    }
};
static thread_local ParticleDiagnosticContext t_particleDiagnostics;

// 0 = hallway, 1 = elite, 2 = boss (elite set = MonsterEncounterPool::elites).
static int encounterDifficulty(sts::MonsterEncounter e) {
    if (sts::isBossEncounter(e)) return 2;
    for (const auto &row : MonsterEncounterPool::elites)
        for (const auto &el : row)
            if (el == e) return 1;
    return 0;
}

static int particleDiagnosticStratumImpl(const BattleContext &bc, int depth) {
    if (depth >= 20) return 9;
    const double hpFrac = bc.player.maxHp > 0
        ? (double)bc.player.curHp / bc.player.maxHp : 0.0;
    const int hb = hpFrac < 0.30 ? 0 : (hpFrac < 0.70 ? 1 : 2);
    return hb * 3 + encounterDifficulty(bc.encounter);
}

// Stratum partition: depth >= 20 -> 9 (dedicated deep-tree subset);
// otherwise hpFrac band (0,1,2) x difficulty (0,1,2) -> 0..8. The deep subset
// is its own reservoir so early- AND late-depth states both get coverage; the
// hpFrac x difficulty reservoirs cover the rest of the search distribution.
// Hot-path leaf hook: cheap stratum computation + reservoir sampling per
// stratum. Full features + model predictions are computed only for accepted
// rows. Uses only t_particleDiagnostics.rng (never search RNG) and reads the leaf state.
static std::string particleLeafDrawOrder(const BattleContext &bc) {
    std::ostringstream out;
    for (int i = (int)bc.cards.drawPile.size() - 1; i >= 0; --i) {
        if (i != (int)bc.cards.drawPile.size() - 1) out << ';';
        out << (int)bc.cards.drawPile[i].getId();
    }
    return out.str();
}

static bool particleLeafRngEqual(const BattleContext &a, const BattleContext &b) {
    return a.shuffleRng.seed0 == b.shuffleRng.seed0 && a.shuffleRng.seed1 == b.shuffleRng.seed1
        && a.shuffleRng.counter == b.shuffleRng.counter
        && a.cardRandomRng.seed0 == b.cardRandomRng.seed0 && a.cardRandomRng.seed1 == b.cardRandomRng.seed1
        && a.cardRandomRng.counter == b.cardRandomRng.counter
        && a.aiRng.seed0 == b.aiRng.seed0 && a.aiRng.seed1 == b.aiRng.seed1
        && a.aiRng.counter == b.aiRng.counter
        && a.miscRng.seed0 == b.miscRng.seed0 && a.miscRng.seed1 == b.miscRng.seed1
        && a.miscRng.counter == b.miscRng.counter
        && a.potionRng.seed0 == b.potionRng.seed0 && a.potionRng.seed1 == b.potionRng.seed1
        && a.potionRng.counter == b.potionRng.counter
        && a.monsterHpRng.seed0 == b.monsterHpRng.seed0 && a.monsterHpRng.seed1 == b.monsterHpRng.seed1
        && a.monsterHpRng.counter == b.monsterHpRng.counter;
}

static bool particleLeafSameMultiset(const BattleContext &a, const BattleContext &b) {
    if (a.cards.drawPile.size() != b.cards.drawPile.size()) return false;
    std::map<int, int> ca, cb;
    for (const auto &c : a.cards.drawPile) ++ca[(int)c.getId()];
    for (const auto &c : b.cards.drawPile) ++cb[(int)c.getId()];
    return ca == cb;
}

static void particleLeafProbeOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (g_particleLeafProbeFile.empty() || !d.searcher || !d.bc) return;
    const std::uint64_t sourceLeafId = ++t_particleDiagnostics.particleProbeSourceLeafSeq;
    if (g_particleLeafProbeMaxGroups > 0
        && t_particleDiagnostics.particleProbeGroups >= g_particleLeafProbeMaxGroups) return;
    if (g_particleLeafProbeRate < 1.0) {
        if (std::uniform_real_distribution<double>(0.0, 1.0)(t_particleDiagnostics.rng)
            >= g_particleLeafProbeRate) return;
    }
    const BattleContext &base = *d.bc;
    const int k = std::max(1, std::min(g_particleLeafProbeK, 64));
    const std::uint64_t rngSeed = (t_particleDiagnostics.seed * 0x9e3779b97f4a7c15ULL)
                                ^ sourceLeafId ^ 0x9e3779b97f4a7c15ULL;
    const int nf = search::combatFeatureCount();
    std::vector<float> baseFeatures(nf);
    search::combatExtractFeatures(base, baseFeatures.data());
    const std::string baseDrawOrder = particleLeafDrawOrder(base);
    std::vector<std::vector<CardInstance>> orders;
    std::unordered_set<std::string> distinctOrders;
    orders.push_back(base.cards.drawPile);
    distinctOrders.insert(baseDrawOrder);
    std::mt19937_64 orderRng(rngSeed ^ 0xd1b54a32d192ed03ULL);
    const int maxAttempts = std::max(16, k * 16);
    for (int attempt = 0; attempt < maxAttempts && (int)orders.size() < k; ++attempt) {
        std::vector<int> permutation(base.cards.drawPile.size());
        for (size_t i = 0; i < permutation.size(); ++i) permutation[i] = (int)i;
        std::shuffle(permutation.begin(), permutation.end(), orderRng);
        std::vector<CardInstance> candidate;
        candidate.reserve(permutation.size());
        for (int idx : permutation) candidate.push_back(base.cards.drawPile[idx]);
        std::ostringstream order;
        for (auto it = candidate.rbegin(); it != candidate.rend(); ++it) {
            if (it != candidate.rbegin()) order << ';';
            order << (int)it->getId();
        }
        if (distinctOrders.insert(order.str()).second) orders.push_back(std::move(candidate));
    }
    const int distinctCount = (int)distinctOrders.size();
    for (int variant = 0; variant < (int)orders.size(); ++variant) {
        BattleContext state = base;
        state.cards.drawPile = orders[variant];
        const std::string drawOrder = particleLeafDrawOrder(state);
        std::vector<float> features(nf);
        search::combatExtractFeatures(state, features.data());
        bool sameFeatures = features == baseFeatures;
        bool sameRng = particleLeafRngEqual(base, state);
        bool sameMultiset = particleLeafSameMultiset(base, state);
        std::mt19937_64 diagnosticRng(rngSeed);
        std::vector<search::Action> actions;
        double target = std::numeric_limits<double>::quiet_NaN();
        bool terminal = false;
        const int steps = d.searcher->diagnosticRollout(state, actions, diagnosticRng,
                                                         target, terminal);
        ParticleLeafProbeRow row;
        row.seed = t_particleDiagnostics.seed; row.fightIdx = t_particleDiagnostics.fightIdx; row.decIdx = t_particleDiagnostics.decIdx;
        row.sourceLeafId = sourceLeafId; row.obsHash = d.obsHash; row.variant = variant;
        row.depth = d.treeDepth; row.turn = base.turn; row.curHp = base.player.curHp;
        row.maxHp = base.player.maxHp; row.rolloutSteps = steps; row.terminal = terminal ? 1 : 0;
        row.invariantOk = (sameFeatures && sameRng && sameMultiset) ? 1 : 0;
        row.uniqueVariantsSampled = distinctCount;
        row.drawPileSize = (int)base.cards.drawPile.size(); row.target = target;
        row.rawRolloutEval = d.rawRolloutEval;
        row.encounter = t_particleDiagnostics.encounter; row.drawOrder = drawOrder;
        row.feats = std::move(features);
        t_particleDiagnostics.particleProbeRows.push_back(std::move(row));
    }
    ++t_particleDiagnostics.particleProbeGroups;
}

// Called after a run driven by runFullRunOOC: serialize the sampled rows for
// the current seed.
static std::string particleLeafProbeSeedCsv() {
    std::ostringstream o;
    for (const auto &row : t_particleDiagnostics.particleProbeRows) {
        o << row.seed << ',' << row.fightIdx << ',' << row.decIdx << ',' << row.sourceLeafId << ','
          << row.obsHash << ',' << row.variant << ',' << row.depth << ',' << row.encounter << ','
          << row.turn << ',' << row.curHp << ',' << row.maxHp << ',' << row.drawPileSize << ','
          << row.rolloutSteps << ',' << row.terminal << ',' << row.invariantOk << ',' << row.uniqueVariantsSampled << ',' << row.target
          << ',' << row.rawRolloutEval << ',' << row.drawOrder;
        for (const float v : row.feats) o << ',' << v;
        o << '\n';
    }
    return o.str();
}

static std::string particleLeafProbeHeaderStr() {
    std::string h = "seed,fightIdx,decIdx,sourceLeafId,obsHash,variant,treeDepth,encounterName,turn,"
                    "curHp,maxHp,drawPileSize,rolloutSteps,terminal,invariantOk,uniqueVariantsSampled,target,rawRolloutEval,drawOrder";
    for (const auto &name : search::combatFeatureNames()) h += ',' + name;
    return h;
}

// ---------------------------------------------------------------------------
// PHASE-1b posterior-valid particle sensitivity probe (particle_posterior_probe)
//
// For a sampled Searcher3 frontier-type-0 source leaf, replay the exact
// SEMANTIC pre-rollout action prefix (tree actions + expansion action +
// deterministic chain actions, with actual post-action observations recorded
// per step) under EVERY positive-weight particle of the searcher's CURRENT
// finite root belief. A candidate is compatible only if every checkpoint
// observation AND outcome match exactly (INTERMEDIATE_OBSERVATION_MISMATCH
// rejects even if the leaf later reconverges) and the final visible leaf
// observation + outcome match. Accepted leaf worlds are deduplicated by
// FullHiddenStateKey EQUALITY (ordered std::map, never a combined hash) with
// probability mass aggregated across collapsing root particles. Each
// evaluated compatible world is scored with the isolated diagnosticRollout
// using one per-group CRN seed; the searcher's RNG, tree, belief, and the
// live battle are never touched. Source groups whose source particle needed
// the stale-particle fallback shuffle are marked SOURCE_PARTICLE_FALLBACK and
// are scientifically ineligible (their replay is NOT an implementation
// failure). "Posterior-valid" is relative to Searcher3's finite belief
// approximation, not an exact Bayesian posterior.
// ---------------------------------------------------------------------------
struct ParticlePosteriorProbeRow {
    int rowType = 0;                     // 0 = group summary, 1 = evaluated compatible world
    std::uint64_t seed = 0, obsHash = 0, sourceLeafId = 0;
    int fightIdx = -1, decIdx = -1, treeDepth = 0, turn = 0;
    int curHp = 0, maxHp = 0, drawPileSize = 0;
    int rootParticleCount = 0, positiveParticleCount = 0, replayAttempted = 0;
    int replayCompatibleParticles = 0, uniqueCompatibleStates = 0, evaluatedWorldCount = 0;
    double compatibleMass = 0.0, evaluatedMass = 0.0;
    int sourceParticleIndex = -1, sourceParticleReplayOk = -1, sourceParticleFallback = 0;
    int groupEligible = 1, invariantOk = 1;
    std::string replayFailure;
    int semanticReplayFailures = 0, actionIllegalFailures = 0, intermediateObservationMismatches = 0;
    int intermediateOutcomeMismatches = 0, finalObservationMismatches = 0, drawPileMismatches = 0;
    int firstMismatchCheckpoint = -1;
    std::uint64_t expectedMismatchHash = 0, actualMismatchHash = 0;
    std::uint32_t mismatchActionBits = 0;
    int rootCarriedFlag = 0, reuseGeneration = 0, reuseSearchCount = -1;
    int searchSimulation = 0;
    std::string ageStratum;
    int ageBin = -1;
    int candidateParticleIndex = -1, candidateIsSource = 0, dedupOrdinal = -1;
    int semanticBranchesCreated = 0, maxSurvivingBranches = 0, branchesCollapsed = 0;
    int extraSemanticBranches = 0;
    int replayExplosion = 0;
    int rolloutSteps = 0, terminal = 0;
    double candidateWeight = 0.0;
    double target = std::numeric_limits<double>::quiet_NaN();
    double controlledTarget = std::numeric_limits<double>::quiet_NaN();
    double controlledTargetStd = std::numeric_limits<double>::quiet_NaN();
    std::string encounter, rngSignature, drawOrder;
};

// Audit-only RNG signature telemetry; hidden-state identity/dedup uses
// FullHiddenStateKey equality, never this hash.
static std::string posteriorProbeRngSignature(const sts::FullHiddenStateKey &key) {
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (int i = 0; i < 6; ++i) {
        h ^= key.seed0[i]; h *= 1099511628211ULL;
        h ^= key.seed1[i]; h *= 1099511628211ULL;
        h ^= (std::uint64_t)(std::int64_t)key.counter[i]; h *= 1099511628211ULL;
    }
    std::ostringstream o;
    o << std::hex << h;
    return o.str();
}

// Semantic remap of one recorded checkpoint action onto a candidate replay
// state whose hand order may differ. CARD rebinds by canonical card identity
// (resolveCardKeyInHand); END_TURN and POTION raw bits carry visible
// slot/target semantics and replay exactly. Any other action type (all
// card-select paths) has no exact semantic replay here -> nullopt, which
// marks the whole source group ineligible rather than guessing.
static std::optional<search::Action> posteriorProbeRemapAction(
    const search::S3LeafActionCheckpoint &cp, const BattleContext &state) {
    switch (cp.action.getActionType()) {
    case search::ActionType::CARD: {
        if (!cp.hasCardKey) return std::nullopt;
        search::BattleScumSearcher3::CardActionKey key;
        key.id = cp.cardId;
        key.upgradeCount = cp.upgradeCount;
        key.costForTurn = cp.costForTurn;
        key.freeToPlayOnce = cp.freeToPlayOnce;
        key.specialData = cp.specialData;
        key.target = cp.target;
        const auto hi = search::resolveCardKeyInHand(key, state);
        if (!hi) return std::nullopt;
        if (key.target >= 0)
            return search::Action(search::ActionType::CARD, *hi, key.target);
        return search::Action(search::ActionType::CARD, *hi);
    }
    case search::ActionType::END_TURN:
    case search::ActionType::POTION:
        return cp.action;
    default:
        return std::nullopt;   // SINGLE_/MULTI_CARD_SELECT: not exactly replayable
    }
}

static std::string replayCardDebug(const search::S3LeafActionCheckpoint &cp,
                                   const BattleContext &state,
                                   const search::Action &resolved) {
    std::ostringstream out;
    const int raw = cp.action.getSourceIdx();
    const int resolvedIndex = resolved.getSourceIdx();
    const int matches = std::count_if(state.cards.hand.begin(),
                                      state.cards.hand.begin() + state.cards.cardsInHand,
                                      [&](const CardInstance &card) {
        return card.getId() == cp.cardId
            && card.getUpgradeCount() == cp.upgradeCount
            && card.costForTurn == cp.costForTurn
            && card.freeToPlayOnce == cp.freeToPlayOnce
            && card.specialData == cp.specialData;
    });
    const CardInstance *resolvedCard = (resolvedIndex >= 0
        && resolvedIndex < state.cards.cardsInHand) ? &state.cards.hand[resolvedIndex] : nullptr;
    out << "checkpoint=" << cp.action.getSourceIdx()
        << ",rawIndex=" << raw
        << ",sourceUniqueId=" << cp.sourceUniqueId
        << ",resolvedIndex=" << resolvedIndex
        << ",resolvedUniqueId=" << (resolvedCard ? resolvedCard->uniqueId : -1)
        << ",sameIndex=" << (raw == resolvedIndex)
        << ",sameUniqueId=" << (resolvedCard && resolvedCard->uniqueId == cp.sourceUniqueId)
        << ",semanticMatches=" << matches
        << ",sourceCardId=" << (int)cp.cardId
        << ",sourceUpgradeCount=" << (int)cp.upgradeCount
        << ",sourceCost=" << (int)cp.sourceCost
        << ",sourceCostForTurn=" << (int)cp.costForTurn
        << ",sourceFreeToPlayOnce=" << cp.freeToPlayOnce
        << ",sourceSpecialData=" << cp.specialData
        << ",sourceRetain=" << cp.sourceRetain
        << ",target=" << cp.target;
    if (resolvedCard) {
        out << ",resolvedCardId=" << (int)resolvedCard->getId()
            << ",resolvedUpgradeCount=" << resolvedCard->getUpgradeCount()
            << ",resolvedCost=" << (int)resolvedCard->cost
            << ",resolvedCostForTurn=" << (int)resolvedCard->costForTurn
            << ",resolvedFreeToPlayOnce=" << resolvedCard->freeToPlayOnce
            << ",resolvedSpecialData=" << resolvedCard->specialData
            << ",resolvedRetain=" << resolvedCard->retain;
    }
    return out.str();
}

static bool replaySourcePrefix(const BattleContext &root,
                               const search::S3LeafDiagnostic &d,
                               bool semantic, int &firstMismatch,
                               std::string &detail) {
    BattleContext state = root;
    firstMismatch = -1;
    for (size_t i = 0; i < d.actionCheckpoints.size(); ++i) {
        const auto &cp = d.actionCheckpoints[i];
        std::optional<search::Action> action = semantic
            ? posteriorProbeRemapAction(cp, state)
            : std::optional<search::Action>(cp.action);
        if (!action || !action->isValidAction(state)) {
            firstMismatch = (int)i;
            detail = "unresolved_or_illegal";
            return false;
        }
        if (semantic && cp.action.getActionType() == search::ActionType::CARD) {
            if (!detail.empty()) detail += ";";
            detail += replayCardDebug(cp, state, *action);
        }
        action->execute(state);
        const auto obs = sts::CombatObservation::fromBattleContext(state);
        if (obs != cp.observation || state.outcome != cp.outcome) {
            firstMismatch = (int)i;
            return false;
        }
    }
    return true;
}

static void writeReplayDebugRow(const search::S3LeafDiagnostic &d,
                                const BattleContext &sourceRoot,
                                std::uint64_t seed, int fightIdx, int decIdx,
                                std::uint64_t sourceLeafId) {
    if (g_particlePosteriorReplayDebugFile.empty()) return;
    int rawMismatch = -1, semanticMismatch = -1;
    std::string rawDetail, semanticDetail;
    const bool rawOk = replaySourcePrefix(sourceRoot, d, false, rawMismatch, rawDetail);
    const bool semanticOk = replaySourcePrefix(sourceRoot, d, true, semanticMismatch, semanticDetail);
    static std::mutex mutex;
    std::lock_guard<std::mutex> lock(mutex);
    std::ifstream probe(g_particlePosteriorReplayDebugFile);
    const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    std::ofstream out(g_particlePosteriorReplayDebugFile, std::ios::app);
    if (!out) return;
    if (empty) out << "seed,fightIdx,decIdx,sourceLeafId,sourceParticleIndex,rawSourceReplayOk,"
                      "semanticSourceReplayOk,rawFirstMismatchCheckpoint,semanticFirstMismatchCheckpoint,"
                      "rootCarried,reuseGeneration,hiddenFingerprintBeforeMismatch,cardDebug\n";
    std::uint64_t hiddenBefore = 0;
    if (semanticMismatch > 0 && semanticMismatch - 1 < (int)d.actionCheckpoints.size())
        hiddenBefore = d.actionCheckpoints[semanticMismatch - 1].hiddenFingerprint;
    out << seed << ',' << fightIdx << ',' << decIdx << ',' << sourceLeafId << ','
        << d.particleIndex << ',' << rawOk << ',' << semanticOk << ','
        << rawMismatch << ',' << semanticMismatch << ',' << d.rootCarried << ','
        << d.reuseGeneration << ',' << hiddenBefore << ",\"" << semanticDetail << "\"\n";
}

static int particlePosteriorAgeStratumForOrdinal(int ordinal) {
    if (ordinal >= g_particlePosteriorAgeEarlyStart
        && ordinal <= g_particlePosteriorAgeEarlyEnd) return 0;
    if (ordinal >= g_particlePosteriorAgeLateStart
        && ordinal <= g_particlePosteriorAgeLateEnd) return 1;
    return -1;
}

static void particlePosteriorAgeCaptureOnLeafQuery(
    const search::S3LeafDiagnostic &d) {
    if (d.frontierType != 0 || t_particleDiagnostics.fightIdx != 0 || t_particleDiagnostics.decIdx != 0) return;
    const int stratum = particlePosteriorAgeStratumForOrdinal(
        d.searchSimulationOrdinal);
    if (stratum < 0) return;
    auto &candidates = t_particleDiagnostics.particlePosteriorAgeCandidates[stratum];
    if (!candidates.empty() && candidates.back().ordinal == d.searchSimulationOrdinal)
        return;
    ParticlePosteriorAgeCandidate candidate;
    candidate.stratum = stratum;
    candidate.ordinal = d.searchSimulationOrdinal;
    candidate.state = *d.bc;
    candidate.diagnostic = d;
    candidates.push_back(std::move(candidate));
}

static std::vector<int> particlePosteriorAgeSelectEvenly(
    const std::vector<ParticlePosteriorAgeCandidate> &candidateRows) {
    std::vector<int> candidates;
    candidates.reserve(candidateRows.size());
    for (const auto &candidate : candidateRows) candidates.push_back(candidate.ordinal);
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
    std::vector<int> selected;
    if (candidates.size() < static_cast<size_t>(g_particlePosteriorAgeMinPerStratum))
        return selected;
    const int target = static_cast<int>(std::min<size_t>(16, candidates.size()));
    selected.reserve(target);
    for (int rank = 0; rank < target; ++rank) {
        const size_t index = std::min(
            candidates.size() - 1,
            (static_cast<size_t>(2 * rank + 1) * candidates.size())
                / (2 * static_cast<size_t>(target)));
        selected.push_back(candidates[index]);
    }
    return selected;
}

static void particlePosteriorProbeOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (g_particlePosteriorProbeFile.empty() || !d.searcher || !d.bc) return;
    if (d.frontierType != 0) return;   // actual S3 frontier leaves only
    int ageStratum = -1;
    int ageBin = -1;
    if (g_particlePosteriorAgeSplit) {
        if (t_particleDiagnostics.fightIdx != 0 || t_particleDiagnostics.decIdx != 0) return;
        ageStratum = particlePosteriorAgeStratumForOrdinal(
            d.searchSimulationOrdinal);
        if (ageStratum < 0) return;
        const auto &selected = t_particleDiagnostics.particlePosteriorAgeSelected[ageStratum];
        const auto it = std::find(selected.begin(), selected.end(),
                                  d.searchSimulationOrdinal);
        if (it == selected.end()) return;
        ageBin = static_cast<int>(it - selected.begin());
        if (ageBin >= 16 || t_particleDiagnostics.particlePosteriorAgeBins[ageStratum][ageBin]) return;
    } else if (g_particlePosteriorProbeMaxGroups >= 0
               && t_particleDiagnostics.particlePosteriorGroups >= g_particlePosteriorProbeMaxGroups) return;
    const std::uint64_t sourceLeafId = ++t_particleDiagnostics.particlePosteriorSourceLeafSeq;
    const BattleContext &base = *d.bc;
    const auto &particles = d.searcher->belief.particles;
    const int sourceIndex = static_cast<int>(d.particleIndex);

    ParticlePosteriorProbeRow g;
    g.seed = t_particleDiagnostics.seed; g.fightIdx = t_particleDiagnostics.fightIdx; g.decIdx = t_particleDiagnostics.decIdx;
    g.sourceLeafId = sourceLeafId; g.obsHash = d.obsHash; g.treeDepth = d.treeDepth;
    g.turn = base.turn; g.curHp = base.player.curHp; g.maxHp = base.player.maxHp;
    g.drawPileSize = (int)base.cards.drawPile.size(); g.encounter = t_particleDiagnostics.encounter;
    g.rootParticleCount = (int)particles.size();
    g.positiveParticleCount = (int)std::count_if(
        particles.begin(), particles.end(),
        [](const sts::HiddenBattleState &p) { return p.weight > 0.0; });
    double positiveWeightTotal = 0.0;
    for (const auto &p : particles) if (p.weight > 0.0) positiveWeightTotal += p.weight;
    g.sourceParticleIndex = sourceIndex;
    g.sourceParticleFallback = d.particleUsedFallback ? 1 : 0;
    g.rootCarriedFlag = d.rootCarried ? 1 : 0;
    g.reuseGeneration = d.reuseGeneration;
    g.reuseSearchCount = d.reuseSearchCount;
    g.searchSimulation = d.searchSimulationOrdinal;
    g.ageStratum = ageStratum == 0 ? "EARLY" : ageStratum == 1 ? "LATE" : "";
    g.ageBin = ageBin;
    if (!g_particlePosteriorReplayDebugFile.empty()
        && sourceIndex >= 0 && sourceIndex < (int)particles.size()) {
        BattleContext sourceRoot = *d.searcher->rootBc;
        if (search::applyHiddenStateExact(sourceRoot, particles[sourceIndex]))
            writeReplayDebugRow(d, sourceRoot, t_particleDiagnostics.seed, t_particleDiagnostics.fightIdx,
                                t_particleDiagnostics.decIdx, sourceLeafId);
    }

    auto finishGroup = [&]() {
        t_particleDiagnostics.particlePosteriorRows.push_back(g);
        ++t_particleDiagnostics.particlePosteriorGroups;
        if (g_particlePosteriorAgeSplit)
            t_particleDiagnostics.particlePosteriorAgeBins[ageStratum][ageBin] = true;
    };

    // (1) Source simulation needed the stale-particle fallback shuffle: the
    // stored particle alone does not specify that world. Scientifically
    // ineligible; NOT an implementation failure and replay is not attempted.
    if (d.particleUsedFallback) {
        g.groupEligible = 0;
        g.sourceParticleReplayOk = -1;
        g.replayFailure = "SOURCE_PARTICLE_FALLBACK";
        finishGroup();
        return;
    }
    if (sourceIndex < 0 || sourceIndex >= (int)particles.size()) {
        g.groupEligible = 0; g.sourceParticleReplayOk = -1; g.invariantOk = 0;
        g.replayFailure = "SOURCE_PARTICLE_INDEX_INVALID";
        finishGroup();
        return;
    }
    // (2) The prefix must be exactly replayable by action semantics. Any
    // card-select action (or a CARD without recorded identity) makes the whole
    // group ineligible — no raw-index replay is pretended to be equivalent.
    for (const auto &cp : d.actionCheckpoints) {
        const auto type = cp.action.getActionType();
        const bool intrinsicallyUnsupported =
            (type != search::ActionType::CARD
             && type != search::ActionType::END_TURN
             && type != search::ActionType::POTION)
            || (type == search::ActionType::CARD && !cp.hasCardKey);
        if (intrinsicallyUnsupported) {
            g.groupEligible = 0;
            g.sourceParticleReplayOk = -1;
            g.replayFailure = "UNREPLAYABLE_ACTION_PREFIX";
            finishGroup();
            return;
        }
    }

    const CombatObservation sourceFinalObs = CombatObservation::fromBattleContext(base);
    struct Candidate {
        int rootIndex = -1;
        double weight = 0.0;
        bool source = false;
        BattleContext state;
        sts::FullHiddenStateKey key;
    };
    using PhysicalCardKey = std::tuple<CardId, std::int16_t,
                                       std::int8_t, std::int8_t, bool, bool, bool>;
    struct ReplayStateKey {
        sts::FullHiddenStateKey hidden;
        std::vector<PhysicalCardKey> draw, hand, discard, exhaust;
        bool operator<(const ReplayStateKey &o) const {
            return std::tie(hidden, draw, hand, discard, exhaust)
                < std::tie(o.hidden, o.draw, o.hand, o.discard, o.exhaust);
        }
    };
    // Canonicalize the identity of each ordered card zone so that
    // permutations of behaviorally-identical duplicate cards (differing only
    // by simulator-private CardInstance::uniqueId) collapse during replay
    // dedup. All gameplay-meaningful fields (id, specialData, cost,
    // costForTurn, upgraded, freeToPlayOnce, retain) remain in the key; zone
    // ORDER is preserved (hand/draw/discard ordering is observably meaningful).
    auto physicalCards = [](const std::vector<CardInstance> &cards) {
        std::vector<PhysicalCardKey> out;
        out.reserve(cards.size());
        for (const auto &c : cards)
            out.emplace_back(c.id, c.specialData, c.cost,
                             c.costForTurn, c.upgraded, c.freeToPlayOnce, c.retain);
        return out;
    };
    auto replayStateKey = [&](const BattleContext &state) {
        ReplayStateKey key{sts::fullHiddenStateKey(state), {}, {}, {}, {}};
        key.draw = physicalCards(state.cards.drawPile);
        key.hand = physicalCards(std::vector<CardInstance>(
            state.cards.hand.begin(), state.cards.hand.begin() + state.cards.cardsInHand));
        key.discard = physicalCards(state.cards.discardPile);
        key.exhaust = physicalCards(state.cards.exhaustPile);
        return key;
    };
    std::vector<Candidate> compatible;
    std::map<sts::FullHiddenStateKey, size_t> byKey;   // equality-backed exact identity
    int acceptedParticles = 0;

    auto replayCandidate = [&](int particleIndex, bool isSource) {
        Candidate c;
        c.rootIndex = particleIndex;
        c.weight = positiveWeightTotal > 0.0
            ? particles[particleIndex].weight / positiveWeightTotal : 0.0;
        c.source = isSource;
        c.state = *d.searcher->rootBc;
        if (!search::applyHiddenStateExact(c.state, particles[particleIndex])) {
            ++g.drawPileMismatches;
            return;
        }
        std::vector<Candidate> frontier{std::move(c)};
        for (size_t checkpointIndex = 0; checkpointIndex < d.actionCheckpoints.size(); ++checkpointIndex) {
            const auto &cp = d.actionCheckpoints[checkpointIndex];
            std::vector<Candidate> next;
            int generatedThisCheckpoint = 0;
            for (const auto &stateCandidate : frontier) {
                std::vector<search::Action> actions;
                if (cp.action.getActionType() == search::ActionType::CARD) {
                    search::BattleScumSearcher3::CardActionKey key;
                    key.id = cp.cardId; key.upgradeCount = cp.upgradeCount;
                    key.costForTurn = cp.costForTurn; key.freeToPlayOnce = cp.freeToPlayOnce;
                    key.specialData = cp.specialData; key.target = cp.target;
                    for (int hi = 0; hi < stateCandidate.state.cards.cardsInHand; ++hi) {
                        const auto &card = stateCandidate.state.cards.hand[hi];
                        if (card.getId() == key.id && card.getUpgradeCount() == key.upgradeCount
                            && card.costForTurn == key.costForTurn
                            && card.freeToPlayOnce == key.freeToPlayOnce
                            && card.specialData == key.specialData) {
                            auto action = key.target >= 0
                                ? search::Action(search::ActionType::CARD, hi, key.target)
                                : search::Action(search::ActionType::CARD, hi);
                            if (action.isValidAction(stateCandidate.state)) actions.push_back(action);
                        }
                    }
                    g.semanticBranchesCreated += (int)actions.size();
                    g.extraSemanticBranches += std::max(0, (int)actions.size() - 1);
                    generatedThisCheckpoint += (int)actions.size();
                } else {
                    const auto action = posteriorProbeRemapAction(cp, stateCandidate.state);
                    if (action && action->isValidAction(stateCandidate.state)) actions.push_back(*action);
                }
                for (const auto &action : actions) {
                    Candidate successor = stateCandidate;
                    action.execute(successor.state);
                    const auto obs = CombatObservation::fromBattleContext(successor.state);
                    if (obs == cp.observation && successor.state.outcome == cp.outcome)
                        next.push_back(std::move(successor));
                    else if (obs != cp.observation) ++g.intermediateObservationMismatches;
                    else ++g.intermediateOutcomeMismatches;
                }
            }
            std::map<ReplayStateKey, size_t> checkpointKeys;
            std::vector<Candidate> deduped;
            for (auto &candidate : next) {
                const auto key = replayStateKey(candidate.state);
                const auto inserted = checkpointKeys.emplace(key, deduped.size());
                if (inserted.second)
                    deduped.push_back(std::move(candidate));
                else {
                    auto &existing = deduped[inserted.first->second];
                    ++g.branchesCollapsed;
                }
            }
            g.maxSurvivingBranches = std::max(g.maxSurvivingBranches, (int)deduped.size());
            if (!g_particlePosteriorReplayTraceFile.empty()) {
                static std::mutex traceMutex;
                std::lock_guard<std::mutex> lock(traceMutex);
                std::ifstream probe(g_particlePosteriorReplayTraceFile);
                const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
                std::ofstream out(g_particlePosteriorReplayTraceFile, std::ios::app);
                if (out) {
                    if (empty)
                        out << "seed,sourceLeafId,checkpoint,incoming,generated,outgoing,actionType,cardId\n";
                    out << t_particleDiagnostics.seed << ',' << sourceLeafId << ',' << checkpointIndex << ','
                        << (int)frontier.size() << ',' << generatedThisCheckpoint
                        << ',' << (int)deduped.size()
                        << ',' << (int)cp.action.getActionType() << ',' << (int)cp.cardId << '\n';
                }
            }
            if (deduped.size() > g_particlePosteriorReplayCeiling) {
                g.replayExplosion = 1;
                g.replayFailure = "AMBIGUOUS_SEMANTIC_REPLAY_EXPLOSION";
                return;
            }
            frontier = std::move(deduped);
            if (frontier.empty()) return;
        }
        std::map<sts::FullHiddenStateKey, Candidate> localLeaves;
        bool finalAccepted = false;
        for (auto &survivor : frontier) {
            const CombatObservation finalObs = CombatObservation::fromBattleContext(survivor.state);
            if (finalObs != sourceFinalObs || survivor.state.outcome != d.outcome) {
                ++g.finalObservationMismatches;
                continue;
            }
            survivor.key = sts::fullHiddenStateKey(survivor.state);
            const auto existing = localLeaves.find(survivor.key);
            if (existing == localLeaves.end()) {
                localLeaves.emplace(survivor.key, std::move(survivor));
            } else if (survivor.source && !existing->second.source) {
                existing->second = std::move(survivor);
            }
        }
        if (!localLeaves.empty()) {
            const double branchWeight = c.weight / localLeaves.size();
            for (auto &[key, survivor] : localLeaves) {
                survivor.weight = branchWeight;
                const auto found = byKey.find(key);
                if (found != byKey.end()) {
                    compatible[found->second].weight += survivor.weight;
                    compatible[found->second].source |= survivor.source;
                } else {
                    byKey.emplace(key, compatible.size());
                    compatible.push_back(std::move(survivor));
                }
            }
            finalAccepted = true;
        }
        if (finalAccepted) ++acceptedParticles;
    };

    g.replayAttempted = g.positiveParticleCount
        + (particles[sourceIndex].weight > 0.0 ? 0 : 1);
    replayCandidate(sourceIndex, true);
    for (int i = 0; i < (int)particles.size(); ++i)
        if (particles[i].weight > 0.0 && i != sourceIndex)
            replayCandidate(i, false);

    if (g.replayExplosion) {
        g.groupEligible = 0;
        g.sourceParticleReplayOk = -1;
        finishGroup();
        return;
    }

    g.replayCompatibleParticles = acceptedParticles;
    bool sourceOk = false;
    double compatibleMass = 0.0;
    for (const auto &c : compatible) {
        compatibleMass += c.weight;
        if (c.source) sourceOk = true;
    }
    g.uniqueCompatibleStates = (int)compatible.size();
    g.compatibleMass = compatibleMass;

    // (3) Mandatory source-particle replay invariant. The exact source
    // particle MUST reproduce the source leaf; failure is an implementation
    // failure that invalidates the run.
    if (!sourceOk) {
        g.sourceParticleReplayOk = 0;
        g.invariantOk = 0;
        g.replayFailure = "SOURCE_PARTICLE_REPLAY_FAILED";
        finishGroup();
        return;
    }
    g.sourceParticleReplayOk = 1;

    // (4) Evaluation set: all unique compatible states by default; if K > 0,
    // deterministic mass-respecting selection (highest weight first, ties by
    // discovery order) with the source world always included, no padding.
    std::vector<int> order(compatible.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = (int)i;
    const int cap = g_particlePosteriorProbeK > 0
        ? std::min(g_particlePosteriorProbeK, (int)compatible.size())
        : (int)compatible.size();
    if ((int)order.size() > cap) {
        std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
            return compatible[a].weight > compatible[b].weight;
        });
        order.resize(cap);
        int sourceSlot = -1;
        for (int i = 0; i < (int)compatible.size(); ++i)
            if (compatible[i].source) { sourceSlot = i; break; }
        if (sourceSlot >= 0 && !order.empty()
            && std::find(order.begin(), order.end(), sourceSlot) == order.end())
            order.back() = sourceSlot;
    }
    g.evaluatedWorldCount = (int)order.size();
    double evaluatedMass = 0.0;
    for (int idx : order) evaluatedMass += compatible[idx].weight;
    g.evaluatedMass = evaluatedMass;

    const std::uint64_t rngSeed = (t_particleDiagnostics.seed * 0x9e3779b97f4a7c15ULL)
                                ^ sourceLeafId ^ 0x9e3779b97f4a7c15ULL;
    constexpr int kControlledRollouts = 4;
    struct ControlledValue { double mean = 0.0; double std = 0.0; };
    std::map<std::vector<sts::FullHiddenCardId>, ControlledValue> controlled;
    for (int idx : order) {
        const auto &candidate = compatible[idx];
        auto &value = controlled[candidate.key.drawPileOrder];
        std::vector<double> samples;
        samples.reserve(kControlledRollouts);
        for (int replicate = 0; replicate < kControlledRollouts; ++replicate) {
            BattleContext controlledState = base;
            controlledState.cards.drawPile = candidate.state.cards.drawPile;
            std::mt19937_64 controlledRng(rngSeed ^ (std::uint64_t)replicate
                                          * 0xd1b54a32d192ed03ULL);
            std::vector<search::Action> controlledActions;
            double controlledTarget = std::numeric_limits<double>::quiet_NaN();
            bool controlledTerminal = false;
            d.searcher->diagnosticRollout(controlledState, controlledActions,
                                          controlledRng, controlledTarget,
                                          controlledTerminal);
            samples.push_back(controlledTarget);
        }
        value.mean = std::accumulate(samples.begin(), samples.end(), 0.0)
            / samples.size();
        double variance = 0.0;
        for (double sample : samples)
            variance += (sample - value.mean) * (sample - value.mean);
        value.std = std::sqrt(variance / samples.size());
    }
    t_particleDiagnostics.particlePosteriorRows.push_back(g);   // group summary row first
    ++t_particleDiagnostics.particlePosteriorGroups;
    if (g_particlePosteriorAgeSplit)
        t_particleDiagnostics.particlePosteriorAgeBins[ageStratum][ageBin] = true;
    for (int ordinal = 0; ordinal < (int)order.size(); ++ordinal) {
        const auto &c = compatible[order[ordinal]];
        BattleContext state = c.state;   // exact full leaf world, draw order + 6 RNG streams preserved
        std::mt19937_64 diagnosticRng(rngSeed);   // same CRN seed across worlds within this group
        std::vector<search::Action> actions;
        double target = std::numeric_limits<double>::quiet_NaN();
        bool terminal = false;
        const int steps = d.searcher->diagnosticRollout(state, actions, diagnosticRng,
                                                        target, terminal);
        ParticlePosteriorProbeRow w = g;   // repeat source-group metadata on every world row
        w.rowType = 1;
        w.candidateParticleIndex = c.rootIndex;
        w.candidateWeight = c.weight;
        w.candidateIsSource = c.source ? 1 : 0;
        w.dedupOrdinal = ordinal;
        w.rngSignature = posteriorProbeRngSignature(c.key);
        w.drawOrder = particleLeafDrawOrder(c.state);
        w.rolloutSteps = steps;
        w.terminal = terminal ? 1 : 0;
        w.target = target;
        const auto controlledIt = controlled.find(c.key.drawPileOrder);
        if (controlledIt != controlled.end()) {
            w.controlledTarget = controlledIt->second.mean;
            w.controlledTargetStd = controlledIt->second.std;
        }
        t_particleDiagnostics.particlePosteriorRows.push_back(std::move(w));
    }
}



static std::string particlePosteriorProbeHeaderStr() {
    return "rowType,seed,fightIdx,decIdx,sourceLeafId,obsHash,treeDepth,encounterName,turn,"
           "curHp,maxHp,drawPileSize,rootParticleCount,positiveParticleCount,replayAttempted,"
           "replayCompatibleParticles,uniqueCompatibleStates,compatibleMass,evaluatedWorldCount,"
           "evaluatedMass,sourceParticleIndex,sourceParticleReplayOk,sourceParticleFallback,"
           "groupEligible,invariantOk,replayFailure,semanticReplayFailures,actionIllegalFailures,"
           "intermediateObservationMismatches,intermediateOutcomeMismatches,finalObservationMismatches,"
           "drawPileMismatches,firstMismatchCheckpoint,expectedMismatchHash,actualMismatchHash,mismatchActionBits,"
           "rootCarried,reuseGeneration,reuseSearchCount,searchSimulation,ageStratum,ageBin,candidateParticleIndex,"
           "candidateWeight,candidateIsSource,dedupOrdinal,semanticBranchesCreated,extraSemanticBranches,maxSurvivingBranches,"
           "branchesCollapsed,replayExplosion,rngSignature,drawOrder,terminal,target,"
           "fullTarget,controlledTarget,controlledTargetStd,rolloutSteps";
}

static std::string particlePosteriorProbeSeedCsv() {
    std::ostringstream o;
    for (const auto &r : t_particleDiagnostics.particlePosteriorRows) {
        o << r.rowType << ',' << r.seed << ',' << r.fightIdx << ',' << r.decIdx << ','
          << r.sourceLeafId << ',' << r.obsHash << ',' << r.treeDepth << ',' << r.encounter << ','
          << r.turn << ',' << r.curHp << ',' << r.maxHp << ',' << r.drawPileSize << ','
          << r.rootParticleCount << ',' << r.positiveParticleCount << ',' << r.replayAttempted << ','
          << r.replayCompatibleParticles << ',' << r.uniqueCompatibleStates << ','
          << r.compatibleMass << ',' << r.evaluatedWorldCount << ',' << r.evaluatedMass << ','
          << r.sourceParticleIndex << ',' << r.sourceParticleReplayOk << ','
          << r.sourceParticleFallback << ',' << r.groupEligible << ',' << r.invariantOk << ','
          << (r.replayFailure.empty() ? std::string("-") : r.replayFailure) << ','
          << r.semanticReplayFailures << ',' << r.actionIllegalFailures << ','
          << r.intermediateObservationMismatches << ',' << r.intermediateOutcomeMismatches << ','
          << r.finalObservationMismatches << ',' << r.drawPileMismatches << ','
          << r.firstMismatchCheckpoint << ',' << r.expectedMismatchHash << ','
          << r.actualMismatchHash << ',' << r.mismatchActionBits << ','
          << r.rootCarriedFlag << ',' << r.reuseGeneration << ',' << r.reuseSearchCount << ','
          << r.searchSimulation << ',' << r.ageStratum << ',' << r.ageBin << ','
          << r.candidateParticleIndex << ',' << r.candidateWeight << ','
          << r.candidateIsSource << ',' << r.dedupOrdinal << ',' << r.semanticBranchesCreated << ','
          << r.extraSemanticBranches << ','
          << r.maxSurvivingBranches << ',' << r.branchesCollapsed << ',' << r.replayExplosion << ','
          << r.rngSignature << ','
          << '"' << r.drawOrder << '"' << ',' << r.terminal << ',' << r.target << ','
          << r.target << ',' << r.controlledTarget << ',' << r.controlledTargetStd << ','
          << r.rolloutSteps << '\n';
    }
    return o.str();
}

static void recordPosteriorSearchFingerprint(
    const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    int best = -1;
    std::int64_t visits = -1;
    for (int i = 0; i < (int)s3.root.edges.size(); ++i) {
        const auto count = s3.root.edges[i].child.simulationCount;
        if (count > visits) { visits = count; best = i; }
    }
    const int decision = t_particleDiagnostics.decIdx;
    std::ostringstream row;
    row << t_particleDiagnostics.seed << ':' << decision << ':'
        << sts::CombatObservation::fromBattleContext(bc).visibleHash() << ':'
        << (best >= 0 ? s3.root.edges[best].action.bits : 0xffffffffu) << ':'
        << visits << ';';
    t_particleDiagnostics.actionFingerprint += row.str();

    if (g_particlePosteriorAgeSplit && t_particleDiagnostics.fightIdx == 0 && decision == 0) {
        for (int stratum = 0; stratum < 2; ++stratum) {
            t_particleDiagnostics.particlePosteriorAgeSelected[stratum] =
                particlePosteriorAgeSelectEvenly(
                    t_particleDiagnostics.particlePosteriorAgeCandidates[stratum]);
            for (int rank = 0; rank < (int)t_particleDiagnostics.particlePosteriorAgeSelected[stratum].size(); ++rank) {
                const int ordinal = t_particleDiagnostics.particlePosteriorAgeSelected[stratum][rank];
                auto it = std::find_if(
                    t_particleDiagnostics.particlePosteriorAgeCandidates[stratum].begin(),
                    t_particleDiagnostics.particlePosteriorAgeCandidates[stratum].end(),
                    [ordinal](const ParticlePosteriorAgeCandidate &candidate) {
                        return candidate.ordinal == ordinal;
                    });
                if (it == t_particleDiagnostics.particlePosteriorAgeCandidates[stratum].end()) continue;
                auto diagnostic = it->diagnostic;
                diagnostic.searcher = const_cast<search::BattleScumSearcher3 *>(&s3);
                diagnostic.bc = &it->state;
                particlePosteriorProbeOnLeafQuery(diagnostic);
            }
        }
        t_particleDiagnostics.particlePosteriorAgeCandidates[0].clear();
        t_particleDiagnostics.particlePosteriorAgeCandidates[1].clear();
    }
    ++t_particleDiagnostics.decIdx;
}
void configureParticleDiagnosticsFromEnvironment() {
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_FILE"))
        g_particleLeafProbeFile = d;
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_K")) {
        const int k = std::atoi(d); if (k >= 1) g_particleLeafProbeK = k;
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_RATE")) {
        g_particleLeafProbeRate = std::atof(d);
        g_particleLeafProbeRate = std::max(0.0, std::min(1.0, g_particleLeafProbeRate));
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_MAX_GROUPS")) {
        const int n = std::atoi(d); if (n >= 0) g_particleLeafProbeMaxGroups = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_FILE"))
        g_particlePosteriorProbeFile = d;
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_K")) {
        const int k = std::atoi(d); if (k >= 0) g_particlePosteriorProbeK = k;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_MAX_GROUPS")) {
        const int n = std::atoi(d); if (n >= -1) g_particlePosteriorProbeMaxGroups = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_SPLIT"))
        g_particlePosteriorAgeSplit = std::atoi(d) != 0;
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_EARLY_START"))
        g_particlePosteriorAgeEarlyStart = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_EARLY_END"))
        g_particlePosteriorAgeEarlyEnd = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_LATE_START"))
        g_particlePosteriorAgeLateStart = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_LATE_END"))
        g_particlePosteriorAgeLateEnd = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_MIN_PER_STRATUM"))
        g_particlePosteriorAgeMinPerStratum = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_PER_STRATUM"))
        g_particlePosteriorAgePerStratum = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_DEBUG_FILE"))
        g_particlePosteriorReplayDebugFile = d;
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_CEILING")) {
        const int n = std::atoi(d); if (n >= 1) g_particlePosteriorReplayCeiling = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_TRACE_FILE"))
        g_particlePosteriorReplayTraceFile = d;
}

bool particleDiagnosticsActive() {
    return g_particleDiagnosticsActive;
}

void beginParticleDiagnosticFight(std::uint64_t seed, int fightIdx, int floor,
                                  int act, sts::MonsterEncounter encounter) {
    if (!g_particleDiagnosticsActive) return;
    t_particleDiagnostics.seed = seed;
    t_particleDiagnostics.fightIdx = fightIdx;
    t_particleDiagnostics.floor = floor;
    t_particleDiagnostics.act = act;
    t_particleDiagnostics.encounter = monsterEncounterEnumNames[(int)encounter];
    t_particleDiagnostics.decIdx = 0;
}

int particleDiagnosticStratum(const sts::BattleContext &bc, int depth) {
    return particleDiagnosticStratumImpl(bc, depth);
}

int particleDiagnosticStrataCount() {
    return kParticleDiagnosticStrata;
}

void startParticleLeafProbe(const std::string &outputFile) {
    if (g_particleLeafProbeFile.empty()) g_particleLeafProbeFile = outputFile;
    g_particleDiagnosticsActive = true;
}

void installParticleLeafProbeHooks(std::uint64_t seed) {
    search::g_onS3LeafQuery = particleLeafProbeOnLeafQuery;
    search::g_onSearchComplete3 = [](const BattleContext &,
                                     const search::BattleScumSearcher3 &) {
        ++t_particleDiagnostics.decIdx;
    };
    t_particleDiagnostics.init(seed);
}

std::string finishParticleLeafProbeSeed() {
    const std::string out = particleLeafProbeSeedCsv();
    search::g_onS3LeafQuery = nullptr;
    search::g_onSearchComplete3 = nullptr;
    return out;
}

std::string particleLeafProbeHeader() {
    return particleLeafProbeHeaderStr();
}

int particleLeafProbeK() {
    return g_particleLeafProbeK;
}

double particleLeafProbeRate() {
    return g_particleLeafProbeRate;
}

int particleLeafProbeMaxGroups() {
    return g_particleLeafProbeMaxGroups;
}

bool startParticlePosteriorProbe(const std::string &outputFile) {
    if (g_particlePosteriorAgeSplit
        && (g_particlePosteriorAgeMinPerStratum < 1
            || g_particlePosteriorAgeMinPerStratum > 16
            || g_particlePosteriorAgePerStratum != 16
            || g_particlePosteriorAgeEarlyEnd < g_particlePosteriorAgeEarlyStart
            || g_particlePosteriorAgeLateEnd < g_particlePosteriorAgeLateStart)) {
        std::cerr << "particle_posterior_probe: invalid age-split configuration; "
                     "require 16 bins and ascending windows\n";
        return false;
    }
    if (g_particlePosteriorProbeFile.empty()) g_particlePosteriorProbeFile = outputFile;
    g_particleDiagnosticsActive = true;
    return true;
}

void installParticlePosteriorProbeHooks(std::uint64_t seed) {
    search::g_s3LeafTraceActions = true;
    search::g_onSearchComplete3 = recordPosteriorSearchFingerprint;
    search::g_onS3LeafQuery = g_particlePosteriorAgeSplit
        ? particlePosteriorAgeCaptureOnLeafQuery
        : particlePosteriorProbeOnLeafQuery;
    t_particleDiagnostics.init(seed);
}

std::string finishParticlePosteriorProbeSeed() {
    const std::string out = particlePosteriorProbeSeedCsv();
    search::g_onS3LeafQuery = nullptr;
    search::g_s3LeafTraceActions = false;
    search::g_onSearchComplete3 = nullptr;
    return out;
}

std::string particlePosteriorProbeHeader() {
    return particlePosteriorProbeHeaderStr();
}

std::string particlePosteriorActionFingerprint() {
    return t_particleDiagnostics.actionFingerprint;
}

int particlePosteriorProbeK() {
    return g_particlePosteriorProbeK;
}

int particlePosteriorProbeMaxGroups() {
    return g_particlePosteriorProbeMaxGroups;
}

void stopParticleDiagnostics() {
    g_particleDiagnosticsActive = false;
    search::g_onS3LeafQuery = nullptr;
    search::g_s3LeafTraceActions = false;
    search::g_onSearchComplete3 = nullptr;
}

} // namespace one_combat
