#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include "ooc_test_state.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace {
using namespace sts;
using namespace sts::search;
using J = nlohmann::json;
int checks = 0;
void require(bool value, const char *message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}
Card decodeCard(const J &j) {
    Card c(static_cast<CardId>(j.at("id").get<int>()));
    c.misc = j.at("misc").get<std::int16_t>();
    c.upgraded = j.at("upgraded").get<bool>();
    return c;
}
OocCardTarget decodeDeck(const J &j) {
    auto c = decodeCard(j);
    return {c.id, c.misc, c.upgraded, j.at("bottle").get<std::int8_t>(),
            j.at("occurrence").get<std::uint16_t>()};
}
OocEntity decodeEntity(const J &j) {
    const auto type = j.at("type").get<std::string>();
    if (type == "none") return OocNoTarget{};
    if (type == "card") return decodeCard(j.at("value"));
    const int value = j.at("value").get<int>();
    if (type == "relic") return static_cast<RelicId>(value);
    if (type == "potion") return static_cast<Potion>(value);
    if (type == "key") return static_cast<Key>(value);
    if (type == "gold") return value;
    throw std::runtime_error("unrecognized entity tag");
}
// Independent decoder proves the persisted typed payload is sufficient to
// reconstruct canonical identity, rather than merely comparing serializer output.
OocSemanticPayload decodePayload(const J &j) {
    const auto type = j.at("type").get<std::string>();
    if (type == "none") return OocNoTarget{};
    if (type == "deck_card") return decodeDeck(j.at("card"));
    if (type == "transaction") return OocTransactionTarget{decodeDeck(j.at("card")),
        static_cast<Event>(j.at("event").get<int>()), j.at("option"), j.at("expectedGoldCost")};
    if (type == "selector") {
        OocSelectorTarget v;
        v.type = static_cast<CardSelectScreenType>(j.at("selectorType").get<int>());
        v.requiredPicks = j.at("requiredPicks"); v.completedPicks = j.at("completedPicks");
        const auto &target = j.at("target");
        if (target.at("type") == "deck_card") v.card = decodeDeck(target.at("card"));
        else if (target.at("type") == "candidate")
            v.card = OocCandidateTarget{decodeCard(target.at("card")), target.at("occurrence")};
        else throw std::runtime_error("unrecognized selector tag");
        return v;
    }
    if (type == "reward") {
        OocRewardTarget v; v.entity = decodeEntity(j.at("entity"));
        for (const auto &c : j.at("cardGroup")) v.cardGroup.push_back(decodeCard(c));
        v.groupOccurrence = j.at("groupOccurrence"); v.occurrence = j.at("occurrence");
        v.sapphirePaired = j.at("sapphirePaired"); return v;
    }
    if (type == "shop") return OocShopTarget{decodeEntity(j.at("entity")), j.at("expectedPrice"), j.at("occurrence")};
    if (type == "event") return OocEventTarget{static_cast<Event>(j.at("event").get<int>()), j.at("option")};
    if (type == "relic") return OocRelicTarget{static_cast<RelicId>(j.at("relic").get<int>()), j.at("occurrence")};
    throw std::runtime_error("unrecognized payload tag");
}
void roundTrip(const OocSemanticAction &a) {
    const auto text = oocSemanticActionPayloadJson(a);
    auto restored = a;
    restored.target = decodePayload(J::parse(text));
    require(restored.target.index() == a.target.index(), "payload variant was lost");
    require(canonicalOocSemanticActionKey(a) == canonicalOocSemanticActionKey(restored), "payload lost canonical identity");
    require(text == oocSemanticActionPayloadJson(restored), "payload is not canonical after reconstruction");
}
void payloads() {
    const OocCardTarget deck{CardId::BASH, -17, true, 2, 65535};
    Card card(CardId::SEARING_BLOW, true); card.misc = 19;
    std::vector<OocSemanticPayload> payloads{
        OocNoTarget{}, deck, OocTransactionTarget{deck, Event::OLD_BEGGAR, 0, 75},
        OocSelectorTarget{CardSelectScreenType::TRANSFORM, 3, 2, deck},
        OocSelectorTarget{CardSelectScreenType::OBTAIN, 1, 0, OocCandidateTarget{card, 7}},
        OocEventTarget{Event::THE_LIBRARY, 0}, OocRelicTarget{RelicId::ASTROLABE, 3}};
    for (const OocEntity &entity : std::vector<OocEntity>{OocNoTarget{}, card, RelicId::ANCHOR,
            Potion::FIRE_POTION, 123, static_cast<Key>(1)}) {
        payloads.push_back(OocRewardTarget{entity, {Card(CardId::BASH), card, card}, 3, 4, true});
        payloads.push_back(OocShopTarget{entity, 137, 5});
    }
    for (const auto &payload : payloads)
        roundTrip({OocSemanticEffect::TAKE_CARD, OocSemanticSource::REWARDS, payload});
}
GameContext fixture(ScreenState screen) {
    static const GameContext base(CharacterClass::IRONCLAD, 0x51514Du, 0);
    auto gc = test::cloneOocTestState(base);
    gc.screenState = screen; gc.curEvent = Event::INVALID; gc.gold = 500;
    return gc;
}
void boundaries() {
    using S = CardSelectScreenType;
    using R = GameAction::RewardsActionType;
    auto check = [](const GameContext &g, GameAction a, S expected) {
        const auto before = test::oocStateFingerprint(g);
        require(oocSemanticPrimitiveCompoundSelector(g, a.bits) == expected, "wrong source selector suppression boundary");
        require(before == test::oocStateFingerprint(g), "boundary inspection changed source state/RNG");
        const auto enumeration = enumerateOocSemanticActions(g);
        require(enumeration.supported && enumeration.complete, "boundary fixture incomplete");
        for (const auto &action : enumeration.actions) roundTrip(action);
    };
    auto fire = fixture(ScreenState::REST_ROOM);
    check(fire, GameAction(1), S::UPGRADE);
    check(fire, GameAction(0), S::INVALID);
    fire.relics.add({RelicId::PEACE_PIPE, 0});
    check(fire, GameAction(4), S::REMOVE);
    auto shop = fixture(ScreenState::SHOP_ROOM);
    std::fill(std::begin(shop.info.shop.prices), std::end(shop.info.shop.prices), -1);
    shop.info.shop.removeCost = 75;
    check(shop, GameAction(R::CARD_REMOVE), S::REMOVE);
    auto event = fixture(ScreenState::EVENT_SCREEN);
    event.curEvent = Event::OLD_BEGGAR;
    check(event, GameAction(0), S::REMOVE);
    event.curEvent = Event::THE_LIBRARY;
    check(event, GameAction(0), S::INVALID);
    event.curEvent = Event::AUGMENTER;
    check(event, GameAction(1), S::INVALID);
}
} // namespace
int runOocSemanticPipelineTests() {
    try {
        payloads(); boundaries();
        std::cout << "ooc_semantic_pipeline PASS checks=" << checks << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ooc_semantic_pipeline FAIL: " << e.what() << '\n';
        return 1;
    }
}
