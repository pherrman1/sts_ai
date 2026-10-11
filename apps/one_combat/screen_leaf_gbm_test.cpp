// Screen GBM features: an offered Circlet must not abort the leaf, and known
// relic ids keep their trained one-hot slots (audit 2026-10-11 finding 4).
#include "screen_leaf_gbm.h"
#include "constants/Relics.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace {
using Json = nlohmann::json;
int failures = 0;
void require(bool ok, const char *message) {
    if (!ok) { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
float feature(const std::vector<float> &f, const std::string &name) {
    const auto &names = one_combat::screenGbmFeatureNames();
    return f.at(std::find(names.begin(), names.end(), name) - names.begin());
}
float relicSum(const std::vector<float> &f) {
    float sum = 0;
    for (int i = 0; i < 178; ++i) sum += feature(f, "sf_relic" + std::to_string(i));
    return sum;
}
Json bossRelics(std::vector<int> ids) { return {{"screen", "boss_relic"}, {"relics", ids}}; }
}

int main() {
    using one_combat::screenGbmFeatures;
    require(one_combat::screenGbmFeatureNames().size() == 18 + 30 + 372 + 178 + 44,
            "trained feature schema is unchanged");
    const auto known = screenGbmFeatures(bossRelics({0, 5, 177}), {}, 0);
    require(feature(known, "sf_relic0") == 1 && feature(known, "sf_relic5") == 1
            && feature(known, "sf_relic177") == 1 && relicSum(known) == 3
            && feature(known, "sf_n_offers") == 3, "known relics keep their one-hot slots");
    try {
        const int circlet = int(sts::RelicId::CIRCLET), red = int(sts::RelicId::RED_CIRCLET);
        const auto oov = screenGbmFeatures(bossRelics({0, circlet, red}), {}, 0);
        require(feature(oov, "sf_relic0") == 1 && relicSum(oov) == 1 && feature(oov, "sf_n_offers") == 3,
                "Circlets count as offers without a relic slot");
        const Json shop = {{"screen", "shop"}, {"removeCost", 75}, {"cards", Json::array()},
                           {"potionSlots", Json::array()},
                           {"relics", {{{"id", circlet}, {"price", 150}}, {{"id", 3}, {"price", 200}}}}};
        const auto shopF = screenGbmFeatures(shop, {}, 160);
        require(feature(shopF, "sf_relic3") == 1 && relicSum(shopF) == 1 && feature(shopF, "sf_n_offers") == 2
                && feature(shopF, "sf_affordable") == 1, "a shop Circlet keeps its price and offer count");
    } catch (const std::exception &e) {
        std::cerr << "FAIL: Circlet offer threw: " << e.what() << '\n'; ++failures;
    }
    bool invalidThrows = false;
    try { screenGbmFeatures(bossRelics({int(sts::RelicId::INVALID)}), {}, 0); }
    catch (const std::runtime_error &) { invalidThrows = true; }
    require(invalidThrows, "RelicId::INVALID is still rejected");
    if (failures) return 1;
    std::cout << "screen gbm features: PASS\n";
    return 0;
}
