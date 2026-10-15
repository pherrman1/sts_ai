#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

#include "ooc_test_state.h"
#include "one_combat/ooc_native_fallback.h"

namespace {
void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// A real, valid compact tree whose card marginal changes sign across the
// unrevealed encounter split. This makes a leaked action observable.
one_combat::CompactTreeNet cardModel(int hidden, float hiddenThreshold,
                                     int card, float cardThreshold) {
    one_combat::CompactTreeNet model;
    model.ok = true;
    model.logistic = false;
    model.nodes = {{hidden, hiddenThreshold, 1, 4},
                   {card, cardThreshold, 2, 3}, {-1, 0, 0, 0}, {-1, 2, 0, 0},
                   {card, cardThreshold, 5, 6}, {-1, 0, 0, 0}, {-1, -2, 0, 0}};
    model.roots = {0, model.nodes.size()};
    return model;
}

sts::GameContext changedHidden(const sts::GameContext &source) {
    auto changed = source;
    changed.seed ^= 0xcafebabedeadbeefULL;
    for (auto stream : {&changed.aiRng, &changed.cardRandomRng, &changed.cardRng,
            &changed.eventRng, &changed.mathUtilRng, &changed.merchantRng, &changed.miscRng,
            &changed.monsterHpRng, &changed.monsterRng, &changed.neowRng, &changed.potionRng,
            &changed.relicRng, &changed.shuffleRng, &changed.treasureRng}) {
        stream->seed0 ^= 12345;
        stream->seed1 ^= 67890;
        stream->counter += 17;
    }
    std::reverse(changed.monsterList.begin() + changed.monsterListOffset, changed.monsterList.end());
    std::reverse(changed.eliteMonsterList.begin() + changed.eliteMonsterListOffset,
                 changed.eliteMonsterList.end());
    return changed;
}
}

