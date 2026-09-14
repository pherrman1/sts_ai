#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <sstream>
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
    // Independent legacy oracle: preserve stringify/character-parse/strtof.
    const auto compare = [&](const GameContext &gc, const one_combat::PathHistory &path) {
        std::vector<float> old; std::string cur;
        for (char c : one_combat::richRow(gc, path)) {
            if (c == ',') { old.push_back(std::strtof(cur.c_str(), nullptr)); cur.clear(); }
            else cur += c;
        }
        if (!cur.empty()) old.push_back(std::strtof(cur.c_str(), nullptr));
        const auto numeric = one_combat::richFeatureVec(gc, path);
        if (old.size() != numeric.size() || old.size() != one_combat::richIdxMap().size()
            || std::memcmp(old.data(), numeric.data(), old.size() * sizeof(float)) != 0) {
            std::cerr << "numeric rich feature bitwise mismatch\n"; return false;
        }
        return true;
    };
    ok &= compare(base, emptyPath); ok &= compare(enriched, enrichedPath);
    for (int i = 0; i < 4096; ++i) {
        auto gc = enriched; auto path = enrichedPath;
        gc.ascension = i % 21; gc.act = i % 4 + 1; gc.floorNum = i % 60;
        gc.maxHp = 1 + i % 200; gc.curHp = i % (gc.maxHp + 1);
        // Stress integral-to-float rounding at and above the exact integer range.
        const int edges[] = {0, -1, 16777215, 16777216, 16777217,
            std::numeric_limits<int>::max(), std::numeric_limits<int>::min()};
        gc.gold = edges[i % 7]; gc.potionChance = i % 101;
        gc.cardRarityFactor = i % 50 - 25;
        gc.blueKey = i & 1; gc.greenKey = i & 2; gc.redKey = i & 4;
        gc.monsterListOffset = i % (gc.monsterList.size() + 1);
        gc.eliteMonsterListOffset = i % (gc.eliteMonsterList.size() + 1);
        gc.curMapNodeX = i % 7; gc.curMapNodeY = i % 17 - 1;
        if (i & 8) gc.map.reset();
        gc.potionCapacity = i % 6; gc.potionCount = gc.potionCapacity;
        for (int j = 0; j < 5; ++j) gc.potions[j] = static_cast<Potion>((i + j) % one_combat::kNumPotions);
        gc.relics.relics[0].data = i % 100 - 50;
        gc.deck.cards.clear(); gc.deck.bottleIdxs = {-1, -1, -1};
        for (int j = 0; j < i % (Deck::MAX_SIZE + 1); ++j)
            gc.deck.cards.push_back(Card(static_cast<CardId>((i + j) % one_combat::kNumCardIds), (i + j) % 2));
        if (gc.deck.size() >= 3) {
            const int n = gc.deck.size();
            gc.deck.cards[n - 3] = Card(CardId::IRON_WAVE, i % 2);
            gc.deck.cards[n - 2] = Card(CardId::DEFEND_RED, i % 2);
            gc.deck.cards[n - 1] = Card(CardId::INFLAME, i % 2);
            gc.deck.bottleIdxs = {n - 3, n - 2, n - 1};
        }
        for (int j = 0; j < 10; ++j) path.roomVisits[j] = (i * (j + 1)) % 100;
        ok &= compare(gc, path);
    }
    std::cout << "rich feature parity: 4098 states, every float bitwise compared\n";
    return ok ? 0 : 1;
}
