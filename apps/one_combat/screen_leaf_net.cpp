#include "screen_leaf_net.h"
#include "screen_leaf_import.h"
#include "screen_leaf_s0.h"
#include "run_features.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace one_combat {
namespace {
using Json = nlohmann::json;
void need(bool ok, const char *message) { if (!ok) throw std::runtime_error(std::string("screen leaf net: ") + message); }

// Order of tensors in the exported file (tools/export_screen_leaf_native_379.py).
enum T { MEAN, SCALE, IDS, KINDS, ROLES, EFFECTS, SOURCES, TARGETS, EVENTS, SCREENS, CARD_W, CARD_B, GROUP_W,
         GROUP_B, ENTITY_W, ENTITY_B, ACTION_W, ACTION_B, TRUNK0_W, TRUNK0_B, TRUNK3_W, TRUNK3_B, HEAD_W, HEAD_B,
         TENSOR_COUNT };
const std::array<const char *, TENSOR_COUNT> NAMES{"mean", "scale", "ids.weight", "kinds.weight", "roles.weight",
    "effects.weight", "sources.weight", "targets.weight", "events.weight", "screens.weight", "card_encoder.0.weight",
    "card_encoder.0.bias", "group_encoder.0.weight", "group_encoder.0.bias", "entity_encoder.0.weight",
    "entity_encoder.0.bias", "action_encoder.0.weight", "action_encoder.0.bias", "trunk.0.weight", "trunk.0.bias",
    "trunk.3.weight", "trunk.3.bias", "head.weight", "head.bias"};
const std::array<const char *, 5> SCREEN_NAMES{"boss_relic", "rest", "shop", "treasure", "rewards"};
const std::map<std::string, int> KIND{{"none", 0}, {"card", 1}, {"relic", 2}, {"potion", 3}, {"gold", 4}, {"key", 5}};
enum Role { SHOP_CARD, SHOP_RELIC, SHOP_POTION, BUYABLE_RELIC, HELD_POTION, BOSS_RELIC };

using Row = std::array<float, 14>;
using Card = std::array<float, 3>;
struct Option { Row row; std::vector<Card> group; };
using Entity = std::array<float, 8>;

Card cardText(const std::string &text) {
    static const std::regex r(R"((\d+),(-?\d+),([01]))");
    std::smatch m; need(std::regex_match(text, m, r), "invalid semantic card");
    return {std::stof(m[1]), std::stof(m[2]), std::stof(m[3])};
}
std::array<float, 4> entityText(const std::string &text) {
    if (text == "none") return {0, 0, 0, 0};
    const auto comma = text.find(',');
    need(comma != std::string::npos, "invalid semantic entity");
    const auto kind = text.substr(0, comma), rest = text.substr(comma + 1);
    need(KIND.count(kind), "unknown semantic entity");
    if (kind == "card") { const auto c = cardText(rest); return {1, c[0], c[1], c[2]}; }
    const float value = std::stof(rest);
    if (kind == "gold") return {4, 0, value, 0};
    return {float(KIND.at(kind)), value, 0, 0};
}
Option parseOption(const std::string &key) {
    static const std::regex head(R"(ooc:v1:effect=(\d+):source=(\d+):(.*))");
    static const std::regex card(R"(card=(\d+):misc=(-?\d+):upgraded=([01]):bottle=(-?\d+):occurrence=(\d+))");
    static const std::regex transaction(R"(transaction:event=(\d+):option=(-?\d+):cost=(\d+):(card=.*))");
    static const std::regex shop(R"(shop=(.*):price=(-?\d+):occurrence=(\d+))");
    static const std::regex relic(R"(relic=(\d+):occurrence=(\d+))");
    static const std::regex reward(
        R"(reward=(.*):group=\[(.*)\]:groupOccurrence=(\d+):occurrence=(\d+):sapphirePaired=([01]))");
    std::smatch m; need(std::regex_match(key, m, head), "semantic key schema mismatch");
    const float effect = std::stof(m[1]), source = std::stof(m[2]);
    const std::string tail = m[3];
    Option o{{effect, source, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, -1}, {}};
    auto &row = o.row;
    if (tail == "none") return o;
    if (std::regex_match(tail, m, card)) {
        row[2] = 1; row[3] = 1; row[4] = std::stof(m[1]); row[5] = std::stof(m[2]); row[6] = std::stof(m[3]);
        row[7] = std::stof(m[4]); row[8] = std::stof(m[5]);
        return o;
    }
    if (std::regex_match(tail, m, transaction)) {
        auto inner = parseOption("ooc:v1:effect=" + std::to_string(int(effect)) + ":source="
                                 + std::to_string(int(source)) + ":" + std::string(m[4]));
        inner.row[2] = 5; inner.row[12] = std::stof(m[1]); inner.row[13] = std::stof(m[2]);
        inner.row[9] = std::stof(m[3]);
        return inner;
    }
    if (std::regex_match(tail, m, shop)) {
        const auto e = entityText(m[1]);
        row[2] = 2; std::copy(e.begin(), e.end(), row.begin() + 3);
        row[9] = std::stof(m[2]); row[8] = std::stof(m[3]);
        return o;
    }
    if (std::regex_match(tail, m, relic)) {
        row[2] = 3; row[3] = 2; row[4] = std::stof(m[1]); row[8] = std::stof(m[2]);
        return o;
    }
    if (std::regex_match(tail, m, reward)) {
        const auto e = entityText(m[1]);
        row[2] = 4; std::copy(e.begin(), e.end(), row.begin() + 3);
        const std::string group = m[2];
        if (!group.empty()) {
            need(group.back() == ';', "noncanonical reward group");
            std::stringstream ss(group.substr(0, group.size() - 1)); std::string item;
            while (std::getline(ss, item, ';')) o.group.push_back(cardText(item));
            std::sort(o.group.begin(), o.group.end());
        }
        need(o.group.size() <= 4, "reward group exceeds native capacity");
        row[10] = std::stof(m[3]); row[8] = std::stof(m[4]); row[11] = std::stof(m[5]);
        return o;
    }
    throw std::runtime_error("screen leaf net: unsupported public option target " + key);
}

float gelu(float x) { return 0.5f * x * (1.0f + std::erf(x / std::sqrt(2.0f))); }

void linear(const ScreenLeafNet::Tensor &w, const ScreenLeafNet::Tensor &b, const float *x, float *y, bool act) {
    const int out = w.shape[0], in = w.shape[1];
    for (int o = 0; o < out; ++o) {
        float s = b.v[o];
        const float *row = &w.v[std::size_t(o) * in];
        for (int i = 0; i < in; ++i) s += row[i] * x[i];
        y[o] = act ? gelu(s) : s;
    }
}
const float *embed(const ScreenLeafNet::Tensor &t, float index) {
    const int i = int(index);
    need(i >= 0 && i < t.shape[0], "embedding index out of range");
    return &t.v[std::size_t(i) * t.shape[1]];
}
// Masked mean of encoded vectors plus count/100 (ScreenModel.pool).
std::array<float, 17> pool(const std::vector<std::array<float, 16>> &values) {
    std::array<float, 17> out{};
    for (const auto &v : values) for (int i = 0; i < 16; ++i) out[i] += v[i];
    const float n = float(values.size());
    for (int i = 0; i < 16; ++i) out[i] /= std::max(n, 1.0f);
    out[16] = n / 100.0f;
    return out;
}
std::array<float, 16> encodeGroup(const ScreenLeafNet::Seed &s, const std::vector<Card> &cards) {
    std::vector<std::array<float, 16>> encoded;
    for (const auto &c : cards) {
        float x[10]; const float *id = embed(s.t[IDS], c[0]);
        std::copy(id, id + 8, x); x[8] = c[1] / 100.0f; x[9] = c[2];
        std::array<float, 16> y; linear(s.t[CARD_W], s.t[CARD_B], x, y.data(), true); encoded.push_back(y);
    }
    const auto pooled = pool(encoded);
    std::array<float, 16> y; linear(s.t[GROUP_W], s.t[GROUP_B], pooled.data(), y.data(), true);
    return y;
}

struct Encoded {
    int screen = -1;
    std::array<float, 5> context{};
    std::vector<Entity> entities;
    std::vector<Option> actions;
};

int integerField(const Json &v) { need(v.is_number_integer(), "invalid public integer"); return v.get<int>(); }

std::vector<std::string> canonicalShopOptions(const std::vector<float> &base, const Json &c,
                                              std::vector<std::string> keys) {
    // BASE_INDEX gold 4, potionCount 10, potionCapacity 11, r64 (Sozu) 322.
    const float gold = base[4]; const int count = int(base[10]), capacity = int(base[11]);
    const bool sozu = base[322] != 0;
    need(capacity == integerField(c.at("ownedPotionCapacity")), "shop/base potion capacity differs");
    bool affordable = false;
    for (const auto &p : c.at("potionSlots")) {
        const int price = integerField(p.at("price"));
        affordable = affordable || (price >= 0 && price <= gold);
    }
    std::vector<std::string> expected;
    if (capacity && count >= capacity && !sozu && affordable) {
        std::map<int, int> occurrences;
        for (const auto &v : c.at("ownedPotions")) {
            const int potion = integerField(v);
            if (potion == 0 || potion == 1) continue;
            const int occurrence = occurrences[potion]++;
            expected.push_back("ooc:v1:effect=29:source=3:reward=potion," + std::to_string(potion)
                + ":group=[]:groupOccurrence=0:occurrence=" + std::to_string(occurrence) + ":sapphirePaired=0");
        }
    }
    std::vector<std::string> provided;
    for (const auto &k : keys) if (parseOption(k).row[0] == 29) provided.push_back(k);
    auto sortedExpected = expected; std::sort(sortedExpected.begin(), sortedExpected.end());
    std::sort(provided.begin(), provided.end());
    need(provided.empty() || provided == sortedExpected, "partial/invalid provided shop discard set");
    for (const auto &k : expected)
        if (std::find(keys.begin(), keys.end(), k) == keys.end()) keys.push_back(k);
    return keys;
}

Encoded encode(const std::vector<float> &base, const Json &c, std::vector<std::string> keys) {
    Encoded e;
    const std::string screen = c.at("screen");
    for (int i = 0; i < 4; ++i) if (screen == SCREEN_NAMES[i]) e.screen = i;
    need(e.screen >= 0, "screen outside native replacement families");
    auto add = [&](int role, int kind, float id = 0, float misc = 0, float upgrade = 0, float price = 0,
                   float slot = -1, float present = 1) {
        need(id >= 0 && id < 512, "entity id out of range");
        e.entities.push_back({float(role), float(kind), id, misc, upgrade, price, slot, present});
    };
    if (screen == "boss_relic") {
        for (const auto &v : c.at("relics")) add(BOSS_RELIC, 2, float(integerField(v)));
    } else if (screen == "treasure") {
        e.context[4] = float(integerField(c.at("chestSize")));
    } else if (screen == "shop") {
        e.context[0] = float(integerField(c.at("removeCost")));
        e.context[1] = float(integerField(c.at("ownedPotionCapacity")));
        for (const auto &v : c.at("ownedPotions")) add(HELD_POTION, 3, float(integerField(v)));
        const std::array<std::tuple<const char *, int, int>, 3> fields{
            std::tuple{"cards", SHOP_CARD, 1}, std::tuple{"relics", SHOP_RELIC, 2},
            std::tuple{"potionSlots", SHOP_POTION, 3}};
        for (const auto &[field, role, kind] : fields) {
            for (const auto &item : c.at(field)) {
                const float slot = float(integerField(item.at("slot")));
                const float price = float(integerField(item.at("price")));
                if (price < 0) add(role, kind, 0, 0, 0, price, slot, 0);
                else if (kind == 1) {
                    const auto &card = item.at("card");
                    add(role, kind, float(integerField(card.at("id"))), float(integerField(card.at("misc"))),
                        card.at("upgraded").get<bool>() ? 1.0f : 0.0f, price, slot);
                } else add(role, kind, float(integerField(item.at("id"))), 0, 0, price, slot);
            }
        }
        for (const auto &item : c.at("policyBuyableRelics"))
            add(BUYABLE_RELIC, 2, float(integerField(item.at("id"))), 0, 0, float(integerField(item.at("price"))));
        keys = canonicalShopOptions(base, c, keys);
    }
    for (const auto &k : keys) e.actions.push_back(parseOption(k));
    std::sort(e.entities.begin(), e.entities.end());
    std::sort(e.actions.begin(), e.actions.end(),
              [](const Option &a, const Option &b) { return std::tie(a.row, a.group) < std::tie(b.row, b.group); });
    return e;
}

double forward(const ScreenLeafNet::Seed &s, const std::vector<float> &base, const Encoded &e, int head) {
    std::vector<float> features; features.reserve(521);
    for (int i = 0; i < 461; ++i) features.push_back((base[i] - s.t[MEAN].v[i]) / s.t[SCALE].v[i]);
    const float *screen = embed(s.t[SCREENS], float(e.screen));
    features.insert(features.end(), screen, screen + 4);
    const std::array<float, 5> contextScale{100, 5, 1, 1, 4};
    for (int i = 0; i < 5; ++i) features.push_back(e.context[i] / contextScale[i]);
    std::vector<std::array<float, 16>> entities, actions, groups;
    for (const auto &en : e.entities) {
        float x[21]; const float *r = embed(s.t[ROLES], en[0]), *k = embed(s.t[KINDS], en[1]), *id = embed(s.t[IDS], en[2]);
        std::copy(r, r + 4, x); std::copy(k, k + 4, x + 4); std::copy(id, id + 8, x + 8);
        const std::array<float, 5> scale{100, 1, 100, 10, 1};
        for (int i = 0; i < 5; ++i) x[16 + i] = en[3 + i] / scale[i];
        std::array<float, 16> y; linear(s.t[ENTITY_W], s.t[ENTITY_B], x, y.data(), true); entities.push_back(y);
    }
    for (const auto &a : e.actions) {
        const auto &row = a.row; float x[50]; int at = 0;
        auto put = [&](const float *v, int n) { std::copy(v, v + n, x + at); at += n; };
        put(embed(s.t[EFFECTS], row[0]), 4); put(embed(s.t[SOURCES], row[1]), 3); put(embed(s.t[TARGETS], row[2]), 3);
        put(embed(s.t[KINDS], row[3]), 4); put(embed(s.t[IDS], row[4]), 8);
        const std::array<float, 7> scale{100, 1, 3, 10, 100, 10, 1};
        for (int i = 0; i < 7; ++i) x[at++] = row[5 + i] / scale[i];
        put(embed(s.t[EVENTS], row[12]), 4); x[at++] = row[13] / 10.0f;
        const auto g = encodeGroup(s, a.group); put(g.data(), 16);
        need(at == 50, "action width");
        std::array<float, 16> y; linear(s.t[ACTION_W], s.t[ACTION_B], x, y.data(), true); actions.push_back(y);
    }
    for (const auto *set : {&entities, &actions, &groups}) {
        const auto p = pool(*set); features.insert(features.end(), p.begin(), p.end());
    }
    need(features.size() == 521, "trunk width");
    float h1[64], h2[32], out[8];
    linear(s.t[TRUNK0_W], s.t[TRUNK0_B], features.data(), h1, true);
    linear(s.t[TRUNK3_W], s.t[TRUNK3_B], h1, h2, true);
    linear(s.t[HEAD_W], s.t[HEAD_B], h2, out, false);
    return 1.0 / (1.0 + std::exp(-double(out[head])));
}
}

