# 2026-08-27 — Silver leaf VNet transfer

Date: 2026-08-27
Session/task: Observe `models/v_combat_7k_tuned.txt` on isolated Silver rollout leaves and test the smallest direct evaluator transfer.

## Decision

Keep the direct Silver leaf VNet evaluator rejected and default-off. Retain the
observer, bounded CSV, and analysis tool as diagnostic infrastructure only.

## Rationale

The 8-seed corpus had positive but borderline sibling ranking: strict
concordance 0.5578, with lower Act-3 and long-rollout strata at 0.5449 and
0.5420. The direct 1000-simulation arm then reduced win rate from 25% to 0%,
reduced mean floor from 42.5 to 29.8, and increased mean per-run time from
37.48s to 195.95s. This fails the preregistered fixed-simulation criterion;
the equal-runtime follow-up was therefore not run.

## Alternatives considered

- Calibrated direct VNet deployment — rejected by the paired gameplay and
  throughput gate; no production default changes.
- Nonlinear calibration, shallow rollout hybrids, risk bins, or new training —
  rejected as outside this bounded transfer experiment.
- A second feature extractor or VNet implementation — rejected; the callback
  crosses the type-free `BattleStateWire` boundary and invokes the existing
  live `CombatValueNet::predict` path.

## Evidence

- `third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp::rolloutToEnd`
  and `include/sim/search/SilverBridge.h::SilverLeafObserver`.
- `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp` and
  `SilverStateBridge.cpp` implement the opt-in observer/direct bridge.
- `apps/silver_bridge_test.cpp`, `silver_bridge_boundary`, and
  `tools/analyze_silver_vnet_leaf.py --self-test` pass.
- Phase-1 raw CSV: `build/silver_vnet_phase1.csv`, 66,310 rows / 8 seeds,
  SHA-256 `7B7E6E55497D0B85FCD8159CCCE8489E5AA645DF4521C2963E32A29795D550A0`.
- Phase-1 analysis: `build/silver_vnet_phase1_analysis.txt`, SHA-256
  `B860C27567ADBD72B917231664B875A0C9AEDFFE6529280A74EB9E508AA902AC`.
- Fixed-simulation paired analysis: `build/silver_vnet_phase3_paired_analysis.txt`,
  8 paired seeds, SHA-256
  `A97E27A2DDE3065851AC7FC64FACF86390FF088E03B1C4DAE4A659DEBED70EA5`.
- Direct telemetry: `build/silver_vnet_phase3_B.log`; 5,461,485 rollouts
  skipped, 6,485,000 simulations, and zero conversion, semantic-resolution,
  transaction, or knowledge failures.

## Status and follow-up

Implemented, measured, and closed as `DIRECT_VNET_REJECTED`. The observer is
diagnostic-only; revisit only with a separately justified lower-cost inference
path and a new experiment, not by weakening this result.
