# 2026-08-09 — Canonicalize strategic CSV rows before grouped training

Date: 2026-08-09

## Decision

Both strategic trainers sort loaded rows by `(seed, decIdx)` before constructing
group offsets and initialize a deterministic batch permutation RNG.

## Rationale

The seed-disjoint splitter correctly returned row-level masks, but the trainers
assumed `(seed, decIdx)` rows were contiguous when deriving `block_start` from
`np.unique(..., return_inverse=True)`. On the frozen 3.06M-row Tier-B CSV this
triggered `seed split crossed a decision group`. After sorting, train and
validation groups remain seed-disjoint. The batch loop also referenced an
undefined `rng`; `np.random.default_rng(0)` now makes the batch order explicit.

## Evidence

The corrected token trainer loaded the full dataset, reported 3,720 train and
930 validation seeds with empty intersection, and completed a three-epoch
`STRAT_SELECT_METRIC=val_pol_ce` run. A paired full-dataset `q_top1` run was
not attempted again after resource pressure; use a reduced fixture or redirected
batch job for that comparison.

## Status

Implemented and Python-compiled.
