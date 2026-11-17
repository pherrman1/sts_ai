#include "az_driver.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <ctime>
#include <limits>
#include <random>
#include <stdexcept>

#include "sim/search/SearchRng.h"

namespace sts::azbench {

    using search::Action;
    using search::ActionType;
    using search::AmberTokens;
    using search::AmberTokenType;

    namespace {

        double cpuSeconds() {
            timespec ts{};
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
            return static_cast<double>(ts.tv_sec) + 1e-9 * static_cast<double>(ts.tv_nsec);
        }

        // float -> IEEE half bits (round to nearest, no NaN payloads; enough for features).
        std::uint16_t half(float x) {
            std::uint32_t b;
            std::memcpy(&b, &x, 4);
            const std::uint32_t sign = (b >> 16) & 0x8000u;
            const int exp = static_cast<int>((b >> 23) & 0xff) - 127 + 15;
            std::uint32_t man = b & 0x7fffffu;
            if (exp <= 0) return static_cast<std::uint16_t>(sign);
            if (exp >= 31) return static_cast<std::uint16_t>(sign | 0x7c00u);
            man += 0x1000u;
            if (man & 0x800000u) {
                man = 0;
                if (exp + 1 >= 31) return static_cast<std::uint16_t>(sign | 0x7c00u);
                return static_cast<std::uint16_t>(sign | ((exp + 1) << 10));
            }
            return static_cast<std::uint16_t>(sign | (exp << 10) | (man >> 13));
        }

        // Id ranges in one shared space (stub only).
        constexpr int kCardBase = 1, kMonsterBase = 400, kRelicBase = 560, kStatusBase = 760, kPotionBase = 900;

        std::int16_t clampId(int base, int v) {
            return static_cast<std::int16_t>(std::clamp(base + v, 1, search::kAmberIdVocab - 1));
        }

        void putCard(AmberTokens &t, int i, const CardInstance &c, int zone, float pos) {
            auto &k = t.at(AmberTokenType::CARD, i);
            k.ids = {clampId(kCardBase, static_cast<int>(c.id)), static_cast<std::int16_t>(1 + zone), 0, 0};
            k.f[0] = half(c.upgraded ? 1.f : 0.f);
            k.f[1] = half(static_cast<float>(c.cost));
            k.f[2] = half(static_cast<float>(c.costForTurn));
            k.f[3] = half(pos);
        }

        float slog(float x) { return std::copysign(std::log1p(std::fabs(x)), x); }

    }

