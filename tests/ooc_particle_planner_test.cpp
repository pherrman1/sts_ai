// Offline checks of the OOC particle planners (STS_OOC_SEARCH_MODE=particle and
// particle_beam) on toy generative models: replay, common random numbers, the
// P=1 and beam(1,1) reductions, non-anticipativity, pruning and the horizon.
#include "sim/search/OocParticlePlanner.h"

#include <cmath>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts::search;
namespace {
int checks = 0;
void require(bool ok, const std::string &why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
// Root 0 offers actions 1 and 2. Each successor draws a hidden world w from
// the transition stream; its leaf value is w's fraction plus a fixed action
// bonus, so common random numbers make the root gap exactly the bonus.
struct WorldModel : OocGenerativeModel {
    struct S { std::uint64_t w = 0; OocActionId a = 0; };
    std::vector<S> states{S{}};
    double bonus = 0.01;
    unsigned leafCalls = 0;
    double lastLeaf = -1;
    std::set<OocActionId> unsupported;
    std::optional<double> terminalValue(OocStateId) const override { return std::nullopt; }
    bool isLeafBoundary(OocStateId s) const override { return s != 0; }
    std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{1, 0.7}, {2, 0.3}}; }
    OocStateId sampleSuccessor(OocStateId, OocActionId a, std::mt19937_64 &rng) override {
        if (unsupported.count(a)) throw OocSearchUnsupported("toy_unsupported");
        states.push_back({rng() % 1000, a});
        return states.size() - 1;
    }
    double leafValue(OocStateId) const override { return 0.5; }
    OocLeafEvaluation evaluateLeafWithOutcome(OocStateId s, std::mt19937_64 &rng) override {
        ++leafCalls;
        const double noise = double(rng() % 100) / 1e5;   // the leaf stream is shared across actions too
        lastLeaf = 0.4 * double(states[s].w) / 1000 + noise + (states[s].a == 2 ? bonus : 0);
        return {lastLeaf};
    }
};
// Root 0 (actions 1, 2) -> X: a hidden reward h in {0, 1} is drawn, but X's
// candidates and prior are public and identical for both h. X's action 10 or
// 11 reveals h at Y, whose prior then depends on h. Y's actions end the game.
struct HiddenRewardModel : OocGenerativeModel {
    enum Kind { ROOT, X, Y, END };
    struct S { Kind kind; int hidden = 0; OocActionId taken = 0; };
    std::vector<S> states{S{ROOT}};
    std::map<int, std::set<OocActionId>> takenAtX, takenAtY;   // by hidden reward
    std::optional<double> terminalValue(OocStateId s) const override {
        if (states[s].kind != END) return std::nullopt;
        return states[s].taken == 20 + OocActionId(states[s].hidden) ? 1.0 : 0.0;
    }
    std::vector<OocPlannerAction> legalActions(OocStateId s) const override {
        switch (states[s].kind) {
            case ROOT: return {{1, 0.5}, {2, 0.5}};
            case X: return {{10, 0.6}, {11, 0.4}};   // public: no h here
            case Y: return states[s].hidden ? std::vector<OocPlannerAction>{{20, 0.2}, {21, 0.8}}
                                            : std::vector<OocPlannerAction>{{20, 0.8}, {21, 0.2}};
            case END: break;
        }
        return {};
    }
    OocStateId sampleSuccessor(OocStateId s, OocActionId a, std::mt19937_64 &rng) override {
        const auto from = states[s];
        S next{END, from.hidden, a};
        if (from.kind == ROOT) next = {X, int(rng() % 2), a};
        else if (from.kind == X) { takenAtX[from.hidden].insert(a); next = {Y, from.hidden, a}; }
        else takenAtY[from.hidden].insert(a);
        states.push_back(next);
        return states.size() - 1;
    }
    double leafValue(OocStateId) const override { return 0.5; }
    OocLeafEvaluation evaluateLeafWithOutcome(OocStateId s, std::mt19937_64 &) override {
        return {states[s].kind == Y ? 0.6 : 0.5};
    }
};
// A chain of decisions where every edge resolves one combat: the beam must stop
// branching once the horizon is spent, and the leaf learns the spent combats.
struct CombatChain : OocGenerativeModel {
    std::vector<int> depth{0};
    std::vector<unsigned> spentSeen;
    std::optional<double> terminalValue(OocStateId) const override { return std::nullopt; }
    std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{1, 0.6}, {2, 0.4}}; }
    OocStateId sampleSuccessor(OocStateId s, OocActionId, std::mt19937_64 &) override {
        depth.push_back(depth[s] + 1);
        return depth.size() - 1;
    }
    unsigned edgeCombats(OocStateId) const override { return 1; }
    double leafValue(OocStateId) const override { return 0.5; }
    OocLeafEvaluation evaluateLeafAfterCombats(OocStateId s, std::mt19937_64 &, unsigned spent) override {
        spentSeen.push_back(spent);
        return {0.1 * depth[s]};
    }
};
}

