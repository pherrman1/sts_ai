//
// Created by gamerpuppy on 7/4/2021.
//

#ifndef STS_LIGHTSPEED_ACTIONS_H
#define STS_LIGHTSPEED_ACTIONS_H

#include <array>
#include <cstdint>
#include <new>
#include <vector>

#include "constants/PlayerStatusEffects.h"
#include "constants/MonsterStatusEffects.h"
#include "constants/Cards.h"
#include "constants/Potions.h"

#include "combat/InputState.h"
#include "combat/CardSelectInfo.h"
#include "combat/CardInstance.h"
#include "combat/CardQueue.h"
#include "game/Random.h"

namespace sts {

    class BattleContext;

    typedef std::array<std::uint16_t,5> DamageMatrix;

    // Combat actions are plain values: a type tag plus the parameters the
    // action was created with. Two queued actions compare equal exactly when
    // they would do the same thing, which lets search code compare and hash
    // pending action queues. Each variant is trivially copyable, so copying a
    // BattleContext copies the queued actions with plain copies.
    //
    // X(Name, type1,field1, type2,field2, ...) declares ActData_Name with those
    // fields; its operator() (in Actions.cpp) performs the action.
#define STS_FOREACH_COMBAT_ACTION(X) \
    X(BuffPlayer, PlayerStatus,s, int,amount) \
    X(DebuffPlayer, PlayerStatus,s, int,amount, bool,isSourceMonster) \
    X(DecrementStatus, PlayerStatus,s, int,amount) \
    X(RemoveStatus, PlayerStatus,s) \
    X(BuffEnemy, MonsterStatus,s, int,idx, int,amount) \
    X(DebuffEnemy, MonsterStatus,s, int,idx, int,amount, bool,isSourceMonster) \
    X(DebuffAllEnemy, MonsterStatus,s, int,amount, bool,isSourceMonster) \
    X(SetState, InputState,state) \
    X(AttackEnemy, int,idx, int,damage) \
    X(AttackAllEnemy, int,baseDamage) \
    X(AttackAllEnemyMatrix, DamageMatrix,damageMatrix) \
    X(DamageEnemy, int,idx, int,damage) \
    X(DamageAllEnemy, int,damage) \
    X(AttackPlayer, int,idx, int,damage) \
    X(DamagePlayer, int,damage, bool,selfDamage) \
    X(VampireAttack, int,damage) \
    X(PlayerLoseHp, int,hp, bool,selfDamage) \
    X(HealPlayer, int,amount) \
    X(MonsterGainBlock, int,idx, int,amount) \
    X(RollMove, int,monsterIdx) \
    X(ReactiveRollMove) \
    X(NoOpRollMove) \
    X(ChangeStance, Stance,stance) \
    X(GainEnergy, int,amount) \
    X(GainBlock, int,amount) \
    X(DrawCards, int,amount) \
    X(EmptyDeckShuffle) \
    X(ShuffleDrawPile) \
    X(ShuffleTempCardIntoDrawPile, CardId,id, int,count) \
    X(PlayTopCard, int,monsterTargetIdx, bool,exhausts) \
    X(MakeTempCardInHand, CardInstance,card, int,amount) \
    X(MakeTempCardInDrawPile, CardInstance,c, int,amount, bool,shuffleInto) \
    X(MakeTempCardInDiscard, CardInstance,c, int,amount) \
    X(DiscardNoTriggerCard) \
    X(ClearCardQueue) \
    X(DiscardAtEndOfTurn) \
    X(DiscardAtEndOfTurnHelper) \
    X(RestoreRetainedCards, int,count) \
    X(UnnamedEndOfTurnAction) \
    X(MonsterStartTurnAction) \
    X(TriggerEndOfTurnOrbsAction) \
    X(ExhaustTopCardInHand) \
    X(ExhaustSpecificCardInHand, int,idx, std::int16_t,uniqueId) \
    X(DamageRandomEnemy, int,damage) \
    X(ExhaustRandomCardInHand, int,count) \
    X(MadnessAction) \
    X(RandomizeHandCost) \
    X(GainBlockRandomEnemy, int,sourceMonster, int,amount) \
    X(SummonGremlins) \
    X(SpawnTorchHeads) \
    X(SpireShieldDebuff) \
    X(OnAfterCardUsed) \
    X(PutRandomCardsInDrawPile, CardType,type, int,count) \
    X(DiscoveryAction, CardType,type, int,amount) \
    X(InfernalBladeAction) \
    X(JackOfAllTradesAction, bool,upgraded) \
    X(TransmutationAction, bool,upgraded, int,energy, bool,useEnergy) \
    X(ViolenceAction, int,count) \
    X(BetterDiscardPileToHandAction, int,amount, CardSelectTask,task) \
    X(ArmamentsAction) \
    X(DualWieldAction, int,copyCount) \
    X(ExhumeAction) \
    X(ForethoughtAction, bool,upgraded) \
    X(HeadbuttAction) \
    X(ChooseExhaustOne) \
    X(DrawToHandAction, CardSelectTask,task, CardType,cardType) \
    X(WarcryAction) \
    X(TimeEaterPlayCardQueueItem, CardQueueItem,x) \
    X(UpgradeAllCardsInHand) \
    X(EssenceOfDarkness, int,darkOrbsPerSlot) \
    X(IncreaseOrbSlots, int,count) \
    X(SuicideAction, int,monsterIdx, bool,triggerRelics) \
    X(PoisonLoseHpAction, int,monsterIdx) \
    X(RemovePlayerDebuffs) \
    X(UpgradeRandomCardAction) \
    X(CodexAction) \
    X(ExhaustMany, int,limit) \
    X(GambleAction) \
    X(ToolboxAction) \
    X(DualityAction) \
    X(ApotheosisAction) \
    X(DropkickAction, int,targetIdx) \
    X(EnlightenmentAction, bool,upgraded) \
    X(EntrenchAction) \
    X(FeedAction, int,idx, int,damage, bool,upgraded) \
    X(FiendFireAction, int,targetIdx, int,calculatedDamage) \
    X(HandOfGreedAction, int,idx, int,damage, bool,upgraded) \
    X(LimitBreakAction) \
    X(ReaperAction, int,baseDamage) \
    X(RitualDaggerAction, int,idx, int,damage) \
    X(SecondWindAction, int,blockPerCard) \
    X(SeverSoulExhaustAction) \
    X(SwordBoomerangAction, int,baseDamage) \
    X(SpotWeaknessAction, int,target, int,strength) \
    X(WhirlwindAction, int,baseDamage, int,energy, bool,useEnergy) \
    X(AttackAllMonsterRecursive, DamageMatrix,matrix, int,timesRemaining) \
    X(TransmutationCardsInHand, Random,rng, int,count, bool,upgraded) \
    X(IncreasePlayerOrbSlots, int,count)

#define STS_ACT_NARG(...) STS_ACT_NARG_(__VA_ARGS__, STS_ACT_RSEQ())
#define STS_ACT_NARG_(...) STS_ACT_ARG_N(__VA_ARGS__)
#define STS_ACT_ARG_N(_1, _2, _3, _4, _5, _6, _7, _8, _9, _10, _11, _12, N, ...) N
#define STS_ACT_RSEQ() 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0
#define STS_ACT_EACH_0(F, a)
#define STS_ACT_EACH_1(F, a)
#define STS_ACT_EACH_2(F, t, n) F(t, n)
#define STS_ACT_EACH_4(F, t, n, ...) F(t, n) STS_ACT_EACH_2(F, __VA_ARGS__)
#define STS_ACT_EACH_6(F, t, n, ...) F(t, n) STS_ACT_EACH_4(F, __VA_ARGS__)
#define STS_ACT_EACH_8(F, t, n, ...) F(t, n) STS_ACT_EACH_6(F, __VA_ARGS__)
#define STS_ACT_CAT(a, b) STS_ACT_CAT_(a, b)
#define STS_ACT_CAT_(a, b) a##b
#define STS_ACT_EACH(F, ...) STS_ACT_CAT(STS_ACT_EACH_, STS_ACT_NARG(__VA_ARGS__))(F, __VA_ARGS__)

#define STS_ACT_FIELD(type, name) type name;
#define STS_ACT_DATA(Name, ...) struct ActData_##Name { \
        __VA_OPT__(STS_ACT_EACH(STS_ACT_FIELD, __VA_ARGS__)) \
        void operator()(BattleContext &bc) const; \
        bool operator==(const ActData_##Name &rhs) const = default; };
    STS_FOREACH_COMBAT_ACTION(STS_ACT_DATA)

#define STS_ACT_ENUM(Name, ...) Name,
    enum class CombatActionType : std::uint8_t {
        INVALID,
        STS_FOREACH_COMBAT_ACTION(STS_ACT_ENUM)
    };

    struct Action {
        CombatActionType type = CombatActionType::INVALID;
        bool clearOnCombatVictory = true;
        bool executeAfterCombatVictory = false;
        union {
#define STS_ACT_VARIANT(Name, ...) ActData_##Name v_##Name;
            STS_FOREACH_COMBAT_ACTION(STS_ACT_VARIANT)
        };

        Action() {}

        void operator()(BattleContext &bc) const;
        bool operator==(const Action &rhs) const;
    };

#define STS_ACT_MAKE(Name, ...) \
    inline Action makeAction(const ActData_##Name &data, bool clearOnCombatVictory=true, \
                             bool executeAfterCombatVictory=false) { \
        Action a; \
        a.type = CombatActionType::Name; \
        a.clearOnCombatVictory = clearOnCombatVictory; \
        a.executeAfterCombatVictory = executeAfterCombatVictory; \
        new (&a.v_##Name) ActData_##Name(data); \
        return a; \
    }
    STS_FOREACH_COMBAT_ACTION(STS_ACT_MAKE)

    struct Actions {
        static Action SetState(InputState state);

        // implemented in BattleContext.h because of template
        template <PlayerStatus s> static Action BuffPlayer(int amount=1);
        template <PlayerStatus s> static Action DebuffPlayer(int amount=1, bool isSourceMonster=true);

        template <PlayerStatus s> static Action DecrementStatus(int amount=1);
        template <PlayerStatus s> static Action RemoveStatus();

        template <MonsterStatus> static Action BuffEnemy(int idx, int amount=1);
        template <MonsterStatus> static Action DebuffEnemy(int idx, int amount, bool isSourceMonster=true);
        template <MonsterStatus> static Action DebuffAllEnemy(int amount, bool isSourceMonster=true);


        // todo, action and damage actions should clear certain actions from the queue if the player kills all enemies
        static Action AttackEnemy(int idx, int damage);

        // for cards that do one hit, like cleave
        static Action AttackAllEnemy(int baseDamage);

        // for cards like whirlwind, where damage is calculated once
        static Action AttackAllEnemy(DamageMatrix damageMatrix);

        static Action DamageEnemy(int idx, int damage);

        // all usages of this in game have pureDamage set to true
        static Action DamageAllEnemy(int damage); // todo maybe need to add boolean isPlayerOwner

        static Action AttackPlayer(int idx, int damage);
        static Action DamagePlayer(int damage, bool selfDamage=false);

        static Action VampireAttack(int damage); // only used by shelled parasite

        static Action PlayerLoseHp(int hp, bool selfDamage=false);
        static Action HealPlayer(int amount, bool executeAfterCombatVictory=false);

        static Action MonsterGainBlock(int idx, int amount);
        static Action RollMove(int monsterIdx);
        static Action ReactiveRollMove(); // for writhing mass

        static Action NoOpRollMove();

        static Action ChangeStance(Stance stance);
        static Action GainEnergy(int amount);
        static Action GainBlock(int amount);
        static Action DrawCards(int amount);


        // the draw pile doesn't actually have to be empty
        // the game calls on shuffle when this is created
        static Action EmptyDeckShuffle();

        // used by Deep Breath and Reboot, does not trigger onShuffle relics
        static Action ShuffleDrawPile();

        static Action ShuffleTempCardIntoDrawPile(CardId id, int count=1);

        static Action PlayTopCard(int monsterTargetIdx, bool exhausts);
        static Action MakeTempCardInHand(CardId card, bool upgraded= false, int amount = 1);
        static Action MakeTempCardInHand(CardInstance c, int amount = 1);
        static Action MakeTempCardInDrawPile(const CardInstance &c, int amount, bool shuffleInto);
        static Action MakeTempCardInDiscard(const CardInstance &c, int amount = 1);

        static Action DiscardNoTriggerCard(); // for doubt, shame, etc, discards the BattleContext.curCard


        static Action ClearCardQueue();
        static Action DiscardAtEndOfTurn();
        static Action DiscardAtEndOfTurnHelper();
        static Action RestoreRetainedCards(int count);

        static Action UnnamedEndOfTurnAction();
        static Action MonsterStartTurnAction();
        static Action TriggerEndOfTurnOrbsAction();

        static Action ExhaustTopCardInHand();
        static Action ExhaustSpecificCardInHand(int idx, std::int16_t uniqueId);

        // Random Actions

        static Action DamageRandomEnemy(int damage); // juggernaut
        static Action GainBlockRandomEnemy(int sourceMonster, int amount);

        static Action SummonGremlins();
        static Action SpawnTorchHeads();
        static Action SpireShieldDebuff(); // only called if player has orb slots

        static Action ExhaustRandomCardInHand(int count);
        static Action MadnessAction();
        static Action RandomizeHandCost();
        static Action UpgradeRandomCardAction(); // Warped Tongs Relic

        static Action CodexAction(); // Nilrys Codex onPlayerEndTurn
        static Action ExhaustMany(int limit);
        static Action GambleAction();
        static Action ToolboxAction();
        static Action FiendFireAction(int targetIdx, int calculatedDamage); // Fiend Fire Card
        static Action SwordBoomerangAction(int baseDamage); // Sword Boomerang

        static Action PutRandomCardsInDrawPile(CardType type, int count); // used by chrysalis and metamorphosis
        static Action DiscoveryAction(CardType type, int amount); // attack potion, skill potion
        static Action InfernalBladeAction();
        static Action JackOfAllTradesAction(bool upgraded);
        static Action TransmutationAction(bool upgraded, int energy, bool useEnergy);
        // Adds the colorless cards TransmutationAction rolled: replays the rolls from
        // a copy of cardRandomRng taken before them, so the action stays a fixed-size value.
        static Action TransmutationCardsInHand(const Random &rng, int count, bool upgraded);
        static Action ViolenceAction(int count);

        static Action BetterDiscardPileToHandAction(int amount, CardSelectTask task); // used by hologram and liquid memories
        static Action ArmamentsAction();
        static Action DualWieldAction(int copyCount);
        static Action ExhumeAction();
        static Action ForethoughtAction(bool upgraded);
        static Action HeadbuttAction();
        static Action ChooseExhaustOne();
        static Action DrawToHandAction(CardSelectTask task, CardType cardType);
        static Action WarcryAction();

        // ************

        static Action TimeEaterPlayCardQueueItem(const CardQueueItem &item);
        static Action UpgradeAllCardsInHand();
        static Action OnAfterCardUsed(); // called UseCardAction in game
        static Action EssenceOfDarkness(int darkOrbsPerSlot); // handle sacred bark
        static Action IncreaseOrbSlots(int count);
        static Action IncreasePlayerOrbSlots(int count); // Inserter relic

        static Action SuicideAction(int monsterIdx, bool triggerRelics);

        static Action PoisonLoseHpAction(int monsterIdx);
        static Action RemovePlayerDebuffs(); // Orange Pellets Relic

        static Action DualityAction(); // Duality Relic

        static Action ApotheosisAction();
        static Action DropkickAction(int targetIdx);
        static Action EnlightenmentAction(bool upgraded);
        static Action EntrenchAction();
        static Action FeedAction(int idx, int damage, bool upgraded);
        static Action HandOfGreedAction(int idx, int damage, bool upgraded);
        static Action LimitBreakAction();
        static Action ReaperAction(int baseDamage);
        static Action RitualDaggerAction(int idx, int damage);
        static Action SecondWindAction(int blockPerCard);
        static Action SeverSoulExhaustAction();
        static Action SpotWeaknessAction(int target, int strength); // Spot Weakness
        static Action WhirlwindAction(int baseDamage, int energy, bool useEnergy);

        static Action AttackAllMonsterRecursive(DamageMatrix matrix, int timesRemaining);
    };

}

#endif //STS_LIGHTSPEED_ACTIONS_H
