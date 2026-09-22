// Exact hot-path regression checks against the isolated Silver implementation.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string>
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/BattleSearcher.h"
#include "sim/search/Action.h"

// Keep the combat-only link closure consistent with SilverNativeFixtureRunner.
bool sts::GameContext::hasRelic(sts::RelicId id) const { return relics.has(id); }
int sts::Deck::size() const { return cards.size(); }

namespace {
using Search = sts::search::BattleSearcher;
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
void equalStats(const sts::search::SearchStats &a, const sts::search::SearchStats &b);
sts::BattleContext fixture(sts::GameContext &gc) {
    gc.cc = sts::CharacterClass::IRONCLAD;
    gc.seed = 0xBADC0DEu;
    gc.ascension = 0; gc.floorNum = 1; gc.act = 1;
    gc.curHp = 80; gc.maxHp = 80; gc.potionCapacity = 3;
    std::fill(gc.potions.begin(), gc.potions.end(), sts::Potion::EMPTY_POTION_SLOT);
    gc.map = std::make_shared<sts::Map>();
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::DEFEND_RED));
    gc.deck.cards.push_back(sts::Card(sts::CardId::BASH));
    sts::BattleContext bc{};
    bc.init(gc, sts::MonsterEncounter::LOOTER);
    return bc;
}

std::vector<sts::search::Action> rootActions(const sts::BattleContext &bc) {
    Search search(bc);
    search.step();
    std::vector<sts::search::Action> actions;
    actions.reserve(search.getRootEdges().size());
    for (const auto &edge : search.getRootEdges()) actions.push_back(edge.action);
    return actions;
}

std::vector<sts::search::Action> potionActions(const sts::BattleContext &bc, sts::Potion potion) {
    std::vector<sts::search::Action> result;
    for (const auto &action : rootActions(bc)) {
        if (action.getActionType() == sts::search::ActionType::POTION
                && bc.potions[action.getSourceIdx()] == potion) {
            result.push_back(action);
        }
    }
    return result;
}

void installPotions(sts::BattleContext &bc, std::initializer_list<sts::Potion> potions) {
    bc.potions.fill(sts::Potion::EMPTY_POTION_SLOT);
    bc.potionCapacity = static_cast<int>(potions.size());
    bc.potionCount = static_cast<int>(potions.size());
    std::copy(potions.begin(), potions.end(), bc.potions.begin());
}

void historicalQueueIdentityTests(const sts::BattleContext &original) {
    auto retained = original;
    auto observed = original;
    retained.curCardQueueItem.card = sts::CardInstance(sts::CardId::INFLAME);
    observed.curCardQueueItem.card = sts::CardInstance(sts::CardId::SPOT_WEAKNESS);
    require(!retained.equalForSearch(observed)
                && sts::search::hashBattleState(retained) == sts::search::hashBattleState(observed)
                && sts::search::equalForSearchIgnoringHistoricalQueueItem(retained, observed),
            "settled normal historical queue items must share Silver identity only");
    Search dedup(original);
    auto *representative = dedup.getOrCreateNode(sts::BattleContext(retained));
    require(dedup.getOrCreateNode(sts::BattleContext(observed)) == representative
                && dedup.stats.queueItemCanonicalHits == 1
                && representative->state->curCardQueueItem == retained.curCardQueueItem,
            "normal dedup must keep a stable representative and count one relaxed hit");

    const auto excluded = [&](const auto &change) {
        auto a = retained;
        auto b = observed;
        change(a); change(b);
        require(!sts::search::equalForSearchIgnoringHistoricalQueueItem(a, b),
                "pending or non-decision state must keep exact queue identity");
        Search boundary(original);
        require(boundary.getOrCreateNode(std::move(a))
                    != boundary.getOrCreateNode(std::move(b)),
                "excluded queue variants must remain distinct nodes");
    };
    excluded([](auto &s) { s.inputState = sts::InputState::EXECUTING_ACTIONS; });
    excluded([](auto &s) { s.actionQueue.pushBack(sts::Actions::GainEnergy(1)); });
    excluded([](auto &s) { s.cardQueue.pushBack(sts::CardQueueItem{}); });
    excluded([](auto &s) { s.outcome = sts::Outcome::PLAYER_VICTORY; });
    excluded([](auto &s) { s.isBattleOver = true; });
    excluded([](auto &s) { s.endTurnQueued = true; });
    excluded([](auto &s) { s.turnHasEnded = true; });
    auto energy = observed;
    ++energy.player.energy;
    require(!sts::search::equalForSearchIgnoringHistoricalQueueItem(energy, retained),
            "ordinary energy difference must remain distinct");

    auto gambleRetained = retained;
    auto gambleObserved = observed;
    installPotions(gambleRetained, {sts::Potion::GAMBLERS_BREW});
    installPotions(gambleObserved, {sts::Potion::GAMBLERS_BREW});
    const sts::search::Action gamble(sts::search::ActionType::POTION, 0, 0);
    require(gamble.isValidAction(gambleRetained), "Gambler's Brew fixture must be valid");
    gamble.execute(gambleRetained);
    gamble.execute(gambleObserved);
    require(gambleRetained.inputState == sts::InputState::CARD_SELECT
                && gambleRetained.cardSelectInfo.cardSelectTask == sts::CardSelectTask::GAMBLE
                && gambleRetained.actionQueue.size == 0 && gambleRetained.cardQueue.size == 0
                && sts::search::equalForSearchIgnoringHistoricalQueueItem(
                    gambleRetained, gambleObserved),
            "Gambler's Brew must reach equivalent quiescent selection states");
    Search selectionDedup(gambleRetained);
    auto *selectionRepresentative = selectionDedup.getOrCreateNode(
        sts::BattleContext(gambleRetained));
    require(selectionDedup.getOrCreateNode(sts::BattleContext(gambleObserved))
                == selectionRepresentative && selectionDedup.stats.queueItemCanonicalHits == 1,
            "quiescent CARD_SELECT must deduplicate by historical queue identity");
    const auto pick = rootActions(gambleRetained).front();
    require(pick.getActionType() == sts::search::ActionType::SINGLE_CARD_SELECT,
            "GAMBLE fixture must offer a card pick");
    pick.execute(gambleRetained);
    pick.execute(gambleObserved);
    require(sts::search::equalForSearchIgnoringHistoricalQueueItem(
                gambleRetained, gambleObserved),
            "reopened GAMBLE selection must remain equivalent");
    sts::search::Action confirm(sts::search::ActionType::MULTI_CARD_SELECT,
                                gambleRetained.cardSelectInfo.selectedBits);
    require(confirm.isValidAction(gambleRetained), "GAMBLE confirmation must be legal");
    confirm.execute(gambleRetained);
    confirm.execute(gambleObserved);
    require(sts::search::equalForSearchIgnoringHistoricalQueueItem(
                gambleRetained, gambleObserved),
            "GAMBLE confirmation must retain historical queue equivalence");

    auto attackRetained = retained;
    auto attackObserved = observed;
    installPotions(attackRetained, {sts::Potion::ATTACK_POTION});
    installPotions(attackObserved, {sts::Potion::ATTACK_POTION});
    sts::search::Action(sts::search::ActionType::POTION, 0, 0).execute(attackRetained);
    sts::search::Action(sts::search::ActionType::POTION, 0, 0).execute(attackObserved);
    require(attackRetained.inputState == sts::InputState::CARD_SELECT
                && attackRetained.cardSelectInfo.cardSelectTask == sts::CardSelectTask::DISCOVERY
                && sts::search::equalForSearchIgnoringHistoricalQueueItem(
                    attackRetained, attackObserved)
                && rootActions(attackRetained) == rootActions(attackObserved),
            "Attack Potion must reach equivalent quiescent Discovery selection");

    auto cardRetained = retained;
    auto cardObserved = observed;
    const auto actions = rootActions(cardRetained);
    const auto card = std::find_if(actions.begin(), actions.end(), [](const auto &a) {
        return a.getActionType() == sts::search::ActionType::CARD;
    });
    require(card != actions.end(), "fixture must have a playable card");
    card->execute(cardRetained);
    card->execute(cardObserved);
    require(cardRetained.curCardQueueItem == cardObserved.curCardQueueItem
                && cardRetained.equalForSearch(cardObserved),
            "playing a card must overwrite the historical queue item");

    auto potionRetained = retained;
    auto potionObserved = observed;
    installPotions(potionRetained, {sts::Potion::STRENGTH_POTION});
    installPotions(potionObserved, {sts::Potion::STRENGTH_POTION});
    sts::search::Action(sts::search::ActionType::POTION, 0, 0).execute(potionRetained);
    sts::search::Action(sts::search::ActionType::POTION, 0, 0).execute(potionObserved);
    require(sts::search::equalForSearchIgnoringHistoricalQueueItem(
                potionRetained, potionObserved),
            "ordinary potion use must preserve historical equivalence");

    auto turnRetained = retained;
    auto turnObserved = observed;
    sts::search::Action(sts::search::ActionType::END_TURN).execute(turnRetained);
    sts::search::Action(sts::search::ActionType::END_TURN).execute(turnObserved);
    require(sts::search::equalForSearchIgnoringHistoricalQueueItem(
                turnRetained, turnObserved),
            "ending turn must not consume the old historical card");

    auto headbutt = retained;
    headbutt.cards.hand[0] = sts::CardInstance(sts::CardId::HEADBUTT);
    headbutt.cards.hand[0].uniqueId = original.cards.hand[0].uniqueId;
    for (int i = 0; i < 2; ++i) {
        auto discarded = headbutt.cards.hand[1];
        headbutt.cards.removeFromHandAtIdx(1);
        headbutt.cards.moveToDiscardPile(discarded);
    }
    const sts::search::Action headbuttPlay(sts::search::ActionType::CARD, 0, 0);
    require(headbuttPlay.isValidAction(headbutt), "Headbutt fixture must be playable");
    headbuttPlay.execute(headbutt);
    require(headbutt.inputState == sts::InputState::CARD_SELECT
                && headbutt.cardSelectInfo.cardSelectTask == sts::CardSelectTask::HEADBUTT
                && headbutt.actionQueue.size > 0
                && !sts::search::queueItemIsHistoricalAtDecision(headbutt),
            "Headbutt selection with pending card bookkeeping must stay exact");
    auto headbuttVariant = headbutt;
    headbuttVariant.curCardQueueItem.card = sts::CardInstance(sts::CardId::SPOT_WEAKNESS);
    require(!sts::search::equalForSearchIgnoringHistoricalQueueItem(
                headbutt, headbuttVariant),
            "pending Headbutt selection must not canonicalize");
    Search headbuttDedup(original);
    require(headbuttDedup.getOrCreateNode(std::move(headbutt))
                != headbuttDedup.getOrCreateNode(std::move(headbuttVariant)),
            "pending Headbutt selection must retain separate nodes");
}

struct SameTurnPath {
    sts::BattleContext state;
    int damageToTarget = 0;
    int targetHp = 0;
    int playerHp = 0;
    int targetVulnerable = 0;
    int targetBlock = 0;
    int energy = 0;
    int handSize = 0;
    int discardSize = 0;
    int energyWasted = 0;
    int cardsDrawn = 0;
    int actionQueueSize = 0;
    int cardQueueSize = 0;
    sts::InputState inputState = sts::InputState::EXECUTING_ACTIONS;
    sts::Outcome outcome = sts::Outcome::UNDECIDED;
    std::uint64_t rngCounter = 0;
};

int handIndexForUniqueId(const sts::BattleContext &bc, std::int16_t uniqueId) {
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        if (bc.cards.hand[i].uniqueId == uniqueId) return i;
    }
    return -1;
}

bool resolveCardByIdentity(sts::BattleContext &bc, std::int16_t uniqueId, int target) {
    if (bc.inputState != sts::InputState::PLAYER_NORMAL) return false;
    const int handIdx = handIndexForUniqueId(bc, uniqueId);
    if (handIdx < 0) return false;
    const sts::search::Action action(sts::search::ActionType::CARD, handIdx, target);
    if (!action.isValidAction(bc)) return false;
    action.execute(bc);
    return true;
}

