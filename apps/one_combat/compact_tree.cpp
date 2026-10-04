#include "compact_tree.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <unordered_set>

namespace one_combat {

bool CompactTreeNet::load(const std::string &path, const std::unordered_map<std::string, int> &featureIdx,
                          const char *kind) {
    this->path = path;
    ok = false;
    std::ifstream f(path); if (!f) { std::cerr << kind << ": cannot open " << path << "\n"; return false; }
    std::string tok; int nfeat = 0, ntrees = 0; double baseScore = 0.5;
    f >> tok >> nfeat;
    if (!f || tok != "nfeat" || nfeat < 1 || static_cast<std::size_t>(nfeat) > featureIdx.size()) { std::cerr << kind << ": invalid feature count\n"; return false; }
    sel.resize(nfeat); featureNames.resize(nfeat);
    std::unordered_set<std::string> seenFeatures;
    for (int i = 0; i < nfeat; ++i) { std::string kw, name; f >> kw >> name;
        auto it = featureIdx.find(name);
        if (kw != "feat" || it == featureIdx.end() || !seenFeatures.insert(name).second) {
            std::cerr << kind << ": unknown or duplicate feature: " << name << "\n"; return false; }
        sel[i] = it->second; featureNames[i] = name; }
    f >> tok >> logistic;
    if (!f || tok != "logistic") { std::cerr << kind << ": invalid logistic header\n"; return false; }
    f >> tok >> baseScore;
    if (!f || tok != "base_score" || !std::isfinite(baseScore)) { std::cerr << kind << ": invalid base score\n"; return false; }
    f >> tok >> ntrees;
    if (tok != "ntrees" || !f.good() || ntrees < 1 || (logistic && !(baseScore > 0.0 && baseScore < 1.0))) {
        std::cerr << kind << ": truncated/missing tree count in " << path << "\n"; return false;
    }
    baseMargin = logistic ? std::log(baseScore / (1.0 - baseScore)) : baseScore;
    nodes.clear(); roots.clear(); roots.reserve(ntrees + 1);
    for (int t = 0; t < ntrees; ++t) {
        std::string kw; int ti, nn; f >> kw >> ti >> nn;
        if (!f.good() || kw != "tree" || ti != t || nn < 1) { std::cerr << kind << ": invalid tree " << t << " header in " << path << "\n"; return false; }
        std::vector<Node> tr(nn);
        for (int i = 0; i < nn; ++i) {
            std::string type; f >> type;
            Node nd = { -1, 0.0f, 0, 0 };
            if (type == "L") { double v = 0.0; f >> v; nd = { -1, (float)v, 0, 0 }; }
            else if (type == "S") {
                int fi = 0, y = 0, no = 0; float th = 0.0f; f >> fi >> th >> y >> no;
                if (fi < 0) { std::cerr << kind << ": negative split feature in tree " << t << "\n"; return false; }
                nd = { fi, th, y, no };
            }
            else { std::cerr << kind << ": invalid node tag in tree " << t << "\n"; return false; }
            if (!f.good()) { std::cerr << kind << ": truncated node in tree " << t << " of " << path << "\n"; return false; }
            if (!std::isfinite(nd.thr)) { std::cerr << kind << ": non-finite node in tree " << t << "\n"; return false; }
            tr[i] = nd;
        }
        for (const Node &nd : tr) if (nd.feat >= 0 &&
            (nd.feat >= nfeat || nd.yes < 0 || nd.no < 0 || nd.yes >= nn || nd.no >= nn)) {
            std::cerr << kind << ": invalid split index in tree " << t << "\n"; return false; }
        if (tr.back().feat >= 0) {
            std::cerr << kind << ": final node is not a leaf in tree " << t << "\n"; return false;
        }
        std::vector<unsigned char> visit(nn, 0);
        std::function<bool(int)> validateTree = [&](int node) {
            if (visit[node] == 1) return false;
            if (visit[node] == 2) return true;
            visit[node] = 1;
            const Node &nd = tr[node];
            if (nd.feat >= 0 && (!validateTree(nd.yes) || !validateTree(nd.no))) return false;
            visit[node] = 2;
            return true;
        };
        if (!validateTree(0) || std::find(visit.begin(), visit.end(), 0) != visit.end()) {
            std::cerr << kind << ": cyclic or unreachable node in tree " << t << "\n"; return false;
        }
        roots.push_back(nodes.size());
        for (auto &nd : tr) if (nd.feat >= 0) nd.feat = sel[nd.feat];
        nodes.insert(nodes.end(), tr.begin(), tr.end());
    }
    roots.push_back(nodes.size());
    if (f >> tok) { std::cerr << kind << ": trailing data after " << ntrees << " trees in " << path << "\n"; return false; }
    if (!f.eof()) { std::cerr << kind << ": read failure in " << path << "\n"; return false; }
    ok = true;
    std::cout << "[" << kind << ": " << ntrees << " trees, " << nfeat << " feats from " << path << "]\n";
    return true;
}

double CompactTreeNet::predict(const std::vector<float> &raw) const {
    double m = baseMargin;
    for (std::size_t t = 0; t + 1 < roots.size(); ++t) {
        const Node *tr = nodes.data() + roots[t];
        const int size = static_cast<int>(roots[t + 1] - roots[t]);
        int i = 0, steps = 0;
        while (tr[i].feat >= 0 && ++steps <= size)
            i = (raw[tr[i].feat] < tr[i].thr) ? tr[i].yes : tr[i].no;
        if (steps > size) return std::numeric_limits<double>::quiet_NaN();
        m += tr[i].thr;
    }
    const double out = logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
    return logistic ? std::max(0.0, std::min(1.0, out)) : out;
}

double CompactTreeNet::predictMarginalized(
        const std::vector<float> &raw,
        const std::vector<MarginalFeature> &features) const {
    if (!ok || raw.empty()) return std::numeric_limits<double>::quiet_NaN();

    // The deployed win model is logistic.  Its public-belief value is
    // E[sigmoid(margin)], not sigmoid(E[margin]); the link function is
    // nonlinear.  Enumerate the (small, discrete) pity prior here so the
    // returned value is mathematically the same mixture as the hidden-state
    // particles represented by the caller.
    if (logistic) {
        std::vector<float> particle = raw;
        struct Group { int representative; std::size_t count; };
        std::unordered_map<int, std::size_t> slotByRaw;
        std::vector<std::vector<Group>> groups;
        groups.reserve(features.size());
        for (const auto &feature : features) {
            if (feature.rawIndex < 0 || feature.rawIndex >= static_cast<int>(raw.size())
                    || feature.step <= 0 || feature.low > feature.high)
                return std::numeric_limits<double>::quiet_NaN();
            if (!slotByRaw.emplace(feature.rawIndex, slotByRaw.size()).second)
                return std::numeric_limits<double>::quiet_NaN();
            std::map<std::vector<unsigned char>, Group> bySplits;
            for (int value = feature.low; value <= feature.high; value += feature.step) {
                std::vector<unsigned char> signature;
                for (const auto &node : nodes)
                    if (node.feat == feature.rawIndex)
                        signature.push_back(static_cast<unsigned char>(value < node.thr));
                auto [it, inserted] = bySplits.emplace(std::move(signature), Group{value, 0});
                ++it->second.count;
                if (value > feature.high - feature.step) break;
            }
            std::vector<Group> collapsed;
            for (const auto &[signature, group] : bySplits) collapsed.push_back(group);
            groups.push_back(std::move(collapsed));
        }
        std::vector<std::size_t> stride(groups.size(), 1);
        std::size_t cells = 1;
        for (std::size_t i = groups.size(); i-- > 0;) {
            stride[i] = cells;
            cells *= groups[i].size();
        }
        if (cells == 0) return std::numeric_limits<double>::quiet_NaN();
        std::vector<double> margins(cells, baseMargin);
        const auto treeValue = [&](std::size_t treeIndex) {
            const Node *tree = nodes.data() + roots[treeIndex];
            const int size = static_cast<int>(roots[treeIndex + 1] - roots[treeIndex]);
            int node = 0, steps = 0;
            while (tree[node].feat >= 0 && ++steps <= size)
                node = particle[tree[node].feat] < tree[node].thr ? tree[node].yes : tree[node].no;
            if (steps > size) return std::numeric_limits<double>::quiet_NaN();
            return static_cast<double>(tree[node].thr);
        };
        for (std::size_t t = 0; t + 1 < roots.size(); ++t) {
            std::set<std::size_t> relevant;
            for (std::size_t n = roots[t]; n < roots[t + 1]; ++n) {
                const int feature = nodes[n].feat;
                const auto it = slotByRaw.find(feature);
                if (it != slotByRaw.end()) relevant.insert(it->second);
            }
            if (relevant.empty()) {
                const double contribution = treeValue(t);
                if (!std::isfinite(contribution)) return contribution;
                for (auto &margin : margins) margin += contribution;
            } else if (relevant.size() == 1) {
                const auto slot = *relevant.begin();
                const auto feature = features[slot];
                for (std::size_t group = 0; group < groups[slot].size(); ++group) {
                    particle[feature.rawIndex] = static_cast<float>(groups[slot][group].representative);
                    const double contribution = treeValue(t);
                    if (!std::isfinite(contribution)) return contribution;
                    for (std::size_t cell = 0; cell < cells; ++cell)
                        if ((cell / stride[slot]) % groups[slot].size() == group)
                            margins[cell] += contribution;
                }
            } else {
                // The deployed model currently has only a small number of
                // trees that split on both hidden features. Keep the exact
                // two-dimensional table path explicit and reject a future
                // higher-dimensional marginalization rather than silently
                // changing its probability semantics.
                if (relevant.size() != 2)
                    return std::numeric_limits<double>::quiet_NaN();
                const auto first = *relevant.begin();
                const auto second = *std::next(relevant.begin());
                for (std::size_t a = 0; a < groups[first].size(); ++a)
                    for (std::size_t b = 0; b < groups[second].size(); ++b) {
                        particle[features[first].rawIndex] = static_cast<float>(groups[first][a].representative);
                        particle[features[second].rawIndex] = static_cast<float>(groups[second][b].representative);
                        const double contribution = treeValue(t);
                        if (!std::isfinite(contribution)) return contribution;
                        for (std::size_t cell = 0; cell < cells; ++cell) {
                            if ((cell / stride[first]) % groups[first].size() == a
                                    && (cell / stride[second]) % groups[second].size() == b)
                                margins[cell] += contribution;
                        }
                    }
            }
        }
        double total = 0.0;
        std::size_t totalWeight = 0;
        for (std::size_t cell = 0; cell < cells; ++cell) {
            std::size_t remainder = cell;
            std::size_t weight = 1;
            for (std::size_t i = 0; i < groups.size(); ++i) {
                const std::size_t group = (remainder / stride[i]) % groups[i].size();
                weight *= groups[i][group].count;
            }
            const double probability = 1.0 / (1.0 + std::exp(-margins[cell]));
            total += probability * static_cast<double>(weight);
            totalWeight += weight;
        }
        if (totalWeight == 0)
            return std::numeric_limits<double>::quiet_NaN();
        return total / static_cast<double>(totalWeight);
    }

    std::unordered_map<int, std::size_t> slotByRaw;
    for (const auto &feature : features) {
        if (feature.rawIndex < 0 || feature.rawIndex >= static_cast<int>(raw.size())
                || feature.step <= 0 || feature.low > feature.high)
            return std::numeric_limits<double>::quiet_NaN();
        if (!slotByRaw.emplace(feature.rawIndex, slotByRaw.size()).second)
            return std::numeric_limits<double>::quiet_NaN();
    }

    double margin = baseMargin;
    for (std::size_t t = 0; t + 1 < roots.size(); ++t) {
        const Node *tree = nodes.data() + roots[t];
        const int size = static_cast<int>(roots[t + 1] - roots[t]);
        std::vector<int> lower;
        std::vector<int> upper;
        lower.reserve(features.size());
        upper.reserve(features.size());
        for (const auto &feature : features) {
            lower.push_back(feature.low);
            upper.push_back(feature.high);
        }
        std::function<double(int)> expected = [&](int index) -> double {
            if (index < 0 || index >= size) return std::numeric_limits<double>::quiet_NaN();
            const Node &node = tree[index];
            if (node.feat < 0) return node.thr;
            if (node.feat < 0 || node.feat >= static_cast<int>(raw.size()))
                return std::numeric_limits<double>::quiet_NaN();
            // load() resolves each node's selected-feature index through sel,
            // so the stored node feature is already a raw-vector index just
            // like predict()'s lookup.
            const auto it = slotByRaw.find(node.feat);
            if (it == slotByRaw.end()) {
                const int child = raw[node.feat] < node.thr ? node.yes : node.no;
                return expected(child);
            }
            const std::size_t slot = it->second;
            const auto &prior = features[slot];
            int total = 0, left = 0;
            for (int value = lower[slot]; value <= upper[slot]; value += prior.step) {
                ++total;
                if (static_cast<float>(value) < node.thr) ++left;
                if (value > upper[slot] - prior.step) break;
            }
            if (total <= 0) return std::numeric_limits<double>::quiet_NaN();
            if (left == 0) return expected(node.no);
            if (left == total) return expected(node.yes);
            const double pLeft = static_cast<double>(left) / total;
            const int oldLower = lower[slot], oldUpper = upper[slot];
            lower[slot] = oldLower;
            upper[slot] = oldLower + (left - 1) * prior.step;
            const double yes = expected(node.yes);
            lower[slot] = oldLower + left * prior.step;
            upper[slot] = oldUpper;
            const double no = expected(node.no);
            lower[slot] = oldLower;
            upper[slot] = oldUpper;
            if (!std::isfinite(yes) || !std::isfinite(no))
                return std::numeric_limits<double>::quiet_NaN();
            return pLeft * yes + (1.0 - pLeft) * no;
        };
        const double contribution = expected(0);
        if (!std::isfinite(contribution)) return contribution;
        margin += contribution;
    }
    const double out = logistic ? 1.0 / (1.0 + std::exp(-margin)) : margin;
    return logistic ? std::max(0.0, std::min(1.0, out)) : out;
}

} // namespace one_combat
