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
//   --turn-cap T       an undecided fight past turn T scores as Silver's loss leaf (default 25); every
//                      action reports the probability `capped` of reaching it under optimal play
//   --keep-energy-waste  keep Silver's loss-score energy-waste term (and the counter in the
//                        state key); by default it is dropped, which only changes losing leaves
//   --encounter NAME   force the encounter (CULTIST, JAW_WORM, TWO_LOUSE, SMALL_SLIMES)
//   --max-states N     give up on a fight above N memoized states (default 60,000,000)
//   --objective silver|hp   value optimised by the solver (default silver; hp = end HP, 0 on death)
//   --verify-memo      keep full states and check every memo hit with equalForSearch (slow)
//   --no-canonical-draws  enumerate draw orders too (slow; a check of the canonical-draw probabilities)

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
        void add(std::uint64_t v) {
            a = splitmix(a ^ v);
            b = splitmix(b + v * 0xD6E8FEB86659FD93ULL + 0x632BE59BD9B4E019ULL);
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
        Key key() const { return {a, b}; }
    };

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

    Key stateKey(const BattleContext &bc) {
        KeyBuilder k;
        k.add(bc.turn); k.add(static_cast<int>(bc.outcome)); k.add(static_cast<int>(bc.inputState));
        k.add(bc.energyWasted); k.add(bc.cardsDrawn); k.add(bc.monsterTurnIdx);
        k.add(static_cast<std::uint64_t>(bc.miscBits.to_ullong()));
        k.add((bc.smokeBombUsed ? 1 : 0) | (bc.skipMonsterTurn ? 2 : 0) | (bc.intentsHidden ? 4 : 0));
        k.add(bc.potionCount); k.add(bc.potionCapacity);
        for (int i = 0; i < bc.potionCapacity; ++i) k.add(static_cast<int>(bc.potions[i]));
        const auto &p = bc.player;
        k.add(p.gold); k.add(p.curHp); k.add(p.maxHp); k.add(p.energy); k.add(p.energyPerTurn); k.add(p.cardDrawPerTurn);
        k.add(static_cast<int>(p.stance)); k.add(p.orbSlots); k.add(p.lastTargetedMonster);
        k.add(p.block); k.add(p.artifact); k.add(p.dexterity); k.add(p.focus); k.add(p.strength);
        k.add(static_cast<std::uint64_t>(p.justAppliedBits)); k.add(p.statusBits0); k.add(static_cast<std::uint64_t>(p.statusBits1));
        k.add(static_cast<int>(p.statusMap.size()));
        for (const auto &[s, v] : p.statusMap) { k.add(static_cast<int>(s)); k.add(static_cast<int>(v)); }
        k.add(p.relicBits0); k.add(p.relicBits1);
        for (int v : {int(p.happyFlowerCounter), int(p.incenseBurnerCounter), int(p.inkBottleCounter), int(p.inserterCounter),
                      int(p.nunchakuCounter), int(p.penNibCounter), int(p.sundialCounter), int(p.haveUsedNecronomiconThisTurn),
                      int(p.combustHpLoss), int(p.devaFormEnergyPerTurn), int(p.echoFormCardsDoubled), int(p.panacheCounter),
                      int(p.cardsPlayedThisTurn), int(p.attacksPlayedThisTurn), int(p.skillsPlayedThisTurn),
                      int(p.orangePelletsCardTypesPlayed.to_ulong()), int(p.cardsDiscardedThisTurn),
                      int(p.lastAttackUnblockedDamage), int(p.timesDamagedThisCombat), int(p.bomb1), int(p.bomb2), int(p.bomb3)})
            k.add(v);
        const auto &mg = bc.monsters;
        k.add(mg.monstersAlive); k.add(mg.monsterCount);
        k.add(static_cast<int>(mg.extraRollMoveOnTurn.to_ulong())); k.add(static_cast<int>(mg.skipTurn.to_ulong()));
        for (int i = 0; i < mg.monsterCount; ++i) {
            const auto &m = mg.arr[i];
            if (m.pendingMoveRolls != 0 || m.pendingDirectMoveChoice != 0)
                throw std::runtime_error("exact solver: pending hidden monster roll (Runic Dome) unsupported");
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
        k.add(cm.nextUniqueCardId); k.add(cm.handNormalityCount); k.add(cm.handPainCount); k.add(cm.strikeCount);
        k.add(cm.handBloodCardCount); k.add(cm.drawPileBloodCardCount); k.add(cm.discardPileBloodCardCount);
        k.addSorted(cm.hand.begin(), cm.hand.begin() + cm.cardsInHand);
        k.add(cm.drawPile.size()); k.add(cm.drawPile.knownTop()); k.add(cm.drawPile.knownBottom());
        k.add(cm.drawPile.isConcrete() ? 1 : 0);
        for (const auto &c : cm.drawPile) k.addCard(c);
        k.addSorted(cm.discardPile.begin(), cm.discardPile.end());
        k.addSorted(cm.exhaustPile.begin(), cm.exhaustPile.end());
        for (const auto &c : cm.stasisCards) k.addCard(c);
        return k.key();
    }

    // ---- solver ----------------------------------------------------------

    struct Val {
        double v = 0;     // optimised objective
        double score = 0; // Silver terminal evaluation
        double hp = 0;    // end HP (0 on death), before post-combat heals
        double win = 0;
        double capped = 0; // probability of reaching the turn cap
    };

    struct Outcome1 { BattleContext state; double p; };

    // Open-addressing memo, about 40 bytes per state (an unordered_map node took ~95).
    class CompactMemo {
        struct Slot { std::uint64_t a = 0, b = 0; double v = 0; float hp = 0, win = 0, capped = 0, score = 0; };
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
            return true;
        }
        void emplace(Key k, const Val &v) {
            if ((size_ + 1) * 10 > slots_.size() * 7) grow();
            k = norm(k);
            auto &s = slots_[probe(k)];
            if (empty(s)) ++size_;
            s = {k.a, k.b, v.v, static_cast<float>(v.hp), static_cast<float>(v.win),
                 static_cast<float>(v.capped), static_cast<float>(v.score)};
        }
    };

    class ExactSolver {
    public:
        ExactSolver(const BattleContext &battleRoot, const SilverSearcher &live, bool hpObjective,
                    std::int64_t maxStates, bool verify, bool canonicalDraws, bool dropEnergyWaste)
            : scorer_(battleRoot, live.searchContext()), enumerator_(battleRoot, live.searchContext()),
              hpObjective_(hpObjective), dropEnergyWaste_(dropEnergyWaste), maxStates_(maxStates), verify_(verify) {
            scorer_.evalWeights = live.evalWeights;
            enumerator_.evalWeights = live.evalWeights;
            script_.canonicalDraws = canonicalDraws;
        }

        std::vector<SAction> actions(const BattleContext &s) { return enumerator_.enumerateActions(s); }

        Val q(const BattleContext &s, const SAction &a) {
            Val total;
            double mass = 0;
            for (auto &o : outcomes(s, a)) {
                const Val v = solve(o.state);
                total.v += o.p * v.v; total.score += o.p * v.score; total.hp += o.p * v.hp; total.win += o.p * v.win;
                total.capped += o.p * v.capped;
                mass += o.p;
            }
            if (std::abs(mass - 1.0) > 1e-9)
                throw std::runtime_error("exact solver: outcome probabilities sum to " + std::to_string(mass));
            return total;
        }

        std::size_t states() const { return memo_.size(); }
        // Drop every memoized state (after an infeasible solve) to free memory.
        void clear() { memo_.clear(); inProgress_.clear(); }
        std::int64_t replays() const { return replays_; }
        std::int64_t verifiedHits() const { return verifiedHits_; }

    private:
        SilverSearcher scorer_;
        SilverSearcher enumerator_;
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

        Val solve(const BattleContext &s) {
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
            if (memoize) {
                key = stateKey(s);
                checkSame(key, s);
                if (Val hit; memo_.find(key, hit)) return hit;
                if (inProgress_.count(key)) throw std::runtime_error("exact solver: cycle in the game graph");
                inProgress_[key] = 1;
            }
            const auto acts = actions(s);
            Val best;
            if (acts.empty()) {
                best = terminal(s);
            } else {
                best.v = -1e300;
                for (const auto &a : acts) {
                    const Val v = q(s, a);
                    if (v.v > best.v) best = v;
                }
            }
            if (memoize) {
                inProgress_.erase(key);
                memo_.emplace(key, best);
                ++statesByTurn_[s.turn];
                if (memo_.size() % 100000 == 0)
                    std::cerr << "  states=" << memo_.size() << " replays=" << replays_ << " turn=" << s.turn << '\n';
                if (static_cast<std::int64_t>(memo_.size()) > maxStates_)
                    throw Infeasible("more than " + std::to_string(maxStates_) + " states");
            }
            return best;
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
                    out.push_back({next, p});
                    continue;
                }
                const Key key = stateKey(next);
                if (auto it = index.find(key); it != index.end()) {
                    out[it->second].p += p;
                } else {
                    index.emplace(key, out.size());
                    out.push_back({next, p});
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
                         " [--no-canonical-draws]\n";
            return 2;
        }
        const int count = std::stoi(argv[1]);
        const std::uint64_t startSeed = std::stoull(argv[2]);
        std::ofstream out(argv[3], std::ios::app);
        if (!out) throw std::runtime_error(std::string("cannot open ") + argv[3]);
        std::vector<Config> configs;
        std::optional<MonsterEncounter> forced;
        std::int64_t maxStates = 60'000'000;
        bool hpObjective = false, verify = false, canonicalOff = false, keepEnergyWaste = false;
        int turnCap = 25;
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
            else if (arg == "--keep-energy-waste") keepEnergyWaste = true;
            else if (arg == "--turn-cap") turnCap = std::stoi(value());
            else throw std::invalid_argument("unknown option " + arg);
        }
        if (configs.empty()) configs = {parseConfig("prod"), parseConfig("live"),
                                        parseConfig("flatprior:2500"), parseConfig("flatprior:10000")};
        const std::string objective = std::string(hpObjective ? "hp" : "silver") + (keepEnergyWaste ? "" : "-noew");

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
                sts::search::g_nativeSilverRootObserver = [&](const sts::search::NativeSilverRootView &view) {
                    if (view.skipped || !fightFailure.empty()) return;
                    const SilverSearcher &searcher = view.searcher;
                    const BattleContext &root = searcher.rootSearchState();
                    if (root.turn <= unsolvableThroughTurn) { ++unscoredRoots; return; }
                    try {
                        if (!solver) {
                            solver = std::make_unique<ExactSolver>(root, searcher, hpObjective, maxStates, verify,
                                                                   !canonicalOff && canonicalDrawsSafe(root), !keepEnergyWaste);
                            solver->turnCap_ = turnCap;
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
                                {"solveSeconds", solveSeconds}, {"seconds", seconds(fightStart)}};
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
