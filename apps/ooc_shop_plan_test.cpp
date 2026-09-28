// Seed-free fixture shops for the native shop step: the default re-plans every
// step, STS_NATIVE_SHOP_PLAN_ONCE runs one plan per visit, and The Courier or a
// stale stored plan falls back to the default behavior.
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
using one_combat::CompactTreeNet;

void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

sts::GameContext fixtureShop(std::uint64_t fixture, int gold, bool courier) {
    using namespace sts;
    GameContext gc(CharacterClass::IRONCLAD, fixture, 0);
    gc.screenState = ScreenState::SHOP_ROOM;
    gc.curRoom = Room::SHOP;
    gc.gold = gold;
    gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    if (courier) gc.relics.add({RelicId::THE_COURIER, 0});
    gc.info.shop.setup(gc);
    return gc;
}

std::string summary(const sts::GameContext &gc) {
    std::ostringstream out;
    out << "gold=" << gc.gold << " deck=" << gc.deck.size() << " relics=" << gc.relics.size()
        << " remove=" << gc.info.shop.removeCost << " screen=" << static_cast<int>(gc.screenState)
        << " prices=";
    for (int i = 0; i < 7; ++i) out << gc.info.shop.cardPrice(i) << ',';
    for (int i = 0; i < 3; ++i) out << gc.info.shop.relicPrice(i) << ',';
    return out.str();
}

// Runs shop steps (and the screens a purchase can open) until the visit ends
// or maxShopSteps shop steps have run.
sts::GameContext walkVisit(sts::GameContext gc, const CompactTreeNet &floor, int maxShopSteps = 32) {
    using namespace sts;
    one_combat::PathHistory path;
    for (int step = 0; step < 64 && maxShopSteps > 0; ++step) {
        if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::nativeFloorShopStep(gc, path, floor);
            --maxShopSteps;
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
    return gc;
}

std::vector<std::string> planTokens(sts::GameContext gc, const CompactTreeNet &floor) {
    one_combat::PathHistory path;
    std::istringstream in(one_combat::nativeShopPlan(gc, path, floor));
    std::vector<std::string> tokens;
    for (std::string t; in >> t;) tokens.push_back(t);
    return tokens;
}
}

int main(int argc, char **argv) {
    try {
        require(argc == 2, "usage: ooc_shop_plan_test v_rich_trees.txt");
        CompactTreeNet floor;
        require(floor.load(argv[1], one_combat::richIdxMap(), "floor"), "cannot load floor model");
        int visits = 0, purchases = 0, reuses = 0;
        for (std::uint64_t fixture = 1; fixture <= 4; ++fixture) {
            for (const int gold : {99, 320, 999}) {
                const auto shop = fixtureShop(0x5409000ULL + fixture, gold, false);
                const auto tokens = planTokens(shop, floor);

                // Default: every shop step re-plans.
                one_combat::setNativeShopPlanOnceForTesting(0);
                (void)one_combat::takeNativeShopPlanStats();
                const auto replanned = walkVisit(shop, floor);
                const auto base = one_combat::takeNativeShopPlanStats();
                require(base.shopExits == 1 && base.planReuses == 0
                            && base.planCalls == base.shopSteps
                            && base.shopSteps == 1 + base.replanCalls,
                        "default shop step did not re-plan every step");

                // Plan once: one plan, then the stored items in order.
                one_combat::setNativeShopPlanOnceForTesting(1);
                const auto once = walkVisit(shop, floor);
                const auto stats = one_combat::takeNativeShopPlanStats();
                require(once.screenState == sts::ScreenState::MAP_SCREEN && stats.shopExits == 1,
                        "plan-once visit did not leave the shop");
                require(stats.planCalls == 1 && stats.replanCalls == 0
                            && stats.planReuses == tokens.size(),
                        "plan-once visit re-planned: calls=" + std::to_string(stats.planCalls)
                            + " reuses=" + std::to_string(stats.planReuses)
                            + " planned=" + std::to_string(tokens.size()));
                for (const auto &t : tokens) {
                    if (t[0] == 'c') require(once.info.shop.cardPrice(t[1] - '0') == -1, "planned card not bought");
                    if (t[0] == 'r') require(once.info.shop.relicPrice(t[1] - '0') == -1, "planned relic not bought");
                    if (t[0] == 'x') require(once.info.shop.removeCost == -1, "planned removal not bought");
                }
                require(once.relics.size() + once.deck.size() - shop.relics.size() - shop.deck.size()
                            + (once.info.shop.removeCost == -1 && shop.info.shop.removeCost >= 0 ? 2 : 0)
                            == tokens.size(),
                        "plan-once visit bought more than the plan");
                // Unless a purchase changes later choices, both modes agree.
                if (summary(once) != summary(replanned))
                    std::cout << "  mode difference: " << summary(once) << "\n    vs " << summary(replanned) << "\n";

                // A plan left by a visit that stopped mid-shop must not leak into
                // a different state: a fresh visit re-plans from its own state.
                if (!tokens.empty()) {
                    (void)walkVisit(shop, floor, 1);
                    const auto other = fixtureShop(0x5409000ULL + fixture + 100, gold, false);
                    (void)one_combat::takeNativeShopPlanStats();
                    (void)walkVisit(other, floor);
                    const auto fresh = one_combat::takeNativeShopPlanStats();
                    require(fresh.planCalls == 1 && fresh.planReuses + 1 == fresh.shopSteps,
                            "stale stored plan leaked into another shop");
                }
                ++visits;
                purchases += static_cast<int>(tokens.size());
                reuses += static_cast<int>(stats.planReuses);
            }
        }
        require(purchases > 0, "fixtures never bought anything; the visit checks are vacuous");

        // The Courier restocks bought slots: plan-once must match the default.
        int courierPurchases = 0;
        for (std::uint64_t fixture = 1; fixture <= 4; ++fixture) {
            const auto shop = fixtureShop(0x5409000ULL + fixture, 999, true);
            one_combat::setNativeShopPlanOnceForTesting(0);
            const auto replanned = walkVisit(shop, floor);
            (void)one_combat::takeNativeShopPlanStats();
            one_combat::setNativeShopPlanOnceForTesting(1);
            const auto once = walkVisit(shop, floor);
            const auto stats = one_combat::takeNativeShopPlanStats();
            require(stats.planReuses == 0 && summary(once) == summary(replanned),
                    "Courier shop did not fall back to re-planning");
            courierPurchases += static_cast<int>(stats.shopSteps - 1);
        }
        require(courierPurchases > 0, "Courier fixtures never bought anything");
        one_combat::setNativeShopPlanOnceForTesting(-1);
        std::cout << "ooc_shop_plan_test: " << visits << " shops, " << purchases
                  << " planned purchases, " << reuses << " plan reuses, " << courierPurchases
                  << " Courier purchases\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ooc_shop_plan_test FAIL: " << e.what() << "\n";
        return 1;
    }
}
