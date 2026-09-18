#include "advisor_protocol.h"
#include "live_ooc_importer.h"

#include <iostream>
#include <string>

using nlohmann::json;

int main() {
    one_combat::advisor::LatestObservation latest;
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
                    response = one_combat::advisor::errorResponse(validation.code, validation.message);
                } else if (!latest.accept(request)) {
                    response = one_combat::advisor::staleResponse(request, "older sequence in session");
                } else {
                    if (request.observation.value("boundary", std::string()) == "combat") {
                        response = one_combat::advisor::unsupportedResponse(
                            request, "live combat importer is not configured");
                    } else {
                        one_combat::advisor::PublicOocState imported;
                        const auto importedResult =
                            one_combat::advisor::importPublicOoc(request.observation, imported);
                        if (!importedResult.ok) {
                            response = one_combat::advisor::errorResponse(
                                importedResult.code, importedResult.message);
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
