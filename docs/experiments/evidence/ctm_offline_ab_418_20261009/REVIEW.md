# Independent review: #418 offline CTM A/B (production vs pathb-r2 escape-only)

Reviewed 2026-10-09. Read-only. Verdict: **PASSED**, no blocking issues for a pre-registered live 128-pair A/B.

## What was checked

* Integrity: `sha256sum -c SHA256SUMS.txt` in `ctm-pathb/offline-ab-20261009/` is all OK. Script copy = commit
  72ebd7d1 bytes = ff71cf53...0005, and every results JSON records that `scriptSha256`. The runbook copy is identical
  to the committed RUNBOOK.md. PREREG-FROZEN (14:05:18Z) is after the commit (14:04:35Z) and records FASTF 90806c25,
  STD1E b9188de0 and manifest d9d8377e.
* Script against the pre-registration (runbook section 4): populations (valid / both / candOnly / prodOnly / neither),
  per-row metrics (clip, HP floor at log 1e-6, survival_bias = y - p), paired source-seed bootstrap (one count matrix
  shared by both stacks, deltas taken per row, ratio of seed-weighted sums, 95% percentile), G1-G4, the
  FAIL/PASS/NON_INFERIOR logic, and the gate guard on reps/seed/split. All match. Tag enum ordinals (37/17/21) match
  `include/constants/Potions.h`; `split_for_seed` matches `tools/combat_transition_model_experiment.py:211`.
* Recomputation (this folder): the production Stage 0 local-part scores in `ctm-stage0/analysis/scores/local-w*-learned.csv`,
  concatenated, are byte-identical to Philipp's `stage0_learned.prod.csv` (418e3259...). Tags regenerated from
  `ctm-stage0/part-local` are byte-identical (1815a621...). Re-running `compare` here (`python3 -I`, numpy 2.5.3)
  reproduces every production-side mean, CI and census count in `stage0_learned.json` exactly (19 slices, 0
  mismatches). A separate naive loop bootstrap reproduces the production survival NLL CI [0.0498, 0.0942].
* Results: main_test census 50,185 rows / 2,355 seeds, prodOnly 0, candOnly 425 (smoke_bomb 416, hp_envelope 9),
  hpZero 0/0, all guards true, no flags. ΔH -0.0675 [-0.0727, -0.0627], ΔS -0.0006 [-0.0015, +0.0004]. Boss ΔS
  upper +0.0035 < 0.02, boss ΔH upper -0.47 < 0.10, candidate bias [0.0006, 0.0028] inside ±0.01. PASS follows.
  No flags in any secondary set or in the Stage 0 replication.

## Deviation (-P -E instead of -I)

Harmless. -I = -E -P -s; the only difference is the user site, which is appended after the stdlib and only supplied
numpy. The recomputation under -I with a different numpy patch version gives bit-identical bootstrap results.

## Non-blocking notes for the live A/B pre-registration

1. The HP gain is mostly the teacher shift (H5): production boss hp_bias +11.8 HP, candidate -0.2; non-boss gain is
   small. Survival is a tie. Offline says nothing about play strength.
2. The candidate is slightly more optimistic about survival than production: Δbias +0.0017 [0.0013, 0.0022] overall,
   +0.0128 [0.0100, 0.0158] on bosses (inside the band). candOnly boss rows with a held Smoke Bomb (42 rows) show
   bias +0.06 and hp_bias +8.6, too few to flag. Worth a diagnostic in the live A/B (boss deaths per arm).
3. The hand-back carried only results/extract/PREREG/DEVIATIONS. The runbook's tarball also includes scores/, tags/
   and logs/ (the `ctmscorerows research candidate pathb-r2` lines and `rows=R scored=S` counts). Candidate loading
   is shown only indirectly (it scores smoke_bomb and hp_envelope rows production refuses; the loader is fail-closed
   on manifest d9d8377e). Attach the logs to the evidence PR.
4. Stage 0 replication used the 43-seed local part (849 rows), the runbook default; it agrees in direction but is weak.
5. Pending knowledge impact: ledger §386 "no escapes" wording (runbook H4).
