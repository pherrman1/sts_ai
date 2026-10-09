// Whole-combat, combat-eval, combat-transition and counterfactual-surrogate dataset generators.
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"
#include "one_combat/combat_predictor_input.h"
#include "one_combat/combat_transition_runtime.h"
#include "ooc_strategic_tok_net.h"
#include "screen_leaf_s0.h"
#include "one_combat/ooc_native_fallback.h"

#include <regex>
#include <cstdio>
#include <iomanip>
#include <openssl/evp.h>
#include <set>
#ifndef _WIN32
#include <sys/file.h>
#include <unistd.h>
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
    nlohmann::json policy = {
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
    // Bind effective policy controls into teacher identity checks. The default
    // removal correction is included unless explicitly disabled.
    if (const int count = one_combat::nativeOocPublicFutureCount(); count > 0)
        policy["parameters"]["native_ooc_public_futures"] = count;
    if (one_combat::nativeOocShopDeckSizeFixEnabled())
        policy["flags"]["native_ooc_shop_deck_size_fix"] = true;
    if (sts::search::oocSkipOptionalRecallEnabled())
        policy["flags"]["skip_optional_recall"] = true;
    if (sts::search::oocSkipFullHpRestEnabled())
        policy["flags"]["skip_full_hp_rest"] = true;
    if (sts::search::oocRemoveLowObtainWeightEnabled())
        policy["flags"]["remove_low_obtain_weight"] = true;
    if (one_combat::nativeOocCardWinRankEnabled())
        policy["flags"]["native_ooc_card_win_rank"] = true;
    return policy;
}

WholeCombatTeacher loadWholeCombatTeacher(const std::string &path, int sims,
                                                 bool allowStaleProvenance,
                                                 bool requireOocPolicy,
                                                 bool allowLearnedStop) {
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
    const char *binaryObjective = std::getenv("STS_SILVER_FINAL_BOSS_BINARY");
    const bool binaryObjectiveEnabled = binaryObjective && std::string(binaryObjective) == "1";
    if (s.value("final_boss_binary", false) != binaryObjectiveEnabled)
        throw std::runtime_error("wholecombatgen: final-boss objective differs from teacher");
    // Budget policy: absent/"flat_exact" is the frozen exact-10k contract.
    // "learned_stop" (ADR-0026 production Silver) is accepted only by callers
    // that opt in; it pins the compiled stop model and threshold.
    const std::string budgetPolicy=s.value("budget_policy",std::string{"flat_exact"});
    const bool learnedStopTeacher=budgetPolicy=="learned_stop";
    if (!learnedStopTeacher && budgetPolicy!="flat_exact") throw std::runtime_error("wholecombatgen: unknown budget_policy "+budgetPolicy);
    if (learnedStopTeacher && !allowLearnedStop) throw std::runtime_error("wholecombatgen: this mode accepts only the frozen exact-10k teacher");
    if (s.value("simulation_budgets",std::vector<int>{})!=std::vector<int>{10000} || sims!=10000
        || s.value("exploration_parameter",-1.0)!=25.0 || s.value("exploration_parameter_chance",-1.0)!=25.0
        || s.value("chance_widening_c",-1.0)!=3.7028 || s.value("chance_widening_alpha",-1.0)!=0.52389
        || s.value("end_turn_widening_c",-1.0)!=3.7028 || s.value("end_turn_widening_alpha",-1.0)!=0.52389
        || s.value("reuse_cap_mode",std::string{})!="allocated" || s.value("reuse_cap",-1)!=32768
        || s.value("sequential_halving",true) || s.value("pruning",true) || s.value("learned_visit_puct",true)
        || s.value("direct_learned_leaf",true) || s.value("adaptive",true))
        throw std::runtime_error(learnedStopTeacher ? "wholecombatgen: not the learned-stop ordinary Silver contract"
                                                    : "wholecombatgen: not the frozen exact-10k ordinary Silver contract");
    if (learnedStopTeacher) {
        if (s.value("learned_stop_model",std::string{})!=search::nativeSilverStopModelId()
            || s.value("learned_stop_threshold",-1.0)!=search::nativeSilverLearnedStopThreshold())
            throw std::runtime_error("wholecombatgen: learned-stop model/threshold mismatch with the compiled stop model");
        if (!search::nativeSilverLearnedStopEnabled() || search::nativeSilverAdaptiveEnabled()
            || search::nativeSilverExactRootBudgets() || search::nativeSilverSearchesSingletonRoots()
            || search::nativeSilverLearnedStopBossFallback()
            || search::nativeSilverLearnedStopBossMax()!=0)
            throw std::runtime_error("wholecombatgen: effective Silver is not plain learned stopping");
    } else if (search::nativeSilverLearnedStopEnabled()) {
        throw std::runtime_error("wholecombatgen: exact-10k teacher with learned stopping enabled");
    }
    if (search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("wholecombatgen: production reuse cap mismatch with frozen 32k teacher");
    if (!t.contains("environment") || !t["environment"].is_object()) throw std::runtime_error("wholecombatgen: missing environment");
    for (const auto &[name, expected] : t["environment"].items()) {
        if (allowStaleProvenance && name == "STS_EXECUTABLE_GIT_SHA") continue;
        const char *actual=std::getenv(name.c_str());
        if (!expected.is_string() || !actual || expected.get<std::string>()!=actual)
            throw std::runtime_error("wholecombatgen: environment mismatch for "+name);
    }
    std::map<std::string,std::string> required={{"STS_FAIR","1"},{"STS_SEARCHER3","0"},{"STS_SILVER_SEARCH","1"},{"STS_SILVER_EXACT_ROOT_BUDGETS","1"},{"STS_SILVER_REUSE_CAP_MODE","allocated"},{"STS_SILVER_ADAPTIVE","0"},{"STS_SILVER_VNET_LEAF_DIRECT","0"}};
    if (learnedStopTeacher) { required["STS_SILVER_EXACT_ROOT_BUDGETS"]="0"; required["STS_SILVER_LEARNED_STOP"]="1"; }
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

struct VwinOption {
    std::string key;
    std::uint32_t primitiveBits = 0;
    bool mapPrimitive = false;
    std::optional<search::OocSemanticAction> semantic;
};

struct VwinDecisionSnapshot {
    std::string screen, screenContentsJson, features;
    std::vector<std::string> candidateKeys;
    bool supported = false, complete = false;
};

enum class VwinContinuation { NONE, CARD_REWARD_FALLBACK_DRAIN };

struct VwinSampledDecision {
    VwinContinuation continuation = VwinContinuation::NONE;
    int decisionIdx = -1;
    int fightIdx = 0;
    std::string type;
    std::string chosenKey;
    std::unique_ptr<GameContext> pre;
    PathHistory path;
    search::ScumSearchAgent2 agentAfter;
    OocPolicyThreadState policyAfter;
    std::vector<VwinOption> options;
    std::size_t sourceTraceIndex = 0;
};

struct VwinMapRow {
    std::string branchId;
    int deviationIdx = 0, rowIdx = 0, act = 0, floor = 0, mapX = 0, mapY = 0;
    std::string features;
};

struct VwinRawRow {
    std::string branchId;
    int deviationIdx = 0, rowIdx = 0, act = 0, floor = 0, mapX = 0, mapY = 0;
    std::string roomClass, encounter, features;
    int actBoss = 0, preHp = 0, preMaxHp = 0, prePotions = 0, preGold = 0;
    int postAfterBattleHp = -1;
};

struct VwinDecisionSinkRow {
    std::string branchId, screen, features, screenContentsJson, chosenKey;
    int deviationIdx = 0, rowIdx = 0, decisionIdx = 0, act = 0, floor = 0;
    std::vector<std::string> candidateKeys;
    bool supported = false, complete = false;
};

struct VwinDecisionRow {
    std::string branchId;
    int deviationIdx = 0, decisionIdx = 0, act = 0, floor = 0, screen = 0;
    std::string type, chosenKey, error;
    bool supported = false, complete = false;
    std::vector<std::string> candidateKeys;
};

struct VwinBossEntry {
    std::unique_ptr<GameContext> pre;
    PathHistory path;
    search::ScumSearchAgent2 agent;
    OocPolicyThreadState policy;
    int fightIdx = 0, act = 0, floor = 0, sourceWon = -1;
    int terminalHp = -1, postAfterBattleHp = -1, firstActionBits = -1;
    double signedOutcome = 0.0;
    bool labelValid = false, sourceTrajectoryValid = false;
    std::string encounter, roomClass;
};

struct VwinPendingDecision {
    std::size_t rowIndex = 0;
    std::string chosenKey;
    CardSelectScreenType selector = CardSelectScreenType::INVALID;
    std::vector<VwinOption> options;
    std::unique_ptr<GameContext> pre;
    PathHistory path;
    std::vector<std::uint32_t> observedPrimitiveBits;
};

struct VwinPendingSinkDecision {
    std::size_t rowIndex = 0, logIndex = 0;
    CardSelectScreenType selector = CardSelectScreenType::INVALID;
    std::unique_ptr<GameContext> pre;
    std::vector<VwinOption> options;
    std::vector<std::uint32_t> observedPrimitiveBits;
};

struct VwinCfTarget {
    int act = 0, floor = 0, decisionIdx = -1;
    std::string publicStateSha256;
    std::string preflightReceiptPath, preflightReceiptSha256;
    std::vector<std::string> optionKeys;
};

struct VwinCollector {
    std::uint64_t sourceSeed = 0;
    int samplesPerType = 0;
    std::string branchId = "source";
    int deviationIdx = 0;
    bool captureRefresh = false, captureBoss = false, allowSampling = false;
    bool captureAllCombatEntries = false;   // with captureBoss: every fight, not only bosses (#400)
    bool captureDecisionSink = false;
    bool cfOptionCapV2 = false;             // ooccfpilotgen GEN=2 option cap (see vwinCfLimitOptions)
    std::optional<VwinCfTarget> cfTarget;   // GEN=2 diagnostic: exact initial REST screen only
    int decisionIdx = 0, fightIdx = 0, mapRowIdx = 0, rawRowIdx = 0, decisionSinkRowIdx = 0;
    std::map<std::string, int> eligibleByType;
    std::map<std::string, std::mt19937_64> reservoirRng;
    std::map<std::string, std::vector<VwinSampledDecision>> sampled;
    std::vector<VwinMapRow> mapRows;
    std::vector<VwinRawRow> rawRows;
    std::vector<VwinDecisionRow> decisions;
    std::vector<VwinDecisionSinkRow> decisionSinkRows;
    nlohmann::json decisionSinkLog = nlohmann::json::array();
    std::optional<VwinPendingSinkDecision> pendingSinkAction;
    std::vector<VwinBossEntry> bossEntries;
    std::string combatRows;
    std::vector<std::string> trace;
    std::optional<VwinPendingDecision> pendingAction;
    int pendingRawIndex = -1;
    int rawCaptureCount = 0;
    int winCount = 0;
};

// Counterfactual pilot horizon: the first `bosses` boss fights after the branch
// (GEN=1), or the whole run (GEN=2, `fullRun`).
struct CfHorizon {
    int bosses = 1, bossesBeaten = 0;
    bool fullRun = false;
    bool reached = false, diedBeforeBoss = false;
    int bossWon = -1, hp = -1, maxHp = -1, act = -1, floor = -1, fights = 0;
    int finalWon = -1;                         // GEN=2 label: run won (1), lost (0)
    int firstBossWon = -1, firstBossHp = -1, firstBossMaxHp = -1, firstBossAct = -1;
    std::string afterFeatures;   // rich row right after the forced option
    // GEN=2: first MAP screen after the branch screen is finished.
    bool mapRecorded = false;
    int mapAct = -1, mapFloor = -1;
    std::string mapFeatures;
};

struct VwinBranchStart {
    const VwinSampledDecision *decision = nullptr;
    VwinOption option;
    std::string branchId;
    // Counterfactual pilot only: redraw hidden futures from this seed after the
    // forced option (before it with `redrawBeforeOption`, GEN=2), and stop at
    // the horizon. #334 sets neither.
    std::optional<std::uint64_t> futureSeed;
    CfHorizon *horizon = nullptr;
    bool redrawBeforeOption = false;
};

struct VwinArmResult {
    int won = -1, terminalHp = -1, postAfterBattleHp = -1, firstActionBits = -1, potionsAfter = -1;
    double signedOutcome = 0.0, cpuSeconds = 0.0;
    std::uint64_t simulations = 0, decisions = 0;
    std::int64_t lockStops = 0, modelStops = 0;
    bool valid = false;
    std::string outcome, quarantineReason;
};

static std::string vwinSha256(const std::string &text) {
    unsigned char digest[EVP_MAX_MD_SIZE]{};
    unsigned int size = 0;
    EVP_MD_CTX *raw = EVP_MD_CTX_new();
    if (!raw) throw std::runtime_error("vwin refresh: cannot allocate SHA256 context");
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(raw, EVP_MD_CTX_free);
    if (EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1
        || EVP_DigestUpdate(context.get(), text.data(), text.size()) != 1
        || EVP_DigestFinal_ex(context.get(), digest, &size) != 1 || size != 32)
        throw std::runtime_error("vwin refresh: SHA256 computation failed");
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < size; ++i) out << std::setw(2) << static_cast<unsigned>(digest[i]);
    return out.str();
}

static std::string vwinOptionKey(const search::OocSemanticAction &action) {
    return search::canonicalOocSemanticActionKey(action);
}

static std::string vwinMapOptionKey(std::uint32_t bits) {
    std::ostringstream out;
    out << "map:" << std::hex << std::setw(8) << std::setfill('0') << bits;
    return out.str();
}

static std::string vwinScreenDecisionType(const GameContext &gc) {
    if (gc.screenState == ScreenState::MAP_SCREEN) return "MAP";
    if (gc.screenState == ScreenState::EVENT_SCREEN)
        return gc.curEvent == Event::NEOW ? "NEOW" : "EVENT";
    if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) return "BOSS_RELIC";
    if (gc.screenState == ScreenState::TREASURE_ROOM) return "TREASURE";
    if (gc.curRoom == Room::REST || gc.screenState == ScreenState::REST_ROOM) return "REST";
    if (gc.curRoom == Room::SHOP || gc.screenState == ScreenState::SHOP_ROOM) return "SHOP";
    if (gc.screenState == ScreenState::CARD_SELECT) {
        if (gc.curRoom == Room::REST) return "REST";
        if (gc.curRoom == Room::SHOP) return "SHOP";
        return "OTHER_SELECTOR";
    }
    return "OTHER_SELECTOR";
}

static std::vector<VwinOption> vwinOptions(const GameContext &gc,
                                           bool &supported, bool &complete,
                                           std::string &error) {
    std::vector<VwinOption> result;
    if (gc.screenState == ScreenState::MAP_SCREEN) {
        supported = complete = true;
        for (const auto &action : search::GameAction::getAllActionsInState(gc))
            result.push_back({vwinMapOptionKey(action.bits), action.bits, true, std::nullopt});
        return result;
    }
    const auto enumeration = search::enumerateOocSemanticActions(gc);
    supported = enumeration.supported;
    complete = enumeration.complete;
    error = enumeration.error;
    for (const auto &action : enumeration.actions)
        result.push_back({vwinOptionKey(action), 0, false, action});
    return result;
}

static std::string vwinDecisionScreenName(const GameContext &gc) {
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN: return "event";
        case ScreenState::REWARDS: return "rewards";
        case ScreenState::BOSS_RELIC_REWARDS: return "boss_relic";
        case ScreenState::CARD_SELECT: return "selector";
        case ScreenState::TREASURE_ROOM: return "treasure";
        case ScreenState::REST_ROOM: return "rest";
        case ScreenState::SHOP_ROOM: return "shop";
        case ScreenState::MAP_SCREEN: return "map";
        default: return "other";
    }
}

static const char *vwinSelectorTypeName(CardSelectScreenType type) {
    switch (type) {
        case CardSelectScreenType::TRANSFORM: return "transform";
        case CardSelectScreenType::TRANSFORM_UPGRADE: return "transform_upgrade";
        case CardSelectScreenType::UPGRADE: return "upgrade";
        case CardSelectScreenType::REMOVE: return "remove";
        case CardSelectScreenType::DUPLICATE: return "duplicate";
        case CardSelectScreenType::OBTAIN: return "obtain";
        case CardSelectScreenType::BOTTLE: return "bottle";
        case CardSelectScreenType::BONFIRE_SPIRITS: return "bonfire_spirits";
        case CardSelectScreenType::INVALID: return "invalid";
    }
    return "invalid";
}

static nlohmann::json vwinCardContents(const Card &card) {
    return {{"id", static_cast<int>(card.id)},
            {"upgraded", card.isUpgraded()},
            {"misc", card.misc}};
}

static nlohmann::json vwinDecisionScreenContents(
        const GameContext &gc, const std::vector<VwinOption> &options) {
    nlohmann::json contents = {
        {"screen", vwinDecisionScreenName(gc)},
        {"screenState", static_cast<int>(gc.screenState)},
    };
    auto availableOptions = [&] {
        nlohmann::json result = nlohmann::json::array();
        for (const auto &option : options) {
            nlohmann::json item = {{"key", option.key}};
            if (option.semantic) {
                item["effect"] = static_cast<int>(option.semantic->effect);
                item["source"] = static_cast<int>(option.semantic->source);
            }
            result.push_back(std::move(item));
        }
        return result;
    };

    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN: {
            contents["eventId"] = static_cast<int>(gc.curEvent);
            contents["optionIds"] = nlohmann::json::array();
            for (const auto &action : search::GameAction::getAllActionsInState(gc))
                contents["optionIds"].push_back(action.getIdx1());
            if (gc.curEvent == Event::NEOW) {
                contents["neowOffers"] = nlohmann::json::array();
                for (const auto &offer : gc.info.neowRewards)
                    contents["neowOffers"].push_back({
                        {"bonusId", static_cast<int>(offer.r)},
                        {"drawbackId", static_cast<int>(offer.d)}
                    });
            }
            break;
        }
        case ScreenState::REWARDS: {
            const auto &rewards = gc.info.rewardsContainer;
            contents["gold"] = nlohmann::json::array();
            for (int i = 0; i < rewards.goldRewardCount; ++i)
                contents["gold"].push_back(rewards.gold[i]);
            contents["cardRewards"] = nlohmann::json::array();
            for (int group = 0; group < rewards.cardRewardCount; ++group) {
                nlohmann::json cards = nlohmann::json::array();
                for (const auto &card : rewards.cardRewards[group])
                    cards.push_back(vwinCardContents(card));
                contents["cardRewards"].push_back({
                    {"group", group}, {"cards", std::move(cards)}
                });
            }
            contents["relics"] = nlohmann::json::array();
            for (int i = 0; i < rewards.relicCount; ++i)
                contents["relics"].push_back(static_cast<int>(rewards.relics[i]));
            contents["potions"] = nlohmann::json::array();
            for (int i = 0; i < rewards.potionCount; ++i)
                contents["potions"].push_back(static_cast<int>(rewards.potions[i]));
            contents["emeraldKey"] = rewards.emeraldKey;
            contents["sapphireKey"] = rewards.sapphireKey;
            break;
        }
        case ScreenState::BOSS_RELIC_REWARDS:
            contents["relics"] = nlohmann::json::array();
            for (const auto relic : gc.info.bossRelics) {
                if (relic != RelicId::INVALID)
                    contents["relics"].push_back(static_cast<int>(relic));
            }
            break;
        case ScreenState::CARD_SELECT:
            contents["selectorType"] = vwinSelectorTypeName(gc.info.selectScreenType);
            contents["selectorTypeId"] = static_cast<int>(gc.info.selectScreenType);
            contents["requiredPicks"] = gc.info.toSelectCount;
            contents["completedPicks"] = gc.info.haveSelectedCards.size();
            contents["cards"] = nlohmann::json::array();
            for (const auto &card : gc.info.toSelectCards)
                contents["cards"].push_back({
                    {"deckIndex", card.deckIdx}, {"card", vwinCardContents(card.card)}
                });
            break;
        case ScreenState::TREASURE_ROOM:
            contents["chestSize"] = static_cast<int>(gc.info.chestSize);
            contents["availableOptions"] = availableOptions();
            break;
        case ScreenState::REST_ROOM:
            contents["availableOptions"] = availableOptions();
            break;
        case ScreenState::SHOP_ROOM: {
            const auto &shop = gc.info.shop;
            contents["cards"] = nlohmann::json::array();
            for (int i = 0; i < 7; ++i) {
                const int price = shop.cardPrice(i);
                contents["cards"].push_back({
                    {"slot", i},
                    {"id", price < 0 ? nlohmann::json(nullptr)
                                      : nlohmann::json(static_cast<int>(shop.cards[i].id))},
                    {"price", price},
                    {"card", price < 0 ? nlohmann::json(nullptr) : vwinCardContents(shop.cards[i])}
                });
            }
            contents["relics"] = nlohmann::json::array();
            for (int i = 0; i < 3; ++i) {
                const int price = shop.relicPrice(i);
                contents["relics"].push_back({
                    {"slot", i},
                    {"id", price < 0 ? nlohmann::json(nullptr)
                                      : nlohmann::json(static_cast<int>(shop.relics[i]))},
                    {"price", price}
                });
            }
            contents["potionSlots"] = nlohmann::json::array();
            for (int i = 0; i < 3; ++i) {
                const int price = shop.potionPrice(i);
                contents["potionSlots"].push_back({
                    {"slot", i},
                    {"id", price < 0 ? nlohmann::json(nullptr)
                                      : nlohmann::json(static_cast<int>(shop.potions[i]))},
                    {"price", price}
                });
            }
            contents["removeCost"] = shop.removeCost;
            contents["policyBuyableRelics"] = nlohmann::json::array();
            for (const auto &option : options) {
                if (!option.semantic
                    || option.semantic->effect != search::OocSemanticEffect::BUY_RELIC)
                    continue;
                const auto *target = std::get_if<search::OocShopTarget>(&option.semantic->target);
                const auto *relic = target ? std::get_if<RelicId>(&target->entity) : nullptr;
                if (!target || !relic) continue;
                contents["policyBuyableRelics"].push_back({
                    {"id", static_cast<int>(*relic)}, {"price", target->expectedPrice},
                    {"key", option.key}
                });
            }
            contents["ownedPotionCapacity"] = gc.potionCapacity;
            contents["ownedPotions"] = nlohmann::json::array();
            for (int i = 0; i < gc.potionCapacity && i < static_cast<int>(gc.potions.size()); ++i)
                contents["ownedPotions"].push_back(static_cast<int>(gc.potions[i]));
            break;
        }
        default:
            contents["availableOptions"] = availableOptions();
            break;
    }
    return contents;
}

static std::optional<VwinDecisionSnapshot> vwinMakeDecisionSnapshot(
        const GameContext &gc, const PathHistory &path,
        const std::vector<VwinOption> &options, bool supported, bool complete) {
    if (gc.screenState == ScreenState::MAP_SCREEN || options.size() < 2)
        return std::nullopt;
    VwinDecisionSnapshot snapshot;
    snapshot.screen = vwinDecisionScreenName(gc);
    snapshot.screenContentsJson = vwinDecisionScreenContents(gc, options).dump();
    snapshot.features = richRow(gc, path);
    snapshot.supported = supported;
    snapshot.complete = complete;
    for (const auto &option : options) snapshot.candidateKeys.push_back(option.key);
    std::sort(snapshot.candidateKeys.begin(), snapshot.candidateKeys.end());
    return snapshot;
}

nlohmann::json one_combat::screenLeafPublicContract(const sts::GameContext &gc) {
    bool supported = false, complete = false;
    std::string error;
    const auto options = vwinOptions(gc, supported, complete, error);
    if (!supported || !complete) throw std::runtime_error("incomplete restored DECISION: " + error);
    std::vector<std::string> keys;
    std::vector<std::string> replacementDiscards;
    for (const auto &option : options) keys.push_back(option.key);
    for (const auto &option : options)
        if (option.semantic && option.semantic->effect == search::OocSemanticEffect::DISCARD_POTION)
            replacementDiscards.push_back(option.key);
    std::sort(keys.begin(), keys.end());
    std::sort(replacementDiscards.begin(), replacementDiscards.end());
    return {{"screenContents", vwinDecisionScreenContents(gc, options)}, {"candidateKeys", keys},
            {"replacementDiscardKeys", replacementDiscards}};
}

static bool vwinIsCardRewardChoice(const VwinOption &option) {
    if (!option.semantic || option.semantic->source != search::OocSemanticSource::REWARDS)
        return false;
    using Effect = search::OocSemanticEffect;
    return option.semantic->effect == Effect::TAKE_CARD
        || option.semantic->effect == Effect::SKIP_CARD_REWARD
        || option.semantic->effect == Effect::SINGING_BOWL;
}

static std::string vwinDecisionType(const GameContext &gc,
                                    const std::vector<VwinOption> &options,
                                    const std::string &chosenKey,
                                    std::uint32_t chosenPrimitiveBits) {
    if (gc.screenState != ScreenState::REWARDS) return vwinScreenDecisionType(gc);
    const auto chosen = std::find_if(options.begin(), options.end(), [&](const auto &option) {
        return option.key == chosenKey;
    });
    if (chosen != options.end())
        return vwinIsCardRewardChoice(*chosen) ? "CARD_REWARD" : std::string{};
    if (search::GameAction(chosenPrimitiveBits).getRewardsActionType()
        == search::GameAction::RewardsActionType::CARD)
        return "CARD_REWARD";
    // Gold, potion, relic, key, and leave actions are deterministic pickups or
    // screen control. Keep them out of the card-reward sampling pool.
    return {};
}

static std::vector<VwinOption> vwinCardRewardGroupOptions(
        const std::vector<VwinOption> &options, const std::string &chosenKey) {
    const auto chosen = std::find_if(options.begin(), options.end(), [&](const auto &option) {
        return option.key == chosenKey;
    });
    if (chosen == options.end() || !vwinIsCardRewardChoice(*chosen)) return {};
    const auto *chosenTarget = std::get_if<search::OocRewardTarget>(&chosen->semantic->target);
    if (!chosenTarget) return {};

    std::vector<VwinOption> result;
    for (const auto &option : options) {
        if (!vwinIsCardRewardChoice(option)) continue;
        const auto *target = std::get_if<search::OocRewardTarget>(&option.semantic->target);
        if (target && target->cardGroup == chosenTarget->cardGroup
            && target->groupOccurrence == chosenTarget->groupOccurrence)
            result.push_back(option);
    }
    return result;
}

static std::vector<VwinOption> vwinLimitOptions(const std::vector<VwinOption> &options,
                                                const std::string &chosenKey,
                                                std::uint64_t seed, int decisionIdx) {
    if (options.size() <= 6) return options;
    std::vector<std::pair<std::string, VwinOption>> ranked;
    for (const auto &option : options) {
        if (option.key == chosenKey) continue;
        ranked.emplace_back(vwinSha256("vwin-option-cap-334-v1:" + std::to_string(seed)
            + ":" + std::to_string(decisionIdx) + ":" + option.key), option);
    }
    std::sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) {
        return a.first == b.first ? a.second.key < b.second.key : a.first < b.first;
    });
    std::vector<VwinOption> result;
    const auto chosen = std::find_if(options.begin(), options.end(), [&](const auto &option) {
        return option.key == chosenKey;
    });
    if (chosen == options.end()) return {};
    result.push_back(*chosen);
    for (std::size_t i = 0; i < 5 && i < ranked.size(); ++i) result.push_back(ranked[i].second);
    std::sort(result.begin(), result.end(), [](const auto &a, const auto &b) {
        return a.key < b.key;
    });
    return result;
}

// ooccfpilotgen GEN=2 option cap. Options that differ only in the deck
// position of an identical card (same id, misc, upgrade, bottle) are one
// option; the chosen key represents its class, otherwise the smallest key.
// The chosen option and every skip/leave option are always kept; the rest
// fill up to six by sha256 rank.
static std::string vwinCfCanonicalKey(const std::string &key) {
    static const std::regex occurrence("occurrence=[0-9]+");
    return std::regex_replace(key, occurrence, "occurrence=*");
}

static bool vwinCfAlwaysKeep(const VwinOption &option) {
    using Effect = search::OocSemanticEffect;
    if (!option.semantic) return false;
    const auto effect = option.semantic->effect;
    return effect == Effect::SKIP_CARD_REWARD || effect == Effect::SKIP_BOSS_RELIC
        || effect == Effect::LEAVE_SHOP || effect == Effect::LEAVE_CAMPFIRE
        || effect == Effect::LEAVE_REWARDS;
}

static std::vector<VwinOption> vwinCfLimitOptions(const std::vector<VwinOption> &options,
                                                  const std::string &chosenKey,
                                                  std::uint64_t seed, int decisionIdx) {
    std::map<std::string, VwinOption> classes;
    for (const auto &option : options) {
        const auto canonical = vwinCfCanonicalKey(option.key);
        auto found = classes.find(canonical);
        if (found == classes.end()) classes.emplace(canonical, option);
        else if (option.key == chosenKey
                 || (found->second.key != chosenKey && option.key < found->second.key))
            found->second = option;
    }
    std::vector<VwinOption> result;
    std::vector<std::pair<std::string, VwinOption>> ranked;
    for (const auto &[canonical, option] : classes) {
        if (option.key == chosenKey || vwinCfAlwaysKeep(option)) result.push_back(option);
        else ranked.emplace_back(vwinSha256("ooc-cf-option-cap-v2:" + std::to_string(seed)
            + ":" + std::to_string(decisionIdx) + ":" + canonical), option);
    }
    if (std::none_of(result.begin(), result.end(),
                     [&](const auto &option) { return option.key == chosenKey; }))
        return {};
    std::sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) {
        return a.first == b.first ? a.second.key < b.second.key : a.first < b.first;
    });
    for (std::size_t i = 0; i < ranked.size() && result.size() < 6; ++i)
        result.push_back(ranked[i].second);
    std::sort(result.begin(), result.end(), [](const auto &a, const auto &b) {
        return a.key < b.key;
    });
    return result;
}

static std::optional<std::size_t> vwinReservoirSlot(std::mt19937_64 &rng, int seen,
                                                     int capacity, std::size_t retained) {
    if (seen < 1 || capacity < 1)
        throw std::runtime_error("vwin refresh: invalid reservoir sampling state");
    if (retained < static_cast<std::size_t>(capacity)) return retained;
    const auto selected = std::uniform_int_distribution<int>(1, seen)(rng);
    if (selected > capacity) return std::nullopt;
    return static_cast<std::size_t>(selected - 1);
}

static void vwinMaybeSampleDecision(VwinCollector &capture, std::size_t rowIndex,
                                    const std::vector<VwinOption> &options,
                                    const std::string &chosenKey,
                                    const GameContext &pre, const PathHistory &path) {
    const auto &row = capture.decisions.at(rowIndex);
    if (!capture.allowSampling || !row.supported || !row.complete || options.size() < 2
        || chosenKey.empty()
        || std::none_of(options.begin(), options.end(), [&](const auto &option) {
               return option.key == chosenKey;
           })
        || capture.samplesPerType <= 0) return;
    if (capture.cfTarget) {
        const auto &target = *capture.cfTarget;
        if (row.type != "REST" || pre.screenState != ScreenState::REST_ROOM
            || pre.act != target.act || pre.floorNum != target.floor
            || (target.decisionIdx >= 0 && row.decisionIdx != target.decisionIdx)) return;
    }
    int &seen = capture.eligibleByType[row.type];
    ++seen;
    auto &reservoir = capture.sampled[row.type];
    std::optional<std::size_t> slot;
    if (capture.cfTarget) {
        if (seen != 1 || !reservoir.empty())
            throw std::runtime_error("ooc cf target: ambiguous repeated REST target");
        slot = 0;
    } else {
        auto rng = capture.reservoirRng.find(row.type);
        if (rng == capture.reservoirRng.end()) {
            const std::string identity = "vwin-refresh-334-v1:" + std::to_string(capture.sourceSeed)
                + ":" + row.type;
            const auto digest = vwinSha256(identity);
            const std::uint64_t state = std::stoull(digest.substr(0, 16), nullptr, 16);
            rng = capture.reservoirRng.emplace(row.type, std::mt19937_64(state)).first;
        }
        slot = vwinReservoirSlot(rng->second, seen, capture.samplesPerType, reservoir.size());
    }
    if (!slot) return;
    VwinSampledDecision sample;
    sample.decisionIdx = row.decisionIdx;
    sample.fightIdx = capture.fightIdx;
    sample.type = row.type;
    // Capture the live call site, before its fallback invocation unwinds.
    if (row.type == "CARD_REWARD" && one_combat::inCardRewardFallback())
        sample.continuation = VwinContinuation::CARD_REWARD_FALLBACK_DRAIN;
    sample.chosenKey = chosenKey;
    sample.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(pre));
    sample.path = path;
    sample.options = options;
    if (*slot == reservoir.size()) reservoir.push_back(std::move(sample));
    else reservoir[*slot] = std::move(sample);
}

static std::size_t vwinBeginDecision(VwinCollector &capture, const GameContext &gc,
                                     const PathHistory &path,
                                     const std::vector<VwinOption> &options,
                                     const std::string &decisionType,
                                     const std::string &chosenKey,
                                     bool supported, bool complete,
                                     const std::string &error,
                                     bool deferSampling = false) {
    VwinDecisionRow row;
    row.branchId = capture.branchId;
    row.deviationIdx = capture.deviationIdx;
    row.decisionIdx = capture.decisionIdx++;
    row.act = gc.act;
    row.floor = gc.floorNum;
    row.screen = static_cast<int>(gc.screenState);
    row.type = decisionType;
    row.supported = supported;
    row.complete = complete;
    row.error = error;
    row.chosenKey = chosenKey;
    for (const auto &option : options) row.candidateKeys.push_back(option.key);
    const std::size_t rowIndex = capture.decisions.size();
    capture.decisions.push_back(row);
    if (!deferSampling) vwinMaybeSampleDecision(capture, rowIndex, options, chosenKey, gc, path);
    return rowIndex;
}

