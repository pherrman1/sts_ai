//
// Created by gamerpuppy on 7/4/2021.
//

#ifndef STS_LIGHTSPEED_BATTLECONTEXT_H
#define STS_LIGHTSPEED_BATTLECONTEXT_H

#include <vector>
#include <array>
#include <functional>

#include "sts_common.h"

#include "data_structure/fixed_list.h"
#include "constants/Potions.h"
#include "constants/MonsterEncounters.h"
#include "combat/InputState.h"
#include "combat/Player.h"
#include "combat/Monster.h"
#include "combat/MonsterGroup.h"
#include "combat/ActionQueue.h"
#include "combat/CardQueue.h"
#include "combat/Actions.h"
#include "combat/CardManager.h"
#include "combat/CardSelectInfo.h"


namespace sts {



    enum class Outcome {
        UNDECIDED=0,
        PLAYER_VICTORY,
        PLAYER_LOSS,
    };

    static constexpr const char * battleOutcomeStrings[] {
            "UNDECIDED",
            "PLAYER_VICTORY",
            "PLAYER_LOSS",
    };

    class GameContext;

    extern thread_local std::function<void(const BattleContext &, GameContext &)> g_onBattleExitPersistent;

    // Optional instrumentation at the RAW persistent-transfer boundary.  The
    // callback runs after combat-owned persistent fields have been copied into
    // GameContext, but before GameContext::regainControl()/afterBattle.  It is
    // invoked for victory, loss, and unresolved exits so data producers can
    // quarantine the latter two without pretending they are successful fights.
    // It is null by default and has no gameplay effect.
    extern thread_local std::function<void(const BattleContext &, GameContext &)> g_onBattleExitRaw;

    extern thread_local BattleContext *g_debug_bc;

    // STS_DEAD_TARGET_DEBUFF_FIX: unset or 1 = a debuff or buff on a dead,
    // half-dead or escaped monster does nothing, as in the game
    // (ApplyPowerAction.update returns first when target.isDeadOrEscaped();
    // combat parity canary 2026-10-18: Uppercut killing its target leaves it
    // without Weak or Vulnerable); 0 = the legacy engine applies it. Other
    // values are fatal. Read only when the target is already dead.
    bool deadTargetDebuffFix();

    // STS_CURL_UP_LETHAL_FIX: unset/1 (default) = Curl Up does not trigger on
    // a lethal hit, as in CurlUpPower.onAttacked (damageAmount <
    // currentHealth; combat parity canary 2 2026-10-18). The dead louse's
    // block and status bits are part of Silver's node identity, so this can
    // change search. 0 = the legacy engine curls anyway. Other values are
    // fatal. Read only on a lethal hit.
    bool curlUpLethalFix();

    // STS_DEAD_MONSTER_BLOCK_FIX: unset/1 (default) = queued monster block
    // (Curl Up, Malleable, Guardian mode shift, block moves) does nothing once
    // the monster is dead, as in GainBlockAction.update (skips isDying or
    // isDead; overnight live play 2026-10-19: Fiend Fire curls a louse with an
    // early hit and kills it before the block lands). Dead-monster block is
    // part of Silver's node identity, so this can change search. 0 = the
    // legacy engine adds the block. Other values are fatal. Read only when
    // the monster is dead.
    bool deadMonsterBlockFix();

    // STS_DEAD_ALLY_STRENGTH_FIX: unset/1 (default) = Donu's Circle of Power
    // and Spire Spear's Piercer skip a dead ally's Strength, as Java's queued
    // ApplyPowerAction skips a dead target (follow-up to live problem 56).
    // Dead monsters' powers are part of Silver's node identity, so this can
    // change search. 0 = the legacy engine buffs the dead ally. Other values
    // are fatal. Read only when the ally is dead.
    bool deadAllyStrengthFix();

