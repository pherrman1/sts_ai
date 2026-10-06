#pragma once
// #367 Silver terminal win pricing with the new v_win (X2-B), default off.
//
// STS_SILVER_VWIN_LEAF=1 installs a per-combat pricer into native Silver.
// A won (or escaped) fight is priced at the state the engine reaches right
// after it: the combat reward screen (and other DECISION screens) by the
// ADR-0027 screen GBM on its pinned X2-B anchor, the map (a Smoke Bomb escape,
// which forfeits the rewards) and other screens by X2-B itself. Rewards come
// from re-drawn noncombat futures, never from the real RNG.
// STS_SILVER_VWIN_LEAF_SAMPLES=<k> (default 4) sets how many futures each
// price averages; the same futures are shared by all of a combat's prices.
#include <cstdint>
#include <string>

namespace one_combat {
struct SilverVwinLeafTotals {
    std::int64_t combats = 0;        // combats with an active pricer
    std::int64_t flatCombats = 0;    // combats whose win value does not vary: handcrafted pricing kept
    std::int64_t unsupported = 0;    // combats whose run state cannot be re-drawn: handcrafted pricing kept
    std::int64_t prices = 0;         // distinct terminal keys priced
    std::int64_t lookups = 0;        // all victory lookups, cache hits included
    std::int64_t screenGbm = 0, anchor = 0, fallbacks = 0, decided = 0;
    double seconds = 0;              // thread CPU spent building prices
};
// Reads the environment; returns the configuration label for sidecars
// ("off" when disabled). Call once before parallel runs.
std::string configureSilverVwinLeaf();
SilverVwinLeafTotals silverVwinLeafTotals();
// Installs the pricer and checks it on constructed normal, elite, Dead
// Adventurer and boss fights; prints a JSON report. No game is played.
int silverVwinLeafSelfTest();
}
