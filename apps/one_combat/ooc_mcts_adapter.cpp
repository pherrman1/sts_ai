#include "run_profile.h"
#include "ooc_mcts_adapter.h"
#ifndef STS_LIVE_ADVISOR
#include "screen_leaf_net.h"
#include "screen_leaf_gbm.h"
#include "screen_leaf_s0.h"
#endif
#include "ooc_profile.h"
#include "combat_transition_runtime.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <numeric>
#include <time.h>
#include "../ooc_strategic_tok_net.h"
#include "run_driver.h"
#include "ooc_checkpoint_policy.h"
#include "ooc_native_fallback.h"
#include "ooc_policy.h"
#include "combat/BattleContext.h"
#include "sim/search/NativeSilverBackend.h"
#include "../ooc_test_state.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <nlohmann/json.hpp>

namespace one_combat {
static_assert(!std::is_constructible_v<OocGameContextModel, const GameContext &>,
              "OOC MCTS roots must require explicit PathHistory");
namespace {
std::string liveGraphPath;
std::uint64_t liveGraphDecisionIndex = 1;
std::mutex liveTraceMutex;
GameContext detachedCopy(const GameContext &parent) {
    GameContext child = parent;
    if (parent.map) child.map = std::make_shared<sts::Map>(*parent.map);
    return child;
}
// Re-determinize only a detached hypothetical state. Published offers, the
// current map/boss, selected cards, and observed encounter history stay fixed.
// A fresh seed also covers native per-floor RNG resets and next-act map setup.
void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng) {
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
            &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
            &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
            &gc.shuffleRng, &gc.treasureRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter; // native thresholds depend on past draw counts
    }
    const auto shuffleUnknown = [&](auto &pool) {
        // Canonicalize first so the actual hidden ordering cannot affect samples.
        std::sort(pool.begin(), pool.end());
        std::shuffle(pool.begin(), pool.end(), rng);
    };
    for (auto pool : {&gc.commonRelicPool, &gc.uncommonRelicPool, &gc.rareRelicPool,
                     &gc.shopRelicPool, &gc.bossRelicPool}) shuffleUnknown(*pool);
    shuffleUnknown(gc.colorlessCardPool);
    // Event pools are eligible sets, not queues. Canonical order removes any
    // dependence on an unobserved representation without changing membership.
    std::sort(gc.eventList.begin(), gc.eventList.end());
    std::sort(gc.shrineList.begin(), gc.shrineList.end());
    std::sort(gc.specialOneTimeEventList.begin(), gc.specialOneTimeEventList.end());
    if (gc.act >= 1 && gc.act <= 3) {
        const int count = gc.monsterList.size();
        if (gc.monsterListOffset < 0 || gc.monsterListOffset > count
            || gc.eliteMonsterListOffset < 0 || gc.eliteMonsterListOffset > gc.eliteMonsterList.size())
            throw sts::search::OocSearchUnsupported("invalid_hidden_encounter_history");
        const int weakCount = gc.act == 1 ? 3 : 2;
        gc.monsterList.resize(gc.monsterListOffset);
        for (int i = gc.monsterListOffset; i < count; ++i) {
            const int act = gc.act - 1;
            if (i < weakCount)
                gc.populateMonsterList(sts::MonsterEncounterPool::weakEnemies[act],
                    sts::MonsterEncounterPool::weakWeights[act], sts::MonsterEncounterPool::weakCount[act], 1);
            else if (i == weakCount)
                gc.populateFirstStrongEnemy(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act]);
            else
                gc.populateMonsterList(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act], 1);
        }
        for (int i = gc.eliteMonsterListOffset; i < gc.eliteMonsterList.size(); ++i) {
            sts::MonsterEncounter draw;
            do { draw = sts::MonsterEncounterPool::elites[gc.act-1][gc.monsterRng.random(2)]; }
            while (i > 0 && draw == gc.eliteMonsterList[i-1]);
            gc.eliteMonsterList[i] = draw;
        }
        if (gc.act == 3 && gc.ascension >= 20) {
            const sts::MonsterEncounter bosses[] = {sts::MonsterEncounter::AWAKENED_ONE,
                sts::MonsterEncounter::TIME_EATER, sts::MonsterEncounter::DONU_AND_DECA};
            do { gc.secondBoss = bosses[gc.monsterRng.random(2)]; } while (gc.secondBoss == gc.boss);
        }
    }
    if (gc.screenState == sts::ScreenState::TREASURE_ROOM) {
        // Chest size is visible; contents are not. Keep native gold/tier
        // correlation from the single roll used by setupTreasureRoom().
        const int size = int(gc.info.chestSize);
        if (size < 0 || size >= 3) throw sts::search::OocSearchUnsupported("invalid_hidden_chest");
        const int roll = gc.treasureRng.random(99);
        gc.info.haveGold = roll < sts::chestGoldChances[size];
        const auto chances = sts::chestRelicTierChances[size];
        gc.info.tier = roll < chances[0] ? sts::RelicTier::COMMON
            : roll < chances[0] + chances[1] ? sts::RelicTier::UNCOMMON : sts::RelicTier::RARE;
    }
    if (gc.screenState == sts::ScreenState::EVENT_SCREEN && gc.curEvent == sts::Event::DEAD_ADVENTURER) {
        // The description reveals the encounter, but unsearched rewards remain hidden.
        if (gc.info.phase < 0 || gc.info.phase > int(gc.info.rewards.size()))
            throw sts::search::OocSearchUnsupported("invalid_hidden_event_history");
        auto first = gc.info.rewards.begin() + gc.info.phase;
        std::sort(first, gc.info.rewards.end());
        std::shuffle(first, gc.info.rewards.end(), rng);
    }
}

// Search-equivalence of two sampled successors of one chance node (#384).
// Omits exactly what sampleNoncombatFuture re-draws before every later
// transition and leaf continuation: the run seed, every RNG stream (a counter
// only positions a re-seeded stream), pool order, unseen monster/elite queue
// entries, the A20 second Act-3 boss, hidden chest gold/tier and unsearched
// Dead Adventurer reward order. Everything copied forward is kept, including
// hidden room/potion/rarity counters. Separate parts let a diagnostic
// attribute a split to one component.
enum OutcomePart { HIDDEN, SCREEN, PLAYER, DECK, RELICS, POTIONS, MAP, PATH, OUTCOME_PARTS };
std::array<std::string, OUTCOME_PARTS> outcomeEquivalenceParts(const GameContext &g, const PathHistory &path) {
    std::array<std::string, OUTCOME_PARTS> parts;
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.monsterChance, g.shopChance, g.treasureChance, g.potionChance, g.cardRarityFactor);
        const auto members = [&](auto pool) { std::sort(pool.begin(), pool.end()); w.sequence(pool); };
        members(g.eventList); members(g.shrineList); members(g.specialOneTimeEventList);
        members(g.commonRelicPool); members(g.uncommonRelicPool); members(g.rareRelicPool);
        members(g.shopRelicPool); members(g.bossRelicPool); members(g.colorlessCardPool);
        const auto seen = [&](const auto &list, int offset) {
            const int n = std::clamp<int>(offset, 0, list.size());
            w.value(offset);
            for (int i = 0; i < n; ++i) w.value(list[i]);
        };
        seen(g.monsterList, g.monsterListOffset);
        seen(g.eliteMonsterList, g.eliteMonsterListOffset);
        if (!(g.act == 3 && g.ascension >= 20)) w.value(g.secondBoss);
        parts[HIDDEN] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        auto info = g.info;
        if (g.screenState == sts::ScreenState::TREASURE_ROOM) {
            info.haveGold = false;
            info.tier = sts::RelicTier::COMMON;
        }
        if (g.screenState == sts::ScreenState::EVENT_SCREEN && g.curEvent == sts::Event::DEAD_ADVENTURER
                && info.phase >= 0 && info.phase <= int(info.rewards.size()))
            std::sort(info.rewards.begin() + info.phase, info.rewards.end());
        w.values(g.outcome, g.screenState, info, g.lastRoom, g.curEvent, g.curRoom, g.boss,
                 static_cast<bool>(g.regainControlAction), g.restRoomResolved);
        parts[SCREEN] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.noteForYourselfCard, g.skipBattles, g.act, g.ascension, g.floorNum, g.cc,
                 g.curHp, g.maxHp, g.gold, g.wingBootsCharges, g.shopRemoveCount, g.speedrunPace,
                 g.curMapNodeX, g.curMapNodeY, g.blueKey, g.greenKey, g.redKey, g.keysEnabled,
                 g.smokeBombUsed);
        parts[PLAYER] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(g.deck.cards);
        w.sequence(g.deck.bottleIdxs);
        parts[DECK] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(g.relics.relics);
        parts[RELICS] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.potionCount, g.potionCapacity);
        w.sequence(g.potions);
        parts[POTIONS] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.value(static_cast<bool>(g.map));
        if (g.map) {
            w.values(g.map->burningEliteX, g.map->burningEliteY, g.map->burningEliteBuff);
            for (const auto &row : g.map->nodes) w.sequence(row);
        }
        parts[MAP] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(path.roomVisits);
        w.value(path.lastNodeKey);
        parts[PATH] = w.finish();
    }
    return parts;
}
std::uint64_t outcomeEquivalenceKeyOf(const GameContext &g, const PathHistory &path) {
    std::string joined;
    for (const auto &part : outcomeEquivalenceParts(g, path)) { joined += part; joined += '|'; }
    return std::hash<std::string>{}(joined);
}

void sampleLiveOocHiddenCountersImpl(GameContext &gc, std::mt19937_64 &rng,
                                     int priorEventRooms, bool questionHistoryComplete) {
    // Only '?' room transitions change these room chances. Bound increments
    // by the number of rooms already visited in this act, and reproduce the
    // native float-addition lattice (including Juzu's >1 monster chance).
    if (!questionHistoryComplete) {
        const int actStart = gc.act <= 1 ? 0 : gc.act == 2 ? 17 : gc.act == 3 ? 34 : 51;
        const int priorRooms = std::clamp(std::min(gc.floorNum - actStart, priorEventRooms), 0, 16);
        gc.monsterChance = 0.1f;
        gc.shopChance = 0.03f;
        gc.treasureChance = 0.02f;
        // Draw one latent outcome per observed '?' room, then update all three
        // counters together by the native room-outcome rule. Independent lattice
        // draws create counter triples that no room history could have produced.
        for (int i = 0; i < priorRooms; ++i) {
            const int outcome = std::uniform_int_distribution<int>(0, 3)(rng);
            gc.monsterChance = outcome == 0 ? 0.1f : gc.monsterChance + 0.1f;
            gc.shopChance = outcome == 1 ? 0.03f : gc.shopChance + 0.03f;
            gc.treasureChance = outcome == 2 ? 0.02f : gc.treasureChance + 0.02f;
        }
    }
    gc.potionChance = 10 * std::uniform_int_distribution<int>(-4, 6)(rng);
    gc.cardRarityFactor = std::uniform_int_distribution<int>(-40, 5)(rng);
}

