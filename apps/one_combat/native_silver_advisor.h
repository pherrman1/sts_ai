#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSearcher.h"

namespace sts::search { struct CombatValueNet; }

namespace one_combat::advisor {

struct NativeSilverRootSummary {
    silver_bridge::SemanticAction action;
    std::int64_t edgeVisits = 0;
    bool selectionQValid = false;
    double selectionQ = 0.0;   // mean evaluation of the edge's child
};

struct NativeSilverDecision {
    bool accepted = false;
    std::string failureReason;
    std::int64_t simulations = 0;      // run by this call
    std::int64_t rootVisits = 0;
    silver_bridge::SemanticAction action;
    std::vector<silver_bridge::SemanticAction> legalActions;
    std::vector<NativeSilverRootSummary> rootActionSummaries;
    bool exactReroot = false;
    bool equivalentCopyReroot = false;   // rerooted through another copy of an equivalent card
    std::int64_t inheritedVisits = 0;
    bool fallback = false;
    std::string fallbackReason = "none";
    // End-of-combat samples of every simulation run at this root since it
    // became the root (decide plus later extends); inherited visits excluded.
    // `outcomes.edges` is indexed like rootActionSummaries.
    sts::search::SilverOutcomeCapture outcomes;
    int rootHp = 0;
    int rootMaxHp = 0;
};

// Silver search for the live advisor, run natively on the main engine. One
// session covers one combat: each decision's root is rerooted into the
// retained graph when the previous search reached it.
class NativeSilverAdvisorSession {
public:
    // With `rolloutRootTable` (a combat_policy_mlp model owned by the caller),
    // every decide() builds the ADR-0046 per-root rollout card table at its
    // root; without it the rollouts keep the ADR-0040 table.
    explicit NativeSilverAdvisorSession(const sts::search::CombatValueNet *rolloutRootTable = nullptr);
    ~NativeSilverAdvisorSession();

    // Search `simulations` from the state in `wire`.
    NativeSilverDecision decide(const silver_bridge::BattleStateWire &wire, std::int64_t simulations);
    // Search `additional` more simulations from the current root.
    NativeSilverDecision extend(std::int64_t additional);

    // The retained graph (breadth first from the root, at most `maxNodes`).
    [[nodiscard]] silver_bridge::SilverTreeSnapshot snapshot(std::size_t maxNodes) const;

private:
    std::unique_ptr<sts::search::SilverSearcher> searcher_;
    const sts::search::CombatValueNet *rolloutRootTable_ = nullptr;
    sts::search::SilverSearchContext context_;
    std::int64_t lastInheritedVisits_ = 0;
    bool lastExactReroot_ = false;
    bool lastEquivalentCopyReroot_ = false;
    sts::BattleContext liveRoot_;
    std::string lastFallbackReason_ = "none";
    sts::search::SilverOutcomeCapture outcomes_;

    NativeSilverDecision result(std::int64_t simulations) const;
};

}
