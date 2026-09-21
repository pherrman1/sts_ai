#include "ooc_policy.h"
#include "ooc_checkpoint_policy.h"
#include "run_driver.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <sstream>
#include <unordered_set>

#include "game/Map.h"
#include "../ooc_checkpoint_net.h"
#include "../ooc_strategic_net.h"
#include "../ooc_strategic_tok_net.h"
#include "sim/search/CombatCpsiNet.h"
#include "sim/search/OocSemanticAction.h"

using namespace sts;

namespace one_combat {

static double sigmoid(double z) { return 1.0 / (1.0 + std::exp(-z)); }

// These settings and counters belong to the fallback path policy.  The driver
// only supplies environment configuration and resets the per-run state through
// the narrow entry points below; the policy implementation owns the state.
static int g_pathGraph = 0;
static int g_pathAction = 0;
static int g_pathActionMax = -1;
static double g_pathActionMargin = 0.0;
static bool g_pathActionTrace = false;
static thread_local int t_pathActionUses = 0;
static int g_vPath = 0;
static double g_vPathK = 0.4;
static thread_local double t_pathAggr = 0.0;
static double g_restVThreshold = 0.15;

bool configurePathActionPolicyFromEnvironment() {
    bool enabled = false;
    if (const char *d = std::getenv("STS_PATH_GRAPH")) {
        g_pathGraph = std::atoi(d) != 0;
        if (g_pathGraph) {
            enabled = true;
            std::cout << "[model-driven pathing via full-map graph NN ON]\n";
        }
    }
    if (const char *d = std::getenv("STS_PATH_ACTION")) {
        g_pathAction = std::atoi(d) != 0;
        if (const char *m = std::getenv("STS_PATH_ACTION_MAX"))
            g_pathActionMax = std::atoi(m);
        if (const char *m = std::getenv("STS_PATH_ACTION_MARGIN"))
            g_pathActionMargin = std::atof(m);
        g_pathActionTrace = std::getenv("STS_PATH_ACTION_TRACE")
                         && std::atoi(std::getenv("STS_PATH_ACTION_TRACE")) != 0;
        if (g_pathAction) {
            enabled = true;
            std::cout << "[model-driven pathing via paired route-action NN ON: max="
                      << g_pathActionMax << " margin=" << g_pathActionMargin << "]\n";
        }
    }
    return enabled;
}

void configureVPathPolicyFromEnvironment() {
    if (const char *d = std::getenv("STS_VPATH")) {
        g_vPath = std::atoi(d) != 0;
        if (const char *k = std::getenv("STS_VPATH_K")) g_vPathK = std::atof(k);
        if (g_vPath)
            std::cout << "[V-informed pathing ON: k=" << g_vPathK
                      << " (needs v_server on :5555)]\n";
    }
}

void configureRestVPolicyFromEnvironment() {
    if (const char *d = std::getenv("STS_REST_V_THRESH")) {
        g_restVThreshold = std::atof(d);
        std::cout << "[rest-V heal threshold = " << g_restVThreshold << "]\n";
    }
}

void resetPathPolicyState() {
    t_pathActionUses = 0;
    t_pathAggr = 0.0;
}

bool oocActionNNPolicy(GameContext &gc) {
    if (!g_oocActionNN || gc.act < 1 || gc.act > 3) return false;
    auto actions = search::GameAction::getAllActionsInState(gc);
    actions.erase(std::remove_if(actions.begin(), actions.end(), [&](const auto &action) {
        return !search::isSupportedAutonomousOocAction(gc, action);
    }), actions.end());
    if (actions.empty()) return false;

    // Native checkpoint-distilled inference (no server)
    if (g_oocCheckpointNet.ok) {
        const std::vector<float> state = richFeatureVec(gc);
        double best = -1e100;
        int bestIdx = -1;
        for (int i = 0; i < (int)actions.size(); ++i) {
            const double score = g_oocCheckpointNet.predict(
                state.data(), actions[i].bits, (int)gc.screenState, gc.act);
            if (score > best) { best = score; bestIdx = i; }
        }
        if (bestIdx < 0) return false;
        actions[bestIdx].execute(gc);
        return true;
    }

    // Server fallback
    std::ostringstream req;
    req << "OA;";
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) req << ',';
        req << actions[i].bits;
    }
    req << ';' << (int)gc.screenState << ';' << gc.act << ';' << vFeatCsv(gc) << '\n';
    const std::string resp = vTransact(req.str());
    std::istringstream in(resp);
    double best = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        std::string tok;
        if (!(in >> tok)) break;
        const auto comma = tok.find(',');
        if (comma == std::string::npos) break;
        const double pwin = std::atof(tok.substr(0, comma).c_str());
        const double hpFrac = std::atof(tok.substr(comma + 1).c_str());
        const double score = 10.0 * pwin + hpFrac * gc.maxHp;
        if (score > best) { best = score; bestIdx = i; }
    }
    if (bestIdx < 0) return false;
    actions[bestIdx].execute(gc);
    return true;
}

