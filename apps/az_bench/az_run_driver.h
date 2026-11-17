// Stage 1 of the Amber-Eye-style self-play loop (2026-11-17): the whole-run self-play producer. Worker threads each
// play hundreds of A20 Ironclad runs from Neow to the end; every decision with more than one legal action runs a
// Gumbel AlphaZero search whose leaves are net evaluations, as in the stage 0 combat driver (az_driver.h): requests
// go on one queue, batching threads (Python with the GPU net) pack them into flat batches (az_pack.h) and post the
// results back. Positions of searched moves are kept as training samples whose labels (final outcome, HP at the end
// of the floor) are filled in when the run ends.
//
// From https://8e9f.github.io/amber_eye/: one net for combat and out-of-combat states; Gumbel AlphaZero with 64 / 16
// positions per full / fast move, playout cap randomization p = 0.25; double progressive widening at chance nodes;
// a step that reveals hidden information is resampled in the search; utility U = F + H at first (F = expected final
// floor, H = HP), later P(win) + 0.25 H out of combat and F + 0.5 H in combat.
//
// Our choices: the search tree ends at combat boundaries: an out-of-combat action that starts a fight leads to a
// leaf (the fight's first decision, valued by the net) and a combat action that wins the fight leads to a leaf (the
// state after the fight, valued by the net); a lost fight is terminal. Out-of-combat edges are all chance edges: each
// new outcome is a detached copy of the parent with its hidden future resampled (sampleNoncombatFuture) before the
// action executes; combat edges reseed the search RNG as in stage 0. F = E[final floor] / 57 (a win counts 57), H =
// E[HP at the end of the floor] / max HP; the net's heads are turned into F and E[HP] by the caller, the driver
// mixes U = F + w H with w = hpWeightCombat or hpWeightOoc and scales by 1 / (1 + w) into [0, 1]. One leaf in flight
// per run, no tree reuse between moves. The improved policy completes unvisited edges' Q with the net's root value
// (not the paper's v_mix; a stage-1 simplification).
#ifndef STS_AZ_RUN_DRIVER_H
#define STS_AZ_RUN_DRIVER_H

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <random>
#include <stdexcept>
#include <thread>
#include <vector>

#include "az_pack.h"
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/AmberTokens.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/GameAction.h"
#include "sim/search/SilverSearcher.h"

namespace sts::azbench {

    using CombatEncodeFn = void (*)(const BattleContext &, const search::SilverSearchContext &,
                                    const std::vector<search::Action> &, search::AmberTokens &);
    using GameEncodeFn = void (*)(const GameContext &, const std::vector<search::GameAction> &,
                                  search::AmberTokens &);

    // Placeholder out-of-combat encoder (the default is the native search::amberEncodeGame): run / deck / relic / potion
    // tokens and one OPTION token per legal action (type = screen, action bits as features).
    void stubEncodeGame(const GameContext &gc, const std::vector<search::GameAction> &actions,
                        search::AmberTokens &out);

    // Fair play (ADR-0002): the search and the net see a fight only through the player's public view, as the
    // production Silver search does (nativeSilverSearchRoot): the draw pile is the player's information set (known
    // top / bottom, unknown multiset; concrete only under Frozen Eye) and under Runic Dome the rolled intents are
    // hidden. A per-run CombatKnowledgeState follows the real fight; it observes bc.init and every real action.
    //
    // Starts the fight of gc in bc with knowledge tracking (knowledge is reset).
    void initObservedBattle(const GameContext &gc, BattleContext &bc, search::CombatKnowledgeState &knowledge);
    // Executes a real combat action with the knowledge tracker observing it.
    void executeObserved(BattleContext &bc, std::uint32_t bits, search::CombatKnowledgeState &knowledge);
    // The public view of a live fight (search root and net input). Returns an empty string, or why the view cannot
    // be built (the run is then abandoned as a loss).
    std::string publicCombatRoot(const BattleContext &live, search::CombatKnowledgeState &knowledge,
                                 BattleContext &root);

    constexpr int kOutcomeClasses = 57;   // 0 = win, f = death on floor f (1..56)
    constexpr int kHpClasses = 256;
    constexpr int kAscensions = 21;

