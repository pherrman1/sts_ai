//
// S3RejuvenationProbe: opt-in, shadow-only rejuvenation probe for Searcher3.
//
// When enabled (STS_S3_REJUV_SHADOW=1), each filtered real-observation
// boundary with compatible <= STS_S3_REJUV_TRIGGER appends the committed
// semantic action + real post-action observation to a per-combat history
// anchored at battle start, then samples fresh hidden-state hypotheses from
// the anchor observation and replays the FULL recorded history under each
// (semantic action remap + exact observation/outcome equality). Accepted
// hypotheses are evidence that the persistent filtered posterior's loss of
// support is particle depletion (in-principle recoverable) rather than a hard
// history inconsistency. Pure telemetry: nothing here mutates the live
// battle, the searcher, its belief, or any battle RNG.
//
#ifndef STS_LIGHTSPEED_S3REJUVENATIONPROBE_H
#define STS_LIGHTSPEED_S3REJUVENATIONPROBE_H

#include "sim/search/Action.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/CombatObservation.h"

#include <optional>
#include <random>
#include <string>
#include <vector>

namespace sts::search {

// One committed real boundary: semantic action identity (position-independent)
// + raw bits + the real post-action observation + outcome.
struct S3RejuvenationEntry {
    Action action;
    bool hasCardKey = false;                     // CARD / SINGLE_CARD_SELECT
    BattleScumSearcher3::CardActionKey cardKey;
    bool hasMultiKeys = false;                   // MULTI_CARD_SELECT
    std::vector<BattleScumSearcher3::CardActionKey> multiKeys;
    std::vector<std::int16_t> multiUniqueIds;
    CardSelectTask selectTask = CardSelectTask::INVALID;
    int rawSelectIndex = -1;
    std::int16_t selectedUniqueId = -1;
    std::vector<CardInstance> selectSourcePile;
    CombatObservation postObs;
    Outcome postOutcome = Outcome::UNDECIDED;
};

// Full real observation/action history of one combat, anchored at battle
// start. Holds a copy of the anchor state so replay is fully independent of
// the live battle.
struct S3RejuvenationHistory {
    BattleContext anchor;
    CombatObservation anchorObs;
    std::vector<S3RejuvenationEntry> entries;

    explicit S3RejuvenationHistory(const BattleContext &battleStart);
    void record(const BattleContext &preState, const Action &action,
                const BattleContext &postState);
};

enum class S3RejuvenationProposalFamily {
    ORACLE,
    DRAW_ORDER,
    SHUFFLE_RNG,
    CARD_RANDOM_RNG,
    AI_RNG,
    MISC_RNG,
    MONSTER_HP_RNG,
    POTION_RNG,
    ALL_FRESH,
};

HiddenBattleState oracleHiddenState(const BattleContext &anchor);
HiddenBattleState makeConditionalBlockProposal(
    const HiddenBattleState &oracle,
    const HiddenBattleState &fresh,
    S3RejuvenationProposalFamily family);
const char *proposalFamilyName(S3RejuvenationProposalFamily family);

// Remap a recorded semantic action onto a replay state whose hand order may
// differ from the live one. END_TURN / POTION replay their raw bits directly
// (visible slot/target); CARD / SINGLE_CARD_SELECT resolve by card identity;
// MULTI_CARD_SELECT matches the recorded selected multiset onto the hand.
// Returns nullopt when no semantic counterpart exists (proposal discarded,
// never a history rejection).
std::optional<Action> remapRejuvenationAction(const S3RejuvenationEntry &entry,
                                              const BattleContext &state);

// Outcome of replaying the full history under one hidden-state hypothesis.
struct S3RejuvenationReplayResult {
    enum class Status {
        FULL_HISTORY_ACCEPTED,   // every recorded boundary obs+outcome matched
        REMAP_FAILURE,           // first failure: semantic remap impossible
        ACTION_ILLEGAL,          // first failure: remapped action not legal
        SIM_HEALTH_FAILURE,      // first failure: replay ended early / stuck
        INTERMEDIATE_MISMATCH,   // an intermediate boundary mismatched
        FINAL_MISMATCH,          // all intermediates matched, final mismatched
    };
    Status status = Status::FINAL_MISMATCH;
    int firstMismatchIndex = -1;    // boundary of the first obs/outcome mismatch
    int firstMismatchActionType = -1;
    int firstRemappedIndex = -1;
    bool finalObsMatched = false;   // final-state-compatible diagnostic
    bool finalDiagAborted = false;  // continuation after a first mismatch became impossible
    int transitionsExecuted = 0;    // replay transitions actually executed
    BattleContext finalState;       // replay end state (valid iff hasFinalState)
    bool hasFinalState = false;
};

// Deterministic replay: install the hypothesis on a copy of the anchor and
// walk the recorded boundaries with semantic action remap and bare
// Action::execute (exact live transition semantics). fallbackRng is used only
// by applyHiddenState's stale-particle draw fallback.
S3RejuvenationReplayResult replayRejuvenationHistory(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng);

// Same exact replay and equality checks, but executes each recorded Action's
// original raw bits instead of semantic remapping. This is an oracle-only
// discriminator for replay correctness, not a proposal or gameplay path.
S3RejuvenationReplayResult replayRejuvenationHistoryRaw(
    const S3RejuvenationHistory &history,
    const HiddenBattleState &particle,
    std::mt19937_64 &fallbackRng);

// Shadow probe (pure telemetry; never mutates live state). Called by the
// fair-S3 boundary sites after filterRealTransition returns; no-ops unless
// g_s3RejuvShadow and g_s3RejuvShadowFile are set and
// filterStats.compatible <= g_s3RejuvTrigger. Appends one CSV row per trigger.
void runRejuvenationShadowProbe(const S3RejuvenationHistory &history,
                                const RealBeliefFilterStats &filterStats,
                                const Belief &belief,
                                const BattleContext &bc,
                                int decisionIdx);

// Conditional AI_RNG decision-sensitivity diagnostic. This is a nested,
// fixed-hidden Searcher3 evaluation and never changes the live search.
void runAiSensitivityShadow(const S3RejuvenationHistory &history,
                            const RealBeliefFilterStats &filterStats,
                            const Belief &belief,
                            const BattleContext &bc,
                            int decisionIdx,
                            const std::vector<HiddenBattleState> &acceptedAiStates);

// Flags (env STS_S3_REJUV_*; parsed in apps/one_combat.cpp; off by default).
extern bool g_s3RejuvShadow;
extern int g_s3RejuvTrigger;
extern int g_s3RejuvProposals;
extern std::string g_s3RejuvShadowFile;
extern bool g_s3AiSensitivityShadow;
extern std::string g_s3AiSensitivityFile;
extern int g_s3AiSensitivityRootsPerSeed;
extern int g_s3AiSensitivityAlternatives;
extern int g_s3AiSensitivitySims;

} // namespace sts::search
#endif // STS_LIGHTSPEED_S3REJUVENATIONPROBE_H
