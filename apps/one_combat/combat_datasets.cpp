// Whole-combat, combat-eval, combat-transition and counterfactual-surrogate dataset generators.
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"

// ---------------------------------------------------------------------------
// Combat feature header/row for whole-combat datasets. They delegate to the
// library (search::combatFeatureNames / combatExtractFeatures) so training data
// and C++ inference use the same feature extraction.
static std::string combatHeaderStr() {
    const auto &names = search::combatFeatureNames();
    std::string h;
    for (size_t i = 0; i < names.size(); ++i) { if (i) h += ','; h += names[i]; }
    return h;
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

// One canonical battle-start row per completed fight. GameContext labels and
// diagnostics are captured after exitBattle returns, i.e. after regainControl
// has entered the reward screen and normal afterBattle effects have run.

static nlohmann::json effectiveOocPolicySpecification() {
    nlohmann::json models = nlohmann::json::array();
    auto addModel = [&](const char *role, const std::string &path) {
        if (!path.empty())
            models.push_back({{"role", role}, {"path", path}, {"sha256", fileSha256(path)}});
    };
    if (g_floorNet.ok) addModel("floor", g_floorNet.path);
    if (g_winNet.ok) addModel("win", g_winNet.path);
    if (g_oocActionNN && g_oocCheckpointNet.ok) addModel("ooc_checkpoint", g_oocCheckpointNet.path);
    if (g_oocStrategicNet.ok) addModel("ooc_strategic", g_oocStrategicNet.path);
    if (g_oocStrategicTokNet.ok) addModel("ooc_strategic_tok", g_oocStrategicTokNet.path);
    if (g_oocMapRoute && g_cpsiNet.loaded()) addModel("cpsi", g_cpsiNet.path);
    if (g_actFightProbeAllOoc && g_actFightProbePredict && g_actFightProbePredictNet.loaded())
        addModel("act_fight_probe_predict", g_actFightProbePredictNet.path);
    return {
        {"schema_version", "runFullRunOOC_policy_v1"},
        {"policy_chain", "runFullRunOOC"},
        {"restV", false},
        {"shopV", true},
        {"native_ooc", g_nativeOoc},
        {"flags", {
            {"collect_keys", g_collectKeys},
            {"ooc_action_nn", g_oocActionNN},
            {"act_fight_probe_all_ooc", g_actFightProbeAllOoc},
            {"ooc_map_route", g_oocMapRoute},
            {"ooc_strategic_map", g_oocStrategicMap},
            {"path_v", g_pathV},
            {"event_v", g_eventV},
            {"ooc_strategic_event", g_oocStrategicEvent},
            {"ooc_strategic_card", g_oocStrategicNet.ok || g_oocStrategicTokNet.ok},
            {"ooc_strategic_tok", g_oocStrategicTok != 0},
            {"ooc_strategic_shop", g_oocStrategicShop},
            {"ooc_shop_beam", g_oocShopBeam},
            {"ooc_strategic_rest", g_oocStrategicRest},
            {"ooc_strategic_q", g_oocStrategicQ},
            {"ooc_strategic_score_policy", g_oocStrategicScorePolicy},
            {"rest_win", g_restWin},
            {"ooc_strategic_boss_relic", g_oocStrategicBossRelic},
            {"boss_relic_v", g_bossRelicV != 0},
            {"ooc_strategic_treasure", g_oocStrategicTreasure},
            {"neow_v", g_neowV != 0},
            {"card_win", g_cardWin},
            {"card_nn", g_cardNN},
            {"card_action", g_cardAction},
            {"shop_win", g_shopWin},
            {"boss_v", g_bossV != 0},
            {"boss_draft", g_bossDraft != 0},
            {"act_fight_probe_draft", g_actFightProbeDraft},
            {"act_fight_probe_all_ooc", g_actFightProbeAllOoc},
            {"act_fight_probe_predict", g_actFightProbePredict},
            {"act_fight_probe_encounter_nn", g_actFightProbeEncounterNN},
            {"act_fight_probe_gate_regret", g_oocStrategicGateRegret},
        }},
        {"parameters", {
            {"card_skip_threshold", g_cardSkipThresh},
            {"card_win_skip", g_cardWinSkip},
            {"card_nn_weight", g_cardNNW},
            {"card_nn_skip", g_cardNNSkip},
            {"shop_beam_width", g_oocShopBeamWidth},
            {"shop_beam_depth", g_oocShopBeamDepth},
            {"shop_beam_budget", g_oocShopBeamBudget},
            {"strategic_margin", g_oocStrategicMargin},
            {"strategic_margin_card", g_oocStrategicMarginCard},
            {"strategic_margin_rest", g_oocStrategicMarginRest},
            {"strategic_margin_event", g_oocStrategicMarginEvent},
            {"strategic_margin_shop", g_oocStrategicMarginShop},
            {"strategic_margin_treasure", g_oocStrategicMarginTreasure},
            {"strategic_margin_boss_relic", g_oocStrategicMarginBossRelic},
            {"strategic_margin_map", g_oocStrategicMarginMap},
            {"strategic_gate", g_oocStrategicGateRegret ? "regret" : "margin"},
            {"strategic_gate_eps", g_oocStrategicGateEps},
            {"map_route_horizon", g_oocMapRouteHorizon},
            {"boss_draft_rows", g_bossDraftRows},
            {"boss_draft_fights", g_bossDraftN},
            {"boss_draft_sims", g_bossDraftSims},
            {"boss_draft_futures", g_bossDraftFutures},
            {"boss_v_weight", g_bossVW},
            {"act_fight_probe_sims", g_actFightProbeSims},
            {"act_fight_probe_futures", g_actFightProbeFutures},
            {"act_fight_probe_checkpoint_sims", g_actFightProbeCheckpointSims},
            {"act_fight_probe_floor_decay", g_actFightProbeFloorDecay},
            {"act_fight_probe_max_checkpoints", g_actFightProbeMaxCheckpoints},
            {"act_fight_probe_term_win", g_actFightProbeTermWin},
            {"act_fight_probe_margin", g_actFightProbeMargin},
            {"act_fight_probe_predict_win_threshold", g_actFightProbePredictWinThreshold},
            {"stop_after_act", g_stopAfterAct},
        }},
        {"model_artifacts", std::move(models)},
    };
}

WholeCombatTeacher loadWholeCombatTeacher(const std::string &path, int sims,
                                                 bool allowStaleProvenance,
                                                 bool requireOocPolicy) {
    std::ifstream in(path); if (!in) throw std::runtime_error("wholecombatgen: cannot open teacher " + path);
    nlohmann::json t; in >> t;
    auto req = [&](const char *key) { if (!t.contains(key) || !t[key].is_string() || t[key].get<std::string>().empty()) throw std::runtime_error(std::string("wholecombatgen: teacher missing ")+key); return t[key].get<std::string>(); };
    const std::string id=req("teacher_id"), gitSha=req("git_sha"), exeSha=req("executable_sha256");
    if (id.find_first_of(",\r\n") != std::string::npos) throw std::runtime_error("wholecombatgen: teacher_id is not CSV-safe");
    if (gitSha.size()!=40 || (!allowStaleProvenance && gitSha!=trainingExecutableGitSha())) throw std::runtime_error("wholecombatgen: teacher git_sha mismatch");
    if (exeSha.size()!=64 || (!allowStaleProvenance && exeSha!=fileSha256(g_mainBinaryPath))) throw std::runtime_error("wholecombatgen: executable SHA256 mismatch");
    if (req("combat_backend")!="silver_uct" || req("rng_regime")!="project_fair") throw std::runtime_error("wholecombatgen: teacher backend/RNG mismatch");
    if (!t.contains("search_configuration") || !t["search_configuration"].is_object()) throw std::runtime_error("wholecombatgen: missing search_configuration");
    const auto &s=t["search_configuration"];
    if (s.value("simulation_budgets",std::vector<int>{})!=std::vector<int>{10000} || sims!=10000
        || s.value("exploration_parameter",-1.0)!=25.0 || s.value("exploration_parameter_chance",-1.0)!=25.0
        || s.value("chance_widening_c",-1.0)!=3.7028 || s.value("chance_widening_alpha",-1.0)!=0.52389
        || s.value("end_turn_widening_c",-1.0)!=3.7028 || s.value("end_turn_widening_alpha",-1.0)!=0.52389
        || s.value("reuse_cap_mode",std::string{})!="allocated" || s.value("reuse_cap",-1)!=32768
        || s.value("sequential_halving",true) || s.value("pruning",true) || s.value("learned_visit_puct",true)
        || s.value("direct_learned_leaf",true) || s.value("adaptive",true))
        throw std::runtime_error("wholecombatgen: not the frozen exact-10k ordinary Silver contract");
    if (search::silverLiveReuseCap() != 32768)
        throw std::runtime_error("wholecombatgen: production reuse cap mismatch with frozen 32k teacher");
    if (!t.contains("environment") || !t["environment"].is_object()) throw std::runtime_error("wholecombatgen: missing environment");
    for (const auto &[name, expected] : t["environment"].items()) { const char *actual=std::getenv(name.c_str()); if (!expected.is_string() || !actual || expected.get<std::string>()!=actual) throw std::runtime_error("wholecombatgen: environment mismatch for "+name); }
    const std::map<std::string,std::string> required={{"STS_FAIR","1"},{"STS_SEARCHER3","0"},{"STS_SILVER_SEARCH","1"},{"STS_SILVER_EXACT_ROOT_BUDGETS","1"},{"STS_SILVER_REUSE_CAP_MODE","allocated"},{"STS_SILVER_ADAPTIVE","0"},{"STS_SILVER_VNET_LEAF_DIRECT","0"},{"STS_SILVER_TELEMETRY","1"}};
    for (const auto &[name,value]:required) if (!t["environment"].contains(name) || t["environment"][name]!=value) throw std::runtime_error("wholecombatgen: frozen environment missing "+name+"="+value);
    if (!t.contains("model_artifacts") || !t["model_artifacts"].is_array()) throw std::runtime_error("wholecombatgen: model_artifacts must be an array");
    for (const auto &a:t["model_artifacts"]) { const std::string role=a.value("role",std::string{}), p=a.value("path",std::string{}), h=a.value("sha256",std::string{}); if(role.empty()||p.empty()||h.size()!=64||fileSha256(p)!=h) throw std::runtime_error("wholecombatgen: artifact hash mismatch for "+role); }
    if (requireOocPolicy && (!t.contains("ooc_policy") || t["ooc_policy"] != effectiveOocPolicySpecification()))
        throw std::runtime_error("wholecombatgen: effective OOC policy configuration/artifacts mismatch");
    return {id,std::move(t)};
}
static std::string wholePotionIds(const GameContext &gc) { std::ostringstream o; for(int i=0;i<gc.potionCapacity&&i<(int)gc.potions.size();++i){if(i)o<<';';o<<(int)gc.potions[i];} return o.str(); }
static std::map<int,int> wholeRelics(const GameContext &gc) { std::map<int,int> o; for(const auto&r:gc.relics.relics)o[(int)r.id]=r.data; return o; }
static std::string wholeRelicChanges(const std::map<int,int>&b,const GameContext&a){std::ostringstream o;bool first=true;for(const auto&r:a.relics.relics){auto it=b.find((int)r.id);int old=it==b.end()?0:it->second;if(old==r.data)continue;if(!first)o<<';';first=false;o<<(int)r.id<<':'<<old<<'>'<<r.data;}return o.str();}
static std::vector<std::tuple<int,int,int>> wholeDeck(const GameContext&gc){std::vector<std::tuple<int,int,int>>o;for(const auto&c:gc.deck.cards)o.emplace_back((int)c.id,c.upgraded?1:0,c.misc);return o;}
static int wholeCardCount(const GameContext&gc,CardId id){int n=0;for(const auto&c:gc.deck.cards)if(c.id==id)++n;return n;}
static std::string wholeRitualChanges(const std::vector<std::tuple<int,int,int>>&b,const GameContext&a){std::ostringstream o;bool first=true;for(int i=0;i<(int)a.deck.cards.size();++i){const auto&c=a.deck.cards[i];if(c.id!=CardId::RITUAL_DAGGER)continue;int old=(i<(int)b.size()&&std::get<0>(b[i])==(int)c.id)?std::get<2>(b[i]):-1;if(old==c.misc)continue;if(!first)o<<';';first=false;o<<i<<':'<<old<<'>'<<c.misc;}return o.str();}

static std::string runWholeCombatGenSeed(std::uint64_t seed,int sims,int asc,const WholeCombatTeacher&teacher){
    trainingRunStart(); GameContext gc(CharacterClass::IRONCLAD,seed,asc); search::ScumSearchAgent2 agent;agent.simulationCountBase=sims;agent.rng=std::default_random_engine(seed);std::ostringstream out;int fightIdx=0;using RT=search::GameAction::RewardsActionType;
    while(gc.outcome==GameOutcome::UNDECIDED){
        if(gc.screenState==ScreenState::BATTLE){
            const int act=gc.act,floor=gc.floorNum,room=(int)gc.curRoom,startHp=gc.curHp,startMaxHp=gc.maxHp,startGold=gc.gold,startPotionCount=gc.potionCount,startParasites=wholeCardCount(gc,CardId::PARASITE);const std::string startPotions=wholePotionIds(gc);const auto startRelics=wholeRelics(gc);const auto startDeck=wholeDeck(gc);std::string features;int hooks=0;
            search::g_onCombatDecision=[&](const BattleContext&s){if(hooks++==0)features=combatFeatureRow(s);};BattleContext bc;agent.playoutBattle(gc,bc);const int encounter=(int)bc.encounter;search::g_onCombatDecision=nullptr;
            if(!trainingRunValid(bc.outcome!=Outcome::UNDECIDED)||hooks==0)return{};const int won=bc.outcome==Outcome::PLAYER_VICTORY?1:0;bc.exitBattle(gc);
            const std::string relics=wholeRelicChanges(startRelics,gc),ritual=wholeRitualChanges(startDeck,gc);const bool deckChanged=startDeck!=wholeDeck(gc),parasite=wholeCardCount(gc,CardId::PARASITE)>startParasites;std::ostringstream summary;summary<<"potions="<<startPotionCount<<'>'<<gc.potionCount<<";hp="<<startHp<<'>'<<gc.curHp<<";maxhp="<<startMaxHp<<'>'<<gc.maxHp<<";gold_delta="<<gc.gold-startGold<<";relics="<<(relics.empty()?"none":"changed")<<";deck="<<(deckChanged?"changed":"same")<<";parasite="<<(parasite?1:0)<<";stolen_gold="<<gc.info.stolenGold;const char*roomClass=room==(int)Room::MONSTER?"NORMAL":room==(int)Room::ELITE?"ELITE":room==(int)Room::BOSS?"BOSS":"OTHER";
            out<<seed<<','<<fightIdx<<','<<act<<','<<floor<<','<<encounter<<','<<roomClass<<",0,"<<teacher.id<<','<<features<<','<<won<<','<<gc.curHp<<','<<startHp<<','<<startMaxHp<<','<<gc.maxHp<<','<<(startMaxHp>0?(double)gc.curHp/startMaxHp:0.0)<<','<<startPotions<<','<<wholePotionIds(gc)<<','<<startPotionCount<<','<<gc.potionCount<<','<<gc.gold-startGold<<','<<(gc.smokeBombUsed?1:0)<<','<<relics<<','<<ritual<<','<<(deckChanged?1:0)<<','<<(parasite?1:0)<<','<<summary.str()<<'\n';++fightIdx;
        }else if(gc.screenState==ScreenState::MAP_SCREEN&&gc.curMapNodeY<14)search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        else if(gc.screenState==ScreenState::REWARDS){auto&r=gc.info.rewardsContainer;if(r.goldRewardCount>0)search::GameAction(RT::GOLD,0).execute(gc);else if(r.relicCount>0)search::GameAction(RT::RELIC,0).execute(gc);else if(r.potionCount>0)search::GameAction(RT::POTION,0).execute(gc);else if(g_collectKeys&&r.emeraldKey)search::GameAction(RT::KEY,0).execute(gc);else if(g_collectKeys&&r.sapphireKey)search::GameAction(RT::KEY,0).execute(gc);else if(r.cardRewardCount==0)search::GameAction(RT::SKIP).execute(gc);else evalCardRewardPolicy(gc);}else agent.stepOutOfCombatPolicy(gc);
    }search::g_onCombatDecision=nullptr;return out.str();
}

// V1 producer: capture the persistent GameContext before BattleContext::init;
// read terminal labels from BattleContext before exitBattle/afterBattle.
// The optional runout record deliberately separates a completed trajectory
// from the existing per-combat label validity.  An escape is still a bad V1
// combat label, but it need not invalidate the eventual-run outcome.
struct CombatEvalSeedResult {
    std::string rows;
    std::uint64_t sourceSeed = 0;
    GameOutcome finalOutcome = GameOutcome::UNDECIDED;
    int finalFloor = 0;
    int finalHp = 0;
    int fightCount = 0;
    int invalidCombatRows = 0;
    int simulatorHealthFailures = 0;
    bool sourceValid = true;
    bool trajectoryComplete = false;
    bool trajectoryValid = false;
    bool fatalFailure = false;
};

static const char *combatEvalGameOutcome(GameOutcome outcome) {
    switch (outcome) {
        case GameOutcome::PLAYER_VICTORY: return "PLAYER_VICTORY";
        case GameOutcome::PLAYER_LOSS: return "PLAYER_LOSS";
        case GameOutcome::UNDECIDED: return "UNDECIDED";
    }
    return "UNDECIDED";
}

static int combatEvalFinalWon(GameOutcome outcome) {
    return outcome == GameOutcome::PLAYER_VICTORY ? 1
        : outcome == GameOutcome::PLAYER_LOSS ? 0 : -1;
}

static CombatEvalSeedResult runCombatEvalGenSeed(std::uint64_t seed, int sims, int asc,
                                                 const WholeCombatTeacher &teacher,
                                                 bool captureCombat = true) {
    trainingRunStart();
    const int sourceHealthFailures = search::g_simHealthFailureCount;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent; agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path;
    one_combat::resetPathPolicyState();
    t_actFightProbeDecisionIdx = 0;
    t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;
    t_shopV = true;
    std::ostringstream out; int fightIdx = 0; bool sourceValid = true;
    int invalidCombatRows = 0;
    bool fatalFailure = false;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            const int act = gc.act, floor = gc.floorNum, room = (int)gc.curRoom;
            const MonsterEncounter encounter = gc.info.encounter;
            const int encounterIndex = static_cast<int>(encounter);
            const bool representableEncounter = encounterIndex >= 0 && encounterIndex < static_cast<int>(sizeof(monsterEncounterStrings) / sizeof(monsterEncounterStrings[0]));
            const std::string features = captureCombat ? vFeatCsv(gc) : std::string{};
            int hooks = 0;
            auto previousCombatObserver = std::move(search::g_onCombatDecision);
            if (captureCombat)
                search::g_onCombatDecision = [&](const BattleContext &) { ++hooks; };
            BattleContext bc; const int healthBefore = search::g_simHealthFailureCount;
            agent.playoutBattle(gc, bc);
            search::g_onCombatDecision = std::move(previousCombatObserver);
            const bool initializationTerminal = hooks == 0
                && bc.turn == 0 && bc.outcome != Outcome::UNDECIDED;
            const auto label = captureCombat
                ? combatEvalTerminal(bc, encounter, hooks, healthBefore, search::g_simHealthFailureCount,
                                     initializationTerminal)
                : CombatEvalLabel{};
            const bool labelValid = captureCombat && label.labelValid;
            const bool healthOk = captureCombat ? label.healthOk : true;
            if (captureCombat) {
                out << seed << ',' << fightIdx << ',' << act << ',' << floor << ',' << combatEvalRoomClass(static_cast<Room>(room)) << ','
                    << csvQuote(representableEncounter ? monsterEncounterStrings[encounterIndex] : "INVALID") << ',' << teacher.id << ',' << features << ',';
                label.write(out); out << '\n';
            }
            ++fightIdx;
            // Keep every completed terminal as an auditable row.  A simulator
            // or hook failure cannot safely advance the run; ordinary
            // non-death terminations can be exited and the next fight may be
            // collected, while the contract/trainer excludes this row.
            if (captureCombat && !labelValid) { sourceValid = false; ++invalidCombatRows; }
            if (captureCombat && !labelValid && (!healthOk || !hooks || !representableEncounter)) {
                fatalFailure = true;
                search::g_onGameActionExecute = {}; t_curPath = nullptr;
                const int healthFailures = std::max(0, search::g_simHealthFailureCount - sourceHealthFailures);
                return {out.str(), seed, gc.outcome, gc.floorNum, gc.curHp, fightIdx,
                        invalidCombatRows, healthFailures, false, false, false, fatalFailure};
            }
            bc.exitBattle(gc);
        } else {
            runFullRunOocPolicyStep(gc, agent, false, true);
        }
    }
    search::g_onCombatDecision = nullptr;
    t_curPath = nullptr;
    const bool complete = gc.outcome != GameOutcome::UNDECIDED;
    const int healthFailures = std::max(0, search::g_simHealthFailureCount - sourceHealthFailures);
    const bool trajectoryValid = complete && healthFailures == 0 && !fatalFailure;
    return {out.str(), seed, gc.outcome, gc.floorNum, gc.curHp, fightIdx,
            invalidCombatRows, healthFailures, sourceValid, complete,
            trajectoryValid, fatalFailure};
}

