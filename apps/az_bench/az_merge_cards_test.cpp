// Card-stack merging (search::amberMergeCards) over the states the stage 1 driver encodes in whole runs (combat and
// out of combat, fake net): CARD slot 41 is unused before merging; the merged CARD tokens are pairwise different, and
// each raw card is in exactly one stack of an identical card whose copy count (slot 41) is the number of raw copies;
// every other segment and every action field is unchanged except CARD references, which name the stack of the card
// they named; merging twice changes nothing. Prints the token reduction.
//
// usage: az-merge-cards-test [--runs 6] [--seed-base 1] [--test-hp 0]
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <random>
#include <string>
#include <vector>

#include "az_run_driver.h"
#include "sim/search/AmberEncoder.h"

using namespace sts;
using search::AmberToken;
using search::AmberTokens;

namespace {

    constexpr int kCard = static_cast<int>(search::AmberTokenType::CARD);
    std::atomic<long long> g_states{0}, g_fail{0}, g_rawTok{0}, g_mergedTok{0}, g_rawCards{0}, g_mergedCards{0};
    std::mutex g_printM;

    bool sameCard(const AmberToken &a, const AmberToken &b) {   // ignoring the copy count and a deck card's index
        if (a.ids != b.ids) return false;
        const bool deck = a.f[10] == 0x3c00;
        for (int j = 0; j < search::kAmberFloat; ++j)
            if (j != 41 && !(deck && j == 11) && a.f[j] != b.f[j]) return false;
        return true;
    }

    int liveTokens(const AmberTokens &t) {
        int n = 0;
        for (int s = 0; s < search::kAmberTokenTypes; ++s) n += t.n[s];
        return n;
    }

    void fail(const char *what) {
        if (++g_fail <= 20) {
            std::lock_guard<std::mutex> l(g_printM);
            std::fprintf(stderr, "FAIL: %s\n", what);
        }
    }

    void check(const AmberTokens &raw, const AmberTokens &m) {
        ++g_states;
        g_rawTok += liveTokens(raw);
        g_mergedTok += liveTokens(m);
        g_rawCards += raw.n[kCard];
        g_mergedCards += m.n[kCard];
        const AmberToken *rc = &raw.tok[search::kAmberOff[kCard]], *mc = &m.tok[search::kAmberOff[kCard]];
        const int rn = raw.n[kCard], mn = m.n[kCard];
        for (int i = 0; i < rn; ++i)
            if (rc[i].f[41] != 0) { fail("CARD slot 41 used before merging"); return; }
        for (int s = 0; s < search::kAmberTokenTypes; ++s) {
            if (s == kCard) continue;
            if (raw.n[s] != m.n[s] ||
                std::memcmp(&raw.tok[search::kAmberOff[s]], &m.tok[search::kAmberOff[s]], sizeof(AmberToken) * raw.n[s]))
                { fail("non-CARD segment changed"); return; }
        }
        if (raw.nAct != m.nAct || raw.cut != m.cut) { fail("action count / cut changed"); return; }
        // Stacks: pairwise different; copy counts add up per identical card.
        int total = 0;
        for (int i = 0; i < mn; ++i) {
            const int copies = static_cast<int>(std::lround(search::amberHalfToFloat(mc[i].f[41]) * 10.0f)) + 1;
            total += copies;
            int raws = 0;
            for (int j = 0; j < rn; ++j) raws += sameCard(rc[j], mc[i]);
            if (raws != copies) { fail("copy count differs from the raw copies"); return; }
            for (int j = i + 1; j < mn; ++j)
                if (sameCard(mc[i], mc[j])) { fail("two stacks of the same card"); return; }
        }
        if (total != rn) { fail("copies do not add up to the raw cards"); return; }
        for (int a = 0; a < raw.nAct; ++a) {
            const auto &x = raw.act[a], &y = m.act[a];
            if (x.type != y.type || x.srcSeg != y.srcSeg || x.tgtSeg != y.tgtSeg || x.f != y.f)
                { fail("action fields changed"); return; }
            if (x.srcSeg != kCard && x.srcIdx != y.srcIdx) { fail("non-CARD source changed"); return; }
            if (x.tgtSeg != kCard && x.tgtIdx != y.tgtIdx) { fail("non-CARD target changed"); return; }
            if (x.srcSeg == kCard && (y.srcIdx >= mn || !sameCard(rc[x.srcIdx], mc[y.srcIdx]))) { fail("CARD source not its stack"); return; }
            if (x.tgtSeg == kCard && (y.tgtIdx >= mn || !sameCard(rc[x.tgtIdx], mc[y.tgtIdx]))) { fail("CARD target not its stack"); return; }
        }
        AmberTokens twice = m;
        search::amberMergeCards(twice);
        if (std::memcmp(&twice, &m, sizeof(AmberTokens))) fail("merging twice changes the tokens");
    }

