// Moved unchanged from apps/one_combat/ooc_mcts_adapter.cpp (2026-11-17); see sim/search/OocHiddenFuture.h.
#include "sim/search/OocHiddenFuture.h"

#include <algorithm>
#include <memory>

#include "constants/MonsterEncounters.h"
#include "constants/Misc.h"
#include "game/Map.h"
#include "sim/search/OocMctsPlanner.h"

namespace sts::search {

GameContext detachedGameCopy(const GameContext &parent) {
    GameContext child = parent;
    if (parent.map) child.map = std::make_shared<sts::Map>(*parent.map);
    return child;
}
// Re-determinize only a detached hypothetical state. Published offers, the
// current map/boss, selected cards, and observed encounter history stay fixed.
// A fresh seed also covers native per-floor RNG resets and next-act map setup.
void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng) {
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
            &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
            &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
            &gc.shuffleRng, &gc.treasureRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter; // native thresholds depend on past draw counts
    }
    const auto shuffleUnknown = [&](auto &pool) {
        // Canonicalize first so the actual hidden ordering cannot affect samples.
        std::sort(pool.begin(), pool.end());
        std::shuffle(pool.begin(), pool.end(), rng);
    };
    for (auto pool : {&gc.commonRelicPool, &gc.uncommonRelicPool, &gc.rareRelicPool,
                     &gc.shopRelicPool, &gc.bossRelicPool}) shuffleUnknown(*pool);
    shuffleUnknown(gc.colorlessCardPool);
    // Event pools are eligible sets, not queues. Canonical order removes any
    // dependence on an unobserved representation without changing membership.
    std::sort(gc.eventList.begin(), gc.eventList.end());
    std::sort(gc.shrineList.begin(), gc.shrineList.end());
    std::sort(gc.specialOneTimeEventList.begin(), gc.specialOneTimeEventList.end());
    if (gc.act >= 1 && gc.act <= 3) {
        const int count = gc.monsterList.size();
        if (gc.monsterListOffset < 0 || gc.monsterListOffset > count
            || gc.eliteMonsterListOffset < 0 || gc.eliteMonsterListOffset > gc.eliteMonsterList.size())
            throw OocSearchUnsupported("invalid_hidden_encounter_history");
        const int weakCount = gc.act == 1 ? 3 : 2;
        gc.monsterList.resize(gc.monsterListOffset);
        for (int i = gc.monsterListOffset; i < count; ++i) {
            const int act = gc.act - 1;
            if (i < weakCount)
                gc.populateMonsterList(sts::MonsterEncounterPool::weakEnemies[act],
                    sts::MonsterEncounterPool::weakWeights[act], sts::MonsterEncounterPool::weakCount[act], 1);
            else if (i == weakCount)
                gc.populateFirstStrongEnemy(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act]);
            else
                gc.populateMonsterList(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act], 1);
        }
        for (int i = gc.eliteMonsterListOffset; i < gc.eliteMonsterList.size(); ++i) {
            sts::MonsterEncounter draw;
            do { draw = sts::MonsterEncounterPool::elites[gc.act-1][gc.monsterRng.random(2)]; }
            while (i > 0 && draw == gc.eliteMonsterList[i-1]);
            gc.eliteMonsterList[i] = draw;
        }
        // The second A20 boss is hidden until the first boss falls; once its
        // fight has started (a BATTLE leaf after a sampled first-boss win) it is
        // revealed, and Silver reads gc.secondBoss to recognise the final fight.
        const bool secondBossRevealed = gc.screenState == sts::ScreenState::BATTLE
            && gc.info.encounter == gc.secondBoss;
        if (gc.act == 3 && gc.ascension >= 20 && !secondBossRevealed) {
            const sts::MonsterEncounter bosses[] = {sts::MonsterEncounter::AWAKENED_ONE,
                sts::MonsterEncounter::TIME_EATER, sts::MonsterEncounter::DONU_AND_DECA};
            do { gc.secondBoss = bosses[gc.monsterRng.random(2)]; } while (gc.secondBoss == gc.boss);
        }
    }
    if (gc.screenState == sts::ScreenState::TREASURE_ROOM) {
        // Chest size is visible; contents are not. Keep native gold/tier
        // correlation from the single roll used by setupTreasureRoom().
        const int size = int(gc.info.chestSize);
        if (size < 0 || size >= 3) throw OocSearchUnsupported("invalid_hidden_chest");
        const int roll = gc.treasureRng.random(99);
        gc.info.haveGold = roll < sts::chestGoldChances[size];
        const auto chances = sts::chestRelicTierChances[size];
        gc.info.tier = roll < chances[0] ? sts::RelicTier::COMMON
            : roll < chances[0] + chances[1] ? sts::RelicTier::UNCOMMON : sts::RelicTier::RARE;
    }
    if (gc.screenState == sts::ScreenState::EVENT_SCREEN && gc.curEvent == sts::Event::DEAD_ADVENTURER) {
        // The description reveals the encounter, but unsearched rewards remain hidden.
        if (gc.info.phase < 0 || gc.info.phase > int(gc.info.rewards.size()))
            throw OocSearchUnsupported("invalid_hidden_event_history");
        auto first = gc.info.rewards.begin() + gc.info.phase;
        std::sort(first, gc.info.rewards.end());
        std::shuffle(first, gc.info.rewards.end(), rng);
    }
}

}