// Wave B regret gate (Step 5): per-screen deployed-default heuristic runners
// used to identify a_heur. Each mirrors the deployed-default OOC policy the
// datagen uses (runStrategicGenSeed), so the "heuristic" comparison arm and the
// regret arm share the same reference action.
void regretHeurCardReward(GameContext &pre, search::ScumSearchAgent2 &) {
    serverCardRewardPolicy(pre);   // native floor card pick with skip
}
static void regretHeurRest(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_restWin && restWinPolicy(pre)) {}
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurUpgrade(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_restWin) upgradeSelectWinPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
// The heuristic probes mirror the LIVE fallback chain of the screen (the code
// path that would run if the gate returned false), so a_heur is the action the
// run would actually take without the gate — not the flags-off datagen default.
// SHOP is the critical case: bestbench forces shopV=true, so the live fallback
// is shopVPolicy, not stepOutOfCombatPolicy's relic-buy-or-random.
static void regretHeurEvent(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_eventV && pre.curEvent != Event::NEOW) eventVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurShop(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (t_shopV) shopVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurAgent(GameContext &pre, search::ScumSearchAgent2 &agent) {
    agent.stepOutOfCombatPolicy(pre);   // TREASURE
}
static void regretHeurBossRelic(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_bossRelicV) bossRelicVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurMap(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_pathV) pathVPolicy(pre);
    else search::GameAction(chooseMapAction(pre)).execute(pre);
}

// One-ply post-action search for CARD REWARD decisions (Phase 5, 5.5.1).
// Every legal reward action is scored and the best action is executed only
// when its margin over the runner-up meets the gate
// (STS_OOC_STRATEGIC_MARGIN), otherwise the heuristic card policy stays in
// charge.  Scoring (Tier-B round, §72): the Q(s,a) head
// (OocStrategicNet::predictActionValue) evaluates each action directly on the
// pre-decision state — no clones or successor states.  STS_OOC_STRATEGIC_Q=0
// restores the V2 behaviour: successors of copied GameContexts are scored with
// the value head of the successor screen.  Greedy un-gated deployment is a
// recorded failure mode (EXPERIMENTS §66m), so the gate is mandatory.
// Score one V5/V6 action with the loaded strategic net: the Q_win head by
// default, or the policy head when STS_OOC_STRATEGIC_SCORE=policy (Phase F
// 5.7.2 gate arm).  predictPolicyLogit returns the raw logit — sigmoid to the
// probability scale so the probability-point STS_OOC_STRATEGIC_MARGIN
// semantics apply unchanged.
double oocStrategicScore(const float *state, std::uint32_t bits,
                                const int cats[6], int actionType, int screen) {
    if (g_oocStrategicScorePolicy)
        return sigmoid(g_oocStrategicNet.predictPolicyLogit(state, bits, cats, actionType, screen));
    return g_oocStrategicNet.predictActionValue(state, bits, cats, actionType, screen);
}
// Exact primitive candidate contract shared with the V4 one-ply gates.
bool oocOnePlyCardRewardPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if (!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) return false;
    if (gc.screenState != ScreenState::REWARDS) return false;
    auto &r = gc.info.rewardsContainer;
    if (r.cardRewardCount == 0) return false;
    if (g_oocStrategicTokNet.ok && !g_oocStrategicGateRegret
            && g_oocStrategicTracePath.empty() && !t_tokCheckPending) {
        const PathHistory emptyPath;
        const double margin = g_oocStrategicMarginCard >= 0.0
            ? g_oocStrategicMarginCard : g_oocStrategicMargin;
        return takeQualifiedV4CardReward(gc, t_curPath ? *t_curPath : emptyPath,
                                         g_oocStrategicTokNet, margin);
    }
    using RT = search::GameAction::RewardsActionType;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate

    const double margin = g_oocStrategicMarginCard >= 0.0 ? g_oocStrategicMarginCard : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        // V4 token net: Q(s,a) on the token state (STS_OOC_STRATEGIC_Q does
        // not apply to the token path). TokState built once per decision.
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const bool useQ = g_oocStrategicQ;
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            double v;
            if (useQ) {
                int actionType, c1, c2, c3, cand1, cand2, cand3;
                strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
                const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
                v = oocStrategicScore(state.data(), actions[i].bits,
                                      cats, actionType, (int)gc.screenState);
            } else {
                GameContext probe = gc;
                probe.map = std::make_shared<Map>(*gc.map);
                actions[i].execute(probe);
                v = g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                   (int)probe.screenState);
            }
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurCardReward, agent);
}

