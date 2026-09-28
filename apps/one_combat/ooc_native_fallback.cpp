#include "ooc_native_fallback.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat {
namespace {
void requireModels(const CompactTreeNet &model) {
    if (!model.ok) throw std::runtime_error("native OOC fallback model unavailable");
}
std::vector<float> features(const sts::GameContext &gc, const PathHistory &path) {
    return richFeatureVec(gc, path);
}
}

int nativeFloorCardPick(sts::GameContext &gc, const PathHistory &path,
                        const CompactTreeNet &floor, int rewardIndex, double skipThreshold) {
    requireModels(floor);
    const auto &r = gc.info.rewardsContainer;
    const auto base = features(gc, path);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    double best = -1e100; int bestIdx = 5;
    const double v0 = floor.predict(base);
    for (int i = 0; i < r.cardRewards[rewardIndex].size(); ++i) {
        auto row = base;
        const int cid = static_cast<int>(r.cardRewards[rewardIndex][i].getId());
        const auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) row[it->second] += 1.0f;
        row[dsz] += 1.0f;
        const double marginal = floor.predict(row) - v0;
        if (marginal > best) { best = marginal; bestIdx = i; }
    }
    return best < skipThreshold ? 5 : bestIdx;
}

namespace {
// Everything computeShopPlan reads: the feature row, the filtered offer, the
// remove cost, gold, and the model identity. Equal keys give equal plans, so
// the cache is exact; floats are keyed by bit pattern.
struct ShopPlanItem { char kind; int slot, price, id; };
struct ShopPlanKey {
    std::vector<std::uint32_t> words;
    std::size_t hash = 0;
    bool operator==(const ShopPlanKey &o) const { return hash == o.hash && words == o.words; }
};
struct ShopPlanKeyHash {
    std::size_t operator()(const ShopPlanKey &k) const { return k.hash; }
};
constexpr std::size_t kShopPlanCacheMaxEntries = 4096;
thread_local std::unordered_map<ShopPlanKey, std::string, ShopPlanKeyHash> t_shopPlanCache;
thread_local NativeShopPlanStats t_shopPlanStats;
// Set after a shop step that bought something, so the next shop step is a
// re-plan within the same visit. Approximate if a rollout stops mid-shop.
thread_local bool t_shopReplanPending = false;
std::atomic<int> g_shopPlanCacheOverride{-1};

bool shopPlanCacheEnabled() {
    const int forced = g_shopPlanCacheOverride.load(std::memory_order_relaxed);
    if (forced >= 0) return forced != 0;
    static const bool enabled = [] {
        const char *value = std::getenv("STS_NATIVE_SHOP_PLAN_CACHE");
        if (!value || std::strcmp(value, "1") == 0) return true;
        if (std::strcmp(value, "0") == 0) return false;
        throw std::runtime_error("STS_NATIVE_SHOP_PLAN_CACHE must be 0 or 1");
    }();
    return enabled;
}

ShopPlanKey shopPlanKey(const sts::GameContext &gc, const std::vector<float> &base,
                        const std::vector<ShopPlanItem> &items, const CompactTreeNet &floor) {
    ShopPlanKey key;
    auto &w = key.words;
    w.reserve(base.size() + items.size() * 4 + 12);
    for (const auto address : {reinterpret_cast<std::uintptr_t>(&floor),
                               reinterpret_cast<std::uintptr_t>(floor.nodes.data())}) {
        const auto bits = static_cast<std::uint64_t>(address);
        w.push_back(static_cast<std::uint32_t>(bits));
        w.push_back(static_cast<std::uint32_t>(bits >> 32));
    }
    w.push_back(static_cast<std::uint32_t>(floor.nodes.size()));
    w.push_back(static_cast<std::uint32_t>(gc.gold));
    w.push_back(static_cast<std::uint32_t>(gc.info.shop.removeCost));
    w.push_back(static_cast<std::uint32_t>(base.size()));
    for (const float f : base) {
        std::uint32_t bits;
        std::memcpy(&bits, &f, sizeof bits);
        w.push_back(bits);
    }
    w.push_back(static_cast<std::uint32_t>(items.size()));
    for (const auto &item : items) {
        w.push_back(static_cast<std::uint32_t>(item.kind));
        w.push_back(static_cast<std::uint32_t>(item.slot));
        w.push_back(static_cast<std::uint32_t>(item.price));
        w.push_back(static_cast<std::uint32_t>(item.id));
    }
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (const std::uint32_t x : w) { h ^= x; h *= 0x100000001b3ULL; }
    key.hash = static_cast<std::size_t>(h);
    return key;
}

std::string computeShopPlan(const sts::GameContext &gc, const std::vector<float> &base,
                            const std::vector<ShopPlanItem> &items, const CompactTreeNet &floor) {
    const auto &sh = gc.info.shop;
    const auto &idx = richIdxMap();
    const int goldIdx = idx.at("gold"), dsz = idx.at("deckSize");
    int removeId = -1; double removeGain = 0.0;
    if (sh.removeCost >= 0) {
        const double v0 = floor.predict(base);
        for (int id = 0; id < 372; ++id) {
            const auto it = idx.find("d" + std::to_string(id));
            if (it == idx.end() || base[it->second] <= 0) continue;
            auto row = base; row[it->second] -= 1.0f; row[dsz] -= 1.0f;
            const double gain = floor.predict(row) - v0;
            if (removeId < 0 || gain > removeGain) { removeId = id; removeGain = gain; }
        }
    }
    double best = -1e100; unsigned bestMask = 0; bool bestRemove = false;
    const unsigned total = 1u << items.size();
    for (unsigned mask = 0; mask < total; ++mask) {
        int spend = 0, adds = 0;
        for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
            spend += items[k].price; ++adds;
        }
        for (int rem = 0; rem <= 1; ++rem) {
            if (rem && (sh.removeCost < 0 || removeId < 0)) continue;
            if (spend + (rem ? sh.removeCost : 0) > gc.gold) continue;
            auto row = base; row[goldIdx] -= spend + (rem ? sh.removeCost : 0); row[dsz] += adds;
            for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
                if (items[k].kind == 'c') {
                    const auto it = idx.find("d" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] += 1.0f;
                } else {
                    const auto it = idx.find("r" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] = std::max(row[it->second], 1.0f);
                }
            }
            if (rem) {
                const auto it = idx.find("d" + std::to_string(removeId));
                if (it != idx.end()) row[it->second] -= 1.0f;
            }
            const double value = floor.predict(row);
            if (value > best) { best = value; bestMask = mask; bestRemove = rem != 0; }
        }
    }
    std::ostringstream out;
    for (unsigned k = 0; k < items.size(); ++k)
        if (bestMask & (1u << k)) out << items[k].kind << items[k].slot << ' ';
    if (bestRemove) out << 'x';
    return out.str();
}

