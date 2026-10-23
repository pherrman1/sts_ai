//
// Created by gamerpuppy on 7/5/2021.
//

#include "combat/Monster.h"

#include "game/Random.h"
#include <stdexcept>
#include <map>
#include <vector>
#include <algorithm>
#include <cstdlib>
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"

using namespace sts;

void Monster::setRandomHp(Random &hpRng, bool higherHp) {
    auto hpRange = monsterHpRange[static_cast<int>(id)][higherHp ? 1 : 0];
    curHp = hpRng.random(hpRange[0], hpRange[1]);
    maxHp = curHp;
}

void Monster::applyStartOfTurnPowers(BattleContext &bc) {
    if (!hasStatus<MS::BARRICADE>()) {
        block = 0;
    }

    if (hasStatus<MS::CHOKED>()) {
        setHasStatus<MS::CHOKED>(false);
    }

    if (hasStatus<MS::FLIGHT>()) {
        setStatus<MS::FLIGHT>(bc.ascension >= 17 ? 4 : 3);
    }

    if (hasStatus<MS::INVINCIBLE>()) {
        setStatus<MS::INVINCIBLE>(bc.ascension >= 19 ? 200 : 300);
    }

    if (hasStatus<MS::POISON>() && !bc.monsters.areMonstersBasicallyDead()) {
        bc.addToBot(Actions::PoisonLoseHpAction(this->idx));
    }
}

void Monster::applyEndOfTurnTriggers(BattleContext &bc) {
    // Monster Powers atEndOfTurnPreEndTurnCards and atEndOfTurn
    if (hasStatus<MS::METALLICIZE>()) {
        addBlock(getStatus<MS::METALLICIZE>());
    }

    if (hasStatus<MS::MALLEABLE>()) {
        setStatus<MS::MALLEABLE>(3);
    }

    if (hasStatus<MS::PLATED_ARMOR>()) {
        addBlock(getStatus<MS::PLATED_ARMOR>());
    }

    if (hasStatus<MS::INTANGIBLE>()) {
        decrementStatus<MS::INTANGIBLE>();
    }

    if (hasStatus<MS::REGEN>()) {
        heal(getStatus<MS::REGEN>());
    }

    if (hasStatus<MS::SHACKLED>()) {
        buff<MS::STRENGTH>(getStatus<MS::SHACKLED>());
        removeStatus<MS::SHACKLED>();
    }
}

void Monster::applyEndOfRoundPowers(BattleContext &bc) {
    // Monster Powers atEndOfRound
    if (hasStatus<MS::RITUAL>()) { // sort of a hack, RitualPower contains a skipFirst boolean
        if (wasJustApplied<MS::RITUAL>()) {
            setJustApplied<MS::RITUAL>(false);
        } else {
            buff<MS::STRENGTH>(getStatus<MS::RITUAL>());
        }
    }

    if (hasStatus<MS::SLOW>()) {
        setStatus<MS::SLOW>(0);
    }

    if (hasStatus<MS::LOCK_ON>()) {
        decrementStatus<MS::LOCK_ON>();
    }

    if (hasStatus<MS::WEAK>()) {
        if (wasJustApplied<MS::WEAK>()) {
            setJustApplied<MS::WEAK>(false);
        } else {
            decrementStatus<MS::WEAK>();
        }
    }

    if (hasStatus<MS::VULNERABLE>()) {
        if (wasJustApplied<MS::VULNERABLE>()) {
            setJustApplied<MS::VULNERABLE>(false);
        } else {
            decrementStatus<MS::VULNERABLE>();
        }
    }

    if (hasStatus<MS::GENERIC_STRENGTH_UP>()) {
        buff<MS::STRENGTH>(getStatus<MS::GENERIC_STRENGTH_UP>());
    }

}

void Monster::resetForNewOccupant(int monsterIdx, MonsterId monsterId, int /*ascension*/) {
    const auto previousGeneration = occupantGeneration;
    if (previousGeneration == UINT32_MAX) {
        throw std::runtime_error("monster occupant generation overflow");
    }
    *this = Monster{};
    occupantGeneration = previousGeneration + 1;
    id = monsterId;
    idx = monsterIdx;
    search::emitMonsterOccupantReset(idx, occupantGeneration);
}

void Monster::construct(BattleContext &bc, MonsterId monsterId, int monsterIdx) {
    resetForNewOccupant(monsterIdx, monsterId, bc.ascension);
    initHp(bc.monsterHpRng, bc.ascension);

    switch (id) {
        case MonsterId::GREEN_LOUSE:
        case MonsterId::RED_LOUSE:
            if (bc.ascension >= 2) {
                miscInfo = bc.monsterHpRng.random(6, 8);
            } else {
                miscInfo = bc.monsterHpRng.random(5, 7);
            }
            break;

        case MonsterId::DARKLING:
            if (bc.ascension >= 2) {
                miscInfo = bc.monsterHpRng.random(9, 13);
            } else {
                miscInfo = bc.monsterHpRng.random(7, 11);
            }
            break;

        default:
            break;
    }
    latentDamageMask = latentDamagePrior(id, bc.ascension);
    latentDamageMaterialized = latentDamageMask != 0;
    search::emitMonsterLatentDamagePrior(idx, latentDamageMask);
}