// One-ply post-action search for CAMPFIRE decisions (Phase 5, 5.5.2): every
// legal rest option (REST/SMITH/LIFT/GIRYA/PEACE_PIPE/SHOVEL/SKIP) is scored
// with the Q(s,a) head on the pre-decision state and the best option is
// executed only when its margin over the runner-up meets the gate; otherwise
// the default rest layer (win-rate rest) runs.  The smith's upgrade-target
// pick (CARD_SELECT/UPGRADE) is gated separately by
// oocOnePlyUpgradeSelectPolicy under the same flag.
bool oocOnePlyRestPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicRest) return false;
    if (gc.screenState != ScreenState::REST_ROOM) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginRest >= 0.0 ? g_oocStrategicMarginRest : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurRest, agent);
}

// One-ply Q gate for the smith's upgrade-target pick (the CARD_SELECT screen
// that follows a campfire SMITH).  Scores every legal target; executes the
// argmax only when its margin over the runner-up meets the gate, else the
// win-rate upgrade-target layer runs.
bool oocOnePlyUpgradeSelectPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicRest) return false;
    if (gc.screenState != ScreenState::CARD_SELECT
        || gc.info.selectScreenType != CardSelectScreenType::UPGRADE) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginRest >= 0.0 ? g_oocStrategicMarginRest : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurUpgrade, agent);
}

// One-ply post-action search for EVENT decisions (Phase 5, 5.5.3): every legal
// event option (including Neow) is scored with the Q(s,a) head on the
// pre-decision state and the best option is executed only when its margin over
// the runner-up meets the gate; otherwise the default event layer runs.  The
// Tier-B labels already average the stochastic continuations of each option,
// so no RNG-clone sampling is needed at deployment.
bool oocOnePlyEventPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicEvent) return false;
    if (gc.screenState != ScreenState::EVENT_SCREEN) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;   // e.g. MATCH_AND_KEEP
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginEvent >= 0.0 ? g_oocStrategicMarginEvent : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurEvent, agent);
}

// One-ply post-action search for SHOP decisions (R6, §76): every legal shop
// action (buy card/relic/potion, CARD_REMOVE, leave) is scored with the Q(s,a)
// head on the pre-decision state and the best action is executed only when its
// margin over the runner-up meets the gate; otherwise the V-knapsack shop layer
// runs.  Called once per decision, so repeated buys are re-scored each time.
bool oocOnePlyShopPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicShop) return false;
    if (gc.screenState != ScreenState::SHOP_ROOM) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginShop >= 0.0 ? g_oocStrategicMarginShop : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurShop, agent);
}

// One-ply post-action search for TREASURE decisions (R6, §76): the chest open/
// skip actions are scored with the Q(s,a) head on the pre-decision state and
// the best action is executed only when its margin over the runner-up meets
// the gate; otherwise the default treasure layer runs.
bool oocOnePlyTreasurePolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicTreasure) return false;
    if (gc.screenState != ScreenState::TREASURE_ROOM) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginTreasure >= 0.0 ? g_oocStrategicMarginTreasure : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurAgent, agent);
}

// One-ply post-action search for BOSS RELIC decisions (R6, §76): the three
// offered relics plus skip are scored with the Q(s,a) head on the
// pre-decision state and the best action is executed only when its margin over
// the runner-up meets the gate; otherwise the boss relic layer runs.
bool oocOnePlyBossRelicPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicBossRelic) return false;
    if (gc.screenState != ScreenState::BOSS_RELIC_REWARDS) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginBossRelic >= 0.0 ? g_oocStrategicMarginBossRelic : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurBossRelic, agent);
}

