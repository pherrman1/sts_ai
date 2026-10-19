//
// Created by gamerpuppy on 7/24/2021.
//

#include "combat/CardManager.h"
#include "combat/BattleContext.h"

#include "game/GameContext.h"
#include "game/Card.h"

#include "sim/search/CombatKnowledge.h"

#include <algorithm>

using namespace sts;

namespace {
    // Java resetAttributes when a card lands in a pile (STS_PILE_COST_RESET_FIX).
    CardInstance landed(CardInstance c) {
        if (c.costForTurn != c.cost && pileCostResetFix()) c.costForTurn = c.cost;
        return c;
    }
}

void CardManager::init(const sts::GameContext &gc, BattleContext &bc) {

//    masterDeckSize = gc.deck.size();
    nextUniqueCardId = gc.deck.size();
    handPainCount = false;
    handNormalityCount = false;
    strikeCount = 0;

    fixed_list<int, Deck::MAX_SIZE> idxs(gc.deck.size());
    for (int i = 0; i < idxs.size(); ++i) {
        idxs[i] = i;
    }
    java::Collections::shuffle(idxs.begin(), idxs.end(), java::Random(bc.shuffleRng.randomLong()));

    drawPile.concreteCards().resize(gc.deck.size());
    discardPile.clear();
    exhaustPile.clear();

    int normalCount = 0;
    bool isInnateMemo[Deck::MAX_SIZE];

    for (int i = 0; i < gc.deck.size(); ++i) {
        const int deckIdx = idxs[i];
        const auto &deckCard = gc.deck.cards[deckIdx];
//        if (deckCard.isStrikeCard()) { ++strikeCount; } do at createDeckCardInstanceInDrawPile

        bool isBottled = std::find(gc.deck.bottleIdxs.begin(), gc.deck.bottleIdxs.end(), deckIdx) != gc.deck.bottleIdxs.end();
        isInnateMemo[i] = deckCard.isInnate() || isBottled;

        if (!isInnateMemo[i]) {
            ++normalCount;
        }
    }

    int normalIdx = 0;
    int innateIdx = normalCount;

    for (int i = 0; i < gc.deck.size(); ++i) {
        const int deckIdx = idxs[i];
        const auto &deckCard = gc.deck.cards[deckIdx];

        if (isInnateMemo[i]) {
            createDeckCardInstanceInDrawPile(deckCard, deckIdx, innateIdx);
            ++innateIdx;
        } else {
            createDeckCardInstanceInDrawPile(deckCard, deckIdx, normalIdx);
            ++normalIdx;
        }
    }

    int innateCount =  innateIdx - normalCount;
    if (innateCount  > bc.player.cardDrawPerTurn) {
        bc.addToBot( Actions::DrawCards(innateCount-bc.player.cardDrawPerTurn) );
    }
}

void CardManager::createDeckCardInstanceInDrawPile(const Card &card, int deckIdx, int drawIdx) {
    auto &c = drawPile.concreteCards()[drawIdx];
    c = CardInstance(card);
    c.setUniqueId(deckIdx);
#ifdef sts_asserts
    if (card.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to create invalid deck instance in draw pile" << std::endl;
        assert(false);
    }
#endif
    notifyAddCardToCombat(c);
    notifyAddToDrawPile(c);
}

void CardManager::createTempCardShuffledIntoDrawPile(Random &cardRandomRng, CardInstance c) {
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to create invalid card in draw pile" << std::endl;
        assert(false);
    }
#endif

    c.uniqueId = static_cast<std::int16_t>(nextUniqueCardId++);
    notifyAddCardToCombat(c);
    notifyAddToDrawPile(c);
    drawPile.shuffleIn(cardRandomRng, c);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT, c);
}

void CardManager::createTempCardOnDrawPileTop(CardInstance c) {
    c.uniqueId = static_cast<std::int16_t>(nextUniqueCardId++);
    notifyAddCardToCombat(c);
    // A created card is added straight to the pile and keeps its cost.
    notifyAddToDrawPile(c);
    drawPile.addToTop(c);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::KNOWN_TOP_PLACED, c);
}

void CardManager::createTempCardInDiscard(CardInstance c) {
    c.uniqueId = static_cast<std::int16_t>(nextUniqueCardId++);
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to create invalid card in discard" << std::endl;
        assert(false);
    }
#endif
    notifyAddCardToCombat(c);
    notifyAddToDiscardPile(c);
    discardPile.push_back(c);
}

void CardManager::createTempCardInHand(CardInstance c) {
    c.uniqueId = static_cast<std::int16_t>(nextUniqueCardId++);
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to create invalid card in hand" << std::endl;
        assert(false);
    }
