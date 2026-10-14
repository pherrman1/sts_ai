# Pre-registration: situational Silver leaf bundle vs legacy leaf, paired whole runs (ledger §468)

Written and committed before any cohort seed ran. Philipp, 2026-10-14 11:18Z, in the thread "Situational Silver leaf
evaluation" after §466: "Keep it in. Fix the bug for the A20 boss. Add the smaller idea and test again with all
those things." Worker count: [NWORKERS](NWORKERS) (Philipp's pick).

## Question

Does Silver with all situational leaf changes together play better whole runs than the legacy leaf?

## Arms ([arm_env.sh](arm_env.sh))

Both arms are the §422/§433 `off` environment (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys off,
`STS_STOP_AFTER_ACT=3`), plus:

| arm | `A20_BOSS_HEAL_FIX` | `FINAL_FIGHT_LEAF` | `NO_LOSS_POTION_CREDIT` | `RELIC_HEAL_LEAF` |
|---|---|---|---|---|
| `base` | 0 | 0 | 0 | 0 |
| `all` | 1 | 1 | 1 | 1 |

(all `STS_SILVER_*`). What they change in `SilverSearcher::evaluateEndState`:
- A20 boss heal fix: no act-transition heal credit after the first A20 act-3 boss (no effect at A0).
- Final-fight leaf (§466): in the run-ending fight every win scores `53 + root maxHp`; losses keep shaping without
  potion or cheat-death credit.
- No loss potion credit: every loss drops the 5.5-per-held-potion credit.
- Relic heal leaf: victory HP counts Meat on the Bone / Burning Blood / Black Blood post-combat heals.

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT); workers build `one_combat` and refuse to run unless its sha256 equals
  [binary.sha256](binary.sha256). The run commit may differ only in docs and tools.
- Cohorts ([COHORT](COHORT)): **A0 seeds 98000000–98000499** and **A20 seeds 98000500–98000999**, fresh, both arms
  on every seed (coordinator-assigned 98000000–98000999). Seed i of the concatenated list goes to worker
  (i mod NWORKERS) + 1. Smoke seeds 74070100–74070101 ([SMOKE.md](SMOKE.md)).
- Per-unit timeout 4 h. A seed drops out of its cohort's pairs (in both arms; counted in the report; no rerun or
  replacement) when either arm's unit (a) names a `[bestbench-seed-failure]` in its log (Silver stall caught by
  `bestbench`), (b) ends with rc=124 (4 h timeout), or (c) has a worker stall record `stall-ARM-aASC-SEED.txt`
  (log silent 60 min, backtrace taken, process killed; brief §3).

## Analysis ([tools/analyze_silver_leaf_468.py](../../../../tools/analyze_silver_leaf_468.py))

Pairs: cohort seeds with a row in both arms. Paired seed bootstrap 95% CI, 10,000 resamples, RNG 468 (A0) / 488 (A20).
- **Primary A0:** Δwin = win(all) − win(base).
- **Primary A20:** Δfloor = floor(all) − floor(base) (wins are too rare at A20, §457).
- Each: **BETTER** if the CI lower bound > 0, **WORSE** if the upper bound < 0, otherwise **NOT_SHOWN**.
- Secondary (descriptive): the other metric per cohort, exact McNemar, end HP, boss deaths, seconds per run,
  pairs reaching floor 50 (the A20 double boss, where the heal fix acts).

**Reading.** 500 A0 pairs resolve about ±3.5 pp of win rate; 500 A20 pairs about ±1 floor (Inference, from typical
discordance). Effects of single leaf terms are likely smaller; NOT_SHOWN does not mean equal. This run tests the
bundle, not the individual terms.

## Validity

All units rc=0 apart from the dropped seeds above; any other nonzero rc, crash, missing seed, non-cohort seed, or a
unit whose `.env` does not set all four options to its arm's value (0 for `base`, 1 for `all`) makes the result
INVALID (the analyzer checks all of these).

## Decision

- **BETTER** in a cohort: propose making the bundle the default for that setting (ADR); Philipp decides.
- **WORSE:** keep all opt-ins off; the A20 heal fix stays (it is a correctness fix) unless the A20 cohort is WORSE,
  in which case Philipp decides.
- **NOT_SHOWN:** no default change beyond the A20 heal fix.
