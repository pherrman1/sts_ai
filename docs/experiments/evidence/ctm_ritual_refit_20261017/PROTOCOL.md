# Ritual-only CTM head refit on corrected pilot data — preregistration

Status: written before any refit-head score on VALIDATION was computed.
Requested by Philipp 2026-10-17 ("yes do that": refit and qualify the Ritual
head, with Smoke Bomb states included through the escape branch and a pooled
non-escape check instead of a per-cell threshold).

## Baseline evidence (already observed)

`tools/ctm_ritual_pilot_eval.py` on the §505/§506 pilot Writhing targets: the
deployed heads predict ~0.4–0.7% Dagger growth where 7–10% is observed in both
TRAIN and VALIDATION (positive-row NLL ≈ 6 nats). Escaped Smoke fights have zero
growth and the deployed heads already give them ~0. The self-consistency
exposure gap stays small (or infinite from zero-mixture rows) and cannot detect
this miscalibration, so it is not used as the gate here.

## Intervention

`tools/ctm_ritual_refit.py`: only the six `ritual.*` tensors of each deployed
artifact (fast `c6d56bbc…`, standard `b9188de0…`) change.

- Examples: every corrected pilot row (§505 + §506 outputs) whose pre-deck holds a
  Ritual Dagger, exact duplicates across cells merged, runtime route (Brew held →
  standard), ordinary support with `writhing_ritual=True`, active Tail excluded.
  Target = per-Dagger increment tuple (Writhing rows after the Implant/Omamori
  event); likelihood = Σ over the artifact's own exact potion-trace posterior.
- Fit: warm start from each artifact's own head, AdamW lr 1e-3, wd 1e-4, 256 rows
  per batch, clip 1. Epochs = argmin of 5-fold source-grouped CV inside TRAIN
  (max 80), then one fit on all TRAIN. VALIDATION and TEST are never read by `fit`.
- Recipe chosen on TRAIN CV only (lr 3e-4 underfit at 40 epochs; 3e-3 gave the
  same CV optimum as 1e-3).

## Qualification on VALIDATION (one run, frozen commit)

`ctm_ritual_refit.py evaluate` (paired deployed vs refit, same rows; source
bootstrap 2,000 reps, seed 20261017). Cohorts over VALIDATION sources only:

1. **Writhing, not escaped** (natural + Brew + Smoke-not-escaped pooled): refit NLL
   lower than deployed, paired-difference 95% CI upper bound < 0.
2. **Calibration** on the same cohort: |refit mean P(growth) − observed rate| at
   most half of the deployed gap.
3. **Writhing, escaped**: refit mean P(growth) ≤ 0.001.
4. **Non-Writhing Dagger fights** (no regression): paired-difference 95% CI upper
   bound ≤ +0.005 nat.
5. No row with infinite refit NLL in cohorts 1 and 4 unless the deployed head is
   also infinite on it.

All five pass → `RITUAL_REFIT_QUALIFIED_DEVELOPMENT`: the refit tensors may be
packaged with the `writhingRitual` capability as a research candidate (not a
default change; live/runtime selection is a separate step). Any failure →
`RITUAL_REFIT_NOT_QUALIFIED`; no retry on VALIDATION with a changed recipe
without a new protocol.

## Limits

Corrected rows cover A0 Ironclad runs that obtained a Dagger at the start, with
Act-3 hallway fights forced to Writhing. Active-Tail composition, A20, and
non-pilot Dagger acquisition timing are not evaluated. VALIDATION sources were
used as pilot coverage evidence (§505/§506) but never for fitting or recipe
choice.
