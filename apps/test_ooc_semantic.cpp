#include <algorithm>
#include <functional>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "ooc_test_state.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace {
using namespace sts;
using namespace sts::search;
using Effect = OocSemanticEffect;
using Source = OocSemanticSource;
using Type = GameAction::RewardsActionType;
using Predicate = std::function<bool(const OocSemanticAction &)>;
int checks = 0;

void require(bool yes, const std::string &message) {
    ++checks;
    if (!yes) throw std::runtime_error(message);
}

GameContext fixture(ScreenState screen) {
    // All scenarios clone one deterministic seed; no campaign traversal.
    static const GameContext initial(CharacterClass::IRONCLAD, 0x51514Du, 0);
    auto gc = test::cloneOocTestState(initial);
    gc.screenState = screen;
    gc.gold = 500;
    gc.curHp = 40;
    gc.curEvent = Event::INVALID;
    gc.regainControlAction = [](GameContext &g) {
        ++g.info.eventData;
        g.screenState = ScreenState::MAP_SCREEN;
        g.regainControlAction = nullptr;
    };
    return gc;
}

void primitive(GameContext &gc, GameAction action) {
    require(action.isValidAction(gc), "independent manual primitive is illegal");
    action.execute(gc);
}

std::vector<OocSemanticAction> enumerate(const GameContext &gc) {
    const auto before = test::oocStateFingerprint(gc);
    const auto first = enumerateOocSemanticActions(gc);
    const auto second = enumerateOocSemanticActions(gc);
    require(first.supported && first.complete && first.error.empty(),
            "enumeration unsupported/incomplete: " + first.error);
    require(before == test::oocStateFingerprint(gc), "enumeration mutated state or RNG");
    std::vector<std::string> a, b;
    for (const auto &action : first.actions) a.push_back(canonicalOocSemanticActionKey(action));
    for (const auto &action : second.actions) b.push_back(canonicalOocSemanticActionKey(action));
    require(a == b, "repeated enumeration changed keys/order");
    require(std::is_sorted(a.begin(), a.end()), "enumeration keys are not canonical sorted");
    require(std::set<std::string>(a.begin(), a.end()).size() == a.size(), "duplicate semantic keys");
    return first.actions;
}

OocSemanticAction find(const GameContext &gc, Effect effect, Predicate predicate = {}) {
    for (const auto &a : enumerate(gc))
        if (a.effect == effect && (!predicate || predicate(a))) return a;
    throw std::runtime_error("required semantic effect absent: " + std::to_string(int(effect)));
}

void unchangedFailure(GameContext &gc, const OocSemanticAction &action) {
    const auto before = test::oocStateFingerprint(gc);
    const auto result = executeOocSemanticAction(gc, action);
    require(!result.ok && !result.error.empty(), "stale/ambiguous action accepted");
    require(before == test::oocStateFingerprint(gc), "rejected action mutated state/RNG");
}

int bottleSlot(const Deck &deck, int idx) {
    for (int slot = 0; slot < 3; ++slot) if (deck.bottleIdxs[slot] == idx) return slot;
    return -1;
}

bool matches(const Deck &deck, int idx, const OocCardTarget &target) {
    const auto same = [&](int i) {
        const auto &c = deck.cards[i];
        return c.id == target.id && c.misc == target.misc && c.upgraded == target.upgraded
            && bottleSlot(deck, i) == target.bottleSlot;
    };
    if (!same(idx)) return false;
    unsigned occurrence = 0;
    for (int i = 0; i < idx; ++i) if (same(i)) ++occurrence;
    return occurrence == target.occurrence;
}

// Resolve only after the independently specified source primitive has opened
// its actual live selector. Never infer the manual route from execution traces.
void select(GameContext &gc, const OocSemanticAction &a) {
    require(gc.screenState == ScreenState::CARD_SELECT, "manual source did not open selector");
    const OocCardTarget *deckTarget = std::get_if<OocCardTarget>(&a.target);
    const OocCandidateTarget *candidate = nullptr;
    if (const auto *t = std::get_if<OocTransactionTarget>(&a.target)) deckTarget = &t->card;
    if (const auto *t = std::get_if<OocSelectorTarget>(&a.target)) {
        deckTarget = std::get_if<OocCardTarget>(&t->card);
        candidate = std::get_if<OocCandidateTarget>(&t->card);
    }
    int found = -1;
    unsigned occurrence = 0;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i) {
        const auto &c = gc.info.toSelectCards[i];
        bool match = deckTarget && c.deckIdx >= 0 && c.deckIdx < gc.deck.size()
            && matches(gc.deck, c.deckIdx, *deckTarget);
        if (candidate && c.card.id == candidate->card.id && c.card.misc == candidate->card.misc
                && c.card.upgraded == candidate->card.upgraded)
            match = occurrence++ == candidate->occurrence;
        if (match) {
            require(found == -1, "manual target ambiguous");
            found = i;
        }
    }
    require(found >= 0, "manual target absent");
    primitive(gc, GameAction(found));
}