int oocPolicyParitySelfTest(std::uint64_t seed, int sims, int asc) {
    using OocAction = std::pair<int, std::uint32_t>;
    auto traceRun = [](const auto &run) {
        std::vector<OocAction> trace;
        auto previous = std::move(search::g_onGameActionExecute);
        search::g_onGameActionExecute = [&](std::uint32_t bits, const GameContext *target) {
            if (target) trace.emplace_back(static_cast<int>(target->screenState), bits);
        };
        const auto result = run();
        search::g_onGameActionExecute = std::move(previous);
        return std::make_pair(result, std::move(trace));
    };

    const auto normal = traceRun([&] {
        return runFullRunOOC(seed, sims, asc, false, true, false);
    });
    WholeCombatTeacher parityTeacher{"ooc-policy-parity", nlohmann::json::object()};
    const auto captured = traceRun([&] {
        return runCombatEvalGenSeed(seed, sims, asc, parityTeacher, false);
    });
    const auto &specialized = captured.first;
    const bool sameOutcome = normal.first.won == (specialized.finalOutcome == GameOutcome::PLAYER_VICTORY)
        && normal.first.floor == specialized.finalFloor
        && normal.first.hpEnd == specialized.finalHp;
    if (!sameOutcome || normal.second != captured.second) {
        std::cerr << "ooc policy parity failed: seed=" << seed
                  << " normal=(" << normal.first.won << ',' << normal.first.floor << ',' << normal.first.hpEnd
                  << ") specialized=(" << static_cast<int>(specialized.finalOutcome) << ',' << specialized.finalFloor
                  << ',' << specialized.finalHp << ") actions=" << normal.second.size()
                  << '/' << captured.second.size() << '\n';
        return 1;
    }
    std::cout << "ooc policy parity: seed=" << seed << " actions=" << normal.second.size()
              << " outcome=" << (normal.first.won ? "PLAYER_VICTORY" : "PLAYER_LOSS")
              << " floor=" << normal.first.floor << " hp=" << normal.first.hpEnd << "\n";
    return 0;
}


