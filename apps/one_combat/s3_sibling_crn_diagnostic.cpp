#include "s3_sibling_crn_diagnostic.h"

#include "combat/BattleContextBinary.h"
#include "frontier_blob_io.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/CombatPVNet.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/S3SiblingCrnDiagnostic.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace one_combat {
namespace {

// Offline sibling common-random-numbers diagnostic. This intentionally does
// not call search(), allocate PUCT visits, or touch the historical g_s3Crn
// warm-start path. Each output row is one attempted forced-action evaluation.
std::string csvQuoted(const std::string &s) {
    std::string out = "\"";
    for (char c : s) { if (c == '\"') out.push_back('\"'); out.push_back(c); }
    out.push_back('\"');
    return out;
}

std::string s3CrnActionDesc(const sts::search::Action &a, const sts::BattleContext &bc) {
    std::ostringstream ss; a.printDesc(ss, bc); return ss.str();
}

std::string s3CrnCounters(const std::array<std::int32_t, 6> &v) {
    std::ostringstream ss;
    for (std::size_t i = 0; i < v.size(); ++i) { if (i) ss << ';'; ss << v[i]; }
    return ss.str();
}

std::uint64_t s3CrnFileHash(const std::string &path) {
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

bool s3SiblingCrnDiagnostic(const std::string &inCsv,
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

} // namespace

bool isS3SiblingCrnDiagnosticMode(const std::string &mode) {
    return mode == "s3siblingcrn";
}

int runS3SiblingCrnDiagnosticMode(const std::string &mode, int argc, char **argv) {
    if (!isS3SiblingCrnDiagnosticMode(mode)) return 2;
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
    sts::search::g_s3Crn = false;
    return s3SiblingCrnDiagnostic(argv[2], argv[3], argv[4], budgets,
                                  std::stoi(argv[6]), std::stoi(argv[7]),
                                  std::stoull(argv[8]), argv[9], argv[10],
                                  argc > 11 ? argv[11] : "") ? 0 : 1;
}

} // namespace one_combat