const char *Monster::getName() const {
    return monsterIdStrings[static_cast<int>(id)];
}

bool Monster::hasStatusInternal(MonsterStatus s) const {
    return statusBits & (1ULL << (int)s);
}

int Monster::getStatusInternal(MonsterStatus s) const {
    if (s == MS::STRENGTH) {
        return strength;
    }

    if (!hasStatusInternal(s)) {
        return 0;
    }

    switch (s) {
        case MS::ARTIFACT:
            return artifact;

        case MS::BLOCK_RETURN:
            return blockReturn;

        case MS::CHOKED:
            return choked;

        case MS::CORPSE_EXPLOSION:
            return corpseExplosion;

        case MS::LOCK_ON:
            return lockOn;

        case MS::MARK:
            return mark;

        case MS::METALLICIZE:
            return metallicize;

        case MS::PLATED_ARMOR:
            return platedArmor;

        case MS::POISON:
            return poison;

        case MS::REGEN:
            return regen;

        case MS::SHACKLED:
            return shackled;

        case MS::VULNERABLE:
            return vulnerable;

        case MS::WEAK:
            return weak;

        case MS::ANGRY:
        case MS::BEAT_OF_DEATH:
        case MS::CURIOSITY:
        case MS::CURL_UP:
        case MS::ENRAGE:
        case MS::FADING:
        case MS::FLIGHT:
        case MS::GENERIC_STRENGTH_UP:
        case MS::INTANGIBLE:
        case MS::MALLEABLE:
        case MS::MODE_SHIFT:
        case MS::RITUAL:
        case MS::SLOW:
        case MS::SPORE_CLOUD:
        case MS::THIEVERY:
        case MS::THORNS:
        case MS::TIME_WARP:
            return uniquePower0;

        case MS::INVINCIBLE:
        case MS::REACTIVE:
        case MS::SHARP_HIDE:
            return uniquePower1;

        // boolean powers
        case MS::ASLEEP:
        case MS::BARRICADE:
        case MS::MINION:
        case MS::MINION_LEADER:
        case MS::PAINFUL_STABS:
        case MS::REGROW:
        case MS::SHIFTING:
        case MS::STASIS:
            return true; // already did status check above

        default:
#ifdef sts_asserts
            assert(false);
#endif
            return 0;
    }
}

