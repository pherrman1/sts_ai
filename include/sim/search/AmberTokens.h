// Token input of the Amber-Eye-shaped net (tools/az_bench/amber_net.py; stage 0 of the self-play loop assessment,
// 2026-11-16): one state as segments of tokens per type, each token up to 4 categorical ids and up to 64 floats, plus
// the legal-action list the policy is computed over. The segments come in AmberTokenType order, as
// amber_net.TOKEN_TYPES; the batching side pads each segment to the batch's longest and concatenates them, so an
// action names its source / target token as (segment, index within the segment).
//
// This header is the interface between the encoder (state -> AmberTokens) and the batched net-leaf search driver
// (AmberTokens rows -> one GPU batch). Storage is flat: segment s owns slots [kAmberOff[s], kAmberOff[s] + kAmberCap[s])
// of `tok`, of which the first n[s] are live. An encoder that meets more tokens or actions than fit keeps the first
// ones and counts the rest in `cut`.
#ifndef STS_AMBER_TOKENS_H
#define STS_AMBER_TOKENS_H

#include <array>
#include <cstdint>

namespace sts::search {

    enum class AmberTokenType : std::uint8_t { RUN, PLAYER, STATUS, MONSTER, CARD, RELIC, POTION, OPTION, MAP, COUNT };
    constexpr int kAmberTokenTypes = static_cast<int>(AmberTokenType::COUNT);
    constexpr int kAmberCat = 4, kAmberFloat = 64, kAmberActFeat = 8;
    constexpr int kAmberIdVocab = 1024;    // amber_net.ID_VOCAB; id 0 = none / padding
    constexpr int kAmberActionTypes = 16;  // amber_net.ACTION_TYPES

    constexpr std::array<int, kAmberTokenTypes> kAmberCap = {1, 1, 24, 16, 96, 32, 5, 16, 32};
    constexpr std::array<int, kAmberTokenTypes> kAmberOff = {0, 1, 2, 26, 42, 138, 170, 175, 191};
    constexpr int kAmberMaxTokens = 223;   // kAmberOff.back() + kAmberCap.back()
    constexpr int kAmberMaxActions = 96;
    constexpr std::uint8_t kAmberNoSeg = 0xff;

    struct AmberToken {
        std::array<std::int16_t, kAmberCat> ids{};   // categorical ids in [0, kAmberIdVocab)
        std::array<std::uint16_t, kAmberFloat> f{};  // numerical features as IEEE float16 bits (trailing unused = 0)
    };

    struct AmberAction {
        std::uint8_t type = 0;                       // [0, kAmberActionTypes)
        std::uint8_t srcSeg = kAmberNoSeg, tgtSeg = kAmberNoSeg;   // AmberTokenType, or kAmberNoSeg = none
        std::uint8_t srcIdx = 0, tgtIdx = 0;         // index within that segment
        std::array<std::uint16_t, kAmberActFeat> f{};               // float16 bits
    };

    struct AmberTokens {
        std::array<AmberToken, kAmberMaxTokens> tok{};
        std::array<std::uint8_t, kAmberTokenTypes> n{};
        std::array<AmberAction, kAmberMaxActions> act{};
        int nAct = 0;
        int cut = 0;

        void clear() { n.fill(0); nAct = 0; cut = 0; }
        AmberToken &at(AmberTokenType s, int i) { return tok[kAmberOff[static_cast<int>(s)] + i]; }
        const AmberToken &at(AmberTokenType s, int i) const { return tok[kAmberOff[static_cast<int>(s)] + i]; }
    };

    static_assert(kAmberOff[kAmberTokenTypes - 1] + kAmberCap[kAmberTokenTypes - 1] == kAmberMaxTokens);

}

#endif
