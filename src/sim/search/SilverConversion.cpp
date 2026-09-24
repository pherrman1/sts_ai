// Explicit live-observation to isolated-Silver conversion helpers.
#include "sim/search/SilverConversion.h"

#include <algorithm>

#include "combat/BattleContext.h"
#include "constants/Relics.h"
#include "game/GameContext.h"

namespace sts::search {
namespace {

bool sameCard(const CardInstance &a, const CardInstance &b) {
    return a.id == b.id && a.uniqueId == b.uniqueId && a.specialData == b.specialData
        && a.cost == b.cost && a.costForTurn == b.costForTurn && a.upgraded == b.upgraded
        && a.freeToPlayOnce == b.freeToPlayOnce && a.retain == b.retain;
}

bool sameIdentity(const CardInstance &a, const CardInstance &b) {
    return a.id == b.id && a.uniqueId == b.uniqueId;
}

bool cardLess(const CardInstance &a, const CardInstance &b) {
    if (a.id != b.id) return a.id < b.id;
    if (a.uniqueId != b.uniqueId) return a.uniqueId < b.uniqueId;
    if (a.specialData != b.specialData) return a.specialData < b.specialData;
    if (a.cost != b.cost) return a.cost < b.cost;
    if (a.costForTurn != b.costForTurn) return a.costForTurn < b.costForTurn;
    if (a.upgraded != b.upgraded) return a.upgraded < b.upgraded;
    if (a.freeToPlayOnce != b.freeToPlayOnce) return a.freeToPlayOnce < b.freeToPlayOnce;
    return a.retain < b.retain;
}

bool eraseKnown(std::vector<CardInstance> &unknown, const CardInstance &known) {
    auto it = std::find_if(unknown.begin(), unknown.end(), [&](const CardInstance &candidate) {
        return sameIdentity(candidate, known);
    });
    if (it == unknown.end()) return false;
    unknown.erase(it);
    return true;
}

bool sameCards(const std::vector<CardInstance> &a, const std::vector<CardInstance> &b) {
    return a.size() == b.size() && std::equal(a.begin(), a.end(), b.begin(), sameCard);
}

silver_bridge::CardWire toWire(const CardInstance &card) {
    return {static_cast<std::int16_t>(card.id), card.uniqueId, card.specialData,
            card.cost, card.costForTurn, card.upgraded, card.freeToPlayOnce, card.retain};
}

template <typename Cards>
std::vector<silver_bridge::CardWire> canonicalPileWire(const Cards &cards) {
    std::vector<CardInstance> sorted(cards.begin(), cards.end());
    std::sort(sorted.begin(), sorted.end(), cardLess);
    std::vector<silver_bridge::CardWire> result;
    result.reserve(sorted.size());
    for (const auto &card : sorted) result.push_back(toWire(card));
    return result;
}

silver_bridge::PileWire toWire(const SilverDrawPileObservation &pile) {
    silver_bridge::PileWire out;
    out.fullOrderObserved = pile.fullOrderObserved;
    out.valid = pile.valid;
    for (const auto &card : pile.knownBottom) out.knownBottom.push_back(toWire(card));
    for (const auto &card : pile.unknown) out.unknown.push_back(toWire(card));
    for (const auto &card : pile.knownTop) out.knownTop.push_back(toWire(card));
    return out;
}

silver_bridge::MonsterRollInputsWire toWire(const HiddenIntentRollInputs &in) {
    return {in.curHp, in.maxHp, in.knightCurHp, in.knightMaxHp, in.monsterTurnNumber,
            in.miscInfo, in.aliveCount, in.monstersAlive, in.knightAlive,
            in.playerConstricted, in.asleep, in.halfDead};
}

silver_bridge::CardQueueItemWire toWire(const CardQueueItem &item) {
    silver_bridge::CardQueueItemWire out;
    out.card = toWire(item.card);
    out.target = item.target;
    out.isEndTurn = item.isEndTurn;
    out.triggerOnUse = item.triggerOnUse;
    out.ignoreEnergyTotal = item.ignoreEnergyTotal;
    out.energyOnUse = item.energyOnUse;
    out.freeToPlay = item.freeToPlay;
    out.randomTarget = item.randomTarget;
    out.autoplay = item.autoplay;
    out.regretCardCount = item.regretCardCount;
    out.purgeOnUse = item.purgeOnUse;
    out.exhaustOnUse = item.exhaustOnUse;
    return out;
}

} // namespace

SilverDrawPileObservation makeSilverDrawPileObservation(
    const BattleContext &live, const CombatKnowledgeState &knowledge) {
    SilverDrawPileObservation out;
    out.fullOrderObserved = knowledge.fullDrawPileOrderObserved;
    if (out.fullOrderObserved) {
        // Frozen Eye is the sole permitted read of live ordering. This branch
        // preserves the concrete bottom-to-top vector exactly.
        out.knownTop.assign(live.cards.drawPile.begin(), live.cards.drawPile.end());
        return out;
    }

    // Reading contents is permitted: the player knows which cards remain.
    // Canonical sorting immediately destroys the live vector order.
    out.unknown.assign(live.cards.drawPile.begin(), live.cards.drawPile.end());
    out.knownBottom = knowledge.knownBottom;
    out.knownTop = knowledge.knownTop;
    for (const auto &c : out.knownBottom) out.valid = eraseKnown(out.unknown, c) && out.valid;
    for (const auto &c : out.knownTop) out.valid = eraseKnown(out.unknown, c) && out.valid;
    if (!out.valid) {
        // A stale observer must never be repaired by inspecting positions.
        // Drop all positional facts and retain only the observable multiset.
        out.knownBottom.clear();
        out.knownTop.clear();
        out.unknown.assign(live.cards.drawPile.begin(), live.cards.drawPile.end());
    }
    std::sort(out.unknown.begin(), out.unknown.end(), cardLess);
    return out;
}

silver::CardPile makeSilverCardPile(const BattleContext &live,
                                   const CombatKnowledgeState &knowledge) {
    const SilverDrawPileObservation view = makeSilverDrawPileObservation(live, knowledge);
    silver::CardPile pile;
    pile.assignInformationState(view.knownBottom, view.unknown, view.knownTop,
                                view.fullOrderObserved);
    return pile;
}

bool liveMonsterIntentIsObservable(const BattleContext &live) {
    return !live.player.hasRelic<RelicId::RUNIC_DOME>();
}

bool sameSilverDrawPileObservation(const SilverDrawPileObservation &a,
                                   const SilverDrawPileObservation &b) {
    return a.fullOrderObserved == b.fullOrderObserved && a.valid == b.valid
        && sameCards(a.knownBottom, b.knownBottom) && sameCards(a.unknown, b.unknown)
        && sameCards(a.knownTop, b.knownTop);
}

SilverRunContext makeSilverRunContext(const GameContext &live) {
    SilverRunContext out;
    out.act = live.act;
    out.omamoriOwned = live.relics.has(RelicId::OMAMORI);
    out.omamoriValue = out.omamoriOwned ? live.relics.getRelicValue(RelicId::OMAMORI) : 0;
    return out;
}

SilverBattleStateConversion makeSilverBattleStateConversion(
        const BattleContext &live, const CombatKnowledgeState &knowledge,
        const SilverRunContext &runContext, std::uint64_t isolatedSearchSeed) {
    SilverBattleStateConversion conversion;
    auto &out = conversion.wire;
    const auto invalidate = [&](std::string reason) {
        out.valid = false;
        if (conversion.failureReason.empty()) conversion.failureReason = std::move(reason);
    };
    if (knowledge.consistencyFailureCount != 0) {
        invalidate("knowledge_consistency_failure count="
                   + std::to_string(knowledge.consistencyFailureCount));
    }
    out.fullDrawOrderObserved = knowledge.fullDrawPileOrderObserved;
    // This is observer configuration captured from GameContext before live
    // monster initialization. Reading Player's initialized relic state here
    // cannot repair a missing pre-init configuration: that would conceal a
    // lifecycle error and could leak the materialized live move.
    out.intentsHidden = knowledge.hiddenMonsterIntents;
    if (out.intentsHidden != !liveMonsterIntentIsObservable(live)) {
        invalidate("monster_intent_visibility_lifecycle_mismatch configured_hidden="
                   + std::to_string(out.intentsHidden ? 1 : 0));
    }
    out.isolatedSearchSeed = isolatedSearchSeed;
    out.observedGeneration = knowledge.generation;
    out.floorNum = live.floorNum;
    out.encounter = static_cast<int>(live.encounter);
    out.loopCount = live.loopCount;
    out.energyWasted = live.energyWasted;
    out.cardsDrawn = live.cardsDrawn;
    out.act = runContext.act;
    out.omamoriOwned = runContext.omamoriOwned;
    out.omamoriValue = runContext.omamoriValue;
    out.ascension = live.ascension;
    out.outcome = static_cast<int>(live.outcome);
    out.inputState = static_cast<int>(live.inputState);
    out.historicalQueueItemAtSource =
        (live.inputState == InputState::PLAYER_NORMAL || live.inputState == InputState::CARD_SELECT)
        && live.outcome == Outcome::UNDECIDED && !live.isBattleOver()
        && !live.endTurnQueued && !live.turnHasEnded
        && live.actionQueue.size == 0 && live.cardQueue.size == 0;
    out.monsterTurnIdx = live.monsterTurnIdx;
    out.endTurnQueued = live.endTurnQueued;
    out.turnHasEnded = live.turnHasEnded;
    out.skipMonsterTurn = live.skipMonsterTurn;
    out.potionCount = live.potionCount;
    out.potionCapacity = live.potionCapacity;
    for (std::size_t i = 0; i < out.potions.size(); ++i) out.potions[i] = static_cast<std::int16_t>(live.potions[i]);
    out.turn = live.turn;
    out.miscBits = static_cast<std::uint32_t>(live.miscBits.to_ulong());

    const Player &p = live.player;
    auto &wp = out.player;
    wp.characterClass = static_cast<std::int16_t>(p.cc);
    wp.gold = p.gold; wp.curHp = p.curHp; wp.maxHp = p.maxHp; wp.energy = p.energy;
    wp.energyPerTurn = p.energyPerTurn; wp.cardDrawPerTurn = p.cardDrawPerTurn;
    wp.stance = static_cast<std::int16_t>(p.stance); wp.orbSlots = p.orbSlots;
    wp.lastTargetedMonster = p.lastTargetedMonster; wp.block = p.block; wp.artifact = p.artifact;
    wp.dexterity = p.dexterity; wp.focus = p.focus; wp.strength = p.strength;
    wp.justAppliedBits = p.justAppliedBits; wp.statusBits0 = p.statusBits0; wp.statusBits1 = p.statusBits1;
    for (const auto &[status, amount] : p.statusMap) wp.statusMap.emplace_back(static_cast<std::int16_t>(status), amount);
    wp.relicBits0 = p.relicBits0; wp.relicBits1 = p.relicBits1;
    wp.relicCounters = {p.happyFlowerCounter, p.incenseBurnerCounter, p.inkBottleCounter,
                        p.inserterCounter, p.nunchakuCounter, p.penNibCounter, p.sundialCounter};
    wp.haveUsedNecronomiconThisTurn = p.haveUsedNecronomiconThisTurn;
    wp.combustHpLoss = p.combustHpLoss; wp.devaFormEnergyPerTurn = p.devaFormEnergyPerTurn;
    wp.echoFormCardsDoubled = p.echoFormCardsDoubled; wp.panacheCounter = p.panacheCounter;
    wp.cardsPlayedThisTurn = p.cardsPlayedThisTurn; wp.attacksPlayedThisTurn = p.attacksPlayedThisTurn;
    wp.skillsPlayedThisTurn = p.skillsPlayedThisTurn; wp.cardsDiscardedThisTurn = p.cardsDiscardedThisTurn;
    wp.orangePelletsCardTypesPlayed = static_cast<std::uint8_t>(p.orangePelletsCardTypesPlayed.to_ulong());
    wp.lastAttackUnblockedDamage = p.lastAttackUnblockedDamage;
    wp.timesDamagedThisCombat = p.timesDamagedThisCombat;
    wp.bombs = {p.bomb1, p.bomb2, p.bomb3};

    out.monsterCount = live.monsters.monsterCount;
    out.monstersAlive = live.monsters.monstersAlive;
    out.extraRollMoveOnTurn = static_cast<std::uint8_t>(live.monsters.extraRollMoveOnTurn.to_ulong());
    out.skipMonsterTurnBits = static_cast<std::uint8_t>(live.monsters.skipTurn.to_ulong());
    for (std::size_t i = 0; i < out.monsters.size(); ++i) {
        const Monster &m = live.monsters.arr[i];
        auto &wm = out.monsters[i];
        wm.idx = m.idx; wm.id = static_cast<std::int16_t>(m.id); wm.curHp = m.curHp;
        wm.maxHp = m.maxHp; wm.block = m.block; wm.isEscapingB = m.isEscapingB;
        wm.halfDead = m.halfDead; wm.escapeNext = m.escapeNext;
        if (!out.intentsHidden) {
            wm.moveHistory = {static_cast<std::int16_t>(m.moveHistory[0]), static_cast<std::int16_t>(m.moveHistory[1])};
            wm.miscInfo = m.miscInfo;
        } else if (m.idx >= 0 && knowledge.hasPublicMonsterState[i]) {
            // Do not read the concrete immediate live roll under Runic Dome.
            // For a deferred chain this is the public pre-roll snapshot; once
            // materialized (e.g. Spot Weakness) it is the public result.
            wm.moveHistory = knowledge.publicMonsterMoveHistory[i];
            wm.miscInfo = knowledge.publicMonsterMiscInfo[i];
        } else if (m.idx >= 0) {
            invalidate("missing_public_hidden_intent_state monster_index="
                       + std::to_string(i) + " monster_id="
                       + std::to_string(static_cast<int>(m.id)));
        }
        wm.statusBits = m.statusBits;
        wm.smallPowers = {m.artifact, m.blockReturn, m.choked, m.corpseExplosion, m.lockOn,
                          m.mark, m.metallicize, m.platedArmor, m.poison, m.regen, m.shackled};
        wm.strength = m.strength; wm.vulnerable = m.vulnerable; wm.weak = m.weak;
        wm.uniquePower0 = m.uniquePower0; wm.uniquePower1 = m.uniquePower1;
        if (out.intentsHidden) {
            wm.pendingMoveRolls = knowledge.pendingHiddenIntentRolls[i];
            wm.pendingRollInputs = toWire(knowledge.pendingHiddenIntentInputs[i]);
            for (const auto &entry : knowledge.pendingHiddenIntentInputHistory[i])
                wm.pendingRollInputHistory.push_back(toWire(entry));
            // Looter/Mugger sample their next move directly inside takeTurn,
            // rather than through rollMove. At a post-turn Runic root the
            // live concrete result is hidden, so carry only the public rule
            // into the isolated model's deferred direct-choice state.
            if (knowledge.hasUnrepresentableHiddenIntent[i]) {
                const auto publicMove = knowledge.publicMonsterMoveHistory[i][0];
                if (m.id == MonsterId::LOOTER
                        && publicMove == static_cast<std::int16_t>(MonsterMoveId::LOOTER_MUG)) {
                    wm.pendingDirectMoveChoice = 1;
                } else if (m.id == MonsterId::MUGGER
                        && publicMove == static_cast<std::int16_t>(MonsterMoveId::MUGGER_MUG)) {
                    wm.pendingDirectMoveChoice = 2;
                } else {
                    invalidate("unsupported_deferred_hidden_intent monster_index="
                               + std::to_string(i) + " monster_id="
                               + std::to_string(static_cast<int>(m.id))
                               + " public_move=" + std::to_string(publicMove));
                }
            }
        }
    }

    out.nextUniqueCardId = live.cards.nextUniqueCardId;
    out.handNormalityCount = live.cards.handNormalityCount; out.handPainCount = live.cards.handPainCount;
    out.strikeCount = live.cards.strikeCount; out.handBloodCardCount = live.cards.handBloodCardCount;
    out.drawPileBloodCardCount = live.cards.drawPileBloodCardCount;
    out.discardPileBloodCardCount = live.cards.discardPileBloodCardCount;
    for (int i = 0; i < live.cards.cardsInHand; ++i) out.hand.push_back(toWire(live.cards.hand[i]));
    for (const auto &card : live.cards.limbo) out.limbo.push_back(toWire(card));
    for (std::size_t i = 0; i < out.stasisCards.size(); ++i) out.stasisCards[i] = toWire(live.cards.stasisCards[i]);
    out.drawPile = toWire(makeSilverDrawPileObservation(live, knowledge));
    // A stale positional fact is a boundary failure. Propagate the draw-pile
    // observation's fail-closed validity into the complete protocol so the
    // private materializer can never rebuild it from a hidden live position.
    if (!out.drawPile.valid) {
        invalidate("stale_draw_pile_positional_knowledge known_bottom="
                   + std::to_string(knowledge.knownBottom.size())
                   + " known_top=" + std::to_string(knowledge.knownTop.size())
                   + " live_size=" + std::to_string(live.cards.drawPile.size()));
    }
    out.discardPile.unknown = canonicalPileWire(live.cards.discardPile);
    out.exhaustPile.unknown = canonicalPileWire(live.cards.exhaustPile);

    const auto &select = live.cardSelectInfo;
    for (std::size_t i = 0; i < out.cardSelect.cards.size(); ++i) out.cardSelect.cards[i] = static_cast<std::int16_t>(select.cards[i]);
    out.cardSelect.canPickZero = select.canPickZero; out.cardSelect.canPickAnyNumber = select.canPickAnyNumber;
    out.cardSelect.pickCount = select.pickCount; out.cardSelect.data0 = select.data0;
    out.cardSelect.task = static_cast<std::int16_t>(select.cardSelectTask);
    // The live simulator has atomic multi-select actions and no mutable
    // selected-bit state at a decision boundary; Discovery has its legacy true default.
    out.cardSelect.setCostToZero = true;
    out.cardSelect.selectedBits = 0;
    out.curCardQueueItem = toWire(live.curCardQueueItem);
    return conversion;
}

silver_bridge::BattleStateWire makeSilverBattleStateWire(
        const BattleContext &live, const CombatKnowledgeState &knowledge,
        const SilverRunContext &runContext, std::uint64_t isolatedSearchSeed) {
    return makeSilverBattleStateConversion(
        live, knowledge, runContext, isolatedSearchSeed).wire;
}

} // namespace sts::search