    // STS_MUGGER_DEATH_RNG_FIX: unset/1 (default) = a dying Mugger draws
    // aiRng.random(2) for its death sound (Mugger.die calls playDeathSfx,
    // which uses aiRng; the Looter's uses MathUtils), as in the game (combat
    // parity canary 2 2026-10-18: aiRng counter 9 in Java vs 8 natively after
    // the kill). Later monster rolls in the fight change. 0 = the legacy
    // engine draws nothing. Other values are fatal.
    bool muggerDeathRngFix();

    // STS_SPIRE_SURROUNDED_DEATH_FIX: unset/1 (default) = when Spire Shield
    // or Spire Spear dies with its partner alive, the player loses Surrounded,
    // as SpireShield/SpireSpear.die() queue RemoveSpecificPowerAction
    // (javap, live parity problem 40); this unblocks Smoke Bomb. 0 = the legacy
    // engine keeps Surrounded for the rest of the fight. Other values are fatal.
    bool spireSurroundedDeathFix();

    // STS_MUMMIFIED_HAND_PLAYED_CARD_FIX: unset/1 (default) = Mummified Hand
    // never picks the Power being played, which Java's cardQueue still holds
    // (live parity problem 48). 0 = the legacy pick. Other values are fatal.
    bool mummifiedHandPlayedCardFix();

    // STS_SLIME_SPLIT_RNG_FIX: unset/1 (default) = a large slime's split draws
    // aiRng for the two spawned medium slimes' first moves (SpawnMonsterAction
    // -> init -> rollMove) and, for Spike Slime (L) only, one more roll from
    // its queued RollMoveAction, as in the game; the split trigger of both
    // large slimes and the Slime Boss records the split move twice in the
    // move history (damage() calls setMove and queues a SetMoveAction).
    // Overnight live play 2026-10-19: aiRng counter 6 in Java vs 8 natively
    // after an Acid Slime (L) split. Later monster rolls in the fight change.
    // 0 = the legacy engine draws two extra rolls for either large slime and
    // keeps the previous move in moveHistory[1]. Other values are fatal.
    bool slimeSplitRngFix();

    // STS_DYING_ATTACKER_FIX: unset/1 (default) = a queued monster attack
    // hit does nothing once its attacker is dead or half-dead, as in the game
    // (DamageAction.update cancels a non-THORNS hit when its owner isDying or
    // halfDead; overnight live parity 2026-10-19: Thorns killed a Byrd
    // mid-Peck and the game skipped its last two hits, HP 46 vs native 44).
    // 0 = the legacy engine lands every hit. Other values are fatal. Read
    // only when the attacker is dead or half-dead.
    bool dyingAttackerFix();

    // STS_BLOOD_POTION_HEAL_FIX: unset/1 (default) = a Blood Potion drunk in
    // combat heals 20% of max HP, 40% with Sacred Bark, as in the game and as
    // out of combat (combat parity canary 2 2026-10-18: 15 vs 31 HP at 79 max
    // HP). 0 = the legacy engine, which had the two swapped. Other values are
    // fatal. Read only when a Blood Potion is drunk in combat.
    bool bloodPotionHealFix();

    // STS_HALF_DEAD_POWER_RESET_FIX: unset/1 (default) = a Darkling going
    // half-dead loses its power amounts as well as its status bits, as in
    // Darkling.damage (powers.clear(); overnight parity 2026-10-19: Vulnerable
    // and Weak left on killed Darklings). Without it a debuff on the revived
    // Darkling adds to the stale amount. 0 = the legacy engine. Other values
    // are fatal. Read only when a Darkling goes half-dead.
    bool halfDeadPowerResetFix();

    // STS_STRIKE_COUNT_FIX: unset/1 (default) = Perfected Strike counts Strikes
    // in hand, draw and discard only, as Java PerfectedStrike.countCards: a
    // Havoc/Mayhem-autoplayed Perfected Strike does not count itself, and the
    // live importer's recounted strikeCount skips the exhaust pile and Stasis
    // cards (overnight live play 2026-10-19, problem 10: 53 -> 26 natively vs
    // 29 in the game). 0 = the legacy counts. Other values are fatal. Read only
    // when an autoplayed Perfected Strike is used or the importer recounts.
    bool strikeCountFix();

