// Whole-combat, combat-eval, combat-transition and counterfactual-surrogate dataset generators.
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"
#include "one_combat/combat_predictor_input.h"

#include <set>
#ifndef _WIN32
#include <sys/file.h>
#endif

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
    if (req("combat_backend")=="silver_uct") throw std::runtime_error("wholecombatgen: vendored silver_uct teachers were retired with the vendored Silver model (ADR-0022); freeze a native_silver teacher");
    if (req("combat_backend")!="native_silver" || req("rng_regime")!="project_fair") throw std::runtime_error("wholecombatgen: teacher backend/RNG mismatch");
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
    if (search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("wholecombatgen: production reuse cap mismatch with frozen 32k teacher");
    if (!t.contains("environment") || !t["environment"].is_object()) throw std::runtime_error("wholecombatgen: missing environment");
    for (const auto &[name, expected] : t["environment"].items()) {
        if (allowStaleProvenance && name == "STS_EXECUTABLE_GIT_SHA") continue;
        const char *actual=std::getenv(name.c_str());
        if (!expected.is_string() || !actual || expected.get<std::string>()!=actual)
            throw std::runtime_error("wholecombatgen: environment mismatch for "+name);
    }
    const std::map<std::string,std::string> required={{"STS_FAIR","1"},{"STS_SEARCHER3","0"},{"STS_SILVER_SEARCH","1"},{"STS_SILVER_EXACT_ROOT_BUDGETS","1"},{"STS_SILVER_REUSE_CAP_MODE","allocated"},{"STS_SILVER_ADAPTIVE","0"},{"STS_SILVER_VNET_LEAF_DIRECT","0"}};
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
        else if(gc.screenState==ScreenState::REWARDS){auto&r=gc.info.rewardsContainer;if(r.goldRewardCount>0)search::GameAction(RT::GOLD,0).execute(gc);else if(r.relicCount>0)search::GameAction(RT::RELIC,0).execute(gc);else if(r.potionCount>0&&gc.potionCount<gc.potionCapacity)search::GameAction(RT::POTION,0).execute(gc);else if(g_collectKeys&&r.emeraldKey)search::GameAction(RT::KEY,0).execute(gc);else if(g_collectKeys&&r.sapphireKey)search::GameAction(RT::KEY,0).execute(gc);else if(r.cardRewardCount==0)search::GameAction(RT::SKIP).execute(gc);else evalCardRewardPolicy(gc);}else agent.stepOutOfCombatPolicy(gc);
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
             {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"}})
        setenv(name, value, 1);

    search::installNativeSilverBackend();
    const std::filesystem::path stem = std::filesystem::temp_directory_path()
        / ("sts_legacy_teacher_compat_" + trainingExecutableGitSha()
           + "_" + std::to_string(search::nativeSilverReuseCap()));
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
            {"combat_backend", "native_silver"},
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
            }},
            {"model_artifacts", {{{"role", "combat_value_or_leaf"},
                                   {"path", leafPath}, {"sha256", fileSha256(leafPath)}}}},
        };
        std::ofstream out(teacherPath);
        if (!out) throw std::runtime_error("teacher compatibility: cannot create fixture");
        out << teacher.dump(2) << '\n';
        out.close();
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
                                const std::string &teacherPath,
                                bool allowStaleProvenance) {
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, allowStaleProvenance);
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
    std::cout << (allowStaleProvenance
                     ? "combattransitionlizardtargetcandidategen teacher="
                     : "combattransitiongen teacher=") << teacher.id << " completed="
              << completed << '/' << nSeeds << " quarantined=" << nSeeds - completed
              << " rows=" << rows << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, allowStaleProvenance
                                ? "combattransitionlizardtargetcandidategen"
                                : "combattransitiongen", nSeeds, completed,
                            nSeeds - completed, g_trainingHealthFailures.load(),
                            rows, seedOffset, sims, asc);
}



