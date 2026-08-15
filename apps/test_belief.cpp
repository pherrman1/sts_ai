#include "test_belief.h"

#include <cmath>
#include <iostream>
#include <random>
#include <vector>

#include "combat/BattleContext.h"
#include "game/Game.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/BattleScumSearcher3.h"

using namespace sts;

namespace {

bool sameDrawOrder(const HiddenBattleState &a, const HiddenBattleState &b) {
    if (a.drawPileOrder.size() != b.drawPileOrder.size()) return false;
    for (size_t i = 0; i < a.drawPileOrder.size(); ++i)
        if (a.drawPileOrder[i].getId() != b.drawPileOrder[i].getId()) return false;
    return true;
}

} // namespace

int testBelief() {
    CombatObservation obs;
    obs.drawPileContents = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};

    Belief b;
    b.particles.resize(2);
    b.particles[0].drawPileOrder = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};
    b.particles[1].drawPileOrder = {CardInstance(CardId::DEFEND_RED), CardInstance(CardId::STRIKE_RED)};
    b.update(obs);
    if (b.particles[0].weight != 1.0 || b.particles[1].weight != 0.0) {
        std::cout << "belief FAIL: contradictory particle not zeroed\n";
        return 1;
    }
    std::mt19937_64 rng(12345);
    for (int i = 0; i < 1000; ++i) {
        const HiddenBattleState &s = b.sample(rng);
        if (sameDrawOrder(s, b.particles[1])) {
            std::cout << "belief FAIL: zero-weight particle sampled\n";
            return 1;
        }
    }

    CombatObservation unobserved;
    unobserved.drawPileContents = {CardInstance(CardId::STRIKE_RED),
                                   CardInstance(CardId::DEFEND_RED),
                                   CardInstance(CardId::STRIKE_RED)};
    Belief u;
    u.particles.resize(2);
    u.particles[0].drawPileOrder = {CardInstance(CardId::STRIKE_RED), CardInstance(CardId::DEFEND_RED)};
    u.particles[1].drawPileOrder = {CardInstance(CardId::DEFEND_RED), CardInstance(CardId::STRIKE_RED)};
    u.update(unobserved);
    if (u.particles[0].weight != 0.0 || u.particles[1].weight != 0.0) {
        std::cout << "belief FAIL: unobservable draw not zeroed\n";
        return 1;
    }
    int seen0 = 0, seen1 = 0;
    for (int i = 0; i < 1000; ++i) {
        const HiddenBattleState &s = u.sample(rng);
        if (sameDrawOrder(s, u.particles[0])) ++seen0;
        else if (sameDrawOrder(s, u.particles[1])) ++seen1;
        else {
            std::cout << "belief FAIL: unknown particle sampled\n";
            return 1;
        }
    }
    if (seen0 == 0 || seen1 == 0) {
        std::cout << "belief FAIL: uniform fallback not uniform\n";
        return 1;
    }
    std::cout << "belief PASS\n";
    return 0;
}

int testBeliefOrderInvariance() {
    int failures = 0;
    CombatObservation obsA, obsB;
    obsA.turn = 1; obsB.turn = 1;
    obsA.ascension = 0; obsB.ascension = 0;
    obsA.drawPileContents = {
        CardInstance(CardId::STRIKE_RED), CardInstance(CardId::BASH), CardInstance(CardId::DEFEND_RED)
    };
    obsB.drawPileContents = {
        CardInstance(CardId::BASH), CardInstance(CardId::DEFEND_RED), CardInstance(CardId::STRIKE_RED)
    };

    if (!(obsA == obsB)) {
        std::cout << "belief_order_invariance FAIL: obsA != obsB\n";
        ++failures;
    }
    if (obsA.visibleHash() != obsB.visibleHash()) {
        std::cout << "belief_order_invariance FAIL: hash differs\n";
        ++failures;
    }

    Belief b1, b2;
    for (int i = 0; i < 4; ++i) {
        HiddenBattleState p;
        p.weight = 1.0;
        p.drawPileOrder = {
            CardInstance(CardId::STRIKE_RED), CardInstance(CardId::BASH), CardInstance(CardId::DEFEND_RED)
        };
        b1.particles.push_back(p);
        b2.particles.push_back(p);
    }
    b1.update(obsA);
    b2.update(obsB);

    for (size_t i = 0; i < b1.particles.size(); ++i) {
        if (std::abs(b1.particles[i].weight - b2.particles[i].weight) > 1e-9) {
            std::cout << "belief_order_invariance FAIL: particle " << i
                      << " weight differs: " << b1.particles[i].weight
                      << " vs " << b2.particles[i].weight << '\n';
            ++failures;
        }
    }

    if (failures == 0) {
        std::cout << "belief_order_invariance PASS\n";
        return 0;
    }
    std::cout << "belief_order_invariance FAIL (" << failures << " checks)\n";
    return 1;
}