    // STS_PILE_COST_RESET_FIX: unset/1 (default) = a card that lands in the
    // discard, draw or exhaust pile mid-turn gets costForTurn = cost, as in the
    // game (Soul.update calls clearPowers -> resetAttributes when the card
    // lands; ExhaustCardEffect.update calls resetAttributes; combat parity
    // canary 2 2026-10-19: a played 0-cost Discovery Power Through shows
    // costForTurn 1 in the discard pile). Cards created straight into a pile
    // (ShowCardAndAddToDiscardEffect etc.) keep their cost. 0 = the legacy
    // engine, which kept the turn cost until the end of turn. Other values are
    // fatal. Read only when a moved card's costForTurn differs from its cost.
    bool pileCostResetFix();

    // STS_HAND_UPGRADE_ALL_FIX: unset/1 (default) = upgrading every card in
    // hand (Armaments+, Blessing of the Forge) skips cards that cannot be
    // upgraded, as in the game (ArmamentsAction checks c.canUpgrade(); live
    // overnight 2026-10-19 seed 111194457: Ascender's Bane stayed unupgraded).
    // 0 = the legacy engine also upgrades curses and statuses (Burn+ deals 4).
    // Other values are fatal. Read only when such an upgrade resolves.
    bool handUpgradeAllFix();

    // STS_MAYHEM_AFTER_DRAW_FIX: unset/1 (default) = Mayhem plays the top
    // card after the start-of-turn draw, as in the game (MayhemPower queues a
    // wrapper action that queues PlayTopCardAction at the bottom when it
    // runs, behind DrawCardAction; overnight live play 2026-10-19 problem 13:
    // the played card opened a hand selection, Metallicize instead of a
    // pre-draw attack). 0 = the legacy engine, which played the pre-draw top
    // card. Other values are fatal. Read only at a Mayhem turn start.
    bool mayhemAfterDrawFix();

    // STS_MAGNETISM_FIX: unset/1 (default) = Magnetism adds its random
    // colorless card(s) to the hand at the start of each turn, as in the game
    // (MagnetismPower.atStartOfTurn rolls returnTrulyRandomColorlessCardInCombat
    // on cardRandomRng and queues MakeTempCardInHandAction; overnight live play
    // 2026-10-20 problem 39). 0 = the legacy engine, where Magnetism did
    // nothing. Other values are fatal. Read only at a Magnetism turn start.
    bool magnetismFix();

    struct BattleContext {

        // begin for debugging purposes
        inline static int sum = 0; // for preventing optimization in benchmarks
        bool haveUsedDiscoveryAction = false; // for tracking undefined behavior resulting from using the action
        bool undefinedBehaviorEvoked = false; // some cards cause inconsistent outcomes in games
        std::uint64_t seed = 0;
        int floorNum = 0;
        MonsterEncounter encounter = MonsterEncounter::INVALID;
        int loopCount = 0;
        int energyWasted = 0;
        int cardsDrawn = 0;
        // end for debugging purposes

        Random aiRng;
        Random cardRandomRng;
        Random miscRng;
        Random monsterHpRng;
        Random potionRng;
        Random shuffleRng;

        int ascension = 0;
        Outcome outcome = Outcome::UNDECIDED;
        bool smokeBombUsed = false;
        InputState inputState = InputState::EXECUTING_ACTIONS;
        CardSelectInfo cardSelectInfo;

        int monsterTurnIdx = 6;

        // Search only (Runic Dome): monster move rolls are deferred until the
        // move is used or queried (Monster::pendingMoveRolls), so a search
        // cannot see intents the player cannot. Always false in real play.
        bool intentsHidden = false;

        bool isBattleOver() const { return outcome != Outcome::UNDECIDED; }
        bool endTurnQueued = false;
        bool turnHasEnded = false;
        bool skipMonsterTurn = false;