void Monster::enterGuardianDefensiveMode() {
    removeStatus<MS::MODE_SHIFT>();
    cancelPendingMove();
    setMove(MMID::THE_GUARDIAN_DEFENSIVE_MODE);
    search::emitHiddenMonsterIntentMaterialized(
        idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
}

void Monster::wakeMetallicize(BattleContext &bc) {
    // Lagavulin.damage queues ChangeStateAction("OPEN"), whose changeState
    // queues ReducePowerAction(Metallicize, 8): the wake subtracts 8, the same
    // as the natural wake (STS_LAGAVULIN_WAKE_METALLICIZE_FIX).
    if (lagavulinWakeMetallicizeFix() && getStatus<MS::METALLICIZE>() > 8) {
        decrementStatus<MS::METALLICIZE>(8);
    } else { // ReducePowerAction removes the power when the amount runs out
        removeStatus<MS::METALLICIZE>();
    }
}

bool Monster::isAlive() const {
    return curHp > 0;
}

bool Monster::isTargetable() const {
    return !isDeadOrEscaped();
}

bool Monster::isDying() const {
    return curHp <= 0;
}

bool Monster::isEscaping() const {
    return isEscapingB;
}

bool Monster::isDeadOrEscaped() const {
    return isDying() || isHalfDead() || isEscaping();
}

bool Monster::isHalfDead() const {
    return halfDead;
}

bool Monster::doesEscapeNext() const {
    return escapeNext;
}

bool Monster::isAttacking() const {
    return isMoveAttack(moveHistory[0]);
}

void Monster::heal(int amount) {
#ifdef sts_asserts
    if (amount < 0) {
        assert (false);
    }
#endif

    curHp = std::min(maxHp, curHp + amount);
}

void Monster::addBlock(int amount) {
    block += amount;
}

void Monster::die(BattleContext &bc) {
    // Mugger.die starts with playDeathSfx, which draws aiRng.random(2)
    // (STS_MUGGER_DEATH_RNG_FIX=0 restores the legacy engine, which drew nothing).
    if (id == MonsterId::MUGGER && muggerDeathRngFix()) {
        bc.aiRng.random(2);
    }
    --bc.monsters.monstersAlive;

    if (id == MonsterId::AWAKENED_ONE && !miscInfo) { // is awakened one stage 1 // todo change to status
        halfDead = true;
        removeDebuffs();
        removeStatus<MS::CURIOSITY>();
        cancelPendingMove();
        setMove(MonsterMoveId::AWAKENED_ONE_REBIRTH);
        bc.addToBot(Actions::SetMonsterMove(idx,MMID::AWAKENED_ONE_REBIRTH)); // vanilla queues this after in-flight rolls
        search::emitHiddenMonsterIntentMaterialized(
            idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
        bc.cardQueue.clear();

    } else if ((bc.monsters.monstersAlive == 0 && !bc.monsters.anyHalfDead()) || hasStatus<MS::MINION_LEADER>()) {
//            bc.cleanCardQueue(); // todo should this really return like this?
        if (bc.outcome == Outcome::UNDECIDED) {
            bc.outcome = Outcome::PLAYER_VICTORY;
        }
        return;
    }

    if ((id == MonsterId::SPIRE_SHIELD || id == MonsterId::SPIRE_SPEAR)
            && bc.player.hasStatus<PS::SURROUNDED>() && spireSurroundedDeathFix()) {
        bc.player.removeStatus<PS::SURROUNDED>();
    }

    if (hasStatus<MS::SPORE_CLOUD>()) {
        // spore cloud always has a value of 2 in game
        bc.addToTop( Actions::DebuffPlayer<PS::VULNERABLE>(2, bc.turnHasEnded) );

    } else if (hasStatus<MS::REGROW>()) {
        resetAllStatusEffects();
        cancelPendingMove();
        setMove(MMID::DARKLING_REGROW);
        bc.addToBot(Actions::SetMonsterMove(idx,MMID::DARKLING_REGROW)); // vanilla queues this after in-flight rolls
        search::emitHiddenMonsterIntentMaterialized(
            idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
        halfDead = true;

    } else if (hasStatus<MS::STASIS>()) {
        returnStasisCard(bc);
    }

    if (hasStatus<MS::CORPSE_EXPLOSION>()) {
        int damage = maxHp * getStatus<MS::CORPSE_EXPLOSION>();
        bc.addToBot( Actions::DamageAllEnemy(damage) );
    }

    if (bc.player.hasRelic<RelicId::GREMLIN_HORN>()) {
        bc.addToBot( Actions::GainEnergy(1) );
        bc.addToBot( Actions::DrawCards(1) );
    }

    if (bc.player.hasRelic<RelicId::THE_SPECIMEN>()) {
        bc.addToBot( Actions::SetState(InputState::SELECT_ENEMY_THE_SPECIMEN_APPLY_POISON) );
    }
}

void Monster::suicideAction(BattleContext &bc) {
    if (!isAlive()) {
        return;
    }

    --bc.monsters.monstersAlive;
    curHp = 0;
    if (bc.monsters.monstersAlive == 0 && bc.outcome == Outcome::UNDECIDED) {
        bc.outcome = Outcome::PLAYER_VICTORY;
    }
}

void Monster::attackedUnblockedHelper(BattleContext &bc, int damage) { // todo, is this supposed to be only damage > 0 ????
    if (bc.player.hasRelic<RelicId::THE_BOOT>() && damage > 0 && damage < 5) {
        damage = 5;
    }

    if (bc.player.hasStatus<PS::ENVENOM>()) {
        bc.addToTop( Actions::DebuffEnemy<MS::POISON>(this->idx, bc.player.getStatus<PS::ENVENOM>()) );
    }

    if (hasStatus<MS::INVINCIBLE>()) {
        damage = std::min(damage, getStatus<MS::INVINCIBLE>());
        setStatus<MS::INVINCIBLE>(getStatus<MS::INVINCIBLE>() - damage);

    } else if (hasStatus<MS::PLATED_ARMOR>()) {
        decrementStatus<MS::PLATED_ARMOR>();
        if(!hasStatus<MS::PLATED_ARMOR>() && id == MonsterId::SHELLED_PARASITE) {
            cancelPendingMove();
            setMove(MMID::SHELLED_PARASITE_STUNNED);
            search::emitHiddenMonsterIntentMaterialized(
                idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
        }

    } else if (hasStatus<MS::CURL_UP>()) {
        // Java CurlUpPower.onAttacked requires damageAmount < currentHealth:
        // a lethal hit does not curl (STS_CURL_UP_LETHAL_FIX=0 restores).
        if (damage < curHp || !curlUpLethalFix()) {
            bc.addToBot(Actions::MonsterGainBlock(this->idx, getStatus<MS::CURL_UP>()) );
            setHasStatus<MS::CURL_UP>(false);
        }

    } else if (hasStatus<MS::FLIGHT>() && damage > 0) {
        auto flight = getStatus<MS::FLIGHT>();
        if (flight == 1) {
            cancelPendingMove();
            setMove(MMID::BYRD_STUNNED);
            search::emitHiddenMonsterIntentMaterialized(
                idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
        }
        // Java ReducePowerAction removes Flight at 0 (the Byrd is grounded): no more
        // halved damage and no start-of-turn reset (STS_BYRD_GROUNDED_FLIGHT_FIX=0 restores).
        if (flight == 1 && byrdGroundedFlightFix()) {
            removeStatus<MS::FLIGHT>();
        } else {
            setStatus<MS::FLIGHT>(flight-1);
        }

    } else if (hasStatus<MS::MALLEABLE>() || hasStatus<MS::REACTIVE>()) {
        if (hasStatus<MS::MALLEABLE>()) {
            const auto malleable = getStatus<MS::MALLEABLE>();
            bc.addToBot( Actions::MonsterGainBlock(this->idx, malleable) );
            setStatus<MS::MALLEABLE>(malleable+1);
        }
        if (hasStatus<MS::REACTIVE>()) {
            if (getStatus<MS::REACTIVE>() == 0) {
                setStatus<MS::REACTIVE>(1);
                bc.addToBot( Actions::ReactiveRollMove() );

            } else {
                setStatus<MS::REACTIVE>(getStatus<MS::REACTIVE>()+1);
            }
        }

    } else if (hasStatus<MS::THORNS>()) {
        bc.addToTop( Actions::DamagePlayer(getStatus<MS::THORNS>()) );

    } else if (hasStatus<MS::ASLEEP>()) {
        // lagavulin
        setHasStatus<MS::ASLEEP>(false);
        wakeMetallicize(bc);
        cancelPendingMove();
        setMove(MMID::LAGAVULIN_SLEEP);

    } else if (hasStatus<MS::SHIFTING>()) {
        addDebuff<MS::STRENGTH>(-damage);
        buff<MS::SHACKLED>(damage);
    }

    curHp -= damage;
    if (curHp <= 0) {
        curHp = 0;
        die(bc);
    } else {
        onHpLost(bc, damage);
    }
}

void Monster::attacked(BattleContext &bc, int damage) {
    if (isDeadOrEscaped()) { // these probably shouldn't happen
        std::cerr << bc.seed << " was dead when attacked" << idx << "\n" << bc;
        assert(false);
        return;
    }

    if (damage < 0) {// these probably shouldn't happen
        damage = 0;
    }

    if (hasStatus<MS::INTANGIBLE>()) {
        if (damage > 0) {
            damage = 1;
        }
    }

    if (hasStatus<MS::ANGRY>()) { // onAttacked
        buff<MS::STRENGTH>(getStatus<MS::ANGRY>());
    }

    const bool hadBlock = block > 0;
    const int tempDamage = damage;
    damage -= block;
    block = std::max(0, block - tempDamage);

    if (hadBlock && block == 0 && bc.player.hasRelic<RelicId::HAND_DRILL>()) {
        bc.addToBot(Actions::DebuffEnemy<MS::VULNERABLE>(idx, 2, false) );
    }

    if (damage > 0) { // todo can damage be zero???
        attackedUnblockedHelper(bc, damage);
    }
}

void Monster::damageUnblockedHelper(BattleContext &bc, int damage) {

    if (hasStatus<MS::INVINCIBLE>()) {
        damage = std::min(damage, getStatus<MS::INVINCIBLE>());
        setStatus<MS::INVINCIBLE>(getStatus<MS::INVINCIBLE>() - damage);
    }
        if (hasStatus<MS::ASLEEP>()) {
        // lagavulin
        setHasStatus<MS::ASLEEP>(false);
        wakeMetallicize(bc);
        cancelPendingMove();
        setMove(MMID::LAGAVULIN_SLEEP);
    }
    if (hasStatus<MS::SHIFTING>()) {
        addDebuff<MS::STRENGTH>(-damage);
        buff<MS::SHACKLED>(damage);
    }

    curHp = std::max(0, curHp-damage);
    if (curHp == 0) {
        die(bc);
    } else {
        onHpLost(bc, damage);
    }
}

void Monster::damage(BattleContext &bc, int damage) {
    if (isDeadOrEscaped()) { // these probably shouldn't happen
        std::cerr << bc.seed << " was dead when damaged" << idx << "\n" << bc;
        assert(false);
        return;
    }

    if (damage < 0) {
        damage = 0;
    }

    // Only Nemesis gains monster Intangible; its damage() override caps every
    // positive hit to 1, including thorns, power, relic and potion damage.
    if (hasStatus<MS::INTANGIBLE>()) {
        if (damage > 0) {
            damage = 1;
        }
    }

    const bool hadBlock = block > 0;
    const int tempDamage = damage;
    damage -= block;
    block = std::max(0, block-tempDamage);

    if (hadBlock && block == 0 && bc.player.hasRelic<RelicId::HAND_DRILL>()) {
        bc.addToBot(Actions::DebuffEnemy<MS::VULNERABLE>(idx, 2, false) );
    }

    if (damage > 0) {
        damageUnblockedHelper(bc, damage);
    } else {
        return;
    }
}

void Monster::onHpLost(BattleContext &bc, int amount) {
    const bool atOrBelowHalf = curHp <= maxHp/2;
    switch (id) {
        case MonsterId::ACID_SLIME_L:
            if (atOrBelowHalf && !(moveHistory[0] == MMID::ACID_SLIME_L_SPLIT && slimeSplitRollOrderFix())) {
                cancelPendingMove();
                moveHistory[0] = MMID::ACID_SLIME_L_SPLIT;
                if (slimeSplitRngFix()) moveHistory[1] = MMID::ACID_SLIME_L_SPLIT; // setMove, then the queued SetMoveAction
                search::emitHiddenMonsterIntentMaterialized(
                    idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
            }
            break;

        case MonsterId::SLIME_BOSS:
            if (atOrBelowHalf && !(moveHistory[0] == MMID::SLIME_BOSS_SPLIT && slimeSplitRollOrderFix())) {
                cancelPendingMove();
                moveHistory[0] = MMID::SLIME_BOSS_SPLIT;
                if (slimeSplitRngFix()) moveHistory[1] = MMID::SLIME_BOSS_SPLIT; // setMove, then the queued SetMoveAction
                search::emitHiddenMonsterIntentMaterialized(
                    idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
            }
            break;

        case MonsterId::SPIKE_SLIME_L:
            if (atOrBelowHalf && !(moveHistory[0] == MMID::SPIKE_SLIME_L_SPLIT && slimeSplitRollOrderFix())) {
                cancelPendingMove();
                moveHistory[0] = MMID::SPIKE_SLIME_L_SPLIT;
                if (slimeSplitRngFix()) moveHistory[1] = MMID::SPIKE_SLIME_L_SPLIT; // setMove, then the queued SetMoveAction
                search::emitHiddenMonsterIntentMaterialized(
                    idx, static_cast<std::int16_t>(moveHistory[0]), static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
            }
            break;

        case MonsterId::THE_GUARDIAN:
            if (hasStatus<MS::MODE_SHIFT>()) {
                const int newModeShiftAmount = getStatus<MS::MODE_SHIFT>() - amount;
                if (newModeShiftAmount <= 0) {
                    enterGuardianDefensiveMode();
                    bc.addToBot( Actions::MonsterGainBlock(idx, 20) );
                } else {
                    setStatus<MS::MODE_SHIFT>(newModeShiftAmount);
                }
            }
            break;

        default:
            break;
    }
}

void Monster::removeDebuffs() {
    if (getStatus<MS::STRENGTH>() < 0) {
        setStatus<MS::STRENGTH>(0);
    }

    removeStatus<MS::BLOCK_RETURN>();
    removeStatus<MS::CHOKED>();
    removeStatus<MS::CORPSE_EXPLOSION>();
    removeStatus<MS::LOCK_ON>();
    removeStatus<MS::MARK>();
    removeStatus<MS::POISON>();
    removeStatus<MS::SHACKLED>();
    removeStatus<MS::VULNERABLE>();
    removeStatus<MS::WEAK>();
}

void Monster::resetAllStatusEffects() {
    statusBits = 0;
    setStatus<MS::STRENGTH>(0);
    block = 0;
    // Java Darkling.damage clears its powers when it goes half-dead. Clearing
    // only the bits left the amounts behind, and a later debuff on the revived
    // Darkling added to them (STS_HALF_DEAD_POWER_RESET_FIX=0 restores).
    if (halfDeadPowerResetFix()) {
        artifact = blockReturn = choked = corpseExplosion = lockOn = 0;
        mark = 0;
        metallicize = platedArmor = poison = regen = shackled = 0;
        vulnerable = weak = 0;
        uniquePower0 = 0;
        uniquePower1 = 0;
    }
}

// this is calculated at the player when the damage occurs in game, consider testing whether there are any scenarios when it can't be done before
int Monster::calculateDamageToPlayer(const BattleContext &bc, int baseDamage) const {
    const auto &p = bc.player;
    auto damage = static_cast<float>(baseDamage + getStatus<MS::STRENGTH>());

    if (p.hasStatus<PS::SURROUNDED>()) { // todo this is probably wrong
        const bool facingSelf = p.lastTargetedMonster == idx || bc.monsters.arr[p.lastTargetedMonster].isDeadOrEscaped();
        if (!facingSelf) {
            damage *= 1.5;
        }
    }

    if (hasStatus<MS::WEAK>()) {
        if (p.hasRelic<RelicId::PAPER_KRANE>()) {
            damage *= 0.6f;
        } else {
            damage *= 0.75f;
        }
    }

    if (p.hasStatus<PS::VULNERABLE>()) {
        if (p.hasRelic<RelicId::ODD_MUSHROOM>()) {
            damage *= 1.25f;
        } else {
            damage *= 1.5f;
        }
    }

    if (p.stance == Stance::WRATH) {
        damage *= 2;
    }

    // apply backIdx attack for spire guard elites

    if (p.hasStatus<PS::INTANGIBLE>()) {
        damage = std::min(damage, static_cast<float>(1));
    }

    return std::max(static_cast<int>(std::floor(damage)), 0);
}

void Monster::attackPlayerHelper(BattleContext &bc, int baseDamage, int times) {
    const int damage = calculateDamageToPlayer(bc, baseDamage);

    for (int i = 0; i < times; i++) {
        bc.addToBot(Actions::AttackPlayer(idx, damage));
    }
}

bool Monster::firstTurn() const {
    return moveHistory[0] == MMID::INVALID;
}

bool Monster::lastMove(MMID moveId) const {
    return moveHistory[0] == moveId;
}

bool Monster::lastMoveBefore(MMID moveId) const {
    return moveHistory[1] == moveId;
}

bool Monster::lastTwoMoves(MMID moveId) const {
    return moveHistory[0] == moveId && moveHistory[1] == moveId;
}

bool Monster::eitherLastTwo(MonsterMoveId moveId) const {
    return moveHistory[0] == moveId || moveHistory[1] == moveId;
}

MonsterRollInputs Monster::captureRollInputs(const BattleContext &bc) const {
    MonsterRollInputs inputs;
    inputs.curHp = static_cast<std::int16_t>(curHp);
    inputs.maxHp = static_cast<std::int16_t>(maxHp);
    inputs.miscInfo = latentDamageMask ? 0 : miscInfo;
    const auto &knight = bc.monsters.arr[0];
    inputs.knightCurHp = static_cast<std::int16_t>(knight.curHp);
    inputs.knightMaxHp = static_cast<std::int16_t>(knight.maxHp);
    inputs.knightAlive = knight.isAlive();
    inputs.monsterTurnNumber = static_cast<std::int16_t>(bc.getMonsterTurnNumber());
    inputs.aliveCount = static_cast<std::int8_t>(bc.monsters.getAliveCount());
    inputs.monstersAlive = static_cast<std::int8_t>(bc.monsters.monstersAlive);
    inputs.playerConstricted = bc.player.hasStatus<PS::CONSTRICTED>();
    inputs.asleep = hasStatus<MS::ASLEEP>();
    inputs.halfDead = halfDead;
    return inputs;
}

void Monster::rollMove(BattleContext &bc) {
    // Runic Dome hides the result, not the public state in which the roll is
    // made.  Record the roll-time inputs before the aiRng resolves the move so
    // an observer (or a search under intentsHidden) can represent a pending
    // chance event. The observer is configured from GameContext before
    // BattleContext::init, so this remains correct when Player relic
    // initialization has not yet run. It records neither the rolled move nor
    // an RNG value.
    const MonsterRollInputs inputs = captureRollInputs(bc);
    search::emitHiddenMonsterIntentRollStarted(
        idx, inputs, static_cast<std::int16_t>(moveHistory[0]),
        static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
    if (bc.intentsHidden) {
        // Search under Runic Dome: defer the roll until the move is used or
        // queried (materializePendingMove), so the search cannot see it early.
        if (pendingMoveRolls == 255) throw std::runtime_error("hidden intent roll chain overflow");
        if (pendingMoveRolls != 0) {
            if (pendingRollInputHistory.empty()) {
                pendingRollInputHistory.assign(pendingMoveRolls, pendingRollInputs);
            }
            pendingRollInputHistory.push_back(inputs);
        }
        pendingRollInputs = inputs;
        ++pendingMoveRolls;
        return;
    }
    rollMoveFromInputs(bc, inputs);
}

void Monster::rollMoveFromInputs(BattleContext &bc, const MonsterRollInputs &in) {
    auto miscInfoCopy = latentDamageMask ? miscInfo : in.miscInfo;

#ifdef STS_EXACT_CHANCE
    if (auto *outer = exact::g_chanceScript) {
        // Exact enumeration (research tooling): one choice among the distinct
        // (move, miscInfo) results of the uniform 0..99 roll, with any draws
        // inside getMoveForRoll enumerated exactly. Monsters whose roll reads
        // only its inputs, move history and ascension are cached.
        struct Dist { std::vector<std::pair<MMID, int>> results; std::vector<double> weights; };
        thread_local std::map<std::vector<int>, Dist> cache;
        const bool cacheable = id == MonsterId::CULTIST || id == MonsterId::JAW_WORM || id == MonsterId::RED_LOUSE
            || id == MonsterId::GREEN_LOUSE || id == MonsterId::ACID_SLIME_S || id == MonsterId::ACID_SLIME_M
            || id == MonsterId::SPIKE_SLIME_S || id == MonsterId::SPIKE_SLIME_M;
        const std::vector<int> key = {static_cast<int>(id), static_cast<int>(moveHistory[0]), static_cast<int>(moveHistory[1]),
            miscInfoCopy, bc.ascension, in.curHp, in.maxHp, in.knightCurHp, in.knightMaxHp, in.monsterTurnNumber,
            in.miscInfo, in.aliveCount, in.monstersAlive, in.knightAlive, in.playerConstricted, in.asleep, in.halfDead};
        const Dist *dist = nullptr;
        Dist computed;
        if (auto it = cache.find(key); cacheable && it != cache.end()) {
            dist = &it->second;
        } else {
            exact::ChanceScript inner;
            exact::g_chanceScript = &inner;
            try {
                for (int roll = 0; roll < 100; ++roll) {
                    std::vector<std::vector<int>> stack{{}};
                    while (!stack.empty()) {
                        auto prefix = std::move(stack.back());
                        stack.pop_back();
                        inner.reset(prefix);
                        int misc = miscInfoCopy;
                        const auto move = getMoveForRoll(bc, in, misc, roll);
                        inner.untried(stack);
                        std::size_t r = 0;
                        while (r < computed.results.size()
                               && !(computed.results[r].first == move && computed.results[r].second == misc)) ++r;
                        if (r == computed.results.size()) { computed.results.emplace_back(move, misc); computed.weights.push_back(0); }
                        computed.weights[r] += inner.prob / 100.0;
                    }
                }
            } catch (...) {
                exact::g_chanceScript = outer;
                throw;
            }
            exact::g_chanceScript = outer;
            dist = cacheable ? &cache.emplace(key, std::move(computed)).first->second : &computed;
        }
        ++bc.aiRng.counter;
        const int k = dist->results.size() == 1 ? 0
            : outer->choose(dist->weights.data(), static_cast<int>(dist->weights.size()));
        miscInfo = dist->results[k].second;
        search::CombatKnowledgeMoveRollScope rollScope;
        setMove(dist->results[k].first);
        return;
    }
#endif

    const auto move = getMoveForRoll(bc, in, miscInfoCopy, bc.aiRng.random(99));

    miscInfo = miscInfoCopy;
    // Suppress the generic deterministic setMove publication below: this
    // concrete live result is hidden under Runic Dome and is represented by
    // the preceding deferred-roll observer event instead.
    search::CombatKnowledgeMoveRollScope rollScope;
    setMove(move);
}

bool Monster::observeAttackPredicate(BattleContext &bc) {
    const int step = pendingMoveRolls + (pendingDirectMoveChoice != 0 ? 1 : 0);
    if (!bc.intentsHidden || step == 0) return isAttacking();
    if (!pendingAttackPredicates.empty() && pendingAttackPredicates.back().first == step) {
        return pendingAttackPredicates.back().second;
    }
    // Sample only to obtain the public predicate; restore the information set
    // before returning to a decision node. The isolated search RNG advances.
    const Monster hidden = *this;
    materializePendingMove(bc);
    const bool attacking = isAttacking();
    *this = hidden;
    pendingAttackPredicates.emplace_back(step, attacking);
    return attacking;
}

std::uint16_t Monster::latentDamagePrior(MonsterId id, int ascension) {
    int lo=0,hi=0;
    if(id==MonsterId::RED_LOUSE || id==MonsterId::GREEN_LOUSE) { lo=ascension>=2?6:5; hi=lo+2; }
    else if(id==MonsterId::DARKLING) { lo=ascension>=2?9:7; hi=lo+4; }
    std::uint16_t mask=0; for(int v=lo; lo && v<=hi; ++v) mask|=std::uint16_t(1u<<v);
    return mask;
}
int Monster::publicIncomingDamage(const BattleContext &bc) const {
    if(bc.intentsHidden && latentDamageMask &&
            (moveHistory[0]==MMID::RED_LOUSE_BITE || moveHistory[0]==MMID::GREEN_LOUSE_BITE || moveHistory[0]==MMID::DARKLING_NIP)) {
        int count=0,sum=0;
        for(int v=0;v<16;++v) if(latentDamageMask&(1u<<v)) { ++count; sum+=calculateDamageToPlayer(bc,v); }
        return count?sum/count:0;
    }
    const auto di=getMoveBaseDamage(bc);
    return calculateDamageToPlayer(bc,di.damage)*di.attackCount;
}
void Monster::materializeLatentDamage(BattleContext &bc) {
    if(!latentDamageMask || latentDamageMaterialized) return;
    int count=0; for(int v=0;v<16;++v) count+=(latentDamageMask>>v)&1;
    int pick=bc.monsterHpRng.random(count-1);
    for(int v=0;v<16;++v) if(latentDamageMask&(1u<<v)) {
        if(pick--==0) { miscInfo=v; latentDamageMaterialized=true; return; }
    }
    throw std::runtime_error("empty persistent damage posterior");
}

void Monster::materializePendingMove(BattleContext &bc) {
    materializeLatentDamage(bc);
    const int n = pendingMoveRolls;
    const auto direct = pendingDirectMoveChoice;
    if (n == 0 && direct == 0) return;
    const Monster hidden = *this;
    // Rejection sampling of complete latent chains gives the exact posterior
    // conditioned on every public predicate, including before a reactive
    // reroll. Rejecting never resets the isolated RNG. A pathological or
    // impossible supplied constraint fails closed, never returns a biased move.
    search::CombatKnowledgeMoveRollScope rollScope;
    for (int attempt = 0; attempt < 100000; ++attempt) {
        *this = hidden;
        bool accepted = true;
        auto matches = [&](int step) {
            for (const auto &[at, attack] : pendingAttackPredicates) {
                if (at == step && isAttacking() != attack) return false;
            }
            return true;
        };
        for (int i = 0; i < n; ++i) {
            auto in = pendingRollInputHistory.empty() ? pendingRollInputs : pendingRollInputHistory.at(i);
            in.miscInfo = miscInfo;
            rollMoveFromInputs(bc, in);
            if (!matches(i + 1)) { accepted = false; break; }
        }
        if (!accepted) continue;
        if (direct != 0) {
            setMove(direct == 1
                ? (bc.aiRng.randomBoolean(0.5f) ? MMID::LOOTER_SMOKE_BOMB : MMID::LOOTER_LUNGE)
                : (bc.aiRng.randomBoolean(0.5f) ? MMID::MUGGER_SMOKE_BOMB : MMID::MUGGER_LUNGE));
            if (!matches(n + 1)) continue;
        }
        cancelPendingMove();
        return;
    }
    *this = hidden;
    throw std::runtime_error("hidden intent predicate posterior sampling exhausted");
}

void Monster::cancelPendingMove() {
    // A forced move override (stun, split, mode shift, rebirth, regrow)
    // discards a deferred roll: the overridden roll is unobservable in the
    // real game as well (Silver's analysis).
    pendingMoveRolls = 0;
    pendingRollInputs = MonsterRollInputs{};
    pendingDirectMoveChoice = 0;
    pendingRollInputHistory.clear();
    pendingAttackPredicates.clear();
}

void Monster::setMove(MMID moveId) {
    moveHistory[1] = moveHistory[0];
    moveHistory[0] = moveId;
    // Direct setMove transitions after a monster action are deterministic or
    // otherwise inferable from public state. `rollMove` scopes its own call
    // so random materialized results cannot arrive here as known information.
    search::emitKnownMonsterIntentSet(
        idx, static_cast<std::int16_t>(moveHistory[0]),
        static_cast<std::int16_t>(moveHistory[1]), latentDamageMask ? 0 : miscInfo);
}

namespace sts {

    bool shackledOverflowFix() {
        const char *value = std::getenv("STS_SHACKLED_OVERFLOW_FIX");
        if (!value || !*value || std::string(value) == "1") return true;
        if (std::string(value) == "0") return false;
        throw std::runtime_error("STS_SHACKLED_OVERFLOW_FIX must be 0 or 1");
    }

    std::int16_t shackledAmount(int amount) {
        // GainStrengthPower's constructor and stackPower clamp to [-999, 999].
        if (shackledOverflowFix()) return static_cast<std::int16_t>(std::clamp(amount, -999, 999));
        return static_cast<std::int8_t>(amount);
    }

    std::ostream& printIfHaveStatus(std::ostream &os, const Monster &m, MonsterStatus s, bool &havePrint) {
        if (!m.getStatusInternal(s)) {
            return os;
        }

        if (havePrint) {
            os << ", ";
        }
        havePrint = true;

        os << '(' << enemyStatusStrings[(int)s];
        if (!isBooleanPower(s)) {
            os << "," << m.getStatusInternal(s);
        }
        os << ")";
        return os;
    }



    std::ostream &operator<<(std::ostream &os, const Monster &m) {
        os << "{";
        os << m.idx << " " << sts::monsterIdStrings[(int) m.id]
           << " hp:(" << m.curHp << "/" << m.maxHp << ")"
           << " block:(" << m.block << ") statusEffects:{";

        bool havePrint = false;
        printIfHaveStatus(os, m, MS::STRENGTH, havePrint);
        for (int i = static_cast<int>(MS::ARTIFACT); i <= static_cast<int>(MS::STASIS); ++i) {
            auto s = static_cast<MS>(i);
            if (s != MonsterStatus::STRENGTH) {
                printIfHaveStatus(os, m, s, havePrint);
            }
        }
        os << "}";

        os << " halfDead: " << m.halfDead
           << ", moveHistory: { " << monsterMoveStrings[(int) m.moveHistory[0]] << ", " << monsterMoveStrings[(int) m.moveHistory[1]] << "}"
           << " nextActionDamage: " << " miscInfo: " << m.miscInfo << " uniquePower0: " << m.uniquePower0 << " uniquePower1: " << m.uniquePower1
            << "}";
        return os;
    }

}
