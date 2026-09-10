#ifndef STS_SILVER_PLAYER_STATUS_MAP_H
#define STS_SILVER_PLAYER_STATUS_MAP_H

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>
#include "constants/PlayerStatusEffects.h"

namespace sts {

// Sorted sparse storage for copied combat states. Membership is independent of
// value: an explicitly stored zero must survive equality and wire conversion.
// Insertion invalidates iterators/references; status-processing loops only queue
// actions or change status bits, and must not insert while iterating this map.
class PlayerStatusMap {
    using Storage = std::vector<std::pair<PlayerStatus, std::int16_t>>;
    Storage entries;

    auto lowerBound(PlayerStatus key) {
        return std::lower_bound(entries.begin(), entries.end(), key,
            [](const auto &entry, PlayerStatus status) { return entry.first < status; });
    }
    auto lowerBound(PlayerStatus key) const {
        return std::lower_bound(entries.begin(), entries.end(), key,
            [](const auto &entry, PlayerStatus status) { return entry.first < status; });
    }

public:
    // Iteration exposes immutable keys/values; mutations go through [] or at().
    using const_iterator = Storage::const_iterator;
    const_iterator begin() const noexcept { return entries.begin(); }
    const_iterator end() const noexcept { return entries.end(); }
    std::size_t size() const noexcept { return entries.size(); }
    bool empty() const noexcept { return entries.empty(); }
    void clear() noexcept { entries.clear(); }

    const_iterator find(PlayerStatus key) const {
        auto it = lowerBound(key);
        return it != entries.end() && it->first == key ? it : entries.end();
    }
    std::pair<const_iterator, bool> emplace(PlayerStatus key, std::int16_t value) {
        auto it = lowerBound(key);
        if (it != entries.end() && it->first == key) return {it, false};
        return {entries.insert(it, {key, value}), true};
    }
    std::int16_t &operator[](PlayerStatus key) {
        auto it = lowerBound(key);
        if (it == entries.end() || it->first != key) it = entries.insert(it, {key, 0});
        return it->second;
    }
    std::int16_t &at(PlayerStatus key) {
        auto it = lowerBound(key);
        if (it == entries.end() || it->first != key) throw std::out_of_range("PlayerStatusMap::at");
        return it->second;
    }
    const std::int16_t &at(PlayerStatus key) const {
        auto it = find(key);
        if (it == end()) throw std::out_of_range("PlayerStatusMap::at");
        return it->second;
    }
    bool operator==(const PlayerStatusMap &other) const { return entries == other.entries; }
};
} // namespace sts
#endif
