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

// Canonical policy features score exact Silver-enumerated actions in restored
// internal states.  The main simulator can disagree about legality at this
// isolated boundary (notably private selections and potion timing), but the
// compatible Action encoding is still required by combatExtractPolicyFeatures.
SemanticActionResolution resolveSilverSemanticActionForPolicyFeatures(
        const BattleContext &restored, const silver_bridge::SemanticAction &semantic);

} // namespace search
} // namespace sts

#endif
