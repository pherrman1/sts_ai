# 2026-08-05 — Phase 2 (observation-keyed search + belief fix): identity expansion neutral + kept; obs-keyed descent falsified

Date: 2026-08-05
Session/task: Execute the plan's Phase 2 (P0 after T5): (1) expand
`CombatObservation` to fully determine the visible decision, (2)
`Edge{action → child[obsHash]}` observation-keyed children, (3) move belief
updates out of `step()` to the agent boundary. Gated vs the §113 honest
references (EXPERIMENTS.md §114).

## Decisions

1. **Observation identity expansion — kept (neutral).** `CombatObservation`
   now hashes and compares `inputState` + card-select context
   (`cardSelectTask`, `pickCount`, `canPickZero`, `canPickAnyNumber`, the
   three offer cards). Before this, a PLAYER_NORMAL state and a CARD_SELECT
   state — or two card-select screens with different tasks/offers — could
   share an identity, conflating distinct decisions. Measured neutral:
   256 seeds @1k vs the §113 honest reference = 37.5% vs 36.3%
   (+1.2pp; 36 vs 33 flips on 69 flipped seeds; within noise). Kept as a
   correctness fix at zero measured cost.
2. **Observation-keyed descent — falsified and reverted.** `descendKeyed`
   (child lookup/creation by (action, post-action obsHash)) made the tree
   grow linearly with simulations (100 sims → 300–600 nodes) because
   particle determinization diverges observations at almost every level; the
   fixed budget is starved and search depth collapses. Isolated local A/B
   (100 sims / 8 particles / 2 seeds): baseline floor 33.0, obs-expansion
   only 31.5, full keyed descent 11.0. GCP 64-seed @1k with the keyed
   descent: 0% win / floor 7.1. Reverted; the identity expansion alone is
   neutral.
3. **Belief fix — kept, gated.** The in-`step()` `belief.update` calls
   (expansion + internal branches) were removed; the belief is updated only
   at the agent boundary after a committed action in the non-fair S3 path,
   gated on `g_s3Belief`. The fair path already rebuilds the searcher/
   belief from the real state each decision. Inert in the recommended
   config (`STS_S3_BELIEF=0`).

## Rationale

- The identity gap was a documented open question (combat-search.md
  "Should `CombatObservation` identity include …"); expanding it is the
  plan's Phase-2 item 1 and costs nothing measured.
- The tree-explosion mechanism (linear node growth under particle
  determinization) is why the keyed descent cannot transfer at fixed
  budgets; this is the §62/§100-family lesson again — offline/structural
  gains do not transfer without gate confirmation.

## Alternatives considered

- Key children by a *subset* of the observation (decision context only)
  instead of the full hash — not run; the full-hash falsification already
  shows the divergence is pervasive, and a partial key reintroduces the
  conflation the expansion was meant to fix.
- Drop the observation expansion too (it changes the composite seed →
  different particle RNG) — rejected: measured neutral on 256 seeds, and
  the identity contract is now correct.

## Evidence

- EXPERIMENTS.md §114; CSVs `build/p2_obs_expand_1k_256.csv`,
  `build/p2_obs_expand_clean.csv` (GCP + local).
- Tests: `obs_identity` (decision-context cases), `seed_contract` (two full
  200-sim searches must match action/obsHash/visit counts), `cardselect_parity`,
  `belief`, `drawpile`, `prune`, `happy_flower` — all PASS, 3-run
  hash-identical.
- Code: `include/sim/search/CombatObservation.h`,
  `src/sim/search/CombatObservation.cpp` (identity fields),
  `src/sim/search/ScumSearchAgent2.cpp` (agent-boundary belief update),
  `apps/test.cpp` (test extensions).

## Status

- Phase 2 closed with this verdict; recommended stack and headline
  (42.6% @3k / 36.3% @1k, §113) unchanged. GCP tree re-synced to the final
  Phase-2 files. Committed with EXPERIMENTS.md §114.
