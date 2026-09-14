#include "ooc_mcts_adapter.h"
#include "combat_transition_runtime.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <time.h>
#include "../ooc_strategic_tok_net.h"
#include "run_driver.h"
#include "combat/BattleContext.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/BattleScumSearcher2.h"
#include "../ooc_test_state.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <type_traits>

namespace one_combat {
static_assert(!std::is_constructible_v<OocGameContextModel, const GameContext &>,
              "OOC MCTS roots must require explicit PathHistory");
namespace {
GameContext detachedCopy(const GameContext &parent) {
    GameContext child = parent;
    if (parent.map) child.map = std::make_shared<sts::Map>(*parent.map);
    return child;
}
void require(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
void applySampledCombatExit(GameContext &gc, const CombatRuntimeSample &sample) {
    const bool escape = sample.outcome == CombatRuntimeSample::Outcome::ESCAPE;
    if ((sample.outcome != CombatRuntimeSample::Outcome::VICTORY && !escape)
        || sample.rawPost.smokeBombUsed != escape
        || (escape && sts::isBossEncounter(gc.info.encounter)))
        throw std::runtime_error("combat outcome disagrees with RAW smokeBombUsed");
    applyCombatTransitionState(gc, sample.rawPost);
    gc.regainControl();
}
}
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature) {
    if (!std::isfinite(temperature) || temperature <= 0)
        throw std::invalid_argument("OOC MCTS invalid policy temperature");
    for (double l : logits) if (!std::isfinite(l)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    if (logits.empty()) return {};
    double largest = *std::max_element(logits.begin(), logits.end());
    std::vector<double> weights;
    for (double l : logits) {
        double w = std::exp((l - largest) / temperature);
        if (!std::isfinite(w) || w < 0) throw std::runtime_error("OOC MCTS invalid policy weight");
        weights.push_back(w);
    }
    return weights;
}
OocGameContextModel::OocGameContextModel(const GameContext &gc, const PathHistory &path,
    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts)
    : combatSampler(std::move(sampler)), options(std::move(opts)) {
    if (!std::isfinite(options.priorTemperature) || options.priorTemperature <= 0 || (options.leafCombats != 0 && options.leafCombats != 1 && options.leafCombats != 3))
        throw std::invalid_argument("OOC MCTS invalid adapter options");
    if (!winNetOk()) throw std::runtime_error("OOC MCTS requires native v_win");
    if (!g_oocStrategicTokNet.ok) throw std::runtime_error("OOC MCTS requires native V4 policy");
    auto history = path;
    history.update(gc);
    states.push_back({detachedCopy(gc), history, {}});
}
const GameContext &OocGameContextModel::state(sts::search::OocStateId id) const { return states.at(id).gc; }
const PathHistory &OocGameContextModel::pathHistory(sts::search::OocStateId id) const { return states.at(id).path; }
std::optional<double> OocGameContextModel::terminalValue(sts::search::OocStateId id) const {
    switch (state(id).outcome) {
        case sts::GameOutcome::PLAYER_LOSS: return 0;
        case sts::GameOutcome::PLAYER_VICTORY: return 1;
        case sts::GameOutcome::UNDECIDED: return std::nullopt;
    }
    throw std::runtime_error("OOC MCTS invalid outcome");
}
OocGameContextModel::Metadata &OocGameContextModel::mutableMetadata(sts::search::OocStateId id) const {
    const auto &snapshot = states.at(id);
    if (!snapshot.metadata) {
        Metadata value;
        if (v4DecisionSupported(snapshot.gc)) {
            value.candidates = v4CandidateActions(snapshot.gc);
            value.boundary = value.candidates.empty();
            std::set<std::uint32_t> ids;
            for (auto action : value.candidates)
                if (!ids.insert(action.bits).second) value.boundary = true;
        }
        value.edges.resize(value.candidates.size());
        snapshot.metadata = std::move(value);
        ++continuation_.metadataBuilds;
    }
    return *snapshot.metadata;
}
const OocGameContextModel::Metadata &OocGameContextModel::metadata(sts::search::OocStateId id) const {
    return mutableMetadata(id);
}
bool OocGameContextModel::isLeafBoundary(sts::search::OocStateId id) const {
    return metadata(id).boundary;
}
std::optional<sts::search::OocActionId> OocGameContextModel::soleLegalAction(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) return std::nullopt;
    const auto &actions = metadata(id).candidates;
    if (actions.size()==1 && actions.front().isValidAction(state(id))) return actions.front().bits;
    return std::nullopt;
}
std::vector<double> OocGameContextModel::policyLogits(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    if (!g_oocStrategicTokNet.ok) throw std::runtime_error("OOC MCTS V4 unavailable");
    const auto &snapshot = states.at(id);
    const auto &gc = snapshot.gc;
    auto &cached = mutableMetadata(id);
    if (cached.logits) return *cached.logits;
    const auto &actions = cached.candidates;
    ++continuation_.priorBuilds;
    const TokState ts = buildTokState(gc, snapshot.path);
    const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
        ts.nRl, ts.rl, ts.nPt, ts.pt);
    std::vector<double> logits;
    for (auto a : actions) {
        int type, c1, c2, c3, d1, d2, d3, et, ei; float price;
        strategicCands(gc, a, type, c1, c2, c3, d1, d2, d3);
        tokEntity(gc, a, et, ei, price);
        const int cats[6] = {c1,c2,c3,d1,d2,d3};
        const float entity[4] = {float(et==0),float(et==1),float(et==2),float(et==3)};
        const double logit = g_oocStrategicTokNet.predictPolicyLogit(prepared, a.bits, cats, type, int(gc.screenState), entity, ei, price);
        if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
        logits.push_back(logit);
    }
    cached.logits = logits;
    return logits;
}
std::vector<sts::search::OocPlannerAction> OocGameContextModel::legalActions(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    auto &cached = mutableMetadata(id);
    if (cached.priors) return *cached.priors;
    const auto &actions = cached.candidates;
    auto weights = options.uniformPrior ? std::vector<double>(actions.size(), 1.0)
                                      : oocPolicyWeights(policyLogits(id), options.priorTemperature);
    std::vector<sts::search::OocPlannerAction> result;
    result.reserve(actions.size());
    for (std::size_t i=0; i<actions.size(); ++i)
        result.push_back({actions[i].bits, weights[i]});
    cached.priors = result;
    return result;
}
sts::search::OocStateId OocGameContextModel::sampleSuccessor(sts::search::OocStateId id,
    sts::search::OocActionId action, std::mt19937_64 &rng) {
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS transition from leaf");
    auto &cached = mutableMetadata(id);
    const auto &actions = cached.candidates;
    auto it = std::find_if(actions.begin(), actions.end(), [&](auto a) { return a.bits == action; });
    if (it == actions.end()) throw std::runtime_error("OOC MCTS illegal action ID");
    auto &edge = cached.edges.at(it - actions.begin());
    if (edge.deterministic) return *edge.deterministic;
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    it->execute(child.gc);
    child.path.update(child.gc);
    const bool enteredCombat = child.gc.screenState == sts::ScreenState::BATTLE;
    if (enteredCombat && combatSampler && !edge.combat) {
        const auto input = captureCombatPredictorInput(child.gc, child.gc.info.encounter,
                                                       potionKeepValue(child.gc));
        edge.combat = combatSampler->prepare(child.gc, input);
        ++continuation_.preparedCombats;
    }
    if (enteredCombat) ++continuation_.combatEdgeSamples;
    if (options.checkpointLeaves && enteredCombat) resolveCombat(child, rng, edge.combat.get());
    else if (combatSampler && enteredCombat) {
        if (edge.combat->support().supported) {
            ++combatSamples_;
            const auto sampled = edge.combat->sample(rng);
            switch (sampled.outcome) {
                case CombatRuntimeSample::Outcome::UNSUPPORTED: break;
                case CombatRuntimeSample::Outcome::DEATH:
                    child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                    break;
                case CombatRuntimeSample::Outcome::VICTORY:
                case CombatRuntimeSample::Outcome::ESCAPE:
                    applySampledCombatExit(child.gc, sampled);
                    // Live runs record the entered room before combat and the
                    // continuation on the next loop, including act changes.
                    child.path.update(child.gc);
                    break;
            }
        }
    }
    if (options.checkpointLeaves && !enteredCombat) edge.deterministic = states.size();
    states.push_back(std::move(child));
    return states.size()-1;
}
double OocGameContextModel::leafValue(sts::search::OocStateId id) const {
    if (options.checkpointLeaves && !terminalValue(id)
        && state(id).screenState != sts::ScreenState::MAP_SCREEN)
        throw std::runtime_error("OOC MCTS v_win requires a resolved map checkpoint");
    if (auto terminal = terminalValue(id)) return *terminal;
    if (options.checkpointLeaves && options.constantLeaf) return 0.5;
    // Native-only seam; its implementation has no server fallback branch.
    auto gc = detachedCopy(state(id));
    struct PathScope {
        const PathHistory *saved = t_curPath;
        explicit PathScope(const PathHistory &path) { t_curPath = &path; }
        ~PathScope() { t_curPath = saved; }
    } scope(states.at(id).path);
    return vStateWinNative(gc);
}
bool OocGameContextModel::isDeterministicTransition(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    const auto &cached = metadata(id);
    const auto it = std::find_if(cached.candidates.begin(), cached.candidates.end(),
        [&](auto candidate) { return candidate.bits == action; });
    return it != cached.candidates.end() && cached.edges.at(it-cached.candidates.begin()).deterministic.has_value();
}
void OocGameContextModel::resolveCombat(Snapshot &child, std::mt19937_64 &rng,
    const PreparedCombatTransition *prepared) {
    ++continuation_.imaginedCombats;
    const int battleAct = child.gc.act;
    const auto battleRoom = child.gc.curRoom;
    bool victory = false;
    const auto input = prepared ? CombatPredictorInputV1{}
        : captureCombatPredictorInput(child.gc, child.gc.info.encounter, potionKeepValue(child.gc));
    const auto support = prepared ? prepared->support()
        : combatSampler ? combatSampler->support(child.gc, input)
                        : CombatRuntimeSupport{false, "missing_sampler"};
    auto reason = support.reason;
    if (support.supported) {
        const auto sampled = prepared ? prepared->sample(rng) : combatSampler->sample(child.gc, input, rng);
        if (sampled.outcome != CombatRuntimeSample::Outcome::UNSUPPORTED) {
            ++combatSamples_;
            if (sampled.outcome == CombatRuntimeSample::Outcome::DEATH) {
                child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                return;
            }
            applySampledCombatExit(child.gc, sampled);
            victory = true;
        } else reason = "sample_returned_unsupported";
    }
    if (!victory) {
        ++continuation_.unsupportedCombats;
        ++continuation_.supportReasons[reason.empty() ? "unspecified" : reason];
        throw sts::search::OocSearchUnsupported(reason.empty() ? "unspecified" : reason);
    }
    if (victory && g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == sts::Room::BOSS)
        child.gc.outcome = sts::GameOutcome::PLAYER_VICTORY;
    child.path.update(child.gc);
}
namespace {
// Preserve observers and run-local policy bookkeeping across detached work.
struct ImaginedScope {
    const PathHistory *path = t_curPath;
    std::string rows = std::move(t_oocStrategicTraceRows);
    int decision = t_oocStrategicTraceDecision;
    bool shop = t_shopV, tok = t_tokCheckPending;
    int probeDecision = t_actFightProbeDecisionIdx, probeAction = t_actFightProbeActionIdx,
        probeFuture = t_actFightProbeFutureIdx;
    decltype(sts::search::g_onGameActionExecute) observer = std::move(sts::search::g_onGameActionExecute);
    decltype(sts::search::g_onCombatDecision) combatObserver=std::move(sts::search::g_onCombatDecision);
    decltype(sts::search::g_onSearchComplete) searchObserver=std::move(sts::search::g_onSearchComplete);
    decltype(sts::search::g_onSearchComplete3) searchObserver3=std::move(sts::search::g_onSearchComplete3);
    decltype(sts::g_onBattleExitPersistent) exitObserver=std::move(sts::g_onBattleExitPersistent);
    sts::search::SilverLiveDiagnostics silver = std::move(sts::search::g_silverLiveDiagnostics);
    bool disallowed = sts::search::g_disallowImaginedCombat;
    double potion = sts::search::g_potionKeepValue;
    ImaginedScope() {
        sts::search::g_disallowImaginedCombat=true;
        t_tokCheckPending=false; sts::search::g_onGameActionExecute={};
        sts::search::g_onCombatDecision={}; sts::search::g_onSearchComplete={};
        sts::search::g_onSearchComplete3={}; sts::g_onBattleExitPersistent={};
    }
    ~ImaginedScope() {
        t_curPath=path; t_oocStrategicTraceRows=std::move(rows); t_oocStrategicTraceDecision=decision;
        t_shopV=shop; t_tokCheckPending=tok;
        t_actFightProbeDecisionIdx=probeDecision; t_actFightProbeActionIdx=probeAction; t_actFightProbeFutureIdx=probeFuture;
        sts::search::g_onGameActionExecute=std::move(observer);
        sts::search::g_onCombatDecision=std::move(combatObserver);
        sts::search::g_onSearchComplete=std::move(searchObserver);
        sts::search::g_onSearchComplete3=std::move(searchObserver3);
        sts::g_onBattleExitPersistent=std::move(exitObserver);
        sts::search::g_silverLiveDiagnostics=std::move(silver);
        sts::search::g_disallowImaginedCombat=disallowed; sts::search::g_potionKeepValue=potion;
    }
};

template<class Checkpoint, class Step>
double boundedContinuation(int maxSteps, Checkpoint checkpoint, Step advance) {
    for (int step=0; step<maxSteps; ++step) {
        if (const auto value=checkpoint()) return *value;
        advance();
    }
    // The last permitted transition may itself reach an exact terminal or
    // resolved checkpoint. Exhaustion applies only to still-pending work.
    if (const auto value=checkpoint()) return *value;
    throw sts::search::OocSearchUnsupported("continuation_step_limit_" + std::to_string(maxSteps));
}

}
double OocGameContextModel::evaluateLeaf(sts::search::OocStateId id, std::mt19937_64 &rng) {
    if (!options.checkpointLeaves) return leafValue(id);
    ImaginedScope scope;
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    t_curPath=&child.path;
    if (child.gc.screenState == sts::ScreenState::BATTLE) ++continuation_.battleLeaves;
    else if (child.gc.screenState == sts::ScreenState::MAP_SCREEN) ++continuation_.mapLeaves;
    else ++continuation_.pendingLeaves;
    ScumSearchAgent2 agent; agent.simulationCountBase=10000; agent.rng.seed(rng());
    const int maxSteps = options.leafCombats ? 1024 : 256;
    unsigned additionalCombats = 0;
    const auto checkpoint = [&]() -> std::optional<double> {
        child.path.update(child.gc);
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) return 0;
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) return 1;
        if (child.gc.screenState == sts::ScreenState::MAP_SCREEN && additionalCombats >= options.leafCombats)
            return options.constantLeaf ? 0.5 : vStateWinNative(child.gc);
        return std::nullopt;
    };
    return boundedContinuation(maxSteps,checkpoint,[&] {
        ++continuation_.projectionSteps;
        if (child.gc.screenState == sts::ScreenState::BATTLE) { resolveCombat(child,rng); ++additionalCombats; }
        else {
            bool applied = false;
            if (options.uniformLeafPolicy && v4DecisionSupported(child.gc)) {
                const auto actions = v4CandidateActions(child.gc);
                std::set<std::uint32_t> ids;
                bool unique = !actions.empty();
                for (auto action : actions) if (!ids.insert(action.bits).second) unique = false;
                if (unique) {
                    const auto selected = std::uniform_int_distribution<std::size_t>(0, actions.size()-1)(rng);
                    actions[selected].execute(child.gc); applied = true;
                }
            }
            if (!applied) runFullRunOocPolicyStep(child.gc,agent,false,true);
        }
    });
}

}

