// Offline #863 recurring-mass definition, using retained historical headers.
#include "constants/Cards.h"
#include <iostream>
int main() {
    int id, upgraded;
    while (std::cin >> id >> upgraded) {
        const auto c = static_cast<sts::CardId>(id);
        std::cout << (sts::getCardType(c) != sts::CardType::POWER
            && !sts::doesCardExhaust(c, upgraded)
            && c != sts::CardId::ASCENDERS_BANE && c != sts::CardId::DAZED
            && c != sts::CardId::VOID && c != sts::CardId::CLUMSY) << '\n';
    }
}
