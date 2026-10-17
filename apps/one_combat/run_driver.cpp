#include "sim/search/RunGoal.h"
#include "run_driver.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <map>
#include <mutex>
#include <sstream>

#include "combat/BattleContext.h"
#include "sim/search/GameAction.h"
#include "sim/search/MatchAndKeepPolicy.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/NativeSilverBackend.h"
#include "e2c_capture.h"
#include "ooc_policy.h"
#include "ooc_native_fallback.h"
#include "ooc_checkpoint_policy.h"
#include "ooc_mcts_adapter.h"
#include "heart1_policy.h"
#include "sim/search/PotionRewardPolicy.h"
#include "ooc_profile.h"
#include "run_profile.h"
#include "run_features.h"

using namespace sts;

namespace {

std::mutex g_oocStrategicTraceMutex;

// Research-only (#347 OOC divergence): STS_OOC_DECISION_TRACE=<path> appends
// one JSON line per real out-of-combat step and per battle of runFullRunOOC
// (state before, what the screen offered, state after). It only reads state,
// so the run is unchanged; unset, nothing is computed.
constexpr const char *kOocTraceScreens[] = {"INVALID", "EVENT", "REWARDS", "BOSS_RELIC",
    "CARD_SELECT", "MAP", "TREASURE", "REST", "SHOP", "BATTLE"};

std::string oocTraceCard(const Card &c) {
    return std::string(c.getName()) + (c.isUpgraded() ? "+" : "");
}

nlohmann::json oocTraceState(const GameContext &gc) {
    nlohmann::json deck = nlohmann::json::array(), relics = nlohmann::json::array(),
                   potions = nlohmann::json::array();
    for (const auto &c : gc.deck.cards) deck.push_back(oocTraceCard(c));
    for (const auto &r : gc.relics.relics) relics.push_back(relicEnumNames[static_cast<int>(r.id)]);
    for (int i = 0; i < gc.potionCapacity && i < static_cast<int>(gc.potions.size()); ++i)
        if (gc.potions[i] != Potion::EMPTY_POTION_SLOT && gc.potions[i] != Potion::INVALID)
            potions.push_back(potionEnumNames[static_cast<int>(gc.potions[i])]);
    return {{"act", gc.act}, {"floor", gc.floorNum}, {"x", gc.curMapNodeX}, {"y", gc.curMapNodeY},
            {"screen", kOocTraceScreens[static_cast<int>(gc.screenState)]},
            {"room", roomStrings[static_cast<int>(gc.curRoom)]},
            {"event", gc.screenState == ScreenState::EVENT_SCREEN
                ? eventIdStrings[static_cast<int>(gc.curEvent)] : ""},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold}, {"deck", deck},
            {"relics", relics}, {"potions", potions}, {"potionCapacity", gc.potionCapacity}};
}

