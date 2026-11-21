// GameContext::rngFix (default off): the seeding of the RNG Fix mod (Steam workshop 2181005326, source
// github.com/Nickel-makes/RngFix at 88b5885), which the Amber Eye page names for training and evaluation. Off, a
// run is seeded as the vanilla game (every stream from the run seed); on, every stream has its own seed, raw
// output k of Random(seed). No gameplay is driven.
#include "combat/BattleContext.h"
#include "game/GameContext.h"

#include <array>
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seeds; no gameplay is driven.
static constexpr std::array<std::uint64_t, 3> SEEDS = {111200152ull, 1ull, 0x8000000000000000ull};

// The mod's `Random gen = new Random(Settings.seed); gen.random.nextLong()` chain, with the engine's generator.
static std::uint64_t chained(std::uint64_t seed, int index) {
    Random gen(seed);
    for (int i = 0; i < index; ++i) gen.nextLong();
    return gen.nextLong();
}

static std::pair<std::uint64_t, std::uint64_t> state(const Random &r) { return {r.seed0, r.seed1}; }

static constexpr std::uint64_t KNOWN_0 = 11025727135499881287ull, KNOWN_11 = 13133405872493276616ull,
                               KNOWN_14 = 17634792858663210023ull;

static void checkDerivedSeed() {
    for (const auto seed : SEEDS) {
        for (int k = 0; k < 16; ++k) {
            require(Random::derivedSeed(seed, k) == chained(seed, k), "derivedSeed must be raw output k");
            // The mod's `new Random(Settings.seed, k)` followed by one raw nextLong (Neow k = 13, event room k = 14).
            Random counted(seed, k);
            require(Random::derivedSeed(seed, k) == counted.nextLong(), "derivedSeed must match Random(seed, k)");
        }
    }
    // Known answers (frozen 2026-11-21; the same values from a separate Python transcription of libgdx RandomXS128)
    // so a change of the derivation cannot pass unnoticed.
    std::cout << "derivedSeed(111200152, 0 / 11 / 14) = " << Random::derivedSeed(111200152ull, 0) << " "
              << Random::derivedSeed(111200152ull, 11) << " " << Random::derivedSeed(111200152ull, 14) << '\n';
    require(Random::derivedSeed(111200152ull, 0) == KNOWN_0, "known answer k = 0");
    require(Random::derivedSeed(111200152ull, 11) == KNOWN_11, "known answer k = 11");
    require(Random::derivedSeed(111200152ull, 14) == KNOWN_14, "known answer k = 14");
}

static void checkOff(std::uint64_t seed) {
    const GameContext plain(CharacterClass::IRONCLAD, seed, 20);
    const GameContext off(CharacterClass::IRONCLAD, seed, 20, false);
    require(!plain.rngFix && !off.rngFix, "rngFix must default to off");
    // Neow's options are drawn in the constructor; every other stream is untouched.
    // The constructor draws from some streams (Neow's options, encounter lists, relic pools): replaying the same
    // number of draws from the run seed must give the same state.
    for (const GameContext *gc : {&plain, &off})
        for (const Random *r : {&gc->neowRng, &gc->treasureRng, &gc->eventRng, &gc->relicRng, &gc->potionRng,
                                &gc->cardRng, &gc->cardRandomRng, &gc->merchantRng, &gc->monsterRng, &gc->shuffleRng,
                                &gc->miscRng})
            require(*r == Random(seed, r->counter), "off: every stream is the run seed's");
    GameContext gc = off;
    gc.floorNum = 7;
    for (const auto stream : {GameContext::FLOOR_MONSTER_HP, GameContext::FLOOR_AI, GameContext::FLOOR_SHUFFLE,
                              GameContext::FLOOR_CARD_RANDOM, GameContext::FLOOR_MISC})
        require(gc.floorRng(stream) == Random(seed + 7), "off: per-floor streams are Random(seed + floorNum)");
    gc.reseedFloorRngs();
    require(gc.miscRng == Random(seed + 7) && gc.shuffleRng == Random(seed + 7)
            && gc.cardRandomRng == Random(seed + 7), "off: a new floor resets misc, shuffle and card-random alike");
    // A fight draws from its streams while it is set up; each must still be the shared Random(seed + floorNum).
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    for (const Random *r : {&bc.aiRng, &bc.monsterHpRng, &bc.shuffleRng, &bc.cardRandomRng})
        require(*r == Random(seed + 7, r->counter), "off: a fight's streams are Random(seed + floorNum)");
}

