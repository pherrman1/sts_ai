#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/BattleSearcher.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <string>

bool sts::GameContext::hasRelic(sts::RelicId relic) const {
    return relics.has(relic);
}

int sts::Deck::size() const {
    return cards.size();
}

namespace {

using namespace sts;

struct StateFixture {
    GameContext game;
    BattleContext state;

    explicit StateFixture(MonsterEncounter encounter)
        : game() {
        game.cc = CharacterClass::IRONCLAD;
        game.seed = 0x51A7u;
        game.ascension = 0;
        game.floorNum = 1;
        game.act = 1;
        game.curHp = 80;
        game.maxHp = 80;
        game.potionCapacity = 3;
        std::fill(game.potions.begin(), game.potions.end(), Potion::EMPTY_POTION_SLOT);
        game.map = std::make_shared<Map>();
        for (int i = 0; i < 5; ++i) game.deck.cards.push_back(Card(CardId::STRIKE_RED));
        for (int i = 0; i < 4; ++i) game.deck.cards.push_back(Card(CardId::DEFEND_RED));
        game.deck.cards.push_back(Card(CardId::BASH));
        state.init(game, encounter);
    }
};

void checkParity(const std::string &name, const BattleContext &root,
                 const BattleContext &terminal, int &failures) {
    search::BattleSearcher searcher(root);
    const auto features = search::terminalValueFeatures(root, terminal);
    const auto reconstructed = search::evaluateTerminalFeatures(features);
    const auto production = searcher.evaluateEndStateForDiagnostics(terminal);
    if (std::abs(reconstructed - production) > 1e-9) {
        std::cerr << name << " parity mismatch reconstructed=" << reconstructed
                  << " production=" << production << '\n';
        ++failures;
    }
}

} // namespace

int main() {
    int failures = 0;

    StateFixture victoryFixture(MonsterEncounter::CULTIST);
    auto &victoryRoot = victoryFixture.state;
    auto victory = victoryRoot;
    victory.outcome = Outcome::PLAYER_VICTORY;
    victory.turn = 7;
    victory.player.curHp = 42;
    victory.potionCount = 2;
    victory.player.gold += 37;
    victory.player.maxHp += 3;
    checkParity("victory", victoryRoot, victory, failures);

    StateFixture lossFixture(MonsterEncounter::CULTIST);
    auto &lossRoot = lossFixture.state;
    auto loss = lossRoot;
    loss.outcome = Outcome::PLAYER_LOSS;
    loss.turn = 6;
    loss.energyWasted = 2;
    loss.cardsDrawn = 9;
    loss.potionCount = 1;
    loss.monsters.monstersAlive = 1;
    loss.monsters.arr[0].curHp = loss.monsters.arr[0].maxHp / 2;
    checkParity("ordinary loss", lossRoot, loss, failures);

    StateFixture spikerFixture(MonsterEncounter::THREE_SHAPES);
    auto &spikerRoot = spikerFixture.state;
    auto spiker = spikerRoot;
    spiker.outcome = Outcome::PLAYER_LOSS;
    spiker.turn = 8;
    spiker.energyWasted = 11;
    checkParity("spiker exception", spikerRoot, spiker, failures);

    StateFixture cappedFixture(MonsterEncounter::CULTIST);
    auto &cappedRoot = cappedFixture.state;
    auto capped = cappedRoot;
    capped.outcome = Outcome::PLAYER_LOSS;
    capped.turn = 101;
    checkParity("turn cap survival", cappedRoot, capped, failures);

    StateFixture relicFixture(MonsterEncounter::CULTIST);
    auto &relicRoot = relicFixture.state;
    relicRoot.potionCapacity = 2;
    relicRoot.potions[0] = Potion::FAIRY_POTION;
    relicRoot.potionCount = 1;
    relicRoot.player.setHasRelic<RelicId::SACRED_BARK>(true);
    relicRoot.player.setHasRelic<RelicId::LIZARD_TAIL>(true);
    auto relicVictory = relicRoot;
    relicVictory.outcome = Outcome::PLAYER_VICTORY;
    checkParity("Fairy Sacred Bark Lizard Tail", relicRoot, relicVictory, failures);

    StateFixture bloomFixture(MonsterEncounter::CULTIST);
    auto &bloomRoot = bloomFixture.state;
    bloomRoot.potionCapacity = 2;
    bloomRoot.potions[0] = Potion::FAIRY_POTION;
    bloomRoot.potionCount = 1;
    bloomRoot.player.setHasRelic<RelicId::MARK_OF_THE_BLOOM>(true);
    auto bloomVictory = bloomRoot;
    bloomVictory.outcome = Outcome::PLAYER_VICTORY;
    checkParity("Mark of the Bloom", bloomRoot, bloomVictory, failures);

    if (failures != 0) return 1;
    std::cout << "silver_terminal_value PASS\n";
    return 0;
}
