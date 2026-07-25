//
// CombatObservation.cpp: implementation
//
#include "sim/search/CombatObservation.h"
#include "combat/BattleContext.h"
#include "game/Random.h"

#include <cstring>
#include <algorithm>

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

std::uint64_t CombatObservation::visibleHash() const {
    std::uint64_t h = 0x9e3779b97f4a7c15ULL;
    hashMix(h, static_cast<std::uint64_t>(turn));
    hashMix(h, static_cast<std::uint64_t>(ascension));
    hashMix(h, static_cast<std::uint64_t>(encounter));
    hashMix(h, static_cast<std::uint64_t>(player.curHp));
    hashMix(h, static_cast<std::uint64_t>(player.block));
    hashMix(h, static_cast<std::uint64_t>(player.energy));
    hashMix(h, static_cast<std::uint64_t>(player.strength));
    hashMix(h, static_cast<std::uint64_t>(player.dexterity));
    hashMix(h, static_cast<std::uint64_t>(player.focus));
    hashMix(h, static_cast<std::uint64_t>(player.artifact));
    hashMix(h, static_cast<std::uint64_t>(player.gold));
    hashMix(h, static_cast<std::uint64_t>(player.cardsPlayedThisTurn));
    hashMix(h, static_cast<std::uint64_t>(player.attacksPlayedThisTurn));
    hashMix(h, static_cast<std::uint64_t>(player.skillsPlayedThisTurn));

    for (const auto &m : monsters) {
        hashMix(h, static_cast<std::uint64_t>(m.id));
        hashMix(h, static_cast<std::uint64_t>(m.curHp));
        hashMix(h, static_cast<std::uint64_t>(m.block));
        hashMix(h, static_cast<std::uint64_t>(m.strength));
        hashMix(h, static_cast<std::uint64_t>(m.vulnerable));
        hashMix(h, static_cast<std::uint64_t>(m.weak));
        hashMix(h, static_cast<std::uint64_t>(m.poison));
        hashMix(h, static_cast<std::uint64_t>(m.artifact));
        hashMix(h, static_cast<std::uint64_t>(m.incomingDamage));
        hashMix(h, static_cast<std::uint64_t>(m.isAttacking ? 1 : 0));
    }

    // Draw pile: commutative multiset (player knows contents, not order)
    std::uint64_t drawAcc = 0;
    for (const auto &c : drawPileContents)
        drawAcc += static_cast<std::uint64_t>(c.getId()) * 6364136223846793005ULL;
    hashMix(h, drawAcc);

    // Hand: commutative (multiset via sum)
    std::uint64_t handAcc = 0;
    for (const auto &c : hand)
        handAcc += static_cast<std::uint64_t>(c.getId()) * 6364136223846793005ULL;
    hashMix(h, handAcc);

    // Discard/exhaust: commutative
    std::uint64_t disAcc = 0;
    for (const auto &c : discardPile)
        disAcc += static_cast<std::uint64_t>(c.getId()) * 6364136223846793005ULL;
    hashMix(h, disAcc);

    std::uint64_t exhAcc = 0;
    for (const auto &c : exhaustPile)
        exhAcc += static_cast<std::uint64_t>(c.getId()) * 6364136223846793005ULL;
    hashMix(h, exhAcc);

    for (const auto &p : potions)
        hashMix(h, static_cast<std::uint64_t>(static_cast<int>(p)));

    // 128-bit relics: hash via per-bit accumulator
    for (int r = 0; r < 128; ++r)
        if (relics.test(r)) hashMix(h, static_cast<std::uint64_t>(r) * 6364136223846793005ULL);

    return h ? h : 1;
}

bool CombatObservation::operator==(const CombatObservation &o) const {
    if (turn != o.turn || ascension != o.ascension || encounter != o.encounter)
        return false;
    if (player.curHp != o.player.curHp || player.block != o.player.block
        || player.energy != o.player.energy || player.strength != o.player.strength
        || player.dexterity != o.player.dexterity || player.focus != o.player.focus
        || player.artifact != o.player.artifact || player.gold != o.player.gold)
        return false;
    if (player.cardsPlayedThisTurn != o.player.cardsPlayedThisTurn
        || player.attacksPlayedThisTurn != o.player.attacksPlayedThisTurn
        || player.skillsPlayedThisTurn != o.player.skillsPlayedThisTurn)
        return false;
    if (monsters.size() != o.monsters.size()) return false;
    for (size_t i = 0; i < monsters.size(); ++i) {
        const auto &a = monsters[i], &b = o.monsters[i];
        if (a.id != b.id || a.curHp != b.curHp || a.block != b.block
            || a.strength != b.strength || a.vulnerable != b.vulnerable
            || a.weak != b.weak || a.poison != b.poison || a.artifact != b.artifact)
            return false;
    }
    if (hand.size() != o.hand.size() || discardPile.size() != o.discardPile.size()
        || exhaustPile.size() != o.exhaustPile.size())
        return false;
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

void Belief::resample(std::mt19937_64 &rng) {
    if (particles.empty()) return;
    std::vector<double> weights(particles.size());
    double total = 0.0;
    for (size_t i = 0; i < particles.size(); ++i) {
        weights[i] = particles[i].weight;
        total += weights[i];
    }
    if (total <= 0.0) {
        for (auto &p : particles) p.weight = 1.0 / particles.size();
        return;
    }

    std::vector<HiddenBattleState> resampled(particles.size());
    std::uniform_real_distribution<double> dist(0.0, total);
    for (auto &p : resampled) {
        double r = dist(rng);
        double acc = 0.0;
        for (const auto &src : particles) {
            acc += src.weight;
            if (acc >= r) { p = src; break; }
        }
        p.weight = 1.0 / particles.size();
    }
    particles = std::move(resampled);
}

void Belief::update(const CombatObservation &obs) {
    // Reweight particles based on consistency with observation
    for (auto &p : particles) {
        // If the draw pile order doesn't match observed draws, zero weight
        // Simplified: keep all particles, weight them by consistency
        (void)obs;
    }
}

const HiddenBattleState &Belief::sample(std::mt19937_64 &rng) const {
    std::uniform_int_distribution<size_t> dist(0, particles.size() - 1);
    return particles[dist(rng)];
}

} // namespace sts
