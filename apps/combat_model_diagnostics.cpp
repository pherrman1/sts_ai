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
#include "sim/search/CombatPVNet.h"
#include "sim/search/CombatValueNet.h"

using namespace sts;

bool isCombatModelDiagnosticMode(const std::string &mode) {
    return mode == "vnettest" || mode == "policynettest"
        || mode == "pvnetparity" || mode == "policystats";
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

}

    return 0;
}
