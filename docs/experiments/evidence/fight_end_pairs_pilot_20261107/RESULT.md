# RESULT: stage-2 leaf pilot, paired fight-end continuations under net-0420 (2026-11-07)

Design: [PREREG.md](PREREG.md), amended before the stop by
[deviation 1](PREREG.md#deviation-1-2026-11-07-before-the-stop-inverse-probability-weights). Run commit 41cb91db
(code 6e72a8d8), binary `96861592…`, net-0420 (`8c0bd16c…`), combat B,
`fightendpairgen 8 FIRST 1000 20 OUT n=4,ooc=ppo default`. Analysis: `analyze.py` at c3433e78, output
[`results/analysis.json`](results/analysis.json).

**Decision: GO.** This is the weighted analysis, which is the primary one under the PREREG as amended by deviation 1
before the stop. The frozen unweighted analysis gives **NO-GO**. The two decisions differ.

The weights are the exact inverse inclusion probabilities of the fork sampler. Without them, the analysis estimates the
wrong population: forks of runs that die soon after a fight are over-sampled, and the base copy replays the source run,
so its outcome is biased towards a loss (see [Weighted against unweighted](#weighted-against-unweighted)). No default
changes in any case.

## Run

- **Start and stop.**
  - The first unit was claimed at 09:38 CET.
  - Philipp did not stop the run, so the 12 h cap ended it. The stop was requested at 21:39 CET, and `worker.sh stop`
    reached all 40 workers by 21:44 CET.
  - Running units finished and uploaded; the last tar (111795760) landed at 23:37 CET.
  - The stop did not depend on any result: the cap was fixed, and the interim training (below) did not move it.
- **Units.** 1,948 of the 2,560 units started, in queue order. 1,938 uploaded, and every uploaded unit passes the unit
  check (rc 0, 8 source rows; `units_bad` is empty).
- **Units not uploaded.** 10 started units did not upload:
  - 9 failed all four attempts with rc 1: 111781544, 111781808, 111783952, 111786448, 111790136, 111790960, 111792384,
    111792648 and 111794712;
  - 111793728 failed two attempts and was not retried after the stop.

  One failing continuation kills the whole unit (prelaunch review K, F1). The repro of 111781808 is a
  `CombatStateFailure` stall on seed 111781809 at floor 51. Each unit's attempts all ran on one worker, but the
  failures are spread over 10 workers, and 111781808 also fails in a fresh container, so they come from the units, not
  the workers. The 10 units are 0.5% of the started units. That is under the 2% re-run threshold, so nothing was
  re-run, and a failed unit is dropped whole. The drop is not random: it removes the runs whose continuations stall
  (80 of 15,584 started source runs).
- **Upload warnings.** W9 and W10 logged ".part File exists" for 111790832 and 111795320, and the claim of 111790832
  says `failed: rc=upload`. Both tars landed complete and pass the unit check, so both units count.
- **Size.** 15,504 source runs, 61,739 forks (3.98 per run) and 6.48 copies per fork, base included: about 400,000
  continuations.
- **Cost.**
  - Continuations: 1,869 core-h, 16.8 s each. By act: 14.3, 19.6, 22.1 and 8.0 s.
  - Source runs: 89 core-h, 20.7 s each.
  - Total: 1,958 core-h.
- **Policy path.** No flag on either check:
  - The source runs kill the Heart in 24.39% of runs. §760 had 25.49% for net-0420 on G1's seeds, and the band is
    20-31%.
  - The net's fallback share is 0.

## Weighted against unweighted

| | weighted (primary, deviation 1) | unweighted (frozen) |
| --- | --- | --- |
| S: −15 HP, acts 1-4, Δ pp [95%] | −2.94 [−3.50, −2.35] | +0.15 [−0.30, +0.62] |
| S: potion, acts 1-4 | −2.29 [−2.91, −1.71] | −0.09 [−0.60, +0.40] |
| S: −5 max HP, acts 1-4 | −2.77 [−3.37, −2.13] | +0.12 [−0.36, +0.61] |
| sign check S | pass | pass |
| β, pp per HP [95%] | +0.192 [+0.147, +0.234] | −0.056 [−0.090, −0.021] |
| cost*, core-h [95%] | 638 [430, 1,078] | ∞ (β ≤ 0) |
| price check P | pass | fail |
| **decision** | **GO** | **NO-GO** |
| 8-HP z, acts 1 / 2 / 3 | 5.6 / 4.3 / 1.2 | 7.4 / 0.7 / 0.7 |
| base Heart kill | 35.53% | 24.50% |

**The decisions differ.** Every unweighted act-1 cell is positive, from +1.3 to +2.8 pp: losing HP, a potion, max HP or
gold appears to raise the Heart kill. This is the length bias that deviation 1 removes:

- A run with K eligible fight ends gives each of them with probability min(4, K) / K.
- K depends on the run's future. Forks from runs that die soon after the fight are therefore over-represented.
- The base copy replays the source run exactly, so the base outcome of those forks is mostly a loss.
- The variant copies leave that path, so D = y_variant − y_base is biased upwards.

In acts 3 and 4, runs have similar K. The weights barely vary there (n_eff ≈ pairs), and the two analyses agree within
0.3 pp. The unweighted 8-HP z of 7.4 in act 1 measures a +1.84 pp effect, which has the wrong sign.

The frozen script itself (`analyze.py` at 41cb91db), run on the same tars, gives the unweighted column exactly.

The weighted base Heart kill (35.5%) is above the run-level rate (24.4%). That is expected. The weighted rate counts
every eligible won fight end once, and runs that kill the Heart have more of them. Unweighted, the base rate is close to
the run-level rate (24.5%), because most runs give 4 forks.

**Labeling.** The weighted decision is the decision under the amended PREREG.

- Deviation 1 was committed at 16:17 CET (b651ebc4, c3433e78), five hours before the stop, and passed K's delta review.
- Interim data informed it. In the exploratory interim training (below), every family looked like a gain in act 1. A
  check on 250 interim units then found an act-1 base Heart kill of 16.9% unweighted against 29.2% weighted.
- The amendment rests on the sampler's mechanism, which is exact for `strata=none`, not on the size of any effect. Rows,
  seeds, the stop rule and every threshold stayed as frozen.

## Cells (weighted, Heart kill in pp)

Δ is the mean of D = y_variant − y_base with its 95% source-seed bootstrap CI. f is the discordance and ρ the pairing
efficiency. n_eff = (Σw)² / Σw².

| act | family | pairs | n_eff | Δ [95%] | f | ρ | unweighted Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | −3 HP | 36,098 | 27,866 | −0.24 [−0.87, +0.36] | 0.139 | 0.64 | +2.60 |
| 1 | −8 HP | 35,763 | 27,621 | −1.93 [−2.61, −1.25] | 0.163 | 0.57 | +1.84 |
| 1 | −15 HP | 34,519 | 26,704 | −3.49 [−4.23, −2.75] | 0.193 | 0.48 | +1.27 |
| 1 | potion | 20,248 | 16,277 | −1.69 [−2.46, −0.92] | 0.159 | 0.60 | +1.75 |
| 1 | −5 max HP | 36,098 | 27,866 | −2.62 [−3.38, −1.86] | 0.194 | 0.48 | +1.46 |
| 1 | −50 gold | 30,405 | 23,528 | −1.32 [−2.11, −0.54] | 0.200 | 0.47 | +2.84 |
| 2 | −3 HP | 15,949 | 14,868 | −0.97 [−1.69, −0.26] | 0.129 | 0.72 | +0.29 |
| 2 | −8 HP | 15,782 | 14,716 | −1.68 [−2.45, −0.91] | 0.153 | 0.67 | −0.23 |
| 2 | −15 HP | 15,242 | 14,227 | −2.85 [−3.67, −2.00] | 0.174 | 0.62 | −1.22 |
| 2 | potion | 11,948 | 11,279 | −2.74 [−3.72, −1.76] | 0.157 | 0.68 | −1.35 |
| 2 | −5 max HP | 15,949 | 14,868 | −3.08 [−3.96, −2.14] | 0.189 | 0.59 | −1.41 |
| 2 | −50 gold | 14,082 | 13,125 | −1.37 [−2.30, −0.35] | 0.206 | 0.56 | +0.31 |
| 3 | −3 HP | 8,889 | 8,800 | −0.25 [−1.06, +0.56] | 0.117 | 0.77 | −0.01 |
| 3 | −8 HP | 8,870 | 8,781 | −0.49 [−1.29, +0.34] | 0.118 | 0.76 | −0.28 |
| 3 | −15 HP | 8,787 | 8,699 | −1.56 [−2.46, −0.69] | 0.137 | 0.73 | −1.30 |
| 3 | potion | 8,843 | 8,763 | −2.41 [−3.47, −1.47] | 0.142 | 0.71 | −2.24 |
| 3 | −5 max HP | 8,889 | 8,800 | −2.73 [−3.78, −1.68] | 0.179 | 0.64 | −2.44 |
| 3 | −50 gold | 8,184 | 8,102 | −0.88 [−1.99, +0.22] | 0.183 | 0.63 | −0.68 |
| 4 | −3 HP | 803 | 797 | −1.92 [−4.04, +0.25] | 0.099 | 0.76 | −1.87 |
| 4 | −8 HP | 802 | 796 | −2.40 [−4.83, −0.05] | 0.121 | 0.71 | −2.37 |
| 4 | −15 HP | 795 | 789 | −5.82 [−8.27, −3.39] | 0.121 | 0.72 | −5.91 |
| 4 | potion | 564 | 560 | −5.43 [−8.49, −2.43] | 0.129 | 0.53 | −5.50 |
| 4 | −5 max HP | 803 | 797 | −1.86 [−4.11, +0.46] | 0.109 | 0.74 | −1.87 |
| 4 | −50 gold | 122 | 121 | +0.74 [−5.87, +6.79] | 0.125 | 0.70 | +0.82 |
| 1-4 | −3 HP | 61,739 | 51,526 | −0.50 [−0.97, −0.03] | 0.131 | 0.71 | +1.57 |
| 1-4 | −8 HP | 61,217 | 51,121 | −1.57 [−2.06, −1.04] | 0.150 | 0.67 | +0.94 |
| 1-4 | −15 HP | 59,343 | 49,658 | −2.94 [−3.50, −2.35] | 0.174 | 0.62 | +0.15 |
| 1-4 | potion | 41,603 | 36,408 | −2.29 [−2.91, −1.71] | 0.153 | 0.69 | −0.09 |
| 1-4 | −5 max HP | 61,739 | 51,526 | −2.77 [−3.37, −2.13] | 0.188 | 0.58 | +0.12 |
| 1-4 | −50 gold | 52,793 | 44,200 | −1.23 [−1.89, −0.57] | 0.198 | 0.56 | +1.61 |

The weighted base Heart kill by act is 26.3%, 36.8%, 51.9% and 71.4% for acts 1-4.

**Final floor** (secondary, weighted Δ in floors):

| family | act 1 | act 2 | act 3 | acts 1-4 |
| --- | --- | --- | --- | --- |
| −3 HP | −0.22 | −0.25 | −0.06 | −0.19 |
| −8 HP | −1.26 | −0.67 | −0.10 | −0.82 |
| −15 HP | −2.58 | −1.31 | −0.28 | −1.67 |
| potion | −1.20 | −0.86 | −0.20 | −0.80 |
| −5 max HP | −1.60 | −0.84 | −0.17 | −1.05 |
| −50 gold | −0.61 | −0.30 | −0.02 | −0.38 |

## HP slope, resolution per act and projection

- **Slope.** β = 0.192 pp of Heart kill per HP [0.147, 0.234]. It is fitted over acts 1-3, through the origin, on the
  −3, −8 and −15 HP pairs.
- **Resolution per act.** The 8-HP price is −1.93 pp in act 1 (z 5.6), −1.68 pp in act 2 (z 4.3) and −0.49 pp in act 3
  (z 1.2). The pilot resolves acts 1 and 2 at z ≥ 3 but not act 3 (`pilot_resolves_hp8_all_acts` is false).
- **Projection.** cost* = 638 core-h [430, 1,078]. That buys z = 3 on an 8-HP price of 8β = 1.53 pp in each of acts
  1-3, and it is under a third of the pilot's own cost. Two caveats (descriptive, not pre-registered):
  - The pre-registered formula uses the per-fork variance. Forks of one run are correlated, since their base copies
    share the source run's outcome, so the seed-bootstrap SE is larger (variance about ×2.0 in act 1, ×1.5 in act 2 and
    ×1.3 in act 3). With the bootstrap SE, the same target costs about 960 core-h. P passes either way.
  - The projection assumes each act's 8-HP price equals the pooled one. Act 3's is a third of it (−0.49 pp). Reaching
    z = 3 at act 3's own price needs about (3 / 1.18)² ≈ 6.5 times the act-3 forks: about 58,000, against 8,870 now.
- **Shape (descriptive).**
  - In act 1 the first 3 HP are nearly free (−0.24 pp), while −8 and −15 HP cost 0.24 and 0.23 pp per HP.
  - Right after the act-1 and act-2 bosses, HP is nearly free: −15 HP gives +0.10 and −0.29 pp. At A20 the act
    transition heals 75% of the missing HP (`GameContext.cpp`, ascension ≥ 5).
  - Max HP and potions keep their price after those bosses: −2.6 to −2.9 pp.

**Room cells** (weighted Δ in pp, pairs in brackets):

| act | room | −3 HP | −8 HP | −15 HP | potion | −5 max HP | −50 gold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | NORMAL | −0.23 (24,002) | −1.89 (23,924) | −3.91 (23,602) | −1.26 (13,872) | −2.48 (24,002) | −1.03 (20,154) |
| 1 | ELITE | −0.42 (9,687) | −2.49 (9,508) | −3.53 (8,861) | −2.40 (5,362) | −2.86 (9,687) | −1.93 (8,083) |
| 1 | BOSS | +0.21 (2,409) | −0.43 (2,331) | +0.10 (2,056) | −2.85 (1,014) | −2.90 (2,409) | −1.49 (2,168) |
| 2 | NORMAL | −0.88 (10,664) | −1.80 (10,596) | −3.36 (10,354) | −2.52 (8,877) | −2.71 (10,664) | −1.59 (9,607) |
| 2 | ELITE | −1.02 (4,111) | −1.68 (4,048) | −2.36 (3,843) | −3.50 (2,444) | −4.11 (4,111) | −0.87 (3,413) |
| 2 | BOSS | −1.51 (1,174) | −0.78 (1,138) | −0.29 (1,045) | −2.70 (627) | −2.60 (1,174) | −1.19 (1,062) |
| 3 | NORMAL | +0.23 (6,058) | −0.26 (6,054) | −1.37 (6,014) | −2.07 (6,330) | −2.59 (6,058) | −0.78 (5,652) |
| 3 | ELITE | −1.24 (2,831) | −0.99 (2,816) | −1.96 (2,773) | −3.26 (2,513) | −3.03 (2,831) | −1.12 (2,532) |
| 4 | ELITE | −1.92 (803) | −2.40 (802) | −5.82 (795) | −5.43 (564) | −1.86 (803) | +0.74 (122) |

Act-3 boss wins and the act-4 Heart never reach a reward screen, so they give no forks.

## Prices in HP units (descriptive)

At β, the prices are:

- a potion: 12.0 HP on average;
- a max-HP point: 2.9 HP;
- a gold: 0.13 HP, so 50 gold ≈ 6.4 HP.

The Fairy potion makes up 10% of the potion pairs and is worth 75 HP [65, 85]. Without it, the mean potion is worth
3.6 HP [0.6, 6.7] (Δ −0.69 pp [−1.28, −0.11] on 37,410 pairs).

Only Fairy, Swift and Power have CIs above 0. The four types with negative estimates (Fear, Liquid Memories, Dexterity
and Gambler's Brew) have CIs that include 0.

Potion types with at least 200 pairs (`descriptive.py`; seed bootstrap, β fixed at its point estimate):

| potion | pairs | Δ pp [95%] | HP [95%] |
| --- | --- | --- | --- |
| FAIRY_POTION | 4,193 | −14.35 [−16.33, −12.49] | 74.8 [65.2, 85.2] |
| HEART_OF_IRON | 272 | −3.63 [−8.72, +1.37] | 18.9 [−7.1, 45.5] |
| SWIFT_POTION | 1,714 | −3.22 [−5.75, −0.83] | 16.8 [4.3, 30.0] |
| POWER_POTION | 1,485 | −2.73 [−5.25, −0.15] | 14.3 [0.8, 27.4] |
| COLORLESS_POTION | 1,355 | −2.04 [−4.55, +0.42] | 10.6 [−2.2, 23.8] |
| ENERGY_POTION | 1,589 | −1.59 [−4.15, +0.84] | 8.3 [−4.4, 21.6] |
| ELIXIR_POTION | 1,389 | −1.56 [−4.14, +0.83] | 8.2 [−4.3, 21.6] |
| ESSENCE_OF_STEEL | 1,344 | −1.55 [−3.89, +0.86] | 8.1 [−4.5, 20.3] |
| BLOCK_POTION | 1,313 | −1.45 [−3.78, +0.78] | 7.5 [−4.1, 19.7] |
| FLEX_POTION | 1,496 | −1.41 [−3.70, +0.89] | 7.4 [−4.6, 19.3] |
| SKILL_POTION | 1,564 | −1.39 [−3.84, +0.96] | 7.2 [−5.0, 20.0] |
| EXPLOSIVE_POTION | 1,543 | −1.15 [−3.65, +1.21] | 6.0 [−6.3, 19.1] |
| ANCIENT_POTION | 1,794 | −1.13 [−3.20, +1.01] | 5.9 [−5.2, 16.7] |
| REGEN_POTION | 618 | −1.11 [−4.88, +2.62] | 5.8 [−13.6, 25.5] |
| DISTILLED_CHAOS | 386 | −0.98 [−5.67, +3.49] | 5.1 [−18.2, 29.6] |
| STRENGTH_POTION | 1,286 | −0.90 [−3.24, +1.44] | 4.7 [−7.5, 16.9] |
| LIQUID_BRONZE | 1,834 | −0.75 [−3.21, +1.69] | 3.9 [−8.8, 16.7] |
| SNECKO_OIL | 417 | −0.70 [−5.24, +3.73] | 3.6 [−19.5, 27.3] |
| BLOOD_POTION | 647 | −0.67 [−4.68, +3.09] | 3.5 [−16.1, 24.4] |
| SPEED_POTION | 2,115 | −0.51 [−2.43, +1.43] | 2.7 [−7.5, 12.7] |
| FIRE_POTION | 848 | −0.27 [−3.21, +2.68] | 1.4 [−14.0, 16.8] |
| DUPLICATION_POTION | 927 | −0.08 [−2.84, +2.74] | 0.4 [−14.3, 14.8] |
| CULTIST_POTION | 675 | +0.08 [−3.72, +3.75] | −0.4 [−19.6, 19.4] |
| BLESSING_OF_THE_FORGE | 1,658 | +0.23 [−1.94, +2.41] | −1.2 [−12.6, 10.1] |
| WEAK_POTION | 1,800 | +0.30 [−1.68, +2.32] | −1.6 [−12.1, 8.7] |
| ATTACK_POTION | 991 | +0.44 [−2.17, +3.00] | −2.3 [−15.7, 11.3] |
| GAMBLERS_BREW | 1,234 | +1.29 [−1.39, +3.95] | −6.7 [−20.6, 7.3] |
| DEXTERITY_POTION | 2,394 | +1.51 [−0.27, +3.31] | −7.9 [−17.3, 1.4] |
| LIQUID_MEMORIES | 871 | +1.58 [−1.09, +4.00] | −8.2 [−20.9, 5.7] |
| FEAR_POTION | 1,816 | +1.58 [−0.61, +3.81] | −8.3 [−19.9, 3.2] |

## Other descriptive

- **Skips.**
  - `pot:*` without a potion held: 29,839.
  - Gold below 50: 8,946.
  - −15 HP at 15 HP or less: 2,396. The −15 HP cells therefore leave out the forks at 15 HP or less (3.9%).
  - −8 HP at 8 HP or less: 522.
- **Weights by act.** The mean weight is 3.91 in act 1, 5.67 in act 2, 6.78 in act 3 and 6.91 in act 4. The maximum is
  9.0 (acts 1-2) and 8.75 (acts 3-4).

## Interim training (exploratory, not part of this analysis)

Philipp asked at 12:48 CET to train on the values while the units ran. That work is on the share
(`leaf-plan/pilot-interim-training/`), with its own plan written before the first fit. It does not enter this
analysis, and the stop stayed fixed at the cap.

Its unweighted results (until 16:00 CET) are superseded by the weighted ones (`RESULT-lernkurve.md`, 880 units). Those
show two things:

- net-0420's critic gives the best HP and potion prices;
- new heads on the frozen trunk still improve with more data.

## Interpretation (inference)

- **What the pairs resolve.** At this size, paired fight-end continuations to the run end resolve per-act Silver leaf
  prices:
  - HP in acts 1-2;
  - potions and max HP in acts 1-3, where every CI is below 0;
  - gold pooled and in acts 1-2.
- **Act 3.** Its HP price is small and unresolved. Resolving it needs act-3 forks specifically, for example with
  `acts=3`.
- **Max HP is expensive.** 5 max HP cost about as much as 11 HP in act 1, and more than 15 HP in acts 2-3.
- **Weights.** Any later use of these pairs (fits, price tables, training) has to weight forks by eligible / sampled.
  Without the weights, the HP price even changes sign.

## Next (needs Philipp's go)

Under the PREREG, GO means stage 3 is proposed to Philipp, with its own go. Acts 1-2 are already resolved, so the
proposal can split in two:

- stage 4 (model fit) directly on these labels, for the HP prices in acts 1-2 and for potions and max HP;
- an act-3 label run (`acts=3`) for act 3's HP price. About 49,000 more act-3 forks at 6.5 copies and 22 s each come
  to roughly 2,000 core-h (rough estimate).

No default changes.

## Files

- `results/analysis.json`: the `analyze.py` output. The weighted analysis is at the top level, the unweighted one under
  `unweighted`.
- `descriptive.py` and `results/descriptive.json`: the tables above, the potion-type prices with CIs, the source-run
  cost and the weights by act.