sts::BattleContext sameTurnState(sts::GameContext &gc, sts::MonsterEncounter encounter,
                                 int targetHp, int energy, bool includeReaper,
                                 bool secondMonster) {
    sts::BattleContext bc{};
    bc.init(gc, encounter);
    bc.cards.clear();
    bc.cards.cardsInHand = includeReaper ? 3 : 2;
    bc.cards.hand[0] = sts::CardInstance(sts::CardId::BASH);
    bc.cards.hand[0].setUniqueId(101);
    bc.cards.hand[1] = sts::CardInstance(sts::CardId::STRIKE_RED);
    bc.cards.hand[1].setUniqueId(102);
    if (includeReaper) {
        bc.cards.hand[2] = sts::CardInstance(sts::CardId::REAPER);
        bc.cards.hand[2].setUniqueId(103);
    }
    bc.cards.nextUniqueCardId = 200;
    bc.cards.strikeCount = 1;
    bc.player.energy = energy;
    bc.player.curHp = 50;
    bc.player.maxHp = 80;
    bc.player.block = 0;
    bc.player.cardsPlayedThisTurn = 0;
    bc.player.attacksPlayedThisTurn = 0;
    bc.player.skillsPlayedThisTurn = 0;
    bc.inputState = sts::InputState::PLAYER_NORMAL;
    bc.outcome = sts::Outcome::UNDECIDED;
    bc.isBattleOver = false;
    bc.endTurnQueued = false;
    bc.turnHasEnded = false;
    bc.actionQueue.clear();
    bc.cardQueue.clear();
    bc.monsters.arr[0].curHp = targetHp;
    bc.monsters.arr[0].maxHp = std::max(bc.monsters.arr[0].maxHp, targetHp);
    bc.monsters.arr[0].block = 0;
    bc.monsters.arr[0].vulnerable = 0;
    bc.monsters.arr[0].weak = 0;
    bc.monsters.arr[0].poison = 0;
    if (secondMonster) {
        bc.monsters.arr[1].curHp = 4;
        bc.monsters.arr[1].block = 0;
        bc.monsters.arr[1].vulnerable = 0;
        bc.monsters.arr[1].weak = 0;
        bc.monsters.arr[1].poison = 0;
        bc.monsters.monstersAlive = 2;
    }
    return bc;
}

SameTurnPath resolveSameTurnPath(const sts::BattleContext &original,
                                 std::initializer_list<std::int16_t> cardIds,
                                 int target = 0) {
    SameTurnPath path{original};
    const int originalTargetHp = original.monsters.arr[target].curHp;
    for (const auto cardId : cardIds) {
        require(resolveCardByIdentity(path.state, cardId, target),
                "same-turn path card must remain legal and resolvable by identity");
    }
    path.damageToTarget = originalTargetHp - path.state.monsters.arr[target].curHp;
    path.targetHp = path.state.monsters.arr[target].curHp;
    path.playerHp = path.state.player.curHp;
    path.targetVulnerable = path.state.monsters.arr[target].vulnerable;
    path.targetBlock = path.state.monsters.arr[target].block;
    path.energy = path.state.player.energy;
    path.handSize = path.state.cards.cardsInHand;
    path.discardSize = path.state.cards.discardPile.size();
    path.energyWasted = path.state.energyWasted;
    path.cardsDrawn = path.state.cardsDrawn;
    path.actionQueueSize = path.state.actionQueue.size;
    path.cardQueueSize = path.state.cardQueue.size;
    path.inputState = path.state.inputState;
    path.outcome = path.state.outcome;
    path.rngCounter = static_cast<std::uint64_t>(path.state.rng.counter);
    return path;
}

void sameTurnDominanceAuditFixtures(sts::GameContext &gc) {
    const auto plain = sameTurnState(gc, sts::MonsterEncounter::JAW_WORM, 100, 3, false, false);
    const auto initialRngCounter = plain.rng.counter;
    const auto bashThenStrike = resolveSameTurnPath(plain, {101, 102});
    const auto strikeThenBash = resolveSameTurnPath(plain, {102, 101});
    require(bashThenStrike.damageToTarget == 17 && strikeThenBash.damageToTarget == 14,
            "plain Bash/Strike fixture must reproduce 17 versus 14 damage");
    require(bashThenStrike.state.inputState == sts::InputState::PLAYER_NORMAL &&
                strikeThenBash.state.inputState == sts::InputState::PLAYER_NORMAL &&
                bashThenStrike.state.actionQueue.size == 0 && bashThenStrike.state.cardQueue.size == 0 &&
                strikeThenBash.state.actionQueue.size == 0 && strikeThenBash.state.cardQueue.size == 0,
            "fully resolved card paths must return to a player decision boundary");
    require(bashThenStrike.targetVulnerable == strikeThenBash.targetVulnerable &&
                bashThenStrike.targetBlock == strikeThenBash.targetBlock &&
                bashThenStrike.playerHp == strikeThenBash.playerHp &&
                bashThenStrike.energy == strikeThenBash.energy &&
                bashThenStrike.handSize == strikeThenBash.handSize &&
                bashThenStrike.discardSize == strikeThenBash.discardSize &&
                bashThenStrike.energyWasted == strikeThenBash.energyWasted &&
                bashThenStrike.cardsDrawn == strikeThenBash.cardsDrawn &&
                bashThenStrike.rngCounter == strikeThenBash.rngCounter &&
                bashThenStrike.rngCounter == static_cast<std::uint64_t>(initialRngCounter),
            "plain endpoints must match on non-damage fields");
    require(!bashThenStrike.state.equalForSearch(strikeThenBash.state) &&
                bashThenStrike.state.curCardQueueItem != strikeThenBash.state.curCardQueueItem,
            "plain Bash/Strike endpoints must expose the last-card queue-item difference");
    auto normalized = bashThenStrike.state;
    normalized.monsters.arr[0].curHp = strikeThenBash.state.monsters.arr[0].curHp;
    normalized.curCardQueueItem = strikeThenBash.state.curCardQueueItem;
    require(normalized.equalForSearch(strikeThenBash.state),
            "plain Bash/Strike differences must be target HP plus last-card queue item");
    auto omittedCounterA = plain;
    auto omittedCounterB = plain;
    omittedCounterB.energyWasted = omittedCounterA.energyWasted + 1;
    omittedCounterB.cardsDrawn = omittedCounterA.cardsDrawn + 1;
    require(omittedCounterA.equalForSearch(omittedCounterB) &&
                sts::search::hashBattleState(omittedCounterA) ==
                    sts::search::hashBattleState(omittedCounterB),
            "evaluation counters omitted from search equality must remain identified as omitted");
    std::cout << "same_turn_plain BashThenStrike_damage=" << bashThenStrike.damageToTarget
              << " StrikeThenBash_damage=" << strikeThenBash.damageToTarget
              << " hp=" << bashThenStrike.targetHp << "/" << strikeThenBash.targetHp
              << " vulnerable=" << bashThenStrike.targetVulnerable
              << " endpoint_difference=target_hp+curCardQueueItem"
              << " rng_counter=" << bashThenStrike.rngCounter
              << " omitted_eval_counters=energyWasted,cardsDrawn\n";

    const auto reaperState = sameTurnState(gc, sts::MonsterEncounter::JAW_WORM,
                                           18, 5, true, false);
    const auto reaperAfterMoreDamage = resolveSameTurnPath(reaperState, {101, 102});
    const auto reaperAfterLessDamage = resolveSameTurnPath(reaperState, {102, 101});
    require(reaperAfterMoreDamage.targetHp == 1 && reaperAfterLessDamage.targetHp == 4 &&
                reaperAfterMoreDamage.targetHp > 0 && reaperAfterLessDamage.targetHp > 0 &&
                reaperAfterMoreDamage.outcome == sts::Outcome::UNDECIDED &&
                reaperAfterLessDamage.outcome == sts::Outcome::UNDECIDED,
            "Reaper shared-continuation fixture must leave both endpoints nonterminal with the target alive");
    auto moreDamageContinuation = reaperAfterMoreDamage.state;
    auto lessDamageContinuation = reaperAfterLessDamage.state;
    require(resolveCardByIdentity(moreDamageContinuation, 103, 0) &&
                resolveCardByIdentity(lessDamageContinuation, 103, 0),
            "Reaper continuation must be legal after either same-turn path");
    require(moreDamageContinuation.outcome == sts::Outcome::PLAYER_VICTORY &&
                lessDamageContinuation.outcome == sts::Outcome::PLAYER_VICTORY &&
                moreDamageContinuation.player.curHp == 51 && lessDamageContinuation.player.curHp == 54 &&
                moreDamageContinuation.postBattleHealedHp() == 51 &&
                lessDamageContinuation.postBattleHealedHp() == 54,
            "shared Reaper continuation must reach victory and preserve distinct healing results");
    std::cout << "same_turn_reaper shared_continuation lower_hp=" << reaperAfterMoreDamage.targetHp
              << " continuation_player_hp=" << moreDamageContinuation.player.curHp
              << " higher_hp=" << reaperAfterLessDamage.targetHp
              << " continuation_player_hp=" << lessDamageContinuation.player.curHp
              << " terminal=PLAYER_VICTORY/PLAYER_VICTORY\n";

    auto boundary = sameTurnState(gc, sts::MonsterEncounter::JAW_WORM, 100, 2, false, false);
    boundary.cards.hand[0] = sts::CardInstance(sts::CardId::WARCRY);
    boundary.cards.hand[0].setUniqueId(101);
    boundary.cards.hand[2] = sts::CardInstance(sts::CardId::DEFEND_RED);
    boundary.cards.hand[2].setUniqueId(104);
    boundary.cards.cardsInHand = 3;
    require(resolveCardByIdentity(boundary, 101, 0), "WARCRY must be a legal first action");
    require(boundary.inputState == sts::InputState::CARD_SELECT &&
                !resolveCardByIdentity(boundary, 102, 0),
            "same-turn dominance must reject an intervening card-selection boundary");

    const auto insufficientEnergy = sameTurnState(gc, sts::MonsterEncounter::JAW_WORM,
                                                  100, 1, false, false);
    require(handIndexForUniqueId(insufficientEnergy, 101) >= 0,
            "insufficient-energy fixture must retain Bash ID 101 before execution");
    auto insufficientPostStrike = insufficientEnergy;
    require(resolveCardByIdentity(insufficientPostStrike, 102, 0) &&
                insufficientPostStrike.player.energy == 0,
            "insufficient-energy fixture must resolve the first Strike");
    require(handIndexForUniqueId(insufficientPostStrike, 101) >= 0 &&
                !resolveCardByIdentity(insufficientPostStrike, 101, 0),
            "same-turn dominance must reject the remaining Bash ID 101 when energy is exhausted");
    auto sufficientPostStrike = sameTurnState(gc, sts::MonsterEncounter::JAW_WORM,
                                               100, 3, false, false);
    require(resolveCardByIdentity(sufficientPostStrike, 102, 0) &&
                sufficientPostStrike.player.energy == 2 &&
                handIndexForUniqueId(sufficientPostStrike, 101) >= 0 &&
                resolveCardByIdentity(sufficientPostStrike, 101, 0),
            "sufficient-energy positive control must resolve the remaining Bash after Strike");
    std::cout << "same_turn_rejections information_boundary=CARD_SELECT"
              << " insufficient_energy=remaining_Bash_101_present_but_illegal"
              << " positive_control=energy3 PASS\n";
}

void canonicalizePotionBelt(sts::BattleContext &bc) {
    std::sort(bc.potions.begin(), bc.potions.begin() + bc.potionCapacity,
              [](sts::Potion lhs, sts::Potion rhs) {
                  return static_cast<int>(lhs) < static_cast<int>(rhs);
              });
}

void executePotion(sts::BattleContext &bc, int slot, int target = 0) {
    const sts::search::Action action(sts::search::ActionType::POTION, slot, target);
    require(action.isValidAction(bc), "potion permutation fixture action must be valid");
    action.execute(bc);
}

