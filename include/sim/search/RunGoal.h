#ifndef STS_RUN_GOAL_H
#define STS_RUN_GOAL_H

#include "game/GameContext.h"
#include "sim/search/GameAction.h"
#include <optional>

namespace sts::search {
// Act-3 victory without keys is a simulator victory, but not a Heart kill.
// An explicit benchmark horizon retains its historical terminal semantics.
inline bool runGoalVictory(const GameContext &gc, bool collectKeys, int stopAfterAct = 0) {
    return gc.outcome == GameOutcome::PLAYER_VICTORY
        && (!collectKeys || gc.act >= 4 || (stopAfterAct > 0 && gc.act >= stopAfterAct));
}

// Key-rule variants. A value-initialized HeartKeyRules holds the ADR-0041 rules; heartKeyRules() reads
// STS_KEY_SAPPHIRE (first|act3|policy), STS_KEY_RUBY (first|hp|policy), STS_KEY_RUBY_MIN_HP (fraction,
// default 0.6) and STS_KEY_EMERALD (first|mask|policy) once, and unset means policy/policy/mask (ADR-0063,
// §691); first restores the ADR-0041 rule for that key.
struct HeartKeyRules {
    enum class Sapphire { FIRST, ACT3, POLICY } sapphire = Sapphire::FIRST;
    enum class Ruby { FIRST, HP, POLICY } ruby = Ruby::FIRST;
    double rubyMinHp = 0.6;
    enum class Emerald { FIRST, MASK } emerald = Emerald::FIRST;
    bool isAdr0041() const {
        return sapphire == Sapphire::FIRST && ruby == Ruby::FIRST && emerald == Emerald::FIRST;
    }
};
HeartKeyRules &heartKeyRules();

// Mandatory key choices. ADR-0041 (first): Sapphire at the first chest, Recall
// at the first Act-3 campfire, and on Act 3 the first legal route that still
// reaches the visible burning elite; earlier acts retain ordinary pathing.
// Variants: act3 takes Sapphire at the first Act-3 chest; policy leaves it to
// the policy until the Act-3 treasure row. hp Recalls at the first Act-3
// campfire at or above the HP fraction, else at the pre-boss row; policy
// forces only the pre-boss row. mask forces an Act-3 edge only when a single
// edge still reaches the burning elite. Acts 1-2 are always the policy's
// choice; Emerald policy is an alias of mask (the Act-3 backstop stays).
std::optional<GameAction> heartKeyAction(const GameContext &gc, bool collectKeys);
// Fallback-chain Recall condition: the historical "Act 3+ without Ruby" rule,
// narrowed to heartKeyAction's choice under a non-first Ruby variant.
bool heartRecallRequired(const GameContext &gc, bool collectKeys);
// False only for an action a variant forbids: Sapphire before Act 3
// (act3), or an Act-3 edge that no longer reaches the burning elite (mask).
bool heartKeyActionAllowed(const GameContext &gc, bool collectKeys, const GameAction &action);
}
#endif
