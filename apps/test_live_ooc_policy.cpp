#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <nlohmann/json.hpp>

#include "ooc_test_state.h"
#include "ooc_strategic_tok_net.h"
#include "one_combat/live_ooc_policy.h"
#include "one_combat/ooc_v4_encoding.h"

namespace {
void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}
}

int main(int argc, char **argv) {
    try {
        using namespace sts;
        using namespace sts::search;
        using namespace one_combat;
        // One fixed native fixture seed, no campaign traversal.
        GameContext gc(CharacterClass::IRONCLAD, 0x51514Du, 0);
        gc.screenState = ScreenState::REST_ROOM;
        gc.curHp = 40;
        const PathHistory path{};
        auto model = std::make_unique<OocStrategicTokNet>();
        const auto missingModel = scoreLiveOocV4(gc, path, *model);
        require(!missingModel.supported && missingModel.reason == "MODEL_UNAVAILABLE"
                && missingModel.selectedIndex == -1, "missing model accepted");
        require(missingModel.candidates.size() == v4CandidateActions(gc).size(),
                "missing model did not retain current candidates for mapping validation");
        model->ok = true; // zero weights give exact ties for every action

        GameContext shop = gc;
        shop.screenState = ScreenState::SHOP_ROOM;
        shop.gold = 200;
        for (int i = 0; i < 7; ++i) shop.info.shop.cardPrice(i) = -1;
        for (int i = 0; i < 3; ++i) shop.info.shop.potionPrice(i) = -1;
        shop.info.shop.removeCost = -1;
        shop.info.shop.relics[0] = RelicId::PRISMATIC_SHARD;
        shop.info.shop.relicPrice(0) = 50;
        shop.info.shop.relics[1] = RelicId::ANCHOR;
        shop.info.shop.relicPrice(1) = 50;
        shop.info.shop.relicPrice(2) = -1;
        const auto allShopActions = search::GameAction::getAllActionsInState(shop);
        const auto shopCandidates = v4CandidateActions(shop);
        const auto isRelic = [](const auto &action) {
            return action.getRewardsActionType() == search::GameAction::RewardsActionType::RELIC
                && action.getIdx1() >= 0 && action.getIdx1() < 3;
        };
        require(std::any_of(allShopActions.begin(), allShopActions.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "shop fixture did not expose Prismatic Shard");
        require(std::none_of(shopCandidates.begin(), shopCandidates.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "Prismatic Shard remained an autonomous OOC candidate");
        require(std::any_of(shopCandidates.begin(), shopCandidates.end(), [&](const auto &action) {
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::ANCHOR;
                }), "normal relic was removed with Prismatic Shard");
        require(std::any_of(shopCandidates.begin(), shopCandidates.end(), [](const auto &action) {
                    return action.getRewardsActionType() == search::GameAction::RewardsActionType::SKIP;
                }), "shop leave action was removed with Prismatic Shard");
        const auto shopDecision = scoreLiveOocV4(shop, path, *model);
        require(shopDecision.supported, "shop with Prismatic Shard became unsupported: " + shopDecision.reason);
        require(std::none_of(shopDecision.candidates.begin(), shopDecision.candidates.end(), [&](const auto &candidate) {
                    const auto action = search::GameAction(candidate.primitiveBits);
                    return isRelic(action)
                        && shop.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
                }), "scored OOC candidates still contain Prismatic Shard");

        const auto before = test::oocStateFingerprint(gc);
        int callbacks = 0;
        g_onGameActionExecute = [&](std::uint32_t, const GameContext *) { ++callbacks; };
        LiveOocV4QPolicy provider(*model);
        const auto decision = provider.score(gc, path);
        g_onGameActionExecute = {};
        require(decision.supported, "campfire score failed: " + decision.reason);
        require(before == test::oocStateFingerprint(gc) && callbacks == 0,
                "read-only scoring mutated state/RNG or executed a primitive");
        require(decision.selectedIndex == 0, "ties do not choose first canonical key");
        require(decision.candidates.size() == v4CandidateActions(gc).size(), "candidate count changed");
        bool smith = false;
        for (std::size_t i = 0; i < decision.candidates.size(); ++i) {
            const auto &candidate = decision.candidates[i];
            require(candidate.q == 0.0, "zero model did not tie");
            if (i) require(decision.candidates[i-1].semanticKey < candidate.semanticKey,
                           "canonical identities not strictly sorted");
            if (candidate.primitiveBits == GameAction(1).bits) {
                const auto payload = nlohmann::json::parse(candidate.payload);
                require(payload.at("currentScreenOnly") == true && payload.at("type") == "none"
                        && !payload.contains("card"), "smith returned a target or compound plan");
                const auto preview = nlohmann::json::parse(candidate.followUpPreview);
                require(preview.at("status") == "OK" && preview.at("scope") == "selector_preview"
                        && preview.at("policy") == "v4_q" && !preview.contains("liveAction"),
                        "smith preview is not a separate display-only selector decision");
                smith = true;
            }
        }
        require(smith, "smith current-screen intent missing");
        auto wall = gc;
        wall.screenState = ScreenState::EVENT_SCREEN;
        wall.curEvent = Event::LIVING_WALL;
        const auto wallBefore = test::oocStateFingerprint(wall);
        const auto wallDecision = provider.score(wall, path);
        require(wallDecision.supported && wallBefore == test::oocStateFingerprint(wall),
                "Living Wall preview changed native state");
        auto selector = wall;
        selector.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
        const auto selectorDecision = provider.score(selector, path);
        require(selectorDecision.supported, "direct upgrade selector unavailable");
        const auto &selectorBest = selectorDecision.candidates.at(selectorDecision.selectedIndex);
        const int expectedDeckIndex = selector.info.toSelectCards[GameAction(selectorBest.primitiveBits).getIdx1()].deckIdx;
        std::set<int> physicalDeckIndices;
        for (const auto &candidate : selectorDecision.candidates)
            physicalDeckIndices.insert(selector.info.toSelectCards[GameAction(candidate.primitiveBits).getIdx1()].deckIdx);
        require(physicalDeckIndices.size() == static_cast<std::size_t>(selector.deck.size()),
                "duplicate physical upgrade cards were collapsed");
        for (const auto &candidate : wallDecision.candidates) {
            const auto preview = nlohmann::json::parse(candidate.followUpPreview);
            if (candidate.primitiveBits == GameAction(2).bits) {
                require(preview.at("status") == "OK" && preview.at("q") == selectorBest.q
                        && preview.at("semanticKey") == selectorBest.semanticKey
                        && preview.at("card").at("deckIndex") == expectedDeckIndex,
                        "Living Wall upgrade preview differs from separate native selector");
            } else require(preview.at("status") == "UNSUPPORTED"
                        && preview.at("reason") == "V4_SELECTOR_UNSUPPORTED"
                        && !preview.contains("q") && !preview.contains("card"),
                        "remove/transform preview invented a scored target");
        }
        model->q2b = std::numeric_limits<float>::infinity();
        require(scoreLiveOocV4(gc, path, *model).reason == "NONFINITE_Q", "infinite Q accepted");
        model->q2b = std::numeric_limits<float>::quiet_NaN();
        require(scoreLiveOocV4(gc, path, *model).reason == "NONFINITE_Q", "NaN Q accepted");
        model->q2b = 0;
        gc.outcome = GameOutcome::PLAYER_VICTORY;
        require(scoreLiveOocV4(gc, path, *model).reason == "EMPTY_CANDIDATE_SET", "empty candidates accepted");
        gc.outcome = GameOutcome::UNDECIDED;
        gc.screenState = ScreenState::CARD_SELECT;
        gc.info.selectScreenType = CardSelectScreenType::REMOVE;
        require(scoreLiveOocV4(gc, path, *model).reason == "V4_SCREEN_UNSUPPORTED", "removal support widened");
        gc.info.selectScreenType = CardSelectScreenType::UPGRADE;
        gc.info.toSelectCount = 2;
        gc.info.toSelectCards.clear();
        gc.info.toSelectCards.push_back(SelectScreenCard(gc.deck.cards[0], 0));
        require(scoreLiveOocV4(gc, path, *model).reason.rfind("SEMANTIC_ENUMERATION_FAILURE:", 0) == 0,
                "malformed selector cardinality was classified as fallback-safe unsupported");
        model->ok = false;
        require(scoreLiveOocV4(gc, path, *model).reason.rfind("SEMANTIC_ENUMERATION_FAILURE:", 0) == 0,
                "missing model hid malformed semantic enumeration");
        model->ok = true;
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer = {};
        require(scoreLiveOocV4(gc, path, *model).reason == "V4_SCREEN_UNSUPPORTED", "non-card reward support widened");
        auto &rewards = gc.info.rewardsContainer;
        rewards.cardRewardCount = 1;
        rewards.cardRewards[0].push_back(Card(CardId::BASH));
        rewards.goldRewardCount = 2;
        rewards.gold[0] = 20;
        rewards.gold[1] = 30;
        require(scoreLiveOocV4(gc, path, *model).reason == "CANDIDATE_ENUMERATION_DISAGREEMENT",
                "duplicate native primitive enumeration accepted");

        require(argc == 2 && model->load(argv[1]), "tracked V4 model failed to load");
        gc.screenState = ScreenState::REST_ROOM;
        const auto actual = scoreLiveOocV4(gc, path, *model);
        require(actual.supported, "tracked model scoring failed: " + actual.reason);
        const auto tokens = buildTokStatePure(gc, path);
        for (const auto &candidate : actual.candidates) {
            const GameAction action(candidate.primitiveBits);
            int type, c1, c2, c3, v1, v2, v3, entityType, entityId;
            float goldGePrice;
            strategicCands(gc, action, type, c1, c2, c3, v1, v2, v3);
            const int cats[6] = {c1, c2, c3, v1, v2, v3};
            tokEntity(gc, action, entityType, entityId, goldGePrice);
            const float entity[4] = {float(entityType == 0), float(entityType == 1),
                                     float(entityType == 2), float(entityType == 3)};
            const double expected = model->predictActionValue(tokens.glob, tokens.nDk, tokens.dk,
                tokens.nRl, tokens.rl, tokens.nPt, tokens.pt, action.bits, cats, type,
                int(gc.screenState), entity, entityId, goldGePrice);
            require(candidate.q == expected, "prepared scorer differs from direct V4 Q");
        }
        GameContext pending(CharacterClass::IRONCLAD, 991, 0);
        pending.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        pending.regainControlAction = [](GameContext &state) {
            state.screenState = ScreenState::MAP_SCREEN;
            state.regainControlAction = nullptr;
        };
        bool leafSawMap = false;
        OocMctsDependencies deps;
        deps.policyAvailable = [] { return true; };
        deps.policyLogits = [](const GameContext &, const PathHistory &,
                               const std::vector<GameAction> &actions) {
            return std::vector<double>(actions.size(), 0.0);
        };
        deps.leafValue = [&](const GameContext &state, const PathHistory &) {
            leafSawMap = state.screenState == ScreenState::MAP_SCREEN;
            return 0.25;
        };
        deps.continuationStep = [](GameContext &state, PathHistory &, std::mt19937_64 &) {
            const auto semantic = enumerateOocSemanticPrimitiveBindings(state);
            if (!semantic.supported || !semantic.complete || semantic.bindings.empty())
                throw OocSearchUnsupported("test continuation enumeration");
            GameAction(semantic.bindings.front().primitiveBits).execute(state);
        };
        OocAdapterOptions checkpoint;checkpoint.checkpointLeaves=true;
        OocGameContextModel checkpointModel(pending, path, {}, checkpoint, std::move(deps));
        std::mt19937_64 checkpointRng(17);
        require(checkpointModel.evaluateLeaf(0, checkpointRng) == 0.25 && leafSawMap
                && checkpointModel.continuationMetrics().projectionSteps > 0,
                "advisor checkpoint leaf evaluated an unresolved selector");
        std::cout << "live OOC policy contract PASS\n";
        return 0;
    } catch (const std::exception &error) {
        sts::search::g_onGameActionExecute = {};
        std::cerr << "live OOC policy contract FAIL: " << error.what() << '\n';
        return 1;
    }
}
