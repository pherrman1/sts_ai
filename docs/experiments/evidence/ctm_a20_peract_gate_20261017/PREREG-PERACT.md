# Pre-registration: per-act boss death-logit shifts for the A20 CTM (offline gate)

Written 2026-10-17 before the decision corpus is scored. Requested by Philipp (16:18Z, "yes to per act boss shift
offline gate"), following audit finding 2 in `/mnt/project-files/audit-2026-10-17/ctm-a20.md`.

## Candidate and incumbent
- Base: the uncalibrated pathb-a20 stack (fast `ae785ec2…`, standard `e338506d…`, manifest `704f2a58…`, LIZARD=1).
- Incumbent: the deployed §470 global shift. Death logit −0.18325317 on every `sts::isBossEncounter` row.
- Candidate: one death-logit shift per act, applied to boss rows by the row's `act`. Act 4 (the Heart) gets no shift.
  The shifts are the MLE intercepts on Stage 1 VALIDATION rows with `room_class == BOSS` (the §470 fit rule and rows,
  59,282 rows, sha `9b00722f…`), fit on uncalibrated scores:
  act 1 −0.4747, act 2 −0.2371, act 3 +0.0720.
  These were computed during the audit, before this file was written. The Stage 1 TEST split was also inspected then,
  so TEST is not a decision set.

## Decision corpus
- The fresh Stage 4 main corpus, all rows. This is the same corpus as the §470 decision step: `ctm-a20/stage4/w*.tar.gz`
  with the w02 per-seed rerun (seed 78600595 excluded), 76,406 rows from 3,999 seeds, `rows/none.jsonl` sha
  `690eef72…`.
- It has never been used for a per-act fit or a per-act look.
- Scored once with the uncalibrated base via `one_combat ctmscorerows`. Both arms are then derived from the same
  score file by the logit shift (exact for the survival head; HP heads are unchanged by either arm).

## Criteria (all must pass), seed-cluster bootstrap with 2,000 resamples, 95% CIs
1. Boss-row survival NLL, candidate minus incumbent: upper CI < 0. Boss rows are those with `room_class == BOSS`;
   the rows with a boss encounter but room class OTHER are reported separately.
2. Pooled boss death bias of the candidate within ±0.01 (the §443 criterion 2 bar).
3. Per-act boss death bias of the candidate: |bias| ≤ 0.02 in each of acts 1–3.
4. Non-boss rows are identical in both arms (by construction, checked).

PASS means a runtime change (a manifest field with per-act shifts, Heart excluded) may be implemented. The
implementation then needs its own review. Making it the default is Philipp's call. FAIL or a partial pass is
recorded as is, with no retry on this corpus.
