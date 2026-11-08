# E1-S: does the fight-end HP price depend on the situation? (offline, plan)

Written 2026-11-08 00:45 CET, before any interaction term was fitted. Data: E1's luck rows (PR #1004, ledger §764;
`/mnt/project-files/learned-price-head/e1/units/`, the snapshot listed in E1's `inputs.sha256`). 0 core-h, no new seeds.
Context: Philipp 2026-11-08 00:40 CET dropped the P1 gate and wants prices from the E1 luck approach. A learned,
context-dependent price only pays if the HP price varies with the situation in ways Silver's leaf does not model
(it already models the act-boss heal). The CRN pairs could not show such variation (leaf stage 4).

## Question

Beyond act x room (NORMAL / ELITE / BOSS), does the luck HP price at a fight's end change with the state at the
fight's START? Start features are fixed before the fight's luck is drawn, so E[u | start] = 0 and the interactions
are identified by the same randomisation as E1's main estimate.

## Model

E1's `per_act_room` luck model (analyze.py at f29d1695: game-level OLS of heartKill on per-game sums of the luck
components, HC1 SEs, ATT = 2) on all 8,192 E1 seeds (fights with a healthy replay), plus, over the acts 1-3
NORMAL/ELITE/BOSS fights:

- `hz_k = sum_f u_h,f * z_k,f` (HP-luck interactions; coefficient gamma_k, pp per HP per SD of z_k), and
- `sz_k = sum_f u_s,f * z_k,f` (survival-luck interactions, controls).

Features z_k (fight start, standardised within act over the fights used):
1. HP fraction `hp / maxHp`;
2. floor (position within the act);
3. potions held (`potionCount`);
4. max HP.

## Primary test and decision

Joint Wald test of gamma_1..gamma_4 = 0 (HC1 covariance, chi-square with 4 df).
- **STATE_DEPENDENT** if p < 0.01 and at least one |gamma_k| >= 0.2 x beta_bar, where beta_bar is the pooled luck
  HP price on the same seeds (E1: 0.155 pp per HP): some feature moves the price by at least 20% per SD.
- **NOT_SHOWN** otherwise.

STATE_DEPENDENT leads to a proposal (needs Philipp's go): a per-fight HP price from these terms in Silver's existing
price-table leaf, gated against Silver's default. NOT_SHOWN: the context-dependent head stays parked; global
luck prices remain the path.

## Checks and descriptives (not gated)

- Placebo: the same fit with 4 random N(0,1) features per fight (numpy seed 20261108); its Wald p is reported and is
  expected to be unremarkable. A placebo p < 0.01 makes the primary result void.
- gamma_k with 95% CI; implied SD of the price across fights, sqrt(gamma' C gamma) / beta_bar (C = feature
  correlation).
- Per-act gamma (one fit per act, interactions within that act only).
- Price by start-HP-fraction tercile (tercile x act h columns in place of the HP-fraction interaction).
- Act-boss fights: luck price vs 0.25 x the same act's NORMAL price (Silver's A20 heal model).
