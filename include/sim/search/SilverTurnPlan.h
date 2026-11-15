#ifndef STS_LIGHTSPEED_SILVERTURNPLAN_H
#define STS_LIGHTSPEED_SILVERTURNPLAN_H

// Research only (#1058, port of spire-mentor's turn_plan.rs): every deterministic
// plan of a Silver decision state, for an offline root-filter study. Nothing in
// play or search calls this.
//
// A plan is a line of the player's actions from the root that stops at
// END_TURN, at the first action that advances a combat RNG stream (Silver's own
// chance-node test: seedSearchRng, execute, searchRngCounter != 0, as in
// SilverSearcher's expansion), or where the fight ends. The search runs depth
// first over SilverSearcher::enumerateActions (Silver's canonical edges, so
// equivalent hand copies count once). Decision states are merged by
// hashBattleState (hash only, no equalForSearch check), so lines that reach the
// same state end in the same plans. Each plan records the set of root actions
// from which one of its lines starts (firstMask), which is what a root filter
// would keep. On a cap hit the set is marked capped and a filter must leave the
// root unfiltered.

#include <bitset>
#include <cstdint>
#include <functional>
#include <limits>
#include <string>
#include <vector>

#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "sim/search/SilverSearcher.h"

namespace sts::search {

    struct TurnPlanConfig {
        int maxPlans = 512;
        int maxNodes = 20000;
        int act = 1;   // for the incoming-damage stand-in of unrolled intents (5 * act, as turndomgen)
    };

    enum class TurnPlanEnd : int { END_TURN = 0, CHANCE = 1, FIGHT_OVER = 2, LEFT_TURN = 3 };

    using TurnPlanMask = std::bitset<128>;

    struct TurnPlan {
        TurnPlanMask firstMask;     // root actions (indices into TurnPlanSet::rootActions) with a line to this plan
        TurnPlanEnd end = TurnPlanEnd::END_TURN;
        Action last;                // END_TURN or the stochastic action; the action that ended the fight
        int length = 0;             // actions on the line by which the depth-first search first reached it, `last` included
        double logPrior = -std::numeric_limits<double>::infinity();   // best line: sum of log policy prior
        int bestFirst = -1;         // root action of the best-prior line
        std::vector<float> features;   // turnPlanFeatureNames() order
    };

    struct TurnPlanSet {
        bool capped = false;
        int nodes = 0;              // distinct decision states, root included
        int merges = 0;             // deterministic steps that reached an existing state
        std::int64_t execs = 0;     // executed actions
        std::vector<Action> rootActions;
        std::vector<TurnPlan> plans;
    };

    // Optional policy prior over `actions` at `state` (normalized); empty function = no logPrior.
    using TurnPlanPrior = std::function<std::vector<double>(const BattleContext &, const std::vector<Action> &)>;

    TurnPlanSet enumerateTurnPlans(const BattleContext &root, const SilverSearchContext &context,
                                   const TurnPlanConfig &config, const TurnPlanPrior &prior = {});

    // Hand-built end-state features relative to the root (spire-mentor's 18 end-state and 6 context
    // features, adapted to StS1 and this engine).
    const std::vector<std::string> &turnPlanFeatureNames();

}

#endif //STS_LIGHTSPEED_SILVERTURNPLAN_H
