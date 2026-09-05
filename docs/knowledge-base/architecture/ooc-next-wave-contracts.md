# OOC next-wave contracts — Phase E search + Phase B configs + benchmark protocol

Status: executed 2026-08-03. Results: §81 (V4 full gate stack
41.4%/+20.3pp @ m1 — top measured arm, V3 stays default), §82 (margin 1.0
optimal; 256-seed block +14.1pp significant), §83 (K=1+K=3 mixture +15.6pp,
below K=3-only), §85 (shop beam negative — value-head leaves weak; the
one-ply shop gate stays), §86/§87/§88 (Phase-B encoder neutrals;
conclusion: the token-state Q gap is the state contract, not encoder
capacity/info/Q-shape), C_ψ export-writer bug fixed + re-exported
(cross-check 2.4e-06), hidden-info audit delivered (future-encounter
features flagged). A3 (STRATEGIC_BRANCH_FUTURES=3) delivered (§84: +13.3pp gate,
below futures=1's +18.8pp — label contract closed at K=3×futures=1). The map-route search (B2) uses the ready C_ψ
loader but is deferred — leaf-value choice is the lesson from §85.

## 1. Benchmark protocol (A0/A1)

- Recorded block: `STS_FAIR=1 ./build/one_combat bestbench 1000 128 0 126700`
  (12 threads), baseline `build/tierb_gate_base.csv` bit-identical (21.1% /
  37.5 / 8.6), paired via `paired_analysis.py`.
- **A0 — V4 token net × full gate stack** (never benchmarked together):
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  + `REST=1 EVENT=1 SHOP=1 TREASURE=1 BOSS_RELIC=1` at margins 0.5/1.0/5.0.
  Reference arms: §76 V3 full stack (39.8% @ 0.5/1.0), §75 V4 cards+rest+event
  (+3.1pp @ 5.0). Record as §81.
- **A1 — margin refinement + secondary block:** §76 V3 config at margins
  1.5/2.0/3.0 (the curve is flat 0.5–1.0, dead at 5.0). Secondary paired block:
  seeds 126700–126955 (256 seeds), 1,000 sims, baseline run on the same
  extended range (gates off) + full-stack run at the best margin. Update
  `docs/knowledge-base/evaluation/current-baselines.md` with a gates-on
  headline row (marked opt-in/experimental; gates stay **off by default**).
  Record as §82.

## 2. B1 contract — shop beam search (apps/one_combat.cpp)

- New policy `oocShopBeamPolicy(GameContext&)` behind `STS_OOC_SHOP_BEAM=1`
  (default off; `STS_OOC_SHOP_BEAM_WIDTH` default 32, `STS_OOC_SHOP_BEAM_DEPTH`
  default 0 = until leave/no affordable actions). Runs on SHOP_ROOM **instead
  of** the one-ply shop gate when enabled (gate/beam mutual exclusion: beam
  first, else the one-ply gate, else shopVPolicy).
- Beam: state = (remaining shop offers, gold, deck) — clone via
  `detachedCounterfactualCopy` (one_combat.cpp:3191) per beam node; expand
  every legal `GameAction` (buy card/relic/potion, CARD_REMOVE, leave);
  dedup nodes by fingerprint (gold + offer-set + deck digest — reuse the
  `StratFingerprint` fields where applicable); width 16–64 default 32; depth
  = until leave or no affordable actions. Leaf value = per-screen value head
  `predictValue(state, ScreenState::SHOP_ROOM)` (V3 net; token net path via
  `buildTokState` when loaded). Execute the FIRST action of the best-scoring
  sequence; on ties/empty, fall back to the one-ply shop gate.
- Hidden info: shop purchase transitions are deterministic (no RNG); the leaf
  value head sees only visible state — no hidden-RNG copying (B3 audits).
- Benchmarks: (a) beam-only vs baseline (isolates the beam); (b) full §76
  stack with beam replacing the shop gate at the A1 margin. Record as §85.

## 3. B2a contract — C++ C_ψ loader (new files only)

- New `include/sim/search/CombatCpsiNet.h` + `src/sim/search/CombatCpsiNet.cpp`
  (own ONLY new files; the trainer's export format is the spec:
  `train_combat_cpsi.py`'s `combat_cpsi_v1` text export — read the writer to
  get the exact block order, and `probe_cpsi.py` for the CPSINet architecture).
- `CombatCpsiNet::load(path)` parses the text format; `predict(scalar[11],
  deckBag[371], relics[128], potions[44], encounter)` → {death, win, hp,
  quantiles[11], potionProb[44], turns} with the exact postprocessing
  (sigmoids, expm1) used at training time.
- Entry-state builder from `GameContext` (pre-combat ONLY: no hand/draw/
  monster/intent): deck counts by card id [0..370], relics [0..127], potions
  [0..43], ascension, curHp, maxHp, the 8 relic counters (happyFlowerCtr,
  incenseBurnerCtr, inkBottleCtr, inserterCtr, nunchakuCtr, penNibCtr,
  sundialCtr, panacheCtr — from `RelicInstance.data` of the corresponding
  relics; 0 when absent).
- Verification: numpy cross-check harness (deterministic inputs; compare C++
  against the torch CPSINet forward with the same inputs; tolerance 1e-3).
- Usage (for B2): a probe helper evaluating the fixed probe set + arbitrary
  encounters on a `GameContext`.

## 4. B3 contract — hidden-information audit (5.6.4, spec §13)

- Audit the strategic datagen branches (`finishOocCounterfactual`,
  `detachedCounterfactualCopy`, `runStrategicGenSeed2`), the one-ply gates,
  and any rollout/sampling path: no path may copy hidden RNG/future seeds or
  use information the player cannot see (future card rewards, unknown shop
  contents, exact future encounter identity beyond the known pool, event
  outcomes before selection). Rollouts must sample unknown outcomes from
  conditional distributions.
- Deliverable: an audit report in the historical evidence + KB
  (`docs/knowledge-base/behavior/determinism-and-rng.md` update) + fixes for
  any violations found. Owns existing `src/sim/search/*` files (NOT
  one_combat.cpp, NOT the new CombatCpsiNet files).

## 5. C1 contract — deck set transformer (strategic_tok_net.py + train_strategic_tok.py)

- Config lever `STRAT_TOK_TRANSFORMER=1` (default 0): replaces the deck
  single-head attention (`deck_encode`) with a 2-layer transformer at dim 32
  (2 heads, FFN 64, LayerNorm eps 1e-5, GELU, residual) over the counted
  `(cardId, upgraded, countF)` tokens; pooling unchanged (mean over valid).
  Rung masking semantics unchanged. `Net(rung, nprobes, transformer=0/1)`.
- Held-out A/B vs the §75/§80 V4 numbers (policy top-1 0.793, Q MAE 16.2,
  val CE 0.486). No export this round (native format change would be a
  follow-up if it wins).
- C4 (distributional value heads) and C2 (candidate–deck cross-attention)
  are follow-up configs in the same files, serialized on the GPU by the
  orchestrator.

## 6. A2/A3 contracts

- **A2 — K=1+K=3 joint labels:** concatenate `build/strategic_tierb.csv` +
  `build/strategic_k1.csv` (disjoint seeds; header once) into
  `build/strategic_mix.csv`; train the V3 CE+Q trainer
  (`train_strategic.py`) on it; held-out + full-stack gate at the A1 margin.
  Record as §83.
- **A3 — STRATEGIC_BRANCH_FUTURES A/B:** strategicgen2 datagen
  (`STRATEGIC_BRANCH_FUTURES=3`, else the §73 config) on seeds 134000+
  (~1,000 seeds); V3 CE+Q retrain; held-out + gate. Record as §84.
