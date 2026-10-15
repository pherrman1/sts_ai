# OOC map-route wave contracts — M1 gate, C1 validation, S1 scrub (working spec)

Status: executed 2026-08-04 on the GCP server `sts-test`
(europe-west3-c, c4-highcpu-24, preemptible). Results: **M1 — one-ply map Q
gate: negative at every margin** (EXPERIMENTS.md §91; −16.4/−15.6/−19.5pp at
m0.5/1.0/5.0, CIs exclude zero; ref arm bit-reproduced `gates_ref_m1.csv`
39.8%). **C1 — V4 full stack on the 256-seed block: 105/256 = 41.0%**
(§92; +18.0pp vs the flags-off 256-baseline, +3.9pp vs the V3 256-stack §82).
**M2 — C_ψ short-horizon route search: negative at every margin** (§93;
−1.6/−10.2/−20.3pp at m0.5/1.0/5.0, significant at m1.0/m5.0; weighted C_ψ
pool expectation + MAP V-head leaf; m0.5 floor +2.0 significant but no win
conversion). S1 (future-encounter scrub A/B) is blocked on the training data
location (the `strategic_tierb.csv`/GPU live on the desktop machine, not the
server). Map pathing stays the tuned heuristic DP; both NN overrides are
falsified on the current nets.

## 1. M1 contract — one-ply map route Q gate (delivered, negative)

- New `oocOnePlyMapPolicy` mirroring `oocOnePlyEventPolicy` (one_combat.cpp):
  score every legal child (`getAllMapActions` → `GameAction(x)`) with the Q(s,a)
  head on the pre-decision state; cats via `strategicCands` MAP case
  (cand1=child x, cand2=row, cand3=room); tok path via `buildTokState`
  + `tokEntity` (no-op for MAP); execute argmax only when
  `best − second ≥ margin`; else `chooseMapAction` runs. Dual-net V3/token.
- Env: `STS_OOC_STRATEGIC_MAP=1` (default off), per-screen knob
  `STS_OOC_STRATEGIC_MARGIN_MAP` (sentinel −1.0 = global). Wired into
  `runFullRunOOC` (before the heuristic pathing branch) and `runTraceRun`.
- No datagen, no retrain: Tier-B CSV already has MAP rows with counterfactual
  successor labels (all-decision sampling, §73).
- Hidden info: the map DAG is fully visible at decision time; no hidden
  RNG/future-seed use (spec §A.14 clean).
- Verification: 8-seed smoke (flags-on ≠ off, gate fires, no crash); paired
  128-seed block vs the §76 m1.0 reference (bit-identical to
  `gates_ref_m1.csv`), margins 0.5/1.0/5.0; rerun determinism check.

## 2. C1 contract — V4 full stack on the 256-seed block (delivered)

- §81 follow-up 3: `STS_OOC_STRATEGIC_TOK_NN=…ooc_strategic_tok_final.native`
  + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, margin 1.0, fair, 1,000 sims,
  seeds 126700–126955. Result 105/256 (41.0%). Recorded §92.

## 3. S1 contract — future-encounter feature scrub A/B (deferred: data location)

- B3 finding: `nextFight0..2`/`nextEliteId`/`bossId` (rich rows and V4 globals)
  leak exact future encounters into the training contract (§A.14 violation).
- Plan: retrain V3 (and V4) with those columns dropped; held-out A/B
  (`_metrics.json`) + gate A/B vs the §76/§81 references; decide keep/scrub on
  the measured trade; log the decision. Probe slots (§80) using
  nextFight0/nextEliteId/bossId must be scrubbed too.
- **Blocked**: `build/strategic_tierb.csv` (6.5 GB) is not on the server and
  not on the laptop checkout; the GPU + data live on the desktop machine.
  Needs the user to sync the CSV (or run the trainer there).

## 4. M2 contract — short-horizon map route search (delivered, negative)

- §91 falsified the direct-Q-per-route leaf for map decisions on the current
  V3 net (Q head conditions on `(x, row, room)` only — no downstream route
  information — and cannot beat the tuned bottom-up DP `chooseMapAction`).
- §93 then falsified the C_ψ-surrogate continuation: `oocMapRouteSearchPolicy`
  (weighted C_ψ pool-average P(death)/E[hp|win] per fight room, 30% rest
  heal, pass-through shops/treasures/events, survival × MAP-V-head leaf with
  position advanced + expected HP, max over downstream paths, margin-gated;
  `STS_CPSI_NN`/`STS_OOC_MAP_ROUTE`/`STS_OOC_MAP_ROUTE_HORIZON`). Significant
  damage at m1.0 (−10.2pp) and m5.0 (−20.3pp), neutral at m0.5 (−1.6pp wins,
  +2.0pp floor significant — deeper routes without win conversion). The
  margin signature (worse the more it fires) mirrors §91/M1.
- Conclusion: the heuristic pathing stays the map layer; both direct NN
  overrides are falsified on the current nets. Open levers, in order:
  (a) M3 — map DAG message-passing encoder (plan 5.3.2), held-out on the
  tierb pipeline first; (b) Tier-B-style paired counterfactual labels per
  legal route child (the §62 lesson) — both need the tierb CSV / desktop
  GPU.

## 5. Benchmark protocol (unchanged from §6 of the plan)

- Recorded block 126700–126827 (128), 1,000 sims, fair, 12/24 threads;
  reference `build/gates_ref_m1.csv` bit-identical (39.8%); margins
  0.5/1.0/5.0; paired via `paired_analysis.py`; full config provenance in
  EXPERIMENTS.md. 256-block secondary: 126700–126955.
