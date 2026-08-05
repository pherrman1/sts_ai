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
thread_local std::function<double(const BattleContext &)> g_terminalBonus;
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
    for (int64_t i = 0; i < simulations; ++i)
        step();
}

void BattleScumSearcher3::searchToTotal(int64_t targetSimulations) {
    if (isTerminal(*rootBc)) { outcomePlayerHp = rootBc->player.curHp; return; }
    if (g_s3Crn && !rootCarried && !crnWarmStarted) { warmStartRootCRN(*rootBc); crnWarmStarted = true; }
    while (root.simulationCount < targetSimulations)
        step();
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

// ---- ISMCTS step ------------------------------------------------------------
void BattleScumSearcher3::step() {
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

        if (isTerminal(state)) {
            backpropagate(path, evaluateTerminal(state), actionStack);
            return;
        }

        if (g_s3Prune && canPruneAsDead(state)) {
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
                backpropagate(path, evaluateLeaf(state), actionStack);
                return;
            }

            int selIdx = std::uniform_int_distribution<int>(
                0, (int)cur->edges.size() - 1)(rng);
            auto &edge = cur->edges[selIdx];

            if (!edge.action.isValidAction(state)) {
                backpropagate(path, evaluateLeaf(state), actionStack);
                return;
            }

            edge.action.execute(state);
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

            // Blend: capture leaf value, then rollout, then blend
            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                && state.outcome == Outcome::UNDECIDED)
                vLeaf = g_combatVNet.predict(state);
            else if (g_usePVNet && g_combatPVNet.loaded()
                     && state.outcome == Outcome::UNDECIDED)
                vLeaf = g_combatPVNet.leafValue(state, riskLambda);

            playoutRandom(state, actionStack);
            double eval = evaluateLeaf(state);
            if (g_usePVNet && g_combatPVNet.loaded() && !std::isnan(vLeaf))
                eval = g_pvnetAlpha * vLeaf + (1.0 - g_pvnetAlpha) * eval;
            else if (!std::isnan(vLeaf))
                eval = g_vnetAlpha * vLeaf + (1.0 - g_vnetAlpha) * eval;
            backpropagate(path, eval, actionStack);
            return;
        }

        // Internal node
        int selIdx = selectBestEdgePUCT(*cur);
        auto &edge = cur->edges[selIdx];

        if (!edge.action.isValidAction(state)) {
            playoutRandom(state, actionStack);
            backpropagate(path, evaluateLeaf(state), actionStack);
            return;
        }

        edge.action.execute(state);
        actionStack.push_back(edge.action);
        cur = &edge.child;
        if (g_s3Belief) belief.update(CombatObservation::fromBattleContext(state));

        if (g_s3Prune && canPruneAsDead(state)) {
            backpropagate(path, 0.0, actionStack);
            return;
        }
    }

    backpropagate(path, evaluateLeaf(state), actionStack);
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

void BattleScumSearcher3::playoutRandom(BattleContext &state,
                                        std::vector<Action> &actionStack) {
    if ((g_useVNet && g_combatVNet.loaded() && g_vnetAlpha >= 1.0)
        || (g_useDistVNet && g_combatDistVNet.loaded())) return;

    Node tmp;
    int steps = 0;
    while (!isTerminal(state) && steps < 200) {
        ++steps;
        enumerateActionsForNode(tmp, state);
        if (tmp.edges.empty()) break;

        int total = 0;
        for (const auto &e : tmp.edges) total += rolloutWeight(e.action, state);
        int pick = std::uniform_int_distribution<int>(0, total - 1)(rng);
        int sel = 0;
        for (int i = 0; i < (int)tmp.edges.size(); ++i) {
            pick -= rolloutWeight(tmp.edges[i].action, state);
            if (pick < 0) { sel = i; break; }
        }
        const auto &a = tmp.edges[sel].action;
        if (a.isValidAction(state)) {
            actionStack.push_back(a);
            a.execute(state);
        }
        tmp.edges.clear();
    }
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

double BattleScumSearcher3::evaluateLeaf(const BattleContext &bc) {
    if (isTerminal(bc)) return evaluateTerminal(bc);
    if (g_usePVNet && g_combatPVNet.loaded())
        return g_combatPVNet.leafValue(bc, riskLambda);
    if (g_useDistVNet && g_combatDistVNet.loaded())
        return g_combatDistVNet.predictFromBC(bc).riskAdjustedValue(
            riskLambda, bc.player.maxHp, g_combatDistVNet.winBonus);
    if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha > 0.0)
        return g_combatVNet.predict(bc);
    double hpR = (double)bc.player.curHp / bc.player.maxHp;
    double eR = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].curHp > 0)
            eR += (double)bc.monsters.arr[i].curHp / bc.monsters.arr[i].maxHp;
    eR /= std::max(1, bc.monsters.monstersAlive);
    return 100.0 * (0.7 * hpR + 0.3 * (1.0 - eR));
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
            const auto &csi = bc.cardSelectInfo;
            switch (csi.cardSelectTask) {
                case CardSelectTask::ARMAMENTS:
                    for (int i = 0; i < bc.cards.cardsInHand; ++i)
                        if (bc.cards.hand[i].canUpgrade())
                            node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
                    break;
                    break;
                    break;
                    break;
                case CardSelectTask::CODEX:
                    for (int i = 0; i < 4; ++i)
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
                case CardSelectTask::DISCOVERY:
                    for (int i = 0; i < 3; ++i)
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
                case CardSelectTask::EXHAUST_ONE:
                    for (int i = 0; i < bc.cards.cardsInHand; ++i)
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
                case CardSelectTask::EXHUME:
                    for (int i = 0; i < (int)bc.cards.exhaustPile.size(); ++i)
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
                default:
                    for (int i = 0; i < csi.pickCount; ++i)
                        node.edges.push_back(BattleScumSearcher3::Edge{Action(ActionType::SINGLE_CARD_SELECT, i)});
                    break;
            }
            break;
        }
        default:
            break;
    }
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

        actionFeats.resize(n * 14);
        for (int i = 0; i < n; ++i)
            combatFillActionFeatures(bc, node.edges[i].action, actionFeats.data() + i*14);

        // Score all actions at once
        thread_local std::vector<float> logitsCache;
        logitsCache.resize(n);
        float bestLogit = -1e30f;
        for (int i = 0; i < n; ++i) {
            float logit = g_combatPVNet.policyScore(global.data(), actionFeats.data() + i*14);
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
