#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include "combat/PlayerStatusMap.h"

namespace {
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
void equal(const sts::PlayerStatusMap &actual,
           const std::map<PlayerStatus, std::int16_t> &expected) {
    require(actual.size() == expected.size(), "membership count");
    auto it = actual.begin();
    for (const auto &[key, value] : expected) {
        require(it != actual.end() && it->first == key && it->second == value,
                "sorted wire iteration and signed values");
        require(actual.at(key) == value, "const lookup");
        ++it;
    }
    require(it == actual.end(), "iteration length");
}
}

int main() {
    try {
        sts::PlayerStatusMap actual;
        std::map<PlayerStatus, std::int16_t> expected;
        require(actual.empty(), "initial empty");
        bool threw = false;
        try { actual.at(PS::WEAK); } catch (const std::out_of_range &) { threw = true; }
        require(threw && actual.empty(), "missing at throws without inserting");
        // Cover the complete uint8_t key domain, including values received by
        // wire casts outside the named enum, in a non-sorted permutation.
        for (int n = 0; n < 256; ++n) {
            const auto key = static_cast<PlayerStatus>((n * 157) & 255);
            const auto value = static_cast<std::int16_t>(n % 3 == 0 ? 0 : n % 2 ? -n : n);
            auto [it, inserted] = actual.emplace(key, value);
            expected.emplace(key, value);
            require(inserted && it->first == key && it->second == value, "insert result");
            require(!actual.emplace(key, 12345).second, "duplicate preserves first value");
            equal(actual, expected);
        }
        actual[PS::WEAK] = expected[PS::WEAK] = std::numeric_limits<std::int16_t>::min();
        actual.at(PS::FRAIL) = expected.at(PS::FRAIL) = std::numeric_limits<std::int16_t>::max();
        equal(actual, expected);
        auto copied = actual;
        require(copied == actual, "copy equality");
        copied[PS::WEAK] = 0;
        require(!(copied == actual), "copy independence and value inequality");
        copied = actual;
        auto moved = std::move(copied);
        require(moved == actual, "move equality");
        actual.clear(); expected.clear();
        require(actual.empty(), "clear");
        require(actual[PS::WEAK] == 0, "subscript inserts zero");
        expected[PS::WEAK];
        equal(actual, expected);
        require(!(actual == sts::PlayerStatusMap{}), "zero membership differs from absence");
        const auto &constant = actual;
        threw = false;
        try { constant.at(PS::FRAIL); } catch (const std::out_of_range &) { threw = true; }
        require(threw && actual.size() == 1, "const missing lookup");
        std::cout << "PASS: Silver status storage matches ordered map membership, values, copy and iteration\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
