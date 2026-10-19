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
    bool operator==(const FixedChoice &) const = default;
};

// Mirror of flatten_dict(Choice.as_dict()) in silverbot: the raw record that
// collate_fn turns into tensors. JSON keys match the Python record exactly.
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
bool buildChoice(const sts::GameContext &, Choice &, std::string *reason = nullptr);

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

// take_free_rewards: gold always, relics unless a key shares the screen.
// Returns the number of actions executed.
int takeFreeRewards(sts::GameContext &);

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
    std::vector<Block> blocks_;
    std::vector<float> finalNorm_, valueNorm_;
    Linear choiceLogits_, valueHead_;
};

bool enabled();
const Net &net();

// The run-driver hook: one real out-of-combat step by heart1 (greedy, the
// temperature-0 eval policy). False leaves the step to the ordinary chain.
bool policyStep(sts::GameContext &);

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
