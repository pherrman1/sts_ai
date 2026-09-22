#include "advisor_protocol.h"
#include "live_ooc_importer.h"
#include "live_ooc_state.h"
#include "live_ooc_policy.h"
#include "ooc_v4_encoding.h"
#include "../ooc_strategic_tok_net.h"
#include <fstream>
#include <iomanip>
#include <sstream>
#include "combat_transition_runtime.h"
#include "live_silver_importer.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"

#include <iostream>
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <string>
#include <chrono>
#include <memory>

using nlohmann::json;

namespace {
// Content fingerprint is diagnostic identity, not an artifact trust decision.
std::string modelIdentity(const std::string &path) {
    std::ifstream stream(path, std::ios::binary);
    std::uint64_t hash = 14695981039346656037ULL;
    char byte;
    while (stream.get(byte)) { hash ^= static_cast<unsigned char>(byte); hash *= 1099511628211ULL; }
    if (!stream.eof()) return "unavailable";
    std::ostringstream out; out << "fnv1a64:" << std::hex << std::setw(16) << std::setfill('0') << hash;
    return out.str();
}
std::uint64_t stableHash(const std::string &value) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const unsigned char byte : value) { hash ^= byte; hash *= 1099511628211ULL; }
    return hash;
}
struct PendingCompoundPlan {
    bool active = false;
    std::string session;
    std::int64_t sequence = 0;
    int selectorType = 0;
    std::string selectorName;
    json card;
};

int keyInteger(const std::string &key, const char *field) {
    const std::string prefix = std::string(field) + "=";
    const auto start = key.find(prefix);
    if (start == std::string::npos) return -1;
    const auto valueStart = start + prefix.size();
    const auto end = key.find(':', valueStart);
    try { return std::stoi(key.substr(valueStart, end - valueStart)); }
    catch (...) { return -1; }
}

PendingCompoundPlan pendingCompoundPlan(const one_combat::advisor::Request &request,
                                        const json &selected) {
    PendingCompoundPlan plan;
    const auto targetType = selected.value("type", std::string());
    if (targetType != "transaction" && targetType != "deck_card"
            && !selected.contains("compoundTarget")) return plan;
    const auto source = keyInteger(selected.value("semanticKey", std::string()), "source");
    const auto effect = keyInteger(selected.value("semanticKey", std::string()), "effect");
    // These are the only public source primitives whose semantic enumeration
    // expands to a deterministic single-card selector. The numeric selector
    // IDs are the append-only native CardSelectScreenType wire values.
    if (source == 0) { plan.selectorType = 3; plan.selectorName = "upgrade"; }
    else if (source == 2 || source == 4) { plan.selectorType = 4; plan.selectorName = "remove"; }
    else if (source == 5 && effect == 0) { plan.selectorType = 3; plan.selectorName = "upgrade"; }
    else if (source == 5 && effect == 1) { plan.selectorType = 4; plan.selectorName = "remove"; }
    else if (source == 5 && effect == 2) { plan.selectorType = 1; plan.selectorName = "transform"; }
    else if (source == 5 && effect == 3) { plan.selectorType = 2; plan.selectorName = "transform_upgrade"; }
    else return plan;
    const auto &target = selected.contains("compoundTarget")
        ? selected.at("compoundTarget") : selected.at("card");
    if (!target.is_object()) return PendingCompoundPlan{};
    plan.active = true;
    plan.session = request.session;
    plan.sequence = request.sequence;
    plan.card = target;
    return plan;
}

bool sameCardTarget(const json &candidate, int selectorType, const json &target) {
    if (candidate.value("type", std::string()) != "selector") return false;
    if (candidate.value("selectorType", -1) != selectorType) return false;
    const auto &candidateTarget = candidate.value("target", json::object());
    if (candidateTarget.value("type", std::string()) != "deck_card") return false;
    const auto &card = candidateTarget.value("card", json::object());
    for (const char *field : {"id", "misc", "upgraded", "bottle", "occurrence"})
        if (!card.contains(field) || !target.contains(field) || card.at(field) != target.at(field)) return false;
    return true;
}

