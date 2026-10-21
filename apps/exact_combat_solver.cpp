// Exact expectimax baseline for native Silver on small combats (research tooling).
//
// Built only as the exact_combat_solver target, which compiles the engine with
// -DSTS_EXACT_CHANCE (include/game/ExactChance.h): every chance event of an
// information-set search state (draws from the unknown draw pile, monster move
// rolls, any other RNG draw) is enumerated exactly instead of sampled. Nothing
// here changes any other binary.
//
// For each source seed the tool plays the A20 Ironclad first fight (the seed's
// first Act-1 encounter, starter deck, no Neow bonus) once per config with
// native Silver, on the same battle. At the first searched root it solves the
// whole fight exactly from Silver's own information-set root state (memoized,
// shared by all configs): the optimal expected value of Silver's terminal
// evaluation (SilverSearcher::scoreEndState) over the full game tree. Every
// searched root of every config is then looked up: each legal root action's Q
// value, and the win probability and expected end HP of the optimal
// continuation. One JSON line per searched root, one summary line per config.
//
// usage: exact_combat_solver COUNT START_SEED OUT.jsonl [options]
//   --configs a,b,...  (default prod,live,flatprior:2500,flatprior:10000)
//       prod       learned stop (A20 default), STS_SILVER_ROOT_PRIOR root+tree prior from the environment
//       live       flat 10,000 per root, no prior (the live advisor's search)
//       flat:N     flat N per root, no prior
//       flatprior:N flat N per root, prior from the environment
//   --turn-cap T       an undecided fight past turn T scores as Silver's loss leaf (default 8; dominance
//                      and bounds need T <= 8, where a 1-HP win still beats any loss or cap leaf); every
//                      action reports the probability `capped` of reaching it under optimal play
//   --keep-energy-waste  keep Silver's loss-score energy-waste term (and the counter in the
//                        state key); by default it is dropped, which only changes losing leaves
//   --encounter NAME   force the encounter (CULTIST, JAW_WORM, TWO_LOUSE, SMALL_SLIMES)
//   --max-states N     give up on a fight above N memoized states (default 60,000,000)
//   --objective silver|hp   value optimised by the solver (default silver; hp = end HP, 0 on death)
//   --verify-memo      keep full states and check every memo hit with equalForSearch (slow)
//   --no-canonical-draws  enumerate draw orders too (slow; a check of the canonical-draw probabilities)
//   --no-dominance     solve every end-of-turn state; by default, in fights where it is exact
//                      (dominanceSafe), an end-of-turn state is skipped when another one reachable
//                      from the same state is at least as good in player block and every monster's
//                      HP, block, Vulnerable and Weak, and equal in everything else
//   --no-bounds        no alpha pruning; by default (same fights, no potions) chance and decision
//                      nodes stop once an upper bound shows they cannot beat a sibling; every
//                      reported value stays exact

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "constants/MonsterEncounters.h"
#include "game/ExactChance.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverSearcher.h"

#ifndef STS_EXACT_CHANCE
#error "exact_combat_solver must be compiled with -DSTS_EXACT_CHANCE"
#endif

using json = nlohmann::json;
using namespace sts;
using SAction = sts::search::Action;
using sts::search::SilverSearcher;

namespace {

    struct Infeasible : std::runtime_error { using std::runtime_error::runtime_error; };

    // ---- state key -------------------------------------------------------

    inline std::uint64_t splitmix(std::uint64_t x) {
        x += 0x9E3779B97F4A7C15ULL;
        x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
        x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
        return x ^ (x >> 31);
    }

    struct Key {
        std::uint64_t a = 0, b = 0;
        bool operator==(const Key &o) const { return a == o.a && b == o.b; }
    };
    struct KeyHash { std::size_t operator()(const Key &k) const { return static_cast<std::size_t>(k.a); } };

    struct KeyBuilder {
        std::uint64_t a = 0x243F6A8885A308D3ULL, b = 0x13198A2E03707344ULL;
        // Two cheap order-sensitive streams, mixed fully only in key().
        static std::uint64_t rotl(std::uint64_t x, int r) { return (x << r) | (x >> (64 - r)); }
        void add(std::uint64_t v) {
            a = rotl(a ^ v, 29) * 0x9E3779B97F4A7C15ULL;
            b = rotl(b + v * 0xD6E8FEB86659FD93ULL, 31) * 0xC2B2AE3D27D4EB4FULL + 0x632BE59BD9B4E019ULL;
        }
        void add(std::int64_t v) { add(static_cast<std::uint64_t>(v)); }
        void add(int v) { add(static_cast<std::uint64_t>(static_cast<std::int64_t>(v))); }
        void addCard(const CardInstance &c) {
            add(static_cast<int>(c.id)); add(static_cast<int>(c.uniqueId)); add(static_cast<int>(c.specialData));
            add(static_cast<int>(c.cost)); add(static_cast<int>(c.costForTurn));
            add((c.upgraded ? 1 : 0) | (c.freeToPlayOnce ? 2 : 0) | (c.retain ? 4 : 0));
        }
        template <typename It> void addSorted(It begin, It end) {
            std::vector<CardInstance> v(begin, end);
            std::sort(v.begin(), v.end());
            add(static_cast<int>(v.size()));
            for (const auto &c : v) addCard(c);
        }
        Key key() const { return {splitmix(a ^ rotl(b, 17)), splitmix(b ^ splitmix(a))}; }
    };

    // Status bits implied by the amounts dominance compares (Vulnerable, Weak).
    std::uint64_t monotoneStatusBits(const Monster &) {
        return (1ULL << static_cast<int>(MonsterStatus::VULNERABLE)) | (1ULL << static_cast<int>(MonsterStatus::WEAK));
    }

    bool quiet(const BattleContext &bc) {
        return bc.outcome == Outcome::UNDECIDED && bc.inputState == InputState::PLAYER_NORMAL
            && !bc.endTurnQueued && !bc.turnHasEnded && bc.actionQueue.size == 0 && bc.cardQueue.size == 0;
    }

    // Renumber the unique ids of cards whose ids carry no information (no special
    // data): states equal up to which physical copy sits where get equal ids.
    void canonicalizeIds(BattleContext &bc) {
        auto &cm = bc.cards;
        struct Ref { std::uint64_t cls; int pile; int pos; };
        std::vector<Ref> refs;
        std::vector<std::int16_t> pool;
        auto visit = [&](const CardInstance &c, int pile, int pos) {
            if (c.id == CardId::INVALID || c.usesSpecialData()) return;
            refs.push_back({c.exactChanceClassKey(), pile, pos});
            pool.push_back(c.uniqueId);
        };
        // The hand is a multiset: order its refs by class only (stable on position).
        for (int i = 0; i < cm.cardsInHand; ++i) visit(cm.hand[i], 0, i);
        for (int i = 0; i < cm.drawPile.size(); ++i) visit(cm.drawPile[i], 1, i);
        for (int i = 0; i < static_cast<int>(cm.discardPile.size()); ++i) visit(cm.discardPile[i], 2, i);
        for (int i = 0; i < static_cast<int>(cm.exhaustPile.size()); ++i) visit(cm.exhaustPile[i], 3, i);
        if (refs.empty()) return;
        std::sort(pool.begin(), pool.end());
        std::vector<int> order(refs.size());
        for (std::size_t i = 0; i < refs.size(); ++i) order[i] = static_cast<int>(i);
        std::stable_sort(order.begin(), order.end(), [&](int x, int y) {
            if (refs[x].cls != refs[y].cls) return refs[x].cls < refs[y].cls;
            return refs[x].pile < refs[y].pile;   // positions keep their order within a pile
        });
        std::vector<std::int16_t> assigned(refs.size());
        for (std::size_t r = 0; r < order.size(); ++r) assigned[order[r]] = pool[r];
        std::size_t next = 0;
        auto nextId = [&](const CardInstance &c) -> std::int16_t {
            return (c.id == CardId::INVALID || c.usesSpecialData()) ? c.uniqueId : assigned[next++];
        };
        for (int i = 0; i < cm.cardsInHand; ++i) cm.hand[i].uniqueId = nextId(cm.hand[i]);
        // Draw pile: assign in index order (mutateAll visits in order), then it re-sorts its unknown region.
        std::vector<std::int16_t> drawIds;
        for (int i = 0; i < cm.drawPile.size(); ++i) drawIds.push_back(nextId(cm.drawPile[i]));
        std::size_t d = 0;
        cm.drawPile.mutateAll([&](CardInstance &c) { c.uniqueId = drawIds[d++]; });
        for (auto &c : cm.discardPile) c.uniqueId = nextId(c);
        for (auto &c : cm.exhaustPile) c.uniqueId = nextId(c);
    }

