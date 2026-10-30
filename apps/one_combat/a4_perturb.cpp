#include "a4_perturb.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "heart1_policy.h"

using namespace sts;

namespace one_combat {
namespace {
struct A4CardCount { int card; int upgraded; int count; };
struct A4RelicCount { int relic; int count; };
struct A4PotionCount { int potion; int count; };
#include "a4_perturb_tables.inc"

// Relics whose pickup changes other fields or opens a screen, whose loss would leave other fields stale (bottles,
// Potion Belt, Wing Boots), or that a run cannot lose (starters) or never holds as a real relic (Circlets): never
// added or removed.
bool structuralRelic(RelicId r) {
    switch (r) {
        case RelicId::BURNING_BLOOD: case RelicId::BLACK_BLOOD:
        case RelicId::ASTROLABE: case RelicId::BOTTLED_FLAME: case RelicId::BOTTLED_LIGHTNING:
        case RelicId::BOTTLED_TORNADO: case RelicId::CALLING_BELL: case RelicId::CAULDRON:
        case RelicId::DOLLYS_MIRROR: case RelicId::EMPTY_CAGE: case RelicId::LEES_WAFFLE: case RelicId::MANGO:
        case RelicId::NECRONOMICON: case RelicId::NEOWS_LAMENT: case RelicId::OLD_COIN: case RelicId::ORRERY:
        case RelicId::PANDORAS_BOX: case RelicId::PEAR: case RelicId::POTION_BELT: case RelicId::PRISMATIC_SHARD:
        case RelicId::STRAWBERRY: case RelicId::TINY_HOUSE: case RelicId::WAR_PAINT: case RelicId::WHETSTONE:
        case RelicId::WING_BOOTS: case RelicId::CIRCLET: case RelicId::RED_CIRCLET: case RelicId::INVALID:
            return true;
        default:
            return false;
    }
}

// Out-of-combat counters (RelicInstance::data) and their ranges, as BattleContext reads and writes them back.
int counterLimit(RelicId r) {
    switch (r) {
        case RelicId::HAPPY_FLOWER: case RelicId::SUNDIAL: return 3;   // 0..2
        case RelicId::INCENSE_BURNER: return 6;                        // 0..5
        case RelicId::INK_BOTTLE: case RelicId::NUNCHAKU: case RelicId::PEN_NIB: return 10;   // 0..9
        default: return 0;
    }
}

bool addableCard(const Card &c) {
    const auto type = c.getType();
    return (type == CardType::ATTACK || type == CardType::SKILL || type == CardType::POWER)
        && c.getRarity() != CardRarity::BASIC;
}

// Non-basic cards a shop could remove without side effects (Parasite costs max HP), never a bottled card.
bool removableCard(const GameContext &gc, int idx) {
    const auto &c = gc.deck.cards[idx];
    if (gc.deck.isCardBottled(idx) || c.getRarity() == CardRarity::BASIC || c.getId() == CardId::PARASITE) return false;
    return c.getType() != CardType::CURSE || c.canTransform();
}

class Draw {
    std::mt19937_64 rng_;
public:
    Draw(std::uint64_t specSeed, int child) {
        std::seed_seq seq{specSeed, std::uint64_t(child), std::uint64_t(0x41345045525455ULL)};   // "A4PERTU"
        rng_.seed(seq);
    }
    std::uint64_t below(std::uint64_t n) { return rng_() % n; }
    int between(int lo, int hi) { return lo + int(below(std::uint64_t(hi - lo + 1))); }
    bool coin() { return below(2) == 1; }
    template <class T> std::size_t weighted(const std::vector<T> &rows) {
        std::uint64_t total = 0;
        for (const auto &r : rows) total += std::uint64_t(r.count);
        auto x = below(total);
        for (std::size_t i = 0; i < rows.size(); ++i) {
            if (x < std::uint64_t(rows[i].count)) return i;
            x -= std::uint64_t(rows[i].count);
        }
        throw std::logic_error("weighted draw");
    }
};

std::vector<A4CardCount> addableCards(const GameContext &gc) {
    std::vector<A4CardCount> out;
    if (gc.deck.size() >= Deck::MAX_SIZE) return out;
    for (const auto &row : kA4Cards)
        if (addableCard(Card(CardId(row.card)))) out.push_back(row);
    return out;
}
std::vector<A4RelicCount> addableRelics(const GameContext &gc) {
    std::vector<A4RelicCount> out;
    for (const auto &row : kA4Relics)
        if (!structuralRelic(RelicId(row.relic)) && !gc.relics.has(RelicId(row.relic))) out.push_back(row);
    return out;
}
std::vector<A4PotionCount> addablePotions(const GameContext &gc) {
    std::vector<A4PotionCount> out;
    if (gc.relics.has(RelicId::SOZU) || gc.potionCount >= gc.potionCapacity) return out;
    for (const auto &row : kA4Potions)
        if (Potion(row.potion) != Potion::EMPTY_POTION_SLOT && Potion(row.potion) != Potion::INVALID) out.push_back(row);
    return out;
}
std::vector<int> deckIdxs(const GameContext &gc, const std::function<bool(int)> &keep) {
    std::vector<int> out;
    for (int i = 0; i < gc.deck.size(); ++i) if (keep(i)) out.push_back(i);
    return out;
}
std::vector<RelicId> heldRelics(const GameContext &gc, bool counters) {
    std::vector<RelicId> out;
    for (const auto &r : gc.relics.relics)
        if (counters ? counterLimit(r.id) > 0 : !structuralRelic(r.id)) out.push_back(r.id);
    return out;
}

nlohmann::json cardJson(const Card &c) {
    return {{"id", cardEnumStrings[int(c.getId())]}, {"upgraded", c.getUpgraded()}};
}
const char *relicName(RelicId r) { return relicEnumNames[int(r)]; }

void addCard(GameContext &gc, Card c) {
    // Deck::obtain's egg upgrades, without its other pickup effects (Ceramic Fish gold).
    const auto type = c.getType();
    if (!c.isUpgraded() && ((type == CardType::ATTACK && gc.relics.has(RelicId::MOLTEN_EGG))
            || (type == CardType::SKILL && gc.relics.has(RelicId::TOXIC_EGG))
            || (type == CardType::POWER && gc.relics.has(RelicId::FROZEN_EGG))))
        c.upgrade();
    gc.deck.obtainRaw(c);
}
void addRelic(GameContext &gc, RelicId r) {
    if (gc.obtainRelic(r)) throw std::logic_error("STS_A4_PERTURB relic opened a screen");
    // As a reward would: the relic leaves every pool, so no later shop offers it again.
    for (auto *pool : {&gc.commonRelicPool, &gc.uncommonRelicPool, &gc.rareRelicPool, &gc.shopRelicPool,
                       &gc.bossRelicPool})
        pool->erase(std::remove(pool->begin(), pool->end(), r), pool->end());
}
}  // namespace

std::optional<A4PerturbSpec> parseA4Perturb(const char *value) {
    if (!value || !*value) return std::nullopt;
    const std::string text(value);
    std::vector<std::string> parts;
    for (std::size_t at = 0;;) {
        const auto next = text.find(':', at);
        parts.push_back(text.substr(at, next == std::string::npos ? std::string::npos : next - at));
        if (next == std::string::npos) break;
        at = next + 1;
    }
    const auto digits = [](const std::string &t, std::size_t limit) {
        return !t.empty() && t.size() <= limit && t.find_first_not_of("0123456789") == std::string::npos;
    };
    if (parts.size() != 4 || !digits(parts[0], 6) || !digits(parts[1], 19) || !digits(parts[2], 2)
            || !digits(parts[3], 19) || std::stoi(parts[2]) < 1)
        throw std::runtime_error("STS_A4_PERTURB must be INDEX:SALT:K:SPECSEED (K 1-99 children, child 0 the"
                                 " unchanged control; SALT 0 keeps the game's own future)");
    return A4PerturbSpec{std::stoull(parts[0]), std::stoull(parts[1]), std::stoi(parts[2]), std::stoull(parts[3])};
}

const std::optional<A4PerturbSpec> &a4PerturbSpec() {
    static const auto spec = parseA4Perturb(std::getenv("STS_A4_PERTURB"));
    return spec;
}

nlohmann::json applyA4Perturbation(GameContext &gc, std::uint64_t specSeed, int child) {
    if (child == 0) return {{"child", 0}, {"op", "none"}};
    Draw draw(specSeed, child);
    const auto cards = addableCards(gc);
    const auto relics = addableRelics(gc);
    const auto potions = addablePotions(gc);
    const auto removable = deckIdxs(gc, [&](int i) { return removableCard(gc, i); });
    const auto upgradeable = deckIdxs(gc, [&](int i) {
        const auto &c = gc.deck.cards[i];
        return c.canUpgrade() && c.getType() != CardType::CURSE && c.getType() != CardType::STATUS;
    });
    const auto upgraded = deckIdxs(gc, [&](int i) {
        const auto &c = gc.deck.cards[i];
        return c.upgraded && c.getId() != CardId::SEARING_BLOW;
    });
    const auto held = heldRelics(gc, false);
    const auto counters = heldRelics(gc, true);
    std::vector<int> filledSlots;
    for (int i = 0; i < gc.potionCapacity; ++i)
        if (gc.potions[i] != Potion::EMPTY_POTION_SLOT) filledSlots.push_back(i);

    std::vector<std::string> ops = {"hp", "max_hp", "gold"};
    if (!cards.empty()) ops.push_back("card_add");
    if (!removable.empty()) ops.push_back("card_remove");
    if (!upgradeable.empty()) ops.push_back("upgrade");
    if (!upgraded.empty()) ops.push_back("unupgrade");
    if (!relics.empty()) ops.push_back("relic_add");
    if (!held.empty()) ops.push_back("relic_remove");
    if (!relics.empty() && !held.empty()) ops.push_back("relic_swap");
    if (!counters.empty()) ops.push_back("relic_counter");
    if (!potions.empty()) ops.push_back("potion_add");
    if (!filledSlots.empty()) ops.push_back("potion_remove");
    const auto op = ops[draw.below(ops.size())];
    nlohmann::json out = {{"child", child}, {"op", op}};

    if (op == "hp") {
        // +-(5..25)% of max HP, clamped to 1..max; the sign that can move HP at all when the other cannot.
        const int pct = draw.between(5, 25);
        const int delta = std::max(1, int(std::lround(pct * gc.maxHp / 100.0)));
        bool up = draw.coin();
        if (up && gc.curHp >= gc.maxHp) up = false;
        if (!up && gc.curHp <= 1) up = true;
        const int after = std::clamp(gc.curHp + (up ? delta : -delta), 1, gc.maxHp);
        out.update({{"field", "curHp"}, {"before", gc.curHp}, {"after", after}, {"percent", up ? pct : -pct}});
        gc.curHp = after;
    } else if (op == "max_hp") {
        // +-(3..10) max HP as the game changes it: a gain heals the same amount (playerIncreaseMaxHp, no heal under
        // Mark of the Bloom), a loss lowers current HP only to the new max (loseMaxHp).
        int delta = draw.between(3, 10);
        const bool up = draw.coin();
        if (!up) delta = std::min(delta, gc.maxHp - 1);
        out.update({{"field", "maxHp"}, {"before", gc.maxHp}, {"curHpBefore", gc.curHp}});
        if (up) gc.playerIncreaseMaxHp(delta);
        else gc.loseMaxHp(delta);
        out.update({{"after", gc.maxHp}, {"curHpAfter", gc.curHp}});
    } else if (op == "gold") {
        const int delta = draw.between(25, 150);
        bool up = draw.coin();
        if (!up && gc.gold == 0) up = true;
        const int after = std::max(0, gc.gold + (up ? delta : -delta));
        out.update({{"field", "gold"}, {"before", gc.gold}, {"after", after}});
        gc.gold = after;
    } else if (op == "card_add") {
        const auto &row = cards[draw.weighted(cards)];
        Card c(CardId(row.card));
        if (row.upgraded) c.upgrade();
        addCard(gc, c);
        out.update({{"field", "deck"}, {"card", cardJson(gc.deck.cards.back())}});
    } else if (op == "card_remove") {
        const int idx = removable[draw.below(removable.size())];
        out.update({{"field", "deck"}, {"card", cardJson(gc.deck.cards[idx])}, {"deckIdx", idx}});
        gc.deck.remove(gc, idx);
    } else if (op == "upgrade") {
        const int idx = upgradeable[draw.below(upgradeable.size())];
        out.update({{"field", "deck"}, {"card", cardJson(gc.deck.cards[idx])}, {"deckIdx", idx}});
        gc.deck.upgrade(idx);
    } else if (op == "unupgrade") {
        const int idx = upgraded[draw.below(upgraded.size())];
        out.update({{"field", "deck"}, {"card", cardJson(gc.deck.cards[idx])}, {"deckIdx", idx}});
        auto &c = gc.deck.cards[idx];
        const bool could = c.canUpgrade();
        c.upgraded = false;
        gc.deck.upgradeableCount += int(c.canUpgrade()) - int(could);
    } else if (op == "relic_add") {
        const auto r = RelicId(relics[draw.weighted(relics)].relic);
        addRelic(gc, r);
        out.update({{"field", "relics"}, {"added", relicName(r)}});
    } else if (op == "relic_remove") {
        const auto r = held[draw.below(held.size())];
        gc.relics.remove(r);
        out.update({{"field", "relics"}, {"removed", relicName(r)}});
    } else if (op == "relic_swap") {
        const auto removed = held[draw.below(held.size())];
        const auto added = RelicId(relics[draw.weighted(relics)].relic);
        gc.relics.remove(removed);
        addRelic(gc, added);
        out.update({{"field", "relics"}, {"removed", relicName(removed)}, {"added", relicName(added)}});
    } else if (op == "relic_counter") {
        const auto r = counters[draw.below(counters.size())];
        int &data = gc.relics.getRelicValueRef(r);
        const int limit = counterLimit(r);
        int after = int(draw.below(std::uint64_t(limit - 1)));
        if (after >= data) ++after;   // any other value of the counter
        out.update({{"field", "relics"}, {"relic", relicName(r)}, {"before", data}, {"after", after}});
        data = after;
    } else if (op == "potion_add") {
        const auto p = Potion(potions[draw.weighted(potions)].potion);
        gc.obtainPotion(p);
        out.update({{"field", "potions"}, {"added", getPotionName(p)}});
    } else if (op == "potion_remove") {
        const int slot = filledSlots[draw.below(filledSlots.size())];
        out.update({{"field", "potions"}, {"removed", getPotionName(gc.potions[slot])}, {"slot", slot}});
        gc.discardPotionAtIdx(slot);
    }
    return out;
}

namespace {
// Every field an operator may touch, in groups, plus every game Random and the screen.
struct Fields {
    int curHp, maxHp, gold;
    std::vector<std::array<int, 3>> deck;
    std::array<int, 4> typeCounts;
    std::array<int, 3> bottles;
    int upgradeable, transformable;
    std::vector<std::array<int, 2>> relics;
    std::array<std::uint64_t, 3> relicBits;
    std::vector<std::vector<RelicId>> pools;
    std::array<int, 5> potions;
    int potionCount, potionCapacity;
    std::vector<std::array<std::uint64_t, 3>> rngs;
    std::vector<int> other;
};
Fields fields(const GameContext &gc) {
    Fields f{gc.curHp, gc.maxHp, gc.gold, {}, gc.deck.cardTypeCounts, gc.deck.bottleIdxs,
             gc.deck.upgradeableCount, gc.deck.transformableCount, {},
             {gc.relics.relicBits0, gc.relics.relicBits1, gc.relics.relicBits2},
             {gc.commonRelicPool, gc.uncommonRelicPool, gc.rareRelicPool, gc.shopRelicPool, gc.bossRelicPool},
             {}, gc.potionCount, gc.potionCapacity, {},
             {gc.act, gc.floorNum, int(gc.screenState), gc.wingBootsCharges, gc.redKey, gc.greenKey, gc.blueKey,
              gc.curMapNodeX, gc.curMapNodeY, gc.ascension, int(gc.outcome)}};
    for (const auto &c : gc.deck.cards) f.deck.push_back({int(c.id), int(c.upgraded), int(c.misc)});
    for (const auto &r : gc.relics.relics) f.relics.push_back({int(r.id), r.data});
    for (int i = 0; i < 5; ++i) f.potions[i] = int(gc.potions[i]);
    for (const Random *r : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng, &gc.mathUtilRng,
                            &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng, &gc.monsterRng, &gc.neowRng,
                            &gc.potionRng, &gc.relicRng, &gc.shuffleRng, &gc.treasureRng})
        f.rngs.push_back({std::uint64_t(r->counter), r->seed0, r->seed1});
    return f;
}
// Deck caches recomputed from the cards, as Deck::obtainRaw counts them.
std::array<int, 6> deckCounts(const GameContext &gc) {
    std::array<int, 6> n{};
    for (const auto &c : gc.deck.cards) {
        const auto type = c.getType();
        if (type == CardType::CURSE ? c.canTransform() : true) { ++n[int(type)]; ++n[4]; }
        if (type != CardType::CURSE && c.canUpgrade()) ++n[5];
    }
    return n;
}
}  // namespace

