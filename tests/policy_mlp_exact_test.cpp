// predictPolicyMlp must stay bit-identical to the plain reference loops below
// (the pre-2026-10-21 implementation): Silver's prior playouts take its argmax,
// so any rounding change can change play. Uses the deployed g7f_E model and
// random sparse inputs shaped like real calls (~60 nonzero state features,
// signed zeros, empty monster slots, 1-40 edges, with and without targets), plus
// special values (subnormals, huge and infinite inputs) in every fifth call.
#include "sim/search/CombatValueNet.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <random>
#include <vector>

using namespace sts::search;

namespace {

void referencePolicyMlp(const CombatValueNet &net, const float *stateFeatures, const float *actionBlocks,
                        const int *targetSlots, int n, double *out) {
    const int S = combatFeatureCount(), A = combatPolicyFeatureCount() - S;
    const int H1 = net.pmH1, H2 = net.pmH2;
    const int monOff = combatMonsterSlotOffset(), monFeats = kCombatMonsterSlotFeatures;
    const int embRows = 128, numCards = 371;
    std::vector<float> base(net.pmB1.begin(), net.pmB1.end()), h(H1), z(H2);
    auto row = [&](float v) {
        const int r = (int)std::lround(v);
        return r < 0 ? 0 : (r >= embRows ? embRows - 1 : r);
    };
    if (!net.pmEnc.empty()) {
        const float *w = &net.pmEnc[(std::size_t)row(stateFeatures[1]) * H1];
        for (int j = 0; j < H1; ++j) base[j] += w[j];
    }
    if (!net.pmMonId.empty() || !net.pmMonDmg.empty()) {
        for (int k = 0; k < 5; ++k) {
            const float id = stateFeatures[monOff + k * monFeats];
            if (id == 0.f || std::lround(id) + 1 <= 0) continue;
            if (!net.pmMonId.empty()) {
                const float *w = &net.pmMonId[(std::size_t)row(id + 1.f) * H1];
                for (int j = 0; j < H1; ++j) base[j] += w[j];
            }
            if (!net.pmMonDmg.empty()) {
                const float *w = &net.pmMonDmg[(std::size_t)row(stateFeatures[monOff + k * monFeats + 4]) * H1];
                for (int j = 0; j < H1; ++j) base[j] += w[j];
            }
        }
    }
    for (int i = 0; i < S; ++i) {
        const float v = stateFeatures[i];
        if (v == 0.f) continue;
        const float *w = &net.pmStateW[(std::size_t)i * H1];
        for (int j = 0; j < H1; ++j) base[j] += v * w[j];
    }
    for (int e = 0; e < n; ++e) {
        const float *a = actionBlocks + (std::size_t)e * A;
        for (int j = 0; j < H1; ++j) h[j] = base[j];
        for (int k = 0; k < A; ++k) {
            const float v = a[k];
            if (v == 0.f) continue;
            const float *w = &net.pmActionW[(std::size_t)k * H1];
            for (int j = 0; j < H1; ++j) h[j] += v * w[j];
        }
        int card = (int)a[4] + 1;
        if (card < 0 || card > numCards) card = 0;
        const float *c = &net.pmCard[(std::size_t)card * H1];
        for (int j = 0; j < H1; ++j) h[j] += c[j];
        const int slot = targetSlots ? targetSlots[e] : -1;
        if (slot >= 0 && slot < 5) {
            const float *t = stateFeatures + monOff + slot * monFeats;
            for (int k = 0; k < monFeats; ++k) {
                const float v = t[k];
                if (v == 0.f) continue;
                const float *w = &net.pmTargetW[(std::size_t)k * H1];
                for (int j = 0; j < H1; ++j) h[j] += v * w[j];
            }
        }
        for (int i = 0; i < H2; ++i) z[i] = net.pmB2[i];
        for (int j = 0; j < H1; ++j) {
            const float v = h[j];
            if (v <= 0.f) continue;
            const float *w = &net.pmW2T[(std::size_t)j * H2];
            for (int i = 0; i < H2; ++i) z[i] += v * w[i];
        }
        float o = net.pmB3;
        for (int i = 0; i < H2; ++i) if (z[i] > 0.f) o += net.pmW3[i] * z[i];
        out[e] = o;
    }
}

}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "models/combat_policy_mlp_g7f_E.txt";
    CombatValueNet net;
    if (!net.load(path) || !net.isPolicyMlp) {
        std::fprintf(stderr, "policy_mlp_exact_test: cannot load %s\n", path);
        return 1;
    }
    const int S = combatFeatureCount(), A = combatPolicyFeatureCount() - S;
    const int monOff = combatMonsterSlotOffset();
    std::mt19937 rng(20261021);
    std::uniform_int_distribution<int> feat(0, S - 1), small(0, 12), edgeCount(1, 12), slot(-1, 4);
    std::uniform_real_distribution<float> unit(0.f, 1.f);
    std::vector<float> state(S), actions;
    std::vector<int> targets;
    std::vector<double> got, want;
    long cases = 0, edges = 0, mismatches = 0;
    for (int c = 0; c < 4000; ++c) {
        std::fill(state.begin(), state.end(), 0.f);
        const int nnz = 20 + (int)(unit(rng) * 80);
        for (int i = 0; i < nnz; ++i) state[feat(rng)] = (float)small(rng) * (unit(rng) < 0.1f ? -1.f : 1.f);
        if (c % 7 == 0) state[feat(rng)] = -0.f;
        state[0] = 20.f;
        state[1] = (float)(c % 60);
        for (int k = 0; k < 5; ++k) {
            const int b = monOff + k * kCombatMonsterSlotFeatures;
            state[b] = k < 1 + c % 5 ? (float)(c % 50) : -1.f;
            state[b + 1] = (float)small(rng) * 10.f;
            state[b + 4] = (float)small(rng);
        }
        // Every fourth call has 13-40 edges (several interleaved output-sum groups of 8).
        const int n = c % 4 == 1 ? 13 + (int)(unit(rng) * 28) : edgeCount(rng);
        actions.assign((std::size_t)n * A, 0.f);
        targets.resize(n);
        for (int e = 0; e < n; ++e) {
            float *a = actions.data() + (std::size_t)e * A;
            for (int k = 0; k < 4; ++k) a[(unsigned)rng() % A] = (float)small(rng);
            a[4] = e + 1 == n ? -1.f : (float)((unsigned)rng() % 371);
            targets[e] = slot(rng);
        }
        // Every fifth call carries special values: signed zeros, subnormals, huge and infinite inputs.
        if (c % 5 == 2) {
            const float special[] = {-0.f, 1e-40f, -1e-40f, 1e30f, -1e30f, INFINITY, -INFINITY, 3e-39f};
            for (int i = 0; i < 6; ++i) state[feat(rng)] = special[(unsigned)rng() % 8];
            for (int i = 0; i < 2; ++i) actions[(unsigned)rng() % actions.size()] = special[(unsigned)rng() % 8];
            for (int e = 0; e < n; ++e) actions[(std::size_t)e * A + 4] = e + 1 == n ? -1.f : (float)((unsigned)rng() % 371);
        }
        const int *t = c % 3 == 0 ? nullptr : targets.data();
        got.assign(n, 0.0);
        want.assign(n, 0.0);
        net.predictPolicyMlp(state.data(), actions.data(), t, n, got.data());
        referencePolicyMlp(net, state.data(), actions.data(), t, n, want.data());
        ++cases;
        edges += n;
        // Bit for bit; a NaN output (inf - inf from the special values) only has to be NaN on both sides.
        for (int e = 0; e < n; ++e) {
            if (std::isnan(got[e]) && std::isnan(want[e])) continue;
            if (std::memcmp(&got[e], &want[e], sizeof(double)) != 0) { ++mismatches; break; }
        }
    }
    std::printf("policy_mlp_exact_test: %ld calls, %ld edges, %ld mismatches\n", cases, edges, mismatches);
    return mismatches == 0 ? 0 : 1;
}
