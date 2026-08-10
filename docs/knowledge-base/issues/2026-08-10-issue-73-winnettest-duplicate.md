# Issue 73: Duplicate `winnettest` branch — second is unreachable

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `apps/one_combat.cpp:10828, 11463`

## Symptom

`mode == "winnettest"` matches first at ~10828 (CSV-based validation). The
second branch at ~11463 (live full-run native-vs-server parity check) can never
run — dead code with functional content.

## Evidence

- `one_combat.cpp`: first `winnettest` branch at mode dispatch.
- `one_combat.cpp`: unreachable second branch later in the else-if chain.

## Candidate fix directions

Either remove the dead second branch or rename it to a distinct mode name.

## Relevant code

- `apps/one_combat.cpp`: duplicate `winnettest` branches
