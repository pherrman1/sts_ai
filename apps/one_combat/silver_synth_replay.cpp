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
// Rows are sparse: OUT.nnz (uint32 per row), OUT.idx (uint16 per value),
// OUT.val (float32 per value) and one OUT.meta.jsonl line per row.
//
// silversynthreplay: one task per line ({id, wire, bits, prior|null, weight,
// budgets, seeds}); for each seed a fresh native Silver root search, with the
// optional root prior bonus, reports the most visited action at each budget.
// "prior": "native" uses the backend's STS_SILVER_ROOT_PRIOR model (its
// normalized prior is echoed). `silversynthreplay names OUT.json` instead
// writes the policy feature names (for the model exporter) and exits.

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
    m.update({{"k", "state"}, {"act", row.at("act")}, {"floor", row.at("floor")}, {"room", row.at("room")},
              {"encounter", row.at("encounter")}, {"turn", row.at("turn")}, {"hp", row.at("hp")},
              {"inheritedVisits", row.at("inheritedVisits")}, {"edges", bits.size()},
              {"second", hasSecond}, {"cont", hasCont}});
    out.writeState(state.bc, m);
    const auto &edges = scorer.rootNode().edges;
    for (std::size_t e = 0; e < edges.size(); ++e) {
        nlohmann::json a = {{"k", "act"}, {"e", e}, {"bits", bits[e]}, {"visits", recorded[e].at("visits")},
                            {"q", recorded[e].at("q")}};
        if (hasSecond) {
            a["q2"] = edgeQ(row.at("second"), bits[e]);
            for (const auto &s : row.at("second"))
                if (s.at("bits").get<std::uint64_t>() == bits[e]) a["visits2"] = s.at("visits");
        }
        out.writeAction(state.bc, edges[e].action, a);
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
