// Live-action boundary for the isolated Silver combat model.
// Adapted integration code; the search/simulator implementation remains
// daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverLiveBackend.h"

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSemanticAction.h"

namespace sts::search {

thread_local SilverLiveDiagnostics g_silverLiveDiagnostics {};

namespace {

struct SilverLiveOptions {
    silver_bridge::SilverReuseCapMode reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
    std::string scalingDiagnosticFile;
    std::string stickyQualityFile;
    std::string rootDiagnosticFile;
    int rootDiagnosticMaxPerSeed = 8;
    std::int64_t rootDiagnosticReferenceBudget = 25000;
    int rootDiagnosticReplicates = 2;
    std::string leafVNetLogFile;
    std::string leafVNetModel = "models/v_combat_7k_tuned.txt";
    int leafVNetSample = 16;
    int leafVNetMaxPerCombat = 5000;
    bool leafVNetDirect = false;
    double leafVNetAffineA = 1.0;
    double leafVNetAffineB = 0.0;
    bool installed = false;
};

SilverLiveOptions g_silverLiveOptions;
std::mutex g_scalingDiagnosticMutex;
bool g_scalingDiagnosticHeaderWritten = false;
std::mutex g_stickyQualityMutex;
bool g_stickyQualityHeaderWritten = false;
bool g_stickyQualitySummaryHeaderWritten = false;
std::mutex g_rootDiagnosticMutex;
bool g_rootDiagnosticHeaderWritten = false;
std::mutex g_leafVNetLogMutex;
bool g_leafVNetLogHeaderWritten = false;
bool g_stickyQualityActionTraceForTest = false;
std::mutex g_stickyQualitySelectionMutex;
std::unordered_map<std::uint64_t, int> g_stickyQualitySelectionsByRunSeed;
std::unordered_map<std::uint64_t, int> g_rootDiagnosticSelectionsByRunSeed;
struct StickyQualityTestBudgets { std::int64_t fresh = 0, ref25 = 0, ref50 = 0; };
StickyQualityTestBudgets g_stickyQualityTestBudgets;
constexpr const char *kScalingDiagnosticHeader =
    "run_seed,floor,encounter,combat_decision_ordinal,transaction_subdecision_ordinal,turn,input_state,configured_simulations,had_predecessor,reroot_attempted,exact_candidate_found,exact_reroot,fallback,fallback_reason,configured_cap_mode,configured_cap,allocated_nodes_before_root,active_nodes_before_root,allocated_nodes_after_search,active_nodes_after_search,inherited_visits,simulations_added,nodes_created,root_visits_after_search,chosen_edge_visits";
constexpr const char *kStickyQualityHeader =
    "run_seed,act,floor,encounter,room_type,combat_decision_ordinal,turn,input_state,allocated_nodes_before_root,active_nodes_before_root,inherited_visits,configured_cap,active_simulations_added,active_nodes_created,fresh_budget,ref25_budget,ref50_budget,active_action_fingerprint,fresh_action_fingerprint,ref25_action_fingerprint,ref50_action_fingerprint,ref25_ref50_agree,fresh_ref50_agree,active_ref50_agree,fresh_active_disagree,fresh_wall_ms,ref25_wall_ms,ref50_wall_ms,fresh_nodes_created,fresh_simulations_added,ref25_nodes_created,ref25_simulations_added,ref50_nodes_created,ref50_simulations_added,ref25_root_action_summaries,ref50_root_action_summaries,q_diagnostic_available,ref50_chosen_selection_q,active_ref50_selection_q,fresh_ref50_selection_q,ref50_q_gap_active,ref50_q_gap_fresh,ref50_q_gap_active_minus_fresh";
constexpr const char *kStickyQualitySummaryHeader =
    "run_seed,floor,encounter,sticky_eligible_ordinary_decisions,selected_evaluated_decisions,excluded_transaction_subdecisions";
constexpr const char *kRootDiagnosticHeader =
    "run_seed,act,floor,encounter,room_type,combat_decision_ordinal,turn,input_state,cur_hp,max_hp,potion_count,action_type,stochastic,action_fingerprint,chosen_1k,chosen_1k_visits,chosen_1k_q,chosen_37k,chosen_37k_visits,chosen_37k_q,active_reroot_exact,active_fallback_reason,active_inherited_visits,reference_budget,reference_replicates,reference_value,reference_value_stddev,reference_rollout_win_rate,reference_rollout_actions,reference_rollout_turns,reference_rollout_calls,reference_terminal_wins,reference_terminal_losses,reference_utility_sum,reference_win_bonus,reference_hp,reference_potion,reference_turn_penalty,reference_death_save,reference_gold,reference_max_hp,reference_parasite_penalty,reference_monster_damage,reference_alive,reference_energy_waste,reference_draw,reference_survival,current_1k_rollout_calls,current_1k_terminal_wins,current_1k_terminal_losses,current_1k_rollout_actions,current_1k_rollout_turns,current_1k_utility_sum,current_1k_win_bonus_sum,current_1k_hp_sum,current_1k_potion_sum,current_1k_turn_penalty_sum,current_1k_death_save_sum,current_1k_gold_sum,current_1k_max_hp_sum,current_1k_parasite_penalty_sum,current_1k_monster_damage_sum,current_1k_alive_sum,current_1k_energy_waste_sum,current_1k_draw_sum,current_1k_survival_sum,current_37k_rollout_calls,current_37k_terminal_wins,current_37k_terminal_losses,current_37k_rollout_actions,current_37k_rollout_turns,current_37k_utility_sum,current_37k_win_bonus_sum,current_37k_hp_sum,current_37k_potion_sum,current_37k_turn_penalty_sum,current_37k_death_save_sum,current_37k_gold_sum,current_37k_max_hp_sum,current_37k_parasite_penalty_sum,current_37k_monster_damage_sum,current_37k_alive_sum,current_37k_energy_waste_sum,current_37k_draw_sum,current_37k_survival_sum";
constexpr const char *kLeafVNetHeader =
    "run_seed,act,floor,encounter,combat_decision_ordinal,isolated_search_seed,root_state_hash,parent_state_hash,leaf_state_hash,depth,action_count_before_rollout,leaf_turn,leaf_input_state,leaf_cur_hp,leaf_max_hp,vnet_raw_prediction,rollout_terminal_outcome,rollout_utility,rollout_action_count,rollout_turn_delta,rollout_wall_micros";

void parseSilverLiveOptions() {
    SilverLiveOptions options;
    if (const char *raw = std::getenv("STS_SILVER_REUSE_CAP_MODE")) {
        const std::string mode(raw);
        if (mode.empty() || mode == "allocated") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
        } else if (mode == "active") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::ACTIVE;
        } else if (mode == "none") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
        } else {
            throw std::invalid_argument("STS_SILVER_REUSE_CAP_MODE must be 'allocated', 'active', or 'none' (got '"
                                        + mode + "')");
        }
    }
    if (const char *raw = std::getenv("STS_SILVER_SCALING_DIAG_FILE"))
        options.scalingDiagnosticFile = raw;
    if (const char *raw = std::getenv("STS_SILVER_STICKY_QUALITY_FILE"))
        options.stickyQualityFile = raw;
    if (const char *raw = std::getenv("STS_SILVER_ROOT_DIAG_FILE"))
        options.rootDiagnosticFile = raw;
    if (const char *raw = std::getenv("STS_SILVER_ROOT_DIAG_MAX_PER_SEED"))
        options.rootDiagnosticMaxPerSeed = std::atoi(raw);
    if (const char *raw = std::getenv("STS_SILVER_ROOT_DIAG_REF_BUDGET"))
        options.rootDiagnosticReferenceBudget = std::atoll(raw);
    if (const char *raw = std::getenv("STS_SILVER_ROOT_DIAG_REPLICATES"))
        options.rootDiagnosticReplicates = std::atoi(raw);
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_LOG")) options.leafVNetLogFile = raw;
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_MODEL")) options.leafVNetModel = raw;
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_SAMPLE")) options.leafVNetSample = std::atoi(raw);
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_MAX_PER_COMBAT")) options.leafVNetMaxPerCombat = std::atoi(raw);
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_DIRECT")) options.leafVNetDirect = std::atoi(raw) != 0;
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_A")) options.leafVNetAffineA = std::atof(raw);
    if (const char *raw = std::getenv("STS_SILVER_VNET_LEAF_B")) options.leafVNetAffineB = std::atof(raw);
    if (!options.rootDiagnosticFile.empty()
            && (options.rootDiagnosticMaxPerSeed <= 0
                || options.rootDiagnosticReferenceBudget <= 0
                || options.rootDiagnosticReplicates <= 0)) {
        throw std::invalid_argument(
            "STS_SILVER_ROOT_DIAG_MAX_PER_SEED, _REF_BUDGET, and _REPLICATES must be positive");
    }
    if (!options.leafVNetLogFile.empty() || options.leafVNetDirect) {
        if (options.leafVNetSample <= 0 || options.leafVNetMaxPerCombat <= 0)
            throw std::invalid_argument("STS_SILVER_VNET_LEAF_SAMPLE and _MAX_PER_COMBAT must be positive");
    }
    if (!options.stickyQualityFile.empty()
            && options.reuseCapMode != silver_bridge::SilverReuseCapMode::ACTIVE) {
        throw std::invalid_argument(
            "STS_SILVER_STICKY_QUALITY_FILE requires STS_SILVER_REUSE_CAP_MODE=active");
    }
    options.installed = true;
    g_silverLiveOptions = std::move(options);
}

