// Research only (#1058): deterministic turn-plan enumeration; see SilverTurnPlan.h.
#include "sim/search/SilverTurnPlan.h"

#include <algorithm>
#include <cmath>
#include <unordered_map>

#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"

namespace sts::search {

    namespace {

        int incomingOf(const BattleContext &bc, int act) {
            int incoming = 0;
            for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                const auto &m = bc.monsters.arr[i];
                if (m.isDeadOrEscaped() || m.isHalfDead()) continue;
                incoming += (m.pendingMoveRolls > 0 || m.pendingDirectMoveChoice != 0) ? 5 * act : m.publicIncomingDamage(bc);
            }
            return incoming;
        }

        int aliveCount(const BattleContext &bc) {
            int n = 0;
            for (int i = 0; i < bc.monsters.monsterCount; ++i)
                if (bc.monsters.arr[i].isAlive() && !bc.monsters.arr[i].isHalfDead()) ++n;
            return n;
        }

        std::vector<float> featuresOf(const BattleContext &root, const BattleContext &end, TurnPlanEnd type,
                                      const Action &last, int length, int act) {
            std::vector<float> f;
            f.reserve(32);
            f.push_back(type == TurnPlanEnd::END_TURN);
            f.push_back(type == TurnPlanEnd::CHANCE);
            f.push_back(type == TurnPlanEnd::FIGHT_OVER);
            f.push_back(type == TurnPlanEnd::LEFT_TURN);
            f.push_back(end.outcome == Outcome::PLAYER_VICTORY);
            const auto &p0 = root.player, &p1 = end.player;
            f.push_back(static_cast<float>(p0.curHp - p1.curHp));
            f.push_back(static_cast<float>(p1.block - p0.block));
            f.push_back(static_cast<float>(p1.energy));
            int removed = 0, kills = 0, vuln = 0, weak = 0;
            float minFrac = 1.f;
            const int mc = std::min(root.monsters.monsterCount, end.monsters.monsterCount);
            for (int i = 0; i < mc; ++i) {
                const auto &a = root.monsters.arr[i], &b = end.monsters.arr[i];
                if (!a.isAlive() || a.isHalfDead()) continue;
                const bool dead = !b.isAlive() || b.isDeadOrEscaped();
                removed += a.curHp - (dead ? 0 : b.curHp);
                if (dead) { ++kills; continue; }
                vuln += b.vulnerable - a.vulnerable;
                weak += b.weak - a.weak;
                if (b.maxHp > 0) minFrac = std::min(minFrac, static_cast<float>(b.curHp) / static_cast<float>(b.maxHp));
            }
            f.push_back(static_cast<float>(removed));
            f.push_back(static_cast<float>(kills));
            f.push_back(minFrac);
            f.push_back(static_cast<float>(p1.strength - p0.strength));
            f.push_back(static_cast<float>(p1.dexterity - p0.dexterity));
            f.push_back(static_cast<float>(vuln));
            f.push_back(static_cast<float>(weak));
            f.push_back(static_cast<float>(p1.cardsPlayedThisTurn - p0.cardsPlayedThisTurn));
            f.push_back(static_cast<float>(p1.attacksPlayedThisTurn - p0.attacksPlayedThisTurn));
            f.push_back(static_cast<float>(p1.skillsPlayedThisTurn - p0.skillsPlayedThisTurn));
            f.push_back(static_cast<float>(static_cast<int>(end.cards.exhaustPile.size())
                                           - static_cast<int>(root.cards.exhaustPile.size())));
            f.push_back(static_cast<float>(root.potionCount - end.potionCount));
            const int incoming = end.outcome == Outcome::UNDECIDED ? incomingOf(end, act) : 0;
            f.push_back(static_cast<float>(std::max(0, incoming - p1.block)));
            f.push_back(static_cast<float>(incoming));
            f.push_back(static_cast<float>(end.cards.cardsInHand));
            f.push_back(static_cast<float>(length));
            f.push_back(last.getActionType() == ActionType::CARD);
            f.push_back(last.getActionType() == ActionType::POTION);
            // Context (equal for every plan of a root).
            f.push_back(p0.maxHp > 0 ? static_cast<float>(p0.curHp) / static_cast<float>(p0.maxHp) : 0.f);
            f.push_back(static_cast<float>(p0.energy));
            f.push_back(static_cast<float>(aliveCount(root)));
            f.push_back(static_cast<float>(incomingOf(root, act)));
            f.push_back(static_cast<float>(p0.block));
            f.push_back(static_cast<float>(root.turn));
            return f;
        }