nlohmann::json oocTraceOffer(const GameContext &gc) {
    nlohmann::json o = nlohmann::json::object();
    if (gc.screenState == ScreenState::REWARDS) {
        const auto &r = gc.info.rewardsContainer;
        nlohmann::json cards = nlohmann::json::array(), relics = nlohmann::json::array(),
                       potions = nlohmann::json::array(), gold = nlohmann::json::array();
        for (int i = 0; i < r.cardRewardCount; ++i) {
            nlohmann::json one = nlohmann::json::array();
            for (const auto &c : r.cardRewards[i]) one.push_back(oocTraceCard(c));
            cards.push_back(one);
        }
        for (int i = 0; i < r.relicCount; ++i) relics.push_back(relicEnumNames[static_cast<int>(r.relics[i])]);
        for (int i = 0; i < r.potionCount; ++i) potions.push_back(potionEnumNames[static_cast<int>(r.potions[i])]);
        for (int i = 0; i < r.goldRewardCount; ++i) gold.push_back(r.gold[i]);
        o = {{"cards", cards}, {"relics", relics}, {"potions", potions}, {"gold", gold}};
    } else if (gc.screenState == ScreenState::SHOP_ROOM) {
        const auto &sh = gc.info.shop;
        nlohmann::json cards = nlohmann::json::array(), relics = nlohmann::json::array(),
                       potions = nlohmann::json::array();
        for (int i = 0; i < 7; ++i)
            if (sh.cards[i].getId() != CardId::INVALID && sh.cardPrice(i) >= 0)
                cards.push_back({oocTraceCard(sh.cards[i]), sh.cardPrice(i)});
        for (int i = 0; i < 3; ++i) {
            if (sh.relics[i] != RelicId::INVALID && sh.relicPrice(i) >= 0)
                relics.push_back({relicEnumNames[static_cast<int>(sh.relics[i])], sh.relicPrice(i)});
            if (sh.potions[i] != Potion::INVALID && sh.potionPrice(i) >= 0)
                potions.push_back({potionEnumNames[static_cast<int>(sh.potions[i])], sh.potionPrice(i)});
        }
        o = {{"cards", cards}, {"relics", relics}, {"potions", potions}, {"removeCost", sh.removeCost}};
    } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        nlohmann::json relics = nlohmann::json::array();
        for (const auto r : gc.info.bossRelics)
            if (r != RelicId::INVALID) relics.push_back(relicEnumNames[static_cast<int>(r)]);
        o = {{"relics", relics}};
    } else if (gc.screenState == ScreenState::CARD_SELECT) {
        o = {{"selectType", static_cast<int>(gc.info.selectScreenType)}, {"toSelect", gc.info.toSelectCount}};
    }
    return o;
}

void oocTraceEmit(const nlohmann::json &row) {
    static const char *path = std::getenv("STS_OOC_DECISION_TRACE");
    std::lock_guard<std::mutex> lock(g_oocStrategicTraceMutex);
    std::ofstream f(path, std::ios::app);
    f << row.dump() << '\n';
}

// A floor spans first observation by the real driver to first observation of
// the next floor (map-choice/entry work belongs to the floor being left).
class FloorProfile {
    bool enabled;
    std::function<void(const nlohmann::json &)> emit;
    bool active = false;
    nlohmann::json context;
    int act = -1, floor = -1;
    double wall = 0, cpu = 0, combatWall = 0, combatCpu = 0;
    std::uint64_t combatDecisions = 0, combatSimulations = 0;
    one_combat::LiveOocMctsMetrics start;
public:
    explicit FloorProfile(std::function<void(const nlohmann::json &)> sink = {})
        : enabled(bool(sink) || !one_combat::runProfilePath().empty()),
          emit(sink ? std::move(sink) : one_combat::writeRunProfile) {}
    bool on() const { return enabled; }
    void advance(const GameContext &gc, const one_combat::LiveOocMctsMetrics &metrics) {
        if (!enabled || (active && act == gc.act && floor == gc.floorNum)) return;
        finish(metrics, "advanced");
        active = true; act = gc.act; floor = gc.floorNum; start = metrics;
        context = {{"schema", 1}, {"kind", "floor"}, {"seed", std::to_string(gc.seed)},
            {"act", act}, {"floor", floor}, {"room", roomStrings[int(gc.curRoom)]},
            {"map_x", gc.curMapNodeX}, {"map_y", gc.curMapNodeY},
            {"encounters", nlohmann::json::array()}};
        combatWall = combatCpu = 0; combatDecisions = combatSimulations = 0;
        wall = one_combat::runProfileWall(); cpu = one_combat::oocProfileCpu();
    }
    void combat(const BattleContext &bc, double elapsedWall, double elapsedCpu) {
        if (!enabled) return;
        combatWall += elapsedWall; combatCpu += elapsedCpu;
        combatDecisions += search::g_nativeSilverCombatStats.decisions;
        combatSimulations += search::g_nativeSilverCombatStats.simulations;
        context["encounters"].push_back(monsterEncounterEnumNames[int(bc.encounter)]);
    }
    void finish(const one_combat::LiveOocMctsMetrics &m, const std::string &status,
                const std::string &error = {}) {
        if (!enabled || !active) return;
        const double wallElapsed = one_combat::runProfileWall() - wall;
        const double cpuElapsed = one_combat::oocProfileCpu() - cpu;
        const auto observerSkips = [](const one_combat::LiveOocMctsMetrics &metrics) {
            const auto &reasons = metrics.continuation.supportReasons;
            const auto it = reasons.find("semantic_observer_active");
            return it == reasons.end() ? std::uint64_t{0} : std::uint64_t(it->second);
        };
        auto row = context;
        row.update({{"wall_seconds", wallElapsed}, {"thread_cpu_seconds", cpuElapsed},
            {"real_combat_wall_seconds", combatWall}, {"real_combat_cpu_seconds", combatCpu},
            {"combat_decisions", combatDecisions}, {"combat_simulations", combatSimulations},
            {"ooc_decisions", m.decisions - start.decisions},
            {"ooc_owned", m.owned - start.owned}, {"fallbacks", m.fallback - start.fallback},
            // Disabled calls and observer early returns emit no decision row.
            {"unprofiled_disabled", (m.decisions - m.owned - m.fallback)
                - (start.decisions - start.owned - start.fallback)},
            {"unprofiled_observer", observerSkips(m) - observerSkips(start)},
            {"support_aborts", m.supportAborts - start.supportAborts},
            {"ooc_wall_seconds", m.wallSeconds - start.wallSeconds},
            {"ooc_cpu_seconds", m.cpuSeconds - start.cpuSeconds},
            {"ooc_simulations", m.search.simulations - start.search.simulations},
            {"leaf_evaluations", m.search.leafEvaluations - start.search.leafEvaluations},
            {"transition_samples", m.search.transitionSamples - start.search.transitionSamples},
            {"outcome_particles", m.search.outcomeParticles - start.search.outcomeParticles},
            {"ctm_samples", m.combatSamples - start.combatSamples},
            {"status", status}, {"error", error}});
        emit(row);
        active = false;
    }
};

} // namespace

