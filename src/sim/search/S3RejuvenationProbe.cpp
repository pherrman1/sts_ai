//
// S3RejuvenationProbe implementation. Pure telemetry: replay uses copies of
// the anchor state and a dedicated probe RNG; nothing here touches the live
// battle, the searcher, its belief, or any battle RNG stream.
//
#include "sim/search/S3RejuvenationProbe.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <map>
#include <set>
#include <sstream>
#include <iostream>

namespace sts::search {

// Flags (env STS_S3_REJUV_*; off by default).
bool g_s3RejuvShadow = false;
int g_s3RejuvTrigger = 16;
int g_s3RejuvProposals = 256;
std::string g_s3RejuvShadowFile;
bool g_s3AiSensitivityShadow = false;
std::string g_s3AiSensitivityFile;
int g_s3AiSensitivityRootsPerSeed = 4;
int g_s3AiSensitivityAlternatives = 4;
int g_s3AiSensitivitySims = 256;

namespace {

std::string enc(double v);
std::uint64_t drawOrderOnlyHash(const FullHiddenStateKey &k);
std::uint64_t rngOnlyHash(const FullHiddenStateKey &k);
void writeSensitivityRow(const std::vector<std::string> &cols);

// ── CSV telemetry writer (append + mutex; header written once per file). ──
std::mutex &rejuvCsvMutex() {
    static std::mutex m;
    return m;
}

void writeRejuvCsvRow(const std::vector<std::string> &cols) {
    if (g_s3RejuvShadowFile.empty()) return;
    std::lock_guard<std::mutex> lock(rejuvCsvMutex());
    std::ifstream probe(g_s3RejuvShadowFile, std::ios::binary);
    const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    probe.close();
    std::ofstream out(g_s3RejuvShadowFile, std::ios::app);
    if (!out) return;
    if (empty) {
            out << "seed,encounter,floor,decision_idx,turn,compatible,attempted,"
               "collapse,fresh_rebuild,posterior_support,history_length,proposal_family,"
               "oracle_status,oracle_raw_status,proposals,accepted,acceptance_rate,"
               "unique,duplicate,novel,final_state_compatible,final_only_not_full,"
               "remap_failure,action_illegal,sim_health,intermediate_mismatch,"
               "final_mismatch,final_diag_aborted,transitions,unique_draw_orders,"
               "unique_rng,m4,m8,m16,m32,first_mismatch_count,first_mismatch_mean,"
               "first_mismatch_min,first_mismatch_max,first_mismatch_action_types,"
               "shuffle_counter,card_random_counter,ai_counter,misc_counter,"
               "monster_hp_counter,potion_counter,shuffle_consumed,card_random_consumed,"
               "ai_consumed,misc_consumed,monster_hp_consumed,potion_consumed,"
               "cpu_ms,cpu_per_proposal_ms\n";
    }
    for (size_t i = 0; i < cols.size(); ++i) {
        if (i) out << ',';
        out << cols[i];
    }
    out << '\n';
}

struct RootActionMetrics {
    std::int64_t visits = 0;
    double evaluationSum = 0.0;
    double meanQ = 0.0;
    std::int64_t availabilityCount = 0;
};

using RootMetrics = std::map<std::uint32_t, RootActionMetrics>;

RootMetrics rootMetrics(const BattleScumSearcher3 &s) {
    RootMetrics out;
    for (const auto &e : s.root.edges) {
        const auto visits = e.child.simulationCount;
        const double evaluationSum = e.child.evaluationSum;
        out[e.action.bits] = {
            visits, evaluationSum, visits > 0 ? evaluationSum / visits : 0.0,
            e.availabilityCount};
    }
    return out;
}

std::uint32_t selectedRootAction(const BattleScumSearcher3 &s,
                                 const BattleContext &bc) {
    std::uint32_t selected = 0;
    std::int64_t best = -1;
    for (const auto &e : s.root.edges) {
        if (e.child.simulationCount > best
            && (!g_s3Live || e.action.isValidAction(bc))) {
            best = e.child.simulationCount;
            selected = e.action.bits;
        }
    }
    return selected;
}

std::uint32_t selectedRootAction(const RootMetrics &m,
                                 const BattleContext &bc) {
    std::uint32_t selected = 0;
    std::int64_t best = -1;
    for (const auto &[bits, stats] : m) {
        Action action(bits);
        if (stats.visits > best && action.isValidAction(bc)) {
            best = stats.visits;
            selected = bits;
        }
    }
    return selected;
}

std::vector<std::uint32_t> topTwoRootActions(const RootMetrics &m,
                                             const BattleContext &bc) {
    std::vector<std::uint32_t> actions;
    for (const auto &[bits, stats] : m) {
        if (!Action(bits).isValidAction(bc)) continue;
        const auto it = std::find_if(actions.begin(), actions.end(), [&](std::uint32_t x) {
            return m.at(x).visits < stats.visits;
        });
        actions.insert(it, bits);
    }
    if (actions.size() > 2) actions.resize(2);
    return actions;
}

double visitShareTv(const RootMetrics &a, const RootMetrics &b) {
    std::int64_t totalA = 0, totalB = 0;
    for (const auto &[_, s] : a) totalA += s.visits;
    for (const auto &[_, s] : b) totalB += s.visits;
    if (totalA <= 0 || totalB <= 0) return 0.0;
    std::set<std::uint32_t> keys;
    for (const auto &[k, _] : a) keys.insert(k);
    for (const auto &[k, _] : b) keys.insert(k);
    double tv = 0.0;
    for (const auto k : keys) {
        const double pa = static_cast<double>(a.count(k) ? a.at(k).visits : 0) / totalA;
        const double pb = static_cast<double>(b.count(k) ? b.at(k).visits : 0) / totalB;
        tv += std::abs(pa - pb);
    }
    return 0.5 * tv;
}

bool sameCurrentBoundary(const BattleContext &oracleBc,
                         const HiddenBattleState &candidate,
                         const BattleContext &candidateBc,
                         bool requireDifferentAi) {
    if (CombatObservation::fromBattleContext(oracleBc)
        != CombatObservation::fromBattleContext(candidateBc)) return false;
    if (oracleBc.outcome != candidateBc.outcome) return false;
    const auto oracle = fullHiddenStateKey(oracleHiddenState(oracleBc));
    const auto actual = fullHiddenStateKey(candidate);
    if (oracle.drawPileOrder != actual.drawPileOrder) return false;
    for (int i : {0, 1, 3, 4, 5}) {
        if (oracle.seed0[i] != actual.seed0[i] || oracle.seed1[i] != actual.seed1[i]
            || oracle.counter[i] != actual.counter[i]) return false;
    }
    const bool differentAi = oracle.seed0[2] != actual.seed0[2]
        || oracle.seed1[2] != actual.seed1[2]
        || oracle.counter[2] != actual.counter[2];
    return !requireDifferentAi || differentAi;
}

std::uint64_t hiddenIdentityHash(const HiddenBattleState &state) {
    const auto key = fullHiddenStateKey(state);
    return drawOrderOnlyHash(key) ^ (rngOnlyHash(key) + 0x9e3779b97f4a7c15ULL
        + (drawOrderOnlyHash(key) << 6) + (drawOrderOnlyHash(key) >> 2));
}

bool sameOracleSearch(const RootMetrics &a, const RootMetrics &b,
                      std::uint32_t selectedA, std::uint32_t selectedB) {
    if (selectedA != selectedB || a.size() != b.size()) return false;
    for (const auto &[bits, x] : a) {
        const auto it = b.find(bits);
        if (it == b.end() || x.visits != it->second.visits
            || x.evaluationSum != it->second.evaluationSum
            || x.meanQ != it->second.meanQ
            || x.availabilityCount != it->second.availabilityCount) return false;
    }
    return true;
}

void runFixedHiddenSearch(const HiddenBattleState &hidden, int simulations,
                          BattleScumSearcher3 &out) {
    Belief fixed;
    fixed.particles.assign(64, hidden);
    for (auto &p : fixed.particles) p.weight = 1.0 / fixed.particles.size();
    out.belief = std::move(fixed);
    out.search(simulations);
}

void runSensitivityCondition(const BattleContext &bc, const HiddenBattleState &hidden,
                             const char *condition, int alternative,
                             std::uint64_t rootHash, int sourceDecisionIdx,
                             int searchDecisionIdx, const RootMetrics &oracleMetrics,
                             std::uint32_t oracleSelected, int novelCount,
                             bool supportEmpty, const RootMetrics &metrics,
                             bool &oracleControlOk) {
    BattleContext fixedBc = bc;
    std::mt19937_64 fallback(0x4d595df4d0f33173ULL);
    applyHiddenState(fixedBc, hidden, fallback);
    const bool sameBoundary = sameCurrentBoundary(
        bc, hidden, fixedBc, std::string(condition).find("ORACLE") != 0);
    if (!sameBoundary) {
        writeSensitivityRow({std::to_string(bc.seed), std::to_string(static_cast<int>(bc.encounter)),
            std::to_string(bc.floorNum), std::to_string(sourceDecisionIdx),
            std::to_string(searchDecisionIdx), std::to_string(bc.turn),
            std::to_string(rootHash), condition, std::to_string(alternative),
            std::to_string(hiddenIdentityHash(hidden)), "", "", "", "", "",
            "BLOCK_ISOLATION_FAILURE", "", "", "", "", "", "", "", "", "",
            std::to_string(novelCount), std::to_string(supportEmpty)});
        oracleControlOk = false;
        return;
    }

    if (searchDecisionIdx != sourceDecisionIdx + 1) {
        oracleControlOk = false;
        return;
    }
    const auto selected = selectedRootAction(metrics, bc);
    std::int64_t totalVisits = 0;
    for (const auto &[_, stats] : metrics) totalVisits += stats.visits;
    const double total = std::max<std::int64_t>(1, totalVisits);
    const double tv = visitShareTv(oracleMetrics, metrics);
    const auto top = topTwoRootActions(metrics, bc);
    const auto oracleTop = topTwoRootActions(oracleMetrics, bc);
    const bool topChanged = top != oracleTop;
    double maxDq = 0.0, selectedDq = 0.0;
    for (const auto &[bits, stats] : metrics) {
        const auto it = oracleMetrics.find(bits);
        if (it == oracleMetrics.end()) continue;
        maxDq = std::max(maxDq, std::abs(stats.meanQ - it->second.meanQ));
        if (bits == oracleSelected) selectedDq = stats.meanQ - it->second.meanQ;
    }
    bool qOrderFlip = false;
    if (oracleMetrics.count(oracleSelected)) {
        const double oracleSelectedQ = oracleMetrics.at(oracleSelected).meanQ;
        const double treatmentSelectedQ = metrics.count(oracleSelected)
            ? metrics.at(oracleSelected).meanQ : oracleSelectedQ;
        for (const auto &[bits, oracleStats] : oracleMetrics) {
            if (bits == oracleSelected || !metrics.count(bits)) continue;
            const double treatmentQ = metrics.at(bits).meanQ;
            const bool oracleAbove = oracleSelectedQ >= oracleStats.meanQ;
            const bool treatmentAbove = treatmentSelectedQ >= treatmentQ;
            if (oracleAbove != treatmentAbove) { qOrderFlip = true; break; }
        }
    }
    const bool selectedChanged = selected != oracleSelected;
    const std::string control = std::string(condition) == "ORACLE_A" ? "BASELINE"
        : std::string(condition) == "ORACLE_B" ? (sameOracleSearch(oracleMetrics, metrics,
            oracleSelected, selected) ? "EXACT" : "MISMATCH") : "N/A";
    for (const auto &[bits, stats] : metrics) {
        const double share = stats.visits / total;
        writeSensitivityRow({std::to_string(bc.seed), std::to_string(static_cast<int>(bc.encounter)),
            std::to_string(bc.floorNum), std::to_string(sourceDecisionIdx),
            std::to_string(searchDecisionIdx), std::to_string(bc.turn),
            std::to_string(rootHash), condition, std::to_string(alternative),
            std::to_string(hiddenIdentityHash(hidden)), std::to_string(bits),
            std::to_string(stats.visits), enc(share), enc(stats.meanQ), std::to_string(selected),
            "OK", control, selectedChanged ? "1" : "0", topChanged ? "1" : "0",
            enc(tv), enc(maxDq), enc(selectedDq), qOrderFlip ? "1" : "0",
            std::to_string(novelCount), std::to_string(supportEmpty)});
    }
    if (std::string(condition) == "ORACLE_B" && control != "EXACT") {
        oracleControlOk = false;
    }
}

void writeSensitivityRow(const std::vector<std::string> &cols) {
    static std::mutex mutex;
    std::lock_guard<std::mutex> lock(mutex);
    std::ifstream probe(g_s3AiSensitivityFile, std::ios::binary);
    const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    std::ofstream out(g_s3AiSensitivityFile, std::ios::app);
    if (!out) return;
    if (empty) out << "seed,encounter,floor,source_filter_decision_idx,search_decision_idx,turn,root_obs_hash,condition,alternative,"
        "hidden_hash,action_bits,visits,visit_share,q,selected_action,block_isolation,"
        "oracle_control,selected_changed,top2_changed,visit_tv,max_common_abs_dq,"
        "oracle_selected_dq,q_order_flip,novel_candidates,positive_support_empty\n";
    for (size_t i = 0; i < cols.size(); ++i) { if (i) out << ','; out << cols[i]; }
    out << '\n';
}

std::string enc(double v) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3) << v;
    return oss.str();
}

