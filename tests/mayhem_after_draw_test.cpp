// STS_MAYHEM_AFTER_DRAW_FIX (default on): Mayhem plays the top card of the draw
// pile after the start-of-turn draw, as in the game (MayhemPower queues a
// wrapper action that queues PlayTopCardAction behind DrawCardAction). =0
// restores the legacy engine, which played the pre-draw top card.
#include "combat/BattleContext.h"
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from this fix thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200121;

// Starts the next player turn with Mayhem 1 and the given draw pile (bottom
// first); the hand is empty before the draw.
static void startTurn(BattleContext &bc, const std::vector<CardId> &drawBottomFirst) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();

    while (bc.cards.cardsInHand > 0) {
        const CardInstance c = bc.cards.hand[0];
        bc.cards.removeFromHandAtIdx(0);
        bc.cards.moveToDiscardPile(c);
    }
    for (const auto &c : bc.cards.drawPile.concreteCards()) {
        bc.cards.notifyRemoveFromDrawPile(c);
    }
    std::vector<CardInstance> order;
    for (const CardId id : drawBottomFirst) {
        CardInstance c(id);
        c.uniqueId = bc.cards.nextUniqueCardId++;
        bc.cards.notifyAddToDrawPile(c);
        order.push_back(c);
    }
    bc.cards.drawPile.assignConcrete(order);

    bc.player.buff<PS::MAYHEM>(1);
    bc.afterMonsterTurns();
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
}

static void check(bool fixed) {
    using C = CardId;
    {
        // Pre-draw top is Inflame; after drawing five the top is Metallicize.
        BattleContext bc;
        startTurn(bc, {C::DEFEND_RED, C::METALLICIZE, C::STRIKE_RED, C::STRIKE_RED,
                       C::STRIKE_RED, C::STRIKE_RED, C::INFLAME});
        require(bc.player.getStatus<PS::METALLICIZE>() == (fixed ? 3 : 0), "Metallicize played by Mayhem");
        require(bc.player.getStatus<PS::STRENGTH>() == (fixed ? 0 : 2), "Inflame played by Mayhem");
        require(bc.cards.cardsInHand == 5, "the turn draws five cards");
    }
    {
        // After the draw the top card is Armaments: the game asks which hand
        // card to upgrade; before the draw the hand is empty and nothing asks.
        BattleContext bc;
        startTurn(bc, {C::DEFEND_RED, C::ARMAMENTS, C::STRIKE_RED, C::STRIKE_RED,
                       C::STRIKE_RED, C::STRIKE_RED, C::BASH});
        require((bc.inputState == InputState::CARD_SELECT) == fixed, "Armaments card selection after the draw");
    }
}

int main() {
    try {
        unsetenv("STS_MAYHEM_AFTER_DRAW_FIX");
        check(true);
        setenv("STS_MAYHEM_AFTER_DRAW_FIX", "1", 1);
        check(true);
        setenv("STS_MAYHEM_AFTER_DRAW_FIX", "0", 1);
        check(false);
        std::cout << "mayhem_after_draw: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "mayhem_after_draw: FAIL: " << e.what() << '\n';
        return 1;
    }
}
