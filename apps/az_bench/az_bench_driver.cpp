// Stage 0 throughput bench, part 3, C++ only: the end-to-end producer (az_driver.h) with the fake net (random
// logits and values) on B batching threads, so the CPU side's rate is measured without a GPU. The GPU run uses the
// Python module (bindings/az_bench_module.cpp, tools/az_bench/e2e_bench.py) with the same driver.
//
//   az-bench-driver WIRES.jsonl [--workers W] [--games G] [--batchers B] [--batch N] [--seconds S]
//                   [--full-sims 64] [--fast-sims 16] [--full-prob 0.25] [--encoder amber|stub]
//
// Prints one JSON object: positions (net evaluations) per second, moves, fights, mean batch rows, and the workers'
// thread-CPU microseconds per position for step+enumerate, encode, and the whole search loop.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

#include "az_driver.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

using nlohmann::json;
using namespace sts;

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "usage: az-bench-driver WIRES.jsonl [--workers W] [--games G] [--batchers B] [--batch N] "
                     "[--seconds S] [--full-sims N] [--fast-sims N] [--full-prob P] [--encoder amber|stub]\n";
        return 2;
    }
    azbench::DriverConfig cfg;
    int batchers = 1, batch = 4096;
    double seconds = 5;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        if (i + 1 >= argc) { std::cerr << a << " needs a value\n"; return 2; }
        const std::string v = argv[++i];
        if (a == "--workers") cfg.workers = std::stoi(v);
        else if (a == "--games") cfg.gamesPerWorker = std::stoi(v);
        else if (a == "--batchers") batchers = std::stoi(v);
        else if (a == "--batch") batch = std::stoi(v);
        else if (a == "--seconds") seconds = std::stod(v);
        else if (a == "--full-sims") cfg.fullSims = std::stoi(v);
        else if (a == "--fast-sims") cfg.fastSims = std::stoi(v);
        else if (a == "--full-prob") cfg.fullProb = std::stod(v);
        else if (a == "--encoder") {
            if (v == "amber") cfg.encode = search::amberEncodeCombat;
            else if (v == "stub") cfg.encode = azbench::stubEncode;
            else { std::cerr << "--encoder amber|stub\n"; return 2; }
        }
        else { std::cerr << "unknown option " << a << "\n"; return 2; }
    }
    std::vector<azbench::Root> roots;
    std::ifstream f(argv[1]);
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        const auto wire = json::parse(line).at("wire").get<silver_bridge::BattleStateWire>();
        azbench::Root r{search::battleContextFromWire(wire), search::searchContextFromWire(wire)};
        if (r.state.outcome == Outcome::UNDECIDED) roots.push_back(std::move(r));
    }
    if (roots.empty()) { std::cerr << "no undecided wire rows\n"; return 2; }

    // At most one request per game is in flight: wait for half of them at most.
    const int minRows = std::max(1, std::min(batch, cfg.workers * cfg.gamesPerWorker) / 2);
    azbench::Driver driver(std::move(roots), cfg);
    std::atomic<bool> stop{false};
    std::vector<std::thread> pool;
    for (int b = 0; b < batchers; ++b) {
        pool.emplace_back([&, b] {
            azbench::PackedBatch pb;
            std::vector<float> logits, value;
            std::uint64_t rng = 0x9e3779b97f4a7c15ull + static_cast<std::uint64_t>(b);
            while (!stop.load()) {
                if (!driver.nextBatch(batch, minRows, 2, pb)) continue;
                azbench::fakeNetEvaluate(pb, logits, value, rng);
                driver.submit(pb, logits.data(), value.data());
            }
        });
    }
    driver.start();
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds / 5));   // warm-up
    const auto s0 = driver.stats();
    const auto t0 = std::chrono::steady_clock::now();
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
    const auto s1 = driver.stats();
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    stop = true;
    driver.stop();
    for (auto &t : pool) t.join();

    const double evals = static_cast<double>(s1.evals - s0.evals);
    const double n = std::max(1.0, evals);
    json out = {
        {"workers", cfg.workers}, {"games_per_worker", cfg.gamesPerWorker}, {"batchers", batchers},
        {"max_batch", batch}, {"full_sims", cfg.fullSims}, {"fast_sims", cfg.fastSims}, {"full_prob", cfg.fullProb},
        {"net", "fake"}, {"encoder", cfg.encode == azbench::stubEncode ? "stub" : "amber"}, {"seconds", wall},
        {"positions_per_s", evals / wall},
        {"moves_per_s", static_cast<double>(s1.moves - s0.moves) / wall},
        {"fights", s1.fights - s0.fights},
        {"terminal_leaves_per_s", static_cast<double>(s1.terminalLeaves - s0.terminalLeaves) / wall},
        {"mean_batch_rows", s1.batches > s0.batches ? static_cast<double>(s1.batchRows - s0.batchRows) /
                                                         static_cast<double>(s1.batches - s0.batches) : 0.0},
        {"worker_us_per_position", {{"step_enumerate", 1e6 * (s1.stepCpu - s0.stepCpu) / n},
                                    {"encode", 1e6 * (s1.encodeCpu - s0.encodeCpu) / n},
                                    {"search_loop", 1e6 * (s1.searchCpu - s0.searchCpu) / n}}},
        {"encode_cut", s1.encodeCut},
    };
    std::cout << out.dump() << std::endl;
    return 0;
}