void potionActionCanonicalization(sts::GameContext &gc, const sts::BattleContext &original) {
    auto duplicate = original;
    installPotions(duplicate, {sts::Potion::STRENGTH_POTION, sts::Potion::EMPTY_POTION_SLOT,
                               sts::Potion::STRENGTH_POTION});
    duplicate.potionCount = 2;
    const auto noPotions = original;
    const auto noPotionActions = rootActions(noPotions);
    auto nonPotionActions = [](const std::vector<sts::search::Action> &actions) {
        std::vector<sts::search::Action> result;
        for (const auto &action : actions) {
            if (action.getActionType() != sts::search::ActionType::POTION) result.push_back(action);
        }
        return result;
    };
    require(nonPotionActions(rootActions(duplicate)) == nonPotionActions(noPotionActions),
            "duplicate potions must not change ordinary root actions");
    const auto strengthActions = potionActions(duplicate, sts::Potion::STRENGTH_POTION);
    require(strengthActions.size() == 1 && strengthActions.front().getSourceIdx() == 0,
            "duplicate non-target potion must retain only the first representative slot");

    auto targetedGc = gc;
    sts::BattleContext targeted{};
    targeted.init(targetedGc, sts::MonsterEncounter::TWO_FUNGI_BEASTS);
    installPotions(targeted, {sts::Potion::FIRE_POTION, sts::Potion::EMPTY_POTION_SLOT,
                              sts::Potion::FIRE_POTION});
    targeted.potionCount = 2;
    const auto fireActions = potionActions(targeted, sts::Potion::FIRE_POTION);
    require(fireActions.size() == 2, "duplicate targeted potion must retain both targets");
    require(fireActions[0].getSourceIdx() == 0 && fireActions[1].getSourceIdx() == 0
                && fireActions[0].getTargetIdx() != fireActions[1].getTargetIdx(),
            "targeted potion reduction must retain target alternatives on its representative slot");

    auto multiplicity = original;
    installPotions(multiplicity, {sts::Potion::STRENGTH_POTION, sts::Potion::STRENGTH_POTION,
                                 sts::Potion::STRENGTH_POTION});
    for (int expectedRemaining = 3; expectedRemaining > 0; --expectedRemaining) {
        const auto actions = potionActions(multiplicity, sts::Potion::STRENGTH_POTION);
        require(actions.size() == 1, "each remaining identical potion must have one representative action");
        require(actions.front().getSourceIdx() == 3 - expectedRemaining,
                "successive identical potion uses must retain the first occupied slot");
        executePotion(multiplicity, actions.front().getSourceIdx());
        require(multiplicity.potionCount == expectedRemaining - 1,
                "using a representative potion must consume exactly one copy");
    }
    require(potionActions(multiplicity, sts::Potion::STRENGTH_POTION).empty(),
            "all identical potion copies must eventually be consumable");

    auto differentTypes = original;
    installPotions(differentTypes, {sts::Potion::STRENGTH_POTION, sts::Potion::DEXTERITY_POTION});
    const auto strengthAndDexterity = rootActions(differentTypes);
    int strengthCount = 0, dexterityCount = 0;
    for (const auto &action : strengthAndDexterity) {
        if (action.getActionType() != sts::search::ActionType::POTION) continue;
        if (differentTypes.potions[action.getSourceIdx()] == sts::Potion::STRENGTH_POTION) ++strengthCount;
        if (differentTypes.potions[action.getSourceIdx()] == sts::Potion::DEXTERITY_POTION) ++dexterityCount;
    }
    require(strengthCount == 1 && dexterityCount == 1,
            "different potion types must retain separate representatives");

    auto fairy = original;
    installPotions(fairy, {sts::Potion::FAIRY_POTION, sts::Potion::FAIRY_POTION});
    const auto fairyActions = potionActions(fairy, sts::Potion::FAIRY_POTION);
    require(fairyActions.size() == 1 && fairyActions.front().getTargetIdx() > 5,
            "duplicate Fairy Potions must retain one discard action and no use action");

    auto blockedSmoke = original;
    blockedSmoke.encounter = sts::MonsterEncounter::HEXAGHOST;
    installPotions(blockedSmoke, {sts::Potion::SMOKE_BOMB, sts::Potion::SMOKE_BOMB});
    const auto smokeActions = potionActions(blockedSmoke, sts::Potion::SMOKE_BOMB);
    require(smokeActions.size() == 1 && smokeActions.front().getTargetIdx() > 5,
            "blocked duplicate Smoke Bombs must retain one discard action and no use action");

    auto gambler = original;
    gambler.cards.cardsInHand = 1;
    gambler.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    installPotions(gambler, {sts::Potion::GAMBLERS_BREW, sts::Potion::GAMBLERS_BREW});
    const auto usableGamblerActions = potionActions(gambler, sts::Potion::GAMBLERS_BREW);
    require(usableGamblerActions.size() == 1 && usableGamblerActions.front().getTargetIdx() <= 5,
            "duplicate Gambler's Brews with a nonempty hand must retain one use action");
    gambler.cards.cardsInHand = 0;
    require(potionActions(gambler, sts::Potion::GAMBLERS_BREW).empty(),
            "duplicate Gambler's Brews with an empty hand must remain unavailable");

    const auto permutation = [&](sts::Potion potion, int target) {
        auto stateA = original;
        auto stateB = original;
        installPotions(stateA, {potion, sts::Potion::EMPTY_POTION_SLOT, potion});
        installPotions(stateB, {potion, sts::Potion::EMPTY_POTION_SLOT, potion});
        stateA.potionCount = stateB.potionCount = 2;
        executePotion(stateA, 0, target);
        executePotion(stateB, 2, target);
        const auto rngA = stateA.rng;
        const auto rngB = stateB.rng;
        canonicalizePotionBelt(stateA);
        canonicalizePotionBelt(stateB);
        require(stateA.equalForSearch(stateB),
                "identical potion slots must produce equivalent successor search states after normalization");
        require(rngA == rngB, "identical potion slots must advance the same RNG state");
    };
    permutation(sts::Potion::STRENGTH_POTION, 0);
    permutation(sts::Potion::FIRE_POTION, 0);
    permutation(sts::Potion::ENTROPIC_BREW, 0);
}

void selection(Search &search) {
    Search::Node parent, finite, nan, negativeInfinity;
    parent.simulationCount = 20;
    finite.simulationCount = nan.simulationCount = negativeInfinity.simulationCount = 1;
    finite.evaluationSum = 3;
    nan.evaluationSum = std::numeric_limits<double>::quiet_NaN();
    negativeInfinity.evaluationSum = -std::numeric_limits<double>::infinity();
    parent.edges.resize(4);
    parent.edges[0].node = &finite; parent.edges[0].visitCount = 1;
    require(search.selectBestEdgeToSearch(parent) == 1, "first unexplored edge tie");
    parent.edges[0].node = nullptr;
    require(search.selectBestEdgeToSearch(parent) == 0, "initial infinity tie");
    parent.edges[0].node = &nan;
    require(search.selectBestEdgeToSearch(parent) == 0, "initial NaN must retain original strict-comparison behavior");
    parent.edges[0].node = &negativeInfinity;
    require(search.selectBestEdgeToSearch(parent) == 1, "negative infinity must not stop scan");
    parent.edges[0].node = &finite;
    parent.edges[1].node = &nan; parent.edges[1].visitCount = 1;
    require(search.selectBestEdgeToSearch(parent) == 2, "later NaN must not hide first infinity");
}

void cardActionCanonicalization(const sts::BattleContext &original) {
    sts::CardInstance equivalentA(sts::CardId::STRIKE_RED);
    sts::CardInstance equivalentB = equivalentA;
    equivalentA.setUniqueId(11); equivalentB.setUniqueId(22);
    require(sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "ordinary copies with different unique ids must be equivalent");
    equivalentB.costForTurn = equivalentA.costForTurn - 1;
    require(!sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "different costForTurn must remain distinct");
    equivalentB = equivalentA; equivalentB.upgraded = !equivalentA.upgraded;
    require(!sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "different upgrade state must remain distinct");
    equivalentB = equivalentA; equivalentB.freeToPlayOnce = true;
    require(!sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "different freeToPlayOnce state must remain distinct");
    equivalentB = equivalentA; equivalentB.retain = true;
    require(!sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "different retain state must remain distinct");
    equivalentB = equivalentA; equivalentB.specialData = 1;
    require(!sts::search::Action::areCardsEquivalentForSearch(equivalentA, equivalentB),
            "different specialData must remain distinct");

    auto bc = original;
    bc.cards.cardsInHand = 3;
    bc.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    bc.cards.hand[1] = sts::CardInstance(sts::CardId::DEFEND_RED);
    bc.cards.hand[2] = sts::CardInstance(sts::CardId::STRIKE_RED);
    bc.cards.hand[0].setUniqueId(101);
    bc.cards.hand[2].setUniqueId(202);

    Search search(bc);
    search.step();
    std::vector<int> strikeIndices;
    for (const auto &edge : search.getRootEdges()) {
        if (edge.action.getActionType() == sts::search::ActionType::CARD &&
            bc.cards.hand[edge.action.getSourceIdx()].id == sts::CardId::STRIKE_RED) {
            strikeIndices.push_back(edge.action.getSourceIdx());
        }
    }
    require(strikeIndices.size() == 1 && strikeIndices.front() == 0,
            "separated equivalent card plays must retain the first representative");

    auto differentiated = bc;
    differentiated.cards.hand[2].retain = true;
    Search distinct(differentiated);
    distinct.step();
    int strikeCount = 0;
    for (const auto &edge : distinct.getRootEdges()) {
        if (edge.action.getActionType() == sts::search::ActionType::CARD &&
            differentiated.cards.hand[edge.action.getSourceIdx()].id == sts::CardId::STRIKE_RED) {
            ++strikeCount;
        }
    }
    require(strikeCount == 2, "different retain state must preserve separate card plays");

    auto special = bc;
    special.cards.hand[0] = sts::CardInstance(sts::CardId::RAMPAGE);
    special.cards.hand[2] = special.cards.hand[0];
    special.cards.hand[0].setUniqueId(303);
    special.cards.hand[2].setUniqueId(404);
    Search identitySensitive(special);
    identitySensitive.step();
    int specialCount = 0;
    for (const auto &edge : identitySensitive.getRootEdges()) {
        if (edge.action.getActionType() == sts::search::ActionType::CARD &&
            special.cards.hand[edge.action.getSourceIdx()].id == sts::CardId::RAMPAGE) {
            ++specialCount;
        }
    }
    require(specialCount == 2, "identity-sensitive card copies must remain distinct");
}

