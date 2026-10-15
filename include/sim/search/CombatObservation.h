//
// CombatObservation: agent-facing observation that NEVER exposes RNG state.
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
    std::uint32_t occupantGeneration = 0;
    std::uint16_t latentDamageMask = 0;
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
