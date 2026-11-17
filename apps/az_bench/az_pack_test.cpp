// packFlat with packed tokens (FlatBuffers::packIdx, az_pack.h) writes the same live tokens as the [R][T] layout:
// packed token p equals slot packIdx[p] of the padded pack, rows are in order (seqOff), mask and actions are
// identical. Random AmberTokens rows, several batch sizes and bucket sets, 1 and 4 pack threads.
#include <cstdio>
#include <random>
#include <vector>

#include "az_pack.h"

using namespace sts;

namespace {

    struct Bufs {
        std::vector<std::int8_t> tokType;
        std::vector<std::int16_t> ids;
        std::vector<std::uint16_t> f;
        std::vector<std::uint8_t> mask, aMask;
        std::vector<std::int16_t> aType, aSrc, aTgt;
        std::vector<std::uint16_t> aF;
        std::vector<std::int32_t> packIdx, seqOff;
        explicit Bufs(int R, int T, int A)
            : tokType(static_cast<std::size_t>(R) * T), ids(tokType.size() * search::kAmberCat),
              f(tokType.size() * search::kAmberFloat), mask(tokType.size()), aMask(static_cast<std::size_t>(R) * A),
              aType(aMask.size()), aSrc(aMask.size()), aTgt(aMask.size()), aF(aMask.size() * search::kAmberActFeat),
              packIdx(tokType.size()), seqOff(static_cast<std::size_t>(R) + 1) {}
        azbench::FlatBuffers view(bool packed) {
            azbench::FlatBuffers b{tokType.data(), ids.data(), f.data(), mask.data(), aType.data(), aSrc.data(),
                                   aTgt.data(), aF.data(), aMask.data()};
            if (packed) { b.packIdx = packIdx.data(); b.seqOff = seqOff.data(); }
            return b;
        }
    };

}

int main() {
    std::mt19937_64 rng(1);
    int fails = 0, checked = 0;
    for (int trial = 0; trial < 40; ++trial) {
        const int B = 1 + static_cast<int>(rng() % 70);
        std::vector<search::AmberTokens> rows(B);
        for (auto &tk : rows) {
            tk.clear();
            for (int s = 0; s < search::kAmberTokenTypes; ++s) {
                const int cap = search::kAmberCap[s];
                tk.n[s] = static_cast<std::uint8_t>(s == 0 ? 1 : rng() % (std::min(cap, 12) + 1));
                for (int i = 0; i < tk.n[s]; ++i) {
                    auto &t = tk.tok[search::kAmberOff[s] + i];
                    for (auto &x : t.ids) x = static_cast<std::int16_t>(rng() % search::kAmberIdVocab);
                    for (auto &x : t.f) x = static_cast<std::uint16_t>(rng());
                }
            }
            tk.nAct = 1 + static_cast<int>(rng() % 9);
            for (int a = 0; a < tk.nAct; ++a) {
                auto &x = tk.act[a];
                x.type = static_cast<std::uint8_t>(rng() % search::kAmberActionTypes);
                x.srcSeg = static_cast<std::uint8_t>(rng() % search::kAmberTokenTypes);
                x.srcIdx = 0;
                if (tk.n[x.srcSeg] == 0) x.srcSeg = search::kAmberNoSeg;
                x.tgtSeg = search::kAmberNoSeg;
                for (auto &v : x.f) v = static_cast<std::uint16_t>(rng());
            }
        }
        const std::vector<int> rowB = trial % 2 ? std::vector<int>{64, 128} : std::vector<int>{};
        const std::vector<int> tokB = trial % 3 ? std::vector<int>{32, 48, 64, 96, 212} : std::vector<int>{};
        const std::vector<int> actB = {16, 32, 96};
        const int threads = trial % 4 == 0 ? 4 : 1;
        const int R = 256, T = search::kAmberMaxTokens, A = search::kAmberMaxActions;
        Bufs pad(R, T, A), pk(R, T, A);
        // Stale garbage in both, as after earlier batches.
        for (auto &x : pad.f) x = static_cast<std::uint16_t>(rng());
        for (auto &x : pk.f) x = static_cast<std::uint16_t>(rng());
        auto tokensOf = [&](int r) -> const search::AmberTokens & { return rows[r]; };
        azbench::FlatShape s1, s2;
        azbench::packFlat(B, tokensOf, rowB, tokB, actB, pad.view(false), s1, threads);
        azbench::packFlat(B, tokensOf, rowB, tokB, actB, pk.view(true), s2, threads);
        bool ok = s1.rows == s2.rows && s1.rowsPadded == s2.rowsPadded && s1.tokens == s2.tokens &&
                  s1.actions == s2.actions && s1.packed == 0 && s2.packed > 0;
        const int Rp = s2.rowsPadded, Tp = s2.tokens, Ap = s2.actions;
        const std::size_t RT = static_cast<std::size_t>(Rp) * Tp, RA = static_cast<std::size_t>(Rp) * Ap;
        for (std::size_t j = 0; ok && j < RT; ++j) ok = pad.mask[j] == pk.mask[j];
        for (std::size_t j = 0; ok && j < RA; ++j)
            ok = pad.aMask[j] == pk.aMask[j] && pad.aType[j] == pk.aType[j] && pad.aSrc[j] == pk.aSrc[j] &&
                 pad.aTgt[j] == pk.aTgt[j];
        for (std::size_t j = 0; ok && j < RA * search::kAmberActFeat; ++j) ok = pad.aF[j] == pk.aF[j];
        // Packed tokens: row order, one per live slot, same contents as the padded pack's slot (live rows).
        std::size_t live = 0;
        for (std::size_t j = 0; j < RT; ++j) live += pk.mask[j];
        ok = ok && static_cast<std::size_t>(s2.packed) == live && pk.seqOff[0] == 0 && pk.seqOff[Rp] == s2.packed;
        for (int r = 0; ok && r < Rp; ++r) {
            int n = 0;
            for (int t = 0; t < Tp; ++t) n += pk.mask[static_cast<std::size_t>(r) * Tp + t];
            ok = pk.seqOff[r + 1] - pk.seqOff[r] == n;
            for (int p = pk.seqOff[r]; ok && p < pk.seqOff[r + 1]; ++p) {
                const std::size_t j = static_cast<std::size_t>(pk.packIdx[p]);
                ok = j / Tp == static_cast<std::size_t>(r) && pk.mask[j] && (p == pk.seqOff[r] || pk.packIdx[p] > pk.packIdx[p - 1]);
                if (ok && r < B) {
                    ok = pk.tokType[p] == pad.tokType[j];
                    for (int c = 0; ok && c < search::kAmberCat; ++c) ok = pk.ids[p * search::kAmberCat + c] == pad.ids[j * search::kAmberCat + c];
                    for (int c = 0; ok && c < search::kAmberFloat; ++c) ok = pk.f[p * search::kAmberFloat + c] == pad.f[j * search::kAmberFloat + c];
                }
            }
        }
        ++checked;
        if (!ok) { std::fprintf(stderr, "FAIL trial %d (B %d)\n", trial, B); ++fails; }
    }
    std::printf("{\"trials\": %d, \"fails\": %d}\n", checked, fails);
    return fails ? 1 : 0;
}