    struct RunConfig {
        int workers = 11;
        int gamesPerWorker = 700;
        int ascension = 20;             // of the first runs; setAscension changes it while running
        std::uint64_t seedBase = 0;     // run seeds seedBase, seedBase + 1, ... (one per started run)
        std::int64_t maxRuns = -1;      // stop starting runs after this many (-1 = unlimited)
        int fullSims = 64, fastSims = 16;
        int fullCandidates = 16, fastCandidates = 4;
        double fullProb = 0.25;
        double cVisit = 50, cScale = 1.0;
        double wideningC = 3.7028, wideningAlpha = 0.52389;
        double hpWeightCombat = 1.0, hpWeightOoc = 1.0;   // U = F + w H (Amber's first utility: both 1)
        int maxMovesPerFight = 400;     // a fight past this many decisions counts as lost (stall guard)
        double keepFull = 1.0;          // keep probability of a full-search move as a sample (policy + value)
        double keepFast = 0.0;          // ... of a fast-search move (value only)
        // Samples of unfinished runs wait in memory for their labels (~5.5 KB each). Above this many, the keep
        // probabilities are scaled by maxPendingSamples / pending, so memory stays bounded as runs get longer.
        std::int64_t maxPendingSamples = 300000;
        std::uint64_t searchSeed = 0;   // search / Gumbel / resampling RNG
        int testMaxHp = 0;              // tests only: > 0 sets max / current HP at the run's start (reach late floors)
        // Pick-rate exploration (from Amber Eye; 2026-11-17, default off): an out-of-combat item (CHOOSE_CARD / CHOOSE_OPTION source token: card reward, event /
        // Neow option, relic, shop item) picked in fewer than pickTarget of all runs so far is under target. A root
        // offering one gets a full search, and with probability min(1, exploreC * (1 - rate / pickTarget)) the most
        // under-target item is played instead of the search's choice (the sample keeps the search policy). Rates are over
        // the runs finished in this process, after a warm-up of 1 / pickTarget runs.
        double exploreC = 0;
        double pickTarget = 0.01;
        CombatEncodeFn encodeCombat = nullptr;   // default: search::amberEncodeCombat
        GameEncodeFn encodeGame = nullptr;       // default: search::amberEncodeGame (stubEncodeGame = placeholder)
    };

    // One training sample: the searched position's live tokens and legal actions (flat layout of one row, as
    // packFlat writes it), the improved policy over its actions (full moves), and its labels.
    struct Sample {
        std::vector<std::int8_t> tokType;
        std::vector<std::int16_t> ids;       // [n][4]
        std::vector<std::uint16_t> f;        // [n][64] float16 bits
        std::vector<std::int16_t> aType, aSrc, aTgt;
        std::vector<std::uint16_t> aF;       // [a][8]
        std::vector<float> policy;           // [a] improved policy (empty for a fast move)
        float searchValue = 0;               // root value after the search (scaled utility)
        std::int16_t outcome = -1;           // label: 0 win, f death floor
        std::int16_t hpEnd = -1;             // label: HP at the end of this floor (0 on death)
        std::int16_t maxHp = 0, floor = 0;
        std::uint8_t combat = 0;
        std::uint64_t run = 0;               // run seed
    };

    // Run progress counters of finished runs (2026-11-17; why A0 runs rarely reach Act 4): keys held at the run's
    // end, campfire choices, elite fights, Act 4 and the Heart. Counted per run while it plays, added to the run's
    // ascension when it ends.
    struct RunProgress {
        std::int64_t ruby = 0, emerald = 0, sapphire = 0, allKeys = 0;   // runs ending with the key / all three
        std::int64_t campfires = 0;        // campfire choices (rest, smith, recall, lift, toke, dig)
        std::int64_t recallOffered = 0;    // ... of which with Recall legal (keys on, no Ruby key yet)
        std::int64_t rest = 0, smith = 0, recall = 0, otherCampfire = 0;
        std::int64_t elites = 0;           // elite fights started (Room::ELITE; not event elites)
        std::int64_t burningElites = 0;    // ... of which the burning (Emerald key) elite
        std::int64_t act4 = 0;             // runs that entered Act 4
        std::int64_t heart = 0;            // runs that started the Heart fight
        std::int64_t keylessVictories = 0; // runs ended by the Act 3 boss without the three keys (floor 51)
        RunProgress &operator+=(const RunProgress &o) {
            ruby += o.ruby; emerald += o.emerald; sapphire += o.sapphire; allKeys += o.allKeys;
            campfires += o.campfires; recallOffered += o.recallOffered;
            rest += o.rest; smith += o.smith; recall += o.recall; otherCampfire += o.otherCampfire;
            elites += o.elites; burningElites += o.burningElites; act4 += o.act4; heart += o.heart;
            keylessVictories += o.keylessVictories;
            return *this;
        }
    };

