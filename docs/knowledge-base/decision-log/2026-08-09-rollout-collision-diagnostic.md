# 2026-08-09 — Mid-rollout visible-state collision frequency in Searcher3 fair play (measurement + diagnostic column)

Date: 2026-08-09
Session/task: Measure mid-rollout visible-state collision frequency in
Searcher3 fair play (diagnostic measurement; gates rollout TT / path-reuse /
move-ordering work). No gameplay change.

## Decision

1. Measured the collision rate with the existing `rollouttrace` mode on the
   §135a gate corpus (`build/leafdiag_gate_64.csv`), replaying 16 seeds with
   the full gate-matching env (incl. V4 OOC gate arms — required for 100%
   leaf re-capture; the minimal env in the plan causes re-capture WARNINGs).
2. Added a trailing `stateHash` column to `rollouttrace` output: each row's
   OWN `visibleHash` (`CombatObservation::fromBattleContext(bc).visibleHash()`,
   equals the leaf `obsHash` at step 0). The mode previously emitted only the
   leaf hash (deduped per decision by construction → leaf-level collisions
   are 0 by design), so exact per-state hashing was impossible from the old
   CSV. Diagnostic-only output path; `search::g_onRolloutStep` stays nullptr
   in all normal paths, so default behavior is byte-identical.

## Result (evidence)

Exact mid-rollout (steps ≥ 1) visibleHash collision rate: **0.0891%** pooled
(756,724 unique / 757,399 states across 4,821 searches, 73,354 trajectories);
per-search mean 0.0916%, median 0%, 4.3% of searches have any collision.
Cross-trajectory repeats within a search: 0.139% of mid-rollout states.
Coarse-feature upper bound (CSV projection): 2.84% — the extra hashed fields
differentiate ~97% of coarse-colliding states. §114's near-zero-collision
prediction and the leafCache "effectively unique" comment are now backed by
data. **Verdict: <1% → dead end for rollout TT / path reuse / move-ordering
caching.**

## Rationale

The task's decision rule is >10% viable / <1% dead end. The coarse CSV
projection (2.56-2.8%) was in the ambiguous band, so an exact measurement was
required; adding the per-state hash to the diagnostic tool's output was the
smallest change that yields it (no search-code instrumentation needed).

## Alternatives considered

- Coarse-feature proxy only (no code change): 2.84% upper bound is
  inconclusive vs the 1% threshold — rejected as the sole answer.
- `thread_local std::map` counter inside `playoutRandom` behind an env flag
  (plan's alternative): would touch search code; the diagnostic output column
  is smaller and gives richer per-state data — chosen.
- Replaying with the minimal env (no OOC gate arms): 0% leaf re-capture
  (documented §135a constraint) — rejected; the full gate env matches the
  corpus.

## Evidence

`build/rollout_trace.csv` (830,753 rows; 16 seeds, replay 1000, asc 0, full
gate env; 100% re-capture). Columns 1-20 of a 2-seed replay verified
byte-identical to the §135a `build/rollouttrace_gate_64.csv` rows for those
seeds. Reproducibility note: the §142 (de75e6c) tok-globals 50→41 change and
its uncommitted `NGLB 50→41` loader follow-up break loading of the deployed
tok-net models, so the replay must run from a pre-§142 build (commit 2fb271a
+ the stateHash column; `/tmp/sts_ref` worktree).

## Status

Closed (measurement complete, dead end recorded in `EXPERIMENTS.md` §144).
No gameplay promotion. The `stateHash` column is committed via the §142
commit (de75e6c swept the working tree) and present in the working tree.
