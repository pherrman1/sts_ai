//
// Created by gamerpuppy on 7/4/2021.
//

#include "combat/Actions.h"
#include "sim/search/CombatKnowledge.h"
#include "combat/BattleContext.h"
#include "game/Game.h"

#include <type_traits>
#include <utility>
#include <vector>

using namespace sts;

namespace {

    constexpr std::size_t kPlayerStatusCount = static_cast<std::size_t>(PlayerStatus::THE_BOMB) + 1;
    constexpr std::size_t kMonsterStatusCount = static_cast<std::size_t>(MonsterStatus::INVALID) + 1;

    // Calls fn(std::integral_constant<Enum, value>{}) so a status stored in an
    // action reaches the status templates on Player, Monster and BattleContext.
    template <typename Enum, typename Fn, std::size_t... I>
    void dispatchStatus(Enum value, Fn &fn, std::index_sequence<I...>) {
        using Call = void (*)(Fn &);
        static constexpr Call table[] = {
            +[](Fn &f) { f(std::integral_constant<Enum, static_cast<Enum>(I)>{}); }...
        };
        table[static_cast<std::size_t>(value)](fn);
    }

    template <typename Fn>
    void withPlayerStatus(PlayerStatus s, Fn &&fn) {
        dispatchStatus(s, fn, std::make_index_sequence<kPlayerStatusCount>{});
    }

    template <typename Fn>
    void withMonsterStatus(MonsterStatus s, Fn &&fn) {
        dispatchStatus(s, fn, std::make_index_sequence<kMonsterStatusCount>{});
    }

}

void Action::operator()(BattleContext &bc) const {
    switch (type) {
#define STS_ACT_CALL(Name, ...) case CombatActionType::Name: v_##Name(bc); break;
        STS_FOREACH_COMBAT_ACTION(STS_ACT_CALL)
#undef STS_ACT_CALL
        case CombatActionType::INVALID:
            break;
    }
}

