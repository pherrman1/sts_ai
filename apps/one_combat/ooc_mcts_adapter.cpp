#include "ooc_mcts_adapter.h"
#include "ooc_profile.h"
#include "combat_transition_runtime.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <time.h>
#include "../ooc_strategic_tok_net.h"
#include "run_driver.h"
#include "combat/BattleContext.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/BattleScumSearcher2.h"
#include "../ooc_test_state.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <type_traits>

namespace one_combat {
static_assert(!std::is_constructible_v<OocGameContextModel, const GameContext &>,
              "OOC MCTS roots must require explicit PathHistory");
namespace {
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

void require(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
double bossLeafUtility(const CombatTransitionExpectation &estimate) {
    const double survival = 1.0 - estimate.death;
    return 0.75 * survival + 0.25 * survival * estimate.winningHpFraction;
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
            const double logit = g_oocStrategicTokNet.predictPolicyLogit(prepared, action.bits,
                cats, type, int(gc.screenState), entity, entityId, price);
            if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
            result.push_back(logit);
        }
        return result;
    };
    if (winNetOk()) {
        dependencies.leafValue = [](const GameContext &source, const PathHistory &path) {
            auto gc = detachedCopy(source);
            const auto *saved = t_curPath;
            t_curPath = &path;
            try {
                const double value = vStateWinNative(gc);
                t_curPath = saved;
                return value;
            } catch (...) {
                t_curPath = saved;
                throw;
            }
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
    : combatSampler(std::move(sampler)), options(std::move(opts)),
      dependencies(std::move(deps)) {
    if (!std::isfinite(options.priorTemperature) || options.priorTemperature <= 0 || (options.leafCombats != 0 && options.leafCombats != 1 && options.leafCombats != 3))
        throw std::invalid_argument("OOC MCTS invalid adapter options");
    if (!options.bossLeaf && !dependencies.leafValue)
        throw std::runtime_error("OOC MCTS requires a leaf-value dependency");
    if (!dependencies.policyAvailable || !dependencies.policyLogits
            || !dependencies.policyAvailable())
        throw std::runtime_error("OOC MCTS requires native V4 policy dependencies");
    if (!dependencies.potionKeepValue) dependencies.potionKeepValue = [](const GameContext &) { return 0.0; };
    if (!dependencies.stopAfterAct) dependencies.stopAfterAct = [] { return 0; };
    auto history = path;
    history.update(gc);
    states.push_back({detachedCopy(gc), history, {}});
}
const GameContext &OocGameContextModel::state(sts::search::OocStateId id) const { return states.at(id).gc; }
const PathHistory &OocGameContextModel::pathHistory(sts::search::OocStateId id) const { return states.at(id).path; }
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
                std::set<std::uint32_t> sources;
                for (const auto &binding : enumeration.bindings) {
                    if (!GameAction(binding.primitiveBits).isValidAction(gc)) continue;
                    const auto key = sts::search::canonicalOocSemanticActionKey(binding.semantic);
                    if (!keys.insert(key).second) { value.candidates.clear(); break; }
                    value.candidates.push_back({static_cast<sts::search::OocActionId>(value.candidates.size()),
                        key, binding.semantic, GameAction(binding.primitiveBits), binding.compoundSelector});
                    sources.insert(binding.primitiveBits);
                }
                if (v4DecisionSupported(gc)) {
                    std::set<std::uint32_t> qualified;
                    const auto primitives = v4CandidateActions(gc);
                    for (auto action : primitives) qualified.insert(action.bits);
                    value.sourcePriorCovered = qualified.size() == primitives.size() && qualified == sources;
                }
            }
        }
        if (id == 0 && options.rootPrimitiveBits) {
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
    if (options.stopAtMapCheckpoint
            && state(id).screenState == sts::ScreenState::MAP_SCREEN)
        return true;
    return metadata(id).boundary;
}
std::optional<sts::search::OocActionId> OocGameContextModel::soleLegalAction(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) return std::nullopt;
    const auto &actions = metadata(id).candidates;
    if (actions.size()==1 && actions.front().primitive.isValidAction(state(id))) return actions.front().id;
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
    if (cached.logits) return *cached.logits;
    const auto &actions = cached.candidates;
    if (!cached.sourcePriorCovered) return std::vector<double>(actions.size(), 0.0);
    ++continuation_.priorBuilds;
    std::vector<GameAction> sources;
    std::map<std::uint32_t, std::size_t> sourceIndexes;
    for (const auto &candidate : actions) {
        const auto a = candidate.primitive;
        if (!sourceIndexes.count(a.bits)) {
            sourceIndexes.emplace(a.bits, sources.size());
            sources.push_back(a);
        }
    }
    OocProfileScope prediction(OocProfileBucket::PolicyPredict);
    const auto sourceLogits = dependencies.policyLogits(gc, snapshot.path, sources);
    if (sourceLogits.size() != sources.size())
        throw std::runtime_error("OOC MCTS policy-logit count mismatch");
    for (double logit : sourceLogits)
        if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    std::vector<double> logits;
    logits.reserve(actions.size());
    for (const auto &candidate : actions)
        logits.push_back(sourceLogits.at(sourceIndexes.at(candidate.primitive.bits)));
    cached.logits = logits;
    return logits;
}
std::vector<sts::search::OocPlannerAction> OocGameContextModel::legalActions(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    auto &cached = mutableMetadata(id);
    if (cached.priors) return *cached.priors;
    const auto &actions = cached.candidates;
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
    if (options.sampleNoncombat) sampleNoncombatFuture(child.gc, rng);
    if (it->semantic) {
        const auto executed = sts::search::executeOocSemanticAction(child.gc, *it->semantic);
        if (!executed.ok) throw sts::search::OocSearchUnsupported("semantic_execution:" + executed.error);
    } else it->primitive.execute(child.gc);
    child.path.update(child.gc);
    const bool enteredCombat = child.gc.screenState == sts::ScreenState::BATTLE;
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
    if (options.checkpointLeaves && enteredCombat) resolveCombat(child, rng, preparationCache.get());
    else if (combatSampler && enteredCombat) {
        if (preparationCache->support().supported) {
            ++combatSamples_;
            const auto sampled = preparationCache->sample(rng);
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
    return dependencies.leafValue(state(id), states.at(id).path);
}
bool OocGameContextModel::isDeterministicTransition(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    if (options.sampleNoncombat) return false;
    const auto &cached = metadata(id);
    const auto it = std::find_if(cached.candidates.begin(), cached.candidates.end(),
        [&](auto candidate) { return candidate.id == action; });
    return it != cached.candidates.end() && cached.edges.at(it-cached.candidates.begin()).deterministic.has_value();
}
void OocGameContextModel::resolveCombat(Snapshot &child, std::mt19937_64 &rng,
    const PreparedCombatTransition *prepared) {
    OocProfileScope profile(OocProfileBucket::CombatResolve);
    ++continuation_.imaginedCombats;
    const int battleAct = child.gc.act;
    const auto battleRoom = child.gc.curRoom;
    bool victory = false;
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
            ++combatSamples_;
            if (sampled.outcome == CombatRuntimeSample::Outcome::DEATH) {
                child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                return;
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
    decltype(sts::search::g_onSearchComplete) searchObserver=std::move(sts::search::g_onSearchComplete);
    decltype(sts::search::g_onSearchComplete3) searchObserver3=std::move(sts::search::g_onSearchComplete3);
    decltype(sts::g_onBattleExitPersistent) exitObserver=std::move(sts::g_onBattleExitPersistent);
    sts::search::SilverLiveDiagnostics silver = std::move(sts::search::g_silverLiveDiagnostics);
    bool disallowed = sts::search::g_disallowImaginedCombat;
    double potion = sts::search::g_potionKeepValue;
    ImaginedScope() {
        sts::search::g_disallowImaginedCombat=true;
        t_tokCheckPending=false; sts::search::g_onGameActionExecute={};
        sts::search::g_onCombatDecision={}; sts::search::g_onSearchComplete={};
        sts::search::g_onSearchComplete3={}; sts::g_onBattleExitPersistent={};
    }
    ~ImaginedScope() {
        t_curPath=path; t_oocStrategicTraceRows=std::move(rows); t_oocStrategicTraceDecision=decision;
        t_shopV=shop; t_tokCheckPending=tok;
        t_actFightProbeDecisionIdx=probeDecision; t_actFightProbeActionIdx=probeAction; t_actFightProbeFutureIdx=probeFuture;
        sts::search::g_onGameActionExecute=std::move(observer);
        sts::search::g_onCombatDecision=std::move(combatObserver);
        sts::search::g_onSearchComplete=std::move(searchObserver);
        sts::search::g_onSearchComplete3=std::move(searchObserver3);
        sts::g_onBattleExitPersistent=std::move(exitObserver);
        sts::search::g_silverLiveDiagnostics=std::move(silver);
        sts::search::g_disallowImaginedCombat=disallowed; sts::search::g_potionKeepValue=potion;
    }
};
#endif
}
double OocGameContextModel::evaluateLeaf(sts::search::OocStateId id, std::mt19937_64 &rng) {
    OocProfileScope profile(OocProfileBucket::EvaluateLeaf);
    if (options.stopAtMapCheckpoint
            && state(id).screenState == sts::ScreenState::MAP_SCREEN)
        return leafValue(id);
    if (!options.checkpointLeaves && !options.sampleNoncombat) return leafValue(id);
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    if (options.sampleNoncombat) sampleNoncombatFuture(child.gc, rng);
    if (!options.checkpointLeaves) {
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) return 0;
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) return 1;
        return options.bossLeaf ? bossLeafValue(child.gc)
            : dependencies.leafValue(child.gc, child.path);
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
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) return 0;
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) return 1;
        if (child.gc.screenState == sts::ScreenState::MAP_SCREEN && additionalCombats >= options.leafCombats) {
            if (options.constantLeaf) return 0.5;
            if (options.bossLeaf) return bossLeafValue(child.gc);
            OocProfileScope inference(OocProfileBucket::LeafValue);
            return dependencies.leafValue(child.gc, child.path);
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

#ifndef STS_LIVE_ADVISOR
namespace one_combat {

namespace {
bool liveEnabled = false;
std::uint64_t liveSimulations = 512;
sts::search::OocMctsConfig liveConfig;
OocAdapterOptions liveOptions{true};
std::shared_ptr<const CombatTransitionSampler> liveSampler;
std::string liveTrace, liveRootLockTrace, liveCheckpointTrace;
std::mutex liveTraceMutex;
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
        if (value == "native") { opts.constantLeaf = false; opts.bossLeaf = false; }
        else if (value == "constant") { opts.constantLeaf = true; opts.bossLeaf = false; }
        else if (value == "boss") { opts.constantLeaf = false; opts.bossLeaf = true; }
        else invalid();
    }
    else if (key == "STS_OOC_MCTS_LEAF_POLICY") opts.uniformLeafPolicy = choice("v4", "uniform");
    else if (key == "STS_OOC_MCTS_EARLY_STOP") config.allowUnqualifiedRootStop = choice("0", "1");
    else if (key == "STS_OOC_MCTS_GAP_STOP_20") config.stopAt512VisitGap20 = choice("0", "1");
    else if (key == "STS_OOC_MCTS_ROOT_SELECTION") config.selectByMeanQ = choice("visits", "q");
    else if (key == "STS_OOC_MCTS_TEMPERATURE") { const double x = number(); if (x <= 0) invalid(); opts.priorTemperature = x; }
    else if (key == "STS_OOC_MCTS_CPUCT") { const double x = number(); if (x < 0) invalid(); config.cPuct = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_K") { const double x = number(); if (x <= 0) invalid(); config.wideningK = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_ALPHA") { const double x = number(); if (x <= 0 || x >= 1) invalid(); config.wideningAlpha = x; }
    else if (key == "STS_OOC_MCTS_MAX_DEPTH") { const auto x = integer(); if (!x || x > 32) invalid(); config.maxDepth = x; }
    else if (key == "STS_OOC_MCTS_LEAF_COMBATS") { const auto x = integer(); if (x != 0 && x != 1 && x != 3) invalid(); opts.leafCombats = x; }
    else invalid();
}
const char *const liveControlKeys[] = {
    "STS_OOC_MCTS_EARLY_STOP", "STS_OOC_MCTS_GAP_STOP_20", "STS_OOC_MCTS_PRIOR", "STS_OOC_MCTS_TEMPERATURE", "STS_OOC_MCTS_CPUCT",
    "STS_OOC_MCTS_WIDEN_K", "STS_OOC_MCTS_WIDEN_ALPHA", "STS_OOC_MCTS_MAX_DEPTH",
    "STS_OOC_MCTS_ROOT_SELECTION", "STS_OOC_MCTS_LEAF_VALUE",
    "STS_OOC_MCTS_LEAF_COMBATS", "STS_OOC_MCTS_LEAF_POLICY"
};
void recordSearchAbort(const sts::search::OocMctsResult &result, OocContinuationMetrics &continuation) {
    if (!result.aborted) return;
    if (result.abortReason.rfind("continuation_step_limit_",0) == 0) {
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
    liveSimulations = 512; liveConfig = {}; liveOptions = {true};
    if (!liveEnabled) return;
    if (sts::search::silverLiveReuseCap() != 32768)
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
    liveConfig.allowUnqualifiedRootStop = true; // May skip later aborts; provider guarantee remains false.
    for (const char *key : liveControlKeys)
        if (const char *value = std::getenv(key)) applyLiveControl(key, value, liveConfig, liveOptions);
    if (liveConfig.stopAt512VisitGap20
        && (liveSimulations != 2048 || liveConfig.selectByMeanQ))
        throw std::runtime_error("STS_OOC_MCTS_GAP_STOP_20 requires 2048 visit-selected simulations");
    if (const char *trace = std::getenv("STS_OOC_MCTS_ROOT_LOCK_TRACE")) liveRootLockTrace = trace;
    liveConfig.observeRootLock = !liveRootLockTrace.empty();
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
    const char *artifact = std::getenv("STS_OOC_MCTS_COMBAT_MODEL");
    if (!artifact || !*artifact) throw std::runtime_error("STS_OOC_MCTS requires STS_OOC_MCTS_COMBAT_MODEL");
    liveSampler = std::make_shared<NativeCombatTransitionSampler>(artifact);
    const auto precision = std::cout.precision();
    std::cout << std::setprecision(17) << "[live OOC MCTS ON sims=" << liveSimulations
        << " combat_model=" << artifact << " prior=" << (liveOptions.uniformPrior ? "uniform" : "policy")
        << " temperature=" << liveOptions.priorTemperature << " cpuct=" << liveConfig.cPuct
        << " widen_k=" << liveConfig.wideningK << " widen_alpha=" << liveConfig.wideningAlpha
        << " max_depth=" << liveConfig.maxDepth << " root_selection=" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << " early_stop=" << liveConfig.allowUnqualifiedRootStop
        << " gap_stop_20=" << liveConfig.stopAt512VisitGap20
        << " leaf_value=" << (liveOptions.bossLeaf ? "boss" : liveOptions.constantLeaf ? "constant" : "native")
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
        << ",\"leafValue\":\"" << (liveOptions.bossLeaf ? "boss" : liveOptions.constantLeaf ? "constant" : "native")
        << "\",\"leafCombats\":" << liveOptions.leafCombats << ",\"leafPolicy\":\"" << (liveOptions.uniformLeafPolicy ? "uniform" : "v4")
        << "\",\"simulations\":" << liveSimulations << "}\n";
    std::cout.precision(precision);
}
namespace {
sts::search::OocMctsResult searchWithSoleRootShortcut(sts::search::OocGenerativeModel &model,
    const sts::search::OocMctsConfig &config, std::optional<sts::search::OocActionId> soleAction,
    std::uint64_t simulations) {
    if (!config.observeRootLock && config.maxDepth && soleAction && model.searchGuaranteedNonAborting()) {
        sts::search::OocMctsResult result;
        result.selectedAction = soleAction;
        result.metrics.trivialRootBypasses = 1;
        return result;
    }
    // An abort hands control to the ordered fallback policy, which may consume
    // agent RNG even when the primitive candidate set contains just one action.
    return sts::search::OocMctsPlanner(config).search(model, 0, simulations);
}
}
sts::search::OocMctsResult selectOocMctsAction(const GameContext &gc, const PathHistory &path,
    std::uint64_t seed, std::uint64_t index, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler> sampler, std::uint64_t &samples,
    OocContinuationMetrics *continuation, std::optional<OocGameContextModel::Candidate> *selected) {
    ImaginedScope scope;
    OocGameContextModel model(gc, path, std::move(sampler), liveOptions);
    samples = 0;
    if (selected) selected->reset();
    if (model.terminalValue(0) || model.isLeafBoundary(0)) return {};
    auto config = liveConfig;
    config.seed = oocMctsSearchSeed(seed, index);
    if (!simulations) throw std::invalid_argument("OOC MCTS requires simulations > 0");
    const auto result = searchWithSoleRootShortcut(model, config, model.soleLegalAction(0), simulations);
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
    std::optional<OocGameContextModel::Candidate> selected;
    const auto result = selectOocMctsAction(gc, path, seed, index, liveSimulations, liveSampler, samples, &continuation, &selected);
    profile.stop();
    metrics.wallSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now()-wallStart).count();
    metrics.cpuSeconds += threadCpuSeconds()-cpuStart;
    if (!liveCheckpointTrace.empty()) {
        ImaginedScope scope;
        OocGameContextModel shadow(gc, path, liveSampler, liveOptions);
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
    for (auto &[reason,count] : continuation.continuationReasons) c.continuationReasons[reason]+=count;
    for (auto &[reason,count] : continuation.supportReasons) c.supportReasons[reason]+=count;
    auto &m = metrics.search;
    m.outcomeParticles+=result.metrics.outcomeParticles; m.decisionNodes+=result.metrics.decisionNodes;
    m.chanceNodes+=result.metrics.chanceNodes; m.particleRevisits+=result.metrics.particleRevisits;
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
    if (oocProfileEnabled()) {
        static const char *names[] = {"mcts", "real_combat", "metadata", "policy_logits",
            "policy_prepare", "policy_predict", "successor", "combat_prepare", "combat_resolve",
            "evaluate_leaf", "leaf_value", "v4_state_network", "v4_action_value"};
        nlohmann::json counters = nlohmann::json::object();
        for (std::size_t index = 0; index < oocProfileCounters.size(); ++index) {
            const auto &counter = oocProfileCounters[index];
            counters[names[index]] = {{"calls", counter.calls}, {"inclusiveCpuSec", counter.inclusive},
                {"exclusiveCpuSec", counter.exclusive}};
        }
        std::cerr << "[ooc-cpu-profile] " << nlohmann::json{{"seed",seed},
            {"processCpuAtReportSec",oocProfileCpu(CLOCK_PROCESS_CPUTIME_ID)},
            {"mctsCpuSec",m.cpuSeconds},{"realCombats",realCombats},{"counters",counters}}.dump() << '\n';
        oocProfileCounters = {};
    }
    if (liveTrace.empty()) return;
    std::lock_guard<std::mutex> lock(liveTraceMutex);
    const std::string header = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,transitionSamples,combatSurrogateSamples,leafEvaluations,maxDepth,mctsWallSec,mctsCpuSec,realCombats,imaginedCombats,unsupportedCombats,mctsSupportAborts,discardedSimulations,simulationAttempts,pendingLeaves,battleLeaves,mapLeaves,projectionSteps,outcomeParticles,particleRevisits,deterministicRevisits,depthSum,continuationLimitAborts,trivialRootBypasses,earlyStopLockedRoot,earlyStopVisitGap20,savedSimulations,metadataBuilds,priorBuilds,preparedCombats,combatEdgeSamples\n";
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
        << ',' << m.continuation.combatEdgeSamples << '\n';
    std::ofstream reasons(liveTrace+".support.jsonl",std::ios::app);
    reasons << nlohmann::json{{"seed",seed},{"reasons",m.continuation.supportReasons},
        {"continuation_reasons",m.continuation.continuationReasons},
        {"continuation_limit_aborts",m.continuation.continuationLimitAborts}}.dump() << '\n';
    reasons.flush();
    if (!reasons) throw std::runtime_error("OOC MCTS support trace write failed");
    out.flush();
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE write failed");
}

}

#include "../../tests/data/ooc_v4_policy_fixture.h"
namespace one_combat {
void oocMctsAdapterSelfTest() {
    using namespace sts;
    using namespace sts::search;
    // Inspect the actual configured option before fixture-specific resets.
    require(!liveEnabled || liveOptions.sampleNoncombat,
        "enabled live OOC MCTS must sample noncombat outcomes after all startup resets");
    std::cout << std::setprecision(12);
    require(g_oocStrategicTokNet.path == "selfplay/models/ooc_strategic_tok_final.native"
        || g_oocStrategicTokNet.path.find("/selfplay/models/ooc_strategic_tok_final.native") != std::string::npos,
        "policy parity requires tracked final V4 artifact");
    float glob[42]; for (int i=0;i<42;++i) glob[i]=(i-20)*.125f;
    const int dk[96][3] = {{1,0,5},{42,1,2},{100,0,1}};
    const int rl[64][2] = {{1,1},{23,4}};
    const int pt[8][2] = {{2,1},{7,2}};
    const auto fixturePrepared = g_oocStrategicTokNet.prepareState(glob,3,dk,2,rl,2,pt);
    for (auto f : v4PolicyFixtures) {
        const float et[4] = {float(f.entityType==0),float(f.entityType==1),float(f.entityType==2),float(f.entityType==3)};
        double logit = g_oocStrategicTokNet.predictPolicyLogit(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        double q = g_oocStrategicTokNet.predictActionValue(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        require(logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price)
            && q == g_oocStrategicTokNet.predictActionValue(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price),
            "prepared V4 policy/Q exactly match legacy entry points");
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
    auto checkCandidates = [&](GameContext fixture, bool execute=true) {
        const auto before=test::oocStateFingerprint(fixture);
        const auto bindings=enumerateOocSemanticPrimitiveBindings(fixture);
        const bool map=fixture.screenState==ScreenState::MAP_SCREEN;
        const auto primitive=v4CandidateActions(fixture);
        require(map || (bindings.supported && bindings.complete && !bindings.bindings.empty()),
            "semantic coverage fixture must be complete");
        OocGameContextModel provider(fixture,path);
        const auto actual=provider.legalActions(0);
        require(actual.size()==(map?primitive.size():bindings.bindings.size()),
            "adapter exposes complete semantic sibling set");
        std::set<std::string> keys;
        std::map<std::uint32_t,double> mass;
        std::map<std::uint32_t,unsigned> counts;
        for(std::size_t i=0;i<actual.size();++i) {
            const auto &candidate=provider.candidate(0,actual[i].id);
            require(keys.insert(candidate.key).second,"unique immutable semantic identities");
            require(map ? actual[i].id==primitive[i].bits : actual[i].id==i,
                "MAP preserves primitive IDs; semantic IDs are local ordinals");
            if (!map) require(candidate.semantic
                && candidate.key==canonicalOocSemanticActionKey(bindings.bindings[i].semantic)
                && candidate.primitive.bits==bindings.bindings[i].primitiveBits,
                "semantic keys and source projection match complete enumeration");
            mass[candidate.primitive.bits]+=actual[i].prior;
            ++counts[candidate.primitive.bits];
            if (execute && !map) {
                auto expected=detachedCopy(fixture);
                const auto result=executeOocSemanticAction(expected,*candidate.semantic);
                require(result.ok,"fixture semantic execution succeeds");
                const auto child=provider.sampleSuccessor(0,actual[i].id,rng);
                require(test::oocStateFingerprint(provider.state(child))==test::oocStateFingerprint(expected),
                    "adapter semantic edge reaches complete transactional successor");
                if(candidate.compoundSelector!=CardSelectScreenType::INVALID)
                    require(result.executedPrimitiveBits.size()==2 && expected.screenState!=ScreenState::CARD_SELECT,
                        "compound edge consumes both source and physical card target");
            }
        }
        bool qualified=v4DecisionSupported(fixture);
        std::set<std::uint32_t> established;
        for(auto a:primitive) qualified=established.insert(a.bits).second && qualified;
        qualified=qualified && established.size()==counts.size();
        for(const auto &[bits,count]:counts) qualified=qualified && established.count(bits);
        if(qualified) {
            const auto tokens=buildTokState(fixture,path);
            std::vector<double> sourceLogits;
            for(auto action:primitive) {
                int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
                strategicCands(fixture,action,type,c1,c2,c3,d1,d2,d3);
                tokEntity(fixture,action,et,ei,price);
                const int cats[6]={c1,c2,c3,d1,d2,d3};
                const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
                sourceLogits.push_back(g_oocStrategicTokNet.predictPolicyLogit(tokens.glob,
                    tokens.nDk,tokens.dk,tokens.nRl,tokens.rl,tokens.nPt,tokens.pt,
                    action.bits,cats,type,int(fixture.screenState),entity,ei,price));
            }
            const auto weights=oocPolicyWeights(sourceLogits);
            for(std::size_t i=0;i<primitive.size();++i)
                require(std::abs(mass.at(primitive[i].bits)-weights[i])<1e-12,
                    "source prior mass conserved across semantic expansion and one-to-one actions");
            for(auto action:actual) {
                const auto bits=provider.candidate(0,action.id).primitive.bits;
                require(std::abs(action.prior-mass.at(bits)/counts.at(bits))<1e-12,
                    "compound target weights split equally");
            }
        } else for(auto action:actual) require(action.prior==1,"unqualified V4 semantic roots are wholly uniform");
        OocAdapterOptions uniform; uniform.uniformPrior=true;
        OocGameContextModel uniformProvider(fixture,path,{},uniform);
        for(auto action:uniformProvider.legalActions(0)) require(action.prior==1,"explicit uniform semantic siblings");
        require(test::oocStateFingerprint(fixture)==before
            && test::oocStateFingerprint(provider.state(0))==before,"semantic testing preserves immutable root");
        std::cout<<"semantic_adapter_coverage screen="<<int(fixture.screenState)
            <<" event="<<int(fixture.curEvent)<<" selector="<<int(fixture.info.selectScreenType)
            <<" count="<<actual.size()<<" v4_qualified="<<qualified<<'\n';
    };
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
        require(removals==selector.info.toSelectCards.size() && strikeOccurrences.size()>1,
            "shop removal covers every physical card including distinct equivalent-card occurrences");
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
        // Compare actual search choices/statistics with the former primitive
        // root interface. Native transition parity is checked above separately.
        struct PrimitiveMapRoot final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<OocPlannerAction> primitiveActions;
            PrimitiveMapRoot(const GameContext &g,const PathHistory &p):adapter(g,p) {
                const auto actions=v4CandidateActions(g);
                const auto weights=oocPolicyWeights(adapter.policyLogits(0));
                for(std::size_t i=0;i<actions.size();++i) primitiveActions.push_back({actions[i].bits,weights[i]});
            }
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
                require(id==0,"bounded MAP comparison never expands a child"); return primitiveActions;
            }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
                return adapter.sampleSuccessor(id,a,r);
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
        } baseline(gc,path);
        OocGameContextModel current(gc,path);
        OocMctsConfig config; config.maxDepth=1;
        const auto expected=OocMctsPlanner(config).search(baseline,0,32);
        const auto actual=OocMctsPlanner(config).search(current,0,32);
        require(actual.selectedAction==expected.selectedAction && actual.rootActions.size()==expected.rootActions.size(),
            "MAP selected primitive ID matches former candidate interface");
        for(std::size_t i=0;i<actual.rootActions.size();++i) {
            const auto &a=actual.rootActions[i], &b=expected.rootActions[i];
            require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
                "MAP planner statistics remain exactly equivalent");
        }
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
            require(actions.size()==state.info.toSelectCards.size(),"one current pick without subset cross-product");
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
    fixture.info.rewardsContainer.relics[0]=RelicId::BOTTLED_FLAME;
    checkCandidates(fixture);
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
        std::mt19937_64 pandoraDraws(819);
        for(auto action:pandora.legalActions(0)) {
            const auto &c=pandora.candidate(0,action.id);
            if(c.semantic->effect!=OocSemanticEffect::TAKE_BOSS_RELIC
                || std::get<OocRelicTarget>(c.semantic->target).relic!=RelicId::PANDORAS_BOX) continue;
            for(int n=0;n<16;++n) pandoraOutcomes.insert(visible(pandora.state(pandora.sampleSuccessor(0,action.id,pandoraDraws))));
        }
        require(pandoraOutcomes.size()>1,"Pandora random transformations resampled");
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
        std::mt19937_64 left(19),right(19);
        sampleNoncombatFuture(source,left); sampleNoncombatFuture(altered,right);
        require(test::oocStateFingerprint(source)==test::oocStateFingerprint(altered),
            "hypothetical future independent of copied hidden seeds and queue ordering");
        require(left==right,"sampling consumes reproducible planner draws");
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
        OocMctsConfig parsed; OocAdapterOptions opts{true};
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","1",parsed,opts);
        require(parsed.allowUnqualifiedRootStop,"explicit early-stop enable parsed");
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","0",parsed,opts);
        require(!parsed.allowUnqualifiedRootStop,"early-stop rollback parsed");
        applyLiveControl("STS_OOC_MCTS_ROOT_SELECTION","q",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_COMBATS","3",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","boss",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_CPUCT","0",parsed,opts);
        require(parsed.selectByMeanQ && parsed.cPuct == 0 && opts.leafCombats == 3 && opts.bossLeaf,
            "accepted bounded knobs");
        require(std::abs(bossLeafUtility({true,0.2f,0.5f})-0.7)<1e-7
            && bossLeafUtility({true,1,1})==0 && bossLeafUtility({true,0,1})==1,
            "boss leaf survival/HP utility");
        for (const auto &invalid : std::vector<std::pair<std::string,std::string>>{
            {"STS_OOC_MCTS_EARLY_STOP","true"},{"STS_OOC_MCTS_EARLY_STOP","2"},{"STS_OOC_MCTS_PRIOR","none"},{"STS_OOC_MCTS_TEMPERATURE","0"},
            {"STS_OOC_MCTS_CPUCT","-1"},{"STS_OOC_MCTS_WIDEN_K","nan"},
            {"STS_OOC_MCTS_WIDEN_ALPHA","1"},{"STS_OOC_MCTS_MAX_DEPTH","33"},
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
    require(regainCalls==2 && fake->sampleCalls==1 && fake->supportCalls==1,
            "injected reward continuation exactly once");
    require(test::oocStateFingerprint(crossed.state(crossedId))==test::oocStateFingerprint(real),
            "injected continuation OOC/reward/RNG fingerprint");
    require(combatTransitionFingerprint(crossed.state(crossedId))==combatTransitionFingerprint(real),
            "injected persistent continuation fingerprint");
    require(crossed.pathHistory(crossedId).roomVisits==realPath.roomVisits
        && crossed.pathHistory(crossedId).lastNodeKey==realPath.lastNodeKey,"native PathHistory parity");
    require(test::oocStateFingerprint(crossed.state(0))==rootFingerprint,"combat parent unchanged");
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
        bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
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
    OocMctsConfig chanceConfig; chanceConfig.maxDepth=1; chanceConfig.seed=12345;
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
    for (int amount : {1,1000}) {
        auto pendingGold=detachedCopy(reward);
        auto &container=pendingGold.info.rewardsContainer;
        container.goldRewardCount=1; container.gold[0]=amount;
        container.cardRewardCount=container.relicCount=container.potionCount=0;
        container.emeraldKey=container.sapphireKey=false;
        const auto fingerprint=test::oocStateFingerprint(pendingGold);
        const auto features=richFeatureVec(pendingGold);
        if (pendingFeatures.empty()) pendingFeatures=features;
        else require(features==pendingFeatures,"rich model cannot see pending reward contents fixture");
        auto completed=detachedCopy(pendingGold);
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<16 && completed.screenState!=ScreenState::MAP_SCREEN;++step)
            runFullRunOocPolicyStep(completed,oracleAgent,false,true);
        require(completed.screenState==ScreenState::MAP_SCREEN && completed.gold==pendingGold.gold+amount,
            "pending gold oracle reaches checkpoint after collection");
        OocGameContextModel projected(pendingGold,path,{}, {true});
        rejects([&] { projected.leafValue(0); });
        std::mt19937_64 projectionRng(543);
        const auto savedPath=t_curPath;
        t_curPath=&projected.pathHistory(0);
        const auto oracleValue=vStateWinNative(completed);
        t_curPath=savedPath;
        require(projected.evaluateLeaf(0,projectionRng)==oracleValue
            && projected.continuationMetrics().pendingLeaves==1
            && projected.continuationMetrics().projectionSteps>=2
            && test::oocStateFingerprint(projected.state(0))==fingerprint
            && test::oocStateFingerprint(pendingGold)==fingerprint && t_curPath==savedPath,
            "pending reward projection matches resolved oracle and preserves caller");
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
            bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override { return adapter.sampleSuccessor(id,a,r); }
            double leafValue(OocStateId) const override { throw OocSearchUnsupported("continuation_step_limit_1024"); }
        } bounded(adapter);
        OocMctsConfig config; config.maxDepth=1;
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
        rejects([&] { forbiddenAgent.playoutBattle(forbiddenBattle); });
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
        ~LiveConfigScope() { liveEnabled=enabled; liveSimulations=simulations; liveSampler=sampler; }
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
        && unsupportedMetrics.owned==0 && unsupportedMetrics.search.simulationAttempts==1
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
    require(!oocMctsPolicyStep(sole,solePath,42,7,soleMetrics)
        && soleMetrics.search.trivialRootBypasses==0 && soleMetrics.search.simulations==0
        && soleMetrics.search.simulationAttempts==1 && soleMetrics.combatSamples==0
        && soleMetrics.supportAborts==1 && soleMetrics.fallback==1
        && test::oocStateFingerprint(sole)==soleBefore,
        "abort-capable sole map root searches and returns untouched state to fallback");

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
    liveConfig.allowUnqualifiedRootStop=false; // Verify rollback preserves legacy fallback/RNG.
    OocGameContextModel wheelModel(wheel,wheelPath,liveSampler,liveOptions);
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
    require(!oocMctsPolicyStep(wheel,wheelPath,42,7,wheelMetrics)
        && wheelMetrics.search.trivialRootBypasses==0 && wheelMetrics.supportAborts==1
        && wheelMetrics.fallback==1 && wheelMetrics.search.simulationAttempts>0
        && wheelAgent.rng==agentBefore && test::oocStateFingerprint(wheel)==wheelBefore,
        "unsafe sole wheel root cannot skip abort and RNG-consuming fallback");
    runFullRunOocPolicyStep(wheel,wheelAgent,false,true);
    require(wheelAgent.rng==wheelOracleAgent.rng && wheelAgent.rng!=agentBefore
        && test::oocStateFingerprint(wheel)==test::oocStateFingerprint(wheelOracle),
        "unsafe sole wheel dispatch preserves ordered fallback state and agent RNG");
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
    require(!duplicateRoot.isLeafBoundary(0), "semantic identity supports distinct gold rewards");
    for(auto action:duplicateRoot.legalActions(0))
        require(action.prior==1,"incomplete primitive gold coverage makes whole semantic prior uniform");
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
        OocAdapterOptions opts; opts.checkpointLeaves=true;
        OocGameContextModel before(fixed,fixedPath,reference,opts),after(fixed,fixedPath,native,opts);
        auto cfg=OocMctsConfig{}; cfg.seed=20260914;cfg.maxDepth=1;
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
