//
// CombatDistValueNet: distributional combat value function with:
//   - death probability
//   - win probability
//   - ending HP quantiles (conditional on win)
//   - potion use probability per potion
//   - expected turns remaining
//   - cross-entity attention (transformer) architecture
//
#ifndef STS_LIGHTSPEED_COMBATDISTVALUENET_H
#define STS_LIGHTSPEED_COMBATDISTVALUENET_H

#include "sim/search/CombatObservation.h"
#include "sim/search/CombatValueNet.h"

#include <string>
#include <vector>
#include <cstdint>
#include <array>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    // -- Distributional combat value prediction -----------------------------
    static constexpr int kQuantileBins = 11;  // 0%, 10%, ..., 100%

    struct CombatDistOutcome {
        double deathProbability = 0.0;
        double winProbability = 0.0;
        std::array<double, kQuantileBins> endHpQuantiles{};
        std::array<double, 44> potionUseProbability{};
        double expectedTurnsRemaining = 0.0;

        double riskAdjustedValue(double lambda, double maxHp, double winBonus) const;
        double expectedEndHp() const;
        double cvarEndHp(double alpha) const;
    };

    struct CombatDistValueNet {
        bool isLoaded = false;
        double winBonus = 50.0;
        int entityDim = 128;        // dimension for entity embeddings
        int hiddenDim = 256;        // transformer hidden dim
        int numHeads = 4;           // attention heads
        int numLayers = 2;          // transformer layers

        // Entity embeddings
        std::vector<float> cardEmbed;        // (371, 128) per-card embedding
        std::vector<float> relicEmbed;       // (128, 64)
        std::vector<float> potionEmbed;      // (44, 32)
        std::vector<float> encEmbed;         // (128, 32)
        std::vector<float> monIdEmbed;       // (256, 64)
        std::vector<float> monIntentEmbed;   // (32, 16)
        std::vector<float> zonePosEmbed;     // (4, 128) zone positional encoding

        // Transformer layers (self-attention across entity tokens)
        struct TransformerLayer {
            std::vector<float> qkvFcW;   // (3*entityDim, entityDim)
            std::vector<float> qkvFcB;   // (3*entityDim)
            std::vector<float> projW;    // (entityDim, entityDim)
            std::vector<float> projB;    // (entityDim)
            std::vector<float> ffnW1;    // (hiddenDim, entityDim)
            std::vector<float> ffnB1;    // (hiddenDim)
            std::vector<float> ffnW2;    // (entityDim, hiddenDim)
            std::vector<float> ffnB2;    // (entityDim)
            std::vector<float> ln1W;     // (entityDim) layernorm gain
            std::vector<float> ln1B;     // (entityDim) layernorm bias
            std::vector<float> ln2W;     // (entityDim)
            std::vector<float> ln2B;     // (entityDim)
        };
        std::vector<TransformerLayer> layers;

        // Global state embedding from scalar features
        std::vector<float> scalarW;     // (entityDim, 64)
        std::vector<float> scalarB;     // (entityDim)
        std::vector<float> scalarMean;  // (64)
        std::vector<float> scalarInv;   // (64)

        // Monster stats encoder (per-monster MLP)
        std::vector<float> monContMean; // (7)
        std::vector<float> monContInv;  // (7)
        std::vector<float> monEncW;     // (entityDim, 23)
        std::vector<float> monEncB;     // (entityDim)

        // Pooling from entity tokens -> single state vector
        std::vector<float> poolAttnW;   // (1, entityDim) attention pooling

        // Output heads (from pooled state)
        std::vector<float> deathW;      // (1, entityDim)
        float deathB = 0.f;
        std::vector<float> winW;        // (1, entityDim)
        float winB = 0.f;
        std::vector<float> quantileW;   // (kQuantileBins, entityDim)
        std::vector<float> quantileB;   // (kQuantileBins)
        std::vector<float> potionW;     // (44, entityDim)
        std::vector<float> potionB;     // (44)
        std::vector<float> turnsW;      // (1, entityDim)
        float turnsB = 0.f;

        // Scalar feature selector (indices into canonical 1766)
        std::vector<int> scalarSel;

        bool load(const std::string &path);
        [[nodiscard]] bool loaded() const { return isLoaded; }

        CombatDistOutcome predict(const CombatObservation &obs,
                                  const std::array<float, 1766> &canonFeatures) const;
        CombatDistOutcome predictFromBC(const BattleContext &bc) const;
        [[nodiscard]] double predictScalar(const BattleContext &bc) const; // risk-adjusted utility
        [[nodiscard]] std::string description() const;
    };

    extern CombatDistValueNet g_combatDistVNet;
    extern bool g_useDistVNet;

} // namespace sts::search

#endif // STS_LIGHTSPEED_COMBATDISTVALUENET_H
