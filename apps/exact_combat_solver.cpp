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
//
// exact_combat_solver roots IN.jsonl OUT.jsonl [options] (research, see rootsMain): Silver's
// recorded roots of the last turns of real A20 elite and boss fights (one_combat
// endgamerootgen), each solved through a short horizon with proven bounds on every action.

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
#include "combat/BattleContextBinary.h"
#include "constants/MonsterEncounters.h"
#include "game/ExactChance.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverRolloutAgent.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverValueHead.h"

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
        // Policy evaluation (--policy-turns): from this game turn on, every decision
        // follows Silver's greedy rollout policy (policy_, deterministic tie-breaks)
        // instead of the max, so the value is the exact expectation of "optimal play
        // before turn policyFromTurn_, Silver's playout from there". Needs prune_ and
        // bounds_ off (they assume an optimal continuation).
        int policyFromTurn_ = 1 << 30;
        sts::search::SilverRolloutAgent policy_;
        std::vector<int> policyTable_;
        void setPolicy(int fromTurn, const sts::search::SilverSearcher &live) {
            policyFromTurn_ = fromTurn;
            policy_ = sts::search::SilverRolloutAgent(false, 0, live.searchContext().act);
            policy_.zeroCostSkillTurnCap = live.rolloutConfig.zeroCostCap;
            policy_.blockRule = live.rolloutConfig.blockRule;
            if (live.rolloutConfig.cardTable) {
                policyTable_.assign(live.rolloutConfig.cardTable, live.rolloutConfig.cardTable + 372 * 2);
                policy_.playTable = policyTable_.data();
            }
        }
        // Research (--policy-then-exact): from this game turn on, a state's value is
        // exactSource_'s abstract exact value instead of play, so the value becomes
        // "optimal play before policyFromTurn_, Silver's playout until this turn starts,
        // the exact value from there" (a perfect turn-start leaf behind one greedy turn).
        int exactFromTurn_ = 1 << 30;
        ExactSolver *exactSource_ = nullptr;
        // The abstract exact value of a decision state (false where the model does not apply).
        bool abstractValue(const BattleContext &s, double &out) {
            if (s.turn > turnCap_) { out = terminal(s).v; return true; }
            return quiet(s) && modelDec(1, s, out);
        }
        // Research (--leaf-oracles M@S): a fixed N(0, leafNoise_^2) error per state, drawn from the
        // state's key, so it repeats on every visit as a value net's error would.
        double leafNoise_ = 0;
        double noiseAt(const BattleContext &s) const {
            if (leafNoise_ == 0) return 0;
            const Key k = stateKey(s);
            const double u1 = static_cast<double>(splitmix(k.a) >> 11) * 0x1.0p-53 + 0x1.0p-54;
            const double u2 = static_cast<double>(splitmix(k.b ^ 0x5EED5EED5EED5EEDULL) >> 11) * 0x1.0p-53;
            return leafNoise_ * std::sqrt(-2.0 * std::log(u1)) * std::cos(6.283185307179586 * u2);
        }
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
            if (general_) return generalUpperBound(s);
            // Research (--oracle-pass): the values of a previous full solve as
            // upper bounds, to measure what perfect bounds would save.
            if (oracle_ && oracleBoundsOn_ && quiet(s)) {
                const Key k = pre ? keyAtHp(*pre, s.player.curHp) : stateKey(s);
                if (Val hit; oracle_->find(k, hit)) { ++oracleBounds_; return std::min(hit.v, formulaBound(s)); }
            }
            double ub = formulaBound(s);
            // The same state at more HP is worth at least as much (see monotone()):
            // a memoized twin a few HP higher, exact or itself a bound, bounds it.
            if (pre && quiet(s) && lipschitz_) {
                const double t = twinUpperBound(*pre, s, 0);
                if (t < 1e299) ++twinBounds_;
                ub = std::min(t, ub);
            } else if (pre && quiet(s)) {
                const int top = std::min(s.player.maxHp, s.player.curHp + kTwinProbes);
                for (int h = s.player.curHp + 1; h <= top; ++h)
                    if (Val hit; memo_.find(keyAtHp(*pre, h), hit)) { ++twinBounds_; ub = std::min(hit.v, ub); break; }
            }
            if (relaxedBound_ && quiet(s) && s.turn <= turnCap_) {
                if (double r; modelDec(0, s, r)) {
                    r = rxPad(r);
                    if (r < ub) { ++relaxedDecTighter_; ub = r; }
                }
            }
            return ub;
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
        // Research (--relaxed-bound): the value of a relaxed game in which the
        // player picks every card drawn (any cards the draw could deliver) while
        // the monster keeps its exact move probabilities. A max over draws is at
        // least their expectation, so the relaxed value bounds the exact one in
        // every state. Jaw Worm and the Cultist (and Two Louse and Small Slimes,
        // see their models below) with the starter deck only: there the relaxed
        // state between turns needs no hand, discard pile or block, only the
        // monster's HP, Strength, Vulnerable and last two moves, the draw pile's
        // counts, whether Ascender's Bane is exhausted and the turn, with one
        // value per player HP. --relaxed-free-draws (Jaw Worm and the Cultist
        // only) lets every turn draw any cards of the deck (no draw pile in the
        // state: smaller and looser).
        // --relaxed-check compares the bound with every exact value and the
        // mirrored monster turn and draw with the engine's outcomes, and prunes
        // nothing with it.
        // --relaxed-order: search end-of-turn candidates by their relaxed value (ties by --order-heuristic).
        bool relaxedBound_ = false, relaxedCheck_ = false, relaxedFreeDraws_ = false, relaxedOrder_ = false;
        std::int64_t relaxedCutoffs_ = 0, relaxedDecTighter_ = 0, relaxedViolations_ = 0, relaxedMirror_ = 0;
        std::int64_t relaxedChecked_ = 0, relaxedGateMisses_ = 0, relaxedEndChecks_ = 0, relaxedDecChecks_ = 0;
        std::int64_t relaxedEndSlack_[7] = {}, relaxedDecSlack_[7] = {}, relaxedIntentSlack_[7] = {}, relaxedWouldCut_ = 0;
        double rxSeconds_[2] = {0, 0};
        bool relaxedReady() const { return rxOn_ || lxOn_ || sxOn_; }
        std::size_t relaxedStates() const { return rxTab_[0].index.size(); }
        // Research (--abstract-check, --abstract-only): table 1 runs the same
        // recursion with the draw's exact probabilities instead of the max, which
        // on this abstract state is the fight's exact value (the hand is empty
        // between turns, and the discard pile, energy, block and cards drawn
        // follow from the rest). --abstract-check compares it with every exact
        // value of the search; --abstract-only skips the search.
        bool abstractCheck_ = false;
        std::int64_t abstractChecks_ = 0, abstractMismatches_ = 0;
        double abstractMaxDiff_ = 0;
        std::size_t abstractStates() const { return rxTab_[1].index.size(); }
        // A root action's value from the abstract exact recursion (false where it does not apply).
        bool abstractQ(const BattleContext &s, const SAction &a, double &out) {
            if (a.getActionType() == search::ActionType::END_TURN) return quiet(s) && modelEnd(1, s, out);
            double v = 0;
            for (const auto &o : outcomes(s, a)) {
                if (o.state.outcome != Outcome::UNDECIDED) { v += o.p * terminal(o.state).v; continue; }
                double d = 0;
                if (!quiet(o.state) || !modelDec(1, o.state, d)) return false;
                v += o.p * (o.state.turn > turnCap_ ? terminal(o.state).v : d);
            }
            out = v;
            return true;
        }
        // Research (--policy-this-turn): a root action's value when Silver's playout
        // policy (policy_, see setPolicy) plays the rest of the root's turn and the
        // abstract exact value takes over where the policy ends the turn: what a perfect
        // start-of-turn leaf would give after a greedy finish of the turn (false where
        // the model does not apply).
        bool turnPolicyQ(const BattleContext &s, const SAction &a, double &out) {
            if (a.getActionType() == search::ActionType::END_TURN) {
                if (!abstractQ(s, a, out)) return false;
                out += noiseAt(s);   // --leaf-oracle turn: the error of an afterstate net
                return true;
            }
            double v = 0;
            for (const auto &o : outcomes(s, a)) {
                if (o.state.outcome != Outcome::UNDECIDED) { v += o.p * terminal(o.state).v; continue; }
                if (o.state.turn != s.turn) return false;
                SAction next;
                if (o.state.inputState == InputState::PLAYER_NORMAL) next = policy_.chooseBattleCardPlay(o.state);
                else if (o.state.inputState == InputState::CARD_SELECT) next = policy_.chooseBattleCardSelect(o.state);
                else return false;
                double d = 0;
                if (!turnPolicyQ(o.state, next, d)) return false;
                v += o.p * d;
            }
            out = v;
            return true;
        }

        // Sets the relaxed game up for the root's fight (Jaw Worm or the Cultist;
        // Two Louse and Small Slimes below); false where it does not apply.
        bool relaxedInit() {
            const BattleContext &r = rootCopy_;
            if (r.monsters.monsterCount == 2) return lxInit() || sxInit();
            if (r.monsters.monsterCount != 1) return false;
            rxMonster_ = r.monsters.arr[0].id;
            if (rxMonster_ != MonsterId::JAW_WORM && rxMonster_ != MonsterId::CULTIST) return false;
            if (!rxDeckInit(r)) return false;
            const int asc = r.ascension;
            if (rxMonster_ == MonsterId::CULTIST) {
                // MonsterSpecific.cpp, CULTIST: Incantation first (Ritual, which skips the
                // end of the round it is applied in, Monster::applyEndOfRoundPowers),
                // then Dark Strike for 6 every turn, each round ending with Ritual's Strength.
                rxRitual_ = asc >= 17 ? 5 : asc >= 2 ? 4 : 3;
                rxAttack_[RX_CHOMP] = 6; rxAttack_[RX_THRASH] = -1; rxAttack_[RX_BELLOW] = -1;
                rxStrGain_[RX_CHOMP] = rxRitual_; rxStrGain_[RX_THRASH] = 0; rxStrGain_[RX_BELLOW] = 0;
                std::fill(std::begin(rxBlock_), std::end(rxBlock_), 0);
                for (int last = 0; last < 3; ++last)
                    for (int before = 0; before < 4; ++before)
                        for (int n = 0; n < 3; ++n) rxRoll_[last][before][n] = n == RX_CHOMP ? 1 : 0;
                rxOn_ = true;
                RxView x;
                rxOn_ = rxView(r, x);
                return rxOn_;
            }
            rxAttack_[RX_CHOMP] = asc >= 2 ? 12 : 11;
            rxAttack_[RX_THRASH] = 7;
            rxAttack_[RX_BELLOW] = -1;
            rxStrGain_[RX_CHOMP] = 0; rxStrGain_[RX_THRASH] = 0; rxStrGain_[RX_BELLOW] = asc >= 17 ? 5 : asc >= 2 ? 4 : 3;
            rxBlock_[0] = 0; rxBlock_[1] = 5; rxBlock_[2] = asc >= 17 ? 9 : 6; rxBlock_[3] = 0;
            // The move roll (MonsterSpecific.cpp, JAW_WORM): 0..99 uniform with the
            // engine's float coin flips, after the move `last` with `before` before it.
            using exact::ChanceScript;
            const double b1 = ChanceScript::booleanProbability(0.5625f), b2 = ChanceScript::booleanProbability(0.357f),
                         b3 = ChanceScript::booleanProbability(0.416f);
            for (int last = 0; last < 3; ++last)
                for (int before = 0; before < 4; ++before) {
                    double p[3] = {0, 0, 0};
                    if (last == 0) { p[2] += 0.25 * b1; p[1] += 0.25 * (1 - b1); } else p[0] += 0.25;
                    if (last == 1 && before == 1) { p[0] += 0.30 * b2; p[2] += 0.30 * (1 - b2); } else p[1] += 0.30;
                    if (last == 2) { p[0] += 0.45 * b3; p[1] += 0.45 * (1 - b3); } else p[2] += 0.45;
                    for (int n = 0; n < 3; ++n) rxRoll_[last][before][n] = p[n];
                }
            rxOn_ = true;
            RxView x;
            rxOn_ = rxView(r, x);
            return rxOn_;
        }
    private:
        // ---- relaxed game (--relaxed-bound) -----------------------------------
        // The single monster's moves: Jaw Worm's; the Cultist's Dark Strike and
        // Incantation take the Chomp and Bellow slots (an attack, a move without one).
        enum { RX_CHOMP = 0, RX_THRASH = 1, RX_BELLOW = 2, RX_NONE = 3 };
        struct RxDeck {
            int s = 0, d = 0, b = 0, a = 0, x = 0;   // Strikes, Defends, Bashes, Ascender's Banes, Slimed
            int total() const { return s + d + b + a + x; }
            bool operator==(const RxDeck &) const = default;
        };
        // A concrete state as the relaxed game sees it.
        struct RxView {
            int m = 0, mb = 0, str = 0, vuln = 0, mv0 = 0, mv1 = 0, h = 0, pblock = 0, e = 0, t = 0;
            RxDeck hand, pile;
            bool abGone = false;   // Ascender's Bane exhausted
        };
        bool rxOn_ = false;
        MonsterId rxMonster_ = MonsterId::JAW_WORM;
        RxDeck rxDeck_;   // the root's deck without Slimed cards
        int rxH_ = 0, rxEnergy_ = 3, rxDraw_ = 5, rxCardsOffset_ = 0, rxRitual_ = 0;
        // Per move: its attack's base damage (-1: none), the Strength the monster
        // has gained by the next turn, the block it starts the next turn with.
        int rxAttack_[3] = {}, rxStrGain_[3] = {}, rxBlock_[4] = {};
        double rxRoll_[3][4][3] = {};
        int rxDepth_ = 0;
        // Open addressing, power-of-two table: every bound query looks up start states.
        class RxIndex {
            static constexpr std::uint64_t kEmpty = ~0ULL;   // no key has its top bits set
            std::vector<std::uint64_t> keys_;
            std::vector<std::size_t> vals_;
            std::size_t size_ = 0;
            std::size_t slot(std::uint64_t k) const {
                const std::size_t mask = keys_.size() - 1;
                std::size_t i = static_cast<std::size_t>(splitmix(k)) & mask;
                while (keys_[i] != kEmpty && keys_[i] != k) i = (i + 1) & mask;
                return i;
            }
        public:
            std::size_t size() const { return size_; }
            bool find(std::uint64_t k, std::size_t &v) const {
                if (keys_.empty()) return false;
                const std::size_t i = slot(k);
                if (keys_[i] == kEmpty) return false;
                v = vals_[i];
                return true;
            }
            void emplace(std::uint64_t k, std::size_t v) {
                if ((size_ + 1) * 2 > keys_.size()) {
                    std::vector<std::uint64_t> oldK(keys_.empty() ? std::size_t(1) << 16 : keys_.size() * 2, kEmpty);
                    std::vector<std::size_t> oldV(oldK.size(), 0);
                    oldK.swap(keys_);
                    oldV.swap(vals_);
                    for (std::size_t j = 0; j < oldK.size(); ++j)
                        if (oldK[j] != kEmpty) { const std::size_t i = slot(oldK[j]); keys_[i] = oldK[j]; vals_[i] = oldV[j]; }
                }
                const std::size_t i = slot(k);
                if (keys_[i] == kEmpty) ++size_;
                keys_[i] = k;
                vals_[i] = v;
            }
        };
        // Start-of-turn state -> offset of its values (one per player HP 0..rxH_) in the pool;
        // table 0 the relaxed game, table 1 the abstract exact recursion.
        struct RxTable { RxIndex index; std::vector<double> pool; };
        RxTable rxTab_[2];
        std::unordered_map<std::uint64_t, double> rxLeafCache_;
        std::vector<std::vector<double>> rxWinRows_;                // per turn, the win score per HP

        // The damage of the monster's move: base + Strength for an attack (Chomp, Thrash, Dark Strike).
        int rxHit(int mv, int str) const { return rxAttack_[mv] < 0 ? 0 : rxAttack_[mv] + str; }
        static bool rxCount(const CardInstance &c, RxDeck &d) {
            if (c.upgraded || c.freeToPlayOnce) return false;
            switch (c.id) {
                case CardId::STRIKE_RED: if (c.costForTurn != 1) return false; ++d.s; return true;
                case CardId::DEFEND_RED: if (c.costForTurn != 1) return false; ++d.d; return true;
                case CardId::BASH: if (c.costForTurn != 2) return false; ++d.b; return true;
                case CardId::ASCENDERS_BANE: ++d.a; return true;
                case CardId::SLIMED: if (c.costForTurn != 1) return false; ++d.x; return true;
                default: return false;
            }
        }
        static int rxMove(MonsterMoveId id) {
            switch (id) {
                case MonsterMoveId::JAW_WORM_CHOMP: case MonsterMoveId::CULTIST_DARK_STRIKE: return RX_CHOMP;
                case MonsterMoveId::JAW_WORM_THRASH: return RX_THRASH;
                case MonsterMoveId::JAW_WORM_BELLOW: case MonsterMoveId::CULTIST_INCANTATION: return RX_BELLOW;
                case MonsterMoveId::INVALID: return RX_NONE;
                default: return -1;
            }
        }

        // The deck and turn constants of the root's fight (every model). Slimed
        // cards are not part of the fixed deck: the Small Slimes model counts the
        // ones left in its state (`slimed`), the other models refuse them.
        bool rxDeckInit(const BattleContext &r, bool slimed = false) {
            RxDeck all;
            bool ok = true;
            auto add = [&](const CardInstance &c) { ok = ok && rxCount(c, all); };
            const auto &cm = r.cards;
            for (int i = 0; i < cm.cardsInHand; ++i) add(cm.hand[i]);
            for (const auto &c : cm.drawPile) add(c);
            for (const auto &c : cm.discardPile) add(c);
            for (const auto &c : cm.exhaustPile) add(c);
            // At most one Bash keeps the play orders below exhaustive; the keys pack counts in 4 bits.
            if (!ok || all.b > 1 || all.a > 1 || all.s > 15 || all.d > 15 || (all.x && !slimed)) return false;
            all.x = 0;
            rxDeck_ = all;
            rxH_ = r.player.curHp;
            rxEnergy_ = r.player.energyPerTurn;
            rxDraw_ = r.player.cardDrawPerTurn;
            rxCardsOffset_ = r.cardsDrawn - rxDraw_ * r.turn;
            return true;
        }

        // The card part of a view: the hand and draw pile, whether Ascender's Bane
        // is exhausted; false unless every card is a starter card of the root's deck
        // or, where `slimed` is given (it gets their count), a Slimed not exhausted.
        bool rxCards(const BattleContext &s, RxDeck &hand, RxDeck &pile, bool &abGone, int *slimed = nullptr) const {
            const auto &cm = s.cards;
            RxDeck rest, ex;
            hand = pile = RxDeck{};
            for (int i = 0; i < cm.cardsInHand; ++i) if (!rxCount(cm.hand[i], hand)) return false;
            for (const auto &c : cm.drawPile) if (!rxCount(c, pile)) return false;
            for (const auto &c : cm.discardPile) if (!rxCount(c, rest)) return false;
            for (const auto &c : cm.exhaustPile) if (!rxCount(c, ex)) return false;
            if (ex.s || ex.d || ex.b) return false;
            if (!slimed && (hand.x || pile.x || rest.x || ex.x)) return false;
            for (const auto &c : cm.stasisCards) if (c.id != CardId::INVALID) return false;
            if (hand.s + pile.s + rest.s != rxDeck_.s || hand.d + pile.d + rest.d != rxDeck_.d
                || hand.b + pile.b + rest.b != rxDeck_.b || hand.a + pile.a + rest.a + ex.a != rxDeck_.a)
                return false;
            abGone = ex.a > 0;
            if (slimed) *slimed = hand.x + pile.x + rest.x;
            return true;
        }

        // The relaxed view of `s`, or false where the relaxed game does not model it.
        bool rxView(const BattleContext &s, RxView &x) const {
            if (!rxOn_ || s.outcome != Outcome::UNDECIDED || s.monsters.monsterCount != 1) return false;
            const auto &m = s.monsters.arr[0];
            if (m.id != rxMonster_ || !m.isAlive() || m.weak || m.artifact || m.strength < 0 || m.block < 0
                || m.wasJustApplied<MonsterStatus::VULNERABLE>())
                return false;
            if (rxMonster_ == MonsterId::CULTIST) {
                // Vulnerable and Ritual only; Ritual from Incantation on, none before.
                const std::uint64_t allowed = 1ULL << static_cast<int>(MonsterStatus::RITUAL)
                    | 1ULL << static_cast<int>(MonsterStatus::VULNERABLE);
                const int ritual = m.hasStatus<MonsterStatus::RITUAL>() ? m.getStatus<MonsterStatus::RITUAL>() : 0;
                if ((m.statusBits & ~allowed) || ritual != (rxMove(m.moveHistory[1]) == RX_NONE ? 0 : rxRitual_)) return false;
            }
            const auto &p = s.player;
            if (p.strength || p.dexterity || p.statusBits0 || p.statusBits1 || !p.statusMap.empty() || p.energy < 0
                || p.energyPerTurn != rxEnergy_ || p.cardDrawPerTurn != rxDraw_ || p.curHp > rxH_ || p.curHp <= 0)
                return false;
            if (s.cardsDrawn - rxDraw_ * s.turn != rxCardsOffset_ || s.turn < 0 || s.turn > 200) return false;
            x.m = m.curHp; x.mb = m.block; x.str = m.strength; x.vuln = m.vulnerable;
            x.mv0 = rxMove(m.moveHistory[0]); x.mv1 = rxMove(m.moveHistory[1]);
            if (x.mv0 < 0 || x.mv0 == RX_NONE || x.mv1 < 0) return false;
            x.h = p.curHp; x.pblock = p.block; x.e = p.energy; x.t = s.turn;
            if (x.m > 255 || x.str > 255 || x.vuln > 15) return false;
            return rxCards(s, x.hand, x.pile, x.abGone);
        }

        std::uint64_t rxKey(int m, int str, int vuln, int mv0, int mv1, const RxDeck &pile, bool abGone, int t) const {
            using U = std::uint64_t;
            if (m < 0 || m > 255 || str < 0 || str > 255 || vuln < 0 || vuln > 15 || t < 0 || t > 255)
                throw std::runtime_error("relaxed bound: state out of range");
            return U(m) | U(str) << 8 | U(vuln) << 16 | U(mv0) << 20 | U(mv1) << 22 | U(pile.s) << 24 | U(pile.d) << 28
                | U(pile.b) << 32 | U(pile.a) << 36 | U(abGone ? 1 : 0) << 40 | U(t) << 41;
        }

        // Silver's (or the HP objective's) leaf values: a win at HP h on turn t;
        // a death in the monster turn of turn t (death) or the turn-cap leaf at
        // turn t, both at monster HP m.
        double rxWin(int h, int t) {
            if (hpObjective_) return h;
            if (static_cast<int>(rxWinRows_.size()) <= t) rxWinRows_.resize(t + 1);
            auto &row = rxWinRows_[t];
            if (row.empty()) {
                row.assign(rxH_ + 1, 0);
                for (int hp = 1; hp <= rxH_; ++hp) {
                    BattleContext w = rootCopy_;
                    w.player.curHp = hp;
                    w.turn = t;
                    w.outcome = Outcome::PLAYER_VICTORY;
                    row[hp] = scorer_.scoreEndState(w);
                }
            }
            return row[h];
        }
        double rxLeaf(int m, int t, bool death) {
            if (hpObjective_) return 0;
            const std::uint64_t k = static_cast<std::uint64_t>(m) << 32 | static_cast<std::uint64_t>(t) << 1 | (death ? 1 : 0);
            if (auto it = rxLeafCache_.find(k); it != rxLeafCache_.end()) return it->second;
            BattleContext w = rootCopy_;
            w.outcome = death ? Outcome::PLAYER_LOSS : Outcome::UNDECIDED;
            w.player.curHp = death ? 0 : 1;
            w.turn = t;
            w.cardsDrawn = rxCardsOffset_ + rxDraw_ * t;
            w.energyWasted = 0;
            w.monsters.arr[0].curHp = m;
            const double v = scorer_.scoreEndState(w);
            rxLeafCache_.emplace(k, v);
            return v;
        }

        // Every play of a hand with `e` energy against a monster at HP m with
        // block mb and Vulnerable vuln: any number of Strikes and Defends the
        // energy pays for, the Bash (if played) at any position among the
        // Strikes. Calls win() for a play that kills, else end(m', vuln', maxD)
        // for every play of Strikes and Bash, with every Defend count 0..maxD.
        // Unupgraded starter cards: Strike 6, Bash 8 then 2 Vulnerable (both
        // x1.5 rounded down against Vulnerable), Defend 5 block.
        template <typename Win, typename End>
        static void rxPlays(int m, int mb, int vuln, const RxDeck &hand, int e, Win win, End end) {
            for (int nb = 0; nb <= std::min(hand.b, 1) && 2 * nb <= e; ++nb)
                for (int ns = 0; ns <= std::min(hand.s, e - 2 * nb); ++ns)
                    for (int pos = 0; pos <= (nb ? ns : 0); ++pos) {   // Strikes played before the Bash
                        int v = vuln, dmg = pos * (v > 0 ? 9 : 6);
                        if (nb) { dmg += v > 0 ? 12 : 8; v += 2; }
                        dmg += (ns - pos) * (v > 0 ? 9 : 6);
                        const int m2 = m - std::max(0, dmg - mb);
                        if (m2 <= 0) win();
                        else end(m2, v, std::min(hand.d, e - 2 * nb - ns));
                    }
        }

        // Every hand the turn's draw could deliver from draw pile `pile`, with the
        // draw pile it leaves and its probability: the whole pile first when it
        // holds fewer cards than the draw, then the rest from the discard pile
        // (every card not drawn and not exhausted, `slimed` Slimed among them
        // and the pile) shuffled; each multiset of the cards drawn from a pile is
        // hypergeometric. With free draws: any cards of the deck (probabilities
        // meaningless, the pile left empty).
        template <typename F>
        void rxHands(const RxDeck &pile, bool abGone, int slimed, bool freeDraws, F f) const {
            using exact::ChanceScript;
            RxDeck avail = rxDeck_;
            if (abGone) avail.a = 0;
            avail.x = slimed;
            RxDeck from = pile, base;
            int need = rxDraw_;
            if (freeDraws) {
                from = avail;
                need = std::min(rxDraw_, avail.total());
            } else if (pile.total() < rxDraw_) {
                base = pile;
                from = {avail.s - pile.s, avail.d - pile.d, avail.b - pile.b, avail.a - pile.a, avail.x - pile.x};
                need = std::min(rxDraw_ - pile.total(), from.total());
            }
            const double ways = ChanceScript::binom(from.total(), need);
            for (int s = 0; s <= std::min(from.s, need); ++s)
                for (int d = 0; d <= std::min(from.d, need - s); ++d)
                    for (int b = 0; b <= std::min(from.b, need - s - d); ++b)
                        for (int x = 0; x <= std::min(from.x, need - s - d - b); ++x) {
                            const int a = need - s - d - b - x;
                            if (a > from.a) continue;
                            const RxDeck hand{base.s + s, base.d + d, base.b + b, base.a + a, base.x + x};
                            const RxDeck left = freeDraws ? RxDeck{}
                                                          : RxDeck{from.s - s, from.d - d, from.b - b, from.a - a, from.x - x};
                            const double p = ChanceScript::binom(from.s, s) * ChanceScript::binom(from.d, d)
                                * ChanceScript::binom(from.b, b) * ChanceScript::binom(from.a, a)
                                * ChanceScript::binom(from.x, x) / ways;
                            f(hand, left, p);
                        }
        }

        // The value per player HP of the start of turn t (before its draw): in
        // table 0 the relaxed game's (max over hands), in table 1 the same
        // recursion's with the draw's exact probabilities (expectation over hands).
        std::size_t rxStart(int mode, int m, int str, int vuln, int mv0, int mv1, const RxDeck &pile, bool abGone, int t) {
            const bool freeDraws = mode == 0 && relaxedFreeDraws_;
            const RxDeck keyPile = freeDraws ? RxDeck{} : pile;
            const std::uint64_t key = rxKey(m, str, vuln, mv0, mv1, keyPile, abGone, t);
            if (std::size_t off; rxTab_[mode].index.find(key, off)) return off;
            const auto t0 = rxDepth_ == 0 ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
            ++rxDepth_;
            std::vector<double> value(rxH_ + 1, mode == 0 ? -1e300 : 0.0), best(rxH_ + 1);
            if (t > turnCap_) {
                std::fill(value.begin(), value.end(), rxLeaf(m, t, false));
            } else {
                rxHands(keyPile, abGone, 0, freeDraws, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    const bool gone = abGone || hand.a > 0;
                    std::fill(best.begin(), best.end(), -1e300);
                    rxPlays(m, rxBlock_[mv1], vuln, hand, rxEnergy_,
                            [&] { for (int h = 1; h <= rxH_; ++h) best[h] = std::max(best[h], rxWin(h, t)); },
                            [&](int m2, int v, int maxD) {
                                const auto g = rxAfterMonster(mode, m2, v, str, mv0, mv1, left, gone, t);
                                const double death = rxLeaf(m2, t, true);
                                for (int nd = 0; nd <= maxD; ++nd) {
                                    const int loss = std::max(0, rxHit(mv0, str) - 5 * nd);
                                    for (int h = 1; h <= rxH_; ++h)
                                        best[h] = std::max(best[h], h - loss <= 0 ? death : g[h - loss]);
                                }
                            });
                    for (int h = 1; h <= rxH_; ++h) value[h] = mode == 0 ? std::max(value[h], best[h]) : value[h] + p * best[h];
                });
            }
            --rxDepth_;
            auto &tab = rxTab_[mode];
            const std::size_t off = tab.pool.size();
            tab.pool.insert(tab.pool.end(), value.begin(), value.end());
            tab.index.emplace(key, off);
            if (rxDepth_ == 0) rxSeconds_[mode] += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            return off;
        }

        // After the monster's move `mv0` of turn t (its attack already taken off
        // the player's HP): the expected value per player HP over its next move,
        // at the start of turn t+1.
        std::vector<double> rxAfterMonster(int mode, int m, int vuln, int str, int mv0, int mv1, const RxDeck &pile, bool abGone, int t) {
            std::vector<double> g(rxH_ + 1, 0);
            if (t + 1 > turnCap_) {
                std::fill(g.begin(), g.end(), rxLeaf(m, t + 1, false));
                return g;
            }
            const int str2 = str + rxStrGain_[mv0], v2 = std::max(0, vuln - 1);
            for (int n = 0; n < 3; ++n) {
                const double p = rxRoll_[mv0][mv1][n];
                if (p <= 0) continue;
                const std::size_t off = rxStart(mode, m, str2, v2, n, mv0, pile, abGone, t + 1);
                const auto &pool = rxTab_[mode].pool;
                for (int h = 1; h <= rxH_; ++h) g[h] += p * pool[off + h];
            }
            return g;
        }

        // The value of ending the turn now (at player block pblock), at HP h.
        double rxEndAt(int mode, int m, int vuln, int str, int mv0, int mv1, const RxDeck &pile, bool abGone, int t, int pblock, int h) {
            const int hp = h - std::max(0, rxHit(mv0, str) - pblock);
            if (hp <= 0) return rxLeaf(m, t, true);
            if (t + 1 > turnCap_) return rxLeaf(m, t + 1, false);
            const int str2 = str + rxStrGain_[mv0], v2 = std::max(0, vuln - 1);
            double v = 0;
            for (int n = 0; n < 3; ++n) {
                const double p = rxRoll_[mv0][mv1][n];
                if (p <= 0) continue;
                const std::size_t off = rxStart(mode, m, str2, v2, n, mv0, pile, abGone, t + 1);
                v += p * rxTab_[mode].pool[off + hp];
            }
            return v;
        }

        // The value of a decision state (the rest of its turn played from its
        // hand), and of an end-of-turn state.
        double rxDecAt(int mode, const RxView &x) {
            double best = -1e300;
            const bool gone = x.abGone || x.hand.a > 0;
            rxPlays(x.m, x.mb, x.vuln, x.hand, x.e, [&] { best = std::max(best, rxWin(x.h, x.t)); },
                    [&](int m2, int v, int maxD) {
                        for (int nd = 0; nd <= maxD; ++nd)
                            best = std::max(best, rxEndAt(mode, m2, v, x.str, x.mv0, x.mv1, x.pile, gone, x.t, x.pblock + 5 * nd, x.h));
                    });
            return best;
        }
        double rxEndOf(int mode, const RxView &x) {
            return rxEndAt(mode, x.m, x.vuln, x.str, x.mv0, x.mv1, x.pile, x.abGone || x.hand.a > 0, x.t, x.pblock, x.h);
        }
        // Summation order differs from the exact solver's: pad by rounding error.
        static double rxPad(double v) { return v + 1e-9 * (1 + std::abs(v)); }

        static int slackBucket(double d) {
            return d < 0.5 ? 0 : d < 1 ? 1 : d < 2 ? 2 : d < 4 ? 3 : d < 8 ? 4 : d < 16 ? 5 : 6;
        }
        // --relaxed-check: the bound against an exact value.
        void rxCheck(const BattleContext &s, double exact, bool end) {
            double r = 0;
            if (s.turn > turnCap_ || !(end ? modelEnd(0, s, r) : modelDec(0, s, r))) { ++relaxedGateMisses_; return; }
            const double ub = rxPad(r);
            ++(end ? relaxedEndChecks_ : relaxedDecChecks_);
            if (ub < exact - 1e-9) {
                if (++relaxedViolations_ <= 10)
                    std::cerr << "relaxed bound violated (" << (end ? "end" : "decision") << "): bound " << ub << " exact "
                              << exact << " turn " << s.turn << " hp " << s.player.curHp << " monsters " << monsterHps(s) << '\n';
                return;
            }
            ++(end ? relaxedEndSlack_ : relaxedDecSlack_)[slackBucket(ub - exact)];
        }

        // --abstract-check: the abstract exact recursion against an exact value of the search.
        void abstractCompare(const BattleContext &s, double exact, bool end) {
            double a = 0;
            if (s.turn > turnCap_ || !(end ? modelEnd(1, s, a) : modelDec(1, s, a))) { ++relaxedGateMisses_; return; }
            ++abstractChecks_;
            const double diff = std::abs(a - exact);
            abstractMaxDiff_ = std::max(abstractMaxDiff_, diff);
            if (diff > 1e-9 * (1 + std::abs(exact)) && ++abstractMismatches_ <= 10)
                std::cerr << "abstract value differs (" << (end ? "end" : "decision") << "): abstract " << a << " exact " << exact
                          << " turn " << s.turn << " hp " << s.player.curHp << " monsters " << monsterHps(s) << '\n';
        }
        static std::string monsterHps(const BattleContext &s) {
            std::string out;
            for (int i = 0; i < s.monsters.monsterCount; ++i)
                out += (i ? "/" : "") + std::to_string(s.monsters.arr[i].curHp);
            return out;
        }

        // --relaxed-check: the engine's outcomes of ending the turn at `s` against
        // the relaxed game's monster turn, leaves and draw.
        void rxMirror(const BattleContext &s, const SAction &endTurn) {
            RxView x;
            if (!rxView(s, x)) { ++relaxedGateMisses_; return; }
            ++relaxedChecked_;
            const int hp = x.h - std::max(0, rxHit(x.mv0, x.str) - x.pblock);
            const bool gone = x.abGone || x.hand.a > 0;
            const int str2 = x.str + rxStrGain_[x.mv0], v2 = std::max(0, x.vuln - 1);
            auto bad = [&](const char *what) {
                if (++relaxedMirror_ <= 10)
                    std::cerr << "relaxed mirror mismatch: " << what << " (turn " << s.turn << " hp " << x.h << " monster "
                              << x.m << " move " << x.mv0 << ")\n";
            };
            double pMove[3] = {0, 0, 0};
            for (const auto &o : outcomes(s, endTurn)) {
                const BattleContext &n = o.state;
                if (hp <= 0) {
                    if (n.outcome != Outcome::PLAYER_LOSS) bad("expected a death");
                    else if (std::abs(terminal(n).v - rxLeaf(x.m, s.turn, true)) > 1e-9) bad("death leaf");
                    continue;
                }
                if (n.outcome != Outcome::UNDECIDED || !quiet(n)) { bad("expected a quiet undecided state"); continue; }
                const auto &mn = n.monsters.arr[0];
                if (n.turn != s.turn + 1 || n.player.curHp != hp || n.player.block != 0 || n.player.energy != rxEnergy_
                    || mn.curHp != x.m || mn.block != rxBlock_[x.mv0] || mn.strength != str2 || mn.vulnerable != v2
                    || rxMove(mn.moveHistory[1]) != x.mv0) {
                    if (relaxedMirror_ < 10)
                        std::cerr << "  engine: turn " << n.turn << " hp " << n.player.curHp << " block " << n.player.block
                                  << " energy " << int(n.player.energy) << " monster " << mn.curHp << " block " << mn.block
                                  << " str " << mn.strength << " vuln " << mn.vulnerable << " last " << rxMove(mn.moveHistory[1])
                                  << "; relaxed: hp " << hp << " block " << rxBlock_[x.mv0] << " str " << str2 << " vuln " << v2
                                  << " (pblock " << x.pblock << " mb " << x.mb << " mv1 " << x.mv1 << ")\n";
                    bad("monster turn");
                    continue;
                }
                RxView y;
                if (!rxView(n, y)) { bad("next state outside the relaxed game"); continue; }
                pMove[y.mv0] += o.p;
                if (y.abGone != gone) bad("exhaust");
                // The drawn hand and the pile it leaves must be a draw the relaxed game
                // offers, with the engine's probability (move roll times draw).
                double pDraw = -1;
                const RxDeck before = x.pile;
                rxHands(before, gone, 0, false, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    if (hand.s == y.hand.s && hand.d == y.hand.d && hand.b == y.hand.b && hand.a == y.hand.a
                        && left.s == y.pile.s && left.d == y.pile.d && left.b == y.pile.b && left.a == y.pile.a)
                        pDraw = p;
                });
                if (pDraw < 0) bad("draw");
                else if (std::abs(o.p - rxRoll_[x.mv0][x.mv1][y.mv0] * pDraw) > 1e-9) bad("draw probability");
                if (n.turn > turnCap_) {
                    if (std::abs(terminal(n).v - rxLeaf(x.m, n.turn, false)) > 1e-9) bad("cap leaf");
                } else {
                    // The start value maxes over hands: at least this hand's value.
                    const std::size_t off = rxStart(0, x.m, str2, v2, y.mv0, x.mv0, before, gone, n.turn);
                    if (rxDecAt(0, y) > rxTab_[0].pool[off + hp] + 1e-9) bad("start value below a drawn hand");
                }
            }
            if (hp > 0)
                for (int k = 0; k < 3; ++k)
                    if (std::abs(pMove[k] - rxRoll_[x.mv0][x.mv1][k]) > 1e-9) bad("move probabilities");
        }

        // The active model's value of the decision state `s` (the rest of its turn
        // played from its hand) or of ending the turn at `s`, in table `mode` (0 the
        // relaxed game, 1 the exact recursion); false where no model applies.
        bool modelDec(int mode, const BattleContext &s, double &v) {
            if (RxView x; rxView(s, x)) { v = rxDecAt(mode, x); return true; }
            if (LxView x; lxView(s, x)) { v = lxDecAt(mode, x); return true; }
            if (SxView x; sxView(s, x)) { v = sxDecAt(mode, x); return true; }
            return false;
        }
        bool modelEnd(int mode, const BattleContext &s, double &v) {
            if (RxView x; rxView(s, x)) { v = rxEndOf(mode, x); return true; }
            if (LxView x; lxView(s, x)) { v = lxEndOf(mode, x); return true; }
            if (SxView x; sxView(s, x)) { v = sxEndOf(mode, x); return true; }
            return false;
        }
        void modelMirror(const BattleContext &s, const SAction &endTurn) {
            if (rxOn_) rxMirror(s, endTurn);
            else if (lxOn_) lxMirror(s, endTurn);
            else if (sxOn_) sxMirror(s, endTurn);
        }

        // ---- Two Louse model ---------------------------------------------------
        // The Jaw Worm recursion for the starter deck against two lice
        // (MonsterSpecific.cpp): Bite for the louse's rolled damage plus Strength;
        // Red Louse's Grow (+4 Strength at A17, else +3); Green Louse's Spit Web
        // (Weak 2 on the player). Curl Up gives its block once, on the first hit
        // that gets through without killing (Monster::attackedUnblockedHelper).
        // Between turns: per louse its HP (0 once dead, every other field then 0),
        // Strength, Vulnerable, whether Curl Up is unused, its intent and last
        // move; the player's Weak; the draw pile's counts, Bane exhausted, the
        // turn; one value per player HP. The lice have no block then (Curl Up's
        // block falls off when the monsters' turn starts) and no Weak is pending
        // as just applied (that clears at the end of the round).
        enum { LX_BITE = 0, LX_SPECIAL = 1, LX_NONE = 2 };
        struct LxLouse {
            int hp = 0, str = 0, vuln = 0, block = 0, mv0 = 0, mv1 = 0;
            bool curl = false;
            bool operator==(const LxLouse &) const = default;
        };
        using LxLice = std::array<LxLouse, 2>;
        struct LxView {
            LxLice l;
            int h = 0, pblock = 0, e = 0, t = 0, weak = 0;
            RxDeck hand, pile;
            bool abGone = false;
        };
        bool lxOn_ = false, lxAsc17_ = true;
        bool lxRed_[2] = {false, false};
        int lxBite_[2] = {0, 0}, lxCurl_[2] = {0, 0}, lxGrow_ = 4;

        bool lxInit() {
            const BattleContext &r = rootCopy_;
            for (int i = 0; i < 2; ++i) {
                const auto &m = r.monsters.arr[i];
                if (m.id != MonsterId::RED_LOUSE && m.id != MonsterId::GREEN_LOUSE) return false;
                lxRed_[i] = m.id == MonsterId::RED_LOUSE;
                lxBite_[i] = m.miscInfo;
                lxCurl_[i] = m.hasStatus<MonsterStatus::CURL_UP>() ? m.getStatus<MonsterStatus::CURL_UP>() : 0;
            }
            if (!rxDeckInit(r)) return false;
            lxAsc17_ = r.ascension >= 17;
            lxGrow_ = lxAsc17_ ? 4 : 3;
            lxOn_ = true;
            LxView x;
            lxOn_ = lxView(r, x);
            return lxOn_;
        }

        static int lxMove(MonsterMoveId id) {
            switch (id) {
                case MonsterMoveId::RED_LOUSE_BITE: case MonsterMoveId::GREEN_LOUSE_BITE: return LX_BITE;
                case MonsterMoveId::RED_LOUSE_GROW: case MonsterMoveId::GREEN_LOUSE_SPIT_WEB: return LX_SPECIAL;
                case MonsterMoveId::INVALID: return LX_NONE;
                default: return -1;
            }
        }

        // The Two Louse view of `s`, or false where the model does not apply.
        bool lxView(const BattleContext &s, LxView &x) const {
            if (!lxOn_ || s.outcome != Outcome::UNDECIDED || s.monsters.monsterCount != 2) return false;
            const std::uint64_t allowed = 1ULL << static_cast<int>(MonsterStatus::CURL_UP)
                | 1ULL << static_cast<int>(MonsterStatus::VULNERABLE) | 1ULL << static_cast<int>(MonsterStatus::STRENGTH);
            int alive = 0;
            for (int i = 0; i < 2; ++i) {
                const auto &m = s.monsters.arr[i];
                auto &l = x.l[i];
                l = LxLouse{};
                if (m.id != (lxRed_[i] ? MonsterId::RED_LOUSE : MonsterId::GREEN_LOUSE)) return false;
                if (!m.isAlive()) continue;
                ++alive;
                if (m.weak || m.artifact || m.strength < 0 || m.block < 0 || m.latentDamageMask || (m.statusBits & ~allowed)
                    || m.wasJustApplied<MonsterStatus::VULNERABLE>() || m.miscInfo != lxBite_[i])
                    return false;
                l.hp = m.curHp; l.str = m.strength; l.vuln = m.vulnerable; l.block = m.block;
                l.curl = m.hasStatus<MonsterStatus::CURL_UP>();
                if (l.curl && m.getStatus<MonsterStatus::CURL_UP>() != lxCurl_[i]) return false;
                l.mv0 = lxMove(m.moveHistory[0]); l.mv1 = lxMove(m.moveHistory[1]);
                if (l.mv0 < 0 || l.mv0 == LX_NONE || l.mv1 < 0 || l.hp > 31 || l.str > 63 || l.vuln > 7) return false;
            }
            if (alive == 0 || s.monsters.monstersAlive != alive) return false;
            // Weak is the only status; a worn-off one leaves its map entry behind (Player::decrementStatus).
            const auto &p = s.player;
            const bool weak = p.hasStatus<PlayerStatus::WEAK>();
            x.weak = weak ? p.getStatus<PlayerStatus::WEAK>() : 0;
            const int statuses = __builtin_popcountll(p.statusBits0) + __builtin_popcountll(p.statusBits1);
            bool onlyWeak = true;
            for (const auto &entry : p.statusMap) onlyWeak = onlyWeak && entry.first == PlayerStatus::WEAK;
            if (p.strength || p.dexterity || p.justAppliedBits || statuses != (weak ? 1 : 0) || !onlyWeak
                || (weak && x.weak <= 0) || x.weak > 15 || p.energy < 0
                || p.energyPerTurn != rxEnergy_ || p.cardDrawPerTurn != rxDraw_ || p.curHp > rxH_ || p.curHp <= 0)
                return false;
            if (s.cardsDrawn - rxDraw_ * s.turn != rxCardsOffset_ || s.turn < 0 || s.turn > 200) return false;
            x.h = p.curHp; x.pblock = p.block; x.e = p.energy; x.t = s.turn;
            return rxCards(s, x.hand, x.pile, x.abGone);
        }

        std::uint64_t lxKey(const LxLice &l, int weak, const RxDeck &pile, bool abGone, int t) const {
            using U = std::uint64_t;
            U k = 0;
            for (int i = 0; i < 2; ++i) {
                const auto &x = l[i];
                if (x.hp < 0 || x.hp > 31 || x.str < 0 || x.str > 63 || x.vuln < 0 || x.vuln > 7 || x.block)
                    throw std::runtime_error("Two Louse model: state out of range");
                k |= (U(x.hp) | U(x.str) << 5 | U(x.vuln) << 11 | U(x.curl ? 1 : 0) << 14 | U(x.mv0) << 15 | U(x.mv1) << 16)
                    << (18 * i);
            }
            if (weak < 0 || weak > 15 || t < 0 || t > 255 || pile.b > 1 || pile.a > 1)
                throw std::runtime_error("Two Louse model: state out of range");
            return k | U(weak) << 36 | U(pile.s) << 40 | U(pile.d) << 44 | U(pile.b) << 48 | U(pile.a) << 49
                | U(abGone ? 1 : 0) << 50 | U(t) << 51;
        }

        // Silver's (or the HP objective's) value of a death in the monster turn of
        // turn t (death) or of the turn-cap leaf at turn t, at lice HP m0, m1.
        double lxLeaf(int m0, int m1, int t, bool death) {
            if (hpObjective_) return 0;
            const std::uint64_t k = static_cast<std::uint64_t>(m0) << 40 | static_cast<std::uint64_t>(m1) << 32
                | static_cast<std::uint64_t>(t) << 1 | (death ? 1 : 0);
            if (auto it = rxLeafCache_.find(k); it != rxLeafCache_.end()) return it->second;
            BattleContext w = rootCopy_;
            w.outcome = death ? Outcome::PLAYER_LOSS : Outcome::UNDECIDED;
            w.player.curHp = death ? 0 : 1;
            w.turn = t;
            w.cardsDrawn = rxCardsOffset_ + rxDraw_ * t;
            w.energyWasted = 0;
            w.monsters.arr[0].curHp = m0;
            w.monsters.arr[1].curHp = m1;
            w.monsters.monstersAlive = (m0 > 0 ? 1 : 0) + (m1 > 0 ? 1 : 0);
            const double v = scorer_.scoreEndState(w);
            rxLeafCache_.emplace(k, v);
            return v;
        }

        // A card's damage as BattleContext::calculateCardDamage computes it here:
        // x0.75 while the player is Weak, x1.5 against Vulnerable, in floats, rounded down.
        static int lxDamage(int base, bool weak, bool vuln) {
            float d = static_cast<float>(base);
            if (weak) d *= .75f;
            if (vuln) d *= 1.5f;
            return std::max(0, static_cast<int>(d));
        }
        // An attack on louse i: its block first; damage that gets through and does
        // not kill curls it up (its Curl Up block after the card); a dead louse is zeroed.
        void lxHit(LxLouse &l, int i, int dmg) const {
            const int through = dmg - l.block;
            l.block = std::max(0, l.block - dmg);
            if (through <= 0) return;
            if (l.curl && through < l.hp) { l.block += lxCurl_[i]; l.curl = false; }
            l.hp -= through;
            if (l.hp <= 0) l = LxLouse{};
        }

        // Every play of a hand with `e` energy: any sequence of the hand's Strikes
        // and Bash the energy pays for, each at a living louse (Strike 6, Bash 8
        // then Vulnerable 2), then as many Defends as the energy left pays for
        // (block only ever saves HP). Calls win() if a play kills both lice, and
        // end(lice, d) once per distinct state of the lice after the attacks, with
        // the most Defends d any play reaching it leaves energy for.
        template <typename Win, typename End>
        void lxPlays(const LxLice &start, const RxDeck &hand, int e, bool weak, Win win, End end) const {
            std::vector<std::pair<LxLice, int>> seen;
            bool won = false;
            auto rec = [&](auto &&self, const LxLice &cur, int s, int b, int en) -> void {
                if (cur[0].hp == 0 && cur[1].hp == 0) { won = true; return; }
                LxLice key = cur;
                for (auto &l : key) l.block = 0;   // the lice's block falls off before it matters again
                const int d = std::min(hand.d, en);
                bool found = false;
                for (auto &[k, dd] : seen)
                    if (k == key) { dd = std::max(dd, d); found = true; break; }
                if (!found) seen.emplace_back(key, d);
                for (int i = 0; i < 2; ++i) {
                    if (cur[i].hp == 0) continue;
                    if (s > 0 && en >= 1) {
                        LxLice n = cur;
                        lxHit(n[i], i, lxDamage(6, weak, n[i].vuln > 0));
                        self(self, n, s - 1, b, en - 1);
                    }
                    if (b > 0 && en >= 2) {
                        LxLice n = cur;
                        lxHit(n[i], i, lxDamage(8, weak, n[i].vuln > 0));
                        if (n[i].hp > 0) n[i].vuln += 2;
                        self(self, n, s, b - 1, en - 2);
                    }
                }
            };
            rec(rec, start, hand.s, hand.b, e);
            if (won) win();
            for (const auto &[k, d] : seen) end(k, d);
        }

        // The chance that a louse's next move is its special one (Grow / Spit Web)
        // after the move `last` with `before` before it: roll 0..99, below 25 the
        // special unless it was last (and, below A17, also before), else Bite
        // unless Bite was both last and before.
        double lxSpecialP(int last, int before) const {
            double p = 0;
            if (!(last == LX_SPECIAL && (lxAsc17_ || before == LX_SPECIAL))) p += 0.25;
            if (last == LX_BITE && before == LX_BITE) p += 0.75;
            return p;
        }
        // The lice's turn after the player's: returns the Bites' damage (the
        // player's block not yet taken off) and sets the state at the start of
        // the next turn before the new moves (Grow's Strength, Spit Web's Weak,
        // one Vulnerable off, and one Weak off unless Spit Web gave it to a player
        // without Weak this round, Player::debuff), with each louse's chance of a
        // special next move.
        int lxMonsterTurn(const LxLice &l, int weak, LxLice &next, int &weak2, double (&pSp)[2]) const {
            int dmg = 0, spits = 0;
            next = l;
            for (int i = 0; i < 2; ++i) {
                auto &n = next[i];
                pSp[i] = 0;
                if (n.hp == 0) continue;
                n.block = 0;
                if (n.mv0 == LX_BITE) dmg += lxBite_[i] + n.str;
                else if (lxRed_[i]) n.str += lxGrow_;
                else ++spits;
                n.vuln = std::max(0, n.vuln - 1);
                pSp[i] = lxSpecialP(n.mv0, n.mv1);
                n.mv1 = n.mv0;
            }
            weak2 = spits ? (weak == 0 ? 2 * spits : weak + 2 * spits - 1) : std::max(0, weak - 1);
            return dmg;
        }
        // Each joint next move of the living lice, with its probability.
        template <typename F>
        void lxRolls(const LxLice &next, const double (&pSp)[2], F f) const {
            for (int a = 0; a < (next[0].hp ? 2 : 1); ++a) {
                const double pa = next[0].hp ? (a ? pSp[0] : 1 - pSp[0]) : 1.0;
                if (pa <= 0) continue;
                for (int b = 0; b < (next[1].hp ? 2 : 1); ++b) {
                    const double pb = next[1].hp ? (b ? pSp[1] : 1 - pSp[1]) : 1.0;
                    if (pb <= 0) continue;
                    LxLice n = next;
                    if (n[0].hp) n[0].mv0 = a ? LX_SPECIAL : LX_BITE;
                    if (n[1].hp) n[1].mv0 = b ? LX_SPECIAL : LX_BITE;
                    f(n, pa * pb);
                }
            }
        }

        // The value per player HP of the start of turn t (before its draw), as rxStart.
        std::size_t lxStart(int mode, const LxLice &l, int weak, const RxDeck &pile, bool abGone, int t) {
            const std::uint64_t key = lxKey(l, weak, pile, abGone, t);
            if (std::size_t off; rxTab_[mode].index.find(key, off)) return off;
            const auto t0 = rxDepth_ == 0 ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
            ++rxDepth_;
            std::vector<double> value(rxH_ + 1, mode == 0 ? -1e300 : 0.0), best(rxH_ + 1);
            if (t > turnCap_) {
                std::fill(value.begin(), value.end(), lxLeaf(l[0].hp, l[1].hp, t, false));
            } else {
                rxHands(pile, abGone, 0, false, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    const bool gone = abGone || hand.a > 0;
                    std::fill(best.begin(), best.end(), -1e300);
                    lxPlays(l, hand, rxEnergy_, weak > 0,
                            [&] { for (int h = 1; h <= rxH_; ++h) best[h] = std::max(best[h], rxWin(h, t)); },
                            [&](const LxLice &post, int maxD) {
                                LxLice next;
                                int weak2 = 0;
                                double pSp[2];
                                const int loss = std::max(0, lxMonsterTurn(post, weak, next, weak2, pSp) - 5 * maxD);
                                const auto g = lxAfter(mode, next, pSp, weak2, left, gone, t);
                                const double death = lxLeaf(post[0].hp, post[1].hp, t, true);
                                for (int h = 1; h <= rxH_; ++h)
                                    best[h] = std::max(best[h], h - loss <= 0 ? death : g[h - loss]);
                            });
                    for (int h = 1; h <= rxH_; ++h) value[h] = mode == 0 ? std::max(value[h], best[h]) : value[h] + p * best[h];
                });
            }
            --rxDepth_;
            auto &tab = rxTab_[mode];
            const std::size_t off = tab.pool.size();
            tab.pool.insert(tab.pool.end(), value.begin(), value.end());
            tab.index.emplace(key, off);
            if (rxDepth_ == 0) rxSeconds_[mode] += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            return off;
        }

        // After the lice's turn of turn t: the expected start value per player HP of
        // turn t+1 over their new moves (the cap leaf past the turn cap).
        std::vector<double> lxAfter(int mode, const LxLice &next, const double (&pSp)[2], int weak2, const RxDeck &pile,
                                    bool abGone, int t) {
            std::vector<double> g(rxH_ + 1, 0);
            if (t + 1 > turnCap_) {
                std::fill(g.begin(), g.end(), lxLeaf(next[0].hp, next[1].hp, t + 1, false));
                return g;
            }
            lxRolls(next, pSp, [&](const LxLice &n, double p) {
                const std::size_t off = lxStart(mode, n, weak2, pile, abGone, t + 1);
                const auto &pool = rxTab_[mode].pool;
                for (int h = 1; h <= rxH_; ++h) g[h] += p * pool[off + h];
            });
            return g;
        }

        // The value of ending the turn now (at player block pblock), at HP h.
        double lxEndAt(int mode, const LxLice &l, int weak, const RxDeck &pile, bool abGone, int t, int pblock, int h) {
            LxLice next;
            int weak2 = 0;
            double pSp[2];
            const int hp = h - std::max(0, lxMonsterTurn(l, weak, next, weak2, pSp) - pblock);
            if (hp <= 0) return lxLeaf(l[0].hp, l[1].hp, t, true);
            if (t + 1 > turnCap_) return lxLeaf(l[0].hp, l[1].hp, t + 1, false);
            double v = 0;
            lxRolls(next, pSp, [&](const LxLice &n, double p) {
                const std::size_t off = lxStart(mode, n, weak2, pile, abGone, t + 1);
                v += p * rxTab_[mode].pool[off + hp];
            });
            return v;
        }

        // The value of a decision state (the rest of its turn played from its
        // hand), and of an end-of-turn state.
        double lxDecAt(int mode, const LxView &x) {
            double best = -1e300;
            const bool gone = x.abGone || x.hand.a > 0;
            lxPlays(x.l, x.hand, x.e, x.weak > 0, [&] { best = std::max(best, rxWin(x.h, x.t)); },
                    [&](const LxLice &post, int maxD) {
                        best = std::max(best, lxEndAt(mode, post, x.weak, x.pile, gone, x.t, x.pblock + 5 * maxD, x.h));
                    });
            return best;
        }
        double lxEndOf(int mode, const LxView &x) {
            return lxEndAt(mode, x.l, x.weak, x.pile, x.abGone || x.hand.a > 0, x.t, x.pblock, x.h);
        }

        // --relaxed-check: the engine's outcomes of ending the turn at `s` against
        // the model's lice turn, leaves and draw.
        void lxMirror(const BattleContext &s, const SAction &endTurn) {
            LxView x;
            if (!lxView(s, x)) { ++relaxedGateMisses_; return; }
            ++relaxedChecked_;
            LxLice next;
            int weak2 = 0;
            double pSp[2];
            const int hp = x.h - std::max(0, lxMonsterTurn(x.l, x.weak, next, weak2, pSp) - x.pblock);
            const bool gone = x.abGone || x.hand.a > 0;
            auto bad = [&](const char *what) {
                if (++relaxedMirror_ <= 10)
                    std::cerr << "Two Louse mirror mismatch: " << what << " (turn " << s.turn << " hp " << x.h << " lice "
                              << x.l[0].hp << "/" << x.l[1].hp << " moves " << x.l[0].mv0 << "/" << x.l[1].mv0 << " weak "
                              << x.weak << ")\n";
            };
            double pMove[2][2] = {};
            for (const auto &o : outcomes(s, endTurn)) {
                const BattleContext &n = o.state;
                if (hp <= 0) {
                    if (n.outcome != Outcome::PLAYER_LOSS) bad("expected a death");
                    else if (std::abs(terminal(n).v - lxLeaf(x.l[0].hp, x.l[1].hp, s.turn, true)) > 1e-9) bad("death leaf");
                    continue;
                }
                if (n.outcome != Outcome::UNDECIDED || !quiet(n)) { bad("expected a quiet undecided state"); continue; }
                if (n.turn != s.turn + 1 || n.player.curHp != hp || n.player.block != 0 || n.player.energy != rxEnergy_) {
                    bad("player at the turn start");
                    continue;
                }
                LxView y;
                if (!lxView(n, y)) { bad("next state outside the model"); continue; }
                bool same = y.weak == weak2 && y.abGone == gone;
                for (int i = 0; i < 2; ++i) {
                    const auto &a = y.l[i], &b = next[i];
                    same = same && a.hp == b.hp && a.str == b.str && a.vuln == b.vuln && a.block == 0 && a.curl == b.curl
                        && a.mv1 == b.mv1;
                }
                if (!same) {
                    if (relaxedMirror_ < 10)
                        for (int i = 0; i < 2; ++i)
                            std::cerr << "  louse " << i << " engine: hp " << y.l[i].hp << " str " << y.l[i].str << " vuln "
                                      << y.l[i].vuln << " block " << y.l[i].block << " curl " << y.l[i].curl << " last "
                                      << y.l[i].mv1 << "; model: hp " << next[i].hp << " str " << next[i].str << " vuln "
                                      << next[i].vuln << " curl " << next[i].curl << " last " << next[i].mv1 << " (weak engine "
                                      << y.weak << " model " << weak2 << ")\n";
                    bad("lice turn");
                    continue;
                }
                const int r0 = y.l[0].hp ? y.l[0].mv0 : 0, r1 = y.l[1].hp ? y.l[1].mv0 : 0;
                pMove[r0][r1] += o.p;
                // The drawn hand and the pile it leaves must be a draw the model
                // offers, with the engine's probability (both move rolls times draw).
                double pDraw = -1;
                rxHands(x.pile, gone, 0, false, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    if (hand == y.hand && left == y.pile) pDraw = p;
                });
                const double pRoll = (y.l[0].hp ? (r0 ? pSp[0] : 1 - pSp[0]) : 1.0) * (y.l[1].hp ? (r1 ? pSp[1] : 1 - pSp[1]) : 1.0);
                if (pDraw < 0) bad("draw");
                else if (std::abs(o.p - pRoll * pDraw) > 1e-9) bad("draw probability");
                if (n.turn > turnCap_) {
                    if (std::abs(terminal(n).v - lxLeaf(y.l[0].hp, y.l[1].hp, n.turn, false)) > 1e-9) bad("cap leaf");
                } else {
                    // The start value maxes over hands: at least this hand's value.
                    const std::size_t off = lxStart(0, y.l, weak2, x.pile, gone, n.turn);
                    if (lxDecAt(0, y) > rxTab_[0].pool[off + hp] + 1e-9) bad("start value below a drawn hand");
                }
            }
            if (hp > 0)
                for (int a = 0; a < 2; ++a)
                    for (int b = 0; b < 2; ++b) {
                        const double pa = next[0].hp ? (a ? pSp[0] : 1 - pSp[0]) : (a ? 0.0 : 1.0);
                        const double pb = next[1].hp ? (b ? pSp[1] : 1 - pSp[1]) : (b ? 0.0 : 1.0);
                        if (std::abs(pMove[a][b] - pa * pb) > 1e-9) bad("move probabilities");
                    }
        }

        // ---- Small Slimes model ------------------------------------------------
        // The same recursion for the starter deck against Small Slimes at A17+
        // (MonsterGroup.cpp: Spike Slime (S) with Acid Slime (M), or Acid Slime (S)
        // with Spike Slime (M); MonsterSpecific.cpp): Acid Slime (S) alternates Lick
        // (Weak 1) and Tackle 4; Spike Slime (S) Tackles for 6 every turn; Acid
        // Slime (M) rolls Corrosive Spit (8, and a Slimed into the discard pile),
        // Tackle 12 and Lick (Weak 1); Spike Slime (M) rolls Flame Tackle (10, and a
        // Slimed) and Lick (Frail 1). No block, Strength or split. A Slimed costs 1
        // and exhausts; Frail makes a Defend 3 block (BattleContext::calculateCardBlock).
        // Between turns: per slime its HP (0 once dead, every other field then 0),
        // Vulnerable, intent and last move; the player's Weak and Frail; the draw
        // pile's counts (Slimed included), the Slimed cards not exhausted, Bane
        // exhausted, the turn; one value per player HP.
        enum { SX_NONE = 3 };
        struct SxSlime {
            int hp = 0, vuln = 0, mv0 = 0, mv1 = 0;
            bool operator==(const SxSlime &) const = default;
        };
        using SxSlimes = std::array<SxSlime, 2>;
        struct SxView {
            SxSlimes l;
            int h = 0, pblock = 0, e = 0, t = 0, weak = 0, frail = 0, slimed = 0;
            RxDeck hand, pile;
            bool abGone = false;
        };
        bool sxOn_ = false;
        MonsterId sxKind_[2] = {MonsterId::INVALID, MonsterId::INVALID};
        // Per slime and move: its damage, the Slimed it adds, the Weak and Frail it
        // gives; and its next move's chances after the move `last` with `before` before it.
        int sxDmg_[2][3] = {}, sxAdd_[2][3] = {}, sxWeak_[2][3] = {}, sxFrail_[2][3] = {};
        double sxRoll_[2][3][4][3] = {};

        bool sxInit() {
            const BattleContext &r = rootCopy_;
            if (r.ascension < 17) return false;
            using exact::ChanceScript;
            // randomBoolean() is a fair coin; randomBoolean(f) the engine's float flip.
            const double coin = 0.5, b05 = ChanceScript::booleanProbability(0.5f), b04 = ChanceScript::booleanProbability(0.4f);
            for (int i = 0; i < 2; ++i) {
                sxKind_[i] = r.monsters.arr[i].id;
                auto &roll = sxRoll_[i];
                switch (sxKind_[i]) {
                    case MonsterId::ACID_SLIME_S:   // 0 Tackle, 1 Lick; each sets the other
                        sxDmg_[i][0] = 4; sxWeak_[i][1] = 1;
                        for (int before = 0; before < 4; ++before) { roll[0][before][1] = 1; roll[1][before][0] = 1; }
                        break;
                    case MonsterId::SPIKE_SLIME_S:  // 0 Tackle, every turn
                        sxDmg_[i][0] = 6;
                        for (int before = 0; before < 4; ++before) roll[0][before][0] = 1;
                        break;
                    case MonsterId::ACID_SLIME_M:   // 0 Corrosive Spit, 1 Tackle, 2 Lick; roll 0..99
                        sxDmg_[i][0] = 8; sxAdd_[i][0] = 1; sxDmg_[i][1] = 12; sxWeak_[i][2] = 1;
                        for (int last = 0; last < 3; ++last)
                            for (int before = 0; before < 4; ++before) {
                                double *p = roll[last][before];
                                if (last == 0 && before == 0) { p[1] += 0.4 * coin; p[2] += 0.4 * (1 - coin); } else p[0] += 0.4;
                                if (last == 1 && before == 1) { p[0] += 0.4 * b05; p[2] += 0.4 * (1 - b05); } else p[1] += 0.4;
                                if (last == 2) { p[0] += 0.2 * b04; p[1] += 0.2 * (1 - b04); } else p[2] += 0.2;
                            }
                        break;
                    case MonsterId::SPIKE_SLIME_M:  // 0 Flame Tackle, 1 Lick; roll 0..99
                        sxDmg_[i][0] = 10; sxAdd_[i][0] = 1; sxFrail_[i][1] = 1;
                        for (int last = 0; last < 2; ++last)
                            for (int before = 0; before < 4; ++before) {
                                double *p = roll[last][before];
                                if (last == 0 && before == 0) p[1] += 0.3; else p[0] += 0.3;
                                if (last == 1) p[0] += 0.7; else p[1] += 0.7;
                            }
                        break;
                    default: return false;
                }
            }
            if (!rxDeckInit(r, true)) return false;
            sxOn_ = true;
            SxView x;
            sxOn_ = sxView(r, x);
            return sxOn_;
        }

        static int sxMove(MonsterMoveId id) {
            switch (id) {
                case MonsterMoveId::ACID_SLIME_S_TACKLE: case MonsterMoveId::SPIKE_SLIME_S_TACKLE:
                case MonsterMoveId::ACID_SLIME_M_CORROSIVE_SPIT: case MonsterMoveId::SPIKE_SLIME_M_FLAME_TACKLE: return 0;
                case MonsterMoveId::ACID_SLIME_S_LICK: case MonsterMoveId::ACID_SLIME_M_TACKLE:
                case MonsterMoveId::SPIKE_SLIME_M_LICK: return 1;
                case MonsterMoveId::ACID_SLIME_M_LICK: return 2;
                case MonsterMoveId::INVALID: return SX_NONE;
                default: return -1;
            }
        }

        // The Small Slimes view of `s`, or false where the model does not apply.
        bool sxView(const BattleContext &s, SxView &x) const {
            if (!sxOn_ || s.outcome != Outcome::UNDECIDED || s.monsters.monsterCount != 2) return false;
            const std::uint64_t allowed = 1ULL << static_cast<int>(MonsterStatus::VULNERABLE);
            int alive = 0;
            for (int i = 0; i < 2; ++i) {
                const auto &m = s.monsters.arr[i];
                auto &l = x.l[i];
                l = SxSlime{};
                if (m.id != sxKind_[i]) return false;
                if (!m.isAlive()) continue;
                ++alive;
                if (m.weak || m.artifact || m.strength || m.block || m.latentDamageMask || (m.statusBits & ~allowed))
                    return false;
                l.hp = m.curHp; l.vuln = m.vulnerable;
                l.mv0 = sxMove(m.moveHistory[0]); l.mv1 = sxMove(m.moveHistory[1]);
                if (l.mv0 < 0 || l.mv0 == SX_NONE || l.mv1 < 0 || l.hp > 63 || l.vuln > 15) return false;
            }
            if (alive == 0 || s.monsters.monstersAlive != alive) return false;
            // Weak and Frail are the only statuses; a worn-off one leaves its map entry behind (Player::decrementStatus).
            const auto &p = s.player;
            const bool weak = p.hasStatus<PlayerStatus::WEAK>(), frail = p.hasStatus<PlayerStatus::FRAIL>();
            x.weak = weak ? p.getStatus<PlayerStatus::WEAK>() : 0;
            x.frail = frail ? p.getStatus<PlayerStatus::FRAIL>() : 0;
            const int statuses = __builtin_popcountll(p.statusBits0) + __builtin_popcountll(p.statusBits1);
            bool known = true;
            for (const auto &entry : p.statusMap)
                known = known && (entry.first == PlayerStatus::WEAK || entry.first == PlayerStatus::FRAIL);
            if (p.strength || p.dexterity || p.justAppliedBits || statuses != (weak ? 1 : 0) + (frail ? 1 : 0) || !known
                || (weak && x.weak <= 0) || (frail && x.frail <= 0) || x.weak > 3 || x.frail > 3 || p.energy < 0
                || p.energyPerTurn != rxEnergy_ || p.cardDrawPerTurn != rxDraw_ || p.curHp > rxH_ || p.curHp <= 0)
                return false;
            if (s.cardsDrawn - rxDraw_ * s.turn != rxCardsOffset_ || s.turn < 0 || s.turn > 200) return false;
            x.h = p.curHp; x.pblock = p.block; x.e = p.energy; x.t = s.turn;
            return rxCards(s, x.hand, x.pile, x.abGone, &x.slimed) && x.slimed <= 15;
        }

        std::uint64_t sxKey(const SxSlimes &l, int weak, int frail, int slimed, const RxDeck &pile, bool abGone, int t) const {
            using U = std::uint64_t;
            U k = 0;
            for (int i = 0; i < 2; ++i) {
                const auto &x = l[i];
                if (x.hp < 0 || x.hp > 63 || x.vuln < 0 || x.vuln > 15)
                    throw std::runtime_error("Small Slimes model: state out of range");
                k |= (U(x.hp) | U(x.vuln) << 6 | U(x.mv0) << 10 | U(x.mv1) << 12) << (14 * i);
            }
            if (weak < 0 || weak > 3 || frail < 0 || frail > 3 || slimed < 0 || slimed > 15 || pile.x > 15 || pile.b > 1
                || pile.a > 1 || t < 0 || t > 255)
                throw std::runtime_error("Small Slimes model: state out of range");
            return k | U(weak) << 28 | U(frail) << 30 | U(pile.s) << 32 | U(pile.d) << 36 | U(pile.b) << 40 | U(pile.a) << 41
                | U(pile.x) << 42 | U(slimed) << 46 | U(abGone ? 1 : 0) << 50 | U(t) << 51;
        }

        // Every play of a hand with `e` energy: any sequence of the hand's Strikes
        // and Bash the energy pays for, each at a living slime (as lxPlays, the
        // slimes without block). Calls win() if a play kills both slimes, and
        // end(slimes, e') once per distinct state of the slimes after the attacks,
        // with the most energy e' any play reaching it leaves for Slimed and Defends.
        template <typename Win, typename End>
        void sxPlays(const SxSlimes &start, const RxDeck &hand, int e, bool weak, Win win, End end) const {
            std::vector<std::pair<SxSlimes, int>> seen;
            bool won = false;
            auto hit = [](SxSlime &l, int dmg) { l.hp -= dmg; if (l.hp <= 0) l = SxSlime{}; };
            auto rec = [&](auto &&self, const SxSlimes &cur, int s, int b, int en) -> void {
                if (cur[0].hp == 0 && cur[1].hp == 0) { won = true; return; }
                bool found = false;
                for (auto &[k, ee] : seen)
                    if (k == cur) { ee = std::max(ee, en); found = true; break; }
                if (!found) seen.emplace_back(cur, en);
                for (int i = 0; i < 2; ++i) {
                    if (cur[i].hp == 0) continue;
                    if (s > 0 && en >= 1) {
                        SxSlimes n = cur;
                        hit(n[i], lxDamage(6, weak, n[i].vuln > 0));
                        self(self, n, s - 1, b, en - 1);
                    }
                    if (b > 0 && en >= 2) {
                        SxSlimes n = cur;
                        hit(n[i], lxDamage(8, weak, n[i].vuln > 0));
                        if (n[i].hp > 0) n[i].vuln += 2;
                        self(self, n, s, b - 1, en - 2);
                    }
                }
            };
            rec(rec, start, hand.s, hand.b, e);
            if (won) win();
            for (const auto &[k, en] : seen) end(k, en);
        }

        // The slimes' turn after the player's: returns the attacks' damage (the
        // player's block not yet taken off) and sets the state at the start of the
        // next turn before the new moves (one Vulnerable off; the Licks' Weak and
        // Frail, one of each off unless a Lick gave it to a player without it this
        // round, Player::debuff), the Slimed cards the attacks put into the discard
        // pile, and each slime's next-move chances.
        int sxMonsterTurn(const SxSlimes &l, int weak, int frail, SxSlimes &next, int &weak2, int &frail2, int &added,
                          double (&pN)[2][3]) const {
            int dmg = 0, wk = 0, fr = 0;
            added = 0;
            next = l;
            for (int i = 0; i < 2; ++i) {
                auto &n = next[i];
                for (int k = 0; k < 3; ++k) pN[i][k] = 0;
                if (n.hp == 0) continue;
                dmg += sxDmg_[i][n.mv0];
                added += sxAdd_[i][n.mv0];
                wk += sxWeak_[i][n.mv0];
                fr += sxFrail_[i][n.mv0];
                n.vuln = std::max(0, n.vuln - 1);
                for (int k = 0; k < 3; ++k) pN[i][k] = sxRoll_[i][n.mv0][n.mv1][k];
                n.mv1 = n.mv0;
            }
            weak2 = wk ? (weak == 0 ? wk : weak + wk - 1) : std::max(0, weak - 1);
            frail2 = fr ? (frail == 0 ? fr : frail + fr - 1) : std::max(0, frail - 1);
            return dmg;
        }
        // Each joint next move of the living slimes, with its probability.
        template <typename F>
        void sxRolls(const SxSlimes &next, const double (&pN)[2][3], F f) const {
            for (int a = 0; a < 3; ++a) {
                const double pa = next[0].hp ? pN[0][a] : (a ? 0.0 : 1.0);
                if (pa <= 0) continue;
                for (int b = 0; b < 3; ++b) {
                    const double pb = next[1].hp ? pN[1][b] : (b ? 0.0 : 1.0);
                    if (pb <= 0) continue;
                    SxSlimes n = next;
                    if (n[0].hp) n[0].mv0 = a;
                    if (n[1].hp) n[1].mv0 = b;
                    f(n, pa * pb);
                }
            }
        }

        // The value per player HP of the start of turn t (before its draw), as
        // rxStart; `slimed` Slimed cards are in the draw and discard piles.
        std::size_t sxStart(int mode, const SxSlimes &l, int weak, int frail, int slimed, const RxDeck &pile, bool abGone, int t) {
            const std::uint64_t key = sxKey(l, weak, frail, slimed, pile, abGone, t);
            if (std::size_t off; rxTab_[mode].index.find(key, off)) return off;
            const auto t0 = rxDepth_ == 0 ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
            ++rxDepth_;
            std::vector<double> value(rxH_ + 1, mode == 0 ? -1e300 : 0.0), best(rxH_ + 1);
            if (t > turnCap_) {
                std::fill(value.begin(), value.end(), lxLeaf(l[0].hp, l[1].hp, t, false));
            } else {
                const int per = frail > 0 ? 3 : 5;   // a Defend's block
                rxHands(pile, abGone, slimed, false, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    const bool gone = abGone || hand.a > 0;
                    std::fill(best.begin(), best.end(), -1e300);
                    sxPlays(l, hand, rxEnergy_, weak > 0,
                            [&] { for (int h = 1; h <= rxH_; ++h) best[h] = std::max(best[h], rxWin(h, t)); },
                            [&](const SxSlimes &post, int en) {
                                SxSlimes next;
                                int weak2 = 0, frail2 = 0, added = 0;
                                double pN[2][3];
                                const int dmg = sxMonsterTurn(post, weak, frail, next, weak2, frail2, added, pN);
                                const double death = lxLeaf(post[0].hp, post[1].hp, t, true);
                                // nx Slimed played, then as many Defends as the energy left pays for.
                                for (int nx = 0; nx <= std::min(hand.x, en); ++nx) {
                                    const int loss = std::max(0, dmg - per * std::min(hand.d, en - nx));
                                    const auto g = sxAfter(mode, next, pN, weak2, frail2, slimed - nx + added, left, gone, t);
                                    for (int h = 1; h <= rxH_; ++h)
                                        best[h] = std::max(best[h], h - loss <= 0 ? death : g[h - loss]);
                                }
                            });
                    for (int h = 1; h <= rxH_; ++h) value[h] = mode == 0 ? std::max(value[h], best[h]) : value[h] + p * best[h];
                });
            }
            --rxDepth_;
            auto &tab = rxTab_[mode];
            const std::size_t off = tab.pool.size();
            tab.pool.insert(tab.pool.end(), value.begin(), value.end());
            tab.index.emplace(key, off);
            if (rxDepth_ == 0) rxSeconds_[mode] += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            return off;
        }

        // After the slimes' turn of turn t: the expected start value per player HP
        // of turn t+1 over their new moves (the cap leaf past the turn cap).
        std::vector<double> sxAfter(int mode, const SxSlimes &next, const double (&pN)[2][3], int weak2, int frail2,
                                    int slimed, const RxDeck &pile, bool abGone, int t) {
            std::vector<double> g(rxH_ + 1, 0);
            if (t + 1 > turnCap_) {
                std::fill(g.begin(), g.end(), lxLeaf(next[0].hp, next[1].hp, t + 1, false));
                return g;
            }
            sxRolls(next, pN, [&](const SxSlimes &n, double p) {
                const std::size_t off = sxStart(mode, n, weak2, frail2, slimed, pile, abGone, t + 1);
                const auto &pool = rxTab_[mode].pool;
                for (int h = 1; h <= rxH_; ++h) g[h] += p * pool[off + h];
            });
            return g;
        }

        // The value of ending the turn now (at player block pblock, `slimed`
        // Slimed not exhausted), at HP h.
        double sxEndAt(int mode, const SxSlimes &l, int weak, int frail, int slimed, const RxDeck &pile, bool abGone, int t,
                       int pblock, int h) {
            SxSlimes next;
            int weak2 = 0, frail2 = 0, added = 0;
            double pN[2][3];
            const int hp = h - std::max(0, sxMonsterTurn(l, weak, frail, next, weak2, frail2, added, pN) - pblock);
            if (hp <= 0) return lxLeaf(l[0].hp, l[1].hp, t, true);
            if (t + 1 > turnCap_) return lxLeaf(l[0].hp, l[1].hp, t + 1, false);
            double v = 0;
            sxRolls(next, pN, [&](const SxSlimes &n, double p) {
                const std::size_t off = sxStart(mode, n, weak2, frail2, slimed + added, pile, abGone, t + 1);
                v += p * rxTab_[mode].pool[off + hp];
            });
            return v;
        }

        // The value of a decision state (the rest of its turn played from its
        // hand), and of an end-of-turn state.
        double sxDecAt(int mode, const SxView &x) {
            double best = -1e300;
            const bool gone = x.abGone || x.hand.a > 0;
            const int per = x.frail > 0 ? 3 : 5;
            sxPlays(x.l, x.hand, x.e, x.weak > 0, [&] { best = std::max(best, rxWin(x.h, x.t)); },
                    [&](const SxSlimes &post, int en) {
                        for (int nx = 0; nx <= std::min(x.hand.x, en); ++nx)
                            best = std::max(best, sxEndAt(mode, post, x.weak, x.frail, x.slimed - nx, x.pile, gone, x.t,
                                                          x.pblock + per * std::min(x.hand.d, en - nx), x.h));
                    });
            return best;
        }
        double sxEndOf(int mode, const SxView &x) {
            return sxEndAt(mode, x.l, x.weak, x.frail, x.slimed, x.pile, x.abGone || x.hand.a > 0, x.t, x.pblock, x.h);
        }

        // --relaxed-check: the engine's outcomes of ending the turn at `s` against
        // the model's slimes turn, leaves and draw.
        void sxMirror(const BattleContext &s, const SAction &endTurn) {
            SxView x;
            if (!sxView(s, x)) { ++relaxedGateMisses_; return; }
            ++relaxedChecked_;
            SxSlimes next;
            int weak2 = 0, frail2 = 0, added = 0;
            double pN[2][3];
            const int hp = x.h - std::max(0, sxMonsterTurn(x.l, x.weak, x.frail, next, weak2, frail2, added, pN) - x.pblock);
            const bool gone = x.abGone || x.hand.a > 0;
            const int slimed2 = x.slimed + added;
            auto bad = [&](const char *what) {
                if (++relaxedMirror_ <= 10)
                    std::cerr << "Small Slimes mirror mismatch: " << what << " (turn " << s.turn << " hp " << x.h << " slimes "
                              << x.l[0].hp << "/" << x.l[1].hp << " moves " << x.l[0].mv0 << "/" << x.l[1].mv0 << " weak "
                              << x.weak << " frail " << x.frail << " slimed " << x.slimed << ")\n";
            };
            double pMove[3][3] = {};
            for (const auto &o : outcomes(s, endTurn)) {
                const BattleContext &n = o.state;
                if (hp <= 0) {
                    if (n.outcome != Outcome::PLAYER_LOSS) bad("expected a death");
                    else if (std::abs(terminal(n).v - lxLeaf(x.l[0].hp, x.l[1].hp, s.turn, true)) > 1e-9) bad("death leaf");
                    continue;
                }
                if (n.outcome != Outcome::UNDECIDED || !quiet(n)) { bad("expected a quiet undecided state"); continue; }
                if (n.turn != s.turn + 1 || n.player.curHp != hp || n.player.block != 0 || n.player.energy != rxEnergy_) {
                    bad("player at the turn start");
                    continue;
                }
                SxView y;
                if (!sxView(n, y)) { bad("next state outside the model"); continue; }
                bool same = y.weak == weak2 && y.frail == frail2 && y.slimed == slimed2 && y.abGone == gone;
                for (int i = 0; i < 2; ++i) {
                    const auto &a = y.l[i], &b = next[i];
                    same = same && a.hp == b.hp && a.vuln == b.vuln && a.mv1 == b.mv1;
                }
                if (!same) {
                    if (relaxedMirror_ < 10)
                        for (int i = 0; i < 2; ++i)
                            std::cerr << "  slime " << i << " engine: hp " << y.l[i].hp << " vuln " << y.l[i].vuln << " last "
                                      << y.l[i].mv1 << "; model: hp " << next[i].hp << " vuln " << next[i].vuln << " last "
                                      << next[i].mv1 << " (weak engine " << y.weak << " model " << weak2 << ", frail engine "
                                      << y.frail << " model " << frail2 << ", slimed engine " << y.slimed << " model "
                                      << slimed2 << ")\n";
                    bad("slimes turn");
                    continue;
                }
                const int r0 = y.l[0].hp ? y.l[0].mv0 : 0, r1 = y.l[1].hp ? y.l[1].mv0 : 0;
                pMove[r0][r1] += o.p;
                // The drawn hand and the pile it leaves must be a draw the model
                // offers, with the engine's probability (both move rolls times draw).
                double pDraw = -1;
                rxHands(x.pile, gone, slimed2, false, [&](const RxDeck &hand, const RxDeck &left, double p) {
                    if (hand == y.hand && left == y.pile) pDraw = p;
                });
                const double pRoll = (y.l[0].hp ? pN[0][r0] : 1.0) * (y.l[1].hp ? pN[1][r1] : 1.0);
                if (pDraw < 0) bad("draw");
                else if (std::abs(o.p - pRoll * pDraw) > 1e-9) bad("draw probability");
                if (n.turn > turnCap_) {
                    if (std::abs(terminal(n).v - lxLeaf(y.l[0].hp, y.l[1].hp, n.turn, false)) > 1e-9) bad("cap leaf");
                } else {
                    // The start value maxes over hands: at least this hand's value.
                    const std::size_t off = sxStart(0, y.l, weak2, frail2, slimed2, x.pile, gone, n.turn);
                    if (sxDecAt(0, y) > rxTab_[0].pool[off + hp] + 1e-9) bad("start value below a drawn hand");
                }
            }
            if (hp > 0)
                for (int a = 0; a < 3; ++a)
                    for (int b = 0; b < 3; ++b) {
                        const double pa = next[0].hp ? pN[0][a] : (a ? 0.0 : 1.0);
                        const double pb = next[1].hp ? pN[1][b] : (b ? 0.0 : 1.0);
                        if (std::abs(pMove[a][b] - pa * pb) > 1e-9) bad("move probabilities");
                    }
        }
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

        // ---- endgame roots (exact_combat_solver roots) -----------------------
        // Research: values of recorded Silver roots of real elite and boss fights
        // (one_combat endgamerootgen) through turnCap_ only. general_: every bound
        // is generalUpperBound (no starter-fight assumption), and a fight still
        // undecided past the cap is worth capUpper_ ? generalUpperBound : 0, the
        // floor of both objectives used there, so one pass with each brackets the
        // true value of every action.
        bool general_ = false, capUpper_ = false, winObjective_ = false, dropCardsDrawn_ = false;
        // surviveObjective_: 1 for a win or a fight still undecided past the cap, 0 for a loss
        // (the same in both passes: the probability of surviving the horizon under best play).
        bool collapseCapDraws_ = false, collapseCapAll_ = false, surviveObjective_ = false;
        std::string collapseRefused_;   // why some horizon end turn kept its chance events (roots report)
        std::chrono::steady_clock::time_point deadline_ = std::chrono::steady_clock::time_point::max();

        // What the player can still reach in this fight from `s`: the most HP, max HP and
        // gold, and whether potions can be gained (Entropic Brew, Alchemize). HP rises only
        // through the engine's heal sources: their total is bounded here per source (Feed and
        // Darkstone Periapt with the max HP they add, a Blood or Regen Potion, Fruit Juice,
        // Bandage Up per copy, Toy Ornithopter per potion, Bird-Faced Urn per power, Regen,
        // Magic Flower's 1.5x; a revive by Fairy or Lizard Tail restarts from its HP), and a
        // source without such a bound (Reaper, Bite, Exhume, random cards) allows the max HP.
        // Feed and Hand of Greed pay once per monster that can still die, a split slime
        // counting its splits.
        struct Ceilings { int hp = 0, maxHp = 0, gold = 0; bool potionGain = false; };
        Ceilings ceilings(const BattleContext &s) const {
            const auto &p = s.player;
            const bool bark = p.hasRelic<RelicId::SACRED_BARK>();
            int feeds = 0, bandages = 0, powers = 0, potions = 0, bloods = 0, regens = 0, juice = 0, revivePct = 0;
            bool greed = false, unbounded = false, potionGain = false, dualWield = false;
            // A card played twice (Duplication, Echo Form, Burst) heals twice.
            bool doubler = p.hasStatus<PlayerStatus::DUPLICATION>() || p.hasStatus<PlayerStatus::ECHO_FORM>()
                || p.hasStatus<PlayerStatus::BURST>();
            auto card = [&](const CardInstance &c, bool exhausted) {
                switch (c.id) {
                    case CardId::REAPER: case CardId::BITE: case CardId::EXHUME: unbounded = true; break;
                    case CardId::FEED: ++feeds; break;
                    case CardId::BANDAGE_UP: bandages += exhausted ? 0 : 1; break;
                    case CardId::HAND_OF_GREED: greed = true; break;
                    case CardId::DUAL_WIELD: dualWield = true; break;
                    case CardId::ECHO_FORM: case CardId::BURST: doubler = true; break;
                    case CardId::ALCHEMIZE: potionGain = true; break;
                    case CardId::INFERNAL_BLADE: case CardId::JACK_OF_ALL_TRADES: case CardId::DISCOVERY:
                    case CardId::TRANSMUTATION: case CardId::CHRYSALIS: case CardId::METAMORPHOSIS:
                    case CardId::MAGNETISM: case CardId::WHITE_NOISE:
                        unbounded = greed = true; ++feeds; break;
                    default: break;
                }
                if (!exhausted && c.getType() == CardType::POWER) ++powers;
            };
            const auto &cm = s.cards;
            for (int i = 0; i < cm.cardsInHand; ++i) card(cm.hand[i], false);
            for (const auto &c : cm.drawPile) card(c, false);
            for (const auto &c : cm.discardPile) card(c, false);
            for (const auto &c : cm.exhaustPile) card(c, true);
            for (const auto &c : cm.stasisCards) card(c, false);
            for (int i = 0; i < s.potionCapacity; ++i) {
                switch (s.potions[i]) {
                    case Potion::EMPTY_POTION_SLOT: continue;
                    case Potion::BLOOD_POTION: ++bloods; break;
                    case Potion::REGEN_POTION: ++regens; break;
                    case Potion::FAIRY_POTION: revivePct = std::max(revivePct, bark ? 60 : 30); break;
                    case Potion::FRUIT_JUICE: juice += bark ? 10 : 5; break;
                    case Potion::DUPLICATION_POTION: doubler = true; break;
                    case Potion::ENTROPIC_BREW: potionGain = unbounded = greed = true; ++feeds; break;
                    case Potion::ATTACK_POTION: case Potion::SKILL_POTION: case Potion::POWER_POTION:
                    case Potion::COLORLESS_POTION: unbounded = greed = true; ++feeds; break;
                    default: break;
                }
                ++potions;
            }
            if (p.hasRelic<RelicId::LIZARD_TAIL>()) revivePct = std::max(revivePct, 50);
            if (p.hasStatus<PlayerStatus::MAGNETISM>()) unbounded = greed = true;
            // Copies of a power (Dual Wield) heal through the Urn without a bound here; so do
            // Bandage Ups played twice.
            if ((dualWield && p.hasRelic<RelicId::BIRD_FACED_URN>()) || (doubler && bandages > 0)) unbounded = true;
            int kills = 0;
            bool unimplanted = false;
            for (int i = 0; i < s.monsters.monsterCount; ++i) {
                const auto &m = s.monsters.arr[i];
                if (!m.isAlive() || m.hasStatus<MonsterStatus::MINION>()) continue;
                kills += m.id == MonsterId::SLIME_BOSS ? 7
                    : (m.id == MonsterId::ACID_SLIME_L || m.id == MonsterId::SPIKE_SLIME_L) ? 3 : 1;
                if (m.id == MonsterId::WRITHING_MASS && !m.miscInfo) unimplanted = true;
            }
            const int periapt = p.hasRelic<RelicId::DARKSTONE_PERIAPT>() && unimplanted ? 6 : 0;
            Ceilings c;
            c.maxHp = p.maxHp + 4 * feeds * kills + juice + periapt;
            if (unbounded) {
                c.hp = c.maxHp;
            } else {
                const int regen = p.getStatus<PlayerStatus::REGEN>();
                const int perRegenPotion = bark ? 55 : 15;   // Regen 5 (10): 5 + 4 + ... + 1
                double heal = 4.0 * feeds * kills + juice + periapt + 6.0 * bandages + regen * (regen + 1) / 2.0
                    + bloods * (c.maxHp * (bark ? 40 : 20) / 100) + regens * perRegenPotion;
                if (p.hasRelic<RelicId::TOY_ORNITHOPTER>()) heal += 5.0 * potions;
                if (p.hasRelic<RelicId::BIRD_FACED_URN>()) heal += 4.0 * powers;   // twice for Echo Form or Duplication
                if (greed && p.hasRelic<RelicId::BLOODY_IDOL>()) heal += 5.0 * kills;   // 5 per gold gain
                if (p.hasRelic<RelicId::MAGIC_FLOWER>()) heal *= 1.5;
                const int from = std::max(p.curHp, c.maxHp * revivePct / 100);
                c.hp = static_cast<int>(std::min<double>(c.maxHp, from + std::ceil(heal)));
            }
            c.gold = p.gold + (greed ? 25 * kills : 0);
            c.potionGain = potionGain;
            return c;
        }

        // An upper bound on the value of `s` under any play, for any state of these
        // objectives: the HP ceiling (hp), or Silver's victory score now (no win comes
        // earlier) at the ceilings, potions as held (they are only used up) and no
        // escape; a loss is worth 0 in both.
        double generalUpperBound(const BattleContext &s) {
            if (s.outcome != Outcome::UNDECIDED) return terminal(s).v;
            if (surviveObjective_) return 1.0;
            const Ceilings c = ceilings(s);
            if (hpObjective_) return std::max(0, c.hp);
            if (c.potionGain) throw std::runtime_error("exact solver: potions can be gained (Entropic Brew, Alchemize)");
            KeyBuilder k;
            k.add(c.hp); k.add(c.maxHp); k.add(c.gold); k.add(s.turn); k.add(s.potionCapacity);
            for (int i = 0; i < s.potionCapacity; ++i) k.add(static_cast<int>(s.potions[i]));
            k.add(s.player.relicBits0); k.add(s.player.relicBits1); k.add(static_cast<std::uint64_t>(s.miscBits.to_ullong()));
            for (int i = 0; i < s.monsters.monsterCount; ++i) {
                const auto &m = s.monsters.arr[i];
                k.add(static_cast<int>(m.id)); k.add(m.curHp > 0 ? 1 : 0); k.add(static_cast<int>(m.moveHistory[0])); k.add(m.miscInfo);
            }
            const Key key = k.key();
            if (auto it = boundCache_.find(key); it != boundCache_.end()) return it->second;
            BattleContext w = s;
            w.outcome = Outcome::PLAYER_VICTORY;
            w.smokeBombUsed = false;
            w.player.maxHp = c.maxHp;
            w.player.gold = static_cast<decltype(w.player.gold)>(c.gold);
            double best = 0;
            // Meat on the Bone heals 12 at or below half HP: the score can peak there.
            for (const int hp : {c.hp, std::min(c.hp, c.maxHp / 2)}) {
                w.player.curHp = std::max(1, hp);
                best = std::max(best, scorer_.scoreEndState(w));
            }
            boundCache_.emplace(key, best);
            return best;
        }
        std::unordered_map<Key, double, KeyHash> boundCache_;
        std::size_t memoSize() const { return memo_.size(); }

        // Research (roots --explain): the best line from `s` under this pass's values, following
        // the most likely outcome of each chance step, one line per step on `os`.
        std::vector<Outcome1> outcomesOf(const BattleContext &s, const SAction &a) {
            auto outs = outcomes(s, a);
            std::sort(outs.begin(), outs.end(), [](const Outcome1 &x, const Outcome1 &y) { return x.p > y.p; });
            return outs;
        }
        void explain(const BattleContext &s, std::ostream &os, int depth = 0) {
            if (depth > 40 || s.outcome != Outcome::UNDECIDED || s.turn > turnCap_) {
                os << "    end: outcome " << static_cast<int>(s.outcome) << " turn " << s.turn << " hp " << s.player.curHp
                   << " value " << solve(s).v << '\n';
                return;
            }
            const auto acts = actions(s);
            int best = -1;
            double bestV = -1e300;
            for (std::size_t i = 0; i < acts.size(); ++i) {
                const double v = q(s, acts[i]).v;
                if (v > bestV) { bestV = v; best = static_cast<int>(i); }
            }
            if (best < 0) { os << "    no actions\n"; return; }
            auto outs = outcomes(s, acts[best]);
            std::sort(outs.begin(), outs.end(), [](const Outcome1 &a, const Outcome1 &b) { return a.p > b.p; });
            os << "    t" << s.turn << " hp " << s.player.curHp << " blk " << s.player.block << " e " << s.player.energy
               << " | ";
            acts[best].printDesc(os, s);
            os << " = " << bestV << " (" << outs.size() << " outcomes, top p "
               << outs[0].p << ")\n";
            explain(outs[0].state, os, depth + 1);
        }

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
            v.v = hpObjective_ ? v.hp : surviveObjective_ ? v.win
                : winObjective_ ? (v.win ? std::max(0.0, v.score) : 0.0) : v.score;
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
            if (s.turn >= exactFromTurn_) {
                Val v;
                if (!exactSource_ || !exactSource_->abstractValue(s, v.v))
                    throw std::runtime_error("--policy-then-exact: a state outside the abstract model");
                v.score = v.hp = v.win = v.capped = -1;   // not tracked by the recursion
                return v;
            }
            if (s.turn > turnCap_) {
                // Horizon: an undecided fight past the cap scores like a loss leaf
                // (Silver's unresolved-playout evaluation); `capped` reports how
                // much probability reaches it.
                Val v = terminal(s);
                if (general_) {
                    // Roots mode: the floor of the objective (lower pass) or the general upper bound.
                    v.v = v.score = surviveObjective_ ? 1.0 : capUpper_ ? generalUpperBound(s) : 0.0;
                    v.hp = capUpper_ ? ceilings(s).hp : 0;
                    v.win = capUpper_ && !surviveObjective_ ? 1 : 0;
                }
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
            if (s.turn >= policyFromTurn_ && (s.inputState == InputState::PLAYER_NORMAL
                    || s.inputState == InputState::CARD_SELECT)) {
                const SAction a = s.inputState == InputState::PLAYER_NORMAL ? policy_.chooseBattleCardPlay(s)
                                                                            : policy_.chooseBattleCardSelect(s);
                best = expand(s, a, kNoAlpha);
            } else if (!prune_ || !memoize || !turnValue(s, alpha, best)) {
                const auto acts = actions(s);
                if (acts.empty()) {
                    best = terminal(s);
                } else {
                    best = maxOver(acts.size(), alpha, [&](std::size_t i, double a) { return q(s, acts[i], a); });
                }
            }
            if (memoize) {
                inProgress_.erase(key);
                if (relaxedCheck_ && best.exact) rxCheck(s, best.v, false);
                if (abstractCheck_ && best.exact) abstractCompare(s, best.v, false);
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
            if (relaxedCheck_) modelMirror(s, endTurn);
            // Research (--relaxed-check): end-of-turn states the relaxed bound would refute before any replay.
            const bool rxWould = relaxedCheck_ && alpha > kNoAlpha && [&] {
                double r = 0;
                return modelEnd(0, s, r) && rxPad(r) <= alpha;
            }();
            if (intentBound_ && alpha > kNoAlpha) {
                if (const double ub = intentUpperBound(s); ub <= alpha) {
                    ++cutoffs_;
                    ++intentCutoffs_;
                    noteState(s, 1);
                    remember(key, bound(ub));
                    return bound(ub);
                }
            }
            if (relaxedBound_ && alpha > kNoAlpha) {
                if (double r; modelEnd(0, s, r)) {
                    if (const double ub = rxPad(r); ub <= alpha) {
                        ++cutoffs_;
                        ++relaxedCutoffs_;
                        noteState(s, 1);
                        remember(key, bound(ub));
                        return bound(ub);
                    }
                } else {
                    ++relaxedGateMisses_;
                }
            }
            if (rxWould) ++relaxedWouldCut_;
            const Val v = expand(s, endTurn, alpha);
            if (relaxedCheck_ && v.exact) {
                rxCheck(s, v.v, true);
                ++relaxedIntentSlack_[slackBucket(std::max(0.0, intentUpperBound(s) - v.v))];
            }
            if (abstractCheck_ && v.exact) abstractCompare(s, v.v, true);
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
            if (orderHeuristic_ >= 0 || relaxedOrder_) {
                std::vector<double> hk(cands.size(), 0);
                if (orderHeuristic_ >= 0) {
                    for (std::size_t i : survivors) hk[i] = heuristicKey(cands[i].st, orderHeuristic_);
                    std::stable_sort(survivors.begin(), survivors.end(), [&](std::size_t x, std::size_t y) { return hk[x] > hk[y]; });
                }
                if (relaxedOrder_) {
                    for (std::size_t i : survivors) {
                        double r = 0;
                        hk[i] = modelEnd(0, cands[i].st, r) ? r : 1e300;
                    }
                    std::stable_sort(survivors.begin(), survivors.end(), [&](std::size_t x, std::size_t y) { return hk[x] > hk[y]; });
                }
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
            // Roots mode: ending the cap turn leads only to horizon leaves (or terminals decided
            // before the draw), valued without the hand, so its draw is not enumerated; Fire
            // Breathing deals damage per drawn status or curse, so it keeps the draw exact.
            script_.collapseBatchDraws = collapseCapDraws_ && endTurn && s.turn == turnCap_
                && !s.player.hasStatus<PS::FIRE_BREATHING>();
            // The same leaves see no other chance result either (next intents, summoned minions'
            // kinds and HP) unless one can damage a monster or the player: Juggernaut and Mayhem
            // hit at random, Fire Breathing hits per drawn card, Runic Dome hides intents, and a
            // Writhing Mass roll sets the Parasite flag of the victory score.
            if (collapseCapAll_ && endTurn && s.turn == turnCap_) {
                const char *refused = s.player.hasStatus<PS::FIRE_BREATHING>() ? "Fire Breathing"
                    : s.player.hasStatus<PS::JUGGERNAUT>() ? "Juggernaut" : s.player.hasStatus<PS::MAYHEM>() ? "Mayhem"
                    : s.player.hasRelic<RelicId::RUNIC_DOME>() ? "Runic Dome"
                    : std::any_of(s.monsters.arr.begin(), s.monsters.arr.begin() + s.monsters.monsterCount,
                                  [](const Monster &m) { return m.id == MonsterId::WRITHING_MASS; }) ? "Writhing Mass" : nullptr;
                script_.collapseAll = refused == nullptr;
                if (refused && collapseRefused_.empty()) std::cerr << "  horizon end turn kept its chance events: " << refused << '\n';
                if (refused) collapseRefused_ = refused;
            }
            struct CollapseOff {
                exact::ChanceScript &c;
                ~CollapseOff() { c.collapseBatchDraws = false; c.collapseAll = false; }
            } collapseOff{script_};
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
                if ((replays_ & 4095) == 0 && std::chrono::steady_clock::now() > deadline_)
                    throw Infeasible("time limit");
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
                if (dropCardsDrawn_) next.cardsDrawn = 0;
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

    // Research (--leaf-heads): a value head on the frozen trunk of a combat_policy_mlp prior (SilverValueHead.h);
    // tools in the leaf-value research folder export g7f_E's own value head and the probe head to its text format.
    using LeafHead = sts::search::SilverValueHead;

    struct Config {
        std::string name;
        sts::search::NativeSilverBudgetOverride budget;
        int flatSims = 10000;
        bool prior = false;
        std::optional<double> exploration;   // "@c=X" suffix: UCB exploration X at decision and chance edges
        std::optional<int> maxBackup;        // "@mb=K" suffix: STS_SILVER_MAX_BACKUP=K for this config
    };

    Config parseConfig(const std::string &full) {
        using P = sts::search::NativeSilverBudgetOverride::Policy;
        Config c;
        c.name = full;
        std::string name = full;
        if (const auto at = name.find("@mb="); at != std::string::npos) {
            c.maxBackup = std::stoi(name.substr(at + 4));
            name = name.substr(0, at);
        }
        if (const auto at = name.find("@c="); at != std::string::npos) {
            c.exploration = std::stod(name.substr(at + 3));
            name = name.substr(0, at);
        }
        c.budget.skipSingletonRoots = true;
        if (name == "prod") { c.budget.policy = P::LearnedStop; c.prior = true; }
        else if (name == "live") { c.budget.policy = P::Flat; }
        else if (name.rfind("flat:", 0) == 0) { c.budget.policy = P::Flat; c.flatSims = std::stoi(name.substr(5)); }
        else if (name.rfind("flatprior:", 0) == 0) { c.budget.policy = P::Flat; c.flatSims = std::stoi(name.substr(10)); c.prior = true; }
        else throw std::invalid_argument("unknown config " + name);
        return c;
    }

    // Diagnostic readout of Silver's tree (the search is untouched): a decision node is
    // worth its best child among those with at least minVisits simulations, a chance node
    // the visit-weighted mean of its outcomes, anything else (and every node below
    // minVisits) its mean playout value.
    double maxBackup(const SilverSearcher::Node *n, int minVisits,
                     std::unordered_map<const SilverSearcher::Node *, double> &memo, int depth) {
        const double mean = n->evaluationSum / std::max<std::int64_t>(1, n->simulationCount);
        if (n->simulationCount < minVisits || depth > 200) return mean;
        if (auto it = memo.find(n); it != memo.end()) return it->second;
        memo[n] = mean;   // cycle guard
        double v = mean;
        if (n->isRandomNode) {
            double sum = 0, w = 0;
            for (const auto &e : n->edges) {
                if (!e.node || e.visitCount == 0) continue;
                sum += e.visitCount * maxBackup(e.node, minVisits, memo, depth + 1);
                w += e.visitCount;
            }
            if (w > 0) v = sum / w;
        } else {
            double best = -1e300;
            for (const auto &e : n->edges)
                if (e.node && e.node->simulationCount >= minVisits)
                    best = std::max(best, maxBackup(e.node, minVisits, memo, depth + 1));
            if (best > -1e300) v = best;
        }
        memo[n] = v;
        return v;
    }
    double maxBackup(const SilverSearcher::Node *n, int minVisits) {
        std::unordered_map<const SilverSearcher::Node *, double> memo;
        return maxBackup(n, minVisits, memo, 0);
    }

    double seconds(std::chrono::steady_clock::time_point since) {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - since).count();
    }

    // ---- roots: Silver roots of real elite and boss fights (one_combat endgamerootgen) ----

    // The recorder's snapshot back into the search root (as its round-trip check does).
    BattleContext restoreRoot(const json &j) {
        const std::string hex = j.at("state");
        std::vector<std::uint8_t> bytes(hex.size() / 2);
        for (std::size_t i = 0; i < bytes.size(); ++i)
            bytes[i] = static_cast<std::uint8_t>(std::stoi(hex.substr(2 * i, 2), nullptr, 16));
        BattleContext bc = deserializeBattleContext(bytes.data(), bytes.size());
        const auto &x = j.at("extras");
        bc.energyWasted = x.at("energyWasted"); bc.cardsDrawn = x.at("cardsDrawn");
        bc.miscBits = std::bitset<32>(x.at("miscBits").get<unsigned long>());
        bc.smokeBombUsed = x.at("smokeBombUsed"); bc.monsterTurnIdx = x.at("monsterTurnIdx");
        bc.endTurnQueued = x.at("endTurnQueued"); bc.turnHasEnded = x.at("turnHasEnded");
        bc.skipMonsterTurn = x.at("skipMonsterTurn"); bc.intentsHidden = x.at("intentsHidden");
        bc.haveUsedDiscoveryAction = x.at("haveUsedDiscoveryAction");
        if (!j.at("drawConcrete").get<bool>()) {
            const std::vector<CardInstance> all(bc.cards.drawPile.begin(), bc.cards.drawPile.end());
            const int bottom = j.at("drawKnownBottom"), top = j.at("drawKnownTop");
            bc.cards.drawPile.assignInformationState(
                std::vector<CardInstance>(all.begin(), all.begin() + bottom),
                std::vector<CardInstance>(all.begin() + bottom, all.end() - top),
                std::vector<CardInstance>(all.end() - top, all.end()));
        }
        if (bc.turn != j.at("turn").get<int>() || bc.player.curHp != j.at("hp").get<int>()
                || bc.cards.cardsInHand != j.at("handSize").get<int>())
            throw std::runtime_error("roots: the snapshot does not decode to the recorded root");
        return bc;
    }

    sts::search::SilverSearchContext contextOf(const json &c) {
        sts::search::SilverSearchContext x;
        x.act = c.at("act"); x.actBossRoom = c.at("actBossRoom"); x.omamoriCharged = c.at("omamoriCharged");
        x.eliteRewards = c.at("eliteRewards"); x.finalBossBinary = c.at("finalBossBinary");
        x.finalFightLeaf = c.at("finalFightLeaf"); x.actHealFollows = c.at("actHealFollows");
        x.noLossPotionCredit = c.at("noLossPotionCredit"); x.relicHealLeaf = c.at("relicHealLeaf");
        x.escapeForfeitsRun = c.at("escapeForfeitsRun");
        return x;
    }

    void weightsOf(const json &w, sts::search::SilverEvalWeights &x) {
        x.winBonus = w.at("winBonus"); x.potionWeight = w.at("potionWeight");
        x.victoryTurnPenalty = w.at("victoryTurnPenalty"); x.monsterDamageWeight = w.at("monsterDamageWeight");
        x.aliveWeight = w.at("aliveWeight"); x.energyWasteWeight = w.at("energyWasteWeight");
        x.drawWeight = w.at("drawWeight"); x.turnSurvivalWeight = w.at("turnSurvivalWeight");
        x.goldWeight = w.at("goldWeight"); x.maxHpWeight = w.at("maxHpWeight"); x.parasitePenalty = w.at("parasitePenalty");
        x.escapePenalty = w.at("escapePenalty"); x.eliteEscapePenalty = w.at("eliteEscapePenalty");
        x.potionTypeWeightsOn = w.at("potionTypeWeightsOn");
        const auto types = w.at("potionTypeWeights").get<std::vector<double>>();
        for (std::size_t i = 0; i < types.size() && i < x.potionTypeWeights.size(); ++i) x.potionTypeWeights[i] = types[i];
        x.concaveHpK = w.at("concaveHpK");
    }

    // exact_combat_solver roots IN.jsonl OUT.jsonl [options]: every recorded root of the
    // selected turns (--to-end: turns before the fight's last turn, default 0,1) solved through
    // --horizon more turns (default 0: the root's own turn) under --objective win (Silver's
    // victory score, 0 for a loss; the default) or hp (end HP, 0 for a loss). Two passes per
    // root: a fight still undecided past the horizon is worth 0 (the lower pass) or the
    // general upper bound (the upper pass), so each action gets a proven interval [lo, hi]
    // of its value under optimal play. --objective survive is exact in one pass: the
    // probability of a win or of still being alive past the horizon (lo = hi). Ending the
    // horizon's last turn enumerates no chance event its leaves cannot see (--collapse all,
    // the default; draws: only its draws; none). One JSON line per root.
    int rootsMain(int argc, char **argv) {
        if (argc < 4) {
            std::cerr << "usage: exact_combat_solver roots IN.jsonl OUT.jsonl [--horizon H] [--to-end 0,1]"
                         " [--objective win|hp|survive] [--rooms ELITE,BOSS] [--max-states N] [--time-limit S] [--skip N]"
                         " [--take N] [--verify-memo] [--no-canonical-draws] [--collapse all|draws|none] [--no-bounds]"
                         " [--policy-lower P] [--explain INDEX]\n";
            return 2;
        }
        std::ifstream in(argv[2]);
        if (!in) throw std::runtime_error(std::string("cannot open ") + argv[2]);
        std::ofstream out(argv[3], std::ios::app);
        if (!out) throw std::runtime_error(std::string("cannot open ") + argv[3]);
        int horizon = 0, policyLower = 0;
        std::vector<int> toEnd{0, 1};
        std::vector<std::string> rooms{"ELITE", "BOSS"};
        bool hpObjective = false, surviveObjective = false, verify = false, canonicalOff = false, boundsOff = false;
        std::string collapse = "all";
        std::int64_t maxStates = 12'000'000, skip = 0, take = -1, explainIndex = -1;
        double timeLimit = 600;
        for (int i = 4; i < argc; ++i) {
            const std::string arg = argv[i];
            auto value = [&]() -> std::string {
                if (i + 1 >= argc) throw std::invalid_argument(arg + " needs a value");
                return argv[++i];
            };
            if (arg == "--horizon") horizon = std::stoi(value());
            else if (arg == "--to-end") {
                toEnd.clear();
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) toEnd.push_back(std::stoi(item));
            } else if (arg == "--rooms") {
                rooms.clear();
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) rooms.push_back(item);
            } else if (arg == "--objective") {
                const auto v = value();
                if (v != "win" && v != "hp" && v != "survive") throw std::invalid_argument("--objective win|hp|survive");
                hpObjective = v == "hp";
                surviveObjective = v == "survive";
            } else if (arg == "--max-states") maxStates = std::stoll(value());
            else if (arg == "--time-limit") timeLimit = std::stod(value());
            else if (arg == "--skip") skip = std::stoll(value());
            else if (arg == "--take") take = std::stoll(value());
            else if (arg == "--verify-memo") verify = true;
            else if (arg == "--no-canonical-draws") canonicalOff = true;
            else if (arg == "--collapse") {
                collapse = value();
                if (collapse != "all" && collapse != "draws" && collapse != "none")
                    throw std::invalid_argument("--collapse all|draws|none");
            } else if (arg == "--no-collapse") collapse = "none";
            else if (arg == "--no-bounds") boundsOff = true;
            else if (arg == "--explain") explainIndex = std::stoll(value());
            else if (arg == "--policy-lower") policyLower = std::stoi(value());
            else throw std::invalid_argument("unknown option " + arg);
        }
        if (surviveObjective && policyLower > 0) throw std::invalid_argument("--objective survive is exact: no --policy-lower");
        sts::search::installNativeSilverBackend();
        std::int64_t eligible = 0, solved = 0;
        for (std::string line; std::getline(in, line);) {
            if (line.empty()) continue;
            const json j = json::parse(line);
            if (j.contains("summary")) continue;
            if (std::find(toEnd.begin(), toEnd.end(), j.at("turnsToEnd").get<int>()) == toEnd.end()) continue;
            if (std::find(rooms.begin(), rooms.end(), j.at("room").get<std::string>()) == rooms.end()) continue;
            if (j.at("skipped").get<bool>() || j.at("edges").size() < 2) continue;
            const std::int64_t index = eligible++;
            if (index < skip || (take >= 0 && index >= skip + take)) continue;
            json row = {{"index", index}};
            for (const char *k : {"seed", "fight", "floor", "act", "room", "encounter", "decision", "turn", "endTurn",
                                  "turnsToEnd", "won", "endHp", "hp", "maxHp", "block", "energy", "handSize",
                                  "monstersAlive", "simulations", "inheritedVisits", "chosen", "chosenLabel"})
                row[k] = j.at(k);
            row["horizon"] = horizon;
            row["policyLower"] = policyLower;
            row["objective"] = hpObjective ? "hp" : surviveObjective ? "survive" : "win";
            row["collapse"] = collapse;
            const auto t0 = std::chrono::steady_clock::now();
            try {
                if (!j.value("roundTrip", false) || j.at("inputState").get<int>() != static_cast<int>(InputState::PLAYER_NORMAL))
                    throw std::runtime_error("unsupported: not a restorable quiet player decision");
                const BattleContext root = restoreRoot(j);
                if (!quiet(root)) throw std::runtime_error("unsupported: not a quiet player decision");
                SilverSearcher live(root, contextOf(j.at("context")));
                weightsOf(j.at("weights"), live.evalWeights);
                // Silver's playout policy of this root (its card table, block rule), for --policy-lower.
                std::vector<int> cardTable;
                if (j.contains("rollout")) {
                    const auto &r = j.at("rollout");
                    if (!r.at("cardTable").is_null()) {
                        cardTable = r.at("cardTable").get<std::vector<int>>();
                        live.rolloutConfig.cardTable = cardTable.data();
                    }
                    live.rolloutConfig.zeroCostCap = r.at("zeroCostCap");
                    live.rolloutConfig.blockRule = {r.at("blockFirstMargin").get<int>(), r.at("blockLethalCheck").get<bool>(),
                                                    r.at("blockOffset").get<int>()};
                }
                if (!hpObjective && live.evalWeights.concaveHpK != 0)
                    throw std::runtime_error("unsupported: concave HP leaf (the potion term is not monotone)");
                if (!hpObjective && live.evalWeights.potionTypeWeightsOn)
                    for (const double w : live.evalWeights.potionTypeWeights)
                        if (w < 0) throw std::runtime_error("unsupported: negative potion weight");
                std::map<std::uint32_t, json> edges;
                for (const auto &e : j.at("edges")) edges[e.at(0).get<std::uint32_t>()] = e;
                json acts = json::array();
                std::vector<double> lo, hi;
                int chosenIdx = -1;
                for (int pass = 0; pass < (surviveObjective ? 1 : 2); ++pass) {
                    const auto tp = std::chrono::steady_clock::now();
                    ExactSolver solver(root, live, hpObjective, maxStates, verify, !canonicalOff, true);
                    solver.general_ = true;
                    solver.capUpper_ = pass == 1;
                    solver.winObjective_ = !hpObjective && !surviveObjective;
                    solver.surviveObjective_ = surviveObjective;
                    solver.dropCardsDrawn_ = true;
                    solver.collapseCapDraws_ = collapse != "none";
                    solver.collapseCapAll_ = collapse == "all";
                    solver.bounds_ = !boundsOff;
                    solver.turnCap_ = root.turn + horizon;
                    if (pass == 0 && policyLower > 0) {
                        // A lower bound needs only some play: after the horizon, Silver's playout
                        // policy for policyLower more turns (exactly in expectation), then 0.
                        solver.setPolicy(root.turn + horizon + 1, live);
                        solver.turnCap_ += policyLower;
                    }
                    solver.deadline_ = tp + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                        std::chrono::duration<double>(timeLimit));
                    const auto actions = solver.actions(root);
                    if (actions.size() != edges.size()) row["edgeMismatch"] = true;
                    if (pass == 0) {
                        const auto c = solver.ceilings(root);
                        row["ceilHp"] = c.hp; row["ceilMaxHp"] = c.maxHp; row["ceilGold"] = c.gold;
                    }
                    for (std::size_t i = 0; i < actions.size(); ++i) {
                        const Val v = solver.q(root, actions[i]);
                        if (!v.exact) throw std::runtime_error("roots: a root value came back as a bound");
                        if (pass == 0) {
                            json act = {{"label", actionLabel(actions[i], root)}, {"bits", actions[i].bits}, {"lo", v.v},
                                        {"loWin", v.win}, {"loCapped", v.capped}};
                            if (auto it = edges.find(actions[i].bits); it != edges.end()) {
                                act["visits"] = it->second.at(1);
                                act["silverQ"] = it->second.at(2);
                            }
                            if (actions[i].bits == j.at("chosen").get<std::uint32_t>()) chosenIdx = static_cast<int>(i);
                            if (surviveObjective) { act["hi"] = v.v; hi.push_back(v.v); }
                            if (actions[i].getActionType() != search::ActionType::END_TURN) {
                                // What the action does by itself (its most likely outcome): block gained,
                                // monster HP and block removed, player HP change.
                                const auto outs = solver.outcomesOf(root, actions[i]);
                                if (!outs.empty()) {
                                    auto pool = [](const BattleContext &b) {
                                        int t = 0;
                                        for (int m = 0; m < b.monsters.monsterCount; ++m)
                                            if (b.monsters.arr[m].isAlive()) t += b.monsters.arr[m].curHp + b.monsters.arr[m].block;
                                        return t;
                                    };
                                    const auto &n = outs[0].state;
                                    act["dBlock"] = n.player.block - root.player.block;
                                    act["dDmg"] = pool(root) - pool(n);
                                    act["dHp"] = n.player.curHp - root.player.curHp;
                                }
                            }
                            acts.push_back(act);
                            lo.push_back(v.v);
                        } else {
                            acts[i]["hi"] = v.v;
                            acts[i]["hiCapped"] = v.capped;
                            hi.push_back(v.v);
                        }
                    }
                    if (index == explainIndex) {
                        std::cerr << "root " << index << (pass == 0 ? " lower" : " upper") << " pass, best line:\n";
                        solver.explain(root, std::cerr);
                        std::cerr << "  Silver's line:\n";
                        for (const auto &a : actions)
                            if (a.bits == j.at("chosen").get<std::uint32_t>()) {
                                auto outs = solver.outcomesOf(root, a);
                                std::cerr << "    " << actionLabel(a, root) << " (" << outs.size() << " outcomes)\n";
                                solver.explain(outs[0].state, std::cerr, 1);
                            }
                    }
                    const std::string tag = pass == 0 ? "lower" : "upper";
                    if (!solver.collapseRefused_.empty()) row["collapseRefused"] = solver.collapseRefused_;
                    row[tag + "States"] = solver.memoSize();
                    row[tag + "Replays"] = solver.replays();
                    row[tag + "Seconds"] = seconds(tp);
                }
                row["actions"] = acts;
                row["chosenIdx"] = chosenIdx;
                if (chosenIdx < 0) throw std::runtime_error("roots: Silver's action is not among the solver's actions");
                const double bestLo = *std::max_element(lo.begin(), lo.end());
                const double bestHi = *std::max_element(hi.begin(), hi.end());
                row["bestLo"] = bestLo;
                row["bestHi"] = bestHi;
                row["regretLo"] = std::max(0.0, bestLo - hi[chosenIdx]);
                row["regretHi"] = std::max(0.0, bestHi - lo[chosenIdx]);
                row["status"] = "ok";
                ++solved;
            } catch (const Infeasible &e) {
                row["status"] = std::string("infeasible: ") + e.what();
            } catch (const std::exception &e) {
                row["status"] = std::string(e.what()).rfind("unsupported", 0) == 0 ? e.what()
                                                                                    : std::string("unsupported: ") + e.what();
            }
            row["seconds"] = seconds(t0);
            out << row.dump() << '\n';
            out.flush();
        }
        std::cerr << "roots: " << solved << " solved of " << eligible << " eligible\n";
        return 0;
    }

}

