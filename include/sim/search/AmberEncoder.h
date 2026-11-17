// Native encoder from a combat search state to Amber-Eye-shaped tokens (sim/search/AmberTokens.h; stage 0 of the
// self-play loop assessment, 2026-11-16). It reads BattleContext directly: no wire struct, no JSON, no strings and
// no heap allocation per call, so a net-leaf search can encode every leaf (CombatTokNet's wire-JSON encoder costs
// ~150 us per position).
//
// Information content: at least what CombatTokNet's combatTokEncodeWire reads from the state's wire
// (wireFromSearchState): global, player, monsters with ids, moves, numbers and statuses, player statuses, cards in
// every zone, relics, potions, the current card-queue item, and in card-select states the pending card queue, the
// pending action queue and the card-select info. The draw pile is encoded as the wire exposes it: in
// information-set mode the known bottom / known top with their positions and the unknown middle without order; a
// concrete pile with its full order. Feature layout per token type: AmberEncoder.cpp.
//
// Categorical ids, one shared space in [1, kAmberIdVocab), 0 = none, disjoint ranges per kind (static_asserted):
//   card       1 + (CardId - 1)                     CardId 1..ZAP
//   relic      kAmberRelicBase + RelicId            RelicId 0..RED_CIRCLET
//   potion     kAmberPotionBase + (Potion - 2)      Potion 2..WEAK_POTION (no id for INVALID / empty slot)
//   status     kAmberStatusBase + (PlayerStatus-1)  PlayerStatus 1..THE_BOMB
//   monster    kAmberMonsterBase + (MonsterId - 1)  MonsterId 1..WRITHING_MASS
//   move       kAmberMoveBase + (MonsterMoveId - 1) MonsterMoveId 1..WRITHING_MASS_STRONG_STRIKE
//   m-power    kAmberMonPowerBase + (MS - ANGRY)    MonsterStatus ANGRY..TIME_WARP (a monster has at most one)
#ifndef STS_AMBER_ENCODER_H
#define STS_AMBER_ENCODER_H

#include <cstdint>
#include <vector>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/AmberTokens.h"
#include "sim/search/GameAction.h"
#include "sim/search/SilverSearcher.h"

namespace sts::search {

    constexpr int kAmberCardBase = 1;
    constexpr int kAmberRelicBase = kAmberCardBase + static_cast<int>(CardId::ZAP);
    constexpr int kAmberPotionBase = kAmberRelicBase + static_cast<int>(RelicId::RED_CIRCLET) + 1;
    constexpr int kAmberStatusBase = kAmberPotionBase + static_cast<int>(Potion::WEAK_POTION) - 1;
    constexpr int kAmberMonsterBase = kAmberStatusBase + static_cast<int>(PlayerStatus::THE_BOMB);
    constexpr int kAmberMoveBase = kAmberMonsterBase + static_cast<int>(MonsterId::WRITHING_MASS);
    constexpr int kAmberMonPowerBase = kAmberMoveBase + static_cast<int>(MonsterMoveId::WRITHING_MASS_STRONG_STRIKE);
    constexpr int kAmberIdEnd = kAmberMonPowerBase + static_cast<int>(MonsterStatus::TIME_WARP)
                                - static_cast<int>(MonsterStatus::ANGRY) + 1;
    static_assert(kAmberIdEnd <= kAmberIdVocab, "Amber id ranges overflow the shared vocabulary");

    // Out-of-combat ranges (amberEncodeGame), after the combat ones. Bosses reuse the monster range (their main
    // monster), cards / relics / potions the combat ranges; room types, rest options, reward kinds, Neow bonuses
    // and drawbacks are float one-hots (AmberGameEncoder.cpp), since the vocabulary has no room for them.
    //   event      kAmberEventBase + (Event - NEOW)     Event NEOW..WORLD_OF_GOOP
    //   screen     kAmberScreenBase + (ScreenState - 1) ScreenState EVENT_SCREEN..BATTLE
    constexpr int kAmberEventBase = kAmberIdEnd;
    constexpr int kAmberScreenBase = kAmberEventBase + static_cast<int>(Event::WORLD_OF_GOOP)
                                     - static_cast<int>(Event::NEOW) + 1;
    constexpr int kAmberGameIdEnd = kAmberScreenBase + static_cast<int>(ScreenState::BATTLE);
    static_assert(kAmberGameIdEnd <= kAmberIdVocab, "Amber out-of-combat id ranges overflow the shared vocabulary");

