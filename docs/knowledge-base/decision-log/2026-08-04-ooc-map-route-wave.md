# 2026-08-04 — OOC map-route wave: M1 one-ply map gate negative, C1 V4-256 confirmed, S1 blocked

Date: 2026-08-04
Session/task: Execute the map-route wave (M1 one-ply map Q gate, C1 V4-on-256
validation, S1 scrub A/B prep) per the continuation of
`docs/archive/ooc-action-plan-2026-08.md` and the new working spec
`docs/knowledge-base/architecture/ooc-map-route-contracts.md`. Long runs on
the GCP server `sts-test` (preemptible, c4-highcpu-24, 24 threads; binary
built there from the synced tree).

## Decisions / findings

1. **M1 — one-ply map route Q gate is a clear negative at every margin
   (§91):** −16.4pp (m0.5), −15.6pp (m1.0), −19.5pp (m5.0) vs the §76 full
   stack reference (39.8%, bit-reproduced `gates_ref_m1.csv`); all CIs exclude
   zero. Even m5.0 — where the other gates are neutral — is the worst point,
   so the Q head's MAP rankings are anti-predictive wherever it fires.
   **Inference:** the V3 Q head conditions on `(child x, row, room)` via the
   6-cat embeddings only; it carries no downstream route information and
   cannot beat the tuned bottom-up DP (`chooseMapAction`), consistent with
   §62 (graph-NN pathing rejected) and §66m/§70/§73 (weak NN overrides
   damage). **The direct-Q-per-route scheme for map decisions is falsified on
   the current V3 net.** The gate stays opt-in (`STS_OOC_STRATEGIC_MAP=1`,
   default off).
2. **C1 — V4 full stack on the 256-seed block holds (§92):** 105/256 =
   41.0% vs V3's 37.1% on the same block (+3.9pp, same-block aggregate;
   V3-256 per-seed CSV not retained here so not pair-matched) and +18.0pp vs
   the flags-off 256 baseline. No default flip; gates stay opt-in.
3. **S1 (future-encounter scrub) is blocked on data location:** the
   `strategic_tierb.csv` training data and the GPU live on the desktop
   machine; neither the GCP server nor the laptop checkout has the CSV.
   Needs the user to sync it or run the trainer there. Open question.
4. **M2 is re-scoped by M1:** the map route search (plan 5.6.2) must use a
   route-aware leaf — the map DAG encoder (5.3.2) and/or a C_ψ-conditioned
   continuation value (5.4.4) — never the raw V3 Q head.
5. **M2 delivered and ALSO negative (§93):** the C_ψ-surrogate route search
   (weighted pool-average combat expectation + survival × MAP-V-head leaf,
   horizon 3, margin-gated) lost **−1.6pp (m0.5, neutral; floor +2.0
   significant — routes deeper but does not convert), −10.2pp (m1.0, CI
   [−18.0,−3.1]), −20.3pp (m5.0, CI [−29.7,−10.9])** vs the same full stack
   with heuristic pathing. Same margin signature as M1: the more the search
   overrides `chooseMapAction`, the worse. **Both direct map overrides are
   falsified on the current nets; the tuned heuristic DP stays the map
   layer.** The standing §62 lesson (needs paired counterfactual route
   labels, not better state pricing) is reconfirmed; M3 (map DAG encoder) is
   the remaining open lever and is held-out-first.
6. **Server workflow established:** the GCP working tree
   (`/home/philippherrmann/sts_sweep`, rsync'd, non-git) matches local HEAD;
   sync `apps/one_combat.cpp` via `gcloud compute scp`, build with 24
   threads, run sweeps there, pull per-seed CSVs back for `paired_analysis.py`.
   WSL has no route to the server IP; `gcloud compute ssh` (plink) works.

## Evidence

- EXPERIMENTS.md §91 (M1 table + verdict), §92 (C1); per-seed CSVs on the
  GCP server `/tmp/m1_bench/{ref_m1,map_m0.5,map_m1.0,map_m5.0}.csv`,
  `/tmp/c1/c1_v4_256.csv`; M1 rerun determinism verified bit-identical
  excluding the `sec` column.
- EXPERIMENTS.md §93 (M2 table + verdict); per-seed CSVs on the GCP server
  `/tmp/m2w_bench/{ref_m1,m2w_m0.5,m2w_m1.0,m2w_m5.0}.csv` (weighted pool;
  uniform-pool run retained at `/tmp/m2_bench/`).
- `apps/one_combat.cpp::oocOnePlyMapPolicy` (M1, new), globals ~:751-752, env
  parse ~:6662-6666/6690-6700, wiring `runFullRunOOC` ~:2194,
  `runTraceRun` ~:2569; `oocMapRouteSearchPolicy`/`mapRouteSearch`/
  `mapRouteLeafValue`/`routeCpsiExpect` (M2, new), `STS_CPSI_NN`/`STS_OOC_MAP_ROUTE`/
  `STS_OOC_MAP_ROUTE_HORIZON` env, wiring `runFullRunOOC` ~:2202.

## Status and follow-up

- M1 delivered (negative, recorded); C1 delivered (recorded); M2 delivered
  (negative, recorded). Map pathing stays the heuristic. Next:
  (1) user syncs `strategic_tierb.csv` (and probes npy if used) → S1 scrub
  retrain + gate A/B; (2) M3 map DAG encoder held-out on the new pipeline;
  (3) Phase F distillation and Tier-B-style route labels are the standing
  levers per §62/§93.