void uidFragmentationDiagnostic(const sts::BattleContext &original) {
    auto base = original;
    base.cards.cardsInHand = 1;
    base.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    base.cards.hand[0].setUniqueId(101);
    sts::CardInstance drawStrike(sts::CardId::STRIKE_RED);
    drawStrike.setUniqueId(202);
    base.cards.drawPile.assignInformationState({}, {drawStrike}, {}, false);

    auto swapped = base;
    swapped.cards.hand[0].setUniqueId(202);
    sts::CardInstance swappedDraw(sts::CardId::STRIKE_RED);
    swappedDraw.setUniqueId(101);
    swapped.cards.drawPile.assignInformationState({}, {swappedDraw}, {}, false);
    require(!base.equalForSearch(swapped), "UID swap must miss exact search equality");
    const auto swappedComparison = sts::search::compareForSearchIgnoringBenignDrawIdentityDiagnostic(
        base, swapped);
    require(swappedComparison.equivalent && swappedComparison.handDifferent
                && swappedComparison.drawDifferent,
            "ordinary hand/draw UID swap must match the diagnostic comparator");
    require(sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(base, swapped),
            "diagnostic comparator wrapper must agree with detailed comparison");

    auto special = base;
    special.cards.hand[0] = sts::CardInstance(sts::CardId::RAMPAGE);
    special.cards.hand[0].setUniqueId(301);
    sts::CardInstance specialDraw(sts::CardId::RAMPAGE);
    specialDraw.setUniqueId(302);
    special.cards.drawPile.assignInformationState({}, {specialDraw}, {}, false);
    auto specialSwapped = special;
    specialSwapped.cards.hand[0].setUniqueId(302);
    sts::CardInstance specialSwappedDraw(sts::CardId::RAMPAGE);
    specialSwappedDraw.setUniqueId(301);
    specialSwapped.cards.drawPile.assignInformationState({}, {specialSwappedDraw}, {}, false);
    require(special.cards.hand[0].usesSpecialData(), "Rampage must be identity-sensitive");
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                special, specialSwapped),
            "special-data card UID swap must remain distinct");

    const auto ordinaryDifference = [&](auto mutate, const char *message) {
        auto changed = base;
        mutate(changed.cards.hand[0]);
        require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(base, changed),
                message);
    };
    ordinaryDifference([](auto &card) { card.upgraded = true; },
                       "upgrade difference must remain distinct");
    ordinaryDifference([](auto &card) { card.cost = static_cast<std::int8_t>(card.cost + 1); },
                       "base cost difference must remain distinct");
    ordinaryDifference([](auto &card) { card.costForTurn = static_cast<std::int8_t>(card.costForTurn - 1); },
                       "turn cost difference must remain distinct");
    ordinaryDifference([](auto &card) { card.freeToPlayOnce = true; },
                       "free-to-play difference must remain distinct");
    ordinaryDifference([](auto &card) { card.retain = true; },
                       "retain difference must remain distinct");
    ordinaryDifference([](auto &card) { card.specialData = 1; },
                       "special-data difference must remain distinct");

    auto knownTopChanged = base;
    sts::CardInstance top(sts::CardId::BASH);
    top.setUniqueId(401);
    knownTopChanged.cards.drawPile.assignInformationState({}, {drawStrike}, {top}, false);
    auto knownTopUidChanged = knownTopChanged;
    knownTopUidChanged.cards.drawPile = {};
    sts::CardInstance topChanged = top;
    topChanged.setUniqueId(402);
    knownTopUidChanged.cards.drawPile.assignInformationState({}, {drawStrike}, {topChanged}, false);
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                knownTopChanged, knownTopUidChanged),
            "known-top UID difference must remain distinct");

    auto knownBottomChanged = base;
    sts::CardInstance bottom(sts::CardId::DEFEND_RED);
    bottom.setUniqueId(403);
    knownBottomChanged.cards.drawPile.assignInformationState({bottom}, {drawStrike}, {}, false);
    auto knownBottomUidChanged = knownBottomChanged;
    sts::CardInstance bottomChanged = bottom;
    bottomChanged.setUniqueId(404);
    knownBottomUidChanged.cards.drawPile.assignInformationState({bottomChanged}, {drawStrike}, {}, false);
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                knownBottomChanged, knownBottomUidChanged),
            "known-bottom UID difference must remain distinct");

    auto discardChanged = base;
    sts::CardInstance discard(sts::CardId::DEFEND_RED);
    discard.setUniqueId(501);
    discardChanged.cards.discardPile.assignInformationState({}, {discard}, {}, false);
    auto discardUidChanged = discardChanged;
    discard.setUniqueId(502);
    discardUidChanged.cards.discardPile.assignInformationState({}, {discard}, {}, false);
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                discardChanged, discardUidChanged),
            "discard UID difference must remain distinct");

    auto exhaustChanged = base;
    sts::CardInstance exhaust(sts::CardId::DEFEND_RED);
    exhaust.setUniqueId(601);
    exhaustChanged.cards.exhaustPile.assignInformationState({}, {exhaust}, {}, false);
    auto exhaustUidChanged = exhaustChanged;
    exhaust.setUniqueId(602);
    exhaustUidChanged.cards.exhaustPile.assignInformationState({}, {exhaust}, {}, false);
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                exhaustChanged, exhaustUidChanged),
            "exhaust UID difference must remain distinct");

    auto queueChanged = base;
    queueChanged.curCardQueueItem.card = sts::CardInstance(sts::CardId::STRIKE_RED);
    queueChanged.curCardQueueItem.card.setUniqueId(701);
    auto queueUidChanged = queueChanged;
    queueUidChanged.curCardQueueItem.card.setUniqueId(702);
    require(!sts::search::equalForSearchIgnoringBenignDrawIdentityDiagnostic(
                queueChanged, queueUidChanged),
            "queued-card UID difference must remain distinct");

    auto parity = base;
    sts::CardInstance duplicateA(sts::CardId::STRIKE_RED);
    duplicateA.setUniqueId(801);
    sts::CardInstance duplicateB(sts::CardId::STRIKE_RED);
    duplicateB.setUniqueId(802);
    sts::CardInstance duplicateC(sts::CardId::DEFEND_RED);
    duplicateC.setUniqueId(803);
    parity.cards.drawPile.assignInformationState({}, {duplicateA, duplicateB, duplicateC}, {}, false);
    Search diagnosticsOff(parity);
    Search diagnosticsOn(parity);
    diagnosticsOn.collectUidFragmentationDiagnostics = true;
    diagnosticsOff.recordActionTrace = true;
    diagnosticsOn.recordActionTrace = true;
    diagnosticsOff.search(128);
    diagnosticsOn.search(128);
    require(diagnosticsOff.getBestAction() == diagnosticsOn.getBestAction(),
            "UID diagnostics must not change the selected action");
    require(diagnosticsOff.randGen == diagnosticsOn.randGen,
            "UID diagnostics must not change search RNG");
    require(diagnosticsOff.rolloutAgent.rng == diagnosticsOn.rolloutAgent.rng,
            "UID diagnostics must not change rollout RNG");
    require(diagnosticsOff.actionStack == diagnosticsOn.actionStack,
            "UID diagnostics must not change the action trace");
    equalStats(diagnosticsOff.stats, diagnosticsOn.stats);
    require(diagnosticsOff.stats.uidRelaxedNodeAllocationCandidates == 0
                && diagnosticsOff.stats.uidRelaxedNodeCandidatesWithDrawDifference == 0
                && diagnosticsOff.stats.uidRelaxedNodeCandidatesWithHandDifference == 0
                && diagnosticsOff.stats.uidRelaxedNodeCandidatesWithBothHandAndDrawDifference == 0
                && diagnosticsOff.stats.uidRelaxedChanceSiblingCandidates == 0
                && diagnosticsOff.stats.uidRelaxedChanceSiblingCandidatesByCategory[0] == 0
                && diagnosticsOff.stats.uidRelaxedChanceSiblingCandidatesByCategory[1] == 0
                && diagnosticsOff.stats.uidRelaxedChanceSiblingCandidatesByCategory[2] == 0
                && diagnosticsOff.stats.uidRelaxedChanceSiblingCandidatesWithHandDrawSwap == 0,
            "UID diagnostics must remain inactive by default");
    require(diagnosticsOff.getRootEdges().size() == diagnosticsOn.getRootEdges().size(),
            "UID diagnostics must not change root edge count");
    for (std::size_t i = 0; i < diagnosticsOff.getRootEdges().size(); ++i) {
        const auto &lhs = diagnosticsOff.getRootEdges()[i];
        const auto &rhs = diagnosticsOn.getRootEdges()[i];
        require(lhs.action == rhs.action && lhs.visitCount == rhs.visitCount
                    && lhs.rngAdvanceSteps == rhs.rngAdvanceSteps
                    && lhs.node->simulationCount == rhs.node->simulationCount
                    && lhs.node->evaluationSum == rhs.node->evaluationSum,
                "UID diagnostics must not change root edge statistics");
    }
}

void singleCardSelectCanonicalization(const sts::BattleContext &original) {
    const std::array<sts::CardSelectTask, 7> tasks = {
        sts::CardSelectTask::ARMAMENTS, sts::CardSelectTask::EXHAUST_ONE,
        sts::CardSelectTask::FORETHOUGHT, sts::CardSelectTask::WARCRY,
        sts::CardSelectTask::HEADBUTT, sts::CardSelectTask::EXHUME,
        sts::CardSelectTask::LIQUID_MEMORIES_POTION,
    };

    for (const auto task : tasks) {
        auto bc = original;
        bc.inputState = sts::InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = task;
        bc.cardSelectInfo.selectedBits = 0;
        const bool handSource = task == sts::CardSelectTask::ARMAMENTS ||
                                task == sts::CardSelectTask::EXHAUST_ONE ||
                                task == sts::CardSelectTask::FORETHOUGHT ||
                                task == sts::CardSelectTask::WARCRY;
        if (handSource) {
            bc.cards.cardsInHand = 3;
            bc.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
            bc.cards.hand[1] = sts::CardInstance(sts::CardId::DEFEND_RED);
            bc.cards.hand[2] = sts::CardInstance(sts::CardId::STRIKE_RED);
            bc.cards.hand[0].setUniqueId(501); bc.cards.hand[2].setUniqueId(502);
        } else {
            std::vector<sts::CardInstance> cards = {
                sts::CardInstance(sts::CardId::STRIKE_RED),
                sts::CardInstance(sts::CardId::DEFEND_RED),
                sts::CardInstance(sts::CardId::STRIKE_RED),
            };
            cards[0].setUniqueId(501); cards[2].setUniqueId(502);
            if (task == sts::CardSelectTask::EXHUME) {
                bc.cards.exhaustPile.assignInformationState({}, cards, {}, false);
            } else {
                bc.cards.discardPile.assignInformationState({}, cards, {}, false);
            }
        }

        const auto actions = sts::search::Action::enumerateCardSelectActions(bc);
        require(actions.size() == 2 && actions[0].getSelectIdx() == 0 && actions[1].getSelectIdx() == 1,
                "safe single-card selects must retain the first equivalent representative");
    }

    auto differentiated = original;
    differentiated.inputState = sts::InputState::CARD_SELECT;
    differentiated.cardSelectInfo.cardSelectTask = sts::CardSelectTask::HEADBUTT;
    std::vector<sts::CardInstance> differentiatedCards = {
        sts::CardInstance(sts::CardId::STRIKE_RED), sts::CardInstance(sts::CardId::STRIKE_RED),
    };
    differentiatedCards[1].retain = true;
    differentiated.cards.discardPile.assignInformationState({}, differentiatedCards, {}, false);
    require(sts::search::Action::enumerateCardSelectActions(differentiated).size() == 2,
            "differing select card state must preserve separate choices");

    auto execution = original;
    execution.inputState = sts::InputState::CARD_SELECT;
    execution.cardSelectInfo.cardSelectTask = sts::CardSelectTask::EXHAUST_ONE;
    execution.cards.cardsInHand = 3;
    execution.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    execution.cards.hand[1] = sts::CardInstance(sts::CardId::DEFEND_RED);
    execution.cards.hand[2] = sts::CardInstance(sts::CardId::STRIKE_RED);
    execution.cards.hand[0].setUniqueId(601); execution.cards.hand[2].setUniqueId(602);
    const auto representative = sts::search::Action::enumerateCardSelectActions(execution).front();
    representative.execute(execution);
    require(execution.cards.cardsInHand == 2 && execution.cards.exhaustPile.size() == 1 &&
            execution.cards.exhaustPile[0].id == sts::CardId::STRIKE_RED,
            "select representative must still execute the expected pile transformation");
}

