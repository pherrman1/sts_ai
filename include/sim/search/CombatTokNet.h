// Native inference for the combat plan's token combat net (tools/combat_net/model.py; stage 3, 2026-11-08), and
// its input encoder for one Silver root: a port of tools/combat_net/wire_encoder.encode plus one row of
// tools/combat_net/tensorize.py (caps, int16 clipping, float16 storage of the float groups).
// Weights come from tools/combat_net/export_native.py (magic CTOKNET1).
#ifndef STS_COMBAT_TOK_NET_H
#define STS_COMBAT_TOK_NET_H

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "sim/search/SilverSearcher.h"

namespace sts::search {

    // tensorize.py caps.
    constexpr int kCtnGlobLen = 97;   // wire_encoder global (59) + player (38)
    constexpr int kCtnCardMax = 128, kCtnMonMax = 5, kCtnMonNum = 128, kCtnStatusMax = 32;
    constexpr int kCtnQueueMax = 8, kCtnQueueLen = 24, kCtnSelMax = 10, kCtnActionLen = 47;
    constexpr int kCtnPotionSlots = 5, kCtnValueClasses = 21, kCtnAux = 2;

    // One root as tensorize.py stores it (one row of each array).
    struct CombatTokInputs {
        std::array<float, kCtnGlobLen> glob{};                        // float16(slog(x)), as glob.npy
        std::array<std::uint8_t, 128> relics{}, sbits{};
        std::vector<std::array<std::int16_t, 2>> smap;                // the first kCtnStatusMax statusMap pairs
        std::array<std::array<std::int16_t, 4>, kCtnMonMax> mcat{};   // idx, id, last move, move before
        std::array<std::array<float, kCtnMonNum>, kCtnMonMax> mnum{}; // float16(slog(x))
        int nmon = 0;
        std::array<std::int16_t, kCtnPotionSlots> potions{};
        std::vector<std::array<std::int16_t, kCtnQueueLen>> queues;
        std::vector<std::array<std::int16_t, 9>> cards;
        std::vector<std::array<std::int16_t, kCtnActionLen>> actions;  // one per root edge
    };

    struct CombatTokOutputs {
        std::vector<float> logits;                          // policy logit per action
        std::array<float, kCtnValueClasses> value{};        // class 0 = death, 1..20 = end HP / max HP bins
        std::array<float, kCtnAux> aux{};                   // HP lost over the next 1 and 2 turns, / 10
    };

    class CombatTokNet {
    public:
        bool load(const std::string &path, std::string *error = nullptr);
        bool loaded() const { return d_ > 0; }
        // Same math as CombatNet.forward in eval mode (float32; sums in another order, so equal up to rounding).
        void forward(const CombatTokInputs &in, CombatTokOutputs &out) const;
        int dim() const { return d_; }
        int layerCount() const { return static_cast<int>(layers_.size()); }
        bool valueTrained() const { return valueOn_; }

        struct Linear {
            int in = 0, out = 0;
            std::vector<float> wt;   // [in][out] (PyTorch's weight transposed)
            std::vector<float> b;
        };
        struct Layer {
            Linear qkv, proj, ff1, ff2;
            std::vector<float> ln1w, ln1b, ln2w, ln2b;
        };

    private:
        int d_ = 0, heads_ = 0;
        bool valueOn_ = false, auxOn_ = false;
        std::vector<float> card_, zone_, mon_, monIdx_, move_, stat_, pot_, tokType_;
        std::vector<float> aType_, aCard_, aPot_, aTarget_, aSel_;
        Linear cardNum_, monNum_, statNum_, queue_, glob0_, glob2_, aNum_, pol0_, pol2_, val0_, val2_, aux0_, aux2_;
        std::vector<Layer> layers_;
        std::vector<float> normW_, normB_;
    };

    // The state groups of one root from its wire (nlohmann::json(wireFromSearchState(...)), as the silverazgen rows
    // carry it). Clears `out.actions`. Throws std::runtime_error on a wire that wire_encoder.encode would reject
    // for a missing field or a global/player block of another length.
    void combatTokEncodeWire(const nlohmann::json &wire, CombatTokInputs &out);
    // tensorize.action_row of a semantic fingerprint (wire_encoder.parse_semantic), int16-clipped; all zeros for
    // an empty fingerprint.
    std::array<std::int16_t, kCtnActionLen> combatTokActionRow(const std::string &semantic);
    // Both, for a searcher's root: the wire of `state` under `context` and one action row per edge, in edge order.
    void combatTokEncodeRoot(const BattleContext &state, const SilverSearchContext &context,
                             const std::vector<SilverSearcher::Edge> &edges, CombatTokInputs &out);

    // float -> nearest float16 (ties to even) -> float, as numpy's float32 -> float16 cast.
    float combatTokRoundHalf(float x);

}

#endif