void require(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
double bossLeafUtility(const CombatTransitionExpectation &estimate) {
    const double survival = 1.0 - estimate.death;
    return 0.75 * survival + 0.25 * survival * estimate.winningHpFraction;
}
// Phase-0 Smoke Bomb approximation (#370). The qualified CTM excludes combats
// that start with a Smoke Bomb. Rather than abort the whole search, value such
// a combat as if the Smoke Bomb slot were empty (no escape) and return the
// Smoke Bomb unused afterwards; a potion the CTM generated into that slot is
// dropped, since the occupied slot could not have held it. Against bosses the
// Smoke Bomb cannot be used, so only slot occupancy differs there.
class InitialSmokeBombMaskingSampler final : public CombatTransitionSampler {
    std::shared_ptr<const CombatTransitionSampler> inner_;
    static constexpr int kEmpty = static_cast<int>(sts::Potion::EMPTY_POTION_SLOT);
    static constexpr int kSmoke = static_cast<int>(sts::Potion::SMOKE_BOMB);
public:
    struct Masked {
        GameContext gc;
        CombatPredictorInputV1 input;
        std::vector<int> slots;
    };
    explicit InitialSmokeBombMaskingSampler(std::shared_ptr<const CombatTransitionSampler> inner)
        : inner_(std::move(inner)) {}
    static std::optional<Masked> mask(const GameContext &gc, const CombatPredictorInputV1 &input) {
        if (gc.smokeBombUsed) return std::nullopt;
        std::vector<int> slots;
        for (int i = 0; i < static_cast<int>(gc.potions.size()); ++i)
            if (gc.potions[i] == sts::Potion::SMOKE_BOMB) slots.push_back(i);
        if (slots.empty()) return std::nullopt;
        Masked masked{gc, input, slots};
        for (int slot : slots) {
            masked.gc.potions[slot] = sts::Potion::EMPTY_POTION_SLOT;
            --masked.gc.potionCount;
            for (auto &token : masked.input.potions)
                if (token.slot == slot && token.potionId == kSmoke) token.potionId = kEmpty;
            --masked.input.globals.potionCount;
        }
        return masked;
    }
    static CombatRuntimeSample restore(CombatRuntimeSample sample, const std::vector<int> &slots) {
        if (sample.outcome != CombatRuntimeSample::Outcome::VICTORY
                && sample.outcome != CombatRuntimeSample::Outcome::ESCAPE) return sample;
        auto &post = sample.rawPost;
        for (int slot : slots) post.potions.at(slot) = kSmoke;
        post.potionCount = static_cast<int>(std::count_if(post.potions.begin(), post.potions.end(),
            [](int p) { return p > kEmpty; }));
        return sample;
    }
    std::unique_ptr<PreparedCombatTransition> prepare(const GameContext &gc,
            const CombatPredictorInputV1 &input) const override {
        auto masked = mask(gc, input);
        if (!masked) return inner_->prepare(gc, input);
        class Restoring final : public PreparedCombatTransition {
            std::unique_ptr<PreparedCombatTransition> inner_;
            std::vector<int> slots_;
        public:
            Restoring(std::unique_ptr<PreparedCombatTransition> inner, std::vector<int> slots)
                : inner_(std::move(inner)), slots_(std::move(slots)) {}
            const CombatRuntimeSupport &support() const override { return inner_->support(); }
            CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
                return restore(inner_->sample(rng), slots_);
            }
        };
        return std::make_unique<Restoring>(inner_->prepare(masked->gc, masked->input), masked->slots);
    }
    CombatRuntimeSupport support(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        const auto masked = mask(gc, input);
        return masked ? inner_->support(masked->gc, masked->input) : inner_->support(gc, input);
    }
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastSupport(input);
    }
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastExpectation(input);
    }
    CombatTransitionExpectation expectation(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        const auto masked = mask(gc, input);
        return masked ? inner_->expectation(masked->gc, masked->input) : inner_->expectation(gc, input);
    }
    CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &input,
            std::mt19937_64 &rng) const override {
        const auto masked = mask(gc, input);
        if (!masked) return inner_->sample(gc, input, rng);
        return restore(inner_->sample(masked->gc, masked->input, rng), masked->slots);
    }
};
std::shared_ptr<const CombatTransitionSampler> maskInitialSmokeBomb(
        std::shared_ptr<const CombatTransitionSampler> sampler) {
    if (!sampler) return sampler;
    return std::make_shared<InitialSmokeBombMaskingSampler>(std::move(sampler));
}
void applySampledCombatExit(GameContext &gc, const CombatRuntimeSample &sample) {
    const bool escape = sample.outcome == CombatRuntimeSample::Outcome::ESCAPE;
    if ((sample.outcome != CombatRuntimeSample::Outcome::VICTORY && !escape)
        || sample.rawPost.smokeBombUsed != escape
        || (escape && sts::isBossEncounter(gc.info.encounter)))
        throw std::runtime_error("combat outcome disagrees with RAW smokeBombUsed");
    applyCombatTransitionState(gc, sample.rawPost);
    gc.regainControl();
}
}
void sampleLiveOocHiddenCounters(GameContext &gc, std::mt19937_64 &rng,
                                 int priorEventRooms, bool questionHistoryComplete) {
    sampleLiveOocHiddenCountersImpl(gc, rng, priorEventRooms, questionHistoryComplete);
}
#ifndef STS_LIVE_ADVISOR
OocMctsDependencies defaultOocMctsDependencies() {
    OocMctsDependencies dependencies;
    dependencies.policyAvailable = [] { return g_oocStrategicTokNet.ok; };
    dependencies.policyLogits = [](const GameContext &gc, const PathHistory &path,
                                   const std::vector<GameAction> &actions) {
        if (!g_oocStrategicTokNet.ok) throw std::runtime_error("OOC MCTS V4 unavailable");
        const TokState ts = buildTokState(gc, path);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        const auto policyPrefix = g_oocStrategicTokNet.preparePolicyPrefix(prepared);
        std::vector<double> result;
        result.reserve(actions.size());
        for (const auto action : actions) {
            int type, c1, c2, c3, d1, d2, d3, entityType, entityId;
            float price;
            strategicCands(gc, action, type, c1, c2, c3, d1, d2, d3);
            tokEntity(gc, action, entityType, entityId, price);
            const int cats[6] = {c1, c2, c3, d1, d2, d3};
            const float entity[4] = {float(entityType == 0), float(entityType == 1),
                                     float(entityType == 2), float(entityType == 3)};
            const double logit = g_oocStrategicTokNet.predictPolicyLogit(prepared, policyPrefix, action.bits,
                cats, type, int(gc.screenState), entity, entityId, price);
            if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
            result.push_back(logit);
        }
        return result;
    };
    if (winNetOk()) {
        // Features only read the state, so no detached copy or t_curPath swap.
        dependencies.leafValue = [](const GameContext &source, const PathHistory &path) {
            std::vector<float> raw;
            {
                OocProfileScope features(OocProfileBucket::LeafFeatures);
                raw = richFeatureVec(source, path);
            }
            OocProfileScope predict(OocProfileBucket::LeafPredict);
            return vStateWinNativeFeatures(raw);
        };
    }
    dependencies.continuationStep = [](GameContext &gc, PathHistory &, std::mt19937_64 &) {
        ScumSearchAgent2 agent;
        agent.simulationCountBase = 10000;
        runFullRunOocPolicyStep(gc, agent, false, true);
    };
    dependencies.potionKeepValue = [](const GameContext &gc) { return ::potionKeepValue(gc); };
    dependencies.stopAfterAct = [] { return g_stopAfterAct; };
    return dependencies;
}
#endif
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature) {
    if (!std::isfinite(temperature) || temperature <= 0)
        throw std::invalid_argument("OOC MCTS invalid policy temperature");
    for (double l : logits) if (!std::isfinite(l)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    if (logits.empty()) return {};
    double largest = *std::max_element(logits.begin(), logits.end());
    std::vector<double> weights;
    for (double l : logits) {
        double w = std::exp((l - largest) / temperature);
        if (!std::isfinite(w) || w < 0) throw std::runtime_error("OOC MCTS invalid policy weight");
        weights.push_back(w);
    }
    return weights;
}
#ifndef STS_LIVE_ADVISOR
OocGameContextModel::OocGameContextModel(const GameContext &gc, const PathHistory &path,
    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts)
    : OocGameContextModel(gc, path, std::move(sampler), std::move(opts),
                          defaultOocMctsDependencies()) {}
#endif

OocGameContextModel::OocGameContextModel(const GameContext &gc, const PathHistory &path,
    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts,
    OocMctsDependencies deps)
    : combatSampler(maskInitialSmokeBomb(std::move(sampler))), options(std::move(opts)),
      dependencies(std::move(deps)) {
    if (!std::isfinite(options.priorTemperature) || options.priorTemperature <= 0 || (options.leafCombats != 0 && options.leafCombats != 1 && options.leafCombats != 3))
        throw std::invalid_argument("OOC MCTS invalid adapter options");
    if (!options.bossLeaf && !dependencies.leafValue)
        throw std::runtime_error("OOC MCTS requires a leaf-value dependency");
    if (!dependencies.policyAvailable || !dependencies.policyLogits
            || !dependencies.policyAvailable())
        throw std::runtime_error("OOC MCTS requires native V4 policy dependencies");
    if (!dependencies.potionKeepValue) dependencies.potionKeepValue = [](const GameContext &) { return 4.0; };
    if (!dependencies.stopAfterAct) dependencies.stopAfterAct = [] { return 0; };
    auto root = detachedCopy(gc);
    collectForcedRewardGold(root);
    auto history = path;
    history.update(root);
    states.push_back({std::move(root), history, {}});
}
const GameContext &OocGameContextModel::state(sts::search::OocStateId id) const { return states.at(id).gc; }
const PathHistory &OocGameContextModel::pathHistory(sts::search::OocStateId id) const { return states.at(id).path; }
const OocGameContextModel::CombatPrediction &OocGameContextModel::prediction(sts::search::OocStateId id) const {
    return states.at(id).combatPrediction;
}
namespace {
std::string graphRoomName(sts::Room room) {
    switch (room) {
        case sts::Room::MONSTER: return "Monster";
        case sts::Room::ELITE: return "Elite";
        case sts::Room::EVENT: return "Event";
        case sts::Room::SHOP: return "Shop";
        case sts::Room::REST: return "Rest";
        case sts::Room::TREASURE: return "Treasure";
        case sts::Room::BOSS: return "Boss";
        case sts::Room::BOSS_TREASURE: return "Boss treasure";
        default: return "Unknown";
    }
}
std::string graphEntityName(const sts::search::OocEntity &entity) {
    if (const auto *card = std::get_if<sts::Card>(&entity)) return card->getName();
    if (const auto *relic = std::get_if<sts::RelicId>(&entity)) return sts::getRelicName(*relic);
    if (const auto *potion = std::get_if<sts::Potion>(&entity)) return sts::getPotionName(*potion);
    if (const auto *gold = std::get_if<int>(&entity)) return std::to_string(*gold) + " gold";
    if (std::get_if<sts::Key>(&entity)) return "key";
    return "";
}
std::string graphActionLabel(const OocGameContextModel &model, const sts::search::OocTreeNode &node) {
    const auto &source = model.state(node.state);
    const auto &action = model.candidate(node.state, node.action);
    if (!action.semantic) {
        if (source.screenState == sts::ScreenState::MAP_SCREEN) {
            const int x = action.primitive.getIdx1(), y = source.curMapNodeY + 1;
            const bool hasRoom = source.map && y >= 0 && y < 15 && x >= 0 && x < 7;
            const std::string room = hasRoom ? graphRoomName(source.map->nodes[y][x].room) : "Unknown";
            return "Travel to " + room + " room at (" + std::to_string(x) + "," + std::to_string(y) + ")";
        }
        return "Choose game action " + std::to_string(action.primitive.bits);
    }
    static constexpr const char *effects[] = {
        "Upgrade card", "Remove card", "Transform card", "Transform and upgrade card",
        "Duplicate card", "Take card", "Bottle card", "Sacrifice card", "Take relic",
        "Collect gold", "Take potion", "Take key", "Skip card reward", "Use Singing Bowl",
        "Leave rewards", "Open chest", "Leave treasure", "Rest", "Take Ruby Key",
        "Lift", "Dig", "Leave campfire", "Buy card", "Buy relic", "Buy potion",
        "Leave shop", "Choose event option", "Take boss relic", "Skip boss relic", "Discard potion"
    };
    const auto effect = static_cast<unsigned>(action.semantic->effect);
    std::string label = effect < std::size(effects) ? effects[effect] : "OOC action";
    std::string target;
    const auto &payload = action.semantic->target;
    if (const auto *card = std::get_if<sts::search::OocCardTarget>(&payload))
        target = sts::getCardName(card->id);
    else if (const auto *selection = std::get_if<sts::search::OocSelectorTarget>(&payload)) {
        if (const auto *card = std::get_if<sts::search::OocCardTarget>(&selection->card))
            target = sts::getCardName(card->id);
        else if (const auto *candidate = std::get_if<sts::search::OocCandidateTarget>(&selection->card))
            target = candidate->card.getName();
    } else if (const auto *reward = std::get_if<sts::search::OocRewardTarget>(&payload))
        target = graphEntityName(reward->entity);
    else if (const auto *shop = std::get_if<sts::search::OocShopTarget>(&payload))
        target = graphEntityName(shop->entity);
    else if (const auto *relic = std::get_if<sts::search::OocRelicTarget>(&payload))
        target = sts::getRelicName(relic->relic);
    else if (const auto *event = std::get_if<sts::search::OocEventTarget>(&payload))
        target = std::to_string(event->option);
    else if (const auto *transaction = std::get_if<sts::search::OocTransactionTarget>(&payload))
        target = sts::getCardName(transaction->card.id);
    if (!target.empty()) label = action.semantic->effect == sts::search::OocSemanticEffect::TAKE_GOLD
        ? "Collect " + target : label + ": " + target;
    return label;
}
}
void annotateOocTree(const OocGameContextModel &model, sts::search::OocTreeSnapshot &tree) {
    static const char *screens[] = {"invalid", "event", "rewards", "boss relic",
        "card select", "map", "treasure", "rest", "shop", "battle"};
    for (auto &node : tree.nodes) {
        const auto &state = model.state(node.state);
        node.floor = state.floorNum;
        node.mapX = state.curMapNodeX;
        node.mapY = state.curMapNodeY;
        node.hp = state.curHp;
        node.maxHp = state.maxHp;
        node.gold = state.gold;
        const auto screen = static_cast<unsigned>(state.screenState);
        node.screen = screen < std::size(screens) ? screens[screen] : "unknown";
        const auto room = static_cast<unsigned>(state.curRoom);
        node.room = room < std::size(sts::roomStrings) ? sts::roomStrings[room] : "unknown";
        if (node.chance) {
            node.key = model.candidate(node.state, node.action).key;
            node.label = graphActionLabel(model, node);
        } else {
            node.outcome = state.outcome == sts::GameOutcome::PLAYER_LOSS ? "loss"
                : state.outcome == sts::GameOutcome::PLAYER_VICTORY ? "victory" : "undecided";
            std::string place = node.screen == "map" ? "Map choice"
                : graphRoomName(state.curRoom) + " room · " + node.screen;
            if (node.mapY >= 0) place += " (" + std::to_string(node.mapX) + "," + std::to_string(node.mapY) + ")";
            node.label = "Floor " + std::to_string(node.floor) + " · " + place
                + " · HP " + std::to_string(node.hp) + "/" + std::to_string(node.maxHp)
                + " · " + std::to_string(node.gold) + " gold";
            if (node.outcome == "loss") node.label = "CTM sampled loss · entered combat at HP "
                + std::to_string(node.hp) + "/" + std::to_string(node.maxHp)
                + " · final HP unavailable · Floor " + std::to_string(node.floor);
            if (node.outcome == "victory") node.label = "Victory · " + node.label;
        }
    }
    for (auto &edge : tree.edges) {
        if (!edge.particle || !edge.childId) continue;
        const auto &node = tree.nodes.at(*edge.childId);
        const auto &prediction = model.prediction(node.state);
        if (!prediction.used) continue;
        edge.combatModelUsed = true;
        const auto encounter = static_cast<unsigned>(prediction.encounter);
        edge.combatEncounter = encounter < std::size(sts::monsterEncounterEnumNames)
            ? sts::monsterEncounterEnumNames[encounter] : "unknown encounter";
        edge.combatOutcome = prediction.outcome;
    }
}
std::optional<double> OocGameContextModel::terminalValue(sts::search::OocStateId id) const {
    switch (state(id).outcome) {
        case sts::GameOutcome::PLAYER_LOSS: return 0;
        case sts::GameOutcome::PLAYER_VICTORY: return 1;
        case sts::GameOutcome::UNDECIDED: return std::nullopt;
    }
    throw std::runtime_error("OOC MCTS invalid outcome");
}
OocGameContextModel::Metadata &OocGameContextModel::mutableMetadata(sts::search::OocStateId id) const {
    const auto &snapshot = states.at(id);
    if (!snapshot.metadata) {
        OocProfileScope profile(OocProfileBucket::Metadata);
        Metadata value;
        const auto &gc = snapshot.gc;
        if (gc.outcome == sts::GameOutcome::UNDECIDED && gc.screenState == sts::ScreenState::MAP_SCREEN
            && v4DecisionSupported(gc)) {
            std::set<std::uint32_t> ids;
            for (auto action : v4CandidateActions(gc)) {
                if (!ids.insert(action.bits).second) { value.candidates.clear(); break; }
                value.candidates.push_back({action.bits, "map:" + std::to_string(action.bits), {}, action});
            }
            value.sourcePriorCovered = true;
        } else if (gc.outcome == sts::GameOutcome::UNDECIDED && gc.screenState != sts::ScreenState::BATTLE
                   && gc.screenState != sts::ScreenState::MAP_SCREEN) {
            const auto enumeration = sts::search::enumerateOocSemanticPrimitiveBindings(gc);
            if (enumeration.supported && enumeration.complete) {
                std::set<std::string> keys;
                std::set<std::string> cardChoices;
                std::set<std::uint32_t> sources;
                std::map<std::string, std::vector<GameAction>> groups;
                std::set<std::uint32_t> droppedKeys;
                for (const auto &binding : enumeration.bindings) {
                    if (!GameAction(binding.primitiveBits).isValidAction(gc)) continue;
                    if (!options.collectKeys && (binding.semantic.effect == sts::search::OocSemanticEffect::TAKE_KEY
                            || binding.semantic.effect == sts::search::OocSemanticEffect::TAKE_RUBY_KEY)) {
                        droppedKeys.insert(binding.primitiveBits);
                        continue;
                    }
                    if (id == 0 && options.rootPrimitiveBits
                            && !options.rootPrimitiveBits->count(binding.primitiveBits)) continue;
                    const auto key = sts::search::canonicalOocSemanticActionKey(binding.semantic);
                    if (!keys.insert(key).second) { value.candidates.clear(); break; }
                    const auto choiceKey = sts::search::canonicalOocMctsChoiceKey(binding.semantic, &gc);
                    groups[choiceKey].push_back(GameAction(binding.primitiveBits));
                    sources.insert(binding.primitiveBits);
                    if (!cardChoices.insert(choiceKey).second) continue;
                    value.candidates.push_back({static_cast<sts::search::OocActionId>(value.candidates.size()),
                        key, binding.semantic, GameAction(binding.primitiveBits), binding.compoundSelector});
                }
                if (!value.candidates.empty())
                    for (const auto &candidate : value.candidates)
                        value.priorSourceGroups.push_back(groups.at(
                            sts::search::canonicalOocMctsChoiceKey(*candidate.semantic, &gc)));
                if (v4DecisionSupported(gc)) {
                    std::set<std::uint32_t> qualified;
                    auto primitives = v4CandidateActions(gc);
                    primitives.erase(std::remove_if(primitives.begin(), primitives.end(),
                        [&](auto action) { return droppedKeys.count(action.bits) != 0; }), primitives.end());
                    for (auto action : primitives)
                        if (id != 0 || !options.rootPrimitiveBits || options.rootPrimitiveBits->count(action.bits))
                            qualified.insert(action.bits);
                    const std::size_t qualifiedCount = std::count_if(primitives.begin(), primitives.end(),
                        [&](auto action) { return id != 0 || !options.rootPrimitiveBits
                            || options.rootPrimitiveBits->count(action.bits); });
                    value.sourcePriorCovered = qualified.size() == qualifiedCount && qualified == sources;
                }
            }
        }
        if (id == 0 && options.rootPrimitiveBits && gc.screenState == sts::ScreenState::MAP_SCREEN) {
            const auto &allowed = *options.rootPrimitiveBits;
            value.candidates.erase(std::remove_if(value.candidates.begin(), value.candidates.end(),
                [&](const auto &candidate) { return !allowed.count(candidate.primitive.bits); }),
                value.candidates.end());
            if (v4DecisionSupported(gc)) {
                std::set<std::uint32_t> qualified;
                for (const auto &action : v4CandidateActions(gc))
                    if (allowed.count(action.bits)) qualified.insert(action.bits);
                std::set<std::uint32_t> sources;
                for (const auto &candidate : value.candidates) sources.insert(candidate.primitive.bits);
                value.sourcePriorCovered = qualified == sources;
            }
        }
        value.boundary = value.candidates.empty();
        value.edges.resize(value.candidates.size());
        snapshot.metadata = std::move(value);
        ++continuation_.metadataBuilds;
    }
    return *snapshot.metadata;
}
const OocGameContextModel::Metadata &OocGameContextModel::metadata(sts::search::OocStateId id) const {
    return mutableMetadata(id);
}
bool OocGameContextModel::isLeafBoundary(sts::search::OocStateId id) const {
    if (id != 0 && state(id).screenState == sts::ScreenState::MAP_SCREEN
            && options.stopAtMapCheckpoint)
        return true;
    return metadata(id).boundary;
}
std::optional<sts::search::OocActionId> OocGameContextModel::soleLegalAction(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) return std::nullopt;
    const auto &actions = metadata(id).candidates;
    if (actions.size()==1 && actions.front().primitive.isValidAction(state(id))) {
        if (options.priorTracePath.empty()) return actions.front().id;
        auto &cached = mutableMetadata(id);
        if (!cached.priors)
            cached.priors = std::vector<sts::search::OocPlannerAction>{{actions.front().id, 1.0}};
        tracePrior(id, cached, *cached.priors);
        return actions.front().id;
    }
    return std::nullopt;
}
const OocGameContextModel::Candidate &OocGameContextModel::candidate(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    const auto &candidates = metadata(id).candidates;
    const auto it = std::find_if(candidates.begin(), candidates.end(),
        [&](const auto &c) { return c.id == action; });
    if (it == candidates.end()) throw std::runtime_error("OOC MCTS illegal action ID");
    return *it;
}
std::vector<double> OocGameContextModel::policyLogits(sts::search::OocStateId id) const {
    OocProfileScope profile(OocProfileBucket::PolicyLogits);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    if (!dependencies.policyAvailable()) throw std::runtime_error("OOC MCTS V4 unavailable");
    const auto &snapshot = states.at(id);
    const auto &gc = snapshot.gc;
    auto &cached = mutableMetadata(id);
    if (cached.candidates.size() == 1) ++continuation_.singletonPolicyLogitCalls;
    if (cached.logits) return *cached.logits;
    const auto &actions = cached.candidates;
    if (!cached.sourcePriorCovered) return std::vector<double>(actions.size(), 0.0);
    if (actions.size() == 1) ++continuation_.singletonPolicyInferenceCalls;
    ++continuation_.priorBuilds;
    std::vector<GameAction> sources;
    std::map<std::uint32_t, std::size_t> sourceIndexes;
    const auto addSource = [&](GameAction a) {
        if (!sourceIndexes.count(a.bits)) {
            sourceIndexes.emplace(a.bits, sources.size());
            sources.push_back(a);
        }
    };
    for (std::size_t i = 0; i < actions.size(); ++i) {
        if (cached.priorSourceGroups.empty()) addSource(actions[i].primitive);
        else for (const auto a : cached.priorSourceGroups.at(i)) addSource(a);
    }
    OocProfileScope prediction(OocProfileBucket::PolicyPredict);
    const auto sourceLogits = dependencies.policyLogits(gc, snapshot.path, sources);
    if (sourceLogits.size() != sources.size())
        throw std::runtime_error("OOC MCTS policy-logit count mismatch");
    for (double logit : sourceLogits)
        if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    if (!options.priorTracePath.empty())
        cached.priorTraceSources = Metadata::PriorTraceSources{sources, sourceLogits};
    std::vector<double> logits;
    logits.reserve(actions.size());
    for (std::size_t i = 0; i < actions.size(); ++i) {
        if (cached.priorSourceGroups.empty()) {
            logits.push_back(sourceLogits.at(sourceIndexes.at(actions[i].primitive.bits)));
        } else {
            const auto &group = cached.priorSourceGroups.at(i);
            double sum = 0;
            for (const auto action : group) sum += sourceLogits.at(sourceIndexes.at(action.bits));
            logits.push_back(sum / group.size()); // mean logit: no physical-copy multiplicity bonus
        }
    }
    cached.logits = logits;
    return logits;
}
void OocGameContextModel::tracePrior(sts::search::OocStateId id, Metadata &cached,
    const std::vector<sts::search::OocPlannerAction> &actions) const {
    if (options.priorTracePath.empty() || cached.priorTraceWritten) return;
    const auto &gc = state(id);
    const auto &candidates = cached.candidates;
    if (actions.size() != candidates.size())
        throw std::runtime_error("OOC MCTS prior trace candidate count mismatch");

    const bool singleton = candidates.size() == 1;
    const bool uniform = options.uniformPrior || !cached.sourcePriorCovered;
    const bool modelPrior = cached.sourcePriorCovered && !uniform && !singleton;
    static constexpr std::array<const char *, 10> screenNames = {"invalid", "event", "card reward",
        "boss relic", "card select", "map", "treasure", "rest", "shop", "battle"};
    const int screenId = int(gc.screenState);
    const std::string screenName = screenId >= 0 && screenId < int(screenNames.size())
        ? screenNames[screenId] : "unknown";
    const int roomId = int(gc.curRoom);
    const std::string roomName = roomId >= 0 && roomId < int(std::size(sts::roomStrings))
        ? sts::roomStrings[roomId] : "unknown";
    nlohmann::json row = {
        {"schemaVersion", 1},
        {"runSeed", options.priorTraceRunSeed},
        {"decisionIndex", options.priorTraceDecisionIndex},
        {"searchSeed", options.priorTraceSearchSeed},
        {"modelStateId", id},
        {"stateRole", id == 0 ? "root" : "hypothetical"},
        {"floor", gc.floorNum},
        {"screenId", screenId}, {"screen", screenName},
        {"roomId", roomId}, {"room", roomName},
        {"priorTemperature", options.priorTemperature},
        {"candidateCount", candidates.size()},
        {"sourcePriorCovered", cached.sourcePriorCovered},
        {"singleton", singleton},
        {"uniformPrior", uniform},
        {"candidates", nlohmann::json::array()}
    };

    std::vector<double> normalizedWeights;
    if (modelPrior) {
        if (!cached.logits || cached.logits->size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace missing production candidate logits");
        if (!cached.priorTraceSources)
            throw std::runtime_error("OOC MCTS prior trace missing native source logits");
        const auto &sources = cached.priorTraceSources->actions;
        const auto &sourceLogits = cached.priorTraceSources->logits;
        if (sources.size() != sourceLogits.size())
            throw std::runtime_error("OOC MCTS prior trace source-logit count mismatch");
        std::map<std::uint32_t, std::size_t> sourceIndexes;
        for (std::size_t i = 0; i < sources.size(); ++i) {
            if (!sourceIndexes.emplace(sources[i].bits, i).second)
                throw std::runtime_error("OOC MCTS prior trace duplicate source primitive");
            if (!std::isfinite(sourceLogits[i]))
                throw std::runtime_error("OOC MCTS prior trace nonfinite source logit");
        }
        if (cached.priorSourceGroups.empty() && sources.size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace direct-source count mismatch");
        if (!cached.priorSourceGroups.empty() && cached.priorSourceGroups.size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace source-group count mismatch");

        const auto tokenState = buildTokStatePure(gc, states.at(id).path);
        if (tokenState.nDk < 0 || tokenState.nDk > 96
                || tokenState.nRl < 0 || tokenState.nRl > 64
                || tokenState.nPt < 0 || tokenState.nPt > 8)
            throw std::runtime_error("OOC MCTS prior trace invalid token-state length");
        nlohmann::json tokens = {{"glob", nlohmann::json::array()},
            {"deck", {{"nDk", tokenState.nDk}, {"tokens", nlohmann::json::array()}}},
            {"relic", {{"nRl", tokenState.nRl}, {"tokens", nlohmann::json::array()}}},
            {"potion", {{"nPt", tokenState.nPt}, {"tokens", nlohmann::json::array()}}}};
        for (const float value : tokenState.glob) {
            if (!std::isfinite(value)) throw std::runtime_error("OOC MCTS prior trace nonfinite global input");
            tokens["glob"].push_back(value);
        }
        for (int i = 0; i < tokenState.nDk; ++i)
            tokens["deck"]["tokens"].push_back({tokenState.dk[i][0], tokenState.dk[i][1], tokenState.dk[i][2]});
        for (int i = 0; i < tokenState.nRl; ++i)
            tokens["relic"]["tokens"].push_back({tokenState.rl[i][0], tokenState.rl[i][1]});
        for (int i = 0; i < tokenState.nPt; ++i)
            tokens["potion"]["tokens"].push_back({tokenState.pt[i][0], tokenState.pt[i][1]});
        row["tokenState"] = std::move(tokens);

        row["sourcePrimitives"] = nlohmann::json::array();
        for (std::size_t i = 0; i < sources.size(); ++i) {
            int type, c1, c2, c3, d1, d2, d3, entityType, entityId;
            float price;
            strategicCands(gc, sources[i], type, c1, c2, c3, d1, d2, d3);
            tokEntity(gc, sources[i], entityType, entityId, price);
            if (!std::isfinite(price))
                throw std::runtime_error("OOC MCTS prior trace nonfinite source-action feature");
            row["sourcePrimitives"].push_back({
                {"primitiveBits", sources[i].bits}, {"actionType", type},
                {"cats", {c1, c2, c3, d1, d2, d3}}, {"screen", int(gc.screenState)},
                {"entityType", entityType}, {"entityId", entityId},
                {"goldGePrice", price}, {"teacherSourceLogit", sourceLogits[i]}});
        }

        std::vector<double> reproducedCandidateLogits;
        reproducedCandidateLogits.reserve(candidates.size());
        for (std::size_t i = 0; i < candidates.size(); ++i) {
            double reproduced = 0;
            if (cached.priorSourceGroups.empty()) {
                const auto found = sourceIndexes.find(candidates[i].primitive.bits);
                if (found == sourceIndexes.end())
                    throw std::runtime_error("OOC MCTS prior trace direct primitive source missing");
                reproduced = sourceLogits.at(found->second);
            } else {
                const auto &group = cached.priorSourceGroups.at(i);
                if (group.empty()) throw std::runtime_error("OOC MCTS prior trace empty semantic source group");
                for (const auto source : group) {
                    const auto found = sourceIndexes.find(source.bits);
                    if (found == sourceIndexes.end())
                        throw std::runtime_error("OOC MCTS prior trace semantic source missing");
                    reproduced += sourceLogits.at(found->second);
                }
                reproduced /= group.size();
            }
            if (!std::isfinite(reproduced) || reproduced != cached.logits->at(i))
                throw std::runtime_error("OOC MCTS prior trace candidate-logit reproduction mismatch");
            reproducedCandidateLogits.push_back(reproduced);
        }

        auto expectedWeights = oocPolicyWeights(reproducedCandidateLogits, options.priorTemperature);
        std::map<std::uint32_t, std::size_t> multiplicity;
        for (const auto &candidate : candidates) ++multiplicity[candidate.primitive.bits];
        for (std::size_t i = 0; i < expectedWeights.size(); ++i) {
            expectedWeights[i] /= multiplicity.at(candidates[i].primitive.bits);
            if (!std::isfinite(expectedWeights[i]) || actions[i].id != candidates[i].id
                    || expectedWeights[i] != actions[i].prior)
                throw std::runtime_error("OOC MCTS prior trace planner-weight reproduction mismatch");
        }
        const double totalWeight = std::accumulate(expectedWeights.begin(), expectedWeights.end(), 0.0);
        if (!std::isfinite(totalWeight) || totalWeight <= 0)
            throw std::runtime_error("OOC MCTS prior trace invalid prior normalization");
        normalizedWeights.reserve(expectedWeights.size());
        for (const double weight : expectedWeights) normalizedWeights.push_back(weight / totalWeight);

        row["teacherCandidateLogits"] = reproducedCandidateLogits;
        row["teacherRawPriorWeights"] = expectedWeights;
        row["teacherNormalizedPrior"] = normalizedWeights;
    }

    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (actions[i].id != candidates[i].id)
            throw std::runtime_error("OOC MCTS prior trace candidate ID/order mismatch");
        const auto &candidate = candidates[i];
        nlohmann::json groups = nlohmann::json::array();
        if (!cached.priorSourceGroups.empty())
            for (const auto source : cached.priorSourceGroups.at(i)) groups.push_back(source.bits);
        nlohmann::json item = {{"candidateId", candidate.id}, {"semanticKey", candidate.key},
            {"primitiveBits", candidate.primitive.bits}, {"hasSemantic", candidate.semantic.has_value()},
            {"compoundSelector", int(candidate.compoundSelector)}, {"priorSourceGroup", std::move(groups)},
            {"searchPriorWeight", actions[i].prior}};
        if (modelPrior) {
            item["teacherCandidateLogit"] = cached.logits->at(i);
            item["teacherRawPriorWeight"] = actions[i].prior;
            item["teacherNormalizedPrior"] = normalizedWeights.at(i);
        }
        row["candidates"].push_back(std::move(item));
    }

    std::lock_guard<std::mutex> lock(liveTraceMutex);
    std::ofstream out(options.priorTracePath, std::ios::app);
    if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE cannot open output");
    out << row.dump() << '\n';
    if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE write failed");
    cached.priorTraceWritten = true;
}
std::vector<sts::search::OocPlannerAction> OocGameContextModel::legalActions(sts::search::OocStateId id) const {
    OocProfileScope priorBuild(OocProfileBucket::PriorBuild);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    auto &cached = mutableMetadata(id);
    if (cached.priors) return *cached.priors;
    const auto &actions = cached.candidates;
    OocProfileScope singletonPrior(OocProfileBucket::SingletonPrior, actions.size() == 1);
    if (actions.size() == 1) {
        std::vector<sts::search::OocPlannerAction> result{{actions.front().id, 1.0}};
        cached.priors = result;
        tracePrior(id, cached, result);
        return result;
    }
    const bool uniform = options.uniformPrior || !cached.sourcePriorCovered;
    auto weights = uniform ? std::vector<double>(actions.size(), 1.0)
                                      : oocPolicyWeights(policyLogits(id), options.priorTemperature);
    if (!uniform) {
        std::map<std::uint32_t, std::size_t> counts;
        for (const auto &a : actions) ++counts[a.primitive.bits];
        for (std::size_t i=0; i<actions.size(); ++i) weights[i] /= counts.at(actions[i].primitive.bits);
    }
    std::vector<sts::search::OocPlannerAction> result;
    result.reserve(actions.size());
    for (std::size_t i=0; i<actions.size(); ++i)
        result.push_back({actions[i].id, weights[i]});
    cached.priors = result;
    tracePrior(id, cached, result);
    return result;
}
sts::search::OocStateId OocGameContextModel::sampleSuccessor(sts::search::OocStateId id,
    sts::search::OocActionId action, std::mt19937_64 &rng) {
    OocProfileScope profile(OocProfileBucket::Successor);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS transition from leaf");
    auto &cached = mutableMetadata(id);
    const auto &actions = cached.candidates;
    auto it = std::find_if(actions.begin(), actions.end(), [&](const auto &a) { return a.id == action; });
    if (it == actions.end()) throw std::runtime_error("OOC MCTS illegal action ID");
    auto &edge = cached.edges.at(it - actions.begin());
    if (!options.sampleNoncombat && edge.deterministic) return *edge.deterministic;
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    // A live MAP root is searchable.  The hidden room outcome must be sampled
    // before transitionToMapNode consumes monster/shop/treasure chances.
    // Qualified successors retain their updated room counters.
    if (options.sampleNoncombat) {
        sampleNoncombatFuture(child.gc, rng);
        if (id == 0 && dependencies.sampleHiddenCounters)
            dependencies.sampleHiddenCounters(child.gc, rng);
    }
    if (it->semantic) {
        const auto executed = sts::search::executeOocSemanticAction(child.gc, *it->semantic);
        if (!executed.ok) throw sts::search::OocSearchUnsupported("semantic_execution:" + executed.error);
    } else it->primitive.execute(child.gc);
    collectForcedRewardGold(child.gc);
    child.path.update(child.gc);
    const bool enteredCombat = child.gc.screenState == sts::ScreenState::BATTLE;
    const auto encounter = enteredCombat ? child.gc.info.encounter : sts::MonsterEncounter::INVALID;
    // A sampled future can change the encounter and predictor input on every
    // visit. Never borrow a preparation from another hypothetical successor.
    std::unique_ptr<PreparedCombatTransition> sampledCombat;
    auto &preparationCache = options.sampleNoncombat ? sampledCombat : edge.combat;
    if (enteredCombat && combatSampler && !preparationCache) {
        OocProfileScope preparation(OocProfileBucket::CombatPrepare);
        const auto input = captureCombatPredictorInput(child.gc, child.gc.info.encounter,
                                                       dependencies.potionKeepValue(child.gc));
        preparationCache = combatSampler->prepare(child.gc, input);
        ++continuation_.preparedCombats;
    }
    if (enteredCombat) ++continuation_.combatEdgeSamples;
    if (options.checkpointLeaves && enteredCombat) {
        const auto outcome = resolveCombat(child, rng, preparationCache.get());
        child.combatPrediction = {true, encounter,
            outcome == CombatRuntimeSample::Outcome::DEATH ? "death"
            : outcome == CombatRuntimeSample::Outcome::ESCAPE ? "escape" : "victory"};
    }
    else if (combatSampler && enteredCombat) {
        if (preparationCache->support().supported) {
            ++combatSamples_;
            const auto sampled = preparationCache->sample(rng);
            if (sampled.outcome != CombatRuntimeSample::Outcome::UNSUPPORTED)
                child.combatPrediction = {true, encounter,
                    sampled.outcome == CombatRuntimeSample::Outcome::DEATH ? "death"
                    : sampled.outcome == CombatRuntimeSample::Outcome::ESCAPE ? "escape" : "victory"};
            switch (sampled.outcome) {
                case CombatRuntimeSample::Outcome::UNSUPPORTED: break;
                case CombatRuntimeSample::Outcome::DEATH:
                    child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                    break;
                case CombatRuntimeSample::Outcome::VICTORY:
                case CombatRuntimeSample::Outcome::ESCAPE:
                    applySampledCombatExit(child.gc, sampled);
                    // Live runs record the entered room before combat and the
                    // continuation on the next loop, including act changes.
                    child.path.update(child.gc);
                    break;
            }
        }
    }
    if (!options.sampleNoncombat && options.checkpointLeaves && !enteredCombat) edge.deterministic = states.size();
    states.push_back(std::move(child));
    return states.size()-1;
}
double OocGameContextModel::bossLeafValue(const GameContext &source) const {
    if (!combatSampler) throw std::runtime_error("OOC MCTS boss leaf requires combat evaluator");
    struct BossProbe { sts::MonsterEncounter encounter; int act, floor; };
    static constexpr BossProbe bosses[] = {
        {sts::MonsterEncounter::SLIME_BOSS, 1, 17},
        {sts::MonsterEncounter::THE_GUARDIAN, 1, 17},
        {sts::MonsterEncounter::HEXAGHOST, 1, 17},
        {sts::MonsterEncounter::CHAMP, 2, 34},
        {sts::MonsterEncounter::COLLECTOR, 2, 34},
        {sts::MonsterEncounter::AUTOMATON, 2, 34},
        {sts::MonsterEncounter::AWAKENED_ONE, 3, 50},
        {sts::MonsterEncounter::DONU_AND_DECA, 3, 50},
        {sts::MonsterEncounter::TIME_EATER, 3, 50},
        {sts::MonsterEncounter::THE_HEART, 4, 55}
    };
    double total = 0;
    for (const auto &boss : bosses) {
        auto probe = detachedCopy(source);
        const auto encounter = boss.encounter;
        probe.act = boss.act;
        probe.floorNum = boss.floor;
        probe.curRoom = sts::Room::BOSS;
        probe.info.encounter = encounter;
        const auto input = captureCombatPredictorInput(probe, encounter,
                                                       dependencies.potionKeepValue(probe));
        const auto estimate = combatSampler->expectation(probe, input);
        if (!estimate.supported)
            throw sts::search::OocSearchUnsupported("boss_leaf_unsupported_" + std::to_string((int)encounter));
        const double value = bossLeafUtility(estimate);
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("OOC MCTS invalid boss leaf value");
        total += value;
    }
    return total / std::size(bosses);
}
double OocGameContextModel::leafValue(sts::search::OocStateId id) const {
    OocProfileScope profile(OocProfileBucket::EvaluateLeaf);
    if (options.checkpointLeaves && !terminalValue(id)
        && state(id).screenState != sts::ScreenState::MAP_SCREEN)
        throw std::runtime_error("OOC MCTS leaf requires a resolved map checkpoint");
    if (auto terminal = terminalValue(id)) return *terminal;
    if (options.checkpointLeaves && options.constantLeaf) return 0.5;
    if (options.bossLeaf) return bossLeafValue(state(id));
    OocProfileScope inference(OocProfileBucket::LeafValue);
    return anchorValue(state(id), states.at(id).path);
}
std::optional<std::uint64_t> OocGameContextModel::outcomeEquivalenceKey(sts::search::OocStateId id) const {
    // Without sampled futures a successor's concrete RNG is its future.
    if (!options.sampleNoncombat) return std::nullopt;
    return outcomeEquivalenceKeyOf(state(id), pathHistory(id));
}
bool OocGameContextModel::isDeterministicTransition(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    if (options.sampleNoncombat) return false;
    const auto &cached = metadata(id);
    const auto it = std::find_if(cached.candidates.begin(), cached.candidates.end(),
        [&](auto candidate) { return candidate.id == action; });
    return it != cached.candidates.end() && cached.edges.at(it-cached.candidates.begin()).deterministic.has_value();
}
CombatRuntimeSample::Outcome OocGameContextModel::resolveCombat(Snapshot &child, std::mt19937_64 &rng,
    const PreparedCombatTransition *prepared) {
    OocProfileScope profile(OocProfileBucket::CombatResolve);
    ++continuation_.imaginedCombats;
    const int battleAct = child.gc.act;
    const auto battleRoom = child.gc.curRoom;
    bool victory = false;
    auto sampledOutcome = CombatRuntimeSample::Outcome::UNSUPPORTED;
    const auto input = prepared ? CombatPredictorInputV1{}
        : captureCombatPredictorInput(child.gc, child.gc.info.encounter,
                                      dependencies.potionKeepValue(child.gc));
    const auto support = prepared ? prepared->support()
        : combatSampler ? combatSampler->support(child.gc, input)
                        : CombatRuntimeSupport{false, "missing_sampler"};
    auto reason = support.reason;
    if (support.supported) {
        const auto sampled = prepared ? prepared->sample(rng) : combatSampler->sample(child.gc, input, rng);
        if (sampled.outcome != CombatRuntimeSample::Outcome::UNSUPPORTED) {
            sampledOutcome = sampled.outcome;
            ++combatSamples_;
            if (sampled.outcome == CombatRuntimeSample::Outcome::DEATH) {
                child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                return sampledOutcome;
            }
            applySampledCombatExit(child.gc, sampled);
            victory = true;
        } else reason = "sample_returned_unsupported";
    }
    if (!victory) {
        ++continuation_.unsupportedCombats;
        ++continuation_.supportReasons[reason.empty() ? "unspecified" : reason];
        throw sts::search::OocSearchUnsupported(reason.empty() ? "unspecified" : reason);
    }
    if (victory && dependencies.stopAfterAct() > 0 && battleAct == dependencies.stopAfterAct()
            && battleRoom == sts::Room::BOSS)
        child.gc.outcome = sts::GameOutcome::PLAYER_VICTORY;
    child.path.update(child.gc);
    return sampledOutcome;
}
namespace {
template<class Checkpoint, class Step>
double boundedContinuation(int maxSteps, Checkpoint checkpoint, Step advance) {
    for (int step=0; step<maxSteps; ++step) {
        if (const auto value=checkpoint()) return *value;
        advance();
    }
    if (const auto value=checkpoint()) return *value;
    throw sts::search::OocSearchUnsupported("continuation_step_limit_" + std::to_string(maxSteps));
}

#ifndef STS_LIVE_ADVISOR
// Preserve observers and run-local policy bookkeeping across detached work.
struct ImaginedScope {
    const PathHistory *path = t_curPath;
    std::string rows = std::move(t_oocStrategicTraceRows);
    int decision = t_oocStrategicTraceDecision;
    bool shop = t_shopV, tok = t_tokCheckPending;
    int probeDecision = t_actFightProbeDecisionIdx, probeAction = t_actFightProbeActionIdx,
        probeFuture = t_actFightProbeFutureIdx;
    decltype(sts::search::g_onGameActionExecute) observer = std::move(sts::search::g_onGameActionExecute);
    decltype(sts::search::g_onCombatDecision) combatObserver=std::move(sts::search::g_onCombatDecision);
    decltype(sts::g_onBattleExitPersistent) exitObserver=std::move(sts::g_onBattleExitPersistent);
    sts::search::NativeSilverCombatStats silver = sts::search::g_nativeSilverCombatStats;
    bool disallowed = sts::search::g_disallowImaginedCombat;
    ImaginedScope() {
        sts::search::g_disallowImaginedCombat=true;
        t_tokCheckPending=false; sts::search::g_onGameActionExecute={};
        sts::search::g_onCombatDecision={};
        sts::g_onBattleExitPersistent={};
    }
    ~ImaginedScope() {
        t_curPath=path; t_oocStrategicTraceRows=std::move(rows); t_oocStrategicTraceDecision=decision;
        t_shopV=shop; t_tokCheckPending=tok;
        t_actFightProbeDecisionIdx=probeDecision; t_actFightProbeActionIdx=probeAction; t_actFightProbeFutureIdx=probeFuture;
        sts::search::g_onGameActionExecute=std::move(observer);
        sts::search::g_onCombatDecision=std::move(combatObserver);
        sts::g_onBattleExitPersistent=std::move(exitObserver);
        sts::search::g_nativeSilverCombatStats=silver;
        sts::search::g_disallowImaginedCombat=disallowed;
    }
};
#endif
}
namespace {
sts::search::OocEndpoint endpointOf(const sts::GameContext &gc) {
    return {gc.curHp, gc.maxHp, gc.floorNum};
}
}
std::optional<sts::search::OocEndpoint> OocGameContextModel::endpoint(sts::search::OocStateId id) const {
    return endpointOf(state(id));
}
double OocGameContextModel::evaluateLeaf(sts::search::OocStateId id, std::mt19937_64 &rng) {
    bool terminal = false;
    sts::search::OocEndpoint endpoint;
    return evaluateLeafImpl(id, rng, terminal, endpoint);
}
sts::search::OocLeafEvaluation OocGameContextModel::evaluateLeafWithOutcome(
        sts::search::OocStateId id, std::mt19937_64 &rng) {
    bool terminal = false;
    sts::search::OocEndpoint endpoint;
    const double value = evaluateLeafImpl(id, rng, terminal, endpoint);
    return {value, terminal, endpoint};
}
std::optional<double> OocGameContextModel::screenLeafValue(const GameContext &gc, const PathHistory &path) {
#ifdef STS_LIVE_ADVISOR
    (void)gc; (void)path; throw std::runtime_error("screen leaf is unavailable in the live advisor");
#else
    if (!options.screenLeafNet && !options.screenLeafGbm) throw std::runtime_error("screen leaf requested without a loaded model");
    nlohmann::json contract;
    try { contract = screenLeafPublicContract(gc); }
    catch (const std::exception &) { ++continuation_.screenLeafFallbacks; return std::nullopt; }
    const auto &contents = contract.at("screenContents");
    if (options.screenLeafNet && !options.screenLeafNet->covers(contents.at("screen").get<std::string>())) {
        ++continuation_.screenLeafFallbacks; return std::nullopt;
    }
    std::vector<float> rich;
    if (options.screenLeafGbm) rich = richFeatureVec(gc, path);
    else {
        const std::string row = richRow(gc, path);
        rich.reserve(1017);
        for (const char *p = row.c_str(); *p;) {
            char *end = nullptr; rich.push_back(std::strtof(p, &end));
            if (end == p) throw std::runtime_error("screen leaf rich row parse");
            p = *end == ',' ? end + 1 : end;
        }
    }
    OocProfileScope inference(OocProfileBucket::LeafValue);
    ++continuation_.screenLeafEvaluations;
    const auto keys = contract.at("candidateKeys").get<std::vector<std::string>>();
    if (options.screenLeafGbm) {
        static const int goldIndex = richIdxMap().at("gold");
        const auto screenFeatures = screenGbmFeatures(contents, keys, rich.at(goldIndex));
        rich.insert(rich.end(), screenFeatures.begin(), screenFeatures.end());
        const double x2b = std::clamp(anchorValue(gc, path), 1e-7, 1 - 1e-7);
        const double margin = std::log(x2b / (1 - x2b)) + options.screenLeafGbm->residual(rich);
        return 1.0 / (1.0 + std::exp(-margin));
    }
    return options.screenLeafNet->predictFromRich(rich, contents, keys);
#endif
}
double OocGameContextModel::anchorValue(const GameContext &gc, const PathHistory &path) const {
#ifndef STS_LIVE_ADVISOR
    if (options.screenLeafGbm && options.screenLeafGbm->hasAnchor()) {
        OocProfileScope predict(OocProfileBucket::LeafPredict);
        return options.screenLeafGbm->anchor(richFeatureVec(gc, path));
    }
#endif
    return dependencies.leafValue(gc, path);
}
// `endpoint` receives the player state that was actually evaluated: the node
// itself, or the detached continuation where it stopped.
double OocGameContextModel::evaluateLeafImpl(sts::search::OocStateId id,
        std::mt19937_64 &rng, bool &terminal, sts::search::OocEndpoint &endpoint) {
    terminal = terminalValue(id).has_value();
    endpoint = endpointOf(state(id));
    OocProfileScope profile(OocProfileBucket::EvaluateLeaf);
    if (id != 0 && state(id).screenState == sts::ScreenState::MAP_SCREEN
            && options.stopAtMapCheckpoint)
        return leafValue(id);
    if (!options.checkpointLeaves && !options.sampleNoncombat) return leafValue(id);
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    struct EndpointOnExit {
        const GameContext &gc; sts::search::OocEndpoint &out;
        ~EndpointOnExit() { out = endpointOf(gc); }
    } endpointOnExit{child.gc, endpoint};
    if (options.sampleNoncombat) {
        sampleNoncombatFuture(child.gc, rng);
        if (id == 0 && dependencies.sampleHiddenCounters)
            dependencies.sampleHiddenCounters(child.gc, rng);
    }
    if (!options.checkpointLeaves) {
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) { terminal = true; return 0; }
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) { terminal = true; return 1; }
        return options.bossLeaf ? bossLeafValue(child.gc)
            : anchorValue(child.gc, child.path);
    }
#ifndef STS_LIVE_ADVISOR
    ImaginedScope scope;
    t_curPath=&child.path;
#endif
    if (child.gc.screenState == sts::ScreenState::BATTLE) ++continuation_.battleLeaves;
    else if (child.gc.screenState == sts::ScreenState::MAP_SCREEN) ++continuation_.mapLeaves;
    else ++continuation_.pendingLeaves;
    const int maxSteps = options.leafCombats ? 1024 : 256;
    unsigned additionalCombats = 0;
    const auto checkpoint = [&]() -> std::optional<double> {
        child.path.update(child.gc);
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) { terminal = true; return 0; }
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) { terminal = true; return 1; }
        if (options.screenLeaf && child.gc.screenState != sts::ScreenState::BATTLE
                && child.gc.screenState != sts::ScreenState::MAP_SCREEN)
            if (const auto value = screenLeafValue(child.gc, child.path)) return value;
        // Direct probe: value the first non-combat state without a playout.
        if (((options.directLeaf || options.screenLeaf) && child.gc.screenState != sts::ScreenState::BATTLE)
                || (child.gc.screenState == sts::ScreenState::MAP_SCREEN
                && (additionalCombats >= options.leafCombats || options.stopAtMapCheckpoint))) {
            if (options.constantLeaf) return 0.5;
            if (options.bossLeaf) return bossLeafValue(child.gc);
            OocProfileScope inference(OocProfileBucket::LeafValue);
            return anchorValue(child.gc, child.path);
        }
        return std::nullopt;
    };
    return boundedContinuation(maxSteps,checkpoint,[&] {
        ++continuation_.projectionSteps;
        if (child.gc.screenState == sts::ScreenState::BATTLE) { resolveCombat(child,rng); ++additionalCombats; }
        else {
            if (options.sampleNoncombat) sampleNoncombatFuture(child.gc, rng);
            bool applied = false;
            if (options.uniformLeafPolicy && v4DecisionSupported(child.gc)) {
                const auto actions = v4CandidateActions(child.gc);
                std::set<std::uint32_t> ids;
                bool unique = !actions.empty();
                for (auto action : actions) if (!ids.insert(action.bits).second) unique = false;
                if (unique) {
                    const auto selected = std::uniform_int_distribution<std::size_t>(0, actions.size()-1)(rng);
                    actions[selected].execute(child.gc); applied = true;
                }
            }
            if (!applied) {
                if (!dependencies.continuationStep)
                    throw sts::search::OocSearchUnsupported("missing_continuation_step");
                dependencies.continuationStep(child.gc, child.path, rng);
            }
        }
    });
}

}

namespace one_combat {
sts::search::OocMctsResult searchWithSoleRootShortcut(sts::search::OocGenerativeModel &model,
    const sts::search::OocMctsConfig &config, std::optional<sts::search::OocActionId> soleAction,
    std::uint64_t simulations) {
    if (!config.observeRootLock && config.rootCheckpointSimulations.empty()
        && config.maxDepth && soleAction) {
        sts::search::OocMctsResult result;
        result.selectedAction = soleAction;
        result.rootActions.push_back({*soleAction, 1.0, 0, 0.0});
        result.metrics.trivialRootBypasses = 1;
        return result;
    }
    return sts::search::OocMctsPlanner(config).search(model, 0, simulations);
}
}

