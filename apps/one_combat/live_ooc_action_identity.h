#pragma once

#include <string>
#include <utility>
#include <nlohmann/json.hpp>
#include "sim/search/OocSemanticAction.h"

namespace one_combat {
inline std::pair<std::string, std::string> currentLiveOocIdentity(
        const sts::search::OocSemanticPrimitiveBinding &binding) {
    using namespace sts;
    using namespace sts::search;
    auto semantic = binding.semantic;
    if (binding.compoundSelector == CardSelectScreenType::INVALID)
        return {canonicalOocSemanticActionKey(semantic), oocSemanticActionPayloadJson(semantic)};
    const auto sourceKey = canonicalOocSemanticActionKey(semantic);
    const auto originalPayload = nlohmann::json::parse(oocSemanticActionPayloadJson(semantic));
    if (const auto *transaction = std::get_if<OocTransactionTarget>(&semantic.target)) {
        if (semantic.source == OocSemanticSource::SHOP_REMOVE)
            semantic.target = OocShopTarget{OocNoTarget{}, transaction->expectedGoldCost, 0};
        else
            semantic.target = OocEventTarget{transaction->event, transaction->option};
    } else {
        semantic.target = OocNoTarget{};
    }
    auto payload = nlohmann::json::parse(oocSemanticActionPayloadJson(semantic));
    payload["currentScreenOnly"] = true;
    payload["selectorType"] = static_cast<int>(binding.compoundSelector);
    // Keep the physical card target in the source identity even though the
    // executable source primitive is intentionally screen-only.  The live
    // protocol uses this retained target to resolve the following selector.
    if (originalPayload.value("type", std::string()) == "transaction"
            && originalPayload.contains("card"))
        payload["compoundTarget"] = originalPayload.at("card");
    const auto targetKey = originalPayload.contains("card")
        ? ":target=" + originalPayload.at("card").dump() : std::string();
    return {sourceKey + ":current-screen" + targetKey, payload.dump()};
}
}