int teacherSchemaCompatibilitySelfTest() {
    for (const auto &[name, value] : std::vector<std::pair<const char *, const char *>>{
             {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
             {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
             {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
             {"STS_SILVER_TELEMETRY", "1"}})
        setenv(name, value, 1);

    search::installSilverLiveBackend();
    const std::filesystem::path stem = std::filesystem::temp_directory_path()
        / ("sts_legacy_teacher_compat_" + trainingExecutableGitSha()
           + "_" + std::to_string(search::silverLiveReuseCap()));
    const std::filesystem::path teacherPath = stem.string() + ".json";
    const std::filesystem::path wholePath = stem.string() + ".whole.csv";
    const std::filesystem::path evalPath = stem.string() + ".eval.csv";
    const auto cleanup = [&] {
        for (const auto &path : {teacherPath, wholePath, evalPath,
                                 std::filesystem::path(wholePath.string() + ".provenance.json"),
                                 std::filesystem::path(evalPath.string() + ".provenance.json")}) {
            std::error_code ignored;
            std::filesystem::remove(path, ignored);
        }
    };
    try {
        const std::string leafPath = "models/silver_leaf_m10_10k.txt";
        const nlohmann::json teacher = {
            {"teacher_id", "legacy-schema-compat"},
            {"git_sha", trainingExecutableGitSha()},
            {"executable_sha256", fileSha256(g_mainBinaryPath)},
            {"combat_backend", "silver_uct"},
            {"rng_regime", "project_fair"},
            {"search_configuration", {
                {"simulation_budgets", {10000}}, {"exploration_parameter", 25.0},
                {"exploration_parameter_chance", 25.0}, {"chance_widening_c", 3.7028},
                {"chance_widening_alpha", 0.52389}, {"end_turn_widening_c", 3.7028},
                {"end_turn_widening_alpha", 0.52389}, {"reuse_cap_mode", "allocated"},
                {"reuse_cap", 32768}, {"sequential_halving", false}, {"pruning", false},
                {"learned_visit_puct", false}, {"direct_learned_leaf", false}, {"adaptive", false},
            }},
            {"environment", {
                {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
                {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
                {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
                {"STS_SILVER_TELEMETRY", "1"},
            }},
            {"model_artifacts", {{{"role", "combat_value_or_leaf"},
                                   {"path", leafPath}, {"sha256", fileSha256(leafPath)}}}},
        };
        std::ofstream out(teacherPath);
        if (!out) throw std::runtime_error("teacher compatibility: cannot create fixture");
        out << teacher.dump(2) << '\n';
        out.close();
        if (search::silverLiveReuseCap() != 32768) {
            const auto expectCapMismatch = [&](const auto &run) {
                bool rejected = false;
                try { run(); }
                catch (const std::runtime_error &error) {
                    rejected = std::string(error.what()).find("production reuse cap mismatch") != std::string::npos;
                }
                if (!rejected || std::filesystem::exists(wholePath) || std::filesystem::exists(evalPath))
                    throw std::runtime_error("frozen teacher cap mismatch must reject before output");
            };
            expectCapMismatch([&] { wholeCombatGen(0, 10000, 0, wholePath.string(), 0, teacherPath.string()); });
            expectCapMismatch([&] { combatEvalGen(0, 10000, 0, evalPath.string(), 0, teacherPath.string(), ""); });
            cleanup();
            std::cout << "frozen 32k teacher compatibility: both producers reject production cap mismatch before output\n";
            return 0;
        }
        wholeCombatGen(0, 10000, 0, wholePath.string(), 0, teacherPath.string());
        combatEvalGen(0, 10000, 0, evalPath.string(), 0, teacherPath.string(), "");
    } catch (...) {
        cleanup();
        throw;
    }
    cleanup();
    std::cout << "legacy teacher schema compatibility: wholecombatgen and combatevalgen without RUNOUT accepted\n";
    return 0;
}

void combatEvalGen(int nSeeds, int sims, int asc, const std::string &outfile,
                          long long seedOffset, const std::string &teacherPath,
                          const std::string &runoutPath) {
    trainingCampaignStart(); const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false,
                                                                           !runoutPath.empty());
    std::ofstream f(outfile); if (!f) throw std::runtime_error("combatevalgen: cannot open output");
    std::ofstream runout;
    if (!runoutPath.empty()) {
        runout.open(runoutPath);
        if (!runout) throw std::runtime_error("combatevalgen: cannot open runout output");
        runout << "sourceSeed,finalOutcome,finalWon,finalFloor,finalHp,fightCount,trajectoryComplete,trajectoryValid,combatRows,invalidCombatRows,teacherId,simulatorHealthFailures,fatalFailure\n";
    }
    f << "sourceSeed,fightIdx,act,floor,roomClass,encounter,teacherId," << richStateHeader()
      << ',' << combatEvalLabelHeader() << '\n';
    long long rows = 0; int completed = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const CombatEvalSeedResult generated = runCombatEvalGenSeed(seedOffset + s, sims, asc, teacher);
        #pragma omp critical(combat_eval_write)
        {
            f << generated.rows; f.flush();
            rows += std::count(generated.rows.begin(), generated.rows.end(), '\n');
            if (generated.sourceValid) ++completed; else ++g_trainingInvalidRuns;
            g_trainingInvalidBranches += generated.invalidCombatRows;
            if (!runoutPath.empty()) {
                runout << generated.sourceSeed << ',' << combatEvalGameOutcome(generated.finalOutcome) << ','
                       << combatEvalFinalWon(generated.finalOutcome) << ',' << generated.finalFloor << ','
                       << generated.finalHp << ',' << generated.fightCount << ','
                       << (generated.trajectoryComplete ? 1 : 0) << ','
                       << (generated.trajectoryValid ? 1 : 0) << ','
                       << std::count(generated.rows.begin(), generated.rows.end(), '\n') << ','
                       << generated.invalidCombatRows << ',' << teacher.id << ','
                       << generated.simulatorHealthFailures << ',' << (generated.fatalFailure ? 1 : 0) << '\n';
                runout.flush();
            }
        }
    }
    std::cout << "combatevalgen teacher=" << teacher.id << " completed=" << completed << '/' << nSeeds << " quarantined=" << nSeeds-completed << " rows=" << rows << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, "combatevalgen", nSeeds, completed, nSeeds-completed, g_trainingHealthFailures.load(), rows, seedOffset, sims, asc);
}
void wholeCombatGen(int nSeeds,int sims,int asc,const std::string&outfile,long long seedOffset,const std::string&teacherPath){trainingCampaignStart();search::g_richCombatFeatures=true;const auto teacher=loadWholeCombatTeacher(teacherPath,sims);std::ofstream f(outfile);if(!f)throw std::runtime_error("wholecombatgen: cannot open output");f<<"sourceSeed,fightIdx,act,floor,encounter,roomClass,decisionIdx,teacherId,"<<combatHeaderStr()<<",won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac,startPotionIds,endPotionIds,startPotionCount,endPotionCount,goldDelta,smokeBombUsed,changedRelicCounters,ritualDaggerChanges,deckStructureChanged,parasiteAdded,persistentMutationSummary\n";long long rows=0;int completed=0;
    #pragma omp parallel for schedule(dynamic)
    for(int s=0;s<nSeeds;++s){const std::string generated=runWholeCombatGenSeed(seedOffset+s,sims,asc,teacher);
        #pragma omp critical(whole_combat_write)
        {f<<generated;f.flush();rows+=std::count(generated.begin(),generated.end(),'\n');if(!generated.empty())++completed;}}
    std::cout<<"wholecombatgen teacher="<<teacher.id<<" completed="<<completed<<'/'<<nSeeds<<" quarantined="<<nSeeds-completed<<" rows="<<rows<<" -> "<<outfile<<'\n';writeTrainingProvenance(outfile,"wholecombatgen",nSeeds,completed,nSeeds-completed,g_trainingHealthFailures.load(),rows,seedOffset,sims,asc);
}

static nlohmann::json combatTransitionRowJson(
    std::uint64_t sourceSeed, int fightIdx, int act, int floor, Room room,
    int encounter, const std::string &teacherId, bool runValid,
    bool outcomeDecided,
    int rawCaptureCount,
    const std::optional<one_combat::CombatTransitionRecord> &record,
    const nlohmann::json &predictorInput) {
    const bool captureValid = rawCaptureCount == 1 && record.has_value();
    const bool rowValid = runValid && captureValid;
    const std::string quarantineReason =
        rawCaptureCount == 0 ? "missing_raw_capture" :
        rawCaptureCount > 1 ? "repeated_raw_capture" :
        !record ? "missing_raw_record" :
        !runValid ? (outcomeDecided ? "invalid_run" : "unresolved") : "";
    return {
        {"schemaVersion", one_combat::CombatTransitionRecord::SCHEMA},
        {"rowSchemaVersion", one_combat::COMBAT_TRANSITION_ROW_SCHEMA},
        {"sourceSeed", sourceSeed}, {"fightIdx", fightIdx},
        {"act", act}, {"floor", floor},
        {"roomClass", combatEvalRoomClass(room)}, {"encounter", encounter},
        {"teacherId", teacherId}, {"runValid", rowValid},
        {"quarantineReason", quarantineReason},
        {"captureCount", rawCaptureCount},
        {"captureStatus", rawCaptureCount == 0 ? "missing" :
                          rawCaptureCount == 1 ? "exactly_one" : "repeated"},
        {"predictorInput", predictorInput},
        {"transition", captureValid ? one_combat::combatTransitionRecordJson(*record)
                                     : nlohmann::json(nullptr)}
    };
}

// Capture one JSONL transition per real fight at the RAW persistent-transfer
// boundary. This is a data producer only: it never substitutes the snapshot
// for native continuation and is not part of the default gameplay path.
static std::string runCombatTransitionGenSeed(std::uint64_t seed, int sims, int asc,
                                              const WholeCombatTeacher &teacher) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path;
    t_curPath = &path;
    std::ostringstream out;
    int fightIdx = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            const GameContext pre = gc;
            const int battleAct = gc.act;
            const int battleFloor = gc.floorNum;
            const Room battleRoom = gc.curRoom;
            const int battleEncounter = static_cast<int>(gc.info.encounter);
            const auto predictorInput = one_combat::combatPredictorInputJson(
                one_combat::captureCombatPredictorInput(
                    pre, static_cast<MonsterEncounter>(battleEncounter),
                    potionKeepValue(gc)));
            std::optional<one_combat::CombatTransitionRecord> record;
            int rawCaptureCount = 0;
            bool decided = false;
            bool runValid = false;
            BattleContext bc;
            {
                one_combat::CombatTransitionRawObserverScope scope(
                    [&](const BattleContext &ended, GameContext &raw) {
                        ++rawCaptureCount;
                        if (rawCaptureCount == 1)
                            record = one_combat::captureCombatTransition(pre, ended, raw);
                    });
                agent.playoutBattle(gc, bc);
                decided = bc.outcome != Outcome::UNDECIDED;
                runValid = trainingRunValid(decided);
                // Keep the RAW observer armed through the real exit.  The
                // callback is intentionally before regainControl/afterBattle,
                // including for loss and unresolved outcomes.
                bc.exitBattle(gc);
            }
            nlohmann::json row = combatTransitionRowJson(
                seed, fightIdx++, battleAct, battleFloor, battleRoom,
                battleEncounter, teacher.id, runValid, decided, rawCaptureCount, record,
                predictorInput);
            out << row.dump() << '\n';
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0) search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0) search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else evalCardRewardPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return out.str();
}

