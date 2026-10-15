# Issue 68: Stale multi-select validation in fair mode

- **Status:** closed (2026-08-10)
- **Fix:** `isValidMultiCardSelectAction` now requires
  `bc.inputState == InputState::CARD_SELECT` before validating
  EXHAUST_MANY/GAMBLE masks, matching `isValidSingleCardSelectAction`'s guard.
  Stale `cardSelectInfo.cardSelectTask` values can no longer re-validate
  MULTI_CARD_SELECT actions once the state has left CARD_SELECT (fair-mode edge
  re-check in `BattleScumSearcher2.cpp`).
  Regression test: `./build/test issue_fixes` (ctest `issue_fixes`).
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `src/sim/search/Action.cpp:200-228`, `src/sim/search/BattleScumSearcher2.cpp:431-440`

## Symptom

`isValidMultiCardSelectAction` lacks the `inputState == CARD_SELECT` gate that
`isValidSingleCardSelectAction` has. Since the `cardSelectInfo.cardSelectTask`
field is stale after a select, EXHAUST_MANY/GAMBLE masks can validate while
`inputState == PLAYER_NORMAL`.

Reachable via fair-mode edge re-validation (`BattleScumSearcher2.cpp:431-440`),
which re-checks stored edges against a possibly different world state.

## Evidence

- `Action.cpp:131`: single-select has `inputState == CARD_SELECT` guard.
- `Action.cpp:200-228`: multi-select lacks this guard.
- `BattleScumSearcher2.cpp:431-440`: fair-mode edge re-validation.

## Candidate fix directions

Add `bc.inputState == InputState::CARD_SELECT` guard to
`isValidMultiCardSelectAction`.

## Relevant code

- `src/sim/search/Action.cpp:200-228`
