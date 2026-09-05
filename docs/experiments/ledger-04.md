## 97. Combat value net under the gate stack — negative at every α (2026-08-04)

- **Goal:** §28/§31's fair-play 1,500-tree combat value net
  (`build/v_combat_fair_trees.txt` sha256
  `e0b645a52b21832ed95fef3b84a50836ca55a61e0a142a9cd13eb85d6d93c8f1`,
  +6.2pp over the pre-gate fair baseline in §28) was never tested under the
  established one-ply gate stack — every gate round (§76/§81/§82/§89/§91–§96)
  ran without `STS_VNET`. A/B on the recorded block: V3 full gate stack @m1.0
  (reference `build/gates_ref_m1.csv`, 39.8%, re-measured bit-identical
  first — 0 non-`sec` diffs) vs the same stack + vnet.
- **Setup:** fair, A0, 1,000 sims, seeds 126700–126827, 12 threads (local;
  binary at commit `db78f4d`). Env: `STS_FAIR=1`,
  `STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`, REST/EVENT/
  SHOP/TREASURE/BOSS_RELIC=1, margin 1.0, `STS_VNET=build/v_combat_fair_trees.txt`.

  | arm | win% | win Δ | floor Δ | HP Δ | cpu_sec/run |
  |---|---|---:|---:|---:|---:|
  | ref (gates only) | 39.8% | — | — | 19.3 | 9.16 |
  | + vnet α0.3 | 36.7% | −3.1 [−11.7,+5.5] | +0.5 | −1.3 | 28.35 |
  | + vnet α0.5 | 39.8% | +0.0 [−10.2,+10.2] | +0.4 | +0.2 | 29.19 |
  | + vnet α0.3, `STS_POLICY=0` | 36.7% | −3.1 [−10.9,+4.7] | −0.2 | −2.1 | 27.92 |

- **Verdict:** ❌ the fair 1,500-tree vnet is strictly dominated under the
  gate stack at 1,000 sims: α0.3 loses ~3pp at 3.1× compute, α0.5 ties at
  3.2× compute. §28's old +6.2pp was measured against a much weaker pre-gate
  fair baseline; the PUCT prior + gate stack already capture what the vnet
  leaf offered, and at low α the net's (older-era) guidance actively hurts.
  The vnet-α curve's mild optimum (~0.5) offers nothing over the free
  reference. No V4+vnet arm was run (no positive point to extend). `STS_VNET`
  stays off for the gate stack. Per-seed CSVs `build/vnet_{a03,a05,a03_nopol}_128.csv`.

## 98. Fair sim-budget sweep of the gate stack — 4,000 sims statistically established (2026-08-04)

- **Goal:** §26's known-RNG sim frontier (PUCT@2000–3000 = +8–11pp over 1000,
  ceiling ~73% with fixed c_puct) was never re-measured in fair play under
  the top OOC stack — every gate benchmark ran at 1,000 sims, and combat has
  repeatedly been identified as the binding constraint (§13, §36). With the
  vnet rejected (§97), the clean frontier test is the gates-only stack at
  higher budgets.
- **Setup:** V3 full gate stack @m1.0 (no vnet), fair, A0, 24 threads on the
  GCP server `sts-test` (binary + artifacts verified hash-identical to local
  HEAD `db78f4d`); 128-seed block 126700–126827 and 256-seed block
  126700–126955; paired per-seed vs the 1,000-sim references
  (`build/gates_ref_m1.csv` 39.8% / `build/sec256_gate_m1.csv` 37.1%).
- **Results — 256-seed block (paired vs sec256_gate_m1):**

  | sims | win% | win Δ (95% CI) | floor Δ (95% CI) | HP Δ | cpu_sec/run |
  |---:|---:|---:|---:|---:|---:|
  | 1000 | 37.1% | — | — | 17.8 | ~9–20* |
  | 2000 | 39.1% | +2.0 [−3.5,+7.8] | +1.2 [−0.1,+2.4] | +1.2 | 20.21 |
  | 3000 | 43.0% | +5.9 [+0.0,+11.7] | +1.4 [−0.0,+2.8] | +4.6 | 30.36 |
  | 4000 | 44.5% | **+7.4 [+1.2,+13.7]** | **+2.7 [+1.2,+4.1]** | +4.2 | 42.66 |

  \* the 1,000-sim `sec256_gate_m1.csv` was measured at 12 threads (§82);
  per-seed CSV retained, cpu column not comparable.
  Also: 128-block confirmation 3k = 43.0% (+3.1 [−5.5,+11.7] vs
  `gates_ref_m1.csv`); 2k@128 = 39.8% (+0.0).
- **Verdict:** ✅ **4,000 sims is the new recommended combat budget for the
  gate stack: +7.4pp win / +2.7 floor / +4.2 HP on 256 paired seeds with
  both win and floor CIs excluding zero, at 4.7× cpu** (42.7 vs 9.2
  cpu-s/run). The curve is monotone and matches the §26 known-RNG direction
  (combat is search-limited); the fair curve is flatter (2k = wash, gains
  appear from 3k up) — no free lunch, but the payoff is established at the
  top OOC stack, unlike the cheap-sims dead ends (§21/§22). Runtime is
  deployment-relevant: 256 seeds @4k = ~8 min wall on 24 threads, but
  cpu_sec/run 42.7 (vs ~6.96 for the flags-off default @1k).
- **Open:** does the curve extend past 4k (known-RNG fixed-c_puct plateaus
  ~6–10k, §26)? V4-net arm at 3k pending (§99). Per-seed CSVs
  `build/simsweep_{2k,3k,4k}_256.csv`, `build/simsweep_{2k,3k}_128.csv`.

## 99. V4 token net at higher sim budgets — new top arm: V4 @3,000 sims (2026-08-04)

- **Goal:** the §98 frontier used the V3 gates; the V4 token net (§81/§92 top
  arm at 1k) was never tested above 1,000 sims. A/B on the same 256-seed
  block, same server, same protocol as §98.
- **Setup:** fair, A0, seeds 126700–126955, 24 threads, V4 full gate stack
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  sha256 `05178ec8…9e1ea` + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, margin 1.0),
  3,000 and 4,000 sims. Banner verified `[ooc-strat-tok-net] loaded`.
- **Complete §98+§99 frontier (256-seed block, paired vs `sec256_gate_m1.csv`):**

  | config | win% | win Δ (95% CI) | floor Δ (95% CI) | HP Δ | cpu_sec/run |
  |---|---|---:|---:|---:|---:|
  | V3 @1000 (ref) | 37.1% | — | — | 17.8 | ~9–20* |
  | V3 @2000 | 39.1% | +2.0 [−3.5,+7.8] | +1.2 [−0.1,+2.4] | +1.2 | 20.2 |
  | V3 @3000 | 43.0% | +5.9 [+0.0,+11.7] | +1.4 [−0.0,+2.8] | +4.6 | 30.4 |
  | V3 @4000 | 44.5% | +7.4 [+1.2,+13.7] | +2.7 [+1.2,+4.1] | +4.2 | 42.7 |
  | **V4 @3000** | **45.3%** | **+8.2 [+0.8,+15.6]** | +2.0 [+0.3,+3.7] | **+7.5** | 31.3 |
  | V4 @4000 | 46.5% | +9.4 [+2.0,+17.2] | +1.8 [+0.0,+3.6] | +5.8 | 41.7 |

  \* 1,000-sim reference measured at 12 threads (§82); cpu column not comparable.
  V4@3k vs V4@4k: +1.2pp win (CI [−4.3,+6.6]), floor −0.1, HP −1.7 — the V4
  curve flattens past 3k.
- **Verdict:** ✅ **V4 @3,000 sims is the new top arm: 45.3% win / 42.9 floor /
  25.3 HP on 256 paired seeds — +8.2pp win and +2.0 floor vs the previous
  recommended config (V3@1k gate stack), both CIs excluding zero, at 3.4×
  cpu.** V4's net-vs-net edge persists at higher sims (V4@3k +2.3pp over
  V3@3k at equal cost, §92's +3.9pp direction), and V4@3k beats V3@4k
  (45.3 vs 44.5%) at 27% less cost. V4@4k's +1.2pp over V4@3k is noise with
  no floor/HP gain — **3k is the operating point, not 4k**. Combined with
  §97 (vnet rejected) and §98 (fair sim frontier, monotone then flat), the
  combat-side wave concludes: spend more sims on the V4 gate stack; the
  prior/gate stack needs no combat value net.
- **Artifacts:** `build/simsweep_v4_3k_256.csv`, `build/simsweep_v4_4k_256.csv`
  (pulled from server `/tmp/`); decision log
  `2026-08-04-combat-side-wave.md`.

## 100. Map-DAG encoder wave (5.3.2): V6 artifact on the tierb pipeline — offline gain, gameplay neutral-to-negative (2026-08-04)