bool Action::operator==(const Action &rhs) const {
    if (type != rhs.type || clearOnCombatVictory != rhs.clearOnCombatVictory
            || executeAfterCombatVictory != rhs.executeAfterCombatVictory) {
        return false;
    }
    switch (type) {
#define STS_ACT_EQ(Name, ...) case CombatActionType::Name: return v_##Name == rhs.v_##Name;
        STS_FOREACH_COMBAT_ACTION(STS_ACT_EQ)
#undef STS_ACT_EQ
        case CombatActionType::INVALID:
            return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Factories

Action Actions::SetState(InputState state) {
    return makeAction(ActData_SetState{state});
}

Action Actions::AttackEnemy(int idx, int damage) {
    return makeAction(ActData_AttackEnemy{idx, damage});
}

Action Actions::AttackAllEnemy(int baseDamage) {
    return makeAction(ActData_AttackAllEnemy{baseDamage});
}

Action Actions::AttackAllEnemy(DamageMatrix damageMatrix) {
    return makeAction(ActData_AttackAllEnemyMatrix{damageMatrix});
}

Action Actions::DamageEnemy(int idx, int damage) {
    return makeAction(ActData_DamageEnemy{idx, damage});
}

Action Actions::DamageAllEnemy(int damage) {
    // todo this is probably broken
    return makeAction(ActData_DamageAllEnemy{damage});
}

Action Actions::AttackPlayer(int idx, int damage) {
    return makeAction(ActData_AttackPlayer{idx, damage}, false);
}

Action Actions::DamagePlayer(int damage, bool selfDamage) {
    return makeAction(ActData_DamagePlayer{damage, selfDamage}, false);
}

Action Actions::VampireAttack(int damage) {
    return makeAction(ActData_VampireAttack{damage});
}

Action Actions::PlayerLoseHp(int hp, bool selfDamage) {
    // TODO this doesn't take into account intangible or relics
    return makeAction(ActData_PlayerLoseHp{hp, selfDamage}, false);
}

Action Actions::HealPlayer(int amount, bool executeAfterCombatVictory) {
    return makeAction(ActData_HealPlayer{amount}, false, executeAfterCombatVictory);
}

Action Actions::MonsterGainBlock(int idx, int amount) {
    return makeAction(ActData_MonsterGainBlock{idx, amount});
}

Action Actions::RollMove(int monsterIdx) {
    return makeAction(ActData_RollMove{monsterIdx});
}

Action Actions::ReactiveRollMove() {
    return makeAction(ActData_ReactiveRollMove{});
}

Action Actions::NoOpRollMove() {
    return makeAction(ActData_NoOpRollMove{});
}

Action Actions::ChangeStance(Stance stance) {
    return makeAction(ActData_ChangeStance{stance});
}

Action Actions::GainEnergy(int amount) {
    return makeAction(ActData_GainEnergy{amount});
}

Action Actions::GainBlock(int amount) {
    return makeAction(ActData_GainBlock{amount}, false);
}

Action Actions::DrawCards(int amount) {
    return makeAction(ActData_DrawCards{amount});
}

Action Actions::EmptyDeckShuffle() {
    return makeAction(ActData_EmptyDeckShuffle{});
}

Action Actions::ShuffleDrawPile() {
    return makeAction(ActData_ShuffleDrawPile{});
}

Action Actions::ShuffleTempCardIntoDrawPile(CardId id, int count) {
    return makeAction(ActData_ShuffleTempCardIntoDrawPile{id, count});
}

Action Actions::PlayTopCard(int monsterTargetIdx, bool exhausts) {
    return makeAction(ActData_PlayTopCard{monsterTargetIdx, exhausts});
}

Action Actions::MakeTempCardInHand(CardInstance card, int amount) {
    // todo master reality when the action is created
    return makeAction(ActData_MakeTempCardInHand{card, amount});
}

Action Actions::MakeTempCardInDrawPile(const CardInstance &c, int amount, bool shuffleInto) {
    // the random calculation is done in an effect so it be wrong to do it here?
    return makeAction(ActData_MakeTempCardInDrawPile{c, amount, shuffleInto});
}

Action Actions::MakeTempCardInDiscard(const CardInstance &c, int amount) {
    return makeAction(ActData_MakeTempCardInDiscard{c, amount});
}

Action Actions::DiscardNoTriggerCard() {
    return makeAction(ActData_DiscardNoTriggerCard{});
}

Action Actions::ClearCardQueue() {
    return makeAction(ActData_ClearCardQueue{});
}

Action Actions::DiscardAtEndOfTurn() {
    return makeAction(ActData_DiscardAtEndOfTurn{});
}

Action Actions::DiscardAtEndOfTurnHelper() {
    return makeAction(ActData_DiscardAtEndOfTurnHelper{});
}

Action Actions::RestoreRetainedCards(int count) {
    return makeAction(ActData_RestoreRetainedCards{count});
}

Action Actions::UnnamedEndOfTurnAction() {
    // EndTurnAction does this:
        //        AbstractDungeon.player.resetControllerValues();
        //        this.turnHasEnded = true;
        //        playerHpLastTurn = AbstractDungeon.player.currentHealth;
    return makeAction(ActData_UnnamedEndOfTurnAction{});
}

Action Actions::MonsterStartTurnAction() {
    return makeAction(ActData_MonsterStartTurnAction{});
}

Action Actions::TriggerEndOfTurnOrbsAction() {
    return makeAction(ActData_TriggerEndOfTurnOrbsAction{});
}

Action Actions::ExhaustTopCardInHand() {
    return makeAction(ActData_ExhaustTopCardInHand{});
}

Action Actions::ExhaustSpecificCardInHand(int idx, std::int16_t uniqueId) {
    return makeAction(ActData_ExhaustSpecificCardInHand{idx, uniqueId});
}

Action Actions::DamageRandomEnemy(int damage) {
    return makeAction(ActData_DamageRandomEnemy{damage});
}

Action Actions::ExhaustRandomCardInHand(int count) {
    return makeAction(ActData_ExhaustRandomCardInHand{count});
}

Action Actions::MadnessAction() {
    return makeAction(ActData_MadnessAction{});
}

Action Actions::RandomizeHandCost() {
    return makeAction(ActData_RandomizeHandCost{});
}

Action Actions::GainBlockRandomEnemy(int sourceMonster, int amount) {
    return makeAction(ActData_GainBlockRandomEnemy{sourceMonster, amount});
}

Action Actions::SummonGremlins() {
    // gremlin leader searches in the order 1, 2, 0 for open space
    return makeAction(ActData_SummonGremlins{});
}

Action Actions::SpawnTorchHeads() {
    return makeAction(ActData_SpawnTorchHeads{});
}

Action Actions::SpireShieldDebuff() {
    return makeAction(ActData_SpireShieldDebuff{});
}

Action Actions::OnAfterCardUsed() {
    return makeAction(ActData_OnAfterCardUsed{}, false);
}

Action Actions::PutRandomCardsInDrawPile(CardType type, int count) {
    return makeAction(ActData_PutRandomCardsInDrawPile{type, count});
}

Action Actions::DiscoveryAction(CardType type, int amount) {
    return makeAction(ActData_DiscoveryAction{type, amount});
}

Action Actions::InfernalBladeAction() {
    return makeAction(ActData_InfernalBladeAction{});
}

Action Actions::JackOfAllTradesAction(bool upgraded) {
    return makeAction(ActData_JackOfAllTradesAction{upgraded});
}

Action Actions::TransmutationAction(bool upgraded, int energy, bool useEnergy) {
    return makeAction(ActData_TransmutationAction{upgraded, energy, useEnergy});
}

Action Actions::ViolenceAction(int count) {
    // todo a faster algorithm for inserting into the attack list
    return makeAction(ActData_ViolenceAction{count});
}

Action Actions::BetterDiscardPileToHandAction(int amount, CardSelectTask task) {
    return makeAction(ActData_BetterDiscardPileToHandAction{amount, task});
}

Action Actions::ArmamentsAction() {
    return makeAction(ActData_ArmamentsAction{});
}

Action Actions::DualWieldAction(int copyCount) {
    return makeAction(ActData_DualWieldAction{copyCount});
}

Action Actions::ExhumeAction() {
    // todo this is bugged because the selected card cannot be exhume
    return makeAction(ActData_ExhumeAction{});
}

Action Actions::ForethoughtAction(bool upgraded) {
    return makeAction(ActData_ForethoughtAction{upgraded});
}

Action Actions::HeadbuttAction() {
    return makeAction(ActData_HeadbuttAction{});
}

Action Actions::ChooseExhaustOne() {
    return makeAction(ActData_ChooseExhaustOne{});
}

Action Actions::DrawToHandAction(CardSelectTask task, CardType cardType) {
    return makeAction(ActData_DrawToHandAction{task, cardType});
}

Action Actions::WarcryAction() {
    return makeAction(ActData_WarcryAction{});
}

Action Actions::TimeEaterPlayCardQueueItem(const CardQueueItem &x) {
    return makeAction(ActData_TimeEaterPlayCardQueueItem{x}, false);
}

Action Actions::UpgradeAllCardsInHand() {
    return makeAction(ActData_UpgradeAllCardsInHand{});
}

Action Actions::EssenceOfDarkness(int darkOrbsPerSlot) {
    return makeAction(ActData_EssenceOfDarkness{darkOrbsPerSlot});
}

Action Actions::IncreaseOrbSlots(int count) {
    return makeAction(ActData_IncreaseOrbSlots{count});
}

Action Actions::SuicideAction(int monsterIdx, bool triggerRelics) {
    return makeAction(ActData_SuicideAction{monsterIdx, triggerRelics});
}

Action Actions::PoisonLoseHpAction(int monsterIdx) {
    return makeAction(ActData_PoisonLoseHpAction{monsterIdx});
}

Action Actions::RemovePlayerDebuffs() {
    return makeAction(ActData_RemovePlayerDebuffs{});
}

Action Actions::UpgradeRandomCardAction() {
    return makeAction(ActData_UpgradeRandomCardAction{});
}

Action Actions::CodexAction() {
    return makeAction(ActData_CodexAction{});
}

Action Actions::ExhaustMany(int limit) {
    return makeAction(ActData_ExhaustMany{limit});
}

Action Actions::GambleAction() {
    return makeAction(ActData_GambleAction{});
}

Action Actions::ToolboxAction() {
    return makeAction(ActData_ToolboxAction{});
}

Action Actions::DualityAction() {
    return makeAction(ActData_DualityAction{});
}

Action Actions::ApotheosisAction() {
    return makeAction(ActData_ApotheosisAction{});
}

Action Actions::DropkickAction(int targetIdx) {
    // assume bc.curCard is the card being used
    return makeAction(ActData_DropkickAction{targetIdx});
}

Action Actions::EnlightenmentAction(bool upgraded) {
    return makeAction(ActData_EnlightenmentAction{upgraded});
}

Action Actions::EntrenchAction() {
    return makeAction(ActData_EntrenchAction{});
}

Action Actions::FeedAction(int idx, int damage, bool upgraded) {
    return makeAction(ActData_FeedAction{idx, damage, upgraded});
}

Action Actions::FiendFireAction(int targetIdx, int calculatedDamage) {
    return makeAction(ActData_FiendFireAction{targetIdx, calculatedDamage});
}

Action Actions::HandOfGreedAction(int idx, int damage, bool upgraded) {
    return makeAction(ActData_HandOfGreedAction{idx, damage, upgraded});
}

Action Actions::LimitBreakAction() {
    return makeAction(ActData_LimitBreakAction{});
}

Action Actions::ReaperAction(int baseDamage) {
    return makeAction(ActData_ReaperAction{baseDamage});
}

Action Actions::RitualDaggerAction(int idx, int damage) {
    return makeAction(ActData_RitualDaggerAction{idx, damage});
}

Action Actions::SecondWindAction(int blockPerCard) {
    return makeAction(ActData_SecondWindAction{blockPerCard});
}

Action Actions::SeverSoulExhaustAction() {
    return makeAction(ActData_SeverSoulExhaustAction{});
}

Action Actions::SwordBoomerangAction(int baseDamage) {
    // pretty hacky until I can figure out a better solution
    return makeAction(ActData_SwordBoomerangAction{baseDamage});
}

Action Actions::SpotWeaknessAction(int target, int strength) {
    return makeAction(ActData_SpotWeaknessAction{target, strength});
}

Action Actions::WhirlwindAction(int baseDamage, int energy, bool useEnergy) {
    return makeAction(ActData_WhirlwindAction{baseDamage, energy, useEnergy});
}

Action Actions::AttackAllMonsterRecursive(DamageMatrix matrix, int timesRemaining) {
    return makeAction(ActData_AttackAllMonsterRecursive{matrix, timesRemaining});
}

Action Actions::MakeTempCardInHand(CardId card, bool upgraded, int amount) {
    CardInstance c(card, upgraded);
    return Actions::MakeTempCardInHand(c, amount);
}
Action Actions::TransmutationCardsInHand(const Random &rng, int count, bool upgraded) {
    return makeAction(ActData_TransmutationCardsInHand{rng, count, upgraded});
}

Action Actions::IncreasePlayerOrbSlots(int count) {
    return makeAction(ActData_IncreasePlayerOrbSlots{count});
}

// ---------------------------------------------------------------------------
// Action bodies

void ActData_BuffPlayer::operator()(BattleContext &bc) const {
    if (s == PlayerStatus::CORRUPTION && !bc.player.hasStatus<PS::CORRUPTION>()) {
        bc.cards.onBuffCorruption();
    }
    const int amount = this->amount;
    withPlayerStatus(s, [&](auto status) { bc.player.buff<decltype(status)::value>(amount); });
}

void ActData_DebuffPlayer::operator()(BattleContext &bc) const {
    const int amount = this->amount;
    const bool isSourceMonster = this->isSourceMonster;
    withPlayerStatus(s, [&](auto status) {
        bc.player.debuff<decltype(status)::value>(amount, isSourceMonster);
    });
}

void ActData_DecrementStatus::operator()(BattleContext &bc) const {
    const int amount = this->amount;
    withPlayerStatus(s, [&](auto status) { bc.player.decrementStatus<decltype(status)::value>(amount); });
}

void ActData_RemoveStatus::operator()(BattleContext &bc) const {
    withPlayerStatus(s, [&](auto status) { bc.player.setHasStatus<decltype(status)::value>(false); });
}

void ActData_BuffEnemy::operator()(BattleContext &bc) const {
    // todo check if alive?
    const int amount = this->amount;
    auto &monster = bc.monsters.arr[idx];
    withMonsterStatus(s, [&](auto status) { monster.buff<decltype(status)::value>(amount); });
}

void ActData_DebuffEnemy::operator()(BattleContext &bc) const {
    const int idx = this->idx;
    const int amount = this->amount;
    const bool isSourceMonster = this->isSourceMonster;
    withMonsterStatus(s, [&](auto status) {
        bc.debuffEnemy<decltype(status)::value>(idx, amount, isSourceMonster);
    });
}

void ActData_DebuffAllEnemy::operator()(BattleContext &bc) const {
    // todo this should just add all to bot immediately, not be called first
    // ^^ never mind i think adding to top is a workaround here
    for (int i = bc.monsters.monsterCount-1; i >= 0; --i) {
        if (bc.monsters.arr[i].isTargetable()) {
            bc.addToTop(makeAction(ActData_DebuffEnemy{s, i, amount, isSourceMonster}));
        }
    }
}

void ActData_TransmutationCardsInHand::operator()(BattleContext &bc) const {
    Random rolls = rng;
    for (int i = 0; i < count; ++i) {
        const auto cid = sts::getTrulyRandomColorlessCardInCombat(rolls);
        CardInstance c(cid, upgraded);
        c.setCostForTurn(0);
        c.uniqueId = bc.cards.nextUniqueCardId++;
        bc.cards.notifyAddCardToCombat(c);
        bc.moveToHandHelper(c);
    }
}

void ActData_IncreasePlayerOrbSlots::operator()(BattleContext &bc) const {
    bc.player.increaseOrbSlots(count);
}

void ActData_SetState::operator()(BattleContext &bc) const {
        bc.setState(state);
    }

void ActData_AttackEnemy::operator()(BattleContext &bc) const {
        if (bc.monsters.arr[idx].isDeadOrEscaped()) {
            return;
        }

        bc.monsters.arr[idx].attacked(bc, damage);
        bc.checkCombat();
    }

void ActData_AttackAllEnemy::operator()(BattleContext &bc) const {
        // assume bc.curCard is the card being used

        int damageMatrix[5];
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (!bc.monsters.arr[i].isDeadOrEscaped()) {
                damageMatrix[i] = bc.calculateCardDamage(bc.curCardQueueItem.card, i, baseDamage);
            }
        }

        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (!bc.monsters.arr[i].isDeadOrEscaped()) {
                bc.monsters.arr[i].attacked(bc, damageMatrix[i]);
            }
        }

        bc.checkCombat();
    }

