// Semantic OOC pilot modes (oocsemanticcapture, oocsemanticeval, oocsemanticselftest).
// Split out of apps/one_combat.cpp; see driver_shared.h for shared state.

#include "one_combat/driver_shared.h"

// Separate semantic pilot schema. Source observation never runs a semantic
// counterfactual; branch execution starts only after atomic manifest replay.
struct SemanticPilotDecision {
    nlohmann::json identity;
    GameContext pre;
    PathHistory path;
    std::vector<search::OocSemanticAction> actions;
};
struct SemanticPilotObserverScope {
    decltype(search::g_onGameActionExecute) previous = std::move(search::g_onGameActionExecute);
    SemanticPilotObserverScope() { search::g_onGameActionExecute = {}; }
    ~SemanticPilotObserverScope() { search::g_onGameActionExecute = std::move(previous); t_curPath = nullptr; }
};

static nlohmann::json semanticPilotIdentity(const GameContext &gc, int idx,
                                            const search::OocEnumerationResult &enumeration) {
    nlohmann::json actions = nlohmann::json::array();
    for (int i=0; i<(int)enumeration.actions.size(); ++i) {
        const auto &a=enumeration.actions[i];
        actions.push_back({{"semanticActionIdx",i}, {"semanticKey",search::canonicalOocSemanticActionKey(a)},
            {"semanticEffect",(int)a.effect}, {"semanticSource",(int)a.source},
            {"semanticPayload",nlohmann::json::parse(search::oocSemanticActionPayloadJson(a))}});
    }
    return {{"sourceSeed",gc.seed},{"decisionIdx",idx},{"act",gc.act},{"floor",gc.floorNum},
        {"screen",(int)gc.screenState},{"semanticSchemaVersion",1},{"supported",enumeration.supported},
        {"complete",enumeration.complete},{"actions",actions}};
}

static void semanticPilotRequireIdentity(const nlohmann::json &live,const nlohmann::json &frozen) {
    if(live!=frozen) throw std::runtime_error("semantic pilot: frozen semantic sibling/metadata mismatch");
}

static std::optional<SemanticPilotDecision> semanticPilotSource(std::uint64_t seed,
                                                               const nlohmann::json *frozen=nullptr) {
    SemanticPilotObserverScope observerScope;
    trainingRunStart(); vDisconnect();
    GameContext gc(CharacterClass::IRONCLAD,seed,0);
    search::ScumSearchAgent2 agent; agent.simulationCountBase=10000; agent.simulationCountTotal=0;
    agent.rng=std::default_random_engine(seed);
    std::default_random_engine reservoir(seed*2862933555777941757ULL+97);
    PathHistory path; t_curPath=&path;
    std::optional<SemanticPilotDecision> selected;
    int eligible=0;
    CardSelectScreenType suppress=CardSelectScreenType::INVALID;
    search::g_onGameActionExecute=[&](std::uint32_t bits,const GameContext *target) {
        if (target!=&gc || (frozen && selected)) return;
        path.update(gc);
        if (suppress!=CardSelectScreenType::INVALID) {
            if (gc.screenState!=ScreenState::CARD_SELECT || gc.info.selectScreenType!=suppress)
                throw std::runtime_error("semantic pilot: compound selector boundary mismatch");
            suppress=CardSelectScreenType::INVALID;
            return;
        }
        const auto enumeration=search::enumerateOocSemanticActions(gc);
        // Floor zero excludes Neow independently of its primitive options.
        if (gc.outcome==GameOutcome::UNDECIDED && gc.floorNum>0 && enumeration.supported
            && enumeration.complete && enumeration.actions.size()>=2) {
            const int idx=eligible++;
            const bool replace=frozen ? idx==frozen->at("decisionIdx").get<int>()
                : std::uniform_int_distribution<int>(1,eligible)(reservoir)==1;
            if (replace) {
                auto identity=semanticPilotIdentity(gc,idx,enumeration);
                if (frozen) semanticPilotRequireIdentity(identity,*frozen);
                selected=SemanticPilotDecision{std::move(identity),detachedCounterfactualCopy(gc),path,enumeration.actions};
            }
        }
        suppress=search::oocSemanticPrimitiveCompoundSelector(gc,bits);
    };
    while (gc.outcome==GameOutcome::UNDECIDED && !(frozen && selected)) {
        path.update(gc);
        stepCounterfactualAuditSource(gc,agent);
        if (search::g_simHealthFailureCount!=t_trainingHealthFailures)
            throw std::runtime_error("semantic pilot: source simulator health failure");
    }
    if (frozen && !selected) throw std::runtime_error("semantic pilot: frozen source decision not reached");
    return selected;
}

