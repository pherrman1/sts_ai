# Risk-veto probe on §711 expert states: dropped after the smoke (2026-11-08)

**Status:** not run. Philipp dropped the probe on 2026-11-08 00:29 CET after this smoke.

## Plan that was approved

Stage R of the combat-transformer plan: replay §711's 329 Baalorlord expert units with `expertfights`, adding arms
`veto5` and `veto10` (`STS_SILVER_RISK_VETO` delta 0.05 / 0.10, share 0.25, min samples 32, #1005) on act 1-3 elite
and boss rooms, 2 copies each, on 40 workers. Philipp's typed go: 2026-11-08 00:07 CET.

## Smoke

Two units (1675881103, 1648247344) on an arm build (branch commit 8a63785b, not merged: `veto<P>` arm token, a
thread-local veto override and a `riskVetoes` counter in the per-combat stats; binary 22ee0a36…). Both units rc 0.

- `riskVetoes` = 0 over 2,279 Silver decisions in the veto arms; the arm outcomes equal production exactly.
- A debug print (not committed) of the per-root-edge playout outcomes at delta 0.05 covered 674 roots. Eligible gap =
  death rate of the most-visited edge minus that of an edge with ≥ 25% of its visits, both with ≥ 32 resolved
  playouts. Largest gap 0.038. Roots with gap ≥ 0.005 / 0.01 / 0.02 / 0.03 / 0.05: 18 / 13 / 4 / 3 / 0.
- Unit 1675881103: 171 roots, 83 with any playout death, max gap 0.0087. Unit 1648247344: 504 roots, 406 with any
  death, max gap 0.038.

## Interpretation (inference)

With an expert deck the rollout leaf rarely dies, and the edges Silver weighs die at nearly the same rate. The veto
at 0.05 / 0.10 cannot fire, and at 0.01 it would touch about 2% of roots, too few to move a winrate that the run
could measure. The flag was motivated by the starter-deck fixture (Nob, A20, 60 HP: 47% of playouts die), which is not
representative of these states.

## Decision

Probe dropped, no compute spent beyond the smoke (~1 core-h). `STS_SILVER_RISK_VETO` stays a default-off research
flag. A risk-aware choice should wait for a learned value with real risk estimates (plan stages 1-3). No seeds used
(the probe replays §711's runs).