void ActData_AttackAllEnemyMatrix::operator()(BattleContext &bc) const {
        // assume bc.curCard is the card being used

        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (!bc.monsters.arr[i].isDeadOrEscaped()) {
                bc.monsters.arr[i].attacked(bc, static_cast<int>(damageMatrix[i]));
            }
        }

        bc.checkCombat();
    }

void ActData_DamageEnemy::operator()(BattleContext &bc) const {
        if (bc.monsters.arr[idx].isDeadOrEscaped()) {
            return;
        }

        bc.monsters.arr[idx].damage(bc, damage);
        bc.checkCombat();
    }

void ActData_DamageAllEnemy::operator()(BattleContext &bc) const {
        for (int idx = 0; idx < bc.monsters.monsterCount; idx++) {
            if (!bc.monsters.arr[idx].isDeadOrEscaped()) {
                bc.monsters.arr[idx].damage(bc, damage); // possible should addToBot here todo
            }
        }
        bc.checkCombat();
    }

void ActData_AttackPlayer::operator()(BattleContext &bc) const {
        bc.player.attacked(bc, idx, damage);
    }

void ActData_DamagePlayer::operator()(BattleContext &bc) const {
        bc.player.damage(bc, damage, selfDamage);
    }

void ActData_VampireAttack::operator()(BattleContext &bc) const {
        const auto mIdx = 0;
        auto &m = bc.monsters.arr[mIdx]; // only used by shelled parasite so idx is 0
        bc.player.attacked(bc, mIdx, damage);
        if (m.isAlive()) {
            m.heal(std::min(damage, static_cast<int>(bc.player.lastAttackUnblockedDamage)));
        }
    }

