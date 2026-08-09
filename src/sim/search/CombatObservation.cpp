//
// CombatObservation.cpp: implementation
//
#include "sim/search/CombatObservation.h"
#include "combat/BattleContext.h"
#include "game/Random.h"

#include <cstring>
#include <algorithm>
#include <set>

namespace sts {

// ---- MonsterVisibleState ---------------------------------------------------
void MonsterVisibleState::fromMonster(const Monster &m, const BattleContext &bc) {
    id = m.id;
    curHp = m.curHp;
    maxHp = m.maxHp;
    block = m.block;
    strength = m.strength;
    vulnerable = m.vulnerable;
    weak = m.weak;
    poison = m.poison;
    artifact = m.artifact;
    isAttacking = m.isAttacking();
    isTargetable = m.isTargetable();
    lastMove = m.moveHistory[0] != MMID::INVALID ? m.moveHistory[0] : m.moveHistory[1];
    if (isAttacking) {
        const auto di = m.getMoveBaseDamage(bc);
        incomingDamage = m.calculateDamageToPlayer(bc, di.damage) * di.attackCount;
        incomingHits = di.attackCount;
    }
}

// ---- PlayerVisibleState ----------------------------------------------------
void PlayerVisibleState::fromPlayer(const Player &p) {
    curHp = p.curHp;
    maxHp = p.maxHp;
    block = p.block;
    energy = p.energy;
    strength = p.strength;
    dexterity = p.dexterity;
    focus = p.focus;
    artifact = p.artifact;
    stance = p.stance;
    gold = p.gold;
    cardsPlayedThisTurn = p.cardsPlayedThisTurn;
    attacksPlayedThisTurn = p.attacksPlayedThisTurn;
    skillsPlayedThisTurn = p.skillsPlayedThisTurn;
    relicCounters[0] = p.happyFlowerCounter;
    relicCounters[1] = p.incenseBurnerCounter;
    relicCounters[2] = p.inkBottleCounter;
    relicCounters[3] = p.inserterCounter;
    relicCounters[4] = p.nunchakuCounter;
    relicCounters[5] = p.penNibCounter;
    relicCounters[6] = p.sundialCounter;
    relicCounters[7] = p.panacheCounter;
    powers.clear();
    for (const auto &kv : p.statusMap)
        if (kv.second > 0) powers.emplace_back(kv.first, kv.second);
}

// ---- CombatObservation -----------------------------------------------------
static inline void hashMix(std::uint64_t &h, std::uint64_t x) {
    h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
}

// Canonical card identity shared by operator== and visibleHash: the fields
// that decide how a card plays this turn (mirrors enumerateActionsForNode's
// hand dedup key: id, upgrades, costForTurn, freeToPlayOnce, specialData).
struct CardKey {
    CardId id;
    std::int16_t specialData;
    std::int8_t costForTurn;
    bool upgraded;
    bool freeToPlayOnce;