void contractedSelectionExperimentFixtures(sts::GameContext &gc) {
    auto headbutt = sameTurnState(gc, sts::MonsterEncounter::TWO_FUNGI_BEASTS,
                                  100, 3, false, true);
    headbutt.cards.clear();
    headbutt.cards.cardsInHand = 1;
    headbutt.cards.hand[0] = sts::CardInstance(sts::CardId::HEADBUTT);
    headbutt.cards.hand[0].setUniqueId(701);
    headbutt.cards.nextUniqueCardId = 702;
    std::vector<sts::CardInstance> discard = {
        sts::CardInstance(sts::CardId::STRIKE_RED),
        sts::CardInstance(sts::CardId::BASH),
        sts::CardInstance(sts::CardId::STRIKE_RED),
    };
    discard[0].setUniqueId(711);
    discard[1].setUniqueId(712);
    discard[2].setUniqueId(713);
    headbutt.cards.discardPile.assignInformationState({}, discard, {}, false);
    headbutt.inputState = sts::InputState::PLAYER_NORMAL;
    headbutt.outcome = sts::Outcome::UNDECIDED;
    headbutt.isBattleOver = false;
    headbutt.monsters.monsterCount = 2;
    headbutt.monsters.monstersAlive = 2;

    Search control(headbutt);
    control.step();
    Search macro(headbutt);
    macro.contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
    macro.step();
    int macroEdges = 0;
    for (const auto &edge : macro.getRootEdges()) {
        if (edge.hasContinuation()) ++macroEdges;
    }
    require(macroEdges == 4, "Headbutt macro surface must be two targets by two canonical selections");
    require(macro.stats.macroEligibleDecisionNodes == 1
                && macro.stats.macroEdgesGenerated == 4
                && macro.stats.macroOptionCountSum == 4,
            "macro telemetry must count the one eligible root and four generated edges");
    int ordinaryEdges = 0;
    for (const auto &edge : control.getRootEdges()) if (edge.hasContinuation()) ++ordinaryEdges;
    require(ordinaryEdges == 0, "control must retain primitive edges without continuations");

    Search selected(headbutt);
    selected.contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
    selected.search(32);
    const auto sequence = selected.getBestActionSequence();
    require(sequence.size() == 2 && selected.getBestAction() == sequence.front(),
            "experimental sequence accessor must preserve getBestAction compatibility");
    const Search::Edge *selectedEdge = nullptr;
    for (const auto &edge : selected.getRootEdges()) {
        if (edge.action == sequence[0] && edge.hasContinuation()
                && edge.continuation == sequence[1]) {
            selectedEdge = &edge;
            break;
        }
    }
    require(selectedEdge != nullptr && selectedEdge->node != nullptr && !selectedEdge->node->isRandomNode,
            "selected macro must point directly to its final deterministic state");
    auto sequential = headbutt;
    const auto rngBefore = sequential.rng;
    for (const auto &action : sequence) {
        require(action.isValidAction(sequential), "macro primitive must be valid in sequence order");
        action.execute(sequential);
    }
    require(sequential.equalForSearch(*selectedEdge->node->state)
                && sequential.rng == selectedEdge->node->state->rng
                && sequential.rng == rngBefore,
            "macro endpoint must equal ordinary sequential execution including RNG state");

    auto forced = headbutt;
    forced.inputState = sts::InputState::CARD_SELECT;
    forced.cardSelectInfo.cardSelectTask = sts::CardSelectTask::HEADBUTT;
    forced.cards.discardPile.assignInformationState({}, {discard.front()}, {}, false);
    Search forcedSearch(forced);
    forcedSearch.contractMode = silver_bridge::SilverSearchContractMode::FORCED_SELECTION;
    forcedSearch.search(1);
    require(forcedSearch.stats.forcedSelectionsContracted == 1
                && forcedSearch.root->state->inputState == sts::InputState::PLAYER_NORMAL,
            "arm A must auto-resolve a one-option CARD_SELECT without a selection search");

    require(!sts::search::Action::hasEnumeratedCardSelectActions(sts::CardSelectTask::HOLOGRAM),
            "Hologram must not claim a deterministic enumerator it does not implement");
    auto hologram = headbutt;
    hologram.inputState = sts::InputState::CARD_SELECT;
    // Hologram is deliberately absent from the seven-task allowlist.  Use a
    // supported non-allowlisted selector here so the fallback path can be
    // exercised without invoking the simulator's intentionally unimplemented
    // Hologram execution action.
    hologram.cardSelectInfo.cardSelectTask = sts::CardSelectTask::DUAL_WIELD;
    hologram.cards.cardsInHand = 2;
    hologram.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    hologram.cards.hand[1] = sts::CardInstance(sts::CardId::BASH);
    Search hologramSearch(hologram);
    hologramSearch.contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
    hologramSearch.step();
    for (const auto &edge : hologramSearch.getRootEdges())
        require(!edge.hasContinuation(), "unsupported selectors including Hologram must remain uncontracted");

    auto stochastic = headbutt;
    stochastic.cards.hand[0] = sts::CardInstance(sts::CardId::DISCOVERY);
    stochastic.cards.hand[0].setUniqueId(731);
    Search stochasticSearch(stochastic);
    stochasticSearch.contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
    stochasticSearch.step();
    for (const auto &edge : stochasticSearch.getRootEdges())
        require(!edge.hasContinuation(), "RNG-consuming CARD_SELECT parents must not form macros");

    auto deadBranch = sameTurnState(gc, sts::MonsterEncounter::TWO_FUNGI_BEASTS,
                                    100, 3, false, true);
    deadBranch.cards.clear();
    deadBranch.cards.cardsInHand = 3;
    deadBranch.cards.hand[0] = sts::CardInstance(sts::CardId::TRUE_GRIT, true);
    deadBranch.cards.hand[1] = sts::CardInstance(sts::CardId::STRIKE_RED);
    deadBranch.cards.hand[2] = sts::CardInstance(sts::CardId::DEFEND_RED);
    deadBranch.cards.hand[0].setUniqueId(741);
    deadBranch.cards.hand[1].setUniqueId(742);
    deadBranch.cards.hand[2].setUniqueId(743);
    deadBranch.cards.nextUniqueCardId = 744;
    deadBranch.player.setHasRelic<sts::RelicId::DEAD_BRANCH>(true);

    const sts::search::Action trueGrit(sts::search::ActionType::CARD, 0);
    require(trueGrit.isValidAction(deadBranch), "True Grit+ Dead Branch fixture must be playable");
    auto afterTrueGrit = deadBranch;
    const auto trueGritRng = afterTrueGrit.rng;
    trueGrit.execute(afterTrueGrit);
    require(afterTrueGrit.rng == trueGritRng
                && afterTrueGrit.inputState == sts::InputState::CARD_SELECT
                && afterTrueGrit.cardSelectInfo.cardSelectTask == sts::CardSelectTask::EXHAUST_ONE,
            "True Grit+ must reach a deterministic EXHAUST_ONE screen");
    const auto exhaustChoices = sts::search::Action::enumerateCardSelectActions(afterTrueGrit);
    require(exhaustChoices.size() >= 2,
            "True Grit+ Dead Branch fixture must expose at least two exhaust choices");
    auto afterExhaust = afterTrueGrit;
    exhaustChoices.front().execute(afterExhaust);
    require(afterExhaust.rng != trueGritRng,
            "Dead Branch must make the EXHAUST_ONE continuation stochastic");

    Search deadBranchSearch(deadBranch);
    deadBranchSearch.contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
    deadBranchSearch.step();
    int trueGritEdges = 0;
    for (const auto &edge : deadBranchSearch.getRootEdges()) {
        if (edge.action.getActionType() == sts::search::ActionType::CARD
                && edge.action.getSourceIdx() == 0) {
            ++trueGritEdges;
            require(!edge.hasContinuation(),
                    "True Grit+ with Dead Branch must remain an uncontracted primitive edge");
        }
    }
    require(trueGritEdges == 1,
            "True Grit+ Dead Branch fixture must retain exactly one primitive card edge");
}

std::set<std::vector<int>> semanticGambleSurface(const sts::BattleContext &bc, bool canonical) {
    std::vector<int> classIds(bc.cards.cardsInHand, -1);
    std::vector<const sts::CardInstance *> classRepresentatives;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) {
        for (std::size_t classId = 0; classId < classRepresentatives.size(); ++classId) {
            if (sts::search::Action::areCardsEquivalentForSearch(
                    bc.cards.hand[i], *classRepresentatives[classId])) {
                classIds[i] = static_cast<int>(classId);
                break;
            }
        }
        if (classIds[i] < 0) {
            classIds[i] = static_cast<int>(classRepresentatives.size());
            classRepresentatives.push_back(&bc.cards.hand[i]);
        }
    }

    std::set<std::vector<int>> surface;
    auto record = [&](int selectedBits) {
        std::vector<int> counts(classRepresentatives.size(), 0);
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            if (selectedBits & (1 << i)) {
                ++counts[classIds[i]];
            }
        }
        surface.insert(std::move(counts));
    };
    if (!canonical) {
        for (int selectedBits = 0; selectedBits < (1 << bc.cards.cardsInHand); ++selectedBits) {
            record(selectedBits);
        }
        return surface;
    }
    std::set<int> visited;
    std::function<void(int)> visit = [&](int selectedBits) {
        if (!visited.insert(selectedBits).second) {
            return;
        }
        auto state = bc;
        state.inputState = sts::InputState::CARD_SELECT;
        state.cardSelectInfo.cardSelectTask = sts::CardSelectTask::GAMBLE;
        state.cardSelectInfo.canPickAnyNumber = true;
        state.cardSelectInfo.selectedBits = selectedBits;
        const auto actions = sts::search::Action::enumerateCardSelectActions(state);
        for (const auto &action : actions) {
            if (action.getActionType() == sts::search::ActionType::MULTI_CARD_SELECT) {
                record(selectedBits);
            } else {
                visit(selectedBits | (1 << action.getSelectIdx()));
            }
        }
    };
    visit(0);
    return surface;
}

void gambleMultiplicityCanonicalization(const sts::BattleContext &original) {
    auto state = original;
    state.inputState = sts::InputState::CARD_SELECT;
    state.cardSelectInfo.cardSelectTask = sts::CardSelectTask::GAMBLE;
    state.cardSelectInfo.canPickAnyNumber = true;
    state.cards.cardsInHand = 4;
    state.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    state.cards.hand[1] = sts::CardInstance(sts::CardId::DEFEND_RED);
    state.cards.hand[2] = sts::CardInstance(sts::CardId::STRIKE_RED);
    state.cards.hand[3] = sts::CardInstance(sts::CardId::STRIKE_RED);

    auto singleIndices = [](const std::vector<sts::search::Action> &actions) {
        std::vector<int> indices;
        for (const auto &action : actions) {
            if (action.getActionType() == sts::search::ActionType::SINGLE_CARD_SELECT) {
                indices.push_back(action.getSelectIdx());
            }
        }
        return indices;
    };
    const auto initialActions = sts::search::Action::enumerateCardSelectActions(state);
    require(singleIndices(initialActions) == std::vector<int>({0, 1}),
            "GAMBLE must expose only first representatives at the initial state");
    require(initialActions.size() == 3
                && initialActions.back().getActionType() == sts::search::ActionType::MULTI_CARD_SELECT,
            "GAMBLE initial representative reduction must retain confirmation");

    state.cardSelectInfo.selectedBits = 1 << 0;
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(state))
                == std::vector<int>({1, 2}),
            "GAMBLE must expose the next equivalent copy after selecting one");
    state.cardSelectInfo.selectedBits = (1 << 0) | (1 << 2);
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(state))
                == std::vector<int>({1, 3}),
            "GAMBLE must expose the third equivalent copy after selecting two");

    state.cardSelectInfo.selectedBits = 1 << 2;
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(state))
                == std::vector<int>({0, 1}),
            "GAMBLE must handle a noncanonical incoming selectedBits state");
    require(sts::search::Action::enumerateCardSelectActions(state).back().getActionType()
                == sts::search::ActionType::MULTI_CARD_SELECT,
            "GAMBLE noncanonical selectedBits must retain confirmation");

    auto twoAndTwo = state;
    twoAndTwo.cardSelectInfo.selectedBits = 0;
    twoAndTwo.cards.cardsInHand = 4;
    twoAndTwo.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    twoAndTwo.cards.hand[1] = sts::CardInstance(sts::CardId::STRIKE_RED);
    twoAndTwo.cards.hand[2] = sts::CardInstance(sts::CardId::DEFEND_RED);
    twoAndTwo.cards.hand[3] = sts::CardInstance(sts::CardId::DEFEND_RED);
    const auto twoAndTwoSurface = semanticGambleSurface(twoAndTwo, true);
    const auto twoAndTwoReference = semanticGambleSurface(twoAndTwo, false);
    require(twoAndTwoSurface == twoAndTwoReference && twoAndTwoSurface.size() == 9,
            "GAMBLE 2+2 canonical surface must equal all 9 semantic subsets");

    auto fiveAndFive = twoAndTwo;
    fiveAndFive.cards.cardsInHand = 10;
    for (int i = 0; i < 5; ++i) {
        fiveAndFive.cards.hand[i] = sts::CardInstance(sts::CardId::STRIKE_RED);
        fiveAndFive.cards.hand[i + 5] = sts::CardInstance(sts::CardId::DEFEND_RED);
    }
    const auto fiveAndFiveSurface = semanticGambleSurface(fiveAndFive, true);
    const auto fiveAndFiveReference = semanticGambleSurface(fiveAndFive, false);
    require(fiveAndFiveSurface == fiveAndFiveReference && fiveAndFiveSurface.size() == 36,
            "GAMBLE 5+5 canonical surface must equal all 36 semantic subsets");

    auto distinct = state;
    distinct.cards.cardsInHand = 2;
    distinct.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED);
    distinct.cards.hand[1] = distinct.cards.hand[0];
    distinct.cards.hand[1].upgraded = true;
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(distinct)).size() == 2,
            "GAMBLE must preserve upgraded same-name cards");
    distinct.cards.hand[1].upgraded = distinct.cards.hand[0].upgraded;
    distinct.cards.hand[1].costForTurn = distinct.cards.hand[0].costForTurn - 1;
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(distinct)).size() == 2,
            "GAMBLE must preserve same-name cards with distinct costForTurn");
    distinct.cards.hand[1].costForTurn = distinct.cards.hand[0].costForTurn;
    distinct.cards.hand[1].retain = true;
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(distinct)).size() == 2,
            "GAMBLE must preserve same-name cards with distinct retain state");

    auto special = state;
    special.cards.cardsInHand = 2;
    special.cards.hand[0] = sts::CardInstance(sts::CardId::RAMPAGE);
    special.cards.hand[1] = special.cards.hand[0];
    special.cards.hand[0].setUniqueId(701);
    special.cards.hand[1].setUniqueId(702);
    require(singleIndices(sts::search::Action::enumerateCardSelectActions(special)).size() == 2,
            "GAMBLE must preserve identity-sensitive special-data copies");
}