void ActData_PlayerLoseHp::operator()(BattleContext &bc) const {
        bc.player.loseHp(bc, hp, selfDamage);
    }

void ActData_HealPlayer::operator()(BattleContext &bc) const {
        bc.player.heal(amount);
    }

void ActData_MonsterGainBlock::operator()(BattleContext &bc) const {
        bc.monsters.arr[idx].block += amount;
    }

void ActData_RollMove::operator()(BattleContext &bc) const {
        Monster &m = bc.monsters.arr[monsterIdx];
        m.rollMove(bc);
    }

void ActData_ReactiveRollMove::operator()(BattleContext &bc) const {
        // writhing mass is always monster 0
        Monster &m = bc.monsters.arr[0];

        for (int i = 0 ; i < m.getStatus<MS::REACTIVE>(); ++i) {
            m.rollMove(bc);
        }
        m.setStatus<MS::REACTIVE>(0);
    }

void ActData_NoOpRollMove::operator()(BattleContext &bc) const {
        bc.noOpRollMove();
    }

void ActData_ChangeStance::operator()(BattleContext &bc) const {
        // stance system is not implemented; no-op
    }

void ActData_GainEnergy::operator()(BattleContext &bc) const {
        bc.player.gainEnergy(amount);
    }

void ActData_GainBlock::operator()(BattleContext &bc) const {
        bc.player.gainBlock(bc, amount);
    }

void ActData_DrawCards::operator()(BattleContext &bc) const {
        bc.drawCards(amount);
    }

void ActData_EmptyDeckShuffle::operator()(BattleContext &bc) const {
        bc.cards.moveDiscardPileIntoToDrawPile(bc.shuffleRng);
    }

void ActData_ShuffleDrawPile::operator()(BattleContext &bc) const {
        bc.cards.drawPile.reshuffleSelf(bc.shuffleRng);
        search::emitCombatKnowledgeEvent(search::CombatKnowledgeEventType::SHUFFLE_OCCURRED);
    }

void ActData_ShuffleTempCardIntoDrawPile::operator()(BattleContext &bc) const {
        CardInstance c(id);
        for (int i = 0; i < count; ++i) {
            bc.cards.createTempCardShuffledIntoDrawPile(bc.cardRandomRng, c);
        }
    }

void ActData_PlayTopCard::operator()(BattleContext &bc) const {
        bc.playTopCardInDrawPile(monsterTargetIdx, exhausts);
    }

void ActData_MakeTempCardInHand::operator()(BattleContext &bc) const {
        for (int i = 0; i < amount; ++i) {
            CardInstance c(card);
            c.uniqueId = bc.cards.nextUniqueCardId++;
            bc.cards.notifyAddCardToCombat(c);
            bc.moveToHandHelper(c);
        }
    }

void ActData_MakeTempCardInDrawPile::operator()(BattleContext &bc) const {
        for (int i = 0; i < amount; ++i) {
            if (shuffleInto) {
                bc.cards.createTempCardShuffledIntoDrawPile(bc.cardRandomRng, c);
            }
            // todo else
        }
    }

void ActData_MakeTempCardInDiscard::operator()(BattleContext &bc) const { // todo maybe store by reference instead of copy if CardInstance is too big to fit directly in the lambda. Make a seperate space where the card will be stored
        for (int i = 0; i < amount; ++i) {
            bc.cards.createTempCardInDiscard(c);
        }
    }

void ActData_DiscardNoTriggerCard::operator()(BattleContext &bc) const {
        const auto &c = bc.curCardQueueItem.card;
        bc.cards.notifyRemoveFromHand(c);
        bc.cards.moveToDiscardPile(c);
    }

void ActData_ClearCardQueue::operator()(BattleContext &bc) const {
        bc.cardQueue.clear();
    }

void ActData_DiscardAtEndOfTurn::operator()(BattleContext &bc) const {
        bc.discardAtEndOfTurn();
    }

void ActData_DiscardAtEndOfTurnHelper::operator()(BattleContext &bc) const {
        bc.discardAtEndOfTurnHelper();
    }

void ActData_RestoreRetainedCards::operator()(BattleContext &bc) const {
        bc.restoreRetainedCards(count);
    }

void ActData_UnnamedEndOfTurnAction::operator()(BattleContext &bc) const {
        bc.turnHasEnded = true;
        if (!bc.skipMonsterTurn) {
            bc.addToBot(Actions::MonsterStartTurnAction());
            bc.monsterTurnIdx = 0; // monstergroup preincrements this
        }
    }

void ActData_MonsterStartTurnAction::operator()(BattleContext &bc) const {
        bc.monsters.applyPreTurnLogic(bc);
    }

void ActData_TriggerEndOfTurnOrbsAction::operator()(BattleContext &bc) const {
        // todo
    }

void ActData_ExhaustTopCardInHand::operator()(BattleContext &bc) const {
        bc.exhaustTopCardInHand();
    }

void ActData_ExhaustSpecificCardInHand::operator()(BattleContext &bc) const {
        bc.exhaustSpecificCardInHand(idx, uniqueId);
    }

void ActData_DamageRandomEnemy::operator()(BattleContext &bc) const {
        const int idx = bc.monsters.getRandomMonsterIdx(bc.cardRandomRng, true);
        if (idx == -1) {
            return;
        }
        bc.monsters.arr[idx].damage(bc, damage);
        bc.checkCombat();
    }

void ActData_ExhaustRandomCardInHand::operator()(BattleContext &bc) const {
        for (int i = 0; i < count; ++i) {
            if (bc.cards.cardsInHand <= 0) {
                return;
            }
            const auto idx = bc.cards.getRandomCardIdxInHand(bc.cardRandomRng);
            auto c = bc.cards.hand[idx];
            bc.cards.removeFromHandAtIdx(idx);
            bc.triggerAndMoveToExhaustPile(c);
        }
    }

void ActData_MadnessAction::operator()(BattleContext &bc) const {

        bool haveNonZeroCost = false;
        bool haveNonZeroTurnCost = false;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            const auto &c = bc.cards.hand[i];

            if (c.costForTurn > 0) {
                haveNonZeroTurnCost = true;
                break;
            }

            if (c.cost > 0) {
                haveNonZeroCost = true;
            }
        }

        const auto haveValidCard = haveNonZeroCost || haveNonZeroTurnCost;
        if (!haveValidCard) {
            return;
        }

        // always have 1 or more cards in hand here
//#pragma clang diagnostic push
//#pragma ide diagnostic ignored "EndlessLoop"
        while (true) {
            const auto randomIdx = bc.cardRandomRng.random(bc.cards.cardsInHand-1);
            auto &c = bc.cards.hand[randomIdx];

            if (haveNonZeroTurnCost) {
                if (c.costForTurn > 0) {
                    c.cost = 0;
                    c.costForTurn = 0;
                    break;
                } else {
                    continue;
                }

            } else {
                if (c.cost > 0) {
                    c.cost = 0;
                    c.costForTurn = 0;
                    break;

                } else {
                    continue;
                }
            }
        }
