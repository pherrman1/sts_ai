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

        search::SilverSearchContext combatContext(const GameContext &gc) {
            search::SilverSearchContext c;
            c.act = gc.act;
            c.actBossRoom = gc.curRoom == Room::BOSS;
            c.eliteRewards = gc.isEliteTriggerCombat();
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
        double w = 0;
        int child = -1;                  // decision child (deterministic combat edge)
        bool chance = false, tried = false;
        std::uint64_t base = 0;          // chance: randomness base
        std::vector<int> outcomes;
        std::vector<std::int32_t> outcomeN;
    };

    struct RunDriver::Node {
        Node() = default;
        Node(Node &&) noexcept = default;
        Node &operator=(Node &&) noexcept = default;
        bool combat = false;
        BattleContext bc;                    // combat node
        search::SilverSearchContext ctx;     // combat node: its fight
        std::unique_ptr<GameContext> gc;     // out-of-combat node (kept allocated across pool reuse)
        std::shared_ptr<const GameContext> outer;   // combat node, crossCombat: the game state at its fight's start
        std::vector<Edge> edges;
        bool evaluated = false, terminal = false, boundary = false;
        float value = 0;
        std::int32_t n = 0;
        double w = 0;
        std::vector<float> dist;             // searchEmaLambda > 0: outcome distribution of the node's value [57]
        // savescum combat node: the real fight (bc is its public view) and its knowledge tracker (kept allocated
        // across pool reuse; valid while hasReal).
        bool hasReal = false;
        std::unique_ptr<BattleContext> real;
        std::unique_ptr<search::CombatKnowledgeState> kn;
    };

    struct PathStep { int node; int edge; int outcome; };

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
        std::vector<PathStep> path;
        int pendingNode = -1;
        bool pendingCombat = false;
        float pendingMaxHp = 1;
        AmberTokens tokens;
        std::vector<float> resLogits;
        float resF = 0, resEhp = 0;
        std::uint32_t resVersion = 0;        // weights version of the result (submit)
        // Evaluation cache (RunConfig::evalCache): input hash -> result, all of weights version cacheVersion; emptied
        // at the start of each run, on a weights change and when full.
        struct CacheEntry { float F = 0, ehp = 0; int nAct = 0; std::vector<float> logits, hpf, dist; };   // hpf: utility AMBER; dist: searchEmaLambda > 0
        std::unordered_map<std::uint64_t, CacheEntry> cache;
        std::uint32_t cacheVersion = 0;
        std::uint64_t pendingHash = 0;
        bool pendingHit = false;             // the pending leaf was answered by the cache
        std::array<float, kFloors> resHpf{};   // utility AMBER: E[HP_f] / 255 of the pending leaf
        std::array<float, kOutcomeClasses> resDist{};   // searchEmaLambda > 0: outcome softmax of the pending leaf
        std::vector<double> rootDist;          // searchEmaLambda > 0: sum of the backed-up distributions at the root
        std::vector<std::uint16_t> moveDist;   // ... search result of each chain move of the run [M][57], float16
        int pendingFloor = 0;                  // floor of the pending leaf
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
        std::vector<int> inbox;
        std::vector<int> hits;               // runs whose pending leaf the cache answered (handled like results)
        std::mt19937_64 rng;
        RunStats st;
        mutable std::mutex sm;
        RunStats published;
    };

    namespace {

        double q01(const Edge &e, double fallback) { return e.n ? e.w / e.n : fallback; }

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
            for (int i = 0; i < k; ++i) { logit[i] = node.edges[i].logit; n[i] = node.edges[i].n; w[i] = node.edges[i].w; }
            completedQValues(k, logit.data(), n.data(), w.data(), node.value, true, q.data());
        }

        int maxVisits(const RunDriver::Node &node) {
            int maxN = 0;
            for (const auto &e : node.edges) maxN = std::max(maxN, static_cast<int>(e.n));
            return maxN;
        }

        int selectNonRoot(const RunDriver::Node &node, const RunConfig &cfg) {
            const int k = static_cast<int>(node.edges.size());
            double sumN = 0;
            for (const auto &e : node.edges) sumN += e.n;
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
                const double sc = s[i] / z - node.edges[i].n / (1.0 + sumN);
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
        float terminalUtility(bool win, bool alive, int floor, int hp, int maxHp, double w, const RunConfig &cfg) {
            const double F = win ? 1.0 : std::clamp(floor, 1, kOutcomeClasses - 1) / 57.0;
            double H;
            if (cfg.utility == Utility::AMBER) H = amberTerminalH(win, alive, floor, hp);
            else H = (win || (alive && cfg.keylessHp)) ? std::clamp(static_cast<double>(hp) / std::max(1, maxHp), 0.0, 1.0) : 0.0;
            return static_cast<float>((F + w * H) / (1.0 + w));
        }

        float terminalUtility(const GameContext &gc, double w, const RunConfig &cfg) {
            return terminalUtility(heartWin(gc), heartWin(gc) || keylessVictory(gc), gc.floorNum, gc.curHp, gc.maxHp,
                                   w, cfg);
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
        std::vector<GameAction> kept;
        kept.reserve(before);
        for (const auto &a : v)
            if (search::heartKeyActionAllowed(gc, true, a)) kept.push_back(a);
        if (kept.empty() || kept.size() == before) return -1;
        v.swap(kept);
        return 3;
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
            it.c = amberExploreC(it.hist, cfg_.pickTarget * static_cast<double>(games), cfg_.exploreT);
            it.stamp = games;
        }
        return it.c;
    }

    RunDriver::RunDriver(RunConfig cfg) : cfg_(cfg) {
        if (cfg_.ascension < 0 || cfg_.ascension >= kAscensions) throw std::invalid_argument("run driver: ascension 0..20");
        ascension_.store(cfg_.ascension);
        setForceKeys(cfg_.forceKeys);
        savescum_.store(cfg_.savescum);
        picks_.reset(new std::atomic<std::uint32_t>[kPickBuckets]);
        for (int i = 0; i < kPickBuckets; ++i) picks_[i].store(0);
        if (!cfg_.encodeCombat) cfg_.encodeCombat = search::amberEncodeCombat;
        if (!cfg_.encodeGame) cfg_.encodeGame = search::amberEncodeGame;
        if (cfg_.utility != Utility::FLOOR_HP && cfg_.utility != Utility::AMBER)
            throw std::invalid_argument("run driver: utility 0 (floor HP) or 1 (Amber)");
        if (!(cfg_.searchEmaLambda >= 0 && cfg_.searchEmaLambda < 1))
            throw std::invalid_argument("run driver: searchEmaLambda in [0, 1)");
        if (cfg_.gamesPerWorker > 0xffff) throw std::invalid_argument("run driver: at most 65535 runs per worker");
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
            for (int k = 0; k < 2; ++k) {
                s.oocSearched[k] += p.oocSearched[k]; s.oocNotBestQ[k] += p.oocNotBestQ[k];
                s.oocSpreadN[k] += p.oocSpreadN[k]; s.oocSpreadSum[k] += p.oocSpreadSum[k];
            }
            s.oocEdgeKinds[0] += p.oocEdgeKinds[0]; s.oocEdgeKinds[1] += p.oocEdgeKinds[1];
            s.treeFightStarts += p.treeFightStarts; s.treeFightExits += p.treeFightExits; s.autoGold += p.autoGold;
            s.savescumRuns += p.savescumRuns; s.savescumChecks += p.savescumChecks; s.savescumMismatches += p.savescumMismatches;
            for (int k = 0; k < 3; ++k) s.forcedKeys[k] += p.forcedKeys[k];
            s.keyRouteMasked += p.keyRouteMasked;
            if (p.heartHpMin >= 0 && (s.heartHpMin < 0 || p.heartHpMin < s.heartHpMin)) s.heartHpMin = p.heartHpMin;
            s.memPoolNodes += p.memPoolNodes; s.memPoolGc += p.memPoolGc; s.memPoolReal += p.memPoolReal;
            s.memPoolOuter += p.memPoolOuter; s.memPendingCap += p.memPendingCap; s.memMoveDistCap += p.memMoveDistCap;
            s.memCacheEntries += p.memCacheEntries;
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
        auto memGauges = [&] {
            RunStats &st = wk.st;
            st.memPoolNodes = st.memPoolGc = st.memPoolReal = st.memPoolOuter = 0;
            st.memPendingCap = st.memMoveDistCap = st.memCacheEntries = 0;
            for (const Run &g : wk.runs) {
                st.memPoolNodes += static_cast<std::int64_t>(g.pool.size());
                for (const Node &n : g.pool) {
                    st.memPoolGc += n.gc != nullptr;
                    st.memPoolReal += n.real != nullptr;
                    st.memPoolOuter += n.outer != nullptr;
                }
                st.memPendingCap += static_cast<std::int64_t>(g.pending.capacity());
                st.memMoveDistCap += static_cast<std::int64_t>(g.moveDist.capacity());
                st.memCacheEntries += static_cast<std::int64_t>(g.cache.size());
            }
        };

        auto combatActions = [&](const BattleContext &bc) -> const std::vector<Action> & {
            if (!enumerator) enumerator = std::make_unique<search::SilverSearcher>(bc, search::SilverSearchContext{});
            cacts = enumerator->enumerateActions(bc);
            return cacts;
        };

        // Legal out-of-combat actions; simHelp bans buying Prismatic Shard (Amber Eye's simulator); forceKeys (the
        // run's state) applies the key backstops (keyBackstopActions; its result in *keyRule when given).
        // Singing Bowl actions (appendSingingBowlActions); STS_AZ_SINGING_BOWL=0 restores the old action list.
        const char *bowlEnv = std::getenv("STS_AZ_SINGING_BOWL");
        const bool singingBowl = !(bowlEnv && std::strcmp(bowlEnv, "0") == 0);
        auto oocActions = [&](const GameContext &gc, bool forceKeys, int *keyRule = nullptr) -> std::vector<GameAction> {
            auto v = GameAction::getAllActionsInState(gc);
            if (singingBowl) appendSingingBowlActions(gc, v);
            if (cfg.simHelp)
                v.erase(std::remove_if(v.begin(), v.end(), [&](const GameAction &a) {
                    return !search::isSupportedAutonomousOocAction(gc, a);
                }), v.end());
            const int rule = forceKeys ? keyBackstopActions(gc, v) : -1;
            if (keyRule) *keyRule = rule;
            return v;
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
            n.hasReal = false;
            return g.poolUsed++;
        };
        auto setGc = [](Node &n, GameContext &&gc) {
            n.combat = false;
            if (n.gc) *n.gc = std::move(gc);
            else n.gc = std::make_unique<GameContext>(std::move(gc));
        };
        // savescum: a combat node holds the real fight and its tracker; n.bc is their public view (net input, action
        // list). False when the view cannot be built.
        auto setReal = [](Node &n, const BattleContext &real, const search::CombatKnowledgeState &kn) {
            if (n.real) *n.real = real;
            else n.real = std::make_unique<BattleContext>(real);
            if (n.kn) *n.kn = kn;
            else n.kn = std::make_unique<search::CombatKnowledgeState>(kn);
            n.hasReal = true;
            return publicCombatRoot(*n.real, *n.kn, n.bc).empty();
        };

        // Request a net evaluation of node ni (enumerates its actions, encodes it, queues it).
        auto request = [&](Run &g, int gi, int ni) {
            Node &node = g.pool[ni];
            const double t0 = cpuSeconds();
            if (node.combat) {
                const auto &acts = combatActions(node.bc);
                node.edges.resize(acts.size());
                for (std::size_t k = 0; k < acts.size(); ++k) node.edges[k] = Edge{acts[k].bits};
                const double t1 = cpuSeconds();
                cfg.encodeCombat(node.bc, node.ctx, acts, g.tokens);
                if (cfg.mergeCards) search::amberMergeCards(g.tokens);
                wk.st.stepCpu += t1 - t0;
                wk.st.encodeCpu += cpuSeconds() - t1;
                g.pendingCombat = true;
                g.pendingMaxHp = static_cast<float>(std::max<int>(1, node.bc.player.maxHp));
                g.pendingFloor = node.bc.floorNum;
            } else {
                gacts = oocActions(*node.gc, g.forceKeys);
                node.edges.resize(gacts.size());
                for (std::size_t k = 0; k < gacts.size(); ++k) node.edges[k] = Edge{gacts[k].bits};
                const double t1 = cpuSeconds();
                cfg.encodeGame(*node.gc, gacts, g.tokens);
                if (cfg.mergeCards) search::amberMergeCards(g.tokens);
                if (ni == 0 && (cfg.exploreC > 0 || cfg.exploreAmber)) {
                    // Pick-rate items of the root's actions: hash of the source token's ids.
                    g.rootKeys.assign(gacts.size(), -1);
                    for (int k = 0; k < g.tokens.nAct; ++k) {
                        const auto &a = g.tokens.act[k];
                        const auto t = static_cast<search::AmberActionType>(a.type);
                        if ((t != search::AmberActionType::CHOOSE_CARD && t != search::AmberActionType::CHOOSE_OPTION)
                            || a.srcSeg == search::kAmberNoSeg) continue;
                        const auto &tok = g.tokens.at(static_cast<AmberTokenType>(a.srcSeg), a.srcIdx);
                        std::uint64_t h = 0x9e3779b97f4a7c15ull * (a.type + 1);
                        for (int c = 0; c < 2; ++c) h = (h ^ static_cast<std::uint16_t>(tok.ids[c])) * 0x100000001b3ull;
                        // The OPTION kind one-hot and option index (f 12-51): event / rest options are separate items.
                        if (static_cast<AmberTokenType>(a.srcSeg) == AmberTokenType::OPTION)
                            for (int c = 12; c < 52; ++c) h = (h ^ tok.f[c]) * 0x100000001b3ull;
                        h ^= h >> 29;
                        g.rootKeys[k] = static_cast<int>(h & (kPickBuckets - 1));
                    }
                }
                wk.st.stepCpu += t1 - t0;
                wk.st.encodeCpu += cpuSeconds() - t1;
                g.pendingCombat = false;
                g.pendingMaxHp = static_cast<float>(std::max(1, node.gc->maxHp));
                g.pendingFloor = node.gc->floorNum;
            }
            (node.combat ? wk.st.encodeCut : wk.st.encodeCutOoc) += g.tokens.cut;
            g.pendingNode = ni;
            g.pendingHit = false;
            if (cfg.evalCache) {
                const std::uint32_t v = weightsVersion_.load(std::memory_order_acquire);
                if (g.cacheVersion != v) { g.cache.clear(); g.cacheVersion = v; }
                g.pendingHash = inputHash(g.tokens);
                const auto it = g.cache.find(g.pendingHash);
                if (it != g.cache.end() && it->second.nAct == g.tokens.nAct) {
                    // Answered as a result would be, in the worker loop's next round (no recursion into advance).
                    g.resLogits = it->second.logits;
                    g.resF = it->second.F;
                    g.resEhp = it->second.ehp;
                    if (!it->second.hpf.empty()) std::copy(it->second.hpf.begin(), it->second.hpf.end(), g.resHpf.begin());
                    if (!it->second.dist.empty()) std::copy(it->second.dist.begin(), it->second.dist.end(), g.resDist.begin());
                    g.pendingHit = true;
                    ++wk.st.cacheHits;
                    wk.hits.push_back(gi);
                    return;
                }
            }
            outbox.push_back(static_cast<std::uint32_t>(wi) << 16 | static_cast<std::uint32_t>(gi));
        };

        const bool emaOn = cfg.searchEmaLambda > 0;
        auto backup = [&](Run &g, float v) {
            if (emaOn) {   // the leaf (last path entry) adds its distribution to the root's sum
                const Node &leaf = g.pool[g.path.back().node];
                if (leaf.dist.size() != static_cast<std::size_t>(kOutcomeClasses))
                    throw std::logic_error("run driver: leaf without an outcome distribution");
                for (int k = 0; k < kOutcomeClasses; ++k) g.rootDist[k] += leaf.dist[k];
            }
            for (const auto &p : g.path) {
                Node &n = g.pool[p.node];
                n.n += 1;
                n.w += v;
                if (p.edge >= 0) {
                    Edge &e = n.edges[p.edge];
                    e.n += 1;
                    e.w += v;
                    if (p.outcome >= 0) e.outcomeN[p.outcome] += 1;
                }
            }
            g.path.clear();
            ++g.spent;
        };

        // Labels of the current floor's samples once the floor is left (or the run ends).
        auto closeFloor = [&](Run &g, int hpEnd) {
            for (std::size_t i = g.floorStart; i < g.pending.size(); ++i) g.pending[i].hpEnd = static_cast<std::int16_t>(hpEnd);
            g.floorStart = g.pending.size();
            if (g.floor >= 1 && g.floor <= kFloors) g.floorHp[g.floor] = static_cast<std::int16_t>(hpEnd);
        };

        std::function<void(Run &, int)> startMove;

        auto enterBattle = [&](Run &g) {
            initObservedBattle(g.gc, g.bc, *g.knowledge);
            g.ctx = combatContext(g.gc);
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
            g.gc = GameContext(CharacterClass::IRONCLAD, seed, g.asc);
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
            const bool alive = win || (keylessVictory(g.gc) && (cfg.keylessHp || cfg.utility == Utility::AMBER));
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
            if (cfg.utility == Utility::AMBER) {
                // Floors skipped without a record (a floor counter jump) take the HP of the next recorded floor.
                for (int f = std::min(kFloors, std::max(1, g.floor)) - 1; f >= 1; --f)
                    if (g.floorHp[f] < 0) g.floorHp[f] = g.floorHp[f + 1];
                const int tail = win ? g.gc.curHp : 0;
                for (auto &s : g.pending) {
                    s.hpFloor.resize(kFloors);
                    amberFloorLabels(s.floor, g.floorHp.data(), tail, s.hpFloor.data());
                }
            }
            if (cfg.exploreAmber) {   // the run's items: once per run in the rate, smallest gap into the item's log
                for (int key : g.pickedKeys) picks_[key].fetch_add(1, std::memory_order_relaxed);
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
        auto applyReal = [&](Run &g, std::uint32_t bits) {
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
                    switch (g.gc.screenState) {
                        case ScreenState::TREASURE_ROOM:
                            ++p.chests;
                            if (a.getIdx1() != 0) ++p.chestsSkipped;
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

        startMove = [&](Run &g, int gi) {
            // Moves with one legal action (or none) are played without a search.
            while (true) {
                if (!g.active) return;
                if (g.gc.outcome != GameOutcome::UNDECIDED) { endRun(g, gi); return; }
                std::size_t legal;
                std::uint32_t only = 0;
                if (g.inBattle) {
                    const auto &a = combatActions(g.bc);
                    legal = a.size();
                    if (legal == 1) only = a[0].bits;
                } else {
                    if (goldToTake(g.gc)) { ++wk.st.autoGold; applyReal(g, takeGoldBits); continue; }
                    int keyRule = -1;
                    gacts = oocActions(g.gc, g.forceKeys, &keyRule);
                    if (keyRule >= 0 && keyRule < 3) ++wk.st.forcedKeys[keyRule];
                    else if (keyRule == 3) ++wk.st.keyRouteMasked;
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
            g.path.clear();
            const int r = newNode(g);
            Node &root = g.pool[r];
            if (g.inBattle) {
                root.combat = true;
                root.ctx = g.ctx;
                root.outer = g.fightOuter;   // crossCombat only (null otherwise)
                const bool view = g.savescum ? setReal(root, g.bc, *g.knowledge)
                                             : publicCombatRoot(g.bc, *g.knowledge, root.bc).empty();
                if (!view) {
                    // No fair view of this fight (an intent pattern the tracker cannot represent): abandon the run.
                    ++wk.st.knowledgeFailures;
                    g.poolUsed = 0;
                    g.path.clear();
                    g.gc.outcome = GameOutcome::PLAYER_LOSS;
                    g.inBattle = false;
                    endRun(g, gi);
                    return;
                }
            } else {
                setGc(root, search::detachedGameCopy(g.gc));
            }
            g.path.push_back({r, -1, -1});
            g.rootKeys.clear();
            g.rootUnder.clear();
            request(g, gi, r);
            if (!g.inBattle && (cfg.exploreC > 0 || cfg.exploreAmber)) {
                ++wk.st.oocRoots;
                const double games = static_cast<double>(runsDone_.load(std::memory_order_relaxed));
                bool under = false;
                // Rates are over finished runs, after a warm-up of 1 / pickTarget runs (no item is under target before).
                if (games * cfg.pickTarget >= 1.0) {
                    if (cfg.exploreAmber) g.rootUnder.assign(g.rootKeys.size(), 0);
                    for (std::size_t k = 0; k < g.rootKeys.size(); ++k) {
                        const int key = g.rootKeys[k];
                        if (key >= 0 && picks_[key].load(std::memory_order_relaxed) < cfg.pickTarget * games) {
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
                const bool warm = runsDone_.load(std::memory_order_relaxed) * cfg.pickTarget >= 1.0;
                const double games = static_cast<double>(runsDone_.load(std::memory_order_relaxed));
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
                // Gap in policy logits (the net's prior logits) below the search's pick, at least 1e-9.
                const int searchPick = pick;
                const double top = root.edges[searchPick].logit;
                auto gap = [&](int i) { return std::max(1e-9, top - static_cast<double>(root.edges[i].logit)); };
                std::vector<int> under;
                for (int i = 0; i < k; ++i)
                    if (g.rootKeys[i] >= 0 && i != searchPick && i < static_cast<int>(g.rootUnder.size())
                        && g.rootUnder[i]) under.push_back(i);
                std::shuffle(under.begin(), under.end(), wk.rng);
                const std::int64_t games = runsDone_.load(std::memory_order_relaxed);
                for (int i : under) {
                    const double m = gap(i);
                    const double c = exploreItemC(g.rootKeys[i], games);
                    ++wk.st.exploreAttempts;
                    if (c == 0) ++wk.st.exploreCZero;
                    if (std::isinf(c)) ++wk.st.exploreCInf;
                    const double p = std::isinf(c) ? 1.0 : std::min(1.0, c * std::exp(-m / cfg.exploreT));
                    if (U(wk.rng) < p) { pick = i; ++wk.st.forcedPicks; break; }
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
                bits = search::SilverSearcher::translateAction(Action(bits), root.bc, g.bc).bits;
                if (!Action(bits).isValidAction(g.bc)) {
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
                const int cap = static_cast<int>(std::ceil(cfg.wideningC * std::pow(edge0.n + 1.0, cfg.wideningAlpha)));
                if (static_cast<int>(edge0.outcomes.size()) >= cap) {
                    outcome = static_cast<int>(edge0.n % edge0.outcomes.size());
                    return edge0.outcomes[outcome];
                }
            }
            const int child = newNode(g);   // pool may not move (capacity reserved), references stay valid
            Node &parent = g.pool[cur];
            Edge &edge = parent.edges[e];
            Node &cn = g.pool[child];
            if (parent.combat) {
                BattleContext next = parent.bc;
                if (first) edge.base = search::searchRandomnessBase(next);
                search::seedSearchRng(next, edge.base + edge.outcomes.size());
                Action(edge.bits).execute(next);
                if (first) edge.chance = search::searchRngCounter(next) != 0;
                if (next.outcome == Outcome::PLAYER_LOSS) {
                    cn.combat = true;
                    cn.bc = next;
                    cn.evaluated = cn.terminal = true;
                    cn.value = terminalUtility(false, false, g.gc.floorNum, 0, 1, cfg.hpWeightCombat, cfg);
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
                        cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg);
                        if (emaOn) setOneHot(cn, outcomeClass(*cn.gc));
                    }
                } else {
                    cn.combat = true;
                    cn.bc = next;
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
                    GameAction(edge.bits).execute(next);
                    if (next.outcome != GameOutcome::UNDECIDED) {
                        setGc(cn, std::move(next));
                        cn.evaluated = cn.terminal = true;
                        cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg);
                        if (emaOn) setOneHot(cn, outcomeClass(*cn.gc));
                    } else if (next.screenState == ScreenState::BATTLE) {
                        // A fight starts: the leaf is its first state, valued by the net (in combat).
                        cn.combat = true;
                        // Its public view, as at a real fight start (the shuffle is a sample anyway; this keeps the
                        // net's input distribution the same as at real roots).
                        search::CombatKnowledgeState k;
                        BattleContext live;
                        initObservedBattle(next, live, k);
                        if (!publicCombatRoot(live, k, cn.bc).empty()) cn.bc = live;
                        cn.ctx = combatContext(next);
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
                             bool &combatRng, bool &revealed) {
            combatRng = revealed = false;
            const Node &parent = g.pool[pi];
            Node &cn = g.pool[ci];
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
            };
            // One out-of-combat step on gc, tested for hidden information on its own (a later step's new-floor reseed
            // must not hide an earlier draw).
            auto oocExec = [&](std::uint32_t b) {
                if (!detect) { GameAction(b).execute(gc); return; }
                const auto snap = search::captureOocHidden(gc);
                GameAction(b).execute(gc);
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
                    // The edge's action is in the public view's indexing: map it to the real fight (as the real run).
                    const Action a = search::SilverSearcher::translateAction(Action(bits), parent.bc, bc);
                    if (!a.isValidAction(bc)) { unsupportedLeaf(); return; }
                    combatExec(a.bits);
                } else {
                    bc = parent.bc;
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
                    cn.value = terminalUtility(false, false, fl, 0, 1, cfg.hpWeightOoc, cfg);
                    if (emaOn) setOneHot(cn, std::clamp(fl, 1, kOutcomeClasses - 1));
                    return;
                }
                if (inCombat) {
                    if (bc.outcome == Outcome::PLAYER_LOSS) {
                        combatRng = !ss && (combatRng || search::searchRngCounter(bc) != 0);
                        cn.combat = true;
                        cn.bc = std::move(bc);
                        cn.evaluated = cn.terminal = true;
                        const int fl = outer ? outer->floorNum : g.gc.floorNum;
                        cn.value = terminalUtility(false, false, fl, 0, 1, cfg.hpWeightCombat, cfg);
                        if (emaOn) setOneHot(cn, std::clamp(fl, 1, kOutcomeClasses - 1));   // death on this floor
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
                        const auto &a = combatActions(bc);
                        if (a.size() == 1) { combatExec(a[0].bits); continue; }
                    }
                    combatRng = !ss && (combatRng || search::searchRngCounter(bc) != 0);
                    cn.combat = true;
                    cn.ctx = ctx;
                    cn.outer = std::move(outer);
                    if (ss) {
                        if (!setReal(cn, bc, sk)) { ++wk.st.knowledgeFailures; unsupportedLeaf(); }
                    } else {
                        cn.bc = std::move(bc);
                    }
                    return;
                }
                if (gc.outcome != GameOutcome::UNDECIDED) {
                    setGc(cn, std::move(gc));
                    cn.evaluated = cn.terminal = true;
                    cn.value = terminalUtility(*cn.gc, cfg.hpWeightOoc, cfg);
                    if (emaOn) setOneHot(cn, outcomeClass(*cn.gc));
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
                    ctx = combatContext(gc);
                    if (!cfg.crossCombat) {   // the fight's first state is a leaf valued by the net
                        cn.combat = true;
                        cn.ctx = ctx;
                        cn.boundary = true;
                        if (ss) {
                            if (!setReal(cn, bc, sk)) { ++wk.st.knowledgeFailures; unsupportedLeaf(); }
                        } else {
                            cn.bc = std::move(bc);
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
                const int cap = static_cast<int>(std::ceil(cfg.wideningC * std::pow(edge0.n + 1.0, cfg.wideningAlpha)));
                if (static_cast<int>(edge0.outcomes.size()) >= cap) {
                    outcome = static_cast<int>(edge0.n % edge0.outcomes.size());
                    return edge0.outcomes[outcome];
                }
            }
            const int child = newNode(g);   // pool may not move (capacity reserved), references stay valid
            Node &parent = g.pool[cur];
            Edge &edge = parent.edges[e];
            const int k = static_cast<int>(edge.outcomes.size());
            if (first) edge.base = parent.combat ? search::searchRandomnessBase(parent.bc) : wk.rng();
            bool combatRng = false, revealed = false;
            if (g.savescum) {   // the real step: one deterministic child
                stepAmber(g, cur, edge.bits, edge.base, k, false, child, combatRng, revealed);
                edge.chance = false;
            } else if (first && cfg.chanceOnReveal) {
                stepAmber(g, cur, edge.bits, edge.base, k, false, child, combatRng, revealed);
                if (revealed) {
                    resetNode(g.pool[child]);
                    bool c2 = false, r2 = false;
                    stepAmber(g, cur, edge.bits, edge.base, k, true, child, c2, r2);
                }
                edge.chance = revealed || combatRng;
                if (!parent.combat) ++wk.st.oocEdgeKinds[edge.chance ? 1 : 0];
            } else {
                stepAmber(g, cur, edge.bits, edge.base, k, true, child, combatRng, revealed);
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

        auto advance = [&](Run &g, int gi) {
            while (true) {
                if (g.phaseQueue.empty()) {
                    if (g.spent > 0 && g.cand.size() > 1 && g.phasesLeft > 0) halve(g);
                    if (g.spent >= g.budget || g.cand.size() <= 1) { finishMove(g, gi); return; }
                    fillPhase(g);
                }
                const int forced = g.phaseQueue.back();
                g.phaseQueue.pop_back();
                g.path.clear();
                int cur = 0, e = forced;
                while (true) {
                    int outcome;
                    const double t0 = cpuSeconds();
                    const int child = amberRules || g.savescum ? expandAmber(g, cur, e, outcome) : expand(g, cur, e, outcome);
                    wk.st.stepCpu += cpuSeconds() - t0;
                    g.path.push_back({cur, e, outcome});
                    Node &cn = g.pool[child];
                    g.path.push_back({child, -1, -1});
                    if (!cn.evaluated) { request(g, gi, child); return; }
                    if (cn.terminal || cn.boundary || cn.edges.empty()) {
                        if (cn.terminal) ++wk.st.terminalLeaves;
                        backup(g, cn.value);
                        break;
                    }
                    g.path.pop_back();
                    cur = child;
                    e = selectNonRoot(cn, cfg);
                }
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
            for (int gi : ready) {
                Run &g = wk.runs[gi];
                Node &n = g.pool[g.pendingNode];
                const double w = g.pendingCombat ? cfg.hpWeightCombat : cfg.hpWeightOoc;
                const double H = cfg.utility == Utility::AMBER
                                     ? amberH(g.pendingFloor, g.resHpf.data())
                                     : std::clamp(static_cast<double>(g.resEhp) / g.pendingMaxHp, 0.0, 1.0);
                n.evaluated = true;
                n.value = static_cast<float>((std::clamp<double>(g.resF, 0.0, 1.0) + w * H) / (1.0 + w));
                for (std::size_t k = 0; k < n.edges.size() && k < g.resLogits.size(); ++k) n.edges[k].logit = g.resLogits[k];
                if (emaOn) n.dist.assign(g.resDist.begin(), g.resDist.end());
                if (g.pendingHit) {
                    g.pendingHit = false;
                } else {
                    ++wk.st.evals;
                    // Only results of the cache's weights version go in (a batch evaluated before the last
                    // weights change carries the old version).
                    if (cfg.evalCache && g.resVersion == g.cacheVersion) {
                        if (static_cast<int>(g.cache.size()) >= cfg.evalCacheCap) g.cache.clear();
                        auto &e = g.cache[g.pendingHash];
                        e.F = g.resF;
                        e.ehp = g.resEhp;
                        e.nAct = g.tokens.nAct;
                        e.logits = g.resLogits;
                        if (cfg.utility == Utility::AMBER) e.hpf.assign(g.resHpf.begin(), g.resHpf.end());
                        if (emaOn) e.dist.assign(g.resDist.begin(), g.resDist.end());
                    }
                }
                const bool rootEval = g.pendingNode == 0;
                g.pendingNode = -1;
                if (rootEval) {
                    if (g.keep) {
                        g.cur = Sample{};
                        if (cfg.compactSamples) flattenInto(g.tokens, g.cur, &g.dict, &g.dictIndex);
                        else flattenInto(g.tokens, g.cur);
                        g.cur.combat = g.inBattle ? 1 : 0;
                        g.cur.maxHp = static_cast<std::int16_t>(g.inBattle ? g.bc.player.maxHp : g.gc.maxHp);
                        g.cur.floor = static_cast<std::int16_t>(g.gc.floorNum);
                        g.cur.run = g.seed;
                    }
                    g.path.clear();
                    g.pool[0].n = 1;
                    g.pool[0].w = n.value;
                    if (emaOn) g.rootDist.assign(n.dist.begin(), n.dist.end());
                    initRoot(g);
                } else {
                    backup(g, n.value);
                }
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
                 [&](int r) -> const AmberTokens & { return workers_[take[r] >> 16]->runs[take[r] & 0xffff].tokens; },
                 rowBuckets, tokBuckets, actBuckets, buf, shape, packThreads);
        batches_ += 1;
        batchRows_ += shape.rows;
        packNs_ += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - tPack)
                       .count();
        return take;
    }

    void RunDriver::submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *F,
                           const float *ehp, const float *hpf, std::uint32_t version, const float *dist) {
        if (cfg_.utility == Utility::AMBER && !hpf)
            throw std::invalid_argument("run driver: utility AMBER needs per-floor HP results (hpf)");
        if (cfg_.searchEmaLambda > 0 && !dist)
            throw std::invalid_argument("run driver: searchEmaLambda > 0 needs outcome distributions (dist)");
        thread_local std::vector<std::vector<int>> per;
        per.assign(workers_.size(), {});
        for (int r = 0; r < rows; ++r) {
            const std::uint32_t t = tickets[r];
            Run &g = workers_[t >> 16]->runs[t & 0xffff];
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
            per[t >> 16].push_back(static_cast<int>(t & 0xffff));
        }
        for (std::size_t w = 0; w < per.size(); ++w) {
            if (per[w].empty()) continue;
            std::lock_guard<std::mutex> l(workers_[w]->im);
            auto &in = workers_[w]->inbox;
            in.insert(in.end(), per[w].begin(), per[w].end());
        }
    }

}
