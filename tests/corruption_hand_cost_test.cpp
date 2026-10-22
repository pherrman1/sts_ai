// STS_CORRUPTION_HAND_COST_FIX (default on): a card made in hand under
// Corruption runs the game's onCardDrawOrDiscard pass, which calls
// modifyCostForCombat(-9) on every hand SKILL with costForTurn != 0, so a
// generated skill ends at cost 0 / costForTurn 0 (live parity problem 83:
// Dead Branch skills under Snecko Eye + Corruption). =0 restores the legacy
// engine, which zeroed only costForTurn.
#include "combat/BattleContext.h"
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from this thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200071;

static BattleContext corruptedBattle() {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    bc.player.setHasStatus<PS::CORRUPTION>(true);
    return bc;
}

static const CardInstance &lastInHand(const BattleContext &bc) {
    return bc.cards.hand[bc.cards.cardsInHand - 1];
}

static void check(bool fixed) {
    {   // Dead Branch / MakeTempCardInHand: Entrench (base 2) and an attack.
        auto bc = corruptedBattle();
        while (bc.cards.cardsInHand > 0) bc.cards.removeFromHandAtIdx(0);
        bc.addToBot(Actions::MakeTempCardInHand(CardInstance(CardId::ENTRENCH)));
        bc.addToBot(Actions::MakeTempCardInHand(CardInstance(CardId::HEAVY_BLADE)));
        bc.inputState = InputState::EXECUTING_ACTIONS;
        bc.executeActions();
        require(bc.cards.cardsInHand == 2, "two generated cards in hand");
        const auto &entrench = bc.cards.hand[0];
        require(entrench.getId() == CardId::ENTRENCH, "Entrench first");
        require(entrench.costForTurn == 0, "Corruption zeroes Entrench's turn cost");
        require(entrench.cost == (fixed ? 0 : 2), "Entrench's combat cost");
        const auto &blade = lastInHand(bc);
        require(blade.cost == 2 && blade.costForTurn == 2, "attacks keep their cost");
    }
    {   // A 1-cost skill (Double Tap, as in the seed 111200508 hands).
        auto bc = corruptedBattle();
        while (bc.cards.cardsInHand > 0) bc.cards.removeFromHandAtIdx(0);
        bc.addToBot(Actions::MakeTempCardInHand(CardInstance(CardId::DOUBLE_TAP)));
        bc.inputState = InputState::EXECUTING_ACTIONS;
        bc.executeActions();
        const auto &tap = lastInHand(bc);
        require(tap.costForTurn == 0 && tap.cost == (fixed ? 0 : 1), "Double Tap cost");
    }
    {   // Without Corruption nothing changes.
        GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::JAW_WORM);
        bc.inputState = InputState::EXECUTING_ACTIONS;
        bc.executeActions();
        while (bc.cards.cardsInHand > 0) bc.cards.removeFromHandAtIdx(0);
        bc.addToBot(Actions::MakeTempCardInHand(CardInstance(CardId::ENTRENCH)));
        bc.inputState = InputState::EXECUTING_ACTIONS;
        bc.executeActions();
        const auto &entrench = lastInHand(bc);
        require(entrench.cost == 2 && entrench.costForTurn == 2, "no Corruption, no change");
    }
}

int main() {
    try {
        unsetenv("STS_CORRUPTION_HAND_COST_FIX");
        check(true);
        setenv("STS_CORRUPTION_HAND_COST_FIX", "1", 1);
        check(true);
        setenv("STS_CORRUPTION_HAND_COST_FIX", "0", 1);
        check(false);
        std::cout << "corruption_hand_cost: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "corruption_hand_cost: FAIL: " << e.what() << '\n';
        return 1;
    }
}
