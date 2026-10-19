// STS_PILE_COST_RESET_FIX (default on): a card that lands in the discard,
// draw or exhaust pile gets costForTurn = cost (Java Soul.update ->
// clearPowers -> resetAttributes; ExhaustCardEffect.update). A card created
// straight into a pile keeps its turn cost (ShowCardAndAddToDiscardEffect).
// =0 restores the legacy engine, which kept the turn cost until end of turn.
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from the Discovery fix thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200161;

// Records the card each draw-pile placement reports to Silver's knowledge
// tracker, which must carry the cost the pile now holds.
struct PlacedCards final : search::CombatKnowledgeObserver {
    std::vector<CardInstance> cards;
    void observeCombatKnowledgeEvent(const search::CombatKnowledgeEvent &event) override {
        if (event.hasCard) cards.push_back(event.card);
    }
};

static CardInstance freeCard() {
    CardInstance c(CardId::POWER_THROUGH);
    require(c.cost == 1, "Power Through must cost 1");
    c.setCostForTurn(0);
    return c;
}

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    const int expected = fixed ? 1 : 0;

    bc.cards.moveToDiscardPile(freeCard());
    require(bc.cards.discardPile.back().costForTurn == expected, "played card in discard");

    bc.cards.moveToExhaustPile(freeCard());
    require(bc.cards.exhaustPile.back().costForTurn == expected, "exhausted card");

    PlacedCards placed;
    search::g_combatKnowledgeObserver = &placed;
    bc.cards.moveToDrawPileTop(freeCard());
    bc.cards.moveToDrawPileBottom(freeCard());
    bc.cards.shuffleIntoDrawPile(bc.cardRandomRng, freeCard());
    search::g_combatKnowledgeObserver = nullptr;
    require(placed.cards.size() == 3, "each placement must report its card");
    for (const auto &c : placed.cards)
        require(c.costForTurn == expected, "the knowledge tracker must see the pile's turn cost");
    int moved = 0;
    for (int i = 0; i < bc.cards.drawPile.size(); ++i) {
        const auto &c = bc.cards.drawPile[i];
        if (c.getId() != CardId::POWER_THROUGH) continue;
        ++moved;
        require(c.costForTurn == expected, "card put on the draw pile");
    }
    require(moved == 3, "the three placed cards must be in the draw pile");

    // A Discovery copy created straight into the discard pile keeps cost 0,
    // until the discard pile is shuffled into the draw pile.
    bc.cards.discardPile.clear();
    bc.cards.createTempCardInDiscard(freeCard());
    require(bc.cards.discardPile.back().costForTurn == 0, "created card must keep its turn cost");
    bc.cards.moveDiscardPileIntoToDrawPile(bc.shuffleRng);
    bool found = false;
    for (int i = 0; i < bc.cards.drawPile.size(); ++i) {
        const auto &c = bc.cards.drawPile[i];
        if (c.getId() == CardId::POWER_THROUGH && c.uniqueId == bc.cards.nextUniqueCardId - 1) {
            found = true;
            require(c.costForTurn == expected, "shuffled card");
        }
    }
    require(found, "shuffled card not found in the draw pile");

    bc.cards.createTempCardOnDrawPileTop(freeCard());
    require(bc.cards.drawPile.back().costForTurn == 0, "created card on top must keep its turn cost");
}

int main() {
    try {
        unsetenv("STS_PILE_COST_RESET_FIX");
        check(true);
        setenv("STS_PILE_COST_RESET_FIX", "1", 1);
        check(true);
        setenv("STS_PILE_COST_RESET_FIX", "0", 1);
        check(false);
        std::cout << "pile_cost_reset: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "pile_cost_reset: FAIL: " << e.what() << '\n';
        return 1;
    }
}