    // `endTurnProjection`: the key of a state about to end its turn with the
    // fields that dominance compares (player block, each monster's HP, block,
    // Vulnerable, Weak, and everything of a dead monster) and the fields the end
    // of the turn forgets (energy, this turn's counters, which cards sit in hand
    // rather than discard) left out. Only used where dominanceSafe() holds.
    // The key builder over everything but the player's current HP, which
    // stateKey() adds last, so the key of the same state at another HP is one
    // add() away (upper bounds from memoized higher-HP twins).
    KeyBuilder statePrefix(const BattleContext &bc, bool endTurnProjection = false) {
        const bool proj = endTurnProjection;
        KeyBuilder k;
        k.add(bc.turn); k.add(static_cast<int>(bc.outcome)); k.add(static_cast<int>(bc.inputState));
        k.add(proj ? 0 : bc.energyWasted); k.add(bc.cardsDrawn); k.add(bc.monsterTurnIdx);
        k.add(static_cast<std::uint64_t>(bc.miscBits.to_ullong()));
        k.add((bc.smokeBombUsed ? 1 : 0) | (bc.skipMonsterTurn ? 2 : 0) | (bc.intentsHidden ? 4 : 0));
        k.add(bc.potionCount); k.add(bc.potionCapacity);
        for (int i = 0; i < bc.potionCapacity; ++i) k.add(static_cast<int>(bc.potions[i]));
        const auto &p = bc.player;
        k.add(p.gold); k.add(p.maxHp); k.add(proj ? 0 : p.energy); k.add(p.energyPerTurn); k.add(p.cardDrawPerTurn);
        k.add(static_cast<int>(p.stance)); k.add(p.orbSlots); k.add(proj ? 0 : p.lastTargetedMonster);
        k.add(proj ? 0 : p.block); k.add(p.artifact); k.add(p.dexterity); k.add(p.focus); k.add(p.strength);
        k.add(static_cast<std::uint64_t>(p.justAppliedBits)); k.add(p.statusBits0); k.add(static_cast<std::uint64_t>(p.statusBits1));
        k.add(static_cast<int>(p.statusMap.size()));
        for (const auto &[s, v] : p.statusMap) { k.add(static_cast<int>(s)); k.add(static_cast<int>(v)); }
        k.add(p.relicBits0); k.add(p.relicBits1);
        for (int v : {int(p.happyFlowerCounter), int(p.incenseBurnerCounter), int(p.inkBottleCounter), int(p.inserterCounter),
                      int(p.nunchakuCounter), int(p.penNibCounter), int(p.sundialCounter), int(p.haveUsedNecronomiconThisTurn),
                      int(p.combustHpLoss), int(p.devaFormEnergyPerTurn), int(p.echoFormCardsDoubled), int(p.panacheCounter),
                      proj ? 0 : int(p.cardsPlayedThisTurn), proj ? 0 : int(p.attacksPlayedThisTurn),
                      proj ? 0 : int(p.skillsPlayedThisTurn),
                      int(p.orangePelletsCardTypesPlayed.to_ulong()), int(p.cardsDiscardedThisTurn),
                      int(p.lastAttackUnblockedDamage), int(p.timesDamagedThisCombat), int(p.bomb1), int(p.bomb2), int(p.bomb3)})
            k.add(v);
        const auto &mg = bc.monsters;
        k.add(proj ? 0 : mg.monstersAlive); k.add(mg.monsterCount);
        k.add(static_cast<int>(mg.extraRollMoveOnTurn.to_ulong())); k.add(static_cast<int>(mg.skipTurn.to_ulong()));
        for (int i = 0; i < mg.monsterCount; ++i) {
            const auto &m = mg.arr[i];
            if (m.pendingMoveRolls != 0 || m.pendingDirectMoveChoice != 0)
                throw std::runtime_error("exact solver: pending hidden monster roll (Runic Dome) unsupported");
            if (proj) {
                k.add(m.idx); k.add(int(m.id));
                if (!m.isAlive()) continue;
                for (int v : {m.maxHp, int(m.isEscapingB), int(m.halfDead), int(m.escapeNext), int(m.moveHistory[0]),
                              int(m.moveHistory[1]), int(m.artifact), int(m.blockReturn), int(m.choked),
                              int(m.corpseExplosion), int(m.lockOn), int(m.mark), int(m.metallicize), int(m.platedArmor),
                              int(m.poison), int(m.regen), int(m.shackled), m.strength, m.uniquePower0,
                              int(m.uniquePower1), m.miscInfo, int(m.occupantGeneration), int(m.latentDamageMask),
                              int(m.latentDamageMaterialized)})
                    k.add(v);
                k.add(m.statusBits & ~monotoneStatusBits(m));
                continue;
            }
            for (int v : {m.idx, int(m.id), m.curHp, m.maxHp, m.block, int(m.isEscapingB), int(m.halfDead), int(m.escapeNext),
                          int(m.moveHistory[0]), int(m.moveHistory[1]), int(m.artifact), int(m.blockReturn), int(m.choked),
                          int(m.corpseExplosion), int(m.lockOn), int(m.mark), int(m.metallicize), int(m.platedArmor),
                          int(m.poison), int(m.regen), int(m.shackled), m.strength, m.vulnerable, m.weak, m.uniquePower0,
                          int(m.uniquePower1), m.miscInfo, int(m.occupantGeneration), int(m.latentDamageMask),
                          int(m.latentDamageMaterialized)})
                k.add(v);
            k.add(m.statusBits);
        }
        const auto &cm = bc.cards;
        if (proj) {
            // End of turn: the hand joins the discard pile (ethereal cards exhaust),
            // so only the union matters; copies are interchangeable by class.
            std::vector<std::uint64_t> leaving, ethereal;
            for (int i = 0; i < cm.cardsInHand; ++i)
                (cm.hand[i].isEthereal() ? ethereal : leaving).push_back(cm.hand[i].exactChanceClassKey());
            for (const auto &c : cm.discardPile) leaving.push_back(c.exactChanceClassKey());
            for (auto *v : {&leaving, &ethereal}) {
                std::sort(v->begin(), v->end());
                k.add(static_cast<int>(v->size()));
                for (auto x : *v) k.add(x);
            }
            k.add(cm.nextUniqueCardId); k.add(cm.strikeCount); k.add(cm.drawPileBloodCardCount);
            k.add(cm.drawPile.size()); k.add(cm.drawPile.knownTop()); k.add(cm.drawPile.knownBottom());
            k.add(cm.drawPile.isConcrete() ? 1 : 0);
            for (const auto &c : cm.drawPile) k.add(c.exactChanceClassKey());
            std::vector<std::uint64_t> ex;
            for (const auto &c : cm.exhaustPile) ex.push_back(c.exactChanceClassKey());
            std::sort(ex.begin(), ex.end());
            for (auto x : ex) k.add(x);
            for (const auto &c : cm.stasisCards) k.addCard(c);
            return k;
        }
        k.add(cm.nextUniqueCardId); k.add(cm.handNormalityCount); k.add(cm.handPainCount); k.add(cm.strikeCount);
        k.add(cm.handBloodCardCount); k.add(cm.drawPileBloodCardCount); k.add(cm.discardPileBloodCardCount);
        k.addSorted(cm.hand.begin(), cm.hand.begin() + cm.cardsInHand);
        k.add(cm.drawPile.size()); k.add(cm.drawPile.knownTop()); k.add(cm.drawPile.knownBottom());
        k.add(cm.drawPile.isConcrete() ? 1 : 0);
        for (const auto &c : cm.drawPile) k.addCard(c);
        k.addSorted(cm.discardPile.begin(), cm.discardPile.end());
        k.addSorted(cm.exhaustPile.begin(), cm.exhaustPile.end());
        for (const auto &c : cm.stasisCards) k.addCard(c);
        return k;
    }

    Key keyAtHp(KeyBuilder k, int hp) {
        k.add(hp);
        return k.key();
    }

    Key stateKey(const BattleContext &bc, bool endTurnProjection = false) {
        return keyAtHp(statePrefix(bc, endTurnProjection), bc.player.curHp);
    }

    // ---- solver ----------------------------------------------------------

    // Research: parameters of ordering heuristic 7 (--order-lambda, --order-vuln).
    double g_orderLambda = 1.0, g_orderVuln = 0.0, g_orderBlockMon = 0.0;

    struct Val {
        double v = 0;     // optimised objective
        double score = 0; // Silver terminal evaluation
        double hp = 0;    // end HP (0 on death), before post-combat heals
        double win = 0;
        double capped = 0; // probability of reaching the turn cap
        // false: a fail-low bound from pruning, v >= the true value and the rest unset.
        bool exact = true;
        // Research (--twin-order): signature of the best end-of-turn candidate of a decision state.
        std::uint32_t sig = 0;
    };

    constexpr double kNoAlpha = -1e300;

    Val bound(double v) {
        Val b;
        b.v = v;
        b.exact = false;
        return b;
    }

    struct Outcome1 { BattleContext state; double p; KeyBuilder pre; bool hasPre; };

    // Open-addressing memo, about 40 bytes per state (an unordered_map node took ~95).
    // A fail-low bound is stored with win = -1.
    class CompactMemo {
        struct Slot { std::uint64_t a = 0, b = 0; double v = 0; float hp = 0, win = 0, capped = 0, score = 0; std::uint32_t sig = 0; };
        std::vector<Slot> slots_;
        std::size_t size_ = 0;
        static bool empty(const Slot &s) { return s.a == 0 && s.b == 0; }
        static Key norm(Key k) { if (k.a == 0 && k.b == 0) k.a = 1; return k; }
        std::size_t probe(const Key &k) const {
            const std::size_t mask = slots_.size() - 1;
            std::size_t i = static_cast<std::size_t>(splitmix(k.a)) & mask;
            while (!empty(slots_[i]) && !(slots_[i].a == k.a && slots_[i].b == k.b)) i = (i + 1) & mask;
            return i;
        }
        void grow() {
            std::vector<Slot> old(slots_.empty() ? 0 : slots_.size());
            old.swap(slots_);
            slots_.assign(old.empty() ? (std::size_t(1) << 20) : old.size() * 2, Slot{});
            for (const auto &s : old) if (!empty(s)) slots_[probe({s.a, s.b})] = s;
        }
    public:
        std::size_t size() const { return size_; }
        void clear() { std::vector<Slot>().swap(slots_); size_ = 0; }
        bool find(Key k, Val &out) const {
            if (slots_.empty()) return false;
            k = norm(k);
            const auto &s = slots_[probe(k)];
            if (empty(s)) return false;
            out.v = s.v; out.hp = s.hp; out.win = s.win; out.capped = s.capped; out.score = s.score;
            out.exact = s.win >= 0;
            out.sig = s.sig;
            return true;
        }
        void emplace(Key k, const Val &v) {
            if ((size_ + 1) * 10 > slots_.size() * 7) grow();
            k = norm(k);
            auto &s = slots_[probe(k)];
            if (empty(s)) ++size_;
            s = {k.a, k.b, v.v, static_cast<float>(v.hp), v.exact ? static_cast<float>(v.win) : -1.0f,
                 static_cast<float>(v.capped), static_cast<float>(v.score), v.sig};
        }
    };

