## Current findings summary (2026-08-08)

Brief orientation before searching the full ledger. The canonical configuration
and current numbers live in `docs/knowledge-base/evaluation/current-baselines.md`.

### Accepted (confirmed by multiple gates)

- **Searcher3 ISMCTS > Searcher2 fair-play** (~+39pp win, §early S3 entries).
- **V4 one-ply Q gate stack significantly raises win%** (card/rest/event/shop/
  treasure/boss-relic; +8-14pp vs flags-off baseline, §76/§82/§99).
- **V4 token net ≈ V3 strategic net** at matched budgets (§92/§99); V4 is the
  deployed format since 2026-08-03.
- **S3−belief−chain is the current particle config**: belief+chain ON costs
  −11.3 to −12.1pp, significant (§124).
- **V_combat honest-data leaf @α=0.3**: +12.5pp at ~2-2.4× cpu, three
  independent gates confirm (§126). Now default ON in the fair-S3 path.
- **Forced-move contraction is decision-neutral** at −8.5–18% cpu (§120/§121/§123).
- **`STS_LIVE_VALID` fair-tree fix**: +5.5–5.9pp win at +7.9–14.6% cpu (§122/§123).
  Default ON in the fair-S3 path since 2026-08-07.
- **Native OOC GBMs replace v_server** for floor/win inference (§43/§68).
  The server is only required by self-play meta and some experimental endpoints.
- **Compact policy prior auto-loads** (+4.3pp win over plain UCB, §26).
- **Heuristic path + shop-V + win-rest** is the default OOC stack without gates.

### Falsified / closed (do not re-investigate without new evidence)

- **Devalue-high-HP objective** — negative (§3, evalcombat/evalrun modes removed).
- **Convergence-based early stopping** (`STS_CONVERGE`) — no free lunch (§22).
- **Root-stability early stopping** (`STS_CONV_ROOT`) — falsified at gates (§118).
- **Non-fair forced-move contraction** — divergent results, restricted to fair
  path only (§120/§121).
- **S3 deterministic chain compression** — net-negative on binary gates (§106).
- **S3 particle belief reweighting** — costs −11 to −12pp (§124).
- **Distilled native combat MLP** — rejected at 500 paired seeds (§56).
- **Entity-aware multi-head combat model** — rejected at 500 paired seeds (§57).
- **A4 one-turn rollout bootstrap** — falsified at gates (§133).
- **A1 K-rollouts** — NULL result (visited, no improvement pattern).
- **V_combat legacy (known-RNG data) on Searcher3** — rejected; the honest-data
  retrain (§126) is the new baseline.

### Open questions

- Can the all-act checkpoint rollout be distilled into a deployable NN? (§66/§143).
- Tactical turn-beam rollout (B1, §plan-rollout-experiments) — gate pending.
- Dynamic α by rollout length (A2) — gate pending.
- Policy-filtered rollout (A3) — gate pending.
- S3 leaf-value cache (`STS_PVNET_CACHE`) — on by default, behavior-preserving;
  `STS_PVNET_COND_*` gates for deployment speed still experimental.

### Recommended starting points for new experiments

- OOC: V4 token-net gate stack at margin 1.0 (baseline: §124 `b2c_1k_64p.csv`).
- Combat: Searcher3 fair-path with `STS_S3_BELIEF=0 STS_S3_CHAIN=0` and
  honest-data V_combat default ON (baseline: §126 `vnet_all_a03_1k.csv`).
- Evaluation: `bestbench` paired-gate protocol; 256-seed block 126700–126955.

---

## §2026-08-10 Searcher3 real-observation belief filtering (filter-only)

**Question:** Can exact real-transition posterior filtering improve the carried
Searcher3 belief, after the prior audit selected the belief line over root
allocation? This was diagnostic-first; no gameplay default was changed.

**Pre-implementation audit:** `docs/knowledge-base/decision-log/2026-08-10-s3-real-belief-filter-audit.md`.
The old `drawOrderConsistent` prefix predicate is not a posterior test across
card play, discard/exhaust, generated cards, reshuffle, enemy effects, or RNG
advancement. The new filter propagates each particle from a copied pre-action
`BattleContext` through the exact real `Action::execute` transition and compares
player-visible `CombatObservation` equality. Hypothetical MCTS updates remain
off by default.

**Implementation:** Opt-in `STS_S3_REAL_BELIEF_FILTER=1`; filtering only,
normalized equal weights for survivors, no duplication or rejuvenation. A
zero-survivor posterior is logged and safely restored to the prior particles
with uniform weights. Propagation failures are explicit and never use the old
shuffle approximation. `apps/test.cpp::testRealBeliefFilter` and the existing
`belief_immutability` test pass. The diagnostic extends `STS_S3_BELIEF_AUDIT`
with propagation, survivor, collapse, diversity, exactness, and CPU columns.

**Configuration:** fair Searcher3, A0, 64 particles, 1,000 simulations per
live decision, current native floor/win models, `v_combat_7k_tuned.txt`
(alpha 0.3), `policy_trees_c.txt`, no PVNet/dist VNet, 24 OpenMP threads,
`STS_S3_INTERNAL_BELIEF_UPDATE=0`, paired seeds 93000–93031 on `sts-test`.
Control had the filter unset; Filter set `STS_S3_REAL_BELIEF_FILTER=1`.

**Results (32 paired seeds):**

| Metric | Control | Filter |
|---|---:|---:|
| win rate | 10/32 (31.25%) | 11/32 (34.38%) |
| avg floor | 38.719 | 38.719 |
| avg HP end | 13.625 | 16.938 |
| CPU sec/run | 24.045 | 24.769 |
| paired win flips | — | 1/32 |
| belief rows | — | 11,521 |
| compatible fraction mean / median | — | 0.720 / 1.000 |
| posterior collapse fraction | — | 13.97% |
| propagation failure fraction | — | 3.65% of boundary rows |
| fallback-shuffle fraction | — | 0% |
| distinct surviving draw orders mean / median | — | 42.96 / 64 |
| distinct surviving RNG signatures mean / median | — | 55.03 / 64 |
| filter CPU mean / median | — | 0.185 / 0.176 ms/boundary |

The first gate is semantic and computational rather than win-rate promotion.
The filter is affordable and materially removes the old stale-pile artifact,
but collapse is non-trivial and diversity is not uniformly healthy. The 32-seed
quality result is not a promotion gate. Rejuvenation should only be tested if a
follow-up confirms that collapse harms useful posterior diversity; generic
cloning is not justified.

**Artifacts:** `build/belief_filter_control_32.csv`,
`build/belief_filter_filter_32.csv`, `build/belief_filter_diag_32.csv`,
`tools/analyze_s3_belief_filter.py`.

**Decision:** filtering semantics are promising enough for a confirmation gate,
but this iteration does not justify rejuvenation or a gameplay-default change.

---
## §2026-08-10 Searcher3 particle-count sweep

- **Question:** Does increasing Searcher3’s real-observation-filter particle set improve gameplay at fixed 1,000 simulations, and how does utilization scale? No PUCT, allocation, model, reuse, or hypothetical-belief behavior changed; `STS_S3_INTERNAL_BELIEF_UPDATE=0` remained off.
- **Audit:** `BattleScumSearcher3::step` samples exactly one belief particle per simulation, with replacement. Equal-weight beliefs use uniform sampling; larger particle sets increase initial/filter work but do not make each simulation replay every particle. New opt-in audit fields record selected indices, coverage, concentration, belief initialization CPU, filter CPU, and search CPU.
- **Configuration:** fair Searcher3, A0, 1,000 sims, 24 threads, real-boundary filtering on, 7k combat VNet alpha 0.3, policy tree on, PVNet/dist-VNet off, paired seeds 93100–93131. 64p/128p were extended on fresh paired seeds 93132–93163; no run exceeded the 128-seed ceiling.

| particles | wins/32 | mean floor | mean HP | CPU s/run | global collapse | sampled fraction |
|---:|---:|---:|---:|---:|---:|---:|
| 64 | 9 | 42.344 | 10.750 | 29.732 | 14.98% | 91.1% |
| 128 | 14 | 41.469 | 14.875 | 28.606 | 13.22% | 90.9% |
| 256 | 11 | 41.312 | 15.062 | 28.549 | 11.27% | 89.8% |
| 512 | 11 | 41.750 | 16.812 | 29.227 | 10.28% | 81.1% |

- **Extended 64p/128p block:** 64p = 18/64 wins; 128p = 24/64; 18 paired win flips. Aggregate collapse was 14.64% versus 12.93%; CPU was 31.07 versus 30.92 sec/run. This is confirmation evidence, not a promotion gate.
- **Compute:** mean filter CPU increased approximately 0.24/0.46/0.86/1.68 ms at 64/128/256/512p; belief initialization was 0.016/0.030/0.055/0.105 ms. Runtime remained effectively flat at this sample size. Utilization stayed high through 256p, so no particle×simulation interaction arm was justified.
- **Verdict:** Collapse decreases monotonically, but gameplay does not: 128p is promising, while 256p/512p do not improve the initial 128p result. Existing bestbench output has no action histories, so only paired outcome flips are claimed. Keep 64p default and confirm 128p with a larger paired gate.
- **Artifacts:** `build/particle_sweep_{64,128,256,512}{,_diag}.csv`, `build/particle_sweep_{64,128}_ext{,_diag}.csv`, `tools/analyze_s3_particle_sweep.py`.
## §2026-08-10 Searcher3 posterior-collapse diagnosis + fresh fallback