static std::string vwinResolveObservedCompoundKey(
        const GameContext &pre, const std::vector<VwinOption> &options,
        const std::vector<std::uint32_t> &observedPrimitiveBits) {
    if (observedPrimitiveBits.size() < 2) return {};
    std::set<std::string> matches;
    auto previous = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = {};
    try {
        for (const auto &option : options) {
            if (!option.semantic) continue;
            auto replay = detachedCounterfactualCopy(pre);
            const auto result = search::executeOocSemanticAction(replay, *option.semantic);
            if (result.ok && result.executedPrimitiveBits == observedPrimitiveBits)
                matches.insert(option.key);
        }
    } catch (...) {
        search::g_onGameActionExecute = std::move(previous);
        throw;
    }
    search::g_onGameActionExecute = std::move(previous);
    return matches.size() == 1 ? *matches.begin() : std::string{};
}

static void vwinFinishDecision(VwinCollector &capture, VwinPendingDecision pending,
                               const search::ScumSearchAgent2 &agent,
                               const OocPolicyThreadState &policyState) {
    if (pending.rowIndex >= capture.decisions.size())
        throw std::runtime_error("vwin refresh: decision row index is out of range");
    auto &row = capture.decisions[pending.rowIndex];
    std::string chosenKey = pending.chosenKey;
    if (pending.selector != CardSelectScreenType::INVALID) {
        if (pending.pre)
            chosenKey = vwinResolveObservedCompoundKey(*pending.pre, pending.options,
                                                        pending.observedPrimitiveBits);
        if (chosenKey.empty() && row.error.empty())
            row.error = "compound_selector_semantic_binding_unresolved";
        if (!chosenKey.empty() && pending.pre)
            vwinMaybeSampleDecision(capture, pending.rowIndex, pending.options, chosenKey,
                                    *pending.pre, pending.path);
    }
    row.chosenKey = chosenKey;
    if (chosenKey.empty() && !row.error.empty()) row.error += ";chosen_option_unresolved";
    const auto found = capture.sampled.find(row.type);
    if (found != capture.sampled.end()) {
        for (auto &sample : found->second) {
            if (sample.decisionIdx != row.decisionIdx) continue;
            sample.chosenKey = chosenKey;
            // A targeted diagnostic validates the complete legal inventory
            // first, then keeps the baseline plus explicitly requested keys.
            if (!capture.cfTarget)
                sample.options = capture.cfOptionCapV2
                    ? vwinCfLimitOptions(sample.options, chosenKey, capture.sourceSeed, sample.decisionIdx)
                    : vwinLimitOptions(sample.options, chosenKey, capture.sourceSeed, sample.decisionIdx);
            sample.agentAfter = agent;
            sample.policyAfter = policyState;
            sample.sourceTraceIndex = capture.trace.size();
            break;
        }
    }
    capture.trace.push_back("D:" + std::to_string(row.decisionIdx) + ":" + chosenKey);
}

static std::string vwinResolveChosenKey(const GameContext &gc, std::uint32_t bits,
                                       const std::vector<std::string> &allowedKeys);

static bool vwinPendingAwaitsSelector(const VwinPendingDecision &pending,
                                      const GameContext &gc) {
    return pending.selector != CardSelectScreenType::INVALID
        && gc.screenState == ScreenState::CARD_SELECT
        && gc.info.selectScreenType == pending.selector;
}

static void vwinObserveDecisionScreen(VwinCollector &, const GameContext &,
                                      const PathHistory &, std::uint32_t, int);
static void vwinFinishDecisionSink(VwinCollector &, const GameContext *, bool = false);

static void vwinObservePolicyStep(VwinCollector &capture, GameContext &gc,
                                  PathHistory &path, search::ScumSearchAgent2 &agent,
                                  const std::function<void()> &step) {
    auto finishPendingDecision = [&] {
        if (!capture.pendingAction) return;
        auto pending = std::move(*capture.pendingAction);
        capture.pendingAction.reset();
        vwinFinishDecision(capture, std::move(pending), agent,
                           one_combat::captureOocPolicyThreadState());
    };

    auto previous = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = [&](std::uint32_t bits, const GameContext *target) {
        if (target == &gc) {
            path.update(gc);
            bool consumedCompoundSelector = false;
            if (capture.pendingAction
                && vwinPendingAwaitsSelector(*capture.pendingAction, gc)) {
                capture.pendingAction->observedPrimitiveBits.push_back(bits);
                vwinObserveDecisionScreen(capture, gc, path, bits, -1);
                consumedCompoundSelector = true;
            }
            if (!consumedCompoundSelector) {
                finishPendingDecision();
                bool supported = false, complete = false;
                std::string error;
                auto options = vwinOptions(gc, supported, complete, error);
                std::vector<std::string> keys;
                keys.reserve(options.size());
                for (const auto &option : options) keys.push_back(option.key);
                const auto selector = search::oocSemanticPrimitiveCompoundSelector(gc, bits);
                const auto chosenKey = selector == CardSelectScreenType::INVALID
                    ? vwinResolveChosenKey(gc, bits, keys) : std::string{};
                const auto decisionType = vwinDecisionType(gc, options, chosenKey, bits);
                vwinObserveDecisionScreen(capture, gc, path, bits,
                    decisionType.empty() ? -1 : capture.decisionIdx);
                if (gc.screenState != ScreenState::REWARDS || decisionType == "CARD_REWARD") {
                    if (decisionType == "CARD_REWARD" && !chosenKey.empty()) {
                        auto cardOptions = vwinCardRewardGroupOptions(options, chosenKey);
                        const bool chosenPresent = std::any_of(cardOptions.begin(), cardOptions.end(),
                            [&](const auto &option) { return option.key == chosenKey; });
                        if (chosenPresent) {
                            options = std::move(cardOptions);
                        } else {
                            supported = false;
                            complete = false;
                            if (error.empty()) error = "card_reward_group_binding_unresolved";
                        }
                    }
                    if ((!supported || !complete) && error.empty())
                        error = "semantic_option_enumeration_unsupported_or_incomplete";
                    else if (supported && complete && options.size() >= 2 && chosenKey.empty()
                             && selector == CardSelectScreenType::INVALID)
                        error = "chosen_primitive_binding_unresolved";
                    const auto rowIndex = vwinBeginDecision(capture, gc, path,
                        options, decisionType, chosenKey, supported, complete, error,
                        selector != CardSelectScreenType::INVALID);
                    if (gc.screenState == ScreenState::MAP_SCREEN) {
                        capture.mapRows.push_back({capture.branchId, capture.deviationIdx,
                            capture.mapRowIdx++, gc.act, gc.floorNum, gc.curMapNodeX,
                            gc.curMapNodeY, richRow(gc, path)});
                    }
                    VwinPendingDecision pending;
                    pending.rowIndex = rowIndex;
                    pending.chosenKey = chosenKey;
                    pending.selector = selector;
                    pending.observedPrimitiveBits.push_back(bits);
                    if (selector != CardSelectScreenType::INVALID) {
                        pending.options = std::move(options);
                        pending.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                        pending.path = path;
                    }
                    capture.pendingAction = std::move(pending);
                }
            }
        }
        if (previous) previous(bits, target);
    };
    try {
        step();
    } catch (...) {
        search::g_onGameActionExecute = std::move(previous);
        throw;
    }
    search::g_onGameActionExecute = std::move(previous);

    vwinFinishDecisionSink(capture, &gc);

    // A source action that opened its compound selector is only half of the
    // semantic decision. Keep it pending across policy steps until the target
    // is selected, or until policy moves to a different screen.
    if (!capture.pendingAction
        || !vwinPendingAwaitsSelector(*capture.pendingAction, gc))
        finishPendingDecision();
}

static void vwinRefreshRunPolicyStep(VwinCollector &capture, GameContext &gc,
                                     PathHistory &path, search::ScumSearchAgent2 &agent) {
    vwinObservePolicyStep(capture, gc, path, agent,
        [&] { runFullRunOocPolicyStep(gc, agent, false, true); });
}

static void vwinResumeContinuation(const VwinSampledDecision &decision,
                                   VwinCollector &capture, GameContext &gc,
                                   PathHistory &path, search::ScumSearchAgent2 &agent) {
    if (decision.continuation == VwinContinuation::CARD_REWARD_FALLBACK_DRAIN
        && gc.screenState == ScreenState::REWARDS
        && gc.info.rewardsContainer.cardRewardCount > 0) {
        // Every sibling resumes the sampled invocation before another V4 gate.
        vwinObservePolicyStep(capture, gc, path, agent,
            [&] { one_combat::serverCardRewardPolicy(gc); });
    }
}

static bool vwinSelectedDecision(const VwinCollector &capture, int decisionIdx) {
    for (const auto &[type, samples] : capture.sampled) {
        (void)type;
        if (std::any_of(samples.begin(), samples.end(), [&](const auto &sample) {
                return sample.decisionIdx == decisionIdx;
            })) return true;
    }
    return false;
}

static std::string vwinRunoutHeader() {
    return "sourceSeed,branchId,deviationIdx,finalOutcome,finalWon,finalFloor,finalHp,fightCount,"
           "trajectoryComplete,trajectoryValid,combatRows,invalidCombatRows,teacherId,"
           "simulatorHealthFailures,fatalFailure";
}

static std::string vwinCombatHeader() {
    return "sourceSeed,branchId,deviationIdx," + std::string("fightIdx,act,floor,roomClass,encounter,teacherId,")
        + richStateHeader() + "," + combatEvalLabelHeader();
}

static std::string vwinMapHeader() {
    return "sourceSeed,branchId,deviationIdx,rowIdx,act,floor,mapX,mapY,teacherId,"
        + richStateHeader();
}

static std::string vwinRawHeader() {
    return "sourceSeed,branchId,deviationIdx,rowIdx,act,floor,mapX,mapY,teacherId,"
        + richStateHeader() + ",roomClass,actBoss,encounter,preHp,preMaxHp,prePotions,preGold,postAfterBattleHp";
}

static std::string vwinDecisionHeader() {
    return "sourceSeed,branchId,deviationIdx,decisionIdx,type,act,floor,screen,optionCount,"
        "chosenKey,supported,complete,sampled,candidateKeysJson,error";
}

static std::string vwinDecisionSinkHeader() {
    return "sourceSeed,branchId,deviationIdx,rowIdx,decisionIdx,act,floor,screen,teacherId,"
        + richStateHeader() + ",screenContents,candidates,won";
}

static std::string vwinBranchHeader() {
    return "sourceSeed,decisionIdx,type,optionKey,chosen,branchId,won,finalFloor,finalHp,valid";
}

static std::string vwinResolveChosenKey(const GameContext &gc, std::uint32_t bits,
                                       const std::vector<std::string> &allowedKeys) {
    if (gc.screenState == ScreenState::MAP_SCREEN) {
        const auto key = vwinMapOptionKey(bits);
        return std::find(allowedKeys.begin(), allowedKeys.end(), key) != allowedKeys.end()
            ? key : std::string{};
    }
    const auto bindings = search::enumerateOocSemanticPrimitiveBindings(gc);
    if (!bindings.supported || !bindings.complete) return {};
    std::set<std::string> matches;
    for (const auto &binding : bindings.bindings) {
        if (binding.primitiveBits != bits) continue;
        const auto key = vwinOptionKey(binding.semantic);
        if (std::find(allowedKeys.begin(), allowedKeys.end(), key) != allowedKeys.end())
            matches.insert(key);
    }
    return matches.size() == 1 ? *matches.begin() : std::string{};
}

static void vwinFinishDecisionSink(VwinCollector &capture, const GameContext *gc,
                                   bool force) {
    if (!capture.captureDecisionSink || !capture.pendingSinkAction) return;
    const auto &waiting = *capture.pendingSinkAction;
    if (!force && gc && gc->screenState == ScreenState::CARD_SELECT
        && gc->info.selectScreenType == waiting.selector) return;
    auto pending = std::move(*capture.pendingSinkAction);
    capture.pendingSinkAction.reset();
    auto &row = capture.decisionSinkRows.at(pending.rowIndex);
    row.chosenKey = vwinResolveObservedCompoundKey(*pending.pre, pending.options,
                                                   pending.observedPrimitiveBits);
    if (row.chosenKey.empty()) {
        auto &log = capture.decisionSinkLog.at(pending.logIndex);
        log["rowIdx"] = -1;
        log["error"] = "compound_selector_semantic_binding_unresolved";
        // Selector rows may already follow the reserved parent row. Retain
        // those valid captures, closing the gap in their independent indices.
        capture.decisionSinkRows.erase(capture.decisionSinkRows.begin() + pending.rowIndex);
        for (std::size_t i = pending.rowIndex; i < capture.decisionSinkRows.size(); ++i)
            capture.decisionSinkRows[i].rowIdx = static_cast<int>(i);
        for (auto &entry : capture.decisionSinkLog) {
            const int idx = entry.at("rowIdx").get<int>();
            if (idx > static_cast<int>(pending.rowIndex)) entry["rowIdx"] = idx - 1;
        }
        --capture.decisionSinkRowIdx;
    }
}

static void vwinObserveDecisionScreen(VwinCollector &capture, const GameContext &gc,
                                      const PathHistory &path, std::uint32_t bits,
                                      int decisionIdx) {
    if (!capture.captureDecisionSink) return;
    vwinFinishDecisionSink(capture, &gc);
    if (capture.pendingSinkAction)
        capture.pendingSinkAction->observedPrimitiveBits.push_back(bits);
    if (gc.screenState == ScreenState::MAP_SCREEN) return;
    bool supported = false, complete = false;
    std::string error;
    const auto options = vwinOptions(gc, supported, complete, error);
    const auto logIndex = capture.decisionSinkLog.size();
    capture.decisionSinkLog.push_back({
        {"rowIdx", -1}, {"decisionIdx", decisionIdx},
        {"screen", vwinDecisionScreenName(gc)}, {"optionCount", options.size()},
        {"supported", supported}, {"complete", complete},
        {"error", supported && complete ? "" : "semantic_option_enumeration_unsupported_or_incomplete"},
        {"enumerationError", error}
    });
    // Partial enumerations cannot establish the real option count. Log their
    // support/error status even when zero or one candidates were returned.
    // Singleton screens need no chosen binding or feature snapshot.
    if (options.size() < 2 || !supported || !complete) return;
    const auto selector = search::oocSemanticPrimitiveCompoundSelector(gc, bits);
    std::vector<std::string> keys;
    for (const auto &option : options) keys.push_back(option.key);
    const auto chosenKey = selector == CardSelectScreenType::INVALID
        ? vwinResolveChosenKey(gc, bits, keys) : std::string{};
    if (selector == CardSelectScreenType::INVALID && chosenKey.empty()) {
        capture.decisionSinkLog[logIndex]["error"] = "chosen_primitive_binding_unresolved";
        return;
    }
    if (selector != CardSelectScreenType::INVALID && capture.pendingSinkAction) {
        capture.decisionSinkLog[logIndex]["error"] = "compound_selector_semantic_binding_unresolved";
        return;
    }
    auto snapshot = vwinMakeDecisionSnapshot(gc, path, options, supported, complete);
    if (!snapshot) return;
    VwinDecisionSinkRow row;
    row.branchId = capture.branchId;
    row.deviationIdx = capture.deviationIdx;
    row.rowIdx = capture.decisionSinkRowIdx++;
    capture.decisionSinkLog[logIndex]["rowIdx"] = row.rowIdx;
    row.decisionIdx = decisionIdx;
    row.act = gc.act;
    row.floor = gc.floorNum;
    row.screen = std::move(snapshot->screen);
    row.features = std::move(snapshot->features);
    row.screenContentsJson = std::move(snapshot->screenContentsJson);
    row.candidateKeys = std::move(snapshot->candidateKeys);
    row.supported = supported;
    row.complete = complete;
    row.chosenKey = chosenKey;
    if (selector != CardSelectScreenType::INVALID) {
        VwinPendingSinkDecision pending;
        pending.rowIndex = capture.decisionSinkRows.size();
        pending.logIndex = logIndex;
        pending.selector = selector;
        pending.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
        pending.options = options;
        pending.observedPrimitiveBits.push_back(bits);
        capture.pendingSinkAction = std::move(pending);
    }
    capture.decisionSinkRows.push_back(std::move(row));
}

// Semantic execution intentionally disables observers. Reconstruct its public
// intermediate screens from the returned primitives on a detached state copy.
// This never changes the real branch, its agent, policy state, or trace indices.
static void vwinCaptureForcedDecision(VwinCollector &capture, GameContext before,
                                      const PathHistory &path,
                                      const std::vector<std::uint32_t> &bits,
                                      int decisionIdx) {
    for (std::size_t i = 0; i < bits.size(); ++i) {
        vwinObserveDecisionScreen(capture, before, path, bits[i], i == 0 ? decisionIdx : -1);
        search::GameAction(bits[i]).execute(before);
        vwinFinishDecisionSink(capture, &before);
    }
    vwinFinishDecisionSink(capture, nullptr, true);
}

static std::uint64_t vwinThreadCpuNanos() {
    timespec value{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0)
        throw std::runtime_error("vwin refresh: thread CPU clock unavailable");
    return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL
        + static_cast<std::uint64_t>(value.tv_nsec);
}

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
                                                 bool captureCombat = true,
                                                 VwinCollector *vwin = nullptr,
                                                 const VwinBranchStart *branch = nullptr,
                                                 bool forceMissingCombatDecisionHookForTest = false) {
    trainingRunStart();
    const int sourceHealthFailures = search::g_simHealthFailureCount;
    GameContext gc = branch
        ? detachedCounterfactualCopy(*branch->decision->pre)
        : GameContext(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    if (branch) {
        agent = branch->decision->agentAfter;
    } else {
        agent.simulationCountBase = sims;
        agent.rng = std::default_random_engine(seed);
    }
    PathHistory path;
    int fightIdx = 0;
    if (branch) {
        path = branch->decision->path;
        one_combat::restoreOocPolicyThreadState(branch->decision->policyAfter);
        fightIdx = branch->decision->fightIdx;
    } else {
        one_combat::resetPathPolicyState();
        t_actFightProbeDecisionIdx = 0;
        t_tokCheckPending = g_oocStrategicTokCheck;
        t_shopV = true;
    }
    t_curPath = &path;
    std::ostringstream out; bool sourceValid = true;
    int invalidCombatRows = 0;
    bool fatalFailure = false;
    if (vwin) {
        vwin->sourceSeed = seed;
        vwin->fightIdx = fightIdx;
        vwin->decisionIdx = branch ? branch->decision->decisionIdx + 1 : 0;
        vwin->mapRowIdx = 0;
        vwin->rawRowIdx = 0;
        vwin->pendingAction.reset();
        vwin->pendingRawIndex = -1;
        vwin->rawCaptureCount = 0;
        vwin->winCount = 0;
        if (branch) {
            VwinDecisionRow row;
            row.branchId = vwin->branchId;
            row.deviationIdx = vwin->deviationIdx;
            row.decisionIdx = branch->decision->decisionIdx;
            row.act = gc.act;
            row.floor = gc.floorNum;
            row.screen = static_cast<int>(gc.screenState);
            row.type = branch->decision->type;
            row.chosenKey = branch->option.key;
            row.supported = row.complete = true;
            for (const auto &option : branch->decision->options)
                row.candidateKeys.push_back(option.key);
            vwin->decisions.push_back(std::move(row));
            if (gc.screenState == ScreenState::MAP_SCREEN) {
                vwin->mapRows.push_back({vwin->branchId, vwin->deviationIdx,
                    vwin->mapRowIdx++, gc.act, gc.floorNum, gc.curMapNodeX,
                    gc.curMapNodeY, richRow(gc, path)});
            }
            vwin->trace.push_back("D:" + std::to_string(branch->decision->decisionIdx)
                                  + ":" + branch->option.key);
            if (branch->futureSeed && branch->redrawBeforeOption) {
                // GEN=2: the option's own randomness is part of the sampled
                // future. The redraw must leave the published screen intact.
                const auto rowBefore = richRow(gc, path);
                const auto screenBefore = vwinDecisionScreenContents(gc, branch->decision->options).dump();
                std::mt19937_64 future(*branch->futureSeed);
                one_combat::resampleCounterfactualFuture(gc, future);
                // The four HIDDEN_FUTURE rich fields (#397) read the redrawn
                // queues and may change; every other field must not.
                const auto split = [](const std::string &row) {
                    std::vector<std::string> cells;
                    std::stringstream in(row);
                    for (std::string cell; std::getline(in, cell, ',');) cells.push_back(cell);
                    return cells;
                };
                const auto names = split(richStateHeader());
                const auto before = split(rowBefore), after = split(richRow(gc, path));
                if (before.size() != names.size() || after.size() != names.size())
                    throw std::runtime_error("ooc cf pilot: rich row width mismatch");
                static const std::set<std::string> hiddenFuture = {
                    "nextEliteId", "nextFight0", "nextFight1", "nextFight2"};
                for (std::size_t i = 0; i < names.size(); ++i)
                    if (before[i] != after[i] && !hiddenFuture.count(names[i]))
                        throw std::runtime_error("ooc cf pilot: future redraw changed public feature "
                                                 + names[i]);
                if (vwinDecisionScreenContents(gc, branch->decision->options).dump() != screenBefore)
                    throw std::runtime_error("ooc cf pilot: future redraw changed the published decision screen");
            }
            const int healthBefore = search::g_simHealthFailureCount;
            auto previous = std::move(search::g_onGameActionExecute);
            search::g_onGameActionExecute = {};
            try {
                if (branch->option.mapPrimitive) {
                    search::GameAction(branch->option.primitiveBits).execute(gc);
                } else if (branch->option.semantic) {
                    const auto executed = search::executeOocSemanticAction(gc, *branch->option.semantic);
                    if (!executed.ok || executed.executedPrimitiveBits.empty())
                        throw std::runtime_error("vwin refresh: branch semantic action failed: "
                                                 + executed.error);
                    if (vwin->captureDecisionSink)
                        vwinCaptureForcedDecision(*vwin,
                            detachedCounterfactualCopy(*branch->decision->pre), path,
                            executed.executedPrimitiveBits, branch->decision->decisionIdx);
                } else {
                    throw std::runtime_error("vwin refresh: branch option has no executable action");
                }
                search::g_onGameActionExecute = std::move(previous);
            } catch (...) {
                search::g_onGameActionExecute = std::move(previous);
                throw;
            }
            if (healthBefore != search::g_simHealthFailureCount)
                throw std::runtime_error("vwin refresh: health failure during forced branch action");
            if (branch->horizon) branch->horizon->afterFeatures = richRow(gc, path);
            if (branch->futureSeed && !branch->redrawBeforeOption) {
                std::mt19937_64 future(*branch->futureSeed);
                one_combat::resampleCounterfactualFuture(gc, future);
            }
        }
    }

    if (branch && vwin)
        vwinResumeContinuation(*branch->decision, *vwin, gc, path, agent);

    auto finishPendingDecision = [&] {
        if (!vwin || !vwin->pendingAction) return;
        auto pending = std::move(*vwin->pendingAction);
        vwin->pendingAction.reset();
        vwinFinishDecision(*vwin, std::move(pending), agent,
                           one_combat::captureOocPolicyThreadState());
    };

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (branch && branch->horizon && branch->horizon->fullRun && !branch->horizon->mapRecorded
            && gc.screenState == ScreenState::MAP_SCREEN) {
            auto &h = *branch->horizon;
            h.mapRecorded = true;
            h.mapAct = gc.act;
            h.mapFloor = gc.floorNum;
            h.mapFeatures = richRow(gc, path);
        }
        if (gc.screenState == ScreenState::BATTLE) {
            const int act = gc.act, floor = gc.floorNum, room = (int)gc.curRoom;
            const MonsterEncounter encounter = gc.info.encounter;
            const int encounterIndex = static_cast<int>(encounter);
            const bool representableEncounter = encounterIndex >= 0 && encounterIndex < static_cast<int>(sizeof(monsterEncounterStrings) / sizeof(monsterEncounterStrings[0]));
            const std::string features = captureCombat ? vFeatCsv(gc) : std::string{};
            int hooks = 0;
            const bool captureEntry = vwin && vwin->captureBoss
                && (gc.curRoom == Room::BOSS || vwin->captureAllCombatEntries);
            const bool captureActions = vwin && (vwin->captureRefresh || captureEntry);
            const int bossEntryIdx = captureEntry
                ? static_cast<int>(vwin->bossEntries.size()) : -1;
            if (captureActions) {
                agent.recordActions = true;
                agent.gameActionHistory.clear();
            }
            if (bossEntryIdx >= 0) {
                VwinBossEntry entry;
                entry.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                entry.path = path;
                entry.agent = agent;
                entry.policy = one_combat::captureOocPolicyThreadState();
                entry.fightIdx = fightIdx;
                entry.act = act;
                entry.floor = floor;
                entry.encounter = representableEncounter ? monsterEncounterStrings[encounterIndex] : "INVALID";
                entry.roomClass = combatEvalRoomClass(static_cast<Room>(room));
                vwin->bossEntries.push_back(std::move(entry));
            }
            BattleContext bc;
            const int healthBefore = search::g_simHealthFailureCount;
            std::unique_ptr<CombatEvalDecisionScope> decisionScope;
            if ((captureCombat || (vwin && vwin->captureBoss))
                && !forceMissingCombatDecisionHookForTest)
                decisionScope = std::make_unique<CombatEvalDecisionScope>(true);
            std::unique_ptr<one_combat::CombatTransitionRawObserverScope> rawScope;
            const int rawCaptureBefore = vwin ? vwin->rawCaptureCount : 0;
            const int preHp = gc.curHp, preMaxHp = gc.maxHp, prePotions = gc.potionCount, preGold = gc.gold;
            const int mapX = gc.curMapNodeX, mapY = gc.curMapNodeY;
            if (vwin && vwin->captureRefresh) {
                rawScope = std::make_unique<one_combat::CombatTransitionRawObserverScope>(
                    [&](const BattleContext &ended, GameContext &raw) {
                        if (ended.outcome != Outcome::PLAYER_VICTORY) return;
                        VwinRawRow row;
                        row.branchId = vwin->branchId;
                        row.deviationIdx = vwin->deviationIdx;
                        row.rowIdx = vwin->rawRowIdx++;
                        row.act = act;
                        row.floor = floor;
                        row.mapX = mapX;
                        row.mapY = mapY;
                        row.roomClass = combatEvalRoomClass(static_cast<Room>(room));
                        row.encounter = representableEncounter ? monsterEncounterStrings[encounterIndex] : "INVALID";
                        row.features = richRow(raw, path);
                        row.actBoss = static_cast<Room>(room) == Room::BOSS ? 1 : 0;
                        row.preHp = preHp;
                        row.preMaxHp = preMaxHp;
                        row.prePotions = prePotions;
                        row.preGold = preGold;
                        vwin->rawRows.push_back(std::move(row));
                        vwin->pendingRawIndex = static_cast<int>(vwin->rawRows.size()) - 1;
                        ++vwin->rawCaptureCount;
                        ++vwin->winCount;
                    });
            }
            agent.playoutBattle(gc, bc);
            if (decisionScope) hooks = decisionScope->hooks;
            const bool initializationTerminal = !forceMissingCombatDecisionHookForTest && hooks == 0
                && bc.turn == 0 && bc.outcome != Outcome::UNDECIDED;
            const auto label = (captureCombat || (vwin && vwin->captureBoss))
                ? combatEvalTerminal(bc, encounter, hooks, healthBefore, search::g_simHealthFailureCount,
                                     initializationTerminal)
                : CombatEvalLabel{};
            const bool labelValid = captureCombat && label.labelValid;
            const bool healthOk = (captureCombat || (vwin && vwin->captureBoss))
                ? label.healthOk : search::g_simHealthFailureCount == healthBefore;
            if (vwin && captureActions) {
                for (const int bits : agent.gameActionHistory)
                    vwin->trace.push_back("A:" + std::to_string(fightIdx) + ":" + std::to_string(bits));
            }
            if (vwin && bossEntryIdx >= 0) {
                auto &entry = vwin->bossEntries.at(static_cast<std::size_t>(bossEntryIdx));
                entry.firstActionBits = agent.gameActionHistory.empty()
                    ? -1 : agent.gameActionHistory.front();
                entry.sourceWon = bc.outcome == Outcome::PLAYER_VICTORY ? 1
                    : bc.outcome == Outcome::PLAYER_LOSS ? 0 : -1;
                entry.terminalHp = bc.player.curHp;
                entry.signedOutcome = label.signedOutcome;
                entry.labelValid = label.labelValid;
            }
            if (captureCombat && (!vwin || vwin->captureRefresh)) {
                if (vwin && vwin->captureRefresh) {
                    out << seed << ',' << vwin->branchId << ',' << vwin->deviationIdx << ','
                        << fightIdx << ',' << act << ',' << floor << ','
                        << combatEvalRoomClass(static_cast<Room>(room)) << ','
                        << csvQuote(representableEncounter ? monsterEncounterStrings[encounterIndex] : "INVALID")
                        << ',' << teacher.id << ',' << richRow(gc, path) << ',';
                    label.write(out); out << '\n';
                } else {
                out << seed << ',' << fightIdx << ',' << act << ',' << floor << ',' << combatEvalRoomClass(static_cast<Room>(room)) << ','
                    << csvQuote(representableEncounter ? monsterEncounterStrings[encounterIndex] : "INVALID") << ',' << teacher.id << ',' << features << ',';
                label.write(out); out << '\n';
                }
            }
            // Keep every completed terminal as an auditable row.  A simulator
            // or hook failure cannot safely advance the run; ordinary
            // non-death terminations can be exited and the next fight may be
            // collected, while the contract/trainer excludes this row.
            if (captureCombat && !labelValid) { sourceValid = false; ++invalidCombatRows; }
            if ((captureCombat && !labelValid && (!healthOk || !hooks || !representableEncounter))
                || (vwin && (bc.outcome == Outcome::UNDECIDED || !healthOk))) {
                fatalFailure = true;
                search::g_onGameActionExecute = {}; t_curPath = nullptr;
                const int healthFailures = std::max(0, search::g_simHealthFailureCount - sourceHealthFailures);
                if (vwin) for (auto &entry : vwin->bossEntries) entry.sourceTrajectoryValid = false;
                if (vwin) vwin->combatRows = out.str();
                return {out.str(), seed, gc.outcome, gc.floorNum, gc.curHp, fightIdx + 1,
                        invalidCombatRows, healthFailures, false, false, false, fatalFailure};
            }
            bc.exitBattle(gc);
            decisionScope.reset();
            rawScope.reset();
            if (vwin && vwin->captureRefresh) {
                if (bc.outcome == Outcome::PLAYER_VICTORY
                    && vwin->rawCaptureCount != rawCaptureBefore + 1)
                    throw std::runtime_error("vwin refresh: victory did not produce exactly one WIN_RAW row");
                if (vwin->pendingRawIndex >= 0) {
                    vwin->rawRows.at(static_cast<std::size_t>(vwin->pendingRawIndex)).postAfterBattleHp = gc.curHp;
                    vwin->pendingRawIndex = -1;
                }
                vwin->trace.push_back("C:" + std::to_string(fightIdx) + ":"
                    + std::to_string(static_cast<int>(bc.outcome)) + ":"
                    + std::to_string(bc.player.curHp) + ":" + std::to_string(gc.curHp));
            }
            if (vwin && bossEntryIdx >= 0) {
                auto &entry = vwin->bossEntries.at(static_cast<std::size_t>(bossEntryIdx));
                entry.postAfterBattleHp = gc.curHp;
            }
            if (captureActions) {
                agent.recordActions = false;
                agent.gameActionHistory.clear();
            }
            ++fightIdx;
            if (vwin) vwin->fightIdx = fightIdx;
            if (branch && branch->horizon) {
                auto &h = *branch->horizon;
                ++h.fights;
                if (static_cast<Room>(room) == Room::BOSS) {
                    const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
                    if (won) ++h.bossesBeaten;
                    h.hp = gc.curHp; h.maxHp = gc.maxHp; h.act = act; h.floor = floor;
                    if (h.firstBossWon < 0) {
                        h.firstBossWon = won ? 1 : 0;
                        h.firstBossHp = won ? gc.curHp : 0;
                        h.firstBossMaxHp = gc.maxHp;
                        h.firstBossAct = act;
                    }
                    // Stop after the last horizon boss, on a loss, or when the
                    // run ends with this boss (act 3, keys off).
                    if (!won || h.bossesBeaten >= h.bosses || gc.outcome != GameOutcome::UNDECIDED) {
                        h.reached = true;
                        h.bossWon = won ? 1 : 0;
                        break;
                    }
                }
            }
        } else {
            if (!vwin || !vwin->captureRefresh) {
                runFullRunOocPolicyStep(gc, agent, false, true);
            } else {
                vwinRefreshRunPolicyStep(*vwin, gc, path, agent);
            }
        }
    }
    finishPendingDecision();
    if (vwin) vwinFinishDecisionSink(*vwin, nullptr, true);
    search::g_onCombatDecision = nullptr;
    t_curPath = nullptr;
    if (branch && branch->horizon && !branch->horizon->reached
        && gc.outcome == GameOutcome::PLAYER_LOSS) {
        auto &h = *branch->horizon;
        h.reached = h.diedBeforeBoss = true;
        h.bossWon = 0; h.hp = 0; h.maxHp = gc.maxHp; h.act = gc.act; h.floor = gc.floorNum;
    }
    if (branch && branch->horizon && branch->horizon->fullRun)
        branch->horizon->finalWon = combatEvalFinalWon(gc.outcome);
    const bool complete = gc.outcome != GameOutcome::UNDECIDED;
    const int healthFailures = std::max(0, search::g_simHealthFailureCount - sourceHealthFailures);
    const bool trajectoryValid = complete && healthFailures == 0 && !fatalFailure;
    if (vwin) for (auto &entry : vwin->bossEntries) entry.sourceTrajectoryValid = trajectoryValid;
    if (vwin) vwin->combatRows = out.str();
    return {out.str(), seed, gc.outcome, gc.floorNum, gc.curHp, fightIdx,
            invalidCombatRows, healthFailures, sourceValid, complete,
            trajectoryValid, fatalFailure};
}

