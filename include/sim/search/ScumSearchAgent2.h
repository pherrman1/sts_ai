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

    // Default-off REST policy filter. Strictly parses unset/0/1;
    // enabled mode skips optional Recall only when key collection is off.
    bool oocSkipOptionalRecallEnabled();
    void filterOptionalRecallActions(const GameContext &gc, std::vector<GameAction> &actions);

    // Experimental eligibility rule, not a claim that every upgrade helps.
    // Leaves Dream Catcher, damaged players and forced rest actions unchanged.
    bool oocSkipFullHpRestEnabled();
    bool oocFullHpRestExclusionApplies(const GameContext &gc);
    void filterFullHpRestActions(const GameContext &gc, std::vector<GameAction> &actions);

    // Thread-local guard for surrogate-only OOC imagination; default false.
    extern thread_local bool g_disallowImaginedCombat;

    // Optional recording hook. If set, the combat backend calls it with the live
    // battle state at each decision point (once per agent decision -- NOT on the
    // hot search path). Used to snapshot combat states for training datasets;
    // leave null in normal play.
    extern thread_local std::function<void(const BattleContext&)> g_onCombatDecision;

    struct ScumSearchAgent2;
    // Executable-installed combat backend. one_combat installs native Silver
    // (NativeSilverBackend) at startup; tests may install stubs.
    // Process-wide, immutable after executable startup.  The callback must not
    // be thread-local: bestbench runs independent whole runs in OpenMP workers
    // and an opt-in combat backend selected at process startup must be visible
    // to each worker.  Backend-owned per-combat state remains local to the
    // callback implementation.
    extern std::function<void(ScumSearchAgent2&, GameContext&, BattleContext&)>
        g_externalCombatBackend;

    struct ScumSearchAgent2 {
        std::int64_t simulationCountTotal = 0;
        std::vector<int> gameActionHistory;

        int stepCount = 0;
        bool paused = false;
        bool pauseOnCardReward = false;

        bool printActions = false;
        bool printLogs = false;
        bool recordActions = false;

        int simulationCountBase = 50000;
        double bossSimulationMultiplier = 3;
        int stepsNoSolution = 5;
        int stepsWithSolution = 15;

        std::default_random_engine rng;


        // public interface
        void playout(GameContext &gc);

        // Initializes and plays a battle through the executable-installed
        // combat backend (Silver in one_combat); throws when none is
        // installed. Callers must not pre-initialize BattleContext so the
        // backend can install pre-init hooks (notably the Runic-Dome intent
        // observer) before BattleContext::init.
        void playoutBattle(GameContext &gc, BattleContext &bc);

        // A backend installed through g_externalCombatBackend commits validated
        // live actions through this same method, preserving health checks and
        // optional action logging.
        void takeAction(BattleContext &bc, Action a);

        // private methods
        void takeAction(GameContext &gc, GameAction a);

        void stepOutOfCombatPolicy(GameContext &gc);
        void cardSelectPolicy(GameContext &gc);
        void stepEventPolicy(GameContext &gc);
        void stepRandom(GameContext &gc);
        void stepRewardsPolicy(GameContext &gc);
        void weightedCardRewardPolicy(GameContext &gc);
    };

}


#endif //STS_LIGHTSPEED_SCUMSEARCHAGENT2_H
