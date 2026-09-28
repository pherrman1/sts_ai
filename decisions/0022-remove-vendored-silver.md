# ADR-0022: Remove the vendored Silver model; native Silver only

Date: 2026-09-25
Status: accepted

Supersedes: [ADR-0015](0015-live-silver-equivalent-copy-reroot.md) (equivalent
physical-copy reroot). Amends [ADR-0021](0021-native-silver-default.md), whose
vendored opt-out and fallback are removed.

The launcher-specific GCP manifest guidance below is historical; ADR-0024
retires that launcher. The native backend and telemetry contract remains.

## Context

ADR-0021 made the Silver search ported onto the main engine the default and
kept the vendored copy of the Silver fork (`third_party/silver_lightspeed`,
compiled under a private namespace and reached through a wire-protocol bridge)
for `STS_NATIVE_SILVER=0`, for vendored-only research options, and for the live
advisor. The advisor now runs the native searcher (PR #324). What remained on
the vendored model were research tools and frozen research contracts (teacher
dataset generators, live OOC MCTS, semantic pilot, k-budget evaluation, GCP
manifests) that pinned "vendored Silver, exact 10k, telemetry on".

## Decision

- Delete the vendored model, its bridge (`SilverLiveBackend`,
  `SilverStateBridge`, `SilverSearcherBridge`), the learned root prior
  (`SilverPriorNetV1`), and every research app, tool and test that needed
  them.
- `one_combat` installs only the native backend. `STS_NATIVE_SILVER=0` and any
  `STS_SILVER_*` option the native backend does not honor exit with an error.
  Frozen environments may still pin the neutral values
  `STS_SILVER_REUSE_CAP_MODE=allocated`, `STS_SILVER_VNET_LEAF_DIRECT=0` and
  `STS_SILVER_TELEMETRY=0`.
- The native backend honors `STS_SILVER_EXACT_ROOT_BUDGETS=1` (flat budget
  without the boss multiplier), so "exact 10k" research contracts run on it.
- Frozen research contracts move to native Silver: teachers declare
  `combat_backend: native_silver`, no longer require `STS_SILVER_TELEMETRY=1`,
  and a `silver_uct` (vendored) teacher is rejected with a message naming this
  ADR. GCP manifests must set `expect_silver_telemetry: false`. Run-level
  checks read `nativeSilverExactRootBudgets`, `nativeSilverAdaptiveEnabled` and
  `nativeSilverReuseCap`; OOC continuation cost counts native combat decisions
  (`g_nativeSilverCombatStats`), and selection transactions no longer occur.
- Bestbench metadata keeps its keys with native values
  (`effectiveCombatBackend="native_silver"`, reuse-cap mode `allocated`, no
  upstream SHA). The benchmark canary accepts only `native_silver` and proves
  activation by the startup banner.

## Rationale

The native search matched the vendored model on the 128-seed gate (§348) and
runs Silver on the rules the agent plays by. Keeping a second simulator only
for research tooling doubles the rule set that must be kept correct. The user
chose to move the frozen research contracts to native Silver rather than keep
the vendored model for them.

## Alternatives considered

- Keep the vendored model only for the frozen research contracts. Rejected by
  the user: it keeps the second rule set alive indefinitely.
- Retire the OOC research modes and dataset generators with the model.
  Rejected: they are still useful on native Silver.

## Consequences

- Datasets and results produced with the vendored teacher stay valid as
  recorded history but cannot be regenerated bit-identically; their manifests
  are rejected by the current validators. New teachers must be frozen on
  native Silver.
- Playing a different physical copy of an equivalent card starts a fresh
  search root in the advisor (ADR-0015's equivalent-copy reroot is not
  carried over); only inherited visits are lost.
- The advisor's search root cannot represent queued continuations other than
  an interrupted card's `OnAfterCardUsed`.
- Historical analysis scripts that validate old vendored evidence (for
  example `analyze_deepset_entropic_brew_hybrid_confirmation.py`) keep their
  vendored expectations and cannot be re-run end to end.

## Affected files

- Removed: `third_party/silver_lightspeed/`, `include/silver/`,
  `include/sim/search/{SilverLiveBackend,SilverPriorNet,SilverHardCombat,SilverRootMechanism}.h`,
  `src/sim/search/SilverPriorNet.cpp`, `apps/silver_*.cpp`, the Silver research
  tools under `tools/` and their tests.
- `apps/one_combat.cpp`, `apps/one_combat/{combat_datasets,run_driver,semantic_pilot,ooc_factor_eval,ooc_mcts_adapter}.cpp`
- `src/sim/search/NativeSilverBackend.cpp`, `include/sim/search/SilverBridge.h`
- `tools/ooc_pipeline_contract.py`, `tools/ooc_semantic_pipeline_contract.py`,
  `tools/combat_evaluator_contract.py`, `tools/battle_start_runout_contract.py`,
  `tools/freeze_ooc_k_budget_experiment.py`, `tools/agent/gcp_benchmark.py`,
  `tools/agent/check_benchmark_canary.py`, `tools/seed_guard.sh`
- `apps/live_silver_importer_test.cpp`, `apps/runic_dome_lifecycle_test.cpp`

## Evidence

- Ledger §348: native 86/128 vs vendored 83/128 on seeds 126700–126827.
- PR #324: the advisor runs native Silver; `test silver_wire_state` checks the
  wire path against the native backend's own roots.
- Local checks for this change: build without the vendored model, the ported
  importer and Runic Dome lifecycle tests, the contract and canary self-tests,
  and native `one_combat` output unchanged from before the deletion.
