// Evaluation cache of the stage 1 run driver (RunConfig::evalCache, az_run_driver.h) is exact: with a net whose
// output depends only on its input row, runs played with and without the cache make the same moves and produce the
// same training samples, and every leaf is either a net evaluation or a cache hit (evals without = evals + hits
// with). A cached result is never used after the weights version changed (version bumped before every batch:
// no hits).
//
// One worker with one run in flight, so the search's RNG sequence does not depend on batch timing.
//
// --utility amber: the net also gives per-floor HP (hpf), which the cache must return too.
//
// --amber-search: Amber Eye's search rules (chanceOnReveal, crossCombat, simHelp) on; the cache stays exact.
//
// usage: az-eval-cache-test [--runs 3] [--seed-base 1] [--fast] [--utility amber] [--amber-search]
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "az_run_driver.h"

using namespace sts;

namespace {

    std::uint64_t mix(std::uint64_t h, std::uint64_t w) {
        h ^= w + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
        h ^= h >> 31;
        h *= 0xbf58476d1ce4e5b9ull;
        return h ^ (h >> 29);
    }

    float unit(std::uint64_t h) { return static_cast<float>((h >> 11) * (1.0 / 9007199254740992.0)); }

    struct Result {
        std::uint64_t digest = 0;
        azbench::RunStats stats;
        std::size_t samples = 0;
        int batches = 0;
    };

    // Plays cfg.maxRuns runs with a fake net that is a hash of each row's live input (and of the weights version
    // when versionPerBatch: the version is bumped before every batch).
    Result play(azbench::RunConfig cfg, bool versionPerBatch) {
        const int T = search::kAmberMaxTokens, A = search::kAmberMaxActions, R = 8;
        std::vector<std::int8_t> tokType(static_cast<std::size_t>(R) * T);
        std::vector<std::int16_t> ids(static_cast<std::size_t>(R) * T * search::kAmberCat);
        std::vector<std::uint16_t> f(static_cast<std::size_t>(R) * T * search::kAmberFloat);
        std::vector<std::uint8_t> mask(static_cast<std::size_t>(R) * T), aMask(static_cast<std::size_t>(R) * A);
        std::vector<std::int16_t> aType(static_cast<std::size_t>(R) * A), aSrc(aType.size()), aTgt(aType.size());
        std::vector<std::uint16_t> aF(static_cast<std::size_t>(R) * A * search::kAmberActFeat);
        azbench::FlatBuffers fb{tokType.data(), ids.data(), f.data(), mask.data(), aType.data(), aSrc.data(),
                                aTgt.data(), aF.data(), aMask.data()};
        azbench::RunDriver d(cfg);
        Result res;
        std::uint32_t version = 0;
        d.start();
        std::vector<float> logits, F, ehp, hpf;
        const bool amber = cfg.utility == azbench::Utility::AMBER;
        std::vector<azbench::Sample> samples;
        while (d.stats().runsDone < cfg.maxRuns) {
            if (versionPerBatch) d.setWeightsVersion(++version);
            azbench::FlatShape shape;
            const auto tickets = d.nextBatchFlat(R, 1, 5, {}, {}, {}, fb, shape, 1);
            if (tickets.empty()) continue;
            ++res.batches;
            const int B = shape.rows, Tn = shape.tokens, An = shape.actions;
            logits.assign(static_cast<std::size_t>(B) * An, 0.f);
            F.resize(B);
            ehp.resize(B);
            hpf.resize(static_cast<std::size_t>(B) * azbench::kFloors);
            for (int r = 0; r < B; ++r) {
                std::uint64_t h = version;
                for (int t = 0; t < Tn; ++t) {
                    const std::size_t q = static_cast<std::size_t>(r) * Tn + t;
                    if (!mask[q]) continue;
                    h = mix(h, static_cast<std::uint64_t>(t) << 8 | static_cast<std::uint8_t>(tokType[q]));
                    for (int c = 0; c < search::kAmberCat; ++c) h = mix(h, static_cast<std::uint16_t>(ids[q * search::kAmberCat + c]));
                    for (int c = 0; c < search::kAmberFloat; ++c) h = mix(h, f[q * search::kAmberFloat + c]);
                }
                for (int a = 0; a < An; ++a) {
                    const std::size_t q = static_cast<std::size_t>(r) * An + a;
                    if (!aMask[q]) continue;
                    h = mix(h, static_cast<std::uint64_t>(static_cast<std::uint16_t>(aType[q])) << 32 |
                                   static_cast<std::uint64_t>(static_cast<std::uint16_t>(aSrc[q])) << 16 |
                                   static_cast<std::uint16_t>(aTgt[q]));
                    for (int c = 0; c < search::kAmberActFeat; ++c) h = mix(h, aF[q * search::kAmberActFeat + c]);
                }
                for (int a = 0; a < An; ++a) logits[static_cast<std::size_t>(r) * An + a] = 4.f * unit(mix(h, 1000 + a)) - 2.f;
                F[r] = unit(mix(h, 1));
                ehp[r] = 80.f * unit(mix(h, 2));
                for (int k = 0; k < azbench::kFloors; ++k) hpf[static_cast<std::size_t>(r) * azbench::kFloors + k] = unit(mix(h, 3 + k));
            }
            d.submit(tickets.data(), B, An, logits.data(), F.data(), ehp.data(), amber ? hpf.data() : nullptr, version);
            d.takeSamples(1 << 20, samples);
        }
        d.stop();
        d.takeSamples(1 << 20, samples);
        res.stats = d.stats();
        res.samples = samples.size();
        std::uint64_t h = 0;
        for (const auto &s : samples) {
            for (auto x : s.tokType) h = mix(h, static_cast<std::uint8_t>(x));
            for (auto x : s.ids) h = mix(h, static_cast<std::uint16_t>(x));
            for (auto x : s.f) h = mix(h, x);
            for (auto x : s.aType) h = mix(h, static_cast<std::uint16_t>(x));
            for (auto x : s.policy) { std::uint32_t u; std::memcpy(&u, &x, 4); h = mix(h, u); }
            std::uint32_t u;
            std::memcpy(&u, &s.searchValue, 4);
            h = mix(h, u);
            h = mix(h, static_cast<std::uint64_t>(s.outcome) << 32 | static_cast<std::uint16_t>(s.hpEnd));
            h = mix(h, s.run);
        }
        const auto &st = res.stats;
        h = mix(h, static_cast<std::uint64_t>(st.moves));
        h = mix(h, static_cast<std::uint64_t>(st.floorsSum));
        for (auto x : st.outcomes) h = mix(h, static_cast<std::uint64_t>(x));
        res.digest = h;
        return res;
    }

}

