// Stage 0 throughput bench, part 2 (Amber-Eye-style self-play loop, 2026-11-16): how many positions per second the
// CPU side of a net-leaf search produces, per thread and over T threads.
//
//   az-bench-producer WIRES.jsonl [--threads T] [--seconds S] [--games G] [--no-encode] [--max-steps N]
//
// WIRES: rows with a "wire" field (a silver_bridge::BattleStateWire, as tests/data/combat_net_wire_sample.jsonl or
// silverazgen rows carry it). Each thread keeps G games, each started from a wire row (round robin). One position is
// what a search does once per leaf: copy the parent state, apply one legal action (uniformly random), enumerate the
// child's legal actions, and encode the child for the net (sts::search::combatTokEncodeRoot, the encoder the
// native combat net uses today: wire struct -> JSON -> arrays, plus one semantic fingerprint per action). The child
// becomes the game's next parent; a decided fight or one past --max-steps restarts from its wire row.
//
// Prints one JSON object: positions per second over all threads (wall clock) and the thread-CPU microseconds per
// position of each phase (copy+step, enumerate, encode). The action RNG is seeded per thread (std::mt19937_64(thread
// index)); it picks actions only, no game seed is drawn, and the states' own RNG streams come from their wires.
#include <atomic>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "sim/search/CombatTokNet.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

using nlohmann::json;
using namespace sts;
using namespace sts::search;

namespace {

    double cpuSeconds() {
        timespec ts{};
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
        return static_cast<double>(ts.tv_sec) + 1e-9 * static_cast<double>(ts.tv_nsec);
    }

    struct Root {
        BattleContext state;
        SilverSearchContext context;
    };

    struct ThreadResult {
        std::int64_t positions = 0, restarts = 0, encodeErrors = 0;
        double stepCpu = 0, enumCpu = 0, encodeCpu = 0;
    };

    void usage() {
        std::cerr << "usage: az-bench-producer WIRES.jsonl [--threads T] [--seconds S] [--games G] [--no-encode] "
                     "[--max-steps N]\n";
    }

}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage();
        return 2;
    }
    const std::string path = argv[1];
    int threads = static_cast<int>(std::thread::hardware_concurrency());
    double seconds = 5.0;
    int games = 64, maxSteps = 400;
    bool encode = true;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) throw std::invalid_argument(a + " needs a value");
            return argv[++i];
        };
        if (a == "--threads") threads = std::stoi(next());
        else if (a == "--seconds") seconds = std::stod(next());
        else if (a == "--games") games = std::stoi(next());
        else if (a == "--max-steps") maxSteps = std::stoi(next());
        else if (a == "--no-encode") encode = false;
        else {
            usage();
            return 2;
        }
    }
    if (threads < 1 || games < 1 || seconds <= 0) {
        usage();
        return 2;
    }

    std::vector<Root> roots;
    {
        std::ifstream f(path);
        if (!f) {
            std::cerr << "cannot open " << path << "\n";
            return 2;
        }
        std::string line;
        while (std::getline(f, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            const auto wire = row.at("wire").get<silver_bridge::BattleStateWire>();
            Root r{battleContextFromWire(wire), searchContextFromWire(wire)};
            if (r.state.outcome == Outcome::UNDECIDED) roots.push_back(std::move(r));
        }
    }
    if (roots.empty()) {
        std::cerr << "no undecided wire rows in " << path << "\n";
        return 2;
    }

    std::atomic<bool> stop{false};
    std::vector<ThreadResult> results(threads);
    auto work = [&](int t) {
        ThreadResult &res = results[t];
        std::mt19937_64 rng(static_cast<std::uint64_t>(t));
        SilverSearcher enumerator(roots[0].state, roots[0].context);
        struct Game {
            int root;
            BattleContext state;
            int steps = 0;
        };
        std::vector<Game> live;
        live.reserve(games);
        for (int g = 0; g < games; ++g) {
            const int r = (t * games + g) % static_cast<int>(roots.size());
            live.push_back({r, roots[r].state, 0});
        }
        std::vector<search::Action> actions;
        std::vector<SilverSearcher::Edge> edges;
        CombatTokInputs in;
        while (!stop.load(std::memory_order_relaxed)) {
            for (auto &g : live) {
                double t0 = cpuSeconds();
                actions = enumerator.enumerateActions(g.state);
                double t1 = cpuSeconds();
                res.enumCpu += t1 - t0;
                if (actions.empty()) {
                    g.state = roots[g.root].state;
                    g.steps = 0;
                    ++res.restarts;
                    continue;
                }
                BattleContext child = g.state;
                actions[std::uniform_int_distribution<std::size_t>(0, actions.size() - 1)(rng)].execute(child);
                double t2 = cpuSeconds();
                res.stepCpu += t2 - t1;
                // The child's own edges: the encoder needs them (one action row per edge), and the next position
                // reuses them as its parent's actions only in a real search; here they are enumerated again.
                actions = child.outcome == Outcome::UNDECIDED ? enumerator.enumerateActions(child)
                                                               : std::vector<search::Action>{};
                double t3 = cpuSeconds();
                res.enumCpu += t3 - t2;
                if (encode) {
                    edges.assign(actions.size(), {});
                    for (std::size_t k = 0; k < actions.size(); ++k) edges[k].action = actions[k];
                    try {
                        combatTokEncodeRoot(child, roots[g.root].context, edges, in);
                    } catch (const std::exception &) {
                        ++res.encodeErrors;
                    }
                    res.encodeCpu += cpuSeconds() - t3;
                }
                ++res.positions;
                if (child.outcome != Outcome::UNDECIDED || ++g.steps >= maxSteps) {
                    g.state = roots[g.root].state;
                    g.steps = 0;
                    ++res.restarts;
                } else {
                    g.state = std::move(child);
                }
            }
        }
    };

    const auto wall0 = std::chrono::steady_clock::now();
    std::vector<std::thread> pool;
    for (int t = 0; t < threads; ++t) pool.emplace_back(work, t);
    std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
    stop = true;
    for (auto &th : pool) th.join();
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();

    ThreadResult sum;
    for (const auto &r : results) {
        sum.positions += r.positions;
        sum.restarts += r.restarts;
        sum.encodeErrors += r.encodeErrors;
        sum.stepCpu += r.stepCpu;
        sum.enumCpu += r.enumCpu;
        sum.encodeCpu += r.encodeCpu;
    }
    const double n = static_cast<double>(std::max<std::int64_t>(1, sum.positions));
    json out = {
        {"wires", path},
        {"roots", roots.size()},
        {"threads", threads},
        {"games_per_thread", games},
        {"encode", encode},
        {"seconds", wall},
        {"positions", sum.positions},
        {"positions_per_s", static_cast<double>(sum.positions) / wall},
        {"positions_per_s_per_thread", static_cast<double>(sum.positions) / wall / threads},
        {"us_per_position", {{"copy_step", 1e6 * sum.stepCpu / n},
                             {"enumerate", 1e6 * sum.enumCpu / n},
                             {"encode", 1e6 * sum.encodeCpu / n}}},
        {"restarts", sum.restarts},
        {"encode_errors", sum.encodeErrors},
    };
    std::cout << out.dump() << std::endl;
    return 0;
}
