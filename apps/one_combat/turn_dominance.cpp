// ---- turndomgen (research: end-of-turn dominance opportunity in Silver's real decisions) ----
// Plays whole runs as bestbench does (runFullRunOOC with the process's OOC and
// Silver settings). At every searched Silver root it follows every line of the
// player's actions from each root edge to the end of the turn, as long as the
// line is deterministic (no RNG stream advances, the search's own chance
// test). Each line ends where END_TURN is legal (that state is an end-of-turn
// candidate) or the fight ends. End-of-turn candidates are grouped by the
// exact_combat_solver end-of-turn projection (everything but player HP and
// block, each live monster's HP, block, Vulnerable and Weak, and the fields the
// end of the turn forgets); within a group a candidate is dominated when another
// one has at least the player HP and block and at most every live monster's HP
// and block and at least its Vulnerable and Weak, and is better in one of them.
// A root edge is dominated when all its lines are deterministic and every
// candidate they reach is dominated. Observation only: the runs are unchanged.
//
// The dominance is the naive one: it is exact only where the fight's value is
// monotone in the compared fields (exact_combat_solver dominanceSafe); the row
// says whether that gate holds (`gateSafe`). Elsewhere a dominated edge is an
// opportunity to inspect, not a proven mistake.
#include "one_combat/driver_shared.h"
#include "run_driver.h"
#include "combat/BattleContextBinary.h"
#include "constants/MonsterEncounters.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverSearcher.h"

#include <unordered_map>

namespace {

    std::uint64_t splitmix(std::uint64_t x) {
        x += 0x9E3779B97F4A7C15ULL;
        x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
        x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
        return x ^ (x >> 31);
    }

    // CardInstance::exactChanceClassKey (compiled only with STS_EXACT_CHANCE):
    // equal for copies that are equivalent for search.
    std::uint64_t classKey(const CardInstance &c) {
        std::uint64_t k = static_cast<std::uint64_t>(static_cast<int>(c.id));
        k = k * 1000003u + static_cast<std::uint16_t>(c.specialData);
        k = k * 1000003u + static_cast<std::uint8_t>(c.cost);
        k = k * 1000003u + static_cast<std::uint8_t>(c.costForTurn);
        k = k * 1000003u + (c.upgraded ? 1u : 0u) + (c.freeToPlayOnce ? 2u : 0u) + (c.retain ? 4u : 0u);
        if (c.usesSpecialData()) k = k * 1000003u + static_cast<std::uint16_t>(c.uniqueId) + 1u;
        return k;
    }

    struct Key {
        std::uint64_t a = 0, b = 0;
        bool operator==(const Key &o) const { return a == o.a && b == o.b; }
    };
    struct KeyHash { std::size_t operator()(const Key &k) const { return static_cast<std::size_t>(k.a); } };

    // exact_combat_solver's KeyBuilder.
    struct KeyBuilder {
        std::uint64_t a = 0x243F6A8885A308D3ULL, b = 0x13198A2E03707344ULL;
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
        Key key() const { return {splitmix(a ^ rotl(b, 17)), splitmix(b ^ splitmix(a))}; }
    };

