# Issues

Last verified: 2026-08-02 against the current working tree.

This directory collects known issues extracted from the knowledge-base pages,
sorted by importance. Each entry records the symptom, evidence, why it matters,
and a candidate fix direction; nothing here is a decision or a completed
diagnosis. Entries are closed by a fixing commit or test, not by editing
history.

## Importance tiers

- **Critical** — silently invalidates measurements, results, or model behavior.
- **High** — blocks operation, progress, or an experiment's validity.
- **Medium** — tooling or evidence gaps that waste effort or mislead readers.
- **Low** — debt and design questions without an immediate functional impact.

## Index

Sorted by importance; entry files are reverse-chronological in their own list.

| ID | Tier | Title | Status | Source pages |
| --- | --- | --- | --- | --- |
| [01](2026-08-02-issue-01-meta-arm-bypass.md) | Critical | Self-play meta arm bypasses its candidate models | closed | [selfplay-loop](../operations/selfplay-loop.md) |
| [02](2026-08-02-issue-02-no-current-benchmark.md) | Critical | No fresh benchmark on the current checkout | closed | [current-baselines](../evaluation/current-baselines.md) |
| [03](2026-08-02-issue-03-searcher3-composite-seeding.md) | Critical | Searcher3 composite seeding uses unassigned values | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [04](2026-08-02-issue-04-belief-conditioning-noop.md) | Critical | Searcher3 belief conditioning is a no-op | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [05](2026-08-02-issue-05-drawpile-order-ignored.md) | Critical | `HiddenBattleState::drawPileOrder` is never applied | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [06](2026-08-02-issue-06-pvnet-only-priors-zero.md) | Critical | PVNet-only multi-edge priors are zero | closed | [combat-search](../architecture/combat-search.md), [current-baselines](../evaluation/current-baselines.md) |
| [07](2026-08-02-issue-07-observation-identity-mismatch.md) | Critical | `CombatObservation` equality and hash disagree | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [08](2026-08-02-issue-08-ooc-checkpoint-truncated-load.md) | Critical | `OocCheckpointNet::load` reports success on truncated payloads | closed | [out-of-combat](../architecture/out-of-combat.md), [invariants](../behavior/invariants.md) |
| [09](2026-08-02-issue-09-paired-analysis-column-drift.md) | Critical | `paired_analysis.py` reads the wrong HP/time columns | closed | [benchmark-protocol](../evaluation/benchmark-protocol.md), [invariants](../behavior/invariants.md) |
| [10](2026-08-02-issue-10-fair-replay-nondeterminism.md) | Critical | Fair multi-thread replay is not bit-identical; no test | open | [determinism-and-rng](../behavior/determinism-and-rng.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [11](2026-08-02-issue-11-selfplay-snapshot-nonrunnable.md) | High | Checked-in self-play snapshot cannot run | closed | [selfplay-loop](../operations/selfplay-loop.md) |
| [12](2026-08-02-issue-12-clean-clone-configure-fails.md) | High | Clean clone cannot configure (json/pybind11 absent) | closed | [build-and-debugging](../operations/build-and-debugging.md) |
| [13](2026-08-02-issue-13-baseline-cache-provenance.md) | High | Baseline cache key omits fixed native trees | closed | [selfplay-loop](../operations/selfplay-loop.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [14](2026-08-02-issue-14-value-margin-misapplied.md) | High | `VALUE_MARGIN=-0.5` applies to every value candidate | closed | [selfplay-loop](../operations/selfplay-loop.md), [invariants](../behavior/invariants.md) |
| [15](2026-08-02-issue-15-gate-multiplicity.md) | High | Repeated gate looks are not multiplicity-adjusted | closed | [selfplay-loop](../operations/selfplay-loop.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [16](2026-08-02-issue-16-pvnet-sweep-provenance.md) | High | PVNet sweep provenance is unverified | open | [current-baselines](../evaluation/current-baselines.md) |
| [17](2026-08-02-issue-17-guaranteed-death-pruning-unproven.md) | High | Aggressive guaranteed-death pruning is unproven | closed | [combat-search](../architecture/combat-search.md) |
| [18](2026-08-02-issue-18-bestbench-banner-stale.md) | Medium | `bestBench` banner/comment describe an older stack | closed | [out-of-combat](../architecture/out-of-combat.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [19](2026-08-02-issue-19-parity-test-invalid.md) | Medium | `parity_test.py` cannot run as written | closed | [build-and-debugging](../operations/build-and-debugging.md), [training-and-inference](../architecture/training-and-inference.md) |
| [20](2026-08-02-issue-20-runtrace-divergence.md) | Medium | `runtrace` is not a mirror of `runFullRunOOC` | closed | [out-of-combat](../architecture/out-of-combat.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [21](2026-08-02-issue-21-v-server-stale-comments.md) | Medium | `v_server.py` comments describe an old layout | closed | [out-of-combat](../architecture/out-of-combat.md), [training-and-inference](../architecture/training-and-inference.md) |
| [22](2026-08-02-issue-22-no-automated-invariant-tests.md) | Medium | No automated invariant/test suite exists | closed | [invariants](../behavior/invariants.md), [overview](../architecture/overview.md) |
| [23](2026-08-02-issue-23-fairgen-name-misleading.md) | Medium | `fairgen` does not enable the fair path itself | closed | [training-and-inference](../architecture/training-and-inference.md) |
| [24](2026-08-02-issue-24-isbattleover-trap.md) | Medium | `isBattleOver` is never set true | closed | [invariants](../behavior/invariants.md) |
| [25](2026-08-02-issue-25-blas-hardcoded-path.md) | Medium | Native inference probes a hard-coded OpenBLAS path | closed | [combat-search](../architecture/combat-search.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [26](2026-08-02-issue-26-one-combat-centralization.md) | Low | `one_combat.cpp` centralizes policy and experiments | open | [overview](../architecture/overview.md), [out-of-combat](../architecture/out-of-combat.md) |
| [27](2026-08-02-issue-27-python-deps-unpinned.md) | Low | No dependency lock for Python packages | open | [training-and-inference](../architecture/training-and-inference.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [28](2026-08-02-issue-28-expert-hand-authored-features.md) | Low | Policy input includes hand-authored Expert features | closed | [combat-search](../architecture/combat-search.md) |
| [29](2026-08-02-issue-29-python-combat-bindings.md) | Low | Python cannot issue card-by-card combat actions | open | [out-of-combat](../architecture/out-of-combat.md), [overview](../architecture/overview.md) |
| [30](2026-08-02-issue-30-selfplay-bootstrap-policy.md) | Low | Self-play bootstrap policy for stale `state.env` is undefined | closed | [selfplay-loop](../operations/selfplay-loop.md) |

## Conventions

- An entry's status changes to `closed` with a note of the fixing commit or
  test. Do not rewrite the entry's evidence.
- When a candidate investigation in
  [`investigations/`](../investigations/README.md) is promoted to a completed
  diagnosis, link it from the relevant issue entry.
- New issues found in the knowledge base are appended to the index and get a
  new entry file dated with the day they were recorded.