// Telemetry-only hashes (uniqueness/novelty/milestones are equality-backed via
// FullHiddenStateKey; these are separate draw-order-only and RNG-only counts).
std::uint64_t drawOrderOnlyHash(const FullHiddenStateKey &k) {
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (const auto &c : k.drawPileOrder) { h ^= c.hash(); h *= 1099511628211ULL; }
    return h;
}

std::uint64_t rngOnlyHash(const FullHiddenStateKey &k) {
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (int i = 0; i < 6; ++i) {
        h ^= k.seed0[i]; h *= 1099511628211ULL;
        h ^= k.seed1[i]; h *= 1099511628211ULL;
        h ^= static_cast<std::uint64_t>(static_cast<std::int64_t>(k.counter[i]));
        h *= 1099511628211ULL;
    }
    return h;
}

BattleScumSearcher3::CardActionKey semanticCardKey(const CardInstance &c) {
    BattleScumSearcher3::CardActionKey k;
    k.id = c.getId();
    k.upgradeCount = c.getUpgradeCount();
    k.costForTurn = c.costForTurn;
    k.freeToPlayOnce = c.freeToPlayOnce;
    k.specialData = c.specialData;
    k.target = -1;
    return k;
}

// Full canonical semantic identity match (id + upgrade + costForTurn +
// freeToPlayOnce + specialData). Discovery/Codex offer identity is CardId
// only and is matched separately.
bool matchesSemanticKey(const CardInstance &c, const BattleScumSearcher3::CardActionKey &k) {
    return c.getId() == k.id
        && c.getUpgradeCount() == k.upgradeCount
        && c.costForTurn == k.costForTurn
        && c.freeToPlayOnce == k.freeToPlayOnce
        && c.specialData == k.specialData;
}

} // namespace

