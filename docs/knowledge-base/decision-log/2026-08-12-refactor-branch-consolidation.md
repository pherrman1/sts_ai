# 2026-08-12 — Refactor branch consolidation

Date: 2026-08-12
Session/task: Consolidate the completed Phase 6 Batch 1 refactor onto the main branch.

## Decision

Fast-forward `main` to the existing Batch 1 refactor commit and remove the two
redundant local `phase6-batch1-*` branch names. Publish the resulting `main`
history with a plain `git push`.

## Rationale

The branch graph was linear: `phase6-batch1-current` was one commit ahead of
`origin/main`, while `main` and `phase6-batch1-oldbase` both pointed exactly at
`origin/main`. A fast-forward preserves the existing reviewed commit without a
synthetic merge commit or history rewrite.

## Alternatives considered

- Create a merge commit — rejected because the histories had not diverged.
- Squash or amend the refactor commit — rejected because no history rewrite was
  needed and the existing commit was already focused.
- Keep the temporary branch names — rejected because they no longer identify
  distinct work after consolidation.

## Evidence

- `apps/one_combat.cpp::main` and the removed benchmark helpers — Batch 1
  implementation in commit `7107846`.
- `tools/seed_guard.sh::ONE_COMBAT_SEED_INDEX` — removed modes no longer appear
  in the automated seed-argument map.
- `docs/knowledge-base/investigations/2026-08-11-stale-implementation-audit.md`
  — Batch 1 scope and status.
- `cmake --build build -j --target one_combat` — passed in WSL; existing
  narrowing-conversion warnings remain.
- `ctest --test-dir build --output-on-failure` — 23/26 passed; failures were
  WSL CRLF parsing of `selfplay/loop.sh`, missing WSL NumPy, and the Release
  `cardqueue_overflow` assertion expectation.
- `tools/seed_guard.sh env STS_FAIR=1 ./build/one_combat bestbench 1000 8 0` —
  did not finish within a six-minute local timeout; the exact remaining child
  process was terminated.

## Status and follow-up

- Implemented. The branch consolidation does not change runtime behavior.
- **Open question:** the three unrelated CTest failures and slow local fair
  smoke should be repaired or rechecked in a separately scoped handoff.