// This is deliberately a test-only backend: it constructs deterministic
// BattleContexts directly and exercises the same RAW observer, exitBattle,
// and row serializer as combattransitiongen. It never loads a teacher, runs
// Silver, or supplies a production collection path.
static nlohmann::json combatTransitionFixtureTeacher() {
    return {
        {"teacher_id", "test-only-deterministic-transition-fixture"},
        {"git_sha", trainingExecutableGitSha()},
        {"executable_sha256", fileSha256(g_mainBinaryPath)},
        {"combat_backend", "deterministic_fixture"},
        {"rng_regime", "deterministic_fixture"},
        {"search_configuration", nlohmann::json::object()},
        {"environment", nlohmann::json::object()},
        {"model_artifacts", nlohmann::json::array()}
    };
}

static nlohmann::json combatTransitionFixtureRow(std::uint64_t seed, int fightIdx,
                                                  Outcome outcome, int hp) {
    trainingRunStart();
    GameContext source(CharacterClass::IRONCLAD, seed, 0);
    source.screenState = ScreenState::BATTLE;
    source.curRoom = Room::MONSTER;
    source.info.encounter = MonsterEncounter::CULTIST;
    source.regainControlAction = [](GameContext &g) {
        g.screenState = ScreenState::REWARDS;
    };
    GameContext actual = source;
    const auto predictorInput = one_combat::combatPredictorInputJson(
        one_combat::captureCombatPredictorInput(source, MonsterEncounter::CULTIST, 4.0));
    BattleContext bc;
    bc.init(actual, MonsterEncounter::CULTIST);
    bc.player.curHp = hp;
    bc.outcome = outcome;

    std::optional<one_combat::CombatTransitionRecord> record;
    int rawCaptureCount = 0;
    {
        one_combat::CombatTransitionRawObserverScope scope(
            [&](const BattleContext &ended, GameContext &raw) {
                ++rawCaptureCount;
                if (rawCaptureCount == 1)
                    record = one_combat::captureCombatTransition(source, ended, raw);
            });
        const bool decided = bc.outcome != Outcome::UNDECIDED;
        const bool runValid = trainingRunValid(decided);
        bc.exitBattle(actual);
        return combatTransitionRowJson(
            seed, fightIdx, source.act, source.floorNum, source.curRoom,
            static_cast<int>(source.info.encounter),
            "test-only-deterministic-transition-fixture", runValid, decided,
            rawCaptureCount, record, predictorInput);
    }
}

