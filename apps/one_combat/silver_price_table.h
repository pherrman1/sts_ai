#ifndef STS_ONE_COMBAT_SILVER_PRICE_TABLE_H
#define STS_ONE_COMBAT_SILVER_PRICE_TABLE_H

// Research-only Silver price-table leaf (STS_SILVER_PRICE_TABLE_LEAF=<model>[:<ENCOUNTER,...>][:anchor], default off;
// docs/knowledge-base/research/combat-search/silver-price-table-leaf.md). At the start of a selected fight the model scores about
// 20-40 perturbed copies of the fight-start state once; the differences become the fight's
// search::SilverPriceTable, so the search tree never calls the model.
//
// First model "a746": §746's all-feature Heart-entry GBM (model A), refit on all §731 + §745 labels
// (docs/experiments/evidence/silver_price_table_leaf_20261105/fit_export.py), used at Shield & Spear only.

#include <atomic>
#include <cstdint>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

#include "compact_tree.h"
#include "sim/search/SilverSearcher.h"

namespace sts { struct GameContext; }

namespace one_combat {

// The plain run state §732's features read (fit_value.py's state JSON): names as make_variants.py writes them
// (Cards.h cardNames with "+" when upgraded, Relics.h relicEnumNames, Potions.h potionEnumNames).
struct PriceState {
    int hp = 0, maxHp = 0, gold = 0, potionCapacity = 0;
    std::vector<std::string> potions, deck, relics;
    std::vector<int> deckMisc, relicData;
};
PriceState priceStateFromGame(const sts::GameContext &gc);
// fit_value.py's / act4replay's state JSON (gold, deckMisc and relicData optional, default 0).
PriceState priceStateFromJson(const nlohmann::json &j);

// fit_value.py's Feat.row on a fixed vocabulary (the model's column names). Names outside the vocabulary
// (a card, relic or potion never seen in training) add nothing; Python would raise instead.
class PriceFeatures {
public:
    // False when a fixed column (hp, ..., searing_misc, every ctr:<relic>) is missing.
    bool init(const std::vector<std::string> &names);
    std::vector<float> row(const PriceState &s, int *unknown = nullptr) const;
    std::size_t size() const { return names_.size(); }
    const std::vector<std::string> &names() const { return names_; }
    // §732's Silver S&S leaf L (fit_value.py leaf()).
    static double leaf(const PriceState &s);
    // fit_value.py COUNTERS: relics whose counter is a feature (ctr:<relic>, -1 when not held).
    static const std::vector<std::string> &counterRelics();
private:
    std::vector<std::string> names_;
    std::unordered_map<std::string, int> ix_;
    int hp_ = -1, maxHp_ = -1, hpFrac_ = -1, potions_ = -1, capacity_ = -1, emptySlots_ = -1, deckSize_ = -1,
        upgrades_ = -1, leaf_ = -1, searingMisc_ = -1;
    std::vector<int> counterCols_;
};

struct PriceModel {
    std::string name, treesPath, vocabPath, treesSha256, vocabSha256;
    PriceFeatures features;
    CompactTreeNet net;
    // treesPath: CompactTreeNet text whose feature tokens f<i> index the vocab file's "names".
    bool load(const std::string &trees, const std::string &vocab);
    // Heart kill probability (logistic).
    double predict(const PriceState &s, int *unknown = nullptr) const;
};

// Fight-start prices (search::SilverPriceTable); null when the model's HP curve is flat (no scale).
// anchor: the fight's win bonus = V(root) / scale − the table's value of the start state, clamped to
// [winBonus, kAnchorCapFactor × winBonus] (SilverEvalWeights defaults).
inline constexpr double kAnchorCapFactor = 4;
std::shared_ptr<const sts::search::SilverPriceTable> buildPriceTable(const PriceModel &model, const PriceState &root,
                                                                     int *rows = nullptr, bool anchor = false);

struct PriceTableLeafStats {
    std::atomic<std::int64_t> tables{0}, flat{0}, rows{0}, unknownNames{0}, buildNanos{0}, anchorLow{0}, anchorHigh{0};
};
PriceTableLeafStats &priceTableLeafStats();

// Reads STS_SILVER_PRICE_TABLE_LEAF=<model>[:<ENC,...>][:anchor] (unset or 0 = off) after installNativeSilverBackend(); when on, loads the
// model and installs the builder. Throws on a bad spec or a model that does not load. Returns true when on.
bool installSilverPriceTableLeafFromEnv();
// The spec for manifests (model files with sha256, fights); null when off.
nlohmann::json silverPriceTableLeafSpecification();

}  // namespace one_combat

#endif  // STS_ONE_COMBAT_SILVER_PRICE_TABLE_H
