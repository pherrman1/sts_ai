#ifndef STS_LIGHTSPEED_S3_SIBLING_CRN_DIAGNOSTIC_H
#define STS_LIGHTSPEED_S3_SIBLING_CRN_DIAGNOSTIC_H

#include <cstddef>
#include <cstdint>

namespace sts::search {

// Stable identity of one captured frontiergen parent decision. The visible
// observation hash is provenance, not a unique decision key.
struct S3SiblingCrnStateIdentity {
    std::uint64_t sourceSeed = 0;
    std::int32_t fightIdx = -1;
    std::int32_t decisionIdx = -1;
    std::uint64_t stateId = 0;
};

inline std::uint64_t s3SiblingCrnMix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

// Domain-separated deterministic seed schedule. The state identity is always
// included; action is included only by callers that need action-specific
// streams. Sampling mode is represented by the domain, never by row order.
inline std::uint64_t s3SiblingCrnSeed(
    std::uint64_t diagnosticSeed,
    const S3SiblingCrnStateIdentity &identity,
    int k, int replicate, int sample, int action,
    std::uint64_t domain) {
    std::uint64_t x = s3SiblingCrnMix(diagnosticSeed ^ domain);
    x = s3SiblingCrnMix(x ^ identity.sourceSeed);
    x = s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(identity.fightIdx)));
    x = s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(identity.decisionIdx)));
    x = s3SiblingCrnMix(x ^ identity.stateId);
    x = s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(k)));
    x = s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(replicate)));
    x = s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(sample)));
    return s3SiblingCrnMix(x ^ static_cast<std::uint64_t>(
        static_cast<std::uint32_t>(action)));
}

inline bool s3SiblingCrnManifestSatisfied(std::size_t requested,
                                          std::size_t evaluated) {
    return requested == evaluated;
}

} // namespace sts::search

#endif