void gambleMicrobenchmark(sts::GameContext &gc, int simulations, std::size_t expectedRootActions) {
    auto state = fixture(gc);
    state.inputState = sts::InputState::CARD_SELECT;
    state.cardSelectInfo.cardSelectTask = sts::CardSelectTask::GAMBLE;
    state.cardSelectInfo.canPickAnyNumber = true;
    state.cards.cardsInHand = 10;
    for (int i = 0; i < 5; ++i) {
        state.cards.hand[i] = sts::CardInstance(sts::CardId::STRIKE_RED);
        state.cards.hand[i + 5] = sts::CardInstance(sts::CardId::DEFEND_RED);
    }
    const auto rootActions = sts::search::Action::enumerateCardSelectActions(state);
    require(rootActions.size() == expectedRootActions, "GAMBLE microbenchmark root action count mismatch");
    Search search(state);
    const auto start = std::chrono::steady_clock::now();
    search.search(simulations);
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::cout << "gamble_microbenchmark simulations=" << simulations
              << " root_actions=" << rootActions.size()
              << " steps=" << search.stats.steps
              << " nodes_created=" << search.stats.nodesCreated
              << " action_count=" << search.actionCount
              << " wall_seconds=" << elapsed << '\n';
}

void potionMicrobenchmark(sts::GameContext &gc, int simulations, std::size_t expectedRootActions,
                          bool distinctPotions) {
    auto state = fixture(gc);
    state.cards.cardsInHand = 0;
    if (distinctPotions) {
        installPotions(state, {sts::Potion::STRENGTH_POTION, sts::Potion::DEXTERITY_POTION,
                               sts::Potion::BLOCK_POTION, sts::Potion::ENERGY_POTION,
                               sts::Potion::FIRE_POTION});
    } else {
        installPotions(state, {sts::Potion::STRENGTH_POTION, sts::Potion::STRENGTH_POTION,
                               sts::Potion::STRENGTH_POTION, sts::Potion::STRENGTH_POTION,
                               sts::Potion::STRENGTH_POTION});
    }
    const auto rootActionSet = rootActions(state);
    require(rootActionSet.size() == expectedRootActions, "potion microbenchmark root action count mismatch");
    Search search(state);
    const auto start = std::chrono::steady_clock::now();
    search.search(simulations);
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    std::cout << "potion_microbenchmark simulations=" << simulations
              << " root_actions=" << rootActionSet.size()
              << " steps=" << search.stats.steps
              << " nodes_created=" << search.stats.nodesCreated
              << " action_count=" << search.actionCount
              << " wall_seconds=" << elapsed << '\n';
}

void widening(Search &search) {
    // Exercise the complete bounded table, the fallback, both independent parameter
    // sets, and mutation after warming the cache. Compare the original expression.
    for (const auto parameters : {std::pair<double,double>{4.6, 0.37}, {1.0, 0.5}, {2.25, 0.0}, {0.0, 0.5}}) {
        search.chanceWideningC = parameters.first;
        search.chanceWideningAlpha = parameters.second;
        search.endTurnWideningC = parameters.first + 0.75;
        search.endTurnWideningAlpha = parameters.second + 0.03;
        for (int category = 0; category < 3; ++category) {
            const double c = category == 0 ? search.endTurnWideningC : search.chanceWideningC;
            const double alpha = category == 0 ? search.endTurnWideningAlpha : search.chanceWideningAlpha;
            for (std::int64_t visits = 0; visits <= 32770; ++visits) {
                const int expected = std::max(1, static_cast<int>(std::ceil(c * std::pow(visits + 1, alpha))));
                require(search.wideningCap(category, visits) == expected, "widening must preserve original pow expression");
            }
            const std::int64_t visits = 1000000;
            require(search.wideningCap(category, visits) == std::max(1, static_cast<int>(std::ceil(c * std::pow(visits + 1, alpha)))), "large visit fallback");
        }
    }
}

void rootPriorSelection(Search &search) {
    Search::Node child, internal;
    child.simulationCount = 4;
    child.evaluationSum = 12;
    auto *root = search.root;
    const auto saved = *root;
    root->simulationCount = 16;
    root->edges.resize(2);
    for (auto &edge : root->edges) { edge.node = &child; edge.visitCount = 3; }
    internal = *root;
    const auto ordinary = search.evaluateEdge(*root, 0, std::log(17.0));
    search.replayRootPriors = {0.25, 0.75};
    require(search.evaluateEdge(*root, 0, std::log(17.0)) == 3.625, "exact root PUCT formula");
    require(search.selectBestEdgeToSearch(*root) == 1, "prior must influence root allocation");
    require(search.evaluateEdge(internal, 0, std::log(17.0)) == ordinary, "internal UCT unchanged");
    root->isRandomNode = true;
    require(search.evaluateEdge(*root, 0, std::log(17.0)) == ordinary, "chance selection excludes prior");
    root->isRandomNode = false;
    root->edges[0].visitCount = 0;
    require(search.selectBestEdgeToSearch(*root) == 0, "unvisited first despite root prior");
    search.replayRootPriors.clear();
    *root = saved;
}

void equalStats(const sts::search::SearchStats &a, const sts::search::SearchStats &b) {
#define SAME(field) require(a.field == b.field, "trace changed stats: " #field)
    SAME(steps); SAME(nodesCreated); SAME(queueItemCanonicalHits); SAME(detTranspositions);
    SAME(chanceOutcomesSampled); SAME(chanceSiblingReuse); SAME(chanceTranspositions);
    SAME(depthSum); SAME(chanceDepthSum); SAME(rolloutCalls);
    SAME(rolloutTerminalWins); SAME(rolloutTerminalLosses); SAME(rolloutNonTerminalStops);
    SAME(rolloutActionCount); SAME(rolloutTurnDelta); SAME(rolloutSkippedVNet);
    SAME(rolloutUtilitySum); SAME(rolloutWinBonusSum); SAME(rolloutHpSum);
    SAME(rolloutPotionSum); SAME(rolloutTurnPenaltySum); SAME(rolloutDeathSaveSum);
    SAME(rolloutGoldSum); SAME(rolloutMaxHpSum); SAME(rolloutParasitePenaltySum);
    SAME(rolloutMonsterDamageSum); SAME(rolloutAliveSum); SAME(rolloutEnergyWasteSum);
    SAME(rolloutDrawSum); SAME(rolloutSurvivalSum);
    SAME(fpuSelectionOpportunities);
    SAME(fpuVisitedSelectedWithUnvisitedRemaining);
    SAME(fpuUnvisitedSelected);
    for (int i = 0; i < 3; ++i) { SAME(wSampled[i]); SAME(wSibReuse[i]); SAME(wCapped[i]); }
#undef SAME
}

void internalFpuSelectionFixtures(const sts::BattleContext &bc) {
    Search search(bc);
    Search::Node parent, visitedChild;
    auto parentState = bc;
    parentState.inputState = sts::InputState::PLAYER_NORMAL;
    parent.state = &parentState;
    parent.simulationCount = 2;
    parent.evaluationSum = 0.0;
    visitedChild.simulationCount = 1;
    visitedChild.evaluationSum = 0.0;
    parent.edges.resize(2);
    parent.edges[0].visitCount = 1;
    parent.edges[0].node = &visitedChild;
    parent.edges[1].visitCount = 0;
    parent.edges[1].node = nullptr;
    search.internalFpuEnabled = true;
    require(search.selectBestEdgeToSearch(parent) == 0,
            "finite internal FPU must allow a promising visited edge to win");
    require(search.stats.fpuSelectionOpportunities == 1
            && search.stats.fpuVisitedSelectedWithUnvisitedRemaining == 1
            && search.stats.fpuUnvisitedSelected == 0,
            "internal FPU visited-selection telemetry");

    parent.simulationCount = 100;
    parent.edges[0].visitCount = 99;
    visitedChild.simulationCount = 99;
    require(search.selectBestEdgeToSearch(parent) == 1,
            "finite internal FPU must eventually select the remaining edge");
    require(search.stats.fpuSelectionOpportunities == 2
            && search.stats.fpuUnvisitedSelected == 1,
            "internal FPU eventual-exploration telemetry");

    auto rootState = parentState;
    search.root->state = &rootState;
    search.root->simulationCount = 2;
    search.root->evaluationSum = 0.0;
    search.root->edges = parent.edges;
    require(search.selectBestEdgeToSearch(*search.root) == 1,
            "root must retain unvisited-first selection");
    require(search.stats.fpuSelectionOpportunities == 2,
            "root selection must not count as an internal FPU opportunity");

    auto cardSelectState = parentState;
    cardSelectState.inputState = sts::InputState::CARD_SELECT;
    parent.state = &cardSelectState;
    parent.simulationCount = 2;
    parent.edges = search.root->edges;
    require(search.selectBestEdgeToSearch(parent) == 1,
            "CARD_SELECT must retain unvisited-first selection");
    require(search.stats.fpuSelectionOpportunities == 2,
            "CARD_SELECT must not count as an internal FPU opportunity");

    parent.isRandomNode = true;
    parent.state = nullptr;
    require(search.selectBestEdgeToSearch(parent) == 1,
            "chance nodes must retain unvisited-first selection");
    require(search.stats.fpuSelectionOpportunities == 2,
            "chance selection must not count as an internal FPU opportunity");

    Search off(bc);
    Search explicitOff(bc);
    auto offState = parentState;
    offState.inputState = sts::InputState::PLAYER_NORMAL;
    off.root->state = &offState;
    explicitOff.root->state = &offState;
    off.root->simulationCount = explicitOff.root->simulationCount = 2;
    off.root->edges = explicitOff.root->edges = parent.edges;
    require(off.selectBestEdgeToSearch(*off.root)
                == explicitOff.selectBestEdgeToSearch(*explicitOff.root),
            "FPU flag-off selection parity");
    require(off.stats.fpuSelectionOpportunities == 0
            && explicitOff.stats.fpuSelectionOpportunities == 0,
            "FPU flag-off telemetry parity");
}

void traceParity(const sts::BattleContext &bc, bool observe) {
    Search plain(bc), traced(bc);
    plain.collectRolloutDiagnostics = traced.collectRolloutDiagnostics = true;
    plain.collectVictoryCounts = traced.collectVictoryCounts = true;
    traced.recordActionTrace = true;
    traced.stateToNode.assign(1 << 18, {0, nullptr});
    traced.stateToNodeMask = traced.stateToNode.size() - 1;
    std::vector<silver_bridge::SilverLeafObservation> plainLeaves, tracedLeaves;
    auto capture = [](auto &records) {
        return [&records](silver_bridge::SilverLeafObservation &leaf) {
            if (leaf.phase == silver_bridge::SilverLeafObservationPhase::START) leaf.collectResult = true;
            records.push_back(leaf);
        };
    };
    if (observe) { plain.leafObserver = capture(plainLeaves); traced.leafObserver = capture(tracedLeaves); }
    for (int i = 0; i < 96; ++i) {
        plain.step(); traced.step();
        require(plain.poolUsed == traced.poolUsed, "trace changed pool size");
        for (std::size_t k = 0; k < plain.poolUsed; ++k) {
            const auto &x = *plain.allNodes[k], &y = *traced.allNodes[k];
            require(x.randomnessBase == y.randomnessBase && x.isRandomNode == y.isRandomNode,
                    "trace changed chance nodes");
            require(x.simulationCount == y.simulationCount && x.evaluationSum == y.evaluationSum,
                    "trace changed pool visits or values");
            if (!x.isRandomNode) {
                require(x.state->rng.seed0 == y.state->rng.seed0 && x.state->rng.seed1 == y.state->rng.seed1
                        && x.state->rng.counter == y.state->rng.counter, "trace changed simulator RNG");
                require(x.state->equalForSearch(*y.state), "trace changed pool states");
            }
        }
        require(plain.actionStack.empty(), "default trace must stay empty");
        require(traced.actionStack.size() == traced.actionCount, "trace/count mismatch");

        require(plain.actionCount == traced.actionCount, "trace changed action count");
        require(plain.randGen == traced.randGen, "trace changed search RNG");
        require(plain.rolloutAgent.rng == traced.rolloutAgent.rng, "trace changed rollout RNG");
        equalStats(plain.stats, traced.stats);
        require(plain.getBestAction() == traced.getBestAction(), "trace changed chosen action");
        const auto &a = plain.getRootEdges(), &b = traced.getRootEdges();
        require(a.size() == b.size(), "trace changed root edge count");
        for (std::size_t j = 0; j < a.size(); ++j) {
            require(a[j].action == b[j].action && a[j].visitCount == b[j].visitCount, "trace changed root edges");
            require((a[j].node == nullptr) == (b[j].node == nullptr), "trace changed expansion");
            if (a[j].node) require(a[j].node->simulationCount == b[j].node->simulationCount && a[j].node->evaluationSum == b[j].node->evaluationSum, "trace changed backed-up values");
        }
    }
    require(plain.stats.rolloutActionCount > 0, "fixture must exercise rollouts");
    if (!observe) require(!plain.diagnosticRootHashValid, "unobserved search must not hash diagnostic root");
    if (observe) {
        require(!plainLeaves.empty() && plainLeaves.size() == tracedLeaves.size(), "observer event parity");
        for (std::size_t i = 0; i < plainLeaves.size(); ++i) {
            const auto &a = plainLeaves[i], &b = tracedLeaves[i];
            require(a.rootStateHash == sts::search::hashBattleState(bc) && a.rootStateHash == b.rootStateHash, "observer root hash");
            require(a.phase == b.phase && a.actionCountBeforeRollout == b.actionCountBeforeRollout && a.rolloutActionCount == b.rolloutActionCount, "observer action count parity");
            require(a.leafStateHash == b.leafStateHash && a.rolloutUtility == b.rolloutUtility && a.rolloutActionFingerprints == b.rolloutActionFingerprints, "observer rollout parity");
        }
    }
}

