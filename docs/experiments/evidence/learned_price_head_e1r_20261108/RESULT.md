# E1-R: potion prices from reward luck — RESULT

Pre-registration: [PREREG.md](PREREG.md) (written 2026-11-08 01:20 CET; amendment 01:33 CET after the prelaunch
review, before any row of the run existed). Ledger §TBD-b. Philipp's go: 00:58 CET ("Jo nutz fürs Logging später 4
workers, wenn die anderen 4 workers dann sind, hast meine Erlaubnis").

Run: 4 cloud workers × 4 lanes, 04:00-07:19 CET. RUN_COMMIT `32b50049`, code `cf9237a5`, binary `767a44b2…`. The
inputs are E1's 512 units of 16 seeds (111780000-111788191; no new seeds). All 512 units count, and all were first
attempts except 4 units: worker 4 lost its 4 lanes in the 05:25 CET container reset, and the queue ran those
units again after the lease ran out (`a2`). Unit wall median 5.8 min (p90 7.9, max 11.9). 50.2 core-h for the
counted units.
Analysis: `analyze.py` at `c7ddbc4c` (sha256 `d3efd494…`; prelaunch review K PASS, F1 delta PASS). Output is
`e1r_result.json`, and the tar hashes are in `inputs.sha256`.

## Gates

- **G1, same games:** 8,192 of 8,192 seeds have source rows equal to E1's (E1's G1 fields and Silver
  simulations). Heart kill is 24.51% (2,008 games), the same games as E1.
- **G2, the rolls agree with the engine:** 0 of 157,139 rolls are inconsistent, and no unit was lost at rc 88.
- **G3, completeness:** 512 of 512 units count (502 needed).

## Primary: **PARTIAL**

| estimate | pp of Heart kill | 95% CI | z |
| --- | --- | --- | --- |
| V_boss: a reward potion of random type at the act 1-2 boss reward | +1.90 ± 1.05 | [−0.16, +3.96] | 1.8 |
| C_Fairy: a Fairy drop minus any other drop (all rolls) | +9.23 ± 1.56 | [+6.17, +12.28] | 5.9 |

The PREREG rule: USABLE if both CIs exclude 0, PARTIAL if one does. V_boss misses by 0.16 pp.

## Descriptive

- **Rolls:**
  - 157,139 rolls in all, 19.2 per game.
  - 75,306 drops (47.9%); 1.44% of them are a Fairy (1,086).
  - 10,552 boss rolls: 6,363 in act 1, 4,189 in act 2, 1.29 per game. The mean chance at a boss roll is 51.6%.
  - 2,766 rolls at act 4's elite.
  - 109 rolls had chance 0 and 8,781 had chance 100; both carry no luck.
- **V_boss per act:** act 1 +2.96 ± 1.26 pp (z 2.4), act 2 +0.20 ± 1.88.
- **Act 4's elite reward** (the potion goes into the Heart fight): +2.32 ± 2.75.
- **A non-Fairy drop at the boss reward**, V_boss − q × C_Fairy: +1.77 ± 1.05 pp.
- **Sozu:** without Sozu V_boss is +2.07 ± 1.06; the 107 boss rolls with Sozu give −14 ± 10.
- **Slots:**
  - Free slot: +1.94 ± 1.09.
  - Full slots (10.2% of the boss rolls): +1.60 ± 3.87.
- **Mid-act rolls:** +0.62 ± 0.36 / +1.49 ± 0.51 / +0.84 ± 0.72 in acts 1 / 2 / 3. These are attenuated by the chance
  rule, because a drop lowers the act's later chances.
- **Mid-act rolls by the number of later rolls in the act:**
  - 0 later rolls: +3.33 ± 1.05
  - 1-2: +1.69 ± 0.54
  - 3-5: +0.95 ± 0.45
  - 6+: −0.05 ± 0.48

  The fall with more later rolls is the attenuation the PREREG predicted. However, the number of later rolls depends
  on the run's future: a death ends the act's rolls, and a drop changes the chance of dying. So these buckets are
  selected on the outcome, and they are not prices.