int a4PerturbSelfTest() {
    const auto check = [](bool ok, const std::string &what) {
        if (!ok) throw std::runtime_error("a4 perturb selftest: " + what);
    };
    check(!parseA4Perturb(nullptr) && !parseA4Perturb(""), "unset must be off");
    const auto spec = parseA4Perturb("731:5:16:99");
    check(spec && spec->index == 731 && spec->salt == 5 && spec->children == 16 && spec->specSeed == 99, "parse");
    for (const char *bad : {"1:2:3", "1:2:0:4", "1:2:100:4", "1:2:3:4:5", "a:2:3:4", "1::3:4", "1:2:3:", "1:2:-3:4"}) {
        bool refused = false;
        try { parseA4Perturb(bad); } catch (const std::runtime_error &) { refused = true; }
        check(refused, std::string("refuse ") + bad);
    }

    // An Act-4-like fixture (seed 42 builds pools and RNGs only; no game is played).
    GameContext base(CharacterClass::IRONCLAD, 42, 20);
    base.act = 4; base.floorNum = 52; base.curHp = 61; base.gold = 140;
    for (const auto id : {CardId::INFLAME, CardId::SHRUG_IT_OFF, CardId::OFFERING, CardId::FEEL_NO_PAIN,
                          CardId::SEARING_BLOW, CardId::PARASITE, CardId::REGRET, CardId::ASCENDERS_BANE})
        addCard(base, Card(id));
    base.deck.upgrade(0); base.deck.upgrade(1); base.deck.upgrade(4); base.deck.upgrade(4);
    for (const auto r : {RelicId::PEN_NIB, RelicId::INCENSE_BURNER, RelicId::VAJRA, RelicId::POTION_BELT})
        if (base.obtainRelic(r)) throw std::logic_error("fixture relic opened a screen");
    base.relics.getRelicValueRef(RelicId::PEN_NIB) = 4;
    base.obtainPotion(Potion::FIRE_POTION);
    base.screenState = ScreenState::MAP_SCREEN;
    const auto before = fields(base);
    const auto countsBefore = deckCounts(base);
    // The public record (heart1-public-record-v2) the child's entry row carries.
    const auto record = [&](const GameContext &gc) {
        nlohmann::json r;
        std::string reason;
        check(heart1::buildPublicLeafRecord(gc, r, &reason), "fixture record: " + reason);
        return r;
    };
    const auto recordBefore = record(base);

    {
        auto copy = base;
        const auto row = applyA4Perturbation(copy, 7, 0);
        const auto after = fields(copy);
        check(row["op"] == "none" && after.deck == before.deck && after.relics == before.relics
              && after.rngs == before.rngs && after.pools == before.pools && after.potions == before.potions
              && after.curHp == before.curHp && after.maxHp == before.maxHp && after.gold == before.gold
              && after.other == before.other && after.relicBits == before.relicBits, "child 0 changed the state");
    }
    std::map<std::string, int> seen;
    for (int child = 1; child <= 600; ++child) {
        auto copy = base;
        const auto row = applyA4Perturbation(copy, 7, child);
        auto again = base;
        check(applyA4Perturbation(again, 7, child) == row, "not deterministic");
        const std::string op = row["op"];
        ++seen[op];
        const auto after = fields(copy);
        const std::string at = op + " child " + std::to_string(child);
        // Never a game Random, the screen or the position.
        check(after.rngs == before.rngs && after.other == before.other, at + " touched RNG or other state");
        const bool hp = after.curHp != before.curHp, maxHp = after.maxHp != before.maxHp,
                   gold = after.gold != before.gold, deck = after.deck != before.deck,
                   relics = after.relics != before.relics || after.relicBits != before.relicBits,
                   pools = after.pools != before.pools,
                   potions = after.potions != before.potions || after.potionCount != before.potionCount
                             || after.potionCapacity != before.potionCapacity;
        const bool deckCaches = after.typeCounts != before.typeCounts || after.upgradeable != before.upgradeable
                                || after.transformable != before.transformable || after.bottles != before.bottles;
        bool expected = false;
        if (op == "hp") expected = hp && !maxHp && !gold && !deck && !relics && !pools && !potions;
        else if (op == "max_hp") {
            const int gain = after.maxHp - before.maxHp;
            const int curHp = gain > 0 ? std::min(before.curHp + gain, after.maxHp) : std::min(before.curHp, after.maxHp);
            expected = maxHp && after.curHp == curHp && !gold && !deck && !relics && !pools && !potions;
        }
        else if (op == "gold") expected = gold && !hp && !maxHp && !deck && !relics && !pools && !potions;
        else if (op == "card_add" || op == "card_remove" || op == "upgrade" || op == "unupgrade")
            expected = deck && !hp && !maxHp && !gold && !relics && !pools && !potions;
        else if (op == "relic_add" || op == "relic_swap")
            expected = relics && !hp && !maxHp && !gold && !deck && !potions;   // pools: checked below
        else if (op == "relic_remove" || op == "relic_counter")
            expected = relics && !pools && !hp && !maxHp && !gold && !deck && !potions;
        else if (op == "potion_add" || op == "potion_remove")
            expected = potions && after.potionCapacity == before.potionCapacity
                       && !hp && !maxHp && !gold && !deck && !relics && !pools;
        check(expected, at + " changed another field: " + row.dump());
        check(deck || !deckCaches, at + " changed deck caches without the deck");
        // Caches still describe the cards and relics.
        const auto countsAfter = deckCounts(copy);
        for (int i = 0; i < 4; ++i)
            check(after.typeCounts[i] - before.typeCounts[i] == countsAfter[i] - countsBefore[i], at + " type counts");
        check(after.transformable - before.transformable == countsAfter[4] - countsBefore[4], at + " transformable");
        check(after.upgradeable - before.upgradeable == countsAfter[5] - countsBefore[5], at + " upgradeable");
        RelicContainer rebuilt;
        for (const auto &r : copy.relics.relics) rebuilt.add(r);
        check(rebuilt.relicBits0 == copy.relics.relicBits0 && rebuilt.relicBits1 == copy.relics.relicBits1
              && rebuilt.relicBits2 == copy.relics.relicBits2, at + " relic bits");
        int filled = 0;
        for (int i = 0; i < copy.potionCapacity; ++i) filled += copy.potions[i] != Potion::EMPTY_POTION_SLOT;
        check(filled == copy.potionCount, at + " potion count");
        if (op == "relic_add" || op == "relic_swap") {
            const auto r = RelicId(int(std::find(std::begin(relicEnumNames), std::end(relicEnumNames),
                                                 row["added"].get<std::string>()) - std::begin(relicEnumNames)));
            check(copy.relics.has(r) && !structuralRelic(r), at + " added relic");
            for (std::size_t i = 0; i < after.pools.size(); ++i) {
                auto expectedPool = before.pools[i];
                expectedPool.erase(std::remove(expectedPool.begin(), expectedPool.end(), r), expectedPool.end());
                check(after.pools[i] == expectedPool, at + " pools: only the added relic leaves them");
            }
        }
        // The public record changes exactly in the operator's keys (fixed_observation: 0 HP, 1 max HP, 2 gold).
        const auto recordAfter = record(copy);
        std::set<std::string> changed;
        for (const auto &[key, value] : recordAfter.items()) if (recordBefore.value(key, nlohmann::json()) != value) changed.insert(key);
        for (const auto &[key, value] : recordBefore.items()) if (!recordAfter.contains(key)) changed.insert(key);
        std::set<int> fixed;
        for (int i = 0; i < int(recordBefore["obs.fixed_observation"].size()); ++i)
            if (recordBefore["obs.fixed_observation"][i] != recordAfter["obs.fixed_observation"][i]) fixed.insert(i);
        const std::set<std::string> fixedKey = {"obs.fixed_observation"};
        std::set<std::string> wantKeys;
        std::set<int> wantFixed;
        if (op == "hp") { wantKeys = fixedKey; wantFixed = {0}; }
        else if (op == "max_hp") {
            wantKeys = fixedKey; wantFixed = {1};
            if (after.curHp != before.curHp) wantFixed.insert(0);
        } else if (op == "gold") { wantKeys = fixedKey; wantFixed = {2}; }
        else if (op == "card_add" || op == "card_remove" || op == "upgrade" || op == "unupgrade") {
            for (const auto &[key, value] : recordAfter.items()) if (key.rfind("obs.deck.", 0) == 0) wantKeys.insert(key);
            changed.erase("obs.deck.misc");   // equal unless the card carries misc
            wantKeys.erase("obs.deck.misc");
        } else if (op.rfind("relic_", 0) == 0) {
            wantKeys = {"obs.relics.relics", "obs.relics.relic_counters"};
            if (op == "relic_counter") wantKeys = {"obs.relics.relic_counters"};
        } else if (op.rfind("potion_", 0) == 0) wantKeys = {"obs.potions"};
        if (op == "upgrade" || op == "unupgrade") wantKeys = {"obs.deck.upgrades"};
        if (op == "relic_remove" || op == "relic_add" || op == "relic_swap") {
            // relic_counters always lists one entry per relic; its values change only with the relic list.
            if (!changed.count("obs.relics.relic_counters")) wantKeys.erase("obs.relics.relic_counters");
        }
        check(changed == wantKeys && fixed == wantFixed, at + " public record keys changed: " + nlohmann::json(changed).dump()
              + " fixed " + nlohmann::json(fixed).dump());
        if (op == "card_remove") check(row["card"]["id"] != "PARASITE" && row["card"]["id"] != "ASCENDERS_BANE"
                                       && copy.deck.size() == base.deck.size() - 1, at + " removed card");
        if (op == "relic_counter") check(row["before"] != row["after"], at + " counter unchanged");
    }
    for (const char *op : {"hp", "max_hp", "gold", "card_add", "card_remove", "upgrade", "unupgrade", "relic_add",
                           "relic_remove", "relic_swap", "relic_counter", "potion_add", "potion_remove"})
        check(seen[op] > 0, std::string("operator never drawn: ") + op);
    std::cout << "a4 perturb selftest passed\n";
    return 0;
}

}  // namespace one_combat