// Active Lizard Tail shadow and paired counterfactual collection modes.
static std::string runActiveLizardTransitionGenSeed(
    std::uint64_t seed, int sims, int asc, const WholeCombatTeacher &teacher,
    nlohmann::json &interventionRows) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 sourceAgent;
    sourceAgent.simulationCountBase = sims;
    sourceAgent.rng = std::default_random_engine(seed);
    PathHistory path;
    t_curPath = &path;
    std::ostringstream out;
    int fightIdx = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            const int battleAct = gc.act;
            const int battleFloor = gc.floorNum;
            const Room battleRoom = gc.curRoom;
            const int battleEncounter = static_cast<int>(gc.info.encounter);

            // Mark of the Bloom already disables both Fairy and Lizard revival;
            // it is covered by the ordinary exact/copy-through path.
            if (!gc.hasRelic(RelicId::MARK_OF_THE_BLOOM)) {
                const std::string sourceBefore = one_combat::combatTransitionFingerprint(gc);
                GameContext shadow = detachedCounterfactualCopy(gc);
                if (!shadow.hasRelic(RelicId::LIZARD_TAIL))
                    shadow.obtainRelic(RelicId::LIZARD_TAIL);
                shadow.relics.getRelicValueRef(RelicId::LIZARD_TAIL) = 1;
                if (!shadow.hasRelic(RelicId::LIZARD_TAIL) ||
                    shadow.relics.getRelicValue(RelicId::LIZARD_TAIL) != 1)
                    throw std::runtime_error("active Lizard shadow intervention failed");
                const GameContext shadowPre = detachedCounterfactualCopy(shadow);

                const double shadowPotionKeepValue = potionKeepValue(shadow);
                const auto predictorInput = one_combat::combatPredictorInputJson(
                    one_combat::captureCombatPredictorInput(
                        shadow, static_cast<MonsterEncounter>(battleEncounter),
                        shadowPotionKeepValue));
                std::optional<one_combat::CombatTransitionRecord> record;
                int rawCaptureCount = 0;
                search::ScumSearchAgent2 shadowAgent;
                shadowAgent.simulationCountBase = sims;
                shadowAgent.rng = std::default_random_engine(seed);
                BattleContext shadowBattle;
                {
                    one_combat::CombatTransitionRawObserverScope scope(
                        [&](const BattleContext &ended, GameContext &raw) {
                            ++rawCaptureCount;
                            if (rawCaptureCount == 1)
                                record = one_combat::captureCombatTransition(shadowPre, ended, raw);
                        });
                    shadowAgent.playoutBattle(shadow, shadowBattle);
                    const bool decided = shadowBattle.outcome != Outcome::UNDECIDED;
                    const bool valid = trainingRunValid(decided);
                    shadowBattle.exitBattle(shadow);
                    auto row = combatTransitionRowJson(
                        seed, fightIdx, battleAct, battleFloor, battleRoom,
                        battleEncounter, teacher.id, valid, decided, rawCaptureCount,
                        record, predictorInput);
                    out << row.dump() << '\n';
                    interventionRows.push_back({{"sourceSeed", seed},
                                                {"fightIdx", fightIdx},
                                                {"activeLizard", true}});
                }
                if (one_combat::combatTransitionFingerprint(gc) != sourceBefore)
                    throw std::runtime_error("active Lizard shadow mutated source GameContext");
            }

            // Continue the untouched source trajectory with its own teacher
            // search object and original relic state.
            BattleContext sourceBattle;
            sourceAgent.playoutBattle(gc, sourceBattle);
            const bool sourceRunValid = trainingRunValid(
                sourceBattle.outcome != Outcome::UNDECIDED);
            sourceBattle.exitBattle(gc);
            if (!sourceRunValid) {
                t_curPath = nullptr;
                return {};
            }
            ++fightIdx;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0) search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0 && gc.potionCount < gc.potionCapacity)
                search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else evalCardRewardPolicy(gc);
        } else {
            sourceAgent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static nlohmann::json runActiveLizardPairSeed(
    std::uint64_t seed, int sims, int asc, const WholeCombatTeacher &teacher,
    const nlohmann::json &target, nlohmann::json &pairMeta) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 sourceAgent;
    sourceAgent.simulationCountBase = sims;
    sourceAgent.rng = std::default_random_engine(seed);
    PathHistory path;
    PathHistory selectedPath;
    t_curPath = &path;
    int fightIdx = 0;
    int selectedFightIdx = -1;
    int selectedAct = 0;
    int selectedFloor = 0;
    Room selectedRoom = Room::NONE;
    int selectedEncounter = 0;
    std::uint64_t selectedEligibleOrdinal = 0;
    std::uint64_t eligibleBattles = 0;
    std::optional<GameContext> selectedPre;
    const int targetFightIdx = target.at("fightIdx").get<int>();
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            if (!gc.hasRelic(RelicId::MARK_OF_THE_BLOOM) &&
                !gc.hasRelic(RelicId::LIZARD_TAIL)) {
                ++eligibleBattles;
                if (fightIdx == targetFightIdx) {
                    selectedPre = detachedCounterfactualCopy(gc);
                    selectedPath = path;
                    selectedEligibleOrdinal = eligibleBattles;
                    selectedFightIdx = fightIdx;
                    selectedAct = gc.act;
                    selectedFloor = gc.floorNum;
                    selectedRoom = gc.curRoom;
                    selectedEncounter = static_cast<int>(gc.info.encounter);
                }
            }

            // Continue the untouched source trajectory. The selected fight
            // index was fixed from a separate pre-outcome risk-scoring pass.
            BattleContext sourceBattle;
            sourceAgent.playoutBattle(gc, sourceBattle);
            const bool sourceValid = trainingRunValid(
                sourceBattle.outcome != Outcome::UNDECIDED);
            sourceBattle.exitBattle(gc);
            if (!sourceValid) {
                t_curPath = nullptr;
                return nlohmann::json::object();
            }
            ++fightIdx;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0) search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0 && gc.potionCount < gc.potionCapacity)
                search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else evalCardRewardPolicy(gc);
        } else {
            sourceAgent.stepOutOfCombatPolicy(gc);
        }
    }
    if (selectedPre) {
        t_curPath = &selectedPath;
        const std::string sourceBefore = one_combat::combatTransitionFingerprint(*selectedPre);
        GameContext noTail = detachedCounterfactualCopy(*selectedPre);
        GameContext activeTail = detachedCounterfactualCopy(noTail);
        activeTail.obtainRelic(RelicId::LIZARD_TAIL);
        activeTail.relics.getRelicValueRef(RelicId::LIZARD_TAIL) = 1;
        GameContext normalizedActive = detachedCounterfactualCopy(activeTail);
        normalizedActive.relics.remove(RelicId::LIZARD_TAIL);
        const std::string sourceState = one_combat::combatTransitionFingerprint(noTail);
        if (one_combat::combatTransitionFingerprint(normalizedActive) != sourceState)
            throw std::runtime_error("Lizard pair branches differ beyond the injected relic");

        auto runBranch = [&](GameContext &branch) {
            const GameContext pre = detachedCounterfactualCopy(branch);
            const double branchPotionKeepValue = potionKeepValue(branch);
            const auto predictorInput = one_combat::combatPredictorInputJson(
                one_combat::captureCombatPredictorInput(
                    branch, static_cast<MonsterEncounter>(selectedEncounter),
                    branchPotionKeepValue));
            std::optional<one_combat::CombatTransitionRecord> record;
            int rawCaptureCount = 0;
            search::ScumSearchAgent2 branchAgent;
            branchAgent.simulationCountBase = sims;
            branchAgent.rng = std::default_random_engine(seed);
            branchAgent.recordActions = true;
            BattleContext battle;
            {
                one_combat::CombatTransitionRawObserverScope scope(
                    [&](const BattleContext &ended, GameContext &raw) {
                        ++rawCaptureCount;
                        if (rawCaptureCount == 1)
                            record = one_combat::captureCombatTransition(pre, ended, raw);
                    });
                branchAgent.playoutBattle(branch, battle);
                const bool decided = battle.outcome != Outcome::UNDECIDED;
                const bool valid = trainingRunValid(decided);
                battle.exitBattle(branch);
                auto row = combatTransitionRowJson(
                    seed, selectedFightIdx, selectedAct, selectedFloor, selectedRoom,
                    selectedEncounter, teacher.id, valid, decided,
                    rawCaptureCount, record, predictorInput);
                nlohmann::json actionTrace = nlohmann::json::array();
                for (const int bits : branchAgent.gameActionHistory)
                    actionTrace.push_back(static_cast<std::uint32_t>(bits));
                row["silverActionTraceBits"] = std::move(actionTrace);
                row["silverFirstActionBits"] = branchAgent.gameActionHistory.empty()
                    ? nlohmann::json(nullptr)
                    : nlohmann::json(static_cast<std::uint32_t>(branchAgent.gameActionHistory.front()));
                return row;
            }
        };

        const nlohmann::json noTailRow = runBranch(noTail);
        const nlohmann::json activeTailRow = runBranch(activeTail);
        if (noTailRow["predictorInput"] != target.at("predictorInput"))
            throw std::runtime_error("targeted pair pre-state differs from risk-scored candidate");
        if (noTailRow["transition"]["pre"] != target.at("preState"))
            throw std::runtime_error("targeted pair hidden pre-state differs from risk-scored candidate");
        if (one_combat::combatTransitionFingerprint(*selectedPre) != sourceBefore)
            throw std::runtime_error("paired Lizard shadows mutated selected source GameContext");
        pairMeta = {
            {"sourceSeed", seed}, {"fightIdx", selectedFightIdx},
            {"act", selectedAct}, {"floor", selectedFloor},
            {"roomClass", noTailRow["roomClass"]},
            {"encounter", selectedEncounter},
            {"eligibleBattlesInSource", eligibleBattles},
            {"selectedEligibleOrdinal", selectedEligibleOrdinal},
            {"targetRiskBand", target.at("riskBand")},
            {"targetPDeath", target.at("pDeath")},
            {"sourceStateFingerprint", sourceState},
            {"noTailOutcome", noTailRow["transition"]["combatOutcome"]},
            {"activeTailOutcome", activeTailRow["transition"]["combatOutcome"]},
            {"activeTailPostData", [&]() {
                const auto &relics = activeTailRow["transition"]["post"]["relics"];
                for (const auto &relic : relics)
                    if (relic["id"] == static_cast<int>(RelicId::LIZARD_TAIL))
                        return relic["data"];
                throw std::runtime_error("paired active row omitted RAW Lizard post-state");
            }()}
        };
        t_curPath = nullptr;
        return {{"noTail", noTailRow}, {"activeTail", activeTailRow}};
    }
    t_curPath = nullptr;
    return nlohmann::json::object();
}

