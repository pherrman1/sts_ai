# Pre-registration: per-type Silver potion weights vs flat 11, paired whole A20 runs (follow-up to ledger §510)

Written and committed before any cohort seed ran. Philipp, 2026-10-17, thread "Silver leaf evaluation", answering
whether to test per-type potion weights in Silver's leaf: "yes set that up". Worker count: [NWORKERS](NWORKERS) and
cohort size: [COHORT](COHORT) are proposals until Philipp picks them; the run commit may change only those two files.

## Question

Silver scores every held potion at a flat 11 at a victory leaf (`SilverSearcher::evaluateEndState`; Fairy also gets
its death-save term, 0.3 × max HP). §510 priced potions at A20 by paired continuation: 7.8 HP-eq [6.1, 9.8] pooled
without Fairy (post hoc), with a wide spread by type (Attack/Blood/Skill 15-21, Swift/Essence of Steel/Block/Weak/Speed
near 0). Does Silver play better A20 runs with (a) the measured non-Fairy level or (b) per-type weights?

## Why whole runs and not single fights

A fight scored by Silver's own end-state formula would be circular: the arm that values potions at 11 would score
best under the formula that values them at 11. The value of a held potion only shows up in later fights, so the
outcome has to be measured after them. Whole A20 runs on the §473 harness are the cheapest clean measurement
(about 39 s per run, §473); §510-style fight windows scored by a value model cost more per pair and depend on that
model.

## Arms ([arm_env.sh](arm_env.sh))

All three arms are the §422/§433/§473 `off` environment (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys
off, `STS_STOP_AFTER_ACT=3`) on current main defaults (ADR-0034, ADR-0036 escape penalty 12,35, #592 rollout
zero-cost cap), plus the new research option `STS_SILVER_POTION_WEIGHTS` (per-type weights replace
`potionCount × 11` in the victory leaf, and in the loss leaf only when loss potion credit is on, which it is not by default; the Fairy death-save term is unchanged):

| arm | `STS_SILVER_POTION_WEIGHTS` |
|---|---|
| `base` | unset (flat 11; the default) |
| `level` | `FAIRY_POTION=11,SMOKE_BOMB=11,*=7.8` |
| `type` | [WEIGHTS_TYPE](WEIGHTS_TYPE) |

**The weights are fixed here, not tuned.** `type` comes from [derive_weights.py](derive_weights.py) applied to
§510's [analysis.json](analysis510.json) (the `altFloor` column, A20 floor model): empirical-Bayes shrinkage of each
type's HP-eq price toward the non-Fairy pooled price 7.8, with the between-type variance (τ² = 16.3) estimated from
the 25 non-Fairy types with n ≥ 100; types with 30 ≤ n < 100 shrink harder, rarer types get 7.8; floored at 0.
Result: 3.5 (Swift) to 12.3 (Attack). Fairy and Smoke Bomb stay at 11 in both treatment arms: Fairy already has its
own term, and Smoke Bomb's hold value is the escape option (n = 63 in §510, and a cheaper Smoke Bomb would make
escapes cheaper, a separate question).

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT); workers build `one_combat` and refuse to run unless its sha256 equals
  [binary.sha256](binary.sha256). The run commit may differ only in docs and tools.
- Cohort: **A20 seeds 111152000 .. 111152000 + N − 1**, N from [COHORT](COHORT) (at most 1,900), fresh, all three
  arms on every seed (coordinator-assigned 111152000–111153999). Seed i goes to worker (i mod NWORKERS) + 1. Smoke
  seeds 111153900–111153949; pre-launch reviewer seeds 111153950–111153999.
- Per-unit timeout 4 h. A seed drops out of all pairs (counted; no rerun or replacement) when any arm's unit (a)
  names a `[bestbench-seed-failure]` in its log, (b) ends with rc=124, or (c) has a worker stall record.

## Analysis ([tools/analyze_silver_potion_weights.py](../../../../tools/analyze_silver_potion_weights.py))

Pairs: cohort seeds with a row in all three arms. Paired seed bootstrap 95% CI, 10,000 resamples, RNG 510.
- **Primary:** Δfloor(type − base). **BETTER** if the CI lower bound > 0, **WORSE** if the upper bound < 0,
  otherwise **NOT_SHOWN**.
- **Secondary, same labels:** Δfloor(level − base) and Δfloor(type − level) (does the per-type shape add anything
  beyond the level).
- Descriptive: act-3 clears (`won`) with exact McNemar, end HP, boss deaths, pairs reaching floor 50, seconds per
  run, pairs whose rows differ at all.

**Power (Inference).** Unlike §473's Smoke Bomb penalty, potion weights affect almost every run, so most pairs will
diverge. At A20 the per-pair floor difference of diverged runs has an SD of roughly 10 floors (Inference from §473's
spread), so 1,500 pairs resolve about ±0.5 floors. NOT_SHOWN does not mean equal.

## Validity

All units rc=0 apart from the dropped seeds above. Any other nonzero rc, crash, missing seed, non-cohort seed, or a
unit whose `.env` does not carry its arm's `STS_SILVER_POTION_WEIGHTS` value exactly (unset for `base`) or that sets
`STS_SILVER_ESCAPE_PENALTY` makes the result INVALID (the analyzer checks all of these).

## Decision

- Primary **BETTER**: propose `type` as the default with a `STS_SILVER_POTION_WEIGHTS` unset/flat switch restoring
  11 (ADR); Philipp decides.
- Primary NOT_SHOWN and `level − base` BETTER: propose the `level` weights instead; Philipp decides.
- Both NOT_SHOWN: the option stays research-only; the weights are not re-tuned on these seeds.
- Either treatment **WORSE**: that variant stays off.
