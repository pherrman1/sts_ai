// Seed-free check that the native shop-plan cache is exact: cached plans and
// whole shop visits match the uncached planner on fixed fixture shops.
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "game/GameContext.h"
#include "sim/search/GameAction.h"
#include "one_combat/compact_tree.h"
#include "one_combat/ooc_native_fallback.h"
#include "one_combat/run_features.h"

namespace {
void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

sts::GameContext fixtureShop(std::uint64_t fixture, int gold) {
    using namespace sts;
    GameContext gc(CharacterClass::IRONCLAD, fixture, 0);
    gc.screenState = ScreenState::SHOP_ROOM;
    gc.curRoom = Room::SHOP;
    gc.gold = gold;
    gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    gc.info.shop.setup(gc);
    return gc;
}

// Walks one shop visit with the native step; returns the final state summary.
std::string walkVisit(sts::GameContext gc, const one_combat::CompactTreeNet &floor) {
    using namespace sts;
    one_combat::PathHistory path;
    std::string trace;
    for (int step = 0; step < 32; ++step) {
        if (gc.screenState == ScreenState::SHOP_ROOM) {
            trace += one_combat::nativeShopPlan(gc, path, floor) + "|";
            one_combat::nativeFloorShopStep(gc, path, floor);
        } else if (gc.screenState == ScreenState::CARD_SELECT) {
            std::vector<int> ids;
            for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
                ids.push_back(static_cast<int>(gc.info.toSelectCards[i].card.getId()));
            const int choice = ids.empty() ? 0 : one_combat::nativeFloorRemovePick(gc, path, floor, ids);
            search::GameAction(choice, 0).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            // Relics such as Orrery open rewards; skipping returns to the shop.
            search::GameAction(search::GameAction::RewardsActionType::SKIP).execute(gc);
        } else {
            break;
        }
    }
    trace += "gold=" + std::to_string(gc.gold) + " deck=" + std::to_string(gc.deck.size())
        + " relics=" + std::to_string(gc.relics.size()) + " screen="
        + std::to_string(static_cast<int>(gc.screenState));
    return trace;
}
}

int main(int argc, char **argv) {
    try {
        require(argc == 2, "usage: ooc_shop_plan_cache_test v_rich_trees.txt");
        one_combat::CompactTreeNet floor;
        require(floor.load(argv[1], one_combat::richIdxMap(), "floor"), "cannot load floor model");
        // Fixture shops share the starting deck, so equal feature rows with
        // different offers and gold exercise the full cache key.
        struct Case { sts::GameContext shop; std::string plan, visit; };
        std::vector<Case> cases;
        int planChanges = 0;
        one_combat::setNativeShopPlanCacheForTesting(0);
        for (std::uint64_t fixture = 1; fixture <= 4; ++fixture) {
            for (const int gold : {99, 320, 999}) {
                // Variants keep the feature row and item count and change only
                // the offer: the full shop's planned items priced out of reach,
                // then removal unavailable.
                std::string fullPlan;
                for (int variant = 0; variant < 3; ++variant) {
                    auto shop = fixtureShop(0x5409000ULL + fixture, gold);
                    if (variant == 1) {
                        std::istringstream tokens(fullPlan);
                        for (std::string t; tokens >> t;) {
                            if (t[0] == 'c') shop.info.shop.cardPrice(t[1] - '0') = 9999;
                            if (t[0] == 'r') shop.info.shop.relicPrice(t[1] - '0') = 9999;
                        }
                    }
                    if (variant == 2) shop.info.shop.removeCost = -1;
                    auto state = shop;
                    one_combat::PathHistory path;
                    auto plan = one_combat::nativeShopPlan(state, path, floor);
                    auto visit = walkVisit(shop, floor);
                    if (variant == 0) fullPlan = plan;
                    else if (plan != fullPlan) ++planChanges;
                    cases.push_back({std::move(shop), std::move(plan), std::move(visit)});
                }
            }
        }
        require(planChanges > 0, "offer variants never changed the plan; key coverage is vacuous");
        // One warm cache across all shops; the second pass is served from it.
        one_combat::setNativeShopPlanCacheForTesting(1);
        (void)one_combat::takeNativeShopPlanStats();
        int purchases = 0;
        for (int pass = 0; pass < 2; ++pass) {
            for (const auto &c : cases) {
                auto state = c.shop;
                one_combat::PathHistory path;
                const auto plan = one_combat::nativeShopPlan(state, path, floor);
                require(plan == c.plan, "cached plan differs: '" + plan + "' vs '" + c.plan + "'");
                const auto visit = walkVisit(c.shop, floor);
                require(visit == c.visit, "cached shop visit differs:\n  " + visit + "\n  " + c.visit);
            }
            const auto stats = one_combat::takeNativeShopPlanStats();
            require(stats.shopExits == cases.size()
                        && stats.shopSteps == stats.shopExits + stats.replanCalls,
                    "shop step/exit/replan counters are inconsistent: steps="
                        + std::to_string(stats.shopSteps) + " exits="
                        + std::to_string(stats.shopExits) + " replans="
                        + std::to_string(stats.replanCalls));
            if (pass == 1) {
                require(stats.cacheHits == stats.planCalls && stats.replanCacheHits == stats.replanCalls,
                        "second pass was not fully served from the cache");
            }
            purchases = static_cast<int>(stats.replanCalls);
        }
        one_combat::setNativeShopPlanCacheForTesting(-1);
        require(purchases > 0, "fixtures never bought anything; the visit check is vacuous");
        std::cout << "ooc_shop_plan_cache_test: " << cases.size() << " shops, " << purchases
                  << " purchases, cached plans identical\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ooc_shop_plan_cache_test FAIL: " << e.what() << "\n";
        return 1;
    }
}
