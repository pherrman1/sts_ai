# §470 evidence: boss calibration for the A20 Lizard CTM and the opt-in A20 stack

Ledger: [§470](../../ledger-06.md). Pre-registration: [PREREG-470.md](PREREG-470.md) (sha256 `582425eb…`, written
to `/mnt/project-files/ctm-a20/calib470/` before the fit; the copy here is byte-identical).

## Inputs
- Candidate `pathb-a20` with Lizard support (data branch `claude/ctm-a20-data` c507cebb): fast FAST4L `ae785ec2…`,
  standard STD2 `e338506d…`, manifest `704f2a58…`. Bundled byte for byte as
  `selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native` and
  `selfplay/models/combat_transition_near_full_escape_pathb_a20.native`.
- Fit rows: Stage 1 main corpus (`ctm-a20/stage1/` on the share), VALIDATION split, built by [extract.py](extract.py):
  59,282 rows, 3,124 seeds, rows sha256 `9b00722f…`. The same rule gives the Stage 3a TEST split exactly (63,648
  rows, 3,314 seeds, `05776fb3…`).
- Uncalibrated scores: binary `e59727ca` (the re-gate binary), [score.sh](score.sh); validation scores `9f8db36e…`.
- Fresh gate rows: the re-gate's unchanged Stage 4 rows (`/root/regate/rows`, 76,406 main rows from 3,999 seeds);
  production scores reused from the re-gate (same binary and clamped rows, PR #534).
- Calibrated runs: binary `105d1f59` built from this change (before the one-line `[ctm-a20]` log was added; that line
  does not touch scoring). Manifest [candidate-pathb-a20-lizard-boss470.json](candidate-pathb-a20-lizard-boss470.json)
  (`00bb4da6…`) = `704f2a58…` plus `bossSurvivalLogitShift`; the binary embeds the same bytes.

## Fit
[fit.py](fit.py): MLE intercept shift on the death logit of `room_class == BOSS` rows (6,745 rows, 1,593 deaths).
δ = −0.18325317 ([fit-validation.json](fit-validation.json)); validation boss bias +0.0193 → 0, boss NLL
0.3047 → 0.3029.

## Checks (prereg order)
1. VALIDATION rescored with δ ([score2.sh](score2.sh)): boss bias −0.00002 ([fit-validation-recheck.json](fit-validation-recheck.json)).
   The new binary with the old manifest reproduces the old scores byte for byte (`cmp`). Non-boss rows: identical
   except 389 of 390 `OTHER` rows with encounters 18–20 (act-1 bosses fought from an act-3 event), which the runtime
   rule (`sts::isBossEncounter`) treats as bosses; the fit used `room_class == BOSS`. Deviation from the wording
   "identical non-boss rows", recorded, not corrected.
2. Old TEST split, descriptive ([test-descriptive.json](test-descriptive.json)): boss bias +0.0133 → −0.0059.
3. Decision, fresh Stage 4 corpus ([score3.sh](score3.sh), frozen `gate3a.py` `25f7dc00`):
   [main_fresh_boss470.json](main_fresh_boss470.json) **PASS** on all five criteria. Lizard slices (diagnostic):
   [fairy](lizard_fairy_fresh_boss470.json), [brew](lizard_brew_fresh_boss470.json), 0 candidate refusals.
4. Smoke ([smoke.sh](smoke.sh)): §457 `combo_def` environment plus `STS_OOC_MCTS_A20_CTM=1`, ascension 20, seed
   74070351: rc 0, A20 banner, 2/68 V4 fallbacks, 0 support aborts, 0 hybrid support failures, died floor 33
   ([csv](smoke-74070351.csv), [mcts](smoke-74070351.mcts.csv)). Seed 74070350 was started first and killed: the
   smoke script pointed `STS_OOC_MCTS_TRACE` at the decision-trace file; fixed and rerun on the next seed.
5. Final-binary smoke ([smoke_final.sh](smoke_final.sh), binary `a5032150`, the committed code): seed 74070352,
   rc 0, both the startup banner and `[ctm-a20] ascension-20 decisions use pathb-a20` logged, 2/112 V4 fallbacks,
   0 support aborts, died floor 47 ([csv](smoke-74070352.csv), [mcts](smoke-74070352.mcts.csv)).
6. Repo tests at the final code: `ctest -R "ctm_|combat_transition_runtime_loader|combat_transition_active_lizard|combat_transition_native|ooc_mcts$|live_ooc_policy"`, 27/27 passed.
