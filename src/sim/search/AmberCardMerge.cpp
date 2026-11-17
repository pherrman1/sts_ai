// Card-stack merging of Amber tokens (2026-11-17, Philipp: "Gleiche Karten zusammenfassen"); see AmberEncoder.h.
#include "sim/search/AmberEncoder.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>

namespace sts::search {

    namespace {

        constexpr int kCard = static_cast<int>(AmberTokenType::CARD);
        constexpr int kCardCap = kAmberCap[kCard];
        constexpr std::uint16_t kOne = 0x3c00;   // 1.0 in float16

        constexpr int kCopies = 41;              // (copies - 1) / 10

        // Float slots that tell two otherwise identical cards apart without making them different cards: the
        // master-deck index (out of combat, slot 11 with the deck flag 10 set) and the copy count of a stack.
        // Every other slot and id must match.
        bool deckCard(const AmberToken &t) { return t.f[10] == kOne; }
        bool ignored(const AmberToken &t, int j) { return j == kCopies || (j == 11 && deckCard(t)); }
        int copies(const AmberToken &t) {
            return static_cast<int>(std::lround(amberHalfToFloat(t.f[kCopies]) * 10.0f)) + 1;
        }

        bool sameCard(const AmberToken &a, const AmberToken &b) {
            if (a.ids != b.ids) return false;
            for (int j = 0; j < kAmberFloat; ++j)
                if (!ignored(a, j) && a.f[j] != b.f[j]) return false;
            return true;
        }

        std::uint64_t cardHash(const AmberToken &t) {
            std::uint64_t h = 0xcbf29ce484222325ull;
            auto add = [&](std::uint64_t w) { h = (h ^ w) * 0x100000001b3ull; };
            for (auto x : t.ids) add(static_cast<std::uint16_t>(x));
            for (int j = 0; j < kAmberFloat; ++j) add(ignored(t, j) ? 0u : t.f[j]);
            return h ^ (h >> 29);
        }

    }

    void amberMergeCards(AmberTokens &tk) {
        const int n = tk.n[kCard];
        if (n < 2) return;
        AmberToken *cards = &tk.tok[kAmberOff[kCard]];
        // Group identical cards, keeping the first occurrence's place (and its deck index).
        std::array<std::uint64_t, kCardCap> h{};
        std::array<std::uint8_t, kCardCap> order{};
        for (int i = 0; i < n; ++i) { h[i] = cardHash(cards[i]); order[i] = static_cast<std::uint8_t>(i); }
        std::array<std::uint8_t, kCardCap> rep{};    // old index -> its group's first old index
        std::array<int, kCardCap> count{};           // copies, per first old index
        std::sort(order.begin(), order.begin() + n, [&](std::uint8_t a, std::uint8_t b) {
            return h[a] != h[b] ? h[a] < h[b] : a < b;
        });
        for (int i = 0; i < n; ++i) rep[i] = static_cast<std::uint8_t>(i);
        for (int a = 0; a < n;) {
            int b = a + 1;
            while (b < n && h[order[b]] == h[order[a]]) ++b;
            // Within one hash run, group exactly (a collision keeps cards apart); order is ascending old index.
            for (int i = a; i < b; ++i) {
                const int x = order[i];
                if (rep[x] != x) continue;
                for (int j = i + 1; j < b; ++j) {
                    const int y = order[j];
                    if (rep[y] == y && sameCard(cards[x], cards[y])) rep[y] = static_cast<std::uint8_t>(x);
                }
            }
            a = b;
        }
        for (int i = 0; i < n; ++i) count[rep[i]] += copies(cards[i]);   // a stack counts its copies
        // Compact in old order; slot 41 = (copies - 1) / 10, so a single card encodes as before.
        std::array<std::uint8_t, kCardCap> newIdx{};
        int m = 0;
        for (int i = 0; i < n; ++i) {
            if (rep[i] != i) continue;
            if (m != i) std::memcpy(&cards[m], &cards[i], sizeof(AmberToken));
            cards[m].f[kCopies] = amberHalf((count[i] - 1) / 10.0f);
            newIdx[i] = static_cast<std::uint8_t>(m++);
        }
        if (m == n) return;
        tk.n[kCard] = static_cast<std::uint8_t>(m);
        for (int a = 0; a < tk.nAct; ++a) {
            auto &x = tk.act[a];
            if (x.srcSeg == kCard) x.srcIdx = newIdx[rep[x.srcIdx]];
            if (x.tgtSeg == kCard) x.tgtIdx = newIdx[rep[x.tgtIdx]];
        }
    }

}
