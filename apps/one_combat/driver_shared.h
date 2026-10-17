// Shared declarations for the one_combat integration driver translation units
// (apps/one_combat.cpp and the mode implementations split out of it).
#pragma once

#include "one_combat/ooc_mcts_adapter.h"
#include "one_combat/combat_transition_runtime.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <functional>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <random>
#include <string>
#include <thread>
#include <tuple>
#include <unordered_set>
#include <vector>
#include <nlohmann/json.hpp>

#include "game/GameContext.h"
#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatCpsiNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/NativeSilverStopModel.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/SimHealth.h"
#include "sim/search/TrainingIntegrity.h"
#include "game/Map.h"
#include "sim/util/BestBenchMeta.h"
#include "ooc_test_state.h"
#include "ooc_checkpoint_net.h"
#include "ooc_strategic_net.h"
#include "ooc_strategic_tok_net.h"
#include "combat_model_diagnostics.h"
#include "one_combat/compact_tree.h"
#include "one_combat/ooc_native_fallback.h"
#include "one_combat/combat_transition.h"
#include "one_combat/e2c_capture.h"
#include "one_combat/run_features.h"
#include "one_combat/ooc_policy.h"
#include "one_combat/run_driver.h"

#ifdef _OPENMP
#include <omp.h>
#endif

#ifndef _WIN32
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <sys/select.h>
#include <unistd.h>
#include <cstring>
#include <cerrno>
#endif
#include <atomic>
#include <iomanip>
#include <set>
#include <unordered_map>
#include <unordered_set>

using one_combat::CompactTreeNet;
using one_combat::FwdMap;
using one_combat::PathHistory;
using one_combat::forwardMapFeatures;
using one_combat::kNumCardIds;
using one_combat::kNumPotions;
using one_combat::kNumRelics;
using one_combat::richHeader;
using one_combat::richIdxMap;
using one_combat::richRow;
using one_combat::richStateHeader;
using one_combat::oocActionNNPolicy;
using one_combat::oocOnePlyCardRewardPolicy;
using one_combat::oocOnePlyRestPolicy;
using one_combat::oocOnePlyUpgradeSelectPolicy;
using one_combat::oocOnePlyEventPolicy;
using one_combat::oocOnePlyShopPolicy;
using one_combat::oocOnePlyTreasurePolicy;
using one_combat::oocOnePlyBossRelicPolicy;
using one_combat::oocOnePlyMapPolicy;
using one_combat::oocMapRouteSearchPolicy;

using namespace sts;

// ---- Driver state and helpers shared across translation units ----

// OOC policy adapters kept under their legacy unqualified names (one_combat.cpp).
void strategicCands(const sts::GameContext &gc, const sts::search::GameAction &a,
                    int &actionType, int &c1, int &c2, int &c3,
                    int &cand1, int &cand2, int &cand3);
void tokEntity(const sts::GameContext &gc, const sts::search::GameAction &a,
               int &entType, int &entId, float &goldGePrice);

// v_server connection (one_combat.cpp).
int vConnect();
std::string vRequestLine(const std::string &requestWithNewline);

// Mode entry points implemented in split-out translation units.
void runTraceRun(std::uint64_t seed, int sims, int asc);   // run_trace.cpp
void semanticPilotCapture(int count, std::uint64_t offset, const std::string &manifestFile,
                          const std::string &teacherFile);                        // semantic_pilot.cpp
void semanticPilotSelfTest();                                                    // semantic_pilot.cpp
void semanticPilotEvaluate(int count, const std::string &manifestFile, const std::string &outFile,
                           const std::string &teacherFile, const std::string &combatFile = {}); // semantic_pilot.cpp

// Types, globals and helpers defined in one of the driver translation units
// (one_combat.cpp or apps/one_combat/*.cpp) and used by another.
std::string csvQuote(const std::string &s);
std::string fileSha256(const std::string &path);
using WinNet = CompactTreeNet;

