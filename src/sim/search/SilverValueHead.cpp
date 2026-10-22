#include "sim/search/SilverValueHead.h"

#include <algorithm>
#include <fstream>
#include <stdexcept>

#include "sim/search/CombatValueNet.h"

using namespace sts;

search::SilverValueHead search::SilverValueHead::load(const std::string &path) {
    std::ifstream f(path);
    SilverValueHead h;
    std::string tok;
    auto vec = [&](const char *want, std::vector<float> &v, std::size_t n) {
        if (!(f >> tok) || tok != want) throw std::runtime_error(path + ": expected " + want);
        v.resize(n);
        for (float &x : v) f >> x;
    };
    if (!(f >> tok) || tok != "silver_value_head_v1") throw std::runtime_error(path + ": not a silver_value_head_v1");
    f >> tok >> h.in >> tok >> h.hidden;
    if (!f || h.in < 1 || h.in > kMaxWidth || h.hidden < 1 || h.hidden > kMaxWidth)
        throw std::runtime_error(path + ": bad head shape");
    vec("mu", h.mu, h.in);
    vec("inv_sd", h.invSd, h.in);
    std::vector<float> w1;   // row-major (hidden x in) in the file
    vec("w1", w1, static_cast<std::size_t>(h.hidden) * h.in);
    h.w1t.resize(w1.size());
    for (int i = 0; i < h.hidden; ++i)
        for (int j = 0; j < h.in; ++j)
            h.w1t[static_cast<std::size_t>(j) * h.hidden + i] = w1[static_cast<std::size_t>(i) * h.in + j];
    vec("b1", h.b1, h.hidden);
    vec("w2", h.w2, h.hidden);
    std::vector<float> one;
    vec("b2", one, 1);
    h.b2 = one[0];
    f >> tok >> h.scale >> tok >> h.offset;
    if (!f) throw std::runtime_error(path + ": truncated");
    return h;
}

double search::SilverValueHead::value(const std::vector<float> &trunk) const {
    float x[kMaxWidth];
    double a[kMaxWidth];
    for (int j = 0; j < in; ++j) x[j] = (trunk[j] - mu[j]) * invSd[j];
    for (int i = 0; i < hidden; ++i) a[i] = b1[i];
    for (int j = 0; j < in; ++j) {
        const float xj = x[j];
        const float *w = &w1t[static_cast<std::size_t>(j) * hidden];
        for (int i = 0; i < hidden; ++i) a[i] += static_cast<double>(w[i] * xj);
    }
    double y = b2;
    for (int i = 0; i < hidden; ++i)
        if (a[i] > 0) y += w2[i] * a[i];
    return scale * y + offset;
}

double search::SilverValueHead::value(const BattleContext &state, const CombatValueNet &trunk,
                                      std::vector<float> &feat, std::vector<float> &base) const {
    feat.assign(combatFeatureCount(), 0.f);
    combatExtractFeatures(state, feat.data());
    trunk.policyMlpBase(feat.data(), base);
    for (float &x : base) x = std::max(x, 0.f);
    return value(base);
}
