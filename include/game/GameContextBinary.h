// GameContext snapshot for handing a game state from one executable of the same build to another (2026-11-27:
// one_combat expertfights writes the copy starts of Baalorlord's fights, az_bench_native plays them with the Amber
// net). Not a stable save format: the image is the struct's own bytes, so writer and reader must be built from the
// same source with the same compiler (checked by the header's size / offset fingerprint, which catches most
// layout differences, not all). The non-trivial members (the event and relic-pool vectors, the relic list, the
// map) are written separately. regainControlAction (a closure) is not: the snapshot keeps only whether one was
// pending, and the reader installs a stand-in that returns to the map. Use snapshots only where the game replaces
// it before it runs, as at the start of a monster / elite / boss fight (afterBattle sets its own).
#ifndef STS_GAME_CONTEXT_BINARY_H
#define STS_GAME_CONTEXT_BINARY_H

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <new>
#include <stdexcept>
#include <type_traits>
#include <vector>

#include "game/GameContext.h"
#include "game/Map.h"

namespace sts {

namespace gcbin {

constexpr std::uint32_t kMagic = 0x31434753u;   // "SGC1"

inline std::uint64_t fingerprint() {
    std::uint64_t h = 1469598103934665603ull;
    auto mixIn = [&](std::uint64_t x) { h = (h ^ x) * 1099511628211ull; };
    mixIn(sizeof(GameContext));
    mixIn(alignof(GameContext));
    mixIn(offsetof(GameContext, seed));
    mixIn(offsetof(GameContext, eventList));
    mixIn(offsetof(GameContext, colorlessCardPool));
    mixIn(offsetof(GameContext, info));
    mixIn(offsetof(GameContext, map));
    mixIn(offsetof(GameContext, curHp));
    mixIn(offsetof(GameContext, relics));
    mixIn(offsetof(GameContext, deck));
    mixIn(offsetof(GameContext, regainControlAction));
    mixIn(offsetof(GameContext, rngFix));
    mixIn(sizeof(Map));
    mixIn(sizeof(Deck));
    mixIn(sizeof(ScreenStateInfo));
    return h;
}

template <class T> void putRaw(std::vector<std::uint8_t> &out, const T &x) {
    const auto *p = reinterpret_cast<const std::uint8_t *>(&x);
    out.insert(out.end(), p, p + sizeof(T));
}

template <class T> void putVec(std::vector<std::uint8_t> &out, const std::vector<T> &v) {
    putRaw(out, static_cast<std::uint32_t>(v.size()));
    const auto *p = reinterpret_cast<const std::uint8_t *>(v.data());
    out.insert(out.end(), p, p + v.size() * sizeof(T));
}

struct Reader {
    const std::uint8_t *p, *end;
    void need(std::size_t n) const {
        if (static_cast<std::size_t>(end - p) < n) throw std::runtime_error("GameContext snapshot: truncated");
    }
    template <class T> T raw() {
        need(sizeof(T));
        T x;
        std::memcpy(&x, p, sizeof(T));
        p += sizeof(T);
        return x;
    }
    template <class T> std::vector<T> vec() {
        const auto n = raw<std::uint32_t>();
        need(static_cast<std::size_t>(n) * sizeof(T));
        std::vector<T> v(n);
        std::memcpy(v.data(), p, static_cast<std::size_t>(n) * sizeof(T));
        p += static_cast<std::size_t>(n) * sizeof(T);
        return v;
    }
};

}  // namespace gcbin

inline std::vector<std::uint8_t> serializeGameContext(const GameContext &gc) {
    // The image: a copy whose non-trivial members are empty (their bytes are then null pointers / zero).
    GameContext tmp = gc;
    auto release = [](auto &v) { std::remove_reference_t<decltype(v)>().swap(v); };   // no buffer (null pointers)
    release(tmp.eventList);
    release(tmp.shrineList);
    release(tmp.specialOneTimeEventList);
    release(tmp.commonRelicPool);
    release(tmp.uncommonRelicPool);
    release(tmp.rareRelicPool);
    release(tmp.shopRelicPool);
    release(tmp.bossRelicPool);
    release(tmp.relics.relics);
    tmp.map = nullptr;
    tmp.regainControlAction = nullptr;
    std::vector<std::uint8_t> out;
    out.reserve(sizeof(GameContext) + sizeof(Map) + 1024);
    gcbin::putRaw(out, gcbin::kMagic);
    gcbin::putRaw(out, gcbin::fingerprint());
    const auto *img = reinterpret_cast<const std::uint8_t *>(&tmp);
    out.insert(out.end(), img, img + sizeof(GameContext));
    gcbin::putVec(out, gc.eventList);
    gcbin::putVec(out, gc.shrineList);
    gcbin::putVec(out, gc.specialOneTimeEventList);
    gcbin::putVec(out, gc.commonRelicPool);
    gcbin::putVec(out, gc.uncommonRelicPool);
    gcbin::putVec(out, gc.rareRelicPool);
    gcbin::putVec(out, gc.shopRelicPool);
    gcbin::putVec(out, gc.bossRelicPool);
    gcbin::putVec(out, gc.relics.relics);
    gcbin::putRaw(out, static_cast<std::uint8_t>(gc.map ? 1 : 0));
    if (gc.map) gcbin::putRaw(out, *gc.map);
    gcbin::putRaw(out, static_cast<std::uint8_t>(gc.regainControlAction ? 1 : 0));
    return out;
}

// Reads one snapshot from [data, data + size); *used (if given) gets the bytes it took.
inline GameContext deserializeGameContext(const std::uint8_t *data, std::size_t size, std::size_t *used = nullptr) {
    gcbin::Reader r{data, data + size};
    if (r.raw<std::uint32_t>() != gcbin::kMagic) throw std::runtime_error("GameContext snapshot: bad magic");
    if (r.raw<std::uint64_t>() != gcbin::fingerprint())
        throw std::runtime_error("GameContext snapshot: layout fingerprint differs (another build wrote it)");
    r.need(sizeof(GameContext));
    // The image's non-trivial members are empty (null pointers), so a copy of it is well formed.
    alignas(GameContext) unsigned char buf[sizeof(GameContext)];
    std::memcpy(buf, r.p, sizeof(GameContext));
    r.p += sizeof(GameContext);
    GameContext gc = *std::launder(reinterpret_cast<const GameContext *>(buf));
    gc.eventList = r.vec<Event>();
    gc.shrineList = r.vec<Event>();
    gc.specialOneTimeEventList = r.vec<Event>();
    gc.commonRelicPool = r.vec<RelicId>();
    gc.uncommonRelicPool = r.vec<RelicId>();
    gc.rareRelicPool = r.vec<RelicId>();
    gc.shopRelicPool = r.vec<RelicId>();
    gc.bossRelicPool = r.vec<RelicId>();
    gc.relics.relics = r.vec<RelicInstance>();
    if (r.raw<std::uint8_t>()) gc.map = std::make_shared<Map>(r.raw<Map>());
    if (r.raw<std::uint8_t>()) gc.regainControlAction = [](GameContext &g) { g.screenState = ScreenState::MAP_SCREEN; };
    if (used) *used = static_cast<std::size_t>(r.p - data);
    return gc;
}

}  // namespace sts

#endif  // STS_GAME_CONTEXT_BINARY_H