#endif
    notifyAddCardToCombat(c);
    notifyAddToHand(c);
    hand[cardsInHand++] = c;
}

// **************** START Remove Methods ****************

void CardManager::removeFromDrawPileAtIdx(int idx) {
    const CardInstance c = drawPile[idx];
    notifyRemoveFromDrawPile(c);
    drawPile.removeAt(idx);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::DRAW_PILE_CARD_REMOVED, c);
}

CardInstance CardManager::popFromDrawPile(Random &shuffleRng) {
    const auto c = drawPile.drawTop(shuffleRng);
    notifyRemoveFromDrawPile(c);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::DRAW_OCCURRED, c);
    return c;
}

void CardManager::removeFromHandAtIdx(int idx) {
    notifyRemoveFromHand(hand[idx]);
    eraseAtIdxInHand(idx);
}

void CardManager::removeFromHandById(std::uint16_t uniqueId) {
    for (int i = 0; i < cardsInHand; ++i) {
        if (hand[i].getUniqueId() == uniqueId) {
            notifyRemoveFromHand(hand[i]);
            eraseAtIdxInHand(i);
        }
    }
}

void CardManager::removeFromDiscard(int idx) {
    notifyRemoveFromDiscardPile(*(discardPile.begin()+idx));
    discardPile.erase(discardPile.begin()+idx);
}

void CardManager::removeFromExhaustPile(int idx) {
    exhaustPile.erase(exhaustPile.begin()+idx);
}

// **************** END Remove Methods ****************

// **************** START Move Methods ****************

void CardManager::moveToHand(const CardInstance &c) {
#ifdef sts_asserts
    assert(cardsInHand < 10);
#endif
    notifyAddToHand(c);
    hand[cardsInHand++] = c;
}

void CardManager::moveToExhaustPile(const CardInstance &c) {
    notifyRemoveFromCombat(c);
    exhaustPile.push_back(landed(c));
}


void CardManager::moveToDrawPileTop(const CardInstance &c) {
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to move invalid card to draw pile" << std::endl;
        assert(false);
    }
#endif
    notifyAddToDrawPile(c);
    const auto placed = landed(c);
    drawPile.addToTop(placed);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::KNOWN_TOP_PLACED, placed);
}

void CardManager::moveToDrawPileBottom(const CardInstance &c) {
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to move invalid card to draw pile bottom" << std::endl;
        assert(false);
    }
#endif
    notifyAddToDrawPile(c);
    const auto placed = landed(c);
    drawPile.addToBottom(placed);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED, placed);
}

void CardManager::shuffleIntoDrawPile(Random &cardRandomRng, const CardInstance &c) {
#ifdef sts_asserts
    if (!drawPile.empty() && c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to insert invalid card to draw pile" << std::endl;
        assert(false);
    }
#endif
    notifyAddToDrawPile(c);
    const auto placed = landed(c);
    drawPile.shuffleIn(cardRandomRng, placed);
    search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT, placed);
}

void CardManager::moveToDiscardPile(const CardInstance &c) {
    // todo check flurries, weave
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to move invalid card to discard pile" << std::endl;
        assert(false);
    }
#endif
    notifyAddToDiscardPile(c);
    discardPile.push_back(landed(c));
}

void CardManager::moveDiscardPileIntoToDrawPile(Random &shuffleRng) {
    for (auto &c : discardPile) c = landed(c);
    if (!drawPile.isConcrete()) {
        // The shuffle's randomness is deferred to draw time.
        drawPileBloodCardCount += discardPileBloodCardCount;
        drawPile.absorbUnordered(discardPile);

    } else {
        java::Collections::shuffle(
                discardPile.begin(),
                discardPile.end(),
                java::Random(shuffleRng.randomLong())
        );
        if (drawPile.empty()) {
            drawPileBloodCardCount = discardPileBloodCardCount;
            drawPile.assignConcrete({discardPile.begin(), discardPile.end()});

        } else {
            for (const auto &c : discardPile) {
                moveToDrawPileTop(c);
            }
        }
    }

    discardPileBloodCardCount = 0;
    discardPile.clear();
    // A discard->draw transfer changes the observable draw-pile cardinality
    // but must not disclose its shuffled order to the epistemic tracker.
    search::CombatKnowledgeEvent event {search::CombatKnowledgeEventType::RESHUFFLE_OCCURRED};
    event.drawPileSize = static_cast<int>(drawPile.size());
    search::emitCombatKnowledgeEvent(event);
}

// **************** END Move Methods ****************


