// V4 token net: the derived-table paths (cached deck tokens, transposed
// layers, Q prefix) must give bitwise the same floats as the reference loops.
// Usage: ooc_tok_net_fast_test MODEL.native
#include "ooc_strategic_tok_net.h"

#include <cstring>
#include <iostream>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>

namespace {
using Net = OocStrategicTokNet;

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

bool same(const float *a, const float *b, int n) { return std::memcmp(a, b, sizeof(float) * n) == 0; }
bool same(float a, float b) { return std::memcmp(&a, &b, sizeof(float)) == 0; }

struct Inputs {
    float glob[Net::NGLB];
    int nDk = 0, dk[Net::MAXDK][3] = {};
    int nRl = 0, rl[Net::MAXRL][2] = {};
    int nPt = 0, pt[Net::MAXPT][2] = {};
};

Inputs randomInputs(const Net &net, std::mt19937 &rng, int trial) {
    auto uni = [&](int lo, int hi) { return std::uniform_int_distribution<int>(lo, hi)(rng); };
    std::normal_distribution<float> normal(0.0f, 1.5f);
    Inputs in;
    for (int i = 0; i < Net::NGLB; ++i) {
        const float inv = net.globInv[i];
        in.glob[i] = net.globMean[i] + (inv > 0.0f && inv < 1e5f ? normal(rng) / inv : normal(rng));
    }
    // Mostly in-range rows, some out of range to reach the clamps and the
    // uncached negative-count token.
    in.nDk = trial % 17 == 0 ? 0 : uni(1, trial % 5 == 0 ? Net::MAXDK + 8 : 40);
    for (int i = 0; i < std::min(in.nDk, Net::MAXDK); ++i) {
        const bool odd = uni(0, 30) == 0;
        in.dk[i][0] = odd ? uni(-3, Net::NCARD + 3) : uni(0, Net::NCARD - 1);
        in.dk[i][1] = odd ? uni(-1, 2) : uni(0, 1);
        in.dk[i][2] = odd ? uni(-2, 14) : uni(1, 4);
    }
    in.nRl = trial % 13 == 0 ? 0 : uni(1, 30);
    for (int i = 0; i < in.nRl; ++i) {
        in.rl[i][0] = uni(-2, Net::NREL + 2);
        in.rl[i][1] = uni(-3, 14);
    }
    in.nPt = uni(0, Net::MAXPT);
    for (int i = 0; i < in.nPt; ++i) {
        in.pt[i][0] = uni(-2, Net::NPOT + 2);
        in.pt[i][1] = uni(-1, 12);
    }
    return in;
}
}

