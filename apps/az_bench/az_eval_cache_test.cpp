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
// --ema LAM (RunConfig::searchEmaLambda): the net also gives an outcome distribution (dist) and F is that
// distribution's E[final floor] / 57; the HP weights are 0, so the utility is F alone. Then also: (1) the search with
// the search-backed distributions makes the same moves and the same samples (all other fields) as without them;
// (2) every sample's searchValue equals F of its search-backed distribution (the distribution is backed up exactly
// as the scalar); (3) distributions and targets sum to 1; (4) the cache returns the distributions too (the digest
// includes them).
//
// --ema-all: the EMA chain over all searched moves (default with --ema: full moves only).
//
// --ema-hp (RunConfig::searchEmaHp; needs --ema and --amber-search): the net also gives a floor HP distribution.
// Then also: (1) the same moves and samples (all other fields) as without it; (2) every sample has a floor HP target
// (8-bit fixed point, sum 1 up to the rounding) and, with --utility amber, per-floor targets in [0, 1] from its floor
// on and -1 before; (3) the cache returns the HP distributions too (the digest includes the targets); (4) the chains
// end in the real labels: replayed with lambda = 1 - 1e-9 every floor HP target is the one-hot of the sample's real
// hpEnd and every per-floor target its real hpFloor / 255.
//
// --compact (RunConfig::compactSamples): also plays the runs with compact samples (tokens in the run's dictionary)
// and checks that they are the same runs and the same samples, token for token (the digest reads the tokens through
// Sample::expandToken), that every compact sample refers to a dictionary and that the dictionaries hold fewer tokens
// than the samples do (the point of it).
//
// usage: az-eval-cache-test [--runs 3] [--seed-base 1] [--fast] [--utility amber] [--ema LAM] [--ema-all] [--ema-hp] [--amber-search] [--compact] [--root-target 1|2]
#include <algorithm>
#include <limits>
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
        double maxHpSumGap = 0;         // --ema-hp: max |sum - 1| of the floor HP target
        double maxHpRealGap = 0;        // --ema-hp: max distance of the HP targets from the real labels
        bool hpOk = true;               // --ema-hp: every sample has well-formed HP targets
        azbench::RunStats stats;
        std::size_t samples = 0;
        int batches = 0;
        std::size_t tokens = 0;        // tokens of all samples
        std::size_t dictTokens = 0;    // compact: tokens in the distinct dictionaries
        bool compactOk = true;         // compact: every sample refers to a dictionary (and has no copied tokens)
    };

    // --hp-nan-every N: about one fake-net row in N gives a NaN floor HP distribution (a search row that is no
    // distribution); the run driver skips such rows in the floor's EMA chain (STS_AZ_HP_TARGET_GUARD).
    int hpNanEvery = 0;

    // Plays cfg.maxRuns runs with a fake net that is a hash of each row's live input (and of the weights version
    // when versionPerBatch: the version is bumped before every batch).
    Result play(azbench::RunConfig cfg, bool versionPerBatch, bool distNet = false, int R = 8) {
        const int T = search::kAmberMaxTokens, A = search::kAmberMaxActions;
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
        std::vector<float> logits, F, ehp, hpf, dist, hpd;
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
            if (cfg.searchEmaHp) hpd.resize(static_cast<std::size_t>(B) * azbench::kHpClasses);
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
                if (cfg.searchEmaHp) {   // a peaked distribution around a hashed HP
                    float *p = hpd.data() + static_cast<std::size_t>(r) * azbench::kHpClasses;
                    const double c = 100.0 * unit(mix(h, 500));
                    double z = 0;
                    for (int k = 0; k < azbench::kHpClasses; ++k) { p[k] = static_cast<float>(std::exp(-0.02 * (k - c) * (k - c)) * (0.5 + unit(mix(h, 600 + k)))); z += p[k]; }
                    for (int k = 0; k < azbench::kHpClasses; ++k) p[k] = static_cast<float>(p[k] / z);
                    if (hpNanEvery > 0 && mix(h, 700) % static_cast<std::uint64_t>(hpNanEvery) == 0)   // a broken net row
                        std::fill(p, p + azbench::kHpClasses, std::numeric_limits<float>::quiet_NaN());
                }
            }
            d.submit(tickets.data(), B, An, logits.data(), F.data(), ehp.data(), amber ? hpf.data() : nullptr, version,
                     ema ? dist.data() : nullptr, cfg.searchEmaHp ? hpd.data() : nullptr);
            d.takeSamples(1 << 20, samples);
        }
        d.stop();
        d.takeSamples(1 << 20, samples);
        res.stats = d.stats();
        res.samples = samples.size();
        std::uint64_t h = 0;
        std::vector<const azbench::TokenDict *> seen;
        for (const auto &s : samples) {
            if (cfg.compactSamples) {
                res.compactOk = res.compactOk && s.dict && s.tokType.empty() && s.ids.empty() && s.f.empty();
                if (s.dict && std::find(seen.begin(), seen.end(), s.dict.get()) == seen.end()) {
                    seen.push_back(s.dict.get());
                    res.dictTokens += s.dict->size();
                }
            }
            res.tokens += s.numTokens();
            for (std::size_t t = 0; t < s.numTokens(); ++t) {
                std::int8_t type;
                const std::int16_t *id;
                const std::uint16_t *fv;
                s.expandToken(t, type, id, fv);
                h = mix(h, static_cast<std::uint8_t>(type));
                for (int c = 0; c < search::kAmberCat; ++c) h = mix(h, static_cast<std::uint16_t>(id[c]));
                for (int c = 0; c < search::kAmberFloat; ++c) h = mix(h, fv[c]);
            }
            for (std::size_t j = 0; j < s.aType.size(); ++j)
                h = mix(h, static_cast<std::uint64_t>(static_cast<std::uint16_t>(s.aSrc[j])) << 16 |
                               static_cast<std::uint16_t>(s.aTgt[j]));
            for (auto x : s.aF) h = mix(h, x);
            for (auto x : s.hpFloor) h = mix(h, static_cast<std::uint16_t>(x));
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
        for (const auto &s : samples) {
            if (!cfg.searchEmaHp) break;
            double sum = 0;
            for (auto q : s.hpTargetQ) sum += q / 255.0;
            const int lo = s.hpTargetLo, n = static_cast<int>(s.hpTargetQ.size());
            res.hpOk = res.hpOk && n > 0 && lo >= 0 && lo + n <= azbench::kHpClasses && s.hpTargetQ.front() && s.hpTargetQ.back();
            res.maxHpSumGap = std::max(res.maxHpSumGap, std::abs(sum - 1));
            // distance from the one-hot of the real HP at the end of the floor
            const int real = std::clamp<int>(s.hpEnd, 0, azbench::kHpClasses - 1);
            for (int k = 0; k < n; ++k)
                res.maxHpRealGap = std::max(res.maxHpRealGap, std::abs(s.hpTargetQ[k] / 255.0 - (lo + k == real ? 1.0 : 0.0)));
            if (n > 0 && (real < lo || real >= lo + n)) res.maxHpRealGap = 1;
            h = mix(h, static_cast<std::uint64_t>(lo));
            for (auto q : s.hpTargetQ) h = mix(h, q);
            if (amber) {
                res.hpOk = res.hpOk && s.hpFloorTarget.size() == static_cast<std::size_t>(azbench::kFloors) &&
                           s.hpFloor.size() == s.hpFloorTarget.size();
                if (!res.hpOk) break;
                const int fl = std::clamp<int>(s.floor, 1, azbench::kFloors);
                for (int f = 1; f <= azbench::kFloors; ++f) {
                    const float x = s.hpFloorTarget[f - 1];
                    res.hpOk = res.hpOk && (f < fl ? x == -1.f : (x >= 0.f && x <= 1.f)) && (f < fl) == (s.hpFloor[f - 1] < 0);
                    if (f >= fl) res.maxHpRealGap = std::max(res.maxHpRealGap, std::abs(x - std::clamp<int>(s.hpFloor[f - 1], 0, 255) / 255.0));
                    std::uint32_t u;
                    std::memcpy(&u, &x, 4);
                    h = mix(h, u);
                }
            }
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
    bool compact = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() { if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", a.c_str()); std::exit(2); } return std::string(argv[++i]); };
        if (a == "--runs") cfg.maxRuns = std::stoll(next());
        else if (a == "--seed-base") cfg.seedBase = std::stoull(next());
        else if (a == "--utility") { const std::string u = next(); if (u != "amber") { std::fprintf(stderr, "unknown utility %s\n", u.c_str()); return 2; } cfg.utility = azbench::Utility::AMBER; }
        else if (a == "--amber-search") cfg.chanceOnReveal = cfg.crossCombat = cfg.simHelp = true;
        else if (a == "--ema") { cfg.searchEmaLambda = std::stod(next()); cfg.hpWeightCombat = cfg.hpWeightOoc = 0; }
        else if (a == "--ema-all") cfg.searchEmaFullOnly = false;
        else if (a == "--ema-hp") cfg.searchEmaHp = true;
        else if (a == "--compact") compact = true;
        else if (a == "--hp-nan-every") hpNanEvery = std::stoi(next());
        else if (a == "--parallel-nodes") cfg.parallelNodes = std::stoi(next());
        else if (a == "--root-target") cfg.rootTarget = std::stoi(next());
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
    if (compact) {
        azbench::RunConfig cc = cfg;
        cc.compactSamples = true;
        const Result k = play(cc, false);
        std::printf("{\"compact\": {\"samples\": %zu, \"tokens\": %zu, \"dict_tokens\": %zu, \"digest\": \"%016llx\"}}\n",
                    k.samples, k.tokens, k.dictTokens, static_cast<unsigned long long>(k.digest));
        if (k.digest != a.digest || k.samples != a.samples || k.tokens != a.tokens || k.stats.moves != a.stats.moves) {
            std::fprintf(stderr, "FAIL: compact samples differ from copied ones\n");
            fail = 1;
        }
        if (!k.compactOk || k.dictTokens == 0 || k.dictTokens >= k.tokens) {
            std::fprintf(stderr, "FAIL: compact samples without a dictionary, or nothing shared\n");
            fail = 1;
        }
    }
    if (cfg.parallelNodes > 0) {
        // Parallel search nodes: waves of several evaluations per run, and the same games whether the answers come
        // one per batch or many (a wave's answers are handled together, in the order its simulations started).
        // The games differ from the one-at-a-time search's, so there is no digest to compare with it.
        const Result one = play(off, false, false, 1), many = play(off, false, false, 64);
        const double perWave = a.stats.waves ? static_cast<double>(a.stats.waveFlights) / a.stats.waves : 0;
        std::printf("{\"parallel_nodes\": {\"p\": %d, \"waves\": %lld, \"flights_per_wave\": %.2f, \"collisions\": %lld, "
                    "\"digest_batch1\": \"%016llx\", \"digest_batch64\": \"%016llx\"}}\n", cfg.parallelNodes,
                    static_cast<long long>(a.stats.waves), perWave, static_cast<long long>(a.stats.simCollisions),
                    static_cast<unsigned long long>(one.digest), static_cast<unsigned long long>(many.digest));
        if (one.digest != a.digest || many.digest != a.digest) {
            std::fprintf(stderr, "FAIL: parallel search nodes: the games depend on the batching of the answers\n");
            fail = 1;
        }
        if (perWave <= 1.0) { std::fprintf(stderr, "FAIL: parallel search nodes: no wave with several evaluations\n"); fail = 1; }
    } else if (a.stats.waves != 0 || a.stats.simCollisions != 0) {
        std::fprintf(stderr, "FAIL: waves without parallel search nodes\n");
        fail = 1;
    }
    if (cfg.searchEmaLambda > 0) {
        azbench::RunConfig plain = cfg;
        plain.searchEmaLambda = 0;
        plain.searchEmaHp = false;
        plain.rootTarget = 0;
        const Result p = play(plain, false, true);   // the same fake net, distributions not submitted
        std::printf("{\"ema\": {\"lambda\": %g, \"max_value_gap\": %.3g, \"max_sum_gap\": %.3g, \"full_only\": %d, \"base_digest\": \"%016llx\", "
                    "\"plain_digest\": \"%016llx\"}}\n", cfg.searchEmaLambda, a.maxValueGap, a.maxSumGap, cfg.searchEmaFullOnly ? 1 : 0,
                    static_cast<unsigned long long>(a.baseDigest), static_cast<unsigned long long>(p.baseDigest));
        if (p.baseDigest != a.baseDigest || p.samples != a.samples) {
            std::fprintf(stderr, "FAIL: the search-backed distributions changed the moves or samples\n");
            fail = 1;
        }
        // rootTarget != 0: searchDist is no longer the tree mean that the scalar searchValue is.
        if (cfg.rootTarget == 0 && a.maxValueGap > 1e-5) { std::fprintf(stderr, "FAIL: searchValue != F(searchDist)\n"); fail = 1; }
        // Targets come from float16 chain distributions (~1e-3 relative per term).
        if (a.maxSumGap > 5e-3) { std::fprintf(stderr, "FAIL: distributions do not sum to 1\n"); fail = 1; }
    }
    if (cfg.searchEmaHp) {
        azbench::RunConfig plain = cfg, real = cfg;
        plain.searchEmaHp = false;
        real.searchEmaLambda = 1.0 - 1e-9;   // the chains keep (almost) only their ends: the real labels
        const Result p = play(plain, false), r = play(real, false);
        std::printf("{\"ema_hp\": {\"samples\": %zu, \"max_sum_gap\": %.3g, \"real_gap\": %.3g, \"real_gap_lambda_1\": %.3g, "
                    "\"base_digest\": \"%016llx\", \"plain_digest\": \"%016llx\"}}\n", a.samples, a.maxHpSumGap,
                    a.maxHpRealGap, r.maxHpRealGap, static_cast<unsigned long long>(a.baseDigest),
                    static_cast<unsigned long long>(p.baseDigest));
        if (p.baseDigest != a.baseDigest || p.samples != a.samples) { std::fprintf(stderr, "FAIL: the HP search targets changed the moves or samples\n"); fail = 1; }
        if (!a.hpOk || !b.hpOk || !r.hpOk) { std::fprintf(stderr, "FAIL: a sample without well-formed HP targets\n"); fail = 1; }
        // 256 classes rounded to 1 / 255 each: the sum is 1 up to the rounding.
        if (a.maxHpSumGap > 0.1) { std::fprintf(stderr, "FAIL: floor HP targets do not sum to 1\n"); fail = 1; }
        if (r.baseDigest != a.baseDigest || r.maxHpRealGap > 1e-6) { std::fprintf(stderr, "FAIL: the HP chains do not end in the real labels\n"); fail = 1; }
        if (!(a.maxHpRealGap > 1e-3)) { std::fprintf(stderr, "FAIL: the HP targets are the real labels (no search in them)\n"); fail = 1; }
        std::printf("{\"hp_target_guard\": {\"nan_every\": %d, \"bad_rows\": %lld, \"fallbacks\": %lld}}\n", hpNanEvery,
                    static_cast<long long>(a.stats.hpTargetBadRows), static_cast<long long>(a.stats.hpTargetFallbacks));
        if ((hpNanEvery > 0) != (a.stats.hpTargetBadRows > 0)) { std::fprintf(stderr, "FAIL: skipped HP rows do not match the broken net rows\n"); fail = 1; }
        if (a.stats.hpTargetFallbacks != 0) { std::fprintf(stderr, "FAIL: an HP target fell back to the real HP\n"); fail = 1; }
    }
    if (cfg.rootTarget != 0) {
        // RunConfig::rootTarget: the same moves and samples as the tree reading, other targets.
        azbench::RunConfig tree = cfg;
        tree.rootTarget = 0;
        const Result t = play(tree, false);
        std::printf("{\"root_target\": {\"mode\": %d, \"base_digest\": \"%016llx\", \"tree_base_digest\": \"%016llx\", "
                    "\"digest\": \"%016llx\", \"tree_digest\": \"%016llx\", \"tree_value_gap\": %.3g, \"value_gap\": %.3g}}\n",
                    cfg.rootTarget, static_cast<unsigned long long>(a.baseDigest), static_cast<unsigned long long>(t.baseDigest),
                    static_cast<unsigned long long>(a.digest), static_cast<unsigned long long>(t.digest), t.maxValueGap, a.maxValueGap);
        if (t.baseDigest != a.baseDigest || t.samples != a.samples) { std::fprintf(stderr, "FAIL: rootTarget changed the moves or samples\n"); fail = 1; }
        if (t.digest == a.digest) { std::fprintf(stderr, "FAIL: rootTarget did not change the targets\n"); fail = 1; }
        if (!(a.maxValueGap > 1e-4)) { std::fprintf(stderr, "FAIL: rootTarget's searchDist is the tree mean\n"); fail = 1; }
    }
    return fail;
}