static void installDirectSnapshotPostBattleAction(GameContext &gc) {
    // Direct snapshots restore persistent precombat fields, not the transient
    // callback installed by initFromSave. A won branch still needs the normal
    // post-battle continuation when BattleContext::exitBattle calls
    // regainControl() after RAW capture.
    gc.regainControlAction = [](GameContext &context) { context.afterBattle(); };
}

static nlohmann::json runActiveLizardPairFromSnapshot(
    std::uint64_t seed, int sims, int asc, const WholeCombatTeacher &teacher,
    const nlohmann::json &target, nlohmann::json &pairMeta) {
    trainingRunStart();
    const auto &frozenInput = target.at("predictorInput");
    const auto &globals = frozenInput.at("globals");
    const int act = globals.at("act").get<int>();
    const int floor = globals.at("floor").get<int>();
    const auto encounter = static_cast<MonsterEncounter>(globals.at("encounter").get<int>());
    const auto room = static_cast<Room>(globals.at("roomClass").get<int>());
    const auto lastRoom = static_cast<Room>(globals.at("lastRoom").get<int>());
    if (globals.at("characterClass").get<int>() != static_cast<int>(CharacterClass::IRONCLAD)
        || globals.at("ascension").get<int>() != asc
        || globals.at("isBurningElite").get<bool>())
        throw std::runtime_error("direct snapshot replay requires a non-burning Ironclad target at the requested ascension");

    GameContext source(CharacterClass::IRONCLAD, seed, asc);
    source.act = act;
    source.floorNum = floor;
    source.curRoom = room;
    source.lastRoom = lastRoom;
    source.info.encounter = encounter;
    source.screenState = ScreenState::BATTLE;
    source.outcome = GameOutcome::UNDECIDED;
    source.skipBattles = false;
    source.curMapNodeX = 0;
    source.curMapNodeY = 0;
    source.map = std::make_shared<Map>(Map::fromSeed(seed, asc, act, false));
    source.map->burningEliteX = -1;
    source.map->burningEliteY = -1;
    source.map->burningEliteBuff = -1;
    one_combat::applyCombatTransitionState(
        source, one_combat::combatTransitionStateFromJson(target.at("preState")));
    installDirectSnapshotPostBattleAction(source);
    const double frozenPotionKeep = globals.at("potionKeepValue").get<double>();
    const auto reproducedInput = one_combat::combatPredictorInputJson(
        one_combat::captureCombatPredictorInput(source, encounter, frozenPotionKeep));
    if (reproducedInput != frozenInput)
        throw std::runtime_error("direct snapshot replay did not reproduce the archived predictor input");
    const auto sourceBefore = one_combat::combatTransitionFingerprint(source);
    if (sourceBefore != target.at("preState").dump())
        throw std::runtime_error("direct snapshot replay did not reproduce the archived persistent state");

    PathHistory selectedPath;
    t_curPath = &selectedPath;
    GameContext noTail = detachedCounterfactualCopy(source);
    GameContext activeTail = detachedCounterfactualCopy(noTail);
    activeTail.obtainRelic(RelicId::LIZARD_TAIL);
    activeTail.relics.getRelicValueRef(RelicId::LIZARD_TAIL) = 1;
    GameContext normalizedActive = detachedCounterfactualCopy(activeTail);
    normalizedActive.relics.remove(RelicId::LIZARD_TAIL);
    if (one_combat::combatTransitionFingerprint(normalizedActive) != sourceBefore)
        throw std::runtime_error("direct Lizard pair differs beyond the injected relic");

    auto runBranch = [&](GameContext &branch) {
        const GameContext pre = detachedCounterfactualCopy(branch);
        const auto predictorInput = one_combat::combatPredictorInputJson(
            one_combat::captureCombatPredictorInput(
                branch, static_cast<MonsterEncounter>(globals.at("encounter").get<int>()),
                frozenPotionKeep));
        std::optional<one_combat::CombatTransitionRecord> record;
        int rawCaptureCount = 0;
        search::ScumSearchAgent2 branchAgent;
        branchAgent.simulationCountBase = sims;
        branchAgent.rng = std::default_random_engine(seed);
        branchAgent.recordActions = true;
        BattleContext battle;
        {
            one_combat::CombatTransitionRawObserverScope scope(
                [&](const BattleContext &ended, GameContext &raw) {
                    ++rawCaptureCount;
                    if (rawCaptureCount == 1)
                        record = one_combat::captureCombatTransition(pre, ended, raw);
                });
            branchAgent.playoutBattle(branch, battle);
            const bool decided = battle.outcome != Outcome::UNDECIDED;
            const bool valid = trainingRunValid(decided);
            battle.exitBattle(branch);
            auto row = combatTransitionRowJson(
                seed, target.at("fightIdx").get<int>(), act, floor, room,
                static_cast<int>(encounter),
                teacher.id, valid, decided, rawCaptureCount, record, predictorInput);
            nlohmann::json actionTrace = nlohmann::json::array();
            for (const int bits : branchAgent.gameActionHistory)
                actionTrace.push_back(static_cast<std::uint32_t>(bits));
            row["silverActionTraceBits"] = std::move(actionTrace);
            row["silverFirstActionBits"] = branchAgent.gameActionHistory.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json(static_cast<std::uint32_t>(branchAgent.gameActionHistory.front()));
            return row;
        }
    };

    const auto noTailRow = runBranch(noTail);
    const auto activeTailRow = runBranch(activeTail);
    if (noTailRow["predictorInput"] != frozenInput)
        throw std::runtime_error("direct replay ordinary predictor input differs from the archived target");
    if (noTailRow["transition"]["pre"] != target.at("preState"))
        throw std::runtime_error("direct replay ordinary hidden pre-state differs from the archived target");
    if (one_combat::combatTransitionFingerprint(source) != sourceBefore)
        throw std::runtime_error("direct paired branches mutated the archived source snapshot");

    const auto &activeRelics = activeTailRow["transition"]["post"]["relics"];
    int activeTailPostData = -1;
    for (const auto &relic : activeRelics)
        if (relic["id"] == static_cast<int>(RelicId::LIZARD_TAIL))
            activeTailPostData = relic["data"];
    if (activeTailPostData < 0)
        throw std::runtime_error("direct paired active row omitted the raw Lizard post-state");
    pairMeta = nlohmann::json::object();
    pairMeta["sourceSeed"] = seed;
    pairMeta["fightIdx"] = target.at("fightIdx");
    pairMeta["act"] = act;
    pairMeta["floor"] = floor;
    pairMeta["roomClass"] = noTailRow["roomClass"];
    pairMeta["encounter"] = globals.at("encounter");
    pairMeta["eligibleBattlesInSource"] = 0;
    pairMeta["selectedEligibleOrdinal"] = 0;
    pairMeta["replayMode"] = "direct_archived_snapshot";
    pairMeta["targetRiskBand"] = target.at("riskBand");
    pairMeta["targetPDeath"] = target.at("pDeath");
    pairMeta["sourceStateFingerprint"] = sourceBefore;
    pairMeta["noTailOutcome"] = noTailRow["transition"]["combatOutcome"];
    pairMeta["activeTailOutcome"] = activeTailRow["transition"]["combatOutcome"];
    pairMeta["activeTailPostData"] = activeTailPostData;
    t_curPath = nullptr;
    return nlohmann::json{{"noTail", noTailRow}, {"activeTail", activeTailRow}};
}

