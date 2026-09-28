#include "ooc_native_fallback.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <stdexcept>

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
struct ShopPlanItem { char kind; int slot, price, id; };

// The rest of a plan after a purchase, and the state that purchase should leave.
// A later shop step continues the plan only while the state still matches.
struct PendingShopPlan {
    bool active = false;
    std::vector<std::string> tokens;
    std::vector<int> expected;
};
thread_local PendingShopPlan t_pendingShopPlan;
thread_local NativeShopPlanStats t_shopPlanStats;
std::atomic<int> g_shopPlanOnceOverride{-1};

bool shopPlanOnceEnabled() {
    const int forced = g_shopPlanOnceOverride.load(std::memory_order_relaxed);
    if (forced >= 0) return forced != 0;
    static const bool enabled = [] {
        const char *value = std::getenv("STS_NATIVE_SHOP_PLAN_ONCE");
        if (!value || std::strcmp(value, "0") == 0) return false;
        if (std::strcmp(value, "1") == 0) return true;
        throw std::runtime_error("STS_NATIVE_SHOP_PLAN_ONCE must be 0 or 1");
    }();
    return enabled;
}

// Identifies one shop visit between steps: floor, gold, deck size and the
// whole offer. deckDelta accounts for a removal that finishes on the
// card-select screen after the step returns.
std::vector<int> shopVisitSignature(const sts::GameContext &gc, int deckDelta) {
    const auto &sh = gc.info.shop;
    std::vector<int> s = {gc.act, gc.floorNum, gc.gold, gc.deck.size() + deckDelta, sh.removeCost};
    for (int i = 0; i < 7; ++i) {
        s.push_back(sh.cardPrice(i));
        s.push_back(static_cast<int>(sh.cards[i].getId()));
    }
    for (int i = 0; i < 3; ++i) {
        s.push_back(sh.relicPrice(i));
        s.push_back(static_cast<int>(sh.relics[i]));
    }
    return s;
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

} // namespace

std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor) {
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
    ++t_shopPlanStats.planCalls;
    return computeShopPlan(gc, base, items, floor);
}

NativeShopPlanStats takeNativeShopPlanStats() {
    const auto stats = t_shopPlanStats;
    t_shopPlanStats = {};
    return stats;
}

void setNativeShopPlanOnceForTesting(int mode) {
    g_shopPlanOnceOverride.store(mode, std::memory_order_relaxed);
    t_pendingShopPlan = {};
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
    ++t_shopPlanStats.shopSteps;
    const bool sameVisit = t_pendingShopPlan.active
        && t_pendingShopPlan.expected == shopVisitSignature(gc, 0);
    // Another policy (such as the V4 one-ply shop gate) acted since the last
    // purchase, or a continuation stopped mid-shop.
    if (t_pendingShopPlan.active && !sameVisit) ++t_shopPlanStats.planMismatches;
    // The Courier restocks bought slots, so its shops always re-plan.
    const bool reuse = sameVisit && shopPlanOnceEnabled()
        && !gc.hasRelic(sts::RelicId::THE_COURIER);
    std::vector<std::string> tokens;
    if (reuse) {
        tokens = std::move(t_pendingShopPlan.tokens);
        ++t_shopPlanStats.planReuses;
    } else {
        std::istringstream is(nativeShopPlan(gc, path, floor));
        for (std::string token; is >> token;) tokens.push_back(token);
        if (sameVisit) ++t_shopPlanStats.replanCalls;
    }
    t_pendingShopPlan = {};
    const auto leave = [&] {
        ++t_shopPlanStats.shopExits;
        sts::search::GameAction(RT::SKIP).execute(gc);
    };
    if (tokens.empty()) { leave(); return; }
    const std::string token = tokens.front();
    tokens.erase(tokens.begin());
    const int idx = token.size() > 1 ? std::atoi(token.c_str() + 1) : 0;
    if (token[0] == 'c') sts::search::GameAction(RT::CARD, idx).execute(gc);
    else if (token[0] == 'r') {
        const sts::search::GameAction action(RT::RELIC, idx);
        if (!sts::search::isSupportedAutonomousOocAction(gc, action)) { leave(); return; }
        action.execute(gc);
    } else if (token[0] == 'x') sts::search::GameAction(RT::CARD_REMOVE).execute(gc);
    else { leave(); return; }
    t_pendingShopPlan = {true, std::move(tokens), shopVisitSignature(gc, token[0] == 'x' ? -1 : 0)};
}

} // namespace one_combat