static nlohmann::json semanticPilotStateFeatures() {
    return {{"schema","rich_state_masked_hidden_v1"},{"header",richStateHeader()},
        {"maskedColumns",{"nextEliteId","nextFight0","nextFight1","nextFight2"}}};
}

static std::string semanticPilotRichRow(const GameContext &gc,const PathHistory &path) {
    std::stringstream header(richStateHeader()),values(richRow(gc,path));
    std::ostringstream out; std::string name,value; int masked=0; bool first=true;
    while(std::getline(header,name,',')) {
        if(!std::getline(values,value,',')) throw std::runtime_error("semantic pilot: rich feature arity mismatch");
        if(name=="nextEliteId"||name=="nextFight0"||name=="nextFight1"||name=="nextFight2") {value="-1";++masked;}
        if(!first)out<<','; first=false; out<<value;
    }
    if(std::getline(values,value,',')||masked!=4)throw std::runtime_error("semantic pilot: rich feature contract mismatch");
    return out.str();
}

static nlohmann::json semanticPilotRuntimeBinding() {
    if (!g_nativeOoc || !g_floorNet.ok || !g_winNet.ok)
        throw std::runtime_error("semantic pilot: loaded native floor/win models required");
    if (!search::silverLiveBackendInstalled() || !search::silverLiveExactRootBudgets()
        || search::silverLiveReuseCapMode()!="allocated" || search::silverLiveReuseCap()!=32768
        || search::silverLiveAdaptiveEnabled())
        throw std::runtime_error("semantic pilot: frozen Silver runtime mismatch");
    nlohmann::json env=nlohmann::json::object();
    // Freeze the complete STS environment, including unset-vs-set identity;
    // this Linux-only pilot must not silently ignore a new policy option.
#ifndef _WIN32
    for(char **entry=::environ;entry && *entry;++entry) {
        const std::string text(*entry); const auto equal=text.find('=');
        if(equal!=std::string::npos && text.rfind("STS_",0)==0)
            env[text.substr(0,equal)]=text.substr(equal+1);
    }
#else
    throw std::runtime_error("semantic pilot: full environment binding requires Linux");
#endif
    if(env.value("STS_NATIVE_OOC",std::string{})!="1")
        throw std::runtime_error("semantic pilot: STS_NATIVE_OOC=1 must be explicit");
    for(const char *unsupported : {"STS_SILVER_VNET_LEAF_BLEND","STS_SILVER_VNET_LEAF_MODEL",
        "STS_SILVER_ROOT_DIAG_FILE","STS_SILVER_STICKY_QUALITY_FILE","STS_SILVER_LEAF_CORPUS",
        "STS_SIMS_NORMAL","STS_SIMS_ELITE","STS_SIMS_BOSS","STS_SIM_ADAPT",
        "STS_BOSS_V","STS_BOSS_DRAFT","STS_CARD_NN","STS_CARD_ACTION",
        "STS_PATH_GRAPH","STS_PATH_ACTION","STS_PATH_V"})
        if(std::getenv(unsupported))throw std::runtime_error(std::string("semantic pilot: unsupported teacher override ")+unsupported);
    return {{"environment",env},{"oocModels",nlohmann::json::array({
        {{"role","floor"},{"path",g_floorNet.path},{"sha256",fileSha256(g_floorNet.path)}},
        {{"role","win"},{"path",g_winNet.path},{"sha256",fileSha256(g_winNet.path)}}})}};
}

