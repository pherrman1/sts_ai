#include "sim/search/SilverDominance.h"

#include "sim/search/SearchRng.h"

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
    if (better.monsters.monsterCount != worse.monsters.monsterCount) return false;
    bool strict = false;
    for (int i = 0; i < better.monsters.monsterCount; ++i) {
        const auto &b = better.monsters.arr[i], &w = worse.monsters.arr[i];
        if (b.isAlive() != w.isAlive() || b.halfDead != w.halfDead || b.isDeadOrEscaped() != w.isDeadOrEscaped())
            return false;
        if (b.curHp > w.curHp) return false;
        strict = strict || b.curHp < w.curHp;
    }
    if (!strict) return false;
    thread_local BattleContext same;
    same = better;
    for (int i = 0; i < same.monsters.monsterCount; ++i) same.monsters.arr[i].curHp = worse.monsters.arr[i].curHp;
    return same.equalForSearch(worse);
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
                                                        const BattleContext &xa, BattleContext &scratch) {
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
    return dominatesByMonsterHp(scratch, xa) ? R::DOMINATED : R::NOT_DOMINATED;
}
