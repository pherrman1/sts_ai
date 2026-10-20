// STS_UNPLAYABLE_AUTOPLAY_FIX (default on): an autoplayed card (Havoc, Mayhem)
// that fails canUse is still routed like a played card, as in the game
// (GameActionManager sets dontTriggerOnUseCard and queues UseCardAction):
// Havoc exhausts it, Mayhem discards it, Strange Spoon rolls, exhaust triggers
// fire. =0 restores the legacy engine, where the card vanished.
// STS_AUTOPLAY_QUEUE_ORDER_FIX (default on): autoplayed cards join the back of
// the card queue (NewQueueCardAction appends), so a Distilled Chaos plays the
// top card first. =0 restores the legacy front insertion (reverse order).
#include "combat/Actions.h"
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

// Live canary seed of problem 41; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200435;

static int countId(const auto &pile, CardId id) {
    int n = 0;
    for (const auto &c : pile) n += c.getId() == id;
    return n;
}

struct Result {
    int exhaust = 0;
    int discard = 0;
    int block = 0;
    std::int32_t rngRolls = 0;
};

// Puts `top` on the draw pile, `handCard` in hand, and autoplays the top card
// (Havoc exhausts, Mayhem does not).
static Result autoplay(CardId top, bool exhausts, CardId handCard, bool spoon = false, bool feelNoPain = false) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    while (bc.cards.cardsInHand > 0) {
        const CardInstance c = bc.cards.hand[0];
        bc.cards.removeFromHandAtIdx(0);
        bc.cards.moveToDiscardPile(c);
    }
    if (handCard != CardId::INVALID) bc.cards.createTempCardInHand(CardInstance(handCard));
    bc.cards.createTempCardOnDrawPileTop(CardInstance(top, true));
    if (spoon) bc.player.setHasRelic<R::STRANGE_SPOON>(true);
    if (feelNoPain) bc.player.buff<PS::FEEL_NO_PAIN>(3);
    const auto rng = bc.cardRandomRng.counter;
    bc.addToBot(Actions::PlayTopCard(0, exhausts));
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return {countId(bc.cards.exhaustPile, top), countId(bc.cards.discardPile, top), bc.player.block,
            bc.cardRandomRng.counter - rng};
}

static void check(bool fixed);

// Problem 44: Distilled Chaos with draw top Ascender's Bane, Defend, Shrug It
// Off (top first). Returns the order these land in the discard pile.
static std::vector<CardId> distilledChaos() {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    bc.cards.createTempCardOnDrawPileTop(CardInstance(CardId::SHRUG_IT_OFF));
    bc.cards.createTempCardOnDrawPileTop(CardInstance(CardId::DEFEND_RED));
    bc.cards.createTempCardOnDrawPileTop(CardInstance(CardId::ASCENDERS_BANE));
    const int discardBefore = static_cast<int>(bc.cards.discardPile.size());
    bc.obtainPotion(Potion::DISTILLED_CHAOS);
    bc.drinkPotion(0, 0);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    std::vector<CardId> order;
    for (int i = discardBefore; i < static_cast<int>(bc.cards.discardPile.size()); ++i) {
        order.push_back(bc.cards.discardPile[i].getId());
    }
    return order;
}

static void check(bool fixed, bool orderFixed) {
    using C = CardId;
    const std::vector<CardId> order = distilledChaos();
    if (fixed && orderFixed) {
        require(order == std::vector<CardId>({C::ASCENDERS_BANE, C::DEFEND_RED, C::SHRUG_IT_OFF}),
                "Distilled Chaos discard order Bane, Defend, Shrug");
    } else if (fixed) {
        require(order == std::vector<CardId>({C::SHRUG_IT_OFF, C::DEFEND_RED, C::ASCENDERS_BANE}),
                "legacy front insertion plays Shrug, Defend, then the unplayable Bane");
    } else if (orderFixed) {
        require(order == std::vector<CardId>({C::DEFEND_RED, C::SHRUG_IT_OFF}), "legacy Bane vanishes");
    } else {
        require(order == std::vector<CardId>({C::SHRUG_IT_OFF, C::DEFEND_RED}), "legacy engine order");
    }
    check(fixed);
}

static void check(bool fixed) {
    using C = CardId;
    const int on = fixed ? 1 : 0;
    {
        // Problem 41 steps 204/229: Havoc+ plays Burn, which is exhausted.
        const Result r = autoplay(C::BURN, true, C::INVALID);
        require(r.exhaust == on && r.discard == 0, "Havoc'd Burn exhausted");
    }
    {
        // Steps 178/215: Clash+ is unplayable with a Defend in hand.
        const Result r = autoplay(C::CLASH, true, C::DEFEND_RED);
        require(r.exhaust == on && r.discard == 0, "Havoc'd unplayable Clash exhausted");
    }
    {
        // Clash with only attacks in hand is playable: exhausted either way.
        const Result r = autoplay(C::CLASH, true, C::STRIKE_RED);
        require(r.exhaust == 1, "playable Clash exhausted");
    }
    {
        // Mayhem does not exhaust: the unplayable card is discarded.
        const Result r = autoplay(C::BURN, false, C::INVALID);
        require(r.exhaust == 0 && r.discard == on, "Mayhem'd Burn discarded");
    }
    {
        // Strange Spoon rolls cardRandomRng for the exhaust.
        const Result r = autoplay(C::BURN, true, C::INVALID, true);
        require(r.rngRolls == on, "Strange Spoon roll");
        require(r.exhaust + r.discard == on, "Burn exhausted or spooned to discard");
    }
    {
        // The exhaust triggers Feel No Pain.
        const Result r = autoplay(C::BURN, true, C::INVALID, false, true);
        require(r.block == (fixed ? 3 : 0), "Feel No Pain on the exhausted Burn");
    }
}

int main() {
    try {
        unsetenv("STS_UNPLAYABLE_AUTOPLAY_FIX");
        unsetenv("STS_AUTOPLAY_QUEUE_ORDER_FIX");
        check(true, true);
        setenv("STS_UNPLAYABLE_AUTOPLAY_FIX", "1", 1);
        setenv("STS_AUTOPLAY_QUEUE_ORDER_FIX", "1", 1);
        check(true, true);
        setenv("STS_AUTOPLAY_QUEUE_ORDER_FIX", "0", 1);
        check(true, false);
        setenv("STS_UNPLAYABLE_AUTOPLAY_FIX", "0", 1);
        check(false, false);
        setenv("STS_AUTOPLAY_QUEUE_ORDER_FIX", "1", 1);
        check(false, true);
        std::cout << "unplayable_autoplay: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "unplayable_autoplay: FAIL: " << e.what() << '\n';
        return 1;
    }
}
