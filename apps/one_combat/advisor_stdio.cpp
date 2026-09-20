#include "advisor_protocol.h"
#include "live_ooc_importer.h"
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
json silverEvaluator(const one_combat::advisor::Request &request,
                     std::shared_ptr<silver_bridge::SilverSearchSession> &session,
                     std::string &sessionIdentity, std::string &combatEntryIdentity,
                     one_combat::advisor::SilverImportContext &importContext) {
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
    if (imported.decisionOrdinal == 0) {
        session = silver_bridge::makeSilverSearchSession();
        sessionIdentity = request.session;
        combatEntryIdentity = entry;
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
    const auto started = std::chrono::steady_clock::now();
    silver_bridge::SilverSearchConfig config;
    config.simulationsPerDecision = 1000;
    config.collectRootActionSummaries = true;
    config.collectDecisionDiagnostics = true;
    config.adaptiveEnabled = false;
    config.exactVisitLockEnabled = false;
    config.rhoRacingEnabled = false;
    const auto decision = silver_bridge::runSilverDecision(*session, imported.wire, config);
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - started).count();
    if (!decision.accepted) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = decision.failureReason;
        return evaluator;
    }
    evaluator["status"] = "OK";
    evaluator["selectedAction"] = silver_bridge::semanticActionFingerprint(decision.action);
    evaluator["selectedLabel"] = one_combat::advisor::silverActionLabel(decision.action, imported.wire);
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
    evaluator["decisionOrdinal"] = imported.decisionOrdinal;
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
    std::unique_ptr<one_combat::NativeCombatTransitionSampler> ctm;
    std::string ctmStatus = "MODEL_UNAVAILABLE", ctmReason;
    std::string cachedEntryHash;
    json cachedEvaluator;
    std::shared_ptr<silver_bridge::SilverSearchSession> silverSession;
    std::string silverSessionIdentity;
    std::string silverCombatEntryIdentity;
    one_combat::advisor::SilverImportContext silverImportContext;
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
                                                            silverImportContext);
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