// Direct near-term survival supervision for out-of-combat action values.  These
// are deliberately *outcomes of the real counterfactual continuation*, rather
// than a hand-authored encounter tier.  `passed` means that the branch both
// reached and won the target fight; an elite can remain unseen when the chosen
// route avoids all remaining elites, while the next battle and current-act boss
// are normally mandatory unless the branch dies first.
struct FutureFightProbe {
    bool nextCombatSeen = false, nextCombatPassed = false;
    bool nextEliteSeen = false, nextElitePassed = false;
    bool nextBossSeen = false, nextBossPassed = false;
    bool completed = false;  // false only when a bounded rollout was censored
    struct Observation {
        Room room = Room::INVALID;
        MonsterEncounter encounter = MonsterEncounter::INVALID;
        int floor = 0;
        int hp = 0;
        int maxHp = 1;
        bool passed = false;
    };
    // One record for each fight actually reached.  Across encounter-queue
    // samples, reaching a record is precisely its estimated occurrence chance.
    std::vector<Observation> fights;
};

struct OocCounterfactualResult {
    double won;
    double floor;
    double hp;
    int bootstrapped = 0;   // 1 when floor/won came from the native models, 0 on terminal
    bool valid = true;
    bool survivedH = false; // alive at the requested bounded horizon (diagnostic only)
    // Alternative bootstrap (STS_CF_ALT_BOOT_FLOOR_TREES/_WIN_TREES): the same
    // branch endpoint valued by research trees; equals won/floor on terminals.
    double altWon = -1;
    double altFloor = -1;
};
// True when both alternative bootstrap tree files are loaded (research only).
bool altBootstrapEnabled();
struct OocContinuationCost {
    std::uint64_t silverSimulations = 0;
    std::uint64_t combatDecisions = 0;
    std::uint64_t transactionSubdecisions = 0;
    std::uint64_t transactionDecisions = 0;
    double cpuMs = 0.0;
    double wallMs = 0.0;
};
using OocPrefixObserver = std::function<void(const GameContext &, int,
                                               const OocContinuationCost &)>;
struct CombatEvalLabel {
    bool decided, healthOk, escaped, trueDeath, won, turnCapLoss, progressAmbiguous, labelValid;
    double terminalHp, terminalMaxHp, winHpFrac, lossRemainingFrac, signedOutcome;
    int enemyCurHp, enemyMaxHp;
    const char *reason;
    void write(std::ostream &out) const {
        out << won << ',' << trueDeath << ',' << escaped << ',' << turnCapLoss << ','
            << progressAmbiguous << ',' << labelValid << ',' << terminalHp << ',' << terminalMaxHp << ','
            << enemyCurHp << ',' << enemyMaxHp << ',' << winHpFrac << ',' << lossRemainingFrac << ','
            << signedOutcome << ',' << csvQuote(reason);
    }
};
struct CombatEvalFight {
    int act, floor;
    Room room;
    MonsterEncounter encounter;
    std::string features;
    CombatEvalLabel label{};
};
// Compose with the existing observer and restore even if the backend throws.
struct CombatEvalDecisionScope {
    decltype(search::g_onCombatDecision) previous;
    int hooks = 0;
    explicit CombatEvalDecisionScope(bool enabled) : enabled(enabled) {
        if (enabled) {
            previous = std::move(search::g_onCombatDecision);
            search::g_onCombatDecision = [this](const BattleContext &bc) {
                ++hooks;
                if (previous) previous(bc);
            };
        }
    }
    ~CombatEvalDecisionScope() { if (enabled) search::g_onCombatDecision = std::move(previous); }
private:
    bool enabled;
};
struct WholeCombatTeacher { std::string id; nlohmann::json specification; };
extern std::string g_mainBinaryPath;
extern thread_local int t_trainingHealthFailures;
extern WinNet g_winNet;
extern WinNet g_floorNet;
void trainingCampaignStart();
std::string trainingExecutableGitSha();
GameContext detachedCounterfactualCopy(const GameContext &gc);
OocCounterfactualResult
finishOocCounterfactual(GameContext gc, int sims, std::uint64_t agentSeed,
                        PathHistory path, int maxFights = -1, bool bootstrap = false,
                        FutureFightProbe *probe = nullptr, int stopAfterAct = 0,
                        const std::vector<int> *fightSimsSeq = nullptr,
                        bool usePredict = false,
                        const OocPrefixObserver *prefixObserver = nullptr,
                        OocContinuationCost *finalCost = nullptr,
                        bool useFrozenV4 = false,
                        std::vector<CombatEvalFight> *combatCapture = nullptr);
