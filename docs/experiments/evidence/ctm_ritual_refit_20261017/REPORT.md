# Ritual-only CTM head refit — result (2026-10-17)

**Classification: `RITUAL_REFIT_NOT_QUALIFIED`.** Four of five preregistered
criteria pass. The no-regression check on non-Writhing Dagger fights fails its
bound: the point estimate improves, but the 95% CI upper bound is +0.0107 nat
against a +0.005 limit, with only 24 VALIDATION sources. Per the
[protocol](PROTOCOL.md) there is no recipe retry on VALIDATION.

## Frozen run

- Source `a7179dc73f1df08a7e50f66e1ec158ac6267f239` (clean), one run of
  `examples → fit → export → evaluate` under `build/ritual-refit-a7179dc7/`.
- Examples ([examples.json](examples.json)): 20,558 corrected Dagger rows,
  13,874 cross-cell duplicates merged, 430 active-Tail rows excluded, 24
  potion-unscoreable; 6,445 examples (TRAIN 4,167 / VALIDATION 2,278; positives
  455 / 251). `examples.pkl` SHA-256 `d3e9a6598534793f63d2b6e239afb8bffd8d1ee456b6927821c2fb29989f3a71`.
- Fit ([fit.json](fit.json)): fast CV held-out NLL 0.3725 → 0.3353 (16 epochs);
  standard 0.5267 → 0.3666 (31 epochs). Tensors: [fast](fast-ritual.npz),
  [standard](standard-ritual.npz).
- Candidate artifacts ([export.json](export.json)): fast `5520cab2…`, standard
  `7332e402…` (deployed bytes with only `ritual.*` replaced; not deployed).

## VALIDATION ([evaluation.json](evaluation.json))

| Criterion | Result | Pass |
|---|---|---|
| 1. Writhing not escaped (818 rows, 20 sources): NLL diff CI upper < 0 | 0.514 → 0.350, CI [−0.267, −0.063] | yes |
| 2. Calibration gap at most half of deployed | observed 8.3%; deployed 0.6% (gap 7.7 pp) → refit 6.2% (gap 2.1 pp) | yes |
| 3. Escaped Writhing P(growth) ≤ 0.001 | 0.0 | yes |
| 4. Non-Writhing (1,139 rows, 24 sources): diff CI upper ≤ +0.005 | 0.4429 → 0.4406, CI [−0.0157, **+0.0107**] | **no** |
| 5. No new infinite NLL | none | yes |

The cohorts also show improvement elsewhere:
- Smoke-not-escaped: 0.796 → 0.459, CI [−0.522, −0.165].
- Non-Writhing calibration: observed 16.1%, deployed 12.4%, refit 16.3%.
- Standard route overall: 0.509 → 0.382.

## Interpretation

On Writhing Mass the refit is clearly better and close to calibrated. On other
Dagger fights it is neutral-to-better, but the preregistered margin was tighter
than 24 sources can resolve. Lifting the A0 guard needs one of two things:
- an explicit owner override, recorded with this evidence; or
- a new protocol with a powered non-regression check (more VALIDATION sources).
