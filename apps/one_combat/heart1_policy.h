// heart1 out-of-combat policy adapter (opt-in, STS_OOC_HEART1).
//
// Native port of daniel-ziegler/sts_lightspeed @84ab3ea silverbot (MIT): the
// observation/choice encoding (silverbot/playouts.py construct_choice,
// bindings/bindings-util.cpp getNNRepresentation, silverbot/network.py
// collate_fn/map_dag_features) and the transformer forward pass
// (silverbot/network.py NN with a value head; heart1 is dim 256, 4 layers, 8
// heads, and smaller distilled students load from the same format). Weights
// come from heart1.pt via tools/heart1/export_heart1_weights.py; they are not
// vendored. Unset, nothing here is loaded or called.
#ifndef STS_ONE_COMBAT_HEART1_POLICY_H
#define STS_ONE_COMBAT_HEART1_POLICY_H

#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "game/GameContext.h"
#include "sim/search/GameAction.h"

namespace one_combat::heart1 {

// One offered fixed action (silverbot FixedAction plus its optional fields).
struct FixedChoice {
    int action = 0;
    int gold = 0;
    int card = 0;     // CardId::INVALID
    int relic = 180;  // RelicId::INVALID
    int info = 0;     // EventFixedInfo::NONE
    // PPO full-coverage extension (ChoiceOptions::fullCoverage): the held potion a
    // discard token names, added through the potion table. -1 (every heart1 token)
    // adds nothing, so records and outputs of the original choice space are unchanged.
    int potion = -1;
    bool operator==(const FixedChoice &) const = default;
};

// Fixed-action ids of the PPO full-coverage tokens (after silverbot's last id,
// FA_OPEN_CHEST = 165). A net whose fixed-action table is shorter reads them as
// zero rows (the zero-initialised extension), so heart1 and student_sel score them.
inline constexpr int kFaDiscardPotion = 166;  // potion = the held potion; one per discardable slot
inline constexpr int kFaMatchUnseen = 167;    // Match and Keep: flip an unseen slot (card = the face-up card, if any)
inline constexpr int kFaMatchSeen = 168;      // flip a seen slot (card = its card)
inline constexpr int kFaMatchPair = 169;      // flip the seen twin of the face-up card (card = that card)
inline constexpr int kFaEventOption0 = 170;   // event option without a silverbot mapping: + min(option, 7),
                                              // gold = the event id
inline constexpr int kFaCount = 178;          // fixed-action ids 0..177

// Choice construction options. The defaults are the trained heart1 choice space.
struct ChoiceOptions {
    // PPO (STS_OOC_HEART1_PPO): add tokens for every real choice heart1's space
    // lacks: potion discards on reward and shop screens whose potion offer is blocked
    // by full slots, Match and Keep slots, and unmapped event options.
    bool fullCoverage = false;
    // Drop actions the heart key rules mask (heartKeyActionAllowed). False lets the
    // net see every legal action, as when it learns the keys itself.
    bool keyMask = true;
};

// Mirror of flatten_dict(Choice.as_dict()) in silverbot: the raw record that
// collate_fn turns into tensors. JSON keys match the Python record exactly.
inline constexpr int kRunCounterCount = 2;
inline constexpr int kMaxFoughtEncounters = 32;  // student_inputs.py MAX_FOUGHT

struct Record {
    std::vector<int> fixedObservation;  // 10 entries
    std::vector<int> deckCards, deckUpgrades;
    // Student input extension (not read by heart1 itself): card misc in deck order
    // (Ritual Dagger damage, Genetic Algorithm block) and the act; records from
    // before it have no misc (all 0) and act 0.
    std::vector<int> deckMisc;
    int act = 0;
    std::vector<int> relics, relicCounters;
    std::vector<int> potions;
    std::vector<int> mapXs, mapYs, mapRooms;
    std::vector<std::array<int, 3>> mapPathXs;
    int burningEliteX = -1, burningEliteY = -1;
    int mapX = -1, mapY = -1;
    std::vector<int> offeredCards, offeredUpgrades;
    std::vector<int> offeredRelics;
    std::vector<int> offeredPotions;
    std::vector<FixedChoice> fixedActions;
    std::vector<int> paths;
    int screenState = 0;
    int selectScreenType = 0;
    // Shared-encoder input extension v2 (not read by heart1, student C or student_sel;
    // only by nets with x2_* weights). Public run state the v1 record leaves out:
    // runCounters = kRunCounterCount entries (see encodeObservation), foughtEncounters =
    // the normal and elite encounters already fought this act (MonsterEncounter ids),
    // offerPrices = the shop price of each offered card, relic and potion token in
    // token order (empty outside shops). Records from before it carry none of them.
    std::vector<int> runCounters;
    std::vector<int> foughtEncounters;
    std::vector<int> offerPrices;