using Manual = std::function<void(GameContext &, const OocSemanticAction &)>;
GameContext parity(const GameContext &base, const OocSemanticAction &action, const Manual &manual) {
    auto expected = test::cloneOocTestState(base);
    auto actual = test::cloneOocTestState(base);
    const GameContext heldSibling = actual; // Deliberately retain the pre-commit map alias.
    const auto siblingBefore = test::oocStateFingerprint(heldSibling);
    require(!base.map || (expected.map.get() != base.map.get() && actual.map.get() != base.map.get()),
            "test clones alias mutable map");
    manual(expected, action);
    const auto result = executeOocSemanticAction(actual, action);
    require(result.ok, "semantic execution rejected legal action: " + result.error);
    require(test::oocStateFingerprint(heldSibling) == siblingBefore,
            "successful transaction mutated a sibling sharing its original map");
    require(test::oocStateFingerprint(actual) == test::oocStateFingerprint(expected),
            "semantic/manual complete state differs for " + canonicalOocSemanticActionKey(action));
    // Exercise opaque continuation behavior when the action leaves a room with
    // a normal leave button. Selector completion is checked by selector tests.
    if (actual.screenState == ScreenState::REWARDS || actual.screenState == ScreenState::SHOP_ROOM) {
        auto expectedLeave = test::cloneOocTestState(expected);
        auto actualLeave = test::cloneOocTestState(actual);
        primitive(expectedLeave, GameAction(Type::SKIP));
        primitive(actualLeave, GameAction(Type::SKIP));
        require(test::oocStateFingerprint(actualLeave) == test::oocStateFingerprint(expectedLeave),
                "continuations differ after identical primitive leave");
    }
    return actual;
}

Manual direct(GameAction action) {
    return [action](GameContext &g, const OocSemanticAction &) { primitive(g, action); };
}
Manual compound(GameAction source) {
    return [source](GameContext &g, const OocSemanticAction &a) { primitive(g, source); select(g, a); };
}

GameContext rewards() {
    auto g = fixture(ScreenState::REWARDS);
    Rewards r;
    r.addGold(25);
    r.addRelic(RelicId::ANCHOR);
    r.addPotion(Potion::FIRE_POTION);
    CardReward cards;
    cards.push_back(Card(CardId::INFLAME));
    cards.push_back(Card(CardId::BASH));
    r.addCardReward(cards);
    g.info.rewardsContainer = r;
    return g;
}

