# 2026-08-04 — Map-DAG encoder wave (5.3.2): V6 artifact built, offline gain, gameplay neutral-to-negative — falsified, stays opt-in

Date: 2026-08-04
Session/task: Execute the plan "Map DAG encoder on the tierb pipeline"
(5.3.2, the §91/§93 open lever): port the reverse-DAG map encoder into the
tierb trainer + native loader, isolate it on a frozen base (E1), and A/B the
MAP gate on the recorded block. All steps done; the encoder is falsified on
the current labels.

## Decisions / findings

1. **Data without datagen:** `one_combat mapbatch` exported 3,287 lossless
   per-(seed, act) graphs from the corrected CSV (1.7 s); the CSV's 77,789
   MAP-screen rows already carry per-child counterfactual labels (§73
   sample-all), so the encoder trains on exactly the "Tier-B-style route
   labels" §62/§93 demanded.
2. **Implementation:** trainer gains FullMapGraphEncoder + zero-init
   96→168 residual adapter (MAP rows only), `STRAT_FREEZE_BASE=1`,
   `STRAT_INIT_PT`; exporter gains magic OOC_STRAT_V6 (+numpy map path,
   parity incl. 8 direct embedding checks, max err 1.8e-5); `OocStrategicNet`
   gains the encoder + `predictMapActionValue`; the M1 gate routes MAP
   candidates through it when V6; `mapnntest` mode pins C++-vs-Python parity
   (~2e-5). V3/V5 load and margin behavior unchanged.
3. **E1 isolation run:** frozen base = `ooc_strategic_qwin_cal.pt`;
   held-out val_pol_ce 0.4259 (base 0.4671), policy top-1 0.821, q_top1_map
   0.5060, value_mae exactly the base's 1.7388 (frozen-base integrity check).
   **Offline gain, no gameplay transfer.**
4. **A/B (recorded 128-seed block, six gates on, MAP gate at
   probability-point margins):** base map-gate m0.01 15.6% vs the
   no-map-gate arm's 27.3% (§96) — the MAP gate itself costs ~12pp at m0.01,
   replicating §91 on the V5 base; the encoder arm is neutral-to-negative at
   every margin (m0.03 −4.7pp CI [−11.7,+2.3]; m0.05 +0.8pp CI [−2.3,+4.7]).
   **Inference:** the encoder improves label-argmax agreement without fixing
   the causal-route signal — the §62 lesson repeats ("better absolute
   prediction does not identify the causal best route"). The falsification
   points at the label horizon/quality (K=3 one-ply counterfactuals) or the
   policy objective, not the encoder architecture → Phase F (search
   distillation of the policy head) is the coherent next step.
5. **Process bug (trainer state reuse):** a killed trainer leaves a
   byte-size-valid but corrupt `_state.bin` (contiguous corrupted block from
   ~row 400k; the relaunch reused it silently; the frozen base's value_mae
   read 7.57 instead of 1.7388, the tell). Fix: verify frozen-model metrics
   against the source run, or delete `_state.bin` after a killed trainer.

## Evidence

EXPERIMENTS.md §100; `train_strategic.py` (map encoder, freeze, init);
`export_strategic.py` (V6); `apps/ooc_strategic_net.h` +
`apps/one_combat.cpp` (V6 loader, predictMapActionValue, mapnntest);
artifacts `selfplay/models/ooc_strategic_map_enc.{pt,native,metrics.json}`,
`build/strategic_qwin_cal_maps.csv`, `build/mapgate_*.csv`,
`run_mapgate_ab.sh`, `ooc_strategic_map_enc_train.log`.

## Status and follow-up

5.3.2 closed as falsified on the current labels; V6 stays opt-in; the
heuristic pathing and the map-gate-off stack remain the deployed config.
Next: Phase F (5.7.1/5.7.2 — soft-target policy distillation from the
counterfactual labels), which does not need the server and reuses the
corrected CSV.