int vwinRefreshFatalRunoutCountSelfTest(std::uint64_t seed, int sims) {
    if (sims < 1) throw std::runtime_error("vwin fatal runout selftest: SIMS must be positive");
    const auto savedActionHook = std::move(search::g_onGameActionExecute);
    const auto savedCombatHook = std::move(search::g_onCombatDecision);
    const auto savedPolicy = one_combat::captureOocPolicyThreadState();
    search::g_onGameActionExecute = {};
    search::g_onCombatDecision = {};

    CombatEvalSeedResult generated;
    try {
        const WholeCombatTeacher fixture{"vwin-fatal-runout-count-selftest",
                                         nlohmann::json::object()};
        generated = runCombatEvalGenSeed(seed, sims, 0, fixture, true, nullptr, nullptr, true);
    } catch (...) {
        search::g_onGameActionExecute = savedActionHook;
        search::g_onCombatDecision = savedCombatHook;
        one_combat::restoreOocPolicyThreadState(savedPolicy);
        throw;
    }
    search::g_onGameActionExecute = savedActionHook;
    search::g_onCombatDecision = savedCombatHook;
    one_combat::restoreOocPolicyThreadState(savedPolicy);

    const auto combatRows = static_cast<int>(std::count(generated.rows.begin(),
                                                         generated.rows.end(), '\n'));
    if (!generated.fatalFailure || generated.invalidCombatRows != 1 || combatRows != 1)
        throw std::runtime_error("vwin fatal runout selftest: fixture did not produce one fatal combat row");
    if (generated.fightCount != combatRows)
        throw std::runtime_error("vwin fatal runout selftest: runout fightCount differs from combat row count");
    std::cout << "vwin fatal runout contract: fatal fightCount matches its emitted combat row\n";
    return 0;
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


// Loader-only checks for the learned-stop teacher contract (#418). Runs no
// seeds: it installs Silver with production learned stopping and verifies
// which teacher specifications loadWholeCombatTeacher accepts.
int learnedStopTeacherSelfTest() {
    for (const auto &[name, value] : std::vector<std::pair<const char *, const char *>>{
             {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
             {"STS_SILVER_EXACT_ROOT_BUDGETS", "0"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
             {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
             {"STS_SILVER_LEARNED_STOP", "1"}})
        setenv(name, value, 1);
    unsetenv("STS_SILVER_LEARNED_STOP_THRESHOLD");
    unsetenv("STS_SILVER_LEARNED_STOP_BOSS_FALLBACK");
    unsetenv("STS_SILVER_LEARNED_STOP_BOSS_MAX");
    search::installNativeSilverBackend();
    const std::filesystem::path teacherPath = std::filesystem::temp_directory_path()
        / ("sts_learned_stop_teacher_" + trainingExecutableGitSha() + "_"
           + std::to_string(::getpid()) + ".json");
    const nlohmann::json base = {
        {"teacher_id", "learned-stop-selftest"},
        {"git_sha", trainingExecutableGitSha()},
        {"executable_sha256", fileSha256(g_mainBinaryPath)},
        {"combat_backend", "native_silver"},
        {"rng_regime", "project_fair"},
        {"search_configuration", {
            {"budget_policy", "learned_stop"},
            {"learned_stop_model", search::nativeSilverStopModelId()},
            {"learned_stop_threshold", search::nativeSilverLearnedStopThreshold()},
            {"simulation_budgets", {10000}}, {"exploration_parameter", 25.0},
            {"exploration_parameter_chance", 25.0}, {"chance_widening_c", 3.7028},
            {"chance_widening_alpha", 0.52389}, {"end_turn_widening_c", 3.7028},
            {"end_turn_widening_alpha", 0.52389}, {"reuse_cap_mode", "allocated"},
            {"reuse_cap", 32768}, {"sequential_halving", false}, {"pruning", false},
            {"learned_visit_puct", false}, {"direct_learned_leaf", false}, {"adaptive", false},
        }},
        {"environment", {
            {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
            {"STS_SILVER_EXACT_ROOT_BUDGETS", "0"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
            {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
            {"STS_SILVER_LEARNED_STOP", "1"},
        }},
        {"model_artifacts", nlohmann::json::array()},
    };
    const auto loads = [&](const nlohmann::json &teacher, bool allowLearnedStop) {
        { std::ofstream out(teacherPath); out << teacher.dump(); }
        try {
            loadWholeCombatTeacher(teacherPath.string(), 10000, false, false, allowLearnedStop);
            return true;
        } catch (const std::runtime_error &) {
            return false;
        }
    };
    int failures = 0;
    const auto expect = [&](const char *name, bool actual, bool expected) {
        if (actual != expected) {
            ++failures;
            std::cerr << "learnedstopteacherselftest FAIL: " << name << '\n';
        }
    };
    expect("accepts learned-stop teacher when allowed", loads(base, true), true);
    expect("rejects learned-stop teacher when not allowed", loads(base, false), false);
    auto wrongModel = base;
    wrongModel["search_configuration"]["learned_stop_model"] = "gbt-000000000000";
    expect("rejects stop-model mismatch", loads(wrongModel, true), false);
    auto wrongThreshold = base;
    wrongThreshold["search_configuration"]["learned_stop_threshold"] = 0.5;
    expect("rejects threshold mismatch", loads(wrongThreshold, true), false);
    auto unknownPolicy = base;
    unknownPolicy["search_configuration"]["budget_policy"] = "adaptive";
    expect("rejects unknown budget policy", loads(unknownPolicy, true), false);
    auto exactEnv = base;
    exactEnv["environment"]["STS_SILVER_EXACT_ROOT_BUDGETS"] = "1";
    expect("rejects exact-root-budget environment", loads(exactEnv, true), false);
    auto exactTeacher = base;
    exactTeacher["search_configuration"].erase("budget_policy");
    exactTeacher["environment"].erase("STS_SILVER_LEARNED_STOP");
    expect("rejects exact-10k teacher under learned-stop Silver", loads(exactTeacher, true), false);
    // Searching one-action roots changes play but not the teacher spec.
    setenv("STS_SILVER_SEARCH_SINGLETON_ROOTS", "1", 1);
    search::installNativeSilverBackend();
    expect("rejects searched singleton roots", loads(base, true), false);
    unsetenv("STS_SILVER_SEARCH_SINGLETON_ROOTS");
    search::installNativeSilverBackend();
    std::error_code ignored;
    std::filesystem::remove(teacherPath, ignored);
    if (failures == 0) std::cout << "learnedstopteacherselftest PASS\n";
    return failures == 0 ? 0 : 1;
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

static bool vwinTeacherNativeOocEnabled(const nlohmann::json &policy) {
    return policy.value("native_ooc", false);
}

static bool vwinTeacherFlagEnabled(const nlohmann::json &flags, const char *name) {
    const auto it = flags.find(name);
    if (it == flags.end()) return true;
    if (it->is_boolean()) return it->get<bool>();
    if (it->is_number_integer()) return it->get<int>() != 0;
    return true;
}

static void vwinRequireProductionPolicy(const WholeCombatTeacher &teacher) {
    constexpr const char *kPinnedV4TokenSha256 =
        "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c";
    auto require = [](bool ok, const char *what) {
        if (!ok) throw std::runtime_error(std::string("vwin refresh: expected frozen V4 policy: ") + what);
    };
    const char *vpath = std::getenv("STS_VPATH");
    require(!one_combat::vPathPolicyEnabled() && (!vpath || std::atoi(vpath) == 0),
            "STS_VPATH/V-informed pathing disabled");
    require(g_nativeOoc && g_floorNet.ok && g_winNet.ok, "native floor/win heads loaded");
    require(g_oocStrategicTokNet.ok && g_oocStrategicTok == 1, "V4 token model loaded");
    require(fileSha256(g_oocStrategicTokNet.path) == kPinnedV4TokenSha256,
            "pinned V4 token artifact SHA-256");
    require(!g_collectKeys, "act-4 keys disabled");
    require(g_oocStrategicRest && g_oocStrategicEvent && g_oocStrategicShop
            && g_oocStrategicTreasure && g_oocStrategicBossRelic,
            "V4 strategic gates enabled");
    const auto effectiveMargin = [](double overrideMargin) {
        return overrideMargin >= 0.0 ? overrideMargin : g_oocStrategicMargin;
    };
    require(effectiveMargin(g_oocStrategicMarginCard) == 1.0
            && effectiveMargin(g_oocStrategicMarginRest) == 1.0
            && effectiveMargin(g_oocStrategicMarginEvent) == 1.0
            && effectiveMargin(g_oocStrategicMarginShop) == 1.0
            && effectiveMargin(g_oocStrategicMarginTreasure) == 1.0
            && effectiveMargin(g_oocStrategicMarginBossRelic) == 1.0,
            "all active V4 gate margins are 1.0");
    require(!g_oocActionNN, "experimental OOC action model disabled");
    require(g_oocStrategicMargin == 1.0, "V4 strategic margin is 1.0");
    require(!g_oocMapRoute && !g_oocStrategicMap && g_pathV == 0 && g_eventV == 0
            && !g_oocShopBeam && g_oocStrategicQ && !g_oocStrategicScorePolicy
            && !g_restWin && g_bossRelicV == 0 && g_neowV == 0
            && !g_cardWin && !g_cardNN && !g_cardAction && !g_shopWin && g_bossV == 0
            && g_bossDraft == 0 && !g_actFightProbeDraft && !g_actFightProbeAllOoc
            && !g_actFightProbePredict && !g_actFightProbeEncounterNN
            && !g_oocStrategicGateRegret,
            "non-default action/policy interventions disabled");
    if (const char *mcts = std::getenv("STS_OOC_MCTS"))
        require(std::string(mcts) == "0", "STS_OOC_MCTS is off");
    const auto &spec = teacher.specification;
    require(spec.contains("ooc_policy") && spec["ooc_policy"].is_object(),
            "teacher binds ooc_policy");
    const auto &policy = spec["ooc_policy"];
    const auto &flags = policy.at("flags");
    const auto &parameters = policy.at("parameters");
    require(vwinTeacherNativeOocEnabled(policy), "teacher native_ooc=true");
    require(!flags.value("collect_keys", true), "teacher collect_keys=false");
    require(flags.value("ooc_strategic_rest", false)
            && flags.value("ooc_strategic_event", false)
            && flags.value("ooc_strategic_shop", false)
            && flags.value("ooc_strategic_treasure", false)
            && flags.value("ooc_strategic_boss_relic", false),
            "teacher V4 strategic gates");
    require(flags.value("ooc_strategic_tok", false)
            && flags.value("ooc_strategic_card", false), "teacher V4 token/card gate");
    require(flags.value("ooc_strategic_q", false), "teacher strategic Q scoring is enabled");
    require(parameters.value("strategic_margin", -1.0) == 1.0,
            "teacher strategic margin");
    require(policy.value("shopV", false) && policy.value("restV", true) == false,
            "teacher default shop/rest fallback chain");
    for (const char *flag : {"ooc_action_nn", "act_fight_probe_all_ooc", "ooc_map_route",
            "ooc_strategic_map", "path_v", "event_v", "ooc_shop_beam",
            "ooc_strategic_score_policy", "rest_win", "boss_relic_v", "neow_v", "card_win",
            "card_nn", "card_action", "shop_win", "boss_v", "boss_draft",
            "act_fight_probe_draft", "act_fight_probe_predict", "act_fight_probe_encounter_nn",
            "act_fight_probe_gate_regret"})
        require(!vwinTeacherFlagEnabled(flags, flag), "teacher disables non-default intervention flag");
    const auto &artifacts = policy.at("model_artifacts");
    require(std::any_of(artifacts.begin(), artifacts.end(), [](const auto &artifact) {
        return artifact.value("role", std::string{}) == "ooc_strategic_tok";
    }), "teacher hashes the V4 token artifact");
}

int vwinVPathPolicyGuardSelfTest() {
    const char *vpath = std::getenv("STS_VPATH");
    if (!vpath || std::atoi(vpath) == 0 || !one_combat::vPathPolicyEnabled())
        throw std::runtime_error("vwin VPATH guard selftest: run with STS_VPATH=1");
    try {
        WholeCombatTeacher unused{"vwin-vpath-guard-selftest", nlohmann::json::object()};
        vwinRequireProductionPolicy(unused);
    } catch (const std::exception &error) {
        if (std::string(error.what()).find("STS_VPATH/V-informed pathing disabled")
            != std::string::npos) {
            std::cout << "vwin refresh policy guard: enabled STS_VPATH rejected\n";
            return 0;
        }
        throw;
    }
    throw std::runtime_error("vwin VPATH guard selftest: enabled STS_VPATH was accepted");
}

static void vwinWriteCollector(std::ostream &mapOut, std::ostream &rawOut,
                               std::ostream &decisionOut, std::ostream *decisionSinkOut,
                               std::ostream &combatOut, std::uint64_t sourceSeed,
                               const VwinCollector &capture, int won,
                               const WholeCombatTeacher &teacher) {
    for (const auto &row : capture.mapRows)
        mapOut << sourceSeed << ',' << row.branchId << ',' << row.deviationIdx << ','
               << row.rowIdx << ',' << row.act << ',' << row.floor << ',' << row.mapX << ','
               << row.mapY << ',' << teacher.id << ',' << row.features << '\n';
    for (const auto &row : capture.rawRows)
        rawOut << sourceSeed << ',' << row.branchId << ',' << row.deviationIdx << ','
               << row.rowIdx << ',' << row.act << ',' << row.floor << ',' << row.mapX << ','
               << row.mapY << ',' << teacher.id << ',' << row.features << ','
               << csvQuote(row.roomClass) << ',' << row.actBoss << ',' << csvQuote(row.encounter)
               << ',' << row.preHp << ',' << row.preMaxHp << ',' << row.prePotions << ','
               << row.preGold << ',' << row.postAfterBattleHp << '\n';
    for (const auto &row : capture.decisions) {
        nlohmann::json keys = nlohmann::json::array();
        for (const auto &key : row.candidateKeys) keys.push_back(key);
        decisionOut << sourceSeed << ',' << row.branchId << ',' << row.deviationIdx << ','
                    << row.decisionIdx << ',' << row.type << ',' << row.act << ',' << row.floor
                    << ',' << row.screen << ',' << row.candidateKeys.size() << ','
                    << csvQuote(row.chosenKey) << ',' << (row.supported ? 1 : 0) << ','
                    << (row.complete ? 1 : 0) << ','
                    << (vwinSelectedDecision(capture, row.decisionIdx) ? 1 : 0) << ','
                    << csvQuote(keys.dump()) << ',' << csvQuote(row.error) << '\n';
    }
    if (decisionSinkOut) {
        for (const auto &row : capture.decisionSinkRows) {
            nlohmann::json candidates = {
                {"optionKeys", row.candidateKeys}, {"chosenKey", row.chosenKey},
                {"supported", row.supported}, {"complete", row.complete}
            };
            *decisionSinkOut << sourceSeed << ',' << row.branchId << ',' << row.deviationIdx
                << ',' << row.rowIdx << ',' << row.decisionIdx << ',' << row.act << ','
                << row.floor << ',' << csvQuote(row.screen) << ',' << csvQuote(teacher.id)
                << ',' << row.features << ',' << csvQuote(row.screenContentsJson) << ','
                << csvQuote(candidates.dump()) << ',' << won << '\n';
        }
    }
    combatOut << capture.combatRows;
}

static void vwinWriteRunout(std::ostream &out, std::uint64_t sourceSeed,
                            const VwinCollector &capture,
                            const CombatEvalSeedResult &result,
                            const WholeCombatTeacher &teacher,
                            const char *branchParity) {
    out << sourceSeed << ',' << capture.branchId << ',' << capture.deviationIdx << ','
        << combatEvalGameOutcome(result.finalOutcome) << ','
        << combatEvalFinalWon(result.finalOutcome) << ',' << result.finalFloor << ','
        << result.finalHp << ',' << result.fightCount << ','
        << (result.trajectoryComplete ? 1 : 0) << ',' << (result.trajectoryValid ? 1 : 0)
        << ',' << std::count(result.rows.begin(), result.rows.end(), '\n') << ','
        << result.invalidCombatRows << ',' << teacher.id << ','
        << result.simulatorHealthFailures << ',' << (result.fatalFailure ? 1 : 0) << ','
        << branchParity << '\n';
}

static std::vector<VwinSampledDecision *> vwinSamplesInSourceOrder(VwinCollector &capture) {
    std::vector<VwinSampledDecision *> result;
    for (auto &[type, samples] : capture.sampled) {
        (void)type;
        for (auto &sample : samples) result.push_back(&sample);
    }
    std::sort(result.begin(), result.end(), [](const auto *a, const auto *b) {
        return a->decisionIdx < b->decisionIdx;
    });
    return result;
}

void vwinRefreshGen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                    long long seedOffset, const std::string &teacherPath,
                    int samplesPerType, int parityPercent,
                    int diagMaxBranches, const std::string &diagMarkerPath) {
    // Diagnostic-only crash localisation (vwinrefreshcrashdiag). Production
    // vwinrefreshgen passes no marker path and no branch limit.
    std::FILE *diagMarkers = nullptr;
    if (!diagMarkerPath.empty()) {
        diagMarkers = std::fopen(diagMarkerPath.c_str(), "a");
        if (!diagMarkers) throw std::runtime_error("vwin refresh: cannot open diagnostic marker log");
    }
    auto marker = [&](const std::string &branchId, const char *phase) {
        if (!diagMarkers) return;
        std::fprintf(diagMarkers, "%s %s\n", branchId.c_str(), phase);
        std::fflush(diagMarkers);
    };
    if (nSeeds < 1 || sims != 10000 || asc != 0 || samplesPerType < 1
        || parityPercent < 0 || parityPercent > 100 || seedOffset < 0
        || seedOffset > std::numeric_limits<long long>::max() - (nSeeds - 1LL))
        throw std::runtime_error("vwin refresh: requires N>0, exact 10k, Ascension 0, K>0, parity rate 0..100, and a nonnegative nonoverflowing seed range");
    const char *decisionSinkEnv = std::getenv("STS_VWIN_DECISION_SINK");
    const bool captureDecisionSink = decisionSinkEnv && std::string(decisionSinkEnv) == "1";
    if (decisionSinkEnv && std::string(decisionSinkEnv) != "0"
        && std::string(decisionSinkEnv) != "1")
        throw std::runtime_error("vwin refresh: STS_VWIN_DECISION_SINK must be 0 or 1");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true);
    vwinRequireProductionPolicy(teacher);
    search::g_richCombatFeatures = true;
    std::vector<std::string> suffixes = {
        ".map.csv", ".win_raw.csv", ".decisions.csv", ".branches.csv",
        ".combat.csv", ".runout.csv", ".manifest.json"};
    if (captureDecisionSink) suffixes.push_back(".decision.csv");
    for (const auto &suffix : suffixes)
        if (std::filesystem::exists(outPrefix + suffix))
            throw std::runtime_error("vwin refresh: refusing to overwrite existing output "
                                     + outPrefix + suffix);
    std::ofstream mapOut(outPrefix + ".map.csv");
    std::ofstream rawOut(outPrefix + ".win_raw.csv");
    std::ofstream decisionOut(outPrefix + ".decisions.csv");
    std::ofstream decisionSinkOut;
    if (captureDecisionSink) decisionSinkOut.open(outPrefix + ".decision.csv");
    std::ofstream branchOut(outPrefix + ".branches.csv");
    std::ofstream combatOut(outPrefix + ".combat.csv");
    std::ofstream runoutOut(outPrefix + ".runout.csv");
    if (!mapOut || !rawOut || !decisionOut || (captureDecisionSink && !decisionSinkOut)
        || !branchOut || !combatOut || !runoutOut)
        throw std::runtime_error("vwin refresh: cannot open one or more outputs");
    mapOut << vwinMapHeader() << '\n';
    rawOut << vwinRawHeader() << '\n';
    decisionOut << vwinDecisionHeader() << '\n';
    if (captureDecisionSink) decisionSinkOut << vwinDecisionSinkHeader() << '\n';
    branchOut << vwinBranchHeader() << '\n';
    combatOut << vwinCombatHeader() << '\n';
    runoutOut << vwinRunoutHeader() << ",branchParity\n";

    nlohmann::json branchSummary = nlohmann::json::array();
    nlohmann::json decisionTrajectories = nlohmann::json::array();
    nlohmann::json decisionScreens = {{"source", nlohmann::json::object()},
                                     {"branch", nlohmann::json::object()}};
    auto recordDecisionSink = [&](const VwinCollector &capture) {
        if (!captureDecisionSink) return;
        decisionTrajectories.push_back({
            {"sourceSeed", capture.sourceSeed}, {"branchId", capture.branchId},
            {"deviationIdx", capture.deviationIdx}, {"rows", capture.decisionSinkRows.size()},
            {"decisionLog", capture.decisionSinkLog}
        });
        auto &screens = decisionScreens[capture.branchId == "source" ? "source" : "branch"];
        for (const auto &row : capture.decisionSinkRows)
            screens[row.screen] = screens.value(row.screen, std::uint64_t{0}) + 1;
    };
    struct VwinTypeSummary {
        std::uint64_t decisions = 0, unsupported = 0, incomplete = 0;
        std::uint64_t eligible = 0, candidateOptions = 0, sampled = 0, branches = 0;
        double branchCpuSeconds = 0.0;
    };
    std::map<std::string, VwinTypeSummary> typeSummary;
    std::uint64_t sourceMapRows = 0, sourceRawRows = 0, branchMapRows = 0,
                  branchRawRows = 0, decisionRows = 0, decisionSinkRows = 0, branchRows = 0;
    int completedSources = 0, validSources = 0, parityChecks = 0, parityFailures = 0;
    for (int index = 0; index < nSeeds; ++index) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + index);
        VwinCollector source;
        source.sourceSeed = seed;
        source.samplesPerType = samplesPerType;
        source.branchId = "source";
        source.deviationIdx = 0;
        source.captureRefresh = true;
        source.allowSampling = true;
        source.captureDecisionSink = captureDecisionSink;
        marker("source", "before_runCombatEvalGenSeed");
        const auto generated = runCombatEvalGenSeed(seed, sims, asc, teacher, true, &source);
        marker("source", "after_runCombatEvalGenSeed");
        for (const auto &decision : source.decisions) {
            if (decision.branchId != "source") continue;
            auto &summary = typeSummary[decision.type];
            ++summary.decisions;
            if (!decision.supported) ++summary.unsupported;
            if (!decision.complete) ++summary.incomplete;
            const bool eligible = decision.supported && decision.complete
                && decision.candidateKeys.size() >= 2 && !decision.chosenKey.empty()
                && std::find(decision.candidateKeys.begin(), decision.candidateKeys.end(),
                             decision.chosenKey) != decision.candidateKeys.end();
            if (eligible) {
                ++summary.eligible;
                summary.candidateOptions += decision.candidateKeys.size();
            }
            if (vwinSelectedDecision(source, decision.decisionIdx)) ++summary.sampled;
        }
        vwinWriteCollector(mapOut, rawOut, decisionOut,
                           captureDecisionSink ? &decisionSinkOut : nullptr, combatOut,
                           seed, source, combatEvalFinalWon(generated.finalOutcome), teacher);
        vwinWriteRunout(runoutOut, seed, source, generated, teacher, "NA");
        sourceMapRows += source.mapRows.size();
        sourceRawRows += source.rawRows.size();
        decisionRows += source.decisions.size();
        decisionSinkRows += source.decisionSinkRows.size();
        recordDecisionSink(source);
        if (generated.trajectoryComplete) ++completedSources;
        if (generated.trajectoryValid) ++validSources;
        marker("source", "source_bookkeeping_done");

        bool diagStop = false;
        for (auto *sample : vwinSamplesInSourceOrder(source)) {
            if (diagStop) break;
            for (const auto &option : sample->options) {
                if (diagStop) break;
                std::string diagBranchId;
                {  // branch-local scope: the destroyed marker follows its destructors
                const bool chosen = option.key == sample->chosenKey;
                const std::string branchId = "s" + std::to_string(seed) + "-d"
                    + std::to_string(sample->decisionIdx) + "-" + vwinSha256(option.key).substr(0, 12);
                VwinBranchStart start{sample, option, branchId};
                VwinCollector branch;
                branch.sourceSeed = seed;
                branch.branchId = branchId;
                branch.deviationIdx = 1;
                branch.captureRefresh = true;
                branch.allowSampling = false;
                branch.captureDecisionSink = captureDecisionSink;
                diagBranchId = branchId;
                marker(branchId, "before_runCombatEvalGenSeed");
                const auto branchCpuStart = vwinThreadCpuNanos();
                const auto branched = runCombatEvalGenSeed(seed, sims, asc, teacher, true,
                                                            &branch, &start);
                marker(branchId, "after_runCombatEvalGenSeed");
                const double branchCpuSeconds = static_cast<double>(
                    vwinThreadCpuNanos() - branchCpuStart) / 1.0e9;
                auto &summary = typeSummary[sample->type];
                ++summary.branches;
                summary.branchCpuSeconds += branchCpuSeconds;
                bool parity = false;
                bool parityApplicable = false;
                const auto parityHash = vwinSha256("vwin-branch-parity-334-v1:"
                    + std::to_string(seed) + ":" + std::to_string(sample->decisionIdx));
                const int parityBucket = static_cast<int>(std::stoul(parityHash.substr(0, 8), nullptr, 16) % 100);
                if (chosen && generated.trajectoryValid && parityBucket < parityPercent) {
                    parityApplicable = true;
                    const auto first = source.trace.begin()
                        + static_cast<std::ptrdiff_t>(sample->sourceTraceIndex);
                    const std::vector<std::string> expected(first, source.trace.end());
                    parity = expected == branch.trace
                        && branched.finalOutcome == generated.finalOutcome
                        && branched.finalFloor == generated.finalFloor
                        && branched.finalHp == generated.finalHp;
                    ++parityChecks;
                    if (!parity) ++parityFailures;
                }
                marker(branchId, "before_vwinWriteCollector");
                vwinWriteCollector(mapOut, rawOut, decisionOut,
                                   captureDecisionSink ? &decisionSinkOut : nullptr, combatOut,
                                   seed, branch, combatEvalFinalWon(branched.finalOutcome), teacher);
                marker(branchId, "after_vwinWriteCollector");
                marker(branchId, "before_vwinWriteRunout");
                vwinWriteRunout(runoutOut, seed, branch, branched, teacher,
                    parityApplicable ? (parity ? "PASS" : "FAIL") : "NA");
                marker(branchId, "after_vwinWriteRunout");
                marker(branchId, "before_branch_summary");
                branchMapRows += branch.mapRows.size();
                branchRawRows += branch.rawRows.size();
                decisionRows += branch.decisions.size();
                decisionSinkRows += branch.decisionSinkRows.size();
                recordDecisionSink(branch);
                ++branchRows;
                branchOut << seed << ',' << sample->decisionIdx << ',' << sample->type << ','
                          << csvQuote(option.key) << ',' << (chosen ? 1 : 0) << ','
                          << branchId << ',' << combatEvalFinalWon(branched.finalOutcome) << ','
                          << branched.finalFloor << ',' << branched.finalHp << ','
                          << ((branched.trajectoryValid && (!parityApplicable || parity)
                               && (!chosen || generated.trajectoryValid)) ? 1 : 0) << '\n';
                branchSummary.push_back({{"sourceSeed", seed},
                    {"decisionIdx", sample->decisionIdx}, {"type", sample->type},
                    {"optionKey", option.key}, {"chosen", chosen}, {"branchId", branchId},
                    {"cpuSeconds", branchCpuSeconds},
                    {"trajectoryValid", branched.trajectoryValid},
                    {"chosenReplayParity", parityApplicable ? nlohmann::json(parity)
                                                             : nlohmann::json(nullptr)}});
                marker(branchId, "after_branch_summary");
                marker(branchId, "end_of_branch_iteration");
                }
                marker(diagBranchId, "branch_locals_destroyed");
                if (diagMaxBranches > 0 && branchRows >= static_cast<std::uint64_t>(diagMaxBranches))
                    diagStop = true;
            }
        }
        mapOut.flush(); rawOut.flush(); decisionOut.flush(); branchOut.flush();
        if (captureDecisionSink) decisionSinkOut.flush();
        combatOut.flush(); runoutOut.flush();
        if (diagStop) {
            marker("diag", "branch_limit_reached_stop");
            std::fclose(diagMarkers);
            std::cout << "vwin refresh crash diagnostic: stopped after " << branchRows
                      << " branches (no manifest written)\n";
            return;
        }
    }
    if (diagMarkers) std::fclose(diagMarkers);
    mapOut.close(); rawOut.close(); decisionOut.close(); branchOut.close();
    if (captureDecisionSink) decisionSinkOut.close();
    combatOut.close(); runoutOut.close();
    nlohmann::json outputHashes = nlohmann::json::object();
    for (const auto &suffix : {".map.csv", ".win_raw.csv", ".decisions.csv", ".branches.csv",
                               ".combat.csv", ".runout.csv"})
        outputHashes[std::string(suffix).substr(1)] = fileSha256(outPrefix + suffix);
    if (captureDecisionSink)
        outputHashes["decision.csv"] = fileSha256(outPrefix + ".decision.csv");
    nlohmann::json perType = nlohmann::json::object();
    for (const auto &[type, summary] : typeSummary) {
        perType[type] = {
            {"decisions", summary.decisions},
            {"unsupported", summary.unsupported},
            {"incomplete", summary.incomplete},
            {"eligible", summary.eligible},
            {"candidateOptions", summary.candidateOptions},
            {"sampled", summary.sampled},
            {"branches", summary.branches},
            {"branchCpuSeconds", summary.branchCpuSeconds},
            {"meanBranchCpuSeconds", summary.branches > 0
                ? summary.branchCpuSeconds / static_cast<double>(summary.branches) : 0.0},
        };
    }
    nlohmann::json manifest = {
        {"schemaVersion", "vwin_refresh_334_v1"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherPath", std::filesystem::absolute(teacherPath).string()},
        {"teacherManifestSha256", fileSha256(teacherPath)},
        {"teacherId", teacher.id}, {"combatTeacher", teacher.specification},
        {"policy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"sampling", {{"schema", "outcome_blind_reservoir_per_type_v1"},
                       {"samplesPerType", samplesPerType}, {"optionCap", 6},
                       {"capRule", "chosen_plus_five_sha256_ranked"},
                       {"capDomain", "vwin-option-cap-334-v1:{seed}:{decisionIdx}:{optionKey}"}}},
        {"split", {{"rule", "source_seed_sha256_prefix_v1"},
                    {"domain", "vwin-refresh-334-v1:{seed}"},
                    {"prefixBytes", 4}, {"trainLt", 0.70}, {"validationLt", 0.85},
                    {"branchesInheritSourceSeed", true}}},
        {"branchParity", {{"percent", parityPercent},
                           {"rule", "sha256_bucket_decision_v1"},
                           {"domain", "vwin-branch-parity-334-v1:{seed}:{decisionIdx}"},
                           {"checks", parityChecks}, {"failures", parityFailures}}},
        {"stateFeatures", {{"schema", "rich_state_v1"}, {"header", richStateHeader()},
                           {"headerSha256", vwinSha256(richStateHeader())}, {"count", 1017}}},
        {"integrity", {{"completedSources", completedSources}, {"validSources", validSources},
            {"sourceMapRows", sourceMapRows}, {"sourceWinRawRows", sourceRawRows},
            {"branchMapRows", branchMapRows}, {"branchWinRawRows", branchRawRows},
            {"decisionRows", decisionRows}, {"branches", branchRows},
            {"chosenReplayChecks", parityChecks}, {"chosenReplayFailures", parityFailures}}},
        {"outputs", outputHashes}, {"perType", std::move(perType)},
        {"branchRows", std::move(branchSummary)}
    };
    if (captureDecisionSink) {
        manifest["decisionSink"] = {
            {"schema", "vwin_decision_334_v1"}, {"enabled", true},
            {"rows", decisionSinkRows},
            {"screenContentsEncoding", "canonical_json_public_state_v1"},
            {"candidatesEncoding", "canonical_semantic_keys_with_chosen_v1"},
            {"label", "trajectory_finalWon"},
            {"decisionIdxJoin", "legacy_decisions_csv_or_minus_one_for_capture_only"},
            {"trajectories", std::move(decisionTrajectories)},
            {"byScreen", std::move(decisionScreens)},
            {"bytes", std::filesystem::file_size(outPrefix + ".decision.csv")},
            {"bytesPerRow", decisionSinkRows ? static_cast<double>(
                std::filesystem::file_size(outPrefix + ".decision.csv")) / decisionSinkRows : 0.0},
            {"projectedA2Bytes", static_cast<double>(
                std::filesystem::file_size(outPrefix + ".decision.csv")) * 4096.0 / nSeeds},
            {"projectionSourceSeeds", nSeeds}, {"projectionTargetSeeds", 4096}
        };
        manifest["integrity"]["decisionSinkRows"] = decisionSinkRows;
    }
    std::ofstream manifestOut(outPrefix + ".manifest.json");
    if (!manifestOut) throw std::runtime_error("vwin refresh: cannot write manifest");
    manifestOut << manifest.dump(2) << '\n';
    if (!manifestOut) throw std::runtime_error("vwin refresh: manifest write failed");
    if (parityFailures != 0)
        throw std::runtime_error("vwin refresh: chosen replay parity failed for "
                                 + std::to_string(parityFailures) + " branches");
    std::cout << "vwin refresh teacher=" << teacher.id << " completed=" << completedSources
              << '/' << nSeeds << " valid=" << validSources << " branches=" << branchRows
              << " chosenParity=" << parityChecks << '/' << parityChecks
              << " map=" << sourceMapRows + branchMapRows << " win_raw="
              << sourceRawRows + branchRawRows << " -> " << outPrefix << "\n";
}

static VwinCfTarget vwinParseCfTarget(const nlohmann::json &doc,
                                      std::uint64_t sourceSeed, bool preflight) {
    if (!doc.is_object() || doc.value("schemaVersion", std::string{}) != "ooc_cf_target_v1"
        || doc.at("sourceSeed").get<std::uint64_t>() != sourceSeed
        || doc.value("screen", std::string{}) != "REST")
        throw std::runtime_error("ooc cf target: schema, sourceSeed or REST screen mismatch");
    VwinCfTarget target;
    target.act = doc.at("act").get<int>();
    target.floor = doc.at("floor").get<int>();
    target.decisionIdx = doc.value("decisionIdx", -1);
    target.publicStateSha256 = doc.value("publicStateSha256", std::string{});
    target.preflightReceiptPath = doc.value("preflightReceiptPath", std::string{});
    target.preflightReceiptSha256 = doc.value("preflightReceiptSha256", std::string{});
    target.optionKeys = doc.at("optionKeys").get<std::vector<std::string>>();
    const auto isHash = [](const std::string &s) {
        return s.size() == 64 && s.find_first_not_of("0123456789abcdef") == std::string::npos;
    };
    if (target.act < 1 || target.act > 3 || target.floor < 1 || target.decisionIdx < -1
        || (!target.publicStateSha256.empty() && !isHash(target.publicStateSha256))
        || (!target.preflightReceiptSha256.empty() && !isHash(target.preflightReceiptSha256)))
        throw std::runtime_error("ooc cf target: invalid act/floor/decision/hash");
    std::set<std::string> unique;
    for (const auto &key : target.optionKeys)
        if (key.empty() || !unique.insert(key).second)
            throw std::runtime_error("ooc cf target: empty or duplicate option key");
    if (!preflight && (target.decisionIdx < 0 || !isHash(target.publicStateSha256)
        || target.preflightReceiptPath.empty() || !isHash(target.preflightReceiptSha256)
        || target.optionKeys.empty()))
        throw std::runtime_error("ooc cf target: positive futures require decisionIdx, publicStateSha256, "
                                 "preflight receipt path/hash and explicit optionKeys");
    return target;
}

static std::vector<VwinOption> vwinCfTargetOptions(const std::vector<VwinOption> &options,
        const std::string &chosenKey, const std::vector<std::string> &requested,
        bool inventoryOnly) {
    std::map<std::string, VwinOption> legal;
    for (const auto &option : options)
        if (!legal.emplace(option.key, option).second)
            throw std::runtime_error("ooc cf target: duplicate legal semantic key");
    if (!legal.count(chosenKey)) throw std::runtime_error("ooc cf target: captured baseline key is absent");
    std::set<std::string> keep{chosenKey};
    for (const auto &key : requested) {
        if (!legal.count(key)) throw std::runtime_error("ooc cf target: requested option not legal: " + key);
        keep.insert(key);
    }
    std::vector<VwinOption> result;
    for (const auto &[key, option] : legal)
        if ((inventoryOnly && requested.empty()) || keep.count(key)) result.push_back(option);
    return result;
}

static nlohmann::json vwinCfPublicTargetState(const VwinSampledDecision &sample) {
    const auto &gc = *sample.pre;
    auto values = one_combat::richFeatureVec(gc, sample.path);
    const auto &idx = richIdxMap();
    for (const char *name : {"nextEliteId", "nextFight0", "nextFight1", "nextFight2",
                            "remElites", "remFights", "monOffset", "eliteOffset"})
        values[idx.at(name)] = -1;
    nlohmann::json state = {
        {"schemaVersion", "ooc_cf_public_rest_state_v1"},
        {"richHeader", richStateHeader()}, {"richValues", values},
        {"screenContents", vwinDecisionScreenContents(gc, sample.options)},
        {"pathLastNodeKey", sample.path.lastNodeKey},
        {"deck", nlohmann::json::array()}, {"relics", nlohmann::json::array()},
        {"potionSlots", nlohmann::json::array()}, {"map", nlohmann::json::array()}};
    for (int i = 0; i < gc.deck.size(); ++i)
        state["deck"].push_back({{"card", vwinCardContents(gc.deck.cards[i])},
                                 {"bottled", gc.deck.isCardBottled(i)}});
    for (const auto &relic : gc.relics.relics)
        state["relics"].push_back({{"id", static_cast<int>(relic.id)}, {"data", relic.data}});
    for (int i = 0; i < gc.potionCapacity; ++i)
        state["potionSlots"].push_back(static_cast<int>(gc.potions[i]));
    if (gc.map) {
        for (const auto &row : gc.map->nodes) for (const auto &node : row) {
            std::vector<int> edges(node.edges.begin(), node.edges.begin() + node.edgeCount);
            state["map"].push_back({{"x", node.x}, {"y", node.y},
                {"room", static_cast<int>(node.room)}, {"edges", edges}});
        }
        state["burningElitePosition"] = {gc.map->burningEliteX, gc.map->burningEliteY};
    }
    return state;
}

// Counterfactual OOC label pilot. The source trajectory and its outcome-blind
// per-type reservoir are exactly vwinrefreshgen's (K=1). Per seed, one sampled
// CARD_REWARD, REST, SHOP or BOSS_RELIC decision is selected by hash; every
// retained option (chosen plus at most five) is forced FUTURES times. Run k of
// every option redraws the hidden future from the same seed (common random
// numbers across siblings), then the production chain plays until the first
// boss fight after the branch ends. Label: boss beaten, HP after it.
//
// GEN=2 (after review, ACTION-PLAN E2): the label is the final run outcome;
// the future is redrawn before the forced option, so the option's own
// randomness is sampled too; features are also recorded at the first MAP
// screen after the branch screen is finished (`.map.csv`, one row per run);
// the option cap deduplicates identical cards at other deck positions and
// always keeps the chosen and skip/leave options; states are selected only
// from `types`, sha256-ranked in a v2 domain.
void oocCounterfactualPilotGen(int nSeeds, const std::string &outPrefix,
                               long long seedOffset, const std::string &teacherPath,
                               int futures, int statesPerSeed, int cardRewardBosses,
                               int generation, const std::string &typeList,
                               const std::string &targetPath, int futureStart, int asc) {
    constexpr int sims = 10000;
    if (asc < 0 || asc > 20) throw std::runtime_error("ooc cf pilot: ASCENSION must be 0..20");
    if (nSeeds < 1 || futures < 0 || (futures == 0 && targetPath.empty())
        || statesPerSeed < 1 || cardRewardBosses < 1 || cardRewardBosses > 2
        || generation < 1 || generation > 2
        || futureStart < 0 || futureStart > std::numeric_limits<int>::max() - futures
        || seedOffset < 0
        || seedOffset > std::numeric_limits<long long>::max() - (nSeeds - 1LL))
        throw std::runtime_error("ooc cf pilot: requires N>0, FUTURES>0, STATES>0, CARD_BOSSES 1..2, GEN 1..2 and a nonnegative seed range");
    const bool v2 = generation == 2;
    std::set<std::string> inScope = {"BOSS_RELIC", "CARD_REWARD", "REST", "SHOP"};
    if (v2 && !typeList.empty()) {
        std::set<std::string> requested;
        std::stringstream types(typeList);
        for (std::string type; std::getline(types, type, ',');) {
            if (!inScope.count(type)) throw std::runtime_error("ooc cf pilot: unsupported type " + type);
            requested.insert(type);
        }
        if (requested.empty()) throw std::runtime_error("ooc cf pilot: empty TYPES");
        inScope = requested;
    } else if (!v2 && !typeList.empty()) {
        throw std::runtime_error("ooc cf pilot: TYPES requires GEN=2");
    }
    if (!v2 && futureStart != 0) throw std::runtime_error("ooc cf pilot: FUTURE_START requires GEN=2");
    std::optional<VwinCfTarget> target;
    nlohmann::json targetDocument, preflightReceipt;
    if (!targetPath.empty()) {
        if (!v2 || nSeeds != 1 || statesPerSeed != 1 || inScope != std::set<std::string>{"REST"})
            throw std::runtime_error("ooc cf target: requires GEN=2, N=1, STATES=1, TYPES=REST");
        std::ifstream input(targetPath);
        if (!input) throw std::runtime_error("ooc cf target: cannot read target file");
        input >> targetDocument;
        target = vwinParseCfTarget(targetDocument, seedOffset, futures == 0);
        if (futures > 0) {
            if (fileSha256(target->preflightReceiptPath) != target->preflightReceiptSha256)
                throw std::runtime_error("ooc cf target: preflight receipt SHA256 mismatch");
            std::ifstream prior(target->preflightReceiptPath);
            prior >> preflightReceipt;
            if (preflightReceipt.value("schemaVersion", std::string{}) != "ooc_cf_target_receipt_v1"
                || !preflightReceipt.value("preflightOnly", false))
                throw std::runtime_error("ooc cf target: reference must be a zero-future preflight receipt");
        }
    }
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true, true);
    vwinRequireProductionPolicy(teacher);
    const nlohmann::json targetBinding = target ? nlohmann::json{
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification}, {"policy", effectiveOocPolicySpecification()},
        {"sourceSeed", seedOffset}, {"ascension", asc}}
        : nlohmann::json{};
    if (target && futures > 0 && preflightReceipt.at("binding") != targetBinding)
        throw std::runtime_error("ooc cf target: preflight producer/teacher/policy binding changed");
    search::g_richCombatFeatures = true;
    std::vector<std::string> suffixes = {".labels.csv", ".options.csv", ".sources.csv",
                                         ".manifest.json"};
    if (v2) suffixes.push_back(".map.csv");
    if (target) suffixes.push_back(".target.json");
    for (const auto &suffix : suffixes)
        if (std::filesystem::exists(outPrefix + suffix))
            throw std::runtime_error("ooc cf pilot: refusing to overwrite " + outPrefix + suffix);
    std::ofstream labelOut(outPrefix + ".labels.csv"), optionOut(outPrefix + ".options.csv"),
        sourceOut(outPrefix + ".sources.csv");
    std::ofstream mapOut;
    if (v2) mapOut.open(outPrefix + ".map.csv");
    if (!labelOut || !optionOut || !sourceOut || (v2 && !mapOut))
        throw std::runtime_error("ooc cf pilot: cannot open outputs");
    labelOut << "sourceSeed,decisionIdx,type,act,floor,optionIdx,optionKey,chosen,k,futureSeed,"
                "valid,diedBeforeBoss,bossWon,hp,maxHp,horizonAct,horizonFloor,fights,cpuSeconds,error,"
                "horizonBosses,bossesBeaten";
    if (v2) labelOut << ",finalWon,firstBossWon,firstBossHp,firstBossMaxHp,firstBossAct,mapAct,mapFloor";
    labelOut << '\n';
    if (v2) mapOut << "sourceSeed,decisionIdx,type,optionIdx,optionKey,chosen,k,mapAct,mapFloor,"
                   << richStateHeader() << '\n';
    optionOut << "sourceSeed,decisionIdx,type,optionIdx,optionKey,chosen," << richStateHeader() << '\n';
    sourceOut << "sourceSeed,outcome,finalFloor,trajectoryValid,inScopeSamples,decisionIdx,type,"
                 "act,floor,options,sourceCpuSeconds\n";
    std::uint64_t labelRows = 0, validRows = 0;
    std::map<std::string, int> statesByTypeAct;
    int selectedStates = 0;
    for (int index = 0; index < nSeeds; ++index) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + index);
        VwinCollector source;
        source.sourceSeed = seed;
        source.samplesPerType = 1;
        source.branchId = "source";
        source.captureRefresh = true;
        source.allowSampling = true;
        source.cfOptionCapV2 = v2;
        source.cfTarget = target;
        const auto sourceCpuStart = vwinThreadCpuNanos();
        const auto generated = runCombatEvalGenSeed(seed, sims, asc, teacher, true, &source);
        const double sourceCpu = static_cast<double>(vwinThreadCpuNanos() - sourceCpuStart) / 1.0e9;
        std::vector<VwinSampledDecision *> candidates;
        for (auto &[type, samples] : source.sampled)
            if (inScope.count(type))
                for (auto &sample : samples) candidates.push_back(&sample);
        // One state keeps the v1 pilot rule; more states take the next
        // candidates in sha256-ranked order (distinct decision types).
        std::vector<VwinSampledDecision *> selected;
        if (v2) {
            std::vector<std::pair<std::string, VwinSampledDecision *>> ranked;
            for (auto *candidate : candidates)
                ranked.emplace_back(vwinSha256("ooc-cf-pilot-v2-select:" + std::to_string(seed) + ":"
                                               + candidate->type), candidate);
            std::sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) { return a.first < b.first; });
            for (const auto &[hash, candidate] : ranked) {
                if (static_cast<int>(selected.size()) >= statesPerSeed) break;
                selected.push_back(candidate);
            }
        } else if (!candidates.empty()) {
            const auto digest = vwinSha256("ooc-cf-pilot-v1-select:" + std::to_string(seed));
            const std::size_t first = std::stoull(digest.substr(0, 15), nullptr, 16) % candidates.size();
            selected.push_back(candidates[first]);
            std::vector<std::pair<std::string, VwinSampledDecision *>> rest;
            for (std::size_t i = 0; i < candidates.size(); ++i)
                if (i != first)
                    rest.emplace_back(vwinSha256("ooc-cf-pilot-v2-select:" + std::to_string(seed) + ":"
                                                 + candidates[i]->type), candidates[i]);
            std::sort(rest.begin(), rest.end(), [](const auto &a, const auto &b) { return a.first < b.first; });
            for (const auto &[hash, extra] : rest) {
                if (static_cast<int>(selected.size()) >= statesPerSeed) break;
                selected.push_back(extra);
            }
        }
        if (target) {
            if (!generated.trajectoryValid || selected.size() != 1)
                throw std::runtime_error("ooc cf target: source invalid or target not reached exactly once");
            auto &sample = *selected.front();
            const auto publicState = vwinCfPublicTargetState(sample);
            const std::string publicHash = vwinSha256(publicState.dump());
            if (!target->publicStateSha256.empty() && target->publicStateSha256 != publicHash)
                throw std::runtime_error("ooc cf target: public source-state SHA256 mismatch");
            nlohmann::json identity = {{"act", sample.pre->act}, {"floor", sample.pre->floorNum},
                {"screen", "REST"}, {"decisionIdx", sample.decisionIdx},
                {"publicStateSha256", publicHash}, {"chosenKey", sample.chosenKey}};
            if (futures > 0 && preflightReceipt.at("identity") != identity)
                throw std::runtime_error("ooc cf target: captured identity differs from preflight");
            const auto retained = vwinCfTargetOptions(sample.options, sample.chosenKey,
                                                     target->optionKeys, futures == 0);
            nlohmann::json legalKeys = nlohmann::json::array(), retainedKeys = nlohmann::json::array();
            for (const auto &option : sample.options) legalKeys.push_back(option.key);
            for (const auto &option : retained) retainedKeys.push_back(option.key);
            nlohmann::json receipt = {{"schemaVersion", "ooc_cf_target_receipt_v1"},
                {"preflightOnly", futures == 0}, {"binding", targetBinding},
                {"targetPath", std::filesystem::absolute(targetPath).string()},
                {"targetSha256", fileSha256(targetPath)}, {"identity", identity},
                {"publicState", publicState}, {"legalOptionKeys", legalKeys},
                {"retainedOptionKeys", retainedKeys},
                {"futureStart", futureStart}, {"futureCount", futures}};
            std::ofstream targetOut(outPrefix + ".target.json");
            targetOut << receipt.dump(2) << '\n';
            targetOut.close();
            if (!targetOut) throw std::runtime_error("ooc cf target: receipt write failed");
            sample.options = retained;
        }
        if (selected.empty())
            sourceOut << seed << ',' << combatEvalGameOutcome(generated.finalOutcome) << ','
                      << generated.finalFloor << ',' << (generated.trajectoryValid ? 1 : 0) << ','
                      << candidates.size() << ",-1,,-1,-1,0," << sourceCpu << '\n';
        for (auto *sample : selected) {
        sourceOut << seed << ',' << combatEvalGameOutcome(generated.finalOutcome) << ','
                  << generated.finalFloor << ',' << (generated.trajectoryValid ? 1 : 0) << ','
                  << candidates.size() << ',';
        sourceOut << sample->decisionIdx << ',' << sample->type << ',' << sample->pre->act << ','
                  << sample->pre->floorNum << ',' << sample->options.size() << ',' << sourceCpu << '\n';
        ++selectedStates;
        ++statesByTypeAct[sample->type + ":act" + std::to_string(sample->pre->act)];
        const int bosses = v2 ? 1000 : sample->type == "CARD_REWARD" ? cardRewardBosses : 1;
        for (std::size_t optionIdx = 0; optionIdx < sample->options.size(); ++optionIdx) {
            const auto &option = sample->options[optionIdx];
            const bool chosen = option.key == sample->chosenKey;
            for (int j = 0; j < futures; ++j) {
                const int k = futureStart + j;
                const auto futureDigest = vwinSha256(std::string(v2 ? "ooc-cf-pilot-v2-future:" : "ooc-cf-pilot-v1-future:") + std::to_string(seed)
                    + ":" + std::to_string(sample->decisionIdx) + ":" + std::to_string(k));
                const std::uint64_t futureSeed = std::stoull(futureDigest.substr(0, 16), nullptr, 16);
                CfHorizon horizon;
                horizon.bosses = bosses;
                horizon.fullRun = v2;
                VwinBranchStart start{sample, option,
                    "cf" + std::to_string(seed) + "-d" + std::to_string(sample->decisionIdx)
                    + "-o" + std::to_string(optionIdx) + "-k" + std::to_string(k),
                    futureSeed, &horizon, v2};
                VwinCollector branch;
                branch.sourceSeed = seed;
                branch.branchId = start.branchId;
                branch.deviationIdx = 1;
                branch.captureRefresh = true;
                branch.allowSampling = false;
                std::string error;
                bool valid = false;
                const auto cpuStart = vwinThreadCpuNanos();
                try {
                    const auto branched = runCombatEvalGenSeed(seed, sims, asc, teacher, true,
                                                               &branch, &start);
                    valid = horizon.reached && !branched.fatalFailure
                        && branched.simulatorHealthFailures == 0
                        && (!v2 || (horizon.finalWon >= 0 && horizon.mapRecorded));
                    if (!valid)
                        error = !horizon.reached ? "horizon_not_reached"
                            : v2 && horizon.finalWon < 0 ? "run_not_finished"
                            : v2 && !horizon.mapRecorded ? "no_map_after_branch" : "health_or_fatal";
                } catch (const std::exception &e) {
                    error = e.what();
                }
                const double cpu = static_cast<double>(vwinThreadCpuNanos() - cpuStart) / 1.0e9;
                if (j == 0)
                    optionOut << seed << ',' << sample->decisionIdx << ',' << sample->type << ','
                              << optionIdx << ',' << csvQuote(option.key) << ',' << (chosen ? 1 : 0)
                              << ',' << horizon.afterFeatures << '\n';
                labelOut << seed << ',' << sample->decisionIdx << ',' << sample->type << ','
                         << sample->pre->act << ',' << sample->pre->floorNum << ',' << optionIdx << ','
                         << csvQuote(option.key) << ',' << (chosen ? 1 : 0) << ',' << k << ','
                         << futureSeed << ',' << (valid ? 1 : 0) << ','
                         << (horizon.diedBeforeBoss ? 1 : 0) << ',' << horizon.bossWon << ','
                         << horizon.hp << ',' << horizon.maxHp << ',' << horizon.act << ','
                         << horizon.floor << ',' << horizon.fights << ',' << cpu << ','
                         << csvQuote(error) << ',' << bosses << ',' << horizon.bossesBeaten;
                if (v2)
                    labelOut << ',' << horizon.finalWon << ',' << horizon.firstBossWon << ','
                             << horizon.firstBossHp << ',' << horizon.firstBossMaxHp << ','
                             << horizon.firstBossAct << ',' << horizon.mapAct << ','
                             << horizon.mapFloor;
                labelOut << '\n';
                if (v2 && horizon.mapRecorded)
                    mapOut << seed << ',' << sample->decisionIdx << ',' << sample->type << ','
                           << optionIdx << ',' << csvQuote(option.key) << ',' << (chosen ? 1 : 0)
                           << ',' << k << ',' << horizon.mapAct << ',' << horizon.mapFloor << ','
                           << horizon.mapFeatures << '\n';
                ++labelRows;
                if (valid) ++validRows;
            }
        }
        }
        labelOut.flush(); optionOut.flush(); sourceOut.flush();
        if (v2) mapOut.flush();
    }
    labelOut.close(); optionOut.close(); sourceOut.close();
    if (v2) mapOut.close();
    nlohmann::json outputs = nlohmann::json::object();
    for (const auto &suffix : suffixes)
        if (suffix != ".manifest.json")
            outputs[suffix.substr(1)] = fileSha256(outPrefix + suffix);
    nlohmann::json manifest = {
        {"schemaVersion", v2 ? "ooc_cf_pilot_v2" : "ooc_cf_pilot_v1"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherPath", std::filesystem::absolute(teacherPath).string()},
        {"teacherManifestSha256", fileSha256(teacherPath)},
        {"teacherId", teacher.id}, {"combatTeacher", teacher.specification},
        {"policy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"selection", {{"reservoir", "vwinrefreshgen outcome_blind_reservoir_per_type_v1, K=1"},
                       {"types", inScope},
                       {"rule", "sha256(ooc-cf-pilot-v1-select:{seed})[:15] mod in-scope samples"},
                       {"optionCap", "chosen_plus_five_sha256_ranked (vwin-option-cap-334-v1)"}}},
        {"futures", {{"count", futures},
                     {"seedRule", "sha256(ooc-cf-pilot-v1-future:{seed}:{decisionIdx}:{k})[:16]"},
                     {"redraw", "sampleNoncombatFuture after the forced option, before continuation"}}},
        {"statesPerSeed", statesPerSeed},
        {"horizon", {{"rule", "the first N boss fights after the branch, or death or run end before"},
                     {"cardRewardBosses", cardRewardBosses}, {"otherBosses", 1}}},
        {"integrity", {{"selectedStates", selectedStates}, {"labelRows", labelRows},
                       {"validLabelRows", validRows}, {"statesByTypeAct", statesByTypeAct}}},
        {"outputs", outputs},
    };
    if (v2) {
        manifest["selection"]["rule"] = "candidates of TYPES, sha256(ooc-cf-pilot-v2-select:{seed}:{type}) ascending, first STATES_PER_SEED";
        manifest["selection"]["optionCap"] = "ooc-cf-option-cap-v2: dedupe by key with occurrence=*, keep chosen and skip/leave, fill to 6 by sha256(ooc-cf-option-cap-v2:{seed}:{decisionIdx}:{canonicalKey})";
        manifest["futures"]["seedRule"] = "sha256(ooc-cf-pilot-v2-future:{seed}:{decisionIdx}:{k})[:16]";
        manifest["futures"]["redraw"] = "sampleNoncombatFuture before the forced option; published screen and rich row checked unchanged";
        manifest["horizon"] = {{"rule", "whole run; label finalWon; first-boss result and HP after it as diagnostics"}};
        manifest["features"] = {{"options.csv", "rich row right after the forced option (k=0)"},
                                {"map.csv", "rich row at the first MAP screen after the branch, per run"}};
    }
    if (futureStart != 0 || target) {
        manifest["futures"]["start"] = futureStart;
        manifest["features"]["options.csv"] = "rich row right after the forced option (k=FUTURE_START)";
    }
    if (target) {
        manifest["selection"]["reservoir"] = "disabled: one exact initial REST screen";
        manifest["selection"]["rule"] = "sourceSeed, act, floor and REST screen; expected decisionIdx is mandatory for positive futures and optional for preflight";
        manifest["selection"]["optionCap"] = "none: baseline chosen key plus exact requested canonical keys; preflight may inventory all";
        manifest["target"] = {{"path", std::filesystem::absolute(targetPath).string()},
                              {"sha256", fileSha256(targetPath)}, {"specification", targetDocument}};
        manifest["preflightOnly"] = futures == 0;
    }
    std::ofstream manifestOut(outPrefix + ".manifest.json");
    manifestOut << manifest.dump(2) << '\n';
    if (!manifestOut) throw std::runtime_error("ooc cf pilot: manifest write failed");
    std::cout << "ooc cf pilot teacher=" << teacher.id << " states=" << selectedStates << '/' << nSeeds
              << " labels=" << validRows << '/' << labelRows << " -> " << outPrefix << "\n";
}

