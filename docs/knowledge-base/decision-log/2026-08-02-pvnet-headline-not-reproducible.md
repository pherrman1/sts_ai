# 2026-08-02: PVNet 66.4% headline does not reproduce on the current checkout

## Decision

Re-checked the recorded Phase 4b PVNet alpha-sweep headline (66.4% at 100
sims, policy-only) on the current binary and the recorded 126700–126827 seed
block, with the closest reconstructable configuration (`STS_FAIR=1
STS_SEARCHER3=1 STS_PVNET=build/v_combat_pvnet.txt STS_PVNET_ALPHA=0`, tracked
PVNet hash verified, policy prior auto-loaded). Result: **8.6% win / 26.4
floor** at 100 sims vs 4.7%/29.5 for the same-budget default Searcher2; α=1.0
gave 5.5%. The sweep's 66.4% headline does not reproduce.

## Rationale

- **Inference:** the sweep never recorded its seed range, exact command, or
  OOC stack, and the KB already labelled it unresolved; a head-to-head on the
  one block that IS recorded was the cheapest falsification test. The
  α-ordering claim (α=0 better than pure neural leaf) survives; the magnitude
  claim does not.

## Evidence

- `build/pvnet_check_base100.csv`, `build/pvnet_check_s3p0.csv`,
  `build/pvnet_check_s3p1.csv`; EXPERIMENTS.md §72; current-baselines.md row
  and limitation updated.

## Status

Closed. The 60–70% combination the user remembered is historical and not
current-valid. The PVNet combo still shows a modest, CI-touching-zero win
edge (+3.9pp) at 100 sims on this block; not a deployment recommendation.
