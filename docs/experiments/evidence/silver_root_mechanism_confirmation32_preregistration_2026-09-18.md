# Silver root mechanism: 32-source-seed confirmation preregistration

Status: preregistered before collecting or examining seeds `17..32`.

## Question and frozen implementation

The primary question is whether the informative Teacher-A PUCT arm `C` beats
ordinary UCT arm `A` across independent Silver gameplay source seeds. The
implementation remains frozen at
`06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`, with baseline
`be5b6ac2c9914b0a56244f2522b7573f81360067` and Silver upstream SHA
`84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.

The existing confirmation population is seeds `1..16`, two roots per seed.
This extension adds only fresh seeds `17..32`, two roots per seed, and pools the
two identically generated populations to obtain 32 independent source-seed
units and 64 roots. No additional roots are added to seeds `1..16`.

## Frozen protocol

- Capture source seeds `17..32` only; do not inspect their roots before this
  preregistration is committed.
- Select exactly two eligible roots per seed by the lowest two
  `SHA256(UTF8(root_id))` values, breaking hash ties by `root_id`.
- Use the same frozen 10,000-simulation Teacher-A and independent
  25,000-simulation Teacher-B labels.
- Use the same six arms `A/B/E/F/C/D`, four deterministic common replicates,
  and exactly 32 simulations per root/arm/replicate.
- Preserve native-versus-Teacher-A-Q ordering, uniform-versus-Teacher-A visit
  priors, root-only PUCT, unvisited-first handling, ordinary internal UCT,
  current evaluator/rollout/chance/DPW/RNG behavior, and no tree reuse.
- Reduce four replicates within root, two roots within source seed, then pool
  source-seed means across seeds `1..32`. Replicates and roots are not treated
  as independent bootstrap units.
- The sign-test unit is the source-seed mean `C-A` B-regret delta: each unit
  first averages its two root means, with each root mean averaging its four
  replay replicates. A beneficial sign is `C-A < 0`; exact ties `C-A == 0`
  are excluded from the binomial count. Use an exact two-sided paired sign
  test with threshold `p < 0.05`.
- Use 10,000 paired source-seed bootstrap resamples with the same source-seed
  unit.

## Decision rule

Primary: `C-A` mean selected-action B-regret. Lower is better. The primary
effect is considered clear only when the paired source-seed bootstrap 95% CI
for `C-A` is entirely below zero and the exact two-sided sign test defined
above is below 0.05.
Before any training authorization, review B-best probability for non-worsening
and inspect the largest adverse source-seed/root tail. No single tail may be
ignored because the primary interval excludes zero.

- If `C-A` clearly improves, with the required B-best and tail review passed,
  return the evidence for scientific review of a compact nonlinear prior; do
  not train automatically in the capture/analyze job.
- If `C-A` is approximately neutral or its interval includes zero, classify the
  learned-PUCT line as not established and do not train.
- If `C-A` is worse, reject the learned-PUCT line and do not train.

Secondary reports: `C-E` informative-prior recovery, `E-A` uniform-PUCT harm,
`B-A` ordering, B-best probability, improved/worsened/tied source-seed counts,
and within-root replicate dispersion. The previous 16-seed result remains
`ROOT_GUIDANCE_INCONCLUSIVE` until this fresh-seed extension is analyzed.

## Explicit non-goals

No new model, policy training, parameter tuning, gameplay qualification,
runtime integration, default change, or source seed outside `17..32` is
authorized. The run must stop after evidence generation and source-seed-level
analysis for independent review.

**Knowledge impact:** preregistered research follow-up; no implementation or
default change. The subsequent run manifest must record this
preregistration commit SHA before any seed `17..32` data are generated.