// **************** BEGIN NOTIFY METHODS ****************

void CardManager::notifyAddCardToCombat(const CardInstance &c) {
    if (c.isStrikeCard()) {
        ++strikeCount;
    }
}

void CardManager::notifyRemoveFromCombat(const CardInstance &c) {
    if (c.isStrikeCard()) {
        --strikeCount;
    }
}

void CardManager::notifyAddToHand(const CardInstance &c) {
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to notify of invalid card in hand" << std::endl;
        assert(false);
    }
#endif

    if (c.isBloodCard()) {
        ++handBloodCardCount;
    }

    switch (c.id) {
        case CardId::NORMALITY:
            ++handNormalityCount;
            break;

        case CardId::PAIN:
            ++handPainCount;
            break;

        default:
            break;
    }
}

void CardManager::notifyRemoveFromHand(const CardInstance &c) {
    if (c.isBloodCard()) {
        --handBloodCardCount;
    }

    switch (c.id) {
        case CardId::NORMALITY:
            --handNormalityCount;
            break;

        case CardId::PAIN:
            --handPainCount;
            break;

        default:
            break;
    }
}

void CardManager::notifyAddToDrawPile(const CardInstance &c) {

#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to notify of invalid card in draw pile" << std::endl;
        assert(false);
    }
#endif

    if (c.isBloodCard()) {
        ++drawPileBloodCardCount;
    }
}

void CardManager::notifyRemoveFromDrawPile(const CardInstance &c) {
    if (c.isBloodCard()) {
        --drawPileBloodCardCount;
    }
}

void CardManager::notifyAddToDiscardPile(const CardInstance &c) {
#ifdef sts_asserts
    if (c.getId() == CardId::INVALID) {
        std::cerr << *g_debug_bc << '\n';
        std::cerr << "attempted to notify of invalid card in discard pile" << std::endl;
        assert(false);
    }
#endif

    if (c.isBloodCard()) {
        ++discardPileBloodCardCount;
    }
}


void CardManager::notifyRemoveFromDiscardPile(const CardInstance &c) {
    if (c.isBloodCard()) {
        --discardPileBloodCardCount;
    }
}

// **************** END NOTIFY METHODS ****************

void CardManager::eraseAtIdxInHand(int idx) {
#ifdef sts_asserts
    if (idx >= cardsInHand) {
        assert(false);
    }
#endif

    for (int x = idx; x < cardsInHand-1; ++x) {
        hand[x] = hand[x+1];
    }
    --cardsInHand;
}

int CardManager::getRandomCardIdxInHand(Random &rng) {
    return rng.random(cardsInHand-1);
}

void CardManager::resetAttributesAtEndOfTurn() {
    for (int i = 0; i < cardsInHand; ++i) {
        hand[i].setCostForTurn(hand[i].cost);
    }

    for (auto &c : discardPile) {
        c.setCostForTurn(c.cost);
    }

    drawPile.mutateAll([](CardInstance &c) {
        c.setCostForTurn(c.cost);
    });
}

// **************** BEGIN SPECIAL HELPERS ****************

void CardManager::draw(BattleContext &bc, int amount) {
    int evolve = bc.player.getStatus<PS::EVOLVE>();
    int fireBreathing = bc.player.getStatus<PS::FIRE_BREATHING>();

    for (int i = 0; i < amount; i++) {
        auto c = popFromDrawPile(bc.shuffleRng);

        if (bc.player.hasStatus<PS::CONFUSED>()) {
            if (c.cost >= 0) {  // todo status and curses affected by this?
                const auto newCost = static_cast<std::int8_t>(bc.cardRandomRng.random(3));
                if (c.cost != newCost) {
                    c.costForTurn = newCost;
                    c.cost = newCost;
                }
                c.freeToPlayOnce = false;
            }
        }

        if (c.getType() == CardType::SKILL) {
            if (bc.player.hasStatus<PS::CORRUPTION>()) {
                c.setCostForTurn(-9);
            }

        } else if (c.getType() == CardType::STATUS) {
            if (evolve) {
                bc.addToBot( Actions::DrawCards(evolve) );
            }
            if (fireBreathing) {
                bc.addToBot( Actions::DamageAllEnemy(fireBreathing) );
            }
            if (c.getId() == CardId::VOID) {
                // game adds action to bottom of the queue but I think it is ok to do directly
                bc.player.energy = std::max(0, bc.player.energy-1);
            }

        } else if (c.getType() == CardType::CURSE) {
            if (fireBreathing) {
                bc.addToBot( Actions::DamageAllEnemy(fireBreathing) );
            }

        }

        // do we need to check this?
        if (cardsInHand < 10) {
            moveToHand(c);
        } else {
            moveToDiscardPile(c);
        }
    }

}