int combatTransitionFixture(const std::string &outfile,
                                   const std::string &manifestPath) {
    GameContext fixtureSource(CharacterClass::IRONCLAD, 0xC0FFEEu, 0);
    fixtureSource.screenState = ScreenState::BATTLE;
    fixtureSource.curRoom = Room::MONSTER;
    fixtureSource.info.encounter = MonsterEncounter::CULTIST;
    const auto fixtureInput = one_combat::combatPredictorInputJson(
        one_combat::captureCombatPredictorInput(
            fixtureSource, MonsterEncounter::CULTIST, 4.0));
    const std::uint64_t seed = 0xC0FFEEu;
    const auto missing = combatTransitionRowJson(
        seed, 99, 1, 1, Room::MONSTER, static_cast<int>(MonsterEncounter::CULTIST),
        "test-only-deterministic-transition-fixture", false, false, 0, {},
        fixtureInput);
    const auto repeated = combatTransitionRowJson(
        seed, 100, 1, 1, Room::MONSTER, static_cast<int>(MonsterEncounter::CULTIST),
        "test-only-deterministic-transition-fixture", false, true, 2, {},
        fixtureInput);
    if (missing["captureStatus"] != "missing" ||
        missing["quarantineReason"] != "missing_raw_capture" ||
        !missing["transition"].is_null() ||
        repeated["captureStatus"] != "repeated" ||
        repeated["quarantineReason"] != "repeated_raw_capture" ||
        !repeated["transition"].is_null()) {
        throw std::runtime_error("combattransitionselftest: capture quarantine serializer failed");
    }
    const std::vector<nlohmann::json> rows = {
        combatTransitionFixtureRow(seed, 0, Outcome::PLAYER_VICTORY, 23),
        combatTransitionFixtureRow(seed, 1, Outcome::PLAYER_LOSS, 0),
        combatTransitionFixtureRow(seed, 2, Outcome::UNDECIDED, 17),
    };
    std::ofstream output(outfile);
    if (!output) throw std::runtime_error("combattransitionselftest: cannot open output");
    for (const auto &row : rows) output << row.dump() << '\n';
    output.close();

    const auto manifest = nlohmann::json{
        {"schemaVersion", one_combat::CombatTransitionRecord::SCHEMA},
        {"rowSchemaVersion", one_combat::COMBAT_TRANSITION_ROW_SCHEMA},
        {"predictorInputSchemaVersion", one_combat::CombatPredictorInputV1::SCHEMA},
        {"predictorInputFieldSchemaHash", one_combat::combatPredictorInputFieldSchemaHash()},
        {"format", "jsonl"}, {"testFixture", true},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"combatTeacher", combatTransitionFixtureTeacher()},
        {"seedSpec", {{"start", seed}, {"count", 1}}},
        {"csv", {{"path", std::filesystem::absolute(outfile).string()},
                  {"sha256", fileSha256(outfile)}}},
        {"integrity", {{"requestedSeeds", 1}, {"completedSeeds", 1},
                        {"quarantinedSeeds", 0}, {"rows", rows.size()}}}
    };
    std::ofstream manifestFile(manifestPath);
    if (!manifestFile)
        throw std::runtime_error("combattransitionselftest: cannot open manifest");
    manifestFile << manifest.dump(2) << '\n';
    std::cout << "combattransitionselftest wrote " << rows.size()
              << " native rows -> " << outfile << "\n"
              << "manifest -> " << manifestPath << '\n';
    return 0;
}