struct ScalingDiagnosticRow {
    std::uint64_t runSeed = 0;
    int floor = 0, encounter = 0, combatDecisionOrdinal = 0, transactionSubdecisionOrdinal = -1;
    int turn = 0, inputState = 0;
    std::int64_t configuredSimulations = 0;
    silver_bridge::SilverSearchDecisionDiagnostic diagnostic;
};

void writeScalingDiagnostics(const std::vector<ScalingDiagnosticRow> &rows) {
    if (rows.empty()) return;
    std::lock_guard<std::mutex> lock(g_scalingDiagnosticMutex);
    bool empty = false;
    if (!g_scalingDiagnosticHeaderWritten) {
        std::ifstream existing(g_silverLiveOptions.scalingDiagnosticFile, std::ios::binary);
        empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
        if (!empty) {
            std::string header;
            std::getline(existing, header);
            if (header != kScalingDiagnosticHeader) {
                throw std::runtime_error("STS_SILVER_SCALING_DIAG_FILE has an incompatible existing header: "
                                         + g_silverLiveOptions.scalingDiagnosticFile);
            }
        }
    }
    std::ofstream out(g_silverLiveOptions.scalingDiagnosticFile, std::ios::app);
    if (!out) throw std::runtime_error("cannot open STS_SILVER_SCALING_DIAG_FILE: "
                                       + g_silverLiveOptions.scalingDiagnosticFile);
    if (!g_scalingDiagnosticHeaderWritten && empty) {
        out << kScalingDiagnosticHeader << '\n';
    }
    for (const auto &row : rows) {
        const auto &d = row.diagnostic;
        out << row.runSeed << ',' << row.floor << ',' << row.encounter << ','
            << row.combatDecisionOrdinal << ',' << row.transactionSubdecisionOrdinal << ','
            << row.turn << ',' << row.inputState << ',' << row.configuredSimulations << ','
            << (d.hadPredecessor ? 1 : 0) << ',' << (d.rerootAttempted ? 1 : 0) << ','
            << (d.exactCandidateFound ? 1 : 0) << ',' << (d.exactReroot ? 1 : 0) << ','
            << (d.fallback ? 1 : 0) << ','
            << silver_bridge::silverRerootFallbackReasonName(d.fallbackReason) << ','
            << silver_bridge::silverReuseCapModeName(d.configuredCapMode) << ','
            << d.configuredCap << ',' << d.allocatedNodesBeforeRoot << ',' << d.activeNodesBeforeRoot << ','
            << d.allocatedNodesAfterSearch << ',' << d.activeNodesAfterSearch << ','
            << d.inheritedVisits << ',' << d.simulationsAdded << ',' << d.nodesCreated << ',' << d.rootVisitsAfterSearch << ','
            << d.chosenEdgeVisits << '\n';
    }
    out.flush();
    if (!out) throw std::runtime_error("cannot write STS_SILVER_SCALING_DIAG_FILE: "
                                       + g_silverLiveOptions.scalingDiagnosticFile);
    g_scalingDiagnosticHeaderWritten = true;
}

struct StickyQualityBudgets {
    std::int64_t fresh = 3700;
    std::int64_t ref25 = 25000;
    std::int64_t ref50 = 50000;
};

StickyQualityBudgets stickyQualityBudgets() {
    if (g_stickyQualityTestBudgets.fresh > 0 && g_stickyQualityTestBudgets.ref25 > 0
            && g_stickyQualityTestBudgets.ref50 > 0) {
        return {g_stickyQualityTestBudgets.fresh, g_stickyQualityTestBudgets.ref25,
                g_stickyQualityTestBudgets.ref50};
    }
    return {};
}

bool stickyEligible(const silver_bridge::SilverSearchDecisionDiagnostic &d) {
    return d.exactCandidateFound
        && d.allocatedNodesBeforeRoot >= d.configuredCap
        && d.activeNodesBeforeRoot < d.configuredCap;
}

bool sampledStickyDecision(std::uint64_t runSeed, int floor, int encounter, int ordinal) {
    // FNV-1a over four fixed-width public identity components.  Low two bits
    // select exactly one of four stable buckets; there is no gameplay RNG use.
    std::uint64_t h = 1469598103934665603ULL;
    const auto add = [&h](std::uint64_t value) {
        for (int i = 0; i < 8; ++i) {
            h ^= static_cast<std::uint8_t>(value & 0xffU);
            h *= 1099511628211ULL;
            value >>= 8;
        }
    };
    add(runSeed);
    add(static_cast<std::uint32_t>(floor));
    add(static_cast<std::uint32_t>(encounter));
    add(static_cast<std::uint32_t>(ordinal));
    return (h & 3U) == 0U;
}

bool reserveStickyQualitySample(std::uint64_t runSeed) {
    std::lock_guard<std::mutex> lock(g_stickyQualitySelectionMutex);
    int &selected = g_stickyQualitySelectionsByRunSeed[runSeed];
    if (selected >= 16) return false;
    ++selected;
    return true;
}

bool reserveRootDiagnosticSample(std::uint64_t runSeed) {
    std::lock_guard<std::mutex> lock(g_stickyQualitySelectionMutex);
    int &selected = g_rootDiagnosticSelectionsByRunSeed[runSeed];
    if (selected >= g_silverLiveOptions.rootDiagnosticMaxPerSeed) return false;
    ++selected;
    return true;
}

std::string csvField(const std::string &value) {
    if (value.find_first_of(",\"\n\r") == std::string::npos) return value;
    std::string out = "\"";
    for (char ch : value) {
        if (ch == '\"') out += "\"\"";
        else out += ch;
    }
    return out + "\"";
}

CardInstance liveLeafCard(const silver_bridge::CardWire &in) {
    CardInstance out;
    out.id = static_cast<CardId>(in.id);
    out.uniqueId = in.uniqueId; out.specialData = in.specialData;
    out.cost = static_cast<std::int8_t>(in.cost);
    out.costForTurn = static_cast<std::int8_t>(in.costForTurn);
    out.upgraded = in.upgraded; out.freeToPlayOnce = in.freeToPlayOnce; out.retain = in.retain;
    return out;
}