one_combat::LiveOocDecision retainedCompoundDecision(
        const one_combat::advisor::LiveOocStateV1 &state,
        const PendingCompoundPlan &pending) {
    one_combat::LiveOocDecision result;
    result.policy = "mcts_ctm";
    const auto bindings = sts::search::enumerateOocSemanticPrimitiveBindings(state.projected);
    if (!bindings.supported || !bindings.complete) {
        result.reason = "SEMANTIC_ENUMERATION_UNSUPPORTED:" + bindings.error;
        return result;
    }
    const double prior = bindings.bindings.empty()
        ? 0.0 : 1.0 / static_cast<double>(bindings.bindings.size());
    int matches = 0;
    for (const auto &binding : bindings.bindings) {
        const auto payload = json::parse(sts::search::oocSemanticActionPayloadJson(binding.semantic));
        result.candidates.push_back({
            sts::search::canonicalOocSemanticActionKey(binding.semantic), payload.dump(),
            binding.primitiveBits, 0.0, 0, 0.0, prior});
        if (sameCardTarget(payload, pending.selectorType, pending.card)) {
            ++matches;
            result.selectedIndex = static_cast<int>(result.candidates.size()) - 1;
        }
    }
    if (matches != 1) {
        result.candidates.clear();
        result.selectedIndex = -1;
        result.reason = "COMPOUND_TARGET_UNAVAILABLE:" + pending.selectorName;
        return result;
    }
    // This is the retained source transaction's target, not a new selector
    // search. Give the client a coherent one-candidate visit distribution so
    // the selected target and the reported MCTS statistics cannot disagree.
    auto &selected = result.candidates.at(result.selectedIndex);
    selected.visits = 1;
    selected.visitShare = 1.0;
    result.supported = true;
    return result;
}

void validateCapturedLiveOocMapping(const one_combat::advisor::LiveOocStateV1 &state) {
    std::vector<std::uint32_t> expected;
    // Rewards can contain simulator-only synthetic card-skip primitives for
    // groups that Java does not expose as live choices. For those screens the
    // observed primitive set is the source boundary; other screens have an
    // exact native candidate set that can detect missing mappings as well as
    // duplicate ones before policy/model fallback.
    if (state.projected.screenState == sts::ScreenState::REWARDS) {
        expected = one_combat::advisor::liveOocPrimitiveBits(state);
    } else {
        for (const auto &action : one_combat::v4CandidateActions(state.projected))
            if (action.isValidAction(state.projected)) expected.push_back(action.bits);
    }
    if (expected.empty()) return;
    one_combat::advisor::validateLiveOocActionSet(state, expected);
}

std::size_t oocTreeNodeCap() {
    const char *value = std::getenv("STS_OOC_DEBUG_TREE_NODE_CAP");
    if (!value || !*value) return 4096;
    for (const char *p = value; *p; ++p) if (*p < '0' || *p > '9') return 4096;
    char *end = nullptr;
    errno = 0;
    const auto parsed = std::strtoull(value, &end, 10);
    if (errno == ERANGE || end == value || *end || !parsed) return 4096;
    return static_cast<std::size_t>(std::min<unsigned long long>(parsed, 100000));
}