void combatTransitionGen(int nSeeds, int sims, int asc,
                                const std::string &outfile, long long seedOffset,
                                const std::string &teacherPath) {
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims);
    std::ofstream f(outfile);
    if (!f) throw std::runtime_error("combattransitiongen: cannot open output");
    long long rows = 0;
    int completed = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runCombatTransitionGenSeed(seedOffset + s, sims, asc, teacher);
        #pragma omp critical(combat_transition_write)
        {
            f << generated;
            f.flush();
            rows += std::count(generated.begin(), generated.end(), '\n');
            if (!generated.empty()) ++completed;
        }
    }
    f.close();
    nlohmann::json manifest = {
        {"schemaVersion", one_combat::CombatTransitionRecord::SCHEMA},
        {"rowSchemaVersion", one_combat::COMBAT_TRANSITION_ROW_SCHEMA},
        {"predictorInputSchemaVersion", one_combat::CombatPredictorInputV1::SCHEMA},
        {"predictorInputFieldSchemaHash", one_combat::combatPredictorInputFieldSchemaHash()},
        {"format", "jsonl"}, {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"combatTeacher", teacher.specification},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}}},
        {"csv", {{"path", std::filesystem::absolute(outfile).string()},
                  {"sha256", fileSha256(outfile)}}},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed},
                        {"quarantinedSeeds", nSeeds - completed}, {"rows", rows}}}
    };
    std::ofstream mf(outfile + ".manifest.json");
    if (!mf) throw std::runtime_error("combattransitiongen: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "combattransitiongen teacher=" << teacher.id << " completed="
              << completed << '/' << nSeeds << " quarantined=" << nSeeds - completed
              << " rows=" << rows << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, "combattransitiongen", nSeeds, completed,
                            nSeeds - completed, g_trainingHealthFailures.load(),
                            rows, seedOffset, sims, asc);
}

