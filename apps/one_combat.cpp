// one_combat.cpp
//
// "An agent plays one combat" for sts_lightspeed, with two policies:
//   * random    -- uniformly random legal action (baseline)
//   * mcts      -- wraps the built-in BattleScumSearcher2 (Monte Carlo tree search)
// plus a benchmark harness that plays N seeds with each and reports win rate
// and HP retained.
//
// Usage:
//   one_combat mcts   [sims] [seed]     # one verbose combat, MCTS policy
//   one_combat random [seed]            # one verbose combat, random policy
//   one_combat bench  [sims] [nSeeds]   # MCTS(sims) vs random over nSeeds
//
// NOTE ON THE SEARCHER: BattleScumSearcher2 is a *known-RNG* solver -- its
// rollouts see the same upcoming draws the real combat will get, so it plays
// with hidden-information it wouldn't have in a live game. That makes it a
// strong baseline / upper bound, not a fair-play agent. (Fair search over
// unknown RNG is a "planned feature" per the repo README.) It also hardcodes
// evaluateEndState internally, so the EvalFnc ctor arg is currently ignored.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <functional>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <random>
#include <string>
#include <thread>
#include <tuple>
#include <unordered_set>
#include <vector>

#include "game/GameContext.h"
#include "combat/BattleContext.h"
#include "combat/BattleContextBinary.h"
#include "sim/search/Action.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatPVNet.h"
#include "sim/search/CombatCpsiNet.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/S3SiblingCrnDiagnostic.h"
#include "sim/search/S3RejuvenationProbe.h"
#include "sim/search/GameAction.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/SimHealth.h"
#include "sim/search/TrainingIntegrity.h"
#include "game/Map.h"
#include "sim/util/BestBenchMeta.h"
#include "ooc_checkpoint_net.h"
#include "ooc_strategic_net.h"
#include "ooc_strategic_tok_net.h"

#ifdef _OPENMP
#include <omp.h>
#endif

#ifndef _WIN32
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/select.h>
#include <unistd.h>
#include <cstring>
#include <cerrno>
#endif
#include <atomic>
#include <iomanip>
#include <set>
#include <unordered_map>
#include <unordered_set>

extern bool g_collectKeys;              // env STS_COLLECT_KEYS=1: collect act-4 keys
static std::vector<std::string> g_mainArgv;
static std::string g_mainBinaryPath;
// Resolved only after successful loading, so E3a provenance does not confuse
// an unset/failed environment request with the policy actually exercised.
static std::string g_effectiveVNetPath;
static std::string g_effectivePolicyPath;
static std::string g_effectiveOocStrategicPath;
static std::string g_effectiveOocStrategicTokPath;

static thread_local int t_trainingHealthFailures = 0;
static thread_local int t_trainingBranchHealthFailures = 0;
static thread_local bool t_trainingRunActive = false;
struct E2cCapture;
struct PathHistory;
static thread_local E2cCapture *t_e2c = nullptr;
static thread_local std::string t_e2cRows;
static std::atomic<long long> g_e2cCounts[3][6]{}; // eligible, raw, post, pairs, raw_only, post_only
static void e2cBeginFight(int, const sts::GameContext &, const sts::BattleContext &);
static void e2cRawObserver(const sts::BattleContext &, sts::GameContext &);
static void e2cCapturePost(sts::GameContext &);
static std::string e2cRunRows(const E2cCapture &, bool, int, int);
static std::string e2cExplicitRelics(const sts::GameContext &);
static std::string e2cHeader();
static std::string richStateHeader();
static std::string e2cRoomName(int);
static bool g_runwinShadowActive = false;
static int g_runwinShadowR = 1;
static int g_runwinShadowPerStratum = 1;
static int g_runwinShadowMaxGroups = 16;
// E3a is a separate, default-off diagnostic.  It shares the E2c shadow
// estimator but adds a detached eventual-run reference after the source run.
static bool g_runwinRankActive = false;
static int g_runwinRankRoots = 2;
static int g_runwinRankMaxLeaves = 6;
static int g_runwinRankMinLeaves = 3;
static int g_runwinRankReferenceFutures = 8;
static int g_runwinRankReferenceSims = 1000;
static void runwinShadowBeginFight(int, const sts::GameContext &, const PathHistory &, sts::Room, sts::MonsterEncounter);
static void runwinRankBeginFight(int, const sts::GameContext &, const PathHistory &, sts::Room, sts::MonsterEncounter);
static std::atomic<int> g_trainingInvalidRuns{0};
static std::atomic<int> g_trainingInvalidBranches{0};
static std::atomic<int> g_trainingHealthFailures{0};

static void trainingRunStart() {
    t_trainingHealthFailures = sts::search::g_simHealthFailureCount;
    t_trainingBranchHealthFailures = 0;
    t_trainingRunActive = true;
}

static void trainingCampaignStart() {
    g_trainingInvalidRuns = 0;
    g_trainingInvalidBranches = 0;
    g_trainingHealthFailures = 0;
}

static bool trainingRunValid(bool outcomeDecided) {
    const int after = sts::search::g_simHealthFailureCount;
    const bool valid = sts::search::isValidTrainingTerminal(
        outcomeDecided, t_trainingHealthFailures,
        after - t_trainingBranchHealthFailures);
    if (!valid) {
        ++g_trainingInvalidRuns;
        g_trainingHealthFailures += std::max(0, after - t_trainingHealthFailures
                                              - t_trainingBranchHealthFailures);
    }
    return valid;
}

static std::string jsonEscape(const std::string &value) {
    std::string out;
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) { char buf[7]; std::snprintf(buf, sizeof(buf), "\\u%04x", c); out += buf; }
                else out += (char)c;
        }
    }
    return out;
}

static std::string trainingGitValue(const char *command) {
    std::string value;
    FILE *pipe = popen(command, "r");
    if (!pipe) return value;
    char buf[256];
    if (std::fgets(buf, sizeof(buf), pipe)) value = buf;
    pclose(pipe);
    while (!value.empty() && (value.back() == '\n' || value.back() == '\r')) value.pop_back();
    return value;
}

static std::string fileSha256(const std::string &path) {
    // Model paths are operator-provided and may contain spaces.  Quote for the
    // repository's POSIX execution environments; a missing utility/file is
    // represented explicitly as an empty provenance value rather than guessed.
    std::string safe;
    for (char c : path) { if (c == '\'') safe += "'\\\"'\\\"'"; else safe += c; }
    const std::string line = trainingGitValue(("sha256sum '" + safe + "' 2>/dev/null").c_str());
    const size_t cut = line.find_first_of(" \t");
    return cut == std::string::npos ? line : line.substr(0, cut);
}

static void writeTrainingProvenance(const std::string &output, const char *mode,
                                    int requested, int completed, int invalid,
                                    int healthFailures, long long rows,
                                    long long seedOffset, int sims, int asc,
                                    double epsilon = -1.0) {
    std::ofstream p(output + ".provenance.json");
    if (!p) return;
    const char *envs[] = {"STS_FAIR", "STS_SEARCHER3", "STS_S3_PARTICLES",
                          "STS_S3_BELIEF", "STS_S3_CHAIN", "STS_REUSE_MAX_SEARCHES",
                          "STS_S3_PERSIST_FILTERED_BELIEF",
                          "STS_S3_REJUV_SHADOW", "STS_S3_REJUV_TRIGGER",
                          "STS_S3_REJUV_PROPOSALS", "STS_S3_REJUV_SHADOW_FILE",
                           "STS_S3_AI_REJUV_LIVE", "STS_S3_AI_REJUV_LIVE_FILE",
                          "STS_S3_RNG_EXPOSURE_DIAG", "STS_S3_RNG_EXPOSURE_DIAG_FILE",
                          "STS_REUSE_STATS_MODE", "STS_REUSE_ALWAYS_Q", "STS_S3_ALWAYS_Q", "STS_REUSE_DIAG",
                          "STS_S3_GATE_TIMING_DIAG", "STS_S3_GATE_TIMING_DIAG_FILE",
                          "STS_REUSE_OBS_STABLE", "STS_REUSE_RECONCILE_ROOT",
                          "STS_REUSE_CARRY_DIAG", "STS_REUSE_CPU_DIAG",
                          "STS_REUSE_CPU_DIAG_FILE", "STS_LIVE_VALID", "STS_STOP_AFTER_ACT",
                          "STS_S3_STRATEGY_FUSION_DIAG", "STS_S3_STRATEGY_FUSION_DIAG_FILE",
                          "STS_S3_STRATEGY_FUSION_DIAG_PARTICLES",
                          "STS_S3_STRATEGY_FUSION_DIAG_MAX_TRANSITIONS",
                          "STS_S3_STRATEGY_FUSION_DIAG_MIN_CHILD_VISITS",
                          "STS_S3_STRATEGY_FUSION_DIAG_FRESH_SIMS",
                          "STS_S3_STRATEGY_FUSION_DIAG_REF_SIMS",
                          "STS_FORCED_MOVE",
                          "STS_VNET", "STS_VNET_ALPHA", "STS_OOC_STRATEGIC_TOK_NN",
                          "STS_OOC_STRATEGIC_MARGIN", "STS_OOC_STRATEGIC_CARD",
                          "STS_OOC_STRATEGIC_REST", "STS_OOC_STRATEGIC_EVENT",
                          "STS_OOC_STRATEGIC_SHOP", "STS_OOC_STRATEGIC_TREASURE",
                          "STS_OOC_STRATEGIC_BOSS_RELIC", "STS_COLLECT_KEYS",
                          "STRATEGIC_SAMPLE_ALL", "STRATEGIC_SAMPLES_PER_RUN",
                          "STRATEGIC_BRANCH_FIGHTS", "STRATEGIC_BRANCH_SIMS",
                          "STRATEGIC_BRANCH_FUTURES"};
    p << "{\n  \"dataset_path\": \"" << jsonEscape(output) << "\",\n"
      << "  \"timestamp_utc\": \"" << jsonEscape(trainingGitValue("date -u +%Y-%m-%dT%H:%M:%SZ")) << "\",\n"
      << "  \"git_sha\": \"" << jsonEscape(trainingGitValue("git rev-parse HEAD")) << "\",\n"
      << "  \"git_dirty\": " << (trainingGitValue("git status --porcelain --untracked-files=all") != "" ? "true" : "false") << ",\n"
      << "  \"generator\": \"" << jsonEscape(mode) << "\",\n"
      << "  \"argv\": [";
    for (size_t i = 0; i < g_mainArgv.size(); ++i) {
        if (i) p << ',';
        p << "\"" << jsonEscape(g_mainArgv[i]) << "\"";
    }
    p << "],\n  \"command\": \"one_combat";
    for (const auto &arg : g_mainArgv) {
        p << ' ' << jsonEscape(arg);
    }
    p << "\",\n"
      << "  \"seed_offset\": " << seedOffset << ",\n"
      << "  \"requested_seeds\": " << requested << ",\n"
      << "  \"completed_seeds\": " << completed << ",\n"
      << "  \"invalid_or_quarantined_seeds\": " << invalid << ",\n"
      << "  \"invalid_or_quarantined_branches\": " << g_trainingInvalidBranches.load() << ",\n"
      << "  \"simulator_health_hard_failures\": " << healthFailures << ",\n"
      << "  \"rows_written\": " << rows << ",\n"
      << "  \"simulations\": " << sims << ",\n"
      << "  \"ascension\": " << asc << ",\n"
      << "  \"epsilon\": " << epsilon << ",\n"
      << "  \"models\": {\n    \"STS_VNET\": ";
    if (const char *v = std::getenv("STS_VNET")) p << "\"" << jsonEscape(v) << "\""; else p << "null";
    p << ",\n    \"STS_OOC_STRATEGIC_TOK_NN\": ";
    if (const char *v = std::getenv("STS_OOC_STRATEGIC_TOK_NN")) p << "\"" << jsonEscape(v) << "\""; else p << "null";
    p << "\n  },\n  \"environment\": {";
    for (int i = 0; i < (int)(sizeof(envs) / sizeof(envs[0])); ++i) {
        if (i) p << ',';
        const char *value = std::getenv(envs[i]);
        p << "\n    \"" << envs[i] << "\": ";
        if (value) p << '"' << jsonEscape(value) << '"'; else p << "null";
    }
    p << "\n  }\n}\n";
}

// Offline sibling common-random-numbers diagnostic. This intentionally does
// not call search(), allocate PUCT visits, or touch the historical g_s3Crn
// warm-start path. Each output row is one attempted forced-action evaluation.
static std::string csvQuoted(const std::string &s) {
    std::string out = "\"";
    for (char c : s) { if (c == '\"') out.push_back('\"'); out.push_back(c); }
    out.push_back('\"');
    return out;
}

static std::string s3CrnActionDesc(const sts::search::Action &a, const sts::BattleContext &bc) {
    std::ostringstream ss; a.printDesc(ss, bc); return ss.str();
}

static std::string s3CrnCounters(const std::array<std::int32_t, 6> &v) {
    std::ostringstream ss;
    for (std::size_t i = 0; i < v.size(); ++i) { if (i) ss << ';'; ss << v[i]; }
    return ss.str();
}

static std::uint64_t s3CrnFileHash(const std::string &path) {
    std::ifstream in(path, std::ios::binary);
    std::uint64_t h = 1469598103934665603ULL;
    char buf[8192];
    while (in) {
        in.read(buf, sizeof(buf));
        for (std::streamsize i = 0; i < in.gcount(); ++i) {
            h ^= (unsigned char)buf[i]; h *= 1099511628211ULL;
        }
    }
    return h;
}

static std::vector<std::uint8_t> readFgBlob(std::ifstream &f,
                                            std::uint64_t offset,
                                            std::uint32_t size);

static bool s3SiblingCrnDiagnostic(const std::string &inCsv,
                                   const std::string &inBin,
                                   const std::string &outFile,
                                   const std::vector<int> &budgets,
                                   int replicates, int maxStates,
                                   std::uint64_t diagnosticSeed,
                                   const std::string &baselineSha,
                                   const std::string &diagnosticSha,
                                   const std::string &manifestFile) {
    using ParentKey = std::tuple<std::uint64_t, int, int, std::uint64_t>;
    std::map<ParentKey,
             std::pair<std::uint64_t, std::uint32_t>> parents;
    {
        std::ifstream corpus(inCsv);
        std::string line;
        std::getline(corpus, line);
        std::vector<std::string> cols;
        std::stringstream hs(line); std::string tok;
        while (std::getline(hs, tok, ',')) cols.push_back(tok);
        auto ci = [&](const char *name) {
            for (int i = 0; i < (int)cols.size(); ++i) if (cols[(std::size_t)i] == name) return i;
            return -1;
        };
        const int cSeed = ci("seed"), cFight = ci("fightIdx"), cDec = ci("decIdx"),
                  cObs = ci("obsHash"),
                  cType = ci("frontierType"), cOff = ci("binaryOffset"), cSize = ci("binarySize");
        if (cSeed < 0 || cFight < 0 || cDec < 0 || cObs < 0 || cType < 0 || cOff < 0 || cSize < 0) {
            std::cerr << "s3siblingcrn: frontier CSV missing parent provenance columns\n"; return false;
        }
        while (std::getline(corpus, line)) {
            std::vector<std::string> f; std::stringstream ls(line);
            while (std::getline(ls, tok, ',')) f.push_back(tok);
            const int need = std::max({cSeed, cFight, cDec, cObs, cType, cOff, cSize});
            if ((int)f.size() <= need || std::atoi(f[(std::size_t)cType].c_str()) != -1) continue;
            parents[{std::strtoull(f[(std::size_t)cSeed].c_str(), nullptr, 10),
                     std::atoi(f[(std::size_t)cFight].c_str()),
                     std::atoi(f[(std::size_t)cDec].c_str()),
                     std::strtoull(f[(std::size_t)cObs].c_str(), nullptr, 10)}] = {
                std::strtoull(f[(std::size_t)cOff].c_str(), nullptr, 10),
                (std::uint32_t)std::strtoul(f[(std::size_t)cSize].c_str(), nullptr, 10)};
        }
    }
    std::set<std::tuple<std::uint64_t, int, int, std::uint64_t>> selected;
    if (!manifestFile.empty()) {
        std::ifstream manifest(manifestFile);
        std::string line;
        if (!manifest || !std::getline(manifest, line)) {
            std::cerr << "s3siblingcrn: cannot read selection manifest " << manifestFile << '\n';
            return false;
        }
        std::vector<std::string> cols; std::stringstream hs(line); std::string tok;
        while (std::getline(hs, tok, ',')) cols.push_back(tok);
        auto ci = [&](const char *name) {
            for (int i = 0; i < (int)cols.size(); ++i) if (cols[(std::size_t)i] == name) return i;
            return -1;
        };
        const int cSeed = ci("source_seed"), cFight = ci("fight_idx"),
                  cDec = ci("decision_idx"), cState = ci("state_id");
        if (cSeed < 0 || cFight < 0 || cDec < 0 || cState < 0) {
            std::cerr << "s3siblingcrn: selection manifest missing composite identity columns\n";
            return false;
        }
        while (std::getline(manifest, line)) {
            std::vector<std::string> f; std::stringstream ls(line);
            while (std::getline(ls, tok, ',')) f.push_back(tok);
            const int need = std::max({cSeed, cFight, cDec, cState});
            if ((int)f.size() <= need) continue;
            selected.insert({std::strtoull(f[(std::size_t)cSeed].c_str(), nullptr, 10),
                             std::atoi(f[(std::size_t)cFight].c_str()),
                             std::atoi(f[(std::size_t)cDec].c_str()),
                             std::strtoull(f[(std::size_t)cState].c_str(), nullptr, 10)});
        }
        if (selected.empty()) {
            std::cerr << "s3siblingcrn: selection manifest contains no states\n";
            return false;
        }
        maxStates = std::min(maxStates, static_cast<int>(selected.size()));
    }
    std::ifstream bin(inBin, std::ios::binary);
    std::ofstream out(outFile);
    if (!bin || !out) { std::cerr << "s3siblingcrn: cannot open input/output artifact\n"; return false; }
    const std::uint64_t corpusHash = sts::search::s3SiblingCrnMix(
        s3CrnFileHash(inCsv) ^ s3CrnFileHash(inBin));
    out << "baseline_sha,diagnostic_sha,corpus_hash,state_id,source_seed,fight_idx,decision_idx,"
           "encounter,floor,action_id,action_bits,action_desc,action_prior,K,replicate,"
           "sampling_mode,sample_index,value,valid,particle_id,particle_seed,rollout_seed,"
           "pre_action_rng_counters,post_action_rng_counters,final_rng_counters,"
           "rollout_actions,diagnostic_seed\n";
    out << std::setprecision(17);
    int stateOrdinal = 0; long long attempts = 0, invalid = 0;
    const auto started = std::chrono::steady_clock::now();
    for (const auto &entry : parents) {
        if (stateOrdinal >= maxStates) break;
        if (!selected.empty() && selected.find(entry.first) == selected.end()) continue;
        const auto blob = readFgBlob(bin, entry.second.first, entry.second.second);
        if (blob.empty()) continue;
        const sts::BattleContext parent = sts::deserializeBattleContext(blob.data(), blob.size());
        if (parent.outcome != sts::Outcome::UNDECIDED) continue;
        sts::search::BattleScumSearcher3::Node node;
        sts::search::enumerateActionsForNode(node, parent);
        if (node.edges.size() < 2) continue;
        if ((sts::search::g_usePolicyNet && sts::search::g_policyNet.loaded())
            || (sts::search::g_usePVNet && sts::search::g_combatPVNet.loaded()
                && !sts::search::g_pvnetValueOnly))
            sts::search::computeEdgePriors(node, parent);
        std::stable_sort(node.edges.begin(), node.edges.end(),
            [](const auto &a, const auto &b) { return a.prior > b.prior; });
        if (node.edges.size() > 3) node.edges.resize(3);
        const auto [sourceSeed, fightIdx, decIdx, stateId] = entry.first;
        const sts::search::S3SiblingCrnStateIdentity identity{
            sourceSeed, fightIdx, decIdx, stateId};
        const std::uint64_t observedStateId = sts::CombatObservation::fromBattleContext(parent).visibleHash();
        if (observedStateId != stateId) {
            std::cerr << "s3siblingcrn: manifest/parent state hash mismatch for seed="
                      << sourceSeed << " fight=" << fightIdx << " decision=" << decIdx << '\n';
            continue;
        }
        sts::search::BattleScumSearcher3 evaluator(parent, 0, 0, 1);
        auto emit = [&](const char *mode, int k, int rep, int sample, int ai,
                        std::uint64_t particleSeed, const sts::HiddenBattleState &particle) {
            const std::uint64_t rolloutSeed = sts::search::s3SiblingCrnSeed(
                diagnosticSeed, identity, k, rep, sample, ai, 0x726f6c6c6f7574ULL);
            const auto &edge = node.edges[(std::size_t)ai];
            const auto result = evaluator.evaluateForcedActionDiagnostic(parent, particle,
                                                                           edge.action, rolloutSeed);
            ++attempts; if (!result.valid) ++invalid;
            out << baselineSha << ',' << diagnosticSha << ',' << corpusHash << ',' << stateId << ','
                << sourceSeed << ',' << fightIdx << ',' << decIdx << ',' << (int)parent.encounter << ','
                << parent.floorNum << ',' << ai << ',' << edge.action.bits << ','
                << csvQuoted(s3CrnActionDesc(edge.action, parent)) << ',' << edge.prior << ','
                << k << ',' << rep << ',' << mode << ',' << sample << ',' << result.value << ','
                << (result.valid ? 1 : 0) << ',' << particle.id << ',' << particleSeed << ','
                << rolloutSeed << ',' << csvQuoted(s3CrnCounters(result.preActionRngCounters)) << ','
                << csvQuoted(s3CrnCounters(result.postActionRngCounters)) << ','
                << csvQuoted(s3CrnCounters(result.finalRngCounters)) << ','
                << result.rolloutActions << ',' << diagnosticSeed << '\n';
        };
        for (int k : budgets) for (int rep = 0; rep < replicates; ++rep) {
            for (int sample = 0; sample < k; ++sample) {
                const std::uint64_t ps = sts::search::s3SiblingCrnSeed(
                    diagnosticSeed, identity, k, rep, sample, 0, 0x63726eULL);
                std::mt19937_64 prng(ps);
                sts::HiddenBattleState p = sts::Belief::initial(parent, 1, prng).particles.front(); p.id = ps;
                for (int ai = 0; ai < (int)node.edges.size(); ++ai) emit("crn", k, rep, sample, ai, ps, p);
            }
            for (int ai = 0; ai < (int)node.edges.size(); ++ai) for (int sample = 0; sample < k; ++sample) {
                const std::uint64_t ps = sts::search::s3SiblingCrnSeed(
                    diagnosticSeed, identity, k, rep, sample, ai, 0x696e64ULL);
                std::mt19937_64 prng(ps);
                sts::HiddenBattleState p = sts::Belief::initial(parent, 1, prng).particles.front(); p.id = ps;
                emit("independent", k, rep, sample, ai, ps, p);
            }
        }
        constexpr int kReference = 128;
        for (int ai = 0; ai < (int)node.edges.size(); ++ai) for (int sample = 0; sample < kReference; ++sample) {
            const std::uint64_t ps = sts::search::s3SiblingCrnSeed(
                diagnosticSeed, identity, kReference, 0, sample, ai, 0x726566ULL);
            std::mt19937_64 prng(ps);
            sts::HiddenBattleState p = sts::Belief::initial(parent, 1, prng).particles.front(); p.id = ps;
            emit("reference", kReference, 0, sample, ai, ps, p);
        }
        ++stateOrdinal;
    }
    if (!selected.empty() && !sts::search::s3SiblingCrnManifestSatisfied(
            selected.size(), static_cast<std::size_t>(stateOrdinal))) {
        std::cerr << "s3siblingcrn: selection manifest requested " << selected.size()
                  << " states but only " << stateOrdinal
                  << " were usable; refusing a partial formal diagnostic\n";
        out.flush();
        out.close();
        std::remove(outFile.c_str());
        return false;
    }
    out.flush();
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    std::cout << "s3siblingcrn wrote " << attempts << " attempts across " << stateOrdinal
              << " states (invalid=" << invalid << ", " << (seconds > 0 ? attempts / seconds : 0.0)
              << " eval/s) -> " << outFile << '\n';
    return true;
}

// ---------------------------------------------------------------------------
// Live progress line for long parallel benches. Threads call tick() as each run
// finishes; it prints an in-place (\r) status to stderr -- completed/total,
// running win%/floor/HP, elapsed + ETA -- throttled to ~4 Hz. Only draws when
// stderr is a TTY, so redirected A/B logs stay clean. Call done() at the end.
struct BenchProgress {
    int total; const char *label;
    std::atomic<int> n{0}, wins{0};
    std::atomic<long long> floor{0}, hp{0};
    std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
    std::atomic<double> lastDraw{-1.0};
    bool tty = isatty(fileno(stderr));
    BenchProgress(int total_, const char *label_) : total(total_), label(label_) {}
    void tick(bool won, int fl, int h) {
        int d = ++n; wins += won; floor += fl; hp += h;
        if (!tty) return;
        double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        double last = lastDraw.load();
        if (d != total && (el - last) < 0.25) return;         // throttle
        if (!lastDraw.compare_exchange_strong(last, el)) return;
        double eta = d ? el / d * (total - d) : 0;
        std::fprintf(stderr, "\r  %s [%d/%d] %.0f%%  win%%=%.1f floor=%.1f hp=%.1f  %.0fs eta %.0fs      ",
                     label, d, total, 100.0 * d / total,
                     100.0 * wins / d, (double)floor / d, (double)hp / d, el, eta);
        std::fflush(stderr);
    }
    void done() { if (tty) std::fprintf(stderr, "\r\033[K"); }  // clear the line
};

static int numThreads() {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

using namespace sts;

using Policy = std::function<search::Action(const BattleContext &)>;

static MonsterEncounter g_encounter = MonsterEncounter::JAW_WORM;

// ---------------------------------------------------------------------------
// Enumerate legal actions in the current player-choice state
// (mirrors BattleScumSearcher2::enumerateActionsForNode; potions omitted).
// ---------------------------------------------------------------------------
static std::vector<search::Action> legalActions(const BattleContext &bc) {
    using search::Action;
    using search::ActionType;
    std::vector<Action> actions;

    if (bc.inputState == InputState::PLAYER_NORMAL) {
        if (bc.isCardPlayAllowed()) {
            for (int h = 0; h < bc.cards.cardsInHand; ++h) {
                const auto &c = bc.cards.hand[h];
                if (!c.canUseOnAnyTarget(bc)) continue;
                if (c.requiresTarget()) {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            actions.push_back(Action(ActionType::CARD, h, t));
                } else {
                    actions.push_back(Action(ActionType::CARD, h));
                }
            }
        }
        actions.push_back(Action(ActionType::END_TURN));
    } else if (bc.inputState == InputState::CARD_SELECT) {
        actions = Action::enumerateCardSelectActions(bc);
    }
    return actions;
}

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------
static search::Action randomPolicy(const BattleContext &bc) {
    static thread_local std::mt19937 rng(0xC0FFEE);
    auto actions = legalActions(bc);
    if (actions.empty()) return search::Action(search::ActionType::END_TURN);
    std::uniform_int_distribution<int> dist(0, (int)actions.size() - 1);
    return actions[dist(rng)];
}

static Policy makeMctsPolicy(int sims) {
    return [sims](const BattleContext &bc) -> search::Action {
        search::BattleScumSearcher2 searcher(bc);
        searcher.search(sims);
        if (!searcher.bestActionSequence.empty())
            return searcher.bestActionSequence.front();
        return randomPolicy(bc); // fallback (shouldn't trigger in a live state)
    };
}

// ---------------------------------------------------------------------------
// Play a single combat to completion.
// ---------------------------------------------------------------------------
struct Result { bool won; int hpStart, hpEnd, maxHp, turns; };

static Result runCombat(std::uint64_t seed, const Policy &policy, bool verbose) {
    GameContext gc(CharacterClass::IRONCLAD, seed, /*ascension=*/0);
    BattleContext bc;
    bc.init(gc, g_encounter);

    const int hpStart = bc.player.curHp;
    int step = 0;
    // Terminate on a decided outcome (isBattleOver lags a step behind).
    while (bc.outcome == Outcome::UNDECIDED) {
        search::Action a = policy(bc);
        if (verbose) {
            std::cout << "step " << step++ << "  hp=" << bc.player.curHp
                      << "  hand=" << bc.cards.cardsInHand << "  -> ";
            a.printDesc(std::cout, bc) << "\n";
        }
        a.execute(bc);
    }
    return { bc.outcome == Outcome::PLAYER_VICTORY,
             hpStart, bc.player.curHp, bc.player.maxHp, bc.turn };
}

// ---------------------------------------------------------------------------
// Benchmark: N seeds, both policies, aggregate.
// ---------------------------------------------------------------------------
static void benchmark(int sims, int nSeeds) {
    struct Agg { int wins = 0; long long hpRetained = 0; long long turns = 0; double ms = 0; };
    Agg r, m;
    Policy randp = &randomPolicy;
    Policy mctsp = makeMctsPolicy(sims);

    std::cout << "encounter: JawWorm   seeds: 0.." << nSeeds - 1
              << "   mcts sims/decision: " << sims << "\n\n";

    for (std::uint64_t seed = 0; seed < (std::uint64_t)nSeeds; ++seed) {
        auto t0 = std::chrono::steady_clock::now();
        Result rr = runCombat(seed, randp, false);
        auto t1 = std::chrono::steady_clock::now();
        Result mr = runCombat(seed, mctsp, false);
        auto t2 = std::chrono::steady_clock::now();

        r.wins += rr.won; r.hpRetained += rr.hpEnd; r.turns += rr.turns;
        r.ms += std::chrono::duration<double, std::milli>(t1 - t0).count();
        m.wins += mr.won; m.hpRetained += mr.hpEnd; m.turns += mr.turns;
        m.ms += std::chrono::duration<double, std::milli>(t2 - t1).count();
    }

    auto row = [&](const char *name, const Agg &a) {
        std::printf("%-8s  win%%=%5.1f   avg_hp_end=%5.1f   avg_turns=%4.1f   avg_ms=%7.2f\n",
                    name, 100.0 * a.wins / nSeeds,
                    (double)a.hpRetained / nSeeds,
                    (double)a.turns / nSeeds,
                    a.ms / nSeeds);
    };
    row("random", r);
    row("mcts", m);
}

// ---------------------------------------------------------------------------
// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via its out-of-combat policy).
// ---------------------------------------------------------------------------
struct RunResult { bool won; int floor; int act; int hpEnd, maxHp; int fightsLost; double sec; int deathCombat = -1; int deathEncounter = -1; };

static RunResult runFullRun(std::uint64_t seed, int sims, int ascension, bool verbose) {
    GameContext gc(CharacterClass::IRONCLAD, seed, ascension);

    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;    // MCTS sims per in-combat decision
    agent.printLogs = verbose;           // dump GameContext at each out-of-combat step
    agent.rng = std::default_random_engine(seed); // reproducible out-of-combat choices

    auto t0 = std::chrono::steady_clock::now();
    agent.playout(gc);                   // runs until gc.outcome is decided
    auto t1 = std::chrono::steady_clock::now();

    return { gc.outcome == GameOutcome::PLAYER_VICTORY,
             gc.floorNum, gc.act, gc.curHp, gc.maxHp,
             std::chrono::duration<double>(t1 - t0).count() };
}

static void runBenchmark(int sims, int nSeeds, int ascension) {
    std::cout << "whole-run benchmark   seeds: 0.." << nSeeds - 1
              << "   ascension: " << ascension
              << "   mcts sims/decision: " << sims
              << "   threads: " << numThreads() << "\n\n";

    int wins = 0;
    long long floorSum = 0, hpSum = 0;
    double secSum = 0;
    #pragma omp parallel for reduction(+:wins,floorSum,hpSum,secSum) schedule(dynamic)
    for (int seed = 0; seed < nSeeds; ++seed) {
        RunResult r = runFullRun((std::uint64_t)seed, sims, ascension, false);
        wins += r.won; floorSum += r.floor; hpSum += r.hpEnd; secSum += r.sec;
        std::printf("seed %2d  %-4s  floor %2d (act %d)  hp %3d/%-3d  %6.2fs\n",
                    seed, r.won ? "WIN" : "DEAD",
                    r.floor, r.act, r.hpEnd, r.maxHp, r.sec);
    }
    std::printf("\nwin%%=%.1f   avg_floor=%.1f   avg_hp_end=%.1f   avg_sec/run=%.2f\n",
                100.0 * wins / nSeeds,
                (double)floorSum / nSeeds,
                (double)hpSum / nSeeds,
                secSum / nSeeds);
}

// ---------------------------------------------------------------------------
// LOOKAHEAD CARD-REWARD POLICY: for each choice (each card + skip), copy the
// run, apply the choice, play the next N fights with a cheap agent, and keep
// the choice that leaves us best off. Common Random Numbers come for free: the
// copied GameContext carries all game RNG streams, so the only difference
// between branches is the deck. (Like the combat searcher, this peeks at the
// run's fixed future RNG.)
// ---------------------------------------------------------------------------
static double scoreLookaheadState(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -1e6 + gc.floorNum;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return  1e6 + gc.curHp;
    return gc.curHp * 100.0 + gc.floorNum;   // survived the N fights: HP is the discriminator
}

// Bounded, regression-friendly score (HP scale) for causal labels -- unlike
// scoreLookaheadState's +/-1e6 outcome bonuses which would swamp any regression.
static double labelScore(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -100.0;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return gc.maxHp + 200.0;
    return gc.curHp;   // survived the N fights: remaining HP is the signal
}

static double rolloutChoice(const GameContext &base, int rIdx, int cardIdx,
                            int N, int innerSims, std::uint64_t seed, bool useLabelScore = false) {
    GameContext gc = base;                              // shares seeded RNG streams (CRN)
    gc.map = std::make_shared<Map>(*base.map);          // isolate map from the real run
    search::ScumSearchAgent2 inner;
    inner.simulationCountBase = innerSims;
    inner.rng = std::default_random_engine(seed);

    search::GameAction(search::GameAction::RewardsActionType::CARD, rIdx, cardIdx).execute(gc);

    int fights = 0;
    while (gc.outcome == GameOutcome::UNDECIDED && fights < N) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            inner.playoutBattle(bc);
            bc.exitBattle(gc);
            ++fights;
        } else {
            inner.stepOutOfCombatPolicy(gc);
        }
    }
    return useLabelScore ? labelScore(gc) : scoreLookaheadState(gc);
}

static void lookaheadCardPolicy(GameContext &gc, int N, int innerSims, int futures) {
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();

        double bestScore = -1e18;
        int bestIdx = 5;                         // 5 == skip
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = (cand < nCards) ? cand : 5;
            double acc = 0;
            for (int f = 0; f < futures; ++f) {
                std::uint64_t seed = gc.seed ^ (0x9e3779b97f4a7c15ULL * (f + 1));
                acc += rolloutChoice(gc, rIdx, cardIdx, N, innerSims, seed);
            }
            const double score = acc / futures;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        search::GameAction(search::GameAction::RewardsActionType::CARD, rIdx, bestIdx).execute(gc);
    }
}

// Whole run where the card-reward decision is either the weighted table or lookahead.
static RunResult runFullRunDraft(std::uint64_t seed, int outerSims, bool lookahead,
                                 int N, int innerSims, int futures, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;         // mirror stepRewardsPolicy ordering
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (lookahead)             lookaheadCardPolicy(gc, N, innerSims, futures);
            else                            agent.weightedCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void draftBench(int outerSims, int nSeeds, int N, int innerSims, int asc) {
    std::cout << "draft A/B   seeds 0.." << nSeeds - 1 << "   outerSims: " << outerSims
              << "   lookahead(N=" << N << ", innerSims=" << innerSims << ", CRN)"
              << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool lookahead = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunDraft((std::uint64_t)s, outerSims, lookahead, N, innerSims, 1, asc);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    lookahead ? "lookahead" : "weighted-table",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// GREEDY CARD-REWARD POLICY: a deterministic alternative to the built-in
// weightedCardRewardPolicy (which roulette-wheel samples over the weights and
// skips probabilistically). Here we take the argmax card and skip only when the
// best card isn't better than our current deck by a tunable ratio -- so the
// deck's average quality improves monotonically and stays leaner.
// ---------------------------------------------------------------------------
static double avgDeckObtain(const GameContext &gc) {
    long sum = 0;
    for (const auto &c : gc.deck.cards) {
        sum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    return gc.deck.size() > 0 ? (double)sum / gc.deck.size() : 0.0;
}

static void greedyCardRewardPolicy(GameContext &gc, double skipRatio) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();

        int bestIdx = 0, bestRaw = -1;
        double bestW = -1.0;
        for (int i = 0; i < n; ++i) {
            const auto &c = r.cardRewards[rIdx][i];
            const int raw = search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
            double w = std::pow((double)raw, 1.2);                 // same shaping as the baseline
            if (gc.act == 1 && c.getType() == CardType::ATTACK) {  // act-1 attack bias
                w *= 1.4;
            }
            if (w > bestW) { bestW = w; bestIdx = i; bestRaw = raw; }
        }

        // Take the best card unless it's not meaningfully better than our average
        // deck card (skipRatio=0 => never skip; higher => pickier / leaner deck).
        const bool skip = (double)bestRaw < skipRatio * avgDeckObtain(gc);
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// ---------------------------------------------------------------------------
// STATE-AWARE CARD VALUE FUNCTION: score a candidate card given the full run
// state (deck composition, relics, HP, act, ascension, upcoming fights). This
// generalises the flat getObtainWeight table -- picking among 3 cards is then
// just argmax(value), and "skip" is value-vs-a-state-dependent-bar.
// ---------------------------------------------------------------------------

// Rows until the nearest reachable ELITE from the current map position (99 if none
// remain on any reachable path). Used to gauge how soon a hard fight arrives.
static int rowsToNextElite(const GameContext &gc) {
    const Map &map = *gc.map;
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return 99;
        const MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        bool eliteHere = false;
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::ELITE) eliteHere = true;
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
        }
        if (eliteHere) return y - base;
        reach = nxt;
    }
    return 99;
}

// Forward-map features: ONE reachability sweep from the current node giving, for the
// remaining map, the min rows-to-next {elite,rest,shop,boss} and the count of reachable
// rooms of each type ahead. The map is deterministic/known, so this is free information
// the value model should have (it previously saw only pv* history + the next few fights).
struct FwdMap {
    int dElite = 99, dRest = 99, dShop = 99, dBoss = 0;
    int cElite = 0, cRest = 0, cShop = 0, cEvent = 0, cMonster = 0, cTreasure = 0;
};
static FwdMap forwardMapFeatures(const GameContext &gc) {
    FwdMap fm;
    fm.dBoss = 14 - std::max(gc.curMapNodeY, 0);
    if (gc.map == nullptr) return fm;
    const Map &map = *gc.map;
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return fm;
        const MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const MapNode &n = map.getNode(x, y);
            const int d = y - base;
            switch (n.room) {
                case Room::ELITE:    ++fm.cElite;    fm.dElite = std::min(fm.dElite, d); break;
                case Room::REST:     ++fm.cRest;     fm.dRest  = std::min(fm.dRest,  d); break;
                case Room::SHOP:     ++fm.cShop;     fm.dShop  = std::min(fm.dShop,  d); break;
                case Room::EVENT:    ++fm.cEvent;    break;
                case Room::MONSTER:  ++fm.cMonster;  break;
                case Room::TREASURE: ++fm.cTreasure; break;
                default: break;
            }
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
        }
        reach = nxt;
    }
    return fm;
}

static double evalCardValue(const GameContext &gc, const Card &c) {
    const CardType t = c.getType();
    if (t == CardType::CURSE || t == CardType::STATUS) return -1e9;   // never draft these

    double v = (double)search::Expert::getObtainWeight(c.getId(), c.isUpgraded());  // base prior

    const int act = gc.act;
    const int asc = gc.ascension;
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;

    // deck composition (ignore curses/status)
    int nAtk = 0, nSkill = 0, nPow = 0, nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt == CardType::CURSE || dt == CardType::STATUS) continue;
        ++nReal;
        if (dt == CardType::ATTACK) ++nAtk;
        else if (dt == CardType::SKILL) ++nSkill;
        else if (dt == CardType::POWER) ++nPow;
    }
    const double atkFrac = nReal > 0 ? (double)nAtk / nReal : 0.5;

    // (1) curve: aim ~48% attacks; reward the under-represented role.
    const double targetAtk = 0.48;
    if (t == CardType::ATTACK)     v += 25.0 * (targetAtk - atkFrac);
    else if (t == CardType::SKILL) v += 25.0 * (atkFrac - targetAtk);

    // (2) scaling / win-condition: powers scale and you need one by act 2-3;
    //     diminishing once the deck already has a couple.
    if (t == CardType::POWER) {
        v += 8.0 * act;
        if (nPow >= 3) v -= 10.0 * (nPow - 2);
    }

    // (3) raw impact (proxy: base damage of attacks).
    v += 0.4 * c.getBaseDamage();

    // (4) defensive lean when hurt or at high ascension.
    if ((hpFrac < 0.5 || asc >= 15) && t == CardType::SKILL) v += 8.0;

    // (5) upcoming-fight pressure: value power spikes / big hits before a wall.
    const int d = std::min(rowsToNextElite(gc), 15 - gc.curMapNodeY);
    if (d <= 2) {
        if (t == CardType::POWER) v += 6.0;
        v += 0.2 * c.getBaseDamage();
    }
    return v;
}

// Value bar below which we skip: rises with deck size and ascension (avoid
// diluting a big / high-ascension deck), and drops in act 1 (you need cards).
static double evalSkipBar(const GameContext &gc) {
    int nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt != CardType::CURSE && dt != CardType::STATUS) ++nReal;
    }
    double bar = 8.0 + 0.7 * nReal + 1.0 * gc.ascension;
    if (gc.act == 1) bar *= 0.5;
    return bar;
}

static void evalCardRewardPolicy(GameContext &gc, bool allowSkip = true) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestV = -1e18;
        for (int i = 0; i < n; ++i) {
            const double val = evalCardValue(gc, r.cardRewards[rIdx][i]);
            if (val > bestV) { bestV = val; bestIdx = i; }
        }
        const bool skip = allowSkip && (bestV < evalSkipBar(gc));
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// ---------------------------------------------------------------------------
// CAUSAL PER-CARD ADVANTAGE TABLE: offline-learned mean CRN take-vs-skip HP
// advantage per card id (build/card_adv_table.txt, from causalgen + shrinkage).
// Pure tempo signal: loves immediate damage/AoE, undervalues synergy/engine
// cards (it cannot see deck context). Used standalone (policy 5) and fused into
// the expert eval (policy 4).
// ---------------------------------------------------------------------------
static double g_cardAdv[512];
static bool   g_cardAdvSet[512] = {false};
static double g_cardAdvMean = 0.0;
static bool   g_cardAdvLoaded = false;
static double g_tableAlpha = 1.0;      // fusion weight of centered advantage

static void loadCardAdvTable(const std::string &path) {
    std::ifstream f(path);
    if (!f) { std::cerr << "WARNING: could not open card adv table: " << path << "\n"; return; }
    std::string line; double sum = 0; int cnt = 0;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream is(line);
        int id; double val;
        if (!(is >> id >> val)) continue;
        if (id >= 0 && id < 512) { g_cardAdv[id] = val; g_cardAdvSet[id] = true; sum += val; ++cnt; }
    }
    g_cardAdvMean = cnt ? sum / cnt : 0.0;
    g_cardAdvLoaded = true;
    std::cout << "loaded card-adv table (" << cnt << " cards, mean "
              << g_cardAdvMean << ", alpha " << g_tableAlpha << ") from " << path << "\n";
}

// raw learned advantage for a card (falls back to table mean if unseen)
static double cardAdvRaw(const Card &c) {
    int id = (int)c.getId();
    return (id >= 0 && id < 512 && g_cardAdvSet[id]) ? g_cardAdv[id] : g_cardAdvMean;
}
// centered advantage: unseen cards contribute ~0 (treated as average)
static double cardAdvCentered(const Card &c) { return cardAdvRaw(c) - g_cardAdvMean; }

// policy 4: expert eval + alpha * centered causal advantage
static void fusedCardRewardPolicy(GameContext &gc, bool allowSkip = true) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestV = -1e18;
        for (int i = 0; i < n; ++i) {
            const Card &c = r.cardRewards[rIdx][i];
            const double val = evalCardValue(gc, c) + g_tableAlpha * cardAdvCentered(c);
            if (val > bestV) { bestV = val; bestIdx = i; }
        }
        const bool skip = allowSkip && (bestV < evalSkipBar(gc));
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

// policy 5: pure causal table; causally-correct skip rule (take iff adv > 0)
static void tableCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestRaw = -1e18;
        for (int i = 0; i < n; ++i) {
            const Card &c = r.cardRewards[rIdx][i];
            const CardType t = c.getType();
            if (t == CardType::CURSE || t == CardType::STATUS) continue;
            const double raw = cardAdvRaw(c);
            if (raw > bestRaw) { bestRaw = raw; bestIdx = i; }
        }
        const bool skip = bestRaw <= 0.0;
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

static std::string featureRow(const GameContext &gc);      // defined below
static std::string deckCountsCsv(const GameContext &gc);   // defined below

// Accumulates room-type visit counts along the taken path (pv* features). Defined
// here (not just before datagen) because the deployment run loop tracks it too, so
// V queries carry the same path-history features the model was trained on.
struct PathHistory {
    std::array<int, 10> roomVisits{};   // indexed by (int)Room
    long lastNodeKey = -1;
    void update(const GameContext &gc) {
        if (gc.curMapNodeY < 0 || gc.curMapNodeY >= 15 || gc.curMapNodeX < 0 || gc.curMapNodeX >= 7)
            return;
        const long key = (long)gc.act * 100000 + (long)gc.curMapNodeY * 100 + gc.curMapNodeX;
        if (key == lastNodeKey) return;
        lastNodeKey = key;
        const int ri = (int)gc.getCurMapNode().room;
        if (ri >= 0 && ri < 10) ++roomVisits[ri];
    }
};
struct E2cFight {
    int index = -1, room = -1, encounter = -1;
    std::string raw, post, rawRelics, postRelics;
    bool rawSeen = false, postSeen = false;
    std::string screenTrace;
    std::string rewardRelics;
    int pendingCards = -1;
};
struct E2cRoomStats {
    int eligible = 0, raw = 0, post = 0, pairs = 0;
};
struct E2cCapture {
    std::uint64_t seed = 0;
    PathHistory *path = nullptr;
    std::vector<E2cFight> fights;
    E2cFight *current = nullptr;
    E2cRoomStats roomStats[3]{};
};
// Current run's path history, so vFeatCsv() can emit pv* features (nullptr = none).
static thread_local const PathHistory *t_curPath = nullptr;
static thread_local PathHistory t_emptyPath;    // pv* = 0 when no run path is set
static std::string richRow(const GameContext &gc, const PathHistory &path);  // defined below
static void strategicCands(const GameContext &gc, const search::GameAction &a,
                           int &actionType, int &c1, int &c2, int &c3,
                           int &cand1, int &cand2, int &cand3);  // defined below
static struct TokState buildTokState(const GameContext &gc, const PathHistory &path);  // defined below
static void tokEntity(const GameContext &gc, const search::GameAction &a,
                      int &entType, int &entId, float &goldGePrice);  // defined below
static std::string vFeatCsv(const GameContext &gc);                          // defined below
static std::string richHeader();                                             // defined below

// ---------------------------------------------------------------------------
// DECK-AWARE V VIA PYTHON BRIDGE: card picks are rare (~13/run) so we query the
// exact trained GBM held in v_server.py over a TCP socket. Card value =
// V(deck+card) - V(deck); the server returns the chosen index (or 5 = skip).
// One persistent connection per thread.
// ---------------------------------------------------------------------------
static int g_vPort = 5555;
static thread_local int t_vSock = -1;

// A benchmark run must not inherit a persistent server session from a previous
// seed in the same worker.  The protocol is request/response, but closing at a
// run boundary gives repeated-seed checks a clean, independently handled server
// connection and avoids any accidental socket-buffer/session carry-over.
static void vDisconnect() {
#ifndef _WIN32
    if (t_vSock >= 0) close(t_vSock);
#endif
    t_vSock = -1;
}
// Skip a card reward when the best candidate's marginal V(deck+card)-V(deck)
// (final-floor units) is below this. Default -0.5 (RICH V2): take a card unless it
// looks clearly diluting, skip only if marginal < -0.5. Re-swept @512 seeds asc0 on
// V2 -> best band -1.0..-0.25 (win 41-42%), peak -0.5=42.4% vs skip@0=38.7%; V2
// marginals read slightly pessimistic so a fuller deck wins. Positive thresholds
// still fall off a cliff. (Old deck-only V best was 0.0.) Override via STS_SKIP_THR.
static double g_cardSkipThresh = -0.5;
// A/B: route card picks through the WIN model (P(win) marginal) instead of V_floor.
// Own skip scale (win-prob units, ~0..0.05) so g_cardSkipThresh (floor units) doesn't apply.
static bool g_cardWin = false;          // env STS_CARD_WIN=1
static double g_cardWinSkip = 0.0;      // env STS_CARD_WIN_SKIP: skip iff best P(win) marginal < this
static bool g_shopWin = false;          // env STS_SHOP_WIN=1: score shop bundles by P(win) not V_floor
static bool g_nativeOoc = false;
static bool g_oocActionNN = false;          // env STS_OOC_ACTION_NN=1
static double g_oocStrategicMargin = 1.0;   // env STS_OOC_STRATEGIC_MARGIN: one-ply gate in V units
// Per-screen one-ply gate overrides (env STS_OOC_STRATEGIC_MARGIN_*): default
// -1.0 = unset, i.e. fall back to g_oocStrategicMargin so behavior is unchanged.
static double g_oocStrategicMarginCard = -1.0;      // STS_OOC_STRATEGIC_MARGIN_CARD
static double g_oocStrategicMarginRest = -1.0;      // STS_OOC_STRATEGIC_MARGIN_REST (rest + upgrade target)
static double g_oocStrategicMarginEvent = -1.0;     // STS_OOC_STRATEGIC_MARGIN_EVENT
static double g_oocStrategicMarginShop = -1.0;      // STS_OOC_STRATEGIC_MARGIN_SHOP
static double g_oocStrategicMarginTreasure = -1.0;  // STS_OOC_STRATEGIC_MARGIN_TREASURE
static double g_oocStrategicMarginBossRelic = -1.0; // STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC
static bool   g_oocStrategicQ = true;       // env STS_OOC_STRATEGIC_Q=0: score via V2 successor predictValue
static bool   g_oocStrategicScorePolicy = false; // env STS_OOC_STRATEGIC_SCORE=policy: one-ply gates score with sigmoid(policy logit) (5.7.2)
static bool   g_oocStrategicRest = false;   // env STS_OOC_STRATEGIC_REST=1: one-ply Q gate on campfires (5.5.2)
static bool   g_datagenGates = false;       // env STS_DATAGEN_GATES=1: combatgen/distgen OOC decisions route through the one-ply gate chain (§127)
static bool   g_oocStrategicEvent = false;  // env STS_OOC_STRATEGIC_EVENT=1: one-ply Q gate on events (5.5.3)
static bool   g_oocStrategicShop = false;    // env STS_OOC_STRATEGIC_SHOP=1: one-ply Q gate on shop buys (R6)
static bool   g_oocStrategicTreasure = false; // env STS_OOC_STRATEGIC_TREASURE=1: one-ply Q gate on treasure (R6)
static bool   g_oocStrategicBossRelic = false; // env STS_OOC_STRATEGIC_BOSS_RELIC=1: one-ply Q gate on boss relics (R6)
static bool   g_oocStrategicMap = false;     // env STS_OOC_STRATEGIC_MAP=1: one-ply Q gate on map routes (M1)
static double g_oocStrategicMarginMap = -1.0; // env STS_OOC_STRATEGIC_MARGIN_MAP (default -1.0 = fall back to global)
// Wave B regret gate (ooc-qwin-continuation.md Step 5): decision rule
// Qmax(s) − Q(a_heur) > ε for every one-ply gate and the M2 route search.
// a_heur is the deployed-default heuristic action, identified by the
// datagen-proven successor-fingerprint match; when it cannot be identified
// (RNG-tied divergence) the policy falls back to the margin rule.
static bool   g_oocStrategicGateRegret = false; // env STS_OOC_STRATEGIC_GATE=regret
static double g_oocStrategicGateEps = 0.03;     // env STS_OOC_STRATEGIC_GATE_EPS: regret threshold ε
// M2 short-horizon map route search (plan 5.6.2): C_psi combat surrogate +
// strategic V head at the leaf. Hidden-info clean: encounters/bosses are
// sampled from the act's visible pool, never the true future.
static bool   g_oocMapRoute = false;         // env STS_OOC_MAP_ROUTE=1
static int    g_oocMapRouteHorizon = 3;      // env STS_OOC_MAP_ROUTE_HORIZON (clamped 2..5)
static search::CombatCpsiNet g_cpsiNet;      // env STS_CPSI_NN=<path>: combat outcome surrogate
static int    g_oocStrategicTok = 0;        // env STS_OOC_STRATEGIC_TOK_NN: V4 token net loaded
static bool   g_oocStrategicTokCheck = false; // env STS_OOC_STRATEGIC_TOK_CHECK=1: first-decision glob parity hook
static std::string g_oocStrategicTracePath;
static std::mutex g_oocStrategicTraceMutex;
static thread_local std::string t_oocStrategicTraceRows;
static thread_local int t_oocStrategicTraceDecision = 0;
static thread_local bool t_tokCheckPending = false;  // armed per run; consumed by the first gated decision
static thread_local bool t_shopV = false;            // runFullRunOOC's shopV param, for the regret SHOP probe
// Terminal-leaf run-value bonus (cross-combat setup, e.g. Happy Flower):
// STS_TERM_WIN=1 prices Searcher3 terminal VICTORY leaves with the native win
// model on the post-combat run state (weight STS_TERM_WIN_W, default 100;
// STS_TERM_WIN_HIDDEN=resample|zero for the future-fight features;
// STS_TERM_WIN_EVAL=win|cpsi picks the evaluator: the win tree, or the C_psi
// next-fight survival model, which the cpsictr probe shows prices the
// counters correctly).
static bool   g_termWin = false;
static double g_termWinW = 100.0;
static int    g_termWinHidden = 1;      // 1 = resample the act pool, 0 = zero hidden feats
static int    g_termWinEval = 0;        // 0 = win tree, 1 = C_psi next-fight survival
// Forced relic at run start (benchmark): STS_FORCE_RELIC=<NAME> grants the
// relic (counter data 0) and removes it from the draw pools so the run cannot
// naturally roll a duplicate. Enables paired A/B with the relic guaranteed.
static RelicId g_forceRelic = RelicId::INVALID;
// Per-combat stall telemetry: STS_TERM_STALL_LOG=<path> appends one CSV row
// per battle (turns, end HP/gold/potions, counter positions) so the terminal
// bonus's stall behavior can be checked directly.
static std::string g_stallLogPath;
static thread_local const GameContext *t_termGc = nullptr;
static thread_local std::vector<float> t_termBaseRow;
static thread_local bool t_termParityChecked = false;
// C_psi counter-sensitivity probe (diagnostic): STS_CPSI_CTR_PROBE=1
// accumulates, at every post-combat state of runFullRunOOC runs, the
// predicted next-fight P(death)/P(win) deltas when each owned counter relic's
// cpsi scalar is set to each of its possible counter values (vs the state's
// own counter). Needs STS_CPSI_NN. Reported by the cpsictr mode.
static bool g_cpsiCtrProbe = false;
// B1 shop beam search (ooc-next-wave-contracts.md §2): multi-step lookahead over
// deterministic shop purchases, replacing the one-ply shop gate when enabled.
static bool   g_oocShopBeam = false;        // env STS_OOC_SHOP_BEAM=1
static int    g_oocShopBeamWidth = 32;      // env STS_OOC_SHOP_BEAM_WIDTH (clamped 4..256)
static int    g_oocShopBeamDepth = 0;       // env STS_OOC_SHOP_BEAM_DEPTH (0 = until leave / no affordable actions)
static int    g_oocShopBeamBudget = 4096;   // env STS_OOC_SHOP_BEAM_BUDGET: max expanded nodes per shop decision
static int nativeFloorCardPick(GameContext &, int);
static double nativeFloorValue(GameContext &);
static bool oocOnePlyCardRewardPolicy(GameContext &, const search::ScumSearchAgent2 &);
static bool oocOnePlyRestPolicy(GameContext &, const search::ScumSearchAgent2 &);        // 5.5.2 campfire options + upgrade targets
static bool oocOnePlyUpgradeSelectPolicy(GameContext &, const search::ScumSearchAgent2 &); // 5.5.2 smith upgrade-target pick
static bool oocOnePlyEventPolicy(GameContext &, const search::ScumSearchAgent2 &);       // 5.5.3 event options
static bool oocOnePlyShopPolicy(GameContext &, const search::ScumSearchAgent2 &);        // R6 shop buys (incl. remove/leave)
static bool oocShopBeamPolicy(GameContext &);          // B1 multi-step shop beam search (§2)
static bool oocOnePlyTreasurePolicy(GameContext &, const search::ScumSearchAgent2 &);    // R6 treasure chests
static bool oocOnePlyBossRelicPolicy(GameContext &, const search::ScumSearchAgent2 &);   // R6 boss relic picks
static bool oocMapRouteSearchPolicy(GameContext &);    // M2 C_psi route search (defined below)
struct StratFingerprint;                               // successor-state digest (defined below)
static StratFingerprint stratFingerprint(const GameContext &);
// Wave B regret decision: returns the index of the action to take (Q-max when
// Qmax − Q(a_heur) > eps, else a_heur), or -1 when a_heur is unidentifiable
// (caller falls back to the margin rule). Runs `heuristic` on a pre-state copy
// with a copied agent RNG stream and matches the successor fingerprint.
static int regretGateChoose(const GameContext &, const std::vector<search::GameAction> &,
                            const std::vector<double> &, double,
                            void (*)(GameContext &, search::ScumSearchAgent2 &),
                            const search::ScumSearchAgent2 &);
static bool regretGateTail(GameContext &, const std::vector<search::GameAction> &,
                           const std::vector<double> &, int, double, double, double, double,
                           void (*)(GameContext &, search::ScumSearchAgent2 &),
                           const search::ScumSearchAgent2 &);
// ---------------------------------------------------------------------------
// C_psi counter-sensitivity probe (diagnostic): at every post-combat state,
// for each counter relic the run owns, re-predict the next-fight outcome with
// that relic's counter scalar set to each possible value (0..k-1) and
// accumulate the mean ΔP(death)/ΔP(win) vs the state's own counter, averaged
// over the six fixed probe encounters (TWO_LOUSE/GREMLIN_NOB/LAGAVULIN/
// THREE_SENTRIES/SLIME_BOSS/THE_GUARDIAN — same probes as probe_cpsi.py).
// Answers "does ANY trained model price the counters": the deployed GBMs do
// not (0 tree splits on every counter feature in v_win/v_rich). Sensitivity
// != correctness — these labels are observational (counter confounded with
// fight length), so the SIGN of the deltas is the finding; only counterfactual
// datagen gives ground truth.
// ---------------------------------------------------------------------------
struct CpsiCtrAccum {
    struct Relic {
        RelicId id = RelicId::INVALID;
        int scalarIdx = -1;
        int k = 0;
        int states = 0;
        int baseHist[10] = {};
        double sumBaseDeath = 0;
        double sumDeath[10] = {};
        double sumWin[10] = {};
    };
    std::vector<Relic> relics;
    int states = 0;
    long long forwards = 0;
    double wallSec = 0;
    bool ready = false;
};
static CpsiCtrAccum g_cpsiCtrAccum;

static void cpsiCounterProbeAtState(const GameContext &gc) {
    if (!g_cpsiNet.loaded()) return;
    CpsiCtrAccum &acc = g_cpsiCtrAccum;
    if (!acc.ready) {
        // (relic, cpsi scalar slot, counter value range) — mirrors
        // buildCpsiEntry's scalar[3..9] order and each relic's trigger range.
        const CpsiCtrAccum::Relic slots[] = {
            {RelicId::HAPPY_FLOWER, 3, 3},  {RelicId::INCENSE_BURNER, 4, 6},
            {RelicId::INK_BOTTLE, 5, 10},   {RelicId::INSERTER, 6, 2},
            {RelicId::NUNCHAKU, 7, 10},     {RelicId::PEN_NIB, 8, 10},
            {RelicId::SUNDIAL, 9, 3},
        };
        for (const auto &s : slots) acc.relics.push_back(s);
        acc.ready = true;
    }
    const auto t0 = std::chrono::steady_clock::now();
    static constexpr int probeEncounters[6] = {3, 15, 16, 17, 18, 19};
    float scalar[search::kCpsiScalars];
    float deck[search::kCpsiCards], relics[search::kCpsiRelics], potions[search::kCpsiPotions];
    search::buildCpsiEntry(gc, scalar, deck, relics, potions);
    for (CpsiCtrAccum::Relic &r : acc.relics) {
        if (!gc.hasRelic(r.id)) continue;
        ++acc.states;
        ++r.states;
        const int base = (int)scalar[r.scalarIdx];
        if (base >= 0 && base < r.k) ++r.baseHist[base];
        double baseDeath = 0, baseWin = 0;
        for (int e : probeEncounters) {
            search::CpsiOut o;
            g_cpsiNet.predict(scalar, deck, relics, potions, e, o);
            ++acc.forwards;
            baseDeath += o.death;
            baseWin += o.win;
        }
        r.sumBaseDeath += baseDeath / 6;
        const float save = scalar[r.scalarIdx];
        for (int c = 0; c < r.k; ++c) {
            if (c == base) continue;
            scalar[r.scalarIdx] = (float)c;
            double dSum = 0, wSum = 0;
            for (int e : probeEncounters) {
                search::CpsiOut o;
                g_cpsiNet.predict(scalar, deck, relics, potions, e, o);
                ++acc.forwards;
                dSum += o.death;
                wSum += o.win;
            }
            r.sumDeath[c] += (dSum - baseDeath) / 6;
            r.sumWin[c] += (wSum - baseWin) / 6;
        }
        scalar[r.scalarIdx] = save;
    }
    acc.wallSec += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

static void cpsiCtrProbeReport() {
    const CpsiCtrAccum &acc = g_cpsiCtrAccum;
    static const char *const names[] = {"HAPPY_FLOWER", "INCENSE_BURNER",
                                        "INK_BOTTLE", "INSERTER", "NUNCHAKU",
                                        "PEN_NIB", "SUNDIAL"};
    std::printf("cpsi counter probe: %d post-combat states probed, %lld forwards, %.1f us/forward (mean over 6 fixed encounters, delta vs state's own counter)\n",
                acc.states, acc.forwards, acc.forwards > 0 ? acc.wallSec / acc.forwards * 1e6 : 0.0);
    std::printf("%-14s %6s %8s  %s\n", "relic", "states", "base death", "mean delta per counter value");
    for (int i = 0; i < (int)acc.relics.size() && i < 7; ++i) {
        const CpsiCtrAccum::Relic &r = acc.relics[i];
        const double n = r.states > 0 ? (double)r.states : 1.0;
        std::printf("%-14s %6d %8.4f  death", names[i], r.states, r.sumBaseDeath / n);
        for (int c = 0; c < r.k; ++c) std::printf("  c%d %+.4f", c, r.sumDeath[c] / n);
        std::printf("\n");
        std::printf("%-14s %6s %8s  win  ", "", "", "");
        for (int c = 0; c < r.k; ++c) std::printf("  c%d %+.4f", c, r.sumWin[c] / n);
        std::printf("\n");
        if (r.states > 0) {
            std::printf("%-14s %6s %8s  base [", "", "", "");
            for (int c = 0; c < r.k; ++c) std::printf("%d:%d ", c, r.baseHist[c]);
            std::printf("]\n");
        }
    }
}
static std::string nativeShopPlan(GameContext &);
// Terminal-leaf run-value bonus (implementation after the rich feature block).
static double termLeafBonus(const BattleContext &);
static void termWinArmForBattle(GameContext &);
static void termWinDisarm();
static void resampleRemainingActEncounters(GameContext &, std::uint64_t);
// Per-combat stall telemetry (defined with the terminal-leaf bonus block).
static void stallLogRow(const GameContext &, const BattleContext &, std::uint64_t);
// A/B: route card picks through the deck-set NN (P(win) marginal), optionally blended with
// the v_win GBM: marg = w*NN + (1-w)*GBM. Own skip scale (P(win) units).
static bool   g_cardNN     = false;     // env STS_CARD_NN=1
static double g_cardNNW    = 1.0;       // env STS_CARD_NN_W: blend weight on NN (1=pure NN)
static double g_cardNNSkip = 0.0;       // env STS_CARD_NN_SKIP: skip iff best P(win) marginal < this
// Direct paired action-value model (offered cards + skip), optionally with the
// full map graph. Unlike marginal value models, it learns its own skip action.
static bool   g_cardAction = false;     // env STS_CARD_ACTION=1 (CA server op)
// Datagen exploration: softmax temperature over card marginals (final-floor
// units; higher = more spread). The uniform-floor prob is datagen2's `epsilon`.
static double g_dgTemp = 2.0;   // env STS_DG_TEMP (swept: 1-2 good spread+quality, >=3 over-randomizes)
// Per-fight combat sim budget by difficulty (env STS_SIMS_NORMAL/ELITE/BOSS; <=0 or
// unset = use the run's base sims). Deaths cluster at elites/bosses, so we can search
// those deep and skimp on trivial hallway fights for the same win% at far less compute.
static int g_simsNormal = -1, g_simsElite = -1, g_simsBoss = -1;
// Dynamic per-fight budget via the C_psi no-peek combat outcome surrogate
// (STS_SIM_ADAPT=1 + STS_CPSI_NN, EXPERIMENTS.md §103): one forward pass at fight
// start predicts P(death) and E[hp/maxHp|win]; the budget multiplier rises with
// predicted danger. Learned tiering — unlike the static STS_SIMS_* room tiers it
// cannot misjudge difficulty (act-3 monsters ~ act-1 elites, §21). buildCpsiEntry
// uses only pre-combat state, so this is fair-play clean. Takes precedence over
// the static tiers when enabled.
static bool   g_simAdapt = false;       // env STS_SIM_ADAPT=1
static double g_simAdaptMinFrac = 0.4;  // env STS_SIM_ADAPT_MIN_FRAC: budget floor as a fraction of base
static double g_simAdaptMaxFrac = 2.0;  // env STS_SIM_ADAPT_MAX_FRAC: budget ceiling as a fraction of base
// Pick the sim budget for the fight in the current room (falls back to base).
static int fightSims(const GameContext &gc, int base) {
    if (g_simAdapt && g_cpsiNet.loaded() && gc.info.encounter != MonsterEncounter::INVALID) {
        float scalar[search::kCpsiScalars], deck[search::kCpsiCards],
              relics[search::kCpsiRelics], potions[search::kCpsiPotions];
        search::buildCpsiEntry(gc, scalar, deck, relics, potions);
        search::CpsiOut r;
        g_cpsiNet.predict(scalar, deck, relics, potions, (int)gc.info.encounter, r);
        const double m = 0.5 + 1.0 * r.death + 1.0 * (1.0 - r.hp);  // danger = P(death) + expected HP loss
        const double frac = std::min(g_simAdaptMaxFrac, std::max(g_simAdaptMinFrac, m));
        return std::max(1, (int)std::llround(base * frac));
    }
    if (gc.curRoom == Room::BOSS || gc.curRoom == Room::BOSS_TREASURE) return g_simsBoss  > 0 ? g_simsBoss  : base;
    if (gc.curRoom == Room::ELITE)                                     return g_simsElite > 0 ? g_simsElite : base;
    return g_simsNormal > 0 ? g_simsNormal : base;   // MONSTER / event fights
}

// --- boss-aware drafting: for card picks near a hard fight, lean on a boss signal
// (either a rollout, or the boss-survival value model v_boss blended with v_rich).
// The gate is factored so the hard-fight set can later become DYNAMIC (learned from
// where we die); boss-only for now.
static int    g_bossDraft        = 0;      // STS_BOSS_DRAFT: rollout-based near-boss draft (experimental; hurt in A/B)
static int    g_bossDraftRows    = 3;      // trigger when a hard fight is within this many map rows
static int    g_bossDraftN       = 4;      // rollout: fights to simulate forward
static int    g_bossDraftSims    = 150;    // rollout: inner combat sim budget
static int    g_bossDraftFutures = 2;      // rollout: sampled futures per candidate
static int    g_bossV            = 0;      // STS_BOSS_V: blend v_boss marginal into near-boss server picks
static double g_bossVW           = 0.5;    // STS_BOSS_V_W: blend weight on the boss model (0..1)

// Experimental full-act draft evaluator.  For the immediate card decision only,
// it samples the *possible remaining encounter queues* in the current act and
// plays every fight on the selected route through the boss.  Its utility is an
// expectation over survival and a nonlinear post-fight HP safety margin, with a
// modest floor-distance discount.  It intentionally makes no V/card-model query
// for the card being picked; the regular OOC policy is used only inside a sampled
// continuation to resolve later choices.
static bool   g_actFightProbeDraft = false; // STS_ACT_FIGHT_PROBE_DRAFT=1
static int    g_actFightProbeSims = 100;    // STS_ACT_FIGHT_PROBE_SIMS
static int    g_actFightProbeFutures = 4;   // STS_ACT_FIGHT_PROBE_FUTURES
static double g_actFightProbeFloorDecay = 0.985; // STS_ACT_FIGHT_PROBE_FLOOR_DECAY
// Optional inner-search base budgets by reached checkpoint, e.g. 400,200,100.
// The live run's combat budget is unaffected; room-tier overrides still take
// precedence through fightSims().
static std::vector<int> g_actFightProbeCheckpointSims; // STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS
// -1 scores every remaining fight in the current act; a positive value scores only the
// next N combat checkpoints.  This is a horizon in fights, not map nodes, so
// routes with shops/events are not given a structurally different objective.
static int    g_actFightProbeMaxCheckpoints = -1; // STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS
static bool   g_actFightProbeTrace = false; // STS_ACT_FIGHT_PROBE_TRACE=1
// Parallelize the independent immediate-action × sampled-future branches of a
// single OOC decision.  Off by default so ordinary multi-seed benches retain
// their existing outer OpenMP scheduling.
static bool   g_actFightProbeParallelBranches = false; // STS_ACT_FIGHT_PROBE_PARALLEL=1
// Broader version used only for a deliberately expensive Act-1 experiment:
// evaluate every legal OOC action (map, rewards, events, shop, rest, selects),
// not just cards.  This is separate so the card-only oracle remains available.
static bool   g_actFightProbeAllOoc = false; // STS_ACT_FIGHT_PROBE_ALL_OOC=1
// Score and advance checkpoint fights with the entity combat model instead of
// running MCTS.  This is deliberately separate from STS_VNET: the latter is a
// leaf evaluator inside real combat search, while this one supplies both heads
// needed for a virtual post-combat transition.
static bool   g_actFightProbePredict = false; // STS_ACT_FIGHT_PROBE_PREDICT=1
static bool   g_actFightProbeEncounterNN = false; // STS_ACT_FIGHT_PROBE_ENCOUNTER_NN=1
static double g_actFightProbePredictWinThreshold = 0.5;
static std::string g_actFightProbePredictNetPath = "selfplay/models/v_combat_entity_iter34.txt";
static search::CombatValueNet g_actFightProbePredictNet;
// Optional terminal pricing for the capped checkpoint objective: after the
// final scored checkpoint, price each option's resulting branch state with the
// native win model (P(run victory)) and add it to the utility, blended by this
// weight.  HP-only checkpoint safety misses resource compounding (gold, relics,
// deck) that the trunk simulation carries forward but never prices.
static double g_actFightProbeTermWin = 0.0; // STS_ACT_FIGHT_PROBE_TERM_WIN=alpha (0 = off)
// Margin gate: when > 0, the all-OOC oracle overrides a decision only if its
// best action's utility beats the runner-up by at least this margin; otherwise
// control falls through to the ordinary policy stack.  Greedy full-run oracle
// replacement is a recorded regression (EXPERIMENTS.md 66j/66m/67); the margin
// is the design-doc deployment contract for learned override layers.
static double g_actFightProbeMargin = 0.0; // STS_ACT_FIGHT_PROBE_MARGIN=m (0 = always fire)
static int    g_stopAfterAct = 0;            // STS_STOP_AFTER_ACT=N, benchmark horizon
// Optional durable per-action teacher data for the all-OOC oracle.  The file
// is append-only because benchmark runs may be stopped and resumed.
static std::string g_actFightProbeLogPath;   // STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv
static std::ofstream g_actFightProbeLog;
static std::mutex g_actFightProbeLogMutex;
static thread_local int t_actFightProbeDecisionIdx = 0;
static thread_local int t_actFightProbeActionIdx = -1;
static thread_local int t_actFightProbeFutureIdx = -1;

static int actFightProbeCheckpointSims(int defaultSims, int checkpointIdx) {
    if (checkpointIdx >= 0 && checkpointIdx < (int)g_actFightProbeCheckpointSims.size())
        return g_actFightProbeCheckpointSims[checkpointIdx];
    return defaultSims;
}

// --- strategicgen2 (Tier-B one-ply labels) knobs ---
// Per sampled decision, every legal action is branched from a pre-decision copy
// and continued with the deployed-default OOC policy through K=BRANCH_FIGHTS
// battles at STRATEGIC_BRANCH_SIMS sims each, then bootstrapped with the native
// floor/win trees. The same branch seed per decision gives common random
// numbers across actions; STRATEGIC_BRANCH_FUTURES averages over extra seeds.
static int g_strategicSamplesPerRun = 1;    // STRATEGIC_SAMPLES_PER_RUN: reservoir size
static bool g_strategicSampleAll = false;   // STRATEGIC_SAMPLE_ALL=1: label every decision
static int g_strategicBranchFights = 3;     // STRATEGIC_BRANCH_FIGHTS: battles per branch
static std::vector<int> g_strategicBranchSims = {150, 100, 50}; // STRATEGIC_BRANCH_SIMS per fight
static int g_strategicBranchFutures = 1;    // STRATEGIC_BRANCH_FUTURES: branch seeds per action

static std::string actFightProbeCheckpointSimsCsv() {
    std::ostringstream out;
    for (int i = 0; i < (int)g_actFightProbeCheckpointSims.size(); ++i) {
        if (i) out << ';';
        out << g_actFightProbeCheckpointSims[i];
    }
    return out.str();
}

// --- V-informed pathing: the next-fight features are a shared encounter QUEUE
// (route-independent at a decision), so V(state) is ~flat across immediate map
// children -> per-child V scoring gives no signal. Instead use V(state) as a
// deck-STRENGTH scalar (predicted final floor) to MODULATE the heuristic's
// aggression: a strong deck routes harder into elites/fights (farm relics while
// you can), a weak deck routes to rest/shop/event (recover). One V query/floor.
static int    g_vPath  = 0;      // STS_VPATH=1: enable V-strength path modulation
static double g_vPathK = 0.4;    // STS_VPATH_K: modulation gain (0=off .. ~1 strong)
// aggression for the current map decision, in [-1,+1]; set once per chooseMapAction
// call, read by roomValue. 0 = neutral (= plain heuristic).
static thread_local double t_pathAggr = 0.0;
// Act boss floors (finalFloor at which each act's boss sits) — the deck-strength
// anchor: predFloor - bossFloor[act] = how comfortably you clear this act.
static int bossFloorForAct(int act) { return act <= 1 ? 17 : act == 2 ? 34 : 50; }

// Map rows until the next hard fight. Boss sits just past the last map row (14),
// so rows-to-boss = 14 - curMapNodeY. (Extend to fold in elites / learned high-death
// floors for the dynamic version.)
static int rowsToHardFight(const GameContext &gc) {
    return 14 - std::max(gc.curMapNodeY, 0);
}

// --- potion-saving policy: the combat search is per-fight MYOPIC (optimizes THIS
// fight's end HP), so it spends potions on easy fights with no incentive to bank
// them for elites/bosses -- where we actually die. evaluateEndState already values
// a KEPT potion at g_potionKeepValue HP-equiv (drinking costs that much), so we make
// that value DYNAMIC per fight: high in easy fights when a hard fight is near (hoard),
// low in the hard fight itself (spend). Modulated by the potion DROP chance -- if we'll
// likely refill before the hard fight (high potionChance / White Beast Statue = 100%),
// there's less need to save the current one.
static int    g_potionSave    = 0;      // STS_POTION_SAVE=1: enable dynamic potion keep-value
static int    g_potionWindow  = 5;      // STS_POTION_WINDOW: only save when a hard fight is <= this many rows away
static double g_potionBonus   = 18.0;   // STS_POTION_BONUS: extra HP-equiv keep-value at max urgency
static double g_potionSpend   = 1.0;    // STS_POTION_SPEND: keep-value DURING an elite/boss (low = spend)
static double g_potionDesired = 2.5;    // STS_POTION_DESIRED: potions we'd like entering a hard fight
static const double kPotionBaseKeep = 4.0;   // the engine's original constant (neutral default)

// Per-fight potion keep-value (HP-equiv), set into search::g_potionKeepValue before combat.
static double potionKeepValue(const GameContext &gc) {
    if (!g_potionSave) return kPotionBaseKeep;
    const Room r = gc.curRoom;
    if (r == Room::ELITE || r == Room::BOSS || r == Room::BOSS_TREASURE)
        return g_potionSpend;                       // the hard fight itself -> spend freely
    const int hardDist = std::min(rowsToNextElite(gc), rowsToHardFight(gc));  // rows to nearest elite/boss
    if (hardDist <= 0 || hardDist > g_potionWindow) return kPotionBaseKeep;   // nothing hard soon
    const double p = gc.hasRelic(RelicId::WHITE_BEAST_STATUE)
                       ? 1.0 : std::clamp((double)gc.potionChance / 100.0, 0.0, 1.0);
    const double expDrops  = hardDist * p;          // potions we'll likely gain before the hard fight
    const double scarcity  = std::clamp(1.0 - expDrops / g_potionDesired, 0.0, 1.0);  // less save if refilling
    const double proximity = (double)(g_potionWindow - hardDist + 1) / g_potionWindow; // closer = more urgent
    return kPotionBaseKeep + g_potionBonus * proximity * scarcity;
}

static int vConnect() {
    if (t_vSock >= 0) return t_vSock;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)g_vPort);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    // A missing localhost server must not stall a native bestbench forever:
    // WSL can leave a blocking connect in SYN-SENT when port 5555 is absent.
    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags >= 0) fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    const int rc = connect(fd, (sockaddr *)&addr, sizeof(addr));
    if (rc < 0 && errno != EINPROGRESS) { close(fd); return -1; }
    if (rc < 0) {
        fd_set writable, errors;
        FD_ZERO(&writable); FD_SET(fd, &writable);
        FD_ZERO(&errors); FD_SET(fd, &errors);
        timeval timeout{1, 0};
        const int ready = select(fd + 1, nullptr, &writable, &errors, &timeout);
        if (ready <= 0 || FD_ISSET(fd, &errors)) { close(fd); return -1; }
        int error = 0; socklen_t errorLen = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &errorLen) < 0 || error != 0) {
            close(fd); return -1;
        }
    }
    if (flags >= 0) fcntl(fd, F_SETFL, flags);
    t_vSock = fd;
    return fd;
}

// Inference requests are idempotent.  Never turn a transient socket failure or
// short write into a strategic fallback (card skip, empty shop plan, etc.):
// reconnect and replay the complete request.  The old one-shot send() path
// silently changed decisions when a persistent connection was dropped.
static std::string vRequestLine(const std::string &requestWithNewline) {
    // Model loading (especially the optional Torch model) can take several
    // seconds.  A fixed launcher sleep previously let the first benchmark run
    // race server readiness and silently use fallbacks, while later runs used
    // the real policy.  Wait through cold start as well as retrying dropped
    // persistent connections.
    constexpr int maxAttempts = 50;
    for (int attempt = 0; attempt < maxAttempts; ++attempt) {
        int fd = vConnect();
        if (fd < 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        std::size_t sent = 0;
        while (sent < requestWithNewline.size()) {
            const ssize_t n = send(fd, requestWithNewline.data() + sent,
                                   requestWithNewline.size() - sent, 0);
            if (n <= 0) break;
            sent += static_cast<std::size_t>(n);
        }
        if (sent != requestWithNewline.size()) {
            vDisconnect();
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        char buf[8192];
        std::string response;
        while (response.find('\n') == std::string::npos) {
            const ssize_t n = recv(fd, buf, sizeof(buf), 0);
            if (n <= 0) break;
            response.append(buf, static_cast<std::size_t>(n));
        }
        const auto newline = response.find('\n');
        if (newline != std::string::npos) {
            response.resize(newline + 1);
            return response;
        }
        vDisconnect();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return {};
}

static std::string mapGraphCsv(const GameContext &gc, bool rooms) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const MapNode &node = gc.map->getNode(x, y);
        if (rooms) {
            out << static_cast<int>(node.room);
        } else {
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << edgeMask;
        }
    }
    return out.str();
}

static std::string mapSpecialCsv(const GameContext &gc) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const bool burning = !gc.greenKey && x == gc.map->burningEliteX && y == gc.map->burningEliteY;
        out << (burning ? 1 : 0);
    }
    return out.str();
}

// send a tagged candidate/state query and read back the chosen index.
// bossW >= 0 routes the pick through the boss-survival blend "CB;<w>;..." (the
// server returns the chosen card's v_rich marginal, so the skip logic is unchanged).
static int vQuery(GameContext &gc, int rIdx, double bossW = -1.0) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    if (g_nativeOoc && bossW < 0.0 && !g_cardWin && !g_cardNN && !g_cardAction)
        return nativeFloorCardPick(gc, rIdx);
    std::string req;
    if (g_cardAction) req += "CA;";                           // direct card/skip action value
    else if (bossW >= 0.0) { req += "CB;"; req += std::to_string(bossW); req += ';'; }  // boss-V blend
    else if (g_cardNN) { req += "CN;"; req += std::to_string(g_cardNNW); req += ';'; }  // deck-set NN marginal
    else if (g_cardWin) req += "CW;";   // route card pick through the win model (P(win) marginal)
    for (int i = 0; i < n; ++i) {
        if (i) req += ',';
        const Card &card = r.cardRewards[rIdx][i];
        req += std::to_string((int)card.getId());
        if (g_cardAction) { req += ':'; req += card.isUpgraded() ? '1' : '0'; }
    }
    req += ';';
    if (g_cardAction) {
        req += mapGraphCsv(gc, true); req += ';';
        req += mapGraphCsv(gc, false); req += ';';
        req += mapSpecialCsv(gc); req += ';';
    }
    req += vFeatCsv(gc);        // full rich feature vector (richRow schema)
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return 5;
    // server returns "<best_idx> <best_marginal>"; apply the skip threshold here
    int idx = 5; double marg = -1e9;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &marg) < 1) return 5;
    if (idx < 0 || (idx >= n && idx != 5)) return 5;
    if (g_actFightProbeTrace) {
        std::cerr << "[card-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " candidates=";
        for (int i = 0; i < n; ++i)
            std::cerr << (i ? ";" : "") << (int)r.cardRewards[rIdx][i].getId();
        std::cerr << " reqHash=" << std::hash<std::string>{}(req)
                  << " response=" << idx << ':' << marg << "]\n";
    }
    // boss blend returns a floor-scale v_rich marginal, so use the floor skip bar there
    const double skipThr = (bossW >= 0.0) ? g_cardSkipThresh
                         : g_cardNN        ? g_cardNNSkip
                         : (g_cardWin ? g_cardWinSkip : g_cardSkipThresh);
    if (!g_cardAction && idx != 5 && marg < skipThr) return 5; // direct action model selects skip itself
    return idx;
}

// Raw V(state) = predicted final floor for the current state (server "VS" op).
// Used as a deck-strength scalar for V-informed pathing. Returns a large sentinel
// (so aggr clamps to neutral-ish) if the server is unreachable.
static double vStateRaw(GameContext &gc) {
    if (g_nativeOoc) return nativeFloorValue(gc);
    std::string req = "VS;";
    req += vFeatCsv(gc);
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return -1e9;
    double v = -1e9;
    if (std::sscanf(resp.c_str(), "%lf", &v) < 1) return -1e9;
    return v;
}

// Generic one-line request/response to the value server (for trace tooling).
static std::string vSendRecv(const std::string &reqNoNl) {
    std::string req = reqNoNl; req += '\n';
    return vRequestLine(req);
}

// forward decls (native V_win helpers are defined below with the WinNet struct)
static const std::unordered_map<std::string,int> &richIdxMap();
static std::vector<float> richFeatureVec(GameContext &gc);
static bool   winNetOk();
static double winNetPredict(const std::vector<float> &raw);

// Native win-model card pick (P(win) marginal), mirrors server decide_win but socket-free.
static int nativeWinCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int nc = r.cardRewards[rIdx].size();
    const auto &idx = richIdxMap();
    const std::vector<float> base = richFeatureVec(gc);
    const double b = winNetPredict(base);
    const int dsz = idx.at("deckSize");
    int barg = 0; double bmarg = -1e18;
    for (int i = 0; i < nc; ++i) {
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        std::vector<float> v = base;
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) v[it->second] += 1.0f;
        v[dsz] += 1.0f;
        const double m = winNetPredict(v) - b;
        if (m > bmarg) { bmarg = m; barg = i; }
    }
    return bmarg < g_cardWinSkip ? 5 : barg;    // skip if best marginal below the win-scale bar
}

// policy 6: query the deck-aware GBM server for each card reward
static void serverCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        // near a hard fight, blend the boss-survival marginal into the pick
        const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
        // native win-model card pick when available (self-play unified policy) -> no socket
        const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                  : vQuery(gc, rIdx, bossW);
        search::GameAction(RT::CARD, rIdx, idx).execute(gc);
    }
}

// --- BOSS-RELIC + NEOW choice via V_win: pick the option whose RESULTING state has the
// highest P(win). Same "which resulting state is best" frame as shop/rest, now applied to two
// high-impact decisions the default heuristic used to own. Each candidate is applied to a COPY
// (real relic/Neow transition, RNG untouched on the real gc), evaluated with V_win, argmax'd.
static int g_bossRelicV = 0;   // STS_BOSS_RELIC=1
static int g_neowV      = 0;   // STS_NEOW_V=1

// --- NATIVE V_win: compact XGBoost tree-walk on the rich feature vector, to kill the
// v_server socket for OOC V_win decisions (esp. the unbatched per-candidate ones:
// boss-relic/Neow/pathing). Loaded from models/v_win_trees.txt (export_win_model.py).
// Shared compact-tree reader/evaluator.  V_win and the E2c RAW critic use the
// exact same text format and traversal; consumers only supply their canonical
// feature-name -> vector-index map.
struct CompactTreeNet {
    struct Node { int feat; float thr; int yes, no; };   // feat<0 => leaf (value in thr)
    std::vector<std::vector<Node>> trees;
    std::vector<int> sel;                                  // model feat i -> rich raw index
    double baseMargin = 0.0; bool logistic = true, ok = false;
    std::string path;                                      // loaded-tree source path

    std::vector<std::string> featureNames;

    bool load(const std::string &path, const std::unordered_map<std::string,int> &featureIdx,
              const char *kind = "CompactTreeNet") {
        this->path = path;
        ok = false;                                        // only set true after validation passes
        std::ifstream f(path); if (!f) { std::cerr << kind << ": cannot open " << path << "\n"; return false; }
        std::string tok; int nfeat = 0, ntrees = 0; double baseScore = 0.5;
        f >> tok >> nfeat;                                 // "nfeat N"
        if (tok != "nfeat" || nfeat < 1) { std::cerr << kind << ": invalid feature count\n"; return false; }
        sel.resize(nfeat); featureNames.resize(nfeat);
        std::unordered_set<std::string> seenFeatures;
        for (int i = 0; i < nfeat; ++i) { std::string kw, name; f >> kw >> name;
            auto it = featureIdx.find(name);
            if (kw != "feat" || it == featureIdx.end() || !seenFeatures.insert(name).second) {
                std::cerr << kind << ": unknown or duplicate feature: " << name << "\n"; return false; }
            sel[i] = it->second; featureNames[i] = name; }
        f >> tok >> logistic;                              // "logistic 0/1"
        f >> tok >> baseScore;                             // "base_score X"
        f >> tok >> ntrees;                                // "ntrees N"
        if (tok != "ntrees" || !f.good() || ntrees < 1 || (logistic && !(baseScore > 0.0 && baseScore < 1.0))) {
            std::cerr << kind << ": truncated/missing tree count in " << path << "\n"; return false;
        }
        baseMargin = logistic ? std::log(baseScore / (1.0 - baseScore)) : baseScore;
        trees.resize(ntrees);
        for (int t = 0; t < ntrees; ++t) {
            std::string kw; int ti, nn; f >> kw >> ti >> nn;   // "tree t count"
            if (!f.good() || kw != "tree" || ti != t || nn < 1) { std::cerr << kind << ": invalid tree " << t << " header in " << path << "\n"; return false; }
            trees[t].resize(nn);
            for (int i = 0; i < nn; ++i) {
                std::string type; f >> type;
                Node nd = { -1, 0.0f, 0, 0 };
                if (type == "L") { double v; f >> v; nd = { -1, (float)v, 0, 0 }; }
                else if (type == "S") { int fi = 0, y = 0, no = 0; float th = 0.0f; f >> fi >> th >> y >> no; nd = { fi, th, y, no }; }
                else { std::cerr << kind << ": invalid node tag in tree " << t << "\n"; return false; }
                if (!f.good()) { std::cerr << kind << ": truncated node in tree " << t << " of " << path << "\n"; return false; }
                trees[t][i] = nd;
            }
            for (const Node &nd : trees[t]) if (nd.feat >= 0 &&
                (nd.feat >= nfeat || nd.yes < 0 || nd.no < 0 || nd.yes >= nn || nd.no >= nn)) {
                std::cerr << kind << ": invalid split index in tree " << t << "\n"; return false; }
            // Compact exports are serialized in XGBoost node order, whose
            // final node is a leaf.  Keep this historical truncation guard
            // and also reject cycles/unreachable nodes so predict() cannot
            // walk a malformed tree indefinitely or silently ignore data.
            if (trees[t].back().feat >= 0) {
                std::cerr << kind << ": final node is not a leaf in tree " << t << "\n"; return false;
            }
            std::vector<unsigned char> visit(nn, 0);
            std::function<bool(int)> validateTree = [&](int node) {
                if (visit[node] == 1) return false;
                if (visit[node] == 2) return true;
                visit[node] = 1;
                const Node &nd = trees[t][node];
                if (nd.feat >= 0 && (!validateTree(nd.yes) || !validateTree(nd.no))) return false;
                visit[node] = 2;
                return true;
            };
            if (!validateTree(0) || std::find(visit.begin(), visit.end(), 0) != visit.end()) {
                std::cerr << kind << ": cyclic or unreachable node in tree " << t << "\n"; return false;
            }
        }
        f >> tok;                                          // probe: file must end cleanly after the last tree
        if (!f.eof()) { std::cerr << kind << ": trailing data after " << ntrees << " trees in " << path << "\n"; return false; }
        ok = true;
        std::cout << "[" << kind << ": " << ntrees << " trees, " << nfeat << " feats from " << path << "]\n";
        return true;
    }
    double predict(const std::vector<float> &raw) const {
        double m = baseMargin;
        for (const auto &tr : trees) { int i = 0, steps = 0;
            while (tr[i].feat >= 0 && ++steps <= (int)tr.size()) i = (raw[sel[tr[i].feat]] < tr[i].thr) ? tr[i].yes : tr[i].no;
            if (steps > (int)tr.size()) return std::numeric_limits<double>::quiet_NaN();
            m += tr[i].thr; }
        const double out = logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
        return logistic ? std::max(0.0, std::min(1.0, out)) : out;
    }
};
using WinNet = CompactTreeNet;
static WinNet g_winNet;
static WinNet g_floorNet;
// E2c is never loaded implicitly: only runwinshadow with this explicit model
// path can arm the diagnostic producer.
static CompactTreeNet g_runwinShadowNet;
static std::string g_runwinShadowModelPath;
static bool   winNetOk() { return g_winNet.ok; }
static double winNetPredict(const std::vector<float> &raw) { return g_winNet.predict(raw); }

// rich feature NAME -> raw index (from richHeader minus the seed prefix and the 3 labels).
static const std::unordered_map<std::string,int> &richIdxMap() {
    static std::unordered_map<std::string,int> m;
    if (m.empty()) {
        std::string h = richHeader(); std::vector<std::string> names; std::string cur;
        for (char c : h) { if (c == ',') { names.push_back(cur); cur.clear(); } else cur += c; }
        names.push_back(cur);
        // drop "seed" (front) and won/finalFloor/endHp (back) -> raw layout
        for (int i = 1; i + 3 < (int)names.size(); ++i) m[names[i]] = i - 1;
    }
    return m;
}
// rich feature vector as floats (parse of vFeatCsv -> exactly the raw layout).
static std::vector<float> richFeatureVec(GameContext &gc) {
    const std::string s = vFeatCsv(gc);
    std::vector<float> v; v.reserve(1024); std::string cur;
    for (char c : s) { if (c == ',') { v.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); } else cur += c; }
    if (!cur.empty()) v.push_back(std::strtof(cur.c_str(), nullptr));
    return v;
}

static double nativeFloorValue(GameContext &gc) {
    return g_floorNet.ok ? g_floorNet.predict(richFeatureVec(gc)) : 0.0;
}

static int nativeFloorCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const std::vector<float> base = richFeatureVec(gc);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    double best = -1e100; int bestIdx = 5;
    const double v0 = g_floorNet.predict(base);
    for (int i = 0; i < r.cardRewards[rIdx].size(); ++i) {
        std::vector<float> row = base;
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) row[it->second] += 1.0f;
        row[dsz] += 1.0f;
        const double marginal = g_floorNet.predict(row) - v0;
        if (marginal > best) { best = marginal; bestIdx = i; }
    }
    return best < g_cardSkipThresh ? 5 : bestIdx;
}

static std::string nativeShopPlan(GameContext &gc) {
    const Shop &sh = gc.info.shop;
    const auto &idx = richIdxMap();
    const int goldIdx = idx.at("gold"), dsz = idx.at("deckSize");
    const std::vector<float> base = richFeatureVec(gc);
    struct Item { char kind; int slot, price, id; };
    std::vector<Item> items;
    for (int i = 0; i < 7; ++i) if (sh.cardPrice(i) >= 0)
        items.push_back({'c', i, sh.cardPrice(i), (int)sh.cards[i].getId()});
    for (int i = 0; i < 3; ++i) if (sh.relicPrice(i) >= 0)
        items.push_back({'r', i, sh.relicPrice(i), (int)sh.relics[i]});
    if (items.size() > 16) items.resize(16);
    int removeId = -1; double removeGain = 0.0;
    if (sh.removeCost >= 0) {
        double v0 = g_floorNet.predict(base);
        for (int id = 0; id < 372; ++id) {
            auto it = idx.find("d" + std::to_string(id));
            if (it == idx.end() || base[it->second] <= 0) continue;
            auto row = base; row[it->second] -= 1.0f; row[dsz] -= 1.0f;
            double gain = g_floorNet.predict(row) - v0;
            if (removeId < 0 || gain > removeGain) { removeId = id; removeGain = gain; }
        }
    }
    double best = -1e100; unsigned bestMask = 0; bool bestRemove = false;
    const unsigned total = 1u << items.size();
    for (unsigned mask = 0; mask < total; ++mask) {
        int spend = 0, adds = 0;
        for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) { spend += items[k].price; ++adds; }
        for (int rem = 0; rem <= 1; ++rem) {
            if (rem && (sh.removeCost < 0 || removeId < 0)) continue;
            if (spend + (rem ? sh.removeCost : 0) > gc.gold) continue;
            auto row = base; row[goldIdx] -= spend + (rem ? sh.removeCost : 0); row[dsz] += adds;
            for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
                if (items[k].kind == 'c') {
                    auto it = idx.find("d" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] += 1.0f;
                } else {
                    auto it = idx.find("r" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] = std::max(row[it->second], 1.0f);
                }
            }
            if (rem) { auto it = idx.find("d" + std::to_string(removeId)); if (it != idx.end()) row[it->second] -= 1.0f; }
            const double value = g_floorNet.predict(row);
            if (value > best) { best = value; bestMask = mask; bestRemove = rem != 0; }
        }
    }
    std::ostringstream out;
    for (unsigned k = 0; k < items.size(); ++k) if (bestMask & (1u << k)) out << items[k].kind << items[k].slot << ' ';
    if (bestRemove) out << 'x';
    return out.str();
}

static double vStateWin(GameContext &gc) {
    if (g_winNet.ok) return g_winNet.predict(richFeatureVec(gc));   // native path
    double v = 0.5;
    std::sscanf(vSendRecv("VW;" + vFeatCsv(gc)).c_str(), "%lf", &v);
    return v;
}
static void bossRelicVPolicy(GameContext &gc) {
    int best = -1; double bestV = -1e18;
    for (int i = 0; i < 3; ++i) {
        if (gc.info.bossRelics[i] == RelicId::INVALID) continue;
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        g2.chooseBossRelic(i);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseBossRelic(best < 0 ? 0 : best);
}
static void neowVPolicy(GameContext &gc) {
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)gc.info.neowRewards.size(); ++i) {
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        g2.chooseNeowOption(g2.info.neowRewards[i]);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    gc.chooseNeowOption(gc.info.neowRewards[best]);
}

static int g_pathV  = 0;   // STS_PATH_V:  model-driven pathing
static int g_pathGraph = 0; // STS_PATH_GRAPH: full-map graph NN child scoring
static int g_pathAction = 0;// STS_PATH_ACTION: direct paired route-action NN
static int g_pathActionMax = -1;
static double g_pathActionMargin = 0.0;
static bool g_pathActionTrace = false;
static thread_local int t_pathActionUses = 0;
static int g_eventV = 0;   // STS_EVENT_V: model-driven events
static int chooseMapAction(const GameContext &gc);   // heuristic pathing (defined below)

// Model-driven pathing: pick the immediate child whose position maximizes V_win. Position now
// affects V only through the forward-map features (fm*), so V responds to "what's ahead this way".
// Old models not trained on fm* are ~flat here -> payoff after self-play retraining on fm data.
static void pathVPolicy(GameContext &gc) {
    const Map &map = *gc.map;
    std::vector<int> cands;
    const int childRow = gc.curMapNodeY + 1;
    if (gc.curMapNodeY < 0) { for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) cands.push_back(n.x); }
    else { const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY); for (int i = 0; i < n.edgeCount; ++i) cands.push_back(n.edges[i]); }
    if (cands.empty()) { search::GameAction(chooseMapAction(gc)).execute(gc); return; }
    if (g_pathAction) {
        const int heuristic = chooseMapAction(gc);
        std::ostringstream req;
        req << "PA;";
        for (int i = 0; i < (int)cands.size(); ++i) { if (i) req << ','; req << cands[i]; }
        req << ';' << heuristic << ';' << mapGraphCsv(gc, true) << ';' << mapGraphCsv(gc, false) << ';'
            << mapSpecialCsv(gc) << ';' << vFeatCsv(gc);
        int chosen = -1; double advantage = -1e9;
        const std::string response = vSendRecv(req.str());
        std::sscanf(response.c_str(), "%d %lf", &chosen, &advantage);
        const bool capacity = g_pathActionMax < 0 || t_pathActionUses < g_pathActionMax;
        if (g_pathActionTrace) {
            #pragma omp critical(path_action_trace)
            std::cerr << "[path-action] seed=" << gc.seed << " pos=" << gc.curMapNodeX << ','
                      << gc.curMapNodeY << " heuristic=" << heuristic << " chosen=" << chosen
                      << " advantage=" << advantage << " uses=" << t_pathActionUses
                      << " capacity=" << capacity << " response='" << response << "'\n";
        }
        if (capacity && advantage >= g_pathActionMargin
            && std::find(cands.begin(), cands.end(), chosen) != cands.end()) {
            search::GameAction(chosen).execute(gc);
            if (chosen != heuristic) ++t_pathActionUses;
            return;
        }
        search::GameAction(heuristic).execute(gc); // conservative/server-failure fallback
        return;
    }
    int bestX = cands[0]; double bestV = -1e18;
    for (int x : cands) {
        double v;
        if (g_pathGraph) {
            std::string req = "PG;" + std::to_string(x) + ';' + mapGraphCsv(gc, true) + ';'
                            + mapGraphCsv(gc, false) + ';' + mapSpecialCsv(gc) + ';' + vFeatCsv(gc);
            v = 0.5;
            std::sscanf(vSendRecv(req).c_str(), "%lf", &v);
        } else {
            const int oX = gc.curMapNodeX, oY = gc.curMapNodeY;
            gc.curMapNodeX = x; gc.curMapNodeY = childRow; // old forward-summary child evaluation
            v = vStateWin(gc);
            gc.curMapNodeX = oX; gc.curMapNodeY = oY;
        }
        if (v > bestV) { bestV = v; bestX = x; }
    }
    search::GameAction(bestX).execute(gc);
}

// Model-driven events: enumerate the event's options, evaluate V_win of each resulting state,
// pick the best. Returns false (caller falls back to default) if no options are available.
static bool eventVPolicy(GameContext &gc) {
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    int best = 0; double bestV = -1e18;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext g2 = gc;
        g2.map = std::make_shared<Map>(*gc.map);
        actions[i].execute(g2);
        const double v = vStateWin(g2);
        if (v > bestV) { bestV = v; best = i; }
    }
    actions[best].execute(gc);
    return true;
}

// ---------------------------------------------------------------------------
// REST-SITE VALUE POLICY: use the same deck-aware GBM (curHp is a live feature)
// to decide heal-vs-upgrade by their effect on expected final floor.
//   heal  value = V(deck, hp+restHeal) - V(deck, hp)              (server "H")
//   upgrade target = argmax V(deck) - V(deck-card) over deck cards (server "U")
// Rest iff heal value >= g_restVThreshold, else upgrade the deck's most-valued
// card. Only overrides the genuine heal-vs-smith choice (both available); every
// other campfire option (keys/dig/lift/toke) is left to the default agent so
// this stays a clean A/B of exactly the heal/upgrade tradeoff.
// ---------------------------------------------------------------------------
static double g_restVThreshold = 0.15;  // heal iff healGain (final-floor units) >= this;
                                        // swept best band 0.1-0.25 @512 seeds (STS_REST_V_THRESH to override)

// send an already-built request line, return the response line (empty on error)
static std::string vTransact(const std::string &req) {
    int fd = vConnect();
    if (fd < 0) return "";
    if (send(fd, req.data(), req.size(), 0) < 0) { close(fd); t_vSock = -1; return ""; }
    char buf[64]; std::string resp;
    while (resp.find('\n') == std::string::npos) {
        ssize_t k = recv(fd, buf, sizeof(buf), 0);
        if (k <= 0) { close(fd); t_vSock = -1; return ""; }
        resp.append(buf, k);
    }
    return resp;
}

// V(deck, hp+healAmt) - V(deck, hp), in expected-final-floor units (0 on error)
static double vQueryHeal(GameContext &gc, int healAmt) {
    std::string req = "H;" + std::to_string(healAmt) + ";"
                    + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// index (into candIds) of the deck's most-valued card to upgrade (0 on error)
static int vQueryUpgrade(GameContext &gc, const std::vector<int> &candIds) {
    std::string req = "U;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// Marginal V(deck+card)-V(deck) for each card reward candidate (empty on error).
static std::vector<double> vQueryMarginals(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    std::string req = "M;";
    for (int i = 0; i < n; ++i) { if (i) req += ','; req += std::to_string((int)r.cardRewards[rIdx][i].getId()); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    std::vector<double> out;
    std::istringstream is(resp);
    double m;
    while (is >> m) out.push_back(m);
    return out;
}

// Softmax-sample WHICH card to take (0..n-1) among the n candidates by marginal V
// (temp; higher = more spread). With prob uniformEps pick a uniformly-random card
// (coverage floor so V's blind spots still get sampled). The take-vs-skip decision
// is handled by the caller (skip@g_cardSkipThresh on the BEST marginal), so deck
// sizes match the exploit policy and we only diversify the card choice.
static int sampleCardSoftmax(const std::vector<double> &marg, double temp, double uniformEps,
                             std::default_random_engine &ex) {
    const int n = (int)marg.size();
    if (n <= 1) return 0;
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    if (ur(ex) < uniformEps) return std::uniform_int_distribution<int>(0, n - 1)(ex);
    const double mx = *std::max_element(marg.begin(), marg.end());
    const double t = temp > 1e-6 ? temp : 1e-6;
    double sum = 0.0; std::vector<double> w(n);
    for (int i = 0; i < n; ++i) { w[i] = std::exp((marg[i] - mx) / t); sum += w[i]; }
    double rnd = ur(ex) * sum, acc = 0.0;
    for (int i = 0; i < n; ++i) { acc += w[i]; if (rnd <= acc) return i; }
    return n - 1;
}

// Handle a REST_ROOM screen with the value policy. Returns true if it acted;
// false = defer to the default agent (only the heal-vs-smith case is handled).
static bool restVPolicy(GameContext &gc) {
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;      // keys/dig/lift/single-option -> default agent
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    const double healGain = vQueryHeal(gc, healAmt);
    search::GameAction(healGain >= g_restVThreshold ? 0 : 1, 0).execute(gc);  // 0=rest, 1=smith
    return true;
}

// Handle the UPGRADE card-select opened by SMITH: pick the deck's most-valued card.
static void upgradeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryUpgrade(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

// ---------------------------------------------------------------------------
// WIN-RATE REST POLICY: decide heal-vs-upgrade in P(win) units (win model),
// where HP's effect on survival is sharp and nonlinear (unlike expected floor).
// Both options are scored as a P(win) gain and compared directly (no threshold):
//   heal    gain = P(win, hp+restHeal) - P(win, hp)              (server "HW")
//   upgrade gain = max_c P(win, u{c}+1) - P(win)                 (server "UW")
// Rest iff healGain >= best upgradeGain, else smith (upgrading that best card).
// ---------------------------------------------------------------------------
// Default ON: win-rate rest policy beats the default agent by +4.9pp @512 (47.3 vs
// 42.4, floor+HP also up). Needs the win model loaded in v_server (VWIN); set
// STS_REST_WIN=0 to disable (falls back to the sim default rest agent).
static bool g_restWin = true;

// P(win, hp+healAmt) - P(win, hp) from the win model (0 on error).
static double vQueryHealWin(GameContext &gc, int healAmt) {
    if (g_nativeOoc && g_winNet.ok) {
        const int old = gc.curHp;
        const double before = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = std::min(gc.maxHp, old + healAmt);
        const double after = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = old;
        return after - before;
    }
    std::string req = "HW;" + std::to_string(healAmt) + ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// Best upgrade by P(win): returns index into candIds and sets *gain to its win gain.
static int vQueryUpgradeWin(GameContext &gc, const std::vector<int> &candIds, double *gain) {
    if (g_nativeOoc && g_winNet.ok) {
        const auto &idx = richIdxMap(); auto base = richFeatureVec(gc);
        const double before = g_winNet.predict(base); double best = -1e100; int bestIdx = 0;
        for (int i = 0; i < (int)candIds.size(); ++i) {
            auto row = base; auto it = idx.find("u" + std::to_string(candIds[i]));
            if (it != idx.end()) row[it->second] += 1.0f;
            const double d = g_winNet.predict(row) - before;
            if (d > best) { best = d; bestIdx = i; }
        }
        // Mirror v_server.py's deterministic fallback: the deployed win model
        // has no useful upgrade head for some cards, so choose the card whose
        // removal most improves the current state in that case.
        if (std::abs(best) < 1e-6) {
            best = -1e100; bestIdx = 0;
            for (int i = 0; i < (int)candIds.size(); ++i) {
                auto row = base; auto it = idx.find("d" + std::to_string(candIds[i]));
                if (it != idx.end()) row[it->second] -= 1.0f;
                auto ds = idx.find("deckSize"); if (ds != idx.end()) row[ds->second] -= 1.0f;
                const double d = before - g_winNet.predict(row);
                if (d > best) { best = d; bestIdx = i; }
            }
        }
        if (gain) *gain = best;
        return bestIdx;
    }
    std::string req = "UW;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = 0; double g = 0.0;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &g) < 1) { idx = 0; g = 0.0; }
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    if (gain) *gain = g;
    return idx;
}

// Direct paired counterfactual rest-vs-smith model. Returns false when no model is
// deployed (server replies NA), preserving the proven V_win marginal fallback.
static bool vQueryRestCounterfactual(GameContext &gc, double *delta) {
    if (g_nativeOoc) return false;
    const std::string resp = vTransact("RC;" + vFeatCsv(gc) + "\n");
    double d = 0.0;
    if (resp.empty() || resp.rfind("NA", 0) == 0
        || std::sscanf(resp.c_str(), "%lf", &d) != 1 || !std::isfinite(d)) return false;
    if (delta) *delta = d;
    return true;
}

// Deduped ids of the deck's upgradeable cards (candidates for a smith).
static std::vector<int> upgradeableIds(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        const int id = (int)gc.deck.cards[i].getId();
        if (std::find(ids.begin(), ids.end(), id) == ids.end()) ids.push_back(id);
    }
    return ids;
}

// Handle a REST_ROOM screen by win-rate: rest iff heal raises P(win) more than the
// best upgrade does. Returns false (defer to default agent) if it's not a genuine
// heal-vs-smith choice (keys/dig/single-option).
static bool restWinPolicy(GameContext &gc) {
    // Ruby key (RECALL, rest action 2) is mandatory for Act 4: take it at the
    // first act-3+ campfire when we don't hold it yet.
    if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
        search::GameAction(2, 0).execute(gc);
        return true;
    }
    const bool canRest  = !gc.hasRelic(RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(RelicId::FUSION_HAMMER) && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmt = (int)std::lround(0.30 * gc.maxHp)
                      + (gc.hasRelic(RelicId::REGAL_PILLOW) ? 15 : 0);
    double pairedDelta = 0.0;
    if (vQueryRestCounterfactual(gc, &pairedDelta)) {
        search::GameAction(pairedDelta >= 0.0 ? 0 : 1, 0).execute(gc);
        return true;
    }
    const double healGain = vQueryHealWin(gc, healAmt);
    std::vector<int> ids = upgradeableIds(gc);
    double upGain = 0.0;
    if (!ids.empty()) vQueryUpgradeWin(gc, ids, &upGain);
    search::GameAction(healGain >= upGain ? 0 : 1, 0).execute(gc);  // 0=rest, 1=smith
    return true;
}

// Handle the UPGRADE card-select opened by SMITH: pick the card with the best P(win) upgrade.
static void upgradeSelectWinPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    double g = 0.0;
    const int idx = ids.empty() ? 0 : vQueryUpgradeWin(gc, ids, &g);
    search::GameAction(idx, 0).execute(gc);
}

// index (into candIds) of the card whose REMOVAL most raises V (0 on error)
static int vQueryRemove(GameContext &gc, const std::vector<int> &candIds) {
    if (g_nativeOoc && !g_shopWin && g_floorNet.ok) {
        const auto &idx = richIdxMap();
        const int dsz = idx.at("deckSize");
        const std::vector<float> base = richFeatureVec(gc);
        const double v0 = g_floorNet.predict(base);
        double best = -1e100;
        int bestIdx = 0;
        for (int i = 0; i < (int)candIds.size(); ++i) {
            auto row = base;
            auto it = idx.find("d" + std::to_string(candIds[i]));
            if (it != idx.end()) row[it->second] -= 1.0f;
            row[dsz] -= 1.0f;
            const double gain = g_floorNet.predict(row) - v0;
            if (gain > best) { best = gain; bestIdx = i; }
        }
        return bestIdx;
    }
    std::string req = "X;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// ---------------------------------------------------------------------------
// SHOP VALUE POLICY: ask the server for the V-maximizing affordable bundle of
// {card buys, card removal, relic buys} and execute it. Card buys and removal
// are well-modeled (deck-aware V); relics get a generic nRelics delta (can't
// rank relic identity); potions are not modeled (never bought here). Returns
// true if it acted on the shop screen.
// ---------------------------------------------------------------------------
static std::string vQueryShop(GameContext &gc) {
    if (g_nativeOoc && !g_shopWin) return nativeShopPlan(gc);
    const Shop &sh = gc.info.shop;
    std::string cardsCsv, relicsCsv;
    for (int i = 0; i < 7; ++i) {
        if (i) cardsCsv += ',';
        cardsCsv += std::to_string((int)sh.cards[i].getId()) + ":" + std::to_string(sh.cardPrice(i));
    }
    for (int j = 0; j < 3; ++j) {
        if (j) relicsCsv += ',';
        relicsCsv += std::to_string((int)sh.relics[j]) + ":" + std::to_string(sh.relicPrice(j));
    }
    std::string req = std::string(g_shopWin ? "SW;" : "S;") + std::to_string(sh.removeCost)
                    + ";" + cardsCsv + ";" + relicsCsv + ";" + vFeatCsv(gc) + "\n";
    return vTransact(req);
}

// Execute ONE purchase from the V-optimal plan, then return. Re-entry re-optimizes
// on the updated state, so a buy that opens a follow-up screen (e.g. a bottling
// relic, or the removal card-select) can't desync a multi-buy sequence. Empty
// plan -> leave the shop. Each buy strictly spends gold, so this terminates.
static void shopVPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    const std::string requestState = g_actFightProbeTrace ? vFeatCsv(gc) : std::string{};
    std::string plan = vQueryShop(gc);
    if (g_actFightProbeTrace) {
        const Shop &sh = gc.info.shop;
        std::cerr << "[shop-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " gold=" << gc.gold
                  << " cardRng=" << gc.cardRng.seed0 << ':' << gc.cardRng.seed1
                  << " merchantRng=" << gc.merchantRng.seed0 << ':' << gc.merchantRng.seed1
                  << " potionRng=" << gc.potionRng.seed0 << ':' << gc.potionRng.seed1
                  << " remove=" << sh.removeCost << " cards=";
        for (int i = 0; i < 7; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.cards[i].getId() << ':' << sh.cardPrice(i);
        std::cerr << " relics=";
        for (int i = 0; i < 3; ++i)
            std::cerr << (i ? ";" : "") << (int)sh.relics[i] << ':' << sh.relicPrice(i);
        std::cerr << " featHash=" << std::hash<std::string>{}(requestState)
                  << " plan=" << plan << "]\n";
    }
    std::istringstream is(plan);
    std::string tok;
    if (!(is >> tok) || tok.empty()) { search::GameAction(RT::SKIP).execute(gc); return; }
    const int idx = tok.size() > 1 ? std::atoi(tok.c_str() + 1) : 0;
    if (tok[0] == 'c')      search::GameAction(RT::CARD,  idx).execute(gc);
    else if (tok[0] == 'r') search::GameAction(RT::RELIC, idx).execute(gc);
    else if (tok[0] == 'x') search::GameAction(RT::CARD_REMOVE).execute(gc);   // opens REMOVE select
    else                    search::GameAction(RT::SKIP).execute(gc);
}

// Pick the removal target on a shop REMOVE card-select: the worst card by V.
static void removeSelectVPolicy(GameContext &gc) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back((int)gc.info.toSelectCards[i].card.getId());
    const int idx = ids.empty() ? 0 : vQueryRemove(gc, ids);
    search::GameAction(idx, 0).execute(gc);
}

// ---------------------------------------------------------------------------
// LEARNED VALUE FUNCTION: V(state)=sigmoid(bias + sum w_i*feature_i), weights
// trained offline (logistic regression, train_value.py). Card value is the
// marginal V(deck+card) - V(deck); skip if no card has positive marginal value.
// Feature definitions MUST match featureRow() above.
// ---------------------------------------------------------------------------
static std::map<std::string, double> g_valWeights;
static double g_valBias = 0.0;
static bool g_valLoaded = false;
static bool g_learnedNeverSkip = false;   // diagnostic: always take best card, never skip

static void loadValueModel(const std::string &path) {
    std::ifstream f(path);
    if (!f) { std::cerr << "WARNING: could not open value model: " << path << "\n"; return; }
    std::string name; double w;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream is(line);
        is >> name >> w;
        if (name == "bias") g_valBias = w;
        else g_valWeights[name] = w;
    }
    g_valLoaded = true;
    std::cout << "loaded value model (" << g_valWeights.size() << " weights) from " << path << "\n";
}

static double sigmoid(double z) { return 1.0 / (1.0 + std::exp(-z)); }

// current-state features (same definitions as featureRow)
static std::map<std::string, double> stateFeats(const GameContext &gc) {
    std::map<std::string, double> m;
    int nAtk=0,nSkill=0,nPow=0,nCurse=0,nStatus=0,nUpg=0,nStarter=0,nCommon=0,nUncommon=0,nRare=0;
    long obtainSum = 0;
    for (const auto &c : gc.deck.cards) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::SKILL:  ++nSkill; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::CURSE:  ++nCurse; break;
            case CardType::STATUS: ++nStatus; break;
            default: break;
        }
        if (c.isUpgraded()) ++nUpg;
        if (c.isStarterStrikeOrDefend()) ++nStarter;
        switch (c.getRarity()) {
            case CardRarity::COMMON:   ++nCommon; break;
            case CardRarity::UNCOMMON: ++nUncommon; break;
            case CardRarity::RARE:     ++nRare; break;
            default: break;
        }
        obtainSum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    const int deckSize = gc.deck.size();
    m["act"]=gc.act; m["floor"]=gc.floorNum; m["curHp"]=gc.curHp; m["maxHp"]=gc.maxHp;
    m["gold"]=gc.gold; m["deckSize"]=deckSize;
    m["nAttack"]=nAtk; m["nSkill"]=nSkill; m["nPower"]=nPow; m["nCurse"]=nCurse; m["nStatus"]=nStatus;
    m["nUpgraded"]=nUpg; m["nStarter"]=nStarter;
    m["nCommon"]=nCommon; m["nUncommon"]=nUncommon; m["nRare"]=nRare;
    m["obtainSum"]=(double)obtainSum; m["obtainAvg"]= deckSize? (double)obtainSum/deckSize : 0.0;
    m["nRelics"]=(double)gc.relics.relics.size();
    return m;
}

static double logitOf(const std::map<std::string, double> &feats) {
    double z = g_valBias;
    for (const auto &kv : g_valWeights) {
        auto it = feats.find(kv.first);
        if (it != feats.end()) z += kv.second * it->second;
    }
    return z;
}

static void learnedCardRewardPolicy(GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();

        const auto base = stateFeats(gc);
        const double vBase = sigmoid(logitOf(base));

        int bestIdx = -1;
        double bestVal = g_learnedNeverSkip ? -1e18 : 0.0;   // 0.0 => skip unless a card has positive marginal value
        for (int i = 0; i < n; ++i) {
            const auto &c = r.cardRewards[rIdx][i];
            auto f = base;
            f["deckSize"] += 1;
            switch (c.getType()) {
                case CardType::ATTACK: f["nAttack"] += 1; break;
                case CardType::SKILL:  f["nSkill"]  += 1; break;
                case CardType::POWER:  f["nPower"]  += 1; break;
                case CardType::CURSE:  f["nCurse"]  += 1; break;
                case CardType::STATUS: f["nStatus"] += 1; break;
                default: break;
            }
            if (c.isUpgraded()) f["nUpgraded"] += 1;
            switch (c.getRarity()) {
                case CardRarity::COMMON:   f["nCommon"]   += 1; break;
                case CardRarity::UNCOMMON: f["nUncommon"] += 1; break;
                case CardRarity::RARE:     f["nRare"]     += 1; break;
                default: break;
            }
            f["obtainSum"] += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
            f["obtainAvg"] = f["obtainSum"] / f["deckSize"];

            const double val = sigmoid(logitOf(f)) - vBase;
            if (val > bestVal) { bestVal = val; bestIdx = i; }
        }
        search::GameAction(RT::CARD, rIdx, bestIdx >= 0 ? bestIdx : 5).execute(gc);
    }
}

// Whole run where the card-reward decision is the built-in weighted table
// (policyId 0), greedy argmax (1), the hand state-aware value function (2), or
// the learned logistic value function (3).
static RunResult runFullRunCards(std::uint64_t seed, int sims, int asc, int policyId, double skipRatio) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;                  // mirror stepRewardsPolicy ordering
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (policyId == 0)         agent.weightedCardRewardPolicy(gc);
            else if (policyId == 1)         greedyCardRewardPolicy(gc, skipRatio);
            else if (policyId == 2)         evalCardRewardPolicy(gc);
            else if (policyId == 3)         learnedCardRewardPolicy(gc);
            else if (policyId == 4)         fusedCardRewardPolicy(gc);
            else if (policyId == 5)         tableCardRewardPolicy(gc);
            else                            serverCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void cardBench(int sims, int nSeeds, int asc, double skipRatio, int onlyPolicy = -1) {
    std::cout << "card-policy A/B   seeds 0.." << nSeeds - 1 << "   ascension: " << asc
              << "   sims/decision: " << sims << "   greedy skipRatio: " << skipRatio
              << "   threads: " << numThreads() << "\n\n";
    if (!g_valLoaded) loadValueModel("build/value_model.txt");
    if (!g_cardAdvLoaded) loadCardAdvTable("build/card_adv_table.txt");
    const char *names[] = {"weighted-table", "greedy-argmax", "eval-function",
                           "learned-logistic", "eval+causal", "causal-table", "gbm-server"};
    for (int policyId = 0; policyId < 7; ++policyId) {
        if (onlyPolicy >= 0 && policyId != onlyPolicy) continue;
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunCards((std::uint64_t)s, sims, asc, policyId, skipRatio);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    names[policyId],
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// HEURISTIC PATHING: pick the map route by scoring each room and taking the
// child that leads to the best-scoring remaining path to the boss.
//
// Spec (from the player's intuition):
//   * elites & rest sites are great; elites more so the LATER you fight them
//     (you're stronger, and you get healed at act end anyway);
//   * shops are worth it only if you can afford them;
//   * fights build the deck and are good when you have HP, especially act 1;
//   * events balance out a fight-heavy path;
//   * in general take the HARDEST path you can still survive -- reward density
//     beats HP hoarding because the act-transition heals you.
//
// HP-awareness is implicit: the policy re-plans every floor with live curHp,
// and elite/monster values are gated by current HP, so a healthy hero routes
// into elites/fights and a hurt one routes to rests/events.
// ---------------------------------------------------------------------------
static double roomValue(Room r, int y, const GameContext &gc) {
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;
    const int act = gc.act;
    double v;
    switch (r) {
        case Room::ELITE: {
            const double base  = 14.0;             // relic + strong card/gold: top-value room
            const double later = 0.5 * y;          // prefer fighting elites later
            // HP gate, like monsters but demanding MORE health (elites are high-variance):
            // ramps 0 -> 1 as HP goes 40% -> 90% of max, so an elite is only worth
            // routing into when you're near-full. Below 40% it's ~worthless.
            const double gate  = std::clamp((hpFrac - 0.40) / 0.50, 0.0, 1.0);
            v = (base + later) * gate;
            break;
        }
        case Room::REST:
            v = 9.0 + (hpFrac < 0.5 ? 5.0 : 0.0);   // heal/upgrade; more valuable when hurt
            break;
        case Room::SHOP:
            v = gc.gold >= 120 ? 7.0 : gc.gold >= 75 ? 4.0 : 1.5;
            break;
        case Room::MONSTER: {
            const double actMul = act == 1 ? 1.0 : 0.55;   // fights build the deck, esp. act 1
            const double hpMul  = 0.4 + 0.9 * hpFrac;      // good when you have HP
            v = 3.2 * actMul * hpMul;
            break;
        }
        case Room::EVENT:
            v = 3.8;                                // wildcard; balances fight-heavy paths
            break;
        case Room::TREASURE:
            v = 6.0;                                // free relic
            break;
        default:
            return 0.0;                             // BOSS / NONE / INVALID (never modulated)
    }
    // V-informed deck-strength modulation (STS_VPATH): scale AGGRESSIVE rooms up
    // and RECOVERY rooms down when the value model thinks the deck is strong
    // (t_pathAggr > 0), and vice-versa. Neutral aggr (0) leaves the heuristic exact.
    if (g_vPath && t_pathAggr != 0.0) {
        const double a = g_vPathK * t_pathAggr;     // signed gain
        switch (r) {
            case Room::ELITE:   v *= (1.0 + a);        break;  // strong deck -> farm elites/relics
            case Room::MONSTER: v *= (1.0 + 0.75 * a); break;  // ... and fights (deck-building)
            case Room::REST:    v *= (1.0 - 0.75 * a); break;  // weak deck -> value recovery
            case Room::SHOP:    v *= (1.0 - 0.50 * a); break;
            case Room::EVENT:   v *= (1.0 - 0.25 * a); break;
            default: break;
        }
    }
    return v;
}

// Returns the child x-column to move into (== the map GameAction index).
static int chooseMapAction(const GameContext &gc) {
    const Map &map = *gc.map;

    // V-informed deck-strength: one V(state) query -> predicted final floor, turned
    // into an aggression signal in [-1,+1] via the act-boss anchor. Comfortably
    // clearing the act (predFloor >> bossFloor) => aggr>0 => farm elites/fights;
    // barely surviving => aggr<0 => route to recovery. Scale 8 floors ~= full swing.
    t_pathAggr = 0.0;
    if (g_vPath) {
        const double pf = vStateRaw(const_cast<GameContext &>(gc));
        if (pf > -1e8)   // server reachable
            t_pathAggr = std::clamp((pf - bossFloorForAct(gc.act)) / 8.0, -1.0, 1.0);
    }

    // Bottom-up DP: best[y][x] = best total room value from entering (x,y) to boss.
    static thread_local double best[15][7];
    for (int x = 0; x < 7; ++x) {
        best[14][x] = roomValue(map.getNode(x, 14).room, 14, gc);   // then the boss
    }
    for (int y = 13; y >= 0; --y) {
        for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.edgeCount == 0) { best[y][x] = -1e9; continue; }   // unused / dead node
            double bestChild = -1e18;
            for (int i = 0; i < n.edgeCount; ++i) {
                bestChild = std::max(bestChild, best[y + 1][n.edges[i]]);
            }
            best[y][x] = roomValue(n.room, y, gc) + bestChild;
        }
    }

    // Candidate children (mirrors getAllMapActions).
    const int childRow = gc.curMapNodeY + 1;
    int bestX = -1;
    double bestScore = -1e18;
    auto consider = [&](int x) {
        if (best[childRow][x] > bestScore) { bestScore = best[childRow][x]; bestX = x; }
    };
    if (gc.curMapNodeY == -1) {
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) consider(n.x);
    } else {
        const MapNode &n = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < n.edgeCount; ++i) consider(n.edges[i]);
    }
    return bestX;
}

// Whole run where the map route is either the built-in random policy or our heuristic.
static RunResult runFullRunPath(std::uint64_t seed, int sims, int asc, bool heuristicPath) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (heuristicPath && gc.screenState == ScreenState::MAP_SCREEN
                   && gc.curMapNodeY < 14) {                    // y==14 is forced to boss
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void pathBench(int sims, int nSeeds, int asc) {
    std::cout << "pathing A/B   seeds 0.." << nSeeds - 1 << "   ascension: " << asc
              << "   mcts sims/decision: " << sims
              << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool heuristic = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunPath((std::uint64_t)s, sims, asc, heuristic);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-16s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    heuristic ? "heuristic-path" : "random-path",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// COMBINED POLICY: greedy never-skip drafting (exp 8) + heuristic pathing
// (exp 6b) together, vs. the stock baseline (built-in weighted table + random
// path). Everything else identical.
// ---------------------------------------------------------------------------
static RunResult runFullRunCombo(std::uint64_t seed, int sims, int asc, bool combo, double skipRatio) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    auto t0 = std::chrono::steady_clock::now();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
        } else if (combo && gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);            // heuristic pathing
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (combo)                 evalCardRewardPolicy(gc, false);         // eval ranking, never skip
            else                            agent.weightedCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    return { gc.outcome == GameOutcome::PLAYER_VICTORY, gc.floorNum, gc.act,
             gc.curHp, gc.maxHp, std::chrono::duration<double>(t1 - t0).count() };
}

static void comboBench(int sims, int nSeeds, int asc, double skipRatio) {
    std::cout << "combo A/B (greedy-draft + heuristic-path)   seeds 0.." << nSeeds - 1
              << "   ascension: " << asc << "   sims/decision: " << sims
              << "   skipRatio: " << skipRatio << "   threads: " << numThreads() << "\n\n";
    for (int mode = 0; mode < 2; ++mode) {
        const bool combo = (mode == 1);
        int wins = 0; long long floor = 0, hp = 0; double sec = 0;
        auto wall0 = std::chrono::steady_clock::now();
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            RunResult r = runFullRunCombo((std::uint64_t)s, sims, asc, combo, skipRatio);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        }
        double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        std::printf("%-22s  win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    combo ? "combo(eval+path)" : "baseline(table+rand)",
                    100.0 * wins / nSeeds, (double)floor / nSeeds,
                    (double)hp / nSeeds, sec / nSeeds, wall);
    }
}

// ---------------------------------------------------------------------------
// BOSS-GATED ROLLOUT DRAFT: deaths cluster at act bosses, so for card rewards
// picked within a few rows of the upcoming boss we DON'T trust the myopic 1-ply
// server V. Instead, for each candidate (each card + skip) we copy the run,
// apply the pick, and roll the next few fights forward -- INCLUDING the boss --
// scoring by end-state (HP / win). The inner rollouts reuse rolloutChoice, which
// already respects fair-play and the V_combat leaf, so each is cheap. Falls back
// to the server pick when no hard fight is close.
//   The "how close is a hard fight" gate is deliberately factored out
// (rowsToHardFight, defined above) so the hard-fight set can later become DYNAMIC
// (wherever we die often); for now it is boss-only.
// ---------------------------------------------------------------------------
// Returns true iff it handled the card reward(s); false => caller uses server V.
static bool bossGatedDraftPolicy(GameContext &gc) {
    if (!g_bossDraft) return false;
    if (rowsToHardFight(gc) > g_bossDraftRows) return false;   // no hard fight close -> server pick
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx   = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e18;
        int    bestIdx   = 5;                                  // 5 == skip
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = (cand < nCards) ? cand : 5;
            double acc = 0;
            for (int f = 0; f < g_bossDraftFutures; ++f) {
                // seed depends only on f -> every candidate faces the SAME sampled
                // futures (common random numbers -> low-variance A/B between picks).
                std::uint64_t s = gc.seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1));
                acc += rolloutChoice(gc, rIdx, cardIdx, g_bossDraftN, g_bossDraftSims, s);
            }
            const double score = acc / g_bossDraftFutures;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    return true;
}

// Defined after the counterfactual runner below.  Keeping it out of that runner
// prevents recursive rollout drafting: only the live, immediate card pick is
// simulation-scored; subsequent simulated rewards use the ordinary server policy.
static bool actFightProbeDraftPolicy(GameContext &gc);
static bool actFightProbeAllOocPolicy(GameContext &gc);
static bool oocActionNNPolicy(GameContext &gc);
static bool oocOnePlyMapPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent);   // M1 one-ply map route Q gate (defined below)
static bool oocMapRouteSearchPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent);  // M2 C_psi route search (defined below)

// ---------------------------------------------------------------------------
// REST-SITE A/B: best card policy (server V) + heuristic path, with the rest
// site driven either by the default agent heuristic or by the value policy
// (restVPolicy / upgradeSelectVPolicy). Isolates exactly the heal/upgrade change.
// Requires v_server.py running (server card picks + rest queries).
// ---------------------------------------------------------------------------
// --- searchdiag shared state (full definition in the SEARCHDIAG section) ------
// runFullRunOOC touches only this guarded state at battle entry/exit, so the
// default benchmark paths stay unchanged when the mode is inactive.
static bool g_sdiagActive = false;
static std::ofstream g_sdiagFile;
static std::mutex g_sdiagMutex;

struct SdiagMetrics {
    std::int64_t budget = 0;
    std::int64_t sims = 0, terminalInTree = 0, rolloutCalls = 0, leafDirectEval = 0;
    std::int64_t rolloutLeafCalls = 0, fairIllegalStoredEdge = 0;
    std::int64_t rolloutTerminated = 0, rolloutDepthCapped = 0, rolloutSkippedVNet = 0, rolloutNoLegal = 0;
    std::int64_t rolloutActions = 0, treeActions = 0, maxTreeDepth = 0;
    double simSeconds = 0;
    search::FrontierStats frontier;
    std::uint32_t bestAction = 0xFFFFFFFFu;   // most-visited root edge (0xFFFFFFFF = none)
    double visitShare = 0, bestValue = 0, runnerUpValue = 0, valueGap = 0;
};

// Per-fight state: run context + accumulated totals + previous cumulative
// snapshot of the persisting agent searcher (per-decision windowing).
struct SdiagRunCtx {
    std::uint64_t seed = 0;
    int floor = 0, act = 0, room = 0, encounter = 0;
    int fightIdx = 0, decisionIdx = 0;
    SdiagMetrics cum;          // last hook's cumulative counters (non-fair mode)
    SdiagMetrics fTot;         // fight totals (sum of per-decision windows)
};
static thread_local SdiagRunCtx g_sdiagCtx;

static void sdiagFightRow(const BattleContext &bc);   // defined in the SEARCHDIAG section

// ---------------------------------------------------------------------------
// LEAFLIAG: Searcher3 leaf-state diagnostic dataset (2026-08-08 handover).
// Records states at the leaf-expansion blend site (search::g_onS3LeafQuery —
// the same place the learned leaf value is blended with the multi-rollout
// outcome, see BattleScumSearcher3::step) with canonical combat features,
// the deployed end-HP vnet prediction, a secondary diagnostic vnet
// prediction (STS_DIAG_VNET2), and the raw/blended rollout evals, using
// per-stratum reservoir sampling. The companion `leafref` mode replays the
// recorded decisions deterministically and writes high-budget reference
// values. runFullRunOOC touches only this guarded state at battle entry/exit
// when g_leafdiagActive; default runs are byte-identical (flag false).
// Sampling is per-seed and deterministic: the reservoir RNG is seeded from
// the run seed only, never from search RNG, so registering the hook does not
// change search behavior (the callback only reads the leaf state).
// ---------------------------------------------------------------------------
static constexpr int kLeafDiagStrata = 10;   // 3 hpFrac bands x 3 difficulties + 1 deep-tree stratum
static bool g_leafdiagActive = false;
static bool g_frontiergenActive = false;     // frontiergen: same per-fight context hooks (t_ld)
static int  g_fgPerStratum = 200;            // STS_FRONTIERGEN_PER_STRATUM (defined with frontiergen below)
static search::CombatValueNet g_combatVNetDiag;  // secondary diagnostic vnet (STS_DIAG_VNET2); NEVER read by the searcher
static int  g_ldPerStratum = 50;                 // STS_LEAFDIAG_PER_STRATUM: reservoir capacity per stratum per seed
static int  g_ldDeepDepth   = 20;                // STS_LEAFDIAG_DEEP_DEPTH: depth >= this maps to the dedicated deep stratum
static std::string g_particleLeafProbeFile;
static int g_particleLeafProbeK = 8;
static double g_particleLeafProbeRate = 0.05;
static int g_particleLeafProbeMaxGroups = 16;

// Phase 1b: posterior-valid particle sensitivity probe. K=0 (default)
// evaluates ALL unique compatible leaf hidden states from the current finite
// root belief; K>0 caps evaluation at the K highest-mass states (the source
// world is always included, no duplicate padding). MAX_GROUPS: -1 unlimited,
// 0 captures nothing (probe-OFF determinism arm), >0 per-seed group cap.
static std::string g_particlePosteriorProbeFile;
static int g_particlePosteriorProbeK = 0;
static int g_particlePosteriorProbeMaxGroups = 16;
static bool g_particlePosteriorAgeSplit = false;
static int g_particlePosteriorAgeEarlyStart = 100;
static int g_particlePosteriorAgeEarlyEnd = 300;
static int g_particlePosteriorAgeLateStart = 2800;
static int g_particlePosteriorAgeLateEnd = 3000;
static int g_particlePosteriorAgeMinPerStratum = 8;
static int g_particlePosteriorAgePerStratum = 16;
static std::string g_particlePosteriorReplayDebugFile;
static int g_particlePosteriorReplayCeiling = 128;
static std::string g_particlePosteriorReplayTraceFile;

struct LeafDiagRow {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = -1;
    int floor = 0, act = 0;
    std::string encounter;                 // UPPER_CASE enum NAME (monsterEncounterEnumNames)
    int depth = 0;
    std::uint64_t obsHash = 0;
    int nLegalActions = 0;
    int stratum = -1;
    std::vector<float> feats;                    // canonical combat features (combatExtractFeatures)
    double endHpPred = std::numeric_limits<double>::quiet_NaN();
    double utilityRPred = std::numeric_limits<double>::quiet_NaN();
    double rawRolloutEval = std::numeric_limits<double>::quiet_NaN();
    double blendedEval = std::numeric_limits<double>::quiet_NaN();
    int won = -1, fightEndHp = -1;               // fight labels, filled at battle end
};

struct ParticleLeafProbeRow {
    std::uint64_t seed = 0, obsHash = 0, sourceLeafId = 0;
    int fightIdx = -1, decIdx = -1, variant = -1, depth = 0, turn = 0;
    int curHp = 0, maxHp = 0, rolloutSteps = 0, terminal = 0;
    int invariantOk = 0, drawPileSize = 0;
    int uniqueVariantsSampled = 0;
    double target = std::numeric_limits<double>::quiet_NaN();
    double rawRolloutEval = std::numeric_limits<double>::quiet_NaN();
    std::string encounter, drawOrder;
    std::vector<float> feats;
};

// leafref group identity: one Searcher3 decision inside one fight of one run.
struct LeafRefGroupKey {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = -1;
    bool operator==(const LeafRefGroupKey &o) const {
        return seed == o.seed && fightIdx == o.fightIdx && decIdx == o.decIdx;
    }
};
struct LeafRefGroupKeyHash {
    size_t operator()(const LeafRefGroupKey &k) const {
        std::uint64_t h = k.seed ^ ((std::uint64_t)(std::uint32_t)k.fightIdx << 32)
                        ^ (std::uint64_t)(std::uint32_t)k.decIdx;
        h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 33;
        return (size_t)h;
    }
};

struct ParticlePosteriorAgeCandidate {
    int stratum = -1;
    int ordinal = -1;
    BattleContext state;
    search::S3LeafDiagnostic diagnostic;
};

struct LeafDiagCtx {
    std::uint64_t seed = 0;
    int fightIdx = 0, floor = 0, act = 0;
    std::string encounter;                 // UPPER_CASE enum NAME (monsterEncounterEnumNames)
    int decIdx = 0;                              // per-fight searched-decision counter (g_onSearchComplete3)
    std::mt19937_64 rng;                         // reservoir RNG (deterministic per seed; never the search RNG)
    std::vector<std::vector<LeafDiagRow>> strata;   // reservoir per stratum (capacity g_ldPerStratum)
    std::vector<int> stratumCounts;              // candidates seen per stratum
    // leafref-only state (filled per replayed seed; unused by leafdiag):
    std::unordered_map<LeafRefGroupKey, std::unordered_set<std::uint64_t>,
                       LeafRefGroupKeyHash> recorded;   // group -> recorded leaf obsHashes
    std::vector<BattleContext> capturedLeaves;          // regenerated leaves of the current decision
    std::unordered_set<std::uint64_t> capturedSeen;     // dedup: one capture per obsHash per decision
    std::vector<ParticleLeafProbeRow> particleProbeRows;
    int particleProbeGroups = 0;
    std::uint64_t particleProbeSourceLeafSeq = 0;
    std::vector<struct ParticlePosteriorProbeRow> particlePosteriorRows;
    int particlePosteriorGroups = 0;
    std::uint64_t particlePosteriorSourceLeafSeq = 0;
    bool particlePosteriorAgeBins[2][16]{};
    std::vector<ParticlePosteriorAgeCandidate> particlePosteriorAgeCandidates[2];
    std::vector<int> particlePosteriorAgeSelected[2];
    std::string actionFingerprint;
    void init(std::uint64_t sd) {
        seed = sd; fightIdx = 0; floor = 0; act = 0; encounter.clear(); decIdx = 0;
        rng.seed(sd ? sd : 1);
        strata.assign(kLeafDiagStrata, {});
        stratumCounts.assign(kLeafDiagStrata, 0);
        recorded.clear();
        capturedLeaves.clear();
        capturedSeen.clear();
        particleProbeRows.clear();
        particleProbeGroups = 0;
        particleProbeSourceLeafSeq = 0;
        particlePosteriorRows.clear();
        particlePosteriorGroups = 0;
        particlePosteriorSourceLeafSeq = 0;
        for (auto &stratum : particlePosteriorAgeBins)
            for (bool &seen : stratum) seen = false;
        for (auto &candidates : particlePosteriorAgeCandidates) candidates.clear();
        for (auto &ordinals : particlePosteriorAgeSelected) ordinals.clear();
        actionFingerprint.clear();
    }
};
static thread_local LeafDiagCtx t_ld;

// ---- VNet query log (STS_VNET_QUERY_LOG=<path>) -----------------------------------
static std::string g_vnetQueryLogPath;
static double      g_vnetQuerySample = 1.0;
static std::mutex  g_vnetQueryLogMutex;
static std::ofstream g_vnetQueryLogFile;
static thread_local struct {
    std::uint64_t seed = 0;
    int fightIdx = -1;
    int decIdx = -1;
    bool active = false;
    std::mt19937_64 rng;
    std::string buf;
} t_vq;

static void vnetQueryLogFlush() {
    if (t_vq.buf.empty()) return;
    std::lock_guard<std::mutex> lock(g_vnetQueryLogMutex);
    if (!g_vnetQueryLogFile.is_open()) return;
    g_vnetQueryLogFile << t_vq.buf;
    g_vnetQueryLogFile.flush();
    t_vq.buf.clear();
}

static void onVNetQuery(const BattleContext &bc, double prediction) {
    if (!t_vq.active) return;
    if (g_vnetQuerySample < 1.0) {
        std::uniform_real_distribution<double> dist(0.0, 1.0);
        if (dist(t_vq.rng) >= g_vnetQuerySample) return;
    }
    const int nf = search::combatFeatureCount();
    std::vector<float> feats(nf);
    search::combatExtractFeatures(bc, feats.data());
    std::ostringstream o;
    o << t_vq.seed << ',' << t_vq.fightIdx << ',' << t_vq.decIdx
      << ',' << search::g_vnetTraceParent << ',' << search::g_vnetTraceDepth;
    for (int i = 0; i < nf; ++i) {
        o << ',';
        const float v = feats[i];
        if (v == (float)(long)v) o << (long)v; else o << v;
    }
    o << ',' << prediction << '\n';
    t_vq.buf += o.str();
    if (t_vq.buf.size() > 65536) vnetQueryLogFlush();
}

// 0 = hallway, 1 = elite, 2 = boss (elite set = MonsterEncounterPool::elites).
static int encounterDifficulty(sts::MonsterEncounter e) {
    if (sts::isBossEncounter(e)) return 2;
    for (const auto &row : MonsterEncounterPool::elites)
        for (const auto &el : row)
            if (el == e) return 1;
    return 0;
}

// Stratum partition: depth >= g_ldDeepDepth -> 9 (dedicated deep-tree subset);
// otherwise hpFrac band (0,1,2) x difficulty (0,1,2) -> 0..8. The deep subset
// is its own reservoir so early- AND late-depth states both get coverage; the
// hpFrac x difficulty reservoirs cover the rest of the search distribution.
static int leafDiagStratum(const BattleContext &bc, int depth) {
    if (depth >= g_ldDeepDepth) return 9;
    const double hpFrac = bc.player.maxHp > 0
        ? (double)bc.player.curHp / bc.player.maxHp : 0.0;
    const int hb = hpFrac < 0.30 ? 0 : (hpFrac < 0.70 ? 1 : 2);
    return hb * 3 + encounterDifficulty(bc.encounter);
}

static LeafDiagRow leafDiagMakeRow(const search::S3LeafDiagnostic &d, int stratum) {
    LeafDiagRow r;
    const BattleContext &bc = *d.bc;
    r.seed = t_ld.seed; r.fightIdx = t_ld.fightIdx; r.decIdx = t_ld.decIdx;
    r.floor = t_ld.floor; r.act = t_ld.act; r.encounter = t_ld.encounter;
    r.depth = d.treeDepth; r.obsHash = d.obsHash;
    r.nLegalActions = (int)legalActions(bc).size();
    r.stratum = stratum;
    const int nf = search::combatFeatureCount();
    r.feats.assign(nf, 0.f);
    search::combatExtractFeatures(bc, r.feats.data());
    r.endHpPred = d.vnetPred;
    if (std::isnan(d.vnetPred) && search::g_useVNet && search::g_combatVNet.loaded())
        r.endHpPred = search::g_combatVNet.predict(bc);
    r.utilityRPred = g_combatVNetDiag.loaded() ? g_combatVNetDiag.predict(bc)
                                               : std::numeric_limits<double>::quiet_NaN();
    r.rawRolloutEval = d.rawRolloutEval;
    r.blendedEval = d.blendedEval;
    return r;
}

// Hot-path leaf hook: cheap stratum computation + reservoir sampling per
// stratum. Full features + model predictions are computed only for accepted
// rows. Uses only t_ld.rng (never search RNG) and reads the leaf state.
static void leafDiagOnLeafQuery(const search::S3LeafDiagnostic &d) {
    const int stratum = leafDiagStratum(*d.bc, d.treeDepth);
    auto &res = t_ld.strata[stratum];
    int &cnt = t_ld.stratumCounts[stratum];
    if (cnt < g_ldPerStratum) {
        res.push_back(leafDiagMakeRow(d, stratum));
    } else {
        const int j = std::uniform_int_distribution<int>(0, cnt)(t_ld.rng);
        if (j < g_ldPerStratum) res[j] = leafDiagMakeRow(d, stratum);
    }
    ++cnt;
}

static std::string particleLeafDrawOrder(const BattleContext &bc) {
    std::ostringstream out;
    for (int i = (int)bc.cards.drawPile.size() - 1; i >= 0; --i) {
        if (i != (int)bc.cards.drawPile.size() - 1) out << ';';
        out << (int)bc.cards.drawPile[i].getId();
    }
    return out.str();
}

static bool particleLeafRngEqual(const BattleContext &a, const BattleContext &b) {
    return a.shuffleRng.seed0 == b.shuffleRng.seed0 && a.shuffleRng.seed1 == b.shuffleRng.seed1
        && a.shuffleRng.counter == b.shuffleRng.counter
        && a.cardRandomRng.seed0 == b.cardRandomRng.seed0 && a.cardRandomRng.seed1 == b.cardRandomRng.seed1
        && a.cardRandomRng.counter == b.cardRandomRng.counter
        && a.aiRng.seed0 == b.aiRng.seed0 && a.aiRng.seed1 == b.aiRng.seed1
        && a.aiRng.counter == b.aiRng.counter
        && a.miscRng.seed0 == b.miscRng.seed0 && a.miscRng.seed1 == b.miscRng.seed1
        && a.miscRng.counter == b.miscRng.counter
        && a.potionRng.seed0 == b.potionRng.seed0 && a.potionRng.seed1 == b.potionRng.seed1
        && a.potionRng.counter == b.potionRng.counter
        && a.monsterHpRng.seed0 == b.monsterHpRng.seed0 && a.monsterHpRng.seed1 == b.monsterHpRng.seed1
        && a.monsterHpRng.counter == b.monsterHpRng.counter;
}

static bool particleLeafSameMultiset(const BattleContext &a, const BattleContext &b) {
    if (a.cards.drawPile.size() != b.cards.drawPile.size()) return false;
    std::map<int, int> ca, cb;
    for (const auto &c : a.cards.drawPile) ++ca[(int)c.getId()];
    for (const auto &c : b.cards.drawPile) ++cb[(int)c.getId()];
    return ca == cb;
}

static void particleLeafProbeOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (g_particleLeafProbeFile.empty() || !d.searcher || !d.bc) return;
    const std::uint64_t sourceLeafId = ++t_ld.particleProbeSourceLeafSeq;
    if (g_particleLeafProbeMaxGroups > 0
        && t_ld.particleProbeGroups >= g_particleLeafProbeMaxGroups) return;
    if (g_particleLeafProbeRate < 1.0) {
        if (std::uniform_real_distribution<double>(0.0, 1.0)(t_ld.rng)
            >= g_particleLeafProbeRate) return;
    }
    const BattleContext &base = *d.bc;
    const int k = std::max(1, std::min(g_particleLeafProbeK, 64));
    const std::uint64_t rngSeed = (t_ld.seed * 0x9e3779b97f4a7c15ULL)
                                ^ sourceLeafId ^ 0x9e3779b97f4a7c15ULL;
    const int nf = search::combatFeatureCount();
    std::vector<float> baseFeatures(nf);
    search::combatExtractFeatures(base, baseFeatures.data());
    const std::string baseDrawOrder = particleLeafDrawOrder(base);
    std::vector<std::vector<CardInstance>> orders;
    std::unordered_set<std::string> distinctOrders;
    orders.push_back(base.cards.drawPile);
    distinctOrders.insert(baseDrawOrder);
    std::mt19937_64 orderRng(rngSeed ^ 0xd1b54a32d192ed03ULL);
    const int maxAttempts = std::max(16, k * 16);
    for (int attempt = 0; attempt < maxAttempts && (int)orders.size() < k; ++attempt) {
        std::vector<int> permutation(base.cards.drawPile.size());
        for (size_t i = 0; i < permutation.size(); ++i) permutation[i] = (int)i;
        std::shuffle(permutation.begin(), permutation.end(), orderRng);
        std::vector<CardInstance> candidate;
        candidate.reserve(permutation.size());
        for (int idx : permutation) candidate.push_back(base.cards.drawPile[idx]);
        std::ostringstream order;
        for (auto it = candidate.rbegin(); it != candidate.rend(); ++it) {
            if (it != candidate.rbegin()) order << ';';
            order << (int)it->getId();
        }
        if (distinctOrders.insert(order.str()).second) orders.push_back(std::move(candidate));
    }
    const int distinctCount = (int)distinctOrders.size();
    for (int variant = 0; variant < (int)orders.size(); ++variant) {
        BattleContext state = base;
        state.cards.drawPile = orders[variant];
        const std::string drawOrder = particleLeafDrawOrder(state);
        std::vector<float> features(nf);
        search::combatExtractFeatures(state, features.data());
        bool sameFeatures = features == baseFeatures;
        bool sameRng = particleLeafRngEqual(base, state);
        bool sameMultiset = particleLeafSameMultiset(base, state);
        std::mt19937_64 diagnosticRng(rngSeed);
        std::vector<search::Action> actions;
        double target = std::numeric_limits<double>::quiet_NaN();
        bool terminal = false;
        const int steps = d.searcher->diagnosticRollout(state, actions, diagnosticRng,
                                                         target, terminal);
        ParticleLeafProbeRow row;
        row.seed = t_ld.seed; row.fightIdx = t_ld.fightIdx; row.decIdx = t_ld.decIdx;
        row.sourceLeafId = sourceLeafId; row.obsHash = d.obsHash; row.variant = variant;
        row.depth = d.treeDepth; row.turn = base.turn; row.curHp = base.player.curHp;
        row.maxHp = base.player.maxHp; row.rolloutSteps = steps; row.terminal = terminal ? 1 : 0;
        row.invariantOk = (sameFeatures && sameRng && sameMultiset) ? 1 : 0;
        row.uniqueVariantsSampled = distinctCount;
        row.drawPileSize = (int)base.cards.drawPile.size(); row.target = target;
        row.rawRolloutEval = d.rawRolloutEval;
        row.encounter = t_ld.encounter; row.drawOrder = drawOrder;
        row.feats = std::move(features);
        t_ld.particleProbeRows.push_back(std::move(row));
    }
    ++t_ld.particleProbeGroups;
}

// Called at battle exit (runFullRunOOC, g_leafdiagActive): label the current
// fight's sampled rows with the fight outcome.
static void leafDiagFightEnd(const BattleContext &bc) {
    const int won = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
    for (auto &stratum : t_ld.strata)
        for (auto &row : stratum)
            if (row.fightIdx == t_ld.fightIdx) { row.won = won; row.fightEndHp = bc.player.curHp; }
}

static std::string leafDiagSeedCsv() {
    std::ostringstream o;
    for (int s = 0; s < kLeafDiagStrata; ++s)
        for (const auto &row : t_ld.strata[s]) {
            o << row.seed << ',' << row.fightIdx << ',' << row.decIdx << ','
              << row.floor << ',' << row.act << ',' << row.encounter << ','
              << row.depth << ',' << row.obsHash << ','
              << row.nLegalActions << ',' << row.stratum << ',' << row.won << ','
              << row.fightEndHp;
            for (const float v : row.feats) {
                o << ',';
                if (v == (float)(long)v) o << (long)v; else o << v;
            }
            o << ',' << row.endHpPred << ',' << row.utilityRPred << ','
              << row.rawRolloutEval << ',' << row.blendedEval << '\n';
        }
    return o.str();
}

static std::string particleLeafProbeSeedCsv() {
    std::ostringstream o;
    for (const auto &row : t_ld.particleProbeRows) {
        o << row.seed << ',' << row.fightIdx << ',' << row.decIdx << ',' << row.sourceLeafId << ','
          << row.obsHash << ',' << row.variant << ',' << row.depth << ',' << row.encounter << ','
          << row.turn << ',' << row.curHp << ',' << row.maxHp << ',' << row.drawPileSize << ','
          << row.rolloutSteps << ',' << row.terminal << ',' << row.invariantOk << ',' << row.uniqueVariantsSampled << ',' << row.target
          << ',' << row.rawRolloutEval << ',' << row.drawOrder;
        for (const float v : row.feats) o << ',' << v;
        o << '\n';
    }
    return o.str();
}

static std::string particleLeafProbeHeaderStr() {
    std::string h = "seed,fightIdx,decIdx,sourceLeafId,obsHash,variant,treeDepth,encounterName,turn,"
                    "curHp,maxHp,drawPileSize,rolloutSteps,terminal,invariantOk,uniqueVariantsSampled,target,rawRolloutEval,drawOrder";
    for (const auto &name : search::combatFeatureNames()) h += ',' + name;
    return h;
}

// ---------------------------------------------------------------------------
// PHASE-1b posterior-valid particle sensitivity probe (particle_posterior_probe)
//
// For a sampled Searcher3 frontier-type-0 source leaf, replay the exact
// SEMANTIC pre-rollout action prefix (tree actions + expansion action +
// deterministic chain actions, with actual post-action observations recorded
// per step) under EVERY positive-weight particle of the searcher's CURRENT
// finite root belief. A candidate is compatible only if every checkpoint
// observation AND outcome match exactly (INTERMEDIATE_OBSERVATION_MISMATCH
// rejects even if the leaf later reconverges) and the final visible leaf
// observation + outcome match. Accepted leaf worlds are deduplicated by
// FullHiddenStateKey EQUALITY (ordered std::map, never a combined hash) with
// probability mass aggregated across collapsing root particles. Each
// evaluated compatible world is scored with the isolated diagnosticRollout
// using one per-group CRN seed; the searcher's RNG, tree, belief, and the
// live battle are never touched. Source groups whose source particle needed
// the stale-particle fallback shuffle are marked SOURCE_PARTICLE_FALLBACK and
// are scientifically ineligible (their replay is NOT an implementation
// failure). "Posterior-valid" is relative to Searcher3's finite belief
// approximation, not an exact Bayesian posterior.
// ---------------------------------------------------------------------------
struct ParticlePosteriorProbeRow {
    int rowType = 0;                     // 0 = group summary, 1 = evaluated compatible world
    std::uint64_t seed = 0, obsHash = 0, sourceLeafId = 0;
    int fightIdx = -1, decIdx = -1, treeDepth = 0, turn = 0;
    int curHp = 0, maxHp = 0, drawPileSize = 0;
    int rootParticleCount = 0, positiveParticleCount = 0, replayAttempted = 0;
    int replayCompatibleParticles = 0, uniqueCompatibleStates = 0, evaluatedWorldCount = 0;
    double compatibleMass = 0.0, evaluatedMass = 0.0;
    int sourceParticleIndex = -1, sourceParticleReplayOk = -1, sourceParticleFallback = 0;
    int groupEligible = 1, invariantOk = 1;
    std::string replayFailure;
    int semanticReplayFailures = 0, actionIllegalFailures = 0, intermediateObservationMismatches = 0;
    int intermediateOutcomeMismatches = 0, finalObservationMismatches = 0, drawPileMismatches = 0;
    int firstMismatchCheckpoint = -1;
    std::uint64_t expectedMismatchHash = 0, actualMismatchHash = 0;
    std::uint32_t mismatchActionBits = 0;
    int rootCarriedFlag = 0, reuseGeneration = 0, reuseSearchCount = -1;
    int searchSimulation = 0;
    std::string ageStratum;
    int ageBin = -1;
    int candidateParticleIndex = -1, candidateIsSource = 0, dedupOrdinal = -1;
    int semanticBranchesCreated = 0, maxSurvivingBranches = 0, branchesCollapsed = 0;
    int extraSemanticBranches = 0;
    int replayExplosion = 0;
    int rolloutSteps = 0, terminal = 0;
    double candidateWeight = 0.0;
    double target = std::numeric_limits<double>::quiet_NaN();
    double controlledTarget = std::numeric_limits<double>::quiet_NaN();
    double controlledTargetStd = std::numeric_limits<double>::quiet_NaN();
    std::string encounter, rngSignature, drawOrder;
};

// Audit-only RNG signature telemetry; hidden-state identity/dedup uses
// FullHiddenStateKey equality, never this hash.
static std::string posteriorProbeRngSignature(const sts::FullHiddenStateKey &key) {
    std::uint64_t h = 0xcbf29ce484222325ULL;
    for (int i = 0; i < 6; ++i) {
        h ^= key.seed0[i]; h *= 1099511628211ULL;
        h ^= key.seed1[i]; h *= 1099511628211ULL;
        h ^= (std::uint64_t)(std::int64_t)key.counter[i]; h *= 1099511628211ULL;
    }
    std::ostringstream o;
    o << std::hex << h;
    return o.str();
}

// Semantic remap of one recorded checkpoint action onto a candidate replay
// state whose hand order may differ. CARD rebinds by canonical card identity
// (resolveCardKeyInHand); END_TURN and POTION raw bits carry visible
// slot/target semantics and replay exactly. Any other action type (all
// card-select paths) has no exact semantic replay here -> nullopt, which
// marks the whole source group ineligible rather than guessing.
static std::optional<search::Action> posteriorProbeRemapAction(
    const search::S3LeafActionCheckpoint &cp, const BattleContext &state) {
    switch (cp.action.getActionType()) {
    case search::ActionType::CARD: {
        if (!cp.hasCardKey) return std::nullopt;
        search::BattleScumSearcher3::CardActionKey key;
        key.id = cp.cardId;
        key.upgradeCount = cp.upgradeCount;
        key.costForTurn = cp.costForTurn;
        key.freeToPlayOnce = cp.freeToPlayOnce;
        key.specialData = cp.specialData;
        key.target = cp.target;
        const auto hi = search::resolveCardKeyInHand(key, state);
        if (!hi) return std::nullopt;
        if (key.target >= 0)
            return search::Action(search::ActionType::CARD, *hi, key.target);
        return search::Action(search::ActionType::CARD, *hi);
    }
    case search::ActionType::END_TURN:
    case search::ActionType::POTION:
        return cp.action;
    default:
        return std::nullopt;   // SINGLE_/MULTI_CARD_SELECT: not exactly replayable
    }
}

static std::string replayCardDebug(const search::S3LeafActionCheckpoint &cp,
                                   const BattleContext &state,
                                   const search::Action &resolved) {
    std::ostringstream out;
    const int raw = cp.action.getSourceIdx();
    const int resolvedIndex = resolved.getSourceIdx();
    const int matches = std::count_if(state.cards.hand.begin(),
                                      state.cards.hand.begin() + state.cards.cardsInHand,
                                      [&](const CardInstance &card) {
        return card.getId() == cp.cardId
            && card.getUpgradeCount() == cp.upgradeCount
            && card.costForTurn == cp.costForTurn
            && card.freeToPlayOnce == cp.freeToPlayOnce
            && card.specialData == cp.specialData;
    });
    const CardInstance *resolvedCard = (resolvedIndex >= 0
        && resolvedIndex < state.cards.cardsInHand) ? &state.cards.hand[resolvedIndex] : nullptr;
    out << "checkpoint=" << cp.action.getSourceIdx()
        << ",rawIndex=" << raw
        << ",sourceUniqueId=" << cp.sourceUniqueId
        << ",resolvedIndex=" << resolvedIndex
        << ",resolvedUniqueId=" << (resolvedCard ? resolvedCard->uniqueId : -1)
        << ",sameIndex=" << (raw == resolvedIndex)
        << ",sameUniqueId=" << (resolvedCard && resolvedCard->uniqueId == cp.sourceUniqueId)
        << ",semanticMatches=" << matches
        << ",sourceCardId=" << (int)cp.cardId
        << ",sourceUpgradeCount=" << (int)cp.upgradeCount
        << ",sourceCost=" << (int)cp.sourceCost
        << ",sourceCostForTurn=" << (int)cp.costForTurn
        << ",sourceFreeToPlayOnce=" << cp.freeToPlayOnce
        << ",sourceSpecialData=" << cp.specialData
        << ",sourceRetain=" << cp.sourceRetain
        << ",target=" << cp.target;
    if (resolvedCard) {
        out << ",resolvedCardId=" << (int)resolvedCard->getId()
            << ",resolvedUpgradeCount=" << resolvedCard->getUpgradeCount()
            << ",resolvedCost=" << (int)resolvedCard->cost
            << ",resolvedCostForTurn=" << (int)resolvedCard->costForTurn
            << ",resolvedFreeToPlayOnce=" << resolvedCard->freeToPlayOnce
            << ",resolvedSpecialData=" << resolvedCard->specialData
            << ",resolvedRetain=" << resolvedCard->retain;
    }
    return out.str();
}

static bool replaySourcePrefix(const BattleContext &root,
                               const search::S3LeafDiagnostic &d,
                               bool semantic, int &firstMismatch,
                               std::string &detail) {
    BattleContext state = root;
    firstMismatch = -1;
    for (size_t i = 0; i < d.actionCheckpoints.size(); ++i) {
        const auto &cp = d.actionCheckpoints[i];
        std::optional<search::Action> action = semantic
            ? posteriorProbeRemapAction(cp, state)
            : std::optional<search::Action>(cp.action);
        if (!action || !action->isValidAction(state)) {
            firstMismatch = (int)i;
            detail = "unresolved_or_illegal";
            return false;
        }
        if (semantic && cp.action.getActionType() == search::ActionType::CARD) {
            if (!detail.empty()) detail += ";";
            detail += replayCardDebug(cp, state, *action);
        }
        action->execute(state);
        const auto obs = sts::CombatObservation::fromBattleContext(state);
        if (obs != cp.observation || state.outcome != cp.outcome) {
            firstMismatch = (int)i;
            return false;
        }
    }
    return true;
}

static void writeReplayDebugRow(const search::S3LeafDiagnostic &d,
                                const BattleContext &sourceRoot,
                                std::uint64_t seed, int fightIdx, int decIdx,
                                std::uint64_t sourceLeafId) {
    if (g_particlePosteriorReplayDebugFile.empty()) return;
    int rawMismatch = -1, semanticMismatch = -1;
    std::string rawDetail, semanticDetail;
    const bool rawOk = replaySourcePrefix(sourceRoot, d, false, rawMismatch, rawDetail);
    const bool semanticOk = replaySourcePrefix(sourceRoot, d, true, semanticMismatch, semanticDetail);
    static std::mutex mutex;
    std::lock_guard<std::mutex> lock(mutex);
    std::ifstream probe(g_particlePosteriorReplayDebugFile);
    const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
    std::ofstream out(g_particlePosteriorReplayDebugFile, std::ios::app);
    if (!out) return;
    if (empty) out << "seed,fightIdx,decIdx,sourceLeafId,sourceParticleIndex,rawSourceReplayOk,"
                      "semanticSourceReplayOk,rawFirstMismatchCheckpoint,semanticFirstMismatchCheckpoint,"
                      "rootCarried,reuseGeneration,hiddenFingerprintBeforeMismatch,cardDebug\n";
    std::uint64_t hiddenBefore = 0;
    if (semanticMismatch > 0 && semanticMismatch - 1 < (int)d.actionCheckpoints.size())
        hiddenBefore = d.actionCheckpoints[semanticMismatch - 1].hiddenFingerprint;
    out << seed << ',' << fightIdx << ',' << decIdx << ',' << sourceLeafId << ','
        << d.particleIndex << ',' << rawOk << ',' << semanticOk << ','
        << rawMismatch << ',' << semanticMismatch << ',' << d.rootCarried << ','
        << d.reuseGeneration << ',' << hiddenBefore << ",\"" << semanticDetail << "\"\n";
}

static int particlePosteriorAgeStratumForOrdinal(int ordinal) {
    if (ordinal >= g_particlePosteriorAgeEarlyStart
        && ordinal <= g_particlePosteriorAgeEarlyEnd) return 0;
    if (ordinal >= g_particlePosteriorAgeLateStart
        && ordinal <= g_particlePosteriorAgeLateEnd) return 1;
    return -1;
}

static void particlePosteriorAgeCaptureOnLeafQuery(
    const search::S3LeafDiagnostic &d) {
    if (d.frontierType != 0 || t_ld.fightIdx != 0 || t_ld.decIdx != 0) return;
    const int stratum = particlePosteriorAgeStratumForOrdinal(
        d.searchSimulationOrdinal);
    if (stratum < 0) return;
    auto &candidates = t_ld.particlePosteriorAgeCandidates[stratum];
    if (!candidates.empty() && candidates.back().ordinal == d.searchSimulationOrdinal)
        return;
    ParticlePosteriorAgeCandidate candidate;
    candidate.stratum = stratum;
    candidate.ordinal = d.searchSimulationOrdinal;
    candidate.state = *d.bc;
    candidate.diagnostic = d;
    candidates.push_back(std::move(candidate));
}

static std::vector<int> particlePosteriorAgeSelectEvenly(
    const std::vector<ParticlePosteriorAgeCandidate> &candidateRows) {
    std::vector<int> candidates;
    candidates.reserve(candidateRows.size());
    for (const auto &candidate : candidateRows) candidates.push_back(candidate.ordinal);
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
    std::vector<int> selected;
    if (candidates.size() < static_cast<size_t>(g_particlePosteriorAgeMinPerStratum))
        return selected;
    const int target = static_cast<int>(std::min<size_t>(16, candidates.size()));
    selected.reserve(target);
    for (int rank = 0; rank < target; ++rank) {
        const size_t index = std::min(
            candidates.size() - 1,
            (static_cast<size_t>(2 * rank + 1) * candidates.size())
                / (2 * static_cast<size_t>(target)));
        selected.push_back(candidates[index]);
    }
    return selected;
}

static void particlePosteriorProbeOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (g_particlePosteriorProbeFile.empty() || !d.searcher || !d.bc) return;
    if (d.frontierType != 0) return;   // actual S3 frontier leaves only
    int ageStratum = -1;
    int ageBin = -1;
    if (g_particlePosteriorAgeSplit) {
        if (t_ld.fightIdx != 0 || t_ld.decIdx != 0) return;
        ageStratum = particlePosteriorAgeStratumForOrdinal(
            d.searchSimulationOrdinal);
        if (ageStratum < 0) return;
        const auto &selected = t_ld.particlePosteriorAgeSelected[ageStratum];
        const auto it = std::find(selected.begin(), selected.end(),
                                  d.searchSimulationOrdinal);
        if (it == selected.end()) return;
        ageBin = static_cast<int>(it - selected.begin());
        if (ageBin >= 16 || t_ld.particlePosteriorAgeBins[ageStratum][ageBin]) return;
    } else if (g_particlePosteriorProbeMaxGroups >= 0
               && t_ld.particlePosteriorGroups >= g_particlePosteriorProbeMaxGroups) return;
    const std::uint64_t sourceLeafId = ++t_ld.particlePosteriorSourceLeafSeq;
    const BattleContext &base = *d.bc;
    const auto &particles = d.searcher->belief.particles;
    const int sourceIndex = static_cast<int>(d.particleIndex);

    ParticlePosteriorProbeRow g;
    g.seed = t_ld.seed; g.fightIdx = t_ld.fightIdx; g.decIdx = t_ld.decIdx;
    g.sourceLeafId = sourceLeafId; g.obsHash = d.obsHash; g.treeDepth = d.treeDepth;
    g.turn = base.turn; g.curHp = base.player.curHp; g.maxHp = base.player.maxHp;
    g.drawPileSize = (int)base.cards.drawPile.size(); g.encounter = t_ld.encounter;
    g.rootParticleCount = (int)particles.size();
    g.positiveParticleCount = (int)std::count_if(
        particles.begin(), particles.end(),
        [](const sts::HiddenBattleState &p) { return p.weight > 0.0; });
    double positiveWeightTotal = 0.0;
    for (const auto &p : particles) if (p.weight > 0.0) positiveWeightTotal += p.weight;
    g.sourceParticleIndex = sourceIndex;
    g.sourceParticleFallback = d.particleUsedFallback ? 1 : 0;
    g.rootCarriedFlag = d.rootCarried ? 1 : 0;
    g.reuseGeneration = d.reuseGeneration;
    g.reuseSearchCount = d.reuseSearchCount;
    g.searchSimulation = d.searchSimulationOrdinal;
    g.ageStratum = ageStratum == 0 ? "EARLY" : ageStratum == 1 ? "LATE" : "";
    g.ageBin = ageBin;
    if (!g_particlePosteriorReplayDebugFile.empty()
        && sourceIndex >= 0 && sourceIndex < (int)particles.size()) {
        BattleContext sourceRoot = *d.searcher->rootBc;
        if (search::applyHiddenStateExact(sourceRoot, particles[sourceIndex]))
            writeReplayDebugRow(d, sourceRoot, t_ld.seed, t_ld.fightIdx,
                                t_ld.decIdx, sourceLeafId);
    }

    auto finishGroup = [&]() {
        t_ld.particlePosteriorRows.push_back(g);
        ++t_ld.particlePosteriorGroups;
        if (g_particlePosteriorAgeSplit)
            t_ld.particlePosteriorAgeBins[ageStratum][ageBin] = true;
    };

    // (1) Source simulation needed the stale-particle fallback shuffle: the
    // stored particle alone does not specify that world. Scientifically
    // ineligible; NOT an implementation failure and replay is not attempted.
    if (d.particleUsedFallback) {
        g.groupEligible = 0;
        g.sourceParticleReplayOk = -1;
        g.replayFailure = "SOURCE_PARTICLE_FALLBACK";
        finishGroup();
        return;
    }
    if (sourceIndex < 0 || sourceIndex >= (int)particles.size()) {
        g.groupEligible = 0; g.sourceParticleReplayOk = -1; g.invariantOk = 0;
        g.replayFailure = "SOURCE_PARTICLE_INDEX_INVALID";
        finishGroup();
        return;
    }
    // (2) The prefix must be exactly replayable by action semantics. Any
    // card-select action (or a CARD without recorded identity) makes the whole
    // group ineligible — no raw-index replay is pretended to be equivalent.
    for (const auto &cp : d.actionCheckpoints) {
        const auto type = cp.action.getActionType();
        const bool intrinsicallyUnsupported =
            (type != search::ActionType::CARD
             && type != search::ActionType::END_TURN
             && type != search::ActionType::POTION)
            || (type == search::ActionType::CARD && !cp.hasCardKey);
        if (intrinsicallyUnsupported) {
            g.groupEligible = 0;
            g.sourceParticleReplayOk = -1;
            g.replayFailure = "UNREPLAYABLE_ACTION_PREFIX";
            finishGroup();
            return;
        }
    }

    const CombatObservation sourceFinalObs = CombatObservation::fromBattleContext(base);
    struct Candidate {
        int rootIndex = -1;
        double weight = 0.0;
        bool source = false;
        BattleContext state;
        sts::FullHiddenStateKey key;
    };
    using PhysicalCardKey = std::tuple<CardId, std::int16_t,
                                       std::int8_t, std::int8_t, bool, bool, bool>;
    struct ReplayStateKey {
        sts::FullHiddenStateKey hidden;
        std::vector<PhysicalCardKey> draw, hand, discard, exhaust;
        bool operator<(const ReplayStateKey &o) const {
            return std::tie(hidden, draw, hand, discard, exhaust)
                < std::tie(o.hidden, o.draw, o.hand, o.discard, o.exhaust);
        }
    };
    // Canonicalize the identity of each ordered card zone so that
    // permutations of behaviorally-identical duplicate cards (differing only
    // by simulator-private CardInstance::uniqueId) collapse during replay
    // dedup. All gameplay-meaningful fields (id, specialData, cost,
    // costForTurn, upgraded, freeToPlayOnce, retain) remain in the key; zone
    // ORDER is preserved (hand/draw/discard ordering is observably meaningful).
    auto physicalCards = [](const std::vector<CardInstance> &cards) {
        std::vector<PhysicalCardKey> out;
        out.reserve(cards.size());
        for (const auto &c : cards)
            out.emplace_back(c.id, c.specialData, c.cost,
                             c.costForTurn, c.upgraded, c.freeToPlayOnce, c.retain);
        return out;
    };
    auto replayStateKey = [&](const BattleContext &state) {
        ReplayStateKey key{sts::fullHiddenStateKey(state), {}, {}, {}, {}};
        key.draw = physicalCards(state.cards.drawPile);
        key.hand = physicalCards(std::vector<CardInstance>(
            state.cards.hand.begin(), state.cards.hand.begin() + state.cards.cardsInHand));
        key.discard = physicalCards(state.cards.discardPile);
        key.exhaust = physicalCards(state.cards.exhaustPile);
        return key;
    };
    std::vector<Candidate> compatible;
    std::map<sts::FullHiddenStateKey, size_t> byKey;   // equality-backed exact identity
    int acceptedParticles = 0;

    auto replayCandidate = [&](int particleIndex, bool isSource) {
        Candidate c;
        c.rootIndex = particleIndex;
        c.weight = positiveWeightTotal > 0.0
            ? particles[particleIndex].weight / positiveWeightTotal : 0.0;
        c.source = isSource;
        c.state = *d.searcher->rootBc;
        if (!search::applyHiddenStateExact(c.state, particles[particleIndex])) {
            ++g.drawPileMismatches;
            return;
        }
        std::vector<Candidate> frontier{std::move(c)};
        for (size_t checkpointIndex = 0; checkpointIndex < d.actionCheckpoints.size(); ++checkpointIndex) {
            const auto &cp = d.actionCheckpoints[checkpointIndex];
            std::vector<Candidate> next;
            int generatedThisCheckpoint = 0;
            for (const auto &stateCandidate : frontier) {
                std::vector<search::Action> actions;
                if (cp.action.getActionType() == search::ActionType::CARD) {
                    search::BattleScumSearcher3::CardActionKey key;
                    key.id = cp.cardId; key.upgradeCount = cp.upgradeCount;
                    key.costForTurn = cp.costForTurn; key.freeToPlayOnce = cp.freeToPlayOnce;
                    key.specialData = cp.specialData; key.target = cp.target;
                    for (int hi = 0; hi < stateCandidate.state.cards.cardsInHand; ++hi) {
                        const auto &card = stateCandidate.state.cards.hand[hi];
                        if (card.getId() == key.id && card.getUpgradeCount() == key.upgradeCount
                            && card.costForTurn == key.costForTurn
                            && card.freeToPlayOnce == key.freeToPlayOnce
                            && card.specialData == key.specialData) {
                            auto action = key.target >= 0
                                ? search::Action(search::ActionType::CARD, hi, key.target)
                                : search::Action(search::ActionType::CARD, hi);
                            if (action.isValidAction(stateCandidate.state)) actions.push_back(action);
                        }
                    }
                    g.semanticBranchesCreated += (int)actions.size();
                    g.extraSemanticBranches += std::max(0, (int)actions.size() - 1);
                    generatedThisCheckpoint += (int)actions.size();
                } else {
                    const auto action = posteriorProbeRemapAction(cp, stateCandidate.state);
                    if (action && action->isValidAction(stateCandidate.state)) actions.push_back(*action);
                }
                for (const auto &action : actions) {
                    Candidate successor = stateCandidate;
                    action.execute(successor.state);
                    const auto obs = CombatObservation::fromBattleContext(successor.state);
                    if (obs == cp.observation && successor.state.outcome == cp.outcome)
                        next.push_back(std::move(successor));
                    else if (obs != cp.observation) ++g.intermediateObservationMismatches;
                    else ++g.intermediateOutcomeMismatches;
                }
            }
            std::map<ReplayStateKey, size_t> checkpointKeys;
            std::vector<Candidate> deduped;
            for (auto &candidate : next) {
                const auto key = replayStateKey(candidate.state);
                const auto inserted = checkpointKeys.emplace(key, deduped.size());
                if (inserted.second)
                    deduped.push_back(std::move(candidate));
                else {
                    auto &existing = deduped[inserted.first->second];
                    ++g.branchesCollapsed;
                }
            }
            g.maxSurvivingBranches = std::max(g.maxSurvivingBranches, (int)deduped.size());
            if (!g_particlePosteriorReplayTraceFile.empty()) {
                static std::mutex traceMutex;
                std::lock_guard<std::mutex> lock(traceMutex);
                std::ifstream probe(g_particlePosteriorReplayTraceFile);
                const bool empty = !probe.good() || probe.peek() == std::ifstream::traits_type::eof();
                std::ofstream out(g_particlePosteriorReplayTraceFile, std::ios::app);
                if (out) {
                    if (empty)
                        out << "seed,sourceLeafId,checkpoint,incoming,generated,outgoing,actionType,cardId\n";
                    out << t_ld.seed << ',' << sourceLeafId << ',' << checkpointIndex << ','
                        << (int)frontier.size() << ',' << generatedThisCheckpoint
                        << ',' << (int)deduped.size()
                        << ',' << (int)cp.action.getActionType() << ',' << (int)cp.cardId << '\n';
                }
            }
            if (deduped.size() > g_particlePosteriorReplayCeiling) {
                g.replayExplosion = 1;
                g.replayFailure = "AMBIGUOUS_SEMANTIC_REPLAY_EXPLOSION";
                return;
            }
            frontier = std::move(deduped);
            if (frontier.empty()) return;
        }
        std::map<sts::FullHiddenStateKey, Candidate> localLeaves;
        bool finalAccepted = false;
        for (auto &survivor : frontier) {
            const CombatObservation finalObs = CombatObservation::fromBattleContext(survivor.state);
            if (finalObs != sourceFinalObs || survivor.state.outcome != d.outcome) {
                ++g.finalObservationMismatches;
                continue;
            }
            survivor.key = sts::fullHiddenStateKey(survivor.state);
            const auto existing = localLeaves.find(survivor.key);
            if (existing == localLeaves.end()) {
                localLeaves.emplace(survivor.key, std::move(survivor));
            } else if (survivor.source && !existing->second.source) {
                existing->second = std::move(survivor);
            }
        }
        if (!localLeaves.empty()) {
            const double branchWeight = c.weight / localLeaves.size();
            for (auto &[key, survivor] : localLeaves) {
                survivor.weight = branchWeight;
                const auto found = byKey.find(key);
                if (found != byKey.end()) {
                    compatible[found->second].weight += survivor.weight;
                    compatible[found->second].source |= survivor.source;
                } else {
                    byKey.emplace(key, compatible.size());
                    compatible.push_back(std::move(survivor));
                }
            }
            finalAccepted = true;
        }
        if (finalAccepted) ++acceptedParticles;
    };

    g.replayAttempted = g.positiveParticleCount
        + (particles[sourceIndex].weight > 0.0 ? 0 : 1);
    replayCandidate(sourceIndex, true);
    for (int i = 0; i < (int)particles.size(); ++i)
        if (particles[i].weight > 0.0 && i != sourceIndex)
            replayCandidate(i, false);

    if (g.replayExplosion) {
        g.groupEligible = 0;
        g.sourceParticleReplayOk = -1;
        finishGroup();
        return;
    }

    g.replayCompatibleParticles = acceptedParticles;
    bool sourceOk = false;
    double compatibleMass = 0.0;
    for (const auto &c : compatible) {
        compatibleMass += c.weight;
        if (c.source) sourceOk = true;
    }
    g.uniqueCompatibleStates = (int)compatible.size();
    g.compatibleMass = compatibleMass;

    // (3) Mandatory source-particle replay invariant. The exact source
    // particle MUST reproduce the source leaf; failure is an implementation
    // failure that invalidates the run.
    if (!sourceOk) {
        g.sourceParticleReplayOk = 0;
        g.invariantOk = 0;
        g.replayFailure = "SOURCE_PARTICLE_REPLAY_FAILED";
        finishGroup();
        return;
    }
    g.sourceParticleReplayOk = 1;

    // (4) Evaluation set: all unique compatible states by default; if K > 0,
    // deterministic mass-respecting selection (highest weight first, ties by
    // discovery order) with the source world always included, no padding.
    std::vector<int> order(compatible.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = (int)i;
    const int cap = g_particlePosteriorProbeK > 0
        ? std::min(g_particlePosteriorProbeK, (int)compatible.size())
        : (int)compatible.size();
    if ((int)order.size() > cap) {
        std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
            return compatible[a].weight > compatible[b].weight;
        });
        order.resize(cap);
        int sourceSlot = -1;
        for (int i = 0; i < (int)compatible.size(); ++i)
            if (compatible[i].source) { sourceSlot = i; break; }
        if (sourceSlot >= 0 && !order.empty()
            && std::find(order.begin(), order.end(), sourceSlot) == order.end())
            order.back() = sourceSlot;
    }
    g.evaluatedWorldCount = (int)order.size();
    double evaluatedMass = 0.0;
    for (int idx : order) evaluatedMass += compatible[idx].weight;
    g.evaluatedMass = evaluatedMass;

    const std::uint64_t rngSeed = (t_ld.seed * 0x9e3779b97f4a7c15ULL)
                                ^ sourceLeafId ^ 0x9e3779b97f4a7c15ULL;
    constexpr int kControlledRollouts = 4;
    struct ControlledValue { double mean = 0.0; double std = 0.0; };
    std::map<std::vector<sts::FullHiddenCardId>, ControlledValue> controlled;
    for (int idx : order) {
        const auto &candidate = compatible[idx];
        auto &value = controlled[candidate.key.drawPileOrder];
        std::vector<double> samples;
        samples.reserve(kControlledRollouts);
        for (int replicate = 0; replicate < kControlledRollouts; ++replicate) {
            BattleContext controlledState = base;
            controlledState.cards.drawPile = candidate.state.cards.drawPile;
            std::mt19937_64 controlledRng(rngSeed ^ (std::uint64_t)replicate
                                          * 0xd1b54a32d192ed03ULL);
            std::vector<search::Action> controlledActions;
            double controlledTarget = std::numeric_limits<double>::quiet_NaN();
            bool controlledTerminal = false;
            d.searcher->diagnosticRollout(controlledState, controlledActions,
                                          controlledRng, controlledTarget,
                                          controlledTerminal);
            samples.push_back(controlledTarget);
        }
        value.mean = std::accumulate(samples.begin(), samples.end(), 0.0)
            / samples.size();
        double variance = 0.0;
        for (double sample : samples)
            variance += (sample - value.mean) * (sample - value.mean);
        value.std = std::sqrt(variance / samples.size());
    }
    t_ld.particlePosteriorRows.push_back(g);   // group summary row first
    ++t_ld.particlePosteriorGroups;
    if (g_particlePosteriorAgeSplit)
        t_ld.particlePosteriorAgeBins[ageStratum][ageBin] = true;
    for (int ordinal = 0; ordinal < (int)order.size(); ++ordinal) {
        const auto &c = compatible[order[ordinal]];
        BattleContext state = c.state;   // exact full leaf world, draw order + 6 RNG streams preserved
        std::mt19937_64 diagnosticRng(rngSeed);   // same CRN seed across worlds within this group
        std::vector<search::Action> actions;
        double target = std::numeric_limits<double>::quiet_NaN();
        bool terminal = false;
        const int steps = d.searcher->diagnosticRollout(state, actions, diagnosticRng,
                                                        target, terminal);
        ParticlePosteriorProbeRow w = g;   // repeat source-group metadata on every world row
        w.rowType = 1;
        w.candidateParticleIndex = c.rootIndex;
        w.candidateWeight = c.weight;
        w.candidateIsSource = c.source ? 1 : 0;
        w.dedupOrdinal = ordinal;
        w.rngSignature = posteriorProbeRngSignature(c.key);
        w.drawOrder = particleLeafDrawOrder(c.state);
        w.rolloutSteps = steps;
        w.terminal = terminal ? 1 : 0;
        w.target = target;
        const auto controlledIt = controlled.find(c.key.drawPileOrder);
        if (controlledIt != controlled.end()) {
            w.controlledTarget = controlledIt->second.mean;
            w.controlledTargetStd = controlledIt->second.std;
        }
        t_ld.particlePosteriorRows.push_back(std::move(w));
    }
}

static std::string leafDiagHeaderStr() {
    // Provenance prefix: encounterName is the UPPER_CASE enum NAME (Python's
    // encounter_difficulty() tables); the canonical feature block below
    // carries the numeric "encounter" and "turn" encodings, so those two are
    // NOT repeated here (duplicate CSV column names would shadow them under
    // csv.DictReader).
    std::string h = "seed,fightIdx,decIdx,floor,act,encounterName,treeDepth,"
                    "obsHash,nLegalActions,stratum,fightWon,fightEndHp,";
    const auto &names = search::combatFeatureNames();
    for (size_t i = 0; i < names.size(); ++i) { if (i) h += ','; h += names[i]; }
    h += ",endHp_pred,utilityR_pred,rawRolloutEval,blendedEval";
    return h;
}

// ── fightrep: fight-start snapshot/replay harness ──────────────────────────
// STS_FIGHTREP_CAPTURE_DIR=<dir>: during runFullRunOOC, serialize the
// STARTING BattleContext of every Act-3 boss fight (battleRoom==BOSS,
// battleAct==3, i.e. floor 50) into <dir>/fight_<seed>.bin (raw
// serializeBattleContext blob) and write <dir>/fight_<seed>.csv after the
// fight (seed,encounter,floor,won,hpEnd,turns). One file per seed makes
// parallel capture processes safe (no shared-file races). The captured blob
// is exactly the pre-search fight state (all 6 RNG streams + bc.seed + visible
// state), so "fightrep" can re-search the isolated fight at other particle
// counts / sim budgets with the recorded fair-S3 stack and report per-cell
// outcomes.
static std::string g_fightRepCaptureDir;

struct FightRepCaptureMeta {
    std::uint64_t seed;
    int encounter, floor;
    std::uint64_t offset;
    std::uint32_t size;
};

// Fight-start capture (runFullRunOOC, after bc.init): write the blob now; the
// CSV row is written after the fight so it carries the capture-time outcome
// for the replay fidelity gate.
static void fightRepCaptureStart(const BattleContext &bc, std::uint64_t seed) {
    if (g_fightRepCaptureDir.empty()) return;
    const std::vector<std::uint8_t> blob = sts::serializeBattleContext(bc);
    std::ofstream bin(g_fightRepCaptureDir + "/fight_" + std::to_string(seed) + ".bin",
                      std::ios::binary);
    if (!bin) { std::cerr << "[fightrep] cannot open " << g_fightRepCaptureDir
                          << "/fight_" << seed << ".bin\n"; return; }
    bin.write((const char *)blob.data(), (std::streamsize)blob.size());
}

// Fight-end (runFullRunOOC, after playoutBattle): write the index row with the
// capture-time outcome (won,hpEnd,turns) so the replay fidelity gate can
// compare replay outcomes against what the full run actually did.
static void fightRepCaptureEnd(const BattleContext &bc, std::uint64_t seed) {
    if (g_fightRepCaptureDir.empty()) return;
    std::ofstream csv(g_fightRepCaptureDir + "/fight_" + std::to_string(seed) + ".csv");
    if (!csv) { std::cerr << "[fightrep] cannot open " << g_fightRepCaptureDir
                          << "/fight_" << seed << ".csv\n"; return; }
    csv << "seed,encounter,floor,won,hpEnd,turns\n"
        << seed << ',' << (int)bc.encounter << ',' << bc.floorNum << ','
        << (bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0) << ','
        << bc.player.curHp << ',' << bc.turn << '\n';
}

// Replay captured Act-3 boss fight-start snapshots across a (particles x sims)
// grid with the recorded fair-S3 stack. For each captured fight and each cell
// it deserializes the fight-start BattleContext, sets the particle count and
// the per-decision sim budget, and plays the isolated fight out. Output rows:
// seed,encounter,floor,particles,sims,won,hpEnd,turns. The grid is bounded by
// nFights x |particles| x |sims|; the caller passes it through seed_guard.
static void fightRepReplay(const std::string &captureDir, const std::string &outCsv,
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
    search::g_fairPlay = true;
    search::g_useSearcher3 = true;
    search::g_s3Belief = false;
    search::g_s3Chain = false;
    search::g_liveValid = true;
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
        search::g_s3Particles = p;
        for (int s : sims) {
            std::vector<std::string> rows((std::size_t)n);
            #pragma omp parallel for schedule(dynamic)
            for (int i = 0; i < n; ++i) {
                const FightRepCaptureMeta &m = fights[i];
                std::ifstream bin(captureDir + "/fight_" + std::to_string(m.seed) + ".bin",
                                  std::ios::binary);
                std::vector<std::uint8_t> blob((std::istreambuf_iterator<char>(bin)),
                                               std::istreambuf_iterator<char>());
                BattleContext bc = sts::deserializeBattleContext(blob.data(), blob.size());
                if (bc.outcome != Outcome::UNDECIDED) {   // shouldn't happen: snapshots are fight-start
                    rows[i] = std::to_string(m.seed) + ',' + std::to_string(m.encounter) + ','
                            + std::to_string(m.floor) + ',' + std::to_string(p) + ','
                            + std::to_string(s) + ",skip,0,0\n";
                    continue;
                }
                search::ScumSearchAgent2 agent;
                agent.simulationCountBase = s;
                agent.rng = std::default_random_engine(m.seed);
                agent.playoutBattle(bc);
                const int won = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
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

static RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                               bool e2cCapture = false) {
    vDisconnect();
    t_oocStrategicTraceRows.clear();
    t_oocStrategicTraceDecision = 0;
    t_shopV = shopV;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    if (g_forceRelic != RelicId::INVALID && !gc.relics.has(g_forceRelic)) {
        gc.relics.add({g_forceRelic, 0});
        for (std::vector<RelicId> *pool : {&gc.commonRelicPool, &gc.uncommonRelicPool,
                                           &gc.rareRelicPool, &gc.shopRelicPool, &gc.bossRelicPool})
            pool->erase(std::remove(pool->begin(), pool->end(), g_forceRelic), pool->end());
    }

    PathHistory path;                // pv* features for V queries (train/serve parity)
    E2cCapture e2c;
    if (e2cCapture) {
        trainingRunStart();
        e2c.seed = seed;
        e2c.path = &path;
        t_e2c = &e2c;
        t_e2cRows.clear();
    }
    t_pathActionUses = 0;
    t_actFightProbeDecisionIdx = 0;
    t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;
    bool clearedStopActBoss = false;
    int fightsLost = 0, fightsTotal = 0, deathCombat = -1, deathEncounter = -1;
    auto t0 = std::chrono::steady_clock::now();
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            search::g_potionKeepValue = potionKeepValue(gc);           // dynamic potion-saving
            if (search::g_useSearcher3 && g_termWin && g_winNet.ok)
                termWinArmForBattle(gc);   // terminal-leaf run-value bonus (cross-combat setup)
            BattleContext bc{};
            // The isolated Silver backend must enter before BattleContext::init
            // so its observational Runic-Dome hooks see the initial hidden
            // intent lifecycle.  The normal bestbench path deliberately
            // remains byte-for-byte below this opt-in branch.
            if (search::g_externalCombatBackend) {
                agent.playoutBattle(gc, bc);
                ++fightsTotal;
                if (bc.outcome == Outcome::PLAYER_LOSS) {
                    ++fightsLost;
                    if (deathCombat < 0) {
                        deathCombat = fightsTotal;
                        deathEncounter = (int)bc.encounter;
                    }
                }
                bc.exitBattle(gc);
                if (g_cpsiCtrProbe) cpsiCounterProbeAtState(gc);
                stallLogRow(gc, bc, seed);
                if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                    clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                    break;
                }
                continue;
            }
            bc.init(gc);
            if (t_e2c) e2cBeginFight(fightsTotal, gc, bc);
            if (g_runwinShadowActive)
                runwinShadowBeginFight(fightsTotal, gc, path, battleRoom, bc.encounter);
            if (g_runwinRankActive)
                runwinRankBeginFight(fightsTotal, gc, path, battleRoom, bc.encounter);
            if (!g_fightRepCaptureDir.empty() && battleAct == 3 && battleRoom == Room::BOSS)
                fightRepCaptureStart(bc, seed);   // fightrep: fight-start snapshot (floor-50 boss)
            if (g_sdiagActive) {   // searchdiag: per-fight run context
                g_sdiagCtx = SdiagRunCtx{};
                g_sdiagCtx.seed = seed;
                g_sdiagCtx.floor = gc.floorNum;
                g_sdiagCtx.act = gc.act;
                g_sdiagCtx.room = (int)gc.curRoom;
                g_sdiagCtx.encounter = (int)bc.encounter;
                g_sdiagCtx.fightIdx = fightsTotal;
            }
            if (g_leafdiagActive || g_frontiergenActive) {   // leafdiag/frontiergen: per-fight run context
                t_ld.fightIdx = fightsTotal;
                t_ld.floor = gc.floorNum;
                t_ld.act = gc.act;
                // UPPER_CASE enum NAME, so the CSV column matches the Python
                // tools' encounter_difficulty() tables (BOSSES/ELITES); the
                // canonical feature vector separately carries the numeric
                // encoding (combatExtractFeatures "encounter").
                t_ld.encounter = monsterEncounterEnumNames[(int)bc.encounter];
                t_ld.decIdx = 0;
            }
            // VNet query log: set per-fight context before combat
            // (the agent's internal Searcher3 loop handles per-decision iteration)
            if (!g_vnetQueryLogPath.empty()) {
                t_vq.active = true;
                t_vq.seed = seed;
                t_vq.fightIdx = fightsTotal;
                t_vq.decIdx = -1;
                t_vq.rng.seed(seed * 6364136223846793005ULL + (std::uint64_t)fightsTotal);
            }
            agent.playoutBattle(bc);
            if (!g_fightRepCaptureDir.empty() && battleAct == 3 && battleRoom == Room::BOSS)
                fightRepCaptureEnd(bc, seed);   // fightrep: index row + capture-time outcome
            if (g_sdiagActive) sdiagFightRow(bc);   // searchdiag: fight summary
            if (g_leafdiagActive) leafDiagFightEnd(bc);   // leafdiag: label this fight's sampled rows
            if (t_vq.active) vnetQueryLogFlush();         // VNet query log: flush this fight's rows
            if (search::g_useSearcher3 && g_termWin) termWinDisarm();
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) { ++fightsLost; if (deathCombat < 0) { deathCombat = fightsTotal; deathEncounter = (int)bc.encounter; } }
            if (t_e2c) {
                g_onBattleExitPersistent = e2cRawObserver;
                bc.exitBattle(gc);
                g_onBattleExitPersistent = nullptr;
            } else {
                bc.exitBattle(gc);
            }
            if (g_cpsiCtrProbe) cpsiCounterProbeAtState(gc);   // C_psi counter-sensitivity probe
            stallLogRow(gc, bc, seed);                          // stall telemetry (opt-in)
            if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                break;
            }
        } else if (oocActionNNPolicy(gc)) {
            // The action-conditioned next-combat NN is reapplied at every OOC
            // decision, giving a cheap multi-step policy over the whole run.
        } else if (actFightProbeAllOocPolicy(gc)) {
            // Every legal out-of-combat action is ranked by the all-act fight
            // rollout.  The copied continuations themselves use the normal OOC
            // policy, preventing recursive exponential search.
        } else if (oocMapRouteSearchPolicy(gc, agent)) {
            // M2 C_psi short-horizon map route search (plan 5.6.2)
        } else if (oocOnePlyMapPolicy(gc, agent)) {
            // one-ply Q map pick (M1 wave)
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            if (g_pathV) pathVPolicy(gc);                              // model-driven pathing
            else search::GameAction(chooseMapAction(gc)).execute(gc);  // heuristic pathing
        } else if (oocOnePlyEventPolicy(gc, agent)) {
            // one-ply Q event pick (Phase 5, 5.5.3; incl. Neow)
        } else if (g_eventV && gc.screenState == ScreenState::EVENT_SCREEN
                   && gc.curEvent != Event::NEOW && eventVPolicy(gc)) {
            // model-driven event choice
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;                          // take non-card rewards first,
            if (t_e2c) e2cCapturePost(gc);                               // POST boundary: non-card rewards drained, card reward pending
            if (t_e2c && t_e2c->current)
                t_e2c->current->screenTrace += "S=" + std::to_string((int)gc.screenState) + ";";
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);   // else the screen
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);  // never clears
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (actFightProbeDraftPolicy(gc)) { /* all-act, encounter-weighted rollout draft */ }
            else if (bossGatedDraftPolicy(gc)) { /* rollout draft near a hard fight */ }
            else if (oocOnePlyCardRewardPolicy(gc, agent)) { /* one-ply NN card pick (Phase 5) */ }
            else                            serverCardRewardPolicy(gc);  // best card policy (server V)
        } else if (oocShopBeamPolicy(gc)) {
            // B1 multi-step shop beam (ooc-next-wave-contracts.md §2): replaces
            // the one-ply shop gate while STS_OOC_SHOP_BEAM=1 and a net is loaded
        } else if (oocOnePlyShopPolicy(gc, agent)) {
            // one-ply Q shop pick (R6, §76)
        } else if (shopV && gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);                                            // V-knapsack shop buys
        } else if (shopV && gc.curRoom == Room::SHOP && inRemoveSelect) {
            // Shop-scoped (issue 65): CARD_SELECT/REMOVE is also used by Neow,
            // EMPTY_CAGE, and events (Purifier, Ancient Writing); only the shop
            // removal should hit the shop-V removal policy.
            removeSelectVPolicy(gc);                                    // shop removal target
        } else if (oocOnePlyRestPolicy(gc, agent)) {
            // one-ply Q campfire pick (Phase 5, 5.5.2)
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // win-rate rest policy (heal vs upgrade in P(win) units)
        } else if (oocOnePlyUpgradeSelectPolicy(gc, agent)) {
            // one-ply Q smith-target pick (Phase 5, 5.5.2)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);                                 // smith target by P(win)
        } else if (restV && gc.screenState == ScreenState::REST_ROOM && restVPolicy(gc)) {
            // handled by the value policy
        } else if (restV && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectVPolicy(gc);                                    // smith target
        } else if (oocOnePlyBossRelicPolicy(gc, agent)) {
            // one-ply Q boss-relic pick (R6, §76)
        } else if (g_bossRelicV && gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            bossRelicVPolicy(gc);                                       // boss relic by P(win)
        } else if (oocOnePlyTreasurePolicy(gc, agent)) {
            // one-ply Q treasure pick (R6, §76)
        } else if (g_neowV && gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::NEOW) {
            neowVPolicy(gc);                                           // Neow bonus by P(win)
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    auto t1 = std::chrono::steady_clock::now();
    const RunResult result { clearedStopActBoss || gc.outcome == GameOutcome::PLAYER_VICTORY,
                              gc.floorNum, gc.act, gc.curHp, gc.maxHp,
                              fightsLost,
                              std::chrono::duration<double>(t1 - t0).count(),
                              deathCombat, deathEncounter };
    if (!g_oocStrategicTracePath.empty() && !t_oocStrategicTraceRows.empty()) {
        std::lock_guard<std::mutex> lock(g_oocStrategicTraceMutex);
        std::ofstream f(g_oocStrategicTracePath, std::ios::app);
        if (f) {
            if (f.tellp() == 0)
                f << "seed,decIdx,act,floor,screen,nActions,actionBits,qValues,bestIdx,bestSecondMargin,threshold,heurIdx,takeIdx,rule,owned,collectKeys,stopAfterAct,won,finalFloor,finalHp\n";
            std::istringstream in(t_oocStrategicTraceRows);
            std::string line;
            while (std::getline(in, line)) if (!line.empty())
                f << line << ',' << (g_collectKeys ? 1 : 0) << ',' << g_stopAfterAct << ','
                  << (result.won ? 1 : 0) << ',' << result.floor << ',' << result.hpEnd << '\n';
        }
    }
    if (t_vq.active) vnetQueryLogFlush();
    if (e2cCapture) {
        // Same effective label semantics as this function's RunResult (honors an
        // explicit STS_STOP_AFTER_ACT horizon without labelling solely from
        // gc.outcome). Integrity still rejects genuinely unresolved runs and any
        // simulator-health failure, so E2c does not weaken the shared predicate.
        const bool decided = result.won || gc.outcome != GameOutcome::UNDECIDED;
        const bool validRun = trainingRunValid(decided);
        if (validRun)
            t_e2cRows = e2cRunRows(e2c, result.won, result.floor, result.hpEnd);
        if (validRun) for (int i = 0; i < 3; ++i) {
            const auto &s = e2c.roomStats[i];
            g_e2cCounts[i][0] += s.eligible;
            g_e2cCounts[i][1] += s.raw;
            g_e2cCounts[i][2] += s.post;
            g_e2cCounts[i][3] += std::count_if(e2c.fights.begin(), e2c.fights.end(),
                [i](const E2cFight &f) { return f.rawSeen && f.postSeen &&
                    (f.room == (i == 0 ? (int)Room::MONSTER : i == 1 ? (int)Room::ELITE : (int)Room::BOSS)); });
            g_e2cCounts[i][4] += std::count_if(e2c.fights.begin(), e2c.fights.end(),
                [i](const E2cFight &f) { return f.rawSeen && !f.postSeen &&
                    (f.room == (i == 0 ? (int)Room::MONSTER : i == 1 ? (int)Room::ELITE : (int)Room::BOSS)); });
            g_e2cCounts[i][5] += std::count_if(e2c.fights.begin(), e2c.fights.end(),
                [i](const E2cFight &f) { return !f.rawSeen && f.postSeen &&
                    (f.room == (i == 0 ? (int)Room::MONSTER : i == 1 ? (int)Room::ELITE : (int)Room::BOSS)); });
        }
        if (validRun) for (const auto &f : e2c.fights)
            if (f.rawSeen != f.postSeen)
                std::cerr << "e2c incomplete seed=" << e2c.seed << " fight=" << f.index
                          << " room=" << e2cRoomName(f.room) << " encounter=" << f.encounter
                          << " raw=" << f.rawSeen << " post=" << f.postSeen
                          << " relics=" << f.rewardRelics << " pending_cards=" << f.pendingCards
                          << " trace=" << f.screenTrace << '\n';
        t_e2c = nullptr;
        g_onBattleExitPersistent = nullptr;
    }
    vDisconnect();
    return result;
}

// ---------------------------------------------------------------------------
// RUN TRACE: replay ONE seed with the deployed OOC policy and print a
// human-readable line per MAP NODE (what it was, what we fought / which event,
// and the resulting state: HP, gold, deck delta, deck, relics, potions). For
// eyeballing the agent's decisions against human game knowledge. This is a
// DIAGNOSTIC trace, not a mirror of runFullRunOOC: it logs but does not use
// some event/treasure scores and omits some fallthrough policy layers.
// ---------------------------------------------------------------------------
static std::string tr_deck(const GameContext &gc) {
    std::map<std::string,int> m;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ++m[n]; }
    std::string s;
    for (auto &kv : m) { s += kv.first; if (kv.second > 1) s += " x" + std::to_string(kv.second); s += ", "; }
    return s;
}
static std::multiset<std::string> tr_deckMs(const GameContext &gc) {
    std::multiset<std::string> ms;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ms.insert(n); }
    return ms;
}
static std::string tr_relics(const GameContext &gc) {
    std::string s;
    for (const auto &ri : gc.relics.relics) { s += sts::relicNames[(int)ri.id]; s += ", "; }
    return s.empty() ? "-" : s;
}
static std::string tr_potions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        s += sts::getPotionName(gc.potions[i]); s += ", ";
    }
    return s.empty() ? "-" : s;
}
static std::string tr_event(Event e) {
    // enum-order names (matches include/constants/Events.h)
    static const char *const kEventNames[] = {
        "INVALID","MONSTER","REST","SHOP","TREASURE","NEOW","Ominous Forge","Pleading Vagrant",
        "Ancient Writing","Old Beggar","Big Fish","Bonfire Spirits","Colosseum","Cursed Tome",
        "Dead Adventurer","Designer in-Spire","Augmenter","Duplicator","Face Trader","Falling",
        "Forgotten Altar","The Divine Fountain","Ghosts","Golden Idol","Golden Shrine","Wing Statue",
        "Knowing Skull","Lab","The Ssssserpent","Living Wall","Masked Bandits","Match and Keep",
        "Mindbloom","Hypnotizing Mushrooms","Mysterious Sphere","The Nest","Nloth","Note For Yourself",
        "Purifier","Scrap Ooze","Secret Portal","Sensory Stone","Shining Light","The Cleric","The Joust",
        "The Library","The Mausoleum","The Moai Head","The Woman in Blue","Tomb of Lord Red Mask",
        "Transmogrifier","Upgrade Shrine","Vampires","We Meet Again","Wheel of Change","Winding Halls",
        "World of Goop" };
    const int i = (int)e;
    return (i >= 0 && i < (int)(sizeof(kEventNames)/sizeof(*kEventNames))) ? kEventNames[i]
                                                                           : "Event#" + std::to_string(i);
}
static std::string tr_deckDelta(const std::multiset<std::string> &prev, const std::multiset<std::string> &cur) {
    std::string s;
    for (const auto &n : cur) if (cur.count(n) > prev.count(n) && s.find("+" + n + " ") == std::string::npos) {
        int d = (int)cur.count(n) - (int)prev.count(n);
        s += "+" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    for (const auto &n : prev) if (prev.count(n) > cur.count(n) && s.find("-" + n + " ") == std::string::npos) {
        int d = (int)prev.count(n) - (int)cur.count(n);
        s += "-" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    return s;
}

// Log each pending card reward's OPTIONS + the model's marginal-V (final-floor units,
// via the server "M" op) so drafts can be graded, not just the pick. skip bar = g_cardSkipThresh.
// When the OOC action NN is active (STS_OOC_ACTION_NN=1), also query its OA endpoint and
// show the NN's utility score for each card.
static void tr_logDraft(GameContext &gc) {
    // The "M" marginals op is server-only. Skip the draft log cleanly when no
    // server is reachable (same vConnect()<0 fail-fast pattern as vTransact),
    // instead of letting vRequestLine retry ~50x per card reward.
    if (vConnect() < 0) return;
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = 0; rIdx < r.cardRewardCount; ++rIdx) {
        auto &cr = r.cardRewards[rIdx];
        if (cr.size() == 0) continue;

        // V_rich marginals (server M op)
        std::string req = "M;";
        for (int i = 0; i < cr.size(); ++i) { if (i) req += ','; req += std::to_string((int)cr[i].getId()); }
        req += ';'; req += vFeatCsv(gc);
        std::string resp = vSendRecv(req);
        std::vector<double> marg; { std::istringstream is(resp); double v; while (is >> v) marg.push_back(v); }

        // NN scores for each card option + skip
        std::vector<double> nnScores;
        if (g_oocCheckpointNet.ok) {
            const std::vector<float> state = richFeatureVec(gc);
            using RT = search::GameAction::RewardsActionType;
            for (int i = 0; i < cr.size(); ++i) {
                std::uint32_t abits = search::GameAction(RT::CARD, rIdx, i).bits;
                nnScores.push_back(g_oocCheckpointNet.predict(state.data(), abits, (int)gc.screenState, gc.act));
            }
            std::uint32_t sbits = search::GameAction(RT::SKIP).bits;
            nnScores.push_back(g_oocCheckpointNet.predict(state.data(), sbits, (int)gc.screenState, gc.act));
        }

        // One-ply strategic scores for each card option + the CARD(rIdx,5) skip:
        // Q(s,a) directly (Tier-B, §72), or V(s') of the successor when
        // STS_OOC_STRATEGIC_Q=0 (V2 behaviour).
        std::vector<double> oneplyScores;
        if (g_oocStrategicNet.ok) {
            using RT = search::GameAction::RewardsActionType;
            const std::vector<float> state = richFeatureVec(gc);
            auto score = [&](const search::GameAction &a) {
                if (g_oocStrategicQ) {
                    int actionType, c1, c2, c3, cand1, cand2, cand3;
                    strategicCands(gc, a, actionType, c1, c2, c3, cand1, cand2, cand3);
                    const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
                    return g_oocStrategicNet.predictActionValue(state.data(), a.bits,
                                                                cats, actionType, (int)gc.screenState);
                }
                GameContext probe = gc;
                a.execute(probe);
                return g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                      (int)probe.screenState);
            };
            for (int i = 0; i < cr.size(); ++i)
                oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, i)));
            oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, 5)));
        }

        std::string line = "         draft options [skip if <" + std::to_string(g_cardSkipThresh) + "]: ";
        int best = -1; double bestv = -1e18;
        for (int i = 0; i < cr.size(); ++i) {
            double m = i < (int)marg.size() ? marg[i] : 0.0;
            if (m > bestv) { bestv = m; best = i; }
            std::string nm = cr[i].getName(); if (cr[i].isUpgraded()) nm += "+";
            char buf[64];
            if (i < (int)nnScores.size()) {
                std::snprintf(buf, sizeof(buf), "%s(V:%+.2f NN:%.3f)", nm.c_str(), m, nnScores[i]);
                line += buf;
                if (i < (int)oneplyScores.size())
                    line += " 1ply:" + std::to_string(oneplyScores[i]);
                line += "  ";
            } else {
                std::snprintf(buf, sizeof(buf), "%s(%+.2f)  ", nm.c_str(), m);
                line += buf;
            }
        }
        line += "-> V_rich picks ";
        line += (bestv < g_cardSkipThresh) ? "SKIP" : (std::string)(cr[best].getName());
        if (!nnScores.empty()) {
            int nnBest = 0;
            for (int i = 1; i < (int)nnScores.size(); ++i)
                if (nnScores[i] > nnScores[nnBest]) nnBest = i;
            line += "  NN: skip=" + std::to_string(nnScores.back()) + " picks ";
            line += (nnBest < cr.size()) ? (std::string)(cr[nnBest].getName()) : "SKIP";
            if (nnBest > 0 && nnBest != best) line += " [DISAGREE]";
        }
        std::printf("%s\n", line.c_str());
    }
}

// Show NN scores for all legal OOC actions with action descriptions.
static void tr_logOocActions(const char *label, GameContext &gc) {
    if (!g_oocCheckpointNet.ok) return;
    const std::vector<float> state = richFeatureVec(gc);
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return;
    double best = -1e100; int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        double s = g_oocCheckpointNet.predict(state.data(), actions[i].bits, (int)gc.screenState, gc.act);
        std::string desc;
        if (gc.screenState == ScreenState::REST_ROOM) {
            int idx = actions[i].getIdx1();
            if (idx == 0) desc = "HEAL";
            else if (idx == 1) {
                int smithIdx = actions[i].getIdx2();
                if (smithIdx >= 0 && smithIdx < (int)gc.deck.cards.size())
                    desc = std::string("smith:") + gc.deck.cards[smithIdx].getName();
                else desc = "smith";
            } else if (idx == 2) desc = "DIG";
            else if (idx == 3) desc = "LIFT";
            else if (idx == 4) desc = "TOKE";
            else desc = "rest#" + std::to_string(idx);
        } else {
            desc = "#" + std::to_string(i);
        }
        std::printf("         [NN %s] %s = %.3f\n", label, desc.c_str(), s);
        if (s > best) { best = s; bestIdx = i; }
    }
    std::printf("         [NN %s] -> picks #%d (%.3f)\n", label, bestIdx, best);
}

// Refight the CURRENT battle K times from a copy of the pre-fight state, reseeding the
// battle RNGs each time so draw order + enemy moves vary -> separates a bad fight model
// from an unlucky single sample. Prints end-HP distribution, death rate, potions used.
static void tr_refight(const GameContext &gc, int sims, int K) {
    std::vector<int> hp; int deaths = 0, potUsed = 0;
    const int potBefore = gc.potionCount;
    for (int k = 0; k < K; ++k) {
        GameContext g2 = gc;
        BattleContext bc; bc.init(g2);
        bc.shuffleRng      = sts::Random(gc.seed * 2654435761u + k * 40503u + 1);
        bc.aiRng           = sts::Random(gc.seed * 2246822519u + k * 668265263u + 7);
        bc.cardRandomRng   = sts::Random(gc.seed * 3266489917u + k * 374761393u + 13);
        search::ScumSearchAgent2 ag; ag.simulationCountBase = fightSims(gc, sims);
        ag.rng = std::default_random_engine(gc.seed + 999u + k);
        ag.playoutBattle(bc);
        bc.exitBattle(g2);
        const bool died = g2.curHp <= 0 || g2.outcome == GameOutcome::PLAYER_LOSS;
        if (died) ++deaths; hp.push_back(std::max(0, g2.curHp));
        potUsed += potBefore - g2.potionCount;
    }
    std::sort(hp.begin(), hp.end());
    double mean = 0; for (int h : hp) mean += h; mean /= std::max(1, (int)hp.size());
    std::printf("         >> REFIGHT x%d: deaths %d/%d  endHP min %d / med %d / mean %.1f / max %d"
                "  avg potions used %.2f (had %d)\n",
                K, deaths, K, hp.front(), hp[hp.size()/2], mean, hp.back(),
                (double)potUsed / std::max(1, K), potBefore);
}

static void runTraceRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;

    std::printf("=== RUN TRACE seed %llu  asc %d  sims %d%s ===\n",
                (unsigned long long)seed, asc, sims, search::g_fairPlay ? "  [fair-play]" : "");
    std::printf("!!! DIAGNOSTIC TRACE: does NOT exactly reproduce runFullRunOOC policy !!!\n");

    const int refightFloor = std::getenv("STS_REFIGHT_FLOOR") ? std::atoi(std::getenv("STS_REFIGHT_FLOOR")) : -1;
    const int refightN     = std::getenv("STS_REFIGHT_N")     ? std::atoi(std::getenv("STS_REFIGHT_N"))     : 20;
    const int combatLogFloor = std::getenv("STS_COMBAT_LOG")  ? std::atoi(std::getenv("STS_COMBAT_LOG"))    : -1;
    int clLastTurn = -1;
    // Per-decision combat logger (via the g_onCombatDecision hook): one line per in-fight
    // decision -> turn, energy, player HP/block/str/dex, each alive monster's HP/block/intent, hand.
    auto combatLog = [&clLastTurn](const BattleContext &bc) {
        if (bc.turn != clLastTurn) { std::printf("   --- Turn %d ---\n", bc.turn); clLastTurn = bc.turn; }
        auto ps = [&](PlayerStatus s){ auto it = bc.player.statusMap.find(s); return it != bc.player.statusMap.end() ? (int)it->second : 0; };
        std::string mon;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const Monster &m = bc.monsters.arr[i];
            if (m.curHp <= 0 || !m.isTargetable()) continue;
            DamageInfo di = m.getMoveBaseDamage(bc);
            std::string intent = monsterMoveStrings[(int)m.moveHistory[0]];
            if (di.damage > 0) { intent += "(" + std::to_string(di.damage);
                                 if (di.attackCount > 1) intent += "x" + std::to_string(di.attackCount);
                                 intent += ")"; }
            char buf[160];
            std::snprintf(buf, sizeof(buf), "%s HP%d+%d[%s] ", m.getName(), m.curHp, m.block, intent.c_str());
            mon += buf;
        }
        std::string hand;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            std::string n = bc.cards.hand[i].getName(); if (bc.cards.hand[i].isUpgraded()) n += "+";
            hand += n; hand += " ";
        }
        std::printf("   [E%d] you HP%d+%dblk Str%d Dex%d Weak%d | %s| hand: %s\n",
                    bc.player.energy, bc.player.curHp, bc.player.block,
                    ps(PlayerStatus::STRENGTH), ps(PlayerStatus::DEXTERITY), ps(PlayerStatus::WEAK),
                    mon.c_str(), hand.c_str());
    };
    bool nodeActive = false; std::string label, desc; int preHp = gc.curHp;
    std::multiset<std::string> prevDeck = tr_deckMs(gc);

    auto flush = [&]() {
        if (!nodeActive) return;
        auto curDeck = tr_deckMs(gc);
        std::string delta = tr_deckDelta(prevDeck, curDeck);
        std::printf("[F%-2d A%d] %-9s %-22s  HP %d/%d (%+d)  gold %d\n",
                    gc.floorNum, gc.act, label.c_str(), desc.c_str(),
                    gc.curHp, gc.maxHp, gc.curHp - preHp, gc.gold);
        if (!delta.empty())          std::printf("         change: %s\n", delta.c_str());
        std::printf("         deck(%d): %s\n", (int)gc.deck.size(), tr_deck(gc).c_str());
        std::printf("         relics: %s\n", tr_relics(gc).c_str());
        std::printf("         potions: %s\n", tr_potions(gc).c_str());
        prevDeck = curDeck; preHp = gc.curHp; nodeActive = false; label.clear(); desc.clear();
    };
    auto roomName = [](Room r) -> const char * {
        switch (r) { case Room::MONSTER: return "MONSTER"; case Room::ELITE: return "ELITE";
            case Room::BOSS: case Room::BOSS_TREASURE: return "BOSS"; case Room::REST: return "REST";
            case Room::SHOP: return "SHOP"; case Room::TREASURE: return "TREASURE";
            case Room::EVENT: return "EVENT"; default: return "?"; }
    };

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            agent.simulationCountBase = fightSims(gc, sims);
            search::g_potionKeepValue = potionKeepValue(gc);
            BattleContext bc; bc.init(gc);
            flush();  // a battle always begins a fresh node (fixes forced rest/event -> boss merge)
            nodeActive = true; label = roomName(gc.curRoom);
            desc = sts::monsterEncounterStrings[(int)bc.encounter];
            if (gc.floorNum == refightFloor) {
                std::printf("[F%-2d A%d] %-9s %-22s  (pre-fight HP %d/%d)\n",
                            gc.floorNum, gc.act, label.c_str(), desc.c_str(), gc.curHp, gc.maxHp);
                tr_refight(gc, sims, refightN);
            }
            const bool doLog = gc.floorNum == combatLogFloor;
            if (doLog) {
                std::printf("[F%d A%d] === COMBAT LOG: %s (HP %d/%d) ===\n",
                            gc.floorNum, gc.act, desc.c_str(), gc.curHp, gc.maxHp);
                clLastTurn = -1; search::g_onCombatDecision = combatLog;
            }
            agent.playoutBattle(bc);
            if (doLog) { search::g_onCombatDecision = nullptr;
                         std::printf("   === end combat: you HP%d, %s ===\n", bc.player.curHp,
                                     bc.player.curHp > 0 ? "WON" : "DIED"); }
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            flush();
            tr_logOocActions("map", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocMapRouteSearchPolicy(gc, agent))
                    if (!oocOnePlyMapPolicy(gc, agent))
                        search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
            if (!nodeActive) { flush(); nodeActive = true; label = "EVENT"; desc = tr_event(gc.curEvent); }
            tr_logOocActions("event", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "REST"; }
            tr_logOocActions("rest", gc);
            if (!oocActionNNPolicy(gc)) {
                if (!oocOnePlyRestPolicy(gc, agent)) {
                    if (g_restWin && restWinPolicy(gc)) {}
                    else agent.stepOutOfCombatPolicy(gc);
                }
            }
        } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "TREASURE"; }
            tr_logOocActions("treasure", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "SHOP"; }
            tr_logOocActions("shop", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc))
                    if (!oocOnePlyShopPolicy(gc, agent)) shopVPolicy(gc);
        } else if (inRemoveSelect) {
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc)) removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else { tr_logDraft(gc); if (!oocActionNNPolicy(gc)) { if (!oocOnePlyCardRewardPolicy(gc, agent)) serverCardRewardPolicy(gc); } }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            tr_logOocActions("upgrade", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) upgradeSelectWinPolicy(gc);
        } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    flush();
    std::printf("=== %s  final floor %d act %d  HP %d/%d ===\n",
                gc.outcome == GameOutcome::PLAYER_VICTORY ? "VICTORY" : "DEATH",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp);
}

// Single-arm readout of the CURRENT BEST out-of-combat stack: native floor-V
// card picks (skip@g_cardSkipThresh, default -0.5) + heuristic path + shop-V,
// with the default win-rate rest layer (g_restWin, heal-vs-upgrade in P(win)
// units) and optional legacy rest-V via STS_REST_V=1. Use this as the baseline
// arm for new experiments. Serverless under default native OOC.
static std::string benchTimestampUtc() {
    const std::time_t now = std::time(nullptr);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &now);
#else
    gmtime_r(&now, &tm);
#endif
    char buf[32] = {};
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

static void bestBench(int sims, int nSeeds, int asc, std::uint64_t seedOffset = 0,
                      const std::string &resultsFile = "", const std::string &objective = "bestbench") {
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    std::cout << "BEST stack config: skip@" << g_cardSkipThresh
              << "  rest=" << (g_restWin ? "win-rate" : "default")
              << (restV ? "+legacy-rest-V" : "")
              << "  shop-V=ON  path=" << (g_pathV ? "model-driven" : "heuristic")
              << "  shop-beam=" << (g_oocShopBeam ? "ON" : "off")
              << "  native-OOC=" << (g_nativeOoc ? "ON" : "OFF")
              << "  keys=" << (g_collectKeys ? "collect" : "skip")
              << "  searcher=" << (search::g_useSearcher3 ? "Searcher3" : "Searcher2")
              << (search::g_useSearcher3
                  ? "  S3-abl[b,p,c,l,crn]=" + std::to_string(search::g_s3Belief)
                    + std::to_string(search::g_s3Prune) + std::to_string(search::g_s3Chain)
                    + std::to_string(search::g_s3Live) + std::to_string(search::g_s3Crn)
                    + "  S3-particles=" + std::to_string(search::g_s3Particles)
                    + "  S3-rollK=" + std::to_string(search::g_s3RolloutK)
                    + "  S3-turnStop=" + std::to_string(search::g_s3RolloutTurnStop)
                    + "  S3-turnBeam=" + (search::g_s3TurnRollout ? "ON" : "off")
                    + "  S3-semCard=" + (search::g_s3SemanticCardEdges ? "ON" : "off")
                  : std::string())
              << (search::g_fairPlay ? "  fair-play" : "")
              << "  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  asc " << asc << "  sims " << sims << "  threads " << numThreads() << "\n";
    std::cout << "BEST models: floor=" << (g_floorNet.ok ? g_floorNet.path : "MISSING")
              << "  win=" << (g_winNet.ok ? g_winNet.path : "not loaded")
              << "  combatVNet=" << (search::g_useVNet ? "ON" : "off")
              << (search::g_combatVNet.hasEncounterModels
                  ? "+per-encounter(" + std::to_string(search::g_combatVNet.encounterModels.size()) + ")"
                  : "")
              << "  policyNet=" << (search::g_usePolicyNet ? "ON" : "off")
              << "  PVNet=" << (search::g_usePVNet ? "ON" : "off")
              << "  distVNet=" << (search::g_useDistVNet ? "ON" : "off") << "\n";
    // Optional per-seed output powers the adaptive self-play gate. Rows are
    // flushed as runs finish, so the dashboard gets live progress and a killed
    // benchmark leaves valid results. The caller owns truncation; batches append.
    std::ofstream results;
    if (!resultsFile.empty()) {
        results.open(resultsFile, std::ios::app);
        if (results.tellp() == 0) {
            results << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n";
            results.flush();
        }
        sts::BenchConfigSidecar meta;
        meta.objective = objective;
        meta.argv = g_mainArgv;
        meta.timestamp = benchTimestampUtc();
        meta.seedLo = seedOffset;
        meta.seedHi = seedOffset + (std::uint64_t)(nSeeds > 0 ? nSeeds - 1 : 0);
        meta.nSeeds = nSeeds; meta.asc = asc; meta.sims = sims; meta.threads = numThreads();
        meta.cardSkipThresh = g_cardSkipThresh;
        meta.restPolicy = g_restWin ? "win-rate" : "default";
        meta.restV = restV; meta.shopV = true; meta.nativeOoc = g_nativeOoc;
        meta.pathMode = g_pathV ? "model-driven" : "heuristic";
        meta.shopBeam = g_oocShopBeam; meta.collectKeys = g_collectKeys;
        meta.searcher3 = search::g_useSearcher3; meta.fairPlay = search::g_fairPlay;
        meta.s3Belief = search::g_s3Belief; meta.s3Prune = search::g_s3Prune;
        meta.s3Chain = search::g_s3Chain; meta.s3Live = search::g_s3Live; meta.s3Crn = search::g_s3Crn;
        meta.s3Particles = search::g_s3Particles; meta.s3RolloutK = search::g_s3RolloutK;
        meta.s3RolloutTurnStop = search::g_s3RolloutTurnStop != 0;
        meta.s3TurnRollout = search::g_s3TurnRollout;
        meta.s3SemanticCardEdges = search::g_s3SemanticCardEdges;
        meta.silverSearchEnabled = search::silverLiveBackendInstalled();
        meta.stsSilverSearchEffective = meta.silverSearchEnabled;
        meta.effectiveCombatBackend = meta.silverSearchEnabled ? "silver" : "native_searcher";
        meta.silverReuseCapMode = meta.silverSearchEnabled ? search::silverLiveReuseCapMode() : "";
        meta.silverReuseCap = meta.silverSearchEnabled ? search::silverLiveReuseCap() : 0;
        meta.silverUpstreamSha = meta.silverSearchEnabled
            ? "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff" : "";
        meta.executableGitSha = trainingGitValue("git rev-parse HEAD");
        meta.silverScalingDiagnosticFile = meta.silverSearchEnabled
            ? search::silverLiveScalingDiagnosticFile() : "";
        meta.silverStickyQualityFile = meta.silverSearchEnabled
            ? search::silverLiveStickyQualityFile() : "";
        meta.silverAdaptiveEnabled = meta.silverSearchEnabled
            && search::silverLiveAdaptiveEnabled();
        meta.silverAdaptiveTopShare = meta.silverSearchEnabled
            ? search::silverLiveAdaptiveTopTwoVisitGapThreshold() : 0.0;
        meta.silverExactRootBudgets = meta.silverSearchEnabled
            && search::silverLiveExactRootBudgets();
        meta.floorModel = g_floorNet.ok ? g_floorNet.path : "MISSING";
        meta.winModel = g_winNet.ok ? g_winNet.path : "not loaded";
        meta.combatVNet = search::g_useVNet ? "ON" : "off";
        meta.policyNet = search::g_usePolicyNet ? "ON" : "off";
        meta.pvNet = search::g_usePVNet ? "ON" : "off";
        meta.distVNet = search::g_useDistVNet ? "ON" : "off";
        std::ofstream sidecar(resultsFile + ".meta.json", std::ios::app);
        if (!sidecar) std::cerr << "[bestbench] warning: cannot open " << resultsFile << ".meta.json\n";
        else sidecar << sts::benchConfigSidecarLine(meta) << '\n';
    }
    int wins = 0; long long floor = 0, hp = 0; double sec = 0;
    BenchProgress prog(nSeeds, "BEST");
    auto wall0 = std::chrono::steady_clock::now();
    // Do not create a one-iteration outer OpenMP team when the all-OOC oracle
    // is asked to parallelize its branches; that would otherwise serialize the
    // nested region. Multi-seed benches keep the proven outer parallelism.
    if (nSeeds == 1 && g_actFightProbeParallelBranches) {
        const std::uint64_t seed = seedOffset;
        RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
        wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
        if (results.is_open()) {
            results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                    << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                    << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
            results.flush();
        }
        prog.tick(r.won, r.floor, r.hpEnd);
    } else {
        #pragma omp parallel for reduction(+:wins,floor,hp,sec) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            const std::uint64_t seed = seedOffset + (std::uint64_t)s;
            RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec;
            #pragma omp critical(bestbench_results)
            if (results.is_open()) {
                results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                        << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                        << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
                results.flush();
            }
            prog.tick(r.won, r.floor, r.hpEnd);
        }
    }
    prog.done();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    std::printf("BEST                    win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                100.0 * wins / nSeeds, (double)floor / nSeeds, (double)hp / nSeeds, sec / nSeeds, wall);
}

// ---------------------------------------------------------------------------
// DATA GENERATION for an offline value function V(state) ~= P(win). At each
// card-reward decision we log a feature vector of the current run state; the
// label is the eventual outcome of that run (Monte-Carlo return). Card picks
// use eps-greedy exploration so the logged decks are diverse.
// ---------------------------------------------------------------------------
// scalar feature names only; datagen appends d0..d(kNumCardIds-1) then won,finalFloor
static const char *kFeatureHeader =
    "ascension,act,floor,curHp,maxHp,gold,deckSize,nAttack,nSkill,nPower,nCurse,"
    "nStatus,nUpgraded,nStarter,nCommon,nUncommon,nRare,obtainSum,obtainAvg,nRelics";

// deck as per-card-id counts d0..d(kNumCardIds-1) — makes value models deck-aware
// (able to express card synergies), shared by datagen and causalgen.
static const int kNumCardIds = 372;

static std::string deckCountsCsv(const GameContext &gc) {
    std::array<int, kNumCardIds> cnt{};
    for (const auto &c : gc.deck.cards) {
        int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) ++cnt[id];
    }
    std::ostringstream o;
    for (int i = 0; i < kNumCardIds; ++i) { if (i) o << ','; o << cnt[i]; }
    return o.str();
}

static std::string featureRow(const GameContext &gc) {
    int nAtk=0,nSkill=0,nPow=0,nCurse=0,nStatus=0,nUpg=0,nStarter=0,nCommon=0,nUncommon=0,nRare=0;
    long obtainSum = 0;
    for (const auto &c : gc.deck.cards) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::SKILL:  ++nSkill; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::CURSE:  ++nCurse; break;
            case CardType::STATUS: ++nStatus; break;
            default: break;
        }
        if (c.isUpgraded()) ++nUpg;
        if (c.isStarterStrikeOrDefend()) ++nStarter;
        switch (c.getRarity()) {
            case CardRarity::COMMON:   ++nCommon; break;
            case CardRarity::UNCOMMON: ++nUncommon; break;
            case CardRarity::RARE:     ++nRare; break;
            default: break;
        }
        obtainSum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    const int deckSize = gc.deck.size();
    const double obtainAvg = deckSize ? (double)obtainSum / deckSize : 0.0;
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ','
      << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ',' << deckSize << ','
      << nAtk << ',' << nSkill << ',' << nPow << ',' << nCurse << ',' << nStatus << ','
      << nUpg << ',' << nStarter << ',' << nCommon << ',' << nUncommon << ',' << nRare << ','
      << obtainSum << ',' << obtainAvg << ',' << (int)gc.relics.relics.size();
    return o.str();
}

// ---------------------------------------------------------------------------
// RICH datagen v2: a comprehensive per-decision run-state snapshot for training
// value functions that are relic-aware, upgrade-aware, potion-aware, future-fight
// -aware, and path-aware. One row per card-reward decision; label = run outcome.
// Blocks: core, keys, potions-meta, future-fights/act, path-history, bottled
// cards, deck totals d{id}, deck upgrades u{id}, relics r{id} (0=absent /
// 1+counter), potions pot{id} (multi-hot). Wide but sparse. Append-capable.
// ---------------------------------------------------------------------------
static const int kNumRelics  = 181;   // RelicId enum cardinality
static const int kNumPotions = 48;    // Potion enum cardinality

// Accumulates room types visited so far this run (for path evaluation). Updated
// each loop iteration; counts a node once, when the map position first changes.
static std::string richHeader() {
    std::ostringstream h;
    h << "seed,ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor,"
         "blueKey,greenKey,redKey,potionCount,potionCapacity,"
         "bossId,nextEliteId,nextFight0,nextFight1,nextFight2,remElites,remFights,monOffset,eliteOffset,"
         "pvShop,pvRest,pvEvent,pvElite,pvMonster,pvTreasure,"
         "bottledAtkId,bottledSkillId,bottledPowId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    for (int i = 0; i < kNumCardIds; ++i) h << ",u" << i;
    for (int i = 0; i < kNumRelics;  ++i) h << ",r" << i;
    for (int i = 0; i < kNumPotions; ++i) h << ",pot" << i;
    h << ",fmDElite,fmDRest,fmDShop,fmDBoss,fmCElite,fmCRest,fmCShop,fmCEvent,fmCMonster,fmCTreasure";
    h << ",curMapX,curMapY";
    h << ",won,finalFloor,endHp";
    return h.str();
}

// State portion of a row (no seed prefix, no labels — those are added at run end).
static std::string richRow(const GameContext &gc, const PathHistory &path) {
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case CardType::ATTACK: botAtk = id; break;
                case CardType::SKILL:  botSkill = id; break;
                case CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);  // presence + counter
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const int nextElite = gc.eliteMonsterListOffset < gc.eliteMonsterList.size()
                        ? (int)gc.eliteMonsterList[gc.eliteMonsterListOffset] : 0;
    auto nf = [&](int k) -> int {
        const int idx = gc.monsterListOffset + k;
        return idx < gc.monsterList.size() ? (int)gc.monsterList[idx] : 0;
    };
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
      << gc.gold << ',' << gc.deck.size() << ',' << gc.potionChance << ',' << gc.cardRarityFactor << ','
      << (gc.blueKey ? 1 : 0) << ',' << (gc.greenKey ? 1 : 0) << ',' << (gc.redKey ? 1 : 0) << ','
      << gc.potionCount << ',' << gc.potionCapacity << ','
      << (int)gc.boss << ',' << nextElite << ',' << nf(0) << ',' << nf(1) << ',' << nf(2) << ','
      << (gc.eliteMonsterList.size() - gc.eliteMonsterListOffset) << ','
      << (gc.monsterList.size() - gc.monsterListOffset) << ','
      << gc.monsterListOffset << ',' << gc.eliteMonsterListOffset << ','
      << path.roomVisits[(int)Room::SHOP]  << ',' << path.roomVisits[(int)Room::REST]     << ','
      << path.roomVisits[(int)Room::EVENT] << ',' << path.roomVisits[(int)Room::ELITE]    << ','
      << path.roomVisits[(int)Room::MONSTER] << ',' << path.roomVisits[(int)Room::TREASURE] << ','
      << botAtk << ',' << botSkill << ',' << botPow;
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << d[i];
    for (int i = 0; i < kNumCardIds; ++i) o << ',' << u[i];
    for (int i = 0; i < kNumRelics;  ++i) o << ',' << r[i];
    for (int i = 0; i < kNumPotions; ++i) o << ',' << pot[i];
    const FwdMap fm = forwardMapFeatures(gc);   // forward-map (appended last -> old models unaffected)
    o << ',' << fm.dElite << ',' << fm.dRest << ',' << fm.dShop << ',' << fm.dBoss
      << ',' << fm.cElite << ',' << fm.cRest << ',' << fm.cShop << ',' << fm.cEvent
      << ',' << fm.cMonster << ',' << fm.cTreasure;
    // Map position. Combined with seed+act (also stored) the FULL map graph is deterministically
    // reconstructable (see the `dumpmap` mode) -> the eventual GNN gets the whole node+edge structure
    // with NO per-row bloat. Trees ignore these; harmless.
    o << ',' << gc.curMapNodeX << ',' << gc.curMapNodeY;
    return o.str();
}

// Full rich feature vector for a V query — identical schema/order to richRow() so
// training (vrich.csv) and serving match exactly. Uses the current run's path
// history when set (t_curPath), else an empty one (pv* = 0).
static std::string vFeatCsv(const GameContext &gc) {
    static thread_local PathHistory emptyPath;
    return richRow(gc, t_curPath ? *t_curPath : emptyPath);
}

// ---------------------------------------------------------------------------
// V4 TOKEN STATE (ooc-strategic-v4.md §2): 42 globals (36 richRow scalars
// minus 8 hidden-information leaks + 6 derived thresholds) plus canonical
// deck/relic/potion tokens, built from the same GameContext loops as richRow().
// Built once per decision, reused across the legal actions of that decision.
// ---------------------------------------------------------------------------
static constexpr int TOK_NGLOB = 42;
struct TokState {
    float glob[TOK_NGLOB];
    int nDk, nRl, nPt;
    int dk[96][3];
    int rl[64][2];
    int pt[8][2];
};

// Parity hook (STS_OOC_STRATEGIC_TOK_CHECK=1): once per run, on the first
// gated decision, when the token net is loaded. Armed at run start.
// The 8 hidden-information leaks (nextEliteId, nextFight0/1/2,
// remElites, remFights, monOffset, eliteOffset) are excluded; bossId is kept.
static constexpr int TOK_NRAW = 36;
static void tokCheckGlobParity(const GameContext &gc, const TokState &ts) {
    static const char *const names[TOK_NRAW] = {
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize", "potionChance",
        "cardRarityFactor", "blueKey", "greenKey", "redKey", "potionCount", "potionCapacity",
        "bossId",
        "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure",
        "bottledAtkId", "bottledSkillId", "bottledPowId",
        "fmDElite", "fmDRest", "fmDShop", "fmDBoss", "fmCElite", "fmCRest", "fmCShop", "fmCEvent",
        "fmCMonster", "fmCTreasure", "curMapX", "curMapY"
    };
    const std::string csv = vFeatCsv(gc);
    std::vector<float> rich; std::string cur;
    for (char c : csv) { if (c == ',') { rich.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); } else cur += c; }
    if (!cur.empty()) rich.push_back(std::strtof(cur.c_str(), nullptr));
    const auto &idx = richIdxMap();
    for (int i = 0; i < TOK_NRAW; ++i) {
        const auto it = idx.find(names[i]);
        if (it == idx.end() || it->second >= (int)rich.size()) continue;
        const float rv = rich[it->second];
        if (rv != ts.glob[i])
            std::printf("[ooc-tok-check] glob[%d] %s: tok=%g rich=%g\n", i, names[i], ts.glob[i], rv);
    }
}

static TokState buildTokState(const GameContext &gc, const PathHistory &path) {
    TokState ts;
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case CardType::ATTACK: botAtk = id; break;
                case CardType::SKILL:  botSkill = id; break;
                case CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const FwdMap fm = forwardMapFeatures(gc);
    // 36 raw scalars: same as richRow() minus the 8 hidden-information leaks
    // (nextEliteId, nextFight0/1/2, remElites, remFights, monOffset,
    //  eliteOffset at original indices 15-22); bossId is kept (visible on act map).
    const float glob[TOK_NRAW] = {
        (float)gc.ascension, (float)gc.act, (float)gc.floorNum, (float)gc.curHp,
        (float)gc.maxHp, (float)gc.gold, (float)gc.deck.size(),
        (float)gc.potionChance, (float)gc.cardRarityFactor,
        (float)(gc.blueKey ? 1 : 0), (float)(gc.greenKey ? 1 : 0), (float)(gc.redKey ? 1 : 0),
        (float)gc.potionCount, (float)gc.potionCapacity,
        (float)gc.boss,
        (float)path.roomVisits[(int)Room::SHOP], (float)path.roomVisits[(int)Room::REST],
        (float)path.roomVisits[(int)Room::EVENT], (float)path.roomVisits[(int)Room::ELITE],
        (float)path.roomVisits[(int)Room::MONSTER], (float)path.roomVisits[(int)Room::TREASURE],
        (float)botAtk, (float)botSkill, (float)botPow,
        (float)fm.dElite, (float)fm.dRest, (float)fm.dShop, (float)fm.dBoss,
        (float)fm.cElite, (float)fm.cRest, (float)fm.cShop, (float)fm.cEvent,
        (float)fm.cMonster, (float)fm.cTreasure,
        (float)gc.curMapNodeX, (float)gc.curMapNodeY
    };
    for (int i = 0; i < TOK_NRAW; ++i) ts.glob[i] = glob[i];
    // derived threshold features (ooc-strategic-v4.md §2.1)
    // canTakeEliteKey now uses fmCElite (reachable elites on the visible map)
    // instead of the removed remElites (exact hidden-queue count).
    ts.glob[TOK_NRAW + 0] = gc.maxHp > 0 ? (float)gc.curHp / gc.maxHp : 0.0f;
    ts.glob[TOK_NRAW + 1] = (float)(gc.maxHp - gc.curHp);
    ts.glob[TOK_NRAW + 2] = gc.potionCount < gc.potionCapacity ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 3] = gc.gold >= 75 ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 4] = fm.cElite > 0
                  && !(gc.blueKey && gc.greenKey && gc.redKey) ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 5] = fm.dBoss <= 3 ? 1.0f : 0.0f;

    // deck tokens: canonical ascending cardId, upgraded=1 token before the
    // unupgraded one, capped at MAXDK=96
    ts.nDk = 0;
    for (int id = 0; id < kNumCardIds && ts.nDk < 96; ++id) {
        if (u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 1; ts.dk[ts.nDk][2] = u[id]; ++ts.nDk;
        }
        if (ts.nDk < 96 && d[id] - u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 0; ts.dk[ts.nDk][2] = d[id] - u[id]; ++ts.nDk;
        }
    }
    // relic tokens: canonical ascending relicId (counter = 1 + relic data)
    ts.nRl = 0;
    for (int id = 0; id < kNumRelics && ts.nRl < 64; ++id)
        if (r[id] > 0) { ts.rl[ts.nRl][0] = id; ts.rl[ts.nRl][1] = r[id]; ++ts.nRl; }
    // potion tokens: canonical ascending potionId
    ts.nPt = 0;
    for (int id = 0; id < kNumPotions && ts.nPt < 8; ++id)
        if (pot[id] > 0) { ts.pt[ts.nPt][0] = id; ts.pt[ts.nPt][1] = pot[id]; ++ts.nPt; }

    if (g_oocStrategicTokCheck && g_oocStrategicTokNet.ok && t_tokCheckPending) {
        t_tokCheckPending = false;
        tokCheckGlobParity(gc, ts);
    }
    return ts;
}

// ---------------------------------------------------------------------------
// TERMINAL-LEAF RUN-VALUE BONUS (cross-combat setup, e.g. Happy Flower):
// Searcher3 terminal VICTORY leaves are priced with the native win model on
// the post-combat run state (HP, gold, potions, relic counters transferred
// exactly like BattleContext::exitBattle). The bonus is w * P(run win); within
// one combat the post-combat state differs across leaves only in those
// transferred fields, so the bonus changes relative leaf ordering by the
// run-level value of the battle's end state. The base rich row is built once
// per fight (future fights resampled from the act pool or zeroed, so the
// combat search stays hidden-info clean) and patched per leaf by index.
// ---------------------------------------------------------------------------
struct TermWinIndices {
    int curHp = -1, maxHp = -1, gold = -1, potionCount = -1;
    int ascension = -1, dBase = -1, rBase = -1;
    int potBase = -1;
    std::vector<int> potIdx;
    int happyFlower = -1, incenseBurner = -1, inkBottle = -1, inserter = -1;
    int nunchaku = -1, penNib = -1, sundial = -1, lizardTail = -1, neowsLament = -1;
    int boss = -1, nf0 = -1, nf1 = -1, nf2 = -1, nextElite = -1;
    int remElites = -1, remFights = -1;
    bool ok = false;
};
static const TermWinIndices &termWinIndices() {
    // Magic-static lambda: the C++11 init lock guards construction AND the
    // published fields. The previous lazy `static TermWinIndices m; if
    // (!m.ok)` pattern raced: first parallel battle on several threads could
    // read the half-built struct (garbage potIdx vector) and write through a
    // garbage index, corrupting the heap (segfault on the 24-thread server,
    // cpsi-eval arm, 2026-08-06).
    static const TermWinIndices m = [] {
        TermWinIndices m;
        const auto &idx = richIdxMap();
        auto f = [&](const std::string &n) -> int { return idx.count(n) ? (int)idx.at(n) : -1; };
        m.curHp = f("curHp"); m.maxHp = f("maxHp"); m.gold = f("gold");
        m.potionCount = f("potionCount");
        m.ascension = f("ascension"); m.dBase = f("d0"); m.rBase = f("r0");
        m.potBase = f("pot0");
        for (int i = 0; m.potBase >= 0 && i < 64; ++i) {
            const int ix = f("pot" + std::to_string(i));
            if (ix < 0) break;
            m.potIdx.push_back(ix);
        }
        m.happyFlower   = f("r" + std::to_string((int)RelicId::HAPPY_FLOWER));
        m.incenseBurner = f("r" + std::to_string((int)RelicId::INCENSE_BURNER));
        m.inkBottle     = f("r" + std::to_string((int)RelicId::INK_BOTTLE));
        m.inserter      = f("r" + std::to_string((int)RelicId::INSERTER));
        m.nunchaku      = f("r" + std::to_string((int)RelicId::NUNCHAKU));
        m.penNib        = f("r" + std::to_string((int)RelicId::PEN_NIB));
        m.sundial       = f("r" + std::to_string((int)RelicId::SUNDIAL));
        m.lizardTail    = f("r" + std::to_string((int)RelicId::LIZARD_TAIL));
        m.neowsLament   = f("r" + std::to_string((int)RelicId::NEOWS_LAMENT));
        m.boss = f("bossId"); m.nf0 = f("nextFight0"); m.nf1 = f("nextFight1");
        m.nf2 = f("nextFight2"); m.nextElite = f("nextEliteId");
        m.remElites = f("remElites"); m.remFights = f("remFights");
        m.ok = m.curHp >= 0 && m.potBase >= 0;
        return m;
    }();
    return m;
}

// Encode a run-level relic counter exactly like richRow: 1 + data (data 0 -> 1).
static int encRelicCounter(int data) { return 1 + (data > 0 ? data : 0); }

// Build the C_psi no-peek entry from the patched rich row, mirroring
// search::buildCpsiEntry's semantics (deck counts, relic presence [0..127],
// potion counts, scalars = ascension/curHp/maxHp + the 7 counter scalars
// recovered from the rich r<i> slots: slot = 1 + data when owned, else 0).
static void cpsiEntryFromRich(const std::vector<float> &row,
                              const TermWinIndices &ix,
                              float scalar[search::kCpsiScalars],
                              float deck[search::kCpsiCards],
                              float relics[search::kCpsiRelics],
                              float potions[search::kCpsiPotions]) {
    std::fill(scalar, scalar + search::kCpsiScalars, 0.f);
    std::fill(deck, deck + search::kCpsiCards, 0.f);
    std::fill(relics, relics + search::kCpsiRelics, 0.f);
    std::fill(potions, potions + search::kCpsiPotions, 0.f);
    if (ix.ascension >= 0 && ix.ascension < (int)row.size()) scalar[0] = row[ix.ascension];
    if (ix.curHp >= 0 && ix.curHp < (int)row.size()) scalar[1] = row[ix.curHp];
    if (ix.maxHp >= 0 && ix.maxHp < (int)row.size()) scalar[2] = row[ix.maxHp];
    const int counterSlots[7] = {ix.happyFlower, ix.incenseBurner, ix.inkBottle,
                                 ix.inserter, ix.nunchaku, ix.penNib, ix.sundial};
    for (int i = 0; i < 7; ++i) {
        const int s = counterSlots[i];
        if (s >= 0 && s < (int)row.size() && row[s] > 0.f) scalar[3 + i] = row[s] - 1.f;
    }
    if (ix.dBase >= 0)
        for (int id = 0; id < search::kCpsiCards; ++id) {
            const int s = ix.dBase + id;
            if (s < (int)row.size()) deck[id] = row[s];
        }
    if (ix.rBase >= 0)
        for (int id = 0; id < search::kCpsiRelics; ++id) {
            const int s = ix.rBase + id;
            if (s < (int)row.size()) relics[id] = row[s] > 0.f ? 1.f : 0.f;
        }
    for (int pid = 2; pid < search::kCpsiPotions; ++pid)   // skip INVALID/EMPTY like buildCpsiEntry
        if (pid < (int)ix.potIdx.size()) potions[pid] = row[ix.potIdx[pid]];
}

static double termLeafBonus(const BattleContext &bc) {
    // S3 terminal victory leaves only; returns w * P(run win | post-combat
    // state) on the same rich layout as v_win_trees.txt.
    if (!g_termWin || !g_winNet.ok || t_termBaseRow.empty()) return 0.0;
    const TermWinIndices &ix = termWinIndices();
    if (!ix.ok) return 0.0;

    std::vector<float> row = t_termBaseRow;
    // HP: same transfer as BattleContext::exitBattle (victory heals, applied
    // in relic-container order like updateRelicsOnExit: BURNING_BLOOD +6,
    // BLACK_BLOOD +12, MEAT_ON_THE_BONE +12 below half HP; Feed can raise
    // maxHp mid-fight). termLeafBonus runs only on victory leaves, so the
    // outcome gate is implied.
    int hp = bc.player.curHp;
    if (t_termGc)
        for (const auto &r : t_termGc->relics.relics) {
            switch (r.id) {
                case RelicId::BURNING_BLOOD:
                    hp = std::min(hp + 6, (int)bc.player.maxHp);
                    break;
                case RelicId::BLACK_BLOOD:
                    hp = std::min(hp + 12, (int)bc.player.maxHp);
                    break;
                case RelicId::MEAT_ON_THE_BONE:
                    if (hp <= bc.player.maxHp / 2)
                        hp = std::min(hp + 12, (int)bc.player.maxHp);
                    break;
                default:
                    break;
            }
        }
    row[ix.curHp] = (float)hp;
    row[ix.maxHp] = (float)bc.player.maxHp;
    row[ix.gold]  = (float)bc.player.gold;
    row[ix.potionCount] = (float)bc.potionCount;
    for (int i = 0; i < (int)ix.potIdx.size(); ++i) row[ix.potIdx[i]] = 0.0f;
    for (int i = 0; i < bc.potionCapacity && i < (int)bc.potions.size(); ++i) {
        const int pid = (int)bc.potions[i];
        if (pid == (int)Potion::EMPTY_POTION_SLOT) continue;
        if (pid >= 0 && pid < (int)ix.potIdx.size()) ++row[ix.potIdx[pid]];
    }
    // Relic counters: mirror BattleContext::updateRelicsOnExit writes. Each
    // patch is guarded on the run actually owning the relic (base value > 0),
    // so absent relics keep their 0.
    auto present = [&](int ix) { return ix >= 0 && row[ix] > 0.0f; };
    if (present(ix.happyFlower))   row[ix.happyFlower]   = (float)encRelicCounter(bc.player.happyFlowerCounter);
    if (present(ix.incenseBurner)) row[ix.incenseBurner] = (float)encRelicCounter(bc.player.incenseBurnerCounter);
    if (present(ix.inkBottle))     row[ix.inkBottle]     = (float)encRelicCounter(bc.player.inkBottleCounter);
    if (present(ix.inserter))      row[ix.inserter]      = (float)encRelicCounter(bc.player.inserterCounter);
    if (present(ix.nunchaku))      row[ix.nunchaku]      = (float)encRelicCounter(bc.player.nunchakuCounter);
    if (present(ix.penNib))
        row[ix.penNib] = (float)(bc.player.penNibCounter == -1 ? encRelicCounter(9)
                                                               : encRelicCounter(bc.player.penNibCounter));
    if (present(ix.sundial))       row[ix.sundial]       = (float)encRelicCounter(bc.player.sundialCounter);
    if (present(ix.lizardTail) && !bc.player.hasRelic<RelicId::LIZARD_TAIL>()) row[ix.lizardTail] = 1.0f;
    if (ix.neowsLament >= 0 && row[ix.neowsLament] > 1.0f) row[ix.neowsLament] -= 1.0f;

    // Parity check once per run: the patched vector must equal the full
    // vFeatCsv path on a real post-combat copy (mirrors tokCheckGlobParity).
    // The hidden future-fight features (resampled/zeroed in the base) are
    // zeroed in both before comparing.
    if (!t_termParityChecked && t_termGc) {
        GameContext post = *t_termGc;
        post.curHp = bc.player.curHp;   // updateRelicsOnExit applies the burn-blood heal itself
        post.maxHp = bc.player.maxHp;
        post.gold = bc.player.gold;
        post.potionCount = bc.potionCount;
        post.potions = bc.potions;
        bc.updateRelicsOnExit(post);
        std::vector<float> full = richFeatureVec(post);
        std::vector<float> patched = row;
        for (int i : {ix.boss, ix.nextElite, ix.nf0, ix.nf1, ix.nf2, ix.remElites, ix.remFights}) {
            if (i >= 0 && i < (int)full.size()) { full[i] = 0.0f; patched[i] = 0.0f; }
        }
        static thread_local std::vector<std::string> t_richNames;
        if (t_richNames.empty()) {
            std::string h = richHeader(); std::string cur;
            for (char c : h) { if (c == ',') { t_richNames.push_back(cur); cur.clear(); } else cur += c; }
            t_richNames.push_back(cur);
        }
        int mismatches = 0;
        for (int i = 0; i < (int)std::min(full.size(), patched.size()); ++i)
            if (full[i] != patched[i]) {
                const std::string &name = (i + 1) < (int)t_richNames.size() ? t_richNames[i + 1] : "?";
                if (mismatches < 8)
                    std::printf("[term-win parity] idx %d (%s): patched=%g full=%g\n", i, name.c_str(), patched[i], full[i]);
                ++mismatches;
            }
        if (mismatches)
            std::printf("[term-win parity] %d mismatched features (this run)\n", mismatches);
        t_termParityChecked = true;
    }
    // C_psi evaluator: bonus = w * P(win of the next fight) from the no-peek
    // survival model, priced on the same patched post-combat state. The
    // current fight's encounter is used as the fixed probe encounter — its
    // absolute contribution is a constant across a combat's leaves, so only
    // the state-dependent part (HP/potions/gold/counters) orders the leaves.
    // The cpsictr probe shows this model prices all counter relics with the
    // correct sign (charged counter -> lower next-fight death).
    if (g_termWinEval == 1 && g_cpsiNet.loaded()) {
        float scalar[search::kCpsiScalars];
        float deck[search::kCpsiCards], relics[search::kCpsiRelics], potions[search::kCpsiPotions];
        cpsiEntryFromRich(row, ix, scalar, deck, relics, potions);
        search::CpsiOut o;
        g_cpsiNet.predict(scalar, deck, relics, potions, (int)bc.encounter, o);
        return g_termWinW * o.win;
    }
    return g_termWinW * g_winNet.predict(row);
}

// Arm the bonus for one battle (runFullRunOOC, Searcher3 only): builds the
// base rich row once per fight with hidden future fights resampled/zeroed,
// then termLeafBonus patches the transferred fields per terminal leaf.
static void termWinArmForBattle(GameContext &gc) {
    const TermWinIndices &ix = termWinIndices();
    t_termGc = &gc;
    t_termParityChecked = false;
    if (g_termWinHidden == 1) {
        GameContext hidden = gc;
        resampleRemainingActEncounters(hidden, gc.seed + gc.floorNum);
        t_termBaseRow = richFeatureVec(hidden);
    } else {
        t_termBaseRow = richFeatureVec(gc);
        for (int i : {ix.nf0, ix.nf1, ix.nf2, ix.nextElite, ix.remElites, ix.remFights, ix.boss})
            if (i >= 0 && i < (int)t_termBaseRow.size()) t_termBaseRow[i] = 0.0f;
    }
    search::g_terminalBonus = &termLeafBonus;
}

static void termWinDisarm() {
    search::g_terminalBonus = nullptr;
    t_termGc = nullptr;
    t_termBaseRow.clear();
}

// Per-combat stall telemetry (STS_TERM_STALL_LOG=<path>): one CSV row per
// battle, written after exitBattle so the counters are the run-level values
// the next combat starts from. Absent relics are -1 (getRelicValue).
static void stallLogRow(const GameContext &gc, const BattleContext &bc, std::uint64_t seed) {
    if (g_stallLogPath.empty()) return;
    static std::mutex m;
    static bool headerWritten = false;
    std::lock_guard<std::mutex> lock(m);
    std::ofstream f(g_stallLogPath, std::ios::app);
    if (!f) return;
    if (!headerWritten) {
        f << "seed,floor,act,room,encounter,outcome,turns,hpEnd,maxHp,gold,potionCount,"
             "happyFlower,incenseBurner,inkBottle,nunchaku,penNib,sundial\n";
        headerWritten = true;
    }
    f << seed << ',' << gc.floorNum << ',' << gc.act << ',' << (int)gc.curRoom << ','
      << (int)bc.encounter << ',' << (bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0) << ','
      << (bc.turn + 1) << ',' << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ','
      << gc.potionCount << ','
      << gc.relics.getRelicValue(RelicId::HAPPY_FLOWER) << ','
      << gc.relics.getRelicValue(RelicId::INCENSE_BURNER) << ','
      << gc.relics.getRelicValue(RelicId::INK_BOTTLE) << ','
      << gc.relics.getRelicValue(RelicId::NUNCHAKU) << ','
      << gc.relics.getRelicValue(RelicId::PEN_NIB) << ','
      << gc.relics.getRelicValue(RelicId::SUNDIAL) << '\n';
    f.flush();
}

// Rank every legal OOC action in one server request.  The model predicts the
// next-combat win probability and surviving HP fraction; the training score
// used for action selection is the same 10*P(win)+expected HP objective used
// by the offline transfer check.
static bool oocActionNNPolicy(GameContext &gc) {
    if (!g_oocActionNN || gc.act < 1 || gc.act > 3) return false;
    const auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;

    // Native checkpoint-distilled inference (no server)
    if (g_oocCheckpointNet.ok) {
        const std::vector<float> state = richFeatureVec(gc);
        double best = -1e100;
        int bestIdx = -1;
        for (int i = 0; i < (int)actions.size(); ++i) {
            const double score = g_oocCheckpointNet.predict(
                state.data(), actions[i].bits, (int)gc.screenState, gc.act);
            if (score > best) { best = score; bestIdx = i; }
        }
        if (bestIdx < 0) return false;
        actions[bestIdx].execute(gc);
        return true;
    }

    // Server fallback
    std::ostringstream req;
    req << "OA;";
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) req << ',';
        req << actions[i].bits;
    }
    req << ';' << (int)gc.screenState << ';' << gc.act << ';' << vFeatCsv(gc) << '\n';
    const std::string resp = vTransact(req.str());
    std::istringstream in(resp);
    double best = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        std::string tok;
        if (!(in >> tok)) break;
        const auto comma = tok.find(',');
        if (comma == std::string::npos) break;
        const double pwin = std::atof(tok.substr(0, comma).c_str());
        const double hpFrac = std::atof(tok.substr(comma + 1).c_str());
        const double score = 10.0 * pwin + hpFrac * gc.maxHp;
        if (score > best) { best = score; bestIdx = i; }
    }
    if (bestIdx < 0) return false;
    actions[bestIdx].execute(gc);
    return true;
}

// Wave B regret gate (Step 5): per-screen deployed-default heuristic runners
// used to identify a_heur. Each mirrors the deployed-default OOC policy the
// datagen uses (runStrategicGenSeed), so the "heuristic" comparison arm and the
// regret arm share the same reference action.
static void regretHeurCardReward(GameContext &pre, search::ScumSearchAgent2 &) {
    serverCardRewardPolicy(pre);   // native floor card pick with skip
}
static void regretHeurRest(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_restWin && restWinPolicy(pre)) {}
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurUpgrade(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_restWin) upgradeSelectWinPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
// The heuristic probes mirror the LIVE fallback chain of the screen (the code
// path that would run if the gate returned false), so a_heur is the action the
// run would actually take without the gate — not the flags-off datagen default.
// SHOP is the critical case: bestbench forces shopV=true, so the live fallback
// is shopVPolicy, not stepOutOfCombatPolicy's relic-buy-or-random.
static void regretHeurEvent(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_eventV && pre.curEvent != Event::NEOW) eventVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurShop(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (t_shopV) shopVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurAgent(GameContext &pre, search::ScumSearchAgent2 &agent) {
    agent.stepOutOfCombatPolicy(pre);   // TREASURE
}
static void regretHeurBossRelic(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_bossRelicV) bossRelicVPolicy(pre);
    else agent.stepOutOfCombatPolicy(pre);
}
static void regretHeurMap(GameContext &pre, search::ScumSearchAgent2 &agent) {
    if (g_pathV) pathVPolicy(pre);
    else search::GameAction(chooseMapAction(pre)).execute(pre);
}

// One-ply post-action search for CARD REWARD decisions (Phase 5, 5.5.1).
// Every legal reward action is scored and the best action is executed only
// when its margin over the runner-up meets the gate
// (STS_OOC_STRATEGIC_MARGIN), otherwise the heuristic card policy stays in
// charge.  Scoring (Tier-B round, §72): the Q(s,a) head
// (OocStrategicNet::predictActionValue) evaluates each action directly on the
// pre-decision state — no clones or successor states.  STS_OOC_STRATEGIC_Q=0
// restores the V2 behaviour: successors of copied GameContexts are scored with
// the value head of the successor screen.  Greedy un-gated deployment is a
// recorded failure mode (EXPERIMENTS §66m), so the gate is mandatory.
// Score one V5/V6 action with the loaded strategic net: the Q_win head by
// default, or the policy head when STS_OOC_STRATEGIC_SCORE=policy (Phase F
// 5.7.2 gate arm).  predictPolicyLogit returns the raw logit — sigmoid to the
// probability scale so the probability-point STS_OOC_STRATEGIC_MARGIN
// semantics apply unchanged.
static double oocStrategicScore(const float *state, std::uint32_t bits,
                                const int cats[6], int actionType, int screen) {
    if (g_oocStrategicScorePolicy)
        return sigmoid(g_oocStrategicNet.predictPolicyLogit(state, bits, cats, actionType, screen));
    return g_oocStrategicNet.predictActionValue(state, bits, cats, actionType, screen);
}
static bool oocOnePlyCardRewardPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if (!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) return false;
    if (gc.screenState != ScreenState::REWARDS) return false;
    auto &r = gc.info.rewardsContainer;
    if (r.cardRewardCount == 0) return false;
    using RT = search::GameAction::RewardsActionType;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    // The baseline skips a group via CARD(rIdx,5), which the enumerator omits.
    const int rIdx = r.cardRewardCount - 1;
    const search::GameAction skipCard(RT::CARD, rIdx, 5);
    bool have = false;
    for (const auto &a : actions) if (a.bits == skipCard.bits) { have = true; break; }
    if (!have) actions.push_back(skipCard);
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate

    const double margin = g_oocStrategicMarginCard >= 0.0 ? g_oocStrategicMarginCard : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        // V4 token net: Q(s,a) on the token state (STS_OOC_STRATEGIC_Q does
        // not apply to the token path). TokState built once per decision.
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const bool useQ = g_oocStrategicQ;
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            double v;
            if (useQ) {
                int actionType, c1, c2, c3, cand1, cand2, cand3;
                strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
                const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
                v = oocStrategicScore(state.data(), actions[i].bits,
                                      cats, actionType, (int)gc.screenState);
            } else {
                GameContext probe = gc;
                probe.map = std::make_shared<Map>(*gc.map);
                actions[i].execute(probe);
                v = g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                   (int)probe.screenState);
            }
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurCardReward, agent);
}

// One-ply post-action search for CAMPFIRE decisions (Phase 5, 5.5.2): every
// legal rest option (REST/SMITH/LIFT/GIRYA/PEACE_PIPE/SHOVEL/SKIP) is scored
// with the Q(s,a) head on the pre-decision state and the best option is
// executed only when its margin over the runner-up meets the gate; otherwise
// the default rest layer (win-rate rest) runs.  The smith's upgrade-target
// pick (CARD_SELECT/UPGRADE) is gated separately by
// oocOnePlyUpgradeSelectPolicy under the same flag.
static bool oocOnePlyRestPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicRest) return false;
    if (gc.screenState != ScreenState::REST_ROOM) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginRest >= 0.0 ? g_oocStrategicMarginRest : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurRest, agent);
}

// One-ply Q gate for the smith's upgrade-target pick (the CARD_SELECT screen
// that follows a campfire SMITH).  Scores every legal target; executes the
// argmax only when its margin over the runner-up meets the gate, else the
// win-rate upgrade-target layer runs.
static bool oocOnePlyUpgradeSelectPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicRest) return false;
    if (gc.screenState != ScreenState::CARD_SELECT
        || gc.info.selectScreenType != CardSelectScreenType::UPGRADE) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginRest >= 0.0 ? g_oocStrategicMarginRest : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurUpgrade, agent);
}

// One-ply post-action search for EVENT decisions (Phase 5, 5.5.3): every legal
// event option (including Neow) is scored with the Q(s,a) head on the
// pre-decision state and the best option is executed only when its margin over
// the runner-up meets the gate; otherwise the default event layer runs.  The
// Tier-B labels already average the stochastic continuations of each option,
// so no RNG-clone sampling is needed at deployment.
static bool oocOnePlyEventPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicEvent) return false;
    if (gc.screenState != ScreenState::EVENT_SCREEN) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;   // e.g. MATCH_AND_KEEP
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginEvent >= 0.0 ? g_oocStrategicMarginEvent : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurEvent, agent);
}

// One-ply post-action search for SHOP decisions (R6, §76): every legal shop
// action (buy card/relic/potion, CARD_REMOVE, leave) is scored with the Q(s,a)
// head on the pre-decision state and the best action is executed only when its
// margin over the runner-up meets the gate; otherwise the V-knapsack shop layer
// runs.  Called once per decision, so repeated buys are re-scored each time.
static bool oocOnePlyShopPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicShop) return false;
    if (gc.screenState != ScreenState::SHOP_ROOM) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginShop >= 0.0 ? g_oocStrategicMarginShop : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurShop, agent);
}

// One-ply post-action search for TREASURE decisions (R6, §76): the chest open/
// skip actions are scored with the Q(s,a) head on the pre-decision state and
// the best action is executed only when its margin over the runner-up meets
// the gate; otherwise the default treasure layer runs.
static bool oocOnePlyTreasurePolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicTreasure) return false;
    if (gc.screenState != ScreenState::TREASURE_ROOM) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginTreasure >= 0.0 ? g_oocStrategicMarginTreasure : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurAgent, agent);
}

// One-ply post-action search for BOSS RELIC decisions (R6, §76): the three
// offered relics plus skip are scored with the Q(s,a) head on the
// pre-decision state and the best action is executed only when its margin over
// the runner-up meets the gate; otherwise the boss relic layer runs.
static bool oocOnePlyBossRelicPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicBossRelic) return false;
    if (gc.screenState != ScreenState::BOSS_RELIC_REWARDS) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginBossRelic >= 0.0 ? g_oocStrategicMarginBossRelic : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = oocStrategicScore(state.data(), actions[i].bits,
                                               cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurBossRelic, agent);
}

// One-ply post-action search for MAP decisions (M1 wave): every legal child
// node of the visible map DAG is scored with the Q(s,a) head on the
// pre-decision state and the best child is executed only when its margin over
// the runner-up meets the gate; otherwise the heuristic pathing layer runs.
// Candidate resolution follows strategicCands' MAP_SCREEN case (cand1=x,
// cand2=row, cand3=room), identical to the Tier-B training rows, so no new
// datagen is needed. The map is fully visible at decision time (no hidden RNG
// or future-seed use), satisfying spec A.14 for this gate.
static bool oocOnePlyMapPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocStrategicMap) return false;
    if (gc.screenState != ScreenState::MAP_SCREEN || gc.curMapNodeY == 14) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    std::vector<double> q(actions.size(), -1e100);   // per-action scores for the regret gate
    const double margin = g_oocStrategicMarginMap >= 0.0 ? g_oocStrategicMarginMap : g_oocStrategicMargin;
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            int entType, entId; float goldGePrice;
            tokEntity(gc, actions[i], entType, entId, goldGePrice);
            const float entT[4] = {entType == 0 ? 1.0f : 0.0f, entType == 1 ? 1.0f : 0.0f,
                                   entType == 2 ? 1.0f : 0.0f, entType == 3 ? 1.0f : 0.0f};
            const double v = g_oocStrategicTokNet.predictActionValue(
                ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                actions[i].bits, cats, actionType, (int)gc.screenState, entT, entId, goldGePrice);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    } else {
        const std::vector<float> state = richFeatureVec(gc);
        // V6 map-DAG encoder (5.3.2): when the artifact carries it, score each
        // child with the route embedding (rooms/edges/special from the visible
        // map, position + chosen child from gc / cand1), matching the trainer's
        // MAP-screen rows exactly (mapbatch export format).
        int mapRooms[105], mapEdges[105], mapSpecial[105];
        const bool useMapEnc = g_oocStrategicNet.mapEnc;
        if (useMapEnc) {
            const Map &mp = *gc.map;
            for (int y = 0; y < 15; ++y)
                for (int x = 0; x < 7; ++x) {
                    const int i = y * 7 + x;
                    const MapNode &n = mp.getNode(x, y);
                    mapRooms[i] = (int)n.room;
                    int em = 0;
                    for (int e = 0; e < n.edgeCount; ++e) em |= 1 << n.edges[e];
                    mapEdges[i] = em;
                    mapSpecial[i] = 0;
                }
            if (mp.burningEliteX >= 0 && mp.burningEliteY >= 0 && !gc.greenKey)
                mapSpecial[mp.burningEliteY * 7 + mp.burningEliteX] = 1;
        }
        for (int i = 0; i < (int)actions.size(); ++i) {
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(gc, actions[i], actionType, c1, c2, c3, cand1, cand2, cand3);
            const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
            const double v = useMapEnc
                ? g_oocStrategicNet.predictMapActionValue(state.data(), actions[i].bits, cats,
                                                          actionType, (int)gc.screenState,
                                                          mapRooms, mapEdges, mapSpecial,
                                                          gc.curMapNodeX, gc.curMapNodeY, cand1)
                : oocStrategicScore(state.data(), actions[i].bits,
                                    cats, actionType, (int)gc.screenState);
            q[i] = v;
            if (v > best) { second = best; best = v; bestIdx = i; }
            else if (v > second) second = v;
        }
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurMap, agent);
}

// ---------------------------------------------------------------------------
// M2: short-horizon map route search (plan 5.6.2, spec A.11 "map routes").
//
// For each legal child node of the visible map DAG, expand the downstream
// graph HORIZON rows deep (2..5). Each room on a route is priced with the
// C_psi combat outcome surrogate (CombatCpsiNet): fights return P(death) and
// E[hp/maxHp | win]; rests heal a fixed 30% of max HP; shops/treasures/events
// pass through unchanged (v1 limitation). Encounters for hypothetical fights
// are sampled from the act's visible pool (strong monsters / elites) with a
// LOCAL RNG-free expectation — never the run's true future encounter list
// (spec A.14). A route's value = survival-probability × strategic V-head at
// the leaf state (map position advanced to the leaf node, HP updated). The
// best route per child is the max over its downstream paths; the child is
// executed only when its margin over the runner-up meets the gate, else
// chooseMapAction runs. This replaces the M1 one-ply Q gate for map decisions
// when enabled.
// ---------------------------------------------------------------------------
struct RouteCpsiCache {
    bool loaded = false;
    float pDeath = 1.f;   // P(death) from the sampled encounter pool
    float hpFrac = 1.f;   // E[hp/maxHp | win]
};

// Pool-average C_psi expectation for one room type. Row-14 nodes hold the
// last real rooms of the act (elites/hallways); the forced boss fight at
// y==14 is not expanded by this search (the leaf V prices the remaining run).
static bool routeCpsiExpect(const GameContext &gc, Room room,
                            RouteCpsiCache &out) {
    if (!g_cpsiNet.loaded()) return false;
    const int act = gc.act;
    if (room == Room::MONSTER) {
        // Weighted pool expectation: the act's strong pool with its visible
        // weights (MonsterEncounterPool::strongWeights) — the conditional
        // distribution a player knows, never the run's true encounter list.
        const int poolSize = (int)MonsterEncounterPool::strongCount[act - 1];
        double pd = 0, hp = 0, wsum = 0;
        for (int i = 0; i < poolSize; ++i) {
            const double w = MonsterEncounterPool::strongWeights[act - 1][i];
            float scalar[search::kCpsiScalars];
            float deck[search::kCpsiCards];
            float relics[search::kCpsiRelics];
            float potions[search::kCpsiPotions];
            search::buildCpsiEntry(gc, scalar, deck, relics, potions);
            search::CpsiOut r;
            g_cpsiNet.predict(scalar, deck, relics, potions,
                              (int)MonsterEncounterPool::strongEnemies[act - 1][i], r);
            pd += w * r.death; hp += w * r.hp; wsum += w;
        }
        out.pDeath = (float)(pd / wsum);
        out.hpFrac = (float)(hp / wsum);
        return true;
    }
    if (room == Room::ELITE) {
        // Elites are drawn uniformly (rollElite: 1/3 each).
        double pd = 0, hp = 0;
        for (int i = 0; i < 3; ++i) {
            float scalar[search::kCpsiScalars];
            float deck[search::kCpsiCards];
            float relics[search::kCpsiRelics];
            float potions[search::kCpsiPotions];
            search::buildCpsiEntry(gc, scalar, deck, relics, potions);
            search::CpsiOut r;
            g_cpsiNet.predict(scalar, deck, relics, potions,
                              (int)MonsterEncounterPool::elites[act - 1][i], r);
            pd += r.death; hp += r.hp;
        }
        out.pDeath = (float)(pd / 3);
        out.hpFrac = (float)(hp / 3);
        return true;
    }
    return false;
}

// Leaf value of a route: the per-screen value head on the state advanced to
// the leaf node with the route's expected HP (V3 rich state; token-net glob
// when the token net is loaded). The leaf is a MAP_SCREEN successor state
// (the next decision is another map choice), so the MAP head prices it.
// Mutates only curMapNodeX/Y/curHp and restores them (no deep copy per leaf).
static double mapRouteLeafValue(GameContext &gc, int leafX, int leafY,
                                double hpFrac) {
    const int saveX = gc.curMapNodeX, saveY = gc.curMapNodeY, saveHp = gc.curHp;
    gc.curMapNodeX = leafX;
    gc.curMapNodeY = leafY;
    gc.curHp = (int)std::llround(hpFrac * gc.maxHp);
    double v;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        v = g_oocStrategicTokNet.predictValue(ts.glob, (int)ScreenState::MAP_SCREEN);
    } else {
        v = g_oocStrategicNet.predictValue(richFeatureVec(gc).data(),
                                           (int)ScreenState::MAP_SCREEN);
    }
    gc.curMapNodeX = saveX; gc.curMapNodeY = saveY; gc.curHp = saveHp;
    return v;
}

// Best route value from node (x,y) looking down `depth` more rows, given the
// survival prob and HP fraction carried so far. Max over downstream paths
// (mirrors chooseMapAction's bottom-up DP over the visible DAG). The C_psi
// expectation per node is memoized in cache[7*15] (state-independent within
// the decision: the entry state used is the CURRENT pre-decision state, an
// explicit v1 approximation documented in the wave contract).
static double mapRouteSearch(GameContext &gc, int x, int y, int depth,
                             double survival, double hpFrac,
                             RouteCpsiCache cache[7 * 15]) {
    const Map &map = *gc.map;
    const MapNode &n = map.getNode(x, y);
    if (depth <= 0 || y >= 14) {
        return survival * std::max(0.0, mapRouteLeafValue(gc, x, y, hpFrac));
    }
    double nextSurvival = survival, nextHp = hpFrac;
    switch (n.room) {
        case Room::MONSTER:
        case Room::ELITE: {
            RouteCpsiCache &cpsi = cache[y * 7 + x];
            if (!cpsi.loaded) {
                cpsi.loaded = routeCpsiExpect(gc, n.room, cpsi);
                if (!cpsi.loaded) {
                    cpsi.pDeath = 0.f;      // C_psi missing: price the fight as free
                    cpsi.hpFrac = 1.f;
                }
            }
            nextSurvival = survival * (1.0 - cpsi.pDeath);
            nextHp = hpFrac * cpsi.hpFrac;
            break;
        }
        case Room::REST:
            nextHp = std::min(1.0, hpFrac + 0.30);   // base campfire heal
            break;
        default:
            break;                                    // SHOP/TREASURE/EVENT pass through
    }
    if (nextSurvival <= 1e-9 || nextHp <= 0.0) return 0.0;

    double bestChild = -1e100;
    for (int i = 0; i < n.edgeCount; ++i) {
        const double v = mapRouteSearch(gc, n.edges[i], y + 1, depth - 1,
                                        nextSurvival, nextHp, cache);
        if (v > bestChild) bestChild = v;
    }
    if (n.edgeCount == 0) {
        // Dead-end node: the route stops here (leaf).
        return nextSurvival * std::max(0.0, mapRouteLeafValue(gc, x, y, nextHp));
    }
    return bestChild;
}

// M2: short-horizon map route search (plan 5.6.2). Requires a loaded C_psi
// surrogate AND a strategic net (V3 or V4) for the leaf. Encounters come from
// the act's visible pool via expectation, so no hidden future information is
// used. Margin-gated like every other gate.
static bool oocMapRouteSearchPolicy(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_cpsiNet.loaded()) return false;
    if (!g_oocMapRoute) return false;
    if (gc.screenState != ScreenState::MAP_SCREEN || gc.curMapNodeY == 14) return false;
    if (gc.act < 1 || gc.act > 3) return false;
    std::vector<search::GameAction> actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;
    const int depth = std::max(2, std::min(5, g_oocMapRouteHorizon));
    const double margin = g_oocStrategicMarginMap >= 0.0 ? g_oocStrategicMarginMap : g_oocStrategicMargin;
    std::vector<double> q(actions.size(), -1e100);   // per-route scores for the regret gate

    const double baseHpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;
    RouteCpsiCache cache[7 * 15];   // shared across children: the C_psi entry
                                    // state is always the current pre-decision
                                    // state (documented v1 approximation)
    double best = -1e100, second = -1e100;
    int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        const int childX = actions[i].getIdx1();
        const int childY = gc.curMapNodeY + 1;
        const double v = mapRouteSearch(gc, childX, childY, depth, 1.0, baseHpFrac, cache);
        q[i] = v;
        if (v > best) { second = best; best = v; bestIdx = i; }
        else if (v > second) second = v;
    }
    return regretGateTail(gc, actions, q, bestIdx, best, second, margin,
                          g_oocStrategicGateEps, regretHeurMap, agent);
}

struct OocCounterfactualResult {
    double won;
    double floor;
    double hp;
    int bootstrapped = 0;   // 1 when floor/won came from the native models, 0 on terminal
    bool valid = true;
    bool survivedH = false; // alive at the requested bounded horizon (diagnostic only)
};

// Direct near-term survival supervision for out-of-combat action values.  These
// are deliberately *outcomes of the real counterfactual continuation*, rather
// than a hand-authored encounter tier.  `passed` means that the branch both
// reached and won the target fight; an elite can remain unseen when the chosen
// route avoids all remaining elites, while the next battle and current-act boss
// are normally mandatory unless the branch dies first.
struct FutureFightProbe {
    bool nextCombatSeen = false, nextCombatPassed = false;
    bool nextEliteSeen = false, nextElitePassed = false;
    bool nextBossSeen = false, nextBossPassed = false;
    bool completed = false;  // false only when a bounded rollout was censored
    struct Observation {
        Room room = Room::INVALID;
        MonsterEncounter encounter = MonsterEncounter::INVALID;
        int floor = 0;
        int hp = 0;
        int maxHp = 1;
        bool passed = false;
    };
    // One record for each fight actually reached.  Across encounter-queue
    // samples, reaching a record is precisely its estimated occurrence chance.
    std::vector<Observation> fights;
};

struct PredictedCheckpointFight {
    double winProbability = 0.0;
    int endHpIfWin = 1;
    int maxHp = 1;
    bool predictedWin = false;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter);

// Continue a copied run after any out-of-combat counterfactual action. Every
// branch in one decision uses the same agent seed and copied GameContext RNG
// state (common random numbers).  maxFights < 0 means finish the whole run.  A
// bounded branch resolves rewards/path choices after its last fight, stops at
// the next battle, then bootstraps expected final floor and P(win).
static OocCounterfactualResult
finishOocCounterfactual(GameContext gc, int sims, std::uint64_t agentSeed,
                        PathHistory path, int maxFights = -1, bool bootstrap = false,
                        FutureFightProbe *probe = nullptr, int stopAfterAct = 0,
                        const std::vector<int> *fightSimsSeq = nullptr,
                        bool usePredict = false) {
    const int healthBefore = search::g_simHealthFailureCount;
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    int fights = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if (maxFights >= 0 && fights >= maxFights) break;
            const Room room = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSimsSeq && !fightSimsSeq->empty()
                ? (*fightSimsSeq)[std::min(fights, (int)fightSimsSeq->size() - 1)]
                : fightSims(gc, sims);
            BattleContext bc; bc.init(gc);
            bool passed; int endHp, endMaxHp;
            if (usePredict) {
                const auto prediction = predictCheckpointFight(gc, bc.encounter);
                passed = prediction.predictedWin;
                endHp = passed ? prediction.endHpIfWin : 0;
                endMaxHp = prediction.maxHp;
                if (!passed) {
                    gc.outcome = GameOutcome::PLAYER_LOSS;
                } else {
                    BattleContext virtualBattle{};
                    virtualBattle.init(gc, bc.encounter);
                    virtualBattle.player.curHp = prediction.endHpIfWin;
                    virtualBattle.outcome = Outcome::PLAYER_VICTORY;
                    virtualBattle.exitBattle(gc);
                }
            } else {
                agent.playoutBattle(bc);
                passed = bc.outcome == Outcome::PLAYER_VICTORY;
                endHp = passed ? gc.curHp : 0;
                endMaxHp = gc.maxHp;
                bc.exitBattle(gc);
            }
            if (probe) {
                probe->fights.push_back({room, bc.encounter, gc.floorNum, endHp,
                                         endMaxHp, passed});
                if (!probe->nextCombatSeen) {
                    probe->nextCombatSeen = true;
                    probe->nextCombatPassed = passed;
                }
                if (room == Room::ELITE && !probe->nextEliteSeen) {
                    probe->nextEliteSeen = true;
                    probe->nextElitePassed = passed;
                }
                if (room == Room::BOSS && !probe->nextBossSeen) {
                    probe->nextBossSeen = true;
                    probe->nextBossPassed = passed;
                }
            }
            ++fights;
            // This is deliberately after recording the boss outcome: a full-act
            // evaluator stops at the current act's boss rather than leaking a
            // candidate's score into Act+1 rewards/fights.
            if (stopAfterAct > 0 && battleAct == stopAfterAct && room == Room::BOSS) break;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF later rest seed=" << gc.seed << " floor=" << gc.floorNum << "\n";
            if (!(g_restWin && restWinPolicy(gc))) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.empty()) break;
                actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    double won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : 0.0;
    double floor = gc.floorNum;
    int bootstrapped = 0;
    if (bootstrap && gc.outcome == GameOutcome::UNDECIDED) {
        const double vf = vStateRaw(gc);
        const double vw = vStateWin(gc);
        if (std::isfinite(vf) && vf >= gc.floorNum && vf <= 60) floor = vf;
        if (std::isfinite(vw) && vw >= 0 && vw <= 1) won = vw;
        bootstrapped = 1;
    }
    const bool survivedH = gc.outcome != GameOutcome::PLAYER_LOSS;
    const bool valid = search::isValidTrainingTerminal(
        gc.outcome != GameOutcome::UNDECIDED, healthBefore,
        search::g_simHealthFailureCount,
        bootstrap && gc.outcome == GameOutcome::UNDECIDED);
    if (!valid && t_trainingRunActive) {
        g_trainingHealthFailures += std::max(0, search::g_simHealthFailureCount - healthBefore);
        t_trainingBranchHealthFailures += std::max(0, search::g_simHealthFailureCount - healthBefore);
    }
    // Branch health belongs to this branch, not to the enclosing source run.
    if (probe) probe->completed = valid && gc.outcome != GameOutcome::UNDECIDED;
    t_curPath = nullptr;
    return {valid ? won : 0.0, valid ? floor : 0.0,
            valid ? (double)gc.curHp : 0.0, valid ? bootstrapped : -1, valid,
            valid && survivedH};
}

// GameContext normally shares its Map through a shared_ptr. A counterfactual may
// reach the next act and regenerate that map; detach it so speculative branches
// cannot overwrite the live run's current-act map.
static GameContext detachedCounterfactualCopy(const GameContext &gc) {
    GameContext copy = gc;
    if (gc.map) copy.map = std::make_shared<Map>(*gc.map);
    return copy;
}

// Draw one encounter from the game pool.  We use this rather than an equal
// encounter average: Slay the Spire's pools are weighted, and the no-repeat
// rule makes a sequence's conditional distribution depend on its prior two
// encounters.
static MonsterEncounter sampleEncounterWeighted(const MonsterEncounter *pool,
                                                const float *weights, int count,
                                                Random &rng) {
    const float roll = rng.random();
    float cumulative = 0.0f;
    for (int i = 0; i < count; ++i) {
        cumulative += weights[i];
        if (roll < cumulative) return pool[i];
    }
    return pool[count - 1];
}

// Replace only the unseen normal/elite encounter queues in a copied run.  A
// live GameContext has a concrete queue for its seed, but that information is
// hidden from a player.  Sampling this conditional queue is therefore the
// appropriate information-set evaluation for a card pick.  The act boss is
// deliberately NOT resampled: it is chosen at act generation and visible to
// the player, so every candidate must evaluate the known gc.boss.  Map layout
// and all non-combat RNG stay fixed so alternatives differ principally in
// combat fit.
static void resampleRemainingActEncounters(GameContext &gc, std::uint64_t branchSeed) {
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    Random rng(branchSeed);
    const int weakCount = gc.act == 1 ? 3 : 2;
    for (int i = gc.monsterListOffset; i < (int)gc.monsterList.size(); ++i) {
        const bool weak = i < weakCount;
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        MonsterEncounter draw;
        do {
            draw = sampleEncounterWeighted(pool, weights, count, rng);
        } while ((i > 0 && draw == gc.monsterList[i - 1]) ||
                 (i > 1 && draw == gc.monsterList[i - 2]));
        gc.monsterList[i] = draw;
    }
    for (int i = gc.eliteMonsterListOffset; i < (int)gc.eliteMonsterList.size(); ++i) {
        MonsterEncounter draw;
        do {
            draw = MonsterEncounterPool::elites[actIdx][rng.random(2)];
        } while (i > 0 && draw == gc.eliteMonsterList[i - 1]);
        gc.eliteMonsterList[i] = draw;
    }
}

// Death itself is a discontinuity, and HP is most valuable near the danger
// boundary rather than linearly.  This utility is deliberately encounter-agnostic:
// a hard fight matters because it lowers survival/HP in the simulations, not
// because we gave it a hand-authored tier.
static double nonlinearHpSafety(int hp, int maxHp) {
    const double fraction = maxHp > 0 ? (double)hp / maxHp : 0.0;
    return 1.0 / (1.0 + std::exp(-(fraction - 0.35) / 0.10));
}

static double allActFightUtility(const FutureFightProbe &probe, int decisionFloor) {
    double utility = 0.0;
    for (const auto &f : probe.fights) {
        const int floorsAway = std::max(0, f.floor - decisionFloor);
        const double urgency = std::pow(g_actFightProbeFloorDecay, floorsAway);
        // Reaching this record is its occurrence indicator.  Averaging over
        // sampled queues thus estimates P(occurs) * P(survives | occurs), while
        // the sigmoid values a post-fight safety buffer without treating HP as
        // a linear resource.
        utility += urgency * (f.passed ? nonlinearHpSafety(f.hp, f.maxHp) : -1.0);
    }
    return utility;
}

// Full-act, encounter-distribution card policy.  Candidates are card offers
// plus Skip.  Every candidate sees the same sampled hidden encounter queues
// (common random numbers), follows the actual selected map route to the boss,
// and is ranked solely by allActFightUtility -- no V/card scorer is queried for
// this immediate decision.
static bool actFightProbeDraftPolicy(GameContext &gc) {
    if (!g_actFightProbeDraft) return false;
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e100;
        int bestIdx = 5;  // the simulator evaluates Skip as a normal candidate
        // Diagnostic: compute the baseline floor-model pick for comparison
        int baselinePick = 5;
        if (g_actFightProbeTrace)
            baselinePick = nativeFloorCardPick(gc, rIdx);
        // Per-candidate per-future probes saved for trace breakdown
        std::vector<std::vector<FutureFightProbe>> traceFutureProbes;
        if (g_actFightProbeTrace)
            traceFutureProbes.resize(nCards + 1);
        std::vector<double> candidateScores(nCards + 1, 0.0);
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = cand < nCards ? cand : 5;
            double total = 0.0;
            for (int f = 0; f < g_actFightProbeFutures; ++f) {
                // Depends on the decision/future but never on candidate: exact
                // same encounter possibilities for each offered card.
                const std::uint64_t branchSeed = gc.seed
                    ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                    ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(gc.floorNum + 31 * rIdx));
                GameContext branch = detachedCounterfactualCopy(gc);
                search::GameAction(RT::CARD, rIdx, cardIdx).execute(branch);
                resampleRemainingActEncounters(branch, branchSeed);
                FutureFightProbe probe;
                finishOocCounterfactual(std::move(branch), g_actFightProbeSims,
                                        branchSeed, basePath, -1, false, &probe, gc.act,
                                        nullptr, g_actFightProbePredict);
                total += allActFightUtility(probe, gc.floorNum);
                if (g_actFightProbeTrace)
                    traceFutureProbes[cand].push_back(probe);
            }
            const double score = total / std::max(1, g_actFightProbeFutures);
            candidateScores[cand] = score;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        if (g_actFightProbeTrace) {
            // Consecutive-oracle-override counter
            static int consecutiveOverrideCount = 0;
            const bool oracleOverrides = (bestIdx != baselinePick);
            if (oracleOverrides) ++consecutiveOverrideCount;
            else consecutiveOverrideCount = 0;
            std::cerr << "[act-fight draft floor=" << gc.floorNum << " act=" << gc.act
                      << " baseline=" << (baselinePick == 5 ? "skip" : r.cardRewards[rIdx][baselinePick].getName())
                      << "(" << baselinePick << ")"
                      << " overrides=" << consecutiveOverrideCount << "]\n  scores:";
            for (int cand = 0; cand <= nCards; ++cand) {
                if (cand == nCards) std::cerr << " skip=" << candidateScores[cand];
                else std::cerr << ' ' << r.cardRewards[rIdx][cand].getName()
                               << '=' << candidateScores[cand];
            }
            std::cerr << " -> " << (bestIdx == 5 ? "skip" : r.cardRewards[rIdx][bestIdx].getName());
            if (oracleOverrides)
                std::cerr << " OVERRIDES";
            std::cerr << '\n';
            // Per-future fight breakdown for the winning candidate
            const int winCand = (bestIdx == 5) ? nCards : bestIdx;
            std::cerr << "  futures=" << g_actFightProbeFutures
                      << " floor-dcy=" << g_actFightProbeFloorDecay << ':';
            for (int f = 0; f < (int)traceFutureProbes[winCand].size()
                              && f < g_actFightProbeFutures; ++f) {
                const auto &probe = traceFutureProbes[winCand][f];
                double futUtil = allActFightUtility(probe, gc.floorNum);
                std::cerr << (f ? " |" : " [") << "f" << f
                          << " util=" << futUtil;
                for (const auto &fight : probe.fights) {
                    const int floorsAway = std::max(0, fight.floor - gc.floorNum);
                    const double urgency = std::pow(g_actFightProbeFloorDecay, floorsAway);
                    const double safety = fight.passed
                        ? nonlinearHpSafety(fight.hp, fight.maxHp) : -1.0;
                    std::cerr << " " << (fight.passed ? "W" : "L")
                              << " f" << fight.floor
                              << " " << monsterEncounterEnumNames[(int)fight.encounter]
                              << " hp" << fight.hp << "/" << fight.maxHp
                              << " d" << floorsAway
                              << " u" << urgency
                              << " s" << safety;
                }
                std::cerr << ']';
            }
            std::cerr << '\n';
        }
        // Margin gate: if the oracle isn't confident enough about its best pick,
        // fall through to the baseline card policy for this rewards screen.
        if (g_actFightProbeMargin > 0.0) {
            double secondScore = -1e100;
            for (int cand = 0; cand <= nCards; ++cand) {
                const int cardIdx = cand < nCards ? cand : 5;
                if (cardIdx == bestIdx) continue;
                if (candidateScores[cand] > secondScore) secondScore = candidateScores[cand];
            }
            const double margin = bestScore - secondScore;
            if (margin < g_actFightProbeMargin) {
                if (g_actFightProbeTrace)
                    std::cerr << "  margin=" << margin << " < " << g_actFightProbeMargin
                              << " -> fallback\n";
                t_curPath = savedPath;
                return false;
            }
            if (g_actFightProbeTrace)
                std::cerr << "  margin=" << margin << " >= " << g_actFightProbeMargin << " fire\n";
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    t_curPath = savedPath;
    return true;
}

struct EncounterOption {
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
};

// Conditional enemy pools at a concrete combat checkpoint. Normal and elite
// entries retain the game's no-repeat constraints; event fights are fixed by
// their event option. This gives a probability distribution without a hand-made
// difficulty tier.
static std::vector<EncounterOption> possibleEncounterOptions(const GameContext &gc) {
    std::vector<EncounterOption> out;
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    if (gc.curRoom == Room::MONSTER) {
        const int used = gc.monsterListOffset - 1; // battle already consumed this queue slot
        const bool weak = used < (gc.act == 1 ? 3 : 2);
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        double total = 0.0;
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) total += weights[i];
        }
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) out.push_back({pool[i], weights[i] / total});
        }
    } else if (gc.curRoom == Room::ELITE) {
        const int used = gc.eliteMonsterListOffset - 1;
        const MonsterEncounter prev = used > 0 ? gc.eliteMonsterList[used - 1] : MonsterEncounter::INVALID;
        int count = 0;
        for (int i = 0; i < 3; ++i) if (MonsterEncounterPool::elites[actIdx][i] != prev) ++count;
        for (int i = 0; i < 3; ++i) {
            const MonsterEncounter e = MonsterEncounterPool::elites[actIdx][i];
            if (e != prev) out.push_back({e, 1.0 / count});
        }
    } else if (gc.curRoom == Room::BOSS) {
        // Unlike the normal and elite queues, the boss was selected when the
        // act was generated and is public information.  Do not average in
        // alternative bosses the player will never face.
        out.push_back({gc.boss, 1.0});
    } else {
        out.push_back({gc.info.encounter, 1.0});
    }
    return out;
}

// One sampled progression trunk per candidate/future provides realistic deck,
// relic and HP checkpoints. At each reached combat, every possible enemy is
// fought independently from that same pre-fight state; this avoids a recursive
// full-act continuation for each action/enemy combination.
struct CheckpointFightComponent {
    int floor = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
    bool passed = false;
    int hp = 0;
    int maxHp = 1;
    double safety = 0.0;
    double contribution = 0.0;
    int sims = 0;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter) {
    BattleContext bc{};
    bc.init(gc, encounter);
    const auto prediction = g_actFightProbePredictNet.predictOutcome(bc);
    const int maxHp = std::max(1, bc.player.maxHp);
    return {
        std::max(0.0, std::min(1.0, prediction.winProbability)),
        std::max(1, std::min(maxHp, (int)std::lround(prediction.endHpFractionIfWin * maxHp))),
        maxHp,
        prediction.winProbability >= g_actFightProbePredictWinThreshold,
    };
}

// Complete a battle without a combat search.  BattleContext::exitBattle still
// takes the ordinary victory route (including Burning Blood and reward setup),
// but no cards, potions, or combat RNG are consumed.  That missing combat-side
// transition state is the known approximation of this fast benchmark mode.
static bool applyPredictedCheckpointFight(GameContext &gc, MonsterEncounter encounter,
                                          PredictedCheckpointFight *out = nullptr) {
    const auto prediction = predictCheckpointFight(gc, encounter);
    if (out) *out = prediction;
    if (!prediction.predictedWin) {
        gc.outcome = GameOutcome::PLAYER_LOSS;
        return false;
    }
    BattleContext virtualBattle{};
    virtualBattle.init(gc, encounter);
    virtualBattle.player.curHp = prediction.endHpIfWin;
    virtualBattle.outcome = Outcome::PLAYER_VICTORY;
    virtualBattle.exitBattle(gc);
    return gc.outcome == GameOutcome::UNDECIDED;
}

struct OocEncounterPrediction {
    double winProbability = -1.0;
    double hpFraction = 0.0;
};

static std::vector<OocEncounterPrediction> queryOocEncounterPredictions(
        const std::string &rootState, std::uint32_t actionBits, int screen, int act,
        const std::vector<MonsterEncounter> &encounters) {
    std::ostringstream req;
    req << "OE;" << actionBits << ';';
    for (int i = 0; i < (int)encounters.size(); ++i) {
        if (i) req << ',';
        req << (int)encounters[i];
    }
    req << ';' << screen << ';' << act << ';' << rootState << '\n';
    std::istringstream in(vTransact(req.str()));
    std::vector<OocEncounterPrediction> out;
    for (int i = 0; i < (int)encounters.size(); ++i) {
        std::string token;
        if (!(in >> token)) break;
        const auto comma = token.find(',');
        if (comma == std::string::npos) break;
        out.push_back({std::atof(token.substr(0, comma).c_str()),
                       std::atof(token.substr(comma + 1).c_str())});
    }
    return out;
}

static double checkpointedActFightUtility(GameContext gc, int sims, std::uint64_t agentSeed,
                                           PathHistory path, int decisionFloor,
                                           const std::string &rootState,
                                           std::uint32_t rootActionBits,
                                           int rootScreen, int rootAct,
                                           std::vector<CheckpointFightComponent> *components = nullptr) {
    search::ScumSearchAgent2 trunkAgent;
    trunkAgent.simulationCountBase = sims;
    trunkAgent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    double utility = 0.0;
    int steps = 0;
    int checkpointCount = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED && gc.act >= 1 && gc.act <= 3) {
        if (++steps > 160) {
            std::cerr << "[checkpoint trunk safety stop floor=" << gc.floorNum
                      << " screen=" << (int)gc.screenState << "]\n";
            break;
        }
        if (g_actFightProbeTrace)
            std::cerr << "[checkpoint trunk step=" << steps << " floor=" << gc.floorNum
                      << " room=" << (int)gc.curRoom << " screen=" << (int)gc.screenState << "]\n";
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;
            const Room room = gc.curRoom;
            const int floor = gc.floorNum;
            const int checkpointSims = actFightProbeCheckpointSims(sims, checkpointCount);
            double expected = 0.0;
            const auto options = possibleEncounterOptions(gc);
            std::vector<MonsterEncounter> optionEncounters;
            for (const auto &option : options) optionEncounters.push_back(option.encounter);
            const bool useEncounterNN = g_actFightProbeEncounterNN && checkpointCount == 0
                                     && !rootState.empty() && !optionEncounters.empty();
            const auto encounterPredictions = useEncounterNN
                ? queryOocEncounterPredictions(rootState, rootActionBits, rootScreen, rootAct,
                                               optionEncounters)
                : std::vector<OocEncounterPrediction>{};
            const bool lastCheckpoint = g_actFightProbeTermWin > 0.0
                && g_actFightProbeMaxCheckpoints > 0
                && checkpointCount + 1 >= g_actFightProbeMaxCheckpoints;
            double expectedWin = 0.0;
            for (int i = 0; i < (int)options.size(); ++i) {
                GameContext local = detachedCounterfactualCopy(gc);
                bool passed = false;
                int hp = local.curHp, maxHp = local.maxHp;
                double safety = -1.0;
                if (useEncounterNN && i < (int)encounterPredictions.size()
                    && encounterPredictions[i].winProbability >= 0.0) {
                    const auto &prediction = encounterPredictions[i];
                    passed = prediction.winProbability >= g_actFightProbePredictWinThreshold;
                    hp = std::max(1, std::min(local.maxHp,
                        (int)std::lround(prediction.hpFraction * local.maxHp)));
                    maxHp = std::max(1, local.maxHp);
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else if (g_actFightProbePredict) {
                    const auto prediction = predictCheckpointFight(local, options[i].encounter);
                    passed = prediction.predictedWin;
                    hp = prediction.endHpIfWin;
                    maxHp = prediction.maxHp;
                    // The model heads predict P(win) and E[end HP | win].
                    // Keep the oracle's loss penalty in the expected utility.
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else {
                    search::ScumSearchAgent2 fightAgent;
                    fightAgent.simulationCountBase = fightSims(local, checkpointSims);
                    fightAgent.rng = std::default_random_engine(
                        agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1))
                                  ^ (0xa0761d6478bd642fULL * (std::uint64_t)(floor + 1)));
                    BattleContext bc{}; bc.init(local, options[i].encounter);
                    fightAgent.playoutBattle(bc); bc.exitBattle(local);
                    passed = bc.outcome == Outcome::PLAYER_VICTORY;
                    hp = local.curHp;
                    maxHp = local.maxHp;
                    safety = passed ? nonlinearHpSafety(hp, maxHp) : -1.0;
                    // Terminal pricing: the post-fight branch state (HP already
                    // updated) is priced by the native win model in P(win)
                    // units, scale-compatible with the HP-safety sigmoid.
                    if (lastCheckpoint && passed && g_winNet.ok) {
                        const double pw = winNetPredict(richFeatureVec(local));
                        expectedWin += options[i].probability
                            * (local.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : pw);
                    }
                }
                expected += options[i].probability * safety;
                if (components) components->push_back({
                    floor, room, options[i].encounter, options[i].probability, passed,
                    hp, maxHp, safety,
                    std::pow(g_actFightProbeFloorDecay, std::max(0, floor - decisionFloor))
                        * options[i].probability * safety,
                    (g_actFightProbePredict || useEncounterNN) ? 0 : fightSims(local, checkpointSims),
                });
            }
            const double decay = std::pow(g_actFightProbeFloorDecay,
                                          std::max(0, floor - decisionFloor));
            utility += decay * expected;
            if (lastCheckpoint)
                utility += decay * g_actFightProbeTermWin * expectedWin;
            ++checkpointCount;

            // The final scored checkpoint needs no actual trunk battle: no
            // later deck/HP state can contribute to a capped objective.
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;

            // Advance only this one sampled trunk; future checkpoints are then
            // naturally weighted by the probability that the trunk reaches them.
            if (g_actFightProbePredict) {
                if (!applyPredictedCheckpointFight(gc, gc.info.encounter)) break;
            } else {
                trunkAgent.simulationCountBase = fightSims(gc, checkpointSims);
                // g_potionKeepValue is process-global. With saving disabled (the
                // deployed/pilot setting) its default is the same fixed value, so
                // avoid a needless shared write while branches run in parallel.
                // Dynamic potion saving remains sequential until that setting is
                // made thread-local in the combat searcher.
                if (g_potionSave) search::g_potionKeepValue = potionKeepValue(gc);
                BattleContext actual{}; actual.init(gc); trunkAgent.playoutBattle(actual); actual.exitBattle(gc);
            }
            if (room == Room::BOSS) break;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
                search::GameAction(2, 0).execute(gc);   // recall: take the ruby key
            } else {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.empty()) break;
                actions.front().execute(gc);
            }
        } else {
            trunkAgent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return utility;
}

static std::string csvQuote(const std::string &s) {
    std::string out = "\"";
    for (const char c : s) {
        if (c == '\"') out += "\"\"";
        else out += c;
    }
    return out + "\"";
}

static std::string actionDescription(const search::GameAction &action, const GameContext &gc) {
    std::ostringstream out;
    action.printDesc(out, gc);
    // A few event actions have no human-readable printer; retain their stable
    // encoded action bits rather than silently logging an empty legal action.
    return out.str().empty() ? "bits=" + std::to_string(action.bits) : out.str();
}

static std::string joinLegalActions(const std::vector<search::GameAction> &actions,
                                    const GameContext &gc) {
    std::ostringstream out;
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) out << " | ";
        out << i << ':' << actionDescription(actions[i], gc);
    }
    return out.str();
}

// Paired OOC supervision at the next real combat.  Unlike the all-act future
// evaluator, this deliberately stops each counterfactual branch at its first
// battle.  The branch then has two labels: what the ordinary baseline does
// against the concrete encounter, and the weighted result of fighting every
// encounter still possible at that checkpoint.
static std::string oocNextCombatHeader() {
    return "seed,decisionIdx,actionIdx,actionBits,action,legalActions,screen,act,floor,futures,"
           "actualWin,actualHp,allEncounterWin,allEncounterHp,encounterLabels,stateFeatures";
}

struct EncounterLabel {
    double probability = 0.0;
    double weightedWin = 0.0;
    double weightedHp = 0.0;
};

struct NextCombatLabel {
    double actualWin = 0.0, actualHp = 0.0;
    double allWin = 0.0, allHp = 0.0;
    int seen = 0;
    std::map<int, EncounterLabel> encounterLabels;
};

static bool advanceOocToNextBattle(GameContext &gc, int sims, std::uint64_t agentSeed,
                                   PathHistory path) {
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    for (int steps = 0; steps < 180 && gc.outcome == GameOutcome::UNDECIDED; ++steps) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            t_curPath = nullptr;
            return true;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // handled by the deployed rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return false;
}

static NextCombatLabel labelNextCombat(GameContext branch, int branchSims,
                                       std::uint64_t agentSeed) {
    NextCombatLabel label;
    PathHistory emptyPath;
    if (!advanceOocToNextBattle(branch, branchSims, agentSeed, emptyPath)) return label;
    label.seen = 1;
    const auto options = possibleEncounterOptions(branch);
    double weight = 0.0;
    for (int i = 0; i < (int)options.size(); ++i) {
        GameContext local = detachedCounterfactualCopy(branch);
        search::ScumSearchAgent2 fightAgent;
        fightAgent.simulationCountBase = fightSims(local, branchSims);
        fightAgent.rng = std::default_random_engine(
            agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1)));
        BattleContext bc{};
        bc.init(local, options[i].encounter);
        fightAgent.playoutBattle(bc);
        bc.exitBattle(local);
        const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
        const double hp = won ? local.curHp : 0.0;
        const double p = options[i].probability;
        label.allWin += p * (won ? 1.0 : 0.0);
        label.allHp += p * hp;
        weight += p;
        auto &el = label.encounterLabels[(int)options[i].encounter];
        el.probability += p;
        el.weightedWin += p * (won ? 1.0 : 0.0);
        el.weightedHp += p * hp;
    }
    if (weight > 0.0) {
        label.allWin /= weight;
        label.allHp /= weight;
    }

    // Concrete-encounter label from the ordinary baseline continuation.  This
    // is intentionally separate from the encounter-distribution label above.
    GameContext actual = detachedCounterfactualCopy(branch);
    search::ScumSearchAgent2 actualAgent;
    actualAgent.simulationCountBase = fightSims(actual, branchSims);
    actualAgent.rng = std::default_random_engine(agentSeed ^ 0xa0761d6478bd642fULL);
    BattleContext actualBattle{};
    actualBattle.init(actual);
    actualAgent.playoutBattle(actualBattle);
    actualBattle.exitBattle(actual);
    label.actualWin = actualBattle.outcome == Outcome::PLAYER_VICTORY ? 1.0 : 0.0;
    label.actualHp = label.actualWin ? actual.curHp : 0.0;
    return label;
}

static std::string runOocNextCombatSeed(std::uint64_t seed, int outerSims, int asc,
                                         int branchSims, int futures) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);
    PathHistory path;
    t_curPath = &path;
    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<search::GameAction> sampledActions;
    int sampledDecision = -1;
    int eligible = 0, decisionIdx = 0;
    int fightsLost = 0, fightsTotal = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) ++fightsLost;
            bc.exitBattle(gc);
        } else {
            const auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledActions = actions;
                    sampledDecision = decisionIdx;
                }
                ++decisionIdx;
            }
            if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14)
                search::GameAction(chooseMapAction(gc)).execute(gc);
            else if (gc.screenState == ScreenState::REWARDS) {
                auto &r = gc.info.rewardsContainer;
                if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
                else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
                else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                else                            serverCardRewardPolicy(gc);
            } else if (gc.screenState == ScreenState::SHOP_ROOM) shopVPolicy(gc);
            else if (inRemoveSelect) removeSelectVPolicy(gc);
            else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {}
            else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                     && gc.info.selectScreenType == CardSelectScreenType::UPGRADE)
                upgradeSelectWinPolicy(gc);
            else agent.stepOutOfCombatPolicy(gc);
        }
    }
    std::ostringstream out;
    if (sampled) {
        const std::string state = richRow(*sampled, sampledPath);
        const std::string legal = joinLegalActions(sampledActions, *sampled);
        const int nf = std::max(1, futures);
        for (int a = 0; a < (int)sampledActions.size(); ++a) {
            NextCombatLabel total;
            for (int f = 0; f < nf; ++f) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                sampledActions[a].execute(branch);
                const auto label = labelNextCombat(
                    std::move(branch), branchSims,
                    seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                         ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(sampledDecision + 31)));
                total.seen += label.seen;
                total.actualWin += label.actualWin;
                total.actualHp += label.actualHp;
                total.allWin += label.allWin;
                total.allHp += label.allHp;
                for (const auto &[encounter, el] : label.encounterLabels) {
                    auto &dst = total.encounterLabels[encounter];
                    dst.probability += el.probability;
                    dst.weightedWin += el.weightedWin;
                    dst.weightedHp += el.weightedHp;
                }
            }
            std::ostringstream encounterLabels;
            for (const auto &[encounter, el] : total.encounterLabels) {
                if (encounterLabels.tellp() > 0) encounterLabels << '|';
                const double prob = el.probability / nf;
                const double win = el.probability > 0.0 ? el.weightedWin / el.probability : 0.0;
                const double hp = el.probability > 0.0 ? el.weightedHp / el.probability : 0.0;
                encounterLabels << encounter << ':' << prob << ':' << win << ':' << hp;
            }
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledActions[a].bits
                << ',' << csvQuote(actionDescription(sampledActions[a], *sampled)) << ','
                << csvQuote(legal) << ',' << (int)sampled->screenState << ',' << sampled->act << ','
                << sampled->floorNum << ',' << nf << ',' << total.actualWin/nf << ','
                << total.actualHp/nf << ',' << total.allWin/nf << ',' << total.allHp/nf << ','
                << csvQuote(encounterLabels.str()) << ','
                << csvQuote(state) << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void oocNextCombatGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                             std::uint64_t seedOffset, int branchSims, int futures) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << oocNextCombatHeader() << '\n'; out.flush(); }
    std::cout << "oocnextgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " -> " << outfile << '\n';
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string rows = runOocNextCombatSeed(seedOffset+s, outerSims, asc,
                                                       branchSims, futures);
        #pragma omp critical(ooc_next_write)
        { out << rows; out.flush(); }
    }
}

static std::string serializeFightComponents(const std::vector<std::vector<CheckpointFightComponent>> &all) {
    std::ostringstream out;
    for (int future = 0; future < (int)all.size(); ++future) {
        if (future) out << ';';
        out << "f" << future << '=';
        for (int i = 0; i < (int)all[future].size(); ++i) {
            if (i) out << '|';
            const auto &c = all[future][i];
            out << c.floor << ':' << roomStrings[(int)c.room] << ':'
                << monsterEncounterStrings[(int)c.encounter]
                << ":p=" << c.probability << ":win=" << c.passed
                << ":hp=" << c.hp << '/' << c.maxHp
                << ":safety=" << c.safety << ":contrib=" << c.contribution
                << ":sims=" << c.sims;
        }
    }
    return out.str();
}

static bool initActFightProbeLog() {
    if (g_actFightProbeLogPath.empty()) return true;
    std::ifstream existing(g_actFightProbeLogPath);
    const bool needsHeader = !existing.good() || existing.peek() == std::ifstream::traits_type::eof();
    g_actFightProbeLog.open(g_actFightProbeLogPath, std::ios::app);
    if (!g_actFightProbeLog.is_open()) {
        std::cerr << "[all-acts checkpoint teacher log failed to open: " << g_actFightProbeLogPath << "]\n";
        return false;
    }
    if (needsHeader) {
        // stateFeatures is vFeatCsv(gc), whose stable schema is richStateHeader().
        g_actFightProbeLog
            << "seed,decisionIdx,act,floor,mapX,mapY,screen,knownBoss,maxCheckpoints,checkpointSims,actionIdx,action,legalActions,"
               "futures,futureSeeds,futureUtilities,meanUtility,sampleSd,standardError,"
               "checkpointComponents,stateFeatures\n";
        g_actFightProbeLog.flush();
    }
    std::cout << "[all-acts checkpoint teacher log: " << g_actFightProbeLogPath << "]\n";
    return true;
}

static void appendActFightProbeLog(const GameContext &gc, int decisionIdx,
                                   const std::vector<search::GameAction> &actions, int actionIdx,
                                   const std::vector<std::uint64_t> &futureSeeds,
                                   const std::vector<double> &utilities,
                                   const std::vector<std::vector<CheckpointFightComponent>> &components) {
    if (!g_actFightProbeLog.is_open()) return;
    double mean = 0.0;
    for (const double utility : utilities) mean += utility;
    mean /= std::max(1, (int)utilities.size());
    double sq = 0.0;
    for (const double utility : utilities) sq += (utility - mean) * (utility - mean);
    const double sampleSd = utilities.size() > 1 ? std::sqrt(sq / (utilities.size() - 1)) : 0.0;
    const double standardError = utilities.empty() ? 0.0 : sampleSd / std::sqrt((double)utilities.size());

    std::ostringstream seeds, values;
    for (int f = 0; f < (int)futureSeeds.size(); ++f) {
        if (f) { seeds << ';'; values << ';'; }
        seeds << futureSeeds[f];
        values << utilities[f];
    }
    const std::string action = actionDescription(actions[actionIdx], gc);
    std::lock_guard<std::mutex> lock(g_actFightProbeLogMutex);
    g_actFightProbeLog
        << gc.seed << ',' << decisionIdx << ',' << gc.act << ',' << gc.floorNum << ','
        << gc.curMapNodeX << ',' << gc.curMapNodeY << ',' << (int)gc.screenState << ','
        << csvQuote(monsterEncounterStrings[(int)gc.boss]) << ',' << g_actFightProbeMaxCheckpoints << ','
        << csvQuote(actFightProbeCheckpointSimsCsv()) << ',' << actionIdx << ','
        << csvQuote(action) << ',' << csvQuote(joinLegalActions(actions, gc)) << ','
        << utilities.size() << ',' << csvQuote(seeds.str()) << ',' << csvQuote(values.str()) << ','
        << mean << ',' << sampleSd << ',' << standardError << ','
        << csvQuote(serializeFightComponents(components)) << ',' << csvQuote(vFeatCsv(gc)) << '\n';
    g_actFightProbeLog.flush();
}

// All-acts experiment: extend the checkpointed objective from card rewards to
// every legal strategic action in Acts 1--3. This includes boss-relic choices:
// their resulting next-act state is scored at its next combat checkpoints.
static bool actFightProbeAllOocPolicy(GameContext &gc) {
    if (!g_actFightProbeAllOoc || gc.act < 1 || gc.act > 3) return false;
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;

    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    const int decisionIdx = t_actFightProbeDecisionIdx++;
    double bestScore = -1e100;
    int best = -1;
    std::vector<double> scores(actions.size(), -1e100);
    std::vector<bool> valid(actions.size(), false);
    for (int a = 0; a < (int)actions.size(); ++a) valid[a] = actions[a].isValidAction(gc);

    struct BranchResult {
        std::uint64_t seed = 0;
        double utility = 0.0;
        std::vector<CheckpointFightComponent> components;
    };
    const int futures = g_actFightProbeFutures;
    std::vector<BranchResult> branches(actions.size() * futures);
    const bool parallelBranches = g_actFightProbeParallelBranches && !g_actFightProbeTrace
                                  && !g_potionSave;

    // Each branch owns its GameContext, RNG, combat searchers, TCP connection
    // (t_vSock is thread-local), and output slot.  Candidate-independent seeds
    // preserve common random numbers exactly as in the serial oracle.
    #pragma omp parallel for schedule(dynamic) if(parallelBranches)
    for (int task = 0; task < (int)branches.size(); ++task) {
        const int a = task / futures;
        const int f = task % futures;
        t_actFightProbeActionIdx = a;
        t_actFightProbeFutureIdx = f;
        const std::uint64_t branchSeed = gc.seed
            ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
            ^ (0x94d049bb133111ebULL * (std::uint64_t)(gc.floorNum + 97 * gc.curMapNodeY));
        BranchResult &result = branches[task];
        result.seed = branchSeed;
        if (!valid[a]) continue;
        GameContext branch = detachedCounterfactualCopy(gc);
        // Resample before the immediate action: a map choice can create its
        // next battle immediately, and it is hidden information too.
        resampleRemainingActEncounters(branch, branchSeed);
        actions[a].execute(branch);
        result.utility = checkpointedActFightUtility(
            std::move(branch), g_actFightProbeSims, branchSeed, basePath, gc.floorNum,
            vFeatCsv(gc), actions[a].bits, (int)gc.screenState, gc.act,
            &result.components);
    }

    // A serial branch temporarily installs its copied path for server feature
    // parity and clears it on return. Restore the live path before emitting the
    // teacher state/log rows below.
    t_curPath = savedPath;

    // Reduce in fixed action/future order. This retains deterministic scores,
    // logs, and tie-breaking independent of OpenMP scheduling.
    for (int a = 0; a < (int)actions.size(); ++a) {
        if (!valid[a]) continue;
        double total = 0.0;
        std::vector<std::uint64_t> futureSeeds;
        std::vector<double> futureUtilities;
        std::vector<std::vector<CheckpointFightComponent>> components;
        for (int f = 0; f < futures; ++f) {
            const BranchResult &result = branches[a * futures + f];
            futureSeeds.push_back(result.seed);
            futureUtilities.push_back(result.utility);
            components.push_back(result.components);
            total += result.utility;
        }
        scores[a] = total / std::max(1, futures);
        appendActFightProbeLog(gc, decisionIdx, actions, a, futureSeeds, futureUtilities, components);
        if (scores[a] > bestScore) { bestScore = scores[a]; best = a; }
    }
    if (best < 0) { t_curPath = savedPath; return false; }
    if (g_actFightProbeMargin > 0.0) {
        double second = -1e100;
        for (int a = 0; a < (int)actions.size(); ++a) {
            if (!valid[a] || a == best) continue;
            if (scores[a] > second) second = scores[a];
        }
        if (bestScore - second < g_actFightProbeMargin) {
            if (g_actFightProbeTrace)
                std::cerr << "[all-ooc act-fight margin " << bestScore - second
                          << " < " << g_actFightProbeMargin << " -> fallback]\n";
            t_curPath = savedPath;
            return false;
        }
    }
    if (g_actFightProbeTrace) {
        std::cerr << "[all-ooc act-fight floor=" << gc.floorNum << " screen="
                  << (int)gc.screenState << ']';
        for (int a = 0; a < (int)actions.size(); ++a) {
            std::ostringstream desc; actions[a].printDesc(desc, gc);
            std::cerr << ' ' << desc.str() << '=' << scores[a];
        }
        std::cerr << " -> "; actions[best].printDesc(std::cerr, gc); std::cerr << '\n';
    }
    actions[best].execute(gc);
    t_curPath = savedPath;
    return true;
}

// ---------------------------------------------------------------------------
// PAIRED PATH COUNTERFACTUALS: uniformly reservoir-sample one genuine branching
// map decision from each source run, then finish every legal child from the
// identical parent state with common agent/game RNG. This supplies direct route
// action values rather than trying to infer causal alternatives from trajectory
// state values generated by the heuristic policy.
static std::string richStateHeader();
static std::string pathCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateX,heuristicX," + richStateHeader()
         + ",branchWon,branchFloor,branchHp";
}

static std::string runPathCounterfactualSeed(std::uint64_t seed, int outerSims, int asc,
                                             int branchSims, int futures, std::uint64_t futureSalt) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 17);
    PathHistory path;
    t_curPath = &path;

    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<int> sampledCandidates;
    int sampledDecision = -1, sampledHeuristic = -1;
    int eligible = 0, decisionIdx = 0;
    using RT = search::GameAction::RewardsActionType;

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            std::vector<int> candidates;
            if (gc.curMapNodeY < 0) {
                for (const MapNode &node : gc.map->nodes[0]) if (node.edgeCount > 0) candidates.push_back(node.x);
            } else {
                const MapNode &node = gc.map->getNode(gc.curMapNodeX, gc.curMapNodeY);
                for (int i = 0; i < node.edgeCount; ++i) candidates.push_back(node.edges[i]);
            }
            const int heuristic = chooseMapAction(gc);
            if (candidates.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledCandidates = candidates;
                    sampledDecision = decisionIdx;
                    sampledHeuristic = heuristic;
                }
                ++decisionIdx;
            }
            search::GameAction(heuristic).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // current deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::ostringstream out;
    if (sampled) {
        const int na = static_cast<int>(sampledCandidates.size());
        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
        const int nf = std::max(1, futures);
        std::vector<int> validFutures(na, 0);
        for (int f = 0; f < nf; ++f) {
            const std::uint64_t futureSeed = seed
                ^ (0xa24baed4963ee407ULL * static_cast<std::uint64_t>(sampledDecision * nf + f + 1))
                ^ (0x9e3779b97f4a7c15ULL * futureSalt);
            for (int a = 0; a < na; ++a) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                search::GameAction(sampledCandidates[a]).execute(branch);
                const OocCounterfactualResult result = finishOocCounterfactual(
                    branch, branchSims, futureSeed, sampledPath, -1, false);
                if (!result.valid) {
                    ++g_trainingInvalidBranches;
                    continue;
                }
                bw[a] += result.won; bf[a] += result.floor; bh[a] += result.hp;
                ++validFutures[a];
            }
        }
        t_curPath = &sampledPath;
        const std::string state = richRow(*sampled, sampledPath);
        for (int a = 0; a < na; ++a) {
            if (!search::hasCompleteCounterfactualFutureSet(validFutures[a], nf, nf)) continue;
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledCandidates[a] << ','
                << sampledHeuristic << ',' << state << ',' << bw[a]/nf << ',' << bf[a]/nf << ','
                << bh[a]/nf << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void pathCounterfactualGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                                  std::uint64_t seedOffset, int branchSims, int futures,
                                  std::uint64_t futureSalt = 0) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << pathCounterfactualHeader() << '\n'; out.flush(); }
    std::cout << "pathcfgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " futureSalt " << futureSalt
              << " threads " << numThreads() << " -> " << outfile << '\n';
    auto start = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runPathCounterfactualSeed(seedOffset+s, outerSims, asc,
                                                                branchSims, futures, futureSalt);
        #pragma omp critical(path_cf_write)
        {
            out << generated; out.flush();
            rows += std::count(generated.begin(), generated.end(), '\n');
            ++done;
            if (done % 25 == 0 || done == nSeeds) {
                const double elapsed = std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-start).count();
                std::printf("  %d/%d runs, %lld action rows, %.0fs (%.2fs/run)\n",
                            done, nSeeds, rows, elapsed, elapsed/done);
                std::fflush(stdout);
            }
        }
    }
}

static bool genuineRestVsSmith(const GameContext &gc) {
    return !gc.hasRelic(RelicId::COFFEE_DRIPPER)
        && !gc.relics.has(RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
}

static std::string richStateHeader() {
    std::string h = richHeader();
    const std::string prefix = "seed,";
    if (h.rfind(prefix, 0) == 0) h.erase(0, prefix.size());
    const std::string labels = ",won,finalFloor,endHp";
    const size_t p = h.rfind(labels); if (p != std::string::npos) h.erase(p);
    return h;
}

// ---------------------------------------------------------------------------
// E2c: matched RAW / POST snapshots of survived ordinary/elite/act-1-2 boss
// combats at the exact combat-terminal boundary.  RAW fires inside
// BattleContext::exitBattle immediately after persistent-transfer and before
// regainControl()/reward generation; POST fires at the REWARDS screen after all
// non-card rewards are drained, immediately before the first card pick/skip.
// Only the real run-loop exit arms the BattleContext hook (see runFullRunOOC),
// so copied/counterfactual exits cannot produce rows.
// ---------------------------------------------------------------------------
static std::string e2cRoomName(int room) {
    switch ((Room)room) {
        case Room::MONSTER: return "MONSTER";
        case Room::ELITE: return "ELITE";
        case Room::BOSS: return "BOSS";
        default: return "OTHER";
    }
}

static std::string e2cExplicitRelics(const GameContext &gc) {
    std::vector<int> has(kNumRelics, 0), data(kNumRelics, 0);
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) { has[id] = 1; data[id] = ri.data; }   // exact signed data
    }
    std::ostringstream out;
    for (int i = 0; i < kNumRelics; ++i) { if (i) out << ','; out << has[i]; }      // relic_has_<id>
    for (int i = 0; i < kNumRelics; ++i) out << ',' << data[i];                     // relic_data_<id>
    return out.str();
}

static std::string e2cHeader() {
    std::ostringstream out;
    out << "seed,fight_index,boundary,room_type,encounter_id," << richStateHeader();
    for (int i = 0; i < kNumRelics; ++i) out << ",relic_has_" << i;
    for (int i = 0; i < kNumRelics; ++i) out << ",relic_data_" << i;
    out << ",won,finalFloor,endHp\n";
    return out.str();
}

static void e2cBeginFight(int fightIndex, const GameContext &gc, const BattleContext &bc) {
    if (!t_e2c) return;
    t_e2c->current = nullptr;
    if (gc.curRoom != Room::MONSTER && gc.curRoom != Room::ELITE && gc.curRoom != Room::BOSS) return;
    if (gc.curRoom == Room::BOSS && gc.act > 2) return;   // exclude act-3/4 terminal boss
    E2cFight f;
    f.room = (int)gc.curRoom; f.encounter = (int)bc.encounter;
    f.index = fightIndex;
    t_e2c->fights.push_back(std::move(f));
    t_e2c->current = &t_e2c->fights.back();
}

static void e2cRawObserver(const BattleContext &bc, GameContext &gc) {
    if (t_e2c && t_e2c->current && bc.outcome == Outcome::PLAYER_VICTORY) {
        t_e2c->current->raw = richRow(gc, *t_e2c->path);
        t_e2c->current->rawRelics = e2cExplicitRelics(gc);
        t_e2c->current->rawSeen = true;
        auto &s = t_e2c->roomStats[t_e2c->current->room == (int)Room::MONSTER ? 0
                                  : t_e2c->current->room == (int)Room::ELITE ? 1 : 2];
        ++s.eligible;
        ++s.raw;
    }
}

static void e2cCapturePost(GameContext &gc) {
    if (!t_e2c || !t_e2c->current || t_e2c->current->postSeen) return;
    auto &r = gc.info.rewardsContainer;
    t_e2c->current->screenTrace += "REWARDS(" + std::to_string(r.relicCount) + "," +
        std::to_string(r.cardRewardCount) + ");";
    if (t_e2c->current->rewardRelics.empty()) {
        for (int i = 0; i < r.relicCount; ++i) {
            if (i) t_e2c->current->rewardRelics += ";";
            t_e2c->current->rewardRelics += std::to_string((int)r.relics[i]);
        }
    }
    t_e2c->current->pendingCards = r.cardRewardCount;
    if (gc.screenState != ScreenState::REWARDS || r.goldRewardCount || r.relicCount ||
        r.potionCount || (g_collectKeys && (r.emeraldKey || r.sapphireKey)) ||
        r.cardRewardCount == 0) return;
    t_e2c->current->post = richRow(gc, *t_e2c->path);
    t_e2c->current->postRelics = e2cExplicitRelics(gc);
    t_e2c->current->postSeen = true;
    auto &s = t_e2c->roomStats[t_e2c->current->room == (int)Room::MONSTER ? 0
                              : t_e2c->current->room == (int)Room::ELITE ? 1 : 2];
    ++s.post;
}

static std::string e2cRunRows(const E2cCapture &cap, bool won, int finalFloor, int endHp) {
    std::ostringstream out;
    for (const auto &f : cap.fights) {
        if (!f.rawSeen && !f.postSeen) continue;
        const std::string meta = std::string(e2cRoomName(f.room)) + ',' + std::to_string(f.encounter) + ',';
        if (f.rawSeen)
            out << cap.seed << ',' << f.index << ",RAW," << meta << f.raw << ',' << f.rawRelics
                << ',' << (won ? 1 : 0) << ',' << finalFloor << ',' << endHp << '\n';
        if (f.postSeen)
            out << cap.seed << ',' << f.index << ",POST," << meta << f.post << ',' << f.postRelics
                << ',' << (won ? 1 : 0) << ',' << finalFloor << ',' << endHp << '\n';
    }
    return out.str();
}

// E2c RAW canonical feature extraction.  This is deliberately independent of
// the legacy rich model's selected-feature map: T-raw contains the E2c
// explicit relic ownership/data blocks and excludes the rich r* encoding and
// all hidden future fields.  Keep this classifier in lockstep with
// tools/analyze_postcombat_raw_terminal.py::{manifest,t_features}.
static std::vector<std::string> splitCsvNames(const std::string &s) {
    std::vector<std::string> out; std::string cur;
    // std::getline removes '\n' but leaves the '\r' in a normal CRLF CSV.
    // Ignore it here so production parity fixtures are portable between the
    // Windows exporter and the Linux native test binary.
    for (char c : s) { if (c == ',') { out.push_back(cur); cur.clear(); } else if (c != '\r') cur += c; }
    if (!cur.empty()) out.push_back(cur);
    return out;
}
static bool e2cObservableName(const std::string &n) {
    static const std::unordered_set<std::string> exact = {
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize", "potionChance",
        "cardRarityFactor", "blueKey", "greenKey", "redKey", "potionCount", "potionCapacity", "bossId",
        "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure", "bottledAtkId",
        "bottledSkillId", "bottledPowId", "curMapX", "curMapY", "room_type", "encounter_id", "hpFrac"};
    if (exact.count(n)) return true;
    auto digits = [](const std::string &v, const char *prefix) {
        const size_t p = std::strlen(prefix); if (v.rfind(prefix, 0) != 0 || v.size() == p) return false;
        return std::all_of(v.begin() + p, v.end(), [](unsigned char c) { return std::isdigit(c); });
    };
    return digits(n, "d") || digits(n, "u") || digits(n, "pot") ||
           n.rfind("fmD", 0) == 0 || n.rfind("fmC", 0) == 0 ||
           n.rfind("relic_has_", 0) == 0 || n.rfind("relic_data_", 0) == 0;
}
static const std::vector<std::string> &e2cRawCanonicalNames() {
    static const std::vector<std::string> names = [] {
        const std::unordered_set<std::string> meta = {"seed", "fight_index", "boundary", "room_type", "encounter_id"};
        const std::unordered_set<std::string> hidden = {"nextEliteId", "nextFight0", "nextFight1", "nextFight2",
                                                         "remElites", "remFights", "monOffset", "eliteOffset"};
        std::vector<std::string> out;
        for (const std::string &n : splitCsvNames(e2cHeader())) {
            if (n == "won" || n == "finalFloor" || n == "endHp" || hidden.count(n)) continue;
            if (meta.count(n) && n != "room_type" && n != "encounter_id") continue;
            if (!e2cObservableName(n)) continue;
            out.push_back(n);
        }
        return out;
    }();
    return names;
}
static const std::unordered_map<std::string, int> &e2cRawIdxMap() {
    static const std::unordered_map<std::string, int> map = [] {
        std::unordered_map<std::string, int> out;
        const auto &names = e2cRawCanonicalNames();
        for (int i = 0; i < (int)names.size(); ++i) out.emplace(names[i], i);
        return out;
    }();
    return map;
}
static std::vector<float> e2cRawCanonicalVec(const GameContext &gc, const PathHistory &path,
                                               Room room, MonsterEncounter encounter) {
    std::unordered_map<std::string, float> values;
    const auto rNames = splitCsvNames(richStateHeader());
    const auto rValues = splitCsvNames(richRow(gc, path));
    if (rNames.size() != rValues.size()) return {};
    for (size_t i = 0; i < rNames.size(); ++i) values.emplace(rNames[i], std::strtof(rValues[i].c_str(), nullptr));
    values["room_type"] = room == Room::MONSTER ? 0.f : room == Room::ELITE ? 1.f : room == Room::BOSS ? 2.f : -1.f;
    values["encounter_id"] = (float)(int)encounter;
    const auto relicValues = splitCsvNames(e2cExplicitRelics(gc));
    if (relicValues.size() != (size_t)(2 * kNumRelics)) return {};
    for (int i = 0; i < kNumRelics; ++i) values["relic_has_" + std::to_string(i)] = std::strtof(relicValues[i].c_str(), nullptr);
    for (int i = 0; i < kNumRelics; ++i) values["relic_data_" + std::to_string(i)] = std::strtof(relicValues[kNumRelics + i].c_str(), nullptr);
    std::vector<float> out; out.reserve(e2cRawCanonicalNames().size());
    for (const std::string &name : e2cRawCanonicalNames()) {
        const auto it = values.find(name); if (it == values.end()) return {};
        out.push_back(it->second);
    }
    return out;
}

// Exact semantic projection for a terminal diagnostic continuation.  The copy
// executes the canonical exitBattle transfer.  Its temporary hook captures the
// RAW state after cards/relics/HP/potions/gold transfer and before reward
// generation, exactly where E2c sampled it; the live run and its RNG remain
// untouched.
static bool e2cProjectTerminalRaw(const GameContext &battleEntry, const PathHistory &path,
                                  Room room, MonsterEncounter encounter, const BattleContext &terminal,
                                  std::vector<float> &out) {
    if (terminal.outcome != Outcome::PLAYER_VICTORY) return false;
    GameContext post = battleEntry;
    bool captured = false;
    auto previous = g_onBattleExitPersistent;
    g_onBattleExitPersistent = [&](const BattleContext &, GameContext &atRaw) {
        out = e2cRawCanonicalVec(atRaw, path, room, encounter); captured = !out.empty();
    };
    terminal.exitBattle(post);
    g_onBattleExitPersistent = previous;
    return captured;
}

// Regression: the shadow projection must remain equivalent to an independently
// captured E2c RAW boundary from a real exitBattle call.  Cover every transfer
// family that is easy to omit when BattleContext::exitBattle changes.
static int e2cRawProjectionParityTest() {
    auto fail = [](const std::string &why) {
        std::cerr << "e2c_projection_parity FAIL: " << why << '\n'; return 1;
    };
    GameContext entry(CharacterClass::IRONCLAD, 0xE2C2026u, 0);
    // The production run has a post-battle continuation installed.  The
    // fixture intentionally stops at the RAW hook, so a no-op keeps the
    // canonical exitBattle call valid without generating rewards.
    entry.regainControlAction = [](GameContext &) {};
    entry.act = 2; entry.floorNum = 23; entry.curRoom = Room::ELITE;
    entry.curHp = 20; entry.maxHp = 91; entry.gold = 101; entry.potionChance = 37;
    entry.relics.add({RelicId::MEAT_ON_THE_BONE, 0});
    entry.relics.add({RelicId::HAPPY_FLOWER, 1});
    entry.relics.add({RelicId::NEOWS_LAMENT, 3});
    entry.relics.add({RelicId::LIZARD_TAIL, 1});
    entry.relics.add({RelicId::POTION_BELT, 0});
    entry.potionCapacity = 5;
    entry.potionCount = 2;
    entry.potions[0] = Potion::BLOOD_POTION;
    entry.potions[1] = Potion::DEXTERITY_POTION;
    for (int i = 2; i < 5; ++i) entry.potions[i] = Potion::EMPTY_POTION_SLOT;

    BattleContext terminal;
    terminal.init(entry, MonsterEncounter::GREMLIN_NOB);
    terminal.outcome = Outcome::PLAYER_VICTORY;
    terminal.player.curHp = 20; terminal.player.maxHp = 91; terminal.player.gold = 137;
    terminal.potionCapacity = 5; terminal.potionCount = 2;
    terminal.potions[0] = Potion::STRENGTH_POTION;
    terminal.potions[1] = Potion::FIRE_POTION;
    for (int i = 2; i < 5; ++i) terminal.potions[i] = Potion::EMPTY_POTION_SLOT;
    terminal.player.happyFlowerCounter = 2;
    terminal.player.setHasRelic<RelicId::LIZARD_TAIL>(false); // consumed in this terminal state

    PathHistory path;
    std::vector<float> projected;
    if (!e2cProjectTerminalRaw(entry, path, Room::ELITE, MonsterEncounter::GREMLIN_NOB, terminal, projected))
        return fail("projection did not capture terminal victory");

    // Canonical E2c capture: a separate entry copy takes the normal
    // BattleContext::exitBattle path and is observed at the production hook.
    std::vector<float> canonical;
    GameContext actual = entry;
    const auto previous = g_onBattleExitPersistent;
    g_onBattleExitPersistent = [&](const BattleContext &, GameContext &atRaw) {
        canonical = e2cRawCanonicalVec(atRaw, path, Room::ELITE, MonsterEncounter::GREMLIN_NOB);
    };
    terminal.exitBattle(actual);
    g_onBattleExitPersistent = previous;
    if (canonical.empty() || projected.size() != canonical.size()) return fail("canonical capture shape");
    for (size_t i = 0; i < projected.size(); ++i)
        if (projected[i] != canonical[i]) return fail("projected vector differs at feature " + e2cRawCanonicalNames()[i]);

    const auto &idx = e2cRawIdxMap();
    const auto require = [&](const std::string &name, float expected) {
        const auto it = idx.find(name);
        return it != idx.end() && projected[it->second] == expected;
    };
    // HP includes Burning Blood then Meat on the Bone healing; max HP/gold and
    // potion slots/count/chance arrive from the terminal BattleContext.
    if (!require("curHp", 38) || !require("maxHp", 91) || !require("gold", 137) ||
        !require("potionCount", 2) || !require("potionCapacity", 5) || !require("potionChance", 37) ||
        !require("pot" + std::to_string((int)Potion::STRENGTH_POTION), 1) ||
        !require("pot" + std::to_string((int)Potion::FIRE_POTION), 1))
        return fail("HP, gold, or potion transfer");
    const int happy = (int)RelicId::HAPPY_FLOWER, lizard = (int)RelicId::LIZARD_TAIL, lament = (int)RelicId::NEOWS_LAMENT;
    if (!require("relic_has_" + std::to_string(happy), 1) || !require("relic_data_" + std::to_string(happy), 2) ||
        !require("relic_has_" + std::to_string(lizard), 1) || !require("relic_data_" + std::to_string(lizard), 0) ||
        !require("relic_has_" + std::to_string(lament), 1) || !require("relic_data_" + std::to_string(lament), 2) ||
        !require("room_type", 1) || !require("encounter_id", (float)(int)MonsterEncounter::GREMLIN_NOB))
        return fail("relic counter, room, or encounter transfer");
    std::cout << "e2c_projection_parity PASS features=" << projected.size() << " max_abs_error=0\n";
    return 0;
}

static void e2cGen(int nSeeds, int sims, int asc, const std::string &outfile,
                   long long seedOffset = 0) {
    trainingCampaignStart();
    for (auto &row : g_e2cCounts) for (auto &v : row) v = 0;
    const bool append = seedOffset > 0;
    std::cout << "e2cgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << e2cHeader(); f.flush(); }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, true, /*e2cCapture=*/true);
        std::string rows = std::move(t_e2cRows);
        #pragma omp critical(e2c_write)
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0 || done == nSeeds) {
                const double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.2fs/run)\n", done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld E2c rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d "
                "branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), rowCount, outfile.c_str());
    for (int i = 0; i < 3; ++i)
        std::printf("e2c accounting room=%s eligible=%lld raw=%lld post=%lld pairs=%lld raw_only=%lld post_only=%lld\n",
                    i == 0 ? "MONSTER" : i == 1 ? "ELITE" : "BOSS",
                    g_e2cCounts[i][0].load(), g_e2cCounts[i][1].load(), g_e2cCounts[i][2].load(),
                    g_e2cCounts[i][3].load(), g_e2cCounts[i][4].load(), g_e2cCounts[i][5].load());
    writeTrainingProvenance(outfile, "e2cgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc);
    std::ofstream schema(outfile + ".schema.json");
    if (schema)
        schema << "{\n  \"schema_version\": \"e2c-v2\",\n"
               << "  \"raw_primary_retains_incomplete_pairs\": true,\n"
               << "  \"matched_arms_require_complete_raw_post_pairs\": true\n}\n";
}

static std::string restCounterfactualHeader() {
    return "seed,restIdx," + richStateHeader()
         + ",restWon,restFloor,restHp,smithWon,smithFloor,smithHp";
}

static std::string cardCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateId,candidateUpgraded," + richStateHeader()
         + ",branchFutures,branchWon,branchFloor,branchHp"
         + ",branchNextCombatSeen,branchNextCombatPassed"
         + ",branchNextEliteSeen,branchNextElitePassed"
         + ",branchNextBossSeen,branchNextBossPassed,branchFutureComplete";
}

struct DataGen2Rows {
    std::string meta;
    std::string rest;
    std::string card;
};

static DataGen2Rows
runDataGen2Seed(std::uint64_t seed, int sims, int asc, double epsilon,
                int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                int cardCfSims = 0, int cardCfFights = 3, int cardCfFutures = 1,
                int cardCfStride = 1, int cardCfMaxPerRun = 0,
                std::uint64_t cardCfFutureSalt = 0, int cardCfAdaptiveMaxFutures = 0,
                double cardCfAdaptiveGap = 5.0) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    PathHistory path;
    t_curPath = &path;
    std::vector<std::string> rows;
    std::vector<std::string> restRows;
    std::vector<std::string> cardRows;
    int restIdx = 0;
    int cardDecisionIdx = 0, cardCollected = 0;
    using RT = search::GameAction::RewardsActionType;
    // Data is generated with the CURRENT BEST play policy (server card picks
    // skip@g_cardSkipThresh + heuristic path + shop-V), so labels & the state
    // distribution match how we actually play. eps-greedy random card picks keep
    // deck coverage broad. Requires v_server.py running.
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(richRow(gc, path));                 // comprehensive snapshot
                // Softmax-sample each card reward by its V-marginal (temp g_dgTemp)
                // + uniform floor `epsilon`: data spreads over good-but-varied play
                // while every card still gets sampled sometimes (unbiased coverage).
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();

                    // Direct action labels: from the identical pre-choice state,
                    // finish the run after every offered card and after skip.  A
                    // deterministic hash samples decision positions uniformly;
                    // the per-run cap prevents one long run from dominating cost.
                    const int stride = std::max(1, cardCfStride);
                    const bool sampleCardCf = cardCfSims > 0 && cardCfMaxPerRun > 0
                        && cardCollected < cardCfMaxPerRun
                        && ((seed * 11400714819323198485ULL
                             + (std::uint64_t)cardDecisionIdx * 0x9e3779b97f4a7c15ULL)
                            % (std::uint64_t)stride) == 0;
                    if (sampleCardCf) {
                        const int na = nc + 1;                 // offered cards + skip
                        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
                        std::vector<double> ncs(na, 0.0), ncp(na, 0.0);
                        std::vector<double> nes(na, 0.0), nep(na, 0.0);
                        std::vector<double> nbs(na, 0.0), nbp(na, 0.0), nfc(na, 0.0);
                        const int futures = std::max(1, cardCfFutures);
                        const int maxFutures = std::max(futures, cardCfAdaptiveMaxFutures);
                        int usedFutures = 0;
                        bool cardCfInvalid = false;
                        for (int f = 0; f < maxFutures; ++f) {
                            const std::uint64_t futureSeed = seed
                                ^ (0xd1b54a32d192ed03ULL
                                   * (std::uint64_t)(cardDecisionIdx * futures + f + 1))
                                ^ (0x9e3779b97f4a7c15ULL * cardCfFutureSalt);
                            for (int a = 0; a < na; ++a) {
                                const int choice = a < nc ? a : 5;
                                GameContext branch = detachedCounterfactualCopy(gc);
                                search::GameAction(RT::CARD, rIdx, choice).execute(branch);
                                FutureFightProbe probe;
                                OocCounterfactualResult br = finishOocCounterfactual(
                                    branch, cardCfSims, futureSeed, path,
                                    std::max(1, cardCfFights), true, &probe);
                                t_curPath = &path;
                                if (!br.valid) {
                                    ++g_trainingInvalidBranches;
                                    cardCfInvalid = true;
                                    break;
                                }
                                bw[a] += br.won;
                                bf[a] += br.floor;
                                bh[a] += br.hp;
                                ncs[a] += probe.nextCombatSeen;
                                ncp[a] += probe.nextCombatPassed;
                                nes[a] += probe.nextEliteSeen;
                                nep[a] += probe.nextElitePassed;
                                nbs[a] += probe.nextBossSeen;
                                nbp[a] += probe.nextBossPassed;
                                nfc[a] += probe.completed;
                            }
                            if (cardCfInvalid) break;
                            usedFutures = f + 1;
                            if (usedFutures >= futures) {
                                std::vector<double> runningScore(na);
                                for (int a = 0; a < na; ++a)
                                    runningScore[a] = (bf[a] + 10.0 * bw[a]) / usedFutures;
                                std::nth_element(runningScore.begin(), runningScore.end()-2,
                                                 runningScore.end());
                                const double gap = runningScore.back()
                                                   - *(runningScore.end()-2);
                                if (usedFutures >= maxFutures || gap > cardCfAdaptiveGap) break;
                            }
                        }
                        if (!cardCfInvalid
                            && search::hasCompleteCounterfactualFutureSet(usedFutures, usedFutures,
                                                                            futures)) {
                            const std::string state = richRow(gc, path);
                            for (int a = 0; a < na; ++a) {
                                const bool skip = a == nc;
                                const Card *card = skip ? nullptr : &r.cardRewards[rIdx][a];
                                std::ostringstream cr;
                                cr << seed << ',' << cardDecisionIdx << ',' << (skip ? 5 : a) << ','
                                   << (skip ? -1 : (int)card->getId()) << ','
                                   << (skip ? 0 : (card->isUpgraded() ? 1 : 0)) << ',' << state << ','
                                   << usedFutures << ',' << bw[a]/usedFutures << ','
                                   << bf[a]/usedFutures << ',' << bh[a]/usedFutures << ','
                                   << ncs[a]/usedFutures << ',' << ncp[a]/usedFutures << ','
                                   << nes[a]/usedFutures << ',' << nep[a]/usedFutures << ','
                                   << nbs[a]/usedFutures << ',' << nbp[a]/usedFutures << ','
                                   << nfc[a]/usedFutures;
                                cardRows.push_back(cr.str());
                            }
                        }
                        ++cardCollected;
                    }
                    ++cardDecisionIdx;

                    std::vector<double> marg = vQueryMarginals(gc, rIdx);
                    int action;
                    if ((int)marg.size() != nc) {                    // server error -> uniform incl skip
                        action = std::uniform_int_distribution<int>(0, nc)(ex);
                        if (action >= nc) action = 5;
                    } else if (*std::max_element(marg.begin(), marg.end()) < g_cardSkipThresh) {
                        action = 5;                                  // no card improves the deck -> skip (as exploit)
                    } else {
                        action = sampleCardSoftmax(marg, g_dgTemp, epsilon, ex);  // softmax which card
                    }
                    search::GameAction(RT::CARD, rIdx, action).execute(gc);
                }
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);                                       // best shop policy (V-knapsack)
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);                               // shop removal target
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF outer rest seed=" << seed << " idx=" << restIdx << " floor=" << gc.floorNum << "\n";
            if (restCfSims > 0 && genuineRestVsSmith(gc)
                && restCfStride > 0 && (seed % (std::uint64_t)restCfStride) == 0) {
                double rw = 0, rf = 0, rh = 0, sw = 0, sf = 0, sh = 0;
                const int futures = std::max(1, restCfFutures);
                int validFutures = 0;
                bool restCfInvalid = false;
                for (int f = 0; f < futures; ++f) {
                    const std::uint64_t futureSeed = seed ^ (0x9e3779b97f4a7c15ULL
                                                    * (std::uint64_t)(restIdx * futures + f + 1));
                    GameContext gr = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply rest valid=" << search::GameAction(0, 0).isValidAction(gr) << "\n";
                    search::GameAction(0, 0).execute(gr);       // rest
                    OocCounterfactualResult rr = finishOocCounterfactual(
                        gr, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF rest branch done floor=" << rr.floor << "\n";
                    t_curPath = &path;
                    GameContext gs = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply smith valid=" << search::GameAction(1, 0).isValidAction(gs) << "\n";
                    search::GameAction(1, 0).execute(gs);       // smith
                    if (gs.screenState == ScreenState::CARD_SELECT
                        && gs.info.selectScreenType == CardSelectScreenType::UPGRADE)
                        upgradeSelectWinPolicy(gs);
                    OocCounterfactualResult sr = finishOocCounterfactual(
                        gs, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF smith branch done floor=" << sr.floor << "\n";
                    t_curPath = &path;
                    if (!rr.valid || !sr.valid) {
                        g_trainingInvalidBranches += !rr.valid + !sr.valid;
                        restCfInvalid = true;
                        break;
                    }
                    rw += rr.won; rf += rr.floor; rh += rr.hp;
                    sw += sr.won; sf += sr.floor; sh += sr.hp;
                    ++validFutures;
                }
                if (!restCfInvalid
                    && search::hasCompleteCounterfactualFutureSet(validFutures, validFutures,
                                                                    futures)) {
                    std::ostringstream cr;
                    cr << seed << ',' << restIdx << ',' << richRow(gc, path)
                       << ',' << rw/validFutures << ',' << rf/validFutures << ',' << rh/validFutures
                       << ',' << sw/validFutures << ',' << sf/validFutures << ',' << sh/validFutures;
                    restRows.push_back(cr.str());
                }
                ++restIdx;
            }
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply deployed rest policy\n";
            if (!restWinPolicy(gc)) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (!actions.empty()) actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED))
        return {};
    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum, endHp = gc.curHp;
    std::ostringstream o, ro, co;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << ',' << endHp << '\n';
    for (const auto &rr : restRows) ro << rr << '\n';
    for (const auto &cr : cardRows) co << cr << '\n';
    return {o.str(), ro.str(), co.str()};
}

static void dataGen2(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                     long long seedOffset = 0, const std::string &restOut = "",
                     int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                     const std::string &cardOut = "", int cardCfSims = 0,
                     int cardCfFights = 3, int cardCfFutures = 1, int cardCfStride = 1,
                     int cardCfMaxPerRun = 0, std::uint64_t cardCfFutureSalt = 0,
                     int cardCfAdaptiveMaxFutures = 0, double cardCfAdaptiveGap = 5.0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "datagen2 (rich)  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << "  cardFutureSalt " << cardCfFutureSalt
              << (append ? "  [append]" : "") << "  threads " << numThreads() << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << richHeader() << '\n'; f.flush(); }
    std::ofstream rf;
    if (!restOut.empty()) {
        rf.open(restOut, append ? std::ios::app : std::ios::out);
        if (rf.tellp() == 0) { rf << restCounterfactualHeader() << '\n'; rf.flush(); }
    }
    std::ofstream cf;
    if (!cardOut.empty()) {
        cf.open(cardOut, append ? std::ios::app : std::ios::out);
        if (cf.tellp() == 0) { cf << cardCounterfactualHeader() << '\n'; cf.flush(); }
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0, cardRowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto generated = runDataGen2Seed((std::uint64_t)(seedOffset + s), sims, asc, epsilon,
                                         restCfSims, restCfFutures, restCfStride,
                                         cardCfSims, cardCfFights, cardCfFutures, cardCfStride,
                                         cardCfMaxPerRun, cardCfFutureSalt,
                                         cardCfAdaptiveMaxFutures, cardCfAdaptiveGap);
        #pragma omp critical
        {
            f << generated.meta; f.flush();
            if (rf.is_open()) { rf << generated.rest; rf.flush(); }
            if (cf.is_open()) { cf << generated.card; cf.flush(); }
            rowCount += std::count(generated.meta.begin(), generated.meta.end(), '\n');
            cardRowCount += std::count(generated.card.begin(), generated.card.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld meta rows, %lld card-CF rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, cardRowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld meta rows + %lld card-CF rows from %d runs in %.1fs\n",
                rowCount, cardRowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "datagen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount + cardRowCount,
                            seedOffset, sims, asc, epsilon);
}

// ---------------------------------------------------------------------------
// COMBAT VALUE datagen: snapshot the live BattleContext at every in-fight
// decision (via search::g_onCombatDecision) and label each snapshot with that
// fight's eventual outcome (won, end HP). Trains V_combat(state) -> outcome, a
// learned leaf value to replace noisy random rollouts. Features are combat-only
// (player/monsters/available-cards), fixed length.
// Header/row now delegate to the library (search::combatFeatureNames /
// combatExtractFeatures) so combatgen training data and the C++ leaf-inference
// use the SAME feature extraction -- no train/serve drift.
static std::string combatHeaderStr() {
    const auto &names = search::combatFeatureNames();
    std::string h;
    for (size_t i = 0; i < names.size(); ++i) { if (i) h += ','; h += names[i]; }
    return h;
}

// Rich-label suffix (distributional model): endTurn + per-potion-ID consumption flags.
// Potion IDs 0..43 map to the Potion enum (0=EMPTY, 1=INVALID, 2..43=real potions).
static constexpr int kNumGenPotions = 44;
static std::string distLabelHeaderStr() {
    std::string h = ",endTurn,potionsConsumed";
    for (int i = 0; i < kNumGenPotions; ++i) { h += ",pUsed"; h += std::to_string(i); }
    return h;
}

// Snapshot of what's held at a decision so we can later determine consumption.
struct CombatDecisionSnapshot {
    std::string featureRow;
    std::bitset<kNumGenPotions> potionsHeld;
};
static std::string distLabelSuffix(const CombatDecisionSnapshot &snap,
                                   int endTurn,
                                   const std::bitset<kNumGenPotions> &finalPotions) {
    std::ostringstream o;
    o << ',' << endTurn;
    int consumed = 0;
    for (int i = 0; i < kNumGenPotions; ++i) {
        if (snap.potionsHeld[i] && !finalPotions[i]) ++consumed;
    }
    o << ',' << consumed;
    for (int i = 0; i < kNumGenPotions; ++i) {
        o << ',' << (snap.potionsHeld[i] && !finalPotions[i] ? 1 : 0);
    }
    return o.str();
}
static std::bitset<kNumGenPotions> getPotionBits(const BattleContext &bc) {
    std::bitset<kNumGenPotions> b;
    for (int i = 0; i < bc.potionCapacity && i < (int)bc.potions.size(); ++i) {
        int pid = (int)bc.potions[i];
        if (pid >= 0 && pid < kNumGenPotions) b.set(pid);
    }
    return b;
}

static std::string combatFeatureRow(const BattleContext &bc) {
    const int nf = search::combatFeatureCount();
    std::vector<float> feat(nf);
    search::combatExtractFeatures(bc, feat.data());
    std::ostringstream o;
    for (int i = 0; i < nf; ++i) {
        if (i) o << ',';
        const float v = feat[i];
        if (v == (float)(long)v) o << (long)v; else o << v;   // integers stay clean
    }
    return o.str();
}

// Play one full run; emit combat-state rows labeled with each fight's outcome.
// STS_DATAGEN_GATES=1 (winrate wave §127): the OOC decisions of this run loop
// route through the same opt-in one-ply Q gate chain as bestbench, so the
// generated combat labels come from the deployed run-level distribution
// (V4 token-net gates) instead of the heuristic fallback. Each gate
// self-guards on its env flag + model load and returns true when it acted.
static bool datagenGateStack(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN:       return oocOnePlyEventPolicy(gc, agent);
        case ScreenState::REST_ROOM:          return oocOnePlyRestPolicy(gc, agent);
        case ScreenState::TREASURE_ROOM:      return oocOnePlyTreasurePolicy(gc, agent);
        case ScreenState::SHOP_ROOM:          return oocOnePlyShopPolicy(gc, agent);
        case ScreenState::BOSS_RELIC_REWARDS: return oocOnePlyBossRelicPolicy(gc, agent);
        default:                              return false;
    }
}

static std::string runCombatGenSeed(std::uint64_t seed, int sims, int asc, double epsilon,
                                      bool richLabels = false) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    int fightIdx = 0;
    std::vector<CombatDecisionSnapshot> fightSnaps;
    search::g_onCombatDecision = [&](const BattleContext &bc) {
        CombatDecisionSnapshot s;
        s.featureRow = combatFeatureRow(bc);
        s.potionsHeld = getPotionBits(bc);
        fightSnaps.push_back(std::move(s));
    };
    // When richLabels=false: emit just won,endHp (backward-compatible).
    // When richLabels=true: also emit endTurn + per-potion consumption labels.

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            fightSnaps.clear();
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                return {};
            }
            const int won      = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp    = bc.player.curHp;
            const int endTurn  = bc.turn;
            auto finalPotions  = getPotionBits(bc);
            for (const auto &snap : fightSnaps) {
                out << seed << ',' << fightIdx << ',' << snap.featureRow
                    << ',' << won << ',' << endHp;
                if (richLabels)
                    out << distLabelSuffix(snap, endTurn, finalPotions);
                out << '\n';
            }
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (g_datagenGates && oocOnePlyCardRewardPolicy(gc, agent)) { /* gate-stack card pick (§127) */ }
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            if (!g_datagenGates || !datagenGateStack(gc, agent))
                agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    return out.str();
}

// forward decl
static std::string policyHeaderStr();
// ---------------------------------------------------------------------------
// FAIR-PLAY datagen: Searcher3 ISMCTS → value + policy CSVs with visit
// distributions. Policy rows: state+action features + visit count + total.
// ---------------------------------------------------------------------------
static std::tuple<std::string,std::string,std::string>
runFairGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    search::g_richCombatFeatures = true;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path; t_curPath = &path;

    std::ostringstream val, pol, ooc;
    int fightIdx = 0, decIdx = 0, oocDecIdx = 0;
    std::vector<CombatDecisionSnapshot> fightSnaps;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    auto logOoc = [&](const char *screen, int actionId) {
        ooc << seed << ',' << oocDecIdx++ << ',' << screen << ','
            << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
            << (int)gc.deck.cards.size() << ',' << (int)gc.gold << ',' << actionId << '\n';
    };

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        CombatDecisionSnapshot s;
        s.featureRow = combatFeatureRow(bc);
        s.potionsHeld = getPotionBits(bc);
        fightSnaps.push_back(std::move(s));
    };
    search::g_onSearchComplete3 = [&](const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
        const int thisDecIdx = decIdx++;
        const auto &edges = s3.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.child.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v;
            }
            pol << ',' << e.child.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            fightSnaps.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                search::g_onSearchComplete3 = nullptr;
                t_curPath = nullptr;
                return {"", "", ""};
            }
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            const int endTurn = bc.turn;
            auto finalPotions = getPotionBits(bc);
            for (const auto &snap : fightSnaps)
                val << seed << ',' << fightIdx << ',' << snap.featureRow << ','
                    << won << ',' << endHp
                    << distLabelSuffix(snap, endTurn, finalPotions) << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            int action = chooseMapAction(gc); logOoc("MAP", action); search::GameAction(action).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int ridx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[ridx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, ridx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete3 = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str(), ooc.str() };
}

static void fairGen(int nSeeds, int sims, int asc, double epsilon,
                    const std::string &valFile, const std::string &polFile,
                    const std::string &oocFile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fairgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << " + " << oocFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    std::ofstream of(oocFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp"
                             << distLabelHeaderStr() << "\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }
    if (of.tellp() == 0) { of << "seed,decIdx,screen,act,floor,curHp,maxHp,deckSize,gold,action\n"; of.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0, oRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto [vr, pr, or_] = runFairGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << vr;  pf << pr;  of << or_;
            vf.flush(); pf.flush(); of.flush();
            vRows += std::count(vr.begin(), vr.end(), '\n');
            pRows += std::count(pr.begin(), pr.end(), '\n');
            oRows += std::count(or_.begin(), or_.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol + %lld ooc rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, oRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy + %lld ooc rows from %d runs in %.1fs\n",
                vRows, pRows, oRows, nSeeds, wall);
    writeTrainingProvenance(valFile, "fairgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), vRows + pRows + oRows,
                            seedOffset, sims, asc, epsilon);
}

// ---------------------------------------------------------------------------
// LEAFLIAG mode driver: run full runs via runFullRunOOC (fair Searcher3, the
// §126 deployed regime) with the leaf-query hook registered, collecting a
// per-stratum reservoir of actual Searcher3 leaf-expansion states. Sampling
// is deterministic per seed (t_ld.rng seeded from the run seed only), so the
// collected leaf SET is reproducible; CSV row order follows seed completion
// order (nondeterministic under dynamic scheduling, like fairGen). Do NOT set
// probing OOC env arms (STS_OOC_ACTION_NN, STS_BOSS_DRAFT, M1/M2 path gates,
// STS_DATAGEN_GATES, …): their inner probe battles would fire the leaf hook
// and pollute the dataset with non-live decision states.
// ---------------------------------------------------------------------------
static void leafDiag(int nSeeds, int sims, int asc,
                     const std::string &outFile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    std::cout << "leafdiag   seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << "  per-stratum " << g_ldPerStratum << " x " << kLeafDiagStrata << " strata"
              << "  threads " << numThreads() << "  -> " << outFile << "\n";
    if (!g_combatVNetDiag.loaded())
        std::cout << "[leafdiag WARNING: no STS_DIAG_VNET2 secondary model loaded; "
                     "utilityR_pred will be NaN]\n";
    std::ofstream f(outFile);
    if (!f) { std::cerr << "leafdiag: cannot open " << outFile << "\n"; return; }
    f << leafDiagHeaderStr() << "\n";
    f.flush();

    g_leafdiagActive = true;
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    std::vector<long long> stratumSeen(kLeafDiagStrata, 0);
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        // thread_local hooks: set per worker
        search::g_onS3LeafQuery = leafDiagOnLeafQuery;
        search::g_onSearchComplete3 = [](const BattleContext &,
                                         const search::BattleScumSearcher3 &) { ++t_ld.decIdx; };
        t_ld.init((std::uint64_t)(seedOffset + s));
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, false);
        const std::string out = leafDiagSeedCsv();
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical
        {
            f << out;
            f.flush();
            rows += std::count(out.begin(), out.end(), '\n');
            for (int st = 0; st < kLeafDiagStrata; ++st) stratumSeen[st] += t_ld.stratumCounts[st];
            if (++done % 10 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    g_leafdiagActive = false;
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld leaf rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    std::printf("stratum fills (candidates seen):");
    for (int st = 0; st < kLeafDiagStrata; ++st)
        std::printf("  s%d=%lld", st, stratumSeen[st]);
    std::printf("\n");
}

// ---------------------------------------------------------------------------
// E2c shadow-only producer.  The callback only reservoir-samples/copies leaf
// state while search is active.  Diagnostic continuations run after the search
// completes, never write to Searcher3 state, and use only a local RNG derived
// from stable identifiers.  No score is returned to Searcher3.
// ---------------------------------------------------------------------------
struct RunwinShadowCandidate {
    BattleContext leaf;
    search::BattleScumSearcher3 *searcher = nullptr;
    int stratum = -1, depth = 0, rolloutSteps = 0, particleIndex = -1, leafCurHp = 0, leafMaxHp = 0;
    double leafHpFrac = std::numeric_limits<double>::quiet_NaN();
    std::uint64_t obsHash = 0;
    double particleWeight = 0, vnetPred = std::numeric_limits<double>::quiet_NaN();
    double rawRolloutEval = std::numeric_limits<double>::quiet_NaN();
    double blendedEval = std::numeric_limits<double>::quiet_NaN();
    bool particleExact = false, particleFallback = false, rootCarried = false;
    int reuseGeneration = 0, reuseSearchCount = -1, searchSimulation = 0;
};
struct RunwinShadowRow {
    std::uint64_t seed = 0, rootObsHash = 0, leafObsHash = 0;
    int fightIdx = -1, decIdx = -1, floor = 0, act = 0, room = -1, encounter = -1;
    int depth = 0, rootActionBits = -1, searchSimulation = 0, particleIndex = -1, leafCurHp = 0, leafMaxHp = 0;
    int replicate = 0, terminal = 0, survived = 0, projectionFailure = 0, inferenceFailure = 0;
    int replicates = 0, survivedCount = 0, particleExact = 0, particleFallback = 0, rootCarried = 0;
    int reuseGeneration = 0, reuseSearchCount = -1, rolloutSteps = 0;
    double particleWeight = 0, vnetPred = 0, rawRolloutEval = 0, blendedEval = 0, probability = 0;
    double leafHpFrac = std::numeric_limits<double>::quiet_NaN();
    double probabilityMean = 0, probabilityStd = 0, probabilityMin = 0, probabilityMax = 0;
    double conditionalSurvivalMean = std::numeric_limits<double>::quiet_NaN();
};
struct RunwinShadowCtx {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = 0, floor = 0, act = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    GameContext battleEntry;
    PathHistory path;
    std::mt19937_64 reservoir;
    int groups = 0;
    std::vector<int> seen;
    std::vector<std::vector<RunwinShadowCandidate>> reservoirs;
    std::vector<RunwinShadowRow> rows;
    std::vector<std::string> rootRows;
    std::string actionFingerprint;
    void init(std::uint64_t s) {
        seed = s; fightIdx = -1; decIdx = 0; groups = 0; rows.clear(); rootRows.clear(); actionFingerprint.clear();
        reservoir.seed(s ^ 0x9e3779b97f4a7c15ULL); seen.assign(kLeafDiagStrata, 0);
        reservoirs.assign(kLeafDiagStrata, {});
    }
    void beginFight(int fi, const GameContext &base, const PathHistory &p, Room r, MonsterEncounter e) {
        fightIdx = fi; decIdx = 0; floor = base.floorNum; act = base.act; room = r; encounter = e;
        battleEntry = base; path = p; seen.assign(kLeafDiagStrata, 0); reservoirs.assign(kLeafDiagStrata, {});
    }
    void nextDecision() { seen.assign(kLeafDiagStrata, 0); reservoirs.assign(kLeafDiagStrata, {}); ++decIdx; }
};
static thread_local RunwinShadowCtx t_runwinShadow;

static void runwinShadowBeginFight(int fightIdx, const GameContext &base, const PathHistory &path,
                                   Room room, MonsterEncounter encounter) {
    t_runwinShadow.beginFight(fightIdx, base, path, room, encounter);
}

static std::uint64_t runwinShadowSeed(std::uint64_t seed, int fight, int decision,
                                      std::uint64_t leaf, int replicate) {
    std::uint64_t x = seed ^ 0xD1B54A32D192ED03ULL;
    x ^= (std::uint64_t)(std::uint32_t)fight * 0x9e3779b97f4a7c15ULL;
    x ^= (std::uint64_t)(std::uint32_t)decision * 0xbf58476d1ce4e5b9ULL;
    x ^= leaf + (std::uint64_t)replicate * 0x94d049bb133111ebULL;
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL; x ^= x >> 27; x *= 0x94d049bb133111ebULL; x ^= x >> 31;
    return x;
}
static void runwinShadowOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (!g_runwinShadowActive || t_runwinShadow.groups >= g_runwinShadowMaxGroups || !d.bc || !d.searcher) return;
    const int stratum = leafDiagStratum(*d.bc, d.treeDepth);
    int &seen = t_runwinShadow.seen[stratum]; auto &reservoir = t_runwinShadow.reservoirs[stratum];
    RunwinShadowCandidate c;
    c.leaf = *d.bc; c.searcher = d.searcher; c.stratum = stratum; c.depth = d.treeDepth; c.obsHash = d.obsHash;
    c.leafCurHp = d.bc->player.curHp; c.leafMaxHp = d.bc->player.maxHp;
    c.leafHpFrac = c.leafMaxHp > 0 ? (double)c.leafCurHp / c.leafMaxHp : std::numeric_limits<double>::quiet_NaN();
    c.rolloutSteps = d.rolloutSteps; c.particleIndex = (int)d.particleIndex; c.particleWeight = d.particleWeight;
    c.vnetPred = d.vnetPred; c.rawRolloutEval = d.rawRolloutEval; c.blendedEval = d.blendedEval;
    c.particleExact = d.particleAppliedExactly; c.particleFallback = d.particleUsedFallback; c.rootCarried = d.rootCarried;
    c.reuseGeneration = d.reuseGeneration; c.reuseSearchCount = d.reuseSearchCount; c.searchSimulation = d.searchSimulationOrdinal;
    if ((int)reservoir.size() < g_runwinShadowPerStratum) reservoir.push_back(std::move(c));
    else {
        const int j = std::uniform_int_distribution<int>(0, seen)(t_runwinShadow.reservoir);
        if (j < g_runwinShadowPerStratum) reservoir[j] = std::move(c);
    }
    ++seen;
}
static void runwinShadowEvaluate(const RunwinShadowCandidate &c, std::uint64_t rootHash, int rootActionBits) {
    std::vector<double> probs, survived;
    std::vector<RunwinShadowRow> replicateRows;
    for (int rep = 0; rep < g_runwinShadowR; ++rep) {
        RunwinShadowRow row;
        row.seed = t_runwinShadow.seed; row.fightIdx = t_runwinShadow.fightIdx; row.decIdx = t_runwinShadow.decIdx;
        row.floor = t_runwinShadow.floor; row.act = t_runwinShadow.act; row.room = (int)t_runwinShadow.room;
        row.encounter = (int)t_runwinShadow.encounter; row.rootObsHash = rootHash; row.rootActionBits = rootActionBits;
        row.leafObsHash = c.obsHash; row.depth = c.depth; row.searchSimulation = c.searchSimulation;
        row.leafCurHp = c.leafCurHp; row.leafMaxHp = c.leafMaxHp; row.leafHpFrac = c.leafHpFrac;
        row.particleIndex = c.particleIndex; row.particleWeight = c.particleWeight; row.particleExact = c.particleExact;
        row.particleFallback = c.particleFallback; row.rootCarried = c.rootCarried; row.reuseGeneration = c.reuseGeneration;
        row.reuseSearchCount = c.reuseSearchCount; row.rolloutSteps = c.rolloutSteps; row.vnetPred = c.vnetPred;
        row.rawRolloutEval = c.rawRolloutEval; row.blendedEval = c.blendedEval; row.replicate = rep;
        BattleContext continuation = c.leaf; std::vector<search::Action> actions;
        std::mt19937_64 rng(runwinShadowSeed(row.seed, row.fightIdx, row.decIdx, row.leafObsHash, rep));
        double ignoredEval = 0; bool terminal = false;
        c.searcher->diagnosticRollout(continuation, actions, rng, ignoredEval, terminal);
        row.terminal = terminal ? 1 : 0;
        if (!terminal) { row.inferenceFailure = 1; row.probability = std::numeric_limits<double>::quiet_NaN(); }
        else if (continuation.outcome != Outcome::PLAYER_VICTORY) { row.probability = 0.0; }
        else {
            row.survived = 1; std::vector<float> raw;
            if (!e2cProjectTerminalRaw(t_runwinShadow.battleEntry, t_runwinShadow.path, t_runwinShadow.room,
                                       t_runwinShadow.encounter, continuation, raw)) row.projectionFailure = 1;
            else {
                row.probability = g_runwinShadowNet.predict(raw);
                if (!std::isfinite(row.probability) || row.probability < 0 || row.probability > 1) row.inferenceFailure = 1;
                else survived.push_back(row.probability);
            }
        }
        if (!row.projectionFailure && !row.inferenceFailure && std::isfinite(row.probability)) probs.push_back(row.probability);
        replicateRows.push_back(row);
    }
    const double mean = probs.empty() ? std::numeric_limits<double>::quiet_NaN()
        : std::accumulate(probs.begin(), probs.end(), 0.0) / probs.size();
    double variance = 0; for (double p : probs) variance += (p - mean) * (p - mean);
    const double sd = probs.empty() ? std::numeric_limits<double>::quiet_NaN() : std::sqrt(variance / probs.size());
    const double cond = survived.empty() ? std::numeric_limits<double>::quiet_NaN()
        : std::accumulate(survived.begin(), survived.end(), 0.0) / survived.size();
    const int survivedCount = (int)survived.size();
    for (auto &row : replicateRows) { row.replicates = g_runwinShadowR; row.survivedCount = survivedCount;
        row.probabilityMean = mean; row.probabilityStd = sd; row.probabilityMin = probs.empty() ? std::numeric_limits<double>::quiet_NaN() : *std::min_element(probs.begin(), probs.end());
        row.probabilityMax = probs.empty() ? std::numeric_limits<double>::quiet_NaN() : *std::max_element(probs.begin(), probs.end()); row.conditionalSurvivalMean = cond;
        t_runwinShadow.rows.push_back(row); }
}
static void runwinShadowOnSearchComplete(const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    int best = -1; std::int64_t bestVisits = -1;
    for (int i = 0; i < (int)s3.root.edges.size(); ++i) if (s3.root.edges[i].child.simulationCount > bestVisits) { bestVisits = s3.root.edges[i].child.simulationCount; best = i; }
    const int bits = best >= 0 ? (int)s3.root.edges[best].action.bits : -1;
    const std::uint64_t rootHash = CombatObservation::fromBattleContext(bc).visibleHash();
    std::ostringstream fp; fp << t_runwinShadow.seed << ':' << t_runwinShadow.fightIdx << ':' << t_runwinShadow.decIdx << ':' << rootHash << ':' << bits << ':' << bestVisits << ';';
    t_runwinShadow.actionFingerprint += fp.str();
    t_runwinShadow.rootRows.push_back(std::to_string(t_runwinShadow.seed) + ',' + std::to_string(t_runwinShadow.fightIdx) + ',' +
        std::to_string(t_runwinShadow.decIdx) + ',' + std::to_string(t_runwinShadow.floor) + ',' + std::to_string(t_runwinShadow.act) + ',' +
        std::to_string((int)t_runwinShadow.room) + ',' + std::to_string((int)t_runwinShadow.encounter) + ',' + std::to_string(rootHash) + ',' +
        std::to_string(bits) + ',' + std::to_string(bestVisits) + '\n');
    if (g_runwinShadowActive && t_runwinShadow.groups < g_runwinShadowMaxGroups)
        for (const auto &stratum : t_runwinShadow.reservoirs) for (const auto &candidate : stratum) {
            if (t_runwinShadow.groups++ >= g_runwinShadowMaxGroups) break;
            runwinShadowEvaluate(candidate, rootHash, bits);
        }
    t_runwinShadow.nextDecision();
}
static std::string runwinShadowHeader() {
    return "seed,fightIdx,decIdx,floor,act,room,encounter,rootObsHash,rootActionBits,leafObsHash,leaf_curHp,leaf_maxHp,leaf_hpFrac,treeDepth,searchSimulation,particleIndex,particleWeight,particleExact,particleFallback,rootCarried,reuseGeneration,reuseSearchCount,rolloutSteps,vnetPred,rawRolloutEval,blendedEval,replicate,terminal,survived,runwin_probability,replicates,survivedCount,diagnostic_survival_rate,conditional_survival_critic_mean,runwin_mean,runwin_std,runwin_min,runwin_max,projectionFailure,inferenceFailure";
}
static std::string runwinShadowRowsCsv(const RunResult &result) {
    std::ostringstream out;
    // The rank analyzer recomputes replicate aggregates from these serialized
    // rows.  Preserve double precision so that an otherwise valid R=2/M=2
    // smoke does not fail aggregate parity solely because of CSV rounding.
    out << std::setprecision(17);
    for (const auto &r : t_runwinShadow.rows) out << r.seed << ',' << r.fightIdx << ',' << r.decIdx << ',' << r.floor << ',' << r.act << ',' << r.room << ',' << r.encounter << ',' << r.rootObsHash << ',' << r.rootActionBits << ',' << r.leafObsHash << ',' << r.leafCurHp << ',' << r.leafMaxHp << ',' << r.leafHpFrac << ',' << r.depth << ',' << r.searchSimulation << ',' << r.particleIndex << ',' << r.particleWeight << ',' << r.particleExact << ',' << r.particleFallback << ',' << r.rootCarried << ',' << r.reuseGeneration << ',' << r.reuseSearchCount << ',' << r.rolloutSteps << ',' << r.vnetPred << ',' << r.rawRolloutEval << ',' << r.blendedEval << ',' << r.replicate << ',' << r.terminal << ',' << r.survived << ',' << r.probability << ',' << r.replicates << ',' << r.survivedCount << ',' << (r.replicates ? (double)r.survivedCount / r.replicates : 0.0) << ',' << r.conditionalSurvivalMean << ',' << r.probabilityMean << ',' << r.probabilityStd << ',' << r.probabilityMin << ',' << r.probabilityMax << ',' << r.projectionFailure << ',' << r.inferenceFailure << '\n';
    return out.str();
}
static void runwinShadow(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    if (!search::g_useSearcher3 || !g_runwinShadowNet.ok) {
        std::cerr << "runwinshadow requires forced Searcher3 and a successfully loaded STS_RUNWIN_SHADOW_MODEL\n"; return;
    }
    std::ofstream rows(outFile), runs(outFile + ".runs.csv"), roots(outFile + ".roots.csv");
    if (!rows || !runs || !roots) { std::cerr << "runwinshadow: cannot open output or sidecars\n"; return; }
    rows << runwinShadowHeader() << '\n';
    runs << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,actionFingerprint\n";
    roots << "seed,fightIdx,decIdx,floor,act,room,encounter,rootObsHash,rootActionBits,rootVisits\n";
    search::g_richCombatFeatures = true; g_runwinShadowActive = true;
    std::atomic<long long> written{0};
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = (std::uint64_t)(seedOffset + s);
        t_runwinShadow.init(seed);
        search::g_onS3LeafQuery = runwinShadowOnLeafQuery;
        search::g_onSearchComplete3 = runwinShadowOnSearchComplete;
        RunResult result = runFullRunOOC(seed, sims, asc, false, false);
        const std::string csv = runwinShadowRowsCsv(result);
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical(runwin_shadow_write)
        {
            rows << csv; runs << seed << ',' << (result.won ? 1 : 0) << ',' << result.floor << ',' << result.act << ','
                 << result.hpEnd << ',' << result.maxHp << ',' << result.fightsLost << ',' << result.deathCombat << ','
                 << result.deathEncounter << ",\"" << t_runwinShadow.actionFingerprint << "\"\n";
            for (const auto &r : t_runwinShadow.rootRows) roots << r;
            written += std::count(csv.begin(), csv.end(), '\n');
        }
    }
    g_runwinShadowActive = false;
    std::cout << "runwinshadow wrote " << written << " replicate rows to " << outFile << " (R=" << g_runwinShadowR << ")\n";
    std::string manifestPath = g_runwinShadowModelPath;
    const size_t ext = manifestPath.rfind(".txt");
    if (ext != std::string::npos) manifestPath.replace(ext, 4, ".manifest.json");
    const std::string modelHash = fileSha256(g_runwinShadowModelPath);
    const std::string manifestHash = fileSha256(manifestPath);
    std::ofstream provenance(outFile + ".provenance.json");
    if (provenance) provenance << "{\n  \"schema_version\": \"runwinshadow-v1\",\n"
        << "  \"semantic_boundary\": \"isolated terminal continuation then E2c RAW projection\",\n"
        << "  \"model_path\": \"" << jsonEscape(g_runwinShadowModelPath) << "\",\n"
        << "  \"model_sha256\": " << (modelHash.empty() ? "null" : "\"" + modelHash + "\"") << ",\n"
        << "  \"manifest_path\": \"" << jsonEscape(manifestPath) << "\",\n"
        << "  \"manifest_sha256\": " << (manifestHash.empty() ? "null" : "\"" + manifestHash + "\"") << ",\n"
        << "  \"model_description\": \"" << jsonEscape(std::to_string(g_runwinShadowNet.trees.size()) + " compact trees") << "\",\n"
        << "  \"git_sha\": \"" << jsonEscape(trainingGitValue("git rev-parse HEAD")) << "\",\n"
        << "  \"command\": \"one_combat runwinshadow\",\n"
        << "  \"seed_offset\": " << seedOffset << ", \"seeds\": " << nSeeds << ", \"sims\": " << sims << ", \"ascension\": " << asc << ",\n"
        << "  \"replicates\": " << g_runwinShadowR << ", \"per_stratum\": " << g_runwinShadowPerStratum << ", \"max_groups\": " << g_runwinShadowMaxGroups << ",\n"
        << "  \"environment\": {\"STS_RUNWIN_SHADOW_MODEL\": \"" << jsonEscape(g_runwinShadowModelPath)
        << "\", \"STS_RUNWIN_SHADOW_R\": " << g_runwinShadowR << ", \"STS_RUNWIN_SHADOW_PER_STRATUM\": " << g_runwinShadowPerStratum
        << ", \"STS_RUNWIN_SHADOW_MAX_GROUPS\": " << g_runwinShadowMaxGroups << "}\n}\n";
}
static int runwinParity(const std::string &fixture) {
    if (!g_runwinShadowNet.ok) { std::cerr << "runwinparity requires STS_RUNWIN_SHADOW_MODEL\n"; return 2; }
    std::ifstream in(fixture); std::string header;
    if (!std::getline(in, header)) { std::cerr << "runwinparity: cannot read " << fixture << '\n'; return 2; }
    const auto names = splitCsvNames(header); std::unordered_map<std::string, int> cols;
    for (int i = 0; i < (int)names.size(); ++i) if (!cols.emplace(names[i], i).second) { std::cerr << "runwinparity: duplicate fixture column\n"; return 2; }
    const auto expectedIt = cols.find("python_probability");
    if (expectedIt == cols.end()) { std::cerr << "runwinparity: fixture needs python_probability\n"; return 2; }
    // The fixture is a contract for the loaded model, not merely for the
    // current canonical manifest.  A missing selected feature must be a hard
    // failure: zero-filling silently turns a parity check into a false pass.
    std::vector<int> modelCols; modelCols.reserve(g_runwinShadowNet.featureNames.size());
    for (const auto &name : g_runwinShadowNet.featureNames) {
        const auto it = cols.find(name);
        if (it == cols.end()) { std::cerr << "runwinparity: fixture missing model feature " << name << '\n'; return 2; }
        modelCols.push_back(it->second);
    }
    std::string line; int rows = 0; double maxError = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue; const auto fields = splitCsvNames(line);
        if (fields.size() != names.size()) { std::cerr << "runwinparity: malformed row\n"; return 2; }
        std::vector<float> raw(e2cRawCanonicalNames().size(), 0.f);
        for (int i = 0; i < (int)g_runwinShadowNet.sel.size(); ++i)
            raw[g_runwinShadowNet.sel[i]] = std::strtof(fields[modelCols[i]].c_str(), nullptr);
        const double got = g_runwinShadowNet.predict(raw), expected = std::strtod(fields[expectedIt->second].c_str(), nullptr);
        if (!std::isfinite(got)) { std::cerr << "runwinparity: invalid native probability\n"; return 2; }
        maxError = std::max(maxError, std::abs(got - expected)); ++rows;
    }
    std::cout << "runwinparity rows=" << rows << " max_abs_error=" << std::setprecision(10) << maxError << '\n';
    return rows > 0 && maxError <= 1e-4 ? 0 : 1;
}

static void jsonPathAndHash(std::ostream &out, const std::string &path) {
    if (path.empty()) { out << "{\"path\": \"disabled\", \"sha256\": null}"; return; }
    out << "{\"path\": \"" << jsonEscape(path) << "\", \"sha256\": \""
        << jsonEscape(fileSha256(path)) << "\"}";
}

static const char *jsonBool(bool value) { return value ? "true" : "false"; }

// ---------------------------------------------------------------------------
// E3a direct eventual-run reference.  This intentionally remains separate
// from runwinshadow: its reference is an actual copied-run outcome, whereas
// runwinshadow's scientific meaning is the E2c RAW critic score.
// ---------------------------------------------------------------------------
struct RunwinRankRoot {
    std::uint64_t seed = 0, rootObsHash = 0, sampleHash = 0;
    int fightIdx = -1, decIdx = -1, floor = 0, act = 0, room = -1, encounter = -1;
    int rootActionBits = -1;
    std::int64_t rootVisits = 0;
    GameContext battleEntry;
    PathHistory path;
    std::vector<RunwinShadowCandidate> leaves;
};
struct RunwinRankCtx {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = 0, floor = 0, act = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    GameContext battleEntry;
    PathHistory path;
    std::vector<RunwinShadowCandidate> leaves;
    std::vector<RunwinRankRoot> roots;
    std::string actionFingerprint;
    void init(std::uint64_t s) {
        seed = s; fightIdx = -1; decIdx = 0; floor = act = 0;
        leaves.clear(); roots.clear(); actionFingerprint.clear();
    }
    void beginFight(int fi, const GameContext &base, const PathHistory &p,
                    Room r, MonsterEncounter e) {
        fightIdx = fi; decIdx = 0; floor = base.floorNum; act = base.act;
        // A GameContext ordinarily shares its Map.  Root records survive later
        // act transitions, which regenerate that map in place, so source-root
        // capture must own a detached exact battle-entry snapshot.  This also
        // keeps diagnostics observational: no retained root can alias or
        // mutate the live source run's environment map.
        room = r; encounter = e; battleEntry = detachedCounterfactualCopy(base); path = p; leaves.clear();
    }
    void nextDecision() { leaves.clear(); ++decIdx; }
};
static thread_local RunwinRankCtx t_runwinRank;

static std::uint64_t runwinRankMix(std::uint64_t x) {
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL; x ^= x >> 31;
    return x;
}
static std::uint64_t runwinRankLeafHash(std::uint64_t seed, int fight, int decision,
                                        const RunwinShadowCandidate &c) {
    std::uint64_t x = seed ^ 0x6a09e667f3bcc909ULL;
    x ^= (std::uint64_t)(std::uint32_t)fight * 0x9e3779b97f4a7c15ULL;
    x ^= (std::uint64_t)(std::uint32_t)decision * 0xbf58476d1ce4e5b9ULL;
    x ^= c.obsHash;
    x ^= (std::uint64_t)(std::uint32_t)c.searchSimulation * 0x94d049bb133111ebULL;
    x ^= (std::uint64_t)(std::uint32_t)c.particleIndex * 0xd6e8feb86659fd93ULL;
    return runwinRankMix(x);
}
static std::uint64_t runwinRankRootHash(std::uint64_t seed, int fight, int decision,
                                        std::uint64_t root, int actionBits) {
    std::uint64_t x = seed ^ 0xbb67ae8584caa73bULL;
    x ^= (std::uint64_t)(std::uint32_t)fight * 0x9e3779b97f4a7c15ULL;
    x ^= (std::uint64_t)(std::uint32_t)decision * 0xbf58476d1ce4e5b9ULL;
    x ^= root ^ ((std::uint64_t)(std::uint32_t)actionBits * 0x94d049bb133111ebULL);
    return runwinRankMix(x);
}
static bool runwinRankSameLeaf(const RunwinShadowCandidate &a, const RunwinShadowCandidate &b) {
    return a.obsHash == b.obsHash && a.searchSimulation == b.searchSimulation
        && a.particleIndex == b.particleIndex;
}
static bool runwinRankLeafLess(std::uint64_t seed, int fight, int decision,
                               const RunwinShadowCandidate &a, const RunwinShadowCandidate &b) {
    const auto ah = runwinRankLeafHash(seed, fight, decision, a);
    const auto bh = runwinRankLeafHash(seed, fight, decision, b);
    if (ah != bh) return ah < bh;
    if (a.obsHash != b.obsHash) return a.obsHash < b.obsHash;
    if (a.searchSimulation != b.searchSimulation) return a.searchSimulation < b.searchSimulation;
    return a.particleIndex < b.particleIndex;
}
static void runwinRankBeginFight(int fightIdx, const GameContext &base, const PathHistory &path,
                                 Room room, MonsterEncounter encounter) {
    t_runwinRank.beginFight(fightIdx, base, path, room, encounter);
}
static void runwinRankOnLeafQuery(const search::S3LeafDiagnostic &d) {
    if (!g_runwinRankActive || !d.bc) return;
    RunwinShadowCandidate c;
    c.leaf = *d.bc; c.stratum = leafDiagStratum(*d.bc, d.treeDepth); c.depth = d.treeDepth; c.obsHash = d.obsHash;
    c.leafCurHp = d.bc->player.curHp; c.leafMaxHp = d.bc->player.maxHp;
    c.leafHpFrac = c.leafMaxHp > 0 ? (double)c.leafCurHp / c.leafMaxHp : std::numeric_limits<double>::quiet_NaN();
    c.rolloutSteps = d.rolloutSteps; c.particleIndex = (int)d.particleIndex; c.particleWeight = d.particleWeight;
    c.vnetPred = d.vnetPred; c.rawRolloutEval = d.rawRolloutEval; c.blendedEval = d.blendedEval;
    c.particleExact = d.particleAppliedExactly; c.particleFallback = d.particleUsedFallback; c.rootCarried = d.rootCarried;
    c.reuseGeneration = d.reuseGeneration; c.reuseSearchCount = d.reuseSearchCount; c.searchSimulation = d.searchSimulationOrdinal;
    for (const auto &old : t_runwinRank.leaves) if (runwinRankSameLeaf(old, c)) return;
    t_runwinRank.leaves.push_back(std::move(c));
    std::sort(t_runwinRank.leaves.begin(), t_runwinRank.leaves.end(), [](const auto &a, const auto &b) {
        return runwinRankLeafLess(t_runwinRank.seed, t_runwinRank.fightIdx, t_runwinRank.decIdx, a, b);
    });
    if ((int)t_runwinRank.leaves.size() > g_runwinRankMaxLeaves)
        t_runwinRank.leaves.resize(g_runwinRankMaxLeaves);
}
static void runwinRankOnSearchComplete(const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    int best = -1; std::int64_t bestVisits = -1;
    for (int i = 0; i < (int)s3.root.edges.size(); ++i)
        if (s3.root.edges[i].child.simulationCount > bestVisits) {
            bestVisits = s3.root.edges[i].child.simulationCount; best = i;
        }
    const int bits = best >= 0 ? (int)s3.root.edges[best].action.bits : -1;
    const std::uint64_t rootHash = CombatObservation::fromBattleContext(bc).visibleHash();
    std::ostringstream fp;
    fp << t_runwinRank.seed << ':' << t_runwinRank.fightIdx << ':' << t_runwinRank.decIdx << ':'
       << rootHash << ':' << bits << ':' << bestVisits << ';';
    t_runwinRank.actionFingerprint += fp.str();
    RunwinRankRoot root;
    root.seed = t_runwinRank.seed; root.fightIdx = t_runwinRank.fightIdx; root.decIdx = t_runwinRank.decIdx;
    root.floor = t_runwinRank.floor; root.act = t_runwinRank.act; root.room = (int)t_runwinRank.room;
    root.encounter = (int)t_runwinRank.encounter; root.rootObsHash = rootHash; root.rootActionBits = bits;
    root.rootVisits = bestVisits; root.sampleHash = runwinRankRootHash(root.seed, root.fightIdx, root.decIdx, rootHash, bits);
    // Retain an independently owned source snapshot per root.  Do not copy a
    // shared Map pointer into the post-source reference reservoir.
    root.battleEntry = detachedCounterfactualCopy(t_runwinRank.battleEntry);
    root.path = t_runwinRank.path; root.leaves = t_runwinRank.leaves;
    t_runwinRank.roots.push_back(std::move(root));
    t_runwinRank.nextDecision();
}
static std::uint64_t runwinRankCombatSeed(const RunwinRankRoot &root, int future) {
    // Deliberately excludes leaf identity: all sibling leaves use CRN future j.
    return runwinRankMix(root.seed ^ (std::uint64_t)(std::uint32_t)root.fightIdx * 0x9e3779b97f4a7c15ULL
        ^ (std::uint64_t)(std::uint32_t)root.decIdx * 0xbf58476d1ce4e5b9ULL
        ^ root.rootObsHash ^ (std::uint64_t)(std::uint32_t)root.rootActionBits * 0x94d049bb133111ebULL
        ^ (std::uint64_t)(std::uint32_t)future * 0xd6e8feb86659fd93ULL);
}
static std::uint64_t runwinRankDownstreamSeed(const RunwinRankRoot &root, int future) {
    // Root identity plus future index, never leaf identity.
    return runwinRankMix(root.seed ^ (std::uint64_t)(std::uint32_t)root.fightIdx * 0x243f6a8885a308d3ULL
        ^ (std::uint64_t)(std::uint32_t)root.decIdx * 0x13198a2e03707344ULL
        ^ root.rootObsHash ^ (std::uint64_t)(std::uint32_t)root.rootActionBits * 0xa4093822299f31d0ULL
        ^ (std::uint64_t)(std::uint32_t)future * 0x082efa98ec4e6c89ULL);
}
static std::string runwinRankReferenceHeader() {
    return "seed,fightIdx,decIdx,rootObsHash,rootActionBits,leafObsHash,searchSimulation,particleIndex,referenceFutureIdx,combatRolloutSeed,downstreamAgentSeed,combatSurvived,runWon,valid,finalFloor,endHp,healthStatus";
}
static void runwinRankReferenceRows(const RunwinRankRoot &root, const RunwinShadowCandidate &candidate,
                                    std::ostringstream &out) {
    for (int future = 0; future < g_runwinRankReferenceFutures; ++future) {
        const std::uint64_t combatSeed = runwinRankCombatSeed(root, future);
        const std::uint64_t downstreamSeed = runwinRankDownstreamSeed(root, future);
        BattleContext continuation = candidate.leaf;
        // SAME-WORLD CRN reference: evaluator RNG varies by root/future, never
        // leaf; copied battle-entry environment hidden-future RNG is retained
        // across sibling leaves and all M futures (not resampled per future).
        // The evaluator is freshly constructed only after the source run has
        // completed. diagnosticRollout uses the explicitly supplied local RNG.
        search::BattleScumSearcher3 evaluator(continuation, root.seed, root.decIdx, 1);
        std::vector<search::Action> actions; double ignored = 0; bool terminal = false;
        std::mt19937_64 rng(combatSeed);
        evaluator.diagnosticRollout(continuation, actions, rng, ignored, terminal);
        const int survived = terminal && continuation.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
        int won = 0, valid = terminal ? 1 : 0, finalFloor = 0, endHp = 0;
        std::string health = terminal ? "combat_loss" : "nonterminal_combat";
        if (survived) {
            // Exact terminal transfer: copy the battle-entry game, detach its
            // map, then apply BattleContext::exitBattle before full OOC play.
            GameContext branch = detachedCounterfactualCopy(root.battleEntry);
            continuation.exitBattle(branch);
            const OocCounterfactualResult result = finishOocCounterfactual(
                std::move(branch), g_runwinRankReferenceSims, downstreamSeed, root.path,
                /*maxFights=*/-1, /*bootstrap=*/false);
            valid = result.valid ? 1 : 0;
            won = valid && result.won > 0.5 ? 1 : 0;
            finalFloor = valid ? (int)result.floor : 0;
            endHp = valid ? (int)result.hp : 0;
            health = valid ? "ok" : "counterfactual_invalid";
        }
        out << root.seed << ',' << root.fightIdx << ',' << root.decIdx << ',' << root.rootObsHash << ','
            << root.rootActionBits << ',' << candidate.obsHash << ',' << candidate.searchSimulation << ','
            << candidate.particleIndex << ',' << future << ',' << combatSeed << ',' << downstreamSeed << ','
            << survived << ',' << won << ',' << valid << ',' << finalFloor << ',' << endHp << ',' << health << '\n';
    }
}
static void runwinRank(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    if (!search::g_useSearcher3 || !g_runwinShadowNet.ok) {
        std::cerr << "runwinrank requires forced Searcher3 and a successfully loaded STS_RUNWIN_SHADOW_MODEL\n"; return;
    }
    std::ofstream rows(outFile), refs(outFile + ".reference.csv"), runs(outFile + ".runs.csv"), roots(outFile + ".roots.csv");
    if (!rows || !refs || !runs || !roots) { std::cerr << "runwinrank: cannot open output or sidecars\n"; return; }
    rows << runwinShadowHeader() << '\n'; refs << runwinRankReferenceHeader() << '\n';
    runs << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,actionFingerprint\n";
    roots << "seed,fightIdx,decIdx,floor,act,room,encounter,rootObsHash,rootActionBits,rootVisits,rankable,selected,rootSampleHash,sourceLeaves\n";
    search::g_richCombatFeatures = true; g_runwinRankActive = true;
    std::atomic<long long> shadowWritten{0}, referenceWritten{0};
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = (std::uint64_t)(seedOffset + s);
        t_runwinRank.init(seed); t_runwinShadow.rows.clear();
        search::g_onS3LeafQuery = runwinRankOnLeafQuery;
        search::g_onSearchComplete3 = runwinRankOnSearchComplete;
        const RunResult result = runFullRunOOC(seed, sims, asc, false, false);
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        std::vector<int> ranked;
        for (int i = 0; i < (int)t_runwinRank.roots.size(); ++i)
            if ((int)t_runwinRank.roots[i].leaves.size() >= g_runwinRankMinLeaves) ranked.push_back(i);
        std::sort(ranked.begin(), ranked.end(), [](int ai, int bi) {
            const auto &a = t_runwinRank.roots[ai], &b = t_runwinRank.roots[bi];
            if (a.sampleHash != b.sampleHash) return a.sampleHash < b.sampleHash;
            if (a.fightIdx != b.fightIdx) return a.fightIdx < b.fightIdx;
            return a.decIdx < b.decIdx;
        });
        const int selected = std::min(g_runwinRankRoots, (int)ranked.size());
        std::ostringstream referenceCsv;
        for (int i = 0; i < selected; ++i) {
            const auto &root = t_runwinRank.roots[ranked[i]];
            for (const auto &source : root.leaves) {
                // Reuse the existing E2c shadow estimator/projection/model for
                // the R diagnostic rows; it is not used by V_direct below.
                search::BattleScumSearcher3 evaluator(source.leaf, root.seed, root.decIdx, 1);
                RunwinShadowCandidate scored = source; scored.searcher = &evaluator;
                t_runwinShadow.seed = root.seed; t_runwinShadow.fightIdx = root.fightIdx; t_runwinShadow.decIdx = root.decIdx;
                t_runwinShadow.floor = root.floor; t_runwinShadow.act = root.act; t_runwinShadow.room = (Room)root.room;
                t_runwinShadow.encounter = (MonsterEncounter)root.encounter; t_runwinShadow.battleEntry = root.battleEntry; t_runwinShadow.path = root.path;
                runwinShadowEvaluate(scored, root.rootObsHash, root.rootActionBits);
                runwinRankReferenceRows(root, source, referenceCsv);
            }
        }
        const std::string shadowCsv = runwinShadowRowsCsv(result);
        const std::string referenceText = referenceCsv.str();
        #pragma omp critical(runwin_rank_write)
        {
            rows << shadowCsv; refs << referenceText;
            runs << seed << ',' << (result.won ? 1 : 0) << ',' << result.floor << ',' << result.act << ','
                 << result.hpEnd << ',' << result.maxHp << ',' << result.fightsLost << ',' << result.deathCombat << ','
                 << result.deathEncounter << ",\"" << t_runwinRank.actionFingerprint << "\"\n";
            for (int i = 0; i < (int)t_runwinRank.roots.size(); ++i) {
                const auto &root = t_runwinRank.roots[i];
                const bool rankable = (int)root.leaves.size() >= g_runwinRankMinLeaves;
                const bool isSelected = std::find(ranked.begin(), ranked.begin() + selected, i) != ranked.begin() + selected;
                roots << root.seed << ',' << root.fightIdx << ',' << root.decIdx << ',' << root.floor << ',' << root.act << ','
                      << root.room << ',' << root.encounter << ',' << root.rootObsHash << ',' << root.rootActionBits << ','
                      << root.rootVisits << ',' << (rankable ? 1 : 0) << ',' << (isSelected ? 1 : 0) << ',' << root.sampleHash << ',' << root.leaves.size() << '\n';
            }
            shadowWritten += std::count(shadowCsv.begin(), shadowCsv.end(), '\n');
            referenceWritten += std::count(referenceText.begin(), referenceText.end(), '\n');
        }
    }
    g_runwinRankActive = false;
    const std::string manifest = g_runwinShadowModelPath.substr(0, g_runwinShadowModelPath.rfind(".txt")) + ".manifest.json";
    std::ofstream provenance(outFile + ".provenance.json");
    if (provenance) {
        provenance << "{\n  \"schema_version\": \"e3a-runwinrank-v2\",\n"
          << "  \"semantic_boundary\": \"source leaf -> SAME-WORLD CRN diagnostic combat -> canonical exitBattle -> copied full-run counterfactual\",\n"
          << "  \"reference_semantics\": \"M is paired realized-world CRN: copied GameContext/environment hidden-future RNG is preserved across sibling leaves and M; only diagnostic combat-policy and downstream-agent RNG vary by root/future. It is not a marginalization over resampled maps, rewards, or encounters; environment-world variation is across source seeds and the outer source-seed bootstrap.\",\n"
          << "  \"git_sha\": \"" << jsonEscape(trainingGitValue("git rev-parse HEAD")) << "\",\n"
          << "  \"git_dirty\": " << jsonBool(!trainingGitValue("git status --porcelain --untracked-files=all").empty()) << ",\n"
          << "  \"binary\": "; jsonPathAndHash(provenance, g_mainBinaryPath); provenance << ",\n"
          << "  \"build_configuration\": \"CMake one_combat C++17 target\",\n"
          << "  \"command\": \"one_combat";
        for (const auto &arg : g_mainArgv) provenance << ' ' << jsonEscape(arg);
        provenance << "\",\n  \"seed_offset\": " << seedOffset << ", \"seeds\": " << nSeeds
          << ", \"source_sims\": " << sims << ", \"ascension\": " << asc << ",\n"
          << "  \"effective_source_policy\": {\"STS_FAIR\": " << jsonBool(search::g_fairPlay)
          << ", \"STS_SEARCHER3\": " << jsonBool(search::g_useSearcher3)
          << ", \"STS_S3_PARTICLES\": " << search::g_s3Particles
          << ", \"STS_S3_BELIEF\": " << jsonBool(search::g_s3Belief)
          << ", \"STS_S3_CHAIN\": " << jsonBool(search::g_s3Chain)
          << ", \"STS_LIVE_VALID\": " << jsonBool(search::g_liveValid)
          << ", \"STS_S3_ALWAYS_Q\": \"" << jsonEscape(std::getenv("STS_S3_ALWAYS_Q") ? std::getenv("STS_S3_ALWAYS_Q") : "0")
          << "\", \"STS_STOP_AFTER_ACT\": " << g_stopAfterAct << ", \"STS_COLLECT_KEYS\": " << jsonBool(g_collectKeys) << "},\n"
          << "  \"effective_models\": {\"vnet\": "; jsonPathAndHash(provenance, g_effectiveVNetPath);
        provenance << ", \"vnet_alpha\": " << search::g_vnetAlpha << ", \"policy\": "; jsonPathAndHash(provenance, g_effectivePolicyPath);
        provenance << ", \"ooc_strategic\": "; jsonPathAndHash(provenance, g_effectiveOocStrategicPath);
        provenance << ", \"ooc_strategic_token\": "; jsonPathAndHash(provenance, g_effectiveOocStrategicTokPath);
        provenance << ", \"e2c_raw\": "; jsonPathAndHash(provenance, g_runwinShadowModelPath);
        provenance << ", \"e2c_manifest_sha256\": \"" << jsonEscape(fileSha256(manifest)) << "\"},\n"
          << "  \"effective_ooc\": {\"strategic_margin\": " << g_oocStrategicMargin
          << ", \"card\": " << jsonBool(g_oocActionNN) << ", \"rest\": " << jsonBool(g_oocStrategicRest)
          << ", \"event\": " << jsonBool(g_oocStrategicEvent) << ", \"shop\": " << jsonBool(g_oocStrategicShop)
          << ", \"treasure\": " << jsonBool(g_oocStrategicTreasure) << ", \"boss_relic\": " << jsonBool(g_oocStrategicBossRelic) << "},\n"
          << "  \"runwin_replicates\": " << g_runwinShadowR << ", \"selected_roots\": " << g_runwinRankRoots
          << ", \"max_leaves\": " << g_runwinRankMaxLeaves << ", \"min_rankable_leaves\": " << g_runwinRankMinLeaves
          << ", \"reference_futures\": " << g_runwinRankReferenceFutures << ", \"reference_sims\": " << g_runwinRankReferenceSims << ",\n"
          << "  \"crn\": \"combat and downstream seeds are root/future keyed and exclude leaf identity\"\n}\n";
    }
    std::cout << "runwinrank wrote " << shadowWritten << " shadow rows and " << referenceWritten
              << " reference rows to " << outFile << " (R=" << g_runwinShadowR << ", M=" << g_runwinRankReferenceFutures << ")\n";
}

static void particleLeafProbe(int nSeeds, int sims, int asc,
                              const std::string &outFile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    std::ofstream f(outFile);
    if (!f) { std::cerr << "particle_leaf_probe: cannot open " << outFile << '\n'; return; }
    f << particleLeafProbeHeaderStr() << '\n';
    g_leafdiagActive = true;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        search::g_onS3LeafQuery = particleLeafProbeOnLeafQuery;
        search::g_onSearchComplete3 = [](const BattleContext &,
                                         const search::BattleScumSearcher3 &) { ++t_ld.decIdx; };
        t_ld.init((std::uint64_t)(seedOffset + s));
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, false);
        const std::string out = particleLeafProbeSeedCsv();
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical
        f << out;
    }
    g_leafdiagActive = false;
    std::cout << "particle leaf probe wrote " << outFile << " (K="
              << g_particleLeafProbeK << ", rate=" << g_particleLeafProbeRate
              << ", max_groups=" << g_particleLeafProbeMaxGroups << ")\n";
}

static std::string particlePosteriorProbeHeaderStr() {
    return "rowType,seed,fightIdx,decIdx,sourceLeafId,obsHash,treeDepth,encounterName,turn,"
           "curHp,maxHp,drawPileSize,rootParticleCount,positiveParticleCount,replayAttempted,"
           "replayCompatibleParticles,uniqueCompatibleStates,compatibleMass,evaluatedWorldCount,"
           "evaluatedMass,sourceParticleIndex,sourceParticleReplayOk,sourceParticleFallback,"
           "groupEligible,invariantOk,replayFailure,semanticReplayFailures,actionIllegalFailures,"
           "intermediateObservationMismatches,intermediateOutcomeMismatches,finalObservationMismatches,"
           "drawPileMismatches,firstMismatchCheckpoint,expectedMismatchHash,actualMismatchHash,mismatchActionBits,"
           "rootCarried,reuseGeneration,reuseSearchCount,searchSimulation,ageStratum,ageBin,candidateParticleIndex,"
           "candidateWeight,candidateIsSource,dedupOrdinal,semanticBranchesCreated,extraSemanticBranches,maxSurvivingBranches,"
           "branchesCollapsed,replayExplosion,rngSignature,drawOrder,terminal,target,"
           "fullTarget,controlledTarget,controlledTargetStd,rolloutSteps";
}

static std::string particlePosteriorProbeSeedCsv() {
    std::ostringstream o;
    for (const auto &r : t_ld.particlePosteriorRows) {
        o << r.rowType << ',' << r.seed << ',' << r.fightIdx << ',' << r.decIdx << ','
          << r.sourceLeafId << ',' << r.obsHash << ',' << r.treeDepth << ',' << r.encounter << ','
          << r.turn << ',' << r.curHp << ',' << r.maxHp << ',' << r.drawPileSize << ','
          << r.rootParticleCount << ',' << r.positiveParticleCount << ',' << r.replayAttempted << ','
          << r.replayCompatibleParticles << ',' << r.uniqueCompatibleStates << ','
          << r.compatibleMass << ',' << r.evaluatedWorldCount << ',' << r.evaluatedMass << ','
          << r.sourceParticleIndex << ',' << r.sourceParticleReplayOk << ','
          << r.sourceParticleFallback << ',' << r.groupEligible << ',' << r.invariantOk << ','
          << (r.replayFailure.empty() ? std::string("-") : r.replayFailure) << ','
          << r.semanticReplayFailures << ',' << r.actionIllegalFailures << ','
          << r.intermediateObservationMismatches << ',' << r.intermediateOutcomeMismatches << ','
          << r.finalObservationMismatches << ',' << r.drawPileMismatches << ','
          << r.firstMismatchCheckpoint << ',' << r.expectedMismatchHash << ','
          << r.actualMismatchHash << ',' << r.mismatchActionBits << ','
          << r.rootCarriedFlag << ',' << r.reuseGeneration << ',' << r.reuseSearchCount << ','
          << r.searchSimulation << ',' << r.ageStratum << ',' << r.ageBin << ','
          << r.candidateParticleIndex << ',' << r.candidateWeight << ','
          << r.candidateIsSource << ',' << r.dedupOrdinal << ',' << r.semanticBranchesCreated << ','
          << r.extraSemanticBranches << ','
          << r.maxSurvivingBranches << ',' << r.branchesCollapsed << ',' << r.replayExplosion << ','
          << r.rngSignature << ','
          << '"' << r.drawOrder << '"' << ',' << r.terminal << ',' << r.target << ','
          << r.target << ',' << r.controlledTarget << ',' << r.controlledTargetStd << ','
          << r.rolloutSteps << '\n';
    }
    return o.str();
}

static void recordPosteriorSearchFingerprint(
    const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    int best = -1;
    std::int64_t visits = -1;
    for (int i = 0; i < (int)s3.root.edges.size(); ++i) {
        const auto count = s3.root.edges[i].child.simulationCount;
        if (count > visits) { visits = count; best = i; }
    }
    const int decision = t_ld.decIdx;
    std::ostringstream row;
    row << t_ld.seed << ':' << decision << ':'
        << sts::CombatObservation::fromBattleContext(bc).visibleHash() << ':'
        << (best >= 0 ? s3.root.edges[best].action.bits : 0xffffffffu) << ':'
        << visits << ';';
    t_ld.actionFingerprint += row.str();

    if (g_particlePosteriorAgeSplit && t_ld.fightIdx == 0 && decision == 0) {
        for (int stratum = 0; stratum < 2; ++stratum) {
            t_ld.particlePosteriorAgeSelected[stratum] =
                particlePosteriorAgeSelectEvenly(
                    t_ld.particlePosteriorAgeCandidates[stratum]);
            for (int rank = 0; rank < (int)t_ld.particlePosteriorAgeSelected[stratum].size(); ++rank) {
                const int ordinal = t_ld.particlePosteriorAgeSelected[stratum][rank];
                auto it = std::find_if(
                    t_ld.particlePosteriorAgeCandidates[stratum].begin(),
                    t_ld.particlePosteriorAgeCandidates[stratum].end(),
                    [ordinal](const ParticlePosteriorAgeCandidate &candidate) {
                        return candidate.ordinal == ordinal;
                    });
                if (it == t_ld.particlePosteriorAgeCandidates[stratum].end()) continue;
                auto diagnostic = it->diagnostic;
                diagnostic.searcher = const_cast<search::BattleScumSearcher3 *>(&s3);
                diagnostic.bc = &it->state;
                particlePosteriorProbeOnLeafQuery(diagnostic);
            }
        }
        t_ld.particlePosteriorAgeCandidates[0].clear();
        t_ld.particlePosteriorAgeCandidates[1].clear();
    }
    ++t_ld.decIdx;
}

// Phase-1b driver. Identical run regime to particle_leaf_probe (forced
// fair-Searcher3); additionally sets g_s3LeafTraceActions so step() records
// per-action semantic checkpoints. Writes <out>.runs.csv (one row per seed,
// game-independent of probe work) as the probe-OFF vs probe-ON determinism
// comparator.
static void particlePosteriorProbe(int nSeeds, int sims, int asc,
                                   const std::string &outFile, long long seedOffset = 0) {
    if (g_particlePosteriorAgeSplit
        && (g_particlePosteriorAgeMinPerStratum < 1
            || g_particlePosteriorAgeMinPerStratum > 16
            || g_particlePosteriorAgePerStratum != 16
            || g_particlePosteriorAgeEarlyEnd < g_particlePosteriorAgeEarlyStart
            || g_particlePosteriorAgeLateEnd < g_particlePosteriorAgeLateStart)) {
        std::cerr << "particle_posterior_probe: invalid age-split configuration; "
                     "require 16 bins and ascending windows\n";
        return;
    }
    search::g_richCombatFeatures = true;
    std::ofstream f(outFile);
    if (!f) { std::cerr << "particle_posterior_probe: cannot open " << outFile << '\n'; return; }
    std::ofstream runs(outFile + ".runs.csv");
    if (!runs) { std::cerr << "particle_posterior_probe: cannot open " << outFile << ".runs.csv\n"; return; }
    runs << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,actionFingerprint\n";
    f << particlePosteriorProbeHeaderStr() << '\n';
    g_leafdiagActive = true;
    const auto t0 = std::chrono::steady_clock::now();
    long long rows = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + s);
        RunResult r;
        if (g_particlePosteriorAgeSplit) {
            // Capture lightweight leaf snapshots during the single actual
            // search. At search completion, select evenly spaced ordinals and
            // run the expensive posterior replay on those stored snapshots
            // while the same Searcher3 instance is still alive.
            t_ld.init(seed);
            search::g_onS3LeafQuery = particlePosteriorAgeCaptureOnLeafQuery;
            search::g_s3LeafTraceActions = true;
            search::g_onSearchComplete3 = recordPosteriorSearchFingerprint;
            r = runFullRunOOC(seed, sims, asc, false, false);
        } else {
            t_ld.init(seed);
            search::g_onS3LeafQuery = particlePosteriorProbeOnLeafQuery;
            search::g_s3LeafTraceActions = true;
            search::g_onSearchComplete3 = recordPosteriorSearchFingerprint;
            r = runFullRunOOC(seed, sims, asc, false, false);
        }
        const std::string out = particlePosteriorProbeSeedCsv();
        search::g_onS3LeafQuery = nullptr;
        search::g_s3LeafTraceActions = false;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical
        {
            f << out;
            runs << (seedOffset + s) << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                 << r.act << ',' << r.hpEnd << ',' << r.maxHp << ',' << r.fightsLost << ','
                 << r.deathCombat << ',' << r.deathEncounter << ",\""
                 << t_ld.actionFingerprint << "\"\n";
            rows += std::count(out.begin(), out.end(), '\n');
        }
    }
    g_leafdiagActive = false;
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("particle posterior probe wrote %s (%lld rows, K=%s, max_groups=%d) in %.1fs (%.2fs/seed)\n",
                outFile.c_str(), rows,
                g_particlePosteriorProbeK > 0 ? std::to_string(g_particlePosteriorProbeK).c_str() : "all",
                g_particlePosteriorProbeMaxGroups, wall, wall / std::max(1, nSeeds));
}

// ---------------------------------------------------------------------------
// LEAFLREF mode: high-budget reference values for recorded leafdiag leaves.
// Reads a leafdiag CSV, replays each recorded seed deterministically via
// runFullRunOOC (same config + REPLAY_SIMS as the leafdiag run, so the
// regenerated search produces the identical leaf states), re-captures the
// recorded leaves by obsHash, and evaluates each with a FRESH high-budget
// Searcher3. Within a decision group all reference searchers are reseeded
// (rng + belief + particles) from one per-group CRN seed, giving PARTIALLY
// shared determinization draws — the draw-pile shuffle prefix consumes a
// state-dependent number of RNG draws, so the streams diverge after the
// belief/particle prefix (partial CRN, not exact noise cancellation);
// sibling ranking comparison still benefits from the shared prefix. The
// reference value is s3.root mean evaluation (evaluationSum/simulationCount)
// at the leaf — a high-budget Searcher3 estimate, NEVER ground truth; the
// reference searcher runs with the same learned-leaf environment as the
// leafdiag run (deployed STS_VNET at the configured alpha), so the reference
// is NOT model-free (see combat-search.md "Leaf-state diagnostics"). See
// docs/knowledge-base/.../combat-search.md (leafdiag/leafref). Output:
// seed,fightIdx,decIdx,obsHash,referenceValue, budget,particleCount,crnSeed,
// treeSize.
// ---------------------------------------------------------------------------
static thread_local struct {
    int highBudgetSims = 3000;
    int particleCount = 128;
    std::ostringstream out;   // reference rows for the current seed (thread-local)
    long long capturedCount = 0;   // recorded leaves actually re-captured (match-rate sanity)
    long long recordedCount = 0;   // recorded leaves expected for the seed
} t_lr;

static void leafRefOnLeafQuery(const search::S3LeafDiagnostic &d) {
    const LeafRefGroupKey key{t_ld.seed, t_ld.fightIdx, t_ld.decIdx};
    auto it = t_ld.recorded.find(key);
    if (it == t_ld.recorded.end()) return;
    if (it->second.find(d.obsHash) == it->second.end()) return;
    if (!t_ld.capturedSeen.insert(d.obsHash).second) return;   // one capture per obsHash per decision
    t_ld.capturedLeaves.push_back(*d.bc);
    ++t_lr.capturedCount;   // match-rate sanity counter
}

static void leafRefOnSearchComplete3(const BattleContext &,
                                     const search::BattleScumSearcher3 &) {
    const int dec = t_ld.decIdx;
    ++t_ld.decIdx;
    const LeafRefGroupKey key{t_ld.seed, t_ld.fightIdx, dec};
    if (t_ld.recorded.find(key) == t_ld.recorded.end() || t_ld.capturedLeaves.empty()) {
        t_ld.capturedLeaves.clear();
        t_ld.capturedSeen.clear();
        return;
    }
    // One CRN seed per decision group: every reference searcher in the group
    // reseeds rng + belief + particles from it, giving PARTIALLY shared
    // determinization draws. Belief::initial + prepareCRNParticles each
    // std::shuffle the draw pile, consuming a state-dependent number of RNG
    // draws (draw-pile size varies between sibling leaf states), so the
    // streams diverge after that prefix — CRN is partial, not exact. The
    // main replay searcher is NOT running while this fires (between
    // decisions), and g_s3Crn stays untouched — the CRN here is explicit
    // per-searcher reseeding, not the global warm-start path.
    std::uint64_t gs = t_ld.seed;
    gs ^= (std::uint64_t)(std::uint32_t)t_ld.fightIdx * 0x9e3779b97f4a7c15ULL;
    gs ^= (std::uint64_t)(std::uint32_t)dec * 0xbf58476d1ce4e5b9ULL;
    if (!gs) gs = 1;
    search::g_onS3LeafQuery = nullptr;   // suppress the capture hook inside the reference searches
    for (const auto &leaf : t_ld.capturedLeaves) {
        search::BattleScumSearcher3 s3(leaf, 0, 0, t_lr.particleCount);
        s3.rng.seed(gs);   // shared determinization PREFIX across the group (partial CRN, see above)
        s3.belief = Belief::initial(leaf, t_lr.particleCount, s3.rng);
        s3.prepareCRNParticles();
        s3.searchToTotal(t_lr.highBudgetSims);
        const double ref = s3.root.simulationCount > 0
            ? s3.root.evaluationSum / s3.root.simulationCount
            : std::numeric_limits<double>::quiet_NaN();
        const std::uint64_t obsHash =
            CombatObservation::fromBattleContext(leaf).visibleHash();
        t_lr.out << t_ld.seed << ',' << t_ld.fightIdx << ',' << dec << ',' << obsHash << ','
                 << ref << ',' << t_lr.highBudgetSims << ',' << t_lr.particleCount << ','
                 << gs << ',' << s3.root.simulationCount << '\n';
    }
    search::g_onS3LeafQuery = leafRefOnLeafQuery;
    t_ld.capturedLeaves.clear();
    t_ld.capturedSeen.clear();
}

// Parse a leafdiag CSV into seed -> [(fightIdx, decIdx) -> recorded obsHash
// set]; shared by the leafref and rollouttrace replay modes.
static std::map<std::uint64_t, std::map<std::pair<int,int>, std::unordered_set<std::uint64_t>>>
parseLeafDiagGroups(const std::string &inFile) {
    std::ifstream in(inFile);
    if (!in) { std::cerr << "leafref/rollouttrace: cannot open " << inFile << "\n"; return {}; }
    std::string headerLine;
    if (!std::getline(in, headerLine)) { std::cerr << "leafref/rollouttrace: empty CSV\n"; return {}; }
    std::vector<std::string> cols;
    {
        std::istringstream hs(headerLine); std::string c;
        while (std::getline(hs, c, ',')) cols.push_back(c);
    }
    const auto colIdx = [&](const char *name) -> int {
        for (size_t i = 0; i < cols.size(); ++i) if (cols[i] == name) return (int)i;
        return -1;
    };
    const int ciSeed = colIdx("seed"), ciFight = colIdx("fightIdx"),
              ciDec = colIdx("decIdx"), ciObs = colIdx("obsHash");
    if (ciSeed < 0 || ciFight < 0 || ciDec < 0 || ciObs < 0) {
        std::cerr << "leafref/rollouttrace: leafdiag CSV missing "
                     "seed/fightIdx/decIdx/obsHash columns\n";
        return {};
    }
    std::map<std::uint64_t, std::map<std::pair<int,int>, std::unordered_set<std::uint64_t>>> groups;
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream ls(line); std::string tok;
        std::vector<std::string> f;
        while (std::getline(ls, tok, ',')) f.push_back(tok);
        if ((int)f.size() <= std::max({ciSeed, ciFight, ciDec, ciObs})) continue;
        const std::uint64_t seed = std::strtoull(f[ciSeed].c_str(), nullptr, 10);
        const int fight = std::atoi(f[ciFight].c_str());
        const int dec = std::atoi(f[ciDec].c_str());
        const std::uint64_t obs = std::strtoull(f[ciObs].c_str(), nullptr, 10);
        groups[seed][{fight, dec}].insert(obs);
    }
    return groups;
}

static void leafRef(const std::string &inFile, const std::string &outFile,
                    int highBudgetSims, int nSeedsRef, int asc, int replaySims) {
    // (a) parse the leafdiag CSV: seed -> [(fightIdx, decIdx) -> obsHash set]
    auto groups = parseLeafDiagGroups(inFile);
    if (groups.empty()) { std::cerr << "leafref: no recorded groups in " << inFile << "\n"; return; }

    std::ofstream f(outFile);
    if (!f) { std::cerr << "leafref: cannot open " << outFile << "\n"; return; }
    f << "seed,fightIdx,decIdx,obsHash,referenceValue,budget,particleCount,crnSeed,treeSize\n";
    f.flush();
    std::cout << "leafref    " << groups.size() << " recorded seeds, "
              << nSeedsRef << " to process, high-budget " << highBudgetSims
              << " sims x " << t_lr.particleCount << " particles, replay sims " << replaySims
              << "  -> " << outFile << "\n";
    std::cout << "[leafref: replay must match the leafdiag run — SAME particles "
                 "(STS_S3_PARTICLES), STS_VNET+alpha, OOC env arms, ascension; "
                 "a mismatch shows up as a re-capture WARNING]\n";
    if (highBudgetSims < replaySims)
        std::cout << "[leafref WARNING: high-budget " << highBudgetSims
                  << " < replay sims " << replaySims
                  << " — reference budget should exceed the datagen budget]\n";

    g_leafdiagActive = true;   // runFullRunOOC fight-context hooks
    auto t0 = std::chrono::steady_clock::now();
    long long refRows = 0; int done = 0;
    int processed = 0;
    const int nProcess = std::min(nSeedsRef, (int)groups.size());
    #pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < nProcess; ++i) {
        // deterministic seed selection: the i-th recorded seed in sorted order
        std::uint64_t seed = 0;
        #pragma omp critical
        {
            auto it = groups.begin();
            std::advance(it, i);
            seed = it->first;
        }
        const auto &grp = groups[seed];
        // thread_local hook setup per worker (t_lr is thread_local too)
        t_lr.highBudgetSims = highBudgetSims;
        search::g_onS3LeafQuery = leafRefOnLeafQuery;
        search::g_onSearchComplete3 = leafRefOnSearchComplete3;
        t_ld.init(seed);
        t_lr.capturedCount = 0;
        t_lr.recordedCount = 0;
        for (const auto &kv : grp) {
            t_ld.recorded[{seed, kv.first.first, kv.first.second}] = kv.second;
            t_lr.recordedCount += (long long)kv.second.size();
        }
        t_lr.out.str(""); t_lr.out.clear();
        runFullRunOOC(seed, replaySims, asc, false, false);
        const std::string out = t_lr.out.str();
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical
        {
            f << out;
            f.flush();
            refRows += std::count(out.begin(), out.end(), '\n');
            if (t_lr.capturedCount < t_lr.recordedCount)
                std::cout << "[leafref seed " << seed << " WARNING: re-captured "
                          << t_lr.capturedCount << " of " << t_lr.recordedCount
                          << " recorded leaves — replay config differs from the "
                          << "leafdiag run (particles / STS_VNET+alpha / OOC env arms / "
                          << "ascension must match)\n";
            if (++done % 10 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d seeds, %lld reference rows, %.0fs (%.3fs/seed)\n",
                            done, nSeedsRef, refRows, el, el/done);
                std::fflush(stdout);
            }
        }
        ++processed;
    }
    g_leafdiagActive = false;
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld reference rows from %d replayed seeds in %.1fs\n",
                refRows, processed, wall);
}

// ---------------------------------------------------------------------------
// ROLLOUTTRACE mode (Task 6 of the 2026-08-08 handover): actual-rollout state
// sequences for delta-V smoothness diagnostics. Replays recorded leafdiag
// decisions deterministically (same machinery as leafref), re-captures the
// recorded leaves by obsHash, then runs ONE search-policy rollout from each
// leaf INSIDE a BattleScumSearcher3 (search::g_onRolloutStep fires after every
// executed rollout action, so the sequence is the actual rollout policy, not a
// reconstructed approximation). Each row: one state of one trajectory, with
// both model predictions. Output columns:
//   seed,fightIdx,decIdx,obsHash,step,turn,curHp,maxHp,block,energy,strength,
//   hand,draw,discard,monSumHp,monMaxHp,incomingDmg,isTerminal,
//   endHp_pred,utilityR_pred,stateHash
// stateHash is the row state's OWN visibleHash
// (CombatObservation::fromBattleContext(bc).visibleHash()); at step 0 it
// equals obsHash. Diagnostic-only: used to measure mid-rollout visible-state
// collisions per search (rollout-TT / path-reuse viability), never read by
// the search.
// step 0 is the recorded leaf state itself (pre-rollout).
// ---------------------------------------------------------------------------
static thread_local struct {
    std::ostringstream out;        // trace rows for the current seed (thread-local)
    std::uint64_t seed = 0;
    int fightIdx = -1, dec = -1;
    std::uint64_t obsHash = 0;
} t_rt;

static void rolloutTraceWriteRow(const BattleContext &bc, int step, bool isTerminal) {
    double eH = search::g_useVNet && search::g_combatVNet.loaded()
        ? search::g_combatVNet.predict(bc) : std::numeric_limits<double>::quiet_NaN();
    double uR = g_combatVNetDiag.loaded()
        ? g_combatVNetDiag.predict(bc) : std::numeric_limits<double>::quiet_NaN();
    int monSum = 0, monMax = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0) { monSum += bc.monsters.arr[i].curHp; monMax += bc.monsters.arr[i].maxHp; }
    // incoming damage the player faces (same formula as the canonical
    // combatExtractFeatures incomingDmg feature)
    int incoming = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &mm = bc.monsters.arr[i];
        if (mm.curHp <= 0 || !mm.isAttacking()) continue;
        const auto di = mm.getMoveBaseDamage(bc);
        incoming += mm.calculateDamageToPlayer(bc, di.damage) * di.attackCount;
    }
    const std::uint64_t stateHash = CombatObservation::fromBattleContext(bc).visibleHash();
    t_rt.out << t_rt.seed << ',' << t_rt.fightIdx << ',' << t_rt.dec << ','
             << t_rt.obsHash << ',' << step << ',' << bc.turn << ','
             << bc.player.curHp << ',' << bc.player.maxHp << ',' << bc.player.block << ','
             << bc.player.energy << ',' << bc.player.strength << ','
             << bc.cards.cardsInHand << ',' << (int)bc.cards.drawPile.size() << ','
             << (int)bc.cards.discardPile.size() << ',' << monSum << ',' << monMax << ','
             << incoming << ',' << (isTerminal ? 1 : 0) << ','
             << eH << ',' << uR << ',' << stateHash << '\n';
}

static void rolloutTraceOnStep(const BattleContext &bc, int steps) {
    rolloutTraceWriteRow(bc, steps, bc.outcome != Outcome::UNDECIDED);
}

static void rolloutTraceOnSearchComplete3(const BattleContext &,
                                          const search::BattleScumSearcher3 &) {
    const int dec = t_ld.decIdx;
    ++t_ld.decIdx;
    if (t_ld.recorded.find({t_ld.seed, t_ld.fightIdx, dec}) == t_ld.recorded.end()
        || t_ld.capturedLeaves.empty()) {
        t_ld.capturedLeaves.clear();
        t_ld.capturedSeen.clear();
        return;
    }
    std::uint64_t gs = t_ld.seed;
    gs ^= (std::uint64_t)(std::uint32_t)t_ld.fightIdx * 0x9e3779b97f4a7c15ULL;
    gs ^= (std::uint64_t)(std::uint32_t)dec * 0xbf58476d1ce4e5b9ULL;
    if (!gs) gs = 1;
    search::g_onS3LeafQuery = nullptr;   // suppress the capture hook inside the trace rollouts
    for (const auto &leaf : t_ld.capturedLeaves) {
        t_rt.seed = t_ld.seed; t_rt.fightIdx = t_ld.fightIdx; t_rt.dec = dec;
        t_rt.obsHash = CombatObservation::fromBattleContext(leaf).visibleHash();
        rolloutTraceWriteRow(leaf, 0, false);                 // step 0: the leaf state itself
        search::BattleScumSearcher3 s3(leaf, 0, 0, 64);
        s3.rng.seed(gs);
        search::g_onRolloutStep = rolloutTraceOnStep;
        BattleContext sc = leaf;
        std::vector<search::Action> stack;
        s3.playoutRandom(sc, stack);
        search::g_onRolloutStep = nullptr;
    }
    search::g_onS3LeafQuery = leafRefOnLeafQuery;
    t_ld.capturedLeaves.clear();
    t_ld.capturedSeen.clear();
}

static void rolloutTrace(const std::string &inFile, const std::string &outFile,
                         int nSeedsRef, int asc, int replaySims) {
    auto groups = parseLeafDiagGroups(inFile);
    if (groups.empty()) { std::cerr << "rollouttrace: no recorded groups in " << inFile << "\n"; return; }
    std::ofstream f(outFile);
    if (!f) { std::cerr << "rollouttrace: cannot open " << outFile << "\n"; return; }
    f << "seed,fightIdx,decIdx,obsHash,step,turn,curHp,maxHp,block,energy,"
         "strength,hand,draw,discard,monSumHp,monMaxHp,incomingDmg,isTerminal,"
         "endHp_pred,utilityR_pred,stateHash\n";
    f.flush();
    std::cout << "rollouttrace " << groups.size() << " recorded seeds, " << nSeedsRef
              << " to process, replay sims " << replaySims << "  -> " << outFile << "\n";
    std::cout << "[rollouttrace: replay must match the leafdiag run — SAME particles "
                 "(STS_S3_PARTICLES), STS_VNET+alpha, OOC env arms, ascension; "
                 "a mismatch shows up as a re-capture WARNING]\n";
    if (!g_combatVNetDiag.loaded())
        std::cout << "[rollouttrace WARNING: no STS_DIAG_VNET2 secondary model loaded; "
                     "utilityR_pred will be NaN]\n";

    g_leafdiagActive = true;
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    const int nProcess = std::min(nSeedsRef, (int)groups.size());
    #pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < nProcess; ++i) {
        std::uint64_t seed = 0;
        #pragma omp critical
        {
            auto it = groups.begin();
            std::advance(it, i);
            seed = it->first;
        }
        const auto &grp = groups[seed];
        search::g_onS3LeafQuery = leafRefOnLeafQuery;
        search::g_onSearchComplete3 = rolloutTraceOnSearchComplete3;
        t_ld.init(seed);
        t_lr.capturedCount = 0;
        t_lr.recordedCount = 0;
        for (const auto &kv : grp) {
            t_ld.recorded[{seed, kv.first.first, kv.first.second}] = kv.second;
            t_lr.recordedCount += (long long)kv.second.size();
        }
        t_rt.out.str(""); t_rt.out.clear();
        runFullRunOOC(seed, replaySims, asc, false, false);
        const std::string out = t_rt.out.str();
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        #pragma omp critical
        {
            f << out;
            f.flush();
            rows += std::count(out.begin(), out.end(), '\n');
            if (t_lr.capturedCount < t_lr.recordedCount)
                std::cout << "[rollouttrace seed " << seed << " WARNING: re-captured "
                          << t_lr.capturedCount << " of " << t_lr.recordedCount
                          << " recorded leaves — replay config differs from the "
                          << "leafdiag run (particles / STS_VNET+alpha / OOC env arms / "
                          << "ascension must match)\n";
            if (++done % 10 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d seeds, %lld trace rows, %.0fs (%.3fs/seed)\n",
                            done, nProcess, rows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    g_leafdiagActive = false;
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld trace rows from %d replayed seeds in %.1fs\n", rows, nProcess, wall);
}

// ---------------------------------------------------------------------------
// FRONTIERGEN: Searcher3 frontier-leaf corpus with restorable BattleContext
// snapshots (plan "combat-value targets" phase 2). Runs the deployed fair-S3
// stack (STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
// STS_LIVE_VALID=1 — forced here, the same regime leafdiag/fairgen use, with
// explicit live-valid since datagen is not covered by the parse-time default,
// §123) over fresh seeds. search::g_onS3LeafQuery fires at ALL THREE frontier
// sites of BattleScumSearcher3::step() (S3LeafDiagnostic::frontierType:
// 0=unexpanded-leaf blend, 1=illegal-fallback rollout, 2=depth-cap direct
// eval) — gated by search::g_s3LeafQueryAllSites, which ONLY frontiergen sets
// (leafdiag/leafref/rollouttrace keep their historical single-site corpus);
// each captured leaf is serialized with serializeBattleContext into
// OUTFILE[_STAMP].bin (flat concatenation of 4-byte little-endian length +
// blob) and gets one CSV row with provenance + binary offset/size.
//
// Sampling: per-stratum reservoirs (11 strata: 3 hpFrac bands x 3 encounter
// difficulties + 1 deep-tree stratum + 1 boss-only stratum), capacity
// STS_FRONTIERGEN_PER_STRATUM (default 200) per stratum per seed; dedup by
// obsHash per seed at capture time (first kept, duplicateCount incremented,
// no re-serialized blob) AND corpus-wide at flush time (a visible state
// already written by an earlier-flushed seed is dropped without re-
// serialization and counted in the run summary — the corpus holds each
// visible state at most once). Root policy entropy (-sum p_i log p_i over
// root edge visit shares) is computed at search-complete (g_onSearchComplete3)
// and attached to the decision's captured leaves. The search's ROOT
// BattleContext (the pre-action decision state whose search produced the
// leaves — captured by the search-complete hook) is ALSO serialized for the
// leafrelabel sibling pass and indexed in the CSV by a marker row with
// frontierType=-1 (obsHash is the captured root visible hash); parent markers are NOT corpus-deduped (each
// decision needs its own parent for the sibling pass).
//
// Do NOT enable the probing OOC arms (STS_OOC_ACTION_NN, STS_BOSS_DRAFT,
// M1/M2 path gates, STS_DATAGEN_GATES, …): their inner probe battles fire the
// leaf hook and pollute the dataset.
// ---------------------------------------------------------------------------
static constexpr int kFrontierStrata = 11;   // 9 (hpFrac x diff) + deep + boss

struct FrontierRow {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = -1;
    std::uint64_t obsHash = 0;
    int frontierType = 0;                    // 0/1/2 leaf sites; -1 = parent marker
    int treeDepth = 0;
    int budget = 0;
    int turn = 0, floor = 0, act = 0;
    std::string encounter;                   // UPPER_CASE enum NAME
    int curHp = 0, maxHp = 0;
    int isBoss = 0;
    int rolloutLength = 0;
    double policyEntropy = std::numeric_limits<double>::quiet_NaN();
    std::uint64_t binaryOffset = 0;
    std::uint32_t binarySize = 0;
    int duplicateCount = 0;
};

// Per-seed frontiergen state. The fight context (fightIdx/floor/act/encounter/
// decIdx) lives in the shared t_ld struct (populated by runFullRunOOC under
// the g_frontiergenActive guard), so the hooks read it from there; this struct
// only carries the seed, budget, reservoirs, and pending captures.
static thread_local struct {
    std::uint64_t seed = 0;
    int budget = 0;
    std::vector<FrontierRow> rows;                  // finalized rows (this seed)
    std::unordered_map<std::uint64_t, int> rowByObsHash;  // obsHash -> rows index
    std::array<int, kFrontierStrata> stratumCounts{};     // accepted per stratum
    std::vector<FrontierRow> pending;               // current decision's captures
    std::vector<std::vector<std::uint8_t>> pendingBlobs;
    void init(std::uint64_t sd, int sims) {
        seed = sd; budget = sims;
        rows.clear(); rowByObsHash.clear();
        stratumCounts.fill(0);
        pending.clear(); pendingBlobs.clear();
    }
} t_fg;

// bin file shared across threads (writes happen only under the critical
// section inside the search-complete hook, so offsets are global and final).
static std::ofstream *g_fgBinFile = nullptr;

// Corpus-wide obsHash dedup: a leaf visible state is written AT MOST ONCE
// across the whole run — the first seed to flush it wins, later occurrences
// are dropped without re-serialization and counted here. All access happens
// under the frontierGenOnSearchComplete3 critical section. (The per-row
// duplicateCount column keeps its per-seed meaning: duplicates of that
// obsHash seen within the same seed.)
static std::unordered_set<std::uint64_t> g_fgSeenObsHashes;
static long long g_fgCorpusDuplicates = 0;   // cross-seed duplicates dropped

static std::string frontierGenHeaderStr() {
    return "seed,fightIdx,decIdx,obsHash,frontierType,treeDepth,budget,turn,"
           "floor,act,encounterName,curHp,maxHp,isBoss,rolloutLength,"
           "policyEntropy,binaryOffset,binarySize,duplicateCount";
}

// Acceptance rule for one captured leaf: its natural stratum (leafdiag
// mapping) must have capacity; boss leaves additionally draw on the dedicated
// boss-only stratum (stratum 10) so boss rooms are oversampled.
static bool frontierGenAccept(const BattleContext &bc, int depth) {
    const int s0 = leafDiagStratum(bc, depth);
    if (t_fg.stratumCounts[s0] < g_fgPerStratum) { ++t_fg.stratumCounts[s0]; return true; }
    if (isBossEncounter(bc.encounter)
        && t_fg.stratumCounts[10] < g_fgPerStratum) { ++t_fg.stratumCounts[10]; return true; }
    return false;
}

static void writeFgBlob(std::ofstream &f, const std::vector<std::uint8_t> &blob) {
    const std::uint32_t len = (std::uint32_t)blob.size();
    const char hdr[4] = { (char)(len & 0xFF), (char)((len >> 8) & 0xFF),
                          (char)((len >> 16) & 0xFF), (char)((len >> 24) & 0xFF) };
    f.write(hdr, 4);
    f.write((const char *)blob.data(), (std::streamsize)blob.size());
}

static void frontierGenOnLeafQuery(const search::S3LeafDiagnostic &d) {
    const std::uint64_t oh = d.obsHash;
    auto it = t_fg.rowByObsHash.find(oh);
    if (it != t_fg.rowByObsHash.end()) { ++t_fg.rows[it->second].duplicateCount; return; }
    for (auto &pr : t_fg.pending)
        if (pr.obsHash == oh) { ++pr.duplicateCount; return; }   // same-decision repeat
    if (!frontierGenAccept(*d.bc, d.treeDepth)) return;
    if (std::getenv("STS_FRONTIERGEN_DEBUG"))
        std::cerr << "[fg debug] type " << d.frontierType << " depth " << d.treeDepth
                  << " inputState " << (int)d.bc->inputState
                  << " task " << (int)d.bc->cardSelectInfo.cardSelectTask
                  << " turn " << d.bc->turn << " inHand " << d.bc->cards.cardsInHand
                  << " draw " << d.bc->cards.drawPile.size() << "\n";
    FrontierRow r;
    r.seed = t_fg.seed; r.fightIdx = t_ld.fightIdx; r.decIdx = t_ld.decIdx;
    r.obsHash = oh; r.frontierType = d.frontierType; r.treeDepth = d.treeDepth;
    r.budget = t_fg.budget;
    r.turn = d.bc->turn; r.floor = t_ld.floor; r.act = t_ld.act;
    r.encounter = t_ld.encounter;
    r.curHp = d.bc->player.curHp; r.maxHp = d.bc->player.maxHp;
    r.isBoss = isBossEncounter(d.bc->encounter) ? 1 : 0;
    r.rolloutLength = d.rolloutSteps;
    // policyEntropy filled at search-complete
    t_fg.pending.push_back(std::move(r));
    t_fg.pendingBlobs.push_back(sts::serializeBattleContext(*d.bc));
}

// Search-complete hook: compute the root policy entropy, capture the search's
// ROOT BattleContext (the pre-action decision state, for the sibling pass),
// and flush the decision's captured leaves + parent to the shared bin/CSV.
static void frontierGenOnSearchComplete3(const BattleContext &bc,
                                         const search::BattleScumSearcher3 &s3) {
    double entropy = 0.0;
    std::int64_t total = 0;
    for (const auto &e : s3.root.edges) total += e.child.simulationCount;
    if (total > 0) {
        for (const auto &e : s3.root.edges) {
            const double p = (double)e.child.simulationCount / total;
            if (p > 0) entropy -= p * std::log(p);
        }
    }
    for (auto &r : t_fg.pending) r.policyEntropy = entropy;

    // parent marker row (only when this decision captured >= 1 leaf)
    FrontierRow parentRow;
    bool haveParent = !t_fg.pending.empty();
    std::vector<std::uint8_t> parentBlob;
    if (haveParent) {
        parentRow.seed = t_fg.seed; parentRow.fightIdx = t_ld.fightIdx; parentRow.decIdx = t_ld.decIdx;
        parentRow.frontierType = -1;                       // marker
        parentRow.obsHash = sts::CombatObservation::fromBattleContext(bc).visibleHash();
        parentRow.turn = bc.turn; parentRow.floor = t_ld.floor; parentRow.act = t_ld.act;
        parentRow.encounter = t_ld.encounter;
        parentRow.curHp = bc.player.curHp; parentRow.maxHp = bc.player.maxHp;
        parentRow.isBoss = isBossEncounter(bc.encounter) ? 1 : 0;
        parentRow.policyEntropy = entropy;
        parentBlob = sts::serializeBattleContext(bc);
    }

    #pragma omp critical
    {
        if (haveParent && g_fgBinFile) {
            const std::uint64_t off = (std::uint64_t)g_fgBinFile->tellp();
            writeFgBlob(*g_fgBinFile, parentBlob);
            // binaryOffset points at the blob DATA (after the 4-byte length
            // prefix), so readFgBlob(offset, size) reads the exact blob.
            parentRow.binaryOffset = off + 4;
            parentRow.binarySize = (std::uint32_t)parentBlob.size();
            t_fg.rows.push_back(std::move(parentRow));
        }
        for (size_t i = 0; i < t_fg.pending.size(); ++i) {
            // Corpus-wide dedup: a leaf visible state already written by an
            // earlier-flushed seed is dropped (counted; no row, no blob —
            // parent marker rows above are NOT deduped because each decision
            // needs its own parent for the sibling pass).
            if (!g_fgSeenObsHashes.insert(t_fg.pending[i].obsHash).second) {
                ++g_fgCorpusDuplicates;
                continue;
            }
            const std::uint64_t off = (std::uint64_t)g_fgBinFile->tellp();
            writeFgBlob(*g_fgBinFile, t_fg.pendingBlobs[i]);
            t_fg.pending[i].binaryOffset = off + 4;
            t_fg.pending[i].binarySize = (std::uint32_t)t_fg.pendingBlobs[i].size();
            t_fg.rowByObsHash.emplace(t_fg.pending[i].obsHash, (int)t_fg.rows.size());
            t_fg.rows.push_back(std::move(t_fg.pending[i]));
        }
        g_fgBinFile->flush();
    }
    t_fg.pending.clear();
    t_fg.pendingBlobs.clear();
    ++t_ld.decIdx;
}

static std::string frontierGenSeedCsv() {
    std::ostringstream o;
    for (const auto &r : t_fg.rows) {
        o << r.seed << ',' << r.fightIdx << ',' << r.decIdx << ',' << r.obsHash << ','
          << r.frontierType << ',' << r.treeDepth << ',' << r.budget << ','
          << r.turn << ',' << r.floor << ',' << r.act << ',' << r.encounter << ','
          << r.curHp << ',' << r.maxHp << ',' << r.isBoss << ','
          << r.rolloutLength << ',' << r.policyEntropy << ','
          << r.binaryOffset << ',' << r.binarySize << ',' << r.duplicateCount << '\n';
    }
    return o.str();
}

static void frontierGen(int nSeeds, int sims, int asc,
                        const std::string &outBase, long long seedOffset = 0,
                        const std::string &stamp = "") {
    // OUTFILE_CSV[_STAMP].csv: the stamp slots in before the .csv extension
    // (build/frontier_smoke.csv + stamp "smoke" -> build/frontier_smoke_smoke.csv).
    std::string base = outBase;
    if (base.size() >= 4 && base.compare(base.size() - 4, 4, ".csv") == 0)
        base.resize(base.size() - 4);
    const std::string csvFile = stamp.empty() ? base + ".csv" : base + "_" + stamp + ".csv";
    const std::string binFile = stamp.empty() ? base + ".bin" : base + "_" + stamp + ".bin";
    std::cout << "frontiergen seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << "  per-stratum " << g_fgPerStratum << " x " << kFrontierStrata << " strata"
              << "  threads " << numThreads() << "  -> " << csvFile << " + " << binFile << "\n";
    std::ofstream f(csvFile);
    if (!f) { std::cerr << "frontiergen: cannot open " << csvFile << "\n"; return; }
    std::ofstream bin(binFile, std::ios::binary);
    if (!bin) { std::cerr << "frontiergen: cannot open " << binFile << "\n"; return; }
    f << frontierGenHeaderStr() << "\n";
    f.flush();
    g_fgBinFile = &bin;
    g_fgSeenObsHashes.clear();
    g_fgCorpusDuplicates = 0;
    g_frontiergenActive = true;

    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    std::vector<long long> stratumSeen(kFrontierStrata, 0);
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        search::g_onS3LeafQuery = frontierGenOnLeafQuery;
        search::g_onSearchComplete3 = frontierGenOnSearchComplete3;
        search::g_s3LeafQueryAllSites = true;   // frontiergen needs the illegal-fallback + depth-cap sites
        t_fg.init((std::uint64_t)(seedOffset + s), sims);
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, false);
        const std::string out = frontierGenSeedCsv();
        search::g_onS3LeafQuery = nullptr;
        search::g_onSearchComplete3 = nullptr;
        search::g_s3LeafQueryAllSites = false;
        #pragma omp critical
        {
            f << out;
            f.flush();
            rows += std::count(out.begin(), out.end(), '\n');
            for (int st = 0; st < kFrontierStrata; ++st) stratumSeen[st] += t_fg.stratumCounts[st];
            if (++done % 10 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rows, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    g_frontiergenActive = false;
    g_fgBinFile = nullptr;
    bin.flush();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld frontier rows + binary snapshots from %d runs in %.1fs "
                "(%lld cross-seed duplicate obsHashes dropped)\n",
                rows, nSeeds, wall, g_fgCorpusDuplicates);
    std::printf("stratum fills (accepted per stratum):");
    for (int st = 0; st < kFrontierStrata; ++st)
        std::printf("  s%d=%lld", st, stratumSeen[st]);
    std::printf("\n");
}

// ---------------------------------------------------------------------------
// LEAFRELABEL: empirical terminal-outcome distribution per recorded frontier
// leaf (plan phase 3). Reads a frontiergen CSV + bin, deserializes each
// selected leaf's BattleContext, runs a FRESH high-budget Searcher3 with
// terminal-outcome recording (TerminalRecordingSearcher overrides the now-
// virtual evaluateTerminal, so every terminal eval in the search — rollout
// ends, terminal-in-tree, terminal direct evals — records (won, endHp)), and
// writes:
//   leaf.csv     seed,fightIdx,decIdx,obsHash,frontierType,depth,budget,turn,
//                curHp,maxHp,isBoss,pWin,meanHpOnWin,hpQuantile25,
//                hpQuantile50,hpQuantile75,totalTerminals,winCount,nonTerminal
//   sibling.csv  seed,fightIdx,decIdx,leafObsHash,siblingObsHash,actionIdx,
//                pWin,meanHpOnWin,totalTerminals,modelPred,nonTerminal
// totalTerminals counts ONLY terminal evaluations (rollout ends + terminal-in-
// tree + terminal direct evals); sims that end without a terminal eval (prune-
// as-dead backpropagations, non-terminal depth-cap/rollout-cap evals) are
// reported in nonTerminal = budget - totalTerminals (clamped at 0), so the
// denominator semantics are self-documented and totalTerminals need not equal
// the sim budget.
// Sibling mode: per leaf, restore the search's ROOT state (frontierType=-1
// marker rows), enumerate legal actions (the SAME contract as the searcher —
// search::enumerateActionsForNode, which includes potions), and evaluate each
// child with the SAME particle set (one Belief + CRN particle set constructed
// from the parent visible state, seeded from one per-group CRN seed — partial
// CRN, same pattern as leafref) at a separate sibling budget (3-5k sims).
// modelPred is the deployed leaf model's value on the child state (PVNet
// leafValue if a PVNet is loaded, else the vnet prediction) — the ranking
// signal for phase 4; NaN when no combat value model is loaded. Deterministic
// per leaf: the searcher seeds from (agentSeed=0, obsHash, decisionIndex=0),
// so two runs on the same binary inputs produce identical
// pWin/meanHpOnWin.
// ---------------------------------------------------------------------------
struct TerminalRecordingSearcher : public search::BattleScumSearcher3 {
    long long winCount = 0;         // terminal evals that ended in victory
    long long winHpSum = 0;         // sum of player hp over victory evals
    long long totalTerminals = 0;   // all terminal evals observed
    std::vector<long long> hpHist;  // hp -> count (victory evals only)
    using search::BattleScumSearcher3::BattleScumSearcher3;

    double evaluateTerminal(const BattleContext &bc) override {
        const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
        const int hp = bc.player.curHp;
        ++totalTerminals;
        if (won) {
            ++winCount;
            winHpSum += hp;
            if ((int)hpHist.size() <= hp) hpHist.resize(hp + 1, 0);
            ++hpHist[hp];
        }
        return search::BattleScumSearcher3::evaluateTerminal(bc);
    }
};

struct FrontierLeafEntry {
    std::uint64_t seed = 0;
    int fightIdx = -1, decIdx = -1;
    std::uint64_t obsHash = 0;
    int frontierType = 0;
    int treeDepth = 0;
    int budget = 0;
    int turn = 0, floor = 0, act = 0;
    std::string encounter;
    int curHp = 0, maxHp = 0;
    int isBoss = 0;
    int rolloutLength = 0;
    double policyEntropy = std::numeric_limits<double>::quiet_NaN();
    std::uint64_t binaryOffset = 0;
    std::uint32_t binarySize = 0;
};

// Parse a frontiergen CSV: leaf rows (frontierType 0/1/2) -> entries; parent
// marker rows (frontierType -1) -> (seed, fightIdx, decIdx) -> (offset, size).
static std::vector<FrontierLeafEntry> parseFrontierCsv(
    const std::string &inFile,
    std::map<std::tuple<std::uint64_t, int, int>,
             std::pair<std::uint64_t, std::uint32_t>> &parents) {
    std::vector<FrontierLeafEntry> leaves;
    std::ifstream in(inFile);
    if (!in) { std::cerr << "leafrelabel: cannot open " << inFile << "\n"; return leaves; }
    std::string headerLine;
    if (!std::getline(in, headerLine)) { std::cerr << "leafrelabel: empty CSV\n"; return leaves; }
    std::vector<std::string> cols;
    {
        std::istringstream hs(headerLine); std::string c;
        while (std::getline(hs, c, ',')) cols.push_back(c);
    }
    const auto colIdx = [&](const char *name) -> int {
        for (size_t i = 0; i < cols.size(); ++i) if (cols[i] == name) return (int)i;
        return -1;
    };
    const int ciSeed = colIdx("seed"), ciFight = colIdx("fightIdx"),
              ciDec = colIdx("decIdx"), ciObs = colIdx("obsHash"),
              ciType = colIdx("frontierType"), ciDepth = colIdx("treeDepth"),
              ciBudget = colIdx("budget"), ciTurn = colIdx("turn"),
              ciFloor = colIdx("floor"), ciAct = colIdx("act"),
              ciEnc = colIdx("encounterName"), ciCur = colIdx("curHp"),
              ciMax = colIdx("maxHp"), ciBoss = colIdx("isBoss"),
              ciRoll = colIdx("rolloutLength"), ciEnt = colIdx("policyEntropy"),
              ciOff = colIdx("binaryOffset"), ciSize = colIdx("binarySize");
    if (ciSeed < 0 || ciFight < 0 || ciDec < 0 || ciObs < 0 || ciType < 0
        || ciOff < 0 || ciSize < 0) {
        std::cerr << "leafrelabel: frontier CSV missing required columns\n";
        return leaves;
    }
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream ls(line); std::string tok;
        std::vector<std::string> f;
        while (std::getline(ls, tok, ',')) f.push_back(tok);
        const int need = std::max({ciSeed, ciFight, ciDec, ciObs, ciType, ciOff, ciSize});
        if ((int)f.size() <= need) continue;
        FrontierLeafEntry e;
        e.seed = std::strtoull(f[ciSeed].c_str(), nullptr, 10);
        e.fightIdx = std::atoi(f[ciFight].c_str());
        e.decIdx = std::atoi(f[ciDec].c_str());
        e.obsHash = std::strtoull(f[ciObs].c_str(), nullptr, 10);
        e.frontierType = std::atoi(f[ciType].c_str());
        e.binaryOffset = std::strtoull(f[ciOff].c_str(), nullptr, 10);
        e.binarySize = (std::uint32_t)std::strtoul(f[ciSize].c_str(), nullptr, 10);
        if (ciDepth >= 0) e.treeDepth = std::atoi(f[ciDepth].c_str());
        if (ciBudget >= 0) e.budget = std::atoi(f[ciBudget].c_str());
        if (ciTurn >= 0) e.turn = std::atoi(f[ciTurn].c_str());
        if (ciFloor >= 0) e.floor = std::atoi(f[ciFloor].c_str());
        if (ciAct >= 0) e.act = std::atoi(f[ciAct].c_str());
        if (ciEnc >= 0 && ciEnc < (int)f.size()) e.encounter = f[ciEnc];
        if (ciCur >= 0) e.curHp = std::atoi(f[ciCur].c_str());
        if (ciMax >= 0) e.maxHp = std::atoi(f[ciMax].c_str());
        if (ciBoss >= 0) e.isBoss = std::atoi(f[ciBoss].c_str());
        if (ciRoll >= 0) e.rolloutLength = std::atoi(f[ciRoll].c_str());
        if (ciEnt >= 0) e.policyEntropy = std::atof(f[ciEnt].c_str());
        if (e.frontierType == -1) {
            parents[{e.seed, e.fightIdx, e.decIdx}] = {e.binaryOffset, e.binarySize};
        } else {
            leaves.push_back(std::move(e));
        }
    }
    return leaves;
}

// HP|win quantiles from the victory histogram (0.25/0.50/0.75).
static void hpWinQuantiles(const std::vector<long long> &hist,
                           double &q25, double &q50, double &q75) {
    q25 = q50 = q75 = std::numeric_limits<double>::quiet_NaN();
    long long n = 0;
    for (long long c : hist) n += c;
    if (n == 0) return;
    auto quantile = [&](double q) -> double {
        const long long idx = (long long)(q * (n - 1));
        long long acc = 0;
        for (size_t hp = 0; hp < hist.size(); ++hp) {
            acc += hist[hp];
            if (acc > idx) return (double)hp;
        }
        return (double)hist.size() - 1;
    };
    q25 = quantile(0.25);
    q50 = quantile(0.50);
    q75 = quantile(0.75);
}

static std::vector<std::uint8_t> readFgBlob(std::ifstream &f,
                                            std::uint64_t offset, std::uint32_t size) {
    std::vector<std::uint8_t> blob(size);
    if (size == 0) return blob;
    f.clear();
    f.seekg((std::streamoff)offset);
    f.read((char *)blob.data(), (std::streamsize)size);
    if (!f) blob.clear();
    return blob;
}

static void leafRelabel(const std::string &inCsv, const std::string &inBin,
                        const std::string &leafOut, const std::string &siblingOut,
                        int highBudgetSims, int nLeaves, int particleCount,
                        int siblingBudget) {
    std::map<std::tuple<std::uint64_t, int, int>,
             std::pair<std::uint64_t, std::uint32_t>> parents;
    std::vector<FrontierLeafEntry> leaves = parseFrontierCsv(inCsv, parents);
    if (leaves.empty()) { std::cerr << "leafrelabel: no leaf rows in " << inCsv << "\n"; return; }
    const int n = std::min(nLeaves, (int)leaves.size());
    std::ofstream lf(leafOut);
    if (!lf) { std::cerr << "leafrelabel: cannot open " << leafOut << "\n"; return; }
    std::ofstream sf(siblingOut);
    if (!sf) { std::cerr << "leafrelabel: cannot open " << siblingOut << "\n"; return; }
    lf << "seed,fightIdx,decIdx,obsHash,frontierType,depth,budget,turn,curHp,"
          "maxHp,isBoss,pWin,meanHpOnWin,hpQuantile25,hpQuantile50,hpQuantile75,"
          "totalTerminals,winCount,nonTerminal\n";
    sf << "seed,fightIdx,decIdx,leafObsHash,siblingObsHash,actionIdx,pWin,"
          "meanHpOnWin,totalTerminals,modelPred,nonTerminal\n";
    lf.flush(); sf.flush();

    std::cout << "leafrelabel " << n << " of " << leaves.size()
              << " recorded leaves, high-budget " << highBudgetSims
              << " sims x " << particleCount << " particles, sibling budget "
              << siblingBudget << "  -> " << leafOut << " + " << siblingOut << "\n";

    auto t0 = std::chrono::steady_clock::now();
    long long leafRows = 0, siblingRows = 0;
    // Output rows buffered per leaf index so the CSV order is deterministic
    // (independent of OMP completion order); each index is written by exactly
    // one thread, so no locking is needed on the vectors.
    std::vector<std::string> outLeaf((std::size_t)n), outSib((std::size_t)n);
    std::atomic<int> done{0};
    #pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < n; ++i) {
        const FrontierLeafEntry &le = leaves[i];
        std::ifstream bin(inBin, std::ios::binary);
        if (!bin) { std::cerr << "leafrelabel: cannot open " << inBin << "\n"; continue; }
        const std::vector<std::uint8_t> blob =
            readFgBlob(bin, le.binaryOffset, le.binarySize);
        if (blob.empty()) continue;
        const BattleContext leaf =
            sts::deserializeBattleContext(blob.data(), blob.size());
        if (leaf.outcome != Outcome::UNDECIDED) continue;   // datagen only captures live states

        TerminalRecordingSearcher s3(leaf, 0, 0, particleCount);
        s3.searchToTotal(highBudgetSims);
        const long long total = s3.totalTerminals;
        const double pWin = total > 0 ? (double)s3.winCount / total
                                      : std::numeric_limits<double>::quiet_NaN();
        const double meanHp = s3.winCount > 0 ? (double)s3.winHpSum / s3.winCount
                                              : std::numeric_limits<double>::quiet_NaN();
        double q25, q50, q75;
        hpWinQuantiles(s3.hpHist, q25, q50, q75);

        std::ostringstream lrow;
        const long long nonTerm = std::max(0LL, (long long)highBudgetSims - total);
        lrow << le.seed << ',' << le.fightIdx << ',' << le.decIdx << ','
             << le.obsHash << ',' << le.frontierType << ',' << le.treeDepth << ','
             << highBudgetSims << ',' << le.turn << ',' << le.curHp << ','
             << le.maxHp << ',' << le.isBoss << ',' << pWin << ',' << meanHp << ','
             << q25 << ',' << q50 << ',' << q75 << ',' << total << ','
             << s3.winCount << ',' << nonTerm << '\n';

        // Sibling pass: same particle set (CRN) over the search root's
        // children. The root state is the frontiergen parent marker blob.
        std::ostringstream srow;
        auto pit = parents.find({le.seed, le.fightIdx, le.decIdx});
        if (pit != parents.end()) {
            const std::vector<std::uint8_t> pblob =
                readFgBlob(bin, pit->second.first, pit->second.second);
            if (!pblob.empty()) {
                const BattleContext parent =
                    sts::deserializeBattleContext(pblob.data(), pblob.size());
                if (parent.outcome == Outcome::UNDECIDED) {
                    // One CRN seed + one belief/particle set from the parent
                    // visible state (partial CRN, same pattern as leafref).
                    std::uint64_t gs = le.seed;
                    gs ^= (std::uint64_t)(std::uint32_t)le.fightIdx * 0x9e3779b97f4a7c15ULL;
                    gs ^= (std::uint64_t)(std::uint32_t)le.decIdx * 0xbf58476d1ce4e5b9ULL;
                    if (!gs) gs = 1;
                    search::BattleScumSearcher3 crnSeed(parent, 0, 0, particleCount);
                    crnSeed.rng.seed(gs);
                    crnSeed.belief = Belief::initial(parent, particleCount, crnSeed.rng);
                    crnSeed.prepareCRNParticles();

                    // Sibling action set = the searcher's OWN enumeration
                    // contract (search::enumerateActionsForNode, which
                    // includes potion actions; one_combat.cpp::legalActions
                    // omits potions and would under-cover the ranking set).
                    search::BattleScumSearcher3::Node actNode;
                    search::enumerateActionsForNode(actNode, parent);
                    const std::vector<search::Action> actions =
                        [&] { std::vector<search::Action> a; a.reserve(actNode.edges.size());
                              for (const auto &e : actNode.edges) a.push_back(e.action);
                              return a; }();
                    std::unordered_set<std::uint64_t> childSeen;
                    for (int ai = 0; ai < (int)actions.size(); ++ai) {
                        BattleContext child = parent;
                        actions[ai].execute(child);
                        const std::uint64_t childHash =
                            CombatObservation::fromBattleContext(child).visibleHash();
                        if (!childSeen.insert(childHash).second) continue;   // dedup children
                        double pWinS = std::numeric_limits<double>::quiet_NaN();
                        double meanHpS = std::numeric_limits<double>::quiet_NaN();
                        long long totalS = 0;
                        long long nonTermS = 0;
                        double modelPred = std::numeric_limits<double>::quiet_NaN();
                        if (child.outcome != Outcome::UNDECIDED) {
                            const bool won = child.outcome == Outcome::PLAYER_VICTORY;
                            pWinS = won ? 1.0 : 0.0;
                            meanHpS = won ? (double)child.player.curHp
                                          : std::numeric_limits<double>::quiet_NaN();
                            totalS = 1;
                        } else {
                            TerminalRecordingSearcher cs3(child, 0, 0, particleCount);
                            cs3.rng.seed(gs);
                            cs3.installSharedParticles(crnSeed.belief, crnSeed.crnParticles);
                            cs3.searchToTotal(siblingBudget);
                            totalS = cs3.totalTerminals;
                            nonTermS = std::max(0LL, (long long)siblingBudget - totalS);
                            pWinS = totalS > 0 ? (double)cs3.winCount / totalS
                                               : std::numeric_limits<double>::quiet_NaN();
                            meanHpS = cs3.winCount > 0 ? (double)cs3.winHpSum / cs3.winCount
                                                       : std::numeric_limits<double>::quiet_NaN();
                        }
                        if (search::g_usePVNet && search::g_combatPVNet.loaded())
                            modelPred = search::g_combatPVNet.leafValue(child, search::g_riskLambda);
                        else if (search::g_useVNet && search::g_combatVNet.loaded())
                            modelPred = search::g_combatVNet.predict(child);
                        srow << le.seed << ',' << le.fightIdx << ',' << le.decIdx << ','
                             << le.obsHash << ',' << childHash << ',' << ai << ','
                             << pWinS << ',' << meanHpS << ',' << totalS << ','
                             << modelPred << ',' << nonTermS << '\n';
                    }
                }
            }
        }
        outLeaf[(std::size_t)i] = lrow.str();
        outSib[(std::size_t)i] = srow.str();
        if (++done % 10 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d leaves, %.0fs (%.2fs/leaf)\n",
                        done.load(), n, el, el / done.load());
            std::fflush(stdout);
        }
    }
    for (int i = 0; i < n; ++i) {
        lf << outLeaf[(std::size_t)i];
        sf << outSib[(std::size_t)i];
        leafRows += std::count(outLeaf[(std::size_t)i].begin(), outLeaf[(std::size_t)i].end(), '\n');
        siblingRows += std::count(outSib[(std::size_t)i].begin(), outSib[(std::size_t)i].end(), '\n');
    }
    lf.flush(); sf.flush();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld leaf rows + %lld sibling rows from %d leaves in %.1fs\n",
                leafRows, siblingRows, n, wall);
}

// ---------------------------------------------------------------------------
// STRATEGIC data generation: one CSV row per LEGAL action at each OOC decision,
// with full rich state, structured candidate fields, a chosen flag, and the
// terminal outcome. Feeds Phase 5 run-level model training.
// Row schema (strategicHeader()):
//   seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,
//   <1017 rich state>,won,endFloor,endHp
// - action: raw packed GameAction bits (uint32).
// - actionType: rewardsActionType (0..6) on REWARDS/SHOP, CardSelectScreenType
//   on CARD_SELECT, else -1.
// - c1..c3: raw GameAction indices (idx1..idx3), 0 when unused.
// - cand1..c3: screen-specific resolved candidate identities (-1 when N/A):
//   REWARDS: GOLD=gold amt; CARD=cardId,upgraded; RELIC=relicId; POTION=potionId;
//            KEY=2 (emerald) / 3 (sapphire).
//   SHOP:    CARD=cardId,price,upgraded; RELIC=relicId,price; POTION=potionId,price;
//            CARD_REMOVE=removeCost.
//   EVENT:   eventId, option index.  MAP: childX, childY, childRoom.
//   BOSS_RELIC_REWARDS: relicId.  CARD_SELECT: cardId, selectScreenType.
//   REST/TREASURE: -1 (option semantics live in c1 / screen state).
static std::string strategicStateCols() {
    std::string h = richHeader();                       // "seed,<state...>,curMapY,won,finalFloor,endHp"
    const auto comma = h.find(',');
    std::string rest = h.substr(comma + 1);             // drop the "seed," prefix
    const auto wonPos = rest.rfind(",won,finalFloor,endHp");
    return rest.substr(0, wonPos);                      // state columns only, in richRow() order
}

static std::string strategicHeader() {
    return "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,"
         + strategicStateCols() + ",won,endFloor,endHp\n";
}

// Successor-state fingerprint used to detect which legal action the policy
// actually executed. All fields are ints; two actions with identical
// fingerprints are indistinguishable at this decision.
struct StratFingerprint {
    int screen, act, floor, hp, maxHp, gold;
    int keys[3], potionCount, potions[5];
    int deckSize, relicCount;
    long long deckSum, deckUpSum, deckHash;   // deck-content digest (non-last cards)
    long long relicSum, relicHash;            // relic-identity digest
    long long selSum, selHash;                // info.haveSelectedCards digest (multi-select picks)
    int bottledLast;                          // last bottled card id (-1)
    int goldRew, cardRew, relicRew, potionRew;
    int emeraldKey, sapphireKey, mapX, mapY, selectSize;

    bool operator==(const StratFingerprint &o) const {
        if (screen != o.screen || act != o.act || floor != o.floor || hp != o.hp
            || maxHp != o.maxHp || gold != o.gold || potionCount != o.potionCount
            || deckSize != o.deckSize || relicCount != o.relicCount
            || deckSum != o.deckSum || deckUpSum != o.deckUpSum || deckHash != o.deckHash
            || relicSum != o.relicSum || relicHash != o.relicHash
            || selSum != o.selSum || selHash != o.selHash
            || bottledLast != o.bottledLast || goldRew != o.goldRew || cardRew != o.cardRew
            || relicRew != o.relicRew || potionRew != o.potionRew
            || emeraldKey != o.emeraldKey || sapphireKey != o.sapphireKey
            || mapX != o.mapX || mapY != o.mapY || selectSize != o.selectSize)
            return false;
        for (int i = 0; i < 3; ++i) if (keys[i] != o.keys[i]) return false;
        for (int i = 0; i < 5; ++i) if (potions[i] != o.potions[i]) return false;
        return true;
    }
};
static StratFingerprint stratFingerprint(const GameContext &gc) {
    StratFingerprint f{};
    f.screen = (int)gc.screenState; f.act = gc.act; f.floor = gc.floorNum;
    f.hp = gc.curHp; f.maxHp = gc.maxHp; f.gold = gc.gold;
    f.keys[0] = gc.blueKey ? 1 : 0; f.keys[1] = gc.greenKey ? 1 : 0; f.keys[2] = gc.redKey ? 1 : 0;
    f.potionCount = gc.potionCount;
    for (int i = 0; i < 5; ++i)
        f.potions[i] = (i < (int)gc.potions.size()) ? (int)gc.potions[i] : -1;
    f.deckSize = (int)gc.deck.size();
    f.bottledLast = -1;
    for (int i = 0; i < f.deckSize; ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        f.deckSum += id; f.deckUpSum += c.isUpgraded() ? id : 0;
        f.deckHash = f.deckHash * 31 + id * 2 + (c.isUpgraded() ? 1 : 0);
        if (gc.deck.isCardBottled(i)) f.bottledLast = id;
    }
    f.relicCount = (int)gc.relics.relics.size();
    for (const auto &ri : gc.relics.relics) {
        const int rid = (int)ri.id;
        f.relicSum += rid; f.relicHash = f.relicHash * 31 + rid + 1;
    }
    for (const auto &sc : gc.info.haveSelectedCards) {
        const int sid = (int)sc.card.getId();
        f.selSum += sid * 2 + (sc.card.isUpgraded() ? 1 : 0);
        f.selHash = f.selHash * 31 + sc.deckIdx + 1;
    }
    const auto &r = gc.info.rewardsContainer;
    f.goldRew = r.goldRewardCount; f.cardRew = r.cardRewardCount;
    f.relicRew = r.relicCount; f.potionRew = r.potionCount;
    f.emeraldKey = r.emeraldKey ? 1 : 0; f.sapphireKey = r.sapphireKey ? 1 : 0;
    f.mapX = gc.curMapNodeX; f.mapY = gc.curMapNodeY;
    f.selectSize = (int)gc.info.toSelectCards.size();
    return f;
}

// Wave B regret gate (ooc-qwin-continuation.md Step 5): decide between the
// Q-max action and the deployed-default heuristic action a_heur.  a_heur is
// identified by the datagen-proven successor-fingerprint match
// (runStrategicGenSeed, one_combat.cpp:5844): the per-screen deployed-default
// heuristic runs on a pre-state copy (agent RNG stream copied, map detached)
// and the legal action whose successor matches the heuristic's successor wins.
// Returns the index of the action to take (Q-max when Qmax − Q(a_heur) > eps,
// else a_heur), or -1 when the heuristic action is unidentifiable — the
// RNG-tied fallback case (RNG-consuming heuristics, multi-step heuristics,
// indistinguishable successors), where the caller falls back to the margin rule.
static int regretGateChoose(const GameContext &pre,
                            const std::vector<search::GameAction> &actions,
                            const std::vector<double> &q, double eps,
                            void (*heuristic)(GameContext &, search::ScumSearchAgent2 &),
                            const search::ScumSearchAgent2 &liveAgent) {
    GameContext probe = pre;
    probe.map = std::make_shared<Map>(*pre.map);        // detach the shared map before probing
    search::ScumSearchAgent2 probeAgent;
    probeAgent.rng = liveAgent.rng;                     // the probe consumes the same stream the
    probeAgent.simulationCountBase = liveAgent.simulationCountBase;  // live heuristic would use
    heuristic(probe, probeAgent);
    const StratFingerprint realFp = stratFingerprint(probe);
    int heurIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext probe2 = pre;
        probe2.map = std::make_shared<Map>(*pre.map);
        actions[i].execute(probe2);                     // same per-action probe as the datagen
        if (stratFingerprint(probe2) == realFp) { heurIdx = i; break; }
    }
    if (heurIdx < 0) return -1;
    int bestIdx = -1;
    double best = -1e100;
    for (int i = 0; i < (int)q.size(); ++i) if (q[i] > best) { best = q[i]; bestIdx = i; }
    if (bestIdx < 0) return -1;
    return (best - q[heurIdx] > eps) ? bestIdx : heurIdx;
}

static void writeOocTrace(const GameContext &gc,
                          const std::vector<search::GameAction> &actions,
                          const std::vector<double> &q, int bestIdx, int takeIdx,
                          double best, double second, double threshold,
                          const char *rule, bool owned) {
    if (g_oocStrategicTracePath.empty()) return;
    t_oocStrategicTraceRows += std::to_string(gc.seed) + ','
        + std::to_string(t_oocStrategicTraceDecision++) + ','
        + std::to_string(gc.act) + ',' + std::to_string(gc.floorNum) + ','
        + std::to_string((int)gc.screenState) + ',' + std::to_string(actions.size()) + ',';
    for (size_t i = 0; i < actions.size(); ++i) {
        if (i) t_oocStrategicTraceRows += '|';
        t_oocStrategicTraceRows += std::to_string(actions[i].bits);
    }
    t_oocStrategicTraceRows += ",";
    for (size_t i = 0; i < q.size(); ++i) {
        if (i) t_oocStrategicTraceRows += '|';
        std::ostringstream s; s << q[i];
        t_oocStrategicTraceRows += s.str();
    }
    t_oocStrategicTraceRows += ',' + std::to_string(bestIdx) + ','
        + std::to_string(second > -1e90 ? best - second : -1.0) + ','
        + std::to_string(threshold) + ",-1," + std::to_string(takeIdx) + ','
        + rule + ',' + (owned ? "1" : "0") + '\n';
}

// Shared decision tail of every one-ply gate and the M2 route search: in
// regret mode (STS_OOC_STRATEGIC_GATE=regret) the Q-max action replaces the
// heuristic only when Qmax(s) − Q(a_heur) > ε; when a_heur is unidentifiable
// the decision falls back to the margin rule.  Returns whether the policy
// executed an action (the heuristic layer runs otherwise).
static bool regretGateTail(GameContext &gc, const std::vector<search::GameAction> &actions,
                           const std::vector<double> &q, int bestIdx, double best, double second,
                           double margin, double eps,
                           void (*heuristic)(GameContext &, search::ScumSearchAgent2 &),
                           const search::ScumSearchAgent2 &agent) {
    if (g_oocStrategicGateRegret) {
        const int take = regretGateChoose(gc, actions, q, eps, heuristic, agent);
        if (take >= 0) {
            if (!g_oocStrategicTracePath.empty())
                writeOocTrace(gc, actions, q, bestIdx, take, best, second, eps, "regret", true);
            actions[take].execute(gc);
            return true;
        }
    }
    if (bestIdx < 0 || best - second < margin) {
        if (!g_oocStrategicTracePath.empty())
            writeOocTrace(gc, actions, q, bestIdx, -1, best, second, margin, "margin", false);
        return false;
    }
    if (!g_oocStrategicTracePath.empty())
        writeOocTrace(gc, actions, q, bestIdx, bestIdx, best, second, margin, "margin", true);
    actions[bestIdx].execute(gc);
    return true;
}

// ---------------------------------------------------------------------------
// B1 SHOP BEAM SEARCH (ooc-next-wave-contracts.md §2): multi-step lookahead over
// the deterministic shop-purchase sequence, replacing the one-ply shop gate
// while STS_OOC_SHOP_BEAM=1 and a strategic net is loaded.
//
// Node state = (remaining shop offers, gold, deck, relics, potions). Each node
// is a detached counterfactual copy (map detached before any mutation).  Shop
// purchases are deterministic (only the leaf value head reads visible state), so
// the search uses no hidden-RNG information: with THE_COURIER restocks the
// clones advance the SAME copied RNG stream the live run will, producing exactly
// the visible restock a real player would see after the purchase.
//
// Expansion: SHOP_ROOM nodes expand every legal GameAction (affordable card/
// relic/potion buys, CARD_REMOVE, SKIP = leave); leave terminates the node as a
// leaf.  A CARD_REMOVE successor is a CARD_SELECT(REMOVE) screen; those nodes
// expand their removal-target picks (each returns to SHOP_ROOM with removeCost
// spent).  Any other successor screen (e.g. a bottled-relic pick) is rare and
// not part of the purchase contract: it terminates the branch as a leaf.
// Dedup: per-ply fingerprint (gold + offer set + StratFingerprint digests:
// deckSum/deckHash, relicSum/relicHash, potions, screen/select type).  The best
// `width` children by leaf value continue; the rest become buy-then-leave leaf
// candidates.  Every SHOP beam node's own state is a leaf candidate (leave).
//
// Termination: every shop-buy ply strictly spends gold, so depth is bounded by
// gold; the expanded-node budget (STS_OOC_SHOP_BEAM_BUDGET, default 4096) is a
// hard global guard for pathological shops.
// ---------------------------------------------------------------------------
static std::uint64_t shopBeamNodeFingerprint(const GameContext &gc) {
    const StratFingerprint f = stratFingerprint(gc);
    const Shop &s = gc.info.shop;
    std::uint64_t h = 1469598103934665603ULL;   // FNV-1a
    auto mix = [&h](std::uint64_t v) {
        for (int k = 0; k < 4; ++k) { h ^= v & 0xffff; h *= 1099511628211ULL; v >>= 16; }
    };
    mix((std::uint64_t)((std::uint32_t)(int)gc.screenState) << 8
        | (std::uint64_t)((std::uint32_t)(int)gc.info.selectScreenType));
    mix((std::uint64_t)(std::uint32_t)f.gold);
    mix((std::uint64_t)f.deckSum ^ ((std::uint64_t)f.deckUpSum << 1) ^ ((std::uint64_t)f.deckHash << 3));
    mix((std::uint64_t)f.relicSum ^ ((std::uint64_t)f.relicHash << 5));
    mix((std::uint64_t)(std::uint32_t)f.potionCount);
    for (int i = 0; i < 5; ++i) mix((std::uint64_t)(std::uint32_t)(f.potions[i] + 1));
    mix((std::uint64_t)(std::uint32_t)(s.removeCost + 1));
    for (int i = 0; i < 13; ++i) mix((std::uint64_t)(std::uint32_t)(s.prices[i] + 1));
    for (int i = 0; i < 7; ++i)
        mix((std::uint64_t)(std::uint32_t)(((int)s.cards[i].getId() + 1) * 2 + (s.cards[i].isUpgraded() ? 1 : 0)));
    for (int i = 0; i < 3; ++i) mix((std::uint64_t)(std::uint32_t)((int)s.relics[i] + 1));
    for (int i = 0; i < 3; ++i) mix((std::uint64_t)(std::uint32_t)((int)s.potions[i] + 1));
    return h;
}

// Terminal value of a candidate shop state: the per-screen value head on the
// SHOP screen (V3 rich state; V4 token-net glob when the token net is loaded).
static double shopBeamLeafValue(GameContext &gc) {
    // Score the leaf with the head of its ACTUAL successor screen (the V2
    // successor-scoring convention): the per-screen value heads are trained on
    // their own screens, and a post-shop state is not a SHOP screen. Screens
    // outside 1..8 (e.g. BATTLE) clamp to the last head, as predictValue does.
    const int scr = (int)gc.screenState;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        return g_oocStrategicTokNet.predictValue(ts.glob, scr);
    }
    return g_oocStrategicNet.predictValue(richFeatureVec(gc).data(), scr);
}

static bool oocShopBeamPolicy(GameContext &gc) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocShopBeam) return false;
    const bool inShop = gc.screenState == ScreenState::SHOP_ROOM;
    const bool inRemove = gc.screenState == ScreenState::CARD_SELECT
                          && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    if (!inShop && !inRemove) return false;

    using RT = search::GameAction::RewardsActionType;
    struct BeamNode {
        GameContext state;
        std::vector<search::GameAction> actions;
        double value;
    };

    const int width = std::max(4, std::min(256, g_oocShopBeamWidth));
    const int maxDepth = g_oocShopBeamDepth > 0 ? g_oocShopBeamDepth
                                                : std::numeric_limits<int>::max();
    const int maxExpanded = std::max(64, std::min(65536, g_oocShopBeamBudget));

    std::vector<BeamNode> beam;
    beam.push_back({detachedCounterfactualCopy(gc), {}, shopBeamLeafValue(gc)});

    double bestValue = -1e100;
    std::vector<search::GameAction> bestActions;
    int expanded = 0;

    for (int depth = 0; depth < maxDepth && !beam.empty(); ++depth) {
        std::vector<BeamNode> children;
        std::unordered_set<std::uint64_t> seen;
        children.reserve(beam.size() * 16);
        bool budgetHit = false;

        for (std::size_t bi = 0; bi < beam.size(); ++bi) {
            const BeamNode &node = beam[bi];
            const bool nodeShop = node.state.screenState == ScreenState::SHOP_ROOM;
            const std::vector<search::GameAction> legal =
                search::GameAction::getAllActionsInState(node.state);
            if (legal.empty()) continue;

            if (nodeShop) {
                // Leave (SKIP) terminates the node as a leaf on its own state;
                // a node that can only leave is scored the same way.
                if (node.value > bestValue) { bestValue = node.value; bestActions = node.actions; }
                if (legal.size() <= 1) continue;      // only leave left: no purchase possible
                for (const search::GameAction &a : legal) {
                    if (a.getRewardsActionType() == RT::SKIP) continue;
                    if (++expanded > maxExpanded) { budgetHit = true; break; }
                    BeamNode child;
                    child.state = detachedCounterfactualCopy(node.state);
                    a.execute(child.state);
                    child.actions = node.actions;
                    child.actions.push_back(a);
                    children.push_back(std::move(child));
                }
            } else {
                // CARD_SELECT(REMOVE) successor: expand the removal-target picks.
                for (const search::GameAction &a : legal) {
                    if (++expanded > maxExpanded) { budgetHit = true; break; }
                    BeamNode child;
                    child.state = detachedCounterfactualCopy(node.state);
                    a.execute(child.state);            // back to SHOP_ROOM
                    child.actions = node.actions;
                    child.actions.push_back(a);
                    children.push_back(std::move(child));
                }
            }
            if (budgetHit) {
                // The rest of the beam is not expanded: record their leave
                // leaves so no purchase sequence is lost from the candidates.
                for (std::size_t j = bi + 1; j < beam.size(); ++j)
                    if (beam[j].state.screenState == ScreenState::SHOP_ROOM
                        && beam[j].value > bestValue) {
                        bestValue = beam[j].value; bestActions = beam[j].actions;
                    }
                break;
            }
        }
        if (budgetHit) {
            // Remaining beam nodes were already recorded as leave-leaf candidates.
            for (BeamNode &child : children) child.value = shopBeamLeafValue(child.state);
            for (BeamNode &child : children)
                if (child.value > bestValue) { bestValue = child.value; bestActions = child.actions; }
            break;
        }

        // Dedup this ply's children by fingerprint, then keep the top `width`
        // by leaf value; dropped children are buy-then-leave leaf candidates.
        std::vector<BeamNode> kept;
        kept.reserve(children.size());
        for (BeamNode &child : children) {
            child.value = shopBeamLeafValue(child.state);
            if (!seen.insert(shopBeamNodeFingerprint(child.state)).second) continue;
            kept.push_back(std::move(child));
        }
        std::sort(kept.begin(), kept.end(),
                  [](const BeamNode &a, const BeamNode &b) { return a.value > b.value; });
        for (int i = (int)kept.size() - 1; i >= width; --i)
            if (kept[i].value > bestValue) { bestValue = kept[i].value; bestActions = kept[i].actions; }
        if (kept.size() > (size_t)width) kept.resize(width);
        if (kept.empty()) break;
        beam = std::move(kept);
    }

    if (bestActions.empty()) {
        // The beam's best-scoring decision is to leave (buy nothing).
        search::GameAction(RT::SKIP).execute(gc);
        return true;
    }
    bestActions[0].execute(gc);
    return true;
}

// Resolved candidate identities for one legal action in the current screen.
static void strategicCands(const GameContext &gc, const search::GameAction &a,
                           int &actionType, int &c1, int &c2, int &c3,
                           int &cand1, int &cand2, int &cand3) {
    using RT = search::GameAction::RewardsActionType;
    actionType = -1; c1 = a.getIdx1(); c2 = a.getIdx2(); c3 = a.getIdx3();
    cand1 = cand2 = cand3 = -1;
    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &r = gc.info.rewardsContainer;
            switch (t) {
                case RT::GOLD:
                    if (c1 >= 0 && c1 < r.goldRewardCount) cand1 = r.gold[c1];
                    break;
                case RT::CARD:
                    if (c1 >= 0 && c1 < r.cardRewardCount
                        && c2 >= 0 && c2 < (int)r.cardRewards[c1].size()) {
                        const Card &card = r.cardRewards[c1][c2];
                        cand1 = (int)card.getId(); cand2 = card.isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < r.relicCount) cand1 = (int)r.relics[c1]; break;
                case RT::POTION: if (c1 >= 0 && c1 < r.potionCount) cand1 = (int)r.potions[c1]; break;
                case RT::KEY: cand1 = r.emeraldKey ? 2 : 3; break;
                default: break;
            }
            break;
        }
        case ScreenState::SHOP_ROOM: {
            const auto t = a.getRewardsActionType();
            actionType = (int)t;
            const auto &s = gc.info.shop;
            switch (t) {
                case RT::CARD:
                    if (c1 >= 0 && c1 < 7) {
                        cand1 = (int)s.cards[c1].getId(); cand2 = s.cardPrice(c1);
                        cand3 = s.cards[c1].isUpgraded() ? 1 : 0;
                    }
                    break;
                case RT::RELIC: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.relics[c1]; cand2 = s.relicPrice(c1); } break;
                case RT::POTION: if (c1 >= 0 && c1 < 3) { cand1 = (int)s.potions[c1]; cand2 = s.potionPrice(c1); } break;
                case RT::CARD_REMOVE: cand1 = s.removeCost; break;
                default: break;
            }
            break;
        }
        case ScreenState::EVENT_SCREEN:
            cand1 = (int)gc.curEvent; cand2 = c1;
            break;
        case ScreenState::MAP_SCREEN: {
            cand1 = c1;
            const int ty = (gc.curMapNodeY == -1) ? 0 : gc.curMapNodeY + 1;
            cand2 = ty;
            if (c1 >= 0 && ty >= 0 && ty < 15 && c1 < 7)
                cand3 = (int)gc.map->nodes[ty][c1].room;
            break;
        }
        case ScreenState::BOSS_RELIC_REWARDS:
            if (c1 >= 0 && c1 < 3) cand1 = (int)gc.info.bossRelics[c1];
            break;
        case ScreenState::CARD_SELECT: {
            actionType = (int)gc.info.selectScreenType;
            if (c1 >= 0 && c1 < (int)gc.info.toSelectCards.size()) {
                cand1 = (int)gc.info.toSelectCards[c1].card.getId();
                cand2 = (int)gc.info.selectScreenType;
            }
            break;
        }
        default: break;
    }
}

// V4 decision-context entity (ooc-strategic-v4.md §2.5): the candidate card/
// relic/potion conditioning the action value (entType 0=none,1=card,2=relic,
// 3=potion), plus the gold-vs-price threshold feature (SHOP_ROOM cand2=price,
// REWARDS/GOLD cand1=gold amount; else 0).
static void tokEntity(const GameContext &gc, const search::GameAction &a,
                      int &entType, int &entId, float &goldGePrice) {
    using RT = search::GameAction::RewardsActionType;
    entType = 0; entId = -1; goldGePrice = 0.0f;
    switch (gc.screenState) {
        case ScreenState::REWARDS: {
            const RT t = a.getRewardsActionType();
            const auto &r = gc.info.rewardsContainer;
            switch (t) {
                case RT::GOLD:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.goldRewardCount)
                        goldGePrice = gc.gold >= r.gold[a.getIdx1()] ? 1.0f : 0.0f;
                    break;
                case RT::CARD: {
                    const int c1 = a.getIdx1(), c2 = a.getIdx2();
                    if (c1 >= 0 && c1 < r.cardRewardCount
                        && c2 >= 0 && c2 < (int)r.cardRewards[c1].size()) {
                        entType = 1; entId = (int)r.cardRewards[c1][c2].getId();
                    }
                    break;
                }
                case RT::RELIC:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.relicCount) { entType = 2; entId = (int)r.relics[a.getIdx1()]; }
                    break;
                case RT::POTION:
                    if (a.getIdx1() >= 0 && a.getIdx1() < r.potionCount) { entType = 3; entId = (int)r.potions[a.getIdx1()]; }
                    break;
                default: break;
            }
            break;
        }
        case ScreenState::SHOP_ROOM: {
            const RT t = a.getRewardsActionType();
            const auto &s = gc.info.shop;
            int price = -1;
            switch (t) {
                case RT::CARD:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 7) {
                        entType = 1; entId = (int)s.cards[a.getIdx1()].getId(); price = s.cardPrice(a.getIdx1());
                    }
                    break;
                case RT::RELIC:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 3) {
                        entType = 2; entId = (int)s.relics[a.getIdx1()]; price = s.relicPrice(a.getIdx1());
                    }
                    break;
                case RT::POTION:
                    if (a.getIdx1() >= 0 && a.getIdx1() < 3) {
                        entType = 3; entId = (int)s.potions[a.getIdx1()]; price = s.potionPrice(a.getIdx1());
                    }
                    break;
                default: break;
            }
            goldGePrice = (price >= 0 && gc.gold >= price) ? 1.0f : 0.0f;  // trainer parity: price<0 -> 0
            break;
        }
        case ScreenState::CARD_SELECT:
            if (a.getIdx1() >= 0 && a.getIdx1() < (int)gc.info.toSelectCards.size()) {
                entType = 1; entId = (int)gc.info.toSelectCards[a.getIdx1()].card.getId();
            }
            break;
        default: break;
    }
}

static std::string runStrategicGenSeed(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;

    std::vector<std::string> rows;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else Searcher2.
        if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        const int decIdx = (int)rows.size();
        for (const auto &a : actions) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            a.execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, a, actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << a.bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, path);
            rows.push_back(r.str());
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, path);
            rows.push_back(r.str());
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (const auto &row : rows)
        out << row << ',' << won << ',' << gc.floorNum << ',' << gc.curHp << '\n';
    return out.str();
}

// ── Shared strategic branch label evaluator (Tier-B contract) ──────────────
// Used by both strategicgen2 and strategicmarggen. Evaluates K=3 fights with
// bootstrap=true and the standard 150/100/50 sim schedule. Returns the same
// OocCounterfactualResult fields used by Tier-B label averaging.
static OocCounterfactualResult evaluateStrategicBranch(
    GameContext gc, std::uint64_t branchSeed, const PathHistory &path)
{
    return finishOocCounterfactual(std::move(gc), /*sims=*/0, branchSeed, path,
        g_strategicBranchFights, /*bootstrap=*/true,
        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
}

// ── Production V4 OOC step (frozen baseline) ───────────────────────────────
// Executes exactly one OOC decision using the current frozen V4 gate stack.
static void stepFrozenV4Ooc(GameContext &gc, search::ScumSearchAgent2 &agent) {
    const bool inRemove = gc.screenState == ScreenState::CARD_SELECT
                          && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState == ScreenState::BATTLE) {
        BattleContext bc; bc.init(gc);
        agent.playoutBattle(bc);
        bc.exitBattle(gc);
    } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        if (!oocActionNNPolicy(gc))
            if (!oocMapRouteSearchPolicy(gc, agent))
                if (!oocOnePlyMapPolicy(gc, agent))
                    search::GameAction(chooseMapAction(gc)).execute(gc);
    } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::REST_ROOM) {
        if (!oocActionNNPolicy(gc)) {
            if (!oocOnePlyRestPolicy(gc, agent)) {
                if (g_restWin && restWinPolicy(gc)) {}
                else agent.stepOutOfCombatPolicy(gc);
            }
        }
    } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::SHOP_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc))
                if (!oocOnePlyShopPolicy(gc, agent)) shopVPolicy(gc);
    } else if (inRemove) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc)) removeSelectVPolicy(gc);
    } else if (gc.screenState == ScreenState::REWARDS) {
        auto &r = gc.info.rewardsContainer;
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
        else {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyCardRewardPolicy(gc, agent)) serverCardRewardPolicy(gc);
        }
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) upgradeSelectWinPolicy(gc);
    } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
}

// Phase 13A is an offline-only audit.  M0 is kept in a separate net and is
// never consulted by stepFrozenV4Ooc; these helpers only score legal actions
// on a copied pre-decision state.
static OocStrategicTokNet g_phase13aM0Net;

struct Phase13aActionScore {
    int best = -1;
    double bestValue = -1e100;
    double secondValue = -1e100;
    std::vector<double> values;
};

static Phase13aActionScore phase13aScore(const GameContext &gc,
                                         const PathHistory &path,
                                         const std::vector<search::GameAction> &actions,
                                         OocStrategicTokNet &net) {
    Phase13aActionScore out;
    out.values.resize(actions.size(), -1e100);
    const TokState ts = buildTokState(gc, path);
    for (int i = 0; i < (int)actions.size(); ++i) {
        int at, c1, c2, c3, ca1, ca2, ca3;
        strategicCands(gc, actions[i], at, c1, c2, c3, ca1, ca2, ca3);
        const int cats[6] = {c1, c2, c3, ca1, ca2, ca3};
        int et, ei; float gg;
        tokEntity(gc, actions[i], et, ei, gg);
        const float entT[4] = {et == 0 ? 1.0f : 0.0f, et == 1 ? 1.0f : 0.0f,
                               et == 2 ? 1.0f : 0.0f, et == 3 ? 1.0f : 0.0f};
        const double v = net.predictActionValue(
            ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
            actions[i].bits, cats, at, (int)gc.screenState, entT, ei, gg);
        out.values[i] = v;
        if (v > out.bestValue) {
            out.secondValue = out.bestValue;
            out.bestValue = v;
            out.best = i;
        } else if (v > out.secondValue) {
            out.secondValue = v;
        }
    }
    return out;
}

static std::vector<search::GameAction> phase13aActions(const GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (gc.screenState == ScreenState::REWARDS
        && gc.info.rewardsContainer.cardRewardCount > 0) {
        const search::GameAction skip(RT::CARD,
                                      gc.info.rewardsContainer.cardRewardCount - 1, 5);
        bool found = false;
        for (const auto &a : actions) if (a.bits == skip.bits) found = true;
        if (!found) actions.push_back(skip);
    }
    return actions;
}

static bool phase13aOwnedScreen(const GameContext &gc,
                                const std::vector<search::GameAction> &actions) {
    if (g_oocStrategicGateRegret || actions.empty()) return false;
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN:
            return g_oocStrategicEvent;
        case ScreenState::BOSS_RELIC_REWARDS:
            return g_oocStrategicBossRelic;
        case ScreenState::TREASURE_ROOM:
            return g_oocStrategicTreasure;
        case ScreenState::REST_ROOM:
            return g_oocStrategicRest;
        case ScreenState::SHOP_ROOM:
            return g_oocStrategicShop;
        case ScreenState::CARD_SELECT:
            return g_oocStrategicRest
                && gc.info.selectScreenType == CardSelectScreenType::UPGRADE;
        case ScreenState::REWARDS: {
            const auto &r = gc.info.rewardsContainer;
            if (r.goldRewardCount > 0 || r.relicCount > 0 || r.potionCount > 0)
                return false;
            if (g_collectKeys && (r.emeraldKey || r.sapphireKey)) return false;
            return g_oocStrategicTokNet.ok && r.cardRewardCount > 0;
        }
        default:
            return false;
    }
}

static std::string phase13aCandidateHeader() {
    return "sourceSeed,decisionId,act,floor,screen,nActions,gateOwned,liveV4Idx,liveV4Margin,"
           "v4Idx,v4Bits,v4I1,v4I2,v4I3,m0Idx,m0Bits,m0I1,m0I2,m0I3,v4Margin,modelDelta,"
           "goldRewardCount,relicCount,potionCount,emeraldKey,sapphireKey\n";
}

static void phase13aCollect(int nSeeds, std::uint64_t seedOffset,
                            const std::string &outFile, int sims, int asc) {
    std::ofstream out(outFile);
    out << phase13aCandidateHeader();
    for (int si = 0; si < nSeeds; ++si) {
        const std::uint64_t seed = seedOffset + (std::uint64_t)si;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = sims;
        agent.rng = std::default_random_engine(seed);
        PathHistory path;
        t_curPath = &path;
        int decIdx = 0;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            path.update(gc);
            const auto actions = phase13aActions(gc);
            if (phase13aOwnedScreen(gc, actions)) {
                if (actions.size() >= 2 && g_oocStrategicTokNet.ok && g_phase13aM0Net.ok) {
                    const auto v4 = phase13aScore(gc, path, actions, g_oocStrategicTokNet);
                    const auto m0 = phase13aScore(gc, path, actions, g_phase13aM0Net);
                    const double margin = v4.bestValue - v4.secondValue;
                    const double delta = m0.values[m0.best] - m0.values[v4.best];
                    if (v4.best >= 0 && m0.best >= 0 && margin >= g_oocStrategicMargin
                        && m0.best != v4.best && delta >= 1.0) {
                        const auto &va = actions[v4.best];
                        const auto &ma = actions[m0.best];
                        out << seed << ',' << decIdx << ',' << gc.act << ',' << gc.floorNum
                            << ',' << (int)gc.screenState << ',' << actions.size() << ",1,"
                            << v4.best << ',' << margin << ',' << v4.best << ',' << va.bits << ',' << va.getIdx1() << ','
                            << va.getIdx2() << ',' << va.getIdx3() << ',' << m0.best << ','
                            << ma.bits << ',' << ma.getIdx1() << ',' << ma.getIdx2() << ','
                            << ma.getIdx3() << ',' << margin << ',' << delta << ','
                            << gc.info.rewardsContainer.goldRewardCount << ','
                            << gc.info.rewardsContainer.relicCount << ','
                            << gc.info.rewardsContainer.potionCount << ','
                            << (gc.info.rewardsContainer.emeraldKey ? 1 : 0) << ','
                            << (gc.info.rewardsContainer.sapphireKey ? 1 : 0) << '\n';
                    }
                }
            }
            if (phase13aOwnedScreen(gc, actions)) ++decIdx;
            stepFrozenV4Ooc(gc, agent);
        }
        t_curPath = nullptr;
    }
}

static bool phase13aReadManifestRow(const std::string &line,
                                    std::uint64_t &seed, int &decIdx, int &act,
                                    int &floor, int &screen, std::uint32_t &v4Bits,
                                    std::uint32_t &m0Bits, double &margin,
                                    double &modelDelta) {
    std::stringstream ss(line); std::string x;
    std::vector<std::string> c;
    while (std::getline(ss, x, ',')) c.push_back(x);
    if (c.size() < 21) return false;
    try {
        seed = std::stoull(c[0]); decIdx = std::stoi(c[1]); act = std::stoi(c[2]);
        floor = std::stoi(c[3]); screen = std::stoi(c[4]);
        v4Bits = (std::uint32_t)std::stoull(c[10]);
        m0Bits = (std::uint32_t)std::stoull(c[15]);
        margin = std::stod(c[19]); modelDelta = std::stod(c[20]);
    } catch (...) { return false; }
    return true;
}

static std::string phase13aActionMeta(const GameContext &gc,
                                      const search::GameAction &a) {
    int at, c1, c2, c3, ca1, ca2, ca3;
    strategicCands(gc, a, at, c1, c2, c3, ca1, ca2, ca3);
    std::ostringstream out;
    out << at << ':' << c1 << ':' << c2 << ':' << c3 << ':' << ca1 << ':' << ca2 << ':' << ca3;
    return out.str();
}

static void phase13aEvaluate(const std::string &manifestFile,
                             const std::string &outFile, int asc,
                             int referenceSims = 1000, int futures = 4,
                             int futureStart = 0, bool referenceOnly = false) {
    std::ifstream in(manifestFile); std::string line;
    std::ofstream out(outFile);
    out << "sourceSeed,decisionId,act,floor,screen,actionRole,actionBits,idx1,idx2,idx3,"
           "actionMeta,v4Margin,modelDelta,evaluator,future,continuationSeed,won,floorEnd,hpEnd,"
           "bootstrap,valid,healthDelta\n";
    std::getline(in, line);
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::uint64_t seed; std::uint32_t v4Bits, m0Bits;
        int targetDecIdx, act, floor, screen; double margin, delta;
        if (!phase13aReadManifestRow(line, seed, targetDecIdx, act, floor, screen,
                                     v4Bits, m0Bits, margin, delta)) continue;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent; agent.simulationCountBase = 1000;
        agent.rng = std::default_random_engine(seed);
        PathHistory path; t_curPath = &path;
        int decIdx = 0;
        bool found = false;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            path.update(gc);
            const auto actions = phase13aActions(gc);
            if (phase13aOwnedScreen(gc, actions)) {
                if (actions.size() >= 2 && decIdx == targetDecIdx) {
                    int vi = -1, mi = -1;
                    for (int i = 0; i < (int)actions.size(); ++i) {
                        if (actions[i].bits == v4Bits && vi < 0) vi = i;
                        if (actions[i].bits == m0Bits && mi < 0) mi = i;
                    }
                    if (vi >= 0 && mi >= 0 && gc.act == act && gc.floorNum == floor
                        && (int)gc.screenState == screen) {
                        found = true;
                        const PathHistory prePath = path;
                        for (int fi = 0; fi < futures; ++fi) {
                            const int f = futureStart + fi;
                            const std::uint64_t contSeed = seed ^
                                ((std::uint64_t)(targetDecIdx + 1) * 0x9e3779b97f4a7c15ULL) ^
                                ((std::uint64_t)(f + 1) * 0xbf58476d1ce4e5b9ULL);
                            for (int ai : {vi, mi}) {
                                const char role = ai == vi ? 'V' : 'M';
                                GameContext branch = detachedCounterfactualCopy(gc);
                                actions[ai].execute(branch);
                                if (!referenceOnly) {
                                    const int healthBefore = search::g_simHealthFailureCount;
                                    const OocCounterfactualResult s = evaluateStrategicBranch(
                                        branch, contSeed, prePath);
                                    out << seed << ',' << decIdx << ',' << act << ',' << floor << ',' << screen
                                        << ',' << role << ',' << actions[ai].bits << ',' << actions[ai].getIdx1()
                                        << ',' << actions[ai].getIdx2() << ',' << actions[ai].getIdx3() << ','
                                        << phase13aActionMeta(gc, actions[ai]) << ',' << margin << ',' << delta
                                        << ",S," << f << ',' << contSeed << ',' << s.won << ',' << s.floor
                                        << ',' << s.hp << ',' << s.bootstrapped << ',' << (s.valid ? 1 : 0)
                                        << ',' << (search::g_simHealthFailureCount - healthBefore) << '\n';
                                }
                                GameContext refBranch = detachedCounterfactualCopy(gc);
                                actions[ai].execute(refBranch);
                                const int refHealthBefore = search::g_simHealthFailureCount;
                                const OocCounterfactualResult r = finishOocCounterfactual(
                                    std::move(refBranch), referenceSims, contSeed, prePath, -1, false,
                                    nullptr, 0, nullptr, false);
                                out << seed << ',' << decIdx << ',' << act << ',' << floor << ',' << screen
                                    << ',' << role << ',' << actions[ai].bits << ',' << actions[ai].getIdx1()
                                    << ',' << actions[ai].getIdx2() << ',' << actions[ai].getIdx3() << ','
                                    << phase13aActionMeta(gc, actions[ai]) << ',' << margin << ',' << delta
                                    << ",R," << f << ',' << contSeed << ',' << r.won << ',' << r.floor
                                    << ',' << r.hp << ',' << r.bootstrapped << ',' << (r.valid ? 1 : 0)
                                    << ',' << (search::g_simHealthFailureCount - refHealthBefore) << '\n';
                            }
                        }
                    }
                }
            }
            if (phase13aOwnedScreen(gc, actions)) ++decIdx;
            stepFrozenV4Ooc(gc, agent);
        }
        t_curPath = nullptr;
        if (!found) std::cerr << "phase13a: manifest decision not replayed seed=" << seed
                              << " decision=" << targetDecIdx << '\n';
    }
}

// ── Hidden-future marginalization diagnostic ───────────────────────────────
// For each sampled OOC decision, evaluate every legal action under both:
//   Regime F: fixed hidden world (current Tier-B style)
//   Regime M: encounter-marginalized (resample hidden encounters per sample)
// All actions in a sample share the same hidden world (CRN pairing).

struct MargResult { double won, hp, floor, boot; int survivedH; };

static MargResult finishMargCf(GameContext gc, std::uint64_t branchSeed,
                                const PathHistory &path) {
    OocCounterfactualResult r = evaluateStrategicBranch(
        std::move(gc), branchSeed, path);
    return {r.won, r.hp, r.floor, (double)r.bootstrapped, r.survivedH ? 1 : 0};
}

static void strategicMargGen(int nSeeds, int outerSims,
                             int H, int maxPerRun, const std::string &outFile,
                             long long seedOffset) {
    std::ofstream out(outFile);
    out << "seed,decIdx,act,floor,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,"
           "continuationSeed,hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,utility,"
           "survivedH,continuationValue,qSample,"
           "fallbackIdx,fallbackExact,chosenIdx,chosenExact,"
           "v4ModelIdx,v4Margin,v4Threshold,v4Fired,v4ExecutedIdx,v4Override,"
           "richState,actionBits,actionType,c1,c2,c3,cand1,cand2,cand3,hiddenChanged,"
           "sourceWon,sourceFloor,sourceHp\n";
    out.flush();
    auto t0 = std::chrono::steady_clock::now();
    std::mutex outMtx;
    int totalDecisions = 0;
    const double v4Threshold = g_oocStrategicMargin;

    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::uint64_t seed = (std::uint64_t)(seedOffset + s);

        // ── Pass 1: play full source run, collect eligible decision snapshots ──
        struct DecisionSnap {
            GameContext pre;
            PathHistory prePath;
            std::vector<search::GameAction> actions;
            int decIdx, screen, gateKind, actNum, floorNum;
            std::string stateRow;
        };
        std::vector<DecisionSnap> snaps;
        {
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            int decIdx = 0;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                int screen = (int)gc.screenState;
                int gateKind = 0;
                bool isOwned = false;
                if (screen == 1) { gateKind = 1; isOwned = true; }
                else if (screen == 2) { auto &r = gc.info.rewardsContainer; if (r.cardRewardCount > 0) { gateKind = 2; isOwned = true; } }
                else if (screen == 3) { gateKind = 3; isOwned = true; }
                else if (screen == 4) { if (gc.info.selectScreenType == CardSelectScreenType::UPGRADE) { gateKind = 4; isOwned = true; } }
                else if (screen == 6) { gateKind = 5; isOwned = true; }
                else if (screen == 7) { gateKind = 6; isOwned = true; }
                else if (screen == 8) { gateKind = 7; isOwned = true; }

                if (isOwned) {
                    GameContext pre = detachedCounterfactualCopy(gc);
                    auto actions = search::GameAction::getAllActionsInState(gc);
                    if (actions.size() >= 2) {
                        snaps.push_back({std::move(pre), path, std::move(actions),
                                         decIdx, screen, gateKind, gc.act, gc.floorNum,
                                         richRow(pre, path)});
                    }
                    ++decIdx;
                }
                stepFrozenV4Ooc(gc, agent);
            }
            t_curPath = nullptr;
        }

        // ── Uniform sample up to maxPerRun decisions ──
        int nSnaps = (int)snaps.size();
        int nSample = std::min(maxPerRun, nSnaps);
        if (nSnaps > maxPerRun) {
            std::mt19937_64 rng(seed ^ 0x9e3779b97f4a7c15ULL);
            for (int i = 0; i < nSample; ++i) {
                int j = i + (int)(rng() % (std::uint64_t)(nSnaps - i));
                std::swap(snaps[i], snaps[j]);
            }
        }
        snaps.resize(nSample);

        // ── Pass 2: evaluate sampled decisions ──
        std::ostringstream local;
        int localDecisions = 0;
        int sourceWon = 0, sourceFloor = 0, sourceHp = 0;
        {
            // Re-run the source game to get terminal outcome
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                stepFrozenV4Ooc(gc, agent);
            }
            sourceWon = (gc.outcome == GameOutcome::PLAYER_VICTORY) ? 1 : 0;
            sourceFloor = gc.floorNum;
            sourceHp = gc.curHp;
            t_curPath = nullptr;
        }

        {
            search::ScumSearchAgent2 evalAgent;
            evalAgent.simulationCountBase = outerSims;
            evalAgent.rng = std::default_random_engine(seed);
        for (auto &snap : snaps) {
            auto &pre = snap.pre; auto &prePath = snap.prePath;
            auto &actions = snap.actions;
            int screen = snap.screen, gateKind = snap.gateKind;
            int actNum = snap.actNum, floorNum = snap.floorNum;
            int decIdx = snap.decIdx;
            std::string &stateRow = snap.stateRow;

            // Per-action metadata
            std::vector<std::string> actionMetas;
            for (int ai = 0; ai < (int)actions.size(); ++ai) {
                int at, c1v, c2v, c3v, ca1, ca2, ca3;
                strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                char buf[256];
                std::snprintf(buf, sizeof(buf), "%u,%d,%d,%d,%d,%d,%d,%d",
                              actions[ai].bits, at, c1v, c2v, c3v, ca1, ca2, ca3);
                actionMetas.push_back(buf);
            }

            // Fallback via fingerprint (abbreviated — identical to existing code)
            int fallbackIdx = -1, fallbackExact = 0;
            {
                GameContext fbGc = detachedCounterfactualCopy(pre);
                if (screen == 1) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 2) serverCardRewardPolicy(fbGc);
                else if (screen == 3) { if (g_bossRelicV) bossRelicVPolicy(fbGc); else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 4) upgradeSelectWinPolicy(fbGc);
                else if (screen == 6) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 7) { if (g_restWin && restWinPolicy(fbGc)) {} else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 8) shopVPolicy(fbGc);
                auto fbFp = stratFingerprint(fbGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == fbFp) {
                        if (fallbackIdx < 0) { fallbackIdx = ai; fallbackExact = 1; }
                        else { fallbackExact = 0; break; }
                    }
                }
            }

            // Source chosen
            int chosenIdx = -1, chosenExact = 0;
            {
                GameContext postGc = detachedCounterfactualCopy(pre);
                stepFrozenV4Ooc(postGc, evalAgent);
                auto postFp = stratFingerprint(postGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == postFp) {
                        if (chosenIdx < 0) { chosenIdx = ai; chosenExact = 1; }
                        else { chosenExact = 0; break; }
                    }
                }
            }

            // V4 predictions
            int v4BestIdx = -1; double v4Margin = 0; bool v4Fired = false;
            if (g_oocStrategicTokNet.ok) {
                TokState ts = buildTokState(pre, prePath);
                double bestV4 = -1e100, secondV4 = -1e100;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    int at, c1v, c2v, c3v, ca1, ca2, ca3;
                    strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                    const int cats[6] = {c1v, c2v, c3v, ca1, ca2, ca3};
                    int et, ei; float gg;
                    tokEntity(pre, actions[ai], et, ei, gg);
                    const float entT[4] = {et==0?1.f:0.f, et==1?1.f:0.f, et==2?1.f:0.f, et==3?1.f:0.f};
                    double v = g_oocStrategicTokNet.predictActionValue(
                        ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                        actions[ai].bits, cats, at, screen, entT, ei, gg);
                    if (v > bestV4) { secondV4 = bestV4; bestV4 = v; v4BestIdx = ai; }
                    else if (v > secondV4) secondV4 = v;
                }
                v4Margin = bestV4 - secondV4;
                v4Fired = v4Margin >= v4Threshold;
            }
            int v4ExecutedIdx = (v4Fired && v4BestIdx >= 0) ? v4BestIdx : fallbackIdx;
            int v4Override = (fallbackExact == 1 && v4Fired && v4BestIdx >= 0 && v4BestIdx != fallbackIdx) ? 1 : 0;

            std::uint64_t baseSeed = seed ^ ((std::uint64_t)decIdx * 0x9e3779b97f4a7c15ULL);
            if (!baseSeed) baseSeed = 1;

            // EMIT_ROW macro (same as before)
            #define EMIT_ROW(regimeStr, contSeed, hiddenSeedVal, hiddenChangedVal) \
                local << seed << ',' << decIdx << ',' << actNum << ',' << floorNum \
                      << ',' << screen << ',' << gateKind << ',' << ai << ',' \
                      << actions.size() << ',' << h << ',' << regimeStr << ',' << contSeed << ',' << hiddenSeedVal << ',' \
                      << r.won << ',' << r.hp << ',' << r.floor << ',' << r.boot << ',' \
                      << (10.0*r.won+r.hp) << ',' << r.survivedH << ',' << r.won << ',' \
                      << (r.survivedH * r.won) << ',' << fallbackIdx << ',' << fallbackExact << ',' \
                      << chosenIdx << ',' << chosenExact << ',' \
                      << v4BestIdx << ',' << v4Margin << ',' << v4Threshold << ',' \
                      << (v4Fired?1:0) << ',' << v4ExecutedIdx << ',' << v4Override << ',' \
                      << csvQuote(stateRow) << ',' << actionMetas[ai] << ',' << hiddenChangedVal << ",0,0,0\n";

            // Regime F, I, M (identical to existing)
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("fixed", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < std::min(H, 2); ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg_id", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                std::uint64_t hiddenSeed = baseSeed ^ ((std::uint64_t)(h + H) * 0x9e3779b97f4a7c15ULL);
                if (!contSeed) contSeed = 1; if (!hiddenSeed) hiddenSeed = 1;
                GameContext hiddenBase = detachedCounterfactualCopy(pre);
                std::uint64_t hashBefore = 0, hashAfter = 0;
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                resampleRemainingActEncounters(hiddenBase, hiddenSeed);
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                int hiddenChanged = (hashBefore != hashAfter) ? 1 : 0;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(hiddenBase);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg", contSeed, hiddenSeed, hiddenChanged)
                }
            }
            #undef EMIT_ROW
            ++localDecisions;
        }
        }  // end evalAgent scope

        // Source outcome post-processing
        std::string prefix = std::to_string(sourceWon) + "," + std::to_string(sourceFloor) + "," + std::to_string(sourceHp);
        std::string localStr = local.str();
        std::string from = ",0,0,0\n";
        std::string to = "," + prefix + "\n";
        size_t pos = 0;
        while ((pos = localStr.find(from, pos)) != std::string::npos) {
            localStr.replace(pos, from.length(), to);
            pos += to.length();
        }

        #pragma omp critical(marg_write4)
        {
            out << localStr; out.flush();
            totalDecisions += localDecisions;
            if (totalDecisions % 10 == 0 || totalDecisions <= 5) {
                double el = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d decisions, %.0fs (%.1fs/dec)\n",
                            totalDecisions, el, el / std::max(1, totalDecisions));
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %d decisions to %s in %.1fs\n", totalDecisions, outFile.c_str(), wall);
}

// Strong, bounded full-run adjudication for decisions selected offline by
// tools/analyze_ooc_factor.py.  This is a diagnostic mode only: it replays the
// frozen source trajectory, evaluates exactly the two manifest actions, and
// never feeds a result back into live gameplay.
struct OocFactorManifestRow {
    std::uint64_t seed;
    int decIdx, act, floor, screen;
    std::uint32_t currentBits, factorBits;
    std::array<int,7> currentDescriptor, factorDescriptor;
};

struct OocFactorResolvedDecision {
    OocFactorManifestRow manifest;
    GameContext pre;
    PathHistory prePath;
    std::vector<search::GameAction> actions;
    int currentIdx, factorIdx;
};

static void oocFactorEvaluate(const std::string &manifestFile,
                              const std::string &outFile, int referenceSims,
                              int futures, int futureStart, int expectedDecisions,
                              bool marginalTradeoff = false,
                              bool boundedK3 = false,
                              bool semanticFullRun = false) {
    std::ifstream in(manifestFile);
    if (!in) throw std::runtime_error("oocfactoreval: cannot open manifest");
    std::string line;
    std::getline(in, line);
    if (line.empty()) throw std::runtime_error("oocfactoreval: manifest header is missing");
    std::vector<std::string> header;
    { std::stringstream hs(line); std::string h;
      while (std::getline(hs, h, ',')) {
          if (!h.empty() && h.back() == '\r') h.pop_back();
          if (h.size() >= 2 && h.front() == '"' && h.back() == '"')
              h = h.substr(1, h.size() - 2);
          header.push_back(h);
      } }
    std::unordered_map<std::string,int> col;
    for (int i = 0; i < (int)header.size(); ++i) col[header[i]] = i;
    for (const char *name : {"seed","decIdx","act","floor","screen"})
        if (!col.count(name)) throw std::runtime_error("oocfactoreval: manifest header mismatch");
    const char *safeBitsCol = col.count("safeActionBits") ? "safeActionBits" : "safeBits";
    const char *strengthBitsCol = col.count("strengthActionBits") ? "strengthActionBits" : "strengthBits";
    if (marginalTradeoff && (!col.count(safeBitsCol) || !col.count(strengthBitsCol)))
        throw std::runtime_error("oocfactoreval: marginal manifest header mismatch");
    const char *safeDescriptorNames[] = {
        "safeActionType","safeC1","safeC2","safeC3","safeCand1","safeCand2","safeCand3"};
    const char *strengthDescriptorNames[] = {
        "strengthActionType","strengthC1","strengthC2","strengthC3",
        "strengthCand1","strengthCand2","strengthCand3"};
    const bool semanticResolution = boundedK3 || semanticFullRun;
    if (semanticResolution) {
        for (const char *name : safeDescriptorNames)
            if (!col.count(name)) throw std::runtime_error("oocfactoreval: missing semantic column " + std::string(name));
        for (const char *name : strengthDescriptorNames)
            if (!col.count(name)) throw std::runtime_error("oocfactoreval: missing semantic column " + std::string(name));
    }
    std::vector<OocFactorManifestRow> manifest;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line); std::string cell;
        std::vector<std::string> c;
        while (std::getline(ss, cell, ',')) {
            if (!cell.empty() && cell.back() == '\r') cell.pop_back();
            if (cell.size() >= 2 && cell.front() == '"' && cell.back() == '"')
                cell = cell.substr(1, cell.size() - 2);
            c.push_back(cell);
        }
        if ((!marginalTradeoff && c.size() != 7)
                || (marginalTradeoff && c.size() < 7))
            throw std::runtime_error("oocfactoreval: malformed manifest row");
        auto at = [&](const char *name) -> const std::string& { return c.at(col.at(name)); };
        std::array<int,7> safeDescriptor{}, strengthDescriptor{};
        if (semanticResolution) {
            for (int i = 0; i < 7; ++i) {
                safeDescriptor[i] = std::stoi(at(safeDescriptorNames[i]));
                strengthDescriptor[i] = std::stoi(at(strengthDescriptorNames[i]));
            }
            if (safeDescriptor == strengthDescriptor)
                throw std::runtime_error("oocfactoreval: safe and strength descriptors are identical");
        }
        manifest.push_back({std::stoull(at("seed")), std::stoi(at("decIdx")),
                            std::stoi(at("act")), std::stoi(at("floor")),
                            std::stoi(at("screen")),
                            (std::uint32_t)std::stoull(at(marginalTradeoff ? safeBitsCol : "currentBits")),
                            (std::uint32_t)std::stoull(at(marginalTradeoff ? strengthBitsCol : "factorBits")),
                            safeDescriptor, strengthDescriptor});
    }
    if ((int)manifest.size() != expectedDecisions)
        throw std::runtime_error("oocfactoreval: guarded decision count does not match manifest");

    // Resolve the complete manifest before opening the output or starting any
    // expensive full-run continuation.  A producer/evaluator indexing drift
    // therefore fails atomically instead of leaving a partial adjudication.
    std::vector<OocFactorResolvedDecision> resolved;
    resolved.reserve(manifest.size());
    std::ofstream preflight;
    if (futures == 0) {
        preflight.open(outFile);
        if (!preflight) throw std::runtime_error("oocfactoreval: cannot open preflight output");
        preflight << "seed,decIdx,act,floor,screen,replayValid,matchedDecision,"
                     "safeMatchCount,strengthMatchCount\n";
    }
    for (const auto &m : manifest) {
        GameContext gc(CharacterClass::IRONCLAD, m.seed, 0);
        vDisconnect();
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = 1000;
        agent.rng = std::default_random_engine(m.seed);
        PathHistory path; t_curPath = &path;
        int decIdx = 0, safeMatchCount = 0, strengthMatchCount = 0;
        bool found = false, matchedDecision = false;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            path.update(gc);
            const int screen = (int)gc.screenState;
            bool eligible = screen == 1 || screen == 3 || screen == 6
                         || screen == 7 || screen == 8;
            if (screen == 2)
                eligible = gc.info.rewardsContainer.cardRewardCount > 0;
            if (screen == 4)
                eligible = gc.info.selectScreenType == CardSelectScreenType::UPGRADE;
            if (eligible) {
                const auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.size() >= 2) {
                    if (decIdx == m.decIdx && gc.act == m.act
                        && gc.floorNum == m.floor && screen == m.screen) {
                        matchedDecision = true;
                        int ci = -1, fi = -1;
                        for (int i = 0; i < (int)actions.size(); ++i) {
                            if (semanticResolution) {
                                int at,c1,c2,c3,ca1,ca2,ca3;
                                strategicCands(gc, actions[i], at,c1,c2,c3,ca1,ca2,ca3);
                                const std::array<int,7> descriptor{at,c1,c2,c3,ca1,ca2,ca3};
                                if (descriptor == m.currentDescriptor) { ci = i; ++safeMatchCount; }
                                if (descriptor == m.factorDescriptor) { fi = i; ++strengthMatchCount; }
                            } else {
                                if (actions[i].bits == m.currentBits && ci < 0) ci = i;
                                if (actions[i].bits == m.factorBits && fi < 0) fi = i;
                            }
                        }
                        if (semanticResolution && safeMatchCount != 1) ci = -1;
                        if (semanticResolution && strengthMatchCount != 1) fi = -1;
                        if (ci >= 0 && fi >= 0) {
                            found = true;
                            resolved.push_back({m, detachedCounterfactualCopy(gc), path,
                                                actions, ci, fi});
                        }
                    }
                }
                ++decIdx;
            }
            if (found) break;
            stepFrozenV4Ooc(gc, agent);
        }
        t_curPath = nullptr;
        if (futures == 0) {
            preflight << m.seed << ',' << m.decIdx << ',' << m.act << ',' << m.floor
                      << ',' << m.screen << ',' << (found ? 1 : 0) << ','
                      << (matchedDecision ? 1 : 0) << ',' << safeMatchCount << ','
                      << strengthMatchCount << '\n';
        } else if (!found) {
            throw std::runtime_error("oocfactoreval: manifest decision/action did not replay");
        }
    }
    std::cout << "oocfactoreval preflight resolved " << resolved.size() << '/'
              << manifest.size() << " decisions\n";
    if (futures == 0) {
        preflight.close();
        if (resolved.size() != manifest.size())
            throw std::runtime_error("oocfactoreval: preflight did not resolve complete manifest");
        return;
    }

    std::ofstream out(outFile);
    if (!out) throw std::runtime_error("oocfactoreval: cannot open output");
    if (boundedK3) {
        out << "seed,decIdx,act,floor,screen,role,actionBits,future,continuationSeed,"
               "hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,survivedH,"
               "continuationValue,qProduct,denseK3,valid\n";
    } else if (marginalTradeoff) {
        out << "seed,decIdx,act,floor,screen,role,actionBits,future,continuationSeed,"
               "hiddenSeed,won,floorEnd,hpEnd,adjudicatedValue,valid\n";
    } else {
        out << "seed,decIdx,act,floor,screen,role,actionBits,future,continuationSeed,"
               "won,floorEnd,hpEnd,adjudicatedValue,valid\n";
    }
    for (const auto &d : resolved) {
        const auto &m = d.manifest;
        for (int j = 0; j < futures; ++j) {
            const int future = futureStart + j;
            std::uint64_t contSeed = m.seed
                ^ ((std::uint64_t)(m.decIdx + 1) * 0x9e3779b97f4a7c15ULL)
                ^ ((std::uint64_t)(future + 1) * 0xbf58476d1ce4e5b9ULL);
            if (!contSeed) contSeed = 1;
            std::uint64_t hiddenSeed = contSeed ^ 0x94d049bb133111ebULL;
            if (!hiddenSeed) hiddenSeed = 1;
            GameContext siblingBase = detachedCounterfactualCopy(d.pre);
            if (marginalTradeoff)
                resampleRemainingActEncounters(siblingBase, hiddenSeed);
            const char firstRole = marginalTradeoff ? 'S' : 'C';
            const char secondRole = marginalTradeoff ? 'V' : 'F';
            for (const auto roleIdx : {std::pair<char,int>{firstRole, d.currentIdx},
                                      std::pair<char,int>{secondRole, d.factorIdx}}) {
                GameContext branch = detachedCounterfactualCopy(siblingBase);
                d.actions[roleIdx.second].execute(branch);
                const OocCounterfactualResult r = boundedK3
                    ? evaluateStrategicBranch(std::move(branch), contSeed, d.prePath)
                    : finishOocCounterfactual(
                        std::move(branch), referenceSims, contSeed, d.prePath,
                        -1, false, nullptr, 0, nullptr, false);
                out << m.seed << ',' << m.decIdx << ',' << m.act << ',' << m.floor
                    << ',' << m.screen << ',' << roleIdx.first << ','
                    << d.actions[roleIdx.second].bits << ',' << future << ','
                    << contSeed << ',';
                if (marginalTradeoff) out << hiddenSeed << ',';
                if (boundedK3) {
                    out << r.won << ',' << r.hp << ',' << r.floor << ','
                        << r.bootstrapped << ',' << (r.survivedH ? 1 : 0) << ','
                        << r.won << ',' << (r.survivedH ? r.won : 0.0) << ','
                        << (10.0 * r.won + r.hp) << ',' << (r.valid ? 1 : 0) << '\n';
                } else {
                    out << r.won << ',' << r.floor << ',' << r.hp
                        << ',' << (10.0 * r.won + r.hp) << ',' << (r.valid ? 1 : 0) << '\n';
                }
            }
        }
    }
}


static void strategicGen(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  -> " << outFile << "\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    writeTrainingProvenance(outFile, "strategicgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}

// ---------------------------------------------------------------------------
// STRATEGICGEN2 (Tier-B): the strategicgen row schema plus one-ply
// counterfactual labels per action.  At each sampled decision, every legal
// action is applied to a detached pre-decision copy and the branch is continued
// with the deployed-default OOC policy through STRATEGIC_BRANCH_FIGHTS battles
// (cheap sims + STS_VNET combat value net leaf), then the expected floor /
// P(win) are bootstrapped from the native trees.  Common random numbers across
// the actions of one decision (same branch seed); STRATEGIC_BRANCH_FUTURES
// averages over additional branch seeds per action.
// Row schema: strategicHeader() columns, then
//   labelWon,labelHp,labelFloor,labelBootstrap
// (unsampled decisions leave these empty).
static std::string strategicHeader2() {
    std::string h = strategicHeader();
    if (!h.empty() && h.back() == '\n') h.pop_back();
    return h + ",labelWon,labelHp,labelFloor,labelBootstrap\n";
}

static std::string runStrategicGenSeed2(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);

    std::vector<std::string> rows;
    std::vector<std::string> rowLabel;  // per-row Tier-B label suffix ("" when unsampled)
    // Tier-B label sets for sampled decisions: [rowStart,rowEnd) indexes into
    // `rows` (pushed without the label suffix), `labels` holds one label string
    // per action.  In knob mode this is the reservoir: later sampled decisions
    // replace earlier slots so the N kept decisions are uniform over the run.
    std::vector<std::pair<int, int>> labelRanges;
    std::vector<std::vector<std::string>> labelSets;
    int eligible = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);
        const PathHistory prePath = path;
        const int decIdx = (int)rows.size();

        // Sample this decision for Tier-B branching?  Sample-all labels every
        // decision; otherwise uniform reservoir of STRATEGIC_SAMPLES_PER_RUN
        // decisions (replacing an earlier slot means its branch work is lost).
        int labelSlot = -1;
        bool isNewSlot = false;
        if (g_strategicSampleAll) {
            if (!actions.empty()) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            }
        } else if (!actions.empty()) {
            ++eligible;
            if (eligible <= g_strategicSamplesPerRun) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            } else if (std::uniform_int_distribution<int>(1, eligible)(reservoir)
                       <= g_strategicSamplesPerRun) {
                labelSlot = std::uniform_int_distribution<int>(0, g_strategicSamplesPerRun - 1)(reservoir);
            }
        }
        if (labelSlot >= 0) {
            auto &labels = labelSets[labelSlot];
            labels.resize(actions.size());
            for (int a = 0; a < (int)actions.size(); ++a) {
                double won = 0, hp = 0, floor = 0, boot = 0;
                bool branchInvalid = false;
                for (int f = 0; f < g_strategicBranchFutures; ++f) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[a].execute(branch);
                    const std::uint64_t branchSeed =
                        seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                             ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(decIdx + 31));
                    const OocCounterfactualResult r = finishOocCounterfactual(
                        std::move(branch), sims, branchSeed, prePath,
                        g_strategicBranchFights, /*bootstrap=*/true,
                        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
                    if (r.bootstrapped < 0) { branchInvalid = true; break; }
                    won += r.won; hp += r.hp; floor += r.floor; boot += r.bootstrapped;
                }
                if (branchInvalid) {
                    ++g_trainingInvalidBranches;
                    labels.clear();
                    break;
                }
                const int F = std::max(1, g_strategicBranchFutures);
                char buf[128];
                std::snprintf(buf, sizeof(buf), "%.6f,%.6f,%.6f,%.6f",
                              won / F, hp / F, floor / F, boot / F);
                labels[a] = buf;
            }
            if (isNewSlot)
                labelRanges.emplace_back((int)rows.size(), (int)rows.size() + (int)actions.size());
            else
                labelRanges[labelSlot] = {(int)rows.size(), (int)rows.size() + (int)actions.size()};
        }

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else Searcher2.
        if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        for (int a = 0; a < (int)actions.size(); ++a) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            actions[a].execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, actions[a], actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << actions[a].bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
    }
    t_curPath = nullptr;

    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    // Append the surviving Tier-B labels to their decision's rows.  The labels
    // belong AFTER the terminal won/endFloor/endHp columns, so store them in
    // rowLabel and emit them after the terminal fields below.
    for (int s = 0; s < (int)labelRanges.size(); ++s) {
        const auto &[lo, hi] = labelRanges[s];
        const auto &labels = labelSets[s];
        for (int i = lo; i < hi; ++i)
            if (i - lo < (int)labels.size()) rowLabel[i] = labels[i - lo];
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (int i = 0; i < (int)rows.size(); ++i)
        out << rows[i] << ',' << won << ',' << gc.floorNum << ',' << gc.curHp
            << (rowLabel[i].empty() ? "" : "," + rowLabel[i]) << '\n';
    return out.str();
}

static void strategicGen2(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen2  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  sampleAll " << g_strategicSampleAll << "  samplesPerRun "
              << g_strategicSamplesPerRun << "  branchFights " << g_strategicBranchFights
              << "  branchSims";
    for (const int s : g_strategicBranchSims) std::cout << ':' << s;
    std::cout << "  futures " << g_strategicBranchFutures << "  -> " << outFile << "\n";
    if (!search::g_useVNet)
        std::cout << "[strategicgen2 WARNING: STS_VNET not loaded; branch battles have no combat value net leaf]\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader2();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed2((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingHealthFailures.load(), rows, outFile.c_str());
    writeTrainingProvenance(outFile, "strategicgen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}

// ---------------------------------------------------------------------------
// COMBINED value+policy datagen: one full-run play emits BOTH the V_combat value
// rows (g_onCombatDecision snapshot, labeled with fight endHp) AND the policy-target
// rows (g_onSearchComplete root visit-π). Halves self-play combat datagen cost vs
// running combatgen + policygen separately, and the two datasets are perfectly
// aligned (same play). Returns {valueRows, policyRows}.
static std::pair<std::string,std::string>
runFightGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path;
    t_curPath = &path;

    std::ostringstream val, pol;
    int fightIdx = 0, decIdx = 0;
    std::vector<std::string> fightRows;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        fightRows.push_back(combatFeatureRow(bc));
    };
    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        // Advance for every combat decision, including forced/single-edge roots.
        // This keeps decIdx exactly aligned with the value snapshot emitted by
        // g_onCombatDecision, while still omitting useless one-action policy rows.
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) { pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v; }
            pol << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            fightRows.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                search::g_onSearchComplete = nullptr;
                t_curPath = nullptr;
                return {};
            }
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            for (const auto &fr : fightRows)
                val << seed << ',' << fightIdx << ',' << fr << ',' << won << ',' << endHp << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                serverCardRewardPolicy(gc);                    // deployed V_floor exploit policy
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            shopVPolicy(gc);
        } else if (inRemoveSelect) {
            removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && restWinPolicy(gc)) {
            // deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str() };
}

// ---------------------------------------------------------------------------
// SEARCHDIAG: rollout-usage diagnostics for Searcher2 (default search arm).
// Runs full runs via runFullRunOOC with a per-decision hook
// (search::g_onSearchComplete, fires off the hot path) that emits:
//   rowtype A (every decision):  agent-search counters (per-decision window)
//                                + cumulative frontier stats of the stored tree
//   rowtype B (every probeEvery-th decision): fresh probe searcher per stage at
//             ascending budgets, snapshotting the same metrics per stage --
//             independent trees, so per-stage metrics are not correlated by
//             tree reuse. Records root-decision stability vs the previous stage
//             and vs the agent's implied best action.
// Rowtypes A and B share ONE header (same column semantics). Per-fight
// summaries (outcome, totals) go to a SEPARATE file (`<out>.fights.csv`) so no
// rowtype reinterprets columns. Honors STS_FAIR (probes determinize per
// simulation) and STS_ROLLOUT_DEPTH (records depth-capped rollouts). Searcher3
// is not instrumented; the mode refuses to run under STS_SEARCHER3. See
// docs/knowledge-base/architecture/combat-search.md ("rollout-usage
// diagnostics").
// ---------------------------------------------------------------------------

static int  g_sdiagProbeEvery = 1;
static std::ofstream g_sdiagFightFile;   // per-fight summary CSV (separate schema)

// Budget stages for the root-stability sweep (rowtype B), per the searchdiag
// design: 100..30k simulations per stage on fresh probe trees.
static const std::vector<std::int64_t> kSdiagStages = {100, 250, 500, 1000, 3000, 10000, 30000};

// Whole-searcher metrics: counters + frontier walk + root visit distribution.
static SdiagMetrics sdiagMetricsOf(const search::BattleScumSearcher2 &s) {
    assert(s.diag.consistent());   // simulations == terminalInsideTree + rolloutCalls + leafDirectEval
    SdiagMetrics m;
    const auto &d = s.diag;
    m.sims = d.simulations;
    m.terminalInTree = d.terminalInsideTree;
    m.rolloutCalls = d.rolloutCalls;
    m.rolloutLeafCalls = d.rolloutLeafCalls;
    m.fairIllegalStoredEdge = d.fairIllegalStoredEdge;
    m.leafDirectEval = d.leafDirectEval;
    m.rolloutTerminated = d.rolloutTerminated;
    m.rolloutDepthCapped = d.rolloutDepthCapped;
    m.rolloutSkippedVNet = d.rolloutSkippedVNet;
    m.rolloutNoLegal = d.rolloutNoLegalAction;
    m.rolloutActions = d.rolloutActions;
    m.treeActions = d.treeActions;
    m.maxTreeDepth = d.maxTreeDepth;
    m.simSeconds = d.simSeconds;
    s.collectFrontierStats(m.frontier);

    std::int64_t bestN = -1, secondN = -1, total = 0;
    std::uint32_t bestBits = 0xFFFFFFFFu, secondBits = 0xFFFFFFFFu;
    for (const auto &e : s.root.edges) {
        const std::int64_t n = e.node.simulationCount;
        total += n;
        if (n > bestN) { secondN = bestN; secondBits = bestBits; bestN = n; bestBits = e.action.bits; }
        else if (n > secondN) { secondN = n; secondBits = e.action.bits; }
    }
    if (bestN > 0) {
        m.bestAction = bestBits;
        m.visitShare = double(bestN) / total;
        const auto meanOf = [&](std::uint32_t bits, std::int64_t visits) {
            for (const auto &e : s.root.edges)
                if (e.action.bits == bits) return e.node.evaluationSum / double(visits);
            return 0.0;
        };
        m.bestValue = meanOf(bestBits, bestN);
        if (secondN > 0) {
            m.runnerUpValue = meanOf(secondBits, secondN);
            m.valueGap = m.bestValue - m.runnerUpValue;
        }
    }
    return m;
}

// Per-decision window: current cumulative minus the previous snapshot.
static SdiagMetrics sdiagWindow(const SdiagMetrics &cur, const SdiagMetrics &prev) {
    SdiagMetrics w = cur;
    w.sims = cur.sims - prev.sims;
    w.terminalInTree = cur.terminalInTree - prev.terminalInTree;
    w.rolloutCalls = cur.rolloutCalls - prev.rolloutCalls;
    w.rolloutLeafCalls = cur.rolloutLeafCalls - prev.rolloutLeafCalls;
    w.fairIllegalStoredEdge = cur.fairIllegalStoredEdge - prev.fairIllegalStoredEdge;
    w.leafDirectEval = cur.leafDirectEval - prev.leafDirectEval;
    w.rolloutTerminated = cur.rolloutTerminated - prev.rolloutTerminated;
    w.rolloutDepthCapped = cur.rolloutDepthCapped - prev.rolloutDepthCapped;
    w.rolloutSkippedVNet = cur.rolloutSkippedVNet - prev.rolloutSkippedVNet;
    w.rolloutNoLegal = cur.rolloutNoLegal - prev.rolloutNoLegal;
    w.rolloutActions = cur.rolloutActions - prev.rolloutActions;
    w.treeActions = cur.treeActions - prev.treeActions;
    w.simSeconds = cur.simSeconds - prev.simSeconds;
    w.maxTreeDepth = cur.maxTreeDepth;   // cumulative: deepest path in the tree to date
    return w;
}
static void sdiagWriteRow(const char *rowtype, const BattleContext &bc, const SdiagMetrics &m, int stableVsPrev, int stableVsAgent) {
    std::lock_guard<std::mutex> lk(g_sdiagMutex);
    if (!g_sdiagFile) return;
    const SdiagRunCtx &c = g_sdiagCtx;
    const double rFrac = m.sims ? double(m.rolloutCalls) / m.sims : 0;
    const double avgRoll = m.rolloutCalls ? double(m.rolloutActions) / m.rolloutCalls : 0;
    const double avgTD = m.sims ? double(m.treeActions) / m.sims : 0;
    const double tTot = m.treeActions + m.rolloutActions;
    const double tCov = tTot ? double(m.treeActions) / tTot : 0;
    const auto &fr = m.frontier;
    const double tff = (fr.terminalLeaves() + fr.unexpandedLeaves)
                           ? double(fr.terminalLeaves()) / double(fr.terminalLeaves() + fr.unexpandedLeaves) : 0;
    const double vtc = fr.frontierLeafVisits ? double(fr.terminalLeafVisits) / double(fr.frontierLeafVisits) : 0;
    const int deck = (int)(bc.cards.drawPile.size() + bc.cards.cardsInHand
                           + bc.cards.discardPile.size() + bc.cards.exhaustPile.size());
    const int nLegal = (int)legalActions(bc).size();
    g_sdiagFile << rowtype << ',' << (search::g_fairPlay ? 1 : 0) << ',' << c.seed << ',' << c.fightIdx << ',' << c.decisionIdx << ','
                << c.floor << ',' << c.act << ',' << c.room << ',' << c.encounter << ',' << bc.turn << ','
                << deck << ',' << bc.cards.cardsInHand << ',' << nLegal << ','
                << m.budget << ',' << m.sims << ',' << m.terminalInTree << ',' << m.rolloutCalls
                << ',' << m.rolloutLeafCalls << ',' << m.fairIllegalStoredEdge
                << ',' << m.leafDirectEval << ',' << m.rolloutTerminated << ',' << m.rolloutDepthCapped
                << ',' << m.rolloutSkippedVNet << ',' << m.rolloutNoLegal << ','
                << m.rolloutActions << ',' << m.treeActions << ','
                << rFrac << ',' << avgRoll << ',' << avgTD << ',' << m.maxTreeDepth << ',' << tCov << ','
                << m.simSeconds << ',' << (m.simSeconds > 0 ? m.sims / m.simSeconds : 0.0) << ','
                << fr.nodesWalked << ',' << fr.victoryLeaves << ',' << fr.defeatLeaves
                << ',' << fr.unexpandedLeaves << ',' << tff << ',' << vtc << ','
                << m.bestAction << ',' << m.visitShare << ',' << m.bestValue << ','
                << m.runnerUpValue << ',' << m.valueGap << ',' << stableVsPrev << ',' << stableVsAgent << '\n';
    g_sdiagFile.flush();
}

// Rowtype B: fresh probe searcher per stage -- independent trees per budget.
static void sdiagProbe(const BattleContext &bc, std::uint32_t agentBest) {
    int stageIdx = 0;
    std::uint32_t prevBest = 0xFFFFFFFFu;
    for (const std::int64_t stage : kSdiagStages) {
        search::BattleScumSearcher2 probe(bc);
        probe.searchToTotal(stage);
        SdiagMetrics m = sdiagMetricsOf(probe);
        m.budget = stage;
        const int vsPrev = stageIdx == 0 ? -1 : (m.bestAction == prevBest ? 1 : 0);
        const int vsAgent = agentBest == 0xFFFFFFFFu || m.bestAction == 0xFFFFFFFFu
                                ? -1 : (m.bestAction == agentBest ? 1 : 0);
        sdiagWriteRow("B", bc, m, vsPrev, vsAgent);
        prevBest = m.bestAction;
        ++stageIdx;
    }
}

// Hook fired by ScumSearchAgent2 once per agent decision (off the hot path).
static void sdiagOnSearchComplete(const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
    ++g_sdiagCtx.decisionIdx;
    SdiagMetrics cur = sdiagMetricsOf(searcher);
    // Window semantics: non-fair mode reuses ONE searcher per fight, so its
    // counters are cumulative and the per-decision window is the delta. Fair
    // mode rebuilds a fresh searcher every decision (determinizations are
    // world-specific), so the whole search is the window. (Searcher identity
    // cannot be used to tell the two apart: both modes reuse the same stack
    // address.)
    SdiagMetrics win;
    if (search::g_fairPlay) {
        win = cur;
    } else {
        win = sdiagWindow(cur, g_sdiagCtx.cum);
        g_sdiagCtx.cum = cur;
    }
    g_sdiagCtx.cum = cur;
    g_sdiagCtx.fTot.sims += win.sims;
    g_sdiagCtx.fTot.terminalInTree += win.terminalInTree;
    g_sdiagCtx.fTot.rolloutCalls += win.rolloutCalls;
    g_sdiagCtx.fTot.leafDirectEval += win.leafDirectEval;
    g_sdiagCtx.fTot.rolloutTerminated += win.rolloutTerminated;
    g_sdiagCtx.fTot.rolloutDepthCapped += win.rolloutDepthCapped;
    g_sdiagCtx.fTot.rolloutSkippedVNet += win.rolloutSkippedVNet;
    g_sdiagCtx.fTot.rolloutNoLegal += win.rolloutNoLegal;
    g_sdiagCtx.fTot.rolloutActions += win.rolloutActions;
    g_sdiagCtx.fTot.treeActions += win.treeActions;
    win.budget = win.sims;
    sdiagWriteRow("A", bc, win, -1, -1);
    if (g_sdiagProbeEvery > 0 && (g_sdiagCtx.decisionIdx % g_sdiagProbeEvery) == 0)
        sdiagProbe(bc, cur.bestAction);
}

// Per-fight summary (separate CSV, own header -- never shares the A/B schema).
// Searcher3 variant of sdiagMetricsOf: same SdiagMetrics schema, read from
// BattleScumSearcher3::diag + root visit distribution. S3 keeps no frontier
// classification (no terminal markers on nodes), so frontier fields stay 0.
static SdiagMetrics sdiagMetricsOf3(const search::BattleScumSearcher3 &s) {
    SdiagMetrics m;
    const auto &d = s.diag;
    m.sims = d.simulations;
    m.terminalInTree = d.terminalInsideTree;
    m.rolloutCalls = d.rolloutCalls;
    m.rolloutLeafCalls = d.rolloutLeafCalls;
    m.fairIllegalStoredEdge = d.fairIllegalStoredEdge;
    m.leafDirectEval = d.leafDirectEval;
    m.rolloutTerminated = d.rolloutTerminated;
    m.rolloutDepthCapped = d.rolloutDepthCapped;
    m.rolloutSkippedVNet = d.rolloutSkippedVNet;
    m.rolloutNoLegal = d.rolloutNoLegalAction;
    m.rolloutActions = d.rolloutActions;
    m.treeActions = d.treeActions;
    m.maxTreeDepth = d.maxTreeDepth;
    m.simSeconds = d.simSeconds;

    std::int64_t bestN = -1, secondN = -1, total = 0;
    std::uint32_t bestBits = 0xFFFFFFFFu, secondBits = 0xFFFFFFFFu;
    for (const auto &e : s.root.edges) {
        const std::int64_t n = e.child.simulationCount;
        total += n;
        if (n > bestN) { secondN = bestN; secondBits = bestBits; bestN = n; bestBits = e.action.bits; }
        else if (n > secondN) { secondN = n; secondBits = e.action.bits; }
    }
    if (bestN > 0) {
        m.bestAction = bestBits;
        m.visitShare = double(bestN) / total;
        const auto meanOf = [&](std::uint32_t bits, std::int64_t visits) {
            for (const auto &e : s.root.edges)
                if (e.action.bits == bits) return e.child.evaluationSum / double(visits);
            return 0.0;
        };
        m.bestValue = meanOf(bestBits, bestN);
        if (secondN > 0) {
            m.runnerUpValue = meanOf(secondBits, secondN);
            m.valueGap = m.bestValue - m.runnerUpValue;
        }
    }
    return m;
}

// Rowtype A hook for Searcher3 (searchdiag now instruments both searchers).
// Same windowing semantics as the S2 hook: fair mode rebuilds a fresh searcher
// per decision (whole search = window); non-fair reuses one searcher per fight
// (cumulative counters -> per-decision window = delta).
static void sdiagOnSearchComplete3(const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
    ++g_sdiagCtx.decisionIdx;
    SdiagMetrics cur = sdiagMetricsOf3(s3);
    SdiagMetrics win;
    if (search::g_fairPlay) {
        win = cur;
    } else {
        win = sdiagWindow(cur, g_sdiagCtx.cum);
        g_sdiagCtx.cum = cur;
    }
    g_sdiagCtx.cum = cur;
    g_sdiagCtx.fTot.sims += win.sims;
    g_sdiagCtx.fTot.terminalInTree += win.terminalInTree;
    g_sdiagCtx.fTot.rolloutCalls += win.rolloutCalls;
    g_sdiagCtx.fTot.leafDirectEval += win.leafDirectEval;
    g_sdiagCtx.fTot.rolloutTerminated += win.rolloutTerminated;
    g_sdiagCtx.fTot.rolloutDepthCapped += win.rolloutDepthCapped;
    g_sdiagCtx.fTot.rolloutSkippedVNet += win.rolloutSkippedVNet;
    g_sdiagCtx.fTot.rolloutNoLegal += win.rolloutNoLegal;
    g_sdiagCtx.fTot.rolloutActions += win.rolloutActions;
    g_sdiagCtx.fTot.treeActions += win.treeActions;
    win.budget = win.sims;
    sdiagWriteRow("A", bc, win, -1, -1);
    // No rowtype-B probes under Searcher3: the probe stages are Searcher2
    // machinery (sdiagProbe) and S3's fresh-searcher-per-decision fair path
    // would not be comparable to S2 probe trees.
}

static void sdiagFightRow(const BattleContext &bc) {
    std::lock_guard<std::mutex> lk(g_sdiagMutex);
    if (!g_sdiagFightFile) return;
    const SdiagRunCtx &c = g_sdiagCtx;
    const auto &t = c.fTot;
    const double rFrac = t.sims ? double(t.rolloutCalls) / t.sims : 0;
    const double avgRoll = t.rolloutCalls ? double(t.rolloutActions) / t.rolloutCalls : 0;
    const double avgTD = t.sims ? double(t.treeActions) / t.sims : 0;
    const double tTot = t.treeActions + t.rolloutActions;
    const double tCov = tTot ? double(t.treeActions) / tTot : 0;
    g_sdiagFightFile << c.seed << ',' << c.fightIdx << ',' << c.floor << ',' << c.act << ','
                << c.room << ',' << c.encounter << ','
                << (bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0) << ',' << (bc.turn + 1) << ','
                << bc.player.curHp << ',' << t.sims << ',' << t.terminalInTree << ','
                << t.rolloutCalls << ',' << t.leafDirectEval << ',' << t.rolloutActions << ','
                << t.treeActions << ',' << rFrac << ',' << avgRoll << ',' << avgTD << ',' << tCov << '\n';
    g_sdiagFightFile.flush();
}

static void searchDiag(int nSeeds, int sims, int asc, const std::string &out, int probeEvery,
                       std::uint64_t seedOffset = 0) {
    if (search::g_useSearcher3 && probeEvery > 0) {
        std::cerr << "searchdiag: Searcher3 supports rowtype A only (no S2 probe stages); forcing probeEvery=0\n";
        probeEvery = 0;
    }
    g_sdiagProbeEvery = probeEvery;
    g_sdiagActive = true;
    g_sdiagFile.open(out, std::ios::trunc);
    if (!g_sdiagFile) {
        std::cerr << "searchdiag: cannot open " << out << "\n";
        g_sdiagActive = false;
        return;
    }
    const std::string fightOut = out + ".fights.csv";
    g_sdiagFightFile.open(fightOut, std::ios::trunc);
    if (!g_sdiagFightFile) {
        std::cerr << "searchdiag: cannot open " << fightOut << "\n";
        g_sdiagFile.close();
        g_sdiagActive = false;
        return;
    }
    g_sdiagFile << "rowtype,fair,seed,fightIdx,decIdx,floor,act,room,encounter,turn,deckSize,handSize,"
                   "nLegalActions,budget,sims,terminalInTree,rolloutCalls,rolloutLeafCalls,"
                   "fairIllegalStoredEdge,leafDirectEval,"
                   "rolloutTerminated,rolloutDepthCapped,rolloutSkippedVNet,rolloutNoLegal,"
                   "rolloutActions,treeActions,rolloutFraction,avgRolloutLen,avgTreeDepth,maxTreeDepth,"
                   "treeCoverage,simSeconds,simsPerSec,"
                   "nodesWalked,victoryLeaves,defeatLeaves,unexpandedLeaves,terminalFrontierFraction,"
                   "visitedTerminalCoverage,bestAction,visitShare,bestValue,runnerUpValue,valueGap,"
                   "stableVsPrev,stableVsAgent\n";
    g_sdiagFile.flush();
    g_sdiagFightFile << "seed,fightIdx,floor,act,room,encounter,won,turns,hpEnd,"
                        "sims,terminalInTree,rolloutCalls,leafDirectEval,rolloutActions,treeActions,"
                        "rolloutFraction,avgRolloutLen,avgTreeDepth,treeCoverage\n";
    g_sdiagFightFile.flush();
    std::cout << "SEARCHDIAG: seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims/decision " << sims
              << "  asc " << asc << "  probeEvery " << probeEvery
              << "  fair=" << (search::g_fairPlay ? 1 : 0)
              << "  rolloutDepth=" << search::g_maxRolloutDepth
              << "  threads " << numThreads() << "  out " << out
              << "  fights " << fightOut << "\n";
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    int wins = 0;
    auto wall0 = std::chrono::steady_clock::now();
    #pragma omp parallel for reduction(+:wins) schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = seedOffset + (std::uint64_t)s;
        if (search::g_useSearcher3)
            search::g_onSearchComplete3 = sdiagOnSearchComplete3;   // thread_local: set per worker
        else
            search::g_onSearchComplete = sdiagOnSearchComplete;   // thread_local: set per worker
        RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
        search::g_onSearchComplete = nullptr;
        search::g_onSearchComplete3 = nullptr;
        wins += r.won ? 1 : 0;
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    g_sdiagFile.close();
    g_sdiagFightFile.close();
    g_sdiagActive = false;
    std::printf("SEARCHDIAG DONE  win%%=%5.1f  wall=%.1fs\n", 100.0 * wins / nSeeds, wall);
}

// ---------------------------------------------------------------------------
// POLICY-TARGET datagen (AlphaZero-lite phase 1): at every in-combat decision,
// after the searcher has run its full budget, log each root edge as a row
// (state features ++ that action's features) with the edge's VISIT COUNT and the
// decision's TOTAL visits. Training normalizes visit/total -> the MCTS policy
// target π; the learned comparator net(state,action) then steers PUCT selection.
// Reuses g_onSearchComplete (fires once per agent decision, off the hot path).
static std::string policyHeaderStr() {
    const auto &names = search::combatPolicyFeatureNames();
    std::string h = "seed,fightIdx,decIdx";
    for (const auto &n : names) { h += ','; h += n; }
    h += ",visit,total";
    return h;
}

static std::string runPolicyGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out, fightOut;
    int fightIdx = 0, decIdx = 0;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        const int n = (int)edges.size();
        if (n < 2) return;                       // forced single move -> nothing to learn
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            fightOut << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                fightOut << ',';
                const float v = feat[i];
                if (v == (float)(long)v) fightOut << (long)v; else fightOut << v;
            }
            fightOut << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            decIdx = 0;
            fightOut.str(""); fightOut.clear();
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onSearchComplete = nullptr;
                return {};
            }
            ++fightIdx;
            bc.exitBattle(gc);
            out << fightOut.str();
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onSearchComplete = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};
    return out.str();
}

static std::string runDataGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::vector<std::string> rows;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) return {};
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(featureRow(gc) + ',' + deckCountsCsv(gc));  // state + deck ids
                if (ur(ex) < epsilon) {                          // explore: random pick among cards + skip
                    while (r.cardRewardCount > 0) {
                        const int rIdx = r.cardRewardCount - 1;
                        const int nc = r.cardRewards[rIdx].size();
                        const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                        search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);                     // exploit
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum;
    std::ostringstream o;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << '\n';  // seed = run id
    return o.str();
}

// ---------------------------------------------------------------------------
// CAUSAL LABELS: at each card reward, CRN-fork "take card i" vs "skip", play the
// next N fights with common random numbers, and label the card's ADVANTAGE =
// score(take) - score(skip). This measures the true causal effect of the card
// (not just "what losing decks look like"). One row per candidate card.
// ---------------------------------------------------------------------------
// Raw representation (no hand-crafted synergy features): deck as per-card-id
// counts d0..d(kNumCardIds-1) + the candidate card's id; the model (GBM) learns
// which (candidate, deck-card) combinations matter. Plus a few cheap scalars.
// (kNumCardIds / deckCountsCsv defined above featureRow for reuse by datagen.)

static std::string causalContextRow(const GameContext &gc, const Card &c) {
    long obtainSum = 0;
    for (const auto &d : gc.deck.cards) obtainSum += search::Expert::getObtainWeight(d.getId(), d.isUpgraded());
    const int deckSize = gc.deck.size();
    std::ostringstream o;
    o << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ','
      << deckSize << ',' << (int)gc.relics.relics.size() << ',' << obtainSum << ','
      << (deckSize ? (double)obtainSum / deckSize : 0.0) << ','
      << search::Expert::getObtainWeight(c.getId(), c.isUpgraded()) << ',' << c.getBaseDamage() << ','
      << (c.isUpgraded() ? 1 : 0) << ',' << (int)c.getId();
    return o.str();
}

static std::string causalHeader() {
    std::ostringstream h;
    h << "act,floor,curHp,maxHp,gold,deckSize,nRelics,obtainSum,obtainAvg,"
         "c_obtainWeight,c_baseDamage,c_isUpgraded,candidateId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    h << ",advantage";
    return h.str();
}

static std::string runCausalGenSeed(std::uint64_t seed, int sims, int asc, int N, int innerSims, int K, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 2862933555777941757ULL + 7);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    long decision = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) return {};
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                const int rIdx = r.cardRewardCount - 1;
                const int nc = r.cardRewards[rIdx].size();
                const std::uint64_t base = seed * 1000003ULL + (std::uint64_t)decision * 131ULL;
                const std::string dc = deckCountsCsv(gc);        // deck id-counts (same for all candidates)

                // K paired CRN worlds: skip baseline per world, then average card - skip.
                std::vector<double> sSkip(K);
                for (int k = 0; k < K; ++k)
                    sSkip[k] = rolloutChoice(gc, rIdx, 5, N, innerSims, base + k, /*useLabelScore=*/true);
                for (int i = 0; i < nc; ++i) {
                    double adv = 0.0;
                    for (int k = 0; k < K; ++k)
                        adv += rolloutChoice(gc, rIdx, i, N, innerSims, base + k, /*useLabelScore=*/true) - sSkip[k];
                    adv /= K;
                    out << causalContextRow(gc, r.cardRewards[rIdx][i]) << ',' << dc << ',' << adv << '\n';
                }
                ++decision;
                if (ur(ex) < epsilon) {                          // explore to diversify visited states
                    while (r.cardRewardCount > 0) {
                        const int ri = r.cardRewardCount - 1;
                        const int n2 = r.cardRewards[ri].size();
                        const int pick = std::uniform_int_distribution<int>(0, n2)(ex);
                        search::GameAction(RT::CARD, ri, pick < n2 ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    return out.str();
}

static void causalGen(int nSeeds, int sims, int asc, int N, int innerSims, int K, double eps, const std::string &outfile) {
    trainingCampaignStart();
    std::cout << "causalgen  seeds 0.." << nSeeds - 1 << "  outerSims " << sims << "  N " << N
              << "  innerSims " << innerSims << "  K " << K << "  eps " << eps
              << (search::g_fairPlay ? "  [fair-play]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::vector<std::string> per(nSeeds);
    auto t0 = std::chrono::steady_clock::now();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) per[s] = runCausalGenSeed((std::uint64_t)s, sims, asc, N, innerSims, K, eps);

    std::ofstream f(outfile);
    f << causalHeader() << '\n';
    long long rows = 0;
    for (int s = 0; s < nSeeds; ++s) { f << per[s]; rows += std::count(per[s].begin(), per[s].end(), '\n'); }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld causal rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    writeTrainingProvenance(outfile, "causalgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, 0, sims, asc, eps);
}

static void dataGen(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                    long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;   // append onto an existing file; seeds are disjoint
    std::cout << "datagen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << "  eps " << epsilon << (search::g_fairPlay ? "  [fair-play]" : "")
              << (append ? "  [append]" : "")
              << "  threads " << numThreads() << "  -> " << outfile << "\n";
    // Incremental / interrupt-safe: write the header (fresh file only), then flush
    // each run's rows as it finishes (inside a critical section). Killing the
    // process at any time leaves a valid CSV of all completed runs. seedOffset lets
    // a follow-up run append DISJOINT seeds (no duplicate rows) onto prior output.
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (!append) {
        f << "seed," << kFeatureHeader;
        for (int i = 0; i < kNumCardIds; ++i) f << ",d" << i;
        f << ",won,finalFloor\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0;
    int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runDataGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows;
            f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "datagen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Combat-value dataset: per-fight combat states labeled with the fight outcome.
// Interrupt-safe (per-run flush) and append-capable, same as dataGen.
static void combatGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "combatgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, false);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
                std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), rowCount, outfile.c_str());
    writeTrainingProvenance(outfile, "combatgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Policy-target dataset: per-decision root-edge visit distributions. Same
// interrupt-safe (per-run flush) + append pattern as combatGen.
static void policyGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "policygen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << policyHeaderStr() << "\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runPolicyGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld policy rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "policygen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Combined value+policy datagen: ONE play pass writes both CSVs (see runFightGenSeed).
static void fightGen(int nSeeds, int sims, int asc, double epsilon,
                     const std::string &valFile, const std::string &polFile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fightgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto pr = runFightGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << pr.first;  pf << pr.second;  vf.flush(); pf.flush();
            vRows += std::count(pr.first.begin(),  pr.first.end(),  '\n');
            pRows += std::count(pr.second.begin(), pr.second.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy rows from %d runs in %.1fs\n", vRows, pRows, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), vRows + pRows, valFile.c_str());
    writeTrainingProvenance(valFile, "fightgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), vRows + pRows, seedOffset, sims, asc);
}

// ---------------------------------------------------------------------------
// DISTRIBUTIONAL COMBAT VALUE datagen: like combatgen but adds rich labels for
// the distributional model — endTurn (for turns-remaining prediction) and
// per-potion-ID consumption flags (for potion-use-probability prediction).
// The 1766 state features + won/endHp are identical to combatgen output.
// ---------------------------------------------------------------------------
static void distCombatGen(int nSeeds, int sims, int asc, double epsilon,
                          const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "distgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp"
          << distLabelHeaderStr() << "\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, true);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld dist combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "distgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// ---------------------------------------------------------------------------
// DECK DUMP: play one run with our best policy (eval draft + heuristic path)
// and print the final deck, relics and outcome.
// ---------------------------------------------------------------------------
static void dumpRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            evalCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::printf("=== seed %llu  %s  floor %d (act %d)  hp %d/%d  gold %d ===\n",
                (unsigned long long)seed,
                gc.outcome == GameOutcome::PLAYER_VICTORY ? "WIN" : "DEAD",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp, gc.gold);

    std::map<std::string, int> counts;
    for (const auto &c : gc.deck.cards) {
        std::string n = c.getName();
        if (c.isUpgraded()) n += "+";
        ++counts[n];
    }
    std::printf("\nDeck (%d cards):\n", gc.deck.size());
    for (const auto &kv : counts) std::printf("  %2dx %s\n", kv.second, kv.first.c_str());

    std::printf("\nRelics (%d):\n", (int)gc.relics.relics.size());
    for (const auto &ri : gc.relics.relics) std::printf("  - %s\n", getRelicName(ri.id));
}



// Export one deterministic full-map graph per (seed, ascension, act) present
// in a card-counterfactual CSV.  The source CSV repeats the state once per
// available action; de-duplicating here keeps the companion graph table small.
// Each node stores its room id and a seven-bit mask of outgoing destination x
// coordinates.  Row/column are implicit in the fixed 15x7 layout.
static void exportCardCfMaps(const std::string &inputPath, const std::string &outputPath) {
    std::ifstream in(inputPath);
    if (!in) throw std::runtime_error("cannot open card-CF CSV: " + inputPath);
    std::ofstream out(outputPath);
    if (!out) throw std::runtime_error("cannot create map CSV: " + outputPath);

    std::string line;
    if (!std::getline(in, line)) throw std::runtime_error("empty card-CF CSV: " + inputPath);
    std::stringstream header(line);
    std::vector<std::string> columns;
    std::string headerField;
    while (std::getline(header, headerField, ',')) columns.push_back(headerField);
    auto columnIndex = [&](const char *name) {
        auto it = std::find(columns.begin(), columns.end(), name);
        if (it == columns.end()) throw std::runtime_error("map source CSV missing column " + std::string(name));
        return static_cast<int>(it - columns.begin());
    };
    const int seedCol = columnIndex("seed");
    const int ascCol = columnIndex("ascension");
    const int actCol = columnIndex("act");
    const int lastNeededCol = std::max({seedCol, ascCol, actCol});

    out << "seed,ascension,act,burningEliteX,burningEliteY,burningEliteBuff";
    for (int i = 0; i < 15 * 7; ++i) out << ",room" << i;
    for (int i = 0; i < 15 * 7; ++i) out << ",edges" << i;
    out << '\n';

    std::set<std::tuple<std::uint64_t, int, int>> seen;
    std::size_t rows = 0;
    while (std::getline(in, line)) {
        std::stringstream ss(line);
        std::string field;
        std::uint64_t seed = 0;
        int ascension = 0, act = 0;
        for (int col = 0; col <= lastNeededCol; ++col) {
            if (!std::getline(ss, field, ',')) {
                throw std::runtime_error("short row in map source CSV");
            }
            if (col == seedCol) seed = std::stoull(field);
            else if (col == ascCol) ascension = std::stoi(field);
            else if (col == actCol) act = std::stoi(field);
        }
        if (!seen.emplace(seed, ascension, act).second) continue;

        Map map = act == 4 ? Map::act4Map() : Map::fromSeed(seed, ascension, act, true);
        out << seed << ',' << ascension << ',' << act << ','
            << map.burningEliteX << ',' << map.burningEliteY << ',' << map.burningEliteBuff;
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            out << ',' << static_cast<int>(map.getNode(x, y).room);
        }
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &node = map.getNode(x, y);
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << ',' << edgeMask;
        }
        out << '\n';
        ++rows;
    }
    std::cout << "exported " << rows << " unique (seed, ascension, act) maps to "
              << outputPath << '\n';
}

// ---------------------------------------------------------------------------
int main(int argc, char **argv) {
    g_mainBinaryPath = argc > 0 ? argv[0] : "one_combat";
    g_mainArgv.clear();
    for (int i = 1; i < argc; ++i) g_mainArgv.emplace_back(argv[i]);
    std::string mode = argc > 1 ? argv[1] : "bench";

    if (const char *d = std::getenv("VPORT")) g_vPort = std::atoi(d);

    if (const char *d = std::getenv("STS_COLLECT_KEYS")) {
        g_collectKeys = std::atoi(d) != 0;
        std::cout << "[collect keys " << (g_collectKeys ? "ON" : "OFF") << "]\n";
    }

    if (const char *d = std::getenv("STS_ROLLOUT_DEPTH")) {   // cap combat rollout length
        search::g_maxRolloutDepth = std::atoi(d);
        std::cout << "[rollout depth cap = " << search::g_maxRolloutDepth << "]\n";
    }
    if (const char *d = std::getenv("STS_ROLLOUT_CAPS")) {    // context-adaptive rollout caps (Phase 2)        search::g_rolloutCaps = std::atoi(d) != 0;
        if (search::g_rolloutCaps) {
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_BOSS"))      search::g_rolloutCapBoss = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_TURN0"))     search::g_rolloutCapTurn0 = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_ACT23"))     search::g_rolloutCapAct23 = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_LATE_ALIVE")) search::g_rolloutCapLateAlive = std::atoi(v);
            std::cout << "[context rollout caps ON: boss=" << search::g_rolloutCapBoss
                      << " turn0=" << search::g_rolloutCapTurn0
                      << " act23=" << search::g_rolloutCapAct23
                      << " lateAlive<=" << search::g_rolloutCapLateAlive << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_FORCED_MOVE")) {    // forced-action contraction (Phase 5; default ON, 0 disables)
        search::g_forcedMoveSkip = std::atoi(d) != 0;
        std::cout << "[forced-move contraction " << (search::g_forcedMoveSkip ? "ON" : "OFF") << "]\n";
    }
    if (const char *d = std::getenv("STS_LIVE_VALID")) {     // fair-tree structural fix (Phase 4)
        search::g_liveValid = std::atoi(d) != 0;
        if (search::g_liveValid) std::cout << "[live-valid edge re-selection ON]\n";
    }
    if (const char *d = std::getenv("STS_TURN_PENALTY")) {    // -turn*k on capped leaf: loop-breaker
        search::g_leafTurnPenalty = std::atof(d);
        std::cout << "[leaf turn penalty = " << search::g_leafTurnPenalty << "]\n";
    }
    if (const char *d = std::getenv("STS_TT")) {              // transposition table (value sharing)
        search::g_useTT = std::atoi(d) != 0;
        if (search::g_useTT) std::cout << "[transposition table ON]\n";
    }
    if (const char *d = std::getenv("STS_REST_V_THRESH")) {   // rest-site heal-gain threshold
        g_restVThreshold = std::atof(d);
        std::cout << "[rest-V heal threshold = " << g_restVThreshold << "]\n";
    }
    if (const char *d = std::getenv("STS_REST_WIN")) {        // win-rate rest policy (heal vs upgrade by P(win))
        g_restWin = std::atoi(d) != 0;
        if (g_restWin) std::cout << "[win-rate rest policy ON]\n";
    }
    if (const char *d = std::getenv("STS_CARD_WIN")) {       // A/B: card picks by P(win) instead of V_floor
        g_cardWin = std::atoi(d) != 0;
        if (const char *s = std::getenv("STS_CARD_WIN_SKIP")) g_cardWinSkip = std::atof(s);
        if (g_cardWin) std::cout << "[card picks via WIN model, skip<" << g_cardWinSkip << "]\n";
    }
    if (const char *d = std::getenv("STS_CARD_NN")) {        // A/B: card picks via deck-set NN (CN op)
        g_cardNN = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_CARD_NN_W"))    g_cardNNW    = std::atof(w);
        if (const char *s = std::getenv("STS_CARD_NN_SKIP")) g_cardNNSkip = std::atof(s);
        if (g_cardNN) std::cout << "[card picks via deck-set NN: w=" << g_cardNNW
                                << " (1=pure NN, <1 blend w/ v_win), skip<" << g_cardNNSkip
                                << " (needs v_deckset.pt in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_CARD_ACTION")) {    // direct paired card/skip action NN
        g_cardAction = std::atoi(d) != 0;
        if (g_cardAction) std::cout << "[card picks via paired action NN (CA op)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_ACTION_NN")) {
        g_oocActionNN = std::atoi(d) != 0;
        if (g_oocActionNN)
            std::cout << "[OOC decisions via next-combat action NN (OA op), reapplied every decision]\n";
    }
    if (const char *d = std::getenv("STS_OOC_CHECKPOINT_NN")) {
        if (g_oocCheckpointNet.load(d)) {
            g_oocActionNN = true;
            std::cout << "[OOC decisions via native checkpoint-distilled NN]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_NN")) {
        if (g_oocStrategicNet.load(d)) {
            g_effectiveOocStrategicPath = d;
            std::cout << "[OOC one-ply strategic NN ON: card rewards gated at margin "
                      << g_oocStrategicMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TOK_NN")) {
        if (g_oocStrategicTokNet.load(d)) {
            g_effectiveOocStrategicTokPath = d;
            g_oocStrategicTok = 1;
            std::cout << "[OOC one-ply strategic TOK net ON: card rewards gated at margin "
                      << g_oocStrategicMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TOK_CHECK")) {
        g_oocStrategicTokCheck = std::atoi(d) != 0;
        if (g_oocStrategicTokCheck)
            std::cout << "[OOC strategic tok parity check ON (first-decision globs vs richRow)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TRACE")) {
        g_oocStrategicTracePath = d;
        if (!g_oocStrategicTracePath.empty())
            std::cout << "[OOC strategic decision trace: " << g_oocStrategicTracePath << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_Q")) {
        g_oocStrategicQ = std::atoi(d) != 0;
        if (!g_oocStrategicQ)
            std::cout << "[OOC one-ply: Q head disabled, V2 successor-value scoring]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_REST")) {
        g_oocStrategicRest = std::atoi(d) != 0;
        if (g_oocStrategicRest)
            std::cout << "[OOC one-ply: campfire Q gate ON (rest options + upgrade targets)]\n";
    }
    if (const char *d = std::getenv("STS_DATAGEN_GATES")) {  // §127: combatgen/distgen OOC through the one-ply gate chain
        g_datagenGates = std::atoi(d) != 0;
        if (g_datagenGates)
            std::cout << "[datagen OOC gate stack ON: combat labels from the deployed one-ply distribution (§127)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_EVENT")) {
        g_oocStrategicEvent = std::atoi(d) != 0;
        if (g_oocStrategicEvent)
            std::cout << "[OOC one-ply: event Q gate ON (incl. Neow)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_SHOP")) {
        g_oocStrategicShop = std::atoi(d) != 0;
        if (g_oocStrategicShop)
            std::cout << "[OOC one-ply: shop Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TREASURE")) {
        g_oocStrategicTreasure = std::atoi(d) != 0;
        if (g_oocStrategicTreasure)
            std::cout << "[OOC one-ply: treasure Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_BOSS_RELIC")) {
        g_oocStrategicBossRelic = std::atoi(d) != 0;
        if (g_oocStrategicBossRelic)
            std::cout << "[OOC one-ply: boss relic Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MAP")) {  // M1 map route Q gate
        g_oocStrategicMap = std::atoi(d) != 0;
        if (g_oocStrategicMap)
            std::cout << "[OOC one-ply: map route Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_MAP_ROUTE")) {      // M2 C_psi route search
        g_oocMapRoute = std::atoi(d) != 0;
        if (const char *h = std::getenv("STS_OOC_MAP_ROUTE_HORIZON"))
            g_oocMapRouteHorizon = std::atoi(h);
        if (g_oocMapRoute)
            std::cout << "[OOC map route search ON: horizon " << g_oocMapRouteHorizon
                      << " (needs STS_CPSI_NN + strategic net)]\n";
    }
    if (const char *d = std::getenv("STS_CPSI_NN")) {            // C_psi combat outcome surrogate
        const std::string path = std::string(d) == "1" ? "build/v_combat_cpsi.txt" : d;
        if (g_cpsiNet.load(path))
            std::cout << "[C_psi combat surrogate loaded: " << g_cpsiNet.description() << "]\n";
        else
            std::cerr << "[C_psi load failed: " << path << "]\n";
    }
    if (const char *d = std::getenv("STS_CPSI_CTR_PROBE")) {    // C_psi counter-sensitivity probe
        g_cpsiCtrProbe = std::atoi(d) != 0;
        if (g_cpsiCtrProbe) std::cout << "[C_psi counter-sensitivity probe ON (post-combat states)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_SHOP_BEAM")) {     // B1 multi-step shop beam (§2)
        g_oocShopBeam = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_WIDTH"))
            g_oocShopBeamWidth = std::atoi(w);
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_DEPTH"))
            g_oocShopBeamDepth = std::atoi(w);
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_BUDGET"))
            g_oocShopBeamBudget = std::atoi(w);
        if (g_oocShopBeam)
            std::cout << "[OOC shop beam ON: width " << g_oocShopBeamWidth
                      << " depth " << (g_oocShopBeamDepth > 0 ? std::to_string(g_oocShopBeamDepth) : "until-leave")
                      << " budget " << g_oocShopBeamBudget << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN")) {
        g_oocStrategicMargin = std::atof(d);
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_SCORE")) {
        g_oocStrategicScorePolicy = (strcmp(d, "policy") == 0);
        std::cout << "[OOC strategic score source: "
                  << (g_oocStrategicScorePolicy ? "policy (sigmoid)" : "q") << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_CARD"))
        g_oocStrategicMarginCard = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_REST"))
        g_oocStrategicMarginRest = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_EVENT"))
        g_oocStrategicMarginEvent = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_SHOP"))
        g_oocStrategicMarginShop = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_TREASURE"))
        g_oocStrategicMarginTreasure = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC"))
        g_oocStrategicMarginBossRelic = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_MAP"))
        g_oocStrategicMarginMap = std::atof(d);
    if (g_oocStrategicMarginCard >= 0.0 || g_oocStrategicMarginRest >= 0.0
        || g_oocStrategicMarginEvent >= 0.0 || g_oocStrategicMarginShop >= 0.0
        || g_oocStrategicMarginTreasure >= 0.0 || g_oocStrategicMarginBossRelic >= 0.0
        || g_oocStrategicMarginMap >= 0.0) {
        std::cout << "[OOC per-screen margins: card=" << g_oocStrategicMarginCard
                  << " rest=" << g_oocStrategicMarginRest
                  << " event=" << g_oocStrategicMarginEvent
                  << " shop=" << g_oocStrategicMarginShop
                  << " treasure=" << g_oocStrategicMarginTreasure
                  << " boss_relic=" << g_oocStrategicMarginBossRelic
                  << " map=" << g_oocStrategicMarginMap << "]\n";
    }
    if (const char *e = std::getenv("STS_OOC_STRATEGIC_GATE_EPS")) {
        const double v = std::atof(e);
        if (v > 0.0) g_oocStrategicGateEps = v;
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_GATE")) {
        // Wave B regret gate (ooc-qwin-continuation.md Step 5):
        // STS_OOC_STRATEGIC_GATE=regret replaces the margin rule with
        // Qmax(s) − Q(a_heur) > ε for every one-ply gate and the M2 route
        // search; the margin rule stays as the RNG-tied fallback.
        if (std::string(d) == "regret") {
            g_oocStrategicGateRegret = true;
            std::cout << "[OOC regret gate ON: eps " << g_oocStrategicGateEps << "]\n";
        }
    }
    if (const char *v = std::getenv("STRATEGIC_SAMPLES_PER_RUN"))
        g_strategicSamplesPerRun = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STRATEGIC_SAMPLE_ALL"))
        g_strategicSampleAll = std::atoi(v) != 0;
    if (const char *v = std::getenv("STRATEGIC_BRANCH_FIGHTS"))
        g_strategicBranchFights = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STRATEGIC_BRANCH_SIMS")) {
        std::istringstream in(v);
        std::vector<int> parsed;
        std::string token;
        while (std::getline(in, token, ',')) {
            const int p = std::atoi(token.c_str());
            if (p > 0) parsed.push_back(p);
        }
        if (!parsed.empty()) g_strategicBranchSims = parsed;
    }
    if (const char *v = std::getenv("STRATEGIC_BRANCH_FUTURES"))
        g_strategicBranchFutures = std::max(1, std::atoi(v));
    if (const char *d = std::getenv("STS_BOSS_RELIC")) {    // boss relic pick via V_win (needs v_win in v_server)
        g_bossRelicV = std::atoi(d) != 0;
        if (g_bossRelicV) std::cout << "[boss-relic pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_NEOW_V")) {        // Neow bonus pick via V_win
        g_neowV = std::atoi(d) != 0;
        if (g_neowV) std::cout << "[Neow bonus pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_WIN_NET")) {       // native V_win tree-walk (no v_server socket)
        const std::string path = std::string(d) == "1" ? "models/v_win_trees.txt" : d;
        if (!g_winNet.load(path, richIdxMap()))
            std::cerr << "[STS_WIN_NET] failed to load win tree: " << path << "\n";
    }
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_MODEL")) {
        g_runwinShadowModelPath = d;
        if (!g_runwinShadowNet.load(g_runwinShadowModelPath, e2cRawIdxMap(), "E2cRunwinNet"))
            std::cerr << "[STS_RUNWIN_SHADOW_MODEL] failed to load E2c RAW critic: " << g_runwinShadowModelPath << "\n";
    }
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_R"))
        g_runwinShadowR = std::max(1, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_PER_STRATUM"))
        g_runwinShadowPerStratum = std::max(1, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_MAX_GROUPS"))
        g_runwinShadowMaxGroups = std::max(0, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_RANK_ROOTS"))
        g_runwinRankRoots = std::max(1, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_RANK_MAX_LEAVES"))
        g_runwinRankMaxLeaves = std::max(1, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_RANK_MIN_LEAVES"))
        g_runwinRankMinLeaves = std::max(2, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_RANK_REFERENCE_M"))
        g_runwinRankReferenceFutures = std::max(1, std::atoi(d));
    if (const char *d = std::getenv("STS_RUNWIN_RANK_REFERENCE_SIMS"))
        g_runwinRankReferenceSims = std::max(0, std::atoi(d));
    {
        // The baseline is serverless by default. Set STS_NATIVE_OOC=0 only
        // for an explicit legacy-server comparison.
        const char *d = std::getenv("STS_NATIVE_OOC");
        g_nativeOoc = !d || std::atoi(d) != 0;
        if (g_nativeOoc) {
            if (!g_winNet.ok) g_winNet.load("models/v_win_trees.txt", richIdxMap());
            g_floorNet.load("models/v_rich_trees.txt", richIdxMap());
            if (!g_floorNet.ok) {
                std::cerr << "[native OOC] failed to load models/v_rich_trees.txt\n";
                return 1;
            }
            if (!g_winNet.ok) {
                std::cout << "[native V_win NOT loaded; win-rest helpers will use v_server fallback]\n";
            } else {
                std::cout << "[native OOC floor/win GBMs ON; no v_server required]\n";
            }
        }
    }
    if (const char *d = std::getenv("STS_PATH_V")) {        // model-driven pathing (uses forward-map feats)
        g_pathV = std::atoi(d) != 0;
        if (g_pathV) std::cout << "[model-driven pathing via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_PATH_GRAPH")) {    // graph NN scores each legal child subtree
        g_pathGraph = std::atoi(d) != 0;
        if (g_pathGraph) {
            g_pathV = 1;
            std::cout << "[model-driven pathing via full-map graph NN ON]\n";
        }
    }
    if (const char *d = std::getenv("STS_PATH_ACTION")) {   // direct paired route-action model
        g_pathAction = std::atoi(d) != 0;
        if (const char *m = std::getenv("STS_PATH_ACTION_MAX"))
            g_pathActionMax = std::atoi(m);
        if (const char *m = std::getenv("STS_PATH_ACTION_MARGIN"))
            g_pathActionMargin = std::atof(m);
        g_pathActionTrace = std::getenv("STS_PATH_ACTION_TRACE")
                         && std::atoi(std::getenv("STS_PATH_ACTION_TRACE")) != 0;
        if (g_pathAction) {
            g_pathV = 1;
            std::cout << "[model-driven pathing via paired route-action NN ON: max="
                      << g_pathActionMax << " margin=" << g_pathActionMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_EVENT_V")) {       // model-driven event choices
        g_eventV = std::atoi(d) != 0;
        if (g_eventV) std::cout << "[model-driven events via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_POTION_SAVE")) {   // dynamic potion-saving (keep for elites/bosses)
        g_potionSave = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_POTION_WINDOW"))  g_potionWindow  = std::atoi(v);
        if (const char *v = std::getenv("STS_POTION_BONUS"))   g_potionBonus   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_SPEND"))   g_potionSpend   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_DESIRED")) g_potionDesired = std::atof(v);
        if (g_potionSave)
            std::cout << "[potion-saving ON: window=" << g_potionWindow << " bonus=" << g_potionBonus
                      << " spend=" << g_potionSpend << " desired=" << g_potionDesired << "]\n";
    }
    if (const char *d = std::getenv("STS_SHOP_WIN")) {       // A/B: shop bundles scored by P(win)
        g_shopWin = std::atoi(d) != 0;
        if (g_shopWin) std::cout << "[shop scored via WIN model]\n";
    }
    if (const char *d = std::getenv("STS_SIMS_NORMAL")) g_simsNormal = std::atoi(d);  // per-fight sim budgets
    if (const char *d = std::getenv("STS_SIMS_ELITE"))  g_simsElite  = std::atoi(d);
    if (const char *d = std::getenv("STS_SIMS_BOSS"))   g_simsBoss   = std::atoi(d);
    if (g_simsNormal > 0 || g_simsElite > 0 || g_simsBoss > 0)
        std::cout << "[tiered sims: normal=" << g_simsNormal << " elite=" << g_simsElite
                  << " boss=" << g_simsBoss << " (-1=base)]\n";
    if (const char *d = std::getenv("STS_SIM_ADAPT")) {       // C_psi adaptive per-fight sim budget
        g_simAdapt = std::atoi(d) != 0;
        if (const char *f = std::getenv("STS_SIM_ADAPT_MIN_FRAC")) g_simAdaptMinFrac = std::atof(f);
        if (const char *f = std::getenv("STS_SIM_ADAPT_MAX_FRAC")) g_simAdaptMaxFrac = std::atof(f);
        if (g_simAdapt)
            std::cout << "[C_psi adaptive sim budget ON: frac " << g_simAdaptMinFrac
                      << ".." << g_simAdaptMaxFrac << " (needs STS_CPSI_NN)]\n";
    }
    if (const char *d = std::getenv("STS_CONVERGE")) {       // convergence-based early stopping
        search::g_convergeStop = std::atoi(d) != 0;
        if (const char *p = std::getenv("STS_CONV_PATIENCE")) search::g_convPatience = std::atoll(p);
        if (const char *m = std::getenv("STS_CONV_MIN"))      search::g_convMinSims  = std::atoll(m);
        if (search::g_convergeStop)
            std::cout << "[convergence stop ON: patience=" << search::g_convPatience
                      << " minSims=" << search::g_convMinSims << "]\n";
    }
    if (const char *d = std::getenv("STS_CONV_ROOT")) {      // root-stability early stopping
        search::g_convRootStop = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_CONV_ROOT_START"))   search::g_convRootStart = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_GROW"))    search::g_convRootGrow  = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_CHECK"))   search::g_convRootCheck = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_SHARE"))   search::g_convRootShare = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_VALUE"))   search::g_convRootValue = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_MIN"))     search::g_convRootMinSims = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_PATIENCE")) search::g_convRootPatience = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_MAX_FRAC")) search::g_convRootMaxFrac = std::atof(v);
        if (search::g_convRootStop)
            std::cout << "[root-stability stop ON: start=" << search::g_convRootStart
                      << " grow=" << search::g_convRootGrow
                      << " check=" << search::g_convRootCheck
                      << " share=" << search::g_convRootShare
                      << " value=" << search::g_convRootValue
                      << " minSims=" << search::g_convRootMinSims
                      << " patience=" << search::g_convRootPatience
                      << " maxFrac=" << search::g_convRootMaxFrac << "]\n";
        if (search::g_convRootStop && (search::g_convRootStart <= 0 || search::g_convRootGrow <= 1.0))
            std::cout << "[root-stability warning: STS_CONV_ROOT_START must be >0 and STS_CONV_ROOT_GROW >1.0;"
                      << " searchToTotalRootStable forces the full budget instead of growing by chunks]\n";
    }
    if (const char *d = std::getenv("STS_BOSS_DRAFT")) {      // boss-gated rollout drafting
        g_bossDraft = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS"))    g_bossDraftRows    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_N"))       g_bossDraftN       = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_SIMS"))    g_bossDraftSims    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_FUTURES")) g_bossDraftFutures = std::atoi(v);
        if (g_bossDraft)
            std::cout << "[boss-gated rollout draft ON: rows<=" << g_bossDraftRows
                      << " N=" << g_bossDraftN << " sims=" << g_bossDraftSims
                      << " futures=" << g_bossDraftFutures << "]\n";
    }
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_DRAFT")) {
        g_actFightProbeDraft = std::atoi(d) != 0;
        if (g_actFightProbeDraft)
            std::cout << "[all-act encounter rollout draft ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " floor-decay=" << g_actFightProbeFloorDecay
                      << "; immediate cards scored only by simulated fight utility]\n";
    }
    // Shared by both the card-only and every-OOC variants; parse independently
    // of the legacy card-only enable flag.
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_SIMS"))
        g_actFightProbeSims = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FUTURES"))
        g_actFightProbeFutures = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS")) {
        std::istringstream in(v);
        std::string token;
        while (std::getline(in, token, ',')) {
            const int parsed = std::atoi(token.c_str());
            if (parsed > 0) g_actFightProbeCheckpointSims.push_back(parsed);
        }
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FLOOR_DECAY"))
        g_actFightProbeFloorDecay = std::max(0.0, std::min(1.0, std::atof(v)));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS"))
        g_actFightProbeMaxCheckpoints = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_TRACE"))
        g_actFightProbeTrace = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PARALLEL"))
        g_actFightProbeParallelBranches = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT"))
        g_actFightProbePredict = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_ENCOUNTER_NN"))
        g_actFightProbeEncounterNN = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_NET"))
        g_actFightProbePredictNetPath = v;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_WIN_THRESHOLD"))
        g_actFightProbePredictWinThreshold = std::max(0.0, std::min(1.0, std::atof(v)));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_TERM_WIN")) {
        g_actFightProbeTermWin = std::max(0.0, std::atof(v));
        if (g_actFightProbeTermWin > 0.0)
            std::cout << "[all-acts checkpoint terminal win-GBM ON: weight="
                      << g_actFightProbeTermWin
                      << " (searched checkpoints; requires the native win model)]\n";
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_MARGIN")) {
        g_actFightProbeMargin = std::max(0.0, std::atof(v));
        if (g_actFightProbeMargin > 0.0)
            std::cout << "[all-acts checkpoint oracle margin gate ON: best-second >= "
                      << g_actFightProbeMargin << " required, else fallback stack]\n";
    }
    if (g_actFightProbePredict) {
        if (!g_actFightProbePredictNet.load(g_actFightProbePredictNetPath)
            || !g_actFightProbePredictNet.hasOutcomeHeads()) {
            std::cerr << "[all-acts checkpoint predictor load FAILED (needs combat_entity_v1): "
                      << g_actFightProbePredictNetPath << "]\n";
            return 2;
        }
        std::cout << "[all-acts checkpoint predictor ON: " << g_actFightProbePredictNetPath
                  << ", win threshold=" << g_actFightProbePredictWinThreshold << "]\n";
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_LOG"))
        g_actFightProbeLogPath = v;
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_ALL_OOC")) {
        g_actFightProbeAllOoc = std::atoi(d) != 0;
        if (g_actFightProbeAllOoc)
            std::cout << "[Acts 1-3 all-OOC checkpoint rollout ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " max-checkpoints=" << g_actFightProbeMaxCheckpoints
                      << (g_actFightProbeCheckpointSims.empty()
                          ? "" : " checkpoint-sims=" + actFightProbeCheckpointSimsCsv())
                      << (g_actFightProbeEncounterNN ? " predictor=ooc-encounter-NN(first-checkpoint)" : "")
                      << (g_actFightProbePredict ? " predictor=entity-transition" : "")
                      << "; every legal OOC action scored by fight-strength profile]\n";
    }
    if (g_actFightProbeParallelBranches) {
        if (g_potionSave)
            std::cout << "[all-acts branch parallelism disabled: dynamic potion saving writes shared combat state]\n";
        else if (g_actFightProbeTrace)
            std::cout << "[all-acts branch parallelism disabled: trace output must remain ordered]\n";
        else
            std::cout << "[all-acts branch parallelism ON: up to " << numThreads()
                      << " action-future branches at once]\n";
    }
    if (!g_actFightProbeLogPath.empty() && g_actFightProbeAllOoc && !initActFightProbeLog())
        return 2;
    if (const char *d = std::getenv("STS_STOP_AFTER_ACT")) {
        g_stopAfterAct = std::max(0, std::atoi(d));
        if (g_stopAfterAct > 0)
            std::cout << "[benchmark stops after Act " << g_stopAfterAct << " boss]\n";
    }
    if (const char *d = std::getenv("STS_FIGHTREP_CAPTURE_DIR")) {   // fightrep: Act-3 boss fight-start snapshots
        g_fightRepCaptureDir = d;
        std::cout << "[fightrep capture dir = " << d
                  << " (serialize every Act-3 boss fight-start)]\n";
    }
    if (const char *d = std::getenv("STS_BOSS_V")) {          // boss-survival V blended into near-boss picks
        g_bossV = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_BOSS_V_W"))       g_bossVW        = std::atof(w);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS")) g_bossDraftRows = std::atoi(v);
        if (g_bossV)
            std::cout << "[boss-V blend draft ON: w=" << g_bossVW
                      << " rows<=" << g_bossDraftRows << " (needs v_boss in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_SKIP_THR")) {        // card-reward skip threshold (marginal V)
        g_cardSkipThresh = std::atof(d);
        std::cout << "[card skip threshold = " << g_cardSkipThresh << "]\n";
    }
    if (const char *d = std::getenv("STS_VPATH")) {          // V-strength path modulation (needs v_server)
        g_vPath = std::atoi(d) != 0;
        if (const char *k = std::getenv("STS_VPATH_K")) g_vPathK = std::atof(k);
        if (g_vPath)
            std::cout << "[V-informed pathing ON: k=" << g_vPathK << " (needs v_server on :5555)]\n";
    }
    if (const char *d = std::getenv("STS_DG_TEMP")) {         // datagen softmax temperature (card marginals)
        g_dgTemp = std::atof(d);
        std::cout << "[datagen softmax temp = " << g_dgTemp << "]\n";
    }
    if (const char *d = std::getenv("STS_FAIR")) {            // determinized/ISMCTS combat (no future peeking)
        search::g_fairPlay = std::atoi(d) != 0;
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS ON]\n";
    }
    if (const char *d = std::getenv("STS_SEARCHER3")) {      // use enhanced BattleScumSearcher3 engine
        search::g_useSearcher3 = std::atoi(d) != 0;
        if (search::g_useSearcher3) std::cout << "[Searcher3 engine ON: belief/prune/chain/live (CRN opt-in)]\n";
    }
    const char *silverSearchEnv = std::getenv("STS_SILVER_SEARCH");
    const bool silverSearchRequested = silverSearchEnv && std::atoi(silverSearchEnv) != 0;
    if (const char *qualityFile = std::getenv("STS_SILVER_STICKY_QUALITY_FILE")) {
        if (*qualityFile != '\0' && !silverSearchRequested) {
            throw std::invalid_argument(
                "STS_SILVER_STICKY_QUALITY_FILE requires STS_SILVER_SEARCH=1");
        }
    }
    if (silverSearchRequested) {
            // The external callback takes precedence before ScumSearchAgent2
            // enters either Searcher2 or Searcher3. It owns local Silver
            // randomness and therefore never constructs an S3 Belief.
            search::installSilverLiveBackend();
            std::cout << "[isolated Silver combat backend ON: local Silver RNG/chance search; Searcher3 particles bypassed; reuse-cap="
                      << search::silverLiveReuseCapMode() << " cap=" << search::silverLiveReuseCap()
                      << "]\n";
    }
    // STS_LIVE_VALID (Phase 4, fair-tree structural fix): env opt-in as
    // recorded in §122, or default ON for the Searcher3 fair-play regime
    // since 2026-08-07 (§123: two independent 256-seed paired gates give
    // +5.5pp and +5.9pp win at +7.9% and +14.6% cpu — the recorded cpu-trade
    // call accepts that cost for the win; hp +4.1/+3.1, floor +0.6/+1.1).
    // STS_LIVE_VALID=0 explicitly disables. The fairgen datagen mode is NOT
    // covered (it forces the regime after this parse); datagen keeps the
    // recorded §117 behavior unless the flag is set explicitly.
    if (!std::getenv("STS_LIVE_VALID") && search::g_fairPlay && search::g_useSearcher3) {
        search::g_liveValid = true;
        std::cout << "[live-valid edge re-selection ON (fair S3 default, §123)]\n";
    }
    // ── Tree reuse control (STS_REUSE_*) ──────────────────────────────────
    if (const char *d = std::getenv("STS_REUSE_MAX_SEARCHES")) {
        search::g_reuseMaxSearches = std::atoi(d);
        std::cout << "[reuse max-searches = " << search::g_reuseMaxSearches << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_STATS_MODE")) {
        if (std::string(d) == "recursive_reset")
            search::g_reuseStatsMode = 1;
        else
            search::g_reuseStatsMode = 0;  // "keep" or unknown
        std::cout << "[reuse stats-mode = " << (search::g_reuseStatsMode ? "recursive_reset" : "keep") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_ALWAYS_Q")) {
        search::g_reuseAlwaysQ = std::atoi(d) != 0;
        std::cout << "[reuse always-Q = " << (search::g_reuseAlwaysQ ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ALWAYS_Q")) {
        search::g_s3AlwaysQ = std::atoi(d) != 0;
        std::cout << "[S3 always-Q = " << (search::g_s3AlwaysQ ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_DIAG")) {
        search::g_reuseDiag = std::atoi(d) != 0;
        std::cout << "[reuse diagnostics = " << (search::g_reuseDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_OBS_STABLE")) {
        search::g_reuseObsStable = std::atoi(d) != 0;
        std::cout << "[reuse obs-stable = " << (search::g_reuseObsStable ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_RECONCILE_ROOT")) {
        search::g_reuseReconcileRoot = std::atoi(d) != 0;
        std::cout << "[reuse reconcile-root = " << (search::g_reuseReconcileRoot ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CARRY_DIAG")) {
        search::g_reuseCarryDiag = std::atoi(d) != 0;
        std::cout << "[reuse carry-diag = " << (search::g_reuseCarryDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_SEMANTIC_CARD_EDGES")) {
        search::g_s3SemanticCardEdges = std::atoi(d) != 0;
        std::cout << "[S3 semantic-card-edges = " << (search::g_s3SemanticCardEdges ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG")) {
        search::g_s3OutcomeBucketDiag = std::atoi(d) != 0;
        std::cout << "[S3 outcome-bucket-diag = " << (search::g_s3OutcomeBucketDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG_FILE")) {
        search::g_s3OutcomeBucketDiagFile = d;
        std::cout << "[S3 outcome-bucket-diag file = " << search::g_s3OutcomeBucketDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG_PARTICLES")) {
        search::g_s3OutcomeBucketDiagParticles = std::atoi(d);
        std::cout << "[S3 outcome-bucket-diag particles = " << search::g_s3OutcomeBucketDiagParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG")) {
        search::g_s3StrategyFusionDiag = std::atoi(d) != 0;
        std::cout << "[S3 strategy-fusion diag = "
                  << (search::g_s3StrategyFusionDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_FILE")) {
        search::g_s3StrategyFusionDiagFile = d;
        std::cout << "[S3 strategy-fusion diag file = "
                  << search::g_s3StrategyFusionDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_PARTICLES")) {
        search::g_s3StrategyFusionDiagParticles = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag particles = "
                  << search::g_s3StrategyFusionDiagParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_MAX_TRANSITIONS")) {
        search::g_s3StrategyFusionDiagMaxTransitions = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag max transitions = "
                  << search::g_s3StrategyFusionDiagMaxTransitions << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_MIN_CHILD_VISITS")) {
        search::g_s3StrategyFusionDiagMinChildVisits = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag min child visits = "
                  << search::g_s3StrategyFusionDiagMinChildVisits << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_FRESH_SIMS")) {
        search::g_s3StrategyFusionDiagFreshSims = std::max(0, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag fresh sims = "
                  << search::g_s3StrategyFusionDiagFreshSims << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_REF_SIMS")) {
        search::g_s3StrategyFusionDiagReferenceSims = std::max(0, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag reference sims = "
                  << search::g_s3StrategyFusionDiagReferenceSims << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSISTENT_ENDTURN_CHANCE")) {
        search::g_s3PersistentEndTurnChance = std::atoi(d) != 0;
        std::cout << "[S3 persistent END_TURN chance = "
                  << (search::g_s3PersistentEndTurnChance ? "ON" : "off")
                  << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSISTENT_ENDTURN_MAX_PILE")) {
        search::g_s3PersistentEndTurnMaxPile = std::max(0, std::atoi(d));
        std::cout << "[S3 persistent END_TURN max-pile = "
                  << search::g_s3PersistentEndTurnMaxPile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG")) {
        search::g_s3BucketValueDiag = std::atoi(d) != 0;
        std::cout << "[S3 bucket-value-diag = " << (search::g_s3BucketValueDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG_FILE")) {
        search::g_s3BucketValueDiagFile = d;
        std::cout << "[S3 bucket-value-diag file = " << search::g_s3BucketValueDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG_ROLLOUTS")) {
        search::g_s3BucketValueDiagRollouts = std::atoi(d);
        std::cout << "[S3 bucket-value-diag rollouts = " << search::g_s3BucketValueDiagRollouts << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE")) {
        search::g_s3EndTurnMarginalize = std::atoi(d) != 0;
        std::cout << "[S3 END_TURN marginalization = " << (search::g_s3EndTurnMarginalize ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE_PARTICLES")) {
        search::g_s3EndTurnMarginalizeParticles = std::atoi(d);
        std::cout << "[S3 END_TURN marg particles = " << search::g_s3EndTurnMarginalizeParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE_MAX_PILE")) {
        search::g_s3EndTurnMarginalizeMaxPile = std::atoi(d);
        std::cout << "[S3 END_TURN marg max-pile = " << search::g_s3EndTurnMarginalizeMaxPile << "]\n";
    }
    if (!search::s3PersistentChanceFlagsCompatible(
            search::g_s3PersistentEndTurnChance,
            search::g_s3StrategyFusionDiag,
            search::g_s3EndTurnMarginalize)) {
        if (search::g_s3StrategyFusionDiag) {
            std::cerr << "error: STS_S3_PERSISTENT_ENDTURN_CHANCE and "
                         "STS_S3_STRATEGY_FUSION_DIAG are mutually exclusive; "
                         "the diagnostic assumes the legacy shared-child topology\n";
        } else {
            std::cerr << "error: STS_S3_PERSISTENT_ENDTURN_CHANCE and "
                         "STS_S3_ENDTURN_MARGINALIZE are mutually exclusive; "
                         "persistent chance nodes must not run with eager marginalization\n";
        }
        return 2;
    }
    if (search::g_s3PersistentEndTurnChance)
        std::atexit(search::printPersistentEndTurnChanceDiagnostics);
    if (const char *d = std::getenv("STS_S3_DRAW_PROB_DIAG")) {
        search::g_s3DrawProbDiag = std::atoi(d) != 0;
        std::cout << "[S3 draw-prob diag = " << (search::g_s3DrawProbDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_DRAW_PROB_DIAG_FILE")) {
        search::g_s3DrawProbDiagFile = d;
        std::cout << "[S3 draw-prob diag file = " << search::g_s3DrawProbDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LEAFVALUE_DIAG")) {
        search::g_s3LeafValueDiag = std::atoi(d) != 0;
        std::cout << "[S3 leafvalue diag = " << (search::g_s3LeafValueDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LEAFVALUE_DIAG_FILE")) {
        search::g_s3LeafValueDiagFile = d;
        std::cout << "[S3 leafvalue diag file = " << search::g_s3LeafValueDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BELIEF_AUDIT")) {
        search::g_s3BeliefAudit = std::atoi(d) != 0;
        std::cout << "[S3 belief audit = " << (search::g_s3BeliefAudit ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REAL_BELIEF_FILTER")) {
        search::g_s3RealBeliefFilter = std::atoi(d) != 0;
        std::cout << "[S3 real-belief-filter = " << (search::g_s3RealBeliefFilter ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REAL_BELIEF_COLLAPSE_FRESH")) {
        search::g_s3RealBeliefCollapseFresh = std::atoi(d) != 0;
        std::cout << "[S3 real-belief-collapse-fresh = " << (search::g_s3RealBeliefCollapseFresh ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSIST_FILTERED_BELIEF")) {
        search::g_s3PersistFilteredBelief = std::atoi(d) != 0;
        std::cout << "[S3 persist-filtered-belief = " << (search::g_s3PersistFilteredBelief ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_INTERNAL_BELIEF_UPDATE")) {
        search::g_s3InternalBeliefUpdate = std::atoi(d) != 0;
        std::cout << "[S3 internal-belief-update = " << (search::g_s3InternalBeliefUpdate ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_SHADOW")) {
        search::g_s3RejuvShadow = std::atoi(d) != 0;
        std::cout << "[S3 rejuv-shadow = " << (search::g_s3RejuvShadow ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_TRIGGER")) {
        search::g_s3RejuvTrigger = std::max(0, std::atoi(d));
        std::cout << "[S3 rejuv trigger = " << search::g_s3RejuvTrigger << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_PROPOSALS")) {
        search::g_s3RejuvProposals = std::max(1, std::atoi(d));
        std::cout << "[S3 rejuv proposals = " << search::g_s3RejuvProposals << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_SHADOW_FILE")) {
        search::g_s3RejuvShadowFile = d;
        std::cout << "[S3 rejuv shadow file = " << search::g_s3RejuvShadowFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_REJUV_LIVE")) {
        const std::string mode = d;
        if (mode == "off") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::OFF;
        else if (mode == "placebo") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::PLACEBO;
        else if (mode == "ai") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::AI_RNG;
        else if (mode == "placebo1") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::PLACEBO1;
        else if (mode == "ai1") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::AI_RNG1;
        else {
            std::cerr << "Invalid STS_S3_AI_REJUV_LIVE='" << mode
                      << "'; expected off, placebo, ai, placebo1, or ai1\n";
            return 2;
        }
        std::cout << "[S3 AI rejuvenation live = " << mode << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_REJUV_LIVE_FILE")) {
        search::g_s3LiveRejuvenationFile = d;
        std::cout << "[S3 AI rejuvenation live file = " << search::g_s3LiveRejuvenationFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_SHADOW")) {
        search::g_s3AiSensitivityShadow = std::atoi(d) != 0;
        std::cout << "[S3 AI sensitivity shadow = "
                  << (search::g_s3AiSensitivityShadow ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_FILE")) {
        search::g_s3AiSensitivityFile = d;
        std::cout << "[S3 AI sensitivity file = " << search::g_s3AiSensitivityFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_ROOTS_PER_SEED")) {
        search::g_s3AiSensitivityRootsPerSeed = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_ALTS")) {
        search::g_s3AiSensitivityAlternatives = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_SIMS")) {
        search::g_s3AiSensitivitySims = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_RNG_EXPOSURE_DIAG")) {
        search::g_s3RngExposureDiag = std::atoi(d) != 0;
        std::cout << "[S3 RNG exposure diag = " << (search::g_s3RngExposureDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_RNG_EXPOSURE_DIAG_FILE")) {
        search::g_s3RngExposureDiagFile = d;
        std::cout << "[S3 RNG exposure diag file = " << search::g_s3RngExposureDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BELIEF_AUDIT_FILE")) {
        search::g_s3BeliefAuditFile = d;
        std::cout << "[S3 belief audit file = " << search::g_s3BeliefAuditFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_DIAG")) {
        search::g_s3RootRaceDiag = std::atoi(d) != 0;
        std::cout << "[S3 root-race diag = " << (search::g_s3RootRaceDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_DIAG_FILE")) {
        search::g_s3RootRaceDiagFile = d;
        std::cout << "[S3 root-race diag file = " << search::g_s3RootRaceDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_MAX_STATES")) {
        search::g_s3RootRaceDiagMaxStates = std::max(1, std::atoi(d));
        std::cout << "[S3 root-race max states = " << search::g_s3RootRaceDiagMaxStates << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_GATE_TIMING_DIAG")) {
        search::g_s3GateTimingDiag = std::atoi(d) != 0;
        std::cout << "[S3 Q-gate timing diag = "
                  << (search::g_s3GateTimingDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_GATE_TIMING_DIAG_FILE")) {
        search::g_s3GateTimingDiagFile = d;
        std::cout << "[S3 Q-gate timing diag file = "
                  << search::g_s3GateTimingDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_UNION_EXPAND")) {
        search::g_s3UnionExpand = std::atoi(d) != 0;
        std::cout << "[S3 union-expand = " << (search::g_s3UnionExpand ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CPU_DIAG")) {
        search::g_reuseCpuDiag = std::atoi(d) != 0;
        std::cout << "[reuse cpu-diag = " << (search::g_reuseCpuDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CPU_DIAG_FILE")) {
        search::g_reuseCpuDiagFile = d;
        std::cout << "[reuse cpu-diag file = " << search::g_reuseCpuDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_FORCE_RELIC")) {      // force a relic at run start (paired A/B)
        const std::string name(d);
        int id = -1;
        for (int i = 0; i < kNumRelics; ++i)
            if (name == relicEnumNames[i]) { id = i; break; }
        if (id < 0) {
            std::cerr << "[STS_FORCE_RELIC] unknown relic name: " << name << "\n";
        } else {
            g_forceRelic = (RelicId)id;
            std::cout << "[forced relic at run start: " << relicEnumNames[id] << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_TERM_STALL_LOG")) {   // per-combat stall telemetry
        g_stallLogPath = d;
        std::cout << "[stall telemetry log: " << g_stallLogPath << "]\n";
    }
    if (const char *d = std::getenv("STS_TERM_WIN")) {       // terminal-leaf run-value bonus (S3)
        g_termWin = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_TERM_WIN_W")) g_termWinW = std::max(0.0, std::atof(w));
        if (const char *h = std::getenv("STS_TERM_WIN_HIDDEN")) g_termWinHidden = std::string(h) == "zero" ? 0 : 1;
        if (const char *e = std::getenv("STS_TERM_WIN_EVAL"))
            g_termWinEval = std::string(e) == "cpsi" ? 1 : 0;
        if (g_termWin) {
            if (g_termWinEval == 1 && !g_cpsiNet.loaded())
                std::cerr << "[terminal-leaf cpsi evaluator: STS_CPSI_NN not loaded; falling back to win tree]\n";
            if (!g_winNet.ok) g_winNet.load("models/v_win_trees.txt", richIdxMap());
            std::cout << "[terminal-leaf run-value bonus ON: w=" << g_termWinW
                      << " eval=" << (g_termWinEval == 1 ? "cpsi" : "win")
                      << " hidden=" << (g_termWinHidden ? "resample" : "zero")
                      << " (S3 victory leaves; requires the native win model)]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_BELIEF")) {      // S3 ablation: particle belief reweighting
        search::g_s3Belief = std::atoi(d) != 0;
        std::cout << "[S3 ablation: belief=" << (search::g_s3Belief ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_POOL_REDIRECT")) {  // S3 fair: forced-move budget pool redirect (opt-in)
        search::g_s3PoolRedirect = std::atoi(d) != 0;
        std::cout << "[S3 pool-redirect = " << (search::g_s3PoolRedirect ? "ON" : "off") << "]\n";
    }
    // A2: dynamic alpha by rollout length (opt-in)
    if (const char *d = std::getenv("STS_VNET_ALPHA_LEN")) {
        search::g_vnetAlphaLen = std::atoi(d) != 0;
        if (const char *t = std::getenv("STS_VNET_ALPHA_LEN_TABLE")) {
            search::g_vnetAlphaLenTable.clear();
            std::string ts(t);
            size_t pos = 0;
            while (pos < ts.size()) {
                auto comma = ts.find(',', pos);
                if (comma == std::string::npos) comma = ts.size();
                auto colon = ts.find(':', pos);
                if (colon != std::string::npos && colon < comma) {
                    int ceil = std::stoi(ts.substr(pos, colon-pos));
                    double a = std::stod(ts.substr(colon+1, comma-colon-1));
                    search::g_vnetAlphaLenTable.push_back({ceil, a});
                }
                pos = comma + 1;
            }
        }
        std::cout << "[VNet alpha-len = " << (search::g_vnetAlphaLen ? "ON" : "off");
        if (search::g_vnetAlphaLen) {
            std::cout << " table=";
            for (size_t i = 0; i < search::g_vnetAlphaLenTable.size(); ++i) {
                if (i) std::cout << ",";
                std::cout << search::g_vnetAlphaLenTable[i].first << ":"
                          << search::g_vnetAlphaLenTable[i].second;
            }
        }
        std::cout << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PRUNE")) {       // S3 ablation: canPruneAsDead pruning
        search::g_s3Prune = std::atoi(d) != 0;
        std::cout << "[S3 ablation: prune=" << (search::g_s3Prune ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_CHAIN")) {       // S3 ablation: deterministic chain compression
        search::g_s3Chain = std::atoi(d) != 0;
        std::cout << "[S3 ablation: chain=" << (search::g_s3Chain ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LIVE")) {        // S3 ablation: live-valid root-edge filter
        search::g_s3Live = std::atoi(d) != 0;
        std::cout << "[S3 ablation: live=" << (search::g_s3Live ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_CRN")) {         // S3 opt-in: root CRN warm start (once per fresh searcher)
        search::g_s3Crn = std::atoi(d) != 0;
        std::cout << "[S3 ablation: crn=" << (search::g_s3Crn ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PARTICLES")) {   // S3 belief particle count (default 64)
        const int n = std::atoi(d);
        if (n >= 1) {
            search::g_s3Particles = n;
            std::cout << "[S3 particles = " << search::g_s3Particles << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_EXPAND")) {      // Phase 6: on-no-valid-edge expansion (requires live-valid semantics)
        search::g_s3Expand = std::atoi(d) != 0;
        std::cout << "[S3 expand = " << (search::g_s3Expand ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_EXPAND_MAX")) {  // cap on new edges added per expansion (default 32)
        const int n = std::atoi(d);
        if (n >= 1) search::g_s3ExpandMaxNew = n;
    }
    if (const char *d = std::getenv("STS_S3_EXPAND_SIMPLE")) {  // no-PUCT edge expansion: pick by rolloutWeight
        search::g_s3ExpandSimple = std::atoi(d) != 0;
        std::cout << "[S3 expand-simple = " << (search::g_s3ExpandSimple ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_POLICY")) {  // sample rollout actions from the GBM policy prior (opt-in)
        search::g_s3RolloutPolicy = std::atoi(d) != 0;
        std::cout << "[S3 rollout-policy = " << (search::g_s3RolloutPolicy ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_K")) {      // A1: K rollouts per leaf, averaged (opt-in)
        const int k = std::atoi(d);
        if (k >= 1) {
            search::g_s3RolloutK = k;
            std::cout << "[S3 rollout-K = " << search::g_s3RolloutK << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_TURN_STOP")) {  // A4: stop rollout after N full player turns (opt-in)
        const int n = std::atoi(d);
        if (n >= 0) {
            search::g_s3RolloutTurnStop = n;
            std::cout << "[S3 rollout turn-stop = " << search::g_s3RolloutTurnStop << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_TURN_ROLLOUT")) {  // B1: tactical turn-beam rollout (opt-in)
        search::g_s3TurnRollout = std::atoi(d) != 0;
        if (search::g_s3TurnRollout) {
            if (const char *w = std::getenv("STS_S3_TURN_BEAM_WIDTH")) {
                const int n = std::atoi(w);
                if (n >= 1) search::g_s3TurnBeamWidth = n;
            }
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W1")) search::g_s3TurnScoreW1 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W2")) search::g_s3TurnScoreW2 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W3")) search::g_s3TurnScoreW3 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W4")) search::g_s3TurnScoreW4 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W5")) search::g_s3TurnScoreW5 = std::atof(w);
            std::cout << "[S3 turn-beam rollout ON: width=" << search::g_s3TurnBeamWidth
                      << " scorer w1..w5=" << search::g_s3TurnScoreW1 << "/" << search::g_s3TurnScoreW2
                      << "/" << search::g_s3TurnScoreW3 << "/" << search::g_s3TurnScoreW4
                      << "/" << search::g_s3TurnScoreW5 << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_RISK_LAMBDA")) {    // risk sensitivity for Searcher3 PUCT
        search::g_riskLambda = std::atof(d);
        std::cout << "[risk lambda = " << search::g_riskLambda << "]\n";
    }
    if (const char *d = std::getenv("STS_VNET")) {           // learned V_combat leaf value
        std::string path = std::string(d) == "1" ? "build/v_combat_trees.txt" : d;
        if (search::g_combatVNet.load(path)) {
            g_effectiveVNetPath = path;
            search::g_useVNet = true;
            if (const char *a = std::getenv("STS_VNET_ALPHA")) search::g_vnetAlpha = std::atof(a);
            if (const char *b = std::getenv("STS_COMBAT_WIN_BONUS"))
                search::g_combatVNet.setWinBonus(std::atof(b));
            if (const char *c = std::getenv("STS_VNET_COND_BOSS"))
                search::g_vnetCondBossOnly = std::atoi(c) != 0;
            if (const char *c = std::getenv("STS_VNET_COND_ACT3"))
                search::g_vnetCondAct3 = std::atoi(c) != 0;
            std::cout << "[V_combat leaf value ON: " << path << ", "
                      << search::g_combatVNet.description() << ", alpha "
                      << search::g_vnetAlpha
                      << (search::g_vnetCondBossOnly ? ", cond-boss-only" : "")
                      << (search::g_vnetCondAct3 ? ", cond-act3" : "") << "]\n";
        } else {
            std::cout << "[V_combat load FAILED: " << path << "]\n";
        }
    }
    // V_combat leaf default (§148 hyperparameter-tuned model trained on the
    // 7k combat dataset, 1.58M rows / 87K fights). 50-trial Optuna TPE search
    // found better-regularized XGBoost params (min_child_weight 82, L1 α=1.8,
    // γ=4.4, subsample 0.54, eta 0.03). Trained on the full 7k corpus with
    // these params, exported at 1000 trees. 64-seed S3-fair gate: 37.5% win
    // vs 31.2% for the honest-data tuned model and 20.3% for the original
    // (§126 model). The improvement is +6.3pp from 5.5× data and +10.9pp
    // from hyperparameters for a total of +17.2pp over the §126 baseline.
    // Scoped: fair + Searcher3 only, when STS_VNET is unset.
    if (!std::getenv("STS_VNET") && search::g_fairPlay && search::g_useSearcher3) {
        const char *vnetDefault = "models/v_combat_7k_tuned.txt";
        if (search::g_combatVNet.load(vnetDefault)) {
            g_effectiveVNetPath = vnetDefault;
            search::g_useVNet = true;
            search::g_vnetAlpha = 0.3;
            std::cout << "[V_combat leaf default ON: " << vnetDefault << ", "
                      << search::g_combatVNet.description() << ", alpha "
                      << search::g_vnetAlpha << " (fair S3, §148)]\n";
        } else {
            std::cout << "[V_combat leaf default load FAILED: "
                      << vnetDefault << " (continuing without)]\n";
        }
    }
    // Per-encounter specialization overlay (per-boss fine-tuned trees from
    // train_value_combat_per_encounter.py, or combat_mlp_meta_v1 deltas already
    // inside a loaded base). Must run after the base model is loaded (STS_VNET
    // or the fair-S3 default): loadEncounterModels replaces the base weights
    // with <dir>/_pooled.txt when present and dispatches predict(bc) to
    // <dir>/<ENUM_NAME>.txt per-encounter models. A missing/invalid dir only
    // warns and keeps the already-loaded base model.
    if (const char *d = std::getenv("STS_VNET_PER_ENCOUNTER")) {
        const std::string dir = d;
        if (search::g_combatVNet.loadEncounterModels(dir)) {
            std::vector<int> encs;
            encs.reserve(search::g_combatVNet.encounterModels.size());
            for (const auto &kv : search::g_combatVNet.encounterModels) encs.push_back(kv.first);
            std::sort(encs.begin(), encs.end());
            std::string names;
            for (int e : encs) {
                if (!names.empty()) names += ",";
                names += monsterEncounterEnumNames[e];
            }
            std::cout << "[V_combat per-encounter models ON: " << dir << " ("
                      << encs.size() << "): " << names << "; base "
                      << search::g_combatVNet.description() << "]\n";
        } else {
            std::cout << "[V_combat per-encounter load FAILED: " << dir
                      << " (no per-encounter dispatch; continuing with the "
                         "already-loaded base model)]\n";
        }
    }
    // Zero-mean ranking correction (STS_VNET_RANK_CORR, experimental,
    // standalone diagnostic model — NOT a default; nothing is promoted without
    // a paired gameplay gate): a small compact-tree model trained on
    // group-centered leafref - endHp_pred residuals, ADDED on top of the
    // primary vnet/PVNet leaf value in evaluateLeaf()/evaluateLeafState() to
    // improve within-group action ranking without shifting the HP scale (the
    // fair-path search-complete clamp re-zeroes the per-search mean). Parsed
    // after the STS_VNET region so it works with the deployed vnet and with
    // experimental vnets. Non-fatal: a missing/invalid path only warns and
    // keeps the correction off (behavior byte-identical to the uncorrected
    // searcher).
    if (const char *d = std::getenv("STS_VNET_RANK_CORR")) {
        const std::string path = d;
        if (search::g_combatVNetRankCorr.load(path)) {
            search::g_useVNetRankCorr = true;
            std::cout << "[V_combat rank-correction ON: " << path << ", "
                      << search::g_combatVNetRankCorr.description() << "]\n";
        } else {
            std::cout << "[V_combat rank-correction load FAILED: " << path
                      << " (continuing without; behavior byte-identical to the "
                         "uncorrected searcher)]\n";
        }
    }
    // Residual VNet correction (STS_VNET_RESIDUAL=<path>, STS_VNET_RESIDUAL_BETA=<b>):
    // the loaded model is ADDED with weight beta on top of the primary VNet.
    // At beta=0, behavior is byte-identical to the uncorrected searcher.
    if (const char *d = std::getenv("STS_VNET_RESIDUAL")) {
        const std::string path = d;
        if (const char *b = std::getenv("STS_VNET_RESIDUAL_BETA"))
            search::g_vnetResidualBeta = std::atof(b);
        if (search::g_combatVNetResidual.load(path)) {
            search::g_useVNetResidual = true;
            std::cout << "[V_combat residual ON: " << path << ", beta="
                      << search::g_vnetResidualBeta << " "
                      << search::g_combatVNetResidual.description() << "]\n";
        } else {
            std::cout << "[V_combat residual load FAILED: " << path << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_DIAG_VNET2")) {   // secondary diagnostic vnet (leafdiag/leafref only)
        std::string path = d;
        if (g_combatVNetDiag.load(path)) {
            std::cout << "[DIAG V_combat #2 ON: " << path << ", "
                      << g_combatVNetDiag.description()
                      << " (leafdiag/leafref diagnostics only; never used by the search)]\n";
        } else {
            std::cout << "[DIAG V_combat #2 load FAILED: " << path
                         << " (leafdiag reports NaN for secondary predictions)]\n";
        }
    }
    if (const char *a = std::getenv("STS_DIAG_VNET2_ALPHA")) {   // reporting-only blend for the secondary model
        std::cout << "[DIAG V_combat #2 alpha = " << std::atof(a) << " (reporting only)]\n";
    }
    // VNet query log (STS_VNET_QUERY_LOG=<path>): log every CombatValueNet::predict()
    // call inside Searcher3 to a CSV for train-vs-deployment distribution shift diagnostics.
    // STS_VNET_QUERY_SAMPLE=<prob> (default 1.0) controls the sampling rate.
    // Zero behavior change when unset.
    if (const char *d = std::getenv("STS_VNET_QUERY_LOG")) {
        g_vnetQueryLogPath = d;
        if (const char *s = std::getenv("STS_VNET_QUERY_SAMPLE")) {
            g_vnetQuerySample = std::atof(s);
            if (g_vnetQuerySample <= 0.0) g_vnetQuerySample = 1.0;
            if (g_vnetQuerySample > 1.0)  g_vnetQuerySample = 1.0;
        }
        g_vnetQueryLogFile.open(g_vnetQueryLogPath, std::ios::out);
        if (g_vnetQueryLogFile.is_open()) {
            g_vnetQueryLogFile << "seed,fightIdx,decIdx,parentObsHash,depth";
            for (const auto &name : search::combatFeatureNames())
                g_vnetQueryLogFile << ',' << name;
            g_vnetQueryLogFile << ",vnetPred\n";
            g_vnetQueryLogFile.flush();
            search::g_onVNetQuery = onVNetQuery;
            std::cout << "[VNet query log ON: " << g_vnetQueryLogPath
                      << " sample=" << g_vnetQuerySample << "]\n";
        } else {
            std::cerr << "[VNet query log FAILED to open: " << g_vnetQueryLogPath << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_LEAFDIAG_PER_STRATUM")) {   // leafdiag reservoir capacity per stratum per seed
        const int n = std::atoi(d);
        if (n >= 1) g_ldPerStratum = n;
    }
    if (const char *d = std::getenv("STS_LEAFDIAG_DEEP_DEPTH")) {    // leafdiag deep-tree stratum threshold
        const int n = std::atoi(d);
        if (n >= 1) g_ldDeepDepth = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_FILE")) {
        g_particleLeafProbeFile = d;
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_K")) {
        const int k = std::atoi(d); if (k >= 1) g_particleLeafProbeK = k;
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_RATE")) {
        g_particleLeafProbeRate = std::atof(d);
        g_particleLeafProbeRate = std::max(0.0, std::min(1.0, g_particleLeafProbeRate));
    }
    if (const char *d = std::getenv("STS_PARTICLE_LEAF_PROBE_MAX_GROUPS")) {
        const int n = std::atoi(d); if (n >= 0) g_particleLeafProbeMaxGroups = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_FILE")) {
        g_particlePosteriorProbeFile = d;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_K")) {
        const int k = std::atoi(d); if (k >= 0) g_particlePosteriorProbeK = k;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_PROBE_MAX_GROUPS")) {
        const int n = std::atoi(d); if (n >= -1) g_particlePosteriorProbeMaxGroups = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_SPLIT"))
        g_particlePosteriorAgeSplit = std::atoi(d) != 0;
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_EARLY_START"))
        g_particlePosteriorAgeEarlyStart = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_EARLY_END"))
        g_particlePosteriorAgeEarlyEnd = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_LATE_START"))
        g_particlePosteriorAgeLateStart = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_LATE_END"))
        g_particlePosteriorAgeLateEnd = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_MIN_PER_STRATUM"))
        g_particlePosteriorAgeMinPerStratum = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_AGE_PER_STRATUM"))
        g_particlePosteriorAgePerStratum = std::atoi(d);
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_DEBUG_FILE"))
        g_particlePosteriorReplayDebugFile = d;
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_CEILING")) {
        const int n = std::atoi(d); if (n >= 1) g_particlePosteriorReplayCeiling = n;
    }
    if (const char *d = std::getenv("STS_PARTICLE_POSTERIOR_REPLAY_TRACE_FILE"))
        g_particlePosteriorReplayTraceFile = d;
    if (const char *d = std::getenv("STS_FRONTIERGEN_PER_STRATUM")) {   // frontiergen reservoir capacity per stratum per seed
        const int n = std::atoi(d);
        if (n >= 1) g_fgPerStratum = n;
    }
    if (const char *d = std::getenv("STS_DIST_VNET")) {    // distributional V_combat (transformer, 5-head)
        std::string path = d;
        if (search::g_combatDistVNet.load(path)) {
            search::g_useDistVNet = true;
            std::cout << "[Dist V_combat ON: " << path << ", "
                      << search::g_combatDistVNet.description() << "]\n";
        } else {
            std::cout << "[Dist V_combat load FAILED: " << path << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_PVNET")) {        // shared policy-value network (AlphaZero-style)
        std::string path = d;
        if (search::g_combatPVNet.load(path)) {
            search::g_usePVNet = true;
            std::cout << "[PVNet ON: " << path << ", "
                      << search::g_combatPVNet.description() << "]\n";
        } else {
            std::cout << "[PVNet load FAILED: " << path << "]\n";
        }
    }
    if (search::g_usePVNet) {
        if (const char *a = std::getenv("STS_PVNET_ALPHA")) search::g_pvnetAlpha = std::atof(a);
        if (const char *v = std::getenv("STS_PVNET_VALUE_ONLY")) search::g_pvnetValueOnly = std::atoi(v) != 0;
        if (const char *h = std::getenv("STS_PVNET_HP_SCALE")) search::g_pvnetHpScale = std::atoi(h) != 0;
        // Phase 6 deployment-speed knobs (S3 leaf). STS_PVNET_CACHE defaults
        // ON (behavior-preserving; visibleHash leaf-value cache at the
        // direct-eval sites). STS_PVNET_COND_{TURN,DEPTH,BOSS} gate the
        // per-expansion NN leaf: rollout-only for easy continuations, NN for
        // long/unresolved ones. Defaults preserve pre-phase-6 behavior.
        if (const char *c = std::getenv("STS_PVNET_CACHE")) search::g_pvnetCache = std::atoi(c) != 0;
        if (const char *c = std::getenv("STS_PVNET_COND_TURN")) search::g_pvnetCondMinTurn = std::atoi(c);
        if (const char *c = std::getenv("STS_PVNET_COND_DEPTH")) search::g_pvnetCondMinDepth = std::atoi(c);
        if (const char *c = std::getenv("STS_PVNET_COND_BOSS")) search::g_pvnetCondBossOnly = std::atoi(c) != 0;
        std::cout << "[PVNet alpha = " << search::g_pvnetAlpha;
        if (search::g_pvnetValueOnly) std::cout << ", value-only";
        if (search::g_pvnetHpScale) std::cout << ", hp-scale";
        if (search::g_pvnetCondMinTurn > 0) std::cout << ", cond-turn>=" << search::g_pvnetCondMinTurn;
        if (search::g_pvnetCondMinDepth > 0) std::cout << ", cond-depth>=" << search::g_pvnetCondMinDepth;
        if (search::g_pvnetCondBossOnly) std::cout << ", cond-boss-only";
        if (!search::g_pvnetCache) std::cout << ", leaf-cache-off";
        std::cout << "]\n";
    }
    // AZ-lite policy-guided PUCT selection. DEFAULT ON (+4.3pp full-run win @512
    // vs plain UCB, §26): auto-loads the compact net if present. STS_POLICY=0
    // disables; STS_POLICY=<path> overrides the file; STS_POLICY=1 uses the full
    // 447-tree net. Skipped for policygen so base datasets stay UCB-generated
    // (set STS_POLICY explicitly there for AlphaZero-style self-play iteration).
    {
        const char *d = std::getenv("STS_POLICY");
        const bool disabled = d && std::string(d) == "0";
        if (!disabled && mode != "policygen") {
            std::string path = "models/policy_trees_c.txt";
            if (d && std::string(d) == "1")      path = "build/policy_trees.txt";
            else if (d)                          path = d;
            search::g_policyNet.isPolicy = true;
            if (search::g_policyNet.load(path)) {
                g_effectivePolicyPath = path;
                search::g_usePolicyNet = true;
                std::cout << "[policy PUCT ON: " << path << ", "
                          << search::g_policyNet.description() << "]\n";
            } else if (d) {                       // warn only if explicitly requested
                std::cout << "[policy net load FAILED: " << path << "]\n";
            }
        }
    }
    if (search::g_usePolicyNet || search::g_usePVNet) {
        if (const char *c = std::getenv("STS_CPUCT")) search::g_cPuct = std::atof(c);
        std::cout << "[c_puct = " << search::g_cPuct << "]\n";
    }

    if (mode == "bench") {
        int sims   = argc > 2 ? std::stoi(argv[2]) : 2000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 100;
        benchmark(sims, nSeeds);

    } else if (mode == "strategicmarggen") {
        // Encounter-marginalization diagnostic: uniform sample per run, H hidden worlds.
        // Tier-B branch contract frozen at K=3 fights, 150/100/50 sims, bootstrap=true.
        int nSeeds     = argc > 2 ? std::stoi(argv[2]) : 20;
        int outerSims  = argc > 3 ? std::stoi(argv[3]) : 1000;
        int H          = argc > 4 ? std::stoi(argv[4]) : 4;
        int maxPerRun  = argc > 5 ? std::stoi(argv[5]) : 20;
        std::string out = argc > 6 ? argv[6] : "build/hidden_marg.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 300000;
        std::cout << "strategicmarggen seeds " << seedOff << ".." << seedOff+nSeeds-1
                  << " outerSims=" << outerSims << " H=" << H
                  << " maxPerRun=" << maxPerRun
                  << " (Tier-B branch: K=3, 150/100/50, bootstrap=true)"
                  << " -> " << out << '\n';
        strategicMargGen(nSeeds, outerSims, H, maxPerRun, out, seedOff);

    } else if (mode == "oocfactoreval") {
        // nDecisions is explicit for tools/seed_guard.sh and checked against
        // the manifest by the offline workflow.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_factor/manifest.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_factor/adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        std::cout << "oocfactoreval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart, nDecisions);

    } else if (mode == "oocmargtradeoffeval") {
        // Each replicate resamples the remaining encounters once, shared by
        // the safe/strength sibling actions.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        std::cout << "oocmargtradeoffeval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart,
                          nDecisions, true);

    } else if (mode == "oock3tradeoffeval") {
        // Resolve the frozen semantic pair before evaluating sibling-shared
        // marginal futures under the strategic K=3+bootstrap contract.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/k3_targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/k3_validation.csv";
        int futures = argc > 5 ? std::stoi(argv[5]) : 16;
        int futureStart = argc > 6 ? std::stoi(argv[6]) : 1000;
        if (futures < 0) throw std::runtime_error("oock3tradeoffeval: futures must be nonnegative");
        std::cout << "oock3tradeoffeval decisions=" << nDecisions
                  << " futures=" << futures << " futureStart=" << futureStart
                  << " contract=K3+bootstrap -> " << out << '\n';
        oocFactorEvaluate(manifest, out, 0, futures, futureStart,
                          nDecisions, true, true);

    } else if (mode == "oocsemanticfullruneval") {
        // Resolve the frozen semantic pair exactly as oock3tradeoffeval does,
        // then continue both siblings to terminal run outcome.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/fullrun_targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/fullrun_adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        if (futures < 0) throw std::runtime_error("oocsemanticfullruneval: futures must be nonnegative");
        std::cout << "oocsemanticfullruneval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart,
                          nDecisions, true, false, true);

    } else if (mode == "mcts") {
        int sims          = argc > 2 ? std::stoi(argv[2]) : 2000;
        std::uint64_t sd  = argc > 3 ? std::stoull(argv[3]) : 42;
        Result res = runCombat(sd, makeMctsPolicy(sims), true);
        std::printf("\n=== %s ===  hp %d/%d  turns %d\n",
                    res.won ? "WIN" : "LOSS", res.hpEnd, res.maxHp, res.turns);

    } else if (mode == "random") {
        std::uint64_t sd = argc > 2 ? std::stoull(argv[2]) : 42;
        Result res = runCombat(sd, &randomPolicy, true);
        std::printf("\n=== %s ===  hp %d/%d  turns %d\n",
                    res.won ? "WIN" : "LOSS", res.hpEnd, res.maxHp, res.turns);

    } else if (mode == "run") {          // one whole run, verbose
        int sims         = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t sd = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc          = argc > 4 ? std::stoi(argv[4]) : 0;
        RunResult r = runFullRun(sd, sims, asc, false);
        std::printf("=== %s ===  reached floor %d (act %d)  hp %d/%d  %.2fs\n",
                    r.won ? "WIN" : "DEAD", r.floor, r.act, r.hpEnd, r.maxHp, r.sec);

    } else if (mode == "runbench") {     // many whole runs
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 20;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        runBenchmark(sims, nSeeds, asc);

    } else if (mode == "draftbench") {    // weighted table vs lookahead drafting
        int outerSims = argc > 2 ? std::stoi(argv[2]) : 6000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 16;
        int N         = argc > 4 ? std::stoi(argv[4]) : 1;
        int innerSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int asc       = argc > 6 ? std::stoi(argv[6]) : 0;
        draftBench(outerSims, nSeeds, N, innerSims, asc);

    } else if (mode == "datagen") {       // CSV of (state features, run outcome) for offline V(state)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "data.csv";
        search::g_fairPlay = argc > 7 ? std::stoi(argv[7]) != 0 : false;
        if (const char *sf = std::getenv("STS_FAIR")) {              // warn when the positional arg overrides the env
            const bool envFair = std::atoi(sf) != 0;
            if (envFair != search::g_fairPlay)
                std::cerr << "[datagen] warning: positional arg overrides STS_FAIR=" << sf
                          << " -> g_fairPlay=" << (search::g_fairPlay ? 1 : 0) << "\n";
        }
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        dataGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "datagen2") {      // RICH per-decision state (relics/upgrades/potions/future/path) + outcome
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "vrich.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "e2cgen") {        // E2c matched RAW/POST combat-terminal dataset
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 8;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/e2c_raw_terminal.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        e2cGen(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "datagen3") {      // RICH outcomes + paired rest/card counterfactuals
        int nSeeds       = argc > 2  ? std::stoi(argv[2])  : 2000;
        int sims         = argc > 3  ? std::stoi(argv[3])  : 300;
        int asc          = argc > 4  ? std::stoi(argv[4])  : 0;
        double eps       = argc > 5  ? std::stod(argv[5])  : 0.05;
        std::string out  = argc > 6  ? argv[6] : "vrich.csv";
        std::string rout = argc > 7  ? argv[7] : "rest_cf.csv";
        long long seedOff= argc > 8  ? std::stoll(argv[8]) : 0;
        int restSims     = argc > 9  ? std::stoi(argv[9])  : sims;
        int restFutures  = argc > 10 ? std::stoi(argv[10]) : 1;
        int restStride   = argc > 11 ? std::stoi(argv[11]) : 4;
        std::string cardOut = argc > 12 ? argv[12] : "";
        int cardSims     = argc > 13 ? std::stoi(argv[13]) : 0;
        int cardFights   = argc > 14 ? std::stoi(argv[14]) : 3;
        int cardFutures  = argc > 15 ? std::stoi(argv[15]) : 1;
        int cardStride   = argc > 16 ? std::stoi(argv[16]) : 4;
        int cardMax      = argc > 17 ? std::stoi(argv[17]) : 1;
        std::uint64_t cardFutureSalt = argc > 18 ? std::stoull(argv[18]) : 0;
        int cardAdaptiveMax = argc > 19 ? std::stoi(argv[19]) : 0;
        double cardAdaptiveGap = argc > 20 ? std::stod(argv[20]) : 5.0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff, rout,
                 restSims, restFutures, restStride, cardOut,
                 cardSims, cardFights, cardFutures, cardStride, cardMax, cardFutureSalt,
                 cardAdaptiveMax, cardAdaptiveGap);

    } else if (mode == "pathcfgen") {     // one uniformly sampled paired route decision per run
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 100;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "path_cf.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 2;
        std::uint64_t salt= argc > 9 ? std::stoull(argv[9]) : 0;
        pathCounterfactualGen(nSeeds, outerSims, asc, out, off, branchSims, futures, salt);

    } else if (mode == "oocnextgen") {    // all legal OOC actions, labels at next combat
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "ooc_next_combat.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 1;
        oocNextCombatGen(nSeeds, outerSims, asc, out, off, branchSims, futures);

    } else if (mode == "winnettest") {    // validate C++ WinNet (OOC win trees) vs Python predictions
        // Reads a tierb-schema CSV (state block between `chosen` and `won`),
        // runs the native WinNet on the rich state of each row, and prints
        // "rowidx,vwin" so the Python checker can compare tree-walks exactly.
        std::string trees = argc > 2 ? argv[2] : "models/v_win_trees.txt";
        std::string csv   = argc > 3 ? argv[3] : "build/strategic_qwin.csv";
        long long maxRows = argc > 4 ? std::stoll(argv[4]) : 200;
        if (!g_winNet.load(trees, richIdxMap())) { std::cerr << "load failed: " << trees << "\n"; return 1; }
        std::ifstream f(csv);
        std::string line;
        if (!std::getline(f, line)) { std::cerr << "empty csv\n"; return 1; }
        // header: find the state block between `chosen` and `won`
        std::vector<std::string> hdr; std::stringstream hs(line); std::string cell;
        while (std::getline(hs, cell, ',')) hdr.push_back(cell);
        int ci = -1, wi = -1;
        for (int i = 0; i < (int)hdr.size(); ++i) {
            if (hdr[i] == "chosen") ci = i;
            if (hdr[i] == "won") { wi = i; break; }
        }
        if (ci < 0 || wi < 0 || wi - ci <= 1) { std::cerr << "no state block between chosen and won\n"; return 1; }
        const int nState = wi - ci - 1;
        std::vector<float> raw(nState);
        long long n = 0;
        while (std::getline(f, line) && n < maxRows) {
            std::stringstream ss(line); std::string cell;
            int idx = 0;
            for (int i = 0; i < wi; ++i) {
                std::getline(ss, cell, ',');
                if (i > ci) raw[idx++] = std::stof(cell);
            }
            if (idx != nState) { std::cerr << "short row " << n << "\n"; return 1; }
            std::printf("%lld,%.9f\n", n, g_winNet.predict(raw));
            ++n;
        }
        std::printf("WINNET TEST: %lld rows\n", n);

    } else if (mode == "vnettest") {      // ASSERTING C++ CombatValueNet vs Python parity
        // Fails (nonzero exit) on missing/empty/malformed/out-of-tolerance
        // evidence: a successful model load is NOT proof of inference parity.
        // Numeric cells must be complete finite tokens: std::stof/std::stod
        // alone accept trailing junk and NaN/Inf, which would let invalid
        // evidence pass (e.g. a NaN pyPred makes every |diff| NaN and maxAbs
        // stay at 0, so a garbage row would compare as "in tolerance").
        auto parseFiniteDouble = [](const std::string &s, double &out) -> bool {
            if (s.empty()) return false;
            char *end = nullptr;
            out = std::strtod(s.c_str(), &end);
            if (end != s.c_str() + s.size()) return false;   // trailing junk
            return std::isfinite(out);                        // NaN/Inf rejected
        };
        std::string trees = "build/v_combat_trees.txt";
        std::string val   = "build/v_combat_val.csv";
        double tol = 0.001;
        std::string encounterSel;   // optional --encounter <NAME>: test a per-encounter model
        std::vector<std::string> pos;
        for (int i = 2; i < argc; ++i) {
            if (std::string(argv[i]) == "--encounter" && i + 1 < argc) {
                encounterSel = argv[++i];
            } else {
                pos.emplace_back(argv[i]);
            }
        }
        if (!pos.empty()) trees = pos[0];
        if (pos.size() > 1) val = pos[1];
        if (pos.size() > 2) {
            if (!parseFiniteDouble(pos[2], tol) || tol < 0) {
                std::cerr << "bad tolerance '" << pos[2] << "' (must be a finite "
                          << "non-negative number)\n";
                return 1;
            }
        }
        if (!search::g_combatVNet.load(trees)) { std::cerr << "load failed: " << trees << "\n"; return 1; }
        const search::CombatValueNet *net = &search::g_combatVNet;
        if (!encounterSel.empty()) {
            int enc = -1;
            constexpr int kNumEncounters = sizeof(monsterEncounterEnumNames)
                / sizeof(monsterEncounterEnumNames[0]);
            for (int i = 0; i < kNumEncounters; ++i)
                if (encounterSel == monsterEncounterEnumNames[i]) { enc = i; break; }
            if (enc < 0) {
                std::cerr << "unknown encounter '" << encounterSel << "'\n";
                return 1;
            }
            // 1) in-file per-encounter deltas (combat_mlp_meta_v1) populated by
            //    the load() above; 2) else the STS_VNET_PER_ENCOUNTER directory
            //    overlay of per-encounter tree files.
            auto it = search::g_combatVNet.encounterModels.find(enc);
            if (it == search::g_combatVNet.encounterModels.end()) {
                const char *d = std::getenv("STS_VNET_PER_ENCOUNTER");
                if (!d) {
                    std::cerr << "vnettest --encounter " << encounterSel
                              << " requires STS_VNET_PER_ENCOUNTER=<dir> or a "
                                 "combat_mlp_meta_v1 base with an in-file delta "
                                 "for the encounter\n";
                    return 1;
                }
                if (!search::g_combatVNet.loadEncounterModels(d)) {
                    std::cerr << "per-encounter model load failed for dir '" << d << "'\n";
                    return 1;
                }
                it = search::g_combatVNet.encounterModels.find(enc);
                if (it == search::g_combatVNet.encounterModels.end()) {
                    std::cerr << "no per-encounter model for '" << encounterSel
                              << "' in " << d << "\n";
                    return 1;
                }
            }
            net = &it->second;
            std::printf("VNET PER-ENCOUNTER: testing '%s' (%d) with base %s\n",
                        encounterSel.c_str(), enc, trees.c_str());
        }
        std::ifstream vf(val);
        if (!vf) { std::cerr << "cannot open validation csv: " << val << "\n"; return 1; }
        std::string line;
        if (!std::getline(vf, line)) { std::cerr << "empty validation csv: " << val << "\n"; return 1; }
        const auto &names = search::combatFeatureNames();
        const int nf = search::combatFeatureCount();
        {   // header must be exactly the canonical combat features followed by pyPred
            std::stringstream hs(line); std::string cell;
            std::vector<std::string> hdr;
            while (std::getline(hs, cell, ',')) hdr.push_back(cell);
            if ((int)hdr.size() != nf + 1 || hdr[nf] != "pyPred") {
                std::cerr << "bad header: expected " << nf << " canonical combat "
                          << "features followed by pyPred, got " << hdr.size()
                          << " columns\n";
                return 1;
            }
            for (int i = 0; i < nf; ++i) {
                if (hdr[i] != names[i]) {
                    std::cerr << "bad header: column " << i << " is '" << hdr[i]
                              << "', expected '" << names[i] << "'\n";
                    return 1;
                }
            }
        }
        double maxAbs = 0, sumAbs = 0; int n = 0;
        std::vector<float> canon(nf);
        while (std::getline(vf, line)) {
            if (line.empty()) { std::cerr << "empty row at line " << (n + 2) << "\n"; return 1; }
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < nf; ++i) {
                if (!std::getline(ss, cell, ',')) {
                    std::cerr << "row " << (n + 2) << " too short (missing feature "
                              << i << ")\n";
                    return 1;
                }
                double featVal = 0;
                if (!parseFiniteDouble(cell, featVal)) {
                    std::cerr << "row " << (n + 2) << " malformed feature '" << cell
                              << "' (must be a complete finite number)\n";
                    return 1;
                }
                canon[i] = (float)featVal;
                if (!std::isfinite(canon[i])) {   // finite double can overflow float
                    std::cerr << "row " << (n + 2) << " feature '" << cell
                              << "' overflows the native float feature vector\n";
                    return 1;
                }
            }
            double pyPred = 0;
            if (!std::getline(ss, cell, ',')) {
                std::cerr << "row " << (n + 2) << " missing pyPred\n";
                return 1;
            }
            if (!parseFiniteDouble(cell, pyPred)) {
                std::cerr << "row " << (n + 2) << " malformed pyPred '" << cell
                          << "' (must be a complete finite number)\n";
                return 1;
            }
            std::string extra;
            if (std::getline(ss, extra, ',')) {
                std::cerr << "row " << (n + 2) << " has extra columns after pyPred\n";
                return 1;
            }
            double cpp = net->predictVec(canon.data());
            if (!std::isfinite(cpp)) {   // malformed native model can yield NaN/Inf
                std::cerr << "row " << (n + 2) << " native prediction is non-finite ("
                          << cpp << ") — malformed model or inference\n";
                return 1;
            }
            double d = std::fabs(cpp - pyPred);
            if (!std::isfinite(d)) {     // e.g. finite cpp minus Inf pyPred (unreachable, defensive)
                std::cerr << "row " << (n + 2) << " non-finite prediction difference "
                          << "(cpp=" << cpp << " pyPred=" << pyPred << ")\n";
                return 1;
            }
            maxAbs = std::max(maxAbs, d); sumAbs += d; ++n;
            if (n <= 5) std::printf("  row %d: cpp=%.4f py=%.4f diff=%.6f\n", n, cpp, pyPred, d);
        }
        if (n == 0) { std::cerr << "no validation rows in " << val << "\n"; return 1; }
        std::printf("VNET VALIDATION: %d rows, max|diff|=%.6f  mean|diff|=%.6f  tolerance=%.4g\n",
                    n, maxAbs, sumAbs/n, tol);
        if (maxAbs > tol) {
            std::printf("FAIL: max|diff| %.6f exceeds tolerance %.4g\n", maxAbs, tol);
            return 1;
        }
        std::printf("PASS (C++ matches Python within %.4g)\n", tol);

    } else if (mode == "policynettest") { // validate entity policy logits vs Python
        std::string model = argc > 2 ? argv[2] : "build/policy_entity.txt";
        std::string val   = argc > 3 ? argv[3] : "build/policy_entity_val.csv";
        search::g_policyNet.isPolicy = true;
        if (!search::g_policyNet.load(model)) { std::cerr << "load failed: " << model << "\n"; return 1; }
        std::ifstream vf(val);
        std::string line; std::getline(vf, line);
        const int nf = search::combatPolicyFeatureCount();
        double maxAbs = 0, sumAbs = 0; int n = 0;
        std::vector<float> canon(nf);
        while (std::getline(vf, line)) {
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < nf; ++i) { std::getline(ss, cell, ','); canon[i] = std::stof(cell); }
            double pyPred = 0;
            while (std::getline(ss, cell, ',')) pyPred = std::stod(cell);
            double cpp = search::g_policyNet.predictVec(canon.data());
            double d = std::fabs(cpp - pyPred); maxAbs = std::max(maxAbs, d); sumAbs += d; ++n;
            if (n <= 5) std::printf("  row %d: cpp=%.5f py=%.5f diff=%.7f\n", n, cpp, pyPred, d);
        }
        std::printf("POLICY NET VALIDATION: %d rows, max|diff|=%.7f  mean|diff|=%.7f\n",
                    n, maxAbs, sumAbs/std::max(1, n));
        std::printf("%s\n", maxAbs < 1e-3 ? "PASS (C++ matches Python)" : "FAIL");

    } else if (mode == "pvnetparity") {   // validate C++ CombatPVNet vs Python predictions
        // Parity CSV layout per row: 1766 state feats, 14 action feats,
        // then Python outputs: global(ED), pol(1), win(1), death(1),
        // quantile(NQ), potion(44), turns(1).
        std::string model = argc > 2 ? argv[2] : "models/v_combat_pvnet.txt";
        std::string val   = argc > 3 ? argv[3] : "build/pvnet_parity.csv";
        if (!search::g_combatPVNet.load(model)) { std::cerr << "load failed: " << model << "\n"; return 1; }
        const auto &pv = search::g_combatPVNet;
        std::ifstream vf(val);
        std::string line; std::getline(vf, line);                 // header
        const int D = pv.entityDim, NQ = pv.nQuantile;
        double maxG=0,sumG=0, maxPol=0,sumPol=0, maxVal=0,sumVal=0; int n=0;
        std::array<float,1766> feat{};
        std::array<float,14> act{};
        thread_local std::vector<float> g; g.resize(D);
        std::array<float,11> qs{}; std::array<float,44> pots{}; float turns=0;
        while (std::getline(vf, line)) {
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < 1766; ++i) { std::getline(ss, cell, ','); feat[i] = std::stof(cell); }
            for (int i = 0; i < 14; ++i)   { std::getline(ss, cell, ','); act[i]  = std::stof(cell); }
            std::vector<float> pyG(D);
            for (int i = 0; i < D; ++i) { std::getline(ss, cell, ','); pyG[i] = std::stof(cell); }
            double pyPol=0,pyWin=0,pyDeath=0; std::array<double,11> pyQ{}; std::array<double,44> pyPot{}; double pyTurns=0;
            std::getline(ss, cell, ','); pyPol = std::stod(cell);
            std::getline(ss, cell, ','); pyWin = std::stod(cell);
            std::getline(ss, cell, ','); pyDeath = std::stod(cell);
            for (int i = 0; i < NQ; ++i) { std::getline(ss, cell, ','); pyQ[i] = std::stod(cell); }
            for (int i = 0; i < 44; ++i) { std::getline(ss, cell, ','); pyPot[i] = std::stod(cell); }
            std::getline(ss, cell, ','); pyTurns = std::stod(cell);
            if (!ss) break;
            pv.encode(feat, g.data());
            double pol = pv.policyScore(g.data(), act.data());
            float wp=0,dp=0; qs.fill(0); pots.fill(0); turns=0;
            pv.predictValue(g.data(), wp, dp, &qs, &pots, &turns);
            for (int i = 0; i < D; ++i) { double d = std::fabs((double)g[i] - pyG[i]); maxG = std::max(maxG, d); sumG += d; }
            double dv = std::fabs(pol - pyPol); maxPol = std::max(maxPol, dv); sumPol += dv;
            double dmaxVal=0;
            { double d = std::fabs((double)wp - pyWin); dmaxVal = std::max(dmaxVal, d); }
            { double d = std::fabs((double)dp - pyDeath); dmaxVal = std::max(dmaxVal, d); }
            for (int i = 0; i < NQ; ++i) { double d = std::fabs((double)qs[i] - pyQ[i]); dmaxVal = std::max(dmaxVal, d); }
            for (int i = 0; i < 44; ++i) { double d = std::fabs((double)pots[i] - pyPot[i]); dmaxVal = std::max(dmaxVal, d); }
            { double d = std::fabs((double)turns - pyTurns); dmaxVal = std::max(dmaxVal, d); }
            maxVal = std::max(maxVal, dmaxVal); sumVal += dmaxVal;
            if (n <= 5) std::printf("  row %d: global_max=%.6f pol=%.6f val=%.6f\n", n+1,
                                    maxG, dv, dmaxVal);
            ++n;
        }
        std::printf("PVNET VALIDATION: %d rows, global max=%.6f mean=%.6f | pol max=%.6f mean=%.6f | value max=%.6f mean=%.6f\n",
                    n, maxG, sumG/std::max(1,n*D), maxPol, sumPol/std::max(1,n), maxVal, sumVal/std::max(1,n));
        std::printf("%s\n", maxG < 0.05 && maxPol < 0.05 && maxVal < 0.05 ? "PASS (C++ matches Python)" : "FAIL");

    } else if (mode == "policystats") {  // offline prior quality of the GBM policy net on fairgen policy CSVs
        // Mirrors eval_combat_pvnet.py's policy section for the GBM prior:
        // per decision group, softmax over edge logits vs teacher visit/total.
        // Optional 4th arg "val" restricts to seeds with seed%100<20.
        std::string model = argc > 2 ? argv[2] : "models/policy_trees_c.txt";
        std::string val   = argc > 3 ? argv[3] : "build/fair_p.csv";
        const bool valOnly = argc > 4 && std::string(argv[4]) == "val";
        search::g_policyNet.isPolicy = true;
        if (!search::g_policyNet.load(model)) { std::cerr << "load failed: " << model << "\n"; return 1; }
        std::ifstream vf(val);
        std::string line; std::getline(vf, line);                 // header
        // Locate meta columns by name; the 1780 model features are all others
        // in file order (meta lives at the START of fairgen policy CSVs).
        std::vector<std::string> hdr;
        { std::stringstream hs(line); std::string c; while (std::getline(hs, c, ',')) hdr.push_back(c); }
        const int ncol = (int)hdr.size();
        auto idxOf=[&](const std::string&n){ for(int i=0;i<ncol;++i) if(hdr[i]==n) return i; return -1; };
        const int iSeed=idxOf("seed"), iFid=idxOf("fightIdx"), iDid=idxOf("decIdx"),
                  iVis=idxOf("visit"), iTot=idxOf("total");
        if (iSeed<0||iFid<0||iDid<0||iVis<0||iTot<0){ std::cerr << "missing meta column\n"; return 1; }
        const int stateN = search::combatFeatureCount();
        // Action-block width is header-driven (14 pre-§3.5, 22 since) so old
        // and new fairgen CSVs both analyze; predictVec reads the model's own
        // name-mapped features from the state block regardless of width.
        const int actionN = ncol - stateN - 5;   // 5 meta cols (seed..total)
        // Optional PVNet comparison: load the shared PVNet and report per-group
        // prior entropy for both models plus argmax agreement (4th arg "val",
        // 5th arg PVNet model path).
        const bool havePV = argc > 5;
        search::CombatPVNet pv;
        if (havePV && !pv.load(argv[5])) { std::cerr << "pv load failed: " << argv[5] << "\n"; return 1; }
        double sumCE=0, sumKL=0, sumRegret=0, sumEntropy=0; long long top1=0, top3=0, nGroups=0, nActions=0;
        double sumModelEnt=0, sumPvEnt=0, agree=0;
        std::vector<float> feat(search::combatPolicyFeatureCount());
        std::vector<double> logits, target;
        std::vector<std::vector<float>> grpActs;
        std::array<float,1766> grpState{};
        std::vector<std::string> cells(ncol);
        int stateRow=0; bool inGroup=false; long long curSeed=0; int curFid=0,curDid=0;
        auto flushGroup=[&](){
            if(!inGroup)return;
            const int m=(int)logits.size();
            double mx=*std::max_element(logits.begin(),logits.end());
            double sum=0; for(double&l:logits){l=std::exp(l-mx);sum+=l;}
            double inv=sum>0?1.0/sum:1.0/m;
            double ce=0,kl=0,ent=0,ment=0;
            std::vector<double> gbmP(m);
            for(int i=0;i<m;++i){
                const double p=logits[i]*inv, t=target[i]+1e-9;
                gbmP[i]=p;
                ce+= -t*std::log(p);
                kl+= t*std::log(t/p);
                ent+= -t*std::log(t);
                ment+= -p*std::log(p);
            }
            int best=0; for(int i=1;i<m;++i) if(logits[i]>logits[best]) best=i;
            int tbest=0; for(int i=1;i<m;++i) if(target[i]>target[tbest]) tbest=i;
            top1 += best==tbest;
            if (m>=3) {
                int b1=0,b2=1,b3=2;
                if (logits[b2]>logits[b1]) std::swap(b1,b2);
                if (logits[b3]>logits[b1]) std::swap(b1,b3);
                if (logits[b3]>logits[b2]) std::swap(b2,b3);
                top3 += (tbest==b1||tbest==b2||tbest==b3);
            } else if (m==2) {
                top3 += (tbest==best);
            } else { top3 += 1; }
            sumCE+=ce; sumKL+=kl; sumRegret+=1.0-target[best]; sumEntropy+=ent;
            sumModelEnt += ment;
            if (havePV) {
                thread_local std::vector<float> pvg(pv.entityDim);
                pv.encode(grpState, pvg.data());
                double pvSum=0; int pvBest=0;
                std::vector<double> pvP(m);
                for (int i=0;i<m;++i) {
                    const double l = pv.policyScore(pvg.data(), grpActs[i].data());
                    pvP[i] = l;
                    if (l>pvP[pvBest]) pvBest=i;
                }
                double pmx=pvP[pvBest];
                for (int i=0;i<m;++i) pvP[i]=std::exp(pvP[i]-pmx);
                double psum=0; for (int i=0;i<m;++i) psum+=pvP[i];
                double pinv=psum>0?1.0/psum:1.0/m;
                double pvent=0;
                for (int i=0;i<m;++i){ pvP[i]*=pinv; pvent+= -pvP[i]*std::log(pvP[i]); }
                sumPvEnt += pvent;
                agree += pvBest==best;
            }
            ++nGroups; nActions+=m;
            logits.clear(); target.clear(); grpActs.clear(); inGroup=false;
        };
        while (std::getline(vf, line)) {
            if (line.empty()) continue;
            std::stringstream ss(line); std::string cell;
            for (int i = 0; i < ncol; ++i) { std::getline(ss, cell, ','); cells[i] = cell; }
            const long long seed = std::stoll(cells[iSeed]);
            const int fid = std::stoi(cells[iFid]);
            const int did = std::stoi(cells[iDid]);
            const int vis = std::stoi(cells[iVis]);
            const int tot = std::stoi(cells[iTot]);
            if (tot<=0) continue;
            // contiguity: fairgen writes one decision's edges together
            if (inGroup && (seed!=curSeed || fid!=curFid || did!=curDid)) flushGroup();
            if (valOnly && seed%100>=20) { inGroup=false; continue; }
            curSeed=seed; curFid=fid; curDid=did;
            int fi=0; std::vector<float> act(actionN);
            for (int i = 0; i < ncol; ++i) {
                if (i==iSeed||i==iFid||i==iDid||i==iVis||i==iTot) continue;
                const float v = std::stof(cells[i]);
                if (fi < stateN) feat[fi] = v;
                else if (fi - stateN < actionN) {
                    // action block goes into feat (GBM predictVec path) AND
                    // into act (optional PVNet comparison). Pre-§3.5 this was
                    // only stored in act, so the GBM policy metrics evaluated
                    // zeroed action features (uniform softmax per group).
                    feat[stateN + (fi - stateN)] = v;
                    act[fi - stateN] = v;
                }
                ++fi;
            }
            if (fi != stateN + actionN) { std::cerr << "feature count mismatch: " << fi << "\n"; return 1; }
            if (!inGroup) for (int i=0;i<stateN;++i) grpState[i]=feat[i];
            grpActs.push_back(act);
            logits.push_back(search::g_policyNet.predictVec(feat.data()));
            target.push_back((double)vis/(double)tot);
            inGroup=true;
            if (++stateRow % 100000 == 0) std::printf("  %d rows\n", stateRow);
        }
        flushGroup();
        std::printf("POLICY STATS: %lld groups, %lld actions | top1 %.4f | CE %.4f | KL %.4f | regret %.4f | teacherEntropy %.4f | gbmEntropy %.4f",
                    nGroups, nActions, (double)top1/std::max(1LL,nGroups), sumCE/std::max(1.0,(double)nGroups),
                    sumKL/std::max(1.0,(double)nGroups), sumRegret/std::max(1.0,(double)nGroups),
                    sumEntropy/std::max(1.0,(double)nGroups), sumModelEnt/std::max(1.0,(double)nGroups));
        if (havePV)
            std::printf(" | pvEntropy %.4f | argmaxAgreement %.4f\n",
                        sumPvEnt/std::max(1.0,(double)nGroups), agree/std::max(1.0,(double)nGroups));
        else std::printf("\n");

    } else if (mode == "speedtest") {     // single-fight Searcher3 speed measurement
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t seed = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        // Init a fight directly with a known encounter
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
        std::printf("speedtest: %s  hp=%d/%d  hand=%d  draw=%zu\n",
                    monsterEncounterStrings[(int)bc.encounter], bc.player.curHp,
                    bc.player.maxHp, bc.cards.cardsInHand, bc.cards.drawPile.size());
        for (int s : {100, 500, 1000, 2500}) {
            search::BattleScumSearcher3 s3(bc, 64);
            auto t0 = std::chrono::steady_clock::now();
            s3.search(s);
            auto t1 = std::chrono::steady_clock::now();
            double sec = std::chrono::duration<double>(t1 - t0).count();
        std::printf("  S3 %5d sims: %6.3fs  %6d sim/s  rootVisits=%lld\n",
                    s, sec, int(s/sec),
                    (long long)s3.root.simulationCount);
        }

    } else if (mode == "searchdiag") {    // Searcher2 rollout-usage diagnostics
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 8;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/searchdiag.csv";
        int probeEvery = argc > 6 ? std::stoi(argv[6]) : 1;
        std::uint64_t seedOff = argc > 7 ? std::stoull(argv[7]) : 0;
        searchDiag(nSeeds, sims, asc, out, probeEvery, seedOff);

    } else if (mode == "combatgen") {     // CSV of (combat state, fight outcome) for V_combat
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vcombat.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        combatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "distgen") {       // combatgen + rich distributional labels (endTurn, potion use)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vdist.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        distCombatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "fairgen") {       // Searcher3 ISMCTS: value + policy rows with visit distributions
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/fair_val.csv";
        std::string pout = argc > 7 ? argv[7] : "build/fair_pol.csv";
        std::string oout = argc > 8 ? argv[8] : "build/fair_ooc.csv";
        long long seedOff = argc > 9 ? std::stoll(argv[9]) : 0;
        // fairgen emits Searcher3 policy rows via g_onSearchComplete3; force the
        // project-fair Searcher3 regime here so callers cannot silently produce
        // data under the wrong producer (STS_FAIR=1 STS_SEARCHER3=1 no longer
        // required; the env vars still mean the same thing for other modes).
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[fairgen forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        fairGen(nSeeds, sims, asc, eps, vout, pout, oout, seedOff);

    } else if (mode == "leafdiag") {      // Searcher3 leaf-state diagnostic dataset (handover 2026-08-08)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/leafdiag.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        // Same forced regime as fairgen: the dataset must come from the deployed
        // fair-Searcher3 search (leaf states only exist there).
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[leafdiag forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        leafDiag(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "runwinshadow") {  // E2c RAW critic: strictly read-only shadow producer
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/runwinshadow.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        if (!g_runwinShadowNet.ok) {
            std::cerr << "runwinshadow requires STS_RUNWIN_SHADOW_MODEL=<native E2c model>\n";
            return 2;
        }
        std::cout << "[runwinshadow forced: fair-play / Searcher3; critic is diagnostic-only, R="
                  << g_runwinShadowR << "]\n";
        runwinShadow(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "runwinrank") {  // E3a direct eventual-run leaf-ranking diagnostic
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/e3a_runwin_shadow.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        if (!g_runwinShadowNet.ok) {
            std::cerr << "runwinrank requires STS_RUNWIN_SHADOW_MODEL=<native E2c model>\n";
            return 2;
        }
        if (g_runwinRankMinLeaves > g_runwinRankMaxLeaves) {
            std::cerr << "runwinrank requires STS_RUNWIN_RANK_MIN_LEAVES <= STS_RUNWIN_RANK_MAX_LEAVES\n";
            return 2;
        }
        std::cout << "[runwinrank forced: fair-play / Searcher3; detached E3a reference only, R="
                  << g_runwinShadowR << " M=" << g_runwinRankReferenceFutures << "]\n";
        runwinRank(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "runwinparity") {
        const std::string fixture = argc > 2 ? argv[2] : "tools/runwin_e2c_synthetic_parity.csv";
        return runwinParity(fixture);

    } else if (mode == "e2cprojectiontest") {
        return e2cRawProjectionParityTest();

    } else if (mode == "particle_leaf_probe") {
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/particle_leaf_probe.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        if (g_particleLeafProbeFile.empty()) g_particleLeafProbeFile = out;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[particle_leaf_probe forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        particleLeafProbe(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "particle_posterior_probe") {   // Phase-1b posterior-valid probe
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/particle_posterior_probe.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        if (g_particlePosteriorProbeFile.empty()) g_particlePosteriorProbeFile = out;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[particle_posterior_probe forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        particlePosteriorProbe(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "leafref") {       // high-budget reference values for recorded leafdiag leaves
        if (argc < 5) {
            std::cerr << "usage: one_combat leafref INFILE OUTFILE HIGH_BUDGET_SIMS NSEEDSREF ASC [REPLAY_SIMS]\n"
                         "  REPLAY_SIMS (default 300) must match the sims of the leafdiag run.\n"
                         "  The whole replay config must match the leafdiag run so the identical\n"
                         "  leaf states regenerate: SAME STS_S3_PARTICLES, STS_VNET+alpha,\n"
                         "  OOC env arms, and ascension. Any mismatch shows as a re-capture\n"
                         "  WARNING (re-captured < recorded leaves).\n";
            return 2;
        }
        {
            std::string inFile   = argv[2];
            std::string outFile  = argv[3];
            int highBudgetSims   = std::stoi(argv[4]);
            int nSeedsRef        = argc > 5 ? std::stoi(argv[5]) : 4;
            int asc              = argc > 6 ? std::stoi(argv[6]) : 0;
            int replaySims       = argc > 7 ? std::stoi(argv[7]) : 300;
            search::g_fairPlay = true;
            search::g_useSearcher3 = true;
            std::cout << "[leafref forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
            leafRef(inFile, outFile, highBudgetSims, nSeedsRef, asc, replaySims);
        }

    } else if (mode == "rollouttrace") {   // actual-rollout state sequences for delta-V smoothness (Task 6)
        if (argc < 4) {
            std::cerr << "usage: one_combat rollouttrace INFILE OUTFILE NSEEDSREF ASC [REPLAY_SIMS]\n"
                         "  REPLAY_SIMS (default 300) must match the sims of the leafdiag run.\n"
                         "  The whole replay config must match the leafdiag run so the identical\n"
                         "  leaf states regenerate: SAME STS_S3_PARTICLES, STS_VNET+alpha,\n"
                         "  OOC env arms, and ascension. Any mismatch shows as a re-capture\n"
                         "  WARNING (re-captured < recorded leaves).\n";
            return 2;
        }
        {
            std::string inFile  = argv[2];
            std::string outFile = argv[3];
            int nSeedsRef       = argc > 4 ? std::stoi(argv[4]) : 4;
            int asc             = argc > 5 ? std::stoi(argv[5]) : 0;
            int replaySims      = argc > 6 ? std::stoi(argv[6]) : 300;
            search::g_fairPlay = true;
            search::g_useSearcher3 = true;
            std::cout << "[rollouttrace forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
            rolloutTrace(inFile, outFile, nSeedsRef, asc, replaySims);
        }

    } else if (mode == "frontiergen") {  // S3 frontier-leaf corpus with restorable snapshots (phases 2-3)
        if (argc < 6) {
            std::cerr << "usage: one_combat frontiergen NSEEDS SIMS ASC OUTFILE_CSV [SEEDOFFSET] [STAMP]\n"
                         "  Writes OUTFILE_CSV[_STAMP].csv + OUTFILE_CSV[_STAMP].bin (binary leaf +\n"
                         "  parent-state snapshots, 4-byte little-endian len + serializeBattleContext blob).\n"
                         "  Forces the deployed fair-S3 datagen regime: STS_FAIR=1 STS_SEARCHER3=1\n"
                         "  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1.\n";
            return 2;
        }
        {
            int nSeeds = std::stoi(argv[2]);
            int sims   = std::stoi(argv[3]);
            int asc    = std::stoi(argv[4]);
            std::string out = argv[5];
            long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
            std::string stamp = argc > 7 ? argv[7] : "";
            search::g_fairPlay = true;
            search::g_useSearcher3 = true;
            search::g_s3Belief = false;
            search::g_s3Chain = false;
            search::g_liveValid = true;
            std::cout << "[frontiergen forced: fair-play / determinized MCTS + Searcher3 engine ON, "
                         "STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1 (deployed fair-S3 datagen regime)]\n";
            frontierGen(nSeeds, sims, asc, out, seedOff, stamp);
        }

    } else if (mode == "leafrelabel") {  // empirical terminal-outcome labels for recorded frontier leaves (phase 3)
        if (argc < 8) {
            std::cerr << "usage: one_combat leafrelabel INFILE_CSV INFILE_BIN OUTFILE_LEAF OUTFILE_SIBLING "
                         "HIGH_BUDGET_SIMS NLEAVES [PARTICLES] [SUBSAMPLE_BUDGET]\n"
                         "  INFILE_CSV/INFILE_BIN are frontiergen outputs (same stamp).\n"
                         "  PARTICLES defaults to 16; SUBSAMPLE_BUDGET (default 3000) is the sibling\n"
                         "  evaluation budget (3-5k sims). Forces the same fair-S3 regime as frontiergen.\n";
            return 2;
        }
        {
            std::string inCsv = argv[2];
            std::string inBin = argv[3];
            std::string leafOut = argv[4];
            std::string siblingOut = argv[5];
            int highBudgetSims = std::stoi(argv[6]);
            int nLeaves = std::stoi(argv[7]);
            int particles = argc > 8 ? std::stoi(argv[8]) : 16;
            int siblingBudget = argc > 9 ? std::stoi(argv[9]) : 3000;
            search::g_fairPlay = true;
            search::g_useSearcher3 = true;
            search::g_s3Belief = false;
            search::g_s3Chain = false;
            search::g_liveValid = true;
            std::cout << "[leafrelabel forced: fair-play / determinized MCTS + Searcher3 engine ON, "
                         "STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1]\n";
            leafRelabel(inCsv, inBin, leafOut, siblingOut, highBudgetSims, nLeaves,
                        particles, siblingBudget);
        }

    } else if (mode == "s3siblingcrn") {
        if (argc < 11) {
            std::cerr << "usage: one_combat s3siblingcrn IN_CSV IN_BIN OUT_CSV K_LIST "
                         "REPLICATES MAX_STATES DIAGNOSTIC_SEED BASELINE_SHA DIAGNOSTIC_SHA [MANIFEST]\n";
            return 2;
        }
        std::vector<int> budgets;
        std::stringstream ks(argv[5]); std::string tok;
        while (std::getline(ks, tok, ',')) if (!tok.empty()) budgets.push_back(std::stoi(tok));
        if (budgets.empty() || std::any_of(budgets.begin(), budgets.end(),
                                           [](int k) { return k <= 0; })) return 2;
        search::g_s3Crn = false;
        return s3SiblingCrnDiagnostic(argv[2], argv[3], argv[4], budgets,
                                      std::stoi(argv[6]), std::stoi(argv[7]),
                                      std::stoull(argv[8]), argv[9], argv[10],
                                      argc > 11 ? argv[11] : "") ? 0 : 1;

    } else if (mode == "fightrep") {  // isolated replay of captured Act-3 boss fights (fight-start snapshots)
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
        {
            std::string captureDir = argv[2];
            std::string outCsv = argv[3];
            std::vector<int> particles, sims;
            auto parseList = [](const std::string &s) {
                std::vector<int> v;
                std::stringstream ss(s);
                std::string tok;
                while (std::getline(ss, tok, ','))
                    if (!tok.empty()) v.push_back(std::stoi(tok));
                return v;
            };
            particles = parseList(argv[4]);
            sims = parseList(argv[5]);
            if (particles.empty() || sims.empty()) {
                std::cerr << "fightrep: PARTICLES and SIMS must be non-empty comma lists\n";
                return 2;
            }
            int nFights = argc > 6 ? std::stoi(argv[6]) : 1 << 30;
            fightRepReplay(captureDir, outCsv, particles, sims, nFights);
        }

    } else if (mode == "strategicgen") {  // Phase 5: one row per OOC decision, full rich state
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/strategic.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        strategicGen(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "strategicgen2") {   // Tier-B: strategicgen rows + per-action one-ply labels
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 200;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/strategic_tierb.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        strategicGen2(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "phase13a_collect") {
        if (argc < 5 || !g_oocStrategicTokNet.ok) {
            std::cerr << "usage: one_combat phase13a_collect N_SEEDS SEED_OFFSET OUT.csv [sims] [asc]\n"
                      << "requires STS_OOC_STRATEGIC_TOK_NN=<V4> and STS_PHASE13A_M0_NN=<M0>\n";
            return 2;
        }
        const char *m0 = std::getenv("STS_PHASE13A_M0_NN");
        if (!m0 || !g_phase13aM0Net.load(m0)) {
            std::cerr << "phase13a_collect: failed to load STS_PHASE13A_M0_NN\n";
            return 1;
        }
        phase13aCollect(std::stoi(argv[2]), std::stoull(argv[3]), argv[4],
                        argc > 5 ? std::stoi(argv[5]) : 1000,
                        argc > 6 ? std::stoi(argv[6]) : 0);

    } else if (mode == "phase13a_eval") {
        if (argc < 4 || !g_oocStrategicTokNet.ok) {
            std::cerr << "usage: one_combat phase13a_eval MANIFEST.csv OUT.csv [asc]\n"
                      << "requires STS_OOC_STRATEGIC_TOK_NN=<V4> and STS_PHASE13A_M0_NN=<M0>\n";
            return 2;
        }
        const char *m0 = std::getenv("STS_PHASE13A_M0_NN");
        if (!m0 || !g_phase13aM0Net.load(m0)) {
            std::cerr << "phase13a_eval: failed to load STS_PHASE13A_M0_NN\n";
            return 1;
        }
        phase13aEvaluate(argv[2], argv[3], argc > 4 ? std::stoi(argv[4]) : 0,
                         argc > 5 ? std::stoi(argv[5]) : 1000,
                         argc > 6 ? std::stoi(argv[6]) : 4);

    } else if (mode == "phase13a_ref_eval") {
        if (argc < 4 || !g_oocStrategicTokNet.ok) {
            std::cerr << "usage: one_combat phase13a_ref_eval MANIFEST.csv OUT.csv [asc] [start] [count]\n"
                      << "requires STS_OOC_STRATEGIC_TOK_NN=<V4> and STS_PHASE13A_M0_NN=<M0>\n";
            return 2;
        }
        const char *m0 = std::getenv("STS_PHASE13A_M0_NN");
        if (!m0 || !g_phase13aM0Net.load(m0)) {
            std::cerr << "phase13a_ref_eval: failed to load STS_PHASE13A_M0_NN\n";
            return 1;
        }
        phase13aEvaluate(argv[2], argv[3], argc > 4 ? std::stoi(argv[4]) : 0,
                         1000, argc > 6 ? std::stoi(argv[6]) : 4,
                         argc > 5 ? std::stoi(argv[5]) : 4, true);

    } else if (mode == "policygen") {     // CSV of (state, action, visit/total) MCTS policy targets (AZ-lite)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 10000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vpolicy.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        policyGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "mapbatch") {      // companion full-map graph table for rich/meta/card CSVs
        if (argc < 4) {
            std::cerr << "usage: one_combat mapbatch SOURCE.csv MAPS.csv\n";
            return 2;
        }
        exportCardCfMaps(argv[2], argv[3]);

    } else if (mode == "dumpmap") {       // dump a seed's map GRAPH (nodes+edges) for the future GNN
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int asc = argc > 3 ? std::stoi(argv[3]) : 0;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        const Map &map = *gc.map;
        std::printf("# seed %llu act %d  format: y x room edge_x...\n", (unsigned long long)seed, gc.act);
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::NONE || n.room == Room::INVALID) continue;
            std::printf("%d %d %d", y, x, (int)n.room);
            for (int i = 0; i < n.edgeCount; ++i) std::printf(" %d", n.edges[i]);
            std::printf("\n");
        }

    } else if (mode == "mapnntest") {    // deterministic C++-vs-Python parity for the V6 map-DAG path
        // Fixed synthetic inputs; the Python side (export_strategic.py) computes
        // the same Q from the same checkpoint — the printed numbers must match.
        if (!g_oocStrategicNet.ok || !g_oocStrategicNet.mapEnc) { std::cerr << "mapnntest: need a loaded V6 net (STS_OOC_STRATEGIC_NN)\n"; return 1; }
        std::vector<float> state(OocStrategicNet::NSTATE);
        for (int i = 0; i < OocStrategicNet::NSTATE; ++i) state[i] = (float)((i % 7) * 0.5);
        int rooms[105], edges[105], special[105];
        for (int i = 0; i < 105; ++i) {
            const int y = i / 7, x = i % 7;
            rooms[i] = i % 10;
            int em = 0;
            if (y < 14) for (int cx = 0; cx < 7; ++cx) if (((x * 3 + y) % 7) == cx) em |= 1 << cx;
            edges[i] = em;
            special[i] = (i == 5) ? 1 : 0;
        }
        const int cats[6] = {1, 2, 3, 4, 5, 6};
        const int px = 2, py = 3;
        for (int cx = 0; cx < 7; ++cx)
            std::printf("mapnntest q[child=%d] = %.10f\n", cx,
                        (double)g_oocStrategicNet.predictMapActionValue(
                            state.data(), 0x1234u, cats, 2, (int)ScreenState::MAP_SCREEN,
                            rooms, edges, special, px, py, cx));
        std::printf("mapnntest q[roots pool, no singleton] = %.10f\n",
                    (double)g_oocStrategicNet.predictMapActionValue(
                        state.data(), 0x1234u, cats, 2, (int)ScreenState::MAP_SCREEN,
                        rooms, edges, special, px, -1, -1));

    } else if (mode == "fightgen") {      // ONE pass -> BOTH value (endHp) + policy (visit-pi) CSVs
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/vcombat.csv";
        std::string pout = argc > 7 ? argv[7] : "build/vpolicy.csv";
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        fightGen(nSeeds, sims, asc, eps, vout, pout, seedOff);

    } else if (mode == "causalgen") {     // CSV of (state, card features, CRN advantage) for causal card value
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 200;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int N         = argc > 4 ? std::stoi(argv[4]) : 6;
        int innerSims = argc > 5 ? std::stoi(argv[5]) : 800;
        int K         = argc > 6 ? std::stoi(argv[6]) : 6;
        double eps    = argc > 7 ? std::stod(argv[7]) : 0.30;
        std::string out = argc > 8 ? argv[8] : "causal.csv";
        causalGen(nSeeds, sims, /*asc=*/0, N, innerSims, K, eps, out);

    } else if (mode == "carddump") {      // id,name,type,rarity,obtainWeight,baseDamage for all card ids
        std::cout << "id,name,type,rarity,obtainWeight,baseDamage\n";
        for (int i = 0; i < kNumCardIds; ++i) {
            Card c((CardId)i);
            std::cout << i << ',' << c.getName() << ',' << (int)c.getType() << ','
                      << (int)c.getRarity() << ',' << search::Expert::getObtainWeight((CardId)i)
                      << ',' << c.getBaseDamage() << '\n';
        }

    } else if (mode == "deck") {          // dump final deck+relics of one run (eval+path)
        std::uint64_t sd = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims         = argc > 3 ? std::stoi(argv[3]) : 4000;
        int asc          = argc > 4 ? std::stoi(argv[4]) : 0;
        dumpRun(sd, sims, asc);

    } else if (mode == "cardbench") {     // weighted table vs greedy argmax drafting
        int sims      = argc > 2 ? std::stoi(argv[2]) : 4000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 64;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double skipR  = argc > 5 ? std::stod(argv[5]) : 1.0;
        search::g_fairPlay = argc > 6 ? std::stoi(argv[6]) != 0 : false;
        int onlyPolicy = argc > 7 ? std::stoi(argv[7]) : -1;  // -1=all, else 0..5
        g_learnedNeverSkip = argc > 8 ? std::stoi(argv[8]) != 0 : false;
        g_tableAlpha = argc > 9 ? std::stod(argv[9]) : 1.0;   // eval+causal fusion weight
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS]\n";
        cardBench(sims, nSeeds, asc, skipR, onlyPolicy);

    } else if (mode == "combobench") {    // baseline vs (greedy draft + heuristic path)
        int sims      = argc > 2 ? std::stoi(argv[2]) : 4000;
        int nSeeds    = argc > 3 ? std::stoi(argv[3]) : 128;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double skipR  = argc > 5 ? std::stod(argv[5]) : 0.0;
        search::g_fairPlay = argc > 6 ? std::stoi(argv[6]) != 0 : false;
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS]\n";
        comboBench(sims, nSeeds, asc, skipR);

    } else if (mode == "pathbench") {     // random path vs heuristic path
        int sims   = argc > 2 ? std::stoi(argv[2]) : 8000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 32;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        pathBench(sims, nSeeds, asc);

    } else if (mode == "bestbench") {     // current best OOC stack, single arm (baseline for new experiments)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seedOffset = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        // issue 46 hardening: bestBench APPENDS to the results file and never
        // deduplicates ("caller owns truncation"). A stale file that already
        // contains rows for the requested seed block silently doubles every
        // seed, which the strict paired analyzer then rejects. Fail loudly
        // here instead of corrupting the CSV. Self-play batches use disjoint
        // offsets on fresh per-iteration files, so this never fires there.
        if (!resultsFile.empty()) {
            const std::uint64_t lo = seedOffset, hi = seedOffset + (std::uint64_t)nSeeds - 1;
            std::ifstream stale(resultsFile);
            if (stale) {
                std::string line;
                std::getline(stale, line);                     // header
                while (std::getline(stale, line)) {
                    const std::size_t comma = line.find(',');
                    if (comma == std::string::npos) continue;
                    std::uint64_t s = 0;
                    try { s = std::stoull(line.substr(0, comma)); }
                    catch (...) { continue; }
                    if (s >= lo && s <= hi) {
                        std::cerr << "bestbench: results file " << resultsFile
                                  << " already contains a row for seed " << s
                                  << " (requested block " << lo << ".." << hi << "). "
                                  << "bestbench appends without deduplication; remove "
                                  << "the stale file or use a fresh path (issue 46).\n";
                        return 1;
                    }
                }
            }
        }
        bestBench(sims, nSeeds, asc, seedOffset, resultsFile);

    } else if (mode == "cpsictr") {       // C_psi counter-sensitivity probe (needs STS_CPSI_NN)
        if (!g_cpsiNet.loaded()) {
            std::cerr << "cpsictr requires STS_CPSI_NN=<path> (e.g. build/v_combat_cpsi.txt)\n";
            return 1;
        }
        int sims = argc > 2 ? std::stoi(argv[2]) : 100;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 100;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seedOffset = argc > 5 ? std::stoull(argv[5]) : 0;
        std::cout << "[cpsictr: seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
                  << ", sims " << sims << ", asc " << asc << "]\n";
        for (std::uint64_t s = 0; s < (std::uint64_t)nSeeds; ++s)
            runFullRunOOC(seedOffset + s, sims, asc, false, true);
        cpsiCtrProbeReport();

    } else if (mode == "reprobench") {    // repeat one full run in one process; audit determinism
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        int repeats = argc > 3 ? std::stoi(argv[3]) : 2;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seed = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        std::cout << "[reprobench: seed " << seed << ", repeats " << repeats << "]\n";
        for (int i = 0; i < repeats; ++i) bestBench(sims, 1, asc, seed, resultsFile, "reprobench");

    } else if (mode == "runtrace") {      // per-node human-readable trace of ONE seed (STS_FAIR for fair-play)
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc  = argc > 4 ? std::stoi(argv[4]) : 0;
        runTraceRun(seed, sims, asc);

    } else {
        std::cerr << "usage: one_combat [bench|mcts|random|run|runbench|draftbench|pathbench|cardbench|combobench|datagen|deck] ...\n";
        return 1;
    }
    return 0;
}
