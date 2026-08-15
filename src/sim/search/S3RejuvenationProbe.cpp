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
               "collapse,fresh_rebuild,posterior_support,proposals,accepted,"
               "unique,duplicate,novel,final_state_compatible,final_only_not_full,"
               "remap_failure,action_illegal,sim_health,intermediate_mismatch,"
               "final_mismatch,final_diag_aborted,transitions,unique_draw_orders,"
               "unique_rng,m4,m8,m16,m32,cpu_ms,cpu_per_proposal_ms\n";
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

BattleScumSearcher3::CardActionKey handCardKey(const CardInstance &c) {
    BattleScumSearcher3::CardActionKey k;
    k.id = c.getId();
    k.upgradeCount = c.getUpgradeCount();
    k.costForTurn = c.costForTurn;
    k.freeToPlayOnce = c.freeToPlayOnce;
    k.specialData = c.specialData;
    k.target = -1;
    return k;
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
    case ActionType::SINGLE_CARD_SELECT:
        e.cardKey = BattleScumSearcher3::cardActionKey(preState, action);
        e.hasCardKey = e.cardKey.id != CardId::INVALID;
        break;
    case ActionType::MULTI_CARD_SELECT:
        for (int hi : action.getSelectedIdxs()) {
            if (hi < 0 || hi >= preState.cards.cardsInHand) continue;
            e.multiKeys.push_back(handCardKey(preState.cards.hand[hi]));
        }
        e.hasMultiKeys = !e.multiKeys.empty();
        std::sort(e.multiKeys.begin(), e.multiKeys.end());
        break;
    default:
        break;   // END_TURN / POTION replay raw bits directly
    }
    e.postObs = CombatObservation::fromBattleContext(postState);
    e.postOutcome = postState.outcome;
    entries.push_back(std::move(e));
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
        auto scan = [&](const std::vector<CardInstance> &pile) -> std::optional<int> {
            for (size_t i = 0; i < pile.size(); ++i)
                if (pile[i].getId() == entry.cardKey.id) return static_cast<int>(i);
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
            if (auto i = scan(state.cards.discardPile))
                return Action(ActionType::SINGLE_CARD_SELECT, *i);
            return std::nullopt;
        case CardSelectTask::EXHUME:
            if (auto i = scan(state.cards.exhaustPile))
                return Action(ActionType::SINGLE_CARD_SELECT, *i);
            return std::nullopt;
        case CardSelectTask::EXHAUST_ONE:
        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::NIGHTMARE:
        case CardSelectTask::RECYCLE:
        case CardSelectTask::SETUP:
        case CardSelectTask::WARCRY:
        case CardSelectTask::ARMAMENTS:
        case CardSelectTask::DUAL_WIELD: {
            for (int hi = 0; hi < state.cards.cardsInHand; ++hi)
                if (state.cards.hand[hi].getId() == entry.cardKey.id)
                    return Action(ActionType::SINGLE_CARD_SELECT, hi);
            return std::nullopt;
        }
        case CardSelectTask::SECRET_TECHNIQUE:
        case CardSelectTask::SECRET_WEAPON:
        case CardSelectTask::SEEK:
            if (auto i = scan(state.cards.drawPile))
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
            const auto key = handCardKey(state.cards.hand[hi]);
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
    result.status = allMatched
        ? S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED
        : S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH;
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
    std::mt19937_64 probeRng(h ? h : 1);

    // Existing posterior support at the current hidden state: the positive
    // particles already propagated by filterRealTransition. When the filter
    // lost all support (compatible == 0) the pre-fallback survivor set is
    // empty; the collapseFresh replacement belief is not a comparator.
    std::set<FullHiddenStateKey> existingSupport;
    if (filterStats.compatible > 0) {
        for (const auto &p : belief.particles)
            if (p.weight > 0) existingSupport.insert(fullHiddenStateKey(p));
    }

    int acceptedCount = 0, finalStateCompatible = 0, finalDiagAborted = 0;
    int remapFailures = 0, actionIllegal = 0, simHealthFailures = 0;
    int intermediateMismatch = 0, finalMismatch = 0;
    std::int64_t totalTransitions = 0;
    std::set<FullHiddenStateKey> acceptedKeys;
    std::set<std::uint64_t> acceptedDrawOrders, acceptedRngSignatures;
    std::array<int, 4> milestones = {-1, -1, -1, -1};

    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < proposals; ++i) {
        auto p = HiddenBattleState::sampleParticles(history.anchorObs, history.anchor,
                                                    probeRng, 1)[0];
        const auto res = replayRejuvenationHistory(history, p, probeRng);
        totalTransitions += res.transitionsExecuted;
        switch (res.status) {
        case S3RejuvenationReplayResult::Status::REMAP_FAILURE: ++remapFailures; break;
        case S3RejuvenationReplayResult::Status::ACTION_ILLEGAL: ++actionIllegal; break;
        case S3RejuvenationReplayResult::Status::SIM_HEALTH_FAILURE: ++simHealthFailures; break;
        case S3RejuvenationReplayResult::Status::INTERMEDIATE_MISMATCH: ++intermediateMismatch; break;
        case S3RejuvenationReplayResult::Status::FINAL_MISMATCH: ++finalMismatch; break;
        case S3RejuvenationReplayResult::Status::FULL_HISTORY_ACCEPTED: break;
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

    const int unique = static_cast<int>(acceptedKeys.size());
    const int duplicate = acceptedCount - unique;
    int novel = 0;
    for (const auto &k : acceptedKeys)
        if (!existingSupport.count(k)) ++novel;
    const int finalOnlyNotFull = finalStateCompatible - acceptedCount;

    writeRejuvCsvRow({
        std::to_string(bc.seed),
        std::to_string(static_cast<int>(bc.encounter)),
        std::to_string(bc.floorNum),
        std::to_string(decisionIdx),
        std::to_string(bc.turn),
        std::to_string(filterStats.compatible),
        std::to_string(filterStats.attempted),
        std::to_string(filterStats.posteriorCollapse ? 1 : 0),
        std::to_string(filterStats.freshBeliefRebuilt ? 1 : 0),
        std::to_string(belief.positiveCount()),
        std::to_string(proposals),
        std::to_string(acceptedCount),
        std::to_string(unique),
        std::to_string(duplicate),
        std::to_string(novel),
        std::to_string(finalStateCompatible),
        std::to_string(finalOnlyNotFull),
        std::to_string(remapFailures),
        std::to_string(actionIllegal),
        std::to_string(simHealthFailures),
        std::to_string(intermediateMismatch),
        std::to_string(finalMismatch),
        std::to_string(finalDiagAborted),
        std::to_string(totalTransitions),
        std::to_string(acceptedDrawOrders.size()),
        std::to_string(acceptedRngSignatures.size()),
        std::to_string(milestones[0]),
        std::to_string(milestones[1]),
        std::to_string(milestones[2]),
        std::to_string(milestones[3]),
        enc(cpuMs),
        enc(cpuMs / proposals),
    });
}

} // namespace sts::search
