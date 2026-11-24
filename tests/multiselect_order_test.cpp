// SELECT_MANY order for the Amber encoders (search::amberBalanceMultiSelect, az_run_driver's combat actions; env
// STS_AZ_MULTISELECT_BALANCED, default on since 2026-11-24): a Gambler's Brew screen with 10 distinct hand cards keeps
// the engine's 1,024 masks as a set, and the first kAmberMaxActions (96) of the reordered list reach every hand index
// (the engine's ascending masks stop at index 6) and hold the empty selection, the whole hand, every single card and
// every "all but one"; a list of at most 96 actions is left as it is. With STS_AZ_MULTISELECT_BALANCED=0 (second ctest
// entry) the list stays ascending. No seeds, no gameplay.
#include "sim/search/Action.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/AmberTokens.h"
#include "combat/BattleContext.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <set>
#include <vector>

using namespace sts;

int main() {
    BattleContext bc;
    const CardId ids[10] = {CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::BASH, CardId::ANGER, CardId::CLASH,
                            CardId::CLEAVE, CardId::FLEX, CardId::HAVOC, CardId::HEADBUTT, CardId::IRON_WAVE};
    bc.cards.cardsInHand = 10;
    for (int i = 0; i < 10; ++i) bc.cards.hand[i] = CardInstance(ids[i]);
    bc.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    const auto engine = search::Action::enumerateCardSelectActions(bc);
    auto acts = engine;
    search::amberBalanceMultiSelect(acts, bc.cards.cardsInHand);
    int fail = 0;
    const auto check = [&](bool ok, const char *what) { if (!ok) { ++fail; std::cerr << "FAIL: " << what << "\n"; } };
    std::vector<unsigned> masks, engineMasks;
    for (const auto &a : acts) {
        check(a.getActionType() == search::ActionType::MULTI_CARD_SELECT, "multi-select actions only");
        masks.push_back(a.bits & 0x3ffu);
    }
    for (const auto &a : engine) engineMasks.push_back(a.bits & 0x3ffu);
    check(masks.size() == 1024, "every subset of 10 distinct cards");
    check(std::is_sorted(engineMasks.begin(), engineMasks.end()), "engine order ascending");
    check(std::set<unsigned>(masks.begin(), masks.end()) == std::set<unsigned>(engineMasks.begin(), engineMasks.end()),
          "same set of masks");
    const char *env = std::getenv("STS_AZ_MULTISELECT_BALANCED");
    const bool balanced = !env || std::strcmp(env, "0") != 0;
    if (balanced) {
        const std::set<unsigned> first(masks.begin(), masks.begin() + search::kAmberMaxActions);
        unsigned seen = 0;
        for (unsigned m : first) seen |= m;
        check(seen == 0x3ffu, "the first 96 masks reach every hand index");
        check(first.count(0) && first.count(0x3ffu), "empty selection and whole hand among the first 96");
        for (int i = 0; i < 10; ++i)
            check(first.count(1u << i) && first.count(0x3ffu & ~(1u << i)), "each single card and all but one");
        std::vector<search::Action> small(engine.begin(), engine.begin() + search::kAmberMaxActions);
        auto copy = small;
        search::amberBalanceMultiSelect(copy, bc.cards.cardsInHand);
        bool same = true;
        for (std::size_t i = 0; i < small.size(); ++i) same &= small[i].bits == copy[i].bits;
        check(same, "at most 96 actions: unchanged");
    } else {
        check(masks == engineMasks, "STS_AZ_MULTISELECT_BALANCED=0: the engine's order");
    }
    std::cout << (fail ? "FAILED" : "OK") << " multiselect_order (" << (balanced ? "balanced" : "engine order") << ")\n";
    return fail ? 1 : 0;
}
