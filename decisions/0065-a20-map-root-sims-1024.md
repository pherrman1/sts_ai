# ADR-0065: At A20, every searched map root stops at 1,024 OOC MCTS simulations

Date: 2026-11-01
Status: accepted

Changes the budget of [ADR-0061](0061-ooc-map-only-search-a20.md)'s A20 map-only full-budget roots.

## Context

Under ADR-0061, every searched A20 map root ran the whole `STS_OOC_MCTS_SIMS` budget (4,096 in the A20 configs) with
no early stops, and map search took about 75% of a production game's CPU (§739). The map-root value-of-computation
audit (§737) found that a 1,024-simulation pick differs from the 4,096 pick at 3.7% of map roots (0.58 per game). The
pre-registered non-inferiority SPRT (§741: d0 −1.5 pp, d1 0, α = β = 0.05, §727's 1,536 production games reused as
the control) crossed H1 at 1,024 pairs, giving **NOT_WORSE**. Heart kills went from 25.07% to 25.72%
(+0.65 pp [−0.98, +2.34]), map simulations dropped 75% and wall per diverging game about 42%. In the secondaries the
final floor fell 0.64 [−1.10, −0.17] and act-1 deaths rose 1.2 pp [+0.2, +2.1].

Philipp decided on 2026-11-01 (12:35Z): "Ja mach 1024 das neue A20 default".

## Decision

- With `STS_OOC_MCTS_FULL_ROOT_SIMS` unset, an ADR-0061 map root (A20, heart1 prior, outside the live advisor,
  `STS_OOC_MCTS_SCREENS` unset, `STS_OOC_MCTS_FULL_BUDGET_FRACTION` set) searches at most 1,024 simulations
  (`min(STS_OOC_MCTS_SIMS, 1024)`). This is exactly §741's arm B (`STS_OOC_MCTS_FULL_ROOT_SIMS=1024` on those roots).
- `STS_OOC_MCTS_FULL_ROOT_SIMS=0` restores the whole budget (4,096) at those roots. An explicit `N > 0` keeps its
  old meaning: every full-budget root searches exactly N.
- Below A20, with `STS_OOC_MCTS_SCREENS` set, without the fraction, in the live advisor, in offline scoring and for
  imagined decisions, nothing changes.
- The startup banner prints `map_root_sims_a20_default=1024`. The OOC provenance JSON records
  `"mapRootSimsA20Default":1024`. Policy rows carry the real budget in `budget` / `requestedSimulations`.

## Consequences

- Play changes at A20 map roots where the 1,024 tree's most-visited child differs from the 4,096 one (§727: 652 of
  1,536 games, 0.58 roots per game). Map-search CPU drops by about 75%, and a production game by roughly 40%
  (indicative).
- The learned OOC stop and the gap stop do not act at full-budget roots (unchanged), so nothing interacts with the
  cap. Fast roots (only reachable with `STS_OOC_MCTS_SCREENS` set) keep the fast-root cap.
- AZ policy targets at A20 map roots now come from 1,024-simulation trees.
- Comparability: runs from before this ADR at A20 are reproduced with `STS_OOC_MCTS_FULL_ROOT_SIMS=0`. Freeze files
  must record the flag.
- Open: the act-1 death secondary. A later gate may test a larger budget only in act 1.