template <typename Pile>
void loadLiveLeafPile(Pile &out, const silver_bridge::PileWire &in) {
    out.clear();
    for (const auto &card : in.knownBottom) out.push_back(liveLeafCard(card));
    for (const auto &card : in.unknown) out.push_back(liveLeafCard(card));
    for (const auto &card : in.knownTop) out.push_back(liveLeafCard(card));
}

// Rebuild only the existing live BattleContext input expected by
// CombatValueNet::predict(). This is a wire-to-live adapter, not a second
// feature extractor or VNet implementation; the authoritative 751-feature
// path remains CombatValueNet::predict(BattleContext).
BattleContext liveLeafBattleContext(const silver_bridge::BattleStateWire &in) {
    BattleContext out;
    out.seed = in.isolatedSearchSeed;
    out.floorNum = in.floorNum; out.encounter = static_cast<MonsterEncounter>(in.encounter);
    out.loopCount = in.loopCount; out.energyWasted = in.energyWasted; out.cardsDrawn = in.cardsDrawn;
    out.ascension = in.ascension;
    out.outcome = static_cast<Outcome>(in.outcome); out.inputState = static_cast<InputState>(in.inputState);
    out.monsterTurnIdx = in.monsterTurnIdx; out.endTurnQueued = in.endTurnQueued;
    out.turnHasEnded = in.turnHasEnded; out.skipMonsterTurn = in.skipMonsterTurn;
    out.potionCount = in.potionCount; out.potionCapacity = in.potionCapacity; out.turn = in.turn;
    out.miscBits = std::bitset<32>(in.miscBits);
    for (std::size_t i = 0; i < out.potions.size(); ++i)
        out.potions[i] = static_cast<Potion>(in.potions[i]);

    const auto &wp = in.player;
    auto &p = out.player;
    p.cc = static_cast<CharacterClass>(wp.characterClass); p.gold = wp.gold;
    p.curHp = wp.curHp; p.maxHp = wp.maxHp; p.energy = wp.energy;
    p.energyPerTurn = wp.energyPerTurn; p.cardDrawPerTurn = wp.cardDrawPerTurn;
    p.stance = static_cast<Stance>(wp.stance); p.orbSlots = wp.orbSlots;
    p.lastTargetedMonster = wp.lastTargetedMonster; p.block = wp.block; p.artifact = wp.artifact;
    p.dexterity = wp.dexterity; p.focus = wp.focus; p.strength = wp.strength;
    p.justAppliedBits = wp.justAppliedBits; p.statusBits0 = wp.statusBits0; p.statusBits1 = wp.statusBits1;
    for (const auto &[status, amount] : wp.statusMap)
        p.statusMap.emplace(static_cast<PlayerStatus>(status), amount);
    p.relicBits0 = wp.relicBits0; p.relicBits1 = wp.relicBits1;
    p.happyFlowerCounter = wp.relicCounters[0]; p.incenseBurnerCounter = wp.relicCounters[1];
    p.inkBottleCounter = wp.relicCounters[2]; p.inserterCounter = wp.relicCounters[3];
    p.nunchakuCounter = wp.relicCounters[4]; p.penNibCounter = wp.relicCounters[5];
    p.sundialCounter = wp.relicCounters[6]; p.haveUsedNecronomiconThisTurn = wp.haveUsedNecronomiconThisTurn;
    p.combustHpLoss = wp.combustHpLoss; p.devaFormEnergyPerTurn = wp.devaFormEnergyPerTurn;
    p.echoFormCardsDoubled = wp.echoFormCardsDoubled; p.panacheCounter = wp.panacheCounter;
    p.cardsPlayedThisTurn = wp.cardsPlayedThisTurn; p.attacksPlayedThisTurn = wp.attacksPlayedThisTurn;
    p.skillsPlayedThisTurn = wp.skillsPlayedThisTurn; p.cardsDiscardedThisTurn = wp.cardsDiscardedThisTurn;
    p.orangePelletsCardTypesPlayed = std::bitset<3>(wp.orangePelletsCardTypesPlayed);
    p.lastAttackUnblockedDamage = wp.lastAttackUnblockedDamage; p.timesDamagedThisCombat = wp.timesDamagedThisCombat;
    p.bomb1 = wp.bombs[0]; p.bomb2 = wp.bombs[1]; p.bomb3 = wp.bombs[2];

    out.monsters.monsterCount = in.monsterCount; out.monsters.monstersAlive = in.monstersAlive;
    out.monsters.extraRollMoveOnTurn = std::bitset<5>(in.extraRollMoveOnTurn);
    out.monsters.skipTurn = std::bitset<5>(in.skipMonsterTurnBits);
    for (std::size_t i = 0; i < out.monsters.arr.size(); ++i) {
        const auto &wm = in.monsters[i];
        auto &m = out.monsters.arr[i];
        m.idx = wm.idx; m.id = static_cast<MonsterId>(wm.id); m.curHp = wm.curHp;
        m.maxHp = wm.maxHp; m.block = wm.block; m.isEscapingB = wm.isEscapingB;
        m.halfDead = wm.halfDead; m.escapeNext = wm.escapeNext;
        m.moveHistory[0] = static_cast<MMID>(wm.moveHistory[0]);
        m.moveHistory[1] = static_cast<MMID>(wm.moveHistory[1]); m.statusBits = wm.statusBits;
        m.artifact = static_cast<std::int8_t>(wm.smallPowers[0]);
        m.blockReturn = static_cast<std::int8_t>(wm.smallPowers[1]); m.choked = static_cast<std::int8_t>(wm.smallPowers[2]);
        m.corpseExplosion = static_cast<std::int8_t>(wm.smallPowers[3]); m.lockOn = static_cast<std::int8_t>(wm.smallPowers[4]);
        m.mark = wm.smallPowers[5]; m.metallicize = static_cast<std::int8_t>(wm.smallPowers[6]);
        m.platedArmor = static_cast<std::int8_t>(wm.smallPowers[7]); m.poison = static_cast<std::int8_t>(wm.smallPowers[8]);
        m.regen = static_cast<std::int8_t>(wm.smallPowers[9]); m.shackled = static_cast<std::int8_t>(wm.smallPowers[10]);
        m.strength = wm.strength; m.vulnerable = wm.vulnerable; m.weak = wm.weak;
        m.uniquePower0 = wm.uniquePower0; m.uniquePower1 = wm.uniquePower1; m.miscInfo = wm.miscInfo;
    }

    out.cards.nextUniqueCardId = in.nextUniqueCardId; out.cards.cardsInHand = static_cast<int>(in.hand.size());
    for (int i = 0; i < out.cards.cardsInHand; ++i) out.cards.hand[i] = liveLeafCard(in.hand[i]);
    for (std::size_t i = 0; i < out.cards.limbo.size() && i < in.limbo.size(); ++i)
        out.cards.limbo[i] = liveLeafCard(in.limbo[i]);
    for (std::size_t i = 0; i < out.cards.stasisCards.size(); ++i)
        out.cards.stasisCards[i] = liveLeafCard(in.stasisCards[i]);
    out.cards.handNormalityCount = in.handNormalityCount; out.cards.handPainCount = in.handPainCount;
    out.cards.strikeCount = in.strikeCount; out.cards.handBloodCardCount = in.handBloodCardCount;
    out.cards.drawPileBloodCardCount = in.drawPileBloodCardCount;
    out.cards.discardPileBloodCardCount = in.discardPileBloodCardCount;
    loadLiveLeafPile(out.cards.drawPile, in.drawPile);
    loadLiveLeafPile(out.cards.discardPile, in.discardPile);
    loadLiveLeafPile(out.cards.exhaustPile, in.exhaustPile);
    return out;
}