//#pragma clang diagnostic pop

    }

void ActData_RandomizeHandCost::operator()(BattleContext &bc) const {
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            auto &c = bc.cards.hand[i];
            if (c.cost >= 0) {
                int newCost = bc.cardRandomRng.random(3);
                c.cost = newCost;
                c.costForTurn = newCost;
            }
        }
    }

void ActData_GainBlockRandomEnemy::operator()(BattleContext &bc) const {
        int validIdxs[5];
        int validCount = 0;

        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const auto &m = bc.monsters.arr[i];
            if (i != sourceMonster && !m.isDying()) {
                validIdxs[validCount++] = i;
            }
        }

        int targetIdx;
        if (validCount > 0) {
            targetIdx = validIdxs[bc.aiRng.random(validCount - 1)];
        } else {
            targetIdx = sourceMonster;
        }

        bc.monsters.arr[targetIdx].addBlock(amount);
    }

void ActData_SummonGremlins::operator()(BattleContext &bc) const {
        int openIdxCount = 0;
        int newGremlinIdxs[2];
        if (bc.monsters.arr[1].isDying()) {
            newGremlinIdxs[openIdxCount++] = 1;
        }
        if (bc.monsters.arr[2].isDying()) {
            newGremlinIdxs[openIdxCount++] = 2;
        }
        if (openIdxCount < 2 && bc.monsters.arr[0].isDying()) {
            newGremlinIdxs[openIdxCount++] = 0;
        }
#ifdef sts_asserts
        assert(openIdxCount == 2);
#endif

        auto &gremlin0 = bc.monsters.arr[newGremlinIdxs[0]];
        auto &gremlin1 = bc.monsters.arr[newGremlinIdxs[1]];

        gremlin0 = Monster();
        gremlin1 = Monster();

        gremlin0.construct(bc, MonsterGroup::getGremlin(bc.aiRng), newGremlinIdxs[0]);
        gremlin1.construct(bc, MonsterGroup::getGremlin(bc.aiRng), newGremlinIdxs[1]);
        bc.monsters.monstersAlive += 2;

        if (bc.player.hasRelic<R::PHILOSOPHERS_STONE>()) {
            gremlin0.buff<MS::STRENGTH>(1);
            gremlin1.buff<MS::STRENGTH>(1);
        }
        gremlin0.buff<MS::MINION>();
        gremlin1.buff<MS::MINION>();

        gremlin0.rollMove(bc);
        gremlin1.rollMove(bc);
    }

void ActData_SpawnTorchHeads::operator()(BattleContext &bc) const {
        const auto spawnCount = 3-bc.monsters.monstersAlive;
#ifdef sts_asserts
        assert(spawnCount > 0);
#endif
        const int spawnIdxs[2] {(bc.monsters.arr[1].isDying() ? 1 : 0), 0};

        for (int i = 0; i < spawnCount; ++i) {
            const auto idx = spawnIdxs[i];
            auto &torchHead = bc.monsters.arr[idx];
            torchHead = Monster();
            torchHead.construct(bc, MonsterId::TORCH_HEAD, idx);
            torchHead.initHp(bc.monsterHpRng, bc.ascension); // bug somewhere in game
            torchHead.setMove(MMID::TORCH_HEAD_TACKLE);
            torchHead.buff<MS::MINION>();

            if (bc.player.hasRelic<R::PHILOSOPHERS_STONE>()) {
                torchHead.buff<MS::STRENGTH>(1);
            }
            ++bc.monsters.monstersAlive;
        }

        for (int i = 0; i < spawnCount; ++i) {
            bc.noOpRollMove();
        }
    }

void ActData_SpireShieldDebuff::operator()(BattleContext &bc) const {
        if (bc.aiRng.randomBoolean()) {
            bc.player.debuff<PS::FOCUS>(-1);
        } else {
            bc.player.debuff<PS::STRENGTH>(-1);
        }
    }

void ActData_OnAfterCardUsed::operator()(BattleContext &bc) const {
        bc.onAfterUseCard();
    }

void ActData_PutRandomCardsInDrawPile::operator()(BattleContext &bc) const {
        CardId ids[5];
        for (int i = 0; i < count; ++i) {
            ids[i] = getTrulyRandomCardInCombat(bc.cardRandomRng, bc.player.cc, type);
        }

        for (int i = 0; i < count; ++i) {
            CardInstance card(ids[i], false);
            card.cost = 0;
            card.costForTurn = 0;

            bc.cards.createTempCardShuffledIntoDrawPile(bc.cardRandomRng, card);
        }
    }

void ActData_DiscoveryAction::operator()(BattleContext &bc) const {
        bc.haveUsedDiscoveryAction = true;
        bc.openDiscoveryScreen(sts::generateDiscoveryCards(bc.cardRandomRng, bc.player.cc, type), amount);
        bc.cardSelectInfo.canPickZero = type == CardType::ATTACK || type == CardType::SKILL || type == CardType::POWER;
    }

void ActData_InfernalBladeAction::operator()(BattleContext &bc) const {
        const auto cid = getTrulyRandomCardInCombat(bc.cardRandomRng, bc.player.cc, CardType::ATTACK);
        CardInstance c(cid);
        c.setCostForTurn(0);
        bc.addToTop( Actions::MakeTempCardInHand(c) );
    }

void ActData_JackOfAllTradesAction::operator()(BattleContext &bc) const {
        const auto c1 = sts::getTrulyRandomColorlessCardInCombat(bc.cardRandomRng);
        bc.addToTop( Actions::MakeTempCardInHand(c1) );
        if (upgraded) {
            auto c2 = sts::getTrulyRandomColorlessCardInCombat(bc.cardRandomRng);
            bc.addToTop( Actions::MakeTempCardInHand(c2) );
        }
    }

void ActData_TransmutationAction::operator()(BattleContext &bc) const {
        const auto effectAmount = energy + (bc.player.hasRelic<R::CHEMICAL_X>() ? 2 : 0);

        if (effectAmount == 0) {
            return;
        }

        const Random rolls = bc.cardRandomRng;
        for (int i = 0; i < effectAmount; ++i) {
            sts::getTrulyRandomColorlessCardInCombat(bc.cardRandomRng);
        }
        bc.addToBot( Actions::TransmutationCardsInHand(rolls, effectAmount, upgraded) );

       if (useEnergy) {
           bc.player.useEnergy(bc.player.energy);
       }
    }