void activeLizardPairTransitionGen(
    int nSeeds, int sims, int asc, const std::string &outfile,
    const std::string &targetPath, const std::string &teacherPath,
    const std::string &baselineSha, const std::string &collectorSha) {
    if (nSeeds < 1 || nSeeds > 320)
        throw std::runtime_error("targeted Lizard pilot requires 1..320 pairs");
    if (nSeeds > 128) {
#ifndef _WIN32
        char hostname[256]{};
        const char *researchContext = std::getenv("STS_GCP_RESEARCH_CONTEXT");
        const bool designatedResearchRun =
            researchContext != nullptr && std::string(researchContext) == "sts-test"
            && gethostname(hostname, sizeof(hostname) - 1) == 0
            && std::string(hostname) == "sts-test"
            && std::filesystem::current_path() == "/home/philippherrmann/sts_sweep";
#else
        const bool designatedResearchRun = false;
#endif
        if (!designatedResearchRun)
            throw std::runtime_error("Lizard pair runs above 128 sources require the designated sts-test GCP research context");
    }
    if (sims != 10000)
        throw std::runtime_error("paired Lizard pilot requires exact-10k Silver");
    auto validSha = [](const std::string &s) {
        return s.size() == 40 && std::all_of(s.begin(), s.end(), [](unsigned char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        });
    };
    if (!validSha(baselineSha) || !validSha(collectorSha))
        throw std::runtime_error("paired Lizard pilot requires full baseline and collector SHAs");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, true);
    const auto targetSpec = nlohmann::json::parse(std::ifstream(targetPath));
    const bool directSnapshotReplay = targetSpec.value("schema", std::string{})
        == "lizard_tail_direct_snapshot_replay_plan_v1";
    nlohmann::json selection;
    std::filesystem::path selectionPath;
    std::vector<nlohmann::json> replayTargets;
    nlohmann::json excludedTargets = nlohmann::json::array();
    if (directSnapshotReplay) {
        if (targetSpec.value("replayMode", std::string{}) != "persistent_snapshot_direct"
            || !targetSpec.contains("archivedTargetSelection")
            || !targetSpec.at("archivedTargetSelection").is_object()
            || !targetSpec.contains("excludedBurningEliteTargets")
            || !targetSpec.at("excludedBurningEliteTargets").is_array())
            throw std::runtime_error("invalid direct snapshot replay plan");
        if (targetSpec.value("baselineGitSha", std::string{}) != baselineSha
            || targetSpec.value("collectorGitSha", std::string{}) != collectorSha
            || targetSpec.value("collectorExecutableSha256", std::string{})
                != fileSha256(g_mainBinaryPath))
            throw std::runtime_error("direct replay plan collector or baseline provenance mismatch");
        if (!targetSpec.contains("nativeTeacherManifest")
            || !targetSpec.at("nativeTeacherManifest").is_object())
            throw std::runtime_error("direct replay plan is missing native teacher provenance");
        const auto planDirectory = std::filesystem::path(targetPath).parent_path();
        auto resolvePlanPath = [&](const nlohmann::json &artifact) {
            std::filesystem::path path = artifact.at("path").get<std::string>();
            if (path.is_relative()) path = planDirectory / path;
            return std::filesystem::weakly_canonical(path);
        };
        const auto plannedTeacherPath = resolvePlanPath(targetSpec.at("nativeTeacherManifest"));
        if (plannedTeacherPath != std::filesystem::weakly_canonical(teacherPath)
            || fileSha256(plannedTeacherPath.string())
                != targetSpec.at("nativeTeacherManifest").at("sha256").get<std::string>()
            || targetSpec.at("nativeTeacherManifest").value("identity", std::string{}) != teacher.id
            || teacher.specification.value("git_sha", std::string{}) != collectorSha
            || teacher.specification.value("executable_sha256", std::string{})
                != fileSha256(g_mainBinaryPath))
            throw std::runtime_error("direct replay plan native teacher provenance mismatch");
        selectionPath = targetSpec.at("archivedTargetSelection").at("path").get<std::string>();
        if (selectionPath.is_relative())
            selectionPath = planDirectory / selectionPath;
        selectionPath = std::filesystem::weakly_canonical(selectionPath);
        if (!std::filesystem::is_regular_file(selectionPath)
            || fileSha256(selectionPath.string()) != targetSpec.at("archivedTargetSelection").at("sha256").get<std::string>())
            throw std::runtime_error("direct replay plan does not resolve to its pinned archived target selection");
        selection = nlohmann::json::parse(std::ifstream(selectionPath));
        if (selection.value("schema", std::string{}) != "lizard_tail_risk_target_selection_v1"
            || !selection.contains("targets") || !selection.at("targets").is_array())
            throw std::runtime_error("direct replay plan points to an invalid archived target selection");

        static const std::array<std::pair<long long, int>, 9> expectedExclusions = {{
            {4201016, 12}, {4201026, 5}, {4201030, 12}, {4201031, 20},
            {4201055, 20}, {4201070, 4}, {4201089, 16}, {4201103, 14},
            {4201113, 6}
        }};
        std::set<std::pair<long long, int>> excluded;
        for (const auto &item : targetSpec.at("excludedBurningEliteTargets")) {
            if (!item.is_object() || item.size() != 2 || !item.contains("sourceSeed")
                || !item.contains("fightIdx"))
                throw std::runtime_error("direct replay plan has malformed excluded target identity");
            excluded.emplace(item.at("sourceSeed").get<long long>(), item.at("fightIdx").get<int>());
        }
        const std::set<std::pair<long long, int>> expected(expectedExclusions.begin(), expectedExclusions.end());
        if (excluded != expected || excluded.size() != targetSpec.at("excludedBurningEliteTargets").size())
            throw std::runtime_error("direct replay plan burning-elite exclusions differ from the preregistered target set");
        for (const auto &target : selection.at("targets")) {
            const auto identity = std::make_pair(target.at("sourceSeed").get<long long>(),
                                                 target.at("fightIdx").get<int>());
            const bool burning = target.at("predictorInput").at("globals").at("isBurningElite").get<bool>();
            if (excluded.count(identity)) {
                if (!burning) throw std::runtime_error("direct replay exclusion is not an archived burning-elite target");
                excludedTargets.push_back({{"sourceSeed", identity.first},
                                           {"fightIdx", identity.second}});
            } else {
                if (burning) throw std::runtime_error("direct replay found an unregistered burning-elite target");
                replayTargets.push_back(target);
            }
        }
        if (excluded.size() != expectedExclusions.size()
            || excludedTargets.size() != expectedExclusions.size()
            || replayTargets.size() != static_cast<std::size_t>(nSeeds)
            || selection.at("targets").size() != replayTargets.size() + excludedTargets.size())
            throw std::runtime_error("direct replay plan does not partition the archived targets exactly");
    } else {
        selectionPath = std::filesystem::weakly_canonical(targetPath);
        selection = targetSpec;
        if (!selection.contains("targets") || !selection.at("targets").is_array())
            throw std::runtime_error("targeted Lizard pilot selection lacks targets");
        replayTargets = selection.at("targets").get<std::vector<nlohmann::json>>();
    }
    if (selection.value("schema", std::string{}) != "lizard_tail_risk_target_selection_v1" ||
        replayTargets.size() != static_cast<std::size_t>(nSeeds))
        throw std::runtime_error("targeted Lizard pilot selection schema/count mismatch");
    if (!selection.contains("stateSelection") || !selection["stateSelection"].is_string() ||
        selection["stateSelection"].get<std::string>().empty())
        throw std::runtime_error("targeted Lizard pilot requires a frozen state-selection label");
    const std::string stateSelection = directSnapshotReplay
        ? "direct_archived_snapshot_replay_nonburning_subset_v1"
        : selection["stateSelection"].get<std::string>();
    const long long seedOffset = replayTargets.front().at("sourceSeed").get<long long>();
    std::vector<long long> targetSeeds;
    targetSeeds.reserve(nSeeds);
    for (const auto &target : replayTargets)
        targetSeeds.push_back(target.at("sourceSeed").get<long long>());
    if (!std::is_sorted(targetSeeds.begin(), targetSeeds.end()) ||
        std::adjacent_find(targetSeeds.begin(), targetSeeds.end()) != targetSeeds.end())
        throw std::runtime_error("target selection source seeds must be unique and ascending");
    if (directSnapshotReplay) {
        std::vector<long long> plannedSeeds;
        for (const auto &source : targetSpec.at("sourceSelection").at("replaySourceSeeds"))
            plannedSeeds.push_back(source.get<long long>());
        if (plannedSeeds != targetSeeds)
            throw std::runtime_error("direct replay source list differs from the preregistered plan");
    }
    std::vector<nlohmann::json> pairRows(nSeeds);
    std::vector<int> completedByTarget(nSeeds, 0);
    std::vector<std::string> errors(nSeeds);
    std::filesystem::path checkpointDirectory;
    std::string directPlanSha;
    std::string teacherManifestSha;
    std::string producerExecutableSha;
    int resumedPairCount = 0;