// ── History recording ──────────────────────────────────────────────────────
S3RejuvenationHistory::S3RejuvenationHistory(const BattleContext &battleStart)
    : anchor(battleStart), anchorObs(CombatObservation::fromBattleContext(battleStart)) {}

void S3RejuvenationHistory::record(const BattleContext &preState,
                                   const Action &action,
                                   const BattleContext &postState) {
    S3RejuvenationEntry e;
    e.action = action;
    e.selectTask = preState.cardSelectInfo.cardSelectTask;
    e.rawSelectIndex = action.getActionType() == ActionType::SINGLE_CARD_SELECT
        ? action.getSelectIdx() : -1;
    switch (action.getActionType()) {
    case ActionType::CARD:
        // Hand card: full canonical identity + target via the shared CARD key
        // helper (independent of hand position).
        e.cardKey = BattleScumSearcher3::cardActionKey(preState, action);
        e.hasCardKey = e.cardKey.id != CardId::INVALID;
        if (action.getSourceIdx() >= 0 && action.getSourceIdx() < preState.cards.cardsInHand)
            e.selectedUniqueId = preState.cards.hand[action.getSourceIdx()].uniqueId;
        break;
    case ActionType::SINGLE_CARD_SELECT: {
        // Probe-specific semantic recording: the selected card's canonical
        // identity comes from the task's actual source pile, never the raw
        // physical index. cardSelectInfo.cards only represents Discovery/Codex
        // ordered offers (CardId), so real CardInstance piles are recorded
        // with full canonical identity.
        const int si = action.getSelectIdx();
        const CardSelectTask task = preState.cardSelectInfo.cardSelectTask;
        switch (task) {
        case CardSelectTask::CODEX:
        case CardSelectTask::DISCOVERY:
            if (si >= 0 && si < static_cast<int>(preState.cardSelectInfo.cards.size())
                && preState.cardSelectInfo.cards[si] != CardId::INVALID) {
                e.cardKey.id = preState.cardSelectInfo.cards[si];
                e.hasCardKey = true;
            }
            break;
        case CardSelectTask::HOLOGRAM:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
        case CardSelectTask::HEADBUTT:
        case CardSelectTask::MEDITATE:
            if (si >= 0 && si < static_cast<int>(preState.cards.discardPile.size()))
                e.cardKey = semanticCardKey(preState.cards.discardPile[si]);
            break;
        case CardSelectTask::EXHUME:
            if (si >= 0 && si < static_cast<int>(preState.cards.exhaustPile.size()))
                e.cardKey = semanticCardKey(preState.cards.exhaustPile[si]);
            break;
        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::ARMAMENTS:
        case CardSelectTask::DUAL_WIELD:
        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::WARCRY:
            if (si >= 0 && si < preState.cards.cardsInHand)
                e.cardKey = semanticCardKey(preState.cards.hand[si]);
            break;
        case CardSelectTask::SECRET_TECHNIQUE:
        case CardSelectTask::SECRET_WEAPON:
        case CardSelectTask::SEEK:
            if (si >= 0 && si < static_cast<int>(preState.cards.drawPile.size()))
                e.cardKey = semanticCardKey(preState.cards.drawPile[si]);
            break;
        default:
            break;   // not a semantically recordable single-select task
        }
        e.hasCardKey = e.cardKey.id != CardId::INVALID;
        if (e.selectTask == CardSelectTask::CODEX || e.selectTask == CardSelectTask::DISCOVERY) {
            for (const auto id : preState.cardSelectInfo.cards)
                e.selectSourcePile.emplace_back(id);
        } else if (e.selectTask == CardSelectTask::EXHUME) {
            e.selectSourcePile = preState.cards.exhaustPile;
        } else if (e.selectTask == CardSelectTask::HOLOGRAM
                   || e.selectTask == CardSelectTask::LIQUID_MEMORIES_POTION
                   || e.selectTask == CardSelectTask::HEADBUTT
                   || e.selectTask == CardSelectTask::MEDITATE) {
            e.selectSourcePile = preState.cards.discardPile;
        } else if (e.selectTask == CardSelectTask::SECRET_TECHNIQUE
                   || e.selectTask == CardSelectTask::SECRET_WEAPON
                   || e.selectTask == CardSelectTask::SEEK) {
            e.selectSourcePile = preState.cards.drawPile;
        } else {
            e.selectSourcePile.assign(preState.cards.hand.begin(),
                                      preState.cards.hand.begin() + preState.cards.cardsInHand);
        }
        if (si >= 0 && si < static_cast<int>(e.selectSourcePile.size()))
            e.selectedUniqueId = e.selectSourcePile[si].uniqueId;
        break;
    }
    case ActionType::MULTI_CARD_SELECT:
        // An intentionally empty selection is a distinct, valid semantic
        // identity (Gamble / EXHAUST_MANY select-none): keep hasMultiKeys
        // true even when multiKeys is empty.
        e.hasMultiKeys = true;
        for (int hi : action.getSelectedIdxs()) {
            if (hi < 0 || hi >= preState.cards.cardsInHand) continue;
            e.multiKeys.push_back(semanticCardKey(preState.cards.hand[hi]));
            e.multiUniqueIds.push_back(preState.cards.hand[hi].uniqueId);
        }
        std::sort(e.multiKeys.begin(), e.multiKeys.end());
        break;
    default:
        break;   // END_TURN / POTION replay raw bits directly
    }
    e.postObs = CombatObservation::fromBattleContext(postState);
    e.postOutcome = postState.outcome;
    entries.push_back(std::move(e));
}

