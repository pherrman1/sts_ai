# 2026-08-05 — V4 fixed-stats retrain (issue 36): falsified on the gate, deployed model stays

Date: 2026-08-05
Session/task: rerun-ledger row 36 — retrain the V4 token net with the corrected
glob-44-49 normalization (issue 36) and gate it against the deployed model.

## Decision

The corrected-stats retrain (`ooc_strategic_tok_fixed`) is **rejected**;
the deployed `ooc_strategic_tok_final.native` (sha256 `05178ec8…`) stays the
shipped artifact. The issue-36 fix remains in the trainer (correctness), and
the derived-glob normalization scale is henceforth treated as an active
hyperparameter that must be gated before any future V4 deployment.

## Rationale

- S2 pairing: −2.34pp @128 (p=0.77) and −3.91pp @256 (p=0.36) — negative but
  within noise.
- S3−belief−chain pairing (the §107-promoted search): **−8.98pp @256
  (McNemar p=0.028, significant)**; floor −3.29, HP −7.86. The wrong scale was
  accidentally beneficial — standardizing the six derived globs with their own
  statistics moved the Q-head ranking off the deployed optimum.
- Held-out CE was *better* (0.4854 vs 0.486) — ranking gains again fail to
  transfer to the gate (same pattern as §75/§80/§100), and here they are
  actively harmful.

## Alternatives considered

- Ship the fixed model — rejected: significant paired loss under the
  recommended search.
- Revert the issue-36 fix — rejected: the fix is correct; the deployment
  decision and the trainer fix are independent.
- Retrain with a tuned glob scale — open follow-up only if a future V4 retrain
  is attempted (must gate under S3−belief−chain).

## Evidence

- EXPERIMENTS.md §108 (full config, metrics, three paired gates).
- `selfplay/models/ooc_strategic_tok_fixed.{pt,native}` (native sha256
  `9a54c28a…`, export parity max err 2.5e-05).
- `build/v4fix_128.csv`, `build/v4fix_256.csv`, `build/v4fix_s3_256.csv`.

## Status and follow-up

- Implemented: §108 recorded; rerun-ledger row 36 closed (negative);
  §102-cost re-measure row closed as superseded (§107 re-sized costs).
- Open: none from this session; the derived-glob scale is now a documented
  active hyperparameter for any future V4 retrain.