// Outcome-blind audit of the frozen whole-combat surrogate's deployment
// distribution. One multi-action OOC decision is reservoir-sampled per source
// trajectory before any sibling combat outcome is observed. Every sibling
// retains the sampled GameContext RNG streams (matched hidden future), advances
// to its next real battle, and uses the unchanged external combat action path.
static std::string runCounterfactualSurrogateAuditSeed(std::uint64_t seed, int sims, int asc,
                                                        const WholeCombatTeacher &teacher) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent; agent.simulationCountBase=sims; agent.rng=std::default_random_engine(seed);
    std::default_random_engine reservoir(seed*2862933555777941757ULL+97);
    PathHistory path, sampledPath; t_curPath=&path;
    std::unique_ptr<GameContext> sampled; std::vector<search::GameAction> sampledActions;
    int sampledDecision=-1, eligible=0, decisionIdx=0; std::uint32_t sampledChosen=UINT32_MAX;
    using RT=search::GameAction::RewardsActionType;
    while(gc.outcome==GameOutcome::UNDECIDED){path.update(gc);if(gc.screenState==ScreenState::BATTLE){agent.simulationCountBase=fightSims(gc,sims);BattleContext bc{};agent.playoutBattle(gc,bc);if(!trainingRunValid(bc.outcome!=Outcome::UNDECIDED)){search::g_onGameActionExecute={};t_curPath=nullptr;return{};}bc.exitBattle(gc);continue;}
        const auto actions=search::GameAction::getAllActionsInState(gc);bool replace=false;
        if(actions.size()>=2){++eligible;replace=std::uniform_int_distribution<int>(1,eligible)(reservoir)==1;if(replace){sampled=std::make_unique<GameContext>(detachedCounterfactualCopy(gc));sampledPath=path;sampledActions=actions;sampledDecision=decisionIdx;}++decisionIdx;}
        std::uint32_t executed=UINT32_MAX;search::g_onGameActionExecute=[&](std::uint32_t bits,const GameContext *target){if(target==&gc&&executed==UINT32_MAX)executed=bits;};
        if(gc.screenState==ScreenState::MAP_SCREEN&&gc.curMapNodeY<14)search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        else if(gc.screenState==ScreenState::REWARDS){auto&r=gc.info.rewardsContainer;if(r.goldRewardCount>0)search::GameAction(RT::GOLD,0).execute(gc);else if(r.relicCount>0)search::GameAction(RT::RELIC,0).execute(gc);else if(r.potionCount>0)search::GameAction(RT::POTION,0).execute(gc);else if(g_collectKeys&&r.emeraldKey)search::GameAction(RT::KEY,0).execute(gc);else if(g_collectKeys&&r.sapphireKey)search::GameAction(RT::KEY,0).execute(gc);else if(r.cardRewardCount==0)search::GameAction(RT::SKIP).execute(gc);else evalCardRewardPolicy(gc);}
        else agent.stepOutOfCombatPolicy(gc);
        search::g_onGameActionExecute={};if(replace){sampledChosen=executed;if(executed!=UINT32_MAX&&std::none_of(sampledActions.begin(),sampledActions.end(),[&](const auto&a){return a.bits==executed;})){search::GameAction chosen(executed);if(chosen.isValidAction(*sampled))sampledActions.push_back(chosen);}}
    }
    std::ostringstream out;if(sampled){const std::string legal=joinLegalActions(sampledActions,*sampled);for(int a=0;a<(int)sampledActions.size();++a){GameContext branch=detachedCounterfactualCopy(*sampled);sampledActions[a].execute(branch);const std::uint64_t branchSeed=seed^(0x9e3779b97f4a7c15ULL*(std::uint64_t)(sampledDecision+31));bool reached=advanceOocToNextBattle(branch,sims,branchSeed,sampledPath),valid=reached;std::string reason=reached?"":"no_next_combat",feature;int won=0,endHp=0,startHp=0,startMax=0,endMax=0;std::string encounter="INVALID",room="INVALID";
            int battleAct=0,battleFloor=0;if(reached){battleAct=branch.act;battleFloor=branch.floorNum;BattleContext bc{};int hooks=0;search::g_onCombatDecision=[&](const BattleContext&s){if(hooks++==0){feature=combatFeatureRow(s);startHp=s.player.curHp;startMax=s.player.maxHp;}};room=roomStrings[(int)branch.curRoom];search::ScumSearchAgent2 fight;fight.simulationCountBase=sims;fight.rng=std::default_random_engine(branchSeed);const int healthBefore=search::g_simHealthFailureCount;fight.playoutBattle(branch,bc);search::g_onCombatDecision=nullptr;encounter=monsterEncounterStrings[(int)bc.encounter];valid=hooks>0&&search::isValidTrainingTerminal(bc.outcome!=Outcome::UNDECIDED,healthBefore,search::g_simHealthFailureCount,false);if(valid){won=bc.outcome==Outcome::PLAYER_VICTORY;bc.exitBattle(branch);endHp=won?branch.curHp:0;endMax=branch.maxHp;}else reason=hooks==0?"missing_first_decision_hook":"combat_health_failure";}
            out<<seed<<','<<sampledDecision<<','<<a<<','<<sampledActions[a].bits<<','<<csvQuote(actionDescription(sampledActions[a],*sampled))<<','<<(sampledActions[a].bits==sampledChosen)<<','<<(int)sampled->screenState<<','<<sampled->act<<','<<sampled->floorNum<<','<<battleAct<<','<<battleFloor<<','<<csvQuote(encounter)<<','<<csvQuote(room)<<','<<teacher.id<<','<<valid<<','<<csvQuote(reason);
            if(valid)out<<','<<feature;else for(int i=0;i<1766;++i)out<<",0";out<<','<<won<<','<<endHp<<','<<startHp<<','<<startMax<<','<<endMax<<','<<(startMax>0?(double)endHp/startMax:0.0)<<'\n';}}
    search::g_onCombatDecision=nullptr;t_curPath=nullptr;return out.str();
}

