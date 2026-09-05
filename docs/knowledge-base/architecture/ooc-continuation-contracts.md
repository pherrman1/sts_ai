# OOC continuation contracts — rounds 6–8 (working spec)

Status: working contracts for the post-§75 wave. Each track implements its
section below; the orchestrator runs the GPU/benchmark schedule. Results get
recorded in EXPERIMENTS.md (R6 ≈ §76, R7 ≈ §77, R8 ≈ §78), the historical evidence,
and this file's status note.

Wave status (2026-08-02): R6 delivered (§76: +18.8pp @ margins 0.5/1.0,
statistically established, V3 shop/TREASURE/boss-relic gates; shop-only
+3.1pp). R7 delivered (§77: Q-iso A/B — the Q-head architecture is NOT the
calibration bottleneck; Q MAE ≈ 14.4 both configs vs V4's 16.2; the token
state encoder is). R8 delivered (§78): PPO/GAE diverges on the behavioral
data (val_pol_ce 7.8 at epoch 30, non-finite advantages at epoch 31 —
negative result, CE+Q stays the policy objective); K=1 label-horizon A/B —
K=1 Q calibration far better (Q MAE 7.5 vs 14.3) but the deployed gate is
worse than K=3 (+12.5pp vs +18.8pp @ m1.0, both significant) → K=3 labels
stay the deployment choice. Cross-cutting: seed-128087 loop-guard isolation
landed (`src/combat/BattleContext.cpp`, Release-mode assert no-op → logged
loss termination). Phase C: C_ψ trained (§79, `train_combat_cpsi.py`,
no-peek entry inputs, death/win/HP-quantile/potion/turns heads,
`combat_cpsi_v1` export; win accuracy 0.969, HP MAE 7.2%, turns MAE 0.98 on
2,828,241 distgen rows / ~106k fights); encounter-probe integration
delivered (§80): `probe_cpsi.py` (9 probe slots from C_ψ, 54
features/decision, `build/strategic_tierb_probes.npy`) + `TOK_PROBES_FILE`
trainer lever — held-out A/B neutral (Q MAE 16.89 vs 17.00 at equal epochs);
the token-state calibration gap is not matchup-information-driven.

## 1. R6 contract — one-ply Q gates for shop / TREASURE / boss relic

Goal: complete the one-ply gate coverage (plan Phase D + round-4 follow-up 1)
on the **deployed V3 net** (`selfplay/models/ooc_strategic.native`,
`OocStrategicNet`). No datagen, no retrain — the §73 sample-all Tier-B labels
and `strategicCands` already cover these screens.

Three new gate functions in `apps/one_combat.cpp`, mirroring
`oocOnePlyEventPolicy` (one_combat.cpp:3240) exactly:

- `oocOnePlyShopPolicy` — `ScreenState::SHOP_ROOM` (8): score every legal
  action from `GameAction::getAllActionsInState` (buy CARD/RELIC/POTION,
  CARD_REMOVE, leave/SKIP) with `OocStrategicNet::predictActionValue` on the
  pre-decision state; execute argmax only when best−second ≥
  `g_oocStrategicMargin`; else `shopVPolicy` runs. Cats via `strategicCands`
  (SHOP: cand1=id, cand2=price, cand3=upgraded).
- `oocOnePlyTreasurePolicy` — `ScreenState::TREASURE_ROOM` (6): score legal
  relic/potion/gold picks; else `agent.stepOutOfCombatPolicy`.
- `oocOnePlyBossRelicPolicy` — `ScreenState::BOSS_RELIC_REWARDS` (3): score the
  boss relic choices (and skip if legal); else `bossRelicVPolicy`.

Wiring: same dual-net pattern as the existing four gates — V3 when
`g_oocStrategicNet.ok`, token net when `g_oocStrategicTokNet.ok` (tok entities
via `tokEntity`, which already handles SHOP_ROOM). New env flags, default OFF
(bit-reproducibility of the §74 config): `STS_OOC_STRATEGIC_SHOP=1`,
`STS_OOC_STRATEGIC_TREASURE=1`, `STS_OOC_STRATEGIC_BOSS_RELIC=1`. Wire into
`runFullRunOOC` (SHOP_ROOM branch ~2178, TREASURE_ROOM has no branch today,
BOSS_RELIC_REWARDS ~2196) and `runTraceRun` where the screens are handled.

Verification: `./build/test`, 8-seed smoke (flags-on output differs from off,
gates fire, no crash). Benchmark is the orchestrator's job.

## 2. R7 contract — Q-calibration isolation trainer (train_strategic_qiso.py)

Goal (§75 follow-up 1): decide whether the V4 net's deployed shortfall is
Q-head calibration (Q MAE 16.2 vs V3's 14.3) or the token state encoder.
A/B: **V3 state (1017 rich vector) + V4-style entity-conditioned action
encoder + V3 head contract**.

- Input: `build/strategic_tierb.csv`; state block = columns between `chosen`
  and `won` (1017), z-normalized on TRAIN rows (V3 convention).
- State encoder = V3's `s` (Linear(1017→256)→LN(1e-5)→GELU→Dropout(0.2)→
  Linear(256→128)→GELU) → `z_state(128)`.
