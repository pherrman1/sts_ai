#include "live_ooc_policy.h"
#include "live_ooc_state.h"
#include "ooc_v4_encoding.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <nlohmann/json.hpp>
#include "../ooc_strategic_tok_net.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/ScumSearchAgent2.h"
#include "constants/SaveFileMappings.h"
#include "ooc_checkpoint_policy.h"
#include "ooc_native_fallback.h"
#include "heart1_policy.h"
#include "heart_leaf.h"
#include "run_driver.h"
#include "sim/search/RunGoal.h"

#include <cstdlib>

extern bool g_collectKeys;

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
} // namespace


LiveOocDecision scoreLiveOocV4(const sts::GameContext &projected, const PathHistory &path,
                             const OocStrategicTokNet &model, bool rewardPityHistoryComplete) {
    if (!rewardPityHistoryComplete)
        return unsupported("PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED");
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
            auto identity = currentLiveOocIdentity(binding);
            const auto existing = identities.find(binding.primitiveBits);
            if (existing != identities.end()) {
                // A compound source opens one selector and therefore has one
                // source primitive with several possible retained physical
                // targets. Keep the canonical first target for the one-screen
                // V4 source score; MCTS retains its target-specific semantic
                // candidate. A duplicate non-compound mapping is still an
                // integration error.
                if (binding.compoundSelector == CardSelectScreenType::INVALID
                        || existing->second.first.find(":current-screen") == std::string::npos)
                    return unsupported("AMBIGUOUS_SEMANTIC_MAPPING");
                continue;
            }
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
                                      const PathHistory &path, int) const {
    return scoreLiveOocV4(projected, path, model_, rewardPityHistoryComplete_);
}

bool liveOocEnvChoice(const char *key, const char *off, const char *on, bool fallback) {
    const char *raw = std::getenv(key);
    if (!raw) return fallback;
    const std::string value(raw);
    if (value == on) return true;
    if (value == off) return false;
    throw std::invalid_argument(std::string(key) + " must be " + off + " or " + on);
}

bool liveOocResearchStack() {
    const char *raw = std::getenv("STS_LIVE_OOC_RESEARCH_STACK");
    if (!raw) return true;
    const std::string value(raw);
    if (value == "1") return true;
    if (value == "0") return false;
    throw std::invalid_argument("STS_LIVE_OOC_RESEARCH_STACK must be 0 or 1");
}

bool liveOocA20LeafCalibration() {
    const char *raw = std::getenv("STS_OOC_MCTS_LEAF_CALIBRATION");
    if (!raw || !*raw) return true;
    if (std::string(raw) == "0") return false;
    throw std::invalid_argument("STS_OOC_MCTS_LEAF_CALIBRATION must be unset or 0 in the live advisor");
}

LiveOocMctsPolicy::LiveOocMctsPolicy(const OocStrategicTokNet &model,
                                     std::shared_ptr<const CombatTransitionSampler> sampler,
                                     const CompactTreeNet *oocWinModel,
                                     const CompactTreeNet *oocFloorModel,
                                     std::shared_ptr<const heart1::Net> armC,
                                     std::shared_ptr<const CombatTransitionSampler> samplerA20)
    : model_(model), sampler_(std::move(sampler)), samplerA20_(std::move(samplerA20)),
      winModel_(oocWinModel), floorModel_(oocFloorModel), armC_(std::move(armC)) {
    // ADR-0057: M0 was fit on the pinned public X2-B. B0, another win model, or one without a readable file keeps the
    // raw anchor.
    if (a20LeafCalibration_) {
        try {
            a20LeafCalibration_ = winModel_ && winModel_->ok && fileSha256Hex(winModel_->path) == kHeartLeafAnchorSha256;
        } catch (const std::runtime_error &) {
            a20LeafCalibration_ = false;
        }
    }
}

void LiveOocMctsPolicy::setRootPrimitiveBits(const std::vector<std::uint32_t> &bits) {
    rootPrimitiveBits_ = std::set<std::uint32_t>(bits.begin(), bits.end());
    hasRootPrimitiveBits_ = true;
}