    bool operator==(const Record &) const = default;

    int choiceCount() const {
        return int(offeredCards.size() + offeredRelics.size() + offeredPotions.size()
                   + fixedActions.size() + paths.size());
    }
};

// A record plus the engine actions behind each choice token, in token order:
// cards, relics, potions, fixed, paths.
struct Choice {
    Record record;
    std::vector<sts::search::GameAction> actions;
};

nlohmann::json recordToJson(const Record &);
Record recordFromJson(const nlohmann::json &);

// construct_choice for our engine. False with a reason when silverbot has no
// encoding for the screen (it returns None there and defers to its agent).
bool buildChoice(const sts::GameContext &, Choice &, std::string *reason = nullptr,
                 const ChoiceOptions &options = {});

// Leaf-only public observation extension. It does not change trained heart1
// choice construction. Battle starts expose their current visible encounter;
// Match and Keep masks unseen board identities. Call only at OOC adapter
// boundaries before BattleContext construction, never for mid-combat states.
bool buildPublicLeafRecord(const sts::GameContext &, nlohmann::json &, std::string *reason = nullptr);

// STS_OOC_HEART1_WING_BOOTS_COUNTER (#638): true when records carry the Wing
// Boots charges as its relic counter. Throws on values other than unset/0/1.
bool wingBootsCounter();

// The non-record fields of one STS_OOC_HEART1_CAPTURE row (kind, act, floor,
// screen, select_type, deck_misc, wing_boots_counter).
nlohmann::json captureBase(const sts::GameContext &, const char *kind);

// take_free_rewards: gold always, relics unless a key shares the screen (or
// relics = false, the PPO mode where the net decides reward relics).
// Returns the number of actions executed.
int takeFreeRewards(sts::GameContext &, bool relics = true);

struct Output {
    std::vector<float> logits;  // one per choice token, token order
    float value = 0;
    std::vector<float> pooled;  // value-head input (mean of value-normed tokens)
};

class Net {
public:
    bool load(const std::string &path, std::string *error);
    // Map rows below the current floor are dropped first for a trim_map network.
    // logitsOnly: skip what only the value head needs (the last block's
    // observation rows); the logits are bit-identical, value/pooled stay empty.
    // memo: reuse this thread's output for an equal record from a recent call
    // (the forward is deterministic, so the output is the same); off for timing.
    Output forward(const Record &, bool logitsOnly = false, bool memo = true) const;
    const std::string &path() const { return path_; }
    int dim() const { return dim_; }
    int heads() const { return heads_; }
    int hidden() const { return hidden_; }
    int layers() const { return int(blocks_.size()); }
    bool trimMap() const { return trimMap_; }
    bool extraInputs() const { return extraInputs_; }
    bool extraInputsV2() const { return extraInputsV2_; }

    struct Linear { int out = 0, in = 0; std::vector<float> w, b; };
    struct Embedding { int rows = 0, dim = 0; std::vector<float> w; };
    // memoId: nonzero process-unique key of these weights for the projection memo.
    struct FixedVec { int features = 0; std::vector<float> invFreq; Linear proj; std::uint64_t memoId = 0; };
    struct Block {
        std::vector<float> norm1, norm2;
        Linear inProj, outProj, w1, w2, v;
        Linear inProjKV;  // inProj's key and value rows (derived at load)
    };

private:
    Output forwardRecord(const Record &, bool logitsOnly) const;

