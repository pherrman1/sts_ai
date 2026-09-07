#ifndef STS_ONE_COMBAT_COMPACT_TREE_H
#define STS_ONE_COMBAT_COMPACT_TREE_H

#include <string>
#include <unordered_map>
#include <vector>

namespace one_combat {

struct CompactTreeNet {
    struct Node { int feat; float thr; int yes, no; };
    std::vector<std::vector<Node>> trees;
    std::vector<int> sel;
    double baseMargin = 0.0; bool logistic = true, ok = false;
    std::string path;
    std::vector<std::string> featureNames;

    bool load(const std::string &path, const std::unordered_map<std::string, int> &featureIdx,
              const char *kind = "CompactTreeNet");
    double predict(const std::vector<float> &raw) const;
};

} // namespace one_combat

#endif // STS_ONE_COMBAT_COMPACT_TREE_H
