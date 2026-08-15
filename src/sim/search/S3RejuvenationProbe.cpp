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

namespace sts::search {

// Flags (env STS_S3_REJUV_*; off by default).
bool g_s3RejuvShadow = false;
int g_s3RejuvTrigger = 16;
int g_s3RejuvProposals = 256;
std::string g_s3RejuvShadowFile;

namespace {

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
               "oracle_status,proposals,accepted,acceptance_rate,"
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
    switch (action.getActionType()) {
    case ActionType::CARD:
        // Hand card: full canonical identity + target via the shared CARD key
        // helper (independent of hand position).
        e.cardKey = BattleScumSearcher3::cardActionKey(preState, action);
        e.hasCardKey = e.cardKey.id != CardId::INVALID;
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
        const auto hi = resolveCardKeyInHand(entry.cardKey, state);
        if (!hi) return std::nullopt;
        if (entry.cardKey.target >= 0)
            return Action(ActionType::CARD, *hi, entry.cardKey.target);
        return Action(ActionType::CARD, *hi);
    }
    case ActionType::SINGLE_CARD_SELECT: {
        if (!entry.hasCardKey) return std::nullopt;
        const CardSelectTask task = state.cardSelectInfo.cardSelectTask;
        auto scanCard = [&](const std::vector<CardInstance> &pile) -> std::optional<int> {
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

// ── Full-history replay ────────────────────────────────────────────────────
S3RejuvenationReplayResult replayRejuvenationHistory(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng) {
    S3RejuvenationReplayResult result;
    if (history.entries.empty()) return result;   // nothing recorded: not accepted
    BattleContext state = history.anchor;
    applyHiddenState(state, particle, fallbackRng);
    bool allMatched = true;
    for (size_t i = 0; i < history.entries.size(); ++i) {
        const auto &e = history.entries[i];
        const auto remapped = remapRejuvenationAction(e, state);
        if (!remapped) {
            if (allMatched) {
                result.status = S3RejuvenationReplayResult::Status::REMAP_FAILURE;
                result.firstMismatchIndex = static_cast<int>(i);
                result.firstMismatchActionType = static_cast<int>(e.action.getActionType());
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

// ── Shadow probe driver ────────────────────────────────────────────────────
void runRejuvenationShadowProbe(const S3RejuvenationHistory &history,
                                const RealBeliefFilterStats &filterStats,
                                const Belief &belief,
                                const BattleContext &bc,
                                int decisionIdx) {
    if (history.entries.empty() || g_s3RejuvShadowFile.empty()) return;
    if (!g_s3RejuvShadow || filterStats.compatible > g_s3RejuvTrigger) return;
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
    mix(static_cast<std::uint64_t>(decisionIdx));
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
        std::string oracleStatus;
        const auto t0 = std::chrono::steady_clock::now();
        for (int i = 0; i < count; ++i) {
            const HiddenBattleState p = family == S3RejuvenationProposalFamily::ORACLE
                ? oracle : makeConditionalBlockProposal(oracle, sources[i], family);
            std::mt19937_64 fallbackRng(mixSeed(i, family));
            const auto res = replayRejuvenationHistory(history, p, fallbackRng);
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
            std::to_string(bc.floorNum), std::to_string(decisionIdx), std::to_string(bc.turn),
            std::to_string(filterStats.compatible), std::to_string(filterStats.attempted),
            std::to_string(filterStats.posteriorCollapse ? 1 : 0),
            std::to_string(filterStats.freshBeliefRebuilt ? 1 : 0),
            std::to_string(belief.positiveCount()), std::to_string(history.entries.size()),
            proposalFamilyName(family), oracleStatus, std::to_string(count), std::to_string(acceptedCount),
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
}

} // namespace sts::search
