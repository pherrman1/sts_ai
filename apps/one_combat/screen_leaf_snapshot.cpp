#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"

#include <stdexcept>
#include <string>

namespace sts {
// Only occupied fixed-list elements belong to the state. Unoccupied backing
// storage can contain indeterminate values and is never serialized.
template<class T, int N>
void to_json(nlohmann::json &j, const fixed_list<T, N> &v) {
    if (v.size() < 0 || v.size() > N) throw std::runtime_error("invalid snapshot fixed-list size");
    j = nlohmann::json::array();
    for (const auto &x : v) j.push_back(x);
}
template<class T, int N>
void from_json(const nlohmann::json &j, fixed_list<T, N> &v) {
    if (!j.is_array() || j.size() > N) throw std::runtime_error("invalid snapshot fixed-list array");
    v = fixed_list<T, N>();
    for (const auto &x : j) v.push_back(x.template get<T>());
}

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Card, id, misc, upgraded)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Random, counter, seed0, seed1)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(SelectScreenCard, card, deckIdx)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(RelicInstance, id, data)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(RelicContainer, relics, relicBits0, relicBits1, relicBits2)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Deck, cards, cardTypeCounts, bottleIdxs, upgradeableCount, transformableCount)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Shop, prices, removeCost, cards, potions, relics)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Rewards, goldRewardCount, gold, cardRewardCount, cardRewards,
                                  relicCount, relics, potionCount, potions, emeraldKey, sapphireKey)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(MapNode, x, y, parentCount, parents, edgeCount, edges, room)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Map, burningEliteX, burningEliteY, burningEliteBuff, nodes)
namespace Neow {
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Option, r, d)
}
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(ScreenStateInfo, encounter, transformRng, selectScreenType,
    toSelectCount, toSelectCards, haveSelectedCards, eventData, hpAmount0, hpAmount1, hpAmount2,
    phase, rewards, upgradeOne, cleanUpIsRemoveCard, haveGold, chestSize, tier, goldLoss,
    potionIdx, gold, cardIdx, relicIdx0, relicIdx1, skillCardDeckIdx, powerCardDeckIdx,
    attackCardDeckIdx, bossRelics, neowRewards, rewardsContainer, stolenGold, shop)
} // namespace sts

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(MatchAndKeepWantCache, seed, act, floor, want)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(OocPolicyThreadState, pathActionUses, pathAggr, tokCheckPending,
    shopV, strategicTraceRows, strategicTraceDecision, actFightProbeDecisionIdx,
    actFightProbeActionIdx, actFightProbeFutureIdx, matchAndKeepWant)

namespace one_combat::screen_leaf {
namespace {
// Keep a single list for both directions so adding a transport field cannot
// silently update only export or import. Layout is shared by both frozen #334
// producers and the #379 baseline; this is a versioned semantic field format.
#define SCREEN_LEAF_GC_FIELDS(X) \
    X(noteForYourselfCard) X(skipBattles) X(seed) \
    X(aiRng) X(cardRandomRng) X(cardRng) X(eventRng) X(mathUtilRng) X(merchantRng) \
    X(miscRng) X(monsterHpRng) X(monsterRng) X(neowRng) X(potionRng) X(relicRng) \
    X(shuffleRng) X(treasureRng) X(eventList) X(shrineList) X(specialOneTimeEventList) \
    X(commonRelicPool) X(uncommonRelicPool) X(rareRelicPool) X(shopRelicPool) X(bossRelicPool) \
    X(colorlessCardPool) X(monsterListOffset) X(monsterList) X(eliteMonsterListOffset) \
    X(eliteMonsterList) X(secondBoss) X(outcome) X(screenState) X(info) X(lastRoom) \
    X(curEvent) X(curRoom) X(boss) X(monsterChance) X(shopChance) X(treasureChance) \
    X(potionChance) X(cardRarityFactor) X(wingBootsCharges) X(shopRemoveCount) X(speedrunPace) \
    X(curMapNodeX) X(curMapNodeY) X(act) X(ascension) X(floorNum) X(cc) X(curHp) X(maxHp) \
    X(gold) X(potionCount) X(potionCapacity) X(potions) X(relics) X(deck) X(blueKey) \
    X(greenKey) X(keysEnabled) X(restRoomResolved) X(redKey) X(smokeBombUsed)

void requireShape(const Json &value, const Json &reference, const std::string &where) {
    // Reject missing/extra fields recursively, including nested object shapes.
    // Arrays have variable lengths, validated by their serializers and below.
    if (reference.is_object()) {
        if (!value.is_object() || value.size() != reference.size())
            throw std::runtime_error("snapshot object shape mismatch at " + where);
        for (auto it = reference.begin(); it != reference.end(); ++it) {
            if (!value.contains(it.key()))
                throw std::runtime_error("snapshot missing field " + where + "." + it.key());
            requireShape(value.at(it.key()), it.value(), where + "." + it.key());
        }
    } else if (reference.is_array() && value.is_array()) {
        for (std::size_t i = 0; i < value.size() && i < reference.size(); ++i)
            requireShape(value.at(i), reference.at(i), where + "[]");
    }
}
void validateCounts(const sts::GameContext &gc) {
    const auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount < 0 || r.goldRewardCount > 2 || r.cardRewardCount < 0 ||
        r.cardRewardCount > 5 || r.relicCount < 0 || r.relicCount > 3 ||
        r.potionCount < 0 || r.potionCount > 5 || gc.potionCount < 0 || gc.potionCount > 5 ||
        gc.potionCapacity < 0 || gc.potionCapacity > 5)
        throw std::runtime_error("snapshot container count out of bounds");
    if (gc.map) for (const auto &row : gc.map->nodes) for (const auto &n : row)
        if (n.parentCount < 0 || n.parentCount > 6 || n.edgeCount < 0 || n.edgeCount > 3)
            throw std::runtime_error("snapshot map count out of bounds");
}
} // namespace

