#include "sim/search/SilverUselessAction.h"
#include "combat/BattleContextBinary.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SearchRng.h"

namespace sts::search {
SilverUselessProof proveSilverUselessBlock(const BattleContext &before, const Action &action) {
    SilverUselessProof proof;
    const auto reject = [&](const char *reason) { proof.reason = reason; return proof; };
    if (before.outcome != Outcome::UNDECIDED || before.inputState != InputState::PLAYER_NORMAL
        || before.endTurnQueued || before.turnHasEnded || before.actionQueue.size || before.cardQueue.size
        || before.haveUsedDiscoveryAction || before.intentsHidden || !before.cards.drawPile.isConcrete()) return reject("not_concrete_quiet_root");
    if (action.getActionType() != ActionType::CARD || before.cards.cardsInHand != 1
        || action.getSourceIdx() != 0 || before.cards.hand[0].id != CardId::DEFEND_RED
        || before.potionCount != 0) return reject("outside_last_defend_no_potions_class");
    if (!action.isValidAction(before) || before.cards.hand[0].costForTurn <= 0)
        return reject("not_energy_spending_legal_defend");
    if (before.player.statusBits0 || before.player.statusBits1 || !before.player.statusMap.empty())
        return reject("player_power_or_status");
    // High precision: permit only the starter relic, which has no card-play or
    // end-turn hook. New relic classes require separate mechanical evidence.
    Player relicMask;
    relicMask.setHasRelic<RelicId::BURNING_BLOOD>(true);
    if ((before.player.relicBits0 & ~relicMask.relicBits0)
        || (before.player.relicBits1 & ~relicMask.relicBits1)) return reject("unqualified_relic");
    for (int i = 0; i < before.monsters.monsterCount; ++i)
        if (!before.monsters.arr[i].isDeadOrEscaped() && before.monsters.arr[i].isAttacking())
            return reject("incoming_attack");
    if (before.loopCount >= 900000 || before.turn >= 500 || before.undefinedBehaviorEvoked)
        return reject("safety_boundary");

    // Never let copied diagnostic actions update the live observer or leave a
    // dangling debug-state pointer. Neither branch can influence the decision.
    struct ObserverScope {
        CombatKnowledgeObserver *observer = g_combatKnowledgeObserver;
        BattleContext *debug = g_debug_bc;
        ObserverScope() { g_combatKnowledgeObserver = nullptr; }
        ~ObserverScope() { g_combatKnowledgeObserver = observer; g_debug_bc = debug; }
    } scope;
    BattleContext played = before, ended = before;
    action.execute(played);
    proof.energySpent = before.player.energy - played.player.energy;
    proof.blockGained = played.player.block - before.player.block;
    if (played.outcome != Outcome::UNDECIDED || played.inputState != InputState::PLAYER_NORMAL
        || played.turn != before.turn || played.cards.cardsInHand || played.potionCount
        || proof.energySpent <= 0 || proof.blockGained <= 0
        || played.player.curHp != before.player.curHp || !(played.monsters == before.monsters)
        || !(captureSearchRng(played) == captureSearchRng(before))) return reject("play_has_other_effect");
    const Action endTurn(ActionType::END_TURN);
    endTurn.execute(played);
    endTurn.execute(ended);
    if (played.outcome != Outcome::UNDECIDED || ended.outcome != Outcome::UNDECIDED
        || played.inputState != InputState::PLAYER_NORMAL || ended.inputState != InputState::PLAYER_NORMAL
        || played.turn != before.turn + 1 || ended.turn != played.turn)
        return reject("not_same_next_turn_boundary");
    proof.energyWasteDelta = played.energyWasted - ended.energyWasted;
    proof.extraLoopSteps = played.loopCount - ended.loopCount;
    // Preserve every ordered pile, Player/Monster field and all six RNG streams
    // through operator==. Only bookkeeping is normalized: more loop steps can
    // only bring the played branch closer to the loss guard; energyWasted feeds
    // Silver's heuristic but has no gameplay effect. Report both differences.
    if (proof.extraLoopSteps < 0) return reject("comparator_has_less_loop_headroom");
    played.loopCount = ended.loopCount;
    played.energyWasted = ended.energyWasted;
    if (!(played == ended)) return reject("continuation_not_identical");

    proof.snapshot = serializeBattleContext(before);
    auto restored = deserializeBattleContext(proof.snapshot.data(), proof.snapshot.size());
    if (!restored.equalForSearch(before) || !(restored.cards == before.cards)
        || !(captureSearchRng(restored) == captureSearchRng(before))) {
        proof.snapshot.clear();
        return reject("snapshot_not_replayable");
    }
    proof.verified = true;
    proof.reason = "frozen_state_forced_end_turn_equivalent";
    return proof;
}
}