HiddenBattleState oracleHiddenState(const BattleContext &anchor) {
    HiddenBattleState p;
    p.drawPileOrder = anchor.cards.drawPile;
    p.shuffleRngSeed0 = anchor.shuffleRng.seed0;
    p.shuffleRngSeed1 = anchor.shuffleRng.seed1;
    p.shuffleRngCounter = anchor.shuffleRng.counter;
    p.cardRandomRngSeed0 = anchor.cardRandomRng.seed0;
    p.cardRandomRngSeed1 = anchor.cardRandomRng.seed1;
    p.cardRandomRngCounter = anchor.cardRandomRng.counter;
    p.aiRngSeed0 = anchor.aiRng.seed0;
    p.aiRngSeed1 = anchor.aiRng.seed1;
    p.aiRngCounter = anchor.aiRng.counter;
    p.miscRngSeed0 = anchor.miscRng.seed0;
    p.miscRngSeed1 = anchor.miscRng.seed1;
    p.miscRngCounter = anchor.miscRng.counter;
    p.monsterHpRngSeed0 = anchor.monsterHpRng.seed0;
    p.monsterHpRngSeed1 = anchor.monsterHpRng.seed1;
    p.monsterHpRngCounter = anchor.monsterHpRng.counter;
    p.potionRngSeed0 = anchor.potionRng.seed0;
    p.potionRngSeed1 = anchor.potionRng.seed1;
    p.potionRngCounter = anchor.potionRng.counter;
    return p;
}

HiddenBattleState makeConditionalBlockProposal(
    const HiddenBattleState &oracle,
    const HiddenBattleState &fresh,
    S3RejuvenationProposalFamily family) {
    HiddenBattleState p = oracle;
    switch (family) {
    case S3RejuvenationProposalFamily::DRAW_ORDER: p.drawPileOrder = fresh.drawPileOrder; break;
    case S3RejuvenationProposalFamily::SHUFFLE_RNG:
        p.shuffleRngSeed0 = fresh.shuffleRngSeed0; p.shuffleRngSeed1 = fresh.shuffleRngSeed1;
        p.shuffleRngCounter = fresh.shuffleRngCounter; break;
    case S3RejuvenationProposalFamily::CARD_RANDOM_RNG:
        p.cardRandomRngSeed0 = fresh.cardRandomRngSeed0; p.cardRandomRngSeed1 = fresh.cardRandomRngSeed1;
        p.cardRandomRngCounter = fresh.cardRandomRngCounter; break;
    case S3RejuvenationProposalFamily::AI_RNG:
        p.aiRngSeed0 = fresh.aiRngSeed0; p.aiRngSeed1 = fresh.aiRngSeed1;
        p.aiRngCounter = fresh.aiRngCounter; break;
    case S3RejuvenationProposalFamily::MISC_RNG:
        p.miscRngSeed0 = fresh.miscRngSeed0; p.miscRngSeed1 = fresh.miscRngSeed1;
        p.miscRngCounter = fresh.miscRngCounter; break;
    case S3RejuvenationProposalFamily::MONSTER_HP_RNG:
        p.monsterHpRngSeed0 = fresh.monsterHpRngSeed0; p.monsterHpRngSeed1 = fresh.monsterHpRngSeed1;
        p.monsterHpRngCounter = fresh.monsterHpRngCounter; break;
    case S3RejuvenationProposalFamily::POTION_RNG:
        p.potionRngSeed0 = fresh.potionRngSeed0; p.potionRngSeed1 = fresh.potionRngSeed1;
        p.potionRngCounter = fresh.potionRngCounter; break;
    case S3RejuvenationProposalFamily::ORACLE: break;
    case S3RejuvenationProposalFamily::ALL_FRESH: p = fresh; break;
    }
    return p;
}

const char *proposalFamilyName(S3RejuvenationProposalFamily family) {
    switch (family) {
    case S3RejuvenationProposalFamily::ORACLE: return "ORACLE";
    case S3RejuvenationProposalFamily::DRAW_ORDER: return "DRAW_ORDER";
    case S3RejuvenationProposalFamily::SHUFFLE_RNG: return "SHUFFLE_RNG";
    case S3RejuvenationProposalFamily::CARD_RANDOM_RNG: return "CARD_RANDOM_RNG";
    case S3RejuvenationProposalFamily::AI_RNG: return "AI_RNG";
    case S3RejuvenationProposalFamily::MISC_RNG: return "MISC_RNG";
    case S3RejuvenationProposalFamily::MONSTER_HP_RNG: return "MONSTER_HP_RNG";
    case S3RejuvenationProposalFamily::POTION_RNG: return "POTION_RNG";
    case S3RejuvenationProposalFamily::ALL_FRESH: return "ALL_FRESH";
    }
    return "UNKNOWN";
}

const char *replayStatusName(S3RejuvenationReplayResult::Status status) {
    switch (status) {
    case S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED: return "FULL_HISTORY_ACCEPTED";
    case S3RejuvenationReplayResult::Status::REMAP_FAILURE: return "REMAP_FAILURE";
    case S3RejuvenationReplayResult::Status::ACTION_ILLEGAL: return "ACTION_ILLEGAL";
    case S3RejuvenationReplayResult::Status::SIM_HEALTH_FAILURE: return "SIM_HEALTH_FAILURE";
    case S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH: return "INTERMEDIATE_MISMATCH";
    case S3RejuvenationReplayResult::Status::FINAL_MISMATCH: return "FINAL_MISMATCH";
    }
    return "UNKNOWN";
}