        struct Child { int node; int action; double logp; };

        struct PlanNode {
            std::vector<Child> children;   // deterministic steps to other decision states
            int parents = 0;
            int depth = 0;                 // shortest line length from the root
        };

        struct PendingPlan {
            int node;            // decision node the final action leaves from (the terminal node for FIGHT_OVER)
            double lastLogp;     // log prior of the final action at `node` (0 for FIGHT_OVER)
            TurnPlan plan;
        };

    }  // namespace

    const std::vector<std::string> &turnPlanFeatureNames() {
        static const std::vector<std::string> names = {
            "end_turn", "chance", "fight_over", "left_turn", "won",
            "hp_lost", "block_gained", "energy_left", "enemy_hp_removed", "kills", "min_enemy_hp_frac",
            "strength_gained", "dexterity_gained", "vulnerable_applied", "weak_applied",
            "cards_played", "attacks_played", "skills_played", "exhausted", "potions_used",
            "unblocked_incoming", "incoming", "hand_left", "length", "last_is_card", "last_is_potion",
            "ctx_hp_frac", "ctx_energy", "ctx_alive", "ctx_incoming", "ctx_block", "ctx_turn",
        };
        return names;
    }

    TurnPlanSet enumerateTurnPlans(const BattleContext &root, const SilverSearchContext &context,
                                   const TurnPlanConfig &config, const TurnPlanPrior &prior) {
        TurnPlanSet set;
        SilverSearcher enumerator(root, context);
        set.rootActions = enumerator.enumerateActions(root);
        const int n = static_cast<int>(set.rootActions.size());
        if (n > static_cast<int>(TurnPlanMask().size())) { set.capped = true; return set; }

        std::vector<PlanNode> nodes(1);
        std::unordered_map<std::size_t, int> index;
        index.emplace(hashBattleState(root), 0);
        std::vector<PendingPlan> pending;
        std::unordered_map<std::size_t, int> terminalIndex;   // FIGHT_OVER plans by end-state hash

        // Executes `a` on a copy of `from`; false when an RNG stream advanced (Silver's chance test).
        auto step = [&](const BattleContext &from, const Action &a, BattleContext &out) {
            out = from;
            const SearchRngState pre = captureSearchRng(out);
            seedSearchRng(out, searchRandomnessBase(out));
            a.execute(out);
            ++set.execs;
            if (searchRngCounter(out) != 0) return false;
            restoreSearchRng(out, pre);
            return true;
        };
        auto addPlan = [&](int node, double lastLogp, TurnPlanEnd type, const Action &last,
                           const BattleContext &end, int length) {
            PendingPlan p{node, lastLogp, {}};
            p.plan.end = type;
            p.plan.last = last;
            p.plan.length = length;
            p.plan.features = featuresOf(root, end, type, last, length, config.act);
            pending.push_back(std::move(p));
            if (static_cast<int>(pending.size()) > config.maxPlans) set.capped = true;
        };

        std::vector<std::pair<int, BattleContext>> stack;
        stack.emplace_back(0, root);
        BattleContext next;
        while (!stack.empty() && !set.capped) {
            auto [id, state] = std::move(stack.back());
            stack.pop_back();
            const auto actions = enumerator.enumerateActions(state);
            std::vector<double> p;
            if (prior && actions.size() >= 2) p = prior(state, actions);
            for (std::size_t ai = 0; ai < actions.size() && !set.capped; ++ai) {
                const Action &a = actions[ai];
                const double logp = p.size() == actions.size() ? std::log(std::max(p[ai], 1e-12)) : 0.0;
                const int length = nodes[id].depth + 1;
                if (a.getActionType() == ActionType::END_TURN) {
                    addPlan(id, logp, TurnPlanEnd::END_TURN, a, state, length);
                    continue;
                }
                if (!step(state, a, next)) {
                    addPlan(id, logp, TurnPlanEnd::CHANCE, a, next, length);
                    continue;
                }
                if (next.outcome != Outcome::UNDECIDED || next.turn != root.turn) {
                    const auto type = next.outcome != Outcome::UNDECIDED ? TurnPlanEnd::FIGHT_OVER : TurnPlanEnd::LEFT_TURN;
                    const std::size_t h = hashBattleState(next);
                    // A terminal state reached twice is one plan: record it as a node so the masks merge.
                    auto [it, fresh] = terminalIndex.emplace(h, static_cast<int>(nodes.size()));
                    if (fresh) {
                        nodes.push_back({});
                        nodes.back().depth = length;
                        addPlan(it->second, 0.0, type, a, next, length);
                    } else {
                        ++set.merges;
                    }
                    nodes[id].children.push_back({it->second, static_cast<int>(ai), logp});
                    ++nodes[it->second].parents;
                    continue;
                }
                const std::size_t h = hashBattleState(next);
                auto [it, fresh] = index.emplace(h, static_cast<int>(nodes.size()));
                if (fresh) {
                    if (static_cast<int>(nodes.size()) >= config.maxNodes) { set.capped = true; break; }
                    nodes.push_back({});
                    nodes.back().depth = length;
                    stack.emplace_back(it->second, next);
                } else {
                    ++set.merges;
                }
                nodes[id].children.push_back({it->second, static_cast<int>(ai), logp});
                ++nodes[it->second].parents;
            }
        }
        set.nodes = static_cast<int>(nodes.size());
        if (set.capped) return set;

        // First-action masks and best-prior lines in topological order (Kahn). A cycle would leave nodes
        // unvisited; they are relaxed afterwards until nothing changes.
        std::vector<TurnPlanMask> mask(nodes.size());
        std::vector<double> lp(nodes.size(), -std::numeric_limits<double>::infinity());
        std::vector<int> bestFirst(nodes.size(), -1);
        lp[0] = 0.0;
        auto relax = [&](int from, const Child &c) {
            bool changed = false;
            TurnPlanMask add;
            if (from == 0) add.set(static_cast<std::size_t>(c.action));
            else add = mask[from];
            if ((mask[c.node] | add) != mask[c.node]) { mask[c.node] |= add; changed = true; }
            const double cand = lp[from] + c.logp;
            if (cand > lp[c.node]) {
                lp[c.node] = cand;
                bestFirst[c.node] = from == 0 ? c.action : bestFirst[from];
                changed = true;
            }
            return changed;
        };
        std::vector<int> indeg(nodes.size());
        for (std::size_t i = 0; i < nodes.size(); ++i) indeg[i] = nodes[i].parents;
        std::vector<int> queue{0};
        std::vector<char> done(nodes.size(), 0);
        while (!queue.empty()) {
            const int u = queue.back();
            queue.pop_back();
            done[u] = 1;
            for (const auto &c : nodes[u].children) {
                relax(u, c);
                if (--indeg[c.node] == 0) queue.push_back(c.node);
            }
        }
        if (std::find(done.begin(), done.end(), 0) != done.end()) {
            for (bool changed = true; changed;) {
                changed = false;
                for (std::size_t u = 0; u < nodes.size(); ++u)
                    for (const auto &c : nodes[u].children) changed |= relax(static_cast<int>(u), c);
            }
        }

        set.plans.reserve(pending.size());
        for (auto &pp : pending) {
            auto &plan = pp.plan;
            const bool terminalNode = plan.end == TurnPlanEnd::FIGHT_OVER || plan.end == TurnPlanEnd::LEFT_TURN;
            if (terminalNode) {
                plan.firstMask = mask[pp.node];
                plan.logPrior = lp[pp.node];
                plan.bestFirst = bestFirst[pp.node];
            } else if (pp.node == 0) {
                const int ai = static_cast<int>(std::find(set.rootActions.begin(), set.rootActions.end(), plan.last)
                                                - set.rootActions.begin());
                plan.firstMask.set(static_cast<std::size_t>(ai));
                plan.logPrior = pp.lastLogp;
                plan.bestFirst = ai;
            } else {
                plan.firstMask = mask[pp.node];
                plan.logPrior = lp[pp.node] + pp.lastLogp;
                plan.bestFirst = bestFirst[pp.node];
            }
            set.plans.push_back(std::move(plan));
        }
        return set;
    }

}
