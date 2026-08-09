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

## Post-hoc synthesis (2026-08-09)

### S3 gate invalidation (§113)

The S3−belief−chain pairing that produced the −8.98pp (p=0.028) result used
both arms with the pre-§113 S3 enumerator (commit 619c12c), which had a
battle-skip exploit at WARCRY/GAMBLE CARD_SELECT states (zero valid edges →
UNDECIDED break → rewards/advance). The reference 60.2% is an invalidated
pre-fix baseline (honest re-baseline 42.6–44.5% on the same block, §113/§115).
The v4fix arm's skip contamination was never instrumented and is plausibly
model-dependent. The S3 "statistically significant" claim is therefore
confounded. The only valid honest evidence is the S2 pairings (−2.3 to
−3.9pp, n.s.). This qualifies but does **not** change the original decision
(deployed model stays, fix stays in trainer).

### Two-bug interaction
At §108 time, a second independent trainer bug was present: the glob-block
feature-order skew (deck counts `d0..d11` fed into glob slots 24–35 that C++
fills with forward-map features; discovered and fixed 2026-08-09). Both the
deployed model and the §108 retrain were trained with this skew. The §108
retrain fixed the normalization-stats bug while the feature-order skew
persisted — the interaction has never been tested.

### The offline→online inversion pattern
§108 is the 5th documented occurrence of held-out metric gains failing to
transfer to online paired gates (after §62, §75, §80, §100). The held-out
metrics were directionally better (CE, policy_top1, margin, q_top1) while the
online gate was worse. Offline metrics are useful for debugging and
architecture selection but do not substitute for paired gates as the
deployment criterion.

### Affirmation
- The original decision stands: deployed `05178ec8` stays; `ooc_strategic_tok_fixed` is archived; issue-36 fix stays in the trainer.
- The recommendation to treat derived-glob scale as an active hyperparameter (sweep scaling factors, don't assume "correct" stats are optimal) remains open and was correct.
- The later 2026-08-09 honest artifact swap (NGLOB=50 leaky → NGLOB=42 honest, commit `fc82830`) is a separate development that supersedes the deployment target but does not change the §108 conclusion.
