# ADR-0033: Live OOC MCTS uses the calibrated A20 CTM at ascension 20 by default

Date: 2026-10-14
Status: accepted

## Context

The production CTM stack (pathb-r2, ADR-0027 era) was trained at ascension 0. At ascension 20 it underpredicts
boss deaths badly: death bias −0.147 on boss fights on the fresh §443 corpus. Ledger §457 measured live OOC MCTS
`combo` at A20 with the default CTM as WORSE than OOC MCTS off (−6.20 floors).

§443 trained an A20 CTM, `pathb-a20`, and added Lizard support. §458 measured it live in `combo` at A20 at +6.03 floors
[+2.69, +9.37] vs off. Offline, it failed only the boss death-bias bar (+0.0151 against ±0.01). §470 fit one boss
death-logit shift on Stage 1 VALIDATION rows. With that shift, the stack passes all five Stage 3a criteria on the fresh
Stage 4 corpus (boss bias −0.0041). §470 also added the opt-in switch `STS_OOC_MCTS_A20_CTM` (PR #534).

On 2026-10-14 Philipp chose to make it the default ("merge 534 and make it default.").

## Decision

- **Unset with the automatic stack:** when `STS_OOC_MCTS=1` runs with the automatic default CTM stack and
  `STS_OOC_MCTS_A20_CTM` is unset, OOC MCTS searches whose root is at ascension 20 use the bundled calibrated
  `pathb-a20` stack, active Lizard on. Searches below ascension 20 keep the default stack.
- **Unset with an override:** when `STS_OOC_MCTS_A20_CTM` is unset and any CTM override is present, the A20 stack
  stays off. The overrides are `STS_OOC_MCTS_COMBAT_MODEL`, `STS_OOC_MCTS_BREW_FALLBACK_MODEL`,
  `STS_OOC_MCTS_ACTIVE_LIZARD=0`, `STS_OOC_MCTS_COMBAT_RESOLVER`, `STS_CTM_RESEARCH_CANDIDATE_MANIFEST` and
  `STS_OOC_MCTS_LEAF_CAPTURE`. Explicit CTM research setups are unchanged.
- **Explicit values:**
  - `STS_OOC_MCTS_A20_CTM=0` restores the default stack at every ascension.
  - `STS_OOC_MCTS_A20_CTM=1` together with an override is fatal.
  - Any other value is fatal, even with `STS_OOC_MCTS=0`.
- **Unchanged:** OOC MCTS itself stays off by default (ADR-0027). The live advisor, `screen_leaf_s0` and the offline
  scorers keep their own CTM choice.

## Consequences

- Every `STS_OOC_MCTS=1` run at ascension 20 on the automatic stack plays differently from before. To reproduce
  earlier A20 OOC MCTS results (§457 `combo_def` and anything since), set `STS_OOC_MCTS_A20_CTM=0`.
- Runs below ascension 20 are play-identical. They load the A20 stack at startup, which costs about 4 MB and a short
  load, and log a `[ctm-a20-stack]` line.
- **Unverified:** a live gain of the calibrated stack. §458 used the uncalibrated candidate. No live A/B of the
  calibrated stack has run (seeds 99500000+ are reserved for one).

## Evidence

- Ledger §443 (continued), with evidence `docs/experiments/evidence/ctm_a20_regate_443_20261014/`.
- Ledger §458, with evidence `docs/experiments/evidence/ooc_a20_lizard_458_20261013/`.
- Ledger §470, with evidence `docs/experiments/evidence/ctm_a20_boss_calib_470_20261014/`.
- Code: `configureLiveOocMcts` and `liveSamplerFor` in `apps/one_combat/ooc_mcts_adapter.cpp`, and
  `kA20CandidateManifest` in `apps/one_combat/combat_transition_runtime.cpp`.
