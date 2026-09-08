//
// BattleContextBinary.h: versioned binary (de)serialization of a
// BattleContext snapshots used by fight replay and simulator diagnostics.
//
// The format captures the VISIBLE state plus the 6 RNG streams so a leaf
// snapshot can be restored and re-searched at a higher budget later. It
// deliberately SKIPS the transient execution state — ActionQueue, CardQueue,
// curCardQueueItem, endTurnQueued, turnHasEnded, skipMonsterTurn,
// monsterTurnIdx, haveUsedDiscoveryAction, undefinedBehaviorEvoked,
// loopCount, energyWasted, cardsDrawn, miscBits — because the hooks only fire
// at player-decision states (PLAYER_NORMAL / CARD_SELECT) where those queues
// are empty and the flags are consumed/false. The round-trip correctness
// contract is combatExtractFeatures identity
// (combatExtractFeatures(bc) == combatExtractFeatures(deserialize(serialize(bc)))).
//
// Layout (all integers little-endian):
//   [8]  magic  "STSBC\0\0\0\0"
//   [4]  version (1)
//   [4]  total buffer size in bytes
//   then field groups, each:
//     [1] group id
//     [4] group payload size in bytes
//     [payload]
// Groups: 1=RNG, 2=Player, 3=Monsters, 4=Cards, 5=Potions, 6=Misc.
//
// The format is bound to the sts_lightspeed version that wrote it: any
// BattleContext layout change requires a version bump or re-collection.
// Serializer/deserializer are stateless (no globals, no static state).
//
#ifndef STS_LIGHTSPEED_BATTLECONTEXTBINARY_H
#define STS_LIGHTSPEED_BATTLECONTEXTBINARY_H

#include <cstdint>
#include <vector>
#include <map>

#include "combat/BattleContext.h"

namespace sts {

namespace detail_bc_bin {

inline void putU8(std::vector<std::uint8_t> &v, std::uint8_t x) { v.push_back(x); }
inline void putU16(std::vector<std::uint8_t> &v, std::uint16_t x) {
    v.push_back((std::uint8_t)(x & 0xFF));
    v.push_back((std::uint8_t)((x >> 8) & 0xFF));
}
inline void putU32(std::vector<std::uint8_t> &v, std::uint32_t x) {
    for (int i = 0; i < 4; ++i) v.push_back((std::uint8_t)((x >> (8 * i)) & 0xFF));
}
inline void putU64(std::vector<std::uint8_t> &v, std::uint64_t x) {
    for (int i = 0; i < 8; ++i) v.push_back((std::uint8_t)((x >> (8 * i)) & 0xFF));
}
inline void putI32(std::vector<std::uint8_t> &v, std::int32_t x) { putU32(v, (std::uint32_t)x); }
inline void putI16(std::vector<std::uint8_t> &v, std::int16_t x) { putU16(v, (std::uint16_t)x); }
inline void putI8(std::vector<std::uint8_t> &v, std::int8_t x) { putU8(v, (std::uint8_t)x); }
inline void putBool(std::vector<std::uint8_t> &v, bool b) { putU8(v, b ? 1 : 0); }

// Little-endian read cursor with bounds checking; returns false on overrun.
struct Reader {
    const std::uint8_t *p;
    std::size_t size;
    std::size_t pos = 0;

