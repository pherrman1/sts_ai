#include "live_ooc_policy.h"
#include "ooc_v4_encoding.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <nlohmann/json.hpp>
#include "../ooc_strategic_tok_net.h"
#include "sim/search/OocSemanticAction.h"
#include "constants/SaveFileMappings.h"

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
    // Only these parents open an upgrade selector without a preceding gold,
    // deck, relic or random effect. Other compounds remain explicit display
    // support boundaries. The parent's action set, score and argmax are fixed
    // above and are not affected by this separate selector preview.
    for (auto &candidate : result.candidates) {
        const auto payload = nlohmann::json::parse(candidate.payload);
        if (!payload.value("currentScreenOnly", false)) continue;
        const auto type = static_cast<CardSelectScreenType>(payload.at("selectorType").get<int>());
        const char *typeName = type == CardSelectScreenType::UPGRADE ? "upgrade"
            : type == CardSelectScreenType::REMOVE ? "remove"
            : type == CardSelectScreenType::TRANSFORM ? "transform" : "other";
        nlohmann::json preview = {{"status", "UNSUPPORTED"}, {"selectorType", typeName},
            {"reason", type == CardSelectScreenType::UPGRADE
                ? "PARENT_STATE_TRANSITION_UNQUALIFIED" : "V4_SELECTOR_UNSUPPORTED"}};
        const bool smith = projected.screenState == ScreenState::REST_ROOM
            && candidate.primitiveBits == GameAction(1).bits;
        const bool wallUpgrade = projected.screenState == ScreenState::EVENT_SCREEN
            && projected.curEvent == Event::LIVING_WALL
            && candidate.primitiveBits == GameAction(2).bits;
        if (type == CardSelectScreenType::UPGRADE && (smith || wallUpgrade)) {
            auto selector = projected;
            // This value-only helper builds public eligible cards. It executes
            // no primitive, continuation callback or random transition.
            selector.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
            const auto followUp = scoreLiveOocV4(selector, path, model);
            if (followUp.supported) {
                const auto &selected = followUp.candidates.at(followUp.selectedIndex);
                const auto &target = selector.info.toSelectCards[GameAction(selected.primitiveBits).getIdx1()];
                preview = {{"status", "OK"}, {"scope", "selector_preview"}, {"policy", "v4_q"},
                    {"selectorType", "upgrade"}, {"q", selected.q}, {"semanticKey", selected.semanticKey},
                    {"card", {{"id", nlohmann::json(target.card.id)}, {"upgraded", target.card.isUpgraded()},
                        {"misc", target.card.misc}, {"deckIndex", target.deckIdx}}}};
            } else preview["reason"] = followUp.reason;
        }
        candidate.followUpPreview = preview.dump();
    }
    return result;
}

LiveOocDecision LiveOocV4QPolicy::score(const sts::GameContext &projected,
                                      const PathHistory &path) const {
    return scoreLiveOocV4(projected, path, model_);
}

LiveOocMctsPolicy::LiveOocMctsPolicy(const OocStrategicTokNet &model,
                                     std::shared_ptr<const CombatTransitionSampler> sampler,
                                     const CompactTreeNet *oocWinModel)
    : model_(model), sampler_(std::move(sampler)), winModel_(oocWinModel) {}

void LiveOocMctsPolicy::setRootPrimitiveBits(const std::vector<std::uint32_t> &bits) {
    rootPrimitiveBits_ = std::set<std::uint32_t>(bits.begin(), bits.end());
    hasRootPrimitiveBits_ = true;
}

