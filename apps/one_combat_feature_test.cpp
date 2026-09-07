#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "game/GameContext.h"
#include "one_combat/run_features.h"

namespace {

std::uint64_t fnv1a(const std::string &s) {
    std::uint64_t h = 1469598103934665603ULL;
    for (const unsigned char c : s) { h ^= c; h *= 1099511628211ULL; }
    return h;
}

std::uint64_t indexMapHash() {
    std::vector<std::pair<std::string, int>> entries;
    for (const auto &entry : one_combat::richIdxMap()) entries.push_back(entry);
    std::sort(entries.begin(), entries.end());
    std::string serialized;
    for (const auto &[name, index] : entries) serialized += name + "=" + std::to_string(index) + ";";
    return fnv1a(serialized);
}

bool checkHash(const char *label, std::uint64_t actual, std::uint64_t expected) {
    if (actual == expected) return true;
    std::cerr << label << " hash mismatch: got " << std::hex << actual
              << ", expected " << expected << std::dec << '\n';
    return false;
}

} // namespace

int main() {
    using namespace sts;

    GameContext base(CharacterClass::IRONCLAD, 126700, 0);
    one_combat::PathHistory emptyPath;

    GameContext enriched = base;
    enriched.curMapNodeX = 0;
    enriched.curMapNodeY = 0;
    enriched.deck.obtainRaw(Card(CardId::IRON_WAVE, 1));
    enriched.deck.bottleCard(enriched.deck.size() - 1, CardType::ATTACK);
    enriched.relics.add({RelicId::AKABEKO, 3});
    enriched.potionCapacity = 3;
    enriched.potions[0] = Potion::FIRE_POTION;
    one_combat::PathHistory enrichedPath;
    enrichedPath.update(enriched);

    // These fingerprints cover every byte of the pre-extraction strings and every
    // sorted name-to-index entry; they are deliberately not length-only checks.
    bool ok = true;
    ok &= checkHash("rich header", fnv1a(one_combat::richHeader()), 0xcc1f07b72cb1de88ULL);
    ok &= checkHash("rich state header", fnv1a(one_combat::richStateHeader()), 0x139ef99f9e90e706ULL);
    ok &= checkHash("empty row", fnv1a(one_combat::richRow(base, emptyPath)), 0x5b207136f96a9f2aULL);
    ok &= checkHash("enriched row", fnv1a(one_combat::richRow(enriched, enrichedPath)), 0xabdd40a53f97d6fcULL);
    ok &= checkHash("rich index map", indexMapHash(), 0x7172f89039e330d6ULL);
    return ok ? 0 : 1;
}
