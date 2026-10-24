#include "sim/search/OocParticlePlanner.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <random>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace sts::search {
namespace {
double checkedValue(double value) {
    if (!std::isfinite(value) || value < 0 || value > 1)
        throw std::runtime_error("OOC particle value must be finite and in [0,1]");
    return value;
}
std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
constexpr std::uint64_t kTransitionSalt = 0x5452414e53495431ULL;   // "TRANSIT1"
constexpr std::uint64_t kLeafSalt = 0x4c45414653545231ULL;         // "LEAFSTR1"
std::mt19937_64 stream(std::uint64_t base, std::uint64_t salt) {
    std::seed_seq seq{base, salt};
    return std::mt19937_64(seq);
}
struct Particle {
    OocStateId state;
    std::mt19937_64 transitions;
    std::uint64_t base;
    unsigned spentCombats = 0;
    bool pending = false;     // at a nontrivial decision the plan may branch on
    bool stale = true;        // state changed since `value` was computed
    double value = 0;
};
struct Plan {
    OocActionId root;
    double rootPrior;
    std::vector<std::uint32_t> ranks;
    std::vector<Particle> particles;
    double score = 0;
};
struct Search {
    OocGenerativeModel &model;
    const OocParticleConfig &config;
    OocParticleResult result;
    std::map<OocActionId, std::uint64_t> evaluationsByRoot;

    bool horizonReached(const Particle &p) const {
        return config.horizonCombats && p.spentCombats >= config.horizonCombats;
    }
    void step(Particle &p, OocActionId action) {
        p.state = model.sampleSuccessor(p.state, action, p.transitions);
        p.spentCombats += model.edgeCombats(p.state);
        p.stale = true;
        ++result.transitions;
    }
    // Takes single-action steps until a terminal, boundary, horizon or a
    // nontrivial decision; marks the particle pending at the latter.
    void advance(Particle &p) {
        p.pending = false;
        for (std::uint32_t steps = 0;; ++steps) {
            if (model.terminalValue(p.state) || model.isLeafBoundary(p.state) || horizonReached(p)) return;
            const auto actions = model.legalActions(p.state);
            if (actions.empty()) throw std::runtime_error("OOC particle state without actions");
            if (actions.size() > 1) { p.pending = true; return; }
            if (steps >= config.maxForcedSteps)
                throw OocSearchUnsupported("ooc_particle_forced_step_cap_" + std::to_string(config.maxForcedSteps));
            step(p, actions.front().id);
        }
    }
    void evaluate(Particle &p, OocActionId root) {
        if (!p.stale) return;
        if (const auto terminal = model.terminalValue(p.state)) {
            p.value = checkedValue(*terminal);
            ++result.terminalParticles;
        } else {
            auto leaf = stream(p.base, kLeafSalt);
            p.value = checkedValue(model.evaluateLeafAfterCombats(p.state, leaf, p.spentCombats).value);
            ++result.evaluations;
            ++evaluationsByRoot[root];
        }
        p.stale = false;
    }
    static double mean(const std::vector<Particle> &ps) {
        double total = 0;
        for (const auto &p : ps) total += p.value;
        return total / double(ps.size());
    }
    // Rank r (1-based) of a nontrivial decision: prior descending, then ascending ID.
    OocActionId ranked(OocStateId state, std::uint32_t rank) const {
        auto actions = model.legalActions(state);
        std::stable_sort(actions.begin(), actions.end(), [](const auto &a, const auto &b) {
            return a.prior != b.prior ? a.prior > b.prior : a.id < b.id;
        });
        if (rank == 0 || rank > actions.size()) throw std::runtime_error("OOC particle rank out of range");
        return actions[rank - 1].id;
    }
    static bool better(const Plan &a, const Plan &b) {
        if (a.score != b.score) return a.score > b.score;
        if (a.rootPrior != b.rootPrior) return a.rootPrior > b.rootPrior;
        if (a.root != b.root) return a.root < b.root;
        return a.ranks < b.ranks;
    }
};
}

