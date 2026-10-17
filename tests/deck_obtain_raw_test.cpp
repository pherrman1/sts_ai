#include "game/GameContext.h"

#include <iostream>
#include <stdexcept>

using namespace sts;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// Direct deck fixture: no generated run, map, fight or game seed.
// Deck::obtainRaw (save-file load, fixtures) must keep the same bookkeeping as
// Deck::obtain: one count per card, and Ascender's Bane, Necronomicurse and
// Curse of the Bell do not count as curses (the game's isCursed()).
int main() {
    try {
        GameContext gc{};
        gc.cc = CharacterClass::IRONCLAD;
        const Card cards[] = {
            Card(CardId::STRIKE_RED), Card(CardId::DEFEND_RED), Card(CardId::BASH, 1),
            Card(CardId::INFLAME), Card(CardId::ASCENDERS_BANE), Card(CardId::NECRONOMICURSE),
            Card(CardId::CURSE_OF_THE_BELL), Card(CardId::REGRET),
        };
        Deck viaObtain, viaRaw;
        for (const auto &c : cards) {
            viaObtain.obtain(gc, c);
            viaRaw.obtainRaw(c);
        }
        require(viaRaw.size() == viaObtain.size(), "size");
        require(viaRaw.cardTypeCounts == viaObtain.cardTypeCounts, "card type counts");
        require(viaRaw.transformableCount == viaObtain.transformableCount, "transformable count");
        require(viaRaw.upgradeableCount == viaObtain.upgradeableCount, "upgradeable count");
        require(viaRaw.cardTypeCounts[static_cast<int>(CardType::ATTACK)] == 2, "two attacks");
        require(viaRaw.cardTypeCounts[static_cast<int>(CardType::CURSE)] == 1, "only Regret is a curse");

        Deck baneOnly;
        baneOnly.obtainRaw(Card(CardId::STRIKE_RED));
        baneOnly.obtainRaw(Card(CardId::ASCENDERS_BANE));
        require(!baneOnly.hasCurse(), "Ascender's Bane alone does not make the deck cursed");
        baneOnly.obtainRaw(Card(CardId::REGRET));
        require(baneOnly.hasCurse(), "Regret makes the deck cursed");
        baneOnly.remove(gc, 2);
        require(!baneOnly.hasCurse(), "removing Regret clears the curse count");
        require(baneOnly.cardTypeCounts[static_cast<int>(CardType::ATTACK)] == 1, "one attack");
        baneOnly.remove(gc, 0);
        require(baneOnly.cardTypeCounts[static_cast<int>(CardType::ATTACK)] == 0, "attack count returns to zero");
    } catch (const std::exception &e) {
        std::cerr << "deck_obtain_raw_test FAILED: " << e.what() << '\n';
        return 1;
    }
    std::cout << "deck_obtain_raw_test passed\n";
    return 0;
}