void testCampfireAndShop() {
    auto fire = fixture(ScreenState::REST_ROOM);
    fire.relics.add({RelicId::PEACE_PIPE, 0});
    parity(fire, find(fire, Effect::REMOVE_CARD), compound(GameAction(4)));
    parity(fire, find(fire, Effect::UPGRADE_CARD), compound(GameAction(1)));
    for (const auto &[effect, idx] : std::vector<std::pair<Effect, int>>{
            {Effect::REST, 0}, {Effect::TAKE_RUBY_KEY, 2}})
        parity(fire, find(fire, effect), direct(GameAction(idx)));
    fire.relics.add({RelicId::GIRYA, 0});
    fire.relics.add({RelicId::SHOVEL, 0});
    parity(fire, find(fire, Effect::LIFT), direct(GameAction(3)));
    parity(fire, find(fire, Effect::DIG), direct(GameAction(5)));
    auto staleFire = find(fire, Effect::REMOVE_CARD);
    fire.relics.remove(RelicId::PEACE_PIPE);
    unchangedFailure(fire, staleFire);

    auto shop = fixture(ScreenState::SHOP_ROOM);
    std::fill(std::begin(shop.info.shop.prices), std::end(shop.info.shop.prices), -1);
    shop.info.shop.cards[0] = Card(CardId::INFLAME);
    shop.info.shop.cardPrice(0) = 42;
    shop.info.shop.relics[0] = RelicId::ANCHOR;
    shop.info.shop.relicPrice(0) = 80;
    shop.info.shop.potions[0] = Potion::FIRE_POTION;
    shop.info.shop.potionPrice(0) = 20;
    shop.info.shop.removeCost = 75;
    parity(shop, find(shop, Effect::REMOVE_CARD), compound(GameAction(Type::CARD_REMOVE)));
    for (const auto &[effect, type] : std::vector<std::pair<Effect, Type>>{
            {Effect::BUY_CARD, Type::CARD}, {Effect::BUY_RELIC, Type::RELIC},
            {Effect::BUY_POTION, Type::POTION}, {Effect::LEAVE_SHOP, Type::SKIP}})
        parity(shop, find(shop, effect), direct(GameAction(type)));
    auto oldPrice = find(shop, Effect::BUY_CARD);
    ++shop.info.shop.cardPrice(0);
    unchangedFailure(shop, oldPrice);
    auto oldRemoval = find(shop, Effect::REMOVE_CARD);
    ++shop.info.shop.removeCost;
    unchangedFailure(shop, oldRemoval);
    shop.relics.add({RelicId::THE_COURIER, 0});
    const auto after = parity(shop, find(shop, Effect::BUY_CARD), direct(GameAction(Type::CARD)));
    require(after.info.shop.cardPrice(0) >= 0, "Courier failed to restock card");
    require(after.mathUtilRng.counter != shop.mathUtilRng.counter, "Courier fixture did not consume restock RNG");
    enumerate(after);
}

void testRewardsAndTreasure(bool includeSelectors) {
    auto g = rewards();
    for (const auto &[effect, type] : std::vector<std::pair<Effect, Type>>{
            {Effect::TAKE_CARD, Type::CARD}, {Effect::TAKE_GOLD, Type::GOLD},
            {Effect::TAKE_RELIC, Type::RELIC}, {Effect::TAKE_POTION, Type::POTION},
            {Effect::LEAVE_REWARDS, Type::SKIP}}) {
        auto a = find(g, effect, [effect](const auto &action) {
            return effect != Effect::TAKE_CARD
                || std::get<Card>(std::get<OocRewardTarget>(action.target).entity).id == CardId::INFLAME;
        });
        auto after = parity(g, a, direct(GameAction(type)));
        if (effect == Effect::TAKE_CARD || effect == Effect::TAKE_GOLD || effect == Effect::TAKE_RELIC) {
            require(after.screenState == ScreenState::REWARDS, "taking one reward lost remaining screen");
            for (auto remaining : {Effect::TAKE_CARD, Effect::TAKE_GOLD, Effect::TAKE_RELIC})
                if (effect != remaining) (void)find(after, remaining);
        }
        if (effect == Effect::TAKE_GOLD) unchangedFailure(after, a);
    }

    auto full = rewards();
    full.potionCapacity = 3;
    full.potionCount = 3;
    full.potions[0] = Potion::FIRE_POTION;
    full.potions[1] = Potion::STRENGTH_POTION;
    full.potions[2] = Potion::DEXTERITY_POTION;
    full.potions[3] = Potion::EMPTY_POTION_SLOT;
    full.potions[4] = Potion::EMPTY_POTION_SLOT;
    auto fullActions = enumerate(full);
    require(std::none_of(fullActions.begin(), fullActions.end(), [](const auto &action) {
        return action.effect == Effect::TAKE_POTION;
    }), "full potion inventory exposed an executable potion reward");
    (void)find(full, Effect::TAKE_CARD);
    (void)find(full, Effect::LEAVE_REWARDS);
    require(!GameAction(Type::POTION, 0).isValidAction(full),
            "full potion inventory accepted a direct potion reward primitive");
    parity(g, find(g, Effect::SKIP_CARD_REWARD), direct(GameAction(Type::CARD, 0, 5)));
    g.relics.add({RelicId::SINGING_BOWL, 0});
    auto bowl = parity(g, find(g, Effect::SINGING_BOWL), direct(GameAction(Type::CARD, 0, 5)));
    require(bowl.maxHp == g.maxHp + 2, "Singing Bowl did not increase maximum HP");
    for (bool sapphire : {false, true}) {
        auto keyed = rewards();
        keyed.info.rewardsContainer.sapphireKey = sapphire;
        keyed.info.rewardsContainer.emeraldKey = !sapphire;
        parity(keyed, find(keyed, Effect::TAKE_KEY), direct(GameAction(Type::KEY)));
    }
    if (includeSelectors) {
        auto bottle = rewards();
        bottle.info.rewardsContainer.relics[0] = RelicId::BOTTLED_FLAME;
        auto bottled = parity(bottle, find(bottle, Effect::TAKE_RELIC), direct(GameAction(Type::RELIC)));
        auto selected = parity(bottled, find(bottled, Effect::BOTTLE_CARD), select);
        require(selected.screenState == ScreenState::REWARDS, "bottle selector lost original rewards");
        (void)find(selected, Effect::TAKE_CARD);
        (void)find(selected, Effect::TAKE_GOLD);
    }

    auto chest = fixture(ScreenState::TREASURE_ROOM);
    chest.info.chestSize = ChestSize::SMALL;
    chest.info.tier = RelicTier::COMMON;
    chest.info.haveGold = true;
    parity(chest, find(chest, Effect::OPEN_CHEST), direct(GameAction(0)));
    parity(chest, find(chest, Effect::LEAVE_TREASURE), direct(GameAction(1)));
}

