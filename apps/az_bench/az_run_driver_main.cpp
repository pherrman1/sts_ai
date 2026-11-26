// Stage 1 whole-run self-play driver (az_run_driver.h) with a fake net, C++ only: plays runs to the end and checks the
// training samples (labels filled, policy a distribution over the sample's actions, action sources / targets inside
// the row). Smoke test and CPU-side throughput probe.
//
// usage: az-run-driver [--workers 2] [--games 4] [--runs 8] [--batch 64] [--seed 0] [--seed-base 1] [--fast] [--asc 20] [--sims N] [--const-value] [--test-hp HP] [--max-fight-moves 400] [--explore-c C] [--explore-amber] [--pick-target T] [--no-fast-noise] [--q-rescale] [--c-scale S] [--utility floor-hp|amber|amber2|amber2-root] [--keyless-hp] [--chance-on-reveal] [--cross-combat] [--sim-help] [--max-pending N] [--force-keys] [--savescum] [--compact-samples] [--parallel-nodes P] [--candidates C] [--aux-fights] [--enemy-tokens] [--consequences] [--stall-log PATH] [--death-log PATH] [--test-relic ENUM_NAME]...
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <random>
#include <string>
#include <vector>

#include "az_run_driver.h"

using namespace sts;

// --self-test-q: completedQValues against hand-computed Gumbel MuZero completed Q (mctx qtransform_completed_by_mix_value),
// and rootTargetWeights (RunConfig::rootTarget) on the same tree.
static int selfTestQ() {
    int fails = 0;
    auto near = [&](double a, double b, const char *what) {
        if (std::fabs(a - b) > 1e-9) { std::fprintf(stderr, "%s: %.12f != %.12f\n", what, a, b); ++fails; }
    };
    // Three edges, logits ln 1, ln 2, ln 1 (pi = .25 .5 .25); edge 0: n 2, q .6; edge 1: n 1, q .2; edge 2 unvisited.
    const float logit[3] = {0.f, static_cast<float>(std::log(2.0)), 0.f};
    const std::int32_t n[3] = {2, 1, 0};
    const double w[3] = {1.2, 0.2, 0};
    double q[3];
    azbench::completedQValues(3, logit, n, w, 0.5, false, q);   // raw: means, unvisited = node value
    near(q[0], 0.6, "raw q0"); near(q[1], 0.2, "raw q1"); near(q[2], 0.5, "raw q2");
    azbench::completedQValues(3, logit, n, w, 0.5, true, q);
    // v_mix = (0.5 + 3 * (.25 * .6 + .5 * .2) / .75) / 4 = (0.5 + 1) / 4 = 0.375; rescale over {.6, .2, .375}.
    near(q[0], 1.0, "mix q0"); near(q[1], 0.0, "mix q1"); near(q[2], (0.375 - 0.2) / 0.4, "mix q2");
    // Scale invariance: the same Q gaps at 1/100 the size (an out-of-combat root) give the same rescaled values.
    const double w2[3] = {2 * (0.5 + 0.006), 1 * (0.5 + 0.002), 0};
    azbench::completedQValues(3, logit, n, w2, 0.5 + 0.005, true, q);
    // Q = .5 + .01 x (first case's Q) for every value: v_mix = .50375 and the rescaled values equal the first case's.
    near(q[0], 1.0, "small q0"); near(q[1], 0.0, "small q1"); near(q[2], (0.375 - 0.2) / 0.4, "small q2");
    // No visits: every edge = node value, range floored -> all 0. Equal visited values -> all 0.
    const std::int32_t n0[3] = {0, 0, 0};
    azbench::completedQValues(3, logit, n0, w, 0.7, true, q);
    near(q[0], 0.0, "novisit q0"); near(q[2], 0.0, "novisit q2");
    azbench::completedQValues(3, logit, n0, w, 0.7, false, q);
    near(q[1], 0.7, "novisit raw q1");
    // rootTargetWeights (RunConfig::rootTarget) on the same three edges; improved policy pi' = .5 .3 .2.
    const double pi[3] = {0.5, 0.3, 0.2};
    double wE[3], wR = 0;
    azbench::rootTargetWeights(3, logit, n, pi, 1, 0, true, wE, wR);   // tree: n / (1 + sum n), 1 / (1 + sum n)
    near(wE[0], 0.5, "tree w0"); near(wE[1], 0.25, "tree w1"); near(wE[2], 0.0, "tree w2"); near(wR, 0.25, "tree root");
    // policy, rescale: edge 2's .2 goes to vMix = (D_root + 3 (.25 D0 + .5 D1) / .75) / 4 = .25 D_root + .25 D0 + .5 D1.
    azbench::rootTargetWeights(3, logit, n, pi, 1, 1, true, wE, wR);
    near(wE[0], 0.5 + 0.2 * 0.25, "policy w0"); near(wE[1], 0.3 + 0.2 * 0.5, "policy w1"); near(wE[2], 0.0, "policy w2");
    near(wR, 0.2 * 0.25, "policy root");
    // Applied to values: the D_i = Q_i, D_root = .5 case gives sum pi' q_completed with the unrescaled vMix .375.
    near(wE[0] * 0.6 + wE[1] * 0.2 + wR * 0.5, 0.5 * 0.6 + 0.3 * 0.2 + 0.2 * 0.375, "policy value");
    azbench::rootTargetWeights(3, logit, n, pi, 1, 1, false, wE, wR);   // no rescale: unvisited -> root evaluation
    near(wE[0], 0.5, "policy raw w0"); near(wE[1], 0.3, "policy raw w1"); near(wR, 0.2, "policy raw root");
    azbench::rootTargetWeights(3, logit, n, pi, 1, 2, true, wE, wR);   // pick edge 1: its mean only
    near(wE[0], 0.0, "pick w0"); near(wE[1], 1.0, "pick w1"); near(wE[2], 0.0, "pick w2"); near(wR, 0.0, "pick root");
    azbench::rootTargetWeights(3, logit, n, pi, 2, 2, true, wE, wR);   // pick unvisited edge 2: vMix
    near(wE[0], 0.25, "pick2 w0"); near(wE[1], 0.5, "pick2 w1"); near(wR, 0.25, "pick2 root");
    azbench::rootTargetWeights(3, logit, n0, pi, 0, 1, true, wE, wR);   // no visits: all to the root evaluation
    near(wE[0] + wE[1] + wE[2], 0.0, "novisit policy edges"); near(wR, 1.0, "novisit policy root");
    std::printf("completed-Q self test: %s\n", fails ? "FAIL" : "ok");
    return fails ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "--self-test-q") == 0) return selfTestQ();
    azbench::RunConfig cfg;
    cfg.workers = 2;
    cfg.gamesPerWorker = 4;
    cfg.maxRuns = 8;
    cfg.keepFast = 0.2;
    int batch = 64;
    double maxSeconds = 600;
    std::string deathLogPath;   // --death-log: one JSON line per finished run (RunConfig::deathLog)
    std::string stallLogPath;   // --stall-log: one JSON line per stalled run (RunConfig::stallLog)
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
        else if (a == "--test-relic") {   // tests only, repeatable: a relic (RelicId enum name) at each run's start
            const std::string name = next();
            int id = -1;
            for (int r = 0; r < static_cast<int>(RelicId::INVALID); ++r)
                if (name == relicEnumNames[r]) id = r;
            if (id < 0) { std::fprintf(stderr, "--test-relic: unknown relic %s\n", name.c_str()); return 2; }
            cfg.testRelics.push_back(static_cast<RelicId>(id));
        }
        else if (a == "--max-fight-moves") cfg.maxMovesPerFight = std::stoi(next());
        else if (a == "--explore-c") cfg.exploreC = std::stod(next());
        else if (a == "--pick-target") cfg.pickTarget = std::stod(next());
        else if (a == "--explore-amber") cfg.exploreAmber = true;
        else if (a == "--explore-per-offer") cfg.explorePerOffer = true;
        else if (a == "--explore-gap-search") cfg.exploreGapSearch = true;
        else if (a == "--explore-deck-only") cfg.exploreDeckOnly = true;
        else if (a == "--explore-clean-keys") cfg.exploreCleanKeys = true;
        else if (a == "--no-fast-noise") cfg.fastNoise = false;
        else if (a == "--q-rescale") cfg.qRescale = true;
        else if (a == "--c-scale") cfg.cScale = std::stod(next());
        else if (a == "--asc") cfg.ascension = std::stoi(next());
        else if (a == "--utility") {
            const std::string u = next();
            if (u == "amber") cfg.utility = azbench::Utility::AMBER;
            else if (u == "amber2") cfg.utility = azbench::Utility::AMBER2;
            else if (u == "amber2-root") cfg.utility = azbench::Utility::AMBER2_ROOT;
            else if (u == "floor-hp") cfg.utility = azbench::Utility::FLOOR_HP;
            else { std::fprintf(stderr, "--utility floor-hp|amber|amber2|amber2-root\n"); return 2; }
        }
        else if (a == "--keyless-hp") cfg.keylessHp = true;
        else if (a == "--chance-on-reveal") cfg.chanceOnReveal = true;
        else if (a == "--cross-combat") cfg.crossCombat = true;
        else if (a == "--sim-help") cfg.simHelp = true;
        else if (a == "--compact-samples") cfg.compactSamples = true;
        else if (a == "--max-pending") cfg.maxPendingSamples = std::stoll(next());
        else if (a == "--force-keys") cfg.forceKeys = true;
        else if (a == "--force-rewards") cfg.forceRewards = true;
        else if (a == "--rng-fix") cfg.rngFix = true;
        else if (a == "--aux-fights") cfg.auxFights = true;
        else if (a == "--enemy-tokens") cfg.enemyTokens = true;
        else if (a == "--consequences") cfg.consequences = true;
        else if (a == "--stall-log") { stallLogPath = next(); cfg.stallLog = true; }
        else if (a == "--death-log") { deathLogPath = next(); cfg.deathLog = true; }
        else if (a == "--force-potions") cfg.forcePotions = true;
        else if (a == "--ooc-canon") cfg.oocCanon = true;
        else if (a == "--savescum") cfg.savescum = true;
        else if (a == "--eval-cache") cfg.evalCache = true;
        else if (a == "--eval-cache-cap") cfg.evalCacheCap = std::stoi(next());
        else if (a == "--eval-cache-gen") cfg.evalCacheGen = true;
        else if (a == "--parallel-nodes") cfg.parallelNodes = std::stoi(next());
        else if (a == "--sims") { cfg.fullSims = std::stoi(next()); cfg.fastSims = cfg.fullSims; cfg.fullProb = 1.0; }
        else if (a == "--candidates") { cfg.fullCandidates = std::stoi(next()); cfg.fastCandidates = std::max(1, cfg.fullCandidates / 2); }
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
    std::vector<float> logits, F, ehp, hpf;
    const bool amber = azbench::usesAmberH(cfg.utility);
    const bool needDist = azbench::isAmber2(cfg.utility) || cfg.searchEmaLambda > 0;
    std::vector<float> dist;
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
        if (amber) {
            hpf.resize(static_cast<std::size_t>(B) * azbench::kFloors);
            for (auto &x : hpf) x = constValue ? 0.f : 0.3f * U(rng);
        }
        if (needDist) {   // a random outcome softmax per row (class 0 = win)
            dist.resize(static_cast<std::size_t>(B) * azbench::kOutcomeClasses);
            for (int r = 0; r < B; ++r) {
                float sum = 0;
                for (int k = 0; k < azbench::kOutcomeClasses; ++k) sum += (dist[r * azbench::kOutcomeClasses + k] = U(rng));
                for (int k = 0; k < azbench::kOutcomeClasses; ++k) dist[r * azbench::kOutcomeClasses + k] /= sum;
            }
        }
        d.submit(tickets.data(), B, shape.actions, logits.data(), F.data(), ehp.data(), amber ? hpf.data() : nullptr, 0,
                 needDist ? dist.data() : nullptr);
        d.takeSamples(1 << 20, samples);
    }
    d.stop();
    d.takeSamples(1 << 20, samples);
    const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    const auto s = d.stats();

    int bad = 0, withPolicy = 0, combat = 0;
    long long auxRows = 0, auxSamples = 0;
    for (const auto &x : samples) {
        const int n = static_cast<int>(x.numTokens()), na = static_cast<int>(x.aType.size());
        bool ok = x.outcome >= 0 && x.outcome < azbench::kOutcomeClasses && x.hpEnd >= 0 && n >= 1 && na >= 2;
        if (cfg.compactSamples) {   // tokens only in the run's dictionary, every index inside it
            ok = ok && x.dict && x.tokType.empty() && x.ids.empty() && x.f.empty();
            for (int t = 0; ok && t < n; ++t) ok = x.tokIdx[t] < x.dict->size();
            ok = ok && x.dict->ids.size() == x.dict->size() * search::kAmberCat &&
                 x.dict->f.size() == x.dict->size() * search::kAmberFloat;
        } else {
            ok = ok && !x.dict && x.ids.size() == static_cast<std::size_t>(n) * search::kAmberCat &&
                 x.f.size() == static_cast<std::size_t>(n) * search::kAmberFloat;
        }
        for (int j = 0; j < na; ++j) ok = ok && x.aSrc[j] >= -1 && x.aSrc[j] < n && x.aTgt[j] >= -1 && x.aTgt[j] < n;
        // Per-floor HP labels (utility AMBER only): masked (-1) exactly before the sample's floor, >= 0 from it on,
        // the sample's own floor equal to its hp_end label, and 0 after a death's floor.
        if (amber) {
            const int fl = std::clamp<int>(x.floor, 1, azbench::kFloors);
            ok = ok && x.hpFloor.size() == static_cast<std::size_t>(azbench::kFloors);
            for (int f = 1; ok && f <= azbench::kFloors; ++f) ok = (f < fl) == (x.hpFloor[f - 1] < 0);
            if (ok && x.floor >= 1) ok = x.hpFloor[fl - 1] == x.hpEnd;
            if (ok && x.outcome > 0)
                for (int f = std::max(fl, static_cast<int>(x.outcome)) + 1; f <= azbench::kFloors; ++f) ok = ok && x.hpFloor[f - 1] == 0;
        } else {
            ok = ok && x.hpFloor.empty();
        }
        if (!x.policy.empty()) {
            ++withPolicy;
            double sum = 0;
            for (float p : x.policy) { ok = ok && p >= 0.f; sum += p; }
            ok = ok && static_cast<int>(x.policy.size()) == na && std::fabs(sum - 1.0) < 1e-3;
        }
        // Fight starts (auxFights, out-of-combat samples only): offsets match the slots, slots ascending in 0..4 with
        // at most kAuxHallway hallway fights, every row has tokens, compact rows index their sample's dictionary.
        {
            const std::size_t k = x.auxSlot.size();
            if (!cfg.auxFights || x.combat) {
                ok = ok && k == 0 && x.auxTokOff.empty() && x.auxTokIdx.empty() && x.auxTokType.empty();
            } else {
                ok = ok && k >= 1 && x.auxTokOff.size() == k + 1 && x.auxTokOff[0] == 0;
                int hall = 0;
                for (std::size_t r = 0; ok && r < k; ++r) {
                    ok = x.auxSlot[r] < azbench::kAuxSlots && (r == 0 || x.auxSlot[r] >= x.auxSlot[r - 1]) &&
                         x.auxTokOff[r + 1] > x.auxTokOff[r];
                    hall += x.auxSlot[r] == 4;
                }
                ok = ok && hall <= azbench::kAuxHallway;
                const std::size_t nt = cfg.compactSamples ? x.auxTokIdx.size() : x.auxTokType.size();
                ok = ok && x.auxTokOff[k] == nt;
                if (cfg.compactSamples) for (auto t : x.auxTokIdx) ok = ok && t < x.dict->size();
                else ok = ok && x.auxIds.size() == nt * search::kAmberCat && x.auxF.size() == nt * search::kAmberFloat;
                // the first row of a sample is a fight against its act's boss: a MONSTER token in the row
                bool monster = false;
                for (std::uint32_t t = 0; ok && t < x.auxTokOff[1]; ++t) {
                    const int ty = cfg.compactSamples ? x.dict->tokType[x.auxTokIdx[t]] : x.auxTokType[t];
                    monster = monster || ty == static_cast<int>(search::AmberTokenType::MONSTER);
                }
                ok = ok && monster;
                auxRows += static_cast<long long>(k);
                ++auxSamples;
            }
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
    if (cfg.evalCache)
        std::printf("eval_cache: hits %lld evals %lld hit_rate %.1f %%\n", static_cast<long long>(s.cacheHits),
                    static_cast<long long>(s.evals), 100.0 * s.cacheHits / std::max<std::int64_t>(1, s.cacheHits + s.evals));
    std::printf("stalls by type: fight_moves %lld run_moves %lld no_legal %lld; fights ended at start %lld\n",
                static_cast<long long>(s.stallsByType[0]), static_cast<long long>(s.stallsByType[1]),
                static_cast<long long>(s.stallsByType[2]), static_cast<long long>(s.fightsEndedAtStart));
    if (cfg.stallLog) {
        std::ofstream out(stallLogPath);
        std::size_t n = 0;
        for (const auto &r : d.takeStallLogs()) { out << azbench::stallLogJson(r) << '\n'; ++n; }
        std::printf("stall log: %zu records -> %s\n", n, stallLogPath.c_str());
    }
    if (cfg.deathLog) {
        std::ofstream out(deathLogPath);
        std::size_t n = 0, losses = 0;
        for (const auto &r : d.takeDeathLogs()) {
            out << azbench::deathLogJson(r) << '\n';
            ++n;
            losses += r.result == 0 ? 1 : 0;
        }
        std::printf("death log: %zu records (%zu losses) -> %s\n", n, losses, deathLogPath.c_str());
    }
    std::printf("memory: pool_nodes %lld pool_gc %lld pool_bc %lld pool_real %lld pool_outer %lld edge_cap %lld "
                "pending_cap %lld move_dist_cap %lld cache_entries %lld done %lld\n",
                static_cast<long long>(s.memPoolNodes), static_cast<long long>(s.memPoolGc),
                static_cast<long long>(s.memPoolBc),
                static_cast<long long>(s.memPoolReal), static_cast<long long>(s.memPoolOuter),
                static_cast<long long>(s.memEdgeCap),
                static_cast<long long>(s.memPendingCap), static_cast<long long>(s.memMoveDistCap),
                static_cast<long long>(s.memCacheEntries), static_cast<long long>(s.memDone));
    if (cfg.parallelNodes > 0) {
        // Round trips to the net per searched move: its root evaluation and its waves (one-at-a-time: one per
        // evaluation).
        const double sm = static_cast<double>(std::max<long long>(1, s.searchedMoves));
        std::printf("parallel_nodes %d: waves %lld, flights_per_wave %.2f, round_trips_per_move %.2f (evals_per_move %.2f), "
                    "collisions %lld, flight_slots %lld\n", cfg.parallelNodes, static_cast<long long>(s.waves),
                    s.waves ? static_cast<double>(s.waveFlights) / s.waves : 0.0, (s.searchedMoves + s.waves) / sm,
                    s.evals / sm, static_cast<long long>(s.simCollisions), static_cast<long long>(s.memFlights));
        if (s.waves == 0 || s.waveFlights <= s.waves) { std::fprintf(stderr, "parallel nodes: no wave with several evaluations\n"); return 1; }
    }
    if (cfg.auxFights) {
        std::printf("aux fights: %lld rows over %lld out-of-combat samples (stats %lld)\n", auxRows, auxSamples,
                    static_cast<long long>(s.auxFights));
        if (auxSamples == 0 || auxRows != s.auxFights) { std::fprintf(stderr, "aux fights: missing rows\n"); return 1; }
    }
    std::printf("outcomes (class: runs):");
    for (int k = 0; k < azbench::kOutcomeClasses; ++k)
        if (s.outcomes[k]) std::printf(" %d:%lld", k, static_cast<long long>(s.outcomes[k]));
    std::printf("\n");
    if (timedOut) { std::fprintf(stderr, "timed out before %lld runs finished\n", static_cast<long long>(cfg.maxRuns)); return 1; }
    std::printf("pick-rate exploration: ooc_roots %lld explore_roots %lld forced_picks %lld\n",
                static_cast<long long>(s.oocRoots), static_cast<long long>(s.exploreRoots),
                static_cast<long long>(s.forcedPicks));
    std::printf("ooc search [full, fast]: searched %lld %lld not_best_q %lld %lld q_spread_mean %.5f %.5f\n",
                static_cast<long long>(s.oocSearched[0]), static_cast<long long>(s.oocSearched[1]),
                static_cast<long long>(s.oocNotBestQ[0]), static_cast<long long>(s.oocNotBestQ[1]),
                s.oocSpreadSum[0] / std::max<std::int64_t>(1, s.oocSpreadN[0]),
                s.oocSpreadSum[1] / std::max<std::int64_t>(1, s.oocSpreadN[1]));
    std::printf("amber search: ooc_edges deterministic %lld chance %lld tree_fight_starts %lld tree_fight_exits %lld "
                "auto_gold %lld\n",
                static_cast<long long>(s.oocEdgeKinds[0]), static_cast<long long>(s.oocEdgeKinds[1]),
                static_cast<long long>(s.treeFightStarts), static_cast<long long>(s.treeFightExits),
                static_cast<long long>(s.autoGold));
    azbench::RunProgress prog;
    for (const auto &p : s.progressAsc) prog += p;
    const std::int64_t forced = s.forcedKeys[0] + s.forcedKeys[1] + s.forcedKeys[2];
    std::printf("key backstops: forced sapphire %lld ruby %lld emerald %lld route_masked %lld; runs with all keys %lld "
                "act4 %lld keyless_victories %lld (no sapphire %lld ruby %lld emerald %lld; hungry face %lld)\n",
                static_cast<long long>(s.forcedKeys[0]), static_cast<long long>(s.forcedKeys[1]),
                static_cast<long long>(s.forcedKeys[2]), static_cast<long long>(s.keyRouteMasked),
                static_cast<long long>(prog.allKeys), static_cast<long long>(prog.act4),
                static_cast<long long>(prog.keylessVictories), static_cast<long long>(prog.keylessNoSapphire),
                static_cast<long long>(prog.keylessNoRuby), static_cast<long long>(prog.keylessNoEmerald),
                static_cast<long long>(prog.keylessHungryFace));
    if (bad || s.invalidActions || samples.empty() || s.runsDone < cfg.maxRuns) return 1;
    // The key backstops must be inert when off; when on they must act, and a run past the Act-3 boss holds all keys
    // (the treasure row and the last campfire are on every route, the route keeps the burning elite reachable).
    if (!cfg.forceKeys && (forced != 0 || s.keyRouteMasked != 0)) return 1;
    if (cfg.forceKeys && (forced == 0 || prog.keylessVictories != 0)) return 1;
    // Forced rewards: inert when off; when on, chests are opened and no relic left outside the reviewed list.
    std::printf("forced rewards: chests %lld relics %lld deferred %lld on_leave %lld; chests_skipped %lld (cursed_key %lld) "
                "relics_left elite %lld chest %lld other %lld\n",
                static_cast<long long>(s.forcedRewards[0]), static_cast<long long>(s.forcedRewards[1]),
                static_cast<long long>(s.rewardRelicDeferred), static_cast<long long>(s.rewardRelicOnLeave),
                static_cast<long long>(prog.chestsSkipped), static_cast<long long>(prog.chestsSkippedCursedKey),
                static_cast<long long>(prog.relicsLeftElite),
                static_cast<long long>(prog.relicsLeftChest), static_cast<long long>(prog.relicsLeftOther));
    if (!cfg.forceRewards && (s.forcedRewards[0] + s.forcedRewards[1] + s.rewardRelicDeferred + s.rewardRelicOnLeave) != 0)
        return 1;
    // A chest may be skipped only with Cursed Key (forcedRewardActions leaves that choice open).
    if (cfg.forceRewards && (s.forcedRewards[1] == 0 || prog.chestsSkipped != prog.chestsSkippedCursedKey)) return 1;
    // Reward potions and duplicate card selections: inert when off, acting when on.
    std::printf("force potions: %lld; ooc canon: screens %lld removed %lld\n",
                static_cast<long long>(s.forcedPotions), static_cast<long long>(s.oocCanonScreens),
                static_cast<long long>(s.oocCanonRemoved));
    if (cfg.forcePotions != (s.forcedPotions > 0)) return 1;
    if (cfg.oocCanon != (s.oocCanonScreens > 0) || s.oocCanonRemoved < s.oocCanonScreens) return 1;
    // The Amber rules must act when on and be inert when off.
    // savescum replaces the chance rule (no edge is tested or resampled).
    const bool reveal = cfg.chanceOnReveal && !cfg.savescum;
    if (reveal != (s.oocEdgeKinds[0] + s.oocEdgeKinds[1] > 0)) return 1;
    if (reveal && (s.oocEdgeKinds[0] == 0 || s.oocEdgeKinds[1] == 0)) return 1;
    // savescum: every run plays it, and the search's child of each played action is the real next decision state.
    std::printf("savescum: runs %lld checks %lld mismatches %lld\n", static_cast<long long>(s.savescumRuns),
                static_cast<long long>(s.savescumChecks), static_cast<long long>(s.savescumMismatches));
    if (cfg.savescum && (s.savescumRuns != s.runsStarted || s.savescumChecks == 0 || s.savescumMismatches != 0)) return 1;
    if (!cfg.savescum && (s.savescumRuns != 0 || s.savescumChecks != 0)) return 1;
    if (cfg.crossCombat != (s.treeFightStarts > 0 && s.treeFightExits > 0)) return 1;
    if (cfg.simHelp != (s.autoGold > 0)) return 1;
    const bool explore = cfg.exploreC > 0 || cfg.exploreAmber;
    if (cfg.exploreAmber)
        std::printf("amber exploration: attempts %lld c0 %lld cinf %lld natural %lld natural_unplayed %lld moves %lld\n",
                    static_cast<long long>(s.exploreAttempts), static_cast<long long>(s.exploreCZero),
                    static_cast<long long>(s.exploreCInf), static_cast<long long>(s.exploreNatural),
                    static_cast<long long>(s.exploreNaturalUnplayed), static_cast<long long>(s.moves));
    if (cfg.exploreAmber) {
        static const char *kCls[8] = {"card", "deck_edit", "relic", "potion", "event", "rest", "other_option",
                                      "other"};
        std::int64_t fSum = 0, aSum = 0;
        std::printf("amber exploration by class (attempts/forced):");
        for (int k = 0; k < 8; ++k) {
            std::printf(" %s %lld/%lld", kCls[k], static_cast<long long>(s.exploreAttemptsByClass[k]),
                        static_cast<long long>(s.forcedByClass[k]));
            fSum += s.forcedByClass[k]; aSum += s.exploreAttemptsByClass[k];
        }
        std::printf("\n");
        if (fSum != s.forcedPicks || aSum != s.exploreAttempts) return 1;   // the classes partition the totals
        if (cfg.exploreDeckOnly && (s.exploreAttemptsByClass[1] + s.exploreAttemptsByClass[4] + s.exploreAttemptsByClass[5]
                                    + s.exploreAttemptsByClass[6] + s.exploreAttemptsByClass[7]) != 0) return 1;
    }
    if (s.exploreNaturalUnplayed != 0) return 1;   // an item logged as picked by the search must have been played
    if (explore && (s.forcedPicks == 0 || s.exploreRoots == 0)) return 1;   // exploration must act
    if (!explore && (s.forcedPicks != 0 || s.exploreRoots != 0)) return 1;  // ... and be inert when off
    return 0;
}
