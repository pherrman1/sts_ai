#ifndef STS_LIGHTSPEED_OOC_SEMANTIC_ACTION_H
#define STS_LIGHTSPEED_OOC_SEMANTIC_ACTION_H

#include <cstdint>
#include <string>
#include <vector>

#include "constants/Cards.h"

namespace sts {
struct GameContext;

namespace search {

enum class OocSemanticEffect : std::uint8_t {
    UPGRADE_CARD,
};

enum class OocSemanticSource : std::uint8_t {
    CAMPFIRE_SMITH,
};

struct OocCardTarget {
    CardId id = CardId::INVALID;
    std::int16_t misc = 0;
    bool upgraded = false;
    // -1 means unbottled; 0/1/2 identify Bottled Flame/Lightning/Tornado.
    std::int8_t bottleSlot = -1;
    // Zero-based occurrence among cards with the same fields above. This is
    // stable across opening Smith's selector and is not a cached deck index.
    std::uint16_t occurrence = 0;
};

struct OocSemanticAction {
    static constexpr std::uint32_t kSchemaVersion = 1;

    OocSemanticEffect effect = OocSemanticEffect::UPGRADE_CARD;
    OocSemanticSource source = OocSemanticSource::CAMPFIRE_SMITH;
    OocCardTarget target;
};

struct OocExecutionResult {
    bool ok = false;
    std::string error;
    std::vector<std::uint32_t> executedPrimitiveBits;
};

std::vector<OocSemanticAction> enumerateCampfireUpgradeActions(const GameContext &gc);

OocExecutionResult executeOocSemanticAction(GameContext &gc, const OocSemanticAction &action);

std::string canonicalOocSemanticActionKey(const OocSemanticAction &action);

} // namespace search
} // namespace sts

#endif
