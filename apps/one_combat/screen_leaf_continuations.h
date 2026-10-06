#pragma once

// Offline #379 reconstruction only. Frozen exporters wrap their original
// callable; current-main production callback assignments are never changed.
#include "game/GameContext.h"
#include "nlohmann/json.hpp"
#include <stdexcept>
#include <utility>

namespace one_combat::screen_leaf {
using Json = nlohmann::json;

struct TaggedContinuation {
    Json descriptor;
    sts::GameContextAction original;
    void operator()(sts::GameContext &gc) const {
        // Most callbacks replace gc.regainControlAction while running. Preserve
        // this callable's captures even when that assignment destroys our tag.
        const auto callable = original;
        callable(gc);
    }
};

inline sts::GameContextAction tagContinuation(Json descriptor,
                                              sts::GameContextAction original) {
    if (!original || !descriptor.is_object() || !descriptor.contains("kind"))
        throw std::runtime_error("screen leaf: invalid tagged continuation");
    return TaggedContinuation{std::move(descriptor), std::move(original)};
}

inline Json continuationDescriptor(const sts::GameContextAction &action) {
    if (!action) return nullptr;
    const auto *tagged = action.target<TaggedContinuation>();
    if (!tagged) throw std::runtime_error("screen leaf: untagged continuation");
    return tagged->descriptor;
}

// Resolve a frozen continuation identity to current-main behavior. Unknown
// identities and malformed/nested descriptors are errors, never guessed.
sts::GameContextAction importContinuation(const Json &descriptor);
}
