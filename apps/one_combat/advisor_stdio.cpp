#include "advisor_protocol.h"
#include "live_ooc_importer.h"
#include "live_ooc_state.h"
#include "live_ooc_policy.h"
#include "differential_state.h"
#include "../ooc_strategic_tok_net.h"
#include <fstream>
#include <iomanip>
#include <sstream>
#include "combat_transition_runtime.h"
#include "live_silver_importer.h"
#include "sim/search/SilverBridge.h"

#include <iostream>
#include <algorithm>
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
json oocResponse(const one_combat::advisor::Request &request,
                 const one_combat::LiveOocPolicy &policy, const std::string &identity) {
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
        evaluator["differentialState"] = differential::canonicalOocState(
            state.projected, state.path);
        const auto scoreStarted = std::chrono::steady_clock::now();
        const auto decision = policy.score(state.projected, state.path);
        evaluator["scorerLatencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now() - scoreStarted).count();
        // Qualified candidate identities remain checkable without model weights.
        // A missing model must not turn corrupt live mappings into fallback.
        if (!decision.candidates.empty()) {
            try {
                std::vector<std::uint32_t> bits;
                for (const auto &c : decision.candidates) bits.push_back(c.primitiveBits);
                advisor::validateLiveOocActionSet(state, bits);
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
        if (!decision.supported) {
            // Missing support/model may fall back; malformed/ambiguous native
            // candidates and nonfinite scores are integration errors.
            if (decision.reason != "MODEL_UNAVAILABLE" && decision.reason != "V4_SCREEN_UNSUPPORTED"
                    && decision.reason.rfind("SEMANTIC_ENUMERATION_UNSUPPORTED:", 0) != 0)
                return advisor::errorResponse(request, "OOC_POLICY_FAILURE", decision.reason);
            evaluator["reason"] = decision.reason;
        } else {
            try {
                evaluator["candidateSummaries"] = json::array();
                for (const auto &c : decision.candidates) {
                    json summary = {{"semanticKey", c.semanticKey},
                        {"semanticPayload", json::parse(c.payload)}, {"label", c.semanticKey}, {"q", c.q},
                        {"liveAction", advisor::lowerLiveOocAction(state, c.primitiveBits)}};
                    if (!c.followUpPreview.empty()) summary["followUpPreview"] = json::parse(c.followUpPreview);
                    evaluator["candidateSummaries"].push_back(std::move(summary));
                }
                const auto &selected = decision.candidates.at(decision.selectedIndex);
                evaluator["status"] = "OK";
                evaluator["selectedSemanticKey"] = selected.semanticKey;
                evaluator["selectedLabel"] = selected.semanticKey;
                evaluator["selectedLiveAction"] = advisor::lowerLiveOocAction(state, selected.primitiveBits);
                evaluator["model"] = {{"kind", "ooc_strategic_tok_v4"}, {"identity", identity}};
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
    }
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
            {"kind", "analysis"}, {"status", evaluator.at("status")},
            {"session", request.session}, {"sequence", request.sequence},
            {"observationHash", request.observationHash}, {"evaluators", json::array({evaluator})}};
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
    evaluator["differentialState"] = one_combat::differential::canonicalCombatState(imported.wire);
    const auto requestedSimulations = std::max<std::int64_t>(1000,
        request.observation.value("silverSearchBudget", static_cast<std::int64_t>(1000)));
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
    const one_combat::LiveOocV4QPolicy oocPolicy(*oocModel);
    std::unique_ptr<one_combat::NativeCombatTransitionSampler> ctm;
    std::string ctmStatus = "MODEL_UNAVAILABLE", ctmReason;
    std::string cachedEntryHash;
    json cachedEvaluator;
    std::shared_ptr<silver_bridge::SilverSearchSession> silverSession;
    std::string silverSessionIdentity;
    std::string silverCombatEntryIdentity;
    one_combat::advisor::SilverImportContext silverImportContext;
    std::string silverRootIdentity;
    std::int64_t silverSimulations = 0;
    if (const char *path = std::getenv("STS_CTM_MODEL"); path && *path) {
        try {
            ctm = std::make_unique<one_combat::NativeCombatTransitionSampler>(path);
            ctmStatus = "OK";
        } catch (const std::exception &e) {
            ctmStatus = "SCHEMA_MISMATCH"; ctmReason = e.what();
        }
    }
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
                        response = oocResponse(request, oocPolicy, oocIdentity);
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
