// Packing of AmberTokens rows into one flat, bucketed batch (amber_net.AmberNet.forward_flat's layout). Shared by
// the stage 0 combat driver (az_driver.h) and the stage 1 whole-run driver (az_run_driver.h). Layout and buffer
// contract: Driver::nextBatchFlat in az_driver.h.
#ifndef STS_AZ_PACK_H
#define STS_AZ_PACK_H

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <thread>
#include <vector>

#include "sim/search/AmberTokens.h"

namespace sts::azbench {

    struct FlatBuffers {
        std::int8_t *tokType;      // [R][T]
        std::int16_t *ids;         // [R][T][4]
        std::uint16_t *f;          // [R][T][64] float16 bits
        std::uint8_t *mask;        // [R][T]
        std::int16_t *aType, *aSrc, *aTgt;   // [R][A]
        std::uint16_t *aF;         // [R][A][8]
        std::uint8_t *aMask;       // [R][A]
    };
    struct FlatShape { int rows = 0, rowsPadded = 0, tokens = 0, actions = 0; };

    inline int bucketFor(const std::vector<int> &buckets, int n) {
        for (int b : buckets)
            if (b >= n) return b;
        return buckets.empty() ? n : buckets.back();
    }

    inline int liveTokens(const search::AmberTokens &tk) {
        int n = 0;
        for (int s = 0; s < search::kAmberTokenTypes; ++s) n += tk.n[s];
        return n;
    }

    // Packs B rows (tokensOf(r) for r < B) into buf; picks the row / token / action buckets; fills shape.
    template <class TokensOf>
    void packFlat(int B, TokensOf tokensOf, const std::vector<int> &rowBuckets, const std::vector<int> &tokBuckets,
                  const std::vector<int> &actBuckets, const FlatBuffers &buf, FlatShape &shape, int packThreads) {
        int maxT = 1, maxA = 1;
        for (int r = 0; r < B; ++r) {
            const search::AmberTokens &tk = tokensOf(r);
            maxT = std::max(maxT, liveTokens(tk));
            maxA = std::max(maxA, tk.nAct);
        }
        const int R = std::max(B, bucketFor(rowBuckets, B));
        const int T = std::max(maxT, bucketFor(tokBuckets, maxT));
        const int A = std::max(maxA, bucketFor(actBuckets, maxA));
        shape = {B, R, T, A};
        // Dead token slots keep whatever an earlier batch left in tokType / ids / f (the caller's buffers start
        // zeroed, so it is always a finite value and a valid id / type): only the mask says what is live, a dead
        // slot is a masked key, and no output of a live row reads it. Zeroing them cost ~15 MB of stores per batch.
        // Rows are independent: packThreads threads each clear and fill a contiguous range of rows.
        auto packRows = [&](int r0, int r1) {
            const std::size_t n = static_cast<std::size_t>(r1 - r0);
            std::memset(buf.mask + static_cast<std::size_t>(r0) * T, 0, n * T);
            std::memset(buf.aType + static_cast<std::size_t>(r0) * A, 0, sizeof(std::int16_t) * n * A);
            std::fill(buf.aSrc + static_cast<std::size_t>(r0) * A, buf.aSrc + static_cast<std::size_t>(r1) * A,
                      std::int16_t(-1));
            std::fill(buf.aTgt + static_cast<std::size_t>(r0) * A, buf.aTgt + static_cast<std::size_t>(r1) * A,
                      std::int16_t(-1));
            std::memset(buf.aF + static_cast<std::size_t>(r0) * A * search::kAmberActFeat, 0,
                        sizeof(std::uint16_t) * n * A * search::kAmberActFeat);
            std::memset(buf.aMask + static_cast<std::size_t>(r0) * A, 0, n * A);
            for (int r = r0; r < std::min(r1, B); ++r) {
                const search::AmberTokens &tk = tokensOf(r);
                std::array<int, search::kAmberTokenTypes> off{};
                int pos = 0;
                for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                    off[s] = pos;
                    for (int i = 0; i < tk.n[s]; ++i, ++pos) {
                        const auto &k = tk.tok[search::kAmberOff[s] + i];
                        const std::size_t j = static_cast<std::size_t>(r) * T + pos;
                        buf.tokType[j] = static_cast<std::int8_t>(s);
                        std::memcpy(buf.ids + j * search::kAmberCat, k.ids.data(), sizeof(k.ids));
                        std::memcpy(buf.f + j * search::kAmberFloat, k.f.data(), sizeof(k.f));
                        buf.mask[j] = 1;
                    }
                }
                for (int a = 0; a < tk.nAct; ++a) {
                    const auto &x = tk.act[a];
                    const std::size_t j = static_cast<std::size_t>(r) * A + a;
                    buf.aType[j] = x.type;
                    buf.aSrc[j] = x.srcSeg == search::kAmberNoSeg ? -1
                                                                  : static_cast<std::int16_t>(off[x.srcSeg] + x.srcIdx);
                    buf.aTgt[j] = x.tgtSeg == search::kAmberNoSeg ? -1
                                                                  : static_cast<std::int16_t>(off[x.tgtSeg] + x.tgtIdx);
                    std::memcpy(buf.aF + j * search::kAmberActFeat, x.f.data(), sizeof(x.f));
                    buf.aMask[j] = 1;
                }
            }
        };
        const int K = std::max(1, std::min(packThreads, R / 64));
        if (K == 1) {
            packRows(0, R);
        } else {
            std::vector<std::thread> th;
            th.reserve(K - 1);
            for (int k = 1; k < K; ++k) th.emplace_back(packRows, R * k / K, R * (k + 1) / K);
            packRows(0, R / K);
            for (auto &t : th) t.join();
        }
        for (int r = B; r < R; ++r) {   // padding rows: one live (stale) token and one live action; outputs discarded
            buf.mask[static_cast<std::size_t>(r) * T] = 1;
            buf.aMask[static_cast<std::size_t>(r) * A] = 1;
        }
    }

}

#endif
