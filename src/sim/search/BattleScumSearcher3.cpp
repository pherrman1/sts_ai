//
// BattleScumSearcher3.cpp: ISMCTS searcher with particle determinization
//
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatDistValueNet.h"
#include "sim/search/CombatPVNet.h"
#include "combat/BattleContext.h"

#include <algorithm>
#include <chrono>
#include <cmath>

using namespace sts;

namespace sts::search {

bool g_useSearcher3 = false;
bool g_s3Belief = true;
bool g_s3Prune = true;
bool g_s3Chain = true;
bool g_s3Live = true;
bool g_s3Crn = false;
int g_s3Particles = 64;
double g_riskLambda = 0.5;
bool g_s3Expand = false;
int g_s3ExpandMaxNew = 32;
bool g_s3RolloutPolicy = false;
int g_s3RolloutK = 1;
int g_s3RolloutTurnStop = 0;
bool g_vnetCondBossOnly = false;
bool g_vnetCondAct3 = false;
thread_local std::function<double(const BattleContext &)> g_terminalBonus;
thread_local std::function<void(const S3LeafDiagnostic &)> g_onS3LeafQuery;
thread_local std::function<void(const BattleContext &, int steps)> g_onRolloutStep;

// Phase 6 PVNet deployment-speed knobs (see header; STS_PVNET_* parse in
// apps/one_combat.cpp). The leaf cache is behavior-preserving (deterministic
// given the visible state) and on by default; the COND_* gates are off by
// default, preserving the pre-phase-6 per-expansion blend behavior.
bool g_pvnetCache = true;
int g_pvnetCondMinTurn = 0;
int g_pvnetCondMinDepth = 0;
bool g_pvnetCondBossOnly = false;
extern double g_vnetAlpha;

// ---- Particle application: 6 RNG streams + draw pile order -----------------
static bool sameCardMultiset(const std::vector<CardInstance> &a,
                             const std::vector<CardInstance> &b) {
    if (a.size() != b.size()) return false;
    std::vector<CardId> as, bs;
    as.reserve(a.size()); bs.reserve(b.size());
    for (const auto &c : a) as.push_back(c.getId());
    for (const auto &c : b) bs.push_back(c.getId());
    std::sort(as.begin(), as.end());
    std::sort(bs.begin(), bs.end());
    return as == bs;
}

void BattleScumSearcher3::applyParticle(BattleContext &state,
                                        const HiddenBattleState &particle) {
    state.shuffleRng.seed0    = particle.shuffleRngSeed0;
    state.shuffleRng.seed1    = particle.shuffleRngSeed1;
    state.shuffleRng.counter  = 0;
    state.cardRandomRng.seed0 = particle.cardRandomRngSeed0;
    state.cardRandomRng.seed1 = particle.cardRandomRngSeed1;
    state.cardRandomRng.counter = 0;
    state.aiRng.seed0    = particle.aiRngSeed0;
    state.aiRng.seed1    = particle.aiRngSeed1;
    state.aiRng.counter  = 0;
    state.miscRng.seed0  = particle.miscRngSeed0;
    state.miscRng.seed1  = particle.miscRngSeed1;
    state.miscRng.counter = 0;
    state.monsterHpRng.seed0 = particle.monsterHpRngSeed0;
    state.monsterHpRng.seed1 = particle.monsterHpRngSeed1;
    state.monsterHpRng.counter = 0;
    state.potionRng.seed0   = particle.potionRngSeed0;
    state.potionRng.seed1   = particle.potionRngSeed1;
    state.potionRng.counter = 0;
    // Install the sampled draw order when it still matches the copied pile;
    // stale particles (tree reuse across decisions) fall back to a shuffle.
    if (particle.drawPileOrder.size() == (size_t)state.cards.drawPile.size()
        && sameCardMultiset(particle.drawPileOrder, state.cards.drawPile)) {
        std::copy(particle.drawPileOrder.begin(), particle.drawPileOrder.end(),
                  state.cards.drawPile.begin());
    } else {
        std::shuffle(state.cards.drawPile.begin(), state.cards.drawPile.end(), rng);
    }
}

// ---- Observation caching: compute once per node, reuse on subsequent visits
void BattleScumSearcher3::ensureObservation(Node &node, const BattleContext &state) {
    if (!node.obsCached) {
        node.obs = CombatObservation::fromBattleContext(state);
        node.obsHash = node.obs.visibleHash();
        node.obsCached = true;
    }
}

// ---- Constructor -----------------------------------------------------------
BattleScumSearcher3::BattleScumSearcher3(const BattleContext &bc, int particleCount)
    : BattleScumSearcher3(bc, 0, 0, particleCount) {}

BattleScumSearcher3::BattleScumSearcher3(const BattleContext &bc,
                                         std::uint64_t agentSeed,
                                         int decisionIndex,
                                         int particleCount)
    : rootBc(std::make_unique<const BattleContext>(bc))
    , maxParticles(particleCount)
    , agentSeed(agentSeed)
    , decisionIndex(decisionIndex)
    , riskLambda(g_riskLambda)
    , crnParticleCount(std::min(particleCount, 128))
{
    rootObs = CombatObservation::fromBattleContext(bc);
    root.obs = rootObs;
    root.obsHash = rootObs.visibleHash();
    root.obsCached = true;

    reseed();

    belief = Belief::initial(bc, maxParticles, rng);
    prepareCRNParticles();
}

void BattleScumSearcher3::reseed() {
    // Seed RNG from composite: agentSeed ^ visibleHash ^ decisionIdx.
    // Same agent seed + same observation + same decision index = same search.
    // Different agent seeds / decision indices = different particle samples.
    uint64_t h = root.obsHash;
    h ^= agentSeed + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    h ^= (uint64_t)decisionIndex + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
    rng.seed(h ? h : 1);
}

void BattleScumSearcher3::prepareCRNParticles() {
    crnParticles.resize(crnParticleCount);
    for (auto &p : crnParticles) {
        p.randomize(rng);
        p.drawPileOrder = rootObs.drawPileContents;
        std::shuffle(p.drawPileOrder.begin(), p.drawPileOrder.end(), rng);
    }
}

void BattleScumSearcher3::warmStartRootCRN(const BattleContext &bc) {
    if (root.edges.empty())
        enumerateActionsForNode(root, bc);

    if (crnParticles.empty())
        prepareCRNParticles();

    std::vector<double> scores(root.edges.size(), 0.0);
    std::vector<int> counts(root.edges.size(), 0);

    for (const auto &p : crnParticles) {
        BattleContext state = bc;
        applyParticle(state, p);
        for (size_t i = 0; i < root.edges.size(); ++i) {
            if (!root.edges[i].action.isValidAction(state)) continue;
            BattleContext sc = state;
            root.edges[i].action.execute(sc);
            std::vector<Action> dummy;
            playoutRandom(sc, dummy);
            scores[i] += evaluateLeaf(sc);
            ++counts[i];
        }
    }

    for (size_t i = 0; i < root.edges.size(); ++i) {
        if (counts[i] > 0) {
            root.edges[i].child.evaluationSum = scores[i] / counts[i];
            // Don't increment simulationCount — CRN provides a Q prior
            // without reducing exploration budget.
        }
    }
}

// ---- Search -----------------------------------------------------------------
void BattleScumSearcher3::search(int64_t simulations) {
    if (g_s3Crn && !rootCarried && !crnWarmStarted) { warmStartRootCRN(*rootBc); crnWarmStarted = true; }
    auto t0 = std::chrono::steady_clock::now();
    for (int64_t i = 0; i < simulations; ++i)
        step();
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

void BattleScumSearcher3::searchToTotal(int64_t targetSimulations) {
    if (isTerminal(*rootBc)) { outcomePlayerHp = rootBc->player.curHp; return; }
    if (g_s3Crn && !rootCarried && !crnWarmStarted) { warmStartRootCRN(*rootBc); crnWarmStarted = true; }
    auto t0 = std::chrono::steady_clock::now();
    while (root.simulationCount < targetSimulations)
        step();
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

bool BattleScumSearcher3::advanceRoot(const Action &action,
                                       const BattleContext &newRootState) {
    bool reused = false;
    for (auto &edge : root.edges) {
        if (edge.action == action) {
            root = std::move(edge.child);
            reused = true;
            break;
        }
    }
    if (!reused) root = Node{};
    rootCarried = true;

    rootBc = std::make_unique<const BattleContext>(newRootState);
    rootObs = CombatObservation::fromBattleContext(newRootState);
    root.obs = rootObs;
    root.obsHash = rootObs.visibleHash();
    root.obsCached = true;

    bestActionSequence.clear();
    bestActionValue = std::numeric_limits<double>::min();
    outcomePlayerHp = 0;
    return reused;
}

// ---- Lethal / death detection ----------------------------------------------
// Conservative pruning variant: only prune when the player cannot act.
// Guards against pruning states (PLAYER_NORMAL, CARD_SELECT) where the player
// might still defend; the unguarded equivalent was removed as unsound.
bool BattleScumSearcher3::canPruneAsDead(const BattleContext &bc) {
    if (bc.inputState == InputState::PLAYER_NORMAL) return false;
    if (bc.inputState == InputState::CARD_SELECT) return false;
    if (bc.isCardPlayAllowed()) return false;
    int incDmg = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        if (bc.monsters.arr[i].curHp > 0 && bc.monsters.arr[i].isAttacking()) {
            auto di = bc.monsters.arr[i].getMoveBaseDamage(bc);
            incDmg += bc.monsters.arr[i].calculateDamageToPlayer(bc, di.damage) * di.attackCount;
        }
    }
    return incDmg > 0 && (bc.player.curHp + bc.player.block) < incDmg;
}

bool BattleScumSearcher3::isGuaranteedLethal(const BattleContext &bc) const {
    if (!bc.isCardPlayAllowed()) return false;
    int totalDmg = 0, totalHp = 0;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        const auto &c = bc.cards.hand[i];
        if (c.getType() != CardType::ATTACK || !c.canUseOnAnyTarget(bc)) continue;
        totalDmg += bc.calculateCardDamage(c, 0, 6); // rough estimate
    }
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0) totalHp += bc.monsters.arr[i].curHp;
    return totalDmg > 0 && totalDmg >= totalHp;
}

