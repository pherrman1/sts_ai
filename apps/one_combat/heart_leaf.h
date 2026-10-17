#pragma once
// Research Heart leaf (issue #605, default off): an A20 Heart-objective value
// for the end of OOC MCTS rollouts. value = sigmoid(slope * margin(X2-B) +
// residual(heart features)), where the residual is a margin tree model
// (tools/heart_leaf_fit.py) over the rich run vector plus the state X2-B
// cannot see. Loaded only through STS_OOC_MCTS_LEAF_HEART_MODEL=<manifest>.
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include "compact_tree.h"
#include "run_features.h"

namespace one_combat {
constexpr const char *kHeartLeafFeatureSchema = "heart-leaf-features-v1";
constexpr const char *kHeartLeafAnchorPath = "models/candidates/v_win_x2b_public_trees.txt";
constexpr const char *kHeartLeafAnchorSha256 = "e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90";

// Columns appended after the rich vector, in this order.
const std::vector<std::string> &heartLeafExtraNames();
// Rich names (richIdxMap) followed by heartLeafExtraNames().
const std::unordered_map<std::string, int> &heartLeafIdxMap();
// Floor of the act's boss fight: 16, 33, 50 (the second A20 boss is 51) and the Heart at 56.
int heartLeafBossFloor(int act);
// richFeatureVec(gc, path) followed by the extra columns; x2bMargin is the
// pinned public X2-B margin of the same state.
void appendHeartLeafExtras(std::vector<float> &rich, const sts::GameContext &gc, double x2bMargin);
std::vector<float> heartLeafFeatureVec(const sts::GameContext &gc, const PathHistory &path, double x2bMargin);
std::string fileSha256Hex(const std::string &path);

class HeartLeafModel {
public:
    // Manifest JSON: schema "heart-leaf-v1", featureSchema, residual (path
    // relative to the manifest), residualSha256, anchorSha256, anchorSlope.
    explicit HeartLeafModel(const std::string &manifestPath);
    double anchorMargin(const std::vector<float> &rich) const { return anchor_.margin(rich); }
    double value(const sts::GameContext &gc, const PathHistory &path) const;
    // `raw` is heartLeafFeatureVec(); its x2bMargin column is the anchor margin.
    double valueFromFeatures(const std::vector<float> &raw) const;
    const std::string &manifestPath() const { return path_; }
    const std::string &manifestSha256() const { return sha_; }
private:
    CompactTreeNet anchor_, residual_;
    double slope_ = 1.0;
    std::string path_, sha_;
};
} // namespace one_combat