#ifndef _WIN32
    struct CheckpointRunLock {
        int descriptor = -1;
        explicit CheckpointRunLock(const std::filesystem::path &path) {
            descriptor = ::open(path.c_str(), O_CREAT | O_RDWR | O_CLOEXEC, 0600);
            if (descriptor < 0)
                throw std::runtime_error("cannot open direct replay lock: " + path.string());
            if (::flock(descriptor, LOCK_EX | LOCK_NB) != 0) {
                const int savedError = errno;
                ::close(descriptor);
                descriptor = -1;
                throw std::runtime_error("another direct replay collector holds lock "
                                         + path.string() + ": " + std::strerror(savedError));
            }
        }
        ~CheckpointRunLock() {
            if (descriptor >= 0) {
                ::flock(descriptor, LOCK_UN);
                ::close(descriptor);
            }
        }
    };
    std::unique_ptr<CheckpointRunLock> checkpointRunLock;
#endif
    auto writeTextFile = [](const std::filesystem::path &path, const std::string &text) {
        std::ofstream file(path, std::ios::binary | std::ios::trunc);
        if (!file) throw std::runtime_error("cannot open temporary output: " + path.string());
        file.write(text.data(), static_cast<std::streamsize>(text.size()));
        file.flush();
        if (!file) throw std::runtime_error("cannot flush temporary output: " + path.string());
        file.close();
        if (!file) throw std::runtime_error("cannot close temporary output: " + path.string());
#ifndef _WIN32
        const int descriptor = ::open(path.c_str(), O_RDONLY);
        if (descriptor < 0)
            throw std::runtime_error("cannot open temporary output for sync: " + path.string());
        const int syncResult = ::fsync(descriptor);
        const int closeResult = ::close(descriptor);
        if (syncResult != 0 || closeResult != 0)
            throw std::runtime_error("cannot durably sync temporary output: " + path.string());
#endif
    };
    auto renameCompletedFile = [](const std::filesystem::path &temporary,
                                  const std::filesystem::path &destination) {
        std::error_code error;
        std::filesystem::rename(temporary, destination, error);
        if (error)
            throw std::runtime_error("atomic rename failed for " + destination.string()
                                     + ": " + error.message());
#if defined(__linux__)
        auto parent = destination.parent_path();
        if (parent.empty()) parent = ".";
        const int directoryDescriptor = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY);
        if (directoryDescriptor < 0)
            throw std::runtime_error("cannot open output directory for sync: " + parent.string());
        const int syncResult = ::fsync(directoryDescriptor);
        const int closeResult = ::close(directoryDescriptor);
        if (syncResult != 0 || closeResult != 0)
            throw std::runtime_error("cannot durably sync output directory: " + parent.string());
