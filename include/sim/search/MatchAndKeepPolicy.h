#ifndef STS_LIGHTSPEED_MATCH_AND_KEEP_POLICY_H
#define STS_LIGHTSPEED_MATCH_AND_KEEP_POLICY_H

#include <functional>

#include "game/Card.h"
#include "game/GameContext.h"

namespace sts::search {

// Fixed-pattern Match and Keep click policy. It is public-information only:
// a slot's card is read only after that slot has been flipped (seen or face
// up), never from the simulator's hidden layout. `wantCard` answers whether
// the active OOC guide would add the card to the deck.
//
// First click: open a seen pair of a wanted card, else flip the lowest unseen
// slot, else the lowest remaining slot. Second click: complete the pair when
// the card is wanted (its known twin, else the lowest unseen slot); otherwise
// decline with a seen slot that holds a different card, falling back to the
// lowest unseen slot only when no such slot exists.
int chooseMatchAndKeepSlot(const GameContext &gc, const std::function<bool(const Card &)> &wantCard);

} // namespace sts::search

#endif
