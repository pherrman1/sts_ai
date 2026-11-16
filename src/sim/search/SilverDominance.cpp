#include "sim/search/SilverDominance.h"

#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"

using namespace sts;

namespace {

    // SilverSearcher's search-only card equivalence (SilverSearcher.cpp): either copy leads to the same future.
    bool equivalentCopies(const CardInstance &lhs, const CardInstance &rhs) {
        if (lhs.id != rhs.id || lhs.upgraded != rhs.upgraded || lhs.specialData != rhs.specialData
                || lhs.cost != rhs.cost || lhs.costForTurn != rhs.costForTurn
                || lhs.freeToPlayOnce != rhs.freeToPlayOnce || lhs.retain != rhs.retain) {
            return false;
        }
        return lhs.uniqueId == rhs.uniqueId || (!lhs.usesSpecialData() && !rhs.usesSpecialData());
    }

    bool decisionReady(const BattleContext &bc) {
        return bc.outcome == Outcome::UNDECIDED && bc.inputState == InputState::PLAYER_NORMAL
            && !bc.endTurnQueued && !bc.turnHasEnded && bc.actionQueue.size == 0 && bc.cardQueue.size == 0;
    }

}

bool search::orderDominanceGuarded(const BattleContext &bc) {
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (m.isDeadOrEscaped()) continue;
        switch (m.id) {
            case MonsterId::MYSTIC:
            case MonsterId::CENTURION:
            case MonsterId::THE_CHAMP:
            case MonsterId::TIME_EATER:
                return true;
            default:
                break;
        }
    }
    return false;
}

bool search::dominatesByMonsterHp(const BattleContext &better, const BattleContext &worse) {
    return dominatesState(better, worse, DominanceCompare{});
}

namespace {

    // lastTargetedMonster is read only under Surrounded (Spire Shield and Spear: which side the player faces), so it
    // is ignored otherwise.
    // End states: the per-turn counters are reset at the next turn start, after the relics that read them
    // (Art of War: attacks; Pocketwatch: cards). Energy is recharged unless Ice Cream keeps it.
    bool endCountersIgnorable(const BattleContext &bc) {
        return !bc.player.hasRelic<RelicId::POCKETWATCH>() && !bc.player.hasRelic<RelicId::ART_OF_WAR>();
    }

    bool endEnergyIgnorable(const BattleContext &bc) {
        return !bc.player.hasRelic<RelicId::ICE_CREAM>();
    }

    void copyEndCounters(Player &to, const Player &from) {
        to.cardsPlayedThisTurn = from.cardsPlayedThisTurn;
        to.attacksPlayedThisTurn = from.attacksPlayedThisTurn;
        to.skillsPlayedThisTurn = from.skillsPlayedThisTurn;
        to.cardsDiscardedThisTurn = from.cardsDiscardedThisTurn;
        to.haveUsedNecronomiconThisTurn = from.haveUsedNecronomiconThisTurn;
    }

}

bool search::relaxGuarded(const BattleContext &bc) {
    const auto &p = bc.player;
    if (p.hasRelic<RelicId::RED_SKULL>() || p.hasRelic<RelicId::CENTENNIAL_PUZZLE>()
            || p.hasRelic<RelicId::RUNIC_CUBE>() || p.hasRelic<RelicId::SELF_FORMING_CLAY>()
            || p.hasRelic<RelicId::EMOTION_CHIP>() || p.hasRelic<RelicId::MEAT_ON_THE_BONE>()
            || p.hasStatus<PlayerStatus::STATIC_DISCHARGE>()) {
        return true;
    }
    const auto bfb = [](const CardInstance &c) { return c.id == CardId::BLOOD_FOR_BLOOD; };
    for (int i = 0; i < bc.cards.cardsInHand; ++i) if (bfb(bc.cards.hand[i])) return true;
    for (const auto &c : bc.cards.drawPile) if (bfb(c)) return true;
    for (const auto &c : bc.cards.discardPile) if (bfb(c)) return true;
    return false;
}

bool search::dominatesState(const BattleContext &better, const BattleContext &worse, DominanceCompare mode) {
    if (better.monsters.monsterCount != worse.monsters.monsterCount) return false;
    bool strict = false;
    for (int i = 0; i < better.monsters.monsterCount; ++i) {
        const auto &b = better.monsters.arr[i], &w = worse.monsters.arr[i];
        if (b.isAlive() != w.isAlive() || b.halfDead != w.halfDead || b.isDeadOrEscaped() != w.isDeadOrEscaped())
            return false;
        if (b.curHp > w.curHp) return false;
        strict = strict || b.curHp < w.curHp;
        if (mode.relax) {
            if (b.block > w.block) return false;
            strict = strict || b.block < w.block;
        }
    }
    const bool ignoreEnergy = mode.endState && endEnergyIgnorable(worse);
    if (mode.relax) {
        if (better.player.block < worse.player.block) return false;
        strict = strict || better.player.block > worse.player.block;
        if (!ignoreEnergy) {
            if (better.player.energy < worse.player.energy) return false;
            strict = strict || better.player.energy > worse.player.energy;
        }
    }
    if (!strict) return false;
    thread_local BattleContext same;
    same = better;
    for (int i = 0; i < same.monsters.monsterCount; ++i) {
        same.monsters.arr[i].curHp = worse.monsters.arr[i].curHp;
        if (mode.relax) same.monsters.arr[i].block = worse.monsters.arr[i].block;
    }
    if (mode.relax) same.player.block = worse.player.block;
    if (mode.relax || ignoreEnergy) same.player.energy = worse.player.energy;
    if (mode.endState && endCountersIgnorable(worse)) copyEndCounters(same.player, worse.player);
    if (!worse.player.hasStatus<PlayerStatus::SURROUNDED>()) same.player.lastTargetedMonster = worse.player.lastTargetedMonster;
    return same.equalForSearch(worse);
}