void semanticPilotCapture(int count,std::uint64_t offset,const std::string &manifestFile,
                                 const std::string &teacherFile) {
    if (count<1 || count>16) throw std::runtime_error("semantic pilot: source scan must be 1..16 seeds");
    const auto teacher=loadWholeCombatTeacher(teacherFile,10000);
    auto runtime=semanticPilotRuntimeBinding();
    if(std::filesystem::exists(manifestFile)) throw std::runtime_error("semantic pilot: manifest already exists");
    trainingCampaignStart();
    nlohmann::json decisions=nlohmann::json::array(),seeds=nlohmann::json::array();
    for(int i=0;i<count;++i) {
        seeds.push_back(offset+i);
        auto sampled=semanticPilotSource(offset+i);
        if(sampled) decisions.push_back(sampled->identity);
    }
    nlohmann::json doc={{"schema_version","ooc_semantic_manifest_v1"},
        {"row_schema_version","ooc_semantic_action_v1"},
        {"producer_git_sha",trainingExecutableGitSha()},
        {"producer_executable_sha256",fileSha256(g_mainBinaryPath)},
        {"combat_teacher",teacher.specification},{"runtime",runtime},{"stateFeatures",semanticPilotStateFeatures()},
        {"sampling",{{"rule","policy_independent_reservoir_eligible_semantic_decisions"},{"version",1},
            {"sourceSeeds",seeds},{"maxDecisionsPerSeed",1},{"excludeNeow",true}}},
        {"evaluation",{{"H",1},{"budgetSchedule",{10000}},{"futureIdentities",{0}},{"rngRegime","project_fair"}}},
        {"decisions",decisions},{"csv",nullptr},{"integrity",nullptr}};
    std::ofstream out(manifestFile); if(!out) throw std::runtime_error("semantic pilot: cannot write capture manifest");
    out<<doc.dump(2)<<'\n'; out.close(); if(!out) throw std::runtime_error("semantic pilot: manifest write failed");
    std::cout<<"semantic pilot captured "<<decisions.size()<<'/'<<count<<" source decisions -> "<<manifestFile<<'\n';
}

struct SemanticPilotBranch {
    search::OocExecutionResult executed;
    OocCounterfactualResult result;
    OocContinuationCost cost;
};

static SemanticPilotBranch semanticPilotBranch(GameContext branch,
        const search::OocSemanticAction &action,std::uint64_t continuation,const PathHistory &path,
        std::vector<CombatEvalFight> *combatCapture = nullptr, const OocPrefixObserver *checkpoint = nullptr) {
    if(search::g_onGameActionExecute) throw std::runtime_error("semantic pilot: branch observer active");
    const int healthBefore=search::g_simHealthFailureCount;
    auto executed=search::executeOocSemanticAction(branch,action);
    if(!executed.ok || executed.executedPrimitiveBits.empty() || search::g_simHealthFailureCount!=healthBefore)
        throw std::runtime_error("semantic pilot: frozen semantic execution failed/health failure: "+executed.error);
    const std::vector<int> schedule{10000};
    OocContinuationCost cost;
    const auto result=finishOocCounterfactual(std::move(branch),10000,continuation,path,
        1,true,nullptr,0,&schedule,false,checkpoint,&cost,false,combatCapture);
    if(!result.valid || !std::isfinite(result.won) || !std::isfinite(result.hp))
        throw std::runtime_error("semantic pilot: invalid/quarantined continuation");
    if(cost.transactionDecisions>cost.combatDecisions || cost.transactionDecisions>cost.transactionSubdecisions
        || cost.silverSimulations!=10000*(cost.combatDecisions+cost.transactionSubdecisions-cost.transactionDecisions))
        throw std::runtime_error("semantic pilot: exact teacher simulation accounting mismatch");
    return {std::move(executed),result,cost};
}