#ifndef STS_LIVE_ADVISOR
namespace one_combat {

namespace {
bool liveEnabled = false;
std::uint64_t liveSimulations = 512;
sts::search::OocMctsConfig liveConfig;
OocAdapterOptions liveOptions{true};
std::shared_ptr<const CombatTransitionSampler> liveSampler;
std::string liveTrace, liveRootLockTrace, liveCheckpointTrace;
std::uint64_t splitMix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
// Parsing is strict: no whitespace, trailing text, nonfinite or out-of-range knobs.
void applyLiveControl(const std::string &key, const std::string &value,
                      sts::search::OocMctsConfig &config, OocAdapterOptions &opts) {
    const auto invalid = [&] { throw std::runtime_error(key + " invalid value: " + value); };
    const auto choice = [&](const char *a, const char *b) {
        if (value == a) return false;
        if (value == b) return true;
        invalid(); return false;
    };
    const auto number = [&] {
        if (value.empty() || value.find_first_not_of("0123456789.+-eE") != std::string::npos) invalid();
        std::size_t end = 0; double x = 0;
        try { x = std::stod(value, &end); } catch (...) { invalid(); }
        if (end != value.size() || !std::isfinite(x)) invalid();
        return x;
    };
    const auto integer = [&] {
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos) invalid();
        unsigned long long x = 0;
        try { x = std::stoull(value); } catch (...) { invalid(); }
        return x;
    };
    if (key == "STS_OOC_MCTS_PRIOR") opts.uniformPrior = choice("policy", "uniform");
    else if (key == "STS_OOC_MCTS_LEAF_VALUE") {
        opts.constantLeaf = opts.bossLeaf = opts.directLeaf = opts.screenLeaf = opts.screenGbm = false;
        if (value == "native") {}
        else if (value == "constant") opts.constantLeaf = true;
        else if (value == "boss") opts.bossLeaf = true;
        else if (value == "direct") opts.directLeaf = true;
        else if (value == "screen") opts.screenLeaf = true;
        else if (value == "screengbm") opts.screenLeaf = opts.screenGbm = true;
        else invalid();
    }
    else if (key == "STS_OOC_MCTS_LEAF_POLICY") opts.uniformLeafPolicy = choice("v4", "uniform");
    else if (key == "STS_OOC_MCTS_EARLY_STOP") config.allowUnqualifiedRootStop = choice("0", "1");
    else if (key == "STS_OOC_MCTS_GAP_STOP_20") config.stopAt512VisitGap20 = choice("0", "1");
    else if (key == "STS_OOC_MCTS_MERGE_OUTCOMES") config.mergeEquivalentOutcomes = choice("0", "1");
    else if (key == "STS_OOC_MCTS_ROOT_SELECTION") config.selectByMeanQ = choice("visits", "q");
    else if (key == "STS_OOC_MCTS_TEMPERATURE") { const double x = number(); if (x <= 0) invalid(); opts.priorTemperature = x; }
    else if (key == "STS_OOC_MCTS_CPUCT") { const double x = number(); if (x < 0) invalid(); config.cPuct = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_K") { const double x = number(); if (x <= 0) invalid(); config.wideningK = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_ALPHA") { const double x = number(); if (x <= 0 || x >= 1) invalid(); config.wideningAlpha = x; }
    else if (key == "STS_OOC_MCTS_MAX_DEPTH") { const auto x = integer(); if (!x || x > 512) invalid(); config.maxDepth = x; }
    else if (key == "STS_OOC_MCTS_LEAF_COMBATS") { const auto x = integer(); if (x != 0 && x != 1 && x != 3) invalid(); opts.leafCombats = x; }
    else invalid();
}
const char *const liveControlKeys[] = {
    "STS_OOC_MCTS_EARLY_STOP", "STS_OOC_MCTS_GAP_STOP_20", "STS_OOC_MCTS_PRIOR", "STS_OOC_MCTS_TEMPERATURE", "STS_OOC_MCTS_CPUCT",
    "STS_OOC_MCTS_WIDEN_K", "STS_OOC_MCTS_WIDEN_ALPHA", "STS_OOC_MCTS_MAX_DEPTH",
    "STS_OOC_MCTS_ROOT_SELECTION", "STS_OOC_MCTS_LEAF_VALUE",
    "STS_OOC_MCTS_LEAF_COMBATS", "STS_OOC_MCTS_LEAF_POLICY", "STS_OOC_MCTS_MERGE_OUTCOMES"
};
void recordSearchAbort(const sts::search::OocMctsResult &result, OocContinuationMetrics &continuation) {
    if (!result.aborted) return;
    if (result.abortReason.rfind("continuation_step_limit_",0) == 0
            || result.abortReason.rfind("ooc_depth_safety_cap_",0) == 0) {
        ++continuation.continuationLimitAborts;
        ++continuation.continuationReasons[result.abortReason];
    } else if (result.abortReason.rfind("semantic_execution:",0) == 0) {
        ++continuation.supportReasons[result.abortReason];
    } else if (!continuation.unsupportedCombats) {
        // A continuation policy attempted a forbidden native combat before resolveCombat.
        ++continuation.imaginedCombats; ++continuation.unsupportedCombats;
        ++continuation.supportReasons[result.abortReason];
    }
}
double threadCpuSeconds() {
    timespec t{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t) != 0)
        throw std::runtime_error("OOC MCTS thread CPU clock unavailable");
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}
// Reroot-opportunity measurement (issue #339): observation only. Identity is
// the state as the sampled live search treats it. Hidden stream seeds, pool
// order, unrevealed encounter suffixes and hidden chest/Dead Adventurer
// contents are re-determinized at every transition, so they are excluded.
// Public identity keeps the copied native room/potion/rarity counters; the
// RNG identity additionally keeps stream draw counters, which the search's
// own encounter re-determinization advances.
std::string liveReuseTrace;
std::uint64_t reusePublicFingerprint(const GameContext &g, const PathHistory &path, bool rngCounters) {
    sts::test::ooc_state_detail::Writer w;
    w.values(g.noteForYourselfCard, g.skipBattles);
    if (rngCounters)
        for (auto stream : {&g.aiRng, &g.cardRandomRng, &g.cardRng, &g.eventRng,
                &g.mathUtilRng, &g.merchantRng, &g.miscRng, &g.monsterHpRng,
                &g.monsterRng, &g.neowRng, &g.potionRng, &g.relicRng,
                &g.shuffleRng, &g.treasureRng}) w.value(stream->counter);
    w.values(g.monsterChance, g.shopChance, g.treasureChance,
             g.potionChance, g.cardRarityFactor);
    const auto members = [&](auto pool) {
        std::sort(pool.begin(), pool.end());
        w.sequence(pool);
    };
    members(g.eventList); members(g.shrineList); members(g.specialOneTimeEventList);
    members(g.commonRelicPool); members(g.uncommonRelicPool); members(g.rareRelicPool);
    members(g.shopRelicPool); members(g.bossRelicPool); members(g.colorlessCardPool);
    w.value(g.monsterListOffset);
    for (int i = 0; i < std::min<int>(g.monsterListOffset, g.monsterList.size()); ++i) w.value(g.monsterList[i]);
    w.value(g.eliteMonsterListOffset);
    for (int i = 0; i < std::min<int>(g.eliteMonsterListOffset, g.eliteMonsterList.size()); ++i)
        w.value(g.eliteMonsterList[i]);
    if (!(g.act == 3 && g.ascension >= 20)) w.value(g.secondBoss);
    auto info = g.info;
    if (g.screenState == sts::ScreenState::TREASURE_ROOM) {
        info.haveGold = false;
        info.tier = sts::RelicTier::COMMON;
    }
    if (g.screenState == sts::ScreenState::EVENT_SCREEN && g.curEvent == sts::Event::DEAD_ADVENTURER
            && info.phase >= 0 && info.phase <= int(info.rewards.size()))
        std::sort(info.rewards.begin() + info.phase, info.rewards.end());
    w.values(g.outcome, g.screenState, info, g.lastRoom, g.curEvent, g.curRoom, g.boss,
             g.shopRemoveCount, g.speedrunPace, g.curMapNodeX, g.curMapNodeY, static_cast<bool>(g.map));
    if (g.map) {
        w.values(g.map->burningEliteX, g.map->burningEliteY, g.map->burningEliteBuff);
        for (const auto &row : g.map->nodes) w.sequence(row);
    }
    w.values(g.act, g.ascension, g.floorNum, g.cc, g.curHp, g.maxHp, g.gold,
             g.potionCount, g.potionCapacity, g.wingBootsCharges);
    w.sequence(g.potions);
    w.sequence(g.relics.relics);
    w.values(g.relics.relicBits0, g.relics.relicBits1, g.relics.relicBits2);
    w.sequence(g.deck.cards);
    w.sequence(g.deck.cardTypeCounts);
    w.sequence(g.deck.bottleIdxs);
    w.values(g.deck.upgradeableCount, g.deck.transformableCount,
             g.blueKey, g.greenKey, g.redKey,
             static_cast<bool>(g.regainControlAction), g.smokeBombUsed);
    w.sequence(path.roomVisits);
    w.value(path.lastNodeKey);
    return std::hash<std::string>{}(w.finish());
}
struct ReuseCandidate {
    std::uint64_t visits = 0, subtreeDecisionNodes = 0;
    std::uint32_t depth = 0;
    sts::search::OocActionId rootAction = 0;
    bool combat = false, publicStochastic = false;
};
// Stored decision nodes of the most recent completed non-singleton search.
struct ReuseIndex {
    bool valid = false, truncated = false;
    std::uint64_t seed = 0, decision = 0, simulations = 0, storedDecisionNodes = 0;
    int floor = -1, screen = -1;
    sts::search::OocActionId selected = 0;
    std::unordered_multimap<std::uint64_t, ReuseCandidate> rng, publicState;
};
thread_local ReuseIndex t_reuseIndex;
ReuseIndex buildReuseIndex(const OocGameContextModel &model, const sts::search::OocTreeSnapshot &tree) {
    ReuseIndex index;
    index.truncated = tree.truncated;
    const auto n = tree.nodes.size();
    std::vector<std::optional<std::uint64_t>> parent(n);
    std::vector<std::vector<std::uint64_t>> children(n);
    for (const auto &edge : tree.edges)
        if (edge.childId) { parent[*edge.childId] = edge.parentId; children[edge.parentId].push_back(*edge.childId); }
    std::vector<std::uint64_t> rngKey(n), publicKey(n), subtree(n);
    std::vector<ReuseCandidate> info(n);
    for (std::uint64_t i = 0; i < n; ++i) {
        const auto &node = tree.nodes[i];
        if (!node.chance) {
            rngKey[i] = reusePublicFingerprint(model.state(node.state), model.pathHistory(node.state), true);
            publicKey[i] = reusePublicFingerprint(model.state(node.state), model.pathHistory(node.state), false);
        }
    }
    // Snapshot nodes are breadth-first: every parent precedes its children.
    for (std::uint64_t i = 0; i < n; ++i) {
        const auto &node = tree.nodes[i];
        if (!parent[i]) continue;
        auto &current = info[i];
        current = info[*parent[i]];
        if (node.chance) {
            if (node.depth == 0) current.rootAction = node.action;
            std::set<std::uint64_t> outcomes;
            for (auto child : children[i]) outcomes.insert(publicKey[child]);
            current.publicStochastic = current.publicStochastic || outcomes.size() > 1;
        } else {
            current.depth = node.depth;
            current.visits = node.visits;
            current.combat = current.combat || model.prediction(node.state).used;
        }
    }
    for (std::uint64_t i = n; i-- > 0;) {
        subtree[i] += tree.nodes[i].chance ? 0 : 1;
        if (parent[i]) subtree[*parent[i]] += subtree[i];
    }
    for (std::uint64_t i = 1; i < n; ++i) {
        if (tree.nodes[i].chance) continue;
        info[i].subtreeDecisionNodes = subtree[i];
        index.rng.emplace(rngKey[i], info[i]);
        index.publicState.emplace(publicKey[i], info[i]);
        ++index.storedDecisionNodes;
    }
    return index;
}
nlohmann::json reuseMatchJson(const ReuseIndex &index, const std::unordered_multimap<std::uint64_t, ReuseCandidate> &stored,
                              std::uint64_t key) {
    const auto [first, last] = stored.equal_range(key);
    std::uint64_t matches = 0, selectedMatches = 0, selectedVisits = 0;
    const ReuseCandidate *best = nullptr;
    for (auto it = first; it != last; ++it) {
        const auto &candidate = it->second;
        const bool selected = candidate.rootAction == index.selected;
        ++matches; selectedMatches += selected;
        if (selected) selectedVisits += candidate.visits;
        const bool bestSelected = best && best->rootAction == index.selected;
        if (!best || (selected && !bestSelected) || (selected == bestSelected && candidate.visits > best->visits))
            best = &candidate;
    }
    // Summed visits over publicly identical particles bound what merging them
    // could retain; direct rerooting retains only the best single particle.
    nlohmann::json row = {{"matches", matches}, {"selectedBranchMatches", selectedMatches},
        {"selectedBranchVisitsSum", selectedVisits}};
    if (best) row["best"] = {{"depth", best->depth}, {"visits", best->visits},
        {"subtreeDecisionNodes", best->subtreeDecisionNodes}, {"underSelectedAction", best->rootAction == index.selected},
        {"combatOnPath", best->combat}, {"publicStochasticOnPath", best->publicStochastic}};
    return row;
}
}
bool liveOocMctsEnabled() { return liveEnabled; }
std::uint64_t oocMctsSearchSeed(std::uint64_t seed, std::uint64_t index) {
    return splitMix64(seed ^ splitMix64(index));
}
void configureLiveOocMcts() {
    const char *enabled = std::getenv("STS_OOC_MCTS");
    if (enabled && std::string(enabled) != "0" && std::string(enabled) != "1")
        throw std::runtime_error("STS_OOC_MCTS must be 0 or 1");
    liveEnabled = enabled && std::string(enabled) == "1";
    if (const char *trace = std::getenv("STS_OOC_MCTS_TRACE")) liveTrace = trace;
    if (!liveTrace.empty()) {
        std::ofstream out(liveTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot open output");
    }
    liveRootLockTrace.clear();
    liveCheckpointTrace.clear();
    liveReuseTrace.clear();
    liveSimulations = 512; liveConfig = {}; liveOptions = {true};
    liveGraphPath.clear(); liveGraphDecisionIndex = 1;
    if (!liveEnabled) return;
    if (const char *path = std::getenv("STS_OOC_MCTS_GRAPH_FILE")) liveGraphPath = path;
    if (const char *index = std::getenv("STS_OOC_MCTS_GRAPH_DECISION_INDEX")) {
        const std::string value(index);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("STS_OOC_MCTS_GRAPH_DECISION_INDEX must be a nonnegative integer");
        liveGraphDecisionIndex = std::stoull(value);
    }
    if (sts::search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("live OOC MCTS requires frozen Silver reuse cap 32768");
    if (!g_oocStrategicTokNet.ok) throw std::runtime_error("STS_OOC_MCTS requires native V4 policy");
    const char *leafValue = std::getenv("STS_OOC_MCTS_LEAF_VALUE");
    const bool bossLeafRequested = leafValue && std::string(leafValue) == "boss";
    if (!bossLeafRequested && !winNetOk()) throw std::runtime_error("STS_OOC_MCTS requires native v_win");
    // Legacy win loading may retry the default. An explicit failed request must
    // remain a startup failure even if that retry succeeded.
    if (const char *requested = std::getenv("STS_WIN_NET")) {
        CompactTreeNet explicitWin;
        const std::string path = std::string(requested) == "1" ? "models/v_win_trees.txt" : requested;
        if (!explicitWin.load(path, richIdxMap()))
            throw std::runtime_error("STS_OOC_MCTS explicit STS_WIN_NET failed to load");
    }
    if (const char *sims = std::getenv("STS_OOC_MCTS_SIMS")) {
        const std::string value(sims);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("STS_OOC_MCTS_SIMS must be a positive integer");
        liveSimulations = std::stoull(value);
        if (!liveSimulations) throw std::runtime_error("STS_OOC_MCTS_SIMS must be positive");
    }
    liveConfig = {}; liveOptions = {true};
    liveOptions.sampleNoncombat = true;
    liveOptions.collectKeys = g_collectKeys;
    if (const char *trace = std::getenv("STS_OOC_MCTS_PRIOR_TRACE"); trace && *trace) {
        liveOptions.priorTracePath = trace;
        std::ofstream out(liveOptions.priorTracePath, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE cannot open output");
    }
    liveConfig.allowUnqualifiedRootStop = true; // May skip later aborts; provider guarantee remains false.
    for (const char *key : liveControlKeys)
        if (const char *value = std::getenv(key)) applyLiveControl(key, value, liveConfig, liveOptions);
    // Default leaf (ADR-0027): GBM screen leaf on a pinned X2-B anchor. STS_OOC_MCTS_LEAF_VALUE=native rolls back.
    if (!std::getenv("STS_OOC_MCTS_LEAF_VALUE")) applyLiveControl("STS_OOC_MCTS_LEAF_VALUE", "screengbm", liveConfig, liveOptions);
    if (liveOptions.screenLeaf) {
        const char *model = std::getenv("STS_OOC_MCTS_SCREEN_LEAF_MODEL");
        if (liveOptions.screenGbm && (!model || !*model)) model = kDefaultScreenGbmModel;
        if (!model || !*model) throw std::runtime_error("STS_OOC_MCTS_LEAF_VALUE=screen requires STS_OOC_MCTS_SCREEN_LEAF_MODEL");
#ifdef STS_LIVE_ADVISOR
        throw std::runtime_error("STS_OOC_MCTS_LEAF_VALUE=screen is unavailable in the live advisor");
#else
        if (liveOptions.screenGbm)
            liveOptions.screenLeafGbm = std::make_shared<const ScreenLeafGbm>(model, richIdxMap(),
                int(richIdxMap().size()), kScreenGbmAnchor);
        else liveOptions.screenLeafNet = std::make_shared<const ScreenLeafNet>(model);
#endif
    }
    if (liveConfig.stopAt512VisitGap20
        && (liveSimulations != 2048 || liveConfig.selectByMeanQ))
        throw std::runtime_error("STS_OOC_MCTS_GAP_STOP_20 requires 2048 visit-selected simulations");
    if (const char *trace = std::getenv("STS_OOC_MCTS_ROOT_LOCK_TRACE")) liveRootLockTrace = trace;
    liveConfig.observeRootLock = !liveRootLockTrace.empty();
    if (const char *trace = std::getenv("STS_OOC_MCTS_REUSE_TRACE")) liveReuseTrace = trace;
    if (!liveReuseTrace.empty()) {
        if (!liveGraphPath.empty())
            throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE cannot be combined with STS_OOC_MCTS_GRAPH_FILE");
        std::ofstream out(liveReuseTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE cannot open output");
        std::cout << "[ooc-reuse-observer ON live_policy_unchanged=1 tree_node_cap=100000]\n";
    }
    if (const char *trace = std::getenv("STS_OOC_MCTS_CHECKPOINT_TRACE")) liveCheckpointTrace = trace;
    if (!liveCheckpointTrace.empty()) {
        if (liveSimulations != 2048 || liveConfig.selectByMeanQ || liveConfig.observeRootLock)
            throw std::runtime_error("checkpoint shadow requires 2048 visit selection and no root-lock observer");
        std::ofstream out(liveCheckpointTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_CHECKPOINT_TRACE cannot open output");
        std::cout << "[ooc-checkpoint-shadow ON live_policy_unchanged=1 checkpoints=128,256,512,1024,2048]\n";
    }
    if (liveConfig.observeRootLock) {
        std::ofstream out(liveRootLockTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE cannot open output");
        std::cout << "[ooc-root-lock-observer ON full_budget=1 hypothetical_only=1]\n";
    }
    const char *artifactOverride = std::getenv("STS_OOC_MCTS_COMBAT_MODEL");
    if (artifactOverride && !*artifactOverride)
        throw std::runtime_error("STS_OOC_MCTS_COMBAT_MODEL cannot be empty when set");
    const bool automaticDefaultStack=artifactOverride==nullptr;
    const std::string artifact=automaticDefaultStack?
        "selfplay/models/combat_transition_deepsets_lizard_t2.native":artifactOverride;
    const char *brewFallbackOverride = std::getenv("STS_OOC_MCTS_BREW_FALLBACK_MODEL");
    if (brewFallbackOverride && !*brewFallbackOverride)
        throw std::runtime_error("STS_OOC_MCTS_BREW_FALLBACK_MODEL cannot be empty when set");
    const std::string brewFallbackArtifact=brewFallbackOverride?brewFallbackOverride:
        (automaticDefaultStack?"selfplay/models/combat_transition_near_full_except_smoke_v2.native":"");
    const char *activeLizardOverride=std::getenv("STS_OOC_MCTS_ACTIVE_LIZARD");
    bool activeLizardEnabled=automaticDefaultStack;
    if(activeLizardOverride) {
        if(std::string(activeLizardOverride)=="0")activeLizardEnabled=false;
        else if(std::string(activeLizardOverride)=="1")activeLizardEnabled=true;
        else throw std::runtime_error("STS_OOC_MCTS_ACTIVE_LIZARD must be 0 or 1 when set");
    }
    if(activeLizardEnabled && brewFallbackArtifact.empty())
        throw std::runtime_error("STS_OOC_MCTS_ACTIVE_LIZARD=1 requires STS_OOC_MCTS_BREW_FALLBACK_MODEL");
    if(!brewFallbackArtifact.empty())
        liveSampler = std::make_shared<EntropicBrewFallbackCombatTransitionSampler>(
            artifact,brewFallbackArtifact,activeLizardEnabled);
    else
        liveSampler = std::make_shared<NativeCombatTransitionSampler>(artifact);
    const auto precision = std::cout.precision();
    std::cout << std::setprecision(17) << "[live OOC MCTS ON sims=" << liveSimulations
        << " combat_model=" << artifact
        << (!brewFallbackArtifact.empty() ? std::string(" brew_fallback_model=")+brewFallbackArtifact+
            " dispatch=precombat_entropic_brew" : std::string{})
        << " active_lizard_correction=" << (activeLizardEnabled?"1":"0")
        << " prior=" << (liveOptions.uniformPrior ? "uniform" : "policy")
        << " temperature=" << liveOptions.priorTemperature << " cpuct=" << liveConfig.cPuct
        << " widen_k=" << liveConfig.wideningK << " widen_alpha=" << liveConfig.wideningAlpha
        << " max_depth=" << liveConfig.maxDepth << " root_selection=" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << " early_stop=" << liveConfig.allowUnqualifiedRootStop
        << " gap_stop_20=" << liveConfig.stopAt512VisitGap20
        << " merge_outcomes=" << liveConfig.mergeEquivalentOutcomes
        << " leaf_value=" << (liveOptions.bossLeaf ? "boss" : liveOptions.constantLeaf ? "constant" : liveOptions.directLeaf ? "direct" : liveOptions.screenLeaf ? (liveOptions.screenLeafGbm ? "screengbm" : "screen") : "native")
        << " leaf_combats=" << liveOptions.leafCombats << " leaf_policy=" << (liveOptions.uniformLeafPolicy ? "uniform" : "v4")
        << "]\n";
    std::cout << "[ooc-mcts-config] {\"noncombatOutcomes\":\""
        << (liveOptions.sampleNoncombat ? "sampled" : "exact")
        << "\",\"prior\":\"" << (liveOptions.uniformPrior ? "uniform" : "policy")
        << "\",\"temperature\":" << liveOptions.priorTemperature << ",\"cPuct\":" << liveConfig.cPuct
        << ",\"wideningK\":" << liveConfig.wideningK << ",\"wideningAlpha\":" << liveConfig.wideningAlpha
        << ",\"maxDepth\":" << liveConfig.maxDepth << ",\"rootSelection\":\"" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << "\",\"earlyStop\":" << (liveConfig.allowUnqualifiedRootStop ? "true" : "false")
        << ",\"gapStop20\":" << (liveConfig.stopAt512VisitGap20 ? "true" : "false")
        << ",\"mergeOutcomes\":" << (liveConfig.mergeEquivalentOutcomes ? "true" : "false")
        << ",\"leafValue\":\"" << (liveOptions.bossLeaf ? "boss" : liveOptions.constantLeaf ? "constant" : liveOptions.directLeaf ? "direct" : liveOptions.screenLeaf ? (liveOptions.screenLeafGbm ? "screengbm" : "screen") : "native")
        << "\",\"leafCombats\":" << liveOptions.leafCombats << ",\"leafPolicy\":\"" << (liveOptions.uniformLeafPolicy ? "uniform" : "v4")
        << "\",\"simulations\":" << liveSimulations
        << ",\"combatModel\":\"" << artifact << "\",\"brewFallbackModel\":"
        << (!brewFallbackArtifact.empty() ? std::string("\"")+brewFallbackArtifact+"\"" : "null")
        << ",\"dispatchRule\":\""
        << (!brewFallbackArtifact.empty() ? "precombat_entropic_brew_to_standard" : "single_artifact")
        << "\",\"activeLizardCorrection\":" << (activeLizardEnabled?"true":"false")
        << ",\"priorTrace\":\"" << liveOptions.priorTracePath << "\"}\n";
    std::cout.precision(precision);
}
sts::search::OocMctsResult selectOocMctsAction(const GameContext &gc, const PathHistory &path,
    std::uint64_t seed, std::uint64_t index, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler> sampler, std::uint64_t &samples,
    OocContinuationMetrics *continuation, std::optional<OocGameContextModel::Candidate> *selected) {
    ImaginedScope scope;
    auto config = liveConfig;
    config.seed = oocMctsSearchSeed(seed, index);
    auto options = liveOptions;
    if (!options.priorTracePath.empty()) {
        options.priorTraceRunSeed = seed;
        options.priorTraceDecisionIndex = index;
        options.priorTraceSearchSeed = config.seed;
    }
    OocGameContextModel model(gc, path, std::move(sampler), std::move(options));
    samples = 0;
    if (selected) selected->reset();
    if (model.terminalValue(0) || model.isLeafBoundary(0)) return {};
    const bool graphCapture = !liveGraphPath.empty() && index == liveGraphDecisionIndex;
    const bool reuseObserved = !liveReuseTrace.empty();
    config.captureTree = graphCapture || reuseObserved;
    if (reuseObserved) config.treeNodeCap = 100000;
    if (!simulations) throw std::invalid_argument("OOC MCTS requires simulations > 0");
    const auto sole = model.soleLegalAction(0);
    if (!runProfilePath().empty()) {
        config.profileSearch = true;
        // Preserve the singleton shortcut and every existing stopping rule.
        if (!sole) {
            for (const std::uint64_t checkpoint : {128, 256, 512, 1024, 2048, 4096})
                if (checkpoint <= simulations) config.rootCheckpointSimulations.push_back(checkpoint);
        }
    }
    nlohmann::json reuseRow;
    if (reuseObserved) {
        if (t_reuseIndex.seed != seed || t_reuseIndex.decision >= index) t_reuseIndex = {};
        const auto &prior = t_reuseIndex;
        reuseRow = {{"schemaVersion", 1}, {"seed", seed}, {"decisionIndex", index},
            {"floor", gc.floorNum}, {"act", gc.act}, {"screen", int(gc.screenState)}, {"singleton", sole.has_value()},
            {"previousSearch", prior.valid}};
        if (prior.valid) {
            reuseRow["previous"] = {{"decisionIndex", prior.decision}, {"decisionGap", index - prior.decision},
                {"floor", prior.floor}, {"screen", prior.screen}, {"simulations", prior.simulations},
                {"storedDecisionNodes", prior.storedDecisionNodes}, {"truncated", prior.truncated}};
            reuseRow["rng"] = reuseMatchJson(prior, prior.rng, reusePublicFingerprint(gc, path, true));
            reuseRow["public"] = reuseMatchJson(prior, prior.publicState, reusePublicFingerprint(gc, path, false));
        }
    }
    auto result = searchWithSoleRootShortcut(model, config, sole, simulations);
    if (reuseObserved) {
        reuseRow["searched"] = !result.metrics.trivialRootBypasses;
        reuseRow["aborted"] = result.aborted;
        reuseRow["simulations"] = result.metrics.simulations;
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveReuseTrace, std::ios::app);
        if (!out || !(out << reuseRow.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE write failed");
    }
    // A singleton bypass executes without a tree; retain the earlier index so
    // forced chains are measured against the last real search.
    if (reuseObserved && !result.metrics.trivialRootBypasses) {
        if (result.tree && result.selectedAction) {
            t_reuseIndex = buildReuseIndex(model, *result.tree);
            t_reuseIndex.valid = true;
            t_reuseIndex.selected = *result.selectedAction;
            t_reuseIndex.simulations = result.metrics.simulations;
            t_reuseIndex.floor = gc.floorNum;
            t_reuseIndex.screen = int(gc.screenState);
        } else t_reuseIndex = {};
        t_reuseIndex.seed = seed;
        t_reuseIndex.decision = index;
    }
    if (graphCapture) {
        if (result.tree) {
            annotateOocTree(model, *result.tree);
            for (auto &node : result.tree->nodes)
                node.selected = node.chance && node.depth == 0
                    && result.selectedAction && node.action == *result.selectedAction;
        }
        nlohmann::json captured = {{"accepted", result.tree.has_value()}, {"rootId", 0},
            {"truncated", result.tree && result.tree->truncated},
            {"nodes", nlohmann::json::array()}, {"edges", nlohmann::json::array()}};
        if (result.tree) {
            for (const auto &node : result.tree->nodes) {
                captured["nodes"].push_back({{"id", node.id}, {"kind", node.chance ? "chance" : "state"},
                    {"stateId", std::to_string(node.state)}, {"actionId", node.action},
                    {"label", node.label}, {"key", node.key}, {"outcome", node.outcome},
                    {"screen", node.screen}, {"room", node.room}, {"floor", node.floor},
                    {"mapX", node.mapX}, {"mapY", node.mapY}, {"hp", node.hp},
                    {"maxHp", node.maxHp}, {"gold", node.gold}, {"selected", node.selected}, {"depth", node.depth},
                    {"visits", node.visits}, {"prior", node.chance ? nlohmann::json(node.prior) : nlohmann::json(nullptr)},
                    {"q", node.chance && node.visits ? nlohmann::json(node.q) : nlohmann::json(nullptr)}});
            }
            for (const auto &edge : result.tree->edges)
                captured["edges"].push_back({{"parentId", edge.parentId},
                    {"childId", edge.childId ? nlohmann::json(*edge.childId) : nlohmann::json(nullptr)},
                    {"visits", edge.visits}, {"kind", edge.particle ? "particle" : "action"},
                    {"combatModelUsed", edge.combatModelUsed},
                    {"combatEncounter", edge.combatEncounter}, {"combatOutcome", edge.combatOutcome}});
        }
        nlohmann::json actions = nlohmann::json::array();
        for (const auto &action : result.rootActions)
            actions.push_back({{"semanticKey", model.candidate(0, action.id).key},
                {"visits", action.visits}, {"q", action.q}, {"prior", action.prior}});
        const nlohmann::json capture = {{"source", "native_sts_lightspeed_search"},
            {"seed", seed}, {"decisionIndex", index}, {"searchSeed", config.seed},
            {"floor", gc.floorNum}, {"screen", int(gc.screenState)},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp},
            {"requestedSimulations", simulations}, {"completedSimulations", result.metrics.simulations},
            {"aborted", result.aborted}, {"abortReason", result.abortReason},
            {"selectedSemanticKey", result.selectedAction ? model.candidate(0, *result.selectedAction).key : ""},
            {"candidateSummaries", actions}, {"tree", captured}};
        std::ofstream out(liveGraphPath, std::ios::trunc);
        if (!out || !(out << capture.dump(2) << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_GRAPH_FILE write failed");
    }
    if (!result.selectedAction && !result.aborted) throw std::runtime_error("live OOC MCTS missing selected root action");
    if (selected && result.selectedAction) *selected = model.candidate(0, *result.selectedAction);
    if (config.observeRootLock) {
        const auto &m = result.metrics;
        const bool completed = !result.aborted && m.simulations == simulations;
        if (completed && result.hypotheticalLockedAction
            && result.hypotheticalLockedAction != result.selectedAction)
            throw std::runtime_error("OOC hypothetical lock disagrees with full-budget winner");
        const nlohmann::json row = {
            {"seed",seed},{"decisionIndex",index},{"floor",gc.floorNum},{"screen",int(gc.screenState)},
            {"requestedSimulations",simulations},{"completedSimulations",m.simulations},
            {"simulationAttempts",m.simulationAttempts},{"fullBudgetCompleted",completed},
            {"aborted",result.aborted},{"abortReason",result.abortReason},
            {"hypotheticalLockSimulation",m.hypotheticalLockSimulation},
            {"hypotheticalRemainingSimulations",m.hypotheticalRemainingSimulations},
            {"hypotheticalTailWallSeconds",m.hypotheticalTailWallSeconds},
            {"hypotheticalLockedAction",result.hypotheticalLockedAction
                ? nlohmann::json(*result.hypotheticalLockedAction) : nlohmann::json(nullptr)},
            {"selectedKey",result.selectedAction ? model.candidate(0,*result.selectedAction).key : ""},
            {"selectedAction",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
            {"searchGuaranteedNonAborting",model.searchGuaranteedNonAborting()},
            {"earlyStopLockedRoot",m.earlyStopLockedRoot},{"savedSimulations",m.savedSimulations}};
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveRootLockTrace,std::ios::app);
        if (!out || !(out << row.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE write failed");
    }
    samples = model.combatSamples();
    if (continuation) {
        *continuation = model.continuationMetrics();
        recordSearchAbort(result,*continuation);
    }
    return result;
}
bool oocHypotheticalCardTaken(const GameContext &gc, const PathHistory &path, const sts::Card &card,
    const std::function<void(GameContext &)> &step) {
    ImaginedScope scope;
    auto offer = detachedCopy(gc);
    sts::CardReward reward;
    reward.push_back(card);
    offer.info.rewardsContainer = sts::Rewards();
    offer.info.rewardsContainer.addCardReward(reward);
    offer.screenState = sts::ScreenState::REWARDS;
    offer.regainControlAction = [](GameContext &g) {
        g.screenState = sts::ScreenState::MAP_SCREEN;
        g.regainControlAction = nullptr;
    };
    const auto before = offer.deck.size();
    PathHistory offerPath = path;
    t_curPath = &offerPath;
    step(offer);
    return offer.deck.size() > before;
}
bool oocMctsPolicyStep(GameContext &gc, const PathHistory &path, std::uint64_t seed,
    std::uint64_t index, LiveOocMctsMetrics &metrics) {
    ++metrics.decisions;
    if (!liveEnabled) return false;
    const auto wallStart = std::chrono::steady_clock::now();
    const double cpuStart = threadCpuSeconds();
    std::uint64_t samples = 0;
    OocContinuationMetrics continuation;
    OocProfileScope profile(OocProfileBucket::Mcts);
    if (sts::search::g_onGameActionExecute && gc.screenState != sts::ScreenState::MAP_SCREEN) {
        ++metrics.fallback; ++metrics.continuation.supportReasons["semantic_observer_active"]; return false;
    }
    collectForcedRewardGold(gc);
    std::optional<OocGameContextModel::Candidate> selected;
    const auto result = selectOocMctsAction(gc, path, seed, index, liveSimulations, liveSampler, samples, &continuation, &selected);
    profile.stop();
    const double wallElapsed = std::chrono::duration<double>(std::chrono::steady_clock::now()-wallStart).count();
    const double cpuElapsed = threadCpuSeconds()-cpuStart;
    metrics.wallSeconds += wallElapsed;
    metrics.cpuSeconds += cpuElapsed;
    nlohmann::json decisionProfile;
    if (!runProfilePath().empty()) {
        using nlohmann::json;
        const auto actionsJson = [](const std::vector<sts::search::OocRootActionStats> &actions) {
            auto output = json::array();
            for (const auto &a : actions)
                output.push_back({{"id", a.id}, {"prior", a.prior}, {"visits", a.visits}, {"q", a.q}});
            return output;
        };
        auto checkpoints = json::array();
        for (const auto &c : result.rootCheckpoints)
            checkpoints.push_back({{"simulations", c.simulations}, {"actions", actionsJson(c.actions)}});
        const auto &m = result.metrics;
        decisionProfile = {{"schema", 1}, {"kind", "ooc_decision"}, {"seed", std::to_string(seed)},
            {"decision", index}, {"act", gc.act}, {"floor", gc.floorNum},
            {"screen", int(gc.screenState)}, {"room", sts::roomStrings[int(gc.curRoom)]},
            {"wall_seconds", wallElapsed}, {"thread_cpu_seconds", cpuElapsed},
            {"configured_simulations", liveSimulations}, {"completed_simulations", m.simulations},
            {"attempts", m.simulationAttempts}, {"singleton_bypass", m.trivialRootBypasses},
            {"aborted", result.aborted}, {"abort_reason", result.abortReason},
            {"selected_action", result.selectedAction ? json(*result.selectedAction) : json(nullptr)},
            {"selected_key", selected ? selected->key : ""},
            {"selection_rule", liveConfig.selectByMeanQ ? "q_visits_id" : "visits_q_id"},
            {"actions", actionsJson(result.rootActions)}, {"checkpoints", checkpoints},
            {"expanded_action_histogram", runProfileHistogram(m.expandedActionHistogram)},
            {"expanded_nodes", m.expandedNodes0Actions + m.expandedNodes1Action
                + m.expandedNodes2Actions + m.expandedNodes3PlusActions},
            {"outcome_particles", m.outcomeParticles}, {"transition_samples", m.transitionSamples},
            {"ctm_samples", samples}, {"leaf_evaluations", m.leafEvaluations},
            {"max_depth", m.maxDepthReached}, {"depth_sum", m.depthSum},
            {"early_stop_lock", m.earlyStopLockedRoot}, {"early_stop_gap", m.earlyStopVisitGap20}};
    }
    if (!liveCheckpointTrace.empty()) {
        ImaginedScope scope;
        auto shadowOptions = liveOptions;
        shadowOptions.priorTracePath.clear();
        OocGameContextModel shadow(gc, path, liveSampler, std::move(shadowOptions));
        if (!shadow.terminalValue(0) && !shadow.isLeafBoundary(0)) {
            auto config=liveConfig;
            config.seed=oocMctsSearchSeed(seed,index);
            config.observeRootLock=true;
            config.stopAt512VisitGap20=false;
            config.rootCheckpointSimulations={128,256,512,1024,2048};
            const auto observed=sts::search::OocMctsPlanner(config).search(shadow,0,liveSimulations);
            nlohmann::json checkpoints=nlohmann::json::array();
            for (const auto &checkpoint : observed.rootCheckpoints) {
                nlohmann::json actions=nlohmann::json::array();
                for (const auto &action : checkpoint.actions)
                    actions.push_back({{"id",action.id},{"key",shadow.candidate(0,action.id).key},{"prior",action.prior},
                        {"visits",action.visits},{"q",action.q}});
                checkpoints.push_back({{"simulations",checkpoint.simulations},{"actions",actions}});
            }
            const nlohmann::json row={
                {"schemaVersion",1},{"seed",seed},{"decisionIndex",index},
                {"floor",gc.floorNum},{"screen",int(gc.screenState)},
                {"requestedSimulations",liveSimulations},
                {"liveSimulations",result.metrics.simulations},
                {"liveAborted",result.aborted},{"liveAbortReason",result.abortReason},
                {"liveKey",selected ? selected->key : ""},
                {"liveAction",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
                {"liveGapStop20",result.metrics.earlyStopVisitGap20},
                {"liveSavedSimulations",result.metrics.savedSimulations},
                {"shadowSimulations",observed.metrics.simulations},
                {"shadowAttempts",observed.metrics.simulationAttempts},
                {"shadowAborted",observed.aborted},{"shadowAbortReason",observed.abortReason},
                {"finalAction",observed.selectedAction ? nlohmann::json(*observed.selectedAction) : nlohmann::json(nullptr)},
                {"checkpoints",checkpoints}};
            std::lock_guard<std::mutex> lock(liveTraceMutex);
            std::ofstream out(liveCheckpointTrace,std::ios::app);
            if (!out || !(out << row.dump() << '\n'))
                throw std::runtime_error("STS_OOC_MCTS_CHECKPOINT_TRACE write failed");
        }
    }
    metrics.combatSamples += samples;
    auto &c=metrics.continuation;
    c.imaginedCombats+=continuation.imaginedCombats; c.unsupportedCombats+=continuation.unsupportedCombats;
    c.pendingLeaves+=continuation.pendingLeaves; c.battleLeaves+=continuation.battleLeaves;
    c.mapLeaves+=continuation.mapLeaves; c.projectionSteps+=continuation.projectionSteps;
    c.continuationLimitAborts+=continuation.continuationLimitAborts;
    c.metadataBuilds+=continuation.metadataBuilds; c.priorBuilds+=continuation.priorBuilds;
    c.preparedCombats+=continuation.preparedCombats; c.combatEdgeSamples+=continuation.combatEdgeSamples;
    c.singletonPolicyLogitCalls+=continuation.singletonPolicyLogitCalls;
    c.singletonPolicyInferenceCalls+=continuation.singletonPolicyInferenceCalls;
    c.screenLeafEvaluations+=continuation.screenLeafEvaluations; c.screenLeafFallbacks+=continuation.screenLeafFallbacks;
    for (auto &[reason,count] : continuation.continuationReasons) c.continuationReasons[reason]+=count;
    for (auto &[reason,count] : continuation.supportReasons) c.supportReasons[reason]+=count;
    auto &m = metrics.search;
    m.outcomeParticles+=result.metrics.outcomeParticles; m.decisionNodes+=result.metrics.decisionNodes;
    m.chanceNodes+=result.metrics.chanceNodes; m.particleRevisits+=result.metrics.particleRevisits;
    for (const auto &[actions, count] : result.metrics.expandedActionHistogram)
        m.expandedActionHistogram[actions] += count;
    m.expandedNodes0Actions+=result.metrics.expandedNodes0Actions;
    m.expandedNodes1Action+=result.metrics.expandedNodes1Action;
    m.expandedNodes2Actions+=result.metrics.expandedNodes2Actions;
    m.expandedNodes3PlusActions+=result.metrics.expandedNodes3PlusActions;
    m.deterministicRevisits+=result.metrics.deterministicRevisits; m.depthSum+=result.metrics.depthSum;
    m.trivialRootBypasses += result.metrics.trivialRootBypasses;
    m.earlyStopLockedRoot += result.metrics.earlyStopLockedRoot;
    m.earlyStopVisitGap20 += result.metrics.earlyStopVisitGap20;
    m.savedSimulations += result.metrics.savedSimulations;
    m.simulations += result.metrics.simulations;
    m.simulationAttempts += result.metrics.simulationAttempts;
    m.transitionSamples += result.metrics.transitionSamples;
    m.leafEvaluations += result.metrics.leafEvaluations;
    m.maxDepthReached = std::max(m.maxDepthReached, result.metrics.maxDepthReached);
    if (result.aborted) {
        ++metrics.supportAborts; metrics.discardedSimulations+=result.metrics.simulations;
    }
    const auto rootScreen = gc.screenState;
    const auto rootSelector = gc.info.selectScreenType;
    const auto traceDecision = [&](bool executed, const std::string &reason) {
        if (!decisionProfile.is_null()) {
            decisionProfile["executed"] = executed;
            decisionProfile["execution_reason"] = reason;
            writeRunProfile(decisionProfile);
        }
        if (liveTrace.empty()) return;
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveTrace + ".actions.jsonl", std::ios::app);
        out << nlohmann::json{{"seed",seed},{"decisionIndex",index},
            {"screen",int(rootScreen)},{"selector",int(rootSelector)},
            {"selectedId",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
            {"selectedKey",selected ? selected->key : ""},
            {"semantic",selected && selected->semantic.has_value()},
            {"compound",selected && selected->compoundSelector != sts::CardSelectScreenType::INVALID},
            {"executed",executed},{"reason",reason}}.dump() << '\n';
        if (!out) throw std::runtime_error("OOC MCTS action trace write failed");
    };
    if (!result.selectedAction) {
        ++metrics.fallback;
        traceDecision(false, result.aborted ? result.abortReason : "root_boundary");
        return false;
    }
    std::string error;
    if (!selected || !executeOocMctsRoot(gc, *selected, error)) {
        ++metrics.fallback;
        ++metrics.continuation.supportReasons[error.empty() ? "missing_root_identity" : error];
        traceDecision(false,error);
        return false;
    }
    ++metrics.owned;
    traceDecision(true, "");
    return true;
}
bool executeOocMctsRoot(GameContext &gc, const OocGameContextModel::Candidate &selected, std::string &error) {
    if (selected.semantic) {
        const auto fresh = sts::search::enumerateOocSemanticActions(gc);
        if (!fresh.supported || !fresh.complete) { error = "semantic_root_incomplete"; return false; }
        const sts::search::OocSemanticAction *match = nullptr;
        for (const auto &action : fresh.actions) {
            if (sts::search::canonicalOocSemanticActionKey(action) != selected.key) continue;
            if (match) { error = "semantic_root_ambiguous"; return false; }
            match = &action;
        }
        if (!match) { error = "semantic_root_stale"; return false; }
        const auto execution = sts::search::executeOocSemanticAction(gc, *match);
        if (!execution.ok) { error = "semantic_live_execution:" + execution.error; return false; }
        return true;
    }
    if (gc.screenState != sts::ScreenState::MAP_SCREEN) { error = "map_root_stale"; return false; }
    const auto candidates = v4CandidateActions(gc);
    const auto action = std::find_if(candidates.begin(), candidates.end(),
        [&](auto a) { return a.bits == selected.primitive.bits; });
    if (action == candidates.end()) { error = "map_root_stale"; return false; }
    action->execute(gc);
    return true;
}

void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &m, int realCombats) {
    EntropicBrewFallbackCombatTransitionSampler::Metrics brewMetrics;
    const auto hybridSampler=std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSampler);
    if (hybridSampler) brewMetrics=hybridSampler->takeMetrics();
    if (oocProfileEnabled()) {
        static const char *names[] = {"mcts", "real_combat", "metadata", "policy_logits",
            "policy_prepare", "policy_predict", "successor", "combat_prepare", "combat_resolve",
            "evaluate_leaf", "leaf_value", "leaf_features", "leaf_predict", "v4_state_network", "v4_encode_deck",
            "v4_encode_rel", "v4_encode_pot", "v4_state_fusion", "v4_action_value",
            "prior_build", "singleton_prior"};
        nlohmann::json counters = nlohmann::json::object();
        for (std::size_t index = 0; index < oocProfileCounters.size(); ++index) {
            const auto &counter = oocProfileCounters[index];
            counters[names[index]] = {{"calls", counter.calls}, {"inclusiveCpuSec", counter.inclusive},
                {"exclusiveCpuSec", counter.exclusive}};
        }
        nlohmann::json hybrid={{"preparations",brewMetrics.preparations},
            {"fastPreparations",brewMetrics.fastPreparations},
            {"standardBrewFallbackPreparations",brewMetrics.fallbackPreparations},
            {"fastSamples",brewMetrics.fastSamples},{"fallbackSamples",brewMetrics.fallbackSamples},
            {"fallbackRate",brewMetrics.fallbackRate},
            {"uniqueBrewPredictorStates",brewMetrics.uniqueBrewPredictorStates},
            {"fastSupportFailures",brewMetrics.fastSupportFailures},
            {"fallbackSupportFailures",brewMetrics.fallbackSupportFailures},
            {"activeLizardEnabled",hybridSampler && hybridSampler->activeLizardEnabled()},
            {"lizardPreparations",brewMetrics.lizardPreparations},
            {"lizardSamples",brewMetrics.lizardSamples},
            {"lizardOrdinaryWins",brewMetrics.lizardOrdinaryWins},
            {"lizardConsumedWins",brewMetrics.lizardConsumedWins},
            {"lizardConsumedLosses",brewMetrics.lizardConsumedLosses},
            {"lizardBoundaryExclusions",brewMetrics.lizardBoundaryExclusions},
            {"lizardSupportFailures",brewMetrics.lizardSupportFailures}};
        std::cerr << "[ooc-cpu-profile] " << nlohmann::json{{"seed",seed},
            {"processCpuAtReportSec",oocProfileCpu(CLOCK_PROCESS_CPUTIME_ID)},
            {"mctsCpuSec",m.cpuSeconds},{"realCombats",realCombats},{"counters",counters},
            {"expandedNodesByActionCount",{
                {"0",m.search.expandedNodes0Actions},{"1",m.search.expandedNodes1Action},
                {"2",m.search.expandedNodes2Actions},{"3+",m.search.expandedNodes3PlusActions}}},
            {"singletonPolicyLogitCalls",m.continuation.singletonPolicyLogitCalls},
            {"singletonPolicyInferenceCalls",m.continuation.singletonPolicyInferenceCalls},
            {"combatTransitionHybrid",hybrid}}.dump() << '\n';
        oocProfileCounters = {};
    }
    if(hybridSampler)
        std::cerr << "[ooc-combat-transition] " << nlohmann::json{{"seed",seed},
            {"activeLizardEnabled",hybridSampler->activeLizardEnabled()},
            {"lizardPreparations",brewMetrics.lizardPreparations},
            {"lizardSamples",brewMetrics.lizardSamples},
            {"lizardOrdinaryWins",brewMetrics.lizardOrdinaryWins},
            {"lizardConsumedWins",brewMetrics.lizardConsumedWins},
            {"lizardConsumedLosses",brewMetrics.lizardConsumedLosses},
            {"lizardBoundaryExclusions",brewMetrics.lizardBoundaryExclusions},
            {"lizardSupportFailures",brewMetrics.lizardSupportFailures},
            {"fastSupportFailures",brewMetrics.fastSupportFailures},
            {"fallbackSupportFailures",brewMetrics.fallbackSupportFailures},
            {"standardBrewFallbackPreparations",brewMetrics.fallbackPreparations}}.dump() << '\n';
    if (liveTrace.empty()) return;
    std::lock_guard<std::mutex> lock(liveTraceMutex);
    const std::string header = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,transitionSamples,combatSurrogateSamples,leafEvaluations,maxDepth,mctsWallSec,mctsCpuSec,realCombats,imaginedCombats,unsupportedCombats,mctsSupportAborts,discardedSimulations,simulationAttempts,pendingLeaves,battleLeaves,mapLeaves,projectionSteps,outcomeParticles,particleRevisits,deterministicRevisits,depthSum,continuationLimitAborts,trivialRootBypasses,earlyStopLockedRoot,earlyStopVisitGap20,savedSimulations,metadataBuilds,priorBuilds,preparedCombats,combatEdgeSamples,hybridPreparations,hybridFastPreparations,hybridFallbackPreparations,hybridFastSamples,hybridFallbackSamples,hybridFallbackRate,hybridUniqueBrewStates,hybridFastSupportFailures,hybridFallbackSupportFailures\n";
    std::ifstream existing(liveTrace);
    std::string firstLine;
    if (std::getline(existing,firstLine) && firstLine+'\n' != header)
        throw std::runtime_error("STS_OOC_MCTS_TRACE incompatible header; use a fresh trace path");
    std::ofstream out(liveTrace, std::ios::app);
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot write output");
    if (out.tellp() == 0) out << header;
    out << std::setprecision(12) << seed << ',' << m.decisions << ',' << m.owned << ',' << m.fallback
        << ',' << m.search.simulations << ',' << m.search.transitionSamples << ',' << m.combatSamples
        << ',' << m.search.leafEvaluations << ',' << m.search.maxDepthReached
        << ',' << m.wallSeconds << ',' << m.cpuSeconds << ',' << realCombats
        << ',' << m.continuation.imaginedCombats << ',' << m.continuation.unsupportedCombats
        << ',' << m.supportAborts << ',' << m.discardedSimulations << ',' << m.search.simulationAttempts
        << ',' << m.continuation.pendingLeaves << ',' << m.continuation.battleLeaves
        << ',' << m.continuation.mapLeaves << ',' << m.continuation.projectionSteps
        << ',' << m.search.outcomeParticles << ',' << m.search.particleRevisits
        << ',' << m.search.deterministicRevisits << ',' << m.search.depthSum
        << ',' << m.continuation.continuationLimitAborts
        << ',' << m.search.trivialRootBypasses << ',' << m.search.earlyStopLockedRoot
        << ',' << m.search.earlyStopVisitGap20
        << ',' << m.search.savedSimulations << ',' << m.continuation.metadataBuilds
        << ',' << m.continuation.priorBuilds << ',' << m.continuation.preparedCombats
        << ',' << m.continuation.combatEdgeSamples << ',' << brewMetrics.preparations
        << ',' << brewMetrics.fastPreparations << ',' << brewMetrics.fallbackPreparations
        << ',' << brewMetrics.fastSamples << ',' << brewMetrics.fallbackSamples
        << ',' << brewMetrics.fallbackRate << ',' << brewMetrics.uniqueBrewPredictorStates
        << ',' << brewMetrics.fastSupportFailures << ',' << brewMetrics.fallbackSupportFailures << '\n';
    std::ofstream reasons(liveTrace+".support.jsonl",std::ios::app);
    reasons << nlohmann::json{{"seed",seed},{"reasons",m.continuation.supportReasons},
        {"continuation_reasons",m.continuation.continuationReasons},
        {"continuation_limit_aborts",m.continuation.continuationLimitAborts},
        {"screen_leaf_evaluations",m.continuation.screenLeafEvaluations},
        {"screen_leaf_fallbacks",m.continuation.screenLeafFallbacks}}.dump() << '\n';
    reasons.flush();
    if (!reasons) throw std::runtime_error("OOC MCTS support trace write failed");
    out.flush();
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE write failed");
}

}

#include "../../tests/data/ooc_v4_policy_fixture.h"
namespace one_combat {
void oocMctsAdapterSelfTest() {
    runFloorProfileSelfTest();
    using namespace sts;
    using namespace sts::search;
    {
        GameContext counters(CharacterClass::IRONCLAD, 1234, 0);
        counters.act = 2;
        counters.floorNum = 23;
        for (int seed = 0; seed < 128; ++seed) {
            std::mt19937_64 rng(seed);
            sampleLiveOocHiddenCounters(counters, rng, 0);
            require(counters.monsterChance == 0.1f && counters.shopChance == 0.03f
                    && counters.treasureChance == 0.02f,
                    "zero current-act event rooms must reset room-chance counters");
            sampleLiveOocHiddenCounters(counters, rng, 1);
            const bool monster = counters.monsterChance == 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            const bool shop = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            const bool treasure = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f;
            const bool event = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            require(monster || shop || treasure || event,
                    "one event-room outcome must produce a reachable joint chance state");
        }
    }
    // Inspect the actual configured option before fixture-specific resets.
    require(!liveEnabled || liveOptions.sampleNoncombat,
        "enabled live OOC MCTS must sample noncombat outcomes after all startup resets");
    std::cout << std::setprecision(12);
    require(g_oocStrategicTokNet.path == "selfplay/models/ooc_strategic_tok_final.native"
        || g_oocStrategicTokNet.path.find("/selfplay/models/ooc_strategic_tok_final.native") != std::string::npos,
        "policy parity requires tracked final V4 artifact");
    {
        // The simulator's actual ordered driver and the advisor's shared
        // native fallback must reach identical checkpoints from the same
        // public state. Disable the optional V4 gate for this fallback seam;
        // its Q/margin gate has separate parity fixtures below.
        CompactTreeNet floor, win;
        require(floor.load("models/v_rich_trees.txt", richIdxMap(), "ParityFloor")
                && win.load("models/v_win_trees.txt", richIdxMap(), "ParityWin"),
            "checkpoint parity model artifacts unavailable");
        const bool savedV4 = g_oocStrategicTokNet.ok;
        const auto *savedPath = t_curPath;
        g_oocStrategicTokNet.ok = false;
        PathHistory parityPath;
        t_curPath = &parityPath;
        auto compare = [&](GameContext original, const std::function<void(GameContext &)> &advisorStep,
                           const char *reason) {
            original.regainControlAction = [](GameContext &state) {
                state.screenState = ScreenState::MAP_SCREEN;
                state.regainControlAction = nullptr;
            };
            auto oracle = detachedCopy(original), advisor = detachedCopy(original);
            ScumSearchAgent2 agent;
            agent.rng.seed(0);
            runFullRunOocPolicyStep(oracle, agent, false, true);
            advisorStep(advisor);
            require(test::oocStateFingerprint(oracle) == test::oocStateFingerprint(advisor), reason);
        };
        GameContext parity(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::REWARDS;
        parity.curRoom = Room::MONSTER;
        parity.info.rewardsContainer.clear();
        CardReward cards;
        cards.push_back(Card(CardId::ANGER)); cards.push_back(Card(CardId::BASH));
        parity.info.rewardsContainer.addCardReward(cards);
        compare(parity, [&](GameContext &state) {
            const int pick = nativeFloorCardPick(state, parityPath, floor, 0, -0.5);
            GameAction(GameAction::RewardsActionType::CARD, 0, pick).execute(state);
        }, "card-reward simulator/advisor checkpoint mismatch");
        parity.screenState = ScreenState::REST_ROOM;
        parity.curRoom = Room::REST;
        parity.curHp = 30;
        compare(parity, [&](GameContext &state) {
            if (!nativeWinRestStep(state, parityPath, win, false)) {
                ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
            }
        }, "rest simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
        compare(parity, [&](GameContext &state) {
            nativeWinUpgradeSelectStep(state, parityPath, win);
        }, "upgrade-selector simulator/advisor checkpoint mismatch");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::SHOP_ROOM;
        parity.curRoom = Room::SHOP;
        parity.gold = 100;
        for (int i = 0; i < 7; ++i) parity.info.shop.cardPrice(i) = -1;
        for (int i = 0; i < 3; ++i) {
            parity.info.shop.relicPrice(i) = -1;
            parity.info.shop.potionPrice(i) = -1;
        }
        parity.info.shop.cards[0] = Card(CardId::ANGER);
        parity.info.shop.cardPrice(0) = 50;
        parity.info.shop.removeCost = -1;
        compare(parity, [&](GameContext &state) {
            nativeFloorShopStep(state, parityPath, floor);
        }, "shop simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        compare(parity, [&](GameContext &state) {
            std::vector<int> ids;
            for (int i = 0; i < state.info.toSelectCards.size(); ++i)
                ids.push_back(static_cast<int>(state.info.toSelectCards[i].card.getId()));
            GameAction(nativeFloorRemovePick(state, parityPath, floor, ids), 0).execute(state);
        }, "shop remove-selector simulator/advisor checkpoint mismatch");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::EVENT_SCREEN;
        parity.curRoom = Room::EVENT;
        parity.curEvent = Event::THE_WOMAN_IN_BLUE;
        parity.gold = 100;
        compare(parity, [&](GameContext &state) {
            ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
        }, "event simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::TRANSFORM, 1);
        compare(parity, [&](GameContext &state) {
            ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
        }, "transform-selector simulator/advisor checkpoint mismatch");
        g_oocStrategicTokNet.ok = savedV4;
        require(savedV4, "V4 checkpoint parity requires loaded token model");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::REWARDS;
        parity.curRoom = Room::MONSTER;
        parity.info.rewardsContainer.clear();
        parity.info.rewardsContainer.addCardReward(cards);
        compare(parity, [&](GameContext &state) {
            const double margin = g_oocStrategicMarginCard >= 0.0
                ? g_oocStrategicMarginCard : g_oocStrategicMargin;
            if (!takeQualifiedV4CardReward(state, parityPath, g_oocStrategicTokNet, margin)) {
                const int pick = nativeFloorCardPick(state, parityPath, floor, 0, -0.5);
                GameAction(GameAction::RewardsActionType::CARD, 0, pick).execute(state);
            }
        }, "V4 card-reward simulator/advisor checkpoint mismatch");
        t_curPath = savedPath;
    }
    float glob[42]; for (int i=0;i<42;++i) glob[i]=(i-20)*.125f;
    const int dk[96][3] = {{1,0,5},{42,1,2},{100,0,1}};
    const int rl[64][2] = {{1,1},{23,4}};
    const int pt[8][2] = {{2,1},{7,2}};
    const auto fixturePrepared = g_oocStrategicTokNet.prepareState(glob,3,dk,2,rl,2,pt);
    const auto fixturePolicyPrefix = g_oocStrategicTokNet.preparePolicyPrefix(fixturePrepared);
    for (auto f : v4PolicyFixtures) {
        const float et[4] = {float(f.entityType==0),float(f.entityType==1),float(f.entityType==2),float(f.entityType==3)};
        double logit = g_oocStrategicTokNet.predictPolicyLogit(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        double q = g_oocStrategicTokNet.predictActionValue(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        require(logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price)
            && logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,fixturePolicyPrefix,
                    f.bits,f.cats,f.type,f.screen,et,f.entityId,f.price)
            && q == g_oocStrategicTokNet.predictActionValue(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price),
            "prepared V4 policy/Q and shared-prefix policy exactly match legacy entry points");
        require(std::abs(logit-f.logit)<1e-4, "V4 policy parity");
        require(std::abs(q-f.q)<2e-4, "V4 Q regression parity");
        std::cout << "parity bits="<<f.bits<<" logit="<<logit<<" expected="<<f.logit
                  <<" error="<<std::abs(logit-f.logit)<<" q_error="<<std::abs(q-f.q)<<'\n';
    }
    const auto cold = oocPolicyWeights({0, 2}, .5), hot = oocPolicyWeights({0, 2}, 2);
    require(cold[0] < hot[0] && cold[1] == 1 && hot[1] == 1, "temperature changes policy concentration");
    auto extreme = oocPolicyWeights({-10000,0,10000});
    require(extreme == std::vector<double>({0,0,1}), "stable extreme softmax");
    auto rejects = [](auto fn) { bool rejected=false; try { fn(); } catch(const std::exception &) { rejected=true; }
        require(rejected,"invalid adapter input accepted"); };
    rejects([] { oocPolicyWeights({0},0); });
    rejects([] { oocPolicyWeights({NAN}); });
    rejects([] { oocPolicyWeights({0},INFINITY); });
    rejects([] { oocPolicyWeights({0},NAN); });
    // One-unit internal bound exposes the final-transition edge without a live
    // configuration knob or hundreds of artificial native decisions.
    for (double finalValue : {0.0,0.5,1.0}) {
        int transitions=0, checkpointChecks=0;
        const auto value=boundedContinuation(1,[&]() -> std::optional<double> {
            ++checkpointChecks;
            return transitions ? std::optional<double>(finalValue) : std::nullopt;
        },[&] { ++transitions; });
        require(value==finalValue && transitions==1 && checkpointChecks==2,
            "last permitted transition accepts exact terminal or resolved checkpoint value");
    }
    {
        int transitions=0;
        bool aborted=false;
        try { boundedContinuation(1,[] { return std::optional<double>{}; },[&] { ++transitions; }); }
        catch (const OocSearchUnsupported &error) { aborted=std::string(error.what())=="continuation_step_limit_1"; }
        require(aborted && transitions==1,"unresolved continuation still aborts exactly at step limit");
    }
    GameContext gc(CharacterClass::IRONCLAD,42,0);
    gc.screenState=ScreenState::MAP_SCREEN;
    gc.curEvent=Event::INVALID;
    gc.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    require(gc.map != nullptr, "real map fixture");
    PathHistory path; path.update(gc);
    OocGameContextModel model(gc,path);
    auto sourceId = [](const OocGameContextModel &provider, std::uint32_t bits) {
        for (const auto &action : provider.legalActions(0))
            if (provider.candidate(0,action.id).primitive.bits==bits) return action.id;
        throw std::runtime_error("required source primitive absent from adapter candidates");
    };
    // Prior visit counts are external to GameContext and must survive root construction.
    PathHistory nonemptyHistory;
    nonemptyHistory.roomVisits[int(Room::SHOP)]=2;
    nonemptyHistory.roomVisits[int(Room::REST)]=1;
    nonemptyHistory.roomVisits[int(Room::EVENT)]=3;
    nonemptyHistory.roomVisits[int(Room::ELITE)]=4;
    nonemptyHistory.roomVisits[int(Room::MONSTER)]=5;
    nonemptyHistory.roomVisits[int(Room::TREASURE)]=6;
    OocGameContextModel historyModel(gc,nonemptyHistory);
    const auto historyLogits=historyModel.policyLogits(0);
    const auto cachedHistoryActions=historyModel.legalActions(0);
    for (int repeat=0;repeat<3;++repeat) {
        require(historyModel.policyLogits(0)==historyLogits,"cached logits remain bit-exact");
        const auto again=historyModel.legalActions(0);
        require(again.size()==cachedHistoryActions.size(),"cached legal action count");
        for (std::size_t i=0;i<again.size();++i)
            require(again[i].id==cachedHistoryActions[i].id && again[i].prior==cachedHistoryActions[i].prior,
                "cached legal IDs/order/raw priors exact");
    }
    require(historyModel.continuationMetrics().metadataBuilds==1
        && historyModel.continuationMetrics().priorBuilds==1
        && !historyModel.searchGuaranteedNonAborting(),
        "immutable metadata/token/prior build once; live model remains abort-capable");
    const auto historyActions=v4CandidateActions(gc);
    const TokState historyTokens=buildTokState(gc,nonemptyHistory);
    double maxHistoryPolicyError=0;
    for(std::size_t i=0;i<historyActions.size();++i) {
        const auto a=historyActions[i];
        int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
        strategicCands(gc,a,type,c1,c2,c3,d1,d2,d3);
        tokEntity(gc,a,et,ei,price);
        const int cats[6]={c1,c2,c3,d1,d2,d3};
        const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
        const double direct=g_oocStrategicTokNet.predictPolicyLogit(historyTokens.glob,
            historyTokens.nDk,historyTokens.dk,historyTokens.nRl,historyTokens.rl,
            historyTokens.nPt,historyTokens.pt,a.bits,cats,type,int(gc.screenState),entity,ei,price);
        maxHistoryPolicyError=std::max(maxHistoryPolicyError,std::abs(direct-historyLogits[i]));
        require(std::abs(direct-historyLogits[i])<1e-12,"nonempty history V4 policy parity");
    }
    const auto previousHistory=t_curPath;
    t_curPath=&nonemptyHistory;
    const double directHistoryLeaf=vStateWinNative(gc);
    const double adapterHistoryLeaf=historyModel.leafValue(0);
    require(t_curPath==&nonemptyHistory,"leaf restores caller history");
    t_curPath=previousHistory;
    require(std::abs(directHistoryLeaf-adapterHistoryLeaf)<1e-12,"nonempty history native win parity");
    // The fixture must expose lost-history bugs, not merely exercise nonzero inputs.
    const auto emptyHistoryLogits=model.policyLogits(0);
    bool policyChanged=false;
    for(std::size_t i=0;i<historyLogits.size();++i)
        policyChanged=policyChanged || std::abs(historyLogits[i]-emptyHistoryLogits[i])>1e-6;
    require(policyChanged && std::abs(adapterHistoryLeaf-model.leafValue(0))>1e-6,
            "nonempty history fixture must affect both models");
    std::cout<<"nonempty_history_parity actions="<<historyActions.size()
        <<" policy_max_error="<<maxHistoryPolicyError
        <<" leaf_error="<<std::abs(directHistoryLeaf-adapterHistoryLeaf)
        <<" leaf_value="<<adapterHistoryLeaf<<'\n';
    auto candidates=v4CandidateActions(gc);
    auto legal=model.legalActions(0);
    auto logits=model.policyLogits(0);
    require(!legal.empty() && legal.size()==candidates.size(),"candidate parity");
    std::set<std::uint32_t> ids;
    for (std::size_t i=0;i<legal.size();++i) {
        require(legal[i].id==candidates[i].bits && ids.insert(legal[i].id).second,"primitive action identity");
    }
    std::mt19937_64 rng(42);
    rejects([&] { model.sampleSuccessor(0,0xFFFFFFFFu,rng); });
    GameContext expected=detachedCopy(gc);
    candidates.front().execute(expected);
    auto child=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(child).screenState==expected.screenState
        && model.state(child).curMapNodeX==expected.curMapNodeX
        && model.state(child).floorNum==expected.floorNum
        && model.state(child).curHp==expected.curHp,"native copied successor");
    require(model.state(0).curMapNodeX==gc.curMapNodeX && model.state(0).floorNum==gc.floorNum
        && model.state(0).screenState==gc.screenState,"parent unchanged");
    require(model.state(child).map.get()!=model.state(0).map.get()
        && model.state(0).map.get()!=gc.map.get(),"map detached at root and successor");
    auto repeated=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(repeated).curMapNodeX==model.state(child).curMapNodeX
        && model.state(repeated).info.encounter==model.state(child).info.encounter,"concrete RNG replay");
    // Mutate caller's map: materialized root must retain its own content.
    auto room=model.state(0).map->nodes[0][0].room;
    gc.map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room,"external map independence");
    gc.map->nodes[0][0].room=room;
    model.state(child).map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room
        && gc.map->nodes[0][0].room==room,"child map mutation cannot affect ancestors");
    model.state(child).map->nodes[0][0].room=room;
    // Compare the adapter against the complete semantic surface, independently
    // execute each semantic edge, and audit the source-level prior bridge.
    bool directTraceChecked = false, compoundTraceChecked = false;
    std::uint64_t traceFileSuffix = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto newTraceFile = [&]() {
        return "/tmp/ooc_mcts_prior_selftest_" + std::to_string(traceFileSuffix++) + ".jsonl";
    };
    auto checkCandidates = [&](GameContext fixture, bool execute=true) {
        auto canonical = detachedCopy(fixture);
        collectForcedRewardGold(canonical);
        const auto before=test::oocStateFingerprint(canonical);
        const auto bindings=enumerateOocSemanticPrimitiveBindings(canonical);
        std::vector<sts::search::OocSemanticPrimitiveBinding> representatives;
        std::set<std::string> choiceKeys;
        for (const auto &binding : bindings.bindings)
            if (choiceKeys.insert(canonicalOocMctsChoiceKey(binding.semantic, &canonical)).second)
                representatives.push_back(binding);
        const bool map=canonical.screenState==ScreenState::MAP_SCREEN;
        const auto primitive=v4CandidateActions(canonical);
        const TokState tokens=buildTokState(canonical,path);
        const auto prepared=g_oocStrategicTokNet.prepareState(tokens.glob,tokens.nDk,tokens.dk,
            tokens.nRl,tokens.rl,tokens.nPt,tokens.pt);
        const auto policyPrefix=g_oocStrategicTokNet.preparePolicyPrefix(prepared);
        std::map<std::uint32_t,double> sourceLogits;
        for(const auto action:primitive) {
            int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
            strategicCands(canonical,action,type,c1,c2,c3,d1,d2,d3);
            tokEntity(canonical,action,et,ei,price);
            const int cats[6]={c1,c2,c3,d1,d2,d3};
            const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
            const auto reference=g_oocStrategicTokNet.predictPolicyLogit(prepared,action.bits,cats,
                type,int(canonical.screenState),entity,ei,price);
            const auto optimized=g_oocStrategicTokNet.predictPolicyLogit(prepared,policyPrefix,
                action.bits,cats,type,int(canonical.screenState),entity,ei,price);
            require(reference==optimized,"shared-prefix V4 logits are bit-identical for every source primitive");
            sourceLogits.emplace(action.bits,reference);
        }
        require(map || (bindings.supported && bindings.complete && !bindings.bindings.empty()),
            "semantic coverage fixture must be complete");
        OocGameContextModel provider(canonical,path);
        const auto actual=provider.legalActions(0);
        require(actual.size()==(map?primitive.size():representatives.size()),
            "adapter exposes one representative per equivalent card choice");
        std::set<std::string> keys;
        std::map<std::uint32_t,double> mass;
        std::map<std::uint32_t,unsigned> counts;
        for(std::size_t i=0;i<actual.size();++i) {
            const auto &candidate=provider.candidate(0,actual[i].id);
            require(keys.insert(candidate.key).second,"unique immutable semantic identities");
            require(map ? actual[i].id==primitive[i].bits : actual[i].id==i,
                "MAP preserves primitive IDs; semantic IDs are local ordinals");
            if (!map) require(candidate.semantic
                && candidate.key==canonicalOocSemanticActionKey(representatives[i].semantic)
                && candidate.primitive.bits==representatives[i].primitiveBits,
                "semantic keys and source projection match complete enumeration");
            mass[candidate.primitive.bits]+=actual[i].prior;
            ++counts[candidate.primitive.bits];
            if (execute && !map) {
                auto expected=detachedCopy(canonical);
                const auto result=executeOocSemanticAction(expected,*candidate.semantic);
                require(result.ok,"fixture semantic execution succeeds");
                collectForcedRewardGold(expected);
                const auto child=provider.sampleSuccessor(0,actual[i].id,rng);
                require(test::oocStateFingerprint(provider.state(child))==test::oocStateFingerprint(expected),
                    "adapter semantic edge reaches complete transactional successor");
                if(candidate.compoundSelector!=CardSelectScreenType::INVALID)
                    require(result.executedPrimitiveBits.size()==2 && expected.screenState!=ScreenState::CARD_SELECT,
                        "compound edge consumes both source and physical card target");
            }
        }
        bool qualified=v4DecisionSupported(canonical);
        std::set<std::uint32_t> established;
        for(auto a:primitive) qualified=established.insert(a.bits).second && qualified;
        std::set<std::uint32_t> completeSources;
        for(const auto &binding:bindings.bindings)
            if(GameAction(binding.primitiveBits).isValidAction(canonical))
                completeSources.insert(binding.primitiveBits);
        if(map) for(const auto &[bits,count]:counts) completeSources.insert(bits);
        qualified=qualified && established==completeSources;
        if(qualified) {
            std::map<std::string,std::vector<double>> grouped;
            for(const auto &binding:bindings.bindings)
                if(GameAction(binding.primitiveBits).isValidAction(canonical))
                    grouped[canonicalOocMctsChoiceKey(binding.semantic, &canonical)].push_back(sourceLogits.at(binding.primitiveBits));
            std::vector<double> classLogits;
            if(map) for(auto action:primitive) classLogits.push_back(sourceLogits.at(action.bits));
            else for(const auto &binding:representatives) {
                const auto &values=grouped.at(canonicalOocMctsChoiceKey(binding.semantic, &canonical));
                classLogits.push_back(std::accumulate(values.begin(),values.end(),0.0)/values.size());
            }
            const auto weights=oocPolicyWeights(classLogits);
            for(std::size_t i=0;i<actual.size();++i)
                require(actual[i].prior==weights[i]/counts.at(
                    provider.candidate(0,actual[i].id).primitive.bits),
                    "semantic prior preserves exact averaged V4 class logits and source split");
            for(auto action:actual) {
                const auto bits=provider.candidate(0,action.id).primitive.bits;
                require(std::abs(action.prior-mass.at(bits)/counts.at(bits))<1e-12,
                    "compound target weights split equally");
            }
        } else for(auto action:actual) require(action.prior==1,"unqualified V4 semantic roots are wholly uniform");
        const bool traceMapCase = map && !directTraceChecked;
        const bool traceCompoundCase = !map && !compoundTraceChecked
            && canonical.screenState==ScreenState::CARD_SELECT
            && canonical.info.selectScreenType==CardSelectScreenType::UPGRADE;
        if(traceMapCase || traceCompoundCase) {
            require(qualified,"trace fidelity fixture must be prior-covered");
            const auto tracePath = newTraceFile();
            OocAdapterOptions traceOptions;
            traceOptions.priorTracePath=tracePath;
            traceOptions.priorTraceRunSeed=44;
            traceOptions.priorTraceDecisionIndex=5;
            traceOptions.priorTraceSearchSeed=1234567;
            OocGameContextModel traced(canonical,path,{},traceOptions);
            const auto tracedActions=traced.legalActions(0);
            const auto tracedAgain=traced.legalActions(0);
            require(tracedActions.size()==actual.size() && tracedAgain.size()==actual.size(),
                "trace keeps production candidate count");
            for(std::size_t i=0;i<actual.size();++i)
                require(tracedActions[i].id==actual[i].id && tracedActions[i].prior==actual[i].prior
                    && tracedAgain[i].id==actual[i].id && tracedAgain[i].prior==actual[i].prior,
                    "tracing preserves candidate order and raw planner weights");
            std::ifstream traceInput(tracePath);
            std::string traceLine, extraLine;
            require(std::getline(traceInput,traceLine) && !std::getline(traceInput,extraLine),
                "first prior build writes exactly one trace row");
            const auto row=nlohmann::json::parse(traceLine);
            require(row.at("schemaVersion")==1 && row.at("runSeed")==44
                && row.at("decisionIndex")==5 && row.at("searchSeed")==1234567
                && row.at("modelStateId")==0 && row.at("stateRole")=="root"
                && row.at("floor")==canonical.floorNum && row.at("screenId")==int(canonical.screenState)
                && row.at("candidateCount")==actual.size() && row.at("sourcePriorCovered")==true
                && row.at("singleton")==false && row.at("uniformPrior")==false,
                "trace identifies the root prior context and population class");
            const auto tracedLogits=traced.policyLogits(0);
            require(row.at("teacherCandidateLogits").size()==actual.size()
                && row.at("teacherRawPriorWeights").size()==actual.size()
                && row.at("teacherNormalizedPrior").size()==actual.size(),
                "trace contains one candidate logit and prior per production candidate");
            double totalWeight=0;
            for(const auto &action:actual) totalWeight+=action.prior;
            require(std::isfinite(totalWeight) && totalWeight>0,"fixture prior mass is finite");
            for(std::size_t i=0;i<actual.size();++i) {
                const auto &candidate=provider.candidate(0,actual[i].id);
                const auto &tracedCandidate=row.at("candidates").at(i);
                require(tracedCandidate.at("candidateId")==candidate.id
                    && tracedCandidate.at("semanticKey")==candidate.key
                    && tracedCandidate.at("primitiveBits")==candidate.primitive.bits
                    && tracedCandidate.at("hasSemantic")==candidate.semantic.has_value()
                    && tracedCandidate.at("compoundSelector")==int(candidate.compoundSelector),
                    "trace candidate IDs, order and semantic metadata match production");
                std::vector<std::uint32_t> expectedGroup;
                if(!map) {
                    const auto choiceKey=canonicalOocMctsChoiceKey(*candidate.semantic, &canonical);
                    for(const auto &binding:bindings.bindings)
                        if(GameAction(binding.primitiveBits).isValidAction(canonical)
                            && canonicalOocMctsChoiceKey(binding.semantic, &canonical)==choiceKey)
                            expectedGroup.push_back(binding.primitiveBits);
                }
                require(tracedCandidate.at("priorSourceGroup").get<std::vector<std::uint32_t>>()
                    ==expectedGroup,"trace preserves current semantic source groups, including direct MAP empties");
                require(tracedLogits[i]==row.at("teacherCandidateLogits").at(i).get<double>()
                    && tracedLogits[i]==tracedCandidate.at("teacherCandidateLogit").get<double>()
                    && actual[i].prior==tracedCandidate.at("teacherRawPriorWeight").get<double>()
                    && std::abs(actual[i].prior/totalWeight
                        -tracedCandidate.at("teacherNormalizedPrior").get<double>())<1e-12,
                    "trace logits and normalized priors reproduce legalActions exactly");
            }
            std::vector<std::uint32_t> expectedSources;
            std::set<std::uint32_t> seenSources;
            if(map) {
                for(const auto action:primitive)
                    if(seenSources.insert(action.bits).second) expectedSources.push_back(action.bits);
            } else {
                for(const auto &representative:representatives) {
                    const auto choiceKey=canonicalOocMctsChoiceKey(representative.semantic, &canonical);
                    for(const auto &binding:bindings.bindings)
                        if(GameAction(binding.primitiveBits).isValidAction(canonical)
                            && canonicalOocMctsChoiceKey(binding.semantic, &canonical)==choiceKey
                            && seenSources.insert(binding.primitiveBits).second)
                            expectedSources.push_back(binding.primitiveBits);
                }
            }
            const auto &serializedSources=row.at("sourcePrimitives");
            require(serializedSources.size()==expectedSources.size()
                && sourceLogits.size()==expectedSources.size(),
                "one native source logit is captured per distinct source primitive");
            for(std::size_t i=0;i<expectedSources.size();++i) {
                const auto bits=expectedSources[i];
                const auto &source=serializedSources.at(i);
                require(source.at("primitiveBits")==bits
                    && source.at("teacherSourceLogit").get<double>()==sourceLogits.at(bits),
                    "trace source primitive order and native logits match current V4 inputs");
                int type,c1,c2,c3,d1,d2,d3,entityType,entityId; float price;
                const GameAction action(bits);
                strategicCands(canonical,action,type,c1,c2,c3,d1,d2,d3);
                tokEntity(canonical,action,entityType,entityId,price);
                require(source.at("actionType")==type
                    && source.at("cats")==nlohmann::json({c1,c2,c3,d1,d2,d3})
                    && source.at("screen")==int(canonical.screenState)
                    && source.at("entityType")==entityType && source.at("entityId")==entityId
                    && source.at("goldGePrice").get<float>()==price,
                    "trace source features match strategicCands and tokEntity");
            }
            const auto expectedTokens=buildTokState(canonical,path);
            const auto &serializedTokens=row.at("tokenState");
            require(serializedTokens.at("glob").size()==TOK_NGLOB,
                "trace captures all 42 exact state globals");
            for(int i=0;i<TOK_NGLOB;++i)
                require(serializedTokens.at("glob").at(i).get<float>()==expectedTokens.glob[i],
                    "trace globals equal buildTokState");
            for(const auto &[key,count,values,width] : std::array<std::tuple<const char *,int,const int *,int>,3>{
                    std::tuple{"deck",expectedTokens.nDk,&expectedTokens.dk[0][0],3},
                    std::tuple{"relic",expectedTokens.nRl,&expectedTokens.rl[0][0],2},
                    std::tuple{"potion",expectedTokens.nPt,&expectedTokens.pt[0][0],2}}) {
                const std::string block=key;
                const std::string countKey=block=="deck"?"nDk":block=="relic"?"nRl":"nPt";
                const auto &serialized=serializedTokens.at(block);
                require(serialized.at(countKey)==count && serialized.at("tokens").size()==count,
                    "trace token arrays use their exact valid lengths");
                for(int i=0;i<count;++i) for(int j=0;j<width;++j)
                    require(serialized.at("tokens").at(i).at(j)==values[i*width+j],
                        "trace valid token values equal buildTokState");
            }
            std::remove(tracePath.c_str());
            if(map) directTraceChecked=true; else compoundTraceChecked=true;

            if(traceCompoundCase) {
                const auto uniformTracePath=newTraceFile();
                std::size_t inferenceCalls=0;
                auto dependencies=defaultOocMctsDependencies();
                dependencies.policyLogits=[&](const GameContext &,const PathHistory &,
                                               const std::vector<GameAction> &actions) {
                    ++inferenceCalls; return std::vector<double>(actions.size(),0.0);
                };
                OocAdapterOptions uniformOptions;
                uniformOptions.uniformPrior=true;
                uniformOptions.priorTracePath=uniformTracePath;
                OocGameContextModel uniformProvider(canonical,path,{},uniformOptions,dependencies);
                const auto uniformActions=uniformProvider.legalActions(0);
                std::ifstream uniformInput(uniformTracePath);
                require(static_cast<bool>(std::getline(uniformInput,traceLine)),"uniform prior trace row exists");
                const auto uniformRow=nlohmann::json::parse(traceLine);
                require(!inferenceCalls && uniformRow.at("sourcePriorCovered")==true
                    && uniformRow.at("uniformPrior")==true
                    && !uniformRow.contains("tokenState") && !uniformRow.contains("sourcePrimitives")
                    && uniformActions.size()==actual.size(),
                    "explicit uniform trace stays compact and does not force policy inference");
                std::remove(uniformTracePath.c_str());
            }
            if(traceMapCase) {
                const auto singletonTracePath=newTraceFile();
                std::size_t inferenceCalls=0;
                auto dependencies=defaultOocMctsDependencies();
                dependencies.policyLogits=[&](const GameContext &,const PathHistory &,
                                               const std::vector<GameAction> &actions) {
                    ++inferenceCalls; return std::vector<double>(actions.size(),0.0);
                };
                OocAdapterOptions singletonOptions;
                singletonOptions.priorTracePath=singletonTracePath;
                singletonOptions.priorTraceRunSeed=44;
                singletonOptions.priorTraceDecisionIndex=5;
                singletonOptions.priorTraceSearchSeed=1234567;
                singletonOptions.rootPrimitiveBits=std::set<std::uint32_t>{primitive.front().bits};
                OocGameContextModel singletonProvider(canonical,path,{},singletonOptions,dependencies);
                const auto singletonAction=singletonProvider.soleLegalAction(0);
                sts::search::OocMctsConfig singletonConfig;
                singletonConfig.maxDepth=1;
                const auto singletonBypass=searchWithSoleRootShortcut(singletonProvider,
                    singletonConfig,singletonAction,1);
                std::ifstream singletonInput(singletonTracePath);
                require(static_cast<bool>(std::getline(singletonInput,traceLine)),
                    "singleton shortcut writes its prior trace row");
                std::string singletonExtraLine;
                const auto singletonRow=nlohmann::json::parse(traceLine);
                require(singletonAction && singletonBypass.selectedAction==singletonAction
                    && singletonBypass.metrics.trivialRootBypasses==1
                    && inferenceCalls==0 && singletonRow.at("singleton")==true
                    && singletonRow.at("candidateCount")==1
                    && singletonRow.at("runSeed")==44 && singletonRow.at("decisionIndex")==5
                    && singletonRow.at("searchSeed")==1234567
                    && singletonRow.at("candidates").at(0).at("candidateId")==*singletonAction
                    && singletonRow.at("candidates").at(0).at("searchPriorWeight")==1.0
                    && !singletonRow.contains("tokenState") && !singletonRow.contains("sourcePrimitives"),
                    "production singleton root shortcut emits exactly one compact unit-prior trace row");
                require(!std::getline(singletonInput,singletonExtraLine),
                    "singleton shortcut writes only one prior trace row");
                singletonInput.close();
                const auto singletonActions=singletonProvider.legalActions(0);
                require(singletonActions.size()==1 && singletonActions.front().id==*singletonAction
                    && singletonActions.front().prior==1.0,
                    "legalActions reuses the singleton shortcut prior");
                std::ifstream singletonPostInput(singletonTracePath);
                std::string singletonPostLine;
                singletonExtraLine.clear();
                require(static_cast<bool>(std::getline(singletonPostInput,singletonPostLine))
                    && nlohmann::json::parse(singletonPostLine)==singletonRow
                    && !std::getline(singletonPostInput,singletonExtraLine),
                    "singleton legalActions lookup does not duplicate its shortcut trace");
                std::remove(singletonTracePath.c_str());
            }
        }
        OocAdapterOptions uniform; uniform.uniformPrior=true;
        OocGameContextModel uniformProvider(canonical,path,{},uniform);
        for(auto action:uniformProvider.legalActions(0)) require(action.prior==1,"explicit uniform semantic siblings");
        require(test::oocStateFingerprint(canonical)==before
            && test::oocStateFingerprint(provider.state(0))==before,"semantic testing preserves immutable root");
        std::cout<<"semantic_adapter_coverage screen="<<int(canonical.screenState)
            <<" event="<<int(canonical.curEvent)<<" selector="<<int(canonical.info.selectScreenType)
            <<" count="<<actual.size()<<" v4_qualified="<<qualified<<'\n';
    };
    {
        auto cardsOnly = detachedCopy(gc);
        CardReward cards;
        for (auto id : {CardId::SEVER_SOUL, CardId::ANGER, CardId::FLEX}) cards.push_back(Card(id));
        cardsOnly.openCombatRewardScreen(Rewards(cards));
        checkCandidates(cardsOnly);
        cardsOnly.relics.add({RelicId::SINGING_BOWL, 0});
        checkCandidates(cardsOnly);
    }
    auto fixture=detachedCopy(gc);
    fixture.screenState=ScreenState::REST_ROOM;
    fixture.relics.add({RelicId::PEACE_PIPE,0});
    fixture.relics.add({RelicId::GIRYA,0});
    fixture.relics.add({RelicId::SHOVEL,0});
    checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::REST_ROOM;
    fixture.relics.add({RelicId::COFFEE_DRIPPER,0});
    fixture.relics.add({RelicId::FUSION_HAMMER,0}); fixture.obtainKey(Key::RUBY_KEY);
    checkCandidates(fixture);
    for(auto selector : {CardSelectScreenType::UPGRADE,CardSelectScreenType::REMOVE,
        CardSelectScreenType::TRANSFORM,CardSelectScreenType::TRANSFORM_UPGRADE,
        CardSelectScreenType::DUPLICATE,CardSelectScreenType::BONFIRE_SPIRITS}) {
        fixture=detachedCopy(gc); fixture.openCardSelectScreen(selector,1); checkCandidates(fixture);
        if (selector==CardSelectScreenType::UPGRADE || selector==CardSelectScreenType::REMOVE
                || selector==CardSelectScreenType::TRANSFORM
                || selector==CardSelectScreenType::TRANSFORM_UPGRADE) {
            OocGameContextModel provider(fixture,path);
            unsigned strikes=0;
            for(auto action:provider.legalActions(0)) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(0,action.id).semantic->target);
                const auto *card=std::get_if<OocCardTarget>(&target.card);
                if(card && card->id==CardId::STRIKE_RED && !card->upgraded) {
                    ++strikes;
                    require(card->occurrence==0,"single-pick chooses first Strike occurrence");
                }
            }
            require(strikes==1 && provider.legalActions(0).size()<fixture.info.toSelectCards.size(),
                "single-pick remove/upgrade/transform collapses equivalent Strikes");
        }
    }
    {
        auto duplicates=detachedCopy(gc);
        duplicates.deck=Deck{};
        for(int i=0;i<3;++i) duplicates.deck.obtainRaw(Card(CardId::STRIKE_RED));
        for(int i=0;i<2;++i) duplicates.deck.obtainRaw(Card(CardId::DEFEND_RED));
        duplicates.deck.obtainRaw(Card(CardId::BASH));
        duplicates.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        checkCandidates(duplicates);
        auto deps=defaultOocMctsDependencies();
        std::size_t scored=0;
        deps.policyLogits=[&](const GameContext &, const PathHistory &,
                               const std::vector<GameAction> &actions) {
            scored=actions.size();
            std::vector<double> logits;
            for(auto action:actions) {
                const auto &card=duplicates.info.toSelectCards[action.getIdx1()].card;
                const auto idx=action.getIdx1();
                logits.push_back(card.id==CardId::STRIKE_RED ? double(idx)
                    : card.id==CardId::DEFEND_RED ? double(2*idx-3) : 6.0);
            }
            return logits;
        };
        OocGameContextModel grouped(duplicates,path,{}, {},deps);
        const auto actions=grouped.legalActions(0);
        require(actions.size()==3 && scored==6,"six physical upgrades project to three scored classes");
        const auto expected=oocPolicyWeights({1.0,4.0,6.0});
        for(const auto action:actions) {
            const auto &target=std::get<OocSelectorTarget>(grouped.candidate(0,action.id).semantic->target);
            const auto &card=std::get<OocCardTarget>(target.card);
            const auto index=card.id==CardId::STRIKE_RED ? 0 : card.id==CardId::DEFEND_RED ? 1 : 2;
            require(std::abs(action.prior-expected[index])<1e-12,
                "duplicate multiplicity does not alter nonuniform upgrade priors");
        }
        OocAdapterOptions restricted;
        restricted.rootPrimitiveBits=std::set<std::uint32_t>{v4CandidateActions(duplicates)[1].bits};
        OocGameContextModel secondCopy(duplicates,path,{},restricted,deps);
        const auto restrictedActions=secondCopy.legalActions(0);
        require(restrictedActions.size()==1 && scored==6 && restrictedActions.front().prior==1.0
            && secondCopy.candidate(0,restrictedActions.front().id).primitive.bits
                ==*restricted.rootPrimitiveBits->begin(),
            "singleton root keeps its action identity and exact prior without another V4 score");
    }
    {
        // Keys off: a chest's sapphire key must not compete with its relic.
        auto chest=detachedCopy(gc); chest.screenState=ScreenState::REWARDS;
        chest.info.rewardsContainer.clear();
        chest.info.rewardsContainer.addRelic(RelicId::ANCHOR);
        chest.info.rewardsContainer.sapphireKey=true;
        const auto effects=[&](const OocGameContextModel &m) {
            std::vector<OocSemanticEffect> out;
            for(auto a:m.legalActions(0)) out.push_back(m.candidate(0,a.id).semantic->effect);
            return out;
        };
        const auto has=[](const std::vector<OocSemanticEffect> &v,OocSemanticEffect e) {
            return std::find(v.begin(),v.end(),e)!=v.end();
        };
        OocGameContextModel withKeys(chest,path,{},{},defaultOocMctsDependencies());
        require(has(effects(withKeys),OocSemanticEffect::TAKE_KEY),"keys-on chest offers the sapphire key");
        OocAdapterOptions noKeys; noKeys.collectKeys=false;
        auto deps=defaultOocMctsDependencies();
        bool scoredKey=false;
        deps.policyLogits=[&](const GameContext &, const PathHistory &, const std::vector<GameAction> &actions) {
            std::vector<double> logits;
            for(auto a:actions) {
                scoredKey=scoredKey || a.getRewardsActionType()==GameAction::RewardsActionType::KEY;
                logits.push_back(double(logits.size()));
            }
            return logits;
        };
        OocGameContextModel withoutKeys(chest,path,{},noKeys,deps);
        const auto filtered=effects(withoutKeys);
        const auto priors=withoutKeys.legalActions(0);
        require(!has(filtered,OocSemanticEffect::TAKE_KEY) && has(filtered,OocSemanticEffect::TAKE_RELIC)
            && has(filtered,OocSemanticEffect::LEAVE_REWARDS) && !scoredKey
            && priors.size()==2 && priors[0].prior!=priors[1].prior,
            "keys-off chest drops only the key and keeps the policy prior");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::SHOP_ROOM;
    fixture.gold=500; fixture.info.shop.setup(fixture);
    std::fill(std::begin(fixture.info.shop.prices), std::end(fixture.info.shop.prices), -1);
    fixture.info.shop.relics[0]=RelicId::PRISMATIC_SHARD; fixture.info.shop.relicPrice(0)=50;
    fixture.info.shop.relics[1]=RelicId::ANCHOR; fixture.info.shop.relicPrice(1)=50;
    checkCandidates(fixture);
    {
        const auto all = GameAction::getAllActionsInState(fixture);
        const auto v4 = v4CandidateActions(fixture);
        const auto semantic = enumerateOocSemanticPrimitiveBindings(fixture);
        const auto isShardPrimitive = [&](const GameAction primitive) {
            return primitive.getRewardsActionType() == GameAction::RewardsActionType::RELIC
                && primitive.getIdx1() >= 0 && primitive.getIdx1() < 3
                && fixture.info.shop.relics[primitive.getIdx1()] == RelicId::PRISMATIC_SHARD;
        };
        const auto hasShardPrimitive = [&](const std::vector<GameAction> &actions) {
            return std::any_of(actions.begin(), actions.end(), isShardPrimitive);
        };
        const auto hasRelicBinding = [&](RelicId relic) {
            return std::any_of(semantic.bindings.begin(), semantic.bindings.end(), [&](const auto &binding) {
                if (binding.semantic.effect != OocSemanticEffect::BUY_RELIC) return false;
                const auto &target = std::get<OocShopTarget>(binding.semantic.target);
                return std::get<RelicId>(target.entity) == relic;
            });
        };
        require(hasShardPrimitive(all), "shop fixture did not retain displayed Prismatic Shard");
        require(!hasShardPrimitive(v4), "V4 shop candidates retained Prismatic Shard");
        require(semantic.supported && semantic.complete, "semantic shop enumeration unsupported");
        require(!hasRelicBinding(RelicId::PRISMATIC_SHARD),
            "semantic shop bindings retained Prismatic Shard");
        require(hasRelicBinding(RelicId::ANCHOR), "semantic shop bindings lost ordinary relic");
        require(std::any_of(semantic.bindings.begin(), semantic.bindings.end(), [](const auto &binding) {
                    return binding.semantic.effect == OocSemanticEffect::LEAVE_SHOP;
                }), "semantic shop bindings lost Leave");

        OocGameContextModel shop(fixture,path);
        const auto legal = shop.legalActions(0);
        require(!shop.isLeafBoundary(0) && !legal.empty(),
            "Prismatic Shard made semantic shop root unsupported");
        bool mctsAnchor = false, mctsLeave = false;
        for (const auto action : legal) {
            const auto &candidate = shop.candidate(0, action.id);
            require(candidate.semantic.has_value(), "shop MCTS candidate lost semantic identity");
            if (candidate.semantic->effect == OocSemanticEffect::BUY_RELIC) {
                const auto &target = std::get<OocShopTarget>(candidate.semantic->target);
                const auto relic = std::get<RelicId>(target.entity);
                require(relic != RelicId::PRISMATIC_SHARD,
                    "semantic OOC MCTS retained Prismatic Shard");
                mctsAnchor |= relic == RelicId::ANCHOR;
            }
            mctsLeave |= candidate.semantic->effect == OocSemanticEffect::LEAVE_SHOP;
        }
        require(mctsAnchor && mctsLeave,
            "semantic OOC MCTS lost ordinary relic or Leave candidate");

        auto fallbackShop = detachedCopy(fixture);
        search::ScumSearchAgent2 fallbackAgent;
        runFullRunOocPolicyStep(fallbackShop, fallbackAgent, false, true);
        require(!fallbackShop.relics.has(RelicId::PRISMATIC_SHARD),
            "full-run OOC shop fallback bought Prismatic Shard");
    }
    {
        OocGameContextModel shop(fixture,path);
        std::set<unsigned> strikeOccurrences;
        unsigned removals=0;
        for(auto a:shop.legalActions(0)) {
            const auto &c=shop.candidate(0,a.id);
            if(c.semantic->effect!=OocSemanticEffect::REMOVE_CARD) continue;
            ++removals;
            const auto &target=std::get<OocTransactionTarget>(c.semantic->target).card;
            if(target.id==CardId::STRIKE_RED) strikeOccurrences.insert(target.occurrence);
        }
        auto selector=detachedCopy(fixture); GameAction(GameAction::RewardsActionType::CARD_REMOVE).execute(selector);
        require(removals<selector.info.toSelectCards.size() && strikeOccurrences==std::set<unsigned>{0},
            "shop removal searches one first Strike occurrence");
    }
    for(auto event : {Event::BIG_FISH,Event::THE_CLERIC,Event::LIVING_WALL,
        Event::TRANSMORGRIFIER,Event::UPGRADE_SHRINE,Event::DUPLICATOR,
        Event::OMINOUS_FORGE,Event::ANCIENT_WRITING,Event::OLD_BEGGAR,
        Event::DESIGNER_IN_SPIRE,Event::PURIFIER,Event::WING_STATUE}) {
        fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN;
        fixture.curEvent=event; fixture.gold=500; fixture.info.hpAmount0=20;
        fixture.info.hpAmount1=5; fixture.info.upgradeOne=true;
        fixture.info.cleanUpIsRemoveCard=true; checkCandidates(fixture);
    }
    fixture=detachedCopy(gc); fixture.setupTreasureRoom(); checkCandidates(fixture);
    {
        OocGameContextModel chest(fixture,path);
        const auto open=sourceId(chest,0);
        const auto child=chest.sampleSuccessor(0,open,rng);
        require(chest.candidate(0,open).semantic->effect==OocSemanticEffect::OPEN_CHEST
            && chest.state(child).screenState==ScreenState::REWARDS,
            "chest opening stops at newly revealed rewards");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::BOSS_RELIC_REWARDS;
    fixture.info.bossRelics[0]=RelicId::ASTROLABE;
    fixture.info.bossRelics[1]=RelicId::COFFEE_DRIPPER;
    fixture.info.bossRelics[2]=RelicId::FUSION_HAMMER; checkCandidates(fixture);
    checkCandidates(gc,false);
    {
        // Compare a fixed-work search using the original full policy head with
        // the shared-prefix path, including all root statistics, successor
        // fingerprints and the caller-owned search RNG state after each draw.
        auto legacyDependencies=defaultOocMctsDependencies();
        legacyDependencies.policyLogits=[](const GameContext &source,const PathHistory &history,
                                            const std::vector<GameAction> &actions) {
            const TokState tokens=buildTokState(source,history);
            const auto state=g_oocStrategicTokNet.prepareState(tokens.glob,tokens.nDk,tokens.dk,
                tokens.nRl,tokens.rl,tokens.nPt,tokens.pt);
            std::vector<double> logits; logits.reserve(actions.size());
            for(const auto action:actions) {
                int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
                strategicCands(source,action,type,c1,c2,c3,d1,d2,d3);
                tokEntity(source,action,et,ei,price);
                const int cats[6]={c1,c2,c3,d1,d2,d3};
                const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
                logits.push_back(g_oocStrategicTokNet.predictPolicyLogit(state,action.bits,cats,
                    type,int(source.screenState),entity,ei,price));
            }
            return logits;
        };
        struct PrimitiveMapRoot final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<OocPlannerAction> primitiveActions;
            std::vector<std::string> successorFingerprints;
            std::vector<std::uint64_t> rngAfterDraw;
            PrimitiveMapRoot(const GameContext &g,const PathHistory &p,const OocMctsDependencies &deps)
                :adapter(g,p,{}, {},deps) {
                const auto actions=v4CandidateActions(g);
                const auto weights=oocPolicyWeights(adapter.policyLogits(0));
                for(std::size_t i=0;i<actions.size();++i) primitiveActions.push_back({actions[i].bits,weights[i]});
            }
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
                require(id==0,"bounded MAP comparison never expands a child"); return primitiveActions;
            }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
                const auto child=adapter.sampleSuccessor(id,a,r);
                auto copy=r; rngAfterDraw.push_back(copy());
                successorFingerprints.push_back(test::oocStateFingerprint(adapter.state(child)));
                return child;
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
            double evaluateLeaf(OocStateId id,std::mt19937_64 &r) override { return adapter.evaluateLeaf(id,r); }
            bool isDeterministicTransition(OocStateId id,OocActionId a) const override {
                return adapter.isDeterministicTransition(id,a);
            }
        } baseline(gc,path,legacyDependencies);
        struct CurrentPrefixRoot final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<std::string> successorFingerprints;
            std::vector<std::uint64_t> rngAfterDraw;
            CurrentPrefixRoot(const GameContext &g,const PathHistory &p):adapter(g,p) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
                const auto child=adapter.sampleSuccessor(id,a,r);
                auto copy=r; rngAfterDraw.push_back(copy());
                successorFingerprints.push_back(test::oocStateFingerprint(adapter.state(child)));
                return child;
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
            double evaluateLeaf(OocStateId id,std::mt19937_64 &r) override { return adapter.evaluateLeaf(id,r); }
            bool isDeterministicTransition(OocStateId id,OocActionId a) const override {
                return adapter.isDeterministicTransition(id,a);
            }
        } current(gc,path);
        OocMctsConfig config;
        const auto expected=OocMctsPlanner(config).search(baseline,0,32);
        const auto actual=OocMctsPlanner(config).search(current,0,32);
        require(actual.selectedAction==expected.selectedAction && actual.rootActions.size()==expected.rootActions.size()
            && actual.metrics.simulations==expected.metrics.simulations
            && actual.metrics.transitionSamples==expected.metrics.transitionSamples
            && actual.metrics.decisionNodes==expected.metrics.decisionNodes
            && actual.metrics.chanceNodes==expected.metrics.chanceNodes
            && actual.metrics.leafEvaluations==expected.metrics.leafEvaluations
            && actual.metrics.expandedNodes0Actions==expected.metrics.expandedNodes0Actions
            && actual.metrics.expandedNodes1Action==expected.metrics.expandedNodes1Action
            && actual.metrics.expandedNodes2Actions==expected.metrics.expandedNodes2Actions
            && actual.metrics.expandedNodes3PlusActions==expected.metrics.expandedNodes3PlusActions,
            "fixed-work MAP search action and expansion metrics remain exactly equivalent");
        for(std::size_t i=0;i<actual.rootActions.size();++i) {
            const auto &a=actual.rootActions[i], &b=expected.rootActions[i];
            require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
                "MAP planner statistics remain exactly equivalent");
        }
        require(current.successorFingerprints==baseline.successorFingerprints
            && current.rngAfterDraw==baseline.rngAfterDraw,
            "fixed-work successors and search RNG draw sequence remain exactly equivalent");
    }
    auto checkSequential=[&](GameContext source, std::uint32_t sourceBits,int picks) {
        checkCandidates(source);
        OocGameContextModel provider(source,path);
        const auto id=sourceId(provider,sourceBits);
        require(provider.candidate(0,id).compoundSelector==CardSelectScreenType::INVALID,
            "multi-select/random-reveal source remains a separate edge");
        auto child=provider.sampleSuccessor(0,id,rng);
        for(int pick=0;pick<picks;++pick) {
            const auto &state=provider.state(child);
            require(state.screenState==ScreenState::CARD_SELECT,"source/pick retains selector boundary");
            const auto actions=provider.legalActions(child);
            require(!actions.empty() && actions.size()<=state.info.toSelectCards.size(),
                "one current pick per equivalent card without subset cross-product");
            for(auto a:actions) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(child,a.id).semantic->target);
                require(target.completedPicks==pick && target.requiredPicks==picks,"selector progress re-enumerated");
            }
            checkCandidates(detachedCopy(state));
            child=provider.sampleSuccessor(child,actions.front().id,rng);
        }
        require(provider.state(child).screenState!=ScreenState::CARD_SELECT,"last sequential pick completes");
    };
    checkSequential(fixture,0,3);
    {
        auto repeated=detachedCopy(gc);
        repeated.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,3);
        OocGameContextModel provider(repeated,path);
        OocStateId current=0;
        for(unsigned pick=0;pick<3;++pick) {
            unsigned strikes=0;
            std::optional<OocActionId> selected;
            for(auto action:provider.legalActions(current)) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(current,action.id).semantic->target);
                const auto *card=std::get_if<OocCardTarget>(&target.card);
                if(card && card->id==CardId::STRIKE_RED && !card->upgraded) {
                    ++strikes;
                    require(card->occurrence==pick,"multi-pick resolves first remaining Strike");
                    selected=action.id;
                }
            }
            require(strikes==1 && selected,"multi-pick searches one equivalent Strike");
            current=provider.sampleSuccessor(current,*selected,rng);
        }
        require(provider.state(current).screenState!=ScreenState::CARD_SELECT,
            "three equivalent picks complete the selector");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN; fixture.curEvent=Event::AUGMENTER;
    checkSequential(fixture,1,2);
    fixture.curEvent=Event::THE_LIBRARY; checkSequential(fixture,0,1);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::REWARDS;
    Rewards visibleRewards; visibleRewards.addGold(25); visibleRewards.addRelic(RelicId::ANCHOR);
    visibleRewards.addPotion(Potion::FIRE_POTION);
    CardReward visibleCards; visibleCards.push_back(Card(CardId::INFLAME));
    visibleCards.push_back(Card(CardId::BASH)); visibleRewards.addCardReward(visibleCards);
    fixture.info.rewardsContainer=visibleRewards; checkCandidates(fixture);
    fixture.relics.add({RelicId::SINGING_BOWL,0}); checkCandidates(fixture);
    for (auto bottle : {RelicId::BOTTLED_FLAME, RelicId::BOTTLED_LIGHTNING,
                        RelicId::BOTTLED_TORNADO}) {
        fixture.info.rewardsContainer.relics[0]=bottle;
        checkCandidates(fixture);
        OocGameContextModel bottleChoices(fixture,path);
        bool canTake=false, canSkip=false;
        for (const auto &action : bottleChoices.legalActions(0)) {
            const auto &candidate=bottleChoices.candidate(0,action.id);
            if (!candidate.semantic) continue;
            canTake |= candidate.semantic->effect==OocSemanticEffect::TAKE_RELIC;
            canSkip |= candidate.semantic->effect==OocSemanticEffect::LEAVE_REWARDS;
        }
        require(canTake && canSkip && bottleChoices.state(0).info.rewardsContainer.relicCount==1,
            "Bottled relic remains optional after forced gold collection");
    }
    fixture.info.rewardsContainer.relics[0]=RelicId::BOTTLED_FLAME;
    GameAction(GameAction::RewardsActionType::RELIC).execute(fixture);
    require(fixture.info.selectScreenType==CardSelectScreenType::BOTTLE,"bottle fixture opens selector");
    checkCandidates(fixture);
    {
        auto fresh=detachedCopy(gc); fresh.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        OocGameContextModel provider(fresh,path);
        const auto chosen=provider.candidate(0,provider.legalActions(0).front().id);
        std::reverse(fresh.info.toSelectCards.begin(),fresh.info.toSelectCards.end());
        auto expected=detachedCopy(fresh);
        require(executeOocSemanticAction(expected,*chosen.semantic).ok,"fresh resolution oracle");
        std::string error;
        require(executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==test::oocStateFingerprint(expected),
            "fresh root resolves physical identity after selector order changes");
        const auto before=test::oocStateFingerprint(fresh);
        require(!executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==before,"stale root identity executes nothing");
        fresh=detachedCopy(gc); fresh.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        const auto observerBefore=test::oocStateFingerprint(fresh);
        auto savedObserver=std::move(g_onGameActionExecute); int callbacks=0;
        g_onGameActionExecute=[&](std::uint32_t,const GameContext *) { ++callbacks; };
        const bool executed=executeOocMctsRoot(fresh,chosen,error);
        g_onGameActionExecute=std::move(savedObserver);
        require(!executed && callbacks==0 && test::oocStateFingerprint(fresh)==observerBefore,
            "active observer rejects semantic live execution before mutation");
        fresh.info.toSelectCards.push_back(fresh.info.toSelectCards.front());
        const auto ambiguousBefore=test::oocStateFingerprint(fresh);
        require(!executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==ambiguousBefore,
            "ambiguous semantic enumeration rejects live root without mutation");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::CARD_SELECT;
    fixture.info.selectScreenType=CardSelectScreenType::INVALID;
    OocGameContextModel unsupportedSelector(fixture,path);
    require(unsupportedSelector.isLeafBoundary(0),"invalid selector remains boundary");
    fixture=detachedCopy(gc); fixture.curMapNodeY=14;
    OocGameContextModel lastRow(fixture,path); require(lastRow.isLeafBoundary(0),"map row 14 boundary");
    fixture=detachedCopy(gc); fixture.map=nullptr;
    OocGameContextModel noMap(fixture,path); require(noMap.isLeafBoundary(0),"missing map boundary");
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN; fixture.curEvent=Event::MATCH_AND_KEEP;
    OocGameContextModel match(fixture,path); require(match.isLeafBoundary(0),"match and keep boundary");
    {
        // Match and Keep valuation: a lone-card offer on a detached copy; the
        // caller's step decides, and the source state is never touched.
        const auto sourceBefore=test::oocStateFingerprint(gc);
        const auto take=[](GameContext &offer){ GameAction(GameAction::RewardsActionType::CARD,0,0).execute(offer); };
        const auto skip=[](GameContext &offer){ offer.regainControl(); };
        require(oocHypotheticalCardTaken(gc,path,sts::Card(CardId::ANGER),take),"hypothetical offer take");
        require(!oocHypotheticalCardTaken(gc,path,sts::Card(CardId::ANGER),skip),"hypothetical offer skip");
        require(test::oocStateFingerprint(gc)==sourceBefore,"hypothetical offer leaves source untouched");
    }
    // Live outcome sampling must not optimize against copied future streams or
    // freeze random successors in the deterministic-edge cache.
    {
        OocAdapterOptions sampled; sampled.sampleNoncombat=true;
        const auto visible = [](const GameContext &g) {
            std::string result=std::to_string(int(g.screenState))+":"+std::to_string(g.curHp)+":"+std::to_string(g.gold);
            for(const auto &c:g.deck.cards) result += ":"+std::to_string(int(c.id))+"/"+std::to_string(c.isUpgraded());
            for(const auto &r:g.relics.relics) result += ":r"+std::to_string(int(r.id));
            if(g.screenState==ScreenState::BATTLE) result += ":fight"+std::to_string(int(g.info.encounter));
            const auto actions=enumerateOocSemanticActions(g);
            for(const auto &a:actions.actions) result += ":"+canonicalOocSemanticActionKey(a);
            return result;
        };
        const auto varied = [&](GameContext source,OocSemanticEffect effect,OocSemanticSource origin) {
            OocGameContextModel adapter(source,path,{},sampled);
            std::optional<OocActionId> selected;
            for(auto a:adapter.legalActions(0)) {
                const auto &c=adapter.candidate(0,a.id);
                if(c.semantic && c.semantic->effect==effect && c.semantic->source==origin) { selected=a.id; break; }
            }
            require(selected.has_value(),"stochastic fixture has requested semantic edge");
            const auto before=test::oocStateFingerprint(source);
            std::set<std::string> outcomes;
            std::mt19937_64 draws(91234);
            for(int n=0;n<32;++n) {
                auto child=adapter.sampleSuccessor(0,*selected,draws);
                outcomes.insert(visible(adapter.state(child)));
                require(!adapter.isDeterministicTransition(0,*selected),"random outcome never cached as deterministic");
            }
            require(outcomes.size()>1,"unknown noncombat effect produces multiple sampled outcomes");
            require(test::oocStateFingerprint(source)==before && test::oocStateFingerprint(adapter.state(0))==before,
                "sampled outcomes preserve live and immutable parent state");
            std::cout<<"sampled_ooc effect="<<int(effect)<<" source="<<int(origin)<<" outcomes="<<outcomes.size()<<'\n';
        };
        for(auto event:{Event::LIVING_WALL,Event::TRANSMORGRIFIER}) {
            auto source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=event;
            varied(source,OocSemanticEffect::TRANSFORM_CARD,OocSemanticSource::EVENT);
        }
        for(auto stream:{CARD_RNG,MISC_RNG,NEOW_RNG}) {
            auto source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM,1);
            source.info.transformRng=stream;
            varied(source,OocSemanticEffect::TRANSFORM_CARD,OocSemanticSource::SELECTOR);
        }
        auto source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,1);
        varied(source,OocSemanticEffect::TRANSFORM_UPGRADE_CARD,OocSemanticSource::SELECTOR);
        source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=Event::THE_LIBRARY;
        varied(source,OocSemanticEffect::EVENT_CHOICE,OocSemanticSource::EVENT);
        source=detachedCopy(gc); source.setupTreasureRoom();
        varied(source,OocSemanticEffect::OPEN_CHEST,OocSemanticSource::TREASURE);
        source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=Event::DEAD_ADVENTURER;
        source.setupEvent(); varied(source,OocSemanticEffect::EVENT_CHOICE,OocSemanticSource::EVENT);
        source=detachedCopy(gc); source.screenState=ScreenState::BOSS_RELIC_REWARDS;
        source.info.bossRelics[0]=RelicId::PANDORAS_BOX;
        source.info.bossRelics[1]=RelicId::COFFEE_DRIPPER; source.info.bossRelics[2]=RelicId::FUSION_HAMMER;
        // Select Pandora explicitly; canonical relic ordering need not put it first.
        OocGameContextModel pandora(source,path,{},sampled); std::set<std::string> pandoraOutcomes;
        std::set<std::uint64_t> pandoraKeys;
        std::mt19937_64 pandoraDraws(819);
        for(auto action:pandora.legalActions(0)) {
            const auto &c=pandora.candidate(0,action.id);
            if(c.semantic->effect!=OocSemanticEffect::TAKE_BOSS_RELIC
                || std::get<OocRelicTarget>(c.semantic->target).relic!=RelicId::PANDORAS_BOX) continue;
            for(int n=0;n<16;++n) {
                const auto child=pandora.sampleSuccessor(0,action.id,pandoraDraws);
                pandoraOutcomes.insert(visible(pandora.state(child)));
                pandoraKeys.insert(*pandora.outcomeEquivalenceKey(child));
            }
        }
        require(pandoraOutcomes.size()>1,"Pandora random transformations resampled");
        require(pandoraKeys.size()==pandoraOutcomes.size(),"distinct visible outcomes never share an equivalence key");
        source=detachedCopy(gc); source.screenState=ScreenState::REST_ROOM; source.relics.add({RelicId::SHOVEL,0});
        varied(source,OocSemanticEffect::DIG,OocSemanticSource::CAMPFIRE);
        source=detachedCopy(gc); source.screenState=ScreenState::SHOP_ROOM; source.gold=999;
        source.relics.add({RelicId::THE_COURIER,0}); source.info.shop.setup(source);
        varied(source,OocSemanticEffect::BUY_CARD,OocSemanticSource::SHOP);
        // A deterministic upgrade remains the same public effect, even though
        // its unobserved future receives a fresh particle on every draw.
        source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        OocGameContextModel upgrades(source,path,{},sampled);
        const auto upgrade=upgrades.legalActions(0).front().id;
        std::mt19937_64 draws(712);
        const auto first=upgrades.sampleSuccessor(0,upgrade,draws);
        const auto second=upgrades.sampleSuccessor(0,upgrade,draws);
        require(visible(upgrades.state(first))==visible(upgrades.state(second)),"deterministic public upgrade preserved");
        require(upgrades.outcomeEquivalenceKey(first) && upgrades.outcomeEquivalenceKey(first)==upgrades.outcomeEquivalenceKey(second),
            "re-sampled futures of one public upgrade are search-equivalent");
        OocGameContextModel exactUpgrades(source,path);
        require(!exactUpgrades.outcomeEquivalenceKey(0),"exact-replay futures are never merged");
        // Same planner draws, different true seed/stream states/hidden order:
        // both hypothetical futures must be exactly the same.
        source=detachedCopy(gc); source.setupTreasureRoom();
        auto altered=detachedCopy(source);
        altered.seed ^= 0xCAFEBABE;
        for(auto stream:{&altered.aiRng,&altered.cardRandomRng,&altered.cardRng,&altered.eventRng,
                &altered.mathUtilRng,&altered.merchantRng,&altered.miscRng,&altered.monsterHpRng,
                &altered.monsterRng,&altered.neowRng,&altered.potionRng,&altered.relicRng,
                &altered.shuffleRng,&altered.treasureRng}) { stream->seed0 ^= 123; stream->seed1 ^= 456; }
        for(auto pool:{&altered.commonRelicPool,&altered.uncommonRelicPool,&altered.rareRelicPool,
                &altered.shopRelicPool,&altered.bossRelicPool}) std::reverse(pool->begin(),pool->end());
        std::reverse(altered.monsterList.begin(),altered.monsterList.end());
        std::reverse(altered.eliteMonsterList.begin(),altered.eliteMonsterList.end());
        std::reverse(altered.colorlessCardPool.begin(),altered.colorlessCardPool.end());
        altered.info.haveGold=!altered.info.haveGold; altered.info.tier=RelicTier::RARE;
        require(outcomeEquivalenceKeyOf(source,path)==outcomeEquivalenceKeyOf(altered,path),
            "equivalence key omits everything the future sampler re-draws");
        {
            auto richer=detachedCopy(source); ++richer.gold;
            auto counters=detachedCopy(source); counters.potionChance+=10;
            require(outcomeEquivalenceKeyOf(source,path)!=outcomeEquivalenceKeyOf(richer,path)
                && outcomeEquivalenceKeyOf(source,path)!=outcomeEquivalenceKeyOf(counters,path),
                "equivalence key keeps visible state and copied hidden counters");
        }
        std::mt19937_64 left(19),right(19);
        sampleNoncombatFuture(source,left); sampleNoncombatFuture(altered,right);
        require(test::oocStateFingerprint(source)==test::oocStateFingerprint(altered),
            "hypothetical future independent of copied hidden seeds and queue ordering");
        require(left==right,"sampling consumes reproducible planner draws");
        // The shared simulator sampler must preserve native counters. Only
        // the live advisor injects a public-belief prior at a root particle.
        source.monsterChance=.7f; source.shopChance=.12f;
        source.treasureChance=.08f; source.potionChance=20;
        source.cardRarityFactor=-11;
        sampleNoncombatFuture(source,left);
        require(source.monsterChance==.7f && source.shopChance==.12f
                && source.treasureChance==.08f && source.potionChance==20
                && source.cardRarityFactor==-11,
            "simulator hypothetical sampling changed native counters");
        // Revealed offers/selector progress, current map and visible boss survive.
        source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,3);
        GameAction(0).execute(source);
        auto before=visible(source); auto map=source.map; auto boss=source.boss;
        const auto progress=source.info.haveSelectedCards.size();
        sampleNoncombatFuture(source,left);
        require(visible(source)==before && source.map==map && source.boss==boss
            && source.info.haveSelectedCards.size()==progress,"public state and sequential selector progress preserved");
        source=detachedCopy(gc); source.screenState=ScreenState::MAP_SCREEN;
        OocGameContextModel mapModel(source,path,{},sampled);
        std::set<int> encounters;
        const auto mapAction=mapModel.legalActions(0).front().id;
        for(int n=0;n<32;++n) {
            const auto child=mapModel.sampleSuccessor(0,mapAction,left);
            encounters.insert(int(mapModel.state(child).info.encounter));
        }
        require(encounters.size()>1,"MAP samples hidden encounter queue rather than copied future");
        struct CaptureSampler final : CombatTransitionSampler {
            mutable std::set<std::uint64_t> seeds;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &) const override {
                seeds.insert(g.seed); return {true,"sampled fixture"};
            }
            CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
                return {CombatRuntimeSample::Outcome::DEATH,{}};
            }
        };
        auto capture=std::make_shared<CaptureSampler>(); sampled.checkpointLeaves=true;
        OocGameContextModel prepared(source,path,capture,sampled);
        for(int n=0;n<8;++n) prepared.sampleSuccessor(0,mapAction,left);
        require(prepared.continuationMetrics().preparedCombats==8 && capture->seeds.size()==8,
            "each sampled combat successor prepares its own predictor context");
        auto alternate=detachedCopy(source);
        std::reverse(alternate.monsterList.begin(),alternate.monsterList.end()); alternate.seed^=812;
        OocGameContextModel leafA(source,path,{},sampled),leafB(alternate,path,{},sampled);
        std::mt19937_64 aRng(198),bRng(198);
        require(leafA.evaluateLeaf(0,aRng)==leafB.evaluateLeaf(0,bRng),
            "native leaf uses sampled future features rather than actual hidden queue");
    }
    OocAdapterOptions uniformOptions{true}; uniformOptions.uniformPrior = true;
    OocGameContextModel uniformPrior(gc,path,{},uniformOptions);
    const auto uniformActions = uniformPrior.legalActions(0);
    require(!uniformActions.empty(), "uniform prior retains legal actions");
    for (const auto &action : uniformActions) require(action.prior == 1, "uniform prior equal positive weights");
    OocAdapterOptions constantOptions{true}; constantOptions.constantLeaf = true;
    OocGameContextModel constantCheckpoint(gc,path,{},constantOptions);
    std::mt19937_64 constantRng(777);
    require(constantCheckpoint.evaluateLeaf(0,constantRng) == .5, "constant value only at resolved checkpoint");
    for (auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        auto terminal = detachedCopy(gc); terminal.outcome = outcome;
        OocGameContextModel exactTerminal(terminal,path,{},constantOptions);
        require(exactTerminal.evaluateLeaf(0,constantRng) == (outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0),
                "constant ablation preserves terminal values");
    }
    struct BossExpectationSampler final : CombatTransitionSampler {
        mutable int expectationCalls=0;
        mutable std::vector<MonsterEncounter> encounters;
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override {
            return {true,"supported"};
        }
        CombatTransitionExpectation expectation(const GameContext &probe,
            const CombatPredictorInputV1 &) const override {
            ++expectationCalls;
            encounters.push_back(probe.info.encounter);
            return {true,0.2f,0.5f};
        }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,
            std::mt19937_64 &) const override { return {}; }
    };
    auto bossSampler=std::make_shared<BossExpectationSampler>();
    OocAdapterOptions bossCheckpointOptions{true}; bossCheckpointOptions.bossLeaf=true;
    OocGameContextModel bossCheckpoint(gc,path,bossSampler,bossCheckpointOptions);
    const double nativeCheckpointValue=vStateWinNative(gc);
    const double bossCheckpointValue=bossCheckpoint.evaluateLeaf(0,constantRng);
    require(bossSampler->expectationCalls==10 && bossSampler->encounters.size()==10,
        "checkpoint boss leaf calls every all-act boss expectation");
    require(std::set<MonsterEncounter>(bossSampler->encounters.begin(),bossSampler->encounters.end()).size()==10,
        "checkpoint boss leaf probes ten distinct bosses");
    require(std::abs(bossCheckpointValue-0.7)<1e-7
        && std::abs(bossCheckpointValue-nativeCheckpointValue)>1e-6,
        "checkpoint boss leaf returns combat expectation instead of native v_win");
    {
        // Direct probe leaf: a pending non-combat screen is valued by v_win in
        // place, with no policy-chain projection step.
        auto pending=detachedCopy(gc); pending.screenState=ScreenState::REST_ROOM;
        OocAdapterOptions directOptions{true}; directOptions.directLeaf=true;
        OocGameContextModel direct(pending,path,bossSampler,directOptions);
        OocGameContextModel playout(pending,path,bossSampler,OocAdapterOptions{true});
        std::mt19937_64 directRng(20261006);
        const double expected=vStateWinNative(pending);
        require(direct.evaluateLeaf(0,directRng)==expected
            && direct.continuationMetrics().projectionSteps==0
            && direct.continuationMetrics().pendingLeaves==1,
            "direct leaf values a pending screen without projection");
        std::mt19937_64 playoutRng(20261006);
        (void)playout.evaluateLeaf(0,playoutRng);
        require(playout.continuationMetrics().projectionSteps>0,"native leaf still projects a pending screen");
    }
    {
        OocMctsResult capped; capped.aborted=true;
        capped.abortReason="ooc_depth_safety_cap_512_state_513";
        OocContinuationMetrics capCounters;
        recordSearchAbort(capped,capCounters);
        require(capCounters.continuationLimitAborts==1
            && capCounters.continuationReasons.at(capped.abortReason)==1
            && capCounters.imaginedCombats==0 && capCounters.unsupportedCombats==0
            && capCounters.supportReasons.empty(),
            "tree safety cap is a continuation abort, never a combat support failure");
        OocMctsConfig parsed; OocAdapterOptions opts{true};
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","1",parsed,opts);
        require(parsed.allowUnqualifiedRootStop,"explicit early-stop enable parsed");
        for (const auto *cap : {"1", "32", "256", "512"}) {
            applyLiveControl("STS_OOC_MCTS_MAX_DEPTH",cap,parsed,opts);
            require(parsed.maxDepth == std::stoul(cap),"safety cap override parsed");
        }
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","0",parsed,opts);
        require(!parsed.allowUnqualifiedRootStop,"early-stop rollback parsed");
        applyLiveControl("STS_OOC_MCTS_ROOT_SELECTION","q",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_COMBATS","3",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","direct",parsed,opts);
        require(opts.directLeaf && !opts.bossLeaf && !opts.constantLeaf,"direct leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","screen",parsed,opts);
        require(opts.screenLeaf && !opts.directLeaf && !opts.bossLeaf,"screen leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","boss",parsed,opts);
        require(!opts.directLeaf,"boss leaf clears direct leaf");
        applyLiveControl("STS_OOC_MCTS_CPUCT","0",parsed,opts);
        require(parsed.selectByMeanQ && parsed.cPuct == 0 && opts.leafCombats == 3 && opts.bossLeaf,
            "accepted bounded knobs");
        require(std::abs(bossLeafUtility({true,0.2f,0.5f})-0.7)<1e-7
            && bossLeafUtility({true,1,1})==0 && bossLeafUtility({true,0,1})==1,
            "boss leaf survival/HP utility");
        for (const auto &invalid : std::vector<std::pair<std::string,std::string>>{
            {"STS_OOC_MCTS_EARLY_STOP","true"},{"STS_OOC_MCTS_EARLY_STOP","2"},{"STS_OOC_MCTS_PRIOR","none"},{"STS_OOC_MCTS_TEMPERATURE","0"},
            {"STS_OOC_MCTS_CPUCT","-1"},{"STS_OOC_MCTS_WIDEN_K","nan"},
            {"STS_OOC_MCTS_WIDEN_ALPHA","1"},{"STS_OOC_MCTS_MAX_DEPTH","513"},{"STS_OOC_MCTS_MAX_DEPTH","0"},
            {"STS_OOC_MCTS_MAX_DEPTH","2.5"},{"STS_OOC_MCTS_LEAF_COMBATS","2"},
            {"STS_OOC_MCTS_LEAF_POLICY","random"},{"STS_OOC_MCTS_LEAF_VALUE","0"},
            {"STS_OOC_MCTS_ROOT_SELECTION"," q"},{"STS_OOC_MCTS_TEMPERATURE","1junk"}})
            rejects([&] { applyLiveControl(invalid.first,invalid.second,parsed,opts); });
    }
    const PathHistory *saved=t_curPath; t_curPath=&path;
    for (int i=0;i<3;++i) {
        auto probe=detachedCopy(gc); probe.curHp=10+i*30; probe.gold=50+i*150;
        OocGameContextModel leaf(probe,path);
        double direct=vStateWin(probe), adapted=leaf.leafValue(0);
        require(std::abs(direct-adapted)<1e-12,"native v_win leaf parity");
        std::cout<<"leaf_parity hp="<<probe.curHp<<" gold="<<probe.gold<<" value="<<adapted<<'\n';
    }
    t_curPath=saved;
    auto battle=detachedCopy(gc); battle.screenState=ScreenState::BATTLE;
    OocGameContextModel boundary(battle,path);
    require(!boundary.terminalValue(0) && boundary.isLeafBoundary(0),"battle is nonterminal boundary");
    rejects([&] { boundary.legalActions(0); });
    auto br=OocMctsPlanner().search(boundary,0,4);
    require(br.metrics.leafEvaluations==4 && br.rootActions.empty()
        && br.metrics.transitionSamples==0,"battle MCTS boundary");
    for(auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        battle.outcome=outcome;
        OocGameContextModel terminal(battle,path);
        require(terminal.terminalValue(0)==(outcome==GameOutcome::PLAYER_VICTORY?1.:0.),"exact terminal value");
        auto tr=OocMctsPlanner().search(terminal,0,3);
        require(tr.metrics.leafEvaluations==0 && tr.rootActions.empty(),"terminal precedence");
    }
    for (auto screen : {ScreenState::INVALID,ScreenState::CARD_SELECT}) {
        auto unsupported=detachedCopy(gc); unsupported.screenState=screen;
        OocGameContextModel leaf(unsupported,path);
        require(leaf.isLeafBoundary(0),"unsupported state boundary");
    }
    auto reward=detachedCopy(gc); reward.openCombatRewardScreen(reward.createCombatReward());
    require(reward.info.rewardsContainer.cardRewardCount>0,"reward fixture");
    auto rewardActions=v4CandidateActions(reward);
    GameAction skip(GameAction::RewardsActionType::CARD,reward.info.rewardsContainer.cardRewardCount-1,5);
    require(std::count_if(rewardActions.begin(),rewardActions.end(),[&](auto a){return a.bits==skip.bits;})==1,
        "reward skip included exactly once");
    OocGameContextModel rewards(reward,path);
    auto rewardChild=rewards.sampleSuccessor(0,sourceId(rewards,skip.bits),rng);
    require(rewards.state(rewardChild).info.rewardsContainer.cardRewardCount
        ==reward.info.rewardsContainer.cardRewardCount-1,"reward skip execution");
    // Inject an equivalent RAW result from a deterministic native exit. The
    // callback dispatches the same native reward code in both branches.
    struct FakeSampler final : CombatTransitionSampler {
        bool enabled=true, death=false, stochastic=false, escape=false;
        mutable int supportCalls=0, sampleCalls=0;
        mutable std::vector<std::uint64_t> draws;
        CombatTransitionPersistentState raw;
        CombatPredictorInputV1 expectedInput;
        CombatRuntimeSupport support(const GameContext &g, const CombatPredictorInputV1 &input) const override {
            ++supportCalls;
            require(g.screenState==ScreenState::BATTLE,"sampler prebattle screen");
            require(combatPredictorInputJson(input)==combatPredictorInputJson(expectedInput),
                    "predictor must precede battle initialization");
            return {enabled, enabled?"supported":"fake unsupported"};
        }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,
                                   std::mt19937_64 &r) const override {
            ++sampleCalls;
            bool loss=death;
            if(stochastic) { const auto draw=r(); draws.push_back(draw); loss=draw&1; }
            return {loss?CombatRuntimeSample::Outcome::DEATH:
                (escape?CombatRuntimeSample::Outcome::ESCAPE:CombatRuntimeSample::Outcome::VICTORY),raw};
        }
    };
    auto combatRoot=detachedCopy(gc);
    combatRoot.screenState=ScreenState::REST_ROOM;
    combatRoot.curRoom=Room::MONSTER;
    int regainCalls=0;
    combatRoot.regainControlAction=[&](GameContext &g) {
        ++regainCalls;
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else g.afterBattle();
    };
    const auto restActions=v4CandidateActions(combatRoot);
    require(!restActions.empty(),"combat entry rest fixture");
    const auto restAction=restActions.front();
    auto real=detachedCopy(combatRoot);
    PathHistory realPath=path; realPath.update(real);
    restAction.execute(real); realPath.update(real);
    auto fake=std::make_shared<FakeSampler>();
    // An injected sampler is never consulted for ordinary nonbattle actions.
    auto ordinary=detachedCopy(gc); ordinary.screenState=ScreenState::REST_ROOM;
    auto ordinaryExpected=detachedCopy(ordinary);
    const auto ordinaryAction=v4CandidateActions(ordinary).front();
    ordinaryAction.execute(ordinaryExpected);
    OocGameContextModel ordinaryModel(ordinary,path,fake);
    const auto ordinaryId=ordinaryModel.sampleSuccessor(0,sourceId(ordinaryModel,ordinaryAction.bits),rng);
    require(fake->supportCalls==0 && fake->sampleCalls==0
        && test::oocStateFingerprint(ordinaryModel.state(ordinaryId))==test::oocStateFingerprint(ordinaryExpected),
        "ordinary injected successor unchanged");
    fake->expectedInput=captureCombatPredictorInput(real,real.info.encounter,potionKeepValue(real));
    const auto preFingerprint=test::oocStateFingerprint(real);
    BattleContext deterministic;
    deterministic.init(real,MonsterEncounter::CULTIST);
    deterministic.player.curHp=37;
    deterministic.outcome=Outcome::PLAYER_VICTORY;
    int rawCalls=0;
    {
        CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
            ++rawCalls; fake->raw=captureCombatTransitionState(raw);
        });
        deterministic.exitBattle(real);
    }
    realPath.update(real);
    require(rawCalls==1 && regainCalls==2,"native oracle continuation once");
    regainCalls=0;
    OocGameContextModel crossed(combatRoot,path,fake);
    const auto rootFingerprint=test::oocStateFingerprint(crossed.state(0));
    const auto crossedId=crossed.sampleSuccessor(0,sourceId(crossed,restAction.bits),rng);
    sts::search::OocTreeSnapshot annotated;
    annotated.nodes.push_back({0,1,0,false,0,0,0,0});
    annotated.nodes.push_back({1,1,0,true,0,sourceId(crossed,restAction.bits),1,0});
    annotated.nodes.push_back({2,1,1,false,crossedId,0,0,0});
    annotated.edges.push_back({0,1,1,false});
    annotated.edges.push_back({1,2,1,true});
    annotateOocTree(crossed,annotated);
    require(!annotated.nodes[1].label.empty()
        && annotated.nodes[1].label!=annotated.nodes[1].key
        && annotated.nodes[2].label.find("HP ")!=std::string::npos
        && annotated.edges[1].combatModelUsed
        && annotated.edges[1].combatEncounter=="CULTIST"
        && annotated.edges[1].combatOutcome=="victory"
        && !annotated.edges[0].combatModelUsed,
        "graph annotates game action/state and only CTM-sampled edge");
    require(regainCalls==2 && fake->sampleCalls==1 && fake->supportCalls==1,
            "injected reward continuation exactly once");
    require(test::oocStateFingerprint(crossed.state(crossedId))==test::oocStateFingerprint(real),
            "injected continuation OOC/reward/RNG fingerprint");
    require(combatTransitionFingerprint(crossed.state(crossedId))==combatTransitionFingerprint(real),
            "injected persistent continuation fingerprint");
    require(crossed.pathHistory(crossedId).roomVisits==realPath.roomVisits
        && crossed.pathHistory(crossedId).lastNodeKey==realPath.lastNodeKey,"native PathHistory parity");
    require(test::oocStateFingerprint(crossed.state(0))==rootFingerprint,"combat parent unchanged");
    // A custom host may omit the callback. Its CTM input must use the same
    // neutral keep value as the native simulator, not the old zero fallback.
    auto fallbackSampler=std::make_shared<FakeSampler>();
    fallbackSampler->death=true;
    auto fallbackPre=detachedCopy(combatRoot);
    restAction.execute(fallbackPre);
    fallbackSampler->expectedInput=captureCombatPredictorInput(
        fallbackPre,fallbackPre.info.encounter,4.0);
    auto fallbackDeps=defaultOocMctsDependencies();
    fallbackDeps.potionKeepValue={};
    OocGameContextModel fallback(combatRoot,path,fallbackSampler,{},std::move(fallbackDeps));
    const auto fallbackId=fallback.sampleSuccessor(0,sourceId(fallback,restAction.bits),rng);
    require(fallbackSampler->expectedInput.globals.potionKeepValue==4.0
        && fallbackSampler->supportCalls==1 && fallbackSampler->sampleCalls==1
        && fallback.state(fallbackId).outcome==GameOutcome::PLAYER_LOSS,
        "omitted potion keep callback supplies neutral CTM input");
    // Compare an actual Smoke Bomb exit with explicit ESCAPE injection from
    // the identical prebattle origin. Includes Cleric's pre-reward maxHP gain.
    for (bool cleric : {false, true}) {
        const int savedRegainCalls = regainCalls;
        auto escapeRoot=detachedCopy(combatRoot);
        escapeRoot.potions[0]=Potion::SMOKE_BOMB;
        escapeRoot.potionCount=1;
        escapeRoot.smokeBombUsed=true; // Native battle initialization resets it.
        if (cleric) escapeRoot.relics.add({RelicId::FACE_OF_CLERIC,0});
        auto oracle=detachedCopy(escapeRoot);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        restAction.execute(oracle); oraclePath.update(oracle);
        auto escapeSampler=std::make_shared<FakeSampler>();
        escapeSampler->escape=true;
        escapeSampler->expectedInput=captureCombatPredictorInput(oracle,oracle.info.encounter,potionKeepValue(oracle));
        BattleContext smoke;
        smoke.init(oracle,MonsterEncounter::CULTIST);
        require(!smoke.smokeBombUsed,"native pre-used Smoke flag reset");
        smoke.player.curHp=37;
        smoke.drinkPotion(0);
        require(smoke.smokeBombUsed && smoke.outcome==Outcome::PLAYER_VICTORY
            && smoke.potionCount==0,"native Smoke Bomb consumes and exits");
        int escapeRawCalls=0;
        {
            CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
                ++escapeRawCalls; escapeSampler->raw=captureCombatTransitionState(raw);
            });
            smoke.exitBattle(oracle);
        }
        oraclePath.update(oracle);
        OocGameContextModel imagined(escapeRoot,path,escapeSampler);
        const auto parent=test::oocStateFingerprint(imagined.state(0));
        const auto escaped=imagined.sampleSuccessor(0,sourceId(imagined,restAction.bits),rng);
        require(escapeRawCalls==1 && escapeSampler->sampleCalls==1
            && test::oocStateFingerprint(imagined.state(escaped))==test::oocStateFingerprint(oracle)
            && combatTransitionFingerprint(imagined.state(escaped))==combatTransitionFingerprint(oracle),
            "ESCAPE exact native OOC/persistent/all-RNG continuation parity");
        require(oracle.screenState==ScreenState::MAP_SCREEN && !oracle.smokeBombUsed
            && imagined.pathHistory(escaped).roomVisits==oraclePath.roomVisits
            && imagined.pathHistory(escaped).lastNodeKey==oraclePath.lastNodeKey
            && test::oocStateFingerprint(imagined.state(0))==parent,
            "ESCAPE no rewards, native PathHistory, unchanged parent");
        escapeSampler->escape=false;
        OocGameContextModel mislabeled(escapeRoot,path,escapeSampler);
        rejects([&] { mislabeled.sampleSuccessor(0,sourceId(mislabeled,restAction.bits),rng); });
        auto boss=detachedCopy(escapeRoot);
        boss.info.encounter=MonsterEncounter::SLIME_BOSS;
        rejects([&] { applySampledCombatExit(boss,{CombatRuntimeSample::Outcome::ESCAPE,escapeSampler->raw}); });
        BattleContext blocked;
        blocked.init(boss,MonsterEncounter::SLIME_BOSS);
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && !blocked.smokeBombUsed
            && blocked.potions[0]==Potion::SMOKE_BOMB && blocked.potionCount==1,
            "boss blocks Smoke Bomb without consuming it or accepting ESCAPE");
        blocked.init(escapeRoot,MonsterEncounter::CULTIST);
        blocked.player.buff<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && blocked.potionCount==1,
            "Surrounded blocks Smoke Bomb without consumption");
        blocked.player.removeStatus<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.smokeBombUsed && blocked.potionCount==0,
            "removing Surrounded allows escape later in the same combat");
        regainCalls=savedRegainCalls;
    }
    std::cout<<"smoke_escape_oracle native_origin=identical cleric=both raw_outcome=ESCAPE parity=exact\n";
    {
        // Phase-0 Smoke Bomb masking (#370): the CTM sees an empty slot, the
        // Smoke Bomb returns unused, and a potion generated into its slot is
        // dropped. States without a Smoke Bomb pass through unchanged.
        struct RecordingSampler final : CombatTransitionSampler {
            mutable std::vector<std::array<int,5>> seenPotions;
            mutable std::vector<int> seenInputCounts;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &p) const override {
                record(g,p);
                for (auto potion : g.potions)
                    if (potion==Potion::SMOKE_BOMB) return {false,"smoke_bomb"};
                return {true,"supported"};
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &p,
                    std::mt19937_64 &) const override {
                record(g,p);
                CombatRuntimeSample result{CombatRuntimeSample::Outcome::VICTORY,
                    captureCombatTransitionState(g)};
                result.rawPost.potions[1]=static_cast<int>(Potion::FIRE_POTION); // generated
                return result;
            }
            void record(const GameContext &g,const CombatPredictorInputV1 &p) const {
                std::array<int,5> potions{};
                for (int i=0;i<5;++i) potions[i]=static_cast<int>(g.potions[i]);
                seenPotions.push_back(potions);
                seenInputCounts.push_back(p.globals.potionCount);
            }
        };
        auto recording=std::make_shared<RecordingSampler>();
        const auto wrapped=maskInitialSmokeBomb(recording);
        auto withSmoke=detachedCopy(gc);
        withSmoke.potionCapacity=3;
        withSmoke.potions={Potion::BLOCK_POTION,Potion::SMOKE_BOMB,Potion::EMPTY_POTION_SLOT,
            Potion::EMPTY_POTION_SLOT,Potion::EMPTY_POTION_SLOT};
        withSmoke.potionCount=2;
        withSmoke.info.encounter=MonsterEncounter::CULTIST;
        const auto input=captureCombatPredictorInput(withSmoke,MonsterEncounter::CULTIST,4.0);
        require(wrapped->support(withSmoke,input).supported,"masked Smoke Bomb combat is supported");
        std::mt19937_64 maskRng(5);
        const auto sampled=wrapped->sample(withSmoke,input,maskRng);
        require(recording->seenPotions.back()[1]==static_cast<int>(Potion::EMPTY_POTION_SLOT)
            && recording->seenInputCounts.back()==1,"CTM sees the Smoke Bomb slot as empty");
        require(sampled.outcome==CombatRuntimeSample::Outcome::VICTORY
            && sampled.rawPost.potions[1]==static_cast<int>(Potion::SMOKE_BOMB)
            && sampled.rawPost.potions[0]==static_cast<int>(Potion::BLOCK_POTION)
            && sampled.rawPost.potionCount==2 && !sampled.rawPost.smokeBombUsed,
            "Smoke Bomb returns unused and displaces a generated potion");
        const auto prepared=wrapped->prepare(withSmoke,input);
        require(prepared->support().supported
            && prepared->sample(maskRng).rawPost.potions[1]==static_cast<int>(Potion::SMOKE_BOMB),
            "prepared path masks and restores the Smoke Bomb");
        auto noSmoke=detachedCopy(withSmoke);
        noSmoke.potions[1]=Potion::EMPTY_POTION_SLOT; noSmoke.potionCount=1;
        const auto plain=captureCombatPredictorInput(noSmoke,MonsterEncounter::CULTIST,4.0);
        const auto passed=wrapped->sample(noSmoke,plain,maskRng);
        require(passed.rawPost.potions[1]==static_cast<int>(Potion::FIRE_POTION),
            "states without a Smoke Bomb pass through unchanged");
        std::cout<<"smoke_bomb_mask masked=empty_slot restored=unused generated=dropped\n";
    }
    {
        // Phase-0 masking (#370): the CTM sees an empty slot for an initial
        // Smoke Bomb, and the Smoke Bomb returns unused after the combat.
        struct RecordingSampler final : CombatTransitionSampler {
            mutable std::vector<int> seenPotions;
            mutable int seenCount = -1, calls = 0;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &) const override {
                const bool smoke=std::any_of(g.potions.begin(),g.potions.end(),[](auto p){return p==Potion::SMOKE_BOMB;});
                return {!smoke, smoke ? "smoke_bomb" : "supported"};
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &in,
                    std::mt19937_64 &) const override {
                ++calls; seenCount=in.globals.potionCount; seenPotions.clear();
                for (const auto &token : in.potions) seenPotions.push_back(token.potionId);
                CombatRuntimeSample result;
                result.outcome=CombatRuntimeSample::Outcome::VICTORY;
                result.rawPost=captureCombatTransitionState(g);
                result.rawPost.potions[1]=int(Potion::FIRE_POTION); // generated into the masked slot
                result.rawPost.potionCount=2;
                return result;
            }
        };
        auto recorder=std::make_shared<RecordingSampler>();
        const auto masked=maskInitialSmokeBomb(recorder);
        auto held=detachedCopy(gc);
        held.potions.fill(Potion::EMPTY_POTION_SLOT);
        held.potions[0]=Potion::BLOCK_POTION; held.potions[1]=Potion::SMOKE_BOMB; held.potionCount=2;
        held.info.encounter=MonsterEncounter::CULTIST;
        const auto input=captureCombatPredictorInput(held,MonsterEncounter::CULTIST,4.0);
        require(!recorder->support(held,input).supported && masked->support(held,input).supported,
            "Smoke Bomb masking makes the combat supported");
        std::mt19937_64 maskRng(5);
        for (const auto &draw : {masked->sample(held,input,maskRng), masked->prepare(held,input)->sample(maskRng)}) {
            require(recorder->seenCount==1 && recorder->seenPotions.at(1)==int(Potion::EMPTY_POTION_SLOT)
                && recorder->seenPotions.at(0)==int(Potion::BLOCK_POTION),
                "CTM sees the Smoke Bomb slot as empty");
            require(draw.outcome==CombatRuntimeSample::Outcome::VICTORY
                && draw.rawPost.potions[1]==int(Potion::SMOKE_BOMB) && draw.rawPost.potionCount==2
                && !draw.rawPost.smokeBombUsed,
                "Smoke Bomb returns unused and replaces a potion generated into its slot");
        }
        auto plain=detachedCopy(held); plain.potions[1]=Potion::EMPTY_POTION_SLOT; plain.potionCount=1;
        const auto plainInput=captureCombatPredictorInput(plain,MonsterEncounter::CULTIST,4.0);
        const auto passed=masked->sample(plain,plainInput,maskRng);
        require(recorder->seenCount==1 && passed.rawPost.potions[1]==int(Potion::FIRE_POTION),
            "states without a Smoke Bomb pass through unchanged");
        auto used=detachedCopy(held); used.smokeBombUsed=true;
        require(!masked->support(used,captureCombatPredictorInput(used,MonsterEncounter::CULTIST,4.0)).supported,
            "pre-used Smoke Bomb state stays unsupported");
    }
    fake->enabled=false; regainCalls=0;
    OocGameContextModel unsupportedCombat(combatRoot,path,fake);
    const auto unsupportedId=unsupportedCombat.sampleSuccessor(0,sourceId(unsupportedCombat,restAction.bits),rng);
    require(fake->sampleCalls==1 && regainCalls==1 && unsupportedCombat.isLeafBoundary(unsupportedId)
        && test::oocStateFingerprint(unsupportedCombat.state(unsupportedId))==preFingerprint,
        "unsupported combat retains exact battle leaf");
    OocGameContextModel disabledCombat(combatRoot,path);
    const auto disabledId=disabledCombat.sampleSuccessor(0,sourceId(disabledCombat,restAction.bits),rng);
    require(test::oocStateFingerprint(disabledCombat.state(disabledId))==preFingerprint
        && disabledCombat.pathHistory(disabledId).roomVisits==unsupportedCombat.pathHistory(unsupportedId).roomVisits,
        "no sampler combat behavior unchanged");
    fake->enabled=true; fake->death=true; regainCalls=0;
    OocGameContextModel deathCombat(combatRoot,path,fake);
    const auto deathId=deathCombat.sampleSuccessor(0,sourceId(deathCombat,restAction.bits),rng);
    require(regainCalls==1 && deathCombat.terminalValue(deathId)==0
        && deathCombat.state(deathId).screenState==ScreenState::BATTLE,
        "death terminal without reward continuation");
    fake->death=false; fake->stochastic=true;
    std::mt19937_64 plannerRng(991), expectedRng(991);
    OocGameContextModel chanceCombat(combatRoot,path,fake);
    for(int i=0;i<8;++i) {
        const auto expectedDraw=expectedRng();
        const auto sampleId=chanceCombat.sampleSuccessor(0,sourceId(chanceCombat,restAction.bits),plannerRng);
        require(fake->draws.back()==expectedDraw,"independent supplied planner RNG draw");
        require(bool(chanceCombat.terminalValue(sampleId))==bool(expectedDraw&1),
                "chance outcome not value selected");
    }
    // Restrict the test root to the entry action so every planner chance
    // expansion exercises combat without unrelated rest/select decisions.
    struct SingleEntryModel final : OocGenerativeModel {
        OocGameContextModel &adapter;
        OocActionId entry;
        SingleEntryModel(OocGameContextModel &a,OocActionId e):adapter(a),entry(e) {}
        std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
        bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
        std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
            require(id==0,"single-entry planner must stop at depth one"); return {{entry,1.0}};
        }
        OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
            return adapter.sampleSuccessor(id,a,r);
        }
        double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
    };
    fake->draws.clear();
    const auto samplesBefore=fake->sampleCalls;
    OocGameContextModel plannerCombat(combatRoot,path,fake);
    SingleEntryModel entryModel(plannerCombat,sourceId(plannerCombat,restAction.bits));
    OocMctsConfig chanceConfig; chanceConfig.seed=12345;
    OocMctsPlanner chancePlanner(chanceConfig);
    const auto chanceResult=chancePlanner.search(entryModel,0,32);
    std::mt19937_64 expectedChanceRng(chanceConfig.seed);
    std::vector<std::uint64_t> expectedChanceDraws;
    for(std::uint64_t visit=1;visit<=32;++visit) {
        if(expectedChanceDraws.size()<chancePlanner.chanceWideningLimit(visit))
            expectedChanceDraws.push_back(expectedChanceRng());
        else {
            std::uniform_int_distribution<std::size_t> choose(0,expectedChanceDraws.size()-1);
            (void)choose(expectedChanceRng);
        }
    }
    require(fake->draws==expectedChanceDraws && std::set<std::uint64_t>(fake->draws.begin(),fake->draws.end()).size()==fake->draws.size(),
            "planner expansions receive independent RNG draws with unbiased particle reuse");
    const auto &chanceMetrics=chanceResult.metrics;
    require(chanceMetrics.simulations==32 && chanceMetrics.chanceNodes==1
        && chanceMetrics.transitionSamples==expectedChanceDraws.size()
        && chanceMetrics.outcomeParticles==chanceMetrics.transitionSamples
        && chanceMetrics.decisionNodes==chanceMetrics.outcomeParticles+1
        && chanceMetrics.maxDepthReached==1
        && fake->sampleCalls-samplesBefore==int(chanceMetrics.transitionSamples)
        && chanceResult.rootActions.size()==1 && chanceResult.rootActions.front().visits==32,
        "combat planner progressive widening particle metrics preserved");
    // Native continuation may enter another battle (e.g. chained battles).
    // The adapter crosses one combat boundary per primitive transition.
    fake->stochastic=false;
    auto chainedRoot=detachedCopy(combatRoot);
    int chainContinuations=0;
    chainedRoot.regainControlAction=[&](GameContext &g) {
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else { ++chainContinuations; g.enterBattle(MonsterEncounter::CULTIST); }
    };
    const auto chainSamplesBefore=fake->sampleCalls;
    OocGameContextModel chainedCombat(chainedRoot,path,fake);
    const auto chainedId=chainedCombat.sampleSuccessor(0,sourceId(chainedCombat,restAction.bits),rng);
    require(chainContinuations==1 && fake->sampleCalls==chainSamplesBefore+1
        && chainedCombat.state(chainedId).screenState==ScreenState::BATTLE
        && chainedCombat.isLeafBoundary(chainedId) && !chainedCombat.terminalValue(chainedId),
        "second battle continuation remains leaf without recursive sampling");
    const auto chainedResult=OocMctsPlanner().search(chainedCombat,chainedId,4);
    require(chainedResult.metrics.transitionSamples==0 && chainedResult.metrics.leafEvaluations==4
        && fake->sampleCalls==chainSamplesBefore+1,"chained battle planner retains leaf seam");
    std::cout<<"combat_planner_chance simulations="<<chanceMetrics.simulations
        <<" particles="<<chanceMetrics.outcomeParticles<<" samples="<<chanceMetrics.transitionSamples
        <<" depth="<<chanceMetrics.maxDepthReached<<" chained_battle=leaf"<<'\n';
    std::cout<<"combat_adapter_oracle raw_calls="<<rawCalls
        <<" fingerprint=exact path_history=exact stochastic_draws="<<fake->draws.size()<<'\n';
    auto result=OocMctsPlanner().search(model,0,32);
    double sum=0; for(auto a:result.rootActions) sum+=a.prior;
    require(std::abs(sum-1)<1e-12,"normalized priors");
    auto best=std::max_element(logits.begin(),logits.end());
    auto priorBest=std::max_element(result.rootActions.begin(),result.rootActions.end(),[](auto a,auto b){return a.prior<b.prior;});
    require(priorBest->id==legal[best-logits.begin()].id,"policy prior ordering");
    for(auto a:result.rootActions) {
        auto it=std::find_if(legal.begin(),legal.end(),[&](auto l){return l.id==a.id;});
        require(std::isfinite(a.prior) && a.prior>=0,"finite nonnegative priors");
        std::cout << "MAP(x=" << GameAction(a.id).getIdx1() << ")";
        std::cout<<" bits="<<a.id<<" logit="<<logits[it-legal.begin()]<<" prior="<<a.prior
            <<" visits="<<a.visits<<" Q="<<a.q<<'\n';
    }
    auto m=result.metrics;
    std::cout<<"selected="<<result.selectedAction.value_or(0xFFFFFFFFu)<<" simulations="<<m.simulations
        <<" decision_nodes="<<m.decisionNodes<<" chance_nodes="<<m.chanceNodes
        <<" particles="<<m.outcomeParticles<<" samples="<<m.transitionSamples
        <<" leaf_evaluations="<<m.leafEvaluations<<" max_depth="<<m.maxDepthReached<<'\n';
    // Rich features cannot see pending gold. Checkpoint projection must collect
    // it on a detached copy, and match the existing policy's completed oracle.
    std::vector<float> pendingFeatures;
    for (int amount : {1}) {
        auto pendingGold=detachedCopy(reward);
        auto &container=pendingGold.info.rewardsContainer;
        container.goldRewardCount=1; container.gold[0]=amount;
        container.cardRewardCount=container.relicCount=container.potionCount=0;
        container.emeraldKey=container.sapphireKey=false;
        collectForcedRewardGold(pendingGold);
        const auto fingerprint=test::oocStateFingerprint(pendingGold);
        const auto features=richFeatureVec(pendingGold);
        if (pendingFeatures.empty()) pendingFeatures=features;
        else require(features==pendingFeatures,"rich model cannot see pending reward contents fixture");
        auto completed=detachedCopy(pendingGold);
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<16 && completed.screenState!=ScreenState::MAP_SCREEN;++step)
            runFullRunOocPolicyStep(completed,oracleAgent,false,true);
        require(completed.screenState==ScreenState::MAP_SCREEN && completed.gold==pendingGold.gold,
            "pending gold oracle reaches checkpoint after collection");
        OocGameContextModel projected(pendingGold,path,{}, {true});
        rejects([&] { projected.leafValue(0); });
        std::mt19937_64 projectionRng(543);
        const auto savedPath=t_curPath;
        t_curPath=&projected.pathHistory(0);
        const auto oracleValue=vStateWinNative(completed);
        t_curPath=savedPath;
        const auto projectedValue=projected.evaluateLeaf(0,projectionRng);
        require(projectedValue==oracleValue,
            "pending reward projection value differs from resolved oracle");
        require(projected.continuationMetrics().pendingLeaves==1
            && projected.continuationMetrics().projectionSteps>=1,
            "pending reward projection did not retain continuation accounting");
        require(test::oocStateFingerprint(projected.state(0))==fingerprint
            && test::oocStateFingerprint(pendingGold)==fingerprint && t_curPath==savedPath,
            "pending reward projection mutated canonical root or caller path");
    }
    // All pending screen families are evaluated only after the same policy
    // continuation. This also covers selectors outside MCTS-owned decisions.
    for (int family=0;family<5;++family) {
        auto pending=detachedCopy(gc);
        if (family==0) { pending.screenState=ScreenState::SHOP_ROOM; pending.info.shop.setup(pending); }
        if (family==1) { pending.screenState=ScreenState::EVENT_SCREEN; pending.curEvent=Event::BIG_FISH;
            pending.info.hpAmount0=20; pending.info.hpAmount1=5; }
        if (family==2) pending.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        if (family==3) pending.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        if (family==4) pending=detachedCopy(reward);
        const auto beforePending=test::oocStateFingerprint(pending);
        auto completed=detachedCopy(pending);
        PathHistory completedPath=path; completedPath.update(completed);
        const auto previousPath=t_curPath; t_curPath=&completedPath;
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<64 && completed.screenState!=ScreenState::MAP_SCREEN;++step) {
            runFullRunOocPolicyStep(completed,oracleAgent,false,true); completedPath.update(completed);
        }
        require(completed.screenState==ScreenState::MAP_SCREEN,"pending screen oracle reaches checkpoint");
        const double expectedValue=vStateWinNative(completed); t_curPath=previousPath;
        OocGameContextModel projected(pending,path,{}, {true});
        int observerCalls=0;
        auto savedObserver=std::move(sts::search::g_onGameActionExecute);
        sts::search::g_onGameActionExecute=[&](std::uint32_t,const GameContext *) { ++observerCalls; };
        t_oocStrategicTraceRows="live trace sentinel";
        const auto savedRows=t_oocStrategicTraceRows;
        std::mt19937_64 projectionRng(543);
        require(projected.evaluateLeaf(0,projectionRng)==expectedValue
            && test::oocStateFingerprint(pending)==beforePending && observerCalls==0
            && t_oocStrategicTraceRows==savedRows && t_curPath==previousPath,
            "pending screen projection matches oracle without live observer or bookkeeping mutation");
        sts::search::g_onGameActionExecute=std::move(savedObserver);
        t_oocStrategicTraceRows.clear();
    }
    // Controlled map fixtures prove horizon counting without native combat/search.
    struct HorizonSampler final : CombatTransitionSampler {
        mutable unsigned calls = 0;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            ++calls;
            return {CombatRuntimeSample::Outcome::VICTORY,captureCombatTransitionState(g)};
        }
    };
    for (unsigned horizon : {1u,3u}) {
        auto horizonRoot = detachedCopy(gc);
        for (auto &row : horizonRoot.map->nodes) for (auto &node : row) node.room = Room::MONSTER;
        auto sampler = std::make_shared<HorizonSampler>();
        OocAdapterOptions opts{true}; opts.leafCombats = horizon; opts.constantLeaf = true; opts.uniformLeafPolicy = true;
        OocGameContextModel projected(horizonRoot,path,sampler,opts);
        std::mt19937_64 projectionRng(912);
        const auto before = test::oocStateFingerprint(horizonRoot);
        require(projected.evaluateLeaf(0,projectionRng) == .5 && sampler->calls == horizon
            && projected.continuationMetrics().imaginedCombats == horizon
            && projected.continuationMetrics().projectionSteps >= horizon*2
            && test::oocStateFingerprint(horizonRoot) == before,
            "uniform continuation completes exact additional combat horizon and preserves root");
    }
    {
        // Inject the bounded-continuation exception after a genuine successful
        // adapter surrogate draw; isolate root-abort accounting from native exits.
        auto root=detachedCopy(gc);
        for (auto &row : root.map->nodes) for (auto &node : row) node.room=Room::MONSTER;
        auto sampler=std::make_shared<HorizonSampler>();
        OocGameContextModel adapter(root,path,sampler,{true});
        struct BoundModel final : OocGenerativeModel {
            OocGameContextModel &adapter;
            explicit BoundModel(OocGameContextModel &a):adapter(a) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override { return adapter.sampleSuccessor(id,a,r); }
            double leafValue(OocStateId) const override { throw OocSearchUnsupported("continuation_step_limit_1024"); }
        } bounded(adapter);
        OocMctsConfig config;
        const auto result=OocMctsPlanner(config).search(bounded,0,1);
        auto counters=adapter.continuationMetrics();
        recordSearchAbort(result,counters);
        const auto samples=adapter.combatSamples();
        require(result.aborted && !result.selectedAction && result.rootActions.empty()
            && result.abortReason=="continuation_step_limit_1024"
            && counters.continuationLimitAborts==1
            && counters.continuationReasons.at(result.abortReason)==1
            && counters.unsupportedCombats==0 && counters.supportReasons.empty()
            && counters.imaginedCombats==samples && samples==1 && sampler->calls==1,
            "continuation limit abort preserves honest successful combat and separate reason accounting");
    }
    {
        auto pending = detachedCopy(gc); pending.screenState = ScreenState::EVENT_SCREEN;
        pending.curEvent = Event::BIG_FISH; pending.info.hpAmount0 = 20; pending.info.hpAmount1 = 5;
        auto oracle = detachedCopy(pending);
        std::mt19937_64 oracleRng(919), projectionRng(919);
        oracleRng(); // Existing continuation agent seeding consumes one search draw.
        const auto actions = v4CandidateActions(oracle);
        require(v4DecisionSupported(oracle) && actions.size() > 1, "uniform event fixture legal alternatives");
        actions[std::uniform_int_distribution<std::size_t>(0,actions.size()-1)(oracleRng)].execute(oracle);
        ScumSearchAgent2 oracleAgent;
        for (int step=0; step<64 && oracle.screenState != ScreenState::MAP_SCREEN; ++step)
            runFullRunOocPolicyStep(oracle,oracleAgent,false,true);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        const auto previousPath=t_curPath; t_curPath=&oraclePath;
        const double expected=vStateWinNative(oracle); t_curPath=previousPath;
        OocAdapterOptions opts{true}; opts.uniformLeafPolicy=true;
        OocGameContextModel projected(pending,path,{},opts);
        require(projected.evaluateLeaf(0,projectionRng)==expected,
            "uniform supported decision executes correct primitive and resolves checkpoint");
    }
    // A single unsupported combat invalidates the entire root; never choose
    // from partial Q, assign a scalar penalty, or call a real combat backend.
    fake->enabled=false;
    OocGameContextModel unsupportedRoot(combatRoot,path,fake,{true});
    const auto unsupportedBefore=test::oocStateFingerprint(unsupportedRoot.state(0));
    const auto samplesBeforeAbort=fake->sampleCalls;
    std::mt19937_64 adapterRng(77), untouchedRng(77);
    rejects([&] { unsupportedRoot.sampleSuccessor(0,sourceId(unsupportedRoot,restAction.bits),adapterRng); });
    require(unsupportedRoot.continuationMetrics().imaginedCombats==1
        && unsupportedRoot.continuationMetrics().unsupportedCombats==1
        && unsupportedRoot.continuationMetrics().supportReasons.at("fake unsupported")==1
        && fake->sampleCalls==samplesBeforeAbort && adapterRng==untouchedRng
        && test::oocStateFingerprint(unsupportedRoot.state(0))==unsupportedBefore,
        "unsupported input aborts before any draw/combat/value and preserves root");
    OocGameContextModel unsupportedPlanner(combatRoot,path,fake,{true});
    SingleEntryModel unsupportedEntry(unsupportedPlanner,sourceId(unsupportedPlanner,restAction.bits));
    const auto aborted=OocMctsPlanner().search(unsupportedEntry,0,128);
    require(aborted.aborted && !aborted.selectedAction && aborted.rootActions.empty()
        && aborted.metrics.simulations==0 && aborted.metrics.simulationAttempts==1
        && aborted.abortReason=="fake unsupported","unsupported root returns no partial action with counted attempt");
    // A surprise UNSUPPORTED sample uses the same whole-root contract.
    struct UnsupportedDraw final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override { return {}; }
    };
    OocGameContextModel unsupportedDraw(combatRoot,path,std::make_shared<UnsupportedDraw>(),{true});
    SingleEntryModel unsupportedDrawEntry(unsupportedDraw,sourceId(unsupportedDraw,restAction.bits));
    const auto abortedDraw=OocMctsPlanner().search(unsupportedDrawEntry,0,128);
    require(abortedDraw.aborted && !abortedDraw.selectedAction
        && unsupportedDraw.continuationMetrics().supportReasons.at("sample_returned_unsupported")==1,
        "unsupported sample cannot escape into a BATTLE scalar leaf");
    // Even an optional configured leaf policy cannot bypass the surrogate.
    const bool beforeDisallow=sts::search::g_disallowImaginedCombat;
    {
        ImaginedScope scope;
        ScumSearchAgent2 forbiddenAgent; BattleContext forbiddenBattle;
        auto detachedBattle=detachedCopy(battle);
        rejects([&] { forbiddenAgent.playoutBattle(detachedBattle,forbiddenBattle); });
    }
    require(sts::search::g_disallowImaginedCombat==beforeDisallow,"surrogate-only guard restores real combat permission");
    OocGameContextModel deterministicOoc(ordinary,path,{}, {true});
    const auto deterministicId=deterministicOoc.sampleSuccessor(0,sourceId(deterministicOoc,ordinaryAction.bits),adapterRng);
    const auto rngBeforeCache=adapterRng;
    require(deterministicOoc.isDeterministicTransition(0,sourceId(deterministicOoc,ordinaryAction.bits))
        && deterministicOoc.sampleSuccessor(0,sourceId(deterministicOoc,ordinaryAction.bits),adapterRng)==deterministicId
        && adapterRng==rngBeforeCache,"deterministic OOC child reused without RNG draw");
    std::cout << "corrected_continuations reward_oracle=exact unsupported_root=V4 unsupported_sample=V4 native_imagination=forbidden deterministic_reuse=exact\n";
    // No fallback even if availability changes after construction.
    bool policyOk=g_oocStrategicTokNet.ok; g_oocStrategicTokNet.ok=false;
    rejects([&] { OocGameContextModel unavailable(gc,path); });
    g_oocStrategicTokNet.ok=policyOk;
    // Exercise the same live dispatch seam with a stateless lethal imagined
    // sampler. Every selected first-row map action must leave live combat pending.
    struct ImaginedDeath final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {true, "test supported"};
        }
        CombatRuntimeSample sample(const GameContext &, const CombatPredictorInputV1 &,
                                   std::mt19937_64 &) const override {
            return {CombatRuntimeSample::Outcome::DEATH, {}};
        }
    };
    struct LiveConfigScope {
        bool enabled = liveEnabled;
        std::uint64_t simulations = liveSimulations;
        std::shared_ptr<const CombatTransitionSampler> sampler = liveSampler;
        sts::search::OocMctsConfig config = liveConfig;
        OocAdapterOptions options = liveOptions;
        ~LiveConfigScope() { liveEnabled=enabled; liveSimulations=simulations; liveSampler=sampler;
            liveConfig=config; liveOptions=options; }
    } liveScope;
    auto live=GameContext(CharacterClass::IRONCLAD, 42, 0);
    live.screenState=ScreenState::MAP_SCREEN;
    live.curEvent=Event::INVALID;
    live.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    for (auto &node : live.map->nodes[0]) node.room=Room::MONSTER;
    PathHistory livePath; livePath.update(live);
    const auto before=test::oocStateFingerprint(live);
    const auto beforePath=livePath;
    LiveOocMctsMetrics offMetrics;
    liveEnabled=false; liveSampler.reset();
    require(!oocMctsPolicyStep(live,livePath,42,7,offMetrics)
        && offMetrics.decisions==1 && offMetrics.search.simulations==0
        && test::oocStateFingerprint(live)==before, "OFF dispatch has no search/model/RNG use");
    struct AlwaysUnsupported final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {false,"test unsupported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            throw std::runtime_error("unsupported sampler must not draw");
        }
    };
    liveEnabled=true; liveSimulations=128; liveSampler=std::make_shared<AlwaysUnsupported>();
    LiveOocMctsMetrics unsupportedMetrics;
    require(!oocMctsPolicyStep(live,livePath,42,7,unsupportedMetrics)
        && unsupportedMetrics.fallback==1 && unsupportedMetrics.supportAborts==1
        && unsupportedMetrics.owned==0 && unsupportedMetrics.search.trivialRootBypasses==0
        && unsupportedMetrics.search.simulationAttempts==1
        && unsupportedMetrics.search.simulations==0 && unsupportedMetrics.continuation.unsupportedCombats==1
        && unsupportedMetrics.continuation.supportReasons.at("test unsupported")==1
        && test::oocStateFingerprint(live)==before && !sts::search::g_disallowImaginedCombat,
        "unsupported live search returns untouched decision to existing V4 with reconciled abort metrics");
    auto sole=detachedCopy(live);
    int firstNode=-1;
    for (auto &node : sole.map->nodes[0]) {
        if (firstNode < 0 && node.edgeCount > 0) firstNode=node.x;
        else node.edgeCount=0;
    }
    PathHistory solePath; solePath.update(sole);
    const auto soleCandidates=v4CandidateActions(sole);
    require(soleCandidates.size()==1,"sole map candidate fixture");
    OocGameContextModel soleModel(sole,solePath,liveSampler,liveOptions);
    const auto soleAction=soleModel.soleLegalAction(0);
    const auto soleBypass=searchWithSoleRootShortcut(soleModel,liveConfig,soleAction,128);
    require(soleAction && soleBypass.selectedAction==soleAction && !soleBypass.aborted
        && soleBypass.metrics.trivialRootBypasses==1 && soleBypass.metrics.simulations==0
        && soleBypass.metrics.simulationAttempts==0 && soleBypass.metrics.transitionSamples==0
        && soleBypass.metrics.leafEvaluations==0 && soleModel.combatSamples()==0
        && soleBypass.rootActions.size()==1 && soleBypass.rootActions[0].prior==1.0
        && soleBypass.rootActions[0].visits==0,
        "sole map root bypasses unsupported hypothetical continuation");
    auto profileConfig = liveConfig;
    profileConfig.profileSearch = true;
    const auto profiledSole = searchWithSoleRootShortcut(soleModel, profileConfig, soleAction, 128);
    require(profiledSole.selectedAction == soleBypass.selectedAction
        && profiledSole.metrics.trivialRootBypasses == 1
        && profiledSole.metrics.simulationAttempts == 0
        && profiledSole.metrics.expandedActionHistogram.empty(),
        "branch profiling preserves sole-root bypass and zero work");
    auto soleWithPotions=detachedCopy(sole);
    soleWithPotions.potions[0]=Potion::FIRE_POTION;
    soleWithPotions.potionCount=1;
    OocGameContextModel potionModel(soleWithPotions,solePath,liveSampler,liveOptions);
    const auto potionAction=potionModel.soleLegalAction(0);
    const auto potionBypass=searchWithSoleRootShortcut(potionModel,liveConfig,potionAction,128);
    require(potionAction && potionBypass.selectedAction==potionAction
        && potionBypass.metrics.trivialRootBypasses==1
        && potionBypass.metrics.simulationAttempts==0 && potionModel.combatSamples()==0,
        "held potion does not create a competing standalone discard action");
    auto observedConfig=liveConfig;
    observedConfig.observeRootLock=true;
    OocGameContextModel observedSole(sole,solePath,liveSampler,liveOptions);
    const auto observedSearch=searchWithSoleRootShortcut(observedSole,observedConfig,
        observedSole.soleLegalAction(0),128);
    require(observedSearch.metrics.trivialRootBypasses==0
        && observedSearch.metrics.simulationAttempts>0,
        "root-lock observer searches a forced root");
    auto checkpointConfig=liveConfig;
    checkpointConfig.rootCheckpointSimulations={1};
    OocGameContextModel checkpointSole(sole,solePath,liveSampler,liveOptions);
    const auto checkpointSearch=searchWithSoleRootShortcut(checkpointSole,checkpointConfig,
        checkpointSole.soleLegalAction(0),128);
    require(checkpointSearch.metrics.trivialRootBypasses==0
        && checkpointSearch.metrics.simulationAttempts>0,
        "explicit root checkpoint searches a forced root");
    const auto soleSearch=OocMctsPlanner(liveConfig).search(soleModel,0,128);
    require(soleSearch.aborted && soleSearch.metrics.simulationAttempts==1,
        "normal sole-action search aborts after entering unsupported combat");
    auto solePrimitive=detachedCopy(sole), soleFallback=detachedCopy(sole);
    soleCandidates.front().execute(solePrimitive);
    ScumSearchAgent2 soleAgent;
    runFullRunOocPolicyStep(soleFallback,soleAgent,false,true);
    require(test::oocStateFingerprint(soleFallback)==test::oocStateFingerprint(solePrimitive),
        "sole candidate equals original whole-root fallback primitive including live RNG");
    LiveOocMctsMetrics soleMetrics;
    const auto soleBefore=test::oocStateFingerprint(sole);
    require(oocMctsPolicyStep(sole,solePath,42,7,soleMetrics)
        && soleMetrics.search.trivialRootBypasses==1 && soleMetrics.search.simulations==0
        && soleMetrics.search.simulationAttempts==0 && soleMetrics.search.transitionSamples==0
        && soleMetrics.search.leafEvaluations==0 && soleMetrics.combatSamples==0
        && soleMetrics.supportAborts==0 && soleMetrics.fallback==0 && soleMetrics.owned==1
        && test::oocStateFingerprint(sole)==test::oocStateFingerprint(solePrimitive)
        && test::oocStateFingerprint(sole)!=soleBefore,
        "sole map root executes its exact primitive without search or fallback");

    auto makeRewardRoot = [] {
        auto root = GameContext(CharacterClass::IRONCLAD, 84321, 0);
        root.screenState = ScreenState::REWARDS;
        root.info.rewardsContainer.clear();
        root.info.rewardsContainer.addGold(25);
        root.regainControlAction = [](GameContext &g) {
            g.screenState = ScreenState::MAP_SCREEN;
            g.regainControlAction = nullptr;
        };
        return root;
    };
    liveEnabled = true;
    liveSimulations = 128;
    liveSampler = std::make_shared<AlwaysUnsupported>();
    const auto optionsBeforeGoldRoots = liveOptions;
    liveOptions = {};
    auto goldOnly = makeRewardRoot();
    const int goldOnlyBefore = goldOnly.gold;
    PathHistory goldOnlyPath;
    goldOnlyPath.update(goldOnly);
    LiveOocMctsMetrics goldOnlyMetrics;
    const bool goldOnlyHandled = oocMctsPolicyStep(goldOnly, goldOnlyPath, 42, 9, goldOnlyMetrics);
    if (!(goldOnlyHandled && goldOnly.gold == goldOnlyBefore + 25
            && goldOnly.info.rewardsContainer.goldRewardCount == 0
            && goldOnly.screenState == ScreenState::MAP_SCREEN
            && goldOnlyMetrics.search.trivialRootBypasses == 1
            && goldOnlyMetrics.search.simulations == 0
            && goldOnlyMetrics.search.simulationAttempts == 0))
        throw std::runtime_error("live native gold-only root: handled=" + std::to_string(goldOnlyHandled)
            + " gold=" + std::to_string(goldOnly.gold)
            + " remaining=" + std::to_string(goldOnly.info.rewardsContainer.goldRewardCount)
            + " screen=" + std::to_string(int(goldOnly.screenState))
            + " bypass=" + std::to_string(goldOnlyMetrics.search.trivialRootBypasses)
            + " simulations=" + std::to_string(goldOnlyMetrics.search.simulations)
            + " fallback=" + std::to_string(goldOnlyMetrics.fallback));

    auto goldAndCard = makeRewardRoot();
    const int goldAndCardBefore = goldAndCard.gold;
    const int goldAndCardDeckBefore = goldAndCard.deck.size();
    CardReward meaningful;
    meaningful.push_back(Card(CardId::BASH));
    goldAndCard.info.rewardsContainer.addCardReward(meaningful);
    const auto goldAndCardActions = enumerateOocSemanticPrimitiveBindings(goldAndCard);
    const auto cardAction = std::find_if(goldAndCardActions.bindings.begin(), goldAndCardActions.bindings.end(),
        [](const auto &binding) {
            return binding.semantic.effect == OocSemanticEffect::TAKE_CARD;
        });
    require(cardAction != goldAndCardActions.bindings.end(), "gold plus card fixture lacks card action");
    liveOptions.rootPrimitiveBits = std::set<std::uint32_t>{cardAction->primitiveBits};
    PathHistory goldAndCardPath;
    goldAndCardPath.update(goldAndCard);
    LiveOocMctsMetrics goldAndCardMetrics;
    const bool goldAndCardHandled = oocMctsPolicyStep(goldAndCard, goldAndCardPath, 42, 10, goldAndCardMetrics);
    const bool cardAdded = goldAndCard.deck.size() == goldAndCardDeckBefore + 1;
    const auto remainingSemantic = enumerateOocSemanticActions(goldAndCard);
    const bool goldCandidateRemains = std::any_of(remainingSemantic.actions.begin(),
        remainingSemantic.actions.end(), [](const auto &action) {
            return action.effect == OocSemanticEffect::TAKE_GOLD;
        });
    if (!(goldAndCardHandled && goldAndCard.gold == goldAndCardBefore + 25
            && goldAndCard.info.rewardsContainer.goldRewardCount == 0
            && goldAndCard.screenState == ScreenState::MAP_SCREEN && cardAdded
            && goldAndCard.info.rewardsContainer.cardRewardCount == 0 && !goldCandidateRemains
            && goldAndCardMetrics.search.trivialRootBypasses == 1
            && goldAndCardMetrics.search.simulations == 0))
        throw std::runtime_error("live native gold plus card root: handled=" + std::to_string(goldAndCardHandled)
            + " gold=" + std::to_string(goldAndCard.gold)
            + " before=" + std::to_string(goldAndCardBefore)
            + " goldLeft=" + std::to_string(goldAndCard.info.rewardsContainer.goldRewardCount)
            + " screen=" + std::to_string(int(goldAndCard.screenState))
            + " cardAdded=" + std::to_string(cardAdded)
            + " bypass=" + std::to_string(goldAndCardMetrics.search.trivialRootBypasses)
            + " sims=" + std::to_string(goldAndCardMetrics.search.simulations)
            + " fallback=" + std::to_string(goldAndCardMetrics.fallback));
    liveOptions = optionsBeforeGoldRoots;

    // Wheel has one legal primitive, but its existing fallback calls stepRandom:
    // choosing from a singleton still advances ScumSearchAgent2::rng.
    auto wheel=detachedCopy(sole);
    wheel.screenState=ScreenState::EVENT_SCREEN; wheel.curEvent=Event::WHEEL_OF_CHANGE;
    for (unsigned wheelSeed=0;wheelSeed<128;++wheelSeed) {
        wheel.miscRng=Random(wheelSeed);
        auto probe=wheel.miscRng;
        if (probe.random(5)==0) break; // gold, then the normal map callback
    }
    auto wheelRoll=wheel.miscRng;
    require(wheelRoll.random(5)==0,"wheel fixture deterministic gold outcome");
    PathHistory wheelPath; wheelPath.update(wheel);
    const auto wheelCandidates=v4CandidateActions(wheel);
    require(wheelCandidates.size()==1,"sole wheel candidate fixture");
    const auto savedEarlyStop=liveConfig.allowUnqualifiedRootStop;
    liveConfig.allowUnqualifiedRootStop=false;
    OocGameContextModel wheelModel(wheel,wheelPath,liveSampler,liveOptions);
    const auto wheelAction=wheelModel.soleLegalAction(0);
    const auto wheelBypass=searchWithSoleRootShortcut(wheelModel,liveConfig,wheelAction,128);
    require(wheelAction && wheelBypass.selectedAction==wheelAction
        && wheelBypass.metrics.trivialRootBypasses==1
        && wheelBypass.metrics.simulations==0 && wheelBypass.metrics.simulationAttempts==0
        && wheelBypass.metrics.transitionSamples==0 && wheelBypass.metrics.leafEvaluations==0
        && wheelModel.combatSamples()==0,
        "sole wheel semantic action bypasses unsupported hypothetical continuation");
    const auto wheelSearch=OocMctsPlanner(liveConfig).search(wheelModel,0,128);
    require(!wheelModel.searchGuaranteedNonAborting() && wheelSearch.aborted
        && wheelSearch.metrics.simulationAttempts>0,
        "old sole wheel search reaches unsupported combat and aborts");
    auto wheelPrimitive=detachedCopy(wheel), wheelOracle=detachedCopy(wheel);
    wheelCandidates.front().execute(wheelPrimitive);
    ScumSearchAgent2 wheelAgent, wheelOracleAgent;
    wheelAgent.rng.seed(20260914); wheelOracleAgent.rng=wheelAgent.rng;
    const auto agentBefore=wheelAgent.rng;
    runFullRunOocPolicyStep(wheelOracle,wheelOracleAgent,false,true);
    require(wheelOracleAgent.rng!=agentBefore
        && test::oocStateFingerprint(wheelOracle)==test::oocStateFingerprint(wheelPrimitive),
        "same sole wheel primitive hides a fallback agent RNG draw");
    const auto wheelBefore=test::oocStateFingerprint(wheel);
    LiveOocMctsMetrics wheelMetrics;
    require(oocMctsPolicyStep(wheel,wheelPath,42,7,wheelMetrics)
        && wheelMetrics.search.trivialRootBypasses==1 && wheelMetrics.supportAborts==0
        && wheelMetrics.fallback==0 && wheelMetrics.owned==1
        && wheelMetrics.search.simulations==0 && wheelMetrics.search.simulationAttempts==0
        && wheelMetrics.search.transitionSamples==0 && wheelMetrics.search.leafEvaluations==0
        && wheelMetrics.combatSamples==0 && wheelAgent.rng==agentBefore
        && test::oocStateFingerprint(wheel)==test::oocStateFingerprint(wheelPrimitive)
        && test::oocStateFingerprint(wheel)!=wheelBefore,
        "sole wheel root executes its exact action without hypothetical fallback");
    liveConfig.allowUnqualifiedRootStop=savedEarlyStop;
    struct QualifiedSoleRoot final : OocGenerativeModel {
        bool searchGuaranteedNonAborting() const override { return true; }
        std::optional<double> terminalValue(OocStateId) const override { return {}; }
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{7,1}}; }
        OocStateId sampleSuccessor(OocStateId,OocActionId,std::mt19937_64 &) override { ++draws; return 1; }
        double leafValue(OocStateId) const override { return .5; }
        unsigned draws=0;
    } qualifiedSole;
    const auto qualifiedBypass=searchWithSoleRootShortcut(qualifiedSole,liveConfig,7,128);
    require(qualifiedSole.searchGuaranteedNonAborting() && qualifiedBypass.selectedAction==7
        && qualifiedBypass.metrics.trivialRootBypasses==1 && qualifiedBypass.metrics.simulations==0
        && qualifiedBypass.metrics.simulationAttempts==0 && qualifiedSole.draws==0,
        "explicitly non-aborting sole model remains eligible for zero-simulation bypass");
    auto fallbackLive=detachedCopy(live), fallbackOracle=detachedCopy(live);
    ScumSearchAgent2 fallbackLiveAgent,fallbackOracleAgent;
    runFullRunOocPolicyStep(fallbackLive,fallbackLiveAgent,false,true);
    runFullRunOocPolicyStep(fallbackOracle,fallbackOracleAgent,false,true);
    require(test::oocStateFingerprint(fallbackLive)==test::oocStateFingerprint(fallbackOracle),
        "unsupported combat root uses unchanged V4 fallback primitive");
    auto lethal=std::make_shared<ImaginedDeath>();
    std::uint64_t firstSamples=0, repeatedSamples=0;
    const auto first=selectOocMctsAction(live,livePath,42,7,128,lethal,firstSamples);
    const auto second=selectOocMctsAction(live,livePath,42,7,128,lethal,repeatedSamples);
    require(test::oocStateFingerprint(live)==before
        && livePath.roomVisits==beforePath.roomVisits && livePath.lastNodeKey==beforePath.lastNodeKey,
        "live search isolates whole GameContext/map/RNG/PathHistory");
    require(first.selectedAction && first.selectedAction==second.selectedAction
        && firstSamples>0 && firstSamples==repeatedSamples
        && first.rootActions.size()==second.rootActions.size(), "deterministic live selection/samples");
    for (std::size_t i=0;i<first.rootActions.size();++i) {
        const auto &a=first.rootActions[i], &b=second.rootActions[i];
        require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
            "deterministic live root statistics");
    }
    require(oocMctsSearchSeed(42,7)==oocMctsSearchSeed(42,7)
        && oocMctsSearchSeed(42,7)!=oocMctsSearchSeed(42,8), "stable indexed search RNG");
    auto liveExpected=detachedCopy(live);
    const auto liveCandidates=v4CandidateActions(liveExpected);
    const auto selected=std::find_if(liveCandidates.begin(),liveCandidates.end(),
        [&](auto a) { return a.bits==*first.selectedAction; });
    require(selected!=liveCandidates.end(), "selected live candidate exists");
    selected->execute(liveExpected);
    liveEnabled=true; liveSimulations=128; liveSampler=lethal;
    LiveOocMctsMetrics liveMetrics;
    require(oocMctsPolicyStep(live,livePath,42,7,liveMetrics)
        && test::oocStateFingerprint(live)==test::oocStateFingerprint(liveExpected),
        "live execution exactly one primitive, no imagined successor transfer");
    require(live.screenState==ScreenState::BATTLE && live.outcome==GameOutcome::UNDECIDED
        && liveMetrics.combatSamples>0 && liveMetrics.owned==1
        && liveMetrics.decisions==1 && liveMetrics.fallback==0
        && liveMetrics.search.simulations>0
        && liveMetrics.search.simulations+liveMetrics.search.savedSimulations==128,
        "real combat remains pending despite imagined death and visit-lock stopping");
    // Real battle entry dispatches ordinary BattleContext initialization.
    BattleContext pending; pending.init(live);
    require(pending.outcome==Outcome::UNDECIDED && pending.player.curHp==live.curHp,
        "ordinary real battle initializes after selected action");
    auto uncovered=GameContext(CharacterClass::IRONCLAD,42,0);
    uncovered.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    uncovered.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
    uncovered.info.toSelectCount=0; // Deliberately incomplete semantic enumeration.
    const auto uncoveredBefore=test::oocStateFingerprint(uncovered);
    auto fallbackExpected=detachedCopy(uncovered);
    LiveOocMctsMetrics fallbackMetrics;
    require(!oocMctsPolicyStep(uncovered,livePath,42,8,fallbackMetrics)
        && fallbackMetrics.fallback==1 && fallbackMetrics.owned==0
        && fallbackMetrics.search.simulations==0
        && test::oocStateFingerprint(uncovered)==uncoveredBefore, "unsupported live root falls back unchanged");
    ScumSearchAgent2 fallbackAgent, expectedAgent;
    runFullRunOocPolicyStep(uncovered,fallbackAgent,false,true);
    runFullRunOocPolicyStep(fallbackExpected,expectedAgent,false,true);
    require(test::oocStateFingerprint(uncovered)==test::oocStateFingerprint(fallbackExpected),
        "unsupported root uses identical existing policy chain");
    auto multipleGold=detachedCopy(reward);
    multipleGold.info.rewardsContainer.goldRewardCount=2;
    multipleGold.info.rewardsContainer.gold[0]=12;
    multipleGold.info.rewardsContainer.gold[1]=13;
    OocGameContextModel duplicateRoot(multipleGold,livePath,lethal);
    require(!duplicateRoot.isLeafBoundary(0), "multiple-gold normalization must retain reward continuation");
    const auto duplicateActions=duplicateRoot.legalActions(0);
    for (const auto action : duplicateActions) {
        const auto &candidate=duplicateRoot.candidate(0,action.id);
        require(!candidate.semantic || candidate.semantic->effect!=OocSemanticEffect::TAKE_GOLD,
            "multiple-gold normalization left TAKE_GOLD in the candidate set");
    }
    auto goldOnlyFixture=multipleGold;
    goldOnlyFixture.info.rewardsContainer.cardRewardCount=0;
    goldOnlyFixture.info.rewardsContainer.relicCount=0;
    goldOnlyFixture.info.rewardsContainer.potionCount=0;
    OocGameContextModel goldOnlyRoot(goldOnlyFixture,livePath,lethal);
    const auto goldOnlyActions=goldOnlyRoot.legalActions(0);
    require(goldOnlyActions.size()==1 && goldOnlyActions.front().prior==1,
        "gold-only normalization must expose one leave-rewards action");
    const auto &goldOnlyCandidate=goldOnlyRoot.candidate(0,goldOnlyActions.front().id);
    require(goldOnlyCandidate.semantic
            && goldOnlyCandidate.semantic->effect==OocSemanticEffect::LEAVE_REWARDS,
        "gold-only normalization exposed a non-leave reward action");
    std::cout<<"PASS live OOC MCTS OFF/isolation/execution/real-combat/fallback/determinism\n";
    // Opt-in captured-model microbenchmark. Runs only detached search states;
    // this is not a gameplay cohort or a decision-quality experiment.
    if (const char *modelPath=std::getenv("STS_OOC_MCTS_MICROBENCH_MODEL")) {
        auto native=std::make_shared<NativeCombatTransitionSampler>(modelPath);
        struct ReferenceSampler final : CombatTransitionSampler {
            std::shared_ptr<const NativeCombatTransitionSampler> native;
            mutable std::uint64_t encoderCalls=0;
            explicit ReferenceSampler(std::shared_ptr<const NativeCombatTransitionSampler> n):native(std::move(n)) {}
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &p) const override {
                return native->support(g,p);
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &p,std::mt19937_64 &r) const override {
                auto result=native->sample(g,p,r);
                if (result.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED)
                    encoderCalls+=result.outcome==CombatRuntimeSample::Outcome::VICTORY ? 4 : 1;
                return result;
            }
        };
        auto reference=std::make_shared<ReferenceSampler>(native);
        GameContext fixed(CharacterClass::IRONCLAD,42,0);
        fixed.screenState=ScreenState::MAP_SCREEN; fixed.curEvent=Event::INVALID;
        for (auto &node : fixed.map->nodes[0]) node.room=Room::MONSTER;
        // Isolate one searched combat edge from native reward/projection work.
        fixed.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
        PathHistory fixedPath;fixedPath.update(fixed);
        OocAdapterOptions opts; opts.checkpointLeaves=true; opts.stopAtMapCheckpoint=true;
        OocGameContextModel before(fixed,fixedPath,reference,opts),after(fixed,fixedPath,native,opts);
        auto cfg=OocMctsConfig{}; cfg.seed=20260914;
        const auto start=std::chrono::steady_clock::now();
        const auto oldResult=OocMctsPlanner(cfg).search(before,0,512);
        const double oldSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        const auto next=std::chrono::steady_clock::now();
        const auto newResult=OocMctsPlanner(cfg).search(after,0,512);
        const double newSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-next).count();
        require(!oldResult.aborted && !newResult.aborted,"fixed native microbenchmark support");
        require(oldResult.selectedAction==newResult.selectedAction && before.storedStates()==after.storedStates()
            && before.combatSamples()==after.combatSamples(),"prepared search action/state/sample parity");
        const auto &a=oldResult.metrics,&b=newResult.metrics;
        require(a.simulations==b.simulations && a.simulationAttempts==b.simulationAttempts
            && a.decisionNodes==b.decisionNodes && a.chanceNodes==b.chanceNodes
            && a.outcomeParticles==b.outcomeParticles && a.transitionSamples==b.transitionSamples
            && a.leafEvaluations==b.leafEvaluations && a.particleRevisits==b.particleRevisits
            && a.deterministicRevisits==b.deterministicRevisits && a.depthSum==b.depthSum
            && a.maxDepthReached==b.maxDepthReached,"prepared complete tree metrics parity");
        for (std::size_t i=0;i<oldResult.rootActions.size();++i) {
            const auto &x=oldResult.rootActions[i],&y=newResult.rootActions.at(i);
            require(x.id==y.id && x.prior==y.prior && x.visits==y.visits && x.q==y.q,
                "prepared root IDs/order/priors/visits/Q parity");
        }
        for (std::size_t i=0;i<before.storedStates();++i)
            require(test::oocStateFingerprint(before.state(i))==test::oocStateFingerprint(after.state(i))
                && before.pathHistory(i).roomVisits==after.pathHistory(i).roomVisits
                && before.pathHistory(i).lastNodeKey==after.pathHistory(i).lastNodeKey,
                "every prepared search snapshot and PathHistory exact");
        nlohmann::json exact={{"selectedAction",*newResult.selectedAction},
            {"simulations",b.simulations},{"simulationAttempts",b.simulationAttempts},
            {"decisionNodes",b.decisionNodes},{"chanceNodes",b.chanceNodes},
            {"outcomeParticles",b.outcomeParticles},{"transitionSamples",b.transitionSamples},
            {"leafEvaluations",b.leafEvaluations},{"particleRevisits",b.particleRevisits},
            {"deterministicRevisits",b.deterministicRevisits},{"depthSum",b.depthSum},
            {"maxDepthReached",b.maxDepthReached}};
        for (auto action:newResult.rootActions)
            exact["rootActions"].push_back({action.id,action.prior,action.visits,action.q});
        for (std::size_t i=0;i<after.storedStates();++i)
            exact["states"].push_back({test::oocStateFingerprint(after.state(i)),
                after.pathHistory(i).roomVisits,after.pathHistory(i).lastNodeKey});
        std::cout<<"MICROBENCH_PARITY "<<exact.dump()<<'\n';
        std::cout<<"MICROBENCH "<<nlohmann::json{{"simulations",512},{"referenceSeconds",oldSeconds},
            {"preparedSeconds",newSeconds},{"referenceSimulationsPerSecond",512/oldSeconds},
            {"preparedSimulationsPerSecond",512/newSeconds},{"combatSamples",after.combatSamples()},
            {"referenceCombatSamplesPerSecond",before.combatSamples()/oldSeconds},
            {"preparedCombatSamplesPerSecond",after.combatSamples()/newSeconds},
            {"referenceEncoderCalls",reference->encoderCalls},
            {"preparedEncoderCalls",4*after.continuationMetrics().preparedCombats},
            {"uniqueCombatEdges",after.continuationMetrics().preparedCombats},
            {"generatedStates",after.storedStates()},{"decisionNodes",b.decisionNodes},
            {"metadataBuilds",after.continuationMetrics().metadataBuilds},
            {"priorBuilds",after.continuationMetrics().priorBuilds},{"parity",true}}.dump()<<'\n';
    }
    // Opt-in mechanism gate for experimental leaf evaluators. This compares
    // identical detached states and identical planner seeds before gameplay.
    if (const char *modelPath=std::getenv("STS_OOC_MCTS_BOSS_MECHANISM_MODEL")) {
        auto sampler=std::make_shared<NativeCombatTransitionSampler>(modelPath);
        OocAdapterOptions nativeOptions{true};
        OocAdapterOptions bossOptions{true}; bossOptions.bossLeaf=true;
        nlohmann::json mechanism;
        bool everyLeafDiffers=true;
        for (int hp : {20,40,60}) {
            auto probe=detachedCopy(gc); probe.curHp=hp; probe.maxHp=80;
            OocGameContextModel nativeLeaf(probe,path,sampler,nativeOptions);
            OocGameContextModel bossLeaf(probe,path,sampler,bossOptions);
            std::mt19937_64 nativeRng(20260915),bossRng(20260915);
            const double nativeValue=nativeLeaf.evaluateLeaf(0,nativeRng);
            const double bossValue=bossLeaf.evaluateLeaf(0,bossRng);
            everyLeafDiffers=everyLeafDiffers && std::abs(nativeValue-bossValue)>1e-6;
            mechanism["leaves"].push_back({{"hp",hp},{"native",nativeValue},{"boss",bossValue},
                {"bossExpectationCalls",10}});
        }
        require(everyLeafDiffers,"real boss mechanism leaf values must differ from native v_win");
        auto root=detachedCopy(gc);
        PathHistory rootPath; rootPath.update(root);
        OocGameContextModel nativeSearch(root,rootPath,sampler,nativeOptions);
        OocGameContextModel bossSearch(root,rootPath,sampler,bossOptions);
        OocMctsConfig cfg; cfg.seed=20260915;
        const auto nativeResult=OocMctsPlanner(cfg).search(nativeSearch,0,64);
        const auto bossResult=OocMctsPlanner(cfg).search(bossSearch,0,64);
        require(!nativeResult.aborted && !bossResult.aborted
            && nativeResult.rootActions.size()==bossResult.rootActions.size(),
            "real boss mechanism searches must complete on identical roots");
        bool qChanged=false;
        for (std::size_t i=0;i<nativeResult.rootActions.size();++i) {
            const auto &nativeAction=nativeResult.rootActions[i];
            const auto &bossAction=bossResult.rootActions[i];
            require(nativeAction.id==bossAction.id,"real boss mechanism root action identity");
            qChanged=qChanged || std::abs(nativeAction.q-bossAction.q)>1e-6;
            mechanism["rootActions"].push_back({{"id",nativeAction.id},
                {"nativeQ",nativeAction.q},{"bossQ",bossAction.q},
                {"nativeVisits",nativeAction.visits},{"bossVisits",bossAction.visits}});
        }
        require(qChanged,"real boss mechanism must change at least one MCTS root Q");
        mechanism["nativeSelectedAction"]=*nativeResult.selectedAction;
        mechanism["bossSelectedAction"]=*bossResult.selectedAction;
        mechanism["simulations"]=64;
        mechanism["leafValuesDiffer"]=everyLeafDiffers;
        mechanism["rootQChanged"]=qChanged;
        std::cout<<"BOSS_LEAF_MECHANISM "<<mechanism.dump()<<'\n';
    }
    std::cout<<"PASS OOC MCTS adapter (offline native integration only)\n";
}
}
#endif
