#include "az_run_driver.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <functional>
#include <limits>
#include <stdexcept>
#include <unordered_map>

#include "constants/Rooms.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/OocHiddenFuture.h"
#include "sim/search/OocMctsPlanner.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/RunGoal.h"
#include "sim/search/SearchRng.h"

namespace sts::azbench {

    using search::Action;
    using search::AmberTokens;
    using search::AmberTokenType;
    using search::GameAction;

    // STS_AZ_KEY_HOLES=0 restores the old forceKeys behaviour: Smoke Bomb allowed at the act-3 burning elite and the
    // act-3 Secret Portal enterable without the three keys (both end the run keyless, 2026-11-21).
    bool keyHolesClosed() {
        static const bool on = [] {
            const char *v = std::getenv("STS_AZ_KEY_HOLES");
            return !(v && std::strcmp(v, "0") == 0);
        }();
        return on;
    }

    // STS_AZ_KEY_HOLES2=0 restores the forceKeys behaviour of #1158 (2026-11-21, second round): N'loth's Hungry Face
    // may eat the act-3 Sapphire chest, and the act-3 route mask reads an out-of-combat drink's slot as a map x.
    bool keyHoles2Closed() {
        static const bool on = [] {
            const char *v = std::getenv("STS_AZ_KEY_HOLES2");
            return !(v && std::strcmp(v, "0") == 0);
        }();
        return on;
    }

    // N'loth's Hungry Face with its charge left: the next chest opened is empty and offers no Sapphire Key.
    bool hungryFaceCharged(const GameContext &gc) {
        return gc.hasRelic(RelicId::NLOTHS_HUNGRY_FACE) && gc.relics.getRelicValue(RelicId::NLOTHS_HUNGRY_FACE) > 0;
    }

    // forceKeys: the act-3 burning elite with the Emerald Key still missing, the last one of the run (a Smoke Bomb
    // escape there forfeits the Emerald Key and so the Heart; NativeSilverBackend's ADR-0041 rule).
    bool keyEscapeForfeitsEmerald(const GameContext &gc, bool forceKeys) {
        return forceKeys && keyHolesClosed() && gc.keysEnabled && gc.act == 3 && gc.curRoom == Room::ELITE &&
               !gc.hasKey(Key::EMERALD_KEY) && gc.map && gc.map->burningEliteX == gc.curMapNodeX &&
               gc.map->burningEliteY == gc.curMapNodeY;
    }

    namespace {

        double cpuSeconds() {
            timespec ts{};
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
            return static_cast<double>(ts.tv_sec) + 1e-9 * static_cast<double>(ts.tv_nsec);
        }

        float slog(float x) { return std::copysign(std::log1p(std::fabs(x)), x); }

        std::uint64_t mix64(std::uint64_t x) {   // splitmix64 finaliser
            x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ull;
            x ^= x >> 27; x *= 0x94d049bb133111ebull;
            return x ^ (x >> 31);
        }

        // Hash of one state's net input: its live tokens (segment, ids, floats) and its legal actions, i.e.
        // everything packFlat sends for the row.
        std::uint64_t inputHash(const AmberTokens &tk) {
            std::uint64_t h = 0x243f6a8885a308d3ull;
            auto add = [&](std::uint64_t w) { h = mix64(h ^ w) + 0x9e3779b97f4a7c15ull; };
            static_assert(search::kAmberCat == 4 && search::kAmberFloat % 4 == 0 && search::kAmberActFeat == 8);
            for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                add(static_cast<std::uint64_t>(s) << 32 | tk.n[s]);
                for (int i = 0; i < tk.n[s]; ++i) {
                    const auto &t = tk.tok[search::kAmberOff[s] + i];
                    std::uint64_t w;
                    std::memcpy(&w, t.ids.data(), sizeof w);
                    add(w);
                    for (int j = 0; j < search::kAmberFloat; j += 4) {
                        std::memcpy(&w, t.f.data() + j, sizeof w);
                        add(w);
                    }
                }
            }
            add(static_cast<std::uint64_t>(tk.nAct));
            for (int i = 0; i < tk.nAct; ++i) {
                const auto &a = tk.act[i];
                add(static_cast<std::uint64_t>(a.type) | static_cast<std::uint64_t>(a.srcSeg) << 8 |
                    static_cast<std::uint64_t>(a.tgtSeg) << 16 | static_cast<std::uint64_t>(a.srcIdx) << 24 |
                    static_cast<std::uint64_t>(a.tgtIdx) << 32);
                std::uint64_t w;
                std::memcpy(&w, a.f.data(), sizeof w);
                add(w);
                std::memcpy(&w, a.f.data() + 4, sizeof w);
                add(w);
            }
            return h;
        }

