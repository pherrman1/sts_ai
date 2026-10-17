#include "one_combat/rollout_student.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>

namespace one_combat {
namespace {

constexpr int kDim = 64, kHeads = 4, kHidden = 128, kKinds = 11, kEntities = 1536, kAttrs = 8;
constexpr int kDense = 42, kMaxTokens = 384;

std::uint32_t readU32(std::ifstream &in) {
    std::uint32_t v = 0;
    in.read(reinterpret_cast<char *>(&v), 4);
    if (!in) throw std::runtime_error("rollout student: truncated weights");
    return v;
}

std::string readString(std::ifstream &in) {
    std::string s(readU32(in), '\0');
    in.read(s.data(), std::streamsize(s.size()));
    if (!in) throw std::runtime_error("rollout student: truncated weights");
    return s;
}

void layerNorm(const float *x, const std::vector<float> &w, const std::vector<float> &b, float *out) {
    double mean = 0, var = 0;
    for (int d = 0; d < kDim; ++d) mean += x[d];
    mean /= kDim;
    for (int d = 0; d < kDim; ++d) var += (x[d] - mean) * (x[d] - mean);
    const double inv = 1.0 / std::sqrt(var / kDim + 1e-5);
    for (int d = 0; d < kDim; ++d) out[d] = float((x[d] - mean) * inv) * w[d] + b[d];
}

// out[o] = b[o] + sum_i w[o * in + i] * x[i]
void linear(const std::vector<float> &w, const std::vector<float> &b, const float *x, int in, int outs, float *out) {
    for (int o = 0; o < outs; ++o) {
        const float *row = w.data() + std::size_t(o) * in;
        float s = b[o];
        for (int i = 0; i < in; ++i) s += row[i] * x[i];
        out[o] = s;
    }
}

}  // namespace

RolloutStudent::RolloutStudent(const std::string &path) : path_(path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("rollout student: cannot open " + path);
    char magic[8];
    in.read(magic, 8);
    if (!in || std::memcmp(magic, "STSRSD01", 8) != 0) throw std::runtime_error("rollout student: bad magic");
    std::map<std::string, std::pair<std::vector<std::uint32_t>, std::vector<float>>> tensors;
    for (std::uint32_t n = readU32(in), t = 0; t < n; ++t) {
        const auto name = readString(in);
        std::vector<std::uint32_t> dims(readU32(in));
        std::size_t count = 1;
        for (auto &d : dims) count *= (d = readU32(in));
        std::vector<float> data(count);
        in.read(reinterpret_cast<char *>(data.data()), std::streamsize(count * sizeof(float)));
        if (!in) throw std::runtime_error("rollout student: truncated tensor " + name);
        tensors[name] = {std::move(dims), std::move(data)};
    }
    const auto take = [&](const std::string &name, std::vector<std::uint32_t> dims) {
        const auto it = tensors.find(name);
        if (it == tensors.end() || it->second.first != dims)
            throw std::runtime_error("rollout student: missing or misshapen " + name);
        return std::move(it->second.second);
    };
    std::vector<std::string> vocabulary(readU32(in));
    for (auto &v : vocabulary) v = readString(in);
    inputs_ = int(vocabulary.size());
    denseCol_.assign(kDense, -1);
    countCol_.assign(kKinds * kEntities, -1);
    attrCol_.assign(kKinds * kEntities * kAttrs, -1);
    for (int col = 0; col < inputs_; ++col) {
        const auto &name = vocabulary[col];
        int a = 0, b = 0, c = 0;
        char tail[8] = {};
        if (std::sscanf(name.c_str(), "dense.%d%7s", &a, tail) == 1 && a >= 0 && a < kDense) denseCol_[a] = col;
        else if (std::sscanf(name.c_str(), "token.%d.%d.attr%d%7s", &a, &b, &c, tail) == 3
                 && a > 0 && a < kKinds && b >= 0 && b < kEntities && c >= 0 && c < kAttrs)
            attrCol_[(a * kEntities + b) * kAttrs + c] = col;
        else if (std::sscanf(name.c_str(), "token.%d.%d%7s", &a, &b, tail) == 2
                 && a > 0 && a < kKinds && b >= 0 && b < kEntities)
            countCol_[a * kEntities + b] = col;
        else throw std::runtime_error("rollout student: unknown vocabulary entry " + name);
    }
    const std::uint32_t D = kDim, H = kHidden;
    cls_ = take("cls", {1, 1, D});
    kind_ = take("kind.weight", {kKinds, D});
    entity_ = take("entity.weight", {kEntities, D});
    attrs_ = take("attrs.weight", {D, kAttrs});
    for (int i = 0; i < 2; ++i) {
        const std::string p = "encoder.layers." + std::to_string(i) + ".";
        Layer l;
        l.inW = take(p + "self_attn.in_proj_weight", {3 * D, D});
        l.inB = take(p + "self_attn.in_proj_bias", {3 * D});
        l.outW = take(p + "self_attn.out_proj.weight", {D, D});
        l.outB = take(p + "self_attn.out_proj.bias", {D});
        l.l1W = take(p + "linear1.weight", {H, D});
        l.l1B = take(p + "linear1.bias", {H});
        l.l2W = take(p + "linear2.weight", {D, H});
        l.l2B = take(p + "linear2.bias", {D});
        l.n1W = take(p + "norm1.weight", {D});
        l.n1B = take(p + "norm1.bias", {D});
        l.n2W = take(p + "norm2.weight", {D});
        l.n2B = take(p + "norm2.bias", {D});
        layers_.push_back(std::move(l));
    }
    w0_ = take("layers.0.weight", {H, std::uint32_t(inputs_) + D});
    b0_ = take("layers.0.bias", {H});
    w2_ = take("layers.2.weight", {H, H});
    b2_ = take("layers.2.bias", {H});
    w4_ = take("layers.4.weight", {1, H});
    b4_ = take("layers.4.bias", {1});
}

// tools/heart_record_encoder.py encode_record; false where it raises.
bool RolloutStudent::encode(const nlohmann::json &r, std::vector<std::pair<int, float>> &sparse,
                            std::vector<Token> &tokens) const {
    const auto len = [&](const char *k) { return r.at(k).size(); };
    if (len("obs.deck.cards") != len("obs.deck.upgrades") || len("obs.relics.relics") != len("obs.relics.relic_counters")
            || len("cards_offered.cards") != len("cards_offered.upgrades")
            || len("obs.map.xs") != len("obs.map.ys") || len("obs.map.xs") != len("obs.map.roomTypes")
            || len("obs.map.xs") != len("obs.map.pathXs"))
        return false;
    for (const auto &edges : r.at("obs.map.pathXs")) if (edges.size() != 3) return false;
    const auto &screenJson = r.at("screen_state");
    if (!screenJson.is_number_integer()) return false;
    const int screen = screenJson.get<int>();
    if (screen < 0 || screen >= 10) return false;
    const auto &fo = r.at("obs.fixed_observation");
    if (fo.size() != 10) return false;
    static constexpr double scales[10] = {200, 200, 1800, 60, 4, 5, 20, 1, 1, 1};
    double dense[kDense] = {};
    for (int i = 0; i < 10; ++i) dense[i] = fo[i].get<double>() / scales[i];
    dense[10] = r.at("obs.mapX").get<double>() / 7;
    dense[11] = r.at("obs.mapY").get<double>() / 15;
    dense[12] = r.at("obs.map.burningEliteX").get<double>() / 7;
    dense[13] = r.at("obs.map.burningEliteY").get<double>() / 15;
    dense[14 + screen] = 1;
    const int select = r.at("select_screen_type").get<int>();
    if (select >= 0 && select < 16) dense[24 + select] = 1;
    const bool memory = r.contains("leaf.matchSlots");
    dense[40] = memory;
    dense[41] = r.value("leaf.matchAttempts", 0.0) / 5;
    for (double v : dense) if (!std::isfinite(v)) return false;
    tokens.clear();
    const auto add = [&](int kind, int entity, std::initializer_list<double> attrs) {
        if (entity < 0 || entity >= kEntities) return false;
        if ((kind == 1 || kind == 4) && entity >= 512) return false;
        if ((kind == 2 || kind == 5) && (entity < 512 || entity >= 768)) return false;
        if ((kind == 3 || kind == 6) && (entity < 768 || entity >= 832)) return false;
        Token t{kind, entity, {}};
        int j = 0;
        for (double a : attrs) {
            if (!std::isfinite(a)) return false;
            t.attrs[j++] = float(std::clamp(a, -8.0, 8.0));
        }
        tokens.push_back(t);
        return true;
    };
    const auto &deck = r.at("obs.deck.cards"), &upgrades = r.at("obs.deck.upgrades");
    for (std::size_t i = 0; i < deck.size(); ++i)
        if (!add(1, deck[i].get<int>(), {upgrades[i].get<double>() / 10})) return false;
    const auto &relics = r.at("obs.relics.relics"), &counters = r.at("obs.relics.relic_counters");
    for (std::size_t i = 0; i < relics.size(); ++i)
        if (!add(2, 512 + relics[i].get<int>(), {counters[i].get<double>() / 100})) return false;
    for (const auto &p : r.at("obs.potions")) if (!add(3, 768 + p.get<int>(), {})) return false;
    const auto &offered = r.at("cards_offered.cards"), &offeredUp = r.at("cards_offered.upgrades");
    for (std::size_t i = 0; i < offered.size(); ++i)
        if (!add(4, offered[i].get<int>(), {offeredUp[i].get<double>() / 10})) return false;
    for (const auto &c : r.at("relics_offered")) if (!add(5, 512 + c.get<int>(), {})) return false;
    for (const auto &p : r.at("potions_offered")) if (!add(6, 768 + p.get<int>(), {})) return false;
    for (const auto &a : r.at("fixed_actions"))
        if (!add(7, 832 + a.at("action").get<int>(), {a.at("gold").get<double>() / 1800, a.at("card").get<double>() / 512,
                 a.at("relic").get<double>() / 256, a.at("info").get<double>() / 200}))
            return false;
    std::set<int> paths;
    for (const auto &p : r.at("paths_offered")) paths.insert(p.get<int>());
    const int my = r.at("obs.mapY").get<int>();
    const int bx = r.at("obs.map.burningEliteX").get<int>(), by = r.at("obs.map.burningEliteY").get<int>();
    const auto &xs = r.at("obs.map.xs"), &ys = r.at("obs.map.ys"), &rooms = r.at("obs.map.roomTypes"),
               &edges = r.at("obs.map.pathXs");
    for (std::size_t i = 0; i < xs.size(); ++i) {
        const int x = xs[i].get<int>(), y = ys[i].get<int>();
        if (y < my) continue;
        const auto &e = edges[i];
        if (!add(8, 1088 + rooms[i].get<int>(), {x / 7.0, y / 15.0, e[0].get<double>() / 7, e[1].get<double>() / 7,
                 e[2].get<double>() / 7, double(x == bx && y == by), double(y == my + 1 && paths.count(x)),
                 (y - my) / 15.0}))
            return false;
    }
    if (screen == 9) {
        const auto it = r.find("leaf.publicBattleEncounter");
        if (it == r.end() || !it->is_number_integer()) return false;
        const int encounter = it->get<int>();
        if (encounter < 1 || encounter > 63 || !add(9, 1280 + encounter, {})) return false;
    } else if (r.contains("leaf.publicBattleEncounter")) return false;
    if (memory) {
        const auto &slots = r.at("leaf.matchSlots");
        const int attempts = r.at("leaf.matchAttempts").get<int>();
        if (screen != 1 || slots.empty() || slots.size() > 12 || attempts < 0 || attempts > 5) return false;
        std::set<int> seen;
        for (const auto &slot : slots) {
            const int state = slot.at("state").get<int>(), card = slot.at("card").get<int>();
            const int position = slot.at("position").get<int>(), up = slot.at("upgrades").get<int>();
            if (state < -1 || state > 2 || position < 0 || position >= 12 || !seen.insert(position).second) return false;
            int entity = card;
            if (state == -1) {
                if (card != -1 || up != 0) return false;
                entity = 1535;
            } else if (card < 0 || card >= 512) return false;
            if (!add(10, entity, {position / 12.0, state / 3.0, up / 10.0})) return false;
        }
    }
    if (tokens.empty() || tokens.size() > kMaxTokens) return false;
    // DictVectorizer: dense entries, per-entity counts and attribute sums; unseen names drop out.
    std::map<int, float> columns;
    for (int i = 0; i < kDense; ++i)
        if (dense[i] != 0 && denseCol_[i] >= 0) columns[denseCol_[i]] += float(dense[i]);
    for (const auto &t : tokens) {
        const int key = t.kind * kEntities + t.entity;
        if (countCol_[key] >= 0) columns[countCol_[key]] += 1;
        for (int j = 0; j < kAttrs; ++j)
            if (t.attrs[j] != 0 && attrCol_[key * kAttrs + j] >= 0) columns[attrCol_[key * kAttrs + j]] += t.attrs[j];
    }
    sparse.assign(columns.begin(), columns.end());
    return true;
}

std::optional<double> RolloutStudent::predict(const nlohmann::json &record, double anchor) const {
    std::vector<std::pair<int, float>> sparse;
    std::vector<Token> tokens;
    try {
        if (!encode(record, sparse, tokens)) return std::nullopt;
    } catch (const nlohmann::json::exception &) {
        return std::nullopt;
    }
    // Sequence [cls, tokens]; two pre-norm encoder layers (ReLU FF, no dropout); read cls.
    const int n = int(tokens.size()) + 1;
    std::vector<float> h(std::size_t(n) * kDim), y(h.size()), qkv(std::size_t(n) * 3 * kDim), attn(h.size());
    std::copy(cls_.begin(), cls_.end(), h.begin());
    for (int i = 1; i < n; ++i) {
        const auto &t = tokens[i - 1];
        float *row = h.data() + std::size_t(i) * kDim;
        for (int d = 0; d < kDim; ++d) {
            float s = kind_[t.kind * kDim + d] + entity_[std::size_t(t.entity) * kDim + d];
            for (int j = 0; j < kAttrs; ++j) s += attrs_[d * kAttrs + j] * t.attrs[j];
            row[d] = s;
        }
    }
    constexpr int kHeadDim = kDim / kHeads;
    std::vector<float> scores(n), ff(kHidden), proj(kDim);
    for (const auto &l : layers_) {
        for (int i = 0; i < n; ++i) {
            layerNorm(h.data() + std::size_t(i) * kDim, l.n1W, l.n1B, y.data() + std::size_t(i) * kDim);
            linear(l.inW, l.inB, y.data() + std::size_t(i) * kDim, kDim, 3 * kDim, qkv.data() + std::size_t(i) * 3 * kDim);
        }
        for (int i = 0; i < n; ++i)
            for (int head = 0; head < kHeads; ++head) {
                const float *q = qkv.data() + std::size_t(i) * 3 * kDim + head * kHeadDim;
                float best = -INFINITY;
                for (int j = 0; j < n; ++j) {
                    const float *k = qkv.data() + std::size_t(j) * 3 * kDim + kDim + head * kHeadDim;
                    float s = 0;
                    for (int d = 0; d < kHeadDim; ++d) s += q[d] * k[d];
                    scores[j] = s / std::sqrt(float(kHeadDim));
                    best = std::max(best, scores[j]);
                }
                float total = 0;
                for (int j = 0; j < n; ++j) total += scores[j] = std::exp(scores[j] - best);
                float *out = attn.data() + std::size_t(i) * kDim + head * kHeadDim;
                std::fill(out, out + kHeadDim, 0.f);
                for (int j = 0; j < n; ++j) {
                    const float *v = qkv.data() + std::size_t(j) * 3 * kDim + 2 * kDim + head * kHeadDim;
                    for (int d = 0; d < kHeadDim; ++d) out[d] += scores[j] / total * v[d];
                }
            }
        for (int i = 0; i < n; ++i) {
            float *row = h.data() + std::size_t(i) * kDim;
            linear(l.outW, l.outB, attn.data() + std::size_t(i) * kDim, kDim, kDim, proj.data());
            for (int d = 0; d < kDim; ++d) row[d] += proj[d];
            layerNorm(row, l.n2W, l.n2B, y.data());
            linear(l.l1W, l.l1B, y.data(), kDim, kHidden, ff.data());
            for (auto &v : ff) v = std::max(v, 0.f);
            linear(l.l2W, l.l2B, ff.data(), kHidden, kDim, proj.data());
            for (int d = 0; d < kDim; ++d) row[d] += proj[d];
        }
    }
    // MLP on [vocabulary features, cls]; the feature part is sparse.
    const int width = inputs_ + kDim;
    std::vector<float> z0(kHidden), z1(kHidden);
    for (int o = 0; o < kHidden; ++o) {
        const float *row = w0_.data() + std::size_t(o) * width;
        float s = b0_[o];
        for (const auto &[col, v] : sparse) s += row[col] * v;
        for (int d = 0; d < kDim; ++d) s += row[inputs_ + d] * h[d];
        z0[o] = std::max(s, 0.f);
    }
    linear(w2_, b2_, z0.data(), kHidden, kHidden, z1.data());
    for (auto &v : z1) v = std::max(v, 0.f);
    float out = b4_[0];
    for (int i = 0; i < kHidden; ++i) out += w4_[i] * z1[i];
    const double base = std::clamp(anchor, 1e-4, 1 - 1e-4);
    return 1.0 / (1.0 + std::exp(-(double(out) + std::log(base / (1 - base)))));
}

int rolloutStudentScoreCommand(int argc, char **argv) {
    if (argc != 5) {
        std::fprintf(stderr, "usage: one_combat rolloutstudentscore <weights.bin> <rows.jsonl> <out.jsonl>\n");
        return 2;
    }
    const RolloutStudent student(argv[2]);
    std::ifstream in(argv[3]);
    std::ofstream out(argv[4]);
    if (!in || !out) throw std::runtime_error("rolloutstudentscore: cannot open input or output");
    std::string line;
    int n = 0, unsupported = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        const auto value = student.predict(row.at("record"), row.at("x2b").get<double>());
        out << (value ? nlohmann::json{{"value", *value}} : nlohmann::json{{"unsupported", true}}).dump() << '\n';
        ++n;
        unsupported += !value;
    }
    std::printf("rolloutstudentscore rows=%d unsupported=%d -> %s\n", n, unsupported, argv[4]);
    return 0;
}

}  // namespace one_combat
