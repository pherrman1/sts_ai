#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"
#include <iostream>
#include <stdexcept>

using namespace one_combat::screen_leaf;
namespace {
void check(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}
template<class F> void rejects(F f, const char *message) {
    bool rejected = false;
    try { f(); } catch (const std::exception &) { rejected = true; }
    check(rejected, message);
}
}

int main() {
    // Construct state directly. This test never starts a game or drives seeds.
    sts::GameContext gc{};
    gc.info.neowRewards = {};
    gc.cc = sts::CharacterClass::IRONCLAD;
    gc.seed = UINT64_C(18446744073709551610);
    gc.cardRng.seed0 = UINT64_C(9223372036854775813);
    gc.cardRng.counter = 41;
    gc.curHp = 31;
    gc.maxHp = 91;
    gc.info.shop.cards[4].id = sts::CardId::FEED;
    gc.info.shop.cards[4].misc = 7;
    gc.info.shop.cards[4].upgraded = true;
    gc.info.shop.prices[4] = 123;
    gc.info.bossRelics[2] = sts::RelicId::BLACK_STAR;
    gc.info.eventData = 7;
    gc.info.toSelectCards.push_back({});
    gc.info.toSelectCards[0].card = gc.info.shop.cards[4];
    gc.info.toSelectCards[0].deckIdx = 3;
    gc.deck.cards.push_back(gc.info.shop.cards[4]);
    gc.deck.bottleIdxs[1] = 0;
    // Cached values must be transported, not recomputed.
    gc.deck.upgradeableCount = 6;
    gc.deck.cardTypeCounts[2] = 9;
    gc.relics.relics.push_back({sts::RelicId::BLACK_STAR, 11});
    gc.relics.relicBits2 = 71;
    gc.info.rewardsContainer.cardRewards[0].push_back(gc.info.shop.cards[4]);
    gc.info.rewardsContainer.cardRewardCount = 1;
    gc.map = std::make_shared<sts::Map>();
    gc.map->nodes[2][3].edgeCount = 2;
    gc.map->nodes[2][3].edges = {1, 4, 0};
    gc.map->burningEliteBuff = 3;
    gc.eventList.push_back(sts::Event::NEOW);
    OocPolicyThreadState policy;
    policy.pathActionUses = 4;
    policy.pathAggr = 0.123456789012345;
    policy.matchAndKeepWant.want[{17, true}] = false;
    policy.matchAndKeepWant.want[{42, false}] = true;
    policy.strategicTraceRows = "embedded\ntrace,\"text\"";
    one_combat::PathHistory path;
    path.roomVisits[3] = 17;
    path.lastNodeKey = 987654;
    const Json descriptor = {{"kind", "test"}, {"nested", {{"kind", "test-child"}}}};
    gc.regainControlAction = tagContinuation(descriptor, [](sts::GameContext &) {});
    const auto factory = [](const Json &d) {
        return tagContinuation(d, [](sts::GameContext &) {});
    };
    const auto encoded = snapshotJson(gc, path, policy);
    // Exercise textual JSON transport, including uint64 and float conversion.
    const auto decoded = snapshotFromJson(Json::parse(encoded.dump()), factory);
    check(encoded == snapshotJson(decoded.gc, decoded.path, decoded.policy), "roundtrip mismatch");
    check(decoded.gc.map.get() != gc.map.get(), "map pointer shared across transport");
    check(decoded.gc.deck.upgradeableCount == 6, "deck cache recomputed");
    check(decoded.gc.cardRng.seed0 == gc.cardRng.seed0, "uint64 lost precision");
    check(decoded.policy.matchAndKeepWant.want == policy.matchAndKeepWant.want, "policy cache lost");
    auto bad = encoded;
    bad["game"].erase("miscRng");
    rejects([&] { snapshotFromJson(bad, factory); }, "missing RNG accepted");
    bad = encoded;
    bad["game"]["info"]["surprise"] = 1;
    rejects([&] { snapshotFromJson(bad, factory); }, "unknown nested field accepted");
    bad = encoded;
    bad["game"]["deck"]["cards"] = Json::array();
    for (int i = 0; i <= sts::Deck::MAX_SIZE; ++i)
        bad["game"]["deck"]["cards"].push_back(encoded["game"]["deck"]["cards"][0]);
    rejects([&] { snapshotFromJson(bad, factory); }, "over-capacity deck accepted");
    bad = encoded;
    bad["path"]["roomVisits"].push_back(99);
    rejects([&] { snapshotFromJson(bad, factory); }, "extra array member accepted");
    rejects([&] { snapshotFromJson(encoded, {}); }, "missing callback factory accepted");
    gc.regainControlAction = [](sts::GameContext &) {};
    rejects([&] { snapshotJson(gc, path, policy); }, "opaque callback accepted");
    gc.regainControlAction = nullptr;
    gc.map = nullptr;
    auto empty = snapshotFromJson(snapshotJson(gc, path, policy), {});
    check(!empty.gc.map && !empty.gc.regainControlAction, "nulls not preserved");
    std::cout << "screen_leaf_snapshot: PASS\n";
}
