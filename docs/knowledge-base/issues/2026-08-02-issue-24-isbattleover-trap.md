# Issue 24: `isBattleOver` is never set true

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`behavior/invariants.md`](../behavior/invariants.md), "Simulator and action invariants"

## Symptom

Combat control loops must continue while `BattleContext::outcome ==
Outcome::UNDECIDED`; current code resets and reads `isBattleOver` but never
assigns it true. Any code that uses `isBattleOver` as the terminal flag will
loop incorrectly.

## Evidence

- `src/combat/BattleContext.cpp::init`, `afterMonsterTurns`: `isBattleOver`
  read/reset only.
- `AGENTS.md` "Critical safety and correctness traps" and
  `behavior/invariants.md`.

## Why it matters

This is the documented terminal-flag trap. It is already in the invariant list
as a review point; the issue here is that nothing prevents a future writer from
using `isBattleOver` again.

## Candidate fix direction

Either assign `isBattleOver` from `outcome` at every terminal transition (making
it a derived convenience) or remove it; add a unit test that no loop uses it.

## Relevant code

- `include/combat/BattleContext.h::BattleContext`
- `src/combat/BattleContext.cpp::init`, `afterMonsterTurns`

## Resolution (2026-08-02)

Fixed: `isBattleOver` is now a derived method `outcome != UNDECIDED` (`include/combat/BattleContext.h`); all reads updated. Test `./build/small-test isbattleover` PASS.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
