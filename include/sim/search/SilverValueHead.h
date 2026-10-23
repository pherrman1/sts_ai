//
// A value head on the frozen trunk of a combat_policy_mlp prior (silver_value_head_v1 text format, written by the
// leaf-value research tools): Silver points = scale * (w2 . relu(W1 ((relu(trunk base) - mu) * invSd) + b1) + b2)
// + offset. Silver's STS_SILVER_LEAF_HEAD and exact_combat_solver --leaf-heads read it. A file that ends in
// "target shortfall" holds a shortfall head: it predicts how far below the state's win-now value
// (SilverSearcher::winNowValue) the fight ends, and the state is worth win-now - max(0, prediction).
//
#ifndef STS_LIGHTSPEED_SILVERVALUEHEAD_H
#define STS_LIGHTSPEED_SILVERVALUEHEAD_H

#include <string>
#include <vector>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    struct CombatValueNet;

    struct SilverValueHead {
        static constexpr int kMaxWidth = 1024;   // largest `in` and `hidden` load() accepts
        int in = 0, hidden = 0;
        // w1t is W1 transposed (in x hidden), so the forward vectorizes over the hidden units while every unit
        // still sums its inputs in order (the same values as the row-major sum).
        std::vector<float> mu, invSd, w1t, b1, w2;
        float b2 = 0;
        double scale = 1, offset = 0;
        bool shortfall = false;   // value() is the shortfall below win-now, not the state's value

        static SilverValueHead load(const std::string &path);
        // The head on a trunk embedding (relu(trunk base), `in` values).
        [[nodiscard]] double value(const std::vector<float> &trunk) const;
        // The head's value of `state` on `trunk`; feat and base are scratch and keep the state block and
        // relu(trunk base).
        double value(const BattleContext &state, const CombatValueNet &trunk, std::vector<float> &feat,
                     std::vector<float> &base) const;
    };

}

#endif //STS_LIGHTSPEED_SILVERVALUEHEAD_H
