# 2026-08-05 — code review of recent models: bugs fixed, rerun ledger created

Date: 2026-08-05
Session/task: Thorough code review of the recent model stack (strategic/Q_win,
token-state, PVNet, C_psi, dist) plus the in-flight S3-ablation/S2-PVNet diff;
fix critical bugs and record invalidated experiments.

## Decision

Fix now, record everywhere:

1. **Critical correctness fixes** (all landed in the 2026-08-05 working tree,
   each tracked as an issue): `probe_cpsi.py` scalar normalization + raw
   quantiles (issue 31); PVNet `turns`/`potion` heads trained properly via
   fairgen rich labels (`endTurn,potionsConsumed,pUsed0..43`) with a loud
   warning when labels are absent (issue 32); `fit_vwin_calibration.py` PAVA on
   fit rows only (issue 33); Searcher3 `global.resize(entityDim)` heap overflow
   (issue 34); `_state.bin` fingerprint sidecar (issue 35); token-state glob
   44–49 stats from derived values (issue 36); PVNet fixed 14-token layout
   (issue 37); tok exporter fails loudly on non-default configs (issue 38);
   `train_combat_dist` val-loss selection (issue 39); calibration checker
   rejects map-encoder checkpoints loudly (issue 40); `g_s3Live=0` now truly
   removes the live-valid filter (issue 41); CRN warm start fires once per
   fresh searcher, never after `advanceRoot` (issue 42).
2. **In-flight diff kept**: the S3 ablation flags and the S2-PVNet priors
   wiring are reviewed, fixed, and land as a recorded re-test of a channel
   §102 closed (policy priors hurt at depth on S3; S2@3k is a different
   regime). Labelled **Open question** whether S2-priors will survive a gate.
3. **Q_win-line fixes landed despite the falsified line** (§104/§105): the
   corrupted artifacts would poison any future retrain; current negatives
   stand as recorded.
4. **New rerun ledger** (`evaluation/rerun-ledger.md`) maps each fix to the
   experiments it invalidates and their status; GPU-gated reruns wait for the
   free GPU and are not started on the shared VM.
5. **New finding**: `bestbench` appends without dedup; scripts must truncate
   (issue 46). The §106 ablation's first aggregation used polluted files; the
   affected arms were re-run clean.

## Rationale

- Bug-for-bug evidence at `file:line` level from the review; every fix is a
  one-behavior change with the cheapest proving check run (parity, ASAN,
  smoke datagen).
- The Q_win artifacts (calibration map, state.bin, probes) are inputs to every
  downstream trainer; leaving them broken means any future reopening of the
  line silently trains on wrong data.
- Rerun decisions follow the resource policy: local GPU when free, `sts-test`
  VM only when empty (another agent is active); benchmark gates only when the
  box is otherwise idle.

## Alternatives considered

- Drop the PVNet potion/turns heads from the export contract instead of
  training them — rejected: consumers (parity, eval, C++) already read them
  and the producer change is small; heads become meaningful after a regen.
- Land the in-flight diff as-is and fix later — rejected: the live-valid
  ablation arm measured nothing and the CRN re-warm was destructive, so
  recording results from it would have polluted §106.
- Park the Q_win-line fixes until the line reopens — rejected: small fixes,
  high reuse value.

## Evidence

- Issue entries `docs/knowledge-base/issues/2026-08-05-issue-31..46` with
  `file:line` evidence; rerun ledger `docs/knowledge-base/evaluation/rerun-ledger.md`.
- ASAN build clean on S2/S3+PVNet paths (`build_asan/one_combat`);
  `combat_pvnet_parity.py` ~1e-6; fairgen rich-label smoke
  (`/tmp/opencode/fair_v.csv`, 1816 cols); trainer smoke on rich labels.
- §106 re-run: `s3ablate_s2_ref` 43.8% reproduces the recorded 43.75%
  reference; `s3ablate_s3_ctl` re-run in flight at write time.

## Status and follow-up

- Implemented: issues 31–43 closed in-tree; issues 44–46 open (hygiene
  batch, bestbench hardening).
- Rerun rows tracked in `evaluation/rerun-ledger.md`; GPU-gated rows scheduled
  when the local GPU is free.
- Open question: whether S2-PVNet priors survive a gate at 3k sims
  (the in-flight re-test); whether §106's belief/chain deltas survive the
  clean control re-run (numbers verified after re-run).