    // exact_combat_solver statePrefix(bc, endTurnProjection = true) without the
    // player's block and HP (compared, not keyed here). Monster Vulnerable and
    // Weak status bits are left out with their amounts.
    Key endTurnProjection(const BattleContext &bc) {
        KeyBuilder k;
        k.add(bc.turn); k.add(static_cast<int>(bc.outcome)); k.add(static_cast<int>(bc.inputState));
        k.add(bc.cardsDrawn); k.add(bc.monsterTurnIdx);
        k.add(static_cast<std::uint64_t>(bc.miscBits.to_ullong()));
        k.add((bc.smokeBombUsed ? 1 : 0) | (bc.skipMonsterTurn ? 2 : 0) | (bc.intentsHidden ? 4 : 0));
        k.add(bc.potionCount); k.add(bc.potionCapacity);
        for (int i = 0; i < bc.potionCapacity; ++i) k.add(static_cast<int>(bc.potions[i]));
        const auto &p = bc.player;
        k.add(p.gold); k.add(p.maxHp); k.add(p.energyPerTurn); k.add(p.cardDrawPerTurn);
        k.add(static_cast<int>(p.stance)); k.add(p.orbSlots);
        k.add(p.artifact); k.add(p.dexterity); k.add(p.focus); k.add(p.strength);
        k.add(static_cast<std::uint64_t>(p.justAppliedBits)); k.add(p.statusBits0); k.add(static_cast<std::uint64_t>(p.statusBits1));
        k.add(static_cast<int>(p.statusMap.size()));
        for (const auto &[s, v] : p.statusMap) { k.add(static_cast<int>(s)); k.add(static_cast<int>(v)); }
        k.add(p.relicBits0); k.add(p.relicBits1);
        for (int v : {int(p.happyFlowerCounter), int(p.incenseBurnerCounter), int(p.inkBottleCounter), int(p.inserterCounter),
                      int(p.nunchakuCounter), int(p.penNibCounter), int(p.sundialCounter), int(p.haveUsedNecronomiconThisTurn),
                      int(p.combustHpLoss), int(p.devaFormEnergyPerTurn), int(p.echoFormCardsDoubled), int(p.panacheCounter),
                      int(p.orangePelletsCardTypesPlayed.to_ulong()), int(p.cardsDiscardedThisTurn),
                      int(p.lastAttackUnblockedDamage), int(p.timesDamagedThisCombat), int(p.bomb1), int(p.bomb2), int(p.bomb3)})
            k.add(v);
        const auto &mg = bc.monsters;
        k.add(mg.monsterCount);
        k.add(static_cast<int>(mg.extraRollMoveOnTurn.to_ulong())); k.add(static_cast<int>(mg.skipTurn.to_ulong()));
        const std::uint64_t vulnWeak = (1ULL << static_cast<int>(MonsterStatus::VULNERABLE))
            | (1ULL << static_cast<int>(MonsterStatus::WEAK));
        for (int i = 0; i < mg.monsterCount; ++i) {
            const auto &m = mg.arr[i];
            k.add(m.idx); k.add(int(m.id));
            if (!m.isAlive()) continue;
            for (int v : {m.maxHp, int(m.isEscapingB), int(m.halfDead), int(m.escapeNext), int(m.moveHistory[0]),
                          int(m.moveHistory[1]), int(m.artifact), int(m.blockReturn), int(m.choked),
                          int(m.corpseExplosion), int(m.lockOn), int(m.mark), int(m.metallicize), int(m.platedArmor),
                          int(m.poison), int(m.regen), int(m.shackled), m.strength, m.uniquePower0,
                          int(m.uniquePower1), m.miscInfo, int(m.occupantGeneration), int(m.latentDamageMask),
                          int(m.latentDamageMaterialized), int(m.pendingMoveRolls), int(m.pendingDirectMoveChoice)})
                k.add(v);
            k.add(m.statusBits & ~vulnWeak);
        }
        const auto &cm = bc.cards;
        // End of turn: the hand joins the discard pile (ethereal cards exhaust),
        // so only the union matters; copies are interchangeable by class.
        std::vector<std::uint64_t> leaving, ethereal;
        for (int i = 0; i < cm.cardsInHand; ++i)
            (cm.hand[i].isEthereal() ? ethereal : leaving).push_back(classKey(cm.hand[i]));
        for (const auto &c : cm.discardPile) leaving.push_back(classKey(c));
        for (auto *v : {&leaving, &ethereal}) {
            std::sort(v->begin(), v->end());
            k.add(static_cast<int>(v->size()));
            for (auto x : *v) k.add(x);
        }
        k.add(cm.nextUniqueCardId); k.add(cm.strikeCount); k.add(cm.drawPileBloodCardCount);
        k.add(cm.drawPile.size()); k.add(cm.drawPile.knownTop()); k.add(cm.drawPile.knownBottom());
        k.add(cm.drawPile.isConcrete() ? 1 : 0);
        for (const auto &c : cm.drawPile) k.add(classKey(c));
        std::vector<std::uint64_t> ex;
        for (const auto &c : cm.exhaustPile) ex.push_back(classKey(c));
        std::sort(ex.begin(), ex.end());
        for (auto x : ex) k.add(x);
        for (const auto &c : cm.stasisCards) k.addCard(c);
        return k.key();
    }