- **Types:** each of the 33 types has at least 500 drops, and each was fitted against the rest.
  - Only the Fairy stands out (+9.23 ± 1.56).
  - The other 32 types have |z| ≤ 2.1. The largest are Entropic Brew +3.26 ± 1.55, Cultist +2.90 ± 1.51, Regen
    +2.11 ± 1.10 and Distilled Chaos −2.22 ± 1.11.
  - Their sum of z² is 33.6 for 32 types (p ≈ 0.39 against χ²(32)). This is a post hoc check, and the separate fits
    are only nearly independent. It is what noise alone gives.
- **In HP at E1's luck price** (0.155 pp per HP, §764; G1 passed):
  - V_boss: 12.3 ± 6.8 HP
  - a non-Fairy drop at the boss: 11.4 ± 6.8 HP
  - act 1's boss alone: 19.1 ± 8.1 HP
  - C_Fairy: 59.5 ± 10.0 HP

## Comparison (HP per potion)

| | ordinary potion | Fairy minus ordinary |
| --- | --- | --- |
| Silver's default leaf | 11 | death save 0.3 × max HP, about 22-26 |
| P1, CRN stage 4 (§766) | 3.7 | 47.6 − 3.7 + death save, about 66-70 |
| PF (§767 arm) | 11 | 47.6 − 11 + death save, about 59-63 |
| §763 CRN pilot (at 0.192 pp/HP) | 3.6 [0.6, 6.7] | about 71 |
| E1-R, reward luck (at 0.155 pp/HP) | 11.4 ± 6.8 (boss reward) | 59.5 ± 10.0 |

The whole-run gate §767 found:
- P1 (ordinary potions at 3.7) costs 2.5 pp [−4.4, −0.6].
- PF (ordinary potions at 11, Fairy at 47.6) is neutral: +0.15 pp [−1.3, +1.6], NOT_WORSE.

The max-HP range in the table (75-85) is an assumption for the conversion, not a measurement.

## Interpretation (Inference)

**Fairy.** Reward luck measures the potion prices without any replay, independently of the CRN pairs.
- A Fairy drop is worth about 9 pp of Heart kill more than another drop, about 60 HP.
- That is roughly 2.5 times the death-save credit of Silver's leaf.
- It matches the CRN pilot and P1 in direction and size. In pp it is lower than the pilot's contrast of about
  13.7 pp (z of the difference about 2.4). Part of that gap can come from the different populations: reward drops
  include full slots, Sozu and act 4, while the CRN forks put the Fairy into a slot at a won fight end in acts 1-3.

**Ordinary potions.** At 8,192 games, an ordinary potion at the boss reward (about 1.8 pp, about 11 HP) is not
resolved.
- The point estimate is Silver's 11 HP.
- It is about 1.1 SE above P1's 3.7 HP. That agrees with §767, where cutting ordinary potions to 3.7 cost Heart
  kills.
- No potion type other than the Fairy differs measurably from the rest.

**Leaf weights.** Like the CRN pairs, these are marginal values under the policy that runs with Silver's 11 HP
weights, so they are not leaf weights per se (§542, §767). The Fairy premium that the luck data confirm was already
tested as a leaf weight (PF) and gained nothing measurable.

**Learned price head.** Neither the HP price (E1-S, no state dependence) nor the potion prices (no type structure
beyond the Fairy) show structure that a learned head could exploit at this data size.

## Decision

PARTIAL (a measurement; no default change).
- C_Fairy is measured; V_boss is unresolved.
- No follow-up run is started by this result.
- Two follow-ups are possible:
  - an offline estimate that uses every roll with the chance rule's attenuation modelled (exploratory, 0 core-h);
  - E1-R on the leaf pilot's second block (12,288 seeds, about 75 core-h, needs Philipp's go), for SE(V_boss) of
    about 0.66 pp.

## Commands

```
# SNAP/e1runits: this campaign's 512 tars (inputs.sha256); SNAP/e1units: E1's 512 tars (E1's inputs.sha256)
python3 -I docs/experiments/evidence/learned_price_head_e1r_20261108/selftest_analyze.py 20000
python3 -I docs/experiments/evidence/learned_price_head_e1r_20261108/analyze.py SNAP/e1runits SNAP/e1units e1r_result.json
```
