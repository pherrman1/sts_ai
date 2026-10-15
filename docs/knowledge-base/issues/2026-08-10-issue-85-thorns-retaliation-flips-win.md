# Issue 85: Lethal Thorns retaliation flips win to loss

> Provenance: originally recorded under duplicate legacy ID #50; renumbered to
> canonical #85 during documentation cleanup (2026-08-11). Substantive issue
> evidence is unchanged.

- **Status:** closed (2026-08-10)
- **Fix:** outcome setters guarded with `UNDECIDED` check (`Monster::die`,
  `Monster::suicideAction`, `Player::wouldDie`, LOOTER/MUGGER escape) and
  `executeActions()` now breaks immediately on any decided outcome, so the
  queued Thorns `DamagePlayer` retaliation never runs after the killing blow.
  Regression test: `./build/test thorns_retaliation` (ctest `thorns_retaliation`).
- **Tier:** High
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/BattleContext.cpp`, `src/combat/Monster.cpp`, `src/combat/Player.cpp`

## Symptom

When the player kills the last enemy with an attack and the enemy's Thorns
damage is lethal, the win is flipped to a loss. Root cause: last-write-wins
`outcome` with no `UNDECIDED` guard on setters, combined with the
VICTORY-drains-queue / LOSS-breaks-immediately asymmetry, and
`clearOnCombatVictory=false` on player-damage actions.

## Evidence

- `BattleContext.cpp:776-787`: PLAYER_LOSS breaks immediately; VICTORY drains
  the queue first, then breaks.
- `Monster.cpp:372-377`: Thorns queues `DamagePlayer` to queue top before
  `die()` sets VICTORY at 293-296.
- `Actions.cpp:78-94`: `DamagePlayer`/`AttackPlayer`/`PlayerLoseHp` have
  `clearOnCombatVictory=false`.
- `Player.cpp:346`: `wouldDie` sets `outcome = PLAYER_LOSS` unconditionally.
- Real StS behavior (community-verified): combat ends immediately on last-enemy
  death; Thorns/Spikes/Explosion do not trigger on the killing blow.

## Why it matters

Any fight against a Thorns enemy (Spiker, Guardian defensive mode) where the
player is at low HP can produce a false loss. This silently inflates loss rates
in benchmarks and datagen.

## Candidate fix directions

1. Guard all outcome setters with `if (outcome == Outcome::UNDECIDED)`.
2. Make `checkCombat`/queue-drain victory semantics drop retaliation actions
   (align with real game).

## Relevant code

- `src/combat/BattleContext.cpp:776-787`, `690-726`
- `src/combat/Monster.cpp:280-296`, `372-377`
- `src/combat/Actions.cpp:78-94`
- `src/combat/Player.cpp:346`