// One-ply post-action search for MAP decisions (M1 wave): every legal child
// node of the visible map DAG is scored with the Q(s,a) head on the
// pre-decision state and the best child is executed only when its margin over
// the runner-up meets the gate; otherwise the heuristic pathing layer runs.
// Candidate resolution follows strategicCands' MAP_SCREEN case (cand1=x,
// cand2=row, cand3=room), identical to the Tier-B training rows, so no new
// datagen is needed. The map is fully visible at decision time (no hidden RNG
// or future-seed use), satisfying spec A.14 for this gate.
bool oocOnePlyMapPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicMap) return false;
    if (gc.screenState != ScreenState::MAP_SCREEN || gc.curMapNodeY == 14) return false;
    std::vector<search::GameAction> actions = v4CandidateActions(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginMap >= 0.0 ? g_oocStrategicMarginMap : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                prepared, actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        // V6 map-DAG encoder (5.3.2): when the artifact carries it, score each
        // child with the route embedding (rooms/edges/special from the visible
        // map, position + chosen child from gc / cand1), matching the trainer's
        // MAP-screen rows exactly (mapbatch export format).
        int mapRooms[105], mapEdges[105], mapSpecial[105];
        const bool useMapEnc = g_oocStrategicNet.mapEnc;
        if (useMapEnc) {
            const Map &mp = *gc.map;
            for (int y = 0; y < 15; ++y)
                for (int x = 0; x < 7; ++x) {
                    const int i = y * 7 + x;
                    const MapNode &n = mp.getNode(x, y);
                    mapRooms[i] = (int)n.room;
                    int em = 0;
                    for (int e = 0; e < n.edgeCount; ++e) em |= 1 << n.edges[e];
                    mapEdges[i] = em;
                    mapSpecial[i] = 0;
                }
            if (mp.burningEliteX >= 0 && mp.burningEliteY >= 0 && !gc.greenKey)
                mapSpecial[mp.burningEliteY * 7 + mp.burningEliteX] = 1;
        }
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = useMapEnc
                ? g_oocStrategicNet.predictMapActionValue(state.data(), actions[i].bits, cats,
                                                          actionType, (int)gc.screenState,
                                                          mapRooms, mapEdges, mapSpecial,
                                                          gc.curMapNodeX, gc.curMapNodeY, cand1)
                : oocStrategicScore(state.data(), actions[i].bits,
                                    cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurMap, agent);
}

// Candidate identity and entity encodings are policy-owned; datagen callers
// use the same concrete functions through the public module contract.
// ---------------------------------------------------------------------------
// M2: short-horizon map route search (plan 5.6.2, spec A.11 "map routes").
//
// For each legal child node of the visible map DAG, expand the downstream
// graph HORIZON rows deep (2..5). Each room on a route is priced with the
// C_psi combat outcome surrogate (CombatCpsiNet): fights return P(death) and
// E[hp/maxHp | win]; rests heal a fixed 30% of max HP; shops/treasures/events
// pass through unchanged (v1 limitation). Encounters for hypothetical fights
// are sampled from the act's visible pool (strong monsters / elites) with a
// LOCAL RNG-free expectation — never the run's true future encounter list
// (spec A.14). A route's value = survival-probability × strategic V-head at
// the leaf state (map position advanced to the leaf node, HP updated). The
// best route per child is the max over its downstream paths; the child is
// executed only when its margin over the runner-up meets the gate, else
// chooseMapAction runs. This replaces the M1 one-ply Q gate for map decisions
// when enabled.
// ---------------------------------------------------------------------------
struct RouteCpsiCache {
    bool loaded = false;
    float pDeath = 1.f;   // P(death) from the sampled encounter pool
    float hpFrac = 1.f;   // E[hp/maxHp | win]
};

