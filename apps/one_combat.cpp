// one_combat.cpp -- integration driver for full-run evaluation, data generation,
// and focused search/model diagnostics.

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
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatPVNet.h"
#include "sim/search/CombatCpsiNet.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/S3RejuvenationProbe.h"
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
#include "one_combat/e2c_capture.h"
#include "one_combat/run_features.h"
#include "one_combat/fight_replay.h"
#include "one_combat/search_diagnostics.h"
#include "one_combat/vnet_query_log.h"
#include "one_combat/particle_diagnostics.h"
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

OocCheckpointNet g_oocCheckpointNet;
OocStrategicNet g_oocStrategicNet;
OocStrategicTokNet g_oocStrategicTokNet;

// Legacy driver callers (strategic datagen and the retained shop beam) keep
// the old unqualified spelling while the implementations live in ooc_policy.
void strategicCands(const sts::GameContext &gc, const sts::search::GameAction &a,
                    int &actionType, int &c1, int &c2, int &c3,
                    int &cand1, int &cand2, int &cand3) {
    one_combat::strategicCands(gc, a, actionType, c1, c2, c3, cand1, cand2, cand3);
}
void tokEntity(const sts::GameContext &gc, const sts::search::GameAction &a,
               int &entType, int &entId, float &goldGePrice) {
    one_combat::tokEntity(gc, a, entType, entId, goldGePrice);
}

extern bool g_collectKeys;              // env STS_COLLECT_KEYS=1: collect act-4 keys
static std::vector<std::string> g_mainArgv;
static std::string g_mainBinaryPath;
// Resolved only after successful loading, so E3a provenance does not confuse
// an unset/failed environment request with the policy actually exercised.
static std::string g_effectiveVNetPath;
static std::string g_effectivePolicyPath;
static std::string g_effectiveOocStrategicPath;
static std::string g_effectiveOocStrategicTokPath;

static thread_local int t_trainingHealthFailures = 0;
static thread_local int t_trainingBranchHealthFailures = 0;
static thread_local bool t_trainingRunActive = false;
static std::atomic<int> g_trainingInvalidRuns{0};
static std::atomic<int> g_trainingInvalidBranches{0};
static std::atomic<int> g_trainingHealthFailures{0};

void trainingRunStart() {
    t_trainingHealthFailures = sts::search::g_simHealthFailureCount;
    t_trainingBranchHealthFailures = 0;
    t_trainingRunActive = true;
}

static void trainingCampaignStart() {
    g_trainingInvalidRuns = 0;
    g_trainingInvalidBranches = 0;
    g_trainingHealthFailures = 0;
}

bool trainingRunValid(bool outcomeDecided) {
    const int after = sts::search::g_simHealthFailureCount;
    const bool valid = sts::search::isValidTrainingTerminal(
        outcomeDecided, t_trainingHealthFailures,
        after - t_trainingBranchHealthFailures);
    if (!valid) {
        ++g_trainingInvalidRuns;
        g_trainingHealthFailures += std::max(0, after - t_trainingHealthFailures
                                              - t_trainingBranchHealthFailures);
    }
    return valid;
}

static std::string jsonEscape(const std::string &value) {
    std::string out;
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) { char buf[7]; std::snprintf(buf, sizeof(buf), "\\u%04x", c); out += buf; }
                else out += (char)c;
        }
    }
    return out;
}

static std::string trainingGitValue(const char *command) {
    std::string value;
    FILE *pipe = popen(command, "r");
    if (!pipe) return value;
    char buf[256];
    if (std::fgets(buf, sizeof(buf), pipe)) value = buf;
    pclose(pipe);
    while (!value.empty() && (value.back() == '\n' || value.back() == '\r')) value.pop_back();
    return value;
}

static std::string trainingExecutableGitSha() {
    const char *declared = std::getenv("STS_EXECUTABLE_GIT_SHA");
    if (declared && *declared) {
        const std::string sha(declared);
        const bool valid = sha.size() == 40 && std::all_of(sha.begin(), sha.end(), [](unsigned char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        });
        if (!valid) throw std::runtime_error("invalid STS_EXECUTABLE_GIT_SHA");
        return sha;
    }
    return trainingGitValue("git rev-parse HEAD");
}

static std::string fileSha256(const std::string &path) {
    // Model paths are operator-provided and may contain spaces.  Quote for the
    // repository's POSIX execution environments; a missing utility/file is
    // represented explicitly as an empty provenance value rather than guessed.
    std::string safe;
    for (char c : path) { if (c == '\'') safe += "'\\\"'\\\"'"; else safe += c; }
    const std::string line = trainingGitValue(("sha256sum '" + safe + "' 2>/dev/null").c_str());
    const size_t cut = line.find_first_of(" \t");
    return cut == std::string::npos ? line : line.substr(0, cut);
}

static void writeTrainingProvenance(const std::string &output, const char *mode,
                                    int requested, int completed, int invalid,
                                    int healthFailures, long long rows,
                                    long long seedOffset, int sims, int asc,
                                    double epsilon = -1.0) {
    std::ofstream p(output + ".provenance.json");
    if (!p) return;
    const char *envs[] = {"STS_FAIR", "STS_SEARCHER3", "STS_S3_PARTICLES",
                          "STS_S3_BELIEF", "STS_S3_CHAIN", "STS_REUSE_MAX_SEARCHES",
                          "STS_S3_PERSIST_FILTERED_BELIEF",
                          "STS_S3_REJUV_SHADOW", "STS_S3_REJUV_TRIGGER",
                          "STS_S3_REJUV_PROPOSALS", "STS_S3_REJUV_SHADOW_FILE",
                           "STS_S3_AI_REJUV_LIVE", "STS_S3_AI_REJUV_LIVE_FILE",
                          "STS_S3_RNG_EXPOSURE_DIAG", "STS_S3_RNG_EXPOSURE_DIAG_FILE",
                          "STS_REUSE_STATS_MODE", "STS_REUSE_ALWAYS_Q", "STS_S3_ALWAYS_Q", "STS_REUSE_DIAG",
                          "STS_S3_GATE_TIMING_DIAG", "STS_S3_GATE_TIMING_DIAG_FILE",
                          "STS_REUSE_OBS_STABLE", "STS_REUSE_RECONCILE_ROOT",
                          "STS_REUSE_CARRY_DIAG", "STS_REUSE_CPU_DIAG",
                          "STS_REUSE_CPU_DIAG_FILE", "STS_LIVE_VALID", "STS_STOP_AFTER_ACT",
                          "STS_S3_STRATEGY_FUSION_DIAG", "STS_S3_STRATEGY_FUSION_DIAG_FILE",
                          "STS_S3_STRATEGY_FUSION_DIAG_PARTICLES",
                          "STS_S3_STRATEGY_FUSION_DIAG_MAX_TRANSITIONS",
                          "STS_S3_STRATEGY_FUSION_DIAG_MIN_CHILD_VISITS",
                          "STS_S3_STRATEGY_FUSION_DIAG_FRESH_SIMS",
                          "STS_S3_STRATEGY_FUSION_DIAG_REF_SIMS",
                          "STS_FORCED_MOVE",
                          "STS_VNET", "STS_VNET_ALPHA", "STS_OOC_STRATEGIC_TOK_NN",
                          "STS_OOC_STRATEGIC_MARGIN", "STS_OOC_STRATEGIC_CARD",
                          "STS_OOC_STRATEGIC_REST", "STS_OOC_STRATEGIC_EVENT",
                          "STS_OOC_STRATEGIC_SHOP", "STS_OOC_STRATEGIC_TREASURE",
                          "STS_OOC_STRATEGIC_BOSS_RELIC", "STS_COLLECT_KEYS",
                          "STRATEGIC_SAMPLE_ALL", "STRATEGIC_SAMPLES_PER_RUN",
                          "STRATEGIC_BRANCH_FIGHTS", "STRATEGIC_BRANCH_SIMS",
                          "STRATEGIC_BRANCH_FUTURES"};
    p << "{\n  \"dataset_path\": \"" << jsonEscape(output) << "\",\n"
      << "  \"timestamp_utc\": \"" << jsonEscape(trainingGitValue("date -u +%Y-%m-%dT%H:%M:%SZ")) << "\",\n"
      << "  \"git_sha\": \"" << jsonEscape(trainingExecutableGitSha()) << "\",\n"
      << "  \"git_dirty\": " << (trainingGitValue("git status --porcelain --untracked-files=all") != "" ? "true" : "false") << ",\n"
      << "  \"generator\": \"" << jsonEscape(mode) << "\",\n"
      << "  \"argv\": [";
    for (size_t i = 0; i < g_mainArgv.size(); ++i) {
        if (i) p << ',';
        p << "\"" << jsonEscape(g_mainArgv[i]) << "\"";
    }
    p << "],\n  \"command\": \"one_combat";
    for (const auto &arg : g_mainArgv) {
        p << ' ' << jsonEscape(arg);
    }
    p << "\",\n"
      << "  \"seed_offset\": " << seedOffset << ",\n"
      << "  \"requested_seeds\": " << requested << ",\n"
      << "  \"completed_seeds\": " << completed << ",\n"
      << "  \"invalid_or_quarantined_seeds\": " << invalid << ",\n"
      << "  \"invalid_or_quarantined_branches\": " << g_trainingInvalidBranches.load() << ",\n"
      << "  \"simulator_health_hard_failures\": " << healthFailures << ",\n"
      << "  \"rows_written\": " << rows << ",\n"
      << "  \"simulations\": " << sims << ",\n"
      << "  \"ascension\": " << asc << ",\n"
      << "  \"epsilon\": " << epsilon << ",\n"
      << "  \"models\": {\n    \"STS_VNET\": ";
    if (const char *v = std::getenv("STS_VNET")) p << "\"" << jsonEscape(v) << "\""; else p << "null";
    p << ",\n    \"STS_OOC_STRATEGIC_TOK_NN\": ";
    if (const char *v = std::getenv("STS_OOC_STRATEGIC_TOK_NN")) p << "\"" << jsonEscape(v) << "\""; else p << "null";
    p << "\n  },\n  \"environment\": {";
    for (int i = 0; i < (int)(sizeof(envs) / sizeof(envs[0])); ++i) {
        if (i) p << ',';
        const char *value = std::getenv(envs[i]);
        p << "\n    \"" << envs[i] << "\": ";
        if (value) p << '"' << jsonEscape(value) << '"'; else p << "null";
    }
    p << "\n  }\n}\n";
}

// ---------------------------------------------------------------------------
// Live progress line for long parallel benches. Threads call tick() as each run
// finishes; it prints an in-place (\r) status to stderr -- completed/total,
// running win%/floor/HP, elapsed + ETA -- throttled to ~4 Hz. Only draws when
// stderr is a TTY, so redirected A/B logs stay clean. Call done() at the end.
struct BenchProgress {
    int total; const char *label;
    std::atomic<int> n{0}, wins{0};
    std::atomic<long long> floor{0}, hp{0};
    std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
    std::atomic<double> lastDraw{-1.0};
    bool tty = isatty(fileno(stderr));
    BenchProgress(int total_, const char *label_) : total(total_), label(label_) {}
    void tick(bool won, int fl, int h) {
        int d = ++n; wins += won; floor += fl; hp += h;
        if (!tty) return;
        double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        double last = lastDraw.load();
        if (d != total && (el - last) < 0.25) return;         // throttle
        if (!lastDraw.compare_exchange_strong(last, el)) return;
        double eta = d ? el / d * (total - d) : 0;
        std::fprintf(stderr, "\r  %s [%d/%d] %.0f%%  win%%=%.1f floor=%.1f hp=%.1f  %.0fs eta %.0fs      ",
                     label, d, total, 100.0 * d / total,
                     100.0 * wins / d, (double)floor / d, (double)hp / d, el, eta);
        std::fflush(stderr);
    }
    void done() { if (tty) std::fprintf(stderr, "\r\033[K"); }  // clear the line
};

static int numThreads() {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

using namespace sts;

// ---------------------------------------------------------------------------
// Enumerate legal actions in the current player-choice state
// (mirrors BattleScumSearcher2::enumerateActionsForNode; potions omitted).
// ---------------------------------------------------------------------------
static std::vector<search::Action> legalActions(const BattleContext &bc) {
    using search::Action;
    using search::ActionType;
    std::vector<Action> actions;

    if (bc.inputState == InputState::PLAYER_NORMAL) {
        if (bc.isCardPlayAllowed()) {
            for (int h = 0; h < bc.cards.cardsInHand; ++h) {
                const auto &c = bc.cards.hand[h];
                if (!c.canUseOnAnyTarget(bc)) continue;
                if (c.requiresTarget()) {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            actions.push_back(Action(ActionType::CARD, h, t));
                } else {
                    actions.push_back(Action(ActionType::CARD, h));
                }
            }
        }
        actions.push_back(Action(ActionType::END_TURN));
    } else if (bc.inputState == InputState::CARD_SELECT) {
        actions = Action::enumerateCardSelectActions(bc);
    }
    return actions;
}

// ---------------------------------------------------------------------------
// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via its out-of-combat policy).
// ---------------------------------------------------------------------------
static RunResult runFullRun(std::uint64_t seed, int sims, int ascension, bool verbose) {
    GameContext gc(CharacterClass::IRONCLAD, seed, ascension);

    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;    // MCTS sims per in-combat decision
    agent.printLogs = verbose;           // dump GameContext at each out-of-combat step
    agent.rng = std::default_random_engine(seed); // reproducible out-of-combat choices

    auto t0 = std::chrono::steady_clock::now();
    agent.playout(gc);                   // runs until gc.outcome is decided
    auto t1 = std::chrono::steady_clock::now();

    return { gc.outcome == GameOutcome::PLAYER_VICTORY,
             gc.floorNum, gc.act, gc.curHp, gc.maxHp,
             std::chrono::duration<double>(t1 - t0).count() };
}

// ---------------------------------------------------------------------------
// LOOKAHEAD CARD-REWARD POLICY: for each choice (each card + skip), copy the
// run, apply the choice, play the next N fights with a cheap agent, and keep
// the choice that leaves us best off. Common Random Numbers come for free: the
// copied GameContext carries all game RNG streams, so the only difference
// between branches is the deck. (Like the combat searcher, this peeks at the
// run's fixed future RNG.)
// ---------------------------------------------------------------------------
static double scoreLookaheadState(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -1e6 + gc.floorNum;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return  1e6 + gc.curHp;
    return gc.curHp * 100.0 + gc.floorNum;   // survived the N fights: HP is the discriminator
}

// Bounded, regression-friendly score (HP scale) for causal labels -- unlike
// scoreLookaheadState's +/-1e6 outcome bonuses which would swamp any regression.
static double labelScore(const GameContext &gc) {
    if (gc.outcome == GameOutcome::PLAYER_LOSS)    return -100.0;
    if (gc.outcome == GameOutcome::PLAYER_VICTORY) return gc.maxHp + 200.0;
    return gc.curHp;   // survived the N fights: remaining HP is the signal
}

static double rolloutChoice(const GameContext &base, int rIdx, int cardIdx,
                            int N, int innerSims, std::uint64_t seed, bool useLabelScore = false) {
    GameContext gc = base;                              // shares seeded RNG streams (CRN)
    gc.map = std::make_shared<Map>(*base.map);          // isolate map from the real run
    search::ScumSearchAgent2 inner;
    inner.simulationCountBase = innerSims;
    inner.rng = std::default_random_engine(seed);

    search::GameAction(search::GameAction::RewardsActionType::CARD, rIdx, cardIdx).execute(gc);

    int fights = 0;
    while (gc.outcome == GameOutcome::UNDECIDED && fights < N) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            inner.playoutBattle(bc);
            bc.exitBattle(gc);
            ++fights;
        } else {
            inner.stepOutOfCombatPolicy(gc);
        }
    }
    return useLabelScore ? labelScore(gc) : scoreLookaheadState(gc);
}

// ---------------------------------------------------------------------------
// STATE-AWARE CARD VALUE FUNCTION: score a candidate card given the full run
// state (deck composition, relics, HP, act, ascension, upcoming fights). This
// generalises the flat getObtainWeight table -- picking among 3 cards is then
// just argmax(value), and "skip" is value-vs-a-state-dependent-bar.
// ---------------------------------------------------------------------------

// Rows until the nearest reachable ELITE from the current map position (99 if none
// remain on any reachable path). Used to gauge how soon a hard fight arrives.
static int rowsToNextElite(const GameContext &gc) {
    const Map &map = *gc.map;
    std::array<bool, 7> reach{};
    int startRow;
    if (gc.curMapNodeY < 0) {
        startRow = 0;
        for (const MapNode &n : map.nodes[0]) if (n.edgeCount > 0) reach[n.x] = true;
    } else {
        startRow = gc.curMapNodeY + 1;
        if (startRow > 14) return 99;
        const MapNode &cur = map.getNode(gc.curMapNodeX, gc.curMapNodeY);
        for (int i = 0; i < cur.edgeCount; ++i) reach[cur.edges[i]] = true;
    }
    const int base = std::max(gc.curMapNodeY, 0);
    for (int y = startRow; y <= 14; ++y) {
        std::array<bool, 7> nxt{};
        bool eliteHere = false;
        for (int x = 0; x < 7; ++x) if (reach[x]) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::ELITE) eliteHere = true;
            for (int i = 0; i < n.edgeCount; ++i) nxt[n.edges[i]] = true;
        }
        if (eliteHere) return y - base;
        reach = nxt;
    }
    return 99;
}

static double evalCardValue(const GameContext &gc, const Card &c) {
    const CardType t = c.getType();
    if (t == CardType::CURSE || t == CardType::STATUS) return -1e9;   // never draft these

    double v = (double)search::Expert::getObtainWeight(c.getId(), c.isUpgraded());  // base prior

    const int act = gc.act;
    const int asc = gc.ascension;
    const double hpFrac = gc.maxHp > 0 ? (double)gc.curHp / gc.maxHp : 1.0;

    // deck composition (ignore curses/status)
    int nAtk = 0, nSkill = 0, nPow = 0, nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt == CardType::CURSE || dt == CardType::STATUS) continue;
        ++nReal;
        if (dt == CardType::ATTACK) ++nAtk;
        else if (dt == CardType::SKILL) ++nSkill;
        else if (dt == CardType::POWER) ++nPow;
    }
    const double atkFrac = nReal > 0 ? (double)nAtk / nReal : 0.5;

    // (1) curve: aim ~48% attacks; reward the under-represented role.
    const double targetAtk = 0.48;
    if (t == CardType::ATTACK)     v += 25.0 * (targetAtk - atkFrac);
    else if (t == CardType::SKILL) v += 25.0 * (atkFrac - targetAtk);

    // (2) scaling / win-condition: powers scale and you need one by act 2-3;
    //     diminishing once the deck already has a couple.
    if (t == CardType::POWER) {
        v += 8.0 * act;
        if (nPow >= 3) v -= 10.0 * (nPow - 2);
    }

    // (3) raw impact (proxy: base damage of attacks).
    v += 0.4 * c.getBaseDamage();

    // (4) defensive lean when hurt or at high ascension.
    if ((hpFrac < 0.5 || asc >= 15) && t == CardType::SKILL) v += 8.0;

    // (5) upcoming-fight pressure: value power spikes / big hits before a wall.
    const int d = std::min(rowsToNextElite(gc), 15 - gc.curMapNodeY);
    if (d <= 2) {
        if (t == CardType::POWER) v += 6.0;
        v += 0.2 * c.getBaseDamage();
    }
    return v;
}

// Value bar below which we skip: rises with deck size and ascension (avoid
// diluting a big / high-ascension deck), and drops in act 1 (you need cards).
static double evalSkipBar(const GameContext &gc) {
    int nReal = 0;
    for (const auto &d : gc.deck.cards) {
        const CardType dt = d.getType();
        if (dt != CardType::CURSE && dt != CardType::STATUS) ++nReal;
    }
    double bar = 8.0 + 0.7 * nReal + 1.0 * gc.ascension;
    if (gc.act == 1) bar *= 0.5;
    return bar;
}

static void evalCardRewardPolicy(GameContext &gc, bool allowSkip = true) {
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int n = r.cardRewards[rIdx].size();
        int bestIdx = 0; double bestV = -1e18;
        for (int i = 0; i < n; ++i) {
            const double val = evalCardValue(gc, r.cardRewards[rIdx][i]);
            if (val > bestV) { bestV = val; bestIdx = i; }
        }
        const bool skip = allowSkip && (bestV < evalSkipBar(gc));
        search::GameAction(RT::CARD, rIdx, skip ? 5 : bestIdx).execute(gc);
    }
}

static std::string featureRow(const GameContext &gc);      // defined below
static std::string deckCountsCsv(const GameContext &gc);   // defined below

// Current run's path history, so vFeatCsv() can emit pv* features (nullptr = none).
thread_local const PathHistory *t_curPath = nullptr;
thread_local PathHistory t_emptyPath;    // pv* = 0 when no run path is set
std::string vFeatCsv(const GameContext &gc);                          // defined below

// ---------------------------------------------------------------------------
// DECK-AWARE V VIA PYTHON BRIDGE: card picks are rare (~13/run) so we query the
// exact trained GBM held in v_server.py over a TCP socket. Card value =
// V(deck+card) - V(deck); the server returns the chosen index (or 5 = skip).
// One persistent connection per thread.
// ---------------------------------------------------------------------------
static int g_vPort = 5555;
static thread_local int t_vSock = -1;

// A benchmark run must not inherit a persistent server session from a previous
// seed in the same worker.  The protocol is request/response, but closing at a
// run boundary gives repeated-seed checks a clean, independently handled server
// connection and avoids any accidental socket-buffer/session carry-over.
void vDisconnect() {
#ifndef _WIN32
    if (t_vSock >= 0) close(t_vSock);
#endif
    t_vSock = -1;
}
// Skip a card reward when the best candidate's marginal V(deck+card)-V(deck)
// (final-floor units) is below this. Default -0.5 (RICH V2): take a card unless it
// looks clearly diluting, skip only if marginal < -0.5. Re-swept @512 seeds asc0 on
// V2 -> best band -1.0..-0.25 (win 41-42%), peak -0.5=42.4% vs skip@0=38.7%; V2
// marginals read slightly pessimistic so a fuller deck wins. Positive thresholds
// still fall off a cliff. (Old deck-only V best was 0.0.) Override via STS_SKIP_THR.
double g_cardSkipThresh = -0.5;
// A/B: route card picks through the WIN model (P(win) marginal) instead of V_floor.
// Own skip scale (win-prob units, ~0..0.05) so g_cardSkipThresh (floor units) doesn't apply.
bool g_cardWin = false;          // env STS_CARD_WIN=1
double g_cardWinSkip = 0.0;      // env STS_CARD_WIN_SKIP: skip iff best P(win) marginal < this
bool g_shopWin = false;          // env STS_SHOP_WIN=1: score shop bundles by P(win) not V_floor
bool g_nativeOoc = false;
bool g_oocActionNN = false;          // env STS_OOC_ACTION_NN=1
double g_oocStrategicMargin = 1.0;   // env STS_OOC_STRATEGIC_MARGIN: one-ply gate in V units
// Per-screen one-ply gate overrides (env STS_OOC_STRATEGIC_MARGIN_*): default
// -1.0 = unset, i.e. fall back to g_oocStrategicMargin so behavior is unchanged.
double g_oocStrategicMarginCard = -1.0;      // STS_OOC_STRATEGIC_MARGIN_CARD
double g_oocStrategicMarginRest = -1.0;      // STS_OOC_STRATEGIC_MARGIN_REST (rest + upgrade target)
double g_oocStrategicMarginEvent = -1.0;     // STS_OOC_STRATEGIC_MARGIN_EVENT
double g_oocStrategicMarginShop = -1.0;      // STS_OOC_STRATEGIC_MARGIN_SHOP
double g_oocStrategicMarginTreasure = -1.0;  // STS_OOC_STRATEGIC_MARGIN_TREASURE
double g_oocStrategicMarginBossRelic = -1.0; // STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC
bool   g_oocStrategicQ = true;       // env STS_OOC_STRATEGIC_Q=0: score via V2 successor predictValue
bool   g_oocStrategicScorePolicy = false; // env STS_OOC_STRATEGIC_SCORE=policy: one-ply gates score with sigmoid(policy logit) (5.7.2)
bool   g_oocStrategicRest = false;   // env STS_OOC_STRATEGIC_REST=1: one-ply Q gate on campfires (5.5.2)
static bool   g_datagenGates = false;       // env STS_DATAGEN_GATES=1: combatgen/distgen OOC decisions route through the one-ply gate chain (§127)
bool   g_oocStrategicEvent = false;  // env STS_OOC_STRATEGIC_EVENT=1: one-ply Q gate on events (5.5.3)
bool   g_oocStrategicShop = false;    // env STS_OOC_STRATEGIC_SHOP=1: one-ply Q gate on shop buys (R6)
bool   g_oocStrategicTreasure = false; // env STS_OOC_STRATEGIC_TREASURE=1: one-ply Q gate on treasure (R6)
bool   g_oocStrategicBossRelic = false; // env STS_OOC_STRATEGIC_BOSS_RELIC=1: one-ply Q gate on boss relics (R6)
bool   g_oocStrategicMap = false;     // env STS_OOC_STRATEGIC_MAP=1: one-ply Q gate on map routes (M1)
double g_oocStrategicMarginMap = -1.0; // env STS_OOC_STRATEGIC_MARGIN_MAP (default -1.0 = fall back to global)
// Wave B regret gate (ooc-qwin-continuation.md Step 5): decision rule
// Qmax(s) − Q(a_heur) > ε for every one-ply gate and the M2 route search.
// a_heur is the deployed-default heuristic action, identified by the
// datagen-proven successor-fingerprint match; when it cannot be identified
// (RNG-tied divergence) the policy falls back to the margin rule.
bool   g_oocStrategicGateRegret = false; // env STS_OOC_STRATEGIC_GATE=regret
double g_oocStrategicGateEps = 0.03;     // env STS_OOC_STRATEGIC_GATE_EPS: regret threshold ε
// M2 short-horizon map route search (plan 5.6.2): C_psi combat surrogate +
// strategic V head at the leaf. Hidden-info clean: encounters/bosses are
// sampled from the act's visible pool, never the true future.
bool   g_oocMapRoute = false;         // env STS_OOC_MAP_ROUTE=1
int    g_oocMapRouteHorizon = 3;      // env STS_OOC_MAP_ROUTE_HORIZON (clamped 2..5)
search::CombatCpsiNet g_cpsiNet;      // env STS_CPSI_NN=<path>: combat outcome surrogate
static int    g_oocStrategicTok = 0;        // env STS_OOC_STRATEGIC_TOK_NN: V4 token net loaded
bool   g_oocStrategicTokCheck = false; // env STS_OOC_STRATEGIC_TOK_CHECK=1: first-decision glob parity hook
std::string g_oocStrategicTracePath;
thread_local std::string t_oocStrategicTraceRows;
thread_local int t_oocStrategicTraceDecision = 0;
thread_local bool t_tokCheckPending = false;  // armed per run; consumed by the first gated decision
thread_local bool t_shopV = false;            // runFullRunOOC's shopV param, for the regret SHOP probe
// Forced relic at run start (benchmark): STS_FORCE_RELIC=<NAME> grants the
// relic (counter data 0) and removes it from the draw pools so the run cannot
// naturally roll a duplicate. Enables paired A/B with the relic guaranteed.
RelicId g_forceRelic = RelicId::INVALID;
// B1 shop beam search (ooc-next-wave-contracts.md §2): multi-step lookahead over
// deterministic shop purchases, replacing the one-ply shop gate when enabled.
static bool   g_oocShopBeam = false;        // env STS_OOC_SHOP_BEAM=1
static int    g_oocShopBeamWidth = 32;      // env STS_OOC_SHOP_BEAM_WIDTH (clamped 4..256)
static int    g_oocShopBeamDepth = 0;       // env STS_OOC_SHOP_BEAM_DEPTH (0 = until leave / no affordable actions)
static int    g_oocShopBeamBudget = 4096;   // env STS_OOC_SHOP_BEAM_BUDGET: max expanded nodes per shop decision
int nativeFloorCardPick(GameContext &, int);
double nativeFloorValue(GameContext &);
bool oocShopBeamPolicy(GameContext &);          // B1 multi-step shop beam search (§2)
struct StratFingerprint;                               // successor-state digest (defined below)
static StratFingerprint stratFingerprint(const GameContext &);
// Wave B regret decision: returns the index of the action to take (Q-max when
// Qmax − Q(a_heur) > eps, else a_heur), or -1 when a_heur is unidentifiable
// (caller falls back to the margin rule). Runs `heuristic` on a pre-state copy
// with a copied agent RNG stream and matches the successor fingerprint.
static int regretGateChoose(const GameContext &, const std::vector<search::GameAction> &,
                            const std::vector<double> &, double,
                            void (*)(GameContext &, search::ScumSearchAgent2 &),
                            const search::ScumSearchAgent2 &);
bool regretGateTail(GameContext &, const std::vector<search::GameAction> &,
                           const std::vector<double> &, int, double, double, double, double,
                           void (*)(GameContext &, search::ScumSearchAgent2 &),
                           const search::ScumSearchAgent2 &);
std::string nativeShopPlan(GameContext &);
static void resampleRemainingActEncounters(GameContext &, std::uint64_t);
// A/B: route card picks through the deck-set NN (P(win) marginal), optionally blended with
// the v_win GBM: marg = w*NN + (1-w)*GBM. Own skip scale (P(win) units).
static bool   g_cardNN     = false;     // env STS_CARD_NN=1
static double g_cardNNW    = 1.0;       // env STS_CARD_NN_W: blend weight on NN (1=pure NN)
static double g_cardNNSkip = 0.0;       // env STS_CARD_NN_SKIP: skip iff best P(win) marginal < this
// Direct paired action-value model (offered cards + skip), optionally with the
// full map graph. Unlike marginal value models, it learns its own skip action.
static bool   g_cardAction = false;     // env STS_CARD_ACTION=1 (CA server op)
// Datagen exploration: softmax temperature over card marginals (final-floor
// units; higher = more spread). The uniform-floor prob is datagen2's `epsilon`.
static double g_dgTemp = 2.0;   // env STS_DG_TEMP (swept: 1-2 good spread+quality, >=3 over-randomizes)
// Per-fight combat sim budget by difficulty (env STS_SIMS_NORMAL/ELITE/BOSS; <=0 or
// unset = use the run's base sims). Deaths cluster at elites/bosses, so we can search
// those deep and skimp on trivial hallway fights for the same win% at far less compute.
static int g_simsNormal = -1, g_simsElite = -1, g_simsBoss = -1;
// Dynamic per-fight budget via the C_psi no-peek combat outcome surrogate
// (STS_SIM_ADAPT=1 + STS_CPSI_NN, EXPERIMENTS.md §103): one forward pass at fight
// start predicts P(death) and E[hp/maxHp|win]; the budget multiplier rises with
// predicted danger. Learned tiering — unlike the static STS_SIMS_* room tiers it
// cannot misjudge difficulty (act-3 monsters ~ act-1 elites, §21). buildCpsiEntry
// uses only pre-combat state, so this is fair-play clean. Takes precedence over
// the static tiers when enabled.
static bool   g_simAdapt = false;       // env STS_SIM_ADAPT=1
static double g_simAdaptMinFrac = 0.4;  // env STS_SIM_ADAPT_MIN_FRAC: budget floor as a fraction of base
static double g_simAdaptMaxFrac = 2.0;  // env STS_SIM_ADAPT_MAX_FRAC: budget ceiling as a fraction of base
// Pick the sim budget for the fight in the current room (falls back to base).
int fightSims(const GameContext &gc, int base) {
    if (g_simAdapt && g_cpsiNet.loaded() && gc.info.encounter != MonsterEncounter::INVALID) {
        float scalar[search::kCpsiScalars], deck[search::kCpsiCards],
              relics[search::kCpsiRelics], potions[search::kCpsiPotions];
        search::buildCpsiEntry(gc, scalar, deck, relics, potions);
        search::CpsiOut r;
        g_cpsiNet.predict(scalar, deck, relics, potions, (int)gc.info.encounter, r);
        const double m = 0.5 + 1.0 * r.death + 1.0 * (1.0 - r.hp);  // danger = P(death) + expected HP loss
        const double frac = std::min(g_simAdaptMaxFrac, std::max(g_simAdaptMinFrac, m));
        return std::max(1, (int)std::llround(base * frac));
    }
    if (gc.curRoom == Room::BOSS || gc.curRoom == Room::BOSS_TREASURE) return g_simsBoss  > 0 ? g_simsBoss  : base;
    if (gc.curRoom == Room::ELITE)                                     return g_simsElite > 0 ? g_simsElite : base;
    return g_simsNormal > 0 ? g_simsNormal : base;   // MONSTER / event fights
}

// --- boss-aware drafting: for card picks near a hard fight, lean on a boss signal
// (either a rollout, or the boss-survival value model v_boss blended with v_rich).
// The gate is factored so the hard-fight set can later become DYNAMIC (learned from
// where we die); boss-only for now.
static int    g_bossDraft        = 0;      // STS_BOSS_DRAFT: rollout-based near-boss draft (experimental; hurt in A/B)
int    g_bossDraftRows    = 3;      // trigger when a hard fight is within this many map rows
static int    g_bossDraftN       = 4;      // rollout: fights to simulate forward
static int    g_bossDraftSims    = 150;    // rollout: inner combat sim budget
static int    g_bossDraftFutures = 2;      // rollout: sampled futures per candidate
int    g_bossV            = 0;      // STS_BOSS_V: blend v_boss marginal into near-boss server picks
double g_bossVW           = 0.5;    // STS_BOSS_V_W: blend weight on the boss model (0..1)

// Experimental full-act draft evaluator.  For the immediate card decision only,
// it samples the *possible remaining encounter queues* in the current act and
// plays every fight on the selected route through the boss.  Its utility is an
// expectation over survival and a nonlinear post-fight HP safety margin, with a
// modest floor-distance discount.  It intentionally makes no V/card-model query
// for the card being picked; the regular OOC policy is used only inside a sampled
// continuation to resolve later choices.
static bool   g_actFightProbeDraft = false; // STS_ACT_FIGHT_PROBE_DRAFT=1
static int    g_actFightProbeSims = 100;    // STS_ACT_FIGHT_PROBE_SIMS
static int    g_actFightProbeFutures = 4;   // STS_ACT_FIGHT_PROBE_FUTURES
static double g_actFightProbeFloorDecay = 0.985; // STS_ACT_FIGHT_PROBE_FLOOR_DECAY
// Optional inner-search base budgets by reached checkpoint, e.g. 400,200,100.
// The live run's combat budget is unaffected; room-tier overrides still take
// precedence through fightSims().
static std::vector<int> g_actFightProbeCheckpointSims; // STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS
// -1 scores every remaining fight in the current act; a positive value scores only the
// next N combat checkpoints.  This is a horizon in fights, not map nodes, so
// routes with shops/events are not given a structurally different objective.
static int    g_actFightProbeMaxCheckpoints = -1; // STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS
bool   g_actFightProbeTrace = false; // STS_ACT_FIGHT_PROBE_TRACE=1
// Parallelize the independent immediate-action × sampled-future branches of a
// single OOC decision.  Off by default so ordinary multi-seed benches retain
// their existing outer OpenMP scheduling.
static bool   g_actFightProbeParallelBranches = false; // STS_ACT_FIGHT_PROBE_PARALLEL=1
// Broader version used only for a deliberately expensive Act-1 experiment:
// evaluate every legal OOC action (map, rewards, events, shop, rest, selects),
// not just cards.  This is separate so the card-only oracle remains available.
static bool   g_actFightProbeAllOoc = false; // STS_ACT_FIGHT_PROBE_ALL_OOC=1
// Score and advance checkpoint fights with the entity combat model instead of
// running MCTS.  This is deliberately separate from STS_VNET: the latter is a
// leaf evaluator inside real combat search, while this one supplies both heads
// needed for a virtual post-combat transition.
static bool   g_actFightProbePredict = false; // STS_ACT_FIGHT_PROBE_PREDICT=1
static bool   g_actFightProbeEncounterNN = false; // STS_ACT_FIGHT_PROBE_ENCOUNTER_NN=1
static double g_actFightProbePredictWinThreshold = 0.5;
static std::string g_actFightProbePredictNetPath = "selfplay/models/v_combat_entity_iter34.txt";
static search::CombatValueNet g_actFightProbePredictNet;
// Optional terminal pricing for the capped checkpoint objective: after the
// final scored checkpoint, price each option's resulting branch state with the
// native win model (P(run victory)) and add it to the utility, blended by this
// weight.  HP-only checkpoint safety misses resource compounding (gold, relics,
// deck) that the trunk simulation carries forward but never prices.
static double g_actFightProbeTermWin = 0.0; // STS_ACT_FIGHT_PROBE_TERM_WIN=alpha (0 = off)
// Margin gate: when > 0, the all-OOC oracle overrides a decision only if its
// best action's utility beats the runner-up by at least this margin; otherwise
// control falls through to the ordinary policy stack.  Greedy full-run oracle
// replacement is a recorded regression (EXPERIMENTS.md 66j/66m/67); the margin
// is the design-doc deployment contract for learned override layers.
static double g_actFightProbeMargin = 0.0; // STS_ACT_FIGHT_PROBE_MARGIN=m (0 = always fire)
int    g_stopAfterAct = 0;            // STS_STOP_AFTER_ACT=N, benchmark horizon
// Optional durable per-action teacher data for the all-OOC oracle.  The file
// is append-only because benchmark runs may be stopped and resumed.
static std::string g_actFightProbeLogPath;   // STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv
static std::ofstream g_actFightProbeLog;
static std::mutex g_actFightProbeLogMutex;
thread_local int t_actFightProbeDecisionIdx = 0;
thread_local int t_actFightProbeActionIdx = -1;
thread_local int t_actFightProbeFutureIdx = -1;

static int actFightProbeCheckpointSims(int defaultSims, int checkpointIdx) {
    if (checkpointIdx >= 0 && checkpointIdx < (int)g_actFightProbeCheckpointSims.size())
        return g_actFightProbeCheckpointSims[checkpointIdx];
    return defaultSims;
}

// --- strategicgen2 (Tier-B one-ply labels) knobs ---
// Per sampled decision, every legal action is branched from a pre-decision copy
// and continued with the deployed-default OOC policy through K=BRANCH_FIGHTS
// battles at STRATEGIC_BRANCH_SIMS sims each, then bootstrapped with the native
// floor/win trees. The same branch seed per decision gives common random
// numbers across actions; STRATEGIC_BRANCH_FUTURES averages over extra seeds.
static int g_strategicSamplesPerRun = 1;    // STRATEGIC_SAMPLES_PER_RUN: reservoir size
static bool g_strategicSampleAll = false;   // STRATEGIC_SAMPLE_ALL=1: label every decision
static int g_strategicBranchFights = 3;     // STRATEGIC_BRANCH_FIGHTS: battles per branch
static std::vector<int> g_strategicBranchSims = {150, 100, 50}; // STRATEGIC_BRANCH_SIMS per fight
static int g_strategicBranchFutures = 1;    // STRATEGIC_BRANCH_FUTURES: branch seeds per action

static std::string actFightProbeCheckpointSimsCsv() {
    std::ostringstream out;
    for (int i = 0; i < (int)g_actFightProbeCheckpointSims.size(); ++i) {
        if (i) out << ';';
        out << g_actFightProbeCheckpointSims[i];
    }
    return out.str();
}

// --- V-informed pathing: the next-fight features are a shared encounter QUEUE
// (route-independent at a decision), so V(state) is ~flat across immediate map
// children -> per-child V scoring gives no signal. Instead use V(state) as a
// deck-STRENGTH scalar (predicted final floor) to MODULATE the heuristic's
// aggression: a strong deck routes harder into elites/fights (farm relics while
// you can), a weak deck routes to rest/shop/event (recover). One V query/floor.
// Act boss floors (finalFloor at which each act's boss sits) — the deck-strength
// anchor: predFloor - bossFloor[act] = how comfortably you clear this act.
static int bossFloorForAct(int act) { return act <= 1 ? 17 : act == 2 ? 34 : 50; }

// Map rows until the next hard fight. Boss sits just past the last map row (14),
// so rows-to-boss = 14 - curMapNodeY. (Extend to fold in elites / learned high-death
// floors for the dynamic version.)
int rowsToHardFight(const GameContext &gc) {
    return 14 - std::max(gc.curMapNodeY, 0);
}

// --- potion-saving policy: the combat search is per-fight MYOPIC (optimizes THIS
// fight's end HP), so it spends potions on easy fights with no incentive to bank
// them for elites/bosses -- where we actually die. evaluateEndState already values
// a KEPT potion at g_potionKeepValue HP-equiv (drinking costs that much), so we make
// that value DYNAMIC per fight: high in easy fights when a hard fight is near (hoard),
// low in the hard fight itself (spend). Modulated by the potion DROP chance -- if we'll
// likely refill before the hard fight (high potionChance / White Beast Statue = 100%),
// there's less need to save the current one.
static int    g_potionSave    = 0;      // STS_POTION_SAVE=1: enable dynamic potion keep-value
static int    g_potionWindow  = 5;      // STS_POTION_WINDOW: only save when a hard fight is <= this many rows away
static double g_potionBonus   = 18.0;   // STS_POTION_BONUS: extra HP-equiv keep-value at max urgency
static double g_potionSpend   = 1.0;    // STS_POTION_SPEND: keep-value DURING an elite/boss (low = spend)
static double g_potionDesired = 2.5;    // STS_POTION_DESIRED: potions we'd like entering a hard fight
static const double kPotionBaseKeep = 4.0;   // the engine's original constant (neutral default)

// Per-fight potion keep-value (HP-equiv), set into search::g_potionKeepValue before combat.
double potionKeepValue(const GameContext &gc) {
    if (!g_potionSave) return kPotionBaseKeep;
    const Room r = gc.curRoom;
    if (r == Room::ELITE || r == Room::BOSS || r == Room::BOSS_TREASURE)
        return g_potionSpend;                       // the hard fight itself -> spend freely
    const int hardDist = std::min(rowsToNextElite(gc), rowsToHardFight(gc));  // rows to nearest elite/boss
    if (hardDist <= 0 || hardDist > g_potionWindow) return kPotionBaseKeep;   // nothing hard soon
    const double p = gc.hasRelic(RelicId::WHITE_BEAST_STATUE)
                       ? 1.0 : std::clamp((double)gc.potionChance / 100.0, 0.0, 1.0);
    const double expDrops  = hardDist * p;          // potions we'll likely gain before the hard fight
    const double scarcity  = std::clamp(1.0 - expDrops / g_potionDesired, 0.0, 1.0);  // less save if refilling
    const double proximity = (double)(g_potionWindow - hardDist + 1) / g_potionWindow; // closer = more urgent
    return kPotionBaseKeep + g_potionBonus * proximity * scarcity;
}

static int vConnect() {
    if (t_vSock >= 0) return t_vSock;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)g_vPort);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    // A missing localhost server must not stall a native bestbench forever:
    // WSL can leave a blocking connect in SYN-SENT when port 5555 is absent.
    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags >= 0) fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    const int rc = connect(fd, (sockaddr *)&addr, sizeof(addr));
    if (rc < 0 && errno != EINPROGRESS) { close(fd); return -1; }
    if (rc < 0) {
        fd_set writable, errors;
        FD_ZERO(&writable); FD_SET(fd, &writable);
        FD_ZERO(&errors); FD_SET(fd, &errors);
        timeval timeout{1, 0};
        const int ready = select(fd + 1, nullptr, &writable, &errors, &timeout);
        if (ready <= 0 || FD_ISSET(fd, &errors)) { close(fd); return -1; }
        int error = 0; socklen_t errorLen = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &errorLen) < 0 || error != 0) {
            close(fd); return -1;
        }
    }
    if (flags >= 0) fcntl(fd, F_SETFL, flags);
    t_vSock = fd;
    return fd;
}

// Inference requests are idempotent.  Never turn a transient socket failure or
// short write into a strategic fallback (card skip, empty shop plan, etc.):
// reconnect and replay the complete request.  The old one-shot send() path
// silently changed decisions when a persistent connection was dropped.
static std::string vRequestLine(const std::string &requestWithNewline) {
    // Model loading (especially the optional Torch model) can take several
    // seconds.  A fixed launcher sleep previously let the first benchmark run
    // race server readiness and silently use fallbacks, while later runs used
    // the real policy.  Wait through cold start as well as retrying dropped
    // persistent connections.
    constexpr int maxAttempts = 50;
    for (int attempt = 0; attempt < maxAttempts; ++attempt) {
        int fd = vConnect();
        if (fd < 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        std::size_t sent = 0;
        while (sent < requestWithNewline.size()) {
            const ssize_t n = send(fd, requestWithNewline.data() + sent,
                                   requestWithNewline.size() - sent, 0);
            if (n <= 0) break;
            sent += static_cast<std::size_t>(n);
        }
        if (sent != requestWithNewline.size()) {
            vDisconnect();
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            continue;
        }

        char buf[8192];
        std::string response;
        while (response.find('\n') == std::string::npos) {
            const ssize_t n = recv(fd, buf, sizeof(buf), 0);
            if (n <= 0) break;
            response.append(buf, static_cast<std::size_t>(n));
        }
        const auto newline = response.find('\n');
        if (newline != std::string::npos) {
            response.resize(newline + 1);
            return response;
        }
        vDisconnect();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return {};
}

std::string mapGraphCsv(const GameContext &gc, bool rooms) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const MapNode &node = gc.map->getNode(x, y);
        if (rooms) {
            out << static_cast<int>(node.room);
        } else {
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << edgeMask;
        }
    }
    return out.str();
}

std::string mapSpecialCsv(const GameContext &gc) {
    std::ostringstream out;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        if (x || y) out << ',';
        const bool burning = !gc.greenKey && x == gc.map->burningEliteX && y == gc.map->burningEliteY;
        out << (burning ? 1 : 0);
    }
    return out.str();
}

// send a tagged candidate/state query and read back the chosen index.
// bossW >= 0 routes the pick through the boss-survival blend "CB;<w>;..." (the
// server returns the chosen card's v_rich marginal, so the skip logic is unchanged).
int vQuery(GameContext &gc, int rIdx, double bossW) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    if (g_nativeOoc && bossW < 0.0 && !g_cardWin && !g_cardNN && !g_cardAction)
        return nativeFloorCardPick(gc, rIdx);
    std::string req;
    if (g_cardAction) req += "CA;";                           // direct card/skip action value
    else if (bossW >= 0.0) { req += "CB;"; req += std::to_string(bossW); req += ';'; }  // boss-V blend
    else if (g_cardNN) { req += "CN;"; req += std::to_string(g_cardNNW); req += ';'; }  // deck-set NN marginal
    else if (g_cardWin) req += "CW;";   // route card pick through the win model (P(win) marginal)
    for (int i = 0; i < n; ++i) {
        if (i) req += ',';
        const Card &card = r.cardRewards[rIdx][i];
        req += std::to_string((int)card.getId());
        if (g_cardAction) { req += ':'; req += card.isUpgraded() ? '1' : '0'; }
    }
    req += ';';
    if (g_cardAction) {
        req += mapGraphCsv(gc, true); req += ';';
        req += mapGraphCsv(gc, false); req += ';';
        req += mapSpecialCsv(gc); req += ';';
    }
    req += vFeatCsv(gc);        // full rich feature vector (richRow schema)
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return 5;
    // server returns "<best_idx> <best_marginal>"; apply the skip threshold here
    int idx = 5; double marg = -1e9;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &marg) < 1) return 5;
    if (idx < 0 || (idx >= n && idx != 5)) return 5;
    if (g_actFightProbeTrace) {
        std::cerr << "[card-v decision=" << t_actFightProbeDecisionIdx - 1
                  << " action=" << t_actFightProbeActionIdx
                  << " future=" << t_actFightProbeFutureIdx
                  << " floor=" << gc.floorNum << " candidates=";
        for (int i = 0; i < n; ++i)
            std::cerr << (i ? ";" : "") << (int)r.cardRewards[rIdx][i].getId();
        std::cerr << " reqHash=" << std::hash<std::string>{}(req)
                  << " response=" << idx << ':' << marg << "]\n";
    }
    // boss blend returns a floor-scale v_rich marginal, so use the floor skip bar there
    const double skipThr = (bossW >= 0.0) ? g_cardSkipThresh
                         : g_cardNN        ? g_cardNNSkip
                         : (g_cardWin ? g_cardWinSkip : g_cardSkipThresh);
    if (!g_cardAction && idx != 5 && marg < skipThr) return 5; // direct action model selects skip itself
    return idx;
}

// Raw V(state) = predicted final floor for the current state (server "VS" op).
// Used as a deck-strength scalar for V-informed pathing. Returns a large sentinel
// (so aggr clamps to neutral-ish) if the server is unreachable.
double vStateRaw(GameContext &gc) {
    if (g_nativeOoc) return nativeFloorValue(gc);
    std::string req = "VS;";
    req += vFeatCsv(gc);
    req += '\n';
    const std::string resp = vRequestLine(req);
    if (resp.empty()) return -1e9;
    double v = -1e9;
    if (std::sscanf(resp.c_str(), "%lf", &v) < 1) return -1e9;
    return v;
}

// Generic one-line request/response to the value server (for trace tooling).
std::string vSendRecv(const std::string &reqNoNl) {
    std::string req = reqNoNl; req += '\n';
    return vRequestLine(req);
}

// native V_win helpers use the shared compact-tree reader and rich feature map.
std::vector<float> richFeatureVec(GameContext &gc);
bool   winNetOk();
static double winNetPredict(const std::vector<float> &raw);

// Native win-model card pick (P(win) marginal), mirrors server decide_win but socket-free.
int nativeWinCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int nc = r.cardRewards[rIdx].size();
    const auto &idx = richIdxMap();
    const std::vector<float> base = richFeatureVec(gc);
    const double b = winNetPredict(base);
    const int dsz = idx.at("deckSize");
    int barg = 0; double bmarg = -1e18;
    for (int i = 0; i < nc; ++i) {
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        std::vector<float> v = base;
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) v[it->second] += 1.0f;
        v[dsz] += 1.0f;
        const double m = winNetPredict(v) - b;
        if (m > bmarg) { bmarg = m; barg = i; }
    }
    return bmarg < g_cardWinSkip ? 5 : barg;    // skip if best marginal below the win-scale bar
}

// --- BOSS-RELIC + NEOW choice via V_win: pick the option whose RESULTING state has the
// highest P(win). Same "which resulting state is best" frame as shop/rest, now applied to two
// high-impact decisions the default heuristic used to own. Each candidate is applied to a COPY
// (real relic/Neow transition, RNG untouched on the real gc), evaluated with V_win, argmax'd.
int g_bossRelicV = 0;   // STS_BOSS_RELIC=1
int g_neowV      = 0;   // STS_NEOW_V=1

using WinNet = CompactTreeNet;
static WinNet g_winNet;
static WinNet g_floorNet;
// The E2c module loads its native model only for the explicit parity-validation
// mode; ordinary gameplay and e2cgen do not load or invoke it.
bool   winNetOk() { return g_winNet.ok; }
static double winNetPredict(const std::vector<float> &raw) { return g_winNet.predict(raw); }

// rich feature vector as floats (parse of vFeatCsv -> exactly the raw layout).
std::vector<float> richFeatureVec(GameContext &gc) {
    const std::string s = vFeatCsv(gc);
    std::vector<float> v; v.reserve(1024); std::string cur;
    for (char c : s) { if (c == ',') { v.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); } else cur += c; }
    if (!cur.empty()) v.push_back(std::strtof(cur.c_str(), nullptr));
    return v;
}

double nativeFloorValue(GameContext &gc) {
    return g_floorNet.ok ? g_floorNet.predict(richFeatureVec(gc)) : 0.0;
}

int nativeFloorCardPick(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const std::vector<float> base = richFeatureVec(gc);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    double best = -1e100; int bestIdx = 5;
    const double v0 = g_floorNet.predict(base);
    for (int i = 0; i < r.cardRewards[rIdx].size(); ++i) {
        std::vector<float> row = base;
        const int cid = (int)r.cardRewards[rIdx][i].getId();
        auto it = idx.find("d" + std::to_string(cid));
        if (it != idx.end()) row[it->second] += 1.0f;
        row[dsz] += 1.0f;
        const double marginal = g_floorNet.predict(row) - v0;
        if (marginal > best) { best = marginal; bestIdx = i; }
    }
    return best < g_cardSkipThresh ? 5 : bestIdx;
}

std::string nativeShopPlan(GameContext &gc) {
    const Shop &sh = gc.info.shop;
    const auto &idx = richIdxMap();
    const int goldIdx = idx.at("gold"), dsz = idx.at("deckSize");
    const std::vector<float> base = richFeatureVec(gc);
    struct Item { char kind; int slot, price, id; };
    std::vector<Item> items;
    for (int i = 0; i < 7; ++i) if (sh.cardPrice(i) >= 0)
        items.push_back({'c', i, sh.cardPrice(i), (int)sh.cards[i].getId()});
    for (int i = 0; i < 3; ++i) if (sh.relicPrice(i) >= 0)
        items.push_back({'r', i, sh.relicPrice(i), (int)sh.relics[i]});
    if (items.size() > 16) items.resize(16);
    int removeId = -1; double removeGain = 0.0;
    if (sh.removeCost >= 0) {
        double v0 = g_floorNet.predict(base);
        for (int id = 0; id < 372; ++id) {
            auto it = idx.find("d" + std::to_string(id));
            if (it == idx.end() || base[it->second] <= 0) continue;
            auto row = base; row[it->second] -= 1.0f; row[dsz] -= 1.0f;
            double gain = g_floorNet.predict(row) - v0;
            if (removeId < 0 || gain > removeGain) { removeId = id; removeGain = gain; }
        }
    }
    double best = -1e100; unsigned bestMask = 0; bool bestRemove = false;
    const unsigned total = 1u << items.size();
    for (unsigned mask = 0; mask < total; ++mask) {
        int spend = 0, adds = 0;
        for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) { spend += items[k].price; ++adds; }
        for (int rem = 0; rem <= 1; ++rem) {
            if (rem && (sh.removeCost < 0 || removeId < 0)) continue;
            if (spend + (rem ? sh.removeCost : 0) > gc.gold) continue;
            auto row = base; row[goldIdx] -= spend + (rem ? sh.removeCost : 0); row[dsz] += adds;
            for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
                if (items[k].kind == 'c') {
                    auto it = idx.find("d" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] += 1.0f;
                } else {
                    auto it = idx.find("r" + std::to_string(items[k].id));
                    if (it != idx.end()) row[it->second] = std::max(row[it->second], 1.0f);
                }
            }
            if (rem) { auto it = idx.find("d" + std::to_string(removeId)); if (it != idx.end()) row[it->second] -= 1.0f; }
            const double value = g_floorNet.predict(row);
            if (value > best) { best = value; bestMask = mask; bestRemove = rem != 0; }
        }
    }
    std::ostringstream out;
    for (unsigned k = 0; k < items.size(); ++k) if (bestMask & (1u << k)) out << items[k].kind << items[k].slot << ' ';
    if (bestRemove) out << 'x';
    return out.str();
}

double vStateWin(GameContext &gc) {
    if (g_winNet.ok) return g_winNet.predict(richFeatureVec(gc));   // native path
    double v = 0.5;
    std::sscanf(vSendRecv("VW;" + vFeatCsv(gc)).c_str(), "%lf", &v);
    return v;
}
int g_pathV  = 0;   // STS_PATH_V:  model-driven pathing
int g_eventV = 0;   // STS_EVENT_V: model-driven events
// send an already-built request line, return the response line (empty on error)
std::string vTransact(const std::string &req) {
    int fd = vConnect();
    if (fd < 0) return "";
    if (send(fd, req.data(), req.size(), 0) < 0) { close(fd); t_vSock = -1; return ""; }
    char buf[64]; std::string resp;
    while (resp.find('\n') == std::string::npos) {
        ssize_t k = recv(fd, buf, sizeof(buf), 0);
        if (k <= 0) { close(fd); t_vSock = -1; return ""; }
        resp.append(buf, k);
    }
    return resp;
}

// Marginal V(deck+card)-V(deck) for each card reward candidate (empty on error).
static std::vector<double> vQueryMarginals(GameContext &gc, int rIdx) {
    auto &r = gc.info.rewardsContainer;
    const int n = r.cardRewards[rIdx].size();
    std::string req = "M;";
    for (int i = 0; i < n; ++i) { if (i) req += ','; req += std::to_string((int)r.cardRewards[rIdx][i].getId()); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    std::vector<double> out;
    std::istringstream is(resp);
    double m;
    while (is >> m) out.push_back(m);
    return out;
}

// Softmax-sample WHICH card to take (0..n-1) among the n candidates by marginal V
// (temp; higher = more spread). With prob uniformEps pick a uniformly-random card
// (coverage floor so V's blind spots still get sampled). The take-vs-skip decision
// is handled by the caller (skip@g_cardSkipThresh on the BEST marginal), so deck
// sizes match the exploit policy and we only diversify the card choice.
static int sampleCardSoftmax(const std::vector<double> &marg, double temp, double uniformEps,
                             std::default_random_engine &ex) {
    const int n = (int)marg.size();
    if (n <= 1) return 0;
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    if (ur(ex) < uniformEps) return std::uniform_int_distribution<int>(0, n - 1)(ex);
    const double mx = *std::max_element(marg.begin(), marg.end());
    const double t = temp > 1e-6 ? temp : 1e-6;
    double sum = 0.0; std::vector<double> w(n);
    for (int i = 0; i < n; ++i) { w[i] = std::exp((marg[i] - mx) / t); sum += w[i]; }
    double rnd = ur(ex) * sum, acc = 0.0;
    for (int i = 0; i < n; ++i) { acc += w[i]; if (rnd <= acc) return i; }
    return n - 1;
}

// ---------------------------------------------------------------------------
// WIN-RATE REST POLICY: decide heal-vs-upgrade in P(win) units (win model),
// where HP's effect on survival is sharp and nonlinear (unlike expected floor).
// Both options are scored as a P(win) gain and compared directly (no threshold):
//   heal    gain = P(win, hp+restHeal) - P(win, hp)              (server "HW")
//   upgrade gain = max_c P(win, u{c}+1) - P(win)                 (server "UW")
// Rest iff healGain >= best upgradeGain, else smith (upgrading that best card).
// ---------------------------------------------------------------------------
// Default ON: win-rate rest policy beats the default agent by +4.9pp @512 (47.3 vs
// 42.4, floor+HP also up). Needs the win model loaded in v_server (VWIN); set
// STS_REST_WIN=0 to disable (falls back to the sim default rest agent).
bool g_restWin = true;

// P(win, hp+healAmt) - P(win, hp) from the win model (0 on error).
double vQueryHealWin(GameContext &gc, int healAmt) {
    if (g_nativeOoc && g_winNet.ok) {
        const int old = gc.curHp;
        const double before = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = std::min(gc.maxHp, old + healAmt);
        const double after = g_winNet.predict(richFeatureVec(gc));
        gc.curHp = old;
        return after - before;
    }
    std::string req = "HW;" + std::to_string(healAmt) + ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// Best upgrade by P(win): returns index into candIds and sets *gain to its win gain.
int vQueryUpgradeWin(GameContext &gc, const std::vector<int> &candIds, double *gain) {
    if (g_nativeOoc && g_winNet.ok) {
        const auto &idx = richIdxMap(); auto base = richFeatureVec(gc);
        const double before = g_winNet.predict(base); double best = -1e100; int bestIdx = 0;
        for (int i = 0; i < (int)candIds.size(); ++i) {
            auto row = base; auto it = idx.find("u" + std::to_string(candIds[i]));
            if (it != idx.end()) row[it->second] += 1.0f;
            const double d = g_winNet.predict(row) - before;
            if (d > best) { best = d; bestIdx = i; }
        }
        // Mirror v_server.py's deterministic fallback: the deployed win model
        // has no useful upgrade head for some cards, so choose the card whose
        // removal most improves the current state in that case.
        if (std::abs(best) < 1e-6) {
            best = -1e100; bestIdx = 0;
            for (int i = 0; i < (int)candIds.size(); ++i) {
                auto row = base; auto it = idx.find("d" + std::to_string(candIds[i]));
                if (it != idx.end()) row[it->second] -= 1.0f;
                auto ds = idx.find("deckSize"); if (ds != idx.end()) row[ds->second] -= 1.0f;
                const double d = before - g_winNet.predict(row);
                if (d > best) { best = d; bestIdx = i; }
            }
        }
        if (gain) *gain = best;
        return bestIdx;
    }
    std::string req = "UW;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = 0; double g = 0.0;
    if (std::sscanf(resp.c_str(), "%d %lf", &idx, &g) < 1) { idx = 0; g = 0.0; }
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    if (gain) *gain = g;
    return idx;
}

// Handle a REST_ROOM screen by win-rate: rest iff heal raises P(win) more than the
// best upgrade does. Returns false (defer to default agent) if it's not a genuine
// heal-vs-smith choice (keys/dig/single-option).
// index (into candIds) of the card whose REMOVAL most raises V (0 on error)
int vQueryRemove(GameContext &gc, const std::vector<int> &candIds) {
    if (g_nativeOoc && !g_shopWin && g_floorNet.ok) {
        const auto &idx = richIdxMap();
        const int dsz = idx.at("deckSize");
        const std::vector<float> base = richFeatureVec(gc);
        const double v0 = g_floorNet.predict(base);
        double best = -1e100;
        int bestIdx = 0;
        for (int i = 0; i < (int)candIds.size(); ++i) {
            auto row = base;
            auto it = idx.find("d" + std::to_string(candIds[i]));
            if (it != idx.end()) row[it->second] -= 1.0f;
            row[dsz] -= 1.0f;
            const double gain = g_floorNet.predict(row) - v0;
            if (gain > best) { best = gain; bestIdx = i; }
        }
        return bestIdx;
    }
    std::string req = "X;";
    for (size_t i = 0; i < candIds.size(); ++i) { if (i) req += ','; req += std::to_string(candIds[i]); }
    req += ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    int idx = resp.empty() ? 0 : std::atoi(resp.c_str());
    if (idx < 0 || idx >= (int)candIds.size()) idx = 0;
    return idx;
}

// ---------------------------------------------------------------------------
// SHOP VALUE POLICY: ask the server for the V-maximizing affordable bundle of
// {card buys, card removal, relic buys} and execute it. Card buys and removal
// are well-modeled (deck-aware V); relics get a generic nRelics delta (can't
// rank relic identity); potions are not modeled (never bought here). Returns
// true if it acted on the shop screen.
// ---------------------------------------------------------------------------
std::string vQueryShop(GameContext &gc) {
    if (g_nativeOoc && !g_shopWin) return nativeShopPlan(gc);
    const Shop &sh = gc.info.shop;
    std::string cardsCsv, relicsCsv;
    for (int i = 0; i < 7; ++i) {
        if (i) cardsCsv += ',';
        cardsCsv += std::to_string((int)sh.cards[i].getId()) + ":" + std::to_string(sh.cardPrice(i));
    }
    for (int j = 0; j < 3; ++j) {
        if (j) relicsCsv += ',';
        relicsCsv += std::to_string((int)sh.relics[j]) + ":" + std::to_string(sh.relicPrice(j));
    }
    std::string req = std::string(g_shopWin ? "SW;" : "S;") + std::to_string(sh.removeCost)
                    + ";" + cardsCsv + ";" + relicsCsv + ";" + vFeatCsv(gc) + "\n";
    return vTransact(req);
}

// Execute ONE purchase from the V-optimal plan, then return. Re-entry re-optimizes
// on the updated state, so a buy that opens a follow-up screen (e.g. a bottling
// relic, or the removal card-select) can't desync a multi-buy sequence. Empty
// plan -> leave the shop. Each buy strictly spends gold, so this terminates.
static double sigmoid(double z) { return 1.0 / (1.0 + std::exp(-z)); }

// ---------------------------------------------------------------------------
// HEURISTIC PATHING: pick the map route by scoring each room and taking the
// child that leads to the best-scoring remaining path to the boss.
//
// Spec (from the player's intuition):
//   * elites & rest sites are great; elites more so the LATER you fight them
//     (you're stronger, and you get healed at act end anyway);
//   * shops are worth it only if you can afford them;
//   * fights build the deck and are good when you have HP, especially act 1;
//   * events balance out a fight-heavy path;
//   * in general take the HARDEST path you can still survive -- reward density
//     beats HP hoarding because the act-transition heals you.
//
// HP-awareness is implicit: the policy re-plans every floor with live curHp,
// and elite/monster values are gated by current HP, so a healthy hero routes
// into elites/fights and a hurt one routes to rests/events.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// BOSS-GATED ROLLOUT DRAFT: deaths cluster at act bosses, so for card rewards
// picked within a few rows of the upcoming boss we DON'T trust the myopic 1-ply
// server V. Instead, for each candidate (each card + skip) we copy the run,
// apply the pick, and roll the next few fights forward -- INCLUDING the boss --
// scoring by end-state (HP / win). The inner rollouts reuse rolloutChoice, which
// already respects fair-play and the V_combat leaf, so each is cheap. Falls back
// to the server pick when no hard fight is close.
//   The "how close is a hard fight" gate is deliberately factored out
// (rowsToHardFight, defined above) so the hard-fight set can later become DYNAMIC
// (wherever we die often); for now it is boss-only.
// ---------------------------------------------------------------------------
// Returns true iff it handled the card reward(s); false => caller uses server V.
bool bossGatedDraftPolicy(GameContext &gc) {
    if (!g_bossDraft) return false;
    if (rowsToHardFight(gc) > g_bossDraftRows) return false;   // no hard fight close -> server pick
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    while (r.cardRewardCount > 0) {
        const int rIdx   = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e18;
        int    bestIdx   = 5;                                  // 5 == skip
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = (cand < nCards) ? cand : 5;
            double acc = 0;
            for (int f = 0; f < g_bossDraftFutures; ++f) {
                // seed depends only on f -> every candidate faces the SAME sampled
                // futures (common random numbers -> low-variance A/B between picks).
                std::uint64_t s = gc.seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1));
                acc += rolloutChoice(gc, rIdx, cardIdx, g_bossDraftN, g_bossDraftSims, s);
            }
            const double score = acc / g_bossDraftFutures;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    return true;
}

// ---------------------------------------------------------------------------
// RUN TRACE: replay ONE seed with the deployed OOC policy and print a
// human-readable line per MAP NODE (what it was, what we fought / which event,
// and the resulting state: HP, gold, deck delta, deck, relics, potions). For
// eyeballing the agent's decisions against human game knowledge. This is a
// DIAGNOSTIC trace, not a mirror of runFullRunOOC: it logs but does not use
// some event/treasure scores and omits some fallthrough policy layers.
// ---------------------------------------------------------------------------
static std::string tr_deck(const GameContext &gc) {
    std::map<std::string,int> m;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ++m[n]; }
    std::string s;
    for (auto &kv : m) { s += kv.first; if (kv.second > 1) s += " x" + std::to_string(kv.second); s += ", "; }
    return s;
}
static std::multiset<std::string> tr_deckMs(const GameContext &gc) {
    std::multiset<std::string> ms;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ms.insert(n); }
    return ms;
}
static std::string tr_relics(const GameContext &gc) {
    std::string s;
    for (const auto &ri : gc.relics.relics) { s += sts::relicNames[(int)ri.id]; s += ", "; }
    return s.empty() ? "-" : s;
}
static std::string tr_potions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        s += sts::getPotionName(gc.potions[i]); s += ", ";
    }
    return s.empty() ? "-" : s;
}
static std::string tr_event(Event e) {
    // enum-order names (matches include/constants/Events.h)
    static const char *const kEventNames[] = {
        "INVALID","MONSTER","REST","SHOP","TREASURE","NEOW","Ominous Forge","Pleading Vagrant",
        "Ancient Writing","Old Beggar","Big Fish","Bonfire Spirits","Colosseum","Cursed Tome",
        "Dead Adventurer","Designer in-Spire","Augmenter","Duplicator","Face Trader","Falling",
        "Forgotten Altar","The Divine Fountain","Ghosts","Golden Idol","Golden Shrine","Wing Statue",
        "Knowing Skull","Lab","The Ssssserpent","Living Wall","Masked Bandits","Match and Keep",
        "Mindbloom","Hypnotizing Mushrooms","Mysterious Sphere","The Nest","Nloth","Note For Yourself",
        "Purifier","Scrap Ooze","Secret Portal","Sensory Stone","Shining Light","The Cleric","The Joust",
        "The Library","The Mausoleum","The Moai Head","The Woman in Blue","Tomb of Lord Red Mask",
        "Transmogrifier","Upgrade Shrine","Vampires","We Meet Again","Wheel of Change","Winding Halls",
        "World of Goop" };
    const int i = (int)e;
    return (i >= 0 && i < (int)(sizeof(kEventNames)/sizeof(*kEventNames))) ? kEventNames[i]
                                                                           : "Event#" + std::to_string(i);
}
static std::string tr_deckDelta(const std::multiset<std::string> &prev, const std::multiset<std::string> &cur) {
    std::string s;
    for (const auto &n : cur) if (cur.count(n) > prev.count(n) && s.find("+" + n + " ") == std::string::npos) {
        int d = (int)cur.count(n) - (int)prev.count(n);
        s += "+" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    for (const auto &n : prev) if (prev.count(n) > cur.count(n) && s.find("-" + n + " ") == std::string::npos) {
        int d = (int)prev.count(n) - (int)cur.count(n);
        s += "-" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    return s;
}

// Log each pending card reward's OPTIONS + the model's marginal-V (final-floor units,
// via the server "M" op) so drafts can be graded, not just the pick. skip bar = g_cardSkipThresh.
// When the OOC action NN is active (STS_OOC_ACTION_NN=1), also query its OA endpoint and
// show the NN's utility score for each card.
static void tr_logDraft(GameContext &gc) {
    // The "M" marginals op is server-only. Skip the draft log cleanly when no
    // server is reachable (same vConnect()<0 fail-fast pattern as vTransact),
    // instead of letting vRequestLine retry ~50x per card reward.
    if (vConnect() < 0) return;
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = 0; rIdx < r.cardRewardCount; ++rIdx) {
        auto &cr = r.cardRewards[rIdx];
        if (cr.size() == 0) continue;

        // V_rich marginals (server M op)
        std::string req = "M;";
        for (int i = 0; i < cr.size(); ++i) { if (i) req += ','; req += std::to_string((int)cr[i].getId()); }
        req += ';'; req += vFeatCsv(gc);
        std::string resp = vSendRecv(req);
        std::vector<double> marg; { std::istringstream is(resp); double v; while (is >> v) marg.push_back(v); }

        // NN scores for each card option + skip
        std::vector<double> nnScores;
        if (g_oocCheckpointNet.ok) {
            const std::vector<float> state = richFeatureVec(gc);
            using RT = search::GameAction::RewardsActionType;
            for (int i = 0; i < cr.size(); ++i) {
                std::uint32_t abits = search::GameAction(RT::CARD, rIdx, i).bits;
                nnScores.push_back(g_oocCheckpointNet.predict(state.data(), abits, (int)gc.screenState, gc.act));
            }
            std::uint32_t sbits = search::GameAction(RT::SKIP).bits;
            nnScores.push_back(g_oocCheckpointNet.predict(state.data(), sbits, (int)gc.screenState, gc.act));
        }

        // One-ply strategic scores for each card option + the CARD(rIdx,5) skip:
        // Q(s,a) directly (Tier-B, §72), or V(s') of the successor when
        // STS_OOC_STRATEGIC_Q=0 (V2 behaviour).
        std::vector<double> oneplyScores;
        if (g_oocStrategicNet.ok) {
            using RT = search::GameAction::RewardsActionType;
            const std::vector<float> state = richFeatureVec(gc);
            auto score = [&](const search::GameAction &a) {
                if (g_oocStrategicQ) {
                    int actionType, c1, c2, c3, cand1, cand2, cand3;
                    strategicCands(gc, a, actionType, c1, c2, c3, cand1, cand2, cand3);
                    const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
                    return g_oocStrategicNet.predictActionValue(state.data(), a.bits,
                                                                cats, actionType, (int)gc.screenState);
                }
                GameContext probe = gc;
                a.execute(probe);
                return g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                      (int)probe.screenState);
            };
            for (int i = 0; i < cr.size(); ++i)
                oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, i)));
            oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, 5)));
        }

        std::string line = "         draft options [skip if <" + std::to_string(g_cardSkipThresh) + "]: ";
        int best = -1; double bestv = -1e18;
        for (int i = 0; i < cr.size(); ++i) {
            double m = i < (int)marg.size() ? marg[i] : 0.0;
            if (m > bestv) { bestv = m; best = i; }
            std::string nm = cr[i].getName(); if (cr[i].isUpgraded()) nm += "+";
            char buf[64];
            if (i < (int)nnScores.size()) {
                std::snprintf(buf, sizeof(buf), "%s(V:%+.2f NN:%.3f)", nm.c_str(), m, nnScores[i]);
                line += buf;
                if (i < (int)oneplyScores.size())
                    line += " 1ply:" + std::to_string(oneplyScores[i]);
                line += "  ";
            } else {
                std::snprintf(buf, sizeof(buf), "%s(%+.2f)  ", nm.c_str(), m);
                line += buf;
            }
        }
        line += "-> V_rich picks ";
        line += (bestv < g_cardSkipThresh) ? "SKIP" : (std::string)(cr[best].getName());
        if (!nnScores.empty()) {
            int nnBest = 0;
            for (int i = 1; i < (int)nnScores.size(); ++i)
                if (nnScores[i] > nnScores[nnBest]) nnBest = i;
            line += "  NN: skip=" + std::to_string(nnScores.back()) + " picks ";
            line += (nnBest < cr.size()) ? (std::string)(cr[nnBest].getName()) : "SKIP";
            if (nnBest > 0 && nnBest != best) line += " [DISAGREE]";
        }
        std::printf("%s\n", line.c_str());
    }
}

// Show NN scores for all legal OOC actions with action descriptions.
static void tr_logOocActions(const char *label, GameContext &gc) {
    if (!g_oocCheckpointNet.ok) return;
    const std::vector<float> state = richFeatureVec(gc);
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return;
    double best = -1e100; int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        double s = g_oocCheckpointNet.predict(state.data(), actions[i].bits, (int)gc.screenState, gc.act);
        std::string desc;
        if (gc.screenState == ScreenState::REST_ROOM) {
            int idx = actions[i].getIdx1();
            if (idx == 0) desc = "HEAL";
            else if (idx == 1) {
                int smithIdx = actions[i].getIdx2();
                if (smithIdx >= 0 && smithIdx < (int)gc.deck.cards.size())
                    desc = std::string("smith:") + gc.deck.cards[smithIdx].getName();
                else desc = "smith";
            } else if (idx == 2) desc = "DIG";
            else if (idx == 3) desc = "LIFT";
            else if (idx == 4) desc = "TOKE";
            else desc = "rest#" + std::to_string(idx);
        } else {
            desc = "#" + std::to_string(i);
        }
        std::printf("         [NN %s] %s = %.3f\n", label, desc.c_str(), s);
        if (s > best) { best = s; bestIdx = i; }
    }
    std::printf("         [NN %s] -> picks #%d (%.3f)\n", label, bestIdx, best);
}

// Refight the CURRENT battle K times from a copy of the pre-fight state, reseeding the
// battle RNGs each time so draw order + enemy moves vary -> separates a bad fight model
// from an unlucky single sample. Prints end-HP distribution, death rate, potions used.
static void tr_refight(const GameContext &gc, int sims, int K) {
    std::vector<int> hp; int deaths = 0, potUsed = 0;
    const int potBefore = gc.potionCount;
    for (int k = 0; k < K; ++k) {
        GameContext g2 = gc;
        BattleContext bc; bc.init(g2);
        bc.shuffleRng      = sts::Random(gc.seed * 2654435761u + k * 40503u + 1);
        bc.aiRng           = sts::Random(gc.seed * 2246822519u + k * 668265263u + 7);
        bc.cardRandomRng   = sts::Random(gc.seed * 3266489917u + k * 374761393u + 13);
        search::ScumSearchAgent2 ag; ag.simulationCountBase = fightSims(gc, sims);
        ag.rng = std::default_random_engine(gc.seed + 999u + k);
        ag.playoutBattle(bc);
        bc.exitBattle(g2);
        const bool died = g2.curHp <= 0 || g2.outcome == GameOutcome::PLAYER_LOSS;
        if (died) ++deaths; hp.push_back(std::max(0, g2.curHp));
        potUsed += potBefore - g2.potionCount;
    }
    std::sort(hp.begin(), hp.end());
    double mean = 0; for (int h : hp) mean += h; mean /= std::max(1, (int)hp.size());
    std::printf("         >> REFIGHT x%d: deaths %d/%d  endHP min %d / med %d / mean %.1f / max %d"
                "  avg potions used %.2f (had %d)\n",
                K, deaths, K, hp.front(), hp[hp.size()/2], mean, hp.back(),
                (double)potUsed / std::max(1, K), potBefore);
}

static void runTraceRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;

    std::printf("=== RUN TRACE seed %llu  asc %d  sims %d%s ===\n",
                (unsigned long long)seed, asc, sims, search::g_fairPlay ? "  [fair-play]" : "");
    std::printf("!!! DIAGNOSTIC TRACE: does NOT exactly reproduce runFullRunOOC policy !!!\n");

    const int refightFloor = std::getenv("STS_REFIGHT_FLOOR") ? std::atoi(std::getenv("STS_REFIGHT_FLOOR")) : -1;
    const int refightN     = std::getenv("STS_REFIGHT_N")     ? std::atoi(std::getenv("STS_REFIGHT_N"))     : 20;
    const int combatLogFloor = std::getenv("STS_COMBAT_LOG")  ? std::atoi(std::getenv("STS_COMBAT_LOG"))    : -1;
    int clLastTurn = -1;
    // Per-decision combat logger (via the g_onCombatDecision hook): one line per in-fight
    // decision -> turn, energy, player HP/block/str/dex, each alive monster's HP/block/intent, hand.
    auto combatLog = [&clLastTurn](const BattleContext &bc) {
        if (bc.turn != clLastTurn) { std::printf("   --- Turn %d ---\n", bc.turn); clLastTurn = bc.turn; }
        auto ps = [&](PlayerStatus s){ auto it = bc.player.statusMap.find(s); return it != bc.player.statusMap.end() ? (int)it->second : 0; };
        std::string mon;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const Monster &m = bc.monsters.arr[i];
            if (m.curHp <= 0 || !m.isTargetable()) continue;
            DamageInfo di = m.getMoveBaseDamage(bc);
            std::string intent = monsterMoveStrings[(int)m.moveHistory[0]];
            if (di.damage > 0) { intent += "(" + std::to_string(di.damage);
                                 if (di.attackCount > 1) intent += "x" + std::to_string(di.attackCount);
                                 intent += ")"; }
            char buf[160];
            std::snprintf(buf, sizeof(buf), "%s HP%d+%d[%s] ", m.getName(), m.curHp, m.block, intent.c_str());
            mon += buf;
        }
        std::string hand;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            std::string n = bc.cards.hand[i].getName(); if (bc.cards.hand[i].isUpgraded()) n += "+";
            hand += n; hand += " ";
        }
        std::printf("   [E%d] you HP%d+%dblk Str%d Dex%d Weak%d | %s| hand: %s\n",
                    bc.player.energy, bc.player.curHp, bc.player.block,
                    ps(PlayerStatus::STRENGTH), ps(PlayerStatus::DEXTERITY), ps(PlayerStatus::WEAK),
                    mon.c_str(), hand.c_str());
    };
    bool nodeActive = false; std::string label, desc; int preHp = gc.curHp;
    std::multiset<std::string> prevDeck = tr_deckMs(gc);

    auto flush = [&]() {
        if (!nodeActive) return;
        auto curDeck = tr_deckMs(gc);
        std::string delta = tr_deckDelta(prevDeck, curDeck);
        std::printf("[F%-2d A%d] %-9s %-22s  HP %d/%d (%+d)  gold %d\n",
                    gc.floorNum, gc.act, label.c_str(), desc.c_str(),
                    gc.curHp, gc.maxHp, gc.curHp - preHp, gc.gold);
        if (!delta.empty())          std::printf("         change: %s\n", delta.c_str());
        std::printf("         deck(%d): %s\n", (int)gc.deck.size(), tr_deck(gc).c_str());
        std::printf("         relics: %s\n", tr_relics(gc).c_str());
        std::printf("         potions: %s\n", tr_potions(gc).c_str());
        prevDeck = curDeck; preHp = gc.curHp; nodeActive = false; label.clear(); desc.clear();
    };
    auto roomName = [](Room r) -> const char * {
        switch (r) { case Room::MONSTER: return "MONSTER"; case Room::ELITE: return "ELITE";
            case Room::BOSS: case Room::BOSS_TREASURE: return "BOSS"; case Room::REST: return "REST";
            case Room::SHOP: return "SHOP"; case Room::TREASURE: return "TREASURE";
            case Room::EVENT: return "EVENT"; default: return "?"; }
    };

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            agent.simulationCountBase = fightSims(gc, sims);
            search::g_potionKeepValue = potionKeepValue(gc);
            BattleContext bc; bc.init(gc);
            flush();  // a battle always begins a fresh node (fixes forced rest/event -> boss merge)
            nodeActive = true; label = roomName(gc.curRoom);
            desc = sts::monsterEncounterStrings[(int)bc.encounter];
            if (gc.floorNum == refightFloor) {
                std::printf("[F%-2d A%d] %-9s %-22s  (pre-fight HP %d/%d)\n",
                            gc.floorNum, gc.act, label.c_str(), desc.c_str(), gc.curHp, gc.maxHp);
                tr_refight(gc, sims, refightN);
            }
            const bool doLog = gc.floorNum == combatLogFloor;
            if (doLog) {
                std::printf("[F%d A%d] === COMBAT LOG: %s (HP %d/%d) ===\n",
                            gc.floorNum, gc.act, desc.c_str(), gc.curHp, gc.maxHp);
                clLastTurn = -1; search::g_onCombatDecision = combatLog;
            }
            agent.playoutBattle(bc);
            if (doLog) { search::g_onCombatDecision = nullptr;
                         std::printf("   === end combat: you HP%d, %s ===\n", bc.player.curHp,
                                     bc.player.curHp > 0 ? "WON" : "DIED"); }
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            flush();
            tr_logOocActions("map", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocMapRouteSearchPolicy(gc, agent))
                    if (!oocOnePlyMapPolicy(gc, agent))
                        search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
            if (!nodeActive) { flush(); nodeActive = true; label = "EVENT"; desc = tr_event(gc.curEvent); }
            tr_logOocActions("event", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "REST"; }
            tr_logOocActions("rest", gc);
            if (!oocActionNNPolicy(gc)) {
                if (!oocOnePlyRestPolicy(gc, agent)) {
                    if (g_restWin && one_combat::restWinPolicy(gc)) {}
                    else agent.stepOutOfCombatPolicy(gc);
                }
            }
        } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "TREASURE"; }
            tr_logOocActions("treasure", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "SHOP"; }
            tr_logOocActions("shop", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc))
                    if (!oocOnePlyShopPolicy(gc, agent)) one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc)) one_combat::removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else { tr_logDraft(gc); if (!oocActionNNPolicy(gc)) { if (!oocOnePlyCardRewardPolicy(gc, agent)) one_combat::serverCardRewardPolicy(gc); } }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            tr_logOocActions("upgrade", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) one_combat::upgradeSelectWinPolicy(gc);
        } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    flush();
    std::printf("=== %s  final floor %d act %d  HP %d/%d ===\n",
                gc.outcome == GameOutcome::PLAYER_VICTORY ? "VICTORY" : "DEATH",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp);
}

// Single-arm readout of the CURRENT BEST out-of-combat stack: native floor-V
// card picks (skip@g_cardSkipThresh, default -0.5) + heuristic path + shop-V,
// with the default win-rate rest layer (g_restWin, heal-vs-upgrade in P(win)
// units) and optional legacy rest-V via STS_REST_V=1. Use this as the baseline
// arm for new experiments. Serverless under default native OOC.
static std::string benchTimestampUtc() {
    const std::time_t now = std::time(nullptr);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &now);
#else
    gmtime_r(&now, &tm);
#endif
    char buf[32] = {};
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

static bool bestBench(int sims, int nSeeds, int asc, std::uint64_t seedOffset = 0,
                      const std::string &resultsFile = "", const std::string &objective = "bestbench") {
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    std::cout << "BEST stack config: skip@" << g_cardSkipThresh
              << "  rest=" << (g_restWin ? "win-rate" : "default")
              << (restV ? "+legacy-rest-V" : "")
              << "  shop-V=ON  path=" << (g_pathV ? "model-driven" : "heuristic")
              << "  shop-beam=" << (g_oocShopBeam ? "ON" : "off")
              << "  native-OOC=" << (g_nativeOoc ? "ON" : "OFF")
              << "  keys=" << (g_collectKeys ? "collect" : "skip")
              << "  searcher=" << (search::g_useSearcher3 ? "Searcher3" : "Searcher2")
              << (search::g_useSearcher3
                  ? "  S3-abl[b,p,c,l,crn]=" + std::to_string(search::g_s3Belief)
                    + std::to_string(search::g_s3Prune) + std::to_string(search::g_s3Chain)
                    + std::to_string(search::g_s3Live) + std::to_string(search::g_s3Crn)
                    + "  S3-particles=" + std::to_string(search::g_s3Particles)
                    + "  S3-rollK=" + std::to_string(search::g_s3RolloutK)
                    + "  S3-turnStop=" + std::to_string(search::g_s3RolloutTurnStop)
                    + "  S3-turnBeam=" + (search::g_s3TurnRollout ? "ON" : "off")
                    + "  S3-semCard=" + (search::g_s3SemanticCardEdges ? "ON" : "off")
                  : std::string())
              << (search::g_fairPlay ? "  fair-play" : "")
              << "  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  asc " << asc << "  sims " << sims << "  threads " << numThreads() << "\n";
    std::cout << "BEST models: floor=" << (g_floorNet.ok ? g_floorNet.path : "MISSING")
              << "  win=" << (g_winNet.ok ? g_winNet.path : "not loaded")
              << "  combatVNet=" << (search::g_useVNet ? "ON" : "off")
              << (search::g_combatVNet.hasEncounterModels
                  ? "+per-encounter(" + std::to_string(search::g_combatVNet.encounterModels.size()) + ")"
                  : "")
              << "  policyNet=" << (search::g_usePolicyNet ? "ON" : "off")
              << "  PVNet=" << (search::g_usePVNet ? "ON" : "off")
              << "  distVNet=" << (search::g_useDistVNet ? "ON" : "off") << "\n";
    // Optional per-seed output powers the adaptive self-play gate. Rows are
    // flushed as runs finish, so the dashboard gets live progress and a killed
    // benchmark leaves valid results. The caller owns truncation; batches append.
    std::ofstream results;
    if (!resultsFile.empty()) {
        results.open(resultsFile, std::ios::app);
        if (results.tellp() == 0) {
            results << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n";
            results.flush();
        }
        sts::BenchConfigSidecar meta;
        meta.objective = objective;
        meta.argv = g_mainArgv;
        meta.timestamp = benchTimestampUtc();
        meta.seedLo = seedOffset;
        meta.seedHi = seedOffset + (std::uint64_t)(nSeeds > 0 ? nSeeds - 1 : 0);
        meta.nSeeds = nSeeds; meta.asc = asc; meta.sims = sims; meta.threads = numThreads();
        meta.cardSkipThresh = g_cardSkipThresh;
        meta.restPolicy = g_restWin ? "win-rate" : "default";
        meta.restV = restV; meta.shopV = true; meta.nativeOoc = g_nativeOoc;
        meta.pathMode = g_pathV ? "model-driven" : "heuristic";
        meta.shopBeam = g_oocShopBeam; meta.collectKeys = g_collectKeys;
        meta.searcher3 = search::g_useSearcher3; meta.fairPlay = search::g_fairPlay;
        meta.s3Belief = search::g_s3Belief; meta.s3Prune = search::g_s3Prune;
        meta.s3Chain = search::g_s3Chain; meta.s3Live = search::g_s3Live; meta.s3Crn = search::g_s3Crn;
        meta.s3Particles = search::g_s3Particles; meta.s3RolloutK = search::g_s3RolloutK;
        meta.s3RolloutTurnStop = search::g_s3RolloutTurnStop != 0;
        meta.s3TurnRollout = search::g_s3TurnRollout;
        meta.s3SemanticCardEdges = search::g_s3SemanticCardEdges;
        meta.silverSearchEnabled = search::silverLiveBackendInstalled();
        meta.stsSilverSearchEffective = meta.silverSearchEnabled;
        meta.effectiveCombatBackend = meta.silverSearchEnabled ? "silver" : "native_searcher";
        meta.silverReuseCapMode = meta.silverSearchEnabled ? search::silverLiveReuseCapMode() : "";
        meta.silverReuseCap = meta.silverSearchEnabled ? search::silverLiveReuseCap() : 0;
        meta.silverUpstreamSha = meta.silverSearchEnabled
            ? "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff" : "";
        meta.executableGitSha = trainingExecutableGitSha();
        meta.silverScalingDiagnosticFile = meta.silverSearchEnabled
            ? search::silverLiveScalingDiagnosticFile() : "";
        meta.silverStickyQualityFile = meta.silverSearchEnabled
            ? search::silverLiveStickyQualityFile() : "";
        meta.silverAdaptiveEnabled = meta.silverSearchEnabled
            && search::silverLiveAdaptiveEnabled();
        meta.silverAdaptiveTopShare = meta.silverSearchEnabled
            ? search::silverLiveAdaptiveTopTwoVisitGapThreshold() : 0.0;
        meta.silverExactRootBudgets = meta.silverSearchEnabled
            && search::silverLiveExactRootBudgets();
        meta.floorModel = g_floorNet.ok ? g_floorNet.path : "MISSING";
        meta.winModel = g_winNet.ok ? g_winNet.path : "not loaded";
        meta.combatVNet = search::g_useVNet ? "ON" : "off";
        meta.policyNet = search::g_usePolicyNet ? "ON" : "off";
        meta.pvNet = search::g_usePVNet ? "ON" : "off";
        meta.distVNet = search::g_useDistVNet ? "ON" : "off";
        std::ofstream sidecar(resultsFile + ".meta.json", std::ios::app);
        if (!sidecar) std::cerr << "[bestbench] warning: cannot open " << resultsFile << ".meta.json\n";
        else sidecar << sts::benchConfigSidecarLine(meta) << '\n';
    }
    int wins = 0, completed = 0; long long floor = 0, hp = 0; double sec = 0;
    std::vector<std::pair<std::uint64_t, std::string>> failures;
    BenchProgress prog(nSeeds, "BEST");
    auto wall0 = std::chrono::steady_clock::now();
    // Do not create a one-iteration outer OpenMP team when the all-OOC oracle
    // is asked to parallelize its branches; that would otherwise serialize the
    // nested region. Multi-seed benches keep the proven outer parallelism.
    if (nSeeds == 1 && g_actFightProbeParallelBranches) {
        const std::uint64_t seed = seedOffset;
        try {
            RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec; ++completed;
            if (results.is_open()) {
                results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                        << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                        << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
                results.flush();
            }
            prog.tick(r.won, r.floor, r.hpEnd);
        } catch (const std::exception &e) {
            failures.emplace_back(seed, e.what());
        } catch (...) {
            failures.emplace_back(seed, "unknown non-standard exception");
        }
    } else {
        #pragma omp parallel for reduction(+:wins,floor,hp,sec,completed) schedule(dynamic)
        for (int s = 0; s < nSeeds; ++s) {
            const std::uint64_t seed = seedOffset + (std::uint64_t)s;
            try {
                RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
                wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec; ++completed;
                #pragma omp critical(bestbench_results)
                if (results.is_open()) {
                    results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                            << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                            << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
                    results.flush();
                }
                prog.tick(r.won, r.floor, r.hpEnd);
            } catch (const std::exception &e) {
                #pragma omp critical(bestbench_failures)
                failures.emplace_back(seed, e.what());
            } catch (...) {
                #pragma omp critical(bestbench_failures)
                failures.emplace_back(seed, "unknown non-standard exception");
            }
        }
    }
    prog.done();
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    if (completed > 0) {
        std::printf("BEST                    win%%=%5.1f   avg_floor=%5.1f   avg_hp_end=%5.1f   cpu_sec/run=%.2f   wall=%.1fs\n",
                    100.0 * wins / completed, (double)floor / completed,
                    (double)hp / completed, sec / completed, wall);
    }
    if (!failures.empty()) {
        std::sort(failures.begin(), failures.end());
        for (const auto &[seed, message] : failures) {
            std::cerr << "[bestbench-seed-failure] seed=" << seed << " error=" << message << '\n';
        }
        std::cerr << "bestbench: FAILED requested=" << nSeeds << " completed=" << completed
                  << " failed=" << failures.size() << '\n';
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// DATA GENERATION for an offline value function V(state) ~= P(win). At each
// card-reward decision we log a feature vector of the current run state; the
// label is the eventual outcome of that run (Monte-Carlo return). Card picks
// use eps-greedy exploration so the logged decks are diverse.
// ---------------------------------------------------------------------------
// scalar feature names only; datagen appends d0..d(kNumCardIds-1) then won,finalFloor
static const char *kFeatureHeader =
    "ascension,act,floor,curHp,maxHp,gold,deckSize,nAttack,nSkill,nPower,nCurse,"
    "nStatus,nUpgraded,nStarter,nCommon,nUncommon,nRare,obtainSum,obtainAvg,nRelics";

// deck as per-card-id counts d0..d(kNumCardIds-1) — makes value models deck-aware
// (able to express card synergies), shared by datagen and causalgen.
static std::string deckCountsCsv(const GameContext &gc) {
    std::array<int, kNumCardIds> cnt{};
    for (const auto &c : gc.deck.cards) {
        int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) ++cnt[id];
    }
    std::ostringstream o;
    for (int i = 0; i < kNumCardIds; ++i) { if (i) o << ','; o << cnt[i]; }
    return o.str();
}

static std::string featureRow(const GameContext &gc) {
    int nAtk=0,nSkill=0,nPow=0,nCurse=0,nStatus=0,nUpg=0,nStarter=0,nCommon=0,nUncommon=0,nRare=0;
    long obtainSum = 0;
    for (const auto &c : gc.deck.cards) {
        switch (c.getType()) {
            case CardType::ATTACK: ++nAtk; break;
            case CardType::SKILL:  ++nSkill; break;
            case CardType::POWER:  ++nPow; break;
            case CardType::CURSE:  ++nCurse; break;
            case CardType::STATUS: ++nStatus; break;
            default: break;
        }
        if (c.isUpgraded()) ++nUpg;
        if (c.isStarterStrikeOrDefend()) ++nStarter;
        switch (c.getRarity()) {
            case CardRarity::COMMON:   ++nCommon; break;
            case CardRarity::UNCOMMON: ++nUncommon; break;
            case CardRarity::RARE:     ++nRare; break;
            default: break;
        }
        obtainSum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    const int deckSize = gc.deck.size();
    const double obtainAvg = deckSize ? (double)obtainSum / deckSize : 0.0;
    std::ostringstream o;
    o << gc.ascension << ',' << gc.act << ',' << gc.floorNum << ','
      << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ',' << deckSize << ','
      << nAtk << ',' << nSkill << ',' << nPow << ',' << nCurse << ',' << nStatus << ','
      << nUpg << ',' << nStarter << ',' << nCommon << ',' << nUncommon << ',' << nRare << ','
      << obtainSum << ',' << obtainAvg << ',' << (int)gc.relics.relics.size();
    return o.str();
}

// ---------------------------------------------------------------------------
// RICH datagen v2: a comprehensive per-decision run-state snapshot for training
// value functions that are relic-aware, upgrade-aware, potion-aware, future-fight
// -aware, and path-aware. One row per card-reward decision; label = run outcome.
// Blocks: core, keys, potions-meta, future-fights/act, path-history, bottled
// cards, deck totals d{id}, deck upgrades u{id}, relics r{id} (0=absent /
// 1+counter), potions pot{id} (multi-hot). Wide but sparse. Append-capable.
// ---------------------------------------------------------------------------
// Full rich feature vector for a V query — identical schema/order to richRow() so
// training (vrich.csv) and serving match exactly. Uses the current run's path
// history when set (t_curPath), else an empty one (pv* = 0).
std::string vFeatCsv(const GameContext &gc) {
    static thread_local PathHistory emptyPath;
    return richRow(gc, t_curPath ? *t_curPath : emptyPath);
}

// ---------------------------------------------------------------------------
// V4 TOKEN STATE (ooc-strategic-v4.md §2): 42 globals (36 richRow scalars
// minus 8 hidden-information leaks + 6 derived thresholds) plus canonical
// deck/relic/potion tokens, built from the same GameContext loops as richRow().
// Built once per decision, reused across the legal actions of that decision.
// ---------------------------------------------------------------------------
// Parity hook (STS_OOC_STRATEGIC_TOK_CHECK=1): once per run, on the first
// gated decision, when the token net is loaded. Armed at run start.
// The 8 hidden-information leaks (nextEliteId, nextFight0/1/2,
// remElites, remFights, monOffset, eliteOffset) are excluded; bossId is kept.
static constexpr int TOK_NRAW = 36;
static void tokCheckGlobParity(const GameContext &gc, const TokState &ts) {
    static const char *const names[TOK_NRAW] = {
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize", "potionChance",
        "cardRarityFactor", "blueKey", "greenKey", "redKey", "potionCount", "potionCapacity",
        "bossId",
        "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure",
        "bottledAtkId", "bottledSkillId", "bottledPowId",
        "fmDElite", "fmDRest", "fmDShop", "fmDBoss", "fmCElite", "fmCRest", "fmCShop", "fmCEvent",
        "fmCMonster", "fmCTreasure", "curMapX", "curMapY"
    };
    const std::string csv = vFeatCsv(gc);
    std::vector<float> rich; std::string cur;
    for (char c : csv) { if (c == ',') { rich.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); } else cur += c; }
    if (!cur.empty()) rich.push_back(std::strtof(cur.c_str(), nullptr));
    const auto &idx = richIdxMap();
    for (int i = 0; i < TOK_NRAW; ++i) {
        const auto it = idx.find(names[i]);
        if (it == idx.end() || it->second >= (int)rich.size()) continue;
        const float rv = rich[it->second];
        if (rv != ts.glob[i])
            std::printf("[ooc-tok-check] glob[%d] %s: tok=%g rich=%g\n", i, names[i], ts.glob[i], rv);
    }
}

TokState buildTokState(const GameContext &gc, const PathHistory &path) {
    TokState ts;
    std::array<int, kNumCardIds> d{}, u{};
    int botAtk = -1, botSkill = -1, botPow = -1;
    for (int i = 0; i < gc.deck.size(); ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        if (id >= 0 && id < kNumCardIds) { ++d[id]; if (c.isUpgraded()) ++u[id]; }
        if (gc.deck.isCardBottled(i)) {
            switch (c.getType()) {
                case CardType::ATTACK: botAtk = id; break;
                case CardType::SKILL:  botSkill = id; break;
                case CardType::POWER:  botPow = id; break;
                default: break;
            }
        }
    }
    std::array<int, kNumRelics> r{};
    for (const auto &ri : gc.relics.relics) {
        const int id = (int)ri.id;
        if (id >= 0 && id < kNumRelics) r[id] = 1 + (ri.data > 0 ? ri.data : 0);
    }
    std::array<int, kNumPotions> pot{};
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        const int id = (int)gc.potions[i];
        if (id >= 0 && id < kNumPotions) ++pot[id];
    }
    const FwdMap fm = forwardMapFeatures(gc);
    // 36 raw scalars: same as richRow() minus the 8 hidden-information leaks
    // (nextEliteId, nextFight0/1/2, remElites, remFights, monOffset,
    //  eliteOffset at original indices 15-22); bossId is kept (visible on act map).
    const float glob[TOK_NRAW] = {
        (float)gc.ascension, (float)gc.act, (float)gc.floorNum, (float)gc.curHp,
        (float)gc.maxHp, (float)gc.gold, (float)gc.deck.size(),
        (float)gc.potionChance, (float)gc.cardRarityFactor,
        (float)(gc.blueKey ? 1 : 0), (float)(gc.greenKey ? 1 : 0), (float)(gc.redKey ? 1 : 0),
        (float)gc.potionCount, (float)gc.potionCapacity,
        (float)gc.boss,
        (float)path.roomVisits[(int)Room::SHOP], (float)path.roomVisits[(int)Room::REST],
        (float)path.roomVisits[(int)Room::EVENT], (float)path.roomVisits[(int)Room::ELITE],
        (float)path.roomVisits[(int)Room::MONSTER], (float)path.roomVisits[(int)Room::TREASURE],
        (float)botAtk, (float)botSkill, (float)botPow,
        (float)fm.dElite, (float)fm.dRest, (float)fm.dShop, (float)fm.dBoss,
        (float)fm.cElite, (float)fm.cRest, (float)fm.cShop, (float)fm.cEvent,
        (float)fm.cMonster, (float)fm.cTreasure,
        (float)gc.curMapNodeX, (float)gc.curMapNodeY
    };
    for (int i = 0; i < TOK_NRAW; ++i) ts.glob[i] = glob[i];
    // derived threshold features (ooc-strategic-v4.md §2.1)
    // canTakeEliteKey now uses fmCElite (reachable elites on the visible map)
    // instead of the removed remElites (exact hidden-queue count).
    ts.glob[TOK_NRAW + 0] = gc.maxHp > 0 ? (float)gc.curHp / gc.maxHp : 0.0f;
    ts.glob[TOK_NRAW + 1] = (float)(gc.maxHp - gc.curHp);
    ts.glob[TOK_NRAW + 2] = gc.potionCount < gc.potionCapacity ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 3] = gc.gold >= 75 ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 4] = fm.cElite > 0
                  && !(gc.blueKey && gc.greenKey && gc.redKey) ? 1.0f : 0.0f;
    ts.glob[TOK_NRAW + 5] = fm.dBoss <= 3 ? 1.0f : 0.0f;

    // deck tokens: canonical ascending cardId, upgraded=1 token before the
    // unupgraded one, capped at MAXDK=96
    ts.nDk = 0;
    for (int id = 0; id < kNumCardIds && ts.nDk < 96; ++id) {
        if (u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 1; ts.dk[ts.nDk][2] = u[id]; ++ts.nDk;
        }
        if (ts.nDk < 96 && d[id] - u[id] > 0) {
            ts.dk[ts.nDk][0] = id; ts.dk[ts.nDk][1] = 0; ts.dk[ts.nDk][2] = d[id] - u[id]; ++ts.nDk;
        }
    }
    // relic tokens: canonical ascending relicId (counter = 1 + relic data)
    ts.nRl = 0;
    for (int id = 0; id < kNumRelics && ts.nRl < 64; ++id)
        if (r[id] > 0) { ts.rl[ts.nRl][0] = id; ts.rl[ts.nRl][1] = r[id]; ++ts.nRl; }
    // potion tokens: canonical ascending potionId
    ts.nPt = 0;
    for (int id = 0; id < kNumPotions && ts.nPt < 8; ++id)
        if (pot[id] > 0) { ts.pt[ts.nPt][0] = id; ts.pt[ts.nPt][1] = pot[id]; ++ts.nPt; }

    if (g_oocStrategicTokCheck && g_oocStrategicTokNet.ok && t_tokCheckPending) {
        t_tokCheckPending = false;
        tokCheckGlobParity(gc, ts);
    }
    return ts;
}

// Rank every legal OOC action in one server request.  The model predicts the
// next-combat win probability and surviving HP fraction; the training score
// used for action selection is the same 10*P(win)+expected HP objective used
// by the offline transfer check.

struct OocCounterfactualResult {
    double won;
    double floor;
    double hp;
    int bootstrapped = 0;   // 1 when floor/won came from the native models, 0 on terminal
    bool valid = true;
    bool survivedH = false; // alive at the requested bounded horizon (diagnostic only)
};

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

static void stepFrozenV4Ooc(GameContext &, search::ScumSearchAgent2 &);

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

struct PredictedCheckpointFight {
    double winProbability = 0.0;
    int endHpIfWin = 1;
    int maxHp = 1;
    bool predictedWin = false;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter);

// Shared V1 labels: persistent pre-init features and terminal pre-exit outcome.
// Ambiguous Awakened One deaths retain V1's validity mask; loss-severity
// consumers must exclude progressAmbiguous, as the existing trainer does.
static std::string csvQuote(const std::string &s);
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
static const char *combatEvalLabelHeader() {
    return "won,trueDeath,escaped,turnCapLoss,progressAmbiguous,labelValid,terminalCombatHp,terminalCombatMaxHp,terminalNonMinionCurHp,terminalNonMinionMaxHp,winHpFrac,lossRemainingFrac,signedOutcome,quarantineReason";
}
static bool combatEvalEncounterValid(MonsterEncounter encounter) {
    const int index = static_cast<int>(encounter);
    return index >= 0 && index < static_cast<int>(sizeof(monsterEncounterStrings) / sizeof(monsterEncounterStrings[0]));
}
static const char *combatEvalRoomClass(Room room) {
    return room == Room::MONSTER ? "NORMAL" : room == Room::ELITE ? "ELITE" : room == Room::BOSS ? "BOSS" : "OTHER";
}
static CombatEvalLabel combatEvalTerminal(const BattleContext &bc, MonsterEncounter encounter,
                                         int hooks, int healthBefore, int healthAfter,
                                         bool allowInitializationTerminal = false) {
    constexpr double eps = 1e-3;
    const bool representableEncounter = combatEvalEncounterValid(encounter);
    bool decided = bc.outcome != Outcome::UNDECIDED;
    bool healthOk = search::isValidTrainingTerminal(decided, healthBefore,
                           healthAfter);
    bool escaped = bc.smokeBombUsed;
    bool trueDeath = bc.outcome == Outcome::PLAYER_LOSS && bc.player.curHp <= 0 && !escaped;
    bool won = bc.outcome == Outcome::PLAYER_VICTORY;
    // The simulator's terminal turn bound is 100.  An unresolved
    // battle below that bound is an invalid/non-death termination,
    // never a death label.
    constexpr int kCombatTurnCap = 100;
    bool turnCapLoss = !decided && bc.turn >= kCombatTurnCap;
    // Some start-of-combat effects can resolve a fight during BattleContext::init
    // before the first decision callback (for example Neow's Lament's final
    // charge).  The pre-init GameContext feature row is still a valid battle-start
    // example, but a missing hook remains fatal everywhere else.
    const bool initializationTerminal = allowInitializationTerminal
        && hooks == 0 && bc.turn == 0 && decided;
    const bool hasFirstDecisionBoundary = hooks > 0 || initializationTerminal;
    bool progressAmbiguous = trueDeath && encounter == MonsterEncounter::AWAKENED_ONE;
    bool labelValid = !escaped && representableEncounter && hasFirstDecisionBoundary
        && healthOk && (won || trueDeath);
    double terminalHp = std::max(0, bc.player.curHp), terminalMaxHp = std::max(0, bc.player.maxHp);
    double winHpFrac = std::max(eps, std::min(1.0, terminalMaxHp > 0 ? terminalHp / terminalMaxHp : eps));
    double enemyRatio = search::getNonMinionMonsterCurHpRatio(bc);
    int enemyCurHp = 0, enemyMaxHp = 0;
    search::getNonMinionMonsterHpTotals(bc, enemyCurHp, enemyMaxHp);
    double lossRemainingFrac = std::max(eps, std::min(1.0, enemyRatio));
    double signedOutcome = labelValid ? (won ? winHpFrac : -lossRemainingFrac) : 0.0;
    const char *reason = !representableEncounter ? "unknown_encounter" : !hasFirstDecisionBoundary ? "missing_first_decision_hook" : !healthOk ? "simulator_health_failure" : escaped ? "escape" : turnCapLoss ? "turn_cap" : (decided && !trueDeath && !won) ? "non_death_loss" : "";
    return {decided, healthOk, escaped, trueDeath, won, turnCapLoss, progressAmbiguous, labelValid,
            terminalHp, terminalMaxHp, winHpFrac, lossRemainingFrac, signedOutcome, enemyCurHp, enemyMaxHp, reason};
}
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

// Continue a copied run after any out-of-combat counterfactual action. Every
// branch in one decision uses the same agent seed and copied GameContext RNG
// state (common random numbers).  maxFights < 0 means finish the whole run.  A
// bounded branch resolves rewards/path choices after its last fight, stops at
// the next battle, then bootstraps expected final floor and P(win).
static OocCounterfactualResult
finishOocCounterfactual(GameContext gc, int sims, std::uint64_t agentSeed,
                        PathHistory path, int maxFights = -1, bool bootstrap = false,
                        FutureFightProbe *probe = nullptr, int stopAfterAct = 0,
                        const std::vector<int> *fightSimsSeq = nullptr,
                        bool usePredict = false,
                        const OocPrefixObserver *prefixObserver = nullptr,
                        OocContinuationCost *finalCost = nullptr,
                        bool useFrozenV4 = false,
                        std::vector<CombatEvalFight> *combatCapture = nullptr) {
    using RT = search::GameAction::RewardsActionType;
    const int healthBefore = search::g_simHealthFailureCount;
    const auto continuationWallStart = std::chrono::steady_clock::now();
    const std::clock_t continuationCpuStart = std::clock();
    OocContinuationCost continuationCost;
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.simulationCountTotal = 0;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    int fights = 0;
    int observedFights = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            // A completed fight's checkpoint is observed only after the normal
            // OOC continuation has reached the following battle. The callback
            // receives a const state and must not consume live RNG.
            if (prefixObserver && fights > observedFights) {
                continuationCost.cpuMs = 1000.0 * (std::clock() - continuationCpuStart) / CLOCKS_PER_SEC;
                continuationCost.wallMs = std::chrono::duration<double, std::milli>(
                    std::chrono::steady_clock::now() - continuationWallStart).count();
                (*prefixObserver)(gc, fights, continuationCost);
                observedFights = fights;
            }
            if (maxFights >= 0 && fights >= maxFights) break;
            const Room room = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSimsSeq && !fightSimsSeq->empty()
                ? (*fightSimsSeq)[std::min(fights, (int)fightSimsSeq->size() - 1)]
                : fightSims(gc, sims);
            BattleContext bc;
            bool passed; int endHp, endMaxHp;
            if (usePredict) {
                bc.init(gc);
                const auto prediction = predictCheckpointFight(gc, bc.encounter);
                passed = prediction.predictedWin;
                endHp = passed ? prediction.endHpIfWin : 0;
                endMaxHp = prediction.maxHp;
                if (!passed) {
                    gc.outcome = GameOutcome::PLAYER_LOSS;
                } else {
                    BattleContext virtualBattle{};
                    virtualBattle.init(gc, bc.encounter);
                    virtualBattle.player.curHp = prediction.endHpIfWin;
                    virtualBattle.outcome = Outcome::PLAYER_VICTORY;
                    virtualBattle.exitBattle(gc);
                }
            } else {
                const std::int64_t simulationsBefore = agent.simulationCountTotal;
                const int fightHealthBefore = search::g_simHealthFailureCount;
                std::optional<CombatEvalFight> captured;
                if (combatCapture) captured = CombatEvalFight{gc.act, gc.floorNum, gc.curRoom, gc.info.encounter, vFeatCsv(gc)};
                {
                    CombatEvalDecisionScope observer(combatCapture != nullptr);
                    agent.playoutBattle(gc, bc);
                    if (captured) {
                        captured->label = combatEvalTerminal(bc, captured->encounter, observer.hooks,
                                                            fightHealthBefore, search::g_simHealthFailureCount);
                        combatCapture->push_back(std::move(*captured));
                    }
                }
                continuationCost.silverSimulations += static_cast<std::uint64_t>(
                    std::max<std::int64_t>(0, agent.simulationCountTotal - simulationsBefore));
                continuationCost.combatDecisions += search::g_silverLiveDiagnostics.decisions;
                continuationCost.transactionSubdecisions += search::g_silverLiveDiagnostics.transactionSubdecisions;
                continuationCost.transactionDecisions += search::g_silverLiveDiagnostics.transactionDecisions;
                passed = bc.outcome == Outcome::PLAYER_VICTORY;
                endHp = passed ? gc.curHp : 0;
                endMaxHp = gc.maxHp;
                bc.exitBattle(gc);
            }
            if (probe) {
                probe->fights.push_back({room, bc.encounter, gc.floorNum, endHp,
                                         endMaxHp, passed});
                if (!probe->nextCombatSeen) {
                    probe->nextCombatSeen = true;
                    probe->nextCombatPassed = passed;
                }
                if (room == Room::ELITE && !probe->nextEliteSeen) {
                    probe->nextEliteSeen = true;
                    probe->nextElitePassed = passed;
                }
                if (room == Room::BOSS && !probe->nextBossSeen) {
                    probe->nextBossSeen = true;
                    probe->nextBossPassed = passed;
                }
            }
            ++fights;
            // This is deliberately after recording the boss outcome: a full-act
            // evaluator stops at the current act's boss rather than leaking a
            // candidate's score into Act+1 rewards/fights.
            if (stopAfterAct > 0 && battleAct == stopAfterAct && room == Room::BOSS) break;
        } else if (useFrozenV4) {
            stepFrozenV4Ooc(gc, agent);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else one_combat::serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF later rest seed=" << gc.seed << " floor=" << gc.floorNum << "\n";
            if (!(g_restWin && one_combat::restWinPolicy(gc))) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.empty()) break;
                actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    if (prefixObserver && fights > observedFights) {
        continuationCost.cpuMs = 1000.0 * (std::clock() - continuationCpuStart) / CLOCKS_PER_SEC;
        continuationCost.wallMs = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - continuationWallStart).count();
        (*prefixObserver)(gc, fights, continuationCost);
    }
    double won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : 0.0;
    double floor = gc.floorNum;
    int bootstrapped = 0;
    if (bootstrap && gc.outcome == GameOutcome::UNDECIDED) {
        const double vf = vStateRaw(gc);
        const double vw = vStateWin(gc);
        if (std::isfinite(vf) && vf >= gc.floorNum && vf <= 60) floor = vf;
        if (std::isfinite(vw) && vw >= 0 && vw <= 1) won = vw;
        bootstrapped = 1;
    }
    const bool survivedH = gc.outcome != GameOutcome::PLAYER_LOSS;
    continuationCost.cpuMs = 1000.0 * (std::clock() - continuationCpuStart) / CLOCKS_PER_SEC;
    continuationCost.wallMs = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - continuationWallStart).count();
    if (finalCost) *finalCost = continuationCost;
    const bool valid = search::isValidTrainingTerminal(
        gc.outcome != GameOutcome::UNDECIDED, healthBefore,
        search::g_simHealthFailureCount,
        bootstrap && gc.outcome == GameOutcome::UNDECIDED);
    if (!valid && t_trainingRunActive) {
        g_trainingHealthFailures += std::max(0, search::g_simHealthFailureCount - healthBefore);
        t_trainingBranchHealthFailures += std::max(0, search::g_simHealthFailureCount - healthBefore);
    }
    // Branch health belongs to this branch, not to the enclosing source run.
    if (probe) probe->completed = valid && gc.outcome != GameOutcome::UNDECIDED;
    t_curPath = nullptr;
    return {valid ? won : 0.0, valid ? floor : 0.0,
            valid ? (double)gc.curHp : 0.0, valid ? bootstrapped : -1, valid,
            valid && survivedH};
}

// GameContext normally shares its Map through a shared_ptr. A counterfactual may
// reach the next act and regenerate that map; detach it so speculative branches
// cannot overwrite the live run's current-act map.
static GameContext detachedCounterfactualCopy(const GameContext &gc) {
    GameContext copy = gc;
    if (gc.map) copy.map = std::make_shared<Map>(*gc.map);
    return copy;
}

// Draw one encounter from the game pool.  We use this rather than an equal
// encounter average: Slay the Spire's pools are weighted, and the no-repeat
// rule makes a sequence's conditional distribution depend on its prior two
// encounters.
static MonsterEncounter sampleEncounterWeighted(const MonsterEncounter *pool,
                                                const float *weights, int count,
                                                Random &rng) {
    const float roll = rng.random();
    float cumulative = 0.0f;
    for (int i = 0; i < count; ++i) {
        cumulative += weights[i];
        if (roll < cumulative) return pool[i];
    }
    return pool[count - 1];
}

// Replace only the unseen normal/elite encounter queues in a copied run.  A
// live GameContext has a concrete queue for its seed, but that information is
// hidden from a player.  Sampling this conditional queue is therefore the
// appropriate information-set evaluation for a card pick.  The act boss is
// deliberately NOT resampled: it is chosen at act generation and visible to
// the player, so every candidate must evaluate the known gc.boss.  Map layout
// and all non-combat RNG stay fixed so alternatives differ principally in
// combat fit.
static void resampleRemainingActEncounters(GameContext &gc, std::uint64_t branchSeed) {
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    Random rng(branchSeed);
    const int weakCount = gc.act == 1 ? 3 : 2;
    for (int i = gc.monsterListOffset; i < (int)gc.monsterList.size(); ++i) {
        const bool weak = i < weakCount;
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        MonsterEncounter draw;
        do {
            draw = sampleEncounterWeighted(pool, weights, count, rng);
        } while ((i > 0 && draw == gc.monsterList[i - 1]) ||
                 (i > 1 && draw == gc.monsterList[i - 2]));
        gc.monsterList[i] = draw;
    }
    for (int i = gc.eliteMonsterListOffset; i < (int)gc.eliteMonsterList.size(); ++i) {
        MonsterEncounter draw;
        do {
            draw = MonsterEncounterPool::elites[actIdx][rng.random(2)];
        } while (i > 0 && draw == gc.eliteMonsterList[i - 1]);
        gc.eliteMonsterList[i] = draw;
    }
}

// Death itself is a discontinuity, and HP is most valuable near the danger
// boundary rather than linearly.  This utility is deliberately encounter-agnostic:
// a hard fight matters because it lowers survival/HP in the simulations, not
// because we gave it a hand-authored tier.
static double nonlinearHpSafety(int hp, int maxHp) {
    const double fraction = maxHp > 0 ? (double)hp / maxHp : 0.0;
    return 1.0 / (1.0 + std::exp(-(fraction - 0.35) / 0.10));
}

static double allActFightUtility(const FutureFightProbe &probe, int decisionFloor) {
    double utility = 0.0;
    for (const auto &f : probe.fights) {
        const int floorsAway = std::max(0, f.floor - decisionFloor);
        const double urgency = std::pow(g_actFightProbeFloorDecay, floorsAway);
        // Reaching this record is its occurrence indicator.  Averaging over
        // sampled queues thus estimates P(occurs) * P(survives | occurs), while
        // the sigmoid values a post-fight safety buffer without treating HP as
        // a linear resource.
        utility += urgency * (f.passed ? nonlinearHpSafety(f.hp, f.maxHp) : -1.0);
    }
    return utility;
}

// Full-act, encounter-distribution card policy.  Candidates are card offers
// plus Skip.  Every candidate sees the same sampled hidden encounter queues
// (common random numbers), follows the actual selected map route to the boss,
// and is ranked solely by allActFightUtility -- no V/card scorer is queried for
// this immediate decision.
bool actFightProbeDraftPolicy(GameContext &gc) {
    if (!g_actFightProbeDraft) return false;
    using RT = search::GameAction::RewardsActionType;
    auto &r = gc.info.rewardsContainer;
    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    while (r.cardRewardCount > 0) {
        const int rIdx = r.cardRewardCount - 1;
        const int nCards = r.cardRewards[rIdx].size();
        double bestScore = -1e100;
        int bestIdx = 5;  // the simulator evaluates Skip as a normal candidate
        // Diagnostic: compute the baseline floor-model pick for comparison
        int baselinePick = 5;
        if (g_actFightProbeTrace)
            baselinePick = nativeFloorCardPick(gc, rIdx);
        // Per-candidate per-future probes saved for trace breakdown
        std::vector<std::vector<FutureFightProbe>> traceFutureProbes;
        if (g_actFightProbeTrace)
            traceFutureProbes.resize(nCards + 1);
        std::vector<double> candidateScores(nCards + 1, 0.0);
        for (int cand = 0; cand <= nCards; ++cand) {
            const int cardIdx = cand < nCards ? cand : 5;
            double total = 0.0;
            for (int f = 0; f < g_actFightProbeFutures; ++f) {
                // Depends on the decision/future but never on candidate: exact
                // same encounter possibilities for each offered card.
                const std::uint64_t branchSeed = gc.seed
                    ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                    ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(gc.floorNum + 31 * rIdx));
                GameContext branch = detachedCounterfactualCopy(gc);
                search::GameAction(RT::CARD, rIdx, cardIdx).execute(branch);
                resampleRemainingActEncounters(branch, branchSeed);
                FutureFightProbe probe;
                finishOocCounterfactual(std::move(branch), g_actFightProbeSims,
                                        branchSeed, basePath, -1, false, &probe, gc.act,
                                        nullptr, g_actFightProbePredict);
                total += allActFightUtility(probe, gc.floorNum);
                if (g_actFightProbeTrace)
                    traceFutureProbes[cand].push_back(probe);
            }
            const double score = total / std::max(1, g_actFightProbeFutures);
            candidateScores[cand] = score;
            if (score > bestScore) { bestScore = score; bestIdx = cardIdx; }
        }
        if (g_actFightProbeTrace) {
            // Consecutive-oracle-override counter
            static int consecutiveOverrideCount = 0;
            const bool oracleOverrides = (bestIdx != baselinePick);
            if (oracleOverrides) ++consecutiveOverrideCount;
            else consecutiveOverrideCount = 0;
            std::cerr << "[act-fight draft floor=" << gc.floorNum << " act=" << gc.act
                      << " baseline=" << (baselinePick == 5 ? "skip" : r.cardRewards[rIdx][baselinePick].getName())
                      << "(" << baselinePick << ")"
                      << " overrides=" << consecutiveOverrideCount << "]\n  scores:";
            for (int cand = 0; cand <= nCards; ++cand) {
                if (cand == nCards) std::cerr << " skip=" << candidateScores[cand];
                else std::cerr << ' ' << r.cardRewards[rIdx][cand].getName()
                               << '=' << candidateScores[cand];
            }
            std::cerr << " -> " << (bestIdx == 5 ? "skip" : r.cardRewards[rIdx][bestIdx].getName());
            if (oracleOverrides)
                std::cerr << " OVERRIDES";
            std::cerr << '\n';
            // Per-future fight breakdown for the winning candidate
            const int winCand = (bestIdx == 5) ? nCards : bestIdx;
            std::cerr << "  futures=" << g_actFightProbeFutures
                      << " floor-dcy=" << g_actFightProbeFloorDecay << ':';
            for (int f = 0; f < (int)traceFutureProbes[winCand].size()
                              && f < g_actFightProbeFutures; ++f) {
                const auto &probe = traceFutureProbes[winCand][f];
                double futUtil = allActFightUtility(probe, gc.floorNum);
                std::cerr << (f ? " |" : " [") << "f" << f
                          << " util=" << futUtil;
                for (const auto &fight : probe.fights) {
                    const int floorsAway = std::max(0, fight.floor - gc.floorNum);
                    const double urgency = std::pow(g_actFightProbeFloorDecay, floorsAway);
                    const double safety = fight.passed
                        ? nonlinearHpSafety(fight.hp, fight.maxHp) : -1.0;
                    std::cerr << " " << (fight.passed ? "W" : "L")
                              << " f" << fight.floor
                              << " " << monsterEncounterEnumNames[(int)fight.encounter]
                              << " hp" << fight.hp << "/" << fight.maxHp
                              << " d" << floorsAway
                              << " u" << urgency
                              << " s" << safety;
                }
                std::cerr << ']';
            }
            std::cerr << '\n';
        }
        // Margin gate: if the oracle isn't confident enough about its best pick,
        // fall through to the baseline card policy for this rewards screen.
        if (g_actFightProbeMargin > 0.0) {
            double secondScore = -1e100;
            for (int cand = 0; cand <= nCards; ++cand) {
                const int cardIdx = cand < nCards ? cand : 5;
                if (cardIdx == bestIdx) continue;
                if (candidateScores[cand] > secondScore) secondScore = candidateScores[cand];
            }
            const double margin = bestScore - secondScore;
            if (margin < g_actFightProbeMargin) {
                if (g_actFightProbeTrace)
                    std::cerr << "  margin=" << margin << " < " << g_actFightProbeMargin
                              << " -> fallback\n";
                t_curPath = savedPath;
                return false;
            }
            if (g_actFightProbeTrace)
                std::cerr << "  margin=" << margin << " >= " << g_actFightProbeMargin << " fire\n";
        }
        search::GameAction(RT::CARD, rIdx, bestIdx).execute(gc);
    }
    t_curPath = savedPath;
    return true;
}

struct EncounterOption {
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
};

// Conditional enemy pools at a concrete combat checkpoint. Normal and elite
// entries retain the game's no-repeat constraints; event fights are fixed by
// their event option. This gives a probability distribution without a hand-made
// difficulty tier.
static std::vector<EncounterOption> possibleEncounterOptions(const GameContext &gc) {
    std::vector<EncounterOption> out;
    const int actIdx = std::max(0, std::min(2, gc.act - 1));
    if (gc.curRoom == Room::MONSTER) {
        const int used = gc.monsterListOffset - 1; // battle already consumed this queue slot
        const bool weak = used < (gc.act == 1 ? 3 : 2);
        const MonsterEncounter *pool = weak ? MonsterEncounterPool::weakEnemies[actIdx]
                                            : MonsterEncounterPool::strongEnemies[actIdx];
        const float *weights = weak ? MonsterEncounterPool::weakWeights[actIdx]
                                    : MonsterEncounterPool::strongWeights[actIdx];
        const int count = weak ? MonsterEncounterPool::weakCount[actIdx]
                               : MonsterEncounterPool::strongCount[actIdx];
        double total = 0.0;
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) total += weights[i];
        }
        for (int i = 0; i < count; ++i) {
            const bool repeat1 = used > 0 && pool[i] == gc.monsterList[used - 1];
            const bool repeat2 = used > 1 && pool[i] == gc.monsterList[used - 2];
            if (!repeat1 && !repeat2) out.push_back({pool[i], weights[i] / total});
        }
    } else if (gc.curRoom == Room::ELITE) {
        const int used = gc.eliteMonsterListOffset - 1;
        const MonsterEncounter prev = used > 0 ? gc.eliteMonsterList[used - 1] : MonsterEncounter::INVALID;
        int count = 0;
        for (int i = 0; i < 3; ++i) if (MonsterEncounterPool::elites[actIdx][i] != prev) ++count;
        for (int i = 0; i < 3; ++i) {
            const MonsterEncounter e = MonsterEncounterPool::elites[actIdx][i];
            if (e != prev) out.push_back({e, 1.0 / count});
        }
    } else if (gc.curRoom == Room::BOSS) {
        // Unlike the normal and elite queues, the boss was selected when the
        // act was generated and is public information.  Do not average in
        // alternative bosses the player will never face.
        out.push_back({gc.boss, 1.0});
    } else {
        out.push_back({gc.info.encounter, 1.0});
    }
    return out;
}

// One sampled progression trunk per candidate/future provides realistic deck,
// relic and HP checkpoints. At each reached combat, every possible enemy is
// fought independently from that same pre-fight state; this avoids a recursive
// full-act continuation for each action/enemy combination.
struct CheckpointFightComponent {
    int floor = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    double probability = 0.0;
    bool passed = false;
    int hp = 0;
    int maxHp = 1;
    double safety = 0.0;
    double contribution = 0.0;
    int sims = 0;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter) {
    BattleContext bc{};
    bc.init(gc, encounter);
    const auto prediction = g_actFightProbePredictNet.predictOutcome(bc);
    const int maxHp = std::max(1, bc.player.maxHp);
    return {
        std::max(0.0, std::min(1.0, prediction.winProbability)),
        std::max(1, std::min(maxHp, (int)std::lround(prediction.endHpFractionIfWin * maxHp))),
        maxHp,
        prediction.winProbability >= g_actFightProbePredictWinThreshold,
    };
}

// Complete a battle without a combat search.  BattleContext::exitBattle still
// takes the ordinary victory route (including Burning Blood and reward setup),
// but no cards, potions, or combat RNG are consumed.  That missing combat-side
// transition state is the known approximation of this fast benchmark mode.
static bool applyPredictedCheckpointFight(GameContext &gc, MonsterEncounter encounter,
                                          PredictedCheckpointFight *out = nullptr) {
    const auto prediction = predictCheckpointFight(gc, encounter);
    if (out) *out = prediction;
    if (!prediction.predictedWin) {
        gc.outcome = GameOutcome::PLAYER_LOSS;
        return false;
    }
    BattleContext virtualBattle{};
    virtualBattle.init(gc, encounter);
    virtualBattle.player.curHp = prediction.endHpIfWin;
    virtualBattle.outcome = Outcome::PLAYER_VICTORY;
    virtualBattle.exitBattle(gc);
    return gc.outcome == GameOutcome::UNDECIDED;
}

struct OocEncounterPrediction {
    double winProbability = -1.0;
    double hpFraction = 0.0;
};

static std::vector<OocEncounterPrediction> queryOocEncounterPredictions(
        const std::string &rootState, std::uint32_t actionBits, int screen, int act,
        const std::vector<MonsterEncounter> &encounters) {
    std::ostringstream req;
    req << "OE;" << actionBits << ';';
    for (int i = 0; i < (int)encounters.size(); ++i) {
        if (i) req << ',';
        req << (int)encounters[i];
    }
    req << ';' << screen << ';' << act << ';' << rootState << '\n';
    std::istringstream in(vTransact(req.str()));
    std::vector<OocEncounterPrediction> out;
    for (int i = 0; i < (int)encounters.size(); ++i) {
        std::string token;
        if (!(in >> token)) break;
        const auto comma = token.find(',');
        if (comma == std::string::npos) break;
        out.push_back({std::atof(token.substr(0, comma).c_str()),
                       std::atof(token.substr(comma + 1).c_str())});
    }
    return out;
}

static double checkpointedActFightUtility(GameContext gc, int sims, std::uint64_t agentSeed,
                                           PathHistory path, int decisionFloor,
                                           const std::string &rootState,
                                           std::uint32_t rootActionBits,
                                           int rootScreen, int rootAct,
                                           std::vector<CheckpointFightComponent> *components = nullptr) {
    search::ScumSearchAgent2 trunkAgent;
    trunkAgent.simulationCountBase = sims;
    trunkAgent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    double utility = 0.0;
    int steps = 0;
    int checkpointCount = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED && gc.act >= 1 && gc.act <= 3) {
        if (++steps > 160) {
            std::cerr << "[checkpoint trunk safety stop floor=" << gc.floorNum
                      << " screen=" << (int)gc.screenState << "]\n";
            break;
        }
        if (g_actFightProbeTrace)
            std::cerr << "[checkpoint trunk step=" << steps << " floor=" << gc.floorNum
                      << " room=" << (int)gc.curRoom << " screen=" << (int)gc.screenState << "]\n";
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;
            const Room room = gc.curRoom;
            const int floor = gc.floorNum;
            const int checkpointSims = actFightProbeCheckpointSims(sims, checkpointCount);
            double expected = 0.0;
            const auto options = possibleEncounterOptions(gc);
            std::vector<MonsterEncounter> optionEncounters;
            for (const auto &option : options) optionEncounters.push_back(option.encounter);
            const bool useEncounterNN = g_actFightProbeEncounterNN && checkpointCount == 0
                                     && !rootState.empty() && !optionEncounters.empty();
            const auto encounterPredictions = useEncounterNN
                ? queryOocEncounterPredictions(rootState, rootActionBits, rootScreen, rootAct,
                                               optionEncounters)
                : std::vector<OocEncounterPrediction>{};
            const bool lastCheckpoint = g_actFightProbeTermWin > 0.0
                && g_actFightProbeMaxCheckpoints > 0
                && checkpointCount + 1 >= g_actFightProbeMaxCheckpoints;
            double expectedWin = 0.0;
            for (int i = 0; i < (int)options.size(); ++i) {
                GameContext local = detachedCounterfactualCopy(gc);
                bool passed = false;
                int hp = local.curHp, maxHp = local.maxHp;
                double safety = -1.0;
                if (useEncounterNN && i < (int)encounterPredictions.size()
                    && encounterPredictions[i].winProbability >= 0.0) {
                    const auto &prediction = encounterPredictions[i];
                    passed = prediction.winProbability >= g_actFightProbePredictWinThreshold;
                    hp = std::max(1, std::min(local.maxHp,
                        (int)std::lround(prediction.hpFraction * local.maxHp)));
                    maxHp = std::max(1, local.maxHp);
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else if (g_actFightProbePredict) {
                    const auto prediction = predictCheckpointFight(local, options[i].encounter);
                    passed = prediction.predictedWin;
                    hp = prediction.endHpIfWin;
                    maxHp = prediction.maxHp;
                    // The model heads predict P(win) and E[end HP | win].
                    // Keep the oracle's loss penalty in the expected utility.
                    safety = prediction.winProbability * nonlinearHpSafety(hp, maxHp)
                           + (1.0 - prediction.winProbability) * -1.0;
                } else {
                    search::ScumSearchAgent2 fightAgent;
                    fightAgent.simulationCountBase = fightSims(local, checkpointSims);
                    fightAgent.rng = std::default_random_engine(
                        agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1))
                                  ^ (0xa0761d6478bd642fULL * (std::uint64_t)(floor + 1)));
                    BattleContext bc{}; bc.init(local, options[i].encounter);
                    fightAgent.playoutBattle(bc); bc.exitBattle(local);
                    passed = bc.outcome == Outcome::PLAYER_VICTORY;
                    hp = local.curHp;
                    maxHp = local.maxHp;
                    safety = passed ? nonlinearHpSafety(hp, maxHp) : -1.0;
                    // Terminal pricing: the post-fight branch state (HP already
                    // updated) is priced by the native win model in P(win)
                    // units, scale-compatible with the HP-safety sigmoid.
                    if (lastCheckpoint && passed && g_winNet.ok) {
                        const double pw = winNetPredict(richFeatureVec(local));
                        expectedWin += options[i].probability
                            * (local.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : pw);
                    }
                }
                expected += options[i].probability * safety;
                if (components) components->push_back({
                    floor, room, options[i].encounter, options[i].probability, passed,
                    hp, maxHp, safety,
                    std::pow(g_actFightProbeFloorDecay, std::max(0, floor - decisionFloor))
                        * options[i].probability * safety,
                    (g_actFightProbePredict || useEncounterNN) ? 0 : fightSims(local, checkpointSims),
                });
            }
            const double decay = std::pow(g_actFightProbeFloorDecay,
                                          std::max(0, floor - decisionFloor));
            utility += decay * expected;
            if (lastCheckpoint)
                utility += decay * g_actFightProbeTermWin * expectedWin;
            ++checkpointCount;

            // The final scored checkpoint needs no actual trunk battle: no
            // later deck/HP state can contribute to a capped objective.
            if (g_actFightProbeMaxCheckpoints > 0
                && checkpointCount >= g_actFightProbeMaxCheckpoints) break;

            // Advance only this one sampled trunk; future checkpoints are then
            // naturally weighted by the probability that the trunk reaches them.
            if (g_actFightProbePredict) {
                if (!applyPredictedCheckpointFight(gc, gc.info.encounter)) break;
            } else {
                trunkAgent.simulationCountBase = fightSims(gc, checkpointSims);
                // g_potionKeepValue is process-global. With saving disabled (the
                // deployed/pilot setting) its default is the same fixed value, so
                // avoid a needless shared write while branches run in parallel.
                // Dynamic potion saving remains sequential until that setting is
                // made thread-local in the combat searcher.
                if (g_potionSave) search::g_potionKeepValue = potionKeepValue(gc);
                BattleContext actual{}; actual.init(gc); trunkAgent.playoutBattle(actual); actual.exitBattle(gc);
            }
            if (room == Room::BOSS) break;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else one_combat::serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
                search::GameAction(2, 0).execute(gc);   // recall: take the ruby key
            } else {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (actions.empty()) break;
                actions.front().execute(gc);
            }
        } else {
            trunkAgent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    return utility;
}

static std::string csvQuote(const std::string &s) {
    std::string out = "\"";
    for (const char c : s) {
        if (c == '\"') out += "\"\"";
        else out += c;
    }
    return out + "\"";
}

static std::string actionDescription(const search::GameAction &action, const GameContext &gc) {
    std::ostringstream out;
    action.printDesc(out, gc);
    // A few event actions have no human-readable printer; retain their stable
    // encoded action bits rather than silently logging an empty legal action.
    return out.str().empty() ? "bits=" + std::to_string(action.bits) : out.str();
}

static std::string joinLegalActions(const std::vector<search::GameAction> &actions,
                                    const GameContext &gc) {
    std::ostringstream out;
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) out << " | ";
        out << i << ':' << actionDescription(actions[i], gc);
    }
    return out.str();
}

// Paired OOC supervision at the next real combat.  Unlike the all-act future
// evaluator, this deliberately stops each counterfactual branch at its first
// battle.  The branch then has two labels: what the ordinary baseline does
// against the concrete encounter, and the weighted result of fighting every
// encounter still possible at that checkpoint.
static std::string oocNextCombatHeader() {
    return "seed,decisionIdx,actionIdx,actionBits,action,legalActions,screen,act,floor,futures,"
           "actualWin,actualHp,allEncounterWin,allEncounterHp,encounterLabels,stateFeatures";
}

struct EncounterLabel {
    double probability = 0.0;
    double weightedWin = 0.0;
    double weightedHp = 0.0;
};

struct NextCombatLabel {
    double actualWin = 0.0, actualHp = 0.0;
    double allWin = 0.0, allHp = 0.0;
    int seen = 0;
    std::map<int, EncounterLabel> encounterLabels;
};

static bool advanceOocToNextBattle(GameContext &gc, int sims, std::uint64_t agentSeed,
                                   PathHistory path, std::ostringstream *failureTrace=nullptr) {
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    for (int steps = 0; steps < 180 && gc.outcome == GameOutcome::UNDECIDED; ++steps) {
        path.update(gc);
        const int beforeScreen=(int)gc.screenState,beforeEvent=(int)gc.curEvent,beforeHp=gc.curHp;
        std::uint32_t executed=UINT32_MAX;
        if(failureTrace)search::g_onGameActionExecute=[&](std::uint32_t bits,const GameContext*target){if(target==&gc&&executed==UINT32_MAX)executed=bits;};
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if(failureTrace)search::g_onGameActionExecute={};
            t_curPath = nullptr;
            return true;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            one_combat::serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // handled by the deployed rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
        if(failureTrace){search::g_onGameActionExecute={};*failureTrace<<" step="<<steps<<":screen="<<beforeScreen<<",event="<<beforeEvent<<",actionBits="<<executed<<",hp="<<beforeHp<<">"<<gc.curHp<<",finalScreen="<<(int)gc.screenState<<",outcome="<<(int)gc.outcome;}
    }
    if(failureTrace)search::g_onGameActionExecute={};
    t_curPath = nullptr;
    return false;
}

static NextCombatLabel labelNextCombat(GameContext branch, int branchSims,
                                       std::uint64_t agentSeed) {
    NextCombatLabel label;
    PathHistory emptyPath;
    if (!advanceOocToNextBattle(branch, branchSims, agentSeed, emptyPath)) return label;
    label.seen = 1;
    const auto options = possibleEncounterOptions(branch);
    double weight = 0.0;
    for (int i = 0; i < (int)options.size(); ++i) {
        GameContext local = detachedCounterfactualCopy(branch);
        search::ScumSearchAgent2 fightAgent;
        fightAgent.simulationCountBase = fightSims(local, branchSims);
        fightAgent.rng = std::default_random_engine(
            agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1)));
        BattleContext bc{};
        bc.init(local, options[i].encounter);
        fightAgent.playoutBattle(bc);
        bc.exitBattle(local);
        const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
        const double hp = won ? local.curHp : 0.0;
        const double p = options[i].probability;
        label.allWin += p * (won ? 1.0 : 0.0);
        label.allHp += p * hp;
        weight += p;
        auto &el = label.encounterLabels[(int)options[i].encounter];
        el.probability += p;
        el.weightedWin += p * (won ? 1.0 : 0.0);
        el.weightedHp += p * hp;
    }
    if (weight > 0.0) {
        label.allWin /= weight;
        label.allHp /= weight;
    }

    // Concrete-encounter label from the ordinary baseline continuation.  This
    // is intentionally separate from the encounter-distribution label above.
    GameContext actual = detachedCounterfactualCopy(branch);
    search::ScumSearchAgent2 actualAgent;
    actualAgent.simulationCountBase = fightSims(actual, branchSims);
    actualAgent.rng = std::default_random_engine(agentSeed ^ 0xa0761d6478bd642fULL);
    BattleContext actualBattle{};
    actualBattle.init(actual);
    actualAgent.playoutBattle(actualBattle);
    actualBattle.exitBattle(actual);
    label.actualWin = actualBattle.outcome == Outcome::PLAYER_VICTORY ? 1.0 : 0.0;
    label.actualHp = label.actualWin ? actual.curHp : 0.0;
    return label;
}

static std::string runOocNextCombatSeed(std::uint64_t seed, int outerSims, int asc,
                                         int branchSims, int futures) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);
    PathHistory path;
    t_curPath = &path;
    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<search::GameAction> sampledActions;
    int sampledDecision = -1;
    int eligible = 0, decisionIdx = 0;
    int fightsLost = 0, fightsTotal = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{}; bc.init(gc);
            agent.playoutBattle(bc);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) ++fightsLost;
            bc.exitBattle(gc);
        } else {
            const auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledActions = actions;
                    sampledDecision = decisionIdx;
                }
                ++decisionIdx;
            }
            if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14)
                search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
            else if (gc.screenState == ScreenState::REWARDS) {
                auto &r = gc.info.rewardsContainer;
                if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
                else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
                else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                else                            one_combat::serverCardRewardPolicy(gc);
            } else if (gc.screenState == ScreenState::SHOP_ROOM) one_combat::shopVPolicy(gc);
            else if (inRemoveSelect) one_combat::removeSelectVPolicy(gc);
            else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {}
            else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                     && gc.info.selectScreenType == CardSelectScreenType::UPGRADE)
                one_combat::upgradeSelectWinPolicy(gc);
            else agent.stepOutOfCombatPolicy(gc);
        }
    }
    std::ostringstream out;
    if (sampled) {
        const std::string state = richRow(*sampled, sampledPath);
        const std::string legal = joinLegalActions(sampledActions, *sampled);
        const int nf = std::max(1, futures);
        for (int a = 0; a < (int)sampledActions.size(); ++a) {
            NextCombatLabel total;
            for (int f = 0; f < nf; ++f) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                sampledActions[a].execute(branch);
                const auto label = labelNextCombat(
                    std::move(branch), branchSims,
                    seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                         ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(sampledDecision + 31)));
                total.seen += label.seen;
                total.actualWin += label.actualWin;
                total.actualHp += label.actualHp;
                total.allWin += label.allWin;
                total.allHp += label.allHp;
                for (const auto &[encounter, el] : label.encounterLabels) {
                    auto &dst = total.encounterLabels[encounter];
                    dst.probability += el.probability;
                    dst.weightedWin += el.weightedWin;
                    dst.weightedHp += el.weightedHp;
                }
            }
            std::ostringstream encounterLabels;
            for (const auto &[encounter, el] : total.encounterLabels) {
                if (encounterLabels.tellp() > 0) encounterLabels << '|';
                const double prob = el.probability / nf;
                const double win = el.probability > 0.0 ? el.weightedWin / el.probability : 0.0;
                const double hp = el.probability > 0.0 ? el.weightedHp / el.probability : 0.0;
                encounterLabels << encounter << ':' << prob << ':' << win << ':' << hp;
            }
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledActions[a].bits
                << ',' << csvQuote(actionDescription(sampledActions[a], *sampled)) << ','
                << csvQuote(legal) << ',' << (int)sampled->screenState << ',' << sampled->act << ','
                << sampled->floorNum << ',' << nf << ',' << total.actualWin/nf << ','
                << total.actualHp/nf << ',' << total.allWin/nf << ',' << total.allHp/nf << ','
                << csvQuote(encounterLabels.str()) << ','
                << csvQuote(state) << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void oocNextCombatGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                             std::uint64_t seedOffset, int branchSims, int futures) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << oocNextCombatHeader() << '\n'; out.flush(); }
    std::cout << "oocnextgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " -> " << outfile << '\n';
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string rows = runOocNextCombatSeed(seedOffset+s, outerSims, asc,
                                                       branchSims, futures);
        #pragma omp critical(ooc_next_write)
        { out << rows; out.flush(); }
    }
}

static std::string serializeFightComponents(const std::vector<std::vector<CheckpointFightComponent>> &all) {
    std::ostringstream out;
    for (int future = 0; future < (int)all.size(); ++future) {
        if (future) out << ';';
        out << "f" << future << '=';
        for (int i = 0; i < (int)all[future].size(); ++i) {
            if (i) out << '|';
            const auto &c = all[future][i];
            out << c.floor << ':' << roomStrings[(int)c.room] << ':'
                << monsterEncounterStrings[(int)c.encounter]
                << ":p=" << c.probability << ":win=" << c.passed
                << ":hp=" << c.hp << '/' << c.maxHp
                << ":safety=" << c.safety << ":contrib=" << c.contribution
                << ":sims=" << c.sims;
        }
    }
    return out.str();
}

static bool initActFightProbeLog() {
    if (g_actFightProbeLogPath.empty()) return true;
    std::ifstream existing(g_actFightProbeLogPath);
    const bool needsHeader = !existing.good() || existing.peek() == std::ifstream::traits_type::eof();
    g_actFightProbeLog.open(g_actFightProbeLogPath, std::ios::app);
    if (!g_actFightProbeLog.is_open()) {
        std::cerr << "[all-acts checkpoint teacher log failed to open: " << g_actFightProbeLogPath << "]\n";
        return false;
    }
    if (needsHeader) {
        // stateFeatures is vFeatCsv(gc), whose stable schema is richStateHeader().
        g_actFightProbeLog
            << "seed,decisionIdx,act,floor,mapX,mapY,screen,knownBoss,maxCheckpoints,checkpointSims,actionIdx,action,legalActions,"
               "futures,futureSeeds,futureUtilities,meanUtility,sampleSd,standardError,"
               "checkpointComponents,stateFeatures\n";
        g_actFightProbeLog.flush();
    }
    std::cout << "[all-acts checkpoint teacher log: " << g_actFightProbeLogPath << "]\n";
    return true;
}

static void appendActFightProbeLog(const GameContext &gc, int decisionIdx,
                                   const std::vector<search::GameAction> &actions, int actionIdx,
                                   const std::vector<std::uint64_t> &futureSeeds,
                                   const std::vector<double> &utilities,
                                   const std::vector<std::vector<CheckpointFightComponent>> &components) {
    if (!g_actFightProbeLog.is_open()) return;
    double mean = 0.0;
    for (const double utility : utilities) mean += utility;
    mean /= std::max(1, (int)utilities.size());
    double sq = 0.0;
    for (const double utility : utilities) sq += (utility - mean) * (utility - mean);
    const double sampleSd = utilities.size() > 1 ? std::sqrt(sq / (utilities.size() - 1)) : 0.0;
    const double standardError = utilities.empty() ? 0.0 : sampleSd / std::sqrt((double)utilities.size());

    std::ostringstream seeds, values;
    for (int f = 0; f < (int)futureSeeds.size(); ++f) {
        if (f) { seeds << ';'; values << ';'; }
        seeds << futureSeeds[f];
        values << utilities[f];
    }
    const std::string action = actionDescription(actions[actionIdx], gc);
    std::lock_guard<std::mutex> lock(g_actFightProbeLogMutex);
    g_actFightProbeLog
        << gc.seed << ',' << decisionIdx << ',' << gc.act << ',' << gc.floorNum << ','
        << gc.curMapNodeX << ',' << gc.curMapNodeY << ',' << (int)gc.screenState << ','
        << csvQuote(monsterEncounterStrings[(int)gc.boss]) << ',' << g_actFightProbeMaxCheckpoints << ','
        << csvQuote(actFightProbeCheckpointSimsCsv()) << ',' << actionIdx << ','
        << csvQuote(action) << ',' << csvQuote(joinLegalActions(actions, gc)) << ','
        << utilities.size() << ',' << csvQuote(seeds.str()) << ',' << csvQuote(values.str()) << ','
        << mean << ',' << sampleSd << ',' << standardError << ','
        << csvQuote(serializeFightComponents(components)) << ',' << csvQuote(vFeatCsv(gc)) << '\n';
    g_actFightProbeLog.flush();
}

// All-acts experiment: extend the checkpointed objective from card rewards to
// every legal strategic action in Acts 1--3. This includes boss-relic choices:
// their resulting next-act state is scored at its next combat checkpoints.
bool actFightProbeAllOocPolicy(GameContext &gc) {
    if (!g_actFightProbeAllOoc || gc.act < 1 || gc.act > 3) return false;
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return false;

    const PathHistory *const savedPath = t_curPath;
    const PathHistory basePath = savedPath ? *savedPath : PathHistory{};
    const int decisionIdx = t_actFightProbeDecisionIdx++;
    double bestScore = -1e100;
    int best = -1;
    std::vector<double> scores(actions.size(), -1e100);
    std::vector<bool> valid(actions.size(), false);
    for (int a = 0; a < (int)actions.size(); ++a) valid[a] = actions[a].isValidAction(gc);

    struct BranchResult {
        std::uint64_t seed = 0;
        double utility = 0.0;
        std::vector<CheckpointFightComponent> components;
    };
    const int futures = g_actFightProbeFutures;
    std::vector<BranchResult> branches(actions.size() * futures);
    const bool parallelBranches = g_actFightProbeParallelBranches && !g_actFightProbeTrace
                                  && !g_potionSave;

    // Each branch owns its GameContext, RNG, combat searchers, TCP connection
    // (t_vSock is thread-local), and output slot.  Candidate-independent seeds
    // preserve common random numbers exactly as in the serial oracle.
    #pragma omp parallel for schedule(dynamic) if(parallelBranches)
    for (int task = 0; task < (int)branches.size(); ++task) {
        const int a = task / futures;
        const int f = task % futures;
        t_actFightProbeActionIdx = a;
        t_actFightProbeFutureIdx = f;
        const std::uint64_t branchSeed = gc.seed
            ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
            ^ (0x94d049bb133111ebULL * (std::uint64_t)(gc.floorNum + 97 * gc.curMapNodeY));
        BranchResult &result = branches[task];
        result.seed = branchSeed;
        if (!valid[a]) continue;
        GameContext branch = detachedCounterfactualCopy(gc);
        // Resample before the immediate action: a map choice can create its
        // next battle immediately, and it is hidden information too.
        resampleRemainingActEncounters(branch, branchSeed);
        actions[a].execute(branch);
        result.utility = checkpointedActFightUtility(
            std::move(branch), g_actFightProbeSims, branchSeed, basePath, gc.floorNum,
            vFeatCsv(gc), actions[a].bits, (int)gc.screenState, gc.act,
            &result.components);
    }

    // A serial branch temporarily installs its copied path for server feature
    // parity and clears it on return. Restore the live path before emitting the
    // teacher state/log rows below.
    t_curPath = savedPath;

    // Reduce in fixed action/future order. This retains deterministic scores,
    // logs, and tie-breaking independent of OpenMP scheduling.
    for (int a = 0; a < (int)actions.size(); ++a) {
        if (!valid[a]) continue;
        double total = 0.0;
        std::vector<std::uint64_t> futureSeeds;
        std::vector<double> futureUtilities;
        std::vector<std::vector<CheckpointFightComponent>> components;
        for (int f = 0; f < futures; ++f) {
            const BranchResult &result = branches[a * futures + f];
            futureSeeds.push_back(result.seed);
            futureUtilities.push_back(result.utility);
            components.push_back(result.components);
            total += result.utility;
        }
        scores[a] = total / std::max(1, futures);
        appendActFightProbeLog(gc, decisionIdx, actions, a, futureSeeds, futureUtilities, components);
        if (scores[a] > bestScore) { bestScore = scores[a]; best = a; }
    }
    if (best < 0) { t_curPath = savedPath; return false; }
    if (g_actFightProbeMargin > 0.0) {
        double second = -1e100;
        for (int a = 0; a < (int)actions.size(); ++a) {
            if (!valid[a] || a == best) continue;
            if (scores[a] > second) second = scores[a];
        }
        if (bestScore - second < g_actFightProbeMargin) {
            if (g_actFightProbeTrace)
                std::cerr << "[all-ooc act-fight margin " << bestScore - second
                          << " < " << g_actFightProbeMargin << " -> fallback]\n";
            t_curPath = savedPath;
            return false;
        }
    }
    if (g_actFightProbeTrace) {
        std::cerr << "[all-ooc act-fight floor=" << gc.floorNum << " screen="
                  << (int)gc.screenState << ']';
        for (int a = 0; a < (int)actions.size(); ++a) {
            std::ostringstream desc; actions[a].printDesc(desc, gc);
            std::cerr << ' ' << desc.str() << '=' << scores[a];
        }
        std::cerr << " -> "; actions[best].printDesc(std::cerr, gc); std::cerr << '\n';
    }
    actions[best].execute(gc);
    t_curPath = savedPath;
    return true;
}

// ---------------------------------------------------------------------------
// PAIRED PATH COUNTERFACTUALS: uniformly reservoir-sample one genuine branching
// map decision from each source run, then finish every legal child from the
// identical parent state with common agent/game RNG. This supplies direct route
// action values rather than trying to infer causal alternatives from trajectory
// state values generated by the heuristic policy.
static std::string pathCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateX,heuristicX," + richStateHeader()
         + ",branchWon,branchFloor,branchHp";
}

static std::string runPathCounterfactualSeed(std::uint64_t seed, int outerSims, int asc,
                                             int branchSims, int futures, std::uint64_t futureSalt) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 17);
    PathHistory path;
    t_curPath = &path;

    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<int> sampledCandidates;
    int sampledDecision = -1, sampledHeuristic = -1;
    int eligible = 0, decisionIdx = 0;
    using RT = search::GameAction::RewardsActionType;

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            std::vector<int> candidates;
            if (gc.curMapNodeY < 0) {
                for (const MapNode &node : gc.map->nodes[0]) if (node.edgeCount > 0) candidates.push_back(node.x);
            } else {
                const MapNode &node = gc.map->getNode(gc.curMapNodeX, gc.curMapNodeY);
                for (int i = 0; i < node.edgeCount; ++i) candidates.push_back(node.edges[i]);
            }
            const int heuristic = one_combat::chooseMapAction(gc);
            if (candidates.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledCandidates = candidates;
                    sampledDecision = decisionIdx;
                    sampledHeuristic = heuristic;
                }
                ++decisionIdx;
            }
            search::GameAction(heuristic).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else one_combat::serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // current deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::ostringstream out;
    if (sampled) {
        const int na = static_cast<int>(sampledCandidates.size());
        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
        const int nf = std::max(1, futures);
        std::vector<int> validFutures(na, 0);
        for (int f = 0; f < nf; ++f) {
            const std::uint64_t futureSeed = seed
                ^ (0xa24baed4963ee407ULL * static_cast<std::uint64_t>(sampledDecision * nf + f + 1))
                ^ (0x9e3779b97f4a7c15ULL * futureSalt);
            for (int a = 0; a < na; ++a) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                search::GameAction(sampledCandidates[a]).execute(branch);
                const OocCounterfactualResult result = finishOocCounterfactual(
                    branch, branchSims, futureSeed, sampledPath, -1, false);
                if (!result.valid) {
                    ++g_trainingInvalidBranches;
                    continue;
                }
                bw[a] += result.won; bf[a] += result.floor; bh[a] += result.hp;
                ++validFutures[a];
            }
        }
        t_curPath = &sampledPath;
        const std::string state = richRow(*sampled, sampledPath);
        for (int a = 0; a < na; ++a) {
            if (!search::hasCompleteCounterfactualFutureSet(validFutures[a], nf, nf)) continue;
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledCandidates[a] << ','
                << sampledHeuristic << ',' << state << ',' << bw[a]/nf << ',' << bf[a]/nf << ','
                << bh[a]/nf << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

static void pathCounterfactualGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                                  std::uint64_t seedOffset, int branchSims, int futures,
                                  std::uint64_t futureSalt = 0) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << pathCounterfactualHeader() << '\n'; out.flush(); }
    std::cout << "pathcfgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " futureSalt " << futureSalt
              << " threads " << numThreads() << " -> " << outfile << '\n';
    auto start = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runPathCounterfactualSeed(seedOffset+s, outerSims, asc,
                                                                branchSims, futures, futureSalt);
        #pragma omp critical(path_cf_write)
        {
            out << generated; out.flush();
            rows += std::count(generated.begin(), generated.end(), '\n');
            ++done;
            if (done % 25 == 0 || done == nSeeds) {
                const double elapsed = std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-start).count();
                std::printf("  %d/%d runs, %lld action rows, %.0fs (%.2fs/run)\n",
                            done, nSeeds, rows, elapsed, elapsed/done);
                std::fflush(stdout);
            }
        }
    }
}

static bool genuineRestVsSmith(const GameContext &gc) {
    return !gc.hasRelic(RelicId::COFFEE_DRIPPER)
        && !gc.relics.has(RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
}

// ---------------------------------------------------------------------------
// E2c producer orchestration stays in the driver; capture state and validation
// implementation live in one_combat/e2c_capture.
static void e2cGen(int nSeeds, int sims, int asc, const std::string &outfile,
                   long long seedOffset = 0) {
    trainingCampaignStart();
    one_combat::resetE2cAccounting();
    const bool append = seedOffset > 0;
    std::cout << "e2cgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << one_combat::e2cHeader(); f.flush(); }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, true, /*e2cCapture=*/true);
        std::string rows = one_combat::takeE2cRows();
        #pragma omp critical(e2c_write)
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0 || done == nSeeds) {
                const double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.2fs/run)\n", done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld E2c rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d "
                "branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), rowCount, outfile.c_str());
    const auto accounting = one_combat::e2cAccounting();
    for (int i = 0; i < 3; ++i)
        std::printf("e2c accounting room=%s eligible=%lld raw=%lld post=%lld pairs=%lld raw_only=%lld post_only=%lld\n",
                    i == 0 ? "MONSTER" : i == 1 ? "ELITE" : "BOSS",
                    accounting.counts[i][0], accounting.counts[i][1], accounting.counts[i][2],
                    accounting.counts[i][3], accounting.counts[i][4], accounting.counts[i][5]);
    writeTrainingProvenance(outfile, "e2cgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc);
    std::ofstream schema(outfile + ".schema.json");
    if (schema)
        schema << "{\n  \"schema_version\": \"e2c-v2\",\n"
               << "  \"raw_primary_retains_incomplete_pairs\": true,\n"
               << "  \"matched_arms_require_complete_raw_post_pairs\": true\n}\n";
}

static std::string restCounterfactualHeader() {
    return "seed,restIdx," + richStateHeader()
         + ",restWon,restFloor,restHp,smithWon,smithFloor,smithHp";
}

static std::string cardCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateId,candidateUpgraded," + richStateHeader()
         + ",branchFutures,branchWon,branchFloor,branchHp"
         + ",branchNextCombatSeen,branchNextCombatPassed"
         + ",branchNextEliteSeen,branchNextElitePassed"
         + ",branchNextBossSeen,branchNextBossPassed,branchFutureComplete";
}

struct DataGen2Rows {
    std::string meta;
    std::string rest;
    std::string card;
};

static DataGen2Rows
runDataGen2Seed(std::uint64_t seed, int sims, int asc, double epsilon,
                int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                int cardCfSims = 0, int cardCfFights = 3, int cardCfFutures = 1,
                int cardCfStride = 1, int cardCfMaxPerRun = 0,
                std::uint64_t cardCfFutureSalt = 0, int cardCfAdaptiveMaxFutures = 0,
                double cardCfAdaptiveGap = 5.0) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    PathHistory path;
    t_curPath = &path;
    std::vector<std::string> rows;
    std::vector<std::string> restRows;
    std::vector<std::string> cardRows;
    int restIdx = 0;
    int cardDecisionIdx = 0, cardCollected = 0;
    using RT = search::GameAction::RewardsActionType;
    // Data is generated with the CURRENT BEST play policy (server card picks
    // skip@g_cardSkipThresh + heuristic path + shop-V), so labels & the state
    // distribution match how we actually play. eps-greedy random card picks keep
    // deck coverage broad. Requires v_server.py running.
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(richRow(gc, path));                 // comprehensive snapshot
                // Softmax-sample each card reward by its V-marginal (temp g_dgTemp)
                // + uniform floor `epsilon`: data spreads over good-but-varied play
                // while every card still gets sampled sometimes (unbiased coverage).
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();

                    // Direct action labels: from the identical pre-choice state,
                    // finish the run after every offered card and after skip.  A
                    // deterministic hash samples decision positions uniformly;
                    // the per-run cap prevents one long run from dominating cost.
                    const int stride = std::max(1, cardCfStride);
                    const bool sampleCardCf = cardCfSims > 0 && cardCfMaxPerRun > 0
                        && cardCollected < cardCfMaxPerRun
                        && ((seed * 11400714819323198485ULL
                             + (std::uint64_t)cardDecisionIdx * 0x9e3779b97f4a7c15ULL)
                            % (std::uint64_t)stride) == 0;
                    if (sampleCardCf) {
                        const int na = nc + 1;                 // offered cards + skip
                        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
                        std::vector<double> ncs(na, 0.0), ncp(na, 0.0);
                        std::vector<double> nes(na, 0.0), nep(na, 0.0);
                        std::vector<double> nbs(na, 0.0), nbp(na, 0.0), nfc(na, 0.0);
                        const int futures = std::max(1, cardCfFutures);
                        const int maxFutures = std::max(futures, cardCfAdaptiveMaxFutures);
                        int usedFutures = 0;
                        bool cardCfInvalid = false;
                        for (int f = 0; f < maxFutures; ++f) {
                            const std::uint64_t futureSeed = seed
                                ^ (0xd1b54a32d192ed03ULL
                                   * (std::uint64_t)(cardDecisionIdx * futures + f + 1))
                                ^ (0x9e3779b97f4a7c15ULL * cardCfFutureSalt);
                            for (int a = 0; a < na; ++a) {
                                const int choice = a < nc ? a : 5;
                                GameContext branch = detachedCounterfactualCopy(gc);
                                search::GameAction(RT::CARD, rIdx, choice).execute(branch);
                                FutureFightProbe probe;
                                OocCounterfactualResult br = finishOocCounterfactual(
                                    branch, cardCfSims, futureSeed, path,
                                    std::max(1, cardCfFights), true, &probe);
                                t_curPath = &path;
                                if (!br.valid) {
                                    ++g_trainingInvalidBranches;
                                    cardCfInvalid = true;
                                    break;
                                }
                                bw[a] += br.won;
                                bf[a] += br.floor;
                                bh[a] += br.hp;
                                ncs[a] += probe.nextCombatSeen;
                                ncp[a] += probe.nextCombatPassed;
                                nes[a] += probe.nextEliteSeen;
                                nep[a] += probe.nextElitePassed;
                                nbs[a] += probe.nextBossSeen;
                                nbp[a] += probe.nextBossPassed;
                                nfc[a] += probe.completed;
                            }
                            if (cardCfInvalid) break;
                            usedFutures = f + 1;
                            if (usedFutures >= futures) {
                                std::vector<double> runningScore(na);
                                for (int a = 0; a < na; ++a)
                                    runningScore[a] = (bf[a] + 10.0 * bw[a]) / usedFutures;
                                std::nth_element(runningScore.begin(), runningScore.end()-2,
                                                 runningScore.end());
                                const double gap = runningScore.back()
                                                   - *(runningScore.end()-2);
                                if (usedFutures >= maxFutures || gap > cardCfAdaptiveGap) break;
                            }
                        }
                        if (!cardCfInvalid
                            && search::hasCompleteCounterfactualFutureSet(usedFutures, usedFutures,
                                                                            futures)) {
                            const std::string state = richRow(gc, path);
                            for (int a = 0; a < na; ++a) {
                                const bool skip = a == nc;
                                const Card *card = skip ? nullptr : &r.cardRewards[rIdx][a];
                                std::ostringstream cr;
                                cr << seed << ',' << cardDecisionIdx << ',' << (skip ? 5 : a) << ','
                                   << (skip ? -1 : (int)card->getId()) << ','
                                   << (skip ? 0 : (card->isUpgraded() ? 1 : 0)) << ',' << state << ','
                                   << usedFutures << ',' << bw[a]/usedFutures << ','
                                   << bf[a]/usedFutures << ',' << bh[a]/usedFutures << ','
                                   << ncs[a]/usedFutures << ',' << ncp[a]/usedFutures << ','
                                   << nes[a]/usedFutures << ',' << nep[a]/usedFutures << ','
                                   << nbs[a]/usedFutures << ',' << nbp[a]/usedFutures << ','
                                   << nfc[a]/usedFutures;
                                cardRows.push_back(cr.str());
                            }
                        }
                        ++cardCollected;
                    }
                    ++cardDecisionIdx;

                    std::vector<double> marg = vQueryMarginals(gc, rIdx);
                    int action;
                    if ((int)marg.size() != nc) {                    // server error -> uniform incl skip
                        action = std::uniform_int_distribution<int>(0, nc)(ex);
                        if (action >= nc) action = 5;
                    } else if (*std::max_element(marg.begin(), marg.end()) < g_cardSkipThresh) {
                        action = 5;                                  // no card improves the deck -> skip (as exploit)
                    } else {
                        action = sampleCardSoftmax(marg, g_dgTemp, epsilon, ex);  // softmax which card
                    }
                    search::GameAction(RT::CARD, rIdx, action).execute(gc);
                }
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);                                       // best shop policy (V-knapsack)
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);                               // shop removal target
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF outer rest seed=" << seed << " idx=" << restIdx << " floor=" << gc.floorNum << "\n";
            if (restCfSims > 0 && genuineRestVsSmith(gc)
                && restCfStride > 0 && (seed % (std::uint64_t)restCfStride) == 0) {
                double rw = 0, rf = 0, rh = 0, sw = 0, sf = 0, sh = 0;
                const int futures = std::max(1, restCfFutures);
                int validFutures = 0;
                bool restCfInvalid = false;
                for (int f = 0; f < futures; ++f) {
                    const std::uint64_t futureSeed = seed ^ (0x9e3779b97f4a7c15ULL
                                                    * (std::uint64_t)(restIdx * futures + f + 1));
                    GameContext gr = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply rest valid=" << search::GameAction(0, 0).isValidAction(gr) << "\n";
                    search::GameAction(0, 0).execute(gr);       // rest
                    OocCounterfactualResult rr = finishOocCounterfactual(
                        gr, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF rest branch done floor=" << rr.floor << "\n";
                    t_curPath = &path;
                    GameContext gs = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply smith valid=" << search::GameAction(1, 0).isValidAction(gs) << "\n";
                    search::GameAction(1, 0).execute(gs);       // smith
                    if (gs.screenState == ScreenState::CARD_SELECT
                        && gs.info.selectScreenType == CardSelectScreenType::UPGRADE)
                        one_combat::upgradeSelectWinPolicy(gs);
                    OocCounterfactualResult sr = finishOocCounterfactual(
                        gs, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF smith branch done floor=" << sr.floor << "\n";
                    t_curPath = &path;
                    if (!rr.valid || !sr.valid) {
                        g_trainingInvalidBranches += !rr.valid + !sr.valid;
                        restCfInvalid = true;
                        break;
                    }
                    rw += rr.won; rf += rr.floor; rh += rr.hp;
                    sw += sr.won; sf += sr.floor; sh += sr.hp;
                    ++validFutures;
                }
                if (!restCfInvalid
                    && search::hasCompleteCounterfactualFutureSet(validFutures, validFutures,
                                                                    futures)) {
                    std::ostringstream cr;
                    cr << seed << ',' << restIdx << ',' << richRow(gc, path)
                       << ',' << rw/validFutures << ',' << rf/validFutures << ',' << rh/validFutures
                       << ',' << sw/validFutures << ',' << sf/validFutures << ',' << sh/validFutures;
                    restRows.push_back(cr.str());
                }
                ++restIdx;
            }
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply deployed rest policy\n";
            if (!one_combat::restWinPolicy(gc)) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (!actions.empty()) actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED))
        return {};
    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum, endHp = gc.curHp;
    std::ostringstream o, ro, co;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << ',' << endHp << '\n';
    for (const auto &rr : restRows) ro << rr << '\n';
    for (const auto &cr : cardRows) co << cr << '\n';
    return {o.str(), ro.str(), co.str()};
}

static void dataGen2(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                     long long seedOffset = 0, const std::string &restOut = "",
                     int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                     const std::string &cardOut = "", int cardCfSims = 0,
                     int cardCfFights = 3, int cardCfFutures = 1, int cardCfStride = 1,
                     int cardCfMaxPerRun = 0, std::uint64_t cardCfFutureSalt = 0,
                     int cardCfAdaptiveMaxFutures = 0, double cardCfAdaptiveGap = 5.0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "datagen2 (rich)  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << "  cardFutureSalt " << cardCfFutureSalt
              << (append ? "  [append]" : "") << "  threads " << numThreads() << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << richHeader() << '\n'; f.flush(); }
    std::ofstream rf;
    if (!restOut.empty()) {
        rf.open(restOut, append ? std::ios::app : std::ios::out);
        if (rf.tellp() == 0) { rf << restCounterfactualHeader() << '\n'; rf.flush(); }
    }
    std::ofstream cf;
    if (!cardOut.empty()) {
        cf.open(cardOut, append ? std::ios::app : std::ios::out);
        if (cf.tellp() == 0) { cf << cardCounterfactualHeader() << '\n'; cf.flush(); }
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0, cardRowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto generated = runDataGen2Seed((std::uint64_t)(seedOffset + s), sims, asc, epsilon,
                                         restCfSims, restCfFutures, restCfStride,
                                         cardCfSims, cardCfFights, cardCfFutures, cardCfStride,
                                         cardCfMaxPerRun, cardCfFutureSalt,
                                         cardCfAdaptiveMaxFutures, cardCfAdaptiveGap);
        #pragma omp critical
        {
            f << generated.meta; f.flush();
            if (rf.is_open()) { rf << generated.rest; rf.flush(); }
            if (cf.is_open()) { cf << generated.card; cf.flush(); }
            rowCount += std::count(generated.meta.begin(), generated.meta.end(), '\n');
            cardRowCount += std::count(generated.card.begin(), generated.card.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld meta rows, %lld card-CF rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, cardRowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld meta rows + %lld card-CF rows from %d runs in %.1fs\n",
                rowCount, cardRowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "datagen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount + cardRowCount,
                            seedOffset, sims, asc, epsilon);
}

// ---------------------------------------------------------------------------
// COMBAT VALUE datagen: snapshot the live BattleContext at every in-fight
// decision (via search::g_onCombatDecision) and label each snapshot with that
// fight's eventual outcome (won, end HP). Trains V_combat(state) -> outcome, a
// learned leaf value to replace noisy random rollouts. Features are combat-only
// (player/monsters/available-cards), fixed length.
// Header/row now delegate to the library (search::combatFeatureNames /
// combatExtractFeatures) so combatgen training data and the C++ leaf-inference
// use the SAME feature extraction -- no train/serve drift.
static std::string combatHeaderStr() {
    const auto &names = search::combatFeatureNames();
    std::string h;
    for (size_t i = 0; i < names.size(); ++i) { if (i) h += ','; h += names[i]; }
    return h;
}

// Rich-label suffix (distributional model): endTurn + per-potion-ID consumption flags.
// Potion IDs 0..43 map to the Potion enum (0=EMPTY, 1=INVALID, 2..43=real potions).
static constexpr int kNumGenPotions = 44;
static std::string distLabelHeaderStr() {
    std::string h = ",endTurn,potionsConsumed";
    for (int i = 0; i < kNumGenPotions; ++i) { h += ",pUsed"; h += std::to_string(i); }
    return h;
}

// Snapshot of what's held at a decision so we can later determine consumption.
struct CombatDecisionSnapshot {
    std::string featureRow;
    std::bitset<kNumGenPotions> potionsHeld;
};
static std::string distLabelSuffix(const CombatDecisionSnapshot &snap,
                                   int endTurn,
                                   const std::bitset<kNumGenPotions> &finalPotions) {
    std::ostringstream o;
    o << ',' << endTurn;
    int consumed = 0;
    for (int i = 0; i < kNumGenPotions; ++i) {
        if (snap.potionsHeld[i] && !finalPotions[i]) ++consumed;
    }
    o << ',' << consumed;
    for (int i = 0; i < kNumGenPotions; ++i) {
        o << ',' << (snap.potionsHeld[i] && !finalPotions[i] ? 1 : 0);
    }
    return o.str();
}
static std::bitset<kNumGenPotions> getPotionBits(const BattleContext &bc) {
    std::bitset<kNumGenPotions> b;
    for (int i = 0; i < bc.potionCapacity && i < (int)bc.potions.size(); ++i) {
        int pid = (int)bc.potions[i];
        if (pid >= 0 && pid < kNumGenPotions) b.set(pid);
    }
    return b;
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
struct WholeCombatTeacher { std::string id; nlohmann::json specification; };

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

static WholeCombatTeacher loadWholeCombatTeacher(const std::string &path, int sims,
                                                 bool allowStaleProvenance = false,
                                                 bool requireOocPolicy = false) {
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

static int oocPolicyParitySelfTest(std::uint64_t seed, int sims, int asc) {
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

static void combatEvalGen(int nSeeds, int sims, int asc, const std::string &outfile,
                          long long seedOffset, const std::string &teacherPath,
                          const std::string &runoutPath);
static void wholeCombatGen(int nSeeds, int sims, int asc, const std::string &outfile,
                           long long seedOffset, const std::string &teacherPath);

static int teacherSchemaCompatibilitySelfTest() {
    for (const auto &[name, value] : std::vector<std::pair<const char *, const char *>>{
             {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
             {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
             {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
             {"STS_SILVER_TELEMETRY", "1"}})
        setenv(name, value, 1);

    const std::filesystem::path stem = std::filesystem::temp_directory_path()
        / ("sts_legacy_teacher_compat_" + trainingExecutableGitSha());
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

static void combatEvalGen(int nSeeds, int sims, int asc, const std::string &outfile,
                          long long seedOffset, const std::string &teacherPath,
                          const std::string &runoutPath = {}) {
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
static void wholeCombatGen(int nSeeds,int sims,int asc,const std::string&outfile,long long seedOffset,const std::string&teacherPath){trainingCampaignStart();search::g_richCombatFeatures=true;const auto teacher=loadWholeCombatTeacher(teacherPath,sims);std::ofstream f(outfile);if(!f)throw std::runtime_error("wholecombatgen: cannot open output");f<<"sourceSeed,fightIdx,act,floor,encounter,roomClass,decisionIdx,teacherId,"<<combatHeaderStr()<<",won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac,startPotionIds,endPotionIds,startPotionCount,endPotionCount,goldDelta,smokeBombUsed,changedRelicCounters,ritualDaggerChanges,deckStructureChanged,parasiteAdded,persistentMutationSummary\n";long long rows=0;int completed=0;
    #pragma omp parallel for schedule(dynamic)
    for(int s=0;s<nSeeds;++s){const std::string generated=runWholeCombatGenSeed(seedOffset+s,sims,asc,teacher);
        #pragma omp critical(whole_combat_write)
        {f<<generated;f.flush();rows+=std::count(generated.begin(),generated.end(),'\n');if(!generated.empty())++completed;}}
    std::cout<<"wholecombatgen teacher="<<teacher.id<<" completed="<<completed<<'/'<<nSeeds<<" quarantined="<<nSeeds-completed<<" rows="<<rows<<" -> "<<outfile<<'\n';writeTrainingProvenance(outfile,"wholecombatgen",nSeeds,completed,nSeeds-completed,g_trainingHealthFailures.load(),rows,seedOffset,sims,asc);
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

static void counterfactualSurrogateAuditGen(int nSeeds,int sims,int asc,const std::string&outfile,
                                            std::uint64_t seedOffset,const std::string&teacherPath){
    trainingCampaignStart();search::g_richCombatFeatures=true;const auto teacher=loadWholeCombatTeacher(teacherPath,sims);std::ofstream f(outfile);if(!f)throw std::runtime_error("counterfactual surrogate audit: cannot open output");f<<"sourceSeed,decisionIdx,actionIdx,actionBits,action,chosen,screen,decisionAct,decisionFloor,battleAct,battleFloor,battleEncounter,roomClass,teacherId,valid,quarantineReason,"<<combatHeaderStr()<<",won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac\n";long long rows=0;int completed=0;
    for(int s=0;s<nSeeds;++s){const auto r=runCounterfactualSurrogateAuditSeed(seedOffset+s,sims,asc,teacher);rows+=std::count(r.begin(),r.end(),'\n');if(!r.empty())++completed;f<<r;f.flush();}
    std::cout<<"ooccfaudit teacher="<<teacher.id<<" completed="<<completed<<'/'<<nSeeds<<" quarantined="<<nSeeds-completed<<" rows="<<rows<<" -> "<<outfile<<'\n';writeTrainingProvenance(outfile,"ooccfaudit",nSeeds,completed,nSeeds-completed,g_trainingHealthFailures.load(),rows,seedOffset,sims,asc);
}

static bool datagenGateStack(GameContext &gc, const search::ScumSearchAgent2 &agent) {
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN:       return oocOnePlyEventPolicy(gc, agent);
        case ScreenState::REST_ROOM:          return oocOnePlyRestPolicy(gc, agent);
        case ScreenState::TREASURE_ROOM:      return oocOnePlyTreasurePolicy(gc, agent);
        case ScreenState::SHOP_ROOM:          return oocOnePlyShopPolicy(gc, agent);
        case ScreenState::BOSS_RELIC_REWARDS: return oocOnePlyBossRelicPolicy(gc, agent);
        default:                              return false;
    }
}

static std::string runCombatGenSeed(std::uint64_t seed, int sims, int asc, double epsilon,
                                      bool richLabels = false) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    int fightIdx = 0;
    std::vector<CombatDecisionSnapshot> fightSnaps;
    search::g_onCombatDecision = [&](const BattleContext &bc) {
        CombatDecisionSnapshot s;
        s.featureRow = combatFeatureRow(bc);
        s.potionsHeld = getPotionBits(bc);
        fightSnaps.push_back(std::move(s));
    };
    // When richLabels=false: emit just won,endHp (backward-compatible).
    // When richLabels=true: also emit endTurn + per-potion consumption labels.

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            fightSnaps.clear();
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                return {};
            }
            const int won      = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp    = bc.player.curHp;
            const int endTurn  = bc.turn;
            auto finalPotions  = getPotionBits(bc);
            for (const auto &snap : fightSnaps) {
                out << seed << ',' << fightIdx << ',' << snap.featureRow
                    << ',' << won << ',' << endHp;
                if (richLabels)
                    out << distLabelSuffix(snap, endTurn, finalPotions);
                out << '\n';
            }
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (g_datagenGates && oocOnePlyCardRewardPolicy(gc, agent)) { /* gate-stack card pick (§127) */ }
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            if (!g_datagenGates || !datagenGateStack(gc, agent))
                agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    return out.str();
}

// forward decl
static std::string policyHeaderStr();
// ---------------------------------------------------------------------------
// FAIR-PLAY datagen: Searcher3 ISMCTS → value + policy CSVs with visit
// distributions. Policy rows: state+action features + visit count + total.
// ---------------------------------------------------------------------------
static std::tuple<std::string,std::string,std::string>
runFairGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    search::g_richCombatFeatures = true;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path; t_curPath = &path;

    std::ostringstream val, pol, ooc;
    int fightIdx = 0, decIdx = 0, oocDecIdx = 0;
    std::vector<CombatDecisionSnapshot> fightSnaps;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    auto logOoc = [&](const char *screen, int actionId) {
        ooc << seed << ',' << oocDecIdx++ << ',' << screen << ','
            << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ','
            << (int)gc.deck.cards.size() << ',' << (int)gc.gold << ',' << actionId << '\n';
    };

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        CombatDecisionSnapshot s;
        s.featureRow = combatFeatureRow(bc);
        s.potionsHeld = getPotionBits(bc);
        fightSnaps.push_back(std::move(s));
    };
    search::g_onSearchComplete3 = [&](const BattleContext &bc, const search::BattleScumSearcher3 &s3) {
        const int thisDecIdx = decIdx++;
        const auto &edges = s3.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.child.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v;
            }
            pol << ',' << e.child.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            fightSnaps.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                search::g_onSearchComplete3 = nullptr;
                t_curPath = nullptr;
                return {"", "", ""};
            }
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            const int endTurn = bc.turn;
            auto finalPotions = getPotionBits(bc);
            for (const auto &snap : fightSnaps)
                val << seed << ',' << fightIdx << ',' << snap.featureRow << ','
                    << won << ',' << endHp
                    << distLabelSuffix(snap, endTurn, finalPotions) << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            int action = one_combat::chooseMapAction(gc); logOoc("MAP", action); search::GameAction(action).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int ridx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[ridx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, ridx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete3 = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str(), ooc.str() };
}

static void fairGen(int nSeeds, int sims, int asc, double epsilon,
                    const std::string &valFile, const std::string &polFile,
                    const std::string &oocFile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fairgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << " + " << oocFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    std::ofstream of(oocFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp"
                             << distLabelHeaderStr() << "\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }
    if (of.tellp() == 0) { of << "seed,decIdx,screen,act,floor,curHp,maxHp,deckSize,gold,action\n"; of.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0, oRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto [vr, pr, or_] = runFairGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << vr;  pf << pr;  of << or_;
            vf.flush(); pf.flush(); of.flush();
            vRows += std::count(vr.begin(), vr.end(), '\n');
            pRows += std::count(pr.begin(), pr.end(), '\n');
            oRows += std::count(or_.begin(), or_.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol + %lld ooc rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, oRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy + %lld ooc rows from %d runs in %.1fs\n",
                vRows, pRows, oRows, nSeeds, wall);
    writeTrainingProvenance(valFile, "fairgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), vRows + pRows + oRows,
                            seedOffset, sims, asc, epsilon);
}

// ---------------------------------------------------------------------------
// Retained Searcher3 diagnostic mode drivers run full runs via runFullRunOOC (fair Searcher3, the
// §126 deployed regime) with the leaf-query hook registered, collecting a
// per-stratum reservoir of actual Searcher3 leaf-expansion states. Sampling
// is deterministic per seed (the particle diagnostic RNG is seeded from the run seed only), so the
// collected leaf SET is reproducible; CSV row order follows seed completion
// order (nondeterministic under dynamic scheduling, like fairGen). Do NOT set
// probing OOC env arms (STS_OOC_ACTION_NN, STS_BOSS_DRAFT, M1/M2 path gates,
// STS_DATAGEN_GATES, …): their inner probe battles would fire the leaf hook
// and pollute the dataset with non-live decision states.
// ---------------------------------------------------------------------------
static void particleLeafProbe(int nSeeds, int sims, int asc,
                              const std::string &outFile, long long seedOffset = 0) {
    search::g_richCombatFeatures = true;
    std::ofstream f(outFile);
    if (!f) { std::cerr << "particle_leaf_probe: cannot open " << outFile << '\n'; return; }
    f << one_combat::particleLeafProbeHeader() << '\n';
    one_combat::startParticleLeafProbe(outFile);
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + s);
        one_combat::installParticleLeafProbeHooks(seed);
        runFullRunOOC(seed, sims, asc, false, false);
        const std::string out = one_combat::finishParticleLeafProbeSeed();
        #pragma omp critical
        f << out;
    }
    one_combat::stopParticleDiagnostics();
    std::cout << "particle leaf probe wrote " << outFile << " (K="
              << one_combat::particleLeafProbeK() << ", rate="
              << one_combat::particleLeafProbeRate()
              << ", max_groups=" << one_combat::particleLeafProbeMaxGroups() << ")\n";
}

static void particlePosteriorProbe(int nSeeds, int sims, int asc,
                                   const std::string &outFile, long long seedOffset = 0) {
    if (!one_combat::startParticlePosteriorProbe(outFile)) return;
    search::g_richCombatFeatures = true;
    std::ofstream f(outFile);
    if (!f) {
        one_combat::stopParticleDiagnostics();
        std::cerr << "particle_posterior_probe: cannot open " << outFile << '\n';
        return;
    }
    std::ofstream runs(outFile + ".runs.csv");
    if (!runs) {
        one_combat::stopParticleDiagnostics();
        std::cerr << "particle_posterior_probe: cannot open " << outFile << ".runs.csv\n";
        return;
    }
    runs << "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,actionFingerprint\n";
    f << one_combat::particlePosteriorProbeHeader() << '\n';
    const auto t0 = std::chrono::steady_clock::now();
    long long rows = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + s);
        one_combat::installParticlePosteriorProbeHooks(seed);
        const RunResult r = runFullRunOOC(seed, sims, asc, false, false);
        const std::string out = one_combat::finishParticlePosteriorProbeSeed();
        const std::string fingerprint = one_combat::particlePosteriorActionFingerprint();
        #pragma omp critical
        {
            f << out;
            runs << (seedOffset + s) << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                 << r.act << ',' << r.hpEnd << ',' << r.maxHp << ',' << r.fightsLost << ','
                 << r.deathCombat << ',' << r.deathEncounter << ",\"" << fingerprint << "\"\n";
            rows += std::count(out.begin(), out.end(), '\n');
        }
    }
    one_combat::stopParticleDiagnostics();
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("particle posterior probe wrote %s (%lld rows, K=%s, max_groups=%d) in %.1fs (%.2fs/seed)\n",
                outFile.c_str(), rows,
                one_combat::particlePosteriorProbeK() > 0
                    ? std::to_string(one_combat::particlePosteriorProbeK()).c_str() : "all",
                one_combat::particlePosteriorProbeMaxGroups(), wall, wall / std::max(1, nSeeds));
}

// ---------------------------------------------------------------------------
// STRATEGIC data generation: one CSV row per LEGAL action at each OOC decision,
// with full rich state, structured candidate fields, a chosen flag, and the
// terminal outcome. Feeds Phase 5 run-level model training.
// Row schema (strategicHeader()):
//   seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,
//   <1017 rich state>,won,endFloor,endHp
// - action: raw packed GameAction bits (uint32).
// - actionType: rewardsActionType (0..6) on REWARDS/SHOP, CardSelectScreenType
//   on CARD_SELECT, else -1.
// - c1..c3: raw GameAction indices (idx1..idx3), 0 when unused.
// - cand1..c3: screen-specific resolved candidate identities (-1 when N/A):
//   REWARDS: GOLD=gold amt; CARD=cardId,upgraded; RELIC=relicId; POTION=potionId;
//            KEY=2 (emerald) / 3 (sapphire).
//   SHOP:    CARD=cardId,price,upgraded; RELIC=relicId,price; POTION=potionId,price;
//            CARD_REMOVE=removeCost.
//   EVENT:   eventId, option index.  MAP: childX, childY, childRoom.
//   BOSS_RELIC_REWARDS: relicId.  CARD_SELECT: cardId, selectScreenType.
//   REST/TREASURE: -1 (option semantics live in c1 / screen state).
static std::string strategicStateCols() {
    std::string h = richHeader();                       // "seed,<state...>,curMapY,won,finalFloor,endHp"
    const auto comma = h.find(',');
    std::string rest = h.substr(comma + 1);             // drop the "seed," prefix
    const auto wonPos = rest.rfind(",won,finalFloor,endHp");
    return rest.substr(0, wonPos);                      // state columns only, in richRow() order
}

static std::string strategicHeader() {
    return "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,"
         + strategicStateCols() + ",won,endFloor,endHp\n";
}

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
static StratFingerprint stratFingerprint(const GameContext &gc) {
    StratFingerprint f{};
    f.screen = (int)gc.screenState; f.act = gc.act; f.floor = gc.floorNum;
    f.hp = gc.curHp; f.maxHp = gc.maxHp; f.gold = gc.gold;
    f.keys[0] = gc.blueKey ? 1 : 0; f.keys[1] = gc.greenKey ? 1 : 0; f.keys[2] = gc.redKey ? 1 : 0;
    f.potionCount = gc.potionCount;
    for (int i = 0; i < 5; ++i)
        f.potions[i] = (i < (int)gc.potions.size()) ? (int)gc.potions[i] : -1;
    f.deckSize = (int)gc.deck.size();
    f.bottledLast = -1;
    for (int i = 0; i < f.deckSize; ++i) {
        const Card &c = gc.deck.cards[i];
        const int id = (int)c.getId();
        f.deckSum += id; f.deckUpSum += c.isUpgraded() ? id : 0;
        f.deckHash = f.deckHash * 31 + id * 2 + (c.isUpgraded() ? 1 : 0);
        if (gc.deck.isCardBottled(i)) f.bottledLast = id;
    }
    f.relicCount = (int)gc.relics.relics.size();
    for (const auto &ri : gc.relics.relics) {
        const int rid = (int)ri.id;
        f.relicSum += rid; f.relicHash = f.relicHash * 31 + rid + 1;
    }
    for (const auto &sc : gc.info.haveSelectedCards) {
        const int sid = (int)sc.card.getId();
        f.selSum += sid * 2 + (sc.card.isUpgraded() ? 1 : 0);
        f.selHash = f.selHash * 31 + sc.deckIdx + 1;
    }
    const auto &r = gc.info.rewardsContainer;
    f.goldRew = r.goldRewardCount; f.cardRew = r.cardRewardCount;
    f.relicRew = r.relicCount; f.potionRew = r.potionCount;
    f.emeraldKey = r.emeraldKey ? 1 : 0; f.sapphireKey = r.sapphireKey ? 1 : 0;
    f.mapX = gc.curMapNodeX; f.mapY = gc.curMapNodeY;
    f.selectSize = (int)gc.info.toSelectCards.size();
    return f;
}

// Wave B regret gate (ooc-qwin-continuation.md Step 5): decide between the
// Q-max action and the deployed-default heuristic action a_heur.  a_heur is
// identified by the datagen-proven successor-fingerprint match
// (runStrategicGenSeed, one_combat.cpp:5844): the per-screen deployed-default
// heuristic runs on a pre-state copy (agent RNG stream copied, map detached)
// and the legal action whose successor matches the heuristic's successor wins.
// Returns the index of the action to take (Q-max when Qmax − Q(a_heur) > eps,
// else a_heur), or -1 when the heuristic action is unidentifiable — the
// RNG-tied fallback case (RNG-consuming heuristics, multi-step heuristics,
// indistinguishable successors), where the caller falls back to the margin rule.
static int regretGateChoose(const GameContext &pre,
                            const std::vector<search::GameAction> &actions,
                            const std::vector<double> &q, double eps,
                            void (*heuristic)(GameContext &, search::ScumSearchAgent2 &),
                            const search::ScumSearchAgent2 &liveAgent) {
    GameContext probe = pre;
    probe.map = std::make_shared<Map>(*pre.map);        // detach the shared map before probing
    search::ScumSearchAgent2 probeAgent;
    probeAgent.rng = liveAgent.rng;                     // the probe consumes the same stream the
    probeAgent.simulationCountBase = liveAgent.simulationCountBase;  // live heuristic would use
    heuristic(probe, probeAgent);
    const StratFingerprint realFp = stratFingerprint(probe);
    int heurIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        GameContext probe2 = pre;
        probe2.map = std::make_shared<Map>(*pre.map);
        actions[i].execute(probe2);                     // same per-action probe as the datagen
        if (stratFingerprint(probe2) == realFp) { heurIdx = i; break; }
    }
    if (heurIdx < 0) return -1;
    int bestIdx = -1;
    double best = -1e100;
    for (int i = 0; i < (int)q.size(); ++i) if (q[i] > best) { best = q[i]; bestIdx = i; }
    if (bestIdx < 0) return -1;
    return (best - q[heurIdx] > eps) ? bestIdx : heurIdx;
}

static void writeOocTrace(const GameContext &gc,
                          const std::vector<search::GameAction> &actions,
                          const std::vector<double> &q, int bestIdx, int takeIdx,
                          double best, double second, double threshold,
                          const char *rule, bool owned) {
    if (g_oocStrategicTracePath.empty()) return;
    t_oocStrategicTraceRows += std::to_string(gc.seed) + ','
        + std::to_string(t_oocStrategicTraceDecision++) + ','
        + std::to_string(gc.act) + ',' + std::to_string(gc.floorNum) + ','
        + std::to_string((int)gc.screenState) + ',' + std::to_string(actions.size()) + ',';
    for (size_t i = 0; i < actions.size(); ++i) {
        if (i) t_oocStrategicTraceRows += '|';
        t_oocStrategicTraceRows += std::to_string(actions[i].bits);
    }
    t_oocStrategicTraceRows += ",";
    for (size_t i = 0; i < q.size(); ++i) {
        if (i) t_oocStrategicTraceRows += '|';
        std::ostringstream s; s << q[i];
        t_oocStrategicTraceRows += s.str();
    }
    t_oocStrategicTraceRows += ',' + std::to_string(bestIdx) + ','
        + std::to_string(second > -1e90 ? best - second : -1.0) + ','
        + std::to_string(threshold) + ",-1," + std::to_string(takeIdx) + ','
        + rule + ',' + (owned ? "1" : "0") + '\n';
}

// Shared decision tail of every one-ply gate and the M2 route search: in
// regret mode (STS_OOC_STRATEGIC_GATE=regret) the Q-max action replaces the
// heuristic only when Qmax(s) − Q(a_heur) > ε; when a_heur is unidentifiable
// the decision falls back to the margin rule.  Returns whether the policy
// executed an action (the heuristic layer runs otherwise).
bool regretGateTail(GameContext &gc, const std::vector<search::GameAction> &actions,
                           const std::vector<double> &q, int bestIdx, double best, double second,
                           double margin, double eps,
                           void (*heuristic)(GameContext &, search::ScumSearchAgent2 &),
                           const search::ScumSearchAgent2 &agent) {
    if (g_oocStrategicGateRegret) {
        const int take = regretGateChoose(gc, actions, q, eps, heuristic, agent);
        if (take >= 0) {
            if (!g_oocStrategicTracePath.empty())
                writeOocTrace(gc, actions, q, bestIdx, take, best, second, eps, "regret", true);
            actions[take].execute(gc);
            return true;
        }
    }
    if (bestIdx < 0 || best - second < margin) {
        if (!g_oocStrategicTracePath.empty())
            writeOocTrace(gc, actions, q, bestIdx, -1, best, second, margin, "margin", false);
        return false;
    }
    if (!g_oocStrategicTracePath.empty())
        writeOocTrace(gc, actions, q, bestIdx, bestIdx, best, second, margin, "margin", true);
    actions[bestIdx].execute(gc);
    return true;
}

// ---------------------------------------------------------------------------
// B1 SHOP BEAM SEARCH (ooc-next-wave-contracts.md §2): multi-step lookahead over
// the deterministic shop-purchase sequence, replacing the one-ply shop gate
// while STS_OOC_SHOP_BEAM=1 and a strategic net is loaded.
//
// Node state = (remaining shop offers, gold, deck, relics, potions). Each node
// is a detached counterfactual copy (map detached before any mutation).  Shop
// purchases are deterministic (only the leaf value head reads visible state), so
// the search uses no hidden-RNG information: with THE_COURIER restocks the
// clones advance the SAME copied RNG stream the live run will, producing exactly
// the visible restock a real player would see after the purchase.
//
// Expansion: SHOP_ROOM nodes expand every legal GameAction (affordable card/
// relic/potion buys, CARD_REMOVE, SKIP = leave); leave terminates the node as a
// leaf.  A CARD_REMOVE successor is a CARD_SELECT(REMOVE) screen; those nodes
// expand their removal-target picks (each returns to SHOP_ROOM with removeCost
// spent).  Any other successor screen (e.g. a bottled-relic pick) is rare and
// not part of the purchase contract: it terminates the branch as a leaf.
// Dedup: per-ply fingerprint (gold + offer set + StratFingerprint digests:
// deckSum/deckHash, relicSum/relicHash, potions, screen/select type).  The best
// `width` children by leaf value continue; the rest become buy-then-leave leaf
// candidates.  Every SHOP beam node's own state is a leaf candidate (leave).
//
// Termination: every shop-buy ply strictly spends gold, so depth is bounded by
// gold; the expanded-node budget (STS_OOC_SHOP_BEAM_BUDGET, default 4096) is a
// hard global guard for pathological shops.
// ---------------------------------------------------------------------------
static std::uint64_t shopBeamNodeFingerprint(const GameContext &gc) {
    const StratFingerprint f = stratFingerprint(gc);
    const Shop &s = gc.info.shop;
    std::uint64_t h = 1469598103934665603ULL;   // FNV-1a
    auto mix = [&h](std::uint64_t v) {
        for (int k = 0; k < 4; ++k) { h ^= v & 0xffff; h *= 1099511628211ULL; v >>= 16; }
    };
    mix((std::uint64_t)((std::uint32_t)(int)gc.screenState) << 8
        | (std::uint64_t)((std::uint32_t)(int)gc.info.selectScreenType));
    mix((std::uint64_t)(std::uint32_t)f.gold);
    mix((std::uint64_t)f.deckSum ^ ((std::uint64_t)f.deckUpSum << 1) ^ ((std::uint64_t)f.deckHash << 3));
    mix((std::uint64_t)f.relicSum ^ ((std::uint64_t)f.relicHash << 5));
    mix((std::uint64_t)(std::uint32_t)f.potionCount);
    for (int i = 0; i < 5; ++i) mix((std::uint64_t)(std::uint32_t)(f.potions[i] + 1));
    mix((std::uint64_t)(std::uint32_t)(s.removeCost + 1));
    for (int i = 0; i < 13; ++i) mix((std::uint64_t)(std::uint32_t)(s.prices[i] + 1));
    for (int i = 0; i < 7; ++i)
        mix((std::uint64_t)(std::uint32_t)(((int)s.cards[i].getId() + 1) * 2 + (s.cards[i].isUpgraded() ? 1 : 0)));
    for (int i = 0; i < 3; ++i) mix((std::uint64_t)(std::uint32_t)((int)s.relics[i] + 1));
    for (int i = 0; i < 3; ++i) mix((std::uint64_t)(std::uint32_t)((int)s.potions[i] + 1));
    return h;
}

// Terminal value of a candidate shop state: the per-screen value head on the
// SHOP screen (V3 rich state; V4 token-net glob when the token net is loaded).
static double shopBeamLeafValue(GameContext &gc) {
    // Score the leaf with the head of its ACTUAL successor screen (the V2
    // successor-scoring convention): the per-screen value heads are trained on
    // their own screens, and a post-shop state is not a SHOP screen. Screens
    // outside 1..8 (e.g. BATTLE) clamp to the last head, as predictValue does.
    const int scr = (int)gc.screenState;
    if (g_oocStrategicTokNet.ok) {
        const TokState ts = buildTokState(gc, t_curPath ? *t_curPath : t_emptyPath);
        return g_oocStrategicTokNet.predictValue(ts.glob, scr);
    }
    return g_oocStrategicNet.predictValue(richFeatureVec(gc).data(), scr);
}

bool oocShopBeamPolicy(GameContext &gc) {
    if ((!g_oocStrategicNet.ok && !g_oocStrategicTokNet.ok) || !g_oocShopBeam) return false;
    const bool inShop = gc.screenState == ScreenState::SHOP_ROOM;
    const bool inRemove = gc.screenState == ScreenState::CARD_SELECT
                          && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    if (!inShop && !inRemove) return false;

    using RT = search::GameAction::RewardsActionType;
    struct BeamNode {
        GameContext state;
        std::vector<search::GameAction> actions;
        double value;
    };

    const int width = std::max(4, std::min(256, g_oocShopBeamWidth));
    const int maxDepth = g_oocShopBeamDepth > 0 ? g_oocShopBeamDepth
                                                : std::numeric_limits<int>::max();
    const int maxExpanded = std::max(64, std::min(65536, g_oocShopBeamBudget));

    std::vector<BeamNode> beam;
    beam.push_back({detachedCounterfactualCopy(gc), {}, shopBeamLeafValue(gc)});

    double bestValue = -1e100;
    std::vector<search::GameAction> bestActions;
    int expanded = 0;

    for (int depth = 0; depth < maxDepth && !beam.empty(); ++depth) {
        std::vector<BeamNode> children;
        std::unordered_set<std::uint64_t> seen;
        children.reserve(beam.size() * 16);
        bool budgetHit = false;

        for (std::size_t bi = 0; bi < beam.size(); ++bi) {
            const BeamNode &node = beam[bi];
            const bool nodeShop = node.state.screenState == ScreenState::SHOP_ROOM;
            const std::vector<search::GameAction> legal =
                search::GameAction::getAllActionsInState(node.state);
            if (legal.empty()) continue;

            if (nodeShop) {
                // Leave (SKIP) terminates the node as a leaf on its own state;
                // a node that can only leave is scored the same way.
                if (node.value > bestValue) { bestValue = node.value; bestActions = node.actions; }
                if (legal.size() <= 1) continue;      // only leave left: no purchase possible
                for (const search::GameAction &a : legal) {
                    if (a.getRewardsActionType() == RT::SKIP) continue;
                    if (++expanded > maxExpanded) { budgetHit = true; break; }
                    BeamNode child;
                    child.state = detachedCounterfactualCopy(node.state);
                    a.execute(child.state);
                    child.actions = node.actions;
                    child.actions.push_back(a);
                    children.push_back(std::move(child));
                }
            } else {
                // CARD_SELECT(REMOVE) successor: expand the removal-target picks.
                for (const search::GameAction &a : legal) {
                    if (++expanded > maxExpanded) { budgetHit = true; break; }
                    BeamNode child;
                    child.state = detachedCounterfactualCopy(node.state);
                    a.execute(child.state);            // back to SHOP_ROOM
                    child.actions = node.actions;
                    child.actions.push_back(a);
                    children.push_back(std::move(child));
                }
            }
            if (budgetHit) {
                // The rest of the beam is not expanded: record their leave
                // leaves so no purchase sequence is lost from the candidates.
                for (std::size_t j = bi + 1; j < beam.size(); ++j)
                    if (beam[j].state.screenState == ScreenState::SHOP_ROOM
                        && beam[j].value > bestValue) {
                        bestValue = beam[j].value; bestActions = beam[j].actions;
                    }
                break;
            }
        }
        if (budgetHit) {
            // Remaining beam nodes were already recorded as leave-leaf candidates.
            for (BeamNode &child : children) child.value = shopBeamLeafValue(child.state);
            for (BeamNode &child : children)
                if (child.value > bestValue) { bestValue = child.value; bestActions = child.actions; }
            break;
        }

        // Dedup this ply's children by fingerprint, then keep the top `width`
        // by leaf value; dropped children are buy-then-leave leaf candidates.
        std::vector<BeamNode> kept;
        kept.reserve(children.size());
        for (BeamNode &child : children) {
            child.value = shopBeamLeafValue(child.state);
            if (!seen.insert(shopBeamNodeFingerprint(child.state)).second) continue;
            kept.push_back(std::move(child));
        }
        std::sort(kept.begin(), kept.end(),
                  [](const BeamNode &a, const BeamNode &b) { return a.value > b.value; });
        for (int i = (int)kept.size() - 1; i >= width; --i)
            if (kept[i].value > bestValue) { bestValue = kept[i].value; bestActions = kept[i].actions; }
        if (kept.size() > (size_t)width) kept.resize(width);
        if (kept.empty()) break;
        beam = std::move(kept);
    }

    if (bestActions.empty()) {
        // The beam's best-scoring decision is to leave (buy nothing).
        search::GameAction(RT::SKIP).execute(gc);
        return true;
    }
    bestActions[0].execute(gc);
    return true;
}

// Strategic datagen resolves candidate identities through the policy module seam.
static std::string runStrategicGenSeed(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;

    std::vector<std::string> rows;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else Searcher2.
        if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        const int decIdx = (int)rows.size();
        for (const auto &a : actions) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            a.execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, a, actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << a.bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, path);
            rows.push_back(r.str());
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, path);
            rows.push_back(r.str());
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (const auto &row : rows)
        out << row << ',' << won << ',' << gc.floorNum << ',' << gc.curHp << '\n';
    return out.str();
}

// ── Shared strategic branch label evaluator (Tier-B contract) ──────────────
// Used by both strategicgen2 and strategicmarggen. Evaluates K=3 fights with
// bootstrap=true and the standard 150/100/50 sim schedule. Returns the same
// OocCounterfactualResult fields used by Tier-B label averaging.
static OocCounterfactualResult evaluateStrategicBranch(
    GameContext gc, std::uint64_t branchSeed, const PathHistory &path)
{
    return finishOocCounterfactual(std::move(gc), /*sims=*/0, branchSeed, path,
        g_strategicBranchFights, /*bootstrap=*/true,
        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
}

// ── Production V4 OOC step (frozen baseline) ───────────────────────────────
// Executes exactly one OOC decision using the current frozen V4 gate stack.
static void stepFrozenV4Ooc(GameContext &gc, search::ScumSearchAgent2 &agent) {
    const bool inRemove = gc.screenState == ScreenState::CARD_SELECT
                          && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState == ScreenState::BATTLE) {
        BattleContext bc; bc.init(gc);
        agent.playoutBattle(bc);
        bc.exitBattle(gc);
    } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        if (!oocActionNNPolicy(gc))
            if (!oocMapRouteSearchPolicy(gc, agent))
                if (!oocOnePlyMapPolicy(gc, agent))
                    search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::REST_ROOM) {
        if (!oocActionNNPolicy(gc)) {
            if (!oocOnePlyRestPolicy(gc, agent)) {
                if (g_restWin && one_combat::restWinPolicy(gc)) {}
                else agent.stepOutOfCombatPolicy(gc);
            }
        }
    } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::SHOP_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc))
                if (!oocOnePlyShopPolicy(gc, agent)) one_combat::shopVPolicy(gc);
    } else if (inRemove) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc)) one_combat::removeSelectVPolicy(gc);
    } else if (gc.screenState == ScreenState::REWARDS) {
        auto &r = gc.info.rewardsContainer;
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
        else {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyCardRewardPolicy(gc, agent)) one_combat::serverCardRewardPolicy(gc);
        }
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) one_combat::upgradeSelectWinPolicy(gc);
    } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
}

static std::vector<search::GameAction> v4EvaluatorActions(const GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (gc.screenState == ScreenState::REWARDS
        && gc.info.rewardsContainer.cardRewardCount > 0) {
        const search::GameAction skip(RT::CARD,
                                      gc.info.rewardsContainer.cardRewardCount - 1, 5);
        bool found = false;
        for (const auto &a : actions) if (a.bits == skip.bits) found = true;
        if (!found) actions.push_back(skip);
    }
    return actions;
}

static bool v4EvaluatorOwnedScreen(const GameContext &gc,
                                   const std::vector<search::GameAction> &actions) {
    if (g_oocStrategicGateRegret || actions.empty()) return false;
    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN: return g_oocStrategicEvent;
        case ScreenState::BOSS_RELIC_REWARDS: return g_oocStrategicBossRelic;
        case ScreenState::TREASURE_ROOM: return g_oocStrategicTreasure;
        case ScreenState::REST_ROOM: return g_oocStrategicRest;
        case ScreenState::SHOP_ROOM: return g_oocStrategicShop;
        case ScreenState::CARD_SELECT:
            return g_oocStrategicRest
                && gc.info.selectScreenType == CardSelectScreenType::UPGRADE;
        case ScreenState::REWARDS: {
            const auto &r = gc.info.rewardsContainer;
            if (r.goldRewardCount > 0 || r.relicCount > 0 || r.potionCount > 0)
                return false;
            if (g_collectKeys && (r.emeraldKey || r.sapphireKey)) return false;
            return g_oocStrategicTokNet.ok && r.cardRewardCount > 0;
        }
        default: return false;
    }
}

struct V4H1Sample {
    GameContext pre;
    PathHistory path;
    std::vector<search::GameAction> actions;
    std::uint64_t seed = 0;
    int decisionIdx = -1;
    std::uint32_t chosenBits = UINT32_MAX;
};

static void requireV4H1Comparator(bool allowThreadOverride = false) {
    const std::map<std::string,std::string> required = {
        {"STS_FAIR","1"},{"STS_SEARCHER3","1"},{"STS_S3_BELIEF","0"},
        {"STS_S3_CHAIN","0"},{"STS_S3_PARTICLES","64"},
        {"STS_COLLECT_KEYS","1"},
        {"STS_OOC_STRATEGIC_TOK_NN","selfplay/models/ooc_strategic_tok_final.native"},
        {"STS_VNET","models/v_combat_7k_tuned.txt"},{"STS_VNET_ALPHA","0.3"},
        {"STS_OOC_STRATEGIC_REST","1"},{"STS_OOC_STRATEGIC_EVENT","1"},
        {"STS_OOC_STRATEGIC_SHOP","1"},{"STS_OOC_STRATEGIC_TREASURE","1"},
        {"STS_OOC_STRATEGIC_BOSS_RELIC","1"},{"STS_OOC_STRATEGIC_MARGIN","1.0"},
    };
    for (const auto &[name, expected] : required) {
        const char *actual = std::getenv(name.c_str());
        if (!actual || actual != expected)
            throw std::runtime_error("oocv4h1: comparator environment mismatch for " + name);
    }
    if (!search::g_fairPlay || !search::g_useSearcher3 || !g_oocStrategicTokNet.ok
        || !g_oocStrategicRest || !g_oocStrategicEvent || !g_oocStrategicShop
        || !g_oocStrategicTreasure || !g_oocStrategicBossRelic
        || g_oocStrategicMargin != 1.0 || g_oocStrategicGateRegret
        || g_oocStrategicMarginCard >= 0.0 || g_oocStrategicMarginRest >= 0.0
        || g_oocStrategicMarginEvent >= 0.0 || g_oocStrategicMarginShop >= 0.0
        || g_oocStrategicMarginTreasure >= 0.0 || g_oocStrategicMarginBossRelic >= 0.0
        || !g_collectKeys || !search::g_useVNet
        || g_effectiveVNetPath != "models/v_combat_7k_tuned.txt"
        || search::g_vnetAlpha != 0.3 || (!allowThreadOverride && numThreads() != 24))
        throw std::runtime_error("oocv4h1: recommended V4/Searcher3/VNet stack is not loaded");
    if (search::g_externalCombatBackend)
        throw std::runtime_error("oocv4h1: Silver must be disabled during source replay");
}

static std::vector<search::GameAction> canonicalV4Actions(const GameContext &gc) {
    std::vector<search::GameAction> out;
    std::unordered_set<std::uint32_t> seen;
    for (const auto &a : v4EvaluatorActions(gc)) if (seen.insert(a.bits).second) out.push_back(a);
    return out;
}

static WholeCombatTeacher switchToV4H1Teacher(const std::string &teacherPath, int sims) {
    setenv("STS_SEARCHER3", "0", 1);
    setenv("STS_SILVER_SEARCH", "1", 1);
    const bool allowStale = std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")
        && std::atoi(std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")) != 0;
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, allowStale);
    search::installSilverLiveBackend();
    if (!search::silverLiveBackendInstalled() || !search::silverLiveExactRootBudgets()
        || search::silverLiveReuseCapMode() != "allocated"
        || search::silverLiveReuseCap() != 32768 || search::silverLiveAdaptiveEnabled())
        throw std::runtime_error("oocv4h1: Silver teacher failed runtime validation");
    return teacher;
}

struct V4ActRolloutObservation {
    int act = 0;
    int floor = 0;
    Room room = Room::INVALID;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    GameContext battleEntry;
};

static std::uint64_t v4ActRolloutSeed(std::uint64_t sourceSeed, int rollout) {
    std::uint64_t x = sourceSeed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(rollout + 1));
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31;
    return x ? x : 1;
}

static std::uint64_t v4ActCombatSeed(std::uint64_t rolloutSeed,
                                     int encounter, int occurrence) {
    std::uint64_t x = rolloutSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(encounter + 1))
        ^ (0xa0761d6478bd642fULL * (std::uint64_t)(occurrence + 1));
    x ^= x >> 32; x *= 0xe7037ed1a0b428dULL; x ^= x >> 29;
    return x ? x : 1;
}

static bool advanceRandomActNoFight(GameContext &gc, search::ScumSearchAgent2 &agent,
                                    PathHistory &path, int stopAct,
                                    std::vector<V4ActRolloutObservation> &out) {
    for (int steps = 0; steps < 512 && gc.outcome == GameOutcome::UNDECIDED; ++steps) {
        if (gc.act != stopAct)
            return true;  // Boss rewards may advance the act off-screen; zero cells is valid.
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext observed{};
            observed.init(gc);
            V4ActRolloutObservation row;
            row.act = gc.act; row.floor = gc.floorNum; row.room = gc.curRoom;
            row.encounter = observed.encounter;
            row.battleEntry = detachedCounterfactualCopy(gc);
            out.push_back(std::move(row));

            // Pass through the canonical post-combat transition without
            // consuming combat RNG, cards, or Silver/search budget.
            BattleContext virtualBattle{};
            virtualBattle.init(gc, observed.encounter);
            virtualBattle.player.curHp = gc.curHp;
            virtualBattle.outcome = Outcome::PLAYER_VICTORY;
            virtualBattle.exitBattle(gc);
            continue;
        }
        using RT = search::GameAction::RewardsActionType;
        if (gc.screenState == ScreenState::REWARDS) {
            // The exploratory route deliberately discards rewards so that the
            // rollout measures encounter exposure, not card/shop policy.
            search::GameAction(RT::SKIP).execute(gc);
            continue;
        }
        auto actions = search::GameAction::getAllActionsInState(gc);
        if (!actions.empty()) {
            std::uniform_int_distribution<int> pick(0, (int)actions.size() - 1);
            actions[pick(agent.rng)].execute(gc);
        } else {
            // Screens with an implicit single transition retain the existing
            // cheap base transition; this path never enters combat search.
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    return gc.outcome != GameOutcome::UNDECIDED || gc.act != stopAct;
}

static V4H1Sample replayV4ActRolloutTarget(std::uint64_t seed, int decision,
                                           int sourceSims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 source; source.simulationCountBase = sourceSims;
    source.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    int decisionIdx = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const auto actions = canonicalV4Actions(gc);
        if (v4EvaluatorOwnedScreen(gc, actions) && actions.size() >= 2) {
            if (decisionIdx == decision) {
                t_curPath = nullptr;
                return {detachedCounterfactualCopy(gc), path, actions, seed, decision,
                        UINT32_MAX};
            }
            ++decisionIdx;
        }
        if (gc.screenState == ScreenState::BATTLE) {
            source.simulationCountBase = fightSims(gc, sourceSims);
            search::g_potionKeepValue = potionKeepValue(gc);
        }
        stepFrozenV4Ooc(gc, source);
    }
    t_curPath = nullptr;
    throw std::runtime_error("oocv4h1rollout: target decision did not replay");
}

static std::vector<V4H1Sample> replayV4ActRolloutTargets(std::uint64_t seed,
                                                         int sourceSims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 source; source.simulationCountBase = sourceSims;
    source.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    std::vector<V4H1Sample> targets;
    int decisionIdx = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const auto actions = canonicalV4Actions(gc);
        if (v4EvaluatorOwnedScreen(gc, actions) && actions.size() >= 2) {
            targets.push_back({detachedCounterfactualCopy(gc), path, actions,
                               seed, decisionIdx, UINT32_MAX});
            ++decisionIdx;
        }
        if (gc.screenState == ScreenState::BATTLE) {
            source.simulationCountBase = fightSims(gc, sourceSims);
            search::g_potionKeepValue = potionKeepValue(gc);
        }
        stepFrozenV4Ooc(gc, source);
    }
    t_curPath = nullptr;
    if (targets.empty())
        throw std::runtime_error("oocv4h1rolloutall: source produced no eligible OOC decisions");
    return targets;
}

static std::string v4ActActionDescription(const search::GameAction &action,
                                          const GameContext &gc) {
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState == ScreenState::REWARDS) {
        if (action.getRewardsActionType() == RT::CARD) {
            const int group = action.getIdx1(), card = action.getIdx2();
            if (card == 5) return "special card-reward skip (bits=1280)";
            const auto &r = gc.info.rewardsContainer;
            if (group >= 0 && group < r.cardRewardCount
                && card >= 0 && card < (int)r.cardRewards[group].size())
                return r.cardRewards[group][card].getName();
        }
        if (action.getRewardsActionType() == RT::SKIP)
            return "generic reward-screen SKIP";
    }
    return actionDescription(action, gc);
}

static void requireV4ActRolloutTarget(const V4H1Sample &target) {
    if (target.pre.act != 1 || target.pre.floorNum != 8
        || target.pre.screenState != ScreenState::REWARDS || target.decisionIdx != 11
        || target.actions.size() != 5)
        throw std::runtime_error("oocv4h1rollout: source target is not Act 1 floor 8 decision 11");
    const std::vector<std::string> expected = {
        "Pommel Strike", "Warcry", "Whirlwind", "generic reward-screen SKIP",
        "special card-reward skip"};
    bool sawSpecialSkip = false;
    for (int i = 0; i < 5; ++i) {
        const std::string desc = v4ActActionDescription(target.actions[i], target.pre);
        if (desc.find(expected[i]) == std::string::npos)
            throw std::runtime_error("oocv4h1rollout: unexpected action mapping at index "
                                     + std::to_string(i) + ": " + desc);
        if (target.actions[i].bits == 1280) sawSpecialSkip = true;
    }
    if (!sawSpecialSkip)
        throw std::runtime_error("oocv4h1rollout: special card skip bits=1280 missing");
}

static void v4ActRolloutCanary() {
    if (v4ActRolloutSeed(984123, 0) != v4ActRolloutSeed(984123, 0)
        || v4ActRolloutSeed(984123, 0) == v4ActRolloutSeed(984123, 1)
        || v4ActCombatSeed(7, 1, 0) != v4ActCombatSeed(7, 1, 0)
        || v4ActCombatSeed(7, 1, 0) == v4ActCombatSeed(7, 2, 0))
        throw std::runtime_error("oocv4h1rollout canary failed: seed pairing is not deterministic");
    std::cout << "oocv4h1rollout canary PASS\n";
}

static void evaluateV4ActRollout(std::uint64_t seed, int decision, int rollouts,
                                 int silverSims, int asc, const std::string &outFile,
                                 const std::string &teacherPath) {
    if (seed != 984123 || decision != 11 || rollouts < 1 || silverSims < 1 || asc != 0)
        throw std::runtime_error("oocv4h1rollout: frozen seed/decision/rollout configuration mismatch");
    requireV4H1Comparator(true);
    const V4H1Sample target = replayV4ActRolloutTarget(seed, decision, 1000, asc);
    requireV4ActRolloutTarget(target);
    const bool staleTeacher = std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")
        && std::atoi(std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")) != 0;
    const auto teacher = switchToV4H1Teacher(teacherPath, 10000);
    std::ofstream out(outFile + ".partial");
    if (!out) throw std::runtime_error("oocv4h1rollout: cannot open output");
    out << "sourceSeed,decisionIdx,actionIdx,actionBits,actionSemantic,rolloutIndex,rolloutSeed,"
           "floor,roomClass,encounter,encounterCount,encounterProbability,combatSeed,silverSimulations,"
           "silverBackendSimulations,silverWin,terminalOutcome,postCombatVStateWin,weightedContribution,valid\n";
    std::map<std::pair<int, int>, int> counts;
    struct Cell { int action = 0; int rollout = 0; std::uint64_t rolloutSeed = 0, combatSeed = 0;
        V4ActRolloutObservation obs; };
    std::vector<Cell> cells;
    for (int ri = 0; ri < rollouts; ++ri) {
        const std::uint64_t rolloutSeed = v4ActRolloutSeed(seed, ri);
        GameContext hiddenBase = detachedCounterfactualCopy(target.pre);
        resampleRemainingActEncounters(hiddenBase, rolloutSeed);
        for (int ai = 0; ai < 5; ++ai) {
            GameContext branch = detachedCounterfactualCopy(hiddenBase);
            target.actions[ai].execute(branch);
            PathHistory branchPath = target.path;
            search::ScumSearchAgent2 agent; agent.simulationCountBase = 0;
            agent.rng = std::default_random_engine(rolloutSeed);
            std::vector<V4ActRolloutObservation> observations;
            if (!advanceRandomActNoFight(branch, agent, branchPath, 1, observations))
                throw std::runtime_error("oocv4h1rollout: lightweight Act 1 transition did not complete"
                    " action=" + std::to_string(ai) + " rollout=" + std::to_string(ri)
                    + " observations=" + std::to_string(observations.size())
                    + " screen=" + std::to_string((int)branch.screenState)
                    + " act=" + std::to_string(branch.act)
                    + " floor=" + std::to_string(branch.floorNum)
                    + " outcome=" + std::to_string((int)branch.outcome));
            for (int oi = 0; oi < (int)observations.size(); ++oi) {
                const int enc = (int)observations[oi].encounter;
                ++counts[{ai, enc}];
                cells.push_back({ai, ri, rolloutSeed,
                                 v4ActCombatSeed(rolloutSeed, enc, oi),
                                 std::move(observations[oi])});
            }
        }
    }
    std::vector<double> scoreSum(5, 0.0), scoreWeight(5, 0.0);
    std::vector<int> cellCount(5, 0);
    struct CellResult {
        std::uint64_t actualSims = 0;
        std::uint64_t silverDecisions = 0;
        bool workerSilverInstalled = false;
        bool won = false;
        double value = 0.0;
        bool valid = false;
    };
    std::vector<CellResult> results(cells.size());
    auto runSilverCell = [&](const Cell &cell) {
        CellResult result;
        result.workerSilverInstalled = search::silverLiveBackendInstalled();
        if (!result.workerSilverInstalled) return result;
        GameContext local = detachedCounterfactualCopy(cell.obs.battleEntry);
        search::ScumSearchAgent2 fight; fight.simulationCountBase = silverSims;
        fight.rng = std::default_random_engine(cell.combatSeed);
        BattleContext bc{}; bc.init(local, cell.obs.encounter);
        const int healthBefore = search::g_simHealthFailureCount;
        const std::int64_t before = fight.simulationCountTotal;
        fight.playoutBattle(bc);
        result.actualSims = (std::uint64_t)std::max<std::int64_t>(
            0, fight.simulationCountTotal - before);
        result.silverDecisions = search::g_silverLiveDiagnostics.decisions;
        result.won = bc.outcome == Outcome::PLAYER_VICTORY;
        bc.exitBattle(local);
        result.valid = search::isValidTrainingTerminal(true, healthBefore,
            search::g_simHealthFailureCount, false);
        if (result.won)
            result.value = local.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : vStateWin(local);
        return result;
    };
    if (cells.empty())
        throw std::runtime_error("oocv4h1rollout: no observed combat cells");
    // Fixed probes prove both the per-thread install contract and CRN
    // determinism before the full queue is released.
    const int workerCount = std::max(1, numThreads());
    const int probeCount = std::min((int)cells.size(), workerCount);
    std::vector<CellResult> serialProbe(probeCount), parallelProbe(probeCount);
#ifdef _OPENMP
    omp_set_dynamic(0);
    omp_set_num_threads(1);
#endif
    for (int i = 0; i < probeCount; ++i)
        serialProbe[i] = runSilverCell(cells[i]);
#ifdef _OPENMP
    omp_set_num_threads(workerCount);
#endif
    #pragma omp parallel
    {
        #pragma omp for schedule(static)
        for (int i = 0; i < probeCount; ++i)
            parallelProbe[i] = runSilverCell(cells[i]);
    }
    for (int i = 0; i < probeCount; ++i) {
        const auto &a = serialProbe[i], &b = parallelProbe[i];
        if (!b.workerSilverInstalled || b.actualSims == 0
            || a.won != b.won || std::abs(a.value - b.value) > 1e-12)
            throw std::runtime_error("oocv4h1rollout: Silver worker canary failed at probe "
                + std::to_string(i));
    }
    if (serialProbe[0].actualSims == 0)
        throw std::runtime_error("oocv4h1rollout: serial Silver canary reported no simulations");
    #ifdef _OPENMP
    omp_set_num_threads(workerCount);
    #endif
    // Rollout generation and seed assignment stay serial and deterministic;
    // only independent Silver cells are parallelized. OMP_NUM_THREADS controls
    // the worker count, matching the other combat benchmarks in this binary.
    #pragma omp parallel
    {
        #pragma omp for schedule(dynamic)
        for (int ci = 0; ci < (int)cells.size(); ++ci)
            results[ci] = runSilverCell(cells[ci]);
    }
    for (const auto &result : results)
        if (!result.workerSilverInstalled || result.actualSims == 0)
            throw std::runtime_error("oocv4h1rollout: a Silver worker reported no Silver activity");
    for (int ci = 0; ci < (int)cells.size(); ++ci) {
        const auto &cell = cells[ci];
        const auto &result = results[ci];
        const int encounterCount = counts[{cell.action, (int)cell.obs.encounter}];
        const double contribution = result.value / std::max(1, rollouts);
        scoreSum[cell.action] += result.value;
        scoreWeight[cell.action] += 1.0;
        ++cellCount[cell.action];
        out << seed << ',' << decision << ',' << cell.action << ',' << target.actions[cell.action].bits
            << ',' << csvQuote(v4ActActionDescription(target.actions[cell.action], target.pre)) << ','
            << cell.rollout << ',' << cell.rolloutSeed << ',' << cell.obs.floor << ','
            << (int)cell.obs.room << ',' << monsterEncounterEnumNames[(int)cell.obs.encounter] << ','
            << encounterCount << ',' << ((double)encounterCount / std::max(1, rollouts)) << ','
            << cell.combatSeed << ',' << silverSims << ',' << result.actualSims << ',' << result.won << ','
            << (result.won ? 1 : 0) << ',' << result.value << ',' << contribution << ','
            << (result.valid ? 1 : 0) << '\n';
    }
    out.close();
    if (!out) throw std::runtime_error("oocv4h1rollout: failed to finish CSV");
    std::filesystem::rename(outFile + ".partial", outFile);
    std::ofstream json(outFile + ".json");
    std::ofstream report(outFile + ".report.txt");
    if (!json || !report) throw std::runtime_error("oocv4h1rollout: cannot open summary output");
    GameContext genericSkip = detachedCounterfactualCopy(target.pre);
    GameContext specialSkip = detachedCounterfactualCopy(target.pre);
    target.actions[3].execute(genericSkip);
    target.actions[4].execute(specialSkip);
    const bool skipsRedundant = stratFingerprint(genericSkip) == stratFingerprint(specialSkip);
    json << "{\"sourceSeed\":" << seed << ",\"decisionIdx\":" << decision
         << ",\"rollouts\":" << rollouts << ",\"silverSimulations\":" << silverSims
         << ",\"silverWorkerThreads\":" << numThreads()
         << ",\"teacherId\":" << nlohmann::json(teacher.id).dump()
         << ",\"teacherProvenance\":"
         << nlohmann::json(staleTeacher ? "stale_manifest_allowed" : "exact").dump()
         << ",\"genericAndSpecialSkipRedundant\":" << (skipsRedundant ? "true" : "false")
         << ",\"encounterDistribution\":[";
    bool firstEncounter = true;
    for (const auto &[key, count] : counts) {
        if (!firstEncounter) json << ',';
        firstEncounter = false;
        json << "{\"actionIdx\":" << key.first << ",\"encounter\":"
             << nlohmann::json(monsterEncounterEnumNames[key.second]).dump()
             << ",\"count\":" << count << ",\"probability\":"
             << ((double)count / std::max(1, rollouts)) << "}";
    }
    json << "],\"actions\":[";
    report << "source seed=" << seed << " decisionIdx=" << decision << " rollouts=" << rollouts
           << " silverSimulations=" << silverSims << " silverWorkerThreads=" << numThreads()
           << " teacher_provenance=" << (staleTeacher ? "stale_manifest_allowed" : "exact") << "\n";
    report << "encounter distribution (action, identity, count, probability):\n";
    for (const auto &[key, count] : counts)
        report << key.first << " " << monsterEncounterEnumNames[key.second] << " "
               << count << " " << ((double)count / std::max(1, rollouts)) << "\n";
    int selected = -1; double best = -1.0;
    for (int ai = 0; ai < 5; ++ai) {
        const double score = scoreSum[ai] / std::max(1.0, scoreWeight[ai]);
        if (score > best) { best = score; selected = ai; }
        if (ai) json << ',';
        json << "{\"actionIdx\":" << ai << ",\"bits\":" << target.actions[ai].bits
             << ",\"description\":" << nlohmann::json(v4ActActionDescription(target.actions[ai], target.pre)).dump()
             << ",\"cells\":" << cellCount[ai] << ",\"score\":" << score << "}";
        report << ai << " " << v4ActActionDescription(target.actions[ai], target.pre)
               << " weighted_score=" << score << " cells=" << cellCount[ai] << "\n";
    }
    json << "],\"selectedAction\":" << selected << "}\n";
    report << "selected_action=" << selected << "\n";
    report << "generic_skip_vs_special_skip=" << (skipsRedundant ? "redundant" : "distinct") << "\n";
}

static void evaluateV4ActRolloutAll(std::uint64_t seed, int rollouts, int silverSims,
                                    int asc, const std::string &outFile,
                                    const std::string &teacherPath) {
    if (seed != 984123 || rollouts < 1 || silverSims < 1 || asc != 0)
        throw std::runtime_error("oocv4h1rolloutall: frozen seed/rollout configuration mismatch");
    requireV4H1Comparator(true);
    const auto targets = replayV4ActRolloutTargets(seed, 1000, asc);
    const bool staleTeacher = std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")
        && std::atoi(std::getenv("STS_V4H1_ROLLOUT_ALLOW_STALE_TEACHER")) != 0;
    const auto teacher = switchToV4H1Teacher(teacherPath, 10000);
    std::ofstream out(outFile + ".partial");
    if (!out) throw std::runtime_error("oocv4h1rolloutall: cannot open output");
    out << "sourceSeed,decisionIdx,actionIdx,actionBits,actionSemantic,rolloutIndex,rolloutSeed,"
           "floor,roomClass,encounter,encounterCount,encounterProbability,combatSeed,silverSimulations,"
           "silverBackendSimulations,silverWin,terminalOutcome,postCombatVStateWin,weightedContribution,valid\n";
    using CountKey = std::tuple<int, int, int>;
    std::map<CountKey, int> counts;
    struct Cell { int target = 0, action = 0, rollout = 0; std::uint64_t rolloutSeed = 0, combatSeed = 0;
        V4ActRolloutObservation obs; };
    std::vector<Cell> cells;
    for (int ti = 0; ti < (int)targets.size(); ++ti) {
        const auto &target = targets[ti];
        for (int ri = 0; ri < rollouts; ++ri) {
            const std::uint64_t rolloutSeed = v4ActRolloutSeed(seed,
                ri + ti * rollouts);
            GameContext hiddenBase = detachedCounterfactualCopy(target.pre);
            resampleRemainingActEncounters(hiddenBase, rolloutSeed);
            for (int ai = 0; ai < (int)target.actions.size(); ++ai) {
                GameContext branch = detachedCounterfactualCopy(hiddenBase);
                target.actions[ai].execute(branch);
                PathHistory branchPath = target.path;
                search::ScumSearchAgent2 agent; agent.simulationCountBase = 0;
                agent.rng = std::default_random_engine(rolloutSeed);
                std::vector<V4ActRolloutObservation> observations;
                if (!advanceRandomActNoFight(branch, agent, branchPath, target.pre.act, observations))
                    throw std::runtime_error("oocv4h1rolloutall: lightweight target-act transition did not complete"
                        " decision=" + std::to_string(target.decisionIdx)
                        + " action=" + std::to_string(ai) + " rollout=" + std::to_string(ri)
                        + " act=" + std::to_string(target.pre.act)
                        + " floor=" + std::to_string(target.pre.floorNum)
                        + " screen=" + std::to_string((int)target.pre.screenState)
                        + " endAct=" + std::to_string(branch.act)
                        + " endFloor=" + std::to_string(branch.floorNum)
                        + " endScreen=" + std::to_string((int)branch.screenState)
                        + " outcome=" + std::to_string((int)branch.outcome)
                        + " observations=" + std::to_string(observations.size()));
                for (int oi = 0; oi < (int)observations.size(); ++oi) {
                    const int enc = (int)observations[oi].encounter;
                    const CountKey key{ti, ai, enc};
                    ++counts[key];
                    cells.push_back({ti, ai, ri, rolloutSeed,
                                     v4ActCombatSeed(rolloutSeed, enc, oi),
                                     std::move(observations[oi])});
                }
            }
        }
    }
    struct CellResult { std::uint64_t actualSims = 0, silverDecisions = 0;
        bool workerSilverInstalled = false, won = false;
        double value = 0.0; bool valid = false; };
    std::vector<CellResult> results(cells.size());
    auto runSilverCell = [&](const Cell &cell) {
        CellResult result;
        result.workerSilverInstalled = search::silverLiveBackendInstalled();
        if (!result.workerSilverInstalled) return result;
        GameContext local = detachedCounterfactualCopy(cell.obs.battleEntry);
        search::ScumSearchAgent2 fight; fight.simulationCountBase = silverSims;
        fight.rng = std::default_random_engine(cell.combatSeed);
        BattleContext bc{}; bc.init(local, cell.obs.encounter);
        const int healthBefore = search::g_simHealthFailureCount;
        const std::int64_t before = fight.simulationCountTotal;
        fight.playoutBattle(bc);
        result.actualSims = (std::uint64_t)std::max<std::int64_t>(
            0, fight.simulationCountTotal - before);
        result.silverDecisions = search::g_silverLiveDiagnostics.decisions;
        result.won = bc.outcome == Outcome::PLAYER_VICTORY;
        bc.exitBattle(local);
        result.valid = search::isValidTrainingTerminal(true, healthBefore,
            search::g_simHealthFailureCount, false);
        if (result.won)
            result.value = local.outcome == GameOutcome::PLAYER_VICTORY ? 1.0 : vStateWin(local);
        return result;
    };
    if (cells.empty())
        throw std::runtime_error("oocv4h1rolloutall: no observed combat cells");
    const int workerCount = std::max(1, numThreads());
    const int probeCount = std::min((int)cells.size(), workerCount);
    std::vector<CellResult> serialProbe(probeCount), parallelProbe(probeCount);
    std::atomic<std::uint64_t> workerMask{0};
#ifdef _OPENMP
    omp_set_dynamic(0);
    omp_set_num_threads(1);
#endif
    for (int i = 0; i < probeCount; ++i)
        serialProbe[i] = runSilverCell(cells[i]);
#ifdef _OPENMP
    omp_set_num_threads(workerCount);
#endif
    #pragma omp parallel
    {
#ifdef _OPENMP
        const int tid = omp_get_thread_num();
        if (tid < 64) workerMask.fetch_or(1ULL << tid);
#else
        workerMask.fetch_or(1ULL);
#endif
        #pragma omp for schedule(static)
        for (int i = 0; i < probeCount; ++i)
            parallelProbe[i] = runSilverCell(cells[i]);
    }
    for (int i = 0; i < probeCount; ++i) {
        const auto &a = serialProbe[i], &b = parallelProbe[i];
        if (!b.workerSilverInstalled || b.actualSims == 0
            || a.won != b.won || std::abs(a.value - b.value) > 1e-12
            || a.actualSims != b.actualSims)
            throw std::runtime_error("oocv4h1rolloutall: Silver worker canary failed at probe "
                + std::to_string(i) + " serial(inst=" + std::to_string(a.workerSilverInstalled)
                + ",decisions=" + std::to_string(a.silverDecisions)
                + ",sims=" + std::to_string(a.actualSims) + ",won=" + std::to_string(a.won)
                + ",value=" + std::to_string(a.value) + ") parallel(inst="
                + std::to_string(b.workerSilverInstalled) + ",decisions="
                + std::to_string(b.silverDecisions) + ",sims=" + std::to_string(b.actualSims)
                + ",won=" + std::to_string(b.won) + ",value=" + std::to_string(b.value) + ")");
    }
    if (serialProbe[0].actualSims == 0)
        throw std::runtime_error("oocv4h1rolloutall: serial Silver canary reported no simulations");
    if (workerCount >= 64 || workerMask.load() != ((1ULL << workerCount) - 1))
        throw std::runtime_error("oocv4h1rolloutall: not every configured worker ran the Silver canary");
#ifdef _OPENMP
    omp_set_num_threads(workerCount);
#endif
    #pragma omp parallel
    {
        #pragma omp for schedule(dynamic)
        for (int ci = 0; ci < (int)cells.size(); ++ci)
            results[ci] = runSilverCell(cells[ci]);
    }
    for (const auto &result : results)
        if (!result.workerSilverInstalled || result.actualSims == 0)
            throw std::runtime_error("oocv4h1rolloutall: a Silver worker reported no Silver activity");
    std::vector<std::vector<double>> scoreSum(targets.size()), scoreWeight(targets.size());
    std::vector<std::vector<int>> cellCount(targets.size());
    for (int ti = 0; ti < (int)targets.size(); ++ti) {
        scoreSum[ti].assign(targets[ti].actions.size(), 0.0);
        scoreWeight[ti].assign(targets[ti].actions.size(), 0.0);
        cellCount[ti].assign(targets[ti].actions.size(), 0);
    }
    for (int ci = 0; ci < (int)cells.size(); ++ci) {
        const auto &cell = cells[ci]; const auto &target = targets[cell.target];
        const auto &result = results[ci];
        const CountKey key{cell.target, cell.action, (int)cell.obs.encounter};
        const int encounterCount = counts[key];
        const double contribution = result.value / std::max(1, rollouts);
        scoreSum[cell.target][cell.action] += result.value;
        scoreWeight[cell.target][cell.action] += 1.0;
        ++cellCount[cell.target][cell.action];
        out << seed << ',' << target.decisionIdx << ',' << cell.action << ','
            << target.actions[cell.action].bits << ','
            << csvQuote(v4ActActionDescription(target.actions[cell.action], target.pre)) << ','
            << cell.rollout << ',' << cell.rolloutSeed << ',' << cell.obs.floor << ','
            << (int)cell.obs.room << ',' << monsterEncounterEnumNames[(int)cell.obs.encounter] << ','
            << encounterCount << ',' << ((double)encounterCount / std::max(1, rollouts)) << ','
            << cell.combatSeed << ',' << silverSims << ',' << result.actualSims << ',' << result.won << ','
            << (result.won ? 1 : 0) << ',' << result.value << ',' << contribution << ','
            << (result.valid ? 1 : 0) << '\n';
    }
    out.close();
    if (!out) throw std::runtime_error("oocv4h1rolloutall: failed to finish CSV");
    std::filesystem::rename(outFile + ".partial", outFile);
    std::ofstream json(outFile + ".json");
    std::ofstream report(outFile + ".report.txt");
    if (!json || !report) throw std::runtime_error("oocv4h1rolloutall: cannot open summary output");
    json << "{\"sourceSeed\":" << seed << ",\"decisionCount\":" << targets.size()
         << ",\"rollouts\":" << rollouts << ",\"silverSimulations\":" << silverSims
         << ",\"silverWorkerThreads\":" << numThreads()
         << ",\"silverWorkerCanary\":\"pass\",\"silverWorkerMask\":" << workerMask.load()
         << ",\"teacherId\":" << nlohmann::json(teacher.id).dump()
         << ",\"teacherProvenance\":"
         << nlohmann::json(staleTeacher ? "stale_manifest_allowed" : "exact").dump()
         << ",\"decisions\":[";
    report << "source seed=" << seed << " decisionCount=" << targets.size()
           << " rollouts=" << rollouts << " silverSimulations=" << silverSims
           << " silverWorkerThreads=" << numThreads() << " silverWorkerCanary=pass"
           << " silverWorkerMask=" << workerMask.load() << " teacher_provenance="
           << (staleTeacher ? "stale_manifest_allowed" : "exact") << "\n";
    for (int ti = 0; ti < (int)targets.size(); ++ti) {
        const auto &target = targets[ti];
        if (ti) json << ',';
        json << "{\"decisionIdx\":" << target.decisionIdx << ",\"floor\":"
             << target.pre.floorNum << ",\"actions\":[";
        report << "decision=" << target.decisionIdx << " act=" << target.pre.act
               << " floor=" << target.pre.floorNum << " actions=" << target.actions.size() << "\n";
        int selected = -1; double best = -1.0;
        for (int ai = 0; ai < (int)target.actions.size(); ++ai) {
            const double score = scoreSum[ti][ai] / std::max(1.0, scoreWeight[ti][ai]);
            if (score > best) { best = score; selected = ai; }
            if (ai) json << ',';
            json << "{\"actionIdx\":" << ai << ",\"bits\":" << target.actions[ai].bits
                 << ",\"description\":"
                 << nlohmann::json(v4ActActionDescription(target.actions[ai], target.pre)).dump()
                 << ",\"cells\":" << cellCount[ti][ai] << ",\"score\":" << score << "}";
            report << "  " << ai << " " << v4ActActionDescription(target.actions[ai], target.pre)
                   << " weighted_score=" << score << " cells=" << cellCount[ti][ai] << "\n";
        }
        json << "],\"selectedAction\":" << selected << "}";
        report << "  selected_action=" << selected << "\n";
    }
    json << "]}\n";
}

struct MargResult { double won, hp, floor, boot; int survivedH; };

static MargResult finishMargCf(GameContext gc, std::uint64_t branchSeed,
                                const PathHistory &path) {
    OocCounterfactualResult r = evaluateStrategicBranch(
        std::move(gc), branchSeed, path);
    return {r.won, r.hp, r.floor, (double)r.bootstrapped, r.survivedH ? 1 : 0};
}

static void strategicMargGen(int nSeeds, int outerSims,
                             int H, int maxPerRun, const std::string &outFile,
                             long long seedOffset) {
    std::ofstream out(outFile);
    out << "seed,decIdx,act,floor,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,"
           "continuationSeed,hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,utility,"
           "survivedH,continuationValue,qSample,"
           "fallbackIdx,fallbackExact,chosenIdx,chosenExact,"
           "v4ModelIdx,v4Margin,v4Threshold,v4Fired,v4ExecutedIdx,v4Override,"
           "richState,actionBits,actionType,c1,c2,c3,cand1,cand2,cand3,hiddenChanged,"
           "sourceWon,sourceFloor,sourceHp\n";
    out.flush();
    auto t0 = std::chrono::steady_clock::now();
    std::mutex outMtx;
    int totalDecisions = 0;
    const double v4Threshold = g_oocStrategicMargin;

    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::uint64_t seed = (std::uint64_t)(seedOffset + s);

        // ── Pass 1: play full source run, collect eligible decision snapshots ──
        struct DecisionSnap {
            GameContext pre;
            PathHistory prePath;
            std::vector<search::GameAction> actions;
            int decIdx, screen, gateKind, actNum, floorNum;
            std::string stateRow;
        };
        std::vector<DecisionSnap> snaps;
        {
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            int decIdx = 0;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                int screen = (int)gc.screenState;
                int gateKind = 0;
                bool isOwned = false;
                if (screen == 1) { gateKind = 1; isOwned = true; }
                else if (screen == 2) { auto &r = gc.info.rewardsContainer; if (r.cardRewardCount > 0) { gateKind = 2; isOwned = true; } }
                else if (screen == 3) { gateKind = 3; isOwned = true; }
                else if (screen == 4) { if (gc.info.selectScreenType == CardSelectScreenType::UPGRADE) { gateKind = 4; isOwned = true; } }
                else if (screen == 6) { gateKind = 5; isOwned = true; }
                else if (screen == 7) { gateKind = 6; isOwned = true; }
                else if (screen == 8) { gateKind = 7; isOwned = true; }

                if (isOwned) {
                    GameContext pre = detachedCounterfactualCopy(gc);
                    auto actions = search::GameAction::getAllActionsInState(gc);
                    if (actions.size() >= 2) {
                        snaps.push_back({std::move(pre), path, std::move(actions),
                                         decIdx, screen, gateKind, gc.act, gc.floorNum,
                                         richRow(pre, path)});
                    }
                    ++decIdx;
                }
                stepFrozenV4Ooc(gc, agent);
            }
            t_curPath = nullptr;
        }

        // ── Uniform sample up to maxPerRun decisions ──
        int nSnaps = (int)snaps.size();
        int nSample = std::min(maxPerRun, nSnaps);
        if (nSnaps > maxPerRun) {
            std::mt19937_64 rng(seed ^ 0x9e3779b97f4a7c15ULL);
            for (int i = 0; i < nSample; ++i) {
                int j = i + (int)(rng() % (std::uint64_t)(nSnaps - i));
                std::swap(snaps[i], snaps[j]);
            }
        }
        snaps.resize(nSample);

        // ── Pass 2: evaluate sampled decisions ──
        std::ostringstream local;
        int localDecisions = 0;
        int sourceWon = 0, sourceFloor = 0, sourceHp = 0;
        {
            // Re-run the source game to get terminal outcome
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                stepFrozenV4Ooc(gc, agent);
            }
            sourceWon = (gc.outcome == GameOutcome::PLAYER_VICTORY) ? 1 : 0;
            sourceFloor = gc.floorNum;
            sourceHp = gc.curHp;
            t_curPath = nullptr;
        }

        {
            search::ScumSearchAgent2 evalAgent;
            evalAgent.simulationCountBase = outerSims;
            evalAgent.rng = std::default_random_engine(seed);
        for (auto &snap : snaps) {
            auto &pre = snap.pre; auto &prePath = snap.prePath;
            auto &actions = snap.actions;
            int screen = snap.screen, gateKind = snap.gateKind;
            int actNum = snap.actNum, floorNum = snap.floorNum;
            int decIdx = snap.decIdx;
            std::string &stateRow = snap.stateRow;

            // Per-action metadata
            std::vector<std::string> actionMetas;
            for (int ai = 0; ai < (int)actions.size(); ++ai) {
                int at, c1v, c2v, c3v, ca1, ca2, ca3;
                strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                char buf[256];
                std::snprintf(buf, sizeof(buf), "%u,%d,%d,%d,%d,%d,%d,%d",
                              actions[ai].bits, at, c1v, c2v, c3v, ca1, ca2, ca3);
                actionMetas.push_back(buf);
            }

            // Fallback via fingerprint (abbreviated — identical to existing code)
            int fallbackIdx = -1, fallbackExact = 0;
            {
                GameContext fbGc = detachedCounterfactualCopy(pre);
                if (screen == 1) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 2) one_combat::serverCardRewardPolicy(fbGc);
                else if (screen == 3) { if (g_bossRelicV) one_combat::bossRelicVPolicy(fbGc); else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 4) one_combat::upgradeSelectWinPolicy(fbGc);
                else if (screen == 6) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 7) { if (g_restWin && one_combat::restWinPolicy(fbGc)) {} else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 8) one_combat::shopVPolicy(fbGc);
                auto fbFp = stratFingerprint(fbGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == fbFp) {
                        if (fallbackIdx < 0) { fallbackIdx = ai; fallbackExact = 1; }
                        else { fallbackExact = 0; break; }
                    }
                }
            }

            // Source chosen
            int chosenIdx = -1, chosenExact = 0;
            {
                GameContext postGc = detachedCounterfactualCopy(pre);
                stepFrozenV4Ooc(postGc, evalAgent);
                auto postFp = stratFingerprint(postGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == postFp) {
                        if (chosenIdx < 0) { chosenIdx = ai; chosenExact = 1; }
                        else { chosenExact = 0; break; }
                    }
                }
            }

            // V4 predictions
            int v4BestIdx = -1; double v4Margin = 0; bool v4Fired = false;
            if (g_oocStrategicTokNet.ok) {
                TokState ts = buildTokState(pre, prePath);
                double bestV4 = -1e100, secondV4 = -1e100;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    int at, c1v, c2v, c3v, ca1, ca2, ca3;
                    strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                    const int cats[6] = {c1v, c2v, c3v, ca1, ca2, ca3};
                    int et, ei; float gg;
                    tokEntity(pre, actions[ai], et, ei, gg);
                    const float entT[4] = {et==0?1.f:0.f, et==1?1.f:0.f, et==2?1.f:0.f, et==3?1.f:0.f};
                    double v = g_oocStrategicTokNet.predictActionValue(
                        ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                        actions[ai].bits, cats, at, screen, entT, ei, gg);
                    if (v > bestV4) { secondV4 = bestV4; bestV4 = v; v4BestIdx = ai; }
                    else if (v > secondV4) secondV4 = v;
                }
                v4Margin = bestV4 - secondV4;
                v4Fired = v4Margin >= v4Threshold;
            }
            int v4ExecutedIdx = (v4Fired && v4BestIdx >= 0) ? v4BestIdx : fallbackIdx;
            int v4Override = (fallbackExact == 1 && v4Fired && v4BestIdx >= 0 && v4BestIdx != fallbackIdx) ? 1 : 0;

            std::uint64_t baseSeed = seed ^ ((std::uint64_t)decIdx * 0x9e3779b97f4a7c15ULL);
            if (!baseSeed) baseSeed = 1;

            // EMIT_ROW macro (same as before)
            #define EMIT_ROW(regimeStr, contSeed, hiddenSeedVal, hiddenChangedVal) \
                local << seed << ',' << decIdx << ',' << actNum << ',' << floorNum \
                      << ',' << screen << ',' << gateKind << ',' << ai << ',' \
                      << actions.size() << ',' << h << ',' << regimeStr << ',' << contSeed << ',' << hiddenSeedVal << ',' \
                      << r.won << ',' << r.hp << ',' << r.floor << ',' << r.boot << ',' \
                      << (10.0*r.won+r.hp) << ',' << r.survivedH << ',' << r.won << ',' \
                      << (r.survivedH * r.won) << ',' << fallbackIdx << ',' << fallbackExact << ',' \
                      << chosenIdx << ',' << chosenExact << ',' \
                      << v4BestIdx << ',' << v4Margin << ',' << v4Threshold << ',' \
                      << (v4Fired?1:0) << ',' << v4ExecutedIdx << ',' << v4Override << ',' \
                      << csvQuote(stateRow) << ',' << actionMetas[ai] << ',' << hiddenChangedVal << ",0,0,0\n";

            // Regime F, I, M (identical to existing)
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("fixed", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < std::min(H, 2); ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg_id", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                std::uint64_t hiddenSeed = baseSeed ^ ((std::uint64_t)(h + H) * 0x9e3779b97f4a7c15ULL);
                if (!contSeed) contSeed = 1; if (!hiddenSeed) hiddenSeed = 1;
                GameContext hiddenBase = detachedCounterfactualCopy(pre);
                std::uint64_t hashBefore = 0, hashAfter = 0;
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                resampleRemainingActEncounters(hiddenBase, hiddenSeed);
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                int hiddenChanged = (hashBefore != hashAfter) ? 1 : 0;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(hiddenBase);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg", contSeed, hiddenSeed, hiddenChanged)
                }
            }
            #undef EMIT_ROW
            ++localDecisions;
        }
        }  // end evalAgent scope

        // Source outcome post-processing
        std::string prefix = std::to_string(sourceWon) + "," + std::to_string(sourceFloor) + "," + std::to_string(sourceHp);
        std::string localStr = local.str();
        std::string from = ",0,0,0\n";
        std::string to = "," + prefix + "\n";
        size_t pos = 0;
        while ((pos = localStr.find(from, pos)) != std::string::npos) {
            localStr.replace(pos, from.length(), to);
            pos += to.length();
        }

        #pragma omp critical(marg_write4)
        {
            out << localStr; out.flush();
            totalDecisions += localDecisions;
            if (totalDecisions % 10 == 0 || totalDecisions <= 5) {
                double el = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d decisions, %.0fs (%.1fs/dec)\n",
                            totalDecisions, el, el / std::max(1, totalDecisions));
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %d decisions to %s in %.1fs\n", totalDecisions, outFile.c_str(), wall);
}

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

static void oocFactorEvaluate(const std::string &manifestFile,
                              const std::string &outFile, int referenceSims,
                              int futures, int futureStart, int expectedDecisions,
                              bool marginalTradeoff = false,
                              bool boundedK3 = false,
                              bool semanticFullRun = false) {
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

static void stepCounterfactualAuditSource(GameContext &gc,
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

static void oocBudgetEvaluate(const std::string &manifestFile,
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
    if(!search::silverLiveBackendInstalled()||!search::silverLiveExactRootBudgets()
        ||search::silverLiveReuseCapMode()!="allocated"||search::silverLiveReuseCap()!=32768
        ||search::silverLiveAdaptiveEnabled())
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

static void semanticPilotCapture(int count,std::uint64_t offset,const std::string &manifestFile,
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
static void semanticPilotSelfTest() {
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

static void semanticPilotEvaluate(int count,const std::string &manifestFile,const std::string &outFile,
                                  const std::string &teacherFile,const std::string &combatFile = {}) {
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

static void strategicGen(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  -> " << outFile << "\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    writeTrainingProvenance(outFile, "strategicgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}

// ---------------------------------------------------------------------------
// STRATEGICGEN2 (Tier-B): the strategicgen row schema plus one-ply
// counterfactual labels per action.  At each sampled decision, every legal
// action is applied to a detached pre-decision copy and the branch is continued
// with the deployed-default OOC policy through STRATEGIC_BRANCH_FIGHTS battles
// (cheap sims + STS_VNET combat value net leaf), then the expected floor /
// P(win) are bootstrapped from the native trees.  Common random numbers across
// the actions of one decision (same branch seed); STRATEGIC_BRANCH_FUTURES
// averages over additional branch seeds per action.
// Row schema: strategicHeader() columns, then
//   labelWon,labelHp,labelFloor,labelBootstrap
// (unsampled decisions leave these empty).
static std::string strategicHeader2() {
    std::string h = strategicHeader();
    if (!h.empty() && h.back() == '\n') h.pop_back();
    return h + ",labelWon,labelHp,labelFloor,labelBootstrap\n";
}

static std::string runStrategicGenSeed2(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);

    std::vector<std::string> rows;
    std::vector<std::string> rowLabel;  // per-row Tier-B label suffix ("" when unsampled)
    // Tier-B label sets for sampled decisions: [rowStart,rowEnd) indexes into
    // `rows` (pushed without the label suffix), `labels` holds one label string
    // per action.  In knob mode this is the reservoir: later sampled decisions
    // replace earlier slots so the N kept decisions are uniform over the run.
    std::vector<std::pair<int, int>> labelRanges;
    std::vector<std::vector<std::string>> labelSets;
    int eligible = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);
        const PathHistory prePath = path;
        const int decIdx = (int)rows.size();

        // Sample this decision for Tier-B branching?  Sample-all labels every
        // decision; otherwise uniform reservoir of STRATEGIC_SAMPLES_PER_RUN
        // decisions (replacing an earlier slot means its branch work is lost).
        int labelSlot = -1;
        bool isNewSlot = false;
        if (g_strategicSampleAll) {
            if (!actions.empty()) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            }
        } else if (!actions.empty()) {
            ++eligible;
            if (eligible <= g_strategicSamplesPerRun) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            } else if (std::uniform_int_distribution<int>(1, eligible)(reservoir)
                       <= g_strategicSamplesPerRun) {
                labelSlot = std::uniform_int_distribution<int>(0, g_strategicSamplesPerRun - 1)(reservoir);
            }
        }
        if (labelSlot >= 0) {
            auto &labels = labelSets[labelSlot];
            labels.resize(actions.size());
            for (int a = 0; a < (int)actions.size(); ++a) {
                double won = 0, hp = 0, floor = 0, boot = 0;
                bool branchInvalid = false;
                for (int f = 0; f < g_strategicBranchFutures; ++f) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[a].execute(branch);
                    const std::uint64_t branchSeed =
                        seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                             ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(decIdx + 31));
                    const OocCounterfactualResult r = finishOocCounterfactual(
                        std::move(branch), sims, branchSeed, prePath,
                        g_strategicBranchFights, /*bootstrap=*/true,
                        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
                    if (r.bootstrapped < 0) { branchInvalid = true; break; }
                    won += r.won; hp += r.hp; floor += r.floor; boot += r.bootstrapped;
                }
                if (branchInvalid) {
                    ++g_trainingInvalidBranches;
                    labels.clear();
                    break;
                }
                const int F = std::max(1, g_strategicBranchFutures);
                char buf[128];
                std::snprintf(buf, sizeof(buf), "%.6f,%.6f,%.6f,%.6f",
                              won / F, hp / F, floor / F, boot / F);
                labels[a] = buf;
            }
            if (isNewSlot)
                labelRanges.emplace_back((int)rows.size(), (int)rows.size() + (int)actions.size());
            else
                labelRanges[labelSlot] = {(int)rows.size(), (int)rows.size() + (int)actions.size()};
        }

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else Searcher2.
        if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        for (int a = 0; a < (int)actions.size(); ++a) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            actions[a].execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, actions[a], actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << actions[a].bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
    }
    t_curPath = nullptr;

    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    // Append the surviving Tier-B labels to their decision's rows.  The labels
    // belong AFTER the terminal won/endFloor/endHp columns, so store them in
    // rowLabel and emit them after the terminal fields below.
    for (int s = 0; s < (int)labelRanges.size(); ++s) {
        const auto &[lo, hi] = labelRanges[s];
        const auto &labels = labelSets[s];
        for (int i = lo; i < hi; ++i)
            if (i - lo < (int)labels.size()) rowLabel[i] = labels[i - lo];
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (int i = 0; i < (int)rows.size(); ++i)
        out << rows[i] << ',' << won << ',' << gc.floorNum << ',' << gc.curHp
            << (rowLabel[i].empty() ? "" : "," + rowLabel[i]) << '\n';
    return out.str();
}

static void strategicGen2(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen2  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  sampleAll " << g_strategicSampleAll << "  samplesPerRun "
              << g_strategicSamplesPerRun << "  branchFights " << g_strategicBranchFights
              << "  branchSims";
    for (const int s : g_strategicBranchSims) std::cout << ':' << s;
    std::cout << "  futures " << g_strategicBranchFutures << "  -> " << outFile << "\n";
    if (!search::g_useVNet)
        std::cout << "[strategicgen2 WARNING: STS_VNET not loaded; branch battles have no combat value net leaf]\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader2();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed2((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingHealthFailures.load(), rows, outFile.c_str());
    writeTrainingProvenance(outFile, "strategicgen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}

// ---------------------------------------------------------------------------
// COMBINED value+policy datagen: one full-run play emits BOTH the V_combat value
// rows (g_onCombatDecision snapshot, labeled with fight endHp) AND the policy-target
// rows (g_onSearchComplete root visit-π). Halves self-play combat datagen cost vs
// running combatgen + policygen separately, and the two datasets are perfectly
// aligned (same play). Returns {valueRows, policyRows}.
static std::pair<std::string,std::string>
runFightGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);
    PathHistory path;
    t_curPath = &path;

    std::ostringstream val, pol;
    int fightIdx = 0, decIdx = 0;
    std::vector<std::string> fightRows;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onCombatDecision = [&](const BattleContext &bc) {
        fightRows.push_back(combatFeatureRow(bc));
    };
    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        // Advance for every combat decision, including forced/single-edge roots.
        // This keeps decIdx exactly aligned with the value snapshot emitted by
        // g_onCombatDecision, while still omitting useless one-action policy rows.
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        if ((int)edges.size() < 2) return;
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            pol << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) { pol << ','; const float v = feat[i];
                if (v == (float)(long)v) pol << (long)v; else pol << v; }
            pol << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            fightRows.clear(); decIdx = 0;
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onCombatDecision = nullptr;
                search::g_onSearchComplete = nullptr;
                t_curPath = nullptr;
                return {};
            }
            const int won   = bc.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            const int endHp = bc.player.curHp;
            for (const auto &fr : fightRows)
                val << seed << ',' << fightIdx << ',' << fr << ',' << won << ',' << endHp << '\n';
            ++fightIdx;
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                one_combat::serverCardRewardPolicy(gc);                    // deployed V_floor exploit policy
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onCombatDecision = nullptr;
    search::g_onSearchComplete = nullptr;
    t_curPath = nullptr;
    return { val.str(), pol.str() };
}

// ---------------------------------------------------------------------------
static void searchDiag(int nSeeds, int sims, int asc, const std::string &out, int probeEvery,
                       std::uint64_t seedOffset = 0) {
    const int displayProbeEvery = search::g_useSearcher3 && probeEvery > 0 ? 0 : probeEvery;
    if (!one_combat::startSearchDiagnostics(out, probeEvery)) return;
    const std::string fightOut = out + ".fights.csv";
    std::cout << "SEARCHDIAG: seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims/decision " << sims
              << "  asc " << asc << "  probeEvery " << displayProbeEvery
              << "  fair=" << (search::g_fairPlay ? 1 : 0)
              << "  rolloutDepth=" << search::g_maxRolloutDepth
              << "  threads " << numThreads() << "  out " << out
              << "  fights " << fightOut << "\n";
    const bool restV = std::getenv("STS_REST_V") && std::atoi(std::getenv("STS_REST_V")) != 0;
    int wins = 0;
    auto wall0 = std::chrono::steady_clock::now();
    #pragma omp parallel for reduction(+:wins) schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::uint64_t seed = seedOffset + (std::uint64_t)s;
        one_combat::installSearchDiagnosticThreadHooks();
        RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
        one_combat::clearSearchDiagnosticThreadHooks();
        wins += r.won ? 1 : 0;
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    one_combat::stopSearchDiagnostics();
    std::printf("SEARCHDIAG DONE  win%%=%5.1f  wall=%.1fs\n", 100.0 * wins / nSeeds, wall);
}

// POLICY-TARGET datagen (AlphaZero-lite phase 1): at every in-combat decision,
// after the searcher has run its full budget, log each root edge as a row
// (state features ++ that action's features) with the edge's VISIT COUNT and the
// decision's TOTAL visits. Training normalizes visit/total -> the MCTS policy
// target π; the learned comparator net(state,action) then steers PUCT selection.
// Reuses g_onSearchComplete (fires once per agent decision, off the hot path).
static std::string policyHeaderStr() {
    const auto &names = search::combatPolicyFeatureNames();
    std::string h = "seed,fightIdx,decIdx";
    for (const auto &n : names) { h += ','; h += n; }
    h += ",visit,total";
    return h;
}

static std::string runPolicyGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out, fightOut;
    int fightIdx = 0, decIdx = 0;
    const int nf = search::combatPolicyFeatureCount();
    std::vector<float> feat(nf);

    search::g_onSearchComplete = [&](const BattleContext &bc, const search::BattleScumSearcher2 &searcher) {
        const int thisDecIdx = decIdx++;
        const auto &edges = searcher.root.edges;
        const int n = (int)edges.size();
        if (n < 2) return;                       // forced single move -> nothing to learn
        std::int64_t total = 0;
        for (const auto &e : edges) total += e.node.simulationCount;
        if (total <= 0) return;
        for (const auto &e : edges) {
            search::combatExtractPolicyFeatures(bc, e.action, feat.data());
            fightOut << seed << ',' << fightIdx << ',' << thisDecIdx;
            for (int i = 0; i < nf; ++i) {
                fightOut << ',';
                const float v = feat[i];
                if (v == (float)(long)v) fightOut << (long)v; else fightOut << v;
            }
            fightOut << ',' << e.node.simulationCount << ',' << total << '\n';
        }
    };

    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            decIdx = 0;
            fightOut.str(""); fightOut.clear();
            BattleContext bc; bc.init(gc);
            agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                search::g_onSearchComplete = nullptr;
                return {};
            }
            ++fightIdx;
            bc.exitBattle(gc);
            out << fightOut.str();
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (ur(ex) < epsilon) {                     // explore drafting for state diversity
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();
                    const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                    search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                }
            } else {
                evalCardRewardPolicy(gc);
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    search::g_onSearchComplete = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};
    return out.str();
}

static std::string runDataGenSeed(std::uint64_t seed, int sims, int asc, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::vector<std::string> rows;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) return {};
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                rows.push_back(featureRow(gc) + ',' + deckCountsCsv(gc));  // state + deck ids
                if (ur(ex) < epsilon) {                          // explore: random pick among cards + skip
                    while (r.cardRewardCount > 0) {
                        const int rIdx = r.cardRewardCount - 1;
                        const int nc = r.cardRewards[rIdx].size();
                        const int pick = std::uniform_int_distribution<int>(0, nc)(ex);
                        search::GameAction(RT::CARD, rIdx, pick < nc ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);                     // exploit
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum;
    std::ostringstream o;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << '\n';  // seed = run id
    return o.str();
}

// ---------------------------------------------------------------------------
// CAUSAL LABELS: at each card reward, CRN-fork "take card i" vs "skip", play the
// next N fights with common random numbers, and label the card's ADVANTAGE =
// score(take) - score(skip). This measures the true causal effect of the card
// (not just "what losing decks look like"). One row per candidate card.
// ---------------------------------------------------------------------------
// Raw representation (no hand-crafted synergy features): deck as per-card-id
// counts d0..d(kNumCardIds-1) + the candidate card's id; the model (GBM) learns
// which (candidate, deck-card) combinations matter. Plus a few cheap scalars.
// (kNumCardIds / deckCountsCsv defined above featureRow for reuse by datagen.)

static std::string causalContextRow(const GameContext &gc, const Card &c) {
    long obtainSum = 0;
    for (const auto &d : gc.deck.cards) obtainSum += search::Expert::getObtainWeight(d.getId(), d.isUpgraded());
    const int deckSize = gc.deck.size();
    std::ostringstream o;
    o << gc.act << ',' << gc.floorNum << ',' << gc.curHp << ',' << gc.maxHp << ',' << gc.gold << ','
      << deckSize << ',' << (int)gc.relics.relics.size() << ',' << obtainSum << ','
      << (deckSize ? (double)obtainSum / deckSize : 0.0) << ','
      << search::Expert::getObtainWeight(c.getId(), c.isUpgraded()) << ',' << c.getBaseDamage() << ','
      << (c.isUpgraded() ? 1 : 0) << ',' << (int)c.getId();
    return o.str();
}

static std::string causalHeader() {
    std::ostringstream h;
    h << "act,floor,curHp,maxHp,gold,deckSize,nRelics,obtainSum,obtainAvg,"
         "c_obtainWeight,c_baseDamage,c_isUpgraded,candidateId";
    for (int i = 0; i < kNumCardIds; ++i) h << ",d" << i;
    h << ",advantage";
    return h.str();
}

static std::string runCausalGenSeed(std::uint64_t seed, int sims, int asc, int N, int innerSims, int K, double epsilon) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 2862933555777941757ULL + 7);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    std::ostringstream out;
    long decision = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; bc.init(gc); agent.playoutBattle(bc);
            if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) return {};
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else {
                const int rIdx = r.cardRewardCount - 1;
                const int nc = r.cardRewards[rIdx].size();
                const std::uint64_t base = seed * 1000003ULL + (std::uint64_t)decision * 131ULL;
                const std::string dc = deckCountsCsv(gc);        // deck id-counts (same for all candidates)

                // K paired CRN worlds: skip baseline per world, then average card - skip.
                std::vector<double> sSkip(K);
                for (int k = 0; k < K; ++k)
                    sSkip[k] = rolloutChoice(gc, rIdx, 5, N, innerSims, base + k, /*useLabelScore=*/true);
                for (int i = 0; i < nc; ++i) {
                    double adv = 0.0;
                    for (int k = 0; k < K; ++k)
                        adv += rolloutChoice(gc, rIdx, i, N, innerSims, base + k, /*useLabelScore=*/true) - sSkip[k];
                    adv /= K;
                    out << causalContextRow(gc, r.cardRewards[rIdx][i]) << ',' << dc << ',' << adv << '\n';
                }
                ++decision;
                if (ur(ex) < epsilon) {                          // explore to diversify visited states
                    while (r.cardRewardCount > 0) {
                        const int ri = r.cardRewardCount - 1;
                        const int n2 = r.cardRewards[ri].size();
                        const int pick = std::uniform_int_distribution<int>(0, n2)(ex);
                        search::GameAction(RT::CARD, ri, pick < n2 ? pick : 5).execute(gc);
                    }
                } else {
                    evalCardRewardPolicy(gc);
                }
            }
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    return out.str();
}

static void causalGen(int nSeeds, int sims, int asc, int N, int innerSims, int K, double eps, const std::string &outfile) {
    trainingCampaignStart();
    std::cout << "causalgen  seeds 0.." << nSeeds - 1 << "  outerSims " << sims << "  N " << N
              << "  innerSims " << innerSims << "  K " << K << "  eps " << eps
              << (search::g_fairPlay ? "  [fair-play]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::vector<std::string> per(nSeeds);
    auto t0 = std::chrono::steady_clock::now();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) per[s] = runCausalGenSeed((std::uint64_t)s, sims, asc, N, innerSims, K, eps);

    std::ofstream f(outfile);
    f << causalHeader() << '\n';
    long long rows = 0;
    for (int s = 0; s < nSeeds; ++s) { f << per[s]; rows += std::count(per[s].begin(), per[s].end(), '\n'); }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld causal rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    writeTrainingProvenance(outfile, "causalgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, 0, sims, asc, eps);
}

static void dataGen(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                    long long seedOffset = 0) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;   // append onto an existing file; seeds are disjoint
    std::cout << "datagen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << "  eps " << epsilon << (search::g_fairPlay ? "  [fair-play]" : "")
              << (append ? "  [append]" : "")
              << "  threads " << numThreads() << "  -> " << outfile << "\n";
    // Incremental / interrupt-safe: write the header (fresh file only), then flush
    // each run's rows as it finishes (inside a critical section). Killing the
    // process at any time leaves a valid CSV of all completed runs. seedOffset lets
    // a follow-up run append DISJOINT seeds (no duplicate rows) onto prior output.
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (!append) {
        f << "seed," << kFeatureHeader;
        for (int i = 0; i < kNumCardIds; ++i) f << ",d" << i;
        f << ",won,finalFloor\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0;
    int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runDataGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows;
            f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "datagen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Combat-value dataset: per-fight combat states labeled with the fight outcome.
// Interrupt-safe (per-run flush) and append-capable, same as dataGen.
static void combatGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "combatgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, false);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
                std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), rowCount, outfile.c_str());
    writeTrainingProvenance(outfile, "combatgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Policy-target dataset: per-decision root-edge visit distributions. Same
// interrupt-safe (per-run flush) + append pattern as combatGen.
static void policyGen(int nSeeds, int sims, int asc, double epsilon,
                      const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;   // datagen writes full-width rows
    const bool append = seedOffset > 0;
    std::cout << "policygen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << policyHeaderStr() << "\n"; f.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runPolicyGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld policy rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "policygen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Combined value+policy datagen: ONE play pass writes both CSVs (see runFightGenSeed).
static void fightGen(int nSeeds, int sims, int asc, double epsilon,
                     const std::string &valFile, const std::string &polFile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "fightgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << valFile << " + " << polFile << "\n";
    std::ofstream vf(valFile, append ? std::ios::app : std::ios::out);
    std::ofstream pf(polFile, append ? std::ios::app : std::ios::out);
    if (vf.tellp() == 0) { vf << "seed,fightIdx," << combatHeaderStr() << ",won,endHp\n"; vf.flush(); }
    if (pf.tellp() == 0) { pf << policyHeaderStr() << "\n"; pf.flush(); }

    auto t0 = std::chrono::steady_clock::now();
    long long vRows = 0, pRows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto pr = runFightGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon);
        #pragma omp critical
        {
            vf << pr.first;  pf << pr.second;  vf.flush(); pf.flush();
            vRows += std::count(pr.first.begin(),  pr.first.end(),  '\n');
            pRows += std::count(pr.second.begin(), pr.second.end(), '\n');
            if (++done % 100 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld val + %lld pol rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, vRows, pRows, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld value + %lld policy rows from %d runs in %.1fs\n", vRows, pRows, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), vRows + pRows, valFile.c_str());
    writeTrainingProvenance(valFile, "fightgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), vRows + pRows, seedOffset, sims, asc);
}

// ---------------------------------------------------------------------------
// DISTRIBUTIONAL COMBAT VALUE datagen: like combatgen but adds rich labels for
// the distributional model — endTurn (for turns-remaining prediction) and
// per-potion-ID consumption flags (for potion-use-probability prediction).
// The 1766 state features + won/endHp are identical to combatgen output.
// ---------------------------------------------------------------------------
static void distCombatGen(int nSeeds, int sims, int asc, double epsilon,
                          const std::string &outfile, long long seedOffset = 0) {
    trainingCampaignStart();
    search::g_richCombatFeatures = true;
    const bool append = seedOffset > 0;
    std::cout << "distgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << "seed,fightIdx," << combatHeaderStr() << ",won,endHp"
          << distLabelHeaderStr() << "\n";
        f.flush();
    }

    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::string rows = runCombatGenSeed((std::uint64_t)(seedOffset + s), sims, asc, epsilon, true);
        #pragma omp critical
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 200 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.3fs/run)\n", done, nSeeds, rowCount, el, el/done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld dist combat rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "distgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc, epsilon);
}

// Export one deterministic full-map graph per (seed, ascension, act) present
// in a card-counterfactual CSV.  The source CSV repeats the state once per
// available action; de-duplicating here keeps the companion graph table small.
// Each node stores its room id and a seven-bit mask of outgoing destination x
// coordinates.  Row/column are implicit in the fixed 15x7 layout.
static void exportCardCfMaps(const std::string &inputPath, const std::string &outputPath) {
    std::ifstream in(inputPath);
    if (!in) throw std::runtime_error("cannot open card-CF CSV: " + inputPath);
    std::ofstream out(outputPath);
    if (!out) throw std::runtime_error("cannot create map CSV: " + outputPath);

    std::string line;
    if (!std::getline(in, line)) throw std::runtime_error("empty card-CF CSV: " + inputPath);
    std::stringstream header(line);
    std::vector<std::string> columns;
    std::string headerField;
    while (std::getline(header, headerField, ',')) columns.push_back(headerField);
    auto columnIndex = [&](const char *name) {
        auto it = std::find(columns.begin(), columns.end(), name);
        if (it == columns.end()) throw std::runtime_error("map source CSV missing column " + std::string(name));
        return static_cast<int>(it - columns.begin());
    };
    const int seedCol = columnIndex("seed");
    const int ascCol = columnIndex("ascension");
    const int actCol = columnIndex("act");
    const int lastNeededCol = std::max({seedCol, ascCol, actCol});

    out << "seed,ascension,act,burningEliteX,burningEliteY,burningEliteBuff";
    for (int i = 0; i < 15 * 7; ++i) out << ",room" << i;
    for (int i = 0; i < 15 * 7; ++i) out << ",edges" << i;
    out << '\n';

    std::set<std::tuple<std::uint64_t, int, int>> seen;
    std::size_t rows = 0;
    while (std::getline(in, line)) {
        std::stringstream ss(line);
        std::string field;
        std::uint64_t seed = 0;
        int ascension = 0, act = 0;
        for (int col = 0; col <= lastNeededCol; ++col) {
            if (!std::getline(ss, field, ',')) {
                throw std::runtime_error("short row in map source CSV");
            }
            if (col == seedCol) seed = std::stoull(field);
            else if (col == ascCol) ascension = std::stoi(field);
            else if (col == actCol) act = std::stoi(field);
        }
        if (!seen.emplace(seed, ascension, act).second) continue;

        Map map = act == 4 ? Map::act4Map() : Map::fromSeed(seed, ascension, act, true);
        out << seed << ',' << ascension << ',' << act << ','
            << map.burningEliteX << ',' << map.burningEliteY << ',' << map.burningEliteBuff;
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            out << ',' << static_cast<int>(map.getNode(x, y).room);
        }
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &node = map.getNode(x, y);
            int edgeMask = 0;
            for (int i = 0; i < node.edgeCount; ++i) edgeMask |= 1 << node.edges[i];
            out << ',' << edgeMask;
        }
        out << '\n';
        ++rows;
    }
    std::cout << "exported " << rows << " unique (seed, ascension, act) maps to "
              << outputPath << '\n';
}

// ---------------------------------------------------------------------------
int main(int argc, char **argv) {
    g_mainBinaryPath = argc > 0 ? argv[0] : "one_combat";
    g_mainArgv.clear();
    for (int i = 1; i < argc; ++i) g_mainArgv.emplace_back(argv[i]);
    std::string mode = argc > 1 ? argv[1] : "";

    if (const char *d = std::getenv("VPORT")) g_vPort = std::atoi(d);

    if (const char *d = std::getenv("STS_COLLECT_KEYS")) {
        g_collectKeys = std::atoi(d) != 0;
        std::cout << "[collect keys " << (g_collectKeys ? "ON" : "OFF") << "]\n";
    }

    if (const char *d = std::getenv("STS_ROLLOUT_DEPTH")) {   // cap combat rollout length
        search::g_maxRolloutDepth = std::atoi(d);
        std::cout << "[rollout depth cap = " << search::g_maxRolloutDepth << "]\n";
    }
    if (const char *d = std::getenv("STS_ROLLOUT_CAPS")) {    // context-adaptive rollout caps (Phase 2)        search::g_rolloutCaps = std::atoi(d) != 0;
        if (search::g_rolloutCaps) {
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_BOSS"))      search::g_rolloutCapBoss = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_TURN0"))     search::g_rolloutCapTurn0 = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_ACT23"))     search::g_rolloutCapAct23 = std::atoi(v);
            if (const char *v = std::getenv("STS_ROLLOUT_CAPS_LATE_ALIVE")) search::g_rolloutCapLateAlive = std::atoi(v);
            std::cout << "[context rollout caps ON: boss=" << search::g_rolloutCapBoss
                      << " turn0=" << search::g_rolloutCapTurn0
                      << " act23=" << search::g_rolloutCapAct23
                      << " lateAlive<=" << search::g_rolloutCapLateAlive << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_FORCED_MOVE")) {    // forced-action contraction (Phase 5; default ON, 0 disables)
        search::g_forcedMoveSkip = std::atoi(d) != 0;
        std::cout << "[forced-move contraction " << (search::g_forcedMoveSkip ? "ON" : "OFF") << "]\n";
    }
    if (const char *d = std::getenv("STS_LIVE_VALID")) {     // fair-tree structural fix (Phase 4)
        search::g_liveValid = std::atoi(d) != 0;
        if (search::g_liveValid) std::cout << "[live-valid edge re-selection ON]\n";
    }
    if (const char *d = std::getenv("STS_TURN_PENALTY")) {    // -turn*k on capped leaf: loop-breaker
        search::g_leafTurnPenalty = std::atof(d);
        std::cout << "[leaf turn penalty = " << search::g_leafTurnPenalty << "]\n";
    }
    if (const char *d = std::getenv("STS_TT")) {              // transposition table (value sharing)
        search::g_useTT = std::atoi(d) != 0;
        if (search::g_useTT) std::cout << "[transposition table ON]\n";
    }
    one_combat::configureRestVPolicyFromEnvironment();
    if (const char *d = std::getenv("STS_REST_WIN")) {        // win-rate rest policy (heal vs upgrade by P(win))
        g_restWin = std::atoi(d) != 0;
        if (g_restWin) std::cout << "[win-rate rest policy ON]\n";
    }
    if (const char *d = std::getenv("STS_CARD_WIN")) {       // A/B: card picks by P(win) instead of V_floor
        g_cardWin = std::atoi(d) != 0;
        if (const char *s = std::getenv("STS_CARD_WIN_SKIP")) g_cardWinSkip = std::atof(s);
        if (g_cardWin) std::cout << "[card picks via WIN model, skip<" << g_cardWinSkip << "]\n";
    }
    if (const char *d = std::getenv("STS_CARD_NN")) {        // A/B: card picks via deck-set NN (CN op)
        g_cardNN = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_CARD_NN_W"))    g_cardNNW    = std::atof(w);
        if (const char *s = std::getenv("STS_CARD_NN_SKIP")) g_cardNNSkip = std::atof(s);
        if (g_cardNN) std::cout << "[card picks via deck-set NN: w=" << g_cardNNW
                                << " (1=pure NN, <1 blend w/ v_win), skip<" << g_cardNNSkip
                                << " (needs v_deckset.pt in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_CARD_ACTION")) {    // direct paired card/skip action NN
        g_cardAction = std::atoi(d) != 0;
        if (g_cardAction) std::cout << "[card picks via paired action NN (CA op)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_ACTION_NN")) {
        g_oocActionNN = std::atoi(d) != 0;
        if (g_oocActionNN)
            std::cout << "[OOC decisions via next-combat action NN (OA op), reapplied every decision]\n";
    }
    if (const char *d = std::getenv("STS_OOC_CHECKPOINT_NN")) {
        if (g_oocCheckpointNet.load(d)) {
            g_oocActionNN = true;
            std::cout << "[OOC decisions via native checkpoint-distilled NN]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_NN")) {
        if (g_oocStrategicNet.load(d)) {
            g_effectiveOocStrategicPath = d;
            std::cout << "[OOC one-ply strategic NN ON: card rewards gated at margin "
                      << g_oocStrategicMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TOK_NN")) {
        if (g_oocStrategicTokNet.load(d)) {
            g_effectiveOocStrategicTokPath = d;
            g_oocStrategicTok = 1;
            std::cout << "[OOC one-ply strategic TOK net ON: card rewards gated at margin "
                      << g_oocStrategicMargin << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TOK_CHECK")) {
        g_oocStrategicTokCheck = std::atoi(d) != 0;
        if (g_oocStrategicTokCheck)
            std::cout << "[OOC strategic tok parity check ON (first-decision globs vs richRow)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TRACE")) {
        g_oocStrategicTracePath = d;
        if (!g_oocStrategicTracePath.empty())
            std::cout << "[OOC strategic decision trace: " << g_oocStrategicTracePath << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_Q")) {
        g_oocStrategicQ = std::atoi(d) != 0;
        if (!g_oocStrategicQ)
            std::cout << "[OOC one-ply: Q head disabled, V2 successor-value scoring]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_REST")) {
        g_oocStrategicRest = std::atoi(d) != 0;
        if (g_oocStrategicRest)
            std::cout << "[OOC one-ply: campfire Q gate ON (rest options + upgrade targets)]\n";
    }
    if (const char *d = std::getenv("STS_DATAGEN_GATES")) {  // §127: combatgen/distgen OOC through the one-ply gate chain
        g_datagenGates = std::atoi(d) != 0;
        if (g_datagenGates)
            std::cout << "[datagen OOC gate stack ON: combat labels from the deployed one-ply distribution (§127)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_EVENT")) {
        g_oocStrategicEvent = std::atoi(d) != 0;
        if (g_oocStrategicEvent)
            std::cout << "[OOC one-ply: event Q gate ON (incl. Neow)]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_SHOP")) {
        g_oocStrategicShop = std::atoi(d) != 0;
        if (g_oocStrategicShop)
            std::cout << "[OOC one-ply: shop Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TREASURE")) {
        g_oocStrategicTreasure = std::atoi(d) != 0;
        if (g_oocStrategicTreasure)
            std::cout << "[OOC one-ply: treasure Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_BOSS_RELIC")) {
        g_oocStrategicBossRelic = std::atoi(d) != 0;
        if (g_oocStrategicBossRelic)
            std::cout << "[OOC one-ply: boss relic Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MAP")) {  // M1 map route Q gate
        g_oocStrategicMap = std::atoi(d) != 0;
        if (g_oocStrategicMap)
            std::cout << "[OOC one-ply: map route Q gate ON]\n";
    }
    if (const char *d = std::getenv("STS_OOC_MAP_ROUTE")) {      // M2 C_psi route search
        g_oocMapRoute = std::atoi(d) != 0;
        if (const char *h = std::getenv("STS_OOC_MAP_ROUTE_HORIZON"))
            g_oocMapRouteHorizon = std::atoi(h);
        if (g_oocMapRoute)
            std::cout << "[OOC map route search ON: horizon " << g_oocMapRouteHorizon
                      << " (needs STS_CPSI_NN + strategic net)]\n";
    }
    if (const char *d = std::getenv("STS_CPSI_NN")) {            // C_psi combat outcome surrogate
        const std::string path = std::string(d) == "1" ? "build/v_combat_cpsi.txt" : d;
        if (g_cpsiNet.load(path))
            std::cout << "[C_psi combat surrogate loaded: " << g_cpsiNet.description() << "]\n";
        else
            std::cerr << "[C_psi load failed: " << path << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_SHOP_BEAM")) {     // B1 multi-step shop beam (§2)
        g_oocShopBeam = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_WIDTH"))
            g_oocShopBeamWidth = std::atoi(w);
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_DEPTH"))
            g_oocShopBeamDepth = std::atoi(w);
        if (const char *w = std::getenv("STS_OOC_SHOP_BEAM_BUDGET"))
            g_oocShopBeamBudget = std::atoi(w);
        if (g_oocShopBeam)
            std::cout << "[OOC shop beam ON: width " << g_oocShopBeamWidth
                      << " depth " << (g_oocShopBeamDepth > 0 ? std::to_string(g_oocShopBeamDepth) : "until-leave")
                      << " budget " << g_oocShopBeamBudget << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN")) {
        g_oocStrategicMargin = std::atof(d);
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_SCORE")) {
        g_oocStrategicScorePolicy = (strcmp(d, "policy") == 0);
        std::cout << "[OOC strategic score source: "
                  << (g_oocStrategicScorePolicy ? "policy (sigmoid)" : "q") << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_CARD"))
        g_oocStrategicMarginCard = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_REST"))
        g_oocStrategicMarginRest = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_EVENT"))
        g_oocStrategicMarginEvent = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_SHOP"))
        g_oocStrategicMarginShop = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_TREASURE"))
        g_oocStrategicMarginTreasure = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC"))
        g_oocStrategicMarginBossRelic = std::atof(d);
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_MARGIN_MAP"))
        g_oocStrategicMarginMap = std::atof(d);
    if (g_oocStrategicMarginCard >= 0.0 || g_oocStrategicMarginRest >= 0.0
        || g_oocStrategicMarginEvent >= 0.0 || g_oocStrategicMarginShop >= 0.0
        || g_oocStrategicMarginTreasure >= 0.0 || g_oocStrategicMarginBossRelic >= 0.0
        || g_oocStrategicMarginMap >= 0.0) {
        std::cout << "[OOC per-screen margins: card=" << g_oocStrategicMarginCard
                  << " rest=" << g_oocStrategicMarginRest
                  << " event=" << g_oocStrategicMarginEvent
                  << " shop=" << g_oocStrategicMarginShop
                  << " treasure=" << g_oocStrategicMarginTreasure
                  << " boss_relic=" << g_oocStrategicMarginBossRelic
                  << " map=" << g_oocStrategicMarginMap << "]\n";
    }
    if (const char *e = std::getenv("STS_OOC_STRATEGIC_GATE_EPS")) {
        const double v = std::atof(e);
        if (v > 0.0) g_oocStrategicGateEps = v;
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_GATE")) {
        // Wave B regret gate (ooc-qwin-continuation.md Step 5):
        // STS_OOC_STRATEGIC_GATE=regret replaces the margin rule with
        // Qmax(s) − Q(a_heur) > ε for every one-ply gate and the M2 route
        // search; the margin rule stays as the RNG-tied fallback.
        if (std::string(d) == "regret") {
            g_oocStrategicGateRegret = true;
            std::cout << "[OOC regret gate ON: eps " << g_oocStrategicGateEps << "]\n";
        }
    }
    if (const char *v = std::getenv("STRATEGIC_SAMPLES_PER_RUN"))
        g_strategicSamplesPerRun = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STRATEGIC_SAMPLE_ALL"))
        g_strategicSampleAll = std::atoi(v) != 0;
    if (const char *v = std::getenv("STRATEGIC_BRANCH_FIGHTS"))
        g_strategicBranchFights = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STRATEGIC_BRANCH_SIMS")) {
        std::istringstream in(v);
        std::vector<int> parsed;
        std::string token;
        while (std::getline(in, token, ',')) {
            const int p = std::atoi(token.c_str());
            if (p > 0) parsed.push_back(p);
        }
        if (!parsed.empty()) g_strategicBranchSims = parsed;
    }
    if (const char *v = std::getenv("STRATEGIC_BRANCH_FUTURES"))
        g_strategicBranchFutures = std::max(1, std::atoi(v));
    if (const char *d = std::getenv("STS_BOSS_RELIC")) {    // boss relic pick via V_win (needs v_win in v_server)
        g_bossRelicV = std::atoi(d) != 0;
        if (g_bossRelicV) std::cout << "[boss-relic pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_NEOW_V")) {        // Neow bonus pick via V_win
        g_neowV = std::atoi(d) != 0;
        if (g_neowV) std::cout << "[Neow bonus pick via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_WIN_NET")) {       // native V_win tree-walk (no v_server socket)
        const std::string path = std::string(d) == "1" ? "models/v_win_trees.txt" : d;
        if (!g_winNet.load(path, richIdxMap()))
            std::cerr << "[STS_WIN_NET] failed to load win tree: " << path << "\n";
    }
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_MODEL")) {
        if (!one_combat::loadE2cRawModel(d))
            std::cerr << "[STS_RUNWIN_SHADOW_MODEL] failed to load E2c RAW critic: " << d << "\n";
    }
    {
        // The baseline is serverless by default. Set STS_NATIVE_OOC=0 only
        // for an explicit legacy-server comparison.
        const char *d = std::getenv("STS_NATIVE_OOC");
        g_nativeOoc = !d || std::atoi(d) != 0;
        if (g_nativeOoc) {
            if (!g_winNet.ok) g_winNet.load("models/v_win_trees.txt", richIdxMap());
            g_floorNet.load("models/v_rich_trees.txt", richIdxMap());
            if (!g_floorNet.ok) {
                std::cerr << "[native OOC] failed to load models/v_rich_trees.txt\n";
                return 1;
            }
            if (!g_winNet.ok) {
                std::cout << "[native V_win NOT loaded; win-rest helpers will use v_server fallback]\n";
            } else {
                std::cout << "[native OOC floor/win GBMs ON; no v_server required]\n";
            }
        }
    }
    if (const char *d = std::getenv("STS_PATH_V")) {        // model-driven pathing (uses forward-map feats)
        g_pathV = std::atoi(d) != 0;
        if (g_pathV) std::cout << "[model-driven pathing via V_win ON]\n";
    }
    if (one_combat::configurePathActionPolicyFromEnvironment()) g_pathV = 1;
    if (const char *d = std::getenv("STS_EVENT_V")) {       // model-driven event choices
        g_eventV = std::atoi(d) != 0;
        if (g_eventV) std::cout << "[model-driven events via V_win ON]\n";
    }
    if (const char *d = std::getenv("STS_POTION_SAVE")) {   // dynamic potion-saving (keep for elites/bosses)
        g_potionSave = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_POTION_WINDOW"))  g_potionWindow  = std::atoi(v);
        if (const char *v = std::getenv("STS_POTION_BONUS"))   g_potionBonus   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_SPEND"))   g_potionSpend   = std::atof(v);
        if (const char *v = std::getenv("STS_POTION_DESIRED")) g_potionDesired = std::atof(v);
        if (g_potionSave)
            std::cout << "[potion-saving ON: window=" << g_potionWindow << " bonus=" << g_potionBonus
                      << " spend=" << g_potionSpend << " desired=" << g_potionDesired << "]\n";
    }
    if (const char *d = std::getenv("STS_SHOP_WIN")) {       // A/B: shop bundles scored by P(win)
        g_shopWin = std::atoi(d) != 0;
        if (g_shopWin) std::cout << "[shop scored via WIN model]\n";
    }
    if (const char *d = std::getenv("STS_SIMS_NORMAL")) g_simsNormal = std::atoi(d);  // per-fight sim budgets
    if (const char *d = std::getenv("STS_SIMS_ELITE"))  g_simsElite  = std::atoi(d);
    if (const char *d = std::getenv("STS_SIMS_BOSS"))   g_simsBoss   = std::atoi(d);
    if (g_simsNormal > 0 || g_simsElite > 0 || g_simsBoss > 0)
        std::cout << "[tiered sims: normal=" << g_simsNormal << " elite=" << g_simsElite
                  << " boss=" << g_simsBoss << " (-1=base)]\n";
    if (const char *d = std::getenv("STS_SIM_ADAPT")) {       // C_psi adaptive per-fight sim budget
        g_simAdapt = std::atoi(d) != 0;
        if (const char *f = std::getenv("STS_SIM_ADAPT_MIN_FRAC")) g_simAdaptMinFrac = std::atof(f);
        if (const char *f = std::getenv("STS_SIM_ADAPT_MAX_FRAC")) g_simAdaptMaxFrac = std::atof(f);
        if (g_simAdapt)
            std::cout << "[C_psi adaptive sim budget ON: frac " << g_simAdaptMinFrac
                      << ".." << g_simAdaptMaxFrac << " (needs STS_CPSI_NN)]\n";
    }
    if (const char *d = std::getenv("STS_CONVERGE")) {       // convergence-based early stopping
        search::g_convergeStop = std::atoi(d) != 0;
        if (const char *p = std::getenv("STS_CONV_PATIENCE")) search::g_convPatience = std::atoll(p);
        if (const char *m = std::getenv("STS_CONV_MIN"))      search::g_convMinSims  = std::atoll(m);
        if (search::g_convergeStop)
            std::cout << "[convergence stop ON: patience=" << search::g_convPatience
                      << " minSims=" << search::g_convMinSims << "]\n";
    }
    if (const char *d = std::getenv("STS_CONV_ROOT")) {      // root-stability early stopping
        search::g_convRootStop = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_CONV_ROOT_START"))   search::g_convRootStart = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_GROW"))    search::g_convRootGrow  = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_CHECK"))   search::g_convRootCheck = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_SHARE"))   search::g_convRootShare = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_VALUE"))   search::g_convRootValue = std::atof(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_MIN"))     search::g_convRootMinSims = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_PATIENCE")) search::g_convRootPatience = std::atoll(v);
        if (const char *v = std::getenv("STS_CONV_ROOT_MAX_FRAC")) search::g_convRootMaxFrac = std::atof(v);
        if (search::g_convRootStop)
            std::cout << "[root-stability stop ON: start=" << search::g_convRootStart
                      << " grow=" << search::g_convRootGrow
                      << " check=" << search::g_convRootCheck
                      << " share=" << search::g_convRootShare
                      << " value=" << search::g_convRootValue
                      << " minSims=" << search::g_convRootMinSims
                      << " patience=" << search::g_convRootPatience
                      << " maxFrac=" << search::g_convRootMaxFrac << "]\n";
        if (search::g_convRootStop && (search::g_convRootStart <= 0 || search::g_convRootGrow <= 1.0))
            std::cout << "[root-stability warning: STS_CONV_ROOT_START must be >0 and STS_CONV_ROOT_GROW >1.0;"
                      << " searchToTotalRootStable forces the full budget instead of growing by chunks]\n";
    }
    if (const char *d = std::getenv("STS_BOSS_DRAFT")) {      // boss-gated rollout drafting
        g_bossDraft = std::atoi(d) != 0;
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS"))    g_bossDraftRows    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_N"))       g_bossDraftN       = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_SIMS"))    g_bossDraftSims    = std::atoi(v);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_FUTURES")) g_bossDraftFutures = std::atoi(v);
        if (g_bossDraft)
            std::cout << "[boss-gated rollout draft ON: rows<=" << g_bossDraftRows
                      << " N=" << g_bossDraftN << " sims=" << g_bossDraftSims
                      << " futures=" << g_bossDraftFutures << "]\n";
    }
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_DRAFT")) {
        g_actFightProbeDraft = std::atoi(d) != 0;
        if (g_actFightProbeDraft)
            std::cout << "[all-act encounter rollout draft ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " floor-decay=" << g_actFightProbeFloorDecay
                      << "; immediate cards scored only by simulated fight utility]\n";
    }
    // Shared by both the card-only and every-OOC variants; parse independently
    // of the legacy card-only enable flag.
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_SIMS"))
        g_actFightProbeSims = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FUTURES"))
        g_actFightProbeFutures = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS")) {
        std::istringstream in(v);
        std::string token;
        while (std::getline(in, token, ',')) {
            const int parsed = std::atoi(token.c_str());
            if (parsed > 0) g_actFightProbeCheckpointSims.push_back(parsed);
        }
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_FLOOR_DECAY"))
        g_actFightProbeFloorDecay = std::max(0.0, std::min(1.0, std::atof(v)));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS"))
        g_actFightProbeMaxCheckpoints = std::max(1, std::atoi(v));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_TRACE"))
        g_actFightProbeTrace = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PARALLEL"))
        g_actFightProbeParallelBranches = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT"))
        g_actFightProbePredict = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_ENCOUNTER_NN"))
        g_actFightProbeEncounterNN = std::atoi(v) != 0;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_NET"))
        g_actFightProbePredictNetPath = v;
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_PREDICT_WIN_THRESHOLD"))
        g_actFightProbePredictWinThreshold = std::max(0.0, std::min(1.0, std::atof(v)));
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_TERM_WIN")) {
        g_actFightProbeTermWin = std::max(0.0, std::atof(v));
        if (g_actFightProbeTermWin > 0.0)
            std::cout << "[all-acts checkpoint terminal win-GBM ON: weight="
                      << g_actFightProbeTermWin
                      << " (searched checkpoints; requires the native win model)]\n";
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_MARGIN")) {
        g_actFightProbeMargin = std::max(0.0, std::atof(v));
        if (g_actFightProbeMargin > 0.0)
            std::cout << "[all-acts checkpoint oracle margin gate ON: best-second >= "
                      << g_actFightProbeMargin << " required, else fallback stack]\n";
    }
    if (g_actFightProbePredict) {
        if (!g_actFightProbePredictNet.load(g_actFightProbePredictNetPath)
            || !g_actFightProbePredictNet.hasOutcomeHeads()) {
            std::cerr << "[all-acts checkpoint predictor load FAILED (needs combat_entity_v1): "
                      << g_actFightProbePredictNetPath << "]\n";
            return 2;
        }
        std::cout << "[all-acts checkpoint predictor ON: " << g_actFightProbePredictNetPath
                  << ", win threshold=" << g_actFightProbePredictWinThreshold << "]\n";
    }
    if (const char *v = std::getenv("STS_ACT_FIGHT_PROBE_LOG"))
        g_actFightProbeLogPath = v;
    if (const char *d = std::getenv("STS_ACT_FIGHT_PROBE_ALL_OOC")) {
        g_actFightProbeAllOoc = std::atoi(d) != 0;
        if (g_actFightProbeAllOoc)
            std::cout << "[Acts 1-3 all-OOC checkpoint rollout ON: sims=" << g_actFightProbeSims
                      << " futures=" << g_actFightProbeFutures
                      << " max-checkpoints=" << g_actFightProbeMaxCheckpoints
                      << (g_actFightProbeCheckpointSims.empty()
                          ? "" : " checkpoint-sims=" + actFightProbeCheckpointSimsCsv())
                      << (g_actFightProbeEncounterNN ? " predictor=ooc-encounter-NN(first-checkpoint)" : "")
                      << (g_actFightProbePredict ? " predictor=entity-transition" : "")
                      << "; every legal OOC action scored by fight-strength profile]\n";
    }
    if (g_actFightProbeParallelBranches) {
        if (g_potionSave)
            std::cout << "[all-acts branch parallelism disabled: dynamic potion saving writes shared combat state]\n";
        else if (g_actFightProbeTrace)
            std::cout << "[all-acts branch parallelism disabled: trace output must remain ordered]\n";
        else
            std::cout << "[all-acts branch parallelism ON: up to " << numThreads()
                      << " action-future branches at once]\n";
    }
    if (!g_actFightProbeLogPath.empty() && g_actFightProbeAllOoc && !initActFightProbeLog())
        return 2;
    if (const char *d = std::getenv("STS_STOP_AFTER_ACT")) {
        g_stopAfterAct = std::max(0, std::atoi(d));
        if (g_stopAfterAct > 0)
            std::cout << "[benchmark stops after Act " << g_stopAfterAct << " boss]\n";
    }
    one_combat::configureFightReplayFromEnvironment();
    if (const char *d = std::getenv("STS_BOSS_V")) {          // boss-survival V blended into near-boss picks
        g_bossV = std::atoi(d) != 0;
        if (const char *w = std::getenv("STS_BOSS_V_W"))       g_bossVW        = std::atof(w);
        if (const char *v = std::getenv("STS_BOSS_DRAFT_ROWS")) g_bossDraftRows = std::atoi(v);
        if (g_bossV)
            std::cout << "[boss-V blend draft ON: w=" << g_bossVW
                      << " rows<=" << g_bossDraftRows << " (needs v_boss in v_server)]\n";
    }
    if (const char *d = std::getenv("STS_SKIP_THR")) {        // card-reward skip threshold (marginal V)
        g_cardSkipThresh = std::atof(d);
        std::cout << "[card skip threshold = " << g_cardSkipThresh << "]\n";
    }
    one_combat::configureVPathPolicyFromEnvironment();
    if (const char *d = std::getenv("STS_DG_TEMP")) {         // datagen softmax temperature (card marginals)
        g_dgTemp = std::atof(d);
        std::cout << "[datagen softmax temp = " << g_dgTemp << "]\n";
    }
    if (const char *d = std::getenv("STS_FAIR")) {            // determinized/ISMCTS combat (no future peeking)
        search::g_fairPlay = std::atoi(d) != 0;
        if (search::g_fairPlay) std::cout << "[fair-play / determinized MCTS ON]\n";
    }
    if (const char *d = std::getenv("STS_SEARCHER3")) {      // use enhanced BattleScumSearcher3 engine
        search::g_useSearcher3 = std::atoi(d) != 0;
        if (search::g_useSearcher3) std::cout << "[Searcher3 engine ON: belief/prune/chain/live (CRN opt-in)]\n";
    }
    const char *silverSearchEnv = std::getenv("STS_SILVER_SEARCH");
    const bool silverSearchRequested = silverSearchEnv && std::atoi(silverSearchEnv) != 0;
    if (const char *qualityFile = std::getenv("STS_SILVER_STICKY_QUALITY_FILE")) {
        if (*qualityFile != '\0' && !silverSearchRequested) {
            throw std::invalid_argument(
                "STS_SILVER_STICKY_QUALITY_FILE requires STS_SILVER_SEARCH=1");
        }
    }
    if (silverSearchRequested) {
            // The external callback takes precedence before ScumSearchAgent2
            // enters either Searcher2 or Searcher3. It owns local Silver
            // randomness and therefore never constructs an S3 Belief.
            search::installSilverLiveBackend();
            std::cout << "[isolated Silver combat backend ON: local Silver RNG/chance search; Searcher3 particles bypassed; reuse-cap="
                      << search::silverLiveReuseCapMode() << " cap=" << search::silverLiveReuseCap()
                      << "]\n";
    }
    // STS_LIVE_VALID (Phase 4, fair-tree structural fix): env opt-in as
    // recorded in §122, or default ON for the Searcher3 fair-play regime
    // since 2026-08-07 (§123: two independent 256-seed paired gates give
    // +5.5pp and +5.9pp win at +7.9% and +14.6% cpu — the recorded cpu-trade
    // call accepts that cost for the win; hp +4.1/+3.1, floor +0.6/+1.1).
    // STS_LIVE_VALID=0 explicitly disables. The fairgen datagen mode is NOT
    // covered (it forces the regime after this parse); datagen keeps the
    // recorded §117 behavior unless the flag is set explicitly.
    if (!std::getenv("STS_LIVE_VALID") && search::g_fairPlay && search::g_useSearcher3) {
        search::g_liveValid = true;
        std::cout << "[live-valid edge re-selection ON (fair S3 default, §123)]\n";
    }
    // ── Tree reuse control (STS_REUSE_*) ──────────────────────────────────
    if (const char *d = std::getenv("STS_REUSE_MAX_SEARCHES")) {
        search::g_reuseMaxSearches = std::atoi(d);
        std::cout << "[reuse max-searches = " << search::g_reuseMaxSearches << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_STATS_MODE")) {
        if (std::string(d) == "recursive_reset")
            search::g_reuseStatsMode = 1;
        else
            search::g_reuseStatsMode = 0;  // "keep" or unknown
        std::cout << "[reuse stats-mode = " << (search::g_reuseStatsMode ? "recursive_reset" : "keep") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_ALWAYS_Q")) {
        search::g_reuseAlwaysQ = std::atoi(d) != 0;
        std::cout << "[reuse always-Q = " << (search::g_reuseAlwaysQ ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ALWAYS_Q")) {
        search::g_s3AlwaysQ = std::atoi(d) != 0;
        std::cout << "[S3 always-Q = " << (search::g_s3AlwaysQ ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_DIAG")) {
        search::g_reuseDiag = std::atoi(d) != 0;
        std::cout << "[reuse diagnostics = " << (search::g_reuseDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_OBS_STABLE")) {
        search::g_reuseObsStable = std::atoi(d) != 0;
        std::cout << "[reuse obs-stable = " << (search::g_reuseObsStable ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_RECONCILE_ROOT")) {
        search::g_reuseReconcileRoot = std::atoi(d) != 0;
        std::cout << "[reuse reconcile-root = " << (search::g_reuseReconcileRoot ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CARRY_DIAG")) {
        search::g_reuseCarryDiag = std::atoi(d) != 0;
        std::cout << "[reuse carry-diag = " << (search::g_reuseCarryDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_SEMANTIC_CARD_EDGES")) {
        search::g_s3SemanticCardEdges = std::atoi(d) != 0;
        std::cout << "[S3 semantic-card-edges = " << (search::g_s3SemanticCardEdges ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG")) {
        search::g_s3OutcomeBucketDiag = std::atoi(d) != 0;
        std::cout << "[S3 outcome-bucket-diag = " << (search::g_s3OutcomeBucketDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG_FILE")) {
        search::g_s3OutcomeBucketDiagFile = d;
        std::cout << "[S3 outcome-bucket-diag file = " << search::g_s3OutcomeBucketDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_OUTCOME_BUCKET_DIAG_PARTICLES")) {
        search::g_s3OutcomeBucketDiagParticles = std::atoi(d);
        std::cout << "[S3 outcome-bucket-diag particles = " << search::g_s3OutcomeBucketDiagParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG")) {
        search::g_s3StrategyFusionDiag = std::atoi(d) != 0;
        std::cout << "[S3 strategy-fusion diag = "
                  << (search::g_s3StrategyFusionDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_FILE")) {
        search::g_s3StrategyFusionDiagFile = d;
        std::cout << "[S3 strategy-fusion diag file = "
                  << search::g_s3StrategyFusionDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_PARTICLES")) {
        search::g_s3StrategyFusionDiagParticles = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag particles = "
                  << search::g_s3StrategyFusionDiagParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_MAX_TRANSITIONS")) {
        search::g_s3StrategyFusionDiagMaxTransitions = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag max transitions = "
                  << search::g_s3StrategyFusionDiagMaxTransitions << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_MIN_CHILD_VISITS")) {
        search::g_s3StrategyFusionDiagMinChildVisits = std::max(1, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag min child visits = "
                  << search::g_s3StrategyFusionDiagMinChildVisits << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_FRESH_SIMS")) {
        search::g_s3StrategyFusionDiagFreshSims = std::max(0, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag fresh sims = "
                  << search::g_s3StrategyFusionDiagFreshSims << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_STRATEGY_FUSION_DIAG_REF_SIMS")) {
        search::g_s3StrategyFusionDiagReferenceSims = std::max(0, std::atoi(d));
        std::cout << "[S3 strategy-fusion diag reference sims = "
                  << search::g_s3StrategyFusionDiagReferenceSims << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSISTENT_ENDTURN_CHANCE")) {
        search::g_s3PersistentEndTurnChance = std::atoi(d) != 0;
        std::cout << "[S3 persistent END_TURN chance = "
                  << (search::g_s3PersistentEndTurnChance ? "ON" : "off")
                  << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSISTENT_ENDTURN_MAX_PILE")) {
        search::g_s3PersistentEndTurnMaxPile = std::max(0, std::atoi(d));
        std::cout << "[S3 persistent END_TURN max-pile = "
                  << search::g_s3PersistentEndTurnMaxPile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG")) {
        search::g_s3BucketValueDiag = std::atoi(d) != 0;
        std::cout << "[S3 bucket-value-diag = " << (search::g_s3BucketValueDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG_FILE")) {
        search::g_s3BucketValueDiagFile = d;
        std::cout << "[S3 bucket-value-diag file = " << search::g_s3BucketValueDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BUCKET_VALUE_DIAG_ROLLOUTS")) {
        search::g_s3BucketValueDiagRollouts = std::atoi(d);
        std::cout << "[S3 bucket-value-diag rollouts = " << search::g_s3BucketValueDiagRollouts << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE")) {
        search::g_s3EndTurnMarginalize = std::atoi(d) != 0;
        std::cout << "[S3 END_TURN marginalization = " << (search::g_s3EndTurnMarginalize ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE_PARTICLES")) {
        search::g_s3EndTurnMarginalizeParticles = std::atoi(d);
        std::cout << "[S3 END_TURN marg particles = " << search::g_s3EndTurnMarginalizeParticles << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ENDTURN_MARGINALIZE_MAX_PILE")) {
        search::g_s3EndTurnMarginalizeMaxPile = std::atoi(d);
        std::cout << "[S3 END_TURN marg max-pile = " << search::g_s3EndTurnMarginalizeMaxPile << "]\n";
    }
    if (!search::s3PersistentChanceFlagsCompatible(
            search::g_s3PersistentEndTurnChance,
            search::g_s3StrategyFusionDiag,
            search::g_s3EndTurnMarginalize)) {
        if (search::g_s3StrategyFusionDiag) {
            std::cerr << "error: STS_S3_PERSISTENT_ENDTURN_CHANCE and "
                         "STS_S3_STRATEGY_FUSION_DIAG are mutually exclusive; "
                         "the diagnostic assumes the legacy shared-child topology\n";
        } else {
            std::cerr << "error: STS_S3_PERSISTENT_ENDTURN_CHANCE and "
                         "STS_S3_ENDTURN_MARGINALIZE are mutually exclusive; "
                         "persistent chance nodes must not run with eager marginalization\n";
        }
        return 2;
    }
    if (search::g_s3PersistentEndTurnChance)
        std::atexit(search::printPersistentEndTurnChanceDiagnostics);
    if (const char *d = std::getenv("STS_S3_DRAW_PROB_DIAG")) {
        search::g_s3DrawProbDiag = std::atoi(d) != 0;
        std::cout << "[S3 draw-prob diag = " << (search::g_s3DrawProbDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_DRAW_PROB_DIAG_FILE")) {
        search::g_s3DrawProbDiagFile = d;
        std::cout << "[S3 draw-prob diag file = " << search::g_s3DrawProbDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LEAFVALUE_DIAG")) {
        search::g_s3LeafValueDiag = std::atoi(d) != 0;
        std::cout << "[S3 leafvalue diag = " << (search::g_s3LeafValueDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LEAFVALUE_DIAG_FILE")) {
        search::g_s3LeafValueDiagFile = d;
        std::cout << "[S3 leafvalue diag file = " << search::g_s3LeafValueDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BELIEF_AUDIT")) {
        search::g_s3BeliefAudit = std::atoi(d) != 0;
        std::cout << "[S3 belief audit = " << (search::g_s3BeliefAudit ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REAL_BELIEF_FILTER")) {
        search::g_s3RealBeliefFilter = std::atoi(d) != 0;
        std::cout << "[S3 real-belief-filter = " << (search::g_s3RealBeliefFilter ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REAL_BELIEF_COLLAPSE_FRESH")) {
        search::g_s3RealBeliefCollapseFresh = std::atoi(d) != 0;
        std::cout << "[S3 real-belief-collapse-fresh = " << (search::g_s3RealBeliefCollapseFresh ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PERSIST_FILTERED_BELIEF")) {
        search::g_s3PersistFilteredBelief = std::atoi(d) != 0;
        std::cout << "[S3 persist-filtered-belief = " << (search::g_s3PersistFilteredBelief ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_INTERNAL_BELIEF_UPDATE")) {
        search::g_s3InternalBeliefUpdate = std::atoi(d) != 0;
        std::cout << "[S3 internal-belief-update = " << (search::g_s3InternalBeliefUpdate ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_SHADOW")) {
        search::g_s3RejuvShadow = std::atoi(d) != 0;
        std::cout << "[S3 rejuv-shadow = " << (search::g_s3RejuvShadow ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_TRIGGER")) {
        search::g_s3RejuvTrigger = std::max(0, std::atoi(d));
        std::cout << "[S3 rejuv trigger = " << search::g_s3RejuvTrigger << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_PROPOSALS")) {
        search::g_s3RejuvProposals = std::max(1, std::atoi(d));
        std::cout << "[S3 rejuv proposals = " << search::g_s3RejuvProposals << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_REJUV_SHADOW_FILE")) {
        search::g_s3RejuvShadowFile = d;
        std::cout << "[S3 rejuv shadow file = " << search::g_s3RejuvShadowFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_REJUV_LIVE")) {
        const std::string mode = d;
        if (mode == "off") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::OFF;
        else if (mode == "placebo") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::PLACEBO;
        else if (mode == "ai") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::AI_RNG;
        else if (mode == "placebo1") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::PLACEBO1;
        else if (mode == "ai1") search::g_s3LiveRejuvenationMode = search::S3LiveRejuvenationMode::AI_RNG1;
        else {
            std::cerr << "Invalid STS_S3_AI_REJUV_LIVE='" << mode
                      << "'; expected off, placebo, ai, placebo1, or ai1\n";
            return 2;
        }
        std::cout << "[S3 AI rejuvenation live = " << mode << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_REJUV_LIVE_FILE")) {
        search::g_s3LiveRejuvenationFile = d;
        std::cout << "[S3 AI rejuvenation live file = " << search::g_s3LiveRejuvenationFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_SHADOW")) {
        search::g_s3AiSensitivityShadow = std::atoi(d) != 0;
        std::cout << "[S3 AI sensitivity shadow = "
                  << (search::g_s3AiSensitivityShadow ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_FILE")) {
        search::g_s3AiSensitivityFile = d;
        std::cout << "[S3 AI sensitivity file = " << search::g_s3AiSensitivityFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_ROOTS_PER_SEED")) {
        search::g_s3AiSensitivityRootsPerSeed = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_ALTS")) {
        search::g_s3AiSensitivityAlternatives = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_AI_SENSITIVITY_SIMS")) {
        search::g_s3AiSensitivitySims = std::max(1, std::atoi(d));
    }
    if (const char *d = std::getenv("STS_S3_RNG_EXPOSURE_DIAG")) {
        search::g_s3RngExposureDiag = std::atoi(d) != 0;
        std::cout << "[S3 RNG exposure diag = " << (search::g_s3RngExposureDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_RNG_EXPOSURE_DIAG_FILE")) {
        search::g_s3RngExposureDiagFile = d;
        std::cout << "[S3 RNG exposure diag file = " << search::g_s3RngExposureDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_BELIEF_AUDIT_FILE")) {
        search::g_s3BeliefAuditFile = d;
        std::cout << "[S3 belief audit file = " << search::g_s3BeliefAuditFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_DIAG")) {
        search::g_s3RootRaceDiag = std::atoi(d) != 0;
        std::cout << "[S3 root-race diag = " << (search::g_s3RootRaceDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_DIAG_FILE")) {
        search::g_s3RootRaceDiagFile = d;
        std::cout << "[S3 root-race diag file = " << search::g_s3RootRaceDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROOT_RACE_MAX_STATES")) {
        search::g_s3RootRaceDiagMaxStates = std::max(1, std::atoi(d));
        std::cout << "[S3 root-race max states = " << search::g_s3RootRaceDiagMaxStates << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_GATE_TIMING_DIAG")) {
        search::g_s3GateTimingDiag = std::atoi(d) != 0;
        std::cout << "[S3 Q-gate timing diag = "
                  << (search::g_s3GateTimingDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_GATE_TIMING_DIAG_FILE")) {
        search::g_s3GateTimingDiagFile = d;
        std::cout << "[S3 Q-gate timing diag file = "
                  << search::g_s3GateTimingDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_UNION_EXPAND")) {
        search::g_s3UnionExpand = std::atoi(d) != 0;
        std::cout << "[S3 union-expand = " << (search::g_s3UnionExpand ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CPU_DIAG")) {
        search::g_reuseCpuDiag = std::atoi(d) != 0;
        std::cout << "[reuse cpu-diag = " << (search::g_reuseCpuDiag ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_REUSE_CPU_DIAG_FILE")) {
        search::g_reuseCpuDiagFile = d;
        std::cout << "[reuse cpu-diag file = " << search::g_reuseCpuDiagFile << "]\n";
    }
    if (const char *d = std::getenv("STS_FORCE_RELIC")) {      // force a relic at run start (paired A/B)
        const std::string name(d);
        int id = -1;
        for (int i = 0; i < kNumRelics; ++i)
            if (name == relicEnumNames[i]) { id = i; break; }
        if (id < 0) {
            std::cerr << "[STS_FORCE_RELIC] unknown relic name: " << name << "\n";
        } else {
            g_forceRelic = (RelicId)id;
            std::cout << "[forced relic at run start: " << relicEnumNames[id] << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_BELIEF")) {      // S3 ablation: particle belief reweighting
        search::g_s3Belief = std::atoi(d) != 0;
        std::cout << "[S3 ablation: belief=" << (search::g_s3Belief ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_POOL_REDIRECT")) {  // S3 fair: forced-move budget pool redirect (opt-in)
        search::g_s3PoolRedirect = std::atoi(d) != 0;
        std::cout << "[S3 pool-redirect = " << (search::g_s3PoolRedirect ? "ON" : "off") << "]\n";
    }
    // A2: dynamic alpha by rollout length (opt-in)
    if (const char *d = std::getenv("STS_VNET_ALPHA_LEN")) {
        search::g_vnetAlphaLen = std::atoi(d) != 0;
        if (const char *t = std::getenv("STS_VNET_ALPHA_LEN_TABLE")) {
            search::g_vnetAlphaLenTable.clear();
            std::string ts(t);
            size_t pos = 0;
            while (pos < ts.size()) {
                auto comma = ts.find(',', pos);
                if (comma == std::string::npos) comma = ts.size();
                auto colon = ts.find(':', pos);
                if (colon != std::string::npos && colon < comma) {
                    int ceil = std::stoi(ts.substr(pos, colon-pos));
                    double a = std::stod(ts.substr(colon+1, comma-colon-1));
                    search::g_vnetAlphaLenTable.push_back({ceil, a});
                }
                pos = comma + 1;
            }
        }
        std::cout << "[VNet alpha-len = " << (search::g_vnetAlphaLen ? "ON" : "off");
        if (search::g_vnetAlphaLen) {
            std::cout << " table=";
            for (size_t i = 0; i < search::g_vnetAlphaLenTable.size(); ++i) {
                if (i) std::cout << ",";
                std::cout << search::g_vnetAlphaLenTable[i].first << ":"
                          << search::g_vnetAlphaLenTable[i].second;
            }
        }
        std::cout << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PRUNE")) {       // S3 ablation: canPruneAsDead pruning
        search::g_s3Prune = std::atoi(d) != 0;
        std::cout << "[S3 ablation: prune=" << (search::g_s3Prune ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_CHAIN")) {       // S3 ablation: deterministic chain compression
        search::g_s3Chain = std::atoi(d) != 0;
        std::cout << "[S3 ablation: chain=" << (search::g_s3Chain ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_LIVE")) {        // S3 ablation: live-valid root-edge filter
        search::g_s3Live = std::atoi(d) != 0;
        std::cout << "[S3 ablation: live=" << (search::g_s3Live ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_CRN")) {         // S3 opt-in: root CRN warm start (once per fresh searcher)
        search::g_s3Crn = std::atoi(d) != 0;
        std::cout << "[S3 ablation: crn=" << (search::g_s3Crn ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_PARTICLES")) {   // S3 belief particle count (default 64)
        const int n = std::atoi(d);
        if (n >= 1) {
            search::g_s3Particles = n;
            std::cout << "[S3 particles = " << search::g_s3Particles << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_EXPAND")) {      // Phase 6: on-no-valid-edge expansion (requires live-valid semantics)
        search::g_s3Expand = std::atoi(d) != 0;
        std::cout << "[S3 expand = " << (search::g_s3Expand ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_EXPAND_MAX")) {  // cap on new edges added per expansion (default 32)
        const int n = std::atoi(d);
        if (n >= 1) search::g_s3ExpandMaxNew = n;
    }
    if (const char *d = std::getenv("STS_S3_EXPAND_SIMPLE")) {  // no-PUCT edge expansion: pick by rolloutWeight
        search::g_s3ExpandSimple = std::atoi(d) != 0;
        std::cout << "[S3 expand-simple = " << (search::g_s3ExpandSimple ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_POLICY")) {  // sample rollout actions from the GBM policy prior (opt-in)
        search::g_s3RolloutPolicy = std::atoi(d) != 0;
        std::cout << "[S3 rollout-policy = " << (search::g_s3RolloutPolicy ? "ON" : "off") << "]\n";
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_K")) {      // A1: K rollouts per leaf, averaged (opt-in)
        const int k = std::atoi(d);
        if (k >= 1) {
            search::g_s3RolloutK = k;
            std::cout << "[S3 rollout-K = " << search::g_s3RolloutK << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_ROLLOUT_TURN_STOP")) {  // A4: stop rollout after N full player turns (opt-in)
        const int n = std::atoi(d);
        if (n >= 0) {
            search::g_s3RolloutTurnStop = n;
            std::cout << "[S3 rollout turn-stop = " << search::g_s3RolloutTurnStop << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_S3_TURN_ROLLOUT")) {  // B1: tactical turn-beam rollout (opt-in)
        search::g_s3TurnRollout = std::atoi(d) != 0;
        if (search::g_s3TurnRollout) {
            if (const char *w = std::getenv("STS_S3_TURN_BEAM_WIDTH")) {
                const int n = std::atoi(w);
                if (n >= 1) search::g_s3TurnBeamWidth = n;
            }
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W1")) search::g_s3TurnScoreW1 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W2")) search::g_s3TurnScoreW2 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W3")) search::g_s3TurnScoreW3 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W4")) search::g_s3TurnScoreW4 = std::atof(w);
            if (const char *w = std::getenv("STS_S3_TURN_SCORE_W5")) search::g_s3TurnScoreW5 = std::atof(w);
            std::cout << "[S3 turn-beam rollout ON: width=" << search::g_s3TurnBeamWidth
                      << " scorer w1..w5=" << search::g_s3TurnScoreW1 << "/" << search::g_s3TurnScoreW2
                      << "/" << search::g_s3TurnScoreW3 << "/" << search::g_s3TurnScoreW4
                      << "/" << search::g_s3TurnScoreW5 << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_RISK_LAMBDA")) {    // risk sensitivity for Searcher3 PUCT
        search::g_riskLambda = std::atof(d);
        std::cout << "[risk lambda = " << search::g_riskLambda << "]\n";
    }
    if (const char *d = std::getenv("STS_VNET")) {           // learned V_combat leaf value
        std::string path = std::string(d) == "1" ? "build/v_combat_trees.txt" : d;
        if (search::g_combatVNet.load(path)) {
            g_effectiveVNetPath = path;
            search::g_useVNet = true;
            if (const char *a = std::getenv("STS_VNET_ALPHA")) search::g_vnetAlpha = std::atof(a);
            if (const char *b = std::getenv("STS_COMBAT_WIN_BONUS"))
                search::g_combatVNet.setWinBonus(std::atof(b));
            if (const char *c = std::getenv("STS_VNET_COND_BOSS"))
                search::g_vnetCondBossOnly = std::atoi(c) != 0;
            if (const char *c = std::getenv("STS_VNET_COND_ACT3"))
                search::g_vnetCondAct3 = std::atoi(c) != 0;
            std::cout << "[V_combat leaf value ON: " << path << ", "
                      << search::g_combatVNet.description() << ", alpha "
                      << search::g_vnetAlpha
                      << (search::g_vnetCondBossOnly ? ", cond-boss-only" : "")
                      << (search::g_vnetCondAct3 ? ", cond-act3" : "") << "]\n";
        } else {
            std::cout << "[V_combat load FAILED: " << path << "]\n";
        }
    }
    // V_combat leaf default (§148 hyperparameter-tuned model trained on the
    // 7k combat dataset, 1.58M rows / 87K fights). 50-trial Optuna TPE search
    // found better-regularized XGBoost params (min_child_weight 82, L1 α=1.8,
    // γ=4.4, subsample 0.54, eta 0.03). Trained on the full 7k corpus with
    // these params, exported at 1000 trees. 64-seed S3-fair gate: 37.5% win
    // vs 31.2% for the honest-data tuned model and 20.3% for the original
    // (§126 model). The improvement is +6.3pp from 5.5× data and +10.9pp
    // from hyperparameters for a total of +17.2pp over the §126 baseline.
    // Scoped: fair + Searcher3 only, when STS_VNET is unset.
    if (!std::getenv("STS_VNET") && search::g_fairPlay && search::g_useSearcher3) {
        const char *vnetDefault = "models/v_combat_7k_tuned.txt";
        if (search::g_combatVNet.load(vnetDefault)) {
            g_effectiveVNetPath = vnetDefault;
            search::g_useVNet = true;
            search::g_vnetAlpha = 0.3;
            std::cout << "[V_combat leaf default ON: " << vnetDefault << ", "
                      << search::g_combatVNet.description() << ", alpha "
                      << search::g_vnetAlpha << " (fair S3, §148)]\n";
        } else {
            std::cout << "[V_combat leaf default load FAILED: "
                      << vnetDefault << " (continuing without)]\n";
        }
    }
    // Per-encounter specialization overlay (per-boss fine-tuned trees from
    // train_value_combat_per_encounter.py, or combat_mlp_meta_v1 deltas already
    // inside a loaded base). Must run after the base model is loaded (STS_VNET
    // or the fair-S3 default): loadEncounterModels replaces the base weights
    // with <dir>/_pooled.txt when present and dispatches predict(bc) to
    // <dir>/<ENUM_NAME>.txt per-encounter models. A missing/invalid dir only
    // warns and keeps the already-loaded base model.
    if (const char *d = std::getenv("STS_VNET_PER_ENCOUNTER")) {
        const std::string dir = d;
        if (search::g_combatVNet.loadEncounterModels(dir)) {
            std::vector<int> encs;
            encs.reserve(search::g_combatVNet.encounterModels.size());
            for (const auto &kv : search::g_combatVNet.encounterModels) encs.push_back(kv.first);
            std::sort(encs.begin(), encs.end());
            std::string names;
            for (int e : encs) {
                if (!names.empty()) names += ",";
                names += monsterEncounterEnumNames[e];
            }
            std::cout << "[V_combat per-encounter models ON: " << dir << " ("
                      << encs.size() << "): " << names << "; base "
                      << search::g_combatVNet.description() << "]\n";
        } else {
            std::cout << "[V_combat per-encounter load FAILED: " << dir
                      << " (no per-encounter dispatch; continuing with the "
                         "already-loaded base model)]\n";
        }
    }
    // Zero-mean ranking correction (STS_VNET_RANK_CORR, experimental,
    // standalone diagnostic model — NOT a default; nothing is promoted without
    // a paired gameplay gate): a small compact-tree model trained on
    // group-centered leaf-value residuals, ADDED on top of the
    // primary vnet/PVNet leaf value in evaluateLeaf()/evaluateLeafState() to
    // improve within-group action ranking without shifting the HP scale (the
    // fair-path search-complete clamp re-zeroes the per-search mean). Parsed
    // after the STS_VNET region so it works with the deployed vnet and with
    // experimental vnets. Non-fatal: a missing/invalid path only warns and
    // keeps the correction off (behavior byte-identical to the uncorrected
    // searcher).
    if (const char *d = std::getenv("STS_VNET_RANK_CORR")) {
        const std::string path = d;
        if (search::g_combatVNetRankCorr.load(path)) {
            search::g_useVNetRankCorr = true;
            std::cout << "[V_combat rank-correction ON: " << path << ", "
                      << search::g_combatVNetRankCorr.description() << "]\n";
        } else {
            std::cout << "[V_combat rank-correction load FAILED: " << path
                      << " (continuing without; behavior byte-identical to the "
                         "uncorrected searcher)]\n";
        }
    }
    // Residual VNet correction (STS_VNET_RESIDUAL=<path>, STS_VNET_RESIDUAL_BETA=<b>):
    // the loaded model is ADDED with weight beta on top of the primary VNet.
    // At beta=0, behavior is byte-identical to the uncorrected searcher.
    if (const char *d = std::getenv("STS_VNET_RESIDUAL")) {
        const std::string path = d;
        if (const char *b = std::getenv("STS_VNET_RESIDUAL_BETA"))
            search::g_vnetResidualBeta = std::atof(b);
        if (search::g_combatVNetResidual.load(path)) {
            search::g_useVNetResidual = true;
            std::cout << "[V_combat residual ON: " << path << ", beta="
                      << search::g_vnetResidualBeta << " "
                      << search::g_combatVNetResidual.description() << "]\n";
        } else {
            std::cout << "[V_combat residual load FAILED: " << path << "]\n";
        }
    }
    one_combat::configureVNetQueryLogFromEnvironment();
    one_combat::configureParticleDiagnosticsFromEnvironment();
    if (const char *d = std::getenv("STS_DIST_VNET")) {    // distributional V_combat (transformer, 5-head)
        std::string path = d;
        if (search::g_combatDistVNet.load(path)) {
            search::g_useDistVNet = true;
            std::cout << "[Dist V_combat ON: " << path << ", "
                      << search::g_combatDistVNet.description() << "]\n";
        } else {
            std::cout << "[Dist V_combat load FAILED: " << path << "]\n";
        }
    }
    if (const char *d = std::getenv("STS_PVNET")) {        // shared policy-value network (AlphaZero-style)
        std::string path = d;
        if (search::g_combatPVNet.load(path)) {
            search::g_usePVNet = true;
            std::cout << "[PVNet ON: " << path << ", "
                      << search::g_combatPVNet.description() << "]\n";
        } else {
            std::cout << "[PVNet load FAILED: " << path << "]\n";
        }
    }
    if (search::g_usePVNet) {
        if (const char *a = std::getenv("STS_PVNET_ALPHA")) search::g_pvnetAlpha = std::atof(a);
        if (const char *v = std::getenv("STS_PVNET_VALUE_ONLY")) search::g_pvnetValueOnly = std::atoi(v) != 0;
        if (const char *h = std::getenv("STS_PVNET_HP_SCALE")) search::g_pvnetHpScale = std::atoi(h) != 0;
        // Phase 6 deployment-speed knobs (S3 leaf). STS_PVNET_CACHE defaults
        // ON (behavior-preserving; visibleHash leaf-value cache at the
        // direct-eval sites). STS_PVNET_COND_{TURN,DEPTH,BOSS} gate the
        // per-expansion NN leaf: rollout-only for easy continuations, NN for
        // long/unresolved ones. Defaults preserve pre-phase-6 behavior.
        if (const char *c = std::getenv("STS_PVNET_CACHE")) search::g_pvnetCache = std::atoi(c) != 0;
        if (const char *c = std::getenv("STS_PVNET_COND_TURN")) search::g_pvnetCondMinTurn = std::atoi(c);
        if (const char *c = std::getenv("STS_PVNET_COND_DEPTH")) search::g_pvnetCondMinDepth = std::atoi(c);
        if (const char *c = std::getenv("STS_PVNET_COND_BOSS")) search::g_pvnetCondBossOnly = std::atoi(c) != 0;
        std::cout << "[PVNet alpha = " << search::g_pvnetAlpha;
        if (search::g_pvnetValueOnly) std::cout << ", value-only";
        if (search::g_pvnetHpScale) std::cout << ", hp-scale";
        if (search::g_pvnetCondMinTurn > 0) std::cout << ", cond-turn>=" << search::g_pvnetCondMinTurn;
        if (search::g_pvnetCondMinDepth > 0) std::cout << ", cond-depth>=" << search::g_pvnetCondMinDepth;
        if (search::g_pvnetCondBossOnly) std::cout << ", cond-boss-only";
        if (!search::g_pvnetCache) std::cout << ", leaf-cache-off";
        std::cout << "]\n";
    }
    // AZ-lite policy-guided PUCT selection. DEFAULT ON (+4.3pp full-run win @512
    // vs plain UCB, §26): auto-loads the compact net if present. STS_POLICY=0
    // disables; STS_POLICY=<path> overrides the file; STS_POLICY=1 uses the full
    // 447-tree net. Skipped for policygen so base datasets stay UCB-generated
    // (set STS_POLICY explicitly there for AlphaZero-style self-play iteration).
    {
        const char *d = std::getenv("STS_POLICY");
        const bool disabled = d && std::string(d) == "0";
        if (!disabled && mode != "policygen") {
            std::string path = "models/policy_trees_c.txt";
            if (d && std::string(d) == "1")      path = "build/policy_trees.txt";
            else if (d)                          path = d;
            search::g_policyNet.isPolicy = true;
            if (search::g_policyNet.load(path)) {
                g_effectivePolicyPath = path;
                search::g_usePolicyNet = true;
                std::cout << "[policy PUCT ON: " << path << ", "
                          << search::g_policyNet.description() << "]\n";
            } else if (d) {                       // warn only if explicitly requested
                std::cout << "[policy net load FAILED: " << path << "]\n";
            }
        }
    }
    if (search::g_usePolicyNet || search::g_usePVNet) {
        if (const char *c = std::getenv("STS_CPUCT")) search::g_cPuct = std::atof(c);
        std::cout << "[c_puct = " << search::g_cPuct << "]\n";
    }

    if (mode == "strategicmarggen") {
        // Encounter-marginalization diagnostic: uniform sample per run, H hidden worlds.
        // Tier-B branch contract frozen at K=3 fights, 150/100/50 sims, bootstrap=true.
        int nSeeds     = argc > 2 ? std::stoi(argv[2]) : 20;
        int outerSims  = argc > 3 ? std::stoi(argv[3]) : 1000;
        int H          = argc > 4 ? std::stoi(argv[4]) : 4;
        int maxPerRun  = argc > 5 ? std::stoi(argv[5]) : 20;
        std::string out = argc > 6 ? argv[6] : "build/hidden_marg.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 300000;
        std::cout << "strategicmarggen seeds " << seedOff << ".." << seedOff+nSeeds-1
                  << " outerSims=" << outerSims << " H=" << H
                  << " maxPerRun=" << maxPerRun
                  << " (Tier-B branch: K=3, 150/100/50, bootstrap=true)"
                  << " -> " << out << '\n';
        strategicMargGen(nSeeds, outerSims, H, maxPerRun, out, seedOff);

    } else if (mode == "oocfactoreval") {
        // nDecisions is explicit for tools/seed_guard.sh and checked against
        // the manifest by the offline workflow.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_factor/manifest.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_factor/adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        std::cout << "oocfactoreval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart, nDecisions);

    } else if (mode == "oocmargtradeoffeval") {
        // Each replicate resamples the remaining encounters once, shared by
        // the safe/strength sibling actions.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        std::cout << "oocmargtradeoffeval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart,
                          nDecisions, true);

    } else if (mode == "oock3tradeoffeval") {
        // Resolve the frozen semantic pair before evaluating sibling-shared
        // marginal futures under the strategic K=3+bootstrap contract.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/k3_targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/k3_validation.csv";
        int futures = argc > 5 ? std::stoi(argv[5]) : 16;
        int futureStart = argc > 6 ? std::stoi(argv[6]) : 1000;
        if (futures < 0) throw std::runtime_error("oock3tradeoffeval: futures must be nonnegative");
        std::cout << "oock3tradeoffeval decisions=" << nDecisions
                  << " futures=" << futures << " futureStart=" << futureStart
                  << " contract=K3+bootstrap -> " << out << '\n';
        oocFactorEvaluate(manifest, out, 0, futures, futureStart,
                          nDecisions, true, true);

    } else if (mode == "oocsemanticfullruneval") {
        // Resolve the frozen semantic pair exactly as oock3tradeoffeval does,
        // then continue both siblings to terminal run outcome.
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_targeted/fullrun_targets.csv";
        std::string out = argc > 4 ? argv[4] : "build/ooc_targeted/fullrun_adjudication.csv";
        int referenceSims = argc > 5 ? std::stoi(argv[5]) : 1000;
        int futures = argc > 6 ? std::stoi(argv[6]) : 16;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        if (futures < 0) throw std::runtime_error("oocsemanticfullruneval: futures must be nonnegative");
        std::cout << "oocsemanticfullruneval decisions=" << nDecisions
                  << " referenceSims=" << referenceSims << " futures=" << futures
                  << " futureStart=" << futureStart << " -> " << out << '\n';
        oocFactorEvaluate(manifest, out, referenceSims, futures, futureStart,
                          nDecisions, true, false, true);

    } else if (mode == "oocsemanticselftest") {
        semanticPilotSelfTest();
    } else if (mode == "oocsemanticcapture") {
        if(argc!=6) throw std::runtime_error("usage: one_combat oocsemanticcapture N_SEEDS SEED_OFFSET MANIFEST.json TEACHER.json");
        semanticPilotCapture(std::stoi(argv[2]),std::stoull(argv[3]),argv[4],argv[5]);
    } else if (mode == "oocsemanticeval") {
        if(argc!=6 && argc!=7) throw std::runtime_error("usage: one_combat oocsemanticeval N_DECISIONS MANIFEST.json OUT.csv TEACHER.json [COMBAT.csv]");
        semanticPilotEvaluate(std::stoi(argv[2]),argv[3],argv[4],argv[5],argc==7?argv[6]:"");
    } else if (mode == "oockbudgeteval") {
        int nDecisions = argc > 2 ? std::stoi(argv[2]) : 0;
        std::string manifest = argc > 3 ? argv[3] : "build/ooc_k_budget/manifest.json";
        std::string out = argc > 4 ? argv[4] : "build/ooc_k_budget/rows.csv";
        std::string budgetText = argc > 5 ? argv[5] : "10000,10000,10000";
        int futures = argc > 6 ? std::stoi(argv[6]) : 4;
        int futureStart = argc > 7 ? std::stoi(argv[7]) : 0;
        std::string side = argc > 8 ? argv[8] : "A";
        std::string spec = argc > 9 ? argv[9] : "build/ooc_k_budget/experiment.json";
        int shardIndex = argc > 10 ? std::stoi(argv[10]) : -1;
        int shardCount = argc > 11 ? std::stoi(argv[11]) : 24;
        int workIndex = argc > 12 ? std::stoi(argv[12]) : -1;
        int workCount = argc > 13 ? std::stoi(argv[13]) : 12;
        std::vector<int> schedule; std::stringstream bs(budgetText); std::string cell;
        while(std::getline(bs,cell,','))schedule.push_back(std::stoi(cell));
        nlohmann::json manifestDoc; {std::ifstream mf(manifest);if(!mf)throw std::runtime_error("oockbudgeteval: cannot open manifest");mf>>manifestDoc;}
        if(!manifestDoc.contains("decisions")||(int)manifestDoc["decisions"].size()!=nDecisions)
            throw std::runtime_error("oockbudgeteval: guarded decision count does not match manifest");
        std::cout<<"oockbudgeteval decisions="<<nDecisions<<" schedule="<<budgetText
                 <<" futures="<<futures<<" futureStart="<<futureStart<<" side="<<side
                 <<" shard="<<shardIndex<<'/'<<shardCount
                 <<" work="<<workIndex<<'/'<<workCount
                 <<" -> "<<out<<'\n';
        oocBudgetEvaluate(manifest,out,schedule,futures,futureStart,side,spec,
                          shardIndex,shardCount,workIndex,workCount);

    } else if (mode == "run") {          // one whole run, verbose
        int sims         = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t sd = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc          = argc > 4 ? std::stoi(argv[4]) : 0;
        RunResult r = runFullRun(sd, sims, asc, false);
        std::printf("=== %s ===  reached floor %d (act %d)  hp %d/%d  %.2fs\n",
                    r.won ? "WIN" : "DEAD", r.floor, r.act, r.hpEnd, r.maxHp, r.sec);

    } else if (mode == "datagen") {       // CSV of (state features, run outcome) for offline V(state)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "data.csv";
        search::g_fairPlay = argc > 7 ? std::stoi(argv[7]) != 0 : false;
        if (const char *sf = std::getenv("STS_FAIR")) {              // warn when the positional arg overrides the env
            const bool envFair = std::atoi(sf) != 0;
            if (envFair != search::g_fairPlay)
                std::cerr << "[datagen] warning: positional arg overrides STS_FAIR=" << sf
                          << " -> g_fairPlay=" << (search::g_fairPlay ? 1 : 0) << "\n";
        }
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        dataGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "datagen2") {      // RICH per-decision state (relics/upgrades/potions/future/path) + outcome
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 2000;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.25;
        std::string out = argc > 6 ? argv[6] : "vrich.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "e2cgen") {        // E2c matched RAW/POST combat-terminal dataset
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 8;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/e2c_raw_terminal.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        e2cGen(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "datagen3") {      // RICH outcomes + paired rest/card counterfactuals
        int nSeeds       = argc > 2  ? std::stoi(argv[2])  : 2000;
        int sims         = argc > 3  ? std::stoi(argv[3])  : 300;
        int asc          = argc > 4  ? std::stoi(argv[4])  : 0;
        double eps       = argc > 5  ? std::stod(argv[5])  : 0.05;
        std::string out  = argc > 6  ? argv[6] : "vrich.csv";
        std::string rout = argc > 7  ? argv[7] : "rest_cf.csv";
        long long seedOff= argc > 8  ? std::stoll(argv[8]) : 0;
        int restSims     = argc > 9  ? std::stoi(argv[9])  : sims;
        int restFutures  = argc > 10 ? std::stoi(argv[10]) : 1;
        int restStride   = argc > 11 ? std::stoi(argv[11]) : 4;
        std::string cardOut = argc > 12 ? argv[12] : "";
        int cardSims     = argc > 13 ? std::stoi(argv[13]) : 0;
        int cardFights   = argc > 14 ? std::stoi(argv[14]) : 3;
        int cardFutures  = argc > 15 ? std::stoi(argv[15]) : 1;
        int cardStride   = argc > 16 ? std::stoi(argv[16]) : 4;
        int cardMax      = argc > 17 ? std::stoi(argv[17]) : 1;
        std::uint64_t cardFutureSalt = argc > 18 ? std::stoull(argv[18]) : 0;
        int cardAdaptiveMax = argc > 19 ? std::stoi(argv[19]) : 0;
        double cardAdaptiveGap = argc > 20 ? std::stod(argv[20]) : 5.0;
        dataGen2(nSeeds, sims, asc, eps, out, seedOff, rout,
                 restSims, restFutures, restStride, cardOut,
                 cardSims, cardFights, cardFutures, cardStride, cardMax, cardFutureSalt,
                 cardAdaptiveMax, cardAdaptiveGap);

    } else if (mode == "pathcfgen") {     // one uniformly sampled paired route decision per run
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 100;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "path_cf.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 2;
        std::uint64_t salt= argc > 9 ? std::stoull(argv[9]) : 0;
        pathCounterfactualGen(nSeeds, outerSims, asc, out, off, branchSims, futures, salt);

    } else if (mode == "oocnextgen") {    // all legal OOC actions, labels at next combat
        int nSeeds        = argc > 2 ? std::stoi(argv[2]) : 500;
        int outerSims     = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc           = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out   = argc > 5 ? argv[5] : "ooc_next_combat.csv";
        std::uint64_t off = argc > 6 ? std::stoull(argv[6]) : 0;
        int branchSims    = argc > 7 ? std::stoi(argv[7]) : 100;
        int futures       = argc > 8 ? std::stoi(argv[8]) : 1;
        oocNextCombatGen(nSeeds, outerSims, asc, out, off, branchSims, futures);

    } else if (mode == "winnettest") {    // validate C++ WinNet (OOC win trees) vs Python predictions
        // Reads a tierb-schema CSV (state block between `chosen` and `won`),
        // runs the native WinNet on the rich state of each row, and prints
        // "rowidx,vwin" so the Python checker can compare tree-walks exactly.
        std::string trees = argc > 2 ? argv[2] : "models/v_win_trees.txt";
        std::string csv   = argc > 3 ? argv[3] : "build/strategic_qwin.csv";
        long long maxRows = argc > 4 ? std::stoll(argv[4]) : 200;
        if (!g_winNet.load(trees, richIdxMap())) { std::cerr << "load failed: " << trees << "\n"; return 1; }
        std::ifstream f(csv);
        std::string line;
        if (!std::getline(f, line)) { std::cerr << "empty csv\n"; return 1; }
        // header: find the state block between `chosen` and `won`
        std::vector<std::string> hdr; std::stringstream hs(line); std::string cell;
        while (std::getline(hs, cell, ',')) hdr.push_back(cell);
        int ci = -1, wi = -1;
        for (int i = 0; i < (int)hdr.size(); ++i) {
            if (hdr[i] == "chosen") ci = i;
            if (hdr[i] == "won") { wi = i; break; }
        }
        if (ci < 0 || wi < 0 || wi - ci <= 1) { std::cerr << "no state block between chosen and won\n"; return 1; }
        const int nState = wi - ci - 1;
        std::vector<float> raw(nState);
        long long n = 0;
        while (std::getline(f, line) && n < maxRows) {
            std::stringstream ss(line); std::string cell;
            int idx = 0;
            for (int i = 0; i < wi; ++i) {
                std::getline(ss, cell, ',');
                if (i > ci) raw[idx++] = std::stof(cell);
            }
            if (idx != nState) { std::cerr << "short row " << n << "\n"; return 1; }
            std::printf("%lld,%.9f\n", n, g_winNet.predict(raw));
            ++n;
        }
        std::printf("WINNET TEST: %lld rows\n", n);

    } else if (isCombatModelDiagnosticMode(mode)) {
        return runCombatModelDiagnosticMode(mode, argc, argv);

    } else if (mode == "speedtest") {     // single-fight Searcher3 speed measurement
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        std::uint64_t seed = argc > 3 ? std::stoull(argv[3]) : 42;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        // Init a fight directly with a known encounter
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        BattleContext bc; bc.init(gc, MonsterEncounter::CULTIST);
        std::printf("speedtest: %s  hp=%d/%d  hand=%d  draw=%zu\n",
                    monsterEncounterStrings[(int)bc.encounter], bc.player.curHp,
                    bc.player.maxHp, bc.cards.cardsInHand, bc.cards.drawPile.size());
        for (int s : {100, 500, 1000, 2500}) {
            search::BattleScumSearcher3 s3(bc, 64);
            auto t0 = std::chrono::steady_clock::now();
            s3.search(s);
            auto t1 = std::chrono::steady_clock::now();
            double sec = std::chrono::duration<double>(t1 - t0).count();
        std::printf("  S3 %5d sims: %6.3fs  %6d sim/s  rootVisits=%lld\n",
                    s, sec, int(s/sec),
                    (long long)s3.root.simulationCount);
        }

    } else if (mode == "searchdiag") {    // Searcher2 rollout-usage diagnostics
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 8;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/searchdiag.csv";
        int probeEvery = argc > 6 ? std::stoi(argv[6]) : 1;
        std::uint64_t seedOff = argc > 7 ? std::stoull(argv[7]) : 0;
        searchDiag(nSeeds, sims, asc, out, probeEvery, seedOff);

    } else if (mode == "combatgen") {     // CSV of (combat state, fight outcome) for V_combat
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vcombat.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        combatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "distgen") {       // combatgen + rich distributional labels (endTurn, potion use)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vdist.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        distCombatGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "fairgen") {       // Searcher3 ISMCTS: value + policy rows with visit distributions
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/fair_val.csv";
        std::string pout = argc > 7 ? argv[7] : "build/fair_pol.csv";
        std::string oout = argc > 8 ? argv[8] : "build/fair_ooc.csv";
        long long seedOff = argc > 9 ? std::stoll(argv[9]) : 0;
        // fairgen emits Searcher3 policy rows via g_onSearchComplete3; force the
        // project-fair Searcher3 regime here so callers cannot silently produce
        // data under the wrong producer (STS_FAIR=1 STS_SEARCHER3=1 no longer
        // required; the env vars still mean the same thing for other modes).
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[fairgen forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        fairGen(nSeeds, sims, asc, eps, vout, pout, oout, seedOff);

    } else if (mode == "runwinparity") {
        const std::string fixture = argc > 2 ? argv[2] : "tools/runwin_e2c_synthetic_parity.csv";
        return one_combat::runwinParity(fixture);

    } else if (mode == "e2cprojectiontest") {
        return one_combat::e2cRawProjectionParityTest();

    } else if (mode == "particle_leaf_probe") {
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/particle_leaf_probe.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[particle_leaf_probe forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        particleLeafProbe(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "particle_posterior_probe") {   // Phase-1b posterior-valid probe
        int nSeeds = argc > 2 ? std::stoi(argv[2]) : 4;
        int sims = argc > 3 ? std::stoi(argv[3]) : 300;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/particle_posterior_probe.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        search::g_fairPlay = true;
        search::g_useSearcher3 = true;
        std::cout << "[particle_posterior_probe forced: fair-play / determinized MCTS + Searcher3 engine ON]\n";
        particlePosteriorProbe(nSeeds, sims, asc, out, seedOff);


    } else if (one_combat::isFightReplayMode(mode)) {
        return one_combat::runFightReplayMode(mode, argc, argv);

    } else if (mode == "strategicgen") {  // Phase 5: one row per OOC decision, full rich state
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 500;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/strategic.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        strategicGen(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "strategicgen2") {   // Tier-B: strategicgen rows + per-action one-ply labels
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 200;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        std::string out = argc > 5 ? argv[5] : "build/strategic_tierb.csv";
        long long seedOff = argc > 6 ? std::stoll(argv[6]) : 0;
        strategicGen2(nSeeds, sims, asc, out, seedOff);

    } else if (mode == "policygen") {     // CSV of (state, action, visit/total) MCTS policy targets (AZ-lite)
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 10000;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string out = argc > 6 ? argv[6] : "build/vpolicy.csv";
        long long seedOff = argc > 7 ? std::stoll(argv[7]) : 0;
        policyGen(nSeeds, sims, asc, eps, out, seedOff);

    } else if (mode == "mapbatch") {      // companion full-map graph table for rich/meta/card CSVs
        if (argc < 4) {
            std::cerr << "usage: one_combat mapbatch SOURCE.csv MAPS.csv\n";
            return 2;
        }
        exportCardCfMaps(argv[2], argv[3]);

    } else if (mode == "dumpmap") {       // dump a seed's map GRAPH (nodes+edges) for the future GNN
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int asc = argc > 3 ? std::stoi(argv[3]) : 0;
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        const Map &map = *gc.map;
        std::printf("# seed %llu act %d  format: y x room edge_x...\n", (unsigned long long)seed, gc.act);
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const MapNode &n = map.getNode(x, y);
            if (n.room == Room::NONE || n.room == Room::INVALID) continue;
            std::printf("%d %d %d", y, x, (int)n.room);
            for (int i = 0; i < n.edgeCount; ++i) std::printf(" %d", n.edges[i]);
            std::printf("\n");
        }

    } else if (mode == "mapnntest") {    // deterministic C++-vs-Python parity for the V6 map-DAG path
        // Fixed synthetic inputs; the Python side (export_strategic.py) computes
        // the same Q from the same checkpoint — the printed numbers must match.
        if (!g_oocStrategicNet.ok || !g_oocStrategicNet.mapEnc) { std::cerr << "mapnntest: need a loaded V6 net (STS_OOC_STRATEGIC_NN)\n"; return 1; }
        std::vector<float> state(OocStrategicNet::NSTATE);
        for (int i = 0; i < OocStrategicNet::NSTATE; ++i) state[i] = (float)((i % 7) * 0.5);
        int rooms[105], edges[105], special[105];
        for (int i = 0; i < 105; ++i) {
            const int y = i / 7, x = i % 7;
            rooms[i] = i % 10;
            int em = 0;
            if (y < 14) for (int cx = 0; cx < 7; ++cx) if (((x * 3 + y) % 7) == cx) em |= 1 << cx;
            edges[i] = em;
            special[i] = (i == 5) ? 1 : 0;
        }
        const int cats[6] = {1, 2, 3, 4, 5, 6};
        const int px = 2, py = 3;
        for (int cx = 0; cx < 7; ++cx)
            std::printf("mapnntest q[child=%d] = %.10f\n", cx,
                        (double)g_oocStrategicNet.predictMapActionValue(
                            state.data(), 0x1234u, cats, 2, (int)ScreenState::MAP_SCREEN,
                            rooms, edges, special, px, py, cx));
        std::printf("mapnntest q[roots pool, no singleton] = %.10f\n",
                    (double)g_oocStrategicNet.predictMapActionValue(
                        state.data(), 0x1234u, cats, 2, (int)ScreenState::MAP_SCREEN,
                        rooms, edges, special, px, -1, -1));

    } else if (mode == "fightgen") {      // ONE pass -> BOTH value (endHp) + policy (visit-pi) CSVs
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 300;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 2500;
        int asc       = argc > 4 ? std::stoi(argv[4]) : 0;
        double eps    = argc > 5 ? std::stod(argv[5]) : 0.3;
        std::string vout = argc > 6 ? argv[6] : "build/vcombat.csv";
        std::string pout = argc > 7 ? argv[7] : "build/vpolicy.csv";
        long long seedOff = argc > 8 ? std::stoll(argv[8]) : 0;
        fightGen(nSeeds, sims, asc, eps, vout, pout, seedOff);

    } else if (mode == "wholecombatgen") {
        if (argc < 8) { std::cerr << "usage: one_combat wholecombatgen N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json\n"; return 2; }
        wholeCombatGen(std::stoi(argv[2]),std::stoi(argv[3]),std::stoi(argv[4]),argv[5],std::stoll(argv[6]),argv[7]);
    } else if (mode == "combatevalgen") {
        if (argc < 8) { std::cerr << "usage: one_combat combatevalgen N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json [RUNOUT.csv]\n"; return 2; }
        combatEvalGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5], std::stoll(argv[6]), argv[7], argc > 8 ? argv[8] : "");
    } else if (mode == "oocpolicyparity") {
        if (argc < 3 || argc > 5) {
            std::cerr << "usage: one_combat oocpolicyparity SEED [SIMS] [ASC]\n";
            return 2;
        }
        return oocPolicyParitySelfTest(std::stoull(argv[2]), argc > 3 ? std::stoi(argv[3]) : 100,
                                       argc > 4 ? std::stoi(argv[4]) : 0);
    } else if (mode == "teacher_schema_compat") {
        return teacherSchemaCompatibilitySelfTest();
    } else if (mode == "ooccfaudit") {
        if (argc < 8) { std::cerr << "usage: one_combat ooccfaudit N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json\n"; return 2; }
        counterfactualSurrogateAuditGen(std::stoi(argv[2]),std::stoi(argv[3]),std::stoi(argv[4]),argv[5],std::stoull(argv[6]),argv[7]);
    } else if (mode == "oocv4h1rollout") {
        if (argc == 3 && std::string(argv[2]) == "--self-test") {
            v4ActRolloutCanary();
            return 0;
        }
        if (argc < 9) {
            std::cerr << "usage: one_combat oocv4h1rollout SEED DECISION ROLLOUTS SILVER_SIMS ASC OUT.csv TEACHER.json\n";
            return 2;
        }
        evaluateV4ActRollout(std::stoull(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
            std::stoi(argv[5]), std::stoi(argv[6]), argv[7], argv[8]);

    } else if (mode == "oocv4h1rolloutall") {
        if (argc == 3 && std::string(argv[2]) == "--self-test") {
            v4ActRolloutCanary();
            return 0;
        }
        if (argc < 8) {
            std::cerr << "usage: one_combat oocv4h1rolloutall SEED ROLLOUTS SILVER_SIMS ASC OUT.csv TEACHER.json\n";
            return 2;
        }
        evaluateV4ActRolloutAll(std::stoull(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
            std::stoi(argv[5]), argv[6], argv[7]);

    } else if (mode == "causalgen") {     // CSV of (state, card features, CRN advantage) for causal card value
        int nSeeds    = argc > 2 ? std::stoi(argv[2]) : 200;
        int sims      = argc > 3 ? std::stoi(argv[3]) : 1000;
        int N         = argc > 4 ? std::stoi(argv[4]) : 6;
        int innerSims = argc > 5 ? std::stoi(argv[5]) : 800;
        int K         = argc > 6 ? std::stoi(argv[6]) : 6;
        double eps    = argc > 7 ? std::stod(argv[7]) : 0.30;
        std::string out = argc > 8 ? argv[8] : "causal.csv";
        causalGen(nSeeds, sims, /*asc=*/0, N, innerSims, K, eps, out);

    } else if (mode == "carddump") {      // id,name,type,rarity,obtainWeight,baseDamage for all card ids
        std::cout << "id,name,type,rarity,obtainWeight,baseDamage\n";
        for (int i = 0; i < kNumCardIds; ++i) {
            Card c((CardId)i);
            std::cout << i << ',' << c.getName() << ',' << (int)c.getType() << ','
                      << (int)c.getRarity() << ',' << search::Expert::getObtainWeight((CardId)i)
                      << ',' << c.getBaseDamage() << '\n';
        }

    } else if (mode == "bestbench") {     // current best OOC stack, single arm (baseline for new experiments)
        int sims   = argc > 2 ? std::stoi(argv[2]) : 1000;
        int nSeeds = argc > 3 ? std::stoi(argv[3]) : 512;
        int asc    = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seedOffset = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        // issue 46 hardening: bestBench APPENDS to the results file and never
        // deduplicates ("caller owns truncation"). A stale file that already
        // contains rows for the requested seed block silently doubles every
        // seed, which the strict paired analyzer then rejects. Fail loudly
        // here instead of corrupting the CSV. Self-play batches use disjoint
        // offsets on fresh per-iteration files, so this never fires there.
        if (!resultsFile.empty()) {
            const std::uint64_t lo = seedOffset, hi = seedOffset + (std::uint64_t)nSeeds - 1;
            std::ifstream stale(resultsFile);
            if (stale) {
                std::string line;
                std::getline(stale, line);                     // header
                while (std::getline(stale, line)) {
                    const std::size_t comma = line.find(',');
                    if (comma == std::string::npos) continue;
                    std::uint64_t s = 0;
                    try { s = std::stoull(line.substr(0, comma)); }
                    catch (...) { continue; }
                    if (s >= lo && s <= hi) {
                        std::cerr << "bestbench: results file " << resultsFile
                                  << " already contains a row for seed " << s
                                  << " (requested block " << lo << ".." << hi << "). "
                                  << "bestbench appends without deduplication; remove "
                                  << "the stale file or use a fresh path (issue 46).\n";
                        return 1;
                    }
                }
            }
        }
        if (!bestBench(sims, nSeeds, asc, seedOffset, resultsFile)) return 1;

    } else if (mode == "reprobench") {    // repeat one full run in one process; audit determinism
        int sims = argc > 2 ? std::stoi(argv[2]) : 1000;
        int repeats = argc > 3 ? std::stoi(argv[3]) : 2;
        int asc = argc > 4 ? std::stoi(argv[4]) : 0;
        std::uint64_t seed = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        std::cout << "[reprobench: seed " << seed << ", repeats " << repeats << "]\n";
        for (int i = 0; i < repeats; ++i) {
            if (!bestBench(sims, 1, asc, seed, resultsFile, "reprobench")) return 1;
        }

    } else if (mode == "runtrace") {      // per-node human-readable trace of ONE seed (STS_FAIR for fair-play)
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc  = argc > 4 ? std::stoi(argv[4]) : 0;
        runTraceRun(seed, sims, asc);

    } else {
        std::cerr << "usage: one_combat MODE [ARGS...]\n";
        return 2;
    }
    return 0;
}
