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
                                            const Action &a, const BattleContext &xa, BattleContext &scratch,
                                            bool relax = false);

    // Round 2 (#1057): STS_SILVER_ORDER_DOMINANCE is a bit mask of these rules (1 = the round-1 order test).
    enum : unsigned {
        DOM_SWAP = 1u,       // a at X (reached by b from P) dominated by a-then-b from P
        DOM_RELAX = 2u,      // comparison mode for every rule: more player block, less monster block, more energy
        DOM_END_ADJ = 4u,    // End Turn at X dominated by "card c, then End Turn" (end states compared)
        DOM_SEG_STATE = 8u,  // decision node dominated by another decision node of the same deterministic segment
        DOM_SEG_END = 16u,   // End Turn at X dominated by End Turn at another node of the same segment
        DOM_ROOT = 32u,      // searchGumbelRoot drops the root's End Turn from the candidates when DOM_END_ADJ flags it
        DOM_ALL = 63u,
    };

    // Comparison mode. relax: player block may be higher, monster block lower and (at a decision) energy higher in
    // `better`. endState: both states are end-of-turn states (endOfTurnState); energy and the per-turn card counters
    // are reset before the player acts again, so they are ignored (not with Ice Cream, Pocketwatch or Art of War).
    struct DominanceCompare {
        bool relax = false;
        bool endState = false;
    };

    // Player-side payoffs for taking damage or for low HP, which break "more block is better": Red Skull,
    // Centennial Puzzle, Runic Cube, Self-Forming Clay, Emotion Chip, Meat on the Bone, Static Discharge and
    // Blood for Blood in any pile. With one of them, DOM_RELAX compares block as equal.
    bool relaxGuarded(const BattleContext &bc);

    // `better` dominates `worse` under `mode`: the same monsters alive (and half dead), no monster HP higher, under
    // relax no monster block higher, no player block or energy lower; at least one of these strictly better; and the
    // states equalForSearch once those fields are copied from `worse`.
    bool dominatesState(const BattleContext &better, const BattleContext &worse, DominanceCompare mode);

    // The state after End Turn at the decision `x`, stopped before the first monster acts (end-of-turn relics and
    // powers, hand discard and the monsters' pre-turn block loss have run; no draw, no move roll). False when `x`
    // is not a quiet decision or the end of turn consumed search randomness.
    bool endOfTurnState(const BattleContext &x, BattleContext &out);

    // Bucket key for the segment tables: hashBattleState with the fields dominatesState may compare unequally
    // zeroed (monster HP and block, player block, energy; end-state per-turn counters).
    std::size_t dominanceKey(const BattleContext &bc, DominanceCompare mode, BattleContext &scratch);

}

#endif //STS_LIGHTSPEED_SILVERDOMINANCE_H