int main(int argc, char **argv) try {
    require(argc == 2, "usage: ooc_tok_net_fast_test MODEL.native");
    auto fast = std::make_unique<Net>();
    require(fast->load(argv[1], true), "model load");
    require(fast->derived.ready, "load did not build the derived tables");
    auto reference = std::make_unique<Net>(*fast);
    reference->derived = Net::Derived{};

    std::mt19937 rng(20261012u);
    auto uni = [&](int lo, int hi) { return std::uniform_int_distribution<int>(lo, hi)(rng); };
    int states = 0, actions = 0;
    for (int trial = 0; trial < 400; ++trial) {
        const Inputs in = randomInputs(*fast, rng, trial);
        const auto a = fast->prepareState(in.glob, in.nDk, in.dk, in.nRl, in.rl, in.nPt, in.pt);
        const auto b = reference->prepareState(in.glob, in.nDk, in.dk, in.nRl, in.rl, in.nPt, in.pt);
        require(a.hasQPrefix && !b.hasQPrefix, "Q prefix presence");
        require(same(a.values, b.values, Net::NHIDDEN2), "prepareState differs at trial " + std::to_string(trial));
        const int screen = uni(-1, Net::NSCR + 1);
        require(same(fast->predictValue(in.glob, screen), reference->predictValue(in.glob, screen)),
                "predictValue differs");
        const auto pa = fast->preparePolicyPrefix(a);
        const auto pb = reference->preparePolicyPrefix(b);
        require(same(pa.values, pb.values, Net::POLHID), "policy prefix differs");
        for (int k = 0; k < 6; ++k, ++actions) {
            const std::uint32_t bits = static_cast<std::uint32_t>(rng());
            const int cats[6] = {uni(-2, 600), uni(-2, 600), uni(-2, 600), uni(-1, 400), uni(-1, 400), uni(-1, 400)};
            const int actionType = uni(-1, Net::ATYPEVOCAB + 1);
            const int entType = uni(0, 3);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const int entId = uni(-1, Net::NCARD + 1);
            const float gold = uni(0, 1) ? 1.0f : 0.0f;
            const float qRef = reference->predictActionValue(b, bits, cats, actionType, screen, entT, entId, gold);
            require(same(fast->predictActionValue(a, bits, cats, actionType, screen, entT, entId, gold), qRef),
                    "predictActionValue differs");
            require(same(fast->predictActionValue(b, bits, cats, actionType, screen, entT, entId, gold), qRef),
                    "predictActionValue without Q prefix differs");
            require(same(fast->predictActionValue(in.glob, in.nDk, in.dk, in.nRl, in.rl, in.nPt, in.pt,
                                                  bits, cats, actionType, screen, entT, entId, gold), qRef),
                    "unprepared predictActionValue differs");
            const float lRef = reference->predictPolicyLogit(b, bits, cats, actionType, screen, entT, entId, gold);
            require(same(fast->predictPolicyLogit(a, bits, cats, actionType, screen, entT, entId, gold), lRef),
                    "predictPolicyLogit differs");
            require(same(fast->predictPolicyLogit(a, pa, bits, cats, actionType, screen, entT, entId, gold), lRef)
                    && same(reference->predictPolicyLogit(b, pb, bits, cats, actionType, screen, entT, entId, gold), lRef),
                    "predictPolicyLogit with prefix differs");
        }
        ++states;
    }
    // A copy keeps working tables; a rebuild after an in-place edit follows the edit.
    auto edited = std::make_unique<Net>(*fast);
    edited->eCard[1][0] += 0.25f; edited->f0w[3][5] -= 0.5f; edited->q0w[2][7] += 0.5f;
    edited->rebuildDerived();
    auto editedRef = std::make_unique<Net>(*edited);
    editedRef->derived = Net::Derived{};
    const Inputs in = randomInputs(*fast, rng, 1);
    Inputs withCard = in;
    withCard.nDk = 1; withCard.dk[0][0] = 1; withCard.dk[0][1] = 0; withCard.dk[0][2] = 2;
    const auto e1 = edited->prepareState(withCard.glob, 1, withCard.dk, in.nRl, in.rl, in.nPt, in.pt);
    const auto e2 = editedRef->prepareState(withCard.glob, 1, withCard.dk, in.nRl, in.rl, in.nPt, in.pt);
    const int cats[6] = {1, 2, 3, 0, 0, 0};
    const float entT[4] = {0.0f, 1.0f, 0.0f, 0.0f};
    require(same(e1.values, e2.values, Net::NHIDDEN2)
            && same(edited->predictActionValue(e1, 5u, cats, 1, 2, entT, 1, 1.0f),
                    editedRef->predictActionValue(e2, 5u, cats, 1, 2, entT, 1, 1.0f))
            && !same(e1.values, fast->prepareState(withCard.glob, 1, withCard.dk, in.nRl, in.rl,
                                                   in.nPt, in.pt).values, Net::NHIDDEN2),
            "rebuilt tables do not follow the edited weights");
    std::cout << "ooc_tok_net_fast: PASS (" << states << " states, " << actions
              << " actions, bitwise equal to the reference loops)\n";
    return 0;
} catch (const std::exception &e) {
    std::cerr << "ooc_tok_net_fast: FAIL: " << e.what() << '\n';
    return 1;
}