        // savescum self-check: fingerprints of a real decision state (RNG states, HP, gold, deck, piles in order,
        // monsters). Two states that the same deterministic steps reached have the same fingerprint.
        struct Fp {
            std::uint64_t h = 0x452821e638d01377ull;
            void add(std::uint64_t w) { h = mix64(h ^ w) + 0x9e3779b97f4a7c15ull; }
            void rng(const Random &r) { add(r.seed0); add(r.seed1); add(static_cast<std::uint32_t>(r.counter)); }
        };
        std::uint64_t stateFingerprint(const BattleContext &bc) {
            Fp f;
            f.add(1);
            for (const Random *r : {&bc.aiRng, &bc.cardRandomRng, &bc.miscRng, &bc.monsterHpRng, &bc.potionRng,
                                    &bc.shuffleRng}) f.rng(*r);
            f.add(static_cast<std::uint64_t>(bc.turn));
            f.add(static_cast<std::uint64_t>(bc.player.curHp) << 32 | static_cast<std::uint32_t>(bc.player.block));
            f.add(static_cast<std::uint64_t>(bc.player.energy));
            const auto &cm = bc.cards;
            f.add(static_cast<std::uint64_t>(cm.cardsInHand));
            for (int i = 0; i < cm.cardsInHand; ++i) f.add(static_cast<std::uint64_t>(cm.hand[i].id));
            f.add(static_cast<std::uint64_t>(cm.drawPile.size()));
            for (int i = 0; i < cm.drawPile.size(); ++i) f.add(static_cast<std::uint64_t>(cm.drawPile[i].id));
            f.add(static_cast<std::uint64_t>(cm.discardPile.size()));
            for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                const auto &m = bc.monsters.arr[i];
                f.add(static_cast<std::uint64_t>(m.id) << 40 | static_cast<std::uint64_t>(static_cast<std::uint32_t>(m.curHp)) << 8);
                f.add(static_cast<std::uint64_t>(m.moveHistory[0]));
            }
            return f.h;
        }
        std::uint64_t stateFingerprint(const GameContext &gc) {
            Fp f;
            f.add(2);
            for (const Random *r : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                                    &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                                    &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng}) f.rng(*r);
            f.add(static_cast<std::uint64_t>(gc.floorNum) << 32 | static_cast<std::uint32_t>(gc.screenState));
            f.add(static_cast<std::uint64_t>(gc.curHp) << 32 | static_cast<std::uint32_t>(gc.maxHp));
            f.add(static_cast<std::uint64_t>(gc.gold));
            f.add(static_cast<std::uint64_t>(gc.curMapNodeX + 16) << 32 | static_cast<std::uint32_t>(gc.curMapNodeY + 16));
            f.add(static_cast<std::uint64_t>(gc.deck.size()));
            for (int i = 0; i < gc.deck.size(); ++i) f.add(static_cast<std::uint64_t>(gc.deck.cards[i].id));
            f.add(gc.relics.relicBits0); f.add(gc.relics.relicBits1); f.add(gc.relics.relicBits2);
            return f.h;
        }

        std::int16_t clampId(int v) { return static_cast<std::int16_t>(std::clamp(v, 1, search::kAmberIdVocab - 1)); }

        constexpr int kMaxMovesPerRun = 50000;   // whole-run stall guard (a normal A20 run takes a few thousand)

        // A win is a Heart kill. The engine also ends a run as a victory after the act 3 boss without the three keys;
        // that run counts as ending on its floor (no Act 4, no win).
        bool heartWin(const GameContext &gc) {
            return gc.outcome == GameOutcome::PLAYER_VICTORY && gc.act == 4;
        }

        // The act 3 boss beaten without the three keys: the engine's victory, not a win here.
        bool keylessVictory(const GameContext &gc) {
            return gc.outcome == GameOutcome::PLAYER_VICTORY && gc.act != 4;
        }

        int outcomeClass(const GameContext &gc) {
            return heartWin(gc) ? 0 : std::clamp(gc.floorNum, 1, kOutcomeClasses - 1);
        }

        // RunConfig::auxFights: the fight starts of an out-of-combat sample on gc, as (slot, encounter, room): the act
        // boss, the act's elites, kAuxHallway hallway fights drawn from the act's strong pool with its weights by an
        // RNG seeded with `seed`. Returns how many it wrote into out.
        struct AuxFight { std::uint8_t slot; MonsterEncounter enc; Room room; };
        int auxFightList(const GameContext &gc, std::uint64_t seed, std::array<AuxFight, 1 + 3 + kAuxHallway> &out) {
            int n = 0;
            if (gc.boss != MonsterEncounter::INVALID) out[n++] = {0, gc.boss, Room::BOSS};
            if (gc.act >= 4) {
                out[n++] = {1, MonsterEncounter::SHIELD_AND_SPEAR, Room::ELITE};
                return n;
            }
            if (gc.act < 1) return n;
            const int a = gc.act - 1;
            for (int k = 0; k < 3; ++k)
                out[n++] = {static_cast<std::uint8_t>(1 + k), MonsterEncounterPool::elites[a][k], Room::ELITE};
            std::mt19937_64 r(seed);
            std::uniform_real_distribution<double> u(0.0, 1.0);
            const int cnt = MonsterEncounterPool::strongCount[a];
            double tot = 0;
            for (int k = 0; k < cnt; ++k) tot += MonsterEncounterPool::strongWeights[a][k];
            for (int h = 0; h < kAuxHallway; ++h) {
                double x = u(r) * tot;
                int k = 0;
                for (; k < cnt - 1; ++k) {
                    x -= MonsterEncounterPool::strongWeights[a][k];
                    if (x < 0) break;
                }
                out[n++] = {4, MonsterEncounterPool::strongEnemies[a][k], Room::MONSTER};
            }
            return n;
        }

        // escapeForfeitsRun is only an enumeration rule here: combatActions drops Smoke Bomb, the net input keeps the
        // flag at 0 (encodeContext), as in every fight the net has been trained on.
        search::SilverSearchContext combatContext(const GameContext &gc, bool forceKeys) {
            search::SilverSearchContext c;
            c.act = gc.act;
            c.actBossRoom = gc.curRoom == Room::BOSS;
            c.eliteRewards = gc.isEliteTriggerCombat();
            c.escapeForfeitsRun = keyEscapeForfeitsEmerald(gc, forceKeys);
            return c;
        }
        search::SilverSearchContext encodeContext(search::SilverSearchContext c) {
            c.escapeForfeitsRun = false;
            return c;
        }

        // Flat layout of one row (packFlat's per-row layout without padding). dict non-null (RunConfig::compactSamples):
        // the tokens go into the run's dictionary *dict (index: content hash -> position; a new dictionary when the
        // row would overflow it) and the sample keeps their positions.
        void flattenInto(const AmberTokens &tk, Sample &s, std::shared_ptr<TokenDict> *dict = nullptr,
                         std::unordered_map<std::uint64_t, std::uint32_t> *index = nullptr) {
            std::array<int, search::kAmberTokenTypes> off{};
            int n = 0;
            for (int t = 0; t < search::kAmberTokenTypes; ++t) { off[t] = n; n += tk.n[t]; }
            if (dict) {
                if (!*dict || (*dict)->size() + static_cast<std::size_t>(n) > TokenDict::kMax) {
                    *dict = std::make_shared<TokenDict>();
                    index->clear();
                }
                TokenDict &d = **dict;
                s.tokIdx.resize(n);
                int pos = 0;
                for (int t = 0; t < search::kAmberTokenTypes; ++t) {
                    for (int i = 0; i < tk.n[t]; ++i, ++pos) {
                        const auto &k = tk.tok[search::kAmberOff[t] + i];
                        std::uint64_t h = 0x9e3779b97f4a7c15ull * static_cast<std::uint64_t>(t + 1);
                        auto mixIn = [&h](std::uint64_t w) {
                            h ^= w + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
                            h *= 0xbf58476d1ce4e5b9ull;
                            h ^= h >> 31;
                        };
                        for (int c = 0; c < search::kAmberCat; ++c) mixIn(static_cast<std::uint16_t>(k.ids[c]));
                        for (int c = 0; c < search::kAmberFloat; ++c) mixIn(k.f[c]);
                        // Open addressing on the hash: a colliding entry with other content moves on to h + 1.
                        for (;; ++h) {
                            const auto it = index->find(h);
                            if (it == index->end()) {
                                const auto at = static_cast<std::uint32_t>(d.size());
                                d.tokType.push_back(static_cast<std::int8_t>(t));
                                d.ids.insert(d.ids.end(), k.ids.begin(), k.ids.end());
                                d.f.insert(d.f.end(), k.f.begin(), k.f.end());
                                index->emplace(h, at);
                                s.tokIdx[pos] = static_cast<std::uint16_t>(at);
                                break;
                            }
                            const std::size_t q = it->second;
                            if (d.tokType[q] == static_cast<std::int8_t>(t) &&
                                std::memcmp(&d.ids[q * search::kAmberCat], k.ids.data(), sizeof(k.ids)) == 0 &&
                                std::memcmp(&d.f[q * search::kAmberFloat], k.f.data(), sizeof(k.f)) == 0) {
                                s.tokIdx[pos] = static_cast<std::uint16_t>(q);
                                break;
                            }
                        }
                    }
                }
                s.dict = *dict;
            } else {
                s.tokType.resize(n);
                s.ids.resize(static_cast<std::size_t>(n) * search::kAmberCat);
                s.f.resize(static_cast<std::size_t>(n) * search::kAmberFloat);
                int pos = 0;
                for (int t = 0; t < search::kAmberTokenTypes; ++t) {
                    for (int i = 0; i < tk.n[t]; ++i, ++pos) {
                        const auto &k = tk.tok[search::kAmberOff[t] + i];
                        s.tokType[pos] = static_cast<std::int8_t>(t);
                        std::memcpy(&s.ids[static_cast<std::size_t>(pos) * search::kAmberCat], k.ids.data(), sizeof(k.ids));
                        std::memcpy(&s.f[static_cast<std::size_t>(pos) * search::kAmberFloat], k.f.data(), sizeof(k.f));
                    }
                }
            }
            const int a = tk.nAct;
            s.aType.resize(a);
            s.aSrc.resize(a);
            s.aTgt.resize(a);
            s.aF.resize(static_cast<std::size_t>(a) * search::kAmberActFeat);
            for (int j = 0; j < a; ++j) {
                const auto &x = tk.act[j];
                s.aType[j] = x.type;
                s.aSrc[j] = x.srcSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.srcSeg] + x.srcIdx);
                s.aTgt[j] = x.tgtSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.tgtSeg] + x.tgtIdx);
                std::memcpy(&s.aF[static_cast<std::size_t>(j) * search::kAmberActFeat], x.f.data(), sizeof(x.f));
            }
        }

    }

    namespace {
        // Points the thread's combat knowledge observer at one tracker for a scope (null outside: search steps
        // never reach a tracker).
        class ObserverScope {
        public:
            explicit ObserverScope(search::CombatKnowledgeObserver *o) : prev_(search::g_combatKnowledgeObserver) {
                search::g_combatKnowledgeObserver = o;
            }
            ~ObserverScope() { search::g_combatKnowledgeObserver = prev_; }
            ObserverScope(const ObserverScope &) = delete;
            ObserverScope &operator=(const ObserverScope &) = delete;
        private:
            search::CombatKnowledgeObserver *prev_;
        };
    }

    void initObservedBattle(const GameContext &gc, BattleContext &bc, search::CombatKnowledgeState &knowledge) {
        knowledge = search::CombatKnowledgeState();
        bc = BattleContext();
        knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
        knowledge.initializeFromLiveBattle(bc);
        knowledge.beginCombatInitialization();
        {
            ObserverScope o(&knowledge);
            bc.init(gc);
        }
        knowledge.synchronizeAfterCombatInitialization(bc);
    }

    void executeObserved(BattleContext &bc, std::uint32_t bits, search::CombatKnowledgeState &knowledge) {
        ObserverScope o(&knowledge);
        Action(bits).execute(bc);
    }

    std::string publicCombatRoot(const BattleContext &live, search::CombatKnowledgeState &knowledge,
                                 BattleContext &root) {
        knowledge.reconcilePublicDrawPileCardinality(live);
        if (knowledge.consistencyFailureCount != 0) return "knowledge tracker lost consistency";
        ObserverScope o(nullptr);
        return search::nativeSilverSearchRoot(live, knowledge, root);
    }

    void stubEncodeGame(const GameContext &gc, const std::vector<GameAction> &actions, AmberTokens &out) {
        out.clear();
        auto &run = out.at(AmberTokenType::RUN, 0);
        run.ids = {clampId(900 + static_cast<int>(gc.screenState)), 0, 0, 0};
        run.f[0] = search::amberHalf(static_cast<float>(gc.floorNum) / 50.f);
        run.f[1] = search::amberHalf(static_cast<float>(gc.act) / 4.f);
        run.f[2] = search::amberHalf(slog(static_cast<float>(gc.gold)));
        out.n[static_cast<int>(AmberTokenType::RUN)] = 1;
        auto &pl = out.at(AmberTokenType::PLAYER, 0);
        pl.f[0] = search::amberHalf(slog(static_cast<float>(gc.curHp)));
        pl.f[1] = search::amberHalf(slog(static_cast<float>(gc.maxHp)));
        pl.f[2] = search::amberHalf(static_cast<float>(gc.curHp) / static_cast<float>(std::max(1, gc.maxHp)));
        out.n[static_cast<int>(AmberTokenType::PLAYER)] = 1;
        const int capC = search::kAmberCap[static_cast<int>(AmberTokenType::CARD)];
        int nc = 0;
        for (int i = 0; i < gc.deck.size(); ++i) {
            if (nc >= capC) { ++out.cut; break; }
            const auto &c = gc.deck.cards[i];
            auto &k = out.at(AmberTokenType::CARD, nc++);
            k.ids = {clampId(search::kAmberCardBase + static_cast<int>(c.getId()) - 1), 0, 0, 0};
            k.f[0] = search::amberHalf(c.isUpgraded() ? 1.f : 0.f);
        }
        out.n[static_cast<int>(AmberTokenType::CARD)] = static_cast<std::uint8_t>(nc);
        const int capR = search::kAmberCap[static_cast<int>(AmberTokenType::RELIC)];
        int nr = 0;
        for (const auto &r : gc.relics.relics) {
            if (nr >= capR) { ++out.cut; break; }
            out.at(AmberTokenType::RELIC, nr++).ids = {clampId(search::kAmberRelicBase + static_cast<int>(r.id)), 0, 0, 0};
        }
        out.n[static_cast<int>(AmberTokenType::RELIC)] = static_cast<std::uint8_t>(nr);
        int np = 0;
        for (int i = 0; i < std::min(gc.potionCapacity, 5); ++i)
            if (gc.potions[i] != Potion::EMPTY_POTION_SLOT)
                out.at(AmberTokenType::POTION, np++).ids = {
                    clampId(search::kAmberPotionBase + static_cast<int>(gc.potions[i]) - 2), 0, 0, 0};
        out.n[static_cast<int>(AmberTokenType::POTION)] = static_cast<std::uint8_t>(np);
        const int capO = search::kAmberCap[static_cast<int>(AmberTokenType::OPTION)];
        int no = 0;
        for (const auto &a : actions) {
            if (out.nAct >= search::kAmberMaxActions) { ++out.cut; continue; }
            auto &e = out.act[out.nAct++];
            e.type = 10;
            e.srcSeg = e.tgtSeg = search::kAmberNoSeg;
            e.f[0] = search::amberHalf(static_cast<float>(a.bits & 0xff));
            e.f[1] = search::amberHalf(static_cast<float>((a.bits >> 8) & 0xff));
            e.f[2] = search::amberHalf(static_cast<float>((a.bits >> 16) & 0xff));
            e.f[3] = search::amberHalf(static_cast<float>(a.bits >> 24));
            if (no < capO) {
                auto &k = out.at(AmberTokenType::OPTION, no);
                k.ids = {clampId(900 + static_cast<int>(gc.screenState)), 0, 0, 0};
                k.f = {};
                for (int b = 0; b < 4; ++b) k.f[b] = e.f[b];
                e.srcSeg = static_cast<std::uint8_t>(AmberTokenType::OPTION);
                e.srcIdx = static_cast<std::uint8_t>(no++);
            }
        }
        out.n[static_cast<int>(AmberTokenType::OPTION)] = static_cast<std::uint8_t>(no);
    }

    void completedQValues(int k, const float *logit, const std::int32_t *n, const double *w, double value,
                          bool rescale, double *q) {
        if (!rescale) {
            for (int i = 0; i < k; ++i) q[i] = n[i] ? w[i] / n[i] : value;
            return;
        }
        double mxLogit = -1e300;
        for (int i = 0; i < k; ++i) mxLogit = std::max(mxLogit, static_cast<double>(logit[i]));
        double z = 0;
        for (int i = 0; i < k; ++i) z += std::exp(logit[i] - mxLogit);
        double sumN = 0, piQ = 0, piVisited = 0;
        for (int i = 0; i < k; ++i) {
            if (!n[i]) continue;
            const double pi = std::exp(logit[i] - mxLogit) / z;
            sumN += n[i];
            piQ += pi * (w[i] / n[i]);
            piVisited += pi;
        }
        const double vMix = sumN > 0 ? (value + sumN * piQ / std::max(piVisited, 1e-30)) / (1.0 + sumN) : value;
        double lo = 1e300, hi = -1e300;
        for (int i = 0; i < k; ++i) {
            q[i] = n[i] ? w[i] / n[i] : vMix;
            lo = std::min(lo, q[i]);
            hi = std::max(hi, q[i]);
        }
        const double range = std::max(hi - lo, 1e-8);
        for (int i = 0; i < k; ++i) q[i] = (q[i] - lo) / range;
    }

    // --- search state ---------------------------------------------------------------------------------------------

    struct Edge {
        std::uint32_t bits = 0;          // search::Action (combat node) or search::GameAction (out-of-combat node)
        float logit = 0;
        std::int32_t n = 0;
        std::uint32_t realBits = 0;      // savescum combat node: the action mapped to the real fight (request)
        double w = 0;
        int child = -1;                  // decision child (deterministic combat edge)
        bool chance = false, tried = false;
        bool realOk = false;             // savescum combat node: realBits is a valid action of the real fight
        std::uint8_t vn = 0;             // parallelNodes: virtual losses (simulations in flight through this edge)
        std::uint64_t base = 0;          // chance: randomness base
        std::vector<int> outcomes;
        std::vector<std::int32_t> outcomeN;
    };

    struct RunDriver::Node {
        Node() = default;
        Node(Node &&) noexcept = default;
        Node &operator=(Node &&) noexcept = default;
        bool combat = false;
        // A slot holds only its current kind's state (2026-11-19 RAM): bc for a combat node (null under savescum,
        // whose public view is rebuilt from real + kn when needed), gc for an out-of-combat node, real + kn for a
        // savescum combat node. Each is kept allocated while the slot stays that kind and released when it changes.
        std::unique_ptr<BattleContext> bc;   // combat node (not savescum)
        search::SilverSearchContext ctx;     // combat node: its fight
        std::unique_ptr<GameContext> gc;     // out-of-combat node (kept allocated across pool reuse)
        std::shared_ptr<const GameContext> outer;   // combat node, crossCombat: the game state at its fight's start
        std::vector<Edge> edges;
        bool evaluated = false, terminal = false, boundary = false;
        bool inFlight = false;               // its net evaluation is requested and not yet handled
        float value = 0;
        std::int32_t n = 0;
        double w = 0;
        std::vector<float> dist;             // searchEmaLambda > 0: outcome distribution of the node's value [57]
        // searchEmaHp (RunConfig): the node's floor and the HP with which its path left each floor from the search
        // root's on (passed[i] = floor rootFloor + i); what its value says about the HP at the end of the root's
        // floor (hpHot >= 0: the one-hot of that class, else the distribution hpd [256]) and about E[HP_f] / 255 of
        // every floor from the root's on (hpfv [56], utility AMBER).
        int nfloor = 0, hpHot = -1;
        std::vector<std::int16_t> passed;
        std::vector<float> hpd, hpfv;
        // savescum combat node: the real fight (bc is its public view) and its knowledge tracker (kept allocated
        // across pool reuse; valid while hasReal).
        bool hasReal = false;
        std::unique_ptr<BattleContext> real;
        std::unique_ptr<search::CombatKnowledgeState> kn;
        std::uint64_t realStamp = 0;         // savescum: setReal call that wrote real + kn (public-view scratch key)
        std::uint64_t rbase = 0;             // savescum combat node: searchRandomnessBase of its public view
    };

    struct PathStep { int node; int edge; int outcome; };

    // One net evaluation of a run in flight: the simulation's path to the requested node, the node's encoded input
    // and, once answered, its result. A run has one in flight at a time (slot 0), or with RunConfig::parallelNodes a
    // wave of them (slots 0 .. nFlights - 1).
    struct Flight {
        std::vector<PathStep> path;
        int node = -1;
        bool combat = false;
        float maxHp = 1;
        int floor = 0;                       // floor of the requested node
        AmberTokens tokens;
        std::vector<float> resLogits;
        float resF = 0, resEhp = 0;
        std::uint32_t resVersion = 0;        // weights version of the result (submit)
        std::uint64_t hash = 0;              // evalCache: hash of the input
        bool hit = false;                    // answered by the cache
        std::array<float, kFloors> resHpf{};   // utility AMBER: E[HP_f] / 255
        std::array<float, kOutcomeClasses> resDist{};   // searchEmaLambda > 0: outcome softmax
        std::vector<float> resHpd;           // searchEmaHp: floor HP softmax [256]
    };

    // Ticket of a request: worker << 26 | flight slot << 16 | run (with slot 0 the pre-parallelNodes ticket).
    constexpr int kTicketRunBits = 16, kTicketSlotBits = 10;
    constexpr int kMaxFlights = 1 << kTicketSlotBits, kMaxWorkers = 1 << (32 - kTicketRunBits - kTicketSlotBits);
    inline std::uint32_t ticketRun(std::uint32_t t) { return t & ((1u << kTicketRunBits) - 1); }
    inline std::uint32_t ticketSlot(std::uint32_t t) { return (t >> kTicketRunBits) & (kMaxFlights - 1); }
    inline std::uint32_t ticketWorker(std::uint32_t t) { return t >> (kTicketRunBits + kTicketSlotBits); }

    struct RunDriver::Run {
        Run() = default;
        Run(Run &&) noexcept = default;
        Run &operator=(Run &&) noexcept = default;
        bool active = false;
        std::uint64_t seed = 0;
        GameContext gc;
        BattleContext bc;
        std::unique_ptr<search::CombatKnowledgeState> knowledge = std::make_unique<search::CombatKnowledgeState>();
        bool inBattle = false;
        bool forceKeys = false;              // RunConfig::forceKeys state this run started with
        bool savescum = false;               // RunConfig::savescum state this run started with
        bool expectValid = false;            // savescum: the next real decision state must have fingerprint expectFp
        std::uint64_t expectFp = 0;
        std::shared_ptr<const GameContext> fightOuter;   // crossCombat: g.gc at the real fight's start
        std::shared_ptr<const GameContext> heartStart;   // heartArms: the game state at the Heart fight's start
        int heartJob = -1;                   // heartArms: the current play of the Heart fight (-1 = not there yet)
        int heartSearched = 0;               // heartArms: searched moves of the current play
        std::vector<int> rootKeys;           // pick-rate item bucket per root action (-1 = none), OOC roots
        std::vector<std::int8_t> rootClass;  // item class per root action (Stats::forcedByClass order)
        std::vector<char> rootUnder;         // exploreAmber: root action is an under-target item (after warm-up)
        std::unordered_map<int, double> gapMin;   // exploreAmber: this run's smallest gap per item
        std::vector<int> pickedKeys;         // exploreAmber: items played in this run (each once)
        int asc = 20;                        // this run's ascension
        bool heartLog = false;               // RunConfig::heartLogRate: this run's Heart fight is recorded (if any)
        HeartRunLog hlog;                    // ... its record so far
        RunProgress progress;                // this run's progress counters (added to its ascension at the end)
        search::SilverSearchContext ctx;
        int fightMoves = 0, moves = 0, floor = 0;
        std::vector<Node> pool;
        int poolUsed = 0;
        int budget = 0, spent = 0, candidates = 0;
        bool full = false, keep = false;
        std::vector<int> cand;
        std::vector<double> gumbel;
        std::vector<int> phaseQueue;
        int phasesLeft = 0;
        // Net evaluations in flight (Flight): slots 0 .. nFlights - 1 of fl are this wave's, `waiting` of them not
        // yet answered. Slots are allocated on first use and kept. fl changes only while nothing of the run is queued.
        std::vector<std::unique_ptr<Flight>> fl;
        int nFlights = 0, waiting = 0;
        // Evaluation cache (RunConfig::evalCache): input hash -> result, all of weights version cacheVersion; emptied
        // at the start of each run, on a weights change and when full.
        struct CacheEntry { float F = 0, ehp = 0; int nAct = 0; std::vector<float> logits, hpf, dist, hpd; };   // hpf: utility AMBER; dist: searchEmaLambda > 0; hpd: searchEmaHp
        std::unordered_map<std::uint64_t, CacheEntry> cache;
        std::uint32_t cacheVersion = 0;
        std::vector<double> rootDist;          // searchEmaLambda > 0: sum of the backed-up distributions at the root
        std::vector<std::uint16_t> moveDist;   // ... search result of each chain move of the run [M][57], float16
        // searchEmaHp: the sums of the backed-up floor HP distributions and
        // per-floor values at the root; the floor HP search results of the current floor's chain moves [m][256]
        // (floorChain0 = the run's chain moves before this floor); the per-floor search results of the run's chain
        // moves (float16; move m holds floors moveHpfFloor[m] .. 56).
        std::vector<double> rootHpd, rootHpf;
        std::vector<float> floorHpd;
        int floorChain0 = 0;
        std::vector<std::uint16_t> moveHpf;
        std::vector<std::uint8_t> moveHpfFloor;
        std::array<std::int16_t, kFloors + 1> floorHp{};   // utility AMBER: HP at the end of floor f (-1 = not yet)
        std::vector<Sample> pending;
        std::size_t floorStart = 0;          // first pending sample of the current floor
        Sample cur;                          // the current move's sample (root tokens), if kept
        // RunConfig::compactSamples: this run's token dictionary (shared with its samples) and its content index.
        std::shared_ptr<TokenDict> dict;
        std::unordered_map<std::uint64_t, std::uint32_t> dictIndex;
    };

    struct RunDriver::Worker {
        std::vector<Run> runs;
        std::mutex im;
        std::vector<int> inbox;              // answered flights: slot << 16 | run
        std::vector<int> hits;               // flights the cache answered (handled like results), same coding
        std::mt19937_64 rng;
        RunStats st;
        mutable std::mutex sm;
        RunStats published;
    };

    namespace {

        // Mean value of an edge. parallelNodes: a simulation in flight through it (vn) is a virtual loss, a visit of
        // value 0 (the lowest utility) until its answer is backed up; vn is 0 whenever the root is read.
        double q01(const Edge &e, double fallback) { return e.n + e.vn ? e.w / (e.n + e.vn) : fallback; }

        // Completed Q of every edge of node into q (completedQValues in az_run_driver.h).
        void completedQ(const RunDriver::Node &node, const RunConfig &cfg, std::vector<double> &q) {
            const int k = static_cast<int>(node.edges.size());
            q.resize(k);
            if (!cfg.qRescale) {
                for (int i = 0; i < k; ++i) q[i] = q01(node.edges[i], node.value);
                return;
            }
            thread_local std::vector<float> logit;
            thread_local std::vector<std::int32_t> n;
            thread_local std::vector<double> w;
            logit.resize(k);
            n.resize(k);
            w.resize(k);
            for (int i = 0; i < k; ++i) { logit[i] = node.edges[i].logit; n[i] = node.edges[i].n + node.edges[i].vn; w[i] = node.edges[i].w; }
            completedQValues(k, logit.data(), n.data(), w.data(), node.value, true, q.data());
        }

        int maxVisits(const RunDriver::Node &node) {
            int maxN = 0;
            for (const auto &e : node.edges) maxN = std::max(maxN, static_cast<int>(e.n) + e.vn);
            return maxN;
        }

        int selectNonRoot(const RunDriver::Node &node, const RunConfig &cfg) {
            const int k = static_cast<int>(node.edges.size());
            // parallelNodes: a simulation in flight is a virtual loss on its edges (vn): a visit in every count here
            // (also sigma's) and, through q01 / completedQ, a value of 0.
            double sumN = 0;
            for (const auto &e : node.edges) sumN += e.n + e.vn;
            const double sigma = (cfg.cVisit + maxVisits(node)) * cfg.cScale;
            thread_local std::vector<double> s, q;
            completedQ(node, cfg, q);
            s.resize(k);
            double mx = -1e300;
            for (int i = 0; i < k; ++i) {
                s[i] = node.edges[i].logit + sigma * q[i];
                mx = std::max(mx, s[i]);
            }
            double z = 0;
            for (int i = 0; i < k; ++i) { s[i] = std::exp(s[i] - mx); z += s[i]; }
            int best = 0;
            double bestScore = -1e300;
            for (int i = 0; i < k; ++i) {
                const double sc = s[i] / z - (node.edges[i].n + node.edges[i].vn) / (1.0 + sumN);
                if (sc > bestScore) { bestScore = sc; best = i; }
            }
            return best;
        }

        // Root score g + logit + sigma(completed Q) of edge e; q from completedQ(root), sigma from the root's visits.
        double rootScore(const RunDriver::Run &g, const RunDriver::Node &root, int e, double sigma,
                         const std::vector<double> &q) {
            return g.gumbel[e] + root.edges[e].logit + sigma * q[e];
        }

        // Scaled utility (F + w H) / (1 + w) of a state the run cannot continue from. alive: the run ended without
        // a death (a Heart kill, or a keyless act 3 victory).
        float terminalUtility(bool win, bool alive, int floor, int hp, int maxHp, double w, const RunConfig &cfg,
                              bool stateCombat, bool rootCombat) {
            const double F = win ? 1.0 : std::clamp(floor, 1, kOutcomeClasses - 1) / 57.0;
            if (isAmber2(cfg.utility)) {   // AMBER2: by the state's kind, AMBER2_ROOT: by the search root's: OOC P(win) + 0.25 H; combat F + 0.5 H
                return static_cast<float>(amber2Value(cfg.utility == Utility::AMBER2_ROOT ? rootCombat : stateCombat, F, win ? 1.0 : 0.0, amberTerminalH(win, alive, floor, hp)));
            }
            double H;
            if (usesAmberH(cfg.utility)) H = amberTerminalH(win, alive, floor, hp);
            else H = (win || (alive && cfg.keylessHp)) ? std::clamp(static_cast<double>(hp) / std::max(1, maxHp), 0.0, 1.0) : 0.0;
            return static_cast<float>((F + w * H) / (1.0 + w));
        }

        float terminalUtility(const GameContext &gc, double w, const RunConfig &cfg, bool stateCombat, bool rootCombat) {
            return terminalUtility(heartWin(gc), heartWin(gc) || keylessVictory(gc), gc.floorNum, gc.curHp, gc.maxHp,
                                   w, cfg, stateCombat, rootCombat);
        }

        // searchEmaLambda > 0: a terminal node's distribution is the one-hot of its outcome class.
        float halfToFloat(std::uint16_t h) {
            const std::uint32_t sign = static_cast<std::uint32_t>(h & 0x8000u) << 16;
            const std::uint32_t exp = (h >> 10) & 0x1fu, man = h & 0x3ffu;
            float f;
            if (exp == 0) f = std::ldexp(static_cast<float>(man), -24);             // zero / subnormal
            else if (exp == 31) f = man ? std::numeric_limits<float>::quiet_NaN() : std::numeric_limits<float>::infinity();
            else f = std::ldexp(static_cast<float>(man | 0x400u), static_cast<int>(exp) - 25);
            return sign ? -f : f;
        }

        void setOneHot(RunDriver::Node &n, int cls) {
            n.dist.assign(kOutcomeClasses, 0.f);
            n.dist[std::clamp(cls, 0, kOutcomeClasses - 1)] = 1.f;
        }

    }

    int appendSingingBowlActions(const GameContext &gc, std::vector<GameAction> &v) {
        if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState != ScreenState::REWARDS
                || !gc.hasRelic(RelicId::SINGING_BOWL))
            return 0;
        const int n = gc.info.rewardsContainer.cardRewardCount;
        for (int g = 0; g < n; ++g) v.emplace_back(GameAction::RewardsActionType::CARD, g, 5);
        return n;
    }

    int appendPotionReplacementDiscards(const GameContext &gc, std::vector<GameAction> &v) {
        if (gc.outcome != GameOutcome::UNDECIDED || gc.potionCount < gc.potionCapacity
                || gc.hasRelic(RelicId::SOZU))
            return 0;
        bool potionOnOffer = false;
        if (gc.screenState == ScreenState::REWARDS) {
            potionOnOffer = gc.info.rewardsContainer.potionCount > 0;
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            for (int i = 0; i < 3; ++i) {
                const int price = gc.info.shop.potionPrice(i);
                potionOnOffer |= price != -1 && gc.gold >= price;
            }
        }
        if (!potionOnOffer) return 0;
        int added = 0;
        for (int slot = 0; slot < gc.potionCapacity && slot < 5; ++slot) {
            const Potion p = gc.potions[slot];
            if (p == Potion::EMPTY_POTION_SLOT || p == Potion::INVALID) continue;
            bool duplicate = false;
            for (int j = 0; j < slot; ++j) duplicate |= gc.potions[j] == p;
            if (duplicate) continue;   // discarding either copy gives the same state
            const GameAction discard(0xC0000000u | static_cast<unsigned>(slot));
            if (!discard.isValidAction(gc)) continue;
            v.push_back(discard);
            ++added;
        }
        return added;
    }

    int appendOocPotionDrinks(const GameContext &gc, std::vector<GameAction> &v) {
        if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState == ScreenState::BATTLE
                || gc.screenState == ScreenState::CARD_SELECT)
            return 0;
        int added = 0;
        for (int slot = 0; slot < gc.potionCapacity && slot < 5; ++slot) {
            const Potion p = gc.potions[slot];
            const bool helps = p == Potion::FRUIT_JUICE || (p == Potion::BLOOD_POTION && gc.curHp < gc.maxHp);
            if (!helps) continue;
            bool duplicate = false;
            for (int j = 0; j < slot; ++j) duplicate |= gc.potions[j] == p;
            if (duplicate) continue;
            const GameAction drink(0x80000000u | static_cast<unsigned>(slot));
            if (!drink.isValidAction(gc)) continue;   // e.g. not on We Meet Again's screen
            v.push_back(drink);
            ++added;
        }
        return added;
    }

    int canonicalOocSelectActions(const GameContext &gc, std::vector<GameAction> &v) {
        if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState != ScreenState::CARD_SELECT) return 0;
        const auto &cards = gc.info.toSelectCards;
        auto bottled = [&](int i) { const int d = cards[i].deckIdx; return d >= 0 && gc.deck.isCardBottled(d); };
        auto firstEqual = [&](int i) {   // the first selectable index whose card equals card i
            for (int j = 0; j < i; ++j)
                if (cards[j].card == cards[i].card && bottled(j) == bottled(i)) return j;
            return i;
        };
        const std::size_t before = v.size();
        v.erase(std::remove_if(v.begin(), v.end(), [&](const GameAction &a) {
            const int i = static_cast<int>(a.getIdx1());
            return a.bits == static_cast<std::uint32_t>(i) && i >= 0 && i < static_cast<int>(cards.size()) &&
                   firstEqual(i) != i;
        }), v.end());
        return static_cast<int>(before - v.size());
    }

    int forcedRewardPotionActions(const GameContext &gc, std::vector<GameAction> &v) {
        using RT = GameAction::RewardsActionType;
        if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState != ScreenState::REWARDS || v.size() <= 1) return -1;
        const auto &r = gc.info.rewardsContainer;
        if (r.potionCount <= 0 || gc.potionCapacity - gc.potionCount < r.potionCount ||
                gc.hasRelic(RelicId::SOZU)) return -1;
        const GameAction take(RT::POTION, 0);
        if (std::none_of(v.begin(), v.end(), [&](const GameAction &x) { return x.bits == take.bits; })) return -1;
        v.assign(1, take);
        return 1;
    }

    int keyBackstopActions(const GameContext &gc, std::vector<GameAction> &v) {
        const std::size_t before = v.size();
        if (const auto key = search::heartKeyAction(gc, true)) {
            if (std::any_of(v.begin(), v.end(), [&](const GameAction &a) { return a.bits == key->bits; })) {
                v.assign(1, *key);
                if (before <= 1) return -1;
                if (gc.screenState == ScreenState::REST_ROOM) return 1;
                if (gc.screenState == ScreenState::MAP_SCREEN) return 2;
                return gc.screenState == ScreenState::REWARDS && gc.info.rewardsContainer.emeraldKey ? 2 : 0;
            }
        }
        // The act-3 Secret Portal jumps to the boss past the treasure row, the last campfire and the burning elite: with
        // a key still missing it is a keyless victory at best, so only its leave option stays (STS_AZ_KEY_HOLES=0: open).
        const bool portalBlocked = keyHolesClosed() && gc.screenState == ScreenState::EVENT_SCREEN &&
                                   gc.curEvent == Event::SECRET_PORTAL && gc.keysEnabled && gc.act == 3 &&
                                   gc.outcome == GameOutcome::UNDECIDED &&
                                   !(gc.hasKey(Key::RUBY_KEY) && gc.hasKey(Key::EMERALD_KEY) && gc.hasKey(Key::SAPPHIRE_KEY));
        // Sapphire against N'loth's Hungry Face (STS_AZ_KEY_HOLES2): a charged face empties the next chest opened, and
        // the Sapphire waits for the act-3 treasure row. So with the Sapphire missing, (a) a chest before that row is
        // opened (Cursed Key or not) to spend the charge, and (b) Face Trader's trade (a random face, maybe the hungry
        // one) is not offered after the act-2 treasure row, from where no sure chest is left before the act-3 one.
        const bool sapphireOpen = keyHoles2Closed() && gc.keysEnabled && gc.outcome == GameOutcome::UNDECIDED &&
                                  !gc.hasKey(Key::SAPPHIRE_KEY);
        if (sapphireOpen && gc.screenState == ScreenState::TREASURE_ROOM && hungryFaceCharged(gc) && before > 1 &&
                std::any_of(v.begin(), v.end(), [](const GameAction &a) { return a.bits == GameAction(0).bits; })) {
            v.assign(1, GameAction(0));
            return 0;
        }
        const bool faceTradeBlocked = sapphireOpen && gc.screenState == ScreenState::EVENT_SCREEN &&
                                      gc.curEvent == Event::FACE_TRADER && gc.act == 2 && gc.curMapNodeY >= 8 &&
                                      !gc.hasRelic(RelicId::NLOTHS_HUNGRY_FACE);
        // Out-of-combat drinks (0x80000000 | slot) are no map moves: the Emerald route mask leaves them alone.
        const bool drinksFree = keyHoles2Closed();
        std::vector<GameAction> kept;
        kept.reserve(before);
        for (const auto &a : v) {
            if (drinksFree && a.isPotionAction()) { kept.push_back(a); continue; }
            if (portalBlocked && a.bits == GameAction(0).bits) continue;
            if (faceTradeBlocked && a.bits == GameAction(1).bits) continue;
            if (search::heartKeyActionAllowed(gc, true, a)) kept.push_back(a);
        }
        if (kept.empty() || kept.size() == before) return -1;
        v.swap(kept);
        return 3;
    }

    namespace {
        // Philipp's reviewed reward relics (2026-10-07; ooc_tree_rules.cpp reviewedRewardRelic): left to the net.
        bool reviewedRewardRelic(RelicId id) {
            switch (id) {
                case RelicId::BOTTLED_FLAME: case RelicId::BOTTLED_LIGHTNING: case RelicId::BOTTLED_TORNADO:
                case RelicId::DEAD_BRANCH: case RelicId::TUNGSTEN_ROD: case RelicId::UNCEASING_TOP:
                case RelicId::JUZU_BRACELET: return true;
                default: return false;
            }
        }
        // Act on the card reward or the potions of the same screen (Deck::obtain: eggs upgrade, Ceramic Fish +9 gold).
        bool relicBeforeCard(RelicId id) {
            return id == RelicId::CERAMIC_FISH || id == RelicId::MOLTEN_EGG || id == RelicId::TOXIC_EGG ||
                   id == RelicId::FROZEN_EGG || id == RelicId::POTION_BELT;
        }
        // Upgrade random deck cards on pickup: the new card can be one of them.
        bool relicAfterCard(RelicId id) { return id == RelicId::WHETSTONE || id == RelicId::WAR_PAINT; }

        // Index of the forced relic to take next on gc's REWARDS screen (relic-first ones before the rest; card-first
        // ones only when afterCard), -1 when none.
        int forcedRewardRelic(const GameContext &gc, bool afterCard) {
            using RT = GameAction::RewardsActionType;
            const auto &r = gc.info.rewardsContainer;
            int pick = -1;
            for (int i = 0; i < r.relicCount; ++i) {
                const RelicId id = r.relics[i];
                if (reviewedRewardRelic(id) || (r.sapphireKey && i == r.relicCount - 1)) continue;
                if (relicAfterCard(id) && !afterCard) continue;
                if (!GameAction(RT::RELIC, i).isValidAction(gc)) continue;
                if (relicBeforeCard(id)) return i;
                if (pick < 0) pick = i;
            }
            return pick;
        }
    }

    int forcedRewardActions(const GameContext &gc, std::vector<GameAction> &v) {
        using RT = GameAction::RewardsActionType;
        auto keepOnly = [&](const GameAction &a, int rule) {
            if (std::none_of(v.begin(), v.end(), [&](const GameAction &x) { return x.bits == a.bits; })) return -1;
            const bool removed = v.size() > 1;
            v.assign(1, a);
            return removed ? rule : -1;
        };
        if (gc.outcome != GameOutcome::UNDECIDED) return -1;
        if (gc.screenState == ScreenState::TREASURE_ROOM)
            return gc.relics.has(RelicId::CURSED_KEY) ? -1 : keepOnly(GameAction(0), 0);
        if (gc.screenState != ScreenState::REWARDS) return -1;
        const auto &r = gc.info.rewardsContainer;
        const bool cardOpen = r.cardRewardCount > 0;
        const int i = forcedRewardRelic(gc, !cardOpen);
        if (i >= 0) return keepOnly(GameAction(RT::RELIC, i), 1);
        if (!cardOpen) return -1;
        // A card-first relic waits for the card decision (taking a card, or leaving: forcedRewardBeforeLeave).
        const std::size_t before = v.size();
        v.erase(std::remove_if(v.begin(), v.end(), [&](const GameAction &a) {
            if (a.getRewardsActionType() != RT::RELIC || a.getIdx1() >= r.relicCount) return false;
            const RelicId id = r.relics[a.getIdx1()];
            return relicAfterCard(id) && !reviewedRewardRelic(id) &&
                   !(r.sapphireKey && a.getIdx1() == r.relicCount - 1);
        }), v.end());
        return v.size() < before ? 2 : -1;
    }

    std::optional<GameAction> forcedRewardBeforeLeave(const GameContext &gc) {
        using RT = GameAction::RewardsActionType;
        if (gc.outcome != GameOutcome::UNDECIDED || gc.screenState != ScreenState::REWARDS) return std::nullopt;
        const int i = forcedRewardRelic(gc, true);
        if (i < 0) return std::nullopt;
        return GameAction(RT::RELIC, i);
    }

    double amberExploreC(const AmberGapHist &h, double need, double T) {
        if (static_cast<double>(h.natural) >= need) return 0.0;
        std::vector<std::pair<double, double>> bins;   // (exp(-m_b / T), runs) of the non-empty bins
        for (int b = 0; b < AmberGapHist::kBins; ++b)
            if (h.n[b]) bins.emplace_back(std::exp(-(b + 0.5) * AmberGapHist::kBin / T), h.n[b]);
        auto picked = [&](double c) {
            double x = static_cast<double>(h.natural);
            for (const auto &[e, n] : bins) x += n * std::min(1.0, c * e);
            return x;
        };
        double lo = -60.0, hi = 60.0;   // log c; at e^60 every logged gap (< 40) is picked with probability 1
        if (picked(std::exp(hi)) < need) return std::numeric_limits<double>::infinity();
        for (int it = 0; it < 100; ++it) {
            const double mid = 0.5 * (lo + hi);
            (picked(std::exp(mid)) < need ? lo : hi) = mid;
        }
        return std::exp(hi);
    }

    double RunDriver::exploreItemC(int key, std::int64_t games) {
        std::lock_guard<std::mutex> l(exploreM_);
        ExploreItem &it = exploreItems_[key];
        if (it.stamp != games) {   // recomputed once per new finished run
            const double base = cfg_.explorePerOffer ? static_cast<double>(it.hist.runs) : static_cast<double>(games);
            it.c = amberExploreC(it.hist, cfg_.pickTarget * base, cfg_.exploreT);
            it.stamp = games;
        }
        return it.c;
    }

    namespace {
        constexpr char kExploreMagic[8] = {'S', 'T', 'S', 'E', 'X', 'P', 'L', '1'};
        template <class T> void putRaw(std::string &s, T v) { s.append(reinterpret_cast<const char *>(&v), sizeof(T)); }
        template <class T> T getRaw(const std::string &s, std::size_t &pos) {
            if (pos + sizeof(T) > s.size()) throw std::invalid_argument("run driver: explore state is cut short");
            T v;
            std::memcpy(&v, s.data() + pos, sizeof(T));
            pos += sizeof(T);
            return v;
        }
    }

    std::string RunDriver::exploreState() {
        std::string s(kExploreMagic, sizeof(kExploreMagic));
        putRaw<std::int32_t>(s, cfg_.exploreCleanKeys ? 1 : 0);
        putRaw<std::int64_t>(s, exploreGames());
        std::uint32_t nb = 0;
        const std::size_t nbAt = s.size();
        putRaw<std::uint32_t>(s, 0);
        for (int k = 0; k < kPickBuckets; ++k) {
            const std::uint32_t p = picks_[k].load(std::memory_order_relaxed), o = offers_[k].load(std::memory_order_relaxed);
            if (p == 0 && o == 0) continue;
            putRaw<std::int32_t>(s, k); putRaw<std::uint32_t>(s, p); putRaw<std::uint32_t>(s, o);
            ++nb;
        }
        std::memcpy(&s[nbAt], &nb, sizeof(nb));
        std::lock_guard<std::mutex> l(exploreM_);
        putRaw<std::uint32_t>(s, static_cast<std::uint32_t>(exploreItems_.size()));
        for (const auto &[key, it] : exploreItems_) {
            putRaw<std::int32_t>(s, key); putRaw<std::int64_t>(s, it.hist.natural); putRaw<std::int64_t>(s, it.hist.runs);
            std::uint32_t nz = 0;
            for (std::uint32_t n : it.hist.n) nz += n != 0;
            putRaw<std::uint32_t>(s, nz);
            for (int b = 0; b < AmberGapHist::kBins; ++b)
                if (it.hist.n[b]) { putRaw<std::uint16_t>(s, static_cast<std::uint16_t>(b)); putRaw<std::uint32_t>(s, it.hist.n[b]); }
        }
        return s;
    }

    void RunDriver::setExploreState(const std::string &s) {
        if (!threads_.empty()) throw std::logic_error("run driver: setExploreState after start");
        if (s.size() < sizeof(kExploreMagic) || std::memcmp(s.data(), kExploreMagic, sizeof(kExploreMagic)) != 0)
            throw std::invalid_argument("run driver: not an explore state");
        std::size_t pos = sizeof(kExploreMagic);
        if ((getRaw<std::int32_t>(s, pos) != 0) != cfg_.exploreCleanKeys)
            throw std::invalid_argument("run driver: explore state is of the other item rule (exploreCleanKeys)");
        const std::int64_t runs = getRaw<std::int64_t>(s, pos);
        if (runs < 0) throw std::invalid_argument("run driver: explore state runs < 0");
        auto bucket = [&](std::int32_t k) {
            if (k < 0 || k >= kPickBuckets) throw std::invalid_argument("run driver: explore state bucket out of range");
            return k;
        };
        std::vector<std::array<std::uint32_t, 3>> counts(getRaw<std::uint32_t>(s, pos));
        for (auto &c : counts) {
            c[0] = static_cast<std::uint32_t>(bucket(getRaw<std::int32_t>(s, pos)));
            c[1] = getRaw<std::uint32_t>(s, pos); c[2] = getRaw<std::uint32_t>(s, pos);
        }
        std::unordered_map<int, ExploreItem> items;
        const std::uint32_t ni = getRaw<std::uint32_t>(s, pos);
        for (std::uint32_t i = 0; i < ni; ++i) {
            ExploreItem &it = items[bucket(getRaw<std::int32_t>(s, pos))];
            it.hist.natural = getRaw<std::int64_t>(s, pos); it.hist.runs = getRaw<std::int64_t>(s, pos);
            const std::uint32_t nz = getRaw<std::uint32_t>(s, pos);
            for (std::uint32_t j = 0; j < nz; ++j) {
                const std::uint16_t b = getRaw<std::uint16_t>(s, pos);
                if (b >= AmberGapHist::kBins) throw std::invalid_argument("run driver: explore state bin out of range");
                it.hist.n[b] = getRaw<std::uint32_t>(s, pos);
            }
        }
        if (pos != s.size()) throw std::invalid_argument("run driver: explore state has trailing bytes");
        for (int k = 0; k < kPickBuckets; ++k) { picks_[k].store(0); offers_[k].store(0); }
        for (const auto &c : counts) { picks_[c[0]].store(c[1]); offers_[c[0]].store(c[2]); }
        std::lock_guard<std::mutex> l(exploreM_);
        exploreItems_ = std::move(items);
        exploreRunsBase_.store(runs - runsDone_.load());
    }

    RunDriver::RunDriver(RunConfig cfg) : cfg_(cfg) {
        if (cfg_.ascension < 0 || cfg_.ascension >= kAscensions) throw std::invalid_argument("run driver: ascension 0..20");
        ascension_.store(cfg_.ascension);
        setForceKeys(cfg_.forceKeys);
        savescum_.store(cfg_.savescum);
        picks_.reset(new std::atomic<std::uint32_t>[kPickBuckets]);
        for (int i = 0; i < kPickBuckets; ++i) picks_[i].store(0);
        offers_.reset(new std::atomic<std::uint32_t>[kPickBuckets]);
        for (int i = 0; i < kPickBuckets; ++i) offers_[i].store(0);
        if (cfg_.explorePerOffer && !cfg_.exploreAmber)
            throw std::invalid_argument("run driver: explorePerOffer needs exploreAmber");
        if (cfg_.exploreCleanKeys && !cfg_.exploreAmber && !(cfg_.exploreC > 0))
            throw std::invalid_argument("run driver: exploreCleanKeys needs exploreAmber or exploreC");
        if ((cfg_.exploreGapSearch || cfg_.exploreDeckOnly) && !cfg_.exploreAmber)
            throw std::invalid_argument("run driver: exploreGapSearch / exploreDeckOnly need exploreAmber");
        if (!cfg_.encodeCombat) cfg_.encodeCombat = search::amberEncodeCombat;
        if (!cfg_.encodeGame) cfg_.encodeGame = search::amberEncodeGame;
        if (cfg_.utility != Utility::FLOOR_HP && cfg_.utility != Utility::AMBER && !isAmber2(cfg_.utility))
            throw std::invalid_argument("run driver: utility 0 (floor HP), 1 (Amber) or 2 (Amber, later)");
        if (!(cfg_.searchEmaLambda >= 0 && cfg_.searchEmaLambda < 1))
            throw std::invalid_argument("run driver: searchEmaLambda in [0, 1)");
        if (cfg_.searchEmaHp && !(cfg_.searchEmaLambda > 0))
            throw std::invalid_argument("run driver: searchEmaHp needs searchEmaLambda > 0");
        if (cfg_.searchEmaHp && !(cfg_.chanceOnReveal || cfg_.crossCombat || cfg_.simHelp))
            throw std::invalid_argument("run driver: searchEmaHp needs Amber's search rules (chanceOnReveal, crossCombat or simHelp)");
        if (cfg_.gamesPerWorker > 0xffff) throw std::invalid_argument("run driver: at most 65535 runs per worker");
        if (cfg_.workers > kMaxWorkers) throw std::invalid_argument("run driver: at most 64 workers");
        if (cfg_.parallelNodes < 0 || cfg_.parallelNodes > 255)
            throw std::invalid_argument("run driver: parallelNodes 0 (off) .. 255");
        if (cfg_.exploreAmber && cfg_.exploreC > 0)
            throw std::invalid_argument("run driver: exploreAmber and exploreC are exclusive");
        if (cfg_.exploreAmber && !(cfg_.exploreT > 0 && cfg_.pickTarget > 0))
            throw std::invalid_argument("run driver: exploreAmber needs exploreT > 0 and pickTarget > 0");
        int maxSims = std::max(cfg_.fullSims, cfg_.fastSims);
        int maxCand = std::max(cfg_.fullCandidates, cfg_.fastCandidates);
        if (cfg_.heartReps < 1) throw std::invalid_argument("run driver: heartReps >= 1");
        for (const auto &a : cfg_.heartArms) {
            if (a.fullSims < 1 || a.fastSims < 1 || a.fullCandidates < 1 || a.fastCandidates < 1 ||
                !(a.fullProb >= 0 && a.fullProb <= 1))
                throw std::invalid_argument("run driver: heart arm needs sims, candidates >= 1 and fullProb in [0, 1]");
            maxSims = std::max({maxSims, a.fullSims, a.fastSims});
            maxCand = std::max({maxCand, a.fullCandidates, a.fastCandidates});
        }
        for (int w = 0; w < cfg_.workers; ++w) {
            auto wk = std::make_unique<Worker>();
            wk->rng.seed(cfg_.searchSeed * 1000003u + static_cast<std::uint64_t>(w));
            wk->runs.resize(cfg_.gamesPerWorker);
            for (auto &r : wk->runs)
                // One node per simulation; a halving phase rounds its per-candidate count up to 1, so a search
                // can overshoot its budget by at most one simulation per candidate (exploreAmber: under-target
                // items are extra candidates, at most one per encoded action).
                r.pool.reserve(static_cast<std::size_t>(maxSims + maxCand
                                                        + (cfg_.exploreAmber ? search::kAmberMaxActions : 0)) + 2);
            workers_.push_back(std::move(wk));
        }
    }

    RunDriver::~RunDriver() { stop(); }

    void RunDriver::setForceKeys(bool on) {
        if (on) {   // the backstops of the spec are the ADR-0063 defaults; STS_KEY_* variants would change them
            const auto &r = search::heartKeyRules();
            if (r.sapphire != search::HeartKeyRules::Sapphire::POLICY || r.ruby != search::HeartKeyRules::Ruby::POLICY ||
                r.emerald != search::HeartKeyRules::Emerald::MASK)
                throw std::invalid_argument("run driver: forceKeys needs the ADR-0063 key rules (unset STS_KEY_*)");
        }
        forceKeys_.store(on);
    }

    void RunDriver::start() {
        stop_ = false;
        for (int w = 0; w < cfg_.workers; ++w) threads_.emplace_back(&RunDriver::workerLoop, this, w);
    }

    void RunDriver::stop() {
        stop_ = true;
        qcv_.notify_all();
        for (auto &t : threads_) t.join();
        threads_.clear();
    }

    std::uint64_t RunDriver::nextSeed() {
        const std::int64_t i = seedsUsed_++;
        if (cfg_.maxRuns >= 0 && i >= cfg_.maxRuns) return std::numeric_limits<std::uint64_t>::max();
        return cfg_.seedBase + static_cast<std::uint64_t>(i);
    }

    RunStats RunDriver::stats() const {
        RunStats s;
        for (const auto &w : workers_) {
            std::lock_guard<std::mutex> l(w->sm);
            const RunStats &p = w->published;
            s.evals += p.evals; s.moves += p.moves; s.searchedMoves += p.searchedMoves;
            s.runsStarted += p.runsStarted; s.runsDone += p.runsDone; s.wins += p.wins; s.floorsSum += p.floorsSum;
            s.stalls += p.stalls; s.terminalLeaves += p.terminalLeaves; s.encodeCut += p.encodeCut; s.encodeCutOoc += p.encodeCutOoc;
            s.unsupported += p.unsupported; s.knowledgeFailures += p.knowledgeFailures; s.invalidActions += p.invalidActions; s.samplesDone += p.samplesDone; s.samplesPending += p.samplesPending;
            for (int k = 0; k < kOutcomeClasses; ++k) s.outcomes[k] += p.outcomes[k];
            for (int k = 0; k < kAscensions; ++k) {
                s.runsDoneAsc[k] += p.runsDoneAsc[k]; s.winsAsc[k] += p.winsAsc[k]; s.floorsSumAsc[k] += p.floorsSumAsc[k];
                s.progressAsc[k] += p.progressAsc[k];
            }
            s.oocRoots += p.oocRoots; s.exploreRoots += p.exploreRoots; s.forcedPicks += p.forcedPicks;
            s.exploreAttempts += p.exploreAttempts; s.exploreCZero += p.exploreCZero; s.exploreCInf += p.exploreCInf;
            s.exploreNatural += p.exploreNatural; s.exploreNaturalUnplayed += p.exploreNaturalUnplayed;
            s.cacheHits += p.cacheHits;
            s.auxFights += p.auxFights;
            s.waves += p.waves; s.waveFlights += p.waveFlights; s.simCollisions += p.simCollisions;
            for (int k = 0; k < 2; ++k) {
                s.oocSearched[k] += p.oocSearched[k]; s.oocNotBestQ[k] += p.oocNotBestQ[k];
                s.oocSpreadN[k] += p.oocSpreadN[k]; s.oocSpreadSum[k] += p.oocSpreadSum[k];
            }
            s.oocEdgeKinds[0] += p.oocEdgeKinds[0]; s.oocEdgeKinds[1] += p.oocEdgeKinds[1];
            s.treeFightStarts += p.treeFightStarts; s.treeFightExits += p.treeFightExits; s.autoGold += p.autoGold;
            s.savescumRuns += p.savescumRuns; s.savescumChecks += p.savescumChecks; s.savescumMismatches += p.savescumMismatches;
            for (int k = 0; k < 3; ++k) s.forcedKeys[k] += p.forcedKeys[k];
            for (int k = 0; k < 8; ++k) {
                s.exploreAttemptsByClass[k] += p.exploreAttemptsByClass[k];
                s.forcedByClass[k] += p.forcedByClass[k];
            }
            s.keyRouteMasked += p.keyRouteMasked;
            s.forcedRewards[0] += p.forcedRewards[0]; s.forcedRewards[1] += p.forcedRewards[1];
            s.rewardRelicDeferred += p.rewardRelicDeferred; s.rewardRelicOnLeave += p.rewardRelicOnLeave;
            s.oocCanonScreens += p.oocCanonScreens; s.oocCanonRemoved += p.oocCanonRemoved;
            s.forcedPotions += p.forcedPotions;
            if (p.heartHpMin >= 0 && (s.heartHpMin < 0 || p.heartHpMin < s.heartHpMin)) s.heartHpMin = p.heartHpMin;
            s.memPoolNodes += p.memPoolNodes; s.memPoolGc += p.memPoolGc; s.memPoolReal += p.memPoolReal;
            s.memPoolOuter += p.memPoolOuter; s.memEdgeCap += p.memEdgeCap; s.memPoolBc += p.memPoolBc;
            s.memPendingCap += p.memPendingCap; s.memMoveDistCap += p.memMoveDistCap;
            s.memCacheEntries += p.memCacheEntries;
            s.memFlights += p.memFlights;
            s.stepCpu += p.stepCpu; s.encodeCpu += p.encodeCpu; s.searchCpu += p.searchCpu;
        }
        s.batches = batches_.load();
        s.batchRows = batchRows_.load();
        s.packSeconds = 1e-9 * static_cast<double>(packNs_.load());
        {
            std::lock_guard<std::mutex> l(sampleM_);
            s.memDone = static_cast<std::int64_t>(done_.size());
        }
        return s;
    }

    void RunDriver::takeSamples(int maxSamples, std::vector<Sample> &out) {
        std::lock_guard<std::mutex> l(sampleM_);
        const int n = std::min<int>(maxSamples, static_cast<int>(done_.size()));
        for (int i = 0; i < n; ++i) {
            out.push_back(std::move(done_.front()));
            done_.pop_front();
        }
        // A finished run's samples enter done_ together (endRun): finish the last run, so a chunk never splits one
        // (the EMA value labels of selfplay.py --value-ema-halflife need whole runs).
        while (!out.empty() && !done_.empty() && done_.front().run == out.back().run) {
            out.push_back(std::move(done_.front()));
            done_.pop_front();
        }
    }

    void RunDriver::workerLoop(int wi) {
        Worker &wk = *workers_[wi];
        const RunConfig &cfg = cfg_;
        std::vector<std::uint32_t> outbox;
        std::vector<int> ready;
        std::uniform_real_distribution<double> U(0.0, 1.0);
        std::unique_ptr<search::SilverSearcher> enumerator;
        std::vector<Action> cacts;
        std::vector<GameAction> gacts;
        double lastPublish = cpuSeconds();
        double lastMem = lastPublish;
        const char *trimEnv = std::getenv("STS_AZ_POOL_TRIM");
        const bool poolTrim = !(trimEnv && std::strcmp(trimEnv, "0") == 0);
        const std::size_t poolKeep = static_cast<std::size_t>(std::max(cfg.fullSims, cfg.fastSims) +
                                                              std::max(cfg.fullCandidates, cfg.fastCandidates)) + 2;
        // Node edge lists (2026-11-19 memory creep): a reused slot's vector keeps the largest capacity it ever had, so
        // over hours every slot ratchets up to the largest action list it met (jemalloc heap profile: the growing
        // allocation is Node::edges in request). A list now much smaller than its capacity gets an exact-size
        // vector. STS_AZ_EDGE_SHRINK=0 restores the old behaviour.
        const char *shrinkEnv = std::getenv("STS_AZ_EDGE_SHRINK");
        const bool edgeShrink = !(shrinkEnv && std::strcmp(shrinkEnv, "0") == 0);
        auto sizeEdges = [edgeShrink](std::vector<Edge> &edges, std::size_t n) {
            if (edgeShrink && edges.capacity() > 2 * n + 16) std::vector<Edge>(n).swap(edges);
            else edges.resize(n);
        };
        auto memGauges = [&] {
            RunStats &st = wk.st;
            st.memPoolNodes = st.memPoolGc = st.memPoolReal = st.memPoolOuter = st.memEdgeCap = st.memPoolBc = 0;
            st.memPendingCap = st.memMoveDistCap = st.memCacheEntries = st.memFlights = 0;
            for (const Run &g : wk.runs) {
                st.memPoolNodes += static_cast<std::int64_t>(g.pool.size());
                for (const Node &n : g.pool) {
                    st.memPoolGc += n.gc != nullptr;
                    st.memPoolBc += n.bc != nullptr;
                    st.memPoolReal += n.real != nullptr;
                    st.memPoolOuter += n.outer != nullptr;
                    st.memEdgeCap += static_cast<std::int64_t>(n.edges.capacity());
                }
                st.memPendingCap += static_cast<std::int64_t>(g.pending.capacity());
                st.memMoveDistCap += static_cast<std::int64_t>(g.moveDist.capacity());
                st.memCacheEntries += static_cast<std::int64_t>(g.cache.size());
                st.memFlights += static_cast<std::int64_t>(g.fl.size());
            }
        };

        std::unique_ptr<search::SilverSearcher> noEscapeEnumerator;   // ctx.escapeForfeitsRun: without Smoke Bomb
        auto combatActions = [&](const BattleContext &bc, const search::SilverSearchContext &ctx)
                -> const std::vector<Action> & {
            if (ctx.escapeForfeitsRun) {
                if (!noEscapeEnumerator) {
                    search::SilverSearchContext c;
                    c.escapeForfeitsRun = true;
                    noEscapeEnumerator = std::make_unique<search::SilverSearcher>(bc, c);
                }
                cacts = noEscapeEnumerator->enumerateActions(bc);
                return cacts;
            }
            if (!enumerator) enumerator = std::make_unique<search::SilverSearcher>(bc, search::SilverSearchContext{});
            cacts = enumerator->enumerateActions(bc);
            return cacts;
        };

        // Legal out-of-combat actions; simHelp bans buying Prismatic Shard (Amber Eye's simulator); forceKeys (the
        // run's state) applies the key backstops (keyBackstopActions; its result in *keyRule when given).
        // forceRewards: then the forced chest / relic choices (forcedRewardActions; its result in *rewardRule);
        // forcePotions: then the reward potion pickup (forcedRewardPotionActions, *potionRule); oocCanon: last, the
        // duplicate card selections (canonicalOocSelectActions, the number removed in *canonRemoved).
        // Singing Bowl actions (appendSingingBowlActions) come first, so a forced relic restricts them too;
        // STS_AZ_SINGING_BOWL=0 restores the old action list.
        const char *bowlEnv = std::getenv("STS_AZ_SINGING_BOWL");
        const bool singingBowl = !(bowlEnv && std::strcmp(bowlEnv, "0") == 0);
        // Out-of-combat potion actions: discards that make room for an offered potion and Fruit Juice / Blood Potion
        // drinks (appendPotionReplacementDiscards, appendOocPotionDrinks), also before the forced rules;
        // STS_AZ_OOC_POTIONS=0 restores the old list.
        const char *oocPotionEnv = std::getenv("STS_AZ_OOC_POTIONS");
        const bool oocPotions = !(oocPotionEnv && std::strcmp(oocPotionEnv, "0") == 0);
        auto oocActions = [&](const GameContext &gc, bool forceKeys, int *keyRule = nullptr,
                              int *rewardRule = nullptr, int *potionRule = nullptr,
                              int *canonRemoved = nullptr) -> std::vector<GameAction> {
            auto v = GameAction::getAllActionsInState(gc);
            if (singingBowl) appendSingingBowlActions(gc, v);
            if (oocPotions) {
                appendPotionReplacementDiscards(gc, v);
                appendOocPotionDrinks(gc, v);
            }
            if (cfg.simHelp)
                v.erase(std::remove_if(v.begin(), v.end(), [&](const GameAction &a) {
                    return !search::isSupportedAutonomousOocAction(gc, a);
                }), v.end());
            const int rule = forceKeys ? keyBackstopActions(gc, v) : -1;
            if (keyRule) *keyRule = rule;
            const int rr = cfg.forceRewards ? forcedRewardActions(gc, v) : -1;
            if (rewardRule) *rewardRule = rr;
            const int pr = cfg.forcePotions ? forcedRewardPotionActions(gc, v) : -1;
            if (potionRule) *potionRule = pr;
            if (cfg.oocCanon) {
                const int removed = canonicalOocSelectActions(gc, v);
                if (canonRemoved) *canonRemoved = removed;
            }
            return v;
        };
        // forceRewards: leaving a REWARDS screen (SKIP) first takes the card-first relics held back during the card
        // decision. Applies `bits` to gc (a search copy); false when a forced relic left the screen (its own selection
        // screen): the leave is dropped, the rewards come back after it. `taken` counts the relics taken.
        auto execOoc = [&](GameContext &gc, std::uint32_t bits, int *taken = nullptr) {
            const GameAction a(bits);
            if (cfg.forceRewards && gc.screenState == ScreenState::REWARDS &&
                    a.getRewardsActionType() == GameAction::RewardsActionType::SKIP) {
                while (const auto f = forcedRewardBeforeLeave(gc)) {
                    f->execute(gc);
                    if (taken) ++*taken;
                    if (gc.screenState != ScreenState::REWARDS) return false;
                }
            }
            a.execute(gc);
            return true;
        };
        // simHelp: Amber Eye's simulator takes gold from rewards automatically.
        auto goldToTake = [&](const GameContext &gc) {
            return cfg.simHelp && gc.outcome == GameOutcome::UNDECIDED && gc.screenState == ScreenState::REWARDS &&
                   gc.info.rewardsContainer.goldRewardCount > 0;
        };
        const std::uint32_t takeGoldBits = GameAction(GameAction::RewardsActionType::GOLD, 0).bits;

        auto newNode = [&](Run &g) -> int {
            if (g.poolUsed == static_cast<int>(g.pool.size())) {
                if (g.pool.size() == g.pool.capacity()) throw std::logic_error("run driver: node pool overflow");
                g.pool.emplace_back();
            }
            Node &n = g.pool[g.poolUsed];
            n.edges.clear();
            n.outer.reset();
            n.evaluated = n.terminal = n.boundary = false;
            n.value = 0;
            n.n = 0;
            n.w = 0;
            n.dist.clear();
            n.hpHot = -1;
            n.passed.clear();
            n.hasReal = false;
            n.inFlight = false;
            return g.poolUsed++;
        };
        auto setGc = [](Node &n, GameContext &&gc) {
            n.combat = false;
            n.bc.reset();
            n.real.reset();
            n.kn.reset();
            n.hasReal = false;
            if (n.gc) *n.gc = std::move(gc);
            else n.gc = std::make_unique<GameContext>(std::move(gc));
        };
        // A combat node's own fight (not savescum), allocated on first use; the slot's other states are released.
        auto useBc = [](Node &n) -> BattleContext & {
            n.gc.reset();
            n.real.reset();
            n.kn.reset();
            n.hasReal = false;
            if (!n.bc) n.bc = std::make_unique<BattleContext>();
            return *n.bc;
        };
        // savescum: a combat node holds the real fight and its tracker; their public view (net input, action list) is
        // rebuilt when needed into pubScratch, which keeps the last one built (setReal is followed by the node's
        // request). False when the view cannot be built.
        BattleContext pubScratch;
        const Node *pubNode = nullptr;
        std::uint64_t pubStamp = 0, realStamps = 0;
        auto publicView = [&](const Node &n) -> const BattleContext & {
            if (pubNode != &n || pubStamp != n.realStamp) {
                publicCombatRoot(*n.real, *n.kn, pubScratch);
                pubNode = &n;
                pubStamp = n.realStamp;
            }
            return pubScratch;
        };
        auto setReal = [&](Node &n, const BattleContext &real, const search::CombatKnowledgeState &kn) {
            n.bc.reset();
            n.gc.reset();
            if (n.real) *n.real = real;
            else n.real = std::make_unique<BattleContext>(real);
            if (n.kn) *n.kn = kn;
            else n.kn = std::make_unique<search::CombatKnowledgeState>(kn);
            n.hasReal = true;
            n.realStamp = ++realStamps;
            const bool ok = publicCombatRoot(*n.real, *n.kn, pubScratch).empty();
            pubNode = &n;
            pubStamp = n.realStamp;
            if (ok) n.rbase = search::searchRandomnessBase(pubScratch);
            return ok;
        };

        // The run's next free flight slot (allocated on first use).
        auto newFlight = [&](Run &g) -> Flight & {
            if (g.nFlights >= kMaxFlights) throw std::logic_error("run driver: too many evaluations in flight");
            if (g.nFlights == static_cast<int>(g.fl.size())) g.fl.push_back(std::make_unique<Flight>());
            Flight &f = *g.fl[g.nFlights];
            f.path.clear();
            return f;
        };

        // Request a net evaluation of node ni for the flight fl, the run's newest (newFlight; its path is set by the
        // caller): enumerates the node's actions, encodes it, queues it.
        auto request = [&](Run &g, int gi, int ni, Flight &fl) {
            const int slot = g.nFlights++;
            ++g.waiting;
            Node &node = g.pool[ni];
            node.inFlight = true;
            const double t0 = cpuSeconds();
            if (node.combat) {
                const BattleContext &view = node.hasReal ? publicView(node) : *node.bc;
                const auto &acts = combatActions(view, node.ctx);
                sizeEdges(node.edges, acts.size());
                for (std::size_t k = 0; k < acts.size(); ++k) node.edges[k] = Edge{acts[k].bits};
                if (node.hasReal) {   // the edges' actions in the real fight's indexing (translated as the real run)
                    for (std::size_t k = 0; k < acts.size(); ++k) {
                        const Action a = search::SilverSearcher::translateAction(acts[k], view, *node.real);
                        node.edges[k].realBits = a.bits;
                        node.edges[k].realOk = a.isValidAction(*node.real);
                    }
                }
                const double t1 = cpuSeconds();
                cfg.encodeCombat(view, encodeContext(node.ctx), acts, fl.tokens);
                if (cfg.mergeCards) search::amberMergeCards(fl.tokens);
                wk.st.stepCpu += t1 - t0;
                wk.st.encodeCpu += cpuSeconds() - t1;
                fl.combat = true;
                fl.maxHp = static_cast<float>(std::max<int>(1, view.player.maxHp));
                fl.floor = view.floorNum;
            } else {
                gacts = oocActions(*node.gc, g.forceKeys);
                sizeEdges(node.edges, gacts.size());
                for (std::size_t k = 0; k < gacts.size(); ++k) node.edges[k] = Edge{gacts[k].bits};
                const double t1 = cpuSeconds();
                cfg.encodeGame(*node.gc, gacts, fl.tokens);
                if (cfg.enemyTokens) search::amberAppendEncounterTokens(*node.gc, fl.tokens);
                if (cfg.mergeCards) search::amberMergeCards(fl.tokens);
                if (ni == 0 && (cfg.exploreC > 0 || cfg.exploreAmber)) {
                    // Pick-rate items of the root's actions: hash of the source token's ids.
                    g.rootKeys.assign(gacts.size(), -1);
                    g.rootClass.assign(gacts.size(), 7);
                    const auto screen = node.gc->screenState;
                    for (int k = 0; k < fl.tokens.nAct; ++k) {
                        const auto &a = fl.tokens.act[k];
                        const auto t = static_cast<search::AmberActionType>(a.type);
                        if ((t != search::AmberActionType::CHOOSE_CARD && t != search::AmberActionType::CHOOSE_OPTION)
                            || a.srcSeg == search::kAmberNoSeg) continue;
                        // Item class (Stats::forcedByClass order): a CARD token is a card reward / offer, or on a
                        // card-select screen a deck edit; an OPTION by its kind one-hot (f 12-28, AmberGameEncoder.cpp
                        // OptKind). exploreDeckOnly keeps the acquisitions only: cards, relics, potions.
                        const auto seg = static_cast<AmberTokenType>(a.srcSeg);
                        std::int8_t cls = 7;
                        if (seg == AmberTokenType::CARD) {
                            cls = screen == ScreenState::CARD_SELECT ? 1 : 0;
                        } else if (seg == AmberTokenType::OPTION) {
                            const auto &ot = fl.tokens.at(seg, a.srcIdx);
                            int kind = -1;
                            for (int c = 12; c <= 28; ++c) if (ot.f[c]) { kind = c - 12; break; }
                            // REWARD_GOLD 0, REWARD_CARD 1, REWARD_RELIC 2, REWARD_POTION 3, keys 4-5, SINGING_BOWL 6,
                            // SHOP_CARD 7, SHOP_RELIC 8, SHOP_POTION 9, SHOP_REMOVE 10, BOSS_RELIC 11, REST 12,
                            // NEOW 13, EVENT 14, MATCH_SLOT 15, CHEST 16
                            switch (kind) {
                                case 1: case 7: cls = 0; break;
                                case 10: cls = 1; break;
                                case 2: case 8: case 11: cls = 2; break;
                                case 3: case 9: cls = 3; break;
                                case 14: case 15: cls = 4; break;
                                case 12: cls = 5; break;
                                default: cls = 6; break;
                            }
                        }
                        if (cfg.exploreDeckOnly && cls != 0 && cls != 2 && cls != 3) continue;
                        if (k < static_cast<int>(g.rootClass.size())) g.rootClass[k] = cls;
                        const auto &tok = fl.tokens.at(static_cast<AmberTokenType>(a.srcSeg), a.srcIdx);
                        // exploreItemHash (az_run_driver.h): the first rule, or exploreCleanKeys.
                        const std::uint64_t h = exploreItemHash(static_cast<int>(a.type), tok, seg == AmberTokenType::OPTION,
                                                                cfg.exploreCleanKeys);
                        g.rootKeys[k] = static_cast<int>(h & (kPickBuckets - 1));
                    }
                }
                wk.st.stepCpu += t1 - t0;
                wk.st.encodeCpu += cpuSeconds() - t1;
                fl.combat = false;
                fl.maxHp = static_cast<float>(std::max(1, node.gc->maxHp));
                fl.floor = node.gc->floorNum;
            }
            (node.combat ? wk.st.encodeCut : wk.st.encodeCutOoc) += fl.tokens.cut;
            fl.node = ni;
            fl.hit = false;
            if (cfg.evalCache) {
                const std::uint32_t v = weightsVersion_.load(std::memory_order_acquire);
                if (g.cacheVersion != v) { g.cache.clear(); g.cacheVersion = v; }
                fl.hash = inputHash(fl.tokens);
                const auto it = g.cache.find(fl.hash);
                if (it != g.cache.end() && it->second.nAct == fl.tokens.nAct) {
                    // Answered as a result would be, in the worker loop's next round (no recursion into advance).
                    fl.resLogits = it->second.logits;
                    fl.resF = it->second.F;
                    fl.resEhp = it->second.ehp;
                    if (!it->second.hpf.empty()) std::copy(it->second.hpf.begin(), it->second.hpf.end(), fl.resHpf.begin());
                    if (!it->second.dist.empty()) std::copy(it->second.dist.begin(), it->second.dist.end(), fl.resDist.begin());
                    if (!it->second.hpd.empty()) fl.resHpd = it->second.hpd;
                    fl.hit = true;
                    ++wk.st.cacheHits;
                    wk.hits.push_back(slot << 16 | gi);
                    return;
                }
            }
            outbox.push_back(static_cast<std::uint32_t>(wi) << (kTicketRunBits + kTicketSlotBits) |
                             static_cast<std::uint32_t>(slot) << kTicketRunBits | static_cast<std::uint32_t>(gi));
        };

        const bool emaOn = cfg.searchEmaLambda > 0;
        const bool hpOn = cfg.searchEmaHp;                    // floor HP distribution targets from the search
        const bool hpfOn = hpOn && usesAmberH(cfg.utility);   // ... and per-floor HP targets
        auto hpClass = [](int hp) { return std::clamp(hp, 0, kHpClasses - 1); };
        // searchEmaHp: the HP entries of a run-ending node. Death (alive false): HP 0 on its floor and after; a
        // keyless victory: hp on its floor, 0 after; a Heart kill (win): hp on its floor and after (as endRun's
        // labels). Floors the path left before keep their real HP.
        auto setHpEnd = [&](Run &g, Node &cn, bool win, bool alive, int hp) {
            if (!hpOn) return;
            const int rf = g.pool[0].nfloor, h = alive ? hpClass(hp) : 0;
            cn.hpd.clear();
            cn.hpHot = cn.nfloor > rf && !cn.passed.empty() ? hpClass(cn.passed[0]) : h;
            if (!hpfOn) return;
            cn.hpfv.assign(kFloors, 0.f);
            for (int f = std::max(1, rf); f <= kFloors; ++f) {
                int v = f == cn.nfloor ? h : win ? h : 0;
                if (f < cn.nfloor) v = f - rf < static_cast<int>(cn.passed.size()) ? hpClass(cn.passed[f - rf]) : 0;
                cn.hpfv[f - 1] = static_cast<float>(v / 255.0);
            }
        };
        auto setHpDeath = [&](Run &g, Node &cn) { setHpEnd(g, cn, false, false, 0); };
        auto setHpGameEnd = [&](Run &g, Node &cn) {   // an out-of-combat node whose game is over (cn.gc)
            const bool win = heartWin(*cn.gc);
            setHpEnd(g, cn, win, win || (keylessVictory(*cn.gc) && (cfg.keylessHp || usesAmberH(cfg.utility))), cn.gc->curHp);
        };
        // searchEmaHp: the HP entries of a node the net evaluated (resHpd / resHpf are its result).
        auto setHpEval = [&](Run &g, Node &n, const Flight &fl) {
            const int rf = g.pool[0].nfloor;
            if (n.nfloor > rf && !n.passed.empty()) {
                n.hpd.clear();
                n.hpHot = hpClass(n.passed[0]);
            } else {
                n.hpHot = -1;
                n.hpd = fl.resHpd;
            }
            if (!hpfOn) return;
            n.hpfv.assign(kFloors, 0.f);
            for (int f = std::max(1, rf); f <= kFloors; ++f) {
                if (f >= n.nfloor) n.hpfv[f - 1] = std::clamp(fl.resHpf[f - 1], 0.f, 1.f);
                else if (f - rf < static_cast<int>(n.passed.size())) n.hpfv[f - 1] = static_cast<float>(hpClass(n.passed[f - rf]) / 255.0);
            }
        };
        auto copyHp = [&](Node &cn, const Node &from) {   // a child that keeps its parent's value
            if (!hpOn) return;
            cn.hpHot = from.hpHot;
            cn.hpd = from.hpd;
            cn.hpfv = from.hpfv;
        };
        // searchEmaHp: a node's HP entries added to the root's sums.
        auto addHp = [&](Run &g, const Node &n) {
            if (n.hpHot >= 0) g.rootHpd[n.hpHot] += 1.0;
            else {
                if (n.hpd.size() != static_cast<std::size_t>(kHpClasses))
                    throw std::logic_error("run driver: leaf without a floor HP distribution");
                for (int k = 0; k < kHpClasses; ++k) g.rootHpd[k] += n.hpd[k];
            }
            if (hpfOn) {
                if (n.hpfv.size() != static_cast<std::size_t>(kFloors))
                    throw std::logic_error("run driver: leaf without per-floor HP values");
                for (int k = 0; k < kFloors; ++k) g.rootHpf[k] += n.hpfv[k];
            }
        };
        // Backs the value v of the path's leaf up along the path. virt: the path holds virtual losses (parallelNodes),
        // which the real visits replace.
        auto backup = [&](Run &g, const std::vector<PathStep> &path, float v, bool virt = false) {
            if (emaOn) {   // the leaf (last path entry) adds its distribution to the root's sum
                const Node &leaf = g.pool[path.back().node];
                if (leaf.dist.size() != static_cast<std::size_t>(kOutcomeClasses))
                    throw std::logic_error("run driver: leaf without an outcome distribution");
                for (int k = 0; k < kOutcomeClasses; ++k) g.rootDist[k] += leaf.dist[k];
                if (hpOn) addHp(g, leaf);
            }
            for (const auto &p : path) {
                Node &n = g.pool[p.node];
                n.n += 1;
                n.w += v;
                if (p.edge >= 0) {
                    Edge &e = n.edges[p.edge];
                    e.n += 1;
                    e.w += v;
                    if (virt) --e.vn;
                    if (p.outcome >= 0) e.outcomeN[p.outcome] += 1;
                }
            }
            ++g.spent;
        };

        // Labels of the current floor's samples once the floor is left (or the run ends).
        auto closeFloor = [&](Run &g, int hpEnd) {
            for (std::size_t i = g.floorStart; i < g.pending.size(); ++i) g.pending[i].hpEnd = static_cast<std::int16_t>(hpEnd);
            if (hpOn) {
                // The floor's EMA chain of the floor HP distribution, last chain move first, ending in the real HP.
                const double lam = cfg.searchEmaLambda;
                std::array<double, kHpClasses> t{};
                t[hpClass(hpEnd)] = 1.0;
                const int M = static_cast<int>(g.moveDist.size() / kOutcomeClasses);
                int si = static_cast<int>(g.pending.size()) - 1;
                const int s0 = static_cast<int>(g.floorStart);
                auto give = [&](int m) {   // samples whose chain move is m take the current target, 8-bit fixed point
                    for (; si >= s0 && g.pending[si].emaMove == m; --si) {
                        Sample &s = g.pending[si];
                        int lo = kHpClasses, hi = -1;
                        std::array<std::uint8_t, kHpClasses> q;
                        for (int k = 0; k < kHpClasses; ++k) {
                            q[k] = static_cast<std::uint8_t>(std::clamp<long>(std::lround(255.0 * t[k]), 0, 255));
                            if (q[k]) { lo = std::min(lo, k); hi = k; }
                        }
                        if (hi < 0) throw std::logic_error("run driver: empty floor HP target");
                        s.hpTargetLo = static_cast<std::int16_t>(lo);
                        s.hpTargetQ.assign(q.begin() + lo, q.begin() + hi + 1);
                    }
                };
                give(M);   // kept moves after the floor's last chain move: the real HP
                for (int m = M - 1; m >= g.floorChain0; --m) {
                    const float *d = g.floorHpd.data() + static_cast<std::size_t>(m - g.floorChain0) * kHpClasses;
                    for (int k = 0; k < kHpClasses; ++k) t[k] = (1.0 - lam) * d[k] + lam * t[k];
                    give(m);
                }
                if (si >= s0) throw std::logic_error("run driver: kept sample outside its floor's chain");
                g.floorHpd.clear();
                g.floorChain0 = M;
            }
            g.floorStart = g.pending.size();
            if (g.floor >= 1 && g.floor <= kFloors) g.floorHp[g.floor] = static_cast<std::int16_t>(hpEnd);
        };

        std::function<void(Run &, int)> startMove;

        // RunConfig::auxFights: the fight starts of the out-of-combat sample s (the run's current state g.gc) into s's
        // aux fields. Each start is the public view at the fight's first decision of a copy of g.gc that enters the
        // encounter in its room (off the current map node, so no burning-elite buff), encoded without actions. A start
        // whose view cannot be built, or whose tokens went into a new run dictionary (compactSamples), is left out.
        std::array<AuxFight, 1 + 3 + kAuxHallway> auxList;
        std::unique_ptr<GameContext> auxGc;
        BattleContext auxLive, auxView;
        search::CombatKnowledgeState auxKn;
        AmberTokens auxTok;
        Sample auxRow;
        const std::vector<Action> noActions;
        auto auxFightStarts = [&](Run &g, Sample &s) {
            if (!g.gc.map) return;
            const int n = auxFightList(g.gc, g.seed * 0x9e3779b97f4a7c15ull ^ static_cast<std::uint64_t>(g.moves), auxList);
            s.auxTokOff.assign(1, 0);
            for (int k = 0; k < n; ++k) {
                if (auxGc) *auxGc = g.gc;
                else auxGc = std::make_unique<GameContext>(g.gc);
                GameContext &c = *auxGc;
                c.curRoom = auxList[k].room;
                c.info.encounter = auxList[k].enc;
                c.curMapNodeX = -1;
                initObservedBattle(c, auxLive, auxKn);
                if (!publicCombatRoot(auxLive, auxKn, auxView).empty()) continue;
                cfg.encodeCombat(auxView, combatContext(c, false), noActions, auxTok);
                if (cfg.mergeCards) search::amberMergeCards(auxTok);
                if (cfg.compactSamples) {
                    flattenInto(auxTok, auxRow, &g.dict, &g.dictIndex);
                    if (auxRow.dict != s.dict) continue;
                    s.auxTokIdx.insert(s.auxTokIdx.end(), auxRow.tokIdx.begin(), auxRow.tokIdx.end());
                } else {
                    flattenInto(auxTok, auxRow);
                    s.auxTokType.insert(s.auxTokType.end(), auxRow.tokType.begin(), auxRow.tokType.end());
                    s.auxIds.insert(s.auxIds.end(), auxRow.ids.begin(), auxRow.ids.end());
                    s.auxF.insert(s.auxF.end(), auxRow.f.begin(), auxRow.f.end());
                }
                s.auxSlot.push_back(auxList[k].slot);
                s.auxTokOff.push_back(static_cast<std::uint32_t>(cfg.compactSamples ? s.auxTokIdx.size() : s.auxTokType.size()));
                ++wk.st.auxFights;
            }
        };

        auto enterBattle = [&](Run &g) {
            initObservedBattle(g.gc, g.bc, *g.knowledge);
            g.ctx = combatContext(g.gc, g.forceKeys);
            if (cfg.crossCombat) g.fightOuter = std::make_shared<const GameContext>(search::detachedGameCopy(g.gc));
            g.inBattle = true;
            g.fightMoves = 0;
        };


        auto startRun = [&](Run &g, int gi) {
            const std::uint64_t seed = nextSeed();
            if (seed == std::numeric_limits<std::uint64_t>::max()) { g.active = false; return; }
            g.active = true;
            g.seed = seed;
            g.asc = ascension_.load(std::memory_order_relaxed);
            g.forceKeys = forceKeys_.load(std::memory_order_relaxed);
            g.savescum = savescum_.load(std::memory_order_relaxed);
            if (g.savescum) ++wk.st.savescumRuns;
            g.expectValid = false;
            g.gc = GameContext(CharacterClass::IRONCLAD, seed, g.asc, cfg.rngFix);
            if (cfg.testMaxHp > 0) g.gc.curHp = g.gc.maxHp = cfg.testMaxHp;
            g.inBattle = false;
            g.cache.clear();
            g.moves = g.fightMoves = 0;
            g.floor = g.gc.floorNum;
            g.pending.clear();
            g.dict.reset();   // compactSamples: a new dictionary at the run's first kept sample
            g.dictIndex = {};
            g.floorStart = 0;
            g.floorHp.fill(-1);
            g.moveDist.clear();
            g.floorHpd.clear();
            g.floorChain0 = 0;
            g.moveHpf.clear();
            g.moveHpfFloor.clear();
            g.progress = RunProgress{};
            g.hlog = HeartRunLog{};
            // Heart log: a hash of the seed decides (kills are always recorded at the end), not the search RNG.
            g.heartLog = cfg.heartLogRate > 0 &&
                         static_cast<double>(mix64(g.seed ^ 0x6865617274ull) >> 11) * 0x1.0p-53 < cfg.heartLogRate;
            g.heartStart.reset();
            g.heartJob = -1;
            ++wk.st.runsStarted;
            startMove(g, gi);
        };

        auto endRun = [&](Run &g, int gi) {
            if (g.heartJob >= 0) {   // Heart probe: record this play; play the next job from the same start
                const int arms = static_cast<int>(cfg.heartArms.size());
                const GameContext &st = *g.heartStart;
                HeartResult r;
                r.seed = g.seed;
                r.arm = g.heartJob % arms;
                r.rep = g.heartJob / arms;
                r.win = heartWin(g.gc) ? 1 : 0;
                for (int m = 0; m < g.bc.monsters.monsterCount; ++m)
                    if (g.bc.monsters.arr[m].id == MonsterId::CORRUPT_HEART) {
                        r.heartHp = std::max(0, g.bc.monsters.arr[m].curHp);
                        r.heartMaxHp = g.bc.monsters.arr[m].maxHp;
                    }
                if (r.win) r.heartHp = 0;
                r.playerHpStart = st.curHp;
                r.playerMaxHp = st.maxHp;
                r.playerHpEnd = r.win ? g.gc.curHp : 0;
                r.turns = g.bc.turn;
                r.moves = g.fightMoves;
                r.searched = g.heartSearched;
                r.stall = g.bc.outcome == Outcome::UNDECIDED ? 1 : 0;   // stall guard, invalid action or no fair view
                r.deckSize = st.deck.size();
                r.relics = st.relics.size();
                r.asc = g.asc;
                {
                    std::lock_guard<std::mutex> l(heartM_);
                    heartResults_.push_back(r);
                }
                if (++g.heartJob < arms * cfg.heartReps) {
                    g.gc = search::detachedGameCopy(st);
                    g.heartSearched = 0;
                    enterBattle(g);
                    startMove(g, gi);
                    return;
                }
            }
            const bool win = heartWin(g.gc);
            // A keyless act 3 victory is no death: with keylessHp / AMBER its floor keeps the HP (otherwise 0).
            const bool alive = win || (keylessVictory(g.gc) && (cfg.keylessHp || usesAmberH(cfg.utility)));
            closeFloor(g, alive ? g.gc.curHp : 0);
            const int oc = outcomeClass(g.gc);
            for (auto &s : g.pending) s.outcome = static_cast<std::int16_t>(oc);
            if (emaOn) {
                // EMA along the run's searched moves, last move first; a kept sample takes its move's target.
                const double lam = cfg.searchEmaLambda;
                std::array<double, kOutcomeClasses> t{};
                t[oc] = 1.0;
                double realW = 1.0;
                const int M = static_cast<int>(g.moveDist.size() / kOutcomeClasses);
                int si = static_cast<int>(g.pending.size()) - 1;
                auto give = [&](int m) {   // samples whose chain move is m take the current target
                    for (; si >= 0 && g.pending[si].emaMove == m; --si) {
                        Sample &s = g.pending[si];
                        s.outcomeTarget.resize(kOutcomeClasses);
                        for (int k = 0; k < kOutcomeClasses; ++k) s.outcomeTarget[k] = static_cast<float>(t[k]);
                        s.emaRealWeight = static_cast<float>(realW);
                    }
                };
                give(M);   // kept moves after the last chain move: the final outcome
                for (int m = M - 1; m >= 0; --m) {
                    const std::uint16_t *d = g.moveDist.data() + static_cast<std::size_t>(m) * kOutcomeClasses;
                    for (int k = 0; k < kOutcomeClasses; ++k) t[k] = (1.0 - lam) * halfToFloat(d[k]) + lam * t[k];
                    realW *= lam;
                    give(m);
                }
                if (si >= 0) throw std::logic_error("run driver: kept sample without a searched move");
            }
            if (usesAmberH(cfg.utility)) {
                // Floors skipped without a record (a floor counter jump) take the HP of the next recorded floor.
                for (int f = std::min(kFloors, std::max(1, g.floor)) - 1; f >= 1; --f)
                    if (g.floorHp[f] < 0) g.floorHp[f] = g.floorHp[f + 1];
                const int tail = win ? g.gc.curHp : 0;
                for (auto &s : g.pending) {
                    s.hpFloor.resize(kFloors);
                    amberFloorLabels(s.floor, g.floorHp.data(), tail, s.hpFloor.data());
                }
                if (hpfOn) {
                    // Per-floor EMA chain along the run's chain moves, last move first. Move m (on floor fl) holds
                    // search results for the floors fl .. 56; earlier floors keep the real HP, which is what an
                    // earlier move's chain then ends in.
                    const double lam = cfg.searchEmaLambda;
                    std::array<std::int16_t, kFloors> real;
                    amberFloorLabels(1, g.floorHp.data(), tail, real.data());
                    std::array<double, kFloors> t;
                    for (int k = 0; k < kFloors; ++k) t[k] = hpClass(real[k]) / 255.0;
                    const int M = static_cast<int>(g.moveHpfFloor.size());
                    if (M != static_cast<int>(g.moveDist.size() / kOutcomeClasses))
                        throw std::logic_error("run driver: per-floor HP chain out of step");
                    std::size_t off = g.moveHpf.size();
                    int si = static_cast<int>(g.pending.size()) - 1;
                    auto give = [&](int m) {
                        for (; si >= 0 && g.pending[si].emaMove == m; --si) {
                            Sample &s = g.pending[si];
                            const int fl = std::clamp<int>(s.floor, 1, kFloors);
                            s.hpFloorTarget.resize(kFloors);
                            for (int f = 1; f <= kFloors; ++f) s.hpFloorTarget[f - 1] = f < fl ? -1.f : static_cast<float>(t[f - 1]);
                        }
                    };
                    give(M);
                    for (int m = M - 1; m >= 0; --m) {
                        const int fl = g.moveHpfFloor[m], len = kFloors - fl + 1;
                        off -= static_cast<std::size_t>(len);
                        for (int i = 0; i < len; ++i)
                            t[fl - 1 + i] = (1.0 - lam) * halfToFloat(g.moveHpf[off + i]) + lam * t[fl - 1 + i];
                        give(m);
                    }
                    if (si >= 0 || off != 0) throw std::logic_error("run driver: per-floor HP chain does not cover the run");
                }
            }
            if (cfg.exploreAmber) {   // the run's items: once per run in the rate, smallest gap into the item's log
                for (int key : g.pickedKeys) picks_[key].fetch_add(1, std::memory_order_relaxed);
                for (const auto &kv : g.gapMin) offers_[kv.first].fetch_add(1, std::memory_order_relaxed);
                for (const auto &[key, m] : g.gapMin)
                    if (m <= 0) {
                        ++wk.st.exploreNatural;
                        if (std::find(g.pickedKeys.begin(), g.pickedKeys.end(), key) == g.pickedKeys.end())
                            ++wk.st.exploreNaturalUnplayed;
                    }
                {
                    std::lock_guard<std::mutex> l(exploreM_);
                    for (const auto &[key, m] : g.gapMin) exploreItems_[key].hist.add(m);
                }
                g.pickedKeys.clear();
                g.gapMin.clear();
            }
            ++wk.st.runsDone;
            runsDone_.fetch_add(1, std::memory_order_relaxed);
            if (win) ++wk.st.wins;
            wk.st.floorsSum += g.gc.floorNum;
            ++wk.st.outcomes[oc];
            ++wk.st.runsDoneAsc[g.asc];
            if (win) ++wk.st.winsAsc[g.asc];
            wk.st.floorsSumAsc[g.asc] += g.gc.floorNum;
            {
                RunProgress &p = g.progress;
                const bool r = g.gc.hasKey(Key::RUBY_KEY), e = g.gc.hasKey(Key::EMERALD_KEY),
                           sa = g.gc.hasKey(Key::SAPPHIRE_KEY);
                p.ruby = r; p.emerald = e; p.sapphire = sa; p.allKeys = r && e && sa;
                p.act4 = g.gc.act == 4;
                p.keylessVictories = g.gc.outcome == GameOutcome::PLAYER_VICTORY && g.gc.act != 4;
                if (p.keylessVictories) {
                    p.keylessNoSapphire = !sa; p.keylessNoRuby = !r; p.keylessNoEmerald = !e;
                    p.keylessHungryFace = !sa && g.gc.hasRelic(RelicId::NLOTHS_HUNGRY_FACE);
                    static const bool logKeyless = [] {
                        const char *v = std::getenv("STS_AZ_KEYLESS_LOG");
                        return v && std::strcmp(v, "1") == 0;
                    }();
                    if (logKeyless)
                        std::fprintf(stderr, "keyless_victory seed=%llu asc=%d floor=%d sapphire=%d ruby=%d emerald=%d "
                                     "hungry_face=%d\n", static_cast<unsigned long long>(g.gc.seed), g.gc.ascension,
                                     g.gc.floorNum, int(sa), int(r), int(e), int(g.gc.hasRelic(RelicId::NLOTHS_HUNGRY_FACE)));
                }
                p.relicsSum = g.gc.relics.size();
                p.deckSizeSum = g.gc.deck.size();
                if (p.heart) {   // the Heart is the run's last fight, so g.bc still holds it
                    int hp = 0, maxHp = 0;
                    for (int m = 0; m < g.bc.monsters.monsterCount; ++m)
                        if (g.bc.monsters.arr[m].id == MonsterId::CORRUPT_HEART) {
                            hp = std::max(0, g.bc.monsters.arr[m].curHp);
                            maxHp = g.bc.monsters.arr[m].maxHp;
                        }
                    ++p.heartHpHist[std::min(RunProgress::kHeartHpBins - 1, hp / 50)];
                    p.heartHpSum = hp;
                    p.heartTurnsSum = g.bc.turn;
                    if (wk.st.heartHpMin < 0 || hp < wk.st.heartHpMin) wk.st.heartHpMin = hp;
                    if (cfg.heartLogRate > 0 && (g.heartLog || win)) {
                        HeartRunLog &h = g.hlog;
                        h.seed = g.seed;
                        h.asc = g.asc;
                        h.win = win ? 1 : 0;
                        h.floor = g.gc.floorNum;
                        h.heartHp = hp;
                        h.heartMaxHp = maxHp;
                        h.endHp = g.gc.outcome == GameOutcome::PLAYER_LOSS ? 0 : g.gc.curHp;
                        h.turns = g.bc.turn;
                        h.floorHp = g.floorHp;
                        h.elites = p.elites;
                        h.rest = p.rest;
                        h.smith = p.smith;
                        std::lock_guard<std::mutex> l(heartLogM_);
                        heartLogs_.push_back(std::move(h));
                    }
                }
                wk.st.progressAsc[g.asc] += p;
            }

            wk.st.samplesDone += static_cast<std::int64_t>(g.pending.size());
            wk.st.samplesPending -= static_cast<std::int64_t>(g.pending.size());
            pending_.fetch_sub(static_cast<std::int64_t>(g.pending.size()), std::memory_order_relaxed);
            {
                std::lock_guard<std::mutex> l(sampleM_);
                for (auto &s : g.pending) done_.push_back(std::move(s));
            }
            g.pending.clear();
            startRun(g, gi);
        };

        // Applies a chosen action to the real run; handles fight entry / exit, floor labels and the run's end.
        auto applyRealStep = [&](Run &g, std::uint32_t bits) {
            const double t0 = cpuSeconds();
            if (g.inBattle) {
                executeObserved(g.bc, bits, *g.knowledge);
                ++g.fightMoves;
                if (g.bc.outcome == Outcome::UNDECIDED && g.fightMoves >= cfg.maxMovesPerFight) {
                    ++wk.st.stalls;
                    g.gc.outcome = GameOutcome::PLAYER_LOSS;
                    g.inBattle = false;
                } else if (g.bc.outcome != Outcome::UNDECIDED) {
                    g.bc.exitBattle(g.gc);
                    g.inBattle = false;
                }
            } else {
                if (g.gc.screenState == ScreenState::REST_ROOM && !g.gc.restRoomResolved) {
                    RunProgress &p = g.progress;
                    ++p.campfires;
                    if (g.gc.keysEnabled && !g.gc.hasKey(Key::RUBY_KEY)) ++p.recallOffered;
                    const int o = GameAction(bits).getIdx1();
                    ++(o == 0 ? p.rest : o == 1 ? p.smith : o == 2 ? p.recall : p.otherCampfire);
                }
                {   // economy / relic-source counters (logging only)
                    using RT = GameAction::RewardsActionType;
                    RunProgress &p = g.progress;
                    const GameAction a(bits);
                    const auto &r = g.gc.info.rewardsContainer;
                    const Room room = g.gc.curRoom;
                    // A potion action carries no reward / shop item: count it apart (its type bits read as CARD).
                    if (a.isPotionAction()) ++(a.isPotionDiscard() ? p.oocPotionDiscards : p.oocPotionDrinks);
                    else switch (g.gc.screenState) {
                        case ScreenState::TREASURE_ROOM:
                            ++p.chests;
                            if (a.getIdx1() != 0) {
                                ++p.chestsSkipped;
                                if (g.gc.relics.has(RelicId::CURSED_KEY)) ++p.chestsSkippedCursedKey;
                            }
                            break;
                        case ScreenState::REWARDS:
                            if (a.getRewardsActionType() == RT::RELIC)
                                ++(room == Room::ELITE ? p.relicsTakenElite : room == Room::TREASURE ? p.relicsTakenChest
                                                                                                     : p.relicsTakenOther);
                            else if (a.getRewardsActionType() == RT::KEY && r.sapphireKey && r.relicCount > 0)
                                ++p.sapphireRelicForfeits;   // the key replaces the chest's paired relic
                            else if (a.getRewardsActionType() == RT::SKIP && r.relicCount > 0)
                                (room == Room::ELITE ? p.relicsLeftElite : room == Room::TREASURE ? p.relicsLeftChest
                                                                                                  : p.relicsLeftOther) += r.relicCount;
                            break;
                        case ScreenState::SHOP_ROOM:
                            switch (a.getRewardsActionType()) {
                                case RT::CARD: ++p.shopCards; break;
                                case RT::RELIC: ++p.shopRelics; break;
                                case RT::POTION: ++p.shopPotions; break;
                                case RT::CARD_REMOVE: ++p.shopRemoves; break;
                                default: ++p.shops; break;   // leaving ends the visit
                            }
                            break;
                        case ScreenState::BOSS_RELIC_REWARDS:
                            if (a.getIdx1() == 3) ++p.bossRelicSkips;
                            break;
                        default: break;
                    }
                }
                const int gold0 = g.gc.gold;
                GameAction(bits).execute(g.gc);
                (g.gc.gold > gold0 ? g.progress.goldGained : g.progress.goldLost) += std::abs(g.gc.gold - gold0);
            }
            if (!g.inBattle && g.gc.outcome == GameOutcome::UNDECIDED && g.gc.screenState == ScreenState::BATTLE) {
                if (g.gc.curRoom == Room::ELITE) {
                    ++g.progress.elites;
                    if (g.gc.map && g.gc.map->burningEliteX == g.gc.curMapNodeX &&
                        g.gc.map->burningEliteY == g.gc.curMapNodeY)
                        ++g.progress.burningElites;
                }
                if (g.gc.info.encounter == MonsterEncounter::THE_HEART) {
                    g.progress.heart = 1;
                    g.progress.heartEntryHpSum = g.gc.curHp;
                    if (cfg.heartLogRate > 0) {   // Heart log: the state entering the fight (kept for every run: a kill is always recorded)
                        HeartRunLog &h = g.hlog;
                        h.entryHp = g.gc.curHp;
                        h.entryMaxHp = g.gc.maxHp;
                        h.gold = g.gc.gold;
                        h.deck.clear();
                        for (int i = 0; i < g.gc.deck.size(); ++i)
                            h.deck.emplace_back(static_cast<int>(g.gc.deck.cards[i].getId()), g.gc.deck.cards[i].isUpgraded() ? 1 : 0);
                        h.relics.clear();
                        for (const auto &r : g.gc.relics.relics) h.relics.push_back(static_cast<int>(r.id));
                        h.potions.clear();
                        for (int i = 0; i < std::min(g.gc.potionCapacity, 5); ++i)
                            if (g.gc.potions[i] != Potion::EMPTY_POTION_SLOT) h.potions.push_back(static_cast<int>(g.gc.potions[i]));
                    }
                    if (!cfg.heartArms.empty() && g.heartJob < 0) {   // Heart probe: keep the start, play job 0
                        g.heartStart = std::make_shared<const GameContext>(search::detachedGameCopy(g.gc));
                        g.heartJob = 0;
                        g.heartSearched = 0;
                    }
                }
                enterBattle(g);
            }
            wk.st.stepCpu += cpuSeconds() - t0;
            ++wk.st.moves;
            if (++g.moves >= kMaxMovesPerRun && g.gc.outcome == GameOutcome::UNDECIDED) {
                ++wk.st.stalls;
                g.gc.outcome = GameOutcome::PLAYER_LOSS;
                g.inBattle = false;
            }
            if (g.gc.floorNum != g.floor) {
                closeFloor(g, g.gc.curHp);
                g.floor = g.gc.floorNum;
            }
        };

        // applyRealStep, with forceRewards' card-first relics taken (as real steps) before leaving a REWARDS screen.
        auto applyReal = [&](Run &g, std::uint32_t bits) {
            if (cfg.forceRewards && !g.inBattle && g.gc.screenState == ScreenState::REWARDS &&
                    GameAction(bits).getRewardsActionType() == GameAction::RewardsActionType::SKIP) {
                while (const auto f = forcedRewardBeforeLeave(g.gc)) {
                    ++wk.st.rewardRelicOnLeave;
                    applyRealStep(g, f->bits);
                    if (g.inBattle || g.gc.screenState != ScreenState::REWARDS) return;
                }
            }
            applyRealStep(g, bits);
        };

        startMove = [&](Run &g, int gi) {
            // Moves with one legal action (or none) are played without a search.
            while (true) {
                if (!g.active) return;
                if (g.gc.outcome != GameOutcome::UNDECIDED) { endRun(g, gi); return; }
                std::size_t legal;
                std::uint32_t only = 0;
                if (g.inBattle) {
                    const auto &a = combatActions(g.bc, g.ctx);
                    legal = a.size();
                    if (legal == 1) only = a[0].bits;
                } else {
                    if (goldToTake(g.gc)) { ++wk.st.autoGold; applyReal(g, takeGoldBits); continue; }
                    int keyRule = -1, rewardRule = -1, potionRule = -1, canonRemoved = 0;
                    gacts = oocActions(g.gc, g.forceKeys, &keyRule, &rewardRule, &potionRule, &canonRemoved);
                    if (potionRule > 0) ++wk.st.forcedPotions;
                    if (canonRemoved > 0) { ++wk.st.oocCanonScreens; wk.st.oocCanonRemoved += canonRemoved; }
                    if (keyRule >= 0 && keyRule < 3) ++wk.st.forcedKeys[keyRule];
                    else if (keyRule == 3) ++wk.st.keyRouteMasked;
                    if (rewardRule == 0 || rewardRule == 1) ++wk.st.forcedRewards[rewardRule];
                    else if (rewardRule == 2) ++wk.st.rewardRelicDeferred;
                    legal = gacts.size();
                    if (legal == 1) only = gacts[0].bits;
                }
                if (legal == 0) {   // no decision possible: an engine dead end counts as a loss
                    ++wk.st.stalls;
                    g.gc.outcome = GameOutcome::PLAYER_LOSS;
                    g.inBattle = false;
                    continue;
                }
                if (legal > 1) break;
                applyReal(g, only);
            }
            if (g.expectValid) {   // savescum: the search's child of the played action is this state
                g.expectValid = false;
                ++wk.st.savescumChecks;
                const std::uint64_t fp = g.inBattle ? stateFingerprint(g.bc) : stateFingerprint(g.gc);
                if (fp != g.expectFp) ++wk.st.savescumMismatches;
            }
            // savescum off (setSavescum(false)): a run in progress plays fair from its next searched move.
            if (g.savescum && !savescum_.load(std::memory_order_relaxed)) g.savescum = false;
            if (poolTrim) {
                // Release what the last search left in the run's node slots (2026-11-19 memory creep): the fight-start
                // game states that crossCombat combat nodes share (otherwise each slot pins a stale copy until it is
                // reused), and the slots above the usual search size, which only rare large searches (exploreAmber
                // extra candidates) reach and which otherwise keep their game state / real fight for the run's
                // lifetime and every later run of the slot. STS_AZ_POOL_TRIM=0 restores the old behaviour.
                if (g.pool.size() > poolKeep) g.pool.resize(poolKeep);
                for (auto &n : g.pool) n.outer.reset();
            }
            g.poolUsed = 0;
            g.spent = 0;
            const HeartArm *arm = g.heartJob >= 0 && g.inBattle
                                      ? &cfg.heartArms[g.heartJob % static_cast<int>(cfg.heartArms.size())] : nullptr;
            if (arm) ++g.heartSearched;
            g.full = U(wk.rng) < (arm ? arm->fullProb : cfg.fullProb);
            {
                const double pend = static_cast<double>(pending_.load(std::memory_order_relaxed));
                const double scale = cfg.maxPendingSamples > 0 && pend > cfg.maxPendingSamples ? cfg.maxPendingSamples / pend : 1.0;
                g.keep = U(wk.rng) < (g.full ? cfg.keepFull : cfg.keepFast) * scale;
            }
            g.budget = arm ? (g.full ? arm->fullSims : arm->fastSims) : g.full ? cfg.fullSims : cfg.fastSims;
            g.candidates = arm ? (g.full ? arm->fullCandidates : arm->fastCandidates)
                               : g.full ? cfg.fullCandidates : cfg.fastCandidates;
            g.cand.clear();
            g.phaseQueue.clear();
            g.nFlights = g.waiting = 0;
            const int r = newNode(g);
            Node &root = g.pool[r];
            root.nfloor = g.gc.floorNum;
            if (g.inBattle) {
                root.combat = true;
                root.ctx = g.ctx;
                root.outer = g.fightOuter;   // crossCombat only (null otherwise)
                const bool view = g.savescum ? setReal(root, g.bc, *g.knowledge)
                                             : publicCombatRoot(g.bc, *g.knowledge, useBc(root)).empty();
                if (!view) {
                    // No fair view of this fight (an intent pattern the tracker cannot represent): abandon the run.
                    ++wk.st.knowledgeFailures;
                    g.poolUsed = 0;
                    g.gc.outcome = GameOutcome::PLAYER_LOSS;
                    g.inBattle = false;
                    endRun(g, gi);
                    return;
                }
            } else {
                setGc(root, search::detachedGameCopy(g.gc));
            }
            g.rootKeys.clear();
            g.rootClass.clear();
            g.rootUnder.clear();
            {
                Flight &f = newFlight(g);
                f.path.push_back({r, -1, -1});
                request(g, gi, r, f);
            }
            if (!g.inBattle && (cfg.exploreC > 0 || cfg.exploreAmber)) {
                ++wk.st.oocRoots;
                const double games = static_cast<double>(exploreGames());
                bool under = false;
                // Rates are over finished runs, after a warm-up of 1 / pickTarget runs (no item is under target before).
                if (games * cfg.pickTarget >= 1.0) {
                    if (cfg.exploreAmber) g.rootUnder.assign(g.rootKeys.size(), 0);
                    for (std::size_t k = 0; k < g.rootKeys.size(); ++k) {
                        const int key = g.rootKeys[k];
                        if (key < 0) continue;
                        // explorePerOffer: the rate is over the runs that offered the item, after 1 / pickTarget of them
                        const double base = cfg.explorePerOffer
                            ? static_cast<double>(offers_[key].load(std::memory_order_relaxed)) : games;
                        if (base * cfg.pickTarget >= 1.0
                            && picks_[key].load(std::memory_order_relaxed) < cfg.pickTarget * base) {
                            under = true;
                            if (cfg.exploreAmber) g.rootUnder[k] = 1;
                        }
                    }
                }
                if (under) {
                    ++wk.st.exploreRoots;
                    if (!g.full) {   // a root with an under-target item gets a full search (policy target recorded)
                        g.full = true;
                        const double pend = static_cast<double>(pending_.load(std::memory_order_relaxed));
                        const double scale = cfg.maxPendingSamples > 0 && pend > cfg.maxPendingSamples ? cfg.maxPendingSamples / pend : 1.0;
                        g.keep = U(wk.rng) < cfg.keepFull * scale;
                        g.budget = cfg.fullSims;
                        g.candidates = cfg.fullCandidates;
                    }
                }
            }
        };

        auto initRoot = [&](Run &g) {
            Node &root = g.pool[0];
            const int k = static_cast<int>(root.edges.size());
            g.gumbel.assign(k, 0);
            std::extreme_value_distribution<double> G(0.0, 1.0);
            std::vector<int> order(k);
            // cfg.fastNoise false (Amber Eye: no exploration noise on fast moves): a fast move's Gumbel draws stay 0,
            // so it takes the top logits as candidates and plays the best logit + sigma(Q). The draws are still made,
            // so the worker RNG stream (resampling, keep decisions) is the same with and without the flag.
            const bool noisy = g.full || cfg.fastNoise;
            for (int i = 0; i < k; ++i) { const double x = G(wk.rng); g.gumbel[i] = noisy ? x : 0.0; order[i] = i; }
            std::sort(order.begin(), order.end(), [&](int a, int b) {
                return g.gumbel[a] + root.edges[a].logit > g.gumbel[b] + root.edges[b].logit;
            });
            const int m = std::min(k, g.candidates);
            g.cand.assign(order.begin(), order.begin() + m);
            if (!g.rootUnder.empty())   // exploreAmber: every under-target item is a candidate on top of the usual ones
                for (int i = m; i < k; ++i)
                    if (order[i] < static_cast<int>(g.rootUnder.size()) && g.rootUnder[order[i]]) g.cand.push_back(order[i]);
            const int mc = static_cast<int>(g.cand.size());
            g.phasesLeft = mc > 1 ? static_cast<int>(std::ceil(std::log2(mc))) : 1;
        };

        auto fillPhase = [&](Run &g) {
            const int remaining = g.budget - g.spent;
            const int per = std::max(1, remaining / std::max(1, g.phasesLeft) / static_cast<int>(g.cand.size()));
            g.phaseQueue.clear();
            for (int r = 0; r < per; ++r)
                for (int e : g.cand) g.phaseQueue.push_back(e);
        };

        auto halve = [&](Run &g) {
            const Node &root = g.pool[0];
            std::vector<double> q;
            completedQ(root, cfg, q);
            const double sigma = (cfg.cVisit + maxVisits(root)) * cfg.cScale;
            std::sort(g.cand.begin(), g.cand.end(), [&](int a, int b) {
                return rootScore(g, root, a, sigma, q) > rootScore(g, root, b, sigma, q);
            });
            if (g.rootUnder.empty()) {
                g.cand.resize(std::max<std::size_t>(1, (g.cand.size() + 1) / 2));
            } else {   // exploreAmber: under-target items survive; the others are halved as usual
                auto isUnder = [&](int e) { return e < static_cast<int>(g.rootUnder.size()) && g.rootUnder[e] != 0; };
                std::vector<int> kept, forced;
                for (int e : g.cand) (isUnder(e) ? forced : kept).push_back(e);
                if (!kept.empty()) kept.resize(std::max<std::size_t>(1, (kept.size() + 1) / 2));
                kept.insert(kept.end(), forced.begin(), forced.end());
                g.cand = std::move(kept);
            }
            --g.phasesLeft;
        };

        auto finishMove = [&](Run &g, int gi) {
            const Node &root = g.pool[0];
            std::vector<double> q;
            completedQ(root, cfg, q);
            const double sigma = (cfg.cVisit + maxVisits(root)) * cfg.cScale;
            int pick = g.cand.empty() ? 0 : g.cand.front();
            if (g.cand.size() > 1) {
                double best = -1e300;
                for (int e : g.cand) {
                    const double s = rootScore(g, root, e, sigma, q);
                    if (s > best) { best = s; pick = e; }
                }
            }
            ++wk.st.searchedMoves;
            // The search result of this move: the root's mean backed-up distribution (a chain move: kept as float16).
            thread_local std::array<float, kOutcomeClasses> moveResult;
            const bool inChain = emaOn && (g.full || !cfg.searchEmaFullOnly);
            if (emaOn) {
                const double inv = 1.0 / std::max(1, root.n);
                for (int k = 0; k < kOutcomeClasses; ++k) moveResult[k] = static_cast<float>(g.rootDist[k] * inv);
                if (inChain)
                    for (int k = 0; k < kOutcomeClasses; ++k) g.moveDist.push_back(search::amberHalf(moveResult[k]));
                if (hpOn) {
                    // Every backed-up leaf gave a distribution: the root's sum is its visit count.
                    double sum = 0;
                    for (int k = 0; k < kHpClasses; ++k) sum += g.rootHpd[k];
                    if (std::abs(sum * inv - 1.0) > 1e-3) throw std::logic_error("run driver: floor HP search result does not sum to 1");
                    if (inChain) {
                        for (int k = 0; k < kHpClasses; ++k) g.floorHpd.push_back(static_cast<float>(g.rootHpd[k] / sum));
                        if (hpfOn) {
                            const int fl = std::clamp(root.nfloor, 1, kFloors);
                            g.moveHpfFloor.push_back(static_cast<std::uint8_t>(fl));
                            for (int f = fl; f <= kFloors; ++f) g.moveHpf.push_back(search::amberHalf(static_cast<float>(g.rootHpf[f - 1] * inv)));
                        }
                    }
                }
            }
            if (cfg.heartLogRate > 0) {   // Heart log: the first searched move of each act and of the Heart fight
                constexpr int kHeartFloor = 55;   // Act 4: 52 rest, 53 shop, 54 elite, 55 the Heart
                HeartRunLog &h = g.hlog;
                const int slot = g.inBattle && g.progress.heart ? 4 : std::clamp(g.gc.act, 1, 4) - 1;
                if (h.floorAt[slot] < 0) {
                    h.floorAt[slot] = g.gc.floorNum;
                    h.netValue[slot] = root.value;
                    h.searchValue[slot] = static_cast<float>(root.w / std::max(1, root.n));
                    if (root.dist.size() == static_cast<std::size_t>(kOutcomeClasses)) {
                        double ef = 0;
                        for (int k = 0; k < kOutcomeClasses; ++k) ef += (k == 0 ? 57.0 : k) * root.dist[k];
                        h.netPWin[slot] = root.dist[0];
                        h.netPHeartDeath[slot] = root.dist[kHeartFloor];   // death on the Heart floor, every slot
                        h.netEFloor[slot] = static_cast<float>(ef);
                        h.searchPWin[slot] = moveResult[0];
                    } else {
                        h.netPWin[slot] = h.netPHeartDeath[slot] = h.netEFloor[slot] = h.searchPWin[slot] = -1;
                    }
                }
            }
            if (!root.combat) {
                const int kind = g.full ? 0 : 1;
                int bestQ = -1, visited = 0;
                double lo = 1e300, hi = -1e300;
                for (int i = 0; i < static_cast<int>(root.edges.size()); ++i) {
                    const Edge &x = root.edges[i];
                    if (!x.n) continue;
                    ++visited;
                    const double m = x.w / x.n;
                    if (m > hi) { hi = m; bestQ = i; }
                    lo = std::min(lo, m);
                }
                ++wk.st.oocSearched[kind];
                if (bestQ >= 0 && pick != bestQ) ++wk.st.oocNotBestQ[kind];
                if (visited >= 2) { ++wk.st.oocSpreadN[kind]; wk.st.oocSpreadSum[kind] += hi - lo; }
            }
            if (g.keep) {
                Sample &s = g.cur;
                if (g.full) {   // Gumbel AlphaZero's improved policy: softmax(logits + sigma(completed Q))
                    const int k = static_cast<int>(root.edges.size());
                    std::vector<double> z(k);
                    double mx = -1e300;
                    for (int i = 0; i < k; ++i) {
                        z[i] = root.edges[i].logit + sigma * q[i];
                        mx = std::max(mx, z[i]);
                    }
                    double sum = 0;
                    for (auto &x : z) { x = std::exp(x - mx); sum += x; }
                    const int na = static_cast<int>(s.aType.size());
                    s.policy.assign(na, 0.f);
                    // The target covers the encoded actions only (a cut tail is rare): renormalise over them.
                    double kept = 0;
                    for (int i = 0; i < std::min(k, na); ++i) kept += z[i];
                    if (kept <= 0) kept = sum;
                    for (int i = 0; i < std::min(k, na); ++i) s.policy[i] = static_cast<float>(z[i] / kept);
                } else {
                    s.policy.clear();
                }
                s.searchValue = static_cast<float>(root.n ? root.w / root.n : root.value);
                if (emaOn) {
                    // A chain move's own index; a move outside the chain: the next chain move's (not recorded yet).
                    const int chainMoves = static_cast<int>(g.moveDist.size() / kOutcomeClasses);
                    s.emaMove = inChain ? chainMoves - 1 : chainMoves;
                    s.searchDist.assign(moveResult.begin(), moveResult.end());   // float32 (exact mean)
                }
                g.pending.push_back(std::move(s));
                ++wk.st.samplesPending;
                pending_.fetch_add(1, std::memory_order_relaxed);
            }
            if (!root.combat && cfg.exploreC > 0 && !g.rootKeys.empty()) {
                const double games = static_cast<double>(exploreGames());
                const bool warm = games * cfg.pickTarget >= 1.0;
                int worst = -1;
                double worstRate = cfg.pickTarget;
                for (int k = 0; k < static_cast<int>(g.rootKeys.size()) && k < static_cast<int>(root.edges.size()); ++k) {
                    const int key = g.rootKeys[k];
                    if (key < 0) continue;
                    const double rate = picks_[key].load(std::memory_order_relaxed) / games;
                    if (rate < worstRate) { worstRate = rate; worst = k; }
                }
                if (warm && worst >= 0 && worst != pick
                    && U(wk.rng) < std::min(1.0, cfg.exploreC * (1.0 - worstRate / cfg.pickTarget))) {
                    pick = worst;
                    ++wk.st.forcedPicks;
                }
                if (pick < static_cast<int>(g.rootKeys.size()) && g.rootKeys[pick] >= 0)
                    picks_[g.rootKeys[pick]].fetch_add(1, std::memory_order_relaxed);
            }
            if (!root.combat && cfg.exploreAmber && !g.rootKeys.empty()) {
                const int k = std::min(static_cast<int>(g.rootKeys.size()), static_cast<int>(root.edges.size()));
                // Gap in policy logits (the net's prior logits) below the search's pick, at least 1e-9;
                // exploreGapSearch: in the search's root score (Gumbel + logit + sigma(completed Q)) instead.
                const int searchPick = pick;
                auto score = [&](int i) {
                    return cfg.exploreGapSearch ? rootScore(g, root, i, sigma, q) : static_cast<double>(root.edges[i].logit);
                };
                const double top = score(searchPick);
                auto gap = [&](int i) { return std::max(1e-9, top - score(i)); };
                std::vector<int> under;
                for (int i = 0; i < k; ++i)
                    if (g.rootKeys[i] >= 0 && i != searchPick && i < static_cast<int>(g.rootUnder.size())
                        && g.rootUnder[i]) under.push_back(i);
                std::shuffle(under.begin(), under.end(), wk.rng);
                const std::int64_t games = exploreGames();
                for (int i : under) {
                    const double m = gap(i);
                    const double c = exploreItemC(g.rootKeys[i], games);
                    const int cls = i < static_cast<int>(g.rootClass.size()) ? g.rootClass[i] : 7;
                    ++wk.st.exploreAttempts;
                    ++wk.st.exploreAttemptsByClass[cls];
                    if (c == 0) ++wk.st.exploreCZero;
                    if (std::isinf(c)) ++wk.st.exploreCInf;
                    const double p = std::isinf(c) ? 1.0 : std::min(1.0, c * std::exp(-m / cfg.exploreT));
                    if (U(wk.rng) < p) { pick = i; ++wk.st.forcedPicks; ++wk.st.forcedByClass[cls]; break; }
                }
                // Log: m = 0 ("natural") only for the search's pick when it is played; a forced item logs its gap, an
                // overridden search pick 1e-9 (bin 0), every other item its gap.
                for (int i = 0; i < k; ++i) {
                    const int key = g.rootKeys[i];
                    if (key < 0) continue;
                    const double m = (i == searchPick && pick == searchPick) ? 0.0 : gap(i);
                    auto it = g.gapMin.find(key);
                    if (it == g.gapMin.end()) g.gapMin.emplace(key, m);
                    else it->second = std::min(it->second, m);
                }
                if (pick < k && g.rootKeys[pick] >= 0
                    && std::find(g.pickedKeys.begin(), g.pickedKeys.end(), g.rootKeys[pick]) == g.pickedKeys.end())
                    g.pickedKeys.push_back(g.rootKeys[pick]);
            }
            std::uint32_t bits = root.edges[pick].bits;
            if (root.combat) {
                // The search chose against the public view, whose pile orders differ from the real fight's: map card
                // indices by identity (as production does).
                // savescum: root.real is g.bc, so the request's translation is the same.
                const Edge &pe = root.edges[pick];
                const bool ok = root.hasReal ? pe.realOk : true;
                if (root.hasReal) bits = pe.realBits;
                else bits = search::SilverSearcher::translateAction(Action(bits), *root.bc, g.bc).bits;
                if (!ok || !Action(bits).isValidAction(g.bc)) {
                    ++wk.st.invalidActions;
                    g.gc.outcome = GameOutcome::PLAYER_LOSS;
                    g.inBattle = false;
                    startMove(g, gi);
                    return;
                }
            }
            if (g.savescum) {   // the played edge's child, when it is a decision state, is the next real decision
                const Edge &pe = root.edges[pick];
                g.expectValid = false;
                if (pe.tried && !pe.chance && pe.child >= 0) {
                    const Node &c = g.pool[pe.child];
                    if (c.evaluated && !c.terminal && c.edges.size() > 1) {
                        if (c.combat && c.hasReal) { g.expectValid = true; g.expectFp = stateFingerprint(*c.real); }
                        else if (!c.combat && c.gc) { g.expectValid = true; g.expectFp = stateFingerprint(*c.gc); }
                    }
                }
            }
            applyReal(g, bits);
            startMove(g, gi);
        };

        // Expands edge e of node cur (first visit or a new chance outcome); returns the child node.
        auto expand = [&](Run &g, int cur, int e, int &outcome) -> int {
            outcome = -1;
            Edge &edge0 = g.pool[cur].edges[e];
            const bool first = !edge0.tried;
            if (!first && !edge0.chance) return edge0.child;
            if (!first) {
                const int visits = edge0.n + edge0.vn;   // vn: simulations in flight (parallelNodes), else 0
                const int cap = static_cast<int>(std::ceil(cfg.wideningC * std::pow(visits + 1.0, cfg.wideningAlpha)));
                if (static_cast<int>(edge0.outcomes.size()) >= cap) {
                    outcome = static_cast<int>(visits % edge0.outcomes.size());
                    return edge0.outcomes[outcome];
                }
            }
            const int child = newNode(g);   // pool may not move (capacity reserved), references stay valid
            Node &parent = g.pool[cur];
            Edge &edge = parent.edges[e];
            Node &cn = g.pool[child];
            if (parent.combat) {
                BattleContext next = *parent.bc;
                if (first) edge.base = search::searchRandomnessBase(next);
                search::seedSearchRng(next, edge.base + edge.outcomes.size());
                Action(edge.bits).execute(next);
                if (first) edge.chance = search::searchRngCounter(next) != 0;
                if (next.outcome == Outcome::PLAYER_LOSS) {
                    cn.combat = true;
                    useBc(cn) = next;
                    cn.evaluated = cn.terminal = true;
                    cn.value = terminalUtility(false, false, g.gc.floorNum, 0, 1, cfg.hpWeightCombat, cfg, true, g.pool[0].combat);
                    if (emaOn) setOneHot(cn, std::clamp(g.gc.floorNum, 1, kOutcomeClasses - 1));   // death on this floor
                } else if (next.outcome == Outcome::PLAYER_VICTORY) {
                    // Fight won: the leaf is the state after the fight, valued by the net (out of combat).
                    // The real run's hidden future (reward rolls, later encounters) is resampled first, so the
                    // leaf does not show the rewards the real fight would give.
                    GameContext after = search::detachedGameCopy(g.gc);
                    std::mt19937_64 r(edge.base ^ 0x9e3779b97f4a7c15ull ^ (edge.outcomes.size() + 1));
                    try { search::sampleNoncombatFuture(after, r); }
                    catch (const search::OocSearchUnsupported &) { ++wk.st.unsupported; }
                    next.exitBattle(after);
                    setGc(cn, std::move(after));
                    cn.boundary = true;
                    if (cn.gc->outcome != GameOutcome::UNDECIDED) {
                        cn.evaluated = cn.terminal = true;
                        cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg, false, g.pool[0].combat);
                        if (emaOn) { setOneHot(cn, outcomeClass(*cn.gc)); setHpGameEnd(g, cn); }
                    }
                } else {
                    cn.combat = true;
                    useBc(cn) = next;
                    cn.ctx = parent.ctx;
                }
            } else {
                if (first) { edge.chance = true; edge.base = wk.rng(); }
                GameContext next = search::detachedGameCopy(*parent.gc);
                std::mt19937_64 r(edge.base + edge.outcomes.size());
                bool ok = true;
                try { search::sampleNoncombatFuture(next, r); }
                catch (const search::OocSearchUnsupported &) { ok = false; ++wk.st.unsupported; }
                if (ok) {
                    execOoc(next, edge.bits);
                    if (next.outcome != GameOutcome::UNDECIDED) {
                        setGc(cn, std::move(next));
                        cn.evaluated = cn.terminal = true;
                        cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg, false, g.pool[0].combat);
                        if (emaOn) { setOneHot(cn, outcomeClass(*cn.gc)); setHpGameEnd(g, cn); }
                    } else if (next.screenState == ScreenState::BATTLE) {
                        // A fight starts: the leaf is its first state, valued by the net (in combat).
                        cn.combat = true;
                        // Its public view, as at a real fight start (the shuffle is a sample anyway; this keeps the
                        // net's input distribution the same as at real roots).
                        search::CombatKnowledgeState k;
                        BattleContext live;
                        initObservedBattle(next, live, k);
                        BattleContext &cbc = useBc(cn);
                        if (!publicCombatRoot(live, k, cbc).empty()) cbc = live;
                        cn.ctx = combatContext(next, g.forceKeys);
                        cn.boundary = true;
                    } else {
                        setGc(cn, std::move(next));
                    }
                } else {   // hidden history the resampler cannot handle: the child keeps the parent's value
                    cn.combat = false;
                    cn.evaluated = cn.terminal = true;
                    cn.value = parent.value;
                    if (emaOn) cn.dist = parent.dist;
                }
            }
            if (edge.chance) {
                edge.outcomes.push_back(child);
                edge.outcomeN.push_back(0);
                outcome = static_cast<int>(edge.outcomes.size()) - 1;
            } else {
                edge.child = child;
            }
            edge.tried = true;
            return child;
        };


        // --- Amber Eye's search rules (RunConfig::chanceOnReveal / crossCombat / simHelp) ---------------------------
        //
        // One step from node `parent` along action `bits` into node `ci`: the action, then (simHelp) every forced
        // position and reward gold, a won fight's exit into its game state and a fight's start, until a decision, a
        // leaf or the run's end. k: outcome index (randomness base + k); resample false: the hidden state is kept and
        // `revealed` says whether the step used it (out-of-combat parts; the combat part is always a search sample,
        // combatRng says whether it drew). resample true: hidden out-of-combat state is resampled before it is used.
        constexpr std::uint64_t kExitSalt = 0x9e3779b97f4a7c15ull;
        auto stepAmber = [&](Run &g, int pi, std::uint32_t bits, std::uint64_t base, int k, bool resample, int ci,
                             bool &combatRng, bool &revealed, std::uint32_t realBits, bool realOk) {
            combatRng = revealed = false;
            const Node &parent = g.pool[pi];
            Node &cn = g.pool[ci];
            cn.nfloor = parent.nfloor;
            if (hpOn) cn.passed = parent.passed;
            // savescum: bc is the real fight (sk its tracker, observing every step), nothing is resampled or tested.
            const bool ss = g.savescum;
            const bool detect = cfg.chanceOnReveal && !resample && !ss;
            search::CombatKnowledgeState sk;
            bool inCombat = parent.combat, fromCombat = false;
            BattleContext bc;
            std::shared_ptr<const GameContext> outer;
            search::SilverSearchContext ctx;
            GameContext gc;
            int exits = 0;
            auto unsupportedLeaf = [&] {   // hidden history the resampler cannot handle: the parent's value
                ++wk.st.unsupported;
                cn.combat = false;
                cn.evaluated = cn.terminal = true;
                cn.value = parent.value;
                if (emaOn) cn.dist = parent.dist;
                copyHp(cn, parent);
            };
            // One out-of-combat step on gc, tested for hidden information on its own (a later step's new-floor reseed
            // must not hide an earlier draw).
            // searchEmaHp: a step that leaves the floor records the HP it left with (as the real run's closeFloor).
            auto noteFloor = [&] {
                if (gc.floorNum <= cn.nfloor) return;
                if (hpOn) cn.passed.insert(cn.passed.end(), static_cast<std::size_t>(gc.floorNum - cn.nfloor), static_cast<std::int16_t>(gc.curHp));
                cn.nfloor = gc.floorNum;
            };
            auto oocExec = [&](std::uint32_t b) {
                if (!detect) { execOoc(gc, b); noteFloor(); return; }
                const auto snap = search::captureOocHidden(gc);
                execOoc(gc, b);
                noteFloor();
                revealed = revealed || search::oocStepRevealsHidden(snap, gc);
            };
            // A combat step: under savescum on the real fight with its tracker observing.
            auto combatExec = [&](std::uint32_t b) {
                if (ss) executeObserved(bc, b, sk);
                else Action(b).execute(bc);
            };
            if (inCombat) {
                outer = parent.outer;
                ctx = parent.ctx;
                if (ss) {
                    if (!parent.hasReal) throw std::logic_error("run driver: savescum combat node without its real fight");
                    bc = *parent.real;
                    sk = *parent.kn;
                    // The edge's action is in the public view's indexing: mapped to the real fight (as the real run)
                    // when the node was requested (realBits; bc is a copy of parent.real).
                    if (!realOk) { unsupportedLeaf(); return; }
                    combatExec(realBits);
                } else {
                    bc = *parent.bc;
                    search::seedSearchRng(bc, base + k);
                    Action(bits).execute(bc);
                }
            } else {
                gc = search::detachedGameCopy(*parent.gc);
                if (!detect && !ss) {
                    std::mt19937_64 r(base + k);
                    try { search::sampleNoncombatFuture(gc, r); }
                    catch (const search::OocSearchUnsupported &) { unsupportedLeaf(); return; }
                }
                oocExec(bits);
            }
            for (int guard = 0;; ++guard) {
                if (guard > 4000) {   // a forced loop (stall guard): a loss on this floor
                    cn.combat = false;
                    cn.evaluated = cn.terminal = true;
                    const int fl = inCombat ? bc.floorNum : gc.floorNum;
                    cn.value = terminalUtility(false, false, fl, 0, 1, cfg.hpWeightOoc, cfg, false, g.pool[0].combat);
                    if (emaOn) { setOneHot(cn, std::clamp(fl, 1, kOutcomeClasses - 1)); setHpDeath(g, cn); }
                    return;
                }
                if (inCombat) {
                    if (bc.outcome == Outcome::PLAYER_LOSS) {
                        combatRng = !ss && (combatRng || search::searchRngCounter(bc) != 0);
                        cn.combat = true;
                        useBc(cn) = std::move(bc);
                        cn.evaluated = cn.terminal = true;
                        const int fl = outer ? outer->floorNum : g.gc.floorNum;
                        cn.value = terminalUtility(false, false, fl, 0, 1, cfg.hpWeightCombat, cfg, true, g.pool[0].combat);
                        if (emaOn) { setOneHot(cn, std::clamp(fl, 1, kOutcomeClasses - 1)); setHpDeath(g, cn); }   // death on this floor
                        return;
                    }
                    if (bc.outcome == Outcome::PLAYER_VICTORY) {
                        // The fight's exit (rewards) reads the hidden future of the game state of the fight's start.
                        combatRng = !ss && (combatRng || search::searchRngCounter(bc) != 0);
                        gc = search::detachedGameCopy(outer ? *outer : g.gc);
                        const auto snap = search::captureOocHidden(gc);
                        if (!detect && !ss) {
                            std::mt19937_64 r(base ^ kExitSalt ^ (static_cast<std::uint64_t>(k) + 1 +
                                                                 7919ull * static_cast<std::uint64_t>(exits)));
                            try { search::sampleNoncombatFuture(gc, r); }
                            catch (const search::OocSearchUnsupported &) { ++wk.st.unsupported; }
                        }
                        ++exits;
                        if (cfg.crossCombat) ++wk.st.treeFightExits;
                        bc.exitBattle(gc);
                        if (detect) revealed = revealed || search::oocStepRevealsHidden(snap, gc);
                        inCombat = false;
                        fromCombat = true;
                        outer.reset();
                        continue;
                    }
                    if (cfg.simHelp) {
                        const auto &a = combatActions(bc, ctx);
                        if (a.size() == 1) { combatExec(a[0].bits); continue; }
                    }
                    combatRng = !ss && (combatRng || search::searchRngCounter(bc) != 0);
                    cn.combat = true;
                    cn.ctx = ctx;
                    cn.outer = std::move(outer);
                    if (ss) {
                        if (!setReal(cn, bc, sk)) { ++wk.st.knowledgeFailures; unsupportedLeaf(); }
                    } else {
                        useBc(cn) = std::move(bc);
                    }
                    return;
                }
                if (gc.outcome != GameOutcome::UNDECIDED) {
                    setGc(cn, std::move(gc));
                    cn.evaluated = cn.terminal = true;
                    cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg, false, g.pool[0].combat);
                    if (emaOn) { setOneHot(cn, outcomeClass(*cn.gc)); setHpGameEnd(g, cn); }
                    return;
                }
                if (goldToTake(gc)) { oocExec(takeGoldBits); continue; }
                if (gc.screenState == ScreenState::BATTLE) {
                    // A fight starts (always a reveal: oocStepRevealsHidden): its public view, as at a real fight start.
                    search::CombatKnowledgeState kn;
                    BattleContext live;
                    initObservedBattle(gc, live, kn);
                    if (ss) {   // savescum: the real fight (live) and its tracker; its public view only as net input
                        bc = std::move(live);
                        sk = std::move(kn);
                    } else if (!publicCombatRoot(live, kn, bc).empty()) {
                        bc = live;
                    }
                    ctx = combatContext(gc, g.forceKeys);
                    if (!cfg.crossCombat) {   // the fight's first state is a leaf valued by the net
                        cn.combat = true;
                        cn.ctx = ctx;
                        cn.boundary = true;
                        if (ss) {
                            if (!setReal(cn, bc, sk)) { ++wk.st.knowledgeFailures; unsupportedLeaf(); }
                        } else {
                            useBc(cn) = std::move(bc);
                        }
                        return;
                    }
                    outer = std::make_shared<const GameContext>(std::move(gc));
                    ++wk.st.treeFightStarts;
                    inCombat = true;
                    continue;
                }
                if (cfg.simHelp) {
                    const auto a = oocActions(gc, g.forceKeys);
                    if (a.size() == 1) { oocExec(a[0].bits); continue; }
                }
                setGc(cn, std::move(gc));
                cn.boundary = fromCombat && !cfg.crossCombat;   // the state after a won fight: a leaf unless crossCombat
                return;
            }
        };

        auto resetNode = [&](Node &n) {
            n.edges.clear();
            n.dist.clear();
            n.outer.reset();
            n.evaluated = n.terminal = n.boundary = false;
            n.inFlight = false;
            n.combat = false;
            n.value = 0;
            n.n = 0;
            n.w = 0;
        };

        // expand() under Amber's rules. chanceOnReveal: the first visit steps with the real hidden state; if the step
        // revealed hidden information it is redone as a resampled outcome and the edge becomes a chance edge (DPW).
        auto expandAmber = [&](Run &g, int cur, int e, int &outcome) -> int {
            outcome = -1;
            Edge &edge0 = g.pool[cur].edges[e];
            const bool first = !edge0.tried;
            if (!first && !edge0.chance) return edge0.child;
            if (!first) {
                const int visits = edge0.n + edge0.vn;   // vn: simulations in flight (parallelNodes), else 0
                const int cap = static_cast<int>(std::ceil(cfg.wideningC * std::pow(visits + 1.0, cfg.wideningAlpha)));
                if (static_cast<int>(edge0.outcomes.size()) >= cap) {
                    outcome = static_cast<int>(visits % edge0.outcomes.size());
                    return edge0.outcomes[outcome];
                }
            }
            const int child = newNode(g);   // pool may not move (capacity reserved), references stay valid
            Node &parent = g.pool[cur];
            Edge &edge = parent.edges[e];
            const int k = static_cast<int>(edge.outcomes.size());
            if (first) edge.base = !parent.combat ? wk.rng()
                                 : parent.hasReal ? parent.rbase : search::searchRandomnessBase(*parent.bc);
            bool combatRng = false, revealed = false;
            if (g.savescum) {   // the real step: one deterministic child
                stepAmber(g, cur, edge.bits, edge.base, k, false, child, combatRng, revealed, edge.realBits, edge.realOk);
                edge.chance = false;
            } else if (first && cfg.chanceOnReveal) {
                stepAmber(g, cur, edge.bits, edge.base, k, false, child, combatRng, revealed, edge.realBits, edge.realOk);
                if (revealed) {
                    resetNode(g.pool[child]);
                    bool c2 = false, r2 = false;
                    stepAmber(g, cur, edge.bits, edge.base, k, true, child, c2, r2, edge.realBits, edge.realOk);
                }
                edge.chance = revealed || combatRng;
                if (!parent.combat) ++wk.st.oocEdgeKinds[edge.chance ? 1 : 0];
            } else {
                stepAmber(g, cur, edge.bits, edge.base, k, true, child, combatRng, revealed, edge.realBits, edge.realOk);
                if (first) edge.chance = parent.combat ? combatRng : true;
            }
            if (edge.chance) {
                edge.outcomes.push_back(child);
                edge.outcomeN.push_back(0);
                outcome = static_cast<int>(edge.outcomes.size()) - 1;
            } else {
                edge.child = child;
            }
            edge.tried = true;
            return child;
        };
        // savescum (a per-run state, initially cfg.savescum) also takes the Amber path (advance: || g.savescum), so a
        // fair search after the switch-off is the same as in a process started without savescum.
        const bool amberRules = cfg.chanceOnReveal || cfg.crossCombat || cfg.simHelp;

        // One simulation from the root through its edge `forced`. BACKED: it ended in a leaf that needs no net (backed
        // up). REQUESTED: its leaf's evaluation is in flight (backed up when the answer is handled). COLLIDED
        // (parallelNodes only): it reached a node whose evaluation is in flight; nothing changed, it is tried again
        // once that answer is in.
        enum class Sim { BACKED, REQUESTED, COLLIDED };
        const bool parallel = cfg.parallelNodes > 0;
        std::vector<PathStep> simPath;
        auto simulate = [&](Run &g, int gi, int forced) -> Sim {
            simPath.clear();
            int cur = 0, e = forced;
            while (true) {
                int outcome;
                const double t0 = cpuSeconds();
                const int child = amberRules || g.savescum ? expandAmber(g, cur, e, outcome) : expand(g, cur, e, outcome);
                wk.st.stepCpu += cpuSeconds() - t0;
                Node &cn = g.pool[child];
                if (!cn.evaluated && cn.inFlight) return Sim::COLLIDED;   // an existing child: expand made no node
                simPath.push_back({cur, e, outcome});
                simPath.push_back({child, -1, -1});
                if (!cn.evaluated) {
                    Flight &f = newFlight(g);
                    f.path = simPath;
                    if (parallel)   // virtual losses along the path until the answer is backed up
                        for (const auto &p : f.path)
                            if (p.edge >= 0) ++g.pool[p.node].edges[p.edge].vn;
                    request(g, gi, child, f);
                    return Sim::REQUESTED;
                }
                if (cn.terminal || cn.boundary || cn.edges.empty()) {
                    if (cn.terminal) ++wk.st.terminalLeaves;
                    backup(g, simPath, cn.value);
                    return Sim::BACKED;
                }
                simPath.pop_back();
                cur = child;
                e = selectNonRoot(cn, cfg);
            }
        };

        // Runs the move's search on until an evaluation is in flight or the move is played. parallelNodes = P > 0
        // (Amber Eye: "up to 4 nodes per candidate move's subtree were allowed to be visited in parallel"): a wave of
        // the phase's simulations starts together, at most P in flight per root candidate (a root edge's virtual
        // losses count them); the wave's answers are handled together, in the order the simulations started, so a
        // search does not depend on the order in which answers arrive.
        std::vector<int> blocked;
        auto advance = [&](Run &g, int gi) {
            while (true) {
                if (g.phaseQueue.empty()) {
                    if (g.spent > 0 && g.cand.size() > 1 && g.phasesLeft > 0) halve(g);
                    if (g.spent >= g.budget || g.cand.size() <= 1) { finishMove(g, gi); return; }
                    fillPhase(g);
                }
                if (!parallel) {
                    const int forced = g.phaseQueue.back();
                    g.phaseQueue.pop_back();
                    if (simulate(g, gi, forced) == Sim::REQUESTED) return;
                    continue;
                }
                Node &root = g.pool[0];
                blocked.clear();
                bool progressed = false;
                // In the order of the one-at-a-time search (from the back); what cannot start now stays queued.
                for (int i = static_cast<int>(g.phaseQueue.size()) - 1; i >= 0; --i) {
                    const int c = g.phaseQueue[i];
                    if (root.edges[c].vn >= cfg.parallelNodes || g.nFlights >= kMaxFlights
                        || std::find(blocked.begin(), blocked.end(), c) != blocked.end()) continue;
                    const Sim r = simulate(g, gi, c);
                    if (r == Sim::COLLIDED) { ++wk.st.simCollisions; blocked.push_back(c); continue; }
                    g.phaseQueue[i] = -1;
                    progressed = true;
                }
                g.phaseQueue.erase(std::remove(g.phaseQueue.begin(), g.phaseQueue.end(), -1), g.phaseQueue.end());
                if (g.nFlights > 0) { ++wk.st.waves; wk.st.waveFlights += g.nFlights; return; }
                // Nothing in flight: every started simulation ended without the net (and nothing can collide).
                if (!progressed) throw std::logic_error("run driver: parallel search cannot progress");
            }
        };

        const double s0 = cpuSeconds();
        for (int gi = 0; gi < static_cast<int>(wk.runs.size()); ++gi) startRun(wk.runs[gi], gi);
        wk.st.searchCpu += cpuSeconds() - s0;

        while (!stop_.load(std::memory_order_relaxed)) {
            if (!outbox.empty()) {
                {
                    std::lock_guard<std::mutex> l(qm_);
                    queue_.insert(queue_.end(), outbox.begin(), outbox.end());
                }
                qcv_.notify_all();
                outbox.clear();
            }
            {
                std::lock_guard<std::mutex> l(wk.im);
                ready.swap(wk.inbox);
            }
            ready.insert(ready.end(), wk.hits.begin(), wk.hits.end());   // cache answers of the last round
            wk.hits.clear();
            if (ready.empty()) std::this_thread::sleep_for(std::chrono::microseconds(50));
            const double t0 = cpuSeconds();
            for (int code : ready) {
                const int gi = code & 0xffff;
                Run &g = wk.runs[gi];
                // The run's answers are handled together once all are in, in the order their simulations started (one
                // flight without parallelNodes).
                if (--g.waiting > 0) continue;
                const int flights = g.nFlights;
                for (int slot = 0; slot < flights; ++slot) {
                    Flight &fl = *g.fl[slot];
                    Node &n = g.pool[fl.node];
                    const double H = usesAmberH(cfg.utility)
                                         ? amberH(fl.floor, fl.resHpf.data())
                                         : std::clamp(static_cast<double>(fl.resEhp) / fl.maxHp, 0.0, 1.0);
                    n.evaluated = true;
                    n.inFlight = false;
                    if (isAmber2(cfg.utility)) {   // AMBER2: the leaf state's kind; AMBER2_ROOT: the search root's
                        n.value = static_cast<float>(amber2Value(cfg.utility == Utility::AMBER2_ROOT ? g.pool[0].combat : fl.combat, fl.resF, fl.resDist[0], H));
                    } else {
                        const double w = fl.combat ? cfg.hpWeightCombat : cfg.hpWeightOoc;
                        n.value = static_cast<float>((std::clamp<double>(fl.resF, 0.0, 1.0) + w * H) / (1.0 + w));
                    }
                    for (std::size_t k = 0; k < n.edges.size() && k < fl.resLogits.size(); ++k) n.edges[k].logit = fl.resLogits[k];
                    if (emaOn) n.dist.assign(fl.resDist.begin(), fl.resDist.end());
                    if (hpOn) setHpEval(g, n, fl);
                    if (fl.hit) {
                        fl.hit = false;
                    } else {
                        ++wk.st.evals;
                        // Only results of the cache's weights version go in (a batch evaluated before the last
                        // weights change carries the old version).
                        if (cfg.evalCache && fl.resVersion == g.cacheVersion) {
                            if (static_cast<int>(g.cache.size()) >= cfg.evalCacheCap) g.cache.clear();
                            auto &e = g.cache[fl.hash];
                            e.F = fl.resF;
                            e.ehp = fl.resEhp;
                            e.nAct = fl.tokens.nAct;
                            e.logits = fl.resLogits;
                            if (usesAmberH(cfg.utility)) e.hpf.assign(fl.resHpf.begin(), fl.resHpf.end());
                            if (emaOn || isAmber2(cfg.utility)) e.dist.assign(fl.resDist.begin(), fl.resDist.end());
                            if (hpOn) e.hpd = fl.resHpd;
                        }
                    }
                    if (fl.node == 0) {   // the root's evaluation (always alone in flight)
                        if (g.keep) {
                            g.cur = Sample{};
                            if (cfg.compactSamples) flattenInto(fl.tokens, g.cur, &g.dict, &g.dictIndex);
                            else flattenInto(fl.tokens, g.cur);
                            g.cur.combat = g.inBattle ? 1 : 0;
                            g.cur.maxHp = static_cast<std::int16_t>(g.inBattle ? g.bc.player.maxHp : g.gc.maxHp);
                            g.cur.floor = static_cast<std::int16_t>(g.gc.floorNum);
                            g.cur.run = g.seed;
                            if (cfg.auxFights && !g.inBattle) auxFightStarts(g, g.cur);
                        }
                        g.pool[0].n = 1;
                        g.pool[0].w = n.value;
                        if (emaOn) g.rootDist.assign(n.dist.begin(), n.dist.end());
                        if (hpOn) {
                            g.rootHpd.assign(kHpClasses, 0.0);
                            g.rootHpf.assign(kFloors, 0.0);
                            addHp(g, n);
                        }
                        initRoot(g);
                    } else {
                        backup(g, fl.path, n.value, parallel);
                    }
                }
                g.nFlights = 0;
                advance(g, gi);
            }
            ready.clear();
            wk.st.searchCpu += cpuSeconds() - t0;
            if (t0 - lastPublish > 0.05) {
                if (t0 - lastMem > 1.0) { memGauges(); lastMem = t0; }
                std::lock_guard<std::mutex> l(wk.sm);
                wk.published = wk.st;
                lastPublish = t0;
            }
        }
        std::lock_guard<std::mutex> l(wk.sm);
        wk.published = wk.st;
    }

    std::vector<std::uint32_t> RunDriver::takeRequests(int maxRows, int minRows, int timeoutMs) {
        std::vector<std::uint32_t> take;
        std::unique_lock<std::mutex> l(qm_);
        qcv_.wait_for(l, std::chrono::milliseconds(timeoutMs),
                      [&] { return stop_.load() || static_cast<int>(queue_.size()) >= minRows; });
        const int n = std::min<int>(maxRows, static_cast<int>(queue_.size()));
        take.assign(queue_.begin(), queue_.begin() + n);
        queue_.erase(queue_.begin(), queue_.begin() + n);
        return take;
    }

    bool RunDriver::waitRequests(int minRows, int timeoutUs) {
        std::unique_lock<std::mutex> l(qm_);
        qcv_.wait_for(l, std::chrono::microseconds(timeoutUs),
                      [&] { return stop_.load() || static_cast<int>(queue_.size()) >= minRows; });
        return static_cast<int>(queue_.size()) >= minRows;
    }

    std::vector<std::uint32_t> RunDriver::nextBatchFlat(int maxRows, int minRows, int timeoutMs,
                                                        const std::vector<int> &rowBuckets,
                                                        const std::vector<int> &tokBuckets,
                                                        const std::vector<int> &actBuckets, const FlatBuffers &buf,
                                                        FlatShape &shape, int packThreads) {
        std::vector<std::uint32_t> take = takeRequests(maxRows, minRows, timeoutMs);
        shape = {};
        if (take.empty()) return take;
        const auto tPack = std::chrono::steady_clock::now();
        packFlat(static_cast<int>(take.size()),
                 [&](int r) -> const AmberTokens & {
                     return workers_[ticketWorker(take[r])]->runs[ticketRun(take[r])].fl[ticketSlot(take[r])]->tokens;
                 },
                 rowBuckets, tokBuckets, actBuckets, buf, shape, packThreads);
        batches_ += 1;
        batchRows_ += shape.rows;
        packNs_ += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - tPack)
                       .count();
        return take;
    }

    void RunDriver::submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *F,
                           const float *ehp, const float *hpf, std::uint32_t version, const float *dist,
                           const float *hpDist) {
        if (cfg_.searchEmaHp && !hpDist)
            throw std::invalid_argument("run driver: searchEmaHp needs floor HP distributions (hpDist)");
        if (usesAmberH(cfg_.utility) && !hpf)
            throw std::invalid_argument("run driver: utility AMBER needs per-floor HP results (hpf)");
        if (cfg_.searchEmaLambda > 0 && !dist)
            throw std::invalid_argument("run driver: searchEmaLambda > 0 needs outcome distributions (dist)");
        if (isAmber2(cfg_.utility) && !dist)
            throw std::invalid_argument("run driver: utility AMBER2 needs outcome distributions (dist, P(win))");
        thread_local std::vector<std::vector<int>> per;
        per.assign(workers_.size(), {});
        for (int r = 0; r < rows; ++r) {
            const std::uint32_t t = tickets[r];
            // The flight is this ticket's alone until its answer is in the worker's inbox (Run::fl does not change
            // while a request of the run is out).
            Flight &g = *workers_[ticketWorker(t)]->runs[ticketRun(t)].fl[ticketSlot(t)];
            const int na = std::min(g.tokens.nAct, actions);
            g.resLogits.assign(logits + static_cast<std::size_t>(r) * actions,
                               logits + static_cast<std::size_t>(r) * actions + na);
            g.resF = F[r];
            g.resEhp = ehp[r];
            g.resVersion = version;
            if (hpf) std::copy(hpf + static_cast<std::size_t>(r) * kFloors, hpf + static_cast<std::size_t>(r + 1) * kFloors,
                               g.resHpf.begin());
            if (dist) std::copy(dist + static_cast<std::size_t>(r) * kOutcomeClasses,
                                dist + static_cast<std::size_t>(r + 1) * kOutcomeClasses, g.resDist.begin());
            if (cfg_.searchEmaHp) g.resHpd.assign(hpDist + static_cast<std::size_t>(r) * kHpClasses,
                                                  hpDist + static_cast<std::size_t>(r + 1) * kHpClasses);
            per[ticketWorker(t)].push_back(static_cast<int>(t & ((1u << (kTicketRunBits + kTicketSlotBits)) - 1)));
        }
        for (std::size_t w = 0; w < per.size(); ++w) {
            if (per[w].empty()) continue;
            std::lock_guard<std::mutex> l(workers_[w]->im);
            auto &in = workers_[w]->inbox;
            in.insert(in.end(), per[w].begin(), per[w].end());
        }
    }

}
