#ifndef STS_LIGHTSPEED_SMALL_SORTED_MAP_H
#define STS_LIGHTSPEED_SMALL_SORTED_MAP_H

#include <array>
#include <cstdint>
#include <stdexcept>
#include <utility>

namespace sts {

    // Drop-in for the std::map subset Player::statusMap uses, stored inline:
    // entries sorted by key (the same iteration order as std::map), at most
    // `capacity` distinct keys. Copying moves only the used entries, so a
    // BattleContext copy no longer allocates map nodes.
    template <typename K, typename V, int capacity>
    class SmallSortedMap {
    public:
        using value_type = std::pair<K, V>;
        using iterator = value_type *;
        using const_iterator = const value_type *;

        SmallSortedMap() = default;
        SmallSortedMap(const SmallSortedMap &rhs) { *this = rhs; }
        SmallSortedMap &operator=(const SmallSortedMap &rhs) {
            n = rhs.n;
            for (int i = 0; i < n; ++i) data[i] = rhs.data[i];
            return *this;
        }

        iterator begin() { return data.data(); }
        iterator end() { return data.data() + n; }
        const_iterator begin() const { return data.data(); }
        const_iterator end() const { return data.data() + n; }
        [[nodiscard]] std::size_t size() const { return static_cast<std::size_t>(n); }
        [[nodiscard]] bool empty() const { return n == 0; }
        void clear() { n = 0; }

        iterator find(const K &k) {
            const int i = lowerBound(k);
            return i < n && data[i].first == k ? data.data() + i : end();
        }
        const_iterator find(const K &k) const {
            const int i = lowerBound(k);
            return i < n && data[i].first == k ? data.data() + i : end();
        }
        [[nodiscard]] std::size_t count(const K &k) const { return find(k) != end() ? 1 : 0; }

        V &at(const K &k) {
            const auto it = find(k);
            if (it == end()) throw std::out_of_range("SmallSortedMap::at");
            return it->second;
        }
        const V &at(const K &k) const {
            const auto it = find(k);
            if (it == end()) throw std::out_of_range("SmallSortedMap::at");
            return it->second;
        }

        V &operator[](const K &k) { return insertAt(lowerBound(k), k, V{}).first->second; }

        // Like std::map::emplace: no change when the key is already present.
        std::pair<iterator, bool> emplace(const K &k, const V &v) { return insertAt(lowerBound(k), k, v); }

        bool operator==(const SmallSortedMap &rhs) const {
            if (n != rhs.n) return false;
            for (int i = 0; i < n; ++i)
                if (data[i] != rhs.data[i]) return false;
            return true;
        }

    private:
        std::array<value_type, capacity> data{};
        std::int16_t n = 0;

        [[nodiscard]] int lowerBound(const K &k) const {
            int i = 0;
            while (i < n && data[i].first < k) ++i;
            return i;
        }

        std::pair<iterator, bool> insertAt(int i, const K &k, const V &v) {
            if (i < n && data[i].first == k) return {data.data() + i, false};
            if (n == capacity) throw std::length_error("SmallSortedMap capacity");
            for (int j = n; j > i; --j) data[j] = data[j - 1];
            data[i] = {k, v};
            ++n;
            return {data.data() + i, true};
        }
    };

}

#endif //STS_LIGHTSPEED_SMALL_SORTED_MAP_H