void rootHash(const sts::BattleContext &bc) {
    Search search(bc);
    const auto original = search.diagnosticRootHash();
    require(search.diagnosticRootHashValid, "explicit diagnostic query caches hash");
    require(original == sts::search::hashBattleState(bc), "initial root hash");
    auto changed = bc;
    changed.player.curHp -= 1;
    search.setRoot(changed);
    require(!search.diagnosticRootHashValid, "setRoot hash must remain lazy");
    require(search.diagnosticRootHash() == sts::search::hashBattleState(changed) && search.diagnosticRootHash() != original, "setRoot invalidates cached hash");
    auto next = bc;
    next.player.curHp -= 2;
    auto *node = search.getOrCreateNode(std::move(next));
    search.rerootAt(node);
    require(!search.diagnosticRootHashValid, "reroot hash must remain lazy");
    const auto expected = sts::search::hashBattleState(*node->state);
    require(search.diagnosticRootHash() == expected, "reroot invalidates cached hash");
    int observations = 0;
    search.leafObserver = [&](silver_bridge::SilverLeafObservation &leaf) {
        require(leaf.rootStateHash == expected, "observer uses current reroot hash");
        ++observations;
    };
    search.search(8);
    require(observations > 0, "reroot observer must run");
}
std::size_t validateStorage(const Search &search) {
    std::size_t occupied = 0;
    for (const auto &slot : search.stateToNode) if (slot.node) ++occupied;
    require(occupied == search.stateToNodeUsed && occupied <= search.stateToNode.size() / 2,
            "dedup load/accounting invariant failed");
    require((search.stateToNode.size() & (search.stateToNode.size() - 1)) == 0,
            "dedup capacity must remain power of two");
    std::unordered_set<const Search::Node *> liveNodes;
    for (std::size_t i = 0; i < search.poolUsed; ++i) liveNodes.insert(search.allNodes[i].get());
    std::unordered_set<const sts::BattleContext *> owned;
    for (std::size_t i = 0; i < search.decisionStatesUsed; ++i)
        require(owned.insert(search.decisionStates[i].get()).second, "state pool slots must not alias");
    std::unordered_set<const sts::BattleContext *> assigned;
    std::size_t chances = 0;
    for (std::size_t i = 0; i < search.poolUsed; ++i) {
        const auto &node = *search.allNodes[i];
        for (const auto &edge : node.edges)
            require(!edge.node || liveNodes.count(edge.node), "live edge references reclaimed node");
        if (node.isRandomNode) {
            require(liveNodes.count(node.parent), "chance parent references reclaimed node");
            ++chances;
            require(node.state == nullptr, "chance nodes must not own battle states");
            require(node.parent && !node.parent->isRandomNode && node.parent->state,
                    "chance nodes must retain their decision parent state");
        } else {
            require(node.state && owned.count(node.state), "decision node state must belong to active pool");
            require(assigned.insert(node.state).second, "active decision states must not alias");
        }
    }
    require(assigned.size() == search.decisionStatesUsed, "all active states must belong to decision nodes");
    require(search.poolUsed == search.decisionStatesUsed + chances,
            "logical node accounting must include chance nodes");
    return chances;
}

void retainedStateGrowth(const sts::BattleContext &bc) {
    Search search(bc);
    search.search(64);
    Search::Node *candidate = nullptr;
    for (std::size_t i = 1; i < search.poolUsed; ++i) {
        auto *node = search.allNodes[i].get();
        if (!node->isRandomNode && node->state->outcome == sts::Outcome::UNDECIDED) {
            candidate = node;
            break;
        }
    }
    require(candidate != nullptr, "retained growth fixture must provide a reroot candidate");
    search.rerootAt(candidate, true);
    std::vector<std::pair<const sts::BattleContext *, std::uint64_t>> retained;
    for (std::size_t i = 0; i < search.decisionStatesUsed; ++i) {
        const auto *state = search.decisionStates[i].get();
        retained.emplace_back(state, sts::search::hashBattleState(*state));
    }
    search.search(8);
    require(search.decisionStatesUsed > retained.size(), "reroot continuation must exercise state pool growth");
    validateStorage(search);
    for (std::size_t i = 0; i < retained.size(); ++i) {
        require(search.decisionStates[i].get() == retained[i].first,
                "reroot continuation must retain existing state addresses");
        require(sts::search::hashBattleState(*retained[i].first) == retained[i].second,
                "reroot continuation must not overwrite retained decision states");
    }
}

void storage(const sts::BattleContext &bc, bool emitMetrics) {
    Search search(bc);
    require(search.poolUsed == 1 && search.decisionStatesUsed == 1,
            "fresh root claims one node and one state");
    search.search(512);
    const auto chances = validateStorage(search);
    require(chances > 0, "storage fixture must create chance nodes");
    require(search.decisionStatesUsed == static_cast<std::size_t>(search.stats.nodesCreated) + 1,
            "decision state count must preserve root-excluding node creation telemetry");
    const auto nodePeak = search.allNodes.size(), statePeak = search.decisionStates.size();
    const auto nodesUsed = search.poolUsed, statesUsed = search.decisionStatesUsed;
    require(nodePeak == nodesUsed && statePeak == statesUsed, "first search peaks must match active counts");
    std::vector<const sts::BattleContext *> slots;
    for (const auto &state : search.decisionStates) slots.push_back(state.get());
    search.setRoot(bc);
    require(search.poolUsed == 1 && search.decisionStatesUsed == 1,
            "fresh reset must reset both active pool counters");
    require(search.allNodes.size() == nodePeak && search.decisionStates.size() == statePeak,
            "fresh reset must retain both pool high-water allocations");
    require(search.root->state == slots[0], "fresh reset must reuse the root state slot");
    // Replay the same search into retained slots to check that recycling keeps
    // addresses stable without retaining stale state ownership on chance nodes.
    search.search(512);
    require(validateStorage(search) == chances && search.poolUsed == nodesUsed
            && search.decisionStatesUsed == statesUsed, "recycled pool must preserve logical search counts");
    require(search.allNodes.size() == nodePeak && search.decisionStates.size() == statePeak,
            "same search must not grow retained pools");
    for (std::size_t i = 0; i < slots.size(); ++i)
        require(search.decisionStates[i].get() == slots[i], "reset search must reuse stable state addresses");
    if (emitMetrics) {
        std::cout << "storage simulations=512 logical_nodes=" << nodesUsed
                  << " decision_nodes=" << statesUsed << " chance_nodes=" << chances
                  << " node_pool_peak=" << nodePeak << " state_pool_peak=" << statePeak
                  << " node_size=" << sizeof(Search::Node)
                  << " battle_state_size=" << sizeof(sts::BattleContext)
                  << " omitted_chance_state_payload_bytes=" << chances * sizeof(sts::BattleContext) << '\n';
    }
}

void compaction(const sts::BattleContext &bc, int simulations) {
    Search search(bc);
    if (simulations) {
        search.explorationParameter = search.explorationParameterChance = 25.0;
        search.chanceWideningC = search.endTurnWideningC = 3.7028;
        search.chanceWideningAlpha = search.endTurnWideningAlpha = 0.52389;
        search.search(simulations);
    }
    auto changed = bc;
    changed.player.curHp -= 1;
    auto *root = search.root;
    // For the real canary follow an expanded decision child of the selected action.
    if (simulations) {
        const auto action = search.getBestAction();
        for (const auto &edge : search.root->edges) if (edge.action == action && edge.node) {
            root = edge.node;
            if (root->isRandomNode) {
                require(!root->edges.empty(), "selected chance node must have an outcome");
                root = root->edges.front().node;
            }
            break;
        }
        require(root != search.root && !root->isRandomNode, "canary needs an exact decision child");
    } else {
        root = search.getOrCreateNode(std::move(changed));
        changed = bc; changed.player.curHp -= 2;
        auto *shared = search.getOrCreateNode(std::move(changed));
        root->edges.resize(2);
        root->edges[0].node = shared;
        auto *chance = search.allocNode();
        chance->isRandomNode = true; chance->parent = root;
        chance->stochasticAction = sts::search::Action(sts::search::ActionType::END_TURN);
        chance->edges.resize(1); chance->edges[0].node = shared;
        root->edges[1].node = chance;
        root->simulationCount = 17; root->victoryCount = 3; root->evaluationSum = 12.5;
        root->edges[0].visitCount = 9;
        shared->edges.resize(1); shared->edges[0].node = root; // cycle through a transposition
        shared->simulationCount = 11; shared->evaluationSum = -3.25;
        changed = bc; changed.player.curHp -= 3;
        search.getOrCreateNode(std::move(changed)); // unreachable state
        // Exercise the production allocation cap with dead historical nodes.
        while (search.allNodes.size() <= 32768) search.allocNode();
    }
    std::unordered_set<Search::Node*> reachable;
    std::vector<Search::Node*> pending{root};
    while (!pending.empty()) {
        auto *node = pending.back(); pending.pop_back();
        if (!reachable.insert(node).second) continue;
        if (node->isRandomNode) pending.push_back(node->parent);
        for (const auto &edge : node->edges) if (edge.node) pending.push_back(edge.node);
    }
    std::vector<std::pair<Search::Node*, Search::Node>> snapshots;
    for (auto *node : reachable) snapshots.emplace_back(node, *node);
    const auto before = search.allNodes.size(), statesBefore = search.decisionStates.size();
    auto *oldRoot = search.root;
    search.root = root;
    const auto expectedAction = search.getBestAction();
    search.root = oldRoot;
    search.rerootAt(root, true);
    require(search.getBestAction() == expectedAction, "compaction changed retained-tree result");
    require(search.allNodes.size() == reachable.size() && search.poolUsed == reachable.size(), "must reclaim unreachable nodes");
    require(search.allNodes.size() < before, "fixture must discard dead nodes");
    require(search.decisionStates.size() < statesBefore, "must reclaim unreachable states");
    validateStorage(search);
    for (const auto &[node, saved] : snapshots) {
        require(node->state == saved.state && node->parent == saved.parent, "retained pointers changed");
        require(node->outcomesGenerated == saved.outcomesGenerated && node->randomnessBase == saved.randomnessBase
                && node->stochasticAction == saved.stochasticAction, "retained chance bookkeeping changed");
        require(node->simulationCount == saved.simulationCount && node->victoryCount == saved.victoryCount
                && node->evaluationSum == saved.evaluationSum, "retained node statistics changed");
        require(node->edges.size() == saved.edges.size(), "retained edges changed");
        for (std::size_t i = 0; i < node->edges.size(); ++i)
            require(node->edges[i].node == saved.edges[i].node && node->edges[i].visitCount == saved.edges[i].visitCount
                    && node->edges[i].action == saved.edges[i].action && node->edges[i].rngAdvanceSteps == saved.edges[i].rngAdvanceSteps,
                    "retained edge statistics changed");
        if (!node->isRandomNode) {
            auto copy = *node->state;
            require(search.getOrCreateNode(std::move(copy)) == node && !search.lastNodeWasCreated, "retained dedup lookup failed");
        }
    }
    if (simulations) std::cout << "reroot_canary simulations=" << simulations << " before_nodes=" << before
        << " retained_nodes=" << search.poolUsed << " before_states=" << statesBefore
        << " retained_states=" << search.decisionStatesUsed << " historical_allocated_cap=" << (before >= 32768)
        << " retained_allocated_cap=" << (search.allNodes.size() >= 32768) << '\n';
    if (!simulations) {
        auto dead = bc; dead.player.curHp -= 3;
        search.getOrCreateNode(std::move(dead));
        require(search.lastNodeWasCreated, "dead dedup entry survived collection");
        // Remove artificial actions before a genuine continuation.
        root->edges.clear();
    }
    search.search(32);
    validateStorage(search);
}

