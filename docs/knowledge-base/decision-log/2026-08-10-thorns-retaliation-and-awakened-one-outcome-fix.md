# 2026-08-10 — Combat outcome first-write-wins: Thorns retaliation + Awakened One stage 2 (issues #50/#51)

Date: 2026-08-10
Session/task: Fix issues #50 (Thorns retaliation flips win to loss) and #51
(Awakened One premature victory) from `docs/knowledge-base/issues/`.

## Decision

Combat outcome is now first-write-wins and fights end the moment an outcome is
decided:

1. Every combat-resolution outcome setter is guarded with
   `if (outcome == Outcome::UNDECIDED)`:
   - `Monster::die` (`src/combat/Monster.cpp`)
   - `Monster::suicideAction` (`src/combat/Monster.cpp`)
   - `Player::wouldDie` (`src/combat/Player.cpp`)
   - LOOTER_ESCAPE / MUGGER_ESCAPE victory (`src/combat/MonsterSpecific.cpp`)
2. `BattleContext::executeActions` now breaks immediately on any decided
   outcome (`outcome != Outcome::UNDECIDED`) instead of only on PLAYER_LOSS,
   so queued retaliation actions (Thorns `DamagePlayer` is pushed to the queue
   top before `die()` sets VICTORY) never execute after the killing blow.
3. Victory is only granted when `monstersAlive == 0` AND no monster is a
   half-dead Awakened One stage 1 awaiting its mandatory rebirth (new
   `MonsterGroup::anyHalfDead()` helper): the half-dead Awakened One defers
   victory until its rebirth turn runs, keeping Act 3 boss stage 2 playable.
   Darklings are intentionally excluded from the deferral: their regrow is
   pre-empted by victory at `monstersAlive == 0` (the last Darkling to die
   stays dead, matching the real game's max-two-revives rule). A blanket
   "no monster half-dead" predicate (the plan's literal wording) made the
   THREE_DARKLINGS fight non-terminating — every darkling death leaves the
   others mid-regrow, so victory would never fire and the regrow cycle loops
   forever (reproduced as a battle-stall at `bestbench 200 8 0` encounter 40,
   now fixed).

## Rationale

- Last-write-wins `outcome` with unconditional setters let a lethal Thorns
  retaliation overwrite a just-earned PLAYER_VICTORY. Real StS ends the fight
  immediately on last-enemy death (community-verified, cited in issue #50), so
  the drain-the-queue VICTORY path was wrong.
- `monstersAlive == 0` is not a valid victory predicate while the Awakened
  One stage 1 is half-dead: its rebirth must still run, so victory is deferred
  until stage 2 is killed. The codebase already models half-death
  (`Monster::isHalfDead`, `Actions.cpp:1080,1113`); the deferral is scoped to
  the Awakened One because Darkling regrow is pre-empted by victory (see
  Decision 3).

## Alternatives considered

- Leaving the VICTORY-drains-queue behavior and only guarding setters —
  rejected: queued retaliation would still mutate post-victory state and the
  plan calls for aligning queue semantics with real StS.
- Reusing `areMonstersBasicallyDead()` — rejected: it only checks
  `monstersAlive <= 0` and misses half-dead monsters.
- Blanket "no monster half-dead" victory predicate (plan's literal wording) —
  rejected after repository evidence: Darklings always regrow in the model, so
  the last death would never grant victory and THREE_DARKLINGS loops forever.
  The deferral is scoped to the Awakened One stage 1, the only monster whose
  revival is mandatory in this codebase.

## Evidence

- Regression tests added to `apps/test.cpp` (dispatched as
  `./build/test thorns_retaliation`, `./build/test awakened_one_stage2`,
  `./build/test darkling_victory`, registered in `CMakeLists.txt` as ctest
  `thorns_retaliation` / `awakened_one_stage2` / `darkling_victory`). All
  pass; full ctest suite passes.
- `./build/one_combat bestbench 10 4 0` smoke test completes; 8-seed/200-sim
  sanity run shows normal win/floor behavior (win%=25.0, avg_floor=43.5)
  with no Darkling stalls after the scoped deferral.
- Pre-fix: `thorns_retaliation` reproduced the flip (VICTORY → LOSS) and
  `awakened_one_stage2` reproduced premature VICTORY; both fail before the
  change and pass after. With the blanket half-dead predicate, `bestbench
  200 8 0` stalled on encounter 40 (THREE_DARKLINGS); after scoping the
  deferral to the Awakened One the stall is gone (`darkling_victory` guards
  the regression).

## Status and follow-up

- Implemented. Issues #50/#51 marked closed in
  `docs/knowledge-base/issues/`; index rows added with fix note.
- `docs/knowledge-base/behavior/invariants.md` updated with the
  first-write-wins and no-half-dead-victory invariants.
- Out of scope, noted for follow-up: other outcome setters in
  `src/sim/search/ScumSearchAgent2.cpp` are battle-stall guards (immediately
  followed by `break`) and were intentionally left unconditional; stale-object
  risk from concurrent agents rebuilding the same files was resolved by a full
  rebuild after touch.
