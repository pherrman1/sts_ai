# Leaf plan, stage 4: offline fit on the pilot's CRN pairs (plan, 2026-11-08 00:20 CET)

Philipp chose "Offline-Fit, dann Gate" on 2026-11-08 at 00:06 CET. Written before the fits on all units ran. One
preview exists: `leaf_prices.py` on the 880 interim units (P1 beats L by about 12 bp in the skill against C).

**Data.** All 1,938 pilot units (PR #1003): 15,504 source runs and 61,739 forks. Every pair is weighted by
w = eligible / sampled (PREREG deviation 1).

**Models.**

- `L`: Silver's default victory leaf. It is hp + 2 maxHp + 11 per potion + the death save; gold is 0.
- `P1`: global pilot prices in HP units. There are four weights: Fairy on top of its death save, every other potion,
  max HP per point, and gold per gold.
- `P4`: the same as P1, per act.
- `V0`: net-0420's critic.
- `H0`, `H1`, `H2` and `G`: the state-dependent heads of the interim training (`train_eval.py`).

For L, P1 and P4, the leaf differences are scaled per act with one factor in pp per HP, fitted on the HP pairs.

**Metrics.** Cross-fitting uses 5 folds by unit.

- **Cross-family skill** over the non-HP pairs, against zero and against C (a per act × family constant). The paired
  differences P1 − L, P4 − L, P4 − P1 and V0 − L get a unit-cluster bootstrap.
- **State dependence:** the within-cell slope b and the skill, as in `train_eval.py`.
- **Levels:** BCE and AUC.

**Choosing the gate candidate.**

- P1 is the candidate if P1 − L is above 0 with its whole 95% CI. It needs no code: `STS_SILVER_POTION_WEIGHTS`,
  `STS_SILVER_MAXHP_WEIGHT` and `STS_SILVER_GOLD_WEIGHT`.
- P4 replaces it only if P4 − P1 is above 0 with its whole CI and the per-act weights are stable across the folds.
  P4 needs code for per-act weights.
- A state-dependent model (V0 or H*) is a candidate only if it beats P1 or P4 in the skill against C with its CI above
  0.

**The gate.** A whole-run SPRT against the defaults on new seeds, with its own PREREG, review and Philipp's typed go.