**Question:** Are zero-survivor events propagation failures or finite-particle
misses, and does fresh visible-state belief reconstruction help? No search
algorithm, budget, tree reuse, PUCT, model, or hypothetical-belief behavior
was changed. `STS_S3_INTERNAL_BELIEF_UPDATE` stayed off.

**Implementation:** `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1` is opt-in and only
runs after `STS_S3_REAL_BELIEF_FILTER=1` has zero survivors. It calls
`Belief::initial` on the current real state; it does not clone survivors. The
belief audit now records action/hash context, collapse category, predicted
observation distinctness/concentration/entropy, fresh reconstruction, and a
capped 64/128/256/512 diagnostic particle-count probe.

**Configuration:** fair Searcher3, A0, 64 live particles, 1,000 sims, native
floor/win models, `v_combat_7k_tuned.txt` alpha 0.3, `policy_trees_c.txt`, no
PVNet/dist VNet, 24 threads, paired seeds 93100–93131 on `sts-test`.

**Collapse evidence (filter arm B, 12,432 boundary rows):**

| Metric | Result |
|---|---:|
| compatible fraction mean / median | 0.697 / 1.000 |
| propagation-failure rate | 1.24% |
| collapse rate | 1,894/12,432 = 15.23% |
| collapse rows with propagation failures | 0 |
| collapse rows with action-illegal particles | 0 |
| collapse rows with reshuffle/draw signal | 50 |
| predicted observations per collapse, mean / median | 57.23 / 63 |
| dominant predicted-observation share | 3.9% mean |
| predicted-observation entropy | 3.978 mean |
| sensitivity survivors at 64/128/256/512 | 0.64 / 1.69 / 2.77 / 6.34 mean |
| positive sensitivity probes at 64/128/256/512 | 32/64 / 44/64 / 47/64 / 53/64 |

All collapse rows propagated exactly; the dominant explanation is finite
particle deprivation during stochastic END_TURN/card/automatic transitions,
with hidden-state representation limitations still open. The categories are
mechanism-grounded diagnostic labels, not causal proof.

**A/B/C paired gameplay:**

| Metric | A control | B filter | C filter + fresh collapse |
|---|---:|---:|
| wins | 10/32 (31.25%) | 11/32 (34.38%) | 11/32 (34.38%) |
| mean floor | 40.938 | 40.969 | 40.969 |
| mean HP end | 14.688 | 15.531 | 15.531 |
| CPU sec/run | 27.031 | 27.000 | 27.188 |
| paired flips vs A | — | 1/32 | 1/32 |
| paired flips B vs C | — | — | 0/32 |

Fresh reconstruction occurred on every collapse in C and produced no paired
decision/outcome difference from B in this block. Existing bestbench output does
not include per-decision action histories, so decision-change counts were not
claimed. These 32 seeds are diagnostic evidence, not a promotion gate.

**Artifacts:** `build/s3collapse_A_32.csv`, `build/s3collapse_B2_32.csv`,
`build/s3collapse_C2_32.csv`, `build/s3collapse_B2_diag_32.csv`,
`build/s3collapse_C2_diag_32.csv`, and `tools/analyze_s3_belief_filter.py`.

**Verdict:** Fresh-on-collapse is cheap and semantically safer than restoring
rejected particles, but it was gameplay-neutral in this small gate. Confirm the
result before promotion; do not implement general rejuvenation yet.

---

## Historical baseline for experiments as of 2026-07-14

New out-of-combat experiments should A/B against **this stack**, not the old default agent, so we
measure marginal gains instead of re-deriving from scratch. Requires `python3 v_server.py` (plain).

**Best = server card picks (skip@0) + heuristic path + shop-V knapsack.** Rest-V is *excluded*
(it trades win% for depth — see below). Absolute performance @512 seeds, asc0, 1000 sims:
**win% 25.0 · avg_floor 41.3 · hp_end 10.9** (vs the pre-OOC default agent ~20.9%).

Stack decomposition (each vs the 22.1% skip@0 baseline, 512 seeds):
| layer | win% | floor | note |
|---|---|---|---|
| never-skip cards + path (old default) | 20.9 | 38.9 | pre-§16 |
| skip@0 cards + path (§16) | 22.1 | 38.4 | +1.2pp, principled skip |
| **+ shop-V (§15)** | **25.0** | **41.3** | **+2.9pp — the win** |

---

## 🆕 BattleScumSearcher3 — ISMCTS with lethal detection — 2026-07-25

