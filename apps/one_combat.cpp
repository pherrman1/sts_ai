#include "sim/search/RunGoal.h"
#include "sim/search/NativeSilverBackend.h"
#include <cstring>
#include <stdexcept>
#include <unistd.h>
#include <filesystem>
#include "one_combat/ooc_selective_silver_audit.h"
#include "one_combat/ooc_selective_silver_sampler.h"
// one_combat.cpp -- integration driver for full-run evaluation, data generation,
// and focused search/model diagnostics.

#include "one_combat/driver_shared.h"
#include "one_combat/heart1_policy.h"
#include "one_combat/silver_price_table.h"
#include "one_combat/rollout_student.h"
#include "one_combat/expert_replay.h"
#include "one_combat/heart_outcome_capture.h"
#include "one_combat/a4_perturb.h"
#include "one_combat/heart_leaf_tail.h"
#include "one_combat/differential_replay_native.h"
#include "one_combat/screen_leaf_s0.h"
#include "one_combat/screen_leaf_net.h"
#include "one_combat/screen_leaf_gbm.h"
#include "one_combat/screen_leaf_probes.h"

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

extern bool g_collectKeys;              // default on; STS_COLLECT_KEYS=0 restores Act-3 play
static std::vector<std::string> g_mainArgv;
std::string g_mainBinaryPath;
// Resolved only after successful loading, so E3a provenance does not confuse
// an unset/failed environment request with the policy actually exercised.
static std::string g_effectiveOocStrategicPath;
static std::string g_effectiveOocStrategicTokPath;

thread_local int t_trainingHealthFailures = 0;
static thread_local int t_trainingBranchHealthFailures = 0;
static thread_local bool t_trainingRunActive = false;
std::atomic<int> g_trainingInvalidRuns{0};
std::atomic<int> g_trainingInvalidBranches{0};
std::atomic<int> g_trainingHealthFailures{0};

void trainingRunStart() {
    t_trainingHealthFailures = sts::search::g_simHealthFailureCount;
    t_trainingBranchHealthFailures = 0;
    t_trainingRunActive = true;
}

