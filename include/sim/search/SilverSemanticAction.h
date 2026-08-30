// Semantic-action lowering at the isolated Silver / live sts_ai boundary.
#ifndef STS_SILVER_SEMANTIC_ACTION_H
#define STS_SILVER_SEMANTIC_ACTION_H

#include <string>

#include "sim/search/Action.h"
#include "sim/search/SilverBridge.h"

namespace sts {
struct BattleContext;

namespace search {

struct SemanticActionResolution {
    bool ok = false;
    Action action {};
    std::string error;
};

// Resolves a value identity against the live state. A raw Silver index is
// never accepted. Ambiguous/missing/non-legal actions fail closed with a
// diagnostic instead of selecting based on hidden vector layout.
SemanticActionResolution resolveSilverSemanticAction(
    const BattleContext &live, const silver_bridge::SemanticAction &semantic);

// Lowers a selected Silver root edge for live execution. Most action surfaces
// preserve their packed Action bits exactly. Pile-selection roots are the one
// exception: Silver deliberately canonicalizes hidden pile order, so their
// state-local index is translated by the selected card identity. This is an
// explicit boundary rule, not a legality-triggered fallback.
SemanticActionResolution resolveSilverSelectedAction(
    const BattleContext &live, const silver_bridge::SemanticAction &semantic,
    std::uint32_t selectedActionBits);

} // namespace search
} // namespace sts

#endif