void CardManager::onTookDamage() {
    // this method will fail catastrophically if the bloodCardCounts are not correct
    const bool hasAnyBloodCards = handBloodCardCount | drawPileBloodCardCount | discardPileBloodCardCount;
    if (!hasAnyBloodCards) {
        return;
    }

    int i = 0;
    int foundBloodCards = 0;
    while (foundBloodCards < handBloodCardCount) {
        if (hand[i].isBloodCard()) {
            hand[i].tookDamage();
            ++foundBloodCards;
        }
        ++i;
    }

    i = 0;
    foundBloodCards = 0;
    while (foundBloodCards < drawPileBloodCardCount) {
        if (drawPile[i].isBloodCard()) {
            drawPile.mutateAt(i, [](CardInstance &c) { c.tookDamage(); });
            ++foundBloodCards;
        }
        ++i;
    }

    i = 0;
    foundBloodCards = 0;
    while (foundBloodCards < discardPileBloodCardCount) {
        if (discardPile[i].isBloodCard()) {
            discardPile[i].tookDamage();
            ++foundBloodCards;
        }
        ++i;
    }
}

void upgrade(CardInstance &c, int upgradeAmount) {
    c.specialData += upgradeAmount;
}

// for ritual dagger, rampage
void CardManager::findAndUpgradeSpecialData(const std::int16_t uniqueId, const int upgradeAmount) {

    // special checks for most common scenarios
    if (!discardPile.empty() && discardPile.back().uniqueId == uniqueId) {
        upgrade(discardPile.back(), upgradeAmount);
        return;
    }
    if (!exhaustPile.empty() && exhaustPile.back().uniqueId == uniqueId) {
        upgrade(exhaustPile.back(), upgradeAmount);
        return;
    }

    for (int i = static_cast<int>(discardPile.size())-2; i >= 0; --i) {
        auto &c = discardPile[i];
        if (c.uniqueId == uniqueId) {
            upgrade(c, upgradeAmount);
            return;
        }
    }

    for (int i = static_cast<int>(exhaustPile.size())-2; i >= 0; --i) {
        auto &c = exhaustPile[i];
        if (c.uniqueId == uniqueId) {
            upgrade(c, upgradeAmount);
            return;
        }
    }

    for (int i = 0; i < drawPile.size(); ++i) {
        if (drawPile[i].uniqueId == uniqueId) {
            drawPile.mutateAt(i, [&](CardInstance &c) { upgrade(c, upgradeAmount); });
            return;
        }
    }

    for (int i = 0; i < cardsInHand; ++i) {
        auto &c = hand[i];
        if (c.uniqueId == uniqueId) {
            upgrade(c, upgradeAmount);
            return;
        }
    }

}

void CardManager::onBuffCorruption() {
    // game does modifyCostForCombat here but I don't think its necessary as skills cant cost more than 4?
    for (int i = 0; i < cardsInHand; ++i) {
        auto &c = hand[i];
        if (c.getType() == CardType::SKILL && c.cost > 0) {
            c.cost = 0;
            c.costForTurn = 0;
        }
    }

    // probably only need to do hand?

    drawPile.mutateAll([](CardInstance &c) {
        if (c.getType() == CardType::SKILL && c.cost > 0) {
            c.cost = 0;
            c.costForTurn = 0;
        }
    });

    for (auto &c : discardPile) {
        if (c.getType() == CardType::SKILL && c.cost > 0) {
            c.cost = 0;
            c.costForTurn = 0;
        }
    }

    for (auto &c : exhaustPile) {
        if (c.getType() == CardType::SKILL && c.cost > 0) {
            c.cost = 0;
            c.costForTurn = 0;
        }
    }


}

// **************** END SPECIAL HELPERS ****************


namespace sts {

//    std::ostream &operator<<(std::ostream &os, const CardInstance &c) {
//        return os << "("
//            << c.getName()
//            << ", uid:" << std::to_string(c.uniqueId)
//            << ", u:" << std::to_string(c.upgraded)
//            << ", c:" << c.cost
//            << ", ct:" << c.costForTurn
//            << ")";
//    }

    template<typename Forward_Iterator>
    void printArray(std::ostream &os, Forward_Iterator begin, Forward_Iterator end) {
        os << "{ ";
        while (begin != end && begin+1 != end) {
            os << *begin << ", ";
            ++begin;
        }
        if (begin != end) {
            os << *begin;
        }
        os << " }";
    }

