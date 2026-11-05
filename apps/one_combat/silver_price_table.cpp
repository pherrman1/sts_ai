#include "silver_price_table.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>
#include <stdexcept>

#include "constants/Cards.h"
#include "constants/MonsterEncounters.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "game/GameContext.h"
#include "sim/search/NativeSilverBackend.h"

namespace one_combat {

using namespace sts;

PriceState priceStateFromGame(const GameContext &gc) {
    PriceState s;
    s.hp = gc.curHp; s.maxHp = gc.maxHp; s.gold = gc.gold; s.potionCapacity = gc.potionCapacity;
    for (const auto &c : gc.deck.cards) {
        s.deck.push_back(std::string(cardNames[static_cast<int>(c.id)]) + (c.getUpgraded() ? "+" : ""));
        s.deckMisc.push_back(c.misc);
    }
    for (const auto &r : gc.relics.relics) {
        s.relics.emplace_back(relicEnumNames[static_cast<int>(r.id)]);
        s.relicData.push_back(r.data);
    }
    // make_variants.py keeps potion ids > 1 (not INVALID or EMPTY_POTION_SLOT), in slot order.
    for (int i = 0; i < gc.potionCapacity; ++i)
        if (static_cast<int>(gc.potions[i]) > 1) s.potions.emplace_back(potionEnumNames[static_cast<int>(gc.potions[i])]);
    return s;
}

PriceState priceStateFromJson(const nlohmann::json &j) {
    PriceState s;
    s.hp = j.at("hp").get<int>(); s.maxHp = j.at("maxHp").get<int>(); s.gold = j.value("gold", 0);
    s.potionCapacity = j.at("potionCapacity").get<int>();
    s.potions = j.at("potions").get<std::vector<std::string>>();
    s.deck = j.at("deck").get<std::vector<std::string>>();
    s.relics = j.at("relics").get<std::vector<std::string>>();
    // As act4replay: card misc and relic counters are 0 unless the line gives them.
    s.deckMisc = j.contains("deckMisc") ? j.at("deckMisc").get<std::vector<int>>() : std::vector<int>(s.deck.size(), 0);
    s.relicData = j.contains("relicData") ? j.at("relicData").get<std::vector<int>>()
                                          : std::vector<int>(s.relics.size(), 0);
    if (s.deckMisc.size() != s.deck.size() || s.relicData.size() != s.relics.size())
        throw std::runtime_error("price state: deckMisc / relicData must match deck / relics");
    return s;
}

const std::vector<std::string> &PriceFeatures::counterRelics() {
    static const std::vector<std::string> names = {"GIRYA", "HAPPY_FLOWER", "INCENSE_BURNER", "INK_BOTTLE",
                                                   "LIZARD_TAIL", "NUNCHAKU", "OMAMORI", "PEN_NIB", "SUNDIAL"};
    return names;
}

bool PriceFeatures::init(const std::vector<std::string> &names) {
    names_ = names; ix_.clear(); counterCols_.clear();
    for (int i = 0; i < static_cast<int>(names.size()); ++i)
        if (!ix_.emplace(names[i], i).second) return false;
    const auto col = [&](const char *n) { const auto it = ix_.find(n); return it == ix_.end() ? -1 : it->second; };
    hp_ = col("hp"); maxHp_ = col("maxHp"); hpFrac_ = col("hp_frac"); potions_ = col("potions");
    capacity_ = col("capacity"); emptySlots_ = col("empty_slots"); deckSize_ = col("deck_size");
    upgrades_ = col("upgrades"); leaf_ = col("leaf"); searingMisc_ = col("searing_misc");
    for (const auto &r : counterRelics()) counterCols_.push_back(col(("ctr:" + r).c_str()));
    for (const int c : {hp_, maxHp_, hpFrac_, potions_, capacity_, emptySlots_, deckSize_, upgrades_, leaf_, searingMisc_})
        if (c < 0) return false;
    return std::find(counterCols_.begin(), counterCols_.end(), -1) == counterCols_.end();
}

double PriceFeatures::leaf(const PriceState &s) {
    const int m = s.maxHp;
    double v = s.hp + 2 * m + 11 * static_cast<int>(s.potions.size());
    const auto has = [](const std::vector<std::string> &v, const char *n) { return std::find(v.begin(), v.end(), n) != v.end(); };
    if (!has(s.relics, "MARK_OF_THE_BLOOM")) {
        if (has(s.potions, "FAIRY_POTION")) v += m * (has(s.relics, "SACRED_BARK") ? 0.6 : 0.3);
        const auto it = std::find(s.relics.begin(), s.relics.end(), "LIZARD_TAIL");
        if (it != s.relics.end() && s.relicData[it - s.relics.begin()] == 1) v += 0.5 * m;   // unused only
    }
    return v;
}

std::vector<float> PriceFeatures::row(const PriceState &s, int *unknown) const {
    std::vector<float> x(names_.size(), 0.0f);
    int missing = 0;
    const auto add = [&](const std::string &n, float v) {
        const auto it = ix_.find(n);
        if (it == ix_.end()) { ++missing; return; }
        x[it->second] += v;
    };
    x[hp_] = static_cast<float>(s.hp); x[maxHp_] = static_cast<float>(s.maxHp);
    x[hpFrac_] = static_cast<float>(static_cast<double>(s.hp) / std::max(s.maxHp, 1));
    x[potions_] = static_cast<float>(s.potions.size()); x[capacity_] = static_cast<float>(s.potionCapacity);
    x[emptySlots_] = static_cast<float>(s.potionCapacity - static_cast<int>(s.potions.size()));
    x[deckSize_] = static_cast<float>(s.deck.size());
    x[upgrades_] = static_cast<float>(std::count_if(s.deck.begin(), s.deck.end(),
        [](const std::string &c) { return !c.empty() && c.back() == '+'; }));
    x[leaf_] = static_cast<float>(leaf(s));
    for (const auto &p : s.potions) add("pot:" + p, 1);
    for (const int c : counterCols_) x[c] = -1;
    const auto &counters = counterRelics();
    for (std::size_t i = 0; i < s.relics.size(); ++i) {
        const auto it = ix_.find("relic:" + s.relics[i]);
        if (it == ix_.end()) ++missing; else x[it->second] = 1;
        const auto c = std::find(counters.begin(), counters.end(), s.relics[i]);
        if (c != counters.end()) x[counterCols_[c - counters.begin()]] = static_cast<float>(s.relicData[i]);
    }
    for (std::size_t i = 0; i < s.deck.size(); ++i) {
        std::string b = s.deck[i];
        const bool up = !b.empty() && b.back() == '+';
        while (!b.empty() && b.back() == '+') b.pop_back();   // Python's rstrip('+')
        add("card:" + b, 1);
        if (up) add("up:" + b, 1);
        if (b == "Searing Blow") x[searingMisc_] += static_cast<float>(s.deckMisc[i]);
    }
    if (unknown) *unknown += missing;
    return x;
}

bool PriceModel::load(const std::string &trees, const std::string &vocab) {
    treesPath = trees; vocabPath = vocab;
    std::ifstream f(vocab);
    if (!f) { std::cerr << "price table: cannot open " << vocab << "\n"; return false; }
    const auto meta = nlohmann::json::parse(f);
    const auto names = meta.at("names").get<std::vector<std::string>>();
    if (!features.init(names)) { std::cerr << "price table: vocabulary lacks a fixed column: " << vocab << "\n"; return false; }
    std::unordered_map<std::string, int> idx;
    for (int i = 0; i < static_cast<int>(names.size()); ++i) idx["f" + std::to_string(i)] = i;
    if (!net.load(trees, idx, "PriceTableModel") || !net.logistic) return false;
    treesSha256 = meta.value("trees_sha256", std::string());
    return true;
}

double PriceModel::predict(const PriceState &s, int *unknown) const {
    return net.predict(features.row(s, unknown));
}

namespace {

// Relic counters a fight can change (BattleContext::updateRelicsOnExit) with make_variants.py's value range.
const std::vector<std::pair<RelicId, int>> &pricedCounters() {
    static const std::vector<std::pair<RelicId, int>> v = {
        {RelicId::HAPPY_FLOWER, 3}, {RelicId::INCENSE_BURNER, 6}, {RelicId::INK_BOTTLE, 10},
        {RelicId::LIZARD_TAIL, 2}, {RelicId::NUNCHAKU, 10}, {RelicId::OMAMORI, 3}, {RelicId::PEN_NIB, 10},
        {RelicId::SUNDIAL, 3}};
    return v;
}

int potionId(const std::string &name) {
    for (int i = 2; i < static_cast<int>(std::size(potionEnumNames)); ++i)
        if (name == potionEnumNames[i]) return i;
    return -1;
}

}  // namespace

std::shared_ptr<const search::SilverPriceTable> buildPriceTable(const PriceModel &model, const PriceState &root,
                                                                int *rowsOut) {
    int rows = 0, unknown = 0;
    const auto V = [&](const PriceState &s) { ++rows; return model.predict(s, &unknown); };
    const int m = std::max(root.maxHp, 1);
    const double v0 = V(root);
    // HP knots: 1 HP, 10/25/50/75/100% of max HP and the fight-start HP.
    std::vector<int> knots = {1, m, std::clamp(root.hp, 1, m)};
    for (const double f : {0.10, 0.25, 0.50, 0.75}) knots.push_back(std::clamp(static_cast<int>(std::lround(f * m)), 1, m));
    std::sort(knots.begin(), knots.end()); knots.erase(std::unique(knots.begin(), knots.end()), knots.end());
    std::vector<double> vk;
    for (const int h : knots) { PriceState s = root; s.hp = h; vk.push_back(h == root.hp ? v0 : V(s)); }
    auto &stats = priceTableLeafStats();
    const std::size_t n = knots.size();
    double scale = 0;
    if (n > 1) {
        const std::size_t j = std::find(knots.begin(), knots.end(), std::clamp(root.hp, 1, m)) - knots.begin();
        double sum = 0; int parts = 0;
        if (j > 0) { sum += (vk[j] - vk[j - 1]) / (knots[j] - knots[j - 1]); ++parts; }
        if (j + 1 < n) { sum += (vk[j + 1] - vk[j]) / (knots[j + 1] - knots[j]); ++parts; }
        const double local = sum / parts;
        const double chord = (vk[n - 1] - vk[0]) / (knots[n - 1] - knots[0]);
        scale = std::max(local, 0.25 * chord);   // floor: a flat stretch at the root would make every price explode
    }
    if (!(scale > 1e-9)) {
        if (rowsOut) *rowsOut = rows;
        ++stats.flat; stats.rows += rows; stats.unknownNames += unknown;
        return nullptr;
    }
    auto t = std::make_shared<search::SilverPriceTable>();
    t->hpUnit = scale; t->rootWinValue = v0 / scale;
    t->hpKnots = knots;
    for (std::size_t i = 0; i < n; ++i) t->hpValue.push_back(1 + (vk[i] - vk[0]) / scale);
    t->unpricedPotion = search::SilverEvalWeights{}.potionWeight;
    for (std::size_t i = 0; i < root.potions.size(); ++i) {
        const int id = potionId(root.potions[i]);
        if (id < 0 || id >= search::kSilverPotionTypeCount || t->potionPriced[id]) continue;
        PriceState s = root; s.potions.erase(s.potions.begin() + static_cast<std::ptrdiff_t>(i));
        t->potionPrice[id] = (v0 - V(s)) / scale; t->potionPriced[id] = true;
    }
    {
        double sum = 0; int parts = 0;
        PriceState up = root; up.maxHp += 5;
        sum += (V(up) - v0) / 5; ++parts;
        if (root.hp <= root.maxHp - 5) { PriceState dn = root; dn.maxHp -= 5; sum += (v0 - V(dn)) / 5; ++parts; }
        t->maxHpPrice = sum / parts / scale;
    }
    if (root.gold >= 50) { PriceState s = root; s.gold -= 50; t->goldPrice = (v0 - V(s)) / 50 / scale; }
    for (const auto &[relic, range] : pricedCounters()) {
        const std::string name = relicEnumNames[static_cast<int>(relic)];
        const auto it = std::find(root.relics.begin(), root.relics.end(), name);
        if (it == root.relics.end()) continue;
        const auto k = static_cast<std::size_t>(it - root.relics.begin());
        search::SilverPriceTable::Counter c;
        c.relic = relic; c.rootValue = root.relicData[k];
        if (c.rootValue < 0) continue;   // no defined start value: left unpriced
        // A start value outside make_variants.py's range widens it, so the unchanged counter prices 0.
        for (int v = 0; v < std::max(range, c.rootValue + 1); ++v) {
            if (v == c.rootValue) { c.price.push_back(0); continue; }
            PriceState s = root; s.relicData[k] = v;
            c.price.push_back((V(s) - v0) / scale);
        }
        t->counters.push_back(std::move(c));
    }
    if (rowsOut) *rowsOut = rows;
    ++stats.tables; stats.rows += rows; stats.unknownNames += unknown;
    return t;
}

PriceTableLeafStats &priceTableLeafStats() {
    static PriceTableLeafStats stats;
    return stats;
}

namespace {

struct LeafConfig {
    std::string spec;
    PriceModel model;
    std::set<MonsterEncounter> fights;
};
std::unique_ptr<LeafConfig> g_config;

std::int64_t threadNanos() {
    timespec ts{};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return static_cast<std::int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}

}  // namespace

bool installSilverPriceTableLeafFromEnv() {
    const char *raw = std::getenv("STS_SILVER_PRICE_TABLE_LEAF");
    if (!raw || !*raw || std::string(raw) == "0") {
        g_config.reset();
        search::setNativeSilverPriceTableBuilder({});
        return false;
    }
    auto cfg = std::make_unique<LeafConfig>();
    cfg->spec = raw;
    const auto colon = cfg->spec.find(':');
    const std::string model = cfg->spec.substr(0, colon);
    std::string fights = colon == std::string::npos ? "" : cfg->spec.substr(colon + 1);
    std::string trees, vocab;
    if (model == "a746") {
        trees = "models/candidates/silver_price_a746.trees";
        vocab = "models/candidates/silver_price_a746.vocab.json";
        if (fights.empty()) fights = "SHIELD_AND_SPEAR";   // a Heart-entry model: the fight before the Heart
    } else if (model.size() > 6 && model.compare(model.size() - 6, 6, ".trees") == 0) {
        trees = model;
        vocab = model.substr(0, model.size() - 6) + ".vocab.json";
        if (fights.empty()) throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF: a model file needs :<ENCOUNTER,...>");
    } else {
        throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF must be a746[:ENCOUNTERS] or <model>.trees:ENCOUNTERS (0 = off)");
    }
    std::stringstream ss(fights);
    for (std::string tok; std::getline(ss, tok, ',');) {
        int id = -1;
        for (int i = 1; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
            if (tok == monsterEncounterEnumNames[i]) id = i;
        if (id < 0) throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF: unknown encounter " + tok);
        cfg->fights.insert(static_cast<MonsterEncounter>(id));
    }
    if (cfg->fights.empty()) throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF: no fights");
    cfg->model.name = model;
    if (!cfg->model.load(trees, vocab))
        throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF: cannot load " + trees + " / " + vocab);
    std::cerr << "[silver] research leaf: price table " << model << " at " << fights << "\n";
    g_config = std::move(cfg);
    const LeafConfig *config = g_config.get();
    search::setNativeSilverPriceTableBuilder(
        [config](const GameContext &gc, const BattleContext &bc) -> std::shared_ptr<const search::SilverPriceTable> {
            if (!config->fights.count(bc.encounter)) return nullptr;
            const auto t0 = threadNanos();
            auto table = buildPriceTable(config->model, priceStateFromGame(gc));
            priceTableLeafStats().buildNanos += threadNanos() - t0;
            return table;
        });
    return true;
}

nlohmann::json silverPriceTableLeafSpecification() {
    if (!g_config) return nullptr;
    nlohmann::json fights = nlohmann::json::array();
    for (const auto e : g_config->fights) fights.push_back(monsterEncounterEnumNames[static_cast<int>(e)]);
    return {{"spec", g_config->spec}, {"model", g_config->model.name}, {"trees", g_config->model.treesPath},
            {"vocab", g_config->model.vocabPath}, {"fights", fights}};
}

}  // namespace one_combat