    void encodeCombat(const BattleContext &bc, const search::SilverSearchContext &ctx,
                      const std::vector<search::Action> &acts, AmberTokens &out) {
        search::amberEncodeCombat(bc, ctx, acts, out);
        AmberTokens raw = out;
        search::amberMergeCards(out);
        check(raw, out);
    }

    void encodeGame(const GameContext &gc, const std::vector<search::GameAction> &acts, AmberTokens &out) {
        search::amberEncodeGame(gc, acts, out);
        AmberTokens raw = out;
        search::amberMergeCards(out);
        check(raw, out);
    }

}

int main(int argc, char **argv) {
    azbench::RunConfig cfg;
    cfg.workers = 2;
    cfg.gamesPerWorker = 3;
    cfg.maxRuns = 6;
    cfg.seedBase = 1;
    cfg.fullSims = 8; cfg.fastSims = 4; cfg.fullCandidates = 4; cfg.fastCandidates = 2;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() { if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", a.c_str()); std::exit(2); } return std::string(argv[++i]); };
        if (a == "--runs") cfg.maxRuns = std::stoll(next());
        else if (a == "--seed-base") cfg.seedBase = std::stoull(next());
        else if (a == "--test-hp") cfg.testMaxHp = std::stoi(next());
        else { std::fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
    }
    cfg.encodeCombat = encodeCombat;
    cfg.encodeGame = encodeGame;
    const int T = search::kAmberMaxTokens, A = search::kAmberMaxActions, R = 32;
    std::vector<std::int8_t> tokType(static_cast<std::size_t>(R) * T);
    std::vector<std::int16_t> ids(static_cast<std::size_t>(R) * T * search::kAmberCat);
    std::vector<std::uint16_t> f(static_cast<std::size_t>(R) * T * search::kAmberFloat);
    std::vector<std::uint8_t> mask(static_cast<std::size_t>(R) * T), aMask(static_cast<std::size_t>(R) * A);
    std::vector<std::int16_t> aType(static_cast<std::size_t>(R) * A), aSrc(aType.size()), aTgt(aType.size());
    std::vector<std::uint16_t> aF(static_cast<std::size_t>(R) * A * search::kAmberActFeat);
    azbench::FlatBuffers fb{tokType.data(), ids.data(), f.data(), mask.data(), aType.data(), aSrc.data(), aTgt.data(),
                            aF.data(), aMask.data()};
    azbench::RunDriver d(cfg);
    d.start();
    std::mt19937_64 rng(7);
    std::uniform_real_distribution<float> U(0.f, 1.f);
    std::vector<float> logits, F, ehp;
    std::vector<azbench::Sample> samples;
    while (d.stats().runsDone < cfg.maxRuns) {
        azbench::FlatShape shape;
        const auto tickets = d.nextBatchFlat(R, 1, 5, {}, {}, {}, fb, shape, 1);
        if (tickets.empty()) continue;
        const int B = shape.rows;
        logits.assign(static_cast<std::size_t>(B) * shape.actions, 0.f);
        F.resize(B);
        ehp.resize(B);
        for (auto &x : logits) x = U(rng);
        for (int r = 0; r < B; ++r) { F[r] = U(rng); ehp[r] = 80.f * U(rng); }
        d.submit(tickets.data(), B, shape.actions, logits.data(), F.data(), ehp.data());
        d.takeSamples(1 << 20, samples);
    }
    d.stop();
    const auto s = d.stats();
    std::printf("{\"runs\": %lld, \"mean_floor\": %.2f, \"states\": %lld, \"fails\": %lld, \"tokens_per_state\": %.2f, "
                "\"merged_tokens_per_state\": %.2f, \"cards_per_state\": %.2f, \"merged_cards_per_state\": %.2f}\n",
                static_cast<long long>(s.runsDone), s.runsDone ? static_cast<double>(s.floorsSum) / s.runsDone : 0.0,
                g_states.load(), g_fail.load(), static_cast<double>(g_rawTok) / std::max(1LL, g_states.load()),
                static_cast<double>(g_mergedTok) / std::max(1LL, g_states.load()),
                static_cast<double>(g_rawCards) / std::max(1LL, g_states.load()),
                static_cast<double>(g_mergedCards) / std::max(1LL, g_states.load()));
    return g_fail || g_states == 0 || s.invalidActions ? 1 : 0;
}