#endif
    };
    auto retainOrCreateFinalFile = [&](const std::filesystem::path &temporary,
                                       const std::filesystem::path &destination) {
        if (std::filesystem::exists(destination)) {
            if (fileSha256(temporary.string()) != fileSha256(destination.string())) {
                std::error_code ignored;
                std::filesystem::remove(temporary, ignored);
                throw std::runtime_error("refusing to overwrite different completed output: "
                                         + destination.string());
            }
            std::error_code ignored;
            std::filesystem::remove(temporary, ignored);
            return;
        }
        renameCompletedFile(temporary, destination);
    };
    auto checkpointPathFor = [&](int index) {
        const long long sourceSeed = targetSeeds.at(index);
        const int fightIdx = replayTargets.at(index).at("fightIdx").get<int>();
        return checkpointDirectory / ("source_" + std::to_string(sourceSeed)
                                      + "_fight_" + std::to_string(fightIdx) + ".json");
    };
    auto validateCheckpointRow = [&](const nlohmann::json &row, int index) {
        const auto &target = replayTargets.at(index);
        const long long sourceSeed = targetSeeds.at(index);
        const int fightIdx = target.at("fightIdx").get<int>();
        if (!row.is_object() || !row.contains("pair") || !row.contains("noTail")
            || !row.contains("activeTail") || !row.at("pair").is_object())
            throw std::runtime_error("checkpoint pair row has an invalid shape");
        const auto &pairMeta = row.at("pair");
        if (pairMeta.value("sourceSeed", std::numeric_limits<long long>::min()) != sourceSeed
            || pairMeta.value("fightIdx", std::numeric_limits<int>::min()) != fightIdx
            || pairMeta.value("replayMode", std::string{}) != "direct_archived_snapshot"
            || pairMeta.value("sourceStateFingerprint", std::string{})
                != target.at("preState").dump())
            throw std::runtime_error("checkpoint target identity or archived state mismatch");
        const auto &noTailRow = row.at("noTail");
        const auto &activeTailRow = row.at("activeTail");
        for (const auto *armRow : {&noTailRow, &activeTailRow})
            if (!armRow->is_object()
                || armRow->value("sourceSeed", std::numeric_limits<long long>::min()) != sourceSeed
                || armRow->value("fightIdx", std::numeric_limits<int>::min()) != fightIdx
                || !armRow->contains("predictorInput")
                || !armRow->contains("transition"))
                throw std::runtime_error("checkpoint arm identity or predictor input missing");
        if (noTailRow.at("predictorInput") != target.at("predictorInput"))
            throw std::runtime_error("checkpoint no-Tail predictor input differs from archived target");
        auto strippedActiveInput = activeTailRow.at("predictorInput");
        if (!strippedActiveInput.is_object() || !strippedActiveInput.contains("relics")
            || !strippedActiveInput.at("relics").is_array())
            throw std::runtime_error("checkpoint active-Tail predictor input has an invalid shape");
        nlohmann::json activeRelics = nlohmann::json::array();
        int injectedTailCount = 0;
        for (const auto &relic : strippedActiveInput.at("relics")) {
            if (relic.value("relicId", -1) == static_cast<int>(RelicId::LIZARD_TAIL)) {
                if (relic.value("data", -1) != 1)
                    throw std::runtime_error("checkpoint active-Tail predictor input has the wrong Tail data");
                ++injectedTailCount;
            } else {
                activeRelics.push_back(relic);
            }
        }
        if (injectedTailCount != 1)
            throw std::runtime_error("checkpoint active-Tail predictor input lacks exactly one injected Tail");
        strippedActiveInput["relics"] = std::move(activeRelics);
        if (strippedActiveInput != target.at("predictorInput"))
            throw std::runtime_error("checkpoint active-Tail predictor input differs beyond injected Tail");
        const auto &noTailTransition = noTailRow.at("transition");
        if (noTailTransition.is_object()
            && noTailTransition.at("pre") != target.at("preState"))
            throw std::runtime_error("checkpoint no-Tail pre-state differs from archived snapshot");
    };

    if (directSnapshotReplay) {
        directPlanSha = fileSha256(targetPath);
        teacherManifestSha = fileSha256(teacherPath);
        producerExecutableSha = fileSha256(g_mainBinaryPath);
        checkpointDirectory = std::filesystem::path(outfile + ".checkpoints");
        std::filesystem::create_directories(checkpointDirectory);
#ifndef _WIN32
        checkpointRunLock = std::make_unique<CheckpointRunLock>(
            checkpointDirectory / ".collector.lock");
#endif
        for (int s = 0; s < nSeeds; ++s) {
            const auto checkpointPath = checkpointPathFor(s);
            if (!std::filesystem::exists(checkpointPath)) continue;
            std::ifstream checkpointFile(checkpointPath, std::ios::binary);
            if (!checkpointFile)
                throw std::runtime_error("cannot read pair checkpoint: " + checkpointPath.string());
            const auto checkpoint = nlohmann::json::parse(checkpointFile);
            if (checkpoint.value("schema", std::string{})
                    != "lizard_direct_snapshot_pair_checkpoint_v1"
                || checkpoint.value("planSha256", std::string{}) != directPlanSha
                || checkpoint.value("teacherManifestSha256", std::string{}) != teacherManifestSha
                || checkpoint.value("collectorGitSha", std::string{}) != collectorSha
                || checkpoint.value("producerExecutableSha256", std::string{})
                    != producerExecutableSha
                || checkpoint.value("simulationBudget", -1) != sims
                || checkpoint.value("ascension", -1) != asc
                || checkpoint.value("sourceSeed", std::numeric_limits<long long>::min())
                    != targetSeeds.at(s)
                || checkpoint.value("fightIdx", std::numeric_limits<int>::min())
                    != replayTargets.at(s).at("fightIdx").get<int>()
                || !checkpoint.contains("pairRow"))
                throw std::runtime_error("pair checkpoint provenance mismatch: "
                                         + checkpointPath.string());
            const auto &row = checkpoint.at("pairRow");
            validateCheckpointRow(row, s);
            const auto payloadPath = std::filesystem::path(checkpointPath.string() + ".verify.tmp");
            writeTextFile(payloadPath, row.dump());
            const auto payloadSha = fileSha256(payloadPath.string());
            std::error_code ignored;
            std::filesystem::remove(payloadPath, ignored);
            if (checkpoint.value("pairRowSha256", std::string{}) != payloadSha)
                throw std::runtime_error("pair checkpoint payload checksum mismatch: "
                                         + checkpointPath.string());
            pairRows[s] = row;
            completedByTarget[s] = 1;
            ++resumedPairCount;
        }
        std::cout << "lizard direct-snapshot resume loaded=" << resumedPairCount
                  << '/' << nSeeds << " checkpoint_directory="
                  << checkpointDirectory.string() << std::endl;
    }
    std::atomic<int> completedPairCount{resumedPairCount};
    const auto collectionStart = std::chrono::steady_clock::now();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        if (completedByTarget[s]) continue;
#ifdef _OPENMP
        const int workerCount = omp_get_num_threads();
#else
        const int workerCount = 1;
