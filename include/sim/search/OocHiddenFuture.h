// Hidden-information resampling for out-of-combat search copies of a GameContext. Moved here unchanged from
// apps/one_combat/ooc_mcts_adapter.cpp (2026-11-17) so the stage 1 self-play driver (apps/az_bench) shares it.
#ifndef STS_OOC_HIDDEN_FUTURE_H
#define STS_OOC_HIDDEN_FUTURE_H

#include <array>
#include <random>

#include "game/GameContext.h"

namespace sts::search {

    // A copy that owns its map (GameContext::map is a shared_ptr; a plain copy would share it).
    GameContext detachedGameCopy(const GameContext &parent);

    // Re-determinize only a detached hypothetical state. Published offers, the current map/boss, selected cards, and
    // observed encounter history stay fixed. A fresh seed also covers native per-floor RNG resets and next-act map
    // setup. Throws OocSearchUnsupported (sim/search/OocMctsPlanner.h) on an inconsistent hidden history.
    void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng);

    // Amber Eye's chance rule out of combat (stage 1 self-play, 2026-11-17): "When stepping the simulator, it flags if
    // any hidden information was revealed by this step, which can be done by checking if any of the RNGs were used.
    // Some hidden information [...] is randomized at an earlier step [...], so these cases are also detected and
    // resampled." A snapshot of everything sampleNoncombatFuture treats as hidden: the 14 RNG streams, the pre-shuffled
    // relic and colorless pools, the encounter queues past their offsets, the second A20 boss and the act (a new act's
    // map comes from the hidden seed).
    struct OocHiddenSnapshot {
        std::array<Random, 14> streams;
        std::array<int, 5> relicPoolSizes{};
        std::array<CardId, 35> colorless{};
        int monsterListSize = 0, monsterListOffset = 0, eliteListSize = 0, eliteListOffset = 0;
        MonsterEncounter secondBoss = MonsterEncounter::INVALID;
        int act = 0;
    };
    OocHiddenSnapshot captureOocHidden(const GameContext &gc);

    // True if stepping from the state of `before` to `after` used hidden information: an RNG stream drew (a stream
    // reseeded to Random(seed + floorNum) at a new floor without drawing is no use), a pre-shuffled pool or an
    // encounter queue was read, the second boss changed, the act changed, or a fight started (BattleContext::init
    // draws the shuffle and the monsters' rolls from the run's streams).
    bool oocStepRevealsHidden(const OocHiddenSnapshot &before, const GameContext &after);

}

#endif
