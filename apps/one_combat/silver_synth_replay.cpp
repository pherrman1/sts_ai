// Research-only offline harness for the silversynthgen corpus (Gate A / Gate
// B of the synthetic Silver prior pilot). Both modes read corpus-style JSONL
// on stdin and rebuild each recorded search state from its wire; neither plays
// a game seed.
//
// silversynthfeatures OUT_PREFIX: combat features (combatExtractFeatures /
// combatFillActionFeatures) for every leaf and root row, plus, on roots with
// continuation labels, each root action's child states: the generator's two
// label children (same keys, so each pairs with its recorded continuation
// value) and a probe child with four independent SilverRolloutAgent rollouts.
// Every root action row is followed by an "after" row: the state features of
// one sampled outcome of that action.
// Each action row's meta carries "tgt", the targeted monster slot
// (combatActionTargetSlot, -1 when none), for the MLP prior's target gather.
// Each root's state row carries "winNow", SilverSearcher::winNowValue of the
// root (Silver's victory score if the fight ended there, referenced to it).
// Rows are sparse: OUT.nnz (uint32 per row), OUT.idx (uint16 per value),
// OUT.val (float32 per value) and one OUT.meta.jsonl line per row.
//
// silversynthreplay: one task per line ({id, wire, bits, prior|null, weight,
// budgets, seeds}); for each seed a fresh native Silver root search, with the
// optional root prior bonus, reports the most visited action at each budget.
// "prior": "native" uses the backend's STS_SILVER_ROOT_PRIOR model (its
// normalized prior is echoed). `silversynthreplay names OUT.json` instead
// writes the policy feature names (for the model exporter) and exits.
//
// silverpolicymlpcheck MODEL FEATURE_PREFIX OUT.txt [GBM_MODEL]: scores every
// root of a silversynthfeatures file with a combat_policy_mlp_v1 model (one
// logit per action row, in file order, for the Python parity check) and times
// the MLP, and optionally a combat_policy_trees_v1 model, per root.

#include "one_combat/driver_shared.h"
#include "one_combat/silver_synth_keys.h"

#include "sim/search/CombatValueNet.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace {

using silver_synth::key;
using silver_synth::plannerRoot;

constexpr int kProbeRollouts = 4;

struct WireState {
    BattleContext bc;
    search::SilverSearchContext context;
};

WireState fromWire(const nlohmann::json &wire) {
    const auto parsed = wire.get<silver_bridge::BattleStateWire>();
    return {search::battleContextFromWire(parsed), search::searchContextFromWire(parsed)};
}

std::vector<std::uint64_t> edgeBits(const search::SilverSearcher &searcher) {
    std::vector<std::uint64_t> bits;
    for (const auto &edge : searcher.rootNode().edges) bits.push_back(edge.action.bits);
    return bits;
}

struct SparseRows {
    std::ofstream nnz, idx, val, meta;
    std::vector<float> state = std::vector<float>(search::combatFeatureCount());
    std::vector<float> action = std::vector<float>(search::combatPolicyFeatureCount() - search::combatFeatureCount());
    long long rows = 0;

    explicit SparseRows(const std::string &prefix) {
        for (const auto &suffix : {".nnz", ".idx", ".val", ".meta.jsonl"})
            if (std::filesystem::exists(prefix + suffix))
                throw std::runtime_error("silversynthfeatures: refusing to overwrite " + prefix + suffix);
        nnz.open(prefix + ".nnz", std::ios::binary);
        idx.open(prefix + ".idx", std::ios::binary);
        val.open(prefix + ".val", std::ios::binary);
        meta.open(prefix + ".meta.jsonl");
        if (!nnz || !idx || !val || !meta) throw std::runtime_error("silversynthfeatures: cannot open " + prefix);
    }

    void write(const std::vector<float> &features, int offset, const nlohmann::json &m) {
        std::uint32_t count = 0;
        for (int i = 0; i < static_cast<int>(features.size()); ++i) {
            if (features[i] == 0.f) continue;
            const auto j = static_cast<std::uint16_t>(offset + i);
            idx.write(reinterpret_cast<const char *>(&j), sizeof j);
            val.write(reinterpret_cast<const char *>(&features[i]), sizeof(float));
            ++count;
        }
        nnz.write(reinterpret_cast<const char *>(&count), sizeof count);
        meta << m.dump() << '\n';
        ++rows;
    }

    void writeState(const BattleContext &bc, const nlohmann::json &m) {
        search::combatExtractFeatures(bc, state.data());
        write(state, 0, m);
    }