bool sampledLeaf(const silver_bridge::SilverLeafObservation &observation, int modulus) {
    std::uint64_t h = 1469598103934665603ULL;
    const auto mix = [&h](std::uint64_t value) {
        for (int i = 0; i < 8; ++i) { h ^= static_cast<std::uint8_t>(value); h *= 1099511628211ULL; value >>= 8; }
    };
    mix(observation.state.isolatedSearchSeed); mix(observation.rootStateHash);
    mix(observation.parentStateHash); mix(observation.leafStateHash);
    mix(static_cast<std::uint32_t>(observation.depth));
    return h % static_cast<std::uint64_t>(modulus) == 0;
}

void ensureSilverLeafVNetLoaded() {
    static std::mutex mutex;
    static std::string loadedPath;
    std::lock_guard<std::mutex> lock(mutex);
    if (loadedPath == g_silverLiveOptions.leafVNetModel && g_combatVNet.loaded()) return;
    if (!g_combatVNet.load(g_silverLiveOptions.leafVNetModel))
        throw std::runtime_error("cannot load Silver leaf VNet: " + g_silverLiveOptions.leafVNetModel);
    loadedPath = g_silverLiveOptions.leafVNetModel;
    std::cout << "[Silver leaf VNet ON: " << loadedPath << ", "
              << g_combatVNet.description() << ", affine a="
              << g_silverLiveOptions.leafVNetAffineA << " b="
              << g_silverLiveOptions.leafVNetAffineB << "]\n";
}

void writeLeafVNetObservation(std::uint64_t runSeed, int decision,
                              const silver_bridge::SilverLeafObservation &observation) {
    std::lock_guard<std::mutex> lock(g_leafVNetLogMutex);
    bool empty = false;
    if (!g_leafVNetLogHeaderWritten) {
        std::ifstream existing(g_silverLiveOptions.leafVNetLogFile, std::ios::binary);
        empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
        if (!empty) {
            std::string header; std::getline(existing, header);
            if (header != kLeafVNetHeader)
                throw std::runtime_error("STS_SILVER_VNET_LEAF_LOG has an incompatible existing header: "
                                         + g_silverLiveOptions.leafVNetLogFile);
        }
    }
    std::ofstream out(g_silverLiveOptions.leafVNetLogFile, std::ios::app);
    if (!out) throw std::runtime_error("cannot open STS_SILVER_VNET_LEAF_LOG: "
                                      + g_silverLiveOptions.leafVNetLogFile);
    if (!g_leafVNetLogHeaderWritten && empty) out << kLeafVNetHeader << '\n';
    const auto &s = observation.state;
    out << std::setprecision(17)
        << runSeed << ',' << s.act << ',' << s.floorNum << ',' << s.encounter << ',' << decision << ','
        << s.isolatedSearchSeed << ',' << observation.rootStateHash << ',' << observation.parentStateHash << ','
        << observation.leafStateHash << ',' << observation.depth << ',' << observation.actionCountBeforeRollout << ','
        << s.turn << ',' << s.inputState << ',' << s.player.curHp << ',' << s.player.maxHp << ','
        << observation.vnetRawPrediction << ',' << observation.terminalOutcome << ',' << observation.rolloutUtility << ','
        << observation.rolloutActionCount << ',' << observation.rolloutTurnDelta << ',' << observation.rolloutWallMicros << '\n';
    out.flush();
    if (!out) throw std::runtime_error("cannot write STS_SILVER_VNET_LEAF_LOG: "
                                      + g_silverLiveOptions.leafVNetLogFile);
    g_leafVNetLogHeaderWritten = true;
}

std::string rootActionSummaries(const std::vector<silver_bridge::SilverRootActionSummary> &summaries) {
    std::ostringstream out;
    out << std::setprecision(17);
    for (std::size_t i = 0; i < summaries.size(); ++i) {
        if (i != 0) out << ';';
        const auto &s = summaries[i];
        out << silver_bridge::semanticActionFingerprint(s.action) << '@' << s.edgeVisits << '@'
            << s.childSimulations << '@' << s.childEvaluationSum << '@';
        if (s.selectionQValid) out << s.selectionQ;
        else out << "NA";
    }
    return out.str();
}

const silver_bridge::SilverRootActionSummary *findRootAction(
        const std::vector<silver_bridge::SilverRootActionSummary> &summaries,
        const std::string &fingerprint) {
    for (const auto &summary : summaries) {
        if (silver_bridge::semanticActionFingerprint(summary.action) == fingerprint) return &summary;
    }
    return nullptr;
}

double componentMean(double sum, std::int64_t count) {
    return count > 0 ? sum / static_cast<double>(count) : 0.0;
}

std::string optionalDouble(double value, bool valid) {
    if (!valid) return "NA";
    std::ostringstream out;
    out << std::setprecision(17) << value;
    return out.str();
}