    // AmberAction::type values.
    enum class AmberActionType : std::uint8_t {
        END_TURN = 0,
        PLAY_CARD,          // src = hand card, tgt = target monster (cards that need one)
        USE_POTION,         // src = potion, tgt = target monster (potions that need one)
        DISCARD_POTION,     // src = potion
        SELECT_CARD,        // src = the chosen card (hand / draw / discard / exhaust)
        SELECT_OPTION,      // src = the chosen OPTION token (Codex / Discovery card choice)
        SKIP_SELECT,        // Codex / Discovery skip
        SELECT_MANY,        // hand multi-select: src / tgt = first / last chosen card, f[1] = hand-index mask
        SELECT_TWO,         // Liquid Memories (2 picks): src / tgt = first / second discard card
        UNKNOWN,            // an action this encoder cannot resolve against the state (no src / tgt)
        // Out-of-combat (amberEncodeGame); out-of-combat potion drinks / discards use USE_POTION / DISCARD_POTION.
        MAP_MOVE = 10,      // tgt = the destination MAP token (row 14 -> the boss token)
        CHOOSE_OPTION,      // src = the chosen OPTION token (reward item, shop item, boss relic, rest option, Neow
                            // option, event option, chest, Match and Keep slot); tgt = the deck CARD / RELIC /
                            // POTION an event option names (Falling, We Meet Again, N'loth)
        CHOOSE_CARD,        // src = the chosen CARD token: on a card-select screen a deck card (remove / upgrade /
                            // transform / duplicate / bottle) or a card the screen offers (The Library, Neow
                            // choices); on a reward screen the card reward (the Singing Bowl stays an OPTION)
        SKIP_OR_LEAVE,      // reward skip, shop leave, chest skip, boss relic skip, campfire proceed
    };

    // Fills `out` (out.clear() first) for `state` under `context`, with one AmberAction per entry of `actions` in
    // order (the first kAmberMaxActions; the rest counted in out.cut, as are tokens past a segment's capacity).
    // Deterministic: the same state, context and actions give bit-identical live slots.
    void amberEncodeCombat(const BattleContext &state, const SilverSearchContext &context,
                           const std::vector<search::Action> &actions, AmberTokens &out);

    // Out-of-combat counterpart for a GameContext decision screen (ScreenState other than BATTLE; a BATTLE state gets
    // its RUN / PLAYER / CARD / RELIC / POTION / MAP tokens and UNKNOWN actions): RUN, PLAYER, CARD = the master
    // deck, RELIC, POTION, OPTION = the screen's choices, MAP = the current act's nodes still reachable (current node,
    // boss, then nearest rows first; the rest counted in out.cut). Only what the player sees: no RNG, pools, encounter
    // queues, unopened chest contents, Dead Adventurer reward order or burning-elite buff (its elite is public: the
    // event text names it). `actions` =
    // GameAction::getAllActionsInState(gc) or a subset, plus optionally out-of-combat potion drinks / discards
    // (bits 0x80000000 | slot, 0xC0000000 | slot) and the Singing Bowl reward (RewardsActionType::CARD, group, 5).
    // No heap allocation. Feature layout: AmberGameEncoder.cpp.
    void amberEncodeGame(const GameContext &gc, const std::vector<GameAction> &actions, AmberTokens &out);

    // IEEE float16 bits of `x`, round to nearest even (as numpy's float32 -> float16 cast); and back.
    std::uint16_t amberHalf(float x);
    float amberHalfToFloat(std::uint16_t h);

}

#endif
