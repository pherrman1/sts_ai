# Silver policy/value Phase A diagnostic — 2026-09-16

This is an offline engineering diagnostic. It does not train a model, load a
new model, change gameplay, change Silver action selection, or redesign the
terminal utility.

## Binding and scope

- Baseline reviewed SHA: `77fec051c2453d79f05bad5e813989b861fa5d0a`
- Upstream Silver SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`
- Source worktree: fresh Codex-app-managed worktree, detached at the baseline
- Supported input: visible `PLAYER_NORMAL` combat state only
- Candidate contract: one shared state encoder, one scalar value, and all
  currently legal Silver sibling actions
- Canonical widths: 1,766 state features and 22 action features
- Utility: existing `BattleSearcher::evaluateEndState`, with the original
  root retained as teacher-only reference context and the existing gold/maxHP
  root-relative weights (`0.25`, `2.0`)

The converter redacts isolated-search seed, observed-generation, misc-bit
provenance, and latent pending intent data when `intentsHidden` is set. It
retains visible combat/player/enemy/power/status/hand/pile/card/potion/relic
fields in the visible wire. The canonical 1,766-feature projection is
explicitly marked lossy for draw order, some card-instance metadata,
per-monster detail, card-select/queue context, and full relic counters; these
are documented in every emitted example rather than silently treated as
represented.

## A1 — current Silver rollout cost

Guarded source run: `bestbench`, 8 seeds (`100..107`), Release binary, one CPU
thread, fair Silver, 100 simulations per decision, exact root budgets, and
reuse-cap mode `none`. Leaf corpus sampling was modulus 1 with at most 16
leaves per group. The run completed without telemetry conversion, semantic,
transaction, or knowledge failures.

The live telemetry produced 188 combat summaries:

| Metric | Result |
| --- | ---: |
| decisions / simulations / rollout calls | 3,388 / 340,600 / 321,411 |
| rollout calls per simulation | 0.9437 |
| search wall / rollout wall | 153.268 s / 80.545 s |
| rollout wall fraction | 52.5516% |
| call-weighted rollout mean | 250.598 µs |
| mean of per-combat rollout means | 238.950 µs |
| median of per-combat rollout means | 239.684 µs |
| median of per-combat p50 estimates | 231.853 µs |
| median of per-combat p90 estimates | 293.671 µs |
| median of per-combat p99 estimates | 351.290 µs |

The percentile rows are summaries of the per-combat percentile telemetry
emitted by the live backend; the raw sampled rollout rows contain the exact
action and turn counts. Across 140,639 sampled rollout observations (19,916
groups; all 8 seeds), rollout action count was mean/median/p90/p99
`13.633 / 11 / 28 / 45`, and rollout turn delta was
`2.446 / 2 / 5 / 9`. There were 5,016 hidden-intent rows in the source corpus;
the converter redacted them before feature extraction, and 2 of the 16
selected examples retained the `intentsHidden` marker after redaction.

## A2–A4 — contract and representative examples

`apps/silver_policy_value_phase_a.cpp` writes
`silver_policy_value_phase_a_v1` JSONL. The 16 selected examples all have
`input_state=PLAYER_NORMAL`, a teacher utility, exact Silver order, unique
semantic action fingerprints, and 1,766/22 state/action feature widths. The
legal-action counts are `[1, 1, 8, 5, 1, 7, 6, 5, 2, 6, 6, 2, 5, 3, 2, 3]`;
the emitted action objects include the full semantic card/potion/select/target
identity as well as the fingerprint and action features. The original root is
present only under `root_reference_context.teacher_only`.

## A5 — native synthetic CPU benchmark

Binary: `silver_policy_value_phase_a`, Release, `OMP_NUM_THREADS=1`. The timed
region is complete wire materialization, canonical state/action preparation,
one shared `1766 -> 64 -> 64` ReLU encoder, `64 -> 1` value head, and all legal
`[64,22] -> 32 -> 1` action scores. Fixed synthetic weights are deterministic;
there is no model file or training dependency.

| Metric | Result |
| --- | ---: |
| examples / iterations / calls | 16 / 200 / 3,200 |
| action scores | 12,600 |
| call mean / median / p90 / p99 | 120.947 / 120.916 / 126.727 / 142.990 µs |
| calls/s / action scores/s | 8,268.07 / 32,555.52 |
| legal actions mean / median / p90 / p99 | 3.9375 / 3 / 6 / 7 |

Compared with the call-weighted current rollout mean, the candidate mean is
`0.483x` (approximately 52% lower). On this machine and this bounded
representative corpus, the classification is **`PV_COST_FEASIBLE`**. This is
only a cost classification: no action-ranking quality, terminal-label quality,
hidden-state sufficiency, or gameplay benefit has been established.

## Verification and boundaries

- Release configure and target build passed for the new executable.
- The source corpus was produced through `tools/seed_guard.sh`; the local run
  stayed below the 128-seed ceiling.
- The diagnostic-off path remains default-off; no search policy, model loading,
  utility, RNG, or gameplay default was changed.
- Focused native tests passed: `silver_random_bridge`,
  `silver_semantic_action`, `silver_searcher_link_closure`, and
  `silver_bridge_boundary` (4/4). The authoritative GitHub Linux GCC check was
  not run locally and remains required for publication.
- Remaining uncertainty: the canonical projection is intentionally lossy,
  the sample is small and corpus-provided, and this does not qualify runtime
  inference or a gameplay gate.

Knowledge impact: current maintained policy/value contract and Phase-A
engineering evidence were added to the knowledge base and experiment ledger;
runtime defaults and research qualification remain unchanged.
