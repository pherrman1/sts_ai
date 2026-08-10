# Issue 81: v_server `WIN_BOOSTER.predict` unlocked

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `v_server.py:decide_nn`

## Symptom

`decide_nn` calls `WIN_BOOSTER.predict` outside the global `LOCK` — the only
unlocked model call in v_server.py. Correctness depends on installed xgboost's
predict thread-safety.

## Evidence

- `v_server.py:decide_nn`: `WIN_BOOSTER.predict` outside `LOCK`.

## Candidate fix directions

Move the predict call inside the `LOCK` block.

## Relevant code

- `v_server.py:decide_nn` (~line 370)