// V_combat leaf conditioning (STS_VNET_COND_BOSS / STS_VNET_COND_ACT3):
// restricts the learned leaf to the rollout-dominant contexts measured by
// §117 (boss fights, act 3) where the random rollout would otherwise carry
// most of the search mass. Both unset = always on (byte-identical to the
// pre-conditioning vnet behavior).
static bool vnetCondAllowed(const BattleContext &bc) {
    if (g_vnetCondBossOnly && !isBossEncounter(bc.encounter)) return false;
    if (g_vnetCondAct3 && bc.floorNum < 34) return false;
    return true;
}

// ---- ISMCTS step ------------------------------------------------------------
void BattleScumSearcher3::step() {
    ++diag.simulations;
    const auto &particle = belief.sample(rng);

    BattleContext state = *rootBc;
    applyParticle(state, particle);

    std::vector<Node *> path;
    std::vector<Action> actionStack;
    Node *cur = &root;
    int depth = 0;

    while (++depth < maxSearchDepth) {
        path.push_back(cur);
        ensureObservation(*cur, state);
        diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(depth));

        if (isTerminal(state)) {
            ++diag.terminalInsideTree;
            backpropagate(path, evaluateTerminal(state), actionStack);
            return;
        }

        if (g_s3Prune && canPruneAsDead(state)) {
            ++diag.leafDirectEval;
            backpropagate(path, 0.0, actionStack);
            return;
        }

        if (!cur->isExpanded()) {
            enumerateActionsForNode(*cur, state);
            // Priors with either the GBM policy net or the PVNet policy head;
            // computeEdgePriors prefers the PVNet policy head when both exist.
            if ((g_usePolicyNet && g_policyNet.loaded())
                || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly))
                computeEdgePriors(*cur, state);

            if (cur->edges.empty()) {
                ++diag.leafDirectEval;
                backpropagate(path, evaluateLeaf(state, cur->obsHash), actionStack);
                return;
            }

            int selIdx = std::uniform_int_distribution<int>(
                0, (int)cur->edges.size() - 1)(rng);
            auto &edge = cur->edges[selIdx];

            if (!edge.action.isValidAction(state)) {
                ++diag.leafDirectEval;
                backpropagate(path, evaluateLeaf(state, cur->obsHash), actionStack);
                return;
            }

            edge.action.execute(state);
            ++diag.treeActions;
            actionStack.push_back(edge.action);
            path.push_back(&edge.child);
            if (g_s3Belief) belief.update(CombatObservation::fromBattleContext(state));

        if (g_s3Prune && canPruneAsDead(state)) {
                backpropagate(path, 0.0, actionStack);
                return;
            }

            // Deterministic chain compression (2.2): play additional non-drawing
            // cards before rollout, as long as state stays in PLAYER_NORMAL.
            int compSteps = 0;
            if (g_s3Chain) {
                while (compSteps < 10 && state.inputState == InputState::PLAYER_NORMAL
                       && state.outcome == Outcome::UNDECIDED && state.isCardPlayAllowed()) {
                int handBefore = state.cards.cardsInHand;
                bool played = false;
                for (int hi = 0; hi < state.cards.cardsInHand && !played; ++hi) {
                    const auto &c = state.cards.hand[hi];
                    if (!c.canUseOnAnyTarget(state) || c.requiresTarget()) continue;
                    Action a(ActionType::CARD, hi);
                    if (!a.isValidAction(state)) continue;
                    a.execute(state);
                    actionStack.push_back(a);
                    // If hand didn't decrease by exactly 1, something unexpected happened (draw, exhaust, etc.) — stop
                    if (state.cards.cardsInHand != handBefore - 1) { break; }
                    played = true;
                    ++compSteps;
                }
                if (!played) break;
                }
            }

            // Blend: capture leaf value, then rollout, then blend. Phase 6:
            // STS_PVNET_COND_* gates the PVNet leaf here — cheap/easy
            // continuations (early turn, shallow tree, non-boss rooms) use the
            // ordinary rollout only; the NN fires for the long/unresolved
            // continuations where the rollout would otherwise dominate.
            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                && state.outcome == Outcome::UNDECIDED && vnetCondAllowed(state))
                vLeaf = g_combatVNet.predict(state);
            else if (g_usePVNet && g_combatPVNet.loaded()
                     && state.outcome == Outcome::UNDECIDED
                     && pvnetCondAllowed(state, depth))
                vLeaf = g_combatPVNet.leafValue(state, riskLambda);

            double eval = 0.0;
            const int rollSteps = multiRollout(state, actionStack, eval);
            const double rawEval = eval;   // pre-blend rollout outcome (leafdiag snapshot)
            ++diag.rolloutCalls;
            ++diag.rolloutLeafCalls;
            diag.rolloutActions += rollSteps;
            if (g_usePVNet && g_combatPVNet.loaded() && !std::isnan(vLeaf))
                eval = g_pvnetAlpha * vLeaf + (1.0 - g_pvnetAlpha) * eval;
            else if (!std::isnan(vLeaf))
                eval = g_vnetAlpha * vLeaf + (1.0 - g_vnetAlpha) * eval;
            // Leafdiag hook (nullptr by default; the leaf obsHash is computed
            // only when the hook is registered, so unset behavior is
            // unchanged). The leaf identity hash is the state's visibleHash —
            // computed fresh, NOT the parent node's cached obsHash (cur is the
            // expanded parent at this point, its observation predates the
            // committed action + chain compression).
            if (g_onS3LeafQuery) {
                const std::uint64_t leafObsHash =
                    CombatObservation::fromBattleContext(state).visibleHash();
                g_onS3LeafQuery(S3LeafDiagnostic{&state, depth, leafObsHash,
                                                 vLeaf, rawEval, eval});
            }
            backpropagate(path, eval, actionStack);
            return;
        }

        // Internal node
        int selIdx = selectBestEdgePUCT(*cur);
        auto &edge = cur->edges[selIdx];

        if (!edge.action.isValidAction(state)) {
            // Stored edges were enumerated in other determinizations; the chosen
            // action may be illegal in this world. STS_LIVE_VALID (Phase 4):
            // re-select among stored edges valid in THIS particle world (same
            // PUCT scoring) and continue descent; only when none are valid do we
            // fall back to a random rollout (the recorded §117 behavior).
            if (g_liveValid) {
                const int validIdx = selectBestValidEdgePUCT(*cur, state);
                if (validIdx >= 0) {
                    auto &validEdge = cur->edges[validIdx];
                    validEdge.action.execute(state);
                    ++diag.treeActions;
                    actionStack.push_back(validEdge.action);
                    cur = &validEdge.child;
                    if (g_s3Belief) belief.update(CombatObservation::fromBattleContext(state));
                    continue;
                }
                // STS_S3_EXPAND (Phase 6): no stored edge is valid in this
                // particle world. Instead of a random rollout, enumerate the
                // live state's legal actions, add the ones not already stored
                // as new tree edges (priors computed on the new edges only —
                // stored edges may be invalid here, so their action features
                // cannot be filled safely), and descend into the PUCT-best
                // live-valid edge. Action-keyed tree: unchanged from §114's
                // falsified obs-keyed descent. Requires live-valid semantics
                // (g_liveValid); without it this branch is unreachable.
                if (g_s3Expand) {
                    Node live;
                    enumerateActionsForNode(live, state);
                    if (!live.edges.empty()) {
                        std::vector<Action> newActs;
                        newActs.reserve(live.edges.size());
                        for (const auto &le : live.edges) {
                            bool dup = false;
                            for (const auto &se : cur->edges) {
                                if (se.action == le.action) { dup = true; break; }
                            }
                            if (!dup) newActs.push_back(le.action);
                        }
                        if ((int)newActs.size() > g_s3ExpandMaxNew) {
                            std::shuffle(newActs.begin(), newActs.end(), rng);
                            newActs.resize(g_s3ExpandMaxNew);
                        }
                        if (!newActs.empty()) {
                            Node priors;
                            for (const auto &a : newActs)
                                priors.edges.push_back(Edge{a});
                            if ((g_usePolicyNet && g_policyNet.loaded())
                                || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly))
                                computeEdgePriors(priors, state);
                            for (size_t i = 0; i < newActs.size(); ++i)
                                cur->edges.push_back(Edge{newActs[i], Node{}, priors.edges[i].prior});
                            const int newIdx = selectBestValidEdgePUCT(*cur, state);
                            if (newIdx >= 0) {
                                auto &newEdge = cur->edges[newIdx];
                                newEdge.action.execute(state);
                                ++diag.treeActions;
                                actionStack.push_back(newEdge.action);
                                cur = &newEdge.child;
                                if (g_s3Belief) belief.update(CombatObservation::fromBattleContext(state));
                                continue;
                            }
                        }
                    }
                }
            }
            ++diag.rolloutCalls;
            ++diag.fairIllegalStoredEdge;
            double eval = 0.0;
            diag.rolloutActions += multiRollout(state, actionStack, eval);
            backpropagate(path, eval, actionStack);
            return;
        }

        edge.action.execute(state);
        ++diag.treeActions;
        actionStack.push_back(edge.action);
        cur = &edge.child;
        if (g_s3Belief) belief.update(CombatObservation::fromBattleContext(state));

        if (g_s3Prune && canPruneAsDead(state)) {
            ++diag.leafDirectEval;
            backpropagate(path, 0.0, actionStack);
            return;
        }
    }

    // Depth cap: the final child node may never have been visited, so cache
    // its observation before the leaf eval to make the leaf-cache key valid.
    ensureObservation(*cur, state);
    ++diag.leafDirectEval;
    backpropagate(path, evaluateLeaf(state, cur->obsHash), actionStack);
}

