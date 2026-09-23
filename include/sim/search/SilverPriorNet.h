#ifndef STS_SILVER_PRIOR_NET_H
#define STS_SILVER_PRIOR_NET_H

#include "sim/search/SilverBridge.h"

#include <memory>

namespace sts::search {

class SilverPriorNetV1 {
public:
    explicit SilverPriorNetV1(const std::string &path);
    ~SilverPriorNetV1();
    SilverPriorNetV1(SilverPriorNetV1 &&) noexcept;
    SilverPriorNetV1 &operator=(SilverPriorNetV1 &&) noexcept;
    SilverPriorNetV1(const SilverPriorNetV1 &) = delete;
    SilverPriorNetV1 &operator=(const SilverPriorNetV1 &) = delete;

    std::vector<double> logits(const silver_bridge::BattleStateWire &state,
                               const std::vector<silver_bridge::SemanticAction> &actions) const;
    std::vector<double> prior(const silver_bridge::BattleStateWire &state,
                              const std::vector<silver_bridge::SemanticAction> &actions) const;
    const std::string &artifactSha256() const;
    static constexpr double kPuctC = 2.5;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace sts::search

#endif