// Pool-average C_psi expectation for one room type. Row-14 nodes hold the
// last real rooms of the act (elites/hallways); the forced boss fight at
// y==14 is not expanded by this search (the leaf V prices the remaining run).
bool routeCpsiExpect(const GameContext &gc, Room room,
                            RouteCpsiCache &out) {
    if (!g_cpsiNet.loaded()) return false;
    const int act = gc.act;
    if (room == Room::MONSTER) {
        // Weighted pool expectation: the act's strong pool with its visible
        // weights (MonsterEncounterPool::strongWeights) — the conditional
        // distribution a player knows, never the run's true encounter list.
        const int poolSize = (int)MonsterEncounterPool::strongCount[act - 1];
        double pd = 0, hp = 0, wsum = 0;
        for (int i = 0; i < poolSize; ++i) {
            const double w = MonsterEncounterPool::strongWeights[act - 1][i];
            float scalar[search::kCpsiScalars];
            float deck[search::kCpsiCards];
            float relics[search::kCpsiRelics];
            float potions[search::kCpsiPotions];
            search::buildCpsiEntry(gc, scalar, deck, relics, potions);
            search::CpsiOut r;
            g_cpsiNet.predict(scalar, deck, relics, potions,
                              (int)MonsterEncounterPool::strongEnemies[act - 1][i], r);
            pd += w * r.death; hp += w * r.hp; wsum += w;
        }
        out.pDeath = (float)(pd / wsum);
        out.hpFrac = (float)(hp / wsum);
        return true;
    }
    if (room == Room::ELITE) {
        // Elites are drawn uniformly (rollElite: 1/3 each).
        double pd = 0, hp = 0;
        for (int i = 0; i < 3; ++i) {
            float scalar[search::kCpsiScalars];
            float deck[search::kCpsiCards];
            float relics[search::kCpsiRelics];
            float potions[search::kCpsiPotions];
            search::buildCpsiEntry(gc, scalar, deck, relics, potions);
            search::CpsiOut r;
            g_cpsiNet.predict(scalar, deck, relics, potions,
                              (int)MonsterEncounterPool::elites[act - 1][i], r);
            pd += r.death; hp += r.hp;
        }
        out.pDeath = (float)(pd / 3);
        out.hpFrac = (float)(hp / 3);
        return true;
    }
    return false;
}

// Leaf value of a route: the per-screen value head on the state advanced to
// the leaf node with the route's expected HP (V3 rich state; token-net glob
// when the token net is loaded). The leaf is a MAP_SCREEN successor state
// (the next decision is another map choice), so the MAP head prices it.
// Mutates only curMapNodeX/Y/curHp and restores them (no deep copy per leaf).
double mapRouteLeafValue(GameContext &gc, int leafX, int leafY,
                                double hpFrac) {
    const int saveX = gc.curMapNodeX, saveY = gc.curMapNodeY, saveHp = gc.curHp;
    gc.curMapNodeX = leafX;
    gc.curMapNodeY = leafY;
    gc.curHp = (int)std::llround(hpFrac * gc.maxHp);
    double v;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        v = g_oocStrategicTokNet.predictValue(ts.glob, (int)ScreenState::MAP_SCREEN);
    } else {
        v = g_oocStrategicNet.predictValue(richFeatureVec(gc).data(),
                                           (int)ScreenState::MAP_SCREEN);
    }
    gc.curMapNodeX = saveX; gc.curMapNodeY = saveY; gc.curHp = saveHp;
    return v;
}

// Best route value from node (x,y) looking down `depth` more rows, given the
// survival prob and HP fraction carried so far. Max over downstream paths
// (mirrors chooseMapAction's bottom-up DP over the visible DAG). The C_psi
// expectation per node is memoized in cache[7*15] (state-independent within
// the decision: the entry state used is the CURRENT pre-decision state, an
// explicit v1 approximation documented in the wave contract).
double mapRouteSearch(GameContext &gc, int x, int y, int depth,
                             double survival, double hpFrac,
                             RouteCpsiCache cache[7 * 15]) {
    const Map &map = *gc.map;
    const MapNode &n = map.getNode(x, y);
    if (depth <= 0 || y >= 14) {
        return survival * std::max(0.0, mapRouteLeafValue(gc, x, y, hpFrac));
    }
    double nextSurvival = survival, nextHp = hpFrac;
    switch (n.room) {
        case Room::MONSTER:
        case Room::ELITE: {
            RouteCpsiCache &cpsi = cache[y * 7 + x];
            if (!cpsi.loaded) {
                cpsi.loaded = routeCpsiExpect(gc, n.room, cpsi);
                if (!cpsi.loaded) {
                    cpsi.pDeath = 0.f;      // C_psi missing: price the fight as free
                    cpsi.hpFrac = 1.f;
                }
            }
            nextSurvival = survival * (1.0 - cpsi.pDeath);
            nextHp = hpFrac * cpsi.hpFrac;
            break;
        }
        case Room::REST:
            nextHp = std::min(1.0, hpFrac + 0.30);   // base campfire heal
            break;
        default:
            break;                                    // SHOP/TREASURE/EVENT pass through
    }
    if (nextSurvival <= 1e-9 || nextHp <= 0.0) return 0.0;

    double bestChild = -1e100;
    for (int i = 0; i < n.edgeCount; ++i) {
        const double v = mapRouteSearch(gc, n.edges[i], y + 1, depth - 1,
                                        nextSurvival, nextHp, cache);
        if (v > bestChild) bestChild = v;
    }
    if (n.edgeCount == 0) {
        // Dead-end node: the route stops here (leaf).
        return nextSurvival * std::max(0.0, mapRouteLeafValue(gc, x, y, nextHp));
    }
    return bestChild;
}