    class ExactSolver {
    public:
        ExactSolver(const BattleContext &battleRoot, const SilverSearcher &live, bool hpObjective,
                    std::int64_t maxStates, bool verify, bool canonicalDraws, bool dropEnergyWaste)
            : scorer_(battleRoot, live.searchContext()), enumerator_(battleRoot, live.searchContext()), rootCopy_(battleRoot),
              hpObjective_(hpObjective), dropEnergyWaste_(dropEnergyWaste), maxStates_(maxStates), verify_(verify) {
            scorer_.evalWeights = live.evalWeights;
            enumerator_.evalWeights = live.evalWeights;
            script_.canonicalDraws = canonicalDraws;
        }

        std::vector<SAction> actions(const BattleContext &s) { return enumerator_.enumerateActions(s); }

        // The exact value of `a` at `s` (alpha = kNoAlpha), or with a higher alpha
        // either the exact value or a fail-low bound <= alpha.
        Val q(const BattleContext &s, const SAction &a, double alpha = kNoAlpha) {
            if (prune_ && quiet(s) && a.getActionType() == search::ActionType::END_TURN) return endValue(s, a, alpha);
            return expand(s, a, alpha);
        }

        // Dominance pruning (see dominanceSafe): set when every mechanic of the
        // fight is monotone in the compared fields.
        bool prune_ = false;
        // Bound pruning: expectimax alpha pruning (Ballard's Star1) with the
        // upper bound of upperBound(). Exact for the reported values; needs the
        // same safety conditions as dominance plus no potions.
        bool bounds_ = false;
        std::int64_t candidates_ = 0, dominated_ = 0, chanceTurns_ = 0, cutoffs_ = 0;

    private:
        // Expected value of `a` at `s` over its exact outcomes; with alpha, stops
        // as soon as the outcomes left cannot lift the expectation above alpha.
        Val expand(const BattleContext &s, const SAction &a, double alpha) {
            const auto replays0 = replays_;
            auto outs = outcomes(s, a);
            double mass = 0;
            for (const auto &o : outs) mass += o.p;
            if (std::abs(mass - 1.0) > 1e-9)
                throw std::runtime_error("exact solver: outcome probabilities sum to " + std::to_string(mass));
            std::vector<double> ub(outs.size(), 0);
            double rest = 0;   // sum of p * upper bound over the outcomes not yet solved
            if (bounds_ && alpha > kNoAlpha) {
                for (std::size_t i = 0; i < outs.size(); ++i) {
                    ub[i] = upperBound(outs[i].state, outs[i].hasPre ? &outs[i].pre : nullptr);
                    rest += outs[i].p * ub[i];
                }
                if (rest <= alpha) {
                    ++cutoffs_;
                    // Research: replays spent on end-of-turn states refuted before any outcome is solved.
                    if (a.getActionType() == search::ActionType::END_TURN) { ++endFirstCuts_; endFirstCutReplays_ += replays_ - replays0; }
                    return bound(rest);
                }
            }
            Val total;
            double acc = 0;
            for (std::size_t i = 0; i < outs.size(); ++i) {
                const auto &o = outs[i];
                double childAlpha = kNoAlpha;
                if (bounds_ && alpha > kNoAlpha) {
                    rest -= o.p * ub[i];
                    childAlpha = (alpha - acc - rest) / o.p;
                }
                const Val v = solve(o.state, childAlpha, o.hasPre ? &o.pre : nullptr);
                if (!v.exact) { ++cutoffs_; return bound(acc + o.p * v.v + rest); }
                acc += o.p * v.v;
                total.v += o.p * v.v; total.score += o.p * v.score; total.hp += o.p * v.hp; total.win += o.p * v.win;
                total.capped += o.p * v.capped;
            }
            return total;
        }

        // An upper bound on the value of `s` under any play: HP never rises
        // during these fights (Burning Blood heals after them, inside the
        // victory score) and a later win only pays more turn penalty, so the
        // win score at the current HP and turn bounds every win; every loss
        // or cap leaf is bounded term by term.
        double upperBound(const BattleContext &s, const KeyBuilder *pre = nullptr) {
            if (s.outcome != Outcome::UNDECIDED) return terminal(s).v;
            // Research (--oracle-pass): the values of a previous full solve as
            // upper bounds, to measure what perfect bounds would save.
            if (oracle_ && oracleBoundsOn_ && quiet(s)) {
                const Key k = pre ? keyAtHp(*pre, s.player.curHp) : stateKey(s);
                if (Val hit; oracle_->find(k, hit)) { ++oracleBounds_; return std::min(hit.v, formulaBound(s)); }
            }
            // The same state at more HP is worth at least as much (see monotone()):
            // a memoized twin a few HP higher, exact or itself a bound, bounds it.
            if (pre && quiet(s) && lipschitz_) {
                const double t = twinUpperBound(*pre, s, 0);
                if (t < 1e299) ++twinBounds_;
                return std::min(t, formulaBound(s));
            }
            if (pre && quiet(s)) {
                const int top = std::min(s.player.maxHp, s.player.curHp + kTwinProbes);
                for (int h = s.player.curHp + 1; h <= top; ++h)
                    if (Val hit; memo_.find(keyAtHp(*pre, h), hit)) { ++twinBounds_; return std::min(hit.v, formulaBound(s)); }
            }
            return formulaBound(s);
        }

    public:
        // Research (--lipschitz, HP objective only): the value is non-decreasing
        // and 1-Lipschitz in player HP. Playing the higher-HP state's policy from
        // the lower one ends every scenario the same way and at most d HP apart
        // (where only the lower one dies, the higher one ends with at most d HP),
        // since in the fights the bounds are gated to HP changes nothing but
        // death and never rises. So every memoized twin
        // d HP below, exact or a fail-low bound, bounds from above with its
        // value + d, as a twin above does with its value; and (--interpolate) two
        // exact twins whose values differ by exactly their HP gap, or not at all,
        // fix the value of every HP between them.
        bool lipschitz_ = false, interpolate_ = false, endTwin_ = false;
        double eps_ = 0;
        std::int64_t interpolations_ = 0, endTwinCutoffs_ = 0, lipschitzTighter_ = 0;
        std::int64_t interpNoLo_ = 0, interpNoHi_ = 0, slopeHist_[7] = {};
        // Research (--intent-bound): ending the turn costs at least the monsters'
        // visible attack less the player's block before the next decision (the
        // gated fights have no end-of-turn block, thorns or damage reduction), so
        // the formula bound at that HP on the next turn bounds an end-of-turn
        // state before its outcomes are replayed. --intent-check replays them
        // anyway and counts outcomes whose bound is above it.
        bool intentBound_ = false, intentCheck_ = false;
        std::int64_t intentCutoffs_ = 0, intentViolations_ = 0, endFirstCuts_ = 0, endFirstCutReplays_ = 0;
    private:
        Key twinKey(const KeyBuilder &pre, int hp, std::uint64_t tag) const {
            Key k = keyAtHp(pre, hp);
            k.b ^= tag;
            return k;
        }

        // The tightest bound the memo's HP twins of `s` give (+inf without one);
        // `tag` selects the end-of-turn entries.
        double twinUpperBound(const KeyBuilder &pre, const BattleContext &s, std::uint64_t tag) {
            double up = 1e300, down = 1e300;
            const int hp = s.player.curHp;
            for (int h = hp + 1; h <= std::min(s.player.maxHp, hp + kTwinProbes); ++h)
                if (Val hit; memo_.find(twinKey(pre, h, tag), hit)) up = std::min(up, hit.v);
            if (lipschitz_)
                for (int h = hp - 1; h >= std::max(1, hp - kTwinProbes); --h)
                    if (Val hit; memo_.find(twinKey(pre, h, tag), hit)) down = std::min(down, hit.v + (hp - h));
            if (down < up) ++lipschitzTighter_;
            return std::min(up, down);
        }

        // The exact value of `s` from two exact twins around it (see lipschitz_).
        bool interpolate(const KeyBuilder &pre, const BattleContext &s, std::uint64_t tag, Val &out) {
            const int hp = s.player.curHp;
            Val lo, hi;
            int dlo = 0, dhi = 0;
            for (int h = hp - 1; h >= std::max(1, hp - kTwinProbes) && !dlo; --h)
                if (Val hit; memo_.find(twinKey(pre, h, tag), hit) && hit.exact) { lo = hit; dlo = hp - h; }
            if (!dlo) { ++interpNoLo_; return false; }
            for (int h = hp + 1; h <= std::min(s.player.maxHp, hp + kTwinProbes) && !dhi; ++h)
                if (Val hit; memo_.find(twinKey(pre, h, tag), hit) && hit.exact) { hi = hit; dhi = h - hp; }
            if (!dhi) { ++interpNoHi_; return false; }
            const double gap = hi.v - lo.v, eps = 1e-9 * (1 + std::abs(hi.v));
            {
                const double slope = gap / (dlo + dhi);
                ++slopeHist_[slope < 0.001 ? 0 : slope < 0.5 ? 1 : slope < 0.9 ? 2 : slope < 0.99 ? 3 : slope < 0.999999 ? 4 : slope <= 1.000001 ? 5 : 6];
            }
            if (std::abs(gap - (dlo + dhi)) <= eps) {
                out = lo;
                out.v = lo.v + dlo;
                out.hp = lo.hp + dlo;
                out.score = lo.score + dlo * lo.win;
            } else if (std::abs(gap) <= eps) {
                out = lo;
            } else {
                return false;
            }
            out.sig = 0;
            ++interpolations_;
            return true;
        }

        double formulaBound(const BattleContext &s) { return formulaBoundAt(s, s.player.curHp, s.turn); }

