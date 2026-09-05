## 67. Checkpoint-oracle distilled OOC action NN  ➕ promising, needs more data (2026-07-24)
- **Goal:** distill the expensive 3-checkpoint MCTS oracle (§66) into a fast forward-pass NN that
  scores every legal OOC action directly, replacing the entire OOC policy stack (cards, path, shop,
  rest, events) with a single model.
- **Teacher data:** 16 seeds, fair-play, 600 live combat sims, 2 futures, 3 checkpoints,
  decreasing inner sims (400/200/100). 6,307 action rows / 1,974 decisions across acts 1–3.
  Collected via `STS_ACT_FIGHT_PROBE_ALL_OOC=1 STS_ACT_FIGHT_PROBE_LOG=teacher.csv`.
- **Model:** MLP (1017→256→128 state, 32→16 action, screen/act embeddings, 156→96→1 head),
  GELU activations, dropout 0.2. Trained to predict meanUtility with MSE loss. Held-out
  best-action accuracy 44.6% (vs ~31% random with 3.2 actions/decision).
- **Native C++ inference:** exported weights to binary (1.25MB), implemented GELU/Linear/LayerNorm
  from scratch. `STS_OOC_CHECKPOINT_NN=<path>` env flag. Server-free, parity-verified vs PyTorch
  (max error 0.001). CPU overhead ~0.5s/run over baseline.
- **Full-run gate (128 seeds, 1000 sims):** baseline 14.1%/36.2 floor/5.8 HP. Native NN **0.0%/
  19.4 floor**. The 16-seed model cannot reliably differentiate actions (all scores cluster
  at 2.6–2.8, narrow variance). Server-based OA endpoint previously reported 17.2% but was
  unreliable (silent fallback to baseline policies when server dropped).
- **Act-1 trace tooling:** enhanced `runtrace` mode now shows NN scores for every OOC screen
  (card drafts with skip evaluation, Neow upgrades, rest heal/smith, map choices, event options,
  shop actions). Format: `[NN <screen>] <action> = <score>`. See `AGENTS.md` for usage.
- **Verdict:** ➕ the architecture and pipeline work end-to-end (teacher collection → training →
  native deployment → trace evaluation). The model has correct directional instincts (prefers
  heal over smith at low HP, prefers skip over weak cards) but lacks sufficient data to make
  confident decisions. Next: collect more teacher data (100+ seeds) and retrain.

## 67b. Combat value net makes the checkpoint oracle tractable  ➕ strong Act-1 (2026-07-24)
- **Goal:** the §66 all-OOC checkpoint oracle was proven effective (100% Act-1 clear vs 56%
  baseline on 16 seeds) but cost 6,951 CPU-s/run. Make it practical by replacing inner-checkpoint
  pure MCTS rollouts with low-sim MCTS + combat value net leaf.
- **Setup:** `STS_ACT_FIGHT_PROBE_ALL_OOC=1 STS_ACT_FIGHT_PROBE_FUTURES=2
  STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS=3 STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=50,25,10
  STS_VNET=build/v_combat_fair_trees.txt STS_VNET_ALPHA=0.3`
- **8-seed Act-1 (127000–127007):** baseline 50.0% clear / 26.4 HP / 1.32 CPU-s. Oracle+V-net
  **87.5% clear / 48.4 HP / 150.26 CPU-s**. +37.5pp clear rate, +22 HP.
- **Speed:** 150 vs original 6,951 CPU-s/run = **46× speedup** from the combat value net.
  Still 114× baseline, but now practical for small-scale teacher data collection.
- **Interpretation:** 50/25/10 sims with the value net leaf provides near-full combat strength
  for checkpoint evaluation. The value net (trained on fair-play combat data at full sims) gives
  reliable P(win) and E[HP|win] estimates, so MCTS only needs enough sims to resolve action
  choices, not to play out full fights.
- **Verdict:** ➕ the checkpoint oracle is now a viable tool for teacher data collection and
  offline policy evaluation. Next: collect checkpoint-oracle decisions at scale to retrain
  the distilled OOC action NN; A/B the oracle directly as a live policy only if the CPU cost
  can be brought below ~30s/run (more aggressive sim caps or NN acceleration).

## Phase 4b PVNet alpha sweep — 2026-07-30

**Recorded setup (incomplete):** 128 seeds, asc 0, Searcher3 fair-play,
combined PVNet (policy priors + leaf value blend), on a c4-highcpu-24 VM (24
threads). The original note says “baseline heuristic OOC + PUCT (GBM policy)”
but records neither the seed range nor the exact command/model flags, and
“heuristic OOC” does not identify a reproducible `runFullRunOOC` stack.
Current source also invokes Searcher3 `computeEdgePriors` only when the
separate policy net is loaded; the recorded GBM policy may have supplied that
enabling condition, but the omitted command prevents verification.

### Sweep: α-blend × sim budget

| sims | α=0.0 | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|
| **50** | 57.8% | 46.1% | 56.2% | 51.6% | 50.0% |
| **100** | **66.4%** | 59.4% | 63.3% | 62.5% | 50.0% |
| **250** | **65.6%** | 62.5% | 60.9% | 47.7% | 49.2% |
| **500** | 59.4% | **60.2%** | 54.7% | 53.1% | 40.6% |

### Interpretation

- **α=0.0 (policy-only):** PVNet priors guide PUCT and the leaf value comes
  from rollout. It wins or ties within the recorded table at every simulation
  budget; no uncertainty intervals were recorded.
- **α=1.0 (pure neural leaf)** is worst at all 4 sim budgets. The gap grows with sims: from
  ~7pp at 50 sims to ~19pp at 500 sims. The table shows worse performance for
  the pure neural leaf, but does not establish the failure mechanism.
- **α=0.25 (25% neural / 75% rollout)** edges α=0.0 at 500 sims (60.2% vs 59.4%, within noise)
  — no benefit is established by that difference.
- **Recorded conclusion:** the sweep supports evaluating the policy head
  separately from the value head. A separate 32-seed point reported 78.1% at
  100 simulations, but its command and seed range are also absent. This is not
  a current deployment recommendation.

## 68. Current default fair stack re-measured on the recorded block (2026-08-02)

- **Question:** what is the current default stack's result on the recorded
  128-seed block, given the primary §66i reference is not exactly reproducible
  from tracked artifacts (KB issue 02)?
- **Setup:** `STS_FAIR=1 ./build/one_combat bestbench 1000 128 0 126700
  build/bench_2026-08-02_default_fair.csv`. Default Searcher2, A0, 1,000 sims
  per decision, 12 outer workers. Native OOC floor/win trees
  `build/v_rich_trees.txt` sha256
  `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`,
  `build/v_win_trees.txt` sha256
  `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`;
  tracked policy prior `build/policy_trees_c.txt` sha256
  `24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321` loaded
  (c_puct 2.5); skip `-0.5`; heuristic path; shop-V; win-rate rest
  (`g_restWin=true`); no combat value/PVNet/dist nets. Working tree: commit
  `2ae3ea3` plus the uncommitted 2026-08-02 issue-fix set (Searcher3 seeding,
  belief conditioning, draw-order application, PVNet-only priors, observation
  identity, conservative pruning, isBattleOver derived flag, banner, trace
  guards, fairgen forcing).
- **Result:** **27/128 wins (21.1%)**, mean floor **37.5**, mean end HP **8.6**,
  cpu_sec/run 6.96, wall 80.1 s. Per-seed rows in
  `build/bench_2026-08-02_default_fair.csv` (10-column bestbench schema).
- **Interpretation:** a new measurement, not a paired comparison with §66i
  (39/128, 30.5%): that entry's exact flags/artifacts are unverified and may
  have included a combat value net, which this run does not load. The result
  is consistent with the fresh §66j 32-seed baseline under the same stack
  (7/32 = 21.9%, floor 37.31), and the fair multi-thread non-bit-identical
  caveat of §66j applies. Directionally, the §66i headline likely came from a
  different configuration; treat it as historical, not current.
- **Reproducibility:** 12 threads, per-seed CSV retained; fair multi-thread
  replay is not bit-identical across invocations (§66e/66j), so small
  differences in aggregates are expected.

## 69. Fair replay determinism verification (2026-08-02)

- **Question:** is fair multi-thread whole-run replay bit-identical across
  separate process invocations, given the recorded §66e/66j divergence
  (2026-07-23)? KB issue 10.
- **Method:** `STS_FAIR=1 ./build/one_combat bestbench <sims> <nseeds> <asc>
  <offset>` run twice per configuration on commit `63d8b89`; per-seed rows
  compared on all columns except `sec` (wall timing), aligned by seed.
  Configurations: fair Searcher2 at 12 threads (32 seeds), 8 threads (32
  seeds, the historical worker count), 1 thread (16 seeds), 128 seeds at 12
  threads; fair Searcher3 at 12 threads (16 seeds); known-RNG Searcher2 at 12
  threads (32 seeds). Plus `STS_FAIR=1 python3 check_replay.py 1000 16 0
  126700` as an end-to-end probe.
- **Result:** **bit-identical in every configuration** — 0 non-`sec`
  differences across all compared rows. The recorded
  `build/bench_2026-08-02_default_fair.csv` (128 seeds) reproduces exactly on
  a fresh rerun (`build/det_fair128_b.csv`).
- **Interpretation:** the §66e/66j divergence does not reproduce on the
  current code. Timeline: divergence recorded 2026-07-23; `da8c902`
  (2026-07-26) added the `BattleContext::init` full reset whose comment says
  leaving stale nested state behind "made a nominally fresh fair-play combat
  depend on stack/object reuse from a previous run" — **Inference:** that
  stale-state dependency (interleaved by `schedule(dynamic)` outer
  parallelism) was the historical divergence cause. No `random_device` or
  time-based seeding exists; observation hashing is integer-only; OpenMP is
  used only in the outer per-seed loops.
- **Caveats:** verified for this binary/config only (Linux/WSL gcc 13, `-O3`,
  gcc OpenMP). It is not a proof for other compilers, sanitizer builds, or
  configurations, and `sec` legitimately differs. The self-play cache should
  still key on binary/model hashes.

## 70. Phase 5 first round: all-actions strategicgen + Tier-A policy/value net + one-ply card gate (2026-08-02)

