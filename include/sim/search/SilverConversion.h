// Explicit live-observation to isolated-Silver conversion helpers.
#ifndef STS_SILVER_CONVERSION_H
#define STS_SILVER_CONVERSION_H

#include <vector>

#include "combat/CardInstance.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverBridge.h"
#include "silver/CardPile.h"

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

SilverRunContext makeSilverRunContext(const GameContext &live);

SilverDrawPileObservation makeSilverDrawPileObservation(
    const BattleContext &live, const CombatKnowledgeState &knowledge);

// Constructs the isolated model's actual Silver CardPile from the sanitized
// observation. This function is the only draw-pile path from live combat into
// the Silver model.
silver::CardPile makeSilverCardPile(const BattleContext &live,
                                   const CombatKnowledgeState &knowledge);

// Runic Dome hides intent from the player. Callers must use this gate before
// copying any monster move field into the isolated Silver model.
bool liveMonsterIntentIsObservable(const BattleContext &live);

bool sameSilverDrawPileObservation(const SilverDrawPileObservation &a,
                                   const SilverDrawPileObservation &b);

// Complete value-only conversion protocol. It copies no live RNG state and
// redacts materialized intent under Runic Dome. `isolatedSearchSeed` belongs
// to the caller's independent Silver search contract, never BattleContext.
silver_bridge::BattleStateWire makeSilverBattleStateWire(
    const BattleContext &live, const CombatKnowledgeState &knowledge,
    const SilverRunContext &runContext, std::uint64_t isolatedSearchSeed);

} // namespace search
} // namespace sts

#endif