json oocResponse(const one_combat::advisor::Request &request,
                 one_combat::LiveOocPolicy &policy, const std::string &identity,
                 PendingCompoundPlan &pending) {
    using namespace one_combat;
    const auto started = std::chrono::steady_clock::now();
    json evaluator = {{"id", "live_ooc_decision_v1"}, {"scope", "ooc_decision"},
                      {"policy", policy.name()}, {"status", "UNSUPPORTED"}};
    advisor::LiveOocStateV1 state;
    const auto imported = advisor::importLiveOocStateV1(request.observation, state);
    if (!imported.ok && imported.code != "UNSUPPORTED")
        return advisor::errorResponse(request, imported.code, imported.message);
    if (!imported.ok) evaluator["reason"] = imported.message;
    else {
        // After choosing a boss relic, vanilla can expose the already-open
        // boss chest as a completed room with only the native Proceed button.
        // The simulator's TREASURE_ROOM action set describes the pre-open
        // state, so it is not a valid mapping for this observed pass-through.
        // Preserve the one legal live action without scoring hypothetical
        // open/skip actions.
        const auto &ooc = state.ooc;
        const bool openedPassThrough = state.projected.screenState == sts::ScreenState::TREASURE_ROOM
            && ooc.contains("details") && ooc.at("details").is_object()
            && ooc.at("details").value("opened", false)
            && ooc.contains("liveChoices") && ooc.at("liveChoices").is_array()
            && ooc.at("liveChoices").size() == 1
            && ooc.at("liveChoices").at(0).contains("liveAction")
            && ooc.at("liveChoices").at(0).at("liveAction").value("kind", std::string()) == "proceed";
        if (openedPassThrough) {
            const auto liveAction = ooc.at("liveChoices").at(0).at("liveAction");
            evaluator["status"] = "OK";
            evaluator["mode"] = "native_pass_through";
            evaluator["selectedSemanticKey"] = "ooc-live:v1:pass-through";
            evaluator["selectedLabel"] = "proceed";
            evaluator["selectedLiveAction"] = liveAction;
            evaluator["candidateSummaries"] = json::array({json{
                {"semanticKey", "ooc-live:v1:pass-through"},
                {"semanticPayload", json{{"type", "pass_through"}}},
                {"label", "proceed"}, {"q", 0.0}, {"visits", 1},
                {"visitShare", 1.0}, {"prior", 1.0},
                {"liveAction", liveAction}}});
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        if (const auto forcedGold = advisor::forcedRewardGoldPrimitive(state)) {
            const auto liveAction = advisor::lowerLiveOocAction(state, *forcedGold);
            evaluator["status"] = "OK";
            evaluator["mode"] = "native_pass_through";
            evaluator["selectedSemanticKey"] = "ooc-live:v1:take-gold";
            evaluator["selectedLabel"] = "collect gold";
            evaluator["selectedLiveAction"] = liveAction;
            evaluator["candidateSummaries"] = json::array({json{
                {"semanticKey", "ooc-live:v1:take-gold"},
                {"semanticPayload", json{{"type", "take_gold"}}},
                {"label", "collect gold"}, {"q", 0.0}, {"visits", 1},
                {"visitShare", 1.0}, {"prior", 1.0},
                {"liveAction", liveAction}}});
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        try {
            validateCapturedLiveOocMapping(state);
            policy.setRootPrimitiveBits(advisor::liveOocPrimitiveBits(state));
            policy.setRewardPityHistoryComplete(state.rewardPityHistoryComplete);
            const char *treeEnv = std::getenv("STS_OOC_DEBUG_TREE");
            policy.setTreeCapture(request.observation.value("oocDebugTree", false)
                || (treeEnv && std::string(treeEnv) == "1"), oocTreeNodeCap());
        } catch (const std::exception &error) {
            return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
        }
        if (std::string(policy.name()) == "mcts_ctm" && !state.mctsRoot.supported) {
            evaluator["reason"] = state.mctsRoot.reason;
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        LiveOocDecision decision;
        bool appliedPending = false;
        json appliedTarget;
        if (pending.active && pending.session != request.session) pending = PendingCompoundPlan{};
        if (pending.active && request.sequence <= pending.sequence) pending = PendingCompoundPlan{};
        if (pending.active && state.projected.screenState == sts::ScreenState::CARD_SELECT) {
            const auto scoreStarted = std::chrono::steady_clock::now();
            decision = retainedCompoundDecision(state, pending);
            evaluator["scorerLatencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - scoreStarted).count();
            appliedPending = decision.supported;
            appliedTarget = pending.card;
        } else {
            if (pending.active) pending = PendingCompoundPlan{};
            policy.setSearchSeed(stableHash(request.observationHash + ":live-ooc-mcts"));
            const auto scoreStarted = std::chrono::steady_clock::now();
            decision = policy.score(state.mctsRoot.state, state.mctsRoot.path,
                                    state.mctsRoot.currentActEventVisits);
            evaluator["scorerLatencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - scoreStarted).count();
        }
        // Qualified candidate identities remain checkable without model weights.
        // A missing model must not turn corrupt live mappings into fallback.
        if (!decision.candidates.empty()) {
            try {
                std::vector<std::uint32_t> bits;
                for (const auto &c : decision.candidates) bits.push_back(c.primitiveBits);
                advisor::validateLiveOocActionSet(state, bits,
                    std::string(policy.name()) == "mcts_ctm");
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
        if (!decision.supported) {
            // Missing support/model may fall back; malformed/ambiguous native
            // candidates and nonfinite scores are integration errors.
            if (decision.reason != "MODEL_UNAVAILABLE" && decision.reason != "V4_SCREEN_UNSUPPORTED"
                    && decision.reason != "CTM_MODEL_UNAVAILABLE"
                    && decision.reason != "OOC_WIN_MODEL_UNAVAILABLE"
                    && decision.reason != "OOC_FLOOR_MODEL_UNAVAILABLE"
                    && decision.reason != "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED"
                    && decision.reason.rfind("COMPOUND_TARGET_UNAVAILABLE:", 0) != 0
                    && decision.reason.rfind("SEMANTIC_ENUMERATION_UNSUPPORTED:", 0) != 0
                    && decision.reason.rfind("OOC_MCTS_", 0) != 0)
                return advisor::errorResponse(request, "OOC_POLICY_FAILURE", decision.reason);
            evaluator["reason"] = decision.reason;
        } else {
            try {
                evaluator["candidateSummaries"] = json::array();
                for (const auto &c : decision.candidates) {
                    json summary = {{"semanticKey", c.semanticKey},
                        {"semanticPayload", json::parse(c.payload)}, {"label", c.semanticKey}, {"q", c.q},
                        {"visits", c.visits}, {"visitShare", c.visitShare}, {"prior", c.prior},
                        {"liveAction", advisor::lowerLiveOocAction(state, c.primitiveBits)}};
                    if (!c.followUpPreview.empty()) summary["followUpPreview"] = json::parse(c.followUpPreview);
                    evaluator["candidateSummaries"].push_back(std::move(summary));
                }
                const auto &selected = decision.candidates.at(decision.selectedIndex);
                evaluator["status"] = "OK";
                evaluator["selectedSemanticKey"] = selected.semanticKey;
                evaluator["selectedLabel"] = selected.semanticKey;
                evaluator["selectedLiveAction"] = advisor::lowerLiveOocAction(state, selected.primitiveBits);
                if (appliedPending) {
                    evaluator["compoundPlan"] = json{{"status", "APPLIED"},
                        {"selectorType", pending.selectorName}, {"target", appliedTarget},
                        {"selectionMode", "retained_compound_target"}};
                    pending = PendingCompoundPlan{};
                } else {
                    auto selectedPayload = json::parse(selected.payload);
                    selectedPayload["semanticKey"] = selected.semanticKey;
                    const auto plan = pendingCompoundPlan(request, selectedPayload);
                    if (plan.active) {
                        pending = plan;
                        evaluator["compoundPlan"] = json{{"status", "PENDING"},
                            {"selectorType", plan.selectorName}, {"target", plan.card}};
                    }
                }
                if (policy.name() == std::string("mcts_ctm")) {
                    evaluator["model"] = {{"kind", "ooc_mcts_ctm"},
                                           {"prior", "ooc_strategic_tok_v4"},
                                           {"leaf", "v_win_compact_tree"}, {"simulations", 512},
                                           {"selection", "visits_then_q"}, {"identity", identity}};
                } else {
                    evaluator["model"] = {{"kind", "ooc_v4_q"}, {"identity", identity}};
                }
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
        if (decision.tree) {
            const auto &tree = *decision.tree;
            json captured = {{"accepted", true}, {"rootId", 0},
                {"truncated", tree.truncated}, {"nodes", json::array()},
                {"edges", json::array()}};
            for (const auto &node : tree.nodes)
                captured["nodes"].push_back({{"id", node.id}, {"kind", node.chance ? "chance" : "state"},
                    {"stateId", std::to_string(node.state)}, {"actionId", node.action},
                    {"label", node.label}, {"key", node.key}, {"outcome", node.outcome},
                    {"screen", node.screen}, {"room", node.room}, {"floor", node.floor},
                    {"mapX", node.mapX}, {"mapY", node.mapY}, {"hp", node.hp},
                    {"maxHp", node.maxHp}, {"gold", node.gold}, {"selected", node.selected},
                    {"depth", node.depth}, {"visits", node.visits},
                    {"prior", node.chance ? json(node.prior) : json(nullptr)},
                    {"q", node.chance && node.visits ? json(node.q) : json(nullptr)}});
            for (const auto &edge : tree.edges)
                captured["edges"].push_back({{"parentId", edge.parentId},
                    {"childId", edge.childId ? json(*edge.childId) : json(nullptr)},
                    {"visits", edge.visits}, {"kind", edge.particle ? "particle" : "action"},
                    {"combatModelUsed", edge.combatModelUsed},
                    {"combatEncounter", edge.combatEncounter}, {"combatOutcome", edge.combatOutcome}});
            evaluator["tree"] = std::move(captured);
        }
    }
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
            {"kind", "analysis"}, {"status", evaluator.at("status")},
            {"session", request.session}, {"sequence", request.sequence},
            {"observationHash", request.observationHash}, {"evaluators", json::array({evaluator})}};
}

bool truthyEnvironment(const char *name) {
    const char *value = std::getenv(name);
    if (value == nullptr) return false;
    return std::string(value) == "1" || std::string(value) == "true"
        || std::string(value) == "TRUE" || std::string(value) == "yes";
}

std::size_t silverTreeNodeCap() {
    const char *value = std::getenv("STS_SILVER_DEBUG_TREE_NODE_CAP");
    if (value == nullptr || *value == '\0') return 8192;
    for (const char *cursor = value; *cursor != '\0'; ++cursor) {
        if (*cursor < '0' || *cursor > '9') return 8192;
    }
    char *end = nullptr;
    errno = 0;
    const auto parsed = std::strtoull(value, &end, 10);
    if (errno == ERANGE || end == value || *end != '\0' || parsed == 0) return 8192;
    return static_cast<std::size_t>(std::min<unsigned long long>(parsed, 100000));
}

json silverTreeSnapshotJson(const silver_bridge::SilverTreeSnapshot &snapshot) {
    json output = {
        {"accepted", snapshot.accepted},
        {"failureReason", snapshot.failureReason},
        {"truncated", snapshot.truncated},
        {"rootId", snapshot.rootId},
        {"retainedNodeCount", snapshot.retainedNodeCount},
        {"retainedEdgeCount", snapshot.retainedEdgeCount},
        {"nodes", json::array()},
        {"edges", json::array()},
    };
    for (const auto &node : snapshot.nodes) {
        json item = {
            {"id", node.id}, {"parentId", node.parentId}, {"depth", node.depth},
            {"isChanceNode", node.isChanceNode}, {"hasState", node.hasState},
            {"stateHash", node.stateHash}, {"simulationCount", node.simulationCount},
            {"victoryCount", node.victoryCount}, {"evaluationSum", node.evaluationSum},
        };
        if (node.hasState) item["state"] = node.state;
        output["nodes"].push_back(std::move(item));
    }
    for (const auto &edge : snapshot.edges) {
        json item = {
            {"parentId", edge.parentId}, {"childId", edge.childId},
            {"childCaptured", edge.childCaptured}, {"chanceOutcome", edge.chanceOutcome},
            {"rngAdvanceSteps", edge.rngAdvanceSteps}, {"visitCount", edge.visitCount},
            {"hasAction", edge.hasAction}, {"actionFingerprint", edge.actionFingerprint},
            {"actionLabel", edge.actionLabel}, {"hasContinuation", edge.hasContinuation},
            {"continuationFingerprint", edge.continuationFingerprint},
            {"continuationLabel", edge.continuationLabel},
        };
        if (edge.hasAction) item["action"] = edge.action;
        if (edge.hasContinuation) item["continuation"] = edge.continuation;
        output["edges"].push_back(std::move(item));
    }
    return output;
}

json silverEvaluator(const one_combat::advisor::Request &request,
                     std::shared_ptr<silver_bridge::SilverSearchSession> &session,
                     std::string &sessionIdentity, std::string &combatEntryIdentity,
                     one_combat::advisor::SilverImportContext &importContext,
                     std::string &silverRootIdentity,
                     std::int64_t &silverSimulations) {
    const auto entryIdentity = request.observation.value(
        "combatEntryHash", request.observation.value("silverRoot", json::object())
            .value("combatInstance", std::string()));
    // Reset before importing so a new protocol session cannot inherit the
    // previous session's UUID registry when the combat hash happens to repeat.
    importContext.reset(request.session, entryIdentity);
    const auto imported = one_combat::advisor::importSilverRoot(request.observation, importContext);
    json evaluator = {{"id", "silver_player_decision_v2"},
                      {"scope", "combat_player_decision"},
                      {"simulations", 1000}, {"adaptiveEnabled", false},
                      {"exactVisitLockEnabled", false}, {"rhoRacingEnabled", false}};
    const auto clearSession = [&] {
        session.reset();
        sessionIdentity.clear();
        combatEntryIdentity.clear();
        silverRootIdentity.clear();
        silverSimulations = 0;
    };
    if (!imported.ok) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = imported.reason;
        return evaluator;
    }
    const auto entry = request.observation.value("combatEntryHash", std::string());
    const bool matchingSession = session != nullptr && sessionIdentity == request.session
        && combatEntryIdentity == entry;
    if (!matchingSession && imported.playerTurn == 1 && imported.decisionInTurn == 0) {
        session = silver_bridge::makeSilverSearchSession();
        sessionIdentity = request.session;
        combatEntryIdentity = entry;
        silverRootIdentity.clear();
        silverSimulations = 0;
    } else if (!matchingSession) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = "silver_missing_predecessor";
        return evaluator;
    }
    const auto digest = silver_bridge::inspectConvertedBattleState(imported.wire);
    if (!digest.accepted) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = "silver_state_parity_failure";
        return evaluator;
    }
    const auto legal = silver_bridge::enumerateSilverLegalActions(imported.wire);
    if (legal.empty()) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = "silver_no_legal_actions";
        return evaluator;
    }
    const auto requestedSimulations = std::max<std::int64_t>(1000,
        request.observation.value("silverSearchBudget", static_cast<std::int64_t>(1000)));
    const bool transactionalSelection = imported.wire.inputState
            == static_cast<int>(sts::InputState::CARD_SELECT)
        && (imported.wire.cardSelect.task == static_cast<int>(sts::CardSelectTask::EXHAUST_MANY)
            || imported.wire.cardSelect.task == static_cast<int>(sts::CardSelectTask::GAMBLE));
    if (transactionalSelection) {
        const auto started = std::chrono::steady_clock::now();
        silver_bridge::SilverSearchConfig config;
        config.simulationsPerDecision = requestedSimulations;
        config.collectRootActionSummaries = true;
        config.collectDecisionDiagnostics = true;
        config.adaptiveEnabled = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        const auto transaction = silver_bridge::runSequentialSelectionTransaction(
            *session, imported.wire, config);
        evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - started).count();
        if (!transaction.accepted || !transaction.finalConfirmation) {
            clearSession();
            evaluator["status"] = "UNSUPPORTED";
            evaluator["reason"] = transaction.failure.empty()
                ? "silver_selection_transaction_failed" : transaction.failure;
            return evaluator;
        }
        evaluator["status"] = "OK";
        evaluator["selectionMode"] = "sequential_transaction";
        evaluator["simulations"] = transaction.totalSimulations;
        evaluator["requestedSimulations"] = requestedSimulations;
        evaluator["additionalSimulations"] = transaction.totalSimulations;
        evaluator["totalSimulations"] = transaction.totalSimulations;
        evaluator["selectedAction"] = silver_bridge::semanticActionFingerprint(transaction.finalAction);
        evaluator["selectedLabel"] = one_combat::advisor::silverActionLabel(
            transaction.finalAction, imported.wire);
        evaluator["selectedLiveAction"] = one_combat::advisor::selectedLiveAction(
            transaction.finalAction, importContext, request.observation);
        if (evaluator["selectedLiveAction"].is_null()) {
            clearSession();
            evaluator["status"] = "UNSUPPORTED";
            evaluator["reason"] = "silver_live_action_lowering";
            evaluator.erase("selectedAction");
            evaluator.erase("selectedLabel");
            evaluator.erase("selectedLiveAction");
            return evaluator;
        }
        evaluator["playerTurn"] = imported.playerTurn;
        evaluator["decisionInTurn"] = imported.decisionInTurn;
        evaluator["transaction"] = {
            {"searchDecisions", transaction.searchDecisions},
            {"rerootExact", transaction.rerootExact},
            {"rerootFallback", transaction.rerootFallback},
            {"privateStateOnly", transaction.privateStateOnly},
        };
        return evaluator;
    }
    const auto rootIdentity = request.observation.value("silverRoot", json::object()).dump();
    if (silverRootIdentity != rootIdentity) {
        silverRootIdentity = rootIdentity;
        silverSimulations = 0;
    }
    if (silverSimulations > requestedSimulations) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = "silver_budget_regression";
        return evaluator;
    }
    const auto additionalSimulations = requestedSimulations - silverSimulations;
    const auto started = std::chrono::steady_clock::now();
    silver_bridge::SilverSearchConfig config;
    config.simulationsPerDecision = additionalSimulations;
    config.collectRootActionSummaries = true;
    config.collectDecisionDiagnostics = true;
    config.adaptiveEnabled = false;
    config.exactVisitLockEnabled = false;
    config.rhoRacingEnabled = false;
    const auto decision = silverSimulations == 0
        ? silver_bridge::runSilverDecision(*session, imported.wire, config)
        : silver_bridge::continueSilverDecision(*session, additionalSimulations, config);
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - started).count();
    if (!decision.accepted) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = decision.failureReason;
        return evaluator;
    }
    silverSimulations += decision.simulations;
    evaluator["status"] = "OK";
    evaluator["simulations"] = silverSimulations;
    evaluator["requestedSimulations"] = requestedSimulations;
    evaluator["additionalSimulations"] = decision.simulations;
    evaluator["totalSimulations"] = silverSimulations;
    evaluator["rootVisits"] = decision.rootUncertainty.rootVisits;
    evaluator["selectedAction"] = silver_bridge::semanticActionFingerprint(decision.action);
    evaluator["selectedLabel"] = one_combat::advisor::silverActionLabel(decision.action, imported.wire);
    evaluator["selectedLiveAction"] = one_combat::advisor::selectedLiveAction(
        decision.action, importContext, request.observation);
    if (evaluator["selectedLiveAction"].is_null()) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = "silver_live_action_lowering";
        evaluator.erase("selectedAction");
        evaluator.erase("selectedLabel");
        evaluator.erase("selectedLiveAction");
        return evaluator;
    }
    evaluator["legalActions"] = json::array();
    for (const auto &action : legal) evaluator["legalActions"].push_back(silver_bridge::semanticActionFingerprint(action));
    evaluator["rootActionSummaries"] = json::array();
    std::string rankingText;
    std::vector<const silver_bridge::SilverRootActionSummary *> ranked;
    for (const auto &summary : decision.rootActionSummaries) ranked.push_back(&summary);
    std::sort(ranked.begin(), ranked.end(), [](const auto *a, const auto *b) { return a->edgeVisits > b->edgeVisits; });
    std::int64_t totalVisits = 0;
    for (const auto *summary : ranked) totalVisits += summary->edgeVisits;
    for (const auto *summary : ranked) {
        json item = {
            {"fingerprint", silver_bridge::semanticActionFingerprint(summary->action)},
            {"label", one_combat::advisor::silverActionLabel(summary->action, imported.wire)},
            {"liveAction", one_combat::advisor::selectedLiveAction(
                summary->action, importContext, request.observation)},
            {"edgeVisits", summary->edgeVisits}, {"selectionQValid", summary->selectionQValid},
            {"visitShare", totalVisits == 0 ? 0.0 : static_cast<double>(summary->edgeVisits) / totalVisits}};
        if (summary->selectionQValid) item["selectionQ"] = summary->selectionQ;
        evaluator["rootActionSummaries"].push_back(std::move(item));
    }
    for (std::size_t i = 0; i < ranked.size() && i < 5; ++i) {
        if (!rankingText.empty()) rankingText += "\n";
        rankingText += one_combat::advisor::silverActionLabel(ranked[i]->action, imported.wire);
        rankingText += "|" + std::to_string(ranked[i]->edgeVisits);
        rankingText += "|" + (ranked[i]->selectionQValid ? std::to_string(ranked[i]->selectionQ) : "");
    }
    evaluator["rankingText"] = rankingText;
    evaluator["playerTurn"] = imported.playerTurn;
    evaluator["decisionInTurn"] = imported.decisionInTurn;
    evaluator["reroot"] = {
        {"exact", decision.diagnostic.exactReroot},
        {"equivalentCopy", decision.diagnostic.equivalentCopyReroot},
        {"fallback", decision.diagnostic.fallback},
        {"fallbackReason", silver_bridge::silverRerootFallbackReasonName(
            decision.diagnostic.fallbackReason)},
        {"inheritedVisits", decision.diagnostic.inheritedVisits},
    };
    const bool debugTree = request.observation.value("silverDebugTree", false)
        || truthyEnvironment("STS_SILVER_DEBUG_TREE");
    if (debugTree) {
        silver_bridge::SilverTreeSnapshotConfig treeConfig;
        treeConfig.enabled = true;
        treeConfig.maxNodes = silverTreeNodeCap();
        auto tree = silverTreeSnapshotJson(
            silver_bridge::snapshotSilverSearchTree(*session, treeConfig));
        tree["nodeCap"] = treeConfig.maxNodes;
        evaluator["tree"] = std::move(tree);
    }
    return evaluator;
}
}