void ActData_ViolenceAction::operator()(BattleContext &bc) const {
        // The draw pile is unbounded (search rollouts can grow it past 64
        // attacks), so the index list must not have a fixed capacity.
        std::vector<int> attackIdxList;
        attackIdxList.reserve(bc.cards.drawPile.size());
        for (int i = 0; i < bc.cards.drawPile.size(); ++i) {
            const auto &c = bc.cards.drawPile[i];
            if (c.getType() == CardType::ATTACK) {

                if (attackIdxList.empty()) {
                    attackIdxList.push_back(i);
                } else {
                    const auto randomIdx = bc.cardRandomRng.random(static_cast<int>(attackIdxList.size()) - 1);
                    attackIdxList.insert(attackIdxList.begin() + randomIdx, i);
                }
            }
        }

        if (attackIdxList.empty()) {
            return;
        }

        int removeIdxs[4];
        // hack to do this faster: the attackList is just pushed forward by i so we skip removing from bottom
        int i = 0;
        for (; i < count; ++i) {
            if (static_cast<int>(attackIdxList.size())-i <= 0) {
                return;
            }

            java::Collections::shuffle(attackIdxList.begin()+i, attackIdxList.end(), java::Random(bc.shuffleRng.randomLong()));
            const auto removeIdx = attackIdxList[i];
            removeIdxs[i] = removeIdx;

            const auto &c = bc.cards.drawPile[removeIdx];
            if (bc.cards.cardsInHand == 10) {
                bc.cards.moveToDiscardPile(c);
            } else {
                bc.cards.moveToHand(c);
            }
        }

        std::sort(removeIdxs, removeIdxs+i);
        for (int x = i-1; x >= 0; --x) {
            const auto drawPileRemoveIdx = removeIdxs[x];
            bc.cards.removeFromDrawPileAtIdx(drawPileRemoveIdx);
        }

    }

void ActData_BetterDiscardPileToHandAction::operator()(BattleContext &bc) const {
        if (bc.cards.discardPile.empty()) {
            return;
        }
        if (bc.cards.discardPile.size() == 1) {
            const int idx = 0;
            bc.chooseDiscardToHandCard(0, task==CardSelectTask::LIQUID_MEMORIES_POTION);
        } else {
            bc.openSimpleCardSelectScreen(task, 1);
        }
    }

void ActData_ArmamentsAction::operator()(BattleContext &bc) const {
        int canUpgradeCount = 0;
        int lastUpgradeIdx = 0;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            if (bc.cards.hand[i].canUpgrade()) {
                ++canUpgradeCount;
                lastUpgradeIdx = i;
            }
        }

        if (canUpgradeCount == 0) {
            // do nothing

        } else if (canUpgradeCount == 1) {
            bc.cards.hand[lastUpgradeIdx].upgrade();

        } else {
            bc.openSimpleCardSelectScreen(CardSelectTask::ARMAMENTS, 1);
        }
    }

void ActData_DualWieldAction::operator()(BattleContext &bc) const {

//        fixed_list<CardInstance, 10> validCards;
//        fixed_list<CardInstance, 10> invalidCards;
//
//        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
//            const bool valid = bc.cards.hand[i].getType() == CardType::ATTACK || bc.cards.hand[i].getType() == CardType::POWER;
//            if (valid) {
//                validCards.push_back(bc.cards.hand[i]);
//
//            } else {
//                invalidCards.push_back(bc.cards.hand[i]);
//            }
//        }

        int validCount = 0;
        int lastValidIdx = 0;

        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            const bool valid = bc.cards.hand[i].getType() == CardType::ATTACK || bc.cards.hand[i].getType() == CardType::POWER;
            if (valid) {
                ++validCount;
                lastValidIdx = i;
            }
        }

        if (validCount == 0) {
            return;
        }

        if (validCount == 1) {
            for (int i = 0; i < copyCount; ++i) {
                auto c = bc.cards.hand[lastValidIdx];
                if (bc.cards.cardsInHand + 1 <= CardManager::MAX_HAND_SIZE) {
                    bc.cards.createTempCardInHand(c);

                } else {
                    bc.cards.createTempCardInDiscard(c);

                }
            }

        } else {
            bc.inputState = InputState::CARD_SELECT;
            bc.cardSelectInfo.cardSelectTask = CardSelectTask::DUAL_WIELD;
            bc.cardSelectInfo.dualWield_CopyCount() = copyCount;

        }


    }

void ActData_ExhumeAction::operator()(BattleContext &bc) const {
        if (bc.cards.exhaustPile.empty() || bc.cards.cardsInHand == 10) {
            return;
        }

        int nonExhumeCards = 0;
        int lastNonExhumeIdx = -1;
        for (int i = 0; i < bc.cards.exhaustPile.size(); ++i) {
            if (bc.cards.exhaustPile[i].id != CardId::EXHUME) {
                ++nonExhumeCards;
                lastNonExhumeIdx = i;
            }
        }

        if (nonExhumeCards == 0) {
            return;

        } else if (nonExhumeCards == 1) {
            bc.chooseExhumeCard(lastNonExhumeIdx);

        } else {
            bc.cardSelectInfo.cardSelectTask = CardSelectTask::EXHUME;
            bc.inputState = InputState::CARD_SELECT;
        }

    }

void ActData_ForethoughtAction::operator()(BattleContext &bc) const {
        if (bc.cards.cardsInHand == 0) return;
        if (!upgraded && bc.cards.cardsInHand == 1) {
            bc.chooseForethoughtCard(0);
            return;
        }
        bc.openSimpleCardSelectScreen(CardSelectTask::FORETHOUGHT, upgraded ? 99 : 1);
        bc.cardSelectInfo.canPickAnyNumber = upgraded;
        bc.cardSelectInfo.canPickZero = upgraded;
    }

void ActData_HeadbuttAction::operator()(BattleContext &bc) const {
        if (bc.cards.discardPile.empty()) {
            return;

        } else if (bc.cards.discardPile.size() == 1) {
            bc.chooseHeadbuttCard(0);
        } else {
            bc.openSimpleCardSelectScreen(CardSelectTask::HEADBUTT, 1);
        }
    }

void ActData_ChooseExhaustOne::operator()(BattleContext &bc) const {
        if (bc.cards.cardsInHand == 0) {
            return;

        } else if (bc.cards.cardsInHand == 1) {
            bc.chooseExhaustOneCard(0);

        } else {
            bc.openSimpleCardSelectScreen(CardSelectTask::EXHAUST_ONE, 1);

        }
    }

void ActData_DrawToHandAction::operator()(BattleContext &bc) const {
        int count = 0;
        int idx = 0;

        for (int i = 0; i < bc.cards.drawPile.size(); ++i) {
            const auto &c = bc.cards.drawPile[i];
            if (c.getType() == cardType) {
                if (count > 0) {
                    // for keeping rng consistent with game
                    // the game creates a temporary list with the skills
                    bc.cardRandomRng.random(count - 1);
                }
                idx = i;
                ++count;
            }
        }

        if (count == 0) {
            return;
        }

        if (count == 1) {
            bc.chooseDrawToHandCards(&idx, 1);

        } else {
            bc.cardSelectInfo.cardSelectTask = task;
            bc.inputState = InputState::CARD_SELECT;
        }

    }