    void writeAction(const BattleContext &bc, const search::Action &a, const nlohmann::json &m) {
        search::combatFillActionFeatures(bc, a, action.data());
        write(action, search::combatFeatureCount(), m);
    }
};

nlohmann::json rowId(const nlohmann::json &row) {
    return {{"seed", row.at("seed")}, {"variant", row.at("variant")}, {"fight", row.at("fight")},
            {"decision", row.at("decision")}};
}

nlohmann::json edgeQ(const nlohmann::json &edges, std::uint64_t bits) {
    for (const auto &e : edges)
        if (e.at("bits").get<std::uint64_t>() == bits) return e.at("q");
    return nullptr;
}

void featurizeRoot(const nlohmann::json &row, SparseRows &out, std::map<std::string, long long> &counts) {
    const auto state = fromWire(row.at("wire"));
    const auto id = rowId(row);
    const std::uint64_t rootKey = key(row.at("seed").get<std::uint64_t>(), row.at("fight").get<int>(),
                                      row.at("decision").get<int>());
    search::SilverSearcher scorer(plannerRoot(state.bc, key(rootKey, 9)), state.context);
    scorer.prepareRootActions();
    const auto &recorded = row.at("edges");
    const auto bits = edgeBits(scorer);
    bool same = bits.size() == recorded.size();
    for (std::size_t i = 0; same && i < bits.size(); ++i) same = bits[i] == recorded[i].at("bits").get<std::uint64_t>();
    if (!same) { ++counts["rootEdgeMismatch"]; return; }

    const bool hasSecond = row.contains("second");
    const bool hasCont = row.contains("continuations");
    auto m = id;
    BattleContext winNowState = state.bc;
    m.update({{"k", "state"}, {"act", row.at("act")}, {"floor", row.at("floor")}, {"room", row.at("room")},
              {"encounter", row.at("encounter")}, {"turn", row.at("turn")}, {"hp", row.at("hp")},
              {"inheritedVisits", row.at("inheritedVisits")}, {"edges", bits.size()},
              {"second", hasSecond}, {"cont", hasCont}, {"winNow", scorer.winNowValue(winNowState)}});
    out.writeState(state.bc, m);
    const auto &edges = scorer.rootNode().edges;
    for (std::size_t e = 0; e < edges.size(); ++e) {
        nlohmann::json a = {{"k", "act"}, {"e", e}, {"bits", bits[e]}, {"visits", recorded[e].at("visits")},
                            {"q", recorded[e].at("q")},
                            {"tgt", search::combatActionTargetSlot(state.bc, edges[e].action)}};
        if (hasSecond) {
            a["q2"] = edgeQ(row.at("second"), bits[e]);
            for (const auto &s : row.at("second"))
                if (s.at("bits").get<std::uint64_t>() == bits[e]) a["visits2"] = s.at("visits");
        }
        out.writeAction(state.bc, edges[e].action, a);
        // Post-action state (one sampled outcome), for afterstate-based priors.
        BattleContext after = state.bc;
        search::seedSearchRng(after, key(rootKey, 11, e));
        edges[e].action.execute(after);
        out.writeState(after, {{"k", "after"}, {"e", e}, {"terminal", after.outcome != Outcome::UNDECIDED}});
    }
    ++counts["roots"];
    if (!hasCont) return;

    const auto &labels = row.at("continuations");
    for (std::size_t e = 0; e < edges.size(); ++e) {
        const auto &reps = labels.at(e).at("reps");
        for (int rep = 0; rep < static_cast<int>(reps.size()); ++rep) {
            BattleContext world = state.bc;
            search::seedSearchRng(world, key(rootKey, 3, e, rep));
            edges[e].action.execute(world);
            const bool terminal = world.outcome != Outcome::UNDECIDED;
            out.writeState(world, {{"k", "child"}, {"role", "label"}, {"e", e}, {"rep", rep},
                                   {"terminal", terminal}, {"valid", reps[rep].at("valid")},
                                   {"value", reps[rep].at("value")}});
            ++counts["labelChildren"];
        }
        std::vector<double> rollouts;
        BattleContext probe;
        for (int r = 0; r < kProbeRollouts; ++r) {
            BattleContext world = state.bc;
            search::seedSearchRng(world, key(rootKey, 7, e, r));
            edges[e].action.execute(world);
            if (r == 0) probe = world;
            rollouts.push_back(scorer.rolloutValue(world));
        }
        const bool terminal = probe.outcome != Outcome::UNDECIDED;
        out.writeState(probe, {{"k", "child"}, {"role", "probe"}, {"e", e}, {"terminal", terminal},
                               {"exact", terminal ? nlohmann::json(scorer.scoreEndState(probe)) : nlohmann::json(nullptr)},
                               {"rollouts", rollouts}});
    }
    ++counts["contRoots"];
}

}  // namespace