static void semanticCombatCaptureSelfTest(GameContext source, const search::OocSemanticAction &action) {
    auto require=[](bool ok,const char *message){if(!ok)throw std::runtime_error(message);};
    const auto previousDecision=search::g_onCombatDecision;
    try {
        for(const bool win : {false,true}) {
            int calls=0,observed=0;
            search::g_onCombatDecision=[&](const BattleContext &){++observed;};
            search::g_externalCombatBackend=[&](search::ScumSearchAgent2 &agent,GameContext &state,BattleContext &bc){
                ++calls;
                bc.init(state);
                if(search::g_onCombatDecision)search::g_onCombatDecision(bc);
                bc.player.maxHp=80; bc.player.curHp=win?20:0;
                bc.monsters.arr[0].curHp=30; bc.monsters.arr[0].maxHp=50;
                bc.outcome=win?Outcome::PLAYER_VICTORY:Outcome::PLAYER_LOSS;
                agent.simulationCountTotal+=20000;
                search::g_silverLiveDiagnostics={};
                search::g_silverLiveDiagnostics.decisions=1;
                search::g_silverLiveDiagnostics.transactionSubdecisions=2;
                search::g_silverLiveDiagnostics.transactionDecisions=1;
            };
            SemanticPilotObserverScope detached;
            std::string finalOff,finalOn;
            OocPrefixObserver off=[&](const GameContext &gc,int,const OocContinuationCost &){finalOff=test::oocStateFingerprint(gc);};
            OocPrefixObserver on=[&](const GameContext &gc,int,const OocContinuationCost &){finalOn=test::oocStateFingerprint(gc);};
            const int healthBefore=search::g_simHealthFailureCount;
            const auto control=semanticPilotBranch(detachedCounterfactualCopy(source),action,11,{},nullptr,&off);
            const int healthOff=search::g_simHealthFailureCount;
            std::vector<CombatEvalFight> captured;
            const auto treatment=semanticPilotBranch(detachedCounterfactualCopy(source),action,11,{},&captured,&on);
            require(calls==2 && observed==2,"combat capture: extra backend/observer call");
            require(!finalOff.empty() && finalOff==finalOn,"combat capture: resulting GameContext/RNG differs");
            require(healthBefore==healthOff && healthOff==search::g_simHealthFailureCount,"combat capture: health differs");
            require(control.executed.ok==treatment.executed.ok && control.executed.error==treatment.executed.error
                && control.executed.executedPrimitiveBits==treatment.executed.executedPrimitiveBits,"combat capture: primitive execution differs");
            const auto &a=control.result; const auto &b=treatment.result;
            require(a.won==b.won && a.hp==b.hp && a.floor==b.floor && a.bootstrapped==b.bootstrapped
                && a.valid==b.valid && a.survivedH==b.survivedH,"combat capture: semantic labels/qProduct differ");
            require(control.cost.silverSimulations==treatment.cost.silverSimulations
                && control.cost.combatDecisions==treatment.cost.combatDecisions
                && control.cost.transactionSubdecisions==treatment.cost.transactionSubdecisions
                && control.cost.transactionDecisions==treatment.cost.transactionDecisions,"combat capture: search accounting differs");
            require(captured.size()==1 && captured[0].label.labelValid,"combat capture: missing valid row");
            const auto &label=captured[0].label;
            require(label.won==win && label.trueDeath!=win && label.signedOutcome==(win?0.25:-0.6),"combat capture: independent terminal label mismatch");
            auto entry=detachedCounterfactualCopy(source);
            search::executeOocSemanticAction(entry,action);
            PathHistory path; path.update(entry);
            require(captured[0].features==richRow(entry,path),"combat capture: pre-init feature boundary differs");
        }
        // Boundary cases reuse the same V1 formula; no fight is simulated here.
        BattleContext bc{}; auto gc=detachedCounterfactualCopy(source); bc.init(gc,MonsterEncounter::CULTIST);
        bc.player.curHp=0; bc.outcome=Outcome::PLAYER_LOSS;
        auto ambiguous=combatEvalTerminal(bc,MonsterEncounter::AWAKENED_ONE,1,0,0);
        require(ambiguous.progressAmbiguous && ambiguous.labelValid && ambiguous.signedOutcome<0,"combat capture: V1 ambiguous-death semantics changed");
        bc.smokeBombUsed=true;
        auto escape=combatEvalTerminal(bc,MonsterEncounter::CULTIST,1,0,0);
        require(escape.escaped && !escape.trueDeath && !escape.labelValid && escape.signedOutcome==0,"combat capture: escape is valid");
        bc.smokeBombUsed=false; bc.outcome=Outcome::UNDECIDED; bc.turn=100;
        auto cap=combatEvalTerminal(bc,MonsterEncounter::CULTIST,1,0,0);
        require(cap.turnCapLoss && !cap.labelValid && cap.signedOutcome==0,"combat capture: turn cap is valid");
        bc.outcome=Outcome::PLAYER_VICTORY; bc.player.curHp=20;
        require(!combatEvalTerminal(bc,MonsterEncounter::CULTIST,1,0,1).labelValid,"combat capture: health failure is valid");
        require(!combatEvalTerminal(bc,MonsterEncounter::CULTIST,0,0,0).labelValid,"combat capture: missing hook is valid");
        bc.turn=0;
        const auto initializationWin = combatEvalTerminal(
            bc,MonsterEncounter::CULTIST,0,0,0,true);
        require(initializationWin.labelValid && initializationWin.won
                && std::string(initializationWin.reason).empty(),
                "combat capture: resolved initialization victory is valid");
        // A terminal OOC action emits no synthetic fight row.
        source.regainControlAction=[](GameContext &state){state.outcome=GameOutcome::PLAYER_VICTORY;};
        {
            SemanticPilotObserverScope detached;
            std::vector<CombatEvalFight> captured;
            semanticPilotBranch(detachedCounterfactualCopy(source),action,11,{},&captured);
            require(captured.empty(),"combat capture: fabricated a fight before combat");
        }
        // Observer exception safety is independent of combat continuation.
        try {CombatEvalDecisionScope scope(true); throw std::runtime_error("fixture");}catch(const std::runtime_error &){}
        require(bool(search::g_onCombatDecision),"combat capture: observer not restored after exception");
    } catch(...) {search::g_onCombatDecision=previousDecision;throw;}
    search::g_onCombatDecision=previousDecision;
}

