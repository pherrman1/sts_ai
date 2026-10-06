#include "screen_leaf_gbm.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace one_combat {
namespace {
using Json = nlohmann::json;
const std::vector<std::string> SCREENS{"boss_relic", "rest", "shop", "treasure", "rewards", "event", "selector"};
constexpr int CARDS = 372, RELICS = 178, POTIONS = 44;
std::vector<std::string> makeNames() {
    std::vector<std::string> n{"sf_screen", "sf_nopt", "sf_remove_cost", "sf_price_min", "sf_price_mean",
        "sf_affordable", "sf_n_offers", "sf_reward_gold", "sf_n_card_groups", "sf_emerald", "sf_sapphire",
        "sf_chest", "sf_event", "sf_neow", "sf_selector_type", "sf_required", "sf_completed", "sf_n_selector_cards"};
    for (int e = 0; e < 30; ++e) n.push_back("sf_eff" + std::to_string(e));
    for (int i = 0; i < CARDS; ++i) n.push_back("sf_card" + std::to_string(i));
    for (int i = 0; i < RELICS; ++i) n.push_back("sf_relic" + std::to_string(i));
    for (int i = 0; i < POTIONS; ++i) n.push_back("sf_potion" + std::to_string(i));
    return n;
}
enum { SCREEN, NOPT, REMOVE_COST, PRICE_MIN, PRICE_MEAN, AFFORDABLE, N_OFFERS, REWARD_GOLD, N_CARD_GROUPS, EMERALD,
       SAPPHIRE, CHEST, EVENT, NEOW, SELECTOR_TYPE, REQUIRED, COMPLETED, N_SELECTOR_CARDS, EFF0 };
constexpr int CARD0 = EFF0 + 30, RELIC0 = CARD0 + CARDS, POTION0 = RELIC0 + RELICS;
int at(int base, int count, int id) {
    if (id < 0 || id >= count) throw std::runtime_error("screen gbm: entity id out of range");
    return base + id;
}
}

const std::vector<std::string> &screenGbmFeatureNames() { static const auto names = makeNames(); return names; }

std::vector<float> screenGbmFeatures(const Json &c, const std::vector<std::string> &keys, float gold) {
    std::vector<float> f(screenGbmFeatureNames().size(), 0.0f);
    const std::string screen = c.at("screen");
    const auto it = std::find(SCREENS.begin(), SCREENS.end(), screen);
    if (it == SCREENS.end()) throw std::runtime_error("screen gbm: unknown screen " + screen);
    f[SCREEN] = float(it - SCREENS.begin());
    f[NOPT] = float(keys.size());
    for (const auto &k : keys) {
        const std::string prefix = "ooc:v1:effect=";
        if (k.compare(0, prefix.size(), prefix) != 0) throw std::runtime_error("screen gbm: option key schema");
        f[at(EFF0, 30, std::stoi(k.substr(prefix.size())))] += 1;
    }
    std::vector<int> prices;
    auto offer = [&](int base, int count, int id) { f[at(base, count, id)] += 1; f[N_OFFERS] += 1; };
    if (screen == "shop") {
        f[REMOVE_COST] = c.at("removeCost").get<float>();
        for (const auto &[field, base, count] : {std::tuple{"cards", CARD0, CARDS}, std::tuple{"relics", RELIC0, RELICS},
                                                std::tuple{"potionSlots", POTION0, POTIONS}}) {
            for (const auto &item : c.at(field)) {
                const int price = item.at("price").get<int>();
                if (price < 0) continue;
                offer(base, count, base == CARD0 ? item.at("card").at("id").get<int>() : item.at("id").get<int>());
                prices.push_back(price);
            }
        }
    } else if (screen == "boss_relic") {
        for (const auto &r : c.at("relics")) offer(RELIC0, RELICS, r.get<int>());
    } else if (screen == "rewards") {
        int goldSum = 0; for (const auto &g : c.at("gold")) goldSum += g.get<int>();
        f[REWARD_GOLD] = float(goldSum);
        f[N_CARD_GROUPS] = float(c.at("cardRewards").size());
        f[EMERALD] = c.at("emeraldKey").get<bool>() ? 1.0f : 0.0f;
        f[SAPPHIRE] = c.at("sapphireKey").get<bool>() ? 1.0f : 0.0f;
        for (const auto &g : c.at("cardRewards")) for (const auto &card : g.at("cards")) offer(CARD0, CARDS, card.at("id").get<int>());
        for (const auto &r : c.at("relics")) offer(RELIC0, RELICS, r.get<int>());
        for (const auto &p : c.at("potions")) offer(POTION0, POTIONS, p.get<int>());
    } else if (screen == "treasure") {
        f[CHEST] = c.at("chestSize").get<float>();
    } else if (screen == "event") {
        f[EVENT] = c.at("eventId").get<float>();
        f[NEOW] = c.contains("neowOffers") ? float(c.at("neowOffers").size()) : 0.0f;
    } else if (screen == "selector") {
        f[SELECTOR_TYPE] = c.at("selectorTypeId").get<float>();
        f[REQUIRED] = c.at("requiredPicks").get<float>();
        f[COMPLETED] = c.at("completedPicks").get<float>();
        f[N_SELECTOR_CARDS] = float(c.at("cards").size());
        for (const auto &item : c.at("cards")) offer(CARD0, CARDS, item.at("card").at("id").get<int>());
    }
    if (!prices.empty()) {
        // float32 accumulation order matches numpy only for exact integer sums.
        double sum = 0; int affordable = 0;
        for (int p : prices) { sum += p; affordable += p <= gold; }
        f[PRICE_MIN] = float(*std::min_element(prices.begin(), prices.end()));
        f[PRICE_MEAN] = float(sum / prices.size());
        f[AFFORDABLE] = float(affordable);
    }
    return f;
}