        // formulaBound() of `s` with its HP and turn replaced (HP <= 0: dead).
        double formulaBoundAt(const BattleContext &s, int hp, int turn) {
            if (hpObjective_) return std::max(hp, 0);
            const auto &ew = scorer_.evalWeights;
            const int turnsLeft = std::max(0, turnCap_ + 1 - turn) + 1;
            const double loss = ew.monsterDamageWeight
                + ew.drawWeight * (s.cardsDrawn + 20.0 * turnsLeft)
                + ew.turnSurvivalWeight * std::max(turn, turnCap_ + 1);
            if (hp <= 0) return loss;
            // The win score depends on nothing that changes within these fights
            // but HP and turn: cache it by those (a state copy per call was the
            // solver's largest cost).
            const std::uint64_t wk = (static_cast<std::uint64_t>(hp) << 32) | static_cast<std::uint32_t>(turn);
            auto it = winScoreCache_.find(wk);
            if (it == winScoreCache_.end()) {
                BattleContext w = s;
                w.player.curHp = hp;
                w.turn = turn;
                w.outcome = Outcome::PLAYER_VICTORY;
                it = winScoreCache_.emplace(wk, scorer_.scoreEndState(w)).first;
            }
            return std::max(it->second, loss);
        }

        // Research (--intent-bound): see intentBound_.
        double intentUpperBound(const BattleContext &s) {
            int incoming = 0;
            for (int m = 0; m < s.monsters.monsterCount; ++m)
                if (s.monsters.arr[m].isAlive()) incoming += s.monsters.arr[m].publicIncomingDamage(s);
            return formulaBoundAt(s, s.player.curHp - std::max(0, incoming - s.player.block), s.turn + 1);
        }

        void checkIntentBound(const BattleContext &s, const SAction &endTurn) {
            const double ub = intentUpperBound(s);
            for (const auto &o : outcomes(s, endTurn)) {
                const BattleContext &n = o.state;
                const double v = n.outcome != Outcome::UNDECIDED || n.turn > turnCap_ ? terminal(n).v : formulaBound(n);
                if (v > ub + 1e-9 || (n.outcome == Outcome::UNDECIDED && n.turn != s.turn + 1)) ++intentViolations_;
            }
        }

    public:
        // Dominance and bounds assume the value never drops when the player has
        // more HP or block or the monsters less HP. Playing the same moves from
        // the better state, every leaf is at least as good except where the
        // worse state dies and the better one wins in the same or a later turn,
        // or reaches the cap, and the better one wins, so it suffices that every
        // win (worst: 1 HP) beats every loss or cap leaf (best: the cap leaf,
        // a loss scored one turn past the cap). Silver pays 1.5 per turn survived
        // and 0.4 less per turn for a win, so this fails for caps above about 8.
        bool monotone() {
            if (hpObjective_) return true;
            const auto &ew = scorer_.evalWeights;
            const int last = turnCap_ + 1;
            // Turns count from 0 and 5 cards are drawn per turn (the starter-deck fights this is gated to).
            const double bestLoss = ew.monsterDamageWeight - ew.aliveWeight
                + ew.drawWeight * 5.0 * (last + 1) + ew.turnSurvivalWeight * last;
            for (int t = 0; t <= turnCap_; ++t) {
                BattleContext w = rootCopy_;
                w.outcome = Outcome::PLAYER_VICTORY;
                w.player.curHp = 1;
                w.turn = t;
                if (scorer_.scoreEndState(w) <= bestLoss) return false;
            }
            return true;
        }
        std::int64_t twinBounds_ = 0;

        // ---- research statistics (--stats) ----------------------------------
        // Per memoized state: its key without player HP, and its "exogenous"
        // key (also without player block and every monster's HP, block,
        // Vulnerable and Weak: what remains is the deck partition, the
        // monsters' AI state and the turn), counted per turn and kind
        // (0 = turn-start/mid-turn decision state, 1 = end-of-turn state).
        bool stats_ = false;
        struct KindStats {
            std::int64_t states = 0;
            std::unordered_map<Key, char, KeyHash> hpFree, exo, turnFree;
        };
        std::map<std::pair<int, int>, KindStats> kindStats_;

        static Key exoKey(const BattleContext &s) {
            BattleContext e = s;
            e.player.curHp = 0;
            e.player.block = 0;
            for (int i = 0; i < e.monsters.monsterCount; ++i) {
                auto &m = e.monsters.arr[i];
                const bool alive = m.isAlive();
                m.curHp = alive ? 1 : 0;
                m.block = 0;
                m.vulnerable = 0;
                m.weak = 0;
                m.statusBits &= ~monotoneStatusBits(m);
            }
            return stateKey(e);
        }

        void noteState(const BattleContext &s, int kind) {
            if (!stats_) return;
            auto &ks = kindStats_[{s.turn, kind}];
            ++ks.states;
            ks.hpFree.emplace(statePrefix(s).key(), 1);
            ks.exo.emplace(exoKey(s), 1);
            BattleContext t = s;
            t.turn = 0;
            kindStats_[{-1, kind}].turnFree.emplace(stateKey(t), 1);
        }

        // The optimal policy's solution graph from `s`: every decision state
        // and end-of-turn state reached under optimal play (argmax over the
        // memoized exact values) and every chance outcome. Its size is the
        // floor for any method that must certify V*(s) exactly.
        struct SolutionStats {
            std::unordered_map<Key, char, KeyHash> decision, endTurn;
            std::map<int, std::int64_t> byTurn;
            std::int64_t inexactTurns = 0, ties = 0;
        };
        void solutionGraph(const BattleContext &s, SolutionStats &st) {
            if (s.outcome != Outcome::UNDECIDED || s.turn > turnCap_) return;
            if (!quiet(s)) {
                ++st.inexactTurns;
                return;
            }
            if (!st.decision.emplace(stateKey(s), 1).second) return;
            ++st.byTurn[s.turn];
            // Follow every line of plays of the turn to its end, as turnValue does.
            struct Cand { BattleContext st; SAction endTurn; };
            std::vector<Cand> cands;
            std::unordered_map<Key, char, KeyHash> seen;
            seen.emplace(stateKey(s), 1);
            std::vector<BattleContext> stack{s};
            double bestLeaf = -1e300;
            while (!stack.empty()) {
                BattleContext n = std::move(stack.back());
                stack.pop_back();
                const auto acts = actions(n);
                if (acts.empty()) { bestLeaf = std::max(bestLeaf, terminal(n).v); continue; }
                for (const auto &a : acts) {
                    if (a.getActionType() == search::ActionType::END_TURN) { cands.push_back({n, a}); continue; }
                    auto outs = outcomes(n, a);
                    if (outs.size() != 1) { ++st.inexactTurns; return; }
                    auto &o = outs[0].state;
                    if (o.outcome != Outcome::UNDECIDED) { bestLeaf = std::max(bestLeaf, terminal(o).v); continue; }
                    if (!quiet(o) || o.turn != s.turn) { ++st.inexactTurns; return; }
                    if (seen.emplace(stateKey(o), 1).second) stack.push_back(std::move(o));
                }
            }
            double best = bestLeaf;
            std::vector<std::size_t> arg;
            for (std::size_t i = 0; i < cands.size(); ++i) {
                Key key = stateKey(cands[i].st);
                key.b ^= 0x5bd1e9955bd1e995ULL;
                Val hit;
                if (!memo_.find(key, hit) || !hit.exact) continue;
                if (hit.v > best + 1e-9) { best = hit.v; arg.assign(1, i); }
                else if (hit.v >= best - 1e-9) arg.push_back(i);
            }
            if (arg.size() > 1) ++st.ties;
            if (arg.empty()) return;   // the best line wins the fight this turn
            const auto &c = cands[arg[0]];
            Key ekey = stateKey(c.st);
            if (!st.endTurn.emplace(ekey, 1).second) return;
            for (const auto &o : outcomes(c.st, c.endTurn)) solutionGraph(o.state, st);
        }

        // The union of the solution graphs below every root action: the floor
        // for certifying every root Q value exactly.
        void solutionGraphForActions(const BattleContext &root, const std::vector<SAction> &acts, SolutionStats &st) {
            for (const auto &a : acts) {
                if (a.getActionType() == search::ActionType::END_TURN) {
                    if (!st.endTurn.emplace(stateKey(root), 1).second) continue;
                    for (const auto &o : outcomes(root, a)) solutionGraph(o.state, st);
                } else {
                    for (const auto &o : outcomes(root, a)) solutionGraph(o.state, st);
                }
            }
        }

        json statsJson() const {
            json rows = json::array();
            for (const auto &[tk, ks] : kindStats_)
                rows.push_back({{"turn", tk.first}, {"kind", tk.second == 0 ? "decision" : "endTurn"},
                                {"states", ks.states}, {"hpFree", ks.hpFree.size()}, {"exo", ks.exo.size()},
                                {"turnFree", ks.turnFree.size()}});
            return rows;
        }

    private:
        static constexpr int kTwinProbes = 12;

    public:
        std::size_t states() const { return memo_.size(); }
        const CompactMemo &memo() const { return memo_; }
        // Research: candidate-ordering heuristics (higher key = tried first).
        static constexpr int kHeuristics = 7;
        std::int64_t diagTotal_ = 0, diagHits_[kHeuristics] = {};
        std::int64_t marginHist_[7] = {}, slackHist_[7] = {}, oneTurnRefutes_ = 0;
        bool orderDiag_ = false;
        int orderHeuristic_ = -1;
        static double heuristicKey(const BattleContext &y, int h) {
            int incoming = 0, monsterHp = 0, monsterBlock = 0, vuln = 0;
            for (int i = 0; i < y.monsters.monsterCount; ++i) {
                const auto &m = y.monsters.arr[i];
                if (!m.isAlive()) continue;
                incoming += m.publicIncomingDamage(y);
                monsterHp += m.curHp;
                monsterBlock += m.block;
                vuln += std::min(m.vulnerable, 2);
            }
            const double hpAfter = y.player.curHp - std::max(0, incoming - y.player.block);
            switch (h) {
                case 0: return -1000.0 * (monsterHp + monsterBlock) + y.player.block;   // the solver's default
                case 1: return 1000.0 * hpAfter - monsterHp;
                case 2: return hpAfter - 0.3 * monsterHp;
                case 3: return hpAfter - 0.6 * monsterHp;
                case 4: return hpAfter - 1.0 * monsterHp;
                case 5: return hpAfter - 0.6 * monsterHp + 1.5 * vuln;
                case 6: return hpAfter - 0.45 * monsterHp + 1.0 * vuln;
                default: return hpAfter - g_orderLambda * monsterHp + g_orderVuln * vuln - g_orderBlockMon * monsterBlock;
            }
        }
        bool twinOrder_ = false;
        std::int64_t hashMoveHits_ = 0;
        static std::uint32_t sigOf(const BattleContext &y) { return static_cast<std::uint32_t>(statePrefix(y).key().a) | 1u; }
        const CompactMemo *oracle_ = nullptr;
        bool oracleBoundsOn_ = true, oracleOrder_ = false;
        std::int64_t oracleBounds_ = 0;
        // Drop every memoized state (after an infeasible solve) to free memory.
        void clear() { memo_.clear(); inProgress_.clear(); }
        std::int64_t replays() const { return replays_; }
        std::int64_t verifiedHits() const { return verifiedHits_; }