int main() {
    try {
        {
            WorldModel m;
            OocParticleConfig c; c.particles = 64; c.seed = 7;
            const auto r = OocParticlePlanner(c).search(m, 0);
            require(!r.aborted && r.actions.size() == 2 && r.actions[0].rootParticles == 64, "root stage ran");
            require(std::abs((r.actions[1].rootMean - r.actions[0].rootMean) - m.bonus) < 1e-12,
                "common random numbers: particle i sees the same world and leaf stream under every action");
            require(r.selectedAction == 2u && r.rootStageAction == 2u, "highest particle mean is played");
            require(r.evaluations == 128 && r.transitions == 128 && m.leafCalls == 128, "P x |A| evaluations");
            WorldModel again;
            const auto rerun = OocParticlePlanner(c).search(again, 0);
            require(rerun.actions[0].rootMean == r.actions[0].rootMean
                && rerun.actions[1].rootMean == r.actions[1].rootMean
                && rerun.actions[0].rootStdErr == r.actions[0].rootStdErr, "same seed replays exactly");
            c.seed = 8;
            WorldModel other;
            const auto reseeded = OocParticlePlanner(c).search(other, 0);
            require(reseeded.actions[0].rootMean != r.actions[0].rootMean, "another seed draws other worlds");
        }
        {
            // P = 1 is the single continuation: the root mean is that one leaf value.
            for (OocActionId only : {1u, 2u}) {
                WorldModel m;
                m.unsupported = {only == 1 ? 2u : 1u};
                OocParticleConfig c; c.particles = 1; c.seed = 3;
                const auto r = OocParticlePlanner(c).search(m, 0);
                const auto &stats = r.actions[only - 1];
                require(m.leafCalls == 1 && stats.rootMean == m.lastLeaf && stats.rootStdErr == 0,
                    "P=1 equals the single continuation");
                require(r.actions[2 - only].pruned && r.actions[2 - only].pruneReason == "toy_unsupported"
                    && r.selectedAction == only, "an unsupported root action is pruned, not played");
            }
            WorldModel manual, planned;
            OocParticleConfig one; one.particles = 1; one.seed = 5;
            const auto r1 = OocParticlePlanner(one).search(planned, 0);
            for (OocActionId a : {1u, 2u}) {
                auto t = OocParticlePlanner::transitionStream(5, 0);
                const auto next = manual.sampleSuccessor(0, a, t);
                auto leaf = OocParticlePlanner::leafStream(5, 0);
                require(manual.evaluateLeafAfterCombats(next, leaf, 0).value == r1.actions[a - 1].rootMean
                    && r1.actions[a - 1].particleValues.size() == 1, "P=1 replays particle 0's published streams");
            }
            WorldModel none;
            none.unsupported = {1, 2};
            const auto r = OocParticlePlanner(OocParticleConfig{}).search(none, 0);
            require(r.aborted && !r.selectedAction, "a root with every action unsupported aborts");
        }
        {
            // beam(1, 1) keeps the particle search's action and follows rank 1 only.
            for (std::uint64_t seed : {1u, 2u, 3u, 4u}) {
                WorldModel b, c1;
                OocParticleConfig pc; pc.seed = seed; pc.particles = 16;
                const auto particle = OocParticlePlanner(pc).search(b, 0);
                pc.depth = 3; pc.beamWidth = 1; pc.branchK = 1;
                const auto beam = OocParticlePlanner(pc).search(c1, 0);
                require(beam.selectedAction == particle.selectedAction && beam.rootStageAction == particle.selectedAction,
                    "beam(1,1) reduces to the particle choice");
                require(beam.actions[0].rootMean == particle.actions[0].rootMean
                    && beam.actions[1].rootMean == particle.actions[1].rootMean, "beam root stage is the particle stage");
            }
        }
        {
            // Non-anticipativity: equal public histories decide alike; a revealed reward may split them.
            HiddenRewardModel m;
            OocParticleConfig c; c.particles = 32; c.seed = 11; c.depth = 3; c.beamWidth = 1; c.branchK = 1;
            const auto r = OocParticlePlanner(c).search(m, 0);
            require(!r.aborted && m.takenAtX[0].size() == 1 && m.takenAtX[1].size() == 1
                && m.takenAtX[0] == m.takenAtX[1],
                "particles with different hidden rewards but the same public history take the same action");
            require(m.takenAtY[0] == std::set<OocActionId>{20} && m.takenAtY[1] == std::set<OocActionId>{21},
                "after the reward is revealed the particles may diverge");
            require(r.finalBeam.size() == 1 && r.finalBeam[0].ranks == std::vector<std::uint32_t>({1, 1})
                && r.finalBeam[0].score == 1.0, "the contingent plan wins every particle");
            HiddenRewardModel wide;
            c.beamWidth = 8; c.branchK = 2;
            const auto w = OocParticlePlanner(c).search(wide, 0);
            require(wide.takenAtX[0] == std::set<OocActionId>({10, 11}) && wide.takenAtX[0] == wide.takenAtX[1],
                "rank 2 is applied to every particle of its plan");
            require(w.finalBeam.front().score == 1.0 && w.finalBeam.front().ranks.back() == 1
                && w.branchedPlans > 0 && w.levelsExpanded == 2, "the beam ranks plans by particle mean");
        }
        {
            CombatChain m;
            OocParticleConfig c; c.particles = 2; c.depth = 3; c.beamWidth = 8; c.branchK = 2; c.horizonCombats = 2;
            const auto r = OocParticlePlanner(c).search(m, 0);
            require(r.levelsExpanded == 2, "branching stops once the combat horizon is spent");
            unsigned maxSpent = 0;
            for (auto s : m.spentSeen) maxSpent = std::max(maxSpent, s);
            require(maxSpent == 2 && m.spentSeen.front() == 0, "the root edge is free; later combats count");
        }
        bool rejected = false;
        try { OocParticleConfig c; c.particles = 0; OocParticlePlanner p(c); } catch (const std::invalid_argument &) { rejected = true; }
        require(rejected, "zero particles rejected");
    } catch (const std::exception &e) {
        std::cerr << "FAIL ooc_particle_planner: " << e.what() << " (after " << checks << " checks)\n";
        return 1;
    }
    std::cout << "ooc_particle_planner: " << checks << " checks passed\n";
    return 0;
}