static void checkOn(std::uint64_t seed) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 20, true);
    require(gc.rngFix, "rngFix must be kept");
    const auto d = [&](int k) { return Random::derivedSeed(seed, k); };
    // Streams the constructor does not draw from keep their start state.
    require(gc.eventRng == Random(d(1)), "eventRng is output 1");
    require(gc.merchantRng == Random(d(2)), "merchantRng is output 2");
    require(gc.cardRng == Random(d(3)), "cardRng is output 3");
    require(gc.treasureRng == Random(d(4)), "treasureRng is output 4");
    require(gc.potionRng == Random(d(6)), "potionRng is output 6");
    require(gc.shuffleRng == Random(d(9)), "floor 0 shuffleRng is output 9");
    require(gc.cardRandomRng == Random(d(10)), "floor 0 cardRandomRng is output 10");
    require(gc.miscRng == Random(d(11)), "floor 0 miscRng is output 11");
    // monsterRng (encounter lists), relicRng (pool shuffles) and Neow's generator are drawn from in the constructor:
    // replay the same number of draws from the expected seed.
    require(gc.monsterRng.counter > 0 && gc.monsterRng == Random(d(0), gc.monsterRng.counter), "monsterRng is output 0");
    require(gc.relicRng.counter > 0 && gc.relicRng == Random(d(5), gc.relicRng.counter), "relicRng is output 5");
    require(gc.neowRng.counter > 0 && gc.neowRng == Random(d(13), gc.neowRng.counter), "Neow's generator is output 13");
    std::set<std::uint64_t> seeds;
    for (int k = 0; k < 15; ++k) seeds.insert(d(k));
    require(seeds.size() == 15 && !seeds.count(seed), "the derived seeds must differ from each other and the run seed");

    gc.floorNum = 7;
    std::set<std::pair<std::uint64_t, std::uint64_t>> distinct;
    for (const auto stream : {GameContext::FLOOR_MONSTER_HP, GameContext::FLOOR_AI, GameContext::FLOOR_SHUFFLE,
                              GameContext::FLOOR_CARD_RANDOM, GameContext::FLOOR_MISC}) {
        require(gc.floorRng(stream) == Random(d(stream) + 7), "per-floor stream is Random(output k + floorNum)");
        distinct.insert(state(gc.floorRng(stream)));
    }
    require(distinct.size() == 5, "the five per-floor streams must differ");
    gc.reseedFloorRngs();
    require(gc.miscRng == Random(d(11) + 7) && gc.shuffleRng == Random(d(9) + 7)
            && gc.cardRandomRng == Random(d(10) + 7), "a new floor resets misc, shuffle and card-random apart");
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    require(bc.monsterHpRng == Random(d(7) + 7, bc.monsterHpRng.counter), "a fight's monsterHpRng is output 7");
    require(bc.aiRng == Random(d(8) + 7, bc.aiRng.counter), "a fight's aiRng is output 8");
    require(bc.shuffleRng == Random(d(9) + 7, bc.shuffleRng.counter), "a fight's shuffleRng is output 9");
    require(bc.cardRandomRng == Random(d(10) + 7, bc.cardRandomRng.counter), "a fight's cardRandomRng is output 10");

    // A copy (the search works on copies) keeps the flag and so the seeding of later floors.
    GameContext copy = gc;
    copy.floorNum = 8;
    require(copy.rngFix && copy.floorRng(GameContext::FLOOR_AI) == Random(d(8) + 8), "copies keep rngFix");
}

int main() {
    try {
        checkDerivedSeed();
        for (const auto seed : SEEDS) {
            checkOff(seed);
            checkOn(seed);
        }
    } catch (const std::exception &e) {
        std::cerr << "rng_fix_test: " << e.what() << '\n';
        return 1;
    }
    std::cout << "rng_fix_test: ok\n";
    return 0;
}
