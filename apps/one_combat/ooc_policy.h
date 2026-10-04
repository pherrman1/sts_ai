#ifndef STS_ONE_COMBAT_OOC_POLICY_H
#define STS_ONE_COMBAT_OOC_POLICY_H

#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <vector>

#include "game/GameContext.h"
#include "sim/search/GameAction.h"
#include "sim/search/ScumSearchAgent2.h"
#include "compact_tree.h"
#include "run_features.h"
#include "ooc_v4_encoding.h"

struct OocCheckpointNet;
struct OocStrategicNet;
struct OocStrategicTokNet;
namespace sts::search { struct CombatCpsiNet; }

// These are loaded and configured by the integration driver.  The policy
// module reads the same instances; ownership stays in one_combat.cpp.
extern OocCheckpointNet g_oocCheckpointNet;
extern OocStrategicNet g_oocStrategicNet;
extern OocStrategicTokNet g_oocStrategicTokNet;
extern sts::search::CombatCpsiNet g_cpsiNet;

extern bool g_oocActionNN;
extern double g_oocStrategicMargin;
extern double g_oocStrategicMarginCard;
extern double g_oocStrategicMarginRest;
extern double g_oocStrategicMarginEvent;
extern double g_oocStrategicMarginShop;
extern double g_oocStrategicMarginTreasure;
extern double g_oocStrategicMarginBossRelic;
extern double g_oocStrategicMarginMap;
extern bool g_oocStrategicQ;
extern bool g_oocStrategicScorePolicy;
extern bool g_oocStrategicRest;
extern bool g_oocStrategicEvent;
extern bool g_oocStrategicShop;
extern bool g_oocStrategicTreasure;
extern bool g_oocStrategicBossRelic;
extern bool g_oocStrategicMap;
extern bool g_oocStrategicGateRegret;
extern double g_oocStrategicGateEps;
extern bool g_oocMapRoute;
extern int g_oocMapRouteHorizon;
extern std::string g_oocStrategicTracePath;
extern thread_local std::string t_oocStrategicTraceRows;
extern thread_local int t_oocStrategicTraceDecision;
extern thread_local bool t_shopV;

extern int g_bossRelicV;
extern int g_pathV;
extern int g_eventV;
extern bool g_restWin;

extern thread_local const one_combat::PathHistory *t_curPath;
extern thread_local one_combat::PathHistory t_emptyPath;

// Per event instance preferences computed by the active guide. Deferred
// branches must restore these along with the rest of the policy state.
struct MatchAndKeepWantCache {
    std::uint64_t seed = 0;
    int act = -1;
    int floor = -1;
    std::map<std::pair<int, bool>, bool> want;
};
extern thread_local MatchAndKeepWantCache t_matchAndKeepWant;

// State that affects the ordered OOC policy chain and therefore must travel
// with detached counterfactual branches. t_curPath is deliberately excluded:
// callers bind it to the branch's own PathHistory after restoring this value.
struct OocPolicyThreadState {
    int pathActionUses = 0;
    double pathAggr = 0.0;
    bool tokCheckPending = false;
    bool shopV = false;
    std::string strategicTraceRows;
    int strategicTraceDecision = 0;
    int actFightProbeDecisionIdx = 0;
    int actFightProbeActionIdx = 0;
    int actFightProbeFutureIdx = 0;
    MatchAndKeepWantCache matchAndKeepWant;
};

// Cross-module run configuration/state. These remain driver-owned because the
// retained run loop, strategic generators, or both also consume them.
extern bool g_collectKeys;
extern bool g_cardWin;
extern double g_cardWinSkip;
extern double g_cardSkipThresh;
extern bool g_shopWin;
extern bool g_nativeOoc;
extern int g_bossV;
extern double g_bossVW;
extern int g_bossDraftRows;
extern int g_neowV;
extern bool g_actFightProbeTrace;
extern thread_local int t_actFightProbeDecisionIdx;
extern thread_local int t_actFightProbeActionIdx;
extern thread_local int t_actFightProbeFutureIdx;

