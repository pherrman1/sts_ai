#ifndef STS_LIGHTSPEED_SILVERDOMINANCE_H
#define STS_LIGHTSPEED_SILVERDOMINANCE_H

#include <cstdint>

#include "combat/BattleContext.h"
#include "sim/search/Action.h"

// Research (#1057, STS_SILVER_ORDER_DOMINANCE, default off): dominance of card-play orders, after
// tfriedel/spire-mentor's sts2-mcts dominance.rs. At a search node X reached from P by card play b, a card play a at X
// is dominated when playing a before b at P reaches a state that is equal for search to X + a except that no monster
// has more HP and at least one has less. Player HP and block must be equal (relic and power payoffs break
// "more is better"). The same monsters must be alive, so kills (death triggers, Feed, Gremlin Horn, ...) never
// differ. The test is off while a monster whose AI reads monster HP is alive (orderDominanceGuarded).
//
// Soundness (exact values): P + a + b stays reachable from the search root (P is on the path), so removing X + a
// never removes the best line; chains of prunings end at the root, which is never pruned.

namespace sts::search {

    // Monsters whose AI reads monster HP so that lower HP need not be better: the Mystic heals on its own and its
    // Centurion's missing HP; the Champ and Time Eater change phase below half HP at their next move roll. Slime
    // splits, Guardian mode shift, Shifting and other on-damage reactions change the state at once and fail the
    // equality test instead.
    bool orderDominanceGuarded(const BattleContext &bc);

    // `better` dominates `worse`: the same monsters alive, every monster's HP in `better` at most its HP in
    // `worse` and at least one strictly lower, and the two states equalForSearch once those HP are made equal.
    bool dominatesByMonsterHp(const BattleContext &better, const BattleContext &worse);

    // Card play `a` (indices on `from`) re-expressed on `to`: the same card (exact copy first, then a copy
    // equivalent for search) and target. Action() (bits ~0u) when `a` is not a card play or `to` lacks the card.
    Action sameCardPlayOn(const Action &a, const BattleContext &from, const BattleContext &to);

    // Plays card action `a` on `bc` when `bc` is an undecided PLAYER_NORMAL decision, the card is playable there on
    // its target, and the play consumes no search randomness (SearchRng counter, as Silver's chance nodes). Returns
    // false otherwise (`bc` is then unspecified: pass a copy). The RNG streams are restored after the play.
    bool playDeterministicCard(BattleContext &bc, const Action &a);

    enum class OrderDominanceResult : std::uint8_t {
        NOT_DOMINATED,
        DOMINATED,
        SKIPPED,   // not testable: a or b not a deterministic card play here, or the cards cannot be swapped
    };

    // P --b--> X with b a deterministic card play; `xa` = X + a (the caller's copy). Plays a then b from P and
    // compares with `xa`. `scratch` is a work copy.
    OrderDominanceResult testOrderDominance(const BattleContext &p, const Action &b, const BattleContext &x,
                                            const Action &a, const BattleContext &xa, BattleContext &scratch);

}

#endif //STS_LIGHTSPEED_SILVERDOMINANCE_H
