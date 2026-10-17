#ifndef STS_ONE_COMBAT_COMPACT_TREE_H
#define STS_ONE_COMBAT_COMPACT_TREE_H

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace one_combat {

struct CompactTreeNet {
    struct MarginalFeature {
        int rawIndex = -1;
        int low = 0;
        int high = 0;
        int step = 1;
    };
    struct Node { int feat; float thr; int yes, no; };
    // Split features are raw indices; child indices remain relative to each root.
    std::vector<Node> nodes;
    std::vector<std::size_t> roots; // Includes an end sentinel for tree sizes.
    std::vector<int> sel;
    double baseMargin = 0.0; bool logistic = true, ok = false;
    std::string path;
    std::vector<std::string> featureNames;
    // Evaluation copy of nodes/roots: each tree in preorder, the yes child
    // directly after its parent, so a walk touches fewer cache lines. Leaves
    // carry kPackedLeaf as feature. load() builds it. Trees filled in
    // directly are walked from nodes unless pack() is called; code that edits
    // loaded nodes in place must call pack() again.
    struct PackedNode { std::uint16_t feat; std::uint16_t no; float thr; };
    static constexpr std::uint16_t kPackedLeaf = 0xffff;
    std::vector<PackedNode> packed;
    std::vector<std::uint32_t> packedRoots;

    bool load(const std::string &path, const std::unordered_map<std::string, int> &featureIdx,
              const char *kind = "CompactTreeNet");
    // Rebuild packed from nodes/roots. False (and no packed copy) when a tree
    // is malformed or a raw index or tree is too large for PackedNode.
    bool pack();
    bool packedCurrent() const;
    double predict(const std::vector<float> &raw) const;
    // Base margin plus leaf sum, before the logistic link.
    double margin(const std::vector<float> &raw) const;
    // margin() accumulated in float32 from the base, tree by tree, as XGBoost's
    // own prediction does. Loaded (packed) models only.
    float marginFloat32(const std::vector<float> &raw) const;
    // Bit-identical to calling predict() on each row in turn. Rows that equal
    // base outside the varying raw features walk each tree together and only
    // separate at splits on varying features; any other row falls back to
    // predict().
    void predictVariants(const std::vector<float> &base, const std::vector<int> &varying,
                         const std::vector<std::vector<float>> &rows, std::vector<double> &out) const;
    // Same values as predict() on rows that equal base except at the varying
    // raw features. varying must hold distinct in-range indices; values holds
    // one row of varying.size() floats per candidate (row-major).
    void predictDeltas(const std::vector<float> &base, const std::vector<int> &varying,
                       const std::vector<float> &values, std::vector<double> &out) const;
    // Evaluate the tree ensemble after integrating selected raw features over
    // a discrete public-belief prior. This is intentionally separate from
    // predict(): callers must opt in and name the ranges they are marginalizing.
    // Logistic models return the exact discrete mixture E[sigmoid(margin)].
    // Non-logistic models return the expected tree margin.
    double predictMarginalized(const std::vector<float> &raw,
                               const std::vector<MarginalFeature> &features) const;
};

} // namespace one_combat

#endif // STS_ONE_COMBAT_COMPACT_TREE_H