void counterfactualSurrogateAuditGen(int nSeeds,int sims,int asc,const std::string&outfile,
                                            std::uint64_t seedOffset,const std::string&teacherPath){
    trainingCampaignStart();search::g_richCombatFeatures=true;const auto teacher=loadWholeCombatTeacher(teacherPath,sims);std::ofstream f(outfile);if(!f)throw std::runtime_error("counterfactual surrogate audit: cannot open output");f<<"sourceSeed,decisionIdx,actionIdx,actionBits,action,chosen,screen,decisionAct,decisionFloor,battleAct,battleFloor,battleEncounter,roomClass,teacherId,valid,quarantineReason,"<<combatHeaderStr()<<",won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac\n";long long rows=0;int completed=0;
    for(int s=0;s<nSeeds;++s){const auto r=runCounterfactualSurrogateAuditSeed(seedOffset+s,sims,asc,teacher);rows+=std::count(r.begin(),r.end(),'\n');if(!r.empty())++completed;f<<r;f.flush();}
    std::cout<<"ooccfaudit teacher="<<teacher.id<<" completed="<<completed<<'/'<<nSeeds<<" quarantined="<<nSeeds-completed<<" rows="<<rows<<" -> "<<outfile<<'\n';writeTrainingProvenance(outfile,"ooccfaudit",nSeeds,completed,nSeeds-completed,g_trainingHealthFailures.load(),rows,seedOffset,sims,asc);
}
