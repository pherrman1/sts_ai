#include "search_diagnostics.h"

#include "sim/search/Action.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/ScumSearchAgent2.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <vector>

namespace one_combat {

using namespace sts;

namespace {

bool g_sdiagActive = false;
std::ofstream g_sdiagFile;
std::ofstream g_sdiagFightFile;
std::mutex g_sdiagMutex;
int g_sdiagProbeEvery = 1;

struct SdiagMetrics {
    std::int64_t budget = 0;
    std::int64_t sims = 0, terminalInTree = 0, rolloutCalls = 0, leafDirectEval = 0;
    std::int64_t rolloutLeafCalls = 0, fairIllegalStoredEdge = 0;
    std::int64_t rolloutTerminated = 0, rolloutDepthCapped = 0, rolloutSkippedVNet = 0, rolloutNoLegal = 0;
    std::int64_t rolloutActions = 0, treeActions = 0, maxTreeDepth = 0;
    double simSeconds = 0;
    search::FrontierStats frontier;
    std::uint32_t bestAction = 0xFFFFFFFFu;
    double visitShare = 0, bestValue = 0, runnerUpValue = 0, valueGap = 0;
};

struct SdiagRunCtx {
    std::uint64_t seed = 0;
    int floor = 0, act = 0, room = 0, encounter = 0;
    int fightIdx = 0, decisionIdx = 0;
    SdiagMetrics cum;
    SdiagMetrics fTot;
};
thread_local SdiagRunCtx g_sdiagCtx;

static const std::vector<std::int64_t> kSdiagStages = {100, 250, 500, 1000, 3000, 10000, 30000};

static std::vector<search::Action> legalActions(const BattleContext &bc) {
    using search::Action;
    using search::ActionType;
    std::vector<Action> actions;

    if (bc.inputState == InputState::PLAYER_NORMAL) {
        if (bc.isCardPlayAllowed()) {
            for (int h = 0; h < bc.cards.cardsInHand; ++h) {
                const auto &c = bc.cards.hand[h];
                if (!c.canUseOnAnyTarget(bc)) continue;
                if (c.requiresTarget()) {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            actions.push_back(Action(ActionType::CARD, h, t));
                } else {
                    actions.push_back(Action(ActionType::CARD, h));
                }
            }
        }
        actions.push_back(Action(ActionType::END_TURN));
    } else if (bc.inputState == InputState::CARD_SELECT) {
        actions = Action::enumerateCardSelectActions(bc);
    }
    return actions;
}

static SdiagMetrics sdiagMetricsOf(const search::BattleScumSearcher2 &s) {
    assert(s.diag.consistent());
    SdiagMetrics m;
    const auto &d = s.diag;
    m.sims = d.simulations;
    m.terminalInTree = d.terminalInsideTree;
    m.rolloutCalls = d.rolloutCalls;
    m.rolloutLeafCalls = d.rolloutLeafCalls;
    m.fairIllegalStoredEdge = d.fairIllegalStoredEdge;
    m.leafDirectEval = d.leafDirectEval;
    m.rolloutTerminated = d.rolloutTerminated;
    m.rolloutDepthCapped = d.rolloutDepthCapped;
    m.rolloutSkippedVNet = d.rolloutSkippedVNet;
    m.rolloutNoLegal = d.rolloutNoLegalAction;
    m.rolloutActions = d.rolloutActions;
    m.treeActions = d.treeActions;
    m.maxTreeDepth = d.maxTreeDepth;
    m.simSeconds = d.simSeconds;
    s.collectFrontierStats(m.frontier);

    std::int64_t bestN = -1, secondN = -1, total = 0;
    std::uint32_t bestBits = 0xFFFFFFFFu, secondBits = 0xFFFFFFFFu;
    for (const auto &e : s.root.edges) {
        const std::int64_t n = e.node.simulationCount;
        total += n;
        if (n > bestN) { secondN = bestN; secondBits = bestBits; bestN = n; bestBits = e.action.bits; }
        else if (n > secondN) { secondN = n; secondBits = e.action.bits; }
    }
    if (bestN > 0) {
        m.bestAction = bestBits;
        m.visitShare = double(bestN) / total;
        const auto meanOf = [&](std::uint32_t bits, std::int64_t visits) {
            for (const auto &e : s.root.edges)
                if (e.action.bits == bits) return e.node.evaluationSum / double(visits);
            return 0.0;
        };
        m.bestValue = meanOf(bestBits, bestN);
        if (secondN > 0) {
            m.runnerUpValue = meanOf(secondBits, secondN);
            m.valueGap = m.bestValue - m.runnerUpValue;
        }
    }
    return m;
}

static SdiagMetrics sdiagWindow(const SdiagMetrics &cur, const SdiagMetrics &prev) {
    SdiagMetrics w = cur;
    w.sims = cur.sims - prev.sims;
    w.terminalInTree = cur.terminalInTree - prev.terminalInTree;
    w.rolloutCalls = cur.rolloutCalls - prev.rolloutCalls;
    w.rolloutLeafCalls = cur.rolloutLeafCalls - prev.rolloutLeafCalls;
    w.fairIllegalStoredEdge = cur.fairIllegalStoredEdge - prev.fairIllegalStoredEdge;
    w.leafDirectEval = cur.leafDirectEval - prev.leafDirectEval;
    w.rolloutTerminated = cur.rolloutTerminated - prev.rolloutTerminated;
    w.rolloutDepthCapped = cur.rolloutDepthCapped - prev.rolloutDepthCapped;
    w.rolloutSkippedVNet = cur.rolloutSkippedVNet - prev.rolloutSkippedVNet;
    w.rolloutNoLegal = cur.rolloutNoLegal - prev.rolloutNoLegal;
    w.rolloutActions = cur.rolloutActions - prev.rolloutActions;
    w.treeActions = cur.treeActions - prev.treeActions;
    w.simSeconds = cur.simSeconds - prev.simSeconds;
    w.maxTreeDepth = cur.maxTreeDepth;
    return w;
}

static void sdiagWriteRow(const char *rowtype, const BattleContext &bc,
                          const SdiagMetrics &m, int stableVsPrev, int stableVsAgent) {
    std::lock_guard<std::mutex> lk(g_sdiagMutex);
    if (!g_sdiagFile) return;
    const SdiagRunCtx &c = g_sdiagCtx;
    const double rFrac = m.sims ? double(m.rolloutCalls) / m.sims : 0;
    const double avgRoll = m.rolloutCalls ? double(m.rolloutActions) / m.rolloutCalls : 0;
    const double avgTD = m.sims ? double(m.treeActions) / m.sims : 0;
    const double tTot = m.treeActions + m.rolloutActions;
    const double tCov = tTot ? double(m.treeActions) / tTot : 0;
    const auto &fr = m.frontier;
    const double tff = (fr.terminalLeaves() + fr.unexpandedLeaves)
                           ? double(fr.terminalLeaves()) / double(fr.terminalLeaves() + fr.unexpandedLeaves) : 0;
    const double vtc = fr.frontierLeafVisits ? double(fr.terminalLeafVisits) / double(fr.frontierLeafVisits) : 0;
    const int deck = (int)(bc.cards.drawPile.size() + bc.cards.cardsInHand
                           + bc.cards.discardPile.size() + bc.cards.exhaustPile.size());
    const int nLegal = (int)legalActions(bc).size();
    g_sdiagFile << rowtype << ',' << (search::g_fairPlay ? 1 : 0) << ',' << c.seed << ',' << c.fightIdx << ',' << c.decisionIdx << ','
                << c.floor << ',' << c.act << ',' << c.room << ',' << c.encounter << ',' << bc.turn << ','
                << deck << ',' << bc.cards.cardsInHand << ',' << nLegal << ','
                << m.budget << ',' << m.sims << ',' << m.terminalInTree << ',' << m.rolloutCalls
                << ',' << m.rolloutLeafCalls << ',' << m.fairIllegalStoredEdge
                << ',' << m.leafDirectEval << ',' << m.rolloutTerminated << ',' << m.rolloutDepthCapped
                << ',' << m.rolloutSkippedVNet << ',' << m.rolloutNoLegal << ','
                << m.rolloutActions << ',' << m.treeActions << ','
                << rFrac << ',' << avgRoll << ',' << avgTD << ',' << m.maxTreeDepth << ',' << tCov << ','
                << m.simSeconds << ',' << (m.simSeconds > 0 ? m.sims / m.simSeconds : 0.0) << ','
                << fr.nodesWalked << ',' << fr.victoryLeaves << ',' << fr.defeatLeaves
                << ',' << fr.unexpandedLeaves << ',' << tff << ',' << vtc << ','
                << m.bestAction << ',' << m.visitShare << ',' << m.bestValue << ','
                << m.runnerUpValue << ',' << m.valueGap << ',' << stableVsPrev << ',' << stableVsAgent << '\n';
    g_sdiagFile.flush();
}

static void sdiagProbe(const BattleContext &bc, std::uint32_t agentBest) {
    int stageIdx = 0;
    std::uint32_t prevBest = 0xFFFFFFFFu;
    for (const std::int64_t stage : kSdiagStages) {
        search::BattleScumSearcher2 probe(bc);
        probe.searchToTotal(stage);
        SdiagMetrics m = sdiagMetricsOf(probe);
        m.budget = stage;
        const int vsPrev = stageIdx == 0 ? -1 : (m.bestAction == prevBest ? 1 : 0);
        const int vsAgent = agentBest == 0xFFFFFFFFu || m.bestAction == 0xFFFFFFFFu
                                ? -1 : (m.bestAction == agentBest ? 1 : 0);
        sdiagWriteRow("B", bc, m, vsPrev, vsAgent);
        prevBest = m.bestAction;
        ++stageIdx;
    }
}

static void sdiagAccumulate(const SdiagMetrics &win) {
    g_sdiagCtx.fTot.sims += win.sims;
    g_sdiagCtx.fTot.terminalInTree += win.terminalInTree;
    g_sdiagCtx.fTot.rolloutCalls += win.rolloutCalls;
    g_sdiagCtx.fTot.leafDirectEval += win.leafDirectEval;
    g_sdiagCtx.fTot.rolloutTerminated += win.rolloutTerminated;
    g_sdiagCtx.fTot.rolloutDepthCapped += win.rolloutDepthCapped;
    g_sdiagCtx.fTot.rolloutSkippedVNet += win.rolloutSkippedVNet;
    g_sdiagCtx.fTot.rolloutNoLegal += win.rolloutNoLegal;
    g_sdiagCtx.fTot.rolloutActions += win.rolloutActions;
    g_sdiagCtx.fTot.treeActions += win.treeActions;
}

static void sdiagOnSearchComplete(const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
    ++g_sdiagCtx.decisionIdx;
    SdiagMetrics cur = sdiagMetricsOf(searcher);
    SdiagMetrics win;
    if (search::g_fairPlay) win = cur;
    else {
        win = sdiagWindow(cur, g_sdiagCtx.cum);
        g_sdiagCtx.cum = cur;
    }
    g_sdiagCtx.cum = cur;
    sdiagAccumulate(win);
    win.budget = win.sims;
    sdiagWriteRow("A", bc, win, -1, -1);
    if (g_sdiagProbeEvery > 0 && (g_sdiagCtx.decisionIdx % g_sdiagProbeEvery) == 0)
        sdiagProbe(bc, cur.bestAction);
}

static SdiagMetrics sdiagMetricsOf3(const search::BattleScumSearcher3 &s) {
    SdiagMetrics m;
    const auto &d = s.diag;
    m.sims = d.simulations;
    m.terminalInTree = d.terminalInsideTree;
    m.rolloutCalls = d.rolloutCalls;
    m.rolloutLeafCalls = d.rolloutLeafCalls;
    m.fairIllegalStoredEdge = d.fairIllegalStoredEdge;
    m.leafDirectEval = d.leafDirectEval;
    m.rolloutTerminated = d.rolloutTerminated;
    m.rolloutDepthCapped = d.rolloutDepthCapped;
    m.rolloutSkippedVNet = d.rolloutSkippedVNet;
    m.rolloutNoLegal = d.rolloutNoLegalAction;
    m.rolloutActions = d.rolloutActions;
    m.treeActions = d.treeActions;
    m.maxTreeDepth = d.maxTreeDepth;
    m.simSeconds = d.simSeconds;

    std::int64_t bestN = -1, secondN = -1, total = 0;
    std::uint32_t bestBits = 0xFFFFFFFFu, secondBits = 0xFFFFFFFFu;
    for (const auto &e : s.root.edges) {
        const std::int64_t n = e.child.simulationCount;
        total += n;
        if (n > bestN) { secondN = bestN; secondBits = bestBits; bestN = n; bestBits = e.action.bits; }
        else if (n > secondN) { secondN = n; secondBits = e.action.bits; }
    }
    if (bestN > 0) {
        m.bestAction = bestBits;
        m.visitShare = double(bestN) / total;
        const auto meanOf = [&](std::uint32_t bits, std::int64_t visits) {
            for (const auto &e : s.root.edges)
                if (e.action.bits == bits) return e.child.evaluationSum / double(visits);
            return 0.0;
        };
        m.bestValue = meanOf(bestBits, bestN);
        if (secondN > 0) {
            m.runnerUpValue = meanOf(secondBits, secondN);
            m.valueGap = m.bestValue - m.runnerUpValue;
        }
    }
    return m;
}

static void sdiagOnSearchComplete3(const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    ++g_sdiagCtx.decisionIdx;
    SdiagMetrics cur = sdiagMetricsOf3(s3);
    SdiagMetrics win;
    if (search::g_fairPlay) win = cur;
    else {
        win = sdiagWindow(cur, g_sdiagCtx.cum);
        g_sdiagCtx.cum = cur;
    }
    g_sdiagCtx.cum = cur;
    sdiagAccumulate(win);
    win.budget = win.sims;
    sdiagWriteRow("A", bc, win, -1, -1);
}

static void sdiagFightRow(const BattleContext &bc) {
    std::lock_guard<std::mutex> lk(g_sdiagMutex);
    if (!g_sdiagFightFile) return;
    const SdiagRunCtx &c = g_sdiagCtx;
    const auto &t = c.fTot;
    const double rFrac = t.sims ? double(t.rolloutCalls) / t.sims : 0;
    const double avgRoll = t.rolloutCalls ? double(t.rolloutActions) / t.rolloutCalls : 0;
    const double avgTD = t.sims ? double(t.treeActions) / t.sims : 0;
    const double tTot = t.treeActions + t.rolloutActions;
    const double tCov = tTot ? double(t.treeActions) / tTot : 0;
    g_sdiagFightFile << c.seed << ',' << c.fightIdx << ',' << c.floor << ',' << c.act << ','
                << c.room << ',' << c.encounter << ','
                << (bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0) << ',' << (bc.turn + 1) << ','
                << bc.player.curHp << ',' << t.sims << ',' << t.terminalInTree << ','
                << t.rolloutCalls << ',' << t.leafDirectEval << ',' << t.rolloutActions << ','
                << t.treeActions << ',' << rFrac << ',' << avgRoll << ',' << avgTD << ',' << tCov << '\n';
    g_sdiagFightFile.flush();
}

} // namespace

bool startSearchDiagnostics(const std::string &out, int probeEvery) {
    if (search::g_useSearcher3 && probeEvery > 0) {
        std::cerr << "searchdiag: Searcher3 supports rowtype A only (no S2 probe stages); forcing probeEvery=0\n";
        probeEvery = 0;
    }
    g_sdiagProbeEvery = probeEvery;
    g_sdiagActive = true;
    g_sdiagFile.open(out, std::ios::trunc);
    if (!g_sdiagFile) {
        std::cerr << "searchdiag: cannot open " << out << "\n";
        g_sdiagActive = false;
        return false;
    }
    const std::string fightOut = out + ".fights.csv";
    g_sdiagFightFile.open(fightOut, std::ios::trunc);
    if (!g_sdiagFightFile) {
        std::cerr << "searchdiag: cannot open " << fightOut << "\n";
        g_sdiagFile.close();
        g_sdiagActive = false;
        return false;
    }
    g_sdiagFile << "rowtype,fair,seed,fightIdx,decIdx,floor,act,room,encounter,turn,deckSize,handSize,"
                   "nLegalActions,budget,sims,terminalInTree,rolloutCalls,rolloutLeafCalls,"
                   "fairIllegalStoredEdge,leafDirectEval,"
                   "rolloutTerminated,rolloutDepthCapped,rolloutSkippedVNet,rolloutNoLegal,"
                   "rolloutActions,treeActions,rolloutFraction,avgRolloutLen,avgTreeDepth,maxTreeDepth,"
                   "treeCoverage,simSeconds,simsPerSec,"
                   "nodesWalked,victoryLeaves,defeatLeaves,unexpandedLeaves,terminalFrontierFraction,"
                   "visitedTerminalCoverage,bestAction,visitShare,bestValue,runnerUpValue,valueGap,"
                   "stableVsPrev,stableVsAgent\n";
    g_sdiagFile.flush();
    g_sdiagFightFile << "seed,fightIdx,floor,act,room,encounter,won,turns,hpEnd,"
                        "sims,terminalInTree,rolloutCalls,leafDirectEval,rolloutActions,treeActions,"
                        "rolloutFraction,avgRolloutLen,avgTreeDepth,treeCoverage\n";
    g_sdiagFightFile.flush();
    return true;
}

void stopSearchDiagnostics() {
    g_sdiagFile.close();
    g_sdiagFightFile.close();
    g_sdiagActive = false;
}

bool searchDiagnosticsActive() { return g_sdiagActive; }

void beginSearchDiagnosticFight(std::uint64_t seed, int floor, int act, int room,
                                int encounter, int fightIdx) {
    if (!g_sdiagActive) return;
    g_sdiagCtx = SdiagRunCtx{};
    g_sdiagCtx.seed = seed;
    g_sdiagCtx.floor = floor;
    g_sdiagCtx.act = act;
    g_sdiagCtx.room = room;
    g_sdiagCtx.encounter = encounter;
    g_sdiagCtx.fightIdx = fightIdx;
}

void endSearchDiagnosticFight(const BattleContext &bc) {
    if (g_sdiagActive) sdiagFightRow(bc);
}

void installSearchDiagnosticThreadHooks() {
    if (!g_sdiagActive) return;
    if (search::g_useSearcher3)
        search::g_onSearchComplete3 = sdiagOnSearchComplete3;
    else
        search::g_onSearchComplete = sdiagOnSearchComplete;
}

void clearSearchDiagnosticThreadHooks() {
    search::g_onSearchComplete = nullptr;
    search::g_onSearchComplete3 = nullptr;
}

} // namespace one_combat