// ---- Backpropagation --------------------------------------------------------
void BattleScumSearcher3::backpropagate(const std::vector<Node *> &path,
                                        double evaluation,
                                        const std::vector<Action> &actionStack) {
    if (evaluation > bestActionValue) {
        bestActionSequence = actionStack;
        bestActionValue = evaluation;
    }
    if (evaluation < minActionValue) {
        minActionValue = evaluation;
    }
    for (auto *node : path) {
        ++node->simulationCount;
        node->evaluationSum += evaluation;
        auto &d = node->dist;
        ++d.n;
        d.loQ20 += (evaluation - d.loQ20) * 0.02;
        d.loQ05 += (evaluation - d.loQ05) * 0.01;
    }
}

// ---- PUCT selection (AlphaZero formula: Q + c*P*sqrt(N)/(1+N_child)) -------
int BattleScumSearcher3::selectBestEdgePUCT(const Node &node) {
    const int n = (int)node.edges.size();
    if (n == 1) return 0;

    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
                       || (g_usePVNet && g_combatPVNet.loaded());
    const double logParent  = usePuct ? 0.0 : std::log((double)(node.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt((double)(node.simulationCount + 1)) : 0.0;
    const bool exploit = !bestActionSequence.empty();  // Searcher2 pattern: exploit only after finding a winning line
    const double evalRange = std::max(1.0, bestActionValue - minActionValue);

    int best = 0;
    double bestVal = -1e30;
    for (int i = 0; i < n; ++i) {
        const auto &e = node.edges[i];
        double q = 0.0;
        if (exploit) {
            double avg = e.child.evaluationSum / (e.child.simulationCount + 1);
            if (e.child.dist.n > 3) {
                double dn = e.child.dist.loQ05;
                avg = avg - riskLambda * (avg - dn);
            }
            q = avg / evalRange;
        }
        double explore = usePuct
            ? g_cPuct * e.prior * sqrtParent / (e.child.simulationCount + 1)
            : 3.0 * std::sqrt(2.0) * std::sqrt(logParent / (e.child.simulationCount + 1));
        double val = q + explore;
        if (i == 0 || val > bestVal) { best = i; bestVal = val; }
    }
    return best;
}

// STS_LIVE_VALID (Phase 4): same PUCT scoring as selectBestEdgePUCT, but
// restricted to edges whose action is valid in THIS determinization (particle
// world). Returns the best valid edge index, or -1 when none is valid.
int BattleScumSearcher3::selectBestValidEdgePUCT(const Node &node, const BattleContext &bc) {
    const int n = (int)node.edges.size();
    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
                       || (g_usePVNet && g_combatPVNet.loaded());
    const double logParent  = usePuct ? 0.0 : std::log((double)(node.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt((double)(node.simulationCount + 1)) : 0.0;
    const bool exploit = !bestActionSequence.empty();
    const double evalRange = std::max(1.0, bestActionValue - minActionValue);

    int best = -1;
    double bestVal = -1e30;
    for (int i = 0; i < n; ++i) {
        const auto &e = node.edges[i];
        if (!e.action.isValidAction(bc)) continue;
        double q = 0.0;
        if (exploit) {
            double avg = e.child.evaluationSum / (e.child.simulationCount + 1);
            if (e.child.dist.n > 3) {
                double dn = e.child.dist.loQ05;
                avg = avg - riskLambda * (avg - dn);
            }
            q = avg / evalRange;
        }
        double explore = usePuct
            ? g_cPuct * e.prior * sqrtParent / (e.child.simulationCount + 1)
            : 3.0 * std::sqrt(2.0) * std::sqrt(logParent / (e.child.simulationCount + 1));
        double val = q + explore;
        if (best == -1 || val > bestVal) { best = i; bestVal = val; }
    }
    return best;
}

// ---- Random rollout (attack-biased) -----------------------------------------
static int rolloutWeight(const Action &a, const BattleContext &bc) {
    switch (a.getActionType()) {
        case ActionType::CARD: {
            auto t = bc.cards.hand[a.getSourceIdx()].getType();
            if (t == CardType::ATTACK) return 8;
            if (t == CardType::POWER)  return 3;
            return 2;
        }
        case ActionType::END_TURN: return 1;
        case ActionType::POTION:   return 1;
        default:                   return 2;
    }
}

int BattleScumSearcher3::multiRollout(BattleContext &state,
                                      std::vector<Action> &actionStack,
                                      double &evalOut) {
    const int k = std::max(1, g_s3RolloutK);
    int steps = 0;
    double sum = 0.0;
    std::vector<Action> scratch;
    for (int i = 0; i < k; ++i) {
        // Each rollout starts from the same pre-rollout state (independent
        // copy); the caller's `state` is left unmutated. The first rollout's
        // actions go into actionStack so bestActionSequence stays a valid,
        // replayable line.
        BattleContext sc = state;
        steps += playoutRandom(sc, i == 0 ? actionStack : scratch);
        sum += evaluateLeaf(sc);
    }
    evalOut = sum / k;
    return steps;
}

int BattleScumSearcher3::playoutRandom(BattleContext &state,
                                        std::vector<Action> &actionStack) {
    if ((g_useVNet && g_combatVNet.loaded() && g_vnetAlpha >= 1.0)
        || (g_useDistVNet && g_combatDistVNet.loaded())) return 0;

    Node tmp;
    int steps = 0;
    int turnsCompleted = 0;
    // STS_S3_ROLLOUT_POLICY (opt-in): sample rollout actions from the GBM
    // policy prior (the same distribution PUCT priors come from) instead of
    // the static rolloutWeight heuristic. Restricted to the GBM policy net —
    // a PVNet policy-head forward per rollout step would cost ~14-18x a sim.
    const bool usePrior = g_s3RolloutPolicy
        && g_usePolicyNet && g_policyNet.loaded()
        && !(g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
    while (!isTerminal(state) && steps < 200) {
        ++steps;
        enumerateActionsForNode(tmp, state);
        if (tmp.edges.empty()) break;

        int sel = 0;
        if (usePrior) {
            computeEdgePriors(tmp, state);
            double total = 0;
            for (const auto &e : tmp.edges) total += e.prior;
            double pick = std::uniform_real_distribution<double>(0.0, std::max(total, 1e-12))(rng);
            for (int i = 0; i < (int)tmp.edges.size(); ++i) {
                pick -= tmp.edges[i].prior;
                if (pick < 0) { sel = i; break; }
            }
        } else {
            int total = 0;
            for (const auto &e : tmp.edges) total += rolloutWeight(e.action, state);
            int pick = std::uniform_int_distribution<int>(0, total - 1)(rng);
            for (int i = 0; i < (int)tmp.edges.size(); ++i) {
                pick -= rolloutWeight(tmp.edges[i].action, state);
                if (pick < 0) { sel = i; break; }
            }
        }
        const auto &a = tmp.edges[sel].action;
        if (a.isValidAction(state)) {
            const int turnBefore = state.turn;
            actionStack.push_back(a);
            a.execute(state);
            // rollouttrace diagnostics: consecutive actual-rollout states
            // (read-only hook; nullptr by default).
            if (g_onRolloutStep) g_onRolloutStep(state, steps);
            // STS_S3_ROLLOUT_TURN_STOP (A4): a player turn completed when the
            // action chain ran afterMonsterTurns (bc.turn incremented). Stop
            // after N completed turns; the non-terminal endpoint is then
            // evaluated by the learned leaf (n-step bootstrap).
            if (g_s3RolloutTurnStop > 0 && state.turn != turnBefore
                && ++turnsCompleted >= g_s3RolloutTurnStop)
                break;
        }
        tmp.edges.clear();
    }
    return steps;
}

// ---- Terminal / leaf evaluation ---------------------------------------------
bool BattleScumSearcher3::isTerminal(const BattleContext &bc) const {
    return bc.outcome != Outcome::UNDECIDED;
}

double BattleScumSearcher3::evaluateTerminal(const BattleContext &bc) {
    double v;
    if (g_useDistVNet && g_combatDistVNet.loaded())
        v = g_combatDistVNet.predictFromBC(bc).riskAdjustedValue(
            riskLambda, bc.player.maxHp, g_combatDistVNet.winBonus);
    else
        v = bc.outcome == Outcome::PLAYER_VICTORY ? bc.player.curHp + 50.0 : 0.0;
    // Cross-combat pricing: the integration driver may add a run-level bonus
    // on victory leaves (post-combat HP/gold/potions/relic counters), so the
    // search can weigh e.g. stalling to align the Happy Flower counter.
    if (bc.outcome == Outcome::PLAYER_VICTORY && g_terminalBonus)
        v += g_terminalBonus(bc);
    return v;
}

double BattleScumSearcher3::evaluateLeaf(const BattleContext &bc, std::uint64_t obsHash) {
    if (isTerminal(bc)) return evaluateTerminal(bc);
    if (g_usePVNet && g_combatPVNet.loaded()) {
        // Phase 6: the direct-eval sites (no-legal-action, invalid-edge,
        // depth cap) re-evaluate the same visible state on repeated sims.
        // Cache by the node's obsHash — the transformer forward is the
        // dominant cost and the result is deterministic given the visible
        // state. obsHash == 0 disables caching (post-rollout states are
        // effectively unique).
        if (g_pvnetCache && obsHash != 0) {
            auto it = leafCache.find(obsHash);
            if (it != leafCache.end()) return it->second;
        }
        const double v = g_combatPVNet.leafValue(bc, riskLambda);
        if (g_pvnetCache && obsHash != 0) leafCache.emplace(obsHash, v);
        return v;
    }
    if (g_useDistVNet && g_combatDistVNet.loaded())
        return g_combatDistVNet.predictFromBC(bc).riskAdjustedValue(
            riskLambda, bc.player.maxHp, g_combatDistVNet.winBonus);
    if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha > 0.0
        && vnetCondAllowed(bc))
        return g_combatVNet.predict(bc);
    double hpR = (double)bc.player.curHp / bc.player.maxHp;
    double eR = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0)
            eR += (double)bc.monsters.arr[i].curHp / bc.monsters.arr[i].maxHp;
    eR /= std::max(1, bc.monsters.monstersAlive);
    return 100.0 * (0.7 * hpR + 0.3 * (1.0 - eR));
}

bool BattleScumSearcher3::pvnetCondAllowed(const BattleContext &bc, int depth) const {
    if (g_pvnetCondMinTurn > 0 && bc.turn < g_pvnetCondMinTurn) return false;
    if (g_pvnetCondMinDepth > 0 && depth < g_pvnetCondMinDepth) return false;
    if (g_pvnetCondBossOnly && !isBossEncounter(bc.encounter)) return false;
    return true;
}

// ---- Action enumeration -----------------------------------------------------
void enumerateActionsForNode(BattleScumSearcher3::Node &node,
                             const BattleContext &bc) {
    switch (bc.inputState) {
        case InputState::PLAYER_NORMAL: {
            if (bc.isCardPlayAllowed()) {
                for (int hi = 0; hi < bc.cards.cardsInHand; ++hi) {
                    const auto &c = bc.cards.hand[hi];
                    if (!c.canUseOnAnyTarget(bc)) continue;
                    if (hi > 0) {
                        const auto &p = bc.cards.hand[hi - 1];
                        if (c.getId() == p.getId()
                            && c.getUpgradeCount() == p.getUpgradeCount()
                            && c.costForTurn == p.costForTurn
                            && c.freeToPlayOnce == p.freeToPlayOnce
                            && c.specialData == p.specialData)
                            continue;
                    }
                    if (c.requiresTarget()) {
                        for (int t = bc.monsters.monsterCount - 1; t >= 0; --t)
                            if (bc.monsters.arr[t].isTargetable())
                                node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::CARD, hi, t)});
                    } else {
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::CARD, hi)});
                    }
                }
            }
            for (int p = 0; p < bc.potionCapacity; ++p) {
                if (bc.potions[p] == Potion::EMPTY_POTION_SLOT
                    || bc.potions[p] == Potion::FAIRY_POTION) continue;
                if (!potionRequiresTarget(bc.potions[p])) {
                    node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p)});
                } else {
                    for (int t = 0; t < bc.monsters.monsterCount; ++t)
                        if (bc.monsters.arr[t].isTargetable())
                            node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::POTION, p, t)});
                }
            }
            node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::END_TURN)});
            break;
        }
        case InputState::CARD_SELECT: {
            // Single source of truth: search::Action::enumerateCardSelectActions
            // (the same contract the cardselect_parity test checks against
            // isValidAction).
            for (const auto &a : Action::enumerateCardSelectActions(bc)) {
                node.edges.push_back(BattleScumSearcher3::Edge{a});
            }
            break;
        }
        default:
            break;
    }
}

