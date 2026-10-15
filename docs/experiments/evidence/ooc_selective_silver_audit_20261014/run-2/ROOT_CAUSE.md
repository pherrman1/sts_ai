# Run-2 failure root cause: played Discovery rejected as a health failure

Status: diagnosed and fixed in the audit sampler. Run-2 stays
**INVALID_OR_INSUFFICIENT** and sealed; nothing here is a teacher-quality result.

## Replay

Cloud Linux Release build of `6cf118d` (error transport), same frozen plan,
environment and gen6 E bytes (`ca9bd7f2…`), one process per source through
`tools/seed_guard.sh`. Seeds are the two original failed run-2 sources only.

- 97151011 and 97151010 fail at exactly the original evaluations (Act2 Silver8
  k1/candidate1 `map:4`, future 4817961396640544830; Act3 plain10k reference
  k1/candidate0 `map:2`, future 13681190408072724534). All 83 and 162 earlier
  evaluation results match the frozen run-2 raw records exactly (CPU fields
  excluded), so the cloud replay is the same computation.
- Transported reason for both:
  `audit_native_silver:simulator_health_failure`.
- Temporary local instrumentation (not committed; outputs archived) showed
  `bc.undefinedBehaviorEvoked == 1` with `g_simHealthFailureCount` unchanged
  (0 → 0, all four per-reason counts 0): floor 23 Book of Stabbing (11) and
  floor 41 encounter 51 (10). For 11 the continuation deck at that combat
  contains `DISCOVERY` (card id 113), absent from the root deck, so the
  sampled continuation acquired it before the combat.

## Cause

`terminalOutcome` in `apps/one_combat/ooc_selective_silver_sampler.cpp`
treated `bc.undefinedBehaviorEvoked` as `simulator_health_failure`. The only
setter is `BattleContext::useCard` for `CardId::DISCOVERY`
(`src/combat/BattleContext.cpp`), and the
[simulator-health page](../../../../knowledge-base/behavior/simulator-health-monitor.md)
documents it as a deliberate known-card marker, not an error. The source run
(`invalid source battle` check), ordinary live combats and the #539 teacher
comparison do not reject it, so only the audit's Silver/plain10k rescoring
did. Any continuation that obtains and plays Discovery therefore aborted the
whole source. Neither the gen6 prior nor the 2,500 budget is implicated; the
plain10k reference failed the same way.

## Fix and check

`terminalOutcome` now rejects only real health-count changes; the sampler
selftest adds an accepted played-Discovery terminal. With the fixed binary
(`ae05716b…`) both sources complete: 97151011 3 roots, parent 11.36 s / child
293.85 s CPU; 97151010 4 roots, parent 68.10 s / child 748.80 s CPU; all
prefix evaluations identical to the failed runs. These completions are
diagnostic only: no analysis, interval or quality inference was made.

A new cohort needs a new freeze and Philipp's authorization; the fix changes
which continuations are scored, so run-2 data must not be pooled with it.

`diagnostic-replay.tar.gz` (sha256
`89d63d830f9f32f32c30fcb80c08beb2abc2aee9f7534357ba3d15ed3744be29`) holds the
six replay JSONL/logs, the replay environment script and the fix patch.
`s10c` and `s11d` came from two different throwaway instrumentation builds.
