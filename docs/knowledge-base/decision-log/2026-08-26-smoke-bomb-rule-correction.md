# 2026-08-26 — correct Smoke Bomb combat semantics

## Decision

The 2026-08-10 conclusion that the real game forbids Smoke Bomb in combat was
incorrect and is superseded. The maintained contract is: eligible non-boss,
non-`SURROUNDED` combat may be escaped; escape grants no combat rewards;
bosses and `SURROUNDED` block use; discard remains independent.

Historical decision entries remain unchanged. Current behavior and Issue 69
now point to the corrected contract implemented by `e53f994` and merged via
PR #58.

## Rationale

The rule was verified against the pinned Silver reference and exercised at the
live simulator/run boundary. Treating Smoke Bomb as universally forbidden made
all combat backends share the same wrong semantics and later invalidated the
first Silver gameplay smoke when the reference boundary was encountered.

## Evidence

- `BattleContext::smokeBombEscapeBlocked`, `drinkPotion`, and `exitBattle`
- `GameContext::afterBattle`
- `Action::isValidPotionAction` and Searcher2/Searcher3/SimpleAgent enumeration
- `apps/test.cpp::testIssueFixes` (CTest `issue_fixes`)

## Status and follow-up

Implemented and merged. No gameplay/search tuning decision is implied.
