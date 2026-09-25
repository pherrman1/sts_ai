// Lowers an index-free Silver semantic action to a live search::Action.
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

} // namespace search
} // namespace sts

#endif