// ── Semantic action remap ──────────────────────────────────────────────────
std::optional<Action> remapRejuvenationAction(const S3RejuvenationEntry &entry,
                                              const BattleContext &state) {
    switch (entry.action.getActionType()) {
    case ActionType::END_TURN:
    case ActionType::POTION:
        // Raw bits carry visible slot/target directly (hand order irrelevant).
        return entry.action;
    case ActionType::CARD: {
        if (!entry.hasCardKey) return std::nullopt;
        if (entry.selectedUniqueId >= 0) {
            for (int hi = 0; hi < state.cards.cardsInHand; ++hi) {
                if (state.cards.hand[hi].uniqueId == entry.selectedUniqueId) {
                    if (entry.cardKey.target >= 0)
                        return Action(ActionType::CARD, hi, entry.cardKey.target);
                    return Action(ActionType::CARD, hi);
                }
            }
        }
        const auto hi = resolveCardKeyInHand(entry.cardKey, state);
        if (!hi) return std::nullopt;
        if (entry.cardKey.target >= 0)
            return Action(ActionType::CARD, *hi, entry.cardKey.target);
        return Action(ActionType::CARD, *hi);
    }
    case ActionType::SINGLE_CARD_SELECT: {
        // CODEX index 3 is the explicit skip action, not a card identity.
        if (entry.selectTask == CardSelectTask::CODEX && entry.rawSelectIndex == 3)
            return entry.action;
        if (!entry.hasCardKey) return std::nullopt;
        const CardSelectTask task = state.cardSelectInfo.cardSelectTask;
        auto scanCard = [&](const std::vector<CardInstance> &pile) -> std::optional<int> {
            if (entry.selectedUniqueId >= 0) {
                for (size_t i = 0; i < pile.size(); ++i)
                    if (pile[i].uniqueId == entry.selectedUniqueId) return static_cast<int>(i);
            }
            for (size_t i = 0; i < pile.size(); ++i)
                if (matchesSemanticKey(pile[i], entry.cardKey)) return static_cast<int>(i);
            return std::nullopt;
        };
        switch (task) {
        case CardSelectTask::CODEX:
        case CardSelectTask::DISCOVERY:
            for (size_t i = 0; i < state.cardSelectInfo.cards.size(); ++i)
                if (state.cardSelectInfo.cards[i] == entry.cardKey.id)
                    return Action(ActionType::SINGLE_CARD_SELECT, static_cast<int>(i));
            return std::nullopt;
        case CardSelectTask::HOLOGRAM:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
        case CardSelectTask::HEADBUTT:
        case CardSelectTask::MEDITATE:
            if (auto i = scanCard(state.cards.discardPile))
                return Action(ActionType::SINGLE_CARD_SELECT, *i);
            return std::nullopt;
        case CardSelectTask::EXHUME:
            if (auto i = scanCard(state.cards.exhaustPile))
                return Action(ActionType::SINGLE_CARD_SELECT, *i);
            return std::nullopt;
        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::ARMAMENTS:
        case CardSelectTask::DUAL_WIELD:
        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::WARCRY:
        {
            if (entry.selectedUniqueId >= 0) {
                for (int hi = 0; hi < state.cards.cardsInHand; ++hi)
                    if (state.cards.hand[hi].uniqueId == entry.selectedUniqueId)
                        return Action(ActionType::SINGLE_CARD_SELECT, hi);
            }
            for (int hi = 0; hi < state.cards.cardsInHand; ++hi)
                if (matchesSemanticKey(state.cards.hand[hi], entry.cardKey))
                    return Action(ActionType::SINGLE_CARD_SELECT, hi);
            return std::nullopt;
        }
        case CardSelectTask::SECRET_TECHNIQUE:
        case CardSelectTask::SECRET_WEAPON:
        case CardSelectTask::SEEK:
            if (auto i = scanCard(state.cards.drawPile))
                return Action(ActionType::SINGLE_CARD_SELECT, *i);
            return std::nullopt;
        default:
            return std::nullopt;
        }
    }
    case ActionType::MULTI_CARD_SELECT: {
        if (!entry.hasMultiKeys) return std::nullopt;
        const CardSelectTask task = state.cardSelectInfo.cardSelectTask;
        if (task != CardSelectTask::EXHAUST_MANY && task != CardSelectTask::GAMBLE)
            return std::nullopt;
        if (state.cards.cardsInHand > 10) return std::nullopt;   // mask encodes <= 10 indices
        // Greedy multiset match of the recorded selected cards onto the hand.
        std::vector<char> used(entry.multiKeys.size(), 0);
        std::uint32_t mask = 0;
        if (entry.multiUniqueIds.size() == entry.multiKeys.size()
            && !entry.multiUniqueIds.empty()) {
            for (int hi = 0; hi < state.cards.cardsInHand; ++hi) {
                for (const auto uid : entry.multiUniqueIds) {
                    if (uid >= 0 && state.cards.hand[hi].uniqueId == uid) {
                        mask |= 1u << hi;
                        break;
                    }
                }
            }
            int matched = 0;
            for (const auto uid : entry.multiUniqueIds) {
                for (int hi = 0; hi < state.cards.cardsInHand; ++hi)
                    if (uid >= 0 && state.cards.hand[hi].uniqueId == uid) { ++matched; break; }
            }
            if (matched == static_cast<int>(entry.multiUniqueIds.size()))
                return Action(static_cast<std::uint32_t>(ActionType::MULTI_CARD_SELECT) << 29 | mask);
            mask = 0;
        }
        for (int hi = 0; hi < state.cards.cardsInHand; ++hi) {
            const auto key = semanticCardKey(state.cards.hand[hi]);
            for (size_t k = 0; k < entry.multiKeys.size(); ++k) {
                if (!used[k] && entry.multiKeys[k] == key) {
                    used[k] = 1;
                    mask |= 1u << hi;
                    break;
                }
            }
        }
        for (size_t k = 0; k < entry.multiKeys.size(); ++k)
            if (!used[k]) return std::nullopt;   // recorded selection not reproducible
        return Action(static_cast<std::uint32_t>(ActionType::MULTI_CARD_SELECT) << 29 | mask);
    }
    default:
        return std::nullopt;
    }
}

static std::optional<int> remappedSelectIndex(const S3RejuvenationEntry &entry,
                                              const BattleContext &state) {
    const auto a = remapRejuvenationAction(entry, state);
    return a ? std::optional<int>(a->getSelectIdx()) : std::nullopt;
}

