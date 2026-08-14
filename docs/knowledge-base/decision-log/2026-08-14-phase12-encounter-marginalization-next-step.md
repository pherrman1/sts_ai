# 2026-08-14 — Phase 12 encounter marginalization next step

Date: 2026-08-14
Session/task: Persist the Phase 12 research decision before execution

Baseline: `ec05a08b63404d15f083e7bed3d1009cfaf9606a`

## Decision

Run the staged matched encounter-marginalization experiment: generate and
train fixed-world M0 and encounter-marginalized M1 models from **2,000 source
seeds**, with `H=4`, preserving the corrected matched M0/M1 generation,
training, split, and export pipeline. Compare M0 with M1 first. Do not include
a V4 gameplay arm initially. Limit paired gameplay evaluation to **64 seeds**.

Do not immediately scale to 5,000 source seeds. Treat that as a future
research decision based on the 2,000-seed result. No result from this staged
experiment has been observed yet; this is a preregistered decision.

## Current evidence

The corrected 500-source-seed M0/M1 pilot found:

- encounter marginalization changed the diagnostic best action on 191/330
  decisions (57.9%);
- offline `q_top1` favored M1: 0.310 versus 0.260;
- online matched 64-seed pilot: M0 5/64 (7.8%), M1 7/64 (10.9%), delta
  +3.1pp, 95% CI [−4.7,+10.9]pp;
- both models were dramatically weaker than deployed V4 because the training
  set contained only about 12K rows from 500 source seeds.

The pilot is therefore suggestive but is not a promotion result.

## Alternatives considered

- Confirm 128 Searcher3 particles — deferred because the encounter-
  marginalization pipeline already has corrected, validated execution and the
  staged comparison has higher immediate information value.
- Confirm real-observation belief filtering — deferred for the same prioritization
  reason; its diagnostic evidence remains recorded separately.
- Test the current stack at 3,000 simulations — deferred; it does not directly
  resolve the M0/M1 target question.
- Continue structural refactoring — deferred; no production refactor is part
  of this research decision.
- Scale matched M0/M1 to 5,000 source seeds — deferred until the 2,000-seed
  result establishes whether further scale is informative.

## Hypotheses

- **H1:** Fixed-world M0 targets leak unknowable future-encounter information;
  marginalized M1 should outperform M0 when data noise is reduced.
- **H2:** The pilot +3.1pp was sampling noise; scaled M0 approximately equals
  M1.
- **H3:** Data quantity dominated; both models improve substantially, but M1
  does not separate from M0.
- **H4:** Another bottleneck (controller distribution, features, model
  capacity, optimization, or similar) dominates; both models remain weak
  despite scaling.

## Decision rule

- Positive M1 delta with a paired 95% CI excluding zero: strong support for
  marginalization.
- Meaningfully positive point estimate with a CI crossing zero: suggestive /
  inconclusive; no promotion.
- Approximately equal: null; do not automatically scale further.
- M1 materially worse: negative; close this formulation unless a concrete
  defect is found.
- If both remain very weak, flag H4 separately; do not assume more data is
  automatically the solution.

## Methodology and safeguards

- The only conceptual treatment variable is fixed-world versus
  encounter-marginalized target generation.
- Implementation success is separate from scientific success.
- Current code, tests, and raw evidence override this note if a later review
  finds an inconsistency.

## Evidence

- `docs/knowledge-base/evaluation/current-research.md` — current research
  routing and pilot summary.
- `docs/knowledge-base/encounter-marg-final-summary-2026-08-10.md` — corrected
  pilot report.
- `docs/experiments/ledger-06.md` — chronological experiment evidence.
- `apps/one_combat.cpp::strategicMargGen` — generation implementation.
- `tools/convert_marg_to_trainer.py` — corrected conversion pipeline.

## Status and follow-up

- Preregistered decision; experiment not yet run.
- The 2,000-seed result determines whether any later 5,000-seed scaling is
  justified.