# #346 transfer test 2: E3-normalized re-test and equal-size extra-A0 control (plan, written before training)

Authorized by Philipp on 2026-10-09 11:59 UTC: "Yes do the retest and
control". Offline only; no games are played. This follows §405, whose run
omitted E3's weight normalization.

## What changes from TRANSFER-PLAN.md

Everything in [TRANSFER-PLAN.md](TRANSFER-PLAN.md) holds (data, split, features,
arms A/B/C/E, rungs, early stopping on E3 VALIDATION, TEST closed, metrics,
verdict rule), except:

1. **Weights as in E3.** Per-state weights 1/(rows in state) are rescaled by
   one factor, len(w)/sum(w) over the A0 corpus (as `tools/vwin_e3_cf.py`
   does). The A20 block gets the same factor, so an A20 state weighs as much
   as an A0 state. Flag: `--e3-weights`.
2. **New arm D (equal-size extra-A0 control).** E3 TRAIN at fraction f plus
   extra A0 rows from #334. D has as many rows as the A20 block (16,590) and
   the same total weight as the A20 block. Flag: `--extra-a0`.

## Control data (#334)

- **Source:** the #334 cloud returns in `/mnt/project-files/vwin334-cloud-returns/`
  (four archives, seeds 13001870..13002023), part of the frozen #334
  corpus.
- **Selection:** only the 96 sources that `source_split` puts in TRAIN are
  kept; their VALIDATION and TEST shards were deleted after extraction
  without reading labels. (Disclosure: while sizing the pool, the line counts
  of those shards' `map.csv` files were read. No labels or features.)
- **Rows:** the map rows of those 96 sources, 89,866 in all. Each manifest's
  `map.csv`/`runout.csv` SHA-256 is checked. A row's label is its branch's
  `finalWon`, as in E1.
- **Sample:** 16,590 rows, drawn without replacement with
  `numpy.random.default_rng(346)`. Every D row has weight
  (A20 block total weight) / 16,590.
- **Not like-for-like:** #334 rows are trajectory map rows from a different
  generator (#334, A0), not counterfactual option rows. D controls for
  "more A0 rows of the kind X2-B was trained on", not for "same generator
  at A0". The latter would need new A0 data from the §402 generator.
- **No leakage:** #334 seeds (13M) do not overlap E3 VALIDATION sources (55M).

## Metrics and decision rules

- **Primary 1 (re-test):** C − A and B − A, E3 VALIDATION map-row NLL, the
  same verdict rule as TRANSFER-PLAN.md (`TRANSFER_HELPS`, `TRANSFER_HURTS`,
  `INCONCLUSIVE`).
  - **Known in advance:** the §405 reviewer's post-hoc rerun used the same
    normalization and gave `INCONCLUSIVE` for both arms. This run is that
    analysis made pre-registered, with arm D added. It is not independent
    confirmatory evidence. Arms A, B and C should reproduce the reviewer's
    numbers.
- **Primary 2 (control):** C − D at each rung, 95% CI resampling E3
  VALIDATION source seeds (2,000 draws).
  - `A20_BEATS_EXTRA_A0`: CI entirely below 0 on at least 2 of the 3 rungs at
    or below 50%, and the 100% point difference is at most +0.002.
  - `EXTRA_A0_BEATS_A20`: CI entirely above 0 on at least 2 of those rungs.
  - `NO_DIFFERENCE_DETECTED`: anything else.
- **Secondary (descriptive):** D − A under the transfer rule; Brier score;
  boss-relic and card-reward selection gain vs V4 per arm and rung,
  including C − D.
- No promotion or default change follows from this test.

## Execution

```
python -m tools.vwin_a20_transfer /mnt/project-files/ooc-cf-pilot/e3 \
  /mnt/project-files/a20-transfer-346/cf-a20-5ba068e0 \
  --e3-weights --extra-a0 <extracted #334 TRAIN shards> \
  --output /mnt/project-files/a20-transfer-346/transfer2-<sha8>/
```

One cloud container, 4 threads, xgboost 3.4.0, seeds 0,1,2. The report and a
ledger entry follow.
