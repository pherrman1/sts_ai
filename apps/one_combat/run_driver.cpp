#include "sim/search/RunGoal.h"
#include "run_driver.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <map>
#include <mutex>
#include <random>
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
#include "ooc_v4_encoding.h"
#include "sim/search/PotionRewardPolicy.h"
#include "ooc_profile.h"
#include "run_profile.h"
#include "run_features.h"
#include "driver_shared.h"

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
thread_local std::function<const char *(sts::GameContext &)> t_oocDecisionOverride;
thread_local std::function<void(const sts::GameContext &, const sts::BattleContext &,
    int, const std::optional<one_combat::CombatTransitionRecord> &)> t_realCombatObserver;

thread_local MatchAndKeepWantCache t_matchAndKeepWant;

// STS_MATCH_AND_KEEP_HEART1: unset or 1 = with STS_OOC_HEART1 loaded, a Match
// and Keep card that live OOC MCTS does not value is valued by heart1 as one
// argmax rollout step on the lone offer; 0 = the V4/one-ply chain (before
// 2026-10-17). Read per valuation, so tests can switch it.
static bool matchAndKeepHeart1() {
    const char *value = std::getenv("STS_MATCH_AND_KEEP_HEART1");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_MATCH_AND_KEEP_HEART1 must be 0 or 1");
}

// STS_MATCH_AND_KEEP_CURSE_FIX: unset or 1 = a curse is never a wanted Match
// and Keep pair; 0 = curses are valued like any card (before 2026-10-17). The
// lone-card-reward valuation is out of distribution for curses: V4 and heart1
// both took Shame, Writhe or Regret there.
static bool matchAndKeepCurseFix() {
    const char *value = std::getenv("STS_MATCH_AND_KEEP_CURSE_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_MATCH_AND_KEEP_CURSE_FIX must be 0 or 1");
}

static bool matchAndKeepHeart1Step(GameContext &offer) {
    if (!one_combat::heart1::enabled() || !matchAndKeepHeart1()) return false;
    const auto actions = one_combat::v4CandidateActions(offer);
    const auto logits = one_combat::heart1::priorLogits(offer, actions, nullptr);
    if (!logits || logits->size() != actions.size()) return false;
    actions[std::max_element(logits->begin(), logits->end()) - logits->begin()].execute(offer);
    return true;
}