- Action encoders = V4-style: bits Linear(32→32)→GELU→Dropout(0.2)→
  Linear(32→16) (`b16`); cats 6×Embedding(512,4)+atype(16→8) →
  Linear(32→32)→GELU→Linear(32→16) (`a16`); screen Embedding(16→8);
  **entity** Linear(37→32)→GELU→Linear(32→16) (`e16`) using the V4 entity
  extraction rules (REWARDS/SHOP CARD/RELIC/POTION, CARD_SELECT → card;
  goldGePrice on SHOP rows and REWARDS GOLD).
- `z = concat(z_state, b16, a16, s8, e16)` = 184; `pol`/`q` =
  Linear(184→96)→GELU→Linear(96→1); per-screen `vals` (8) on `z_state`
  (Linear(128→64)→GELU→Linear(64→1)).
- Losses/metrics identical to V3/V4: group-CE on chosen + 0.5·per-screen
  value-MSE (10·won+endHp) + 1.0·Q-MSE (10·labelWon+labelHp); metrics
  policy_top1, margin, val_pol_ce, value_mae(+screen), q_top1, q_mae(+screen).
- Env `QISO_ENTITY=0/1` (default 1): entity path zeroed when 0 — the isolation
  lever. Env: STRAT_EPOCHS(40), STRAT_BATCH(4096), STRAT_LR(2e-3),
  STRAT_QLAMBDA(1.0), STRAT_CLIP(1.0), STRAT_DEVICE (CUDA default, `device:`
  print required).
- Memory: reuse the V3 group-ordered float16 mmap machinery; a NEW state file
  (OUT+"_qiso_state.bin", 1017 cols) is fine.
- Output: OUT.pt = {"state_dict","mean"(1017),"inv"(1017),"metrics","entity",
  "nrows"}, OUT_metrics.json. CLI: CSV, OUT. Held-out A/B only — **no native
  export this round** (export/gate follow-up is conditional on a win).

## 3. R8 contract — PPO/GAE trainer (train_strategic_ppo.py)

Goal (plan Phase-A item 5): A/B a PPO-style policy loss against the CE+Q
training, on the same dataset and head contract.

- Input: `build/strategic_tierb.csv`. Trajectory reconstruction: per seed,
  decision groups sorted by `decIdx`; group state s_t = the state block of its
  rows (identical within the group); successor s_{t+1} = next group's state
  (or terminal); `Δf_t = max(0, floor_{t+1} − floor_t)` (floor = state col
  index 2). Terminal: r_T = 10·won + endHp, V(s_{T+1}) = 0.
- Value: V̂ = per-screen value heads as in V3 (chosen-row protocol relaxed to
  ALL groups for value targets — PPO value trains on every strategic state).
- GAE (spec A.10 starting points): γ=0.995 per floor, λ=0.95
  (`PPO_GAMMA`, `PPO_LAMBDA` env): δ_t = r_t + γ^Δf·V̂(s_{t+1}) − V̂(s_t);
  A_t = Σ_{k≥0} (γλ)^{Δf..} δ_{t+k} (accumulate per floor-elapsed discount;
  a per-floor γ is the target — apply γ^{Δf} per transition and (γλ)^{Δf}
  for the advantage decay).
- Policy loss (groups with a valid chosen row only): PPO clip
  (ε=0.2, `PPO_EPS`): ratio = exp(logit_chosen − logit_chosen_old), old
  logits frozen per epoch; loss = −mean(min(ratio·A, clip(ratio,1−ε,1+ε)·A)).
- Auxiliaries: 0.5·value-MSE (target = A_t + V̂_old(s_t)) + 1.0·Q-MSE on
  labelWon/labelHp rows (`PPO_QLAMBDA=1.0`) — same Q head as V3, so the A/B
  isolates the policy objective.
- Held-out metrics identical to V3 (policy_top1, margin, val_pol_ce, q_top1,
  q_mae...). Env: STRAT_EPOCHS(40), STRAT_BATCH(4096), STRAT_LR(2e-3),
  STRAT_CLIP(1.0), STRAT_DEVICE. CLI: CSV, OUT. No native export this round.

## 4. Verification & recording

- Trainer tracks: CPU smoke on a small synthetic strategicgen2-schema CSV
  (STRAT_DEVICE=cpu, 2 epochs) before handoff; the orchestrator runs the real
  GPU training.
- Gate track: smoke + benchmark by the orchestrator on the recorded fair
  128-seed block (seeds 126700–126827, 1,000 sims, 12 threads) vs the
  bit-identical baseline `build/tierb_gate_base.csv` (21.1%/37.5/8.6), margins
  0.5/1.0/5.0, paired via `paired_analysis.py`.
- Docs to update in the same change: EXPERIMENTS.md (R6–R8), historical evidence
  entry, `docs/knowledge-base/architecture/out-of-combat.md` gate list.