std::string cachedShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor, bool &hit) {
    requireModels(floor);
    using RT = sts::search::GameAction::RewardsActionType;
    const auto &sh = gc.info.shop;
    const auto base = features(gc, path);
    std::vector<ShopPlanItem> items;
    for (int i = 0; i < 7; ++i) if (sh.cardPrice(i) >= 0)
        items.push_back({'c', i, sh.cardPrice(i), static_cast<int>(sh.cards[i].getId())});
    for (int i = 0; i < 3; ++i) {
        const sts::search::GameAction action(RT::RELIC, i);
        if (sh.relicPrice(i) >= 0 && sts::search::isSupportedAutonomousOocAction(gc, action))
            items.push_back({'r', i, sh.relicPrice(i), static_cast<int>(sh.relics[i])});
    }
    if (items.size() > 16) items.resize(16);
    hit = false;
    ++t_shopPlanStats.planCalls;
    if (!shopPlanCacheEnabled()) return computeShopPlan(gc, base, items, floor);
    auto key = shopPlanKey(gc, base, items, floor);
    if (const auto found = t_shopPlanCache.find(key); found != t_shopPlanCache.end()) {
        hit = true;
        ++t_shopPlanStats.cacheHits;
        return found->second;
    }
    auto plan = computeShopPlan(gc, base, items, floor);
    if (t_shopPlanCache.size() >= kShopPlanCacheMaxEntries) {
        t_shopPlanCache.clear();
        ++t_shopPlanStats.cacheClears;
    }
    t_shopPlanCache.emplace(std::move(key), plan);
    return plan;
}
} // namespace

std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor) {
    bool hit = false;
    return cachedShopPlan(gc, path, floor, hit);
}

NativeShopPlanStats takeNativeShopPlanStats() {
    const auto stats = t_shopPlanStats;
    t_shopPlanStats = {};
    return stats;
}

void setNativeShopPlanCacheForTesting(int mode) {
    g_shopPlanCacheOverride.store(mode, std::memory_order_relaxed);
    t_shopPlanCache.clear();
    t_shopReplanPending = false;
}

int nativeFloorRemovePick(const sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor, const std::vector<int> &cardIds) {
    requireModels(floor);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    const auto base = features(gc, path);
    const double v0 = floor.predict(base);
    double best = -1e100; int bestIdx = 0;
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        auto row = base;
        const auto it = idx.find("d" + std::to_string(cardIds[i]));
        if (it != idx.end()) row[it->second] -= 1.0f;
        row[dsz] -= 1.0f;
        const double gain = floor.predict(row) - v0;
        if (gain > best) { best = gain; bestIdx = i; }
    }
    return bestIdx;
}

