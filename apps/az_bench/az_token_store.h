// Global token dictionary of the stage 1 replay window (selfplay.py --compact-samples; 2026-11-18). Amber Eye: "we
// can still store the data efficiently by keeping a common dictionary of tokens which are referenced by index in
// replay buffer states. Most tokens, especially cards and relics, are shared between many different states".
//
// A fixed number of slots, each one distinct token (type, ids [4], f [64] float16 bits) with a reference count (the
// window's samples using it). intern adds references to tokens (a token already stored gets the same slot), release
// drops them; a slot whose count reaches 0 is free again. Lookup by a 64-bit content hash in an open-addressing
// table (linear probing, backward-shift deletion); a token whose hash is taken by another token's content (a 64-bit
// collision) gets a slot of its own outside the table, so a lookup never returns another token.
#pragma once

#include <cstdint>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace sts::azbench {

    class TokenStore {
    public:
        static constexpr int kCat = 4, kFloat = 64;

        explicit TokenStore(std::int64_t capacity) {
            if (capacity <= 0 || capacity >= (std::int64_t{1} << 31)) throw std::invalid_argument("TokenStore: capacity");
            cap_ = static_cast<std::size_t>(capacity);
            tokType_.assign(cap_, 0);
            ids_.assign(cap_ * kCat, 0);
            f_.assign(cap_ * kFloat, 0);
            ref_.assign(cap_, 0);
            indexed_.assign(cap_, 0);
            std::size_t n = 1;
            while (n < 2 * cap_) n <<= 1;
            mask_ = n - 1;
            tabHash_.assign(n, 0);
            tabSlot_.assign(n, -1);
            free_.reserve(cap_);
            for (std::size_t i = cap_; i-- > 0;) free_.push_back(static_cast<std::int32_t>(i));
        }

        std::size_t capacity() const { return cap_; }
        std::size_t freeSlots() const { return free_.size(); }
        std::size_t used() const { return cap_ - free_.size(); }

        // Distinct tokens among rows 0..n-1 that are not stored yet (slots intern would take, counts > 0 only).
        std::size_t countNew(std::size_t n, const std::int8_t *type, const std::int16_t *ids, const std::uint16_t *f,
                             const std::int64_t *counts) const {
            std::vector<std::uint64_t> seen;   // hashes of new tokens in this call (small open table)
            std::size_t m = 1;
            while (m < 2 * n + 2) m <<= 1;
            seen.assign(m, 0);
            std::size_t fresh = 0;
            for (std::size_t r = 0; r < n; ++r) {
                if (counts[r] <= 0) continue;
                const std::uint64_t h = hashOf(type[r], ids + r * kCat, f + r * kFloat);
                if (find(h, type[r], ids + r * kCat, f + r * kFloat) >= 0) continue;
                std::size_t i = h & (m - 1);
                bool dup = false;
                while (seen[i] != 0) {
                    if (seen[i] == h) { dup = true; break; }   // same hash in this call: counted once (a collision
                    i = (i + 1) & (m - 1);                     // inside one call may undercount by one; intern checks)
                }
                if (!dup) { seen[i] = h; ++fresh; }
            }
            return fresh;
        }

        // Adds counts[r] references to row r's token and writes its slot to slots[r] (-1 for counts[r] <= 0).
        // Throws (nothing changed for later rows) when no slot is free.
        void intern(std::size_t n, const std::int8_t *type, const std::int16_t *ids, const std::uint16_t *f,
                    const std::int64_t *counts, std::int32_t *slots) {
            for (std::size_t r = 0; r < n; ++r) {
                slots[r] = -1;
                if (counts[r] <= 0) continue;
                const std::int8_t t = type[r];
                const std::int16_t *id = ids + r * kCat;
                const std::uint16_t *fv = f + r * kFloat;
                const std::uint64_t h = hashOf(t, id, fv);
                std::int32_t s = find(h, t, id, fv);
                if (s < 0) {
                    if (free_.empty()) throw std::runtime_error("TokenStore: full");
                    s = free_.back();
                    free_.pop_back();
                    tokType_[s] = t;
                    std::memcpy(&ids_[static_cast<std::size_t>(s) * kCat], id, sizeof(std::int16_t) * kCat);
                    std::memcpy(&f_[static_cast<std::size_t>(s) * kFloat], fv, sizeof(std::uint16_t) * kFloat);
                    indexed_[s] = insert(h, s) ? 1 : 0;   // 0: hash held by other content (stays unshared)
                }
                ref_[s] += static_cast<std::int32_t>(counts[r]);
                slots[r] = s;
            }
        }

        // Drops one reference per entry of slots; a slot at 0 references is free again.
        void release(std::size_t n, const std::int32_t *slots) {
            for (std::size_t k = 0; k < n; ++k) {
                const std::int32_t s = slots[k];
                if (s < 0 || static_cast<std::size_t>(s) >= cap_ || ref_[s] <= 0) throw std::runtime_error("TokenStore: bad release");
                if (--ref_[s] == 0) {
                    if (indexed_[s])   // the hash is recomputed from the slot's content (not stored)
                        erase(hashOf(tokType_[s], &ids_[static_cast<std::size_t>(s) * kCat], &f_[static_cast<std::size_t>(s) * kFloat]));
                    indexed_[s] = 0;
                    free_.push_back(s);
                }
            }
        }

        // Restores a saved state (selfplay.py --replay-save / --replay-load): slot contents and reference counts as
        // tokType() / ids() / f() / refs() held them. Free slots and the lookup table are rebuilt (a 64-bit hash
        // collision may index the other one of the two tokens than before; both stay correct).
        void restore(const std::int8_t *type, const std::int16_t *ids, const std::uint16_t *f, const std::int32_t *refs) {
            std::memcpy(tokType_.data(), type, cap_);
            std::memcpy(ids_.data(), ids, sizeof(std::int16_t) * cap_ * kCat);
            std::memcpy(f_.data(), f, sizeof(std::uint16_t) * cap_ * kFloat);
            std::memcpy(ref_.data(), refs, sizeof(std::int32_t) * cap_);
            std::fill(tabHash_.begin(), tabHash_.end(), 0);
            std::fill(tabSlot_.begin(), tabSlot_.end(), -1);
            free_.clear();
            for (std::size_t i = cap_; i-- > 0;) {
                const auto s = static_cast<std::int32_t>(i);
                if (ref_[i] < 0) throw std::invalid_argument("TokenStore.restore: negative reference count");
                if (ref_[i] == 0) { indexed_[i] = 0; free_.push_back(s); continue; }
                indexed_[i] = insert(hashOf(tokType_[i], &ids_[i * kCat], &f_[i * kFloat]), s) ? 1 : 0;
            }
        }

        std::int8_t *tokType() { return tokType_.data(); }
        std::int16_t *ids() { return ids_.data(); }
        std::uint16_t *f() { return f_.data(); }
        const std::int32_t *refs() const { return ref_.data(); }
        std::size_t bytes() const {
            return cap_ * (1 + 2 * kCat + 2 * kFloat + sizeof(std::int32_t) + 1 + 4) + tabHash_.size() * 12;
        }

    private:
        static std::uint64_t hashOf(std::int8_t t, const std::int16_t *id, const std::uint16_t *fv) {
            std::uint64_t h = 0x9e3779b97f4a7c15ull * static_cast<std::uint64_t>(static_cast<std::uint8_t>(t) + 1);
            auto mix = [&h](std::uint64_t w) {
                h ^= w + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
                h *= 0xbf58476d1ce4e5b9ull;
                h ^= h >> 31;
            };
            for (int c = 0; c < kCat; ++c) mix(static_cast<std::uint16_t>(id[c]));
            for (int c = 0; c < kFloat; ++c) mix(fv[c]);
            return h == 0 ? 1 : h;   // 0 marks an empty table entry
        }

        bool same(std::int32_t s, std::int8_t t, const std::int16_t *id, const std::uint16_t *fv) const {
            return tokType_[s] == t &&
                   std::memcmp(&ids_[static_cast<std::size_t>(s) * kCat], id, sizeof(std::int16_t) * kCat) == 0 &&
                   std::memcmp(&f_[static_cast<std::size_t>(s) * kFloat], fv, sizeof(std::uint16_t) * kFloat) == 0;
        }

        // The slot holding this token, or -1.
        std::int32_t find(std::uint64_t h, std::int8_t t, const std::int16_t *id, const std::uint16_t *fv) const {
            for (std::size_t i = h & mask_; tabHash_[i] != 0; i = (i + 1) & mask_)
                if (tabHash_[i] == h) return same(tabSlot_[i], t, id, fv) ? tabSlot_[i] : -1;
            return -1;
        }

        bool insert(std::uint64_t h, std::int32_t s) {
            std::size_t i = h & mask_;
            for (; tabHash_[i] != 0; i = (i + 1) & mask_)
                if (tabHash_[i] == h) return false;
            tabHash_[i] = h;
            tabSlot_[i] = s;
            return true;
        }

        void erase(std::uint64_t h) {
            std::size_t i = h & mask_;
            while (tabHash_[i] != h) {
                if (tabHash_[i] == 0) return;
                i = (i + 1) & mask_;
            }
            // Backward-shift deletion: move later entries of the probe run into the hole when their home allows.
            std::size_t j = i;
            for (;;) {
                j = (j + 1) & mask_;
                if (tabHash_[j] == 0) break;
                const std::size_t home = tabHash_[j] & mask_;
                const bool between = i <= j ? (home > i && home <= j) : (home > i || home <= j);
                if (between) continue;   // its home lies after the hole: it must stay
                tabHash_[i] = tabHash_[j];
                tabSlot_[i] = tabSlot_[j];
                i = j;
            }
            tabHash_[i] = 0;
            tabSlot_[i] = -1;
        }

        std::size_t cap_ = 0, mask_ = 0;
        std::vector<std::int8_t> tokType_;
        std::vector<std::int16_t> ids_;
        std::vector<std::uint16_t> f_;
        std::vector<std::int32_t> ref_;
        std::vector<std::uint8_t> indexed_;
        std::vector<std::uint64_t> tabHash_;
        std::vector<std::int32_t> tabSlot_;
        std::vector<std::int32_t> free_;
    };

}  // namespace sts::azbench