ScreenLeafNet::ScreenLeafNet(const std::string &path) {
    std::ifstream in(path); need(bool(in), "cannot open model");
    std::string line, word;
    need(std::getline(in, line) && line == "screen-leaf-native-v1", "bad header");
    need(std::getline(in, line) && line == "arm S1", "only the S1 arm is supported natively");
    need(bool(std::getline(in, line)), "missing mask");
    { std::istringstream ss(line); ss >> word; need(word == "mask", "missing mask"); while (ss >> word) mask_.push_back(word); }
    need(mask_ == std::vector<std::string>{"boss_relic", "rest", "shop", "treasure"}, "unexpected replacement mask");
    need(bool(std::getline(in, line)), "missing indices");
    { std::istringstream ss(line); ss >> word; need(word == "indices", "missing indices"); int i; while (ss >> i) indices_.push_back(i); }
    need(indices_.size() == 461, "base index width");
    while (std::getline(in, line) && line != "end") {
        std::istringstream ss(line); ss >> word;
        need(word == "seed", "expected seed block");
        Seed seed;
        for (int t = 0; t < TENSOR_COUNT; ++t) {
            need(bool(std::getline(in, line)), "truncated model");
            std::istringstream ts(line); std::string name; int ndim; ts >> name >> ndim;
            need(name == NAMES[t], "tensor order mismatch");
            Tensor tensor; std::size_t size = 1;
            for (int d = 0; d < ndim; ++d) { int n; ts >> n; tensor.shape.push_back(n); size *= n; }
            tensor.v.resize(size);
            for (auto &x : tensor.v) { double v; ts >> v; x = float(v); }
            need(!ts.fail(), "tensor values");
            seed.t.push_back(std::move(tensor));
        }
        seeds_.push_back(std::move(seed));
    }
    need(seeds_.size() == 3 && line == "end", "expected three seeds");
}
bool ScreenLeafNet::covers(const std::string &screen) const {
    return std::find(mask_.begin(), mask_.end(), screen) != mask_.end();
}
double ScreenLeafNet::predict(const std::vector<float> &base, const Json &screenContents,
                              const std::vector<std::string> &optionKeys) const {
    need(base.size() == 461, "base461 width");
    const auto e = encode(base, screenContents, optionKeys);
    double sum = 0;
    for (const auto &seed : seeds_) sum += forward(seed, base, e, e.screen);
    return sum / double(seeds_.size());
}
double ScreenLeafNet::predictFromRich(const std::vector<float> &base1017, const Json &screenContents,
                                      const std::vector<std::string> &optionKeys) const {
    need(base1017.size() == 1017, "rich width");
    std::vector<float> base; base.reserve(461);
    for (int i : indices_) base.push_back(base1017[i]);
    return predict(base, screenContents, optionKeys);
}

