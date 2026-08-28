// Default-off executable integration for the isolated Silver combat model.
#ifndef STS_SILVER_LIVE_BACKEND_H
#define STS_SILVER_LIVE_BACKEND_H

#include <cstdint>
#include <string>
#include <vector>

#include "sim/search/SilverBridge.h"

namespace sts::search {

struct SilverLiveDiagnostics {
    std::uint64_t conversionFailures = 0;
    std::uint64_t semanticResolutionFailures = 0;
    std::uint64_t transactionFailures = 0;
    std::uint64_t knowledgeConsistencyFailures = 0;
    std::uint64_t decisions = 0;
    std::uint64_t simulations = 0;
    std::uint64_t transactionSubdecisions = 0;
    std::uint64_t adaptiveEscalations = 0;
    std::uint64_t rerootExact = 0;
    std::uint64_t rerootFallback = 0;
    std::uint64_t rerootCandidateFound = 0;
    std::uint64_t rerootCandidateMissing = 0;
    std::uint64_t rerootAllocatedCapBlocked = 0;
    std::uint64_t rerootActiveCapBlocked = 0;
    std::uint64_t nodesCreated = 0;
    std::uint64_t deterministicTranspositions = 0;
    std::uint64_t chanceOutcomes = 0;
    std::uint64_t chanceSiblingReuse = 0;
    std::uint64_t chanceTranspositions = 0;
    std::uint64_t wideningSampled = 0;
    std::uint64_t wideningCapped = 0;
    std::uint64_t depthSum = 0;
    std::uint64_t chanceDepthSum = 0;
    std::uint64_t rolloutSkippedVNet = 0;
    std::uint64_t rolloutCalls = 0;
    std::uint64_t blendEligibleLeaves = 0;
    std::uint64_t blendInvocations = 0;
    std::uint64_t blendDepthAvoided = 0;
    std::uint64_t leafVNetInferenceCalls = 0;
    std::uint64_t leafVNetInferenceMicros = 0;
    std::uint64_t policyModelInferenceCalls = 0;
    std::uint64_t policyModelInferenceMicros = 0;
    std::uint64_t policyScoredDecisionNodes = 0;
    std::uint64_t policyLegalActions = 0;
    std::uint64_t policyPuctSelections = 0;
    std::uint64_t policyFirstExpandedLearnedTop = 0;
    std::uint64_t policyActionAlignmentFailures = 0;
    // Default-off test trace.  It is never populated in production runs.
    std::vector<std::string> actionFingerprints;
};

extern thread_local SilverLiveDiagnostics g_silverLiveDiagnostics;

// Installs the private-model combat callback into the core agent. This symbol
// is linked only by one_combat; other executables retain no full-vendor-model
// dependency. Calling it is idempotent for the current thread.
void installSilverLiveBackend();
void uninstallSilverLiveBackend();

// Effective process-level options parsed by installSilverLiveBackend().  They
// are exposed to one_combat provenance only; no live combat object crosses
// this boundary.
bool silverLiveBackendInstalled();
std::string silverLiveReuseCapMode();
std::int64_t silverLiveReuseCap();
std::string silverLiveScalingDiagnosticFile();
std::string silverLiveStickyQualityFile();
bool silverLiveAdaptiveEnabled();
bool silverLiveExactRootBudgets();
double silverLiveAdaptiveTopTwoVisitGapThreshold();
bool silverLivePolicyOrderingEnabled();
bool silverLivePolicyPuctEnabled();
double silverLivePolicyCpuct();
std::string silverLivePolicyModelPath();

// Stable deterministic sampler used only by STS_SILVER_STICKY_QUALITY_FILE.
// It hashes the documented public decision identity and consumes no RNG.
bool silverStickyQualitySampled(std::uint64_t runSeed, int floor, int encounter,
                                int combatDecisionOrdinal);

// Focused-test-only controls.  They have no environment variable and are
// ignored unless a test explicitly sets all three positive budgets.
void setSilverStickyQualityTestBudgetsForTest(std::int64_t fresh,
                                              std::int64_t ref25,
                                              std::int64_t ref50);
void setSilverLiveActionTraceForTest(bool enabled);

// Focused parity-test seam: project one public Silver wire state back into a
// live BattleContext and run the canonical combat VNet feature extractor.
double silverLiveLeafVNetPredictionForTest(
    const silver_bridge::BattleStateWire &wire, const std::string &modelPath);

// Project a stored Silver wire through the same live-state adapter and
// canonical rich CombatValueNet feature extractor used by deployment.
std::vector<float> silverLiveLeafCanonicalFeatures(
    const silver_bridge::BattleStateWire &wire);

struct SilverPolicyFeatureRow {
    std::string actionFingerprint;
    std::vector<float> features;
    // Zero-based position in the exact current Silver root-edge ordering.
    int silverOrder = -1;
};

// Restore one parent through the live-state bridge, enumerate the exact
// pinned-Silver legal actions, lower each semantic identity to the live
// action, and extract the canonical state+action policy feature vector.
// Any duplicate or unresolvable identity throws; partial rows are never
// returned.
std::vector<SilverPolicyFeatureRow> silverLiveParentPolicyFeatures(
    const silver_bridge::BattleStateWire &wire);

} // namespace sts::search

#endif