    private:
        SilverSearcher scorer_;
        SilverSearcher enumerator_;
        BattleContext rootCopy_;
        bool hpObjective_;
        bool dropEnergyWaste_;
    public:
        int turnCap_ = 25;
    private:
        std::int64_t maxStates_;
        bool verify_;
        exact::ChanceScript script_;
        CompactMemo memo_;
        std::unordered_map<Key, int, KeyHash> inProgress_;
        std::unordered_map<Key, std::unique_ptr<BattleContext>, KeyHash> verifyStates_;
        std::int64_t replays_ = 0;
        std::unordered_map<std::uint64_t, double> winScoreCache_;
    public:
        std::int64_t endCalls_ = 0, endReplays_ = 0, endDead_ = 0, endOutcomes_ = 0, cardCalls_ = 0, cardReplays_ = 0;
        std::map<int, std::int64_t> statesByTurn_;
    private:
        std::int64_t verifiedHits_ = 0;

        Val terminal(const BattleContext &s) {
            Val v;
            v.score = scorer_.scoreEndState(s);
            v.win = s.outcome == Outcome::PLAYER_VICTORY ? 1 : 0;
            v.hp = v.win ? s.player.curHp : 0;
            v.v = hpObjective_ ? v.hp : v.score;
            return v;
        }

        void checkSame(const Key &key, const BattleContext &s) {
            if (!verify_) return;
            auto it = verifyStates_.find(key);
            if (it == verifyStates_.end()) {
                verifyStates_.emplace(key, std::make_unique<BattleContext>(s));
                return;
            }
            const auto &o = *it->second;
            if (!o.equalForSearch(s) || o.energyWasted != s.energyWasted || o.cardsDrawn != s.cardsDrawn)
                throw std::runtime_error("exact solver: memo key collision between unequal states");
            ++verifiedHits_;
        }

        void remember(const Key &key, const Val &v) {
            memo_.emplace(key, v);
            if (memo_.size() % 100000 == 0)
                std::cerr << "  states=" << memo_.size() << " replays=" << replays_ << " cutoffs=" << cutoffs_
                          << " dominated=" << dominated_ << '/' << candidates_ << '\n';
            if (static_cast<std::int64_t>(memo_.size()) > maxStates_)
                throw Infeasible("more than " + std::to_string(maxStates_) + " states");
        }

        // A memo entry answers a query when it is exact, or a bound at or below alpha.
        static bool answers(const Val &hit, double alpha) { return hit.exact || hit.v <= alpha; }

        Val solve(const BattleContext &s, double alpha = kNoAlpha, const KeyBuilder *knownPre = nullptr) {
            if (s.outcome != Outcome::UNDECIDED) return terminal(s);
            if (s.turn > turnCap_) {
                // Horizon: an undecided fight past the cap scores like a loss leaf
                // (Silver's unresolved-playout evaluation); `capped` reports how
                // much probability reaches it.
                Val v = terminal(s);
                v.capped = 1;
                return v;
            }
            const bool memoize = quiet(s);
            Key key;
            KeyBuilder pre;
            if (memoize) {
                pre = knownPre ? *knownPre : statePrefix(s);
                key = keyAtHp(pre, s.player.curHp);
                checkSame(key, s);
                if (Val hit; memo_.find(key, hit) && answers(hit, alpha)) return hit;
                if (Val iv; interpolate_ && interpolate(pre, s, 0, iv)) {
                    remember(key, iv);
                    return iv;
                }
            }
            if (bounds_ && alpha > kNoAlpha) {
                const double ub = upperBound(s, memoize ? &pre : nullptr);
                if (ub <= alpha) { ++cutoffs_; return bound(ub); }
            }
            if (memoize) {
                if (inProgress_.count(key)) throw std::runtime_error("exact solver: cycle in the game graph");
                inProgress_[key] = 1;
            }
            Val best;
            if (!prune_ || !memoize || !turnValue(s, alpha, best)) {
                const auto acts = actions(s);
                if (acts.empty()) {
                    best = terminal(s);
                } else {
                    best = maxOver(acts.size(), alpha, [&](std::size_t i, double a) { return q(s, acts[i], a); });
                }
            }
            if (memoize) {
                inProgress_.erase(key);
                ++statesByTurn_[s.turn];
                noteState(s, 0);
                remember(key, best);
            }
            return best;
        }

        // max over n children: each child is queried with alpha raised to the best
        // exact value so far; the result is exact when it beats alpha, else a
        // fail-low bound (the largest child value or bound).
        template <typename F>
        Val maxOver(std::size_t n, double alpha, F child, Val best = bound(kNoAlpha)) {
            double ceiling = best.v;
            for (std::size_t i = 0; i < n; ++i) {
                // Research (--epsilon): a child only has to beat the best so far by eps_, so the
                // result can be up to eps_ below the true maximum (errors add up along a line).
                const double a = bounds_ ? std::max(alpha, best.exact ? best.v + eps_ : kNoAlpha) : kNoAlpha;
                const Val v = child(i, a);
                ceiling = std::max(ceiling, v.v);
                if (v.exact && (!best.exact || v.v > best.v)) best = v;
            }
            // A bound above the best exact value is <= its query's alpha, which is then alpha itself
            // (up to rounding: a child's bound can land a few ulps above the alpha it was given).
            if (best.exact && best.v >= ceiling - eps_ - 1e-9) return best;
            return bound(ceiling);
        }

        // The value of ending the turn at `s`, memoized under its own tag.
        Val endValue(const BattleContext &s, const SAction &endTurn, double alpha) {
            Key key = stateKey(s);
            key.b ^= 0x5bd1e9955bd1e995ULL;
            if (Val hit; memo_.find(key, hit) && answers(hit, alpha)) return hit;
            if (interpolate_ || (endTwin_ && bounds_ && alpha > kNoAlpha)) {
                const KeyBuilder pre = statePrefix(s);
                if (Val iv; interpolate_ && interpolate(pre, s, 0x5bd1e9955bd1e995ULL, iv)) {
                    remember(key, iv);
                    return iv;
                }
                if (endTwin_ && bounds_ && alpha > kNoAlpha) {
                    const double ub = twinUpperBound(pre, s, 0x5bd1e9955bd1e995ULL);
                    if (ub <= alpha) { ++cutoffs_; ++endTwinCutoffs_; return bound(ub); }
                }
            }
            if (Val hit; bounds_ && oracle_ && oracleBoundsOn_ && alpha > kNoAlpha && oracle_->find(key, hit) && hit.v <= alpha) {
                ++oracleBounds_;
                ++cutoffs_;
                return bound(hit.v);
            }
            if (intentCheck_) checkIntentBound(s, endTurn);
            if (intentBound_ && alpha > kNoAlpha) {
                if (const double ub = intentUpperBound(s); ub <= alpha) {
                    ++cutoffs_;
                    ++intentCutoffs_;
                    noteState(s, 1);
                    remember(key, bound(ub));
                    return bound(ub);
                }
            }
            const Val v = expand(s, endTurn, alpha);
            noteState(s, 1);
            remember(key, v);
            return v;
        }