OocParticlePlanner::OocParticlePlanner(OocParticleConfig config) : config(config) {
    if (config.particles == 0) throw std::invalid_argument("OOC particle search requires particles > 0");
    if (config.depth > 0 && (config.beamWidth == 0 || config.branchK == 0))
        throw std::invalid_argument("OOC particle beam requires beamWidth > 0 and branchK > 0");
}
namespace {
std::uint64_t particleBase(std::uint64_t seed, std::uint32_t particle) {
    return mix(seed ^ mix(0x5041525449434c45ULL + particle));   // "PARTICLE"
}
}
std::mt19937_64 OocParticlePlanner::transitionStream(std::uint64_t seed, std::uint32_t particle) {
    return stream(particleBase(seed, particle), kTransitionSalt);
}
std::mt19937_64 OocParticlePlanner::leafStream(std::uint64_t seed, std::uint32_t particle) {
    return stream(particleBase(seed, particle), kLeafSalt);
}
OocParticleResult OocParticlePlanner::search(OocGenerativeModel &model, OocStateId root) const {
    if (model.terminalValue(root) || model.isLeafBoundary(root))
        throw std::invalid_argument("OOC particle search root must be a decision");
    Search s{model, config, {}, {}};
    auto rootActions = model.legalActions(root);
    if (rootActions.empty()) throw std::runtime_error("OOC particle root without actions");
    std::sort(rootActions.begin(), rootActions.end(), [](const auto &a, const auto &b) { return a.id < b.id; });
    std::vector<Particle> origin;
    origin.reserve(config.particles);
    for (std::uint32_t i = 0; i < config.particles; ++i) {
        const auto base = particleBase(config.seed, i);
        origin.push_back({root, stream(base, kTransitionSalt), base});
    }
    // Root stage: every action on the same particles (arm B).
    std::vector<Plan> beam;
    for (const auto &action : rootActions) {
        OocParticleActionStats stats{action.id, action.prior};
        Plan plan{action.id, action.prior, {}, origin};
        try {
            for (auto &p : plan.particles) {
                s.step(p, action.id);
                p.spentCombats = 0;   // the root edge belongs to every arm's horizon
                s.evaluate(p, action.id);
            }
            plan.score = Search::mean(plan.particles);
            double squares = 0;
            for (const auto &p : plan.particles) squares += (p.value - plan.score) * (p.value - plan.score);
            stats.rootMean = stats.finalScore = plan.score;
            stats.rootParticles = config.particles;
            for (const auto &p : plan.particles) stats.particleValues.push_back(p.value);
            stats.rootStdErr = config.particles > 1
                ? std::sqrt(squares / double(config.particles - 1) / double(config.particles)) : 0;
            beam.push_back(std::move(plan));
        } catch (const OocSearchUnsupported &e) {
            stats.pruned = true;
            stats.pruneReason = e.what();
        }
        s.result.actions.push_back(std::move(stats));
    }
    if (beam.empty()) {
        s.result.aborted = true;
        s.result.abortReason = s.result.actions.front().pruneReason;
        return std::move(s.result);
    }
    std::sort(beam.begin(), beam.end(), Search::better);
    s.result.rootStageAction = beam.front().root;
    if (config.depth > 0 && beam.size() > config.beamWidth) beam.resize(config.beamWidth);
    for (std::uint32_t level = 0; level < config.depth; ++level) {
        std::vector<Plan> next;
        bool branched = false;
        for (auto &plan : beam) {
            try {
                bool pending = false;
                for (auto &p : plan.particles) { s.advance(p); pending |= p.pending; }
                // Single-action steps shared by every child are valued once here.
                for (auto &p : plan.particles) if (!p.pending) s.evaluate(p, plan.root);
                if (!pending) {
                    plan.score = Search::mean(plan.particles);
                    next.push_back(std::move(plan));
                    continue;
                }
                std::uint32_t width = 0;
                for (const auto &p : plan.particles)
                    if (p.pending) width = std::max<std::uint32_t>(width, model.legalActions(p.state).size());
                for (std::uint32_t rank = 1; rank <= std::min(config.branchK, width); ++rank) {
                    Plan child{plan.root, plan.rootPrior, plan.ranks, plan.particles};
                    child.ranks.push_back(rank);
                    try {
                        for (auto &p : child.particles) {
                            if (!p.pending) continue;
                            const auto n = model.legalActions(p.state).size();
                            // A particle with fewer actions than the rank keeps its last-ranked one.
                            s.step(p, s.ranked(p.state, std::min<std::uint32_t>(rank, n)));
                            p.pending = false;
                            s.evaluate(p, child.root);
                        }
                        child.score = Search::mean(child.particles);
                        next.push_back(std::move(child));
                        ++s.result.branchedPlans;
                        branched = true;
                    } catch (const OocSearchUnsupported &) { ++s.result.droppedPlans; }
                }
            } catch (const OocSearchUnsupported &) { ++s.result.droppedPlans; }
        }
        if (next.empty()) break;   // every plan dropped: keep the previous beam
        std::sort(next.begin(), next.end(), Search::better);
        if (next.size() > config.beamWidth) next.resize(config.beamWidth);
        beam = std::move(next);
        if (!branched) break;
        ++s.result.levelsExpanded;
    }
    s.result.selectedAction = beam.front().root;
    for (auto &stats : s.result.actions) {
        stats.evaluations = s.evaluationsByRoot[stats.id];
        if (config.depth == 0 || stats.pruned) continue;
        for (const auto &plan : beam)
            if (plan.root == stats.id) { stats.finalScore = plan.score; stats.inFinalBeam = true; break; }
    }
    for (const auto &plan : beam) s.result.finalBeam.push_back({plan.root, plan.ranks, plan.score});
    return std::move(s.result);
}
}
