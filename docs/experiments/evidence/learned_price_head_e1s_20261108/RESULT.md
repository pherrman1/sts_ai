# E1-S: does the fight-end HP price depend on the situation? RESULT

Plan: [PLAN.md](PLAN.md) (sha256 8956c001…, written 2026-11-08 00:45 CET before any interaction was fitted).
Ledger §TBD-a. Philipp: P1 gate dropped and luck approach wanted 00:40 CET, yes to this test 00:46 CET.
Script `e1_state_dep.py` (reuses E1's `analyze.py` at f29d1695), output `e1s_result.json`. Data: E1's 512 unit tars
(the snapshot in E1's `inputs.sha256`), all 8,192 seeds, 165,773 acts 1-3 NORMAL/ELITE/BOSS fights. 0 core-h.

## Primary: **NOT_SHOWN**

Pooled luck HP price beta_bar = 0.155 ± 0.018 pp per HP (as in E1). Interactions with the fight-start state
(pp per HP per SD of the feature, standardised within act; rooms pooled):

| feature | gamma | SE | gamma / beta_bar |
| --- | --- | --- | --- |
| HP fraction | −0.024 | 0.019 | −15% |
| floor in act | −0.061 | 0.029 | −40% |
| potions held | +0.005 | 0.018 | +3% |
| max HP | −0.018 | 0.018 | −11% |

Joint Wald chi-square(4) = 6.36, p = 0.17 (rule: p < 0.01 and some |gamma| >= 20% of beta_bar). Placebo (4 random
features): p = 0.71. Resolution about ±12% of the price per SD (floor ±19%).

## Descriptive

- Per act, joint p: 0.59 / 0.21 / 0.87. The floor term is −0.089 ± 0.059 / −0.087 ± 0.043 / +0.001 ± 0.055 in
  acts 1 / 2 / 3.
- By room (pp per HP): act 1 NORMAL 0.259 ± 0.053, ELITE 0.163 ± 0.047, BOSS 0.110 ± 0.066; act 2 0.193 / 0.153 /
  0.071; act 3 0.177 / 0.139 / 0.106 (SE 0.04-0.06).
- Boss vs 0.25 × NORMAL of the same act (Silver's A20 heal model): differences +0.046 ± 0.067, +0.023 ± 0.059,
  +0.061 ± 0.054; consistent with the model.
- By start-HP-fraction tercile (low / mid / high): act 1 0.116 / 0.280 / 0.116; act 2 0.151 / 0.181 / 0.117; act 3
  0.141 / 0.127 / 0.166 (SE about 0.05); no monotone pattern.
- Fights that start at full HP: 6.7% / 12.5% / 36.5% in acts 1 / 2 / 3.

Deviation (descriptive only): terciles are equal-size groups by rank (ties in fight order), because a value split
leaves act 3's top tercile empty (36.5% of its fights start at full HP). The first run stopped with an error at
that step, after the primary fit; the rerun with the fix gives the same primary and placebo numbers.

## Interpretation (Inference)

Within act × room, the luck HP price does not change measurably with HP fraction, floor, potions or max HP at this
sample size. Effects of a third of the price per SD or more would likely have shown. A context-dependent net for HP
prices has no support from these data, which matches the CRN finding of the leaf plan's stage 4. The hint that HP
is cheaper late in acts 1-2 (z about −2) would need about twice the data to settle.

## Commands

```
# SNAP/e1units: E1's 512 unit tars (E1's inputs.sha256)
python3 -I docs/experiments/evidence/learned_price_head_e1s_20261108/e1_state_dep.py \
    docs/experiments/evidence/learned_price_head_e1_20261107/analyze.py SNAP/e1units e1s_result.json
```