        // The rest of the turn from `s` when the turn has no chance event: every
        // line of plays is followed to its end (a won fight, or a state that ends
        // the turn); a state that ends the turn is dropped when another one in the
        // same reachable set is at least as good in every compared field and equal
        // in the rest (the projection key), and only the survivors are solved.
        // Returns false (and leaves `out` alone) when the turn has a chance event
        // or a non-quiet intermediate state, so the caller falls back to plain
        // expectimax.
        bool turnValue(const BattleContext &s, double alpha, Val &out) {
            struct Cand { BattleContext st; SAction endTurn; Key proj; };
            std::vector<Cand> cands;
            Val best = bound(kNoAlpha);
            std::unordered_map<Key, char, KeyHash> seen;
            seen.emplace(stateKey(s), 1);
            bool plain = true;
            std::vector<BattleContext> stack{s};
            auto leaf = [&](const BattleContext &t) {
                const Val v = terminal(t);
                if (!best.exact || v.v > best.v) best = v;
            };
            while (!stack.empty() && plain) {
                BattleContext n = std::move(stack.back());
                stack.pop_back();
                const auto acts = actions(n);
                if (acts.empty()) { leaf(n); continue; }
                for (const auto &a : acts) {
                    if (a.getActionType() == search::ActionType::END_TURN) {
                        cands.push_back({n, a, stateKey(n, true)});
                        continue;
                    }
                    auto outs = outcomes(n, a);
                    if (outs.size() != 1) { plain = false; break; }
                    auto &o = outs[0].state;
                    if (o.outcome != Outcome::UNDECIDED) { leaf(o); continue; }
                    if (!quiet(o) || o.turn != s.turn) { plain = false; break; }
                    if (seen.emplace(stateKey(o), 1).second) stack.push_back(std::move(o));
                }
            }
            if (!plain) { ++chanceTurns_; return false; }
            // a is at least as good as b in every compared field.
            auto covers = [](const BattleContext &a, const BattleContext &b) {
                if (a.player.block < b.player.block) return false;
                for (int i = 0; i < a.monsters.monsterCount; ++i) {
                    const auto &ma = a.monsters.arr[i], &mb = b.monsters.arr[i];
                    if (!ma.isAlive()) continue;
                    if (ma.curHp > mb.curHp || ma.block > mb.block || ma.vulnerable < mb.vulnerable || ma.weak < mb.weak)
                        return false;
                }
                return true;
            };
            std::unordered_map<Key, std::vector<std::size_t>, KeyHash> groups;
            for (std::size_t i = 0; i < cands.size(); ++i) groups[cands[i].proj].push_back(i);
            candidates_ += static_cast<std::int64_t>(cands.size());
            std::vector<std::size_t> survivors;
            for (const auto &[proj, members] : groups) {
                for (std::size_t x = 0; x < members.size(); ++x) {
                    const auto &c = cands[members[x]];
                    bool beaten = false;
                    for (std::size_t y = 0; y < members.size() && !beaten; ++y) {
                        if (x == y) continue;
                        const auto &d = cands[members[y]].st;
                        // Equal candidates: keep the first.
                        beaten = covers(d, c.st) && (!covers(c.st, d) || y < x);
                    }
                    if (beaten) ++dominated_;
                    else survivors.push_back(members[x]);
                }
            }
            // Likely-best first, so alpha rises early: least monster HP left, then most block.
            auto order = [&](std::size_t i) {
                const auto &st = cands[i].st;
                int hp = 0;
                for (int m = 0; m < st.monsters.monsterCount; ++m)
                    if (st.monsters.arr[m].isAlive()) hp += st.monsters.arr[m].curHp + st.monsters.arr[m].block;
                return std::pair<int, int>(hp, -st.player.block);
            };
            if (oracle_ && orderDiag_ && survivors.size() >= 2) {
                // Research: how often each ordering heuristic puts an optimal candidate first.
                std::vector<double> ov(cands.size(), -1e300);
                double best = -1e300;
                for (std::size_t i : survivors) {
                    Key k = stateKey(cands[i].st);
                    k.b ^= 0x5bd1e9955bd1e995ULL;
                    if (Val hit; oracle_->find(k, hit) && hit.exact) ov[i] = hit.v;
                    best = std::max(best, ov[i]);
                }
                if (best > -1e299) {
                    // Margins of the other candidates below the best, and the slack of a
                    // one-turn bound (win score at the HP left after this turn's attack).
                    for (std::size_t i : survivors) {
                        if (ov[i] <= -1e299 || ov[i] >= best - 1e-9) continue;
                        const double margin = best - ov[i];
                        int bucket = margin < 0.5 ? 0 : margin < 1 ? 1 : margin < 2 ? 2 : margin < 4 ? 3 : margin < 8 ? 4 : margin < 16 ? 5 : 6;
                        ++marginHist_[bucket];
                        int incoming = 0;
                        for (int m = 0; m < cands[i].st.monsters.monsterCount; ++m)
                            if (cands[i].st.monsters.arr[m].isAlive()) incoming += cands[i].st.monsters.arr[m].publicIncomingDamage(cands[i].st);
                        BattleContext w = cands[i].st;
                        w.player.curHp -= std::max(0, incoming - w.player.block);
                        w.turn += 1;
                        if (w.player.curHp > 0) {
                            const double slack = formulaBound(w) - ov[i];
                            int sb = slack < 0.5 ? 0 : slack < 1 ? 1 : slack < 2 ? 2 : slack < 4 ? 3 : slack < 8 ? 4 : slack < 16 ? 5 : 6;
                            ++slackHist_[sb];
                            if (slack < margin) ++oneTurnRefutes_;
                        }
                    }
                    ++diagTotal_;
                    for (int h = 0; h < kHeuristics; ++h) {
                        std::size_t first = survivors[0];
                        double fk = heuristicKey(cands[first].st, h);
                        for (std::size_t i : survivors) {
                            const double k = heuristicKey(cands[i].st, h);
                            if (k > fk) { fk = k; first = i; }
                        }
                        if (ov[first] >= best - 1e-9) ++diagHits_[h];
                    }
                }
            }
            // Research (--twin-order): the best candidate of a memoized HP twin of `s` goes first.
            std::uint32_t hashSig = 0;
            if (twinOrder_) {
                const KeyBuilder spre = statePrefix(s);
                for (int d = 1; d <= kTwinProbes && !hashSig; ++d)
                    for (int h : {s.player.curHp + d, s.player.curHp - d})
                        if (Val hit; h > 0 && h <= s.player.maxHp && memo_.find(keyAtHp(spre, h), hit) && hit.exact && hit.sig) { hashSig = hit.sig; break; }
            }
            if (orderHeuristic_ >= 0) {
                std::vector<double> hk(cands.size(), 0);
                for (std::size_t i : survivors) hk[i] = heuristicKey(cands[i].st, orderHeuristic_);
                std::stable_sort(survivors.begin(), survivors.end(), [&](std::size_t x, std::size_t y) { return hk[x] > hk[y]; });
            } else if (oracle_ && oracleOrder_) {
                // Research: order by the previous solve's values (best first).
                std::vector<double> ov(cands.size(), -1e300);
                for (std::size_t i : survivors) {
                    Key k = stateKey(cands[i].st);
                    k.b ^= 0x5bd1e9955bd1e995ULL;
                    // Exact values first; a fail-low bound only says "at most v".
                    if (Val hit; oracle_->find(k, hit)) ov[i] = hit.exact ? hit.v : hit.v - 1e6;
                }
                std::stable_sort(survivors.begin(), survivors.end(), [&](std::size_t x, std::size_t y) { return ov[x] > ov[y]; });
            } else {
            std::sort(survivors.begin(), survivors.end(), [&](std::size_t x, std::size_t y) {
                return order(x) != order(y) ? order(x) < order(y) : x < y;
            });
            }
            if (hashSig) {
                for (std::size_t r = 0; r < survivors.size(); ++r)
                    if (sigOf(cands[survivors[r]].st) == hashSig) {
                        std::rotate(survivors.begin(), survivors.begin() + static_cast<std::ptrdiff_t>(r),
                                    survivors.begin() + static_cast<std::ptrdiff_t>(r) + 1);
                        ++hashMoveHits_;
                        break;
                    }
            }
            std::vector<Val> childVals(survivors.size());
            out = maxOver(survivors.size(), alpha, [&](std::size_t i, double a) {
                childVals[i] = endValue(cands[survivors[i]].st, cands[survivors[i]].endTurn, a);
                return childVals[i];
            }, best);
            if (out.exact)
                for (std::size_t i = 0; i < survivors.size(); ++i)
                    if (childVals[i].exact && childVals[i].v >= out.v - 1e-12) { out.sig = sigOf(cands[survivors[i]].st); break; }
            return true;
        }

        // Every outcome of `a` at `s` with its exact probability, equal states merged.
        std::vector<Outcome1> outcomes(const BattleContext &s, const SAction &a) {
            std::vector<Outcome1> out;
            std::unordered_map<Key, std::size_t, KeyHash> index;
            std::vector<std::vector<int>> stack{{}};
            const bool endTurn = a.getActionType() == search::ActionType::END_TURN;
            const auto replaysBefore = replays_;
            std::int64_t dead = 0;
            struct Report {
                ExactSolver &self; bool endTurn; std::int64_t before; std::int64_t &dead; std::vector<Outcome1> &out;
                ~Report() {
                    if (!endTurn) { ++self.cardCalls_; self.cardReplays_ += self.replays_ - before; return; }
                    ++self.endCalls_; self.endReplays_ += self.replays_ - before; self.endDead_ += dead;
                    self.endOutcomes_ += static_cast<std::int64_t>(out.size());
                }
            } report{*this, endTurn, replaysBefore, dead, out};
            while (!stack.empty()) {
                auto prefix = std::move(stack.back());
                stack.pop_back();
                BattleContext next = s;
                script_.reset(prefix);
                exact::g_chanceScript = &script_;
                if (++replays_ % 1000000 == 0)
                {
                    std::cerr << "  replays=" << replays_ << " states=" << memo_.size() << " turn=" << s.turn
                              << " endTurn calls/replays/dead/outcomes=" << endCalls_ << '/' << endReplays_ << '/' << endDead_
                              << '/' << endOutcomes_ << " card calls/replays=" << cardCalls_ << '/' << cardReplays_ << " byTurn";
                    for (const auto &[t, n] : statesByTurn_) std::cerr << ' ' << t << ':' << n;
                    std::cerr << '\n';
                }
                try {
                    a.execute(next);
                } catch (...) {
                    exact::g_chanceScript = nullptr;
                    throw;
                }
                exact::g_chanceScript = nullptr;
                script_.untried(stack);
                // Silver's loss score subtracts 1.75 per wasted energy; dropping the
                // counter removes that term and keeps it out of the state key.
                if (dropEnergyWaste_) next.energyWasted = 0;
                const double p = script_.prob;
                if (endTurn && endCalls_ == 0 && std::getenv("STS_EXACT_DEBUG")) {
                    std::cerr << "run prefix=";
                    for (int x : prefix) std::cerr << x << ',';
                    std::cerr << " p=" << p << " hand=";
                    for (int i = 0; i < next.cards.cardsInHand; ++i) std::cerr << static_cast<int>(next.cards.hand[i].id) << ' ';
                    std::cerr << '\n';
                }
                if (p <= 0) { ++dead; continue; }
                if (quiet(next)) canonicalizeIds(next);
                // Quiet decisions and terminals merge by key; anything else (a card
                // selection mid-action) stays its own outcome.
                if (!quiet(next) && next.outcome == Outcome::UNDECIDED) {
                    out.push_back({next, p, KeyBuilder{}, false});
                    continue;
                }
                const KeyBuilder pre = statePrefix(next);
                const Key key = keyAtHp(pre, next.player.curHp);
                if (auto it = index.find(key); it != index.end()) {
                    out[it->second].p += p;
                } else {
                    index.emplace(key, out.size());
                    out.push_back({next, p, pre, true});
                }
            }
            return out;
        }
    };

