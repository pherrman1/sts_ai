#include "combat_model_diagnostics.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "constants/MonsterEncounters.h"
#include "sim/search/CombatValueNet.h"

using namespace sts;

bool isCombatModelDiagnosticMode(const std::string &mode) {
    return mode == "vnettest";
}

int runCombatModelDiagnosticMode(const std::string &mode, int argc, char **argv) {
if (mode == "vnettest") {      // ASSERTING C++ CombatValueNet vs Python parity
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

}

    return 0;
}
