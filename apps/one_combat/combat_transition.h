#ifndef STS_ONE_COMBAT_COMBAT_TRANSITION_H
#define STS_ONE_COMBAT_COMBAT_TRANSITION_H

#include <array>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "combat_predictor_input.h"
#include "game/GameContext.h"

namespace one_combat {

struct CombatTransitionRandomState {
    std::int32_t counter = 0;
    std::uint64_t seed0 = 0;
    std::uint64_t seed1 = 0;
};

struct CombatTransitionCardState {
    int id = 0;
    std::int16_t misc = 0;
    bool upgraded = false;
};

struct CombatTransitionRelicState {
    int id = 0;
    int data = 0;
};

// State at the boundary owned by BattleContext::exitBattle.  Fields that are
// copied through but not written by combat are intentionally outside this
// structure; the native continuation retains them from the pre-combat copy.
struct CombatTransitionPersistentState {
    int curHp = 0;
    int maxHp = 0;
    int gold = 0;
    int potionCount = 0;
    int potionCapacity = 0;
    std::array<int, 5> potions{};
    bool smokeBombUsed = false;
    int stolenGold = 0;

    std::vector<CombatTransitionRelicState> relics;
    std::array<std::uint64_t, 3> relicBits{};
    std::vector<CombatTransitionCardState> deck;
    std::array<int, 4> cardTypeCounts{};
    std::array<int, 3> bottleIdxs{};
    int upgradeableCount = 0;
    int transformableCount = 0;

    // These are exactly the streams synchronized by exitBattle.  The other
    // GameContext streams are copy-through state and remain in the detached
    // pre-combat continuation.
    std::array<CombatTransitionRandomState, 6> combatRng{};
};

struct CombatTransitionRecord {
    static constexpr const char *SCHEMA = "combat_transition_v1";

    sts::Outcome combatOutcome = sts::Outcome::UNDECIDED;
    sts::GameOutcome rawGameOutcome = sts::GameOutcome::UNDECIDED;
    CombatTransitionPersistentState pre;
    CombatTransitionPersistentState post;
};

static constexpr const char *COMBAT_TRANSITION_ROW_SCHEMA =
    "combat_transition_row_v2";

CombatTransitionPersistentState captureCombatTransitionState(const sts::GameContext &gc);
void applyCombatTransitionState(sts::GameContext &gc,
                                 const CombatTransitionPersistentState &state);
nlohmann::json combatTransitionStateJson(const CombatTransitionPersistentState &state);
CombatTransitionPersistentState combatTransitionStateFromJson(const nlohmann::json &value);
CombatTransitionRecord captureCombatTransition(const sts::GameContext &pre,
                                               const sts::BattleContext &bc,
                                               const sts::GameContext &rawPost);
nlohmann::json combatTransitionRecordJson(const CombatTransitionRecord &record);
std::string combatTransitionFingerprint(const sts::GameContext &gc);

// Composes with an existing raw observer and restores it even if combat or a
// test throws.  The first callback invocation is the only one meaningful for
// a normal exitBattle call, but the scope deliberately does not hide repeats.
class CombatTransitionRawObserverScope {
public:
    explicit CombatTransitionRawObserverScope(
        const std::function<void(const sts::BattleContext &, sts::GameContext &)> &observer);
    ~CombatTransitionRawObserverScope();
    CombatTransitionRawObserverScope(const CombatTransitionRawObserverScope &) = delete;
    CombatTransitionRawObserverScope &operator=(const CombatTransitionRawObserverScope &) = delete;

private:
    std::function<void(const sts::BattleContext &, sts::GameContext &)> previous_;
};

} // namespace one_combat

#endif