    // Cards whose draw order cannot matter (no on-draw trigger, no draw-order
    // dependent effect): the canonical-draw shortcut is used only when every
    // card of the combat is listed. Anything else is still solved exactly,
    // just without merging draw orders early.
    bool canonicalDrawsSafe(const BattleContext &bc) {
        static const std::vector<CardId> safe = {
            CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::BASH, CardId::ASCENDERS_BANE,
        };
        auto ok = [&](const CardInstance &c) { return std::find(safe.begin(), safe.end(), c.id) != safe.end(); };
        const auto &cm = bc.cards;
        for (int i = 0; i < cm.cardsInHand; ++i) if (!ok(cm.hand[i])) return false;
        for (const auto &c : cm.drawPile) if (!ok(c)) return false;
        for (const auto &c : cm.discardPile) if (!ok(c)) return false;
        for (const auto &c : cm.exhaustPile) if (!ok(c)) return false;
        return true;
    }

    // Dominance pruning is exact only when the fight's future is monotone in the
    // compared fields: lower monster HP/block and more monster Vulnerable/Weak
    // or player block never hurt. That holds for the starter cards, Burning
    // Blood and the Act-1 weak monsters listed here (no HP-threshold moves,
    // splits or on-death effects).
    bool dominanceSafe(const BattleContext &bc) {
        if (!canonicalDrawsSafe(bc)) return false;
        const int bb = static_cast<int>(RelicId::BURNING_BLOOD);
        const std::uint64_t want0 = bb < 64 ? 1ULL << bb : 0, want1 = bb < 64 ? 0 : 1ULL << (bb - 64);
        if (bc.player.relicBits0 != want0 || bc.player.relicBits1 != want1) return false;
        static const std::vector<MonsterId> safe = {
            MonsterId::CULTIST, MonsterId::JAW_WORM, MonsterId::RED_LOUSE, MonsterId::GREEN_LOUSE,
            MonsterId::ACID_SLIME_S, MonsterId::SPIKE_SLIME_S, MonsterId::SPIKE_SLIME_M, MonsterId::ACID_SLIME_M,
        };
        for (int i = 0; i < bc.monsters.monsterCount; ++i)
            if (std::find(safe.begin(), safe.end(), bc.monsters.arr[i].id) == safe.end()) return false;
        return true;
    }

    std::string actionLabel(const SAction &a, const BattleContext &bc) {
        std::ostringstream os;
        a.printDesc(os, bc);
        return os.str();
    }

    MonsterEncounter parseEncounter(const std::string &name) {
        for (int i = 0; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
            if (name == monsterEncounterEnumNames[i]) return static_cast<MonsterEncounter>(i);
        throw std::invalid_argument("unknown encounter " + name);
    }

}

namespace {

    struct Config {
        std::string name;
        sts::search::NativeSilverBudgetOverride budget;
        int flatSims = 10000;
        bool prior = false;
    };

    Config parseConfig(const std::string &name) {
        using P = sts::search::NativeSilverBudgetOverride::Policy;
        Config c;
        c.name = name;
        c.budget.skipSingletonRoots = true;
        if (name == "prod") { c.budget.policy = P::LearnedStop; c.prior = true; }
        else if (name == "live") { c.budget.policy = P::Flat; }
        else if (name.rfind("flat:", 0) == 0) { c.budget.policy = P::Flat; c.flatSims = std::stoi(name.substr(5)); }
        else if (name.rfind("flatprior:", 0) == 0) { c.budget.policy = P::Flat; c.flatSims = std::stoi(name.substr(10)); c.prior = true; }
        else throw std::invalid_argument("unknown config " + name);
        return c;
    }

    double seconds(std::chrono::steady_clock::time_point since) {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - since).count();
    }

}