// Optional extra observations of one boss arm (#347 boss-entry rescue).
struct VwinBossArmDetail {
    std::string startDigest, postExitDigest, postExitSummary;
    std::vector<int> trace;
    std::int64_t searchSteps = 0, minRootSteps = -1, maxRootSteps = -1;
    std::int64_t reroots = 0, freshRoots = 0, singletonSkips = 0;
    double wallSeconds = 0.0;
};
static std::string bossRescueStateDigest(const GameContext &gc, const search::ScumSearchAgent2 *agent);
static std::string bossRescueStateSummary(const GameContext &gc);

static VwinArmResult vwinRunBossArm(const VwinBossEntry &entry, int budget,
                                    const search::NativeSilverSearchParams *params = nullptr,
                                    VwinBossArmDetail *detail = nullptr) {
    struct ParamScope {
        explicit ParamScope(const search::NativeSilverSearchParams *p) {
            if (p) search::g_nativeSilverSearchParamOverride = *p;
        }
        ~ParamScope() { search::g_nativeSilverSearchParamOverride.reset(); }
    } paramScope(params);
    trainingRunStart();
    GameContext gc = detachedCounterfactualCopy(*entry.pre);
    PathHistory path = entry.path;
    search::ScumSearchAgent2 agent = entry.agent;
    if (detail) detail->startDigest = bossRescueStateDigest(gc, &agent);
    const auto totalsBefore = search::nativeSilverTotals();
    const auto wallStart = std::chrono::steady_clock::now();
    agent.simulationCountBase = budget;
    agent.recordActions = true;
    agent.gameActionHistory.clear();
    one_combat::restoreOocPolicyThreadState(entry.policy);
    t_curPath = &path;
    const int healthBefore = search::g_simHealthFailureCount;
    const std::int64_t simulationsBefore = agent.simulationCountTotal;
    CombatEvalDecisionScope decisionScope(true);
    BattleContext bc;
    const std::uint64_t cpuStart = vwinThreadCpuNanos();
    agent.playoutBattle(gc, bc);
    const std::uint64_t cpuEnd = vwinThreadCpuNanos();
    const bool initializationTerminal = decisionScope.hooks == 0
        && bc.turn == 0 && bc.outcome != Outcome::UNDECIDED;
    const auto label = combatEvalTerminal(bc, entry.pre->info.encounter,
        decisionScope.hooks, healthBefore, search::g_simHealthFailureCount,
        initializationTerminal);
    VwinArmResult result;
    result.outcome = bc.outcome == Outcome::PLAYER_VICTORY ? "PLAYER_VICTORY"
        : bc.outcome == Outcome::PLAYER_LOSS ? "PLAYER_LOSS" : "UNDECIDED";
    result.won = bc.outcome == Outcome::PLAYER_VICTORY ? 1
        : bc.outcome == Outcome::PLAYER_LOSS ? 0 : -1;
    result.terminalHp = bc.player.curHp;
    result.postAfterBattleHp = -1;
    result.firstActionBits = agent.gameActionHistory.empty()
        ? -1 : agent.gameActionHistory.front();
    result.signedOutcome = label.signedOutcome;
    result.cpuSeconds = static_cast<double>(cpuEnd - cpuStart) / 1.0e9;
    result.simulations = static_cast<std::uint64_t>(std::max<std::int64_t>(0,
        agent.simulationCountTotal - simulationsBefore));
    result.decisions = static_cast<std::uint64_t>(decisionScope.hooks);
    result.lockStops = search::g_nativeSilverCombatStats.lockStops;
    result.modelStops = search::g_nativeSilverCombatStats.modelStops;
    result.valid = label.labelValid && bc.outcome != Outcome::UNDECIDED;
    if (!result.valid) result.quarantineReason = !label.healthOk ? "simulator_health_failure"
        : decisionScope.hooks == 0 && !initializationTerminal ? "missing_combat_decision_hook"
        : bc.outcome == Outcome::UNDECIDED ? "undecided_combat" : label.reason;
    bc.exitBattle(gc);
    result.postAfterBattleHp = gc.curHp;
    result.potionsAfter = gc.potionCount;
    t_curPath = nullptr;
    if (detail) {
        const auto totalsAfter = search::nativeSilverTotals();
        const auto &stats = search::g_nativeSilverCombatStats;
        detail->wallSeconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - wallStart).count();
        detail->trace = agent.gameActionHistory;
        detail->postExitDigest = bossRescueStateDigest(gc, nullptr);
        detail->postExitSummary = bossRescueStateSummary(gc);
        detail->searchSteps = stats.searchSteps;
        detail->minRootSteps = stats.minRootSteps;
        detail->maxRootSteps = stats.maxRootSteps;
        detail->reroots = totalsAfter.reroots - totalsBefore.reroots;
        detail->freshRoots = totalsAfter.freshRoots - totalsBefore.freshRoots;
        detail->singletonSkips = totalsAfter.singletonSkips - totalsBefore.singletonSkips;
    }
    return result;
}

int vwinRefreshPolicySpec(const std::string &outputPath) {
    std::ofstream out(outputPath);
    if (!out) throw std::runtime_error("vwin policy export: cannot open output");
    out << effectiveOocPolicySpecification().dump(2) << '\n';
    if (!out) throw std::runtime_error("vwin policy export: write failed");
    std::cout << "vwin policy export: PASS\n";
    return 0;
}

