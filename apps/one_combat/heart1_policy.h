// heart1 out-of-combat policy adapter (opt-in, STS_OOC_HEART1).
//
// Native port of daniel-ziegler/sts_lightspeed @84ab3ea silverbot (MIT): the
// observation/choice encoding (silverbot/playouts.py construct_choice,
// bindings/bindings-util.cpp getNNRepresentation, silverbot/network.py
// collate_fn/map_dag_features) and the transformer forward pass
// (silverbot/network.py NN, dim 256, 4 layers, 8 heads, value head). Weights
// come from heart1.pt via tools/heart1/export_heart1_weights.py; they are not
// vendored. Unset, nothing here is loaded or called.
#ifndef STS_ONE_COMBAT_HEART1_POLICY_H
#define STS_ONE_COMBAT_HEART1_POLICY_H

#include <array>
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

// take_free_rewards: gold always, relics unless a key shares the screen.
// Returns the number of actions executed.
int takeFreeRewards(sts::GameContext &);

struct Output {
    std::vector<float> logits;  // one per choice token, token order
    float value = 0;
};

class Net {
public:
    bool load(const std::string &path, std::string *error);
    Output forward(const Record &) const;
    const std::string &path() const { return path_; }

    struct Linear { int out = 0, in = 0; std::vector<float> w, b; };
    struct Embedding { int rows = 0; std::vector<float> w; };
    struct FixedVec { int features = 0; std::vector<float> invFreq; Linear proj; };
    struct Block {
        std::vector<float> norm1, norm2;
        Linear inProj, outProj, w1, w2, v;
    };

private:
    std::string path_;
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

// OOC MCTS hook (STS_OOC_MCTS_PRIOR=heart1).
// priorLogits: heart1's logit for each given primitive (a primitive behind
// several tokens keeps its best token); nullopt when silverbot has no encoding
// for the screen or a primitive has no token, so the caller keeps V4 there.
std::optional<std::vector<double>> priorLogits(const sts::GameContext &,
                                               const std::vector<sts::search::GameAction> &);

// STS_OOC_HEART1_CAPTURE=<out.jsonl> (with STS_OOC_HEART1, V4 tree prior): every
// STS_OOC_HEART1_CAPTURE_EVERY-th (default 8) multi-source V4 prior build writes one
// JSON line with the node's heart1 record, heart1 token logits/value and the V4
// source logits. Observation only: the search keeps V4's logits.
bool captureEnabled();
void captureNode(const sts::GameContext &, const std::vector<sts::search::GameAction> &sources,
                 const std::vector<double> &v4Logits);

// Diagnostics for the parity harness (tools/heart1/); neither uses a seed range.
// heart1score <weights> <records.jsonl> <out.jsonl>: native logits for records.
int scoreCommand(int argc, char **argv);
// heart1replay <weights> <asc> <seed> <plan.json> <out.jsonl>: replay one seed's
// out-of-combat action bits and write our record and logits where the plan asks.
int replayCommand(int argc, char **argv);

}  // namespace one_combat::heart1

#endif
