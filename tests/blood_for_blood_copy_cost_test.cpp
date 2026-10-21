// STS_BLOOD_FOR_BLOOD_COPY_COST_FIX (default on): a Blood for Blood generated
// in combat starts at 4 minus the times the player lost HP this combat, as
// Java's BloodForBlood.makeCopy() calls updateCost(-damagedThisCombat) (live
// parity problem 76, seed 111200476 s117: a Discovery+ copy cost 1 in the game
// after three hits, 4 natively; Nilry's Codex likewise, issue784). =0 restores
// the legacy base cost.
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

static void check(int damaged, int expectedCost) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    gc.act = 1; gc.floorNum = 3;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    while (bc.cards.cardsInHand > 0) {
        bc.cards.removeFromHandAtIdx(bc.cards.cardsInHand-1);
    }
    bc.player.timesDamagedThisCombat = static_cast<std::int16_t>(damaged);

    const auto generated = bc.generatedCombatCard(CardId::BLOOD_FOR_BLOOD);
    require(generated.cost == expectedCost && generated.costForTurn == expectedCost,
        "generated cost " + std::to_string(generated.cost) + "/" + std::to_string(generated.costForTurn)
        + ", expected " + std::to_string(expectedCost));
    require(bc.generatedCombatCard(CardId::STRIKE_RED).cost == 1, "other cards keep their base cost");

    bc.cardSelectInfo.data0 = 1;
    bc.cardSelectInfo.setCostToZero = false;
    bc.chooseDiscoveryCard(CardId::BLOOD_FOR_BLOOD);
    require(bc.cards.cardsInHand == 1 && bc.cards.hand[0].id == CardId::BLOOD_FOR_BLOOD, "Discovery adds the card");
    require(bc.cards.hand[0].cost == expectedCost && bc.cards.hand[0].costForTurn == expectedCost,
        "Discovery copy cost " + std::to_string(bc.cards.hand[0].cost) + ", expected " + std::to_string(expectedCost));

    // Nilry's Codex shuffles the pick into the draw pile (CodexAction javap, issue784).
    const int drawBefore = bc.cards.drawPile.size();
    bc.chooseCodexCard(CardId::BLOOD_FOR_BLOOD);
    require(static_cast<int>(bc.cards.drawPile.size()) == drawBefore+1, "Codex adds one card to the draw pile");
    int codexCopies = 0;
    for (const auto &card : bc.cards.drawPile) {
        if (card.id != CardId::BLOOD_FOR_BLOOD) continue;
        ++codexCopies;
        require(card.cost == expectedCost && card.costForTurn == expectedCost,
            "Codex copy cost " + std::to_string(card.cost) + ", expected " + std::to_string(expectedCost));
    }
    require(codexCopies == 1, "Codex adds exactly one Blood for Blood");
}

int main() {
    try {
        for (const char *value : {static_cast<const char *>(nullptr), "1"}) {
            if (value) setenv("STS_BLOOD_FOR_BLOOD_COPY_COST_FIX", value, 1);
            else unsetenv("STS_BLOOD_FOR_BLOOD_COPY_COST_FIX");
            check(0, 4);
            check(3, 1);
            check(6, 0);
        }
        setenv("STS_BLOOD_FOR_BLOOD_COPY_COST_FIX", "0", 1);
        check(3, 4);
        std::cout << "blood_for_blood_copy_cost: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "blood_for_blood_copy_cost: FAIL: " << e.what() << '\n';
        return 1;
    }
}