// Deterministic integration regression: real semantic branch path, observer
// lifetime, continuation dispatch and transaction-aware simulation accounting.
void semanticPilotSelfTest() {
    auto previousBackend=search::g_externalCombatBackend;
    auto previousDiagnostics=search::g_silverLiveDiagnostics;
    auto previousObserver=search::g_onGameActionExecute;
    int hooks=0,backendCalls=0;
    try {
        search::g_onGameActionExecute=[&](std::uint32_t,const GameContext*){++hooks;};
        GameContext gc(CharacterClass::IRONCLAD,0x51514Du,0);
        gc.screenState=ScreenState::REST_ROOM; gc.curHp=40; gc.floorNum=1;
        gc.regainControlAction=[](GameContext &state){state.enterBattle(MonsterEncounter::CULTIST);};
        const auto enumeration=search::enumerateOocSemanticActions(gc);
        auto action=std::find_if(enumeration.actions.begin(),enumeration.actions.end(),[](const auto &a){return a.effect==search::OocSemanticEffect::REST;});
        if(action==enumeration.actions.end())throw std::runtime_error("semantic selftest: no rest action");
        const auto identity=semanticPilotIdentity(gc,0,enumeration);
        semanticPilotRequireIdentity(identity,nlohmann::json::parse(identity.dump()));
        for(int mutation=0;mutation<5;++mutation) {
            auto changed=identity;
            if(mutation==0)changed["floor"]=999;
            if(mutation==1)changed["actions"][0]["semanticKey"]="stale";
            if(mutation==2)changed["actions"][0]["semanticPayload"]["extra"]=1;
            if(mutation==3)std::swap(changed["actions"][0],changed["actions"][1]);
            if(mutation==4)changed["actions"].erase(0);
            bool failed=false;
            try {semanticPilotRequireIdentity(identity,changed);}catch(const std::runtime_error &){failed=true;}
            if(!failed||backendCalls)throw std::runtime_error("semantic selftest: frozen mismatch did not fail before backend");
        }
        bool rejected=false;
        try { semanticPilotBranch(detachedCounterfactualCopy(gc),*action,11,{}); }
        catch(const std::runtime_error &) {rejected=true;}
        if(!rejected||hooks)throw std::runtime_error("semantic selftest: active observer was not rejected");
        search::g_externalCombatBackend=[&](search::ScumSearchAgent2 &agent,GameContext &state,BattleContext &bc){
            ++backendCalls;
            if(search::g_onGameActionExecute)throw std::runtime_error("semantic selftest: observer leaked into backend");
            bc.init(state); bc.player.curHp=0; bc.outcome=Outcome::PLAYER_LOSS;
            agent.simulationCountTotal+=20000;
            search::g_silverLiveDiagnostics={};
            search::g_silverLiveDiagnostics.decisions=1;
            search::g_silverLiveDiagnostics.transactionSubdecisions=2;
            search::g_silverLiveDiagnostics.transactionDecisions=1;
        };
        {
            SemanticPilotObserverScope detached;
            const auto branch=semanticPilotBranch(detachedCounterfactualCopy(gc),*action,11,{});
            if(!branch.result.valid||branch.result.survivedH||branch.result.won!=0||branch.executed.executedPrimitiveBits.size()!=1
                ||backendCalls!=1||hooks!=0||branch.cost.silverSimulations!=20000||branch.cost.combatDecisions!=1
                ||branch.cost.transactionSubdecisions!=2||branch.cost.transactionDecisions!=1)
                throw std::runtime_error("semantic selftest: branch dispatch/accounting mismatch");
        }
        if(!search::g_onGameActionExecute)throw std::runtime_error("semantic selftest: observer not restored");
        semanticCombatCaptureSelfTest(gc,*action);
        const auto masked=semanticPilotRichRow(gc,{});
        std::stringstream names(richStateHeader()),values(masked); std::string name,value; int maskedCount=0;
        while(std::getline(names,name,',')) {
            std::getline(values,value,',');
            if(name=="nextEliteId"||name=="nextFight0"||name=="nextFight1"||name=="nextFight2") {
                if(value!="-1")throw std::runtime_error("semantic selftest: hidden encounter feature leaked");
                ++maskedCount;
            }
        }
        if(maskedCount!=4)throw std::runtime_error("semantic selftest: hidden mask arity");
        int sourceBattles=0;
        search::g_externalCombatBackend=[&](search::ScumSearchAgent2 &agent,GameContext &state,BattleContext &bc){
            bc.init(state); ++sourceBattles;
            bc.outcome=sourceBattles==1?Outcome::PLAYER_VICTORY:Outcome::PLAYER_LOSS;
            if(sourceBattles!=1)bc.player.curHp=0;
            agent.simulationCountTotal+=10000; search::g_silverLiveDiagnostics={};
            search::g_silverLiveDiagnostics.decisions=1;
        };
        const auto sampled=semanticPilotSource(0x51514Du);
        if(!sampled || sampled->actions.size()<2)throw std::runtime_error("semantic selftest: source capture empty");
        const auto frozen=nlohmann::json::parse(sampled->identity.dump());
        sourceBattles=0;
        const auto replay=semanticPilotSource(0x51514Du,&frozen);
        if(!replay||replay->identity!=frozen)throw std::runtime_error("semantic selftest: source replay differs");
        auto stale=frozen; stale["actions"][0]["semanticPayload"]["extra"]=1;
        sourceBattles=0; bool mismatch=false;
        try {semanticPilotSource(0x51514Du,&stale);}catch(const std::runtime_error &){mismatch=true;}
        if(!mismatch)throw std::runtime_error("semantic selftest: source accepted stale payload");

    } catch(...) {
        search::g_externalCombatBackend=previousBackend;search::g_silverLiveDiagnostics=previousDiagnostics;
        search::g_onGameActionExecute=previousObserver;throw;
    }
    search::g_externalCombatBackend=previousBackend;search::g_silverLiveDiagnostics=previousDiagnostics;
    search::g_onGameActionExecute=previousObserver;
    std::cout<<"semantic pilot integrated observer/backend/accounting checks passed\n";
}