int vwinRefreshSelfTest() {
    auto require = [](bool ok, const char *message) {
        if (!ok) throw std::runtime_error(std::string("vwin refresh selftest: ") + message);
    };
    // Exercise the production decision log and reservoir, using real semantic
    // options: treasure must not evict an unrelated selector at K=1.
    VwinCollector typeCapture;
    typeCapture.sourceSeed = 0x334006;
    typeCapture.allowSampling = true;
    typeCapture.samplesPerType = 1;
    PathHistory typePath;
    auto recordType = [&](const GameContext &gc) {
        bool supported = false, complete = false;
        std::string error;
        const auto options = vwinOptions(gc, supported, complete, error);
        require(supported && complete && !options.empty(), "type fixture enumerates options");
        return vwinBeginDecision(typeCapture, gc, typePath, options,
                                 vwinScreenDecisionType(gc), options.front().key,
                                 supported, complete, error);
    };
    GameContext treasure(CharacterClass::IRONCLAD, typeCapture.sourceSeed, 0);
    treasure.screenState = ScreenState::TREASURE_ROOM;
    treasure.curRoom = Room::TREASURE;
    const auto treasureRow = recordType(treasure);
    GameContext selector(CharacterClass::IRONCLAD, typeCapture.sourceSeed, 0);
    selector.curRoom = Room::EVENT;
    selector.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
    const auto selectorRow = recordType(selector);
    const bool treasureTypes = typeCapture.decisions[treasureRow].type == "TREASURE"
        && typeCapture.decisions[treasureRow].candidateKeys.size() == 2
        && typeCapture.decisions[selectorRow].type == "OTHER_SELECTOR"
        && typeCapture.eligibleByType["TREASURE"] == 1
        && typeCapture.eligibleByType["OTHER_SELECTOR"] == 1
        && typeCapture.sampled["TREASURE"].size() == 1
        && typeCapture.sampled["OTHER_SELECTOR"].size() == 1;
    bool finalMapTypes = true;
    for (int act = 1; act <= 3; ++act) {
        GameContext bossMap(CharacterClass::IRONCLAD, typeCapture.sourceSeed, 0);
        bossMap.act = act;
        bossMap.screenState = ScreenState::MAP_SCREEN;
        bossMap.curRoom = Room::REST;
        bossMap.curMapNodeY = 14;
        const auto row = recordType(bossMap);
        finalMapTypes = finalMapTypes && typeCapture.decisions[row].type == "MAP"
            && typeCapture.decisions[row].candidateKeys.size() == 1;
    }
    require(typeCapture.eligibleByType.count("REST") == 0
                && typeCapture.eligibleByType.count("MAP") == 0,
            "singleton boss links do not enter a sampling pool");
    // Report both regressions if both labels are wrong.
    std::string typeFailures;
    if (!treasureTypes) typeFailures += "TREASURE and OTHER_SELECTOR must have separate K=1 pools; ";
    if (!finalMapTypes) typeFailures += "row-14 boss links must be logged as MAP in all three acts; ";
    require(typeFailures.empty(), typeFailures.c_str());

    const auto effectivePolicy = effectiveOocPolicySpecification();
    require(vwinTeacherNativeOocEnabled(effectivePolicy),
            "teacher native_ooc binding reads the top-level policy field");
    const auto &policyFlags = effectivePolicy.at("flags");
    require(!vwinTeacherFlagEnabled(policyFlags, "path_v")
            && !vwinTeacherFlagEnabled(policyFlags, "event_v"),
            "teacher policy guard reads integer-valued path/event flags");
    std::vector<VwinOption> options;
    for (int i = 0; i < 12; ++i)
        options.push_back({"option:" + std::to_string(i), static_cast<std::uint32_t>(i),
                           true, std::nullopt});
    const std::string chosen = "option:8";
    const auto cappedA = vwinLimitOptions(options, chosen, 13000000, 17);
    std::reverse(options.begin(), options.end());
    const auto cappedB = vwinLimitOptions(options, chosen, 13000000, 17);
    require(cappedA.size() == 6 && cappedB.size() == 6, "option cap is exactly six");
    require(std::any_of(cappedA.begin(), cappedA.end(), [&](const auto &option) {
        return option.key == chosen;
    }), "option cap retains chosen option");
    std::vector<std::string> keysA, keysB;
    for (const auto &option : cappedA) keysA.push_back(option.key);
    for (const auto &option : cappedB) keysB.push_back(option.key);
    std::sort(keysA.begin(), keysA.end());
    std::sort(keysB.begin(), keysB.end());
    require(keysA == keysB, "option cap is input-order independent");
    require(vwinLimitOptions({options[0], options[1]}, options[0].key, 1, 1).size() == 2,
            "option cap preserves small option sets");
    {
        nlohmann::json request = {{"schemaVersion", "ooc_cf_target_v1"},
            {"sourceSeed", 0x334006}, {"act", 3}, {"floor", 48},
            {"screen", "REST"}, {"optionKeys", nlohmann::json::array()}};
        const auto target = vwinParseCfTarget(request, 0x334006, true);
        require(target.act == 3 && target.floor == 48 && target.decisionIdx == -1,
                "target preflight accepts exact REST location");
        bool rejected = false;
        try { (void)vwinParseCfTarget(request, 0x334006, false); }
        catch (const std::exception &) { rejected = true; }
        require(rejected, "positive futures require frozen preflight identity");
        request["decisionIdx"] = 71;
        request["publicStateSha256"] = std::string(64, 'a');
        request["preflightReceiptPath"] = "fixture.target.json";
        request["preflightReceiptSha256"] = std::string(64, 'b');
        request["optionKeys"] = {options.front().key};
        require(vwinParseCfTarget(request, 0x334006, false).decisionIdx == 71,
                "target production request binds observer identity");
        request["optionKeys"] = {options.front().key, options.front().key};
        rejected = false;
        try { (void)vwinParseCfTarget(request, 0x334006, false); }
        catch (const std::exception &) { rejected = true; }
        require(rejected, "target rejects duplicate requested keys");
        const auto retained = vwinCfTargetOptions(options, chosen, {options.front().key}, false);
        require(retained.size() == 2
            && std::any_of(retained.begin(), retained.end(), [&](const auto &o) { return o.key == chosen; }),
            "target keeps actual baseline and named alternative exactly");
        require(vwinCfTargetOptions(options, chosen, {}, true).size() == options.size(),
                "target preflight inventory is not truncated to six");
        std::vector<std::string> all;
        for (const auto &option : options) all.push_back(option.key);
        require(vwinCfTargetOptions(options, chosen, all, false).size() == options.size(),
                "explicit target keys are not truncated to six");
        rejected = false;
        try { (void)vwinCfTargetOptions(options, chosen, {"missing:semantic:key"}, false); }
        catch (const std::exception &) { rejected = true; }
        require(rejected, "target rejects absent named alternative");

        VwinCollector capture;
        capture.sourceSeed = 0x334006;
        capture.allowSampling = true; capture.samplesPerType = 1;
        capture.cfOptionCapV2 = true; capture.cfTarget = target;
        GameContext rest(CharacterClass::IRONCLAD, capture.sourceSeed, 0);
        rest.act = 3; rest.floorNum = 48; rest.screenState = ScreenState::REST_ROOM;
        rest.curRoom = Room::REST;
        bool supported = false, complete = false; std::string error;
        const auto legal = vwinOptions(rest, supported, complete, error);
        require(supported && complete && legal.size() >= 2, "target REST fixture has semantic siblings");
        auto offTarget = rest; offTarget.floorNum = 47;
        (void)vwinBeginDecision(capture, offTarget, typePath, legal, "REST", legal.front().key,
                                supported, complete, error);
        require(capture.sampled.empty(), "non-target rest ignored without entering reservoir");
        (void)vwinBeginDecision(capture, rest, typePath, legal, "REST", legal.front().key,
                                supported, complete, error);
        require(capture.sampled.at("REST").size() == 1 && capture.reservoirRng.empty(),
                "exact target captured without reservoir RNG");
        auto &sample = capture.sampled.at("REST").front();
        const auto publicState = vwinCfPublicTargetState(sample);
        sample.pre->seed ^= 99;
        sample.pre->monsterRng.seed0 ^= 123;
        std::reverse(sample.pre->monsterList.begin(), sample.pre->monsterList.end());
        std::reverse(sample.pre->eliteMonsterList.begin(), sample.pre->eliteMonsterList.end());
        require(publicState == vwinCfPublicTargetState(sample),
                "target public-state receipt excludes true seed/RNG/future fields");
        ++sample.pre->gold;
        require(publicState != vwinCfPublicTargetState(sample),
                "target public-state receipt detects visible-state mismatch");
        rejected = false;
        try {
            (void)vwinBeginDecision(capture, rest, typePath, legal, "REST", legal.front().key,
                                    supported, complete, error);
        } catch (const std::exception &) { rejected = true; }
        require(rejected, "target rejects ambiguous repeated matching screen");
    }
    require(vwinSha256("vwin-refresh-selftest").size() == 64,
            "SHA256 identity has 64 lowercase hex characters");
    auto reservoirSelections = [](std::uint64_t seed) {
        const auto digest = vwinSha256("vwin-refresh-334-v1:" + std::to_string(seed) + ":MAP");
        const auto initial = std::stoull(digest.substr(0, 16), nullptr, 16);
        std::mt19937_64 rng(initial);
        std::vector<int> reservoir;
        constexpr int capacity = 5;
        for (int seen = 1; seen <= 257; ++seen) {
            const auto slot = vwinReservoirSlot(rng, seen, capacity, reservoir.size());
            if (!slot) continue;
            if (*slot == reservoir.size()) reservoir.push_back(seen);
            else reservoir[*slot] = seen;
        }
        std::sort(reservoir.begin(), reservoir.end());
        return reservoir;
    };
    for (const std::uint64_t seed : {13000000ULL, 13000001ULL})
        require(reservoirSelections(seed) == reservoirSelections(seed),
                "reservoir helper is repeatable for each seed");

    std::default_random_engine sourceRng(112233);
    auto copiedRng = sourceRng;
    (void)copiedRng();
    require(sourceRng() == std::default_random_engine(112233)(),
            "agent RNG copy is isolated");
    search::ScumSearchAgent2 sourceAgent;
    sourceAgent.simulationCountBase = 10000;
    sourceAgent.rng = std::default_random_engine(112233);
    auto branchAgent = sourceAgent;
    branchAgent.simulationCountBase = 100000;
    (void)branchAgent.rng();
    require(sourceAgent.simulationCountBase == 10000
            && sourceAgent.rng == std::default_random_engine(112233),
            "agent budget and RNG copy are isolated");

    const auto savedPolicy = one_combat::captureOocPolicyThreadState();
    auto alteredPolicy = savedPolicy;
    alteredPolicy.pathActionUses += 7;
    alteredPolicy.pathAggr += 1.25;
    alteredPolicy.tokCheckPending = !savedPolicy.tokCheckPending;
    alteredPolicy.shopV = !savedPolicy.shopV;
    alteredPolicy.strategicTraceRows += "fixture";
    alteredPolicy.strategicTraceDecision += 3;
    alteredPolicy.actFightProbeDecisionIdx += 4;
    alteredPolicy.actFightProbeActionIdx += 5;
    alteredPolicy.actFightProbeFutureIdx += 6;
    one_combat::restoreOocPolicyThreadState(alteredPolicy);
    const auto restoredPolicy = one_combat::captureOocPolicyThreadState();
    const bool policyCopied = restoredPolicy.pathActionUses == alteredPolicy.pathActionUses
        && restoredPolicy.pathAggr == alteredPolicy.pathAggr
        && restoredPolicy.tokCheckPending == alteredPolicy.tokCheckPending
        && restoredPolicy.shopV == alteredPolicy.shopV
        && restoredPolicy.strategicTraceRows == alteredPolicy.strategicTraceRows
        && restoredPolicy.strategicTraceDecision == alteredPolicy.strategicTraceDecision
        && restoredPolicy.actFightProbeDecisionIdx == alteredPolicy.actFightProbeDecisionIdx
        && restoredPolicy.actFightProbeActionIdx == alteredPolicy.actFightProbeActionIdx
        && restoredPolicy.actFightProbeFutureIdx == alteredPolicy.actFightProbeFutureIdx;
    one_combat::restoreOocPolicyThreadState(savedPolicy);
    require(policyCopied, "OOC policy thread state copy/restore");
    require(one_combat::captureOocPolicyThreadState().pathActionUses == savedPolicy.pathActionUses,
            "OOC policy thread state restoration");

    std::stringstream featureHeader(richStateHeader());
    std::string feature;
    int featureCount = 0;
    while (std::getline(featureHeader, feature, ',')) ++featureCount;
    require(featureCount == 1017, "rich state feature schema is 1,017 columns");
    require(vwinThreadCpuNanos() > 0, "thread CPU clock is available");
    std::cout << "vwin refresh contract: treasure/selector sampling pools and final MAP labels, "
                 "deterministic option cap and per-seed reservoir helper, "
                 "targeted REST identity/public-state/explicit-key gates, "
                 "detached agent/policy snapshots, "
                 "1,017-feature header, and thread CPU clock passed\n";
    return 0;
}

static std::string vwinCompoundStateFingerprint(const GameContext &gc) {
    std::ostringstream out;
    out << static_cast<int>(gc.screenState) << ':' << static_cast<int>(gc.curRoom) << ':'
        << static_cast<int>(gc.curEvent) << ':' << gc.act << ':' << gc.floorNum << ':'
        << gc.curHp << ':' << gc.maxHp << ':' << gc.gold << ':' << gc.deck.size() << ':';
    for (const auto &card : gc.deck.cards)
        out << static_cast<int>(card.id) << '/' << card.misc << '/' << card.upgraded << ';';
    return out.str();
}

int vwinRefreshDecisionSinkSelfTest() {
    auto require = [](bool value, const std::string &why) {
        if (!value) throw std::runtime_error("vwin DECISION selftest: " + why);
    };
    using Action = search::GameAction;
    using RewardAction = Action::RewardsActionType;
    const WholeCombatTeacher teacher{"decision-sink-fixture", nlohmann::json::object()};
    auto legacyOutput = [&](const VwinCollector &capture) {
        std::ostringstream map, raw, decisions, combat;
        vwinWriteCollector(map, raw, decisions, nullptr, combat, capture.sourceSeed,
                           capture, 0, teacher);
        return std::vector<std::string>{map.str(), raw.str(), decisions.str(), combat.str()};
    };
    auto run = [&](const GameContext &initial, const std::vector<Action> &actions, bool enabled) {
        auto gc = detachedCounterfactualCopy(initial);
        VwinCollector capture;
        capture.sourceSeed = initial.seed;
        capture.captureDecisionSink = enabled;
        capture.allowSampling = true;
        capture.samplesPerType = 1;
        PathHistory path;
        search::ScumSearchAgent2 agent;
        for (const auto &action : actions)
            vwinObservePolicyStep(capture, gc, path, agent, [&] { action.execute(gc); });
        require(!capture.pendingSinkAction, "fixture resolves its compound decisions");
        return capture;
    };
    // Use a synthetic unsupported selector, independent of which real events
    // the simulator currently implements. Exercise the production observer
    // around a fixture policy step and then a real supported treasure action.
    auto unsupportedRun = [&](bool enabled) {
        GameContext gc(CharacterClass::IRONCLAD, 0x334007, 0);
        gc.curRoom = Room::EVENT;
        gc.screenState = ScreenState::CARD_SELECT;
        gc.info.selectScreenType = CardSelectScreenType::INVALID;
        gc.regainControlAction = [](GameContext &next) { next.screenState = ScreenState::MAP_SCREEN; };
        const auto enumeration = search::enumerateOocSemanticActions(gc);
        require(!enumeration.supported && !enumeration.complete && !enumeration.error.empty(),
                "synthetic fixture must actually have unsupported selector semantics");
        VwinCollector capture;
        capture.sourceSeed = gc.seed;
        capture.captureDecisionSink = enabled;
        PathHistory path;
        search::ScumSearchAgent2 agent;
        vwinObservePolicyStep(capture, gc, path, agent, [&] {
            search::g_onGameActionExecute(Action(0).bits, &gc);
            // Only the synthetic policy step supplies this transition; no
            // invalid action is executed against the simulator.
            gc.screenState = ScreenState::TREASURE_ROOM;
            gc.curRoom = Room::TREASURE;
        });
        require(gc.screenState == ScreenState::TREASURE_ROOM,
                "unsupported fixture step completes and reaches the next screen");
        vwinObservePolicyStep(capture, gc, path, agent, [&] { Action(1).execute(gc); });
        return capture;
    };
    const auto unsupportedOff = unsupportedRun(false);
    const auto unsupportedOn = unsupportedRun(true);
    require(legacyOutput(unsupportedOff) == legacyOutput(unsupportedOn)
            && unsupportedOff.trace == unsupportedOn.trace,
            "unsupported screen preserves legacy errors and continuation with capture enabled");
    require(unsupportedOn.decisionSinkRows.size() == 1
            && unsupportedOn.decisionSinkRows.front().rowIdx == 0
            && unsupportedOn.decisionSinkRows.front().screen == "treasure"
            && unsupportedOn.decisionSinkLog[0]["rowIdx"] == -1
            && unsupportedOn.decisionSinkLog[0]["supported"] == false
            && !unsupportedOn.decisionSinkLog[0]["error"].get<std::string>().empty(),
            "unsupported capture is logged and a later supported screen is captured");

    VwinCollector skipped;
    skipped.captureDecisionSink = true;
    PathHistory skippedPath;
    GameContext partial(CharacterClass::IRONCLAD, 0x334008, 0);
    partial.screenState = ScreenState::BOSS_RELIC_REWARDS;
    std::fill(std::begin(partial.info.bossRelics), std::end(partial.info.bossRelics), RelicId::INVALID);
    vwinObserveDecisionScreen(skipped, partial, skippedPath, Action(3).bits, -1);
    partial.info.bossRelics[0] = RelicId::BLACK_BLOOD;
    vwinObserveDecisionScreen(skipped, partial, skippedPath, Action(3).bits, -1);
    require(skipped.decisionSinkRows.empty()
            && skipped.decisionSinkLog[0]["optionCount"] == 1
            && skipped.decisionSinkLog[1]["optionCount"] == 2
            && skipped.decisionSinkLog[0]["complete"] == false
            && skipped.decisionSinkLog[1]["complete"] == false,
            "partial enumerations with one or multiple candidates are logged without rows");
    GameContext singleton(CharacterClass::IRONCLAD, 0x334009, 0);
    singleton.openCombatRewardScreen(Rewards{});
    vwinObserveDecisionScreen(skipped, singleton, skippedPath, Action(99).bits, -1);
    require(skipped.decisionSinkLog.back()["optionCount"] == 1
            && skipped.decisionSinkLog.back()["error"] == "",
            "singleton returns before attempting a chosen-key match");
    partial.screenState = ScreenState::TREASURE_ROOM;
    partial.curRoom = Room::TREASURE;
    vwinObserveDecisionScreen(skipped, partial, skippedPath, Action(99).bits, -1);
    require(skipped.decisionSinkLog.back()["error"] == "chosen_primitive_binding_unresolved",
            "unmatched primitive is a capture error, not an exception");
    vwinObserveDecisionScreen(skipped, partial, skippedPath, Action(1).bits, -1);
    require(skipped.decisionSinkRows.size() == 1 && skipped.decisionSinkRows[0].rowIdx == 0,
            "skipped screens do not consume row indices");

    GameContext smith(CharacterClass::IRONCLAD, 0x334010, 0);
    smith.screenState = ScreenState::REST_ROOM;
    smith.curRoom = Room::REST;
    smith.regainControlAction = [](GameContext &gc) { gc.screenState = ScreenState::MAP_SCREEN; };
    VwinCollector unresolved;
    unresolved.captureDecisionSink = true;
    vwinObserveDecisionScreen(unresolved, smith, skippedPath, Action(1).bits, -1);
    Action(1).execute(smith);
    vwinObserveDecisionScreen(unresolved, smith, skippedPath, Action(0).bits, -1);
    require(unresolved.pendingSinkAction.has_value() && unresolved.decisionSinkRows.size() == 2,
            "compound reserves a parent row before the valid selector row");
    // Inject a missing/unmatchable observed target without executing an invalid action.
    unresolved.pendingSinkAction->observedPrimitiveBits.back() = Action(99).bits;
    Action(0).execute(smith);
    vwinFinishDecisionSink(unresolved, &smith);
    vwinObserveDecisionScreen(unresolved, partial, skippedPath, Action(1).bits, -1);
    require(!unresolved.pendingSinkAction && unresolved.decisionSinkRows.size() == 2
            && unresolved.decisionSinkRows[0].screen == "selector"
            && unresolved.decisionSinkRows[0].rowIdx == 0
            && unresolved.decisionSinkRows[1].rowIdx == 1
            && unresolved.decisionSinkLog[0]["rowIdx"] == -1
            && unresolved.decisionSinkLog[0]["error"] == "compound_selector_semantic_binding_unresolved"
            && unresolved.decisionSinkLog[1]["rowIdx"] == 0
            && unresolved.decisionSinkLog[2]["rowIdx"] == 1,
            "unresolved compound preserves valid later rows and contiguous log joins");

    GameContext shop(CharacterClass::IRONCLAD, 0x334005, 0);
    shop.screenState = ScreenState::SHOP_ROOM;
    shop.curRoom = Room::SHOP;
    shop.gold = 500;
    shop.regainControlAction = [](GameContext &gc) { gc.screenState = ScreenState::MAP_SCREEN; };
    std::fill(std::begin(shop.info.shop.prices), std::end(shop.info.shop.prices), -1);
    shop.info.shop.cards[0] = Card(CardId::BASH);
    shop.info.shop.cardPrice(0) = 42;
    shop.info.shop.cards[1] = Card(CardId::INFLAME);
    shop.info.shop.cardPrice(1) = 61;
    shop.info.shop.removeCost = 75;
    const std::vector<Action> purchases{
        Action(RewardAction::CARD, 0), Action(RewardAction::CARD, 1), Action(RewardAction::SKIP)};
    const auto off = run(shop, purchases, false);
    const auto on = run(shop, purchases, true);
    require(off.decisionSinkRows.empty(), "sink defaults off");
    require(on.decisionSinkRows.size() == 3, "two shop purchases plus leave produce three rows");
    require(legacyOutput(off) == legacyOutput(on) && off.trace == on.trace,
            "shop capture preserves every legacy output and replay trace");
    for (int i = 0; i < 3; ++i) {
        const auto &row = on.decisionSinkRows[i];
        const auto contents = nlohmann::json::parse(row.screenContentsJson);
        require(row.rowIdx == i && row.screen == "shop", "shop rows are ordered");
        require(contents["cards"][0]["price"] == (i == 0 ? 42 : -1)
                && contents["cards"][1]["price"] == (i < 2 ? 61 : -1)
                && contents["removeCost"] == 75,
                "each shop snapshot captures its own remaining inventory");
        require(row.candidateKeys.size() > 1
                && std::find(row.candidateKeys.begin(), row.candidateKeys.end(), row.chosenKey)
                    != row.candidateKeys.end(), "chosen semantic key is in the full candidate set");
    }
    const auto &offSample = off.sampled.at("SHOP").front();
    const auto &onSample = on.sampled.at("SHOP").front();
    require(offSample.decisionIdx == onSample.decisionIdx
            && offSample.chosenKey == onSample.chosenKey
            && offSample.sourceTraceIndex == onSample.sourceTraceIndex,
            "capture preserves reservoir selection and replay suffix indexing");

    GameContext reward(CharacterClass::IRONCLAD, 0x334006, 0);
    Rewards items;
    items.addGold(35);
    CardReward cards;
    cards.push_back(Card(CardId::BASH));
    cards.push_back(Card(CardId::INFLAME));
    items.addCardReward(cards);
    reward.openCombatRewardScreen(items);
    reward.regainControlAction = [](GameContext &gc) { gc.screenState = ScreenState::MAP_SCREEN; };
    const std::vector<Action> pickups{
        Action(RewardAction::GOLD, 0), Action(RewardAction::CARD, 0, 0), Action(RewardAction::SKIP)};
    const auto rewardsOff = run(reward, pickups, false);
    const auto rewardsOn = run(reward, pickups, true);
    require(rewardsOn.decisionSinkRows.size() == 2,
            "rewards capture includes gold pickup and card choice, omits singleton leave");
    require(rewardsOn.decisionSinkRows[0].decisionIdx == -1
            && rewardsOn.decisionSinkRows[1].decisionIdx == 0,
            "capture-only reward pickup does not consume a sampling decision index");
    require(legacyOutput(rewardsOff) == legacyOutput(rewardsOn)
            && rewardsOff.trace == rewardsOn.trace,
            "reward capture preserves the card-reward log and sampling trace");
    const auto before = nlohmann::json::parse(rewardsOn.decisionSinkRows[0].screenContentsJson);
    const auto after = nlohmann::json::parse(rewardsOn.decisionSinkRows[1].screenContentsJson);
    require(before["gold"].size() == 1 && after["gold"].empty()
            && before["cardRewards"] == after["cardRewards"],
            "reward snapshots contain exactly the still-unclaimed items");
    std::ostringstream map, raw, decisions, decisionSink, combat;
    vwinWriteCollector(map, raw, decisions, &decisionSink, combat, rewardsOn.sourceSeed,
                       rewardsOn, 1, teacher);
    const auto header = vwinDecisionSinkHeader();
    require(std::count(header.begin(), header.end(), ',') + 1 == 1029,
            "DECISION schema retains the unchanged 1017 rich features");
    const auto sinkText = decisionSink.str();
    require(std::count(sinkText.begin(), sinkText.end(), '\n') == 2,
            "writer emits one row per captured decision");
    std::cout << "vwin DECISION contract: unsupported/incomplete/unmatched capture continuation, "
                 "compound-error row joins, sequential shop states, reward pickups, schema, "
                 "unchanged sampling and legacy outputs passed\n";
    return 0;
}

int vwinRefreshRewardTypeSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("vwin reward type selftest: " + message);
    };
    GameContext gc(CharacterClass::IRONCLAD, 0x334334ULL, 0);
    Rewards rewards;
    rewards.addGold(50);
    rewards.addPotion(Potion::BLOCK_POTION);
    rewards.addRelic(RelicId::ANCHOR);
    CardReward firstGroup;
    firstGroup.push_back(Card(CardId::BASH));
    firstGroup.push_back(Card(CardId::STRIKE_RED));
    CardReward secondGroup;
    secondGroup.push_back(Card(CardId::DEFEND_RED));
    secondGroup.push_back(Card(CardId::IRON_WAVE));
    rewards.addCardReward(firstGroup);
    rewards.addCardReward(secondGroup);
    gc.openCombatRewardScreen(rewards);

    bool supported = false, complete = false;
    std::string error;
    auto options = vwinOptions(gc, supported, complete, error);
    require(supported && complete, "mixed reward screen enumeration is complete: " + error);
    using Effect = search::OocSemanticEffect;
    auto findEffect = [&](Effect effect) {
        return std::find_if(options.begin(), options.end(), [&](const auto &option) {
            return option.semantic && option.semantic->effect == effect;
        });
    };
    const auto card = findEffect(Effect::TAKE_CARD);
    const auto skip = findEffect(Effect::SKIP_CARD_REWARD);
    require(card != options.end() && skip != options.end(),
            "card take and skip alternatives exist");
    require(vwinDecisionType(gc, options, card->key, card->primitiveBits) == "CARD_REWARD"
            && vwinDecisionType(gc, options, skip->key, skip->primitiveBits) == "CARD_REWARD",
            "taking or skipping a card is labelled CARD_REWARD");

    const auto cardGroupOptions = vwinCardRewardGroupOptions(options, card->key);
    require(cardGroupOptions.size() == 3,
            "card sample contains exactly the selected group's two cards and skip");
    require(std::all_of(cardGroupOptions.begin(), cardGroupOptions.end(), vwinIsCardRewardChoice),
            "card sample excludes gold, potion, relic, and leave actions");
    require(std::any_of(cardGroupOptions.begin(), cardGroupOptions.end(), [&](const auto &option) {
        return option.key == card->key;
    }), "card sample retains the chosen card");
    require(std::any_of(cardGroupOptions.begin(), cardGroupOptions.end(), [&](const auto &option) {
        return option.key == skip->key;
    }), "card sample retains the selected group's skip option");

    for (const auto effect : {Effect::TAKE_GOLD, Effect::TAKE_POTION,
                              Effect::TAKE_RELIC, Effect::LEAVE_REWARDS}) {
        const auto pickup = findEffect(effect);
        require(pickup != options.end(), "reward fixture includes a non-card action");
        require(vwinDecisionType(gc, options, pickup->key, pickup->primitiveBits).empty(),
                "non-card reward action is skipped instead of labelled CARD_REWARD");
    }

    gc.relics.add({RelicId::SINGING_BOWL, 0});
    error.clear();
    options = vwinOptions(gc, supported, complete, error);
    const auto bowl = std::find_if(options.begin(), options.end(), [&](const auto &option) {
        return option.semantic && option.semantic->effect == Effect::SINGING_BOWL;
    });
    require(bowl != options.end(), "Singing Bowl skip action exists");
    require(vwinDecisionType(gc, options, bowl->key, bowl->primitiveBits) == "CARD_REWARD",
            "Singing Bowl skip remains a card-reward choice");
    const auto bowlOptions = vwinCardRewardGroupOptions(options, bowl->key);
    require(bowlOptions.size() == 3
            && std::all_of(bowlOptions.begin(), bowlOptions.end(), vwinIsCardRewardChoice),
            "Singing Bowl alternatives remain limited to that card group");

    std::cout << "vwin reward type contract: card take/skip sampled by group; pickups skipped\n";
    return 0;
}

int vwinRefreshMatchAndKeepSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("vwin Match and Keep selftest: " + message);
    };
    struct FixtureGuard {
        WinNet floor = g_floorNet;
        bool tok = g_oocStrategicTokNet.ok, native = g_nativeOoc, cardWin = g_cardWin,
             cardNN = g_cardNN, cardAction = g_cardAction, actionNN = g_oocActionNN;
        int bossV = g_bossV;
        double skip = g_cardSkipThresh;
        const PathHistory *path = t_curPath;
        OocPolicyThreadState policy = one_combat::captureOocPolicyThreadState();
        decltype(search::g_onGameActionExecute) observer = search::g_onGameActionExecute;
        ~FixtureGuard() {
            g_floorNet = floor; g_oocStrategicTokNet.ok = tok; g_nativeOoc = native;
            g_cardWin = cardWin; g_cardNN = cardNN; g_cardAction = cardAction;
            g_oocActionNN = actionNN; g_bossV = bossV; g_cardSkipThresh = skip;
            t_curPath = path; one_combat::restoreOocPolicyThreadState(policy);
            search::g_onGameActionExecute = observer;
        }
    } guard;
    g_oocStrategicTokNet.ok = false;
    g_nativeOoc = true;
    g_cardWin = g_cardNN = g_cardAction = g_oocActionNN = false;
    g_bossV = 0;
    g_cardSkipThresh = 0.5;
    search::g_onGameActionExecute = {};
    // Real fallback evaluation wants the first Fiend Fire, but not a duplicate.
    g_floorNet = WinNet{};
    g_floorNet.ok = true;
    g_floorNet.logistic = false;
    const int ff = richIdxMap().at("d" + std::to_string(int(CardId::FIEND_FIRE)));
    g_floorNet.nodes = {{ff, 0.5f, 1, 2}, {-1, 1.0f, 0, 0},
                       {ff, 1.5f, 3, 4}, {-1, 2.0f, 0, 0}, {-1, 0.0f, 0, 0}};
    g_floorNet.roots = {0, g_floorNet.nodes.size()};
    one_combat::restoreOocPolicyThreadState(OocPolicyThreadState{});
    const auto sampled = one_combat::captureOocPolicyThreadState();
    GameContext source(CharacterClass::IRONCLAD, 0x334115, 0);
    source.act = 3; source.floorNum = 42;
    source.curRoom = Room::EVENT; source.curEvent = Event::MATCH_AND_KEEP;
    source.screenState = ScreenState::EVENT_SCREEN;
    source.info.eventData = 5;
    source.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    source.info.toSelectCards.clear();
    for (int i = 0; i < 12; ++i) {
        source.info.toSelectCards.push_back({Card(i < 2 ? CardId::FIEND_FIRE : CardId::BASH),
            i < 4 ? GameContext::MATCH_AND_KEEP_SEEN : GameContext::MATCH_AND_KEEP_UNSEEN});
    }
    PathHistory path;
    t_curPath = &path;
    search::ScumSearchAgent2 agent;
    auto step = [&](GameContext &gc) { runFullRunOocPolicyStep(gc, agent, false, false); };
    const auto key = std::make_pair(int(CardId::FIEND_FIRE), false);
    auto siblingA = detachedCounterfactualCopy(source);
    siblingA.obtainCard(Card(CardId::FIEND_FIRE));
    step(siblingA);
    require(siblingA.info.toSelectCards[4].deckIdx == GameContext::MATCH_AND_KEEP_FACE_UP,
            "altered sibling rejects the known Fiend Fire pair and explores slot four");
    one_combat::restoreOocPolicyThreadState(sampled);
    auto siblingB = detachedCounterfactualCopy(source);
    step(siblingB);
    require(siblingB.info.toSelectCards[0].deckIdx == GameContext::MATCH_AND_KEEP_FACE_UP,
            "restored sibling must accept Fiend Fire instead of inheriting sibling A's rejection");
    const auto midEvent = one_combat::captureOocPolicyThreadState();
    require(midEvent.matchAndKeepWant.seed == source.seed
            && midEvent.matchAndKeepWant.act == 3 && midEvent.matchAndKeepWant.floor == 42
            && midEvent.matchAndKeepWant.want.at(key), "event identity and preference are captured");
    require(sampled.matchAndKeepWant.want.empty(), "captured map is an independent value copy");
    require(t_curPath == &path && !t_oocHypotheticalStep,
            "real hypothetical card valuation restores path and policy-call marker");

    // A nested branch changes the cache, then restores the populated outer snapshot.
    one_combat::restoreOocPolicyThreadState(sampled);
    auto nested = detachedCounterfactualCopy(source);
    nested.obtainCard(Card(CardId::FIEND_FIRE));
    step(nested);
    require(!one_combat::captureOocPolicyThreadState().matchAndKeepWant.want.at(key),
            "nested altered branch really computed the opposite preference");
    one_combat::restoreOocPolicyThreadState(midEvent);
    const auto restored = one_combat::captureOocPolicyThreadState().matchAndKeepWant;
    require(restored.seed == midEvent.matchAndKeepWant.seed
            && restored.act == midEvent.matchAndKeepWant.act
            && restored.floor == midEvent.matchAndKeepWant.floor
            && restored.want == midEvent.matchAndKeepWant.want,
            "nested restore preserves the complete populated cache");
    // Even if the deck changes, the original preference must persist within the
    // same event. Clearing/revaluing on every click would reject this second pick.
    siblingB.obtainCard(Card(CardId::FIEND_FIRE));
    const int before = siblingB.deck.size();
    step(siblingB);
    require(siblingB.deck.size() == before + 1
            && siblingB.info.toSelectCards[1].deckIdx == GameContext::MATCH_AND_KEEP_MATCHED,
            "same-event second click reuses the cached preference");
    auto nextEvent = detachedCounterfactualCopy(source);
    ++nextEvent.floorNum;
    nextEvent.obtainCard(Card(CardId::FIEND_FIRE));
    step(nextEvent);
    require(nextEvent.info.toSelectCards[4].deckIdx == GameContext::MATCH_AND_KEEP_FACE_UP
            && !one_combat::captureOocPolicyThreadState().matchAndKeepWant.want.at(key),
            "different event identity retains ordinary lazy invalidation");
    std::cout << "vwin Match and Keep: PASS; sibling isolation, populated snapshot, "
                 "nested restore, hypothetical scope, same-event reuse and lazy invalidation\n";
    return 0;
}

int vwinRefreshContinuationSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("vwin continuation selftest: " + message);
    };
    struct FixtureGuard {
        std::unique_ptr<OocStrategicTokNet> tok = std::make_unique<OocStrategicTokNet>(g_oocStrategicTokNet);
        WinNet floor = g_floorNet;
        bool native = g_nativeOoc, cardWin = g_cardWin, cardNN = g_cardNN,
             cardAction = g_cardAction, regret = g_oocStrategicGateRegret;
        int bossV = g_bossV;
        double threshold = g_cardSkipThresh, margin = g_oocStrategicMarginCard;
        std::string trace = g_oocStrategicTracePath;
        const PathHistory *path = t_curPath;
        OocPolicyThreadState policy = one_combat::captureOocPolicyThreadState();
        decltype(search::g_onGameActionExecute) observer = search::g_onGameActionExecute;
        ~FixtureGuard() {
            g_oocStrategicTokNet = *tok; g_floorNet = floor;
            g_nativeOoc = native; g_cardWin = cardWin; g_cardNN = cardNN;
            g_cardAction = cardAction; g_bossV = bossV;
            g_cardSkipThresh = threshold; g_oocStrategicMarginCard = margin;
            g_oocStrategicGateRegret = regret; g_oocStrategicTracePath = trace;
            t_curPath = path; one_combat::restoreOocPolicyThreadState(policy);
            search::g_onGameActionExecute = observer;
        }
    } guard;
    g_oocStrategicTokNet = *std::make_unique<OocStrategicTokNet>();
    auto &net = g_oocStrategicTokNet;
    net.ok = true;
    // Real V4 inference: Iron Wave alone scores > 1. Both groups contain it,
    // so V4 ties and falls through with two groups, but acts with one group.
    net.eCard[static_cast<int>(CardId::IRON_WAVE)][0] = 4.0f;
    net.ent0w[0][0] = 1.0f;
    net.ent3w[0][0] = 1.0f;
    net.q0w[0][OocStrategicTokNet::POLIN - OocStrategicTokNet::ENTOUT] = 1.0f;
    net.q2w[0] = 1.0f;
    g_floorNet = WinNet{};
    g_floorNet.ok = true; // Constant floor value: fallback takes candidate zero.
    g_nativeOoc = true;
    g_cardWin = g_cardNN = g_cardAction = false;
    g_bossV = 0;
    g_cardSkipThresh = -0.5;
    g_oocStrategicMarginCard = 1.0;
    g_oocStrategicGateRegret = false;
    g_oocStrategicTracePath.clear();
    one_combat::restoreOocPolicyThreadState(OocPolicyThreadState{});
    search::g_onGameActionExecute = {};

    GameContext source(CharacterClass::IRONCLAD, 0x334041, 0);
    Rewards rewards;
    for (auto first : {CardId::COMBUST, CardId::SHRUG_IT_OFF}) {
        CardReward group;
        group.push_back(Card(first));
        group.push_back(Card(CardId::IRON_WAVE));
        rewards.addCardReward(group);
    }
    source.openCombatRewardScreen(rewards);
    PathHistory path;
    t_curPath = &path;
    search::ScumSearchAgent2 agent;
    VwinCollector capture;
    capture.sourceSeed = source.seed;
    capture.samplesPerType = 2;
    capture.allowSampling = capture.captureDecisionSink = true;
    require(!one_combat::inCardRewardFallback(), "marker starts clear");
    vwinObservePolicyStep(capture, source, path, agent, [&] {
        require(!one_combat::oocOnePlyCardRewardPolicy(source, agent), "V4 declines the two-group tie");
        one_combat::serverCardRewardPolicy(source);
    });
    require(!one_combat::inCardRewardFallback(), "normal return restores marker");
    require(capture.decisions.size() == 2 && capture.decisionSinkRows.size() == 2,
            "both intermediate decisions and sink states are captured");
    auto &samples = capture.sampled.at("CARD_REWARD");
    require(samples.size() == 2 && std::all_of(samples.begin(), samples.end(), [](const auto &s) {
        return s.continuation == VwinContinuation::CARD_REWARD_FALLBACK_DRAIN;
    }), "every actual fallback action records its continuation");
    const auto &sample = samples.front();
    require(sample.options.size() == 3, "both cards and skip retained");
    int checked = 0;
    for (const auto &option : sample.options) {
        auto branch = detachedCounterfactualCopy(*sample.pre);
        PathHistory branchPath = sample.path;
        t_curPath = &branchPath;
        auto branchAgent = sample.agentAfter;
        one_combat::restoreOocPolicyThreadState(sample.policyAfter);
        auto forced = search::executeOocSemanticAction(branch, *option.semantic);
        require(forced.ok, "each retained candidate executes");
        VwinCollector replay;
        replay.captureDecisionSink = true;
        replay.decisionIdx = sample.decisionIdx + 1;
        vwinCaptureForcedDecision(replay, detachedCounterfactualCopy(*sample.pre),
                                  branchPath, forced.executedPrimitiveBits, sample.decisionIdx);
        if (option.key == sample.chosenKey) {
            auto broken = detachedCounterfactualCopy(branch);
            VwinCollector fresh;
            fresh.allowSampling = fresh.captureDecisionSink = true;
            fresh.samplesPerType = 1;
            vwinObservePolicyStep(fresh, broken, branchPath, branchAgent, [&] {
                require(one_combat::oocOnePlyCardRewardPolicy(broken, branchAgent),
                        "broken fresh V4 entry handles group two");
            });
            require(fresh.decisions.size() == 1
                    && fresh.decisions.front().chosenKey != capture.decisions[1].chosenKey,
                    "old replay picks a different second card");
            require(fresh.sampled.at("CARD_REWARD").front().continuation == VwinContinuation::NONE,
                    "actual V4-handled action has no fallback continuation");
        }
        vwinResumeContinuation(sample, replay, branch, branchPath, branchAgent);
        require(branch.info.rewardsContainer.cardRewardCount == 0
                && replay.decisions.size() == 1
                && replay.decisions.front().chosenKey == capture.decisions[1].chosenKey,
                "chosen and untaken siblings resume the fallback second choice");
        require(replay.decisionSinkRows.size() == 2
                && replay.decisionSinkRows[1].decisionIdx == sample.decisionIdx + 1,
                "forced and intermediate sibling sink rows remain present");
        if (option.key == sample.chosenKey) {
            require(vwinCompoundStateFingerprint(branch) == vwinCompoundStateFingerprint(source)
                    && replay.decisionSinkRows[1].features == capture.decisionSinkRows[1].features,
                    "chosen replay matches source result and intermediate state");
        }
        ++checked;
    }
    require(checked == 3, "no sibling skipped");
    // The marker is scoped even when an action callback nests another drain
    // and throws before the outer action executes.
    auto throwing = detachedCounterfactualCopy(*sample.pre);
    search::g_onGameActionExecute = [&](std::uint32_t, const GameContext *target) {
        if (target != &throwing) return;
        require(one_combat::inCardRewardFallback(), "outer fallback marker is active");
        auto nested = detachedCounterfactualCopy(source); // Already drained.
        one_combat::serverCardRewardPolicy(nested);
        require(one_combat::inCardRewardFallback(), "nested return preserves outer marker");
        throw std::runtime_error("fixture interruption");
    };
    bool interrupted = false;
    try { one_combat::serverCardRewardPolicy(throwing); }
    catch (const std::runtime_error &e) {
        if (std::string(e.what()) != "fixture interruption") throw;
        interrupted = true;
    }
    require(interrupted && !one_combat::inCardRewardFallback(), "exception restores marker");
    std::cout << "vwin continuation: PASS; real V4 tie/fresh-entry divergence, fallback chosen + "
                 "2 untaken siblings, intermediate rows, nesting and exceptions\n";
    return 0;
}

int vwinRefreshCompoundSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("vwin compound selftest: " + message);
    };
    struct CompoundFixture {
        const char *name;
        ScreenState screen;
        Room room;
        Event event;
        RelicId relic;
        search::OocSemanticSource source;
    };
    const std::vector<CompoundFixture> fixtures{
        {"smith", ScreenState::REST_ROOM, Room::REST, Event::INVALID, RelicId::INVALID,
         search::OocSemanticSource::CAMPFIRE_SMITH},
        {"peace_pipe", ScreenState::REST_ROOM, Room::REST, Event::INVALID, RelicId::PEACE_PIPE,
         search::OocSemanticSource::CAMPFIRE_PEACE_PIPE},
        {"shop_remove", ScreenState::SHOP_ROOM, Room::SHOP, Event::INVALID, RelicId::INVALID,
         search::OocSemanticSource::SHOP_REMOVE},
        {"event_remove", ScreenState::EVENT_SCREEN, Room::EVENT, Event::OLD_BEGGAR,
         RelicId::INVALID, search::OocSemanticSource::EVENT}
    };
    int checked = 0;
    for (const auto &fixture : fixtures) {
        GameContext pre(CharacterClass::IRONCLAD, 0x334334ULL + checked, 0);
        pre.screenState = fixture.screen;
        pre.curRoom = fixture.room;
        pre.curEvent = fixture.event;
        pre.gold = 500;
        pre.regainControlAction = [](GameContext &gc) {
            ++gc.info.eventData;
            gc.screenState = ScreenState::MAP_SCREEN;
            gc.regainControlAction = nullptr;
        };
        if (fixture.relic != RelicId::INVALID) pre.relics.add({fixture.relic, 0});
        if (fixture.screen == ScreenState::SHOP_ROOM) {
            std::fill(std::begin(pre.info.shop.prices), std::end(pre.info.shop.prices), -1);
            pre.info.shop.removeCost = 75;
        }

        bool supported = false, complete = false;
        std::string error;
        auto options = vwinOptions(pre, supported, complete, error);
        require(supported && complete, std::string(fixture.name) + " enumeration is complete: " + error);
        const auto selected = std::find_if(options.begin(), options.end(), [&](const auto &option) {
            return option.semantic && option.semantic->source == fixture.source
                && search::oocSemanticPrimitiveCompoundSelector(pre,
                    [&]() {
                        const auto bindings = search::enumerateOocSemanticPrimitiveBindings(pre);
                        const auto binding = std::find_if(bindings.bindings.begin(), bindings.bindings.end(),
                            [&](const auto &candidate) {
                                return vwinOptionKey(candidate.semantic) == option.key;
                            });
                        return binding == bindings.bindings.end() ? std::uint32_t{0}
                                                                  : binding->primitiveBits;
                    }()) != CardSelectScreenType::INVALID;
        });
        require(selected != options.end(), std::string(fixture.name) + " compound candidates exist");
        const auto bindings = search::enumerateOocSemanticPrimitiveBindings(pre);
        const auto binding = std::find_if(bindings.bindings.begin(), bindings.bindings.end(),
            [&](const auto &candidate) { return vwinOptionKey(candidate.semantic) == selected->key; });
        require(binding != bindings.bindings.end()
                && binding->compoundSelector != CardSelectScreenType::INVALID,
                std::string(fixture.name) + " source binding has a selector");

        auto expected = detachedCounterfactualCopy(pre);
        auto previous = std::move(search::g_onGameActionExecute);
        search::g_onGameActionExecute = {};
        search::OocExecutionResult expectedExecution;
        try {
            expectedExecution = search::executeOocSemanticAction(expected, *selected->semantic);
            search::g_onGameActionExecute = std::move(previous);
        } catch (...) {
            search::g_onGameActionExecute = std::move(previous);
            throw;
        }
        require(expectedExecution.ok && expectedExecution.executedPrimitiveBits.size() >= 2,
                std::string(fixture.name) + " semantic compound has source and selector actions");

        GameContext source = detachedCounterfactualCopy(pre);
        std::vector<std::uint32_t> observed;
        previous = std::move(search::g_onGameActionExecute);
        search::g_onGameActionExecute = [&](std::uint32_t bits, const GameContext *target) {
            if (target == &source) observed.push_back(bits);
        };
        try {
            for (const auto bits : expectedExecution.executedPrimitiveBits)
                search::GameAction(bits).execute(source);
            search::g_onGameActionExecute = std::move(previous);
        } catch (...) {
            search::g_onGameActionExecute = std::move(previous);
            throw;
        }
        require(observed == expectedExecution.executedPrimitiveBits,
                std::string(fixture.name) + " observer captures the complete compound sequence");

        VwinCollector capture;
        capture.sourceSeed = 13000000ULL + checked;
        capture.samplesPerType = 1;
        capture.allowSampling = true;
        PathHistory path;
        const auto rowIndex = vwinBeginDecision(capture, pre, path, options,
            vwinScreenDecisionType(pre), "", true, true, "", true);
        require(capture.eligibleByType.empty(),
                std::string(fixture.name) + " waits for the selector before reservoir admission");
        VwinPendingDecision pending;
        pending.rowIndex = rowIndex;
        pending.selector = binding->compoundSelector;
        pending.options = options;
        pending.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(pre));
        pending.path = path;
        pending.observedPrimitiveBits = observed;
        search::ScumSearchAgent2 agent;
        vwinFinishDecision(capture, std::move(pending), agent,
                           one_combat::captureOocPolicyThreadState());

        require(capture.decisions.at(rowIndex).chosenKey == selected->key,
                std::string(fixture.name) + " resolves the full chosen semantic key");
        require(capture.eligibleByType[capture.decisions.at(rowIndex).type] == 1
                && vwinSelectedDecision(capture, capture.decisions.at(rowIndex).decisionIdx),
                std::string(fixture.name) + " becomes a sampled/branchable decision");
        auto sample = std::find_if(capture.sampled.at(capture.decisions.at(rowIndex).type).begin(),
            capture.sampled.at(capture.decisions.at(rowIndex).type).end(), [&](const auto &value) {
                return value.decisionIdx == capture.decisions.at(rowIndex).decisionIdx;
            });
        require(sample != capture.sampled.at(capture.decisions.at(rowIndex).type).end()
                && sample->options.size() >= 2,
                std::string(fixture.name) + " retains semantic branch alternatives");

        int branchCount = 0;
        bool chosenReplayMatched = false;
        for (const auto &option : sample->options) {
            require(option.semantic.has_value(), std::string(fixture.name) + " branch is semantic");
            auto branch = detachedCounterfactualCopy(*sample->pre);
            previous = std::move(search::g_onGameActionExecute);
            search::g_onGameActionExecute = {};
            search::OocExecutionResult result;
            try {
                result = search::executeOocSemanticAction(branch, *option.semantic);
                search::g_onGameActionExecute = std::move(previous);
            } catch (...) {
                search::g_onGameActionExecute = std::move(previous);
                throw;
            }
            require(result.ok && !result.executedPrimitiveBits.empty(),
                    std::string(fixture.name) + " semantic alternative executes as a branch");
            ++branchCount;
            if (option.key == sample->chosenKey) {
                chosenReplayMatched = result.executedPrimitiveBits == observed
                    && vwinCompoundStateFingerprint(branch) == vwinCompoundStateFingerprint(source);
            }
        }
        require(branchCount == static_cast<int>(sample->options.size()),
                std::string(fixture.name) + " executes every retained branch alternative");
        require(chosenReplayMatched,
                std::string(fixture.name) + " chosen semantic branch replays the observed source action");
        ++checked;
    }

    struct PolicyFixtureGuard {
        bool oocActionNN = g_oocActionNN;
        bool actFightProbeAllOoc = g_actFightProbeAllOoc;
        bool oocMapRoute = g_oocMapRoute;
        bool oocStrategicRest = g_oocStrategicRest;
        bool restWin = g_restWin;
        int pathV = g_pathV;
        int eventV = g_eventV;
        const PathHistory *currentPath = t_curPath;
        OocPolicyThreadState policy = one_combat::captureOocPolicyThreadState();
        ~PolicyFixtureGuard() {
            g_oocActionNN = oocActionNN;
            g_actFightProbeAllOoc = actFightProbeAllOoc;
            g_oocMapRoute = oocMapRoute;
            g_oocStrategicRest = oocStrategicRest;
            g_restWin = restWin;
            g_pathV = pathV;
            g_eventV = eventV;
            t_curPath = currentPath;
            one_combat::restoreOocPolicyThreadState(policy);
        }
    } guard;
    g_oocActionNN = false;
    g_actFightProbeAllOoc = false;
    g_oocMapRoute = false;
    g_oocStrategicRest = false;
    g_restWin = false;
    g_pathV = 0;
    g_eventV = 0;

    GameContext source(CharacterClass::IRONCLAD, 0x334334ULL, 0);
    source.screenState = ScreenState::REST_ROOM;
    source.curRoom = Room::REST;
    source.act = 1;
    source.curHp = 70;
    source.regainControlAction = [](GameContext &gc) {
        gc.screenState = ScreenState::MAP_SCREEN;
        gc.regainControlAction = nullptr;
    };
    require(source.deck.getUpgradeableCount() > 0,
            "step-boundary fixture has an upgradeable card for the smith action");

    VwinCollector stepCapture;
    stepCapture.sourceSeed = 13000000ULL;
    stepCapture.samplesPerType = 1;
    stepCapture.allowSampling = true;
    stepCapture.captureDecisionSink = true;
    PathHistory stepPath;
    search::ScumSearchAgent2 stepAgent;
    stepAgent.rng = std::default_random_engine(998877);
    t_curPath = &stepPath;
    std::vector<std::uint32_t> observedSmithBits;
    auto previous = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = [&](std::uint32_t bits, const GameContext *target) {
        if (target == &source) observedSmithBits.push_back(bits);
    };
    try {
        vwinRefreshRunPolicyStep(stepCapture, source, stepPath, stepAgent);
        require(source.screenState == ScreenState::CARD_SELECT
                && source.info.selectScreenType == CardSelectScreenType::UPGRADE,
                "real policy step executes Smith and opens its card target selector");
        require(stepCapture.pendingAction
                && vwinPendingAwaitsSelector(*stepCapture.pendingAction, source)
                && stepCapture.pendingAction->observedPrimitiveBits.size() == 1,
                "Smith decision remains pending after the source action step");
        require(stepCapture.decisions.size() == 1
                && stepCapture.decisions.front().chosenKey.empty()
                && stepCapture.eligibleByType.empty(),
                "Smith is not resolved or sampled before its selector target");

        vwinRefreshRunPolicyStep(stepCapture, source, stepPath, stepAgent);
        search::g_onGameActionExecute = std::move(previous);
    } catch (...) {
        search::g_onGameActionExecute = std::move(previous);
        throw;
    }
    require(source.screenState == ScreenState::MAP_SCREEN
            && !stepCapture.pendingAction && observedSmithBits.size() == 2,
            "second real policy step selects the card and closes the compound decision");
    require(stepCapture.decisionSinkRows.size() == 2
            && stepCapture.decisionSinkRows[0].screen == "rest"
            && stepCapture.decisionSinkRows[1].screen == "selector"
            && stepCapture.decisionSinkRows[0].decisionIdx == 0
            && stepCapture.decisionSinkRows[1].decisionIdx == -1
            && !stepCapture.decisionSinkRows[0].chosenKey.empty()
            && !stepCapture.decisionSinkRows[1].chosenKey.empty(),
            "DECISION captures the source screen and its separate card-selector state");
    const auto &smithRow = stepCapture.decisions.front();
    require(!smithRow.chosenKey.empty()
            && stepCapture.eligibleByType[smithRow.type] == 1
            && vwinSelectedDecision(stepCapture, smithRow.decisionIdx),
            "step-spanning Smith decision resolves and enters the reservoir");
    const auto &smithSample = stepCapture.sampled.at(smithRow.type).front();
    require(smithSample.options.size() >= 2
            && std::all_of(smithSample.options.begin(), smithSample.options.end(),
                [](const auto &option) { return option.semantic.has_value(); }),
            "step-spanning Smith decision retains semantic branch alternatives");
    const auto chosenSmith = std::find_if(smithSample.options.begin(), smithSample.options.end(),
        [&](const auto &option) { return option.key == smithSample.chosenKey; });
    require(chosenSmith != smithSample.options.end(),
            "step-spanning Smith sample retains the observed semantic choice");
    auto smithReplay = detachedCounterfactualCopy(*smithSample.pre);
    previous = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = {};
    search::OocExecutionResult smithExecution;
    try {
        smithExecution = search::executeOocSemanticAction(smithReplay, *chosenSmith->semantic);
        search::g_onGameActionExecute = std::move(previous);
    } catch (...) {
        search::g_onGameActionExecute = std::move(previous);
        throw;
    }
    VwinCollector forcedCapture;
    forcedCapture.captureDecisionSink = true;
    auto observer = std::move(search::g_onGameActionExecute);
    search::g_onGameActionExecute = {};
    try {
        vwinCaptureForcedDecision(forcedCapture, detachedCounterfactualCopy(*smithSample.pre),
                                  smithSample.path, smithExecution.executedPrimitiveBits,
                                  smithSample.decisionIdx);
    } catch (...) {
        search::g_onGameActionExecute = std::move(observer);
        throw;
    }
    search::g_onGameActionExecute = std::move(observer);
    require(forcedCapture.decisionSinkRows.size() == 2
            && forcedCapture.decisionSinkRows[0].chosenKey == stepCapture.decisionSinkRows[0].chosenKey
            && forcedCapture.decisionSinkRows[1].chosenKey == stepCapture.decisionSinkRows[1].chosenKey
            && forcedCapture.decisionSinkRows[1].features == stepCapture.decisionSinkRows[1].features,
            "forced branch capture includes the same source and intermediate selector states");
    require(smithExecution.ok && smithExecution.executedPrimitiveBits == observedSmithBits
            && vwinCompoundStateFingerprint(smithReplay) == vwinCompoundStateFingerprint(source),
            "step-spanning Smith chosen branch replays the observed selector action");
    std::cout << "vwin compound contract: " << checked
              << " Smith/Peace Pipe/shop/event semantic fixtures plus a real two-step Smith capture "
                 "sampled, branched, and chosen-replay matched\n";
    return 0;
}

int vwinRefreshBranchParitySelfTest(std::uint64_t seed, int sims, int asc) {
    if (sims < 1 || asc != 0)
        throw std::runtime_error("vwin branch parity selftest: require positive SIMS and Ascension 0");
    WholeCombatTeacher fixture{"vwin-branch-parity-selftest", nlohmann::json::object()};
    VwinCollector source;
    source.sourceSeed = seed;
    source.samplesPerType = 1;
    source.branchId = "source";
    source.captureRefresh = true;
    source.allowSampling = true;
    const auto sourceResult = runCombatEvalGenSeed(seed, sims, asc, fixture, false, &source);
    if (!sourceResult.trajectoryValid)
        throw std::runtime_error("vwin branch parity selftest: source trajectory is invalid");
    auto samples = vwinSamplesInSourceOrder(source);
    if (samples.empty())
        throw std::runtime_error("vwin branch parity selftest: no supported multi-option decision sampled");
    auto *sample = samples.front();
    const auto chosen = std::find_if(sample->options.begin(), sample->options.end(), [&](const auto &option) {
        return option.key == sample->chosenKey;
    });
    if (chosen == sample->options.end())
        throw std::runtime_error("vwin branch parity selftest: chosen option was not retained by cap");
    VwinBranchStart start{sample, *chosen, "selftest-chosen-replay"};
    VwinCollector replay;
    replay.sourceSeed = seed;
    replay.branchId = start.branchId;
    replay.deviationIdx = 1;
    replay.captureRefresh = true;
    const auto replayResult = runCombatEvalGenSeed(seed, sims, asc, fixture, false, &replay, &start);
    if (sample->sourceTraceIndex > source.trace.size())
        throw std::runtime_error("vwin branch parity selftest: source trace index is invalid");
    const std::vector<std::string> expected(
        source.trace.begin() + static_cast<std::ptrdiff_t>(sample->sourceTraceIndex),
        source.trace.end());
    if (expected != replay.trace || sourceResult.finalOutcome != replayResult.finalOutcome
        || sourceResult.finalFloor != replayResult.finalFloor || sourceResult.finalHp != replayResult.finalHp)
        throw std::runtime_error("vwin branch parity selftest: chosen replay diverged from source suffix");
    if (source.rawRows.size() != replay.rawRows.size())
        throw std::runtime_error("vwin branch parity selftest: WIN_RAW victory count changed");
    std::cout << "vwin branch parity: seed=" << seed << " decision=" << sample->decisionIdx
              << " type=" << sample->type << " events=" << expected.size()
              << " outcome=" << combatEvalGameOutcome(sourceResult.finalOutcome)
              << " floor=" << sourceResult.finalFloor << " hp=" << sourceResult.finalHp << "\n";
    return 0;
}

void bossHeadroom347Gen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                        long long seedOffset, const std::string &teacherPath) {
    constexpr int kPilotSeeds = 128;
    constexpr long long kPilotStart = 13000000;
    if (nSeeds != kPilotSeeds || sims != 10000 || asc != 0 || seedOffset != kPilotStart)
        throw std::runtime_error("boss headroom #347: fixed cohort is 128 seeds from 13000000, exact 10k, Ascension 0");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true);
    vwinRequireProductionPolicy(teacher);
    const std::string statesPath = outPrefix + ".states.csv";
    const std::string armsPath = outPrefix + ".arms.csv";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {statesPath, armsPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("boss headroom #347: refusing to overwrite existing output " + path);

    std::vector<VwinBossEntry> entries;
    int completeSources = 0, validSources = 0;
    for (int i = 0; i < nSeeds; ++i) {
        VwinCollector capture;
        capture.sourceSeed = static_cast<std::uint64_t>(seedOffset + i);
        capture.captureBoss = true;
        const auto source = runCombatEvalGenSeed(capture.sourceSeed, sims, asc, teacher,
                                                  false, &capture);
        if (source.trajectoryComplete) ++completeSources;
        if (source.trajectoryValid) ++validSources;
        for (auto &entry : capture.bossEntries) entries.push_back(std::move(entry));
    }

    std::vector<VwinBossEntry *> selected;
    const int quotas[3] = {11, 11, 10};
    nlohmann::json selection = nlohmann::json::array();
    for (int act = 1; act <= 3; ++act) {
        std::vector<VwinBossEntry *> inAct;
        for (auto &entry : entries)
            if (entry.act == act && entry.sourceTrajectoryValid && entry.labelValid
                && entry.sourceWon >= 0 && entry.terminalHp >= 0 && entry.postAfterBattleHp >= 0)
                inAct.push_back(&entry);
        std::sort(inAct.begin(), inAct.end(), [](const auto *a, const auto *b) {
            const auto ka = vwinSha256("boss-headroom-347-v1:" + std::to_string(a->pre->seed)
                                      + ":" + std::to_string(a->fightIdx));
            const auto kb = vwinSha256("boss-headroom-347-v1:" + std::to_string(b->pre->seed)
                                      + ":" + std::to_string(b->fightIdx));
            return ka == kb ? std::tie(a->pre->seed, a->fightIdx)
                            < std::tie(b->pre->seed, b->fightIdx) : ka < kb;
        });
        const std::size_t take = std::min<std::size_t>(quotas[act - 1], inAct.size());
        for (std::size_t i = 0; i < take; ++i) {
            selected.push_back(inAct[i]);
            selection.push_back({{"seed", inAct[i]->pre->seed}, {"fightIdx", inAct[i]->fightIdx},
                                 {"act", act}, {"rank", i + 1},
                                 {"selectionHash", vwinSha256("boss-headroom-347-v1:"
                                     + std::to_string(inAct[i]->pre->seed) + ":"
                                     + std::to_string(inAct[i]->fightIdx))}});
        }
    }

    std::ofstream states(statesPath), arms(armsPath);
    if (!states || !arms) throw std::runtime_error("boss headroom #347: cannot open outputs");
    states << "stateId,sourceSeed,fightIdx,act,floor,roomClass,encounter,sourceWon,sourceSignedOutcome,"
              "sourceTerminalHp,sourcePostAfterBattleHp,sourceFirstActionBits,trajectoryValid\n";
    arms << "stateId,sourceSeed,fightIdx,act,encounter,arm,budget,outcome,won,signedOutcome,"
            "terminalHp,postAfterBattleHp,firstActionBits,firstDecisionAgreement,cpuSeconds,"
            "simulations,decisions,valid,sourceReplayMatch,quarantineReason\n";
    int sourceReplayMatches = 0, sourceReplayMismatches = 0, validStates = 0;
    for (auto *entry : selected) {
        const auto stateId = "s" + std::to_string(entry->pre->seed) + "-f"
            + std::to_string(entry->fightIdx);
        states << stateId << ',' << entry->pre->seed << ',' << entry->fightIdx << ','
               << entry->act << ',' << entry->floor << ',' << entry->roomClass << ','
               << csvQuote(entry->encounter) << ',' << entry->sourceWon << ','
               << std::setprecision(17) << entry->signedOutcome << ',' << entry->terminalHp << ','
               << entry->postAfterBattleHp << ',' << entry->firstActionBits << ','
               << (entry->sourceTrajectoryValid ? 1 : 0) << '\n';
        bool baselineMatches = false;
        for (const auto &[armName, budget] : std::vector<std::pair<std::string, int>>{
                 {"A", 10000}, {"B100", 100000}, {"B30", 30000}}) {
            const auto result = vwinRunBossArm(*entry, budget);
            const bool sourceMatch = armName == "A"
                && result.valid && result.won == entry->sourceWon
                && result.terminalHp == entry->terminalHp;
            if (armName == "A") {
                baselineMatches = sourceMatch;
                if (sourceMatch) ++sourceReplayMatches;
                else ++sourceReplayMismatches;
            }
            const bool firstAgreement = result.firstActionBits >= 0
                && result.firstActionBits == entry->firstActionBits;
            const bool valid = result.valid && (armName != "A" || sourceMatch)
                && (armName == "A" || baselineMatches);
            if (armName == "A" && valid) ++validStates;
            std::string reason = result.quarantineReason;
            if (armName == "A" && result.valid && !sourceMatch) reason = "baseline_replay_mismatch";
            if (armName != "A" && !baselineMatches) reason = "baseline_state_invalid";
            arms << stateId << ',' << entry->pre->seed << ',' << entry->fightIdx << ','
                 << entry->act << ',' << csvQuote(entry->encounter) << ',' << armName << ','
                 << budget << ',' << result.outcome << ',' << result.won << ','
                 << std::setprecision(17) << result.signedOutcome << ',' << result.terminalHp << ','
                 << result.postAfterBattleHp << ',' << result.firstActionBits << ','
                 << (firstAgreement ? 1 : 0) << ',' << std::setprecision(9) << result.cpuSeconds
                 << ',' << result.simulations << ',' << result.decisions << ',' << (valid ? 1 : 0)
                 << ',' << (armName == "A" ? (sourceMatch ? 1 : 0) : -1) << ','
                 << csvQuote(reason) << '\n';
        }
    }
    states.close(); arms.close();
    nlohmann::json manifest = {
        {"schemaVersion", "boss_headroom_347_stage1_v1"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification}, {"policy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"selection", {{"rule", "per_act_sha256_rank"},
                        {"domain", "boss-headroom-347-v1:{seed}:{fightIdx}"},
                        {"quotas", {11, 11, 10}}, {"selected", std::move(selection)}}},
        {"arms", {{"A", 10000}, {"B100", 100000}, {"B30", 30000}}},
        {"integrity", {{"completeSources", completeSources}, {"validSources", validSources},
            {"candidateBossEntries", entries.size()}, {"selectedStates", selected.size()},
            {"sourceReplayMatches", sourceReplayMatches},
            {"sourceReplayMismatches", sourceReplayMismatches}, {"validStates", validStates}}},
        {"outputs", {{"statesSha256", fileSha256(statesPath)},
                     {"armsSha256", fileSha256(armsPath)}}}
    };
    std::ofstream manifestOut(manifestPath);
    if (!manifestOut) throw std::runtime_error("boss headroom #347: cannot write manifest");
    manifestOut << manifest.dump(2) << '\n';
    std::cout << "boss headroom #347 teacher=" << teacher.id << " sourceValid=" << validSources
              << '/' << nSeeds << " selected=" << selected.size() << " A-replay="
              << sourceReplayMatches << '/' << sourceReplayMatches + sourceReplayMismatches
              << " -> " << outPrefix << "\n";
}

// #347 boss-entry budget rescue pilot (docs/experiments/evidence/
// boss_budget_rescue_347_pilot_20261007). One frozen #417 source per process:
// reconstruct the run with the ordinary live run driver (live OOC MCTS when
// the arm enables it), capture the act's boss entry, then replay that entry
// with the original planner seed (control parity) and with four fresh planner
// seeds at flat exact 10k (A) and 40k (B). The #347 boss-preparation R-match
// (docs/experiments/evidence/boss_preparation_rmatch_347_20261007) reuses the
// mode with its own selection schema: the source may be a boss win
// (expectedSourceWon), and each entry gets fresh 10k planner seeds keyed only
// by run seed, act and rep, so the M and F entries of a seed share them.
static std::string bossRescueStateDigest(const GameContext &gc, const search::ScumSearchAgent2 *agent) {
    std::ostringstream o;
    o << "boss-rescue-347-state-v1|seed=" << gc.seed;
    for (const Random *r : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                            &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                            &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng})
        o << "|rng=" << r->counter << ':' << r->seed0 << ':' << r->seed1;
    o << "|act=" << gc.act << "|asc=" << gc.ascension << "|floor=" << gc.floorNum
      << "|room=" << static_cast<int>(gc.curRoom) << "|screen=" << static_cast<int>(gc.screenState)
      << "|outcome=" << static_cast<int>(gc.outcome)
      << "|encounter=" << static_cast<int>(gc.info.encounter) << "|boss=" << static_cast<int>(gc.boss)
      << "|secondBoss=" << static_cast<int>(gc.secondBoss)
      << "|map=" << gc.curMapNodeX << ',' << gc.curMapNodeY
      << "|hp=" << gc.curHp << '/' << gc.maxHp << "|gold=" << gc.gold
      << "|potions=" << gc.potionCount << '/' << gc.potionCapacity << ':';
    for (const auto p : gc.potions) o << static_cast<int>(p) << ',';
    o << "|relics=";
    for (const auto &r : gc.relics.relics) o << static_cast<int>(r.id) << ':' << r.data << ',';
    o << "|deck=";
    for (const auto &c : gc.deck.cards) o << static_cast<int>(c.id) << ':' << c.misc << ':' << c.upgraded << ',';
    o << "|bottles=" << gc.deck.bottleIdxs[0] << ',' << gc.deck.bottleIdxs[1] << ',' << gc.deck.bottleIdxs[2]
      << "|keys=" << gc.blueKey << gc.greenKey << gc.redKey << gc.keysEnabled
      << "|smokeBomb=" << gc.smokeBombUsed << "|wingBoots=" << gc.wingBootsCharges
      << "|lists=" << gc.monsterListOffset << ',' << gc.eliteMonsterListOffset;
    if (agent) o << "|agent=" << agent->simulationCountBase << ':' << agent->bossSimulationMultiplier
                 << ':' << agent->rng;
    return vwinSha256(o.str());
}

static std::string bossRescueStateSummary(const GameContext &gc) {
    std::ostringstream o;
    o << "hp=" << gc.curHp << ";maxHp=" << gc.maxHp << ";gold=" << gc.gold << ";potions=";
    for (int i = 0; i < gc.potionCapacity && i < static_cast<int>(gc.potions.size()); ++i)
        o << (i ? "|" : "") << potionEnumNames[static_cast<int>(gc.potions[i])];
    o << ";relics=";
    bool first = true;
    for (const auto &r : gc.relics.relics) {
        o << (first ? "" : "|") << relicEnumNames[static_cast<int>(r.id)] << ':' << r.data;
        first = false;
    }
    o << ";deck=";
    first = true;
    for (const auto &c : gc.deck.cards) {
        o << (first ? "" : "|") << c.getName() << (c.isUpgraded() ? "+" : "");
        first = false;
    }
    return o.str();
}

static std::uint64_t bossRescuePlannerSeed(const std::string &stateId, int rep) {
    return std::stoull(vwinSha256("boss-rescue-347-planner-v1:" + stateId + ":"
                                  + std::to_string(rep)).substr(0, 16), nullptr, 16);
}

