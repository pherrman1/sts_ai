#include "fight_replay.h"

#include "combat/BattleContext.h"
#include "combat/BattleContextBinary.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/ScumSearchAgent2.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace one_combat {
namespace {

std::string g_fightRepCaptureDir;

struct FightRepCaptureMeta {
    std::uint64_t seed;
    int encounter, floor;
    std::uint64_t offset;
    std::uint32_t size;
};

void fightRepReplay(const std::string &captureDir, const std::string &outCsv,
                    const std::vector<int> &particles, const std::vector<int> &sims,
                    int nFights) {
    // ── Discover captured fights (fight_<seed>.csv + .bin) ─────────────
    std::vector<FightRepCaptureMeta> fights;
    std::error_code ec;
    for (std::filesystem::directory_iterator it(captureDir, ec), end;
         !ec && it != end; it.increment(ec)) {
        const std::string fn = it->path().filename().string();
        if (fn.size() < 11 || fn.compare(0, 6, "fight_") != 0
            || fn.compare(fn.size() - 4, 4, ".csv") != 0)
            continue;
        std::uint64_t seed = 0;
        try { seed = std::stoull(fn.substr(6, fn.size() - 10)); } catch (...) { continue; }
        std::ifstream idx(it->path());
        if (!idx) continue;
        std::string line;
        std::getline(idx, line);   // header
        if (!std::getline(idx, line)) continue;
        std::stringstream ss(line);
        std::string tok;
        std::vector<std::string> f;
        while (std::getline(ss, tok, ',')) f.push_back(tok);
        if (f.size() < 6) continue;
        try {
            fights.push_back({seed, std::stoi(f[1]), std::stoi(f[2]), 0, 0});
        } catch (...) { continue; }
    }
    std::sort(fights.begin(), fights.end(),
              [](const FightRepCaptureMeta &a, const FightRepCaptureMeta &b) {
                  return a.seed < b.seed;
              });
    if (fights.empty()) {
        std::cerr << "fightrep: no fight_<seed>.csv captures found in " << captureDir << "\n";
        return;
    }
    const int n = std::min(nFights, (int)fights.size());
    std::cout << "fightrep: replaying " << n << " captured boss fights x "
              << particles.size() << " particle counts x " << sims.size()
              << " sim budgets = " << (long long)n * particles.size() * sims.size()
              << " cells -> " << outCsv << "\n";

    // ── Forced recorded fair-S3 regime (same as frontiergen/leafrelabel) ──
    sts::search::g_fairPlay = true;
    sts::search::g_useSearcher3 = true;
    sts::search::g_s3Belief = false;
    sts::search::g_s3Chain = false;
    sts::search::g_liveValid = true;
    std::cout << "[fightrep forced: fair-play / determinized MCTS + Searcher3 engine ON, "
                 "STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1]\n";

    std::ofstream out(outCsv);
    if (!out) { std::cerr << "fightrep: cannot open " << outCsv << "\n"; return; }
    out << "seed,encounter,floor,particles,sims,won,hpEnd,turns\n";

    auto t0 = std::chrono::steady_clock::now();
    // Outer loop over cells: g_s3Particles is a process global read at each
    // searcher construction, so set it once per cell on the main thread and
    // parallelize only over fights within a cell.
    for (int p : particles) {
        sts::search::g_s3Particles = p;
        for (int s : sims) {
            std::vector<std::string> rows((std::size_t)n);
            #pragma omp parallel for schedule(dynamic)
            for (int i = 0; i < n; ++i) {
                const FightRepCaptureMeta &m = fights[i];
                std::ifstream bin(captureDir + "/fight_" + std::to_string(m.seed) + ".bin",
                                  std::ios::binary);
                std::vector<std::uint8_t> blob((std::istreambuf_iterator<char>(bin)),
                                               std::istreambuf_iterator<char>());
                sts::BattleContext bc = sts::deserializeBattleContext(blob.data(), blob.size());
                if (bc.outcome != sts::Outcome::UNDECIDED) {   // shouldn't happen: snapshots are fight-start
                    rows[i] = std::to_string(m.seed) + ',' + std::to_string(m.encounter) + ','
                            + std::to_string(m.floor) + ',' + std::to_string(p) + ','
                            + std::to_string(s) + ",skip,0,0\n";
                    continue;
                }
                sts::search::ScumSearchAgent2 agent;
                agent.simulationCountBase = s;
                agent.rng = std::default_random_engine(m.seed);
                agent.playoutBattle(bc);
                const int won = bc.outcome == sts::Outcome::PLAYER_VICTORY ? 1 : 0;
                rows[i] = std::to_string(m.seed) + ',' + std::to_string((int)bc.encounter) + ','
                        + std::to_string(bc.floorNum) + ',' + std::to_string(p) + ','
                        + std::to_string(s) + ',' + std::to_string(won) + ','
                        + std::to_string(bc.player.curHp) + ',' + std::to_string(bc.turn) + '\n';
            }
            for (const auto &r : rows) out << r;
            out.flush();
        }
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::cout << "fightrep done: " << (long long)n * particles.size() * sims.size()
              << " cells in " << wall << "s\n";
}

} // namespace

void configureFightReplayFromEnvironment() {
    if (const char *d = std::getenv("STS_FIGHTREP_CAPTURE_DIR")) {
        g_fightRepCaptureDir = d;
        std::cout << "[fightrep capture dir = " << d
                  << " (serialize every Act-3 boss fight-start)]\n";
    }
}

bool fightReplayCaptureEnabled() {
    return !g_fightRepCaptureDir.empty();
}

void fightReplayCaptureStart(const sts::BattleContext &bc, std::uint64_t seed) {
    if (g_fightRepCaptureDir.empty()) return;
    const std::vector<std::uint8_t> blob = sts::serializeBattleContext(bc);
    std::ofstream bin(g_fightRepCaptureDir + "/fight_" + std::to_string(seed) + ".bin",
                      std::ios::binary);
    if (!bin) { std::cerr << "[fightrep] cannot open " << g_fightRepCaptureDir
                          << "/fight_" << seed << ".bin\n"; return; }
    bin.write((const char *)blob.data(), (std::streamsize)blob.size());
}

void fightReplayCaptureEnd(const sts::BattleContext &bc, std::uint64_t seed) {
    if (g_fightRepCaptureDir.empty()) return;
    std::ofstream csv(g_fightRepCaptureDir + "/fight_" + std::to_string(seed) + ".csv");
    if (!csv) { std::cerr << "[fightrep] cannot open " << g_fightRepCaptureDir
                          << "/fight_" << seed << ".csv\n"; return; }
    csv << "seed,encounter,floor,won,hpEnd,turns\n"
        << seed << ',' << (int)bc.encounter << ',' << bc.floorNum << ','
        << (bc.outcome == sts::Outcome::PLAYER_VICTORY ? 1 : 0) << ','
        << bc.player.curHp << ',' << bc.turn << '\n';
}

bool isFightReplayMode(const std::string &mode) {
    return mode == "fightrep";
}

int runFightReplayMode(const std::string &mode, int argc, char **argv) {
    if (!isFightReplayMode(mode)) return 2;
    if (argc < 5) {
        std::cerr << "usage: one_combat fightrep CAPTURE_DIR OUTFILE_CSV PARTICLES SIMS [NFIGHTS]\n"
                     "  CAPTURE_DIR must contain fight_<seed>.csv + fight_<seed>.bin from a run\n"
                     "  with STS_FIGHTREP_CAPTURE_DIR=<CAPTURE_DIR> (runFullRunOOC serializes\n"
                     "  every Act-3 boss fight-start). PARTICLES and SIMS are comma-separated\n"
                     "  lists (e.g. \"64,128\" \"500,1000\"). NFIGHTS (default all) bounds the\n"
                     "  fights. Replays each isolated fight with the recorded fair-S3 stack and\n"
                     "  writes seed,encounter,floor,particles,sims,won,hpEnd,turns. Keep\n"
                     "  nFights*|particles|*|sims| within the automated seed ceiling via seed_guard.\n";
        return 2;
    }
    std::string captureDir = argv[2];
    std::string outCsv = argv[3];
    auto parseList = [](const std::string &s) {
        std::vector<int> v;
        std::stringstream ss(s);
        std::string tok;
        while (std::getline(ss, tok, ','))
            if (!tok.empty()) v.push_back(std::stoi(tok));
        return v;
    };
    std::vector<int> particles = parseList(argv[4]);
    std::vector<int> sims = parseList(argv[5]);
    if (particles.empty() || sims.empty()) {
        std::cerr << "fightrep: PARTICLES and SIMS must be non-empty comma lists\n";
        return 2;
    }
    int nFights = argc > 6 ? std::stoi(argv[6]) : 1 << 30;
    fightRepReplay(captureDir, outCsv, particles, sims, nFights);
    return 0;
}

} // namespace one_combat
