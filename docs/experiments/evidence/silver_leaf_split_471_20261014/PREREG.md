# Pre-registration: end-of-run Silver leaf parts vs legacy leaf, paired whole runs (ledger §471)

Written and committed before any cohort seed ran. Philipp, 2026-10-14 13:43Z, in the thread "Situational Silver leaf
evaluation", tapped "Split test" on the card "Test the end-of-run leaf parts alone (heal fix + final-fight leaf)
against the old leaf?" after §468 (bundle of all four: A0 NOT_SHOWN, A20 floors WORSE but wins +3.8 pp, more act-1
deaths). Worker count: [NWORKERS](NWORKERS) (Philipp's pick).

## Question

Do the two end-of-run leaf changes alone (A20 first-boss heal fix and final-fight leaf) play better whole runs than the
legacy leaf? They act only in the run's last boss fights, so a difference should show at floors 50–52.

## Arms ([arm_env.sh](arm_env.sh))

Both arms are the §422/§433 `off` environment (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys off,
`STS_STOP_AFTER_ACT=3`), plus:

| arm | `A20_BOSS_HEAL_FIX` | `FINAL_FIGHT_LEAF` | `NO_LOSS_POTION_CREDIT` | `RELIC_HEAL_LEAF` |
|---|---|---|---|---|
| `base` | 0 | 0 | 0 | 0 |
| `end` | 1 | 1 | 0 | 0 |

(all `STS_SILVER_*`). What they change in `SilverSearcher::evaluateEndState`:
- A20 boss heal fix: no act-transition heal credit after the first A20 act-3 boss (no effect at A0).
- Final-fight leaf (§466): in the run-ending fight every win scores `53 + root maxHp`; losses keep shaping without
  potion or cheat-death credit.
- (No loss potion credit and relic heal leaf, both in §468's bundle, stay off in both arms.)

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT) (§468 code plus a merge of main with #532, which changes only OOC MCTS paths;
  both arms run with OOC MCTS off, but the binary differs from §468, so §468 rows are not reused); workers build `one_combat` and refuse to run unless its sha256 equals
  [binary.sha256](binary.sha256). The run commit may differ only in docs and tools.
- Cohorts ([COHORT](COHORT)): **A0 seeds 100000000–100000499** and **A20 seeds 100000500–100000999**, fresh, both
  arms on every seed (coordinator-assigned 100000000–100000999). Seed i of the concatenated list goes to worker
  (i mod NWORKERS) + 1. Smoke seeds 74070450–74070451 ([SMOKE.md](SMOKE.md)).
- Per-unit timeout 4 h. A seed drops out of its cohort's pairs (in both arms; counted in the report; no rerun or
  replacement) when either arm's unit (a) names a `[bestbench-seed-failure]` in its log (Silver stall caught by
  `bestbench`), (b) ends with rc=124 (4 h timeout), or (c) has a worker stall record `stall-ARM-aASC-SEED.txt`
  (log silent 60 min, backtrace taken, process killed; brief §3).

## Analysis ([tools/analyze_silver_leaf_471.py](../../../../tools/analyze_silver_leaf_471.py))

Pairs: cohort seeds with a row in both arms. Paired seed bootstrap 95% CI, 10,000 resamples, RNG 471 (A0) / 491 (A20).
- **Primary A0:** Δwin = win(end) − win(base).
- **Primary A20:** Δfloor = floor(end) − floor(base) (wins are too rare at A20, §457).
- Each: **BETTER** if the CI lower bound > 0, **WORSE** if the upper bound < 0, otherwise **NOT_SHOWN**.
- Secondary (descriptive): the other metric per cohort, exact McNemar, end HP, boss deaths, seconds per run,
  pairs reaching floor 50, deaths per act, and wins among seeds where both arms reach floor 50.

**Reading.** 500 A0 pairs resolve about ±3.5 pp of win rate; 500 A20 pairs about ±1 floor (Inference, from typical
discordance). Effects of single leaf terms are likely smaller; NOT_SHOWN does not mean equal. The two terms are tested
together; they act in different fights (A20 first act-3 boss vs the run-ending fight).

## Validity

All units rc=0 apart from the dropped seeds above; any other nonzero rc, crash, missing seed, non-cohort seed, or a
unit whose `.env` does not set all four options to its arm's value (`base` all 0; `end` heal fix and final-fight leaf 1, the other two 0) makes the result
INVALID (the analyzer checks all of these).

## Decision

- **BETTER** in a cohort: propose making the two end-of-run options the default for that setting (ADR); Philipp decides.
- **NOT_SHOWN:** no default change beyond the A20 heal fix, which stays default on unless the A20 cohort is WORSE.
- **WORSE** in the A20 cohort: Philipp decides on the A20 heal fix; the final-fight leaf stays off.