// Effective OOC policy identity: teacher checks and the bestbench sidecar.
nlohmann::json effectiveOocPolicySpecification();
// Effective Silver leaf valuation (leaf terms, escape penalty, rollout card table)
// for data manifests; defaults are recorded, not only the environment as set.
nlohmann::json effectiveSilverLeafSpecification();
WholeCombatTeacher loadWholeCombatTeacher(const std::string &path, int sims,
                                                 bool allowStaleProvenance = false,
                                                 bool requireOocPolicy = false,
                                                 bool allowLearnedStop = false);
void resampleRemainingActEncounters(GameContext &gc, std::uint64_t branchSeed);
void stepCounterfactualAuditSource(GameContext &gc,
                                           search::ScumSearchAgent2 &agent);
bool combatEvalEncounterValid(MonsterEncounter encounter);
const char *combatEvalLabelHeader();
const char *combatEvalRoomClass(Room room);
CombatEvalLabel combatEvalTerminal(const BattleContext &bc, MonsterEncounter encounter,
                                         int hooks, int healthBefore, int healthAfter,
                                         bool allowInitializationTerminal = false);

struct OocPrefixCheckpoint {
    int prefixFight = 0;
    bool survived = false;
    double continuationValue = 0.0;
    double floorValue = 0.0;
    double hp = 0.0;
    double qProduct = 0.0;
    double denseValue = 0.0;
    std::uint64_t silverSimulations = 0;
    std::uint64_t combatDecisions = 0;
    double cpuMs = 0.0;
    double wallMs = 0.0;
    bool valid = false;
};

std::string actionDescription(const search::GameAction &action, const GameContext &gc);

bool advanceOocToNextBattle(GameContext &gc, int sims, std::uint64_t agentSeed,
                                   PathHistory path, std::ostringstream *failureTrace=nullptr);

void combatEvalGen(int nSeeds, int sims, int asc, const std::string &outfile,
                          long long seedOffset, const std::string &teacherPath,
                          const std::string &runoutPath = {});

// Current-policy v_win refresh collector. OUT_PREFIX produces .map.csv,
// .win_raw.csv, .decisions.csv, .branches.csv, .combat.csv, .runout.csv and
// .manifest.json sidecars. Branch sampling is K decisions per decision type.
void vwinRefreshGen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                    long long seedOffset, const std::string &teacherPath,
                    int samplesPerType, int parityPercent = 100,
                    int diagMaxBranches = -1, const std::string &diagMarkerPath = {});

// Counterfactual OOC label generation: per source seed up to STATES sampled
// card reward, campfire, shop or boss-relic decisions; every option is replayed
// K times with shared re-drawn hidden futures until the next boss fight ends
// (card rewards: the next CARD_BOSSES boss fights).
void oocCounterfactualPilotGen(int nSeeds, const std::string &outPrefix,
                               long long seedOffset, const std::string &teacherPath,
                               int futures, int statesPerSeed = 1, int cardRewardBosses = 1,
                               int generation = 1, const std::string &typeList = {},
                               const std::string &targetPath = {}, int futureStart = 0, int asc = 0);
// Combat-strength card probe: replays the ooccfpilotgen GEN=2 source runs to
// their sampled card rewards and writes CTM expectations per option and act
// encounter. Research only; changes no gameplay.
void cardStrengthProbe(int nSeeds, const std::string &outPrefix, long long seedOffset,
                       const std::string &teacherPath, int asc, int silverReps = 0, bool nextAct = false);
namespace one_combat {
void resampleCounterfactualFuture(GameContext &gc, std::mt19937_64 &rng);
}

