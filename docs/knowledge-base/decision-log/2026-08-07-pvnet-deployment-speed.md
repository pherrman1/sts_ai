# 2026-08-07 — PVNet deployment speed (phase 6 of the value-targets plan): conditional leaf gating + visible-state leaf cache

Date: 2026-08-07
Session/task: Execute phase 6 of
Archived August 2026 value-targets plan — speed up PVNet leaf
deployment in Searcher3. A phase-5 (value-only utility-target trainer) draft
made earlier in the same session was reverted on user instruction (wrong
phase); nothing of it remains in the tree.

## Decision

- Implemented in `BattleScumSearcher3` (S3 only; S2 uses the PVNet policy head
  only and needs no leaf-speed work):
  1. `STS_PVNET_COND_TURN=N` / `STS_PVNET_COND_DEPTH=N` / `STS_PVNET_COND_BOSS=1`
     gate the per-expansion NN leaf (`pvnetCondAllowed`): when a condition
     fails the sim falls back to the ordinary rollout value only (α=0 for that
     sim). Defaults off — pre-phase-6 behavior preserved exactly.
  2. `STS_PVNET_CACHE=1` default ON: `evaluateLeaf` caches PVNet leaf values by
     `node.obsHash` at the direct-eval sites (no-legal-action, invalid-edge,
     depth cap) where repeated sims evaluate the same visible state.
- Direct-eval and post-rollout `evaluateLeaf` calls are deliberately NOT
  gated: the post-rollout call is the "long unresolved continuation" case the
  NN exists for.
- Not implemented, with recorded reasons: (a) batched NN leaf calls — S3 leaf
  evals are on effectively unique states (one new child per expansion), so
  batching needs a step()/backpropagate restructure for only BLAS-efficiency
  gain; (b) GBM/MLP distillation — belongs to the phase-5 training line;
  (c) rollout-skip at `STS_PVNET_ALPHA=1.0` — `playoutRandom` still runs and
  its terminal value is discarded by the α=1.0 blend (wasted compute), but
  removing it changes `bestActionSequence` semantics; recorded as a candidate
  knob for a later session.

## Rationale

- §102 recorded the neural leaf at 14-18× rollout compute at the 3k operating
  point; the phase-6 goal is fewer forwards per sim (gating) and dedup of
  repeated evals (cache), matching the user's "short/easy → rollout, long
  unresolved → NN" design. **Inference:** the per-expansion blend site is the
  dominant NN call (once per expansion ≈ once per sim); gating it is the main
  lever, the direct-eval sites are the repeat-heavy ones.
- Cache default ON is safe because `leafValue` is deterministic given the
  visible state (same rationale as S2's transposition table hashing).
- Env per-knob naming (STS_PVNET_COND_*) follows the repo's per-flag style
  over the composite string sketched in the plan.

## Alternatives considered

- Deferred-queue batched leaf evaluation in `step()` — rejected for this
  session: structural, and unique-state leaf evals leave little to batch.
- Gate the post-rollout/direct-eval `evaluateLeaf` calls too — rejected: those
  are the unresolved-continuation cases the NN should price.
- Implement the phase-5 trainer — reverted per user instruction (this session
  runs phase 6 instead).

## Evidence

- Local smoke (8 seeds, 300 sims, PVNet α=1.0, fair S3−belief−chain/64p):
  cache-on vs cache-off per-seed outcomes identical (only wall-clock differs);
  all three cond knobs change outcomes and print in the `[PVNet alpha = ...]`
  banner; `ctest` 5/5; `searchdiag` runs clean with the knobs.
- Artifacts: `build/pv6_cache_{on,off}.csv`, `build/pv6_cond_{depth,turn,boss}.csv`,
  `build/pv6_sdiag.csv` (+ logs). Code: `BattleScumSearcher3.{h,cpp}`
  (`pvnetCondAllowed`, `evaluateLeaf` cache, blend-site gate),
  `apps/one_combat.cpp` env parse.

## Status and follow-up

- Full paired gate pending: 256-seed @1k/64p vs the §124 reference (winrate
  wave baseline B1-B4 not yet recorded on GCP), then @3k if positive;
  pre-registered null at both budgets closes the leaf line (same rule as
  winrate-plan §4.3).
- Open: rollout-skip-at-α=1.0 knob (wasted rollout compute at pure-NN blend)
  as a cheap follow-up candidate; per-card-instance tokens / value-only model
  stay in the plan's phases 5/7.
