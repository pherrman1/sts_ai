// Conversions between the live->Silver wire protocol (SilverBridge.h) and the
// main engine, for running Silver search natively on a wire state.
#ifndef STS_SILVER_WIRE_STATE_H
#define STS_SILVER_WIRE_STATE_H

#include <string>

#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSearcher.h"

namespace sts::search {

    // A search root for SilverSearcher built from a wire state: the draw pile
    // is the wire's information set (concrete when its full order is
    // observed), discard and exhaust piles hold the wire's cards, the RNG
    // streams are seeded from the wire's public search seed, and under Runic
    // Dome the monsters carry the wire's pending (unrolled) intents. Throws
    // std::invalid_argument for an invalid or incompatible wire.
    BattleContext battleContextFromWire(const silver_bridge::BattleStateWire &wire);

    // Export the bounded typed tail only when every queued action is
    // representable; otherwise retain the historical unobserved contract.
    void capturePendingActionQueue(const BattleContext &state, silver_bridge::BattleStateWire &wire);

    // The run context the wire carries for Silver's terminal evaluation.
    SilverSearchContext searchContextFromWire(const silver_bridge::BattleStateWire &wire);

    // The wire view of a search state (used for inspection output). The draw
    // pile keeps its information-set split.
    silver_bridge::BattleStateWire wireFromSearchState(const BattleContext &state,
                                                      const SilverSearchContext &context);

    // Index-free identity of `action` taken in `state`. Throws
    // std::runtime_error for an action whose indices do not fit `state`.
    silver_bridge::SemanticAction semanticFromSearchAction(const BattleContext &state,
                                                           const Action &action);

    // Stable text identity of a semantic action (the format of earlier
    // advisor captures).
    std::string semanticFingerprint(const silver_bridge::SemanticAction &action);

}

#endif
