# ADR-TBD: Prior-argmax Silver playouts in real boss fights only

Date: 2026-10-21
Status: accepted

Supersedes the elite part of [ADR-0050](0050-silver-prior-playout-boss-elite.md).

## Context

ADR-0050 gave real boss and elite fights prior-argmax playouts (`RolloutConfig::prior`) because §541 showed most of
the point estimate in boss fights (+9.8 / +12.5 score). Elites were almost flat (priorpl2500 +0.11, priorpl10000
+2.89 score). The 2026-10-21 AZ-loop profile (`/mnt/project-files/az-speed-profile/REPORT.md`) measured prior playouts
as the main cost of real combat. Real combat now takes 17-40% of A20 run CPU, and elite decisions cost about 1.12 s
instead of about 0.15 s with greedy playouts. Elite fights are about 12% of run CPU, so dropping them saves about 10%
(about 6% on top of the real-combat learned stop). Philipp decided on 2026-10-21: "maybe we say that prior rollouts
only for bosses and not elites anymore" (09:3xZ), confirmed at 12:32Z ("prior rollouts only in bosses").

## Decision

- Real Silver fights in BOSS rooms keep prior playouts under ADR-0050's conditions: a root prior is set, the scope is
  not `override`, and there is no rollout, root-prior or prior-net override.
- ELITE rooms go back to greedy playouts. That includes burning elites and Act 4's Shield and Spear.
- `STS_SILVER_PRIOR_PLAYOUT_ELITE=1` restores ADR-0050's boss and elite rooms. `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`
  still turns prior playouts off everywhere.
- The Silver leaf specification records `"prior_playout_rooms": "boss"`, or `"boss,elite"` with `=1`.

## Consequences

- Every A20 run that sets a root prior plays elite fights differently from ADR-0050 runs. Comparisons with them need
  `STS_SILVER_PRIOR_PLAYOUT_ELITE=1`.
- Teacher and specification JSONs written under ADR-0050 record `"boss,elite"` and are refused by the `silver_leaf`
  equality check. They must be regenerated or matched with `STS_SILVER_PRIOR_PLAYOUT_ELITE=1`.
- Not gated. The strength effect of greedy elite playouts at run level is not measured, and §541's elite subset was
  not a pre-registered test.
