# Encounter marginalization

Last verified: 2026-08-11.

## Purpose / research question

Does encounter-marginalized supervision (resampling hidden encounters when
evaluating counterfactual OOC actions, producing one averaged label per action)
improve strategic decision quality over a fixed-world baseline?

## Current conclusion

**Encounter-marginalized labels (M1) show directional promise but are not
promoted.** The matched M0/M1 gate on 64 paired seeds showed M1 leading M0
by 3.1pp (10.9% vs 7.8%), but the confidence interval crosses zero and both
models are weaker than deployed V4.

The active research line is to **scale matched M0/M1 generation to 2,000-5,000
source seeds** while preserving the existing contracts, then compare the winner
with V4 only if the matched gate supports it.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-10 | [Encounter-marg final summary](../../encounter-marg-final-summary-2026-08-10.md) | Phase A-D complete: bugs fixed, M0/M1 trained, 64-seed gate |
| 2026-08-10 | [Phase A diagnostic](../../encounter-marg-final-summary-2026-08-10.md) | 57.9% best-action changes; 10.8% V4 reversals → PROMOTE to training |
| 2026-08-10 | [Phase D gate](../../encounter-marg-final-summary-2026-08-10.md) | M0 7.8% vs M1 10.9% (+3.1pp, CI crosses zero) |
| Latest | [current-research.md](../../evaluation/current-research.md) | Active line: scale M0/M1 to 2,000-5,000 seeds |

## Key implementation details

- **M0 (fixed-world):** one random encounter sample per decision; standard
  counterfactual evaluation.
- **M1 (marginalized):** multiple encounter resamples per decision, producing
  one averaged utility per action.
- Both use the frozen V4 gate stack for source trajectory generation
  (`stepFrozenV4Ooc`), H=4 horizon, with identical non-label columns.
- Trainer: `train_strategic_tok.py` with `STRAT_Q_TARGET=absolute`.

## Rejected / falsified approaches

None yet — this is the first matched M0/M1 experiment.

## Relationships

- [strategic-policy.md](strategic-policy.md) — M0/M1 are alternative label sources for the same V4 network architecture
- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — M0/M1 gate was run on a frozen S3+7k-VNet Act-3 stack

## Current implementation

`apps/one_combat.cpp::strategicMargGen` produces the M0/M1 CSV rows.
`tools/convert_marg_to_trainer.py` converts diagnostic CSVs to trainer format.

See [`docs/knowledge-base/evaluation/current-research.md`](../../evaluation/current-research.md)
for the active research routing and next-steps.

## Open questions

- Does scaled M0/M1 (2,000-5,000 seeds) produce a statistically significant gate?
- If so, does the winner become competitive with deployed V4?
- Is the encounter-marginalization benefit dominated by the V4 gate stack's
  Act-4 survival premium?
