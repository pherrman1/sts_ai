#pragma once

#include <cstdint>
#include <string>

#include <nlohmann/json.hpp>

namespace one_combat::advisor {

inline constexpr const char *kProtocol = "sts_model_inspector_v1";
inline constexpr int kProtocolVersion = 1;

struct Request {
    std::string kind;
    std::string session;
    std::uint64_t sequence = 0;
    std::string observationHash;
    nlohmann::json observation;
    bool identityTrusted = false;
};

struct ValidationResult {
    bool ok = false;
    std::string code;
    std::string message;
};

ValidationResult parseRequest(const nlohmann::json &wire, Request &request);
nlohmann::json helloResponse();
nlohmann::json errorResponse(const std::string &code, const std::string &message);
nlohmann::json errorResponse(const Request &request, const std::string &code,
                             const std::string &message);
nlohmann::json unsupportedResponse(const Request &request, const std::string &reason);
nlohmann::json staleResponse(const Request &request, const std::string &reason);

// A request is current only within one session and when its sequence is
// strictly newer than the last accepted observation. The hash is included in
// the response so the UI can reject a response after a reload or reconnect.
class LatestObservation {
    std::string session_;
    std::uint64_t sequence_ = 0;
    std::string hash_;
public:
    bool accept(const Request &request);
    bool matches(const Request &request) const;
    void reset();
};

} // namespace one_combat::advisor