void runFloorProfileSelfTest() {
    std::vector<nlohmann::json> rows;
    FloorProfile profile([&](const nlohmann::json &row) { rows.push_back(row); });
    GameContext gc(CharacterClass::IRONCLAD, 42, 0);
    one_combat::LiveOocMctsMetrics metrics;
    const int firstFloor = gc.floorNum;
    profile.advance(gc, metrics);
    metrics.decisions = 3; metrics.owned = 1; metrics.fallback = 1;
    metrics.continuation.supportReasons["semantic_observer_active"] = 1;
    metrics.search.simulations = 128;
    profile.advance(gc, metrics); // another screen on the same floor
    ++gc.floorNum; gc.curRoom = Room::ELITE;
    profile.advance(gc, metrics);
    ++metrics.decisions; ++metrics.owned; metrics.search.simulations += 256;
    ++gc.floorNum; gc.curRoom = Room::REST;
    profile.advance(gc, metrics);
    profile.finish(metrics, "death");
    profile.finish(metrics, "death"); // no duplicate final row
    if (rows.size() != 3 || rows[0]["floor"] != firstFloor
        || rows[0]["ooc_simulations"] != 128 || rows[0]["ooc_decisions"] != 3
        || rows[0]["unprofiled_disabled"] != 1 || rows[0]["unprofiled_observer"] != 1
        || rows[1]["unprofiled_disabled"] != 0 || rows[1]["unprofiled_observer"] != 0
        || rows[1]["floor"] != firstFloor + 1 || rows[1]["room"] != "ELITE"
        || rows[1]["ooc_simulations"] != 256 || rows[1]["ooc_decisions"] != 1
        || rows[2]["floor"] != firstFloor + 2 || rows[2]["status"] != "death"
        || rows[2]["ooc_simulations"] != 0 || rows[2]["seed"] != "42")
        throw std::runtime_error("floor profile boundary/metadata/delta fixture failed");
}

thread_local bool t_oocHypotheticalStep = false;
thread_local BossEntryHook *t_bossEntryHook = nullptr;
thread_local std::function<void(const sts::GameContext &, const one_combat::PathHistory &)> t_realRunContextObserver;
thread_local std::function<void(std::uint64_t, const char *)> t_realOocDecisionObserver;

thread_local MatchAndKeepWantCache t_matchAndKeepWant;

