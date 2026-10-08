#include "ooc_test_state.h"
#include "one_combat/ooc_native_fallback.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace sts;
using namespace one_combat;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

static CompactTreeNet stump(int feature, float threshold, float below, float above,
                            bool logistic = false) {
    CompactTreeNet model;
    model.ok = true;
    model.logistic = logistic;
    model.nodes = {{feature, threshold, 1, 2}, {-1, below, 0, 0}, {-1, above, 0, 0}};
    model.roots = {0, 3};
    return model;
}

static void addTree(CompactTreeNet &model, const CompactTreeNet &tree) {
    model.nodes.insert(model.nodes.end(), tree.nodes.begin(), tree.nodes.end());
    model.roots.push_back(model.nodes.size());
}

static void sameTrace(const NativeCardWinRankTrace &a, const NativeCardWinRankTrace &b) {
    require(a.baselinePick == b.baselinePick && a.chosenPick == b.chosenPick
        && a.scenarioCount == b.scenarioCount && a.floorBase == b.floorBase
        && a.floorMarginals == b.floorMarginals && a.winEvaluated == b.winEvaluated
        && a.winBase == b.winBase && a.winMarginals == b.winMarginals,
        "changed private state or diagnostic request changed rankings/scores");
}

template<class F> static void rejects(F f, const char *message) {
    bool rejected = false;
    try { f(); } catch (const std::runtime_error &) { rejected = true; }
    require(rejected, message);
}

