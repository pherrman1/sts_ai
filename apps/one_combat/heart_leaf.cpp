#include "heart_leaf.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include <openssl/evp.h>

namespace one_combat {

const std::vector<std::string> &heartLeafExtraNames() {
    static const std::vector<std::string> names{"x2bMargin", "hlFloorsToBoss", "hlAct4", "hlKeys",
        "hlHpFrac", "hlDaggerDamage", "hlSearingLevel", "hlBurningEliteAhead", "hlBurningEliteDist",
        "hlBlueOpen", "hlRedOpen", "hlGreenOpen", "hlKeysClosed"};
    return names;
}

const std::unordered_map<std::string, int> &heartLeafIdxMap() {
    static const auto map = [] {
        auto m = richIdxMap();
        const int offset = int(m.size());
        const auto &extra = heartLeafExtraNames();
        for (std::size_t i = 0; i < extra.size(); ++i) m[extra[i]] = offset + int(i);
        return m;
    }();
    return map;
}

int heartLeafBossFloor(int act) { return act <= 1 ? 16 : act == 2 ? 33 : act == 3 ? 50 : 56; }

namespace {
// Rows ahead to this act's burning elite along the map edges from the current
// node (0 when standing on it), or -1 when it is not reachable.
int burningEliteDistance(const sts::GameContext &gc) {
    if (gc.map == nullptr || gc.act >= 4) return -1;
    const sts::Map &map = *gc.map;
    const int ex = map.burningEliteX, ey = map.burningEliteY;
    if (ex < 0 || ey < 0 || ex >= 7 || ey >= 15) return -1;
    const int base = std::max(gc.curMapNodeY, 0);
    if (gc.curMapNodeY >= 0 && gc.curMapNodeX == ex && gc.curMapNodeY == ey) return 0;
    std::array<bool, 7> reach{};
    int row;
    if (gc.curMapNodeY < 0) {
        row = 0;
        for (const sts::MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        row = gc.curMapNodeY + 1;
        const sts::MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    for (int y = row; y <= std::min(ey, 14); ++y) {
        if (y == ey) return reach[ex] ? y - base : -1;
        std::array<bool, 7> next{};
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const sts::MapNode &n = map.getNode(x, y);
            for (int i = 0; i < n.edgeCount; ++i) next[n.edges[i]] = true;
        }
        reach = next;
    }
    return -1;
}
} // namespace

void appendHeartLeafExtras(std::vector<float> &values, const sts::GameContext &gc, double x2bMargin) {
    int dagger = 0, searing = 0;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const sts::Card &c = gc.deck.cards[i];
        if (c.getId() == sts::CardId::RITUAL_DAGGER) dagger += c.misc;
        if (c.getId() == sts::CardId::SEARING_BLOW) searing = std::max(searing, c.getUpgraded());
    }
    values.push_back(float(x2bMargin));
    values.push_back(float(heartLeafBossFloor(gc.act) - gc.floorNum));
    values.push_back(gc.act >= 4 ? 1.0f : 0.0f);
    values.push_back(float(int(gc.blueKey) + int(gc.greenKey) + int(gc.redKey)));
    values.push_back(gc.maxHp > 0 ? float(gc.curHp) / float(gc.maxHp) : 0.0f);
    values.push_back(float(dagger));
    values.push_back(float(searing));
    // Keys: a missing key is open while a later act or a reachable room of
    // its kind this act remains (chest for Sapphire, campfire for Ruby,
    // burning elite for Emerald). A closed key forfeits Act 4.
    const int elite = burningEliteDistance(gc);
    const FwdMap fm = forwardMapFeatures(gc);
    const bool later = gc.act < 3;
    const bool blueOpen = !gc.blueKey && gc.act < 4 && (later || fm.cTreasure > 0);
    const bool redOpen = !gc.redKey && gc.act < 4 && (later || fm.cRest > 0);
    const bool greenOpen = !gc.greenKey && gc.act < 4 && (later || elite >= 0);
    values.push_back(elite >= 0 && !gc.greenKey ? 1.0f : 0.0f);
    values.push_back(elite >= 0 && !gc.greenKey ? float(elite) : 99.0f);
    values.push_back(blueOpen ? 1.0f : 0.0f);
    values.push_back(redOpen ? 1.0f : 0.0f);
    values.push_back(greenOpen ? 1.0f : 0.0f);
    values.push_back(float((!gc.blueKey && !blueOpen) + (!gc.redKey && !redOpen) + (!gc.greenKey && !greenOpen)));
}

std::vector<float> heartLeafFeatureVec(const sts::GameContext &gc, const PathHistory &path, double x2bMargin) {
    auto values = richFeatureVec(gc, path);
    appendHeartLeafExtras(values, gc, x2bMargin);
    return values;
}

std::string fileSha256Hex(const std::string &path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("heart leaf: cannot open " + path);
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(EVP_MD_CTX_new(), EVP_MD_CTX_free);
    if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1)
        throw std::runtime_error("heart leaf: SHA256 init failed");
    char buffer[1 << 16];
    while (file.read(buffer, sizeof buffer) || file.gcount())
        if (EVP_DigestUpdate(context.get(), buffer, std::size_t(file.gcount())) != 1)
            throw std::runtime_error("heart leaf: SHA256 update failed");
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned length = 0;
    if (EVP_DigestFinal_ex(context.get(), digest, &length) != 1) throw std::runtime_error("heart leaf: SHA256 final failed");
    std::ostringstream hex;
    for (unsigned i = 0; i < length; ++i) hex << std::hex << std::setw(2) << std::setfill('0') << int(digest[i]);
    return hex.str();
}

