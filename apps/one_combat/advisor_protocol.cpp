#include "advisor_protocol.h"

#include <limits>

namespace one_combat::advisor {

namespace {
ValidationResult bad(const char *code, const std::string &message) {
    return {false, code, message};
}
}

ValidationResult parseRequest(const nlohmann::json &wire, Request &request) {
    if (!wire.is_object()) return bad("MALFORMED_REQUEST", "request must be an object");
    if (wire.value("protocol", std::string()) != kProtocol)
        return bad("PROTOCOL_MISMATCH", "unsupported protocol");
    if (!wire.contains("kind") || !wire.at("kind").is_string())
        return bad("MALFORMED_REQUEST", "kind must be a string");
    request.kind = wire.at("kind").get<std::string>();
    if (request.kind == "hello") return {true, {}, {}};
    if (request.kind != "observation")
        return bad("UNSUPPORTED_REQUEST", "kind must be hello or observation");

    const auto requiredString = [&](const char *name, std::string &out) -> ValidationResult {
        if (!wire.contains(name) || !wire.at(name).is_string() || wire.at(name).get<std::string>().empty())
            return bad("MALFORMED_REQUEST", std::string(name) + " must be a non-empty string");
        out = wire.at(name).get<std::string>();
        return {true, {}, {}};
    };
    auto result = requiredString("session", request.session);
    if (!result.ok) return result;
    result = requiredString("observationHash", request.observationHash);
    if (!result.ok) return result;
    if (!wire.contains("sequence") || !wire.at("sequence").is_number_unsigned())
        return bad("MALFORMED_REQUEST", "sequence must be an unsigned integer");
    request.sequence = wire.at("sequence").get<std::uint64_t>();
    if (!wire.contains("observation") || !wire.at("observation").is_object())
        return bad("MALFORMED_REQUEST", "observation must be an object");
    request.observation = wire.at("observation");
    if (!request.observation.contains("boundary") || !request.observation.at("boundary").is_string())
        return bad("MALFORMED_OBSERVATION", "observation.boundary must be a string");
    const std::string boundary = request.observation.at("boundary").get<std::string>();
    if (boundary != "combat" && boundary != "card_reward" && boundary != "rest")
        return bad("UNSUPPORTED_BOUNDARY", "observation.boundary is not supported");
    if (boundary == "card_reward" || boundary == "rest") {
        for (const char *field : {"deck", "candidates"}) {
            if (!request.observation.contains(field) || !request.observation.at(field).is_array())
                return bad("SCHEMA_MISMATCH", std::string("observation.") + field + " must be an array");
            for (const auto &card : request.observation.at(field)) {
                if (!card.is_object() || !card.contains("id") || !card.at("id").is_string()
                    || card.at("id").get<std::string>().empty()
                    || !card.contains("upgraded") || !card.at("upgraded").is_boolean()
                    || !card.contains("misc") || !card.at("misc").is_number_integer())
                    return bad("SCHEMA_MISMATCH", std::string("observation.") + field +
                               " contains an invalid card instance");
            }
        }
    }
    return {true, {}, {}};
}

nlohmann::json helloResponse() {
    return {{"protocol", kProtocol}, {"protocolVersion", kProtocolVersion},
            {"kind", "hello"}, {"status", "READY"},
            {"capabilities", {"observationValidation"}},
            {"evaluators", nlohmann::json::array()}};
}

nlohmann::json errorResponse(const std::string &code, const std::string &message) {
    return {{"protocol", kProtocol}, {"protocolVersion", kProtocolVersion},
            {"kind", "error"}, {"status", "ERROR"}, {"code", code}, {"message", message}};
}

nlohmann::json errorResponse(const Request &request, const std::string &code,
                             const std::string &message) {
    return { {"protocol", kProtocol}, {"protocolVersion", kProtocolVersion},
             {"kind", "error"}, {"status", "ERROR"}, {"code", code},
             {"message", message}, {"session", request.session},
             {"sequence", request.sequence}, {"observationHash", request.observationHash} };
}

nlohmann::json unsupportedResponse(const Request &request, const std::string &reason) {
    return {{"protocol", kProtocol}, {"protocolVersion", kProtocolVersion},
            {"kind", "analysis"}, {"status", "UNSUPPORTED"}, {"reason", reason},
            {"session", request.session}, {"sequence", request.sequence},
            {"observationHash", request.observationHash}, {"evaluators", nlohmann::json::array()}};
}

nlohmann::json staleResponse(const Request &request, const std::string &reason) {
    return {{"protocol", kProtocol}, {"protocolVersion", kProtocolVersion},
            {"kind", "analysis"}, {"status", "STALE"}, {"reason", reason},
            {"session", request.session}, {"sequence", request.sequence},
            {"observationHash", request.observationHash}, {"evaluators", nlohmann::json::array()}};
}

bool LatestObservation::accept(const Request &request) {
    if (request.kind != "observation") return false;
    if (session_ == request.session && request.sequence <= sequence_) return false;
    session_ = request.session;
    sequence_ = request.sequence;
    hash_ = request.observationHash;
    return true;
}

bool LatestObservation::matches(const Request &request) const {
    return request.kind == "observation" && request.session == session_ &&
           request.sequence == sequence_ && request.observationHash == hash_;
}

void LatestObservation::reset() {
    session_.clear();
    sequence_ = 0;
    hash_.clear();
}

} // namespace one_combat::advisor
