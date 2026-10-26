// Research-only known-RNG combat search (DESIGN: /mnt/project-files/p300-clairvoyance).
//
// A slim restore of the non-fair path of BattleScumSearcher2 (deleted in
// ADR-0020, last present at e45820fd^): plain UCB MCTS with random rollouts to
// the end of the battle and the original evaluateEndState. The rollout uses
// P300's accepted sampler (END_TURN weight 0.1, half of card draws by expert
// play ordering), without which random rollouts almost never kill the Heart. Every
// simulation runs on a copy of the real BattleContext, including its six RNG
// streams, so the search sees the true draw order, card randomness and
// monster rolls. This is the regime of P300's stage-value tables
// (gamerpuppy ScumSearchAgent2 / BattleScumSearcher2).
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
            double evaluationSum = 0;
            std::vector<Edge> edges;
        };
        struct Edge {
            Action action;
            Node node;
        };

        std::unique_ptr<const BattleContext> rootState;
        Node root;
        double explorationParameter = 3 * std::sqrt(2.0);

        double bestActionValue = std::numeric_limits<double>::min();
        double minActionValue = std::numeric_limits<double>::max();
        int outcomePlayerHp = 0;
        std::vector<Action> bestActionSequence;
        std::default_random_engine randGen;

        KnownRngSearcher(const BattleContext &bc, std::uint64_t plannerSeed);

        // Run this many more simulations from the (possibly reused) root.
        void search(std::int64_t simulations);
        // Re-root onto the child reached by `action`; the new root state is the
        // live battle after the action.
        void advanceRoot(const Action &action, const BattleContext &newRootState);

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

    // Plays the initialized battle `bc` to the end with the persistent known-RNG
    // searcher: simsBase new simulations per decision (x bossMultiplier in boss fights), commit up
    // to 15 actions of the best line found when it survives, else up to 5
    // most-visited actions (the old ScumSearchAgent2 non-fair loop). A battle
    // exceeding 1000 decisions is a loss. Returns the number of decisions.
    int playoutBattleKnownRng(BattleContext &bc, int simsBase, double bossMultiplier, std::uint64_t plannerSeed);

}

#endif //STS_LIGHTSPEED_KNOWNRNGSEARCHER_H