bool search::BattleScumSearcher3::onlyLegalAction(Action &out) {
    Node tmp;
    enumerateActionsForNode(tmp, *rootBc);
    if (tmp.edges.size() != 1) return false;
    out = tmp.edges[0].action;
    return true;
}

// ---- Policy priors ----------------------------------------------------------
void computeEdgePriors(BattleScumSearcher3::Node &node, const BattleContext &bc) {
    const int n = (int)node.edges.size();
    if (n <= 1) { if (n == 1) node.edges[0].prior = 1.f; return; }

    thread_local std::vector<float> feat, global, actionFeats;
    const int stateN = combatFeatureCount();
    const int actionN = combatPolicyFeatureCount() - stateN;
    if ((int)feat.size() < combatPolicyFeatureCount())
        feat.assign(combatPolicyFeatureCount(), 0.f);
    combatExtractFeatures(bc, feat.data());

    // ── PVNet policy (skipped when value-only so GBM provides priors) ──
    if (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly) {
        const int D = g_combatPVNet.entityDim;
        std::array<float,1766> stateArr{};
        for (int i=0;i<1766;++i) stateArr[i]=feat[i];
        global.resize(D);
        g_combatPVNet.encode(stateArr, global.data());

        const int actionN = combatPolicyFeatureCount() - combatFeatureCount();
        actionFeats.resize(n * actionN);
        for (int i = 0; i < n; ++i)
            combatFillActionFeatures(bc, node.edges[i].action, actionFeats.data() + i*actionN);

        // Score all actions at once
        thread_local std::vector<float> logitsCache;
        logitsCache.resize(n);
        float bestLogit = -1e30f;
        for (int i = 0; i < n; ++i) {
            float logit = g_combatPVNet.policyScore(global.data(), actionFeats.data() + i*actionN);
            if (logit > bestLogit) bestLogit = logit;
            logitsCache[i] = logit;
        }
        // Softmax
        float sum = 0.f;
        for (int i = 0; i < n; ++i) {
            logitsCache[i] = std::exp(logitsCache[i] - bestLogit);
            sum += logitsCache[i];
        }
        float inv = sum > 0.f ? 1.f / sum : 1.f / n;
        for (int i = 0; i < n; ++i)
            node.edges[i].prior = logitsCache[i] * inv;
        return;
    }

    // ── GBM policy (fallback) ──
    float entityState[64];
    if (g_policyNet.isEntityPolicy)
        g_policyNet.encodePolicyStateVec(feat.data(), entityState);

    std::vector<double> logits(n);
    double maxLog = -1e30;
    for (int i = 0; i < n; ++i) {
        combatFillActionFeatures(bc, node.edges[i].action, feat.data() + stateN);
        logits[i] = g_policyNet.isEntityPolicy
            ? g_policyNet.predictPolicyActionVec(feat.data(), entityState)
            : g_policyNet.predictVec(feat.data());
        if (logits[i] > maxLog) maxLog = logits[i];
    }
    double sum = 0;
    for (int i = 0; i < n; ++i) { logits[i] = std::exp(logits[i] - maxLog); sum += logits[i]; }
    double inv = sum > 0 ? 1.0 / sum : 1.0 / n;
    for (int i = 0; i < n; ++i) node.edges[i].prior = (float)(logits[i] * inv);
}

} // namespace sts::search