using sts::GameContext;
using sts::search::GameAction;
using sts::search::ScumSearchAgent2;
using one_combat::PathHistory;

// Shared live/driver seams. These are used by retained strategic generators or
// driver diagnostics as well as by the moved fallback policies. buildTokState
// additionally remains coupled to the driver's token-parity hook.
std::vector<float> richFeatureVec(GameContext &gc);
std::string vFeatCsv(const GameContext &gc);
std::string vTransact(const std::string &request);
TokState buildTokState(const GameContext &gc, const PathHistory &path);
int vQuery(GameContext &gc, int rIdx, double bossW = -1.0);
double vStateRaw(GameContext &gc);
double vStateWin(GameContext &gc);
// Throws when native model is unavailable; never contacts v_server.
double vStateWinNative(GameContext &gc);
// Same checks as vStateWinNative for an already-built rich feature vector.
double vStateWinNativeFeatures(const std::vector<float> &raw);
std::string vSendRecv(const std::string &request);
std::string mapGraphCsv(const GameContext &gc, bool rooms);
std::string mapSpecialCsv(const GameContext &gc);
int nativeWinCardPick(GameContext &gc, int rIdx);
bool winNetOk();
bool nativeWinPolicyAvailable();
bool nativeFloorPolicyAvailable();
bool nativeRestWinPolicy(GameContext &gc);
void nativeUpgradeSelectWinPolicy(GameContext &gc);
void nativeShopVPolicy(GameContext &gc);
int rowsToHardFight(const GameContext &gc);
// Driver-owned model seams. The native branches directly use the loaded
// compact-tree objects (g_winNet/g_floorNet), native shop planner, and rich
// feature index; moving them would broaden the model-loading boundary.
double vQueryHealWin(GameContext &gc, int healAmt);
int vQueryUpgradeWin(GameContext &gc, const std::vector<int> &candIds, double *gain);
int vQueryRemove(GameContext &gc, const std::vector<int> &candIds);
std::string vQueryShop(GameContext &gc);

bool regretGateTail(GameContext &, const std::vector<GameAction> &,
                    const std::vector<double> &, int, double, double, double, double,
                    void (*)(GameContext &, ScumSearchAgent2 &),
                    const ScumSearchAgent2 &);

namespace one_combat {
OocPolicyThreadState captureOocPolicyThreadState();
void restoreOocPolicyThreadState(const OocPolicyThreadState &state);

using ::richFeatureVec;

// True only while executing the multi-action card-reward fallback invocation.
bool inCardRewardFallback();
void serverCardRewardPolicy(GameContext &);
bool restWinPolicy(GameContext &);
void upgradeSelectWinPolicy(GameContext &);
bool eventVPolicy(GameContext &);
void shopVPolicy(GameContext &);
void bossRelicVPolicy(GameContext &);
void pathVPolicy(GameContext &);
int chooseMapAction(const GameContext &);
bool restVPolicy(GameContext &);
void upgradeSelectVPolicy(GameContext &);
void removeSelectVPolicy(GameContext &);
void neowVPolicy(GameContext &);
bool configurePathActionPolicyFromEnvironment();
void configureVPathPolicyFromEnvironment();
bool vPathPolicyEnabled();
void configureRestVPolicyFromEnvironment();
void resetPathPolicyState();

bool oocActionNNPolicy(GameContext &);
bool oocOnePlyCardRewardPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyRestPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyUpgradeSelectPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyEventPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyShopPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyTreasurePolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyBossRelicPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocOnePlyMapPolicy(GameContext &, const ScumSearchAgent2 &);
bool oocMapRouteSearchPolicy(GameContext &, const ScumSearchAgent2 &);

} // namespace one_combat

#endif // STS_ONE_COMBAT_OOC_POLICY_H