    struct RunStats {
        std::int64_t evals = 0, moves = 0, searchedMoves = 0, runsStarted = 0, runsDone = 0, wins = 0;
        std::int64_t floorsSum = 0, stalls = 0, terminalLeaves = 0, unsupported = 0;
        std::int64_t invalidActions = 0;      // chosen actions not valid in the real fight after translation (bug; run lost)
        std::int64_t knowledgeFailures = 0;   // fights whose public view could not be built (run abandoned as a loss)
        std::int64_t encodeCut = 0, encodeCutOoc = 0;   // tokens / actions past capacity (combat, out of combat; MAP keeps the nearest 32 nodes)
        std::int64_t samplesDone = 0, samplesPending = 0;
        std::int64_t batches = 0, batchRows = 0;
        std::array<std::int64_t, kOutcomeClasses> outcomes{};   // finished runs per outcome class
        // Per ascension (curriculum): finished runs, Heart kills, final floors.
        std::array<std::int64_t, kAscensions> runsDoneAsc{}, winsAsc{}, floorsSumAsc{};
        std::array<RunProgress, kAscensions> progressAsc{};   // finished runs' progress counters per ascension
        std::int64_t oocRoots = 0, exploreRoots = 0, forcedPicks = 0;   // searched OOC decisions; with an under-target item; forced
        double stepCpu = 0, encodeCpu = 0, searchCpu = 0, packSeconds = 0;
    };

    class RunDriver {
    public:
        explicit RunDriver(RunConfig cfg);
        ~RunDriver();
        void start();
        void stop();
        // As Driver::nextBatchFlat (az_driver.h): takes up to maxRows requests, packs them into buf.
        std::vector<std::uint32_t> nextBatchFlat(int maxRows, int minRows, int timeoutMs,
                                                 const std::vector<int> &rowBuckets,
                                                 const std::vector<int> &tokBuckets,
                                                 const std::vector<int> &actBuckets, const FlatBuffers &buf,
                                                 FlatShape &shape, int packThreads = 1);
        // Results: logits[row][action] (`actions` per row), F[row] in [0, 1] and expected HP at the end of the
        // floor ehp[row] (absolute) for each ticket.
        void submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *F,
                    const float *ehp);
        // Moves up to maxSamples finished samples (labels filled) into out, then the rest of the last run taken (a
        // run is never split across calls).
        void takeSamples(int maxSamples, std::vector<Sample> &out);
        RunStats stats() const;
        const RunConfig &config() const { return cfg_; }
        std::uint64_t nextSeed();   // the next run seed (thread-safe); runsStarted counts these
        // Ascension of runs started from now on (curriculum; runs in progress keep theirs). 0..20.
        void setAscension(int a) {
            if (a < 0 || a >= kAscensions) throw std::invalid_argument("run driver: ascension 0..20");
            ascension_.store(a);
        }
        int ascension() const { return ascension_.load(); }

        struct Node;
        struct Run;
        struct Worker;

    private:
        void workerLoop(int w);
        std::vector<std::uint32_t> takeRequests(int maxRows, int minRows, int timeoutMs);
        RunConfig cfg_;
        std::vector<std::unique_ptr<Worker>> workers_;
        std::vector<std::thread> threads_;
        std::atomic<bool> stop_{false};
        std::atomic<std::int64_t> seedsUsed_{0};
        std::atomic<std::int64_t> pending_{0};   // samples of unfinished runs, all workers
        static constexpr int kPickBuckets = 1 << 16;
        std::unique_ptr<std::atomic<std::uint32_t>[]> picks_;
        std::atomic<int> ascension_{20};
        std::atomic<std::int64_t> runsDone_{0};   // finished runs, all workers (pick-rate denominator)   // real picks per item hash (pick-rate exploration)
        mutable std::mutex qm_;
        std::condition_variable qcv_;
        std::deque<std::uint32_t> queue_;   // ticket = worker << 16 | run
        std::mutex sampleM_;
        std::deque<Sample> done_;
        std::atomic<std::int64_t> batches_{0}, batchRows_{0}, packNs_{0};
    };

}

#endif