// M2: short-horizon map route search (plan 5.6.2). Requires a loaded C_psi
// surrogate AND a strategic net (V3 or V4) for the leaf. Encounters come from
// the act's visible pool via expectation, so no hidden future information is
// used. Margin-gated like every other gate.
bool oocMapRouteSearchPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_cpsiNet.loaded()) return false;
    if (!g_oocMapRoute) return false;
    if (gc.screenState != ScreenState::MAP_SCREEN || gc.curMapNodeY == 14) return false;
    if (gc.act < 1 || gc.act > 3) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    const int depth = std::max(2, std::min(5, g_oocMapRouteHorizon));
    const double margin = g_oocStrategicMarginMap >= 0.0 ? g_oocStrategicMarginMap : g_oocStrategicMargin;
    std::vector<double> q(actions.size(), -1e100);   // per-route scores for the regret gate

    const double baseHpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;
    RouteCpsiCache cache[7 * 15];   // shared across children: the C_psi entry
                                    // state is always the current pre-decision
                                    // state (documented v1 approximation)
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        const int childX = actions[i].getIdx1();
        const int childY = gc.curMapNodeY + 1;
        const double v = mapRouteSearch(gc, childX, childY, depth, 1.0, baseHpFrac, cache);
        q[i] = v;
        if (v > best) { second = best; best = v; bestIdx = i; }
        else if (v > second) second = v;
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurMap, agent);
}

// Live fallback policy family.  Model loading, feature construction, and the
// transport seams remain driver-owned; these functions own the decisions made
// by the ordinary OOC chain.
// V(deck, hp+healAmt) - V(deck, hp), in expected-final-floor units (0 on error).
static double vQueryHeal(GameContext &gc, int healAmt) {
    std::string req = "H;" + std::to_string(healAmt) + ";"
                    + vFeatCsv(gc) + "\n";
    const std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// Index (into candIds) of the deck's most-valued card to upgrade (0 on error).
static int vQueryUpgrade(GameContext &gc, const std::vector<int> &candIds) {
    std::string req = "U;";
    for (size_t i = 0; i < candIds.size(); ++i) {
        if (i) req += ',';
        req += std::to_string(candIds[i]);
    }
    req += ";" + vFeatCsv(gc) + "\n";
    const std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// Direct paired counterfactual rest-vs-smith model. Returns false when no
// server-side model is deployed, preserving the win-rate marginal fallback.
static bool vQueryRestCounterfactual(GameContext &gc, double *delta) {
    if (g_nativeOoc) return false;
    const std::string resp = vTransact("RC;" + vFeatCsv(gc) + "\n");
    double d = 0.0;
    if (resp.empty() || resp.rfind("NA", 0) == 0
        || std::sscanf(resp.c_str(), "%lf", &d) != 1 || !std::isfinite(d)) return false;
    if (delta) *delta = d;
    return true;
}

// Deduped ids of the deck's upgradeable cards (candidates for a smith).
static std::vector<int> upgradeableIds(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        const int id = (int)gc.deck.cards[i].getId();
        if (std::find(ids.begin(), ids.end(), id) == ids.end()) ids.push_back(id);
    }
    return ids;
}

void serverCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
        const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                  : vQuery(gc, rIdx, bossW);
        search::GameAction(RT::CARD, rIdx, idx).execute(gc);
    }
}

void bossRelicVPolicy(GameContext &gc) {
    int best = -1; double bestV = -1e18;
    for (int i = 0; i < 3; ++i) {
        if (gc.info.bossRelics[i] == RelicId::INVALID) continue;
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        g2.chooseBossRelic(i);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseBossRelic(best < 0 ? 0 : best);
}

void neowVPolicy(GameContext &gc) {
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)gc.info.neowRewards.size(); ++i) {
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        g2.chooseNeowOption(g2.info.neowRewards[i]);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseNeowOption(gc.info.neowRewards[best]);
}

