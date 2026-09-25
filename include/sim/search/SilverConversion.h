// Explicit live-observation to isolated-Silver conversion helpers.
#ifndef STS_SILVER_CONVERSION_H
#define STS_SILVER_CONVERSION_H

#include <string>
#include <vector>

#include "combat/CardInstance.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverBridge.h"
#include "combat/CardPile.h"

namespace sts {
    class BattleContext;
    class GameContext;

namespace search {

// This is the draw-pile portion of the live->Silver boundary. It deliberately
// has no reference to an index in the live vector and contains no live RNG.
// In the normal case unknown is canonicalized as a multiset. Only a legitimate
// full-order observation (Frozen Eye) may preserve the live vector order.
struct SilverDrawPileObservation {
    std::vector<CardInstance> knownBottom;
    std::vector<CardInstance> unknown;
    std::vector<CardInstance> knownTop;
    bool fullOrderObserved = false;
    bool valid = true;
};

// Explicit legitimate run context for Silver fields that are not retained by
// the live BattleContext.  This value is intentionally small and public-only.
struct SilverRunContext {
    int act = 1;
    bool omamoriOwned = false;
    int omamoriValue = 0;
};

// Fail-closed conversion result for diagnostics at the live boundary. The
// reason names only public observer state and never includes live RNG values,
// draw-pile positions, or a materialized hidden monster move.
struct SilverBattleStateConversion {
    silver_bridge::BattleStateWire wire;
    std::string failureReason;
};

SilverRunContext makeSilverRunContext(const GameContext &live);

SilverDrawPileObservation makeSilverDrawPileObservation(
    const BattleContext &live, const CombatKnowledgeState &knowledge);

// The search draw pile for the sanitized observation: the information set, or
// the concrete order under Frozen Eye.
CardPile makeSilverCardPile(const BattleContext &live,
                                   const CombatKnowledgeState &knowledge);

// Runic Dome hides intent from the player. Callers must use this gate before
// copying any monster move field into the isolated Silver model.
bool liveMonsterIntentIsObservable(const BattleContext &live);

bool sameSilverDrawPileObservation(const SilverDrawPileObservation &a,
                                   const SilverDrawPileObservation &b);

// Complete value-only conversion protocol. It copies no live RNG state and
// redacts materialized intent under Runic Dome. `isolatedSearchSeed` is a
// stable public per-battle seed for the independent Silver model, never a
// live BattleContext RNG state.
silver_bridge::BattleStateWire makeSilverBattleStateWire(
    const BattleContext &live, const CombatKnowledgeState &knowledge,
    const SilverRunContext &runContext, std::uint64_t isolatedSearchSeed);

SilverBattleStateConversion makeSilverBattleStateConversion(
    const BattleContext &live, const CombatKnowledgeState &knowledge,
    const SilverRunContext &runContext, std::uint64_t isolatedSearchSeed);

} // namespace search
} // namespace sts

#endif
