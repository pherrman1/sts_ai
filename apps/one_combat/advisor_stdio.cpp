#include "advisor_protocol.h"
#include "live_ooc_importer.h"
#include "combat_transition_runtime.h"

#include <iostream>
#include <cstdlib>
#include <string>
#include <chrono>
#include <memory>

using nlohmann::json;

int main() {
    one_combat::advisor::LatestObservation latest;
    std::unique_ptr<one_combat::NativeCombatTransitionSampler> ctm;
    std::string ctmStatus = "MODEL_UNAVAILABLE", ctmReason;
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
                                {"evaluators", json::array()} };
                        } else {
                            one_combat::CombatPredictorInputV1 input;
                            const auto imported = one_combat::advisor::importCombatPredictorInput(
                                request.observation, input);
                            if (!imported.ok) response = one_combat::advisor::errorResponse(
                                request, imported.code, imported.message);
                            else {
                                const auto started = std::chrono::steady_clock::now();
                                const auto support = ctm->forecastSupport(input);
                                json evaluator = {{"id", "ctm_combat_entry_v2"},
                                    {"scope", "combat_entry"}, {"combatEntryHash",
                                    request.observation.value("combatEntryHash", request.observationHash)},
                                    {"potionKeepValue", input.globals.potionKeepValue}};
                                if (!support.supported) {
                                    evaluator["status"] = "UNSUPPORTED";
                                    evaluator["reason"] = support.reason;
                                } else {
                                    const auto result = ctm->forecastExpectation(input);
                                    evaluator["status"] = "OK";
                                    evaluator["deathProbability"] = result.death;
                                    evaluator["winningHpFraction"] = result.winningHpFraction;
                                }
                                evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                                    std::chrono::steady_clock::now() - started).count();
                                response = {{"protocol", one_combat::advisor::kProtocol},
                                    {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                    {"kind", "analysis"}, {"status", "OK"},
                                    {"session", request.session}, {"sequence", request.sequence},
                                    {"observationHash", request.observationHash},
                                    {"evaluators", json::array({evaluator})},
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
        std::cout << response.dump() << '\n' << std::flush;
    }
    return 0;
}