void silverSynthFeatures(const std::string &outPrefix) {
    search::g_richCombatFeatures = true;
    SparseRows out(outPrefix);
    std::map<std::string, long long> counts;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        const auto kind = row.at("kind").get<std::string>();
        if (kind == "fight") continue;
        if (row.at("wire").is_null()) { ++counts["noWire"]; continue; }
        try {
            if (kind == "leaf") {
                auto m = rowId(row);
                m.update({{"k", "leaf"}, {"sample", row.at("sample")}, {"pathNodes", row.at("pathNodes")},
                          {"value", row.at("rolloutValue")}});
                out.writeState(fromWire(row.at("wire")).bc, m);
                ++counts["leaves"];
            } else if (kind == "root") {
                featurizeRoot(row, out, counts);
            }
        } catch (const std::exception &e) {
            ++counts[std::string("error:") + e.what()];
        }
    }
    nlohmann::json summary = {{"rows", out.rows}, {"stateFeatures", search::combatFeatureCount()},
                              {"policyFeatures", search::combatPolicyFeatureCount()},
                              {"producerGitSha", trainingExecutableGitSha()}};
    for (const auto &[k, v] : counts) summary["counts"][k] = v;
    std::ofstream(outPrefix + ".summary.json") << summary.dump(2) << '\n';
    std::cout << summary.dump() << '\n';
}

void silverSynthReplay(const std::string &namesPath) {
    if (!namesPath.empty()) {
        std::ofstream(namesPath) << nlohmann::json(search::combatPolicyFeatureNames()).dump() << '\n';
        return;
    }
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        const auto task = nlohmann::json::parse(line);
        nlohmann::json result = {{"id", task.at("id")}, {"ok", true}, {"runs", nlohmann::json::array()}};
        try {
            const auto state = fromWire(task.at("wire"));
            const auto want = task.at("bits").get<std::vector<std::uint64_t>>();
            auto budgets = task.at("budgets").get<std::vector<std::int64_t>>();
            std::sort(budgets.begin(), budgets.end());
            for (const auto seed : task.at("seeds").get<std::vector<std::uint64_t>>()) {
                search::SilverSearcher searcher(plannerRoot(state.bc, seed), state.context);
                searcher.prepareRootActions();
                if (edgeBits(searcher) != want) {
                    result["ok"] = false;
                    result["error"] = "edge_mismatch";
                    break;
                }
                if (task.at("prior").is_string()) {
                    // "native": the backend's STS_SILVER_ROOT_PRIOR model.
                    searcher.rootPrior = search::nativeSilverRootPrior(searcher);
                    if (searcher.rootPrior.empty()) throw std::runtime_error("native root prior is off");
                    searcher.rootPriorWeight = task.at("weight").get<double>();
                } else if (!task.at("prior").is_null()) {
                    searcher.rootPrior = task.at("prior").get<std::vector<double>>();
                    searcher.rootPriorWeight = task.at("weight").get<double>();
                }
                std::int64_t done = 0;
                for (const auto budget : budgets) {
                    searcher.search(budget - done);
                    done = budget;
                    std::vector<std::int32_t> visits;
                    for (const auto &edge : searcher.rootNode().edges) visits.push_back(edge.visitCount);
                    if (budget == budgets.front() && seed == task.at("seeds").at(0) && task.at("prior").is_string())
                        result["prior"] = searcher.rootPrior;
                    result["runs"].push_back({{"seed", seed}, {"budget", budget},
                                              {"chosen", searcher.bestAction().bits}, {"visits", visits}});
                }
            }
        } catch (const std::exception &e) {
            result["ok"] = false;
            result["error"] = e.what();
        }
        std::cout << result.dump() << '\n';
    }
}

