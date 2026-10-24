#ifndef STS_LIGHTSPEED_OOCPARTICLEPLANNER_H
#define STS_LIGHTSPEED_OOCPARTICLEPLANNER_H

#include <cstdint>
#include <optional>
#include <random>
#include <string>
#include <vector>

#include "sim/search/OocMctsPlanner.h"

namespace sts::search {
// Research planners for the OOC search-architecture pilot (STS_OOC_SEARCH_MODE).
//
// particle (depth == 0): every legal root action is forced once on each of P
// particles and evaluated with the model's own leaf (the same evaluation a
// PUCT root child gets on its first visit). Particle i of every action starts
// from the same transition stream and the same leaf stream (common random
// numbers). The root value is the particle mean; the highest mean is played.
// No visit counts, widening or adaptive allocation.
//
// particle_beam (depth > 0): the root stage is the particle search above. A
// plan is a root action plus, for each of up to `depth` later nontrivial
// decisions, the rank (1..branchK) of the action the model's prior puts first,
// second, ... at that decision. Each particle applies the rank to its own
// state, so a plan is a contingent policy: it reads only what
// legalActions(state) exposes (public candidates and the policy prior), and
// particles diverge only where their states differ. The best `beamWidth`
// plans (particle mean) survive each level; the best final plan's root action
// is played. Hidden state is never read by the planner itself.
struct OocParticleConfig {
    std::uint32_t particles = 64;
    std::uint32_t beamWidth = 8, branchK = 2, depth = 0;
    // Combats the leaf horizon spans after the root edge; combats the beam
    // plays on later explicit edges are subtracted from it (0: no limit on
    // branching, leaves keep the model's own horizon).
    std::uint32_t horizonCombats = 0;
    std::uint64_t seed = 0;
    // Safety cap on single-action steps a particle takes between decisions.
    std::uint32_t maxForcedSteps = 256;
};
struct OocParticleActionStats {
    OocActionId id;
    double prior = 0;
    // Root stage (particle search): mean, standard error and count of particle values.
    double rootMean = 0, rootStdErr = 0;
    std::uint32_t rootParticles = 0;
    std::vector<double> particleValues;   // root stage, particle order
    // Best final-beam plan score with this root action; rootMean when no plan survived.
    double finalScore = 0;
    bool inFinalBeam = false;
    bool pruned = false;
    std::string pruneReason;
    std::uint64_t evaluations = 0;
};
struct OocParticlePlan {
    OocActionId root;
    std::vector<std::uint32_t> ranks;   // 1-based policy rank per expanded level
    double score = 0;
};
struct OocParticleResult {
    std::optional<OocActionId> selectedAction;
    // The root stage's choice: the particle-search (arm B) action on the same particles.
    std::optional<OocActionId> rootStageAction;
    bool aborted = false;
    std::string abortReason;
    std::vector<OocParticleActionStats> actions;   // root action order
    std::vector<OocParticlePlan> finalBeam;        // best first
    std::uint64_t transitions = 0, evaluations = 0, terminalParticles = 0;
    std::uint64_t branchedPlans = 0, droppedPlans = 0;
    std::uint32_t levelsExpanded = 0;
};
class OocParticlePlanner {
public:
    explicit OocParticlePlanner(OocParticleConfig config = {});
    // Root must be a nonterminal, non-boundary decision. Invalid values throw;
    // OocSearchUnsupported prunes the root action (root stage) or drops the
    // plan (beam) whose particle raised it.
    OocParticleResult search(OocGenerativeModel &model, OocStateId root) const;
    // Particle i's streams: its transitions (copied into every root action and
    // plan) and every leaf evaluation (fresh for each evaluation).
    static std::mt19937_64 transitionStream(std::uint64_t seed, std::uint32_t particle);
    static std::mt19937_64 leafStream(std::uint64_t seed, std::uint32_t particle);
private:
    OocParticleConfig config;
};
}
#endif