        ActionQueue<128> actionQueue;
        CardQueue cardQueue;

        int potionCount = 0;
        int potionCapacity = 3;
        std::array<Potion, 5> potions {Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT,
                                       Potion::EMPTY_POTION_SLOT};

        int turn = 0;
        Player player;
        MonsterGroup monsters;
        CardManager cards;

        CardQueueItem curCardQueueItem;

        std::bitset<32> miscBits; // 0 stolen gold check,

        BattleContext() = default;
        BattleContext(const BattleContext &rhs) = default;

        // Exact equality of every field except the static benchmark `sum`.
        bool operator==(const BattleContext &rhs) const;

        // Equality for search transposition (the Silver fork's rule set):
        // operator== without the RNG streams and the debug/statistics fields
        // (loopCount, energyWasted, cardsDrawn, haveUsedDiscoveryAction,
        // undefinedBehaviorEvoked); curCardQueueItem is ignored when both
        // states are quiet player decisions; the hand is compared as a
        // multiset, and so are the discard and exhaust piles once the draw
        // pile is in information-set mode.
        [[nodiscard]] bool equalForSearch(const BattleContext &rhs) const;

// ****************************************

        void init(const GameContext &gc);
        void init(const GameContext &gc, MonsterEncounter encounterToInit);

        void initRelics(const GameContext &gc);

        void exitBattle(GameContext &g) const;
        void updateRelicsOnExit(GameContext &g) const;
        void updateCardsOnExit(Deck &d) const; // for cards like ritual dagger, and eventually lesson learned results

        [[nodiscard]] bool smokeBombEscapeBlocked() const {
            return isBossEncounter(encounter) || player.hasStatus<PS::SURROUNDED>();
        }

// ****************************************

        void setRequiresStolenGoldCheck(bool value);
        [[nodiscard]] bool requiresStolenGoldCheck() const;
        [[nodiscard]] int getMonsterTurnNumber() const;  // returns 1 for first turn, 2 for second, etc.

// ****************************************

        void executeActions();

        void playCardQueueItem(CardQueueItem);
        void useCard();
        void useNoTriggerCard();

        void useAttackCard();
        void useSkillCard();
        void usePowerCard();

        void onUseAttackCard();
        void onUseSkillCard();
        void onUsePowerCard();

        void onUseStatusOrCurseCard();
        void onAfterUseCard();

        void setState(InputState state);
        void addToTop(const Action &a);
        void addToBot(const Action &a);

        void addToTopCard(CardQueueItem item);
        void addToBotCard(CardQueueItem item);

        void checkCombat();
        void clearPostCombatActions();
        void cleanCardQueue();

        [[nodiscard]] bool isCardPlayAllowed() const;

        // **********************

        void endTurn(); // called when player clicks the end turn button
        void callEndOfTurnActions(); // GameActionManager.callEndTurnActions(), called when the end turn cardQueue item is reached.
        void onTurnEnding(); // AbstractRoom endTurn(), called when the turn actually ends.

        void callEndTurnEarlySequence(); // time eater

        void applyEndOfRoundPowers(); // game : MonsterGroup applyEndOfTurnPowers
        void afterMonsterTurns();

        void obtainPotion(Potion p);
        void discardPotion(int idx);
        void drinkPotion(int idx, int target=0);

        void drawCards(int count);
        void discardAtEndOfTurn();
        void discardAtEndOfTurnHelper();

        void playTopCardInDrawPile(int monsterTargetIdx, bool exhausts);

        void moveToHandHelper(CardInstance c);
        void exhaustSpecificCardInHand(int idx, std::int16_t uniqueId);
        void restoreRetainedCards(int count);
        void exhaustTopCardInHand();

        // this is
        void triggerOnEndOfTurnForPlayingCards();
        void triggerOnOtherCardPlayed(const CardInstance &usedCard);

        template <MonsterStatus s>
        void debuffEnemy(int idx, int amount, bool isSourceMonster=true);