void writeRootDiagnostics(const silver_bridge::BattleStateWire &wire,
                          std::uint64_t runSeed, int ordinal,
                          const std::string &roomType,
                          const silver_bridge::SilverDecisionResult &low,
                          const silver_bridge::SilverDecisionResult &high,
                          const std::vector<silver_bridge::SilverForcedActionReference> &references) {
    if (references.empty()) return;
    std::lock_guard<std::mutex> lock(g_rootDiagnosticMutex);
    bool empty = false;
    if (!g_rootDiagnosticHeaderWritten) {
        std::ifstream existing(g_silverLiveOptions.rootDiagnosticFile, std::ios::binary);
        empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
        if (!empty) {
            std::string header;
            std::getline(existing, header);
            if (header != kRootDiagnosticHeader)
                throw std::runtime_error("STS_SILVER_ROOT_DIAG_FILE has an incompatible existing header: "
                                         + g_silverLiveOptions.rootDiagnosticFile);
        }
    }
    std::ofstream out(g_silverLiveOptions.rootDiagnosticFile, std::ios::app);
    if (!out) throw std::runtime_error("cannot open STS_SILVER_ROOT_DIAG_FILE: "
                                      + g_silverLiveOptions.rootDiagnosticFile);
    if (!g_rootDiagnosticHeaderWritten && empty) out << kRootDiagnosticHeader << '\n';
    out << std::setprecision(17);
    const auto lowChosen = silver_bridge::semanticActionFingerprint(low.action);
    const auto highChosen = silver_bridge::semanticActionFingerprint(high.action);
    for (const auto &reference : references) {
        if (!reference.accepted) continue;
        const auto actionFp = silver_bridge::semanticActionFingerprint(reference.action);
        const auto *lowSummary = findRootAction(low.rootActionSummaries, actionFp);
        const auto *highSummary = findRootAction(high.rootActionSummaries, actionFp);
        const auto &t = reference.telemetry;
        out << runSeed << ',' << wire.act << ',' << wire.floorNum << ',' << wire.encounter << ','
            << roomType << ',' << ordinal << ',' << wire.turn << ',' << wire.inputState << ','
            << wire.player.curHp << ',' << wire.player.maxHp << ',' << wire.potionCount << ','
            << static_cast<int>(reference.action.type) << ',' << (reference.stochastic ? 1 : 0) << ','
            << csvField(actionFp) << ','
            << csvField(lowChosen) << ','
            << (lowSummary == nullptr ? 0 : lowSummary->edgeVisits) << ','
            << optionalDouble(lowSummary == nullptr ? 0.0 : lowSummary->selectionQ,
                              lowSummary != nullptr && lowSummary->selectionQValid) << ','
            << csvField(highChosen) << ','
            << (highSummary == nullptr ? 0 : highSummary->edgeVisits) << ','
            << optionalDouble(highSummary == nullptr ? 0.0 : highSummary->selectionQ,
                              highSummary != nullptr && highSummary->selectionQValid) << ','
            << (low.diagnostic.exactReroot ? 1 : 0) << ','
            << silver_bridge::silverRerootFallbackReasonName(low.diagnostic.fallbackReason) << ','
            << low.diagnostic.inheritedVisits << ','
            << g_silverLiveOptions.rootDiagnosticReferenceBudget << ','
            << g_silverLiveOptions.rootDiagnosticReplicates << ',' << reference.meanValue << ','
            << reference.valueStddev << ','
            << reference.rolloutWinRate << ',' << reference.meanRolloutActions << ','
            << reference.meanRolloutTurns << ',' << t.rolloutCalls << ','
            << t.rolloutTerminalWins << ',' << t.rolloutTerminalLosses << ','
            << componentMean(t.rolloutUtilitySum, t.rolloutCalls) << ','
            << componentMean(t.rolloutWinBonusSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutHpSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutPotionSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutTurnPenaltySum, t.rolloutCalls) << ','
            << componentMean(t.rolloutDeathSaveSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutGoldSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutMaxHpSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutParasitePenaltySum, t.rolloutCalls) << ','
            << componentMean(t.rolloutMonsterDamageSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutAliveSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutEnergyWasteSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutDrawSum, t.rolloutCalls) << ','
            << componentMean(t.rolloutSurvivalSum, t.rolloutCalls) << ','
            << low.telemetry.rolloutCalls << ',' << low.telemetry.rolloutTerminalWins << ','
            << low.telemetry.rolloutTerminalLosses << ',' << low.telemetry.rolloutActionCount << ','
            << low.telemetry.rolloutTurnDelta << ',' << low.telemetry.rolloutUtilitySum << ','
            << low.telemetry.rolloutWinBonusSum << ',' << low.telemetry.rolloutHpSum << ','
            << low.telemetry.rolloutPotionSum << ',' << low.telemetry.rolloutTurnPenaltySum << ','
            << low.telemetry.rolloutDeathSaveSum << ',' << low.telemetry.rolloutGoldSum << ','
            << low.telemetry.rolloutMaxHpSum << ',' << low.telemetry.rolloutParasitePenaltySum << ','
            << low.telemetry.rolloutMonsterDamageSum << ',' << low.telemetry.rolloutAliveSum << ','
            << low.telemetry.rolloutEnergyWasteSum << ',' << low.telemetry.rolloutDrawSum << ','
            << low.telemetry.rolloutSurvivalSum << ','
            << high.telemetry.rolloutCalls << ',' << high.telemetry.rolloutTerminalWins << ','
            << high.telemetry.rolloutTerminalLosses << ',' << high.telemetry.rolloutActionCount << ','
            << high.telemetry.rolloutTurnDelta << ',' << high.telemetry.rolloutUtilitySum << ','
            << high.telemetry.rolloutWinBonusSum << ',' << high.telemetry.rolloutHpSum << ','
            << high.telemetry.rolloutPotionSum << ',' << high.telemetry.rolloutTurnPenaltySum << ','
            << high.telemetry.rolloutDeathSaveSum << ',' << high.telemetry.rolloutGoldSum << ','
            << high.telemetry.rolloutMaxHpSum << ',' << high.telemetry.rolloutParasitePenaltySum << ','
            << high.telemetry.rolloutMonsterDamageSum << ',' << high.telemetry.rolloutAliveSum << ','
            << high.telemetry.rolloutEnergyWasteSum << ',' << high.telemetry.rolloutDrawSum << ','
            << high.telemetry.rolloutSurvivalSum << '\n';
    }
    out.flush();
    if (!out) throw std::runtime_error("cannot write STS_SILVER_ROOT_DIAG_FILE: "
                                      + g_silverLiveOptions.rootDiagnosticFile);
    g_rootDiagnosticHeaderWritten = true;
}

struct StickyQualityRow {
    std::uint64_t runSeed = 0;
    int act = 0, floor = 0, encounter = 0, ordinal = 0, turn = 0, inputState = 0;
    std::string roomType;
    silver_bridge::SilverSearchDecisionDiagnostic activeDiagnostic;
    StickyQualityBudgets budgets;
    std::string activeAction, freshAction, ref25Action, ref50Action;
    std::int64_t freshNodes = 0, freshSims = 0, ref25Nodes = 0, ref25Sims = 0, ref50Nodes = 0, ref50Sims = 0;
    double freshMs = 0, ref25Ms = 0, ref50Ms = 0;
    std::string ref25Summaries, ref50Summaries;
    bool qDiagnosticAvailable = false;
    double ref50ChosenQ = 0, activeQ = 0, freshQ = 0;
    double ref50QGapActive = 0, ref50QGapFresh = 0, ref50QGapActiveMinusFresh = 0;
};

struct StickyQualityCounters {
    int eligibleOrdinary = 0;
    int selected = 0;
    int excludedTransactionSubdecisions = 0;
};

StickyQualityRow evaluateStickyQuality(const silver_bridge::BattleStateWire &wire,
                                       std::uint64_t runSeed, int ordinal, const std::string &roomType,
                                       const silver_bridge::SilverDecisionResult &active,
                                       const silver_bridge::SilverSearchConfig &activeConfig) {
    StickyQualityRow row;
    row.runSeed = runSeed; row.act = wire.act; row.floor = wire.floorNum;
    row.encounter = wire.encounter; row.ordinal = ordinal; row.turn = wire.turn;
    row.inputState = wire.inputState; row.roomType = roomType; row.activeDiagnostic = active.diagnostic;
    row.budgets = stickyQualityBudgets();
    row.budgets.fresh = activeConfig.simulationsPerDecision;
    row.activeAction = silver_bridge::semanticActionFingerprint(active.action);

    const auto runFresh = [&wire, &activeConfig](std::int64_t budget, bool summaries,
                                                   double &elapsedMs) {
        auto config = activeConfig;
        config.simulationsPerDecision = budget;
        config.collectDecisionDiagnostics = true;
        config.collectRootActionSummaries = summaries;
        const auto before = std::chrono::steady_clock::now();
        auto result = silver_bridge::runSilverDecision(wire, config);
        elapsedMs = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - before).count();
        if (!result.accepted) throw std::runtime_error("Silver sticky quality: fresh shadow search returned no semantic decision");
        if (result.inheritedVisits != 0) throw std::runtime_error("Silver sticky quality: fresh shadow search inherited visits");
        if (result.simulations != budget) throw std::runtime_error("Silver sticky quality: fresh shadow search missed requested budget");
        return result;
    };
    const auto fresh = runFresh(row.budgets.fresh, false, row.freshMs);
    const auto ref25 = runFresh(row.budgets.ref25, true, row.ref25Ms);
    const auto ref50 = runFresh(row.budgets.ref50, true, row.ref50Ms);
    row.freshAction = silver_bridge::semanticActionFingerprint(fresh.action);
    row.ref25Action = silver_bridge::semanticActionFingerprint(ref25.action);
    row.ref50Action = silver_bridge::semanticActionFingerprint(ref50.action);
    row.freshNodes = fresh.telemetry.nodesCreated; row.freshSims = fresh.simulations;
    row.ref25Nodes = ref25.telemetry.nodesCreated; row.ref25Sims = ref25.simulations;
    row.ref50Nodes = ref50.telemetry.nodesCreated; row.ref50Sims = ref50.simulations;
    row.ref25Summaries = rootActionSummaries(ref25.rootActionSummaries);
    row.ref50Summaries = rootActionSummaries(ref50.rootActionSummaries);

    // BattleSearcher picks its final root action by maximum edge visits.  The
    // value retained here is its existing UCB child-Q for the selected REF50
    // action and each compared action; no alternative Q convention is made.
    const auto *best = findRootAction(ref50.rootActionSummaries, row.ref50Action);
    const auto *activeAtRef = findRootAction(ref50.rootActionSummaries, row.activeAction);
    const auto *freshAtRef = findRootAction(ref50.rootActionSummaries, row.freshAction);
    if (best != nullptr && activeAtRef != nullptr && freshAtRef != nullptr
            && best->selectionQValid && activeAtRef->selectionQValid && freshAtRef->selectionQValid) {
        row.qDiagnosticAvailable = true;
        row.ref50ChosenQ = best->selectionQ; row.activeQ = activeAtRef->selectionQ;
        row.freshQ = freshAtRef->selectionQ;
        row.ref50QGapActive = row.ref50ChosenQ - row.activeQ;
        row.ref50QGapFresh = row.ref50ChosenQ - row.freshQ;
        row.ref50QGapActiveMinusFresh = row.ref50QGapActive - row.ref50QGapFresh;
    }
    return row;
}