LiveOocDecision LiveOocMctsPolicy::score(const sts::GameContext &projected,
                                         const PathHistory &path, int currentActEventVisits) const {
    LiveOocDecision unsupportedResult;
    unsupportedResult.policy = name();
    if (!model_.ok) { unsupportedResult.reason = "MODEL_UNAVAILABLE"; return unsupportedResult; }
    if (!sampler_) { unsupportedResult.reason = "CTM_MODEL_UNAVAILABLE"; return unsupportedResult; }
    if (!winModel_ || !winModel_->ok) {
        unsupportedResult.reason = "OOC_WIN_MODEL_UNAVAILABLE";
        return unsupportedResult;
    }
    if (!floorModel_ || !floorModel_->ok) {
        unsupportedResult.reason = "OOC_FLOOR_MODEL_UNAVAILABLE";
        return unsupportedResult;
    }

    OocAdapterOptions options;
    options.sampleNoncombat = true;
    options.checkpointLeaves = true;
    options.heart1Prior = bool(armC_);
    // ADR-0041: the terminal objective and every rule below share the
    // process key setting (STS_COLLECT_KEYS, default on).
    options.collectKeys = g_collectKeys;
    if (researchStack_) {
        // The A20 research stack (§504 control, §522 arm C): rollout3 with
        // the student's leaf policy, the heart1full prior (ADR-0042), tree
        // rules and merging (ADR-0031), greedy rollout shops (ADR-0032).
        options.leafCombats = 3;
        options.treeRules = true;
        options.greedyRolloutShop = true;
        options.heart1Coverage = options.heart1LeafPolicy = bool(armC_);
        // ADR-0047: card-select student weights (x_act input, student_sel.bin) also score compound
        // targets in the tree and card selects in rollouts. STS_OOC_MCTS_TARGET_PRIOR=0 /
        // STS_OOC_MCTS_LEAF_SELECTS=chain turn them off, =1 / =heart1 force them on.
        const bool selectStudent = armC_ && armC_->extraInputs();
        options.targetPrior = liveOocEnvChoice("STS_OOC_MCTS_TARGET_PRIOR", "0", "1", selectStudent) && armC_;
        options.heart1LeafSelects = liveOocEnvChoice("STS_OOC_MCTS_LEAF_SELECTS", "chain", "heart1", selectStudent) && armC_;
    }
    // Qualified public question-room history reconstructs the native chance
    // counters; successors update those counters through normal transitions.
    options.stopAtMapCheckpoint = !mapHistoryComplete_;
    // ADR-0057: at ascension 20 the X2-B anchor at rollout3 ends becomes calibrated Heart probability (M0), as
    // offline. Leaves that stop at the map checkpoint keep the raw anchor.
    if (researchStack_ && a20LeafCalibration_ && !options.stopAtMapCheckpoint) {
        options.leafCalibration = a20LeafCalibration();
        options.leafCalibrationMinAscension = 20;
    }
    if (hasRootPrimitiveBits_) options.rootPrimitiveBits = rootPrimitiveBits_;
    OocMctsDependencies dependencies;
    if (armC_) {
        dependencies.heart1PolicyLogits = [this](const sts::GameContext &gc,
                const std::vector<sts::search::GameAction> &actions,
                std::map<std::string, std::uint64_t> *tally) {
            return heart1::priorLogits(*armC_, gc, actions, tally);
        };
    }
    const int observedEventRooms = currentActEventVisits;
    const bool questionHistoryComplete = questionHistoryComplete_;
    const auto questionPosterior = questionChancePosterior_;
    const bool exactPity = exactRewardPity_;
    dependencies.sampleHiddenCounters = [observedEventRooms, questionHistoryComplete, questionPosterior, exactPity](
                                            sts::GameContext &gc, std::mt19937_64 &rng) {
        // Exact reward pity counters (#636) are kept; the sampler still
        // consumes its draws so room-chance particles stay unchanged.
        const int potionChance = gc.potionChance, cardRarityFactor = gc.cardRarityFactor;
        sampleLiveOocHiddenCounters(gc, rng, observedEventRooms, questionHistoryComplete);
        if (exactPity) { gc.potionChance = potionChance; gc.cardRarityFactor = cardRarityFactor; }
        sampleQuestionChancePosterior(gc,rng,questionPosterior);
    };
    // The deployed CTM was trained with the ordinary fixed search keep value.
    // Omitting this dependency falls back to zero, far outside that input domain.
    dependencies.potionKeepValue = [](const sts::GameContext &) { return 4.0; };
    dependencies.policyAvailable = [this] { return model_.ok; };
    const auto policyBatch = [this](const sts::GameContext &gc, const PathHistory &history,
                                      const std::vector<sts::search::GameAction> &actions) {
        if (!rewardPityHistoryComplete_)
            // Pity is a feature of the deployed V4 prior. Returning equal
            // logits is the public-information prior; it avoids turning an
            // unqualified hidden counter into a fake point estimate while the
            // exact marginalized v_win leaf still evaluates each particle.
            return std::vector<double>(actions.size(), 0.0);
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
        // With an exact pity history (#636) every particle carries the real
        // counters forward through native transitions; evaluate them directly.
        if (exactRewardPity_) {
            const double value = winModel_->predict(richFeatureVec(gc, history));
            if (!std::isfinite(value) || value < 0 || value > 1)
                throw std::runtime_error("OOC MCTS invalid native v_win value");
            return value;
        }
        // Without it, potionChance and cardRarityFactor are unknown.  Do not
        // evaluate every particle at the constructor's 0/5 point prior: v_win
        // explicitly splits on both
        // features.  Integrate each tree margin over the native reachable
        // public-belief ranges instead.  The leaf remains deterministic and
        // cheap enough for 512-simulation live searches, while no single
        // hidden pity state is presented as observed fact.
        static const std::vector<CompactTreeNet::MarginalFeature> pityPrior = {
            {7, -40, 60, 10},    // potionChance
            {8, -40, 5, 1},      // cardRarityFactor
        };
        const double value = winModel_->predictMarginalized(richFeatureVec(gc, history), pityPrior);
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("OOC MCTS invalid native v_win value");
        return value;
    };
    dependencies.continuationStep = [this](sts::GameContext &gc, PathHistory &history,
                                           std::mt19937_64 &) {
        // Required key choices precede every other rule (ADR-0041); the
        // free-reward rule would take Sapphire's paired relic first.
        if (const auto key = sts::search::heartKeyAction(gc, g_collectKeys)) {
            key->execute(gc);
            history.update(gc);
            return;
        }
        if (collectFreeOocReward(gc, g_collectKeys)) { history.update(gc); return; }
        // The default simulator checkpoint chain uses these same native
        // compact-tree fallback decisions after its V4 gate. The shared
        // functions prevent a second shop/rest/card policy from drifting.
        if (gc.screenState == ScreenState::SHOP_ROOM) {
            nativeFloorShopStep(gc, history, *floorModel_);
            history.update(gc);
            return;
        }
        if (gc.screenState == ScreenState::REST_ROOM
                && nativeWinRestStep(gc, history, *winModel_, g_collectKeys)) {
            history.update(gc);
            return;
        }
        if (gc.screenState == ScreenState::CARD_SELECT
                && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            nativeWinUpgradeSelectStep(gc, history, *winModel_);
            history.update(gc);
            return;
        }
        if (gc.screenState == ScreenState::CARD_SELECT && gc.curRoom == Room::SHOP
                && gc.info.selectScreenType == CardSelectScreenType::REMOVE) {
            std::vector<int> ids;
            for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
                ids.push_back(static_cast<int>(gc.info.toSelectCards[i].card.getId()));
            const int choice = ids.empty() ? 0 : nativeFloorRemovePick(gc, history, *floorModel_, ids);
            sts::search::GameAction(choice, 0).execute(gc);
            history.update(gc);
            return;
        }
        // The simulator's V4 gate is enabled by default only for card
        // rewards. Other supported screens use the same fallback agent.
        if (gc.screenState != ScreenState::REWARDS) {
            sts::search::ScumSearchAgent2 fallback;
            fallback.rng.seed(0);
            fallback.stepOutOfCombatPolicy(gc);
            history.update(gc);
            return;
        }
        if (!takeQualifiedV4CardReward(gc, history, model_, 1.0)) {
            auto &rewards = gc.info.rewardsContainer;
            while (rewards.cardRewardCount > 0) {
                const int group = rewards.cardRewardCount - 1;
                const int choice = nativeFloorCardPick(gc, history, *floorModel_, group, -0.5);
                sts::search::GameAction(sts::search::GameAction::RewardsActionType::CARD,
                                        group, choice).execute(gc);
            }
        }
        history.update(gc);
    };

    try {
        const auto sampler = projected.ascension == 20 && samplerA20_ ? samplerA20_ : sampler_;
        OocGameContextModel provider(projected, path, sampler, options, std::move(dependencies));
        if (provider.terminalValue(0) || provider.isLeafBoundary(0)) {
            unsupportedResult.reason = "OOC_ROOT_UNSUPPORTED";
            return unsupportedResult;
        }
        sts::search::OocMctsConfig config;
        config.seed = searchSeed_;
        config.captureTree = captureTree_;
        config.captureValueDistribution = true;
        config.treeNodeCap = treeNodeCap_;
        // Issue #633: prune an unsupported edge instead of aborting the root; =0 restores the abort.
        config.pruneUnsupported = liveOocEnvChoice("STS_OOC_MCTS_PRUNE_UNSUPPORTED", "0", "1", true);
        if (researchStack_) {
            config.cPuct = 1.5;
            config.wideningK = 4;
            config.wideningAlpha = 0.75;
            config.maxDepth = 32;
            config.selectByMeanQ = false;
            config.allowUnqualifiedRootStop = true;
            config.mergeEquivalentOutcomes = true;
        }
        const auto search = searchWithSoleRootShortcut(provider, config, provider.soleLegalAction(0), 512);
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
        result.trivialRootBypass = search.metrics.trivialRootBypasses != 0;
        result.tree = search.tree;
        if (!result.trivialRootBypass) {
            result.valueDistribution = search.rootValues.value_or(sts::search::OocValueDistribution{});
            result.hpDistribution = search.rootHp.value_or(sts::search::OocHpDistribution{});
        }
        result.rootHp = projected.curHp;
        result.rootMaxHp = projected.maxHp;
        result.rootFloor = projected.floorNum;
        result.searchModel = {{"ctmStackScope", projected.ascension == 20 && samplerA20_ ? "ascension20" : "base"},
            {"searchStack", researchStack_ ? "a20_research" : "legacy"}, {"collectKeys", options.collectKeys},
            {"leafCombats", options.leafCombats}, {"treeRules", options.treeRules},
            {"wideningK", config.wideningK}, {"wideningAlpha", config.wideningAlpha}, {"maxDepth", config.maxDepth},
            {"pruneUnsupported", config.pruneUnsupported}, {"prunedActions", search.metrics.prunedActions}};
        if (!options.leafCalibration.empty() && projected.ascension >= options.leafCalibrationMinAscension)
            result.searchModel["leafCalibration"] = options.leafCalibration;
        if (armC_) {
            const auto &metrics = provider.continuationMetrics();
            result.searchModel.update({{"prior", options.heart1Coverage ? "arm_c_full" : "arm_c"},
                {"rolloutPolicy", options.heart1LeafPolicy ? "arm_c" : "v4_chain"},
                {"targetPrior", options.targetPrior}, {"rolloutSelects", options.heart1LeafSelects ? "arm_c" : "chain"},
                {"armCPriorNodes", metrics.heart1PriorNodes},
                {"armCPriorFallbacks", metrics.heart1PriorFallbacks},
                {"armCPriorReasons", metrics.heart1PriorReasons},
                {"armCLeafSteps", metrics.heart1LeafSteps}, {"armCLeafFallbacks", metrics.heart1LeafFallbacks}});
        }
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
            const auto values = search.actionValues.find(root.id);
            if (!result.trivialRootBypass) result.candidates.back().valueDistribution = values == search.actionValues.end()
                ? sts::search::OocValueDistribution{} : values->second;
            const auto hp = search.actionHp.find(root.id);
            if (!result.trivialRootBypass) result.candidates.back().hpDistribution = hp == search.actionHp.end()
                ? sts::search::OocHpDistribution{} : hp->second;
        }
        if (result.tree) annotateOocTree(provider, *result.tree);
        std::sort(result.candidates.begin(), result.candidates.end(),
            [](const auto &a, const auto &b) { return a.semanticKey < b.semanticKey; });
        const auto selected = provider.candidate(0, *search.selectedAction);
        const std::string selectedKey = selected.semantic
            ? canonicalOocSemanticActionKey(*selected.semantic)
            : "ooc-live:v1:map:x=" + std::to_string(selected.primitive.getIdx1())
                + ":y=" + std::to_string(projected.curMapNodeY + 1);
        if (result.tree) for (auto &node : result.tree->nodes)
            node.selected = node.chance && node.depth == 0 && node.action == *search.selectedAction;
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
