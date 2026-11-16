// Exact prior-playout pick cache (issue #1051, STS_SILVER_PRIOR_PICK_CACHE): on the states real prior playouts
// reach (small searches of a few A20 fights with the deployed g7f_E prior), every pick nativeSilverPolicyArgmax
// returns with the cache on equals the argmax of the uncached prior, cache hits included, and the state-block
// fingerprint (combatStateFingerprint) is equal exactly when the state block is. A deliberately small table
// (2^10 slots) also exercises eviction. Run from the repository root.
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SilverSearcher.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace sts;

namespace {
int failures = 0;
void require(bool ok, const std::string &message) {
    if (!ok && failures++ < 20) std::cerr << "FAIL: " << message << '\n';
}

// Fixed seed from the engine parity thread's block (as active_power_features_test); no game is played.
constexpr std::uint64_t SEED = 111194452;
}

int main(int argc, char **argv) {
    const char *model = argc > 1 ? argv[1] : "models/combat_policy_mlp_g7f_E.txt";
    setenv("STS_SILVER_ROOT_PRIOR", model, 1);
    setenv("STS_SILVER_ROOT_PRIOR_WEIGHT", "400", 1);
    setenv("STS_SILVER_PRIOR_PICK_CACHE", "10", 1);
    try {
        search::installNativeSilverBackend();
    } catch (const std::exception &e) {
        std::cerr << "prior_pick_cache_test: " << e.what() << '\n';
        return 1;
    }
    const int S = search::combatFeatureCount();
    // State-block fingerprint <-> dense block, both ways.
    std::map<std::pair<std::uint64_t, std::uint64_t>, std::vector<float>> byPrint;
    std::map<std::vector<float>, std::pair<std::uint64_t, std::uint64_t>> byBlock;
    std::vector<float> reuse(S, 0.f), dense(S);
    std::vector<std::uint16_t> touched;
    long calls = 0;
    const MonsterEncounter fights[] = {MonsterEncounter::JAW_WORM, MonsterEncounter::GREMLIN_NOB,
                                       MonsterEncounter::THE_GUARDIAN, MonsterEncounter::HEXAGHOST,
                                       MonsterEncounter::SLIME_BOSS};
    const auto before = search::nativeSilverPriorPickCacheStats();
    for (const auto fight : fights) {
        GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
        BattleContext bc;
        bc.init(gc, fight);
        search::SilverSearchContext context;
        search::SilverSearcher s(bc, context);
        s.rolloutConfig.prior = true;
        s.rolloutPrior = [&](const BattleContext &state, const std::vector<search::SilverSearcher::Edge> &edges) {
            auto prior = search::nativeSilverPolicyPrior(state, edges);
            const int want = static_cast<int>(std::max_element(prior.begin(), prior.end()) - prior.begin());
            const int got = search::nativeSilverPolicyArgmax(state, edges);
            require(got == want, "cached pick " + std::to_string(got) + " != prior argmax " + std::to_string(want)
                                 + " at call " + std::to_string(calls));
            search::combatExtractFeatures(state, dense.data());
            search::combatExtractFeaturesReuse(state, reuse.data(), touched);
            require(std::memcmp(dense.data(), reuse.data(), sizeof(float) * S) == 0, "reuse block differs");
            std::uint64_t a = 0, b = 0;
            require(search::combatStateFingerprint(reuse.data(), touched, a, b), "no fingerprint (rich block off)");
            const auto [p, newPrint] = byPrint.emplace(std::make_pair(a, b), dense);
            require(newPrint || p->second == dense, "equal fingerprints, different state blocks");
            const auto [q, newBlock] = byBlock.emplace(dense, std::make_pair(a, b));
            require(newBlock || q->second == std::make_pair(a, b), "equal state blocks, different fingerprints");
            ++calls;
            return prior;
        };
        s.search(400);
    }
    const auto after = search::nativeSilverPriorPickCacheStats();
    const long lookups = after.lookups - before.lookups, hits = after.hits - before.hits;
    require(calls > 5000, "too few prior-playout calls: " + std::to_string(calls));
    require(lookups == calls, "cache lookups " + std::to_string(lookups) + " != calls " + std::to_string(calls));
    require(hits > calls / 20, "too few cache hits: " + std::to_string(hits));
    require(byPrint.size() == byBlock.size(), "fingerprint and block counts differ");
    std::cout << "prior_pick_cache: calls=" << calls << " hits=" << hits << " distinct states=" << byBlock.size()
              << (failures ? " FAILED" : " OK") << '\n';
    return failures ? 1 : 0;
}