void writeStickyQuality(const std::vector<StickyQualityRow> &rows, std::uint64_t runSeed, int floor, int encounter,
                        const StickyQualityCounters &counters) {
    std::lock_guard<std::mutex> lock(g_stickyQualityMutex);
    const auto requireHeader = [](const std::string &path, const char *expected, bool &written) {
        bool empty = false;
        if (!written) {
            std::ifstream existing(path, std::ios::binary);
            empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
            if (!empty) {
                std::string header; std::getline(existing, header);
                if (header != expected) throw std::runtime_error("STS_SILVER_STICKY_QUALITY_FILE has an incompatible existing header: " + path);
            }
        }
        return empty;
    };
    if (!rows.empty()) {
        const bool empty = requireHeader(g_silverLiveOptions.stickyQualityFile, kStickyQualityHeader,
                                         g_stickyQualityHeaderWritten);
        std::ofstream out(g_silverLiveOptions.stickyQualityFile, std::ios::app);
        if (!out) throw std::runtime_error("cannot open STS_SILVER_STICKY_QUALITY_FILE: " + g_silverLiveOptions.stickyQualityFile);
        if (!g_stickyQualityHeaderWritten && empty) out << kStickyQualityHeader << '\n';
        out << std::setprecision(17);
        for (const auto &row : rows) {
            const auto &d = row.activeDiagnostic;
            out << row.runSeed << ',' << row.act << ',' << row.floor << ',' << row.encounter << ','
                << row.roomType << ',' << row.ordinal << ',' << row.turn << ',' << row.inputState << ','
                << d.allocatedNodesBeforeRoot << ',' << d.activeNodesBeforeRoot << ',' << d.inheritedVisits << ','
                << d.configuredCap << ',' << d.simulationsAdded << ',' << d.nodesCreated << ','
                << row.budgets.fresh << ',' << row.budgets.ref25 << ',' << row.budgets.ref50 << ','
                << csvField(row.activeAction) << ',' << csvField(row.freshAction) << ','
                << csvField(row.ref25Action) << ',' << csvField(row.ref50Action) << ','
                << (row.ref25Action == row.ref50Action ? 1 : 0) << ','
                << (row.freshAction == row.ref50Action ? 1 : 0) << ','
                << (row.activeAction == row.ref50Action ? 1 : 0) << ','
                << (row.freshAction != row.activeAction ? 1 : 0) << ','
                << row.freshMs << ',' << row.ref25Ms << ',' << row.ref50Ms << ','
                << row.freshNodes << ',' << row.freshSims << ',' << row.ref25Nodes << ',' << row.ref25Sims << ','
                << row.ref50Nodes << ',' << row.ref50Sims << ',' << csvField(row.ref25Summaries) << ','
                << csvField(row.ref50Summaries) << ',' << (row.qDiagnosticAvailable ? 1 : 0) << ',';
            if (row.qDiagnosticAvailable) out << row.ref50ChosenQ << ',' << row.activeQ << ',' << row.freshQ << ','
                                         << row.ref50QGapActive << ',' << row.ref50QGapFresh << ','
                                         << row.ref50QGapActiveMinusFresh;
            else out << "NA,NA,NA,NA,NA,NA";
            out << '\n';
        }
        out.flush();
        if (!out) throw std::runtime_error("cannot write STS_SILVER_STICKY_QUALITY_FILE: " + g_silverLiveOptions.stickyQualityFile);
        g_stickyQualityHeaderWritten = true;
    }
    const std::string summaryPath = g_silverLiveOptions.stickyQualityFile + ".summary.csv";
    const bool summaryEmpty = requireHeader(summaryPath, kStickyQualitySummaryHeader,
                                            g_stickyQualitySummaryHeaderWritten);
    std::ofstream summary(summaryPath, std::ios::app);
    if (!summary) throw std::runtime_error("cannot open Silver sticky quality summary: " + summaryPath);
    if (!g_stickyQualitySummaryHeaderWritten && summaryEmpty) summary << kStickyQualitySummaryHeader << '\n';
    summary << runSeed << ',' << floor << ',' << encounter << ',' << counters.eligibleOrdinary << ',' << counters.selected << ','
            << counters.excludedTransactionSubdecisions << '\n';
    summary.flush();
    if (!summary) throw std::runtime_error("cannot write Silver sticky quality summary: " + summaryPath);
    g_stickyQualitySummaryHeaderWritten = true;
}

class KnowledgeObserverScope {
public:
    explicit KnowledgeObserverScope(CombatKnowledgeState &state)
        : previous_(g_combatKnowledgeObserver) {
        g_combatKnowledgeObserver = &state;
    }
    ~KnowledgeObserverScope() { g_combatKnowledgeObserver = previous_; }
    KnowledgeObserverScope(const KnowledgeObserverScope &) = delete;
    KnowledgeObserverScope &operator=(const KnowledgeObserverScope &) = delete;
private:
    CombatKnowledgeObserver *previous_;
};

std::uint64_t isolatedBattleSeed(const BattleContext &bc) {
    // One deterministic, public seed for Silver's one-RNG *battle* model.
    // It must stay constant through the battle: Silver equalForSearch includes
    // BattleContext::seed and SearchAgent reroots into the selected child.
    // This is never a live RNG state or draw-pile order.
    std::uint64_t x = bc.seed ^ (static_cast<std::uint64_t>(bc.floorNum) << 32);
    x ^= 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
    return x;
}

silver_bridge::SilverSearchConfig configFor(const ScumSearchAgent2 &agent, const BattleContext &bc,
                                            bool collectDecisionDiagnostics) {
    silver_bridge::SilverSearchConfig result;
    result.simulationsPerDecision = isBossEncounter(bc.encounter)
        ? static_cast<std::int64_t>(agent.bossSimulationMultiplier * agent.simulationCountBase)
        : agent.simulationCountBase;
    result.reuseCapMode = g_silverLiveOptions.reuseCapMode;
    result.collectDecisionDiagnostics = collectDecisionDiagnostics;
    return result;
}

[[noreturn]] void fail(const char *where, const std::string &detail) {
    throw std::runtime_error(std::string("Silver live backend ") + where + ": " + detail);
}

void addTelemetry(const silver_bridge::SilverSearchTelemetry &telemetry) {
    g_silverLiveDiagnostics.nodesCreated += telemetry.nodesCreated;
    g_silverLiveDiagnostics.deterministicTranspositions += telemetry.detTranspositions;
    g_silverLiveDiagnostics.chanceOutcomes += telemetry.chanceOutcomesSampled;
    g_silverLiveDiagnostics.chanceSiblingReuse += telemetry.chanceSiblingReuse;
    g_silverLiveDiagnostics.chanceTranspositions += telemetry.chanceTranspositions;
    g_silverLiveDiagnostics.depthSum += telemetry.depthSum;
    g_silverLiveDiagnostics.chanceDepthSum += telemetry.chanceDepthSum;
    g_silverLiveDiagnostics.rolloutSkippedVNet += telemetry.rolloutSkippedVNet;
    for (std::size_t i = 0; i < telemetry.wideningSampled.size(); ++i) {
        g_silverLiveDiagnostics.wideningSampled += telemetry.wideningSampled[i];
        g_silverLiveDiagnostics.wideningCapped += telemetry.wideningCapped[i];
    }
}

