// ---- turnplanenum (research, #1058 turn-plan root filter, offline) ----
// one_combat turnplanenum OUT.jsonl [MAX_PLANS=512] [MAX_NODES=20000] < rows.jsonl
// Rows: silverazgen root rows with `wire` and `edges` (the §797 budget-ladder corpus). For each row, rebuilds the
// root from its wire (as rolloutpolicybench does) and enumerates its deterministic turn plans
// (search::enumerateTurnPlans). With STS_SILVER_ROOT_PRIOR set, each plan also carries the best line's summed log
// prior under that policy MLP. Writes one line per row: the row's ids, root action count, the index of each root
// action in the row's `edges` (by action bits, -1 if absent), capped, nodes, merges, execs, thread CPU seconds, and
// the plans as [first-action row-edge indices, end type, log prior, best-prior first row edge, features...]
// (feature names: `one_combat turnplanenum names OUT.json`). Plays no game seed.
#include "one_combat/driver_shared.h"
#include "one_combat/silver_synth_keys.h"

#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SilverTurnPlan.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

#include <cmath>
#include <ctime>

namespace {

    double threadCpu() {
        timespec ts{};
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
        return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
    }

    double round3(double x) { return std::isfinite(x) ? std::round(x * 1000.0) / 1000.0 : -1e9; }

}  // namespace

void turnPlanEnum(const std::string &outPath, int maxPlans, int maxNodes) {
    if (outPath == "names") throw std::runtime_error("turnplanenum: use `turnplanenum names OUT.json`");
    std::ofstream out(outPath);
    if (!out) throw std::runtime_error("turnplanenum: cannot open " + outPath);
    const bool withPrior = !search::nativeSilverRootPriorPath().empty();
    search::TurnPlanPrior prior;
    if (withPrior) {
        prior = [](const BattleContext &bc, const std::vector<search::Action> &actions) {
            std::vector<search::SilverSearcher::Edge> edges;
            edges.reserve(actions.size());
            for (const auto &a : actions) edges.push_back({a});
            return search::nativeSilverPolicyPrior(bc, edges);
        };
    }
    std::string line;
    long long rows = 0;
    while (std::getline(std::cin, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        if (!row.contains("wire") || row.at("wire").is_null()) continue;
        nlohmann::json res = {{"seed", row.at("seed")}, {"fight", row.at("fight")}, {"decision", row.at("decision")}};
        try {
            const auto parsed = row.at("wire").get<silver_bridge::BattleStateWire>();
            const BattleContext bc = search::battleContextFromWire(parsed);
            const auto context = search::searchContextFromWire(parsed);
            const std::uint64_t base = silver_synth::key(row.at("seed").get<std::uint64_t>(),
                                                         row.at("fight").get<std::uint64_t>(),
                                                         row.at("decision").get<std::uint64_t>(), 0x7a9b1a2ULL);
            const BattleContext root = silver_synth::plannerRoot(bc, base);
            search::TurnPlanConfig config;
            config.maxPlans = maxPlans;
            config.maxNodes = maxNodes;
            config.act = row.value("act", 1);
            const double c0 = threadCpu();
            const auto set = search::enumerateTurnPlans(root, context, config, prior);
            const double cpu = threadCpu() - c0;
            const auto &rowEdges = row.at("edges");
            std::vector<int> toRow;
            for (const auto &a : set.rootActions) {
                int e = -1;
                for (std::size_t i = 0; i < rowEdges.size(); ++i)
                    if (rowEdges[i].at("bits").get<std::uint64_t>() == a.bits) e = static_cast<int>(i);
                toRow.push_back(e);
            }
            res["n"] = set.rootActions.size();
            res["toRow"] = toRow;
            res["capped"] = set.capped;
            res["nodes"] = set.nodes;
            res["merges"] = set.merges;
            res["execs"] = set.execs;
            res["cpu"] = cpu;
            nlohmann::json plans = nlohmann::json::array();
            for (const auto &p : set.plans) {
                nlohmann::json first = nlohmann::json::array();
                for (std::size_t i = 0; i < set.rootActions.size(); ++i)
                    if (p.firstMask.test(i)) first.push_back(toRow[i]);
                nlohmann::json v = nlohmann::json::array();
                v.push_back(first);
                v.push_back(static_cast<int>(p.end));
                v.push_back(withPrior ? round3(p.logPrior) : 0.0);
                v.push_back(p.bestFirst >= 0 ? toRow[static_cast<std::size_t>(p.bestFirst)] : -1);
                for (float f : p.features) v.push_back(round3(f));
                plans.push_back(std::move(v));
            }
            res["plans"] = std::move(plans);
        } catch (const std::exception &e) {
            res["error"] = e.what();
        }
        out << res.dump() << '\n';
        ++rows;
    }
    std::cout << "turnplanenum: " << rows << " rows\n";
}

void turnPlanNames(const std::string &outPath) {
    std::ofstream out(outPath);
    if (!out) throw std::runtime_error("turnplanenum: cannot open " + outPath);
    out << nlohmann::json({{"plan", {"first", "end", "logPrior", "bestFirst"}},
                           {"features", search::turnPlanFeatureNames()}}).dump() << '\n';
}
