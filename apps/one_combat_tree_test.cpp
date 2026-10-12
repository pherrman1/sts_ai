// Frozen pre-optimization loader/traversal oracle from PR #183 (6188288).
#include "one_combat/compact_tree.h"
#include "one_combat/run_features.h"
#include <cstring>
#include <cstdint>
#include <random>
struct LegacyTreeNet {
    using Node = one_combat::CompactTreeNet::Node;
    std::vector<std::vector<Node>> trees;
    std::vector<int> sel;
    std::vector<std::string> featureNames;
    std::string path;
    double baseMargin = 0; bool logistic = true, ok = false;
    bool load(const std::string &, const std::unordered_map<std::string,int> &, const char *);
    double predict(const std::vector<float> &) const;
};

#include <algorithm>
#include <cmath>
#include <functional>
#include <fstream>
#include <iostream>
#include <limits>
#include <unordered_set>



bool LegacyTreeNet::load(const std::string &path, const std::unordered_map<std::string, int> &featureIdx,
                          const char *kind) {
    this->path = path;
    ok = false;
    std::ifstream f(path); if (!f) { std::cerr << kind << ": cannot open " << path << "\n"; return false; }
    std::string tok; int nfeat = 0, ntrees = 0; double baseScore = 0.5;
    f >> tok >> nfeat;
    if (tok != "nfeat" || nfeat < 1) { std::cerr << kind << ": invalid feature count\n"; return false; }
    sel.resize(nfeat); featureNames.resize(nfeat);
    std::unordered_set<std::string> seenFeatures;
    for (int i = 0; i < nfeat; ++i) { std::string kw, name; f >> kw >> name;
        auto it = featureIdx.find(name);
        if (kw != "feat" || it == featureIdx.end() || !seenFeatures.insert(name).second) {
            std::cerr << kind << ": unknown or duplicate feature: " << name << "\n"; return false; }
        sel[i] = it->second; featureNames[i] = name; }
    f >> tok >> logistic;
    f >> tok >> baseScore;
    f >> tok >> ntrees;
    if (tok != "ntrees" || !f.good() || ntrees < 1 || (logistic && !(baseScore > 0.0 && baseScore < 1.0))) {
        std::cerr << kind << ": truncated/missing tree count in " << path << "\n"; return false;
    }
    baseMargin = logistic ? std::log(baseScore / (1.0 - baseScore)) : baseScore;
    trees.resize(ntrees);
    for (int t = 0; t < ntrees; ++t) {
        std::string kw; int ti, nn; f >> kw >> ti >> nn;
        if (!f.good() || kw != "tree" || ti != t || nn < 1) { std::cerr << kind << ": invalid tree " << t << " header in " << path << "\n"; return false; }
        trees[t].resize(nn);
        for (int i = 0; i < nn; ++i) {
            std::string type; f >> type;
            Node nd = { -1, 0.0f, 0, 0 };
            if (type == "L") { double v; f >> v; nd = { -1, (float)v, 0, 0 }; }
            else if (type == "S") { int fi = 0, y = 0, no = 0; float th = 0.0f; f >> fi >> th >> y >> no; nd = { fi, th, y, no }; }
            else { std::cerr << kind << ": invalid node tag in tree " << t << "\n"; return false; }
            if (!f.good()) { std::cerr << kind << ": truncated node in tree " << t << " of " << path << "\n"; return false; }
            trees[t][i] = nd;
        }
        for (const Node &nd : trees[t]) if (nd.feat >= 0 &&
            (nd.feat >= nfeat || nd.yes < 0 || nd.no < 0 || nd.yes >= nn || nd.no >= nn)) {
            std::cerr << kind << ": invalid split index in tree " << t << "\n"; return false; }
        if (trees[t].back().feat >= 0) {
            std::cerr << kind << ": final node is not a leaf in tree " << t << "\n"; return false;
        }
        std::vector<unsigned char> visit(nn, 0);
        std::function<bool(int)> validateTree = [&](int node) {
            if (visit[node] == 1) return false;
            if (visit[node] == 2) return true;
            visit[node] = 1;
            const Node &nd = trees[t][node];
            if (nd.feat >= 0 && (!validateTree(nd.yes) || !validateTree(nd.no))) return false;
            visit[node] = 2;
            return true;
        };
        if (!validateTree(0) || std::find(visit.begin(), visit.end(), 0) != visit.end()) {
            std::cerr << kind << ": cyclic or unreachable node in tree " << t << "\n"; return false;
        }
    }
    f >> tok;
    if (!f.eof()) { std::cerr << kind << ": trailing data after " << ntrees << " trees in " << path << "\n"; return false; }
    ok = true;
    std::cout << "[" << kind << ": " << ntrees << " trees, " << nfeat << " feats from " << path << "]\n";
    return true;
}

