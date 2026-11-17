#include "az_run_driver.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <ctime>
#include <functional>
#include <limits>
#include <stdexcept>

#include "constants/Rooms.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/OocHiddenFuture.h"
#include "sim/search/OocMctsPlanner.h"
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

        std::int16_t clampId(int v) { return static_cast<std::int16_t>(std::clamp(v, 1, search::kAmberIdVocab - 1)); }

        constexpr int kMaxMovesPerRun = 50000;   // whole-run stall guard (a normal A20 run takes a few thousand)

        // A win is a Heart kill. The engine also ends a run as a victory after the act 3 boss without the three keys;
        // that run counts as ending on its floor (no Act 4, no win).
        bool heartWin(const GameContext &gc) {
            return gc.outcome == GameOutcome::PLAYER_VICTORY && gc.act == 4;
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

        // Flat layout of one row (packFlat's per-row layout without padding).
        void flattenInto(const AmberTokens &tk, Sample &s) {
            std::array<int, search::kAmberTokenTypes> off{};
            int n = 0;
            for (int t = 0; t < search::kAmberTokenTypes; ++t) { off[t] = n; n += tk.n[t]; }
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
        std::vector<Edge> edges;
        bool evaluated = false, terminal = false, boundary = false;
        float value = 0;
        std::int32_t n = 0;
        double w = 0;
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
        std::vector<int> rootKeys;           // pick-rate item bucket per root action (-1 = none), OOC roots
        int asc = 20;                        // this run's ascension
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
        std::vector<Sample> pending;
        std::size_t floorStart = 0;          // first pending sample of the current floor
        Sample cur;                          // the current move's sample (root tokens), if kept
    };

    struct RunDriver::Worker {
        std::vector<Run> runs;
        std::mutex im;
        std::vector<int> inbox;
        std::mt19937_64 rng;
        RunStats st;
        mutable std::mutex sm;
        RunStats published;
    };

    namespace {

        double q01(const Edge &e, double fallback) { return e.n ? e.w / e.n : fallback; }

        int selectNonRoot(const RunDriver::Node &node, const RunConfig &cfg) {
            const int k = static_cast<int>(node.edges.size());
            int maxN = 0;
            double sumN = 0;
            for (const auto &e : node.edges) { maxN = std::max(maxN, static_cast<int>(e.n)); sumN += e.n; }
            const double sigma = (cfg.cVisit + maxN) * cfg.cScale;
            thread_local std::vector<double> s;
            s.resize(k);
            double mx = -1e300;
            for (int i = 0; i < k; ++i) {
                s[i] = node.edges[i].logit + sigma * q01(node.edges[i], node.value);
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

        double rootScore(const RunDriver::Run &g, const RunDriver::Node &root, int e, const RunConfig &cfg) {
            int maxN = 0;
            for (const auto &x : root.edges) maxN = std::max(maxN, static_cast<int>(x.n));
            return g.gumbel[e] + root.edges[e].logit + (cfg.cVisit + maxN) * cfg.cScale * q01(root.edges[e], root.value);
        }

        // Scaled utility (F + w H) / (1 + w) of a state the run cannot continue from.
        float terminalUtility(bool win, int floor, int hp, int maxHp, double w) {
            const double F = win ? 1.0 : std::clamp(floor, 1, kOutcomeClasses - 1) / 57.0;
            const double H = win ? std::clamp(static_cast<double>(hp) / std::max(1, maxHp), 0.0, 1.0) : 0.0;
            return static_cast<float>((F + w * H) / (1.0 + w));
        }

    }

    RunDriver::RunDriver(RunConfig cfg) : cfg_(cfg) {
        if (cfg_.ascension < 0 || cfg_.ascension >= kAscensions) throw std::invalid_argument("run driver: ascension 0..20");
        ascension_.store(cfg_.ascension);
        picks_.reset(new std::atomic<std::uint32_t>[kPickBuckets]);
        for (int i = 0; i < kPickBuckets; ++i) picks_[i].store(0);
        if (!cfg_.encodeCombat) cfg_.encodeCombat = search::amberEncodeCombat;
        if (!cfg_.encodeGame) cfg_.encodeGame = search::amberEncodeGame;
        if (cfg_.gamesPerWorker > 0xffff) throw std::invalid_argument("run driver: at most 65535 runs per worker");
        for (int w = 0; w < cfg_.workers; ++w) {
            auto wk = std::make_unique<Worker>();
            wk->rng.seed(cfg_.searchSeed * 1000003u + static_cast<std::uint64_t>(w));
            wk->runs.resize(cfg_.gamesPerWorker);
            for (auto &r : wk->runs)
                // One node per simulation; a halving phase rounds its per-candidate count up to 1, so a search
                // can overshoot its budget by at most one simulation per candidate.
                r.pool.reserve(static_cast<std::size_t>(std::max(cfg_.fullSims, cfg_.fastSims) +
                                                        std::max(cfg_.fullCandidates, cfg_.fastCandidates)) + 2);
            workers_.push_back(std::move(wk));
        }
    }

    RunDriver::~RunDriver() { stop(); }

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
            }
            s.oocRoots += p.oocRoots; s.exploreRoots += p.exploreRoots; s.forcedPicks += p.forcedPicks;
            s.stepCpu += p.stepCpu; s.encodeCpu += p.encodeCpu; s.searchCpu += p.searchCpu;
        }
        s.batches = batches_.load();
        s.batchRows = batchRows_.load();
        s.packSeconds = 1e-9 * static_cast<double>(packNs_.load());
        return s;
    }

    void RunDriver::takeSamples(int maxSamples, std::vector<Sample> &out) {
        std::lock_guard<std::mutex> l(sampleM_);
        const int n = std::min<int>(maxSamples, static_cast<int>(done_.size()));
        for (int i = 0; i < n; ++i) {
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

        auto combatActions = [&](const BattleContext &bc) -> const std::vector<Action> & {
            if (!enumerator) enumerator = std::make_unique<search::SilverSearcher>(bc, search::SilverSearchContext{});
            cacts = enumerator->enumerateActions(bc);
            return cacts;
        };

        auto newNode = [&](Run &g) -> int {
            if (g.poolUsed == static_cast<int>(g.pool.size())) {
                if (g.pool.size() == g.pool.capacity()) throw std::logic_error("run driver: node pool overflow");
                g.pool.emplace_back();
            }
            Node &n = g.pool[g.poolUsed];
            n.edges.clear();
            n.evaluated = n.terminal = n.boundary = false;
            n.value = 0;
            n.n = 0;
            n.w = 0;
            return g.poolUsed++;
        };
        auto setGc = [](Node &n, GameContext &&gc) {
            n.combat = false;
            if (n.gc) *n.gc = std::move(gc);
            else n.gc = std::make_unique<GameContext>(std::move(gc));
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
                wk.st.stepCpu += t1 - t0;
                wk.st.encodeCpu += cpuSeconds() - t1;
                g.pendingCombat = true;
                g.pendingMaxHp = static_cast<float>(std::max<int>(1, node.bc.player.maxHp));
            } else {
                gacts = GameAction::getAllActionsInState(*node.gc);
                node.edges.resize(gacts.size());
                for (std::size_t k = 0; k < gacts.size(); ++k) node.edges[k] = Edge{gacts[k].bits};
                const double t1 = cpuSeconds();
                cfg.encodeGame(*node.gc, gacts, g.tokens);
                if (ni == 0 && cfg.exploreC > 0) {
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
            }
            (node.combat ? wk.st.encodeCut : wk.st.encodeCutOoc) += g.tokens.cut;
            g.pendingNode = ni;
            outbox.push_back(static_cast<std::uint32_t>(wi) << 16 | static_cast<std::uint32_t>(gi));
        };

        auto backup = [&](Run &g, float v) {
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
        };

        std::function<void(Run &, int)> startMove;

        auto startRun = [&](Run &g, int gi) {
            const std::uint64_t seed = nextSeed();
            if (seed == std::numeric_limits<std::uint64_t>::max()) { g.active = false; return; }
            g.active = true;
            g.seed = seed;
            g.asc = ascension_.load(std::memory_order_relaxed);
            g.gc = GameContext(CharacterClass::IRONCLAD, seed, g.asc);
            if (cfg.testMaxHp > 0) g.gc.curHp = g.gc.maxHp = cfg.testMaxHp;
            g.inBattle = false;
            g.moves = g.fightMoves = 0;
            g.floor = g.gc.floorNum;
            g.pending.clear();
            g.floorStart = 0;
            ++wk.st.runsStarted;
            startMove(g, gi);
        };

        auto endRun = [&](Run &g, int gi) {
            const bool win = heartWin(g.gc);
            closeFloor(g, win ? g.gc.curHp : 0);
            const int oc = outcomeClass(g.gc);
            for (auto &s : g.pending) s.outcome = static_cast<std::int16_t>(oc);
            ++wk.st.runsDone;
            runsDone_.fetch_add(1, std::memory_order_relaxed);
            if (win) ++wk.st.wins;
            wk.st.floorsSum += g.gc.floorNum;
            ++wk.st.outcomes[oc];
            ++wk.st.runsDoneAsc[g.asc];
            if (win) ++wk.st.winsAsc[g.asc];
            wk.st.floorsSumAsc[g.asc] += g.gc.floorNum;

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
                GameAction(bits).execute(g.gc);
            }
            if (!g.inBattle && g.gc.outcome == GameOutcome::UNDECIDED && g.gc.screenState == ScreenState::BATTLE) {
                initObservedBattle(g.gc, g.bc, *g.knowledge);
                g.ctx = combatContext(g.gc);
                g.inBattle = true;
                g.fightMoves = 0;
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
                    gacts = GameAction::getAllActionsInState(g.gc);
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
            g.poolUsed = 0;
            g.spent = 0;
            g.full = U(wk.rng) < cfg.fullProb;
            {
                const double pend = static_cast<double>(pending_.load(std::memory_order_relaxed));
                const double scale = pend > cfg.maxPendingSamples ? cfg.maxPendingSamples / pend : 1.0;
                g.keep = U(wk.rng) < (g.full ? cfg.keepFull : cfg.keepFast) * scale;
            }
            g.budget = g.full ? cfg.fullSims : cfg.fastSims;
            g.candidates = g.full ? cfg.fullCandidates : cfg.fastCandidates;
            g.cand.clear();
            g.phaseQueue.clear();
            g.path.clear();
            const int r = newNode(g);
            Node &root = g.pool[r];
            if (g.inBattle) {
                root.combat = true;
                root.ctx = g.ctx;
                if (!publicCombatRoot(g.bc, *g.knowledge, root.bc).empty()) {
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
            request(g, gi, r);
            if (!g.inBattle && cfg.exploreC > 0) {
                ++wk.st.oocRoots;
                const double games = static_cast<double>(runsDone_.load(std::memory_order_relaxed));
                bool under = false;
                // Rates are over finished runs, after a warm-up of 1 / pickTarget runs (no item is under target before).
                if (games * cfg.pickTarget >= 1.0)
                    for (int key : g.rootKeys)
                        if (key >= 0 && picks_[key].load(std::memory_order_relaxed) < cfg.pickTarget * games) under = true;
                if (under) {
                    ++wk.st.exploreRoots;
                    if (!g.full) {   // a root with an under-target item gets a full search (policy target recorded)
                        g.full = true;
                        const double pend = static_cast<double>(pending_.load(std::memory_order_relaxed));
                        const double scale = pend > cfg.maxPendingSamples ? cfg.maxPendingSamples / pend : 1.0;
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
            for (int i = 0; i < k; ++i) { g.gumbel[i] = G(wk.rng); order[i] = i; }
            std::sort(order.begin(), order.end(), [&](int a, int b) {
                return g.gumbel[a] + root.edges[a].logit > g.gumbel[b] + root.edges[b].logit;
            });
            const int m = std::min(k, g.candidates);
            g.cand.assign(order.begin(), order.begin() + m);
            g.phasesLeft = m > 1 ? static_cast<int>(std::ceil(std::log2(m))) : 1;
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
            std::sort(g.cand.begin(), g.cand.end(), [&](int a, int b) {
                return rootScore(g, root, a, cfg) > rootScore(g, root, b, cfg);
            });
            g.cand.resize(std::max<std::size_t>(1, (g.cand.size() + 1) / 2));
            --g.phasesLeft;
        };

        auto finishMove = [&](Run &g, int gi) {
            const Node &root = g.pool[0];
            int pick = g.cand.empty() ? 0 : g.cand.front();
            if (g.cand.size() > 1) {
                double best = -1e300;
                for (int e : g.cand) {
                    const double s = rootScore(g, root, e, cfg);
                    if (s > best) { best = s; pick = e; }
                }
            }
            ++wk.st.searchedMoves;
            if (g.keep) {
                Sample &s = g.cur;
                if (g.full) {   // Gumbel AlphaZero's improved policy: softmax(logits + sigma(completed Q))
                    const int k = static_cast<int>(root.edges.size());
                    int maxN = 0;
                    for (const auto &x : root.edges) maxN = std::max(maxN, static_cast<int>(x.n));
                    const double sigma = (cfg.cVisit + maxN) * cfg.cScale;
                    std::vector<double> z(k);
                    double mx = -1e300;
                    for (int i = 0; i < k; ++i) {
                        z[i] = root.edges[i].logit + sigma * q01(root.edges[i], root.value);
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
                    cn.value = terminalUtility(false, g.gc.floorNum, 0, 1, cfg.hpWeightCombat);
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
                        cn.value = terminalUtility(heartWin(*cn.gc), cn.gc->floorNum,
                                                   cn.gc->curHp, cn.gc->maxHp, cfg.hpWeightOoc);
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
                        cn.value = terminalUtility(heartWin(*cn.gc), cn.gc->floorNum,
                                                   cn.gc->curHp, cn.gc->maxHp, cfg.hpWeightOoc);
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
                    const int child = expand(g, cur, e, outcome);
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
            if (ready.empty()) std::this_thread::sleep_for(std::chrono::microseconds(50));
            const double t0 = cpuSeconds();
            for (int gi : ready) {
                Run &g = wk.runs[gi];
                Node &n = g.pool[g.pendingNode];
                const double w = g.pendingCombat ? cfg.hpWeightCombat : cfg.hpWeightOoc;
                const double H = std::clamp(static_cast<double>(g.resEhp) / g.pendingMaxHp, 0.0, 1.0);
                n.evaluated = true;
                n.value = static_cast<float>((std::clamp<double>(g.resF, 0.0, 1.0) + w * H) / (1.0 + w));
                for (std::size_t k = 0; k < n.edges.size() && k < g.resLogits.size(); ++k) n.edges[k].logit = g.resLogits[k];
                ++wk.st.evals;
                const bool rootEval = g.pendingNode == 0;
                g.pendingNode = -1;
                if (rootEval) {
                    if (g.keep) {
                        g.cur = Sample{};
                        flattenInto(g.tokens, g.cur);
                        g.cur.combat = g.inBattle ? 1 : 0;
                        g.cur.maxHp = static_cast<std::int16_t>(g.inBattle ? g.bc.player.maxHp : g.gc.maxHp);
                        g.cur.floor = static_cast<std::int16_t>(g.gc.floorNum);
                        g.cur.run = g.seed;
                    }
                    g.path.clear();
                    g.pool[0].n = 1;
                    g.pool[0].w = n.value;
                    initRoot(g);
                } else {
                    backup(g, n.value);
                }
                advance(g, gi);
            }
            ready.clear();
            wk.st.searchCpu += cpuSeconds() - t0;
            if (t0 - lastPublish > 0.05) {
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
                           const float *ehp) {
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