int main(int argc, char **argv) {
    azbench::RunConfig cfg;
    cfg.workers = 1;
    cfg.gamesPerWorker = 1;
    cfg.maxRuns = 3;
    cfg.seedBase = 1;
    cfg.keepFast = 0.2;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() { if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", a.c_str()); std::exit(2); } return std::string(argv[++i]); };
        if (a == "--runs") cfg.maxRuns = std::stoll(next());
        else if (a == "--seed-base") cfg.seedBase = std::stoull(next());
        else if (a == "--utility") { const std::string u = next(); if (u != "amber") { std::fprintf(stderr, "unknown utility %s\n", u.c_str()); return 2; } cfg.utility = azbench::Utility::AMBER; }
        else if (a == "--amber-search") cfg.chanceOnReveal = cfg.crossCombat = cfg.simHelp = true;
        else if (a == "--fast") { cfg.fullSims = 8; cfg.fastSims = 4; cfg.fullCandidates = 4; cfg.fastCandidates = 2; }
        else { std::fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
    }
    azbench::RunConfig off = cfg, on = cfg;
    on.evalCache = true;
    const Result a = play(off, false), b = play(on, false), c = play(on, true);
    std::printf("{\"no_cache\": {\"evals\": %lld, \"moves\": %lld, \"samples\": %zu, \"digest\": \"%016llx\"}, "
                "\"cache\": {\"evals\": %lld, \"hits\": %lld, \"moves\": %lld, \"samples\": %zu, \"digest\": \"%016llx\"}, "
                "\"cache_version_per_batch\": {\"evals\": %lld, \"hits\": %lld}}\n",
                static_cast<long long>(a.stats.evals), static_cast<long long>(a.stats.moves), a.samples,
                static_cast<unsigned long long>(a.digest), static_cast<long long>(b.stats.evals),
                static_cast<long long>(b.stats.cacheHits), static_cast<long long>(b.stats.moves), b.samples,
                static_cast<unsigned long long>(b.digest), static_cast<long long>(c.stats.evals),
                static_cast<long long>(c.stats.cacheHits));
    int fail = 0;
    if (a.digest != b.digest || a.samples != b.samples || a.stats.moves != b.stats.moves) {
        std::fprintf(stderr, "FAIL: runs differ with the cache\n");
        fail = 1;
    }
    if (a.stats.cacheHits != 0 || b.stats.cacheHits == 0 || a.stats.evals != b.stats.evals + b.stats.cacheHits) {
        std::fprintf(stderr, "FAIL: leaves do not add up (no cache %lld evals; cache %lld evals + %lld hits)\n",
                     static_cast<long long>(a.stats.evals), static_cast<long long>(b.stats.evals),
                     static_cast<long long>(b.stats.cacheHits));
        fail = 1;
    }
    if (c.stats.cacheHits != 0) {
        std::fprintf(stderr, "FAIL: a cached result was used after the weights version changed\n");
        fail = 1;
    }
    if (a.samples == 0 || a.stats.runsDone < cfg.maxRuns) { std::fprintf(stderr, "FAIL: no runs / samples\n"); fail = 1; }
    return fail;
}