bool matchAndKeepPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent, bool restV, bool shopV,
                            const one_combat::PathHistory &path, std::uint64_t runSeed,
                            std::uint64_t decisionIndex, one_combat::LiveOocMctsMetrics *mctsMetrics) {
    if (gc.screenState != ScreenState::EVENT_SCREEN || gc.curEvent != Event::MATCH_AND_KEEP) return false;
    auto &cache = t_matchAndKeepWant;
    if (cache.seed != gc.seed || cache.act != gc.act || cache.floor != gc.floorNum) {
        cache = MatchAndKeepWantCache{gc.seed, gc.act, gc.floorNum, {}};
    }
    const auto want = [&](const Card &card) {
        const auto key = std::make_pair(static_cast<int>(card.id), card.isUpgraded());
        if (const auto it = cache.want.find(key); it != cache.want.end()) return it->second;
        // The active primary guide values the card as a lone card reward:
        // OOC MCTS when enabled, otherwise the ordinary V4/one-ply chain.
        const bool take = one_combat::oocHypotheticalCardTaken(gc, path, card, [&](GameContext &offer) {
            if (mctsMetrics) {
                const std::uint64_t index = (decisionIndex << 12)
                    ^ (static_cast<std::uint64_t>(card.id) << 1) ^ std::uint64_t(card.isUpgraded());
                if (one_combat::oocMctsPolicyStep(offer, path, runSeed, index, *mctsMetrics)) return;
            }
            const bool saved = t_oocHypotheticalStep;
            t_oocHypotheticalStep = true;
            try {
                runFullRunOocPolicyStep(offer, agent, restV, shopV);
            } catch (...) {
                t_oocHypotheticalStep = saved;
                throw;
            }
            t_oocHypotheticalStep = saved;
        });
        cache.want.emplace(key, take);
        return take;
    };
    search::GameAction(search::chooseMatchAndKeepSlot(gc, want)).execute(gc);
    return true;
}

// Opening a treasure chest is free unless Cursed Key turns it into a curse,
// so every OOC policy opens it without Cursed Key (#347: live OOC MCTS left
// every chest closed). With Cursed Key the ordinary decision runs.
static bool openTreasureChestRuleStep(GameContext &gc) {
    if (gc.screenState != ScreenState::TREASURE_ROOM || gc.relics.has(RelicId::CURSED_KEY)) return false;
    search::GameAction(0).execute(gc);
    return true;
}

// Every offered reward relic (elites, event elites, chests) is taken first,
// except Philipp's listed exceptions (2026-10-07), which go to the ordinary
// decision. Live OOC MCTS left most chest relics because its leaf value prices
// them near zero (#347, ledger §390). The Heart key rule runs first to preserve Sapphire pairing.
static bool reviewedRewardRelic(RelicId id) {
    switch (id) {
        case RelicId::BOTTLED_FLAME: case RelicId::BOTTLED_LIGHTNING: case RelicId::BOTTLED_TORNADO:
        case RelicId::DEAD_BRANCH: case RelicId::TUNGSTEN_ROD: case RelicId::UNCEASING_TOP:
        case RelicId::JUZU_BRACELET: return true;
        default: return false;
    }
}
static bool takeRewardRelicRuleStep(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState != ScreenState::REWARDS) return false;
    const auto &r = gc.info.rewardsContainer;
    for (int i = 0; i < r.relicCount; ++i) {
        if (reviewedRewardRelic(r.relics[i]) || !search::GameAction(RT::RELIC, i).isValidAction(gc)) continue;
        search::GameAction(RT::RELIC, i).execute(gc);
        return true;
    }
    return false;
}

thread_local const char *t_oocChainHandler = "";
const char *lastOocChainHandler() { return t_oocChainHandler; }