int main() {
    try {
        // A single initialized fixture; no traversal, combat or continuation.
        GameContext gc(CharacterClass::IRONCLAD, 0x5a17u, 0);
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer.clear();
        CardReward reward;
        reward.push_back(Card(CardId::STRIKE_RED));
        reward.push_back(Card(CardId::DEFEND_RED, 1));
        gc.info.rewardsContainer.addCardReward(reward);
        gc.monsterListOffset = 1;
        gc.eliteMonsterListOffset = 1;
        PathHistory path;
        const auto &idx = richIdxMap();
        const auto raw = richFeatureVec(gc, path);
        const int strike = idx.at("d" + std::to_string(int(CardId::STRIKE_RED)));
        const int defend = idx.at("d" + std::to_string(int(CardId::DEFEND_RED)));
        const auto floor = stump(strike, raw[strike] + .5f, 0, 2);
        const auto win = stump(defend, raw[defend] + .5f, 0, 2, true);
        const auto saved = test::oocStateFingerprint(gc);

        // Off delegates even when the optional win head is unavailable and
        // public mode differs; it does not fill a new trace or add predictions.
        CompactTreeNet unavailable;
        for (const char *publicMode : {"0", "8"}) {
            setenv("STS_OOC_PUBLIC_FUTURES", publicMode, 1);
            for (const char *setting : {static_cast<const char *>(nullptr), "0"}) {
                if (setting) setenv("STS_OOC_CARD_WIN_RANK", setting, 1);
                else unsetenv("STS_OOC_CARD_WIN_RANK");
                NativeCardWinRankTrace untouched;
                untouched.chosenPick = -77;
                resetNativeOocPublicScorerCalls();
                const int expected = nativeFloorCardPick(gc, path, floor, 0, -.5);
                const auto calls = nativeOocPublicScorerCalls();
                resetNativeOocPublicScorerCalls();
                require(nativeCardWinRankPick(gc, path, floor, unavailable, 0, -.5, &untouched) == expected
                    && nativeOocPublicScorerCalls() == calls && untouched.chosenPick == -77,
                    "default/off changed floor action, inference count or trace");
            }
        }
        setenv("STS_OOC_PUBLIC_FUTURES", "8", 1);
        setenv("STS_OOC_CARD_WIN_RANK", "1", 1);
        NativeCardWinRankTrace decision;
        resetNativeOocPublicScorerCalls();
        require(nativeCardWinRankPick(gc, path, floor, win, 0, -.5, &decision) == 1,
                "win head failed to rerank a taken reward");
        require(decision.baselinePick == 0 && decision.chosenPick == 1
            && decision.scenarioCount == 8 && decision.floorBase == 0
            && decision.floorMarginals == std::vector<double>({2, 0})
            && decision.winEvaluated && decision.winMarginals.size() == 2
            && decision.winMarginals[0] == 0 && decision.winMarginals[1] > 0
            && nativeOocPublicScorerCalls() == 2,
            "two-head trace/scenario accounting mismatch");
        require(nativeCardWinRankPick(gc, path, floor, win, 0, -.5) == decision.chosenPick,
                "trace changes decision");
        NativeCardWinRankTrace repeated;
        nativeCardWinRankPick(gc, path, floor, win, 0, -.5, &repeated);
        sameTrace(decision, repeated);

        const auto skipFloor = stump(idx.at("deckSize"), raw[idx.at("deckSize")] + .5f, 0, -1);
        resetNativeOocPublicScorerCalls();
        NativeCardWinRankTrace skip;
        require(nativeFloorCardPick(gc, path, skipFloor, 0, -.5) == 5, "skip fixture not baseline skip");
        resetNativeOocPublicScorerCalls();
        require(nativeCardWinRankPick(gc, path, skipFloor, win, 0, -.5, &skip) == 5
            && skip.baselinePick == 5 && skip.chosenPick == 5 && !skip.winEvaluated
            && skip.winMarginals.empty() && skip.floorMarginals == std::vector<double>({-1, -1})
            && nativeOocPublicScorerCalls() == 1, "win head changed baseline skip or was evaluated after skip");

        const auto equalFloor = stump(strike, raw[strike] + .5f, 0, 0);
        const auto equalWin = stump(defend, raw[defend] + .5f, 0, 0, true);
        require(nativeCardWinRankPick(gc, path, equalFloor, equalWin, 0, 0) == 0,
                "strict maximum tie order or equal-threshold take changed");
        require(nativeCardWinRankPick(gc, path, equalFloor, equalWin, 0, .01) == 5,
                "equal-card baseline skip changed");
        const auto negativeWin = stump(idx.at("deckSize"), raw[idx.at("deckSize")] + .5f, 0, -2, true);
        NativeCardWinRankTrace negative;
        require(nativeCardWinRankPick(gc, path, floor, negativeWin, 0, -.5, &negative) == 0
            && negative.winMarginals[0] < 0 && negative.winMarginals[1] < 0,
            "negative win marginals introduced a win-head skip threshold");

        // Shared scenarios and post-link averaging: infer scenario mass from
        // the non-logistic head, then check the logistic mixture analytically.
        CompactTreeNet hiddenFloor;
        double highMass = 0;
        bool mixed = false;
        for (float split = .5f; split < 100 && !mixed; split += 1) {
            hiddenFloor = stump(idx.at("nextFight0"), split, -2, 3);
            highMass = (nativeOocValue(gc, path, hiddenFloor) + 2) / 5;
            mixed = highMass > 0 && highMass < 1;
        }
        require(mixed, "fixture needs nondegenerate public encounter mixture");
        auto hiddenWin = hiddenFloor;
        hiddenWin.logistic = true;
        addTree(hiddenWin, stump(defend, raw[defend] + .5f, 0, 2));
        NativeCardWinRankTrace mixture;
        require(nativeCardWinRankPick(gc, path, hiddenFloor, hiddenWin, 0, -.5, &mixture) == 1,
                "hidden-sensitive win head failed to rank");
        const auto sigmoid = [](double x) { return 1 / (1 + std::exp(-x)); };
        const double expectedBase = (1-highMass)*sigmoid(-2) + highMass*sigmoid(3);
        const double expectedCard = (1-highMass)*sigmoid(0) + highMass*sigmoid(5);
        require(std::abs(mixture.winBase-expectedBase) < 1e-14
            && std::abs(mixture.winMarginals[1]-(expectedCard-expectedBase)) < 1e-14
            && mixture.winMarginals[0] == 0,
            "heads/candidates did not share futures or logistic predictions were averaged incorrectly");

        auto changed = gc;
        changed.seed ^= 0xcafebabedeadbeefULL;
        for (auto stream : {&changed.aiRng, &changed.cardRandomRng, &changed.cardRng,
                &changed.eventRng, &changed.mathUtilRng, &changed.merchantRng, &changed.miscRng,
                &changed.monsterHpRng, &changed.monsterRng, &changed.neowRng, &changed.potionRng,
                &changed.relicRng, &changed.shuffleRng, &changed.treasureRng}) {
            stream->seed0 ^= 12345; stream->seed1 ^= 67890; stream->counter += 17;
        }
        std::reverse(changed.monsterList.begin()+changed.monsterListOffset, changed.monsterList.end());
        std::reverse(changed.eliteMonsterList.begin()+changed.eliteMonsterListOffset, changed.eliteMonsterList.end());
        const auto changedSaved = test::oocStateFingerprint(changed);
        NativeCardWinRankTrace changedDecision;
        nativeCardWinRankPick(changed, path, hiddenFloor, hiddenWin, 0, -.5, &changedDecision);
        sameTrace(mixture, changedDecision);
        require(saved == test::oocStateFingerprint(gc) && changedSaved == test::oocStateFingerprint(changed),
                "pure card-head scoring mutated source state/RNG");

        auto badFloor = skipFloor;
        badFloor.baseMargin = std::numeric_limits<double>::quiet_NaN();
        rejects([&] { nativeCardWinRankPick(gc, path, badFloor, win, 0, -.5); }, "nonfinite floor baseline accepted");
        auto empty = gc;
        empty.info.rewardsContainer.cardRewards[0].clear();
        require(nativeCardWinRankPick(empty, path, floor, win, 0, -.5) == 5,
                "empty offer no longer preserves baseline skip");
        // Each returned tree prediction is finite, but the public mixture's
        // sum overflows. Check its used base even when no candidate is scored.
        auto overflowFloor = equalFloor;
        overflowFloor.baseMargin = std::numeric_limits<double>::max();
        rejects([&] { nativeCardWinRankPick(empty, path, overflowFloor, win, 0, -.5); },
                "nonfinite public-mixture base accepted on an empty offer");
        auto badWin = win;
        // The loader rejects malformed trees. A synthetic legal-index cycle
        // exercises predict's explicit NaN return before its logistic clamp.
        badWin.nodes[0].yes = 0;
        rejects([&] { nativeCardWinRankPick(gc, path, floor, badWin, 0, -.5); }, "nonfinite win prediction accepted");
        auto badWinCard = win;
        badWinCard.nodes[0].no = 0;
        rejects([&] { nativeCardWinRankPick(gc, path, floor, badWinCard, 0, -.5); }, "nonfinite win card accepted");
        auto badCandidate = floor;
        badCandidate.nodes[2].thr = std::numeric_limits<float>::quiet_NaN();
        rejects([&] { nativeCardWinRankPick(gc, path, badCandidate, win, 0, -.5); }, "nonfinite floor card accepted");
        auto notLogistic = win; notLogistic.logistic = false;
        rejects([&] { nativeCardWinRankPick(gc, path, floor, notLogistic, 0, -.5); }, "nonlogistic win head accepted");
        rejects([&] { nativeCardWinRankPick(gc, path, floor, unavailable, 0, -.5); }, "unloaded win head accepted");
        rejects([&] { nativeCardWinRankPick(gc, path, floor, win, -1, -.5); }, "negative reward index accepted");
        rejects([&] { nativeCardWinRankPick(gc, path, floor, win, 1, -.5); }, "out-of-range reward index accepted");
        rejects([&] { nativeCardWinRankPick(gc, path, floor, win, 0,
            std::numeric_limits<double>::quiet_NaN()); }, "nonfinite floor threshold accepted");
        auto wrongScreen = gc;
        wrongScreen.screenState = ScreenState::MAP_SCREEN;
        rejects([&] { nativeCardWinRankPick(wrongScreen, path, floor, win, 0, -.5); }, "wrong screen accepted");
        for (const char *mode : {"0", "4", "16"}) {
            setenv("STS_OOC_PUBLIC_FUTURES", mode, 1);
            rejects([&] { nativeCardWinRankPick(gc, path, floor, win, 0, -.5); }, "non-public8 enabled mode accepted");
        }
        setenv("STS_OOC_PUBLIC_FUTURES", "8", 1);
        for (const char *invalid : {"", "2", "-1", "true", "01", " 1"}) {
            setenv("STS_OOC_CARD_WIN_RANK", invalid, 1);
            rejects([] { nativeOocCardWinRankEnabled(); }, "malformed card-rank flag accepted");
        }
        unsetenv("STS_OOC_CARD_WIN_RANK");
        require(!nativeOocCardWinRankEnabled(), "unset card rank enabled");
        setenv("STS_OOC_CARD_WIN_RANK", "0", 1);
        require(!nativeOocCardWinRankEnabled(), "zero card rank enabled");
        unsetenv("STS_OOC_CARD_WIN_RANK");
        unsetenv("STS_OOC_PUBLIC_FUTURES");
        std::cout << "native_ooc_card_win_rank PASS: default delegation, fixed floor skip, win rerank, ties, shared public mixture, post-link mean, private RNG invariance, purity, fail-closed predictions/config\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