void dedupGrowth(const sts::BattleContext &bc) {
    for (const std::size_t initial : {std::size_t(8), std::size_t(65536)}) {
        Search search(bc);
        search.stateToNode.assign(initial, {0, nullptr});
        search.stateToNodeMask = initial - 1;
        const auto rng = search.randGen;
        const auto rolloutRng = search.rolloutAgent.rng;
        const std::size_t count = initial == 8 ? 257 : 65537;
        std::vector<Search::Node*> nodes;
        auto capacity = initial;
        int resizes = 0;
        for (std::size_t i = 0; i < count; ++i) {
            auto copy = bc; copy.player.curHp = static_cast<int>(1000 + i);
            auto *node = search.getOrCreateNode(std::move(copy));
            require(search.lastNodeWasCreated, "unique resize fixture state deduped");
            node->simulationCount = i + 1; node->evaluationSum = i * 0.25;
            nodes.push_back(node);
            if (search.stateToNode.size() != capacity) {
                require(search.stateToNode.size() == capacity * 2, "dedup growth must double");
                capacity *= 2; ++resizes;
                std::cout << "dedup_growth capacity=" << capacity << " entries=" << search.stateToNodeUsed << '\n';
            }
            require(search.stateToNodeUsed == i + 1 && search.stateToNodeUsed <= capacity / 2,
                    "dedup occupancy accounting failed");
        }
        require(resizes >= 2, "fixture must force several resizes");
        for (std::size_t i = 0; i < count; ++i) {
            auto copy = *nodes[i]->state;
            require(search.getOrCreateNode(std::move(copy)) == nodes[i] && !search.lastNodeWasCreated,
                    "resize lost prior state or duplicated node");
            require(nodes[i]->simulationCount == static_cast<std::int64_t>(i + 1)
                    && nodes[i]->evaluationSum == i * 0.25, "resize changed statistics");
        }
        require(search.poolUsed == count + 1 && search.randGen == rng && search.rolloutAgent.rng == rolloutRng,
                "resize changed node count or RNG");
        search.search(32); validateStorage(search);
        const auto grown = search.stateToNode.size();
        search.rerootAt(search.root, true);
        require(search.stateToNode.size() == grown, "collection shrank dedup capacity");
        search.setRoot(bc);
        require(search.stateToNodeUsed == 0 && search.stateToNode.size() == grown,
                "fresh reset must clear occupancy without shrinking");
    }
}

void lazyReroot(const sts::BattleContext &bc) {
    Search search(bc);
    auto next = bc; next.player.curHp -= 1;
    auto *candidate = search.getOrCreateNode(std::move(next));
    next = bc; next.player.curHp -= 2;
    auto *orphan = search.getOrCreateNode(std::move(next));
    orphan->simulationCount = 37; orphan->evaluationSum = 12.25;
    const auto slots = search.stateToNode;
    const auto nodes = search.allNodes.size(), states = search.decisionStates.size();
    search.rerootAt(candidate);
    require(search.allNodes.size() == nodes && search.poolUsed == nodes
            && search.decisionStates.size() == states, "below-cap reroot reclaimed baseline history");
    for (std::size_t i = 0; i < slots.size(); ++i)
        require(slots[i].hash == search.stateToNode[i].hash && slots[i].node == search.stateToNode[i].node,
                "below-cap reroot changed dedup table");
    next = *orphan->state;
    require(search.getOrCreateNode(std::move(next)) == orphan && !search.lastNodeWasCreated
            && orphan->simulationCount == 37 && orphan->evaluationSum == 12.25,
            "below-cap reroot lost orphan transposition statistics");
    search.search(32);
    validateStorage(search);
}

void repeatedRerootCanary(const sts::BattleContext &bc, std::int64_t cap) {
    Search search(bc);
    search.explorationParameter = search.explorationParameterChance = 25.0;
    search.chanceWideningC = search.endTurnWideningC = 3.7028;
    search.chanceWideningAlpha = search.endTurnWideningAlpha = 0.52389;
    std::size_t historical = search.poolUsed, reclaimed = 0;
    int crossings = 0, reroots = 0, compactions = 0;
    std::size_t peakNodes = 0, peakStates = 0, peakReachable = 0, capacity = search.stateToNode.size();
    int resizes = 0;
    double peakLoad = 0;
    for (int decision = 0; decision < 32; ++decision) {
        const auto previous = search.poolUsed;
        search.search(10000);
        historical += search.poolUsed - previous;
        while (capacity < search.stateToNode.size()) { capacity *= 2; ++resizes; }
        peakLoad = std::max(peakLoad, double(search.stateToNodeUsed) / search.stateToNode.size());
        validateStorage(search);
        peakNodes = std::max(peakNodes, search.poolUsed);
        peakStates = std::max(peakStates, search.decisionStatesUsed);
        Search::Node *candidate = nullptr;
        for (const auto &edge : search.root->edges) {
            // Follow a legal expanded END_TURN outcome to stress discard/reuse
            // across turns rather than evaluate the search's action quality.
            if (edge.action.getActionType() != sts::search::ActionType::END_TURN || !edge.node) continue;
            candidate = edge.node;
            if (candidate->isRandomNode) {
                require(!candidate->edges.empty(), "repeated canary needs sampled outcome");
                candidate = candidate->edges.front().node;
            }
            break;
        }
        require(candidate && !candidate->isRandomNode, "repeated canary needs exact child");
        std::unordered_set<Search::Node*> reachable;
        std::vector<Search::Node*> pending{candidate};
        while (!pending.empty()) {
            auto *node = pending.back(); pending.pop_back();
            if (!reachable.insert(node).second) continue;
            if (node->isRandomNode) pending.push_back(node->parent);
            for (const auto &edge : node->edges) if (edge.node) pending.push_back(edge.node);
        }
        peakReachable = std::max(peakReachable, reachable.size());
        std::unordered_map<Search::Node*, Search::Node> snapshots;
        for (std::size_t i = 0; i < search.poolUsed; ++i)
            snapshots.emplace(search.allNodes[i].get(), *search.allNodes[i]);
        std::unordered_set<Search::Node*> dedupMembers;
        for (const auto &slot : search.stateToNode) if (slot.node) dedupMembers.insert(slot.node);
        const auto before = search.poolUsed;
        auto *oldRoot = search.root;
        search.root = candidate;
        const bool hasActions = !candidate->edges.empty();
        const auto expectedAction = hasActions ? search.getBestAction() : sts::search::Action{};
        search.root = oldRoot;
        const bool compact = search.allNodes.size() >= cap;
        search.rerootAt(candidate, compact);
        if (compact) ++compactions;
        require(!hasActions || search.getBestAction() == expectedAction,
                "repeated compaction changed retained-tree result");
        validateStorage(search);
        for (const auto &owned : search.allNodes) {
            const auto saved = snapshots.find(owned.get());
            require(saved != snapshots.end(), "reroot introduced a node");
            const auto &node = *owned, &old = saved->second;
            require(node.state == old.state && node.parent == old.parent && node.simulationCount == old.simulationCount
                    && node.victoryCount == old.victoryCount && node.evaluationSum == old.evaluationSum
                    && node.randomnessBase == old.randomnessBase && node.outcomesGenerated == old.outcomesGenerated,
                    "repeated compaction changed retained node");
            require(node.edges.size() == old.edges.size(), "repeated compaction changed edges");
            for (std::size_t i = 0; i < node.edges.size(); ++i)
                require(node.edges[i].node == old.edges[i].node && node.edges[i].action == old.edges[i].action
                        && node.edges[i].visitCount == old.edges[i].visitCount
                        && node.edges[i].rngAdvanceSteps == old.edges[i].rngAdvanceSteps,
                        "repeated compaction changed edge statistics");
            if (!node.isRandomNode && dedupMembers.count(owned.get())) {
                auto copy = *node.state;
                require(search.getOrCreateNode(std::move(copy)) == owned.get() && !search.lastNodeWasCreated,
                        "repeated canary lost retained dedup");
            }
        }
        reclaimed += before - search.poolUsed;
        ++reroots;
        require(search.allNodes.size() < cap, "repeated canary retained tree reaches production cap");
        if (compact && historical >= cap) ++crossings;
        std::cout << "repeated_reroot decision=" << decision << " simulations=10000 historical_nodes=" << historical
                  << " before_nodes=" << before << " old_32k_pressure=" << (before >= 32768)
                  << " reachable_nodes=" << reachable.size() << " reachable_32k_block=" << (reachable.size() >= 32768)
                  << " dedup_capacity=" << search.stateToNode.size() << " dedup_entries=" << search.stateToNodeUsed << " retained_nodes=" << search.poolUsed
                  << " compacted=" << compact << " cumulative_reclaimed=" << reclaimed << " allocated_cap_blocked=0" << std::endl;
        if (crossings >= 1) break;
        require(search.root->state->outcome == sts::Outcome::UNDECIDED,
                "canary ended before repeated historical-cap crossings");
    }
    require(crossings >= 1 && reroots >= 3, "canary must search/reroot repeatedly beyond historical cap");
    const auto retained = search.poolUsed;
    search.search(10000);
    historical += search.poolUsed - retained;
    validateStorage(search);

    std::cout << "repeated_reroot_canary PASS configured_cap=" << cap << " reroots=" << reroots << " historical_cap_reroots=" << crossings
              << " peak_reachable_nodes=" << peakReachable << " peak_live_nodes=" << peakNodes << " peak_states=" << peakStates
              << " dedup_capacity=" << search.stateToNode.size() << " dedup_entries=" << search.stateToNodeUsed
              << " resizes=" << resizes << " peak_sampled_load=" << peakLoad
              << " node_bytes=" << sizeof(Search::Node) << " state_bytes=" << sizeof(sts::BattleContext)
              << " compactions=" << compactions << " final_search_nodes=" << search.poolUsed << " historical_nodes=" << historical << '\n';
}

} // namespace
int main(int argc, char **argv) {
    try {
        sts::GameContext gc{}; // BattleContext keeps a non-owning pointer to this run state.
        const auto bc = fixture(gc);
        Search search(bc);
        historicalQueueIdentityTests(bc);
        if (argc > 1 && std::string(argv[1]) == "--reroot-canary") {
            compaction(bc, 10000);
            return 0;
        }
        if (argc > 1 && std::string(argv[1]) == "--repeated-reroot-canary") {
            gc.curHp = gc.maxHp = 400;
            sts::BattleContext stress{};
            stress.init(gc, sts::MonsterEncounter::JAW_WORM);
            const auto cap = argc > 2 && std::string(argv[2]) == "131072"
                ? 131072 : silver_bridge::kSilverProductionReuseCap;
            require(argc <= 2 || std::string(argv[2]) == "131072", "canary override must be 131072");
            repeatedRerootCanary(stress, cap);
            return 0;
        }
        if (argc > 1 && std::string(argv[1]) == "--gamble-microbenchmark") {
            const int simulations = argc > 2 ? std::stoi(argv[2]) : 10000;
            const auto expectedRootActions = argc > 3 ? static_cast<std::size_t>(std::stoul(argv[3])) : 3;
            require(simulations > 0, "GAMBLE microbenchmark simulations must be positive");
            gambleMicrobenchmark(gc, simulations, expectedRootActions);
            return 0;
        }
        if (argc > 1 && std::string(argv[1]) == "--potion-microbenchmark") {
            const int simulations = argc > 2 ? std::stoi(argv[2]) : 10000;
            const auto expectedRootActions = argc > 3 ? static_cast<std::size_t>(std::stoul(argv[3])) : 2;
            const bool distinctPotions = argc > 4 && std::string(argv[4]) == "distinct";
            require(argc <= 4 || distinctPotions, "potion microbenchmark mode must be distinct when provided");
            require(simulations > 0, "potion microbenchmark simulations must be positive");
            potionMicrobenchmark(gc, simulations, expectedRootActions, distinctPotions);
            return 0;
        }
        dedupGrowth(bc);
        cardActionCanonicalization(bc);
        uidFragmentationDiagnostic(bc);
        singleCardSelectCanonicalization(bc);
        contractedSelectionExperimentFixtures(gc);
        gambleMultiplicityCanonicalization(bc);
        potionActionCanonicalization(gc, bc);
        sameTurnDominanceAuditFixtures(gc);
        lazyReroot(bc);
        compaction(bc, 0);
        selection(search); widening(search); rootPriorSelection(search);
        internalFpuSelectionFixtures(bc);
        traceParity(bc, false); traceParity(bc, true); rootHash(bc);
        retainedStateGrowth(bc);
        storage(bc, argc > 1 && std::string(argv[1]) == "--storage-metrics");
        std::cout << "silver_search_optimization PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "silver_search_optimization FAIL: " << error.what() << '\n';
        return 1;
    }
}
