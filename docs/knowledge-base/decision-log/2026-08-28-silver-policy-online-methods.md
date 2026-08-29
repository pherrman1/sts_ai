# Silver 25k parent-Q online policy methods rejected

Date: 2026-08-28

## Decision

The preregistered offline action scorer remains
`POLICY_MODEL_OFFLINE_REJECTED`. The user explicitly authorized one exploratory
online override because top-action agreement improved offline. That override
does not revise the offline verdict.

The final, corrected 32-seed 2x2 comparison is
`ONLINE_POLICY_METHODS_REJECTED`. No learned mechanism is promoted, all new
runtime flags are removed, and ordinary Silver ordering and UCT remain the
only maintained runtime path.

## Evidence

The four final arms used frozen SHA
`a805d1404e10cc6eaa4fc2d4268f450937b25f0e`, the same fair seeds
`975000..975031`, Release on designated `sts-test`, one thread, ordinary
Silver, 1,000 base simulations, and allocated reuse cap. A/B/C/D were current
ordering plus UCT, learned ordering plus UCT, current ordering plus rank PUCT,
and learned ordering plus rank PUCT.

- A: 20/32 wins, mean floor 47.750, 4.932 CPU seconds/run.
- B: 20/32 wins, mean floor 46.594, 1.491x A CPU.
- C: 17/32 wins, mean floor 45.500, 1.388x A CPU.
- D: 15/32 wins, mean floor 44.750, 1.372x A CPU.

No learned arm gained the required three wins; every learned arm exceeded the
1.25x runtime limit. C and D also regressed gameplay. Complete paired
contrasts, confidence intervals, per-seed results, hashes, and provenance are
in `docs/experiments/evidence/silver_policy_online_methods_2026-08-28.json`.

Attempts 1 and 2 are correctness history, not scientific evidence. Attempt 1
failed on an internal private selection. Attempt 2 completed A/B only and then
C failed at seed 975024 because semantic identity was ambiguous. The final
attempt-3 exact-action repair passed the former B seed-975000 and C seed-975024
crash canaries and completed all 128 registered runs. Only the complete final
attempt supports the verdict.

## Telemetry limitation

`STS_SILVER_TELEMETRY=1` was absent from the final cohort. Total simulations,
policy inference calls and microseconds, scored decision nodes, legal-action
counts, PUCT selections, and aggregate failure counters were not captured.
They are unavailable (`null`) in durable evidence, never numeric zero. Startup
banners, focused mechanism fixtures, native parity, both canaries, and 32
completed rows per arm establish the executed configuration and absence of a
fatal cohort failure, but cannot reconstruct the missing counters.

## Cleanup

PR #79 retains the reusable stored-parent restoration, canonical feature
generation, grouped leakage-safe training, and independent 25k-B evaluation
pipeline. The rejected runtime learned-ordering/PUCT callbacks, model loading,
selection fields, telemetry, BestBench metadata, native predictor/parity and
online analyzer/test, and active compact model are removed. This is scope
reduction after rejection, not a new experiment or a reinterpretation.

## Consequences

- Default Silver has no learned ordering or learned PUCT path.
- The rejected compact model is not shipped in the active `models/` directory.
- The offline pipeline remains reusable for future offline questions.
- Any future online policy hypothesis requires a new design and independent
  authorization; it must not treat either partial attempt as evidence.
