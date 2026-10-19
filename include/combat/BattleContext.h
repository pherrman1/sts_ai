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

    // STS_BLOOD_POTION_HEAL_FIX: unset/1 (default) = a Blood Potion drunk in
    // combat heals 20% of max HP, 40% with Sacred Bark, as in the game and as
    // out of combat (combat parity canary 2 2026-10-18: 15 vs 31 HP at 79 max
    // HP). 0 = the legacy engine, which had the two swapped. Other values are
    // fatal. Read only when a Blood Potion is drunk in combat.
    bool bloodPotionHealFix();

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
