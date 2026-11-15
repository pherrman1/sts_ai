// Four default-on out-of-combat fixes (=0 restores the legacy rule each):
// STS_NLOTHS_FACE_COUNTER_FIX: N'loth's Hungry Face starts at 1; the next
//   non-boss chest still draws its relic from the pool, then the first relic
//   reward (Matryoshka's, if any) is removed, with the sapphire key linked to
//   it (Java removeOneRelicFromRewards).
// STS_OOC_ENTROPIC_BREW_FIX: out-of-combat Entropic Brew draws nothing with
//   Sozu; otherwise potionSlots unlimited draws into the first empty slots.
// Java rules checked with javap against the pinned V2.3.4 jar (2026-11-03).
// STS_ASTROLABE_COLORLESS_UPGRADE_FIX: Astrolabe upgrades a transformed
//   colorless card too.
// STS_OOC_TOY_ORNITHOPTER_FIX: Toy Ornithopter heals 5 after an
//   out-of-combat drink (javap 2026-11-15, #1055).
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
        // The relic is drawn (and leaves the pool), then removed together
        // with the sapphire key linked to it.
        require(first.relicCount == 0 && !first.sapphireKey, "the face must empty the first chest");
    } else {
        require(first.relicCount == 1 && first.relics[0] == RelicId::ANCHOR && first.sapphireKey,
                "legacy chest relic");
    }
    require(gc.commonRelicPool == std::vector<RelicId>{RelicId::LANTERN}, "the chest relic leaves the pool");
    require(gc.relics.getRelicValue(RelicId::NLOTHS_HUNGRY_FACE) == 0, "face counter after the chest");

    gc.openTreasureRoomChest();
    const auto &second = gc.info.rewardsContainer;
    require(second.relicCount == 1 && second.relics[0] == RelicId::LANTERN && second.sapphireKey,
            "second chest relic");

    // A counter imported as 1: both modes draw the relic and consume the
    // chest; only the fix also drops the linked sapphire key.
    auto imported = chestFixture();
    imported.relics.add({RelicId::NLOTHS_HUNGRY_FACE, 1});
    imported.openTreasureRoomChest();
    require(imported.info.rewardsContainer.relicCount == 0, "counter 1 must consume the chest in both modes");
    require(imported.info.rewardsContainer.sapphireKey == !fixed, "imported counter sapphire key");
    require(imported.commonRelicPool.size() == 1u, "imported counter pool draw");

    // With Matryoshka the face removes Matryoshka's relic, which comes first,
    // and the chest relic keeps its sapphire key.
    auto both = chestFixture();
    both.uncommonRelicPool = {RelicId::BLUE_CANDLE};
    both.relics.add({RelicId::NLOTHS_HUNGRY_FACE, 1});
    both.relics.add({RelicId::MATRYOSHKA, 1});
    both.openTreasureRoomChest();
    const auto &r = both.info.rewardsContainer;
    // Matryoshka draws first (common Anchor or uncommon Blue Candle), then
    // the common chest relic.
    const RelicId matryoshkaRelic = both.uncommonRelicPool.empty() ? RelicId::BLUE_CANDLE : RelicId::ANCHOR;
    const RelicId chestRelic = matryoshkaRelic == RelicId::ANCHOR ? RelicId::LANTERN : RelicId::ANCHOR;
    require(r.relicCount == 1 && r.sapphireKey, "Matryoshka + face reward count");
    require(r.relics[0] == (fixed ? chestRelic : matryoshkaRelic), "Matryoshka + face kept relic");
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
    // Three unlimited draws in both modes.
    const Potion q0 = returnRandomPotion(copy, gc.cc, false);
    const Potion q1 = returnRandomPotion(copy, gc.cc, false);
    const Potion q2 = returnRandomPotion(copy, gc.cc, false);
    if (fixed) {
        // The draws fill the brew's own slot and the empty slot in order;
        // the third finds no slot.
        expected = {q0, Potion::BLOCK_POTION, q1, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    } else {
        expected = {q0, Potion::BLOCK_POTION, q2, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    }
    require(drinkBrew(gc) == expected, "Entropic Brew slots");
    require(gc.potionCount == 3 && gc.potionRng == copy, "Entropic Brew count/RNG");

    for (int seed = 1; seed <= 50; ++seed) {
        auto full = fixture();
        full.potionCapacity = 5;
        full.potions = {Potion::ENTROPIC_BREW, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                        Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
        full.potionCount = 1;
        full.potionRng = Random(seed);
        for (const auto potion : drinkBrew(full)) {
            require(potion != Potion::EMPTY_POTION_SLOT, "a five-draw brew left a slot empty");
        }
        require(full.potionCount == 5, "five-draw brew count");
    }

    auto sozu = fixture();
    sozu.potionCapacity = 3;
    sozu.potions = {Potion::ENTROPIC_BREW, Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                    Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    sozu.potionCount = 1;
    sozu.potionRng = Random(5);
    sozu.relics.add({RelicId::SOZU, 0});
    Random sozuCopy = sozu.potionRng;
    if (!fixed) {
        for (int i = 0; i < 3; ++i) returnRandomPotion(sozuCopy, sozu.cc, false);
    }
    const auto afterSozu = drinkBrew(sozu);
    if (fixed) {
        require(sozu.potionRng == sozuCopy, "Sozu brew must draw no potion");
        require(sozu.potionCount == 0 && afterSozu[0] == Potion::EMPTY_POTION_SLOT
                && afterSozu[1] == Potion::EMPTY_POTION_SLOT && afterSozu[2] == Potion::EMPTY_POTION_SLOT,
                "Sozu must refuse brewed potions");
    } else {
        require(sozu.potionRng == sozuCopy, "legacy Sozu brew rolled every draw");
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

static void toyOrnithopter(bool fixed) {
    // Blood Potion: 20% of 80 = 16, then the relic's 5.
    auto gc = fixture();
    gc.potionCapacity = 2;
    gc.potions = {Potion::BLOOD_POTION, Potion::FRUIT_JUICE, Potion::EMPTY_POTION_SLOT,
                  Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT};
    gc.potionCount = 2;
    gc.relics.add({RelicId::TOY_ORNITHOPTER, 0});
    gc.drinkPotionAtIdx(0);
    require(gc.curHp == (fixed ? 61 : 56) && gc.potionCount == 1, "Toy Ornithopter Blood Potion heal");
    // Fruit Juice: +5 max HP (heals 5), then the relic's 5.
    gc.drinkPotionAtIdx(1);
    require(gc.maxHp == 85 && gc.curHp == (fixed ? 71 : 61) && gc.potionCount == 0,
            "Toy Ornithopter Fruit Juice heal");
    // The heal is capped by max HP and blocked by Mark of the Bloom.
    auto full = fixture();
    full.curHp = 79;
    full.potionCapacity = 1;
    full.potions[0] = Potion::FRUIT_JUICE;
    full.potionCount = 1;
    full.relics.add({RelicId::TOY_ORNITHOPTER, 0});
    full.drinkPotionAtIdx(0);
    require(full.maxHp == 85 && full.curHp == (fixed ? 85 : 84), "Toy Ornithopter heal cap");
    auto bloom = fixture();
    bloom.potionCapacity = 1;
    bloom.potions[0] = Potion::BLOOD_POTION;
    bloom.potionCount = 1;
    bloom.relics.add({RelicId::TOY_ORNITHOPTER, 0});
    bloom.relics.add({RelicId::MARK_OF_THE_BLOOM, 0});
    bloom.drinkPotionAtIdx(0);
    require(bloom.curHp == 40, "Mark of the Bloom blocks every heal");
    // Without the relic nothing extra.
    auto plain = fixture();
    plain.potionCapacity = 1;
    plain.potions[0] = Potion::BLOOD_POTION;
    plain.potionCount = 1;
    plain.drinkPotionAtIdx(0);
    require(plain.curHp == 56, "Blood Potion without Toy Ornithopter");
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
            setFlag("STS_OOC_TOY_ORNITHOPTER_FIX", value);
            toyOrnithopter(fixed);
        }
        for (const char *name : {"STS_NLOTHS_FACE_COUNTER_FIX", "STS_OOC_ENTROPIC_BREW_FIX",
                                 "STS_ASTROLABE_COLORLESS_UPGRADE_FIX", "STS_OOC_TOY_ORNITHOPTER_FIX"}) {
            setFlag(name, "2");
            bool rejected = false;
            try {
                auto gc = fixture();
                gc.potionCapacity = 1;
                gc.potions[0] = Potion::ENTROPIC_BREW;
                gc.potionCount = 1;
                gc.relics.add({RelicId::TOY_ORNITHOPTER, 0});
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
