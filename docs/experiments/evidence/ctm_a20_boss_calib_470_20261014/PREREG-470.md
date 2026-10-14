# §470: boss survival calibration for the A20 Lizard CTM, and a built-in A20 switch (pre-registration)

Written 2026-10-14 before any fit. Philipp, 12:33Z: "bro i just want a functiononing a20 ctm." The coordinator
assigned §470 and seeds (live 99500000–99599999, smokes 74070350–399, reviewer 74070400–449).

## Baseline
- Candidate `pathb-a20` with Lizard support (data branch `claude/ctm-a20-data` c507cebb, `ctm-a20-stage4/candidate-lizard/`):
  STD2 `e338506d…`, FAST4L `ae785ec2…`, manifest `704f2a58…`.
- Re-gate on the fresh Stage 4 corpus (PR #534, ledger §443 continued): criteria 1, 3, 4, 5 pass; criterion 2 fails
  on BOSS rows only, death bias +0.0151 [+0.0085, +0.0213] against |bias| ≤ 0.01. Old TEST split (Stage 3a): +0.0153.
- §458 live A20 A/B with this candidate: +6.03 floors [+2.69, +9.37] vs CTM off.

## Hypothesis
One additive shift δ on the survival logit of boss encounters (the same δ in both children, fast and standard)
removes the boss over-prediction of death without changing any other prediction, and the calibrated candidate
passes all five Stage 3a criteria on the fresh Stage 4 corpus.

## Fit (Stage 1 corpus, VALIDATION split only)
- Rows: the Stage 1 main corpus (`ctm-a20/stage1/w00–w16.tar.gz` plus `rerun-stalled.tar.gz`), `main-*.jsonl`
  files, #418 hash split = `validation` (59,282 rows, 3,124 seeds). Stalled-unit seeds take their rows from the
  one-seed reruns (identical where both exist); seeds whose rerun aborted (78217905, 78218250, 78220424, 78220620,
  78225246) are dropped. The same rule reproduces the Stage 3a TEST split exactly (63,648 rows, 3,314 seeds).
  The candidate was trained on TRAIN; VALIDATION was only used for model selection.
- Scores: `one_combat ctmscorerows ROWS OUT FAST4L STD2 1` with the uncalibrated candidate, binary `e59727ca`
  (same call as the re-gate's candidate arm).
- Boss rows: `room_class == BOSS` among scored rows (gate3a's definition).
- δ: maximum likelihood for p' = sigmoid(logit(p_death) + δ) on those rows, |δ| ≤ 2. For an intercept shift the
  MLE sets the mean death bias on the fit rows to 0. Applied at runtime as survival logit − δ on boss encounters.
  Because the Lizard/Brew composition is nonlinear, the δ fit on composed p_death is an approximation; the checks
  below use the real scorer with δ applied.
- Nothing else is fit or tuned. No retraining. No second parameter after seeing results.

## Runtime change (default off, no change for production)
- The research-candidate manifest may carry `bossSurvivalLogitShift` (a number). When present, both runtimes loaded
  under that manifest add it to the death logit (survival logit − δ) when the encounter is a boss
  encounter (`sts::isBossEncounter`). Absent field = today's behavior, byte for byte.
- The calibrated A20 manifest, STD2 and FAST4L are bundled in `selfplay/models/` and pinned in the binary, like the
  production manifest. A new opt-in switch (default off) makes live OOC MCTS use that stack at ascension 20 with
  active Lizard on, without manifest or path variables. Below ascension 20 it uses today's production stack.

## Checks (in order; stop at the first failure)
1. Sanity on VALIDATION: rescoring with δ gives |boss death bias| ≤ 0.002 and identical non-boss rows.
2. Descriptive: old TEST split boss death bias with δ (this split was seen at Stage 3a; not a decision).
3. Decision: frozen `gate3a.py` (`25f7dc00…`) on all 76,406 fresh Stage 4 main rows, same production arm, same five
   criteria and bars as PREREG-REGATE. PASS = all five pass. Honest label: this corpus has been looked at once (the
   re-gate); the calibration is fit without it, but its boss bias was known when this step was chosen.
4. Smoke: one A20 run with the switch on (seed 74070350), banner shows the A20 stack, 0 Lizard support aborts.

## Outcome
- PASS: PR with ledger §470, independent review. Making the switch the A20 default is Philipp's call. A live A/B
  of the calibrated stack (seeds 99500000+) only on his word.
- FAIL: ledger §470 NOT_QUALIFIED; the switch PR can still land default off if Philipp wants the uncalibrated stack.