        [[nodiscard]] int calculateCardDamage(const CardInstance &card, int targetIdx, int baseDamage) const;
        [[nodiscard]] int calculateCardBlock(int baseBlock) const;

        void queuePurgeCard(const CardInstance &c, int target);
        void addPurgeCardToCardQueue(const CardQueueItem &item); // not really the front but hey
        void noOpRollMove(); // called by monsters to manipulate the aiRng counter when their rollMove function doesn't do anything

        void onManualDiscard(const CardInstance &c);
        void onShuffle();
        void triggerAndMoveToExhaustPile(CardInstance c);
        void mummifiedHandOnUsePower();

        // card select screens
        void openDiscoveryScreen(std::array<CardId, 3> discoveryCards, int copyCount);
        void openSimpleCardSelectScreen(CardSelectTask task, int count);

        // single card select helpers
        void chooseArmamentsCard(int handIdx);
        void chooseCodexCard(CardId id);
        void chooseDiscardToHandCard(int discardIdx, bool forZeroCost);
        void chooseDiscoveryCard(CardId id);
        void chooseDualWieldCard(int handIdx);
        void chooseExhaustOneCard(int handIdx);
        void chooseExhumeCard(int exhaustIdx);
        void chooseForethoughtCard(int handIdx);
        void chooseForethoughtCards(const fixed_list<int,10> &idxs);
        void chooseHeadbuttCard(int discardIdx);
        void chooseRecycleCard(int handIdx);
        void chooseWarcryCard(int handIdx);

        // multi card helpers
        void chooseDrawToHandCards(const int *idxs, int cardCount);
        void chooseExhaustCards(const fixed_list<int,10> &idxs);
        void chooseGambleCards(const fixed_list<int,10> &idxs);

    };

    std::ostream& operator<<(std::ostream &os, const BattleContext &bc);

    template <PlayerStatus s>
    Action Actions::BuffPlayer(int amount) {
        return makeAction(ActData_BuffPlayer{s, amount});
    }

    template <PlayerStatus s>
    Action Actions::DebuffPlayer(int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffPlayer{s, amount, isSourceMonster});
    }

    template<PlayerStatus s>
    Action Actions::DecrementStatus(int amount) {
        return makeAction(ActData_DecrementStatus{s, amount});
    }

    template <PlayerStatus s>
    Action Actions::RemoveStatus() {
        return makeAction(ActData_RemoveStatus{s});
    }

    template<MonsterStatus s>
    Action Actions::BuffEnemy(int idx, int amount) {
        return makeAction(ActData_BuffEnemy{s, idx, amount});
    }

    template <MonsterStatus s>
    Action Actions::DebuffEnemy(int idx, int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffEnemy{s, idx, amount, isSourceMonster});
    }

    template <MonsterStatus s>
    Action Actions::DebuffAllEnemy(int amount, bool isSourceMonster) {
        return makeAction(ActData_DebuffAllEnemy{s, amount, isSourceMonster});
    }

    template <MonsterStatus s>
    void BattleContext::debuffEnemy(int idx, int amount, bool isSourceMonster) {
        // todo poison and snake skull
        Monster &e = monsters.arr[idx];
        if (e.isDeadOrEscaped() && deadTargetDebuffFix()) {
            return;
        }

        if (e.hasStatus<MS::ARTIFACT>()) {
            e.decrementStatus<MS::ARTIFACT>();
            return;
        }

        e.addDebuff<s>(amount, isSourceMonster);
        if (player.hasStatus<PS::SADISTIC>()) {
            addToBot( Actions::DamageEnemy(idx, player.getStatus<PS::SADISTIC>()) );
        }

        if (s == MS::VULNERABLE && player.hasRelic<RelicId::CHAMPION_BELT>()) {
            addToBot(Actions::DebuffEnemy<MS::WEAK>(idx, 1, false) );
        }
    }


}

#endif //STS_LIGHTSPEED_BATTLECONTEXT_H
