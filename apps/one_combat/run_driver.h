#ifndef STS_ONE_COMBAT_RUN_DRIVER_H
#define STS_ONE_COMBAT_RUN_DRIVER_H

#include <cstdint>
#include <functional>

#include "game/GameContext.h"
#include "sim/search/ScumSearchAgent2.h"

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

namespace one_combat { struct PathHistory; }
// Research-only (#347 boss-entry rescue): when set, runFullRunOOC calls
// `before` at each boss battle after its budget is set and before Silver
// initializes the battle, and `after` once the battle has exited. Unset
// everywhere else; the hooks must not change the run.
namespace sts { class BattleContext; }
struct BossEntryHook {
    std::function<void(const sts::GameContext &, sts::search::ScumSearchAgent2 &,
                       const one_combat::PathHistory &)> before;
    std::function<void(const sts::GameContext &, const sts::BattleContext &)> after;
};
extern thread_local BossEntryHook *t_bossEntryHook;

// Install the STS_FORCE_RELIC run-start override with native initial relic
// data, preserving the override's relic-pool removal behavior.
bool installRunForcedRelic(sts::GameContext &, sts::RelicId);

// Apply the exact ordered non-combat policy chain used by runFullRunOOC.
// Callers own the battle branch and must invoke this only for non-BATTLE
// screens so specialized combat capture can remain local to the caller.
void runFullRunOocPolicyStep(sts::GameContext &, sts::search::ScumSearchAgent2 &,
                             bool restV, bool shopV);

// The deployed OOC policy: the non-battle step bestbench plays through
// runFullRunOOC with live OOC MCTS off (shop value on, rest value from
// STS_REST_V). Generators whose rows or labels assume the deployed policy call
// this instead of a copied chain (ledger §431). Returns the first primitive
// action executed on gc, or -1 when none went through GameAction::execute; one
// step can resolve several primitives (all card groups of a reward screen, a
// whole shop visit).
bool deployedRestV();
long long deployedOocPolicyStep(sts::GameContext &, sts::search::ScumSearchAgent2 &);
// True while finishOocCounterfactual continues a branch. Decision oracles that
// themselves run counterfactual continuations stand down, and E2C capture
// skips the branch's reward screens.
extern thread_local bool t_oocContinuation;

// Match and Keep: one fixed-pattern click (sim/search/MatchAndKeepPolicy.h).
// Cards are valued by the active guide as a lone card reward: OOC MCTS when
// `mctsMetrics` is given, otherwise the ordinary policy chain. Returns false
// outside the event.
namespace one_combat { struct PathHistory; struct LiveOocMctsMetrics; }
bool matchAndKeepPolicyStep(sts::GameContext &, sts::search::ScumSearchAgent2 &, bool restV, bool shopV,
                            const one_combat::PathHistory &, std::uint64_t runSeed,
                            std::uint64_t decisionIndex, one_combat::LiveOocMctsMetrics *mctsMetrics);
// True while the policy chain runs on a hypothetical Match and Keep offer.
extern thread_local bool t_oocHypotheticalStep;

// Concrete seams shared with retained one_combat.cpp drivers.  These keep
// environment parsing, model loading, and the counterfactual evaluators in
// the integration translation unit while giving the run loop its lifecycle
// entry points.
void runFloorProfileSelfTest();
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