void testTransactionIdentityAndRollback() {
    auto failing = fixture(ScreenState::REST_ROOM);
    failing.regainControlAction = [](GameContext &next) {
        next.map->nodes[0][0].x += 100;
        next.info.eventData += 10;
        next.screenState = ScreenState::BATTLE;
    };
    const auto smith = find(failing, Effect::UPGRADE_CARD);
    const auto originalMap = failing.map;
    unchangedFailure(failing, smith);
    require(failing.map == originalMap, "failed transaction replaced original map ownership");

    auto grouped = rewards();
    CardReward later;
    later.push_back(Card(CardId::JAX));
    grouped.info.rewardsContainer.addCardReward(later);
    const auto takeLater = find(grouped, Effect::TAKE_CARD, [](const auto &a) {
        return std::get<Card>(std::get<OocRewardTarget>(a.target).entity).id == CardId::JAX;
    });
    primitive(grouped, GameAction(Type::CARD, 0, 0));
    require(grouped.info.rewardsContainer.cardRewardCount == 1, "earlier group removal fixture failed");
    parity(grouped, takeLater, direct(GameAction(Type::CARD, 0, 0)));
    grouped = rewards();
    grouped.info.rewardsContainer.addGold(51);
    const auto secondGold = find(grouped, Effect::TAKE_GOLD, [](const auto &a) {
        return std::get<int>(std::get<OocRewardTarget>(a.target).entity) == 51;
    });
    const auto richer = parity(grouped, secondGold, direct(GameAction(Type::GOLD, 1)));
    require(richer.gold == grouped.gold + 51 && richer.info.rewardsContainer.gold[0] == 25,
            "second gold semantic action took the wrong reward");

    auto shop = fixture(ScreenState::SHOP_ROOM);
    std::fill(std::begin(shop.info.shop.prices), std::end(shop.info.shop.prices), -1);
    shop.info.shop.removeCost = -1;
    shop.info.shop.cards[0] = Card(CardId::INFLAME);
    shop.info.shop.cardPrice(0) = 42;
    shop.info.shop.cards[1] = Card(CardId::BASH);
    shop.info.shop.cardPrice(1) = 61;
    const auto buyInflame = find(shop, Effect::BUY_CARD, [](const auto &a) {
        return std::get<Card>(std::get<OocShopTarget>(a.target).entity).id == CardId::INFLAME;
    });
    std::vector<std::string> beforeKeys;
    for (const auto &a : enumerate(shop)) beforeKeys.push_back(canonicalOocSemanticActionKey(a));
    std::swap(shop.info.shop.cards[0], shop.info.shop.cards[1]);
    std::swap(shop.info.shop.cardPrice(0), shop.info.shop.cardPrice(1));
    std::vector<std::string> afterKeys;
    for (const auto &a : enumerate(shop)) afterKeys.push_back(canonicalOocSemanticActionKey(a));
    require(beforeKeys == afterKeys, "shop key identity depends on inventory slot");
    parity(shop, buyInflame, direct(GameAction(Type::CARD, 1)));
}