// Bounded #347 Stage 1 replay on the fixed 128-seed #334 pilot cohort.
void bossHeadroom347Gen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                        long long seedOffset, const std::string &teacherPath);
// #347 boss-entry budget rescue pilot: one selected #417 source per process
// (reconstruct, capture the boss entry, control parity, 4 planner seeds at
// flat exact 10k and 40k). Returns 0 when every validity check passes.
int bossRescue347(int nEntries, const std::string &selectionPath, const std::string &stateId,
                  const std::string &outPrefix);
int bossRescue347SelfTest(int nSeeds, std::uint64_t seed, int sims);
// #400 Stage 1: every fight of each source trajectory replayed under a fixed
// grid of Silver search constants (control must reproduce the source fight).
void silverParamScreen400Gen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                             long long seedOffset, const std::string &teacherPath);
const std::vector<std::pair<std::string, search::NativeSilverSearchParams>> &silverParamScreen400Arms();
// Learned-stop replay A/B: every fight of each exact-10k source trajectory
// replayed under flat 10k (control), #199 adaptive, and learned stopping.
void silverStopReplayGen(int nSeeds, int sims, int asc, const std::string &outPrefix,
                         long long seedOffset, const std::string &teacherPath);
// CTM vs low-sim Silver forecasts on the same fight entries (ctmsilvergen).
void ctmSilverCompareGen(int nSeeds, int asc, const std::string &outPrefix, long long seedOffset,
                         const std::string &teacherPath, int replicates);
// Research-only corpus for a learned Silver prior / leaf value
// (apps/one_combat/silver_synth_gen.cpp). VARIANT is natural or perturbed.
void silverSynthGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                    const std::string &teacherPath, const std::string &variant);
// Silver AZ MLP loop self-play (silver_synth_gen.cpp): silversynthgen root and
// fight rows at SIMS with the STS_SILVER_ROOT_PRIOR MLP as tree prior.
void silverAzGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                 const std::string &variant, int treeMinVisits, int rootBonus);
// One encounter only (silverazfocusgen): REPLICATES recorded copies of its first
// fight per run at SIMS, other fights unrecorded at OTHER_SIMS; a boss is forced.
void silverAzFocusGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                      const std::string &encounter, int replicates, int otherSims, int treeMinVisits, int rootBonus);
// Paired online check of two MLP tree priors on one encounter (silverfocusevalgen, §469).
void silverFocusEvalGen(int nSeeds, int asc, const std::string &outPrefix, long long seedOffset,
                        const std::string &encounter, int replicates, int otherSims, int armSims, int treeMinVisits,
                        const std::string &priorA, const std::string &priorB);
// Offline harness for the silversynthgen corpus (apps/one_combat/silver_synth_replay.cpp):
// sparse combat features of its rows and child states, and root search replay.
void silverSynthFeatures(const std::string &outPrefix);
void silverSynthReplay(const std::string &namesPath = "");
// combat_policy_mlp_v1 logits of every root in a silversynthfeatures file
// (Python parity check) plus per-root timing, optionally against a GBM prior.
void silverPolicyMlpCheck(const std::string &modelPath, const std::string &prefix, const std::string &outPath,
                          const std::string &gbmPath);
int vwinRefreshPolicySpec(const std::string &outputPath);
int vwinRefreshSelfTest();
int vwinRefreshCompoundSelfTest();
int vwinRefreshRewardTypeSelfTest();
int vwinRefreshContinuationSelfTest();
int vwinRefreshMatchAndKeepSelfTest();
int vwinRefreshDecisionSinkSelfTest();
int vwinRefreshFatalRunoutCountSelfTest(std::uint64_t seed, int sims);
int vwinVPathPolicyGuardSelfTest();
int vwinRefreshBranchParitySelfTest(std::uint64_t seed, int sims, int asc);

int combatTransitionFixture(const std::string &outfile,
                                   const std::string &manifestPath);

void combatTransitionGen(int nSeeds, int sims, int asc,
                                const std::string &outfile, long long seedOffset,
                                const std::string &teacherPath,
                                bool allowStaleProvenance = false,
                                const std::string &forcedSetup = "");

