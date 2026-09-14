# Corrected live OOC MCTS paired Silver regression benchmark

The user authorized four corrections after the original §243 negative gate:
resolve pending leaf contents before native win evaluation, cost unsupported
imagined combats, align both real-combat arms to the corpus ordinary exact-10k
Silver policy, and deepen deterministic transitions with a fixed 512-simulation
MCTS budget. See the maintained [OOC contract](../../knowledge-base/architecture/out-of-combat.md).
Knowledge impact: updated live continuation, combat-policy prerequisites and
search/coverage telemetry contracts; unchanged models, support envelope and
OFF default. This bundles four corrections and cannot attribute effects to one.

Hypothesis: the corrected opt-in OOC policy improves Act-3 wins over the existing
V4 OOC stack when both arms use ordinary exact-10k Silver. Control is MCTS OFF;
treatment is corrected MCTS ON at 512, PUCT 1.5, stochastic widening k=2 and
alpha=0.5, depth32. Both use the same frozen executable and model hashes,
A0, four OpenMP workers, keys OFF and Act-3 stop. Only detached imagination uses
the combat surrogate; unsupported imagined combat uses detached 10k Silver.
The original combat-transition artifact and tracked V4/floor/win/combat-policy
models remain frozen; no regeneration, training or support expansion.

Evidence inventory: preserved §243 raw paired32 outputs have the correct seeds
and artifacts but real combat 1k, MCTS128 and the old leaf/unsupported contracts.
They cannot answer this corrected configuration. The user explicitly requires
**the same seeds 970000..970031**, so this is a paired regression comparison,
not fresh confirmation. Excluded 969992..969999 are implementation smoke/parity
seeds. No additional decision-bearing seeds or sweep are authorized.

The decision rule remains the paired seed bootstrap 95% CI on treatment-minus-
control won: strictly positive → OOC_MCTS_WINRATE_UP; strictly negative → DOWN;
otherwise INCONCLUSIVE. Use 200,000 paired resamples, NumPy PCG64 seed20260914,
linear percentile quantiles. Discordant exact two-sided binomial p and secondary
floor/HP/fights/death/runtime metrics are descriptive. Support reasons must sum
to unsupported imagined combats; supported plus unsupported must equal all
imagined combats. Ownership/simulations, effective actual backend and real combat
counts must reconcile. Depth includes searched primitive edges, excluding leaf
projection policy steps. This remains an engineering policy A/B under copied
hidden native RNG; no unbiased stochastic-planning or deployment qualification.

Implementation baseline: `916a3d35ff33bd3992de38f1540049838cb55d80`.
Independent source review approved the corrections after repairing imagined
Silver's file-collector isolation. Focused checks pass3/3; qualified startup
checks pass11/11. Final benchmark SHA and raw results will be recorded below
only after prefreeze canary evidence and independent review pass.