void testEvents() {
    struct Row { Event event; Effect effect; int option; };
    const Row rows[] = {
        {Event::OMINOUS_FORGE, Effect::UPGRADE_CARD, 0},
        {Event::ANCIENT_WRITING, Effect::REMOVE_CARD, 0},
        {Event::OLD_BEGGAR, Effect::REMOVE_CARD, 0},
        {Event::DESIGNER_IN_SPIRE, Effect::UPGRADE_CARD, 0},
        {Event::DESIGNER_IN_SPIRE, Effect::REMOVE_CARD, 2},
        {Event::DESIGNER_IN_SPIRE, Effect::REMOVE_CARD, 4},
        {Event::DUPLICATOR, Effect::DUPLICATE_CARD, 0},
        {Event::LIVING_WALL, Effect::REMOVE_CARD, 0},
        {Event::LIVING_WALL, Effect::TRANSFORM_CARD, 1},
        {Event::LIVING_WALL, Effect::UPGRADE_CARD, 2},
        {Event::PURIFIER, Effect::REMOVE_CARD, 0},
        {Event::THE_CLERIC, Effect::REMOVE_CARD, 1},
        {Event::TRANSMORGRIFIER, Effect::TRANSFORM_CARD, 0},
        {Event::UPGRADE_SHRINE, Effect::UPGRADE_CARD, 0},
        {Event::WING_STATUE, Effect::REMOVE_CARD, 0},
    };
    for (int ascension : {0, 15}) for (const auto &row : rows) {
        auto g = fixture(ScreenState::EVENT_SCREEN);
        g.ascension = ascension;
        g.curEvent = row.event;
        g.info.upgradeOne = true;
        g.info.cleanUpIsRemoveCard = true;
        const auto action = find(g, row.effect, [&](const auto &a) {
            const auto *target = std::get_if<OocTransactionTarget>(&a.target);
            return target && target->option == row.option;
        });
        const auto after = parity(g, action, compound(GameAction(row.option)));
        require(after.screenState == ScreenState::MAP_SCREEN, "event compound did not complete callback");
        if (row.event == Event::DESIGNER_IN_SPIRE && row.option == 4)
            require(after.miscRng.counter > g.miscRng.counter, "Designer4 upgrade continuation not executed");
        auto stale = test::cloneOocTestState(g);
        stale.curEvent = Event::INVALID;
        unchangedFailure(stale, action);
        if (row.event == Event::OLD_BEGGAR) {
            stale = test::cloneOocTestState(g);
            stale.gold = 0;
            unchangedFailure(stale, action);
        }
    }
    auto library = fixture(ScreenState::EVENT_SCREEN);
    library.curEvent = Event::THE_LIBRARY;
    const auto sourceActions = enumerate(library);
    require(!sourceActions.empty(), "Library lacks source choices");
    for (const auto &a : sourceActions)
        require(a.effect == Effect::EVENT_CHOICE && std::holds_alternative<OocEventTarget>(a.target),
                "Library source leaked unrevealed card choices");
    const auto read = find(library, Effect::EVENT_CHOICE, [](const auto &a) {
        return std::get<OocEventTarget>(a.target).option == 0;
    });
    auto revealed = parity(library, read, direct(GameAction(0)));
    require(revealed.info.selectScreenType == CardSelectScreenType::OBTAIN
            && revealed.info.toSelectCards.size() == 20, "Library did not reveal 20-card OBTAIN selector");
    const auto take = find(revealed, Effect::TAKE_CARD);
    require(std::holds_alternative<OocCandidateTarget>(std::get<OocSelectorTarget>(take.target).card),
            "revealed Library card fabricated deck identity");
    parity(revealed, take, select);

    auto wheel = fixture(ScreenState::EVENT_SCREEN);
    wheel.curEvent = Event::WHEEL_OF_CHANGE;
    auto wheelActions = enumerate(wheel);
    require(wheelActions.size() == 1 && wheelActions[0].effect == Effect::EVENT_CHOICE,
            "Wheel must expose generic source choice");
    parity(wheel, wheelActions[0], direct(GameAction(0)));

    auto wing = fixture(ScreenState::EVENT_SCREEN);
    wing.curEvent = Event::WING_STATUE;
    wing.curHp = 7;
    const auto dangerous = find(wing, Effect::EVENT_CHOICE, [](const auto &a) {
        return std::get<OocEventTarget>(a.target).option == 0;
    });
    const auto lost = parity(wing, dangerous, direct(GameAction(0)));
    require(lost.outcome == GameOutcome::PLAYER_LOSS,
            "low-HP Wing Statue fixture did not exercise terminal source outcome");
}

