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
// --ema LAM (RunConfig::searchEmaLambda): the net also gives an outcome distribution (dist) and F is that
// distribution's E[final floor] / 57; the HP weights are 0, so the utility is F alone. Then also: (1) the search with
// the search-backed distributions makes the same moves and the same samples (all other fields) as without them;
// (2) every sample's searchValue equals F of its search-backed distribution (the distribution is backed up exactly
// as the scalar); (3) distributions and targets sum to 1; (4) the cache returns the distributions too (the digest
// includes them).
//
// usage: az-eval-cache-test [--runs 3] [--seed-base 1] [--fast] [--utility amber] [--ema LAM]
#include <algorithm>
#include <cmath>
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
        std::uint64_t baseDigest = 0;   // without the search EMA fields
        double maxValueGap = 0;         // --ema: max |searchValue - F(searchDist)|
        double maxSumGap = 0;           // --ema: max |sum - 1| of searchDist and outcomeTarget
        azbench::RunStats stats;
        std::size_t samples = 0;
        int batches = 0;
    };

    // Plays cfg.maxRuns runs with a fake net that is a hash of each row's live input (and of the weights version
    // when versionPerBatch: the version is bumped before every batch).
    Result play(azbench::RunConfig cfg, bool versionPerBatch, bool distNet = false) {
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
        std::vector<float> logits, F, ehp, hpf, dist;
        const bool ema = cfg.searchEmaLambda > 0;
        distNet = distNet || ema;   // the fake net's F comes from its outcome distribution
        auto floorValue = [](int k) { return (k == 0 ? 57.0 : k) / 57.0; };
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
            dist.resize(static_cast<std::size_t>(B) * azbench::kOutcomeClasses);
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
                if (distNet) {
                    float *p = dist.data() + static_cast<std::size_t>(r) * azbench::kOutcomeClasses;
                    double z = 0, Fr = 0;
                    for (int k = 0; k < azbench::kOutcomeClasses; ++k) { p[k] = unit(mix(h, 100 + k)) + 1e-3f; z += p[k]; }
                    for (int k = 0; k < azbench::kOutcomeClasses; ++k) { p[k] = static_cast<float>(p[k] / z); Fr += p[k] * floorValue(k); }
                    F[r] = static_cast<float>(Fr);
                }
            }
            d.submit(tickets.data(), B, An, logits.data(), F.data(), ehp.data(), amber ? hpf.data() : nullptr, version,
                     ema ? dist.data() : nullptr);
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
        res.baseDigest = h;
        for (const auto &s : samples) {
            if (!ema) break;
            double sd = 0, st2 = 0, Fs = 0;
            for (std::size_t k = 0; k < s.searchDist.size(); ++k) { sd += s.searchDist[k]; Fs += s.searchDist[k] * floorValue(static_cast<int>(k)); }
            for (auto x : s.outcomeTarget) st2 += x;
            if (s.searchDist.size() != static_cast<std::size_t>(azbench::kOutcomeClasses) ||
                s.outcomeTarget.size() != static_cast<std::size_t>(azbench::kOutcomeClasses)) res.maxSumGap = 1e9;
            res.maxSumGap = std::max({res.maxSumGap, std::abs(sd - 1), std::abs(st2 - 1)});
            res.maxValueGap = std::max(res.maxValueGap, std::abs(Fs - s.searchValue));
            for (auto x : s.searchDist) { std::uint32_t u; std::memcpy(&u, &x, 4); h = mix(h, u); }
            for (auto x : s.outcomeTarget) { std::uint32_t u; std::memcpy(&u, &x, 4); h = mix(h, u); }
            std::uint32_t u;
            std::memcpy(&u, &s.emaRealWeight, 4);
            h = mix(h, u);
        }
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
        else if (a == "--ema") { cfg.searchEmaLambda = std::stod(next()); cfg.hpWeightCombat = cfg.hpWeightOoc = 0; }
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
    if (cfg.searchEmaLambda > 0) {
        azbench::RunConfig plain = cfg;
        plain.searchEmaLambda = 0;
        const Result p = play(plain, false, true);   // the same fake net, distributions not submitted
        std::printf("{\"ema\": {\"lambda\": %g, \"max_value_gap\": %.3g, \"max_sum_gap\": %.3g, \"base_digest\": \"%016llx\", "
                    "\"plain_digest\": \"%016llx\"}}\n", cfg.searchEmaLambda, a.maxValueGap, a.maxSumGap,
                    static_cast<unsigned long long>(a.baseDigest), static_cast<unsigned long long>(p.baseDigest));
        if (p.baseDigest != a.baseDigest || p.samples != a.samples) {
            std::fprintf(stderr, "FAIL: the search-backed distributions changed the moves or samples\n");
            fail = 1;
        }
        if (a.maxValueGap > 1e-5) { std::fprintf(stderr, "FAIL: searchValue != F(searchDist)\n"); fail = 1; }
        if (a.maxSumGap > 1e-4) { std::fprintf(stderr, "FAIL: distributions do not sum to 1\n"); fail = 1; }
    }
    return fail;
}