ScreenLeafGbm::ScreenLeafGbm(const std::string &path, std::unordered_map<std::string, int> featureIdx, int screenOffset,
                             const std::string &anchorPath)
        : offset_(screenOffset) {
    if (!anchorPath.empty() && (!anchor_.load(anchorPath, featureIdx, "ScreenLeafGbm anchor") || !anchor_.logistic))
        throw std::runtime_error("screen gbm: cannot load X2-B anchor " + anchorPath);
    const auto &names = screenGbmFeatureNames();
    for (std::size_t i = 0; i < names.size(); ++i) featureIdx[names[i]] = screenOffset + int(i);
    if (!net_.load(path, featureIdx, "ScreenLeafGbm") || net_.logistic)
        throw std::runtime_error("screen gbm: cannot load margin model " + path);
}

double ScreenLeafGbm::anchor(const std::vector<float> &raw) const {
    if (!anchor_.ok) throw std::runtime_error("screen gbm: no pinned anchor");
    const double value = anchor_.predict(raw);
    if (!std::isfinite(value) || value < 0 || value > 1) throw std::runtime_error("screen gbm: invalid anchor value");
    return value;
}

int screenLeafGbmParity(const std::string &model, const std::string &input) {
    // Parity rows carry the 461 selected run features then the screen features.
    std::ifstream predictor("/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a3-final1024-x2b-finalist-20261003-49c28d80/tune/X2/predictor.json");
    if (!predictor) throw std::runtime_error("screen gbm parity: cannot read X2 predictor feature order");
    const auto order = Json::parse(predictor).at("feature_names").get<std::vector<std::string>>();
    std::unordered_map<std::string, int> idx;
    for (std::size_t i = 0; i < order.size(); ++i) idx[order[i]] = int(i);
    ScreenLeafGbm gbm(model, idx, int(order.size()));
    std::ifstream in(input); std::string line; double maxError = 0; int rows = 0;
    while (std::getline(in, line)) {
        const auto row = Json::parse(line);
        const auto x = row.at("x").get<std::vector<float>>();
        maxError = std::max(maxError, std::abs(gbm.residual(x) - row.at("margin").get<double>())); ++rows;
    }
    std::cout << Json{{"rows", rows}, {"maxAbsMarginError", maxError}, {"pass", rows > 0 && maxError < 1e-4}}.dump() << "\n";
    return rows > 0 && maxError < 1e-4 ? 0 : 1;
}
}
