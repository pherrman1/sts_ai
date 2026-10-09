# Pre-registration: Run 2 (Path B) CTM on the §408 states (ledger §410)

Renumbered from §409 (taken by #467) after the freeze; `worker_r2.sh` and `tools/analyze_ctm_r2.py` keep
the old label in their comments so that the frozen bytes stay unchanged.

Written and committed before any rerun seed ran. Philipp's go: 2026-10-09 15:30Z ("Yes do that"),
in reply to the §408 follow-up offer to score the retrained Run 2 CTM on the same states.

## Question

§408 found low-sim Silver more accurate than the production CTM on every post-combat field. Does
the Run 2 retrain (#418 Path B candidate `pathb-r2`, the stack in the live A/B) close that gap?

## Design

- Mode: `one_combat ctmsilvergen 16 0 PREFIX SEED 0 teacher.json 0`. `REPLICATES=0` is the CTM-only
  mode (commit `a84be6bc`): no Silver arms; at every real fight entry it scores the production CTM
  exactly as in §408 and the candidate stack (same draw seeds) as forecaster `ctm_r2`.
- Seeds: the §408 v2 seeds 62100000–62100255, in the same 16 shards of 16 seeds
  ([worker_r2.sh](worker_r2.sh)). This is not a fresh-seed test: the states must be the §408 states,
  so that the Silver forecasts and the truth (control replay) can be reused. No seed beyond these runs.
- Candidate: `FAST-final.native` `90806c25…`, `STD1-escape.native` `b9188de0…`, manifest
  `candidate-v3.json` `d9d8377e…` (as in the #418 live A/B), active Lizard on, loaded as a research
  candidate (the mode refuses otherwise).
- Environment: §408 [env.sh](env.sh) (exact-10k Silver source runs, frozen V4 OOC policy, root prior
  loaded but unused here), `STS_EXECUTABLE_GIT_SHA` = the binary build commit `a84be6bc`.
- Binary: Release `one_combat` built at `a84be6bc`, sha256 in [r2-binary.sha256](r2-binary.sha256);
  [teacher-r2.json](teacher-r2.json) is the §408 teacher with only that binary's git and executable
  hashes swapped in. Smoke (seed 62100000, 17 states): source fields and every production CTM
  forecast and sample identical to §408.
- Budget: about 4.5 CPU-hours (256 exact-10k source runs at ~62 CPU s), on this thread's own 4-CPU
  container, four shards at a time.

## Validity (all required, else INVALID and nothing is scored)

- Every §408 v2 state reappears with identical source fields and an identical production CTM
  forecast (support, reason, P(death), E[HP | win], expected HP; CPU columns excepted).
- Every production CTM sample row is identical to §408.
- All 16 shards rc=0.

## Analysis ([tools/analyze_ctm_r2.py](../../../../tools/analyze_ctm_r2.py))

- States: §408-valid states that both the production CTM and the candidate support.
- Truth and losses as in §408 with its post-combat HP deviation: death Brier; HP MSE with truth =
  control RAW post-combat HP (CTM h = (1 − P(death)) E[HP | win], prior 256 ×4 = replicate mean);
  per-field sample Brier against the control's RAW post-combat state.
- Comparisons: `ctm_r2 − ctm` and `ctm_r2 − prior256` (×4) on death Brier, HP MSE and every field,
  paired seed-bootstrap 95% CI (10,000 resamples, seed 0). Label per metric: A_LOWER (CI < 0),
  A_HIGHER (CI > 0), else NO_DIFFERENCE_DETECTED.
- Primary reading: `ctm_r2 − ctm` on HP MSE, death Brier and the all-but-HP joint Brier.
  Secondary: whether `ctm_r2 − prior256` still shows the §408 gap on HP and the all-but-HP joint.
- Reported too: CPU per forecast and per sample, per-act HP RMSE and bias, the candidate's support
  (including states the production stack does not support, e.g. Smoke Bomb escapes).

## Decision

Descriptive. No default changes; the CTM is neither retired nor swapped by this entry. Philipp
decides.