void activeLizardCombatTransitionGen(int nSeeds, int sims, int asc,
                                     const std::string &outfile, long long seedOffset,
                                     const std::string &teacherPath,
                                     const std::string &baselineSha,
                                     const std::string &collectorSha);

void activeLizardPairTransitionGen(int nPairs, int sims, int asc,
                                   const std::string &outfile,
                                   const std::string &targetPath,
                                   const std::string &teacherPath,
                                   const std::string &baselineSha,
                                   const std::string &collectorSha);

int activeLizardTransitionSelfTest();

void counterfactualSurrogateAuditGen(int nSeeds,int sims,int asc,const std::string&outfile,
                                            std::uint64_t seedOffset,const std::string&teacherPath);

void evalCardRewardPolicy(GameContext &gc, bool allowSkip = true);

OocCounterfactualResult evaluateStrategicBranch(
    GameContext gc, std::uint64_t branchSeed, const PathHistory &path);

extern bool g_actFightProbeAllOoc;
extern std::vector<int> g_actFightProbeCheckpointSims;
extern bool g_actFightProbeDraft;
extern bool g_actFightProbeEncounterNN;
extern double g_actFightProbeFloorDecay;
extern int g_actFightProbeFutures;
extern double g_actFightProbeMargin;
extern int g_actFightProbeMaxCheckpoints;
extern bool g_actFightProbePredict;
extern search::CombatValueNet g_actFightProbePredictNet;
extern double g_actFightProbePredictWinThreshold;
extern int g_actFightProbeSims;
extern double g_actFightProbeTermWin;
extern int g_bossDraft;
extern int g_bossDraftFutures;
extern int g_bossDraftN;
extern int g_bossDraftSims;
extern bool g_cardAction;
extern bool g_cardNN;
extern double g_cardNNSkip;
extern double g_cardNNW;
extern bool g_oocShopBeam;
extern int g_oocShopBeamBudget;
extern int g_oocShopBeamDepth;
extern int g_oocShopBeamWidth;
extern int g_oocStrategicTok;
extern std::atomic<int> g_trainingHealthFailures;
extern std::atomic<int> g_trainingInvalidBranches;
extern std::atomic<int> g_trainingInvalidRuns;

std::string joinLegalActions(const std::vector<search::GameAction> &actions,
                                    const GameContext &gc);

void oocBudgetEvaluate(const std::string &manifestFile,
                              const std::string &outFile,
                              const std::vector<int> &schedule,
                              int futures, int futureStart,
                              const std::string &side,
                              const std::string &specFile,
                              int shardIndex, int shardCount,
                              int workIndex, int workCount);

void oocFactorEvaluate(const std::string &manifestFile,
                              const std::string &outFile, int referenceSims,
                              int futures, int futureStart, int expectedDecisions,
                              bool marginalTradeoff = false,
                              bool boundedK3 = false,
                              bool semanticFullRun = false);

int oocPolicyParitySelfTest(std::uint64_t seed, int sims, int asc);

void stepFrozenV4Ooc(GameContext &gc, search::ScumSearchAgent2 &agent);

int teacherSchemaCompatibilitySelfTest();
int learnedStopTeacherSelfTest();
// The default models are the production stack; a research candidate passes its own pair.
int ctmScoreRows(const std::string &inPath, const std::string &outPath,
                 const std::string &fastModel = "selfplay/models/combat_transition_deepsets_pathb_r2_lizard_ritual_refit.native",
                 const std::string &standardModel = "selfplay/models/combat_transition_near_full_escape_pathb_r2_ritual_refit.native",
                 bool activeLizard = true);
int ctmScoreRowsSelfTest();
int ctmEscapeFeatures(const std::string &inPath, const std::string &model, const std::string &outPrefix);
int ctmLizardFeatures(const std::string &inPath, const std::string &fastModel,
                      const std::string &standardModel, const std::string &outPath);

void wholeCombatGen(int nSeeds,int sims,int asc,const std::string&outfile,long long seedOffset,const std::string&teacherPath);