bool oocTreeRuleStep(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    if (const auto key = search::heartKeyAction(gc, g_collectKeys)) { key->execute(gc); return true; }
    if (openTreasureChestRuleStep(gc) || takeRewardRelicRuleStep(gc)) return true;
    if (gc.screenState != ScreenState::REWARDS) return false;
    auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount > 0) { search::GameAction(RT::GOLD, 0).execute(gc); return true; }
    if (!gc.hasRelic(RelicId::SOZU)) {
        if (const auto potion = search::potionRewardAction(gc)) { potion->execute(gc); return true; }
    }
    // Nothing left (keys only count when STS_COLLECT_KEYS is on): leaving is the only sensible action.
    if (r.cardRewardCount == 0 && r.relicCount == 0 && r.potionCount == 0
        && !(g_collectKeys && (r.emeraldKey || r.sapphireKey))) {
        search::GameAction(RT::SKIP).execute(gc); return true;
    }
    return false;
}

void runFullRunOocPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent,
                             bool restV, bool shopV) {
    // Diagnostic only (STS_OOC_MCTS_DECISION_LOG, STS_OOC_DECISION_TRACE): the
    // chain layer that handled this step. Never read by any policy.
    const auto tag = [](const char *name) { t_oocChainHandler = name; return true; };
    tag("unknown");
    if (const auto key = search::heartKeyAction(gc, g_collectKeys)) {
        tag("heart_key"); key->execute(gc); return;
    }
    if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::MATCH_AND_KEEP) {
        tag("match_and_keep");
        static const one_combat::PathHistory emptyPath;
        matchAndKeepPolicyStep(gc, agent, restV, shopV, t_curPath ? *t_curPath : emptyPath,
                               gc.seed, 0, nullptr);
        return;
    }
    if ((openTreasureChestRuleStep(gc) && tag("chest_rule")) || (takeRewardRelicRuleStep(gc) && tag("relic_rule"))) return;
    if (!t_oocHypotheticalStep && !t_oocContinuation && t_curPath
        && one_combat::oocGbmRankerPolicy(gc, *t_curPath) && tag("gbm_ranker")) return;
    const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    t_shopV = shopV;
    if (one_combat::oocActionNNPolicy(gc) && tag("action_nn")) {
    } else if (actFightProbeAllOocPolicy(gc) && tag("act_fight_probe")) {
    } else if (one_combat::oocMapRouteSearchPolicy(gc, agent) && tag("map_route_search")) {
    } else if (one_combat::oocOnePlyMapPolicy(gc, agent) && tag("v4_map")) {
    } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        tag(g_pathV ? "map_path_v" : "map_heuristic");
        if (g_pathV) one_combat::pathVPolicy(gc);
        else search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (one_combat::oocOnePlyEventPolicy(gc, agent) && tag("v4_event")) {
    } else if (g_eventV && gc.screenState == ScreenState::EVENT_SCREEN
               && gc.curEvent != Event::NEOW && one_combat::eventVPolicy(gc) && tag("event_v")) {
    } else if (gc.screenState == ScreenState::REWARDS) {
        if (!t_oocHypotheticalStep && !t_oocContinuation) { // a hypothetical or branch reward is not a real one
            one_combat::captureE2cPost(gc);
            one_combat::recordE2cScreenState(gc.screenState);
        }
        if (one_combat::collectFreeOocReward(gc, g_collectKeys)) { tag("free_reward"); }
        else if (actFightProbeDraftPolicy(gc)) { tag("act_fight_probe_draft"); }
        else if (bossGatedDraftPolicy(gc)) { tag("boss_gated_draft"); }
        else if (one_combat::oocOnePlyCardRewardPolicy(gc, agent)) { tag("v4_card_reward"); }
        else { tag("card_reward_heuristic"); one_combat::serverCardRewardPolicy(gc); }
    } else if (oocShopBeamPolicy(gc) && tag("shop_beam")) {
    } else if (one_combat::oocOnePlyShopPolicy(gc, agent) && tag("v4_shop")) {
    } else if (shopV && gc.screenState == ScreenState::SHOP_ROOM) {
        tag("shop_v_planner");
        one_combat::shopVPolicy(gc);
    } else if (shopV && gc.curRoom == Room::SHOP && inRemoveSelect) {
        tag("shop_remove_v");
        one_combat::removeSelectVPolicy(gc);
    } else if (one_combat::oocOnePlyRestPolicy(gc, agent) && tag("v4_rest")) {
    } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM
               && one_combat::restWinPolicy(gc) && tag("rest_win")) {
    } else if (one_combat::oocOnePlyUpgradeSelectPolicy(gc, agent) && tag("v4_upgrade_select")) {
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        tag("upgrade_select_win");
        one_combat::upgradeSelectWinPolicy(gc);
    } else if (restV && gc.screenState == ScreenState::REST_ROOM
               && one_combat::restVPolicy(gc) && tag("rest_v")) {
    } else if (restV && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        tag("upgrade_select_v");
        one_combat::upgradeSelectVPolicy(gc);
    } else if (one_combat::oocOnePlyBossRelicPolicy(gc, agent) && tag("v4_boss_relic")) {
    } else if (g_bossRelicV && gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        tag("boss_relic_v");
        one_combat::bossRelicVPolicy(gc);
    } else if (one_combat::oocOnePlyTreasurePolicy(gc, agent) && tag("v4_treasure")) {
    } else if (g_neowV && gc.screenState == ScreenState::EVENT_SCREEN
               && gc.curEvent == Event::NEOW) {
        tag("neow_v");
        one_combat::neowVPolicy(gc);
    } else {
        tag("agent_default");
        agent.stepOutOfCombatPolicy(gc);
    }
}