// ── Full-history replay ────────────────────────────────────────────────────
static S3RejuvenationReplayResult replayRejuvenationHistoryImpl(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng,
    bool semantic) {
    S3RejuvenationReplayResult result;
    if (history.entries.empty()) return result;   // nothing recorded: not accepted
    BattleContext state = history.anchor;
    applyHiddenState(state, particle, fallbackRng);
    bool allMatched = true;
    for (size_t i = 0; i < history.entries.size(); ++i) {
        const auto &e = history.entries[i];
        const auto remapped = semantic ? remapRejuvenationAction(e, state)
                                       : std::optional<Action>(e.action);
        if (!remapped) {
            if (allMatched) {
                result.status = S3RejuvenationReplayResult::Status::REMAP_FAILURE;
                result.firstMismatchIndex = static_cast<int>(i);
                result.firstMismatchActionType = static_cast<int>(e.action.getActionType());
                if (semantic && e.action.getActionType() == ActionType::SINGLE_CARD_SELECT)
                    result.firstRemappedIndex = remappedSelectIndex(e, state).value_or(-1);
                return result;
            }
            // First failure was an intermediate mismatch; the final-only
            // diagnostic cannot continue. Keep the first-failure status.
            result.status = S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH;
            result.finalDiagAborted = true;
            return result;
        }
        if (!remapped->isValidAction(state)) {
            if (allMatched) {
                result.status = S3RejuvenationReplayResult::Status::ACTION_ILLEGAL;
                result.firstMismatchIndex = static_cast<int>(i);
                result.firstMismatchActionType = static_cast<int>(e.action.getActionType());
                if (semantic && e.action.getActionType() == ActionType::SINGLE_CARD_SELECT)
                    result.firstRemappedIndex = remappedSelectIndex(e, state).value_or(-1);
                return result;
            }
            result.status = S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH;
            result.finalDiagAborted = true;
            return result;
        }
        remapped->execute(state);
        ++result.transitionsExecuted;
        const CombatObservation obs = CombatObservation::fromBattleContext(state);
        const bool matched = obs == e.postObs && state.outcome == e.postOutcome;
        if (!matched && allMatched) {
            result.firstMismatchIndex = static_cast<int>(i);
            result.firstMismatchActionType = static_cast<int>(e.action.getActionType());
            allMatched = false;
        }
        // Simulator health: the replay battle ended before the recorded
        // history was exhausted (real histories never continue post-termination).
        if (state.outcome != Outcome::UNDECIDED && i + 1 < history.entries.size()) {
            if (allMatched) {
                result.status = S3RejuvenationReplayResult::Status::SIM_HEALTH_FAILURE;
                return result;
            }
            result.status = S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH;
            result.finalDiagAborted = true;
            return result;
        }
        if (i + 1 == history.entries.size()) result.finalObsMatched = matched;
    }
    result.finalState = state;
    result.hasFinalState = true;
    if (allMatched) {
        result.status = S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED;
    } else if (result.firstMismatchIndex == static_cast<int>(history.entries.size()) - 1) {
        // The first (and only) failure was the final boundary.
        result.status = S3RejuvenationReplayResult::Status::FINAL_MISMATCH;
    } else {
        result.status = S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH;
    }
    return result;
}

S3RejuvenationReplayResult replayRejuvenationHistory(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng) {
    return replayRejuvenationHistoryImpl(history, particle, fallbackRng, true);
}

S3RejuvenationReplayResult replayRejuvenationHistoryRaw(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng) {
    return replayRejuvenationHistoryImpl(history, particle, fallbackRng, false);
}

