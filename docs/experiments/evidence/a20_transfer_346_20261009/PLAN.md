# #346 A20 counterfactual corpus (plan, written before the corpus run)

Issue #346 asks whether harder-Ascension data helps A0 models. This corpus is
Step 1 of the thread plan: the E3 counterfactual generator (§396) run at
Ascension 20, so OOC option spreads and labels can be compared with the A0 E3
corpus.

Authorized by Philipp on 2026-10-09 00:15 UTC: "we really need to also fight
the second boss. lets collect a lot of data, i have a few hours and we could
use like 20 cloud threads with 4 cores each."

## Step 0 (done 2026-10-08, main 10376b97)

`bestbench` flat10k profile (§401), seeds 59000000..59000031 paired:
A0 24/32, A20 6/32, all jobs exit 0. With `STS_STOP_AFTER_ACT=3` that run
stopped after the first Act-3 boss, so the A20 double boss was not played.
Raw files: `/mnt/project-files/a20-transfer-346/probe-10376b97/`.

## Code change in this PR

- `run_driver.cpp`: with `STS_STOP_AFTER_ACT=3` at A20, a won first Act-3 boss
  no longer ends the run; the stop waits for the second boss. A0 is unchanged.
- `ooccfpilotgen`: optional trailing `ASCENSION` argument (0..20, default 0).
  The full-run generator already plays to the end of the run, so its A20 runs
  include the second boss.
- `run_corpus.sh` here: the E3 script plus an `ASCENSION` argument.

## Corpus configuration (frozen at the PR head commit)

- Generator: `ooccfpilotgen` GEN=2, FUTURES=2, STATES_PER_SEED=2,
  TYPES=CARD_REWARD,BOSS_RELIC, ASCENSION=20, learned-stop Silver teacher:
  E3's settings except ascension.
- Seeds: worker W (0..19) runs 59100000 + 60·W .. +59, as 3 chunks of
  4 parts × 5 seeds. Total 59100000..59101199 (1,200 seeds; E3 had 1,000).
- Smoke: seed 59109000, not pooled.
- Output: `/mnt/project-files/a20-transfer-346/cf-a20-<sha8>/wWW/chunkC/`.
- Each worker builds the binary itself from the frozen commit and writes only
  to its own folder.

## Planned comparison (descriptive; no promotion)

Against E3 (A0, seeds 55000000..55000999), per decision type:
- the spread of option values within a decision (best minus mean, and
  best minus second);
- the label win rate and label entropy;
- how often the chosen option is the best one.

A model-transfer test (A0-only vs mixed vs A20-then-A0 GBM learning curves on
the fixed E3 A0 holdout) comes after this comparison, as a separate step.

Re-run of the Step 0 A20 arm with the second boss: same profile and seeds
(59000000..59000031), on this PR's binary.