void addDecisionDiagnostic(const silver_bridge::SilverSearchDecisionDiagnostic &diagnostic) {
    if (diagnostic.exactCandidateFound) ++g_silverLiveDiagnostics.rerootCandidateFound;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::CANDIDATE_MISSING)
        ++g_silverLiveDiagnostics.rerootCandidateMissing;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::ALLOCATED_CAP)
        ++g_silverLiveDiagnostics.rerootAllocatedCapBlocked;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::ACTIVE_CAP)
        ++g_silverLiveDiagnostics.rerootActiveCapBlocked;
}

void runSilverCombat(ScumSearchAgent2 &agent, GameContext &gc, BattleContext &bc) {
    CombatKnowledgeState knowledge;
    // Clear per-combat diagnostics before the observer sees initialization.
    g_silverLiveDiagnostics = {};
    // Monster initialization rolls before BattleContext initializes Player
    // relics. Capture Runic Dome visibility from GameContext up front rather
    // than asking Monster::rollMove to inspect an uninitialized Player.
    knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
    knowledge.initializeFromLiveBattle(bc);
    knowledge.beginCombatInitialization();
    KnowledgeObserverScope observer(knowledge);
    bc.init(gc);
    // Runic Dome roll-input events emitted by init are preserved by this sync.
    knowledge.synchronizeAfterCombatInitialization(bc);
    // One opaque isolated Silver session per live battle. It owns the private
    // BattleSearcher and reroots across all subsequent real decisions.
    auto silverSession = silver_bridge::makeSilverSearchSession();
    const std::uint64_t silverBattleSeed = isolatedBattleSeed(bc);
    const bool collectScalingDiagnostics = !g_silverLiveOptions.scalingDiagnosticFile.empty();
    const bool collectStickyQuality = !g_silverLiveOptions.stickyQualityFile.empty();
    const bool collectRootDiagnostics = !g_silverLiveOptions.rootDiagnosticFile.empty();
    const bool collectLeafVNet = !g_silverLiveOptions.leafVNetLogFile.empty();
    const bool directLeafVNet = g_silverLiveOptions.leafVNetDirect;
    const bool emitTelemetry = std::getenv("STS_SILVER_TELEMETRY")
        && std::atoi(std::getenv("STS_SILVER_TELEMETRY")) != 0;
    // Aggregate reroot-cause counters are advertised by STS_SILVER_TELEMETRY,
    // so populate their value-only records even when the authoritative CSV is
    // disabled. Both options are opt-in; default gameplay retains the cheap
    // no-diagnostic path.
    const bool collectDecisionDiagnostics = collectScalingDiagnostics || collectStickyQuality
        || collectRootDiagnostics || emitTelemetry;
    std::vector<ScalingDiagnosticRow> scalingDiagnostics;
    std::vector<StickyQualityRow> stickyQualityRows;
    StickyQualityCounters stickyQualityCounters;

    int decision = 0;
    int sampledLeafCount = 0;
    silver_bridge::SilverLeafObserver leafObserver;
    if (collectLeafVNet || directLeafVNet) {
        leafObserver = [&, runSeed = gc.seed](silver_bridge::SilverLeafObservation &observation) {
            if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
                const bool logThisLeaf = collectLeafVNet
                    && sampledLeafCount < g_silverLiveOptions.leafVNetMaxPerCombat
                    && sampledLeaf(observation, g_silverLiveOptions.leafVNetSample);
                if (!logThisLeaf && !directLeafVNet) return;
                ensureSilverLeafVNetLoaded();
                const BattleContext projected = liveLeafBattleContext(observation.state);
                const auto previousParent = g_vnetTraceParent;
                const auto previousDepth = g_vnetTraceDepth;
                g_vnetTraceParent = observation.parentStateHash;
                g_vnetTraceDepth = observation.depth;
                observation.vnetRawPrediction = g_combatVNet.predict(projected);
                g_vnetTraceParent = previousParent;
                g_vnetTraceDepth = previousDepth;
                if (logThisLeaf) {
                    observation.collectResult = true;
                    ++sampledLeafCount;
                }
                if (directLeafVNet) {
                    observation.directValue = g_silverLiveOptions.leafVNetAffineA
                        * observation.vnetRawPrediction + g_silverLiveOptions.leafVNetAffineB;
                    observation.skipRollout = true;
                }
            } else if (observation.collectResult) {
                writeLeafVNetObservation(runSeed, decision, observation);
            }
        };
    }
    while (bc.outcome == Outcome::UNDECIDED) {
        if (++decision > 1000) fail("stall", "exceeded 1000 decisions");
        if (g_onCombatDecision) g_onCombatDecision(bc);
        knowledge.reconcilePublicDrawPileCardinality(bc);
        if (knowledge.consistencyFailureCount != 0) {
            ++g_silverLiveDiagnostics.knowledgeConsistencyFailures;
            std::string detail = "observer detected stale or inconsistent positional knowledge at event="
                + std::to_string(static_cast<int>(knowledge.lastEvent))
                + " observed-size-before=" + std::to_string(knowledge.lastObservedDrawPileSize)
                + " initial-size=" + std::to_string(knowledge.initialSynchronizedDrawPileSize)
                + " live-size-now=" + std::to_string(bc.cards.drawPile.size())
                + " events(draw/remove/reshuffle/random/top/bottom)="
                + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::DRAW_OCCURRED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::DRAW_PILE_CARD_REMOVED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::RESHUFFLE_OCCURRED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::KNOWN_TOP_PLACED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED)]);
            if (knowledge.hasDrawMismatch) {
                detail += " expected=" + std::to_string(static_cast<int>(knowledge.lastExpectedKnownDraw.id))
                    + ":" + std::to_string(knowledge.lastExpectedKnownDraw.uniqueId)
                    + " observed=" + std::to_string(static_cast<int>(knowledge.lastObservedDraw.id))
                    + ":" + std::to_string(knowledge.lastObservedDraw.uniqueId);
            }
            fail("knowledge", detail);
        }

        const auto wire = makeSilverBattleStateWire(
            bc, knowledge, makeSilverRunContext(gc), silverBattleSeed);
        if (!wire.valid) {
            ++g_silverLiveDiagnostics.conversionFailures;
            fail("conversion", "live observation cannot be represented without hidden information");
        }

        auto config = configFor(agent, bc, collectDecisionDiagnostics);
        config.collectRootActionSummaries = collectRootDiagnostics;
        config.collectRolloutDiagnostics = collectRootDiagnostics;
        config.leafObserver = leafObserver;
        silver_bridge::SemanticAction semantic;
        if (bc.inputState == InputState::CARD_SELECT
                && (bc.cardSelectInfo.cardSelectTask == CardSelectTask::EXHAUST_MANY
                    || bc.cardSelectInfo.cardSelectTask == CardSelectTask::GAMBLE)) {
            const auto transaction = silver_bridge::runSequentialSelectionTransaction(*silverSession, wire, config);
            if (!transaction.accepted || !transaction.finalConfirmation) {
                ++g_silverLiveDiagnostics.transactionFailures;
                fail("selection transaction", transaction.failure.empty()
                    ? "no final Silver confirmation" : transaction.failure);
            }
            semantic = transaction.finalAction;
            g_silverLiveDiagnostics.simulations += transaction.totalSimulations;
            g_silverLiveDiagnostics.transactionSubdecisions += transaction.searchDecisions;
            g_silverLiveDiagnostics.rerootExact += transaction.rerootExact;
            g_silverLiveDiagnostics.rerootFallback += transaction.rerootFallback;
            addTelemetry(transaction.telemetry);
            if (collectDecisionDiagnostics) {
                if (transaction.searchDiagnostics.size()
                        != static_cast<std::size_t>(transaction.searchDecisions)) {
                    fail("scaling diagnostics", "transaction omitted a private search diagnostic");
                }
                for (std::size_t i = 0; i < transaction.searchDiagnostics.size(); ++i) {
                    addDecisionDiagnostic(transaction.searchDiagnostics[i]);
                    if (collectStickyQuality && stickyEligible(transaction.searchDiagnostics[i])) {
                        ++stickyQualityCounters.excludedTransactionSubdecisions;
                    }
                    if (collectScalingDiagnostics) {
                        scalingDiagnostics.push_back({gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision,
                                                      static_cast<int>(i), wire.turn, wire.inputState,
                                                      config.simulationsPerDecision, transaction.searchDiagnostics[i]});
                    }
                }
            }
        } else {
            const auto result = silver_bridge::runSilverDecision(*silverSession, wire, config);
            if (!result.accepted) {
                ++g_silverLiveDiagnostics.conversionFailures;
                fail("search", "Silver returned no semantic decision");
            }
            semantic = result.action;
            g_silverLiveDiagnostics.simulations += result.simulations;
            g_silverLiveDiagnostics.rerootExact += result.rerootExact;
            g_silverLiveDiagnostics.rerootFallback += result.rerootFallback;
            addTelemetry(result.telemetry);
            if (collectDecisionDiagnostics) {
                addDecisionDiagnostic(result.diagnostic);
                if (collectScalingDiagnostics) {
                    scalingDiagnostics.push_back({gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision,
                                                  -1, wire.turn, wire.inputState, config.simulationsPerDecision,
                                                  result.diagnostic});
                }
            }
            if (collectStickyQuality && stickyEligible(result.diagnostic)) {
                ++stickyQualityCounters.eligibleOrdinary;
                if (sampledStickyDecision(gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision)
                        && reserveStickyQualitySample(gc.seed)) {
                    const char *roomType = gc.curRoom == Room::MONSTER ? "hallway"
                        : gc.curRoom == Room::ELITE ? "elite"
                        : gc.curRoom == Room::BOSS ? "boss" : "other";
                    stickyQualityRows.push_back(evaluateStickyQuality(
                        wire, gc.seed, decision, roomType, result, config));
                    ++stickyQualityCounters.selected;
                }
            }
            if (collectRootDiagnostics && reserveRootDiagnosticSample(gc.seed)) {
                auto low = result;
                if (low.simulations != 1000) {
                    auto lowConfig = config;
                    lowConfig.simulationsPerDecision = 1000;
                    lowConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                    lowConfig.collectDecisionDiagnostics = false;
                    low = silver_bridge::runSilverDecision(wire, lowConfig);
                }
                auto highConfig = config;
                highConfig.simulationsPerDecision = 3700;
                highConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                highConfig.collectDecisionDiagnostics = false;
                const auto high = silver_bridge::runSilverDecision(wire, highConfig);
                if (!low.accepted || !high.accepted) {
                    fail("root diagnostic", "fresh 1k/3.7k comparison returned no semantic decision");
                }
                const auto references = silver_bridge::runSilverForcedActionReferences(
                    wire, config, g_silverLiveOptions.rootDiagnosticReferenceBudget,
                    g_silverLiveOptions.rootDiagnosticReplicates);
                const std::string roomType = gc.curRoom == Room::MONSTER ? "hallway"
                    : gc.curRoom == Room::ELITE ? "elite"
                    : gc.curRoom == Room::BOSS ? "boss" : "other";
                writeRootDiagnostics(wire, gc.seed, decision, roomType, low, high, references);
            }
        }

        const auto resolved = resolveSilverSemanticAction(bc, semantic);
        if (!resolved.ok) {
            ++g_silverLiveDiagnostics.semanticResolutionFailures;
            fail("semantic action resolution", resolved.error);
        }
        if (g_stickyQualityActionTraceForTest) {
            g_silverLiveDiagnostics.actionFingerprints.push_back(
                silver_bridge::semanticActionFingerprint(semantic));
        }
        ++g_silverLiveDiagnostics.decisions;
        agent.takeAction(bc, resolved.action);
    }
    agent.simulationCountTotal += static_cast<std::int64_t>(g_silverLiveDiagnostics.simulations);
    if (collectScalingDiagnostics) writeScalingDiagnostics(scalingDiagnostics);
    if (collectStickyQuality) writeStickyQuality(stickyQualityRows, gc.seed, bc.floorNum,
                                                 static_cast<int>(bc.encounter), stickyQualityCounters);
    if (emitTelemetry) {
        const auto &d = g_silverLiveDiagnostics;
        std::cout << "[silver-combat] decisions=" << d.decisions
                  << " simulations=" << d.simulations
                  << " transaction_subdecisions=" << d.transactionSubdecisions
                  << " reroot_exact=" << d.rerootExact
                  << " reroot_fallback=" << d.rerootFallback
                  << " reroot_candidate_found=" << d.rerootCandidateFound
                  << " reroot_candidate_missing=" << d.rerootCandidateMissing
                  << " reroot_allocated_cap=" << d.rerootAllocatedCapBlocked
                  << " reroot_active_cap=" << d.rerootActiveCapBlocked
                  << " nodes=" << d.nodesCreated
                  << " chance_outcomes=" << d.chanceOutcomes
                  << " chance_sibling_reuse=" << d.chanceSiblingReuse
                  << " det_transpositions=" << d.deterministicTranspositions
                  << " chance_transpositions=" << d.chanceTranspositions
                  << " widening_sampled=" << d.wideningSampled
                  << " widening_capped=" << d.wideningCapped
                  << " depth_sum=" << d.depthSum
                  << " chance_depth_sum=" << d.chanceDepthSum
                  << " rollout_skipped_vnet=" << d.rolloutSkippedVNet
                  << " conversion_failures=" << d.conversionFailures
                  << " semantic_resolution_failures=" << d.semanticResolutionFailures
                  << " transaction_failures=" << d.transactionFailures
                  << " knowledge_failures=" << d.knowledgeConsistencyFailures
                  << '\n';
    }
}

} // namespace