    // exact_combat_solver dominanceSafe: starter cards, Burning Blood only, no
    // potions and the eight Act-1 weak monsters, where the naive dominance is exact.
    bool gateSafe(const BattleContext &bc) {
        static const std::vector<CardId> cards = {
            CardId::STRIKE_RED, CardId::DEFEND_RED, CardId::BASH, CardId::ASCENDERS_BANE,
        };
        auto ok = [&](const CardInstance &c) { return std::find(cards.begin(), cards.end(), c.id) != cards.end(); };
        const auto &cm = bc.cards;
        for (int i = 0; i < cm.cardsInHand; ++i) if (!ok(cm.hand[i])) return false;
        for (const auto &c : cm.drawPile) if (!ok(c)) return false;
        for (const auto &c : cm.discardPile) if (!ok(c)) return false;
        for (const auto &c : cm.exhaustPile) if (!ok(c)) return false;
        if (bc.potionCount != 0) return false;
        const int bb = static_cast<int>(RelicId::BURNING_BLOOD);
        const std::uint64_t want0 = bb < 64 ? 1ULL << bb : 0, want1 = bb < 64 ? 0 : 1ULL << (bb - 64);
        if (bc.player.relicBits0 != want0 || bc.player.relicBits1 != want1) return false;
        static const std::vector<MonsterId> monsters = {
            MonsterId::CULTIST, MonsterId::JAW_WORM, MonsterId::RED_LOUSE, MonsterId::GREEN_LOUSE,
            MonsterId::ACID_SLIME_S, MonsterId::SPIKE_SLIME_S, MonsterId::SPIKE_SLIME_M, MonsterId::ACID_SLIME_M,
        };
        for (int i = 0; i < bc.monsters.monsterCount; ++i)
            if (std::find(monsters.begin(), monsters.end(), bc.monsters.arr[i].id) == monsters.end()) return false;
        return true;
    }

    struct EndState {
        Key proj;
        bool terminal = false;
        bool won = false;
        int hp = 0, block = 0;
        int incoming = 0;         // public incoming attack damage (SilverRolloutAgent::getIncomingDamage)
        int monsterCount = 0;
        std::array<bool, 5> alive{};
        std::array<int, 5> mhp{}, mblock{}, mvuln{}, mweak{};
        std::vector<int> edges;   // root edges with a deterministic line to this state
        bool survivor = true;
        bool materiallyDominated = false;
    };

    EndState endStateOf(const BattleContext &bc, int act) {
        EndState e;
        e.terminal = bc.outcome != Outcome::UNDECIDED;
        e.won = bc.outcome == Outcome::PLAYER_VICTORY;
        if (!e.terminal) e.proj = endTurnProjection(bc);
        e.hp = bc.player.curHp; e.block = bc.player.block;
        e.monsterCount = bc.monsters.monsterCount;
        for (int i = 0; i < e.monsterCount && i < 5; ++i) {
            const auto &m = bc.monsters.arr[i];
            e.alive[i] = m.isAlive();
            e.mhp[i] = m.curHp; e.mblock[i] = m.block; e.mvuln[i] = m.vulnerable; e.mweak[i] = m.weak;
            if (m.isDeadOrEscaped() || m.isHalfDead()) continue;
            e.incoming += (m.pendingMoveRolls > 0 || m.pendingDirectMoveChoice != 0) ? 5 * act : m.publicIncomingDamage(bc);
        }
        return e;
    }

    // a (covering b) is better in a field that can change the fight's value on its
    // own: more player HP, a monster dead or with less HP or more Vulnerable or Weak,
    // or more block while b's block is below the incoming damage. Less monster block
    // and block beyond the incoming damage are not counted.
    bool materiallyBetter(const EndState &a, const EndState &b) {
        if (a.hp > b.hp) return true;
        if (a.block > b.block && b.block < b.incoming) return true;
        for (int i = 0; i < a.monsterCount; ++i) {
            if (!b.alive[i]) continue;
            if (!a.alive[i] || a.mhp[i] < b.mhp[i] || a.mvuln[i] > b.mvuln[i] || a.mweak[i] > b.mweak[i]) return true;
        }
        return false;
    }

