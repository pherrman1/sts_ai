//
// CombatCpsiNet: native C++ loader/inference for the no-peek pre-combat
// outcome model C_psi (train_combat_cpsi.py, text export "combat_cpsi_v1").
// No-peek entry state: 11 persistent scalars, whole-deck bag [0..370],
// relics [0..127], potions [0..43], encounter id -> P(death), P(win),
// E[hp/maxHp | win], 11 HP quantiles, P(use potion i), expected turns.
// 5 fixed tokens (scalar, deck bag, relics, potions, encounter), 2-layer
// transformer (dim 128, hidden 256, 4 heads, post-LN), attention pooling.
//
#ifndef STS_LIGHTSPEED_COMBATCPSINET_H
#define STS_LIGHTSPEED_COMBATCPSINET_H

#include <string>
#include <vector>
#include <cstdint>

namespace sts {
    class GameContext;
}

namespace sts::search {

    static constexpr int kCpsiScalars    = 11;
    static constexpr int kCpsiQuantiles  = 11;
    static constexpr int kCpsiCards      = 371;   // CardId 0..370
    static constexpr int kCpsiRelics     = 128;   // RelicId 0..127
    static constexpr int kCpsiPotions    = 44;    // Potion enum ids 0..43
    static constexpr int kCpsiEncounters = 128;   // Embedding table size

    struct CpsiOut {
        float death = 0.f;
        float win = 0.f;
        float hp = 0.f;                    // E[hp/maxHp | win], sigmoided
        float quantiles[kCpsiQuantiles] = {};    // raw logits (trainer evaluate() semantics)
        float potionProb[kCpsiPotions] = {};     // sigmoided
        float turns = 0.f;                 // expm1(log1p-scale raw)
    };

    struct CombatCpsiNet {
        bool isLoaded = false;
        std::string path;
        double winBonus = 50.0;
        int entityDim = 128;
        int hiddenDim = 256;
        int numHeads = 4;
        int numLayers = 2;
        int nQuantile = kCpsiQuantiles;

        // Scalar encoder (11 -> dim, ReLU)
        std::vector<float> scalarMean;      // (11)
        std::vector<float> scalarInv;       // (11)
        std::vector<float> scalarW;         // (dim, 11)
        std::vector<float> scalarB;         // (dim)

        // Entity embeddings
        std::vector<float> cardEmbed;       // (371, dim)
        std::vector<float> relicEmbed;      // (128, 64)
        std::vector<float> potionEmbed;     // (44, 32)
        std::vector<float> encEmbed;        // (128, 32)

        // Projection layers (64/32 -> dim). Optional in the text format:
        // the trainer's combat_cpsi_v1 writer does NOT export them, so when
        // absent the raw embedding is zero-padded (PVNet identity convention).
        std::vector<float> relicProjW;      // (dim, 64)
        std::vector<float> relicProjB;      // (dim)
        std::vector<float> potionProjW;     // (dim, 32)
        std::vector<float> potionProjB;     // (dim)
        std::vector<float> encProjW;        // (dim, 32)
        std::vector<float> encProjB;        // (dim)
        bool hasRelicProj = false;
        bool hasPotionProj = false;
        bool hasEncProj = false;

        // Transformer layers (post-LN, GELU FFN)
        struct TransformerLayer {
            std::vector<float> qkvFcW;      // (3*dim, dim)
            std::vector<float> qkvFcB;      // (3*dim)
            std::vector<float> projW;       // (dim, dim)
            std::vector<float> projB;       // (dim)
            std::vector<float> ffnW1;       // (hidden, dim)
            std::vector<float> ffnB1;       // (hidden)
            std::vector<float> ffnW2;       // (dim, hidden)
            std::vector<float> ffnB2;       // (dim)
            std::vector<float> ln1W;        // (dim)
            std::vector<float> ln1B;        // (dim)
            std::vector<float> ln2W;        // (dim)
            std::vector<float> ln2B;        // (dim)
        };
        std::vector<TransformerLayer> layers;

        // Attention pooling
        std::vector<float> poolW;           // (dim)
        float poolB = 0.f;

        // Output heads (from pooled embedding)
        std::vector<float> deathW;          // (dim)
        float deathB = 0.f;
        std::vector<float> winW;            // (dim)
        float winB = 0.f;
        std::vector<float> hpW;             // (dim)
        float hpB = 0.f;
        std::vector<float> quantileW;       // (11, dim)
        std::vector<float> quantileB;       // (11)
        std::vector<float> potionW;         // (44, dim)
        std::vector<float> potionB;         // (44)
        std::vector<float> turnsW;          // (dim)
        float turnsB = 0.f;

        bool load(const std::string &path);
        [[nodiscard]] bool loaded() const { return isLoaded; }

        // No-peek forward. Postprocessing matches train_combat_cpsi.py
        // evaluate(): death/win/hp/potionProb sigmoided, quantiles raw,
        // turns expm1(raw log1p-scale logit).
        void predict(const float scalar[11], const float deck[371],
                     const float relics[128], const float potions[44],
                     int encounter, CpsiOut &out) const;

        [[nodiscard]] std::string description() const;
    };

    // Pre-combat entry builder (no hand/draw/monster/intent features):
    // deck = per-card-id counts, relics = presence [0..127], potions =
    // per-Potion-enum-id counts, scalars = ascension/curHp/maxHp + the 8
    // persistent relic counters (from RelicInstance.data; 0 when absent).
    // PANACHE has no relic, so its counter is always 0 pre-combat.
    void buildCpsiEntry(const GameContext &gc, float scalar[11],
                        float deck[371], float relics[128], float potions[44]);

} // namespace sts::search

#endif // STS_LIGHTSPEED_COMBATCPSINET_H