double nativeWinHealGain(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, int healAmount) {
    requireModels(win);
    const int old = gc.curHp;
    const double before = win.predict(features(gc, path));
    gc.curHp = std::min(gc.maxHp, old + healAmount);
    const double after = win.predict(features(gc, path));
    gc.curHp = old;
    return after - before;
}

int nativeWinUpgradePick(const sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, const std::vector<int> &cardIds,
                         double *gain) {
    requireModels(win);
    const auto &idx = richIdxMap();
    const auto base = features(gc, path);
    const double before = win.predict(base);
    double best = -1e100; int bestIdx = 0;
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        auto row = base;
        const auto it = idx.find("u" + std::to_string(cardIds[i]));
        if (it != idx.end()) row[it->second] += 1.0f;
        const double delta = win.predict(row) - before;
        if (delta > best) { best = delta; bestIdx = i; }
    }
    if (std::abs(best) < 1e-6) {
        best = -1e100; bestIdx = 0;
        for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
            auto row = base;
            const auto it = idx.find("d" + std::to_string(cardIds[i]));
            if (it != idx.end()) row[it->second] -= 1.0f;
            const auto ds = idx.find("deckSize");
            if (ds != idx.end()) row[ds->second] -= 1.0f;
            const double delta = before - win.predict(row);
            if (delta > best) { best = delta; bestIdx = i; }
        }
    }
    if (gain) *gain = best;
    return bestIdx;
}

bool nativeWinRestStep(sts::GameContext &gc, const PathHistory &path,
                       const CompactTreeNet &win, bool collectKeys) {
    requireModels(win);
    if (collectKeys && gc.act >= 3 && !gc.hasKey(sts::Key::RUBY_KEY)) {
        sts::search::GameAction(2, 0).execute(gc);
        return true;
    }
    const bool canRest = !gc.hasRelic(sts::RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(sts::RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmount = static_cast<int>(std::lround(0.30 * gc.maxHp))
        + (gc.hasRelic(sts::RelicId::REGAL_PILLOW) ? 15 : 0);
    const double healGain = nativeWinHealGain(gc, path, win, healAmount);
    std::vector<int> ids;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        const int id = static_cast<int>(gc.deck.cards[i].getId());
        if (std::find(ids.begin(), ids.end(), id) == ids.end()) ids.push_back(id);
    }
    double upgradeGain = 0.0;
    if (!ids.empty()) nativeWinUpgradePick(gc, path, win, ids, &upgradeGain);
    sts::search::GameAction(healGain >= upgradeGain ? 0 : 1, 0).execute(gc);
    return true;
}

void nativeWinUpgradeSelectStep(sts::GameContext &gc, const PathHistory &path,
                                const CompactTreeNet &win) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back(static_cast<int>(gc.info.toSelectCards[i].card.getId()));
    double gain = 0.0;
    const int choice = ids.empty() ? 0 : nativeWinUpgradePick(gc, path, win, ids, &gain);
    sts::search::GameAction(choice, 0).execute(gc);
}

void nativeFloorShopStep(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor) {
    using RT = sts::search::GameAction::RewardsActionType;
    const bool replan = t_shopReplanPending;
    bool hit = false;
    const std::string plan = cachedShopPlan(gc, path, floor, hit);
    ++t_shopPlanStats.shopSteps;
    if (replan) {
        ++t_shopPlanStats.replanCalls;
        if (hit) ++t_shopPlanStats.replanCacheHits;
    }
    const auto leave = [&] {
        ++t_shopPlanStats.shopExits;
        t_shopReplanPending = false;
        sts::search::GameAction(RT::SKIP).execute(gc);
    };
    std::istringstream is(plan);
    std::string token;
    if (!(is >> token) || token.empty()) { leave(); return; }
    const int idx = token.size() > 1 ? std::atoi(token.c_str() + 1) : 0;
    t_shopReplanPending = true;
    if (token[0] == 'c') sts::search::GameAction(RT::CARD, idx).execute(gc);
    else if (token[0] == 'r') {
        const sts::search::GameAction action(RT::RELIC, idx);
        if (sts::search::isSupportedAutonomousOocAction(gc, action)) action.execute(gc);
        else leave();
    } else if (token[0] == 'x') sts::search::GameAction(RT::CARD_REMOVE).execute(gc);
    else leave();
}

} // namespace one_combat