- **Goal:** first end-to-end round of the archived Phase 5 plan (semi-Markov run-level strategic agent): upgrade `strategicgen` to log every legal OOC action with structured candidate fields and Tier-A labels, train a joint policy + run-value net, and use it for one-ply post-action value search on card rewards behind a margin gate.
- **Datagen:** `strategicgen` now emits one row per legal action per decision: `seed,decIdx,screen,action,actionType,c1..c3,cand1..c3,chosen,<1017 rich state>,won,endFloor,endHp`. `chosen` is detected by successor-fingerprint matching (deck/relic/selection digests; 2 of 786 smoke decisions remain RNG-tied, e.g. Mausoleum open-with-nothing vs leave). The generator mirrors the deployed default OOC stack (heuristic path, one forced non-card reward per iteration, native floor card pick with `CARD(rIdx,5)` skip, win-rate rest/upgrade, Searcher2 fallback).
- **Dataset:** 200 seeds (128000–128199), 134,832 action rows, 31,870 decisions, 18s wall. `build/strategic_200.csv` sha256 `b28a3d83db40b7abdacfec4850e61abe71f9ead6c9e1872f78fabd37c7241ae5`.
- **Model (`train_strategic.py`):** state MLP 1017→256(LN)→128 + bit/actionType/candidate embeddings, policy head (group softmax on `chosen`) + value head V(s) → `10·won+endHp` on chosen rows only (Tier A labels). Grouped 80/20 split by `(seed,decIdx)`. 60 epochs, CUDA (RTX 3060 Ti). Held-out: policy top-1 **0.778** (predicting the baseline's choice), value MAE **1.73**, RMSE **6.06**, mean logit margin 12.8. Stable training required two fixes: per-group (not global) logsumexp in the group softmax (global max underflowed to `-inf` → NaN at epoch ~30–40) and grad clipping (`STRAT_CLIP=1`). Artifacts `selfplay/models/ooc_strategic.pt/_metrics.json`.
- **Export (`export_strategic.py` → `apps/ooc_strategic_net.h`):** binary `OOC_STRAT_V1`, 1,345,644 bytes, `selfplay/models/ooc_strategic.native` sha256 `b096498abf40dec906dd3020583a9c9920cbd8d05c3a84aa3da3295f514c60a7`; in-script parity vs PyTorch max err logit 6.6e-06 / value 9.5e-05. C++ loader with full payload-read checks (issue-08 pattern), loaded via `STS_OOC_STRATEGIC_NN=<path>`.
- **One-ply gate (`oocOnePlyCardRewardPolicy` in `runFullRunOOC` REWARDS branch):** each legal reward action applied to a copied `GameContext`, successor scored by V(s'); best action executed only if its margin over the runner-up ≥ `STS_OOC_STRATEGIC_MARGIN` (default 1.0), else the heuristic card policy runs. Greedy un-gated deployment stays off (recorded §66m failure mode).
- **Paired gate (fair, A0, 1,000 sims, Searcher2, 12 workers, seeds 126700–126827, `STS_FAIR=1 bestbench 1000 128 0 126700`):**
  - baseline (new binary, flag off): **21.1% / 37.5 floor / 8.6 HP** — bit-identical re-measure of §68, confirming §69 determinism on the new binary.
  - candidate margin=1.0: **10.2% / 31.5 / 3.7** — paired −10.9pp win, floor 95% CI [−8.1, −4.0]; discordant 20/128 (A-only 17, B-only 3).
  - sensitivity margin=5.0: **17.2% / 33.7 / 7.1** — still negative, but monotone: fewer overrides, less damage.
- **Verdict:** ❌ the first Tier-A net is not deployable. The pipeline works end-to-end (collect → train → export → native one-ply → paired gate) and the value head generalizes (MAE 1.73), but its one-ply action ranking damages card picks whenever it overrides — consistent with the §66k/§66m/§67 lesson that terminal-only supervision is a weak action-ranking signal and error compounds across decisions. The margin knob trades damage monotonically. Next candidates, in order: (1) collect more data (1,000+ seeds); (2) Tier-B one-ply counterfactual labels via the existing `finishOocCounterfactual` machinery; (3) per-screen value heads / action-conditioned Q; (4) apply one-ply only to screens where the model's held-out value MAE is best (rest/shop), not card rewards.
- **Artifacts:** `build/strategic_200.csv`, `build/oneply_gate_base.csv`, `build/oneply_gate_cand.csv`, `build/oneply_gate_m5.csv`, `selfplay/models/ooc_strategic.{pt,native,_metrics.json}`.

## 71. Per-screen value heads: card gate goes neutral (2026-08-02)

- **Goal:** isolate the value-head structure (option 2 of §70's decision rule):
  replace the single screen-blind value head with one head per screen (1..8),
  everything else unchanged (same 200-seed Tier-A data, same split seed, same
  policy head, same grouped CE + value MSE, same one-ply card gate).
- **Model (`train_strategic.py`):** shared state encoder (1017→256→128) + 8
  value heads `Linear(128,64)→GELU→Linear(64,1)` indexed by `screen−1`; value
  MSE computed per screen (mean over screens present in the batch), λ=0.5.
  Binary format bumped to `OOC_STRAT_V2` (`export_strategic.py`,
  `apps/ooc_strategic_net.h::OocStrategicNet::predictValue(state, screen)`);
  one-ply and runtrace score successor states with the head of the successor
  screen (`probe.screenState`). Parity: max err logit 7.7e-06, value 1.0e-04
  (value assert relaxed to 2e-4 — float32 accumulation across 8 heads).
- **Held-out value MAE by screen** (best checkpoint, 10·won+endHp scale):
  TREASURE 0.59, REST 0.73, SHOP 0.97, BOSS_RELIC 1.42, MAP 1.64, REWARDS
  2.13, CARD_SELECT 2.63, EVENT 5.21 (n 124/273/321/69/1651/3428/236/294).
  Non-reward screens are 2–8× better calibrated than the §70 pooled head
  (overall MAE 2.01; §70 pooled was 1.73 but dominated by REWARDS).
- **Paired gate** (fair, A0, 1,000 sims, seeds 126700–126827, same baseline
  CSV as §70 — bit-identical replay on the new binary):
  - margin=1.0: **21.1% / 37.5 / 8.6** — per-seed identical to baseline.
  - margin=5.0: **21.1% / 37.5 / 8.6** — per-seed identical to baseline.
  - The gate never changes a card pick: successor-state value margins between
    legal card choices are all below the gate (card successors are scored by
    the MAP head, MAE 1.64).
- **Verdict:** ➖ per-screen heads convert §70's −10.9/−3.9pp damage into 0.0pp
  neutrality, but also produce no card-pick improvement. The round's
  diagnostic value is real: per-screen held-out MAE is the measurement §70
  asked for, and it confirms REST (0.73), SHOP (0.97), TREASURE (0.59) are
  where the value head is strong and REWARDS (2.13)/EVENT (5.21) are weak —
  supporting a rest/shop gated one-ply round next (§70 option 3), and
  suggesting Tier-B labels are needed specifically for card rewards and events
  (§70 option 2).
- **Training-throughput fixes (same metrics, bitwise-neutral to model
  quality):** the trainer was CPU-bound (350–400% CPU, GPU ~35%) because every
  batch gathered 4096 random rows out of the 549MB state tensor plus per-batch
  numpy allocations; fixed by reordering all inputs by decision group once and
  gathering once per epoch into the group permutation, so every batch is a
  contiguous slice (default batch 4096 rows). CPU 127–154%, GPU up to 53%.
  The trainer now defaults to CUDA when available and prints `device:` at
  startup (AGENTS.md training convention).
- **Artifacts:** `build/psh_gate_m1.csv`, `build/psh_gate_m5.csv`,
  `selfplay/models/ooc_strategic.{pt,native,_metrics.json}` (V2).

## 72. PVNet "60-70%" claim re-check on the recorded block (2026-08-02)

- **Question:** the Phase 4b PVNet alpha sweep (2026-07-30, final ledger
  section) recorded a best 100-sim policy-only point of **66.4%** (and a
  78.1% 32-seed point with no command). Is a 60-70% combination still valid
  on the current checkout? The KB has always marked the sweep's seed range
  and exact command as unresolved; this check measures the closest
  reconstructable configuration on the recorded 126700–126827 block.
- **Setup:** `STS_FAIR=1 STS_SEARCHER3=1 STS_PVNET=build/v_combat_pvnet.txt
  STS_PVNET_ALPHA=0 ./build/one_combat bestbench 100 128 0 126700
  build/pvnet_check_s3p0.csv`. Tracked PVNet sha256
  `05d809298921623af7c87c06e7dd31f5129abfd77cc702f75b9867949a59533f`; tracked
  policy prior auto-loaded (banner `policyNet=ON`), satisfying the
  `computeEdgePriors` enabling condition the KB flags. 12 workers, A0, native
  OOC default stack. Reference: default Searcher2 fair at the same budget,
  `build/pvnet_check_base100.csv`; plus α=1.0 (pure neural leaf),
  `build/pvnet_check_s3p1.csv`.
- **Result (128 seeds, 100 sims):**
  - default Searcher2 fair: **4.7% / 29.5 floor / 2.0 HP**
  - Searcher3 + PVNet α=0: **8.6% / 26.4 / 4.2** — paired +3.9pp win
    (95% CI [−0.0, +8.6]), floor −3.1 (CI [−5.6, −0.6]), 9/128 discordant
  - Searcher3 + PVNet α=1.0: **5.5% / 24.4 / 2.8** — worse than α=0,
    consistent with the sweep's "pure neural leaf worst" ordering
- **Verdict:** ❌ the recorded 66.4% headline does **not** reproduce on the
  current checkout and the recorded seed block; the closest reconstructable
  configuration scores 8.6% there. The PVNet combo still beats the
  same-budget default on wins (+3.9pp, CI touching zero) at a floor cost, and
  the α-ordering matches the sweep, but no 60-70% combination exists on the
  current binary. Treat the sweep numbers as historical/unreproducible (as the
  KB already warned), not as a current baseline. Note the sweep may have used
  a different seed block and/or OOC stack; those cannot be recovered from the
  ledger.
- **Artifacts:** `build/pvnet_check_base100.csv`, `build/pvnet_check_s3p0.csv`,
  `build/pvnet_check_s3p1.csv`.
- **Post-§73 confirmation:** re-run on the 2026-08-02 04:12 binary (after the
  Tier-B/`strategicgen2` changes landed) is per-seed identical to the above
  for all three configs (base 4.7%, α=0 8.6%, α=1.0 5.5%). The finding is
  unchanged: no 60–70% PVNet combination exists on the current checkout.
  Artifacts `build/pvnet_check2_{base100,s3p0,s3p1}.csv`.

## 73. Phase 5 round 3: Tier-B one-ply Q labels + Q-head card gate (2026-08-02)

- **Goal:** round-3 of Phase 5: collect Tier-B one-ply counterfactual labels
  per legal OOC action (`strategicgen2`), train a Q(s,a) head on them, export
  `OOC_STRAT_V3`, and gate card rewards on direct Q scoring
  (`oocOnePlyCardRewardPolicy`), keeping the V2 successor-`predictValue` path
  reachable via `STS_OOC_STRATEGIC_Q=0`.
- **Datagen (`strategicgen2`, `apps/one_combat.cpp::runStrategicGenSeed2`):**
  `strategicgen2 5600 1000 0 build/strategic_tierb.csv 128000` with
  `STRATEGIC_SAMPLE_ALL=1` (every decision labeled), `STRATEGIC_BRANCH_FIGHTS=3`
  battles per branch, `STRATEGIC_BRANCH_SIMS=150,100,50`,
  `STRATEGIC_BRANCH_FUTURES=1`, `STS_VNET=build/v_combat_fair_trees.txt`,
  `STS_VNET_ALPHA=0.3` (the §67b cheap-sims + combat value net pattern).
  Each branch applies the action to a detached pre-decision copy, continues
  with the deployed-default OOC policy through the next 3 battles, then
  bootstraps expected floor/P(win) from the native trees
  (`finishOocCounterfactual(..., maxFights=3, bootstrap=true)`); all branches
  of a decision share the branch seed (common random numbers). Schema: the
  `strategicgen` columns unchanged, then
  `won,endFloor,endHp,labelWon,labelHp,labelFloor,labelBootstrap`.
- **Dataset:** 3,057,708 rows / 4,650 seeds (128000–132630; seed 128087
  excluded — it hits a pre-existing `BattleContext::executeActions`
  loop-guard assertion, crash dump shows a `(Dazed,-32767,…)` monster) /
  723,851 decisions, 6.5GB CSV
  (≈6h wall, 12 threads; per-run ≈46–50 s). Smoke (5 seeds): 2,669 rows, all
  labeled, bootstrap rate 74%, chosen-row `labelWon~won` Pearson 0.818 and
  `labelHp~endHp` 0.567 (label sanity: the chosen action's branch predicts the
  run outcome well). Determinism verified: identical 1-seed output on rerun.
- **Correction — V2 native value heads 1–7 were misaligned:** the round-2
  exporter wrote the 8 value heads per-head-interleaved
  (`vals.h.0.weight/bias/2.weight/2.bias` per h), while
  `OocStrategicNet::load` reads them block-major (`val0w`, `val0b`, `val2w`,
  `val2b`). In the deployed `OOC_STRAT_V2` artifact only head 0 (TREASURE) was
  aligned; heads 1–7 read misaligned weights in C++, so §71's per-seed-neutral
  gate and the margin diagnostics below measured that (partly garbage)
  deployment. The trainer-side per-screen MAE table (§71) is unaffected. The
  V3 exporter writes block-major; a C++ harness cross-checked against the
  numpy reference (value 1.6e-08, Q 3.8e-07).
- **V2-path gate diagnostics** (patched V2 artifact loaded as V3,
  `STS_OOC_STRATEGIC_Q=0`, same §71 deployment path; fair, A0, 1,000 sims,
  seeds 126700–126827):
  - margin 0.5: **21.1% / 37.4 / 8.6** — per-seed identical to baseline
    (gate never fires at ≥0.5).
  - margin 0.25: **24.2% / 38.0 / 9.3** — fires on 8/128 seeds (2 A-only,
    6 B-only); paired +3.1pp wins (CI [−1.2, +7.4]), floor +0.55 (CI
    [−0.43, +1.52]), score +0.86 (CI [−0.39, +2.10]): directionally positive,
    not significant, and — unlike §70's margin-1.0 damage — not damaging.
  - The V2 card gate therefore only ever overrides below margin 0.5, and low
    margins are safe on this block.
- **Trainer (`train_strategic.py`):** new Q head
  `Linear(168,96)→GELU→Linear(96,1)` on the same (state, action-bits,
  action-cat, screen) concat as the policy head; loss
  `CE + 0.5·value_MSE + STRAT_QLAMBDA·Q_MSE` (default λ=1.0) with Q target
  `10·labelWon + labelHp` on every labeled row. Memory restructure for
  multi-GB CSVs: state block read in pandas chunks, standardized on train rows
  only, written once to a group-ordered float16 file
  (`OUT + "_state.bin"`, reused on size match), training reads contiguous
  mmap slices; epoch-permuted train batches gather ~4096 rows each. New
  metrics: `q_top1` (argmax Q vs argmax label per ≥2-row val group), `q_mae`,
  `q_rmse`, `q_n`, `q_mae_screen`. CUDA default, `device:` startup print.
- **Held-out metrics (best checkpoint, `selfplay/models/ooc_strategic_metrics.json`):**
  policy top-1 **0.784** (V2: 0.778), logit margin 9.35, value MAE 5.45 /
  RMSE 10.95 (10·won+endHp, chosen rows; not comparable to §71's 2.01 on
  the 200-seed Tier-A set), **Q top-1 0.284** vs oracle label per group
  (random ≈ 0.24 at mean group size 4.2), Q MAE 14.32 / RMSE 20.07 (n
  610,884 val rows). Per-screen value MAE: EVENT 6.76, REWARDS 6.02,
  BOSS_RELIC 3.60, CARD_SELECT 5.19, MAP 4.97, TREASURE 3.16, REST 3.05,
  SHOP 4.11. Per-screen Q MAE: 13.3–16.9 across screens.
- **Export (`export_strategic.py` → `apps/ooc_strategic_net.h`):** binary
  `OOC_STRAT_V3` (value heads block-major + Q head appended), parity logit
  <1e-4, value/Q <2e-4; new `predictActionValue(state, bits, cats,
  actionType, screen)`; truncation-safe loader (issue-08 pattern).
- **Q-head gate** (fair, A0, 1,000 sims, seeds 126700–126827, 12 workers;
  `STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`, direct Q
  scoring; baseline re-measured on the new binary — bit-identical to
  `build/oneply_gate_base.csv`, 21.1%/37.5/8.6):

  | margin | wins | floor Δ | win Δ | score Δ | discordant |
  |---|---:|---:|---:|---:|---:|
  | 0 (greedy) | 22 (−3.9pp) | −0.11 CI [−2.13,+1.91] | −0.039 | −0.50 | 23 |
  | 0.25 | 26 (−0.8pp) | −0.33 CI [−2.35,+1.69] | −0.008 | −0.41 | 25 |
  | 0.5 | 33 (+4.7pp) | +0.06 CI [−2.08,+2.21] | +0.047 | +0.53 | 30 |
  | 1.0 | 29 (+2.2pp) | −1.27 CI [−3.29,+0.76] | +0.016 | −1.11 | 20 |
  | 5.0 | 26 (−0.8pp) | −0.20 CI [−0.80,+0.41] | −0.008 | −0.27 | 3 |

  All deltas are candidate-minus-baseline paired; 95% CIs all span zero.
  The Q gate fires far more than the V2 gate ever did (30 discordant seeds
  at 0.5 vs 8 for V2). The margin curve is **non-monotone with a peak at
  0.5**: greedy margin 0 regresses (−3.9pp wins, 14 A-only / 9 B-only —
  the §66m un-gated lesson holds for the Q model too, so the gate does
  essential work), while 0.25 already turns negative again. Only the 0.5
  point is win-positive.
- **Verdict:** ➖ mixed. The Tier-B Q gate is the first strategic gate that
  actually fires at margin 1.0 (20/128 discordant) and its effect is
  directionally win-positive (+4.7pp at margin 0.5) with wide CIs — not
  §70's damage, not §71's neutrality, but not a statistically established
  improvement either. The pipeline (collect → train → export V3 → native
  Q gate) works end-to-end and Q margins carry signal (Q top-1 0.284,
  chosen-row labelWon~won 0.424 on 725k rows), but the Q head's ranking is
  not yet good enough to move the win rate reliably. A neutral-with-Q-labels
  result was pre-registered as acceptable evidence; this is a small
  directional step beyond it.
- **Artifacts:** `build/strategic_tierb.csv`, `build/psh_gate_m05.csv`,
  `build/psh_gate_m025.csv`, `build/tierb_gate_{base,m0,m025,m05,m1,m5}.csv`,
  `selfplay/models/ooc_strategic.{pt,native,_metrics.json}` (V3).

## 74. Phase 5 round 4: one-ply Q gate for campfires and events (2026-08-02)

- **Goal:** plan items 5.5.2/5.5.3 — extend the one-ply post-action Q gate from
  card rewards to campfires (every legal rest option + the smith's
  upgrade-target pick) and events (every legal option, incl. Neow). No new
  datagen and no retrain: the §73 sample-all Tier-B labels already cover every
  screen's decisions, so this round is purely the C++ gate extension +
  evaluation of the deployed `OOC_STRAT_V3` net.
- **Implementation (`apps/one_combat.cpp`):** three new gate functions mirroring
  `oocOnePlyCardRewardPolicy` — `oocOnePlyRestPolicy` (REST_ROOM:
  REST/SMITH/LIFT/GIRYA/PEACE_PIPE/SHOVEL/SKIP), `oocOnePlyUpgradeSelectPolicy`
  (CARD_SELECT/UPGRADE targets), `oocOnePlyEventPolicy` (EVENT_SCREEN options,
  incl. Neow). Each scores every legal action directly with
  `OocStrategicNet::predictActionValue` on the pre-decision state (input
  resolution identical to the training rows via `strategicCands`) and executes
  the argmax only when its margin over the runner-up reaches
  `STS_OOC_STRATEGIC_MARGIN`, else the default layer runs (win-rate rest,
  win-rate upgrade target, heuristic events). Wired into `runFullRunOOC` and
  `runTraceRun`. Knobs `STS_OOC_STRATEGIC_REST=1` / `STS_OOC_STRATEGIC_EVENT=1`
  (default **off**, so the §73 card-only configuration stays reproducible and
  layer-wise ablations are possible). The plan's "evaluate via V_run(s') with
  RNG-clone sampling" is superseded by the Tier-B Q labels, which already
  average the stochastic continuation per action (CRN, K=3 battles + bootstrap).
- **Paired gate** (fair, A0, 1,000 sims, seeds 126700–126827, 12 workers;
  baseline `build/tierb_gate_base.csv` bit-identical re-measure, 21.1% /
  37.5 / 8.6):

  | config | wins | floor Δ | win Δ | score Δ | discordant |
  |---|---|---:|---:|---:|---:|
  | cards+rest+event, margin 1.0 | **36 (28.1%, +7.0pp)** | +1.38 CI [−0.82,+3.58] | +0.070 CI [−0.012,+0.152] | +2.09 CI [−0.61,+4.78] | 10 A / 19 B |
  | cards+rest+event, margin 0.5 | 31 (24.2%, +3.1pp) | +0.23 CI [−2.21,+2.68] | +0.031 | +0.55 | 13 A / 17 B |
  | cards+rest+event, margin 5.0 | 30 (23.4%, +2.3pp) | −0.09 CI [−1.47,+1.30] | +0.023 | +0.15 | 10 A / 13 B |
  | **ablation m1:** rest-only | 29 (22.7%, +1.6pp) | −1.22 | +0.016 | −1.06 | 11 A / 13 B |
  | **ablation m1:** event-only | 34 (26.6%, +5.5pp) | +0.45 | +0.055 | +1.00 | 10 A / 17 B |
  | **ablation m1:** cards-only (recall §73) | 29 (22.7%, +2.2pp) | −1.27 | +0.016 | −1.11 | 9 A / 11 B |

- **Verdict:** ➕ the strongest Phase-5 result so far. The **event gate is the
  main contributor** (+5.5pp wins alone; events were the default heuristic's
  weakest screen, §71 EVENT value MAE 5.21) and the layers are roughly
  additive (full stack +7.0pp). All 95% CIs still span zero (win CI at m1
  [−1.2, +15.2]pp) so the effect is not statistically established on this
  block, but the direction is consistently positive across margins, and floor
  and HP improve too (38.9 / 12.1 vs 37.5 / 8.6 at m1) — unlike §70's damage
  and §73's mixed card-only result. Margin 1.0 is the best point for the
  combined stack (0.5 and 5.0 are weaker), suggesting the extra layers benefit
  from the larger margins.
- **Artifacts:** `build/tierb_re_gate_{m1,m05,m5}.csv`,
  `build/tierb_rest_only_m1.csv`, `build/tierb_ev_only_m1.csv`.

## 75. Phase 5 round 5: token-based run state (V4) — ablation ladder + paired gate (2026-08-02)

- **Goal:** plan Phase-A items A1–A4 — replace the flat 1017-vector state of the
  OOC strategic net with a token-based run state (50 globals incl. 6 derived
  threshold features, counted deck tokens `(cardId, upgraded, count)` through a
  1-layer single-head self-attention, relic `(id, counter)` and potion
  `(id, count)` mean-pooled token encoders, plus a candidate entity embedding
  sharing the deck/relic/potion tables in the action encoder). Contract:
  `docs/knowledge-base/architecture/ooc-strategic-v4.md`. **No new datagen** —
  everything is derived from the existing §73 `build/strategic_tierb.csv`
  (3,057,708 rows / 4,650 seeds; sha256 `b28a3d83…1ae5` lineage, reused
  `_tok_state.bin` 482 raw float16 cols/row).
- **Implementation:** `train_strategic_tok.py` (rung-masked trainer,
  `STRAT_TOK_RUNG=1..4`; same losses/metrics as V3: group-CE + 0.5·per-screen
  value-MSE + 1.0·Q-MSE on `10·labelWon+labelHp`), `export_strategic_tok.py`
  (`OOC_STRAT_V4` binary, 807,432 B; numpy-vs-PyTorch parity logit 1.05e-05 /
  value 5.18e-06 / Q 3.12e-05), `strategic_tok_net.py` (shared module),
  `apps/ooc_strategic_tok_net.h` (`OocStrategicTokNet`; numpy-vs-native
  cross-check on 16 formula-generated cases: max |q| 2.41e-05, max |v| 2.06e-05),
  `apps/one_combat.cpp` (`buildTokState` mirroring `richRow` loops + thresholds,
  `tokEntity` per §2.5, env `STS_OOC_STRATEGIC_TOK_NN`; the four §74 gates score
  with the token net when loaded, V3 stays fallback; `STS_OOC_STRATEGIC_TOK_CHECK=1`
  parity hook: 0 mismatches vs `richFeatureVec` across 8 benchmark runs).
- **Held-out ablation ladder** (grouped 80/20 by `(seed,decIdx)`, seed 0,
  `STRAT_EPOCHS=40` each, CUDA; V3 reference from §73 = 60 epochs):

  | rung | state groups | pol top-1 | logit margin | val pol CE | value MAE | Q top-1 | Q MAE |
  |---|---|---|---:|---:|---:|---:|---:|
  | 1 | globals 50 only | 0.761 | 5.49 | 0.555 | 25.80 | 0.294 | 27.10 |
  | 2 | + deck tokens | 0.779 | 10.07 | 0.521 | 13.04 | 0.287 | 17.35 |
  | 3 | + relic/potion tokens | 0.777 | 9.38 | 0.526 | 11.05 | 0.291 | 16.70 |
  | 4 | + entity (full) | **0.790** | 10.01 | **0.492** | 11.37 | 0.282 | 17.00 |
  | 4 @60ep | final | **0.793** | **10.32** | **0.486** | 10.18 | 0.290 | 16.22 |
  | V3 ref | rich 1017 | 0.784 | 9.35 | — | 5.45 | 0.284 | 14.32 |

  Deck tokens carry the large held-out gains (value MAE 25.8→13.0, Q MAE
  27.1→17.4, margin 5.5→10.1); relic/potion and the entity add smaller
  increments; the full config's policy ranking (0.793) and val CE (0.486)
  exceed V3's, but absolute value/Q calibration stays worse (value MAE 10.2,
  Q MAE 16.2 vs V3 5.45 / 14.32).
- **Paired gate** (fair, A0, 1,000 sims, seeds 126700–126827, 12 workers;
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  sha256 `05178ec8…9e1ea`, `STS_OOC_STRATEGIC_REST=1`, `STS_OOC_STRATEGIC_EVENT=1`;
  baseline `build/tierb_gate_base.csv` bit-identical, 21.1% / 37.5 / 8.6;
  V3 reference arm = §74):

  | margin | wins | floor Δ | win Δ | score Δ | hp Δ | discordant |
  |---|---:|---:|---:|---:|---:|---:|
  | 1.0 | 27 (21.1%, +0.0pp) | +1.83 CI [−1.05,+4.65] | +0.000 | +1.34 CI [−4.57,+7.23] | +1.3 | 19 A / 19 B |
  | 0.5 | 28 (21.9%, +0.8pp) | +0.71 CI [−2.33,+3.68] | +0.008 | +2.36 CI [−3.71,+8.48] | +2.3 | 20 A / 21 B |
  | 5.0 | **31 (24.2%, +3.1pp)** | +0.80 CI [−2.14,+3.80] | +0.031 | +2.15 CI [−3.78,+7.97] | +1.8 | 9 A / 13 B |

- **Verdict:** ➖ mixed, and weaker than the V3 reference. The token encoder
  works (held-out ranking beats V3; the ablation ladder cleanly attributes the
  gain to deck tokens; deployed input parity verified bit-identical), and the
  deployed gate is directionally win-positive at margin 5.0 (+3.1pp, CIs span
  zero) with floor/HP gains at every margin — but it does **not** beat V3's
  +7.0pp @ m1 (36/128) on the same block, and the margin curve is the opposite
  shape (V4 improves with margin, V3 peaked at 0.5–1.0). Consistent with the
  §61/§62 history: better state representations improve held-out prediction
  without transferring to a deployed gate gain here. **V3 remains the deployed
  default** (`selfplay/models/ooc_strategic.native`); the V4 net stays opt-in.
  Follow-ups: (1) Q-calibration A/B — the V4 Q MAE (16.2) exceeds V3 (14.3),
  so the Q head (not the state encoder) may be the bottleneck; a V3-state +
  V4-architecture Q head would isolate this; (2) re-test after Phase-C combat
  outcome probes are available (the spec's §2.1 threshold set also lacks
  event-cost features — not logged in datagen); (3) keep the token machinery
  as the Phase-B encoder base (deck-set transformer, map DAG), since the
  pipeline is now proven end-to-end.
- **Artifacts:** `build/tok_gate_{m1,m05,m5}.csv`, `build/tok_check8.csv`;
  `selfplay/models/ooc_strategic_tok_{rung1..rung4,final}.{pt,_metrics.json}`,
  `selfplay/models/ooc_strategic_tok_final.native`, per-rung `_tok_state.bin`
  (2.9 GB each, regenerable); `train_strategic_tok.py`, `export_strategic_tok.py`,
  `strategic_tok_net.py`, `apps/ooc_strategic_tok_net.h`,
  `docs/knowledge-base/architecture/ooc-strategic-v4.md`.

## 76. Phase 5 round 6: one-ply Q gates for shop / TREASURE / boss relic (2026-08-02)

- **Goal:** complete the one-ply Q-gate coverage (plan Phase D; round-4
  follow-up 1). No datagen, no retrain: the §73 sample-all Tier-B labels and
  `strategicCands` already cover SHOP_ROOM / TREASURE_ROOM /
  BOSS_RELIC_REWARDS decisions. Pure C++ extension of the deployed V3 net.
- **Implementation (`apps/one_combat.cpp`):** three new gate functions mirroring
  `oocOnePlyEventPolicy` (dual-net V3/token path, margin gate
  `STS_OOC_STRATEGIC_MARGIN`, cats via `strategicCands`, tok entities via
  `tokEntity`): `oocOnePlyShopPolicy` (:3301, buy card/relic/potion,
  CARD_REMOVE, leave), `oocOnePlyTreasurePolicy` (:3345, chest open/skip),
  `oocOnePlyBossRelicPolicy` (:3389, three relics + skip). New flags default
  **off** so the §74/§75 configs stay reproducible:
  `STS_OOC_STRATEGIC_SHOP=1`, `STS_OOC_STRATEGIC_TREASURE=1`,
  `STS_OOC_STRATEGIC_BOSS_RELIC=1`. Wired into `runFullRunOOC` (shop before the
  shop-V branch, boss relic before `bossRelicVPolicy`, new treasure branch) and
  `runTraceRun`.
- **Paired gate** (fair, A0, 1,000 sims, seeds 126700–126827, 12 workers;
  `STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`
  `STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1`; baseline
  `build/tierb_gate_base.csv` bit-identical, 21.1% / 37.5 / 8.6):

  | margin | wins | floor Δ | win Δ | hp Δ | discordant |
  |---|---:|---:|---:|---:|---:|
  | **1.0** | **51 (39.8%, +18.8pp)** | +3.6 CI [+1.1,+6.0] | +0.188 CI [+0.094,+0.281] | +1.2 | 10 A / 34 B |
  | **0.5** | **51 (39.8%, +18.8pp)** | +5.4 CI [+3.1,+7.6] | +0.188 | +1.2 | 10 A / 34 B |
  | 5.0 | 27 (21.1%, +0.0pp) | +0.4 CI [−1.0,+1.9] | +0.000 | +0.4 | 11 A / 11 B |
  | ablation m1: shop-only | 31 (24.2%, +3.1pp) | +0.4 CI [−1.9,+2.7] | +0.031 | +0.4 | 13 A / 17 B |
  | ablation m1: **treasure-only** | **46 (35.9%, +14.8pp)** | +3.0 CI [+0.4,+5.6] | +0.148 CI [+0.062,+0.234] | +1.2 | 9 A / 28 B |
  | ablation m1: boss-only | 35 (27.3%, +6.2pp) | +1.4 CI [−1.2,+4.1] | +0.062 CI [−0.016,+0.141] | +0.7 | 10 A / 18 B |

- **Verdict:** ➕ **statistically established improvement — the strongest
  Phase-5 result.** Cards+rest+event+shop+treasure+boss-relic at margins
  0.5/1.0 = 39.8% wins vs 21.1% baseline (+18.8pp, win CI [+9.4,+28.1]pp and
  floor CI [+1.1,+6.0] excluding zero); margin 5.0 is neutral (gates barely
  fire). The shop gate alone is +3.1pp; the ablations attribute the bulk:
  **treasure-only +14.8pp (significant) is the dominant contributor** — the
  default chest policy skips small chests under Cursed Key
  (`ScumSearchAgent2.cpp::stepOutOfCombatPolicy`), and the Q head learns the
  state-dependent curse-vs-relic tradeoff from the Tier-B labels; boss-only
  +6.2pp (relic choice, incl. Cursed Key itself); roughly additive. Identical win
  outcomes at margins 0.5 and 1.0 on this block (runs are distinct files, same
  results). Determinism re-verified: m1.0 rerun bit-identical excluding the
  `sec` timing column.
- **Artifacts:** `build/r6_gate_{m0.5,m1.0,m5.0}.csv`, `build/r6_shop_only_m1.csv`,
  `build/r6_gate_m1_rerun.csv`.
- **Follow-ups:** (1) large secondary block (256–512 seeds) to tighten the CI
  on the headline; (2) ablation m1: treasure-only and boss-only to attribute
  the two contributors; (3) re-run the same gates on the V4 token net; (4)
  with the gate now statistically established, the §73-deferred PPO A/B
  (Phase-A item 5) and the V4 Q-calibration follow-up gain a stable reference.

## 77. Phase 5 round 7: Q-calibration isolation A/B (V3 state + V4 entity Q) (2026-08-02)

- **Goal** (§75 follow-up 1): decide whether the V4 token net's deployed
  shortfall is Q-head calibration (Q MAE 16.2 vs V3's 14.32) or the token state
  encoder. A/B: the V3 1017-vector state with a V4-style entity-conditioned
  action encoder, entity lever on/off.
- **Implementation:** `train_strategic_tok.py`-derived entity extraction
  (REWARDS/SHOP CARD/RELIC/POTION + CARD_SELECT, goldGePrice) feeding a
  Linear(37→32)→GELU→Linear(32→16) block on the V3 state encoder
  (Linear(1017→256)→LN→GELU→Dropout→Linear(256→128)); z = 184; pol/q heads
  Linear(184→96)→GELU→Linear(96→1); per-screen value heads on z_state.
  Losses/metrics identical to V3 (group-CE + 0.5·value-MSE + 1.0·Q-MSE).
  New file `train_strategic_qiso.py`; `QISO_ENTITY=0/1` env lever.
- **Held-out** (`build/strategic_tierb.csv`, grouped 80/20, 40 epochs, CUDA):

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V3 ref (§73) | 0.784 | 9.35 | — | 5.45 | 0.284 | 14.32 |
  | Q-iso entity=1 | 0.790 | 9.21 | 0.491 | 5.76 | 0.280 | 14.47 |
  | Q-iso entity=0 | 0.782 | 9.20 | 0.516 | 5.75 | 0.287 | 14.43 |

- **Verdict:** ➖ the Q head architecture is **not** the calibration bottleneck:
  both Q-iso configs land at Q MAE ≈ 14.4 (≈ V3's 14.32, well below V4's 16.2)
  — the token state encoder caused V4's worse absolute Q calibration. The V4
  entity conditioning on the V3 state is neutral for Q (0.280 vs 0.287 top-1)
  and mildly positive for policy ranking (top-1 0.790, val CE 0.491 vs 0.516).
  Implication: keep the V3 state for the deployed Q gates; any token-state
  revival must come from better encoders (Phase B) or combat-outcome probes
  (Phase C) closing the calibration gap, not from the Q-head shape.
- **Artifacts:** `selfplay/models/ooc_strategic_qiso.pt/_metrics.json`,
  `ooc_strategic_qiso_e0.pt/_metrics.json`; `train_strategic_qiso.py`.

## 78. Phase 5 round 8: PPO/GAE A/B (negative) + K=1 label-horizon gate A/B (2026-08-02)

- **Goal:** plan Phase-A item 5 — A/B a PPO/GAE policy objective against the
  CE+Q training on the same data (spec §A.10 starting points: γ=0.995/floor,
  λ=0.95, ε=0.2); and the §73 cross-cutting follow-up — K=1 vs K=3 label
  horizon, now tested end-to-end through the deployed gates.
- **Implementation:** `train_strategic_ppo.py` — trajectories reconstructed
  from `build/strategic_tierb.csv` (per-seed decision sequences by `decIdx`,
  successor state = next decision's state, Δf from the floor column, terminal
  r = 10·won+endHp), per-epoch frozen V̂_old/logit_old, backward GAE
  recurrence `A_t = δ_t + (γλ)^{Δf}·A_{t+1}` (vectorization verified against a
  naive loop on epoch 1), PPO-clip policy loss on valid chosen rows, value MSE
  on ALL group states, Q-MSE aux (10·labelWon+labelHp). V3-shaped 168-dim head
  contract so the A/B isolates the policy objective. K=1 data:
  `build/strategic_k1.csv` (649,968 rows / 1,000 seeds, offset 133000,
  `STRATEGIC_BRANCH_FIGHTS=1`, else the §73 config); the V3 CE+Q trainer
  (`train_strategic.py`) trained on it.
- **PPO result (negative):** the run diverged — epoch 30 held-out val_pol_ce
  7.80, policy top-1 0.277 (vs CE+Q's ~0.49/0.79), then crashed at epoch 31 on
  `assert np.isfinite(adv64).all()` (non-finite GAE advantages). A ratio
  overflow fix (clamp exp ratio to [0,1e2]) did not stop the logit drift; the
  policy logits/advantages become non-finite by epoch 31 with the raw-logit
  ratio surrogate and no entropy regularization on this behavioral dataset.
  **Verdict:** ❌ naive PPO-clip with raw-logit ratios on the behavioral
  Tier-A/B data does not train a competitive policy; CE+Q remains the policy
  objective. A salvage would need per-group logsumexp-normalized ratios,
  entropy regularization, and tighter per-epoch step control — deferred.
- **K=1 vs K=3 label horizon — held-out** (V3 architecture, same split):

  | labels | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | K=1 (1,000 seeds) | 0.771 | 5.76 | 0.552 | 2.83 | 0.306 | **7.50** |
  | K=3 (§73, 4,650 seeds) | 0.784 | 9.35 | — | 5.45 | 0.284 | 14.32 |

  K=1's Q calibration is far better (Q MAE 7.50 vs 14.32, top-1 0.306 vs
  0.284; value MAE 2.83 vs 5.45) — consistent with 1-fight targets
  compounding less bootstrap noise.
- **K=1 vs K=3 label horizon — deployed gate** (same full stack as §76, V3
  net replaced by the K=1-trained head; fair, 1,000 sims, seeds 126700–126827,
  baseline 21.1%):

  | config | wins | floor Δ | win Δ | discordant |
  |---|---:|---:|---:|---:|
  | K=1 head, margin 1.0 | 43 (33.6%, +12.5pp) | +3.6 CI [+1.3,+6.0] | +0.125 CI [+0.031,+0.219] | 11 A / 27 B |
  | K=1 head, margin 0.5 | 38 (29.7%, +8.6pp) | −0.0 CI [−3.0,+2.9] | +0.086 | 19 A / 30 B |
  | K=3 head (recall §76), margin 1.0 | **51 (39.8%, +18.8pp)** | +3.6 CI [+1.1,+6.0] | +0.188 CI [+0.094,+0.281] | 10 A / 34 B |

- **Verdict:** ➖ the K=1 head is statistically established at margin 1.0
  (+12.5pp) but **below the K=3 head (+18.8pp)**: its superior held-out Q
  calibration does not transfer to gate win rate, and its margin curve is
  inverted vs K=3 (m1.0 > m0.5). **K=3 labels remain the deployment choice.**
  **Inference:** the K=3 head's noisier targets produce larger Q margins, so
  the gate fires more often and the stronger-than-heuristic NN decisions
  dominate; a better-calibrated head with smaller margins defers to the
  heuristic more. Follow-ups: (1) combine K=1 and K=3 labels (multi-truncation
  mixture) as a calibration-vs-margin compromise; (2) a K=1 retrain on the full
  4,650-seed pool to rule out the data-volume confound.
- **Artifacts:** `build/strategic_k1.csv`, `build/k1_gate_{m1.0,m0.5}.csv`,
  `selfplay/models/ooc_strategic_v3_k1.{pt,native}`,
  `selfplay/models/ooc_strategic_ppo.pt` (diverged run), `train_strategic_ppo.py`.

## 79. Phase C step 1: combat outcome model C_ψ trained (no-peek entry) (2026-08-02)

- **Goal** (plan §5.4.1/5.4.2, spec §A.7): C_ψ(pre-combat state: deck,
  relics, potions, HP, encounter, ascension) → P(death), HP-loss quantiles,
  potion-use, turns. Inventory (wave track) found the labels already exist:
  `build/vdist.csv` (2,828,241 rows / 10.3 GB) carries `won, endHp, endTurn,
  potionsConsumed, pUsed0–43` per fight; the no-peek entry contract and the
  distributional heads both have prior art (`train_combat_transition_entry.py`,
  `train_combat_dist.py`). **No new datagen needed.**
- **Implementation:** `train_combat_cpsi.py` — first row per (seed, fightIdx)
  (verified turn==0), no-peek STRUCTURAL inputs (11 persistent scalars
  incl. 8 relic counters; one whole-deck-bag token; relics r0–127; potions
  pot0–43; encounter embedding; maxHp) — in-fight features never enter the
  model; EntityEncoder/CombatDistNet token architecture (dim 128, 4 heads,
  2 layers); heads: win BCE, death BCE, HP smooth-L1 (win-conditional), 11 HP
  quantiles (pinball), 44 potion-use BCE (masked to fights with consumption),
  turns smooth-L1(log1p); loss weights documented in the file. New self-contained
  export format `combat_cpsi_v1` (text) for later C++ probing.
- **Held-out (best-of-40 epochs, ~106k fights / 2.8M rows):** win_accuracy
  0.969, win Brier 0.0226, death Brier 0.0226, hp_mae_if_win 0.072 (7.2% of
  maxHp), end_hp_rmse 8.74, quantile pinball 0.026, potion BCE 0.0088,
  turns MAE 0.98.
- **Verdict:** ✅ the no-peek entry outcome model is highly accurate — battle
  outcomes are almost fully determined by the pre-combat state in this sim.
  Ready for the encounter-probe integration (plan §5.4.3, spec §A.8).
- **Artifacts:** `selfplay/models/v_combat_cpsi.{pt,txt,_val.csv}` (pt =
  torch checkpoint; txt = 4.7 MB `combat_cpsi_v1` export); `train_combat_cpsi.py`.
- **Correction (2026-08-03):** the original `combat_cpsi_v1` writer omitted the
  relic/potion/encounter projection weights, so the artifact could not
  reproduce the torch model (|ΔP(death)| up to 0.99, |Δturns| up to 3.4,
  measured by the C++ loader cross-check). Writer fixed
  (`train_combat_cpsi.py`, proj blocks after `encounter_embed`; loader
  defaults to identity when absent, PVNet convention) and the artifact
  re-exported from the checkpoint — C++ vs torch cross-check now
  **max abs err 2.4e-06** (`src/sim/search/CombatCpsiNet.*`, B2a).
  The §79 held-out metrics were computed from the .pt, unaffected.

## 80. Phase C step 2: encounter probes into the V4 state — held-out A/B (2026-08-02)

- **Goal** (plan §5.4.3, spec §A.8; §75 follow-up 2): feed matchup-aware
  combat predictions into the strategic state and re-test whether the V4
  token net's Q calibration gap closes. Probe source: the trained C_ψ (§79).
- **Implementation:** `probe_cpsi.py` — per strategic decision, evaluate C_ψ
  (no-peek entry inputs built from the rich state block; the 8 relic counters
  are not in the rich row and are set to 0, documented approximation) on 9
  probe slots: 6 fixed (TWO_LOUSE, GREMLIN_NOB, LAGAVULIN, THREE_SENTRIES,
  SLIME_BOSS, THE_GUARDIAN) + 3 actual upcoming (nextFight0, nextEliteId,
  bossId; INVALID → zeroed). Per slot: [P(death), P(win), hp_frac q50,
  hp_frac q10, turns, max potion prob] = 54 features, float16 npy
  (`build/strategic_tierb_probes.npy`, 3,057,708×54). Trainer lever
  `TOK_PROBES_FILE` appends the block to the V4 globals (fusion
  Linear(160→256)); `strategic_tok_net.py::Net(nprobes=9)` (default 0 keeps
  the export contract untouched).
- **Held-out** (`build/strategic_tierb.csv`, grouped 80/20, 40 epochs, CUDA):

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V4 plain (40ep, §75 ladder) | 0.790 | 10.01 | 0.492 | 11.37 | 0.282 | 17.00 |
  | **V4 + probes (40ep)** | 0.792 | 10.62 | 0.487 | 11.63 | 0.290 | 16.89 |
  | V4 plain (60ep, §75 final) | 0.793 | 10.32 | 0.486 | 10.18 | 0.290 | 16.22 |

- **Verdict:** ➖ neutral — the probes do not move the token-state metrics
  (Q MAE 16.89 vs 17.00 at equal epochs; Q top-1 0.290 vs 0.282, within noise).
  **Inference:** the V4 Q calibration gap is not driven by missing
  matchup information — C_ψ is highly accurate (win acc 0.969) yet its
  features add nothing beyond what the deck/relic/encounter tokens already
  encode. Consistent with §77: the gap is in how the token state conditions
  the Q head, not in the information available. Deployed probe integration
  (C++ C_ψ loader + probe feeding + gate benchmark) remains a Phase-C
  follow-up but is not expected to change this conclusion.
- **Artifacts:** `probe_cpsi.py`, `build/strategic_tierb_probes.npy`,
  `selfplay/models/ooc_strategic_tok_probes.{pt,_metrics.json}`.

## 81. Round 7b: V4 token net × full 7-gate stack (2026-08-03)

- **Goal** (Wave A0): the R6 gates (shop/TREASURE/boss-relic) were never
  benchmarked with the V4 token net — §75 only ran V4 with cards+rest+event
  (+3.1pp @ m5). Test the combination on the recorded block.
- **Config:** `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  (sha256 `05178ec8…9e1ea`) + `REST=1 EVENT=1 SHOP=1 TREASURE=1 BOSS_RELIC=1`,
  fair, 1,000 sims, seeds 126700–126827, baseline `build/tierb_gate_base.csv`
  (21.1% / 37.5 / 8.6).

  | margin | wins | floor Δ | win Δ | discordant |
  |---|---:|---:|---:|---:|
  | **1.0** | **53 (41.4%, +20.3pp)** | +5.7 CI [+2.8,+8.6] | +0.203 CI [+0.102,+0.305] | 12 A / 36 B |
  | 0.5 | 49 (38.3%, +17.2pp) | +3.0 CI [+0.2,+5.9] | +0.172 CI [+0.078,+0.266] | 11 A / 33 B |
  | 5.0 | 30 (23.4%, +2.3pp) | +0.6 CI [−1.0,+2.2] | +0.023 | 11 A / 14 B |

- **Verdict:** ➕ **the V4 token net with the full gate stack beats the V3 full
  stack (39.8% §76 vs 41.4%) at margin 1.0** (+20.3pp vs +18.8pp; both CIs
  exclude zero; overlap makes the net-vs-net delta not itself significant).
  The V4's previously weak deployed result (§75, cards+rest+event only) was a
  gate-coverage artifact — the token net's better policy ranking (0.793 vs
  0.784) and per-screen Q heads carry more value on the treasure/boss screens
  where the heuristic was weakest. Runtime cost: the tok net is ~3.5× slower
  per run (cpu_sec/run 27.2 vs 7.9 for V3) — deployment-relevant at 1,000 sims
  (wall 308 s vs 92 s on 12 threads).
- **Follow-ups:** (1) the §75 verdict is partially superseded — V4 has a
  deployed path; re-run the §77 Q-iso conclusion in this light (the state
  encoder still drives Q calibration, but gate ranking is what matters);
  (2) C1 (deck transformer) and the Phase-B ladder now have a live V4 baseline
  to beat (41.4% @ m1); (3) 256-seed secondary block should include the V4
  config too.
- **Artifacts:** `build/v4full_gate_{m0.5,m1.0,m5.0}.csv`.

## 82. Wave A1: margin refinement + 256-seed secondary block (2026-08-03)

- **Goal:** find the operating margin of the §76 V3 full gate stack (the
  0.5/1.0 plateau with 5.0 dead) and confirm the headline on a larger paired
  block.
- **Margin sweep** (V3 full stack, recorded 128-seed block, 1,000 sims):
  m1.5 37.5% (+16.4pp), m2.0 32.8% (+11.7pp), m3.0 27.3% (+6.2pp). Combined
  with §76 (m0.5/1.0 39.8%, m5.0 21.1%): **margin 1.0 is the operating point**
  (monotone decline beyond it). No better margin exists.
- **Secondary block** (seeds 126700–126955, 256 seeds, fair, 1,000 sims, 12
  threads; new fair baseline `build/sec256_base.csv` 23.0% / 37.2 / 9.1 —
  the extended range is slightly easier than the recorded block):

  | config | wins | floor Δ | win Δ | discordant |
  |---|---:|---:|---:|---:|
  | full stack @ m1.0 | **95 (37.1%, +14.1pp)** | +3.6 CI [+2.0,+5.3] | +0.141 CI [+0.078,+0.207] | 27 A / 49 B |

- **Verdict:** ➕ the §76 result holds at 2× the block size with a tight CI
  excluding zero. Combined with §81 (V4 full stack +20.3pp @ m1 on the 128
  block), the one-ply gate stack is the established deployment lever; margin
  1.0 is the recommended setting.
- **Note (config audit):** an A1 draft ran the 256-block baseline without
  `STS_FAIR=1` (known-RNG Searcher2 diverges from the recorded fair baseline —
  AGENTS.md trap) and was discarded; the fair rerun above is the recorded
  baseline. Determinism of the current binary on the recorded block
  re-verified (8/8 seeds bit-identical, excl. `sec`).
- **Artifacts:** `build/r6_gate_{m1.5,m2.0,m3.0}.csv`, `build/sec256_base.csv`,
  `build/sec256_gate_m1.csv`.

## 85. Phase E step 1: shop beam search — negative (2026-08-03)

- **Goal** (plan 5.6.1, hypothesis #6): beam search over shop purchase
  sequences (width 32, dedup by gold+offers+deck digest, leaf = run value)
  replacing the one-ply shop gate when `STS_OOC_SHOP_BEAM=1` (B1).
- **Implementation:** `oocShopBeamPolicy` (apps/one_combat.cpp) — beam 4..256
  (default 32), depth 0 = until leave/no affordable actions, node budget 4096,
  clones via `detachedCounterfactualCopy`, CARD_REMOVE's successor select
  expanded in-beam, leaf scored with the per-screen value head. First run
  scored leaves with the SHOP head regardless of the successor screen; fixed
  to use the node's actual `screenState` (the V2 successor convention) — both
  versions benchmarked.
- **Paired block** (fair, 1,000 sims, seeds 126700–126827, baseline 21.1%):

  | config | wins | floor Δ | win Δ | discordant |
  |---|---:|---:|---:|---:|
  | beam-only (leaf bug) | 12 (9.4%, −11.7pp) | −4.0 CI [−6.5,−1.6] | −0.117 CI [−0.188,−0.047] | 14 A / 5 B |
  | beam-only (leaf fix) | 15 (11.7%, −9.4pp) | −3.0 CI [−5.6,−0.5] | −0.094 CI [−0.169,−0.020] | 15 A / 6 B |
  | beam+full stack (leaf fix) | 34 (26.6%, +5.5pp) | +0.9 CI [−1.3,+3.2] | +0.055 CI [−0.047,+0.156] | 14 A / 29 B |
  | recall §76: full stack + one-ply shop gate @ m1 | **51 (39.8%, +18.8pp)** | +3.6 | +0.188 | 10 A / 34 B |

- **Verdict:** ❌ the shop beam does not compete with the one-ply shop gate.
  Beam-only is **significantly negative** (−9.4pp with the leaf fix) and
  beam+full-stack (+5.5pp) is far below the gate stack (+18.8pp): the
  per-screen VALUE head's successor-state scoring is a weak leaf signal
  (consistent with §71's successor-scoring weakness vs the direct Q head).
  Runtime is ~4× the gate config (cpu_sec/run 33 vs 8). The beam stays
  opt-in behind `STS_OOC_SHOP_BEAM=1`; **the one-ply shop gate remains the
  shop lever**. Follow-ups: a beam whose leaves use Q(s,leave) instead of the
  value head is the plausible salvage (multi-step lookahead with the Q
  contract), but the gate's +18.8pp already prices the shop well below this
  round's priority.
- **Artifacts:** `build/beam_{only,full}_m1.csv` (leaf-bug),
  `build/beam_{only,full}_fix.csv` (fixed); `apps/one_combat.cpp` (B1).

## 83. Wave A2: K=1+K=3 joint-label Q head (2026-08-03)

- **Goal:** test whether K=1's superior Q calibration (§78: Q MAE 7.5 vs 14.3)
  survives joint training with the K=3 labels and helps the deployed gate.
- **Implementation:** concatenated `build/strategic_tierb.csv` (K=3,
  4,650 seeds) + `build/strategic_k1.csv` (K=1, 1,000 seeds, disjoint ranges)
  → `build/strategic_mix.csv` (3,707,677 rows); V3 CE+Q trainer, 40 epochs.
- **Held-out:** policy top-1 0.783, margin 8.01, value MAE 6.14, Q top-1
  0.283, Q MAE 14.08, val CE 0.508 — Q MAE between K1 (7.5) and K3 (14.3),
  as expected with K=1 rows at ~17% of the mix.
- **Paired gate** (full §76 stack, margin 1.0, fair, 1,000 sims, seeds
  126700–126827, baseline 21.1%): **36.7% (+15.6pp, CI [+5.5,+25.8])** —
  significant, but below the K=3-only full stack (39.8%, +18.8pp §76).
- **Verdict:** ➖ the mixture does not beat K=3-only on the deployed gate;
  K=1's calibration advantage dilutes the K=3 margin signal without a
  compensating deployment gain (consistent with §78's inversion). **K=3
  labels remain the label contract**; the multi-truncation idea is closed for
  this trainer. Follow-up: the §78-proposed K=1 full-pool retrain (volume
  confound) is now moot for deployment — not pursued.
- **Artifacts:** `build/strategic_mix.csv`, `build/mix_gate_m1.csv`,
  `selfplay/models/ooc_strategic_v3_mix.{pt,native}`.

## 86. Phase B step 1 (C1): deck set transformer — held-out neutral (2026-08-03)

- **Goal** (plan 5.3.1): replace the V4 deck single-head attention with a
  2-layer transformer (dim 32, 2 heads, FFN 64, masked over valid tokens,
  mean-pool) — `STRAT_TOK_TRANSFORMER=1` lever on `train_strategic_tok.py`
  (export parity untouched; transformer off by default).
- **Held-out** (`build/strategic_tierb.csv`, grouped 80/20, 40 epochs, CUDA):

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V4 single-head (40ep) | 0.790 | 10.01 | 0.492 | 11.37 | 0.282 | 17.00 |
  | **V4 2-layer transformer (40ep)** | 0.793 | 10.39 | 0.487 | 10.59 | 0.289 | 16.62 |
  | V4 single-head (60ep, §75) | 0.793 | 10.32 | 0.486 | 10.18 | 0.290 | 16.22 |

- **Verdict:** ➖ neutral — the extra transformer capacity does not move the
  held-out metrics (Q MAE 16.62 vs 17.00 at equal epochs; within the
  60-epoch-noise band). The counted-token single-head attention was already
  sufficient; **the token-state Q calibration gap is not an attention-capacity
  issue** (consistent with §77/§80). The transformer config stays available
  via the lever; not pursued further for deployment.
- **Artifacts:** `selfplay/models/ooc_strategic_tok_transformer.{pt,_metrics.json}`;
  `strategic_tok_net.py`/`train_strategic_tok.py` levers.

## 87. Phase B step 2 (C4): distributional value heads — marginal (2026-08-03)

- **Goal** (plan §5 / spec §A.6): per-screen 11-quantile value heads on
  `10·won+endHp` (pinball loss, τ=0.05..0.95) as auxiliary targets alongside
  the per-screen mean heads — `STRAT_TOK_QUANTILES=1` lever.
- **Held-out** (`build/strategic_tierb.csv`, grouped 80/20, 40 epochs, CUDA):

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V4 baseline (40ep) | 0.790 | 10.01 | 0.492 | 11.37 | 0.282 | 17.00 |
  | **V4 + quantile heads (40ep)** | 0.792 | 9.44 | 0.488 | 11.28 | **0.296** | 16.76 |

- **Verdict:** ➖/➔ marginal — Q top-1 0.296 is the best Q ranking observed
  across all configs (V3 0.284, V4 0.282–0.290, C1 0.289), but Q MAE (16.76)
  and the policy metrics are within noise. The distributional auxiliaries
  give a small ranking nudge, not a calibration fix. Kept as a lever; not
  material enough alone to justify a deployment round.
- **Artifacts:** `selfplay/models/ooc_strategic_tok_quants.{pt,_metrics.json}`;
  `strategic_tok_net.py`/`train_strategic_tok.py` levers.

## 88. Phase B step 3 (C2): candidate–deck cross-attention — neutral; Phase-B conclusion (2026-08-03)

- **Goal** (plan 5.3.3): card candidates attend over the counted deck tokens
  (single-head cross-attention, valid tokens only) before the entity MLP —
  `STRAT_TOK_CROSS=1` lever (ent input 37→69 when on; export parity
  untouched).
- **Held-out** (`build/strategic_tierb.csv`, grouped 80/20, 40 epochs, CUDA):

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V4 baseline (40ep) | 0.790 | 10.01 | 0.492 | 11.37 | 0.282 | 17.00 |
  | **V4 + cross-attn (40ep)** | 0.782 | 9.00 | 0.511 | 11.53 | 0.289 | 16.69 |
  | C1 transformer | 0.793 | 10.39 | 0.487 | 10.59 | 0.289 | 16.62 |
  | C4 quantiles | 0.792 | 9.44 | 0.488 | 11.28 | **0.296** | 16.76 |

- **Phase-B conclusion:** all three encoder upgrades (transformer C1,
  distributional heads C4, cross-attention C2) are **held-out neutral** on the
  V4 token state (Q MAE 16.6–16.8 at equal epochs vs 17.0 baseline; policy
  metrics within noise, C2 slightly negative on policy). Together with §77
  (Q-head shape not the gap) and §80 (matchup probes not the gap), **the
  token-state Q calibration gap is not explainable by encoder capacity,
  action conditioning, or information content — it is the counted-token state
  contract itself** (vs the rich vector's per-card absolute counts). The
  token net's deployed strength (§81: 41.4% full stack) comes from gate
  ranking on the strong screens, not from held-out Q calibration. **Phase B
  encoder work on this base is concluded; further token-state investment
  should target the label contract or deployment, not encoders.**
- **Artifacts:** `selfplay/models/ooc_strategic_tok_cross.{pt,_metrics.json}`.

## 84. Wave A3: STRATEGIC_BRANCH_FUTURES A/B — more futures worse (2026-08-03)

- **Goal** (§73 follow-up 3): A/B the Tier-B label averaging across branch
  futures — futures=3 (3 independent branch seeds per action, averaged) vs
  the default futures=1 — on the deployed gate.
- **Implementation:** strategicgen2 datagen with `STRATEGIC_BRANCH_FUTURES=3`
  (else the §73 config) on seeds 134000–134999
  (`build/strategic_fut3.csv`, 659,612 rows / 1,000 seeds; the run was
  interrupted at 905 seeds and resumed at 134907; a duplicate resume process
  was killed and the file deduplicated — row-identical duplicates removed).
  V3 CE+Q retrain (40 epochs) + export + full-stack gate @ m1.0.
- **Held-out:** policy top-1 0.763, margin 5.73, value MAE 3.29, Q top-1
  0.284, Q MAE 11.14, val CE 0.566 (vs futures=1 §73: 0.784 / 9.35 / 5.45 /
  0.284 / 14.32 / —). More futures improve Q calibration (Q MAE 11.1 vs
  14.3) but hurt policy metrics — same calibration-vs-signal trade seen in
  the K=1 A/B.
- **Paired gate** (full stack @ m1.0, fair, 1,000 sims, seeds 126700–126827,
  baseline 21.1%): **34.4% (+13.3pp, CI [+3.9,+22.7])** — significant, but
  below futures=1's 39.8% (+18.8pp, §76). Discordant 43 (14 A / 29 B).
- **Verdict:** ➖ more branch futures are worse for the deployed gate —
  extra averaging dilutes the Q margin signal (the §78 K=1 inversion again:
  better label calibration does not transfer to gate win rate). **futures=1
  stays the label contract.** The label-contract space (K, futures) is now
  closed: K=3 × futures=1 is optimal among {K1,K3}×{futures1,futures3}.
- **Artifacts:** `build/strategic_fut3.csv`, `build/fut3_gate_m1.csv`,
  `selfplay/models/ooc_strategic_v3_fut3.{pt,native}`.

## 89. Per-screen margin sweep — global margin 1.0 confirmed (2026-08-03)

- **Goal:** test whether the one-ply gate margin should differ per screen
  (e.g. a lower card margin vs a higher shop margin). Per-screen knobs
  `STS_OOC_STRATEGIC_MARGIN_{CARD,REST,EVENT,SHOP,TREASURE,BOSS_RELIC}`
  (default: the global margin; bit-reproducible when unset) added to
  `apps/one_combat.cpp`.
- **Method:** coordinate sweep on the **GCP server** (`sts-test`,
  europe-west3-c, c4-highcpu-24, preemptible; binary parity verified
  bit-identical to the local binary on the anchor config, 8/8 seeds). Each
  screen swept at {0.1, 0.25, 0.5, 2.0} with all others at the 1.0 anchor
  (24 runs × 128 seeds, 1,000 sims, fair, 12 threads-equivalent); the 1.0
  point per screen = the `gates_ref_m1.csv` anchor itself.
- **Win rates by screen (anchor 39.8% = 51/128):**

  | screen | m0.1 | m0.25 | m0.5 | m2.0 | m1.0 (anchor) |
  |---|---|---:|---:|---:|---:|
  | CARD | 31.2 | 35.2 | 36.7 | 35.2 | **39.8** |
  | REST | 38.3 | 36.7 | 38.3 | 38.3 | **39.8** |
  | EVENT | 39.8 | 39.8 | 36.7 | 37.5 | **39.8** |
  | SHOP | 38.3 | 37.5 | 37.5 | 38.3 | **39.8** |
  | TREASURE | 39.1 | 39.1 | 39.8 | 35.2 | **39.8** |
  | BOSS_RELIC | 37.5 | 38.3 | 38.3 | **41.4** | 39.8 |

- **Verdict:** ➖ per-screen margins are not supported. **Cards are clearly
  worse below 1.0** (m0.1 −8.6pp, CI [−20.3,+3.1], discordant 20 A-only/9
  B-only — the §73 card-only peak at 0.5 does not survive inside the full
  stack; the other gates change the picture). All other screens are flat or
  worse at every non-1.0 point. The only point above the anchor is
  **BOSS_RELIC at m2.0 (+1.6pp, 2/4 discordant) — validated on the 256-seed
  block: +0.8pp vs the gates-on reference (CI [−1.2,+3.1], 8/256 discordant,
  3%)**. Per the pre-registered adoption rule (must clearly beat the
  reference on 256 seeds), **the single global margin 1.0 stays**; the
  per-screen knobs remain available and documented.
- **Artifacts:** `build/sweep_{SCREEN}_m{M}.csv` (24), `build/boss2_256.csv`;
  per-screen knobs in `apps/one_combat.cpp`; historical evidence
  `2026-08-03-ooc-per-screen-margins.md`.

## 90. Phase B step 4: combined encoder upgrades — negative; Phase B closed (2026-08-03)

- **Goal:** the only untested Phase-B hypothesis — do the individually-neutral
  encoder upgrades (C1 transformer, C4 quantile heads, C2 cross-attention)
  interact positively when combined (`STRAT_TOK_TRANSFORMER=1
  STRAT_TOK_QUANTILES=1 STRAT_TOK_CROSS=1`)?
- **Setup:** 40 epochs, `build/strategic_tierb.csv`, grouped 80/20; batch 2048
  + eval chunk 4096 (the other agent's GPU-resident state (2.95 GB) OOMs the
  transformer attention at batch 4096); `STRAT_TOK_COMPILE=0` (torch.compile
  also OOMs with the resident state; eager numerics).
- **Held-out:**

  | config | pol top-1 | margin | val CE | value MAE | Q top-1 | Q MAE |
  |---|---|---:|---:|---:|---:|---:|
  | V4 baseline (40ep) | 0.790 | 10.01 | 0.492 | 11.37 | 0.282 | 17.00 |
  | C1 / C4 / C2 individual best | 0.793 | 10.39 | 0.487 | 10.59 | 0.296 | 16.62 |
  | **Combined C1+C4+C2** | 0.783 | 9.60 | **0.515** | **13.41** | 0.290 | **18.38** |

- **Verdict:** ❌ the combination is the **worst** config of the whole ladder —
  worse than the baseline and every individual upgrade (Q MAE 18.38 vs 17.00,
  value MAE 13.41 vs 11.37, val CE 0.515 vs 0.492): the upgrades **interfere**
  when combined (added capacity/targets without added signal). Pre-registered
  deployment trigger not met (Q MAE > 15.5, Q top-1 < 0.30) → **no V5 export /
  C++ deployment round**. **Phase B is closed**: encoder capacity (C1),
  training signal (C4), and action conditioning (C2) do not fix the token-state
  Q calibration gap individually or jointly — the gap is the counted-token
  state contract itself (§88 conclusion confirmed). The V4 net's deployed
  strength (§81: 41.4% full stack) stands on its base encoder.
- **Artifacts:** `selfplay/models/ooc_strategic_tok_combined.{pt,_metrics.json}`;
  levers in `strategic_tok_net.py`/`train_strategic_tok.py`.

## 91. M1 wave: one-ply map route Q gate — negative at every margin (2026-08-04)

- **Goal** (plan 5.6.2, direct-Q-per-route scheme): extend the one-ply Q-gate
  coverage to MAP_SCREEN — score every legal child node of the visible map DAG
  with the strategic net's Q(s,a) head and execute the argmax only when its
  margin over the runner-up meets the gate; else `chooseMapAction` runs. The
  Tier-B CSV already contains MAP_SCREEN rows with counterfactual successor
  labels (all-decision sampling, §73), so **no datagen and no retrain**: this
  is purely the C++ gate extension.
- **Implementation (`apps/one_combat.cpp`):** `oocOnePlyMapPolicy` mirroring
  `oocOnePlyEventPolicy` (dual-net V3/token path, margin gate, cats via
  `strategicCands` MAP case: cand1=child x, cand2=row, cand3=room; tok entity
  path no-op for MAP). New flag `STS_OOC_STRATEGIC_MAP=1` (default **off**,
  so the §76/§81 configs stay reproducible), per-screen knob
  `STS_OOC_STRATEGIC_MARGIN_MAP` (sentinel -1.0 = global). Wired into
  `runFullRunOOC` (before the heuristic pathing branch) and `runTraceRun`.
- **Paired gate** (fair, A0, 1,000 sims, seeds 126700–126827, 24 threads,
  reference = the §76 full stack at m1.0, bit-identical to
  `gates_ref_m1.csv`):

  | config | wins | win Δ | floor Δ | discordant |
  |---|---:|---:|---:|---:|
  | full stack ref m1 (no map gate) | **51 (39.8%)** | — | — | — |
  | + map gate m0.5 | 30 (23.4%) | −16.4pp CI [−26.6,−6.2] | −4.5 CI [−7.0,−2.0] | 47 (34 A / 13 B) |
  | + map gate m1.0 | 31 (24.2%) | −15.6pp CI [−24.2,−7.0] | −4.6 CI [−6.7,−2.5] | 34 (27 A / 7 B) |
  | + map gate m5.0 | 26 (20.3%) | −19.5pp CI [−28.9,−10.2] | −4.5 CI [−7.0,−2.2] | 43 (34 A / 9 B) |

- **Verdict:** ? the map Q gate is a clear negative at every margin — even m5.0
  (where the other gates are neutral) is the *worst* point, so the Q head's MAP
  rankings are anti-predictive *wherever it fires*. Consistent with the §62
  history (graph-NN pathing rejected: "better absolute prediction does not
  identify the causal best route") and §66m/§70/§73 (un-gated or weakly
  calibrated NN overrides damage the heuristic): the trained Q head conditions
  on `(child x, row, room)` via the 6-cat embeddings only, with no downstream
  route information, so it cannot beat the tuned bottom-up DP
  (`chooseMapAction`), which carries full-map downstream value. **The
  direct-Q-per-route scheme for map decisions is falsified on the current V3
  net**; the one-ply map gate stays **off by default** (opt-in only). M2 (route
  search) must not rely on this Q head for route scoring without the map DAG
  encoder (5.3.2) or a C_ψ-conditioned leaf.
- **Artifacts:** `apps/one_combat.cpp::oocOnePlyMapPolicy`; per-seed CSVs
  `ref_m1.csv`, `map_m{0.5,1.0,5.0}.csv` (retained on the GCP server
  `/tmp/m1_bench/`); rerun determinism verified bit-identical excluding the
  `sec` column.

## 92. C1 wave: V4 token net full gate stack on the 256-seed block (2026-08-04)

- **Goal** (§81 follow-up 3, historical evidence follow-up 1): the 256-seed secondary
  block (§82) only tested the V3 stack; the V4 config needed the same larger
  block before any default-flip consideration. Same config as §81:
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, margin 1.0, fair, 1,000 sims,
  seeds 126700–126955.
- **Result:** **105/256 (41.0%)** wins, avg floor 42.0, avg HP end 20.9
  (`/tmp/c1_v4_256.csv` on the GCP server). Reference points on the same
  block: flags-off baseline 23.0% (`sec256_base.csv`, §82) and V3 full stack
  95/256 = 37.1% (`sec256_gate_m1.csv`, §82) → **V4 +18.0pp over baseline,
  +3.9pp over V3 on the identical block** (both nets on the same seeds and
  config, differing only in the artifact; the V3-256 per-seed CSV is not
  present here, so the +3.9pp is a same-block aggregate comparison, not a
  paired-match test).
- **Verdict:** the V4 top-arm result holds at 2× the block size; the
  V3-vs-V4 delta on the 256 block matches the 128-block direction (§81:
  V4 41.4% vs V3 39.8%). Runtime: ~10.3 cpu-sec/run vs V3's ~8 (§82) — the
  tok net's ~25% overhead persists. **No default flip is made here**: the
  gates stay opt-in; V4 remains the top measured arm and the V3 reference
  stays the pairing baseline.
- **Artifacts:** `c1_v4_256.csv` (GCP server `/tmp/c1/`).

## 93. M2 wave: C_psi short-horizon map route search — negative at every margin (2026-08-04)

- **Goal** (plan 5.6.2, spec A.11 "map routes"; re-scoped by §91): replace the
  falsified direct-Q map gate with a route search that prices each legal child
  of the visible map DAG down HORIZON=3 rows using the C_ψ combat surrogate
  (`CombatCpsiNet`, §79/§80): fights return pool-averaged P(death) and
  E[hp/maxHp | win] (act strong pool for hallways, elite pool for elites),
  rests heal a fixed 30% of max HP, shops/treasures/events pass through
  (documented v1 limitation); a route's value = survival-probability × the
  strategic V-head (MAP screen) at the leaf state with map position advanced
  and expected HP applied; child = max over downstream paths; margin-gated.
- **Implementation (`apps/one_combat.cpp`):** `oocMapRouteSearchPolicy` +
  `mapRouteSearch`/`mapRouteLeafValue`/`routeCpsiExpect` (C_ψ expectation
  memoized per node across children); C_ψ wired via new `STS_CPSI_NN=<path>`
  (loader existed since B2a); `STS_OOC_MAP_ROUTE=1`,
  `STS_OOC_MAP_ROUTE_HORIZON` (2..5). Route search takes precedence over the
  M1 gate when enabled; both stay off by default. Hidden info: encounters are
  pool expectations from the act's visible pools — never the run's true
  future encounter list (spec A.14 clean); the boss row (y==14) is not
  expanded (leaf V prices the remaining run).
- **Paired gate** (fair, 1,000 sims, seeds 126700–126827, 24 threads;
  reference = the §76 full stack at m1.0, bit-identical to `gates_ref_m1.csv`
  / §91 `ref_m1.csv`; the other six gates stayed ON in both arms — the A/B
  isolates only the map pathing layer):

  | config | wins | win Δ | floor Δ | discordant |
  |---|---:|---:|---:|---:|
  | full stack ref m1 (heuristic pathing) | **51 (39.8%)** | — | — | — |
  | + route search m0.5 | 49 (38.3%) | −1.6pp CI [−10.9,+7.8] | **+2.0 CI [+0.1,+4.0]** | 36 (19 A / 17 B) |
  | + route search m1.0 | 38 (29.7%) | **−10.2pp CI [−18.0,−3.1]** | −1.4 CI [−3.3,+0.6] | 25 (19 A / 6 B) |
  | + route search m5.0 | 25 (19.5%) | **−20.3pp CI [−29.7,−10.9]** | −3.0 CI [−5.5,−0.6] | 40 (33 A / 7 B) |

  (Weighted pool expectation — `strongWeights` for hallways, uniform elites —
  the recorded config; an earlier uniform-pool run gave the same verdict:
  −3.1/−9.4/−21.1pp.)

- **Verdict:** ? the C_ψ route search is a clear negative: significant damage
  at m1.0/m5.0, neutral at m0.5 (win −1.6pp but floor **+2.0pp significant** —
  the search routes deeper without converting to wins). The margin signature
  mirrors §91/M1 — the more the search overrides the tuned bottom-up DP
  (`chooseMapAction`), the worse — so **the C_ψ+pool surrogate continuation
  and the MAP-screen V-head leaf do not provide a usable route signal
  either**. Consistent with §62's standing lesson: "training pooled the
  routes chosen by the heuristic, while inference asks for unseen singleton
  alternatives" — the next justified version needs paired counterfactual
  outcomes per legal child (Tier-B-style route labels) or a route-conditioned
  leaf (map DAG encoder, 5.3.2), not more epochs of the same state contract.
  **Both direct map overrides (M1 Q gate, M2 C_ψ route search) are falsified
  on the current nets; the heuristic pathing stays the map layer.** M3 (map
  DAG encoder) remains the open lever, held out on the tierb pipeline first.
- **Artifacts:** `apps/one_combat.cpp::oocMapRouteSearchPolicy`; per-seed
  CSVs `ref_m1.csv`, `m2w_m{0.5,1.0,5.0}.csv` (GCP server `/tmp/m2w_bench/`);
  C_ψ artifact `selfplay/models/v_combat_cpsi.txt` (also mirrored to
  `build/` for local smoke).

## 94. Wave A1: Q_win objective — probability action-value head + aux heads, V_win calibration finding (2026-08-04)

- **Goal** (Q-refine wave A1): replace the composite Q target `10·labelWon +
  labelHp` with a pure win-probability action value `Q_win(s,a) =
  P(eventual run victory | s,a,π)`: sigmoid output trained with soft-label BCE
  on the already-existing `labelWon` (0/1 terminal + `vStateWin` bootstrap,
  futures-averaged — one_combat.cpp:3811/:6003). HP/floor become separate
  auxiliary probability heads (never summed into the action score). Win =
  `PLAYER_VICTORY` consistently across datagen, bootstrap, benchmark.
- **Trainer (`train_strategic.py`):** `q_win_target = labelWon`; Q head BCE
  (`STRAT_QLAMBDA`); new `q_hp` (`labelHp/maxHp`) and `q_floor`
  (`labelFloor/60`) aux heads with their own BCE weights (`STRAT_HPLAMBDA`,
  `STRAT_FLOORLAMBDA`); metrics now on the probability scale (q_brier,
  q_cal_max decile calibration, q_hp_mae, q_floor_mae); `STRAT_PATIENCE`
  early stop (stop after N epochs without held-out val_pol_ce improvement).
- **Export/native:** new artifact magic `OOC_STRAT_V5` (sigmoid on Q/aux, aux
  weight blocks appended); the loader accepts BOTH `OOC_STRAT_V3` (legacy,
  bit-identical behavior) and `OOC_STRAT_V5`; parity asserted 32 samples
  (V5 Q 9.8e-07, aux ≤ 6.7e-07). Old V3 artifacts remain loadable — the
  §76/§81/§91/§93 references reproduce seed-for-seed on the new binary.
- **V_win bootstrap calibration (the conversation's bootstrap-problem check,
  `check_vwin_calibration.py`):** the native win trees (`build/v_win_trees.txt`,
  1060 trees) are **mildly over-predicting but not grossly miscalibrated**. An
  initial checker bug (base_score treated as a probability added directly to
  leaf margins instead of converted to logit space, as the C++ `WinNet::predict`
  does) produced a false "Brier 0.232, max decile 0.42" headline; after the
  logit fix and a C++/Python **parity check** (`parity_vwin.py`, max |diff|
  0.000000 over 200 rows via the new `winnettest` mode), the true numbers on
  49,976 terminal chosen rows are: Brier 0.153 (vs the always-0.30 baseline
  0.209), log loss 0.471, max decile error 0.18 (over-predicts 0.62 vs 0.47
  and 0.79 vs 0.62 at mid-high values — the classic few-wins XGBoost shape).
  **Inference:** V_win error still propagates into every censored `labelWon`
  and biases Q_win labels upward, but the bias is modest and roughly monotone —
  a small Platt/isotonic recalibration (fit on terminal rows) is the fix
  (§95). Follow-up decision recorded: recalibrate before trusting
  probability-point margins.
- **Fresh training data:** `strategicgen2` on new seeds 200000–201439
  (1,440 seeds → 900,916 rows / 215,234 decisions, 1.92 GB
  `build/strategic_qwin.csv`, GCP server; §73 config — sample-all, branch
  fights 3, branch sims 150/100/50, futures 1 — **minus the absent
  `v_combat_fair_trees.txt` VNet leaf**: recorded deviation). ~20 min on 24
  threads.
- **V3 Q_win retrain (laptop CPU, Intel iGPU/no CUDA, `STRAT_DEVICE=cpu`):**
  40-epoch budget with `STRAT_PATIENCE=6` → **early stop at epoch 30, best
  epoch 24** (no val_pol_ce improvement for 6 epochs, as the user
  requested). Held-out (43,047 groups): **policy top-1 0.792, val_pol_ce
  0.474** (comparable to the V3 reference's 0.784); **q_brier 0.053,
  q_mae 0.173, q_cal_max 0.016** (well calibrated against the biased
  labels); q_hp_mae 0.257, q_floor_mae 0.080. Artifacts
  `selfplay/models/ooc_strategic_qwin.{pt,_metrics.json,_state.bin,native}`
  (V5).
- **Smoke:** trainer 2-epoch synthetic run; exporter parity (V3 and V5);
  loader accepts both magics; legacy V3 full-stack run on the new binary
  **bit-identical seed-for-seed to `ref_m1.csv` (39.8%)**; V5 gate smoke at
  probability-point margins (0.01/0.03/0.05) fires without crash.
- **Status:** Wave A1 delivered (code + trained V5 artifact, opt-in); the
  probability-point margin sweep and the regret gate (Wave B) are the next
  steps, gated on the V_win calibration decision; Q_boss aux head deferred to
  a follow-up round (needs a `strategicgen2` branch-level boss-flag label
  column).

## 95. Wave A2: V_win bootstrap recalibration — parity check, isotonic fit, corrected labels (2026-08-04)

- **Goal** (Wave A2, the bootstrap-problem fix): remove the modest but
  systematic V_win over-prediction from the Q_win labels so probability-point
  margins are trustworthy. Fit a monotone map `C(p)` on terminal rows
  (`labelBootstrap==0`, where `won` is the true outcome) with a seed-held-out
  split, then apply `C` to every censored `labelWon` (which with
  `STRATEGIC_BRANCH_FUTURES=1` IS `V_win(s_cutoff)`) and write a corrected CSV.
- **Parity check first (new `winnettest` mode + `parity_vwin.py`):** the
  Python tree-walk must match the deployed C++ `WinNet::predict` before any
  fit is trusted. `one_combat winnettest <trees> <csv> [rows]` parses a
  tierb-schema CSV, runs the native WinNet on each rich state block, and
  prints `rowidx,vwin`; `parity_vwin.py` re-predicts the same rows in Python.
  **Result: max |diff| 0.000000 over 200 rows — bit-identical.** This also
  caught and corrected the §94 checker bug (base_score must be converted to
  logit space, `log(p/(1-p))`, before adding leaf margins).
- **Fit (`fit_vwin_calibration.py`):** all 216,625 terminal rows (chosen +
  counterfactual branches), 80/20 seed split (1,152 fit / 288 val seeds;
  173,084 / 43,541 rows). Candidates fit on the fit split, selected by
  held-out Brier/log-loss/max-decile:

  | map | val Brier | val logloss | max decile |
  |---|---|---:|---:|
  | raw V_win | 0.1512 | 0.4643 | 0.2373 |
  | Platt (a=0.971, b=−0.652) | 0.1321 | 0.4150 | 0.0762 |
  | **isotonic (PAVA, selected)** | **0.1310** | **0.4105** | **0.0789** |

  Isotonic selected; the decile table after the map is flat (0.02→0.01 …
  0.91→0.93). Map artifacts: `build/strategic_qwin_cal_calmap.json`
  (chosen map, Platt params, metrics).
- **Corrected dataset:** `build/strategic_qwin_cal.csv` — same schema, only
  `labelWon` changed on the 684,291 censored rows (76%); censored mean
  0.4547 → **0.3369** (terminal rate 0.31). State block byte-identical →
  the 1.8 GB `_state.bin` transfers by copy under the new OUT name
  (`ooc_strategic_qwin_cal_state.bin`, trainer byte-size reuse verified).
- **Retrain:** V3 Q_win on the corrected CSV (laptop CPU, 40 epochs, patience
  6). **Interrupted by the session move to the desktop at epoch 20** — not a
  complete checkpoint; the desktop GPU run supersedes it. Partial log showed
  the corrected-labels run trending better than the biased one at the same
  epoch (epoch 20: q_brier 0.0439 / q_cal_max 0.0216 vs the biased run's
  epoch 20: 0.0563 / 0.0562), as expected.
- **Verdict:** the bootstrap bias is real but modest (max decile 0.24 raw),
  and the isotonic map cuts it to 0.08 on held-out seeds. The corrected
  dataset + retrain is the trustable basis for the probability-point margin
  sweep and the regret gate (Wave B). Limitation recorded: the map is fit on
  terminal (decision-state) rows and applied to censored (cutoff-state)
  values under the standard calibration assumption P(y|p) stable in p; the
  definitive transfer check is a short longer-horizon datagen (K=6, ~50–100
  seeds), deferred.
- **Artifacts:** `check_vwin_calibration.py`, `parity_vwin.py`,
  `fit_vwin_calibration.py` (new); `apps/one_combat.cpp` `winnettest` mode;
  `build/strategic_qwin_cal.csv` + `_calmap.json`; interrupted partial
  `selfplay/models/ooc_strategic_qwin_cal_train.log`.

## 96. Wave A1/B sweep: Q_win probability-point margins + regret gate — both negative (2026-08-04)

- **Goal** (ooc-qwin-continuation.md Steps 4–5): with the corrected-label V3
  Q_win retrain and V5 export done, sweep the one-ply gate margin in
  probability-point units m ∈ {0.01, 0.03, 0.05, 0.10} for the calibrated
  (`ooc_strategic_qwin_cal.native`, md5 3ac8343d…) and biased
  (`ooc_strategic_qwin.native`, md5 a8a323c0…) V5 artifacts, then evaluate the
  Wave B regret gate `Qmax(s) − Q(a_heur) > ε` at the same thresholds.
- **Training note:** the desktop `build/strategic_qwin_cal.csv` (7.57 GB,
  809,146 rows, 1,295 seeds) was truncated at the last line by the transfer
  (a malformed trailing row with NaN labels poisoned a valid policy group →
  NaN group-CE → `loss.backward()` crash with "element 0 of tensors does not
  require grad"). The file was truncated at the last complete line; retrain:
  `STRAT_EPOCHS=40 STRAT_PATIENCE=6 train_strategic.py` → best epoch 40
  (no early stop), val_pol_ce 0.4671, policy_top1 0.7967, q_brier 0.0409,
  **q_cal_max 0.0647 (doc target <0.03 missed)**; epoch-10 had q_cal_max
  0.0199 but q_brier 0.0525. Export parity 32/32 (max logit err 9.9e-06).
- **A/B (own held-out splits; different datasets — indicative only):**
  calibrated vs biased: q_brier 0.0409 vs 0.0532 (better), q_cal_max 0.0647
  vs 0.0160 (worse), q_mae 0.146 vs 0.173, policy_top1 0.797 vs 0.792.
- **Truth-check (`check_vwin_calibration.py --ckpt`, new mode; 44,865
  terminal chosen rows of the corrected CSV, both checkpoints on the same
  rows):** V_win trees Brier 0.155 / max decile 0.184 (over-confident top,
  known bias); biased Q_win head Brier 0.097 / decile 0.306; calibrated head
  Brier 0.113 / decile 0.376 — **both heads are UNDER-confident at the top
  deciles, not over-confident: the bootstrap bias did not propagate into the
  head as inflation, and recalibration (which lowered censored labels)
  shifted the head further down on terminal rows** (expectation in §94/§95
  not met; the K=6 transfer validation stays the definitive test).
- **Paired margin sweep** (fair, A0, 1,000 sims, seeds 126700–126827, 24
  threads; reference = §76 full stack at m1.0, bit-identical
  `gates_ref_m1.csv`, 39.8%; full one-ply gate stack
  `STS_OOC_STRATEGIC_NN=<artifact> STS_OOC_STRATEGIC_{REST,EVENT,SHOP,
  TREASURE,BOSS_RELIC}=1`; MAP/M2 off; per-seed CSVs on the GCP server
  `/tmp/qwin_sweep/`, pulled to `build/`):

  | config | wins | win Δ | floor Δ | discordant |
  |---|---:|---:|---:|---:|
  | ref m1 (V3 legacy) | **51 (39.8%)** | — | — | — |
  | biased m0.01 | 43 (33.6%) | −6.2pp CI [−15.6,+3.1] | −2.8 CI [−4.9,−0.7] | 38 |
  | biased m0.03 | 33 (25.8%) | −14.1pp CI [−24.2,−4.7] | −2.9 CI [−5.4,−0.4] | 44 |
  | biased m0.05 | 29 (22.7%) | −17.2pp CI [−26.6,−7.0] | −3.4 CI [−5.9,−1.0] | 46 |
  | biased m0.10 | 28 (21.9%) | −18.0pp CI [−28.1,−8.6] | −3.5 CI [−5.9,−1.1] | 45 |
  | calibrated m0.01 | 35 (27.3%) | −12.5pp CI [−21.1,−3.9] | −3.8 CI [−6.1,−1.6] | 34 |
  | calibrated m0.03 | 32 (25.0%) | −14.8pp CI [−24.2,−5.5] | −3.0 CI [−5.4,−0.6] | 43 |
  | calibrated m0.05 | 29 (22.7%) | −17.2pp CI [−27.3,−7.8] | −3.5 CI [−5.9,−1.1] | 44 |
  | calibrated m0.10 | 28 (21.9%) | −18.0pp CI [−28.1,−7.8] | −3.5 CI [−5.9,−1.1] | 45 |

  (Baseline flags-off 21.1% / 37.5 / 8.6 = `build/tierb_gate_base.csv`.)

- **Paired regret-gate sweep** (same block; calibrated V5 artifact, gate
  flags on, `STS_OOC_STRATEGIC_GATE=regret`, margin fallback 1.0,
  ε ∈ {0.01, 0.03, 0.05, 0.10}):

  | config | wins | win Δ | floor Δ | discordant |
  |---|---:|---:|---:|---:|
  | regret ε0.01 | 25 (19.5%) | −20.3pp CI [−29.7,−10.9] | −7.5 CI [−10.3,−4.7] | 42 |
  | regret ε0.03 | 29 (22.7%) | −17.2pp CI [−26.6,−7.8] | −3.7 CI [−5.9,−1.5] | 42 |
  | regret ε0.05 | 27 (21.1%) | −18.8pp CI [−28.1,−9.4] | −4.4 CI [−6.7,−2.1] | 44 |
  | regret ε0.10 | 29 (22.7%) | −17.2pp CI [−26.6,−7.8] | −4.0 CI [−6.3,−1.7] | 42 |

- **Verdict:** both waves negative. (1) The Q_win gate stack loses to the V3
  legacy reference at every tested margin; the only CI-spanning-zero point is
  biased m0.01 (−6.2pp). (2) Recalibration did NOT improve policy quality:
  at m0.01 the biased artifact is best (33.6% vs 27.3%); at m≥0.03 the two
  artifacts are indistinguishable and ≈ baseline, so the Q_win head only
  contributes at the loosest margin. (3) The regret gate is ≈ baseline at
  every ε (it takes the heuristic action when regret ≤ ε, so it degrades
  toward the heuristic) and its Q-max overrides hurt — strictly worse than
  the margin gate at the same thresholds. **Pre-registered adoption rule
  (beat margin-gate reference on 128 AND hold on 256) fails at 128 — no 256
  run; the regret gate stays opt-in (default off), as do the Q_win
  artifacts.** Consistent with §91/§93: replacing the proven V3 stack with a
  new objective/head damages performance on this block. The V3 legacy stack
  at m1.0 (39.8%) remains the deployed reference.
- **Implementation:** `apps/one_combat.cpp` — Wave B regret gate
  `regretGateChoose`/`regretGateTail` + per-screen live-fallback heuristic
  runners (`regretHeur*`), env `STS_OOC_STRATEGIC_GATE=regret`,
  `STS_OOC_STRATEGIC_GATE_EPS` (default 0.03), wired into all one-ply gates +
  M2; margin path byte-identical with the flag off (verified on the recorded
  block). First regret attempt mis-specified SHOP's a_heur as the datagen
  default (relic-buy-or-random) instead of the live `shopVPolicy` fallback
  and measured 13.3–18.8%; after the fix (t_shopV + live-fallback runners)
  the rerun gives the numbers above — the SHOP a_heur mismatch was the
  damage, but the corrected gate still does not help.
- **Process findings:** (a) the server tree is an rsync copy — after syncing
  only `one_combat.cpp` the build silently linked against the stale
  pre-V5 `apps/ooc_strategic_net.h` and the V5 model failed to load
  ("truncated payload" → silent gate fallback → all runs measured the
  flags-off baseline); sync the net headers with the driver. (b) The
  transferred CSV truncation (above) crashed the trainer with a
  misleading autograd message. (c) GCP VM had been terminated; `gcloud
  compute instances start` before sweeping.
- **Artifacts:** `selfplay/models/ooc_strategic_qwin_cal.{pt,native,
  metrics.json}` (+`_state.bin`), `ooc_strategic_qwin_cal_train.log`,
  `check_vwin_calibration.py` (`--ckpt` mode), per-seed CSVs
  `build/qwin{,_cal}_m*.csv`, `build/regret_cal_e*.csv` (server
  `/tmp/qwin_sweep/`).

