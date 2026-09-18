# Silver root ordering ablation preregistration

Status: preregistered before running the A/B/G/H replay.

## Question

The pooled 32-source-seed six-arm screen found that Teacher-A full root
ordering improves ordinary UCT (`B-A` mean regret `-0.678663`, source-seed
bootstrap 95% CI `[-1.467371,-0.127664]`, B-best delta `+7.8125` pp with CI
`[+0.78125,+14.84375]` pp, exact paired sign test `p=0.0490`), while the
preregistered `C-A` prior gate failed. This ablation asks how much of the
ordering effect is available from only the Teacher-A best or top-two actions.

## Frozen protocol

- Reuse the same 64 frozen roots (`1..16` and `17..32`, two roots per seed),
  the same frozen 10k-A / 25k-B teacher labels, the same four deterministic
  common replicates, and exactly 32 simulations per replay.
- Use ordinary UCT only. Do not use PUCT, priors, learned models, action
  pruning, tree reuse, or parameter tuning.
- Preserve the current evaluator, rollout, chance handling, DPW, RNG contract,
  and root-only order intervention.
- Arms:
  - `A`: native root order;
  - `B`: stable Teacher-A corrected-Q descending full order;
  - `G`: Teacher-A best action first, then the remaining actions in native order;
  - `H`: Teacher-A top two actions first, then the remaining actions in native order.
- Primary contrasts are `G-A`, `H-A`, and `G-B`. `H-A` and `H-B` are secondary
  diagnostics. B-best probability, improved/worsened/tied counts, harmful
  tails, and within-root replicate dispersion are secondary reports.
- Reduction is four replicates within root, then source-seed means over two
  roots. Bootstrap and exact paired sign tests use the 32 source seeds. A clear
  benefit requires the source-seed bootstrap 95% CI entirely below zero and an
  exact two-sided paired sign test `p<0.05`; ties are excluded.
- Reuse the frozen implementation and artifact SHAs recorded in the pooled
  confirmation, but the new replay executable SHA is a separate tooling SHA.

## Decision

- If `G-A` passes, the narrow learned target is the best-action decision.
- If `G-A` fails but `H-A` passes, the target is a small top-two ranker.
- If neither passes but `B-A` remains strong, a listwise or pairwise ranking
  target is justified.
- No model training, gameplay qualification, runtime integration, or default
  promotion is authorized by this preregistration.

**Knowledge impact:** preregistered research follow-up; no implementation or
default change.