void ActData_WarcryAction::operator()(BattleContext &bc) const {
        // todo if the handSize equals or less than the cardsToChoose just choose them here
        if (bc.cards.cardsInHand == 0) {
            return;
        }

        if (bc.cards.cardsInHand == 1) {
            bc.cardRandomRng.random(1);
            bc.chooseWarcryCard(0);

        } else {
            bc.inputState = InputState::CARD_SELECT;
            bc.cardSelectInfo.cardSelectTask = CardSelectTask::WARCRY;
        }
    }

void ActData_TimeEaterPlayCardQueueItem::operator()(BattleContext &bc) const {
        auto item = x;
        item.exhaustOnUse |= item.card.doesExhaust();
        item.triggerOnUse = false;
        bc.curCardQueueItem = item;
        bc.onAfterUseCard();

    }

void ActData_UpgradeAllCardsInHand::operator()(BattleContext &bc) const {
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            bc.cards.hand[i].upgrade();
        }
    }

void ActData_EssenceOfDarkness::operator()(BattleContext &bc) const {
        // orb system is not implemented; no-op
    }

void ActData_IncreaseOrbSlots::operator()(BattleContext &bc) const {
        // orb system is not implemented; no-op
    }

void ActData_SuicideAction::operator()(BattleContext &bc) const {
        auto &m = bc.monsters.arr[monsterIdx];
        if (triggerRelics) {
            if (m.isAlive()) {
                m.damage(bc, m.curHp);
            }
        } else {
            bc.monsters.arr[monsterIdx].suicideAction(bc);
        }
    }

void ActData_PoisonLoseHpAction::operator()(BattleContext &bc) const {
        Monster &m = bc.monsters.arr[monsterIdx];
        if (m.isDeadOrEscaped() || !m.hasStatus<MS::POISON>()) {
            return;
        }
        // poison damage ignores block (DamageType.THORNS in the original game)
        m.damageUnblockedHelper(bc, m.getStatus<MS::POISON>());
        m.decrementStatus<MS::POISON>();
        bc.checkCombat();
    }

void ActData_RemovePlayerDebuffs::operator()(BattleContext &bc) const {
        bc.player.removeDebuffs();
    }

void ActData_UpgradeRandomCardAction::operator()(BattleContext &bc) const {
        fixed_list<int,10> upgradeableHandIdxs;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            if (bc.cards.hand[i].canUpgrade()) {
                upgradeableHandIdxs.push_back(i);
            }
        }

        if (upgradeableHandIdxs.empty()) {
            return;
        }

        java::Collections::shuffle(
                upgradeableHandIdxs.begin(),
                upgradeableHandIdxs.end(),
                java::Random(bc.shuffleRng.randomLong())
        );

        const auto upgradeIdx = upgradeableHandIdxs[0];
        bc.cards.hand[upgradeIdx].upgrade();
    }

void ActData_CodexAction::operator()(BattleContext &bc) const {
        bc.inputState = InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::CODEX;
        bc.cardSelectInfo.canPickZero = true;
        bc.cardSelectInfo.canPickAnyNumber = false;
        bc.cardSelectInfo.pickCount = 1;
        bc.cardSelectInfo.data0 = 0;
        bc.cardSelectInfo.setCostToZero = false;
        bc.cardSelectInfo.drawAfter = 0;
        bc.cardSelectInfo.drawsAfter.clear(); bc.cardSelectInfo.blocksAfter.clear(); bc.cardSelectInfo.damageAllBeforeBlocks = 0;
        bc.cardSelectInfo.codexCards() =
                generateDiscoveryCards(bc.cardRandomRng, CharacterClass::IRONCLAD, CardType::INVALID);
    }

void ActData_ExhaustMany::operator()(BattleContext &bc) const {
        bc.inputState = InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::EXHAUST_MANY;
        bc.cardSelectInfo.pickCount = limit;
    }

void ActData_GambleAction::operator()(BattleContext &bc) const {
        bc.inputState = InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::GAMBLE;
    }

void ActData_ToolboxAction::operator()(BattleContext &bc) const {
        bc.inputState = InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = CardSelectTask::DISCOVERY;
        bc.cardSelectInfo.discovery_CopyCount() = 1;
        bc.cardSelectInfo.pickCount = 1;
        bc.cardSelectInfo.canPickZero = false;
        bc.cardSelectInfo.canPickAnyNumber = false;
        bc.cardSelectInfo.setCostToZero = false;
        bc.cardSelectInfo.drawAfter = 0;
        bc.cardSelectInfo.drawsAfter.clear(); bc.cardSelectInfo.blocksAfter.clear(); bc.cardSelectInfo.damageAllBeforeBlocks = 0;
        bc.cardSelectInfo.discovery_Cards() =
                generateDiscoveryCards(bc.cardRandomRng, bc.player.cc, CardType::STATUS); // status is mapped to colorless
    }

void ActData_DualityAction::operator()(BattleContext &bc) const {
        bc.player.buff<PS::DEXTERITY>(1);
        bc.player.debuff<PS::LOSE_DEXTERITY>(1);
    }

void ActData_ApotheosisAction::operator()(BattleContext &bc) const {

        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            auto &c = bc.cards.hand[i];
            if (c.canUpgrade()) {
                c.upgrade();
            }
        }

        bc.cards.drawPile.mutateAll([](CardInstance &c) {
            if (c.canUpgrade()) {
                c.upgrade();
            }
        });

        for (auto &c : bc.cards.discardPile) {
            if (c.canUpgrade()) {
                c.upgrade();
            }
        }

        for (auto &c : bc.cards.exhaustPile) {
            if (c.canUpgrade()) {
                c.upgrade();
            }
        }
    }

void ActData_DropkickAction::operator()(BattleContext &bc) const {
        if (bc.monsters.arr[targetIdx].isTargetable() && bc.monsters.arr[targetIdx].hasStatus<MS::VULNERABLE>()) {
            bc.addToTop(Actions::DrawCards(1));
            bc.addToTop(Actions::GainEnergy(1));
        }

        const auto &c = bc.curCardQueueItem.card;
        const int damage = bc.calculateCardDamage(c, targetIdx, c.isUpgraded() ? 8 : 5);
        bc.addToTop(Actions::AttackEnemy(targetIdx, damage));
    }

void ActData_EnlightenmentAction::operator()(BattleContext &bc) const {
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            auto &c = bc.cards.hand[i];
            if (c.costForTurn > 1) {
                c.costForTurn = 1;
            }
            if (upgraded && c.cost > 1) {
                c.costForTurn = 1;
                c.cost = 1;
            }
        }
    }

void ActData_EntrenchAction::operator()(BattleContext &bc) const {
        bc.player.gainBlock(bc, bc.player.block);
    }

