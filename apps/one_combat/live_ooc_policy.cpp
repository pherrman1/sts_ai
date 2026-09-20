#include "live_ooc_policy.h"
#include "ooc_v4_encoding.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <nlohmann/json.hpp>
#include "../ooc_strategic_tok_net.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat {
namespace {
using namespace sts;
using namespace sts::search;

LiveOocDecision unsupported(const std::string &reason) {
    LiveOocDecision result;
    result.policy = "v4_q";
    result.reason = reason;
    return result;
}

// Compound semantic enumeration describes a completed transaction. A live
// decision performs only its source action, with the selector scored afresh.
// Its separate identity cannot accidentally be executed as that transaction.
std::pair<std::string, std::string> currentIdentity(const OocSemanticPrimitiveBinding &binding) {
    auto semantic = binding.semantic;
    if (binding.compoundSelector == CardSelectScreenType::INVALID)
        return {canonicalOocSemanticActionKey(semantic), oocSemanticActionPayloadJson(semantic)};
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
    return {canonicalOocSemanticActionKey(semantic) + ":current-screen", payload.dump()};
}
} // namespace

LiveOocDecision scoreLiveOocV4(const sts::GameContext &projected, const PathHistory &path,
                             const OocStrategicTokNet &model) {
    if (!v4DecisionSupported(projected)) return unsupported("V4_SCREEN_UNSUPPORTED");
    const auto actions = v4CandidateActions(projected);
    if (actions.empty()) return unsupported("EMPTY_CANDIDATE_SET");

    std::map<std::uint32_t, std::pair<std::string, std::string>> identities;
    if (projected.screenState == sts::ScreenState::MAP_SCREEN) {
        for (const auto &action : actions) {
            const int x = action.getIdx1();
            const int y = projected.curMapNodeY + 1;
            if (x < 0 || x >= 7 || y < 0 || y >= 15 || !action.isValidAction(projected))
                return unsupported("INVALID_MAP_CANDIDATE");
            identities.emplace(action.bits, std::make_pair(
                "ooc-live:v1:map:x=" + std::to_string(x) + ":y=" + std::to_string(y),
                nlohmann::json({{"type", "map_node"}, {"x", x}, {"y", y}}).dump()));
        }
    } else {
        const auto semantic = sts::search::enumerateOocSemanticPrimitiveBindings(projected);
        if (!semantic.supported)
            return unsupported("SEMANTIC_ENUMERATION_UNSUPPORTED: " + semantic.error);
        if (!semantic.complete)
            return unsupported("SEMANTIC_ENUMERATION_FAILURE: " + semantic.error);
        for (const auto &binding : semantic.bindings) {
            auto identity = currentIdentity(binding);
            const auto existing = identities.find(binding.primitiveBits);
            if (existing != identities.end() && existing->second != identity)
                return unsupported("AMBIGUOUS_SEMANTIC_MAPPING");
            identities.emplace(binding.primitiveBits, std::move(identity));
        }
    }

    // Semantic enumeration includes skips for every reward group; V4's
    // established candidate contract adds only the final group's skip. Validate
    // every V4 primitive against that semantic superset without widening V4.
    std::set<std::uint32_t> primitiveSeen;
    std::set<std::string> semanticSeen;
    for (const auto &action : actions) {
        const auto found = identities.find(action.bits);
        if (!primitiveSeen.insert(action.bits).second || !action.isValidAction(projected)
                || found == identities.end())
            return unsupported("CANDIDATE_ENUMERATION_DISAGREEMENT");
        if (!semanticSeen.insert(found->second.first).second)
            return unsupported("AMBIGUOUS_SEMANTIC_MAPPING");
    }

    if (!model.ok) {
        auto result = unsupported("MODEL_UNAVAILABLE");
        // Preserve the fully validated current candidate set so generic
        // lowering can reject mismatches before allowing model fallback.
        for (const auto &action : actions) {
            const auto &identity = identities.at(action.bits);
            result.candidates.push_back({identity.first, identity.second, action.bits, 0.0});
        }
        std::sort(result.candidates.begin(), result.candidates.end(), [](const auto &a, const auto &b) {
            return a.semanticKey < b.semanticKey;
        });
        return result;
    }

    const auto tokens = buildTokStatePure(projected, path);
    const auto prepared = model.prepareState(tokens.glob, tokens.nDk, tokens.dk,
                                             tokens.nRl, tokens.rl, tokens.nPt, tokens.pt);
    LiveOocDecision result;
    result.policy = "v4_q";
    for (const auto &action : actions) {
        int actionType, c1, c2, c3, cand1, cand2, cand3;
        strategicCands(projected, action, actionType, c1, c2, c3, cand1, cand2, cand3);
        const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
        int entityType, entityId;
        float goldGePrice;
        tokEntity(projected, action, entityType, entityId, goldGePrice);
        const float entity[4] = {entityType == 0 ? 1.0f : 0.0f, entityType == 1 ? 1.0f : 0.0f,
                                 entityType == 2 ? 1.0f : 0.0f, entityType == 3 ? 1.0f : 0.0f};
        const double q = model.predictActionValue(prepared, action.bits, cats, actionType,
            static_cast<int>(projected.screenState), entity, entityId, goldGePrice);
        if (!std::isfinite(q)) return unsupported("NONFINITE_Q");
        const auto &identity = identities.at(action.bits);
        result.candidates.push_back({identity.first, identity.second, action.bits, q});
    }
    std::sort(result.candidates.begin(), result.candidates.end(), [](const auto &a, const auto &b) {
        return a.semanticKey < b.semanticKey;
    });
    result.selectedIndex = 0;
    for (int i = 1; i < static_cast<int>(result.candidates.size()); ++i)
        if (result.candidates[i].q > result.candidates[result.selectedIndex].q)
            result.selectedIndex = i;
    result.supported = true;
    return result;
}

LiveOocDecision LiveOocV4QPolicy::score(const sts::GameContext &projected,
                                      const PathHistory &path) const {
    return scoreLiveOocV4(projected, path, model_);
}
} // namespace one_combat