    Reader(const std::uint8_t *data, std::size_t n) : p(data), size(n) {}
    bool need(std::size_t n) { return pos + n <= size; }
    bool u8(std::uint8_t &out) { if (!need(1)) return false; out = p[pos++]; return true; }
    bool u16(std::uint16_t &out) {
        if (!need(2)) return false;
        out = (std::uint16_t)p[pos] | ((std::uint16_t)p[pos + 1] << 8);
        pos += 2; return true;
    }
    bool u32(std::uint32_t &out) {
        if (!need(4)) return false;
        out = 0;
        for (int i = 0; i < 4; ++i) out |= (std::uint32_t)p[pos + i] << (8 * i);
        pos += 4; return true;
    }
    bool u64(std::uint64_t &out) {
        if (!need(8)) return false;
        out = 0;
        for (int i = 0; i < 8; ++i) out |= (std::uint64_t)p[pos + i] << (8 * i);
        pos += 8; return true;
    }
    bool i32(std::int32_t &out) { std::uint32_t u; if (!u32(u)) return false; out = (std::int32_t)u; return true; }
    bool i16(std::int16_t &out) { std::uint16_t u; if (!u16(u)) return false; out = (std::int16_t)u; return true; }
    bool i8(std::int8_t &out) { std::uint8_t u; if (!u8(u)) return false; out = (std::int8_t)u; return true; }
    bool boolean(bool &out) { std::uint8_t u; if (!u8(u)) return false; out = u != 0; return true; }
};

inline void serializeCardInstance(std::vector<std::uint8_t> &v, const CardInstance &c) {
    putI32(v, (std::int32_t)c.id);
    putI16(v, c.uniqueId);
    putI16(v, c.specialData);
    putI8(v, c.cost);
    putI8(v, c.costForTurn);
    putBool(v, c.upgraded);
    putBool(v, c.freeToPlayOnce);
    putBool(v, c.retain);
}

inline bool deserializeCardInstance(Reader &r, CardInstance &c) {
    std::int32_t id; std::int16_t u, sd; std::int8_t cost, cft; bool up, free, ret;
    if (!r.i32(id) || !r.i16(u) || !r.i16(sd) || !r.i8(cost) || !r.i8(cft)
        || !r.boolean(up) || !r.boolean(free) || !r.boolean(ret))
        return false;
    c = CardInstance();
    c.id = (CardId)id;
    c.uniqueId = u;
    c.specialData = sd;
    c.cost = cost;
    c.costForTurn = cft;
    c.upgraded = up;
    c.freeToPlayOnce = free;
    c.retain = ret;
    return true;
}

} // namespace detail_bc_bin

// Serialize a BattleContext to a self-describing byte buffer. Stateless.
inline std::vector<std::uint8_t> serializeBattleContext(const BattleContext &bc) {
    using namespace detail_bc_bin;
    std::vector<std::uint8_t> out;
    // header: magic + version + total size (patched at the end)
    const char magic[8] = {'S', 'T', 'S', 'B', 'C', 0, 0, 0};
    out.insert(out.end(), magic, magic + 8);
    putU32(out, 1);                    // version
    const std::size_t sizePos = out.size();
    putU32(out, 0);                    // total size placeholder

    // group 1: RNG (6 streams: counter, seed0, seed1)
    {
        std::vector<std::uint8_t> g;
        const Random streams[] = {bc.aiRng, bc.cardRandomRng, bc.miscRng,
                                  bc.monsterHpRng, bc.potionRng, bc.shuffleRng};
        for (const auto &r : streams) {
            putI32(g, r.counter);
            putU64(g, r.seed0);
            putU64(g, r.seed1);
        }
        putU8(out, 1); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // group 2: Player
    {
        std::vector<std::uint8_t> g;
        const Player &p = bc.player;
        putI32(g, (std::int32_t)p.cc);
        putI16(g, p.gold);
        putI32(g, p.curHp);
        putI32(g, p.maxHp);
        putI32(g, p.energy);
        putI8(g, p.energyPerTurn);
        putI8(g, p.cardDrawPerTurn);
        putI8(g, (std::int8_t)p.stance);
        putI8(g, p.orbSlots);
        putI8(g, p.lastTargetedMonster);
        putI32(g, p.block);
        putI32(g, p.artifact);
        putI32(g, p.dexterity);
        putI32(g, p.focus);
        putI32(g, p.strength);
        putU32(g, p.justAppliedBits);
        putU64(g, p.statusBits0);
        putU32(g, p.statusBits1);
        putU32(g, (std::uint32_t)p.statusMap.size());
        for (const auto &kv : p.statusMap) {
            putI16(g, (std::int16_t)kv.first);
            putI16(g, kv.second);
        }
        putU64(g, p.relicBits0);
        putU64(g, p.relicBits1);
        putI8(g, p.happyFlowerCounter);
        putI8(g, p.incenseBurnerCounter);
        putI8(g, p.inkBottleCounter);
        putI8(g, p.inserterCounter);
        putI8(g, p.nunchakuCounter);
        putI8(g, p.penNibCounter);
        putI8(g, p.sundialCounter);
        putBool(g, p.haveUsedNecronomiconThisTurn);
        putI8(g, p.combustHpLoss);
        putI16(g, p.devaFormEnergyPerTurn);
        putI8(g, p.echoFormCardsDoubled);
        putI8(g, p.panacheCounter);
        putI16(g, p.cardsPlayedThisTurn);
        putI16(g, p.attacksPlayedThisTurn);
        putI16(g, p.skillsPlayedThisTurn);
        putU8(g, (std::uint8_t)p.orangePelletsCardTypesPlayed.to_ulong());
        putI16(g, p.cardsDiscardedThisTurn);
        putI16(g, p.lastAttackUnblockedDamage);
        putI16(g, p.timesDamagedThisCombat);
        putI8(g, p.bomb1);
        putI8(g, p.bomb2);
        putI8(g, p.bomb3);
        putU8(out, 2); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // group 3: Monsters
    {
        std::vector<std::uint8_t> g;
        const MonsterGroup &mg = bc.monsters;
        putI32(g, mg.monstersAlive);
        putI32(g, mg.monsterCount);
        putU8(g, (std::uint8_t)mg.extraRollMoveOnTurn.to_ulong());
        putU8(g, (std::uint8_t)mg.skipTurn.to_ulong());
        for (int i = 0; i < mg.monsterCount; ++i) {
            const Monster &m = mg.arr[i];
            putI32(g, m.idx);
            putI32(g, (std::int32_t)m.id);
            putI32(g, m.curHp);
            putI32(g, m.maxHp);
            putI32(g, m.block);
            putBool(g, m.isEscapingB);
            putBool(g, m.halfDead);
            putBool(g, m.escapeNext);
            putI32(g, (std::int32_t)m.moveHistory[0]);
            putI32(g, (std::int32_t)m.moveHistory[1]);
            putU64(g, m.statusBits);
            putI8(g, m.artifact);
            putI8(g, m.blockReturn);
            putI8(g, m.choked);
            putI8(g, m.corpseExplosion);
            putI8(g, m.lockOn);
            putI16(g, m.mark);
            putI8(g, m.metallicize);
            putI8(g, m.platedArmor);
            putI8(g, m.poison);
            putI8(g, m.regen);
            putI8(g, m.shackled);
            putI32(g, m.strength);
            putI32(g, m.vulnerable);
            putI32(g, m.weak);
            putI32(g, m.uniquePower0);
            putI16(g, m.uniquePower1);
            putI32(g, m.miscInfo);
        }
        putU8(out, 3); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // group 4: Cards
    {
        std::vector<std::uint8_t> g;
        const CardManager &c = bc.cards;
        putI32(g, c.nextUniqueCardId);
        putI32(g, c.cardsInHand);
        for (int i = 0; i < c.cardsInHand; ++i) serializeCardInstance(g, c.hand[i]);
        // limbo is transient (end-of-turn discard scratch); not serialized.
        for (const auto &sc : c.stasisCards) serializeCardInstance(g, sc);
        auto putPile = [&](const std::vector<CardInstance> &pile) {
            putI32(g, (std::int32_t)pile.size());
            for (const auto &ci : pile) serializeCardInstance(g, ci);
        };
        putPile(c.drawPile);
        putPile(c.discardPile);
        putPile(c.exhaustPile);
        putI32(g, c.handNormalityCount);
        putI32(g, c.handPainCount);
        putI32(g, c.strikeCount);
        putI32(g, c.handBloodCardCount);
        putI32(g, c.drawPileBloodCardCount);
        putI32(g, c.discardPileBloodCardCount);
        putU8(out, 4); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // group 5: Potions
    {
        std::vector<std::uint8_t> g;
        putI32(g, bc.potionCount);
        putI32(g, bc.potionCapacity);
        for (const auto &p : bc.potions) putI32(g, (std::int32_t)p);
        putU8(out, 5); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // group 6: Misc
    {
        std::vector<std::uint8_t> g;
        putI32(g, bc.ascension);
        putI32(g, (std::int32_t)bc.outcome);
        putI32(g, (std::int32_t)bc.inputState);
        const CardSelectInfo &csi = bc.cardSelectInfo;
        for (const auto &cid : csi.cards) putI32(g, (std::int32_t)cid);
        putBool(g, csi.canPickZero);
        putBool(g, csi.canPickAnyNumber);
        putI32(g, csi.pickCount);
        putI32(g, csi.data0);
        putI32(g, (std::int32_t)csi.cardSelectTask);
        putI32(g, bc.turn);
        putI32(g, bc.floorNum);
        putI32(g, (std::int32_t)bc.encounter);
        putU64(g, bc.seed);
        putU8(out, 6); putU32(out, (std::uint32_t)g.size());
        out.insert(out.end(), g.begin(), g.end());
    }

    // patch total size (the placeholder is already counted in out.size())
    const std::uint32_t totalSize = (std::uint32_t)out.size();
    out[sizePos + 0] = (std::uint8_t)(totalSize & 0xFF);
    out[sizePos + 1] = (std::uint8_t)((totalSize >> 8) & 0xFF);
    out[sizePos + 2] = (std::uint8_t)((totalSize >> 16) & 0xFF);
    out[sizePos + 3] = (std::uint8_t)((totalSize >> 24) & 0xFF);
    return out;
}

// Deserialize a BattleContext from a buffer produced by serializeBattleContext.
// Transient execution state is left at its default (ActionQueue/CardQueue
// empty, endTurnQueued/turnHasEnded/skipMonsterTurn false, monsterTurnIdx 6,
// miscBits clear). Returns a default-constructed BattleContext on malformed
// input.
inline BattleContext deserializeBattleContext(const std::uint8_t *data, std::size_t size) {
    using namespace detail_bc_bin;
    BattleContext bc;
    Reader r(data, size);
    if (size < 16) return bc;
    if (data[0] != 'S' || data[1] != 'T' || data[2] != 'S' || data[3] != 'B'
        || data[4] != 'C' || data[5] != 0 || data[6] != 0 || data[7] != 0)
        return bc;
    r.pos = 8;
    std::uint32_t version = 0;
    if (!r.u32(version) || version != 1) return bc;
    std::uint32_t total = 0;
    if (!r.u32(total) || (std::size_t)total != size) return bc;

    bool ok = true;
    while (ok && r.pos < r.size) {
        std::uint8_t gid = 0;
        std::uint32_t gsize = 0;
        if (!r.u8(gid) || !r.u32(gsize)) { ok = false; break; }
        const std::size_t gend = r.pos + gsize;
        if (gend > r.size) { ok = false; break; }

        switch (gid) {
            case 1: {   // RNG
                Random streams[6];
                for (auto &s : streams) {
                    std::int32_t counter; std::uint64_t s0, s1;
                    if (!r.i32(counter) || !r.u64(s0) || !r.u64(s1)) { ok = false; break; }
                    s.counter = counter; s.seed0 = s0; s.seed1 = s1;
                }
                if (ok) {
                    bc.aiRng = streams[0];
                    bc.cardRandomRng = streams[1];
                    bc.miscRng = streams[2];
                    bc.monsterHpRng = streams[3];
                    bc.potionRng = streams[4];
                    bc.shuffleRng = streams[5];
                }
                break;
            }
            case 2: {   // Player
                Player &p = bc.player;
                std::int32_t cc; std::int16_t gold; std::int32_t curHp, maxHp, energy;
                std::int8_t ept, cdt, stance, orb, ltm;
                std::int32_t block, artifact, dext, focus, strength;
                std::uint32_t jab; std::uint64_t sb0; std::uint32_t sb1;
                std::uint32_t smSize;
                std::uint64_t rb0, rb1;
                std::int8_t hfc, ibc, ikb, insc, nunc, pnb, sdc, chl, efd, panc;
                bool necro;
                std::int16_t deva, cpt, apt, spt, cdt16, lau, tdc;
                std::uint8_t opp;
                std::int8_t b1, b2, b3;
                if (!r.i32(cc) || !r.i16(gold) || !r.i32(curHp) || !r.i32(maxHp)
                    || !r.i32(energy) || !r.i8(ept) || !r.i8(cdt) || !r.i8(stance)
                    || !r.i8(orb) || !r.i8(ltm) || !r.i32(block) || !r.i32(artifact)
                    || !r.i32(dext) || !r.i32(focus) || !r.i32(strength) || !r.u32(jab)
                    || !r.u64(sb0) || !r.u32(sb1) || !r.u32(smSize)) { ok = false; break; }
                std::map<PlayerStatus, std::int16_t> statusMap;
                for (std::uint32_t i = 0; i < smSize; ++i) {
                    std::int16_t key, val;
                    if (!r.i16(key) || !r.i16(val)) { ok = false; break; }
                    statusMap[(PlayerStatus)key] = val;
                }
                if (!ok) break;
                if (!r.u64(rb0) || !r.u64(rb1) || !r.i8(hfc) || !r.i8(ibc) || !r.i8(ikb)
                    || !r.i8(insc) || !r.i8(nunc) || !r.i8(pnb) || !r.i8(sdc)
                    || !r.boolean(necro) || !r.i8(chl) || !r.i16(deva) || !r.i8(efd)
                    || !r.i8(panc) || !r.i16(cpt) || !r.i16(apt) || !r.i16(spt)
                    || !r.u8(opp) || !r.i16(cdt16) || !r.i16(lau) || !r.i16(tdc)
                    || !r.i8(b1) || !r.i8(b2) || !r.i8(b3)) { ok = false; break; }
                p.cc = (CharacterClass)cc;
                p.gold = gold;
                p.curHp = curHp; p.maxHp = maxHp; p.energy = energy;
                p.energyPerTurn = ept; p.cardDrawPerTurn = cdt;
                p.stance = (Stance)stance; p.orbSlots = orb; p.lastTargetedMonster = ltm;
                p.block = block; p.artifact = artifact; p.dexterity = dext;
                p.focus = focus; p.strength = strength;
                p.justAppliedBits = jab; p.statusBits0 = sb0; p.statusBits1 = sb1;
                p.statusMap = std::move(statusMap);
                p.relicBits0 = rb0; p.relicBits1 = rb1;
                p.happyFlowerCounter = hfc; p.incenseBurnerCounter = ibc;
                p.inkBottleCounter = ikb; p.inserterCounter = insc;
                p.nunchakuCounter = nunc; p.penNibCounter = pnb; p.sundialCounter = sdc;
                p.haveUsedNecronomiconThisTurn = necro;
                p.combustHpLoss = chl; p.devaFormEnergyPerTurn = deva;
                p.echoFormCardsDoubled = efd; p.panacheCounter = panc;
                p.cardsPlayedThisTurn = cpt; p.attacksPlayedThisTurn = apt;
                p.skillsPlayedThisTurn = spt;
                p.orangePelletsCardTypesPlayed = std::bitset<3>(opp);
                p.cardsDiscardedThisTurn = cdt16;
                p.lastAttackUnblockedDamage = lau; p.timesDamagedThisCombat = tdc;
                p.bomb1 = b1; p.bomb2 = b2; p.bomb3 = b3;
                break;
            }
            case 3: {   // Monsters
                std::int32_t alive, count;
                std::uint8_t er, st;
                if (!r.i32(alive) || !r.i32(count) || !r.u8(er) || !r.u8(st)
                    || count < 0 || count > 5) { ok = false; break; }
                bc.monsters.monstersAlive = alive;
                bc.monsters.monsterCount = count;
                bc.monsters.extraRollMoveOnTurn = std::bitset<5>(er);
                bc.monsters.skipTurn = std::bitset<5>(st);
                for (int i = 0; i < count; ++i) {
                    Monster &m = bc.monsters.arr[i];
                    std::int32_t idx, id, curHp, maxHp, block, mh0, mh1;
                    bool esc, hd, en;
                    std::uint64_t sbits;
                    std::int8_t art, br, ch, ce, lo, met, pa, poi, reg, sha;
                    std::int16_t mark, up1;
                    std::int32_t str, vul, wk, up0, misc;
                    if (!r.i32(idx) || !r.i32(id) || !r.i32(curHp) || !r.i32(maxHp)
                        || !r.i32(block) || !r.boolean(esc) || !r.boolean(hd)
                        || !r.boolean(en) || !r.i32(mh0) || !r.i32(mh1) || !r.u64(sbits)
                        || !r.i8(art) || !r.i8(br) || !r.i8(ch) || !r.i8(ce) || !r.i8(lo)
                        || !r.i16(mark) || !r.i8(met) || !r.i8(pa) || !r.i8(poi)
                        || !r.i8(reg) || !r.i8(sha) || !r.i32(str) || !r.i32(vul)
                        || !r.i32(wk) || !r.i32(up0) || !r.i16(up1) || !r.i32(misc)) {
                        ok = false; break;
                    }
                    m.idx = idx;
                    m.id = (MonsterId)id;
                    m.curHp = curHp; m.maxHp = maxHp; m.block = block;
                    m.isEscapingB = esc; m.halfDead = hd; m.escapeNext = en;
                    m.moveHistory[0] = (MMID)mh0; m.moveHistory[1] = (MMID)mh1;
                    m.statusBits = sbits;
                    m.artifact = art; m.blockReturn = br; m.choked = ch;
                    m.corpseExplosion = ce; m.lockOn = lo; m.mark = mark;
                    m.metallicize = met; m.platedArmor = pa; m.poison = poi;
                    m.regen = reg; m.shackled = sha;
                    m.strength = str; m.vulnerable = vul; m.weak = wk;
                    m.uniquePower0 = up0; m.uniquePower1 = up1;
                    m.miscInfo = misc;
                }
                break;
            }
            case 4: {   // Cards
                std::int32_t nextId, inHand;
                if (!r.i32(nextId) || !r.i32(inHand) || inHand < 0 || inHand > 10) {
                    ok = false; break;
                }
                bc.cards.nextUniqueCardId = nextId;
                bc.cards.cardsInHand = inHand;
                for (int i = 0; i < inHand; ++i) {
                    if (!deserializeCardInstance(r, bc.cards.hand[i])) { ok = false; break; }
                }
                if (!ok) break;
                for (auto &sc : bc.cards.stasisCards) {
                    if (!deserializeCardInstance(r, sc)) { ok = false; break; }
                }
                if (!ok) break;
                auto readPile = [&](std::vector<CardInstance> &pile) -> bool {
                    std::int32_t n;
                    if (!r.i32(n) || n < 0 || n > 128) return false;
                    pile.clear();
                    pile.reserve((std::size_t)n);
                    for (int i = 0; i < n; ++i) {
                        CardInstance ci;
                        if (!deserializeCardInstance(r, ci)) return false;
                        pile.push_back(ci);
                    }
                    return true;
                };
                if (!readPile(bc.cards.drawPile) || !readPile(bc.cards.discardPile)
                    || !readPile(bc.cards.exhaustPile)) { ok = false; break; }
                std::int32_t hnc, hpc, sc, hbc, dpbc, dsbc;
                if (!r.i32(hnc) || !r.i32(hpc) || !r.i32(sc) || !r.i32(hbc)
                    || !r.i32(dpbc) || !r.i32(dsbc)) { ok = false; break; }
                bc.cards.handNormalityCount = hnc;
                bc.cards.handPainCount = hpc;
                bc.cards.strikeCount = sc;
                bc.cards.handBloodCardCount = hbc;
                bc.cards.drawPileBloodCardCount = dpbc;
                bc.cards.discardPileBloodCardCount = dsbc;
                break;
            }
            case 5: {   // Potions
                std::int32_t count, cap;
                if (!r.i32(count) || !r.i32(cap)) { ok = false; break; }
                bc.potionCount = count; bc.potionCapacity = cap;
                for (auto &p : bc.potions) {
                    std::int32_t pid;
                    if (!r.i32(pid)) { ok = false; break; }
                    p = (Potion)pid;
                }
                break;
            }
            case 6: {   // Misc
                std::int32_t asc, outcome, inputState, c0, c1, c2, pick, data0, task;
                bool cpz, can;
                std::int32_t turn, floor, encounter;
                std::uint64_t seed;
                if (!r.i32(asc) || !r.i32(outcome) || !r.i32(inputState)
                    || !r.i32(c0) || !r.i32(c1) || !r.i32(c2)
                    || !r.boolean(cpz) || !r.boolean(can) || !r.i32(pick) || !r.i32(data0)
                    || !r.i32(task) || !r.i32(turn) || !r.i32(floor) || !r.i32(encounter)
                    || !r.u64(seed)) { ok = false; break; }
                bc.ascension = asc;
                bc.outcome = (Outcome)outcome;
                bc.inputState = (InputState)inputState;
                bc.cardSelectInfo.cards = { (CardId)c0, (CardId)c1, (CardId)c2 };
                bc.cardSelectInfo.canPickZero = cpz;
                bc.cardSelectInfo.canPickAnyNumber = can;
                bc.cardSelectInfo.pickCount = pick;
                bc.cardSelectInfo.data0 = data0;
                bc.cardSelectInfo.cardSelectTask = (CardSelectTask)task;
                bc.turn = turn;
                bc.floorNum = floor;
                bc.encounter = (MonsterEncounter)encounter;
                bc.seed = seed;
                break;
            }
            default:
                ok = false;   // unknown group id -> corrupt
                break;
        }
        r.pos = gend;
    }
    if (!ok) return BattleContext();
    return bc;
}

} // namespace sts

#endif // STS_LIGHTSPEED_BATTLECONTEXTBINARY_H