**What:** New `BattleScumSearcher3` ISMCTS searcher vs `BattleScumSearcher2` (fair-play).  
Searcher3 features:
- All 6 RNG streams randomized per simulation (vs Searcher2's 2)
- Observation caching per node (`ensureObservation`)
- Damage-biased rollout (attacks 8x, same as Searcher2)
- PUCT with policy priors (same formula as Searcher2)
- `isGuaranteedDead()` early backprop — prunes branches where incoming damage exceeds HP+block, skipping wasted rollout steps

**Setup:** Fair-play (both searchers). 32 seeds, asc 0, 1000 sims/decision. No VNet.  
Same OOC stack (server cards + heuristic path + shop-V).

**Results (1000 sims, 32 seeds):**

| Searcher | Win% | Floor | HP end | sec/run |
|---|---|---|---|---|
| Searcher2 (fair-play) | 21.1% | 36.8 |  9.2 | 7.7 |
| **Searcher3 (ISMCTS)** | **59.8%** | **41.2** | **22.7** | **3.3** |
**Takeaway:** 256 paired seeds. +38.7pp, +4.4 floors, +13.5 HP, 2.3× faster than Searcher2 fair-play.
---

## 🆕 Phase 3 — sorted compression + tree reuse — 2026-07-26

**What:** Sorted deterministic compression (Expert::getPlayOrdering) + tree reuse across turns.
**Result (256 seeds, 1000 sims):** S3 63.3% vs S2 fair 21.1%, +42.2pp. 32-seed best: 78.1%.


## 🆕 Deterministic chain compression — 2026-07-25

**What:** Added inline deterministic action compression in Searcher3's `step()`. After executing the chosen edge action, additional non-drawing, non-targeting cards are played before the rollout (up to 10 additional steps). Each compressed action is validated (hand must decrease by exactly 1 — no draws).

**Results (1000 sims, 32 seeds, fair-play):**

| Config | Win% | Floor | HP end | sec/run |
|---|---|---|---|---|
| Searcher3 (no compression) | 68.8 | 42.3 | 30.2 | 3.0 |
| **Searcher3 + compression** | **71.9** | **46.1** | **27.4** | **3.4** |

**Takeaway:** +3.1pp from compression. Effectively increases search depth per simulation.
Even beats Searcher2 known-RNG (60.9%). The `isGuaranteedDead` check is the main driver — it prevents wasting simulations on lines where the player will certainly die.
| + rest-V (§15) | 20.7 | 40.0 | −1.4pp win / +1.6 floor — **excluded** |
| + both | 22.1 | 42.1 | rest-V erases shop-V's win gain |

Invoke: shop-V alone = `runFullRunOOC(seed,sims,asc, restV=false, shopV=true)` with `g_cardSkipThresh=0`
(default). rest-V is behind its flag for depth-focused (act-4/heart) runs only.

## Summary table

| # | Change | Mode | Config | Baseline | Result | Verdict |
|---|--------|------|--------|----------|--------|---------|
| 1 | MCTS combat vs random | `bench` | JawWorm, 100 seeds, 2000 sims | random 91% win / 34 HP | MCTS **100% win / 74 HP** | ✅ huge (single combat) |
| 2 | Combat sims → whole run | `runbench` | 20 seeds | — | 1k:0%/f27 · 8k:0%/f32 · 30k:**17%**/f43 | ↗ depth scales; win needs a good deck |
| 3 | Devalue high HP in eval | `evalrun` | 20 seeds, 8k sims | base 0% / f33.1 | devalue 5% / f32.0 | ➖ noise (myopic combat) |
| 4a | Lookahead drafting N=2 | `draftbench` | 16 seeds, outer 4k, inner 2k | table 6.2% / f30.9 / 7.7cpu-s | look 0% / f29.2 / 36cpu-s | ❌ worse & 5× cost |
| 4b | Lookahead drafting N=3 | `draftbench` | 16 seeds, outer 4k, inner 4k | table 6.2% / f30.9 / ~12cpu-s | look 6.2% / **f32.8** / 138cpu-s | ➖ +2 floors at ~11× cost |
| 5 | Fix uninitialized `player.cc` | (correctness) | — | nondeterministic crashes | stable | ✅ real sim bug fixed |
| 6 | Heuristic pathing (step gate) | `pathbench` | 32 seeds, 4000 sims | random 6.2% / f31.6 | heuristic 9.4% / f31.0 | ➖ wash (2 vs 3 wins = noise) |
| 6b | + tighter elite HP gate | `pathbench` | 64 seeds, 4000 sims | random 4.7% / f28.6 | heuristic 4.7% / **f30.0** | ↗ +1.4 floors, win% flat (deck-gated) |
| 7 | Tree reuse across decisions | `runbench` | 32 seeds, 4000 sims | orig ~4.74 s/run | reuse 5.62 s/run | ❌ no speedup (known-RNG solver) |
| 8 | Greedy never-skip drafting | `cardbench` | 128 seeds, 4000 sims | table 4.7% / f28.2 | greedy 7.0% / f29.4 | ✅ beats table (skipping hurts @ asc0) |
| 9 | **Greedy draft + heuristic path** | `combobench` | 128 seeds, 4000 sims | baseline 4.7% / f28.2 / 1.3hp | **combo 14.8% / f29.9 / 7.1hp** | ✅✅ **3× win rate — policies compound** |
| 10 | State-aware card value function | `cardbench` | 128 seeds, 4000 sims | table 4.7% · greedy 7.0% | **eval 10.2% / f30.9** | ✅ beats table & greedy |
| 11 | **Fair-play (determinized) MCTS** | `*bench …1` | 128 seeds, 4000 sims | known-RNG inflated ~5× | see below | ⚠️ honest numbers; eval edge survives |
| 12 | **Causal per-card value (ML)** | `causalgen`+`cardbench` | 3000 runs K=6 CRN; A/B 400 seeds 2500 sims fair | eval 1.5% / f22.2 | **eval+causal 2.2% / f24.9**; causal-table f29.4 | 🔬✅ fused beats eval; tempo real, per-card synergy not learnable |
| 13 | **Deck-aware V captures synergy** | `datagen`+`train_value_deckaware.py`; `v_server.py`+`cardbench` p6 | 6000 runs V→finalFloor; A/B 400 seeds 2500 sims fair | eval+causal 2.2% / f24.9 | offline: V-marginal **monotone in #synergy partners**; online gbm-server **2.0% / f26.3** | ✅ synergy learnable offline; ➖ online ties best (combat is the ceiling) |
| — | **Build bug fixed** | — | — | stale archive objects | clean rebuild | ⚠️ prior BattleContext/searcher edits weren't linked |

Legend: ✅ clear win · ↗ helps · ➖ neutral/noise · ❌ hurts · ⏳ in progress.

---

## 1. MCTS combat vs. random baseline
- **What:** wrap `BattleScumSearcher2` for in-combat decisions vs. a uniformly-random legal-action policy.
- **Config:** JawWorm, 100 seeds, 2000 sims/decision.
- **Result:** random **91% win / 33.9 avg HP**; MCTS **100% win / 74.1 avg HP**, ~314 ms/combat.
- **Verdict:** ✅ The combat searcher is strong. Combat is *not* the bottleneck.

## 2. Combat sims scaling over a whole run
- **What:** how far a full Neow→Act3 run gets as we raise sims/decision.
- **Config:** 20 seeds. 1k / 8k / 30k sims.
- **Result:** 1k → 0% win, floor 27, 0.6 s/run · 8k → 0%, floor 32, 5.7 s · 30k → **17%**, floor 43, 28 s.
- **Verdict:** ↗ More sims get you deeper, but wins are gated by **deckbuilding / out-of-combat play**, not combat search. Deaths cluster at act bosses with weak decks. → the research lever is the out-of-combat policy.

## 3. Devalue high HP in `evaluateEndState`
- **What:** make HP above 50% of max worth only 0.4× (stop the searcher over-valuing HP it already has). Toggle `search::g_devalueHighHp`.
- **Config:** combat GremlinNob 150 seeds; whole run 20 seeds @ 8k sims.
- **Result:** combat 98.7% win both, 45.5 vs 45.7 HP. Run: base 0% / floor 33.1 vs devalue 5% / floor 32.0 — within noise.
- **Verdict:** ➖ Negative result. The combat searcher is **myopic** (optimizes each fight alone), so "save HP for later" has no "later." Payoff would need cross-fight/run-aware value.

## 4. Lookahead card-reward drafting
- **What:** at each card reward, copy the run, apply each choice (3 cards + skip), play the next *N* fights with a cheap inner agent, keep the best. Common Random Numbers are free (the copied `GameContext` carries all RNG streams).
- **Config:** 16 seeds, outer 4000 sims.
  - **4a — N=2, inner 2000:** weighted-table 6.2% / floor 30.9 / 7.7 cpu-s vs lookahead **0% / floor 29.2 / 36 cpu-s**.
  - **4b — N=3, inner 4000:** weighted-table 6.2% / floor 30.9 / ~12 cpu-s vs lookahead 6.2% / **floor 32.8** / **138 cpu-s**.
- **Verdict:** ❌→➖ N=2 loses outright (weak inner pilot). N=3 edges the table on depth (+~2 floors) but at ~11× compute, and the win-rate diff is noise (1/16). Confirms the payoff shape is a **learned value function** that amortizes this lookahead offline, not online rollout.

## 5. Fix: `BattleContext::init` never set `player.cc`
- **What (correctness, not win%):** `Player.cc` had no default initializer and `init()` never assigned it, so in combat it was **uninitialized stack garbage**. When its value happened to be `3` (Watcher), an Ironclad's **Entropic Brew** (`returnRandomPotion(potionRng, player.cc)`) and "add a random card" effects (`getTrulyRandomCardInCombat`) drew from the **wrong class pool** → e.g. a Watcher **Stance Potion** in an Ironclad run → the searcher tried to drink it → `CHOOSE_STANCE_ACTION` assert (and a `drinkPotion` default assert for unimplemented potions). Nondeterministic, because it depended on stack contents.
- **Fix:** one line — `player.cc = gc.cc;` in `BattleContext::init` (`src/combat/BattleContext.cpp`).
- **Verdict:** ✅ Real latent sim bug, surfaced by heuristic pathing perturbing which fights we reach. Unblocks all whole-run experiments.

## 6. Heuristic map pathing  ⏳
- **What:** replace the random `MAP_SCREEN` choice with a bottom-up DP over the 15×7 map. Each room gets a value; pick the child leading to the best-scoring remaining path to the boss. Spec: elites & rests great; elites more valuable the **later** you fight them; shops gated on gold; monsters scaled up in **act 1** and by current HP; events balance fight-heavy paths; re-plans every floor with live HP so a healthy hero takes the **hardest survivable path** (act-transition heals anyway). Code: `roomValue` / `chooseMapAction` in `apps/one_combat.cpp`, mode `pathbench`.
- **Note:** at **200 sims** the pilot is too weak to win the elites it routes into, so the heuristic *hurt* (floor 20.2 vs random 24.2). Pathing only pays off if you can win what you route into → must evaluate at a real sim count.
- **Config:** 32 seeds, 4000 sims/decision.
- **Result (v1, step-function elite gate):** random-path 6.2% win (2/32) / floor 31.6 / 1.3 HP · heuristic-path 9.4% win (3/32) / floor 31.0 / 3.0 HP → wash (2 vs 3 wins = noise).
- **Result (v2, tighter continuous elite gate, 64 seeds):** random-path 4.7% win (3/64) / floor 28.6 / 1.1 HP · heuristic-path 4.7% win (3/64) / **floor 30.0** / 1.7 HP.
  - Change: elite value gate went from a 3-step function to a continuous ramp `clamp((hpFrac-0.40)/0.50, 0, 1)` — an elite is worth ~0 below 40% HP and only full value near 90% HP (a bigger HP cushion than normal fights, which keep a `0.4 + 0.9*hpFrac` floor).
- **Verdict:** ↗ Small but consistent **+1.4 floor** depth gain (direction stable across 32- and 64-seed runs), slightly higher end-HP, **no win-rate change** and no compute regression. Confirms the recurring theme: pathing/HP-management shows up as *depth, not wins* — wins are gated by **deck quality** (you die at act bosses regardless of route). Marginal keeper; the real lever is the card/deck policy.
- **Note on speed:** deep runs are expensive because rollouts play to true battle-end and act-3 enemies have huge HP (per-run cost ~4s shallow → ~8s at floor 50). A *better* agent that survives longer costs *more* per run. The fix is depth-capped rollouts with a leaf value estimate (queued).

---

## 7. Tree reuse across combat decisions  ❌ (negative result)
- **What:** keep one `BattleScumSearcher2` per battle; after each played action re-root onto that child (`advanceRoot`) keeping its subtree, and `searchToTotal(target)` only tops up the shortfall instead of searching a fresh tree. Header + `BattleScumSearcher2.cpp` + `ScumSearchAgent2::playoutBattle`.
- **Config:** runbench 4000 sims, seeds 0..31.
- **Result:** with reuse actually linked (after the build fix below): 9.4% / floor 32.9 / **5.62 sec/run** vs original playoutBattle ~4.74 sec/run — **no speedup** (slower, partly because the changed RNG stream sends runs deeper, and `advanceRoot` adds a per-move BattleContext copy). *(First measurement claimed 4.69 vs 4.74 "identical" — both were the STALE original code; see build bug.)*
- **Verdict:** ❌ Design mismatch. This is a *known-RNG solver*: once a search finds a complete winning line it **executes 15 moves without re-searching** (`stepsWithSolution=15`), so there's no per-move search to amortize — the first search of each battle dominates. And the winning line runs through **rollout territory never added to the tree** (MCTS expands one node/sim), so re-rooting hits unexpanded children and rebuilds anyway. Reuse would only help a *fair-play* (unknown-RNG) searcher that must re-search every move. **Real speed lever is depth-capped rollouts (cost per sim), not reuse (number of searches).**

## 8. Greedy card-reward drafting  ✅ (first real win-rate gain)
- **What:** replace the built-in `weightedCardRewardPolicy` (roulette-wheel over `getObtainWeight`^1.2 + probabilistic deck-quality-gated skip) with a deterministic **argmax**: take the highest-weight card (same shaping + act-1 attack ×1.4), and skip only if `bestRaw < skipRatio * avgDeckObtain`. Code: `greedyCardRewardPolicy` / mode `cardbench` in `apps/one_combat.cpp`. Runs on the **clean build** (0 crashes).
- **skipRatio sweep (64 seeds, 4000 sims), vs fixed weighted-table 7.8% / f29.9:**
  - 0.0 (never skip): **9.4% / f29.5 / 3.4 HP**
  - 0.5: 7.8% / f29.3 / 2.3 HP
  - 0.7: 6.2% / f28.6 / 2.6 HP
  - 1.0: 4.7% / f27.9 / 1.9 HP
  - → perfectly monotonic: **more skipping = worse.**
- **Confirmation (128 seeds, skipRatio 0.0):** weighted-table 4.7% (6/128) / f28.2 / 1.3 HP vs **greedy 7.0% (9/128) / f29.4 / 2.2 HP** — greedy wins on win%, depth, and HP.
- **Verdict:** ✅ First policy change to move win rate the right way. The built-in policy's probabilistic *skipping* is the culprit — at ascension 0 the deck-dilution cost is small and bigger decks (more payoffs/options) win. Deterministic argmax + never-skip is also simpler. Gain is modest (~+2 pp win, +1 floor) and samples are small, but the monotonic trend + two sample sizes make the direction credible. **Next: try this at higher ascension (dilution matters more → optimal skipRatio likely > 0), and prioritize scaling/power cards.**

## 9. Combined: greedy draft + heuristic pathing  ✅✅ (best result so far)
- **What:** run exp 8 (greedy never-skip drafting, skipRatio 0) and exp 6b (heuristic pathing) together in one whole-run driver, vs the stock baseline (built-in weighted table + random pathing). Mode `combobench` / `runFullRunCombo` in `apps/one_combat.cpp`.
- **Config:** 128 seeds, 4000 sims, ascension 0, clean build (0 crashes), 12 cores.
- **Result:** baseline 4.7% win (6/128) / floor 28.2 / 1.3 HP  vs  **combo 14.8% win (19/128) / floor 29.9 / 7.1 HP**.
- **Verdict:** ✅✅ Best result to date. Win rate **~3×** (19 vs 6 wins — significant, not noise), and the hero finishes far healthier (7.1 vs 1.3 HP). The gain is **super-additive**: greedy alone +2.3pp, pathing alone ~flat on wins, together +10pp. Mechanism = mutual unlock: greedy builds a deck strong enough to *win* the elites that pathing routes into, and winning elites (relics/rewards) snowballs the deck. Neither works well without the other. Compute ~unchanged (1.69 cpu-sec/run).
- **Next:** higher ascension (does the synergy hold when HP/dilution bite?); sweep skipRatio for the *combo* (optimal may differ from the card-only 0.0 now that pathing changes HP trajectory); prioritize scaling/power cards in the draft weights.

## 10. State-aware card value function  ✅
- **What:** `evalCardValue(gc, card)` — transparent weighted sum over the full state: base `getObtainWeight` prior + curve/role need (boost under-represented attack/skill) + scaling bonus for Powers that grows with act (diminishing past ~2) + base-damage impact + defensive lean at low HP / high asc + upcoming-elite pressure (map scan via `rowsToNextElite`). Skip = value below a state-dependent bar (rises with deck size & ascension, halved in act 1). Mode `cardbench` policy 2 / `evalCardRewardPolicy`.
- **Result (128 seeds, 4000 sims, known-RNG):** table 4.7% / f28.2 · greedy 7.0% / f29.4 · **eval 10.2% / f30.9 / 4.6 HP**. Monotonic: eval > greedy > table.
- **Combo note:** eval+heuristic-path = 10.9%; greedy(never-skip)+path = 14.8%. Eval is the better card policy *alone*, but greedy+path had the bigger known-RNG synergy (see fair-play caveat — that synergy was largely a draw-peeking artifact).
- **Verdict:** ✅ Context (curve, scaling, dilution, upcoming fights) beats a flat table.

## 11. Fair-play (determinized / information-set) MCTS  ⚠️ (methodology fix)
- **Why:** the built-in searcher is a *known-RNG solver* — rollouts follow the true future draw order, so it plays with information a real player lacks. All win rates above are optimistic.
- **What:** added `search::g_fairPlay`. Per simulation, `determinize()` re-shuffles the draw pile (hand/discard/exhaust kept — the player knows those) and re-seeds `shuffleRng`/`cardRandomRng`, so the search averages over possible draws instead of exploiting one. Tree descent / leaf / rollout filter actions by `isValidAction` (legal set differs per world). Move selection commits only the **most-visited root child**, then re-searches (`playoutBattleFair`) — the full best line is world-specific. Toggle: trailing `1` arg to `cardbench`/`combobench`. Enemy intents are *not* re-randomized (still known) → this is "draw-fair", a partial fair-play.
- **Result (128 seeds, 4000 sims, fair):** card-only table **0.8%** (was 4.7) · greedy **0.0%** (was 7.0) · eval **2.3%** (was 10.2). Combo: baseline **0.8%** vs eval+path **2.3%**.
- **Verdict:** ⚠️ Known-RNG inflated win rates **~5×** — the numbers *were* distorted. Under fair play: (a) **eval's advantage over the table survives** (2.3 vs 0.8) — it's a real deckbuilding gain, not draw-peeking; (b) **greedy's edge and the big greedy+path synergy did NOT survive** (0.0%) — those were largely known-RNG artifacts; (c) pathing still adds depth not wins. Caveats: fair combat at 4000 sims is weak (dies ~act 2 — ISMCTS has higher variance, needs more sims) and ~6× slower per run (re-search every move); win counts are tiny (0-3/128) so treat as directional.
- **Next:** more sims for fair combat (it's under-powered at 4000); optionally re-randomize enemy intents beyond the visible next one for full fair-play.

## 12. Causal per-card value function (offline ML)  🔬
- **Goal:** learn `value(state, card)` so 3-card picks are easy, *without hand-crafting synergy features* (raw representation, let the model find interactions).
- **Label (causal, CRN):** at each card reward, clone the run and play the next **N=6 fights** twice under **Common Random Numbers** (identical draws/monsters) — once taking the card, once skipping. `advantage = labelScore(take) − labelScore(skip)` (≈ HP survived, big penalty for death). Averaged over **K=6** CRN seeds. Mode `causalgen`; `rolloutChoice` does the paired forks; shared skip baseline across candidates.
- **Representation:** cheap scalars (act/floor/HP/gold/deckSize…) + candidate's own baseDamage/obtainWeight + **372 per-card-id deck counts** (`d0..d371`) + one-hot candidate id → **`HistGradientBoostingRegressor`** (`train_gbm.py`). The trees can split "candidate==X AND deck[Y]>0" to discover synergy with no hand features.
- **Data-gen efficiency (key enabler):** the downstream `innerSims` was the cost sink *and* a noise source. Benchmark: dropping `innerSims` 800→**150** gave **5.5× speedup with label std ~unchanged** (23.0→25.4) — 800 sims to *measure survival* was pure waste; below ~150 the AI gets too weak and std climbs. Config `causalgen 3000 300 6 150 6 0.3` → 102k rows in 23 min (was ~3.3s/run → 0.47s/run).
- **Result — the model:** with 3000 runs (100k rows), split by run:
  - val R² = **0.034** (up 3.6× from 300 runs), top-1 pick accuracy **0.475** vs baseDamage 0.433 vs rarity 0.336 vs random 0.333.
  - **Deck/synergy features *hurt*** (val R² 0.024 with them vs 0.034 without; higher train R² = overfit). Firm at 100k rows: **deck synergy is not learnable at this label SNR.**
  - Label std scales ~1/√K (60.8→23 at K=6) ⇒ still **pure-noise regime**; true signal floor <17. More data helps modestly; the real lever is a less-noisy label (win-prob bootstrap), not more rollouts.
- **Result — the artifact:** a trivial **per-card mean-advantage lookup table** (106 entries, shrunk λ=50) matches the full GBM (top-1 **0.477** vs 0.475). So *all* learnable signal is per-card average value — no state/synergy interaction. Exported to `build/card_adv_table.txt`; wireable into C++ with no ML runtime.
- **StS-sanity (validates the pipeline):** top cards = immediate damage/AoE (Immolate +24, Anger/Bludgeon/Combust +16, Reaper/Shockwave/Uppercut +15); bottom = engine/synergy cards (Entrench −11, Dual Wield −9, Rupture/Dark Embrace/Brutality −8). It's a **raw-tempo evaluator** and *systematically undervalues build-around cards* — the same fact as "synergy not learnable". Notably it **disagrees with `getObtainWeight`** (which rates Barricade 85, Brutality/Flex 65) exactly on those synergy cards.
- **Wired policies:** `cardbench` policy **4 = eval+causal** (`evalCardValue + α·centered_adv`, α CLI arg) and **5 = causal-table** (pure table, causally-correct skip: take iff adv>0). `fusedCardRewardPolicy` / `tableCardRewardPolicy`, table via `loadCardAdvTable`.
- **A/B (400 seeds, 2500 sims, fair-play):** eval-function 1.5% / **f22.2** · **eval+causal 2.2% / f24.9** · causal-table 1.2% / **f29.4** (refs: table 0.2/f20.6, greedy 2.2/f21.5, learned-logistic 0.5/f16.2). Win counts tiny (~6–9/400 — fair combat is HP-starved at 2500 sims) so win% is directional; **avg floor is the high-resolution signal**.
- **The money finding:** **fusing the causal table into the expert eval beats plain eval on both metrics** (win 1.5→2.2%, floor 22.2→**24.9**). And the standalone causal-table reaches by far the **deepest floors (29.4, +7 over eval)** but converts *fewer* to wins (1.2%) — it survives deep on tempo/damage but lacks the scaling/win-con cards it undervalues to close act-3 bosses. **Empirical confirmation of the thesis:** tempo gets you *to* the boss; synergy/scaling *wins* the boss. eval+causal is the sweet spot (expert eval supplies scaling valuation, causal table sharpens survival picks).
- **Verdict:** 🔬✅ The causal signal is **real, StS-sane, and additive** — eval+causal is the new best card policy. But it's a pure *tempo* prior; the "learn synergy from card-ids" premise does not fire at this label SNR. Best path to synergy is a bootstrapped win-probability label, not brute-force rollout data.

## 13. Deck-aware value function captures SYNERGY  ✅ (blind-spot cracked, offline)
- **Goal:** fix §12's blind spot — the causal table is a flat per-card tempo prior that can't see "card X is good *because of my other cards.*"
- **Approach:** learn a **deck-aware** value `V(state, deck-card-ids) → final floor` and use `V(deck+card) − V(deck)` as card value. Key vs the old failed logistic V (§ offline pipeline): that used only **aggregate** features (nCommon/nPower…) so it could only learn "commons bad"; this adds **per-card-id deck counts d0..d371**, letting `V` express card-card interactions. Final floor (mean 32.8, std 12.5) is a *dense* target — far better signal than 2% win/loss.
- **Build:** `datagen` now appends `deckCountsCsv` to each row (deck-aware); new `carddump` mode emits id→type/rarity/obtainWeight/baseDamage (`build/card_meta.csv`). `train_value_deckaware.py`: GBM V + an "add-a-card" transform in feature space (bump deckSize/type/rarity/obtainSum/d[id]) to compute marginals offline. Data: `datagen 6000 1500` → 85k rows.
- **V quality:** val R² **0.357** predicting final floor (vs causal-advantage R² 0.034) — a genuinely useful value function.
- **Synergy proof (the result):** the per-card marginal **rises monotonically with the number of synergy partners in the deck**:
  - Barricade (w/ Metallicize/FeelNoPain/Entrench/BodySlam): 0→−0.95, 1→−0.40, 2→−0.39, **3+→−0.07**
  - Dark Embrace (w/ FeelNoPain/FireBreathing/SecondWind): 0→−2.33, 1→−1.34, 2→−0.71, **3+→−0.38**
  - Rupture (w/ Brutality/Combust/Hemokinesis/Offering): 0→−1.42, 1→−0.54, 2→−0.19, **3+→+0.10** (flips positive!)
  - Body Slam: 0→−1.56 → 1→−0.69 → 2→−0.52. Every probed engine card shows the correct gradient.
- **corr(V-marginal, causal-tempo table) = +0.70** — they agree on damage but V's deck-awareness diverges exactly on the build-arounds (Corruption/Offering/Feed/ShrugItOff "rescued" vs the causal ranking).
- **Caveats:** (1) magnitudes stay *modest* (rarely strongly positive) because the ε-greedy data has **few fully-committed archetype decks** (Barricade 3+ partners n=195 vs 0 partners n=12173) — V extrapolates cautiously into the sparse synergy region; archetype-richer data would sharpen it. (2) V is **correlational** (not causal); ε-exploration de-confounds partially. (3) **Not yet in the agent** — GBM inference in C++ is the open porting problem (candidate fixes: export trees, or switch V to a factorization machine that ports as embedding dot-products with no hand features).
- **Online test (GBM bridged into the agent):** rather than port the GBM, `v_server.py` holds it and the C++ card policy (`serverCardRewardPolicy`, cardbench policy 6 `gbm-server`) queries it over a TCP socket at each pick (~13/run, so speed is fine; persistent per-thread sockets, thread-safe). Card value = `V(deck+card) − V(deck)` from the exact GBM. A/B (400 seeds, 2500 sims, fair-play):
  - gbm-server skip@0 (take iff marginal>0): **0.8% / f25.2** — over-skips (muted marginals → many all-negative rewards → skip, which hurts at asc0).
  - gbm-server **never-skip: 2.0% / f26.3**.
  - vs eval 1.5%/f22.2 · eval+causal 2.2%/f24.9 · causal-table 1.2%/f29.4.
- **Verdict:** ✅ offline / ➖ online. Synergy **is learnable** offline (unambiguous monotone gradient) — the blind spot is real and fixable. But bridged into the agent the deck-aware GBM only **matches** the best prior policy (never-skip 2.0% ≈ eval+causal 2.2%, deeper floors 26.3 vs 24.9) — no *win-rate* gain. Win counts are tiny (~6–9/400) so eval / eval+causal / gbm-server are **statistically indistinguishable on win%**; on the higher-resolution floor metric the ML policies (causal-table 29.4, gbm 26.3) reach deepest. Why no win jump: (1) synergy magnitudes are muted (ε-greedy data lacks committed-archetype decks); (2) V is correlational (not causal); (3) **fair-play combat at 2500 sims is the binding constraint** — a ~2% win ceiling compresses all card policies. Next levers, in priority: more combat sims to lift the ceiling (let deck quality matter), archetype-rich training data, causal-TD de-biasing, and fuse GBM into eval (à la eval+causal) rather than pure V-difference.
- **Separation test (raise combat to 8000 sims, 150 seeds, fair):** eval 2.0% (3 wins)/f23.6 · eval+causal 2.7% (4)/f25.9 · **gbm-server 2.7% (4)/f27.0**. Higher sims lifted win% only marginally (eval 1.5→2.0, eval+causal 2.2→2.7) — the ceiling is still ~3%. gbm-server and eval+causal **tie on win% (4 vs 4 wins = noise)**; gbm reaches the deepest floor (27.0). **Conclusion: at asc0 the card-policy differences show up as ~1 floor of depth, not win-rate — and even 8000-sim fair combat can't finish enough runs to resolve win% (win counts stay 3–4/150).** The binding constraint is now **combat strength**, not card selection. To make deckbuilding pay off in win%, lift the combat ceiling first (depth-capped rollouts + leaf value — the queued speedup), *then* re-run these card A/Bs.

## 14. Depth-capped combat rollouts + leaf value  ⏳ (WIP — turtle-equilibrium blocker)
- **Goal:** lift the combat win ceiling (§13) by making each MCTS simulation cheaper — cap the random rollout length and, if it hits the cap on a non-terminal state, estimate the leaf value instead of playing act-3 fights to the end.
- **Built:** `g_maxRolloutDepth` (env `STS_ROLLOUT_DEPTH`, 0=off/unlimited=original behavior), rollout break in `playoutRandom`, `evaluateLeafState` (terminal→`evaluateEndState`; non-terminal→estimate on the same scale), `updateFromPlayout` routed through it. **Default-off so uncapped paths are byte-identical to before.**
- **Blocker (turtle equilibrium):** any leaf heuristic that values player HP creates an infinite-loop hazard. In a long high-HP fight (act 2/3 elite/boss) no rollout reaches victory within the cap, so the agent optimizes the leaf directly — and when the player can't meaningfully dent the enemy, **turtling (block, don't attack → keep HP, enemy HP stays high) scores higher than attacking (spend HP for tiny progress)**, so the agent blocks forever and the battle never terminates → hang. Removing the `turn` reward (which *also* rewarded stalling) was necessary but not sufficient.
- **Status:** needs a leaf value where reducing enemy HP *always* raises the score (no turtle fixed point) while still crediting survival — a real bias/quality trade-off. Parked; not overnight-safe. Uncapped combat unaffected.

## 15. Out-of-combat value policies: rest sites & shops (via the deck-aware V)  ✅ (shop) / ➖ (rest)
Reuse the served card V (`v_xgb.json`, deck-aware, already includes `curHp`/`floor`/`gold`/`nRelics`)
to make out-of-combat decisions as V-deltas. New server endpoints (`v_server.py`): `H` heal-gain,
`U` upgrade-target, `X` removal-target, `S` shop knapsack. New app modes `restbench`/`shopbench`/`allbench`
(server card picks + heuristic path fixed; A/B one policy vs the default agent). **Run needs
`VNEVERSKIP=1 python3 v_server.py`.** All behind flags; default binary unchanged.
- **Rest sites** (`restbench`): heal iff `V(deck,hp+restHeal)-V(deck,hp) >= thresh`, else upgrade the
  deck's most-*valued* card (crude — model can't see per-card upgrade, so it targets Strike, a poor
  upgrade). 512 seeds asc0 1000 sims: default 20.9% / f38.9 / hp8.2. Threshold sweep best at **~0.1–0.25**
  (non-monotonic): thr0.1 **21.3% / f40.2 / hp8.5**; thr1.0 18.4% (under-heals → dies at bosses); thr0.0
  15.6% (never upgrades). Default set to 0.15. **Verdict ➖ WASH on win% (+0.4pp = noise) but consistent
  +1.1 floor.** Depth doesn't convert to wins — bottleneck is the crude upgrade target.