void semanticPilotEvaluate(int count,const std::string &manifestFile,const std::string &outFile,
                                  const std::string &teacherFile,const std::string &combatFile) {
    const auto teacher=loadWholeCombatTeacher(teacherFile,10000);
    std::ifstream in(manifestFile); if(!in) throw std::runtime_error("semantic pilot: cannot open frozen manifest");
    nlohmann::json doc; in>>doc;
    const nlohmann::json evaluation={{"H",1},{"budgetSchedule",{10000}},{"futureIdentities",{0}},{"rngRegime","project_fair"}};
    if(doc.at("schema_version")!="ooc_semantic_manifest_v1" || doc.at("row_schema_version")!="ooc_semantic_action_v1"
        || doc.at("producer_git_sha")!=trainingExecutableGitSha()
        || doc.at("producer_executable_sha256")!=fileSha256(g_mainBinaryPath)
        || doc.at("combat_teacher")!=teacher.specification || doc.at("runtime")!=semanticPilotRuntimeBinding()
        || doc.at("stateFeatures")!=semanticPilotStateFeatures()
        || doc.at("evaluation")!=evaluation || count<1 || count>16 || (int)doc.at("decisions").size()!=count
        || doc.at("sampling").at("rule")!="policy_independent_reservoir_eligible_semantic_decisions"
        || doc.at("sampling").at("version")!=1)
        throw std::runtime_error("semantic pilot: frozen producer/teacher/evaluation mismatch");
    const auto scanSeeds=doc.at("sampling").at("sourceSeeds").get<std::vector<std::uint64_t>>();
    if(scanSeeds.empty()||scanSeeds.size()>16||doc.at("sampling").at("maxDecisionsPerSeed")!=1
        ||doc.at("sampling").at("excludeNeow")!=true
        ||std::unordered_set<std::uint64_t>(scanSeeds.begin(),scanSeeds.end()).size()!=scanSeeds.size())
        throw std::runtime_error("semantic pilot: invalid frozen source sampling rule");
    trainingCampaignStart();
    std::vector<SemanticPilotDecision> resolved;
    std::unordered_set<std::uint64_t> seeds;
    for(const auto &d:doc.at("decisions")) {
        const auto seed=d.at("sourceSeed").get<std::uint64_t>();
        if(std::find(scanSeeds.begin(),scanSeeds.end(),seed)==scanSeeds.end())
            throw std::runtime_error("semantic pilot: decision seed outside frozen source scan");
        if(!seeds.insert(seed).second) throw std::runtime_error("semantic pilot: multiple decisions for one seed");
        resolved.push_back(std::move(*semanticPilotSource(seed,&d)));
    }
    // Only after every source decision has replayed exactly may any branch run.
    SemanticPilotObserverScope detachedObserver;
    const std::string partial=outFile+".partial", boundManifest=outFile+".manifest.json";
    if(std::filesystem::exists(outFile)||std::filesystem::exists(partial)||std::filesystem::exists(boundManifest))
        throw std::runtime_error("semantic pilot: output already exists");
    std::ofstream combatOut;
    const std::string combatPartial=combatFile+".partial", combatManifest=combatFile+".manifest.json";
    if(!combatFile.empty()) {
        // Refuse aliases between either output, their sidecars and the frozen inputs.
        std::set<std::filesystem::path> paths;
        for(const auto &p : {outFile,partial,boundManifest,manifestFile,teacherFile,combatFile,combatPartial,combatManifest})
            if(!paths.insert(std::filesystem::weakly_canonical(p)).second)
                throw std::runtime_error("semantic pilot: overlapping input/output paths");
        for(const auto &p : {combatFile,combatPartial,combatManifest})
            if(std::filesystem::exists(p))throw std::runtime_error("semantic pilot: combat output already exists");
        combatOut.open(combatPartial);
        if(!combatOut)throw std::runtime_error("semantic pilot: cannot open combat output");
        combatOut<<"sourceSeed,decisionIdx,semanticActionIdx,semanticKey,futureIdentity,branchFightIdx,continuationSeed,hiddenSeed,semanticSource,act,floor,roomClass,encounter,teacherId,"
                 <<richStateHeader()<<','<<combatEvalLabelHeader()<<'\n'<<std::setprecision(17);
    }
    std::size_t combatRows=0,validCombat=0,wins=0,deaths=0,ambiguous=0;
    std::set<std::uint64_t> combatSeeds,quarantinedSeeds;
    std::ofstream out(partial); if(!out) throw std::runtime_error("semantic pilot: cannot open output");
    out<<"sourceSeed,decisionIdx,act,floor,screen,semanticSchemaVersion,semanticActionIdx,semanticKey,semanticEffect,semanticSource,semanticPayload,siblingCount,futureIdentity,H,budgetSchedule,continuationSeed,hiddenSeed,executedPrimitiveBits,survivedPrefix,continuationValue,qProduct,denseReferenceValue,terminalWon,silverSimulations,combatDecisions,transactionSubdecisions,transactionDecisions,cpuMs,wallMs,teacherId,valid,quarantineReason,richRow\n";
    out<<std::setprecision(17);
    std::size_t rows=0;
    const std::vector<int> schedule{10000};
    for(const auto &d:resolved) {
        const auto seed=d.identity.at("sourceSeed").get<std::uint64_t>();
        const int idx=d.identity.at("decisionIdx").get<int>();
        std::uint64_t continuation=seed^((std::uint64_t)(idx+1)*0x9e3779b97f4a7c15ULL)^0xbf58476d1ce4e5b9ULL;
        if(!continuation)continuation=1;
        std::uint64_t hidden=continuation^0x94d049bb133111ebULL; if(!hidden)hidden=1;
        GameContext base=detachedCounterfactualCopy(d.pre); resampleRemainingActEncounters(base,hidden);
        const std::string state=semanticPilotRichRow(d.pre,d.path);
        for(int ai=0;ai<(int)d.actions.size();++ai) {
            std::vector<CombatEvalFight> captures;
            const auto evaluated=semanticPilotBranch(detachedCounterfactualCopy(base),d.actions[ai],continuation,d.path,
                                                     combatFile.empty()?nullptr:&captures);
            if(captures.size()>1)throw std::runtime_error("semantic pilot: H=1 captured multiple combats");
            for(std::size_t fi=0;fi<captures.size();++fi) {
                const auto &fight=captures[fi]; const auto &label=fight.label;
                combatOut<<seed<<','<<idx<<','<<ai<<','<<csvQuote(d.identity.at("actions").at(ai).at("semanticKey").get<std::string>())
                         <<",0,"<<fi<<','<<continuation<<','<<hidden<<','<<(int)d.actions[ai].source<<','
                         <<fight.act<<','<<fight.floor<<','<<combatEvalRoomClass(fight.room)<<','
                         <<csvQuote(combatEvalEncounterValid(fight.encounter)?monsterEncounterStrings[(int)fight.encounter]:"INVALID")
                         <<','<<teacher.id<<','<<fight.features<<',';
                label.write(combatOut); combatOut<<'\n';
                ++combatRows; validCombat+=label.labelValid; wins+=label.labelValid&&label.won;
                deaths+=label.labelValid&&label.trueDeath; ambiguous+=label.progressAmbiguous;
                combatSeeds.insert(seed); if(!label.labelValid)quarantinedSeeds.insert(seed);
            }
            const auto &executed=evaluated.executed;
            const auto &result=evaluated.result;
            const auto &cost=evaluated.cost;
            const auto &a=d.identity.at("actions").at(ai);
            out<<seed<<','<<idx<<','<<d.pre.act<<','<<d.pre.floorNum<<','<<(int)d.pre.screenState<<",1,"<<ai<<','
                <<csvQuote(a.at("semanticKey").get<std::string>())<<','<<(int)d.actions[ai].effect<<','<<(int)d.actions[ai].source<<','
                <<csvQuote(a.at("semanticPayload").dump())<<','<<d.actions.size()<<",0,1,[10000],"<<continuation<<','<<hidden<<','
                <<csvQuote(nlohmann::json(executed.executedPrimitiveBits).dump())<<','<<(result.survivedH?1:0)<<','<<result.won<<','
                <<(result.survivedH?result.won:0.0)<<','<<(10.0*result.won+result.hp)<<',';
            if(result.bootstrapped==0)out<<result.won;
            out<<','<<cost.silverSimulations<<','<<cost.combatDecisions<<','<<cost.transactionSubdecisions<<','<<cost.transactionDecisions<<','
                <<cost.cpuMs<<','<<cost.wallMs<<','<<teacher.id<<",1,,"<<csvQuote(state)<<'\n';
            ++rows;
        }
    }
    out.close(); if(!out)throw std::runtime_error("semantic pilot: CSV write failed");
    std::filesystem::rename(partial,outFile);
    doc["frozen_manifest"]={{"path",manifestFile},{"sha256",fileSha256(manifestFile)}};
    doc["csv"]={{"path",outFile},{"sha256",fileSha256(outFile)}}; doc["integrity"]={{"rows",rows}};
    std::ofstream manifestOut(boundManifest); manifestOut<<doc.dump(2)<<'\n'; manifestOut.close();
    if(!manifestOut)throw std::runtime_error("semantic pilot: bound manifest write failed");
    if(!combatFile.empty()) {
        combatOut.close(); if(!combatOut)throw std::runtime_error("semantic pilot: combat CSV write failed");
        std::filesystem::rename(combatPartial,combatFile);
        std::vector<std::string> names; std::stringstream header(richStateHeader()); std::string name;
        while(std::getline(header,name,','))names.push_back(name);
        nlohmann::json combatDoc={{"schema_version","combat_evaluator_semantic_branch_v1"},
            {"producer_git_sha",trainingExecutableGitSha()},{"producer_executable_sha256",fileSha256(g_mainBinaryPath)},
            {"teacher",teacher.specification},{"frozen_manifest",{{"path",manifestFile},{"sha256",fileSha256(manifestFile)}}},
            {"semantic_manifest",{{"path",boundManifest},{"sha256",fileSha256(boundManifest)}}},
            {"csv",{{"path",combatFile},{"sha256",fileSha256(combatFile)}}},
            {"feature_contract",{{"count",names.size()},{"state_names",names}}},
            {"seed_spec",{{"sourceSeeds",scanSeeds}}},
            {"integrity",{{"rows",combatRows},{"valid",validCombat},{"invalid",combatRows-validCombat},
                {"wins",wins},{"deaths",deaths},{"ambiguous",ambiguous},{"source_seeds",combatSeeds.size()},
                {"quarantined_source_seeds",quarantinedSeeds.size()}}}};
        std::ofstream sidecar(combatManifest); sidecar<<combatDoc.dump(2)<<'\n'; sidecar.close();
        if(!sidecar)throw std::runtime_error("semantic pilot: combat manifest write failed");
    }
    std::cout<<"semantic pilot replayed="<<resolved.size()<<" branches="<<rows<<" -> "<<outFile<<'\n';
}