void completeSelector(GameContext g, int picks, Effect effect) {
    require(g.screenState == ScreenState::CARD_SELECT && g.info.toSelectCount == picks,
            "multi-selector fixture wrong pick count");
    for (int pick = 0; pick < picks; ++pick) {
        const auto action = find(g, effect);
        const auto target = std::get<OocSelectorTarget>(action.target);
        require(target.requiredPicks == picks && target.completedPicks == pick,
                "selector semantic progress metadata wrong");
        const auto beforeCandidates = g.info.toSelectCards.size();
        require(enumerate(g).size() == static_cast<std::size_t>(beforeCandidates),
                "multi-selector enumeration expanded combinations instead of next picks");
        g = parity(g, action, select);
        if (pick + 1 < picks) {
            require(g.screenState == ScreenState::CARD_SELECT
                    && g.info.haveSelectedCards.size() == pick + 1
                    && g.info.toSelectCards.size() == beforeCandidates - 1,
                    "intermediate selection did not retain selector/remove candidate");
            unchangedFailure(g, action);
            auto currentMetadataOldCard = action;
            std::get<OocSelectorTarget>(currentMetadataOldCard.target).completedPicks = pick + 1;
            unchangedFailure(g, currentMetadataOldCard);

            const auto nextAction = find(g, effect);
            auto malformed = test::cloneOocTestState(g);
            ++malformed.info.haveSelectedCards[0].card.misc;
            unchangedFailure(malformed, nextAction);
            malformed = test::cloneOocTestState(g);
            malformed.info.haveSelectedCards[0].deckIdx = malformed.deck.size();
            unchangedFailure(malformed, nextAction);
            malformed = test::cloneOocTestState(g);
            malformed.info.haveSelectedCards[0].deckIdx = -1;
            unchangedFailure(malformed, nextAction);
            // Astrolabe has room for two completed picks and one remaining;
            // this specifically exercises duplicate-history validation rather
            // than only malformed/exhausted pick cardinality.
            if (picks == 3 && pick == 1) {
                malformed = test::cloneOocTestState(g);
                malformed.info.haveSelectedCards[1] = malformed.info.haveSelectedCards[0];
                unchangedFailure(malformed, nextAction);
            }
        }
    }
    require(g.screenState != ScreenState::CARD_SELECT, "last pick did not complete selector");
}

void testSelectors() {
    auto augmenter = fixture(ScreenState::EVENT_SCREEN);
    augmenter.curEvent = Event::AUGMENTER;
    const auto augment = find(augmenter, Effect::EVENT_CHOICE, [](const auto &a) {
        return std::get<OocEventTarget>(a.target).option == 1;
    });
    completeSelector(parity(augmenter, augment, direct(GameAction(1))), 2, Effect::TRANSFORM_CARD);

    auto boss = fixture(ScreenState::BOSS_RELIC_REWARDS);
    boss.enterBossTreasureRoom(); // Actual act-transition continuation mutates the map.
    boss.info.bossRelics[0] = RelicId::ASTROLABE;
    boss.info.bossRelics[1] = RelicId::BLACK_STAR;
    boss.info.bossRelics[2] = RelicId::COFFEE_DRIPPER;
    for (const auto &a : enumerate(boss))
        require(a.effect == Effect::TAKE_BOSS_RELIC || a.effect == Effect::SKIP_BOSS_RELIC,
                "boss source expanded hidden selector choices");
    auto astrolabe = find(boss, Effect::TAKE_BOSS_RELIC, [](const auto &a) {
        return std::get<OocRelicTarget>(a.target).relic == RelicId::ASTROLABE;
    });
    completeSelector(parity(boss, astrolabe, direct(GameAction(0))), 3, Effect::TRANSFORM_UPGRADE_CARD);
    parity(boss, find(boss, Effect::SKIP_BOSS_RELIC), direct(GameAction(3)));

    const std::pair<CardSelectScreenType, Effect> rows[] = {
        {CardSelectScreenType::UPGRADE, Effect::UPGRADE_CARD},
        {CardSelectScreenType::REMOVE, Effect::REMOVE_CARD},
        {CardSelectScreenType::DUPLICATE, Effect::DUPLICATE_CARD},
        {CardSelectScreenType::TRANSFORM, Effect::TRANSFORM_CARD},
        {CardSelectScreenType::BONFIRE_SPIRITS, Effect::SACRIFICE_CARD},
    };
    for (const auto &[type, effect] : rows) {
        auto g = fixture(ScreenState::EVENT_SCREEN);
        g.openCardSelectScreen(type, 1);
        std::reverse(g.info.toSelectCards.begin(), g.info.toSelectCards.end());
        const auto action = find(g, effect);
        parity(g, action, select);
        auto missing = action;
        std::get<OocCardTarget>(std::get<OocSelectorTarget>(missing.target).card).occurrence = 65535;
        unchangedFailure(g, missing);
    }
    auto ambiguous = fixture(ScreenState::EVENT_SCREEN);
    ambiguous.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
    const auto action = find(ambiguous, Effect::UPGRADE_CARD);
    const auto &target = std::get<OocCardTarget>(std::get<OocSelectorTarget>(action.target).card);
    for (const auto &candidate : ambiguous.info.toSelectCards) {
        if (matches(ambiguous.deck, candidate.deckIdx, target)) {
            const auto duplicate = candidate;
            ambiguous.info.toSelectCards.push_back(duplicate);
            break;
        }
    }
    unchangedFailure(ambiguous, action);

    auto unsupported = fixture(ScreenState::MAP_SCREEN);
    const auto before = test::oocStateFingerprint(unsupported);
    const auto mapResult = enumerateOocSemanticActions(unsupported);
    require(!mapResult.supported && !mapResult.complete && !mapResult.error.empty()
            && mapResult.actions.empty(), "unsupported map result silently looks supported");
    require(before == test::oocStateFingerprint(unsupported), "unsupported enumeration mutated state");
    auto malformed = fixture(ScreenState::EVENT_SCREEN);
    malformed.openCardSelectScreen(CardSelectScreenType::REMOVE, 2);
    malformed.info.toSelectCount = 0;
    const auto malformedBefore = test::oocStateFingerprint(malformed);
    const auto malformedResult = enumerateOocSemanticActions(malformed);
    require(!malformedResult.complete && !malformedResult.error.empty(),
            "malformed selector reported complete enumeration");
    require(malformedBefore == test::oocStateFingerprint(malformed), "malformed enumeration mutated state");
}