void silverPolicyMlpCheck(const std::string &modelPath, const std::string &prefix, const std::string &outPath,
                          const std::string &gbmPath) {
    search::CombatValueNet net;
    if (!net.load(modelPath) || !net.isPolicyMlp)
        throw std::runtime_error("silverpolicymlpcheck: cannot load a combat_policy_mlp_v1/v2 model from " + modelPath);
    const int S = search::combatFeatureCount();
    const int A = search::combatPolicyFeatureCount() - S;
    auto readAll = [&](const std::string &suffix, std::size_t width) {
        std::ifstream f(prefix + suffix, std::ios::binary | std::ios::ate);
        if (!f) throw std::runtime_error("silverpolicymlpcheck: cannot open " + prefix + suffix);
        std::string bytes(static_cast<std::size_t>(f.tellg()), '\0');
        f.seekg(0);
        f.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        if (bytes.size() % width) throw std::runtime_error("silverpolicymlpcheck: truncated " + suffix);
        return bytes;
    };
    const auto nnzBytes = readAll(".nnz", 4), idxBytes = readAll(".idx", 2), valBytes = readAll(".val", 4);
    const auto *nnz = reinterpret_cast<const std::uint32_t *>(nnzBytes.data());
    const auto *idx = reinterpret_cast<const std::uint16_t *>(idxBytes.data());
    const auto *val = reinterpret_cast<const float *>(valBytes.data());
    struct Root { std::vector<float> state; std::vector<float> actions; std::vector<int> targets; };
    std::vector<Root> roots;
    std::ifstream meta(prefix + ".meta.jsonl");
    std::string line;
    std::size_t off = 0, rows = nnzBytes.size() / 4;
    Root *cur = nullptr;
    for (std::size_t r = 0; r < rows; ++r) {
        if (!std::getline(meta, line)) throw std::runtime_error("silverpolicymlpcheck: meta shorter than rows");
        const auto m = nlohmann::json::parse(line);
        const auto k = m.at("k").get<std::string>();
        if (k == "state") {
            roots.push_back({std::vector<float>(S, 0.f), {}, {}});
            cur = &roots.back();
            for (std::uint32_t j = 0; j < nnz[r]; ++j) cur->state.at(idx[off + j]) = val[off + j];
        } else if (k == "act" && cur) {
            const std::size_t b = cur->actions.size();
            cur->actions.resize(b + A, 0.f);
            for (std::uint32_t j = 0; j < nnz[r]; ++j) cur->actions.at(b + idx[off + j] - S) = val[off + j];
            cur->targets.push_back(m.at("tgt").get<int>());
        } else if (k == "leaf") {
            cur = nullptr;
        }
        off += nnz[r];
    }
    std::vector<double> out;
    std::ofstream dump(outPath);
    dump.precision(9);
    using Clock = std::chrono::steady_clock;
    std::size_t edges = 0, scored = 0;
    for (const auto &root : roots) if (!root.targets.empty()) { edges += root.targets.size(); ++scored; }
    double bestMlp = 1e300;
    for (int rep = 0; rep < 3; ++rep) {
        double sink = 0;
        const auto t0 = Clock::now();
        for (const auto &root : roots) {
            const int n = static_cast<int>(root.targets.size());
            if (!n) continue;
            out.resize(n);
            net.predictPolicyMlp(root.state.data(), root.actions.data(), root.targets.data(), n, out.data());
            sink += out[0];
            if (rep == 0) for (const double x : out) dump << x << '\n';
        }
        const double us = std::chrono::duration<double, std::micro>(Clock::now() - t0).count() / scored;
        bestMlp = std::min(bestMlp, us + 0 * sink);
    }
    nlohmann::json report = {{"roots", scored}, {"edges", edges}, {"mlp", net.description()},
                             {"mlpUsPerRoot", bestMlp}};
    if (!gbmPath.empty()) {
        search::CombatValueNet gbm;
        if (!gbm.load(gbmPath) || !gbm.isPolicy || gbm.trees.empty())
            throw std::runtime_error("silverpolicymlpcheck: cannot load policy trees from " + gbmPath);
        double best = 1e300;
        for (int rep = 0; rep < 3; ++rep) {
            double sink = 0;
            const auto t0 = Clock::now();
            for (const auto &root : roots) {
                const int n = static_cast<int>(root.targets.size());
                if (!n) continue;
                out.resize(n);
                gbm.predictPolicyActions(root.state.data(), root.actions.data(), n, out.data());
                sink += out[0];
            }
            const double us = std::chrono::duration<double, std::micro>(Clock::now() - t0).count() / scored;
            best = std::min(best, us + 0 * sink);
        }
        report["gbmUsPerRoot"] = best;
        report["gbmTrees"] = gbm.trees.size();
    }
    std::cout << report.dump() << '\n';
}