// Boss-preparation R-match: no preparation arm or stateId in the key.
static std::uint64_t bossPrepPlannerSeed(std::uint64_t runSeed, int act, int rep) {
    return std::stoull(vwinSha256("boss-prep-347-planner-v1:" + std::to_string(runSeed) + ":"
                                  + std::to_string(act) + ":" + std::to_string(rep)).substr(0, 16),
                       nullptr, 16);
}

// Cheap descriptive record of a boss entry (no derived score).
static nlohmann::json bossPrepEntryDescriptor(const GameContext &gc, const PathHistory &path) {
    nlohmann::json potions = nlohmann::json::array(), relics = nlohmann::json::array(),
                   deck = nlohmann::json::array(), rng = nlohmann::json::object();
    for (int i = 0; i < gc.potionCapacity && i < static_cast<int>(gc.potions.size()); ++i)
        potions.push_back(potionEnumNames[static_cast<int>(gc.potions[i])]);
    for (const auto &r : gc.relics.relics)
        relics.push_back({{"relic", relicEnumNames[static_cast<int>(r.id)]}, {"data", r.data}});
    int upgrades = 0;
    for (const auto &c : gc.deck.cards) {
        deck.push_back(std::string(c.getName()) + (c.isUpgraded() ? "+" : ""));
        upgrades += c.isUpgraded() ? 1 : 0;
    }
    const std::vector<std::pair<const char *, const Random *>> streams = {
        {"aiRng", &gc.aiRng}, {"cardRandomRng", &gc.cardRandomRng}, {"cardRng", &gc.cardRng},
        {"eventRng", &gc.eventRng}, {"mathUtilRng", &gc.mathUtilRng}, {"merchantRng", &gc.merchantRng},
        {"miscRng", &gc.miscRng}, {"monsterHpRng", &gc.monsterHpRng}, {"monsterRng", &gc.monsterRng},
        {"neowRng", &gc.neowRng}, {"potionRng", &gc.potionRng}, {"relicRng", &gc.relicRng},
        {"shuffleRng", &gc.shuffleRng}, {"treasureRng", &gc.treasureRng}};
    std::ostringstream rngText;
    for (const auto &[name, r] : streams) {
        rng[name] = r->counter;
        rngText << name << '=' << r->counter << ':' << r->seed0 << ':' << r->seed1 << '|';
    }
    nlohmann::json roomVisits = nlohmann::json::array();
    for (const int v : path.roomVisits) roomVisits.push_back(v);
    return {{"act", gc.act}, {"floor", gc.floorNum},
            {"boss", monsterEncounterEnumNames[static_cast<int>(gc.info.encounter)]},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold},
            {"potionCapacity", gc.potionCapacity}, {"potionCount", gc.potionCount}, {"potions", potions},
            {"deckSize", gc.deck.cards.size()}, {"upgrades", upgrades}, {"deck", deck}, {"relics", relics},
            {"rngCounters", rng}, {"rngDigest", vwinSha256(rngText.str())},
            {"pathRoomVisits", roomVisits}};
}

namespace {
struct BossRescueSource {
    bool captured = false, finished = false;
    int bossBattles = 0;
    VwinBossEntry entry;
    std::string startDigest, postExitDigest, postExitSummary, encounterEnum;
    std::vector<int> trace;
    int won = -1, terminalHp = -1, postExitHp = -1, potionsAfter = -1, budget = -1;
    std::int64_t decisions = 0, simulations = 0, searchSteps = 0, minRootSteps = -1, maxRootSteps = -1;
    double cpuSeconds = 0.0;
    std::uint64_t cpuStart = 0;
};

struct BossRescueRow {
    std::string kind, arm;
    int budget = 0, rep = -1;
    std::optional<std::uint64_t> plannerSeed;
    VwinArmResult result;
    VwinBossArmDetail detail;
};

class PlannerSeedScope {
public:
    explicit PlannerSeedScope(std::optional<std::uint64_t> seed) {
        search::g_nativeSilverPlannerSeedOverride = seed;
    }
    ~PlannerSeedScope() { search::g_nativeSilverPlannerSeedOverride.reset(); }
};

BossRescueRow bossRescueRun(const VwinBossEntry &entry, const std::string &kind, const std::string &arm,
                            int budget, int rep, std::optional<std::uint64_t> plannerSeed) {
    BossRescueRow row;
    row.kind = kind; row.arm = arm; row.budget = budget; row.rep = rep; row.plannerSeed = plannerSeed;
    PlannerSeedScope scope(plannerSeed);
    row.result = vwinRunBossArm(entry, budget, nullptr, &row.detail);
    return row;
}

std::string bossRescueTraceText(const std::vector<int> &trace) {
    std::ostringstream o;
    for (std::size_t i = 0; i < trace.size(); ++i) o << (i ? " " : "") << trace[i];
    return o.str();
}

// Captures the boss entry of `act` from one ordinary runFullRunOOC call.
BossRescueSource bossRescueCapture(std::uint64_t seed, int sims, int act, RunResult &run) {
    BossRescueSource source;
    search::ScumSearchAgent2 *liveAgent = nullptr;
    BossEntryHook hook;
    hook.before = [&](const GameContext &gc, search::ScumSearchAgent2 &agent, const PathHistory &path) {
        ++source.bossBattles;
        if (gc.act != act) return;
        if (source.captured) throw std::runtime_error("boss rescue #347: second boss battle in the target act");
        source.captured = true;
        source.entry.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
        source.entry.path = path;
        source.entry.agent = agent;
        source.entry.policy = one_combat::captureOocPolicyThreadState();
        source.entry.act = gc.act;
        source.entry.floor = gc.floorNum;
        const int encounterIndex = static_cast<int>(gc.info.encounter);
        source.entry.encounter = monsterEncounterStrings[encounterIndex];
        source.encounterEnum = monsterEncounterEnumNames[encounterIndex];
        source.entry.roomClass = combatEvalRoomClass(gc.curRoom);
        source.startDigest = bossRescueStateDigest(gc, &agent);
        source.budget = agent.simulationCountBase;
        // Recording the executed actions does not change any decision.
        agent.recordActions = true;
        agent.gameActionHistory.clear();
        liveAgent = &agent;
        source.cpuStart = vwinThreadCpuNanos();
    };
    hook.after = [&](const GameContext &gc, const BattleContext &bc) {
        if (!liveAgent || source.finished) return;
        source.cpuSeconds = static_cast<double>(vwinThreadCpuNanos() - source.cpuStart) / 1.0e9;
        source.finished = true;
        source.won = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : bc.outcome == Outcome::PLAYER_LOSS ? 0 : -1;
        source.terminalHp = bc.player.curHp;
        source.postExitHp = gc.curHp;
        source.potionsAfter = gc.potionCount;
        source.postExitDigest = bossRescueStateDigest(gc, nullptr);
        source.postExitSummary = bossRescueStateSummary(gc);
        source.trace = liveAgent->gameActionHistory;
        const auto &stats = search::g_nativeSilverCombatStats;
        source.decisions = stats.decisions;
        source.simulations = stats.simulations;
        source.searchSteps = stats.searchSteps;
        source.minRootSteps = stats.minRootSteps;
        source.maxRootSteps = stats.maxRootSteps;
        liveAgent->recordActions = false;
        liveAgent->gameActionHistory.clear();
        liveAgent = nullptr;
    };
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    t_bossEntryHook = &hook;
    try {
        run = runFullRunOOC(seed, sims, 0, restV, true);
    } catch (...) {
        t_bossEntryHook = nullptr;
        throw;
    }
    t_bossEntryHook = nullptr;
    return source;
}

bool bossRescueSameRun(const BossRescueRow &a, const BossRescueRow &b) {
    return a.result.won == b.result.won && a.result.terminalHp == b.result.terminalHp
        && a.detail.trace == b.detail.trace && a.detail.postExitDigest == b.detail.postExitDigest
        && a.result.simulations == b.result.simulations && a.detail.searchSteps == b.detail.searchSteps;
}
} // namespace

int bossRescue347(int nEntries, const std::string &selectionPath, const std::string &stateId,
                  const std::string &outPrefix) {
    if (nEntries != 1) throw std::runtime_error("boss rescue #347: one entry per process");
    const auto selection = nlohmann::json::parse(std::ifstream(selectionPath));
    const std::string selectionSchema = selection.value("schema", "");
    // prep: #347 boss-preparation R-match; otherwise the frozen #425 rescue protocol.
    const bool prep = selectionSchema == "boss_preparation_rmatch_347_selection_v1";
    if (!prep && selectionSchema != "boss_budget_rescue_347_pilot_selection_v1")
        throw std::runtime_error("boss rescue #347: unexpected selection schema");
    const int reps = prep ? selection.at("plannerReps").get<int>() : 4;
    if (reps < 1 || reps > 8) throw std::runtime_error("boss rescue #347: plannerReps must be 1..8");
    nlohmann::json spec;
    for (const auto &candidate : selection.at("selected"))
        if (candidate.at("stateId") == stateId) spec = candidate;
    if (spec.is_null()) throw std::runtime_error("boss rescue #347: state " + stateId + " is not selected");
    const std::uint64_t seed = spec.at("seed").get<std::uint64_t>();
    const int act = spec.at("act").get<int>();
    const std::string sourceArm = spec.at("sourceArm"), boss = spec.at("boss");
    const auto &historical = spec.at("historicalRow");
    // The #425 protocol requires a lost source fight and has no other option.
    if (!prep && spec.contains("expectedSourceWon"))
        throw std::runtime_error("boss rescue #347: expectedSourceWon is not part of the rescue schema");
    const int expectedSourceWon = prep ? spec.at("expectedSourceWon").get<int>() : 0;
    if (expectedSourceWon != 0 && expectedSourceWon != 1)
        throw std::runtime_error("boss rescue #347: expectedSourceWon must be 0 or 1");
    const auto plannerSeed = [&](int rep) {
        return prep ? bossPrepPlannerSeed(seed, act, rep) : bossRescuePlannerSeed(stateId, rep);
    };
    const std::string freshKind = prep ? "fresh" : "A", repeatKind = prep ? "fresh_repeat" : "A_repeat";

    // The process must run the recorded pilot arm with flat exact-10k Silver.
    if (one_combat::liveOocMctsEnabled() != (sourceArm == "mcts"))
        throw std::runtime_error("boss rescue #347: STS_OOC_MCTS does not match source arm " + sourceArm);
    if (!search::nativeSilverBackendInstalled() || !search::nativeSilverExactRootBudgets()
        || search::nativeSilverAdaptiveEnabled() || search::nativeSilverLearnedStopEnabled()
        || search::nativeSilverReuseCap() != 32768 || g_stopAfterAct != 3)
        throw std::runtime_error("boss rescue #347: requires exact-root-budget Silver, adaptive and learned stopping off, reuse cap 32768, STS_STOP_AFTER_ACT=3");
    const std::string rowsPath = outPrefix + ".rows.csv", entryPath = outPrefix + ".entry.json";
    for (const auto &path : {rowsPath, entryPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("boss rescue #347: refusing to overwrite " + path);

    RunResult run{};
    auto source = bossRescueCapture(seed, 10000, act, run);
    const std::map<std::string, std::pair<long long, long long>> runFields = {
        {"won", {run.won ? 1 : 0, historical.at("won").get<long long>()}},
        {"floor", {run.floor, historical.at("floor").get<long long>()}},
        {"act", {run.act, historical.at("act").get<long long>()}},
        {"hpEnd", {run.hpEnd, historical.at("hpEnd").get<long long>()}},
        {"maxHp", {run.maxHp, historical.at("maxHp").get<long long>()}},
        {"fightsLost", {run.fightsLost, historical.at("fightsLost").get<long long>()}},
        {"deathCombat", {run.deathCombat, historical.at("deathCombat").get<long long>()}},
        {"deathEncounter", {run.deathEncounter, historical.at("deathEncounter").get<long long>()}}};
    std::vector<std::string> failures;
    nlohmann::json runJson = nlohmann::json::object();
    for (const auto &[name, values] : runFields) {
        runJson[name] = {{"reconstructed", values.first}, {"historical", values.second}};
        if (values.first != values.second) failures.push_back("run_" + name + "_mismatch");
    }
    if (!source.captured) failures.push_back("boss_entry_not_reached");
    if (source.captured && source.encounterEnum != boss) failures.push_back("boss_identity_mismatch");
    if (source.captured && (!source.finished || source.won != expectedSourceWon))
        failures.push_back(expectedSourceWon == 0 ? "source_boss_not_lost" : "source_boss_not_won");
    if (source.captured && source.budget != 10000) failures.push_back("source_budget_not_10000");

    std::vector<BossRescueRow> rows;
    nlohmann::json checks = nlohmann::json::object();
    if (source.captured && source.finished) {
        const std::string preDigest = bossRescueStateDigest(*source.entry.pre, &source.entry.agent);
        if (preDigest != source.startDigest) failures.push_back("detached_copy_digest_mismatch");
        rows.push_back(bossRescueRun(source.entry, "control", "A", 10000, -1, std::nullopt));
        for (int rep = 0; rep < reps; ++rep) {
            const auto planner = plannerSeed(rep);
            if (prep) {
                rows.push_back(bossRescueRun(source.entry, freshKind, "10k", 10000, rep, planner));
                continue;
            }
            const std::vector<std::pair<std::string, int>> order = rep % 2 == 0
                ? std::vector<std::pair<std::string, int>>{{"A", 10000}, {"B", 40000}}
                : std::vector<std::pair<std::string, int>>{{"B", 40000}, {"A", 10000}};
            for (const auto &[arm, budget] : order)
                rows.push_back(bossRescueRun(source.entry, arm, arm, budget, rep, planner));
        }
        rows.push_back(bossRescueRun(source.entry, "control_repeat", "A", 10000, -1, std::nullopt));
        rows.push_back(bossRescueRun(source.entry, repeatKind, prep ? "10k" : "A", 10000, 0, plannerSeed(0)));

        const auto &control = rows.front();
        const bool controlParity = control.result.valid && control.result.won == source.won
            && control.result.terminalHp == source.terminalHp && control.detail.trace == source.trace
            && control.detail.postExitDigest == source.postExitDigest
            && static_cast<std::int64_t>(control.result.simulations) == source.simulations;
        checks["controlParity"] = {{"pass", controlParity},
            {"won", control.result.won == source.won}, {"terminalHp", control.result.terminalHp == source.terminalHp},
            {"fullTrace", control.detail.trace == source.trace},
            {"postExitStateDigest", control.detail.postExitDigest == source.postExitDigest},
            {"simulations", static_cast<std::int64_t>(control.result.simulations) == source.simulations}};
        if (!controlParity) failures.push_back("control_parity_failure");
        const BossRescueRow *aRep0 = nullptr;
        for (const auto &row : rows) if (row.kind == freshKind && row.rep == 0) aRep0 = &row;
        const bool controlRepeat = bossRescueSameRun(control, rows[rows.size() - 2]);
        const bool aRepeat = aRep0 && bossRescueSameRun(*aRep0, rows.back());
        checks["controlRepeatIdentical"] = controlRepeat;
        checks["aRep0RepeatIdentical"] = aRepeat;
        if (!controlRepeat || !aRepeat) failures.push_back("replay_not_deterministic_or_contaminated");
        bool digests = bossRescueStateDigest(*source.entry.pre, &source.entry.agent) == source.startDigest;
        bool budgets = true, valid = true;
        for (const auto &row : rows) {
            digests = digests && row.detail.startDigest == source.startDigest;
            budgets = budgets && row.detail.minRootSteps == row.budget && row.detail.maxRootSteps == row.budget
                && row.detail.searchSteps == static_cast<std::int64_t>(row.result.decisions) * row.budget
                && static_cast<std::int64_t>(row.result.simulations) == row.detail.searchSteps;
            valid = valid && row.result.valid;
        }
        checks["startDigestIdentical"] = digests;
        checks["budgetSpentEveryRoot"] = budgets;
        checks["allRowsValid"] = valid;
        if (!digests) failures.push_back("start_digest_mismatch");
        if (!budgets) failures.push_back("budget_not_spent");
        if (!valid) failures.push_back("invalid_replay_row");
    }

    std::ofstream out(rowsPath);
    if (!out) throw std::runtime_error("boss rescue #347: cannot open " + rowsPath);
    out << "stateId,stratum,sourceArm,seed,act,boss,kind,arm,budget,rep,plannerSeed,startDigest,valid,"
           "outcome,won,terminalHp,postExitHp,potionsAfter,postExitDigest,decisions,simulations,"
           "searchSteps,minRootSteps,maxRootSteps,reroots,freshRoots,singletonSkips,cpuSeconds,"
           "wallSeconds,traceLen,traceSha256,quarantineReason,postExitSummary,trace\n";
    const auto prefix = [&](std::ostream &o) {
        o << stateId << ',' << spec.at("stratum").get<std::string>() << ',' << sourceArm << ',' << seed
          << ',' << act << ',' << boss << ',';
    };
    if (source.captured && source.finished) {
        prefix(out);
        out << "source,source," << source.budget << ",-1,," << source.startDigest << ",1,"
            << (source.won == 1 ? "PLAYER_VICTORY" : source.won == 0 ? "PLAYER_LOSS" : "UNDECIDED") << ','
            << source.won << ',' << source.terminalHp << ',' << source.postExitHp << ',' << source.potionsAfter
            << ',' << source.postExitDigest << ',' << source.decisions << ',' << source.simulations << ','
            << source.searchSteps << ',' << source.minRootSteps << ',' << source.maxRootSteps << ",,,,"
            << std::setprecision(9) << source.cpuSeconds << ",," << source.trace.size() << ','
            << vwinSha256(bossRescueTraceText(source.trace)) << ",," << csvQuote(source.postExitSummary)
            << ',' << bossRescueTraceText(source.trace) << '\n';
    }
    for (const auto &row : rows) {
        prefix(out);
        std::ostringstream planner;
        if (row.plannerSeed) planner << std::hex << std::setw(16) << std::setfill('0') << *row.plannerSeed;
        out << row.kind << ',' << row.arm << ',' << row.budget << ',' << row.rep << ',' << planner.str() << ','
            << row.detail.startDigest << ',' << (row.result.valid ? 1 : 0) << ',' << row.result.outcome << ','
            << row.result.won << ',' << row.result.terminalHp << ',' << row.result.postAfterBattleHp << ','
            << row.result.potionsAfter << ',' << row.detail.postExitDigest << ',' << row.result.decisions << ','
            << row.result.simulations << ',' << row.detail.searchSteps << ',' << row.detail.minRootSteps << ','
            << row.detail.maxRootSteps << ',' << row.detail.reroots << ',' << row.detail.freshRoots << ','
            << row.detail.singletonSkips << ',' << std::setprecision(9) << row.result.cpuSeconds << ','
            << row.detail.wallSeconds << ',' << row.detail.trace.size() << ','
            << vwinSha256(bossRescueTraceText(row.detail.trace)) << ',' << csvQuote(row.result.quarantineReason)
            << ',' << csvQuote(row.detail.postExitSummary) << ',' << bossRescueTraceText(row.detail.trace) << '\n';
    }
    out.close();
    if (!out) throw std::runtime_error("boss rescue #347: write failed " + rowsPath);

    nlohmann::json env = nlohmann::json::object();
    for (char **e = environ; *e; ++e) {
        const std::string kv = *e;
        if (kv.rfind("STS_", 0) == 0 || kv.rfind("OMP_", 0) == 0)
            env[kv.substr(0, kv.find('='))] = kv.substr(kv.find('=') + 1);
    }
    nlohmann::json plannerSeeds = nlohmann::json::array();
    for (int rep = 0; rep < reps; ++rep) {
        std::ostringstream hex;
        hex << std::hex << std::setw(16) << std::setfill('0') << plannerSeed(rep);
        plannerSeeds.push_back(hex.str());
    }
    nlohmann::json entryJson = {
        {"schema", prep ? "boss_preparation_rmatch_347_entry_v1" : "boss_budget_rescue_347_pilot_entry_v1"},
        {"stateId", stateId}, {"stratum", spec.at("stratum")}, {"sourceArm", sourceArm}, {"seed", seed},
        {"act", act}, {"expectedBoss", boss},
        {"capturedBoss", source.encounterEnum}, {"floor", source.captured ? source.entry.floor : -1},
        {"bossBattlesSeen", source.bossBattles},
        {"entrySummary", source.captured ? bossRescueStateSummary(*source.entry.pre) : ""},
        {"startDigest", source.startDigest},
        {"reconstruction", runJson}, {"sourceFight", {{"won", source.won}, {"terminalHp", source.terminalHp},
            {"postExitHp", source.postExitHp}, {"postExitDigest", source.postExitDigest},
            {"decisions", source.decisions}, {"simulations", source.simulations},
            {"traceLen", source.trace.size()}, {"cpuSeconds", source.cpuSeconds}}},
        {"plannerSeedDomain", prep ? "boss-prep-347-planner-v1:{runSeed}:{act}:{rep}"
                                   : "boss-rescue-347-planner-v1:{stateId}:{rep}"},
        {"plannerSeeds", plannerSeeds}, {"checks", checks},
        {"status", failures.empty() ? "VALID" : "INVALID"}, {"failures", failures},
        {"provenance", {{"executableGitSha", trainingExecutableGitSha()},
            {"executableSha256", fileSha256(g_mainBinaryPath)},
            {"selectionSha256", fileSha256(selectionPath)},
            {"policy", effectiveOocPolicySpecification()}, {"environment", env}}},
        {"outputs", {{"rowsSha256", fileSha256(rowsPath)}}},
    };
    if (prep) {
        entryJson["expectedSourceWon"] = expectedSourceWon;
        entryJson["checks"]["checkedReps"] = reps;
        entryJson["entryDescriptor"] = source.captured
            ? bossPrepEntryDescriptor(*source.entry.pre, source.entry.path) : nlohmann::json();
    }
    std::ofstream entryOut(entryPath);
    if (!entryOut) throw std::runtime_error("boss rescue #347: cannot open " + entryPath);
    entryOut << entryJson.dump(2) << '\n';
    std::cout << "boss rescue #347 " << stateId << " status=" << (failures.empty() ? "VALID" : "INVALID");
    for (const auto &f : failures) std::cout << ' ' << f;
    std::cout << " -> " << outPrefix << '\n';
    return failures.empty() ? 0 : 3;
}

// Fixture checks for the replay boundary on the act-1 boss of one seed at a
// small budget: control parity, determinism, planner-seed consumption, arm
// isolation and per-root budgets. Runs whatever arm environment is exported.
int bossRescue347SelfTest(int nSeeds, std::uint64_t seed, int sims) {
    if (nSeeds != 1 || sims < 1) throw std::runtime_error("boss rescue #347 selftest: one seed, positive sims");
    RunResult run{};
    auto source = bossRescueCapture(seed, sims, 1, run);
    auto require = [](bool ok, const std::string &what) {
        if (!ok) throw std::runtime_error("boss rescue #347 selftest: " + what);
        std::cout << "PASS " << what << '\n';
    };
    require(source.captured && source.finished, "act-1 boss entry captured and fought");
    require(bossRescueStateDigest(*source.entry.pre, &source.entry.agent) == source.startDigest,
            "detached entry copy has the live entry digest");
    const auto control = bossRescueRun(source.entry, "control", "A", sims, -1, std::nullopt);
    require(control.result.won == source.won && control.result.terminalHp == source.terminalHp
            && control.detail.trace == source.trace && control.detail.postExitDigest == source.postExitDigest,
            "original-seed control reproduces the source fight (outcome, HP, trace, post-exit state)");
    const int small = std::max(1, sims / 4);
    std::set<std::vector<int>> traces;
    std::vector<BossRescueRow> fresh;
    for (int rep = 0; rep < 6; ++rep) {
        fresh.push_back(bossRescueRun(source.entry, "A", "A", small, rep, bossRescuePlannerSeed("selftest", rep)));
        traces.insert(fresh.back().detail.trace);
    }
    require(traces.size() >= 2, "fresh planner seeds change the search (" + std::to_string(traces.size())
            + " distinct traces of 6)");
    const auto big = bossRescueRun(source.entry, "B", "B", 4 * small, 0, bossRescuePlannerSeed("selftest", 0));
    bool budgets = true;
    for (const auto *row : {&control, &big}) budgets = budgets && row->detail.minRootSteps == row->budget
        && row->detail.maxRootSteps == row->budget;
    for (const auto &row : fresh) budgets = budgets && row.detail.minRootSteps == row.budget
        && row.detail.maxRootSteps == row.budget;
    require(budgets, "every searched root runs exactly its budget");
    const auto again = bossRescueRun(source.entry, "A", "A", small, 0, bossRescuePlannerSeed("selftest", 0));
    require(bossRescueSameRun(fresh.front(), again), "same state, seed and budget reproduce after other arms");
    const auto controlAgain = bossRescueRun(source.entry, "control", "A", sims, -1, std::nullopt);
    require(bossRescueSameRun(control, controlAgain), "control repeat identical after other arms");
    bool digests = bossRescueStateDigest(*source.entry.pre, &source.entry.agent) == source.startDigest;
    for (const auto &row : fresh) digests = digests && row.detail.startDigest == source.startDigest;
    require(digests && big.detail.startDigest == source.startDigest, "all arms start from the entry digest");
    std::cout << "boss rescue #347 selftest PASS seed=" << seed << " sims=" << sims << " decisions="
              << control.result.decisions << '\n';
    return 0;
}

// #400 Stage 1: replay every real fight of each source trajectory under a
// small fixed grid of Silver search constants. Each arm starts from a detached
// copy of the pre-battle state with the same agent and hidden future; only the
// search constants differ. The control arm must reproduce the source fight.
const std::vector<std::pair<std::string, search::NativeSilverSearchParams>> &silverParamScreen400Arms() {
    static const std::vector<std::pair<std::string, search::NativeSilverSearchParams>> arms = [] {
        const search::NativeSilverSearchParams control;
        auto exploration = [&](double c) {
            auto p = control; p.exploration = c; p.explorationChance = c; return p;
        };
        auto wideningAlpha = [&](double alpha) {
            auto p = control; p.chanceWideningAlpha = alpha; p.endTurnWideningAlpha = alpha; return p;
        };
        return std::vector<std::pair<std::string, search::NativeSilverSearchParams>>{
            {"control", control},
            {"c12", exploration(12.5)}, {"c50", exploration(50.0)},
            {"wa040", wideningAlpha(0.40)}, {"wa065", wideningAlpha(0.65)}};
    }();
    return arms;
}

void silverParamScreen400Gen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                             long long seedOffset, const std::string &teacherPath) {
    if (nSeeds < 1 || sims != 10000 || asc != 0 || seedOffset < 0)
        throw std::runtime_error("silver param screen #400: requires positive seed count, exact 10k, Ascension 0");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true);
    vwinRequireProductionPolicy(teacher);
    const search::NativeSilverSearchParams defaults;
    const auto &spec = teacher.specification["search_configuration"];
    if (spec.value("exploration_parameter", -1.0) != defaults.exploration
        || spec.value("exploration_parameter_chance", -1.0) != defaults.explorationChance
        || spec.value("chance_widening_c", -1.0) != defaults.chanceWideningC
        || spec.value("chance_widening_alpha", -1.0) != defaults.chanceWideningAlpha
        || spec.value("end_turn_widening_c", -1.0) != defaults.endTurnWideningC
        || spec.value("end_turn_widening_alpha", -1.0) != defaults.endTurnWideningAlpha)
        throw std::runtime_error("silver param screen #400: control arm differs from the frozen teacher constants");
    const std::string statesPath = outPrefix + ".states.csv";
    const std::string armsPath = outPrefix + ".arms.csv";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {statesPath, armsPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("silver param screen #400: refusing to overwrite existing output " + path);
    std::ofstream states(statesPath), arms(armsPath);
    if (!states || !arms) throw std::runtime_error("silver param screen #400: cannot open outputs");
    states << "stateId,sourceSeed,fightIdx,act,floor,roomClass,encounter,preHp,preMaxHp,prePotions,"
              "deckSize,relicCount,sourceWon,sourceSignedOutcome,sourceTerminalHp,"
              "sourcePostAfterBattleHp,sourceFirstActionBits,trajectoryValid\n";
    arms << "stateId,sourceSeed,fightIdx,arm,exploration,explorationChance,chanceWideningC,"
            "chanceWideningAlpha,endTurnWideningC,endTurnWideningAlpha,outcome,won,signedOutcome,"
            "terminalHp,postAfterBattleHp,potionsAfter,firstActionBits,cpuSeconds,simulations,"
            "decisions,valid,controlReplayMatch,quarantineReason\n";
    nlohmann::json armSpec = nlohmann::json::object();
    for (const auto &[name, p] : silverParamScreen400Arms())
        armSpec[name] = {{"exploration", p.exploration}, {"explorationChance", p.explorationChance},
                         {"chanceWideningC", p.chanceWideningC}, {"chanceWideningAlpha", p.chanceWideningAlpha},
                         {"endTurnWideningC", p.endTurnWideningC}, {"endTurnWideningAlpha", p.endTurnWideningAlpha}};
    int completeSources = 0, validSources = 0, states_ = 0, controlMatches = 0, controlMismatches = 0;
    int invalidArmRows = 0;
    nlohmann::json perSeed = nlohmann::json::array();
    for (int i = 0; i < nSeeds; ++i) {
        VwinCollector capture;
        capture.sourceSeed = static_cast<std::uint64_t>(seedOffset + i);
        capture.captureBoss = true;
        capture.captureAllCombatEntries = true;
        const auto source = runCombatEvalGenSeed(capture.sourceSeed, sims, asc, teacher,
                                                  false, &capture);
        if (source.trajectoryComplete) ++completeSources;
        if (source.trajectoryValid) ++validSources;
        perSeed.push_back({{"seed", capture.sourceSeed}, {"complete", source.trajectoryComplete},
                           {"valid", source.trajectoryValid}, {"fights", capture.bossEntries.size()},
                           {"finalFloor", source.finalFloor},
                           {"won", source.finalOutcome == GameOutcome::PLAYER_VICTORY}});
        for (auto &entry : capture.bossEntries) {
            const auto stateId = "s" + std::to_string(entry.pre->seed) + "-f" + std::to_string(entry.fightIdx);
            states << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ','
                   << entry.act << ',' << entry.floor << ',' << entry.roomClass << ','
                   << csvQuote(entry.encounter) << ',' << entry.pre->curHp << ',' << entry.pre->maxHp << ','
                   << entry.pre->potionCount << ',' << entry.pre->deck.cards.size() << ','
                   << entry.pre->relics.relics.size() << ',' << entry.sourceWon << ','
                   << std::setprecision(17) << entry.signedOutcome << ',' << entry.terminalHp << ','
                   << entry.postAfterBattleHp << ',' << entry.firstActionBits << ','
                   << (entry.sourceTrajectoryValid ? 1 : 0) << '\n';
            ++states_;
            bool controlMatch = false;
            for (const auto &[armName, params] : silverParamScreen400Arms()) {
                const auto result = vwinRunBossArm(entry, sims, &params);
                const bool isControl = armName == "control";
                if (isControl) {
                    controlMatch = result.valid && entry.labelValid && result.won == entry.sourceWon
                        && result.terminalHp == entry.terminalHp
                        && result.postAfterBattleHp == entry.postAfterBattleHp
                        && result.firstActionBits == entry.firstActionBits;
                    if (controlMatch) ++controlMatches; else ++controlMismatches;
                }
                const bool valid = result.valid && entry.sourceTrajectoryValid && controlMatch;
                std::string reason = result.quarantineReason;
                if (reason.empty() && !entry.sourceTrajectoryValid) reason = "source_trajectory_invalid";
                if (reason.empty() && !controlMatch)
                    reason = isControl ? "control_replay_mismatch" : "control_state_invalid";
                if (!valid) ++invalidArmRows;
                arms << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ',' << armName << ','
                     << std::setprecision(17) << params.exploration << ',' << params.explorationChance << ','
                     << params.chanceWideningC << ',' << params.chanceWideningAlpha << ','
                     << params.endTurnWideningC << ',' << params.endTurnWideningAlpha << ','
                     << result.outcome << ',' << result.won << ',' << result.signedOutcome << ','
                     << result.terminalHp << ',' << result.postAfterBattleHp << ',' << result.potionsAfter << ','
                     << result.firstActionBits << ',' << std::setprecision(9) << result.cpuSeconds << ','
                     << result.simulations << ',' << result.decisions << ',' << (valid ? 1 : 0) << ','
                     << (isControl ? (controlMatch ? 1 : 0) : -1) << ',' << csvQuote(reason) << '\n';
            }
        }
        states.flush(); arms.flush();
    }
    states.close(); arms.close();
    nlohmann::json manifest = {
        {"schemaVersion", "silver_param_screen_400_stage1_v1"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification}, {"policy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"simulationsPerDecision", sims}, {"arms", armSpec},
        {"sources", std::move(perSeed)},
        {"integrity", {{"completeSources", completeSources}, {"validSources", validSources},
            {"states", states_}, {"controlReplayMatches", controlMatches},
            {"controlReplayMismatches", controlMismatches}, {"invalidArmRows", invalidArmRows}}},
        {"outputs", {{"statesSha256", fileSha256(statesPath)}, {"armsSha256", fileSha256(armsPath)}}}
    };
    std::ofstream manifestOut(manifestPath);
    if (!manifestOut) throw std::runtime_error("silver param screen #400: cannot write manifest");
    manifestOut << manifest.dump(2) << '\n';
    std::cout << "silver param screen #400 teacher=" << teacher.id << " sourceValid=" << validSources
              << '/' << nSeeds << " states=" << states_ << " control-replay=" << controlMatches << '/'
              << controlMatches + controlMismatches << " -> " << outPrefix << "\n";
}

// Learned-stop replay A/B: replay every real fight of each exact-10k source
// trajectory under the flat 10k control (must reproduce the source fight), the
// production #199 retained-root adaptive policy, strict-lock-only stopping, and
// the learned stopping policy. Same state, agent and hidden future per arm; only the budget policy
// differs. Adaptive and learned arms commit one-action roots unsearched, as
// production does.
void silverStopReplayGen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                         long long seedOffset, const std::string &teacherPath) {
    if (nSeeds < 1 || sims != 10000 || asc != 0 || seedOffset < 0)
        throw std::runtime_error("silver stop replay: requires positive seed count, exact 10k, Ascension 0");
    if (!search::nativeSilverStopModelTrained())
        throw std::runtime_error("silver stop replay: the compiled stop model is untrained");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true);
    vwinRequireProductionPolicy(teacher);
    using Policy = search::NativeSilverBudgetOverride::Policy;
    const std::vector<std::pair<std::string, search::NativeSilverBudgetOverride>> armDefs = {
        {"control", {Policy::Flat, false}},
        {"adaptive199", {Policy::Adaptive, true}},
        {"lockonly", {Policy::LockOnly, true}},
        {"learned", {Policy::LearnedStop, true}},
    };
    const std::string statesPath = outPrefix + ".states.csv";
    const std::string armsPath = outPrefix + ".arms.csv";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {statesPath, armsPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("silver stop replay: refusing to overwrite existing output " + path);
    std::ofstream states(statesPath), arms(armsPath);
    if (!states || !arms) throw std::runtime_error("silver stop replay: cannot open outputs");
    states << "stateId,sourceSeed,fightIdx,act,floor,roomClass,encounter,preHp,preMaxHp,prePotions,"
              "sourceWon,sourceSignedOutcome,sourceTerminalHp,sourcePostAfterBattleHp,"
              "sourceFirstActionBits,trajectoryValid\n";
    arms << "stateId,sourceSeed,fightIdx,arm,outcome,won,signedOutcome,terminalHp,postAfterBattleHp,"
            "potionsAfter,firstActionBits,cpuSeconds,simulations,decisions,lockStops,modelStops,valid,"
            "controlReplayMatch,quarantineReason\n";
    int completeSources = 0, validSources = 0, states_ = 0, controlMatches = 0, controlMismatches = 0;
    int invalidArmRows = 0;
    nlohmann::json perSeed = nlohmann::json::array();
    for (int i = 0; i < nSeeds; ++i) {
        VwinCollector capture;
        capture.sourceSeed = static_cast<std::uint64_t>(seedOffset + i);
        capture.captureBoss = true;
        capture.captureAllCombatEntries = true;
        const auto source = runCombatEvalGenSeed(capture.sourceSeed, sims, asc, teacher, false, &capture);
        if (source.trajectoryComplete) ++completeSources;
        if (source.trajectoryValid) ++validSources;
        perSeed.push_back({{"seed", capture.sourceSeed}, {"complete", source.trajectoryComplete},
                           {"valid", source.trajectoryValid}, {"fights", capture.bossEntries.size()},
                           {"finalFloor", source.finalFloor},
                           {"won", source.finalOutcome == GameOutcome::PLAYER_VICTORY}});
        for (auto &entry : capture.bossEntries) {
            const auto stateId = "s" + std::to_string(entry.pre->seed) + "-f" + std::to_string(entry.fightIdx);
            states << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ','
                   << entry.act << ',' << entry.floor << ',' << entry.roomClass << ','
                   << csvQuote(entry.encounter) << ',' << entry.pre->curHp << ',' << entry.pre->maxHp << ','
                   << entry.pre->potionCount << ',' << entry.sourceWon << ','
                   << std::setprecision(17) << entry.signedOutcome << ',' << entry.terminalHp << ','
                   << entry.postAfterBattleHp << ',' << entry.firstActionBits << ','
                   << (entry.sourceTrajectoryValid ? 1 : 0) << '\n';
            ++states_;
            bool controlMatch = false;
            for (const auto &[armName, policy] : armDefs) {
                struct BudgetScope {
                    explicit BudgetScope(const search::NativeSilverBudgetOverride &p) {
                        search::g_nativeSilverBudgetOverride = p;
                    }
                    ~BudgetScope() { search::g_nativeSilverBudgetOverride.reset(); }
                } budgetScope(policy);
                const auto result = vwinRunBossArm(entry, sims);
                const bool isControl = armName == "control";
                if (isControl) {
                    controlMatch = result.valid && entry.labelValid && result.won == entry.sourceWon
                        && result.terminalHp == entry.terminalHp
                        && result.postAfterBattleHp == entry.postAfterBattleHp
                        && result.firstActionBits == entry.firstActionBits;
                    if (controlMatch) ++controlMatches; else ++controlMismatches;
                }
                const bool valid = result.valid && entry.sourceTrajectoryValid && controlMatch;
                std::string reason = result.quarantineReason;
                if (reason.empty() && !entry.sourceTrajectoryValid) reason = "source_trajectory_invalid";
                if (reason.empty() && !controlMatch)
                    reason = isControl ? "control_replay_mismatch" : "control_state_invalid";
                if (!valid) ++invalidArmRows;
                arms << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ',' << armName << ','
                     << result.outcome << ',' << result.won << ',' << std::setprecision(17)
                     << result.signedOutcome << ',' << result.terminalHp << ',' << result.postAfterBattleHp << ','
                     << result.potionsAfter << ',' << result.firstActionBits << ',' << std::setprecision(9)
                     << result.cpuSeconds << ',' << result.simulations << ',' << result.decisions << ','
                     << result.lockStops << ',' << result.modelStops << ','
                     << (valid ? 1 : 0) << ',' << (isControl ? (controlMatch ? 1 : 0) : -1) << ','
                     << csvQuote(reason) << '\n';
            }
        }
        states.flush(); arms.flush();
    }
    states.close(); arms.close();
    nlohmann::json manifest = {
        {"schemaVersion", "silver_stop_replay_v2"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification}, {"policy", effectiveOocPolicySpecification()},
        {"stopModel", search::nativeSilverStopModelId()},
        {"stopThreshold", search::nativeSilverLearnedStopThreshold()},
        {"adaptiveTopGap", search::nativeSilverAdaptiveTopGap()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"simulationsPerDecision", sims}, {"arms", {"control", "adaptive199", "lockonly", "learned"}},
        {"sources", std::move(perSeed)},
        {"integrity", {{"completeSources", completeSources}, {"validSources", validSources},
            {"states", states_}, {"controlReplayMatches", controlMatches},
            {"controlReplayMismatches", controlMismatches}, {"invalidArmRows", invalidArmRows}}},
        {"outputs", {{"statesSha256", fileSha256(statesPath)}, {"armsSha256", fileSha256(armsPath)}}}
    };
    std::ofstream manifestOut(manifestPath);
    if (!manifestOut) throw std::runtime_error("silver stop replay: cannot write manifest");
    manifestOut << manifest.dump(2) << '\n';
    std::cout << "silver stop replay teacher=" << teacher.id << " model=" << search::nativeSilverStopModelId()
              << " sourceValid=" << validSources << '/' << nSeeds << " states=" << states_
              << " control-replay=" << controlMatches << '/' << controlMatches + controlMismatches
              << " -> " << outPrefix << "\n";
}

// CTM vs low-sim Silver as combat-outcome forecasters (research comparison).
// Replays every real fight of each exact-10k source trajectory. At each fight
// entry it scores the production CTM stack (survival and winning-HP expectation,
// CPU per forecast and per sample) and replays the fight under fixed Silver arms.
// "control" keeps the source hidden future and must reproduce the source fight;
// every other arm redraws the six combat RNG streams the battle carries (counters
// kept), as a planner resolving a hypothetical fight would. Replicate k uses the
// same redraw and planner seed in every arm. The root prior is off for the source
// and the 10k arms and on for the prior arms (thread override).
namespace {
std::uint64_t ctmSilverMix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
std::uint64_t ctmSilverReplicateSeed(std::uint64_t sourceSeed, int fightIdx, int k, std::uint64_t salt) {
    return ctmSilverMix(ctmSilverMix(sourceSeed ^ salt) ^ (static_cast<std::uint64_t>(fightIdx) << 16)
                        ^ static_cast<std::uint64_t>(k));
}
void ctmSilverRedrawCombatFuture(GameContext &gc, std::uint64_t seed) {
    std::mt19937_64 rng(seed);
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng, &gc.monsterHpRng,
                        &gc.potionRng, &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter;
    }
}
struct RootPriorScope {
    explicit RootPriorScope(bool on) { search::g_nativeSilverRootPriorOverride = on; }
    ~RootPriorScope() { search::g_nativeSilverRootPriorOverride.reset(); }
};
struct CtmSilverArm { std::string name; int budget; bool prior; bool redraw; int replicates; };
// One forecast sample of the RAW post-combat persistent state (the fields the CTM
// models; RNG streams excluded). The deck is written as an FNV-1a hash.
void ctmSilverWriteSample(std::ostream &out, const std::string &stateId, const std::string &forecaster,
                          int k, const char *outcome,
                          const one_combat::CombatTransitionPersistentState &s) {
    std::ostringstream potions, relics;
    for (int i = 0; i < 5; ++i) potions << (i ? ";" : "") << s.potions[i];
    auto sorted = s.relics;
    std::sort(sorted.begin(), sorted.end(), [](const auto &a, const auto &b) {
        return a.id != b.id ? a.id < b.id : a.data < b.data; });
    for (std::size_t i = 0; i < sorted.size(); ++i) relics << (i ? ";" : "") << sorted[i].id << ':' << sorted[i].data;
    std::vector<std::tuple<int, int, int>> cards;
    for (const auto &c : s.deck) cards.emplace_back(c.id, c.upgraded ? 1 : 0, c.misc);
    std::sort(cards.begin(), cards.end());
    std::uint64_t h = 1469598103934665603ULL;
    for (const auto &[id, up, misc] : cards)
        for (const int v : {id, up, misc, -7}) { h ^= static_cast<std::uint32_t>(v); h *= 1099511628211ULL; }
    out << stateId << ',' << forecaster << ',' << k << ',' << outcome << ',' << s.curHp << ',' << s.maxHp << ','
        << s.gold << ',' << s.potionCount << ',' << potions.str() << ',' << relics.str() << ','
        << std::hex << h << std::dec << ',' << (s.smokeBombUsed ? 1 : 0) << ',' << s.stolenGold << '\n';
}
} // namespace