int testBeliefImmutability() {
    int failures = 0;
    bool savedBelief = search::g_s3Belief;
    bool savedInternal = search::g_s3InternalBeliefUpdate;
    search::g_s3Belief = true;

    if (savedInternal) {
        std::cout << "belief_immutability FAIL: g_s3InternalBeliefUpdate must default to false (issue #58)\n";
        ++failures;
    }

    {
        search::g_s3InternalBeliefUpdate = false;
        GameContext gc(CharacterClass::IRONCLAD, 0x42, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::BattleScumSearcher3 s3(bc, 0x42, 0, 64);
        std::vector<double> before(s3.belief.particles.size());
        for (size_t i = 0; i < before.size(); ++i) before[i] = s3.belief.particles[i].weight;
        s3.search(200);
        for (size_t i = 0; i < before.size(); ++i) {
            if (std::abs(s3.belief.particles[i].weight - before[i]) > 1e-9) {
                std::cout << "belief_immutability FAIL: particle " << i
                          << " weight changed from " << before[i]
                          << " to " << s3.belief.particles[i].weight << '\n';
                ++failures;
                break;
            }
        }
        int nonzero = 0;
        for (const auto &p : s3.belief.particles) if (p.weight > 0) ++nonzero;
        if (nonzero != 64) {
            std::cout << "belief_immutability FAIL: " << nonzero << "/64 nonzero after search (OFF)\n";
            ++failures;
        }
    }

    {
        search::g_s3InternalBeliefUpdate = true;
        GameContext gc(CharacterClass::IRONCLAD, 0x43, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::BattleScumSearcher3 s3(bc, 0x43, 0, 64);
        std::vector<double> before(s3.belief.particles.size());
        for (size_t i = 0; i < before.size(); ++i) before[i] = s3.belief.particles[i].weight;
        s3.search(200);
        bool anyChanged = false;
        for (size_t i = 0; i < before.size(); ++i) {
            if (std::abs(s3.belief.particles[i].weight - before[i]) > 1e-9) {
                anyChanged = true;
                break;
            }
        }
        if (!anyChanged) {
            std::cout << "belief_immutability FAIL: historical mode did NOT mutate weights\n";
            ++failures;
        }
    }

    {
        search::g_s3InternalBeliefUpdate = false;
        GameContext gc(CharacterClass::IRONCLAD, 0x44, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::CULTIST);
        search::BattleScumSearcher3 a(bc, 0x44, 0, 64);
        search::BattleScumSearcher3 b(bc, 0x44, 0, 64);
        a.search(200);
        b.search(200);
        if (a.root.edges.size() != b.root.edges.size()) {
            std::cout << "belief_immutability FAIL: determinism edge count differs\n";
            ++failures;
        } else {
            for (size_t i = 0; i < a.root.edges.size(); ++i) {
                if (a.root.edges[i].child.simulationCount != b.root.edges[i].child.simulationCount) {
                    std::cout << "belief_immutability FAIL: determinism visit count differs at edge " << i << '\n';
                    ++failures;
                    break;
                }
            }
        }
    }

    search::g_s3Belief = savedBelief;
    search::g_s3InternalBeliefUpdate = savedInternal;
    if (failures == 0) {
        std::cout << "belief_immutability PASS\n";
        return 0;
    }
    std::cout << "belief_immutability FAIL (" << failures << " checks)\n";
    return 1;
}

int testRealBeliefFilter(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::Action action(search::ActionType::END_TURN);

    search::BattleScumSearcher3 s3(bc, seed, 0, 16);
    BattleContext realPost = bc;
    s3.applyParticle(realPost, s3.belief.particles.front());
    if (!action.isValidAction(realPost)) {
        std::cout << "real_belief_filter FAIL: END_TURN fixture invalid\n";
        return 1;
    }
    action.execute(realPost);
    const auto stats = s3.filterRealTransition(bc, action, realPost);
    if (stats.compatible <= 0 || stats.posteriorCollapse
        || s3.belief.positiveCount() != stats.compatible) {
        std::cout << "real_belief_filter FAIL: exact transition did not survive\n";
        return 1;
    }

    search::BattleScumSearcher3 sequential(bc, seed, 0, 16);
    BattleContext sequentialPost = bc;
    sequential.applyParticle(sequentialPost, sequential.belief.particles.front());
    action.execute(sequentialPost);
    sequential.belief.particles[1].weight = 0.0;
    sequential.belief.particles[1].drawPileOrder.clear();
    const auto sequentialStats = sequential.filterRealTransition(bc, action, sequentialPost);
    if (sequentialStats.attempted != 15
        || sequentialStats.drawPileMismatch != 0
        || sequential.belief.particles[1].weight != 0.0) {
        std::cout << "real_belief_filter FAIL: zero-weight particle was reconsidered\n";
        return 1;
    }

    const bool savedFresh = search::g_s3RealBeliefCollapseFresh;
    search::g_s3RealBeliefCollapseFresh = true;
    search::BattleScumSearcher3 nonCollapse(bc, seed, 0, 8);
    BattleContext samePost = bc;
    nonCollapse.applyParticle(samePost, nonCollapse.belief.particles.front());
    action.execute(samePost);
    const auto nonCollapsed = nonCollapse.filterRealTransition(bc, action, samePost);
    if (nonCollapsed.freshBeliefRebuilt || nonCollapsed.posteriorCollapse) {
        std::cout << "real_belief_filter FAIL: fresh fallback ran without collapse\n";
        search::g_s3RealBeliefCollapseFresh = savedFresh;
        return 1;
    }
    search::BattleScumSearcher3 mismatch(bc, seed, 0, 8);
    BattleContext wrong = realPost;
    ++wrong.player.curHp;
    for (size_t i = 0; i < mismatch.belief.particles.size(); ++i)
        mismatch.belief.particles[i].id = 9000 + i;
    const auto collapsed = mismatch.filterRealTransition(bc, action, wrong);
    if (!collapsed.posteriorCollapse || !collapsed.freshBeliefRebuilt
        || mismatch.belief.particles.size() != 8
        || mismatch.belief.positiveCount() != 8) {
        std::cout << "real_belief_filter FAIL: fresh collapse fallback unsafe\n";
        search::g_s3RealBeliefCollapseFresh = savedFresh;
        return 1;
    }
    for (const auto &p : mismatch.belief.particles) {
        if (p.id >= 9000) {
            std::cout << "real_belief_filter FAIL: rejected particle leaked into fresh belief\n";
            search::g_s3RealBeliefCollapseFresh = savedFresh;
            return 1;
        }
    }
    CombatObservation hiddenA = CombatObservation::fromBattleContext(realPost);
    CombatObservation hiddenB = hiddenA;
    if (!(hiddenA == hiddenB)) {
        std::cout << "real_belief_filter FAIL: hidden-equivalent observation rejected\n";
        return 1;
    }
    search::g_s3RealBeliefCollapseFresh = savedFresh;
    std::cout << "real_belief_filter PASS compatible=" << stats.compatible
              << " attempted=" << stats.attempted << "\n";
    return 0;
}

int testPersistentBeliefTransfer(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    search::Action action(search::ActionType::END_TURN);
    search::BattleScumSearcher3 source(bc, seed, 0, 8);
    BattleContext realPost = bc;
    source.applyParticle(realPost, source.belief.particles.front());
    action.execute(realPost);
    source.filterRealTransition(bc, action, realPost);
    source.belief.particles.front().weight = 0.0;

    search::BattleScumSearcher3 fresh(realPost, seed, 1, 8);
    const bool transferred = search::installTransferredBelief(fresh, &source.belief);
    if (fresh.root.simulationCount != 0
        || !transferred
        || fresh.belief.particles.size() != source.belief.particles.size()) {
        std::cout << "persistent_belief_transfer FAIL: fresh tree or particle count changed\n";
        return 1;
    }
    for (size_t i = 0; i < source.belief.particles.size(); ++i) {
        const auto &a = source.belief.particles[i];
        const auto &b = fresh.belief.particles[i];
        if (a.id != b.id || a.weight != b.weight
            || !sameDrawOrder(a, b)) {
            std::cout << "persistent_belief_transfer FAIL: particle identity/weight changed\n";
            return 1;
        }
    }

    int transferredSearches = 0;
    if (transferred && fresh.root.simulationCount == 0) {
        // A forced transition may invalidate this fresh searcher without
        // calling search(); construction alone must not count as consumption.
        search::countTransferredBeliefSearch(false, transferredSearches);
        if (transferredSearches != 0) {
            std::cout << "persistent_belief_transfer FAIL: no-search transfer counted\n";
            return 1;
        }
        search::countTransferredBeliefSearch(true, transferredSearches);
        fresh.search(1);
    }
    if (transferredSearches != 1 || fresh.root.simulationCount == 0) {
        std::cout << "persistent_belief_transfer FAIL: actual search not counted\n";
        return 1;
    }

    search::BattleScumSearcher3 control(realPost, seed, 2, 8);
    if (search::installTransferredBelief(control, nullptr)
        || control.belief.particles.front().weight == 0.0) {
        std::cout << "persistent_belief_transfer FAIL: persistence-off path transferred\n";
        return 1;
    }
    std::cout << "persistent_belief_transfer PASS\n";
    return 0;
}