// ---- rolloutpolicybench (research, cheap rollouts 2026-11-13) ----
// one_combat rolloutpolicybench OUT_PREFIX BUDGET ARMS CAPTURE_STRIDE < rows.jsonl
// Rows: silverazgen root rows with `wire` (the §797 budget-ladder corpus, prior-playout roots). For every row and arm
// (comma list of asplayed, greedy, tt, ftN, argmax), a fresh Gumbel K16 root search with max backup 4 at BUDGET simulations,
// configured as a whole-run boss-room search (root prior STS_SILVER_ROOT_PRIOR at its weight, tree prior K=8, rollout
// root table from the same model, prior playouts unless greedy). Writes OUT_PREFIX.jsonl (one line per row and arm:
// thread CPU seconds, simulations, rolloutPrior calls, playout actions, the pick's index in the row's edges and the
// prior-step timing split of the asplayed arm) and, when CAPTURE_STRIDE > 0, every CAPTURE_STRIDE-th rolloutPrior call
// of the asplayed arm as silversynthfeatures-style sparse rows (OUT_PREFIX.nnz/.idx/.val/.meta.jsonl; a state row,
// then one act row per edge with `visits` = round(1e6 * prior), the teacher's distribution) for student training.
// Plays no game seed.
void rolloutPolicyBench(const std::string &prefix, std::int64_t budget, const std::string &armList, int captureStride) {
    const auto &priorPath = search::nativeSilverRootPriorPath();
    if (priorPath.empty()) throw std::runtime_error("rolloutpolicybench: needs STS_SILVER_ROOT_PRIOR");
    search::CombatValueNet tableNet;
    if (!tableNet.load(priorPath) || !tableNet.isPolicyMlp)
        throw std::runtime_error("rolloutpolicybench: STS_SILVER_ROOT_PRIOR must be a policy MLP");
    std::vector<std::string> arms;
    {
        std::stringstream ss(armList);
        std::string a;
        while (std::getline(ss, a, ',')) arms.push_back(a);
    }
    std::ofstream out(prefix + ".jsonl");
    if (!out) throw std::runtime_error("rolloutpolicybench: cannot open " + prefix + ".jsonl");
    std::unique_ptr<SparseRows> capture;
    if (captureStride > 0) capture = std::make_unique<SparseRows>(prefix);
    auto cpuNow = [] {
        timespec ts{};
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
        return ts.tv_sec + ts.tv_nsec * 1e-9;
    };
    std::map<std::string, std::unique_ptr<search::CombatValueNet>> students;
    std::string line;
    long long calls = 0, captured = 0;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        if (!row.contains("wire") || row.at("wire").is_null()) continue;
        const auto state = fromWire(row.at("wire"));
        const auto &rowEdges = row.at("edges");
        const std::uint64_t base = key(row.at("seed").get<std::uint64_t>(), row.at("fight").get<std::uint64_t>(),
                                       row.at("decision").get<std::uint64_t>(), 0x5eedb0a7ULL);
        for (const auto &arm : arms) {
            nlohmann::json res = {{"seed", row.at("seed")}, {"fight", row.at("fight")}, {"decision", row.at("decision")},
                                  {"encounter", row.at("encounter")}, {"act", row.at("act")}, {"room", row.at("room")},
                                  {"arm", arm}, {"budget", budget}};
            try {
                search::SilverSearcher s(plannerRoot(state.bc, base), state.context);
                s.prepareRootActions();
                if (s.rootNode().edges.size() < 2) { res["error"] = "single_edge"; out << res.dump() << '\n'; continue; }
                s.maxBackupMinVisits = 4;
                s.rootPrior = search::nativeSilverRootPrior(s);
                s.rootPriorWeight = search::nativeSilverRootPriorWeight();
                s.nodePrior = search::nativeSilverPolicyPrior;
                s.treePriorMinVisits = 8;
                search::nativeSilverRolloutRootTable(s.rootSearchState(), tableNet, s.rootCardTable);
                s.rolloutConfig.cardTable = s.rootCardTable.data();
                auto &rc = s.rolloutConfig;
                rc.prior = arm != "greedy";
                // st=PATH / sttt=PATH: a student policy MLP every playout step / once per playout turn.
                const search::CombatValueNet *student = nullptr;
                std::string policy = arm;
                if (const auto eq = arm.find('='); eq != std::string::npos) {
                    policy = arm.substr(0, eq);
                    auto &slot = students[arm.substr(eq + 1)];
                    if (!slot) {
                        slot = std::make_unique<search::CombatValueNet>();
                        if (!slot->load(arm.substr(eq + 1)) || !slot->isPolicyMlp)
                            throw std::runtime_error("cannot load student " + arm.substr(eq + 1));
                    }
                    student = slot.get();
                    if (policy != "st" && policy != "sttt") throw std::runtime_error("unknown arm " + arm);
                    rc.priorTurnTable = policy == "sttt";
                } else if (arm == "tt") rc.priorTurnTable = true;
                else if (arm.size() == 3 && arm.rfind("ft", 0) == 0) rc.priorTurns = arm[2] - '0';
                else if (arm != "asplayed" && arm != "greedy" && arm != "argmax") throw std::runtime_error("unknown arm " + arm);
                const bool teacher = arm == "asplayed";
                s.rolloutPrior = [&, teacher, student](const BattleContext &bc, const std::vector<search::SilverSearcher::Edge> &edges) {
                    auto p = student ? search::nativeSilverPolicyPriorWith(*student, bc, edges)
                                     : search::nativeSilverPolicyPrior(bc, edges);
                    if (teacher && capture && ++calls % captureStride == 0) {
                        nlohmann::json m = {{"k", "state"}, {"variant", "natural"}, {"seed", row.at("seed")},
                                            {"fight", row.at("fight")}, {"decision", row.at("decision")},
                                            {"enc", row.at("encounter")}, {"turn", bc.turn}};
                        capture->writeState(bc, m);
                        for (std::size_t i = 0; i < edges.size(); ++i)
                            capture->writeAction(bc, edges[i].action,
                                {{"k", "act"}, {"tgt", search::combatActionTargetSlot(bc, edges[i].action)},
                                 {"visits", std::llround(1e6 * p[i])}});
                        ++captured;
                    }
                    return p;
                };
                // argmax (#1051): the production prior playout (nativeSilverPolicyArgmax, with its exact pick cache
                // STS_SILVER_PRIOR_PICK_CACHE), no timing hooks; records the cache's lookups and hits and the root
                // edges' visit counts (bit-identity check against STS_SILVER_PRIOR_PICK_CACHE=0).
                const bool production = arm == "argmax";
                if (production) {
                    s.rolloutPrior = search::nativeSilverPolicyPrior;
                    s.rolloutPriorArgmax = search::nativeSilverPolicyArgmax;
                    s.rolloutPriorArgmaxOf = search::nativeSilverPolicyPrior;
                }
                const auto cache0 = search::nativeSilverPriorPickCacheStats();
                search::NativeSilverPriorTiming timing;
                search::g_nativeSilverPriorTiming = rc.prior && !production ? &timing : nullptr;
                search::SilverSearcher::GumbelRoot g;
                g.k = 16;
                const double c0 = cpuNow();
                const auto sims = s.searchGumbelRoot(budget, g, base ^ 0x9e3779b97f4a7c15ULL);
                const double cpu = cpuNow() - c0;
                search::g_nativeSilverPriorTiming = nullptr;
                const auto pick = s.bestAction().bits;
                int edge = -1;
                for (std::size_t e = 0; e < rowEdges.size(); ++e)
                    if (rowEdges[e].at("bits").get<std::uint64_t>() == pick) edge = static_cast<int>(e);
                res["cpu"] = cpu;
                res["sims"] = sims;
                res["priorCalls"] = s.stats.rolloutPriorCalls;
                res["playoutActions"] = s.stats.rolloutActions;
                res["playouts"] = s.stats.rolloutPlayouts;
                res["edge"] = edge;
                if (production) {
                    const auto cache1 = search::nativeSilverPriorPickCacheStats();
                    res["cacheLookups"] = cache1.lookups - cache0.lookups;
                    res["cacheHits"] = cache1.hits - cache0.hits;
                    std::vector<std::int32_t> visits;
                    for (const auto &e : s.rootNode().edges) visits.push_back(e.visitCount);
                    res["rootVisits"] = visits;
                } else if (rc.prior)
                    res["timing"] = {{"featureSeconds", timing.featureSeconds}, {"mlpSeconds", timing.mlpSeconds},
                                     {"calls", timing.calls}, {"edges", timing.edges}};
            } catch (const std::exception &e) {
                search::g_nativeSilverPriorTiming = nullptr;
                res["error"] = e.what();
            }
            out << res.dump() << '\n';
        }
    }
    std::cout << "rolloutpolicybench: captured " << captured << " prior calls of " << calls << '\n';
}
