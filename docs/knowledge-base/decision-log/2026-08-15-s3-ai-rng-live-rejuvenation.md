# 2026-08-15 — Searcher3 live AI_RNG rejuvenation treatment design

## Decision

Implement an opt-in Searcher3 live treatment mode with mutually exclusive
`off`, `placebo`, and `ai` arms. The first causal implementation permits at
most one attempt per combat, at the first eligible persistent-filter boundary.
The mode defaults off and does not alter the existing shadow defaults.

## Contract

Eligible boundaries require non-collapse, valid battle-start ancestry,
persistent filtered-belief operation, and positive support in `1..16`. The live
path gives initial particles stable lineage IDs and retains immutable
battle-start particles and full committed history. A child is generated from
the source lineage's battle-start particle, uses the existing conditional
AI_RNG block-generation semantics, replays the complete history, and is
accepted only on exact full-history agreement plus non-AI block equality and
full-hidden-state novelty. Placebo runs the same proposal and source/slot
mechanics but inserts an exact duplicate.

Each accepted source is split 50/50 into the source and one zero-weight slot;
the child inherits the source lineage ID. Collapse-fresh invalidates ancestry
and disables further live attempts for that combat. Proposal/replay RNG is
local and deterministic and does not consume live or search RNG. The initial
implementation used one combat-level proposal sequence; this review correction
derives each proposal stream from the fixed salt, game seed, floor, encounter,
source filter decision, source lineage ID, and proposal number, while retaining
the validated `sampleParticles()` AI_RNG distribution semantics.
## Alternatives rejected

- Reusing the shadow oracle-anchored proposal path — rejected because it can
  depend on the real hidden state.
- Repeated attempts or child-of-child expansion — rejected for the first causal
  screen because generic duplication and changing support mechanics would be
  harder to distinguish from novel AI_RNG support.
- Changing `filterRealTransition` weighting — rejected; its equal-survivor
  behavior is outside this experiment.
- Making placebo bit-identical to OFF — rejected; placebo must match treatment
  proposal work, source selection, slots, weights, and timing, differing only
  in inserted child content.

## Evidence

- `/home/philippherrmann/Documents/sts/sts_ai-worktree-test/src/sim/search/S3RejuvenationProbe.cpp::runLiveRejuvenation`
- `/home/philippherrmann/Documents/sts/sts_ai-worktree-test/src/sim/search/ScumSearchAgent2.cpp::playoutBattleFairSearcher3`
- `/home/philippherrmann/Documents/sts/sts_ai-worktree-test/apps/test_belief.cpp::testLiveRejuvenationAttemptGate`
- Existing `rejuv_conditional_blocks`, `rejuv_history_replay`,
  `persistent_belief_transfer`, and `rng_state_propagation` tests.

## Status

Implementation and focused verification pass. The corrected one-seed smoke
passed. The corrected matched 8-seed baseline, placebo, and AI arms each have
8/8 rows. Placebo telemetry has 1,573 rows with 442 injected duplicates and
`unique_children=0`; AI telemetry has 1,553 rows with 424 injected novel
children and `unique_children=424`. The paired AI-minus-placebo deltas are zero
for both win and floor on this implementation/control block. This is an
implementation/control validation, not a scientific treatment result. The
The completed 32-seed gate on seeds `910000–910031` was mixed/inconclusive.
AI−PLACEBO was +3/32 wins and +1.25 mean floor, with exact McNemar
`p=0.5078125` and bootstrap floor CI `[-1.9375,+4.25]`. Both live arms were
exposed in all 32 seeds, but AI remained below OFF in aggregate. An independent
raw-data audit is preserved at
`build/s3live32_causal_gate_910000_910031/s3live32_causal_gate_audit.md`.
The result does not establish H1 or prove that generic duplication was harmful;
no 64-seed extension was started.
