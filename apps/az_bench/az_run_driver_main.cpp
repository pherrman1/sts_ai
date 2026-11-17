// Stage 1 whole-run self-play driver (az_run_driver.h) with a fake net, C++ only: plays runs to the end and checks the
// training samples (labels filled, policy a distribution over the sample's actions, action sources / targets inside
// the row). Smoke test and CPU-side throughput probe.
//
// usage: az-run-driver [--workers 2] [--games 4] [--runs 8] [--batch 64] [--seed 0] [--seed-base 1] [--fast] [--asc 20] [--sims N] [--const-value] [--test-hp HP] [--max-fight-moves 400]
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "az_run_driver.h"

using namespace sts;

int main(int argc, char **argv) {
    azbench::RunConfig cfg;
    cfg.workers = 2;
    cfg.gamesPerWorker = 4;
    cfg.maxRuns = 8;
    cfg.keepFast = 0.2;
    int batch = 64;
    double maxSeconds = 600;
    bool constValue = false;   // F = 0.5, no HP: only terminal leaves steer the search
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() { if (i + 1 >= argc) { std::fprintf(stderr, "missing value for %s\n", a.c_str()); std::exit(2); } return std::string(argv[++i]); };
        if (a == "--workers") cfg.workers = std::stoi(next());
        else if (a == "--games") cfg.gamesPerWorker = std::stoi(next());
        else if (a == "--runs") cfg.maxRuns = std::stoll(next());
        else if (a == "--batch") batch = std::stoi(next());
        else if (a == "--seed") cfg.searchSeed = std::stoull(next());
        else if (a == "--seed-base") cfg.seedBase = std::stoull(next());
        else if (a == "--seconds") maxSeconds = std::stod(next());
        else if (a == "--const-value") constValue = true;
        else if (a == "--test-hp") cfg.testMaxHp = std::stoi(next());
        else if (a == "--max-fight-moves") cfg.maxMovesPerFight = std::stoi(next());
        else if (a == "--asc") cfg.ascension = std::stoi(next());
        else if (a == "--sims") { cfg.fullSims = std::stoi(next()); cfg.fastSims = cfg.fullSims; cfg.fullProb = 1.0; }
        else if (a == "--fast") { cfg.fullSims = 8; cfg.fastSims = 4; cfg.fullCandidates = 4; cfg.fastCandidates = 2; }
        else { std::fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
    }
    if (cfg.maxRuns < 0) { std::fprintf(stderr, "--runs must be >= 0\n"); return 2; }

    const int T = search::kAmberMaxTokens, A = search::kAmberMaxActions, R = batch;
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
    const auto t0 = std::chrono::steady_clock::now();
    bool timedOut = false;
    while (d.stats().runsDone < cfg.maxRuns) {
        if (std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count() > maxSeconds) {
            timedOut = true;
            break;
        }
        azbench::FlatShape shape;
        const auto tickets = d.nextBatchFlat(batch, 1, 5, {}, {}, {}, fb, shape, 1);
        if (tickets.empty()) continue;
        const int B = shape.rows;
        logits.assign(static_cast<std::size_t>(B) * shape.actions, 0.f);
        F.resize(B);
        ehp.resize(B);
        for (auto &x : logits) x = U(rng);
        for (int r = 0; r < B; ++r) { F[r] = constValue ? 0.5f : U(rng); ehp[r] = constValue ? 0.f : 80.f * U(rng); }
        d.submit(tickets.data(), B, shape.actions, logits.data(), F.data(), ehp.data());
        d.takeSamples(1 << 20, samples);
    }
    d.stop();
    d.takeSamples(1 << 20, samples);
    const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    const auto s = d.stats();

    int bad = 0, withPolicy = 0, combat = 0;
    for (const auto &x : samples) {
        const int n = static_cast<int>(x.tokType.size()), na = static_cast<int>(x.aType.size());
        bool ok = x.outcome >= 0 && x.outcome < azbench::kOutcomeClasses && x.hpEnd >= 0 && n >= 1 && na >= 2 &&
                  x.ids.size() == static_cast<std::size_t>(n) * search::kAmberCat &&
                  x.f.size() == static_cast<std::size_t>(n) * search::kAmberFloat;
        for (int j = 0; j < na; ++j) ok = ok && x.aSrc[j] >= -1 && x.aSrc[j] < n && x.aTgt[j] >= -1 && x.aTgt[j] < n;
        if (!x.policy.empty()) {
            ++withPolicy;
            double sum = 0;
            for (float p : x.policy) { ok = ok && p >= 0.f; sum += p; }
            ok = ok && static_cast<int>(x.policy.size()) == na && std::fabs(sum - 1.0) < 1e-3;
        }
        combat += x.combat;
        if (!ok) ++bad;
    }
    std::printf("{\"runs_done\": %lld, \"wins\": %lld, \"mean_floor\": %.2f, \"moves\": %lld, \"searched_moves\": %lld, "
                "\"evals\": %lld, \"evals_per_s\": %.0f, \"samples\": %zu, \"samples_policy\": %d, \"samples_combat\": %d, "
                "\"bad_samples\": %d, \"stalls\": %lld, \"unsupported\": %lld, \"knowledge_failures\": %lld, \"invalid_actions\": %lld, \"encode_cut\": %lld, \"encode_cut_ooc\": %lld, "
                "\"terminal_leaves\": %lld, \"seconds\": %.1f}\n",
                static_cast<long long>(s.runsDone), static_cast<long long>(s.wins),
                s.runsDone ? static_cast<double>(s.floorsSum) / s.runsDone : 0.0, static_cast<long long>(s.moves),
                static_cast<long long>(s.searchedMoves), static_cast<long long>(s.evals), s.evals / secs,
                samples.size(), withPolicy, combat, bad, static_cast<long long>(s.stalls),
                static_cast<long long>(s.unsupported), static_cast<long long>(s.knowledgeFailures), static_cast<long long>(s.invalidActions), static_cast<long long>(s.encodeCut), static_cast<long long>(s.encodeCutOoc),
                static_cast<long long>(s.terminalLeaves), secs);
    std::printf("outcomes (class: runs):");
    for (int k = 0; k < azbench::kOutcomeClasses; ++k)
        if (s.outcomes[k]) std::printf(" %d:%lld", k, static_cast<long long>(s.outcomes[k]));
    std::printf("\n");
    if (timedOut) { std::fprintf(stderr, "timed out before %lld runs finished\n", static_cast<long long>(cfg.maxRuns)); return 1; }
    if (bad || s.invalidActions || samples.empty() || s.runsDone < cfg.maxRuns) return 1;
    return 0;
}
