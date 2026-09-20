#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
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
                smith = true;
            }
        }
        require(smith, "smith current-screen intent missing");
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
        std::cout << "live OOC policy contract PASS\n";
        return 0;
    } catch (const std::exception &error) {
        sts::search::g_onGameActionExecute = {};
        std::cerr << "live OOC policy contract FAIL: " << error.what() << '\n';
        return 1;
    }
}