void trainingCampaignStart() {
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

std::string trainingExecutableGitSha() {
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

std::string fileSha256(const std::string &path) {
    // Model paths are operator-provided and may contain spaces.  Quote for the
    // repository's POSIX execution environments; a missing utility/file is
    // represented explicitly as an empty provenance value rather than guessed.
    std::string safe;
    for (char c : path) { if (c == '\'') safe += "'\\\"'\\\"'"; else safe += c; }
    const std::string line = trainingGitValue(("sha256sum '" + safe + "' 2>/dev/null").c_str());
    const size_t cut = line.find_first_of(" \t");
    return cut == std::string::npos ? line : line.substr(0, cut);
}

void writeTrainingProvenance(const std::string &output, const char *mode,
                                    int requested, int completed, int invalid,
                                    int healthFailures, long long rows,
                                    long long seedOffset, int sims, int asc,
                                    double epsilon) {
    std::ofstream p(output + ".provenance.json");
    if (!p) return;
    const char *envs[] = {"STS_FAIR", "STS_REUSE_MAX_SEARCHES",
                          "STS_REUSE_STATS_MODE", "STS_REUSE_ALWAYS_Q", "STS_REUSE_DIAG",
                          "STS_REUSE_OBS_STABLE", "STS_REUSE_RECONCILE_ROOT",
                          "STS_REUSE_CARRY_DIAG", "STS_REUSE_CPU_DIAG",
                          "STS_REUSE_CPU_DIAG_FILE", "STS_LIVE_VALID", "STS_STOP_AFTER_ACT",
                          "STS_FORCED_MOVE",
                          "STS_VNET", "STS_VNET_ALPHA", "STS_OOC_STRATEGIC_TOK_NN",
                          "STS_OOC_STRATEGIC_TOK_CONST_GUARD", "STS_OOC_GBM_RANKER",
                          "STS_CF_ALT_BOOT_FLOOR_TREES", "STS_CF_ALT_BOOT_WIN_TREES",
                          "STRATEGIC_BRANCH_FUTURE_OFFSET", "STRATEGIC_BRANCH_RESEED",
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
    p << "\n  },\n  \"silver_leaf\": " << effectiveSilverLeafSpecification().dump() << "\n}\n";
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

int numThreads() {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

using namespace sts;

// ---------------------------------------------------------------------------
// Enumerate legal actions in the current player-choice state
// (potions omitted).
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

    return { search::runGoalVictory(gc, g_collectKeys),
             gc.floorNum, gc.act, gc.curHp, gc.maxHp, 0,
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
            BattleContext bc{};
            inner.playoutBattle(gc, bc);
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

void evalCardRewardPolicy(GameContext &gc, bool allowSkip) {
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
static bool g_nativeCardWinRankTrace = false;
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
int    g_oocStrategicTok = 0;        // env STS_OOC_STRATEGIC_TOK_NN: V4 token net loaded
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
bool   g_oocShopBeam = false;        // env STS_OOC_SHOP_BEAM=1
int    g_oocShopBeamWidth = 32;      // env STS_OOC_SHOP_BEAM_WIDTH (clamped 4..256)
int    g_oocShopBeamDepth = 0;       // env STS_OOC_SHOP_BEAM_DEPTH (0 = until leave / no affordable actions)
int    g_oocShopBeamBudget = 4096;   // env STS_OOC_SHOP_BEAM_BUDGET: max expanded nodes per shop decision
int nativeFloorCardPick(GameContext &, int);
double nativeFloorValue(GameContext &);
bool oocShopBeamPolicy(GameContext &);          // B1 multi-step shop beam search (§2)
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
// A/B: route card picks through the deck-set NN (P(win) marginal), optionally blended with
// the v_win GBM: marg = w*NN + (1-w)*GBM. Own skip scale (P(win) units).
bool   g_cardNN     = false;     // env STS_CARD_NN=1
double g_cardNNW    = 1.0;       // env STS_CARD_NN_W: blend weight on NN (1=pure NN)
double g_cardNNSkip = 0.0;       // env STS_CARD_NN_SKIP: skip iff best P(win) marginal < this
// Direct paired action-value model (offered cards + skip), optionally with the
// full map graph. Unlike marginal value models, it learns its own skip action.
bool   g_cardAction = false;     // env STS_CARD_ACTION=1 (CA server op)
// Datagen exploration: softmax temperature over card marginals (final-floor
// units; higher = more spread). The uniform-floor prob is datagen2's `epsilon`.
double g_dgTemp = 2.0;   // env STS_DG_TEMP (swept: 1-2 good spread+quality, >=3 over-randomizes)
// Per-fight combat sim budget by difficulty (env STS_SIMS_NORMAL/ELITE/BOSS; <=0 or
// unset = use the run's base sims). Deaths cluster at elites/bosses, so we can search
// those deep and skimp on trivial hallway fights for the same win% at far less compute.
static int g_simsNormal = -1, g_simsElite = -1, g_simsBoss = -1;
// Dynamic per-fight budget via a no-peek combat outcome surrogate. C_psi is the
// historical path (§103); STS_SIM_ADAPT_CTM selects the qualified native combat
// transition model. Both predict P(death) and E[hp/maxHp|win] from pre-combat
// state, so allocation consumes no gameplay RNG. CTM-unsupported fights retain
// the caller's base budget. Adaptive allocation takes precedence over room tiers.
static bool   g_simAdapt = false;       // env STS_SIM_ADAPT=1
static double g_simAdaptMinFrac = 0.4;  // env STS_SIM_ADAPT_MIN_FRAC: budget floor as a fraction of base
static double g_simAdaptMaxFrac = 2.0;  // env STS_SIM_ADAPT_MAX_FRAC: budget ceiling as a fraction of base
static std::unique_ptr<one_combat::NativeCombatTransitionSampler> g_simAdaptCtm;
// Pick the sim budget for the fight in the current room (falls back to base).
int fightSims(const GameContext &gc, int base) {
    if (g_simAdapt && g_simAdaptCtm && gc.info.encounter != MonsterEncounter::INVALID) {
        const auto input=one_combat::captureCombatPredictorInput(
            gc,gc.info.encounter,potionKeepValue(gc));
        const auto r=g_simAdaptCtm->expectation(gc,input);
        if (!r.supported) return base;
        const double m=0.5+r.death+(1.0-r.winningHpFraction);
        const double frac=std::min(g_simAdaptMaxFrac,std::max(g_simAdaptMinFrac,m));
        return std::max(1,(int)std::llround(base*frac));
    }
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
int    g_bossDraft        = 0;      // STS_BOSS_DRAFT: rollout-based near-boss draft (experimental; hurt in A/B)
int    g_bossDraftRows    = 3;      // trigger when a hard fight is within this many map rows
int    g_bossDraftN       = 4;      // rollout: fights to simulate forward
int    g_bossDraftSims    = 150;    // rollout: inner combat sim budget
int    g_bossDraftFutures = 2;      // rollout: sampled futures per candidate
int    g_bossV            = 0;      // STS_BOSS_V: blend v_boss marginal into near-boss server picks
double g_bossVW           = 0.5;    // STS_BOSS_V_W: blend weight on the boss model (0..1)

// Experimental full-act draft evaluator.  For the immediate card decision only,
// it samples the *possible remaining encounter queues* in the current act and
// plays every fight on the selected route through the boss.  Its utility is an
// expectation over survival and a nonlinear post-fight HP safety margin, with a
// modest floor-distance discount.  It intentionally makes no V/card-model query
// for the card being picked; the regular OOC policy is used only inside a sampled
// continuation to resolve later choices.
bool   g_actFightProbeDraft = false; // STS_ACT_FIGHT_PROBE_DRAFT=1
int    g_actFightProbeSims = 100;    // STS_ACT_FIGHT_PROBE_SIMS
int    g_actFightProbeFutures = 4;   // STS_ACT_FIGHT_PROBE_FUTURES
double g_actFightProbeFloorDecay = 0.985; // STS_ACT_FIGHT_PROBE_FLOOR_DECAY
// Optional inner-search base budgets by reached checkpoint, e.g. 400,200,100.
// The live run's combat budget is unaffected; room-tier overrides still take
// precedence through fightSims().
std::vector<int> g_actFightProbeCheckpointSims; // STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS
// -1 scores every remaining fight in the current act; a positive value scores only the
// next N combat checkpoints.  This is a horizon in fights, not map nodes, so
// routes with shops/events are not given a structurally different objective.
int    g_actFightProbeMaxCheckpoints = -1; // STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS
bool   g_actFightProbeTrace = false; // STS_ACT_FIGHT_PROBE_TRACE=1
// Parallelize the independent immediate-action × sampled-future branches of a
// single OOC decision.  Off by default so ordinary multi-seed benches retain
// their existing outer OpenMP scheduling.
static bool   g_actFightProbeParallelBranches = false; // STS_ACT_FIGHT_PROBE_PARALLEL=1
// Broader version used only for a deliberately expensive Act-1 experiment:
// evaluate every legal OOC action (map, rewards, events, shop, rest, selects),
// not just cards.  This is separate so the card-only oracle remains available.
bool   g_actFightProbeAllOoc = false; // STS_ACT_FIGHT_PROBE_ALL_OOC=1
// Score and advance checkpoint fights with the entity combat model instead of
// running MCTS.  This is deliberately separate from STS_VNET: the latter is a
// leaf evaluator inside real combat search, while this one supplies both heads
// needed for a virtual post-combat transition.
bool   g_actFightProbePredict = false; // STS_ACT_FIGHT_PROBE_PREDICT=1
bool   g_actFightProbeEncounterNN = false; // STS_ACT_FIGHT_PROBE_ENCOUNTER_NN=1
double g_actFightProbePredictWinThreshold = 0.5;
static std::string g_actFightProbePredictNetPath = "selfplay/models/v_combat_entity_iter34.txt";
search::CombatValueNet g_actFightProbePredictNet;
// Optional terminal pricing for the capped checkpoint objective: after the
// final scored checkpoint, price each option's resulting branch state with the
// native win model (P(run victory)) and add it to the utility, blended by this
// weight.  HP-only checkpoint safety misses resource compounding (gold, relics,
// deck) that the trunk simulation carries forward but never prices.
double g_actFightProbeTermWin = 0.0; // STS_ACT_FIGHT_PROBE_TERM_WIN=alpha (0 = off)
// Margin gate: when > 0, the all-OOC oracle overrides a decision only if its
// best action's utility beats the runner-up by at least this margin; otherwise
// control falls through to the ordinary policy stack.  Greedy full-run oracle
// replacement is a recorded regression (EXPERIMENTS.md 66j/66m/67); the margin
// is the design-doc deployment contract for learned override layers.
double g_actFightProbeMargin = 0.0; // STS_ACT_FIGHT_PROBE_MARGIN=m (0 = always fire)
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
int g_strategicSamplesPerRun = 1;    // STRATEGIC_SAMPLES_PER_RUN: reservoir size
bool g_strategicSampleAll = false;   // STRATEGIC_SAMPLE_ALL=1: label every decision
int g_strategicBranchFights = 3;     // STRATEGIC_BRANCH_FIGHTS: battles per branch
std::vector<int> g_strategicBranchSims = {150, 100, 50}; // STRATEGIC_BRANCH_SIMS per fight
int g_strategicBranchFutures = 1;    // STRATEGIC_BRANCH_FUTURES: branch seeds per action
int g_strategicBranchFutureOffset = 0; // STRATEGIC_BRANCH_FUTURE_OFFSET: first branch seed index (research)
bool g_strategicBranchReseed = false;  // STRATEGIC_BRANCH_RESEED=1: independent game RNG per branch future

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

// --- potion keep-value (HP-equiv): high in easy fights when a hard fight is near
// (hoard), low in the hard fight itself (spend), modulated by the potion DROP
// chance. The removed Searcher2 used it in its end-state value; it now only
// feeds the combat-transition predictor input.
static int    g_potionSave    = 0;      // STS_POTION_SAVE=1: enable dynamic potion keep-value
static int    g_potionWindow  = 5;      // STS_POTION_WINDOW: only save when a hard fight is <= this many rows away
static double g_potionBonus   = 18.0;   // STS_POTION_BONUS: extra HP-equiv keep-value at max urgency
static double g_potionSpend   = 1.0;    // STS_POTION_SPEND: keep-value DURING an elite/boss (low = spend)
static double g_potionDesired = 2.5;    // STS_POTION_DESIRED: potions we'd like entering a hard fight
static const double kPotionBaseKeep = 4.0;   // the engine's original constant (neutral default)

// Per-fight potion keep-value (HP-equiv).
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

int vConnect() {
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
std::string vRequestLine(const std::string &requestWithNewline) {
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
double vStateWinNativeFeatures(const std::vector<float> &raw);
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

WinNet g_winNet;
WinNet g_floorNet;
// Research-only alternative bootstrap trees for counterfactual branch endpoints
// (STS_CF_ALT_BOOT_FLOOR_TREES / STS_CF_ALT_BOOT_WIN_TREES, §419 follow-up).
// They value bounded branch endpoints in addition to the default trees and are
// never used by any policy.
WinNet g_altBootFloorNet;
WinNet g_altBootWinNet;
bool altBootstrapEnabled() { return g_altBootFloorNet.ok && g_altBootWinNet.ok; }
bool nativeWinPolicyAvailable() { return g_nativeOoc && g_winNet.ok; }
bool nativeFloorPolicyAvailable() { return g_nativeOoc && !g_shopWin && g_floorNet.ok; }
bool nativeRestWinPolicy(GameContext &gc) {
    static const PathHistory emptyPath;
    return one_combat::nativeWinRestStep(gc, t_curPath ? *t_curPath : emptyPath,
                                        g_winNet, g_collectKeys);
}
void nativeUpgradeSelectWinPolicy(GameContext &gc) {
    static const PathHistory emptyPath;
    one_combat::nativeWinUpgradeSelectStep(gc, t_curPath ? *t_curPath : emptyPath,
                                           g_winNet);
}
void nativeShopVPolicy(GameContext &gc) {
    static const PathHistory emptyPath;
    one_combat::nativeFloorShopStep(gc, t_curPath ? *t_curPath : emptyPath,
                                    g_floorNet);
}
// The E2c module loads its native model only for the explicit parity-validation
// mode; ordinary gameplay and e2cgen do not load or invoke it.
bool   winNetOk() { return g_winNet.ok; }
static double winNetPredict(const std::vector<float> &raw) { return g_winNet.predict(raw); }

// Numeric rich features retain the CSV schema; text remains for dataset/server output.
std::vector<float> richFeatureVec(GameContext &gc) {
    static const PathHistory emptyPath;
    return one_combat::richFeatureVec(gc, t_curPath ? *t_curPath : emptyPath);
}

double nativeFloorValue(GameContext &gc) {
    static const PathHistory emptyPath;
    return g_floorNet.ok ? one_combat::nativeOocValue(gc,
        t_curPath ? *t_curPath : emptyPath, g_floorNet) : 0.0;
}

int nativeFloorCardPick(GameContext &gc, int rIdx) {
    static const PathHistory emptyPath;
    if (one_combat::inCardRewardFallback() && one_combat::nativeOocCardWinRankEnabled()) {
        one_combat::NativeCardWinRankTrace trace;
        const int pick = one_combat::nativeCardWinRankPick(gc,
            t_curPath ? *t_curPath : emptyPath, g_floorNet, g_winNet,
            rIdx, g_cardSkipThresh, g_nativeCardWinRankTrace ? &trace : nullptr);
        if (g_nativeCardWinRankTrace) {
            nlohmann::json offers = nlohmann::json::array();
            for (const auto &card : gc.info.rewardsContainer.cardRewards[rIdx])
                offers.push_back({{"card_id", static_cast<int>(card.getId())},
                                  {"upgraded", card.isUpgraded()}});
            const nlohmann::json row = {
                {"seed", gc.seed}, {"act", gc.act}, {"floor", gc.floorNum},
                {"reward_index", rIdx}, {"hp", gc.curHp}, {"deck_size", gc.deck.size()},
                {"offers", offers}, {"baseline_pick", trace.baselinePick},
                {"chosen_pick", pick}, {"public_futures", trace.scenarioCount},
                {"baseline_action", trace.baselinePick == 5 ? nlohmann::json("SKIP") : offers.at(trace.baselinePick)},
                {"chosen_action", pick == 5 ? nlohmann::json("SKIP") : offers.at(pick)},
                {"floor_base", trace.floorBase}, {"floor_marginals", trace.floorMarginals},
                {"win_evaluated", trace.winEvaluated},
                {"win_base", trace.winEvaluated ? nlohmann::json(trace.winBase) : nlohmann::json(nullptr)},
                {"win_marginals", trace.winMarginals}};
            static std::mutex traceMutex;
            std::lock_guard<std::mutex> lock(traceMutex);
            std::cout << "[card win rank] " << row.dump() << '\n';
        }
        return pick;
    }
    return one_combat::nativeFloorCardPick(gc, t_curPath ? *t_curPath : emptyPath,
                                          g_floorNet, rIdx, g_cardSkipThresh);
}

std::string nativeShopPlan(GameContext &gc) {
    static const PathHistory emptyPath;
    return one_combat::nativeShopPlan(gc, t_curPath ? *t_curPath : emptyPath,
                                      g_floorNet);
}

double vStateWinNative(GameContext &gc) {
    if (!g_winNet.ok) throw std::runtime_error("OOC MCTS requires native v_win");
    return vStateWinNativeFeatures(richFeatureVec(gc));
}

double vStateWinNativeFeatures(const std::vector<float> &raw) {
    if (!g_winNet.ok) throw std::runtime_error("OOC MCTS requires native v_win");
    const double value = g_winNet.predict(raw);
    if (!std::isfinite(value) || value < 0 || value > 1)
        throw std::runtime_error("OOC MCTS invalid native v_win value");
    return value;
}

double vStateWin(GameContext &gc) {
    static const PathHistory emptyPath;
    if (g_winNet.ok) return one_combat::nativeOocValue(gc,
        t_curPath ? *t_curPath : emptyPath, g_winNet);
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
std::vector<double> vQueryMarginals(GameContext &gc, int rIdx) {
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
int sampleCardSoftmax(const std::vector<double> &marg, double temp, double uniformEps,
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
        static const PathHistory emptyPath;
        return one_combat::nativeWinHealGain(gc, t_curPath ? *t_curPath : emptyPath,
                                            g_winNet, healAmt);
    }
    std::string req = "HW;" + std::to_string(healAmt) + ";" + vFeatCsv(gc) + "\n";
    std::string resp = vTransact(req);
    return resp.empty() ? 0.0 : std::atof(resp.c_str());
}

// Best upgrade by P(win): returns index into candIds and sets *gain to its win gain.
int vQueryUpgradeWin(GameContext &gc, const std::vector<int> &candIds, double *gain) {
    if (g_nativeOoc && g_winNet.ok) {
        static const PathHistory emptyPath;
        return one_combat::nativeWinUpgradePick(gc, t_curPath ? *t_curPath : emptyPath,
                                                g_winNet, candIds, gain);
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
        static const PathHistory emptyPath;
        return one_combat::nativeFloorRemovePick(gc, t_curPath ? *t_curPath : emptyPath,
                                                 g_floorNet, candIds);
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
        const search::GameAction action(search::GameAction::RewardsActionType::RELIC, j);
        const int price = search::isSupportedAutonomousOocAction(gc, action) ? sh.relicPrice(j) : -1;
        relicsCsv += std::to_string((int)sh.relics[j]) + ":" + std::to_string(price);
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
    if (t_oocContinuation) return false;  // branch continuations never consult oracles
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
    const bool restV = deployedRestV();
    std::cout << "BEST stack config: skip@" << g_cardSkipThresh
              << "  rest=" << (g_restWin ? "win-rate" : "default")
              << (restV ? "+legacy-rest-V" : "")
              << "  shop-V=ON  path=" << (g_pathV ? "model-driven" : "heuristic")
              << "  shop-beam=" << (g_oocShopBeam ? "ON" : "off")
              << "  native-OOC=" << (g_nativeOoc ? "ON" : "OFF")
              << "  keys=" << (g_collectKeys ? "collect" : "skip")
              << "  searcher=" << "Silver"
              << "  fair-play"
              << "  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  asc " << asc << "  sims " << sims << "  threads " << numThreads() << "\n";
    std::cout << "BEST models: floor=" << (g_floorNet.ok ? g_floorNet.path : "MISSING")
              << "  win=" << (g_winNet.ok ? g_winNet.path : "not loaded")
              << "\n";
    // Optional per-seed output powers the adaptive self-play gate. Rows are
    // flushed as runs finish, so the dashboard gets live progress and a killed
    // benchmark leaves valid results. The caller owns truncation; batches append.
    std::ofstream results;
    if (!resultsFile.empty()) {
        results.open(resultsFile, std::ios::app);
        if (!results) {
            // An unwritable path used to drop every row and exit 0.
            std::cerr << "bestbench: cannot open results file " << resultsFile << " for append\n";
            return false;
        }
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
        meta.fairPlay = true;
        // Native Silver is the only combat backend (ADR-0022); the vendored-era
        // keys keep their schema with the native values.
        meta.silverSearchEnabled = search::nativeSilverBackendInstalled();
        meta.stsSilverSearchEffective = meta.silverSearchEnabled;
        meta.effectiveCombatBackend = "native_silver";
        meta.silverReuseCapMode = "allocated";
        meta.silverReuseCap = search::nativeSilverReuseCap();
        meta.silverUpstreamSha = "";
        meta.executableGitSha = trainingExecutableGitSha();
        meta.silverScalingDiagnosticFile = "";
        meta.silverStickyQualityFile = "";
        meta.silverAdaptiveEnabled = search::nativeSilverAdaptiveEnabled();
        meta.silverAdaptiveRetainedOnly = meta.silverAdaptiveEnabled;
        meta.silverAdaptiveTopShare = meta.silverAdaptiveEnabled ? search::nativeSilverAdaptiveTopGap() : 0.0;
        meta.silverExactRootBudgets = search::nativeSilverExactRootBudgets();
        meta.silverExactVisitLock = false;
        meta.silverRhoRacing = false;
        if (search::nativeSilverLearnedStopEnabled()) {
            meta.silverLearnedStopModel = search::nativeSilverStopModelId();
            meta.silverLearnedStopThreshold = search::nativeSilverLearnedStopThreshold();
            meta.silverLearnedStopBossFallback = search::nativeSilverLearnedStopBossFallback();
            meta.silverLearnedStopBossMax = search::nativeSilverLearnedStopBossMax();
        }
        if (!search::nativeSilverRootPriorPath().empty()) {
            meta.silverRootPrior = search::nativeSilverRootPriorPath();
            meta.silverRootPriorSha256 = fileSha256(meta.silverRootPrior);
            meta.silverRootPriorWeight = search::nativeSilverRootPriorWeight();
            meta.silverTreePriorMinVisits = search::nativeSilverTreePriorMinVisits();
        }
        if (g_oocStrategicTokNet.ok) {
            meta.oocStrategicTokNet = g_oocStrategicTokNet.path;
            meta.oocStrategicTokNetSha256 = fileSha256(meta.oocStrategicTokNet);
            meta.oocStrategicTokConstGuard = g_oocStrategicTokNet.constGuard;
        }
        if (one_combat::oocGbmRankerEnabled()) {
            meta.oocGbmRanker = std::getenv("STS_OOC_GBM_RANKER");
            meta.oocGbmRankerSha256 = fileSha256(meta.oocGbmRanker);
        }
        meta.oocMcts = one_combat::liveOocMctsEnabled();
        meta.heart1WingBootsCounter = one_combat::heart1::wingBootsCounter() ? 1 : 0;
        meta.stopAfterAct = g_stopAfterAct;
        if (g_forceRelic != RelicId::INVALID)
            meta.forceRelic = relicEnumNames[static_cast<int>(g_forceRelic)];
        meta.oocPolicy = effectiveOocPolicySpecification().dump();
        meta.floorModel = g_floorNet.ok ? g_floorNet.path : "MISSING";
        meta.winModel = g_winNet.ok ? g_winNet.path : "not loaded";
        meta.combatVNet = "off";
        meta.policyNet = "off";
        meta.pvNet = "off";
        meta.distVNet = "off";
        std::ofstream sidecar(resultsFile + ".meta.json", std::ios::app);
        if (!sidecar) std::cerr << "[bestbench] warning: cannot open " << resultsFile << ".meta.json\n";
        else sidecar << sts::benchConfigSidecarLine(meta) << '\n';
    }
    int wins = 0, completed = 0; long long floor = 0, hp = 0; double sec = 0;
    std::vector<std::pair<std::uint64_t, std::string>> failures;
    // A seed whose combat aborts (CombatAbort: the backend threw search::CombatStateFailure at a stall, a
    // knowledge-tracker inconsistency, a root conversion or an invalid action) is a completed LOSS row at the floor of the abort with
    // deathEncounter=kDeathEncounterCombatAbort, not a missing row: a missing row would drop the seed from the
    // paired analysis of both arms, biasing the comparison toward the arm that aborts (benchmark protocol:
    // "an unresolved battle is a loss, not a victory"). The abort is still reported on stderr and counted here. Any other exception (a configuration or
    // I/O error, e.g. a missing model) is a seed failure: no row, [bestbench-seed-failure], exit 1.
    std::vector<std::tuple<std::uint64_t, int, std::string>> aborts;
    BenchProgress prog(nSeeds, "BEST");
    auto wall0 = std::chrono::steady_clock::now();
    const auto writeRow = [&](std::uint64_t seed, const RunResult &r) {
        #pragma omp critical(bestbench_results)
        if (results.is_open()) {
            results << seed << ',' << (r.won ? 1 : 0) << ',' << r.floor << ','
                    << r.act << ',' << r.hpEnd << ',' << r.maxHp << ','
                    << r.fightsLost << ',' << r.deathCombat << ',' << r.deathEncounter << ',' << r.sec << '\n';
            results.flush();
        }
    };
    // Do not create a one-iteration outer OpenMP team when the all-OOC oracle
    // is asked to parallelize its branches; that would otherwise serialize the
    // nested region. Multi-seed benches keep the proven outer parallelism.
    if (nSeeds == 1 && g_actFightProbeParallelBranches) {
        const std::uint64_t seed = seedOffset;
        try {
            RunResult r = runFullRunOOC(seed, sims, asc, restV, true);
            wins += r.won; floor += r.floor; hp += r.hpEnd; sec += r.sec; ++completed;
            writeRow(seed, r);
            prog.tick(r.won, r.floor, r.hpEnd);
        } catch (const CombatAbort &e) {
            const RunResult &r = e.partial;
            floor += r.floor; hp += r.hpEnd; sec += r.sec; ++completed;
            writeRow(seed, r);
            aborts.emplace_back(seed, r.floor, e.what());
            prog.tick(false, r.floor, r.hpEnd);
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
                writeRow(seed, r);
                prog.tick(r.won, r.floor, r.hpEnd);
            } catch (const CombatAbort &e) {
                const RunResult &r = e.partial;
                floor += r.floor; hp += r.hpEnd; sec += r.sec; ++completed;
                writeRow(seed, r);
                #pragma omp critical(bestbench_failures)
                aborts.emplace_back(seed, r.floor, e.what());
                prog.tick(false, r.floor, r.hpEnd);
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
    if (!aborts.empty()) {
        std::sort(aborts.begin(), aborts.end());
        for (const auto &[seed, abortFloor, message] : aborts) {
            std::cerr << "[bestbench-combat-abort] seed=" << seed << " floor=" << abortFloor
                      << " recorded as loss (deathEncounter=" << kDeathEncounterCombatAbort << ") error=" << message << '\n';
        }
        std::cerr << "bestbench: " << aborts.size() << " combat abort(s) recorded as loss rows\n";
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
    const TokState ts = buildTokStatePure(gc, path);
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






struct PredictedCheckpointFight {
    double winProbability = 0.0;
    int endHpIfWin = 1;
    int maxHp = 1;
    bool predictedWin = false;
};

static PredictedCheckpointFight predictCheckpointFight(const GameContext &gc,
                                                        MonsterEncounter encounter);

// Remaining non-minion monster HP at combat end (terminal loss labels).
static void nonMinionMonsterHpTotals(const BattleContext &bc, int &curHpTotal, int &maxHpTotal) {
    curHpTotal = 0; maxHpTotal = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (!m.hasStatus<MS::MINION>() && m.id != sts::MonsterId::INVALID) {
            curHpTotal += m.curHp;
            maxHpTotal += m.maxHp;
        }
    }
}

// Shared V1 labels: persistent pre-init features and terminal pre-exit outcome.
// Ambiguous Awakened One deaths retain V1's validity mask; loss-severity
// consumers must exclude progressAmbiguous, as the existing trainer does.
const char *combatEvalLabelHeader() {
    return "won,trueDeath,escaped,turnCapLoss,progressAmbiguous,labelValid,terminalCombatHp,terminalCombatMaxHp,terminalNonMinionCurHp,terminalNonMinionMaxHp,winHpFrac,lossRemainingFrac,signedOutcome,quarantineReason";
}
bool combatEvalEncounterValid(MonsterEncounter encounter) {
    const int index = static_cast<int>(encounter);
    return index >= 0 && index < static_cast<int>(sizeof(monsterEncounterStrings) / sizeof(monsterEncounterStrings[0]));
}
const char *combatEvalRoomClass(Room room) {
    return room == Room::MONSTER ? "NORMAL" : room == Room::ELITE ? "ELITE" : room == Room::BOSS ? "BOSS" : "OTHER";
}
CombatEvalLabel combatEvalTerminal(const BattleContext &bc, MonsterEncounter encounter,
                                         int hooks, int healthBefore, int healthAfter,
                                         bool allowInitializationTerminal) {
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
    int enemyCurHp = 0, enemyMaxHp = 0;
    nonMinionMonsterHpTotals(bc, enemyCurHp, enemyMaxHp);
    double enemyRatio = (enemyCurHp == 0 || enemyMaxHp == 0) ? 0 : (double)enemyCurHp / enemyMaxHp;
    double lossRemainingFrac = std::max(eps, std::min(1.0, enemyRatio));
    double signedOutcome = labelValid ? (won ? winHpFrac : -lossRemainingFrac) : 0.0;
    const char *reason = !representableEncounter ? "unknown_encounter" : !hasFirstDecisionBoundary ? "missing_first_decision_hook" : !healthOk ? "simulator_health_failure" : escaped ? "escape" : turnCapLoss ? "turn_cap" : (decided && !trueDeath && !won) ? "non_death_loss" : "";
    return {decided, healthOk, escaped, trueDeath, won, turnCapLoss, progressAmbiguous, labelValid,
            terminalHp, terminalMaxHp, winHpFrac, lossRemainingFrac, signedOutcome, enemyCurHp, enemyMaxHp, reason};
}

// Continue a copied run after any out-of-combat counterfactual action. Every
// branch in one decision uses the same agent seed and copied GameContext RNG
// state (common random numbers).  maxFights < 0 means finish the whole run.  A
// bounded branch resolves rewards/path choices after its last fight, stops at
// the next battle, then bootstraps expected final floor and P(win).
OocCounterfactualResult
finishOocCounterfactual(GameContext gc, int sims, std::uint64_t agentSeed,
                        PathHistory path, int maxFights, bool bootstrap,
                        FutureFightProbe *probe, int stopAfterAct,
                        const std::vector<int> *fightSimsSeq,
                        bool usePredict,
                        const OocPrefixObserver *prefixObserver,
                        OocContinuationCost *finalCost,
                        bool useFrozenV4,
                        std::vector<CombatEvalFight> *combatCapture,
                        const OocFightEndObserver *fightEndObserver) {
    const int healthBefore = search::g_simHealthFailureCount;
    const auto continuationWallStart = std::chrono::steady_clock::now();
    const std::clock_t continuationCpuStart = std::clock();
    OocContinuationCost continuationCost;
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.simulationCountTotal = 0;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    struct ContinuationScope {
        bool saved = t_oocContinuation;
        ContinuationScope() { t_oocContinuation = true; }
        ~ContinuationScope() { t_oocContinuation = saved; }
    } continuationScope;
    (void)useFrozenV4;
    int fights = 0;
    int observedFights = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
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
                continuationCost.combatDecisions += static_cast<std::uint64_t>(
                    search::g_nativeSilverCombatStats.decisions);
                passed = bc.outcome == Outcome::PLAYER_VICTORY;
                endHp = passed ? gc.curHp : 0;
                endMaxHp = gc.maxHp;
                bc.exitBattle(gc);
                if (fightEndObserver)
                    (*fightEndObserver)(gc, OocFightEnd{fights, battleAct, gc.floorNum, room, bc.encounter, passed});
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
        } else {
            // The deployed OOC step (§431); useFrozenV4 selects the same step.
            if (gc.screenState == ScreenState::REST_ROOM
                && search::GameAction::getAllActionsInState(gc).empty()) break;
            if (!(t_counterfactualHeart1 && one_combat::heart1::policyStep(gc)))
                deployedOocPolicyStep(gc, agent);
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
    double altWon = won, altFloor = floor;
    if (bootstrap && gc.outcome == GameOutcome::UNDECIDED) {
        const double vf = vStateRaw(gc);
        const double vw = vStateWin(gc);
        if (std::isfinite(vf) && vf >= gc.floorNum && vf <= 60) floor = vf;
        if (std::isfinite(vw) && vw >= 0 && vw <= 1) won = vw;
        bootstrapped = 1;
        if (altBootstrapEnabled()) {
            const double af = one_combat::nativeOocValue(gc, path, g_altBootFloorNet);
            const double aw = one_combat::nativeOocValue(gc, path, g_altBootWinNet);
            altFloor = (std::isfinite(af) && af >= gc.floorNum && af <= 60) ? af : gc.floorNum;
            altWon = (std::isfinite(aw) && aw >= 0 && aw <= 1) ? aw : 0.0;
        }
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
            valid && survivedH, valid ? altWon : 0.0, valid ? altFloor : 0.0};
}

// GameContext normally shares its Map through a shared_ptr. A counterfactual may
// reach the next act and regenerate that map; detach it so speculative branches
// cannot overwrite the live run's current-act map.
GameContext detachedCounterfactualCopy(const GameContext &gc) {
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
void resampleRemainingActEncounters(GameContext &gc, std::uint64_t branchSeed) {
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
    if (t_oocContinuation) return false;  // branch continuations never consult oracles
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


// Conditional enemy pools at a concrete combat checkpoint. Normal and elite
// entries retain the game's no-repeat constraints; event fights are fixed by
// their event option. This gives a probability distribution without a hand-made
// difficulty tier.
std::vector<EncounterOption> possibleEncounterOptions(const GameContext &gc) {
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

// Test seam: replaces the encounter-NN server round trip (self-tests only).
static thread_local std::function<std::string(const std::string &)> t_oocEncounterTransactForTest;

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
    std::istringstream in(t_oocEncounterTransactForTest ? t_oocEncounterTransactForTest(req.str())
                                                        : vTransact(req.str()));
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
                    local.info.encounter = options[i].encounter;
                    BattleContext bc{};
                    fightAgent.playoutBattle(local, bc); bc.exitBattle(local);
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
                BattleContext actual{}; trunkAgent.playoutBattle(gc, actual); actual.exitBattle(gc);
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
            if (search::heartRecallRequired(gc, g_collectKeys)) {
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

std::string csvQuote(const std::string &s) {
    std::string out = "\"";
    for (const char c : s) {
        if (c == '\"') out += "\"\"";
        else out += c;
    }
    return out + "\"";
}

std::string actionDescription(const search::GameAction &action, const GameContext &gc) {
    std::ostringstream out;
    action.printDesc(out, gc);
    // A few event actions have no human-readable printer; retain their stable
    // encoded action bits rather than silently logging an empty legal action.
    return out.str().empty() ? "bits=" + std::to_string(action.bits) : out.str();
}

std::string joinLegalActions(const std::vector<search::GameAction> &actions,
                                    const GameContext &gc) {
    std::ostringstream out;
    for (int i = 0; i < (int)actions.size(); ++i) {
        if (i) out << " | ";
        out << i << ':' << actionDescription(actions[i], gc);
    }
    return out.str();
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
    // A Match and Keep valuation is not a decision the run faces: no teacher row.
    if (!g_actFightProbeLog.is_open() || t_oocHypotheticalStep) return;
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
    if (t_oocContinuation) return false;  // branch continuations never consult oracles
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
    // The root state is the live decision state with the live path. Compute it
    // once: each serial branch clears t_curPath on return, and OpenMP workers
    // start with their own null t_curPath.
    const std::string rootState = vFeatCsv(gc);

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
            rootState, actions[a].bits, (int)gc.screenState, gc.act,
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

// Every branch of one all-OOC oracle decision must send the encounter NN the
// same root state, built with the live path (audit 2026-10-11 finding 6: all
// branches after the first used an empty path, so pv* were 0).
// Match and Keep values a card by running the real policy on a detached lone
// card offer. A combat-playing draft oracle must be able to fight there instead
// of aborting the run (audit 2026-10-11 finding 5).
static int matchAndKeepOracleSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("Match and Keep oracle selftest: " + message);
    };
    struct Guard {
        int bossDraft = g_bossDraft, rows = g_bossDraftRows, n = g_bossDraftN, sims = g_bossDraftSims,
            futures = g_bossDraftFutures;
        const PathHistory *path = t_curPath;
        OocPolicyThreadState policy = one_combat::captureOocPolicyThreadState();
        bool disallowed = search::g_disallowImaginedCombat;
        ~Guard() {
            g_bossDraft = bossDraft; g_bossDraftRows = rows; g_bossDraftN = n; g_bossDraftSims = sims;
            g_bossDraftFutures = futures; t_curPath = path; one_combat::restoreOocPolicyThreadState(policy);
            search::g_disallowImaginedCombat = disallowed;
        }
    } guard;
    one_combat::restoreOocPolicyThreadState(OocPolicyThreadState{});
    g_bossDraft = 1; g_bossDraftRows = 99; g_bossDraftN = 1; g_bossDraftSims = 2; g_bossDraftFutures = 1;

    GameContext gc(CharacterClass::IRONCLAD, 74007001, 0);
    for (int i = 0; i < 16 && gc.screenState != ScreenState::MAP_SCREEN; ++i) {
        const auto actions = search::GameAction::getAllActionsInState(gc);
        require(!actions.empty(), "fixture reaches the first map screen");
        actions.front().execute(gc);
    }
    require(gc.screenState == ScreenState::MAP_SCREEN, "fixture is at the map");
    gc.curRoom = Room::EVENT; gc.curEvent = Event::MATCH_AND_KEEP;
    gc.screenState = ScreenState::EVENT_SCREEN;
    gc.info.eventData = 5;
    gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    gc.info.toSelectCards.clear();
    for (int i = 0; i < 12; ++i)
        gc.info.toSelectCards.push_back({Card(i < 2 ? CardId::FIEND_FIRE : CardId::BASH),
            i < 4 ? GameContext::MATCH_AND_KEEP_SEEN : GameContext::MATCH_AND_KEEP_UNSEEN});
    PathHistory path;
    t_curPath = &path;
    search::ScumSearchAgent2 agent;
    try {
        runFullRunOocPolicyStep(gc, agent, false, false);
    } catch (const std::exception &error) {
        require(false, std::string("boss-draft valuation threw: ") + error.what());
    }
    int faceUp = 0;
    for (const auto &slot : gc.info.toSelectCards) faceUp += slot.deckIdx == GameContext::MATCH_AND_KEEP_FACE_UP;
    require(faceUp == 1, "the policy turned exactly one card");
    require(t_curPath == &path && !search::g_disallowImaginedCombat, "valuation restores path and combat permission");
    std::cout << "Match and Keep oracle selftest: PASS\n";
    return 0;
}

// STS_MATCH_AND_KEEP_CURSE_FIX: a seen curse pair is never valued (no cache
// entry) and never flipped; =0 values it like any card, as before 2026-10-17.
static int matchAndKeepCurseSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("Match and Keep curse selftest: " + message);
    };
    struct Guard {
        const PathHistory *path = t_curPath;
        OocPolicyThreadState policy = one_combat::captureOocPolicyThreadState();
        std::optional<std::string> fix = [] {
            const char *v = std::getenv("STS_MATCH_AND_KEEP_CURSE_FIX");
            return v ? std::optional<std::string>(v) : std::nullopt;
        }();
        ~Guard() {
            t_curPath = path; one_combat::restoreOocPolicyThreadState(policy);
            if (fix) setenv("STS_MATCH_AND_KEEP_CURSE_FIX", fix->c_str(), 1);
            else unsetenv("STS_MATCH_AND_KEEP_CURSE_FIX");
        }
    } guard;
    GameContext base(CharacterClass::IRONCLAD, 74007001, 0);
    for (int i = 0; i < 16 && base.screenState != ScreenState::MAP_SCREEN; ++i) {
        const auto actions = search::GameAction::getAllActionsInState(base);
        require(!actions.empty(), "fixture reaches the first map screen");
        actions.front().execute(base);
    }
    require(base.screenState == ScreenState::MAP_SCREEN, "fixture is at the map");
    base.curRoom = Room::EVENT; base.curEvent = Event::MATCH_AND_KEEP;
    base.screenState = ScreenState::EVENT_SCREEN;
    base.info.eventData = 5;
    base.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    base.info.toSelectCards.clear();
    for (int i = 0; i < 12; ++i)
        base.info.toSelectCards.push_back({Card(i < 2 ? CardId::SHAME : CardId::BASH),
            i < 2 ? GameContext::MATCH_AND_KEEP_SEEN : GameContext::MATCH_AND_KEEP_UNSEEN});
    const auto shame = std::make_pair(static_cast<int>(CardId::SHAME), false);
    PathHistory path;
    search::ScumSearchAgent2 agent;
    const auto click = [&](const char *fix) {
        setenv("STS_MATCH_AND_KEEP_CURSE_FIX", fix, 1);
        one_combat::restoreOocPolicyThreadState(OocPolicyThreadState{});
        t_curPath = &path;
        GameContext gc = base;
        runFullRunOocPolicyStep(gc, agent, false, false);
        int faceUp = -1;
        for (int i = 0; i < 12; ++i)
            if (gc.info.toSelectCards[i].deckIdx == GameContext::MATCH_AND_KEEP_FACE_UP) faceUp = i;
        return std::make_pair(faceUp, one_combat::captureOocPolicyThreadState().matchAndKeepWant.want.count(shame));
    };
    const auto fixed = click("1");
    require(fixed.first == 2 && fixed.second == 0, "fix: the curse pair is skipped without a valuation");
    require(click("0").second == 1, "=0: the curse pair is valued like any card");
    bool threw = false;
    try { click("2"); } catch (const std::runtime_error &) { threw = true; }
    require(threw, "an invalid switch value is fatal");
    std::cout << "Match and Keep curse selftest: PASS\n";
    return 0;
}

static int actFightProbeRootStateSelfTest() {
    auto require = [](bool ok, const std::string &message) {
        if (!ok) throw std::runtime_error("act-fight root-state selftest: " + message);
    };
    struct Guard {
        bool allOoc = g_actFightProbeAllOoc, nn = g_actFightProbeEncounterNN,
             predict = g_actFightProbePredict, trace = g_actFightProbeTrace,
             parallel = g_actFightProbeParallelBranches;
        int futures = g_actFightProbeFutures, checkpoints = g_actFightProbeMaxCheckpoints,
            decision = t_actFightProbeDecisionIdx;
        double margin = g_actFightProbeMargin, termWin = g_actFightProbeTermWin;
        const PathHistory *path = t_curPath;
        bool hypothetical = t_oocHypotheticalStep;
        ~Guard() {
            g_actFightProbeAllOoc = allOoc; g_actFightProbeEncounterNN = nn;
            g_actFightProbePredict = predict; g_actFightProbeTrace = trace;
            g_actFightProbeParallelBranches = parallel; g_actFightProbeFutures = futures;
            g_actFightProbeMaxCheckpoints = checkpoints; t_actFightProbeDecisionIdx = decision;
            g_actFightProbeMargin = margin; g_actFightProbeTermWin = termWin;
            t_curPath = path; t_oocEncounterTransactForTest = nullptr;
            t_oocHypotheticalStep = hypothetical;
            if (g_actFightProbeLog.is_open()) g_actFightProbeLog.close();
        }
    } guard;
    g_actFightProbeAllOoc = true; g_actFightProbeEncounterNN = true;
    g_actFightProbePredict = false; g_actFightProbeTrace = false;
    g_actFightProbeParallelBranches = false;
    g_actFightProbeFutures = 2; g_actFightProbeMaxCheckpoints = 1;
    g_actFightProbeMargin = 0.0; g_actFightProbeTermWin = 0.0;

    GameContext gc(CharacterClass::IRONCLAD, 74007000, 0);
    for (int i = 0; i < 16 && gc.screenState != ScreenState::MAP_SCREEN; ++i) {
        const auto actions = search::GameAction::getAllActionsInState(gc);
        require(!actions.empty(), "fixture reaches the first map screen");
        actions.front().execute(gc);
    }
    require(gc.screenState == ScreenState::MAP_SCREEN && gc.act == 1, "fixture is an Act 1 map decision");
    PathHistory path;
    path.roomVisits = {2, 1, 1, 0, 1, 0, 0, 0, 0, 0};
    path.lastNodeKey = 7;
    t_curPath = &path;
    const std::string expected = richRow(gc, path);
    require(expected != richRow(gc, PathHistory{}), "fixture path is visible in the root state");

    // Every first checkpoint is answered by the stub, so no combat is played.
    std::vector<std::string> roots;
    t_oocEncounterTransactForTest = [&](const std::string &req) {
        std::size_t pos = 0;
        for (int field = 0; field < 5; ++field) pos = req.find(';', pos) + 1;
        std::string root = req.substr(pos);
        if (!root.empty() && root.back() == '\n') root.pop_back();
        roots.push_back(root);
        std::string response;
        for (int i = 0; i < 16; ++i) response += "1.0,0.9 ";
        return response + "\n";
    };
    // Teacher log: a hypothetical (Match and Keep) decision writes no rows; a real one does.
    const std::string logPath = (std::filesystem::temp_directory_path()
                                 / ("act_fight_probe_root_state_" + std::to_string(getpid()) + ".csv")).string();
    std::remove(logPath.c_str());
    g_actFightProbeLog.open(logPath);
    require(g_actFightProbeLog.is_open(), "selftest teacher log opens");
    {
        GameContext hypothetical = detachedCounterfactualCopy(gc);
        t_oocHypotheticalStep = true;
        const bool decided = actFightProbeAllOocPolicy(hypothetical);
        t_oocHypotheticalStep = false;
        require(decided, "oracle decides the hypothetical map choice");
        g_actFightProbeLog.flush();
        require(std::ifstream(logPath).peek() == std::ifstream::traits_type::eof(),
                "hypothetical decision writes no teacher-log rows");
    }
    roots.clear();
    int legal = 0;
    for (const auto &action : search::GameAction::getAllActionsInState(gc)) legal += action.isValidAction(gc);
    require(legal >= 2, "fixture offers at least two map actions");
    require(actFightProbeAllOocPolicy(gc), "oracle decides the map choice");
    require((int)roots.size() == 2 * legal, "every branch queried the encounter NN once");
    for (std::size_t i = 0; i < roots.size(); ++i)
        require(roots[i] == expected, "branch " + std::to_string(i) + " root state lost the live path");
    require(t_curPath == &path, "oracle restores the live path");
    g_actFightProbeLog.close();
    std::string row;
    int logRows = 0;
    for (std::ifstream log(logPath); std::getline(log, row);) ++logRows;
    std::remove(logPath.c_str());
    require(logRows == legal, "real decision writes one teacher-log row per legal action");
    std::cout << "act-fight root-state selftest: PASS (" << roots.size() << " branches)\n";
    return 0;
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

std::string strategicHeader() {
    return "seed,decIdx,screen,action,actionType,c1,c2,c3,cand1,cand2,cand3,chosen,"
         + strategicStateCols() + ",won,endFloor,endHp\n";
}

StratFingerprint stratFingerprint(const GameContext &gc) {
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
            auto legal = search::GameAction::getAllActionsInState(node.state);
            legal.erase(std::remove_if(legal.begin(), legal.end(), [&](const auto &action) {
                return !search::isSupportedAutonomousOocAction(node.state, action);
            }), legal.end());
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
// The STS_SILVER_* options the native Silver backend honors, with the values it
// accepts (empty: any value). The vendored model's other options, and its
// STS_COMBAT_* diagnostics, were removed with it (ADR-0022); frozen research
// environments may still pin the neutral values listed here.
static std::string unsupportedSilverOption() {
    struct Supported { const char *name; const char *value; };
    static const Supported kSupported[] = {
        {"STS_SILVER_SEARCH", ""}, {"STS_SILVER_ADAPTIVE", ""},
        {"STS_SILVER_ADAPTIVE_TOP_GAP", ""}, {"STS_SILVER_ADAPTIVE_RETAINED_ONLY", "1"},
        {"STS_SILVER_EXACT_ROOT_BUDGETS", ""}, {"STS_SILVER_SEARCH_SINGLETON_ROOTS", ""},
        {"STS_SILVER_REUSE_CAP_MODE", "allocated"}, {"STS_SILVER_NODE_REUSE_CAP", ""}, {"STS_SILVER_ACT4_STRONG", ""},
        {"STS_SILVER_VNET_LEAF_DIRECT", "0"}, {"STS_SILVER_TELEMETRY", "0"},
        {"STS_SILVER_USELESS_TRACE", ""}, {"STS_SILVER_PUBLIC_TRACE", ""}, {"STS_SILVER_PUBLIC_TARGET", ""}, {"STS_SILVER_TREE_PROFILE", ""}, {"STS_SILVER_TREE_PROFILE_SCOPE", ""}, {"STS_SILVER_DEBUG_TREE", ""}, {"STS_SILVER_DEBUG_TREE_NODE_CAP", ""},
        {"STS_SILVER_LEARNED_STOP", ""}, {"STS_SILVER_LEARNED_STOP_THRESHOLD", ""},
        {"STS_SILVER_LEARNED_STOP_BOSS_FALLBACK", ""}, {"STS_SILVER_LEARNED_STOP_BOSS_MAX", ""}, {"STS_SILVER_LEARNED_STOP_MODEL", ""}, {"STS_SILVER_STOP_TRACE", ""},
        {"STS_SILVER_FINAL_BOSS_BINARY", ""}, {"STS_SILVER_FINAL_FIGHT_LEAF", ""}, {"STS_SILVER_NO_LOSS_POTION_CREDIT", ""}, {"STS_SILVER_RELIC_HEAL_LEAF", ""}, {"STS_SILVER_A20_BOSS_HEAL_FIX", ""}, {"STS_SILVER_LOOP_GUARD", ""}, {"STS_SILVER_ESCAPE_PENALTY", ""}, {"STS_SILVER_POTION_WEIGHTS", ""}, {"STS_SILVER_CONCAVE_HP_LEAF", ""}, {"STS_SILVER_GOLD_WEIGHT", ""}, {"STS_SILVER_MAXHP_WEIGHT", ""}, {"STS_SILVER_VICTORY_TURN_PENALTY", ""}, {"STS_SILVER_LOSS_CEILING", ""}, {"STS_SILVER_INCENSE_HEART_PHASE", ""}, {"STS_SILVER_PRICE_TABLE_LEAF", ""},
        {"STS_SILVER_ROOT_PRIOR", ""}, {"STS_SILVER_ROOT_PRIOR_WEIGHT", ""}, {"STS_SILVER_ROOT_PRIOR_SCOPE", ""}, {"STS_SILVER_TREE_PRIOR_MIN_VISITS", ""},
        {"STS_SILVER_ROLLOUT_UNIFORM", ""}, {"STS_SILVER_ROLLOUTS_PER_LEAF", ""}, {"STS_SILVER_ROLLOUT_CARD_TABLE", ""}, {"STS_SILVER_ROLLOUT_ZERO_COST_CAP", ""}, {"STS_SILVER_ROLLOUT_ACTION_CAP", ""},
        {"STS_SILVER_ROLLOUT_ROOT_TABLE", ""}, {"STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE", ""}, {"STS_SILVER_PRIOR_PLAYOUT_ELITE", ""},
        {"STS_SILVER_LEAF_HEAD", ""}, {"STS_SILVER_LEAF_HEAD_TRUNK", ""}, {"STS_SILVER_LEAF_HEAD_BLEND", ""},
        {"STS_SILVER_LEAF_HEAD_TURN_PENALTY", ""}, {"STS_SILVER_LEAF_HEAD_WIN_CAP", ""},
        {"STS_SILVER_MAX_BACKUP", ""}, {"STS_SILVER_RISK_VETO", ""},
    };
    // Vendored-only diagnostics without the STS_SILVER_ prefix.
    static const char *const kRemoved[] = {
        "STS_COMBAT_BUDGET_DIAG_FILE", "STS_COMBAT_SEQUENTIAL_DIAG_FILE",
        "STS_COMBAT_SEQUENTIAL_DIAG_CHECKPOINTS",
    };
    for (const char *name : kRemoved) {
        if (const char *value = std::getenv(name); value && *value) return std::string(name) + "=" + value;
    }
    for (char **env = environ; env && *env; ++env) {
        const std::string entry(*env);
        if (entry.rfind("STS_SILVER_", 0) != 0) continue;
        const auto eq = entry.find('=');
        const std::string name = entry.substr(0, eq);
        const std::string value = eq == std::string::npos ? "" : entry.substr(eq + 1);
        if (value.empty()) continue;
        bool supported = false;
        for (const auto &option : kSupported) {
            supported = supported || (name == option.name && (!*option.value || value == option.value));
        }
        if (!supported) return name + "=" + value;
    }
    return {};
}

// Default-on switches accept only 0 or 1 when set: atoi would read a typo,
// "true" or an empty value as 0 and silently turn the switch off.
static bool envSwitch(const char *name, bool fallback) {
    const char *value = std::getenv(name);
    if (!value) return fallback;
    if (std::strcmp(value, "1") == 0) return true;
    if (std::strcmp(value, "0") == 0) return false;
    std::cerr << "error: " << name << " must be 0 or 1 when set\n";
    std::exit(2);
}

int main(int argc, char **argv) {
    g_mainBinaryPath = argc > 0 ? argv[0] : "one_combat";
    g_mainArgv.clear();
    for (int i = 1; i < argc; ++i) g_mainArgv.emplace_back(argv[i]);
    std::string mode = argc > 1 ? argv[1] : "";

    if (mode == "differentialreplay")
        return one_combat::runDifferentialReplayNative(std::cin, std::cout);
    // ADR-0020: Silver is the only combat searcher. The native searchers and
    // their known-RNG regime were removed, so a request for them fails.
    if (const char *d = std::getenv("STS_SILVER_SEARCH"); d && std::atoi(d) == 0) {
        std::cerr << "error: STS_SILVER_SEARCH=0 is no longer supported; "
                     "Silver is the only combat searcher (ADR-0020)\n";
        return 2;
    }
    if (const char *d = std::getenv("STS_FAIR"); d && std::atoi(d) == 0) {
        std::cerr << "error: STS_FAIR=0 is no longer supported; "
                     "the known-RNG regime was removed (ADR-0020)\n";
        return 2;
    }
    setenv("STS_SILVER_SEARCH", "1", 0);
    setenv("STS_FAIR", "1", 0);
    // Budgeted Silver policies ignore the caller's budget. Whole-run modes
    // called without a sims argument use one by default: learned stopping
    // (ADR-0026, replacing the #199 adaptive default of ADR-0018). At A20 the
    // whole-run modes use it with a sims argument too (ADR-0051); the argument
    // then no longer sets the budget, and STS_SILVER_LEARNED_STOP=0 restores
    // flat Silver at it. Every other call searches the flat caller budget
    // unless a policy is configured.
    {
        const bool wholeRunMode = mode == "run" || mode == "bestbench" || mode == "reprobench";
        // All three modes take the ascension as argv[4], default 20.
        const bool a20WholeRun = wholeRunMode && (argc > 4 ? std::atoi(argv[4]) : 20) == 20;
        // expertreplay plays one A20 whole run per process (no sims argument).
        const bool wholeRunDefault = (wholeRunMode && argc <= 2) || a20WholeRun || mode == "expertreplay"
            || mode == "expertfights";
        const bool adaptiveConfigured = std::getenv("STS_SILVER_ADAPTIVE")
            || std::getenv("STS_SILVER_ADAPTIVE_RETAINED_ONLY")
            || std::getenv("STS_SILVER_ADAPTIVE_TOP_GAP");
        const char *learned = std::getenv("STS_SILVER_LEARNED_STOP");
        const bool learnedRequested = learned && std::atoi(learned) != 0;
        if (wholeRunDefault && !adaptiveConfigured && !learned && !std::getenv("STS_SILVER_STOP_TRACE")) {
            setenv("STS_SILVER_LEARNED_STOP", "1", 0);
            setenv("STS_SILVER_ADAPTIVE", "0", 0);
            if (a20WholeRun && argc > 2)
                std::cout << "[A20 default: Silver learned stopping, sims argument " << argv[2]
                          << " not used as budget; STS_SILVER_LEARNED_STOP=0 restores flat Silver]" << std::endl;
        } else if (learnedRequested || ((!wholeRunDefault || (a20WholeRun && argc > 2)) && !adaptiveConfigured)) {
            // At A20 with a sims argument, STS_SILVER_LEARNED_STOP=0 is flat Silver at it, as before ADR-0051.
            setenv("STS_SILVER_ADAPTIVE", "0", 0);
        }
    }

    if (const char *d = std::getenv("VPORT")) g_vPort = std::atoi(d);

    // Action.cpp reads this switch lazily, mid-run; check it here so a bad
    // value stops the run at startup instead of failing inside a search.
    envSwitch("STS_MULTISELECT_CANONICAL", true);
    g_collectKeys = envSwitch("STS_COLLECT_KEYS", true);  // Whole-run objective: collect keys and defeat the Heart.
    std::cout << "[collect keys " << (g_collectKeys ? "ON" : "OFF") << "]\n";

    one_combat::configureRestVPolicyFromEnvironment();
    if (std::getenv("STS_REST_WIN")) {        // win-rate rest policy (heal vs upgrade by P(win))
        g_restWin = envSwitch("STS_REST_WIN", true);
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
    // An explicitly requested model that fails to load is fatal: a silent
    // fallback would run the heuristic stack and still exit 0 (audit
    // 2026-10-11, finding 2). A set-but-empty value still means "not set".
    if (const char *d = std::getenv("STS_OOC_CHECKPOINT_NN"); d && *d) {
        if (!g_oocCheckpointNet.load(d)) {
            std::cerr << "[STS_OOC_CHECKPOINT_NN] failed to load model: " << d << "\n";
            return 1;
        }
        g_oocActionNN = true;
        std::cout << "[OOC decisions via native checkpoint-distilled NN]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_NN"); d && *d) {
        if (!g_oocStrategicNet.load(d)) {
            std::cerr << "[STS_OOC_STRATEGIC_NN] failed to load model: " << d << "\n";
            return 1;
        }
        g_effectiveOocStrategicPath = d;
        std::cout << "[OOC one-ply strategic NN ON: card rewards gated at margin "
                  << g_oocStrategicMargin << "]\n";
    }
    if (const char *d = std::getenv("STS_OOC_STRATEGIC_TOK_NN"); d && *d) {
        if (!g_oocStrategicTokNet.load(d)) {
            std::cerr << "[STS_OOC_STRATEGIC_TOK_NN] failed to load model: " << d << "\n";
            return 1;
        }
        g_effectiveOocStrategicTokPath = d;
        g_oocStrategicTok = 1;
        std::cout << "[OOC one-ply strategic TOK net ON: card rewards gated at margin "
                  << g_oocStrategicMargin << "]\n";
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
    if (const char *d = std::getenv("STS_CPSI_NN"); d && *d && std::string(d) != "0") { // C_psi surrogate
        const std::string path = std::string(d) == "1" ? "build/v_combat_cpsi.txt" : d;
        if (!g_cpsiNet.load(path)) {
            std::cerr << "[STS_CPSI_NN] failed to load C_psi model: " << path << "\n";
            return 1;
        }
        std::cout << "[C_psi combat surrogate loaded: " << g_cpsiNet.description() << "]\n";
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
    if (const char *v = std::getenv("STRATEGIC_BRANCH_FUTURE_OFFSET"))
        g_strategicBranchFutureOffset = std::max(0, std::atoi(v));
    if (const char *v = std::getenv("STRATEGIC_BRANCH_RESEED"))
        g_strategicBranchReseed = std::atoi(v) != 0;
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
        if (!g_winNet.load(path, richIdxMap())) {
            std::cerr << "[STS_WIN_NET] explicit STS_WIN_NET failed to load win tree: " << path << "\n";
            return 1;
        }
    }
    if (const char *f = std::getenv("STS_CF_ALT_BOOT_FLOOR_TREES")) {
        const char *w = std::getenv("STS_CF_ALT_BOOT_WIN_TREES");
        if (!w || !g_altBootFloorNet.load(f, richIdxMap()) || !g_altBootWinNet.load(w, richIdxMap())) {
            std::cerr << "[cf-alt-boot] need loadable STS_CF_ALT_BOOT_FLOOR_TREES and STS_CF_ALT_BOOT_WIN_TREES\n";
            return 1;
        }
        std::cout << "[cf-alt-boot] alternative branch bootstrap ON: " << f << " , " << w << "\n";
    }
    if (const char *d = std::getenv("STS_RUNWIN_SHADOW_MODEL"); d && *d) {
        if (!one_combat::loadE2cRawModel(d)) {
            std::cerr << "[STS_RUNWIN_SHADOW_MODEL] failed to load E2c RAW critic: " << d << "\n";
            return 1;
        }
    }
    {
        // The baseline is serverless by default. Set STS_NATIVE_OOC=0 only
        // for an explicit legacy-server comparison.
        g_nativeOoc = envSwitch("STS_NATIVE_OOC", true);
        if (g_nativeOoc) {
            // Without STS_WIN_NET, live OOC MCTS uses the public X2-B win
            // model (§449, ADR-0029); every other run keeps B0. STS_WIN_NET=1
            // restores B0 under OOC MCTS.
            const char *mcts = std::getenv("STS_OOC_MCTS");
            const std::string defaultWin = mcts && std::string(mcts) == "1"
                ? "models/candidates/v_win_x2b_public_trees.txt" : "models/v_win_trees.txt";
            if (!g_winNet.ok) g_winNet.load(defaultWin, richIdxMap());
            g_floorNet.load("models/v_rich_trees.txt", richIdxMap());
            if (!g_floorNet.ok) {
                std::cerr << "[native OOC] failed to load models/v_rich_trees.txt\n";
                return 1;
            }
            // Without V_win the win-rate rest policy reads 0 gains from the
            // absent v_server and always rests (audit 2026-10-11, finding 2).
            if (!g_winNet.ok) {
                std::cerr << "[native OOC] failed to load " << defaultWin << "\n";
                return 1;
            }
            std::cout << "[native OOC floor/win GBMs ON; no v_server required]\n";
            if (!std::getenv("STS_WIN_NET") && mcts && std::string(mcts) == "1")
                std::cout << "[OOC MCTS default win model: " << defaultWin << "]\n";
        }
    }
    try {
        if (sts::search::oocSkipOptionalRecallEnabled())
            std::cout << "[native OOC optional Ruby Recall excluded when keys off and another action is legal]\n";
        if (sts::search::oocSkipFullHpRestEnabled())
            std::cout << "[native OOC full-HP REST excluded when Smith is legal and Dream Catcher is absent]\n";
        if (sts::search::oocRemoveLowObtainWeightEnabled())
            std::cout << "[native OOC fallback REMOVE ranks low acquisition weight first; Bonfire unchanged]\n";
        if (const int futures = one_combat::nativeOocPublicFutureCount(); futures > 0)
            std::cout << "[native OOC public encounter mixture: " << futures << " futures]\n";
        if (one_combat::nativeOocShopDeckSizeFixEnabled())
            std::cout << "[native OOC shop deck-size correction ON]\n";
        one_combat::configureLiveOocMcts();
    }
    catch (const std::exception &e) {
        std::cerr << "[live OOC MCTS startup failure] " << e.what() << '\n';
        return 1;
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
        if (g_simAdapt) {
            if (const char *path=std::getenv("STS_SIM_ADAPT_CTM"))
                if (*path) g_simAdaptCtm=std::make_unique<one_combat::NativeCombatTransitionSampler>(path);
            std::cout << '[' << (g_simAdaptCtm ? "CTM" : "C_psi")
                      << " adaptive sim budget ON: frac " << g_simAdaptMinFrac
                      << ".." << g_simAdaptMaxFrac << (g_simAdaptCtm ? "]\n" : " (needs STS_CPSI_NN)]\n");
        }
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
    try {
        const bool cardRank = one_combat::nativeOocCardWinRankEnabled();
        if (const char *raw = std::getenv("STS_OOC_CARD_WIN_RANK_TRACE")) {
            const std::string value(raw);
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_OOC_CARD_WIN_RANK_TRACE must be 0 or 1");
            g_nativeCardWinRankTrace = value == "1";
        }
        if (g_nativeCardWinRankTrace && !cardRank)
            throw std::runtime_error("STS_OOC_CARD_WIN_RANK_TRACE requires STS_OOC_CARD_WIN_RANK=1");
        if (cardRank) {
            if (!g_nativeOoc || !g_floorNet.ok || !g_winNet.ok || !g_winNet.logistic
                || one_combat::nativeOocPublicFutureCount() != 8
                || one_combat::liveOocMctsEnabled() || g_oocStrategicGateRegret
                || g_cardWin || g_cardNN || g_cardAction || g_oocActionNN
                || g_bossV || g_bossDraft || g_actFightProbeDraft || g_actFightProbeAllOoc
                || !std::isfinite(g_cardSkipThresh))
                throw std::runtime_error("STS_OOC_CARD_WIN_RANK requires native loaded floor/logistic-win models, public8, finite floor skip, margin gate, MCTS off and alternate card policies off");
            std::cout << "[native OOC card win ranking ON; public8 floor take/skip preserved]\n";
        }
    } catch (const std::exception &error) {
        std::cerr << "[native card ranking startup failure] " << error.what() << '\n';
        return 1;
    }
    one_combat::configureVPathPolicyFromEnvironment();
    if (const char *d = std::getenv("STS_DG_TEMP")) {         // datagen softmax temperature (card marginals)
        g_dgTemp = std::atof(d);
        std::cout << "[datagen softmax temp = " << g_dgTemp << "]\n";
    }
    // ADR-0019: Searcher3 was removed. Reject a request for it instead of
    // silently running another searcher; STS_SEARCHER3=0 stays accepted.
    if (const char *d = std::getenv("STS_SEARCHER3"); d && std::atoi(d) != 0) {
        std::cerr << "error: STS_SEARCHER3 is no longer supported; Searcher3 was removed (ADR-0019)\n";
        return 2;
    }
    // Silver owns local RNG/chance search for every combat (ADR-0020), running
    // natively on the main engine (ADR-0021); the vendored model was removed
    // (ADR-0022).
    if (const char *d = std::getenv("STS_NATIVE_SILVER"); d && *d && std::atoi(d) == 0) {
        std::cerr << "error: STS_NATIVE_SILVER=0 is no longer supported; "
                     "the vendored Silver model was removed (ADR-0022)\n";
        return 2;
    }
    if (const auto option = unsupportedSilverOption(); !option.empty()) {
        std::cerr << "error: " << option << " is not supported by the native Silver backend; "
                     "the vendored Silver model and its options were removed (ADR-0022)\n";
        return 2;
    }
    search::installNativeSilverBackend();
    one_combat::installSilverPriceTableLeafFromEnv();   // research, default off (STS_SILVER_PRICE_TABLE_LEAF)
    if (!search::nativeSilverRootPriorPath().empty())
        std::cout << "[research Silver root prior ON: " << search::nativeSilverRootPriorPath()
                  << " weight " << search::nativeSilverRootPriorWeight()
                  << (std::getenv("STS_SILVER_ROOT_PRIOR_SCOPE") && std::string(std::getenv("STS_SILVER_ROOT_PRIOR_SCOPE")) == "override"
                      ? " scope=override (thread opt-in only; live combats plain)" : "")
                  << (search::nativeSilverTreePriorMinVisits() > 0
                      ? "; tree prior K=" + std::to_string(search::nativeSilverTreePriorMinVisits()) : std::string{})
                  << "]\n";
    std::cout << "[Native Silver combat backend: Silver search on the main engine"
              << (search::nativeSilverAdaptiveEnabled() ? "; adaptive"
                  : search::nativeSilverLearnedStopEnabled()
                      ? (search::nativeSilverLearnedStopBossFallback() ? "; learned stop, bosses #199"
                         : search::nativeSilverLearnedStopBossMax() > 0 ? "; learned stop, boss cap raised"
                         : "; learned stop")
                      : "; flat budget")
              << (search::nativeSilverLearnedStopEnabled()
                      ? std::string(" ") + search::nativeSilverStopModelId() : std::string{})
              << (search::nativeSilverExactRootBudgets() ? "; exact root budgets" : "")
              << (search::nativeSilverSearchesSingletonRoots() ? "" : "; one-action roots unsearched")
              << (search::nativeSilverAct4Strong() ? "; Act 4 strong (S&S 10k prior playouts, Heart 40k)" : "")
              << "]\n";
    if (const char *d = std::getenv("STS_FORCE_RELIC"); d && *d) { // force a relic at run start (paired A/B)
        const std::string name(d);
        int id = -1;
        for (int i = 0; i < kNumRelics; ++i)
            if (name == relicEnumNames[i]) { id = i; break; }
        // An unknown name used to run unforced, which turns an A/B into A/A.
        if (id < 0) {
            std::cerr << "[STS_FORCE_RELIC] unknown relic name: " << name << "\n";
            return 1;
        }
        g_forceRelic = (RelicId)id;
        std::cout << "[forced relic at run start: " << relicEnumNames[id] << "]\n";
    }
    try { one_combat::finalizeLiveOocMctsCapture(); }
    catch (const std::exception &error) {
        std::cerr << "[OOC leaf capture startup failure] " << error.what() << '\n';
        return 1;
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

    } else if (mode == "potionpriceprobe") {
        // Paired-continuation resource prices (research only):
        // potionpriceprobe NSEEDS SEED_START SIMS ASC OUT [STATES_PER_RUN] [FIGHTS_AHEAD] [HP_DELTA] [SAMPLE] [EXTRA]
        // FIGHTS_AHEAD: a fight count, or "act" = until the current act's boss fight ends.
        // SAMPLE: potions (states holding a potion; default) or all. EXTRA: comma list of
        // leaf:concave=K, gold:-N, maxhp:-N, ooc=heart1, addpot:NAME ("-" = none).
        if (argc < 7) { std::cerr << "usage: potionpriceprobe NSEEDS SEED_START SIMS ASC OUT [STATES_PER_RUN=4] [FIGHTS_AHEAD=3|act] [HP_DELTA=8] [SAMPLE=potions|all] [EXTRA=-]\n"; return 2; }
        const int nSeeds = std::stoi(argv[2]);
        const std::uint64_t seedStart = std::stoull(argv[3]);
        const int sims = std::stoi(argv[4]);
        const int asc = std::stoi(argv[5]);
        const std::string out = argv[6];
        const int statesPerRun = argc > 7 ? std::stoi(argv[7]) : 4;
        const int fightsAhead = argc <= 8 ? 3
            : std::string(argv[8]) == "act" ? kPriceProbeActHorizon : std::max(0, std::stoi(argv[8]));  // <= 0 is refused
        const int hpDelta = argc > 9 ? std::stoi(argv[9]) : 8;
        const std::string sample = argc > 10 ? argv[10] : "potions";
        if (sample != "potions" && sample != "all") { std::cerr << "potionpriceprobe: SAMPLE must be potions or all\n"; return 2; }
        const std::string extra = argc > 11 && std::string(argv[11]) != "-" ? argv[11] : "";
        std::cout << "potionpriceprobe seeds " << seedStart << ".." << seedStart + nSeeds - 1
                  << " sims=" << sims << " asc=" << asc << " statesPerRun=" << statesPerRun
                  << " fightsAhead=" << (fightsAhead == kPriceProbeActHorizon ? std::string("act") : std::to_string(fightsAhead))
                  << " hpDelta=" << hpDelta << " sample=" << sample
                  << " extra=" << (extra.empty() ? "-" : extra) << " -> " << out << '\n';
        potionPriceProbe(nSeeds, seedStart, sims, asc, out, statesPerRun, fightsAhead, hpDelta,
                         sample == "all", extra);

    } else if (mode == "fightendpairgen") {
        // Paired fight-end continuations (research only; docs/knowledge-base/research/fight-end-pairs.md):
        // fightendpairgen NSEEDS SEED_START SIMS ASC OUT [OPTIONS=-] [VARIANTS=default]
        // OPTIONS: comma list n=FORKS_PER_RUN, rooms=NORMAL+ELITE+BOSS(+OTHER), acts=1+2+3+4,
        // strata=none|room|act|room_act, horizon=end|N, ooc=heart1. VARIANTS: comma list of
        // hp:-N, pot:NAME|*, maxhp:-N, gold:-N, curse:NAME, ctr:RELIC|*:+-N, noop ("default" =
        // hp:-3,hp:-8,hp:-15,pot:*,maxhp:-5,gold:-50). Writes OUT (JSONL) and OUT.manifest.json.
        if (argc < 7) { std::cerr << "usage: fightendpairgen NSEEDS SEED_START SIMS ASC OUT [OPTIONS=-] [VARIANTS=default]\n"; return 2; }
        const int nSeeds = std::stoi(argv[2]);
        const std::uint64_t seedStart = std::stoull(argv[3]);
        const int sims = std::stoi(argv[4]);
        const int asc = std::stoi(argv[5]);
        const std::string out = argv[6];
        const std::string options = argc > 7 ? argv[7] : "-";
        const std::string variants = argc > 8 ? argv[8] : "default";
        std::cout << "fightendpairgen seeds " << seedStart << ".." << seedStart + nSeeds - 1 << " sims=" << sims
                  << " asc=" << asc << " options=" << options << " variants=" << variants << " -> " << out << '\n';
        one_combat::fightEndPairGen(nSeeds, seedStart, sims, asc, out, options, variants);

    } else if (mode == "fightendpairselftest") {
        return one_combat::fightEndPairSelfTest(argc, argv);

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

    } else if (mode == "heartoutcomeselftest") {
        return one_combat::heartOutcomeSelfTest();
    } else if (mode == "forcebossrelicselftest") {
        return forcedBossRelicSelfTest();
    } else if (mode == "forcedecisionselftest") {
        return forcedDecisionSelfTest();
    } else if (mode == "rundriverlossselftest") {   // rundriverlossselftest <nSeeds=1> <seed=0>: one seed only
        if (argc > 2 && std::string(argv[2]) != "1")
            throw std::runtime_error("rundriverlossselftest plays exactly one seed");
        const std::uint64_t seed = argc > 3 ? std::stoull(argv[3]) : 0;
        if (const int rc = runDriverLossAccountingSelfTest(seed)) return rc;
        // bestbench on one seed with a substitute backend that throws `thrown`; returns bestBench's result and the
        // lines of the results file (header first).
        const auto benchWith = [&](std::function<void()> thrown, std::vector<std::string> &lines) {
            const auto savedBackend = search::g_externalCombatBackend;
            search::g_externalCombatBackend = [thrown](search::ScumSearchAgent2 &, GameContext &gc, BattleContext &bc) {
                bc.init(gc);
                thrown();
            };
            const std::string path = (std::filesystem::temp_directory_path()
                / ("sts_rundriverloss_" + std::to_string(seed) + "_" + std::to_string(::getpid()) + ".csv")).string();
            const bool ok = bestBench(1, 1, 20, seed, path, "rundriverlossselftest");
            search::g_externalCombatBackend = savedBackend;
            lines.clear();
            { std::ifstream in(path); for (std::string line; std::getline(in, line);) lines.push_back(line); }
            std::error_code ec;
            std::filesystem::remove(path, ec); std::filesystem::remove(path + ".meta.json", ec);
            return ok;
        };
        std::vector<std::string> lines;
        const auto fail = [&](const std::string &what) {
            std::cerr << "FAIL rundriverlossselftest bestbench: " << what << '\n';
            for (const auto &l : lines) std::cerr << "  " << l << '\n';
            return 1;
        };
        // 1. A combat abort (CombatStateFailure) is a completed loss row (deathEncounter=-2) and still succeeds.
        bool ok = benchWith([] { throw search::CombatStateFailure("selftest: stall"); }, lines);
        if (!ok) return fail("bestBench returned false for a combat abort");
        if (lines.size() != 2) return fail("abort: expected header + one row");
        std::vector<std::string> f;
        { std::stringstream ss(lines[1]); for (std::string x; std::getline(ss, x, ',');) f.push_back(x); }
        if (f.size() != 10 || f[0] != std::to_string(seed) || f[1] != "0" || f[6] != "1" || f[7] != "1"
                || f[8] != std::to_string(kDeathEncounterCombatAbort))
            return fail("abort: row is not seed,won=0,...,fightsLost=1,deathCombat=1,deathEncounter=-2");
        std::cout << "rundriverlossselftest bestbench abort row OK: " << lines[1] << '\n';
        // 2. A plain runtime_error (configuration or I/O error) is a seed failure: no row, bestBench fails.
        ok = benchWith([] { throw std::runtime_error("selftest: cannot open model"); }, lines);
        if (ok) return fail("bestBench succeeded on a configuration error");
        if (lines.size() > 1) return fail("config error: a data row was written");
        std::cout << "rundriverlossselftest bestbench config error OK: no row, failure reported\n";
        return 0;
    } else if (mode == "a4perturbselftest") {
        return one_combat::a4PerturbSelfTest();
    } else if (mode == "heart1pposelftest") {
        one_combat::heart1::ppoSelfTest();
        one_combat::heart1::ppoCoverageSelfTest();
        return 0;
    } else if (mode == "heart1recordselftest") {
        one_combat::heart1::publicRecordInvarianceSelfTest();
        std::cout << "heart1 public record invariance selftest: ok\n";
        return 0;
    } else if (mode == "expertreplay") {
        if (argc != 5 || std::string(argv[2]) != "1")
            throw std::runtime_error("usage: one_combat expertreplay 1 RUN.json OUT.json");
        return one_combat::expertReplayGen(argv[3], argv[4]);
    } else if (mode == "expertfights") {
        if (argc != 5 || std::string(argv[2]) != "1")
            throw std::runtime_error("usage: one_combat expertfights 1 RUN.json OUT.json");
        return one_combat::expertFightsGen(argv[3], argv[4]);
    } else if (mode == "heartoutcomegen") {
        const std::string capture = argc == 6 ? argv[5] : "";
        if (argc != 6 || std::string(argv[2]) != "1"
                || (capture != "on" && capture != "off" && capture != "policy"))
            throw std::runtime_error("usage: one_combat heartoutcomegen 1 SEED OUT.jsonl on|off|policy");
        const std::string seed(argv[3]);
        if (seed.empty() || seed.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("heart outcome seed must be a nonnegative integer");
        return one_combat::heartOutcomeGen(std::stoull(seed), argv[4], capture != "off", capture == "policy");
    } else if (mode == "heartleafparity") {
        if (argc != 4) throw std::runtime_error("usage: one_combat heartleafparity MANIFEST.json ROWS.jsonl");
        return one_combat::heartLeafParity(argv[2], argv[3]);
    } else if (mode == "heartleaftail") {
        if (argc < 6) throw std::runtime_error("usage: one_combat heartleaftail SALT REPEATS OUT.jsonl ROOTS.jsonl...");
        for (int i : {2, 3}) {
            const std::string value(argv[i]);
            if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
                throw std::runtime_error("heartleaftail SALT and REPEATS must be nonnegative integers");
        }
        return one_combat::heartLeafTailGen(std::stoull(argv[2]), unsigned(std::stoul(argv[3])), argv[4],
                                            std::vector<std::string>(argv + 5, argv + argc));
    } else if (mode == "oocselectivesilverspec") {
        try { std::cout << one_combat::oocSelectiveSilverAuditSpec().dump() << '\n'; return 0; }
        catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
    } else if (mode == "oocselectivesilvergen") {
        if (argc != 6 || std::string(argv[2]) != "1") {
            std::cerr << "usage: one_combat oocselectivesilvergen 1 SEED PLAN.json OUT.jsonl\n"; return 2;
        }
        try {
            const std::string value(argv[3]);
            if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
                throw std::runtime_error("audit seed must be a nonnegative integer");
            return one_combat::oocSelectiveSilverAuditGen(std::stoull(value), argv[4], argv[5]);
        }
        catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
    } else if (mode == "oocselectivesilverselftest") {
        try { const int samplerStatus = one_combat::auditNativeSilverSamplerSelfTest();
            if (samplerStatus) return samplerStatus;
            const int horizonStatus = one_combat::oocSelectiveSilverHorizonSelfTest();
            return horizonStatus ? horizonStatus : one_combat::oocSelectiveSilverAccountingSelfTest(); }
        catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
    } else if (mode == "oocleafreplayprobe" || mode == "oocleafstabilityprobe") {
        const bool stability = mode == "oocleafstabilityprobe";
        if (argc != (stability ? 6 : 5) || std::string(argv[2]) != "1") {
            std::cerr << "usage: one_combat " << mode << " 1 SEED ASC"
                << (stability ? " PLAN.json" : "") << '\n';
            return 2;
        }
        try {
            for (int i : {3, 4}) {
                const std::string value(argv[i]);
                if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
                    throw std::runtime_error("seed and ascension must be nonnegative integers");
            }
            return stability
                ? one_combat::oocLeafStabilityProbe(std::stoull(argv[3]), std::stoi(argv[4]), argv[5])
                : one_combat::oocLeafReplayProbe(std::stoull(argv[3]), std::stoi(argv[4]));
        } catch (const std::exception &error) {
            std::cerr << mode << ": " << error.what() << '\n';
            return 1;
        }
    } else if (mode == "oocleafstabilityselftest") {
        try { return one_combat::oocLeafStabilitySelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "oocleafreplayselftest") {
        try { return one_combat::oocLeafReplaySelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "oocmctsconfigselftest") {
        std::cout << "PASS live OOC MCTS configuration startup\n";
    } else if (mode == "oocmctsselftest") {
        try {
            one_combat::oocMctsAdapterSelfTest();
            GameContext gc(CharacterClass::IRONCLAD, 42, 0);
            PathHistory initialHistory;
            one_combat::OocGameContextModel model(gc, initialHistory);
            const bool loaded = g_winNet.ok;
            g_winNet.ok = false;
            bool constructorRejected = false, leafRejected = false;
            try { one_combat::OocGameContextModel missing(gc, initialHistory); }
            catch (const std::runtime_error &) { constructorRejected = true; }
            try { model.leafValue(0); }
            catch (const std::runtime_error &) { leafRejected = true; }
            // Exact terminals still bypass native evaluation at a boundary.
            gc.screenState = ScreenState::BATTLE;
            gc.outcome = GameOutcome::PLAYER_VICTORY;
            g_winNet.ok = loaded;
            one_combat::OocGameContextModel terminal(gc, initialHistory);
            g_winNet.ok = false;
            auto exact = search::OocMctsPlanner().search(terminal, 0, 3);
            g_winNet.ok = loaded;
            if (!constructorRejected || !leafRejected || exact.metrics.leafEvaluations != 0)
                throw std::runtime_error("native v_win fail-closed/terminal test failed");
            std::cout << "PASS native v_win unavailable rejects construction/leaves; terminals bypass leaves\n";
        } catch (const std::exception &e) {
            std::cerr << "FAIL oocmctsselftest: " << e.what() << '\n';
            return 1;
        }
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
        int asc          = argc > 4 ? std::stoi(argv[4]) : 20;
        RunResult r = runFullRun(sd, sims, asc, false);
        std::printf("=== %s ===  reached floor %d (act %d)  hp %d/%d  %.2fs\n",
                    r.won ? "WIN" : "DEAD", r.floor, r.act, r.hpEnd, r.maxHp, r.sec);

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

    } else if (mode == "ooclearnedstoptest") {  // learned OOC stop: features + model parity with the exporter
        return one_combat::oocLearnedStopTestCommand(argc, argv);
    } else if (mode == "heart1logitscheck") {
        return one_combat::heart1::logitsCheckCommand(argc, argv);
    } else if (mode == "heart1cardtable") {   // x3_deck card table for ppo_model.py's deck_aggregates
        return one_combat::heart1::cardTableCommand(argc, argv);
    } else if (mode == "heart1score") {   // heart1 parity: native logits for silverbot records
        return one_combat::heart1::scoreCommand(argc, argv);
    } else if (mode == "heart1replay") {  // heart1 parity: replay one seed's OOC action bits
        return one_combat::heart1::replayCommand(argc, argv);
    } else if (mode == "rolloutstudentscore") {  // §494 rollout student parity on captured sibling rows
        return one_combat::rolloutStudentScoreCommand(argc, argv);
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

    } else if (mode == "runwinparity") {
        const std::string fixture = argc > 2 ? argv[2] : "tools/runwin_e2c_synthetic_parity.csv";
        return one_combat::runwinParity(fixture);

    } else if (mode == "e2cprojectiontest") {
        return one_combat::e2cRawProjectionParityTest();

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

    } else if (mode == "wholecombatgen") {
        if (argc < 8) { std::cerr << "usage: one_combat wholecombatgen N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json\n"; return 2; }
        wholeCombatGen(std::stoi(argv[2]),std::stoi(argv[3]),std::stoi(argv[4]),argv[5],std::stoll(argv[6]),argv[7]);
    } else if (mode == "combattransitiongen") {
        if (argc < 8) { std::cerr << "usage: one_combat combattransitiongen N_SEEDS SIMS ASC OUT.jsonl SEED_OFFSET TEACHER.json\n"; return 2; }
        combatTransitionGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
                            argv[5], std::stoll(argv[6]), argv[7]);
    } else if (mode == "combattransitionforcedgen") {
        if (argc < 9) { std::cerr << "usage: one_combat combattransitionforcedgen N_SEEDS SIMS ASC OUT.jsonl SEED_OFFSET TEACHER.json SETUP\n"
                                     "  SETUP: ritual_writhing | high_maxhp | lizard_fairy | lizard_brew | act4_fork\n"; return 2; }
        combatTransitionGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
                            argv[5], std::stoll(argv[6]), argv[7], false, argv[8]);
    } else if (mode == "silversynthgen") {
        if (argc < 9) { std::cerr << "usage: one_combat silversynthgen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET TEACHER.json VARIANT\n"
                                     "  VARIANT: natural | perturbed (flat exact-10k teacher)\n"; return 2; }
        silverSynthGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
                       argv[5], std::stoll(argv[6]), argv[7], argv[8]);
    } else if (mode == "silverazgen") {
        if (argc < 10) { std::cerr << "usage: one_combat silverazgen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET VARIANT TREE_MIN_VISITS ROOT_BONUS\n"
                                      "  VARIANT: natural | perturbed; prior: STS_SILVER_ROOT_PRIOR (combat_policy_mlp_v1); ROOT_BONUS: 0 | 1\n"; return 2; }
        silverAzGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5], std::stoll(argv[6]),
                    argv[7], std::stoi(argv[8]), std::stoi(argv[9]));
    } else if (mode == "silverazfocusgen") {
        if (argc < 12) { std::cerr << "usage: one_combat silverazfocusgen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET ENCOUNTER REPLICATES OTHER_SIMS TREE_MIN_VISITS ROOT_BONUS\n"
                                      "  ENCOUNTER: MonsterEncounter enum name, e.g. COLLECTOR (a boss is forced as its act's boss)\n"; return 2; }
        silverAzFocusGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5], std::stoll(argv[6]),
                         argv[7], std::stoi(argv[8]), std::stoi(argv[9]), std::stoi(argv[10]), std::stoi(argv[11]));
    } else if (mode == "silverfocusevalgen") {
        if (argc < 13) { std::cerr << "usage: one_combat silverfocusevalgen N_SEEDS ASC OUT_PREFIX SEED_OFFSET ENCOUNTER REPLICATES OTHER_SIMS ARM_SIMS TREE_MIN_VISITS PRIOR_A PRIOR_B\n"; return 2; }
        silverFocusEvalGen(std::stoi(argv[2]), std::stoi(argv[3]), argv[4], std::stoll(argv[5]), argv[6],
                           std::stoi(argv[7]), std::stoi(argv[8]), std::stoi(argv[9]), std::stoi(argv[10]),
                           argv[11], argv[12]);
    } else if (mode == "turndomgen") {
        if (argc < 7) { std::cerr << "usage: one_combat turndomgen N_SEEDS SIMS ASC SEED_OFFSET OUT.jsonl [MAX_EXECS=200000] [MAX_SNAPSHOTS=40]\n"; return 2; }
        turnDominanceGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), std::stoll(argv[5]), argv[6],
                         argc > 7 ? std::stoll(argv[7]) : 200000, argc > 8 ? std::stoi(argv[8]) : 40);
    } else if (mode == "act4replay") {
        if (argc < 8) { std::cerr << "usage: one_combat act4replay N_STATES STATES.jsonl OUT_PREFIX SEED_OFFSET SIMS[,SIMS..] REPLICATES\n"; return 2; }
        act4Replay(std::stoi(argv[2]), argv[3], argv[4], std::stoll(argv[5]), argv[6], std::stoi(argv[7]));
    } else if (mode == "fightreplay") {
        if (argc != 7) { std::cerr << "usage: one_combat fightreplay N_ROWS ROWS.jsonl OUT.jsonl SEED_BASE REPLICATES\n"; return 2; }
        return fightReplay(std::stoi(argv[2]), argv[3], argv[4], std::stoull(argv[5]), std::stoi(argv[6]));
    } else if (mode == "silversynthfeatures") {
        if (argc < 3) { std::cerr << "usage: one_combat silversynthfeatures OUT_PREFIX < corpus.jsonl\n"; return 2; }
        silverSynthFeatures(argv[2]);
    } else if (mode == "silverpolicymlpcheck") {
        if (argc < 5) { std::cerr << "usage: one_combat silverpolicymlpcheck MODEL FEATURE_PREFIX OUT.txt [GBM_MODEL]\n"; return 2; }
        silverPolicyMlpCheck(argv[2], argv[3], argv[4], argc >= 6 ? argv[5] : "");
    } else if (mode == "silversynthreplay") {
        silverSynthReplay(argc >= 4 && std::string(argv[2]) == "names" ? argv[3] : "");
    } else if (mode == "combattransitionlizardtargetcandidategen") {
        if (argc < 8) { std::cerr << "usage: one_combat combattransitionlizardtargetcandidategen N_SEEDS SIMS ASC OUT.jsonl SEED_OFFSET TEACHER.json\n"; return 2; }
        combatTransitionGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]),
                            argv[5], std::stoll(argv[6]), argv[7], true);
    } else if (mode == "combattransitionlizardgen") {
        if (argc < 10) { std::cerr << "usage: one_combat combattransitionlizardgen N_SEEDS SIMS ASC OUT.jsonl SEED_OFFSET TEACHER.json BASELINE_SHA COLLECTOR_SHA\n"; return 2; }
        activeLizardCombatTransitionGen(std::stoi(argv[2]), std::stoi(argv[3]),
            std::stoi(argv[4]), argv[5], std::stoll(argv[6]), argv[7], argv[8], argv[9]);
    } else if (mode == "combattransitionlizardtargetpairgen") {
        if (argc < 10) { std::cerr << "usage: one_combat combattransitionlizardtargetpairgen N_PAIRS SIMS ASC OUT.jsonl TARGETS.json TEACHER.json BASELINE_SHA COLLECTOR_SHA\n"; return 2; }
        activeLizardPairTransitionGen(std::stoi(argv[2]), std::stoi(argv[3]),
            std::stoi(argv[4]), argv[5], argv[6], argv[7], argv[8], argv[9]);
    } else if (mode == "combattransitionselftest") {
        if (argc < 4) {
            std::cerr << "usage: one_combat combattransitionselftest OUT.jsonl MANIFEST.json\n";
            return 2;
        }
        return combatTransitionFixture(argv[2], argv[3]);
    } else if (mode == "combattransitionlizardselftest") {
        return activeLizardTransitionSelfTest();
    } else if (mode == "combatevalgen") {
        if (argc < 8) { std::cerr << "usage: one_combat combatevalgen N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json [RUNOUT.csv]\n"; return 2; }
        combatEvalGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5], std::stoll(argv[6]), argv[7], argc > 8 ? argv[8] : "");
    } else if (mode == "screenleafprobesselftest") {
        try { return one_combat::screenLeafProbesSelfTest(); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafprobes" || mode == "screenleafproject") {
        if (argc != 5) {
            std::cerr << "usage: one_combat " << mode << " INPUT OUTPUT_OR_DIRECTORY LIMIT\n";
            return 2;
        }
        try {
            return mode == "screenleafprobes"
                ? one_combat::screenLeafProbes(argv[2], argv[3], std::stoul(argv[4]))
                : one_combat::screenLeafProject(argv[2], argv[3], std::stoul(argv[4]));
        } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafnetliveparity") {
        if (argc != 5) { std::cerr << "usage: one_combat screenleafnetliveparity MODEL SNAPSHOTS.jsonl LIMIT\n"; return 2; }
        try { return one_combat::screenLeafNetLiveParity(argv[2], argv[3], std::stoul(argv[4])); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafgbmliveparity") {
        if (argc != 4) { std::cerr << "usage: one_combat screenleafgbmliveparity SNAPSHOTS.jsonl OUT.jsonl\n"; return 2; }
        try { return one_combat::screenLeafGbmLiveParity(argv[2], argv[3]); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafgbmparity") {
        if (argc != 4) { std::cerr << "usage: one_combat screenleafgbmparity MODEL PARITY.jsonl\n"; return 2; }
        try { return one_combat::screenLeafGbmParity(argv[2], argv[3]); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafnetparity") {
        if (argc != 4) { std::cerr << "usage: one_combat screenleafnetparity MODEL PARITY.jsonl\n"; return 2; }
        try { return one_combat::screenLeafNetParity(argv[2], argv[3]); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "screenleafs0") {
        if (argc != 6) {
            std::cerr << "usage: one_combat screenleafs0 SNAPSHOTS OUTPUT LIMIT REPLICATES\n";
            return 2;
        }
        try { return one_combat::screenLeafS0(argv[2], argv[3], std::stoul(argv[4]), std::stoul(argv[5])); }
        catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 2; }
    } else if (mode == "vwinrefreshgen") {
        if (argc < 9 || argc > 10) {
            std::cerr << "usage: one_combat vwinrefreshgen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET TEACHER.json K [PARITY_PERCENT]\n";
            return 2;
        }
        try {
            vwinRefreshGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5],
                           std::stoll(argv[6]), argv[7], std::stoi(argv[8]),
                           argc > 9 ? std::stoi(argv[9]) : 100);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "cardstrengthprobe") {
        if (argc < 7 || argc > 9) {
            std::cerr << "usage: one_combat cardstrengthprobe N_SEEDS OUT_PREFIX SEED_OFFSET TEACHER.json ASCENSION [SILVER_REPS] [NEXT_ACT 0|1]\n";
            return 2;
        }
        try {
            cardStrengthProbe(std::stoi(argv[2]), argv[3], std::stoll(argv[4]), argv[5], std::stoi(argv[6]),
                              argc > 7 ? std::stoi(argv[7]) : 0, argc > 8 && std::string(argv[8]) == "1");
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "ooccfpilotgen") {
        if (argc < 7 || argc > 14) {
            std::cerr << "usage: one_combat ooccfpilotgen N_SEEDS OUT_PREFIX SEED_OFFSET TEACHER.json FUTURES [STATES_PER_SEED] [CARD_BOSSES] [GEN] [TYPES] [TARGET.json|-] [FUTURE_START] [ASCENSION]\n";
            return 2;
        }
        try {
            oocCounterfactualPilotGen(std::stoi(argv[2]), argv[3], std::stoll(argv[4]), argv[5],
                                      std::stoi(argv[6]), argc > 7 ? std::stoi(argv[7]) : 1,
                                      argc > 8 ? std::stoi(argv[8]) : 1,
                                      argc > 9 ? std::stoi(argv[9]) : 1,
                                      argc > 10 ? argv[10] : std::string{},
                                      argc > 11 && std::string(argv[11]) != "-" ? argv[11] : std::string{},
                                      argc > 12 ? std::stoi(argv[12]) : 0,
                                      argc > 13 ? std::stoi(argv[13]) : 0);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "vwinrefreshcrashdiag") {
        // Diagnostic-only: one source seed, production vwinrefreshgen semantics,
        // stop after MAX_BRANCHES sibling branches; flushed phase markers.
        if (argc != 8) {
            std::cerr << "usage: one_combat vwinrefreshcrashdiag N_SEEDS OUT_PREFIX SEED TEACHER.json MAX_BRANCHES MARKERS.log\n";
            return 2;
        }
        try {
            if (std::stoi(argv[2]) != 1) throw std::runtime_error("vwinrefreshcrashdiag: N_SEEDS must be 1");
            const int maxBranches = std::stoi(argv[6]);
            if (maxBranches < 1) throw std::runtime_error("vwinrefreshcrashdiag: MAX_BRANCHES must be positive");
            vwinRefreshGen(1, 10000, 0, argv[3], std::stoll(argv[4]), argv[5], 1, 100,
                           maxBranches, argv[7]);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "bossheadroom347gen") {
        if (argc != 8) {
            std::cerr << "usage: one_combat bossheadroom347gen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET TEACHER.json\n";
            return 2;
        }
        try {
            bossHeadroom347Gen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5],
                               std::stoll(argv[6]), argv[7]);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "bossrescue347") {
        if (argc != 6) {
            std::cerr << "usage: one_combat bossrescue347 1 SELECTION.json STATE_ID OUT_PREFIX\n";
            return 2;
        }
        try {
            return bossRescue347(std::stoi(argv[2]), argv[3], argv[4], argv[5]);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "bossrescue347selftest") {
        if (argc != 5) {
            std::cerr << "usage: one_combat bossrescue347selftest 1 SEED SIMS\n";
            return 2;
        }
        try {
            return bossRescue347SelfTest(std::stoi(argv[2]), std::stoull(argv[3]), std::stoi(argv[4]));
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "silverparams400gen") {
        if (argc != 8) {
            std::cerr << "usage: one_combat silverparams400gen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET TEACHER.json\n";
            return 2;
        }
        try {
            silverParamScreen400Gen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5],
                                    std::stoll(argv[6]), argv[7]);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "silverstopreplaygen") {
        if (argc != 8) {
            std::cerr << "usage: one_combat silverstopreplaygen N_SEEDS SIMS ASC OUT_PREFIX SEED_OFFSET TEACHER.json\n";
            return 2;
        }
        try {
            silverStopReplayGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), argv[5],
                                std::stoll(argv[6]), argv[7]);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "endgamerootgen") {
        if (argc != 7 && argc != 8) {
            std::cerr << "usage: one_combat endgamerootgen N_SEEDS SIMS ASC SEED_OFFSET OUT.jsonl [KEEP=2]\n";
            return 2;
        }
        try {
            endgameRootGen(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), std::stoll(argv[5]), argv[6],
                           argc == 8 ? std::stoi(argv[7]) : 2);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "ctmsilvergen") {
        if (argc != 8) {
            std::cerr << "usage: one_combat ctmsilvergen N_SEEDS ASC OUT_PREFIX SEED_OFFSET TEACHER.json REPLICATES\n";
            return 2;
        }
        try {
            ctmSilverCompareGen(std::stoi(argv[2]), std::stoi(argv[3]), argv[4], std::stoll(argv[5]), argv[6],
                                std::stoi(argv[7]));
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 2;
        }
    } else if (mode == "vwinrefreshpolicyspec") {
        if (argc != 3) return 2;
        try { return vwinRefreshPolicySpec(argv[2]); }
        catch (const std::exception &e) {
            std::cerr << e.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshselftest") {
        if (argc != 2) {
            std::cerr << "usage: one_combat vwinrefreshselftest\n";
            return 2;
        }
        try {
            return vwinRefreshSelfTest();
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshcompoundselftest") {
        if (argc != 2) {
            std::cerr << "usage: one_combat vwinrefreshcompoundselftest\n";
            return 2;
        }
        try {
            return vwinRefreshCompoundSelfTest();
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshdecisionsinkselftest") {
        if (argc != 2) return 2;
        try { return vwinRefreshDecisionSinkSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "matchandkeep_oracle_selftest") {
        if (argc != 2) return 2;
        try { return matchAndKeepOracleSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "matchandkeep_curse_selftest") {
        if (argc != 2) return 2;
        try { return matchAndKeepCurseSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "actfightprobeallooc_rootstate_selftest") {
        if (argc != 2) return 2;
        try { return actFightProbeRootStateSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshmatchkeepselftest") {
        if (argc != 2) return 2;
        try { return vwinRefreshMatchAndKeepSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshcontinuationselftest") {
        if (argc != 2) return 2;
        try { return vwinRefreshContinuationSelfTest(); }
        catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshrewardselftest") {
        if (argc != 2) {
            std::cerr << "usage: one_combat vwinrefreshrewardselftest\n";
            return 2;
        }
        try {
            return vwinRefreshRewardTypeSelfTest();
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshfatalcountselftest") {
        if (argc < 3 || argc > 4) {
            std::cerr << "usage: one_combat vwinrefreshfatalcountselftest SEED [SIMS]\n";
            return 2;
        }
        try {
            return vwinRefreshFatalRunoutCountSelfTest(std::stoull(argv[2]),
                argc > 3 ? std::stoi(argv[3]) : 100);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinvpathguardselftest") {
        if (argc != 2) {
            std::cerr << "usage: one_combat vwinvpathguardselftest\n";
            return 2;
        }
        try {
            return vwinVPathPolicyGuardSelfTest();
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "vwinrefreshbranchselftest") {
        if (argc < 3 || argc > 5) {
            std::cerr << "usage: one_combat vwinrefreshbranchselftest SEED [SIMS] [ASC]\n";
            return 2;
        }
        try {
            return vwinRefreshBranchParitySelfTest(std::stoull(argv[2]),
                argc > 3 ? std::stoi(argv[3]) : 100, argc > 4 ? std::stoi(argv[4]) : 0);
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 1;
        }
    } else if (mode == "oocpolicyparity") {
        if (argc < 3 || argc > 5) {
            std::cerr << "usage: one_combat oocpolicyparity SEED [SIMS] [ASC]\n";
            return 2;
        }
        return oocPolicyParitySelfTest(std::stoull(argv[2]), argc > 3 ? std::stoi(argv[3]) : 100,
                                       argc > 4 ? std::stoi(argv[4]) : 0);
    } else if (mode == "teacher_schema_compat") {
        return teacherSchemaCompatibilitySelfTest();
    } else if (mode == "learnedstopteacherselftest") {
        return learnedStopTeacherSelfTest();
    } else if (mode == "ctmscorerows") {
        if (argc != 4 && argc != 6 && argc != 7) {
            std::cerr << "usage: one_combat ctmscorerows ROWS.jsonl OUT.csv [FAST.native STANDARD.native [LIZARD=0|1]]\n";
            return 2;
        }
        if (argc == 4) return ctmScoreRows(argv[2], argv[3]);
        const std::string lizard = argc == 7 ? argv[6] : "1";
        if (lizard != "0" && lizard != "1") { std::cerr << "ctmscorerows LIZARD must be 0 or 1\n"; return 2; }
        return ctmScoreRows(argv[2], argv[3], argv[4], argv[5], lizard == "1");
    } else if (mode == "ctmopeninghands") {
        if (argc != 5) {
            std::cerr << "usage: one_combat ctmopeninghands ROWS.jsonl OUT.jsonl RESAMPLES\n";
            return 2;
        }
        try { return ctmOpeningHands(argv[2], argv[3], std::stoi(argv[4])); }
        catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
    } else if (mode == "ctmescapefeatures") {
        if (argc != 5) {
            std::cerr << "usage: one_combat ctmescapefeatures ROWS.jsonl MODEL.native OUT_PREFIX\n";
            return 2;
        }
        return ctmEscapeFeatures(argv[2], argv[3], argv[4]);
    } else if (mode == "ctmlizardfeatures") {
        if (argc != 6) {
            std::cerr << "usage: one_combat ctmlizardfeatures ROWS.jsonl FAST.native STANDARD.native OUT.csv\n";
            return 2;
        }
        return ctmLizardFeatures(argv[2], argv[3], argv[4], argv[5]);
    } else if (mode == "ctmscoreselftest") {
        return ctmScoreRowsSelfTest();
    } else if (mode == "ctmact4survivaltest") {
        if (argc != 3) { std::cerr << "usage: one_combat ctmact4survivaltest FIXTURE.jsonl\n"; return 2; }
        return ctmAct4SurvivalSelfTest(argv[2]);
    } else if (mode == "ctmcalibrationtest") {
        if (argc != 4) { std::cerr << "usage: one_combat ctmcalibrationtest FIXTURE.jsonl on|off\n"; return 2; }
        return ctmCalibrationSelfTest(argv[2], argv[3]);
    } else if (mode == "ooccfaudit") {
        if (argc < 8) { std::cerr << "usage: one_combat ooccfaudit N_SEEDS SIMS ASC OUT.csv SEED_OFFSET TEACHER.json\n"; return 2; }
        counterfactualSurrogateAuditGen(std::stoi(argv[2]),std::stoi(argv[3]),std::stoi(argv[4]),argv[5],std::stoull(argv[6]),argv[7]);
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
        int asc    = argc > 4 ? std::stoi(argv[4]) : 20;
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
        int asc = argc > 4 ? std::stoi(argv[4]) : 20;
        std::uint64_t seed = argc > 5 ? std::stoull(argv[5]) : 0;
        std::string resultsFile = argc > 6 ? argv[6] : "";
        std::cout << "[reprobench: seed " << seed << ", repeats " << repeats << "]\n";
        for (int i = 0; i < repeats; ++i) {
            if (!bestBench(sims, 1, asc, seed, resultsFile, "reprobench")) return 1;
        }

    } else if (mode == "runtrace") {      // per-node human-readable trace of ONE seed
        std::uint64_t seed = argc > 2 ? std::stoull(argv[2]) : 0;
        int sims = argc > 3 ? std::stoi(argv[3]) : 1000;
        int asc  = argc > 4 ? std::stoi(argv[4]) : 20;
        runTraceRun(seed, sims, asc);

    } else {
        std::cerr << "usage: one_combat MODE [ARGS...]\n";
        return 2;
    }
    return 0;
}
