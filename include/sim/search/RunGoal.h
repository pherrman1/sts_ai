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

// Opt-in key-rule variants; the defaults are the ADR-0041 rules. Read once from
// STS_KEY_SAPPHIRE (first|act3|policy), STS_KEY_RUBY (first|hp|policy),
// STS_KEY_RUBY_MIN_HP (fraction, default 0.6) and STS_KEY_EMERALD (first|mask|policy).
struct HeartKeyRules {
    enum class Sapphire { FIRST, ACT3, POLICY } sapphire = Sapphire::FIRST;
    enum class Ruby { FIRST, HP, POLICY } ruby = Ruby::FIRST;
    double rubyMinHp = 0.6;
    enum class Emerald { FIRST, MASK } emerald = Emerald::FIRST;
    bool isDefault() const {
        return sapphire == Sapphire::FIRST && ruby == Ruby::FIRST && emerald == Emerald::FIRST;
    }
};
HeartKeyRules &heartKeyRules();

// Mandatory key choices. On Act 3, use the first legal route that still
// reaches the visible burning elite; earlier acts retain ordinary pathing.
// Variants: act3 takes Sapphire at the first Act-3 chest; policy leaves it to
// the policy until the Act-3 treasure row. hp Recalls at the first Act-3
// campfire at or above the HP fraction, else at the pre-boss row; policy
// forces only the pre-boss row. mask forces an Act-3 edge only when a single
// edge still reaches the burning elite. Acts 1-2 are always the policy's
// choice; Emerald policy is an alias of mask (the Act-3 backstop stays).
std::optional<GameAction> heartKeyAction(const GameContext &gc, bool collectKeys);
// Fallback-chain Recall condition: the historical "Act 3+ without Ruby" rule,
// narrowed to heartKeyAction's choice under an opt-in Ruby variant.
bool heartRecallRequired(const GameContext &gc, bool collectKeys);
// False only for an action an opt-in variant forbids: Sapphire before Act 3
// (act3), or an Act-3 edge that no longer reaches the burning elite (mask).
bool heartKeyActionAllowed(const GameContext &gc, bool collectKeys, const GameAction &action);
}
#endif