    void stubEncode(const BattleContext &bc, const search::SilverSearchContext &, const std::vector<Action> &actions,
                    AmberTokens &out) {
        out.clear();
        auto &run = out.at(AmberTokenType::RUN, 0);
        run.f[0] = half(static_cast<float>(bc.floorNum) / 50.f);
        run.f[1] = half(static_cast<float>(bc.ascension) / 20.f);
        run.f[2] = half(static_cast<float>(bc.turn) / 10.f);
        out.n[static_cast<int>(AmberTokenType::RUN)] = 1;
        auto &pl = out.at(AmberTokenType::PLAYER, 0);
        pl.f[0] = half(slog(static_cast<float>(bc.player.curHp)));
        pl.f[1] = half(slog(static_cast<float>(bc.player.maxHp)));
        pl.f[2] = half(slog(static_cast<float>(bc.player.block)));
        pl.f[3] = half(static_cast<float>(bc.player.energy));
        out.n[static_cast<int>(AmberTokenType::PLAYER)] = 1;

        int ns = 0;
        for (const auto &kv : bc.player.statusMap) {
            if (ns >= search::kAmberCap[static_cast<int>(AmberTokenType::STATUS)]) { ++out.cut; break; }
            auto &k = out.at(AmberTokenType::STATUS, ns++);
            k.ids = {clampId(kStatusBase, static_cast<int>(kv.first)), 0, 0, 0};
            k.f[0] = half(slog(static_cast<float>(kv.second)));
        }
        out.n[static_cast<int>(AmberTokenType::STATUS)] = static_cast<std::uint8_t>(ns);

        const int nm = std::min(bc.monsters.monsterCount, 5);
        for (int i = 0; i < nm; ++i) {
            const auto &m = bc.monsters.arr[i];
            auto &k = out.at(AmberTokenType::MONSTER, i);
            k.ids = {clampId(kMonsterBase, static_cast<int>(m.id)), static_cast<std::int16_t>(1 + i),
                     clampId(1, static_cast<int>(m.moveHistory[0])), clampId(1, static_cast<int>(m.moveHistory[1]))};
            k.f[0] = half(slog(static_cast<float>(m.curHp)));
            k.f[1] = half(slog(static_cast<float>(m.maxHp)));
            k.f[2] = half(slog(static_cast<float>(m.block)));
        }
        out.n[static_cast<int>(AmberTokenType::MONSTER)] = static_cast<std::uint8_t>(nm);

        // Cards: hand first (so a hand index is a CARD token index), then draw, discard, exhaust.
        const int cap = search::kAmberCap[static_cast<int>(AmberTokenType::CARD)];
        int nc = 0;
        auto add = [&](const CardInstance &c, int zone, float pos) {
            if (nc >= cap) { ++out.cut; return; }
            putCard(out, nc++, c, zone, pos);
        };
        for (int i = 0; i < bc.cards.cardsInHand; ++i) add(bc.cards.hand[i], 0, static_cast<float>(i));
        for (const auto &c : bc.cards.drawPile) add(c, 1, 0.f);
        for (const auto &c : bc.cards.discardPile) add(c, 2, 0.f);
        for (const auto &c : bc.cards.exhaustPile) add(c, 3, 0.f);
        out.n[static_cast<int>(AmberTokenType::CARD)] = static_cast<std::uint8_t>(nc);

        int nr = 0;
        for (int r = 0; r < 128 && nr < search::kAmberCap[static_cast<int>(AmberTokenType::RELIC)]; ++r) {
            const bool has = r < 64 ? (bc.player.relicBits0 >> r) & 1u : (bc.player.relicBits1 >> (r - 64)) & 1u;
            if (!has) continue;
            out.at(AmberTokenType::RELIC, nr++).ids = {clampId(kRelicBase, r), 0, 0, 0};
        }
        out.n[static_cast<int>(AmberTokenType::RELIC)] = static_cast<std::uint8_t>(nr);

        const int np = std::min(bc.potionCapacity, 5);
        for (int i = 0; i < np; ++i)
            out.at(AmberTokenType::POTION, i).ids = {clampId(kPotionBase, static_cast<int>(bc.potions[i])), 0, 0, 0};
        out.n[static_cast<int>(AmberTokenType::POTION)] = static_cast<std::uint8_t>(np);

        for (const auto &a : actions) {
            if (out.nAct >= search::kAmberMaxActions) { ++out.cut; continue; }
            auto &e = out.act[out.nAct++];
            const ActionType t = a.getActionType();
            e.type = static_cast<std::uint8_t>(t);
            e.srcSeg = e.tgtSeg = search::kAmberNoSeg;
            if (t == ActionType::CARD || t == ActionType::POTION) {
                const int s = a.getSourceIdx(), g = a.getTargetIdx();
                const bool card = t == ActionType::CARD;
                const int lim = card ? bc.cards.cardsInHand : np;
                if (s >= 0 && s < lim) {
                    e.srcSeg = static_cast<std::uint8_t>(card ? AmberTokenType::CARD : AmberTokenType::POTION);
                    e.srcIdx = static_cast<std::uint8_t>(s);
                }
                if (g >= 0 && g < nm) {
                    e.tgtSeg = static_cast<std::uint8_t>(AmberTokenType::MONSTER);
                    e.tgtIdx = static_cast<std::uint8_t>(g);
                }
            } else if (t == ActionType::SINGLE_CARD_SELECT) {
                e.f[0] = half(static_cast<float>(a.getSelectIdx()));
            }
        }
    }

    // --- search ------------------------------------------------------------------------------------------------