#endif
        const auto pairStart = std::chrono::steady_clock::now();
        try {
            const auto &target = replayTargets[s];
            const long long sourceSeed = targetSeeds.at(s);
            nlohmann::json pairMeta;
            const nlohmann::json pair = directSnapshotReplay
                ? runActiveLizardPairFromSnapshot(sourceSeed, sims, asc, teacher, target, pairMeta)
                : runActiveLizardPairSeed(sourceSeed, sims, asc, teacher, target, pairMeta);
            if (pair.contains("noTail") && pair.contains("activeTail")) {
                pairRows[s] = nlohmann::json({{"pair", pairMeta}, {"noTail", pair["noTail"]},
                                              {"activeTail", pair["activeTail"]}});
                if (directSnapshotReplay) {
                    validateCheckpointRow(pairRows[s], s);
                    const auto checkpointPath = checkpointPathFor(s);
                    const auto payloadPath = std::filesystem::path(checkpointPath.string()
                                                                   + ".payload.tmp");
                    const std::string pairRowText = pairRows[s].dump();
                    writeTextFile(payloadPath, pairRowText);
                    const auto pairRowSha = fileSha256(payloadPath.string());
                    const auto checkpoint = nlohmann::json({
                        {"schema", "lizard_direct_snapshot_pair_checkpoint_v1"},
                        {"planSha256", directPlanSha},
                        {"teacherManifestSha256", teacherManifestSha},
                        {"collectorGitSha", collectorSha},
                        {"producerExecutableSha256", producerExecutableSha},
                        {"simulationBudget", sims}, {"ascension", asc},
                        {"sourceSeed", sourceSeed},
                        {"fightIdx", target.at("fightIdx")},
                        {"pairRowSha256", pairRowSha}, {"pairRow", pairRows[s]}
                    });
                    const auto temporaryCheckpointPath = std::filesystem::path(
                        checkpointPath.string() + ".tmp");
                    writeTextFile(temporaryCheckpointPath, checkpoint.dump(2) + "\n");
                    renameCompletedFile(temporaryCheckpointPath, checkpointPath);
                    std::error_code ignored;
                    std::filesystem::remove(payloadPath, ignored);
                }
                completedByTarget[s] = 1;
                if (directSnapshotReplay) {
                    const int completed = completedPairCount.fetch_add(1) + 1;
                    const auto pairElapsed = std::chrono::duration_cast<std::chrono::seconds>(
                        std::chrono::steady_clock::now() - pairStart).count();
                    const auto totalElapsed = std::chrono::duration_cast<std::chrono::seconds>(
                        std::chrono::steady_clock::now() - collectionStart).count();
                    #pragma omp critical(lizard_pair_progress_log)
                    {
                        std::cout << "lizard pair completed=" << completed << '/' << nSeeds
                                  << " source=" << sourceSeed
                                  << " fight=" << target.at("fightIdx")
                                  << " pair_elapsed_s=" << pairElapsed
                                  << " total_elapsed_s=" << totalElapsed
                                  << " omp_threads=" << workerCount
                                  << " checkpoint=" << checkpointPathFor(s).string()
                                  << std::endl;
                    }
                }
            } else {
                errors[s] = "selected fight not found or source trajectory incomplete";
            }
        } catch (const std::exception &error) {
            errors[s] = error.what();
            #pragma omp critical(lizard_pair_progress_log)
            {
                std::cout << "lizard pair failed source=" << targetSeeds.at(s)
                          << " error=" << errors[s] << std::endl;
            }
        }
    }
    for (int s = 0; s < nSeeds; ++s) {
        if (!errors[s].empty())
            throw std::runtime_error("targeted Lizard pair failed for source "
                                     + std::to_string(targetSeeds[s]) + ": " + errors[s]);
    }
    long long pairs = 0;
    if (directSnapshotReplay) {
        if (completedPairCount.load() != nSeeds)
            throw std::runtime_error("direct snapshot replay ended without all pair checkpoints");
        const auto outputTemporary = std::filesystem::path(outfile + ".assembling.tmp");
        std::ofstream f(outputTemporary, std::ios::binary | std::ios::trunc);
        if (!f) throw std::runtime_error("paired Lizard pilot: cannot open assembled output");
        for (int s = 0; s < nSeeds; ++s) {
            if (!completedByTarget[s])
                throw std::runtime_error("direct snapshot replay is missing a completed target checkpoint");
            f << pairRows[s].dump() << '\n';
            ++pairs;
        }
        f.flush();
        if (!f) throw std::runtime_error("paired Lizard pilot: cannot flush assembled output");
        f.close();
        if (!f) throw std::runtime_error("paired Lizard pilot: cannot close assembled output");
        retainOrCreateFinalFile(outputTemporary, outfile);
    } else {
        std::ofstream f(outfile);
        if (!f) throw std::runtime_error("paired Lizard pilot: cannot open output");
        for (int s = 0; s < nSeeds; ++s) {
            if (!completedByTarget[s]) continue;
            f << pairRows[s].dump() << '\n';
            ++pairs;
        }
        f.close();
    }
    const int completed = static_cast<int>(pairs);
    if (!directSnapshotReplay) producerExecutableSha = fileSha256(g_mainBinaryPath);
    nlohmann::json manifest = {
        {"schema", directSnapshotReplay
             ? "lizard_tail_direct_snapshot_paired_transition_diagnostic_v1"
             : "lizard_tail_targeted_paired_transition_pilot_v1"},
        {"rowSchemaVersion", one_combat::COMBAT_TRANSITION_ROW_SCHEMA},
        {"predictorInputSchemaVersion", one_combat::CombatPredictorInputV1::SCHEMA},
        {"predictorInputFieldSchemaHash", one_combat::combatPredictorInputFieldSchemaHash()},
        {"format", "jsonl"}, {"producerGitSha", collectorSha},
        {"producerExecutableSha256", producerExecutableSha},
        {"baselineGitSha", baselineSha}, {"combatTeacher", teacher.specification},
        {"combatTeacherManifestSha256", fileSha256(teacherPath)},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}}},
        {"sourceSeeds", targetSeeds},
        {"targetSelection", {{"path", selectionPath.string()},
                               {"sha256", fileSha256(selectionPath.string())}}},
        {"jsonl", {{"path", std::filesystem::absolute(outfile).string()},
                     {"sha256", fileSha256(outfile)}}},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed},
                        {"quarantinedSeeds", nSeeds - completed}, {"pairs", pairs}}},
        {"protocol", {{"samePrecombatContext", true}, {"sameSilverSearchRngSeed", true},
                       {"ordinaryBranchLizard", "absent"},
                       {"interventionBranchLizard", "active_data_1"},
                       {"stateSelection", stateSelection},
                       {"markOfBloom", "eligible_states_excluded"},
                       {"sourceTrajectory", directSnapshotReplay
                            ? "not_replayed_direct_snapshot"
                            : "untouched_normal_policy"}}}
    };
    if (directSnapshotReplay) {
        manifest["directReplayPlan"] = {
            {"path", std::filesystem::absolute(targetPath).string()},
            {"sha256", fileSha256(targetPath)},
            {"mode", "persistent_snapshot_direct"},
            {"excludedBurningEliteTargets", std::move(excludedTargets)}
        };
        manifest["pairCheckpointing"] = {
            {"schema", "lizard_direct_snapshot_pair_checkpoint_v1"},
            {"directory", std::filesystem::absolute(checkpointDirectory).string()},
            {"atomicWritePerCompletedPair", true},
            {"exclusiveCollectorLock", true},
            {"resumeValidatesPlanTeacherCollectorAndRowChecksum", true}
        };
    }
    const std::string manifestPath = outfile + ".manifest.json";
    if (directSnapshotReplay) {
        const std::string manifestText = manifest.dump(2) + "\n";
        const auto manifestTemporary = std::filesystem::path(manifestPath + ".tmp");
        writeTextFile(manifestTemporary, manifestText);
        retainOrCreateFinalFile(manifestTemporary, manifestPath);
    } else {
        std::ofstream mf(manifestPath);
        if (!mf) throw std::runtime_error("paired Lizard pilot: cannot write manifest");
        mf << manifest.dump(2) << '\n';
    }
    std::cout << "combattransitionlizardpairgen teacher=" << teacher.id
              << " completed=" << completed << '/' << nSeeds << " pairs=" << pairs
              << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, "combattransitionlizardtargetpairgen", nSeeds,
                            completed, nSeeds - completed,
                            g_trainingHealthFailures.load(), pairs, seedOffset, sims, asc);
}

