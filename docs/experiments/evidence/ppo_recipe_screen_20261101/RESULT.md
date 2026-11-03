# PPO recipe screen 1: result, 2026-11-03

Pre-registration: [PREREG.md](PREREG.md), including the amendments made during the run (#966/#967/#968).

Analysis: `analyze.py` on `s1res.tgz`, which unpacks to `s1res/<ARM>/games-NNNN.csv`, `loop.json`, `config.json`,
`stalled_seeds.txt`, `serve.log` and `ram.txt`. The bundle was copied from the PC learner's run directory after
SERVE_DONE (sha256 `e9cff032…f44f`). `result.json` holds the numbers.

**Verdict: no arm is PROMISING. LAM_1 (λ 1.0) is WORSE, with the CI upper bound only just below 0. Every other arm
is NOT_SHOWN.** S1's recipe therefore stays BASE.

At this scale (30 updates, 15,360 sampled games per arm) none of the recipe changes moved heart1's Heart rate
measurably. The noise between two whole runs (BASE_S1 vs BASE, +0.82 pp) is as large as the best arm's D.

## Run
- **Schedule:** started 2026-11-02 ~08:00 CET and finished 2026-11-03 04:49 CET (SERVE_DONE).
- **Pause:** 20:32-23:13 CET, at Philipp's request. The learner stopped right after a published update and resumed from
  its saved state. Order and seeds were unchanged.
- **Setup:**
  - Start net heart1, combat K15.
  - 40 cloud actors and the learner on the PC (RTX 3060 Ti).
  - RUN_COMMIT 11c857c9; actors restarted after a stall or a container reset ran f32c9a96 (build inputs unchanged).
  - Learner restarts: on #963 (891b3edc), #964 (33b3b747, `--micro-batch 192`) and #968 (1c35bcb0).
- **Completeness:** all 19 arms are complete: 30/30 iterations (G_256 60/60, G_1024 15/15). The 5,120
  primary-metric seeds (111410240-111415359) are identical in every arm.
- **MB_512** used micro-batch 192 (gradient accumulation) from its iteration 0, as the PREREG amendment records.

## Stalls (combat > 1,000 decisions, counted as losses, #965)

9 stalled games in all, at most 1 per part, so every arm is within the cap (no INCOMPLETE arm):

| Arm | Stalled seeds |
|---|---|
| BASE | 111409050 |
| LR_3E6 | 111405435, 111409050 |
| KL_1 | 111406786 |
| MB_512 | 111406474 |
| REW_ORIG | 111408130 |
| WU_0 | 111411835 |
| WU_10 | 111403638 |
| G_1024 | 111413140 |

Two of these seeds fall in the last third (111411835, 111413140). The sensitivity D drops both from every arm, and
it changes no verdict (largest shift 0.02 pp).

## Primary metric: Heart kills in the last third

Paired by seed against BASE over 5,120 seeds, with a 95% seed bootstrap (10,000 resamples). Noise |BASE_S1 − BASE| =
0.82 pp.

| Arm | Heart % | D vs BASE (pp) | 95% CI | Sensitivity D | Verdict |
|---|---|---|---|---|---|
| BASE_S1 (noise) | 8.36 | +0.82 | [−0.08, +1.70] | +0.82 | NOT_SHOWN |
| KL_1 | 8.26 | +0.72 | [−0.14, +1.58] | +0.72 | NOT_SHOWN |
| KL_DEC | 8.18 | +0.64 | [−0.23, +1.52] | +0.64 | NOT_SHOWN |
| WU_0 | 8.18 | +0.64 | [−0.25, +1.52] | +0.64 | NOT_SHOWN |
| EP_1 | 8.12 | +0.59 | [−0.29, +1.45] | +0.59 | NOT_SHOWN |
| LR_3E6 | 8.11 | +0.57 | [−0.31, +1.46] | +0.57 | NOT_SHOWN |
| ENT_0007 | 7.95 | +0.41 | [−0.43, +1.27] | +0.41 | NOT_SHOWN |
| G_256 | 7.70 | +0.16 | [−0.72, +1.02] | +0.16 | NOT_SHOWN |
| ENT_01 | 7.68 | +0.14 | [−0.72, +1.00] | +0.14 | NOT_SHOWN |
| WU_10 | 7.66 | +0.12 | [−0.76, +1.00] | +0.10 | NOT_SHOWN |
| MB_512 | 7.62 | +0.08 | [−0.78, +0.94] | +0.08 | NOT_SHOWN |
| REW_ORIG | 7.56 | +0.02 | [−0.86, +0.86] | +0.00 | NOT_SHOWN |
| BASE | 7.54 | 0 | | | |
| EP_4 | 7.50 | −0.04 | [−0.90, +0.80] | −0.04 | NOT_SHOWN |
| G_1024 | 7.29 | −0.25 | [−1.15, +0.61] | −0.25 | NOT_SHOWN |
| KL_01 | 7.25 | −0.29 | [−1.15, +0.53] | −0.29 | NOT_SHOWN |
| CLIP_01 | 7.19 | −0.35 | [−1.21, +0.49] | −0.35 | NOT_SHOWN |
| LR_3E5 | 7.05 | −0.49 | [−1.35, +0.37] | −0.51 | NOT_SHOWN |
| LAM_1 | 6.62 | −0.92 | [−1.78, −0.08] | −0.92 | **WORSE** |

There are 18 comparisons and no multiplicity correction (none was pre-registered). At 2.5% per tail, about 0.45 false
WORSE verdicts are expected by chance, so LAM_1's WORSE verdict is weak evidence.

## Secondary

**Heart rate by seed third** (sampled play, temperature 1; seeds per third are the same in every arm, but differ
between thirds):

| | First third | Middle third | Last third |
|---|---|---|---|
| Mean of 19 arms | 8.0% | 7.6% | 7.7% |

No arm shows a rising curve. Because the seeds change between thirds, the slight dip is not paired and is not
evidence of decline.

**Training statistics** (`loop.json`):
- **BASE:** approx-KL per update ~0.011 after warm-up, so the policy does move. Entropy drifts up from 0.208 to 0.222.
- **LR_3E5:** KL ~0.03-0.04 and entropy rises to 0.33. It moves the most and is the second worst.
- **KL_1:** the lowest KL (~0.009) and the best non-noise arm.

Together these point to updates that move the policy without a useful signal behind them. That fits a sparse
1{Heart} reward (~40 kills per 512 games).

## Interpretation (Inference)
- 15k sampled games of PPO from heart1 do not improve it measurably under any of the 18 recipe variants. Larger
  steps (LR_3E5, λ 1.0; EP_4 at mid-run) lean worse, and smaller or anchored steps (KL_1, LR_3E6, EP_1) lean
  better. That is the pattern expected when the gradient carries little signal: staying close to the start net is
  the safest choice.
- The bottleneck is more likely the learning signal than the optimiser settings. Next lever: reward design, with an
  act/floor/key bonus or PBRS (Philipp, 2026-11-02), and a critic that resolves fine state differences. Longer runs
  are a second lever.
- Whole-run noise of ~0.8 pp means any later screen needs either far more games per arm or fewer, larger-effect arms.

## Decision
- **S1 recipe = BASE.** None of the changes is adopted. λ 1.0 is not used.
- **No G1:** there is no candidate net to gate.
- **Proposed next step (needs Philipp's go):** a reward screen. Arms: act-clear bonus, floor/key shaping, and PBRS
  with a simple potential (C++ φ emission needed). It would be pre-registered with fewer arms, a futility rule, and
  the validated `--compile` speed-up.