int main(int argc, char **argv) {
    try {
        if (argc < 4) {
            std::cerr << "usage: exact_combat_solver COUNT START_SEED OUT.jsonl [--configs a,b,...] [--encounter NAME]"
                         " [--max-states N] [--objective silver|hp] [--keep-energy-waste] [--verify-memo]"
                         " [--no-canonical-draws] [--no-dominance] [--no-bounds]\n";
            return 2;
        }
        const int count = std::stoi(argv[1]);
        const std::uint64_t startSeed = std::stoull(argv[2]);
        std::ofstream out(argv[3], std::ios::app);
        if (!out) throw std::runtime_error(std::string("cannot open ") + argv[3]);
        std::vector<Config> configs;
        std::optional<MonsterEncounter> forced;
        std::int64_t maxStates = 60'000'000;
        bool hpObjective = false, verify = false, canonicalOff = false, keepEnergyWaste = false, noDominance = false, noBounds = false;
        bool stats = false, firstRootOnly = false, oraclePass = false, oracleOrder = false, oracleBoundsOff = false;
        bool orderDiag = false;
        int orderHeuristic = -1, oracleCap = -1;
        bool twinOrder = false;
        bool lipschitz = false, interpolate = false, endTwin = false, intentBound = false, intentCheck = false;
        double epsilon = 0;
        int turnCap = 8;
        for (int i = 4; i < argc; ++i) {
            const std::string arg = argv[i];
            auto value = [&]() -> std::string {
                if (i + 1 >= argc) throw std::invalid_argument(arg + " needs a value");
                return argv[++i];
            };
            if (arg == "--configs") {
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) configs.push_back(parseConfig(item));
            } else if (arg == "--encounter") forced = parseEncounter(value());
            else if (arg == "--max-states") maxStates = std::stoll(value());
            else if (arg == "--objective") {
                const auto v = value();
                if (v != "silver" && v != "hp") throw std::invalid_argument("--objective silver|hp");
                hpObjective = v == "hp";
            } else if (arg == "--verify-memo") verify = true;
            else if (arg == "--no-canonical-draws") canonicalOff = true;
            else if (arg == "--no-dominance") noDominance = true;
            else if (arg == "--no-bounds") noBounds = true;
            else if (arg == "--keep-energy-waste") keepEnergyWaste = true;
            else if (arg == "--turn-cap") turnCap = std::stoi(value());
            else if (arg == "--stats") stats = true;
            else if (arg == "--first-root-only") firstRootOnly = true;
            else if (arg == "--oracle-pass") oraclePass = true;
            else if (arg == "--oracle-order") oracleOrder = true;
            else if (arg == "--oracle-no-bounds") oracleBoundsOff = true;
            else if (arg == "--order-diag") orderDiag = true;
            else if (arg == "--oracle-cap") oracleCap = std::stoi(value());
            else if (arg == "--twin-order") twinOrder = true;
            else if (arg == "--order-lambda") g_orderLambda = std::stod(value());
            else if (arg == "--order-vuln") g_orderVuln = std::stod(value());
            else if (arg == "--order-heuristic") orderHeuristic = std::stoi(value());
            else if (arg == "--lipschitz") lipschitz = true;
            else if (arg == "--interpolate") interpolate = true;
            else if (arg == "--end-twin") endTwin = true;
            else if (arg == "--intent-bound") intentBound = true;
            else if (arg == "--intent-check") intentCheck = true;
            else if (arg == "--epsilon") epsilon = std::stod(value());
            else throw std::invalid_argument("unknown option " + arg);
        }
        if (configs.empty()) configs = {parseConfig("prod"), parseConfig("live"),
                                        parseConfig("flatprior:2500"), parseConfig("flatprior:10000")};
        const std::string objective = std::string(hpObjective ? "hp" : "silver") + (keepEnergyWaste ? "" : "-noew");
        if ((lipschitz || interpolate) && !hpObjective)
            throw std::invalid_argument("--lipschitz and --interpolate need --objective hp (Silver's value is not Lipschitz in HP)");

        sts::search::installNativeSilverBackend();
        for (const auto &c : configs)
            if (c.prior && sts::search::nativeSilverRootPriorPath().empty())
                throw std::runtime_error("config " + c.name + " needs STS_SILVER_ROOT_PRIOR (and _WEIGHT) in the environment");

        for (int n = 0; n < count; ++n) {
            const std::uint64_t seed = startSeed + static_cast<std::uint64_t>(n);
            GameContext start(CharacterClass::IRONCLAD, seed, 20);
            const MonsterEncounter encounter = forced ? *forced : start.monsterList[0];
            start.floorNum = 1;
            start.curRoom = Room::MONSTER;
            start.info.encounter = encounter;
            const std::string encounterName = monsterEncounterEnumNames[static_cast<int>(encounter)];

            // One exact solve per fight, built at the first searched root and
            // shared by every config: each config's decisions are looked up in it.
            std::unique_ptr<ExactSolver> solver;
            std::string fightFailure;
            double solveSeconds = 0;
            // A solve that outgrows --max-states is dropped and retried from the
            // first root of a later turn: roots up to this turn stay unscored.
            int unsolvableThroughTurn = -1;
            json infeasibleSolves = json::array();
            for (const auto &config : configs) {
                if (!fightFailure.empty()) break;
                sts::search::g_nativeSilverBudgetOverride = config.budget;
                if (config.prior) sts::search::g_nativeSilverRootPriorOverride.reset();
                else sts::search::g_nativeSilverRootPriorOverride = false;
                int searchedRoots = 0, optimalRoots = 0, unscoredRoots = 0;
                double regretSum = 0, hpLossSum = 0, winLossSum = 0;
                const auto fightStart = std::chrono::steady_clock::now();
                bool firstRootDone = false;
                sts::search::g_nativeSilverRootObserver = [&](const sts::search::NativeSilverRootView &view) {
                    if (view.skipped || !fightFailure.empty()) return;
                    if (firstRootOnly && firstRootDone) return;
                    const SilverSearcher &searcher = view.searcher;
                    const BattleContext &root = searcher.rootSearchState();
                    if (root.turn <= unsolvableThroughTurn) { ++unscoredRoots; return; }
                    try {
                        if (!solver) {
                            solver = std::make_unique<ExactSolver>(root, searcher, hpObjective, maxStates, verify,
                                                                   !canonicalOff && canonicalDrawsSafe(root), !keepEnergyWaste);
                            // --oracle-cap: the first solve runs at a smaller cap and only orders the second
                            // (iterative deepening); the reported Q values are then the first solve's.
                            solver->turnCap_ = oracleCap >= 0 ? oracleCap : turnCap;
                            solver->stats_ = stats;
                            solver->orderHeuristic_ = orderHeuristic;
                            solver->twinOrder_ = twinOrder;
                            solver->eps_ = epsilon;
                            // Energy left over is not compared, so the energy-waste term must be off.
                            const bool safe = !keepEnergyWaste && dominanceSafe(root) && solver->monotone();
                            solver->prune_ = !noDominance && safe;
                            solver->bounds_ = !noBounds && safe && root.potionCount == 0
                                && searcher.evalWeights.victoryTurnPenalty >= 0;
                            // The HP-twin rules rest on the same gate (HP changes nothing but death, and never rises).
                            solver->lipschitz_ = lipschitz && solver->bounds_;
                            solver->interpolate_ = interpolate && solver->bounds_;
                            solver->endTwin_ = (endTwin || lipschitz) && solver->bounds_;
                            solver->intentBound_ = intentBound && solver->bounds_;
                            solver->intentCheck_ = intentCheck && solver->bounds_;
                        }
                        const auto t0 = std::chrono::steady_clock::now();
                        const auto &edges = searcher.rootNode().edges;
                        const SAction chosen = searcher.bestAction();
                        json acts = json::array();
                        double best = -1e300;
                        int bestIdx = -1, chosenIdx = -1;
                        std::vector<Val> qs;
                        for (std::size_t i = 0; i < edges.size(); ++i) {
                            const Val v = solver->q(root, edges[i].action);
                            if (!v.exact) throw std::runtime_error("exact solver: a root value came back as a bound");
                            qs.push_back(v);
                            if (v.v > best) { best = v.v; bestIdx = static_cast<int>(i); }
                            if (edges[i].action == chosen) chosenIdx = static_cast<int>(i);
                            acts.push_back({{"label", actionLabel(edges[i].action, root)}, {"q", v.v}, {"score", v.score},
                                            {"hp", v.hp}, {"win", v.win}, {"capped", v.capped},
                                            {"visits", edges[i].visitCount}});
                        }
                        solveSeconds += seconds(t0);
                        if (chosenIdx < 0) throw std::runtime_error("Silver's chosen action is not a root edge");
                        json row = {{"seed", seed}, {"config", config.name}, {"objective", objective},
                                    {"encounter", encounterName}, {"decision", view.decision}, {"turn", root.turn},
                                    {"hp", root.player.curHp}, {"energy", root.player.energy},
                                    {"simulations", view.simulations}, {"inheritedVisits", view.inheritedVisits},
                                    {"actions", acts}, {"chosen", chosenIdx}, {"best", bestIdx},
                                    {"regret", best - qs[chosenIdx].v}, {"optimal", qs[chosenIdx].v >= best - 1e-9},
                                    {"states", solver->states()}};
                        if (verify) row["verifiedHits"] = solver->verifiedHits();
                        row["solveSecondsSoFar"] = solveSeconds;
                        if (stats && !firstRootDone) {
                            ExactSolver::SolutionStats opt, all;
                            solver->solutionGraph(root, opt);
                            std::vector<SAction> rootActs;
                            for (const auto &e : edges) rootActs.push_back(e.action);
                            solver->solutionGraphForActions(root, rootActs, all);
                            json byTurn = json::object();
                            for (const auto &[t, n] : opt.byTurn) byTurn[std::to_string(t)] = n;
                            json byTurnAll = json::object();
                            for (const auto &[t, n] : all.byTurn) byTurnAll[std::to_string(t)] = n;
                            row["stats"] = {{"memoByTurnKind", solver->statsJson()},
                                            {"solutionDecision", opt.decision.size()}, {"solutionEndTurn", opt.endTurn.size()},
                                            {"solutionByTurn", byTurn}, {"solutionTies", opt.ties},
                                            {"solutionInexactTurns", opt.inexactTurns},
                                            {"allActionsDecision", all.decision.size()}, {"allActionsEndTurn", all.endTurn.size()},
                                            {"allActionsByTurn", byTurnAll}};
                        }
                        if (oraclePass && !firstRootDone) {
                            // A second solve of the same root whose upper bounds are the first solve's
                            // values: the state count perfect bounds would leave with this search order.
                            ExactSolver second(root, searcher, hpObjective, maxStates, false,
                                               !canonicalOff && canonicalDrawsSafe(root), !keepEnergyWaste);
                            second.turnCap_ = turnCap;
                            second.prune_ = solver->prune_;
                            second.bounds_ = solver->bounds_;
                            second.oracle_ = &solver->memo();
                            second.oracleOrder_ = oracleOrder;
                            second.oracleBoundsOn_ = !oracleBoundsOff;
                            second.orderDiag_ = orderDiag;
                            second.orderHeuristic_ = orderHeuristic;
                            const auto t1 = std::chrono::steady_clock::now();
                            double maxDiff = 0;
                            for (std::size_t i = 0; i < edges.size(); ++i) {
                                const Val v = second.q(root, edges[i].action);
                                maxDiff = std::max(maxDiff, std::abs(v.v - qs[i].v));
                            }
                            row["oracle"] = {{"states", second.states()}, {"seconds", seconds(t1)},
                                             {"maxAbsDiffQ", maxDiff}, {"oracleBounds", second.oracleBounds_},
                                             {"cutoffs", second.cutoffs_}};
                            if (orderDiag) {
                                json hits = json::array();
                                for (int h = 0; h < ExactSolver::kHeuristics; ++h) hits.push_back(second.diagHits_[h]);
                                json mh = json::array(), sh = json::array();
                                for (int b = 0; b < 7; ++b) { mh.push_back(second.marginHist_[b]); sh.push_back(second.slackHist_[b]); }
                                row["oracle"]["orderDiag"] = {{"total", second.diagTotal_}, {"firstIsOptimal", hits},
                                                              {"marginHist<.5,1,2,4,8,16,inf", mh}, {"oneTurnSlackHist", sh},
                                                              {"oneTurnBoundRefutes", second.oneTurnRefutes_}};
                            }
                        }
                        firstRootDone = true;
                        out << row.dump() << '\n';
                        out.flush();
                        ++searchedRoots;
                        if (qs[chosenIdx].v >= best - 1e-9) ++optimalRoots;
                        regretSum += best - qs[chosenIdx].v;
                        hpLossSum += qs[bestIdx].hp - qs[chosenIdx].hp;
                        winLossSum += qs[bestIdx].win - qs[chosenIdx].win;
                    } catch (const Infeasible &e) {
                        infeasibleSolves.push_back({{"config", config.name}, {"turn", root.turn},
                                                    {"decision", view.decision}, {"reason", e.what()}});
                        std::cerr << "infeasible from turn " << root.turn << " (" << e.what() << "); retrying later\n";
                        solver->clear();
                        unsolvableThroughTurn = root.turn;
                        ++unscoredRoots;
                    } catch (const std::exception &e) {
                        fightFailure = e.what();
                    }
                };
                GameContext gc = start;
                sts::search::ScumSearchAgent2 agent;
                agent.simulationCountBase = config.flatSims;
                BattleContext bc;
                agent.playoutBattle(gc, bc);
                sts::search::g_nativeSilverRootObserver = nullptr;
                json summary = {{"seed", seed}, {"config", config.name}, {"objective", objective},
                                {"encounter", encounterName}, {"summary", true},
                                {"outcome", bc.outcome == Outcome::PLAYER_VICTORY ? "win" : "loss"},
                                {"endHp", bc.player.curHp}, {"turns", bc.turn}, {"searchedRoots", searchedRoots},
                                {"optimalRoots", optimalRoots}, {"unscoredRoots", unscoredRoots},
                                {"unsolvableThroughTurn", unsolvableThroughTurn}, {"infeasibleSolves", infeasibleSolves},
                                {"regretSum", regretSum}, {"hpLossSum", hpLossSum},
                                {"winLossSum", winLossSum}, {"states", solver ? solver->states() : 0},
                                {"dominance", solver && solver->prune_},
                                {"endTurnCandidates", solver ? solver->candidates_ : 0},
                                {"dominated", solver ? solver->dominated_ : 0},
                                {"chanceTurns", solver ? solver->chanceTurns_ : 0},
                                {"bounds", solver && solver->bounds_}, {"cutoffs", solver ? solver->cutoffs_ : 0},
                                {"twinBounds", solver ? solver->twinBounds_ : 0}, {"turnCap", turnCap},
                                {"hashMoveHits", solver ? solver->hashMoveHits_ : 0},
                                {"interpolations", solver ? solver->interpolations_ : 0},
                                {"endTwinCutoffs", solver ? solver->endTwinCutoffs_ : 0},
                                {"intentCutoffs", solver ? solver->intentCutoffs_ : 0},
                                {"intentViolations", solver ? solver->intentViolations_ : 0},
                                {"endCalls", solver ? solver->endCalls_ : 0},
                                {"endReplays", solver ? solver->endReplays_ : 0},
                                {"endFirstCuts", solver ? solver->endFirstCuts_ : 0},
                                {"endFirstCutReplays", solver ? solver->endFirstCutReplays_ : 0},
                                {"replays", solver ? solver->replays() : 0},
                                {"lipschitzTighter", solver ? solver->lipschitzTighter_ : 0},
                                {"interpNoLo", solver ? solver->interpNoLo_ : 0},
                                {"interpNoHi", solver ? solver->interpNoHi_ : 0},
                                {"slopeHist<.001,.5,.9,.99,1-,1,>1", solver ? json(std::vector<std::int64_t>(solver->slopeHist_, solver->slopeHist_ + 7)) : json::array()},
                                {"solveSeconds", solveSeconds}, {"seconds", seconds(fightStart)}};
                if (solver) {
                    json bt = json::object();
                    for (const auto &[t, n] : solver->statesByTurn_) bt[std::to_string(t)] = n;
                    summary["decisionStatesByTurn"] = bt;
                }
                if (!fightFailure.empty()) summary["failure"] = fightFailure;
                out << summary.dump() << '\n';
                out.flush();
                std::cerr << summary.dump() << '\n';
            }
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "exact_combat_solver: " << e.what() << '\n';
        return 1;
    }
}
