// Three default-on out-of-combat fixes (=0 restores the legacy rule each):
// STS_NLOTHS_FACE_COUNTER_FIX: N'loth's Hungry Face starts at 1, so the next
//   non-boss chest holds no relic and draws none from the pool.
// STS_OOC_ENTROPIC_BREW_FIX: out-of-combat Entropic Brew draws limited
//   potions (no Fruit Juice) into the first empty slots, as in combat.
// STS_ASTROLABE_COLORLESS_UPGRADE_FIX: Astrolabe upgrades a transformed
//   colorless card too.
// Direct public fixtures: no game seed, map or fight.
#include "game/GameContext.h"
#include "game/Game.h"

#include <array>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void setFlag(const char *name, const char *value) {
    if (value) setenv(name, value, 1);
    else unsetenv(name);
}

static GameContext fixture() {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::EVENT;
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static GameContext chestFixture() {
    auto gc = fixture();
    gc.curRoom = Room::TREASURE;
    gc.info.tier = RelicTier::COMMON;
    gc.info.haveGold = false;
    gc.info.chestSize = ChestSize::SMALL;
    gc.commonRelicPool = {RelicId::ANCHOR, RelicId::LANTERN};
    return gc;
}

static void nlothsFace(bool fixed) {
    auto gc = chestFixture();
    require(!gc.obtainRelic(RelicId::NLOTHS_HUNGRY_FACE), "the face opened a screen");
    require(gc.relics.getRelicValue(RelicId::NLOTHS_HUNGRY_FACE) == (fixed ? 1 : 0), "initial face counter");

    gc.openTreasureRoomChest();
    const auto &first = gc.info.rewardsContainer;
    if (fixed) {
        require(first.relicCount == 0, "the face must empty the first chest");
        require(gc.commonRelicPool == std::vector<RelicId>{RelicId::ANCHOR, RelicId::LANTERN},
                "an eaten relic must not leave the pool");
    } else {
        require(first.relicCount == 1 && first.relics[0] == RelicId::ANCHOR, "legacy chest relic");
        require(gc.commonRelicPool == std::vector<RelicId>{RelicId::LANTERN}, "legacy pool draw");
    }
    require(gc.relics.getRelicValue(RelicId::NLOTHS_HUNGRY_FACE) == 0, "face counter after the chest");

    gc.openTreasureRoomChest();
    const auto &second = gc.info.rewardsContainer;
    require(second.relicCount == 1 && second.relics[0] == (fixed ? RelicId::ANCHOR : RelicId::LANTERN),
            "second chest relic");

    // A counter imported as 1 under the legacy rule consumed the chest but
    // still drew the relic from the pool.
    auto imported = chestFixture();
    imported.relics.add({RelicId::NLOTHS_HUNGRY_FACE, 1});
    imported.openTreasureRoomChest();
    require(imported.info.rewardsContainer.relicCount == 0, "counter 1 must consume the chest in both modes");
    require(imported.commonRelicPool.size() == (fixed ? 2u : 1u), "imported counter pool draw");
}

static std::array<Potion, 5> drinkBrew(GameContext &gc) {
    gc.drinkPotionAtIdx(0);
    return gc.potions;
}

static void entropicBrew(bool fixed) {
    auto gc = fixture();
    gc.potionCapacity = 3;
    gc.potions = {Potion::ENTROPIC_BREW, Potion::BLOCK_POTION, Potion::EMPTY_POTION_SLOT,
                  Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    gc.potionCount = 2;
    gc.potionRng = Random(5);
    Random copy = gc.potionRng;
    std::array<Potion, 5> expected = gc.potions;
    if (fixed) {
        // Three limited draws fill the brew's own slot and the empty slot
        // in order; the third draw finds no slot.
        const Potion p1 = returnRandomPotion(copy, gc.cc, true);
        const Potion p2 = returnRandomPotion(copy, gc.cc, true);
        returnRandomPotion(copy, gc.cc, true);
        expected = {p1, Potion::BLOCK_POTION, p2, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    } else {
        const Potion q0 = returnRandomPotion(copy, gc.cc, false);
        returnRandomPotion(copy, gc.cc, false);
        const Potion q2 = returnRandomPotion(copy, gc.cc, false);
        expected = {q0, Potion::BLOCK_POTION, q2, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    }
    require(drinkBrew(gc) == expected, "Entropic Brew slots");
    require(gc.potionCount == 3 && gc.potionRng == copy, "Entropic Brew count/RNG");

    int fruitJuice = 0;
    for (int seed = 1; seed <= 300; ++seed) {
        auto full = fixture();
        full.potionCapacity = 5;
        full.potions = {Potion::ENTROPIC_BREW, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                        Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
        full.potionCount = 1;
        full.potionRng = Random(seed);
        for (const auto potion : drinkBrew(full)) {
            require(potion != Potion::EMPTY_POTION_SLOT, "a five-draw brew left a slot empty");
            if (potion == Potion::FRUIT_JUICE) ++fruitJuice;
        }
        require(full.potionCount == 5, "five-draw brew count");
    }
    require(fixed ? fruitJuice == 0 : fruitJuice > 0, "Fruit Juice from Entropic Brew: " + std::to_string(fruitJuice));

    auto sozu = fixture();
    sozu.potionCapacity = 3;
    sozu.potions = {Potion::ENTROPIC_BREW, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                    Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    sozu.potionCount = 1;
    sozu.potionRng = Random(5);
    sozu.relics.add({RelicId::SOZU, 0});
    Random sozuCopy = sozu.potionRng;
    for (int i = 0; i < 3; ++i) returnRandomPotion(sozuCopy, sozu.cc, fixed);
    const auto afterSozu = drinkBrew(sozu);
    require(sozu.potionRng == sozuCopy, "Sozu brew still rolls every draw");
    if (fixed) {
        require(sozu.potionCount == 0 && afterSozu[0] == Potion::EMPTY_POTION_SLOT
                && afterSozu[1] == Potion::EMPTY_POTION_SLOT && afterSozu[2] == Potion::EMPTY_POTION_SLOT,
                "Sozu must refuse brewed potions");
    } else {
        require(sozu.potionCount == 3 && afterSozu[0] != Potion::EMPTY_POTION_SLOT, "legacy brew ignored Sozu");
    }
}

static void astrolabe(bool fixed) {
    auto gc = fixture();
    Random rng(9);
    Random plain(9);
    const Card upgraded = gc.getTransformedCard(rng, CardId::FLASH_OF_STEEL, true);
    const Card unupgraded = gc.getTransformedCard(plain, CardId::FLASH_OF_STEEL, false);
    require(getCardColor(upgraded.getId()) == CardColor::COLORLESS && upgraded.getId() != CardId::FLASH_OF_STEEL,
            "colorless transform result");
    require(upgraded.getId() == unupgraded.getId() && rng == plain, "autoUpgrade changed the roll");
    require(upgraded.isUpgraded() == fixed && !unupgraded.isUpgraded(), "colorless auto-upgrade");
    Random red(9);
    require(gc.getTransformedCard(red, CardId::BASH, true).isUpgraded(), "colored auto-upgrade changed");

    auto run = fixture();
    run.deck.obtainRaw(Card(CardId::BASH));
    run.deck.obtainRaw(Card(CardId::FLASH_OF_STEEL));
    run.miscRng = Random(9);
    require(run.obtainRelic(RelicId::ASTROLABE), "Astrolabe did not open a screen");
    require(run.screenState == ScreenState::CARD_SELECT && run.info.selectScreenType == CardSelectScreenType::TRANSFORM_UPGRADE
            && run.info.toSelectCount == 2, "Astrolabe screen");
    run.chooseSelectCardScreenOption(0);
    run.chooseSelectCardScreenOption(0);
    require(run.screenState == ScreenState::MAP_SCREEN && run.deck.size() == 2, "Astrolabe transform");
    int colorless = 0;
    for (const auto &card : run.deck.cards) {
        const bool isColorless = getCardColor(card.getId()) == CardColor::COLORLESS;
        colorless += isColorless;
        require(card.isUpgraded() == (fixed || !isColorless), "Astrolabe upgrade of transformed cards");
    }
    require(colorless == 1, "Astrolabe transformed card colors");
}

int main() {
    try {
        for (const char *value : {static_cast<const char *>(nullptr), "1", "0"}) {
            const bool fixed = !value || std::string(value) == "1";
            setFlag("STS_NLOTHS_FACE_COUNTER_FIX", value);
            nlothsFace(fixed);
            setFlag("STS_OOC_ENTROPIC_BREW_FIX", value);
            entropicBrew(fixed);
            setFlag("STS_ASTROLABE_COLORLESS_UPGRADE_FIX", value);
            astrolabe(fixed);
        }
        for (const char *name : {"STS_NLOTHS_FACE_COUNTER_FIX", "STS_OOC_ENTROPIC_BREW_FIX",
                                 "STS_ASTROLABE_COLORLESS_UPGRADE_FIX"}) {
            setFlag(name, "2");
            bool rejected = false;
            try {
                auto gc = fixture();
                gc.potionCapacity = 1;
                gc.potions[0] = Potion::ENTROPIC_BREW;
                gc.potionCount = 1;
                gc.obtainRelic(RelicId::NLOTHS_HUNGRY_FACE);
                gc.drinkPotionAtIdx(0);
                Random rng(1);
                gc.getTransformedCard(rng, CardId::FLASH_OF_STEEL, true);
            } catch (const std::runtime_error &) { rejected = true; }
            require(rejected, std::string("malformed flag accepted: ") + name);
            setFlag(name, nullptr);
        }
        std::cout << "ooc_relic_minor_fix: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ooc_relic_minor_fix: FAIL: " << e.what() << '\n';
        return 1;
    }
}