- **Shops** (`shopbench`): server-side knapsack over {card buys, card removal, relic buys} maximizing
  `V(final deck, final gold, final nRelics)` (gold is a feature, so V weighs spend vs keep). Card buys &
  removal well-modeled; relics get a generic `nRelics` delta (can't rank identity); potions unmodeled
  (never bought). Execute one purchase/call + re-optimize (robust to buy-triggered screens like bottling
  relics — a multi-buy-in-one-call version aborted on those). 512 seeds: default 20.9% / f38.9 / hp8.2 →
  **shop-V 23.0% / f40.8 / hp8.9 (+2.1pp win, +1.9 floor, +0.7 hp)**. **Verdict ✅ genuine win** (default
  shop policy was bad: one relic then random). Removal + synergy-aware buying is the equity.
- **Combined** (`allbench`, rest-V + shop-V): 512 seeds **23.4% / f41.8 / hp8.7 vs 20.9% / f38.9 / hp8.2
  = +2.5pp win, +2.9 floor.** Floor gains stack; shop-V carries win rate, rest-V adds depth.
- **Ops gotchas (cost real debugging):** (a) the shop/rest harness REWARDS branch must claim
  gold/relic/potion before cards or the screen never clears → infinite CPU spin (looked like "slow
  combat"); (b) if `v_server.py` is down, `vQuery` silently returns skip → 10-card deck → floor ~15 / 0
  wins with no error — always confirm the server is listening before trusting a low-floor result.

## 16. Card-reward skip policy = threshold on marginal V  ✅ (skip@0 best)
Card picks (`serverCardRewardPolicy` → `vQuery`) now: the server returns `<best_idx> <best_marginal>`
(marginal = `V(deck+card)-V(deck)` in final-floor units), and the C++ side skips iff `marginal <
g_cardSkipThresh` (env `STS_SKIP_THR`). Puts the skip rule in one place, sweepable without a server
restart. Sweep 512 seeds asc0 1000 sims (server-cards + heuristic-path, `skipbench`):

| skip thr | never(-1e9) | **0** | 0.5 | 1 | 2 | 3 |
|---|---|---|---|---|---|---|
| win% | 20.9 | **22.1** | 11.3 | 8.2 | 4.3 | 1.8 |
| floor | 38.9 | 38.4 | 36.1 | 34.0 | 28.7 | 22.1 |

**Peak exactly at 0 (take iff the card raises expected final floor; skip only diluting/negative-marginal
cards), a sharp cliff after.** Beats never-skip +1.2pp (modest/noise-level but the principled point).
Any positive threshold starves the deck at asc0. **Default set to `g_cardSkipThresh=0`** (replaces the
`VNEVERSKIP=1` hack — the server no longer decides skip). Also clarified: the earlier floor-15 collapses
were purely *server-down* (silent skip), NOT the skip threshold — marginals are mostly positive, so
skip@0 rarely fires. NOTE: at higher ascension, dilution is costlier, so the optimum likely shifts >0;
re-sweep per ascension.

## ⚠️ Build bug (2026-07-12) — invalidated some earlier measurements
The full build names objects `src_combat_BattleContext.cpp.o`. Incremental rebuilds `ar r`'d members under a different basename (`BattleContext.o`), so the archive held **two** copies and the linker silently used the **stale original**. Consequences:
- The `player.cc` fix (exp 5) and the tree-reuse code (exp 7) **were never in the binary** until a clean rebuild. The "cc fix works" and "reuse = no speedup, identical" claims were coincidence (nondeterministic crashes) / old code.
- After a clean rebuild (`rm build/*.o build/libsts.a`; recompile all; `ar rcs`), verified: **`player.cc = gc.cc` is the single fix for ALL potion crashes** (garbage id 69/153 and the Watcher Stance Potion are the same root cause — uninitialized `cc` indexes `potionPool[cc][idx]` out of bounds). 0 crashes over 48 seeds.
- **Pathing results (exp 6/6b) were measured on the pre-cc-fix substrate** (pathing logic itself lives in the always-recompiled app, but combat had the latent cc bug). Likely ~valid (the bug triggers rarely) but worth re-confirming on the clean build.
- Lesson: incremental rebuild must reuse the archive's object name, or do a full clean rebuild; verify `ar t libsts.a | grep -c BattleContext` == 1.

## Ideas queued (not yet tried)
- **Depth-capped rollouts + leaf value estimate** — rollouts currently play to true battle-end; act-3 huge-HP fights make them long. Cap depth and score the leaf heuristically. Cuts cost *per simulation* (the dominant cost). ← highest-value speedup.
- **Transposition / commutation canonicalization** — the searcher is a plain tree with no state hashing, so commuting card orders (Strike→Defend vs Defend→Strike) are explored redundantly (`k!` vs `k`). Merging them cuts effective branching.
- **Improved static card-reward policy** — greedy/argmax over `Expert::getObtainWeight` vs the current roulette-wheel `weightedCardRewardPolicy`.
- ~~**Shop spending policy**~~ — DONE (§15): V-knapsack shop buys/removal, +2.1pp win.
- **Per-card-upgrade V** (`u0..u371` upgraded-counts + retrain) — would let the rest-site upgrade target and any upgrade decision pick *scaling* cards instead of Strike; likely turns §15's rest-site depth gain into wins.
- **Learned value function** V(deck, relics, hp, act) — amortize the lookahead offline; also enables depth-capped combat rollouts.

## §17 Rich value model V2 (relic/upgrade/potion-aware) — historical best on 2026-07-14
Trained train_value_rich.py on vrich.csv (1.44M rows, 10k-sim on-policy). Features:
all 448 with variance — core + d* + u*(upgrades) + r*(relics) + pot*(potions) +
future/path. Val R^2 0.261 vs core-only-refit 0.206 (+0.056). Deployed via
vFeatCsv()==richRow() (train/serve parity); v_server RAW=1005 richRow cols, model
v_rich_xgb.json. Sane top relics: Brimstone +5.0, Dead Branch, Snecko Eye, Necro.
bestBench 1000 sims / 512 seeds / asc0 (PAIRED vs old deck-only V):
  old deck-only V : win 25.0%  floor 41.3
  RICH V2         : win 31.6%  floor 40.7   (+6.6pp win, ~3sigma, 0 server errors)
=> new baseline for future experiments.

## §18 V2 follow-up fixes: true upgrade marginal + relic-identity shopping
Both enabled by V2's u*/r* features. (1) upgrade_pick now flips u{cid}+1 for the
real upgrade value (was V(deck)-V(deck-card) proxy). (2) shop_plan flips bought
relic's r{id} (V2 has no nRelics -> old relic branch was a dead no-op; shop had
stopped buying relics); C++ now sends shop relic ids.
bestBench 1000 sims / 512 seeds / asc0 (paired):
  rich V2 only              : win 31.6%  floor 40.7  endHp 14.2
  V2 + upgrade + shop-relic  : win 38.7%  floor 42.0  endHp 18.4   (+7.1pp, all metrics up, 0 errs)
=> historical best at this point in the ledger. Cumulative this session: 25.0% -> 38.7% (+13.7pp).

## §19 Re-sweep skip + rest-V thresholds on V2 (512 seeds / 1000 sims, rest off unless noted)
SKIP threshold (V2 shifted the optimum negative vs old model's 0.0):
  never-skip 40.2 | -1.0 41.4 | -0.5 42.4 | -0.25 41.6 | 0.0 38.7 | 0.25 27.9 | 0.5 21.1 | 1.0 12.3   (win%)
  => band -1.0..-0.25 all good; peak -0.5. V2 marginals read pessimistic -> fuller deck wins. New default = -0.5.
REST-V (at skip=-0.5): OFF 42.4 | on0.0 34.6 | on0.1 40.2 | on0.15 40.2 | on0.25 40.6 | on0.5 38.7 | on1.0 40.6
  => rest-V still HURTS win% (trades win for depth: floor 44+ but endHp/win down). Stays EXCLUDED.
CONFIRM skip=-0.5 @1024 seeds: win 40.7% floor 42.7 endHp 19.2 (512-set 0..511 was 42.4; 2nd half harder).
=> NEW BEST default: skip@-0.5 + heuristic path + shop-V + rich V2, rest-V off.

## §20 Win-rate model + win-based rest policy (P(win) > floor-V for survival decisions)
train_winrate.py -> build/v_win_xgb.json (target=won, binary:logistic, same rich feats).
Val AUC 0.748 logloss 0.535. HP-sensitivity probe (heal 30% maxHp, P(win) gain by HP band):
  0-20%:+.053 | 20-40%:+.078 | 40-60%:+.073 | 60-80%:+.054 | 80-100%:+.007  (~10x sharper low HP)
=> survival-shaped signal the floor target lacks. Served as 2nd booster (VWIN) w/ HW/UW endpoints;
C++ restWinPolicy = threshold-free (rest iff healGain_win >= best upgradeGain_win). g_restWin default ON.
bestBench @512 (skip@-0.5, same seeds):  default rest 42.4% f43.2 hp19.8  ->  WIN-REST 47.3% f45.0 hp21.0  (+4.9pp, all up)
bestBench @1024:                          default rest 40.7%             ->  WIN-REST 44.4% f44.5 hp20.5  (+3.7pp)
=> NEW BEST. Principle: P(win)=true objective (sharp for survival/threshold), V_floor=denser proxy
   (better for fine card ranking; P(win) saturates/near-0 gradient there). Route per decision.

## §21 High-sim best-stack + difficulty-tiered combat sims (128 seeds asc0)
Flat 50k best stack (skip@-0.5 + rich V2 + relic-shop + win-rest): win 81.2% floor49.5 hp46.8 34.6cpu-s/run
  -> new 50k BEATS old policy's 100k (66.4%) by +15pp; OOC gains x search depth compound. (128 seeds SE~3.5pp)
Tiered (STS_SIMS_NORMAL/ELITE/BOSS, pin elite/boss=50k, cut normal):
  normal10k: 78.1% 24.1cpu | normal5k: 76.6% 25.2 | normal2k: 73.4% 24.6 | n5k/e25k/b50k: 75.0% 21.9
FINDINGS (refutes naive tiering): (1) normal fights are NOT the compute sink — cpu plateaus ~24s once
normal<=10k; elites+bosses dominate (longer fights = costlier sims). (2) "normal" too coarse — act3 monsters
~ act1 elites, so cutting normal-sims costs win% monotonically. No free lunch: compute & importance are ALIGNED.
=> real lever = CONVERGENCE-BASED early stopping inside the searcher (stop any fight once best line decided),
   not static type tiers. Env knobs kept for manual compute/win trades (normal=10k = -3pp for -30% cpu).

## §22 Convergence-based early stopping (searcher change) — ON the flat frontier, NO free lunch
Added BattleScumSearcher2::searchToTotalAdaptive: cap at target sims but stop once bestActionValue
(monotone) plateaus for `patience` sims past a `minSims` floor. Env STS_CONVERGE=1 / STS_CONV_PATIENCE / STS_CONV_MIN.
128 seeds asc0, max 50k:  pat1000: 44.5%/2.07cpu | pat2000: 50.0%/2.91 | pat5000: 64.8%/4.90
Matched-compute FLAT baseline:  flat2000: 50.0%/2.87 | flat4000: 60.9%/4.32
=> convergence ~= flat at equal cpu (2.9cpu: 50.0 vs 50.0 identical; 4.9cpu: +1-2pp within 128-seed noise).
FINDING (2nd combat-efficiency dead end after §21 tiering): combat compute & importance are ALIGNED because
HP MARGIN COMPOUNDS -- deep search finds the least-HP-lost winning line, and that HP feeds every later fight +
the win-rest policy. So no cheap subset of fights to skip; adaptive stopping rides the same cost/win frontier as
a lower flat sim count. Real lever = cheaper/smarter PER-SIM (policy-guided MCTS / faster rollouts), not fewer sims.
Knobs kept (STS_CONVERGE etc.) but OFF by default; no win at fixed compute.

## §23 Profile + optimize combat inner loop ("faster rollouts") — no cheap safe win
Profiled single-thread gprof. EASY fight (mcts, 3-turn): tree-selection heavy -> evaluateEdge looked 10%.
Applied SAFE bit-identical micro-opt: hoist std::log(parentVisits)+evalRange out of the per-edge loop in
selectBestEdgeToSearch (was recomputed ~13M times). Result BIT-IDENTICAL (mcts WIN 79/80 t3) but timing
5.86->5.74s = within noise. LESSON: gprof-on-`-pg` over-attributes high-call-count fns (mcount per-call
overhead that vanishes at -O2 inlining); evaluateEdge wasn't really 10%.
HARD fight (evalcombat 8k/6): real cost = the std::function ACTION-QUEUE effect system --
executeActions 11% + addToBot 9% (59M calls) + Action::execute/addToTop/popFront ~ together ~25%. Spread,
no single hotspot. ActionFunction = std::function<void(BattleContext&)>; cards enqueue lambda effects drained
each step. Meaningful speedup would need replacing std::function Actions with POD/tagged-union dispatch = big
RISKY core-engine rewrite. Kept the evaluateEdge hoist (correct, harmless). CONCLUSION: safe micro-opt yields
~0; combat throughput lever is really policy-guided MCTS (fewer sims) not a cheaper per-sim. Parked.

## §24 V_win vs V_floor for CARD PICKS (A/B) — WASH (unlike rest, which win clearly wins)
Added win-model card endpoint CW (P(win) marginal) + C++ g_cardWin/g_cardWinSkip (STS_CARD_WIN/_SKIP).
Metric isolation @256 (never-skip, only metric differs): floor 41.4% vs WIN 48.0% (+6.6pp, looked real).
Win-skip sweep @256: never 48.0 | -0.03 52.0 | -0.02 52.3 | -0.01 52.0 | -0.005 43.0(cliff). Peak 52.3 vs floor-champ 47.7.
BUT 512-seed confirmation: floor-champ 47.3% vs win skip-0.02 46.5% -> TIED (floor marginally ahead). The 256
lead was a lucky seed-0..255 draw (regression to mean). => card picks are a WASH; keep V_floor (tuned champ).
Consistent w/ principle: P(win) wins for SURVIVAL/threshold decisions (rest +4.9pp robust) but ~ties V_floor for
fine card RANKING (dense-proxy vs true-objective cancel). Win-metric plays safer (lower floor, higher endHp).
CW infra kept env-gated OFF (g_cardWin default false); may matter at higher ascension. Defaults unchanged.

## §25 V_win vs V_floor for SHOPS (A/B) — WASH (like cards; win helps only rest/survival)
Added SW endpoint: shop_plan parameterized on model (V_floor or V_win) via _model_ctx; C++ g_shopWin (STS_SHOP_WIN).
512 seeds / 1000 sims:  floor shop (champion) 47.3% f45.0 hp21.0  vs  WIN shop 47.3% f44.5 hp20.6  -> EXACT TIE.
0 server errors. => shops are a wash; keep V_floor. SW infra kept env-gated OFF (g_shopWin default false).
CONCLUSION of the V_win-vs-V_floor sweep (§24-25): P(win) beats V_floor ONLY for the survival/HP decision
(rest, +4.9pp robust); for deck-VALUE ranking (card picks §24, shops §25) it's a WASH -- fine-grained ranking
favors the denser floor signal, which cancels P(win)'s right-objective edge. So: win-rate for rest, floor for
card/shop/deck value. Both models stay served (v_rich_xgb.json + v_win_xgb.json); CW/SW/UW win-endpoints kept for future (higher asc / events).

================================================================================
§26  ALPHAZERO-LITE: policy-guided combat MCTS (PUCT)  [2026-07-15]
================================================================================
GOAL: combat is search-limited (44%@1k -> 81%@50k). Every cheap-sims shortcut
failed (§21-23). The remaining lever = a learned POLICY PRIOR so MCTS reaches the
same strength at FEWER sims (AlphaZero-lite).

PIPELINE (all in-process native C++ inference -- no per-sim sockets):
 1. Datagen: new `policygen` mode + g_onSearchComplete hook logs, at every root
    decision, each edge's (state feats ++ action feats) with its VISIT COUNT and
    the decision total. Shared extractor combatExtractPolicyFeatures (state block
    = combat value feats; action block = card id/cost/upg/type/target + Expert
    play-order & obtain-weight). 3000 runs @10k sims -> build/vpolicy.csv, 595,338
    edge-rows / 90,571 decisions (6.6 edges/dec).
 2. Train: comparator net(state,action)->logit, target = log(visit+1) (sim budget
    ~constant so it's a consistent logit; C++ softmaxes over a node's edges ->
    prior). train_policy.py, GPU XGBoost, depth6. Val top-1 agreement 0.465 vs
    0.189 uniform (2.5x). Exports compact tree text -> CombatValueNet(isPolicy=1).
 3. PUCT: Edge gains a cached `prior`; computeEdgePriors fills it at node
    expansion (once/sim). selectBestEdgeToSearch swaps UCB's log term for
    c_puct*P(a)*sqrt(Nparent)/(1+Nedge) when a policy net is loaded. Env
    STS_POLICY=<trees> STS_CPUCT=<c>.

RESULTS (evalcombat GremlinNob, starting deck, 512 seeds, in-distribution):
  sims   UCB win%   PUCT-100/c2.5 win%     UCB hp   PUCT hp
   25     74.0        90.8                  21.9     31.9
   50     85.5        95.5                  28.3     36.6
  100     91.8        97.7                  33.1     39.3
  200     94.7        98.4                  36.1     42.1
  500     98.6        99.4                  41.1     44.0
 => PUCT@50 (95.5%) ~= UCB@200-500. **4-8x sim reduction for equal combat strength.**

TREE-COUNT / SPEED (sims=50, 512 seeds; per-sim inference cost matters):
  UCB 85.5% @0.53s | PUCT-50 93.9% @0.65s | PUCT-100 93.9%(c1.5)/95.5%(c2.5) @0.75s
  | PUCT-200 96.3% @1.04s | PUCT-447 97.3% @1.65s. First ~50-100 trees capture
  most of the gain; PUCT-100 dominates UCB on BOTH win% and wall-time. Deploy
  artifact = build/policy_trees_c.txt (100 trees).
C_PUCT sweep (PUCT-100, sims=50): 0.5->78.3 (under-explores, WORSE than UCB!),
  1.0->90.4, 1.5->93.9, 2.5->95.5 (best), 4.0->95.7. Ultra-low sims need MORE
  exploration atop the prior; c_puct=2.5 default. (Optimal c_puct likely falls as
  sims rise -- revisit per operating point.)

STATUS: combat-isolated thesis CONFIRMED. NEXT = validate on FULL runs with the
good OOC stack (does PUCT@~150 combat sims match UCB@~1000 at ~5x speedup, or lift
win% at equal sims?). Artifacts: build/policy.json (full), policy_trees.txt (447),
policy_trees_c.txt (100, deploy), train_policy.py, truncate_trees.py, vpolicy.csv.

--- §26 FULL-RUN validation + DEPLOY (good OOC stack, v_server, bestbench) ---
Combat-isolated gains DO lift full-run win rate at EQUAL sims (but the low-sim
speedup does NOT transfer -- hardest late fights still need the sims):
  256 seeds:  UCB@1000 47.7% f45.4 hp21.4 | PUCT@1000 51.6% f46.1 hp23.1 (+3.9pp)
              PUCT@250 34.0% (too few sims for act3/boss/act4 even with prior)
  512 seeds (CONFIRM, same seeds): UCB@1000 47.3% f45.0 hp21.0 cpu2.90
              -> PUCT@1000 c2.5 **51.6% f45.8 hp23.2** cpu3.20  = +4.3pp / +0.8f /
              +2.2hp for +10% cpu. All three metrics up.
DEFAULT ON (per "if it wins make it default"): one_combat auto-loads
build/policy_trees_c.txt (100 trees, c_puct 2.5) for all PLAY modes; STS_POLICY=0
disables, =1 uses full 447-tree net, =<path> overrides; auto-load skipped for
policygen so base datasets stay UCB-generated. Historical known-RNG best at this point = 51.6% @512.
Takeaway: the payoff is STRENGTH-at-equal-sims, not fewer-sims -- full runs are
bottlenecked by the hardest fights where the prior helps but can't replace search.
NEXT ideas: (1) AlphaZero self-play iteration (regen vpolicy.csv WITH PUCT on ->
retrain -> stronger prior); (2) per-budget c_puct (lower at high sims); (3) add a
value head / leaf blend now that the prior concentrates search; (4) test PUCT@1500-
2000 (combat is search-limited, prior makes each sim more valuable).

--- §26 SIM-BUDGET curve: more time/combat + the PUCT<->UCB CROSSOVER ---
Full-run win% (best OOC stack, asc0, v_server). PUCT = policy_trees_c.txt c2.5:
  sims    PUCT      UCB      seeds
  1000    51.6      47.3     512    <- prior default
  2000    59.6      51.2     512    (+8.4pp PUCT edge)
  3000    62.3       --      512
  4000    64.1      62.9     256
  6000    61.7       --      128 (noisy)
 10000    70.3       --      128
 14000    70.3       --      128
 20000    73.4      80.5     128    <- UCB OVERTAKES (+7pp)
=> Spending MORE time/combat pays off strongly under PUCT up to ~3-4k sims
   (51.6->62.3 @3k, +11pp). BEST PRACTICAL operating point = PUCT@2000-3000.
=> **Historical interpretation:** crossover around 6-10k sims. Only the 20k
   point directly pairs UCB and PUCT beyond 4k, so the interval itself was not measured.
   At 20k plain UCB wins and reaches the ~80% ceiling
   (UCB@20k 80.5%, matching the known 81%@50k), while fixed-c PUCT plateaus ~73%.
c_puct @20k (128 seeds): 0.5->50.8, 1.0->66.4, 2.5->73.4 (MONOTONE UP: high sims
   want MORE exploration, opposite of the low-sim regime where 0.5 under-explored).
WHY PUCT caps below UCB at high sims: PUCT exploration ~ c*P*sqrt(Nparent)/(1+Nedge)
   decays as 1/Nedge; UCB's ~sqrt(logN/(Nedge+1)) decays as 1/sqrt(Nedge) -- slower,
   so UCB keeps probing alt moves at high visit counts while PUCT commits early. The
   prior is a scarce-search ACCELERATOR, not a raise of the asymptote. To lift the
   PUCT asymptote: value-net leaf (AlphaZero's other half; failed w/o a prior
   [[combat-value-function]], retry now) or an exploration schedule, not c_puct.
DEPLOY: default stays PUCT c2.5. Recommended run budget bumped guidance = 2000-3000
   combat sims (was 1000): PUCT@3000 = 62.3% @512 vs old 47.3% (+15pp) for ~2x cpu.

================================================================================
§27  VALUE-NET LEAF (AlphaZero's other half): FAILS known-RNG, WORKS fair-play [2026-07-15]
================================================================================
Q: with the PUCT prior now in place, does a learned V_combat leaf (replacing/
blending the random rollout) finally help? Infra already existed (g_useVNet,
g_vnetAlpha, STS_VNET; blend value = a*Vnet + (1-a)*rollout, a>=1 skips rollout).
Regenerated combat value data with STRONG PUCT play -> build/vcombat2.csv (92,878
rows, 3000 runs); retrained -> v_combat2.json (val R^2 0.881) -> v_combat2_trees.txt.

KNOWN-RNG (default, searcher peeks at true future): value net HURTS, monotone in a.
  bestbench sims2000/256: PUCT-only 60.5% | +Vnet a0.3 52.7 | a0.5 49.6 | a0.7 40.2.
  WHY: known-RNG rollout is random only in ACTION choice -- it plays vs the TRUE
  fixed future, so it's near-ORACLE. A learned average can only blur it. Nothing to
  denoise. (Explains the earlier "value net failed" result too -- it was never the
  selection OR the leaf; the PRIOR was the only lever in known-RNG.)

FAIR-PLAY (STS_FAIR=1, determinized/ISMCTS: each sim re-randomizes hidden draws ->
genuinely NOISY rollout, the honest no-peek setting): value net HELPS, and the a
ordering INVERTS (scarcer search -> lean MORE on the net).
  evalcombat GremlinNob 256 seeds (win% saturates ~98%, read hp_end):
   sims 50 : rollout 96.1%/35.9hp | +Vnet a0.5 96.9/39.3 | a0.7 **98.8/39.6** (+2.7pp/+3.7hp)
   sims100 : rollout 98.0%/39.5   | a0.5 98.0/40.5        | a0.7 98.8/41.8 (+0.8pp/+2.3hp)
   sims300 : rollout 98.4/40.9    | a0.5 98.8/42.2        | a1.0 97.7/41.1
   sims1000: rollout 98.8/42.2    | a0.5 100.0/42.8       | a1.0 97.7/41.6
  a0.5-0.7 blend > a1.0 (pure net): keep the noisy rollout as an anchor; the net
  (known-RNG-trained, so optimistically BIASED for fair play) denoises but isn't
  trusted alone. A fair-play-TRAINED net should do better.

CONCLUSION: AlphaZero's value-net half does NOT transfer to our known-RNG solver
(the rollout is already oracle) but DOES help in the honest FAIR-PLAY regime where
rollouts are real Monte-Carlo. So the value net is a FAIR-PLAY tool. New env toggle
STS_FAIR=1. NEXT (if pursuing honest play): regen combat value data UNDER fair play
(unbiased labels), retrain, and likely regen the PRIOR under fair play too; then
establish the fair-play win-rate baseline (expect well below known-RNG's 81% ceiling
since the agent can no longer peek). Artifacts: vcombat2.csv, v_combat2*.

--- §27 RICH combat features (relics + card identity/location) [2026-07-15] ---
The combat state features were AGGREGATES only (counts/sums) -- no card identity,
no card LOCATION, and ZERO relic info. So [Bash,Strike,Strike] looked identical to
[Offering,LimitBreak,Feed], and a Corruption in-hand vs in-draw vs exhausted looked
the same. Same blind spot the rich OOC model fixed. Enriched combatExtractFeatures
(single source of truth -> both value & policy nets, train/serve parity preserved):
  + 128 relic-presence (r0..r127; hasRelicRuntime only valid <128)
  + per-card-id counts x 4 piles: hd*/dr*/ds*/ex* (hand/draw/discard/exhaust),
    371 card ids each.
  = 50 aggregates + 128 relics + 1484 card-location = 1662 combat feats (was 50);
  policy = +14 action = 1676.
COST GUARD: filling 1662 feats/leaf tripled the hot path (2.86->9.05 cpu/run). Added
g_richCombatFeatures gate: combatExtractFeatures fills the wide block ONLY when a
loaded model reads it (load() auto-detects a rich feature in sel[]) or during datagen
(forced). Legacy narrow nets => narrow fast path (verified back to 2.73 cpu/run).
computeEdgePriors also now extracts the shared wide STATE once/node and refills only
the 14 action feats per edge (was re-extracting per edge). Old policy_trees_c.txt
still loads (its names are a subset) so deployed PUCT is unaffected.
(Debug note: a stray orphaned bench process pinning all cores at 1082% masqueraded
as a code slowdown -- always check `ps --sort=-pcpu` before trusting cpu_sec/run.)
NEXT: fair-play rich datagen -> retrain rich fair V_combat + prior -> re-run the
fair-play value-net A/B (does richness beat the crude net's +3.7hp?).

--- §27 COMPLETE combat features + rich FAIR value net (2026-07-15) ---
User pushed to record the FULL combat state, not just relics/cards. Added to
combatExtractFeatures (now 1770 feats, was 50; gated by g_richCombatFeatures so the
deployed narrow path stays 2.1 cpu/run):
  enemy INTENT (per-monster predicted dmg + attacking) + aggregate incomingDmg;
  per-monster id/hp/block/str/vuln/weak/poison (5 slots); potions by id (44);
  gold; potionCapacity; cards/attacks/skillsPlayedThisTurn; 8 persistent relic
  counters (Nunchaku/PenNib/InkBottle/HappyFlower/IncenseBurner/Inserter/Sundial/
  Panache). Per-turn counter relics (Kunai/Shuriken/Fan/LetterOpener) covered by the
  play-counts. Gold IS a live combat feature (Hand of Greed etc.); only truly-inert
  state (other-class stances/orbs) omitted.
FAIR datagen: combatgen STS_FAIR=1, 2000 runs @1500 sims (killed the last ~200 hung
seeds -- robustness todo #1 -- but 379,891 rows was plenty). Retrain -> v_combat_fair
val R^2 **0.912** (best ever; crude 0.886, rich-knownRNG 0.881). 740 non-const feats.
FAIR-PLAY A/B (evalcombat GremlinNob, 256 seeds), rollout vs +richV leaf:
   sims 25: rollout 92.2%/32.7hp | +richV a0.7 99.2/42.1 | a1.0 99.2/42.1 (+7pp/+9.4hp)
   sims 50: rollout 96.1%/35.9   | a0.7 99.6/43.1                        (+3.5pp/+7.2hp)
   sims100: rollout 98.0%/39.5   | a0.7 100/43.3                         (+2pp/+3.8hp)
 => RICH fair value net ~DOUBLES the crude net's gain (+7.2hp vs +3.7hp @50). And
    PURE-net a1.0 now works (crude a1.0 always HURT): the complete net is accurate
    enough to REPLACE the rollout -> ~1000-sim-rollout quality (42hp) at 25 sims.
    Textbook AlphaZero value head, unlocked by (a) fair play (noisy rollouts to beat)
    + (b) complete features. Artifacts: v_combat_fair.json/_trees.txt, vcombat_fair.csv.
NEXT: fair prior (policygen STS_FAIR) + fair-play FULL-RUN baseline, then value net on
full runs (does the isolated +9hp translate to fair-play win%?).

