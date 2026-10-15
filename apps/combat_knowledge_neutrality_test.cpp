// Whole-combat proof that a default-off knowledge observer is non-mutating.
#include <iostream>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/CombatKnowledge.h"

namespace {

void installDeck(sts::GameContext &gc) {
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.obtainRaw(sts::Card(sts::CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.obtainRaw(sts::Card(sts::CardId::DEFEND_RED));
    gc.deck.obtainRaw(sts::Card(sts::CardId::BASH));
}

void seedGuardedCombat(sts::BattleContext &bc) {
    bc.inputState = sts::InputState::PLAYER_NORMAL;
    bc.cards.cardsInHand = 1;
    bc.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    bc.cards.hand[0].uniqueId = 100;
    bc.cards.drawPile.clear();
    for (int i = 0; i < 9; ++i) {
        sts::CardInstance c((i % 2) ? sts::CardId::DEFEND_RED : sts::CardId::STRIKE_RED);
        c.uniqueId = static_cast<std::int16_t>(101 + i);
        bc.cards.drawPile.concreteCards().push_back(c);
    }
}

bool sameCard(const sts::CardInstance &a, const sts::CardInstance &b) {
    return a.id == b.id && a.uniqueId == b.uniqueId && a.specialData == b.specialData
        && a.cost == b.cost && a.costForTurn == b.costForTurn && a.upgraded == b.upgraded
        && a.freeToPlayOnce == b.freeToPlayOnce && a.retain == b.retain;
}

bool sameRng(const sts::Random &a, const sts::Random &b) {
    // The observer must not consume a live stream. Counter equality is the
    // relevant non-timing guard; seed representation is initialization detail.
    return a.counter == b.counter;
}

bool sameLive(const sts::BattleContext &a, const sts::BattleContext &b) {
    if (a.outcome != b.outcome || a.inputState != b.inputState || a.turn != b.turn
            || a.monsterTurnIdx != b.monsterTurnIdx || a.player.curHp != b.player.curHp
            || a.player.maxHp != b.player.maxHp || a.player.energy != b.player.energy
            || a.player.block != b.player.block || a.cards.cardsInHand != b.cards.cardsInHand
            || a.cards.drawPile.size() != b.cards.drawPile.size()
            || a.cards.discardPile.size() != b.cards.discardPile.size()
            || a.cards.exhaustPile.size() != b.cards.exhaustPile.size()
            || !sameRng(a.aiRng, b.aiRng) || !sameRng(a.cardRandomRng, b.cardRandomRng)
            || !sameRng(a.miscRng, b.miscRng) || !sameRng(a.monsterHpRng, b.monsterHpRng)
            || !sameRng(a.potionRng, b.potionRng) || !sameRng(a.shuffleRng, b.shuffleRng)) return false;
    for (int i = 0; i < a.cards.cardsInHand; ++i) if (!sameCard(a.cards.hand[i], b.cards.hand[i])) return false;
    for (std::size_t i = 0; i < a.cards.drawPile.size(); ++i) if (!sameCard(a.cards.drawPile[i], b.cards.drawPile[i])) return false;
    for (std::size_t i = 0; i < a.cards.discardPile.size(); ++i) if (!sameCard(a.cards.discardPile[i], b.cards.discardPile[i])) return false;
    for (int i = 0; i < a.monsters.monsterCount; ++i) {
        const auto &x = a.monsters.arr[i]; const auto &y = b.monsters.arr[i];
        // Intent history is hidden runtime state and outside the observer's
        // non-timing neutrality contract; compare observable combat values.
        if (x.id != y.id || x.curHp != y.curHp || x.maxHp != y.maxHp || x.block != y.block
                || x.miscInfo != y.miscInfo) return false;
    }
    return true;
}

} // namespace

int main() {
    using namespace sts;
    GameContext gc(CharacterClass::IRONCLAD, 0xC011EC7u, 0);
    installDeck(gc);
    gc.info.encounter = MonsterEncounter::CULTIST;
    BattleContext baseline, observed;
    baseline.init(gc, MonsterEncounter::CULTIST);
    observed.init(gc, MonsterEncounter::CULTIST);
    seedGuardedCombat(baseline);
    seedGuardedCombat(observed);
    search::CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(observed);
    auto *previous = search::g_combatKnowledgeObserver;
    search::g_combatKnowledgeObserver = &knowledge;

    bool ok = true;
    bool stateMismatch = false;
    int executed = 0;
    for (int steps = 0; steps < 64 && baseline.outcome == Outcome::UNDECIDED; ++steps) {
        search::Action chosen(search::ActionType::END_TURN);
        if (baseline.inputState == InputState::PLAYER_NORMAL) {
            bool found = false;
            for (int cardIdx = 0; cardIdx < baseline.cards.cardsInHand && !found; ++cardIdx) {
                for (int target = 0; target < baseline.monsters.monsterCount; ++target) {
                    const search::Action candidate(search::ActionType::CARD, cardIdx, target);
                    if (candidate.isValidAction(baseline)) { chosen = candidate; found = true; break; }
                }
            }
        } else if (baseline.inputState == InputState::CARD_SELECT) {
            const auto actions = search::Action::enumerateCardSelectActions(baseline);
            if (actions.empty()) { ok = false; break; }
            chosen = actions.front();
        }
        if (!chosen.isValidAction(baseline) || !chosen.isValidAction(observed)) { ok = false; break; }
        chosen.execute(baseline);
        chosen.execute(observed);
        knowledge.reconcilePublicDrawPileCardinality(observed);
        ++executed;
        if (!sameLive(baseline, observed)) {
            stateMismatch = true;
            if (executed == 1) {
                std::cerr << "first mismatch: turns " << baseline.turn << '/' << observed.turn
                          << " input " << static_cast<int>(baseline.inputState) << '/' << static_cast<int>(observed.inputState)
                          << " hp " << baseline.player.curHp << '/' << observed.player.curHp
                          << " energy " << baseline.player.energy << '/' << observed.player.energy
                          << " hand " << baseline.cards.cardsInHand << '/' << observed.cards.cardsInHand
                          << " draw " << baseline.cards.drawPile.size() << '/' << observed.cards.drawPile.size()
                          << " discard " << baseline.cards.discardPile.size() << '/' << observed.cards.discardPile.size()
                          << '\n';
            }
        }
    }
    search::g_combatKnowledgeObserver = previous;
    const bool sawKnowledgeEvent = knowledge.eventCounts[static_cast<int>(search::CombatKnowledgeEventType::DRAW_OCCURRED)] > 0;
    if (!ok || stateMismatch || baseline.outcome == Outcome::UNDECIDED || observed.outcome != baseline.outcome
            || !sawKnowledgeEvent || knowledge.consistencyFailureCount != 0) {
        std::cerr << "combat_knowledge_neutrality FAIL outcome=" << static_cast<int>(baseline.outcome)
                  << " draws=" << knowledge.eventCounts[static_cast<int>(search::CombatKnowledgeEventType::DRAW_OCCURRED)]
                  << " failures=" << knowledge.consistencyFailureCount
                  << " last-event=" << static_cast<int>(knowledge.lastEvent)
                  << " executed=" << executed << " input=" << static_cast<int>(baseline.inputState)
                  << " energy=" << baseline.player.energy << '\n';
        return 1;
    }
    std::cout << "combat_knowledge_neutrality PASS outcome=" << static_cast<int>(baseline.outcome)
              << " draws=" << knowledge.eventCounts[static_cast<int>(search::CombatKnowledgeEventType::DRAW_OCCURRED)] << '\n';
    return 0;
}
