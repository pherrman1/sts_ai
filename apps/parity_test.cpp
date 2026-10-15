//
// parity_test.cpp: C++/PyTorch inference parity checker
// Usage: parity_test.elf MODEL_PATH FEAT_CSV N_SAMPLES OUT_CSV
//
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatValueNet.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <cmath>

int main(int argc, char **argv) {
    if (argc < 5) {
        std::cerr << "usage: parity_test MODEL FEAT_CSV N OUT\n";
        return 1;
    }
    const char *modelPath = argv[1];
    const char *featCsv   = argv[2];
    int nSamples          = std::stoi(argv[3]);
    const char *outCsv    = argv[4];

    sts::search::g_richCombatFeatures = true;
    sts::search::CombatDistValueNet net;
    if (!net.load(modelPath)) {
        std::cerr << "LOAD FAILED: " << modelPath << "\n";
        return 2;
    }
    std::cerr << "Loaded: " << net.description() << "\n";

    std::ifstream inf(featCsv);
    std::ofstream outf(outCsv);
    std::string line;
    int count = 0;

    while (std::getline(inf, line) && count < nSamples) {
        std::array<float, 1766> feat{};
        std::stringstream ss(line);
        std::string cell;
        for (int i = 0; i < 1766; ++i) {
            if (!std::getline(ss, cell, ',')) break;
            feat[i] = std::stof(cell);
        }
        sts::CombatObservation dummy;  // not used by predict, just needed for signature
        auto pred = net.predict(dummy, feat);

        outf << pred.deathProbability << ','
             << pred.winProbability;
        for (int q = 0; q < sts::search::kQuantileBins; ++q)
            outf << ',' << pred.endHpQuantiles[q];
        for (int p = 0; p < 44; ++p)
            outf << ',' << pred.potionUseProbability[p];
        outf << ',' << pred.expectedTurnsRemaining << '\n';
        ++count;
    }
    std::cerr << "Wrote " << count << " predictions to " << outCsv << "\n";
    return 0;
}
