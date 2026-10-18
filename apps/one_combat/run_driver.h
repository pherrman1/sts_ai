#ifndef STS_ONE_COMBAT_RUN_DRIVER_H
#define STS_ONE_COMBAT_RUN_DRIVER_H

#include <cstdint>
#include <functional>
#include <optional>

#include "game/GameContext.h"
#include "sim/search/ScumSearchAgent2.h"
#include "combat_transition.h"

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
// Default-off research observation of the actual driver-owned context; never a hypothetical policy copy.
extern thread_local std::function<void(const sts::GameContext &, const one_combat::PathHistory &)> t_realRunContextObserver;
// Called after each real OOC decision with its index and handler ("mcts",
// "chain", "heart_key", ...). While set, the driver arms
// one_combat::armOocPolicyTarget before the OOC MCTS step.
extern thread_local std::function<void(std::uint64_t, const char *)> t_realOocDecisionObserver;
// Default-off research observation of each real combat: called after exitBattle
// with the context copied just before Silver initialized the battle, the ended
// battle, the number of RAW persistent-exit callbacks and the first one's record
// (as combattransitiongen captures them). While unset the driver copies nothing.
extern thread_local std::function<void(const sts::GameContext &pre, const sts::BattleContext &,
    int rawCaptureCount, const std::optional<one_combat::CombatTransitionRecord> &)> t_realCombatObserver;

// Install the STS_FORCE_RELIC run-start override with native initial relic
// data, preserving the override's relic-pool removal behavior.
bool installRunForcedRelic(sts::GameContext &, sts::RelicId);

// Apply the exact ordered non-combat policy chain used by runFullRunOOC.
// Callers own the battle branch and must invoke this only for non-BATTLE
// screens so specialized combat capture can remain local to the caller.
void runFullRunOocPolicyStep(sts::GameContext &, sts::search::ScumSearchAgent2 &,
                             bool restV, bool shopV);
// STS_OOC_MCTS_TREE_RULES: one fixed step shared by the OOC MCTS tree and the
// live root (chest without Cursed Key, unreviewed reward relic, gold, potion
// with belt space, leave an empty reward screen). False when none applies.
bool oocTreeRuleStep(sts::GameContext &);
// The action oocTreeRuleStep would execute, without executing it (the live
// advisor lowers it to the game). Defined with the rules in ooc_tree_rules.cpp.
std::optional<sts::search::GameAction> oocTreeRuleAction(const sts::GameContext &);
// The chest and reward-relic rules alone; every OOC policy applies them.
std::optional<sts::search::GameAction> treasureChestRuleAction(const sts::GameContext &);
std::optional<sts::search::GameAction> rewardRelicRuleAction(const sts::GameContext &);
// Diagnostic: name of the chain layer that handled the latest step on this thread.
const char *lastOocChainHandler();

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
