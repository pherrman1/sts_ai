// Stage 1 whole-run self-play driver (az_run_driver.h) with a fake net, C++ only: plays runs to the end and checks the
// training samples (labels filled, policy a distribution over the sample's actions, action sources / targets inside
// the row). Smoke test and CPU-side throughput probe.
//
// usage: az-run-driver [--workers 2] [--games 4] [--runs 8] [--batch 64] [--seed 0] [--seed-base 1] [--fast] [--asc 20] [--sims N] [--const-value] [--test-hp HP] [--max-fight-moves 400] [--explore-c C] [--explore-amber] [--pick-target T] [--no-fast-noise] [--q-rescale] [--c-scale S] [--utility floor-hp|amber] [--keyless-hp] [--chance-on-reveal] [--cross-combat] [--sim-help] [--max-pending N] [--force-keys] [--savescum] [--compact-samples]
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

// --self-test-q: completedQValues against hand-computed Gumbel MuZero completed Q (mctx qtransform_completed_by_mix_value).
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
        else if (a == "--explore-c") cfg.exploreC = std::stod(next());
        else if (a == "--pick-target") cfg.pickTarget = std::stod(next());
        else if (a == "--explore-amber") cfg.exploreAmber = true;
        else if (a == "--no-fast-noise") cfg.fastNoise = false;
        else if (a == "--q-rescale") cfg.qRescale = true;
        else if (a == "--c-scale") cfg.cScale = std::stod(next());
        else if (a == "--asc") cfg.ascension = std::stoi(next());
        else if (a == "--utility") {
            const std::string u = next();
            if (u == "amber") cfg.utility = azbench::Utility::AMBER;
            else if (u == "floor-hp") cfg.utility = azbench::Utility::FLOOR_HP;
            else { std::fprintf(stderr, "--utility floor-hp|amber\n"); return 2; }
        }
        else if (a == "--keyless-hp") cfg.keylessHp = true;
        else if (a == "--chance-on-reveal") cfg.chanceOnReveal = true;
        else if (a == "--cross-combat") cfg.crossCombat = true;
        else if (a == "--sim-help") cfg.simHelp = true;
        else if (a == "--compact-samples") cfg.compactSamples = true;
        else if (a == "--max-pending") cfg.maxPendingSamples = std::stoll(next());
        else if (a == "--force-keys") cfg.forceKeys = true;
        else if (a == "--savescum") cfg.savescum = true;
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
    std::vector<float> logits, F, ehp, hpf;
    const bool amber = cfg.utility == azbench::Utility::AMBER;
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
        d.submit(tickets.data(), B, shape.actions, logits.data(), F.data(), ehp.data(), amber ? hpf.data() : nullptr);
        d.takeSamples(1 << 20, samples);
    }
    d.stop();
    d.takeSamples(1 << 20, samples);
    const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    const auto s = d.stats();

    int bad = 0, withPolicy = 0, combat = 0;
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
    std::printf("memory: pool_nodes %lld pool_gc %lld pool_real %lld pool_outer %lld edge_cap %lld pending_cap %lld move_dist_cap %lld "
                "cache_entries %lld done %lld\n",
                static_cast<long long>(s.memPoolNodes), static_cast<long long>(s.memPoolGc),
                static_cast<long long>(s.memPoolReal), static_cast<long long>(s.memPoolOuter),
                static_cast<long long>(s.memEdgeCap),
                static_cast<long long>(s.memPendingCap), static_cast<long long>(s.memMoveDistCap),
                static_cast<long long>(s.memCacheEntries), static_cast<long long>(s.memDone));
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
                "act4 %lld keyless_victories %lld\n",
                static_cast<long long>(s.forcedKeys[0]), static_cast<long long>(s.forcedKeys[1]),
                static_cast<long long>(s.forcedKeys[2]), static_cast<long long>(s.keyRouteMasked),
                static_cast<long long>(prog.allKeys), static_cast<long long>(prog.act4),
                static_cast<long long>(prog.keylessVictories));
    if (bad || s.invalidActions || samples.empty() || s.runsDone < cfg.maxRuns) return 1;
    // The key backstops must be inert when off; when on they must act, and a run past the Act-3 boss holds all keys
    // (the treasure row and the last campfire are on every route, the route keeps the burning elite reachable).
    if (!cfg.forceKeys && (forced != 0 || s.keyRouteMasked != 0)) return 1;
    if (cfg.forceKeys && (forced == 0 || prog.keylessVictories != 0)) return 1;
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
    if (s.exploreNaturalUnplayed != 0) return 1;   // an item logged as picked by the search must have been played
    if (explore && (s.forcedPicks == 0 || s.exploreRoots == 0)) return 1;   // exploration must act
    if (!explore && (s.forcedPicks != 0 || s.exploreRoots != 0)) return 1;  // ... and be inert when off
    return 0;
}