HeartLeafModel::HeartLeafModel(const std::string &manifestPath) : path_(manifestPath) {
    std::ifstream in(manifestPath);
    if (!in) throw std::runtime_error("heart leaf: cannot open manifest " + manifestPath);
    const auto manifest = nlohmann::json::parse(in);
    hasCritic_ = manifest.at("featureSchema") == kHeartLeafCriticFeatureSchema;
    if (manifest.at("schema") != "heart-leaf-v1" || (!hasCritic_ && manifest.at("featureSchema") != kHeartLeafFeatureSchema))
        throw std::runtime_error("heart leaf: unknown manifest or feature schema");
    if (manifest.at("anchorSha256") != kHeartLeafAnchorSha256 || fileSha256Hex(kHeartLeafAnchorPath) != kHeartLeafAnchorSha256)
        throw std::runtime_error("heart leaf: anchor is not the pinned public X2-B");
    const auto residual = (std::filesystem::path(manifestPath).parent_path()
        / manifest.at("residual").get<std::string>()).string();
    if (fileSha256Hex(residual) != manifest.at("residualSha256").get<std::string>())
        throw std::runtime_error("heart leaf: residual hash mismatch");
    slope_ = manifest.at("anchorSlope").get<double>();
    act4Offset_ = manifest.value("act4Offset", 0.0);
    if (!std::isfinite(slope_) || !std::isfinite(act4Offset_)) throw std::runtime_error("heart leaf: invalid anchor slope or offset");
    if (!anchor_.load(kHeartLeafAnchorPath, richIdxMap(), "HeartLeaf anchor") || !anchor_.logistic)
        throw std::runtime_error("heart leaf: cannot load anchor");
    auto residualIdx = heartLeafIdxMap();
    if (hasCritic_) {
        const auto critic = (std::filesystem::path(manifestPath).parent_path()
            / manifest.at("critic").get<std::string>()).string();
        if (fileSha256Hex(critic) != manifest.at("criticSha256").get<std::string>())
            throw std::runtime_error("heart leaf: critic hash mismatch");
        if (!critic_.load(critic, heartLeafIdxMap(), "HeartLeaf critic") || critic_.logistic)
            throw std::runtime_error("heart leaf: critic must be a margin (logistic 0) tree model");
        residualIdx.emplace("hlCritic", int(residualIdx.size()));
    }
    if (!residual_.load(residual, residualIdx, "HeartLeaf residual") || residual_.logistic)
        throw std::runtime_error("heart leaf: residual must be a margin (logistic 0) tree model");
    sha_ = fileSha256Hex(manifestPath);
}

double HeartLeafModel::value(const sts::GameContext &gc, const PathHistory &path) const {
    auto raw = richFeatureVec(gc, path);
    appendHeartLeafExtras(raw, gc, anchor_.margin(raw));
    return valueFromFeatures(raw);
}

double HeartLeafModel::valueFromFeatures(const std::vector<float> &raw) const {
    if (raw.size() != heartLeafIdxMap().size()) throw std::runtime_error("heart leaf: feature width");
    static const int anchorColumn = heartLeafIdxMap().at("x2bMargin");
    const double anchor = raw[anchorColumn];
    double residual;
    if (hasCritic_) {
        // The fit used XGBoost's float32 critic predictions as the column, so
        // the critic is summed the same way (a double sum flips residual splits).
        auto withCritic = raw;
        withCritic.push_back(critic_.marginFloat32(raw));
        residual = residual_.predict(withCritic);
    } else {
        residual = residual_.predict(raw);
    }
    static const int act4Column = heartLeafIdxMap().at("hlAct4");
    const double margin = slope_ * anchor + residual + (raw[act4Column] != 0 ? act4Offset_ : 0.0);
    const double value = 1.0 / (1.0 + std::exp(-margin));
    if (!std::isfinite(value)) throw std::runtime_error("heart leaf: nonfinite value");
    return std::clamp(value, 0.0, 1.0);
}
} // namespace one_combat