    struct Edge {
        Action action;
        float logit = 0;
        std::int32_t n = 0;
        double w = 0;
        int child = -1;                  // decision child (deterministic edge)
        bool chance = false, tried = false;
        std::uint64_t base = 0;          // chance: randomness base of the parent
        std::vector<int> outcomes;       // chance: outcome nodes
        std::vector<std::int32_t> outcomeN;
    };

    struct Node {
        BattleContext state;
        std::vector<Edge> edges;
        bool evaluated = false, terminal = false;
        float value = 0;                 // net value (or terminal value)
        std::int32_t n = 0;
        double w = 0;
    };

    struct PathStep { int node; int edge; int outcome; };

    struct Driver::Game {
        int root = 0;                    // wire row
        BattleContext real;              // the fight being played
        int moves = 0;
        std::vector<Node> pool;
        int poolUsed = 0;
        // search of the current move
        int budget = 0, spent = 0, candidates = 0;
        std::vector<int> cand;           // remaining root candidates (edge indices)
        std::vector<double> gumbel;
        std::vector<int> phaseQueue;     // forced root edges still to simulate in this phase
        int phasesLeft = 0, perPhase = 0;
        std::vector<PathStep> path;
        int pendingNode = -1;            // waiting for a net result for this node
        bool waiting = false;
        search::AmberTokens tokens;      // request buffer (read by the batcher while waiting)
        std::vector<float> resLogits;
        float resValue = 0;
    };

    struct Driver::Worker {
        std::vector<Game> games;
        std::mutex im;
        std::vector<int> inbox;          // games with a posted result
        std::mt19937_64 rng;
        Stats st;
        mutable std::mutex sm;
        Stats published;
    };

    namespace {

        float terminalValue(const BattleContext &bc) { return bc.outcome == Outcome::PLAYER_VICTORY ? 1.f : 0.f; }

        int newNode(Driver::Game &g, const BattleContext &state) {
            if (g.poolUsed == static_cast<int>(g.pool.size())) {
                if (g.pool.size() == g.pool.capacity()) throw std::logic_error("az driver: node pool overflow");
                g.pool.emplace_back();
            }
            Node &n = g.pool[g.poolUsed];
            n.state = state;
            n.edges.clear();
            n.evaluated = n.terminal = false;
            n.value = 0;
            n.n = 0;
            n.w = 0;
            return g.poolUsed++;
        }

        double q01(const Edge &e, double fallback) { return e.n ? e.w / e.n : fallback; }