int activeLizardTransitionSelfTest() {
    GameContext source(CharacterClass::IRONCLAD, 920260923u, 0);
    source.screenState = ScreenState::BATTLE;
    source.curRoom = Room::MONSTER;
    source.info.encounter = MonsterEncounter::CULTIST;
    const std::string sourceFingerprint = one_combat::combatTransitionFingerprint(source);
    GameContext shadow = detachedCounterfactualCopy(source);
    shadow.obtainRelic(RelicId::LIZARD_TAIL);
    if (shadow.relics.getRelicValue(RelicId::LIZARD_TAIL) != 1 ||
        source.hasRelic(RelicId::LIZARD_TAIL) ||
        one_combat::combatTransitionFingerprint(source) != sourceFingerprint)
        throw std::runtime_error("active Lizard selftest: acquire/shadow isolation failed");

    GameContext restored(CharacterClass::IRONCLAD, 920260924u, 0);
    restored.screenState = ScreenState::BATTLE;
    restored.curRoom = Room::MONSTER;
    restored.info.encounter = MonsterEncounter::CULTIST;
    installDirectSnapshotPostBattleAction(restored);
    BattleContext restoredVictory;
    restoredVictory.init(restored, MonsterEncounter::CULTIST);
    restoredVictory.outcome = Outcome::PLAYER_VICTORY;
    restoredVictory.exitBattle(restored);
    if (restored.screenState != ScreenState::REWARDS)
        throw std::runtime_error("active Lizard selftest: direct snapshot victory continuation failed");

    GameContext fairy = detachedCounterfactualCopy(shadow);
    fairy.potions[0] = Potion::FAIRY_POTION;
    fairy.potionCount = 1;
    BattleContext fairyBattle;
    fairyBattle.init(fairy, MonsterEncounter::CULTIST);
    fairyBattle.player.curHp = 1;
    fairyBattle.player.wouldDie(fairyBattle);
    if (fairyBattle.player.curHp <= 0 ||
        fairyBattle.potions[0] != Potion::EMPTY_POTION_SLOT ||
        !fairyBattle.player.hasRelic<RelicId::LIZARD_TAIL>())
        throw std::runtime_error("active Lizard selftest: Fairy Potion precedence failed");

    GameContext lizardOnly = detachedCounterfactualCopy(shadow);
    BattleContext lizardBattle;
    lizardBattle.init(lizardOnly, MonsterEncounter::CULTIST);
    lizardBattle.player.curHp = 1;
    lizardBattle.player.wouldDie(lizardBattle);
    if (lizardBattle.player.curHp != std::max(1, lizardBattle.player.maxHp / 2) ||
        lizardBattle.player.hasRelic<RelicId::LIZARD_TAIL>())
        throw std::runtime_error("active Lizard selftest: native revival/consumption failed");

    GameContext bloom = detachedCounterfactualCopy(shadow);
    bloom.obtainRelic(RelicId::MARK_OF_THE_BLOOM);
    BattleContext bloomBattle;
    bloomBattle.init(bloom, MonsterEncounter::CULTIST);
    bloomBattle.player.curHp = 1;
    bloomBattle.player.wouldDie(bloomBattle);
    if (bloomBattle.player.curHp != 0 || bloomBattle.outcome != Outcome::PLAYER_LOSS ||
        !bloomBattle.player.hasRelic<RelicId::LIZARD_TAIL>())
        throw std::runtime_error("active Lizard selftest: Mark of the Bloom semantics failed");
    return 0;
}

void activeLizardCombatTransitionGen(
    int nSeeds, int sims, int asc, const std::string &outfile,
    long long seedOffset, const std::string &teacherPath,
    const std::string &baselineSha, const std::string &collectorSha) {
    if (sims != 10000)
        throw std::runtime_error("active Lizard collector requires exact-10k Silver");
    auto validSha = [](const std::string &s) {
        return s.size() == 40 && std::all_of(s.begin(), s.end(), [](unsigned char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        });
    };
    if (!validSha(baselineSha) || !validSha(collectorSha))
        throw std::runtime_error("active Lizard collector requires full baseline and collector SHAs");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, true);
    std::ofstream f(outfile);
    if (!f) throw std::runtime_error("active Lizard collector: cannot open output");
    std::vector<nlohmann::json> activeRows;
    long long rows = 0;
    int completed = 0;
    for (int s = 0; s < nSeeds; ++s) {
        nlohmann::json seedRows = nlohmann::json::array();
        const std::string generated = runActiveLizardTransitionGenSeed(
            seedOffset + s, sims, asc, teacher, seedRows);
        f << generated;
        f.flush();
        rows += std::count(generated.begin(), generated.end(), '\n');
        if (!generated.empty()) {
            activeRows.insert(activeRows.end(), seedRows.begin(), seedRows.end());
            ++completed;
        }
    }
    f.close();
    const auto producerExecutableSha = fileSha256(g_mainBinaryPath);
    nlohmann::json manifest = {
        {"schemaVersion", one_combat::CombatTransitionRecord::SCHEMA},
        {"rowSchemaVersion", one_combat::COMBAT_TRANSITION_ROW_SCHEMA},
        {"predictorInputSchemaVersion", one_combat::CombatPredictorInputV1::SCHEMA},
        {"predictorInputFieldSchemaHash", one_combat::combatPredictorInputFieldSchemaHash()},
        {"format", "jsonl"}, {"producerGitSha", collectorSha},
        {"producerExecutableSha256", producerExecutableSha},
        {"combatTeacher", teacher.specification},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}}},
        {"csv", {{"path", std::filesystem::absolute(outfile).string()},
                  {"sha256", fileSha256(outfile)}}},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed},
                        {"quarantinedSeeds", nSeeds - completed}, {"rows", rows}}},
        {"lizardIntervention", {{"schema", "active_lizard_shadow_intervention_v1"},
                                 {"activeLizard", true},
                                 {"baselineGitSha", baselineSha},
                                 {"collectorGitSha", collectorSha},
                                 {"collectorExecutableSha256", producerExecutableSha},
                                 {"teacherId", teacher.id},
                                 {"teacherManifestSha256", fileSha256(teacherPath)},
                                 {"teacherGitSha", teacher.specification.at("git_sha")},
                                 {"teacherExecutableSha256", teacher.specification.at("executable_sha256")},
                                 {"teacherModelArtifacts", teacher.specification.at("model_artifacts")},
                                 {"predictorInputFieldSchemaHash", one_combat::combatPredictorInputFieldSchemaHash()},
                                 {"sourceSeedStart", seedOffset},
                                 {"sourceSeedCount", nSeeds},
                                 {"activeLizardRows", activeRows},
                                 {"sourceTrajectory", "untouched_normal_policy"},
                                 {"markOfBloomRows", "excluded"}}}
    };
    const std::string manifestPath = outfile + ".manifest.json";
    std::ofstream mf(manifestPath);
    if (!mf) throw std::runtime_error("active Lizard collector: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "combattransitionlizardgen teacher=" << teacher.id << " completed="
              << completed << '/' << nSeeds << " quarantined=" << nSeeds - completed
              << " rows=" << rows << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, "combattransitionlizardgen", nSeeds, completed,
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
