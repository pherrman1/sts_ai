//
// CombatObservation: agent-facing observation that NEVER exposes RNG state.
// Particle/Belief: hidden-state tracking for POMCP/ISMCTS.
//
#ifndef STS_LIGHTSPEED_COMBATOBSERVATION_H
#define STS_LIGHTSPEED_COMBATOBSERVATION_H

#include "sts_common.h"
#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "constants/MonsterEncounters.h"
#include "constants/PlayerStatusEffects.h"
#include "constants/MonsterStatusEffects.h"
#include "combat/Player.h"
#include "combat/Monster.h"
#include "combat/CardInstance.h"
#include "combat/InputState.h"
#include "combat/CardSelectInfo.h"

#include <vector>
#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <random>
#include <string>
#include <unordered_map>

namespace sts {

// -- Visible Monster State -------------------------------------------------
struct MonsterVisibleState {
    MonsterId id = MonsterId::INVALID;
    int curHp = 0;
    int maxHp = 0;
    int block = 0;
    int strength = 0;
    int vulnerable = 0;
    int weak = 0;
    int poison = 0;
    int artifact = 0;
    int incomingDamage = 0;
    int incomingHits = 0;
    MMID lastMove = MMID::INVALID;
    bool isAttacking = false;
    bool isTargetable = false;

    void fromMonster(const Monster &m, const BattleContext &bc);
};

// -- Player Visible State --------------------------------------------------
struct PlayerVisibleState {
    int curHp = 80;
    int maxHp = 80;
    int block = 0;
    int energy = 0;
    int strength = 0;
    int dexterity = 0;
    int focus = 0;
    int artifact = 0;
    Stance stance = Stance::NEUTRAL;
    int gold = 0;
    int cardsPlayedThisTurn = 0;
    int attacksPlayedThisTurn = 0;
    int skillsPlayedThisTurn = 0;

    std::array<int8_t, 8> relicCounters{};
    std::vector<std::pair<PlayerStatus, int16_t>> powers;

    void fromPlayer(const Player &p);
};

// -- CombatObservation: what the player CAN know ---------------------------
struct CombatObservation {
    PlayerVisibleState player;
    std::vector<MonsterVisibleState> monsters;
    std::vector<CardInstance> hand;
    std::vector<CardInstance> drawPileContents;    // multiset (known, but order unknown)
    std::vector<CardInstance> discardPile;
    std::vector<CardInstance> exhaustPile;
    std::vector<Potion> potions;
    int potionCapacity = 3;
    int turn = 0;
    int ascension = 0;
    MonsterEncounter encounter = MonsterEncounter::INVALID;
    bool isCardPlayAllowed = true;
    // Decision context: the player must know which decision they are facing.
    // Two states that differ only in inputState (PLAYER_NORMAL vs CARD_SELECT)
    // or card-select context (task/pickCount/offer contents) are different
    // decisions and must not share an observation identity.
    InputState inputState = InputState::PLAYER_NORMAL;
    CardSelectTask cardSelectTask = CardSelectTask::INVALID;
    int pickCount = 0;
    bool canPickZero = false;
    bool canPickAnyNumber = false;
    std::array<CardId, 3> cardSelectOffers{CardId::INVALID, CardId::INVALID, CardId::INVALID};
    std::bitset<128> relics;   // only bit 0-127

    static CombatObservation fromBattleContext(const BattleContext &bc);
    std::uint64_t visibleHash() const;
    bool operator==(const CombatObservation &o) const;
    bool operator!=(const CombatObservation &o) const { return !(*this == o); }
};

// -- Particle: a full hidden state consistent with observations ------------
struct HiddenBattleState {
    std::vector<CardInstance> drawPileOrder;   // actual order (hidden)
    std::uint64_t shuffleRngSeed0 = 0;
    std::uint64_t shuffleRngSeed1 = 0;
    std::int32_t shuffleRngCounter = 0;
    std::uint64_t cardRandomRngSeed0 = 0;
    std::uint64_t cardRandomRngSeed1 = 0;
    std::int32_t cardRandomRngCounter = 0;
    std::uint64_t aiRngSeed0 = 0;
    std::uint64_t aiRngSeed1 = 0;
    std::int32_t aiRngCounter = 0;
    std::uint64_t miscRngSeed0 = 0;
    std::uint64_t miscRngSeed1 = 0;
    std::int32_t miscRngCounter = 0;
    std::uint64_t monsterHpRngSeed0 = 0;
    std::uint64_t monsterHpRngSeed1 = 0;
    std::int32_t monsterHpRngCounter = 0;
    std::uint64_t potionRngSeed0 = 0;
    std::uint64_t potionRngSeed1 = 0;
    std::int32_t potionRngCounter = 0;