    std::string path_;
    std::uint64_t forwardId_ = 0;  // nonzero process-unique key of a load, for the output memo
    int dim_ = 0, heads_ = 0, hidden_ = 0;
    bool trimMap_ = false;
    Embedding card_, upgrade_, relic_, potion_;
    FixedVec fixedObs_;
    Embedding boss_, ascension_, keyRuby_, keyEmerald_, keySapphire_, screen_;
    Embedding mapRoom_, isCurrent_, reachable_, burning_;
    FixedVec pos_, pathXs_, rel_, agg_;
    Embedding obsPosition_;
    Embedding selectScreen_, fixedAction_, info_;
    FixedVec gold_, pathX_, cone_;
    Embedding pathRoom_, reachesBurn_;
    Embedding choicePosition_;
    // Optional student inputs (tools/heart1/student_inputs.py): x_deck_misc on deck
    // tokens, x_relic_counter on relic tokens, x_act on the fixed-observation token.
    bool extraInputs_ = false;
    FixedVec deckMisc_, relicCounter_;
    Embedding act_;
    // Optional v2 inputs (tools/heart1/student_inputs.py --v2): x2_run (run counters)
    // and x2_fought (sum over fought encounters) on the fixed-observation token,
    // x2_price on shop card/relic/potion choice tokens. Present iff x2_run is.
    bool extraInputsV2_ = false;
    FixedVec runCounters_, offerPrice_;
    Embedding fought_;
    std::vector<Block> blocks_;
    std::vector<float> finalNorm_, valueNorm_;
    Linear choiceLogits_, valueHead_;
};

bool enabled();
const Net &net();

// The run-driver hook: one real out-of-combat step by heart1 (greedy, the
// temperature-0 eval policy). False leaves the step to the ordinary chain.
bool policyStep(sts::GameContext &);

// ---------------------------------------------------------------- PPO (S0)
// STS_OOC_HEART1_PPO=1 (opt-in, needs STS_OOC_HEART1 and STS_OOC_MCTS=0): the net
// makes every out-of-combat decision except gold, which stays automatic. Choices use
// ChoiceOptions{fullCoverage, keyMask = false}; the heart key rule and the chain's
// rules do not run first (STS_OOC_HEART1_PPO_KEY_RULE=1 keeps heartKeyAction and the
// key mask as a comparison arm). Choices are sampled at STS_OOC_HEART1_TEMPERATURE
// (default 1; 0 = argmax, first maximum) with a counter-based RNG keyed by the run
// seed, STS_OOC_HEART1_SAMPLE_SALT (default 0) and the decision index, so a game is
// reproducible and never touches the game's RNG. STS_OOC_HEART1_PPO_TRAJ=<file>
// appends one JSON line per decision and one per game (schema "heart1-ppo-traj-v1").
bool ppoEnabled();
// STS_OOC_HEART1_PPO_KEY_RULE=1: heartKeyAction and the key mask stay on (comparison arm).
bool ppoKeyRule();
double ppoTemperature();

// Index sampled from softmax(logits / temperature) at uniform u in [0, 1);
// temperature 0 returns the argmax (first maximum). *logp: the log-probability
// of the returned index under softmax(logits / max(temperature, 1)) for
// temperature 0, else under the sampling distribution.
int sampleChoice(const std::vector<float> &logits, double temperature, double u, double *logp = nullptr);
// The counter-based uniform in [0, 1) of decision `index` of a run.
double sampleUniform(std::uint64_t runSeed, std::uint64_t salt, std::uint64_t index);

// One PPO decision at a real out-of-combat state. Returns the decision source
// ("heart1_ppo", "heart1_ppo_single", "auto_gold") or nullptr when the net has no
// choice here: a "fallback" line with the reason is logged and the caller falls back
// to the chain (STS_OOC_HEART1_PPO_STRICT=1 throws instead).
const char *ppoStep(sts::GameContext &, std::uint64_t decisionIndex);
// Per game: clear this thread's buffer; append the outcome line and flush the
// game's lines to STS_OOC_HEART1_PPO_TRAJ under a process-wide lock.
void ppoBeginGame(std::uint64_t seed);
void ppoEndGame(const sts::GameContext &, const nlohmann::json &outcome);
// Throws std::runtime_error when the sampler or the coverage tokens break their
// rules (heart1pposelftest).
void ppoSelfTest();
// Coverage tokens on fixture states (heart1_record_invariance.cpp).
void ppoCoverageSelfTest();

// STS_OOC_SIBLING_CAPTURE annotation of one tree leaf: {"value", "record"} (heart1's
// value head and its input record), or {"unsupported": reason}.
nlohmann::json leafAnnotation(const sts::GameContext &);

// OOC MCTS hook (STS_OOC_MCTS_PRIOR=heart1).
// priorLogits: heart1's logit for each given primitive (a primitive behind
// several tokens keeps its best token). Reward-screen primitives silverbot's
// choice space lacks map as in mapPriorLogits. nullopt when silverbot has no
// encoding for the screen or a primitive has no mapping, so the caller keeps
// V4 there. *tally counts "scored:SCREEN", "mapped:SCREEN:KIND" per mapped
// primitive and "fallback:SCREEN:KIND" per fallback.
std::optional<std::vector<double>> priorLogits(const sts::GameContext &,
                                               const std::vector<sts::search::GameAction> &,
                                               std::map<std::string, std::uint64_t> *tally = nullptr);
// Explicitly owned model for the standalone advisor; no process-global load.
std::optional<std::vector<double>> priorLogits(const Net &, const sts::GameContext &,
                                               const std::vector<sts::search::GameAction> &,
                                               std::map<std::string, std::uint64_t> *tally = nullptr);
// STS_OOC_HEART1_CAPTURE=<out.jsonl> (distillation data, observation only):
// every STS_OOC_HEART1_CAPTURE_EVERY-th (default 8) priorLogits call writes the
// node ("kind":"node"), and every STS_OOC_HEART1_CAPTURE_SELECT_EVERY-th (default 1)
// card select that a rest, shop removal, event or boss-relic source opens on a state
// copy is written ("kind":"select"). Rows carry the
// record, STS_OOC_HEART1_TEACHER's token logits/value (default: the serving net)
// and the serving net's logits ("serve"), plus act and deck card misc; repeated records are written once.
// The returned logits are unchanged.

// The mapping step of priorLogits, given the choice and its token logits:
// skip one card reward -> silverbot's skip token (bowl token with Singing
// Bowl); gold -> the node's best logit; a potion discard -> the node's lowest.
std::optional<std::vector<double>> mapPriorLogits(const Choice &, const std::vector<float> &logits,
                                                  bool singingBowl,
                                                  const std::vector<sts::search::GameAction> &,
                                                  std::map<std::string, std::uint64_t> *tally = nullptr);
// The token side of mapPriorLogits, for policy-target capture: per primitive,
// the choice-token indices it maps to (several when one primitive sits behind
// several tokens) and how: "token", "skip_card", "bowl", "gold" (no token; the
// prior takes the best logit), "discard_potion" (no token; the lowest logit) or
// "none" where mapPriorLogits falls back to V4.
struct TokenMapping {
    std::vector<int> tokens;
    std::string kind;
};
std::vector<TokenMapping> mapChoiceTokens(const Choice &, bool singingBowl,
                                          const std::vector<sts::search::GameAction> &);
// Throws std::runtime_error when mapPriorLogits breaks its rules (oocmctsselftest).
void priorMappingSelfTest();
// Private-state invariance of the public record on every supported screen (#506);
// throws on failure. Defined in heart1_record_invariance.cpp.
void publicRecordInvarianceSelfTest();
// Throws std::runtime_error when the FixedVec projection memo differs from the plain
// projection with two nets of different width on one thread (oocmctsselftest).
void fixedVecMemoSelfTest();
// Throws std::runtime_error when a vector projection kernel differs from the reference loop.
void linearSelfTest();

// Diagnostics for the parity harness (tools/heart1/); neither uses a seed range.
// heart1score <weights> <records.jsonl> <out.jsonl>: native logits for records.
int scoreCommand(int argc, char **argv);
// heart1logitscheck <weights> <records.jsonl> [reps]: logits-only parity and timing.
int logitsCheckCommand(int argc, char **argv);
// heart1replay <weights> <asc> <seed> <plan.json> <out.jsonl>: replay one seed's
// out-of-combat action bits and write our record and logits where the plan asks.
int replayCommand(int argc, char **argv);

}  // namespace one_combat::heart1

#endif