LiveOocDecision LiveOocMctsPolicy::score(const sts::GameContext &projected,
                                         const PathHistory &path) const {
    LiveOocDecision unsupportedResult;
    unsupportedResult.policy = name();
    if (!model_.ok) { unsupportedResult.reason = "MODEL_UNAVAILABLE"; return unsupportedResult; }
    if (!sampler_) { unsupportedResult.reason = "CTM_MODEL_UNAVAILABLE"; return unsupportedResult; }
    if (!winModel_ || !winModel_->ok) {
        unsupportedResult.reason = "OOC_WIN_MODEL_UNAVAILABLE";
        return unsupportedResult;
    }

    OocAdapterOptions options;
    options.sampleNoncombat = true;
    options.checkpointLeaves = true;
    if (hasRootPrimitiveBits_) options.rootPrimitiveBits = rootPrimitiveBits_;
    OocMctsDependencies dependencies;
    dependencies.policyAvailable = [this] { return model_.ok; };
    const auto policyBatch = [this](const sts::GameContext &gc, const PathHistory &history,
                                      const std::vector<sts::search::GameAction> &actions) {
        const TokState tokens = buildTokStatePure(gc, history);
        const auto prepared = model_.prepareState(tokens.glob, tokens.nDk, tokens.dk,
            tokens.nRl, tokens.rl, tokens.nPt, tokens.pt);
        std::vector<double> result;
        result.reserve(actions.size());
        for (const auto action : actions) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, action, actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entityType, entityId;
            float price;
            tokEntity(gc, action, entityType, entityId, price);
            const float entity[4] = {float(entityType == 0), float(entityType == 1),
                                     float(entityType == 2), float(entityType == 3)};
            const double logit = model_.predictPolicyLogit(prepared, action.bits, cats,
                actionType, static_cast<int>(gc.screenState), entity, entityId, price);
            if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
            result.push_back(logit);
        }
        return result;
    };
    dependencies.policyLogits = policyBatch;
    dependencies.leafValue = [this](const sts::GameContext &gc, const PathHistory &history) {
        const double value = winModel_->predict(richFeatureVec(gc, history));
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("OOC MCTS invalid native v_win value");
        return value;
    };
    dependencies.continuationStep = [policyBatch](sts::GameContext &gc, PathHistory &history,
                                           std::mt19937_64 &) {
        const auto enumeration = sts::search::enumerateOocSemanticPrimitiveBindings(gc);
        if (!enumeration.supported || !enumeration.complete || enumeration.bindings.empty())
            throw sts::search::OocSearchUnsupported("continuation_semantic_enumeration");
        std::vector<sts::search::GameAction> sources;
        std::set<std::uint32_t> seen;
        for (const auto &binding : enumeration.bindings)
            if (seen.insert(binding.primitiveBits).second)
                sources.emplace_back(binding.primitiveBits);
        std::size_t selected = 0;
        if (v4DecisionSupported(gc)) {
            const auto logits = policyBatch(gc, history, sources);
            selected = std::max_element(logits.begin(), logits.end()) - logits.begin();
        }
        sources.at(selected).execute(gc);
        history.update(gc);
    };

    try {
        OocGameContextModel provider(projected, path, sampler_, options, std::move(dependencies));
        if (provider.terminalValue(0) || provider.isLeafBoundary(0)) {
            unsupportedResult.reason = "OOC_ROOT_UNSUPPORTED";
            return unsupportedResult;
        }
        sts::search::OocMctsConfig config;
        config.seed = searchSeed_;
        const auto search = sts::search::OocMctsPlanner(config).search(provider, 0, 512);
        if (search.aborted) {
            unsupportedResult.reason = "OOC_MCTS_ABORTED:" + search.abortReason;
            return unsupportedResult;
        }
        const auto &rootActions = search.rootActions;
        if (!search.selectedAction || rootActions.empty()) {
            unsupportedResult.reason = "OOC_MCTS_EMPTY_ROOT";
            return unsupportedResult;
        }
        LiveOocDecision result;
        result.policy = name();
        result.candidates.reserve(rootActions.size());
        for (const auto &root : rootActions) {
            const auto &candidate = provider.candidate(0, root.id);
            std::string key;
            std::string payload;
            if (candidate.semantic) {
                key = canonicalOocSemanticActionKey(*candidate.semantic);
                payload = oocSemanticActionPayloadJson(*candidate.semantic);
            } else {
                const int x = candidate.primitive.getIdx1();
                const int y = projected.curMapNodeY + 1;
                key = "ooc-live:v1:map:x=" + std::to_string(x) + ":y=" + std::to_string(y);
                payload = nlohmann::json({{"type", "map_node"}, {"x", x}, {"y", y}}).dump();
            }
            const double share = search.metrics.simulations
                ? static_cast<double>(root.visits) / search.metrics.simulations : 0.0;
            result.candidates.push_back({key, payload, candidate.primitive.bits, root.q,
                                         root.visits, share, root.prior});
        }
        std::sort(result.candidates.begin(), result.candidates.end(),
            [](const auto &a, const auto &b) { return a.semanticKey < b.semanticKey; });
        const auto selected = provider.candidate(0, *search.selectedAction);
        const std::string selectedKey = selected.semantic
            ? canonicalOocSemanticActionKey(*selected.semantic)
            : "ooc-live:v1:map:x=" + std::to_string(selected.primitive.getIdx1())
                + ":y=" + std::to_string(projected.curMapNodeY + 1);
        for (int i = 0; i < static_cast<int>(result.candidates.size()); ++i) {
            if (result.candidates[i].semanticKey == selectedKey) {
                result.selectedIndex = i;
                break;
            }
        }
        if (result.selectedIndex < 0) {
            unsupportedResult.reason = "OOC_MCTS_SELECTED_ROOT_MISSING";
            return unsupportedResult;
        }
        result.supported = true;
        return result;
    } catch (const sts::search::OocSearchUnsupported &error) {
        unsupportedResult.reason = std::string("OOC_MCTS_UNSUPPORTED:") + error.what();
        return unsupportedResult;
    } catch (const std::exception &error) {
        unsupportedResult.reason = std::string("OOC_MCTS_FAILURE:") + error.what();
        return unsupportedResult;
    }
}
} // namespace one_combat
