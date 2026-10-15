# Issue 75: `STS_WIN_NET` load failure silent

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `apps/one_combat.cpp:9979`

## Symptom

`STS_WIN_NET`: `g_winNet.load(path, ...)` return value ignored. A bad path
silently falls back to `build/v_win_trees.txt` in the native-OOC block.

## Evidence

- `one_combat.cpp:9979`: return value not checked.

## Candidate fix directions

Log an error when `load` returns false.

## Relevant code

- `apps/one_combat.cpp:9979`
