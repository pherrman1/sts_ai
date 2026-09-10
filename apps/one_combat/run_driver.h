#ifndef STS_ONE_COMBAT_RUN_DRIVER_H
#define STS_ONE_COMBAT_RUN_DRIVER_H

#include <cstdint>

#include "game/GameContext.h"

struct RunResult {
    bool won;
    int floor;
    int act;
    int hpEnd;
    int maxHp;
    int fightsLost;
    double sec;
    int deathCombat = -1;
    int deathEncounter = -1;
};

RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV,
                        bool shopV, bool e2cCapture = false);

// Concrete seams shared with retained one_combat.cpp drivers.  These keep
// environment parsing, model loading, and the counterfactual evaluators in
// the integration translation unit while giving the run loop its lifecycle
// entry points.
void trainingRunStart();
bool trainingRunValid(bool outcomeDecided);
void vDisconnect();
int fightSims(const sts::GameContext &gc, int base);
double potionKeepValue(const sts::GameContext &gc);
bool bossGatedDraftPolicy(sts::GameContext &gc);
bool oocShopBeamPolicy(sts::GameContext &gc);
bool actFightProbeDraftPolicy(sts::GameContext &gc);
bool actFightProbeAllOocPolicy(sts::GameContext &gc);

extern bool g_oocStrategicTokCheck;
extern thread_local bool t_tokCheckPending;
extern sts::RelicId g_forceRelic;
extern int g_stopAfterAct;

#endif // STS_ONE_COMBAT_RUN_DRIVER_H
