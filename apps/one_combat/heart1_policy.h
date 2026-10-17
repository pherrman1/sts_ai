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
};

// Mirror of flatten_dict(Choice.as_dict()) in silverbot: the raw record that
// collate_fn turns into tensors. JSON keys match the Python record exactly.
struct Record {
    std::vector<int> fixedObservation;  // 10 entries
    std::vector<int> deckCards, deckUpgrades;
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
    Output forward(const Record &, bool logitsOnly = false) const;
    const std::string &path() const { return path_; }
    int dim() const { return dim_; }
    int heads() const { return heads_; }
    int hidden() const { return hidden_; }
    int layers() const { return int(blocks_.size()); }
    bool trimMap() const { return trimMap_; }

    struct Linear { int out = 0, in = 0; std::vector<float> w, b; };
    struct Embedding { int rows = 0, dim = 0; std::vector<float> w; };
    struct FixedVec { int features = 0; std::vector<float> invFreq; Linear proj; };
    struct Block {
        std::vector<float> norm1, norm2;
        Linear inProj, outProj, w1, w2, v;
    };

private:
    Output forwardRecord(const Record &, bool logitsOnly) const;

    std::string path_;
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
// The mapping step of priorLogits, given the choice and its token logits:
// skip one card reward -> silverbot's skip token (bowl token with Singing
// Bowl); gold -> the node's best logit; a potion discard -> the node's lowest.
std::optional<std::vector<double>> mapPriorLogits(const Choice &, const std::vector<float> &logits,
                                                  bool singingBowl,
                                                  const std::vector<sts::search::GameAction> &,
                                                  std::map<std::string, std::uint64_t> *tally = nullptr);
// Throws std::runtime_error when mapPriorLogits breaks its rules (oocmctsselftest).
void priorMappingSelfTest();

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