int main() {
    using namespace sts;
    using namespace one_combat;
    try {
        // One fixed initialized fixture; no run traversal or combat search.
        GameContext base(CharacterClass::IRONCLAD, 0x5a17u, 0);
        PathHistory path;
        resetNativeOocPublicScorerCalls();
        const auto &idx = richIdxMap();
        base.screenState = ScreenState::REWARDS;
        base.info.rewardsContainer.clear();
        CardReward reward;
        reward.push_back(Card(CardId::STRIKE_RED));
        reward.push_back(Card(CardId::DEFEND_RED));
        base.info.rewardsContainer.addCardReward(reward);
        base.monsterListOffset = 1;
        base.eliteMonsterListOffset = 1;
        auto changed = changedHidden(base);
        // Guarantee distinct hidden first encounters for the sentinel model;
        // the values remain valid members of the act's weak encounter pool.
        base.monsterList[base.monsterListOffset] = MonsterEncounterPool::weakEnemies[0][0];
        changed.monsterList[changed.monsterListOffset] = MonsterEncounterPool::weakEnemies[0][1];
        const auto raw = richFeatureVec(base, path);
        const auto otherRaw = richFeatureVec(changed, path);
        const float split = (raw[idx.at("nextFight0")] + otherRaw[idx.at("nextFight0")]) / 2.0f;
        require(raw[idx.at("nextFight0")] != otherRaw[idx.at("nextFight0")],
                "fixture needs two distinct legal hidden encounters");
        const int strike = idx.at("d" + std::to_string(static_cast<int>(CardId::STRIKE_RED)));
        const auto model = cardModel(idx.at("nextFight0"), split, strike, raw[strike] + .5f);
        setenv("STS_OOC_PUBLIC_FUTURES", "0", 1);
        require(nativeOocValue(base, path, model) == model.predict(raw), "zero changed model prediction");
        const int legacy = nativeFloorCardPick(base, path, model, 0, -.5);
        const int legacyOther = nativeFloorCardPick(changed, path, model, 0, -.5);
        require(legacy != legacyOther, "sentinel must expose the legacy hidden-dependent action");
        require(nativeOocPublicScorerCalls() == 0 && nativeOocPublicFutureCount() == 0,
                "disabled public scorer reported actual use");

        // Unset is the public default: identical to an explicit 8.
        setenv("STS_OOC_PUBLIC_FUTURES", "8", 1);
        const double explicit8 = nativeOocValue(base, path, model);
        const int explicit8Pick = nativeFloorCardPick(base, path, model, 0, -.5);
        unsetenv("STS_OOC_PUBLIC_FUTURES");
        require(nativeOocPublicFutureCount() == 8 && nativeOocValue(base, path, model) == explicit8
                    && nativeFloorCardPick(base, path, model, 0, -.5) == explicit8Pick
                    && nativeFloorCardPick(changed, path, model, 0, -.5) == explicit8Pick,
                "unset is not the public8 default");
        resetNativeOocPublicScorerCalls();
        {
            // OOC MCTS playouts already carry a resampled queue: no mixture.
            NativeOocResampledQueueScope resampled;
            require(nativeOocValue(base, path, model) == model.predict(raw)
                        && nativeOocPublicScorerCalls() == 0,
                    "resampled-queue scope still mixed futures");
        }
        require(nativeOocValue(base, path, model) == explicit8, "mixture not restored after scope");
        resetNativeOocPublicScorerCalls();

        setenv("STS_OOC_PUBLIC_FUTURES", "8", 1);
        const auto snapshot = test::oocStateFingerprint(base);
        const auto changedSnapshot = test::oocStateFingerprint(changed);
        require(nativeFloorCardPick(base, path, model, 0, -.5)
                    == nativeFloorCardPick(changed, path, model, 0, -.5),
                "public card action depends on true hidden suffix/RNG");
        const std::vector<int> targets = {static_cast<int>(CardId::STRIKE_RED),
                                          static_cast<int>(CardId::DEFEND_RED)};
        require(nativeFloorRemovePick(base, path, model, targets)
                    == nativeFloorRemovePick(changed, path, model, targets),
                "public removal action depends on true hidden suffix/RNG");
        require(nativeWinHealGain(base, path, model, 10)
                    == nativeWinHealGain(changed, path, model, 10),
                "public healing marginal depends on hidden suffix/RNG");
        double gain = 0, changedGain = 0;
        require(nativeWinUpgradePick(base, path, model, targets, &gain)
                    == nativeWinUpgradePick(changed, path, model, targets, &changedGain)
                    && gain == changedGain,
                "public upgrade action or marginal depends on hidden suffix/RNG");
        require(snapshot == test::oocStateFingerprint(base)
                    && changedSnapshot == test::oocStateFingerprint(changed),
                "pure public fallback queries mutated state or RNG");
        require(nativeOocPublicScorerCalls() > 0 && nativeOocPublicFutureCount() == 8,
                "enabled public scorer failed to report actual use");

        // A field-sensitive model for each hidden input checks invariance in
        // all three acts, including observed-prefix exclusions.
        for (int act = 1; act <= 3; ++act) {
            auto state = base;
            state.act = act;
            state.monsterList.clear(); state.eliteMonsterList.clear();
            state.monsterListOffset = 0; state.eliteMonsterListOffset = 0;
            state.generateMonsters();
            state.monsterListOffset = act == 1 ? 2 : 1;
            state.eliteMonsterListOffset = 1;
            auto altered = changedHidden(state);
            const auto saved = test::oocStateFingerprint(state);
            const auto alteredSaved = test::oocStateFingerprint(altered);
            for (const char *name : {"nextEliteId", "nextFight0", "nextFight1", "nextFight2"}) {
                CompactTreeNet probe;
                probe.ok = true; probe.logistic = false;
                const auto r = richFeatureVec(state, path);
                probe.nodes = {{idx.at(name), r[idx.at(name)] + .5f, 1, 2},
                               {-1, -1, 0, 0}, {-1, 4, 0, 0}};
                probe.roots = {0, 3};
                const double mean = nativeOocValue(state, path, probe);
                require(mean == nativeOocValue(altered, path, probe),
                        std::string("hidden field not marginalized: ") + name);
                probe.logistic = true;
                const double mixture = nativeOocValue(state, path, probe);
                const double highWeight = (mean + 1.0) / 5.0;
                const double expected = (1.0 - highWeight) / (1.0 + std::exp(1.0))
                                      + highWeight / (1.0 + std::exp(-4.0));
                require(std::abs(mixture - expected) < 1e-14,
                        "logistic model averages margins instead of predictions");
            }
            require(saved == test::oocStateFingerprint(state)
                        && alteredSaved == test::oocStateFingerprint(altered),
                    "value marginalization changed source state/RNG");
            auto exhausted = state;
            exhausted.monsterListOffset = exhausted.monsterList.size();
            exhausted.eliteMonsterListOffset = exhausted.eliteMonsterList.size();
            auto exhaustedAltered = changedHidden(exhausted);
            require(nativeOocValue(exhausted, path, model)
                        == nativeOocValue(exhaustedAltered, path, model),
                    "empty suffix depends on hidden RNG");
            // Shop chooses among one known card and one known relic. Only
            // the returned plan is inspected; no action is executed here.
            state.screenState = ScreenState::SHOP_ROOM; state.gold = 200;
            for (int i = 0; i < 7; ++i) state.info.shop.cardPrice(i) = -1;
            for (int i = 0; i < 3; ++i) {
                state.info.shop.relicPrice(i) = -1;
                state.info.shop.potionPrice(i) = -1;
            }
            state.info.shop.removeCost = 75;
            state.info.shop.cards[0] = Card(CardId::STRIKE_RED);
            state.info.shop.cardPrice(0) = 50;
            state.info.shop.relics[0] = RelicId::ANCHOR;
            state.info.shop.relicPrice(0) = 100;
            altered = changedHidden(state);
            const auto shopSaved = test::oocStateFingerprint(state);
            require(nativeShopPlan(state, path, model) == nativeShopPlan(altered, path, model),
                    "public shop plan depends on true hidden suffix/RNG");
            require(shopSaved == test::oocStateFingerprint(state), "shop scorer mutated source state");
        }
        for (const char *invalid : {"", "-1", "8junk", "1.5", "257"}) {
            setenv("STS_OOC_PUBLIC_FUTURES", invalid, 1);
            bool threw = false;
            try { (void)nativeOocValue(base, path, model); }
            catch (const std::runtime_error &) { threw = true; }
            require(threw, std::string("invalid public-future count accepted: ") + invalid);
        }
        setenv("STS_OOC_PUBLIC_FUTURES", "8", 1);
        // Act 4 encounters are fixed and public: no mixture, plain prediction.
        auto act4 = base;
        act4.act = 4;
        resetNativeOocPublicScorerCalls();
        require(nativeOocValue(act4, path, model) == model.predict(richFeatureVec(act4, path))
                    && nativeOocPublicScorerCalls() == 0,
                "act 4 should be scored without an encounter mixture");
        unsetenv("STS_OOC_PUBLIC_FUTURES");
        std::cout << "PASS public native OOC futures: hidden-sensitive legacy control, "
                     "zero legacy, unset=public8 default, resampled-queue scope, act-4 passthrough, 3-act suffix/RNG invariance, all fallback decisions, "
                     "logistic mixture, source-state preservation, invalid config\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