    bool operator==(const CardKey &o) const {
        return id == o.id && specialData == o.specialData
            && costForTurn == o.costForTurn && upgraded == o.upgraded
            && freeToPlayOnce == o.freeToPlayOnce;
    }
    bool operator<(const CardKey &o) const {
        if (id != o.id) return id < o.id;
        if (specialData != o.specialData) return specialData < o.specialData;
        if (costForTurn != o.costForTurn) return costForTurn < o.costForTurn;
        if (upgraded != o.upgraded) return upgraded < o.upgraded;
        return freeToPlayOnce < o.freeToPlayOnce;
    }
};

static CardKey cardKeyOf(const CardInstance &c) {
    return {c.getId(), c.specialData, c.costForTurn, c.isUpgraded(), c.freeToPlayOnce};
}

static std::uint64_t cardIdentityHash(const CardInstance &c) {
    const CardKey k = cardKeyOf(c);
    std::uint64_t h = static_cast<std::uint64_t>(k.id) * 6364136223846793005ULL;
    h += static_cast<std::uint64_t>(k.specialData) * 2654435761ULL;
    h += static_cast<std::uint64_t>(k.costForTurn) * 40503ULL;
    h += (k.upgraded ? 1ULL : 0ULL) * 0x9e3779b97f4a7c15ULL;
    h += (k.freeToPlayOnce ? 1ULL : 0ULL) * 15461ULL;
    return h;
}

// Piles compare as multisets: the player knows hand/pile contents, not order.
static bool sameCardMultiset(const std::vector<CardInstance> &a,
                             const std::vector<CardInstance> &b) {
    if (a.size() != b.size()) return false;
    std::vector<CardKey> ka, kb;
    ka.reserve(a.size()); kb.reserve(b.size());
    for (const auto &c : a) ka.push_back(cardKeyOf(c));
    for (const auto &c : b) kb.push_back(cardKeyOf(c));
    std::sort(ka.begin(), ka.end());
    std::sort(kb.begin(), kb.end());
    return ka == kb;
}

std::uint64_t CombatObservation::visibleHash() const {
    std::uint64_t h = 0x9e3779b97f4a7c15ULL;
    hashMix(h, static_cast<std::uint64_t>(turn));
    hashMix(h, static_cast<std::uint64_t>(ascension));
    hashMix(h, static_cast<std::uint64_t>(encounter));
    hashMix(h, static_cast<std::uint64_t>(potionCapacity));
    hashMix(h, isCardPlayAllowed ? 1ULL : 0ULL);
    hashMix(h, static_cast<std::uint64_t>(inputState));
    hashMix(h, static_cast<std::uint64_t>(cardSelectTask));
    hashMix(h, static_cast<std::uint64_t>(pickCount));
    hashMix(h, canPickZero ? 1ULL : 0ULL);
    hashMix(h, canPickAnyNumber ? 1ULL : 0ULL);
    for (auto c : cardSelectOffers)
        hashMix(h, static_cast<std::uint64_t>(c));

    hashMix(h, static_cast<std::uint64_t>(player.curHp));
    hashMix(h, static_cast<std::uint64_t>(player.maxHp));
    hashMix(h, static_cast<std::uint64_t>(player.block));
    hashMix(h, static_cast<std::uint64_t>(player.energy));
    hashMix(h, static_cast<std::uint64_t>(player.strength));
    hashMix(h, static_cast<std::uint64_t>(player.dexterity));
    hashMix(h, static_cast<std::uint64_t>(player.focus));
    hashMix(h, static_cast<std::uint64_t>(player.artifact));
    hashMix(h, static_cast<std::uint64_t>(player.stance));
    hashMix(h, static_cast<std::uint64_t>(player.gold));
    hashMix(h, static_cast<std::uint64_t>(player.cardsPlayedThisTurn));
    hashMix(h, static_cast<std::uint64_t>(player.attacksPlayedThisTurn));
    hashMix(h, static_cast<std::uint64_t>(player.skillsPlayedThisTurn));
    for (auto v : player.relicCounters)
        hashMix(h, static_cast<std::uint64_t>(v));
    for (const auto &pw : player.powers) {
        hashMix(h, static_cast<std::uint64_t>(pw.first));
        hashMix(h, static_cast<std::uint64_t>(pw.second));
    }

    for (const auto &m : monsters) {
        hashMix(h, static_cast<std::uint64_t>(m.id));
        hashMix(h, static_cast<std::uint64_t>(m.curHp));
        hashMix(h, static_cast<std::uint64_t>(m.maxHp));
        hashMix(h, static_cast<std::uint64_t>(m.block));
        hashMix(h, static_cast<std::uint64_t>(m.strength));
        hashMix(h, static_cast<std::uint64_t>(m.vulnerable));
        hashMix(h, static_cast<std::uint64_t>(m.weak));
        hashMix(h, static_cast<std::uint64_t>(m.poison));
        hashMix(h, static_cast<std::uint64_t>(m.artifact));
        hashMix(h, static_cast<std::uint64_t>(m.incomingDamage));
        hashMix(h, static_cast<std::uint64_t>(m.incomingHits));
        hashMix(h, static_cast<std::uint64_t>(m.lastMove));
        hashMix(h, m.isAttacking ? 1ULL : 0ULL);
        hashMix(h, m.isTargetable ? 1ULL : 0ULL);
    }

    // Hand and piles: commutative multiset of card identity
    std::uint64_t acc = 0;
    for (const auto &c : hand) acc += cardIdentityHash(c);
    hashMix(h, acc);
    acc = 0;
    for (const auto &c : drawPileContents) acc += cardIdentityHash(c);
    hashMix(h, acc);
    acc = 0;
    for (const auto &c : discardPile) acc += cardIdentityHash(c);
    hashMix(h, acc);
    acc = 0;
    for (const auto &c : exhaustPile) acc += cardIdentityHash(c);
    hashMix(h, acc);

    for (const auto &p : potions)
        hashMix(h, static_cast<std::uint64_t>(static_cast<int>(p)));

    // 128-bit relics: hash via per-bit accumulator
    for (int r = 0; r < 128; ++r)
        if (relics.test(r)) hashMix(h, static_cast<std::uint64_t>(r) * 6364136223846793005ULL);

    return h ? h : 1;
}

bool CombatObservation::operator==(const CombatObservation &o) const {
    if (turn != o.turn || ascension != o.ascension || encounter != o.encounter
        || potionCapacity != o.potionCapacity
        || isCardPlayAllowed != o.isCardPlayAllowed)
        return false;
    if (inputState != o.inputState || cardSelectTask != o.cardSelectTask
        || pickCount != o.pickCount || canPickZero != o.canPickZero
        || canPickAnyNumber != o.canPickAnyNumber
        || cardSelectOffers != o.cardSelectOffers)
        return false;
    if (player.curHp != o.player.curHp || player.maxHp != o.player.maxHp
        || player.block != o.player.block || player.energy != o.player.energy
        || player.strength != o.player.strength || player.dexterity != o.player.dexterity
        || player.focus != o.player.focus || player.artifact != o.player.artifact
        || player.stance != o.player.stance || player.gold != o.player.gold)
        return false;
    if (player.cardsPlayedThisTurn != o.player.cardsPlayedThisTurn
        || player.attacksPlayedThisTurn != o.player.attacksPlayedThisTurn
        || player.skillsPlayedThisTurn != o.player.skillsPlayedThisTurn)
        return false;
    if (player.relicCounters != o.player.relicCounters
        || player.powers != o.player.powers)
        return false;
    if (monsters.size() != o.monsters.size()) return false;
    for (size_t i = 0; i < monsters.size(); ++i) {
        const auto &a = monsters[i], &b = o.monsters[i];
        if (a.id != b.id || a.curHp != b.curHp || a.maxHp != b.maxHp
            || a.block != b.block || a.strength != b.strength
            || a.vulnerable != b.vulnerable || a.weak != b.weak
            || a.poison != b.poison || a.artifact != b.artifact
            || a.incomingDamage != b.incomingDamage || a.incomingHits != b.incomingHits
            || a.lastMove != b.lastMove || a.isAttacking != b.isAttacking
            || a.isTargetable != b.isTargetable)
            return false;
    }
    if (!sameCardMultiset(hand, o.hand)) return false;
    if (!sameCardMultiset(drawPileContents, o.drawPileContents)) return false;
    if (!sameCardMultiset(discardPile, o.discardPile)) return false;
    if (!sameCardMultiset(exhaustPile, o.exhaustPile)) return false;
    if (potions.size() != o.potions.size()) return false;
    for (size_t i = 0; i < potions.size(); ++i)
        if (potions[i] != o.potions[i]) return false;
    if (relics != o.relics) return false;
    return true;
}

CombatObservation CombatObservation::fromBattleContext(const BattleContext &bc) {
    CombatObservation obs;
    obs.turn = bc.turn;
    obs.ascension = bc.ascension;
    obs.encounter = bc.encounter;
    obs.potionCapacity = bc.potionCapacity;
    obs.isCardPlayAllowed = bc.isCardPlayAllowed();
    obs.inputState = bc.inputState;
    obs.cardSelectTask = bc.cardSelectInfo.cardSelectTask;
    obs.pickCount = bc.cardSelectInfo.pickCount;
    obs.canPickZero = bc.cardSelectInfo.canPickZero;
    obs.canPickAnyNumber = bc.cardSelectInfo.canPickAnyNumber;
    obs.cardSelectOffers = bc.cardSelectInfo.cards;

    obs.player.fromPlayer(bc.player);

    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        MonsterVisibleState mvs;
        mvs.fromMonster(bc.monsters.arr[i], bc);
        obs.monsters.push_back(mvs);
    }