namespace one_combat {

namespace {
bool liveEnabled = false;
std::uint64_t liveSimulations = 512;
sts::search::OocMctsConfig liveConfig;
OocAdapterOptions liveOptions{true};
std::shared_ptr<const CombatTransitionSampler> liveSampler;
std::string liveTrace, liveRootLockTrace;
std::mutex liveTraceMutex;
std::uint64_t splitMix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
// Parsing is strict: no whitespace, trailing text, nonfinite or out-of-range knobs.
void applyLiveControl(const std::string &key, const std::string &value,
                      sts::search::OocMctsConfig &config, OocAdapterOptions &opts) {
    const auto invalid = [&] { throw std::runtime_error(key + " invalid value: " + value); };
    const auto choice = [&](const char *a, const char *b) {
        if (value == a) return false;
        if (value == b) return true;
        invalid(); return false;
    };
    const auto number = [&] {
        if (value.empty() || value.find_first_not_of("0123456789.+-eE") != std::string::npos) invalid();
        std::size_t end = 0; double x = 0;
        try { x = std::stod(value, &end); } catch (...) { invalid(); }
        if (end != value.size() || !std::isfinite(x)) invalid();
        return x;
    };
    const auto integer = [&] {
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos) invalid();
        unsigned long long x = 0;
        try { x = std::stoull(value); } catch (...) { invalid(); }
        return x;
    };
    if (key == "STS_OOC_MCTS_PRIOR") opts.uniformPrior = choice("policy", "uniform");
    else if (key == "STS_OOC_MCTS_LEAF_VALUE") opts.constantLeaf = choice("native", "constant");
    else if (key == "STS_OOC_MCTS_LEAF_POLICY") opts.uniformLeafPolicy = choice("v4", "uniform");
    else if (key == "STS_OOC_MCTS_EARLY_STOP") config.allowUnqualifiedRootStop = choice("0", "1");
    else if (key == "STS_OOC_MCTS_ROOT_SELECTION") config.selectByMeanQ = choice("visits", "q");
    else if (key == "STS_OOC_MCTS_TEMPERATURE") { const double x = number(); if (x <= 0) invalid(); opts.priorTemperature = x; }
    else if (key == "STS_OOC_MCTS_CPUCT") { const double x = number(); if (x < 0) invalid(); config.cPuct = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_K") { const double x = number(); if (x <= 0) invalid(); config.wideningK = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_ALPHA") { const double x = number(); if (x <= 0 || x >= 1) invalid(); config.wideningAlpha = x; }
    else if (key == "STS_OOC_MCTS_MAX_DEPTH") { const auto x = integer(); if (!x || x > 32) invalid(); config.maxDepth = x; }
    else if (key == "STS_OOC_MCTS_LEAF_COMBATS") { const auto x = integer(); if (x != 0 && x != 1 && x != 3) invalid(); opts.leafCombats = x; }
    else invalid();
}
const char *const liveControlKeys[] = {
    "STS_OOC_MCTS_EARLY_STOP", "STS_OOC_MCTS_PRIOR", "STS_OOC_MCTS_TEMPERATURE", "STS_OOC_MCTS_CPUCT",
    "STS_OOC_MCTS_WIDEN_K", "STS_OOC_MCTS_WIDEN_ALPHA", "STS_OOC_MCTS_MAX_DEPTH",
    "STS_OOC_MCTS_ROOT_SELECTION", "STS_OOC_MCTS_LEAF_VALUE",
    "STS_OOC_MCTS_LEAF_COMBATS", "STS_OOC_MCTS_LEAF_POLICY"
};
void recordSearchAbort(const sts::search::OocMctsResult &result, OocContinuationMetrics &continuation) {
    if (!result.aborted) return;
    if (result.abortReason.rfind("continuation_step_limit_",0) == 0) {
        ++continuation.continuationLimitAborts;
        ++continuation.continuationReasons[result.abortReason];
    } else if (!continuation.unsupportedCombats) {
        // A continuation policy attempted a forbidden native combat before resolveCombat.
        ++continuation.imaginedCombats; ++continuation.unsupportedCombats;
        ++continuation.supportReasons[result.abortReason];
    }
}
double threadCpuSeconds() {
    timespec t{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t) != 0)
        throw std::runtime_error("OOC MCTS thread CPU clock unavailable");
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}
}
bool liveOocMctsEnabled() { return liveEnabled; }
std::uint64_t oocMctsSearchSeed(std::uint64_t seed, std::uint64_t index) {
    return splitMix64(seed ^ splitMix64(index));
}
void configureLiveOocMcts() {
    const char *enabled = std::getenv("STS_OOC_MCTS");
    if (enabled && std::string(enabled) != "0" && std::string(enabled) != "1")
        throw std::runtime_error("STS_OOC_MCTS must be 0 or 1");
    liveEnabled = enabled && std::string(enabled) == "1";
    if (const char *trace = std::getenv("STS_OOC_MCTS_TRACE")) liveTrace = trace;
    if (!liveTrace.empty()) {
        std::ofstream out(liveTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot open output");
    }
    liveRootLockTrace.clear();
    liveSimulations = 512; liveConfig = {}; liveOptions = {true};
    if (!liveEnabled) return;
    if (!g_oocStrategicTokNet.ok) throw std::runtime_error("STS_OOC_MCTS requires native V4 policy");
    if (!winNetOk()) throw std::runtime_error("STS_OOC_MCTS requires native v_win");
    // Legacy win loading may retry the default. An explicit failed request must
    // remain a startup failure even if that retry succeeded.
    if (const char *requested = std::getenv("STS_WIN_NET")) {
        CompactTreeNet explicitWin;
        const std::string path = std::string(requested) == "1" ? "models/v_win_trees.txt" : requested;
        if (!explicitWin.load(path, richIdxMap()))
            throw std::runtime_error("STS_OOC_MCTS explicit STS_WIN_NET failed to load");
    }
    if (const char *sims = std::getenv("STS_OOC_MCTS_SIMS")) {
        const std::string value(sims);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("STS_OOC_MCTS_SIMS must be a positive integer");
        liveSimulations = std::stoull(value);
        if (!liveSimulations) throw std::runtime_error("STS_OOC_MCTS_SIMS must be positive");
    }
    liveConfig = {}; liveOptions = {true};
    liveConfig.allowUnqualifiedRootStop = true; // May skip later aborts; provider guarantee remains false.
    for (const char *key : liveControlKeys)
        if (const char *value = std::getenv(key)) applyLiveControl(key, value, liveConfig, liveOptions);
    if (const char *trace = std::getenv("STS_OOC_MCTS_ROOT_LOCK_TRACE")) liveRootLockTrace = trace;
    liveConfig.observeRootLock = !liveRootLockTrace.empty();
    if (liveConfig.observeRootLock) {
        std::ofstream out(liveRootLockTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE cannot open output");
        std::cout << "[ooc-root-lock-observer ON full_budget=1 hypothetical_only=1]\n";
    }
    const char *artifact = std::getenv("STS_OOC_MCTS_COMBAT_MODEL");
    if (!artifact || !*artifact) throw std::runtime_error("STS_OOC_MCTS requires STS_OOC_MCTS_COMBAT_MODEL");
    liveSampler = std::make_shared<NativeCombatTransitionSampler>(artifact);
    const auto precision = std::cout.precision();
    std::cout << std::setprecision(17) << "[live OOC MCTS ON sims=" << liveSimulations
        << " combat_model=" << artifact << " prior=" << (liveOptions.uniformPrior ? "uniform" : "policy")
        << " temperature=" << liveOptions.priorTemperature << " cpuct=" << liveConfig.cPuct
        << " widen_k=" << liveConfig.wideningK << " widen_alpha=" << liveConfig.wideningAlpha
        << " max_depth=" << liveConfig.maxDepth << " root_selection=" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << " early_stop=" << liveConfig.allowUnqualifiedRootStop
        << " leaf_value=" << (liveOptions.constantLeaf ? "constant" : "native")
        << " leaf_combats=" << liveOptions.leafCombats << " leaf_policy=" << (liveOptions.uniformLeafPolicy ? "uniform" : "v4")
        << "]\n";
    std::cout << "[ooc-mcts-config] {\"prior\":\"" << (liveOptions.uniformPrior ? "uniform" : "policy")
        << "\",\"temperature\":" << liveOptions.priorTemperature << ",\"cPuct\":" << liveConfig.cPuct
        << ",\"wideningK\":" << liveConfig.wideningK << ",\"wideningAlpha\":" << liveConfig.wideningAlpha
        << ",\"maxDepth\":" << liveConfig.maxDepth << ",\"rootSelection\":\"" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << "\",\"earlyStop\":" << (liveConfig.allowUnqualifiedRootStop ? "true" : "false")
        << ",\"leafValue\":\"" << (liveOptions.constantLeaf ? "constant" : "native")
        << "\",\"leafCombats\":" << liveOptions.leafCombats << ",\"leafPolicy\":\"" << (liveOptions.uniformLeafPolicy ? "uniform" : "v4")
        << "\",\"simulations\":" << liveSimulations << "}\n";
    std::cout.precision(precision);
}
namespace {
sts::search::OocMctsResult searchWithSoleRootShortcut(sts::search::OocGenerativeModel &model,
    const sts::search::OocMctsConfig &config, std::optional<sts::search::OocActionId> soleAction,
    std::uint64_t simulations) {
    if (!config.observeRootLock && config.maxDepth && soleAction && model.searchGuaranteedNonAborting()) {
        sts::search::OocMctsResult result;
        result.selectedAction = soleAction;
        result.metrics.trivialRootBypasses = 1;
        return result;
    }
    // An abort hands control to the ordered fallback policy, which may consume
    // agent RNG even when the primitive candidate set contains just one action.
    return sts::search::OocMctsPlanner(config).search(model, 0, simulations);
}
}
sts::search::OocMctsResult selectOocMctsAction(const GameContext &gc, const PathHistory &path,
    std::uint64_t seed, std::uint64_t index, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler> sampler, std::uint64_t &samples,
    OocContinuationMetrics *continuation) {
    ImaginedScope scope;
    OocGameContextModel model(gc, path, std::move(sampler), liveOptions);
    samples = 0;
    if (model.terminalValue(0) || model.isLeafBoundary(0)) return {};
    auto config = liveConfig;
    config.seed = oocMctsSearchSeed(seed, index);
    if (!simulations) throw std::invalid_argument("OOC MCTS requires simulations > 0");
    const auto result = searchWithSoleRootShortcut(model, config, model.soleLegalAction(0), simulations);
    if (!result.selectedAction && !result.aborted) throw std::runtime_error("live OOC MCTS missing selected root action");
    if (config.observeRootLock) {
        const auto &m = result.metrics;
        const bool completed = !result.aborted && m.simulations == simulations;
        if (completed && result.hypotheticalLockedAction
            && result.hypotheticalLockedAction != result.selectedAction)
            throw std::runtime_error("OOC hypothetical lock disagrees with full-budget winner");
        const nlohmann::json row = {
            {"seed",seed},{"decisionIndex",index},{"floor",gc.floorNum},{"screen",int(gc.screenState)},
            {"requestedSimulations",simulations},{"completedSimulations",m.simulations},
            {"simulationAttempts",m.simulationAttempts},{"fullBudgetCompleted",completed},
            {"aborted",result.aborted},{"abortReason",result.abortReason},
            {"hypotheticalLockSimulation",m.hypotheticalLockSimulation},
            {"hypotheticalRemainingSimulations",m.hypotheticalRemainingSimulations},
            {"hypotheticalTailWallSeconds",m.hypotheticalTailWallSeconds},
            {"hypotheticalLockedAction",result.hypotheticalLockedAction
                ? nlohmann::json(*result.hypotheticalLockedAction) : nlohmann::json(nullptr)},
            {"selectedAction",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
            {"searchGuaranteedNonAborting",model.searchGuaranteedNonAborting()},
            {"earlyStopLockedRoot",m.earlyStopLockedRoot},{"savedSimulations",m.savedSimulations}};
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveRootLockTrace,std::ios::app);
        if (!out || !(out << row.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE write failed");
    }
    samples = model.combatSamples();
    if (continuation) {
        *continuation = model.continuationMetrics();
        recordSearchAbort(result,*continuation);
    }
    return result;
}
bool oocMctsPolicyStep(GameContext &gc, const PathHistory &path, std::uint64_t seed,
    std::uint64_t index, LiveOocMctsMetrics &metrics) {
    ++metrics.decisions;
    if (!liveEnabled) return false;
    const auto wallStart = std::chrono::steady_clock::now();
    const double cpuStart = threadCpuSeconds();
    std::uint64_t samples = 0;
    OocContinuationMetrics continuation;
    const auto result = selectOocMctsAction(gc, path, seed, index, liveSimulations, liveSampler, samples, &continuation);
    metrics.wallSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now()-wallStart).count();
    metrics.cpuSeconds += threadCpuSeconds()-cpuStart;
    metrics.combatSamples += samples;
    auto &c=metrics.continuation;
    c.imaginedCombats+=continuation.imaginedCombats; c.unsupportedCombats+=continuation.unsupportedCombats;
    c.pendingLeaves+=continuation.pendingLeaves; c.battleLeaves+=continuation.battleLeaves;
    c.mapLeaves+=continuation.mapLeaves; c.projectionSteps+=continuation.projectionSteps;
    c.continuationLimitAborts+=continuation.continuationLimitAborts;
    c.metadataBuilds+=continuation.metadataBuilds; c.priorBuilds+=continuation.priorBuilds;
    c.preparedCombats+=continuation.preparedCombats; c.combatEdgeSamples+=continuation.combatEdgeSamples;
    for (auto &[reason,count] : continuation.continuationReasons) c.continuationReasons[reason]+=count;
    for (auto &[reason,count] : continuation.supportReasons) c.supportReasons[reason]+=count;
    auto &m = metrics.search;
    m.outcomeParticles+=result.metrics.outcomeParticles; m.decisionNodes+=result.metrics.decisionNodes;
    m.chanceNodes+=result.metrics.chanceNodes; m.particleRevisits+=result.metrics.particleRevisits;
    m.deterministicRevisits+=result.metrics.deterministicRevisits; m.depthSum+=result.metrics.depthSum;
    m.trivialRootBypasses += result.metrics.trivialRootBypasses;
    m.earlyStopLockedRoot += result.metrics.earlyStopLockedRoot;
    m.savedSimulations += result.metrics.savedSimulations;
    m.simulations += result.metrics.simulations;
    m.simulationAttempts += result.metrics.simulationAttempts;
    m.transitionSamples += result.metrics.transitionSamples;
    m.leafEvaluations += result.metrics.leafEvaluations;
    m.maxDepthReached = std::max(m.maxDepthReached, result.metrics.maxDepthReached);
    if (result.aborted) {
        ++metrics.supportAborts; metrics.discardedSimulations+=result.metrics.simulations;
    }
    if (!result.selectedAction) { ++metrics.fallback; return false; }
    // Resolve from fresh live candidates; never transfer a sampled snapshot.
    const auto candidates = v4CandidateActions(gc);
    const auto action = std::find_if(candidates.begin(), candidates.end(),
        [&](auto a) { return a.bits == *result.selectedAction; });
    if (action == candidates.end()) throw std::runtime_error("live OOC MCTS selected illegal root action");
    ++metrics.owned;
    action->execute(gc);
    return true;
}
void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &m, int realCombats) {
    if (liveTrace.empty()) return;
    std::lock_guard<std::mutex> lock(liveTraceMutex);
    const std::string header = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,transitionSamples,combatSurrogateSamples,leafEvaluations,maxDepth,mctsWallSec,mctsCpuSec,realCombats,imaginedCombats,unsupportedCombats,mctsSupportAborts,discardedSimulations,simulationAttempts,pendingLeaves,battleLeaves,mapLeaves,projectionSteps,outcomeParticles,particleRevisits,deterministicRevisits,depthSum,continuationLimitAborts,trivialRootBypasses,earlyStopLockedRoot,savedSimulations,metadataBuilds,priorBuilds,preparedCombats,combatEdgeSamples\n";
    std::ifstream existing(liveTrace);
    std::string firstLine;
    if (std::getline(existing,firstLine) && firstLine+'\n' != header)
        throw std::runtime_error("STS_OOC_MCTS_TRACE incompatible header; use a fresh trace path");
    std::ofstream out(liveTrace, std::ios::app);
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot write output");
    if (out.tellp() == 0) out << header;
    out << std::setprecision(12) << seed << ',' << m.decisions << ',' << m.owned << ',' << m.fallback
        << ',' << m.search.simulations << ',' << m.search.transitionSamples << ',' << m.combatSamples
        << ',' << m.search.leafEvaluations << ',' << m.search.maxDepthReached
        << ',' << m.wallSeconds << ',' << m.cpuSeconds << ',' << realCombats
        << ',' << m.continuation.imaginedCombats << ',' << m.continuation.unsupportedCombats
        << ',' << m.supportAborts << ',' << m.discardedSimulations << ',' << m.search.simulationAttempts
        << ',' << m.continuation.pendingLeaves << ',' << m.continuation.battleLeaves
        << ',' << m.continuation.mapLeaves << ',' << m.continuation.projectionSteps
        << ',' << m.search.outcomeParticles << ',' << m.search.particleRevisits
        << ',' << m.search.deterministicRevisits << ',' << m.search.depthSum
        << ',' << m.continuation.continuationLimitAborts
        << ',' << m.search.trivialRootBypasses << ',' << m.search.earlyStopLockedRoot
        << ',' << m.search.savedSimulations << ',' << m.continuation.metadataBuilds
        << ',' << m.continuation.priorBuilds << ',' << m.continuation.preparedCombats
        << ',' << m.continuation.combatEdgeSamples << '\n';
    std::ofstream reasons(liveTrace+".support.jsonl",std::ios::app);
    reasons << nlohmann::json{{"seed",seed},{"reasons",m.continuation.supportReasons},
        {"continuation_reasons",m.continuation.continuationReasons},
        {"continuation_limit_aborts",m.continuation.continuationLimitAborts}}.dump() << '\n';
    reasons.flush();
    if (!reasons) throw std::runtime_error("OOC MCTS support trace write failed");
    out.flush();
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE write failed");
}

}

#include "../../tests/data/ooc_v4_policy_fixture.h"
namespace one_combat {
void oocMctsAdapterSelfTest() {
    using namespace sts;
    using namespace sts::search;
    std::cout << std::setprecision(12);
    require(g_oocStrategicTokNet.path == "selfplay/models/ooc_strategic_tok_final.native"
        || g_oocStrategicTokNet.path.find("/selfplay/models/ooc_strategic_tok_final.native") != std::string::npos,
        "policy parity requires tracked final V4 artifact");
    float glob[42]; for (int i=0;i<42;++i) glob[i]=(i-20)*.125f;
    const int dk[96][3] = {{1,0,5},{42,1,2},{100,0,1}};
    const int rl[64][2] = {{1,1},{23,4}};
    const int pt[8][2] = {{2,1},{7,2}};
    const auto fixturePrepared = g_oocStrategicTokNet.prepareState(glob,3,dk,2,rl,2,pt);
    for (auto f : v4PolicyFixtures) {
        const float et[4] = {float(f.entityType==0),float(f.entityType==1),float(f.entityType==2),float(f.entityType==3)};
        double logit = g_oocStrategicTokNet.predictPolicyLogit(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        double q = g_oocStrategicTokNet.predictActionValue(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        require(logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price)
            && q == g_oocStrategicTokNet.predictActionValue(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price),
            "prepared V4 policy/Q exactly match legacy entry points");
        require(std::abs(logit-f.logit)<1e-4, "V4 policy parity");
        require(std::abs(q-f.q)<2e-4, "V4 Q regression parity");
        std::cout << "parity bits="<<f.bits<<" logit="<<logit<<" expected="<<f.logit
                  <<" error="<<std::abs(logit-f.logit)<<" q_error="<<std::abs(q-f.q)<<'\n';
    }
    const auto cold = oocPolicyWeights({0, 2}, .5), hot = oocPolicyWeights({0, 2}, 2);
    require(cold[0] < hot[0] && cold[1] == 1 && hot[1] == 1, "temperature changes policy concentration");
    auto extreme = oocPolicyWeights({-10000,0,10000});
    require(extreme == std::vector<double>({0,0,1}), "stable extreme softmax");
    auto rejects = [](auto fn) { bool rejected=false; try { fn(); } catch(const std::exception &) { rejected=true; }
        require(rejected,"invalid adapter input accepted"); };
    rejects([] { oocPolicyWeights({0},0); });
    rejects([] { oocPolicyWeights({NAN}); });
    rejects([] { oocPolicyWeights({0},INFINITY); });
    rejects([] { oocPolicyWeights({0},NAN); });
    // One-unit internal bound exposes the final-transition edge without a live
    // configuration knob or hundreds of artificial native decisions.
    for (double finalValue : {0.0,0.5,1.0}) {
        int transitions=0, checkpointChecks=0;
        const auto value=boundedContinuation(1,[&]() -> std::optional<double> {
            ++checkpointChecks;
            return transitions ? std::optional<double>(finalValue) : std::nullopt;
        },[&] { ++transitions; });
        require(value==finalValue && transitions==1 && checkpointChecks==2,
            "last permitted transition accepts exact terminal or resolved checkpoint value");
    }
    {
        int transitions=0;
        bool aborted=false;
        try { boundedContinuation(1,[] { return std::optional<double>{}; },[&] { ++transitions; }); }
        catch (const OocSearchUnsupported &error) { aborted=std::string(error.what())=="continuation_step_limit_1"; }
        require(aborted && transitions==1,"unresolved continuation still aborts exactly at step limit");
    }
    GameContext gc(CharacterClass::IRONCLAD,42,0);
    gc.screenState=ScreenState::MAP_SCREEN;
    gc.curEvent=Event::INVALID;
    gc.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    require(gc.map != nullptr, "real map fixture");
    PathHistory path; path.update(gc);
    OocGameContextModel model(gc,path);
    // Prior visit counts are external to GameContext and must survive root construction.
    PathHistory nonemptyHistory;
    nonemptyHistory.roomVisits[int(Room::SHOP)]=2;
    nonemptyHistory.roomVisits[int(Room::REST)]=1;
    nonemptyHistory.roomVisits[int(Room::EVENT)]=3;
    nonemptyHistory.roomVisits[int(Room::ELITE)]=4;
    nonemptyHistory.roomVisits[int(Room::MONSTER)]=5;
    nonemptyHistory.roomVisits[int(Room::TREASURE)]=6;
    OocGameContextModel historyModel(gc,nonemptyHistory);
    const auto historyLogits=historyModel.policyLogits(0);
    const auto cachedHistoryActions=historyModel.legalActions(0);
    for (int repeat=0;repeat<3;++repeat) {
        require(historyModel.policyLogits(0)==historyLogits,"cached logits remain bit-exact");
        const auto again=historyModel.legalActions(0);
        require(again.size()==cachedHistoryActions.size(),"cached legal action count");
        for (std::size_t i=0;i<again.size();++i)
            require(again[i].id==cachedHistoryActions[i].id && again[i].prior==cachedHistoryActions[i].prior,
                "cached legal IDs/order/raw priors exact");
    }
    require(historyModel.continuationMetrics().metadataBuilds==1
        && historyModel.continuationMetrics().priorBuilds==1
        && !historyModel.searchGuaranteedNonAborting(),
        "immutable metadata/token/prior build once; live model remains abort-capable");
    const auto historyActions=v4CandidateActions(gc);
    const TokState historyTokens=buildTokState(gc,nonemptyHistory);
    double maxHistoryPolicyError=0;
    for(std::size_t i=0;i<historyActions.size();++i) {
        const auto a=historyActions[i];
        int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
        strategicCands(gc,a,type,c1,c2,c3,d1,d2,d3);
        tokEntity(gc,a,et,ei,price);
        const int cats[6]={c1,c2,c3,d1,d2,d3};
        const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
        const double direct=g_oocStrategicTokNet.predictPolicyLogit(historyTokens.glob,
            historyTokens.nDk,historyTokens.dk,historyTokens.nRl,historyTokens.rl,
            historyTokens.nPt,historyTokens.pt,a.bits,cats,type,int(gc.screenState),entity,ei,price);
        maxHistoryPolicyError=std::max(maxHistoryPolicyError,std::abs(direct-historyLogits[i]));
        require(std::abs(direct-historyLogits[i])<1e-12,"nonempty history V4 policy parity");
    }
    const auto previousHistory=t_curPath;
    t_curPath=&nonemptyHistory;
    const double directHistoryLeaf=vStateWinNative(gc);
    const double adapterHistoryLeaf=historyModel.leafValue(0);
    require(t_curPath==&nonemptyHistory,"leaf restores caller history");
    t_curPath=previousHistory;
    require(std::abs(directHistoryLeaf-adapterHistoryLeaf)<1e-12,"nonempty history native win parity");
    // The fixture must expose lost-history bugs, not merely exercise nonzero inputs.
    const auto emptyHistoryLogits=model.policyLogits(0);
    bool policyChanged=false;
    for(std::size_t i=0;i<historyLogits.size();++i)
        policyChanged=policyChanged || std::abs(historyLogits[i]-emptyHistoryLogits[i])>1e-6;
    require(policyChanged && std::abs(adapterHistoryLeaf-model.leafValue(0))>1e-6,
            "nonempty history fixture must affect both models");
    std::cout<<"nonempty_history_parity actions="<<historyActions.size()
        <<" policy_max_error="<<maxHistoryPolicyError
        <<" leaf_error="<<std::abs(directHistoryLeaf-adapterHistoryLeaf)
        <<" leaf_value="<<adapterHistoryLeaf<<'\n';
    auto candidates=v4CandidateActions(gc);
    auto legal=model.legalActions(0);
    auto logits=model.policyLogits(0);
    require(!legal.empty() && legal.size()==candidates.size(),"candidate parity");
    std::set<std::uint32_t> ids;
    for (std::size_t i=0;i<legal.size();++i) {
        require(legal[i].id==candidates[i].bits && ids.insert(legal[i].id).second,"primitive action identity");
    }
    std::mt19937_64 rng(42);
    rejects([&] { model.sampleSuccessor(0,0xFFFFFFFFu,rng); });
    GameContext expected=detachedCopy(gc);
    candidates.front().execute(expected);
    auto child=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(child).screenState==expected.screenState
        && model.state(child).curMapNodeX==expected.curMapNodeX
        && model.state(child).floorNum==expected.floorNum
        && model.state(child).curHp==expected.curHp,"native copied successor");
    require(model.state(0).curMapNodeX==gc.curMapNodeX && model.state(0).floorNum==gc.floorNum
        && model.state(0).screenState==gc.screenState,"parent unchanged");
    require(model.state(child).map.get()!=model.state(0).map.get()
        && model.state(0).map.get()!=gc.map.get(),"map detached at root and successor");
    auto repeated=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(repeated).curMapNodeX==model.state(child).curMapNodeX
        && model.state(repeated).info.encounter==model.state(child).info.encounter,"concrete RNG replay");
    // Mutate caller's map: materialized root must retain its own content.
    auto room=model.state(0).map->nodes[0][0].room;
    gc.map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room,"external map independence");
    gc.map->nodes[0][0].room=room;
    model.state(child).map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room
        && gc.map->nodes[0][0].room==room,"child map mutation cannot affect ancestors");
    model.state(child).map->nodes[0][0].room=room;
    // Audit all supported contracts against the pre-existing primitive set.
    auto checkCandidates = [&](GameContext fixture) {
        auto expectedActions=GameAction::getAllActionsInState(fixture);
        require(!expectedActions.empty(),"supported candidate fixture is nonempty");
        require(v4DecisionSupported(fixture),"supported screen classification");
        OocGameContextModel provider(fixture,path);
        const auto tokens=buildTokState(fixture,path);
        const auto prepared=g_oocStrategicTokNet.prepareState(tokens.glob,tokens.nDk,tokens.dk,
            tokens.nRl,tokens.rl,tokens.nPt,tokens.pt);
        // Another preparation must not invalidate a previously prepared value.
        (void)g_oocStrategicTokNet.prepareState(glob,0,dk,0,rl,0,pt);
        for (const auto action : expectedActions) {
            int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
            strategicCands(fixture,action,type,c1,c2,c3,d1,d2,d3);
            tokEntity(fixture,action,et,ei,price);
            const int cats[6]={c1,c2,c3,d1,d2,d3};
            const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
            const auto &net=g_oocStrategicTokNet;
            require(net.predictPolicyLogit(prepared,action.bits,cats,type,int(fixture.screenState),entity,ei,price)
                    == net.predictPolicyLogit(tokens.glob,tokens.nDk,tokens.dk,tokens.nRl,tokens.rl,tokens.nPt,tokens.pt,
                        action.bits,cats,type,int(fixture.screenState),entity,ei,price)
                && net.predictActionValue(prepared,action.bits,cats,type,int(fixture.screenState),entity,ei,price)
                    == net.predictActionValue(tokens.glob,tokens.nDk,tokens.dk,tokens.nRl,tokens.rl,tokens.nPt,tokens.pt,
                        action.bits,cats,type,int(fixture.screenState),entity,ei,price),
                "prepared policy and Q exact across supported screens and interleaved states");
        }
        auto actual=provider.legalActions(0);
        require(actual.size()==expectedActions.size(),"exact V4 candidate count");
        for(std::size_t i=0;i<actual.size();++i)
            require(actual[i].id==expectedActions[i].bits,"exact V4 candidate bits/order");
        std::cout<<"candidate_parity screen="<<int(fixture.screenState)
                 <<" selector="<<int(fixture.info.selectScreenType)<<" count="<<actual.size()<<'\n';
    };
    auto fixture=detachedCopy(gc);
    fixture.screenState=ScreenState::REST_ROOM; checkCandidates(fixture);
    fixture.openCardSelectScreen(CardSelectScreenType::UPGRADE,1); checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN;
    fixture.curEvent=Event::BIG_FISH; fixture.info.hpAmount0=20;
    fixture.info.hpAmount1=5; checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::SHOP_ROOM;
    fixture.info.shop.setup(fixture); checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.setupTreasureRoom(); checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::BOSS_RELIC_REWARDS;
    fixture.info.bossRelics[0]=RelicId::BLACK_BLOOD;
    fixture.info.bossRelics[1]=RelicId::COFFEE_DRIPPER;
    fixture.info.bossRelics[2]=RelicId::FUSION_HAMMER; checkCandidates(fixture);
    checkCandidates(gc);
    for(auto selector : {CardSelectScreenType::TRANSFORM,CardSelectScreenType::TRANSFORM_UPGRADE,
        CardSelectScreenType::REMOVE,CardSelectScreenType::DUPLICATE,CardSelectScreenType::OBTAIN,
        CardSelectScreenType::BOTTLE,CardSelectScreenType::BONFIRE_SPIRITS,CardSelectScreenType::INVALID}) {
        fixture=detachedCopy(gc); fixture.screenState=ScreenState::CARD_SELECT;
        fixture.info.selectScreenType=selector;
        OocGameContextModel unsupported(fixture,path);
        require(unsupported.isLeafBoundary(0),"uncovered selector is a leaf boundary");
    }
    fixture=detachedCopy(gc); fixture.curMapNodeY=14;
    OocGameContextModel lastRow(fixture,path); require(lastRow.isLeafBoundary(0),"map row 14 boundary");
    fixture=detachedCopy(gc); fixture.map=nullptr;
    OocGameContextModel noMap(fixture,path); require(noMap.isLeafBoundary(0),"missing map boundary");
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN; fixture.curEvent=Event::MATCH_AND_KEEP;
    OocGameContextModel match(fixture,path); require(match.isLeafBoundary(0),"match and keep boundary");
    OocAdapterOptions uniformOptions{true}; uniformOptions.uniformPrior = true;
    OocGameContextModel uniformPrior(gc,path,{},uniformOptions);
    const auto uniformActions = uniformPrior.legalActions(0);
    require(!uniformActions.empty(), "uniform prior retains legal actions");
    for (const auto &action : uniformActions) require(action.prior == 1, "uniform prior equal positive weights");
    OocAdapterOptions constantOptions{true}; constantOptions.constantLeaf = true;
    OocGameContextModel constantCheckpoint(gc,path,{},constantOptions);
    std::mt19937_64 constantRng(777);
    require(constantCheckpoint.evaluateLeaf(0,constantRng) == .5, "constant value only at resolved checkpoint");
    for (auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        auto terminal = detachedCopy(gc); terminal.outcome = outcome;
        OocGameContextModel exactTerminal(terminal,path,{},constantOptions);
        require(exactTerminal.evaluateLeaf(0,constantRng) == (outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0),
                "constant ablation preserves terminal values");
    }
    {
        OocMctsConfig parsed; OocAdapterOptions opts{true};
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","1",parsed,opts);
        require(parsed.allowUnqualifiedRootStop,"explicit early-stop enable parsed");
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","0",parsed,opts);
        require(!parsed.allowUnqualifiedRootStop,"early-stop rollback parsed");
        applyLiveControl("STS_OOC_MCTS_ROOT_SELECTION","q",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_COMBATS","3",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_CPUCT","0",parsed,opts);
        require(parsed.selectByMeanQ && parsed.cPuct == 0 && opts.leafCombats == 3, "accepted bounded knobs");
        for (const auto &invalid : std::vector<std::pair<std::string,std::string>>{
            {"STS_OOC_MCTS_EARLY_STOP","true"},{"STS_OOC_MCTS_EARLY_STOP","2"},{"STS_OOC_MCTS_PRIOR","none"},{"STS_OOC_MCTS_TEMPERATURE","0"},
            {"STS_OOC_MCTS_CPUCT","-1"},{"STS_OOC_MCTS_WIDEN_K","nan"},
            {"STS_OOC_MCTS_WIDEN_ALPHA","1"},{"STS_OOC_MCTS_MAX_DEPTH","33"},
            {"STS_OOC_MCTS_MAX_DEPTH","2.5"},{"STS_OOC_MCTS_LEAF_COMBATS","2"},
            {"STS_OOC_MCTS_LEAF_POLICY","random"},{"STS_OOC_MCTS_LEAF_VALUE","0"},
            {"STS_OOC_MCTS_ROOT_SELECTION"," q"},{"STS_OOC_MCTS_TEMPERATURE","1junk"}})
            rejects([&] { applyLiveControl(invalid.first,invalid.second,parsed,opts); });
    }
    const PathHistory *saved=t_curPath; t_curPath=&path;
    for (int i=0;i<3;++i) {
        auto probe=detachedCopy(gc); probe.curHp=10+i*30; probe.gold=50+i*150;
        OocGameContextModel leaf(probe,path);
        double direct=vStateWin(probe), adapted=leaf.leafValue(0);
        require(std::abs(direct-adapted)<1e-12,"native v_win leaf parity");
        std::cout<<"leaf_parity hp="<<probe.curHp<<" gold="<<probe.gold<<" value="<<adapted<<'\n';
    }
    t_curPath=saved;
    auto battle=detachedCopy(gc); battle.screenState=ScreenState::BATTLE;
    OocGameContextModel boundary(battle,path);
    require(!boundary.terminalValue(0) && boundary.isLeafBoundary(0),"battle is nonterminal boundary");
    rejects([&] { boundary.legalActions(0); });
    auto br=OocMctsPlanner().search(boundary,0,4);
    require(br.metrics.leafEvaluations==4 && br.rootActions.empty()
        && br.metrics.transitionSamples==0,"battle MCTS boundary");
    for(auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        battle.outcome=outcome;
        OocGameContextModel terminal(battle,path);
        require(terminal.terminalValue(0)==(outcome==GameOutcome::PLAYER_VICTORY?1.:0.),"exact terminal value");
        auto tr=OocMctsPlanner().search(terminal,0,3);
        require(tr.metrics.leafEvaluations==0 && tr.rootActions.empty(),"terminal precedence");
    }
    for (auto screen : {ScreenState::INVALID,ScreenState::CARD_SELECT,ScreenState::REWARDS}) {
        auto unsupported=detachedCopy(gc); unsupported.screenState=screen;
        OocGameContextModel leaf(unsupported,path);
        require(leaf.isLeafBoundary(0),"unsupported state boundary");
    }
    auto reward=detachedCopy(gc); reward.openCombatRewardScreen(reward.createCombatReward());
    require(reward.info.rewardsContainer.cardRewardCount>0,"reward fixture");
    auto rewardActions=v4CandidateActions(reward);
    GameAction skip(GameAction::RewardsActionType::CARD,reward.info.rewardsContainer.cardRewardCount-1,5);
    require(std::count_if(rewardActions.begin(),rewardActions.end(),[&](auto a){return a.bits==skip.bits;})==1,
        "reward skip included exactly once");
    OocGameContextModel rewards(reward,path);
    auto rewardChild=rewards.sampleSuccessor(0,skip.bits,rng);
    require(rewards.state(rewardChild).info.rewardsContainer.cardRewardCount
        ==reward.info.rewardsContainer.cardRewardCount-1,"reward skip execution");
    // Inject an equivalent RAW result from a deterministic native exit. The
    // callback dispatches the same native reward code in both branches.
    struct FakeSampler final : CombatTransitionSampler {
        bool enabled=true, death=false, stochastic=false, escape=false;
        mutable int supportCalls=0, sampleCalls=0;
        mutable std::vector<std::uint64_t> draws;
        CombatTransitionPersistentState raw;
        CombatPredictorInputV1 expectedInput;
        CombatRuntimeSupport support(const GameContext &g, const CombatPredictorInputV1 &input) const override {
            ++supportCalls;
            require(g.screenState==ScreenState::BATTLE,"sampler prebattle screen");
            require(combatPredictorInputJson(input)==combatPredictorInputJson(expectedInput),
                    "predictor must precede battle initialization");
            return {enabled, enabled?"supported":"fake unsupported"};
        }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,
                                   std::mt19937_64 &r) const override {
            ++sampleCalls;
            bool loss=death;
            if(stochastic) { const auto draw=r(); draws.push_back(draw); loss=draw&1; }
            return {loss?CombatRuntimeSample::Outcome::DEATH:
                (escape?CombatRuntimeSample::Outcome::ESCAPE:CombatRuntimeSample::Outcome::VICTORY),raw};
        }
    };
    auto combatRoot=detachedCopy(gc);
    combatRoot.screenState=ScreenState::REST_ROOM;
    combatRoot.curRoom=Room::MONSTER;
    int regainCalls=0;
    combatRoot.regainControlAction=[&](GameContext &g) {
        ++regainCalls;
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else g.afterBattle();
    };
    const auto restActions=v4CandidateActions(combatRoot);
    require(!restActions.empty(),"combat entry rest fixture");
    const auto restAction=restActions.front();
    auto real=detachedCopy(combatRoot);
    PathHistory realPath=path; realPath.update(real);
    restAction.execute(real); realPath.update(real);
    auto fake=std::make_shared<FakeSampler>();
    // An injected sampler is never consulted for ordinary nonbattle actions.
    auto ordinary=detachedCopy(gc); ordinary.screenState=ScreenState::REST_ROOM;
    auto ordinaryExpected=detachedCopy(ordinary);
    const auto ordinaryAction=v4CandidateActions(ordinary).front();
    ordinaryAction.execute(ordinaryExpected);
    OocGameContextModel ordinaryModel(ordinary,path,fake);
    const auto ordinaryId=ordinaryModel.sampleSuccessor(0,ordinaryAction.bits,rng);
    require(fake->supportCalls==0 && fake->sampleCalls==0
        && test::oocStateFingerprint(ordinaryModel.state(ordinaryId))==test::oocStateFingerprint(ordinaryExpected),
        "ordinary injected successor unchanged");
    fake->expectedInput=captureCombatPredictorInput(real,real.info.encounter,potionKeepValue(real));
    const auto preFingerprint=test::oocStateFingerprint(real);
    BattleContext deterministic;
    deterministic.init(real,MonsterEncounter::CULTIST);
    deterministic.player.curHp=37;
    deterministic.outcome=Outcome::PLAYER_VICTORY;
    int rawCalls=0;
    {
        CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
            ++rawCalls; fake->raw=captureCombatTransitionState(raw);
        });
        deterministic.exitBattle(real);
    }
    realPath.update(real);
    require(rawCalls==1 && regainCalls==2,"native oracle continuation once");
    regainCalls=0;
    OocGameContextModel crossed(combatRoot,path,fake);
    const auto rootFingerprint=test::oocStateFingerprint(crossed.state(0));
    const auto crossedId=crossed.sampleSuccessor(0,restAction.bits,rng);
    require(regainCalls==2 && fake->sampleCalls==1 && fake->supportCalls==1,
            "injected reward continuation exactly once");
    require(test::oocStateFingerprint(crossed.state(crossedId))==test::oocStateFingerprint(real),
            "injected continuation OOC/reward/RNG fingerprint");
    require(combatTransitionFingerprint(crossed.state(crossedId))==combatTransitionFingerprint(real),
            "injected persistent continuation fingerprint");
    require(crossed.pathHistory(crossedId).roomVisits==realPath.roomVisits
        && crossed.pathHistory(crossedId).lastNodeKey==realPath.lastNodeKey,"native PathHistory parity");
    require(test::oocStateFingerprint(crossed.state(0))==rootFingerprint,"combat parent unchanged");
    // Compare an actual Smoke Bomb exit with explicit ESCAPE injection from
    // the identical prebattle origin. Includes Cleric's pre-reward maxHP gain.
    for (bool cleric : {false, true}) {
        const int savedRegainCalls = regainCalls;
        auto escapeRoot=detachedCopy(combatRoot);
        escapeRoot.potions[0]=Potion::SMOKE_BOMB;
        escapeRoot.potionCount=1;
        escapeRoot.smokeBombUsed=true; // Native battle initialization resets it.
        if (cleric) escapeRoot.relics.add({RelicId::FACE_OF_CLERIC,0});
        auto oracle=detachedCopy(escapeRoot);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        restAction.execute(oracle); oraclePath.update(oracle);
        auto escapeSampler=std::make_shared<FakeSampler>();
        escapeSampler->escape=true;
        escapeSampler->expectedInput=captureCombatPredictorInput(oracle,oracle.info.encounter,potionKeepValue(oracle));
        BattleContext smoke;
        smoke.init(oracle,MonsterEncounter::CULTIST);
        require(!smoke.smokeBombUsed,"native pre-used Smoke flag reset");
        smoke.player.curHp=37;
        smoke.drinkPotion(0);
        require(smoke.smokeBombUsed && smoke.outcome==Outcome::PLAYER_VICTORY
            && smoke.potionCount==0,"native Smoke Bomb consumes and exits");
        int escapeRawCalls=0;
        {
            CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
                ++escapeRawCalls; escapeSampler->raw=captureCombatTransitionState(raw);
            });
            smoke.exitBattle(oracle);
        }
        oraclePath.update(oracle);
        OocGameContextModel imagined(escapeRoot,path,escapeSampler);
        const auto parent=test::oocStateFingerprint(imagined.state(0));
        const auto escaped=imagined.sampleSuccessor(0,restAction.bits,rng);
        require(escapeRawCalls==1 && escapeSampler->sampleCalls==1
            && test::oocStateFingerprint(imagined.state(escaped))==test::oocStateFingerprint(oracle)
            && combatTransitionFingerprint(imagined.state(escaped))==combatTransitionFingerprint(oracle),
            "ESCAPE exact native OOC/persistent/all-RNG continuation parity");
        require(oracle.screenState==ScreenState::MAP_SCREEN && !oracle.smokeBombUsed
            && imagined.pathHistory(escaped).roomVisits==oraclePath.roomVisits
            && imagined.pathHistory(escaped).lastNodeKey==oraclePath.lastNodeKey
            && test::oocStateFingerprint(imagined.state(0))==parent,
            "ESCAPE no rewards, native PathHistory, unchanged parent");
        escapeSampler->escape=false;
        OocGameContextModel mislabeled(escapeRoot,path,escapeSampler);
        rejects([&] { mislabeled.sampleSuccessor(0,restAction.bits,rng); });
        auto boss=detachedCopy(escapeRoot);
        boss.info.encounter=MonsterEncounter::SLIME_BOSS;
        rejects([&] { applySampledCombatExit(boss,{CombatRuntimeSample::Outcome::ESCAPE,escapeSampler->raw}); });
        BattleContext blocked;
        blocked.init(boss,MonsterEncounter::SLIME_BOSS);
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && !blocked.smokeBombUsed
            && blocked.potions[0]==Potion::SMOKE_BOMB && blocked.potionCount==1,
            "boss blocks Smoke Bomb without consuming it or accepting ESCAPE");
        blocked.init(escapeRoot,MonsterEncounter::CULTIST);
        blocked.player.buff<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && blocked.potionCount==1,
            "Surrounded blocks Smoke Bomb without consumption");
        blocked.player.removeStatus<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.smokeBombUsed && blocked.potionCount==0,
            "removing Surrounded allows escape later in the same combat");
        regainCalls=savedRegainCalls;
    }
    std::cout<<"smoke_escape_oracle native_origin=identical cleric=both raw_outcome=ESCAPE parity=exact\n";
    fake->enabled=false; regainCalls=0;
    OocGameContextModel unsupportedCombat(combatRoot,path,fake);
    const auto unsupportedId=unsupportedCombat.sampleSuccessor(0,restAction.bits,rng);
    require(fake->sampleCalls==1 && regainCalls==1 && unsupportedCombat.isLeafBoundary(unsupportedId)
        && test::oocStateFingerprint(unsupportedCombat.state(unsupportedId))==preFingerprint,
        "unsupported combat retains exact battle leaf");
    OocGameContextModel disabledCombat(combatRoot,path);
    const auto disabledId=disabledCombat.sampleSuccessor(0,restAction.bits,rng);
    require(test::oocStateFingerprint(disabledCombat.state(disabledId))==preFingerprint
        && disabledCombat.pathHistory(disabledId).roomVisits==unsupportedCombat.pathHistory(unsupportedId).roomVisits,
        "no sampler combat behavior unchanged");
    fake->enabled=true; fake->death=true; regainCalls=0;
    OocGameContextModel deathCombat(combatRoot,path,fake);
    const auto deathId=deathCombat.sampleSuccessor(0,restAction.bits,rng);
    require(regainCalls==1 && deathCombat.terminalValue(deathId)==0
        && deathCombat.state(deathId).screenState==ScreenState::BATTLE,
        "death terminal without reward continuation");
    fake->death=false; fake->stochastic=true;
    std::mt19937_64 plannerRng(991), expectedRng(991);
    OocGameContextModel chanceCombat(combatRoot,path,fake);
    for(int i=0;i<8;++i) {
        const auto expectedDraw=expectedRng();
        const auto sampleId=chanceCombat.sampleSuccessor(0,restAction.bits,plannerRng);
        require(fake->draws.back()==expectedDraw,"independent supplied planner RNG draw");
        require(bool(chanceCombat.terminalValue(sampleId))==bool(expectedDraw&1),
                "chance outcome not value selected");
    }
    // Restrict the test root to the entry action so every planner chance
    // expansion exercises combat without unrelated rest/select decisions.
    struct SingleEntryModel final : OocGenerativeModel {
        OocGameContextModel &adapter;
        OocActionId entry;
        SingleEntryModel(OocGameContextModel &a,OocActionId e):adapter(a),entry(e) {}
        std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
        bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
        std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
            require(id==0,"single-entry planner must stop at depth one"); return {{entry,1.0}};
        }
        OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
            return adapter.sampleSuccessor(id,a,r);
        }
        double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
    };
    fake->draws.clear();
    const auto samplesBefore=fake->sampleCalls;
    OocGameContextModel plannerCombat(combatRoot,path,fake);
    SingleEntryModel entryModel(plannerCombat,restAction.bits);
    OocMctsConfig chanceConfig; chanceConfig.maxDepth=1; chanceConfig.seed=12345;
    OocMctsPlanner chancePlanner(chanceConfig);
    const auto chanceResult=chancePlanner.search(entryModel,0,32);
    std::mt19937_64 expectedChanceRng(chanceConfig.seed);
    std::vector<std::uint64_t> expectedChanceDraws;
    for(std::uint64_t visit=1;visit<=32;++visit) {
        if(expectedChanceDraws.size()<chancePlanner.chanceWideningLimit(visit))
            expectedChanceDraws.push_back(expectedChanceRng());
        else {
            std::uniform_int_distribution<std::size_t> choose(0,expectedChanceDraws.size()-1);
            (void)choose(expectedChanceRng);
        }
    }
    require(fake->draws==expectedChanceDraws && std::set<std::uint64_t>(fake->draws.begin(),fake->draws.end()).size()==fake->draws.size(),
            "planner expansions receive independent RNG draws with unbiased particle reuse");
    const auto &chanceMetrics=chanceResult.metrics;
    require(chanceMetrics.simulations==32 && chanceMetrics.chanceNodes==1
        && chanceMetrics.transitionSamples==expectedChanceDraws.size()
        && chanceMetrics.outcomeParticles==chanceMetrics.transitionSamples
        && chanceMetrics.decisionNodes==chanceMetrics.outcomeParticles+1
        && chanceMetrics.maxDepthReached==1
        && fake->sampleCalls-samplesBefore==int(chanceMetrics.transitionSamples)
        && chanceResult.rootActions.size()==1 && chanceResult.rootActions.front().visits==32,
        "combat planner progressive widening particle metrics preserved");
    // Native continuation may enter another battle (e.g. chained battles).
    // The adapter crosses one combat boundary per primitive transition.
    fake->stochastic=false;
    auto chainedRoot=detachedCopy(combatRoot);
    int chainContinuations=0;
    chainedRoot.regainControlAction=[&](GameContext &g) {
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else { ++chainContinuations; g.enterBattle(MonsterEncounter::CULTIST); }
    };
    const auto chainSamplesBefore=fake->sampleCalls;
    OocGameContextModel chainedCombat(chainedRoot,path,fake);
    const auto chainedId=chainedCombat.sampleSuccessor(0,restAction.bits,rng);
    require(chainContinuations==1 && fake->sampleCalls==chainSamplesBefore+1
        && chainedCombat.state(chainedId).screenState==ScreenState::BATTLE
        && chainedCombat.isLeafBoundary(chainedId) && !chainedCombat.terminalValue(chainedId),
        "second battle continuation remains leaf without recursive sampling");
    const auto chainedResult=OocMctsPlanner().search(chainedCombat,chainedId,4);
    require(chainedResult.metrics.transitionSamples==0 && chainedResult.metrics.leafEvaluations==4
        && fake->sampleCalls==chainSamplesBefore+1,"chained battle planner retains leaf seam");
    std::cout<<"combat_planner_chance simulations="<<chanceMetrics.simulations
        <<" particles="<<chanceMetrics.outcomeParticles<<" samples="<<chanceMetrics.transitionSamples
        <<" depth="<<chanceMetrics.maxDepthReached<<" chained_battle=leaf"<<'\n';
    std::cout<<"combat_adapter_oracle raw_calls="<<rawCalls
        <<" fingerprint=exact path_history=exact stochastic_draws="<<fake->draws.size()<<'\n';
    auto result=OocMctsPlanner().search(model,0,32);
    double sum=0; for(auto a:result.rootActions) sum+=a.prior;
    require(std::abs(sum-1)<1e-12,"normalized priors");
    auto best=std::max_element(logits.begin(),logits.end());
    auto priorBest=std::max_element(result.rootActions.begin(),result.rootActions.end(),[](auto a,auto b){return a.prior<b.prior;});
    require(priorBest->id==legal[best-logits.begin()].id,"policy prior ordering");
    for(auto a:result.rootActions) {
        auto it=std::find_if(legal.begin(),legal.end(),[&](auto l){return l.id==a.id;});
        require(std::isfinite(a.prior) && a.prior>=0,"finite nonnegative priors");
        std::cout << "MAP(x=" << GameAction(a.id).getIdx1() << ")";
        std::cout<<" bits="<<a.id<<" logit="<<logits[it-legal.begin()]<<" prior="<<a.prior
            <<" visits="<<a.visits<<" Q="<<a.q<<'\n';
    }
    auto m=result.metrics;
    std::cout<<"selected="<<result.selectedAction.value_or(0xFFFFFFFFu)<<" simulations="<<m.simulations
        <<" decision_nodes="<<m.decisionNodes<<" chance_nodes="<<m.chanceNodes
        <<" particles="<<m.outcomeParticles<<" samples="<<m.transitionSamples
        <<" leaf_evaluations="<<m.leafEvaluations<<" max_depth="<<m.maxDepthReached<<'\n';
    // Rich features cannot see pending gold. Checkpoint projection must collect
    // it on a detached copy, and match the existing policy's completed oracle.
    std::vector<float> pendingFeatures;
    for (int amount : {1,1000}) {
        auto pendingGold=detachedCopy(reward);
        auto &container=pendingGold.info.rewardsContainer;
        container.goldRewardCount=1; container.gold[0]=amount;
        container.cardRewardCount=container.relicCount=container.potionCount=0;
        container.emeraldKey=container.sapphireKey=false;
        const auto fingerprint=test::oocStateFingerprint(pendingGold);
        const auto features=richFeatureVec(pendingGold);
        if (pendingFeatures.empty()) pendingFeatures=features;
        else require(features==pendingFeatures,"rich model cannot see pending reward contents fixture");
        auto completed=detachedCopy(pendingGold);
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<16 && completed.screenState!=ScreenState::MAP_SCREEN;++step)
            runFullRunOocPolicyStep(completed,oracleAgent,false,true);
        require(completed.screenState==ScreenState::MAP_SCREEN && completed.gold==pendingGold.gold+amount,
            "pending gold oracle reaches checkpoint after collection");
        OocGameContextModel projected(pendingGold,path,{}, {true});
        rejects([&] { projected.leafValue(0); });
        std::mt19937_64 projectionRng(543);
        const auto savedPath=t_curPath;
        t_curPath=&projected.pathHistory(0);
        const auto oracleValue=vStateWinNative(completed);
        t_curPath=savedPath;
        require(projected.evaluateLeaf(0,projectionRng)==oracleValue
            && projected.continuationMetrics().pendingLeaves==1
            && projected.continuationMetrics().projectionSteps>=2
            && test::oocStateFingerprint(projected.state(0))==fingerprint
            && test::oocStateFingerprint(pendingGold)==fingerprint && t_curPath==savedPath,
            "pending reward projection matches resolved oracle and preserves caller");
    }
    // All pending screen families are evaluated only after the same policy
    // continuation. This also covers selectors outside MCTS-owned decisions.
    for (int family=0;family<5;++family) {
        auto pending=detachedCopy(gc);
        if (family==0) { pending.screenState=ScreenState::SHOP_ROOM; pending.info.shop.setup(pending); }
        if (family==1) { pending.screenState=ScreenState::EVENT_SCREEN; pending.curEvent=Event::BIG_FISH;
            pending.info.hpAmount0=20; pending.info.hpAmount1=5; }
        if (family==2) pending.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        if (family==3) pending.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        if (family==4) pending=detachedCopy(reward);
        const auto beforePending=test::oocStateFingerprint(pending);
        auto completed=detachedCopy(pending);
        PathHistory completedPath=path; completedPath.update(completed);
        const auto previousPath=t_curPath; t_curPath=&completedPath;
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<64 && completed.screenState!=ScreenState::MAP_SCREEN;++step) {
            runFullRunOocPolicyStep(completed,oracleAgent,false,true); completedPath.update(completed);
        }
        require(completed.screenState==ScreenState::MAP_SCREEN,"pending screen oracle reaches checkpoint");
        const double expectedValue=vStateWinNative(completed); t_curPath=previousPath;
        OocGameContextModel projected(pending,path,{}, {true});
        int observerCalls=0;
        auto savedObserver=std::move(sts::search::g_onGameActionExecute);
        sts::search::g_onGameActionExecute=[&](std::uint32_t,const GameContext *) { ++observerCalls; };
        t_oocStrategicTraceRows="live trace sentinel";
        const auto savedRows=t_oocStrategicTraceRows;
        std::mt19937_64 projectionRng(543);
        require(projected.evaluateLeaf(0,projectionRng)==expectedValue
            && test::oocStateFingerprint(pending)==beforePending && observerCalls==0
            && t_oocStrategicTraceRows==savedRows && t_curPath==previousPath,
            "pending screen projection matches oracle without live observer or bookkeeping mutation");
        sts::search::g_onGameActionExecute=std::move(savedObserver);
        t_oocStrategicTraceRows.clear();
    }
    // Controlled map fixtures prove horizon counting without native combat/search.
    struct HorizonSampler final : CombatTransitionSampler {
        mutable unsigned calls = 0;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            ++calls;
            return {CombatRuntimeSample::Outcome::VICTORY,captureCombatTransitionState(g)};
        }
    };
    for (unsigned horizon : {1u,3u}) {
        auto horizonRoot = detachedCopy(gc);
        for (auto &row : horizonRoot.map->nodes) for (auto &node : row) node.room = Room::MONSTER;
        auto sampler = std::make_shared<HorizonSampler>();
        OocAdapterOptions opts{true}; opts.leafCombats = horizon; opts.constantLeaf = true; opts.uniformLeafPolicy = true;
        OocGameContextModel projected(horizonRoot,path,sampler,opts);
        std::mt19937_64 projectionRng(912);
        const auto before = test::oocStateFingerprint(horizonRoot);
        require(projected.evaluateLeaf(0,projectionRng) == .5 && sampler->calls == horizon
            && projected.continuationMetrics().imaginedCombats == horizon
            && projected.continuationMetrics().projectionSteps >= horizon*2
            && test::oocStateFingerprint(horizonRoot) == before,
            "uniform continuation completes exact additional combat horizon and preserves root");
    }
    {
        // Inject the bounded-continuation exception after a genuine successful
        // adapter surrogate draw; isolate root-abort accounting from native exits.
        auto root=detachedCopy(gc);
        for (auto &row : root.map->nodes) for (auto &node : row) node.room=Room::MONSTER;
        auto sampler=std::make_shared<HorizonSampler>();
        OocGameContextModel adapter(root,path,sampler,{true});
        struct BoundModel final : OocGenerativeModel {
            OocGameContextModel &adapter;
            explicit BoundModel(OocGameContextModel &a):adapter(a) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override { return adapter.sampleSuccessor(id,a,r); }
            double leafValue(OocStateId) const override { throw OocSearchUnsupported("continuation_step_limit_1024"); }
        } bounded(adapter);
        OocMctsConfig config; config.maxDepth=1;
        const auto result=OocMctsPlanner(config).search(bounded,0,1);
        auto counters=adapter.continuationMetrics();
        recordSearchAbort(result,counters);
        const auto samples=adapter.combatSamples();
        require(result.aborted && !result.selectedAction && result.rootActions.empty()
            && result.abortReason=="continuation_step_limit_1024"
            && counters.continuationLimitAborts==1
            && counters.continuationReasons.at(result.abortReason)==1
            && counters.unsupportedCombats==0 && counters.supportReasons.empty()
            && counters.imaginedCombats==samples && samples==1 && sampler->calls==1,
            "continuation limit abort preserves honest successful combat and separate reason accounting");
    }
    {
        auto pending = detachedCopy(gc); pending.screenState = ScreenState::EVENT_SCREEN;
        pending.curEvent = Event::BIG_FISH; pending.info.hpAmount0 = 20; pending.info.hpAmount1 = 5;
        auto oracle = detachedCopy(pending);
        std::mt19937_64 oracleRng(919), projectionRng(919);
        oracleRng(); // Existing continuation agent seeding consumes one search draw.
        const auto actions = v4CandidateActions(oracle);
        require(v4DecisionSupported(oracle) && actions.size() > 1, "uniform event fixture legal alternatives");
        actions[std::uniform_int_distribution<std::size_t>(0,actions.size()-1)(oracleRng)].execute(oracle);
        ScumSearchAgent2 oracleAgent;
        for (int step=0; step<64 && oracle.screenState != ScreenState::MAP_SCREEN; ++step)
            runFullRunOocPolicyStep(oracle,oracleAgent,false,true);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        const auto previousPath=t_curPath; t_curPath=&oraclePath;
        const double expected=vStateWinNative(oracle); t_curPath=previousPath;
        OocAdapterOptions opts{true}; opts.uniformLeafPolicy=true;
        OocGameContextModel projected(pending,path,{},opts);
        require(projected.evaluateLeaf(0,projectionRng)==expected,
            "uniform supported decision executes correct primitive and resolves checkpoint");
    }
    // A single unsupported combat invalidates the entire root; never choose
    // from partial Q, assign a scalar penalty, or call a real combat backend.
    fake->enabled=false;
    OocGameContextModel unsupportedRoot(combatRoot,path,fake,{true});
    const auto unsupportedBefore=test::oocStateFingerprint(unsupportedRoot.state(0));
    const auto samplesBeforeAbort=fake->sampleCalls;
    std::mt19937_64 adapterRng(77), untouchedRng(77);
    rejects([&] { unsupportedRoot.sampleSuccessor(0,restAction.bits,adapterRng); });
    require(unsupportedRoot.continuationMetrics().imaginedCombats==1
        && unsupportedRoot.continuationMetrics().unsupportedCombats==1
        && unsupportedRoot.continuationMetrics().supportReasons.at("fake unsupported")==1
        && fake->sampleCalls==samplesBeforeAbort && adapterRng==untouchedRng
        && test::oocStateFingerprint(unsupportedRoot.state(0))==unsupportedBefore,
        "unsupported input aborts before any draw/combat/value and preserves root");
    OocGameContextModel unsupportedPlanner(combatRoot,path,fake,{true});
    SingleEntryModel unsupportedEntry(unsupportedPlanner,restAction.bits);
    const auto aborted=OocMctsPlanner().search(unsupportedEntry,0,128);
    require(aborted.aborted && !aborted.selectedAction && aborted.rootActions.empty()
        && aborted.metrics.simulations==0 && aborted.metrics.simulationAttempts==1
        && aborted.abortReason=="fake unsupported","unsupported root returns no partial action with counted attempt");
    // A surprise UNSUPPORTED sample uses the same whole-root contract.
    struct UnsupportedDraw final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override { return {}; }
    };
    OocGameContextModel unsupportedDraw(combatRoot,path,std::make_shared<UnsupportedDraw>(),{true});
    SingleEntryModel unsupportedDrawEntry(unsupportedDraw,restAction.bits);
    const auto abortedDraw=OocMctsPlanner().search(unsupportedDrawEntry,0,128);
    require(abortedDraw.aborted && !abortedDraw.selectedAction
        && unsupportedDraw.continuationMetrics().supportReasons.at("sample_returned_unsupported")==1,
        "unsupported sample cannot escape into a BATTLE scalar leaf");
    // Even an optional configured leaf policy cannot bypass the surrogate.
    const bool beforeDisallow=sts::search::g_disallowImaginedCombat;
    {
        ImaginedScope scope;
        ScumSearchAgent2 forbiddenAgent; BattleContext forbiddenBattle;
        auto detachedBattle=detachedCopy(battle);
        rejects([&] { forbiddenAgent.playoutBattle(detachedBattle,forbiddenBattle); });
        rejects([&] { forbiddenAgent.playoutBattle(forbiddenBattle); });
    }
    require(sts::search::g_disallowImaginedCombat==beforeDisallow,"surrogate-only guard restores real combat permission");
    OocGameContextModel deterministicOoc(ordinary,path,{}, {true});
    const auto deterministicId=deterministicOoc.sampleSuccessor(0,ordinaryAction.bits,adapterRng);
    const auto rngBeforeCache=adapterRng;
    require(deterministicOoc.isDeterministicTransition(0,ordinaryAction.bits)
        && deterministicOoc.sampleSuccessor(0,ordinaryAction.bits,adapterRng)==deterministicId
        && adapterRng==rngBeforeCache,"deterministic OOC child reused without RNG draw");
    std::cout << "corrected_continuations reward_oracle=exact unsupported_root=V4 unsupported_sample=V4 native_imagination=forbidden deterministic_reuse=exact\n";
    // No fallback even if availability changes after construction.
    bool policyOk=g_oocStrategicTokNet.ok; g_oocStrategicTokNet.ok=false;
    rejects([&] { OocGameContextModel unavailable(gc,path); });
    g_oocStrategicTokNet.ok=policyOk;
    // Exercise the same live dispatch seam with a stateless lethal imagined
    // sampler. Every selected first-row map action must leave live combat pending.
    struct ImaginedDeath final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {true, "test supported"};
        }
        CombatRuntimeSample sample(const GameContext &, const CombatPredictorInputV1 &,
                                   std::mt19937_64 &) const override {
            return {CombatRuntimeSample::Outcome::DEATH, {}};
        }
    };
    struct LiveConfigScope {
        bool enabled = liveEnabled;
        std::uint64_t simulations = liveSimulations;
        std::shared_ptr<const CombatTransitionSampler> sampler = liveSampler;
        ~LiveConfigScope() { liveEnabled=enabled; liveSimulations=simulations; liveSampler=sampler; }
    } liveScope;
    auto live=GameContext(CharacterClass::IRONCLAD, 42, 0);
    live.screenState=ScreenState::MAP_SCREEN;
    live.curEvent=Event::INVALID;
    live.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    for (auto &node : live.map->nodes[0]) node.room=Room::MONSTER;
    PathHistory livePath; livePath.update(live);
    const auto before=test::oocStateFingerprint(live);
    const auto beforePath=livePath;
    LiveOocMctsMetrics offMetrics;
    liveEnabled=false; liveSampler.reset();
    require(!oocMctsPolicyStep(live,livePath,42,7,offMetrics)
        && offMetrics.decisions==1 && offMetrics.search.simulations==0
        && test::oocStateFingerprint(live)==before, "OFF dispatch has no search/model/RNG use");
    struct AlwaysUnsupported final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {false,"test unsupported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            throw std::runtime_error("unsupported sampler must not draw");
        }
    };
    liveEnabled=true; liveSimulations=128; liveSampler=std::make_shared<AlwaysUnsupported>();
    LiveOocMctsMetrics unsupportedMetrics;
    require(!oocMctsPolicyStep(live,livePath,42,7,unsupportedMetrics)
        && unsupportedMetrics.fallback==1 && unsupportedMetrics.supportAborts==1
        && unsupportedMetrics.owned==0 && unsupportedMetrics.search.simulationAttempts==1
        && unsupportedMetrics.search.simulations==0 && unsupportedMetrics.continuation.unsupportedCombats==1
        && unsupportedMetrics.continuation.supportReasons.at("test unsupported")==1
        && test::oocStateFingerprint(live)==before && !sts::search::g_disallowImaginedCombat,
        "unsupported live search returns untouched decision to existing V4 with reconciled abort metrics");
    auto sole=detachedCopy(live);
    int firstNode=-1;
    for (auto &node : sole.map->nodes[0]) {
        if (firstNode < 0 && node.edgeCount > 0) firstNode=node.x;
        else node.edgeCount=0;
    }
    PathHistory solePath; solePath.update(sole);
    const auto soleCandidates=v4CandidateActions(sole);
    require(soleCandidates.size()==1,"sole map candidate fixture");
    OocGameContextModel soleModel(sole,solePath,liveSampler,liveOptions);
    const auto soleSearch=OocMctsPlanner(liveConfig).search(soleModel,0,128);
    require(soleSearch.aborted && soleSearch.metrics.simulationAttempts==1,
        "normal sole-action search aborts after entering unsupported combat");
    auto solePrimitive=detachedCopy(sole), soleFallback=detachedCopy(sole);
    soleCandidates.front().execute(solePrimitive);
    ScumSearchAgent2 soleAgent;
    runFullRunOocPolicyStep(soleFallback,soleAgent,false,true);
    require(test::oocStateFingerprint(soleFallback)==test::oocStateFingerprint(solePrimitive),
        "sole candidate equals original whole-root fallback primitive including live RNG");
    LiveOocMctsMetrics soleMetrics;
    const auto soleBefore=test::oocStateFingerprint(sole);
    require(!oocMctsPolicyStep(sole,solePath,42,7,soleMetrics)
        && soleMetrics.search.trivialRootBypasses==0 && soleMetrics.search.simulations==0
        && soleMetrics.search.simulationAttempts==1 && soleMetrics.combatSamples==0
        && soleMetrics.supportAborts==1 && soleMetrics.fallback==1
        && test::oocStateFingerprint(sole)==soleBefore,
        "abort-capable sole map root searches and returns untouched state to fallback");

    // Wheel has one legal primitive, but its existing fallback calls stepRandom:
    // choosing from a singleton still advances ScumSearchAgent2::rng.
    auto wheel=detachedCopy(sole);
    wheel.screenState=ScreenState::EVENT_SCREEN; wheel.curEvent=Event::WHEEL_OF_CHANGE;
    for (unsigned wheelSeed=0;wheelSeed<128;++wheelSeed) {
        wheel.miscRng=Random(wheelSeed);
        auto probe=wheel.miscRng;
        if (probe.random(5)==0) break; // gold, then the normal map callback
    }
    auto wheelRoll=wheel.miscRng;
    require(wheelRoll.random(5)==0,"wheel fixture deterministic gold outcome");
    PathHistory wheelPath; wheelPath.update(wheel);
    const auto wheelCandidates=v4CandidateActions(wheel);
    require(wheelCandidates.size()==1,"sole wheel candidate fixture");
    const auto savedEarlyStop=liveConfig.allowUnqualifiedRootStop;
    liveConfig.allowUnqualifiedRootStop=false; // Verify rollback preserves legacy fallback/RNG.
    OocGameContextModel wheelModel(wheel,wheelPath,liveSampler,liveOptions);
    const auto wheelSearch=OocMctsPlanner(liveConfig).search(wheelModel,0,128);
    require(!wheelModel.searchGuaranteedNonAborting() && wheelSearch.aborted
        && wheelSearch.metrics.simulationAttempts>0,
        "old sole wheel search reaches unsupported combat and aborts");
    auto wheelPrimitive=detachedCopy(wheel), wheelOracle=detachedCopy(wheel);
    wheelCandidates.front().execute(wheelPrimitive);
    ScumSearchAgent2 wheelAgent, wheelOracleAgent;
    wheelAgent.rng.seed(20260914); wheelOracleAgent.rng=wheelAgent.rng;
    const auto agentBefore=wheelAgent.rng;
    runFullRunOocPolicyStep(wheelOracle,wheelOracleAgent,false,true);
    require(wheelOracleAgent.rng!=agentBefore
        && test::oocStateFingerprint(wheelOracle)==test::oocStateFingerprint(wheelPrimitive),
        "same sole wheel primitive hides a fallback agent RNG draw");
    const auto wheelBefore=test::oocStateFingerprint(wheel);
    LiveOocMctsMetrics wheelMetrics;
    require(!oocMctsPolicyStep(wheel,wheelPath,42,7,wheelMetrics)
        && wheelMetrics.search.trivialRootBypasses==0 && wheelMetrics.supportAborts==1
        && wheelMetrics.fallback==1 && wheelMetrics.search.simulationAttempts>0
        && wheelAgent.rng==agentBefore && test::oocStateFingerprint(wheel)==wheelBefore,
        "unsafe sole wheel root cannot skip abort and RNG-consuming fallback");
    runFullRunOocPolicyStep(wheel,wheelAgent,false,true);
    require(wheelAgent.rng==wheelOracleAgent.rng && wheelAgent.rng!=agentBefore
        && test::oocStateFingerprint(wheel)==test::oocStateFingerprint(wheelOracle),
        "unsafe sole wheel dispatch preserves ordered fallback state and agent RNG");
    liveConfig.allowUnqualifiedRootStop=savedEarlyStop;
    struct QualifiedSoleRoot final : OocGenerativeModel {
        bool searchGuaranteedNonAborting() const override { return true; }
        std::optional<double> terminalValue(OocStateId) const override { return {}; }
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{7,1}}; }
        OocStateId sampleSuccessor(OocStateId,OocActionId,std::mt19937_64 &) override { ++draws; return 1; }
        double leafValue(OocStateId) const override { return .5; }
        unsigned draws=0;
    } qualifiedSole;
    const auto qualifiedBypass=searchWithSoleRootShortcut(qualifiedSole,liveConfig,7,128);
    require(qualifiedSole.searchGuaranteedNonAborting() && qualifiedBypass.selectedAction==7
        && qualifiedBypass.metrics.trivialRootBypasses==1 && qualifiedBypass.metrics.simulations==0
        && qualifiedBypass.metrics.simulationAttempts==0 && qualifiedSole.draws==0,
        "explicitly non-aborting sole model remains eligible for zero-simulation bypass");
    auto fallbackLive=detachedCopy(live), fallbackOracle=detachedCopy(live);
    ScumSearchAgent2 fallbackLiveAgent,fallbackOracleAgent;
    runFullRunOocPolicyStep(fallbackLive,fallbackLiveAgent,false,true);
    runFullRunOocPolicyStep(fallbackOracle,fallbackOracleAgent,false,true);
    require(test::oocStateFingerprint(fallbackLive)==test::oocStateFingerprint(fallbackOracle),
        "unsupported combat root uses unchanged V4 fallback primitive");
    auto lethal=std::make_shared<ImaginedDeath>();
    std::uint64_t firstSamples=0, repeatedSamples=0;
    const auto first=selectOocMctsAction(live,livePath,42,7,128,lethal,firstSamples);
    const auto second=selectOocMctsAction(live,livePath,42,7,128,lethal,repeatedSamples);
    require(test::oocStateFingerprint(live)==before
        && livePath.roomVisits==beforePath.roomVisits && livePath.lastNodeKey==beforePath.lastNodeKey,
        "live search isolates whole GameContext/map/RNG/PathHistory");
    require(first.selectedAction && first.selectedAction==second.selectedAction
        && firstSamples>0 && firstSamples==repeatedSamples
        && first.rootActions.size()==second.rootActions.size(), "deterministic live selection/samples");
    for (std::size_t i=0;i<first.rootActions.size();++i) {
        const auto &a=first.rootActions[i], &b=second.rootActions[i];
        require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
            "deterministic live root statistics");
    }
    require(oocMctsSearchSeed(42,7)==oocMctsSearchSeed(42,7)
        && oocMctsSearchSeed(42,7)!=oocMctsSearchSeed(42,8), "stable indexed search RNG");
    auto liveExpected=detachedCopy(live);
    const auto liveCandidates=v4CandidateActions(liveExpected);
    const auto selected=std::find_if(liveCandidates.begin(),liveCandidates.end(),
        [&](auto a) { return a.bits==*first.selectedAction; });
    require(selected!=liveCandidates.end(), "selected live candidate exists");
    selected->execute(liveExpected);
    liveEnabled=true; liveSimulations=128; liveSampler=lethal;
    LiveOocMctsMetrics liveMetrics;
    require(oocMctsPolicyStep(live,livePath,42,7,liveMetrics)
        && test::oocStateFingerprint(live)==test::oocStateFingerprint(liveExpected),
        "live execution exactly one primitive, no imagined successor transfer");
    require(live.screenState==ScreenState::BATTLE && live.outcome==GameOutcome::UNDECIDED
        && liveMetrics.combatSamples>0 && liveMetrics.owned==1
        && liveMetrics.decisions==1 && liveMetrics.fallback==0
        && liveMetrics.search.simulations==128, "real combat remains pending despite imagined death");
    // Real battle entry dispatches ordinary BattleContext initialization.
    BattleContext pending; pending.init(live);
    require(pending.outcome==Outcome::UNDECIDED && pending.player.curHp==live.curHp,
        "ordinary real battle initializes after selected action");
    auto uncovered=GameContext(CharacterClass::IRONCLAD,42,0);
    uncovered.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    uncovered.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
    const auto uncoveredBefore=test::oocStateFingerprint(uncovered);
    auto fallbackExpected=detachedCopy(uncovered);
    LiveOocMctsMetrics fallbackMetrics;
    require(!oocMctsPolicyStep(uncovered,livePath,42,8,fallbackMetrics)
        && fallbackMetrics.fallback==1 && fallbackMetrics.owned==0
        && fallbackMetrics.search.simulations==0
        && test::oocStateFingerprint(uncovered)==uncoveredBefore, "unsupported live root falls back unchanged");
    ScumSearchAgent2 fallbackAgent, expectedAgent;
    runFullRunOocPolicyStep(uncovered,fallbackAgent,false,true);
    runFullRunOocPolicyStep(fallbackExpected,expectedAgent,false,true);
    require(test::oocStateFingerprint(uncovered)==test::oocStateFingerprint(fallbackExpected),
        "unsupported root uses identical existing policy chain");
    auto multipleGold=detachedCopy(reward);
    multipleGold.info.rewardsContainer.goldRewardCount=2;
    multipleGold.info.rewardsContainer.gold[0]=12;
    multipleGold.info.rewardsContainer.gold[1]=13;
    OocGameContextModel duplicateRoot(multipleGold,livePath,lethal);
    require(duplicateRoot.isLeafBoundary(0), "duplicate native gold IDs are a boundary");
    auto goldExpected=detachedCopy(multipleGold);
    LiveOocMctsMetrics goldMetrics;
    require(!oocMctsPolicyStep(multipleGold,livePath,42,9,goldMetrics)
        && goldMetrics.fallback==1 && goldMetrics.search.simulations==0,
        "multi-gold root uses fallback without searching/deduplicating");
    runFullRunOocPolicyStep(multipleGold,fallbackAgent,false,true);
    runFullRunOocPolicyStep(goldExpected,expectedAgent,false,true);
    require(test::oocStateFingerprint(multipleGold)==test::oocStateFingerprint(goldExpected)
        && multipleGold.info.rewardsContainer.goldRewardCount==1,
        "multi-gold fallback retains existing first-gold collection");
    std::cout<<"PASS live OOC MCTS OFF/isolation/execution/real-combat/fallback/determinism\n";
    // Opt-in captured-model microbenchmark. Runs only detached search states;
    // this is not a gameplay cohort or a decision-quality experiment.
    if (const char *modelPath=std::getenv("STS_OOC_MCTS_MICROBENCH_MODEL")) {
        auto native=std::make_shared<NativeCombatTransitionSampler>(modelPath);
        struct ReferenceSampler final : CombatTransitionSampler {
            std::shared_ptr<const NativeCombatTransitionSampler> native;
            mutable std::uint64_t encoderCalls=0;
            explicit ReferenceSampler(std::shared_ptr<const NativeCombatTransitionSampler> n):native(std::move(n)) {}
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &p) const override {
                return native->support(g,p);
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &p,std::mt19937_64 &r) const override {
                auto result=native->sample(g,p,r);
                if (result.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED)
                    encoderCalls+=result.outcome==CombatRuntimeSample::Outcome::VICTORY ? 4 : 1;
                return result;
            }
        };
        auto reference=std::make_shared<ReferenceSampler>(native);
        GameContext fixed(CharacterClass::IRONCLAD,42,0);
        fixed.screenState=ScreenState::MAP_SCREEN; fixed.curEvent=Event::INVALID;
        for (auto &node : fixed.map->nodes[0]) node.room=Room::MONSTER;
        // Isolate one searched combat edge from native reward/projection work.
        fixed.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
        PathHistory fixedPath;fixedPath.update(fixed);
        OocAdapterOptions opts; opts.checkpointLeaves=true;
        OocGameContextModel before(fixed,fixedPath,reference,opts),after(fixed,fixedPath,native,opts);
        auto cfg=OocMctsConfig{}; cfg.seed=20260914;cfg.maxDepth=1;
        const auto start=std::chrono::steady_clock::now();
        const auto oldResult=OocMctsPlanner(cfg).search(before,0,512);
        const double oldSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        const auto next=std::chrono::steady_clock::now();
        const auto newResult=OocMctsPlanner(cfg).search(after,0,512);
        const double newSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-next).count();
        require(!oldResult.aborted && !newResult.aborted,"fixed native microbenchmark support");
        require(oldResult.selectedAction==newResult.selectedAction && before.storedStates()==after.storedStates()
            && before.combatSamples()==after.combatSamples(),"prepared search action/state/sample parity");
        const auto &a=oldResult.metrics,&b=newResult.metrics;
        require(a.simulations==b.simulations && a.simulationAttempts==b.simulationAttempts
            && a.decisionNodes==b.decisionNodes && a.chanceNodes==b.chanceNodes
            && a.outcomeParticles==b.outcomeParticles && a.transitionSamples==b.transitionSamples
            && a.leafEvaluations==b.leafEvaluations && a.particleRevisits==b.particleRevisits
            && a.deterministicRevisits==b.deterministicRevisits && a.depthSum==b.depthSum
            && a.maxDepthReached==b.maxDepthReached,"prepared complete tree metrics parity");
        for (std::size_t i=0;i<oldResult.rootActions.size();++i) {
            const auto &x=oldResult.rootActions[i],&y=newResult.rootActions.at(i);
            require(x.id==y.id && x.prior==y.prior && x.visits==y.visits && x.q==y.q,
                "prepared root IDs/order/priors/visits/Q parity");
        }
        for (std::size_t i=0;i<before.storedStates();++i)
            require(test::oocStateFingerprint(before.state(i))==test::oocStateFingerprint(after.state(i))
                && before.pathHistory(i).roomVisits==after.pathHistory(i).roomVisits
                && before.pathHistory(i).lastNodeKey==after.pathHistory(i).lastNodeKey,
                "every prepared search snapshot and PathHistory exact");
        nlohmann::json exact={{"selectedAction",*newResult.selectedAction},
            {"simulations",b.simulations},{"simulationAttempts",b.simulationAttempts},
            {"decisionNodes",b.decisionNodes},{"chanceNodes",b.chanceNodes},
            {"outcomeParticles",b.outcomeParticles},{"transitionSamples",b.transitionSamples},
            {"leafEvaluations",b.leafEvaluations},{"particleRevisits",b.particleRevisits},
            {"deterministicRevisits",b.deterministicRevisits},{"depthSum",b.depthSum},
            {"maxDepthReached",b.maxDepthReached}};
        for (auto action:newResult.rootActions)
            exact["rootActions"].push_back({action.id,action.prior,action.visits,action.q});
        for (std::size_t i=0;i<after.storedStates();++i)
            exact["states"].push_back({test::oocStateFingerprint(after.state(i)),
                after.pathHistory(i).roomVisits,after.pathHistory(i).lastNodeKey});
        std::cout<<"MICROBENCH_PARITY "<<exact.dump()<<'\n';
        std::cout<<"MICROBENCH "<<nlohmann::json{{"simulations",512},{"referenceSeconds",oldSeconds},
            {"preparedSeconds",newSeconds},{"referenceSimulationsPerSecond",512/oldSeconds},
            {"preparedSimulationsPerSecond",512/newSeconds},{"combatSamples",after.combatSamples()},
            {"referenceCombatSamplesPerSecond",before.combatSamples()/oldSeconds},
            {"preparedCombatSamplesPerSecond",after.combatSamples()/newSeconds},
            {"referenceEncoderCalls",reference->encoderCalls},
            {"preparedEncoderCalls",4*after.continuationMetrics().preparedCombats},
            {"uniqueCombatEdges",after.continuationMetrics().preparedCombats},
            {"generatedStates",after.storedStates()},{"decisionNodes",b.decisionNodes},
            {"metadataBuilds",after.continuationMetrics().metadataBuilds},
            {"priorBuilds",after.continuationMetrics().priorBuilds},{"parity",true}}.dump()<<'\n';
    }
    std::cout<<"PASS OOC MCTS adapter (offline native integration only)\n";
}
}