// ── Shadow probe driver ────────────────────────────────────────────────────
void runRejuvenationShadowProbe(const S3RejuvenationHistory &history,
                                const RealBeliefFilterStats &filterStats,
                                const Belief &belief,
                                const BattleContext &bc,
                                int sourceFilterDecisionIdx,
                                int searchDecisionIdx,
                                bool nextSearchEligible) {
    if (history.entries.empty()) return;
    if ((!g_s3RejuvShadow && !g_s3AiSensitivityShadow)
        || filterStats.compatible > g_s3RejuvTrigger) return;
    const int proposals = std::max(1, g_s3RejuvProposals);

    // Deterministic probe RNG stream, independent of all battle RNG.
    std::uint64_t h = 0x9e3779b97f4a7c15ULL;
    auto mix = [&h](std::uint64_t x) {
        h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    };
    mix(bc.seed);
    mix(static_cast<std::uint64_t>(bc.floorNum));
    mix(static_cast<std::uint64_t>(bc.encounter));
    mix(static_cast<std::uint64_t>(bc.turn));
    mix(static_cast<std::uint64_t>(sourceFilterDecisionIdx));
    mix(static_cast<std::uint64_t>(history.entries.size()));
    std::mt19937_64 proposalRng(h ? h : 1);
    const HiddenBattleState oracle = oracleHiddenState(history.anchor);
    const auto fresh = HiddenBattleState::sampleParticles(
        history.anchorObs, history.anchor, proposalRng, proposals);

    // Existing posterior support at the current hidden state: the positive
    // particles already propagated by filterRealTransition. When the filter
    // lost all support (compatible == 0) the pre-fallback survivor set is
    // empty; the collapseFresh replacement belief is not a comparator.
    std::set<FullHiddenStateKey> existingSupport;
    if (filterStats.compatible > 0) {
        for (const auto &p : belief.particles)
            if (p.weight > 0) existingSupport.insert(fullHiddenStateKey(p));
    }
    std::vector<HiddenBattleState> acceptedAiStates;
    std::set<FullHiddenStateKey> acceptedAiKeys;

    std::array<std::int32_t, 6> counters = {
        bc.shuffleRng.counter, bc.cardRandomRng.counter, bc.aiRng.counter,
        bc.miscRng.counter, bc.monsterHpRng.counter, bc.potionRng.counter};
    std::array<std::int32_t, 6> anchorCounters = {
        history.anchor.shuffleRng.counter, history.anchor.cardRandomRng.counter,
        history.anchor.aiRng.counter, history.anchor.miscRng.counter,
        history.anchor.monsterHpRng.counter, history.anchor.potionRng.counter};

    const std::array<S3RejuvenationProposalFamily, 8> families = {
        S3RejuvenationProposalFamily::DRAW_ORDER,
        S3RejuvenationProposalFamily::SHUFFLE_RNG,
        S3RejuvenationProposalFamily::CARD_RANDOM_RNG,
        S3RejuvenationProposalFamily::AI_RNG,
        S3RejuvenationProposalFamily::MISC_RNG,
        S3RejuvenationProposalFamily::MONSTER_HP_RNG,
        S3RejuvenationProposalFamily::POTION_RNG,
        S3RejuvenationProposalFamily::ALL_FRESH};
    auto mixSeed = [h](int index, S3RejuvenationProposalFamily family) {
        std::uint64_t x = h ^ (static_cast<std::uint64_t>(index + 1) * 0x9e3779b97f4a7c15ULL);
        x ^= static_cast<std::uint64_t>(family) * 0xbf58476d1ce4e5b9ULL;
        x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL; x ^= x >> 27;
        return x ^ (x >> 31);
    };

    auto writeFamily = [&](S3RejuvenationProposalFamily family,
                           const std::vector<HiddenBattleState> &sources,
                           int count) {
        int acceptedCount = 0, finalStateCompatible = 0, finalDiagAborted = 0;
        int remapFailures = 0, actionIllegal = 0, simHealthFailures = 0;
        int intermediateMismatch = 0, finalMismatch = 0, firstMismatchCount = 0;
        std::int64_t totalTransitions = 0, mismatchSum = 0;
        int mismatchMin = -1, mismatchMax = -1;
        std::map<int, int> mismatchActions;
        std::set<FullHiddenStateKey> acceptedKeys;
        std::set<std::uint64_t> acceptedDrawOrders, acceptedRngSignatures;
        std::array<int, 4> milestones = {-1, -1, -1, -1};
        std::string oracleStatus, oracleRawStatus;
        const auto t0 = std::chrono::steady_clock::now();
        for (int i = 0; i < count; ++i) {
            const HiddenBattleState p = family == S3RejuvenationProposalFamily::ORACLE
                ? oracle : makeConditionalBlockProposal(oracle, sources[i], family);
            std::mt19937_64 fallbackRng(mixSeed(i, family));
            const auto res = replayRejuvenationHistory(history, p, fallbackRng);
            if (family == S3RejuvenationProposalFamily::ORACLE) {
                std::mt19937_64 rawFallbackRng(mixSeed(i, S3RejuvenationProposalFamily::ORACLE));
                const auto raw = replayRejuvenationHistoryRaw(history, p, rawFallbackRng);
                oracleStatus = replayStatusName(res.status);
                oracleRawStatus = replayStatusName(raw.status);
                if (res.status != S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED) {
                    std::cerr << "[S3 oracle replay] seed=" << bc.seed
                              << " floor=" << bc.floorNum
                              << " encounter=" << static_cast<int>(bc.encounter)
                              << " decision=" << sourceFilterDecisionIdx
                              << " boundary=" << res.firstMismatchIndex
                              << " action_type=" << res.firstMismatchActionType;
                    if (res.firstMismatchIndex >= 0
                        && res.firstMismatchIndex < static_cast<int>(history.entries.size())) {
                        const auto &e = history.entries[res.firstMismatchIndex];
                        if (e.action.getActionType() == ActionType::SINGLE_CARD_SELECT) {
                            std::cerr << " task=" << static_cast<int>(e.selectTask)
                                      << " raw_select=" << e.rawSelectIndex
                                      << " semantic_select=" << res.firstRemappedIndex
                                      << " source_size=" << e.selectSourcePile.size()
                                      << " source_ids=";
                            for (const auto &c : e.selectSourcePile)
                                std::cerr << static_cast<int>(c.getId()) << ':'
                                          << static_cast<int>(c.getUpgradeCount()) << ',';
                        }
                    }
                    std::cerr << " raw_status=" << oracleRawStatus << '\n';
                }
            }
            if (family == S3RejuvenationProposalFamily::ORACLE)
                oracleStatus = replayStatusName(res.status);
            totalTransitions += res.transitionsExecuted;
            switch (res.status) {
            case S3RejuvenationReplayResult::Status::REMAP_FAILURE: ++remapFailures; break;
            case S3RejuvenationReplayResult::Status::ACTION_ILLEGAL: ++actionIllegal; break;
            case S3RejuvenationReplayResult::Status::SIM_HEALTH_FAILURE: ++simHealthFailures; break;
            case S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH: ++intermediateMismatch; break;
            case S3RejuvenationReplayResult::Status::FINAL_MISMATCH: ++finalMismatch; break;
            case S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED: break;
            }
            if (res.firstMismatchIndex >= 0) {
                ++firstMismatchCount; mismatchSum += res.firstMismatchIndex;
                mismatchMin = mismatchMin < 0 ? res.firstMismatchIndex : std::min(mismatchMin, res.firstMismatchIndex);
                mismatchMax = std::max(mismatchMax, res.firstMismatchIndex);
                ++mismatchActions[res.firstMismatchActionType];
            }
            if (res.finalObsMatched) ++finalStateCompatible;
            if (res.finalDiagAborted) ++finalDiagAborted;
            if (res.status == S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED) {
                ++acceptedCount;
                if (family == S3RejuvenationProposalFamily::AI_RNG) {
                    const auto current = oracleHiddenState(res.finalState);
                    if (acceptedAiKeys.insert(fullHiddenStateKey(current)).second)
                        acceptedAiStates.push_back(current);
                }
                const FullHiddenStateKey key = fullHiddenStateKey(res.finalState);
                acceptedDrawOrders.insert(drawOrderOnlyHash(key));
                acceptedRngSignatures.insert(rngOnlyHash(key));
                if (acceptedKeys.insert(key).second) {
                    const std::size_t n = acceptedKeys.size();
                    if (n == 4) milestones[0] = i + 1;
                    if (n == 8) milestones[1] = i + 1;
                    if (n == 16) milestones[2] = i + 1;
                    if (n == 32) milestones[3] = i + 1;
                }
            }
        }
        const auto t1 = std::chrono::steady_clock::now();
        const double cpuMs = std::chrono::duration<double, std::milli>(t1 - t0).count();
        int novel = 0;
        for (const auto &k : acceptedKeys) if (!existingSupport.count(k)) ++novel;
        std::ostringstream mismatchText;
        for (const auto &[type, n] : mismatchActions) {
            if (mismatchText.tellp() > 0) mismatchText << ';';
            mismatchText << type << ':' << n;
        }
        std::vector<std::string> row = {
            std::to_string(bc.seed), std::to_string(static_cast<int>(bc.encounter)),
            std::to_string(bc.floorNum), std::to_string(sourceFilterDecisionIdx),
            std::to_string(bc.turn),
            std::to_string(filterStats.compatible), std::to_string(filterStats.attempted),
            std::to_string(filterStats.posteriorCollapse ? 1 : 0),
            std::to_string(filterStats.freshBeliefRebuilt ? 1 : 0),
            std::to_string(belief.positiveCount()), std::to_string(history.entries.size()),
            proposalFamilyName(family), oracleStatus, oracleRawStatus,
            std::to_string(count), std::to_string(acceptedCount),
            enc(static_cast<double>(acceptedCount) / count),
            std::to_string(acceptedKeys.size()), std::to_string(acceptedCount - acceptedKeys.size()),
            std::to_string(novel), std::to_string(finalStateCompatible),
            std::to_string(finalStateCompatible - acceptedCount), std::to_string(remapFailures),
            std::to_string(actionIllegal), std::to_string(simHealthFailures),
            std::to_string(intermediateMismatch), std::to_string(finalMismatch),
            std::to_string(finalDiagAborted), std::to_string(totalTransitions),
            std::to_string(acceptedDrawOrders.size()), std::to_string(acceptedRngSignatures.size()),
            std::to_string(milestones[0]), std::to_string(milestones[1]), std::to_string(milestones[2]),
            std::to_string(milestones[3]), std::to_string(firstMismatchCount),
            enc(firstMismatchCount ? static_cast<double>(mismatchSum) / firstMismatchCount : -1.0),
            std::to_string(mismatchMin), std::to_string(mismatchMax), mismatchText.str()};
        for (int c : counters) row.push_back(std::to_string(c));
        for (int i = 0; i < 6; ++i) row.push_back(std::to_string(counters[i] - anchorCounters[i]));
        row.push_back(enc(cpuMs)); row.push_back(enc(cpuMs / count));
        writeRejuvCsvRow(row);
    };

    // Oracle is a single control row; all proposal families share the same
    // paired source vector and are independent of family iteration order.
    std::vector<HiddenBattleState> noSources(1, oracle);
    writeFamily(S3RejuvenationProposalFamily::ORACLE, noSources, 1);
    for (const auto family : families) writeFamily(family, fresh, proposals);
    runAiSensitivityShadow(history, filterStats, belief, bc, sourceFilterDecisionIdx,
                           searchDecisionIdx < 0 ? sourceFilterDecisionIdx + 1 : searchDecisionIdx,
                           nextSearchEligible, acceptedAiStates);
}