    for (int i = 0; i < bc.cards.cardsInHand; ++i)
        obs.hand.push_back(bc.cards.hand[i]);
    for (const auto &c : bc.cards.drawPile)
        obs.drawPileContents.push_back(c);
    for (const auto &c : bc.cards.discardPile)
        obs.discardPile.push_back(c);
    for (const auto &c : bc.cards.exhaustPile)
        obs.exhaustPile.push_back(c);

    for (int i = 0; i < bc.potionCapacity; ++i)
        obs.potions.push_back(bc.potions[i]);

    for (int r = 0; r < 128; ++r)
        if (bc.player.hasRelicRuntime(static_cast<RelicId>(r)))
            obs.relics.set(r);

    return obs;
}

// ---- HiddenBattleState -----------------------------------------------------
void HiddenBattleState::randomize(std::mt19937_64 &rng) {
    auto rand64 = [&]() -> std::uint64_t {
        return static_cast<std::uint64_t>(rng()) << 32 | rng();
    };
    shuffleRngSeed0 = rand64();
    shuffleRngSeed1 = rand64();
    cardRandomRngSeed0 = rand64();
    cardRandomRngSeed1 = rand64();
    aiRngSeed0 = rand64();
    aiRngSeed1 = rand64();
    miscRngSeed0 = rand64();
    miscRngSeed1 = rand64();
    monsterHpRngSeed0 = rand64();
    monsterHpRngSeed1 = rand64();
    potionRngSeed0 = rand64();
    potionRngSeed1 = rand64();
    weight = 1.0;
}

