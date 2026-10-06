#pragma once
// Native inference for the #379 screen-aware leaf ensemble exported by
// tools/export_screen_leaf_native_379.py. Mirrors encode_state() and the S1
// model in tools/screen_leaf_model_379.py (eval mode, mean of seed sigmoids).
#include <array>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace one_combat {
class ScreenLeafNet {
public:
    explicit ScreenLeafNet(const std::string &path);
    // True when the screen family has a trained head.
    bool covers(const std::string &screen) const;
    // base1017: the full rich row (richRow order); selects the frozen 461.
    double predictFromRich(const std::vector<float> &base1017, const nlohmann::json &screenContents,
                           const std::vector<std::string> &optionKeys) const;
    double predict(const std::vector<float> &base461, const nlohmann::json &screenContents,
                   const std::vector<std::string> &optionKeys) const;
    const std::vector<int> &indices() const { return indices_; }

    struct Tensor { std::vector<int> shape; std::vector<float> v; };
    struct Seed { std::vector<Tensor> t; };
private:
    std::vector<int> indices_;
    std::vector<std::string> mask_;
    std::vector<Seed> seeds_;
};
int screenLeafNetParity(const std::string &model, const std::string &input);
int screenLeafNetLiveParity(const std::string &model, const std::string &input, unsigned limit);
}
