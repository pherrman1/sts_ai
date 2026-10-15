# Issue 63: TOKE (Peace Pipe) is a no-op

- **Status:** closed (2026-08-10, fixed in `src/game/GameContext.cpp`)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/game/GameContext.cpp:3736-3739`

## Symptom

`chooseCampfireOption` TOKE (case 4) calls `openCardSelectScreen(REMOVE, 1)`
then immediately `regainControl()` (the REST-room action sets `MAP_SCREEN`).
The removal screen is opened but immediately closed before any pick can be made.
Peace Pipe does nothing.

Inherited from upstream (gamerpuppy/sts_lightspeed).

## Evidence

- `GameContext.cpp:3736-3739`: open then immediate regainControl.
- `GameContext.cpp:765`: REST-room action sets MAP_SCREEN.
- SMITH case (1) correctly omits the `regainControl`.

## Why it matters

Peace Pipe is a common boss relic swap / shop purchase. It currently does
nothing, silently making it a dead relic.

## Candidate fix directions

Remove the `regainControl()` call from the TOKE case, matching the SMITH
pattern.

## Resolution (2026-08-10)

Removed the eager `regainControl()` from `GameContext::chooseCampfireOption`
case 4 (TOKE). The pick path `GameContext::chooseSelectCardScreenOption`
(REMOVE) already calls `regainControl()` once the card is chosen, exactly like
SMITH/UPGRADE. Regression test added to `apps/test.cpp` `testIssueFixes()`;
`./build/test issue_fixes` PASS.

## Relevant code

- `src/game/GameContext.cpp:3736-3739`
