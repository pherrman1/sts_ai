//
// CombatPVNet: shared policy-value network (AlphaZero-style).
// One encoder → one global embedding → policy head + value heads.
//
#ifndef STS_LIGHTSPEED_COMBATPVNET_H
#define STS_LIGHTSPEED_COMBATPVNET_H

#include "sim/search/CombatValueNet.h"

#include <string>
#include <vector>
#include <cstdint>
#include <array>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    static constexpr int kPVQuantileBins = 11;

    struct CombatPVNet {
        bool isLoaded = false;
        double winBonus = 50.0;
        int entityDim = 128;
        int hiddenDim = 256;
        int numHeads = 4;
        int numLayers = 2;
        int nQuantile = 11;

        // Entity embeddings (same as CombatDistValueNet)
        std::vector<float> cardEmbed;        // (371, 128)
        std::vector<float> relicEmbed;       // (128, 64)
        std::vector<float> potionEmbed;      // (44, 32)
        std::vector<float> encEmbed;         // (128, 32)
        std::vector<float> monIdEmbed;       // (256, 64)
        std::vector<float> monIntentEmbed;   // (32, 16)
        std::vector<float> zonePosEmbed;     // (4, 128)

        // New: type embeddings (6 types: scalar, card, relic, potion, encounter, monster)
        std::vector<float> typeEmbed;        // (6, 128)
        // New: learned GLOBAL token
        std::vector<float> globalToken;      // (1, 128)

        // Projection layers for non-128-dim embeddings
        std::vector<float> relicProjW;       // (128, 64) — linear from 64→128
        std::vector<float> relicProjB;       // (128)
        std::vector<float> potionProjW;      // (128, 32)
        std::vector<float> potionProjB;      // (128)
        std::vector<float> encProjW;         // (128, 32)
        std::vector<float> encProjB;         // (128)
        bool hasRelicProj = false;
        bool hasPotionProj = false;
        bool hasEncProj = false;

        // Transformer layers
        struct TransformerLayer {
            std::vector<float> qkvFcW;       // (3D, D)
            std::vector<float> qkvFcB;       // (3D)
            std::vector<float> projW;        // (D, D)
            std::vector<float> projB;        // (D)
            std::vector<float> ffnW1;        // (H, D)
            std::vector<float> ffnB1;        // (H)
            std::vector<float> ffnW2;        // (D, H)
            std::vector<float> ffnB2;        // (D)
            std::vector<float> ln1W;         // (D)
            std::vector<float> ln1B;         // (D)
            std::vector<float> ln2W;         // (D)
            std::vector<float> ln2B;         // (D)
        };
        std::vector<TransformerLayer> layers;

        // Scalar encoder
        std::vector<float> scalarW;          // (D, 64)
        std::vector<float> scalarB;          // (D)
        std::vector<float> scalarMean;       // (64)
        std::vector<float> scalarInv;        // (64)

        // Monster encoder (87 → D)
        std::vector<float> monContMean;      // (7)
        std::vector<float> monContInv;       // (7)
        std::vector<float> monEncW;          // (D, 87)
        std::vector<float> monEncB;          // (D)

        // ── Policy head ──
        // Action encoder: 14 → 64 → D
        std::vector<float> policyActEncW0;   // (64, 14)
        std::vector<float> policyActEncB0;   // (64)
        std::vector<float> policyActEncW2;   // (D, 64)
        std::vector<float> policyActEncB2;   // (D)
        // Scorer: 3*D → D → 1
        std::vector<float> policyScorerW0;   // (D, 3*D)
        std::vector<float> policyScorerB0;   // (D)
        std::vector<float> policyScorerW2;   // (1, D)
        std::vector<float> policyScorerB2;   // (1)

        // ── Value heads ──
        std::vector<float> winW;             // (1, D)
        float winB = 0.f;
        std::vector<float> deathW;           // (1, D)
        float deathB = 0.f;
        std::vector<float> quantileW;        // (NQ, D)
        std::vector<float> quantileB;        // (NQ)
        std::vector<float> potionW;          // (44, D)
        std::vector<float> potionB;          // (44)
        std::vector<float> turnsW;           // (1, D)
        float turnsB = 0.f;

        // Scalar selector
        std::vector<int> scalarSel;

        bool load(const std::string &path);
        [[nodiscard]] bool loaded() const { return isLoaded; }

        // Encoder: state features → global embedding (D-dim vector)
        void encode(const std::array<float, 1766> &feat,
                    float *globalOut) const;

        // Policy: score one action given its action features and global embedding
        float policyScore(const float *globalEmb, const float *actionFeat) const;

        // Policy: score a batch of actions (B actions, same global embedding)
        void policyScores(const float *globalEmb,
                         const float *actionFeats, int nActions,
                         float *logitsOut) const;

        // Value: predict from global embedding
        void predictValue(const float *globalEmb,
                          float &winProb, float &deathProb,
                          std::array<float, 11> *quantiles = nullptr,
                          std::array<float, 44> *potionProbs = nullptr,
                          float *turnsRemaining = nullptr) const;

        // Full inference: encode + value prediction
        void predictFromBC(const BattleContext &bc,
                          float &winProb, float &deathProb,
                          std::array<float, 11> *quantiles = nullptr) const;

        // Leaf utility for MCTS
        [[nodiscard]] double leafValue(const BattleContext &bc, double riskLambda = 0.5) const;

        [[nodiscard]] std::string description() const;

        // ── Helpers ──
        void buildTokens(const std::array<float, 1766> &feat,
                        float *tokensOut, int &nTokens) const;
        void applyTransformer(float *tokens, int nTokens) const;
    };

    extern CombatPVNet g_combatPVNet;
    extern bool g_usePVNet;

} // namespace sts::search

#endif