int main(int argc, char **argv) {
    try {
        if (argc > 1 && std::string(argv[1]) == "roots") return rootsMain(argc, argv);
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
        bool relaxedBound = false, relaxedCheck = false, relaxedFree = false, relaxedOrder = false;
        bool abstractCheck = false, abstractOnly = false;
        double epsilon = 0;
        int turnCap = 8;
        std::vector<int> policyTurns;   // --policy-turns: k = optimal turns before the rollout policy takes over
        int policyTurnCap = 30;
        bool policyThisTurn = false;    // --policy-this-turn: the rollout policy for the root's turn, then exact
        bool policyThenExact = false;   // --policy-then-exact: each --policy-turns k also as "<variant>kT":
                                        // the rollout policy for one turn only, then the exact value
        // --leaf-oracles M,M,...: every config plays each fight once per mode, its own search valuing
        // the leaves with the abstract exact model of the fight instead of the playout (rows and
        // summaries carry the mode as "leafOracle"). none = the playout; exact = V*(leaf) (a perfect
        // value net, no playout); turn = the rollout policy to the end of the leaf's turn, then the
        // exact value of ending it (a perfect afterstate net behind a greedy finish of the turn);
        // turnstart = turn, but a leaf where no card has been played this turn gets V*(leaf);
        // blend:L = L * V* + (1 - L) * playout. A suffix @S adds a fixed N(0, S^2) error per valued
        // state (ExactSolver::noiseAt). Leaves the model cannot value keep their playout (counted).
        // head:NAME = the --leaf-heads value head NAME instead of the playout; hblend:NAME:L = L * head
        // + (1 - L) * playout. A suffix /P on either takes P points off the head's value for every turn the
        // leaf lies beyond the root (so a head cannot prefer stalling over winning now); a final +cap first
        // caps the head at the leaf's win-now value (SilverSearcher::LeafHead::winCap), +capM at win-now + M
        // points (research: how much of the cap's cost is its tightness).
        struct LeafModeSpec {
            std::string tag, mode, head;
            double noise = 0, blend = 0.5, turnPenalty = 0, winCapMargin = 0;
            bool winCap = false;
        };
        std::vector<LeafModeSpec> leafModes;
        // --leaf-heads NAME=PATH,...: value heads on the trunk of --leaf-trunk (default g7f_E);
        // --leaf-head-dump PATH writes the first 300 head-valued leaves (state block, trunk, value).
        std::map<std::string, LeafHead> leafHeads;
        std::string leafTrunkPath = "models/combat_policy_mlp_g7f_E.txt", leafHeadDump;
        // --leaf-label-dump PATH: every --leaf-label-every-th leaf of an "exact" mode (no @S) is written with its
        // state block and V* (training labels for a value head on these fights).
        std::string leafLabelDump;
        int leafLabelEvery = 40;
        // Playout variants evaluated by --policy-turns: "pol" is the production block rule;
        // --policy-block-first adds "polB" (margin 0); --policy-grid M:K:L,... adds "gM_K_L"
        // (margin M, offset K, lethal check L; M = -1 keeps block-first off).
        using BlockRule = sts::search::SilverRolloutAgent::BlockRule;
        std::vector<std::pair<std::string, BlockRule>> policyVariants{{"pol", BlockRule{}}};
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
            else if (arg == "--relaxed-bound") relaxedBound = true;
            else if (arg == "--relaxed-check") relaxedCheck = true;
            else if (arg == "--relaxed-free-draws") relaxedFree = true;
            else if (arg == "--relaxed-order") relaxedOrder = true;
            else if (arg == "--abstract-check") abstractCheck = true;
            else if (arg == "--abstract-only") abstractOnly = true;
            else if (arg == "--epsilon") epsilon = std::stod(value());
            else if (arg == "--policy-turns") {
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) policyTurns.push_back(std::stoi(item));
            } else if (arg == "--policy-turn-cap") policyTurnCap = std::stoi(value());
            else if (arg == "--policy-this-turn") policyThisTurn = true;
            else if (arg == "--policy-then-exact") policyThenExact = true;
            else if (arg == "--leaf-oracles") {
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) {
                    LeafModeSpec m{item, item};
                    if (const auto cap = m.mode.rfind("+cap"); cap != std::string::npos && cap > 0) {
                        m.winCap = true;
                        if (const auto margin = m.mode.substr(cap + 4); !margin.empty()) {
                            std::size_t used = 0;
                            m.winCapMargin = std::stod(margin, &used);
                            if (used != margin.size() || m.winCapMargin < 0)
                                throw std::invalid_argument("--leaf-oracles: +capM needs a margin M >= 0");
                        }
                        m.mode.resize(cap);
                    }
                    if (const auto at = m.mode.find('@'); at != std::string::npos) {
                        m.noise = std::stod(m.mode.substr(at + 1));
                        m.mode.resize(at);
                    }
                    if (const auto slash = m.mode.find('/'); slash != std::string::npos) {
                        m.turnPenalty = std::stod(m.mode.substr(slash + 1));
                        m.mode.resize(slash);
                    }
                    if (m.mode.rfind("blend:", 0) == 0) { m.blend = std::stod(m.mode.substr(6)); m.mode = "blend"; }
                    else if (m.mode.rfind("head:", 0) == 0) { m.head = m.mode.substr(5); m.mode = "head"; }
                    else if (m.mode.rfind("hblend:", 0) == 0) {
                        const auto colon = m.mode.find(':', 7);
                        if (colon == std::string::npos) throw std::invalid_argument("--leaf-oracles hblend:NAME:L");
                        m.head = m.mode.substr(7, colon - 7);
                        m.blend = std::stod(m.mode.substr(colon + 1));
                        m.mode = "hblend";
                    }
                    if (m.mode != "none" && m.mode != "exact" && m.mode != "turn" && m.mode != "turnstart" && m.mode != "blend"
                            && m.mode != "head" && m.mode != "hblend")
                        throw std::invalid_argument("--leaf-oracles items are none|exact|turn|turnstart|blend:L|head:NAME|hblend:NAME:L,"
                                                    " optionally @S (/P and +cap or +capM on a head)");
                    if (!m.head.empty() && m.noise != 0) throw std::invalid_argument("--leaf-oracles: no @S on a head");
                    if (m.head.empty() && (m.turnPenalty != 0 || m.winCap))
                        throw std::invalid_argument("--leaf-oracles: /P and +cap only on head:NAME and hblend:NAME:L");
                    leafModes.push_back(m);
                }
            }
            else if (arg == "--leaf-heads") {
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) {
                    const auto eq = item.find('=');
                    if (eq == std::string::npos) throw std::invalid_argument("--leaf-heads items are NAME=PATH");
                    leafHeads[item.substr(0, eq)] = LeafHead::load(item.substr(eq + 1));
                }
            }
            else if (arg == "--leaf-trunk") leafTrunkPath = value();
            else if (arg == "--leaf-label-dump") leafLabelDump = value();
            else if (arg == "--leaf-label-every") leafLabelEvery = std::stoi(value());
            else if (arg == "--leaf-head-dump") leafHeadDump = value();
            else if (arg == "--policy-block-first") policyVariants.push_back({"polB", BlockRule{0, true, 4}});
            else if (arg == "--policy-grid") {
                std::stringstream list(value());
                for (std::string item; std::getline(list, item, ',');) {
                    BlockRule r;
                    char c1 = 0, c2 = 0;
                    int l = 1;
                    std::stringstream one(item);
                    if (!(one >> r.blockFirstMargin >> c1 >> r.blockOffset >> c2 >> l) || c1 != ':' || c2 != ':')
                        throw std::invalid_argument("--policy-grid entries are M:K:L");
                    r.blockLethalCheck = l != 0;
                    policyVariants.push_back({"g" + std::to_string(r.blockFirstMargin) + "_" + std::to_string(r.blockOffset)
                                              + "_" + std::to_string(l), r});
                }
            }
            else throw std::invalid_argument("unknown option " + arg);
        }
        if (configs.empty()) configs = {parseConfig("prod"), parseConfig("live"),
                                        parseConfig("flatprior:2500"), parseConfig("flatprior:10000")};
        sts::search::CombatValueNet leafTrunk;
        for (const auto &m : leafModes)
            if (!m.head.empty() && !leafHeads.count(m.head))
                throw std::invalid_argument("--leaf-oracles: no --leaf-heads entry " + m.head);
        if (!leafHeads.empty()) {
            if (!leafTrunk.load(leafTrunkPath) || !leafTrunk.isPolicyMlp)
                throw std::runtime_error("--leaf-trunk: cannot load a combat_policy_mlp model from " + leafTrunkPath);
            for (const auto &[name, h] : leafHeads)
                if (h.in != leafTrunk.pmH1) throw std::invalid_argument("--leaf-heads " + name + ": input width is not the trunk's h1");
        }
        std::ofstream leafDump, labelDump;
        int leafDumped = 0;
        std::int64_t labelCalls = 0;
        if (!leafHeadDump.empty()) leafDump.open(leafHeadDump);
        if (!leafLabelDump.empty()) labelDump.open(leafLabelDump);
        // A head's value of a state; feat and base keep the state block and relu(trunk base).
        std::vector<float> feat, base;
        auto headValue = [&](const BattleContext &state, const LeafHead &h) { return h.value(state, leafTrunk, feat, base); };
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
            // Policy-evaluation solvers by (absolute switch turn, rollout card table).
            std::map<std::pair<int, std::vector<int>>, std::unique_ptr<ExactSolver>> policySolvers;
            std::string fightFailure;
            double solveSeconds = 0;
            // A solve that outgrows --max-states is dropped and retried from the
            // first root of a later turn: roots up to this turn stay unscored.
            int unsolvableThroughTurn = -1;
            json infeasibleSolves = json::array();
            // Research (--leaf-oracles): Silver's own leaves valued by the abstract exact model of
            // this fight, built from the fight's first searched root and shared by every mode.
            std::unique_ptr<ExactSolver> leafOracle;
            bool leafOracleReady = false, inLeafPlayout = false;
            std::int64_t leafCalls = 0, leafFallbacks = 0, leafCapBinds = 0;
            double leafCapCut = 0;   // summed head value the cap removed
            const LeafModeSpec *leaf = nullptr;   // the mode of the fight being played
            const Config *leafConfig = nullptr;   // and its config (--leaf-label-dump rows)
            if (!leafModes.empty()) {
                sts::search::g_silverLeafOverride = [&](SilverSearcher &searcher, BattleContext &state, double &value) {
                    if (!leaf || leaf->mode == "none" || inLeafPlayout) return false;   // the playout (also the blend's own)
                    if (!leaf->head.empty()) {
                        ++leafCalls;
                        const LeafHead &h = leafHeads.at(leaf->head);
                        double v = headValue(state, h);
                        if (h.shortfall) v = searcher.winNowValue(state) - std::max(0.0, v);
                        else if (leaf->winCap) {
                            const double cap = searcher.winNowValue(state) + leaf->winCapMargin;
                            if (v > cap) { ++leafCapBinds; leafCapCut += v - cap; v = cap; }
                        }
                        v -= leaf->turnPenalty * std::max(0, state.turn - searcher.rootSearchState().turn);
                        if (leafDump.is_open() && leafDumped < 300) {
                            json d = {{"head", leaf->head}, {"value", v}, {"turn", state.turn},
                                      {"curHp", state.player.curHp}, {"trunk", base}};
                            json nz = json::array();
                            for (int i = 0; i < static_cast<int>(feat.size()); ++i)
                                if (feat[i] != 0.f) nz.push_back({i, feat[i]});
                            d["state"] = nz;
                            leafDump << d.dump() << '\n';
                            ++leafDumped;
                        }
                        if (leaf->mode == "hblend") {
                            inLeafPlayout = true;
                            const double p = searcher.rolloutValue(state);
                            inLeafPlayout = false;
                            v = leaf->blend * v + (1 - leaf->blend) * p;
                        }
                        value = v;
                        return true;
                    }
                    if (!leafOracle) {
                        const BattleContext &r = searcher.rootSearchState();
                        leafOracle = std::make_unique<ExactSolver>(r, searcher, hpObjective, maxStates, false,
                                                                   !canonicalOff && canonicalDrawsSafe(r), !keepEnergyWaste);
                        leafOracle->turnCap_ = turnCap;
                        leafOracleReady = leafOracle->relaxedInit();
                    }
                    ++leafCalls;
                    leafOracle->leafNoise_ = leaf->noise;
                    double v = 0;
                    bool ok = false;
                    const bool playable = state.inputState == InputState::PLAYER_NORMAL
                        || state.inputState == InputState::CARD_SELECT;
                    if (leafOracleReady && playable && (leaf->mode == "turn"
                            || (leaf->mode == "turnstart" && state.player.cardsPlayedThisTurn > 0))) {
                        // The rollout policy to the end of the leaf's turn, then the exact value of ending it.
                        leafOracle->setPolicy(1 << 30, searcher);
                        const SAction next = state.inputState == InputState::PLAYER_NORMAL
                            ? leafOracle->policy_.chooseBattleCardPlay(state) : leafOracle->policy_.chooseBattleCardSelect(state);
                        ok = leafOracle->turnPolicyQ(state, next, v);
                    } else if (leafOracleReady) {
                        ok = leafOracle->abstractValue(state, v);
                        if (ok && labelDump.is_open() && leaf->mode == "exact" && leaf->noise == 0
                                && ++labelCalls % leafLabelEvery == 0) {
                            std::vector<float> x(sts::search::combatFeatureCount(), 0.f);
                            sts::search::combatExtractFeatures(state, x.data());
                            json nz = json::array();
                            for (int i = 0; i < static_cast<int>(x.size()); ++i)
                                if (x[i] != 0.f) nz.push_back({i, x[i]});
                            labelDump << json{{"seed", seed}, {"encounter", encounterName},
                                              {"config", leafConfig ? leafConfig->name : ""}, {"turn", state.turn},
                                              {"played", state.player.cardsPlayedThisTurn},
                                              {"input", static_cast<int>(state.inputState)}, {"v", v},
                                              {"state", nz}}.dump() << '\n';
                        }
                        if (ok) v += leafOracle->noiseAt(state);
                    }
                    if (!ok) { ++leafFallbacks; return false; }
                    if (leaf->mode == "blend") {
                        inLeafPlayout = true;
                        const double p = searcher.rolloutValue(state);
                        inLeafPlayout = false;
                        v = leaf->blend * v + (1 - leaf->blend) * p;
                    }
                    value = v;
                    return true;
                };
            }
            const std::vector<LeafModeSpec> modes = leafModes.empty() ? std::vector<LeafModeSpec>{LeafModeSpec{}} : leafModes;
            for (const auto &config : configs) for (const auto &mode : modes) {
                if (!fightFailure.empty()) break;
                leaf = &mode;
                leafConfig = &config;
                sts::search::g_nativeSilverBudgetOverride = config.budget;
                sts::search::g_nativeSilverMaxBackupOverride = config.maxBackup;
                sts::search::g_nativeSilverSearchParamOverride.reset();
                if (config.exploration) {
                    sts::search::NativeSilverSearchParams params;
                    params.exploration = params.explorationChance = *config.exploration;
                    sts::search::g_nativeSilverSearchParamOverride = params;
                }
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
                            if ((relaxedBound || relaxedCheck || relaxedOrder || abstractCheck || abstractOnly) && solver->bounds_) {
                                solver->relaxedFreeDraws_ = relaxedFree;
                                if (solver->relaxedInit()) {
                                    solver->relaxedBound_ = relaxedBound;
                                    solver->relaxedCheck_ = relaxedCheck;
                                    solver->relaxedOrder_ = relaxedOrder;
                                    solver->abstractCheck_ = abstractCheck;
                                } else {
                                    std::cerr << "relaxed bound: this fight is not modelled; flag ignored\n";
                                }
                            }
                        }
                        const auto t0 = std::chrono::steady_clock::now();
                        const auto &edges = searcher.rootNode().edges;
                        const SAction chosen = searcher.bestAction();
                        json acts = json::array();
                        double best = -1e300;
                        int bestIdx = -1, chosenIdx = -1;
                        std::vector<Val> qs;
                        // Research: every root action's value from the abstract exact recursion, from fresh tables.
                        json qAbstract = json::array();
                        double abstractRootSeconds = 0;
                        if ((abstractCheck || abstractOnly) && solver->relaxedReady()) {
                            const auto ta = std::chrono::steady_clock::now();
                            for (const auto &e : edges) {
                                double qa = 0;
                                qAbstract.push_back(solver->abstractQ(root, e.action, qa) ? json(qa) : json(nullptr));
                            }
                            abstractRootSeconds = seconds(ta);
                        }
                        if (abstractOnly && qAbstract.size() != edges.size())
                            throw std::runtime_error("--abstract-only: this fight is not modelled");
                        for (std::size_t i = 0; i < edges.size(); ++i) {
                            Val v;
                            if (abstractOnly) {
                                if (qAbstract[i].is_null()) throw std::runtime_error("--abstract-only: a root action is not modelled");
                                v.v = qAbstract[i].get<double>();
                                v.score = v.hp = v.win = v.capped = -1;   // not tracked by the recursion
                            } else {
                                v = solver->q(root, edges[i].action);
                            }
                            if (!v.exact) throw std::runtime_error("exact solver: a root value came back as a bound");
                            qs.push_back(v);
                            if (v.v > best) { best = v.v; bestIdx = static_cast<int>(i); }
                            if (edges[i].action == chosen) chosenIdx = static_cast<int>(i);
                            json act = {{"label", actionLabel(edges[i].action, root)}, {"q", v.v}, {"score", v.score},
                                        {"hp", v.hp}, {"win", v.win}, {"capped", v.capped},
                                        {"visits", edges[i].visitCount}};
                            if (edges[i].node && edges[i].node->simulationCount > 0) {
                                act["silverQ"] = edges[i].node->evaluationSum / edges[i].node->simulationCount;
                                for (const int k : {8, 32, 128}) act["silverMaxQ" + std::to_string(k)] = maxBackup(edges[i].node, k);
                            }
                            acts.push_back(act);
                        }
                        for (const int k : policyTurns) for (std::size_t variant = 0; variant < policyVariants.size(); ++variant)
                        for (const bool exactTail : {false, true}) {
                            if (exactTail && !policyThenExact) continue;
                            if (exactTail && !solver->relaxedReady()) throw std::runtime_error("--policy-then-exact: this fight is not modelled");
                            const auto &[variantName, rule] = policyVariants[variant];
                            const int from = root.turn + k;
                            std::vector<int> table;
                            if (searcher.rolloutConfig.cardTable)
                                table.assign(searcher.rolloutConfig.cardTable, searcher.rolloutConfig.cardTable + 372 * 2);
                            table.push_back(static_cast<int>(variant) + (exactTail ? 1000 : 0));   // part of the solver key only
                            // A per-root rollout table (prod) changes the policy at every root: keep
                            // only solvers whose table is the current one, or memory grows per root.
                            for (auto it = policySolvers.begin(); it != policySolvers.end();)
                                it = std::equal(table.begin(), table.end() - 1, it->first.second.begin(),
                                                it->first.second.end() - 1) ? std::next(it) : policySolvers.erase(it);
                            auto &ps = policySolvers[{from, table}];
                            if (!ps) {
                                ps = std::make_unique<ExactSolver>(root, searcher, hpObjective, maxStates, false,
                                                                   !canonicalOff && canonicalDrawsSafe(root), !keepEnergyWaste);
                                ps->turnCap_ = policyTurnCap;
                                ps->setPolicy(from, searcher);
                                ps->policy_.blockRule = rule;
                                if (exactTail) {
                                    ps->exactFromTurn_ = from + 1;
                                    ps->exactSource_ = solver.get();
                                }
                            }
                            for (std::size_t i = 0; i < edges.size(); ++i) {
                                const Val v = ps->q(root, edges[i].action);
                                const std::string tag = variantName + std::to_string(k) + (exactTail ? "T" : "");
                                acts[i][tag] = v.v;
                                acts[i][tag + "Hp"] = v.hp;
                                acts[i][tag + "Win"] = v.win;
                                acts[i][tag + "Capped"] = v.capped;
                            }
                        }
                        // "<variant>T": the variant's playout policy for the rest of the root's turn, then the
                        // abstract exact value (the headroom of a perfect turn-start leaf behind a greedy turn).
                        if (policyThisTurn) {
                            if (!solver->relaxedReady()) throw std::runtime_error("--policy-this-turn: this fight is not modelled");
                            for (const auto &[variantName, rule] : policyVariants) {
                                solver->setPolicy(1 << 30, searcher);   // this root's card table; the solver itself stays optimal
                                solver->policy_.blockRule = rule;
                                for (std::size_t i = 0; i < edges.size(); ++i) {
                                    double v = 0;
                                    acts[i][variantName + "T"] = solver->turnPolicyQ(root, edges[i].action, v) ? json(v) : json(nullptr);
                                }
                            }
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
                        if (!leafModes.empty()) row["leafOracle"] = mode.tag;
                        if (!mode.head.empty()) row["headRoot"] = headValue(root, leafHeads.at(mode.head));   // vs max q: the head's level error
                        if (!qAbstract.empty()) {
                            row["qAbstract"] = qAbstract;
                            row["abstractRootSeconds"] = abstractRootSeconds;
                            row["abstractOnly"] = abstractOnly;
                        }
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
                                {"relaxed", solver && (solver->relaxedBound_ || solver->relaxedCheck_)},
                                {"relaxedCutoffs", solver ? solver->relaxedCutoffs_ : 0},
                                {"relaxedDecTighter", solver ? solver->relaxedDecTighter_ : 0},
                                {"relaxedViolations", solver ? solver->relaxedViolations_ : 0},
                                {"relaxedMirrorMismatches", solver ? solver->relaxedMirror_ : 0},
                                {"relaxedMirrorChecked", solver ? solver->relaxedChecked_ : 0},
                                {"relaxedGateMisses", solver ? solver->relaxedGateMisses_ : 0},
                                {"relaxedEndChecks", solver ? solver->relaxedEndChecks_ : 0},
                                {"relaxedDecChecks", solver ? solver->relaxedDecChecks_ : 0},
                                {"relaxedEndSlack<.5,1,2,4,8,16,inf", solver ? json(std::vector<std::int64_t>(solver->relaxedEndSlack_, solver->relaxedEndSlack_ + 7)) : json::array()},
                                {"relaxedDecSlack<.5,1,2,4,8,16,inf", solver ? json(std::vector<std::int64_t>(solver->relaxedDecSlack_, solver->relaxedDecSlack_ + 7)) : json::array()},
                                {"relaxedIntentSlack<.5,1,2,4,8,16,inf", solver ? json(std::vector<std::int64_t>(solver->relaxedIntentSlack_, solver->relaxedIntentSlack_ + 7)) : json::array()},
                                {"relaxedWouldCut", solver ? solver->relaxedWouldCut_ : 0},
                                {"relaxedStates", solver ? solver->relaxedStates() : 0},
                                {"relaxedSeconds", solver ? solver->rxSeconds_[0] : 0.0},
                                {"abstractChecks", solver ? solver->abstractChecks_ : 0},
                                {"abstractMismatches", solver ? solver->abstractMismatches_ : 0},
                                {"abstractMaxDiff", solver ? solver->abstractMaxDiff_ : 0.0},
                                {"abstractStates", solver ? solver->abstractStates() : 0},
                                {"abstractSeconds", solver ? solver->rxSeconds_[1] : 0.0},
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
                if (!leafModes.empty()) {
                    summary["leafOracle"] = mode.tag;
                    summary["leafOracleCalls"] = leafCalls;
                    summary["leafOracleFallbacks"] = leafFallbacks;
                    if (mode.winCap) { summary["leafCapBinds"] = leafCapBinds; summary["leafCapCut"] = leafCapCut; }
                    leafCalls = leafFallbacks = leafCapBinds = 0;
                    leafCapCut = 0;
                }
                out << summary.dump() << '\n';
                out.flush();
                std::cerr << summary.dump() << '\n';
            }
            sts::search::g_silverLeafOverride = nullptr;
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "exact_combat_solver: " << e.what() << '\n';
        return 1;
    }
}
