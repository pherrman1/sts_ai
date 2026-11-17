// Stage 0 throughput bench, part 3 (Amber-Eye-style self-play loop, 2026-11-16): the end-to-end producer. Worker
// threads each run hundreds of combat games; every game runs a Gumbel AlphaZero search whose leaves are net
// evaluations. A leaf's state is encoded into the game's AmberTokens buffer and its id put on one request queue;
// batching threads (Python with a GPU net, or the C++ fake net) take up to B requests, pack them into one batch,
// evaluate it, and post each result back to its worker. This follows https://8e9f.github.io/amber_eye/ ("14 worker
// threads each running hundreds of self-play games ... network evaluation requests were submitted into a queue, and
// separate threads packed the requests from the queue into larger batches and passed them to the GPU"; Gumbel
// AlphaZero, 64 / 16 positions per full / fast move with playout cap randomization p = 0.25; a step that reveals
// hidden information rerolls its RNG; double progressive widening at chance nodes).
//
// Our choices (bench only): combat-only games restarted from wire rows; no tree reuse between moves; one leaf in
// flight per game (no virtual visits); the leaf value is a scalar in [0, 1] (terminal: 1 win, 0 loss); Gumbel MuZero
// selection below the root. Positions = net evaluations.
#ifndef STS_AZ_BENCH_DRIVER_H
#define STS_AZ_BENCH_DRIVER_H

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "az_pack.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/AmberTokens.h"
#include "sim/search/SilverSearcher.h"

namespace sts::azbench {

    using EncodeFn = void (*)(const BattleContext &, const search::SilverSearchContext &,
                              const std::vector<search::Action> &, search::AmberTokens &);

    // Placeholder encoder until the native Amber encoder lands: real token counts and ids (cards in every pile,
    // monsters, relics, player statuses, potions, legal actions with source / target), a few floats per token.
    void stubEncode(const BattleContext &bc, const search::SilverSearchContext &ctx,
                    const std::vector<search::Action> &actions, search::AmberTokens &out);

    struct DriverConfig {
        int workers = 10;
        int gamesPerWorker = 256;
        int fullSims = 64, fastSims = 16;   // Amber Eye's self-play budgets
        int fullCandidates = 16, fastCandidates = 4;
        double fullProb = 0.25;             // playout cap randomization
        double cVisit = 50, cScale = 1.0;   // Gumbel sigma(q)
        double wideningC = 3.7028, wideningAlpha = 0.52389;   // Silver's DPW constants
        int maxMovesPerFight = 400;
        std::uint64_t seed = 0;             // search / Gumbel RNG only, not a game seed
        EncodeFn encode = search::amberEncodeCombat;   // native Amber encoder; stubEncode = placeholder
    };

    struct Root {
        BattleContext state;
        search::SilverSearchContext context;
    };

    // One packed batch in amber_net.AmberNet.forward's layout. Segment s has slots[s] token slots (the batch's
    // longest); arrays are row-major [rows][slots[s]][...]. Action src/tgt are indices into the concatenation of the
    // padded segments (-1 = none).
    struct PackedBatch {
        int rows = 0, actions = 0;
        std::array<int, search::kAmberTokenTypes> slots{};
        std::array<std::vector<std::int16_t>, search::kAmberTokenTypes> ids;      // [rows][slots][4]
        std::array<std::vector<std::uint16_t>, search::kAmberTokenTypes> f;       // [rows][slots][64] float16 bits
        std::array<std::vector<std::uint8_t>, search::kAmberTokenTypes> mask;     // [rows][slots]
        std::vector<std::int16_t> aType, aSrc, aTgt;                              // [rows][actions]
        std::vector<std::uint16_t> aF;                                            // [rows][actions][8]
        std::vector<std::uint8_t> aMask;                                          // [rows][actions]
        std::vector<std::uint32_t> ticket;                                        // [rows] request ids
    };

    struct Stats {
        std::int64_t evals = 0, moves = 0, fights = 0, wins = 0, terminalLeaves = 0, encodeCut = 0;
        std::int64_t batches = 0, batchRows = 0;
        double stepCpu = 0, encodeCpu = 0, searchCpu = 0;   // worker thread-CPU seconds
        double packSeconds = 0;   // wall seconds nextBatchFlat spent packing (after taking the requests)
    };

    class Driver {
    public:
        Driver(std::vector<Root> roots, DriverConfig cfg);
        ~Driver();
        void start();
        void stop();
        // Takes up to maxRows requests (waits until at least minRows are queued or timeoutMs passes; 0 rows after
        // a stop). Thread-safe; several batching threads may call it.
        bool nextBatch(int maxRows, int minRows, int timeoutMs, PackedBatch &out);
        // Flat layout (one token axis per row, padded to a bucketed length; amber_net.AmberNet.forward_flat): takes up
        // to maxRows requests like nextBatch, then picks the smallest row / token / action counts from the bucket lists
        // that hold the batch and writes it into caller buffers sized for the largest buckets. Token order per row is
        // the AmberTokenType segment order; action src / tgt index that token axis (-1 = none). The buffers must start
        // zeroed: dead token slots are not cleared again, so they hold stale but finite values with valid types / ids,
        // and every consumer masks by count (tests/test_amber_net_flat.py checks that their contents never reach an
        // output). Padding rows hold one live token (stale contents) and one live action; their outputs are discarded.
        // packThreads > 1 packs disjoint row ranges in parallel. Returns the tickets (empty after a stop or timeout).
        using FlatBuffers = azbench::FlatBuffers;   // az_pack.h
        using FlatShape = azbench::FlatShape;
        std::vector<std::uint32_t> nextBatchFlat(int maxRows, int minRows, int timeoutMs,
                                                 const std::vector<int> &rowBuckets, const std::vector<int> &tokBuckets,
                                                 const std::vector<int> &actBuckets, const FlatBuffers &buf,
                                                 FlatShape &shape, int sortWindow = 1, int packThreads = 1);
        // Results for rows of a batch from nextBatch: tickets[row] as PackedBatch::ticket, logits[row][action]
        // (row-major, `actions` per row) and value[row].
        void submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *value);
        void submit(const PackedBatch &b, const float *logits, const float *value) {
            submit(b.ticket.data(), b.rows, b.actions, logits, value);
        }
        Stats stats() const;
        const DriverConfig &config() const { return cfg_; }

        struct Game;
        struct Worker;

    private:
        void workerLoop(int w);
        std::vector<std::uint32_t> takeRequests(int maxRows, int minRows, int timeoutMs);
        // sortWindow > 1: takes up to sortWindow * maxRows requests at once, sorts them by token count and hands
        // them out as consecutive batches of maxRows (every request of a window is served before the next window,
        // so none waits longer than one window).
        std::vector<std::uint32_t> takeSorted(int maxRows, int minRows, int timeoutMs, int sortWindow);
        std::mutex cm_;
        std::deque<std::vector<std::uint32_t>> chunks_;
        std::vector<Root> roots_;
        DriverConfig cfg_;
        std::vector<std::unique_ptr<Worker>> workers_;
        std::vector<std::thread> threads_;
        std::atomic<bool> stop_{false};
        mutable std::mutex qm_;
        std::condition_variable qcv_;
        std::deque<std::uint32_t> queue_;   // ticket = worker << 16 | game
        std::atomic<std::int64_t> batches_{0}, batchRows_{0}, packNs_{0};
    };

    // The C++ fake net: random logits and values, for measuring the CPU side without a GPU.
    void fakeNetEvaluate(const PackedBatch &batch, std::vector<float> &logits, std::vector<float> &value,
                         std::uint64_t &rng);

}

#endif