void ActData_FeedAction::operator()(BattleContext &bc) const {
        auto &m = bc.monsters.arr[idx];
        if (m.isDeadOrEscaped()) {
            return;
        }
        bc.monsters.arr[idx].attacked(bc, damage);

        const bool effectTriggered = !m.hasStatus<MS::MINION>()
                && !m.isAlive()
                && !m.isHalfDead()
                && !(m.hasStatus<MS::REGROW>() && bc.monsters.monstersAlive > 0);

        if (effectTriggered) {
            bc.player.increaseMaxHp(upgraded ? 4 : 3);
        }

        bc.checkCombat();
    }

void ActData_FiendFireAction::operator()(BattleContext &bc) const {
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            bc.addToTop(Actions::AttackEnemy(targetIdx, calculatedDamage));
        }

        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            bc.addToTop( Actions::ExhaustRandomCardInHand(1) );
        }
    }

void ActData_HandOfGreedAction::operator()(BattleContext &bc) const {
        auto &m = bc.monsters.arr[idx];
        if (m.isDeadOrEscaped()) {
            return;
        }
        bc.monsters.arr[idx].damage(bc, damage);

        const bool effectTriggered = !m.hasStatus<MS::MINION>()
                && !m.isAlive()
                && !m.isHalfDead()
                && !(m.hasStatus<MS::REGROW>() && bc.monsters.monstersAlive > 0);

        if (effectTriggered) {
            bc.player.gainGold(bc, upgraded ? 25 : 20);
        }

        bc.checkCombat();
    }

void ActData_LimitBreakAction::operator()(BattleContext &bc) const {
        bc.player.buff<PS::STRENGTH>(bc.player.getStatus<PS::STRENGTH>());
    }

void ActData_ReaperAction::operator()(BattleContext &bc) const {

        int healAmount = 0;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            auto &m = bc.monsters.arr[i];
            if (m.isDeadOrEscaped()) {
                continue;
            }
            int preDamageHp = m.curHp;
            m.attacked(bc, bc.calculateCardDamage(bc.curCardQueueItem.card, i, baseDamage));
            healAmount += preDamageHp-m.curHp;
        }

        if (healAmount > 0) {
            bc.addToBot( Actions::HealPlayer(healAmount) );
        }

        //if (AbstractDungeon.getCurrRoom().monsters.areMonstersBasicallyDead()) {
        //                AbstractDungeon.actionManager.clearPostCombatActions();
        //            }
    }

void ActData_RitualDaggerAction::operator()(BattleContext &bc) const {
        auto &m = bc.monsters.arr[idx];
        if (m.isDeadOrEscaped()) {
            return;
        }
        bc.monsters.arr[idx].attacked(bc, damage);

        const bool shouldUpgrade = !m.hasStatus<MS::MINION>()
                                   && !m.isAlive()
                                   && !(m.hasStatus<MS::REGROW>() && bc.monsters.monstersAlive > 0);
        if (shouldUpgrade) {
            auto &c = bc.curCardQueueItem.card;
            const auto upgradeAmt = c.isUpgraded() ? 5 : 3;

            if (bc.curCardQueueItem.purgeOnUse) {
                bc.cards.findAndUpgradeSpecialData(c.uniqueId, upgradeAmt);
            }
            c.specialData += upgradeAmt;
        }

        bc.checkCombat();
    }

void ActData_SecondWindAction::operator()(BattleContext &bc) const {
        int cardIdxsToExhaust[10];
        int toExhaustCount = 0;

        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            const auto &c = bc.cards.hand[i];
            if (c.getType() != CardType::ATTACK) {
                cardIdxsToExhaust[toExhaustCount++] = i;
                bc.addToTop( Actions::GainBlock(blockPerCard) );
            }
        }

        for (int i = 0; i < toExhaustCount; ++i) {
            const auto handIdx = cardIdxsToExhaust[i];
            const auto &c = bc.cards.hand[handIdx];

            bc.addToTop( Actions::ExhaustSpecificCardInHand(handIdx, c.uniqueId) );
        }
    }

void ActData_SeverSoulExhaustAction::operator()(BattleContext &bc) const {
        for (int i = bc.cards.cardsInHand-1; i >= 0; --i) {
            const auto &c = bc.cards.hand[i];
            if (c.getType() != CardType::ATTACK) {
                bc.addToBot( Actions::ExhaustSpecificCardInHand(i, c.getUniqueId()) );
            }
        }
    }

void ActData_SwordBoomerangAction::operator()(BattleContext &bc) const {
        const static CardInstance swordBoomerang {CardId::SWORD_BOOMERANG};
        const auto idx = bc.monsters.getRandomMonsterIdx(bc.cardRandomRng, true);
        if (idx == -1) {
            return;
        }

        int damage = bc.calculateCardDamage(swordBoomerang, idx, baseDamage);
        bc.addToTop(Actions::AttackEnemy(idx, damage));
    }

void ActData_SpotWeaknessAction::operator()(BattleContext &bc) const {
        // Spot Weakness queries the current intent. Under Runic Dome this is
        // an epistemic materialization point just like the monster acting.
        // The observer captures the now-public move before isAttacking reads
        // it; no simulator decision or RNG stream is affected.
        auto &monster = bc.monsters.arr[target];
        monster.materializePendingMove(bc);
        search::emitHiddenMonsterIntentMaterialized(
            monster.idx, static_cast<std::int16_t>(monster.moveHistory[0]),
            static_cast<std::int16_t>(monster.moveHistory[1]), monster.miscInfo);
        if (bc.monsters.arr[target].isAttacking()) {
            bc.player.buff<PS::STRENGTH>(strength);
        }
    }

void ActData_WhirlwindAction::operator()(BattleContext &bc) const {
        // assume bc.curCard is the card being used

        if (useEnergy) {
            bc.player.useEnergy(bc.player.energy);
        }

        DamageMatrix damageMatrix {0};
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            if (!bc.monsters.arr[i].isDeadOrEscaped()) {
                const auto calcDamage = bc.calculateCardDamage(bc.curCardQueueItem.card, i, baseDamage);

                damageMatrix[i] = static_cast<std::uint16_t>( // fit damage into uint16
                    std::min(
                        static_cast<int>(std::numeric_limits<std::uint16_t>::max()),
                        calcDamage
                    )
                );
            }
        }

        const auto effectAmount = energy + (bc.player.hasRelic<R::CHEMICAL_X>() ? 2 : 0);
        if (effectAmount > 0) {
            Actions::AttackAllMonsterRecursive(damageMatrix, effectAmount)(bc);
        }
    }

void ActData_AttackAllMonsterRecursive::operator()(BattleContext &bc) const {
        if (timesRemaining <= 0) {
            return;
        }

        Actions::AttackAllEnemy(matrix)(bc);

        if (timesRemaining > 1) {
            bc.addToTop(Actions::AttackAllMonsterRecursive(matrix, timesRemaining-1)); // todo should this be to the top? test with
        }
    }
