#include "compact_tree.h"

#include <algorithm>
#include <cmath>
#include <functional>
#include <fstream>
#include <iostream>
#include <limits>
#include <unordered_set>

namespace one_combat {

bool CompactTreeNet::load(const std::string &path, const std::unordered_map<std::string, int> &featureIdx,
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
    nodes.clear(); roots.clear(); roots.reserve(ntrees + 1);
    for (int t = 0; t < ntrees; ++t) {
        std::string kw; int ti, nn; f >> kw >> ti >> nn;
        if (!f.good() || kw != "tree" || ti != t || nn < 1) { std::cerr << kind << ": invalid tree " << t << " header in " << path << "\n"; return false; }
        std::vector<Node> tr(nn);
        for (int i = 0; i < nn; ++i) {
            std::string type; f >> type;
            Node nd = { -1, 0.0f, 0, 0 };
            if (type == "L") { double v; f >> v; nd = { -1, (float)v, 0, 0 }; }
            else if (type == "S") { int fi = 0, y = 0, no = 0; float th = 0.0f; f >> fi >> th >> y >> no; nd = { fi, th, y, no }; }
            else { std::cerr << kind << ": invalid node tag in tree " << t << "\n"; return false; }
            if (!f.good()) { std::cerr << kind << ": truncated node in tree " << t << " of " << path << "\n"; return false; }
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
    f >> tok;
    if (!f.eof()) { std::cerr << kind << ": trailing data after " << ntrees << " trees in " << path << "\n"; return false; }
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

} // namespace one_combat
