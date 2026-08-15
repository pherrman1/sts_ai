# Encounter marginalization

Last verified: 2026-08-15.

## Purpose / research question

Does encounter-marginalized supervision (resampling hidden encounters when
evaluating counterfactual OOC actions, producing one averaged label per action)
improve strategic decision quality over a fixed-world baseline?

## Current conclusion

**Encounter-marginalized labels (M1) do not separate from matched fixed-world
M0 at 2,000 source seeds — null result.** The preregistered 64-seed paired
gameplay gate (seeds 900000–900063, frozen S3 + 7k-VNet Act-3 stack, all
strategic screens ON, margin 1.0) showed M1 16/64 (25.0%) vs M0 17/64 (26.6%),
paired Δ (M1−M0) = **−1.6pp** with 95% CI [−14.1, +10.9]pp (crosses zero).
Offline best-CE: M0 0.50897 vs M1 0.51181.

Per the preregistered decision rule this is a **null / approximately-equal**
result: it does not support promotion or immediate scaling to 5,000 seeds. A
corrective same-seed/same-config Act-3 calibration (ledger-06 §169) placed
deployed V4 at 37.5% vs M0 26.6% / M1 25.0% (V4−M1 +12.5pp CI [+3.1,+23.4];
V4−M0 +10.9pp CI [−1.6,+23.4]), so the Phase-12 models remain below V4 but by a
smaller same-block margin — the historical 48.4% V4 figure was a different
Act-3-only seed block. A separate bottleneck (H4) remains plausible; do not
infer that fixed-world leakage is beneficial.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-10 | [Encounter-marg final summary](../../encounter-marg-final-summary-2026-08-10.md) | Phase A-D complete: bugs fixed, M0/M1 trained, 64-seed gate |
| 2026-08-10 | [Phase A diagnostic](../../encounter-marg-final-summary-2026-08-10.md) | 57.9% best-action changes; 10.8% V4 reversals → PROMOTE to training |
| 2026-08-10 | [Phase D gate](../../encounter-marg-final-summary-2026-08-10.md) | 500-seed pilot: M0 7.8% vs M1 10.9% (+3.1pp, CI crosses zero) |
| 2026-08-15 | [ledger-06 §168](../../../experiments/ledger-06.md) | 2,000-seed: M0 26.6% vs M1 25.0% (−1.6pp, CI crosses zero) → NULL |
| 2026-08-15 | [ledger-06 §169](../../../experiments/ledger-06.md) | Corrective Act-3 gate (same result) + V4 calibration 37.5% (V4−M1 +12.5pp) |

## Key implementation details

- **M0 (fixed-world):** one random encounter sample per decision; standard
  counterfactual evaluation.
- **M1 (marginalized):** multiple encounter resamples per decision, producing
  one averaged utility per action.
- Both use the frozen V4 gate stack for source trajectory generation
  (`stepFrozenV4Ooc`), H=4 horizon, with identical non-label columns.
- Trainer: `train_strategic_tok.py` with `STRAT_Q_TARGET=absolute`.

## Rejected / falsified approaches

- **Matched M0 vs M1 at 2,000 source seeds (2026-08-15): NULL.** The preregistered
  64-seed paired gameplay gate showed M1 (25.0%) not separating from M0 (26.6%),
  paired Δ −1.6pp (95% CI crosses zero). The scaled marginalization formulation
  did not improve the deployed-policy objective over the fixed-world control.

## Relationships

- [strategic-policy.md](strategic-policy.md) — M0/M1 are alternative label sources for the same V4 network architecture
- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — M0/M1 gate was run on a frozen S3+7k-VNet Act-3 stack

## Current implementation

`apps/one_combat.cpp::strategicMargGen` produces the M0/M1 CSV rows.
`tools/convert_marg_to_trainer.py` converts diagnostic CSVs to trainer format.
`tools/reconstruct_marg_csv.py` deterministically reconstructs the malformed
legacy raw CSV (unquoted richState) into the 40-column schema.

See [`docs/knowledge-base/evaluation/current-research.md`](../../evaluation/current-research.md)
for the active research routing and next-steps.

## Open questions

- Does a different M1 formulation (or the fixed-world leakage itself) explain
  why scaling to 2,000 source seeds did not separate M1 from M0?
- Is another bottleneck (controller distribution, feature schema, model capacity,
  optimization; H4) the binding constraint given both arms remain far below
  deployed V4?
- Should any further 5,000-seed scaling be pursued, given the null 2,000-seed gate?