int screenLeafNetParity(const std::string &model, const std::string &input) {
    ScreenLeafNet net(model);
    std::ifstream in(input); need(bool(in), "cannot open parity input");
    std::string line; double maxError = 0, sum = 0; std::vector<double> errors;
    std::map<std::string, double> worst;
    while (std::getline(in, line)) {
        const auto row = Json::parse(line);
        const auto base = row.at("base").get<std::vector<float>>();
        const double native = net.predict(base, row.at("screenContents"),
                                          row.at("candidateKeys").get<std::vector<std::string>>());
        const double error = std::abs(native - row.at("python").get<double>());
        errors.push_back(error); sum += error; maxError = std::max(maxError, error);
        auto &w = worst[row.at("screenContents").at("screen").get<std::string>()]; w = std::max(w, error);
    }
    std::sort(errors.begin(), errors.end());
    auto q = [&](double p) { return errors[std::min(errors.size() - 1, std::size_t(p * errors.size()))]; };
    std::cout << Json{{"rows", errors.size()}, {"maxAbsError", maxError}, {"meanAbsError", sum / errors.size()},
                      {"p95", q(.95)}, {"p99", q(.99)}, {"worstByScreen", worst},
                      {"pass", !errors.empty() && maxError < 1e-5}}.dump() << "\n";
    return !errors.empty() && maxError < 1e-5 ? 0 : 1;
}

