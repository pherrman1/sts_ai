#include "compact_tree.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <functional>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
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
    if (!pack()) { std::cerr << kind << ": cannot pack trees of " << path << "\n"; return false; }
    ok = true;
    std::cout << "[" << kind << ": " << ntrees << " trees, " << nfeat << " feats from " << path << "]\n";
    return true;
}

bool CompactTreeNet::pack() {
    packed.clear(); packedRoots.clear();
    if (roots.empty()) return true;
    if (roots.front() != 0 || roots.back() != nodes.size()) return false;
    std::vector<PackedNode> out;
    std::vector<std::uint32_t> outRoots;
    struct Visit { int node; std::size_t parent; };
    std::vector<Visit> todo;
    for (std::size_t t = 0; t + 1 < roots.size(); ++t) {
        if (roots[t] > roots[t + 1] || roots[t + 1] > nodes.size()) return false;
        const Node *tr = nodes.data() + roots[t];
        const int size = static_cast<int>(roots[t + 1] - roots[t]);
        if (size < 1 || size >= kPackedLeaf) return false;
        const std::size_t start = out.size();
        outRoots.push_back(static_cast<std::uint32_t>(start));
        std::vector<unsigned char> seen(size, 0);
        // Preorder: a node's yes subtree follows it; its no child's offset is
        // patched in when that child is emitted.
        todo.assign(1, {0, SIZE_MAX});
        while (!todo.empty()) {
            const Visit v = todo.back(); todo.pop_back();
            if (v.node < 0 || v.node >= size || seen[v.node]) return false;
            seen[v.node] = 1;
            const std::size_t at = out.size();
            if (at - start >= kPackedLeaf) return false;
            if (v.parent != SIZE_MAX) out[v.parent].no = static_cast<std::uint16_t>(at - start);
            const Node &nd = tr[v.node];
            if (nd.feat < 0) {
                out.push_back({kPackedLeaf, 0, nd.thr});
                continue;
            }
            if (nd.feat >= kPackedLeaf) return false;
            out.push_back({static_cast<std::uint16_t>(nd.feat), 0, nd.thr});
            todo.push_back({nd.no, at});
            todo.push_back({nd.yes, SIZE_MAX});
        }
        if (out.size() - start != static_cast<std::size_t>(size)) return false; // unreachable node
    }
    outRoots.push_back(static_cast<std::uint32_t>(out.size()));
    packed = std::move(out); packedRoots = std::move(outRoots);
    return true;
}

bool CompactTreeNet::packedCurrent() const {
    return packedRoots.size() == roots.size() && packed.size() == nodes.size();
}

double CompactTreeNet::predict(const std::vector<float> &raw) const {
    const double m = margin(raw);
    if (std::isnan(m)) return m;  // malformed directly filled tree
    const double out = logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
    return logistic ? std::max(0.0, std::min(1.0, out)) : out;
}

double CompactTreeNet::margin(const std::vector<float> &raw) const {
    double m = baseMargin;
    if (!packedCurrent()) {
        // Trees filled in directly (tests): walk nodes, with the cycle guard.
        for (std::size_t t = 0; t + 1 < roots.size(); ++t) {
            const Node *tr = nodes.data() + roots[t];
            const int size = static_cast<int>(roots[t + 1] - roots[t]);
            int i = 0, steps = 0;
            while (tr[i].feat >= 0 && ++steps <= size)
                i = (raw[tr[i].feat] < tr[i].thr) ? tr[i].yes : tr[i].no;
            if (steps > size) return std::numeric_limits<double>::quiet_NaN();
            m += tr[i].thr;
        }
    } else {
        for (std::size_t t = 0; t + 1 < packedRoots.size(); ++t) {
            const PackedNode *tr = packed.data() + packedRoots[t];
            int i = 0;
            while (tr[i].feat != kPackedLeaf)
                i = (raw[tr[i].feat] < tr[i].thr) ? i + 1 : tr[i].no;
            m += tr[i].thr;
        }
    }
    return m;
}

void CompactTreeNet::predictVariants(const std::vector<float> &base, const std::vector<int> &varying,
                                     const std::vector<std::vector<float>> &rows,
                                     std::vector<double> &out) const {
    out.assign(rows.size(), 0.0);
    std::vector<unsigned char> isVarying(base.size(), 0);
    std::vector<int> distinct;
    for (const int index : varying)
        if (index >= 0 && index < static_cast<int>(base.size()) && !isVarying[index]) {
            isVarying[index] = 1;
            distinct.push_back(index);
        }
    // Rows that differ from base outside the varying features take predict().
    std::vector<std::size_t> exact;
    std::vector<float> values;
    for (std::size_t r = 0; r < rows.size(); ++r) {
        bool same = rows[r].size() == base.size();
        for (std::size_t i = 0; same && i < base.size(); ++i)
            same = isVarying[i] || std::memcmp(&rows[r][i], &base[i], sizeof(float)) == 0;
        if (!same) { out[r] = predict(rows[r]); continue; }
        exact.push_back(r);
        for (const int index : distinct) values.push_back(rows[r][index]);
    }
    if (exact.empty()) return;
    if (distinct.empty()) {
        for (const std::size_t r : exact) out[r] = predict(rows[r]);
        return;
    }
    std::vector<double> exactOut;
    predictDeltas(base, distinct, values, exactOut);
    for (std::size_t k = 0; k < exact.size(); ++k) out[exact[k]] = exactOut[k];
}