    // a is at least as good as b in every compared field (same projection).
    bool covers(const EndState &a, const EndState &b) {
        if (a.hp < b.hp || a.block < b.block) return false;
        for (int i = 0; i < a.monsterCount; ++i) {
            if (!a.alive[i]) continue;
            if (!b.alive[i]) return false;
            if (a.mhp[i] > b.mhp[i] || a.mblock[i] > b.mblock[i] || a.mvuln[i] < b.mvuln[i] || a.mweak[i] < b.mweak[i])
                return false;
        }
        return true;
    }

    std::string actionLabel(const search::Action &a, const BattleContext &bc) {
        std::ostringstream os;
        a.printDesc(os, bc);
        return os.str();
    }

    std::string hexOf(const std::vector<std::uint8_t> &bytes) {
        static const char *digits = "0123456789abcdef";
        std::string s;
        s.reserve(bytes.size() * 2);
        for (auto b : bytes) { s += digits[b >> 4]; s += digits[b & 15]; }
        return s;
    }

    // The root as one_combat endgamerootgen writes it (draw pile flattened in its
    // information-set order; drawKnownBottom/drawKnownTop give the regions back).
    nlohmann::json rootSnapshot(const BattleContext &root) {
        BattleContext flat = root;
        const auto &pile = root.cards.drawPile;
        if (!pile.isConcrete()) flat.cards.drawPile.assignConcrete(std::vector<CardInstance>(pile.begin(), pile.end()));
        return {{"state", hexOf(serializeBattleContext(flat))}, {"drawConcrete", pile.isConcrete()},
                {"drawKnownBottom", pile.knownBottom()}, {"drawKnownTop", pile.knownTop()},
                {"extras", {{"energyWasted", root.energyWasted}, {"cardsDrawn", root.cardsDrawn},
                            {"miscBits", root.miscBits.to_ulong()}, {"smokeBombUsed", root.smokeBombUsed},
                            {"monsterTurnIdx", root.monsterTurnIdx}, {"endTurnQueued", root.endTurnQueued},
                            {"turnHasEnded", root.turnHasEnded}, {"skipMonsterTurn", root.skipMonsterTurn},
                            {"intentsHidden", root.intentsHidden},
                            {"haveUsedDiscoveryAction", root.haveUsedDiscoveryAction}}}};
    }

    struct TurnDominance {
        std::string status = "ok";      // ok | capped
        std::int64_t execs = 0;
        std::vector<char> open;         // per root edge: some line hits chance or leaves the turn
        std::vector<char> dominated;    // per root edge
        std::vector<int> ends;          // per root edge: distinct end-of-turn candidates reached
        std::vector<char> material;     // per root edge: dominated, and every candidate materially
        std::int64_t endStates = 0, survivors = 0, groups = 0;
    };

