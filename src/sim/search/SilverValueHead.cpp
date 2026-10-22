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
    vec("mu", h.mu, h.in);
    vec("inv_sd", h.invSd, h.in);
    vec("w1", h.w1, static_cast<std::size_t>(h.hidden) * h.in);
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
    double y = b2;
    for (int i = 0; i < hidden; ++i) {
        double a = b1[i];
        const float *w = &w1[static_cast<std::size_t>(i) * in];
        for (int j = 0; j < in; ++j) a += w[j] * ((trunk[j] - mu[j]) * invSd[j]);
        if (a > 0) y += w2[i] * a;
    }
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