    std::ostream &operator<<(std::ostream &os, const CardManager &c) {
        os << "CardManager: {";

        os << "\n\tdrawPile: " << c.drawPile.size() << " ";
        printArray(os, c.drawPile.begin(), c.drawPile.end());

        os << ",\n\tdiscardPile: " << c.discardPile.size() << " ";
        printArray(os, c.discardPile.begin(), c.discardPile.end());

        os << ",\n\texhaustPile: " << c.exhaustPile.size() << " ";
        printArray(os, c.exhaustPile.begin(), c.exhaustPile.end());

        os << ",\n\thand: " << c.cardsInHand << " ";
        printArray(os, c.hand.begin(), c.hand.begin()+c.cardsInHand);

        os << "\n\tstasisCards{" << c.stasisCards[0] << "," << c.stasisCards[1] << "}";

        os << "\n\t" << "handNormalityCount: " << c.handNormalityCount;
        const auto s = ", ";
        os << s << "handPainCount: " << c.handPainCount;
        os << s << "strikeCount: " << c.strikeCount;

        os << s << "handBloodCardCount: " << c.handBloodCardCount;
        os << s << "drawPileBloodCardCount: " << c.drawPileBloodCardCount;
        os << s << "discardPileBloodCardCount: " << c.discardPileBloodCardCount;

        os << "\n}\n";

        return os;
    }


}

namespace {

    template <typename Pile>
    bool sameMultiset(const Pile &a, const Pile &b) {
        if (a.size() != b.size()) {
            return false;
        }
        std::vector<CardInstance> x(a.begin(), a.end());
        std::vector<CardInstance> y(b.begin(), b.end());
        std::sort(x.begin(), x.end());
        std::sort(y.begin(), y.end());
        return x == y;
    }

    bool sameNonHandState(const CardManager &a, const CardManager &b) {
        return a.nextUniqueCardId == b.nextUniqueCardId &&
               a.cardsInHand == b.cardsInHand &&
               a.limbo == b.limbo &&
               a.stasisCards == b.stasisCards &&
               a.drawPile == b.drawPile &&
               a.discardPile == b.discardPile &&
               a.exhaustPile == b.exhaustPile &&
               a.handNormalityCount == b.handNormalityCount &&
               a.handPainCount == b.handPainCount &&
               a.strikeCount == b.strikeCount &&
               a.handBloodCardCount == b.handBloodCardCount &&
               a.drawPileBloodCardCount == b.drawPileBloodCardCount &&
               a.discardPileBloodCardCount == b.discardPileBloodCardCount;
    }

}

bool CardManager::operator==(const CardManager &rhs) const {
    return sameNonHandState(*this, rhs)
        && std::equal(hand.begin(), hand.begin() + cardsInHand, rhs.hand.begin());
}

bool CardManager::equalForSearch(const CardManager &rhs) const {
    if (!drawPile.isConcrete() || !rhs.drawPile.isConcrete()) {
        // Information-set search: discard and exhaust order carry no information
        // the search can use (reshuffles forget order, selections are by card).
        if (!(nextUniqueCardId == rhs.nextUniqueCardId &&
              cardsInHand == rhs.cardsInHand &&
              limbo == rhs.limbo &&
              stasisCards == rhs.stasisCards &&
              drawPile == rhs.drawPile &&
              handNormalityCount == rhs.handNormalityCount &&
              handPainCount == rhs.handPainCount &&
              strikeCount == rhs.strikeCount &&
              handBloodCardCount == rhs.handBloodCardCount &&
              drawPileBloodCardCount == rhs.drawPileBloodCardCount &&
              discardPileBloodCardCount == rhs.discardPileBloodCardCount &&
              sameMultiset(discardPile, rhs.discardPile) &&
              sameMultiset(exhaustPile, rhs.exhaustPile))) {
            return false;
        }
    } else if (!sameNonHandState(*this, rhs)) {
        return false;
    }
    std::array<CardInstance, MAX_HAND_SIZE> lhsHand;
    std::array<CardInstance, MAX_HAND_SIZE> rhsHand;
    std::copy(hand.begin(), hand.begin() + cardsInHand, lhsHand.begin());
    std::copy(rhs.hand.begin(), rhs.hand.begin() + cardsInHand, rhsHand.begin());
    std::sort(lhsHand.begin(), lhsHand.begin() + cardsInHand);
    std::sort(rhsHand.begin(), rhsHand.begin() + cardsInHand);
    return std::equal(lhsHand.begin(), lhsHand.begin() + cardsInHand, rhsHand.begin());
}