void writeTrainingProvenance(const std::string &output, const char *mode,
                                    int requested, int completed, int invalid,
                                    int healthFailures, long long rows,
                                    long long seedOffset, int sims, int asc,
                                    double epsilon = -1.0);

// Successor-state fingerprint used to detect which legal action the policy
// actually executed. All fields are ints; two actions with identical
// fingerprints are indistinguishable at this decision.
struct StratFingerprint {
    int screen, act, floor, hp, maxHp, gold;
    int keys[3], potionCount, potions[5];
    int deckSize, relicCount;
    long long deckSum, deckUpSum, deckHash;   // deck-content digest (non-last cards)
    long long relicSum, relicHash;            // relic-identity digest
    long long selSum, selHash;                // info.haveSelectedCards digest (multi-select picks)
    int bottledLast;                          // last bottled card id (-1)
    int goldRew, cardRew, relicRew, potionRew;
    int emeraldKey, sapphireKey, mapX, mapY, selectSize;

    bool operator==(const StratFingerprint &o) const {
        if (screen != o.screen || act != o.act || floor != o.floor || hp != o.hp
            || maxHp != o.maxHp || gold != o.gold || potionCount != o.potionCount
            || deckSize != o.deckSize || relicCount != o.relicCount
            || deckSum != o.deckSum || deckUpSum != o.deckUpSum || deckHash != o.deckHash
            || relicSum != o.relicSum || relicHash != o.relicHash
            || selSum != o.selSum || selHash != o.selHash
            || bottledLast != o.bottledLast || goldRew != o.goldRew || cardRew != o.cardRew
            || relicRew != o.relicRew || potionRew != o.potionRew
            || emeraldKey != o.emeraldKey || sapphireKey != o.sapphireKey
            || mapX != o.mapX || mapY != o.mapY || selectSize != o.selectSize)
            return false;
        for (int i = 0; i < 3; ++i) if (keys[i] != o.keys[i]) return false;
        for (int i = 0; i < 5; ++i) if (potions[i] != o.potions[i]) return false;
        return true;
    }
};

extern int g_strategicBranchFights;
extern int g_strategicBranchFutures;
extern int g_strategicBranchFutureOffset;
extern bool g_strategicBranchReseed;
extern std::vector<int> g_strategicBranchSims;
extern bool g_strategicSampleAll;
extern int g_strategicSamplesPerRun;

int numThreads();

StratFingerprint stratFingerprint(const GameContext &gc);

void strategicGen(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0);

void strategicGen2(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0);

std::string strategicHeader();

// potionpriceprobe (research): paired-continuation resource prices.
void potionPriceProbe(int nSeeds, std::uint64_t seedStart, int sims, int asc,
                      const std::string &outFile, int statesPerRun, int fightsAhead,
                      int hpDelta);
void strategicMargGen(int nSeeds, int outerSims,
                             int H, int maxPerRun, const std::string &outFile,
                             long long seedOffset);

extern double g_dgTemp;

struct EncounterOption {
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
};

std::vector<EncounterOption> possibleEncounterOptions(const GameContext &gc);

int sampleCardSoftmax(const std::vector<double> &marg, double temp, double uniformEps,
                             std::default_random_engine &ex);

std::vector<double> vQueryMarginals(GameContext &gc, int rIdx);

void dataGen2(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                     long long seedOffset = 0, const std::string &restOut = "",
                     int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                     const std::string &cardOut = "", int cardCfSims = 0,
                     int cardCfFights = 3, int cardCfFutures = 1, int cardCfStride = 1,
                     int cardCfMaxPerRun = 0, std::uint64_t cardCfFutureSalt = 0,
                     int cardCfAdaptiveMaxFutures = 0, double cardCfAdaptiveGap = 5.0);

void e2cGen(int nSeeds, int sims, int asc, const std::string &outfile,
                   long long seedOffset = 0);

void oocNextCombatGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                             std::uint64_t seedOffset, int branchSims, int futures);

void pathCounterfactualGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                                  std::uint64_t seedOffset, int branchSims, int futures,
                                  std::uint64_t futureSalt = 0);
