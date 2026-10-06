#pragma once
// Native GBM screen leaf (tools/screen_leaf_gbm.py): X2-B margin plus an
// XGBoost residual over the 461 run features and fixed-width public screen
// features. value = sigmoid(logit(x2b) + residual).
#include <string>
#include <unordered_map>
#include <vector>
#include <nlohmann/json.hpp>
#include "compact_tree.h"

namespace one_combat {
const std::vector<std::string> &screenGbmFeatureNames();
// Mirrors screen_features() in tools/screen_leaf_gbm.py.
std::vector<float> screenGbmFeatures(const nlohmann::json &screenContents,
                                     const std::vector<std::string> &optionKeys, float gold);
class ScreenLeafGbm {
public:
    // featureIdx maps run-feature names to raw indices; screen features are
    // appended after `screenOffset`.
    ScreenLeafGbm(const std::string &path, std::unordered_map<std::string, int> featureIdx, int screenOffset,
                  const std::string &anchorPath = "");
    double residual(const std::vector<float> &raw) const { return net_.predict(raw); }
    // Pinned X2-B anchor the residual was trained on (raw = run features).
    bool hasAnchor() const { return anchor_.ok; }
    double anchor(const std::vector<float> &raw) const;
    int screenOffset() const { return offset_; }
private:
    CompactTreeNet net_, anchor_;
    int offset_;
};
constexpr const char *kDefaultScreenGbmModel = "models/candidates/screen_leaf_gbm_v1.trees";
constexpr const char *kScreenGbmAnchor = "models/candidates/v_win_x2b_trees.txt";
int screenLeafGbmParity(const std::string &model, const std::string &input);
}