bool search::endOfTurnState(const BattleContext &x, BattleContext &out) {
    if (!decisionReady(x)) return false;
    out = x;
    const SearchRngState before = captureSearchRng(out);
    seedSearchRng(out, searchRandomnessBase(out));
    struct StopScope {
        StopScope() { g_stopBeforeMonsterTurn = true; }
        ~StopScope() { g_stopBeforeMonsterTurn = false; }
    } stop;
    Action(ActionType::END_TURN).execute(out);
    if (searchRngCounter(out) != 0 || out.outcome != Outcome::UNDECIDED || !out.turnHasEnded
            || out.turn != x.turn) {
        return false;
    }
    restoreSearchRng(out, before);
    return true;
}

std::size_t search::dominanceKey(const BattleContext &bc, DominanceCompare mode, BattleContext &scratch) {
    scratch = bc;
    for (int i = 0; i < scratch.monsters.monsterCount; ++i) {
        scratch.monsters.arr[i].curHp = 0;
        if (mode.relax) scratch.monsters.arr[i].block = 0;
    }
    if (mode.relax) scratch.player.block = 0;
    if (mode.relax || (mode.endState && endEnergyIgnorable(bc))) scratch.player.energy = 0;
    if (mode.endState && endCountersIgnorable(bc)) copyEndCounters(scratch.player, Player{});
    if (!bc.player.hasStatus<PlayerStatus::SURROUNDED>()) scratch.player.lastTargetedMonster = 0;
    return hashBattleState(scratch);
}

search::Action search::sameCardPlayOn(const Action &a, const BattleContext &from, const BattleContext &to) {
    if (a.getActionType() != ActionType::CARD) return Action();
    const int src = a.getSourceIdx();
    if (src < 0 || src >= from.cards.cardsInHand) return Action();
    const auto &card = from.cards.hand[src];
    int idx = -1;
    for (int i = 0; i < to.cards.cardsInHand && idx < 0; ++i)
        if (to.cards.hand[i].uniqueId == card.uniqueId && to.cards.hand[i].id == card.id) idx = i;
    for (int i = 0; i < to.cards.cardsInHand && idx < 0; ++i)
        if (equivalentCopies(to.cards.hand[i], card)) idx = i;
    if (idx < 0) return Action();
    return Action(ActionType::CARD, idx, a.getTargetIdx());
}

bool search::playDeterministicCard(BattleContext &bc, const Action &a) {
    if (a.getActionType() != ActionType::CARD || !decisionReady(bc) || !a.isValidAction(bc)) return false;
    const auto &card = bc.cards.hand[a.getSourceIdx()];
    if (card.requiresTarget() && !bc.monsters.arr[a.getTargetIdx()].isTargetable()) return false;
    const SearchRngState before = captureSearchRng(bc);
    seedSearchRng(bc, searchRandomnessBase(bc));
    a.execute(bc);
    if (searchRngCounter(bc) != 0) return false;
    restoreSearchRng(bc, before);
    return true;
}

search::OrderDominanceResult search::testOrderDominance(const BattleContext &p, const Action &b,
                                                        const BattleContext &x, const Action &a,
                                                        const BattleContext &xa, BattleContext &scratch,
                                                        bool relax) {
    using R = OrderDominanceResult;
    if (a.getActionType() != ActionType::CARD || b.getActionType() != ActionType::CARD) return R::SKIPPED;
    if (!decisionReady(xa)) return R::SKIPPED;
    const Action aAtP = sameCardPlayOn(a, x, p);
    if (aAtP.bits == Action().bits) return R::SKIPPED;
    // The card b plays must still be in hand after a, and must not be the card a plays.
    if (aAtP.getSourceIdx() == b.getSourceIdx()) return R::SKIPPED;
    scratch = p;
    if (!playDeterministicCard(scratch, aAtP)) return R::SKIPPED;
    const Action bAfterA = sameCardPlayOn(b, p, scratch);
    if (bAfterA.bits == Action().bits) return R::SKIPPED;
    if (!playDeterministicCard(scratch, bAfterA)) return R::SKIPPED;
    return dominatesState(scratch, xa, DominanceCompare{relax, false}) ? R::DOMINATED : R::NOT_DOMINATED;
}