        // Gumbel MuZero's deterministic non-root selection: argmax pi'(a) - n(a) / (1 + N).
        int selectNonRoot(const Node &node, const DriverConfig &cfg) {
            const int k = static_cast<int>(node.edges.size());
            int maxN = 0;
            double sumN = 0;
            for (const auto &e : node.edges) { maxN = std::max(maxN, static_cast<int>(e.n)); sumN += e.n; }
            const double sigma = (cfg.cVisit + maxN) * cfg.cScale;
            const double vmix = node.value;
            double mx = -1e300;
            thread_local std::vector<double> s;
            s.resize(k);
            for (int i = 0; i < k; ++i) {
                s[i] = node.edges[i].logit + sigma * q01(node.edges[i], vmix);
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

        double rootScore(const Driver::Game &g, const Node &root, int e, const DriverConfig &cfg) {
            int maxN = 0;
            for (const auto &x : root.edges) maxN = std::max(maxN, static_cast<int>(x.n));
            const double q = q01(root.edges[e], root.value);
            return g.gumbel[e] + root.edges[e].logit + (cfg.cVisit + maxN) * cfg.cScale * q;
        }

    }

    Driver::Driver(std::vector<Root> roots, DriverConfig cfg) : roots_(std::move(roots)), cfg_(cfg) {
        for (int w = 0; w < cfg_.workers; ++w) {
            auto wk = std::make_unique<Worker>();
            wk->rng.seed(cfg_.seed * 1000003u + static_cast<std::uint64_t>(w));
            wk->games.resize(cfg_.gamesPerWorker);
            for (int i = 0; i < cfg_.gamesPerWorker; ++i) {
                auto &g = wk->games[i];
                g.root = (w * cfg_.gamesPerWorker + i) % static_cast<int>(roots_.size());
                g.real = roots_[g.root].state;
                // Each simulation adds at most one node, so this capacity is never exceeded and node / edge
                // references stay valid while a simulation creates its leaf.
                g.pool.reserve(static_cast<std::size_t>(std::max(cfg_.fullSims, cfg_.fastSims)) + 2);
            }
            workers_.push_back(std::move(wk));
        }
    }

    Driver::~Driver() { stop(); }

    void Driver::start() {
        stop_ = false;
        for (int w = 0; w < cfg_.workers; ++w) threads_.emplace_back(&Driver::workerLoop, this, w);
    }

    void Driver::stop() {
        stop_ = true;
        qcv_.notify_all();
        for (auto &t : threads_) t.join();
        threads_.clear();
    }

    Stats Driver::stats() const {
        Stats s;
        for (const auto &w : workers_) {
            std::lock_guard<std::mutex> l(w->sm);
            const Stats &p = w->published;
            s.evals += p.evals; s.moves += p.moves; s.fights += p.fights; s.wins += p.wins;
            s.terminalLeaves += p.terminalLeaves; s.encodeCut += p.encodeCut;
            s.stepCpu += p.stepCpu; s.encodeCpu += p.encodeCpu; s.searchCpu += p.searchCpu;
        }
        s.batches = batches_.load();
        s.batchRows = batchRows_.load();
        return s;
    }

    void Driver::workerLoop(int wi) {
        Worker &wk = *workers_[wi];
        const DriverConfig &cfg = cfg_;
        std::vector<std::uint32_t> outbox;
        std::vector<int> ready;
        std::uniform_real_distribution<double> U(0.0, 1.0);
        std::vector<search::Action> acts;
        search::SilverSearcher localEnum(roots_[0].state, roots_[0].context);
        search::SilverSearcher *enumerator = &localEnum;
        double lastPublish = cpuSeconds();

        // Request an evaluation of node `ni` of game g: enumerate its actions, encode, queue.
        auto request = [&](Game &g, int gi, int ni) {
            Node &node = g.pool[ni];
            double t0 = cpuSeconds();
            acts = enumerator->enumerateActions(node.state);
            node.edges.resize(acts.size());
            for (std::size_t k = 0; k < acts.size(); ++k) node.edges[k] = Edge{acts[k]};
            double t1 = cpuSeconds();
            cfg.encode(node.state, roots_[g.root].context, acts, g.tokens);
            wk.st.encodeCut += g.tokens.cut;
            double t2 = cpuSeconds();
            wk.st.stepCpu += t1 - t0;
            wk.st.encodeCpu += t2 - t1;
            g.pendingNode = ni;
            g.waiting = true;
            outbox.push_back(static_cast<std::uint32_t>(wi) << 16 | static_cast<std::uint32_t>(gi));
        };

        auto backup = [&](Game &g, float v) {
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

        auto startMove = [&](Game &g, int gi) {
            g.poolUsed = 0;
            g.spent = 0;
            const bool full = U(wk.rng) < cfg.fullProb;
            g.budget = full ? cfg.fullSims : cfg.fastSims;
            g.candidates = full ? cfg.fullCandidates : cfg.fastCandidates;
            g.cand.clear();
            g.phaseQueue.clear();
            g.path.clear();
            const int r = newNode(g, g.real);
            g.path.push_back({r, -1, -1});
            request(g, gi, r);
        };

        // Root expanded: Gumbel-top-k candidates and the first halving phase.
        auto initRoot = [&](Game &g) {
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

        auto fillPhase = [&](Game &g) {
            const int remaining = g.budget - g.spent;
            const int per = std::max(1, remaining / std::max(1, g.phasesLeft) / static_cast<int>(g.cand.size()));
            g.phaseQueue.clear();
            for (int r = 0; r < per; ++r)
                for (int e : g.cand) g.phaseQueue.push_back(e);
        };

        auto halve = [&](Game &g) {
            const Node &root = g.pool[0];
            std::sort(g.cand.begin(), g.cand.end(), [&](int a, int b) {
                return rootScore(g, root, a, cfg) > rootScore(g, root, b, cfg);
            });
            g.cand.resize(std::max<std::size_t>(1, (g.cand.size() + 1) / 2));
            --g.phasesLeft;
        };

        auto finishMove = [&](Game &g, int gi) {
            const Node &root = g.pool[0];
            int pick = g.cand.empty() ? 0 : g.cand.front();
            if (g.cand.size() > 1) {
                double best = -1e300;
                for (int e : g.cand) {
                    const double s = rootScore(g, root, e, cfg);
                    if (s > best) { best = s; pick = e; }
                }
            }
            double t0 = cpuSeconds();
            root.edges[pick].action.execute(g.real);
            wk.st.stepCpu += cpuSeconds() - t0;
            ++wk.st.moves;
            ++g.moves;
            if (g.real.outcome != Outcome::UNDECIDED || g.moves >= cfg.maxMovesPerFight) {
                ++wk.st.fights;
                if (g.real.outcome == Outcome::PLAYER_VICTORY) ++wk.st.wins;
                g.root = static_cast<int>(wk.rng() % roots_.size());
                g.real = roots_[g.root].state;
                g.moves = 0;
            }
            startMove(g, gi);
        };

        // Runs simulations of game g until one needs a net evaluation (returns) or the move is finished.
        auto advance = [&](Game &g, int gi) {
            while (true) {
                if (g.phaseQueue.empty()) {
                    // A phase just ended (or none started): halve, then stop or start the next phase.
                    if (g.spent > 0 && g.cand.size() > 1 && g.phasesLeft > 0) halve(g);
                    if (g.spent >= g.budget || g.cand.size() <= 1) { finishMove(g, gi); return; }
                    fillPhase(g);
                }
                const int forced = g.phaseQueue.back();
                g.phaseQueue.pop_back();
                // One simulation: forced root edge, then non-root selection down to a new leaf.
                g.path.clear();
                int cur = 0;
                int e = forced;
                while (true) {
                    Node &node = g.pool[cur];
                    Edge &edge = node.edges[e];
                    int child = -1, outcome = -1;
                    double t0 = cpuSeconds();
                    if (!edge.tried) {
                        edge.tried = true;
                        BattleContext next = node.state;
                        edge.base = search::searchRandomnessBase(next);
                        search::seedSearchRng(next, edge.base);
                        edge.action.execute(next);
                        edge.chance = search::searchRngCounter(next) != 0;
                        child = newNode(g, next);
                        if (edge.chance) { edge.outcomes.assign(1, child); edge.outcomeN.assign(1, 0); outcome = 0; }
                        else edge.child = child;
                    } else if (!edge.chance) {
                        child = edge.child;
                    } else {
                        const int cap = static_cast<int>(std::ceil(cfg.wideningC * std::pow(edge.n + 1.0, cfg.wideningAlpha)));
                        if (static_cast<int>(edge.outcomes.size()) < cap) {
                            BattleContext next = g.pool[cur].state;
                            search::seedSearchRng(next, edge.base + edge.outcomes.size());
                            g.pool[cur].edges[e].action.execute(next);
                            child = newNode(g, next);
                            Edge &ed = g.pool[cur].edges[e];   // pool may have grown
                            ed.outcomes.push_back(child);
                            ed.outcomeN.push_back(0);
                            outcome = static_cast<int>(ed.outcomes.size()) - 1;
                        } else {
                            Edge &ed = g.pool[cur].edges[e];
                            outcome = static_cast<int>(ed.n % ed.outcomes.size());
                            child = ed.outcomes[outcome];
                        }
                    }
                    wk.st.stepCpu += cpuSeconds() - t0;
                    g.path.push_back({cur, e, outcome});
                    Node &cn = g.pool[child];
                    if (!cn.evaluated) {
                        if (cn.state.outcome != Outcome::UNDECIDED) {
                            cn.evaluated = cn.terminal = true;
                            cn.value = terminalValue(cn.state);
                            g.path.push_back({child, -1, -1});
                            ++wk.st.terminalLeaves;
                            backup(g, cn.value);
                            break;
                        }
                        g.path.push_back({child, -1, -1});
                        request(g, gi, child);
                        return;
                    }
                    if (cn.terminal || cn.edges.empty()) {
                        g.path.push_back({child, -1, -1});
                        backup(g, cn.value);
                        break;
                    }
                    cur = child;
                    e = selectNonRoot(cn, cfg);
                }
            }
        };

        // Start every game.
        double s0 = cpuSeconds();
        for (int gi = 0; gi < static_cast<int>(wk.games.size()); ++gi) startMove(wk.games[gi], gi);
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
            if (ready.empty()) {
                std::this_thread::sleep_for(std::chrono::microseconds(50));
            }
            double t0 = cpuSeconds();
            for (int gi : ready) {
                Game &g = wk.games[gi];
                Node &n = g.pool[g.pendingNode];
                n.evaluated = true;
                n.value = g.resValue;
                for (std::size_t k = 0; k < n.edges.size() && k < g.resLogits.size(); ++k) n.edges[k].logit = g.resLogits[k];
                g.waiting = false;
                ++wk.st.evals;
                const bool rootEval = g.pendingNode == 0;
                g.pendingNode = -1;
                if (rootEval) {
                    g.path.clear();
                    g.pool[0].n = 1;
                    g.pool[0].w = n.value;
                    if (g.pool[0].edges.empty()) { finishMove(g, gi); continue; }
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

    std::vector<std::uint32_t> Driver::takeRequests(int maxRows, int minRows, int timeoutMs) {
        std::vector<std::uint32_t> take;
        std::unique_lock<std::mutex> l(qm_);
        qcv_.wait_for(l, std::chrono::milliseconds(timeoutMs),
                      [&] { return stop_.load() || static_cast<int>(queue_.size()) >= minRows; });
        const int n = std::min<int>(maxRows, static_cast<int>(queue_.size()));
        take.assign(queue_.begin(), queue_.begin() + n);
        queue_.erase(queue_.begin(), queue_.begin() + n);
        return take;
    }

    std::vector<std::uint32_t> Driver::takeSorted(int maxRows, int minRows, int timeoutMs, int sortWindow) {
        std::lock_guard<std::mutex> l(cm_);
        if (chunks_.empty()) {
            std::vector<std::uint32_t> all = takeRequests(maxRows * sortWindow, minRows, timeoutMs);
            if (all.empty()) return all;
            std::vector<std::pair<int, std::uint32_t>> keyed;
            keyed.reserve(all.size());
            for (auto t : all) {
                const auto &tk = workers_[t >> 16]->games[t & 0xffff].tokens;
                int n = 0;
                for (int s = 0; s < search::kAmberTokenTypes; ++s) n += tk.n[s];
                keyed.emplace_back(n, t);
            }
            std::stable_sort(keyed.begin(), keyed.end(),
                             [](const auto &a, const auto &b) { return a.first < b.first; });
            for (std::size_t i = 0; i < keyed.size(); i += maxRows) {
                std::vector<std::uint32_t> c;
                for (std::size_t j = i; j < std::min(keyed.size(), i + maxRows); ++j) c.push_back(keyed[j].second);
                chunks_.push_back(std::move(c));
            }
        }
        std::vector<std::uint32_t> out = std::move(chunks_.front());
        chunks_.pop_front();
        return out;
    }

    namespace {
        int bucketFor(const std::vector<int> &buckets, int n) {
            for (int b : buckets)
                if (b >= n) return b;
            return buckets.empty() ? n : buckets.back();
        }
    }

    std::vector<std::uint32_t> Driver::nextBatchFlat(int maxRows, int minRows, int timeoutMs,
                                                     const std::vector<int> &rowBuckets,
                                                     const std::vector<int> &tokBuckets,
                                                     const std::vector<int> &actBuckets, const FlatBuffers &buf,
                                                     FlatShape &shape, int sortWindow) {
        std::vector<std::uint32_t> take = sortWindow > 1 ? takeSorted(maxRows, minRows, timeoutMs, sortWindow)
                                                         : takeRequests(maxRows, minRows, timeoutMs);
        shape = {};
        if (take.empty()) return take;
        auto tokensOf = [&](std::uint32_t t) -> const AmberTokens & {
            return workers_[t >> 16]->games[t & 0xffff].tokens;
        };
        int maxT = 1, maxA = 1;
        for (auto t : take) {
            const auto &tk = tokensOf(t);
            int n = 0;
            for (int s = 0; s < search::kAmberTokenTypes; ++s) n += tk.n[s];
            maxT = std::max(maxT, n);
            maxA = std::max(maxA, tk.nAct);
        }
        const int B = static_cast<int>(take.size());
        const int R = std::max(B, bucketFor(rowBuckets, B));
        const int T = std::max(maxT, bucketFor(tokBuckets, maxT));
        const int A = std::max(maxA, bucketFor(actBuckets, maxA));
        shape = {B, R, T, A};
        std::memset(buf.tokType, 0, static_cast<std::size_t>(R) * T);
        std::memset(buf.ids, 0, sizeof(std::int16_t) * R * T * search::kAmberCat);
        std::memset(buf.f, 0, sizeof(std::uint16_t) * R * T * search::kAmberFloat);
        std::memset(buf.mask, 0, static_cast<std::size_t>(R) * T);
        std::memset(buf.aType, 0, sizeof(std::int16_t) * R * A);
        std::fill(buf.aSrc, buf.aSrc + static_cast<std::size_t>(R) * A, std::int16_t(-1));
        std::fill(buf.aTgt, buf.aTgt + static_cast<std::size_t>(R) * A, std::int16_t(-1));
        std::memset(buf.aF, 0, sizeof(std::uint16_t) * R * A * search::kAmberActFeat);
        std::memset(buf.aMask, 0, static_cast<std::size_t>(R) * A);
        for (int r = 0; r < B; ++r) {
            const auto &tk = tokensOf(take[r]);
            std::array<int, search::kAmberTokenTypes> off{};
            int pos = 0;
            for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                off[s] = pos;
                for (int i = 0; i < tk.n[s]; ++i, ++pos) {
                    const auto &k = tk.tok[search::kAmberOff[s] + i];
                    const std::size_t j = static_cast<std::size_t>(r) * T + pos;
                    buf.tokType[j] = static_cast<std::int8_t>(s);
                    std::memcpy(buf.ids + j * search::kAmberCat, k.ids.data(), sizeof(k.ids));
                    std::memcpy(buf.f + j * search::kAmberFloat, k.f.data(), sizeof(k.f));
                    buf.mask[j] = 1;
                }
            }
            for (int a = 0; a < tk.nAct; ++a) {
                const auto &x = tk.act[a];
                const std::size_t j = static_cast<std::size_t>(r) * A + a;
                buf.aType[j] = x.type;
                buf.aSrc[j] = x.srcSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.srcSeg] + x.srcIdx);
                buf.aTgt[j] = x.tgtSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.tgtSeg] + x.tgtIdx);
                std::memcpy(buf.aF + j * search::kAmberActFeat, x.f.data(), sizeof(x.f));
                buf.aMask[j] = 1;
            }
        }
        for (int r = B; r < R; ++r) {   // padding rows: one live run token and one live action
            buf.mask[static_cast<std::size_t>(r) * T] = 1;
            buf.aMask[static_cast<std::size_t>(r) * A] = 1;
        }
        batches_ += 1;
        batchRows_ += B;
        return take;
    }

    bool Driver::nextBatch(int maxRows, int minRows, int timeoutMs, PackedBatch &out) {
        std::vector<std::uint32_t> take = takeRequests(maxRows, minRows, timeoutMs);
        out.rows = static_cast<int>(take.size());
        out.ticket = take;
        if (take.empty()) return false;
        const int B = out.rows;
        out.slots.fill(0);
        out.actions = 1;
        auto tokensOf = [&](std::uint32_t t) -> const AmberTokens & {
            return workers_[t >> 16]->games[t & 0xffff].tokens;
        };
        for (auto t : take) {
            const auto &tk = tokensOf(t);
            for (int s = 0; s < search::kAmberTokenTypes; ++s) out.slots[s] = std::max<int>(out.slots[s], tk.n[s]);
            out.actions = std::max(out.actions, tk.nAct);
        }
        for (int s = 0; s < search::kAmberTokenTypes; ++s) out.slots[s] = std::max(out.slots[s], 1);
        std::array<int, search::kAmberTokenTypes> off{};
        for (int s = 1; s < search::kAmberTokenTypes; ++s) off[s] = off[s - 1] + out.slots[s - 1];
        for (int s = 0; s < search::kAmberTokenTypes; ++s) {
            const int S = out.slots[s];
            out.ids[s].assign(static_cast<std::size_t>(B) * S * search::kAmberCat, 0);
            out.f[s].assign(static_cast<std::size_t>(B) * S * search::kAmberFloat, 0);
            out.mask[s].assign(static_cast<std::size_t>(B) * S, 0);
        }
        const int A = out.actions;
        out.aType.assign(static_cast<std::size_t>(B) * A, 0);
        out.aSrc.assign(static_cast<std::size_t>(B) * A, -1);
        out.aTgt.assign(static_cast<std::size_t>(B) * A, -1);
        out.aF.assign(static_cast<std::size_t>(B) * A * search::kAmberActFeat, 0);
        out.aMask.assign(static_cast<std::size_t>(B) * A, 0);
        for (int r = 0; r < B; ++r) {
            const auto &tk = tokensOf(take[r]);
            for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                const int S = out.slots[s];
                for (int i = 0; i < tk.n[s]; ++i) {
                    const auto &k = tk.tok[search::kAmberOff[s] + i];
                    std::memcpy(&out.ids[s][(static_cast<std::size_t>(r) * S + i) * search::kAmberCat], k.ids.data(),
                                sizeof(k.ids));
                    std::memcpy(&out.f[s][(static_cast<std::size_t>(r) * S + i) * search::kAmberFloat], k.f.data(),
                                sizeof(k.f));
                    out.mask[s][static_cast<std::size_t>(r) * S + i] = 1;
                }
            }
            for (int a = 0; a < tk.nAct; ++a) {
                const auto &x = tk.act[a];
                const std::size_t j = static_cast<std::size_t>(r) * A + a;
                out.aType[j] = x.type;
                out.aSrc[j] = x.srcSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.srcSeg] + x.srcIdx);
                out.aTgt[j] = x.tgtSeg == search::kAmberNoSeg ? -1 : static_cast<std::int16_t>(off[x.tgtSeg] + x.tgtIdx);
                std::memcpy(&out.aF[j * search::kAmberActFeat], x.f.data(), sizeof(x.f));
                out.aMask[j] = 1;
            }
        }
        batches_ += 1;
        batchRows_ += B;
        return true;
    }

    void Driver::submit(const std::uint32_t *tickets, int rows, int actions, const float *logits, const float *value) {
        // Group by worker so each inbox is locked once.
        thread_local std::vector<std::vector<int>> per;
        per.assign(workers_.size(), {});
        for (int r = 0; r < rows; ++r) {
            const std::uint32_t t = tickets[r];
            Game &g = workers_[t >> 16]->games[t & 0xffff];
            const int na = std::min(g.tokens.nAct, actions);
            g.resLogits.assign(logits + static_cast<std::size_t>(r) * actions,
                               logits + static_cast<std::size_t>(r) * actions + na);
            g.resValue = value[r];
            per[t >> 16].push_back(static_cast<int>(t & 0xffff));
        }
        for (std::size_t w = 0; w < per.size(); ++w) {
            if (per[w].empty()) continue;
            std::lock_guard<std::mutex> l(workers_[w]->im);
            auto &in = workers_[w]->inbox;
            in.insert(in.end(), per[w].begin(), per[w].end());
        }
    }

    void fakeNetEvaluate(const PackedBatch &batch, std::vector<float> &logits, std::vector<float> &value,
                         std::uint64_t &rng) {
        logits.resize(static_cast<std::size_t>(batch.rows) * batch.actions);
        value.resize(batch.rows);
        auto next = [&]() {
            rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
            return static_cast<float>(rng >> 40) / static_cast<float>(1u << 24);
        };
        for (auto &x : logits) x = next();
        for (auto &x : value) x = next();
    }

}
