#pragma once
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <time.h>

namespace one_combat {
enum class OocProfileBucket { Mcts, RealCombat, Metadata, PolicyLogits, PolicyPrepare,
    PolicyPredict, Successor, CombatPrepare, CombatResolve, EvaluateLeaf, LeafValue,
    LeafFeatures, LeafPredict,
    V4StateNetwork, V4EncodeDeck, V4EncodeRel, V4EncodePot, V4StateFusion,
    V4ActionValue, PriorBuild, SingletonPrior, Count };
struct OocProfileCounter {
    std::uint64_t calls = 0;
    double inclusive = 0, exclusive = 0;
};
inline bool oocProfileEnabled() {
    static const bool enabled = [] {
        const char *value = std::getenv("STS_OOC_CPU_PROFILE");
        return value && std::strcmp(value, "1") == 0;
    }();
    return enabled;
}
inline double oocProfileCpu(clockid_t clock = CLOCK_THREAD_CPUTIME_ID) {
    timespec value{};
    clock_gettime(clock, &value);
    return value.tv_sec + value.tv_nsec * 1e-9;
}
inline thread_local std::array<OocProfileCounter, static_cast<std::size_t>(OocProfileBucket::Count)> oocProfileCounters{};
class OocProfileScope {
    inline static thread_local OocProfileScope *active = nullptr;
    OocProfileScope *parent = nullptr;
    OocProfileCounter *counter = nullptr;
    double started = 0, children = 0;
public:
    static bool hasParent() { return active != nullptr; }
    explicit OocProfileScope(OocProfileBucket bucket, bool eligible = true) {
        if (!eligible || !oocProfileEnabled()) return;
        counter = &oocProfileCounters[static_cast<std::size_t>(bucket)];
        parent = active;
        active = this;
        started = oocProfileCpu();
    }
    OocProfileScope(const OocProfileScope &) = delete;
    OocProfileScope &operator=(const OocProfileScope &) = delete;
    void stop() {
        if (!counter) return;
        const double elapsed = oocProfileCpu() - started;
        ++counter->calls;
        counter->inclusive += elapsed;
        counter->exclusive += elapsed - children;
        if (parent) parent->children += elapsed;
        active = parent;
        counter = nullptr;
    }
    ~OocProfileScope() { stop(); }
};
}
