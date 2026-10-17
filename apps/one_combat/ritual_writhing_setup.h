#ifndef STS_RITUAL_WRITHING_SETUP_H
#define STS_RITUAL_WRITHING_SETUP_H
#include <functional>
#include <optional>
#include <string>
#include <nlohmann/json.hpp>
#include "game/GameContext.h"

namespace one_combat {
// Research-only public-state overrides. No selected actions or RNG draws.
struct RitualWrithingSetup {
    std::string name;
    bool upgraded;
    int copies;
    sts::Potion potion; // EMPTY means no forced potion, not a potion-free belt.
};
std::optional<RitualWrithingSetup> parseRitualWrithingSetup(const std::string &name);
nlohmann::json ritualWrithingDescriptor(const RitualWrithingSetup &setup);
// Requires an Act-3 hallway battle. Atomic on failure; receipt includes full
// persistent before/after state and every GameContext RNG stream.
nlohmann::json applyRitualWrithingSetup(sts::GameContext &gc, const RitualWrithingSetup &setup);
// Controlled producer boundary: preserve caller-owned partial buffers and
// record failures instead of unwinding through the OpenMP worker boundary.
bool guardRitualWrithingSource(const sts::GameContext &gc, std::uint64_t sourceSeed,
    const int &fightIdx, const std::string &stage, const nlohmann::json &attempt,
    nlohmann::json &failures, const std::function<void()> &work);
}
#endif