thread_local bool t_oocContinuation = false;

bool deployedRestV() {
    const char *d = std::getenv("STS_REST_V");
    return d && std::atoi(d) != 0;
}

long long deployedOocPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent) {
    long long firstBits = -1;
    auto previous = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = [&](std::uint32_t bits, const GameContext *target) {
        if (target == &gc && firstBits < 0) firstBits = bits;
        if (previous) previous(bits, target);
    };
    try {
        runFullRunOocPolicyStep(gc, agent, deployedRestV(), /*shopV=*/true);
    } catch (...) {
        search::g_onGameActionExecute = std::move(previous);
        throw;
    }
    search::g_onGameActionExecute = std::move(previous);
    return firstBits;
}

bool installRunForcedRelic(GameContext &gc, RelicId relic) {
    if (relic == RelicId::INVALID || gc.relics.has(relic)) return false;

    // GameContext::obtainRelic initializes a new Lizard Tail's native active
    // flag to 1. Match that state while retaining the force-run helper's
    // side-effect-free direct insertion for other relics.
    const int initialData = relic == RelicId::LIZARD_TAIL ? 1 : 0;
    gc.relics.add({relic, initialData});
    for (std::vector<RelicId> *pool : {&gc.commonRelicPool, &gc.uncommonRelicPool,
                                       &gc.rareRelicPool, &gc.shopRelicPool, &gc.bossRelicPool})
        pool->erase(std::remove(pool->begin(), pool->end(), relic), pool->end());
    return true;
}

// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via the ordered OOC policy chain).
RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                        bool e2cCapture) {
    const auto publicScorersBefore = one_combat::nativeOocPublicScorerCalls();
    if (one_combat::liveOocMctsEnabled()) {
        if (sims != 10000 || !search::nativeSilverBackendInstalled()
            || !search::nativeSilverExactRootBudgets() || search::nativeSilverAdaptiveEnabled()
            || search::nativeSilverReuseCap() != 32768)
            throw std::runtime_error("live OOC MCTS requires ordinary exact-10k Silver real combat with reuse cap 32768");
        if (e2cCapture) throw std::runtime_error("live OOC MCTS does not support combat corpus capture");
        // With live OOC MCTS, heart1 only serves as the tree prior (STS_OOC_MCTS_PRIOR=heart1);
        // real decisions stay with the search and its chain.
        if (one_combat::heart1::enabled() && !one_combat::liveOocMctsUsesHeart1()
                && !one_combat::liveOocSiblingCaptureEnabled())
            throw std::runtime_error("STS_OOC_HEART1 with live OOC MCTS requires STS_OOC_MCTS_PRIOR=heart1"
                                     " or STS_OOC_SIBLING_CAPTURE");
    }
    vDisconnect();
    t_oocStrategicTraceRows.clear();
    t_oocStrategicTraceDecision = 0;
    t_shopV = shopV;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    installRunForcedRelic(gc, g_forceRelic);

    PathHistory path;                // pv* features for V queries (train/serve parity)
    if (e2cCapture) {
        trainingRunStart();
        one_combat::beginE2cRun(seed, path);
    }
    one_combat::resetPathPolicyState();
    t_actFightProbeDecisionIdx = 0;
    t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;
    one_combat::LiveOocMctsMetrics mctsMetrics;
    std::uint64_t oocDecisionIndex = 0;
    bool clearedStopActBoss = false;
    int fightsLost = 0, fightsTotal = 0, deathCombat = -1, deathEncounter = -1;
    auto t0 = std::chrono::steady_clock::now();
    FloorProfile floorProfile;
    try {
    while (gc.outcome == GameOutcome::UNDECIDED) {
        floorProfile.advance(gc, mctsMetrics);
        path.update(gc);
        if (t_realRunContextObserver) t_realRunContextObserver(gc, path);
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            if (one_combat::liveOocMctsEnabled() && agent.simulationCountBase != 10000)
                throw std::runtime_error("live OOC MCTS real combat budget must remain 10000");
            BossEntryHook *const bossHook = battleRoom == Room::BOSS ? t_bossEntryHook : nullptr;
            if (bossHook) bossHook->before(gc, agent, path);
            const bool traceOoc = std::getenv("STS_OOC_DECISION_TRACE") != nullptr;
            nlohmann::json tracePre;
            if (traceOoc) tracePre = oocTraceState(gc);
            BattleContext bc{};
            // Silver initializes the battle itself so its observational
            // Runic-Dome hooks see the initial hidden intent lifecycle.
            const double combatWall = floorProfile.on() ? one_combat::runProfileWall() : 0;
            const double combatCpu = floorProfile.on() ? one_combat::oocProfileCpu() : 0;
            {
                one_combat::OocProfileScope combatProfile(one_combat::OocProfileBucket::RealCombat);
                agent.playoutBattle(gc, bc);
            }
            if (floorProfile.on()) floorProfile.combat(bc,
                one_combat::runProfileWall() - combatWall, one_combat::oocProfileCpu() - combatCpu);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) {
                ++fightsLost;
                if (deathCombat < 0) {
                    deathCombat = fightsTotal;
                    deathEncounter = (int)bc.encounter;
                }
            }
            if (one_combat::e2cCaptureActive())
                one_combat::beginE2cFight(fightsTotal - 1, gc, bc);
            one_combat::exitBattleWithE2cRawCapture(bc, gc);
            if (bossHook) bossHook->after(gc, bc);
            if (traceOoc)
                oocTraceEmit({{"seed", seed}, {"kind", "battle"}, {"fight", fightsTotal},
                              {"encounter", monsterEncounterEnumNames[static_cast<int>(bc.encounter)]},
                              {"won", bc.outcome == Outcome::PLAYER_VICTORY}, {"pre", tracePre},
                              {"post", oocTraceState(gc)}});
            // A20 Act 3 has two bosses: winning the first one leads straight into
            // the second, so the Act-3 stop waits for that fight.
            const bool a20FirstAct3BossWon = battleAct == 3 && gc.ascension >= 20
                && bc.encounter == gc.boss && bc.outcome == Outcome::PLAYER_VICTORY;
            if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS
                && !a20FirstAct3BossWon) {
                clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                break;
            }
        } else {
            const auto index = oocDecisionIndex++;
            const bool traceOoc = std::getenv("STS_OOC_DECISION_TRACE") != nullptr;
            nlohmann::json tracePre, traceOffer;
            if (traceOoc) {
                tracePre = oocTraceState(gc);
                traceOffer = oocTraceOffer(gc);
            }
            const char *traceBy = "chain";
            if (const auto key = search::heartKeyAction(gc, g_collectKeys)) {
                key->execute(gc); traceBy = "heart_key";
            } else if (one_combat::heart1::enabled() && !one_combat::liveOocMctsEnabled()
                    && one_combat::heart1::policyStep(gc)) {
                traceBy = "heart1";
            } else if (openTreasureChestRuleStep(gc)) {
                traceBy = "chest_rule";
            } else if (takeRewardRelicRuleStep(gc)) {
                traceBy = "relic_rule";
            } else if (one_combat::liveOocMctsTreeRules() && oocTreeRuleStep(gc)) {
                traceBy = "tree_rule";
            } else if (matchAndKeepPolicyStep(gc, agent, restV, shopV, path, seed, index,
                    one_combat::liveOocMctsEnabled() ? &mctsMetrics : nullptr)) {
                traceBy = "match_and_keep";
            } else {
                if (t_realOocDecisionObserver) one_combat::armOocPolicyTarget();
                if (one_combat::oocMctsPolicyStep(gc, path, seed, index, mctsMetrics)) traceBy = "mcts";
                else runFullRunOocPolicyStep(gc, agent, restV, shopV);
            }
            if (t_realOocDecisionObserver) t_realOocDecisionObserver(index, traceBy);
            if (traceOoc)
                oocTraceEmit({{"seed", seed}, {"kind", "ooc"}, {"idx", index}, {"by", traceBy},
                              {"handler", std::string(traceBy) == "chain" ? t_oocChainHandler : ""},
                              {"pre", tracePre}, {"offer", traceOffer}, {"post", oocTraceState(gc)}});
        }
    }
    } catch (const std::exception &e) {
        floorProfile.finish(mctsMetrics, "abort", e.what());
        throw;
    }
    floorProfile.finish(mctsMetrics, clearedStopActBoss ? "stop_act_victory"
        : gc.outcome == GameOutcome::PLAYER_VICTORY ? "victory"
        : gc.outcome == GameOutcome::PLAYER_LOSS ? "death" : "stopped");
    auto t1 = std::chrono::steady_clock::now();
    const RunResult result { clearedStopActBoss || search::runGoalVictory(gc, g_collectKeys, g_stopAfterAct),
                              gc.floorNum, gc.act, gc.curHp, gc.maxHp,
                              fightsLost,
                              std::chrono::duration<double>(t1 - t0).count(),
                              deathCombat, deathEncounter };
    if (!g_oocStrategicTracePath.empty() && !t_oocStrategicTraceRows.empty()) {
        std::lock_guard<std::mutex> lock(g_oocStrategicTraceMutex);
        std::ofstream f(g_oocStrategicTracePath, std::ios::app);
        if (f) {
            if (f.tellp() == 0)
                f << "seed,decIdx,act,floor,screen,nActions,actionBits,qValues,bestIdx,bestSecondMargin,threshold,heurIdx,takeIdx,rule,owned,collectKeys,stopAfterAct,won,finalFloor,finalHp\n";
            std::istringstream in(t_oocStrategicTraceRows);
            std::string line;
            while (std::getline(in, line)) if (!line.empty())
                f << line << ',' << (g_collectKeys ? 1 : 0) << ',' << g_stopAfterAct << ','
                  << (result.won ? 1 : 0) << ',' << result.floor << ',' << result.hpEnd << '\n';
        }
    }
    one_combat::writeLiveOocMctsTrace(seed, mctsMetrics, fightsTotal);
    if (one_combat::nativeOocPublicFutureCount() > 0) {
        std::lock_guard<std::mutex> lock(g_oocStrategicTraceMutex);
        std::cout << "[public OOC receipt seed=" << seed
                  << " futures=" << one_combat::nativeOocPublicFutureCount()
                  << " scorers=" << one_combat::nativeOocPublicScorerCalls() - publicScorersBefore
                  << "]\n";
    }
    if (e2cCapture) {
        // Same effective label semantics as this function's RunResult (honors an
        // explicit STS_STOP_AFTER_ACT horizon without labelling solely from
        // gc.outcome). Integrity still rejects genuinely unresolved runs and any
        // simulator-health failure, so E2c does not weaken the shared predicate.
        const bool decided = result.won || gc.outcome != GameOutcome::UNDECIDED;
        const bool validRun = trainingRunValid(decided);
        one_combat::finishE2cRun(validRun, result.won, result.floor, result.hpEnd);
    }
    vDisconnect();
    return result;
}