bool matchAndKeepPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent, bool restV, bool shopV,
                            const one_combat::PathHistory &path, std::uint64_t runSeed,
                            std::uint64_t decisionIndex, one_combat::LiveOocMctsMetrics *mctsMetrics) {
    if (gc.screenState != ScreenState::EVENT_SCREEN || gc.curEvent != Event::MATCH_AND_KEEP) return false;
    auto &cache = t_matchAndKeepWant;
    if (cache.seed != gc.seed || cache.act != gc.act || cache.floor != gc.floorNum) {
        cache = MatchAndKeepWantCache{gc.seed, gc.act, gc.floorNum, {}};
    }
    const auto want = [&](const Card &card) {
        if (card.getType() == CardType::CURSE && matchAndKeepCurseFix()) return false;
        const auto key = std::make_pair(static_cast<int>(card.id), card.isUpgraded());
        if (const auto it = cache.want.find(key); it != cache.want.end()) return it->second;
        // The active primary guide values the card as a lone card reward:
        // live OOC MCTS when enabled, else heart1 when loaded, else the
        // ordinary V4/one-ply chain.
        const bool take = one_combat::oocHypotheticalCardTaken(gc, path, card, [&](GameContext &offer) {
            if (mctsMetrics) {
                const std::uint64_t index = (decisionIndex << 12)
                    ^ (static_cast<std::uint64_t>(card.id) << 1) ^ std::uint64_t(card.isUpgraded());
                if (one_combat::oocMctsPolicyStep(offer, path, runSeed, index, *mctsMetrics)) return;
            }
            if (matchAndKeepHeart1Step(offer)) return;
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

thread_local const char *t_oocChainHandler = "";
const char *lastOocChainHandler() { return t_oocChainHandler; }

void runFullRunOocPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent,
                             bool restV, bool shopV) {
    // Diagnostic only (STS_OOC_MCTS_DECISION_LOG, STS_OOC_DECISION_TRACE): the
    // chain layer that handled this step. Never read by any policy.
    const auto tag = [](const char *name) { t_oocChainHandler = name; return true; };
    tag("unknown");
    if (const auto key = search::heartKeyAction(gc, g_collectKeys)) {
        tag("heart_key"); key->execute(gc); return;
    }
    // STS_KEY_EMERALD=mask: the map handlers below enumerate unmasked edges, so
    // the chain takes the first edge that still reaches the burning elite.
    if (gc.screenState == ScreenState::MAP_SCREEN && !search::heartKeyRules().isAdr0041()) {
        std::optional<search::GameAction> allowed;
        bool masked = false;
        for (const auto a : search::GameAction::getAllActionsInState(gc)) {
            if (!a.isValidAction(gc)) continue;
            if (!search::heartKeyActionAllowed(gc, g_collectKeys, a)) masked = true;
            else if (!allowed) allowed = a;
        }
        if (masked && allowed) { tag("heart_key_mask"); allowed->execute(gc); return; }
    }
    if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::MATCH_AND_KEEP) {
        tag("match_and_keep");
        static const one_combat::PathHistory emptyPath;
        matchAndKeepPolicyStep(gc, agent, restV, shopV, t_curPath ? *t_curPath : emptyPath,
                               gc.seed, 0, nullptr);
        return;
    }
    if (const auto chest = treasureChestRuleAction(gc)) { tag("chest_rule"); chest->execute(gc); return; }
    if (const auto relic = rewardRelicRuleAction(gc)) { tag("relic_rule"); relic->execute(gc); return; }
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
thread_local bool t_counterfactualHeart1 = false;

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

void beginRealOocChainRun(bool shopV) {
    t_oocStrategicTraceRows.clear();
    t_oocStrategicTraceDecision = 0;
    t_shopV = shopV;
    one_combat::resetPathPolicyState();
    t_actFightProbeDecisionIdx = 0;
    t_tokCheckPending = g_oocStrategicTokCheck;
}

std::optional<ForcedBossRelic> parseForcedBossRelic(const char *value) {
    if (!value || !*value) return std::nullopt;
    const std::string text(value);
    if (text.size() != 3 || (text[0] != '1' && text[0] != '2') || text[1] != ':' || text[2] < '0' || text[2] > '3')
        throw std::runtime_error("STS_OOC_FORCE_BOSS_RELIC must be ACT:CHOICE with ACT 1 or 2 and CHOICE 0-3 (3 = skip)");
    return ForcedBossRelic{text[0] - '0', text[2] - '0'};
}

namespace {
const std::optional<ForcedBossRelic> &forcedBossRelic() {
    static const auto forced = parseForcedBossRelic(std::getenv("STS_OOC_FORCE_BOSS_RELIC"));
    return forced;
}
thread_local bool t_forcedBossRelicTaken = false;
}

int forcedBossRelicSelfTest() {
    const auto check = [](bool ok, const char *what) {
        if (!ok) throw std::runtime_error(std::string("forced boss relic selftest: ") + what);
    };
    check(!parseForcedBossRelic(nullptr) && !parseForcedBossRelic(""), "unset must be off");
    const auto skip = parseForcedBossRelic("2:3");
    check(skip && skip->act == 2 && skip->choice == 3, "2:3 parse");
    for (const char *bad : {"3:0", "0:1", "1:4", "1-2", "1:", "1:01", "a:1"}) {
        bool refused = false;
        try { parseForcedBossRelic(bad); } catch (const std::runtime_error &) { refused = true; }
        check(refused, bad);
    }
    std::cout << "forced boss relic selftest passed\n";
    return 0;
}

namespace {
const char *realOocChainStepBody(GameContext &gc, search::ScumSearchAgent2 &agent, bool restV, bool shopV,
                                 const one_combat::PathHistory &path, std::uint64_t seed, std::uint64_t index,
                                 one_combat::LiveOocMctsMetrics &mctsMetrics) {
    // Research observer (STS_OOC_CAMPFIRE_PRICE, default off): prices every option of a rest site before anything
    // decides it. Play is unchanged. A rule-forced Ruby site has no search candidates and records a price error.
    one_combat::observeOocCampfirePrice(gc, path, seed, index);
    if (const auto &forced = forcedBossRelic(); forced && gc.screenState == ScreenState::BOSS_RELIC_REWARDS
            && gc.act == forced->act) {
        if (t_forcedBossRelicTaken) throw std::runtime_error("STS_OOC_FORCE_BOSS_RELIC: second boss-relic root in the act");
        t_forcedBossRelicTaken = true;
        search::GameAction(forced->choice).execute(gc);
        return "forced_boss_relic";
    }
    if (const auto key = search::heartKeyAction(gc, g_collectKeys)) {
        key->execute(gc);
        return "heart_key";
    }
    if (one_combat::heart1::enabled() && !one_combat::liveOocMctsEnabled() && one_combat::heart1::policyStep(gc))
        return "heart1";
    if (const auto chest = treasureChestRuleAction(gc)) {
        chest->execute(gc);
        return "chest_rule";
    }
    if (const auto relic = rewardRelicRuleAction(gc)) {
        relic->execute(gc);
        return "relic_rule";
    }
    if (one_combat::liveOocMctsTreeRules() && oocTreeRuleStep(gc)) return "tree_rule";
    if (matchAndKeepPolicyStep(gc, agent, restV, shopV, path, seed, index,
                               one_combat::liveOocMctsEnabled() ? &mctsMetrics : nullptr))
        return "match_and_keep";
    // STS_OOC_MCTS_SCREENS (#854; A20 default map only, ADR-TBD): after the same rule chain, student_sel decides
    // unsearched screens.
    if (one_combat::liveOocMctsScreenExcluded(gc) && one_combat::heart1::policyStep(gc)) return "heart1_screen";
    if (t_realOocDecisionObserver) one_combat::armOocPolicyTarget();
    if (one_combat::oocMctsPolicyStep(gc, path, seed, index, mctsMetrics)) return "mcts";
    if (one_combat::liveOocMctsHeart1Fallback(gc) && one_combat::heart1::policyStep(gc)) return "heart1_fallback";
    runFullRunOocPolicyStep(gc, agent, restV, shopV);
    return "chain";
}
thread_local bool t_rootProbeActive = false;
}

std::optional<ForcedDecision> parseForcedDecision(const char *value) {
    if (!value || !*value) return std::nullopt;
    const std::string text(value);
    const auto a = text.find(':');
    const auto b = a == std::string::npos ? std::string::npos : text.find(':', a + 1);
    const auto digits = [](const std::string &t, std::size_t limit) {
        return !t.empty() && t.size() <= limit && t.find_first_not_of("0123456789") == std::string::npos;
    };
    if (b == std::string::npos || !digits(text.substr(0, a), 6) || !digits(text.substr(a + 1, b - a - 1), 19)
            || b + 1 >= text.size())
        throw std::runtime_error("STS_OOC_FORCE_DECISION must be INDEX:SALT:KEY (KEY a root candidate key or - for the"
                                 " production choice; SALT 0 keeps the game's own future)");
    return ForcedDecision{std::stoull(text.substr(0, a)), std::stoull(text.substr(a + 1, b - a - 1)), text.substr(b + 1)};
}

namespace {
const std::optional<ForcedDecision> &forcedDecision() {
    static const auto forced = parseForcedDecision(std::getenv("STS_OOC_FORCE_DECISION"));
    return forced;
}
thread_local bool t_forcedDecisionTaken = false;
}

int forcedDecisionSelfTest() {
    const auto check = [](bool ok, const char *what) {
        if (!ok) throw std::runtime_error(std::string("forced decision selftest: ") + what);
    };
    check(!parseForcedDecision(nullptr) && !parseForcedDecision(""), "unset must be off");
    const auto keyed = parseForcedDecision("12:7:ooc:v1:effect=5:source=7");
    check(keyed && keyed->index == 12 && keyed->salt == 7 && keyed->key == "ooc:v1:effect=5:source=7", "keyed parse");
    const auto production = parseForcedDecision("0:0:-");
    check(production && production->index == 0 && production->salt == 0 && production->key == "-", "production parse");
    for (const char *bad : {"1", "1:2", "1:2:", "a:2:k", "1:b:k", ":2:k", "1::k"}) {
        bool refused = false;
        try { parseForcedDecision(bad); } catch (const std::runtime_error &) { refused = true; }
        check(refused, bad);
    }
    std::cout << "forced decision selftest passed\n";
    return 0;
}

const char *realOocChainStep(GameContext &gc, search::ScumSearchAgent2 &agent, bool restV, bool shopV,
                             const one_combat::PathHistory &path, std::uint64_t seed, std::uint64_t index,
                             one_combat::LiveOocMctsMetrics &mctsMetrics) {
    // Research observer (STS_OOC_ROOT_PROBE, #882, default off): prior, searches and the production choice at the
    // listed decision indices, all in forked children. Play is unchanged.
    if (!t_rootProbeActive && one_combat::rootProbeIndex(index)) {
        one_combat::observeOocRootProbe(gc, path, seed, index, [&](GameContext &copy) {
            t_rootProbeActive = true;   // only ever inside the probe's forked child
            realOocChainStepBody(copy, agent, restV, shopV, path, seed, index, mctsMetrics);
        });
    }
    const auto &forced = forcedDecision();
    if (!forced || t_rootProbeActive || index != forced->index)
        return realOocChainStepBody(gc, agent, restV, shopV, path, seed, index, mctsMetrics);
    // STS_OOC_FORCE_DECISION (research, #882 forks): this decision takes KEY (or the production choice for -), then
    // a SALT above 0 redraws the hidden future as OOC MCTS does for its own continuations; forks of one root share it.
    if (t_forcedDecisionTaken) throw std::runtime_error("STS_OOC_FORCE_DECISION: decision index reached twice");
    t_forcedDecisionTaken = true;
    const char *by = "forced_decision";
    if (forced->key == "-") by = realOocChainStepBody(gc, agent, restV, shopV, path, seed, index, mctsMetrics);
    else {
        std::string error;
        if (!one_combat::executeOocRootKey(gc, path, forced->key, error))
            throw std::runtime_error("STS_OOC_FORCE_DECISION: " + error);
    }
    if (forced->salt) {
        std::seed_seq seq{forced->salt, std::uint64_t(0x464f524b4544ULL)};   // "FORKED"
        std::mt19937_64 rng(seq);
        one_combat::resampleCounterfactualFuture(gc, rng);
    }
    return by;
}

// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via the ordered OOC policy chain).
RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                        bool e2cCapture) {
    const auto publicScorersBefore = one_combat::nativeOocPublicScorerCalls();
    if (one_combat::liveOocMctsRealLearnedStop(asc)) {
        // Default at A20 (ADR-0054): real combats stop learned (ADR-0051; the A20 CTM and its Act-4 survival
        // model were fit on learned-stop outcomes). Imagined fights keep their flat budget
        // override; exact root budgets stay on so their boss budgets stay unmultiplied.
        if (sims != 10000 || !search::nativeSilverBackendInstalled()
            || !search::nativeSilverExactRootBudgets() || search::nativeSilverAdaptiveEnabled()
            || !search::nativeSilverLearnedStopEnabled() || search::nativeSilverLearnedStopBossFallback()
            || search::nativeSilverLearnedStopBossMax() != 0 || search::nativeSilverReuseCap() != 32768)
            throw std::runtime_error("STS_OOC_MCTS_REAL_LEARNED_STOP (default on at A20) requires learned-stop Silver real"
                                     " combat with exact root budgets, no adaptive or boss fallback/max, reuse cap 32768;"
                                     " STS_OOC_MCTS_REAL_LEARNED_STOP=0 restores flat exact 10k");
    } else if (one_combat::liveOocMctsEnabled()) {
        if (sims != 10000 || !search::nativeSilverBackendInstalled()
            || !search::nativeSilverExactRootBudgets() || search::nativeSilverAdaptiveEnabled()
            || search::nativeSilverLearnedStopEnabled() || search::nativeSilverReuseCap() != 32768)
            throw std::runtime_error("live OOC MCTS requires ordinary exact-10k Silver real combat with reuse cap 32768");
    }
    if (one_combat::liveOocMctsEnabled()) {
        if (e2cCapture) throw std::runtime_error("live OOC MCTS does not support combat corpus capture");
        // With live OOC MCTS, heart1 only serves as the tree prior (STS_OOC_MCTS_PRIOR=heart1);
        // real decisions stay with the search and its chain.
        if (one_combat::heart1::enabled() && !one_combat::liveOocMctsUsesHeart1()
                && !one_combat::liveOocSiblingCaptureEnabled())
            throw std::runtime_error("STS_OOC_HEART1 with live OOC MCTS requires STS_OOC_MCTS_PRIOR=heart1"
                                     " or STS_OOC_SIBLING_CAPTURE");
    }
    vDisconnect();
    t_forcedBossRelicTaken = false;
    t_forcedDecisionTaken = false;
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
    beginRealOocChainRun(shopV);
    t_curPath = &path;
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
            std::optional<GameContext> combatPre;
            if (t_realCombatObserver) combatPre = gc;
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
            if (combatPre) {
                std::optional<one_combat::CombatTransitionRecord> record;
                int rawCaptureCount = 0;
                {
                    one_combat::CombatTransitionRawObserverScope scope(
                        [&](const BattleContext &ended, GameContext &raw) {
                            if (++rawCaptureCount == 1)
                                record = one_combat::captureCombatTransition(*combatPre, ended, raw);
                        });
                    one_combat::exitBattleWithE2cRawCapture(bc, gc);
                }
                t_realCombatObserver(*combatPre, bc, rawCaptureCount, record);
            } else one_combat::exitBattleWithE2cRawCapture(bc, gc);
            if (bossHook) bossHook->after(gc, bc);
            if (traceOoc)
                oocTraceEmit({{"seed", seed}, {"kind", "battle"}, {"fight", fightsTotal},
                              {"encounter", monsterEncounterEnumNames[static_cast<int>(bc.encounter)]},
                              {"won", bc.outcome == Outcome::PLAYER_VICTORY},
                              {"outcome", static_cast<int>(bc.outcome)}, {"turns", bc.turn},
                              {"room", battleRoom == Room::MONSTER ? "NORMAL" : battleRoom == Room::ELITE ? "ELITE"
                                          : battleRoom == Room::BOSS ? "BOSS" : "OTHER"},
                              {"escaped", bc.smokeBombUsed}, {"pre", tracePre},
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
            // Non-ADR-0041 key variants mask some actions; report a policy that ignored the mask.
            std::vector<int> keyMaskAllowedX;
            if (!search::heartKeyRules().isAdr0041() && gc.screenState == ScreenState::MAP_SCREEN) {
                bool masked = false;
                for (const auto a : search::GameAction::getAllActionsInState(gc)) {
                    if (!a.isValidAction(gc)) continue;
                    if (search::heartKeyActionAllowed(gc, g_collectKeys, a)) keyMaskAllowedX.push_back(a.getIdx1());
                    else masked = true;
                }
                if (!masked) keyMaskAllowedX.clear();
            }
            const int keyMaskFloor = gc.floorNum;
            const char *overrideBy = t_oocDecisionOverride ? t_oocDecisionOverride(gc) : nullptr;
            traceBy = overrideBy ? overrideBy
                                 : realOocChainStep(gc, agent, restV, shopV, path, seed, index, mctsMetrics);
            if (!keyMaskAllowedX.empty() && gc.floorNum != keyMaskFloor
                    && std::find(keyMaskAllowedX.begin(), keyMaskAllowedX.end(), gc.curMapNodeX) == keyMaskAllowedX.end())
                std::fprintf(stderr, "heart_key_mask_violation seed=%llu floor=%d by=%s handler=%s x=%d\n",
                             static_cast<unsigned long long>(seed), keyMaskFloor, traceBy, t_oocChainHandler,
                             gc.curMapNodeX);
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
    // A fork whose replay never reached its boss-relic root is not a fork of the source game.
    if (forcedBossRelic() && !t_forcedBossRelicTaken)
        throw std::runtime_error("STS_OOC_FORCE_BOSS_RELIC: the run ended before the act's boss-relic root");
    if (forcedDecision() && !t_forcedDecisionTaken)
        throw std::runtime_error("STS_OOC_FORCE_DECISION: the run ended before the forced decision index");
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