int main() {
    one_combat::advisor::LatestObservation latest;
    auto oocModel = std::make_unique<OocStrategicTokNet>();
    std::string oocIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_MODEL"); path && *path) {
        if (oocModel->load(path, true)) oocIdentity = modelIdentity(path);
    }
    one_combat::CompactTreeNet oocWinModel;
    std::string oocWinIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_WIN_MODEL"); path && *path) {
        // CompactTreeNet is also used by the simulator and reports successful
        // loads on stdout. The advisor stdout is a strict JSONL protocol, so
        // keep that diagnostic out of the wire stream.
        std::ostringstream discardedLoadBanner;
        auto *const stdoutBuffer = std::cout.rdbuf(discardedLoadBanner.rdbuf());
        bool loaded = false;
        try {
            loaded = oocWinModel.load(path, one_combat::richIdxMap(), "LiveOocWinModel");
        } catch (...) {
            std::cout.rdbuf(stdoutBuffer);
            throw;
        }
        std::cout.rdbuf(stdoutBuffer);
        if (loaded)
            oocWinIdentity = modelIdentity(path);
    }
    one_combat::CompactTreeNet oocFloorModel;
    std::string oocFloorIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_FLOOR_MODEL"); path && *path) {
        std::ostringstream discardedLoadBanner;
        auto *const stdoutBuffer = std::cout.rdbuf(discardedLoadBanner.rdbuf());
        bool loaded = false;
        try {
            loaded = oocFloorModel.load(path, one_combat::richIdxMap(), "LiveOocFloorModel");
        } catch (...) {
            std::cout.rdbuf(stdoutBuffer);
            throw;
        }
        std::cout.rdbuf(stdoutBuffer);
        if (loaded) oocFloorIdentity = modelIdentity(path);
    }
    std::shared_ptr<one_combat::NativeCombatTransitionSampler> ctm;
    std::string ctmStatus = "MODEL_UNAVAILABLE", ctmReason;
    std::string ctmIdentity = "unavailable";
    std::string cachedEntryHash;
    PendingCompoundPlan pendingCompound;
    json cachedEvaluator;
    std::shared_ptr<silver_bridge::SilverSearchSession> silverSession;
    std::string silverSessionIdentity;
    std::string silverCombatEntryIdentity;
    one_combat::advisor::SilverImportContext silverImportContext;
    std::string silverRootIdentity;
    std::int64_t silverSimulations = 0;
    if (const char *path = std::getenv("STS_CTM_MODEL"); path && *path) {
        try {
            ctm = std::make_shared<one_combat::NativeCombatTransitionSampler>(path);
            ctmStatus = "OK";
            ctmIdentity = modelIdentity(path);
        } catch (const std::exception &e) {
            ctmStatus = "SCHEMA_MISMATCH"; ctmReason = e.what();
        }
    }
    std::unique_ptr<one_combat::LiveOocPolicy> oocPolicy;
    if (const char *selected = std::getenv("STS_LIVE_OOC_POLICY"); selected && std::string(selected) == "v4")
        oocPolicy = std::make_unique<one_combat::LiveOocV4QPolicy>(*oocModel);
    else
        oocPolicy = std::make_unique<one_combat::LiveOocMctsPolicy>(*oocModel, ctm,
                                                                      &oocWinModel, &oocFloorModel);
    std::string line;
    while (std::getline(std::cin, line)) {
        json response;
        try {
            const json wire = json::parse(line);
            if (wire.value("kind", std::string()) == "hello" &&
                wire.value("protocol", std::string()) == one_combat::advisor::kProtocol) {
                response = one_combat::advisor::helloResponse();
            } else {
                one_combat::advisor::Request request;
                const auto validation = one_combat::advisor::parseRequest(wire, request);
                if (!validation.ok) {
                    response = request.identityTrusted
                        ? one_combat::advisor::errorResponse(
                              request, validation.code, validation.message)
                        : one_combat::advisor::errorResponse(validation.code, validation.message);
                } else if (!latest.accept(request)) {
                    response = one_combat::advisor::staleResponse(request, "older sequence in session");
                } else {
                    if (request.observation.value("boundary", std::string()) == "combat") {
                        const auto silver = silverEvaluator(request, silverSession,
                                                            silverSessionIdentity,
                                                            silverCombatEntryIdentity,
                                                            silverImportContext,
                                                            silverRootIdentity,
                                                            silverSimulations);
                        if (!ctm) {
                            if (!request.observation.contains("combatEntry")) {
                                response = one_combat::advisor::unsupportedResponse(
                                    request, "model unavailable");
                            } else response = { {"protocol", one_combat::advisor::kProtocol},
                                {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                {"kind", "analysis"}, {"status", ctmStatus},
                                {"reason", ctmReason.empty() ? ctmStatus : ctmReason},
                                {"session", request.session}, {"sequence", request.sequence},
                                {"observationHash", request.observationHash},
                                {"evaluators", json::array({silver})} };
                        } else {
                            one_combat::CombatPredictorInputV1 input;
                            const auto imported = one_combat::advisor::importCombatPredictorInput(
                                request.observation, input);
                            if (!imported.ok) response = one_combat::advisor::errorResponse(
                                request, imported.code, imported.message);
                            else {
                                const std::string entryHash = request.observation.value(
                                    "combatEntryHash", request.observationHash);
                                json evaluator;
                                if (entryHash == cachedEntryHash && !cachedEvaluator.is_null()) {
                                    evaluator = cachedEvaluator;
                                    evaluator["latencyMicros"] = 0;
                                } else {
                                    const auto started = std::chrono::steady_clock::now();
                                    const auto support = ctm->forecastSupport(input);
                                    evaluator = {{"id", "ctm_combat_entry_v2"},
                                        {"scope", "combat_entry"}, {"combatEntryHash", entryHash},
                                        {"potionKeepValue", input.globals.potionKeepValue}};
                                    if (!support.supported) {
                                        evaluator["status"] = "UNSUPPORTED";
                                        evaluator["reason"] = support.reason;
                                    } else {
                                        const auto result = ctm->forecastExpectation(input);
                                        evaluator["status"] = "OK";
                                        evaluator["deathProbability"] = result.death;
                                        evaluator["winningHpHistogramMin"] = result.winningHpMin;
                                        evaluator["winningHpHistogram"] = result.winningHpHistogram;
                                    }
                                    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                                        std::chrono::steady_clock::now() - started).count();
                                    cachedEntryHash = entryHash;
                                    cachedEvaluator = evaluator;
                                }
                                response = {{"protocol", one_combat::advisor::kProtocol},
                                    {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                    {"kind", "analysis"}, {"status", "OK"},
                                    {"session", request.session}, {"sequence", request.sequence},
                                    {"observationHash", request.observationHash},
                                    {"evaluators", json::array({evaluator, silver})},
                                    {"model", "combat_transition_near_full_except_smoke_v2"},
                                    {"modelStatus", ctmStatus}};
                            }
                        }
                    } else if (request.observation.value("boundary", std::string()) == "ooc") {
                        response = oocResponse(request, *oocPolicy, oocIdentity + ":ctm=" + ctmIdentity
                                                + ":win=" + oocWinIdentity + ":floor=" + oocFloorIdentity,
                                                pendingCompound);
                    } else {
                        one_combat::advisor::PublicOocState imported;
                        const auto importedResult =
                            one_combat::advisor::importPublicOoc(request.observation, imported);
                        if (!importedResult.ok) {
                            response = one_combat::advisor::errorResponse(
                                request, importedResult.code, importedResult.message);
                        } else {
                            // The public OOC state is now imported and ID-checked.
                            // Keep evaluation fail-closed until map/path, relic,
                            // potion, and feature-parity contracts are imported.
                            response = one_combat::advisor::unsupportedResponse(
                                request, "native OOC evaluator is not yet feature-qualified");
                        }
                    }
                }
            }
        } catch (const json::exception &error) {
            response = one_combat::advisor::errorResponse("MALFORMED_JSON", error.what());
        } catch (const std::exception &error) {
            response = one_combat::advisor::errorResponse("ADVISOR_FAILURE", error.what());
        }
        if (response.contains("evaluators") && response["evaluators"].is_array()) {
            for (const auto &evaluator : response["evaluators"]) {
                if (evaluator.value("id", std::string()) == "silver_player_decision_v2") {
                    response["silverStatus"] = evaluator.value("status", std::string());
                    response["silverReason"] = evaluator.value("reason", std::string());
                    response["silverRanking"] = evaluator.value("rankingText", std::string());
                    break;
                }
            }
        }
        std::cout << response.dump() << '\n' << std::flush;
    }
    return 0;
}