void installSilverLiveBackend() {
    parseSilverLiveOptions(); // validates before the first live combat begins
    g_externalCombatBackend = runSilverCombat;
}
void uninstallSilverLiveBackend() { g_externalCombatBackend = nullptr; g_silverLiveOptions.installed = false; }
bool silverLiveBackendInstalled() { return g_silverLiveOptions.installed; }
std::string silverLiveReuseCapMode() {
    return silver_bridge::silverReuseCapModeName(g_silverLiveOptions.reuseCapMode);
}
std::int64_t silverLiveReuseCap() { return silver_bridge::kSilverProductionReuseCap; }
std::string silverLiveScalingDiagnosticFile() { return g_silverLiveOptions.scalingDiagnosticFile; }
std::string silverLiveStickyQualityFile() { return g_silverLiveOptions.stickyQualityFile; }
bool silverStickyQualitySampled(std::uint64_t runSeed, int floor, int encounter,
                                int combatDecisionOrdinal) {
    return sampledStickyDecision(runSeed, floor, encounter, combatDecisionOrdinal);
}
void setSilverStickyQualityTestBudgetsForTest(std::int64_t fresh, std::int64_t ref25,
                                              std::int64_t ref50) {
    g_stickyQualityTestBudgets = {fresh, ref25, ref50};
}
void setSilverLiveActionTraceForTest(bool enabled) { g_stickyQualityActionTraceForTest = enabled; }

} // namespace sts::search