    TurnDominance analyseTurn(const search::SilverSearcher &live, std::int64_t maxExecs, int act) {
        const BattleContext &root = live.rootSearchState();
        const auto &edges = live.rootNode().edges;
        search::SilverSearcher enumerator(root, live.searchContext());
        TurnDominance r;
        r.open.assign(edges.size(), 0);
        r.dominated.assign(edges.size(), 0);
        r.ends.assign(edges.size(), 0);
        r.material.assign(edges.size(), 0);
        std::vector<EndState> states;
        std::unordered_map<std::size_t, std::size_t> stateIndex;   // hashBattleState -> states
        auto record = [&](const BattleContext &bc, int edge) {
            const std::size_t h = search::hashBattleState(bc);
            auto [it, fresh] = stateIndex.emplace(h, states.size());
            if (fresh) states.push_back(endStateOf(bc, act));
            auto &e = states[it->second].edges;
            if (e.empty() || e.back() != edge) e.push_back(edge);
        };
        // Executes `a` on a copy of `from`; false when an RNG stream advanced.
        auto step = [&](const BattleContext &from, const search::Action &a, BattleContext &out) {
            out = from;
            const search::SearchRngState pre = search::captureSearchRng(out);
            search::seedSearchRng(out, search::searchRandomnessBase(out));
            a.execute(out);
            ++r.execs;
            if (search::searchRngCounter(out) != 0) return false;
            search::restoreSearchRng(out, pre);
            return true;
        };
        BattleContext next;
        for (std::size_t ei = 0; ei < edges.size() && r.status == "ok"; ++ei) {
            const int edge = static_cast<int>(ei);
            const auto &first = edges[ei].action;
            if (first.getActionType() == search::ActionType::END_TURN) { record(root, edge); continue; }
            std::vector<BattleContext> stack;
            std::unordered_set<std::size_t> seen;
            if (!step(root, first, next)) { r.open[ei] = 1; continue; }
            seen.insert(search::hashBattleState(next));
            stack.push_back(next);
            while (!stack.empty()) {
                if (r.execs > maxExecs) { r.status = "capped"; break; }
                const BattleContext n = std::move(stack.back());
                stack.pop_back();
                if (n.outcome != Outcome::UNDECIDED) { record(n, edge); continue; }
                if (n.turn != root.turn) { r.open[ei] = 1; continue; }
                const auto acts = enumerator.enumerateActions(n);
                if (acts.empty()) { r.open[ei] = 1; continue; }
                for (const auto &a : acts) {
                    if (a.getActionType() == search::ActionType::END_TURN) {
                        if (n.inputState == InputState::PLAYER_NORMAL) record(n, edge);
                        else r.open[ei] = 1;
                        continue;
                    }
                    if (!step(n, a, next)) { r.open[ei] = 1; continue; }
                    if (seen.insert(search::hashBattleState(next)).second) stack.push_back(next);
                }
            }
        }
        if (r.status != "ok") return r;
        // Dominance within each projection group (terminal states always survive).
        std::unordered_map<Key, std::vector<std::size_t>, KeyHash> groups;
        for (std::size_t i = 0; i < states.size(); ++i)
            if (!states[i].terminal) groups[states[i].proj].push_back(i);
        r.groups = static_cast<std::int64_t>(groups.size());
        for (const auto &[proj, members] : groups) {
            for (std::size_t x : members) {
                for (std::size_t y : members) {
                    if (x == y) continue;
                    if (!covers(states[y], states[x]) || covers(states[x], states[y])) continue;
                    states[x].survivor = false;
                    if (materiallyBetter(states[y], states[x])) { states[x].materiallyDominated = true; break; }
                }
            }
        }
        std::vector<char> reachesSurvivor(edges.size(), 0), reachesImmaterial(edges.size(), 0);
        for (const auto &s : states) {
            ++r.endStates;
            if (s.survivor) ++r.survivors;
            for (int e : s.edges) {
                ++r.ends[e];
                if (s.survivor) reachesSurvivor[e] = 1;
                if (!s.materiallyDominated) reachesImmaterial[e] = 1;
            }
        }
        for (std::size_t ei = 0; ei < edges.size(); ++ei)
        {
            r.dominated[ei] = !r.open[ei] && r.ends[ei] > 0 && !reachesSurvivor[ei];
            r.material[ei] = r.dominated[ei] && !reachesImmaterial[ei];
        }
        return r;
    }

}