void pathVPolicy(GameContext &gc) {
    const Map &map = *gc.map;
    std::vector<int> cands;
    const int childRow = gc.curMapNodeY + 1;
    if (gc.curMapNodeY < 0) {
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) cands.push_back(n.x);
    } else {
        const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < n.edgeCount; ++i) cands.push_back(n.edges[i]);
    }
    if (cands.empty()) { search::GameAction(chooseMapAction(gc)).execute(gc); return; }
    if (g_pathAction) {
        const int heuristic = chooseMapAction(gc);
        std::ostringstream req;
        req << "PA;";
        for (int i = 0; i < (int)cands.size(); ++i) { if (i) req << ','; req << cands[i]; }
        req << ';' << heuristic << ';' << mapGraphCsv(gc, true) << ';' << mapGraphCsv(gc, false) << ';'
            << mapSpecialCsv(gc) << ';' << vFeatCsv(gc);
        int chosen = -1; double advantage = -1e9;
        const std::string response = vSendRecv(req.str());
        std::sscanf(response.c_str(), "%d %lf", &chosen, &advantage);
        const bool capacity = g_pathActionMax < 0 || t_pathActionUses < g_pathActionMax;
        if (g_pathActionTrace) {
            #pragma omp critical(path_action_trace)
            std::cerr << "[path-action] seed=" << gc.seed << " pos=" << gc.curMapNodeX << ','
                      << gc.curMapNodeY << " heuristic=" << heuristic << " chosen=" << chosen
                      << " advantage=" << advantage << " uses=" << t_pathActionUses
                      << " capacity=" << capacity << " response='" << response << "'\n";
        }
        if (capacity && advantage >= g_pathActionMargin
            && std::find(cands.begin(), cands.end(), chosen) != cands.end()) {
            search::GameAction(chosen).execute(gc);
            if (chosen != heuristic) ++t_pathActionUses;
            return;
        }
        search::GameAction(heuristic).execute(gc);
        return;
    }
    int bestX = cands[0]; double bestV = -1e18;
    for (int x : cands) {
        double v;
        if (g_pathGraph) {
            std::string req = "PG;" + std::to_string(x) + ';' + mapGraphCsv(gc, true) + ';'
                            + mapGraphCsv(gc, false) + ';' + mapSpecialCsv(gc) + ';' + vFeatCsv(gc);
            v = 0.5;
            std::sscanf(vSendRecv(req).c_str(), "%lf", &v);
        } else {
            const int oX = gc.curMapNodeX, oY = gc.curMapNodeY;
            gc.curMapNodeX = x; gc.curMapNodeY = childRow;
            v = vStateWin(gc);
            gc.curMapNodeX = oX; gc.curMapNodeY = oY;
        }
        if (v > bestV) { bestV = v; bestX = x; }
    }
    search::GameAction(bestX).execute(gc);
}

bool eventVPolicy(GameContext &gc) {
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        actions[i].execute(g2);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    actions[best].execute(gc);
    return true;
}

bool restVPolicy(GameContext &gc) {
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    const double healGain = vQueryHeal(gc, healAmt);
    search::GameAction(healGain >= g_restVThreshold ? 0 : 1, 0).execute(gc);
    return true;
}

void upgradeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryUpgrade(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

bool restWinPolicy(GameContext &gc) {
    if (nativeWinPolicyAvailable()) return nativeRestWinPolicy(gc);
    if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
        search::GameAction(2, 0).execute(gc);
        return true;
    }
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    double pairedDelta = 0.0;
    if (vQueryRestCounterfactual(gc, &pairedDelta)) {
        search::GameAction(pairedDelta >= 0.0 ? 0 : 1, 0).execute(gc);
        return true;
    }
    const double healGain = vQueryHealWin(gc, healAmt);
    std::vector<int> ids = upgradeableIds(gc);
    double upGain = 0.0;
    if (!ids.empty()) vQueryUpgradeWin(gc, ids, &upGain);
    search::GameAction(healGain >= upGain ? 0 : 1, 0).execute(gc);
    return true;
}

void upgradeSelectWinPolicy(GameContext &gc) {
    if (nativeWinPolicyAvailable()) { nativeUpgradeSelectWinPolicy(gc); return; }
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    double g = 0.0;
    const int idx = ids.empty() ? 0 : vQueryUpgradeWin(gc, ids, &g);
    search::GameAction(idx, 0).execute(gc);
}

