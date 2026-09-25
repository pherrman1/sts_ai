# §343 corrected DEV follow-up protocol

**Original protocol prepared:** 2026-09-25, before any new 10k teacher or
1k arm run.
**Implementation SHA:** `1e63068ff548abb18638e4b02d60e7e0d6dc936c`, frozen after
independent review and before data collection.
**Decision scope:** DEV first decisions only; no gameplay, holdout, tuning, or
default promotion.

## Evidence inventory and correction

The frozen input is
[`hard64-dev-snapshots.jsonl`](../../silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl),
SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
The frozen holdout file was not read for this follow-up.

The preserved §343 1k control/B outputs remain useful for the old instrumented
throughput report, but the former 40/59-versus-35/59 quality comparison is
invalid: the control 1k runs and control 10k reference used the same
`benchmark_seed`, making the 1k trajectory a prefix of its own teacher. B
changes RNG-to-card mapping, so that comparison coupled control to its teacher
and not B. The old raw files remain unchanged and are excluded from quality
interpretation. The old CPU comparison also enabled heavy diagnostics and used
the previous baseline, so it does not satisfy the corrected uninstrumented
current-main CPU check.

A 1-simulation status smoke on the PR branch with B default-off on 2026-09-25
produced 59 `ok` rows and the same five `transactional_selection_required`
rows:
`12100014/9`, `12100014/20`, `12100029/25`, `12100039/17`, and `12100039/24`.
The fixed 59-root eligible mask is based only on those technical status
results, not selected actions or outcomes. Every prospective teacher and arm
must return `ok` for every eligible root; otherwise do not analyze the
incomplete matched screen.

## Hypothesis and setup

**Hypothesis:** candidate B reduces rollout CPU cost while preserving
first-action agreement with independent current-main teacher consensus. The
code baseline is current main `01f6f164a0fe757ec174738ac3a2f0fb98c2462d` plus
the independently reviewed default-off B gate, frozen at a candidate SHA
before data collection. With the flag omitted, control and teacher searches
use canonical piles; only treatment B enables unsorted piles inside rollout
scratch states.

Use GCC Release (`-O3 -flto`), CPU 2, and `OMP_NUM_THREADS=1`. Every replay
uses `tools/seed_guard.sh`; the guard must validate the state-bound
`benchmark_seed`, the optional `isolated_search_seed`, and the JSONL row count.
Each prospective input has 59 rows. Keep `benchmark_seed`, `state_hash`, and
all frozen snapshot fields unchanged. Record both `benchmark_seed` and the
actual `isolated_search_seed` in replay output.

For a UTF-8 string
`silver-rollout-cost-followup-20260925/{domain}/{rep}/{case_id}/{benchmark_seed}`,
derive `isolated_search_seed` as the first eight bytes of SHA-256 interpreted
as an unsigned big-endian integer. Teacher domains are `teacher-01`,
`teacher-02`, and `teacher-03`; paired arm domains are `arm-01` through
`arm-04`. Assert that the four arm seeds and three teacher seeds are pairwise
distinct for every root. The same `arm-NN` JSONL is supplied to control and B;
the only arm difference is `--unsorted-rollout-piles`.

## Quality screen and decision rule

1. Build the exact `01f6f164...` current-main replay executable and the frozen
   candidate Release executable. On the 59 eligible roots and original
   `benchmark_seed`s at 1,000 simulations, require exact selected-action
   fingerprint parity between current main and candidate with B off. This is a
   control-path parity canary, not the quality reference. Stop if parity fails.
2. Run three independent current-main-behavior 10,000-simulation teachers on
   all 59 eligible roots, using the three teacher identities and diagnostics
   off. These use the reviewed candidate executable's replay adapter to supply
   independent RNG identities; the parity canary and default-off gate bind its
   search path to current main.
3. Run four matched 1,000-simulation control/B pairs on all 59 roots, using
   `arm-01` through `arm-04` and diagnostics off.
4. A root has teacher consensus when at least two of its three teachers return
   the same `first_action_fingerprint`. Report consensus coverage and tied or
   three-way-disagreement roots. On consensus roots, each arm's score is the
   fraction of its four identities matching that root's consensus action.
   The primary paired effect is the mean per-root difference (B minus
   control); compute a deterministic 10,000-replicate root-cluster bootstrap
   percentile interval with analysis seed `20260925`. Also report each arm's
   mean agreement with all three teacher outputs across all eligible roots.
5. If the primary mean paired effect is non-negative, run the conditional
   equal-time-equivalent screen: 1,000 control versus 1,100 B simulations on
   the same four arm identities, with diagnostics off. Otherwise stop without
   an equal-runtime or gameplay run.

Directionally non-worse means the predeclared primary paired mean is at least
zero; report the interval and full root counts alongside that gate. Do not
select roots, seeds, or budgets using action outcomes.

## Uninstrumented CPU confirmation

Run four 1,000-simulation control/B pairs across the same 59 roots and
`arm-01` through `arm-04`, all with rollout diagnostics and search timing off.
Alternate order `control/B`, `B/control`, `control/B`, `B/control`. Pin each
command to CPU 2 with `OMP_NUM_THREADS=1`; use `/usr/bin/time` process user CPU
and elapsed time around the guarded executable. Report all eight raw timings,
mean and median by arm, and the B/control ratios. Do not use replay telemetry
for this CPU comparison.

No source edits, repeated seed draws, complete-combat run, or holdout run are
part of this follow-up. Commands, binary hashes, raw rows, analysis, and final
reviewed SHA will be recorded in the accompanying follow-up report.

## Execution deviation found during evidence review

The frozen protocol above specifies strings such as
`silver-rollout-cost-followup-20260925/teacher-01/01/{case_id}/{benchmark_seed}`
and `.../arm-01/01/...`. The retained input-generation helper instead hashed
`.../teacher/01/{case_id}/{benchmark_seed}` and `.../arm/01/...`. Its output
manifest matches the helper's recipe for all 413 identity/root entries and
matches the frozen protocol's recipe for 0/413 entries. The helper and manifest
predate the raw result files by filesystem mtime, but no durable protocol
amendment recorded before collection was retained. The reason for the spelling
change is unknown.

All seven identities were still derived deterministically from the case ID and
state-bound `benchmark_seed`; the three teacher seeds and four arm seeds were
pairwise distinct per root, and the same arm identity was paired across
control/B. Thus the rows preserve independent search identities under the
executed transform, but exact fidelity to the preregistered transform is
unresolved. Treat the measurements as a disclosed DEV screen under the
executed transform, not as an exact reproduction of the frozen seed recipe.