double LegacyTreeNet::predict(const std::vector<float> &raw) const {
    double m = baseMargin;
    for (const auto &tr : trees) { int i = 0, steps = 0;
        while (tr[i].feat >= 0 && ++steps <= (int)tr.size()) i = (raw[sel[tr[i].feat]] < tr[i].thr) ? tr[i].yes : tr[i].no;
        if (steps > (int)tr.size()) return std::numeric_limits<double>::quiet_NaN();
        m += tr[i].thr; }
    const double out = logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
    return logistic ? std::max(0.0, std::min(1.0, out)) : out;
}



int main(int argc, char **argv) {
    if (argc < 2) return 2;
    // A repeated split on one marginalized feature must condition the second
    // split on the first branch; reusing the unconditional prior at every
    // node gives the wrong expectation.
    one_combat::CompactTreeNet marginal;
    marginal.ok = true; marginal.logistic = false;
    marginal.nodes = {{0, 2.0f, 1, 2}, {0, 1.0f, 3, 4}, {-1, 30.0f, 0, 0},
                      {-1, 10.0f, 0, 0}, {-1, 20.0f, 0, 0}};
    marginal.roots = {0, 5}; marginal.sel = {0};
    const double expected = marginal.predictMarginalized({0.0f}, {{0, 0, 2, 1}});
    if (std::abs(expected - 20.0) > 1e-12) {
        std::cerr << "marginal repeated-split expectation mismatch: " << expected << '\n';
        return 1;
    }
    // Logistic mixtures must average probabilities after the link function.
    // This differs from sigmoid(E[margin]) for a non-degenerate prior.
    one_combat::CompactTreeNet logistic;
    logistic.ok = true; logistic.logistic = true; logistic.baseMargin = 0.0;
    logistic.nodes = {{0, 1.0f, 1, 2}, {-1, 0.0f, 0, 0}, {-1, 2.0f, 0, 0}};
    logistic.roots = {0, 3}; logistic.sel = {0};
    const auto sigmoid = [](double value) { return 1.0 / (1.0 + std::exp(-value)); };
    const double logisticExpected = (sigmoid(0.0) + sigmoid(2.0)
        + sigmoid(2.0)) / 3.0;
    const double logisticActual = logistic.predictMarginalized({0.0f}, {{0, 0, 2, 1}});
    if (std::abs(logisticActual - logisticExpected) > 1e-12
            || std::abs(logisticActual - sigmoid(2.0 / 3.0)) < 1e-3) {
        std::cerr << "logistic marginal expectation mismatch: " << logisticActual
                  << " expected " << logisticExpected << '\n';
        return 1;
    }
    std::uint64_t checks = 0;
    for (int a = 1; a < argc; ++a) {
        LegacyTreeNet old; one_combat::CompactTreeNet current;
        auto idx = one_combat::richIdxMap();
        // E2c has additional inputs. Extend the supplied map as its caller does;
        // retain the live rich mapping for the win/floor artifacts.
        std::ifstream header(argv[a]); std::string tag, name; int nfeat = 0;
        header >> tag >> nfeat;
        for (int i = 0; i < nfeat; ++i) {
            header >> tag >> name;
            if (!idx.count(name)) { const int next = static_cast<int>(idx.size()); idx[name] = next; }
        }
        if (!old.load(argv[a], idx, "legacy") || !current.load(argv[a], idx)) return 1;
        std::vector<std::vector<float>> seen;
        const auto equal = [&](const std::vector<float> &raw) {
            seen.push_back(raw);
            const double x = old.predict(raw), y = current.predict(raw); ++checks;
            if (std::memcmp(&x, &y, sizeof(double)) == 0) return true;
            std::cerr << "tree bitwise prediction mismatch at check " << checks << '\n'; return false;
        };
        std::vector<float> raw(idx.size()); std::mt19937 rng(183);
        for (int i = 0; i < 4096; ++i) {
            for (auto &v : raw) v = float(int(rng() % 10000) - 1000) / 17.0f;
            if (!equal(raw)) return 1;
        }
        unsigned split = 0;
        for (const auto &tr : old.trees) for (const auto &nd : tr) if (nd.feat >= 0) {
            if (++split % 128 != 1) continue;
            const int feature = old.sel[nd.feat];
            for (float v : {std::nextafter(nd.thr, -std::numeric_limits<float>::infinity()),
                           nd.thr, std::nextafter(nd.thr, std::numeric_limits<float>::infinity()),
                           std::numeric_limits<float>::quiet_NaN(),
                           -std::numeric_limits<float>::infinity(), std::numeric_limits<float>::infinity()}) {
                raw[feature] = v; if (!equal(raw)) return 1;
            }
        }
        // Reload the same object: flattened roots/nodes must not retain prior trees.
        if (!current.load(argv[a], idx) || !equal(raw)) return 1;
        // Variant rows must reproduce the one-row predictions bit for bit,
        // including rows that differ outside the declared varying features.
        std::mt19937 variantRng(338);
        std::uint64_t sensitive = 0;
        for (int trial = 0; trial < 64; ++trial) {
            const auto &base = seen[variantRng() % seen.size()];
            std::vector<int> varying;
            const int count = 1 + int(variantRng() % 12);
            for (int k = 0; k < count; ++k) varying.push_back(int(variantRng() % base.size()));
            std::vector<std::vector<float>> rows{base};
            for (int r = 0; r < 48; ++r) {
                auto row = base;
                for (const int index : varying)
                    if (variantRng() % 2) row[index] = seen[variantRng() % seen.size()][index];
                if (r % 16 == 15) row[variantRng() % row.size()] += 1.0f;
                rows.push_back(std::move(row));
            }
            // Rows that change a split feature outside the varying set must
            // still get predict(); valuing them as base would differ here.
            for (const auto &node : current.nodes) {
                if (node.feat < 0 || std::find(varying.begin(), varying.end(), node.feat) != varying.end()) continue;
                for (const float value : {-std::numeric_limits<float>::infinity(), std::numeric_limits<float>::infinity()}) {
                    auto row = base; row[node.feat] = value;
                    auto asBase = row; asBase[node.feat] = base[node.feat];
                    const double y = current.predict(row), z = current.predict(asBase);
                    if (std::memcmp(&y, &z, sizeof(double)) != 0) { rows.push_back(std::move(row)); ++sensitive; break; }
                }
                if (rows.size() > 56) break;
            }
            std::vector<double> values;
            current.predictVariants(base, varying, rows, values);
            if (values.size() != rows.size()) { std::cerr << "tree variant size mismatch\n"; return 1; }
            for (std::size_t r = 0; r < rows.size(); ++r) {
                const double y = current.predict(rows[r]); ++checks;
                if (std::memcmp(&values[r], &y, sizeof(double)) != 0) {
                    std::cerr << "tree variant bitwise mismatch at trial " << trial << " row " << r << '\n'; return 1;
                }
            }
        }
        if (sensitive == 0) { std::cerr << "tree variant test found no outside-feature row\n"; return 1; }
    }
    std::cout << "compact tree parity: " << checks << " bitwise double comparisons\n";
    return 0;
}
