//
// Created by keega on 9/19/2021.
//

#ifndef STS_LIGHTSPEED_SCUMSEARCHAGENT2_H
#define STS_LIGHTSPEED_SCUMSEARCHAGENT2_H

#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/GameAction.h"

#include <memory>
#include <random>
#include <functional>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    class BattleScumSearcher2;
    // Thread-local guard for surrogate-only OOC imagination; default false.
    extern thread_local bool g_disallowImaginedCombat;

    // Optional recording hook. If set, playoutBattle calls it with the live battle
    // state at each decision point (once per agent decision -- NOT on the hot search
    // path). Used to snapshot combat states for value-function training; leave null
    // in normal play. Cleared/set by the app around a combat-datagen run.
    extern thread_local std::function<void(const BattleContext&)> g_onCombatDecision;

    // Optional recording hook fired AFTER each root search completes (once per agent
    // decision), with the root state and the searched tree so its root edges' visit
    // counts can be logged as MCTS policy targets (state, action) -> visit share.
    // Used only by the policy-net datagen; null in normal play.
    extern thread_local std::function<void(const BattleContext&, const BattleScumSearcher2&)> g_onSearchComplete;

    struct BattleScumSearcher3;
    extern thread_local std::function<void(const BattleContext&, const BattleScumSearcher3&)> g_onSearchComplete3;

    struct ScumSearchAgent2;
    // Optional executable-installed combat backend. The core agent only calls
    // this value; it has no dependency on the isolated Silver model. Keeping
    // the hook default-null preserves ordinary Searcher2/Searcher3 linkage and
    // behavior, including unit-test targets that intentionally do not link
    // the vendored model.
    // Process-wide, immutable after executable startup.  The callback must not
    // be thread-local: bestbench runs independent whole runs in OpenMP workers
    // and an opt-in combat backend selected at process startup must be visible
    // to each worker.  Backend-owned per-combat state remains local to the
    // callback implementation.
    extern std::function<void(ScumSearchAgent2&, GameContext&, BattleContext&)>
        g_externalCombatBackend;

    struct ScumSearchAgent2 {
        std::int64_t simulationCountTotal;
        std::vector<int> gameActionHistory;

        int stepCount = 0;
        bool paused = false;
        bool pauseOnCardReward = false;

        bool printActions = false;
        bool printLogs = false;

        int simulationCountBase = 50000;
        double bossSimulationMultiplier = 3;
        int stepsNoSolution = 5;
        int stepsWithSolution = 15;

        std::default_random_engine rng;


        // public interface
        void playout(GameContext &gc);

        // Initializes and plays a battle through the executable-installed
        // backend when one is active, otherwise through the ordinary live
        // simulator/search path.  Direct whole-run callers must use this
        // overload rather than pre-initializing BattleContext themselves so
        // an observational backend can install pre-init hooks (notably the
        // Runic-Dome intent observer) before BattleContext::init.
        void playoutBattle(GameContext &gc, BattleContext &bc);

        // A backend installed through g_externalCombatBackend commits validated
        // live actions through this same method, preserving health checks and
        // optional action logging without exposing a raw Silver action index.
        void takeAction(BattleContext &bc, Action a);

        // private methods
        void playoutBattle(BattleContext &bc);
        void playoutBattleFair(BattleContext &bc);   // determinized: commit one move per search

        void takeAction(GameContext &gc, GameAction a);

        // Return true when at least one action was committed this call; false
        // when the tree/line could not supply an action at an unresolved
        // decision (classified by playoutBattle against the canonical live
        // action set for simulator-health reporting).
        bool stepThroughSolution(BattleContext &bc, std::vector<search::Action> &actions, search::BattleScumSearcher2 &searcher);
        bool stepThroughSearchTree(BattleContext &bc, search::BattleScumSearcher2 &searcher);
        void stepOutOfCombatPolicy(GameContext &gc);
        void cardSelectPolicy(GameContext &gc);
        void stepEventPolicy(GameContext &gc);
        void stepRandom(GameContext &gc);
        void stepRewardsPolicy(GameContext &gc);
        void weightedCardRewardPolicy(GameContext &gc);
    };

}


#endif //STS_LIGHTSPEED_SCUMSEARCHAGENT2_H