void testMalformedEntitiesAndObserver() {
    using Corrupt = std::function<void(GameContext &)>;
    const std::vector<Corrupt> rewardCorruptions {
        [](auto &g) { g.info.rewardsContainer.cardRewards[0][0].id = CardId::INVALID; },
        [](auto &g) { g.info.rewardsContainer.relics[0] = RelicId::INVALID; },
        [](auto &g) { g.info.rewardsContainer.potions[0] = Potion::INVALID; },
        [](auto &g) { g.info.rewardsContainer.gold[0] = -1; },
    };
    const auto invalid = [](GameContext &g, const OocSemanticAction &action) {
        const auto before = test::oocStateFingerprint(g);
        const auto result = enumerateOocSemanticActions(g);
        require(!result.complete && !result.error.empty(),
                "invalid active entity reported complete enumeration");
        require(before == test::oocStateFingerprint(g), "invalid entity enumeration mutated state");
        unchangedFailure(g, action);
    };
    for (const auto &corrupt : rewardCorruptions) {
        auto g = rewards();
        const auto action = find(g, Effect::TAKE_GOLD);
        corrupt(g);
        invalid(g, action);
    }
    const std::vector<Corrupt> shopCorruptions {
        [](auto &g) { g.info.shop.cards[0].id = CardId::INVALID; },
        [](auto &g) { g.info.shop.relics[0] = RelicId::INVALID; },
        [](auto &g) { g.info.shop.potions[0] = Potion::INVALID; },
    };
    for (const auto &corrupt : shopCorruptions) {
        auto g = fixture(ScreenState::SHOP_ROOM);
        std::fill(std::begin(g.info.shop.prices), std::end(g.info.shop.prices), -1);
        g.info.shop.removeCost = -1;
        g.info.shop.cards[0] = Card(CardId::INFLAME);
        g.info.shop.cardPrice(0) = 42;
        g.info.shop.relics[0] = RelicId::ANCHOR;
        g.info.shop.relicPrice(0) = 80;
        g.info.shop.potions[0] = Potion::FIRE_POTION;
        g.info.shop.potionPrice(0) = 20;
        const auto action = find(g, Effect::BUY_CARD);
        corrupt(g);
        invalid(g, action);
    }
    auto g = fixture(ScreenState::REST_ROOM);
    const auto action = find(g, Effect::UPGRADE_CARD);
    int observed = 0;
    struct RestoreObserver {
        decltype(g_onGameActionExecute) original;
        ~RestoreObserver() { g_onGameActionExecute = std::move(original); }
    } restore {g_onGameActionExecute};
    g_onGameActionExecute = [&](std::uint32_t, const GameContext *) { ++observed; };
    unchangedFailure(g, action);
    require(observed == 0, "rejected semantic transaction leaked external primitive observation");
}