    double weight = 1.0;
    std::uint64_t id = 0;

    HiddenBattleState() = default;
    void randomize(std::mt19937_64 &rng);

    static std::vector<HiddenBattleState> sampleParticles(
        const CombatObservation &obs,
        const BattleContext &templateBc,
        std::mt19937_64 &rng,
        int count);
};

// -- Equality-backed full-hidden-state identity -----------------------------
// Canonical ordered identity of one draw-pile card. FullHiddenStateKey uses
// these so hidden-state uniqueness/novelty comparisons are exact (vector
// equality + full RNG triples), never a combined hash. Same identity fields
// as CardActionKey (id, upgradeCount, costForTurn, freeToPlayOnce, specialData)
// so replay states and belief particles project identically.
struct FullHiddenCardId {
    CardId id = CardId::INVALID;
    std::int16_t specialData = 0;
    std::int8_t costForTurn = 0;
    std::int8_t upgradeCount = 0;
    bool freeToPlayOnce = false;

    FullHiddenCardId() = default;
    explicit FullHiddenCardId(const CardInstance &c);

    bool operator==(const FullHiddenCardId &o) const;
    bool operator!=(const FullHiddenCardId &o) const { return !(*this == o); }
    bool operator<(const FullHiddenCardId &o) const;
    std::uint64_t hash() const;
};

// One full hidden hypothesis: the ordered draw pile plus the six RNG
// (seed0, seed1, counter) triples. Equality is exact; ordering (operator<)
// makes it usable as an equality-backed std::set key.
struct FullHiddenStateKey {
    std::vector<FullHiddenCardId> drawPileOrder;
    // Six streams, fixed order: shuffle, cardRandom, ai, misc, monsterHp, potion.
    std::array<std::uint64_t, 6> seed0{};
    std::array<std::uint64_t, 6> seed1{};
    std::array<std::int32_t, 6> counter{};

    bool operator==(const FullHiddenStateKey &o) const;
    bool operator!=(const FullHiddenStateKey &o) const { return !(*this == o); }
    bool operator<(const FullHiddenStateKey &o) const;
};

FullHiddenStateKey fullHiddenStateKey(const HiddenBattleState &particle);
FullHiddenStateKey fullHiddenStateKey(const BattleContext &bc);

// -- Belief: weighted set of particles -------------------------------------
struct Belief {
    std::vector<HiddenBattleState> particles;

    void update(const CombatObservation &obs);
    const HiddenBattleState &sample(std::mt19937_64 &rng) const;
    // Same draw as sample(), but exposes the selected index for diagnostics.
    size_t sampleIndex(std::mt19937_64 &rng) const;
    int compatibleCount(const CombatObservation &obs) const;
    int distinctCompatibleDrawOrders(const CombatObservation &obs) const;
    int distinctCompatibleRngSignatures(const CombatObservation &obs) const;
    int fallbackShuffleCount(const BattleContext &bc) const;
    int positiveCount() const;
    int distinctPositiveDrawOrders() const;
    int distinctPositiveRngSignatures() const;
    int distinctPositiveHypotheses() const;
    [[nodiscard]] bool empty() const { return particles.empty(); }
    [[nodiscard]] size_t size() const { return particles.size(); }

    static Belief initial(const BattleContext &bc, int particleCount,
                          std::mt19937_64 &rng);
};

} // namespace sts

// Hash specialization for CombatObservation
namespace std {
template <> struct hash<sts::CombatObservation> {
    std::uint64_t operator()(const sts::CombatObservation &o) const noexcept {
        return o.visibleHash();
    }
};
}

#endif // STS_LIGHTSPEED_COMBATOBSERVATION_H
