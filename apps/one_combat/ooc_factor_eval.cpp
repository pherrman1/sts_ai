// Offline OOC factor and budget adjudication modes (oocfactoreval, oocbudgeteval).
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"

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

void oocFactorEvaluate(const std::string &manifestFile,
                              const std::string &outFile, int referenceSims,
                              int futures, int futureStart, int expectedDecisions,
                              bool marginalTradeoff,
                              bool boundedK3,
                              bool semanticFullRun) {
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

// Frozen-cohort K/search-budget evaluator. The JSON manifest contains one
// entry per source decision and the complete legal sibling set captured by
// ooccfaudit. Replay validates both action bits and the human-readable semantic
// description before any output is opened or continuation work starts.
struct OocBudgetAction { std::uint32_t bits; std::string semantic; bool chosen; };
struct OocBudgetDecision {
    std::uint64_t seed; int decIdx, act, floor, screen;
    std::vector<OocBudgetAction> actions;
};
struct OocBudgetResolved {
    OocBudgetDecision manifest; GameContext pre; PathHistory path;
    std::vector<search::GameAction> actions;
};

void stepCounterfactualAuditSource(GameContext &gc,
                                           search::ScumSearchAgent2 &agent) {
    using RT=search::GameAction::RewardsActionType;
    if(gc.screenState==ScreenState::BATTLE){
        agent.simulationCountBase=fightSims(gc,10000);BattleContext bc{};
        agent.playoutBattle(gc,bc);
        if(bc.outcome==Outcome::UNDECIDED)throw std::runtime_error("oockbudgeteval: source replay combat unresolved");
        bc.exitBattle(gc);
    }else if(gc.screenState==ScreenState::MAP_SCREEN&&gc.curMapNodeY<14)
        search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    else if(gc.screenState==ScreenState::REWARDS){auto&r=gc.info.rewardsContainer;
        if(r.goldRewardCount>0)search::GameAction(RT::GOLD,0).execute(gc);
        else if(r.relicCount>0)search::GameAction(RT::RELIC,0).execute(gc);
        else if(r.potionCount>0)search::GameAction(RT::POTION,0).execute(gc);
        else if(g_collectKeys&&r.emeraldKey)search::GameAction(RT::KEY,0).execute(gc);
        else if(g_collectKeys&&r.sapphireKey)search::GameAction(RT::KEY,0).execute(gc);
        else if(r.cardRewardCount==0)search::GameAction(RT::SKIP).execute(gc);
        else evalCardRewardPolicy(gc);
    }else agent.stepOutOfCombatPolicy(gc);
}

void oocBudgetEvaluate(const std::string &manifestFile,
                              const std::string &outFile,
                              const std::vector<int> &schedule,
                              int futures, int futureStart,
                              const std::string &side,
                              const std::string &specFile,
                              int shardIndex, int shardCount,
                              int workIndex, int workCount) {
    if (side != "A" && side != "B")
        throw std::runtime_error("oockbudgeteval: side must be A or B");
    const std::map<std::string,std::string> frozenEnv={{"STS_FAIR","1"},{"STS_SEARCHER3","0"},
        {"STS_SILVER_SEARCH","1"},{"STS_SILVER_EXACT_ROOT_BUDGETS","1"},
        {"STS_SILVER_REUSE_CAP_MODE","allocated"},{"STS_SILVER_ADAPTIVE","0"},
        {"STS_SILVER_VNET_LEAF_DIRECT","0"},{"STS_NATIVE_OOC","1"}};
    for(const auto &[name,expected]:frozenEnv){const char*actual=std::getenv(name.c_str());
        if(!actual||actual!=expected)throw std::runtime_error("oockbudgeteval: frozen environment mismatch for "+name);}
    if(!search::nativeSilverBackendInstalled()||!search::nativeSilverExactRootBudgets()
        ||search::nativeSilverReuseCap()!=32768||search::nativeSilverAdaptiveEnabled())
        throw std::runtime_error("oockbudgeteval: frozen Silver configuration mismatch");
    std::ifstream specInput(specFile);if(!specInput)throw std::runtime_error("oockbudgeteval: cannot open frozen experiment spec");
    nlohmann::json spec;specInput>>spec;
    if(spec.value("schema",std::string{})!="ooc_k_budget_experiment_v1"
        ||spec.at("sourceSha").get<std::string>()!=trainingExecutableGitSha()
        ||spec.at("executable").at("sha256").get<std::string>()!=fileSha256(g_mainBinaryPath)
        ||spec.at("manifest").at("sha256").get<std::string>()!=fileSha256(manifestFile)
        ||spec.at("analysis").at("sha256").get<std::string>()!=fileSha256(spec.at("analysis").at("path").get<std::string>()))
        throw std::runtime_error("oockbudgeteval: frozen spec hash/source mismatch");
    const int frozenShardCount=spec.at("execution").at("shardCount").get<int>();
    const int frozenWorkCount=spec.at("execution").at("recoveryWorkCount").get<int>();
    if(spec.at("execution").at("recoveryPartition").get<std::string>()!="action_future_modulo")
        throw std::runtime_error("oockbudgeteval: unsupported recovery partition");
    if(shardCount!=frozenShardCount||shardCount<=0||shardIndex < -1
        ||(shardIndex<0&&futures!=0)||shardIndex>=shardCount)
        throw std::runtime_error("oockbudgeteval: invalid or unfrozen shard assignment");
    if(workIndex < -1 || workIndex >= workCount || workCount != frozenWorkCount
        || (workIndex >= 0 && futures == 0))
        throw std::runtime_error("oockbudgeteval: invalid or unfrozen recovery work assignment");
    std::map<std::string,std::string> modelPaths;
    for(const auto &model:spec.at("oocModels")){
        const std::string role=model.at("role").get<std::string>(),path=model.at("path").get<std::string>();
        modelPaths[role]=path;
        if(fileSha256(path)!=model.at("sha256").get<std::string>())
            throw std::runtime_error("oockbudgeteval: frozen OOC model hash mismatch");
    }
    if(!g_nativeOoc||!g_floorNet.ok||!g_winNet.ok||modelPaths.size()!=2
        ||modelPaths["floor"]!=g_floorNet.path||modelPaths["win"]!=g_winNet.path)
        throw std::runtime_error("oockbudgeteval: frozen OOC models were not loaded/used");
    std::vector<int> expectedFutures;
    std::string aStage;
    if(side=="A"){
        aStage=schedule==std::vector<int>{10000,10000,10000}?"stageA":"stageB";
        expectedFutures=spec.at("A").at(aStage).at("futureIdentities").get<std::vector<int>>();
    }else expectedFutures=spec.at("B").at("futureIdentities").get<std::vector<int>>();
    std::vector<int> actualFutures;for(int i=0;i<futures;++i)actualFutures.push_back(futureStart+i);
    if(futures>0&&actualFutures!=expectedFutures)throw std::runtime_error("oockbudgeteval: future identities differ from frozen spec");
    if(side=="A"){
        bool found=false;for(const auto &s:spec.at("A").at(aStage).at("schedules"))if(s.get<std::vector<int>>()==schedule)found=true;
        if(!found)throw std::runtime_error("oockbudgeteval: A schedule differs from frozen spec");
    }else if(spec.at("B").at("schedule").get<std::vector<int>>()!=schedule)
        throw std::runtime_error("oockbudgeteval: B schedule differs from frozen spec");
    if (schedule.empty() || schedule.size() > 3
        || std::any_of(schedule.begin(), schedule.end(), [](int v){ return v <= 0; }))
        throw std::runtime_error("oockbudgeteval: schedule must contain 1..3 positive budgets");
    if (futures < 0) throw std::runtime_error("oockbudgeteval: futures must be nonnegative");
    std::ifstream input(manifestFile);
    if (!input) throw std::runtime_error("oockbudgeteval: cannot open manifest");
    nlohmann::json doc; input >> doc;
    if (doc.value("schema", std::string{}) != "ooc_k_budget_manifest_v1"
        || !doc.contains("decisions") || !doc["decisions"].is_array())
        throw std::runtime_error("oockbudgeteval: manifest schema mismatch");
    std::vector<OocBudgetDecision> manifest;
    for (const auto &j : doc["decisions"]) {
        OocBudgetDecision d{j.at("sourceSeed").get<std::uint64_t>(),
            j.at("decisionIdx").get<int>(), j.at("act").get<int>(),
            j.at("floor").get<int>(), j.at("screen").get<int>(), {}};
        for (const auto &a : j.at("actions"))
            d.actions.push_back({a.at("actionBits").get<std::uint32_t>(),
                                 a.at("semantic").get<std::string>(),
                                 a.at("chosen").get<bool>()});
        if (d.actions.size() < 2) throw std::runtime_error("oockbudgeteval: incomplete sibling set");
        if(shardIndex<0||(int)(d.seed%(std::uint64_t)shardCount)==shardIndex)
            manifest.push_back(std::move(d));
    }

    std::vector<OocBudgetResolved> resolved;
    for (const auto &m : manifest) {
        GameContext gc(CharacterClass::IRONCLAD, m.seed, 0); vDisconnect();
        search::ScumSearchAgent2 sourceAgent; sourceAgent.simulationCountBase=10000;
        sourceAgent.rng=std::default_random_engine(m.seed);
        PathHistory path; t_curPath=&path; int decIdx=0; bool found=false;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            path.update(gc);
            auto actions=search::GameAction::getAllActionsInState(gc);
            if (actions.size() >= 2) {
                if (decIdx == m.decIdx && gc.act == m.act && gc.floorNum == m.floor
                    && (int)gc.screenState == m.screen) {
                    // Preserve the audit's explicit-policy action when the
                    // generic enumerator omitted it (notably card skip).
                    for (const auto &expected : m.actions)
                        if (std::none_of(actions.begin(), actions.end(), [&](const auto &a){return a.bits==expected.bits;})) {
                            search::GameAction candidate(expected.bits);
                            if (candidate.isValidAction(gc)) actions.push_back(candidate);
                        }
                    std::vector<bool> used(actions.size(), false);
                    std::vector<search::GameAction> ordered;
                    for (const auto &expected : m.actions) {
                        int match=-1, count=0;
                        for (int i=0;i<(int)actions.size();++i)
                            if (actions[i].bits==expected.bits
                                && actionDescription(actions[i],gc)==expected.semantic) {match=i;++count;}
                        if (count != 1 || used[match])
                            throw std::runtime_error("oockbudgeteval: semantic action collision/ambiguity");
                        used[match]=true; ordered.push_back(actions[match]);
                    }
                    if (ordered.size()!=actions.size())
                        throw std::runtime_error("oockbudgeteval: legal sibling set differs from manifest");
                    resolved.push_back({m,detachedCounterfactualCopy(gc),path,std::move(ordered)});
                    found=true;
                }
                ++decIdx;
            }
            if(found)break;
            stepCounterfactualAuditSource(gc,sourceAgent);
        }
        t_curPath=nullptr;
        if(!found) throw std::runtime_error("oockbudgeteval: frozen decision did not replay seed="+std::to_string(m.seed));
    }
    if(resolved.size()!=manifest.size()) throw std::runtime_error("oockbudgeteval: incomplete atomic replay");
    std::cout<<"oockbudgeteval preflight resolved "<<resolved.size()<<'/'<<manifest.size()
             <<" decisions shard="<<shardIndex<<'/'<<shardCount<<"\n";
    if(futures==0) return;

    std::ostringstream shardSuffix;
    shardSuffix<<".shard-"<<std::setw(2)<<std::setfill('0')<<shardIndex
               <<"-of-"<<shardCount;
    if(workIndex>=0)
        shardSuffix<<".work-"<<std::setw(2)<<std::setfill('0')<<workIndex
                   <<"-of-"<<workCount;
    shardSuffix<<".csv";
    if(outFile.size()<shardSuffix.str().size()
        ||outFile.substr(outFile.size()-shardSuffix.str().size())!=shardSuffix.str())
        throw std::runtime_error("oockbudgeteval: output filename does not bind frozen shard assignment");
    const std::string partialFile=outFile+".partial";
    if(std::filesystem::exists(outFile)||std::filesystem::exists(partialFile))
        throw std::runtime_error("oockbudgeteval: output or partial file already exists");
    const std::string claimDir=outFile+".claim";
    if(!std::filesystem::create_directory(claimDir))
        throw std::runtime_error("oockbudgeteval: shard output claim already exists");
    if(std::filesystem::exists(outFile)||std::filesystem::exists(partialFile))
        throw std::runtime_error("oockbudgeteval: output appeared after shard claim");
    std::ofstream out(partialFile); if(!out)throw std::runtime_error("oockbudgeteval: cannot open partial output");
    out<<"sourceSeed,decisionIdx,act,floor,screen,actionIdx,actionBits,chosen,side,futureIdentity,"
          "continuationSeed,hiddenSeed,schedule,prefixFight,rowKind,survivedPrefix,continuationValue,"
          "qProduct,denseValue,terminalWon,silverSimulations,combatDecisions,cpuMs,wallMs,valid,quarantineReason\n";
    std::ostringstream scheduleText; for(int i=0;i<(int)schedule.size();++i){if(i)scheduleText<<';';scheduleText<<schedule[i];}
    for(const auto &d:resolved)for(int j=0;j<futures;++j){
        const int future=futureStart+j;
        std::uint64_t contSeed=d.manifest.seed
            ^((std::uint64_t)(d.manifest.decIdx+1)*0x9e3779b97f4a7c15ULL)
            ^((std::uint64_t)(future+1)*0xbf58476d1ce4e5b9ULL);
        if(!contSeed)contSeed=1;std::uint64_t hiddenSeed=contSeed^0x94d049bb133111ebULL;if(!hiddenSeed)hiddenSeed=1;
        GameContext siblingBase=detachedCounterfactualCopy(d.pre);resampleRemainingActEncounters(siblingBase,hiddenSeed);
        for(int ai=0;ai<(int)d.actions.size();++ai){
            const int workOrdinal=j*(int)d.actions.size()+ai;
            if(workIndex>=0&&workOrdinal%workCount!=workIndex)continue;
            GameContext branch=detachedCounterfactualCopy(siblingBase);d.actions[ai].execute(branch);
            std::optional<GameContext> equivalenceBranch;
            const bool checkEquivalence=side=="A"&&std::getenv("STS_OOC_K_CHECKPOINT_EQUIV");
            if(checkEquivalence)equivalenceBranch=detachedCounterfactualCopy(branch);
            std::vector<OocPrefixCheckpoint> prefixes;
            OocPrefixObserver observer=[&](const GameContext &state,int fight,const OocContinuationCost &cost){
                if(side!="A"||fight>(int)schedule.size())return;
                GameContext snapshot=detachedCounterfactualCopy(state);
                const bool survived=snapshot.outcome!=GameOutcome::PLAYER_LOSS;
                double value=snapshot.outcome==GameOutcome::PLAYER_VICTORY?1.0:0.0;
                double floor=snapshot.floorNum;
                double rawFloor=std::numeric_limits<double>::quiet_NaN();
                double rawWin=std::numeric_limits<double>::quiet_NaN();
                bool valid=true;
                if(snapshot.outcome==GameOutcome::UNDECIDED){
                    rawFloor=vStateRaw(snapshot);rawWin=vStateWin(snapshot);
                    // Mirror finishOocCounterfactual's established bootstrap
                    // contract: each optional model estimate falls back to
                    // the initialized finite value when outside its domain.
                    if(std::isfinite(rawFloor)&&rawFloor>=snapshot.floorNum&&rawFloor<=60)
                        floor=rawFloor;
                    if(std::isfinite(rawWin)&&rawWin>=0&&rawWin<=1)
                        value=rawWin;
                    valid=std::isfinite(floor)&&std::isfinite(value);
                }
                if(!valid){
                    std::ostringstream error;
                    error<<"oockbudgeteval: invalid checkpoint bootstrap sourceSeed="<<d.manifest.seed
                         <<" decisionIdx="<<d.manifest.decIdx<<" actionIdx="<<ai
                         <<" futureIdentity="<<future<<" prefixFight="<<fight
                         <<" stateFloor="<<snapshot.floorNum<<" hp="<<snapshot.curHp
                         <<" outcome="<<(int)snapshot.outcome<<" rawFloor="<<rawFloor
                         <<" rawWin="<<rawWin;
                    throw std::runtime_error(error.str());
                }
                prefixes.push_back({fight,survived,value,floor,(double)snapshot.curHp,
                    survived?value:0.0,10.0*value+snapshot.curHp,cost.silverSimulations,
                    cost.combatDecisions,cost.cpuMs,cost.wallMs,valid});
            };
            OocContinuationCost finalCost;
            const auto terminal=finishOocCounterfactual(std::move(branch),schedule.front(),contSeed,d.path,
                -1,false,nullptr,0,&schedule,false,side=="A"?&observer:nullptr,&finalCost);
            if(!terminal.valid) throw std::runtime_error("oockbudgeteval: invalid terminal continuation");
            if(checkEquivalence){
                OocContinuationCost controlCost;
                const auto control=finishOocCounterfactual(std::move(*equivalenceBranch),schedule.front(),contSeed,d.path,
                    -1,false,nullptr,0,&schedule,false,nullptr,&controlCost);
                if(control.valid!=terminal.valid||control.won!=terminal.won||control.floor!=terminal.floor
                    ||control.hp!=terminal.hp||controlCost.silverSimulations!=finalCost.silverSimulations
                    ||controlCost.combatDecisions!=finalCost.combatDecisions)
                    throw std::runtime_error("oockbudgeteval: observational checkpoint equivalence failed");
            }
            if(side=="A") {
                for(int k=1;k<=(int)schedule.size();++k)
                    if(std::none_of(prefixes.begin(),prefixes.end(),[&](const auto&p){return p.prefixFight==k;}))
                        prefixes.push_back({k,terminal.won==1.0,terminal.won,(double)terminal.floor,terminal.hp,
                            terminal.won,10.0*terminal.won+terminal.hp,
                            finalCost.silverSimulations,finalCost.combatDecisions,finalCost.cpuMs,finalCost.wallMs,true});
                std::sort(prefixes.begin(),prefixes.end(),[](const auto&a,const auto&b){return a.prefixFight<b.prefixFight;});
            }
            if(std::any_of(prefixes.begin(),prefixes.end(),[](const auto&p){return !p.valid||!std::isfinite(p.continuationValue)||!std::isfinite(p.qProduct)||!std::isfinite(p.denseValue);}))
                throw std::runtime_error([&]{
                    const auto &p=*std::find_if(prefixes.begin(),prefixes.end(),[](const auto &x){
                        return !x.valid||!std::isfinite(x.continuationValue)
                            ||!std::isfinite(x.qProduct)||!std::isfinite(x.denseValue);});
                    std::ostringstream error;
                    error<<"oockbudgeteval: invalid/non-finite prefix target sourceSeed="<<d.manifest.seed
                         <<" decisionIdx="<<d.manifest.decIdx<<" actionIdx="<<ai
                         <<" futureIdentity="<<future<<" prefixFight="<<p.prefixFight
                         <<" survived="<<p.survived<<" continuationValue="<<p.continuationValue
                         <<" qProduct="<<p.qProduct<<" denseValue="<<p.denseValue
                         <<" valid="<<p.valid;
                    return error.str();
                }());
            for(const auto&p:prefixes)out<<d.manifest.seed<<','<<d.manifest.decIdx<<','<<d.manifest.act<<','<<d.manifest.floor<<','<<d.manifest.screen<<','<<ai<<','<<d.actions[ai].bits<<','<<(d.manifest.actions[ai].chosen?1:0)<<','<<side<<','<<future<<','<<contSeed<<','<<hiddenSeed<<','<<scheduleText.str()<<','<<p.prefixFight<<",prefix,"<<(p.survived?1:0)<<','<<p.continuationValue<<','<<p.qProduct<<','<<p.denseValue<<",,"<<p.silverSimulations<<','<<p.combatDecisions<<','<<p.cpuMs<<','<<p.wallMs<<','<<(p.valid?1:0)<<",\n";
            // Terminal truth is emitted for provenance on both sides. Analysis
            // accepts it as reference only when side=B.
            out<<d.manifest.seed<<','<<d.manifest.decIdx<<','<<d.manifest.act<<','<<d.manifest.floor<<','<<d.manifest.screen<<','<<ai<<','<<d.actions[ai].bits<<','<<(d.manifest.actions[ai].chosen?1:0)<<','<<side<<','<<future<<','<<contSeed<<','<<hiddenSeed<<','<<scheduleText.str()<<",0,terminal,,,,,"<<terminal.won<<','<<finalCost.silverSimulations<<','<<finalCost.combatDecisions<<','<<finalCost.cpuMs<<','<<finalCost.wallMs<<','<<(terminal.valid?1:0)<<","<<(terminal.valid?"":"invalid_terminal")<<'\n';
        }
    }
    out.close();
    std::filesystem::rename(partialFile,outFile);
}