void testLiteralKeys() {
    OocCardTarget card {static_cast<CardId>(7), 11, false, -1, 2};
    const std::vector<std::pair<OocSemanticAction, std::string>> cases {
        {{Effect::UPGRADE_CARD, Source::CAMPFIRE_SMITH, card},
         "ooc:v1:effect=0:source=0:card=7:misc=11:upgraded=0:bottle=-1:occurrence=2"},
        {{Effect::REST, Source::CAMPFIRE, OocNoTarget{}},
         "ooc:v1:effect=17:source=1:none"},
        {{Effect::REMOVE_CARD, Source::SHOP_REMOVE,
          OocTransactionTarget{card, static_cast<Event>(0), -1, 75}},
         "ooc:v1:effect=1:source=4:transaction:event=0:option=-1:cost=75:card=7:misc=11:upgraded=0:bottle=-1:occurrence=2"},
        {{Effect::TRANSFORM_CARD, Source::SELECTOR,
          OocSelectorTarget{CardSelectScreenType::TRANSFORM, 2, 1, card}},
         "ooc:v1:effect=2:source=6:selector=1:required=2:completed=1:card=7:misc=11:upgraded=0:bottle=-1:occurrence=2"},
        {{Effect::TAKE_CARD, Source::SELECTOR,
          OocSelectorTarget{CardSelectScreenType::OBTAIN, 1, 0,
              OocCandidateTarget{Card(static_cast<CardId>(7), 1), 3}}},
         "ooc:v1:effect=5:source=6:selector=6:required=1:completed=0:candidate=7,0,1:occurrence=3"},
        {{Effect::TAKE_GOLD, Source::REWARDS, OocRewardTarget{25, {}, 0, 1, false}},
         "ooc:v1:effect=9:source=7:reward=gold,25:group=[]:groupOccurrence=0:occurrence=1:sapphirePaired=0"},
        {{Effect::TAKE_CARD, Source::REWARDS,
          OocRewardTarget{Card(static_cast<CardId>(7)), {Card(static_cast<CardId>(7))}, 2, 0, false}},
         "ooc:v1:effect=5:source=7:reward=card,7,0,0:group=[7,0,0;]:groupOccurrence=2:occurrence=0:sapphirePaired=0"},
        {{Effect::BUY_CARD, Source::SHOP,
          OocShopTarget{Card(static_cast<CardId>(7)), 42, 0}},
         "ooc:v1:effect=22:source=3:shop=card,7,0,0:price=42:occurrence=0"},
        {{Effect::EVENT_CHOICE, Source::EVENT, OocEventTarget{static_cast<Event>(8), 1}},
         "ooc:v1:effect=26:source=5:event=8:option=1"},
        {{Effect::TAKE_BOSS_RELIC, Source::BOSS_RELIC,
          OocRelicTarget{static_cast<RelicId>(9), 0}},
         "ooc:v1:effect=27:source=9:relic=9:occurrence=0"},
    };
    for (const auto &[action, literal] : cases)
        require(canonicalOocSemanticActionKey(action) == literal, "wire key changed: " + literal);
}

} // namespace

int runOocSemanticTests() {
    try {
        testLiteralKeys();
        testCampfireAndShop();
        testRewardsAndTreasure(true);
        testTransactionIdentityAndRollback();
        testMalformedEntitiesAndObserver();
        testEvents();
        testSelectors();
        std::cout << "ooc_semantic PASS checks=" << checks << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "ooc_semantic FAIL: " << error.what() << '\n';
        return 1;
    }
}

int runOocSemanticTransactionsTests() {
    try {
        testLiteralKeys();
        testCampfireAndShop();
        testRewardsAndTreasure(false);
        testTransactionIdentityAndRollback();
        testMalformedEntitiesAndObserver();
        std::cout << "ooc_semantic_transactions PASS checks=" << checks << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "ooc_semantic_transactions FAIL: " << error.what() << '\n';
        return 1;
    }
}
