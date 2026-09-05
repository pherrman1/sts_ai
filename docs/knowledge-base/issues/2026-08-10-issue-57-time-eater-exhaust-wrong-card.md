# Issue 57: Time Eater exhaust flag applied to wrong card

- **Status:** fixed (2026-08-10)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/combat/Actions.cpp:890-906`

## Symptom

`TimeEaterPlayCardQueueItem` does `item.exhaustOnUse |= bc.curCardQueueItem.card.doesExhaust()`,
OR-ing the *triggering* card's exhaust property onto the *replayed* item instead
of `item.card.doesExhaust()`. A queued Fiend Fire replayed after a non-exhaust
trigger card wrongly avoids exhausting.

## Evidence

- `Actions.cpp:890-906`: `item.exhaustOnUse |= bc.curCardQueueItem.card.doesExhaust()`
  should be `item.card.doesExhaust()`.
- Reachable: Time Eater + autoplay queue (Havoc/Mayhem).

## Why it matters

Card fidelity bug against the Act 3 boss. Fiend Fire exhaust behavior is
critical to its power level.

## Candidate fix directions

Change `bc.curCardQueueItem.card.doesExhaust()` to `item.card.doesExhaust()`.

## Relevant code

- `src/combat/Actions.cpp:890-906`

## Resolution

`TimeEaterPlayCardQueueItem` now ORs the *replayed* card's own exhaust
property: `item.exhaustOnUse |= item.card.doesExhaust();` instead of
`bc.curCardQueueItem.card.doesExhaust()`. Regression test: `time_eater_exhaust`
(see `apps/test.cpp`, CTest entry in `CMakeLists.txt`). See