- **Goal** (§91/§93 open lever): give the strategic net's MAP-screen scoring the
  downstream route information the §91 verdict said it lacked ("the Q head
  conditions on (child x, row, room) via the 6-cat embeddings only") by porting
  the full-map reverse-DAG encoder (train_meta_entity.py::FullMapGraphEncoder:
  room/row/col/burning 32-dim node embeddings, bottom-up sweep rows 14→0 with
  mean+max child messages + log1p degree, mean+max readout over the chosen
  child's subtree, roots when py<0) plus a zero-init residual adapter (96→168)
  into the tierb trainer and the native loader.
- **Data:** no new datagen — `one_combat mapbatch build/strategic_qwin_cal.csv`
  exported 3,287 lossless per-(seed, act) graphs (1.7 s); the corrected CSV's
  77,789 MAP-screen rows (screen 5) carry the per-child counterfactual labels
  (§73 sample-all), joined by (seed, act) with position from curMapX/curMapY and
  the child from cand1; burning cell marked while greenKey absent.
- **Implementation:** `train_strategic.py` — optional MAPS.csv arg (3rd CLI or
  STRAT_MAPS_CSV), FullMapGraphEncoder + zero-init adapter added to the
  (z,b,a,screen) concat for MAP rows only, STRAT_FREEZE_BASE=1 (only map_*
  params train), STRAT_INIT_PT (seed the frozen base from an existing
  checkpoint), new q_top1_map/q_mae_screen-brier metrics. `export_strategic.py`
  — new magic **OOC_STRAT_V6** (V5 layout + encoder block); numpy map path +
  torch/numpy parity incl. 8 direct map-embedding checks (max err 1.8e-5);
  logit tolerance loosened to 2e-4 for V6 (adapter op-order noise; the logit is
  not the deployed gate output). `apps/ooc_strategic_net.h` —
  `OocStrategicNet` gains the encoder arrays + `encodeMapGraph` +
  `predictMapActionValue` (rooms/edges/special/position/chosen from `gc.map`
  and cand1); loader accepts V3/V5/V6. `apps/one_combat.cpp` —
  `oocOnePlyMapPolicy` routes MAP candidates through the graph path when the
  artifact is V6; new `mapnntest` mode for deterministic C++-vs-Python parity
  (max |diff| ~2e-5 on fixed synthetic inputs). V3/V5 loading and margin
  behavior unchanged (verified on the recorded block).
- **E1 (isolation run, frozen base):** `STRAT_FREEZE_BASE=1
  STRAT_INIT_PT=ooc_strategic_qwin_cal.pt`, 40 epochs on the corrected CSV →
  `ooc_strategic_map_enc.native` (V6, md5 de2d1868…). Held-out: val_pol_ce
  0.4259 (base 0.4671), policy top-1 0.821, q_brier 0.0409, **q_top1_map
  0.5060 (4,324 MAP groups; the base's MAP q_top1 was not tracked — added this
  wave — but E1's epoch-1 value was already 0.5009)**, value_mae 1.7388 =
  the loaded base exactly (frozen-base integrity check).
- **Process bug caught:** the first E1 launch was killed mid state.bin write;
  the relaunch silently REUSED the corrupt file (byte size matched) → the
  frozen base's value_mae read 7.57 instead of 1.74, and rows ≥400k differed
  from the clean `ooc_strategic_qwin_cal_state.bin` (contiguous corrupted
  block). Fix: kill, delete, rerun (clean run: value_mae 1.7388 ✓). Lesson:
  a killed trainer's `_state.bin` can be size-valid but corrupt — verify
  frozen-model metrics against the source run before trusting a reused file.
- **Paired A/B** (fair, A0, 1,000 sims, seeds 126700–126827, 12 threads;
  reference = §76 full stack m1.0 `gates_ref_m1.csv`, 39.8%; six gates ON in
  both arms + `STS_OOC_STRATEGIC_MAP=1`, MAP gate at probability-point
  margins; per-seed CSVs `build/mapgate_{qwin_cal,map_enc}_m*.csv`):

  | config | wins | win Δ (vs ref) | floor Δ | discordant |
  |---|---:|---:|---:|---:|
  | base m0.01 | 20 (15.6%) | −24.2pp CI [−33.6,−15.6] | −7.4 CI [−10.0,−4.9] | 45 |
  | base m0.03 | 32 (25.0%) | −14.8pp CI [−24.2,−4.7] | −3.1 CI [−5.5,−0.8] | 43 |
  | base m0.05 | 29 (22.7%) | −17.2pp CI [−26.6,−7.0] | −3.5 CI [−5.9,−1.1] | 44 |
  | base m0.10 | 28 (21.9%) | −18.0pp CI [−28.1,−7.8] | −3.5 CI [−5.9,−1.1] | 45 |
  | enc m0.01 | 18 (14.1%) | −25.8pp CI [−35.2,−16.4] | −7.6 CI [−10.3,−4.9] | 45 |
  | enc m0.03 | 26 (20.3%) | −19.5pp CI [−29.7,−9.4] | −4.1 CI [−6.3,−1.8] | 44 |
  | enc m0.05 | 30 (23.4%) | −16.4pp CI [−25.8,−7.0] | −3.3 CI [−5.7,−0.9] | 44 |
  | enc m0.10 | 28 (21.9%) | −18.0pp CI [−28.1,−7.8] | −3.5 CI [−5.9,−1.1] | 45 |

  (Context: without the MAP gate, the §96 calibrated arms at m0.01/m0.03 were
  27.3%/25.0% — turning the MAP gate ON costs ~12pp at m0.01 even on the base,
  replicating §91's negative; the no-map-gate reference arms are
  `build/qwin_cal_m*.csv`.)

- **Encoder vs base at equal margins (paired):** m0.03 −4.7pp CI [−11.7,+2.3]
  (n.s., negative); m0.05 +0.8pp CI [−2.3,+4.7] (n.s., positive).
- **Verdict:** ❌ the map-DAG encoder does not rescue the map gate on the
  tierb pipeline. Offline MAP ranking improved (q_top1_map ~0.50 vs ~0.49-0.50
  base estimate; val_pol_ce 0.426 vs 0.467) but the A/B is neutral-to-negative
  at every margin, exactly the §62 pattern ("better absolute prediction does
  not identify the causal best route": predictive gain, policy rejected).
  Combined with §96 (the MAP label signal itself is weak), the pre-registered
  success criterion (encoder ≥ base on wins) is not met → **the encoder lever
  (5.3.2) is falsified on the current labels; the heuristic pathing and the
  map-gate-off stack stay; the V6 artifact stays opt-in and undeployed.**
  Remaining levers per §93: Tier-B-style route labels are what the labels
  already are here (per-child counterfactual at MAP), so the falsification
  points at the label horizon/quality (K=3 one-ply) or the policy objective,
  not the encoder — Phase F (search distillation) is the coherent next step.
- **Artifacts:** `selfplay/models/ooc_strategic_map_enc.{pt,native,
  metrics.json}` (+`_state.bin`), `build/strategic_qwin_cal_maps.csv`,
  per-seed `build/mapgate_*.csv`, `run_mapgate_ab.sh`,
  `ooc_strategic_map_enc_train.log`.

## 101. PVNet parity fixes + 100-sim §72 replication on the fixed binary (2026-08-04)

- **Context:** the C++ CombatPVNet inference had three trainer mismatches
  (FFN GELU vs ReLU, sparse vs always-14 token layout, one-unit policy-head
  dot product) plus no parity check (`apps/one_combat.cpp` `pvnetparity`,
  `combat_pvnet_parity.py`; decision log
  `2026-08-04-combat-pvnet-parity-fixes.md`). After the fixes,
  encoder/policy/value match the exported model to ~1e-6 (d128 and d64).
- **Replication setup:** `STS_FAIR=1 STS_SEARCHER3=1
  STS_PVNET=build/v_combat_pvnet.txt STS_PVNET_ALPHA=0 ./build/one_combat
  bestbench 100 128 0 126700 build/pvnet_fixcheck_s3p0_128.csv`; tracked
  PVNet sha256 `05d809298921623af7c87c06e7dd31f5129abfd77cc702f75b9867949a59533f`;
  tracked policy prior auto-loaded; 12 threads; native OOC defaults (no gate
  opt-ins).
- **Result (128 seeds 126700–126827, 100 sims, S3 + PVNet α=0):**
  **16/128 = 12.5% win, mean floor 28.8, mean end HP 6.4**,
  cpu_sec/run 18.5, wall 212 s. Versus the §72 historical same-block result
  (8.6% / 26.4 / 4.2) this is +3.9pp win, +2.4 floor, +2.2 HP — directionally
  positive but within ~1 SE (4.0pp); attribution is not clean because the
  current binary's OOC stack is newer than the §72 binary's even though the
  default opt-in gates are off. Versus the same-budget S2 default (4.7%,
  §72) the S3+PVNet combo remains clearly positive.
- **Cost note for Phase 1:** S3+PVNet is ~18x more expensive per sim than S2
  fair (18.5 vs ~1.0 cpu-sec/run at 100 sims) because `computeEdgePriors`
  runs a PVNet forward per expanded node; a 3k-sim arm ≈ 49 min/128 seeds on
  24 threads. **Caveat:** during part of this replication another agent
  occupied 6 of the 12 local cores, so the run was contended; the 18.5
  cpu-sec/run and wall time are upper bounds, not clean measurements. Not
  re-tested; re-measure on an uncontended server before sizing Phase 1.
- **Artifacts:** `build/pvnet_fixcheck_s3p0_128.csv`,
  `build/pvnet_fixcheck_s3p0_32.csv`, `build/pvnet_parity{,_smoke,_d64}.csv`.

## 102. Dynamic sim budgets I: convergence stop is INERT under fair play (2026-08-04)

- **Goal:** re-test §22's `searchToTotalAdaptive` early stopping
  (`STS_CONVERGE`/`STS_CONV_PATIENCE`/`STS_CONV_MIN`) in the fair regime at
  the new 3k operating point. §22 measured it only in known-RNG @50k; the
  recorded result "convergence ~= flat at equal cpu" does not say whether the
  stop even fires under per-sim determinization.
- **Setup:** fair, A0, V4 full gate stack @3,000 base sims, 64 seeds
  126700–126763, 24 threads (server `sts-test`, binary at `b7af3fa`).
  `(patience, minSims)` ∈ {(200,200), (400,300), (800,400)}.
- **Result:** all three settings are **bit-identical to flat V4@3k on all 64
  seeds** (0 non-`sec` diffs: 23/64 wins, floor 41.6, HP 20.2), cpu_sec/run
  30.4–30.5 vs 31.3 flat (~2.5%, effectively no stopping).
- **Verdict:** ❌ the plateau condition never triggers in fair play. Each
  `step()` re-determinizes the hidden draw order, so `bestActionValue` keeps
  improving; "no improvement for `patience` consecutive sims" essentially
  never occurs within 3k sims. §22's mechanism only stopped in known-RNG,
  where rollouts are near-deterministic. Per-decision stopping in the fair
  regime needs a different convergence signal (e.g., best-action visit-share
  stability or a windowed root-value mean), not `bestActionValue`.
- **Artifacts:** `build/conv_{p200_m200,p400_m300,p800_m400}_64.csv` (pulled
  from server `/tmp/`); `apps/one_combat.cpp::searchToTotalAdaptive` unchanged.

## 103. Dynamic sim budgets II: C_psi difficulty-adaptive per-fight budget — compute-efficient, win edge not established (2026-08-04)

- **What:** new `fightSims` path (`STS_SIM_ADAPT=1` + `STS_CPSI_NN`, code in
  `apps/one_combat.cpp`): at fight start one no-peek C_ψ forward pass
  (`buildCpsiEntry` + `CombatCpsiNet::predict`,
  `selfplay/models/v_combat_cpsi.txt`) sets
  `budget = clamp(base × (0.5 + P(death) + (1 − E[hp/maxHp|win])), minFrac,
  maxFrac) × base` with `STS_SIM_ADAPT_MIN_FRAC=0.4` / `_MAX_FRAC=2.0`
  defaults. Learned tiering — unlike the static `STS_SIMS_*` room tiers it
  cannot misjudge difficulty (act-3 monsters ≈ act-1 elites, §21); pre-combat
  features only, so fair-play clean. Precedence over the static tiers.
- **Setup:** fair, A0, V4 full gate stack, 24 threads, binary `b7af3fa`;
  three 256-seed blocks (126700, 126955, 127211). Arms: flat V4@2k (new
  `build/simsweep_v4_2k_256.csv` + `_b2`,`_b3`), adaptive@2200 (mean budget
  ≈ 1,900; `build/simadapt_2200_256.csv` + `_b2`,`_b3`), flat V4@3k on
  blocks 1/3 (existing `simsweep_v4_3k_256.csv`, new `_b3`).
- **Results — adaptive@2200 vs flat V4@2k (paired):**

  | block | win Δ (95% CI) | floor Δ | HP Δ | cpu Δ |
  |---|---:|---:|---:|---:|
  | 1 (126700) | +2.7 [−3.1,+8.6] | −0.0 | +2.8 | −2.94 (18.98 vs 21.92) |
  | 2 (126955) | +3.9 [−2.0,+9.4] | +0.5 | +1.7 | −2.01 (20.19 vs 22.20) |
  | 3 (127211) | −1.2 | −0.6 | −0.3 | −2.85 (19.26 vs 22.11) |
  | **combined 767** | **+1.8 [−1.7,+5.3]** | −0.0 | **+1.4** | **−2.60 (−12%)** |

  vs flat V4@3k (the recommended reference, 45.3%): block 1 **45.7% (tie) at
  −39% cpu**; block 3 42.6% (−2.7pp) at −40% cpu. Anomaly: adaptive@3000
  (42.6%, block 1) was *worse* than adaptive@2200 (45.7%, block 1) — the
  formula's benefit does not scale with base; noise-level.
- **Verdict:** ➕/➖ mixed. Mechanically it works and is the first dynamic
  budget with a favorable compute/win slope — §21 static tiers and §22
  convergence both found *no* savings, while adaptive@2200 saves ~12% compute
  at no measurable win-rate loss vs flat@2k and on block 1 matched the 3k
  reference at −39% compute. But the win edge is **not established** (767-seed
  CI [−1.7,+5.3], block 3 flipped negative) and vs the 3k reference it is
  block-dependent. Not promotion-grade; **stays opt-in behind
  `STS_SIM_ADAPT=1`**. For compute-constrained runs it is the efficiency
  option; flat V4@3k remains the win-rate operating point.
- **Artifacts:** `build/simsweep_v4_2k_256{,_b2,_b3}.csv`,
  `build/simadapt_2200_256{,_b2,_b3}.csv`, `build/simsweep_v4_3k_256_b3.csv`,
  `build/simadapt_256.csv` (adaptive@3000); `apps/one_combat.cpp::fightSims`,
  `STS_SIM_ADAPT*` env parse.

## 104. Phase F search distillation (5.7.1 + 5.7.2): soft-target policy objective — falsified on the gate A/B (2026-08-04)

- **Goal:** the §100 verdict (better prediction ≠ better play) points at the
  policy objective, not the encoder. Phase F asks the narrow question: does a
  policy head trained on `softmax(labelWon/τ)` search-distillation targets
  beat one trained on one-hot `chosen`, measured as a policy-score gate arm?
  Scope: 5.7.1 (produce the targets) + 5.7.2 (train the head); 5.7.3 (the
  iterative loop) explicitly out of scope.
- **Step 1 — π_target diagnostic (5.7.1a, no code):** on
  `build/strategic_qwin_cal.csv` (809,146 rows, 1,295 seeds; groups =
  seed×1e6+decIdx; 133,144 groups with ≥2 finite labels AND exactly one
  chosen row):
  - `argmax(labelWon)` vs `chosen` agreement **38.0% strict / 58.1% in-set**
    (chosen inside the tied argmax set) — far below the 0.90 stop gate, so the
    distillation has a target population. Per screen: REST 57.5/78.2, MAP
    55.8/66.0, EVENT 43.4/57.8, BOSS_RELIC 41.7/47.3, REWARDS 35.0/57.5,
    TREASURE 23.1/56.8, CARD_SELECT 16.2/44.6, SHOP 15.7/32.8.
  - Soft-target determinacy: median softmax margin (p1−p2) = **0.000 at every
    τ** (τ=1.0: 90.7% of groups <0.05; entropy mean 1.54 bits) — `labelWon`
    is heavily tied (discrete 0/1 + bootstrap fractions), so only the argmax
    carries ranking signal.
  - `argmax(softmax(labelWon/τ))` ≡ `argmax(labelWon)` at all τ (100%) —
    τ reshapes gradient sharpness only, never the ranking.
- **Step 3 — implementation:** `train_strategic.py` gains
  `STRAT_DIST_LAMBDA` (0.5) + `STRAT_DIST_TAU` (1.0): policy loss =
  `(1−λ)·CE(one-hot chosen) + λ·CE(softmax(labelWon/τ))` over each group's
  finite-label rows (same stable-logsumexp group machinery), new held-out
  `dist_top1` (policy argmax vs label argmax); Q/aux heads, early-stop
  criterion (`val_pol_ce`) untouched. `apps/one_combat.cpp` gains
  `STS_OOC_STRATEGIC_SCORE=policy` (default `q`): the one-ply gates score
  candidates with `sigmoid(predictPolicyLogit)` (V5/V6,
  `oocStrategicScore` helper) instead of `predictActionValue`; token path and
  MAP encoder path untouched; env unset verified **bit-identical** to the
  recorded §96 block (`build/qwin_cal_m0.01.csv` per-seed match on all 128
  seeds, only the `sec` column differs).
- **Training** (corrected CSV, 60 epochs, GPU, τ=1.0; state.bin reused from
  the §100-verified base — λ=0 parity run reproduced the baseline epoch-1
  metrics exactly, value_mae 9.0578 ✓):

  | model (md5 .pt) | λ | val_pol_ce (best) | pol_top1 | dist_top1 | q_top1 | q_brier | margin |
  |---|---|---|---|---|---|---|---|
  | V5 base (3ac8343d) | 0 | 0.4671 | 0.7967 | — | 0.3228 | 0.0409 | 18.58 |
  | dist_l025 (e2894dcc) | 0.25 | 0.6635 | 0.7917 | 0.3847 | 0.3418 | 0.0389 | 1.18 |
  | dist_l050 (3f042f2b) | 0.50 | 0.8608 | 0.7890 | 0.3822 | 0.3618 | 0.0393 | 0.75 |
  | dist_l100 | 1.00 | 1.5311 | 0.4434 | 0.3500 | 0.3287 | 0.0521 | 0.01 |

  (val_pol_ce rises with λ by construction — it measures mismatch with
  behavior, which the blend intentionally trades away. λ=1.0 collapses
  behavioral top-1 and flattens the logits; rejected. λ=0.25/0.50 keep
  pol_top1 ≈ 0.79, lift q_top1, and are within noise of each other on
  dist_top1 → both A/B'd. dist_top1 ≈ 0.38 for both — the distilled policy
  agrees with the label argmax no better than behavior did (38%),
  i.e. the tie-dominated labels cap the ranking signal.)
- **Paired A/B** (fair, A0, 1,000 sims, seeds 126700–126827, 12 threads;
  six gates ON, MAP off, `STS_OOC_STRATEGIC_SCORE=policy`; reference =
  `build/gates_ref_m1.csv`, 39.8%; per-seed CSVs `build/qwin_cal_dist_l{025,
  050}_m*.csv`; `run_distgate_ab.sh`):

  | config | wins | vs Q-gate (paired, B−A) | vs ref |
  |---|---:|---|---|
  | Q-gate m0.01/m0.03/m0.05/m0.10 (reused §96) | 27.3/25.0/22.7/21.9% | — | −12.5/−14.8/−17.1/−17.9pp |
  | dist_l025 m0.01/m0.03/m0.05/m0.10 | 9.4/14.1/10.9/14.8% | Q better: +9.4..+26.6 / +3.1..+18.8 / +3.1..+20.3 / −0.8..+14.8pp | m0.10: −25.0 [−34.4,−15.6] |
  | dist_l050 m0.01/m0.03/m0.05/m0.10 | 10.9/8.6/12.5/18.8% | Q better: +7.8..+25.8 / +7.8..+25.0 / +2.3..+18.0 / −4.7..+10.9pp | m0.05: −27.3 [−35.9,−18.8]; m0.10: −21.1 [−30.5,−12.5] |

  The distilled policy logits are near-uniform (raw margin ~1.2 vs 18.6
  baseline ≈ 0.2–0.3 probability-point gaps), so the margin gate fires on
  almost every decision — the arm is an aggressive override. Every policy arm
  loses to both the Q-gate arm and the reference; only at m0.10 does the
  paired CI cross zero (still negative, leaning Q).
- **Verdict:** ❌ pre-registered criterion (1) — distilled-policy gate ≥
  Q-gate on wins per margin — fails at every margin (the Q-gate wins by
  ~+3..+27pp, significant at m≤0.05). No flip candidate → criterion (2)
  moot. The **objective lever is falsified on the current Tier-B labels**:
  soft-target distillation neither improves label-argmax agreement beyond
  behavior's 38% (the tie-dominated `labelWon` caps it) nor transfers to
  gameplay. This completes the §100 falsification chain (encoder → objective):
  both levers are rejected on these labels; the remaining lever per §93 is
  label horizon/quality (K=6 deep targets, 5.7.1b — not run this wave).
  5.7.3 stays unchecked. The score-source env stays opt-in; `q` remains the
  default.
- **Artifacts:** `selfplay/models/ooc_strategic_qwin_cal_dist_l{000,025,050,
  100}.{pt,metrics.json}` (+`_state.bin`; `.native` for l025/l050, parity
  32/32, V5 magic), `build/qwin_cal_dist_l{025,050}_m*.csv` (+`.log`),
  `run_distgate_ab.sh`, `ooc_strategic_qwin_cal_dist_l*_train.log`;
  diagnostic script `/tmp/opencode/ooc_phasef_diag.py` (one-off).

## 105. Label-noise wave (post-§104): futures=2 variance reduction, value-grid quantization, trainer-side denoising — ALL NULL; the label ranking itself is the ceiling (2026-08-05)

- **Goal:** §104's falsification left "label noise" as the explanation for the
  missing transfer. This wave tests the noise readings directly: (L0)
  decompose the noise sources, (L1a) futures=2 variance reduction, (L2)
  trainer-side target denoising. Pre-registered offline gate before any gate
  A/B: dist_top1 > 0.385 OR q_top1 > 0.362 (the §104 l050 numbers); A/B only
  qualifying arms.
- **L0 — noise decomposition (no code, on `build/strategic_qwin_cal.csv`):**
  - Only **55 distinct labelWon values** across 809k rows (terminal 0/1 +
    coarse bootstrap grid) → the tie density IS value quantization.
  - 19.3% of groups have zero spread (max==min), 40.2% have spread <0.05.
  - All-terminal groups agree with behavior 43.3% vs 37.1% for any-censored —
    truncation (K=3) explains only ~6pp of the disagreement.
  - Reading: single-path variance (futures=1) + quantization, not truncation,
    are the structural noise candidates.
- **L1a — futures=2 datagen (matched control):**
  `STRATEGIC_SAMPLE_ALL=1 STRATEGIC_BRANCH_FUTURES=2 ./build/one_combat
  strategicgen2 500 1000 0 build/strategic_qwin_f2.csv 200000` (26 min; §94
  seeds are 200000–201309, so seeds 200000–200499 overlap by design and form
  a matched pair with the fresh futures=1 control
  `build/strategic_qwin_f1.csv`, 13 min). Results: 315k rows both, 100%
  labeled; **unique labelWon 126,097 vs 55** — the quantization is gone.
  Trained the §104 recipe (λ=0.5, τ=1.0, 60 epochs) on both + a λ=0 control
  on f2 (md5s: f1_l050 7122bccb, f2_l000 7ff5a0e1, f2_l050 b538201d):

  | model | dist_top1 | q_top1 | q_brier |
  |---|---|---:|---:|
  | futures=1 λ=0.5 (f1_l050) | 0.3640 | 0.3023 | 0.0458 |
  | futures=2 λ=0.5 (f2_l050) | 0.3610 | 0.3036 | 0.0423 |
  | futures=2 λ=0 (f2_l000) | 0.3619 | 0.3370 | 0.0438 |

  Rank metrics are flat (dist_top1 −0.003, q_top1 +0.001) — the continuous
  value grid and halved per-action variance do not help the model extract
  ranking signal; only q_brier improves (calibration of the Q probabilities,
  not their ranking). (Note: q_top1 ≈ 0.30 on these 500-seed sets vs 0.36 on
  the 1,295-seed §104 set — training-data volume dominates label precision.)
- **L2 — trainer-side denoising on the existing CSV** (new default-off envs
  in `train_strategic.py`, λ=0.5 recipe; all three **fail the offline gate**):

  | arm | knob | dist_top1 | q_top1 | verdict |
  |---|---|---:|---:|---|
  | eps | STRAT_DIST_MARGIN_EPS=0.05 (uniform target within ε of max) | 0.3848 | 0.3199 | fail (q_top1 ↓) |
  | spread | STRAT_DIST_SPREAD_W=1 (group weight ∝ max−min) | 0.3746 | 0.3250 | fail |
  | term | STRAT_DIST_TERM_W=2 (2× weight on labelBootstrap==0 rows) | 0.3834 | 0.3348 | fail |

  Every variant degrades the Q head's label-ranking agreement (q_top1 0.362 →
  ≤0.335). Defaults verified byte-parity with §104 (all knobs off = same
  numbers).
- **Verdict:** ❌ the label-noise reading is falsified on three independent
  angles: (1) quantization removal + variance halving (L1a matched control)
  changes nothing on the ranking metrics; (2) trainer-side target
  engineering (L2) does not help; (3) the L0 probe shows even exact terminal
  labels disagree with behavior 43% of the time. The **one-ply label ranking
  itself is the ceiling** — this closes the "noise" reading of §104 and with
  it the learned-label line (Q-gate §96, map encoder §100, policy objective
  §104, label noise §105). Pre-registered: no gate A/B (no arm qualified).
  L1b (K=6 deep targets, 5.7.1b) is **not run**: L0 shows truncation is the
  weak lever (~6pp terminal-vs-censored gap) and L1a shows label precision
  does not transfer — deferred/closed with this reasoning. Remaining options
  per §93: 5.7.3 (iterative play→search→train loop, which reframes the
  labels via self-play) or abandoning the one-ply label approach.
- **Artifacts:** `build/strategic_qwin_f{1,2}.csv` (+`.log`),
  `selfplay/models/ooc_strategic_qwin_f{1,2}_*.{pt,metrics.json}` (+`_state.bin`),
  `selfplay/models/ooc_strategic_qwin_cal_dist_{eps,spread,term}.{pt,
  metrics.json}` (+`_state.bin`), `ooc_strategic_qwin_{f1,f2}_*_train.log`,
  `ooc_strategic_qwin_cal_dist_{eps,spread,term}_train.log`;
  `train_strategic.py` STRAT_DIST_{MARGIN_EPS,SPREAD_W,TERM_W} (defaults
  reproduce §104 exactly).

## 102. Phase 1 payoff gate: S3+PVNet at 3k sims — no deployable channel; A–H sweep stopped (2026-08-04/05)

- **Question:** does Searcher3+PVNet have a payoff channel at the 3k-sim
  operating point of the recommended config, using the tracked (parity-fixed)
  model? Decides whether the A–H architecture sweep is worth running at all.
- **Setup:** GCP `sts-test` (c4-highcpu-24, 24 threads), fair, A0, 3,000
  sims/decision, 128 seeds 126700–126827, default OOC stack (no gate
  opt-ins), tracked artifacts (PVNet sha256
  `05d809298921623af7c87c06e7dd31f5129abfd77cc702f75b9867949a59533f`, policy
  prior `24793bd3...`, floor `3a342046...`, win `fc52c14c...`), binary built
  from local HEAD + parity fixes, BLAS via
  `STS_OPENBLAS=/usr/lib/x86_64-linux-gnu/libopenblas.so.0` with
  `OPENBLAS_NUM_THREADS=1` (without this, OpenBLAS+OpenMP oversubscribes the
  box ~2x and runs slower than scalar). Arms: true S2 (no `STS_SEARCHER3`),
  S3 control, S3+PVNet α=0, S3+PVNet α=1.0. Note: the script's first arm
  (`pvnetgate_s2_ref_3k_128.csv`) accidentally set `STS_SEARCHER3=1` too and
  is per-seed identical to the S3 control; the true S2 arm is
  `pvnetgate_s2_true_3k_128.csv`.
- **Results (128 seeds, paired):**
  - S2 true: **27/128 = 21.1%**, floor 37.3, HP 8.1, 24.3 cpu-sec/run
    (matches the §68 default @1k of 21.1% — the default fair S2 is flat
    1k→3k sims on this block).
  - S3 ctl: **34/128 = 26.6%**, floor 36.4, HP 13.1, 29.0 cpu-sec/run —
    +5.5pp vs S2, CI [−3.8, +14.8]; floor −0.9 CI [−3.6, +1.8].
  - S3+PVNet α=0 (policy priors only): **25/128 = 19.5%**, floor 34.8,
    HP 9.1, 409.8 cpu-sec/run — −7.0pp vs S3 ctl CI [−15.2, +1.2];
    −1.6pp vs S2 CI [−10.3, +7.1]. **Priors actively hurt at 3k sims.**
  - S3+PVNet α=1.0 (pure neural leaf): **38/128 = 29.7%**, floor 37.8,
    HP 13.1, 436.2 cpu-sec/run — +8.6pp vs S2 CI [−0.9, +18.1],
    +3.1pp vs S3 ctl CI [−5.0, +11.2], at **~15–18x the per-run compute**.
- **Interpretation:** the tracked PVNet's payoff channel closes at 3k sims:
  its policy head degrades search when search is deep (the §72 100-sim
  prior benefit inverts), and its neural leaf buys a within-noise win gain
  at 14–18x compute — dominated by S2/S3 on any fixed wall-clock budget.
  The §97 vnet rejection and this gate agree: learned combat leaves/priors
  do not beat rollout+search at equal compute in the current stack.
  Searcher3 itself (without any net) is the only arm with a same-cost
  positive signal (+5.5pp, CI touching 0).
- **Decision:** per the agreed gate rule, the **A–H architecture sweep is
  stopped**. No Phase 3/4 spend on width/layers/heads/FFN variants: the
  model-architecture levers cannot fix a missing same-cost channel, and the
  14x per-sim leaf cost is structural (per-node priors + neural leaf), not
  data-dependent. Phase 2 fairgen regeneration is deprioritized for this
  purpose; representation experiments (per-card tokens) would face the same
  cost wall unless combined with a fully neural (rollout-free) regime at low
  sims, which §72 and this gate both show loses.
- **Artifacts:** per-seed CSVs `build/pvnetgate_{s2_true,s3_ctl,s3_pv0,
  s3_pv1}_3k_128.csv` (+ `s2_ref`, the mislabeled S3 duplicate); server log
  `/tmp/pvnet_gate.log` on `sts-test`; `run_pvnet_gate.sh` (arm 0
  `STS_SEARCHER3` bug fixed in the script after the run).

## 106. S3 feature ablation at the 3k operating point — belief, chain, and CRN are net-negative; prune/live are inert (2026-08-05)

- **Goal:** attribute S3's same-cost +5.5pp signal (payoff gate §102, CI
  touching 0, measured on the default OOC stack) to its individual
  mechanisms, at the actual operating point: V4 full gate stack, fair, A0,
  3,000 sims/decision.
- **New code:** five env toggles parsed next to `STS_SEARCHER3`
  (`apps/one_combat.cpp::main`): `STS_S3_BELIEF`, `STS_S3_PRUNE`,
  `STS_S3_CHAIN`, `STS_S3_LIVE` (default 1 = full behavior, opt-out) and
  `STS_S3_CRN` (default 0 = opt-in). Wraps: the two `belief.update` calls and
  three `canPruneAsDead` sites in `step()`; the chain-compression loop
  (`src/sim/search/BattleScumSearcher3.cpp`); the agent-level live-valid
  root-edge filter (`s3PickRootAction`, `src/sim/search/ScumSearchAgent2.cpp`,
  Searcher2-style most-visited-then-fallback when off). **Finding en route:**
  `warmStartRootCRN`/`prepareCRNParticles` were dead code — declared and
  defined but never called, so "CRN" was never active in any recorded result;
  `STS_S3_CRN=1` calls `warmStartRootCRN` at the top of `search`/
  `searchToTotal`. (`crnTiebreak` is declared in the header and never
  defined — also dead.) Particle count is hardcoded at 64
  (`ScumSearchAgent2::playoutBattleFair`).
- **Setup:** GCP `sts-test` (24 threads), fair, A0, 3k sims, 128 seeds
  126700–126827, V4 full gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native` sha256 `05178ec8…9e1ea` +
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, margin 1.0, MAP off), tracked policy
  prior auto-load (`24793bd3…`), no vnet/PVNet/dist. Binary = local HEAD
  `8681a75` + the new flags; `OPENBLAS_NUM_THREADS=1` convention. **A0
  bit-identity gate passed:** `s3ablate_s2_ref` matches the recorded §99
  128-slice of `build/simsweep_v4_3k_256.csv` per-seed on all 8 data columns
  (wins 56 = 56, 0 non-`sec` diffs). `run_s3_ablate.sh` reproduces the stack.
- **Results (128 seeds, paired):**

  | arm | wins | win% | floor | HP | cpu-sec/run | win Δ vs S3 ctl (CI) | win Δ vs S2 (CI) |
  |---|---:|---:|---:|---:|---:|---|---|
  | A0 S2 ref | 56 | 43.8 | 43.1 | 24.9 | 32.9 | — | — |
  | A1 S3 ctl | 63 | 49.2 | 41.7 | 30.5 | 35.4 | — | +5.5 [−4.1,+15.0] |
  | A2 S3 − belief | 74 | **57.8** | 43.6 | 37.4 | 31.1 | **+8.6 [−1.1,+18.3]** | **+14.1 [+3.5,+24.7]** |
  | A3 S3 − prune | 63 | 49.2 | 41.7 | 30.5 | 35.2 | +0.0 (bit-identical) | — |
  | A4 S3 − chain | 69 | 53.9 | 43.2 | 32.8 | 35.2 | +4.7 [−4.0,+13.3] | +10.2 [−0.5,+20.8] |
  | A5 S3 − live | 63 | 49.2 | 41.7 | 30.5 | 35.6 | +0.0 (bit-identical) | — |
  | A6 S3 + CRN | 45 | 35.2 | 37.1 | 21.5 | 33.8 | **−14.1 [−24.7,−3.5]** | −8.6 [−18.1,+0.9] |

- **Verdicts (pre-registered criteria):**
  - **Belief reweighting is harmful:** removing it wins +8.6pp vs ctl
    (CI touches 0 at n=128) and **+14.1pp vs S2 (CI excludes 0)**, with
    floor +1.9, HP +6.8, at 12% less compute (31.1 vs 35.4). With only 64
    particles the reweighted belief concentrates on early-draw-matching
    hypotheses and over-commits; uniform resampling explores better
    (**Inference**).
  - **Chain compression is harmful:** +4.7pp vs ctl (CI [−4.0,+13.3]),
    +10.2pp vs S2 (CI [−0.5,+20.8]). Forcing non-drawing cards before the
    rollout commits the rollout to a card-spam line before search can weigh
    the alternatives (**Inference**).
  - **Pruning is inert:** A3 is per-seed bit-identical to ctl on all 128
    seeds — conservative `canPruneAsDead` never changes an outcome in this
    regime (dead weight only).
  - **Live-valid filter is inert:** A5 bit-identical to ctl — in fair play
    the fresh-per-decision tree enumerates edges from the live battle, so
    the filter never changes the selected root action.
  - **CRN warm start is harmful:** −14.1pp vs ctl (CI excludes 0). The 64
    CRN rollouts per root edge inject a noisy Q prior that PUCT then
    trusts (**Inference**).
- **Interpretation:** the S3 package's +5.5pp comes from its
  **particle-determinization core** (six-stream randomization + uniform
  particle sampling + observation caching + PUCT), *despite* its own
  belief/chain machinery — and CRN is confirmed bad enough to have been
  shipped dead. The payoff-gate's "searcher question, not a model question"
  sharpens to: the searcher's value is the determinization/observation
  layer, and the currently-defaulted S3 extras (belief, chain) should be
  off. The `STS_S3_*` flags are defaults-preserving opt-outs; no default
  change yet.
- **Follow-up (proposed, not yet run):** combined arm S3 −belief −chain on
  the 256-seed block paired vs `build/simsweep_v4_3k_256.csv` (A2's CI
  versus ctl touches 0 at n=128; the 256 run decides whether S3−belief−chain
  replaces S2@3k as the recommended combat search); particle-count knob
  (64 → 128) under the same stack.
- **Artifacts:** per-seed CSVs `build/s3ablate_{s2_ref,s3_ctl,s3_nobel,
  s3_noprune,s3_nochain,s3_nolive,s3_crn}_3k_128.csv`; server log
  `/tmp/s3ablate.log` on `sts-test`; `run_s3_ablate.sh`; decision log
  `2026-08-05-s3-ablation.md`.
- **2026-08-05 re-verification (code review):** `bestbench` appends without
  deduplicating, and the first aggregation of this section used
  `s3ablate_s2_ref`/`s3ablate_s3_ctl` files polluted by an earlier partial
  run (append-duplicated rows; issue 46). Both arms were re-run clean on the
  post-fix binary with `run_s3_ablate.sh`'s new per-arm truncation:
  A0 43.8% (56 wins) and A1 49.2% (63 wins) reproduce exactly; the A3/A5
  "bit-identical" claims were re-verified per-seed against the clean A1
  (128/128 seeds, all columns except `sec`). All §106 numbers stand. Also
  re-verified with the corrected `STS_S3_LIVE=0` semantics (issue 41: the
  ablation now truly drops the live-valid filter, invalid edge ends the
  battle like Searcher2) and the CRN once-per-searcher guard (issue 42);
  results unchanged at these seeds.

## 103. Searcher2 + PVNet policy head as PUCT prior @3k sims — exact tie with GBM prior at 8x cost (2026-08-05)

- **Question:** the §102 gate only tested PVNet priors under Searcher3; does
  the PVNet policy head work as the PUCT prior under the *recommended*
  Searcher2? (Searcher2 previously ignored `STS_PVNET` entirely.)
- **Change:** `BattleScumSearcher2` now uses the PVNet policy head for edge
  priors when `STS_PVNET` is loaded (mirroring Searcher3's preference order;
  GBM fallback otherwise; `STS_PVNET_VALUE_ONLY=1` keeps GBM). PUCT gate
  extended accordingly (`src/sim/search/BattleScumSearcher2.cpp`:
  expansion condition, `usePuct`, `computeEdgePriors` PVNet branch).
- **Setup:** local WSL (12 threads), fair, A0, 3,000 sims, 128 seeds
  126700–126827, default OOC stack, tracked parity-fixed PVNet
  (`05d80929...`) vs tracked GBM prior (`policy_trees_c.txt`,
  `24793bd3...`), `OPENBLAS_NUM_THREADS=1`.
- **Result (paired, same binary):**
  - S2+GBM: **27/128 = 21.1%**, floor 37.3, HP 8.1, 24.3 cpu-sec/run
    (`build/pvnetgate_s2_true_3k_128.csv`)
  - S2+PVNet: **27/128 = 21.1%**, floor 38.2, HP 8.7, 199.2 cpu-sec/run
    (`build/pvnetgate_s2_pv0_3k_128.csv`)
  - dWin **+0.0pp** CI [−6.9, +6.9]; discordant 20 (10 wins each way);
    dFloor −0.9 CI [−2.6, +0.7]. An exact statistical tie at **8.2x compute**.
- **Offline prior diagnostics** (new `policystats` mode in
  `apps/one_combat.cpp`, cross-validated against Python/GPU: model-entropy
  matches to 4 decimals; 10,744 val groups, identical grouping):
  - teacher agreement: PVNet top-1 0.409 / CE 1.444 vs GBM top-1 0.388 /
    CE 1.565 — the PVNet head is *marginally better*, not worse;
  - prior entropy: PVNet 1.431 vs GBM 1.565 (PVNet slightly sharper);
  - **the two priors agree on the best action only 41.6% of the time**, yet
    the bot results are identical — at 3k sims the PUCT prior barely matters.
- **Interpretation:** the PVNet policy head is a *correctly working, equal-
  quality* prior; the §102 gate verdict stands — no same-cost channel. The
  mid-run 11–16% readings were small-sample noise (a 200-sim × 16-seed smoke
  also looked bad; consistent with priors mattering more at low sims, but
  untested). The 8x per-sim cost is structural (per-node transformer
  forward), so S2+PVNet stays experimental-off.
- **Artifacts:** `build/pvnetgate_s2_pv0_3k_128.csv`; `policystats` mode:
  `./build/one_combat policystats <gbm.txt> <fair_p.csv> [val] [pvnet.txt]`.

## 107. S3 particle × sims sweep — belief-off variants promoted: S3−belief−chain = 60.2% @3k / 57.4% @1k (2026-08-05)

- **Goal:** the §106 ablation left two open knobs: the particle count was
  hardcoded at 64 in every recorded S3 result, and the combined
  S3−belief−chain variant was untested. Sweep particles × sims for the two
  winning variants and confirm on the 256-seed block.
- **New code:** `STS_S3_PARTICLES` env (default 64; was hardcoded at the two
  `BattleScumSearcher3` construction sites in
  `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`/`playoutBattle`);
  parsed in `apps/one_combat.cpp::main`, banner gains `S3-particles=NNN`.
  Bit-identity gate passed: env-unset vs `STS_S3_PARTICLES=64` identical,
  and the grid's re-run anchor `p64_s3k_belf` is per-seed identical to the
  recorded §106 A2 arm (0 won diffs on 128 seeds).
- **Setup:** GCP `sts-test` (24 threads), fair, A0, V4 full gate stack
  (tok net sha256 `05178ec8…9e1ea` + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1,
  margin 1.0, MAP off), policy prior auto-load, no vnet/PVNet/dist;
  `OPENBLAS_NUM_THREADS=1`; seeds 126700–126827 (grid) and 126700–126955
  (confirmation); `run_s3_particles_sweep.sh` / `run_s3_particles_sweep2.sh`.
- **Batch 1 grid (128 seeds, paired vs recorded A2@64/3k = 57.8%):**

  | arm | particles | sims | wins | win% | floor | HP | cpu-sec/run |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | S3−belief | 16 | 1k | 70 | 54.7 | 43.3 | 32.7 | 10.6 |
  | S3−belief | 64 | 1k | 74 | 57.8 | 43.8 | 34.7 | 10.3 |
  | S3−belief | 256 | 1k | 71 | 55.5 | 42.9 | 35.2 | 10.3 |
  | S3−belief | 16 | 3k | 77 | 60.2 | 44.3 | 39.2 | 30.7 |
  | S3−belief | 64 | 3k | 74 | 57.8 | 43.6 | 37.4 | 30.8 |
  | S3−belief | 256 | 3k | 73 | 57.0 | 44.2 | 36.5 | 31.7 |
  | S3−belief−chain | 16 | 1k | 70 | 54.7 | 42.6 | 34.1 | 9.3 |
  | S3−belief−chain | 64 | 1k | 75 | 58.6 | 44.0 | 37.1 | 10.5 |
  | S3−belief−chain | 256 | 1k | 73 | 57.0 | 42.8 | 35.4 | 9.9 |
  | S3−belief−chain | 16 | 3k | 76 | 59.4 | 44.1 | 34.0 | 31.1 |
  | S3−belief−chain | 64 | 3k | 77 | 60.2 | 44.9 | 37.5 | 30.7 |
  | S3−belief−chain | 256 | 3k | 78 | **60.9** | 44.1 | 36.7 | 30.0 |
  | E1 S3 ctl (belief ON) | 256 | 3k | 65 | 50.8 | 41.8 | 29.5 | 41.2 |

  The grid is **flat in particles** (16/64/256 within noise at every
  sims×variant cell) and **flat-ish in sims** (1k→3k worth ~+2-3pp for the
  belief-off arms). **E1: belief ON at 256 particles = 50.8%, still −6.2pp
  vs belief-off at the same count — the §106 belief harm is a design
  property, not a 64-particle capacity limit.** Belief-ON arms are also the
  slowest (41.2 cpu-sec/run; reweighting cost).
- **Batch 2 (E2 + 256-seed confirmation, paired vs the recorded §99
  reference `build/simsweep_v4_3k_256.csv`, 116/256 = 45.3%):**

  | arm | seeds | sims | wins | win% | floor | HP | cpu-sec/run | win Δ vs ref (CI) |
  |---|---:|---:|---:|---:|---:|---:|---:|---|
  | E2 S3−b−c, 256 p | 128 | 4k | 80 | 62.5 | 45.3 | 37.9 | 41.6 | +18.8 [+8.6,+28.9] vs S2@3k slice |
  | S3−b−c, 64 p | 256 | 1k | 147 | 57.4 | 43.4 | 36.9 | 9.8 | **+12.1 [+4.9,+19.3]** |
  | S3−b−c, 256 p | 256 | 3k | 154 | **60.2** | 44.2 | 39.3 | 29.0 | **+14.8 [+7.9,+21.8]** |

- **Verdict:** ✅ **promotion gate passed — S3−belief−chain replaces S2@3k
  as the recommended combat search.** On the same 256 paired seeds as §99:
  **60.2% (+14.8pp, CI excluding zero; floor +1.3, HP +14.0) at 3k sims/256
  particles** (29.0 cpu-sec/run) is the win-rate point, and **57.4%
  (+12.1pp, CI excluding zero) at 1k sims/64 particles** (9.8 cpu-sec/run,
  3.1× cheaper) is the compute-efficient point. The 4k extension (E2:
  +1.6pp vs 3k) is within noise — 3k stays the operating point; the 1k
  point delivers most of the gain at a third of the cost. Particle count
  64↔256 is free either way. E1 closes the belief-capacity hypothesis.
  S2+PVNet (§103, parallel session) and S3+PVNet (§102) both remain
  rejected at the operating point; the win comes from the searcher
  configuration, not a combat model.
- **Artifacts:** per-seed CSVs `build/pt_sweep_{p16,p64,p256}_s{1k,3k}_
  {belf,both}_128.csv`, `build/pt_sweep_p256_s3k_ctl_128.csv`,
  `build/pt2_{p256_s4k_both_128,p64_s1k_both_256,p256_s3k_both_256}.csv`;
  server logs `/tmp/s3sweep.log`, `/tmp/s3sweep2.log` on `sts-test`;
  `run_s3_particles_sweep.sh`, `run_s3_particles_sweep2.sh`; decision log
  `2026-08-05-s3-particles-sweep.md`. Future gate rounds pair against
  `build/pt2_p256_s3k_both_256.csv` (win point) or
  `build/pt2_p64_s1k_both_256.csv` (efficient point).

- **Caveats and cross-references:** (1) the promoted configuration uses the
  tracked V4 token net, which the 2026-08-05 code review flags for a training
  bug (tok glob stats columns 44–49, issue 36 — retrain pending, GPU-gated;
  see `docs/knowledge-base/evaluation/rerun-ledger.md`). Every gate-stack
  number since §76 — including the §99 reference this section pairs against —
  carries that caveat; the paired deltas above are bug-identical on both
  sides. (2) §106's A0/A1 arms and the A3/A5 bit-identity claims were
  re-verified by the code review with clean re-runs and corrected
  `STS_S3_LIVE=0` semantics (issues 41/42/46); results unchanged. (3) the
  `bestbench` append-without-dedup trap (issue 46) is now guarded by
  per-arm truncation in `run_s3_*.sh`; the §107 CSVs were verified
  seed-unique.

## 108. V4 fixed-stats retrain (issue 36) — S2-paired negative, S3−belief−chain paired SIGNIFICANT negative; deployed model stays (2026-08-05)

- **Goal** (rerun-ledger row 36): re-derive the V4 token net after the
  issue-36 fix (glob slots 44–49 are derived features but were standardized
  with deck-count statistics) and test whether the corrected model replaces
  the deployed `ooc_strategic_tok_final.native` (sha256 `05178ec8…9e1ea`).
- **Training:** `train_strategic_tok.py`, rung 4, `STRAT_EPOCHS=60`, grouped
  80/20 seed 0, CUDA, on the same `build/strategic_tierb.csv` (3,057,708 rows
  / 4,650 seeds) the deployed model used; fixed stats (issue 36). New
  artifact `selfplay/models/ooc_strategic_tok_fixed.{pt,native}`
  (native sha256 `9a54c28a…`; export parity max err logit 9.16e-06 / value
  1.03e-05 / Q 2.47e-05).
- **Held-out (best epoch, vs recorded V4@60ep §75):** val_pol_ce 0.4854 (vs
  0.486), policy_top1 0.796 (vs 0.793), margin 11.14 (vs 10.32), value_mae
  10.18 (vs 10.18), q_top1 0.296 (vs 0.290), q_mae 16.41 (vs 16.22) — slightly
  better ranking, marginally worse Q calibration.
- **Paired gates (fair, A0, 3k sims, full V4 gate stack, margin 1.0):**

  | pairing | new | old ref | Δ win (McNemar p) | floor Δ | HP Δ |
  |---|---|---|---:|---:|---:|
  | S2 @128 (vs `s3ablate_s2_ref_3k_128.csv`, 43.8%) | 53/128 (41.4%) | 56/128 | −2.34pp (p=0.77) | −1.39 | −6.61 |
  | S2 @256 (vs `simsweep_v4_3k_256.csv`, 45.3%) | 106/256 (41.4%) | 116/256 | −3.91pp (p=0.36) | −2.07 | −7.53 |
  | **S3−belief−chain @256/256p (vs §107 `pt2_p256_s3k_both_256.csv`, 60.2%)** | **131/256 (51.2%)** | 154/256 | **−8.98pp (p=0.028)** | −3.29 | −7.86 |

- **Verdict:** ❌ the corrected-stats retrain is a paired negative under every
  search; the negative is **statistically significant under the now-recommended
  S3−belief−chain** (p<0.05, 23-seed swing). The issue-36 normalization was
  wrong but *accidentally beneficial*: standardizing the six derived globs
  with their own scale moved the Q-head ranking off the deployed optimum.
  Held-out CE gains again do not transfer (consistent with §75/§80/§100).
  **Decision: the deployed artifact (05178ec8) stays; `ooc_strategic_tok_fixed`
  is archived as a falsified retrain.** The issue-36 fix stays in the trainer
  (correctness); any future V4 retrain should treat the derived-glob scale as
  an active hyperparameter and gate it (paired S3−belief−chain) before
  deployment.
- **Artifacts:** `selfplay/models/ooc_strategic_tok_fixed.{pt,native}`
  (tracked native; .pt stays local per convention), `build/v4fix_128.csv`,
  `build/v4fix_256.csv`, `build/v4fix_s3_256.csv`,
  `/tmp/opencode/v4_retrain.log`.
- **Post-hoc (2026-08-09, §108 synthesis):** the S3−belief−chain gate ran
  with the pre-§113 enumerator (commit 619c12c) whose battle-skip exploit
  (zero valid edges at WARCRY/GAMBLE CARD_SELECT → UNDECIDED break →
  rewards/advance) inflated both arms. The 60.2% reference is invalidated
  (§113; honest re-baseline 42.6–44.5% on the same block); the v4fix arm's
  skip contamination was never instrumented and is plausibly model-dependent.
  The "statistically significant (p=0.028)" claim therefore rests on a
  confounded measurement. The only valid honest evidence is the S2 pairings
  (−2.34pp @128 p=0.77, −3.91pp @256 p=0.36 — directionally negative, n.s.).
  The deployed-model-stays decision is unchanged; this note clarifies the
  evidence quality. The §108 retrain also fixed only one of two known trainer
  bugs (the glob-block feature-order skew, discovered 2026-08-09, was still
  present in both models); the interaction has never been tested.

## 109. Terminal-leaf run-value bonus (cross-combat setup) — infrastructure in, smoke only; no policy claim yet (2026-08-05)

- **Goal:** let combat search price the post-combat run state at terminal
  victory leaves, so cross-combat setup decisions (stall one turn so the
  Happy Flower counter ends charged for the next fight) become selectable.
  Mechanism: search::g_terminalBonus hook in
  BattleScumSearcher3::evaluateTerminal; one_combat arms it per battle
  (	ermWinArmForBattle/	ermLeafBonus) building one base rich row per
  fight (hidden future fights resampled from the act pool, ossId/

extEliteId/
extFight*/
emElites/
emFights parity-excluded) and
  patching the exitBattle-transferred fields by index; bonus =
  w * v_win_trees.txt P(win). Flags STS_TERM_WIN=1, STS_TERM_WIN_W
  (100), STS_TERM_WIN_HIDDEN=resample|zero. Decision log
  2026-08-05-terminal-leaf-run-value-bonus.md.
- **Stage 0 mechanics test:** ./build/test happy_flower <seed> PASS — relic
  counter ticks once at battle start plus once per turn start, end counter =
  (entry + 1 + bc.turn) mod 3, updateRelicsOnExit write-back, counter 2 at
  battle start charges +1 energy.
- **Research finding:** the deployed win tree has ZERO counter sensitivity —
  none of the counter-relic features split anywhere: `r26` (Happy Flower),
  `r30` (Incense Burner), `r31` (Ink Bottle), `r35` (Lizard Tail), `r44`
  (Nunchaku), `r52` (Pen Nib), `r68` (Sundial), `r131` (Neow's Lament) are
  each selected among its 448 features with 0/1060 tree splits (`r32`
  Inserter unselected). The bonus currently prices HP/gold/potions; counter
  pricing needs a counter-aware terminal model — generic across all counter
  relics, not Happy Flower only (follow-up).
- **Parity:** patched rich row == full
ichFeatureVec on a real post-combat
  copy (hidden features zeroed in both), 0 mismatches on 4-seed runs.
- **Determinism:** two identical STS_TERM_WIN=1 runs (4 seeds, 100 sims)
  agree on every per-seed game column; only wall-clock sec differs.
- **Smoke A/B** (16 seeds 126700–126715, asc 0, 300 sims, STS_FAIR=1,
  S3−belief−chain, 8 threads, native floor/win trees, policy prior auto-load;
  per-seed CSVs uild/termwin_off.csv / uild/termwin_on.csv):

  | arm | win | floor | end hp | cpu-sec/run |
  |---|---|---:|---:|---:|
  | bonus off | 4/16 (25.0%) | 31.4 | 13.7 | 14.37 |
  | bonus on (w=100) | 3/16 (18.8%) | 29.0 | 10.8 | 25.21 |

  **Verdict: smoke only — 16 seeds is noise, no win-rate claim.** The bonus
  demonstrably changes play (fires on victory leaves; result columns differ)
  and costs ~+75% cpu at 300 sims (one 1060-tree walk per terminal leaf) —
  both are Stage-2 tuning targets (paired benchmark, `STS_FORCE_RELIC` for a
  guaranteed Happy Flower, `STS_TERM_WIN_W` sweep, stall telemetry, cost
  reduction). Stage 3: counterfactual terminal model branching EVERY owned
  counter relic 0/1/2 (one at a time, `finishOocCounterfactual` labels).

## 110. C_psi counter-sensitivity probe — the neural surrogate DOES price the counters (correct sign, monotone); wired as STS_TERM_WIN_EVAL=cpsi (2026-08-05)

- **Question:** the deployed GBMs split on none of the counter-relic features
  (V_win/V_rich: 0/1060 and 0/1256 splits on r26/r30/r31/r35/r44/r52/r68/
  r131). Do any OTHER trained models price the counters? Candidates: C_psi
  (no-peek next-fight survival transformer — the only model whose labels are
  the NEXT combat's outcome, with all 8 counters as explicit scalars 3..10 in
  uildCpsiEntry), V3/V4 strategic nets, PVNet (no counter slots), V_combat
  (artifact not on this machine).
- **New code:** cpsictr mode + STS_CPSI_CTR_PROBE=1
  (pps/one_combat.cpp::cpsiCounterProbeAtState/cpsiCtrProbeReport): at
  every post-combat state of
unFullRunOOC runs, for each counter relic the
  run owns, re-predict C_psi with that relic's counter scalar set to each
  value 0..k-1 and accumulate the mean ΔP(death)/ΔP(win) vs the state's own
  counter, averaged over the six fixed probe encounters (TWO_LOUSE/GREMLIN_NOB/
  LAGAVULIN/THREE_SENTRIES/SLIME_BOSS/THE_GUARDIAN — same slots as
  probe_cpsi.py). Deterministic (5-seed double-run identical).
- **Results (400 seeds 126700–127099, asc 0, 100 sims, 1,433 post-combat
  states; mean ΔP(death) at the charged counter value vs state's own base):**

  | relic | states | charged ctr | ΔP(death) | ΔP(win) |
  |---|---|---:|---:|---:|
  | HAPPY_FLOWER | 194 | c2 | **−0.0023** | +0.0020 |
  | INCENSE_BURNER | 67 | c5 | **−0.0072** | +0.0086 |
  | INK_BOTTLE | 276 | c9 | **−0.0066** | +0.0065 |
  | NUNCHAKU | 297 | c9 | **−0.0078** | +0.0077 |
  | PEN_NIB | 428 | c9 | **−0.0118** | +0.0114 |
  | SUNDIAL | 171 | c2 | **−0.0052** | +0.0046 |
  | INSERTER | 0 | — | (Defect-only, expected 0 for Ironclad) |

  Every relic is **correctly signed and monotone** (fully charged → lowest
  next-fight death; the 200-seed 626-state run showed the same pattern).
  The observational confound (counter correlates with previous fight length)
  would push the model the WRONG way; the learned mechanism effects dominate.
  Caveat: this is learned association, not proof of causality — the Stage-3
  counterfactual datagen remains the ground-truth validation.
- **Decision:** wire C_psi in as a terminal-leaf evaluator
  (STS_TERM_WIN_EVAL=cpsi, default win): 	ermLeafBonus builds the
  no-peek entry from the patched rich row (cpsiEntryFromRich mirrors
  uildCpsiEntry — no GameContext copies, no hidden-info features by
  construction) and returns w * P(win of next fight) with the current
  fight's encounter as the fixed probe encounter (a per-combat constant, so
  only the state-dependent part — HP/potions/counters — orders the leaves).
- **Cost (before runtime fix):** the scalar transformer forward was ~0.58 ms;
  cpsi-eval measured 34.5 vs 1.9 cpu-sec/run at 100 sims (16 seeds, fair,
  S3−belief−chain, w=100) — ~18x the win-tree leaf. **Runtime fix
  (2026-08-05):** `#pragma omp simd reduction` on the `linear`/`linearBatch`
  inner loops + weight-row hoisting across the token loop
  (`src/sim/search/CombatCpsiNet.cpp`; per-output math bit-identical, probe
  deltas unchanged to 4 decimals) cut the forward to ~0.20 ms (2.9x) and the
  end-to-end cpsi-eval overhead from +33.7 to +17.4 cpu-sec/run on the same
  16-seed   block (19.2 vs 35.5 cpu-sec/run) — ~9x the win-tree leaf. The
  erf-GELU hypothesis was measured and rejected (a fast-erf LUT build changed
  nothing); the win is the omp-simd reduction (~1.9x alone: 577→300 us) plus
  the weight-row hoisting across the token loop (another ~1.5x: 300→201 us),
  both bit-identical per-output. Benchmark at the 1k-sim operating point
  (est. ~50 min for 128 seeds on 8 threads). 16-seed behavioral smoke: same
  win% 18.8, floor 27.7 vs 30.8, end HP 13.4 vs 6.2 (bonus-on prices
  next-fight survival; noise-level sample, direction as expected).
- **Artifacts:** probe output (400 seeds) in the run transcript; per-seed
  smoke CSVs uild/cpsictr_{off,on}.csv; cpsictr mode + STS_CPSI_CTR_PROBE
  env; decision log addendum 2026-08-05-terminal-leaf-run-value-bonus.md.


## 111. OOC fight-rollout lookahead re-gated on the current stack: greedy and margin-gated searched-checkpoint oracle, win-GBM terminal term — falsified (2026-08-05)

- **What:** re-test the §66 "copy the run, actually simulate the next combat
  checkpoints, evaluate the state, come back" oracle as a **live** policy on
  the §107 recommended stack (S3−belief−chain + V4 one-ply gate stack), with a
  new terminal state evaluator: `STS_ACT_FIGHT_PROBE_TERM_WIN=w` prices each
  option's post-final-checkpoint state with the native win GBM
  (`g_winNet.predict(richFeatureVec(local))`, P(win) units, blended into the
  HP-safety utility), and `STS_ACT_FIGHT_PROBE_MARGIN=m` (best−second ≥ m else
  fallback stack) is the deployment gate. Both flags default off; unset
  behavior byte-identical (verified structurally: term/margin blocks are
  unreachable at defaults).
- **Setup:** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=256`, V4 tok gates REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1,
  margin 1.0, asc 0, 24 threads, oracle = ALL_OOC=1 MAX_CHECKPOINTS=3
  CHECKPOINT_SIMS=400,200,100 FUTURES=2. Seeds 126700–126955, recorded block.
- **Baseline reproductions:** §107 stack @3k = **60.2% win / 44.2 floor /
  39.2 HP** (154/256, matches §107 exactly; `gate_2026-08-05_termlookahead_base.csv`);
  @1k = **56.6% / 43.0 / 35.2** (fresh same-binary pairing reference,
  `gate_2026-08-05_margin_base1k.csv`; §107's 1k point was 57.4% @64p).
- **Arm 1 — greedy (ungated) oracle + TERM_WIN=1.0 @3k:** **0/13 paired wins
  vs baseline 8/13**; all 8 baseline full clears lost; candidate died at
  act-2 floors 22–33 (`gate_2026-08-05_termlookahead_cand.csv`). Run stopped
  at 13 seeds (7+ h projected); the pattern matches §66j/§66m/§67.
- **Attribution (seed 126706):** oracle+TERM_WIN and oracle−TERM_WIN both die
  at floor 22 / fight 14; baseline wins — the failure is the **oracle's
  decision selection, not the terminal term**; TERM_WIN is a ~10–15%
  perturbation of an HP-safety-dominated utility (`diag_126706_ora.nohp.csv`).
- **Arm 2 — margin-gated oracle m=0.15 + TERM_WIN=1.0 @1k:** at n=62 paired
  seeds (run stopped to save compute): candidate **19/62 (30.6%) vs baseline
  33/62 (53.2%)**, paired floor −2.24, paired score −4.50 (SE 2.33),
  reversals 8 cand-better / 22 base-better (`gate_2026-08-05_margin_cand15.csv`,
  62 rows). Estimate stable at ≈ −4.5 since n≈28 with no trend toward zero;
  extrapolated 256-seed CI ≈ [−6.8, −2.2]. A positive flip would need the
  remaining 194 seeds to outrun baseline by ~5σ — stopped at 62.
- **Verdict:** ❌ falsified as a live full-run policy, with and without the
  margin gate. The oracle's HP-safety/win argmax replaces the margin-gated
  one-ply Q stack on every (gated) decision and is net-negative; the marginal
  damage scales with firing rate (ungated 0/13, m=0.15 ~−22pp at n=62). The
  win-GBM terminal term cannot rescue it (failure is selection, not pricing).
  The oracle machinery stays opt-in (probe flags default off); its validated
  role remains offline teacher/ranker (§66k/§66l/§67), not live policy.
- **Artifacts:** CSVs above (local copies in the session temp dir; GCP
  `/home/philippherrmann/sts_sweep/build/`); logs
  `gate_2026-08-05_{termlookahead_base,termlookahead_cand,margin_base1k,margin_cand15}.log`.
  Code: `apps/one_combat.cpp` `g_actFightProbeTermWin`, `g_actFightProbeMargin`,
  `checkpointedActFightUtility` terminal term, `actFightProbeAllOocPolicy` gate.
- **Cost:** baseline 60.2%@3k = 30.8 cpu-s/run (344 s wall); ungated oracle
  ≈ 350–1430 cpu-s/run (13 seeds in 26 min); margin-gated ≈ 62 seeds in 99 min
  → ~5.1 h projected for 256; stopped to save compute.

## �112 CARD_SELECT action-parity fix and the multi-select search regression (2026-08-05, GCP)

- **What:** Phase-1 workstream � make Searcher2/Searcher3/the canonical
  `search::Action::enumerateCardSelectActions` enumerate exactly what the
  simulator validates, pinned by a new exhaustive parity test
  (`./build/test cardselect_parity`, `apps/test.cpp::testCardSelectParity`:
  21 tasks � 3 variants + 3 PLAYER_NORMAL states; 48/63 states failed before,
  all pass after; deterministic). Pre-fix S3 default branch was
  `for (i < pickCount)` (wrong pool for WARCRY/FORETHOUGHT/HEADBUTT/
  SECRET_*/DUAL_WIELD/etc., no EXHUME filter); S2+canonical missed HOLOGRAM/
  MEDITATE/NIGHTMARE/RECYCLE/SETUP/SEEK and emitted one bogus empty subset for
  EXHAUST_MANY/GAMBLE. Fix: canonical enumerator extended to the full validity
  contract; S2/S3 delegate to it. New `STS_MULTISELECT_MODE=all|single|none`
  (default all) prunes the multi-select space without emitting invalid actions.
- **Setup (all arms):** GCP `sts-test` (24 threads), fair, A0, 1,000 sims,
  `STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256`, V4
  tok gates REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, margin 1.0, seeds
  126700�126955 (recorded block), �111 base config; trees hash-verified against
  the tracked identities before the runs.
- **Control:** original 619c12c sources rebuilt on GCP = **56.6% / 43.0 / 35.2**
  � **bit-identical pairing with the �111 `gate_2026-08-05_margin_base1k.csv`
  reference (0/256 mismatches)**, confirming the GCP tree/config reproduces the
  baseline exactly (`build/control_1k_256.csv`).
- **Candidate (full fix):** **39.5% / 41.0 / 18.9** � paired **-17.2pp
  (SE 3.1)**, 14 cand-better / 58 base-better (`build/cand_1k_256.csv`).
- **Bisect:** S3-only change (new canonical+S3, control S2), seeds
  126700�126763 @1k: **28/64 = 43.8% vs control 36/64 = 56.3%** on the same
  subset (`build/s3_only_1k_64.csv`) � the S3 enumeration change alone is the
  regression driver; S2-only bisect not yet run.
- **Mechanism (Inference):** GAMBLE (Gambler's Brew) / EXHAUST_MANY (Elixir,
  Purity) now expand up to 1023 children with uniform policy priors
  (`combatFillActionFeatures` gives identical features to every subset) at a
  fixed 1000-sim budget ? near-random subset choice; pre-fix S3 emitted no
  valid edges there so the old agent effectively never used those
  potions/cards. `combatFillActionFeatures` does not read out of bounds for
  MULTI_CARD_SELECT (verified).
- **Verdict:** enumeration correctness fix is sound and stays (issue 47
  closed); full-subset search scale is not deployable at 1k sims (issue 48
  open). `STS_MULTISELECT_MODE=single`/`none` A/B pending; promote the winner
  and re-gate at 256 seeds @1k and @3k vs the �107 references before any
  default change. Note: the S2 default binary is affected too (its GAMBLE/
  EXHAUST_MANY enumeration changed from 1 bogus action to full subsets).
- **Artifacts:** `build/{control_1k_256,cand_1k_256,s3_only_1k_64,
  base_1k,base_3k}.csv` (local copies; GCP `/home/philippherrmann/sts_sweep/
  build/`); decision log `2026-08-05-cardselect-parity-fix.md`; issues
  47 (closed) / 48 (open).
- **Cost:** ~2 min wall per 256-seed @1k arm; the GCP tree currently has the
  control files installed � re-sync `src/sim/search/{Action.cpp,
  BattleScumSearcher3.cpp}` before the next GCP run.

## �113 CARD_SELECT parity follow-up: the �112 'regression' was a control battle-skip exploit; parity fix is correct and deployed (2026-08-05, GCP + local)
- **What:** continuation of �112 (plan T1-T5). T2 mode A/B and T3 S2-only
  bisect were run as planned; both exposed a contradiction with �112's
  mechanism hypothesis (multi-select subset expansion), and the follow-up
  bisect found the true cause: **the �112 control enumerator skip-wins
  battles at CARD_SELECT states, inflating every control/S3 measurement**.
- **Mechanism (verified by code trace + instrumented runs):** control S3's
  `enumerateActionsForNode` default branch emitted
  `SINGLE_CARD_SELECT 0..pickCount-1`; `WarcryAction` and `GambleAction`
  (Actions.cpp:872-888, 981-986) never set `pickCount`, so at WARCRY and
  GAMBLE CARD_SELECT states the enumerator emitted **zero edges**. The
  agent's root pick (`ScumSearchAgent2::s3PickRootAction`) then found no
  valid action -> `have=false` -> `break` -> battle loop exited with
  **UNDECIDED** outcome -> `BattleContext::exitBattle` treated non-loss as
  victory (`g.regainControl()` -> rewards + floor advance). At the act-3
  boss this chain produced `PLAYER_VICTORY` without killing the boss.
  Predicate tasks (DUAL_WIELD, SECRET_TECHNIQUE/WEAPON) and EXHAUST_MANY
  (Elixir/Purity) also emitted invalid/zero edges at times -> same skip.
  Instrumented counter (`STS_DEBUG_BATTLE_BREAKS`): **41 breaks / 8 seeds
  (27 GAMBLE, 13 WARCRY) on control S3; 164 breaks / 256 seeds**.
- **Decisive A/B (same control-S3 binary, 8 seeds @1k, only break handling
  changed):** silent skip = **62.5%** win; break->PLAYER_LOSS = **0.0%**
  win / floor 30.0. The entire 'control' win rate was the exploit.
- **S2 control has NO skip** (its GAMBLE case emitted a valid empty
  `MULTI_CARD_SELECT 0`; other cases complete for Ironclad tasks): 0 breaks
  on 16 seeds. The exploit is **S3-specific**; **�107 (60.2%), �111
  (56.6%), �112 (56.3%), and the �99/�102-�105 S3 arms are
  invalidated** as honest baselines. �99's headline 45.3% used default
  Searcher2 and survives (S2 control verified break-free).
- **Fix (deployed):** (1) canonical enumerator `search::Action::
  enumerateCardSelectActions` (issue 47, already committed b48cb40) - the
  fixed enumerator produces **0 breaks** (verified on 256 seeds @1k and
  @3k); (2) new run-level guard: `BattleContext::exitBattle` now treats an
  UNDECIDED outcome as PLAYER_LOSS instead of granting rewards. Both S2/S3,
  fair/non-fair paths are covered by the single exitBattle choke point.
- **Honest re-baselines (256 seeds 126700-126955, fair, A0, S3-belief-chain
  off, 256 particles, V4 gate stack, 24 threads, canonical enumerator +
  fix):**
  - honest control S3 (fix only, control enumerator): **9.0% / 26.6 floor /
    47.6 hp @1k** (`build/honest_ctl_1k_256.csv`)
  - **honest fixed agent: 36.3% / 40.5 / 20.3 @1k**
    (`build/honest_fix_1k_256.csv`), **42.6% / 42.2 / 23.1 @3k**
    (`build/honest_fix_3k_256.csv`) - the parity fix is worth **+27.3pp
    over honest control @1k**; the �112 'regression' was the removal of
    the skip exploit, not a search-quality loss.
  - `STS_MULTISELECT_MODE=single/none` with a pickCount-capped single-select
    pool (experimental extension, not committed): 31.6% / 30.5% @1k -
    **negative vs canonical `all` (36.3%)**, so the cap extension is
    rejected and the committed canonical enumerator (full validity
    contract) stays the deployment default.
- **Verdict:** issue 48 closed - there is no multi-select regression; the
  full-subset expansion is correct and necessary, and the �112 delta was
  the removed exploit. `STS_MULTISELECT_MODE` remains an opt-in
  search-scale knob. The exitBattle guard is a general correctness fix:
  any future enumerator gap now costs a loss, never a free win.
- **Artifacts:** `build/{honest_ctl_1k_256,honest_fix_1k_256,
  honest_fix_3k_256,capped_single_1k_256,capped_none_1k_256}.csv` (GCP
  `~/sts_sweep/build/`, local copies); decision log
  `2026-08-05-cardselect-parity-fix.md` (updated); issues 47 (closed) / 48
  (closed); code diff: `BattleContext.cpp` exitBattle guard,
  `ScumSearchAgent2.cpp` env-gated break telemetry, `apps/test.cpp`
  parity-mode pin.
- **Cost:** ~2 min wall per 256-seed @1k arm; ~10 min @3k on GCP sts-test.

## �114 Phase 2 (observation-keyed search + belief fix): observation expansion neutral, obs-keyed descent falsified (2026-08-05, GCP + local)
- **What:** the plan's Phase 2 (P0 after T5) in three parts: (1) expand
  `CombatObservation` so the identity fully determines the visible decision
  (add `inputState` + card-select context: task/pickCount/canPickZero/
  canPickAnyNumber/offer cards); (2) key search children by
  `Edge{action -> child[obsHash]}` so distinct visible outcomes keep
  separate statistics; (3) remove the `belief.update` calls inside
  `step()` and update the belief only at the agent boundary.
- **Part 1 (observation expansion): NEUTRAL, kept as a correctness fix.**
  Previously a PLAYER_NORMAL state and a CARD_SELECT state (or two card-
  select screens with different tasks/offers) could share an observation
  identity. Now `inputState` + `cardSelectInfo` are hashed and compared.
  `obs_identity` extended to pin the decision context; `seed_contract`
  extended to compare two full 200-sim searches (action + obsHash + visit
  counts must match). 256 seeds @1k vs the �113 honest reference
  (`honest_fix_1k_256.csv`): **37.5% / 39.8 floor / 20.0 hp vs 36.3% /
  40.5 / 20.3 - +1.2pp, 36 p2-only vs 33 ref-only flips on 69 flipped
  seeds; within noise**. 64-seed subset: 36.5% vs 40.6% (-4.1pp, 5v7
  flips). Kept because the identity contract is now correct at zero
  measured cost.
- **Part 2 (obs-keyed descent): FALSIFIED and reverted.**
  `descendKeyed` appended a new edge whenever a simulation's post-action
  observation differed from the claimed one. With particle determinization
  the observations diverge at almost every level, so the tree grows
  linearly with simulations instead of logarithmically (100 sims ->
  300-600 nodes), starving the budget and collapsing search depth.
  Isolated A/B at identical budget (100 sims/8 particles/2 seeds, local):
  baseline floor 33.0, observation-expansion-only floor 31.5, full
  obs-keyed descent floor 11.0 (catastrophic). 64-seed @1k on GCP with
  the keyed descent: 0% win / floor 7.1 (also 0% / 9.8 at 1000 sims).
  Reverted the edge-keying; the observation identity expansion alone is
  neutral (Part 1).
- **Part 3 (belief fix): kept, gated.** In-step `belief.update` calls
  removed from `step()` (both the expansion and internal-branch sites);
  the belief is now updated only at the agent boundary after a committed
  action in the non-fair S3 path (`g_s3Belief`-gated). The fair path
  builds a fresh searcher/belief from the real state each decision, so it
  is inherently live. Inert in the recommended config (`STS_S3_BELIEF=0`
  default, fair path).
- **Verdict:** Phase 2 delivered the identity correctness fix (neutral,
  kept) and the belief fix (gated); the observation-keyed search tree is
  falsified at fixed budgets for this particle determinization - the
  recommended configuration and headline (42.6% @3k / 36.3% @1k, �113)
  are unchanged. The plan's Phase 2 item is closed with this verdict; the
  plan doc is updated accordingly.
- **Artifacts:** `build/p2_obs_expand_1k_256.csv` (GCP + local),
  `build/p2_obs_expand_clean.csv`; decision log
  `2026-08-05-phase2-observation-search.md`; code diff:
  `CombatObservation.{h,cpp}` (identity fields), `apps/test.cpp`
  (`obs_identity` decision-context cases, `seed_contract` full-search
  determinism), `ScumSearchAgent2.cpp` (agent-boundary belief update,
  `g_s3Belief`-gated).
- **Cost:** ~2 min wall per 256-seed @1k arm on GCP sts-test.

## �115 Honest-grid completion on the Phase-2 binary: efficient point (64p @1k) and @3k win point re-measured; �107-grid rerun status (2026-08-05, GCP)
- **What:** closes the rerun gaps left by the �113 invalidation on the
  current (Phase-2, e4fbb4a) binary: the efficient point (1k sims @ 64
  particles, the �107 '57.4% @1k/64p' claim) and the 3k win point
  (previously measured pre-Phase-2; Phase 2 changed the composite seed).
- **256 seeds 126700-126955, fair, A0, S3-belief-chain off, V4 gate stack,
  24 threads, current Phase-2 binary (canonical enumerator + exitBattle
  guard + expanded observation identity):**
  - efficient point: **37.5% / 39.4 floor / 20.8 hp @1k/64p**
    (`build/honest_p64_1k_256.csv`) - identical to the 256p @1k point
    (37.5%, 35v32 flips on 67 flipped seeds), confirming �107's 'flat in
    particles' finding holds on the honest stack; 64p is the efficient
    deployment point.
  - win point: **44.5% / 42.5 / 24.4 @3k/256p**
    (`build/honest_fix2_3k_256.csv`) vs the pre-Phase-2 honest 42.6%
    (75 flipped seeds: 40 new-only, 35 old-only) - Phase 2 is
    neutral-to-slightly-positive, consistent with the +1.2pp @1k shift.
- **Rerun status of the �113-invalidated set:** headline and control are
  re-baselined (honest_fix @1k/@3k, honest_ctl); efficient point now
  re-measured (this entry); the remaining invalidated measurements are the
  �106 feature-ablation deltas (belief/chain/CRN), which were never
  deployed (the recommended stack runs belief/chain off) and whose
  direction matched the �107 stack - flagged for re-derivation only if
  that research line reopens (rerun-ledger). �108's S3-paired verdict was
  already negative and its S2-paired (honest) verdict stands.
- **Artifacts:** `build/{honest_p64_1k_256,honest_fix2_3k_256}.csv` (GCP +
  local copies); baselines doc updated to the current-binary numbers.
- **Cost:** ~2 min @1k, ~10 min @3k on GCP sts-test.

## �116 Phase 3 Stage 2 (post-combat run utility): TERM_WIN terminal-leaf bonus paired benchmark - null on win rate and stall behavior, 3.1x cost; intermittent multithread crash in the opt-in path (2026-08-05, GCP + local)
- **What:** the plan's Phase 3 Stage 2: controlled paired benchmark of the
  Searcher3 terminal-leaf run-value bonus (`STS_TERM_WIN=1`, win-tree
  evaluator, W=100) vs control, both with `STS_FORCE_RELIC=HAPPY_FLOWER`
  so the cross-combat setup signal (stall to align the counter) is
  present in both arms; stall telemetry (`STS_TERM_STALL_LOG`) records the
  run-level counter each battle ends on.
- **256-seed paired benchmark (GCP, 1k sims/64 particles, fair, A0,
  S3-belief-chain off, V4 gate stack, forced Happy Flower):** control
  **37.5% / 39.4 / 20.8** (`p3_ctl_hf_1k_256.csv`) vs TERM_WIN **37.9% /
  40.8 / 20.1** (`p3_term_hf_1k_256.csv`) - **+0.4pp, 39 term-only vs 38
  ctl-only flips on 77 flipped seeds: null**. Control reproduces the
  �115 honest 64p @1k baseline (37.5%) exactly, so the forced relic
  itself does not move the win rate.
- **Stall telemetry (32 seeds, 733/731 battles, both arms):** battles
  ending with a charged Happy Flower counter (c2) 30.2% ctl vs 31.7% term
  (+1.5pp); mean turns/battle 4.60 vs 4.71 (+0.11); per-seed mean-counter
  diff +0.052 (sd 0.203) - the bonus does not measurably change stall
  behavior. This is consistent with �110: the deployed win tree has zero
  sensitivity to counter relics, so the bonus cannot price the
  counter-alignment the design targets.
- **Cost:** TERM_WIN ran at 32.4 cpu-sec/run vs 10.5 control = **3.1x
  overhead** at 1k sims (worse than the �109 estimate of +75% at 300
  sims); the per-leaf win-tree walk dominates.
- **Verdict:** Stage 2 **falsified** - no win-rate or stall-behavior
  benefit, 3.1x cost. The terminal-leaf bonus stays opt-in (default off)
  and is not promoted. Stage 3 (counterfactual terminal-value model)
  requires a counter-aware evaluator to have any signal; with the win tree
  insensitive and no measured benefit, Stage 3 stays deferred until a
  counter-sensitive terminal model exists (the �110 C_psi probe shows the
  right machinery exists but was also null at the leaf level in �109's
  smoke).
- **New issue - intermittent multithread crash in the TERM_WIN path
  (pre-existing, 6f0420d):** `STS_TERM_WIN=1` at 12 threads crashes ~2/6
  runs (segfault, 0 output lines; stall-log config 2/5; single-thread 0/5;
  ASAN 0/8). Reproduced on the Phase-1 binary (6f0420d) identically, so it
  is NOT from the Phase-2 changes. The crash occurs before the first
  banner flush, suggesting a startup/parallel-region race in the opt-in
  TERM_WIN arm (thread_local state + shared model access). Recorded as
  issue 49; needs a debugger session. Does not affect the recommended
  stack (TERM_WIN defaults off).
- **Artifacts:** `build/{p3_ctl_hf_1k_256,p3_term_hf_1k_256}.csv` (GCP +
  local); stall logs `build/p3_stall_{ctl,term}.csv`; decision log
  `2026-08-05-phase3-terminal-value-stage2.md`; issue 49.
- **Cost:** ~2 min wall per 256-seed @1k arm on GCP sts-test (GCP shut
  down after this batch per instruction).

