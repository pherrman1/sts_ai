# E3: first counterfactual OOC tranche (2026-10-07/08)

Ledger: [§396](../../ledger-06.md). Pre-registration: [PREREG.md](PREREG.md).
Plan: [ACTION-PLAN.md](ACTION-PLAN.md). Worker brief: [BRIEF-cloud.md](BRIEF-cloud.md).

## Data

- **Producer:** `one_combat ooccfpilotgen` GEN=2 (#434). Frozen git 8edf724c,
  binary sha256 `224a1a42…`, identical in every worker. Learned-stop V4
  teacher. Each branch plays the whole run and is labelled `finalWon`.
- **Generation:** 25 cloud workers × 40 seeds, seeds 55000000..55000999, K=2
  futures, up to 2 states per seed (CARD_REWARD and BOSS_RELIC).
- **Excluded:** 199 of 200 parts finished. Seeds 55000830..834 (w20) stalled
  in Silver; that part was killed and excluded.
- **Reruns:** several workers reran unfinished parts on the same seeds after
  container restarts. The generator is deterministic, so this does not change
  the data.
- **Validity:** 15,667 of 15,668 runs are valid. One (state, k) group was
  dropped. 1,983 states in total, split as TRAIN 1,380 / VALIDATION 333 /
  TEST 270 by `source_split`. TEST was not opened.

  | Type | Act 1 | Act 2 | Act 3 |
  |---|---|---|---|
  | Card reward | 374 | 322 | 299 |
  | Boss relic | 557 | 431 | — |

- **Archive:** `/mnt/project-files/ooc-cf-pilot/export/e3-corpus.tgz`, sha256
  `b9599bf3c3d90b81c913751dae6bfc7ef07a133a7ec971dbca306b032ca25b40`. A copy
  is on Philipp's machine.

## Analysis

`tools/vwin_e3_cf.py`:

- **Cloud arms** (X2B, X2B_raw, E3 with its learning curve) ran at 659726a1
  and are in `report-cloud.json`.
- **F2 and F2_334** need the local #334 corpus. They ran at dc6fd330 on
  Philipp's machine: `--corpus334 …/corpus-mixed-1024.json` (sha256
  ae56f963…), 4 CPU threads, 6m47s. Output is in
  `/home/philippherrmann/Documents/sts/build/e3-f2-dc6fd330/`. The cloud arms
  in that run reproduce the cloud report exactly. That output is not archived
  here; [report-f2-validation-excerpt.json](report-f2-validation-excerpt.json)
  is a verbatim copy of its VALIDATION results for the F2 and F2_334 arms.

Arms:

- **X2B:** frozen X2-B with the four HIDDEN_FUTURE fields masked to -1.
- **E3:** the X2-B recipe trained on E3 TRAIN map rows only. Public 457
  features, each state weighted 1, 3-seed mean.
- **F2_334:** #334 TRAIN, all rows, with E1's F2 focal upweighting.
- **F2:** F2_334's rows plus E3 TRAIN map rows, scaled to the same block
  weight.

Selection gain is the win rate of the model's argmax option minus V4's chosen
option, using the K=2 outcomes. It is computed per state, with a 95% CI that
resamples source seeds.

## Results (VALIDATION, 167 card-reward / 166 boss-relic states)

| Arm | NLL | Brier | Card reward | Boss relic | Pooled |
|---|---:|---:|---|---|---|
| X2B | 0.4957 | 0.1591 | +0.002 [−0.035, +0.038] | −0.048 [−0.093, −0.003] | −0.023 [−0.055, +0.005] |
| E3 | 0.4854 | 0.1577 | +0.010 [−0.028, +0.049] | +0.011 [−0.027, +0.047] | +0.010 [−0.016, +0.037] |
| F2_334 | 0.4870 | 0.1574 | −0.004 [−0.040, +0.031] | −0.015 [−0.063, +0.030] | −0.010 [−0.041, +0.020] |
| **F2** | **0.4788** | **0.1548** | +0.017 [−0.018, +0.051] | +0.012 [−0.027, +0.050] | +0.015 [−0.013, +0.042] |
| Uniform random option | | | −0.001 [−0.027, +0.026] | −0.090 [−0.124, −0.055] | −0.045 [−0.066, −0.024] |

Paired contrasts:

| Contrast | Card reward | Boss relic | Pooled |
|---|---|---|---|
| F2 − X2B | +0.015 [−0.008, +0.041] | +0.060 [+0.020, +0.104] | +0.038 [+0.015, +0.062] |
| F2 − F2_334 | +0.021 [−0.006, +0.049] | +0.027 [−0.006, +0.063] | +0.024 [+0.003, +0.046] |

E3 learning curve at 25/50/100% of TRAIN sources:

| Metric | 25% | 50% | 100% |
|---|---|---|---|
| NLL | 0.4936 | 0.4824 | 0.4854 |
| Card-reward gain | +0.005 | −0.004 | +0.010 |

Agreement with V4 and skip choice:

| Arm | Agrees with V4 (card) | Agrees with V4 (relic) | Picks skip (card) |
|---|---|---|---|
| X2B | 0.24 | 0.36 | 0.24 |
| F2 | 0.34 | 0.51 | 0.21 |

## Verdict under the pre-registered rule

- **Not positive:** F2's card-reward selection gain is +0.017, and its CI
  crosses zero.
- **No second tranche:** the learning curve is not rising.
- **Rule outcome:** `E3_NEGATIVE` for the card-reward criterion. No online A/B
  follows.

Descriptive findings outside the decision rule. These are VALIDATION results,
one of several contrasts reported, and slightly optimistic because the
retrained arms early-stop on VALIDATION:

1. **Card rewards:** a uniformly random option ties V4. Inference: under the
   V4 + Silver continuation, the win-rate effect of the card-reward choice is
   below roughly ±3 pp per decision, which is too small to learn or verify at
   this scale.
2. **Boss relics** carry a real choice effect (random −9 pp).
   - X2-B picks worse than V4 (−4.8 pp).
   - F2 matches V4 and beats X2-B by 6 pp.
   - E3 data adds to #334 (pooled F2 − F2_334 +2.4 pp, CI above zero).
   - F2 also has the best map-row NLL and Brier.
   - Robustness (independent review): dropping all 14 future-dependent
     boss-relic fields (the 4 masked plus `bossId` and the `fm*` map counts)
     keeps E3 − X2B at +0.051 [+0.008, +0.095].