void runAiSensitivityShadow(const S3RejuvenationHistory &history,
                            const RealBeliefFilterStats &filterStats,
                            const Belief &belief,
                            const BattleContext &bc,
                            int sourceFilterDecisionIdx,
                            int searchDecisionIdx,
                            bool nextSearchEligible,
                            const std::vector<HiddenBattleState> &acceptedAiStates) {
    (void)history;
    if (!g_s3AiSensitivityShadow || g_s3AiSensitivityFile.empty()) return;
    if (g_s3Crn) {
        std::cerr << "[S3 AI sensitivity] unsupported with STS_S3_CRN=1; skipped\n";
        return;
    }
    if (!nextSearchEligible || bc.outcome != Outcome::UNDECIDED
        || sourceFilterDecisionIdx < 8 || searchDecisionIdx != sourceFilterDecisionIdx + 1
        || acceptedAiStates.size() < 8
        || bc.aiRng.counter <= history.anchor.aiRng.counter) return;

    BattleScumSearcher3::Node liveRoot;
    enumerateActionsForNode(liveRoot, bc);
    int meaningful = 0;
    for (const auto &edge : liveRoot.edges)
        if (edge.action.isValidAction(bc)) ++meaningful;
    if (meaningful < 2) return;

    static std::mutex rootMutex;
    static std::map<std::uint64_t, int> rootsBySeed;
    static std::set<std::tuple<std::uint64_t, int, int>> rootGroups;
    static int totalRoots = 0;
    std::lock_guard<std::mutex> lock(rootMutex);
    if (rootsBySeed[bc.seed] >= std::max(1, g_s3AiSensitivityRootsPerSeed)
        || totalRoots >= 32) return;
    const auto group = std::make_tuple(bc.seed, static_cast<int>(bc.encounter), bc.floorNum);
    if (rootGroups.count(group)) return;

    const HiddenBattleState oracle = oracleHiddenState(bc);
    const bool supportEmpty = filterStats.compatible == 0;
    std::set<FullHiddenStateKey> existingSupport;
    if (!supportEmpty)
        for (const auto &p : belief.particles)
            if (p.weight > 0.0) existingSupport.insert(fullHiddenStateKey(p));
    std::vector<HiddenBattleState> candidates;
    std::set<FullHiddenStateKey> chosen;
    for (const auto &candidate : acceptedAiStates) {
        const auto key = fullHiddenStateKey(candidate);
        if (existingSupport.count(key) || !chosen.insert(key).second) continue;
        BattleContext candidateBc = bc;
        std::mt19937_64 fallback(0x4d595df4d0f33173ULL);
        applyHiddenState(candidateBc, candidate, fallback);
        if (!sameCurrentBoundary(bc, candidate, candidateBc, true)) {
            writeSensitivityRow({std::to_string(bc.seed), std::to_string(static_cast<int>(bc.encounter)),
                std::to_string(bc.floorNum), std::to_string(sourceFilterDecisionIdx),
                std::to_string(searchDecisionIdx), std::to_string(bc.turn),
                std::to_string(CombatObservation::fromBattleContext(bc).visibleHash()), "AI_ALT",
                "-1", std::to_string(hiddenIdentityHash(candidate)), "", "", "", "", "",
                "BLOCK_ISOLATION_FAILURE", "NOT_EVALUATED", "", "", "", "", "", "", "",
                std::to_string(candidates.size()), std::to_string(supportEmpty)});
            continue;
        }
        candidates.push_back(candidate);
        if (static_cast<int>(candidates.size()) >= std::max(1, g_s3AiSensitivityAlternatives)) break;
    }
    if (candidates.empty()) return;

    ++rootsBySeed[bc.seed];
    ++totalRoots;
    rootGroups.insert(group);
    const auto rootHash = CombatObservation::fromBattleContext(bc).visibleHash();
    BattleScumSearcher3 oracleA(bc, bc.seed, searchDecisionIdx, 64);
    runFixedHiddenSearch(oracle, g_s3AiSensitivitySims, oracleA);
    const RootMetrics oracleMetrics = rootMetrics(oracleA);
    const auto oracleSelected = selectedRootAction(oracleA, bc);
    bool controlOk = true;
    runSensitivityCondition(bc, oracle, "ORACLE_A", 0, rootHash, sourceFilterDecisionIdx,
                             searchDecisionIdx, oracleMetrics, oracleSelected, candidates.size(),
                             supportEmpty, oracleMetrics, controlOk);
    BattleScumSearcher3 oracleB(bc, bc.seed, searchDecisionIdx, 64);
    runFixedHiddenSearch(oracle, g_s3AiSensitivitySims, oracleB);
    const RootMetrics oracleBMetrics = rootMetrics(oracleB);
    runSensitivityCondition(bc, oracle, "ORACLE_B", 0, rootHash, sourceFilterDecisionIdx,
                             searchDecisionIdx, oracleMetrics, oracleSelected, candidates.size(),
                             supportEmpty, oracleBMetrics, controlOk);
    for (size_t i = 0; i < candidates.size() && controlOk; ++i)
    {
        BattleScumSearcher3 alt(bc, bc.seed, searchDecisionIdx, 64);
        runFixedHiddenSearch(candidates[i], g_s3AiSensitivitySims, alt);
        runSensitivityCondition(bc, candidates[i], "AI_ALT", static_cast<int>(i + 1), rootHash,
                                sourceFilterDecisionIdx, searchDecisionIdx, oracleMetrics,
                                oracleSelected, candidates.size(), supportEmpty,
                                rootMetrics(alt), controlOk);
    }
    if (!controlOk) {
        std::cerr << "[S3 AI sensitivity] ORACLE_DUPLICATE_FAILURE seed=" << bc.seed
                  << " floor=" << bc.floorNum << " encounter=" << static_cast<int>(bc.encounter)
                  << " decision=" << sourceFilterDecisionIdx << '\n';
    }
}

} // namespace sts::search