void ctmSilverCompareGen(int nSeeds, int asc, const std::string &outPrefix, long long seedOffset,
                         const std::string &teacherPath, int replicates) {
    constexpr int sims = 10000;
    if (nSeeds < 1 || asc != 0 || seedOffset < 0 || replicates < 0)
        throw std::runtime_error("ctm vs silver: requires a positive seed count, replicates >= 0, Ascension 0");
    // REPLICATES = 0 is CTM-only mode: no Silver arms; the production CTM and a
    // research candidate stack (STS_CTMSILVER_CANDIDATE_FAST/_STANDARD plus the
    // STS_CTM_RESEARCH_CANDIDATE_MANIFEST pair, active Lizard on) are scored on the
    // same states. Its truth comes from a full run on the same seeds.
    const bool ctmOnly = replicates == 0;
    if (!search::nativeSilverExactRootBudgets())
        throw std::runtime_error("ctm vs silver: requires STS_SILVER_EXACT_ROOT_BUDGETS=1 (flat budgets, no boss multiplier)");
    if (search::nativeSilverRootPriorPath().empty())
        throw std::runtime_error("ctm vs silver: requires STS_SILVER_ROOT_PRIOR and _WEIGHT for the prior arms");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, true);
    vwinRequireProductionPolicy(teacher);
    // Deliberately the pre-#418 production stack (lizard_t2 + except_smoke_v2), not
    // the current default: §408/§410/§411 compare against it, so it stays pinned
    // for reproducibility after the #418 swap to pathb-r2.
    const std::string fastModel = "selfplay/models/combat_transition_deepsets_lizard_t2.native";
    const std::string standardModel = "selfplay/models/combat_transition_near_full_except_smoke_v2.native";
    const one_combat::EntropicBrewFallbackCombatTransitionSampler ctm(fastModel, standardModel, true);
    if (ctm.fastRuntime().researchCandidate())
        throw std::runtime_error("ctm vs silver: expected the production CTM stack, not a research candidate");
    std::unique_ptr<const one_combat::EntropicBrewFallbackCombatTransitionSampler> candidate;
    std::string candidateFast, candidateStandard, candidateId;
    if (ctmOnly) {
        const char *f = std::getenv("STS_CTMSILVER_CANDIDATE_FAST");
        const char *d = std::getenv("STS_CTMSILVER_CANDIDATE_STANDARD");
        if (!f || !*f || !d || !*d)
            throw std::runtime_error("ctm vs silver: REPLICATES=0 requires STS_CTMSILVER_CANDIDATE_FAST and _STANDARD");
        candidateFast = f; candidateStandard = d;
        candidate = std::make_unique<const one_combat::EntropicBrewFallbackCombatTransitionSampler>(
            candidateFast, candidateStandard, true);
        if (!candidate->fastRuntime().researchCandidate())
            throw std::runtime_error("ctm vs silver: candidate stack did not load as a research candidate");
        candidateId = candidate->fastRuntime().identity().at("candidateId").get<std::string>();
    }
    std::vector<CtmSilverArm> arms;
    if (!ctmOnly)
        arms = {
            {"control", sims, false, false, 1},
            {"teacher10k", sims, false, true, 2},
            {"prior256", 256, true, true, replicates},
            {"prior64", 64, true, true, replicates},
            {"plain256", 256, false, true, replicates},
        };
    const std::string statesPath = outPrefix + ".states.csv";
    const std::string armsPath = outPrefix + ".arms.csv";
    const std::string samplesPath = outPrefix + ".samples.csv";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {statesPath, armsPath, samplesPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("ctm vs silver: refusing to overwrite existing output " + path);
    std::ofstream states(statesPath), armsOut(armsPath), samples(samplesPath);
    if (!states || !armsOut || !samples) throw std::runtime_error("ctm vs silver: cannot open outputs");
    samples << "stateId,forecaster,k,outcome,curHp,maxHp,gold,potionCount,potions,relics,deckHash,"
               "smokeBombUsed,stolenGold\n";
    states << "stateId,sourceSeed,fightIdx,act,floor,roomClass,encounter,preHp,preMaxHp,prePotions,"
              "sourceWon,sourceTerminalHp,sourceValid,ctmSupported,ctmReason,ctmPDeath,ctmMeanHpWin,"
              "ctmExpectedHp,ctmForecastCpuUs,ctmSampleCpuUs";
    if (ctmOnly)
        states << ",candSupported,candReason,candPDeath,candMeanHpWin,candExpectedHp,candForecastCpuUs,"
                  "candSampleCpuUs";
    states << '\n';
    armsOut << "stateId,sourceSeed,fightIdx,arm,k,budget,prior,redraw,redrawSeed,won,terminalHp,"
               "cpuSeconds,simulations,decisions,valid,controlReplayMatch,quarantineReason\n";
    nlohmann::json armSpec = nlohmann::json::array();
    for (const auto &a : arms)
        armSpec.push_back({{"name", a.name}, {"budget", a.budget}, {"rootPrior", a.prior},
                           {"redrawCombatFuture", a.redraw}, {"replicates", a.replicates}});
    int completeSources = 0, validSources = 0, nStates = 0, controlMatches = 0, controlMismatches = 0;
    int ctmSupported = 0, invalidArmRows = 0, candidateSupported = 0;
    nlohmann::json perSeed = nlohmann::json::array();
    constexpr int kTimingReps = 20;
    constexpr int kCtmSamples = 32;
    for (int i = 0; i < nSeeds; ++i) {
        VwinCollector capture;
        capture.sourceSeed = static_cast<std::uint64_t>(seedOffset + i);
        capture.captureBoss = true;
        capture.captureAllCombatEntries = true;
        CombatEvalSeedResult source;
        {
            RootPriorScope plain(false);
            source = runCombatEvalGenSeed(capture.sourceSeed, sims, asc, teacher, false, &capture);
        }
        if (source.trajectoryComplete) ++completeSources;
        if (source.trajectoryValid) ++validSources;
        perSeed.push_back({{"seed", capture.sourceSeed}, {"complete", source.trajectoryComplete},
                           {"valid", source.trajectoryValid}, {"fights", capture.bossEntries.size()},
                           {"finalFloor", source.finalFloor},
                           {"won", source.finalOutcome == GameOutcome::PLAYER_VICTORY}});
        for (auto &entry : capture.bossEntries) {
            const auto stateId = "s" + std::to_string(entry.pre->seed) + "-f" + std::to_string(entry.fightIdx);
            const GameContext &pre = *entry.pre;
            const auto encounter = pre.info.encounter;
            // CTM forecast and one sample, as the OOC planner prepares them.
            const auto input = one_combat::captureCombatPredictorInput(pre, encounter, potionKeepValue(pre));
            struct CtmScore { one_combat::CombatRuntimeSupport support;
                              double pDeath = -1, meanHpWin = -1, expectedHp = -1, forecastUs = -1, sampleUs = -1; };
            const auto scoreCtm = [&](const one_combat::EntropicBrewFallbackCombatTransitionSampler &model,
                                      const char *forecaster) {
                CtmScore r;
                r.support = model.support(pre, input);
                if (!r.support.supported) return r;
                const auto e = model.expectation(pre, input);
                if (!e.supported) throw std::runtime_error("ctm vs silver: supported state without expectation");
                double mass = 0, hp = 0;
                for (std::size_t b = 0; b < e.winningHpHistogram.size(); ++b) {
                    mass += e.winningHpHistogram[b];
                    hp += double(e.winningHpMin + int(b)) * e.winningHpHistogram[b];
                }
                r.pDeath = e.death;
                r.meanHpWin = mass > 0 ? hp / mass : 0.0;
                r.expectedHp = (1.0 - r.pDeath) * r.meanHpWin;
                std::uint64_t t0 = vwinThreadCpuNanos();
                for (int rep = 0; rep < kTimingReps; ++rep) {
                    const auto in = one_combat::captureCombatPredictorInput(pre, encounter, potionKeepValue(pre));
                    const auto x = model.expectation(pre, in);
                    if (!x.supported) throw std::runtime_error("ctm vs silver: timing expectation unsupported");
                }
                r.forecastUs = static_cast<double>(vwinThreadCpuNanos() - t0) / 1e3 / kTimingReps;
                std::mt19937_64 sampleRng(ctmSilverReplicateSeed(entry.pre->seed, entry.fightIdx, 0, 0x5A3B1E));
                t0 = vwinThreadCpuNanos();
                for (int rep = 0; rep < kTimingReps; ++rep) {
                    const auto in = one_combat::captureCombatPredictorInput(pre, encounter, potionKeepValue(pre));
                    const auto prepared = model.prepare(pre, in);
                    (void)prepared->sample(sampleRng);
                }
                r.sampleUs = static_cast<double>(vwinThreadCpuNanos() - t0) / 1e3 / kTimingReps;
                // Forecast samples of the whole post-combat state, as the planner draws them.
                std::mt19937_64 drawRng(ctmSilverReplicateSeed(entry.pre->seed, entry.fightIdx, 1, 0x5A3B1E));
                const auto prepared = model.prepare(pre, input);
                for (int k = 0; k < kCtmSamples; ++k) {
                    const auto x = prepared->sample(drawRng);
                    using O = one_combat::CombatRuntimeSample::Outcome;
                    const char *o = x.outcome == O::DEATH ? "DEATH" : x.outcome == O::VICTORY ? "VICTORY"
                        : x.outcome == O::ESCAPE ? "ESCAPE" : "UNSUPPORTED";
                    ctmSilverWriteSample(samples, stateId, forecaster, k, o, x.rawPost);
                }
                return r;
            };
            const auto prod = scoreCtm(ctm, "ctm");
            const auto &support = prod.support;
            if (support.supported) ++ctmSupported;
            const double pDeath = prod.pDeath, meanHpWin = prod.meanHpWin, expectedHp = prod.expectedHp,
                         forecastUs = prod.forecastUs, sampleUs = prod.sampleUs;
            // The candidate (CTM-only mode) draws with the same seeds as production.
            std::optional<CtmScore> cand;
            if (candidate) {
                cand = scoreCtm(*candidate, "ctm_r2");
                if (cand->support.supported) ++candidateSupported;
            }
            states << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ',' << entry.act << ','
                   << entry.floor << ',' << entry.roomClass << ',' << csvQuote(entry.encounter) << ','
                   << pre.curHp << ',' << pre.maxHp << ',' << pre.potionCount << ',' << entry.sourceWon << ','
                   << entry.terminalHp << ',' << (entry.sourceTrajectoryValid && entry.labelValid ? 1 : 0) << ','
                   << (support.supported ? 1 : 0) << ',' << csvQuote(support.supported ? "supported" : support.reason)
                   << ',' << std::setprecision(9) << pDeath << ',' << meanHpWin << ',' << expectedHp << ','
                   << forecastUs << ',' << sampleUs;
            if (cand)
                states << ',' << (cand->support.supported ? 1 : 0) << ','
                       << csvQuote(cand->support.supported ? "supported" : cand->support.reason) << ','
                       << cand->pDeath << ',' << cand->meanHpWin << ',' << cand->expectedHp << ','
                       << cand->forecastUs << ',' << cand->sampleUs;
            states << '\n';
            ++nStates;
            bool controlMatch = false;
            for (const auto &arm : arms) {
                for (int k = 0; k < arm.replicates; ++k) {
                    const std::uint64_t redrawSeed = arm.redraw
                        ? ctmSilverReplicateSeed(entry.pre->seed, entry.fightIdx, k, 0xC0FFEE07) : 0;
                    VwinBossEntry replay;
                    replay.pre = std::make_unique<GameContext>(detachedCounterfactualCopy(*entry.pre));
                    if (arm.redraw) ctmSilverRedrawCombatFuture(*replay.pre, redrawSeed);
                    replay.path = entry.path;
                    replay.agent = entry.agent;
                    replay.policy = entry.policy;
                    replay.fightIdx = entry.fightIdx;
                    std::optional<std::uint64_t> plannerSeed;
                    if (arm.redraw) plannerSeed = ctmSilverReplicateSeed(entry.pre->seed, entry.fightIdx, k, 0x91A77E2);
                    PlannerSeedScope plannerScope(plannerSeed);
                    RootPriorScope priorScope(arm.prior);
                    std::optional<one_combat::CombatTransitionPersistentState> rawPost;
                    VwinArmResult result;
                    {
                        one_combat::CombatTransitionRawObserverScope rawScope(
                            [&](const BattleContext &, GameContext &raw) {
                                if (!rawPost) rawPost = one_combat::captureCombatTransitionState(raw);
                            });
                        result = vwinRunBossArm(replay, arm.budget);
                    }
                    if (rawPost) {
                        const char *o = result.won == 0 ? "DEATH" : rawPost->smokeBombUsed ? "ESCAPE"
                            : result.won == 1 ? "VICTORY" : "UNDECIDED";
                        ctmSilverWriteSample(samples, stateId, arm.name, k, o, *rawPost);
                    }
                    const bool isControl = arm.name == "control";
                    if (isControl) {
                        controlMatch = result.valid && entry.labelValid && result.won == entry.sourceWon
                            && result.terminalHp == entry.terminalHp
                            && result.postAfterBattleHp == entry.postAfterBattleHp
                            && result.firstActionBits == entry.firstActionBits;
                        if (controlMatch) ++controlMatches; else ++controlMismatches;
                    }
                    const bool valid = result.valid && entry.sourceTrajectoryValid && controlMatch;
                    std::string reason = result.quarantineReason;
                    if (reason.empty() && !entry.sourceTrajectoryValid) reason = "source_trajectory_invalid";
                    if (reason.empty() && !controlMatch)
                        reason = isControl ? "control_replay_mismatch" : "control_state_invalid";
                    if (!valid) ++invalidArmRows;
                    armsOut << stateId << ',' << entry.pre->seed << ',' << entry.fightIdx << ',' << arm.name << ','
                            << k << ',' << arm.budget << ',' << (arm.prior ? 1 : 0) << ',' << (arm.redraw ? 1 : 0)
                            << ',' << redrawSeed << ',' << result.won << ',' << result.terminalHp << ','
                            << std::setprecision(9) << result.cpuSeconds << ',' << result.simulations << ','
                            << result.decisions << ',' << (valid ? 1 : 0) << ','
                            << (isControl ? (controlMatch ? 1 : 0) : -1) << ',' << csvQuote(reason) << '\n';
                }
            }
        }
        states.flush(); armsOut.flush(); samples.flush();
    }
    states.close(); armsOut.close(); samples.close();
    nlohmann::json manifest = {
        {"schemaVersion", "ctm_vs_silver_forecast_v1"},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification}, {"policy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"rootPrior", {{"path", search::nativeSilverRootPriorPath()},
                       {"sha256", fileSha256(search::nativeSilverRootPriorPath())},
                       {"weight", search::nativeSilverRootPriorWeight()}}},
        {"ctm", {{"fast", fastModel}, {"fastSha256", fileSha256(fastModel)},
                 {"standard", standardModel}, {"standardSha256", fileSha256(standardModel)},
                 {"activeLizard", true}, {"timingReps", kTimingReps}, {"forecastSamples", kCtmSamples}}},
        {"redraw", "six BattleContext RNG streams (ai, cardRandom, misc, monsterHp, potion, shuffle) reseeded, counters kept"},
        {"ctmOnly", ctmOnly},
        {"candidate", ctmOnly ? nlohmann::json{{"candidateId", candidateId},
            {"fast", candidateFast}, {"fastSha256", fileSha256(candidateFast)},
            {"standard", candidateStandard}, {"standardSha256", fileSha256(candidateStandard)},
            {"manifestSha256", std::getenv("STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256")},
            {"activeLizard", true}, {"supported", candidateSupported}} : nlohmann::json(nullptr)},
        {"arms", armSpec}, {"sources", std::move(perSeed)},
        {"integrity", {{"completeSources", completeSources}, {"validSources", validSources},
            {"states", nStates}, {"ctmSupported", ctmSupported}, {"controlReplayMatches", controlMatches},
            {"controlReplayMismatches", controlMismatches}, {"invalidArmRows", invalidArmRows}}},
        {"outputs", {{"statesSha256", fileSha256(statesPath)}, {"armsSha256", fileSha256(armsPath)},
                     {"samplesSha256", fileSha256(samplesPath)}}}
    };
    std::ofstream manifestOut(manifestPath);
    if (!manifestOut) throw std::runtime_error("ctm vs silver: cannot write manifest");
    manifestOut << manifest.dump(2) << '\n';
    std::cout << "ctm vs silver teacher=" << teacher.id << " sourceValid=" << validSources << '/' << nSeeds
              << " states=" << nStates << " ctmSupported=" << ctmSupported << " control-replay="
              << controlMatches << '/' << controlMatches + controlMismatches << " -> " << outPrefix << "\n";
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
// #418 targeted CTM support collections. Each setup forces a rare state the
// ordinary corpus barely reaches; the manifest names the setup so its rows are
// qualified as their own slice, never mixed into the ordinary distribution.
enum class ForcedCtmSetup { NONE, RITUAL_WRITHING, HIGH_MAXHP, LIZARD_FAIRY, LIZARD_BREW };

static ForcedCtmSetup parseForcedCtmSetup(const std::string &name) {
    if (name.empty()) return ForcedCtmSetup::NONE;
    if (name == "ritual_writhing") return ForcedCtmSetup::RITUAL_WRITHING;
    if (name == "high_maxhp") return ForcedCtmSetup::HIGH_MAXHP;
    if (name == "lizard_fairy") return ForcedCtmSetup::LIZARD_FAIRY;
    if (name == "lizard_brew") return ForcedCtmSetup::LIZARD_BREW;
    throw std::runtime_error("combattransitionforcedgen: unknown setup " + name);
}

// Once, before the first fight: the persistent state the setup needs.
static void applyForcedCtmSetupOnce(ForcedCtmSetup setup, GameContext &gc, std::uint64_t seed) {
    switch (setup) {
        case ForcedCtmSetup::RITUAL_WRITHING:
            gc.deck.obtain(gc, CardId::RITUAL_DAGGER);
            break;
        case ForcedCtmSetup::HIGH_MAXHP: {
            // Max HP 150..220 at full HP, deterministic per seed (SplitMix64).
            std::uint64_t z = seed + 0x9e3779b97f4a7c15ULL;
            z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
            z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
            gc.maxHp = 150 + static_cast<int>((z ^ (z >> 31)) % 71);
            gc.curHp = gc.maxHp;
            break;
        }
        case ForcedCtmSetup::LIZARD_FAIRY:
        case ForcedCtmSetup::LIZARD_BREW:
            gc.obtainRelic(RelicId::LIZARD_TAIL);
            break;
        case ForcedCtmSetup::NONE:
            break;
    }
}

// Before every fight, ahead of the pre-combat capture.
static void applyForcedCtmSetupPerFight(ForcedCtmSetup setup, GameContext &gc) {
    if (setup == ForcedCtmSetup::RITUAL_WRITHING && gc.act == 3 && gc.curRoom == Room::MONSTER) {
        gc.info.encounter = MonsterEncounter::WRITHING_MASS;
    } else if (setup == ForcedCtmSetup::LIZARD_FAIRY || setup == ForcedCtmSetup::LIZARD_BREW) {
        // Keep the potion next to an unused Tail while a slot is free.
        const Potion potion = setup == ForcedCtmSetup::LIZARD_FAIRY ? Potion::FAIRY_POTION
                                                                    : Potion::ENTROPIC_BREW;
        bool held = false;
        for (int i = 0; i < gc.potionCapacity; ++i) held = held || gc.potions[i] == potion;
        if (!held && gc.hasRelic(RelicId::LIZARD_TAIL)
            && gc.relics.getRelicValue(RelicId::LIZARD_TAIL) != 0)
            gc.obtainPotion(potion);
    }
}

static std::string runCombatTransitionGenSeed(std::uint64_t seed, int sims, int asc,
                                              const WholeCombatTeacher &teacher,
                                              ForcedCtmSetup setup = ForcedCtmSetup::NONE) {
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
            if (setup != ForcedCtmSetup::NONE) {
                if (fightIdx == 0) applyForcedCtmSetupOnce(setup, gc, seed);
                applyForcedCtmSetupPerFight(setup, gc);
            }
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
                                bool allowStaleProvenance,
                                const std::string &forcedSetup) {
    const ForcedCtmSetup setup = parseForcedCtmSetup(forcedSetup);
    if (setup != ForcedCtmSetup::NONE && allowStaleProvenance)
        throw std::runtime_error("combattransitionforcedgen: forced setups need a current teacher");
    trainingCampaignStart();
    // Only the Lizard candidate mode passes stale provenance; it keeps the
    // frozen exact-10k teacher.
    const bool lizardCandidateMode = allowStaleProvenance;
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, allowStaleProvenance,
                                                false, !lizardCandidateMode);
    std::ofstream f(outfile);
    if (!f) throw std::runtime_error("combattransitiongen: cannot open output");
    long long rows = 0;
    int completed = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runCombatTransitionGenSeed(seedOffset + s, sims, asc, teacher, setup);
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
        {"forcedSetup", forcedSetup.empty() ? "none" : forcedSetup},
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
                     : setup != ForcedCtmSetup::NONE ? "combattransitionforcedgen teacher="
                     : "combattransitiongen teacher=") << teacher.id << " completed="
              << completed << '/' << nSeeds << " quarantined=" << nSeeds - completed
              << " rows=" << rows << " -> " << outfile << '\n';
    writeTrainingProvenance(outfile, allowStaleProvenance
                                ? "combattransitionlizardtargetcandidategen"
                                : setup != ForcedCtmSetup::NONE ? "combattransitionforcedgen"
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
    if (gc.curRoom == Room::EVENT) {
        // Event snapshots omit curEvent and the option-specific callback (which
        // may also capture transient reward state). Calling afterBattle() here
        // would see an unknown event and recursively call regainControl(). RAW
        // combat labels have already been captured before this continuation, so
        // finish the direct replay without fabricating event rewards.
        gc.regainControlAction = [](GameContext &context) {
            context.screenState = ScreenState::MAP_SCREEN;
            context.regainControlAction = nullptr;
        };
        return;
    }
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
    GameContext forcedTail(CharacterClass::IRONCLAD, 920260922u, 0);
    if (!installRunForcedRelic(forcedTail, RelicId::LIZARD_TAIL) ||
        forcedTail.relics.getRelicValue(RelicId::LIZARD_TAIL) != 1)
        throw std::runtime_error("active Lizard selftest: forced Tail was not initialized active");
    BattleContext forcedTailBattle;
    forcedTailBattle.init(forcedTail, MonsterEncounter::CULTIST);
    if (!forcedTailBattle.player.hasRelic<RelicId::LIZARD_TAIL>())
        throw std::runtime_error("active Lizard selftest: forced Tail missing from battle state");

    GameContext forcedAnchor(CharacterClass::IRONCLAD, 920260921u, 0);
    if (!installRunForcedRelic(forcedAnchor, RelicId::ANCHOR) ||
        forcedAnchor.relics.getRelicValue(RelicId::ANCHOR) != 0)
        throw std::runtime_error("active Lizard selftest: ordinary forced relic data changed");

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

    // The archived event snapshot does not carry curEvent or its transient
    // option callback. Its victory continuation must go directly to the map;
    // calling afterBattle() here would recurse through regainControl().
    GameContext restoredEvent(CharacterClass::IRONCLAD, 920260925u, 0);
    restoredEvent.screenState = ScreenState::BATTLE;
    restoredEvent.curRoom = Room::EVENT;
    restoredEvent.curEvent = Event::INVALID;
    restoredEvent.info.encounter = MonsterEncounter::CULTIST;
    installDirectSnapshotPostBattleAction(restoredEvent);
    BattleContext restoredEventVictory;
    restoredEventVictory.init(restoredEvent, MonsterEncounter::CULTIST);
    restoredEventVictory.outcome = Outcome::PLAYER_VICTORY;
    restoredEventVictory.exitBattle(restoredEvent);
    if (restoredEvent.screenState != ScreenState::MAP_SCREEN
        || restoredEvent.regainControlAction != nullptr)
        throw std::runtime_error("active Lizard selftest: event snapshot victory continuation failed");

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