// Live-input parity: the adapter builds inputs from GameContext (richRow and
// the public contract); compare against the recorded DECISION row inputs.
int screenLeafNetLiveParity(const std::string &model, const std::string &input, unsigned limit) {
    ScreenLeafNet net(model);
    std::ifstream in(input); need(bool(in), "cannot open snapshot input");
    std::string line; unsigned rows = 0; double maxError = 0;
    while (rows < limit && std::getline(in, line)) {
        auto row = Json::parse(line);
        const std::string screen = row.at("screenContents").at("screen");
        if (!net.covers(screen)) continue;
        auto state = screen_leaf::importEnvelope(row);
        const auto contract = screenLeafPublicContract(state.gc);
        auto parse = [](const std::string &text) {
            std::vector<float> v; std::stringstream ss(text); std::string item;
            while (std::getline(ss, item, ',')) v.push_back(std::stof(item));
            return v;
        };
        const double live = net.predictFromRich(parse(richRow(state.gc, state.path)), contract.at("screenContents"),
            contract.at("candidateKeys").get<std::vector<std::string>>());
        const double recorded = net.predictFromRich(parse(row.at("features").get<std::string>()),
            row.at("screenContents"), row.at("candidateKeys").get<std::vector<std::string>>());
        maxError = std::max(maxError, std::abs(live - recorded)); ++rows;
    }
    std::cout << Json{{"rows", rows}, {"maxAbsError", maxError}, {"pass", rows > 0 && maxError < 1e-6}}.dump() << "\n";
    return rows > 0 && maxError < 1e-6 ? 0 : 1;
}
}