std::vector<HiddenBattleState> HiddenBattleState::sampleParticles(
    const CombatObservation &obs,
    const BattleContext &templateBc,
    std::mt19937_64 &rng,
    int count)
{
    std::vector<HiddenBattleState> particles(count);
    for (auto &p : particles) {
        p.randomize(rng);
        // Shuffle draw pile contents randomly (hidden order)
        p.drawPileOrder = obs.drawPileContents;
        std::shuffle(p.drawPileOrder.begin(), p.drawPileOrder.end(), rng);
    }
    return particles;
}

// ---- Belief ----------------------------------------------------------------
Belief Belief::initial(const BattleContext &bc, int particleCount,
                       std::mt19937_64 &rng)
{
    auto obs = CombatObservation::fromBattleContext(bc);
    Belief b;
    b.particles = HiddenBattleState::sampleParticles(obs, bc, rng, particleCount);
    return b;
}

// A particle contradicts an observation when the observed draw pile is not the
// front remainder of the particle's sampled order. Cards pop from the pile's
// back (CardManager::popFromDrawPile), so after any draws the observed pile
// must equal the particle's order prefix positionally; unobserved reshuffles
// or inserts leave the particle contradictory. Unprovable cases are
// zero-weighted; the uniform fallback in sample() keeps search alive when all
// particles contradict.
static bool drawOrderConsistent(const HiddenBattleState &p,
                                const CombatObservation &obs) {
    const auto &pile = p.drawPileOrder;
    const auto &rem = obs.drawPileContents;
    if (rem.size() > pile.size()) return false;   // observed more cards than the particle ever had
    for (size_t i = 0; i < rem.size(); ++i)
        if (pile[i].getId() != rem[i].getId()) return false;
    return true;
}

void Belief::update(const CombatObservation &obs) {
    // Reweight particles based on consistency with the observed draw pile
    for (auto &p : particles)
        p.weight *= drawOrderConsistent(p, obs) ? 1.0 : 0.0;
}

const HiddenBattleState &Belief::sample(std::mt19937_64 &rng) const {
    const size_t n = particles.size();
    double total = 0.0;
    bool uniform = true;
    const double firstWeight = particles[0].weight;
    for (const auto &p : particles) {
        if (p.weight != firstWeight) uniform = false;
        total += p.weight;
    }
    if (uniform || total <= 0.0) {
        std::uniform_int_distribution<size_t> dist(0, n - 1);
        return particles[dist(rng)];
    }
    std::uniform_real_distribution<double> dist(0.0, total);
    double r = dist(rng);
    double acc = 0.0;
    for (const auto &p : particles) {
        acc += p.weight;
        if (acc >= r) return p;
    }
    return particles.back();
}

} // namespace sts