Json rewardsJson(const sts::Rewards &rewards) { return Json(rewards); }
sts::Rewards rewardsFromJson(const Json &value) {
    auto result = value.get<sts::Rewards>();
    requireShape(value, Json(result), "rewards");
    if (value != Json(result) || result.goldRewardCount < 0 || result.goldRewardCount > 2 ||
        result.cardRewardCount < 0 || result.cardRewardCount > 5 ||
        result.relicCount < 0 || result.relicCount > 3 ||
        result.potionCount < 0 || result.potionCount > 5)
        throw std::runtime_error("invalid or lossy snapshot rewards");
    return result;
}

Json snapshotJson(const sts::GameContext &gc, const PathHistory &path,
                  const OocPolicyThreadState &policy) {
    validateCounts(gc);
    Json state = Json::object();
#define WRITE_FIELD(name) state[#name] = gc.name;
    SCREEN_LEAF_GC_FIELDS(WRITE_FIELD)
#undef WRITE_FIELD
    state["map"] = gc.map ? Json(*gc.map) : Json(nullptr);
    state["continuation"] = continuationDescriptor(gc.regainControlAction);
    return {{"schema", "screen-leaf-full-state-v1"}, {"game", std::move(state)}, {"policy", policy},
            {"path", {{"roomVisits", path.roomVisits}, {"lastNodeKey", path.lastNodeKey}}}};
}

Snapshot snapshotFromJson(const Json &value, const ContinuationFactory &factory) {
    if (!value.is_object() || value.size() != 4 ||
        value.at("schema") != "screen-leaf-full-state-v1")
        throw std::runtime_error("invalid screen-leaf snapshot schema");
    Snapshot result;
    value.at("policy").get_to(result.policy);
    auto &gc = result.gc;
    const auto &state = value.at("game");
#define READ_FIELD(name) state.at(#name).get_to(gc.name);
    SCREEN_LEAF_GC_FIELDS(READ_FIELD)
#undef READ_FIELD
    if (!state.at("map").is_null()) gc.map = std::make_shared<sts::Map>(state.at("map").get<sts::Map>());
    const auto &descriptor = state.at("continuation");
    if (!descriptor.is_null()) {
        if (!factory) throw std::runtime_error("snapshot continuation factory missing");
        gc.regainControlAction = factory(descriptor);
        if (!gc.regainControlAction) throw std::runtime_error("snapshot continuation factory returned null");
    }
    value.at("path").at("roomVisits").get_to(result.path.roomVisits);
    value.at("path").at("lastNodeKey").get_to(result.path.lastNodeKey);
    // Factory must retain a descriptor: that makes re-export and custody checks
    // possible and rejects opaque callbacks introduced by importer mistakes.
    const auto reexport = snapshotJson(gc, result.path, result.policy);
    requireShape(value, reexport, "snapshot");
    if (value != reexport) throw std::runtime_error("snapshot import is not lossless");
    return result;
}
#undef SCREEN_LEAF_GC_FIELDS
} // namespace one_combat::screen_leaf