void shopVPolicy(GameContext &gc) {
    if (nativeFloorPolicyAvailable() && !g_actFightProbeTrace) {
        nativeShopVPolicy(gc); return;
    }
    using RT = search::GameAction::RewardsActionType;
    const std::string requestState = g_actFightProbeTrace ? vFeatCsv(gc) : std::string{};
    std::string plan = vQueryShop(gc);
    if (g_actFightProbeTrace) {
        const Shop &sh = gc.info.shop;
        std::cerr << "[shop-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " gold=" << gc.gold
                  << " cardRng=" << gc.cardRng.seed0 << ':' << gc.cardRng.seed1
                  << " merchantRng=" << gc.merchantRng.seed0 << ':' << gc.merchantRng.seed1
                  << " potionRng=" << gc.potionRng.seed0 << ':' << gc.potionRng.seed1
                  << " remove=" << sh.removeCost << " cards=";
        for (int i = 0; i < 7; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.cards[i].getId() << ':' << sh.cardPrice(i);
        std::cerr << " relics=";
        for (int i = 0; i < 3; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.relics[i] << ':' << sh.relicPrice(i);
        std::cerr << " featHash=" << std::hash<std::string>{}(requestState)
                  << " plan=" << plan << "]\n";
    }
    std::istringstream is(plan);
    std::string tok;
    if (!(is >> tok) || tok.empty()) { search::GameAction(RT::SKIP).execute(gc); return; }
    const int idx = tok.size() > 1 ? std::atoi(tok.c_str() + 1) : 0;
    if (tok[0] == 'c')      search::GameAction(RT::CARD,  idx).execute(gc);
    else if (tok[0] == 'r') {
        const search::GameAction action(RT::RELIC, idx);
        if (search::isSupportedAutonomousOocAction(gc, action)) action.execute(gc);
        else search::GameAction(RT::SKIP).execute(gc);
    }
    else if (tok[0] == 'x') search::GameAction(RT::CARD_REMOVE).execute(gc);
    else                    search::GameAction(RT::SKIP).execute(gc);
}

void removeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryRemove(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

static int bossFloorForAct(int act) { return act <= 1 ? 17 : act == 2 ? 34 : 50; }

static double roomValue(Room r, int y, const GameContext &gc) {
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;
    const int act = gc.act;
    double v;
    switch (r) {
        case Room::ELITE: {
            const double base = 14.0;
            const double later = 0.5 * y;
            const double gate = std::clamp((hpFrac - 0.40) / 0.50, 0.0, 1.0);
            v = (base + later) * gate;
            break;
        }
        case Room::REST: v = 9.0 + (hpFrac < 0.5 ? 5.0 : 0.0); break;
        case Room::SHOP: v = gc.gold >= 120 ? 7.0 : gc.gold >= 75 ? 4.0 : 1.5; break;
        case Room::MONSTER: {
            const double actMul = act == 1 ? 1.0 : 0.55;
            const double hpMul = 0.4 + 0.9 * hpFrac;
            v = 3.2 * actMul * hpMul;
            break;
        }
        case Room::EVENT: v = 3.8; break;
        case Room::TREASURE: v = 6.0; break;
        default: return 0.0;
    }
    if (g_vPath && t_pathAggr != 0.0) {
        const double a = g_vPathK * t_pathAggr;
        switch (r) {
            case Room::ELITE:   v *= (1.0 + a); break;
            case Room::MONSTER: v *= (1.0 + 0.75 * a); break;
            case Room::REST:    v *= (1.0 - 0.75 * a); break;
            case Room::SHOP:    v *= (1.0 - 0.50 * a); break;
            case Room::EVENT:   v *= (1.0 - 0.25 * a); break;
            default: break;
        }
    }
    return v;
}

int chooseMapAction(const GameContext &gc) {
    const Map &map = *gc.map;
    t_pathAggr = 0.0;
    if (g_vPath) {
        const double pf = vStateRaw(const_cast<GameContext &>(gc));
        if (pf > -1e8)
            t_pathAggr = std::clamp((pf - bossFloorForAct(gc.act)) / 8.0, -1.0, 1.0);
    }
    static thread_local double best[15][7];
    for (int x = 0; x < 7; ++x) best[14][x] = roomValue(map.getNode(x, 14).room, 14, gc);
    for (int y = 13; y >= 0; --y) {
        for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.edgeCount == 0) { best[y][x] = -1e9; continue; }
            double bestChild = -1e18;
            for (int i = 0; i < n.edgeCount; ++i)
                bestChild = std::max(bestChild, best[y + 1][n.edges[i]]);
            best[y][x] = roomValue(n.room, y, gc) + bestChild;
        }
    }
    const int childRow = gc.curMapNodeY + 1;
    int bestX = -1;
    double bestScore = -1e18;
    auto consider = [&](int x) {
        if (best[childRow][x] > bestScore) { bestScore = best[childRow][x]; bestX = x; }
    };
    if (gc.curMapNodeY == -1) {
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) consider(n.x);
    } else {
        const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < n.edgeCount; ++i) consider(n.edges[i]);
    }
    return bestX;
}

} // namespace one_combat
