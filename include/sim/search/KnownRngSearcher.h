// Research-only known-RNG combat search (DESIGN: /mnt/project-files/p300-clairvoyance).
//
// The combat search of P300's stage-value tables (destire-mio/sts-ironclad-agent):
// gamerpuppy's BattleScumSearcher2 / ScumSearchAgent2 non-fair path with P300's
// sim_patch search chain (search_rollout, search_order, search_bounded_loss,
// search_replanning_limit). That means UCB that visits unvisited edges first,
// max backup of the best sampled return, a rollout sampler with END_TURN weight
// 0.1 and half of card draws by expert play ordering, the loss draw/turn bonus
// capped at 20, a fresh searcher per decision and at most 256 replanning rounds.
// Every simulation runs on a copy of the real BattleContext, including its six
// RNG streams, so the search sees the true draw order, card randomness and
// monster rolls.
//
// Results are a separate known-RNG series (ADR-0002) and must never be mixed
// with fair rows. Only `act4replay` with STS_ACT4REPLAY_COMBAT=known uses it.

#ifndef STS_LIGHTSPEED_KNOWNRNGSEARCHER_H
#define STS_LIGHTSPEED_KNOWNRNGSEARCHER_H

#include "combat/BattleContext.h"
#include "sim/search/Action.h"

#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <random>
#include <vector>

namespace sts::search {

    struct KnownRngSearcher {
        struct Edge;
        struct Node {
            std::int64_t simulationCount = 0;
            double evaluationSum = 0;  // best sampled return (max backup), as in P300
            std::vector<Edge> edges;
        };
        struct Edge {
            Action action;
            Node node;
        };

        std::unique_ptr<const BattleContext> rootState;
        Node root;
        double explorationParameter = 3 * std::sqrt(2.0);

        double bestActionValue = std::numeric_limits<double>::lowest();
        double minActionValue = std::numeric_limits<double>::max();
        int outcomePlayerHp = 0;
        std::vector<Action> bestActionSequence;
        std::default_random_engine randGen;

        explicit KnownRngSearcher(const BattleContext &bc);

        void search(std::int64_t simulations);

        static double evaluateEndState(const BattleContext &bc);

    private:
        std::vector<Node *> searchStack;
        std::vector<Action> actionStack;

        void step();
        void updateFromPlayout(const BattleContext &endState);
        int selectBestEdgeToSearch(const Node &cur) const;
        void playoutRandom(BattleContext &state);
        static void enumerateActionsForNode(Node &node, const BattleContext &bc);
    };

    // Plays the initialized battle `bc` to the end: each decision builds a fresh
    // searcher with simsBase simulations (x bossMultiplier in boss fights), then
    // commits up to 15 actions of the best winning line found so far, else up to
    // 5 actions down the most-visited path. After 256 rounds it plays out the
    // cached winning plan or the latest search's best terminal line. A battle that
    // reaches turn 500 is left undecided (invalid row). Returns the rounds used.
    int playoutBattleKnownRng(BattleContext &bc, int simsBase, double bossMultiplier);

}

#endif //STS_LIGHTSPEED_KNOWNRNGSEARCHER_H