void turnDominanceGen(int nSeeds, int sims, int asc, long long seedOffset, const std::string &outPath,
                      long long maxExecs, int maxSnapshots) {
    std::ofstream out(outPath, std::ios::app);
    if (!out) throw std::runtime_error("turndomgen: cannot open " + outPath);
    #pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < nSeeds; ++i) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset) + static_cast<std::uint64_t>(i);
        std::string lines;
        long long roots = 0, skipped = 0, chosenDominated = 0, chosenMaterial = 0, snapshots = 0;
        double enumSec = 0;
        int fight = 0;
        t_realCombatObserver = [&](const GameContext &, const BattleContext &, int,
                                   const std::optional<one_combat::CombatTransitionRecord> &) { ++fight; };
        search::g_nativeSilverRootObserver = [&](const search::NativeSilverRootView &view) {
            if (view.skipped) { ++skipped; return; }
            const auto &s = view.searcher;
            const BattleContext &root = s.rootSearchState();
            const auto &edges = s.rootNode().edges;
            if (edges.empty()) return;
            const auto t0 = std::chrono::steady_clock::now();
            nlohmann::json row = {{"seed", seed}, {"fight", fight + 1}, {"floor", view.live.floorNum},
                                  {"act", view.gc.act}, {"room", roomStrings[static_cast<int>(view.gc.curRoom)]},
                                  {"encounter", monsterEncounterEnumNames[static_cast<int>(view.live.encounter)]},
                                  {"decision", view.decision}, {"turn", root.turn}, {"inputState", static_cast<int>(root.inputState)},
                                  {"hp", root.player.curHp}, {"energy", root.player.energy}, {"handSize", root.cards.cardsInHand},
                                  {"potions", root.potionCount}, {"simulations", view.simulations},
                                  {"inheritedVisits", view.inheritedVisits}, {"gateSafe", gateSafe(root)}};
            const search::Action chosen = s.bestAction();
            int chosenIdx = -1;
            for (std::size_t e = 0; e < edges.size(); ++e) if (edges[e].action == chosen) chosenIdx = static_cast<int>(e);
            row["chosen"] = chosenIdx;
            try {
                const TurnDominance d = analyseTurn(s, maxExecs, view.gc.act);
                row["status"] = d.status;
                row["execs"] = d.execs;
                row["endStates"] = d.endStates; row["survivors"] = d.survivors; row["groups"] = d.groups;
                nlohmann::json es = nlohmann::json::array();
                for (std::size_t e = 0; e < edges.size(); ++e) {
                    const bool hasQ = edges[e].node && edges[e].node->simulationCount > 0;
                    nlohmann::json q = hasQ ? nlohmann::json(edges[e].node->evaluationSum / edges[e].node->simulationCount)
                                            : nlohmann::json(nullptr);
                    es.push_back({edges[e].visitCount, q, d.status == "ok" ? int(d.open[e]) : -1,
                                  d.status == "ok" ? int(d.dominated[e]) : -1, d.status == "ok" ? d.ends[e] : -1});
                }
                row["edges"] = es;
                const bool dom = d.status == "ok" && chosenIdx >= 0 && d.dominated[chosenIdx];
                row["chosenDominated"] = dom;
                row["chosenMaterial"] = dom && d.material[chosenIdx];
                if (dom && d.material[chosenIdx]) ++chosenMaterial;
                int nMaterial = 0;
                for (char m : d.material) nMaterial += m;
                row["materialEdges"] = nMaterial;
                if (dom) {
                    ++chosenDominated;
                    nlohmann::json labels = nlohmann::json::array();
                    for (const auto &e : edges) labels.push_back(actionLabel(e.action, root));
                    row["labels"] = labels;
                    if (snapshots < maxSnapshots) {
                        try { row.update(rootSnapshot(root)); ++snapshots; }
                        catch (const std::exception &ex) { row["stateError"] = ex.what(); }
                    }
                }
            } catch (const std::exception &ex) {
                row["status"] = std::string("error: ") + ex.what();
            }
            enumSec += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            row["enumSec"] = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            lines += row.dump() + '\n';
            ++roots;
        };
        const auto t0 = std::chrono::steady_clock::now();
        nlohmann::json summary = {{"summary", true}, {"seed", seed}};
        try {
            const RunResult r = runFullRunOOC(seed, sims, asc, deployedRestV(), true);
            summary.update({{"won", r.won}, {"floor", r.floor}, {"act", r.act}, {"hpEnd", r.hpEnd},
                            {"fightsLost", r.fightsLost}});
        } catch (const std::exception &e) {
            summary["error"] = e.what();
        }
        search::g_nativeSilverRootObserver = nullptr;
        t_realCombatObserver = nullptr;
        summary.update({{"fights", fight}, {"roots", roots}, {"skippedRoots", skipped},
                        {"chosenDominated", chosenDominated}, {"chosenMaterial", chosenMaterial}, {"enumSec", enumSec},
                        {"sec", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count()}});
        lines += summary.dump() + '\n';
        #pragma omp critical(turn_dominance_out)
        { out << lines; out.flush(); }
    }
}
