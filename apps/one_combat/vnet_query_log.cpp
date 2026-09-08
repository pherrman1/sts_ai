#include "vnet_query_log.h"

#include "combat/BattleContext.h"
#include "sim/search/CombatValueNet.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <vector>

namespace one_combat {

namespace {

std::string g_vnetQueryLogPath;
double g_vnetQuerySample = 1.0;
std::mutex g_vnetQueryLogMutex;
std::ofstream g_vnetQueryLogFile;
thread_local struct {
    std::uint64_t seed = 0;
    int fightIdx = -1;
    int decIdx = -1;
    bool active = false;
    std::mt19937_64 rng;
    std::string buf;
} t_vq;

void vnetQueryLogFlushImpl() {
    if (t_vq.buf.empty()) return;
    std::lock_guard<std::mutex> lock(g_vnetQueryLogMutex);
    if (!g_vnetQueryLogFile.is_open()) return;
    g_vnetQueryLogFile << t_vq.buf;
    g_vnetQueryLogFile.flush();
    t_vq.buf.clear();
}

void onVNetQuery(const sts::BattleContext &bc, double prediction) {
    if (!t_vq.active) return;
    if (g_vnetQuerySample < 1.0) {
        std::uniform_real_distribution<double> dist(0.0, 1.0);
        if (dist(t_vq.rng) >= g_vnetQuerySample) return;
    }
    const int nf = sts::search::combatFeatureCount();
    std::vector<float> feats(nf);
    sts::search::combatExtractFeatures(bc, feats.data());
    std::ostringstream o;
    o << t_vq.seed << ',' << t_vq.fightIdx << ',' << t_vq.decIdx
      << ',' << sts::search::g_vnetTraceParent << ',' << sts::search::g_vnetTraceDepth;
    for (int i = 0; i < nf; ++i) {
        o << ',';
        const float v = feats[i];
        if (v == (float)(long)v) o << (long)v; else o << v;
    }
    o << ',' << prediction << '\n';
    t_vq.buf += o.str();
    if (t_vq.buf.size() > 65536) vnetQueryLogFlushImpl();
}

} // namespace

void configureVNetQueryLogFromEnvironment() {
    if (const char *d = std::getenv("STS_VNET_QUERY_LOG")) {
        g_vnetQueryLogPath = d;
        if (const char *s = std::getenv("STS_VNET_QUERY_SAMPLE")) {
            g_vnetQuerySample = std::atof(s);
            if (g_vnetQuerySample <= 0.0) g_vnetQuerySample = 1.0;
            if (g_vnetQuerySample > 1.0) g_vnetQuerySample = 1.0;
        }
        g_vnetQueryLogFile.open(g_vnetQueryLogPath, std::ios::out);
        if (g_vnetQueryLogFile.is_open()) {
            g_vnetQueryLogFile << "seed,fightIdx,decIdx,parentObsHash,depth";
            for (const auto &name : sts::search::combatFeatureNames())
                g_vnetQueryLogFile << ',' << name;
            g_vnetQueryLogFile << ",vnetPred\n";
            g_vnetQueryLogFile.flush();
            sts::search::g_onVNetQuery = onVNetQuery;
            std::cout << "[VNet query log ON: " << g_vnetQueryLogPath
                      << " sample=" << g_vnetQuerySample << "]\n";
        } else {
            std::cerr << "[VNet query log FAILED to open: " << g_vnetQueryLogPath << "]\n";
        }
    }
}

bool vnetQueryLogConfigured() {
    return !g_vnetQueryLogPath.empty();
}

void beginVNetQueryLogFight(std::uint64_t seed, int fightIdx) {
    t_vq.active = true;
    t_vq.seed = seed;
    t_vq.fightIdx = fightIdx;
    t_vq.decIdx = -1;
    t_vq.rng.seed(seed * 6364136223846793005ULL + (std::uint64_t)fightIdx);
}

void flushVNetQueryLog() {
    if (t_vq.active) vnetQueryLogFlushImpl();
}

} // namespace one_combat
