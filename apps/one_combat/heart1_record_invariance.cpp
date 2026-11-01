// Public-record invariance fixture for the student_sel/heart1 input (#506 step 2).
//
// For every screen that buildChoice or buildPublicLeafRecord supports, states that
// differ only in private simulator fields (seed, RNG streams, encounter queues,
// second boss, pity/rarity counters, event/relic/card pools, hidden event and
// chest rolls) must give byte-identical records and identical legal actions,
// and changing one visible field must change the record. Hand-built states, no
// game seed is driven. This is simulator-side invariance, not live parity.
#include <iostream>
#include "heart1_policy.h"

#include <algorithm>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

#include "constants/Events.h"
#include "game/Map.h"
#include "game/Neow.h"

using namespace sts;

namespace one_combat::heart1 {
namespace {

[[noreturn]] void fail(const std::string &screen, const std::string &what) {
    throw std::runtime_error("heart1 public record invariance selftest: " + screen + ": " + what);
}

GameContext baseState() {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.ascension = 20;
    gc.act = 2;
    gc.floorNum = 20;
    gc.curHp = 50;
    gc.maxHp = 80;
    gc.gold = 300;
    gc.boss = MonsterEncounter::CHAMP;
    gc.keysEnabled = true;
    gc.potionCapacity = 2;
    gc.deck.obtainRaw(Card(CardId::BASH));
    gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    gc.deck.obtainRaw(Card(CardId::DEFEND_RED));
    gc.deck.obtainRaw(Card(CardId::INFLAME, 1));
    gc.relics.add({RelicId::BURNING_BLOOD, 0});
    gc.relics.add({RelicId::NUNCHAKU, 4});
    gc.map = std::make_shared<Map>();
    for (int y = 0; y < 15; ++y)
        for (int x = 0; x < 7; ++x) { gc.map->nodes[y][x].x = x; gc.map->nodes[y][x].y = y; }
    const auto node = [&](int x, int y, Room room) -> MapNode & {
        auto &n = gc.map->nodes[y][x];
        n.room = room;
        return n;
    };
    node(1, 0, Room::MONSTER).addEdge(1);
    node(3, 0, Room::MONSTER).addEdge(4);
    node(1, 1, Room::EVENT).addEdge(2);
    node(4, 1, Room::SHOP).addEdge(3);
    node(2, 2, Room::ELITE);
    node(3, 2, Room::REST);
    gc.map->burningEliteX = 2;
    gc.map->burningEliteY = 2;
    gc.curMapNodeX = -1;
    gc.curMapNodeY = -1;
    // Two normal fights and one elite already fought this act (v2 record input).
    gc.monsterList.push_back(MonsterEncounter::SPHERIC_GUARDIAN);
    gc.monsterList.push_back(MonsterEncounter::CHOSEN);
    gc.monsterListOffset = 2;
    gc.eliteMonsterList.push_back(MonsterEncounter::SLAVERS);
    gc.eliteMonsterListOffset = 1;
    gc.shopRemoveCount = 1;
    return gc;
}

// Changes every private field the record must not depend on. k selects one of
// several distinct realizations.
void scramblePrivate(GameContext &gc, int k) {
    gc.seed = 1000003ULL * (k + 1);
    Random *streams[] = {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                         &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                         &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng};
    int i = 0;
    for (auto *rng : streams) *rng = Random(97ULL * (k + 1) + i++);
    // The consumed queue prefix (encounters already fought) is public; only the
    // unconsumed suffix is private.
    gc.monsterList.resize(std::min<int>(gc.monsterListOffset, gc.monsterList.size()));
    gc.eliteMonsterList.resize(std::min<int>(gc.eliteMonsterListOffset, gc.eliteMonsterList.size()));
    const MonsterEncounter normals[] = {MonsterEncounter::CULTIST, MonsterEncounter::JAW_WORM,
                                        MonsterEncounter::SNECKO, MonsterEncounter::CHOSEN};
    const MonsterEncounter elites[] = {MonsterEncounter::GREMLIN_LEADER, MonsterEncounter::SLAVERS,
                                       MonsterEncounter::BOOK_OF_STABBING};
    for (int j = 0; j < 4; ++j) gc.monsterList.push_back(normals[(j + k) % 4]);
    for (int j = 0; j < 3; ++j) gc.eliteMonsterList.push_back(elites[(j + k) % 3]);
    gc.secondBoss = k % 2 ? MonsterEncounter::TIME_EATER : MonsterEncounter::AWAKENED_ONE;
    gc.potionChance = 10 * k - 20;
    gc.cardRarityFactor = -40 + 9 * k;
    gc.monsterChance = 0.1f * k;
    gc.shopChance = 0.03f * k;
    gc.treasureChance = 0.02f * k;
    gc.eventList = k % 2 ? std::vector<Event>{Event::BIG_FISH} : std::vector<Event>{};
    gc.shrineList = {Event::GOLDEN_SHRINE, Event::PURIFIER};
    std::rotate(gc.shrineList.begin(), gc.shrineList.begin() + k % 2, gc.shrineList.end());
    gc.specialOneTimeEventList = k % 2 ? std::vector<Event>{Event::NLOTH} : std::vector<Event>{};
    gc.commonRelicPool = {RelicId::ANCHOR, RelicId::ORICHALCUM};
    gc.uncommonRelicPool = {RelicId::KUNAI};
    gc.rareRelicPool = k % 2 ? std::vector<RelicId>{RelicId::GIRYA} : std::vector<RelicId>{};
    gc.shopRelicPool = {RelicId::CAULDRON};
    gc.bossRelicPool = {RelicId::SOZU, RelicId::ECTOPLASM};
    std::rotate(gc.bossRelicPool.begin(), gc.bossRelicPool.begin() + k % 2, gc.bossRelicPool.end());
    std::rotate(gc.colorlessCardPool.begin(), gc.colorlessCardPool.begin() + k, gc.colorlessCardPool.end());
    // Hidden rolls stored on the screen: chest contents before opening and the
    // Dead Adventurer reward order.
    gc.info.tier = k % 2 ? RelicTier::RARE : RelicTier::COMMON;
    gc.info.haveGold = k % 2;
    gc.info.rewards = {k % 3, (k + 1) % 3, (k + 2) % 3};
}

std::vector<std::uint32_t> actionBits(const Choice &c) {
    std::vector<std::uint32_t> bits;
    for (const auto &a : c.actions) bits.push_back(a.bits);
    return bits;
}

// Records and actions for a state; leaf-only screens (battle start) have no Choice.
struct Observed {
    nlohmann::json leaf;
    bool choice = false;
    nlohmann::json record;
    std::vector<std::uint32_t> actions;
};

Observed observe(const std::string &screen, const GameContext &gc) {
    Observed o;
    std::string reason;
    if (!buildPublicLeafRecord(gc, o.leaf, &reason)) fail(screen, "leaf record unsupported: " + reason);
    Choice c;
    if (gc.screenState != ScreenState::BATTLE) {
        if (!buildChoice(gc, c, &reason)) fail(screen, "choice unsupported: " + reason);
        o.choice = true;
        o.record = recordToJson(c.record);
        o.actions = actionBits(c);
        if (o.actions.empty()) fail(screen, "fixture offers no actions");
    }
    return o;
}

void check(const std::string &screen, const GameContext &gc,
           const std::vector<std::function<void(GameContext &)>> &publicChanges) {
    const auto base = observe(screen, gc);
    for (int k = 0; k < 3; ++k) {
        auto altered = gc;
        scramblePrivate(altered, k);
        const auto got = observe(screen, altered);
        if (got.leaf != base.leaf || got.record != base.record)
            fail(screen, "record depends on private state (realization " + std::to_string(k) + ")");
        if (got.actions != base.actions)
            fail(screen, "legal choice tokens depend on private state (realization " + std::to_string(k) + ")");
    }
    int i = 0;
    for (const auto &change : publicChanges) {
        auto altered = gc;
        change(altered);
        const auto got = observe(screen, altered);
        if (got.leaf == base.leaf && got.record == base.record)
            fail(screen, "public change " + std::to_string(i) + " left the record unchanged");
        ++i;
    }
}

}  // namespace

void publicRecordInvarianceSelfTest() {
    const auto relicCounter = [](GameContext &g) { g.relics.getRelicValueRef(RelicId::NUNCHAKU) = 7; };
    const auto hp = [](GameContext &g) { g.curHp = 49; };
    const auto deckUpgrade = [](GameContext &g) { g.deck.cards[0].upgraded = 1; };

    {
        auto gc = baseState();
        gc.screenState = ScreenState::MAP_SCREEN;
        check("map", gc, {hp, relicCounter,
            [](GameContext &g) { g.map->nodes[2][3].room = Room::TREASURE; },
            [](GameContext &g) { g.map->burningEliteX = -1; g.map->burningEliteY = -1; },
            [](GameContext &g) { g.boss = MonsterEncounter::AUTOMATON; },
            [](GameContext &g) { g.monsterList[1] = MonsterEncounter::SHELL_PARASITE; },
            [](GameContext &g) { g.eliteMonsterListOffset = 0; },
            [](GameContext &g) { g.shopRemoveCount = 2; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::REWARDS;
        auto &r = gc.info.rewardsContainer;
        r.addGold(25);
        CardReward cards;
        cards.push_back(Card(CardId::POMMEL_STRIKE));
        cards.push_back(Card(CardId::SHRUG_IT_OFF));
        cards.push_back(Card(CardId::CARNAGE));
        r.addCardReward(cards);
        r.addPotion(Potion::BLOCK_POTION);
        r.addRelic(RelicId::ANCHOR);
        check("rewards", gc, {deckUpgrade,
            [](GameContext &g) { g.info.rewardsContainer.cardRewards[0][1] = Card(CardId::UPPERCUT); },
            [](GameContext &g) { g.info.rewardsContainer.relics[0] = RelicId::KUNAI; },
            [](GameContext &g) { g.info.rewardsContainer.potions[0] = Potion::FIRE_POTION; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::SHOP_ROOM;
        gc.curRoom = Room::SHOP;
        auto &s = gc.info.shop;
        const CardId ids[] = {CardId::POMMEL_STRIKE, CardId::TRUE_GRIT, CardId::CARNAGE, CardId::DISARM,
                              CardId::IMPERVIOUS, CardId::FINESSE, CardId::APOTHEOSIS};
        for (int i = 0; i < 7; ++i) s.cards[i] = Card(ids[i]);
        s.relics[0] = RelicId::ANCHOR; s.relics[1] = RelicId::KUNAI; s.relics[2] = RelicId::CAULDRON;
        s.potions[0] = Potion::BLOCK_POTION; s.potions[1] = Potion::FIRE_POTION; s.potions[2] = Potion::SWIFT_POTION;
        for (int &p : s.prices) p = 60;
        s.removeCost = 100;
        check("shop", gc, {relicCounter,
            [](GameContext &g) { g.info.shop.cards[2] = Card(CardId::OFFERING); },
            [](GameContext &g) { g.info.shop.relics[1] = RelicId::ORICHALCUM; },
            [](GameContext &g) { g.gold = 50; },
            [](GameContext &g) { g.info.shop.cardPrice(3) = 61; },
            [](GameContext &g) { g.info.shop.relicPrice(0) = 61; },
            [](GameContext &g) { g.info.shop.potionPrice(2) = 61; },
            [](GameContext &g) { g.info.shop.removeCost = 125; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::BOSS_RELIC_REWARDS;
        gc.info.bossRelics[0] = RelicId::SOZU;
        gc.info.bossRelics[1] = RelicId::ECTOPLASM;
        gc.info.bossRelics[2] = RelicId::RUNIC_DOME;
        check("boss relic", gc, {hp, [](GameContext &g) { g.info.bossRelics[2] = RelicId::CURSED_KEY; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::REST_ROOM;
        gc.curRoom = Room::REST;
        check("rest", gc, {hp, relicCounter, [](GameContext &g) { g.redKey = true; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::CARD_SELECT;
        gc.info.selectScreenType = CardSelectScreenType::UPGRADE;
        gc.info.toSelectCount = 1;
        for (int i = 0; i < 3; ++i) gc.info.toSelectCards.push_back({gc.deck.cards[i], static_cast<std::int16_t>(i)});
        check("card select", gc, {
            [](GameContext &g) { g.info.toSelectCards[1].card = Card(CardId::ANGER); },
            [](GameContext &g) { g.info.selectScreenType = CardSelectScreenType::REMOVE; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::TREASURE_ROOM;
        gc.curRoom = Room::TREASURE;
        check("treasure", gc, {hp});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::EVENT_SCREEN;
        gc.curEvent = Event::FACE_TRADER;
        gc.info.hpAmount0 = 8;
        check("event face trader", gc, {[](GameContext &g) { g.info.hpAmount0 = 9; }});
        gc.curEvent = Event::DEAD_ADVENTURER;
        gc.info.encounter = MonsterEncounter::GREMLIN_NOB;  // named by the event text
        check("event dead adventurer", gc, {hp});
        gc.curEvent = Event::WE_MEET_AGAIN;
        gc.info.potionIdx = -1;
        gc.info.gold = 50;
        gc.info.cardIdx = 1;
        check("event we meet again", gc, {[](GameContext &g) { g.info.gold = 60; },
                                          [](GameContext &g) { g.info.cardIdx = 2; }});
        gc.curEvent = Event::NEOW;
        gc.floorNum = 0;
        gc.info.neowRewards = {Neow::Option{Neow::Bonus::THREE_CARDS, Neow::Drawback::NONE},
                               Neow::Option{Neow::Bonus::UPGRADE_CARD, Neow::Drawback::NONE},
                               Neow::Option{Neow::Bonus::REMOVE_CARD, Neow::Drawback::CURSE},
                               Neow::Option{Neow::Bonus::RANDOM_COLORLESS, Neow::Drawback::NONE}};
        check("event neow", gc, {[](GameContext &g) { g.info.neowRewards[2].d = Neow::Drawback::NO_GOLD; }});
    }
    {
        auto gc = baseState();
        gc.screenState = ScreenState::BATTLE;
        gc.curRoom = Room::MONSTER;
        gc.info.encounter = MonsterEncounter::SNAKE_PLANT;
        check("battle start", gc, {hp, [](GameContext &g) { g.info.encounter = MonsterEncounter::CENTURION_AND_HEALER; }});
    }
}


// PPO full-coverage tokens (ChoiceOptions::fullCoverage): potion discards, Match and
// Keep slots and unmapped event options; the default options keep the trained space.
void ppoCoverageSelfTest() {
    const auto require = [](bool ok, const std::string &what) {
        if (!ok) throw std::runtime_error("heart1 ppo coverage selftest: " + what);
    };
    ChoiceOptions full;
    full.fullCoverage = true;
    full.keyMask = false;
    {
        // Full potion slots and a potion reward: one discard token per held potion.
        auto gc = baseState();
        gc.screenState = ScreenState::REWARDS;
        gc.potions[0] = Potion::FIRE_POTION;
        gc.potions[1] = Potion::BLOCK_POTION;
        gc.potionCount = 2;
        auto &r = gc.info.rewardsContainer;
        CardReward cards;
        cards.push_back(Card(CardId::POMMEL_STRIKE));
        r.addCardReward(cards);
        r.addPotion(Potion::STRENGTH_POTION);
        Choice plain, ppo;
        require(buildChoice(gc, plain), "default rewards choice");
        require(buildChoice(gc, ppo, nullptr, full), "full rewards choice");
        require(ppo.record.choiceCount() == plain.record.choiceCount() + 2, "two discard tokens");
        for (const auto &f : plain.record.fixedActions) require(f.potion == -1, "default tokens carry no potion");
        int discards = 0;
        for (std::size_t i = 0; i < ppo.record.fixedActions.size(); ++i) {
            const auto &f = ppo.record.fixedActions[i];
            if (f.action != kFaDiscardPotion) continue;
            const auto &a = ppo.actions[ppo.record.offeredCards.size() + ppo.record.offeredRelics.size()
                                        + ppo.record.offeredPotions.size() + i];
            require(a.isPotionAction() && a.isPotionDiscard(), "discard token runs a discard");
            require(f.potion == static_cast<int>(gc.potions[a.getIdx1()]), "discard token names its potion");
            auto copy = gc;
            a.execute(copy);
            require(copy.potions[a.getIdx1()] == Potion::EMPTY_POTION_SLOT && copy.potionCount == 1, "slot emptied");
            ++discards;
        }
        require(discards == 2, "discard count");
        require(recordFromJson(recordToJson(ppo.record)) == ppo.record, "JSON round trip with potion");
        require(recordToJson(plain.record).dump().find("\"potion\"") == std::string::npos, "default JSON unchanged");
        // A free slot: no discard tokens.
        gc.potions[1] = Potion::EMPTY_POTION_SLOT;
        gc.potionCount = 1;
        require(buildChoice(gc, ppo, nullptr, full) && ppo.record.choiceCount() == plain.record.choiceCount() + 1,
                "free slot: the potion reward itself, no discard");
        for (const auto &f : ppo.record.fixedActions) require(f.action != kFaDiscardPotion, "no discard with a free slot");
    }
    {
        // Match and Keep: unseen slot, seen twin of the face-up card, a matched pair.
        auto gc = baseState();
        gc.screenState = ScreenState::EVENT_SCREEN;
        gc.curEvent = Event::MATCH_AND_KEEP;
        gc.info.eventData = 4;
        gc.info.toSelectCards.clear();
        gc.info.toSelectCards.push_back(SelectScreenCard(Card(CardId::CARNAGE), GameContext::MATCH_AND_KEEP_UNSEEN));
        gc.info.toSelectCards.push_back(SelectScreenCard(Card(CardId::INFLAME), GameContext::MATCH_AND_KEEP_SEEN));
        gc.info.toSelectCards.push_back(SelectScreenCard(Card(CardId::INFLAME), GameContext::MATCH_AND_KEEP_FACE_UP));
        gc.info.toSelectCards.push_back(SelectScreenCard(Card(CardId::BASH), GameContext::MATCH_AND_KEEP_MATCHED));
        gc.info.toSelectCards.push_back(SelectScreenCard(Card(CardId::SHRUG_IT_OFF), GameContext::MATCH_AND_KEEP_SEEN));
        Choice c;
        std::string reason;
        require(!buildChoice(gc, c, &reason) && reason == "match_and_keep", "default declines Match and Keep");
        require(buildChoice(gc, c, &reason, full), "full Match and Keep: " + reason);
        const auto &f = c.record.fixedActions;
        require(f.size() == 3 && c.actions.size() == 3, "three open slots");
        require(f[0].action == kFaMatchUnseen && f[0].card == static_cast<int>(CardId::INFLAME) && f[0].gold == 4,
                "unseen slot names the face-up card and the attempts");
        require(f[1].action == kFaMatchPair && f[1].card == static_cast<int>(CardId::INFLAME), "pair slot");
        require(f[2].action == kFaMatchSeen && f[2].card == static_cast<int>(CardId::SHRUG_IT_OFF), "seen slot");
        require(c.actions[0].getIdx1() == 0 && c.actions[1].getIdx1() == 1 && c.actions[2].getIdx1() == 4,
                "slot actions");
        // The unseen slot's card is private.
        auto hidden = gc;
        hidden.info.toSelectCards[0].card = Card(CardId::OFFERING);
        Choice h;
        require(buildChoice(hidden, h, nullptr, full) && recordToJson(h.record) == recordToJson(c.record),
                "record independent of an unseen card");
    }
    {
        // An event option without a silverbot mapping (Falling, out-of-range option).
        auto gc = baseState();
        gc.screenState = ScreenState::EVENT_SCREEN;
        gc.curEvent = Event::FALLING;
        Choice c;
        const auto a = search::GameAction::getAllActionsInState(gc);
        if (std::any_of(a.begin(), a.end(), [](const search::GameAction &x) { return x.getIdx1() >= 4; })) {
            require(buildChoice(gc, c, nullptr, full), "unmapped option is a token");
            require(std::any_of(c.record.fixedActions.begin(), c.record.fixedActions.end(), [](const FixedChoice &f) {
                return f.action >= kFaEventOption0 && f.gold == static_cast<int>(Event::FALLING); }), "event token");
        }
    }
    std::cout << "heart1 ppo coverage selftest passed\n";
}

}  // namespace one_combat::heart1