void CompactTreeNet::predictDeltas(const std::vector<float> &base, const std::vector<int> &varying,
                                   const std::vector<float> &values, std::vector<double> &out) const {
    const std::size_t width = varying.size();
    const std::size_t count = width ? values.size() / width : 0;
    if (width == 0 || values.size() % width != 0)
        throw std::invalid_argument("CompactTreeNet::predictDeltas: values do not match varying");
    out.assign(count, 0.0);
    if (count == 0) return;
    // Column of each varying raw feature; -1 marks features fixed at base.
    thread_local std::vector<int> column;
    column.assign(base.size(), -1);
    for (std::size_t j = 0; j < width; ++j) {
        const int index = varying[j];
        if (index < 0 || index >= static_cast<int>(base.size()) || column[index] >= 0)
            throw std::invalid_argument("CompactTreeNet::predictDeltas: invalid or repeated varying index");
        column[index] = static_cast<int>(j);
    }
    if (!packedCurrent()) {
        std::vector<float> row = base;
        for (std::size_t k = 0; k < count; ++k) {
            for (std::size_t j = 0; j < width; ++j) row[varying[j]] = values[k * width + j];
            out[k] = predict(row);
        }
        return;
    }
    // Column-major copy so a split on a varying feature reads one contiguous column.
    thread_local std::vector<float> columns;
    columns.resize(width * count);
    for (std::size_t k = 0; k < count; ++k)
        for (std::size_t j = 0; j < width; ++j) columns[j * count + k] = values[k * width + j];
    thread_local std::vector<double> margins;
    margins.assign(count, baseMargin);
    // Partitions only permute the rows, and any order works for the next
    // tree, so this is filled once per call.
    thread_local std::vector<std::uint32_t> group;
    group.resize(count);
    for (std::size_t k = 0; k < count; ++k) group[k] = static_cast<std::uint32_t>(k);
    struct Pending { int node; std::size_t begin, end; };
    thread_local std::vector<Pending> stack;
    const int *fixedOrColumn = column.data();
    for (std::size_t t = 0; t + 1 < packedRoots.size(); ++t) {
        const PackedNode *tr = packed.data() + packedRoots[t];
        // Every row follows base until the first split on a varying feature.
        int i = 0;
        while (tr[i].feat != kPackedLeaf && fixedOrColumn[tr[i].feat] < 0)
            i = (base[tr[i].feat] < tr[i].thr) ? i + 1 : tr[i].no;
        if (tr[i].feat == kPackedLeaf) {
            const double leaf = tr[i].thr;
            for (std::size_t k = 0; k < count; ++k) margins[k] += leaf;
            continue;
        }
        // From there a split on a fixed feature sends the whole group the way
        // base goes, which is the way every row goes; a split on a varying
        // feature partitions the group. Each row reaches the leaf predict()
        // reaches and adds it in tree order.
        stack.assign(1, {i, 0, count});
        while (!stack.empty()) {
            auto [node, begin, end] = stack.back(); stack.pop_back();
            while (tr[node].feat != kPackedLeaf) {
                const PackedNode &split = tr[node];
                const int c = fixedOrColumn[split.feat];
                if (c < 0) { node = (base[split.feat] < split.thr) ? node + 1 : split.no; continue; }
                const float *col = columns.data() + static_cast<std::size_t>(c) * count;
                const float thr = split.thr;
                const auto mid = std::partition(group.begin() + begin, group.begin() + end,
                    [&](std::uint32_t k) { return col[k] < thr; });
                const std::size_t middle = mid - group.begin();
                if (middle == begin) { node = split.no; continue; }
                if (middle == end) { node = node + 1; continue; }
                stack.push_back({split.no, middle, end});
                node = node + 1; end = middle;
            }
            const double leaf = tr[node].thr;
            for (std::size_t k = begin; k < end; ++k) margins[group[k]] += leaf;
        }
    }
    for (std::size_t k = 0; k < count; ++k) {
        const double m = margins[k];
        const double value = logistic ? 1.0 / (1.0 + std::exp(-m)) : m;
        out[k] = logistic ? std::max(0.0, std::min(1.0, value)) : value;
    }
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
