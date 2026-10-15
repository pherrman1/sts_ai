# ADR-0040: Silver's greedy leaf rollout plays cards by the gen-6-fitted table by default

Date: 2026-10-15
Status: accepted

## Context

Silver values a new tree leaf by one greedy `SilverRolloutAgent` playout. The playout picks the card to play from a
hand-written priority list (`cardPlayPriorities`). §479 added `STS_SILVER_ROLLOUT_CARD_TABLE`, a per-card,
per-upgrade play score that replaces that order. The table `card_table_g6.txt` was fitted offline to gen-6 Silver
move choices (`docs/experiments/evidence/silver_rollout_policy_2x2_20261014/card_table/README.md`; sha256
`fa93269f…5c98`).

Evidence: §479, A20 fight level. 689 paired fights from 64 source runs, greedy at 2,500 simulations, with vs without
the table: +0.33 fight score [−2.28, +2.81], NOT_SHOWN. CPU per fight 0.89x [0.87, 0.91] and per simulation 0.92x
[0.90, 0.93]. Playouts are 11.7 actions long with the table, 13.6 without. With the gen-6 tree prior, table − no table
was −0.77 [−3.32, +2.09] (descriptive). The pre-registered rule gave no follow-up for a `NOT_SHOWN` table.

On 2026-10-15 (08:15Z, thread "random rollouts"), after the §479 result, Philipp wrote: "Let's put the learned card
table as default and merge 554".

## Decision

- `SilverSearcher::envRolloutConfig` uses the table compiled into
  `include/sim/search/SilverRolloutCardTable.h` (generated from `card_table_g6.txt` with the encoding of
  `SilverRolloutAgent::loadPlayTable`) when `STS_SILVER_ROLLOUT_CARD_TABLE` is unset or empty.
- `STS_SILVER_ROLLOUT_CARD_TABLE=0` restores the hand-written priority list. Any other value is still a table file
  path. A missing or malformed file stays fatal.
- Every `SilverSearcher` takes its rollout config from `envRolloutConfig` at construction. The default therefore
  reaches native Silver in whole runs, the Silver synthetic-prior generators, the live-game advisor, unit tests and
  replay tools alike (**Inference** from the code path).
- Only the card-play order changes. Zero-cost-first, the block check, the AoE swap and randomized tie-breaks are
  unchanged. A card missing from the table scores 0.
- The `ctmsilvergen` armset `rollout479` now requires `STS_SILVER_ROLLOUT_CARD_TABLE=0`, so its source run and
  control keep the §479 baseline.

## Consequences

- Native Silver play changes (two A20 `bestbench` seeds, 74071494–495, already play out differently). Reproducing earlier results needs
  `STS_SILVER_ROLLOUT_CARD_TABLE=0`. A comparison against controls from an older binary must set it in the new arm or
  rerun the controls.
- Silver-labelled data (synthetic-prior teachers, AZ self-play) generated after this ADR differ from gens 2–6 unless
  run with `=0`. Teacher manifests do not record the variable.
- Silver gets about 11% cheaper per fight at a fixed simulation budget (§479, greedy 2.5k).
- **Unverified:** a playing-strength gain. §479 was NOT_SHOWN; a gain above about +2.8 fight score is excluded at its
  resolution. No whole-run or A0 test was run. The default follows Philipp's decision, not a passed gate.
- The combination with the ADR-0035 leaf terms and the ADR-0036 escape penalty is what §479 tested (both on).

## Evidence

Ledger-06 §479 (`docs/experiments/ledger-06.md`); evidence `docs/experiments/evidence/silver_rollout_policy_2x2_20261014/`;
`architecture/combat-search.md`; `operations/environment-variables.md`.
