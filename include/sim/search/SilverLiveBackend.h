// Default-off executable integration for the isolated Silver combat model.
#ifndef STS_SILVER_LIVE_BACKEND_H
#define STS_SILVER_LIVE_BACKEND_H

#include <cstdint>

namespace sts::search {

struct SilverLiveDiagnostics {
    std::uint64_t conversionFailures = 0;
    std::uint64_t semanticResolutionFailures = 0;
    std::uint64_t transactionFailures = 0;
    std::uint64_t knowledgeConsistencyFailures = 0;
    std::uint64_t decisions = 0;
    std::uint64_t simulations = 0;
    std::uint64_t transactionSubdecisions = 0;
    std::uint64_t rerootExact = 0;
    std::uint64_t rerootFallback = 0;
    std::uint64_t nodesCreated = 0;
    std::uint64_t deterministicTranspositions = 0;
    std::uint64_t chanceOutcomes = 0;
    std::uint64_t chanceSiblingReuse = 0;
    std::uint64_t chanceTranspositions = 0;
    std::uint64_t wideningSampled = 0;
    std::uint64_t wideningCapped = 0;
    std::uint64_t depthSum = 0;
    std::uint64_t chanceDepthSum = 0;
};

extern thread_local SilverLiveDiagnostics g_silverLiveDiagnostics;

// Installs the private-model combat callback into the core agent. This symbol
// is linked only by one_combat; other executables retain no full-vendor-model
// dependency. Calling it is idempotent for the current thread.
void installSilverLiveBackend();
void uninstallSilverLiveBackend();

} // namespace sts::search

#endif
