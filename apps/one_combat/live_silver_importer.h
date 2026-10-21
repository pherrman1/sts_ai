#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>

#include <nlohmann/json.hpp>

#include "sim/search/SilverBridge.h"

namespace one_combat::advisor {

struct SilverRootImportResult {
    bool ok = false;
    std::string reason;
    int playerTurn = -1;
    int decisionInTurn = -1;
    // Legacy v2 tests and fixtures still name the in-turn ordinal directly.
    // v4 responses publish the explicit playerTurn/decisionInTurn pair.
    int decisionOrdinal = -1;
    silver_bridge::BattleStateWire wire;
};

// Owns only public physical-card identity for one protocol/combat lifetime.
// It deliberately has no game state and no RNG.  A new combatEntryHash clears
// the registry; an already-seen UUID can never receive a different Silver ID.
struct SilverImportContext {
    std::string session;
    std::string combatEntryHash;
    std::unordered_map<std::string, std::int16_t> cardIds;
    int nextUniqueCardId = 0;

    void reset(const std::string &newSession, const std::string &newCombatEntryHash) {
        if (session == newSession && combatEntryHash == newCombatEntryHash) return;
        session = newSession;
        combatEntryHash = newCombatEntryHash;
        cardIds.clear();
        nextUniqueCardId = 0;
    }
};

SilverRootImportResult importSilverRoot(const nlohmann::json &observation);
SilverRootImportResult importSilverRoot(const nlohmann::json &observation,
                                        SilverImportContext &context);
// A Headbutt grid opened by a hit that killed the Gremlin Leader: Java queues
// the surviving minions' escapes behind the grid, so every pick ends the
// combat the same way (native ends it at the hit). Returns the choice index
// (1) to pass through, or 0 when the observation does not qualify
// (STS_SILVER_LEADER_ESCAPE_PASS_THROUGH, live problem 72).
int minionLeaderEscapeChoice(const nlohmann::json &observation);
std::string silverActionLabel(const silver_bridge::SemanticAction &action,
                              const silver_bridge::BattleStateWire &state);
nlohmann::json selectedLiveAction(const silver_bridge::SemanticAction &action,
                                  const SilverImportContext &context,
                                  const nlohmann::json &observation);

} // namespace one_combat::advisor
