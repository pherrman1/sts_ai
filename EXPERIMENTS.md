# StS AI — Experiment Log

Tracks each modification we try, its configuration, and the measured result, so we
can see which ideas actually moved win rate / run depth and which didn't.

**Fixed setup unless noted:** Ironclad, ascension 0, seeds `0..N-1`, 8 threads (OpenMP).
Combat is MCTS via the built-in `BattleScumSearcher2` (a *known-RNG* solver — rollouts
see the real upcoming draws, so numbers are an optimistic upper bound, not fair-play).
Out-of-combat decisions use `ScumSearchAgent2`'s heuristic policies unless the experiment
replaces one. All harness code is in `apps/one_combat.cpp`.

Metrics: **win%** (normally reached and beat the Act 3 boss; all-key runs can
continue to Act 4), **avg_floor** (how deep it got), **avg_hp_end**, and compute.
Despite its label, current `bestBench` **cpu_sec/run** is mean per-run
steady-clock elapsed time; **wall** is the outer benchmark wall time.

**Ledger reading rule (2026-07-31):** every “best,” “current,” “deployed,” or
“running” statement below is a dated historical statement unless a later entry
explicitly confirms it. The maintained current configuration and benchmark
qualification live in
`docs/knowledge-base/evaluation/current-baselines.md`. Known-RNG and project-fair
results are different regimes and must never be compared as one progression.
Missing flags, hashes, or artifacts remain unknown; do not reconstruct them.
In particular, the `fairgen` mode does not set `STS_FAIR` or
`STS_SEARCHER3`; a historical entry or schema that omits either flag does not
establish the intended project-fair Searcher3 generation path.

---

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

## §28 Fair-play FULL-RUN validation — the value net TRANSLATES (2026-07-15)
Built fair prior (policygen STS_FAIR=1, 800 runs -> vpolicy_fair.csv 692k rows;
train_policy -> v_policy_fair.json top-1 0.474; truncated -> policy_fair_trees_c.txt 100t).
Then fair-play full-run A/B (128 seeds, 1000 sims, OOC held constant, v_server up):
  A fair rollout baseline           win 18.8  floor 37.3  hp 8.3   (5 cpu/run)
  B +fair prior only                win 16.4  floor 38.4  hp 8.9   (wash/neg)
  C +prior +vnet a0.3               win 24.2  floor 39.5  hp 11.4
  D +prior +vnet a0.5               win 25.0  floor 39.0  hp 12.2
  E +prior +vnet a0.7               win 21.1  floor 38.3  hp 9.3
  F vnet-only a0.3 (NO prior)       win 25.0  floor 40.8  hp 12.4  (BEST, 26 cpu/run)
  G vnet-only a0.5 (NO prior)       win 19.5  floor 38.3  hp 7.6
VERDICT: the isolated +9hp fair value net TRANSLATES to full runs: +6.2pp win /
+3.5 floor / +4 hp over fair baseline. **The PRIOR is dead weight in fair play**
(B wash; F==D at half cost). a0.3 is the sweet spot without the prior (a0.5 overshoots
-> leans too hard on net). Caveat: 128-seed SE ~3.8pp (18.8 vs 25.0 = 1.6sigma);
floor/hp gains consistent across all vnet arms corroborate. Cost: vnet leaf = 26 vs 5
cpu/run (1780-feat XGBoost walk every leaf) -> truncate trees next. Best fair config =
STS_FAIR=1 STS_POLICY=0 STS_VNET=build/v_combat_fair_trees.txt STS_VNET_ALPHA=0.3.
NEXT: 512-seed confirm (baseline vs F); truncate value trees for speed; low-sim arm.

## §28b Value-net truncation — 100 trees, 3.5x faster, gain intact (2026-07-15)
Full fair value net = 1500 trees @ 21.7 cpu/run (fair full-run). Truncated (truncate_trees.py):
  trees   full-run cpu/run    isolated GremlinNob 256s@50sims (fair, a0.3)
  1500    21.7                win 100.0  hp 40.9   (vs rollout-only 96.1 / 35.9)
   400     8.2                --
   200     6.7                win 98.4   hp 39.8
   100     6.2  (3.5x)        win 99.2   hp 40.0   <- PICK
100 trees keeps +3.1pp/+4.1hp of the full net's +3.9pp/+5.0hp at leaf cost 6.2 vs 5.0
rollout (~free). DEPLOY fair vnet = build/v_combat_fair_100.txt. 512-seed confirm now cheap
(~4.5min/arm). Accuracy plateau mirrors the crude-net/policy-net ~100-tree plateau.

## §29 Boss-aware drafting from EXISTING data (no datagen) (2026-07-15)
Autopsy: default-OOC agent 0.6% win vs server-V 25% (40x) => deckbuilding dominates.
Deaths cluster at ACT BOSSES (median death floor 16; 62/159 at A1 boss).
DIAGNOSIS: v_rich HAS bossId + nextFight* features but NEAR-IGNORES them -- boss-family
= 1.38% of gain (bossId 0.51%); it learned generic deck->finalFloor, not deck-vs-THIS-boss.
=> a TARGET problem, not a data problem. No new datagen needed (vrich.csv has bossId + finalFloor).
FIX: train_boss_survival.py -> P(pass next act boss | state), label = finalFloor > bossFloor[act]
(act1=17,act2=34,act3=50) on the SAME rows. val AUC 0.9106. boss-family importance ~2x (2.54%).
Card marginals are boss-appropriate: TOP Panache/DemonForm/Apotheosis/Mayhem/Reaper (scaling),
BOTTOM curses+dead cards. vs v_rich near-boss (Spearman 0.855 = agrees but re-ranks): drafts UP
DemonForm/LimitBreak/FeelNoPain/FireBreathing (sustained scaling), DOWN Immolate/Feed/Bludgeon
(burst-AoE, good vs hordes not a lone boss). = the right scaling-over-burst shift before a boss.
build/v_boss_xgb.json. Rollout-draft prototype (§ prior) HURT (-4.7pp, noisy 2-future/150-sim
estimator < trained V); boss-V marginal is the cheaper inference-free replacement.
NEXT: serve v_boss, use its marginal for near-boss card picks, 512-seed A/B (128 too noisy;
also truncated-100 vnet may cost vs full-1500 on full runs -- confirm on 512).

## §30 Boss-V blend draft A/B + progress tracker (2026-07-15)
Wired v_boss into near-boss drafting: v_server CB op computes v_rich & v_boss card
marginals, z-normalizes each across candidates (floors vs prob scale), blends
(1-w)*zr+w*zb, returns chosen card's v_rich marginal (skip logic unchanged). C++ sends
CB only within STS_BOSS_DRAFT_ROWS(=3) of a boss (STS_BOSS_V=1, STS_BOSS_V_W=w). ~free.
512-seed fair A/B (vnet100 a0.3):
  control (v_rich)   win 17.4  floor 36.8  hp 6.6
  boss-V w=0.3       win 18.4  floor 36.9  hp 7.2   <- best
  boss-V w=0.5       win 18.0  floor 37.0  hp 6.8
  boss-V w=0.7       win 18.0  floor 36.8  hp 7.4
READ: small CONSISTENT positive (all 3 weights > control, +0.6..1.0pp, hp +0.6..0.8) but
within 512-seed noise (SE_diff ~2.4pp; +1.0pp = 0.4sigma). Matches the 0.855 model overlap:
only a few near-boss picks change. w=0.3 best (light touch). Reasonable KEEP at ~free cost,
NOT the big lever. To amplify: widen gate rows, or sharpen boss model (per-boss / condition
on reaching boss). NOTE control 17.4% @512 vs old arm-F 25% @128 = mostly 128-seed NOISE
(truncation confound still unconfirmed; full-1500 @512 arm would isolate it).
Also: BenchProgress live \r status line (n/total, running win%/floor/hp, elapsed+eta, TTY-only
so logs stay clean) now default in bestBench.

## §31 CORRECTION: more combat-net trees = higher full-run win% (2026-07-16)
Direct test (128 seeds, fair, vnet-only a0.3), same seeds, only tree count varies:
  100 trees   win 16.4  floor 35.6  hp 6.6   (6.9 cpu/run)
  200 trees   win 14.8  floor 36.0  hp 6.8   (7.7)     [win% dip = noise]
  400 trees   win 19.5  floor 38.4  hp 9.4   (10.0)
  1500 trees  win 25.0  floor 40.8  hp 12.4  (27.1)
FLOOR + HP are MONOTONIC in tree count (low-variance corroboration): full net is
genuinely better, +8.6pp/+5.2floor/+5.8hp over 100. CORRECTS §28b + the earlier
claim that "25%@128 vs 17%@512 was mostly seed noise" -- it was MOSTLY TRUNCATION.
The isolated GremlinNob test (100~=1500) was MISLEADING: per-fight ~equal, but small
degradation COMPOUNDS over ~30 fights/run. DEPLOY = full 1500-tree v_combat_fair_trees.txt
(accept 4.5x combat cpu for the win%); 400 = fallback middle (+3pp @1.6x). Overnight
datagen should use >=400-tree net for better finalFloor labels (was 100).

## §32 Overnight fresh-data OOC models: NEGATIVE (volume-starved) (2026-07-16)
Ran datagen2 with the FULL 1500-tree fair combat net (best labels) ~10h -> vrich2.csv
393,635 rows / 26,403 runs (vs old vrich 2.9GB ~6x more). Retrained v_rich2 (finalFloor
R^2 0.352) + v_boss2 (AUC 0.827 on ITS OWN noisier val split -- not comparable to old 0.911).
Head-to-head 128-seed fair A/B (full net + boss-V w0.3), only OOC models swapped:
  OLD v_rich/v_boss   win 27.3  floor 40.6  hp 12.0
  NEW v_rich2/v_boss2 win 18.8  floor 38.7  hp 6.7
=> NEW is -8.5pp/-1.9floor/-5.3hp, consistent across metrics = REAL degradation, not noise.
CAUSE: data VOLUME. 394k rows too few vs old 2.9GB -> value model data-starved (rare
cards/decks). Better strong-agent labels did NOT compensate for ~6x less coverage. KEEP the
OLD models deployed. To make fresh-data retrain win: need multiple nights to reach comparable
volume (./datagen2_loop.sh 26000 300000 continues, disjoint seeds), THEN retrain. Uncertain
payoff. Side result: arm A 27.3% reconfirms FULL-net deploy (~25-27% @128). Assets kept:
v_rich2_xgb.json, v_boss2_xgb.json, vrich2.csv (append more nights before using).

## 33. V-informed pathing (deck-strength modulation)  ➖ (small, ~free, default off)
- **What:** the map heuristic (`roomValue`/`chooseMapAction`) is deck-BLIND. The next-fight
  features are a shared encounter QUEUE (route-independent at a decision) so V(state) is ~flat
  across immediate children -> per-child V scoring gives no signal. Instead use V(state) as a
  deck-STRENGTH scalar: server op `VS` returns raw V(state)=predFloor; C++ `vStateRaw` (1 query/
  floor) -> `aggr = clamp((predFloor - bossFloor[act]) / 8, -1, +1)`. aggr>0 (comfortably clearing
  the act) scales elites/fights UP + rest/shop/event DOWN; aggr<0 the reverse. Env STS_VPATH=1,
  gain STS_VPATH_K (default 0.4). Off = byte-identical to the old heuristic.
- **256-seed (1000 sims):** off 51.6% / f46.1 / 23.1hp -> k=0.4 **56.6%** / 26.8hp (+5.0pp) ; k=0.7 50.0% (overshoot).
- **512-seed confirm:** off 51.6 / f45.8 / 23.3 -> k=0.3 **53.7** / 24.5 ; k=0.4 **53.7** / f46.0 / 24.8 ; k=0.5 52.7.
- **Verdict:** ➖ the 256-seed +5pp was mostly NOISE (regressed to +2.1pp @512 = ~1sigma). SMALL
  consistent positive though: all V-arms > baseline, end-HP +1.2..1.5 (most stable), coherent
  dose-response (peak k=0.3-0.4, down by 0.5/0.7). Same class as boss-V blend: marginal ~free
  keeper behind STS_VPATH (DEFAULT OFF), k~0.35. NOT the big lever; needs 1024-seed confirm before
  default-on. Confirms the standing "pathing = small lever" finding (exp 6/6b) — NOT overturned.

## 34. Deck-set NN win-value model (DeepSets card embeddings)  ➖ (ties GBM; data-ceiling)
- **What:** test the thesis that GBM is synergy-blind and a SET NN over card embeddings should
  model card interactions better. train_deckset.py: deck vector = (d-u)@E_base + u@E_up (sum-pool
  == counts@E, no token expansion), + relic/potion/boss embeddings + z-normed scalars -> MLP ->
  sigmoid P(win). Target=won, GroupShuffleSplit(0.15,rs=0) by seed (SAME split as v_win GBM).
  torch 2.5.1+cu121, RTX 3060 Ti, ~2s/epoch, 126k params.
- **Result:** v1 (dropout 0.1, lr 2e-3) overfit hard (peak 0.737@ep4 then collapse). v2 (dropout
  0.3 everywhere incl pooled deck vec, lr 1e-3, wd 2e-4, best-ckpt) converged clean ->
  **val AUC 0.7497 @ep13 == GBM 0.7482 (TIE).** Two independent model classes hit the same ~0.75
  => **Inference:** the tested capacity increase did not beat the GBM on this
  data/label (~57k effective independent runs). This is consistent with a data/label
  bottleneck but does not prove a ceiling. Synergy did not improve absolute P(win) AUC.
- **Ensemble (eval_ensemble.py, streamed val-only, same rows):** GBM 0.7482 / NN 0.7476 / pred-corr
  0.912. Blend w=0.5 **AUC 0.7536 (+0.0054)**, logloss 0.5348->0.5308. Small but REAL orthogonal
  signal (different errors). Deployable via v_server blend (both models Python-side) if wanted.
- **Caveat / real open question:** absolute-P(win) AUC does NOT measure DRAFT MARGINAL quality.
  The NN's synergy payoff (if any) is in V(deck+card)-V(deck) depending on deck composition, which
  a tied absolute AUC can hide. The meaningful test is a full-run A/B serving NN (or blend) card
  MARGINALS vs GBM -- not yet run.
- **OPS NOTE:** loading vrich.csv float32 = ~5.8GB; running >1 loader concurrently thrashed swap and
  OOM-killed the user's IDE. eval_ensemble.py rewritten to stream val-only chunks (<1GB peak);
  train_deckset.py guarded under __main__ so importing DeckSet does NOT re-load the CSV. Keep to ONE
  CSV loader at a time.

### 34b. Deck-set NN card-MARGINAL full-run A/B  ➖ (does NOT beat v_rich drafting)
- **What:** the deciding test the absolute-AUC tie couldn't settle — does the NN's synergy-aware
  card marginal V(deck+card)-V(deck) improve DRAFTING? Served CN op in v_server (pure NN or
  w*NN+(1-w)*v_win), C++ STS_CARD_NN=1 / _W / _SKIP. A/B vs deployed v_rich floor drafting.
- **Skip-sensitive:** NN P(win) marginals are dilution-shifted (adding a card often lowers P(win)),
  so skip@0 skips too much (thin deck, floor 41). Swept skip on 32 seeds: -0.005 gave 62.5% (!!).
- **BUT 128-seed = the 32-seed spike was NOISE.** baseline 47.7%/f46.6/22.8hp ; NN skip=-0.005
  44.5/f39.1 ; NN skip=-0.02 **49.2**/f43.1 ; blend0.5 46.1/f40.3. Best NN arm TIES on win (49.2 vs
  47.7, within 4.4pp SE) but is -3..-7 FLOOR on every arm: same win%, decks lose EARLIER when they
  lose = worse mid-run decks. Also the skip=-0.005 "win" at 32 seeds was itself noise-overfit
  (-0.02 better at 128). +2hp on survivors doesn't compensate.
- **Verdict:** ➖ NN drafting does NOT beat v_rich. Together with the AUC tie (§34) and ensemble
  +0.005, this tested deck-set NN is negative for deckbuilding; the synergy hypothesis did not
  pay off here. **Inference:** data/labels are the more promising next lever, but these runs do not
  prove a fixed 0.75 ceiling. DEPLOY UNCHANGED (default path still
  v_rich; NN only via STS_CARD_NN env). To beat the ceiling: more runs or a better LABEL (bootstrapped
  /TD win value), not a fancier model. v_server now also loads v_deckset.pt (harmless; +~torch mem).

## 35. Dynamic potion-saving policy  ➖ (hurts both regimes; shelved)
- **Motivation:** data probe showed potions ARE used (~5.5/run, ~1% of runs never use one, mean
  potionCount 0.64 of ~3 cap, 46% at zero -> NO hoarding). The combat MCTS is per-fight MYOPIC
  (never sees future fights), so it spends potions on easy fights with no incentive to bank them
  for elites/bosses where we die. Hypothesis: saving potions for hard fights helps.
- **Design:** evaluateEndState already values a KEPT potion at 4 HP-equiv (drinking costs ~4 HP);
  made that DYNAMIC via search::g_potionKeepValue set per-fight by potionKeepValue(gc):
  ELITE/BOSS room -> keep=1 (spend); else if a hard fight (nearest elite/boss) within WINDOW rows ->
  keep = 4 + BONUS*proximity*scarcity where scarcity = 1 - (hardDist * pDrop)/DESIRED and
  pDrop = WhiteBeastStatue?1:potionChance/100 (refill-aware, per user's potion-chance point).
  Env STS_POTION_SAVE=1 (+WINDOW/BONUS/SPEND/DESIRED). Verified correct via trace (hoards keep 7->21
  as hardDist 5->1 in monster fights, keep=1.0 in elites/bosses).
- **Result (128 seeds known-RNG, 1000 sims):** baseline 47.7%/f46.6/22.8hp ; save-default 41.4
  /45.7/20.3 ; bonus25 42.2/44.8/22.9 ; window3 39.1/45.7/19.7 = **-5..-9pp, ALL configs worse.**
- **Result (64 seeds FAIR-PLAY):** baseline 21.9%/f36.8/8.4 ; save-default 18.8/36.9/6.0 ;
  bonus25 18.8/f36.5/**11.2hp** = -3.1pp (~0.6sigma). Strong arm = MORE end-HP, FEWER wins (the same
  healthier-survivors-fewer-wins signature as the NN draft §34b) = shifts HP<->win tradeoff the WRONG way.
- **Verdict:** ➖ hurts win% in BOTH regimes; gradient points toward baseline (no saving) => optimum
  is ~no saving. 4th combat-search bias to fail for the SAME reason (after depth-cap, TT, known-RNG
  learned-leaf): the per-fight search already makes locally-good potion decisions; forcing hoarding
  costs approach-fight HP/wins that banked potions don't repay. Deaths at bosses = a DECK problem,
  not potion-timing. SHELVED (STS_POTION_SAVE default off; g_potionKeepValue defaults 4 = unchanged).

## 36. Fairy in a Bottle bug (found via runtrace)  ✅ (real sim bug, fixed)
- **Tool:** new `runtrace <seed> <sims> <asc>` mode (STS_FAIR for fair-play) prints a per-map-node
  human trace (room, encounter/event, HP/gold, deck delta + full deck, relics, potions), draft
  OPTIONS + v_rich marginals, and can refight a floor N times (STS_REFIGHT_FLOOR/_N) to separate
  luck from a bad fight model. Built to audit decisions vs human game knowledge.
- **Bug:** BattleScumSearcher2::enumeratePotionActions emitted a "use" action for FAIRY_POTION
  (target -1). Fairy is NOT usable/discardable in StS -- it auto-procs on lethal in
  Player::wouldDie (heal 30% maxHp). drinkPotion's Fairy case is assert(false), but libsts.a is
  built NDEBUG so it silently discarded the Fairy and did nothing -> the search could THROW AWAY
  the auto-revive for zero benefit. (SimpleAgent.canDrink and isValidPotionAction already excluded
  Fairy; the MCTS enumerator was the outlier.) Confirmed via refight: Looter fight used the Fairy
  30/30 times.
- **Fix:** `continue` (enumerate no action) for FAIRY_POTION. Verified: same refight now uses it
  0/30. Strictly removes a dominated move (can only help/neutral); deployed (libsts rebuilt).
- **Audit findings (seed 0, fair-play, DEATH F16 Slime Boss):** (1) low-marginal DRAFT takes:
  Rupture taken at v_rich marginal +0.05 (skip bar -0.5) -- the floor-value model doesn't penalize
  deck BLOAT so near-zero filler gets slurped (human skips). (2) Lagavulin -44hp was NOT unlucky:
  refight 30x = 0 deaths, endHP med 32 (our 36 typical) -- deck just pays HP. (3) Slime Boss from
  52/74 = 29/30 DEATHS (~unwinnable): a DECK problem, not just the pre-boss smith-over-heal rest.
  Everything traces to a weak/bloated deck = the known deckbuilding+label ceiling.

## 37. Self-play training loop — Phase 0 (harness)  ✅ (validated end-to-end)
- **Goal (user-directed):** AlphaZero-style self-play to break the deckbuilding data/label ceiling
  WITHOUT hand knowledge (user explicitly refused expert tiers / bloat penalties — model must learn
  it from outcomes). ONE unified fair-play meta model V_win(state)->P(win) drives card/shop/rest
  (all = "which resulting state has higher V"; no separate shop/rest models). Fair-play throughout
  so the fight model is realistic.
- **Built:** `selfplay/loop.sh` (resumable loop) + `selfplay/status.sh` (console dashboard).
  Per iter: fair-play datagen N runs -> retrain V_win on last WINDOW iters -> GATE candidate vs
  current on held-out seeds -> promote iff cand win% >= current -> checkpoint. Resumable via
  selfplay/state.env (Ctrl-C anytime; re-run continues). Atomic promotion; win-count guard (skip
  retrain if <20 wins/one class); gate seeds 0..GATE held-out (self-play seeds >=1e6).
- **Validated (2 iters @1000 sims):** datagen 150 fair runs->2026 rows; train val AUC 0.76; GATE
  correctly REJECTED the under-trained candidate (0.0% vs current 16.7%) -> current kept, no
  regression. Full pipeline + resume + dashboard confirmed working.
- **Bugs fixed:** datagen2 writes no header on a fresh file (seed vrich header first); bestbench
  prints TWO 'BEST' lines (parse 'win%='); single-class train crash (loop-level win guard).
- **NEXT (Phase 1):** wire COMBAT model retraining (v_combat_fair value net + policy prior) into the
  loop; scale to thousands of runs/iter (overnight-scale, fair-play ~6x slower); tune replay WINDOW
  (volume-vs-freshness risk, cf §32). Note: unified-V_win OOC start is ~slightly weaker than deployed
  v_rich floor drafting, so iter-0 under-performs 51.6%; the loop must climb from there.

## 38. Self-play loop — Phase 1 (combat retraining wired)  ✅ (validated end-to-end)
- **What:** extended the Phase-0 loop to retrain the FULL agent, not just meta V_win. Now each iter
  retrains 3 heads and gates the whole stack all-or-nothing: meta V_win + combat VALUE NET
  (combatgen->train_value_combat->export_combat_model) + POLICY PRIOR (policygen->train_policy).
  Self-play datagen + gate use the current stack (STS_VNET=current value trees + STS_POLICY=current
  prior, cenv() helper). COMBAT=1 default (0 = meta-only Phase-0), POLICY_RETRAIN, VNET_TREES, POLICY_SIMS.
- **Fixes:** datagen2/combatgen/policygen wrote a header only `if(!append)` and self-play seeds>=1e6
  -> always "append" -> no header -> train KeyError. Now write header when file empty (f.tellp()==0),
  backward-compatible. train_winrate now saves the model BEFORE computing AUC so a single-class val
  split (common in early self-play) can't crash away the trained model.
- **Validated (1 iter @300 sims, 60 runs):** 3 datagen passes (meta 882 / combat 14868 / policy 59888
  rows, all headered); value net retrained R^2 0.827 -> exported & LOADS (200t, "[V_combat leaf value
  ON ...]"); policy retrained -> LOADS (576t, "[policy PUCT ON ...]"); gate measured full candidate
  stack (cand 0% vs curr 6.2% -> correctly NOT promoted at tiny scale). Atomic all-or-nothing promote.
- **Cost note:** datagen now = 3 full-run passes AND uses the value-net leaf (~5x combat cost) -> much
  slower/iter; overnight-scale with thousands of runs. Loop is resumable + trackable as before.
- **NEXT:** kick a real run at scale (RUNS_PER_ITER in the thousands); consider per-head gating if
  all-or-nothing stalls; tune replay WINDOW (volume-vs-freshness, cf §32).

## 39. Self-play loop — combined datagen + per-side gating  ✅
- **Combined datagen (fightgen):** new C++ mode `fightgen nSeeds sims asc eps valOut polOut seedOff`
  installs BOTH hooks (g_onCombatDecision value snapshots + g_onSearchComplete visit-π) in ONE play
  pass -> emits the value (endHp) AND policy CSVs perfectly aligned. Self-play datagen is now 2
  full-run passes (meta + fightgen) instead of 3 -> ~2x combat cost, not 3x.
- **Per-side gating (user's "bail-out"):** meta and combat sides A/B'd INDEPENDENTLY against the same
  baseline, each holding the OTHER side at current: promote meta iff (cand_vwin + cur_combat) >=
  current; promote combat iff (cur_vwin + cand_combat) >= current. A stuck side never blocks the
  other. History now: base / meta / combat win% + per-side promote flags.
- **Validated (1 iter @300 sims):** fightgen -> combat 14868 + policy 63723 rows; value net R^2 0.829,
  policy trained, both load; gate: base 6.2%, meta cand 0.0% (rejected), combat cand 6.2% (PROMOTED
  independently) — the meta side stuck while combat advanced, exactly the intended decoupling.

## 40. Boss-relic + Neow picks via V_win  ➖ (wired; not a standalone win at current model)
- **What:** the default heuristic used to own boss-relic + Neow picks (never model-driven -> a gap for
  self-play, since the model can't learn nodes the heuristic controls). Wired both through V_win:
  server "VW" op = raw V_win(state); bossRelicVPolicy/neowVPolicy COPY the gc, apply each option
  (real transition, RNG untouched on the real gc), evaluate V_win, argmax. Env STS_BOSS_RELIC / STS_NEOW_V.
- **A/B (128 fair seeds, 1000 sims, SE ~3.5pp):** baseline 18.8% ; +boss-relic 18.0 ; +Neow 17.2 ;
  +both 21.1/+1.6hp. ALL within noise -> NOT measurably important at current model quality: the default
  boss-relic priority table + default Neow are already competitive, and v_win isn't strong enough to beat
  them. KEEP wired (model must own these for self-play; they improve as v_win improves) but not a standalone win.
- **FEATURE GAP flagged for the datarun:** model sees PARTIAL path info only -- past = pv* room-type
  counts; future = bossId + nextEliteId + nextFight0/1/2 + remElites/remFights. MISSING the full remaining
  MAP TREE (layout ahead, branch options, rows-to-next-elite/rest/shop/boss, remaining reachable room
  counts). The map is deterministic/KNOWN = free info. Add forward-map features (distances + remaining
  reachable counts, maybe flattened 15x7 grid). The map is the ONE spatial/graph structure in StS -> the
  only place a conv/graph encoding fits.

## 41. Forward-map features + model-driven pathing/events  ✅ (features) / ➖ (path needs retrain)
- **Forward-map features (the datarun enabler):** appended 10 cols to richRow/richHeader + server RAW
  (fmDElite/Rest/Shop/Boss = rows-to-next; fmCElite/Rest/Shop/Event/Monster/Treasure = reachable-ahead
  counts). ONE map-reachability sweep (forwardMapFeatures). Appended LAST so existing models are
  unaffected: backward-compat VERIFIED (64-seed fair 23.4% == pre-fm baseline; server loads old models
  fine on the wider 1015-col vector). Map is deterministic/known -> free info the value model lacked
  (previously only pv* history + next-few-fights). Flows into datagen automatically; value model learns
  it on retrain.
- **Model-driven decisions wired (STS_PATH_V / STS_EVENT_V; boss-relic/Neow §40):** so the model owns
  every node (needed for self-play). A/B 64 fair seeds vs current fm-BLIND v_win:
  - model EVENTS = exact wash (23.4 vs 23.4) -> safe, upside once model improves.
  - model PATHING = CATASTROPHIC 6.2% (-17pp) -> pathVPolicy leans on fm features the current model
    ignores -> degenerates to leftmost-child. MUST stay OFF until v_win is retrained on fm data.
- **CONFIG for self-play:** fm features ON (automatic), pathing HEURISTIC + events default (clean iter-0
  data), flip on STS_PATH_V/STS_EVENT_V LATER once retrained v_win uses fm (gate to confirm). Never ship
  STS_PATH_V with an fm-blind model.

## 42. Full map graph capture (seed-determinism, zero bloat)  ✅
- **Insight:** the StS map is DETERMINISTIC from seed+act (both already stored per row), so the full
  node+edge graph need NOT be flattened into every decision-row (that'd repeat the same ~100-400 map
  cols ~30x/run = huge redundant bloat). Instead record POSITION and regenerate the graph on demand.
- **Added:** curMapX,curMapY to richRow/richHeader/server RAW (now 1017 state cols); `dumpmap <seed>
  <asc>` mode dumps the map graph (per node: y x room edges...). Future GNN pipeline: read
  (seed,act,curMapX,curMapY) from a row -> dumpmap -> build node+edge graph. Zero per-row bloat.
- **No trainer changes needed:** no bloaty grid added; the 10 fm aggregates + 2 position cols are all
  tree-friendly (position ~ progress). Full graph lives only in dumpmap, out of the training CSV.
- **Backward-compat VERIFIED again** on the wider 1017-col vector: 64-seed fair 23.4% (== baseline),
  old models load + serve, 0 server errors.

## 43. Native C++ V_win (kill the v_server socket for OOC)  ✅ (core done, validated)
- **What:** ported V_win to a native XGBoost tree-walk so OOC decisions skip the Python socket.
  export_win_model.py -> build/v_win_trees.txt (feats + logistic + base_score + trees). C++ WinNet
  (app-level, in one_combat.cpp): load maps model feats -> rich raw indices via richIdxMap() (from
  richHeader), predict = tree-walk + baseMargin=logit(base_score) + sigmoid. Feature vector =
  richFeatureVec(gc) (parse of vFeatCsv). Env STS_WIN_NET=1 (or path).
- **VALIDATED exact:** winnettest mode -> native vs server VW over 434 samples/5 seeds:
  max|native-server| = 1e-6. Full-run A/B (STS_CARD_WIN+BOSS_RELIC+NEOW): server 18.8%/f33.5/10.4 ==
  native (STS_WIN_NET) 18.8%/f33.5/10.4 -> BYTE-IDENTICAL decisions.
- **Native now:** card pick (nativeWinCardPick, mirrors decide_win: base + per-card d{cid}/deckSize
  delta), boss-relic, Neow, path (all via vStateWin). STILL socket: rest (HW/UW), shop (SW), v_rich
  card path, CB/CN blends -> full elimination needs porting those (mechanical, same predict+delta).
- **ROI (as flagged):** small datagen speedup (6.40 vs 6.56 cpu/run) -- combat DOMINATES (~6s/run),
  OOC socket is <1% -- so this is mainly an architecture cleanup + makes model-driven pathing cheap
  (100s of native per-candidate calls/run vs unbatched socket round-trips). Bigger datagen levers stay:
  modest self-play sims + truncated value net.

## 44. Adaptive paired self-play gate + live telemetry  ✅ (mechanics validated)
- **Why:** a fixed 500-seed gate is statistically defensible at ~5-8% win, but it always pays for
  baseline + meta + combat (up to 1,500 full runs), even when a candidate is clearly better/worse.
- **Gate:** evaluate common held-out seeds in 100-seed batches up to 500. For each candidate, compute
  the per-seed paired delta of `avg_floor + 0.1*win%`; promote only when the conservative lower
  confidence bound (default Z=2.58) exceeds the 0.5-floor margin, reject when the upper bound cannot
  clear it, and extend only inconclusive candidates. An inconclusive result at 500 is rejected.
- **Telemetry:** `bestbench` optionally appends flushed `seed,won,floor,hpEnd,sec` rows. The watcher
  now shows live step-3 arm/progress, win%, avg floor, paired delta/CI, datagen avg floor, and floor
  metrics in history. Mechanics validated by compiling, a nonzero-offset two-seed CSV smoke run,
  synthetic promote/reject cases, and a mocked live dashboard. Full selection behavior remains to be
  observed over subsequent real iterations.

## 45. CPU scaling: OpenMP run-per-thread vs. process-per-run  ✅
- **Setup:** Ryzen 5 7500F (6 physical cores / 12 SMT threads), 12 identical full `datagen2` seeds,
  600 simulations, current self-play stack and shared V_win server. The live iteration-4 datagen
  worker was SIGSTOP'd for the controlled test and resumed afterward without losing CSV progress.
- **Wall time / speedup:** 1 thread 91.89s / 1.00x; 2 threads 49.38s / 1.86x; 4 threads 27.20s /
  3.38x; 6 threads 21.28s / 4.32x; 8 threads 17.89s / 5.14x; 12 threads 17.06s / 5.39x.
  All variants completed all 12 distinct seeds without errors.
- **Multiple processes lose:** twelve concurrent one-thread processes took 19.31s / 4.76x, 13.2%
  slower than one 12-thread OpenMP process. The executable already assigns one independent STS run
  per OpenMP thread with dynamic scheduling, so process-per-run adds model/process overhead without
  exposing more parallelism.
- **Operational conclusion:** keep one `one_combat.elf` process and set `OMP_NUM_THREADS` to the
  available vCPUs. On this SMT desktop, 8 workers are the efficiency knee; 8 -> 12 adds only 4.9%
  throughput. Cloud scaling must be measured separately past one socket / NUMA domain, but sharding
  into multiple processes is not warranted by this benchmark.

## 46. Replay-window repair + deterministic baseline cache  ✅ (live gate validated)
- **Diagnosis:** after 2,000-run iterations were reduced to 500, the shared 5-iteration replay
  window eventually fell from 4,997/3,497 V_win trajectories (val AUC 0.722/0.765) to 2,002
  trajectories (AUC 0.631). Policy was not starved: each 500-run iteration still produced about
  0.5M edge rows / 100k decisions with stable 0.52-0.54 top-1 agreement. Combat candidates gained
  roughly 1-2 average floors but repeatedly exhausted the strict 500-seed gate inconclusively.
- **Changed:** separate `META_WINDOW=10`; retain combat `WINDOW=5` and memory-safe
  `POLICY_WINDOW=1`; adaptive `GATE_SEEDS=1000` (100-seed looks). Iteration 7 V_win then trained on
  6,497 trajectories and recovered to val AUC 0.7554.
- **Baseline cache:** deterministic held-out baseline rows are cached by SHA-256 over the executable,
  deployed V_win/value/policy models, policy mode, sims, ascension, value blend, and behavior-affecting
  `STS_*` environment. A promotion/model/binary/config change therefore invalidates automatically.
  Seeded from the verified iteration-6 0..499 baseline; iteration 7 live gate confirmed cache hits at
  100, 200, and 300 seeds instead of replaying them.
- **Failure safety:** gaming consumed GPU VRAM and all iteration-7 CUDA trainers failed. The old loop
  incorrectly checkpointed a no-model/no-gate `NA` row. That row/state advance was reverted; trainers
  now mark errors and retry without checkpointing. Local continuation uses `STS_XGB_DEVICE=cpu` while
  gaming. CPU rerun successfully trained V_win, combat value, and the 800-tree policy candidate.
- **Dashboard load:** three simultaneous watchers were each rescanning a completed ~400MB combat CSV
  every two seconds. `status.sh` now trusts the authoritative `.done` marker for completed combat
  progress, removing that repeated CPU/disk load.

## 47. One-run CPU profile: combat value inference dominates  ✅
- **Setup:** representative cached seed 2 (floor 40), fair-play current stack, 600 sims, one OpenMP
  worker pinned to CPU 0. The active datagen worker was paused and automatically resumed. A temporary
  optimized `-pg` binary used the same simulator library/models; `strace -f -c` and `/usr/bin/time -v`
  captured OS behavior. Profiled wall/user time was 14.26/13.95s, CPU utilization 97%, RSS 11.5MB.
- **Flat profile:** `CombatValueNet::predictVec` consumed **75.33% / 10.41 CPU-seconds**.
  Next largest self-time was simulator action execution 2.24%, card usability 1.30%, action
  enumeration 1.23%, action-queue insertion 1.09%, search step 0.87%, and combat feature extraction
  0.80%. Random rollout itself was only 0.51%. Total traced syscall time was 0.021s; 45 socket
  request/response pairs and file I/O were negligible, so this is compute-bound native inference.
- **Same-seed production timing split:** both value+policy 15.23s; value-only 13.44s; policy-only
  4.56s; neither 3.31s. Disabling models changes search decisions, so attribution is directional, but
  it consistently puts the 1,500-tree combat value ensemble at roughly 10-11s (~70% of wall), the
  100-tree policy at roughly 1.3-1.8s (~10%), and base simulator/MCTS at ~3.3s (~22%).
- **Why:** current value model = 1,500 trees / 311,006 nodes / 4.35MB; policy = 100 trees / 11,078
  nodes / 160KB. Each MCTS leaf walks all value trees through branch-heavy, dependent node loads.
- **Optimization priority:** first gate a 300-400-tree or shallower/distilled value model; a roughly
  linear inference reduction has far more upside than simulator micro-optimization. Then flatten the
  tree-of-vectors representation and resolve model feature indices to canonical indices at load time
  (removes one dependent lookup per split). Policy and feature extraction are secondary. Preserve
  held-out strength: this profile justifies what to optimize, not promoting a faster weaker model.

## 48. Combat-value tree-count latency sweep  ✅ (speed only; not promoted)
- **Setup:** truncated the deployed 1,500-tree value ensemble after its first 800, 400, and 200
  trees, preserving feature metadata and base score. Kept the deployed 100-tree policy fixed. Timed
  the same representative seed 2, fair-play stack, 600 sims, one worker pinned to CPU 0. The live
  iteration-9 gate worker was paused for isolation and automatically resumed afterward.
- **Results:** 1,500 trees / 311,006 nodes = **11.21s** (floor 40); 800 / 180,344 = **7.50s**
  (floor 40); 400 / 105,196 = **5.08s** (floor 40); 200 / 63,722 = **4.98s** (floor 44).
  Thus 400 trees was **2.21x faster** than the deployed model on this run and retained its observed
  floor, while 200 trees provided essentially no additional wall-time reduction because its changed
  decisions produced a longer run.
- **Conclusion:** 400 trees is the practical latency candidate: it removes 55% versus 800 trees and
  55% versus the 1,500-tree wall time without chasing the route-dependent 200-tree floor. This is a
  one-seed timing result, not sufficient quality evidence. Do not replace the deployed baseline
  mid-gate; evaluate a 400-tree value candidate with the same 100-tree policy on held-out paired
  seeds before promotion.
- **Actual iteration-9 candidate check:** its independently trained 400-tree value (117,888 nodes)
  took **6.05s** with the current 100-tree policy (floor 45), still **1.85x faster** than the 1,500-tree
  baseline. But the gate couples it to a new 800-tree policy (69,392 nodes), making that complete
  candidate take **12.47s** (floor 44), slightly slower than the deployed stack on this seed. Any
  speed-oriented promotion therefore needs to keep/cap the policy near 100 trees or gate value and
  policy changes separately.

## 49. Self-play meta-gate collapse was a serialization/fallback bug  ✅ fixed
- **Symptom:** iterations 7-9 produced identical held-out meta outcomes on every seed: 0% wins and
  average floor 12.9, despite different V_win models and improving validation AUC (up to 0.7908).
- **Root cause:** `loop.sh` trained to a filename ending in `.json.tmp`. XGBoost therefore selected
  binary UBJSON serialization, after which the file was renamed to `.json`. `v_server.py` failed to
  parse it as JSON but treated V_win as optional and continued. Unified card drafting then received
  its no-model fallback (`skip`, marginal -999) for every reward. The repeated meta results measure
  that deterministic fallback, not candidate quality or model variance.
- **Fix:** training temporaries now end in `.tmp.json`; self-play starts the server with
  `VWIN_REQUIRED=1`, making missing, malformed, or feature-incompatible requested models fatal. The
  existing iteration-9 candidate was losslessly loaded as UBJSON and re-saved as real JSON; its 197
  trees and 458 feature names were verified after conversion. Shell/Python syntax checks pass.
- **Evidence impact:** all prior unified-meta gates using these mislabeled candidates are invalid.
  Keep the deployed meta model unchanged and rerun the iteration-9 100-seed meta gate before making
  any claim about V_win variance or unified card/shop policy quality.
- **Corrected 100-seed gate:** with the converted model genuinely loaded, candidate performance rose
  from the invalid 0% / floor 12.9 to **5.0% / floor 29.13**. The paired deployed baseline was
  **29.0% / floor 38.78**; blended-score delta **-12.05**, SE 1.785, 99% CI
  **[-16.656, -7.444]**, therefore reject. The serialization bug explained most of the catastrophic
  result, but the unified V_win card+shop policy remains a clear systematic regression at this
  iteration. Do not restart full self-play with unified meta enabled; isolate card, shop, and rest
  arms before changing the objective/data or attributing the gap to estimator variance.

## 50. Corrected V_win decision-family ablation + independent self-play gates  ✅
- **Setup:** corrected iteration-9 V_win candidate, deployed combat stack, 600 sims, 100 common
  held-out seeds, eight workers. A no-win-decision control disabled win-based card/shop/rest. Each
  candidate arm enabled exactly one decision family; paired score was `floor + 10*won`, with the
  standard 99% interval and +0.5 promotion margin. All four arms ran serially.
- **Rest only:** 25% / floor 38.19. Versus deployed current-rest baseline (29% / 38.78), delta
  **-0.99**, CI **[-4.959, 2.979]**; versus no-rest control (20% / 38.77), delta **-0.08**, CI
  **[-4.264, 4.104]**. Inconclusive/wash: candidate rest is neither promotable nor clearly harmful.
- **Card only:** 17% / floor 31.26 versus control 20% / 38.77; delta **-7.81**, CI
  **[-12.629, -2.991]**: clear reject.
- **Shop only:** 10% / floor 35.19 versus control 20% / 38.77; delta **-4.58**, CI
  **[-7.569, -1.591]**: clear reject.
- **Conclusion:** unified V_win fails independently at both counterfactual card and shop scoring;
  this is not merely interaction between the two or estimator noise. Keep V_floor for card/shop and
  gate retrained V_win only on rest decisions. Learning card/shop later needs action-value/ranking
  targets or randomized counterfactual coverage, not more iterations of the same state classifier.
- **Loop refactor:** meta gates now retain the deployed hybrid and never auto-graduate to unified
  card/shop control. Combat value (candidate value + deployed policy) and combat policy (deployed
  value + candidate policy) have separate CSVs, confidence decisions, and atomic promotions; if both
  pass simultaneously, policy is deferred one iteration to avoid an untested combined stack. Policy
  training is capped by `POLICY_TREES=100` (default 100), while combat value remains capped at 400.
  Dashboard and history schema now report value and policy arms separately.

## 51. Larger training iterations, smaller held-out cap  ✅
- **Changed:** `RUNS_PER_ITER` from 500 to **1,000** and adaptive `GATE_SEEDS` from 1,000 to
  **500** (100-seed looks unchanged). This puts twice as many fresh self-play trajectories behind
  each retrain while bounding verification to half the previous worst case.
- **Resume safety:** `.done` markers now record the run target that created them. A marker is trusted
  only when it equals the current `RUNS_PER_ITER`; empty legacy markers or later target changes fall
  back to distinct-seed CSV counting. Iteration 9 therefore recognized its existing 500 meta and
  500 combat runs and launched exactly the missing 500 of each, beginning meta at seed 1,007,502.
- **Operation:** stopped the old in-memory 500/1,000 controller and resumed a single loop on eight
  logical CPUs with CPU-only XGBoost, 400 value trees, and 100 policy trees. This changes the
  training/evaluation allocation only; promotion still requires the same paired +0.5 margin and
  conservative 99% interval, with clear candidates allowed to stop before 500 seeds.

## 52. Speed-oriented self-play profile + value non-inferiority  ✅ deployed
- **Value promotion rule:** combat value is a latency optimization, so it now promotes when the 99%
  lower confidence bound beats `VALUE_MARGIN=-0.5`; meta and policy retain the stricter
  `PROMOTE_MARGIN=+0.5` superiority rule. Iteration 9's independently gated 400-tree value scored
  delta **+1.562**, CI **[-0.117, +3.241]**, and therefore passes non-inferiority. It was atomically
  deployed (122,080 nodes); the previous 1,500-tree / 311,006-node model is preserved as
  `selfplay/current/v_combat_trees.pre_iter9_1500.txt`. Earlier timing measured the actual candidate
  at 6.05s versus 11.21s for the deployed old stack with the same 100-tree policy (~1.85x faster).
- **Separate budgets:** combat/policy datagen uses **400 sims**, meta-label datagen **300 sims**, and
  held-out gates remain at **600 sims** through a new `GATE_SIMS` setting. Baseline-cache keys use
  the gate budget, so changing cheap datagen budgets cannot reuse or contaminate verification.
- **Cadence:** V_win and policy retrain/gate every **2** iterations (even iteration numbers by
  default); their data is still collected each iteration. Combat value continues every iteration.
  This removes repeated expensive gates for the historically wash/inconclusive rest and policy
  heads while preserving fresh replay data for their next scheduled update.
- **Validation:** shell syntax passes; cadence smoke gives due at iterations 10/12 and skipped at 11;
  the iteration-9 CSVs reproduce the non-inferiority promotion; deployed candidate/current hashes
  match; dashboard reports separate 400/300 datagen and 600 gate budgets and the value-specific bar.

## 53. Historical execution snapshot: iteration 10 on a Google VM
- **Machine:** `sts-test` in `europe-west3-c`, resized to Spot `c4d-highcpu-16`. The project exposes
  64 all-region CPUs, but the enforced C4D-family quota is 24 vCPUs; 16 is therefore the largest
  predefined C4D shape that can start without another quota approval. The loop uses all 16 OpenMP
  threads and CPU-only XGBoost.
- **Resume state:** the local loop was interrupted safely at iteration 10 and its **278/1,000**
  distinct completed meta trajectories were copied to `/mnt/sts-data/sts_lightspeed` together with
  the current models and required replay windows. The remote meta worker resumed exactly the
  remaining 722 runs at seed **1,008,280**; combat datagen remains 0/1,000.
- **Runtime safety:** the new 400 GB data disk holds the active workspace (2.8 GB at launch). A
  16 GB swap file on that already-provisioned disk supplements the VM's 29 GiB RAM to avoid an OOM
  kill during replay-window loading; it was unused at launch. The detached worker reported 16
  threads and roughly 1,400% CPU during its initial sample.
- **Resume audit/fix:** OpenMP completion order meant the interrupted 278-run meta file already held
  two seeds beyond its contiguous prefix. Resuming at `SEED_OFF + distinct_count` therefore reused
  two IDs and left seeds 1,008,023 and 1,008,275 absent. Both missing runs were appended with the
  same deployed stack, restoring exactly **1,000 unique meta seeds** while combat generation kept
  running. Future resumes now append beyond the maximum observed seed, persist that collision-free
  next seed in two-field `.done` markers, and advance `state.env` past the maximum used by either
  datagen pass; the dashboard accepts both legacy and new marker formats.

## 54. Strong-teacher redesign — historical iteration-12 plan/deployment snapshot
- **Teacher/student separation:** combat self-play targets now use `POLICY_SIMS=1000` while the
  deployed/gated agent remains at 400/600 simulations. The combined fight pass still emits value
  snapshots and policy visit targets once, but its policy target is now produced by a materially
  stronger search instead of redistilling the student's own 400-sim behavior.
- **Critical-state combat value:** `train_value_combat.py` weights low-HP, failed-fight,
  empirically high-failure-encounter, and high teacher-disagreement roots. Weights are clipped and
  mean-normalized; encounter difficulty is inferred from replay outcomes, not a hand-written tier
  list. Decision indices now advance even through forced roots and reset per fight, giving exact
  value/policy alignment. A four-run smoke matched all 274 sampled policy decisions and trained
  with disagreement on 274/362 value rows.
- **Paired campfire action values:** meta datagen optionally forks genuine rest-vs-smith states from
  the same pre-action context, uses a detached map and common future agent seed, and records both
  continuations. `train_rest_cf.py` predicts the direct paired gate-score difference; `v_server.py`
  serves it as `RC`, and deployment falls back to the existing V_win marginal comparison until a
  paired model passes the held-out gate. A 50-run smoke emitted 104 decisions from 37 runs, trained
  and served a compatible model, and replayed the previously crashing seed successfully.
- **Cadence and safety:** V_win, paired rest, combat value, and policy retrain/gate every two
  iterations by default; fresh data is still collected each iteration. Promotions retain the
  adaptive paired common-seed gate, 99% confidence bounds, +0.5 superiority for meta/policy, and
  -0.5 non-inferiority only for the latency-oriented combat value. At the 500-seed cap,
  inconclusive candidates remain rejected.
- **Operational telemetry:** the dashboard distinguishes deployed, teacher, meta, counterfactual,
  and gate budgets; reports paired-rest source runs/decisions; and avoids displaying a fake 0% win
  rate when a completed combat CSV is represented only by its authoritative marker.

## 55. Iteration-24 review — historical iteration-25 deployment snapshot
- **Progress audit:** iteration 20 produced the only promotion in iterations 12--24, raising the
  held-out deployed stack from **26.8% / 40.346 floors** to **31.4% / 41.218 floors**. Iterations
  22 and 24 regressed against that new baseline, while no meta or policy candidate promoted. The
  run is making real progress, but not yet consistently.
- **Capacity evidence:** iteration 24's validation RMSE was still improving at boosting round 1,499
  (10.154 at 400, 9.919 at 800, 9.785 at 1,499), but the exporter retained only 400 trees. A new
  held-out test of that exact model found the 1,500-tree export at **31.2% / 41.649 floors** versus
  **31.9% / 41.207 floors** for the deployed stack over 285 paired rows: blended delta **+0.372**,
  99% CI **[-1.935, +2.679]**. It is promising but not promotion-grade. The 800-tree export scored
  delta **-0.197**, CI **[-2.234, +1.841]**; on 281 exact common seeds, 1,500 beat 800 by **+0.605**
  blended score, also inconclusive.
- **Change:** future combat candidates now export all **1,500 trees**. Because this is a strength
  candidate rather than the old 400-tree latency optimization, its gate uses the standard
  **+0.5 superiority margin**, not the -0.5 non-inferiority allowance. The inconclusive iteration-24
  export was not promoted; iteration 26 will be the first newly trained full-capacity candidate.
- **Exporter fixes:** the validation output now has its own path instead of overwriting the replay
  training CSV, and validation reads only the 200 rows needed for the Python/C++ parity check rather
  than loading the multi-gigabyte replay window a second time.

## 56. Distilled native combat MLP  ❌ rejected at 500 paired seeds
- **Implementation:** `train_value_combat_nn.py` streams the replay CSV, samples by whole fight,
  predicts the full XGBoost teacher, trains a weighted MLP, and exports a standalone native format.
  `CombatValueNet` now loads either trees or `combat_mlp_sparse_v1`. Normalization is folded into
  the first-layer weights/bias so native inference skips zero card/relic features. Python/C++ parity
  for the final model had maximum error **0.000028 HP**.
- **Training:** the first dense 751->64->32->1 student used 458,638 sampled rows and generalized
  poorly across held-out fights (truth RMSE **11.521** versus teacher **7.159**). The final sparse
  751->128->64->1 student trained on all **1,830,668** iteration-24--28 replay rows (1,644,998 train,
  185,670 fight-group validation). It improved to truth RMSE **9.708**, teacher-imitation RMSE
  **5.749**, and critical-state truth RMSE **12.715**, but still trailed the teacher's **6.963**.
  Random row validation was misleadingly high (0.986 R2) because adjacent states from the same
  fights leak across a row split; the separate fight-group validation is the meaningful measure.
- **Speed:** on matched seed 2 at 600 sims and one core, sparse MLP took **5.043s** versus **11.775s**
  for 1,500 trees (**2.34x faster**). Across the first 100 seeds on 16 cores it took **50.45s**
  versus **66.55s** for the deployed 400-tree stack, about **24% faster** end-to-end.
- **Gameplay gate:** at 500 common seeds, deployed trees scored **31.4% / 41.218 floors** and the NN
  **24.6% / 39.644 floors**. Paired blended delta was **-2.254**, 99% CI
  **[-3.969, -0.539]**: a formal rejection even under the faster-model `-0.5` non-inferiority bar.
  The NN was not deployed. Its trainer, native evaluator support, model, parity data, and gate CSVs
  are preserved for a future categorical/embedding architecture; normal self-play remains on trees.

## 57. Entity-aware multi-head combat model  ❌ rejected at 500 paired seeds
- **Representation/output:** `train_value_combat_entity.py` replaces raw categorical integers with
  learned embeddings and pooling: four 371-card zone pools, relic and potion pools, encounter
  embedding, and a shared per-monster encoder with sum/max pooling. A 212->128->64 trunk predicts
  separate **P(fight win)** and **remaining-HP fraction conditional on winning** heads. Search backs
  up `P(win) * (win_bonus + E[HP|win])`; terminal rollout wins use the same `win_bonus + HP` scale.
- **Training:** CPU PyTorch 2.13 was installed on the VM. The model used 928,231 rows sampled by
  whole fight from the 1,851,423-row iteration-30--34 replay window, with 91,793 rows held out by
  complete fight. Best validation metrics were win Brier **0.0393**, win accuracy **94.9%**,
  conditional-HP-fraction MAE **0.0840**, and expected-end-HP RMSE **10.079** versus **8.049** for
  the iteration-32 tree teacher on the exact rows. Native/Python utility parity max error was
  **0.000022**.
- **Latency:** matched seed 2 at 600 sims took **6.465s** for the entity model versus **5.592s** for
  the deployed 400-tree model, so this candidate is ~16% slower and must prove superiority rather
  than use the faster-model non-inferiority allowance.
- **Tuning:** on seeds 0--99 at alpha 0.3, bonuses 0/25/50/100 produced blended deltas
  **-1.90/-1.51/-1.56/-3.97**. Bonus 25 was least bad. Its alpha sweep 0/0.1/0.2/0.3/0.5 gave
  **-7.04/-1.89/-2.18/-1.51/-2.45**; the catastrophic alpha-0 result shows that changing terminal
  reward to a survival bonus without the learned head does not help. Bonus 25, alpha 0.3 was selected
  and evaluated on untouched seeds 100--499.
- **Final gate:** over all 500 paired seeds, deployed trees scored **31.4% / 41.218 floors** and the
  entity model **27.6% / 40.004 floors**. Paired blended delta was **-1.594**, 99% CI
  **[-3.319, +0.131]**. The untouched 400-seed confirmation independently gave **-1.615**, CI
  **[-3.550, +0.320]**. Its upper bound is below the required **+0.5** superiority margin, so the
  model is formally rejected and was not deployed. Trainer, native format/evaluator, checkpoint,
  parity sample, and sweep/gate CSVs are preserved for research.

## 58. Shared-state entity policy prior  ➖ promising, not promoted at 500 paired seeds
- **Representation/training:** `train_policy_entity.py` encodes the combat state once per decision:
  learned embeddings pool cards separately across hand/draw/discard/exhaust, plus relics, potions,
  encounter identity, and shared monster/intent encoders with sum/max pooling. A 64-dimensional
  state vector and a card-aware action encoder produce a compatibility logit for each legal edge.
  Grouped cross-entropy directly fits the normalized MCTS visit distribution instead of regressing
  `log(visit+1)` independently per edge. The streaming loader retains one state per decision and
  splits by complete fight, permitting a large replay window without duplicating the 1,766-wide
  state for every action.
- **Data:** GPU training on the local RTX 3060 Ti used **every policy edge from iterations 26--35**:
  **16,861,363 edges / 3,127,654 decisions**, with no sampling. These iterations are post-redesign
  and share the post-iteration-20 deployed combat stack; earlier stale-teacher iterations were not
  mixed in. The fight-group split contained 2,815,541 training and 312,113 validation decisions.
  CPU preprocessing was capped at exactly eight threads.
- **Offline result:** the entity NN reached top-action agreement **57.01%**, captured visit share
  **37.87%**, softmax mass on the teacher-best action **34.76%**, and cross-entropy **1.4103**. The
  deployed 100-tree prior on the same held-out fights scored **46.93% / 34.88% / 30.51% / 1.4499**.
  The earlier single-iteration model reached only 53.0% top-action agreement, so the ten-iteration
  replay window materially improved generalization. Python/native maximum logit error was
  **0.0000030** across the 200-row parity sample.
- **Native inference:** `combat_policy_entity_v1` runs the state encoder once when an MCTS node is
  expanded, then only the small action encoder per legal edge. It is wired into the existing PUCT
  softmax without changing search semantics. The existing tree prior remains the default.
- **Current-stack gate:** on 500 common held-out seeds 51000--51499 at 600 sims, fair play, and
  eight threads, the deployed tree prior scored **33.2% wins / 42.280 floors / 12.644 end HP /
  7.225 CPU-s per run**. The entity prior scored **34.6% / 42.062 / 13.864 / 8.210**: +1.4pp wins,
  -0.218 floor, +1.220 end HP, and **13.6% more CPU**. The canonical floor + 10*win paired score
  delta was **-0.078**, SE **0.673**, 99% CI **[-1.815, +1.659]**. This does not clear the required
  +0.5 lower-bound margin, so it is preserved but **not promoted**.
- **Next policy-model test:** enrich future replay rows with target monster identity/status and
  potion identity (the current schema records only target HP and an is-potion flag), then retune
  policy temperature and `c_puct`. The large offline gain did not transfer decisively under the
  tree prior's existing PUCT calibration.

## 59. Entity-aware joint meta value model  ❌ floor head rejected; win head inconclusive
- **Representation/output:** `train_meta_entity.py` replaces the meta trees' thousands of sparse
  scalar columns with learned set encoders. Cards share an ID embedding augmented by count and
  upgraded fraction and use sum/max pooling; relics and potions have their own pooled embeddings;
  bosses, upcoming elites/fights, and bottled cards use categorical embeddings. Thirty-six
  normalized continuous features join a 192->96 trunk with separate **P(run win)** and
  **expected final floor** heads. The floor head predicts bounded remaining progress rather than an
  unconstrained absolute floor.
- **Data/training:** the CPU-only, eight-thread run used every one of the **182,958 state rows from
  10,000 runs in iterations 29--38**, split by complete seed. On the exact held-out rows, the NN
  improved win ranking (AUC **0.7215** vs tree **0.7144**) and floor accuracy (RMSE **9.769** vs
  **10.943**, R2 **0.247** vs **0.055**). Its win probabilities were slightly less calibrated
  (log loss **0.4337** vs **0.4301**, Brier **0.1346** vs **0.1340**).
- **Serving/parity:** `v_server.py` can opt into the joint TorchScript model with `VMETA_NN` and
  independently enable `VMETA_FLOOR` and `VMETA_WIN`; the existing XGBoost models remain the
  fallback/default. Fifty held-out rows matched offline inference within **5.4e-7** win probability
  and **7e-6 floors**. Serving now hides CUDA before importing PyTorch/XGBoost unless
  `VSERVER_ALLOW_CUDA=1`, preventing a CPU inference server from opening a GPU context.
- **Gameplay gate:** on seeds 53000--53099, the deployed tree stack scored **41.0% wins / 42.47
  floors**. Replacing only its floor decisions with the NN scored **27.0% / 35.90**; paired canonical
  score (`floor + 10*win`) delta **-7.970**, 99% CI **[-12.466, -3.474]**. It is decisively rejected:
  lower held-out regression error did not translate into useful action counterfactuals. The win
  head completed 81 paired seeds before interruption and scored **35.8% / 42.32**, delta **-0.506**,
  99% CI **[-4.406, +3.394]**; this is inconclusive and not promising enough to expose the user's
  machine to another large local gate while gaming. Neither head was deployed.
- **GPU incident:** during the partial win-head gate the NVIDIA driver exhausted VRAM, logged an
  MMU fault against a Python channel, then timed out the game context. No benchmark process survived
  the interruption. All inference tensors had been mapped to CPU, but explicit CUDA hiding is now
  enforced as an additional process-level safety boundary.

## 60. Paired card-reward action values with pretrained entity embeddings  ➕ offline-positive, not deployed
- **Target/data path:** `datagen3` can now fork every offered card plus skip from the identical
  pre-choice `GameContext`, detach the shared map, and finish branches with common agent/game RNG.
  Rows are grouped by `(seed, decisionIdx)`, contain the rich 1,017-feature state plus candidate
  identity/upgrade status, and store fractional mean outcomes over multiple matched futures. Output
  is flushed once per complete source run and is safe to interrupt/resume from collision-free seeds.
- **Label calibration:** three-fight bootstrapping through the old floor/win models was rejected: on
  24 exact decisions it chose the full-run-best action only **25%** of the time and had essentially
  zero rank correlation. Full-run 30-sim labels were also unstable versus 100 sims (best-action
  agreement **58.3%**, advantage correlation **0.234**). At 100 sims, averaging two futures gave
  one-vs-two-future advantage correlation **0.846** and sign agreement **91.7%**. Production data
  therefore uses **100 sims, two futures, full-run outcomes**, one sampled decision per source run.
- **Model:** `train_card_cf.py` trains a 180,349-parameter shared state/action model with separate
  base/upgraded card embeddings, pooled relic/potion/encounter state, candidate-to-deck attention,
  paired advantage regression, and a listwise best-action loss. Serving/deployment is intentionally
  deferred until offline ranking and a full gameplay gate pass.
- **Pilots:** with 500 decisions, scratch embeddings scored **36.205** versus **35.815** for the
  deployed floor-tree selector on 100 held-out paired decisions, but CI was wide. At 1,016 decisions,
  scratch training merely tied the tree. Initializing card/relic/potion and shifted candidate
  embeddings from the large-data `v_deckset.pt` checkpoint improved the same 204-decision validation
  to **36.875 / 46.6% best-or-tied**, versus tree **36.365 / 43.1%**. Paired delta was **+0.510**,
  SE **0.709**, 99% CI **[-1.317, +2.337]**: promising but not yet resolved.
- **Unattended scale-up:** the eight-thread, CUDA-hidden user service completed **20,000** additional
  decisions and automatic training. The final dataset has **21,863 decisions / 87,452 action rows**
  with zero partial groups or duplicate actions; 17,490 decisions train and 4,373 seed-held-out
  decisions validate the model. Artifacts are `selfplay/card_models/card_cf_full21k*`.
- **Full offline result:** the NN chose a best/tied action on **42.58%** of validation decisions and
  scored **37.161**, versus the deployed floor tree's **40.52% / 36.714**. Their paired score delta
  is **+0.446**, SE **0.119**, 99% CI **[+0.139, +0.754]**; NN/tree chose the same action 62.6% of
  the time (749 NN wins / 2,978 ties / 646 losses). The direct-action target has produced a
  statistically real offline improvement, but its 99% lower bound does not clear the normal +0.5
  promotion margin and offline labels are not a gameplay gate. Keep it undeployed until native/server
  parity, latency, and an adaptive paired full-run gate pass.

## 61. Full-map graph encoder for paired card values  ➖ implemented, no measured gain
- **Lossless reconstruction:** `one_combat_cardcf.elf mapbatch CARD_CF.csv MAPS.csv` now exports one
  deterministic map per `(seed, ascension, act)`. Each fixed 15x7 graph stores all 105 room ids,
  every outgoing edge as a seven-bit destination mask, and the burning-elite location. The 87,452-row
  full dataset reduces to **21,863 maps / 9.7 MB**. Recomputing the old forward-map distances and
  reachable-room counts from the exported graphs matched **all 21,863 decisions exactly**, so no new
  rollouts were needed.
- **Encoder:** optional fourth-argument map input in `train_card_cf.py` adds learned room, row, column,
  and burning-elite embeddings. A reverse sweep over the layered DAG recursively aggregates mean and
  max child messages, thereby carrying every downstream room and route into each ancestor. A
  state-specific readout pools only the roots/children reachable from the current map position. Its
  96-dimensional result enters the existing pretrained card network through a zero-initialized
  residual adapter. The graph model has **229,373 parameters** versus 180,349/180,950 reported for
  earlier variants and exports successfully to TorchScript.
- **Controlled offline result:** with the proven 21k card model frozen, six graph-only epochs selected
  a best/tied action on **42.9%** of the identical 4,373-decision validation split and scored
  **37.1626**, versus **42.6% / 37.1608** for the exact zero-map checkpoint. Paired delta is only
  **+0.0018**, SE **0.0683**, 99% CI **[-0.1740, +0.1777]**; choices agreed 86.1% of the time
  (267 graph wins / 3,858 ties / 248 losses). This is no evidence of useful map lift: the existing
  summary features likely capture most map information relevant to card selection, and the full-run
  labels remain noisy. Artifacts are `selfplay/card_buffer/card_cf_maps.csv` and
  `selfplay/card_models/card_cf_graph_full21k*`; keep this variant undeployed.
- **Runtime gate:** `VCARD_ACTION` in `v_server.py` and `STS_CARD_ACTION=1` in the C++ agent now
  provide an opt-in direct-action endpoint. It sends candidate upgrade flags, all 105 room ids and
  edge masks, the active burning-elite marker, and the rich state; the NN chooses cards and skip
  directly. A held-out serving row matched offline inference to **3.5e-8**, and TorchScript/runtime
  smoke tests passed. On **500 paired fair-play seeds 65000--65499 at 600 combat sims**, the floor
  tree scored **15.8% wins / 34.862 floors / 36.442 canonical score**; the graph NN scored **17.6% /
  35.770 / 37.530**. Paired score delta was **+1.088**, SE **0.726**, 99% CI **[-0.781, +2.957]**
  (195 NN wins / 159 ties / 146 losses by score). Runtime was only **1.5%** higher. The point estimate
  is encouraging but the 99% lower bound is below both zero and the +0.5 promotion margin, so keep
  the tree deployed. Per-seed results are `card_tree_gate_65000_500.csv` and
  `card_graph_gate_65000_500.csv`.

## 62. Full-map graph NN for path decisions  ➖ predictive gain, policy rejected
- **Data/model:** `mapbatch` now accepts any rich/meta CSV containing `seed`, `ascension`, and `act`.
  The 317,573-state / 21,863-run `pilot_meta.csv` reconstructs to **42,713 unique act maps / 19 MB**.
  `train_meta_entity.py` optionally adds the same reverse-DAG room/edge encoder through a
  zero-initialized residual on the frozen 96,727-parameter entity meta model. For training it pools
  all legal next children; at inference a third position coordinate selects one legal child so its
  complete downstream subtree is scored. The resulting model has **145,150 parameters** and is
  `selfplay/models/meta_graph_full21k*`.
- **Held-out prediction:** on 47,528 run-held-out states, the exact pretrained baseline had win AUC
  **0.7527**, log loss **0.2550**, and floor RMSE **10.328**. The graph residual improved these to
  **0.7752 / 0.2396 / 9.667** (floor R2 **0.330** vs **0.236**). Thus the historical maps are
  reconstructed correctly and contain useful predictive signal.
- **Serving/policy:** `VPATH_GRAPH` plus `STS_PATH_GRAPH=1` provides an opt-in `PG` endpoint. The C++
  agent leaves the actual run state at the parent and asks the NN to score each legal singleton child
  subtree; the heuristic remains the default and fallback. Runtime/TorchScript smoke tests passed,
  and a reconstructed source row matched direct TorchScript inference exactly (zero observed error).
- **Gameplay pilot:** on **128 paired fair-play seeds 66000--66127 at 600 sims**, heuristic pathing
  scored **15.6% wins / 35.953 floors / 37.516 canonical score**. Pure graph-NN pathing scored
  **10.2% / 35.633 / 36.648**. Paired delta was **-0.867**, SE **1.749**, 99% CI
  **[-5.373, +3.639]** (45 NN wins / 26 ties / 57 losses by score), with 7.8% runtime overhead.
  Do not extend or deploy this observational-value policy. Better absolute prediction does not identify
  the causal best route: training pooled the routes chosen by the heuristic, while inference asks for
  unseen singleton alternatives. The next justified version needs paired counterfactual outcomes for
  every legal child (or a conservative heuristic-residual trained on those direct advantages), not
  more epochs on terminal observational labels. Per-seed files are `path_heuristic_gate_66000_128.csv`
  and `path_graph_gate_66000_128.csv`.

## 63. Paired counterfactual path-action NN  ➖ offline-positive, gameplay inconclusive
- **Direct labels:** `pathcfgen` reservoir-samples one genuine branching map decision per source run,
  forks every legal child from an identical detached state, and completes each branch with common
  future agent seeds. Labels use the gate-aligned `floor + 10*win` score. Output is flushed after
  each complete source run. A two-salt 128-decision calibration found advantage correlation
  **0.836**, sign agreement **84.4%**, and best-action overlap **89.8%**, so production uses two
  futures and spends additional compute on more independent decisions rather than more futures.
- **Data/model:** 5,000 unique decisions (11,784 action branches) were collected with no duplicate
  actions or malformed groups; every source map was exported losslessly to
  `selfplay/path_buffer/path_maps_5k.csv`. `train_path_cf.py` initializes the entity/full-map
  encoders from `meta_graph_full21k.pt`, scores each candidate child subtree directly, and trains
  paired centered-regression plus listwise losses. Artifacts are `selfplay/models/path_cf_5k*`.
- **Held-out result:** on 1,000 seed-held-out decisions, the NN selected a best/tied route **64.9%**
  of the time and scored **32.220** versus **30.691** for the deployed heuristic (oracle 36.089).
  Paired delta was **+1.528**, SE **0.266**, 99% CI **[+0.843, +2.214]**. This establishes a real
  one-decision offline gain but is not sufficient for deployment.
- **Runtime integration:** `VPATH_ACTION`/`STS_PATH_ACTION=1` serves the direct `PA` endpoint;
  `STS_PATH_ACTION_MAX` limits non-heuristic interventions and `STS_PATH_ACTION_MARGIN` supplies a
  conservative predicted-advantage threshold. An opt-in `STS_PATH_ACTION_TRACE=1` prints the raw
  choice/margin/capacity response. Server and simulator must share the host network namespace;
  sandboxed simulator runs cannot reach port 5555 and silently exercise fallback policies.
- **Fresh gameplay look:** with at most one zero-margin intervention, 128 paired fair-play seeds
  71000--71127 at 600 sims gave heuristic **12.5% wins / 34.117 floors / 35.367 score** and NN
  **14.1% / 34.188 / 35.594**. Delta was **+0.227**, SE **1.786**, 99% CI
  **[-4.374, +4.827]**, with 7.4% runtime overhead (49 NN wins / 19 ties / 60 losses by dense
  score). This is inconclusive; do not deploy. The proper continuation is the existing adaptive
  gate's remaining 372 fresh paired seeds to the 500-seed cap, not additional training changes.

## 64. Future-fight auxiliary card supervision  ❌ initial model rejected (2026-07-22)
- **What:** paired card/skip continuations now record pass outcomes for the next combat, next routed
  elite, and current-act boss. These are produced by the normal copied `GameContext` continuation and
  combat search—so encounter queues, event pools, map routing, relics, potions, and ascension rules
  are simulated rather than represented by a hand-authored fight tier. The card-action NN receives
  three auxiliary survival logits (loss weight 0.3) while retaining its full-run value/ranking target.
- **Data:** 2,000 fresh full-run paired decisions / 7,853 action branches, adaptive two-to-eight
  futures, `selfplay/card_buffer/card_cf_future_fight_124k_2k.csv`. Near-term normal survival was
  nearly saturated (99.96% pass); elite pass was 97.1%; boss pass was 85.7% overall (89.9% conditional
  on reaching it). Thus boss survival is the meaningful extra supervision, not the next hallway fight.
- **Offline:** on 400 held-out decisions, future-fight NN selected score **37.676** versus **37.231**
  for the floor-tree selector. Its aggregate auxiliary survival accuracy was 95.4%, but is dominated
  by the trivial normal-combat target and is not policy evidence.
- **Fresh fair-play gate:** 128 common seeds 126000--126127 at 600 combat sims. Baseline floor-tree:
  **15.6% win / 39.352 floor / 7.031 HP**. Pure future-fight action NN: **6.2% / 31.578 / 2.633**.
  Paired canonical-score delta **-8.711**, SE 1.390; candidate/baseline/tie counts **20/78/30**.
  This is a decisive regression, not a noisy pilot: do not extend the gate or deploy either the action
  model or `VCARD_ACTION_SURVIVAL_W`. The immediate cause is likely data scale: the policy head was
  retrained on only 2k decisions, replacing the proven 21.9k full-run action-value dataset; the
  survival task did not compensate for that lost ranking coverage. Next version must initialize from
  or jointly train with the 21k card model, treating old rows as value-only and new rows as
  value-plus-survival, before another gameplay gate. Artifacts/results:
  `selfplay/card_models/card_cf_future_fight_124k_2k*` and
  `selfplay/gate/future_fight_124k_2k/`.
- **Additive retrain attempted:** `train_card_cf.py` now accepts value-only historic rows plus
  survival-labeled rows, masks the auxiliary loss on old rows, preserves the proven graph-card model's
  scalar normalization, and initializes all shared weights from `card_cf_graph_full21k.pt`. The joint
  23,863-decision / 95,305-action model froze the ranker for three epochs while calibrating only the
  new survival head, then fine-tuned. Its best held-out score was **37.285** versus **37.064** for the
  tree reference (the combined split is not directly comparable to the older 21k split).
- **Fresh fair-play gate:** 128 common seeds 126128--126255 at 600 combat sims: baseline **31.2% /
  40.984 floor / 9.977 HP**; initialized joint candidate **23.4% / 40.109 / 6.953**. Paired
  canonical-score delta **-1.656**, SE 1.259 (candidate/baseline/tie **35/49/44**). It is not a
  decisive 128-seed rejection, but its negative point estimate and failure to meet the required
  +0.5 lower-bound promotion condition mean **do not extend or deploy**. The extra labels alone have
  not yet produced a safe card policy improvement. Results:
  `selfplay/gate/future_fight_joint23k/summary_126128_128.json`.

## 65. Live all-act encounter-distribution card rollout  ➕ promising oracle; collect targets, do not deploy (2026-07-22)
- **Policy/evaluation:** `STS_ACT_FIGHT_PROBE_DRAFT=1` replaces only the *immediate* card/Skip
  selection with simulation. For each offer it samples four possible hidden remaining normal/elite
  encounter queues using the game's weighted pools and their no-repeat constraints, samples the
  current-act boss, then plays every reached combat on the chosen route through that boss. All
  candidate cards share each sampled queue (common random numbers). Map layout and non-combat RNG
  stay fixed; later simulated card choices use the ordinary server policy, so the current pick is
  selected **solely** by simulated combat outcomes, not a learned card scorer.
- **Objective:** each reached fight contributes a floor-distance-weighted, nonlinear post-fight HP
  safety value `sigmoid((HP/maxHP - 0.35)/0.10)`; a reached loss contributes -1. Averaging this over
  sampled queues naturally includes both an encounter's probability of occurring (the branch reaches
  it) and its conditional survival probability. This deliberately avoids hand-authored enemy/card
  tiers and avoids treating HP as linear. `STS_ACT_FIGHT_PROBE_FLOOR_DECAY` defaults to 0.985.
- **Fresh fair-play pilot + confirmation:** at 600 outer combat sims, 40 inner combat sims per
  fight, and four encounter-queue futures per offered action, the first 16 paired seeds
  126400--126415 gave baseline **18.75% win / 34.062 floor** versus rollout **25.00% / 40.812**,
  paired canonical (`floor + 10*win`) delta **+7.375**, SE 4.264. An independent 16 seeds
  126416--126431 gave **0.00% / 28.625** versus **18.75% / 38.625**, delta **+11.875**, SE 4.191.
  Combined 32-seed result: baseline **9.375% / 31.344 floor**, rollout **21.875% / 39.719**;
  paired delta **+9.625**, SE **2.969**, 99% CI **[+1.978, +17.272]**, with rollout/baseline/tie
  counts **19/8/5**. This is a real positive directional result, but not a promotion gate.
- **Cost/decision:** rollout consumed **80--126 CPU-seconds/run** versus **4.5--6.1** for baseline,
  so it is far too expensive to deploy as a default live policy. It is nevertheless the first
  future-fight formulation with a positive held-out signal. The justified next step is to collect
  its per-offer simulated all-act utilities as direct action labels, then train an NN to approximate
  this combat-strength-against-encounter-distribution target; retain the rollout as an offline
  oracle and require a normal large paired gameplay gate before any deployment. Results:
  `selfplay/gate/act_fight_probe_allact_16/` and
  `selfplay/gate/act_fight_probe_allact_confirm16/`.

## 66. Checkpointed combat-strength policy for every out-of-combat decision  ➕ strong pilot; confirm and distil (2026-07-23)
- **What changed:** `STS_ACT_FIGHT_PROBE_ALL_OOC=1` extends the encounter-distribution idea from
  card rewards to every strategic action. The original pilot exercised Act 1 map branches, card rewards, events, shops, rest
  sites, and selection targets. For a candidate action, the evaluator follows one ordinary
  out-of-combat trunk, but at each reached combat checkpoint scores every possible next
  normal/elite/boss encounter independently from the identical pre-combat state. It weights those
  scores by the game's encounter distribution and by distance, and uses the same nonlinear HP
  safety utility as the card-only probe. This is deliberately a *combat-strength profile*, not a
  recursive assertion that a floor-1 choice must already beat the Act boss.
- **Pilot:** 16 paired fair-play Ascension-0 seeds 126700--126715, 600 outer combat simulations,
  600 inner simulations per checkpoint fight, and four sampled remaining-encounter futures. Both
  arms used the deployed stack (card skip -0.5, heuristic pathing, shop-V, win-rate rest, PUCT);
  the candidate additionally enabled the all-OOC checkpoint probe and stopped after the Act-1
  boss. Thus `won` here means **cleared Act 1**, not a full-run win.
- **Result:** baseline cleared **9/16 (56.25%)**, reached mean floor **15.000**, and ended with
  mean HP **22.000**. The checkpoint candidate cleared **16/16 (100.0%)**, reached floor
  **16.000**, and ended with **61.875** HP. The paired Act-1 score `floor + 10*cleared` improved
  by **+5.375**, SE **1.690**, 99% normal CI **[+1.021, +9.729]**; 7 seeds improved, 0 regressed,
  and 9 tied on that intentionally coarse score. The result is driven by rescuing both floor-8
  deaths and five floor-16 deaths, while also producing much safer clears.
- **Cost and interpretation:** this is a strong directional result, not a promotion gate. The
  candidate consumed **6,951.89 CPU-seconds/run** versus **2.13** for baseline (roughly 3,265x),
  and only 16 paired Act-1 seeds were evaluated. It establishes that the proposed question—"how
  will this state perform against the possible upcoming fights?"—can select better live strategic
  actions under a very expensive teacher. It does not establish a full-run win-rate gain or justify
  deploying the literal rollout. Raw results are
  `selfplay/gate/act1_checkpoint_all_ooc_16/{baseline,candidate}.{csv,log}`.
- **Continuation plan:** (1) freeze this exact configuration and run one independent 16-seed
  paired Act-1 confirmation before changing any budget, utility, or policy; inspect per-decision
  traces to verify that every intervention is legal and that map/event/shop/rest actions are all
  actually exercised. (2) Add durable per-action teacher logging: state, legal actions, shared
  future samples, mean/uncertainty of the checkpoint utility, and its encounter/HP components.
  First calibrate a cheaper label setting against the 600-simulation teacher by action-ranking
  agreement, rather than assuming a reduced budget is adequate. (3) Collect action-conditioned
  counterfactual groups for all OOC decision types and train a distilled fight-strength/ranking
  model; action representations must cover cards/skip, map children, discrete event/rest choices,
  selection targets, and shop bundles. (4) Serve that model as an opt-in policy, verify
  Python/native parity and latency, then run the ordinary adaptive paired **full-run** fair-play
  gate. Only that final gate can decide promotion. Keep the direct checkpoint evaluator as the
  offline oracle and calibration target throughout.

### 66a. Known-boss correction and teacher traces (2026-07-23)
- The original pilot incorrectly treated the Act-1 boss as hidden: its counterfactual sampler
  replaced `gc.boss`, and its boss checkpoint averaged Guardian, Hexaghost, and Slime Boss. The
  boss is fixed at act generation and visible to the player, so the oracle now preserves the known
  boss and evaluates only that encounter with probability 1. The original 16-seed result remains a
  useful directional pilot, but is not a confirmation of the information-correct oracle.
- `STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv` now emits durable, append-only per-action rows:
  rich state features, all legal actions, known boss, the common future seeds, per-future utility,
  mean/sample-SD/SE, and each probability-weighted encounter/HP safety contribution. This should
  be enabled for the corrected calibration and confirmation runs.
- `STS_ACT_FIGHT_PROBE_MAX_CHECKPOINTS=N` supplies a local combat-strength horizon by scoring the
  next `N` reached combat checkpoints (rather than a variable number of map nodes); after the
  final scored checkpoint it does not pay for an unnecessary trunk fight. The 4-vs-2 future runtime
  calibration uses `N=3` before changing the combat-search budget.
- `STS_ACT_FIGHT_PROBE_PARALLEL=1` parallelizes the independent candidate-action × sampled-future
  branches within one OOC decision. With `bestbench ... 1 ...` it bypasses the otherwise empty outer
  OpenMP seed team, so `OMP_NUM_THREADS=8` genuinely supplies up to eight branch workers for one
  seed. It is intentionally disabled when dynamic potion saving or ordered tracing is enabled.
- `STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=400,200,100` optionally gives the first, second, and third
  reached checkpoint separate inner-combat base budgets. It applies to both each possible-encounter
  evaluation and the corresponding trunk fight; the live run remains at its ordinary outer budget.

### 66b. Three-checkpoint runtime calibration: four versus two futures (2026-07-23)
- **Setup:** corrected known-boss oracle; one fair-play A0 seed (126700); 600 live and inner combat
  simulations; three reached combat checkpoints; deployed skip/shop/rest/PUCT/V-combat stack; and
  `STS_ACT_FIGHT_PROBE_PARALLEL=1`, `OMP_NUM_THREADS=8`. The only changed setting was sampled
  encounter futures: 4 versus 2. Raw logs and durable teacher rows are in
  `selfplay/gate/act1_checkpoint_knownboss_runtime/`.
- **Runtime:** 4 futures took **418.77 wall-seconds**, **2,689.51 CPU-seconds** (mean active use
  ~6.4 cores); 2 futures took **274.10 wall-seconds**, **1,241.73 CPU-seconds** (mean ~4.5 cores).
  Thus 2 futures cut CPU by **53.8%** and wall time by **34.5%** (**1.53×** wall-time speedup). The
  weaker wall-time gain is expected: with only two futures, many two-action decisions expose fewer
  than eight independent branches and cannot fill all eight workers.
- **Scope:** both cleared Act 1, but ended at 65 HP (4 futures) and 90 HP (2 futures). One seed and
  different selected trajectories do **not** establish that two futures preserve teacher quality.
  Next use the teacher rows to measure chosen-action agreement and ranking regret against the
  4-future oracle before selecting the cheaper setting for a paired confirmation.

### 66c. Decreasing inner combat budgets across three checkpoints (2026-07-23)
- **Setup:** same corrected one-seed runtime setup as 66b, retaining **four** encounter futures,
  three checkpoints, 600-sim live combats, and eight-worker branch parallelism. Only the inner
  checkpoint schedule changed from uniform 600 to `STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=400,200,100`.
- **Runtime:** the decreasing schedule took **171.01 wall-seconds** and **1,083.21 CPU-seconds**,
  versus 418.77 wall-seconds / 2,689.51 CPU-seconds for uniform-600 four-future evaluation. That is
  a **59.2% wall-time reduction** (**2.45×** speedup) and **59.7% CPU reduction**. It cleared Act 1
  with 43 HP (uniform-600 cleared with 65 HP).
- **Scope:** retain four futures as chosen, but do not treat this single-seed trajectory as evidence
  that the decreasing schedule is an adequate teacher. Use the durable rows to compare action
  agreement/ranking regret to uniform 600 before adopting it for the paired confirmation.

### 66d. Direct learned combat transitions (2026-07-23)
- **Implementation:** `STS_ACT_FIGHT_PROBE_PREDICT=1` loads the existing entity combat model
  (`selfplay/models/v_combat_entity_iter34.txt`), which was trained from the combat buffer and has
  separate heads for `P(win)` and `E[end HP / max HP | win]`. At each checkpoint it now scores every
  possible enemy as `P(win) * HP-safety + (1-P(win)) * -1`, rather than playing a 400/200/100-sim
  MCTS fight. To reach checkpoints two and three, the sampled trunk applies the model's predicted
  win/loss (default threshold 0.5); on a predicted win it installs the predicted HP and calls the
  normal victory exit path, so Burning Blood and ordinary reward setup still occur. `sims=0` in the
  durable component trace explicitly denotes a model prediction, not a zero-budget combat search.
- **Runtime smoke:** on the same corrected fair-play A0 seed **126700**, four futures, three reached
  checkpoints, 600-sim live combat, eight-worker branch mode, and the 400/200/100 setting, the
  direct-transition run cleared Act 1 with 26 HP in **3.16 wall-seconds** (**2.81 CPU-seconds**).
  This is a **54.1x wall-time speedup** over 171.01 seconds for searched 400/200/100 checkpoints
  (and 132.5x over the 600/600/600 four-future runtime). Native inference was separately checked
  against 200 Python validation rows: max scalar difference 0.000023. Raw artifacts:
  `selfplay/gate/act1_checkpoint_knownboss_runtime/predict_entity_400_200_100.{log,time,teacher.csv}`.
- **Boundary:** this is a fast *approximate* transition, not yet a replacement teacher. It does not
  simulate card plays, potion use, combat RNG, transient relic/card counters, or exact rewards; the
  virtual victory preserves potions and uses the battle-start RNG state. The single successful
  trajectory proves integration and latency only. Before any policy-quality claim, compare action
  rankings/regret from these rows against the searched oracle on identical decision states, then run
  a held-out paired Act-1 gate if that agreement is acceptable.

### 66e. Full-run 16-seed smoke: **invalid pending reproducibility repair** (2026-07-23)
- The full-run smoke did execute real 600-simulation combats and did not accidentally stop after Act
  1: its candidate rows reach floors 20--50. Both arms nevertheless recorded **0/16** full clears.
  That outcome is plausible at this budget: the closest fair-play 600-simulation controls are
  12.5% (16 seeds 126500--126515), 15.6% (128 seeds 126000--126127), and 17.6% (500 seeds
  65000--65499) full-run win rate, for which an all-loss 16-seed block has roughly 12%, 6.6%, and
  4.5% probability respectively. It is not evidence of a hidden Act-1 stop.
- **Do not use the reported paired effect.** Repeating the candidate under the nominally same
  fair-play settings changes outcomes: parallel runs disagreed on seeds 126700 and 126704, and two
  serial one-seed replays of 126700 ended on floors 50 and 42. The serial 16-seed pass likewise gave
  baseline/candidate mean floors 17.0/29.4, not the parallel 16.75/31.0. Thus the prior apparent
  `+14.25`-floor result cannot yet be treated as a valid paired estimate.
- **Next requirement:** find and remove the remaining run-level nondeterminism (then require exact
  repeated per-seed CSV equality) before evaluating teacher agreement or running another gate. Raw
  forensic artifacts remain in `selfplay/gate/act1_predict_transition_fullrun16/`.

### 66f. All-act OOC scope and baseline boss-relic policy (implementation; pending reproducible gate) (2026-07-23)
- `STS_ACT_FIGHT_PROBE_ALL_OOC=1` now applies during **Acts 1--3**, rather than only Act 1. A
  boss-relic screen is an ordinary legal OOC action set: each relic is applied on a copied state,
  transition into the next act is performed normally, and that resulting state is scored at its
  next capped combat checkpoints. The current act's boss remains fixed/known throughout.
- The ordinary baseline already makes boss-relic decisions, but with the built-in
  `Expert::getBossRelicOrdering` table. It only switches those picks to V_win when
  `STS_BOSS_RELIC=1`; this was **not** enabled in the standard fair 600-simulation baseline. Thus
  the all-OOC candidate and baseline both choose a relic, but optimize it by different rules.
- Reproducibility audit: fully resetting `BattleContext`'s nested state at `init()` removed the
  baseline's repeated-seed divergence (seed 126700: three identical one-core replays all died on
  floor 8). The predictor/all-OOC path still has a separate first-run discrepancy, so no new
  all-act/full-run gate has been started; this entry records implementation scope, not a quality
  result.

### 66g. Serverless out-of-combat GBM evaluator (2026-07-23)
- **Implementation:** exported the deployed floor model `build/v_rich_xgb.json` to the native tree
  format `build/v_rich_trees.txt`. With `STS_NATIVE_OOC=1` (now the default), card rewards, shop
  bundles/removal, raw floor values, and win-rate rest/upgrade choices are evaluated in-process.
  The existing native `v_win_trees.txt` evaluator supplies the P(win) path. Set
  `STS_NATIVE_OOC=0` only for an explicit legacy `v_server.py` comparison.
- **Server scope:** the server was only an inference bridge. It served the floor GBM, win GBM, and
  optional neural/paired experimental endpoints; it was not needed for combat search or the entity
  checkpoint predictor. The native baseline replaces the GBM endpoints. Optional `STS_CARD_NN`,
  `STS_CARD_ACTION`, graph/path-action, and paired-rest experiments still require their respective
  server models.
- **Verification:** two independent no-server runs of seed 126700 under the four-future,
  three-checkpoint, direct-transition setup produced identical results: **1/1 win, floor 51,
  90 HP**, at about 15.3 CPU-seconds each. This also removes the previous cold-start race in which
  the first run began before the Python server had loaded its models and silently skipped cards or
  left shops empty.

### 66h. Native versus legacy server-backed evaluator, 64 paired seeds (2026-07-23)
- **Setup:** identical fair-play A0 configuration, 600 live combat simulations, four encounter
  futures, three checkpoint cap, direct entity combat transitions, PUCT/V-combat, seeds
  **126700--126763**, and eight outer workers. The only arm difference was OOC inference:
  `STS_NATIVE_OOC=0` with `v_server.py` versus the default native floor/win GBMs.
- **Results:** legacy server arm won **3/64 (4.7%)**, mean floor **32.03**, mean end HP **1.89**;
  native arm won **5/64 (7.8%)**, mean floor **32.55**, mean end HP **2.55**. Paired native-minus-
  server deltas were **+0.52 floors**, **+0.66 HP**, and **+2 wins**. The paired gate score
  (floor + 10×win) was **+0.83**, SE **1.13**, 95% CI **[-1.39,+3.04]**: no statistically reliable
  quality difference at 64 seeds.
- **Runtime (historical report):** server arm consumed **983.6 wall-seconds** (**380.6 reported process CPU-seconds**; the CSV's
  per-seed elapsed-time sum is 6471 seconds); native arm took **98.8 wall-seconds** (**722.6 process
  CPU-seconds**; CSV sum 738 seconds). Thus native was approximately **10.0× faster wall time**;
  the server arm's wall time includes Python socket/model overhead and did not scale efficiently
  across the eight workers. Per-seed elapsed times are not additive CPU measurements.
- **Conclusion:** native inference is the recommended baseline: it matches the legacy policy within
  this noisy 64-seed gate while eliminating the server dependency and cold-start failure mode. The
  comparison artifacts are in `selfplay/gate/native_vs_server_64/`.
- **Correction:** this 66h quality/runtime comparison is **invalid**. The first native implementation
  omitted the server's zero-signal upgrade-target fallback, so it was not policy-equivalent. A
  corrected one-seed check now matches the server exactly (seed 126700: floor 33). Do not use the
  earlier 64-seed deltas or 10x runtime claim as evidence.

### 66i. Primary recorded fair reference, 1,000 sims × 128 seeds (2026-07-23; historical)
- **Setup:** standard full-run stack with fair play, native in-process floor/win GBMs, PUCT/V-combat,
  no all-OOC checkpoint oracle, 1,000 live combat simulations, A0, seeds **126700--126827**, and
  eight outer workers.
- **Result (primary fair-play benchmark):** **39/128 wins (30.5%)**, mean floor **40.32**, mean end HP **11.91**. Runtime was
  **176.0 wall-seconds / 1,325.3 summed per-run elapsed-seconds**. Raw output is in
  `selfplay/gate/baseline_1000_128/`.
- This is the primary recorded fair-play score on the fixed 128-seed benchmark. Its cited raw
  directory is absent and the exact artifact/flag set is incomplete, so it is not exactly
  reproducible from the current checkout. It must not be
  compared directly with the historical 51.6%/1,000-sim known-RNG score: fair play re-randomizes
  hidden information during search, while known-RNG simulations can peek at future draws. The
  known-RNG number remains a diagnostic only; fair-play is the primary quality benchmark.

### 66j. Future-count / checkpoint-horizon sweep at 1,000 fair-play sims (2026-07-23)
- **Question:** does the all-OOC combat-strength evaluator improve full-run performance, and how
  many sampled futures and next combat checkpoints are useful? The candidate used the native floor/
  win GBMs, `STS_ACT_FIGHT_PROBE_ALL_OOC=1`, the entity combat predictor
  (`STS_ACT_FIGHT_PROBE_PREDICT=1`), and every legal Act 1--3 OOC action was scored. This is the
  fast predicted-transition evaluator, not the expensive searched checkpoint teacher.
- **Setup:** Ascension 0, fair-play, 1,000 live combat sims, common seed block 126700--126731,
  and futures × next-combats in `{1,2,4} × {1,2,3}`. A fresh baseline on the same block was
  **7/32 wins (21.9%)**, mean floor **37.31**, mean end HP **8.03**.

  | futures | next combats | wins | avg floor | avg end HP | paired score delta* |
  |---:|---:|---:|---:|---:|---:|
  | 1 | 1 | 1/32 (3.1%) | 29.41 | 1.34 | −9.78 |
  | 1 | 2 | 2/32 (6.2%) | 32.03 | 2.97 | −6.84 |
  | 1 | 3 | 2/32 (6.2%) | 31.25 | 2.75 | −7.62 |
  | 2 | 1 | 1/32 (3.1%) | 30.38 | 0.28 | −8.81 |
  | 2 | 2 | 2/32 (6.2%) | 30.91 | 1.81 | −7.97 |
  | 2 | 3 | 1/32 (3.1%) | **32.84** | 0.25 | **−6.34** |
  | 4 | 1 | 1/32 (3.1%) | 30.47 | 1.25 | −8.72 |
  | 4 | 2 | 2/32 (6.2%) | 30.41 | **3.25** | −8.47 |
  | 4 | 3 | 1/32 (3.1%) | 32.75 | 1.06 | −6.44 |

  *Paired score is `floor + 10×win`; deltas are candidate minus the fresh baseline per seed.
- **Verdict:** no performance gain appeared. The best depth point, 2 futures × 3 combats, was
  **−4.47 floors** and **−6.34 score units** paired against baseline, with 1 versus 7 wins.
  More futures did not improve the result, and longer horizons only partially recovered the damage.
  The current predicted-transition evaluator is therefore not deployable as an OOC policy. The
  likely issue is model/transition error compounding across counterfactual OOC trunks; the entity
  predictor does not model combat card/potion use or exact post-combat state transitions.
- **Reproducibility note:** the earlier stored 32-seed subset of the 128-seed baseline was 6/32,
  floor 39.59, while the fresh replay was 7/32, floor 37.31. This fair-play multi-thread run is
  not bit-identical across separate 8-thread invocations, so the table is directional; future
  gates should use repeated fixed-thread runs or single-thread paired evaluation.

### 66k. Direct next-combat OOC action labels and first NN (2026-07-24)
- **Collector:** added `oocnextgen`. It samples one genuine OOC decision from each baseline run,
  enumerates **all legal actions**, continues each branch only to its next battle, and records both
  the concrete baseline-combat result and the weighted result of searching every possible encounter
  at that checkpoint. This removes the multi-checkpoint predicted-transition approximation.
- **Dataset:** 2,000 seed-held-out decision groups and **10,564 action rows** across map, rewards,
  shop, rest, event, and selection screens. Mean group size was 5.31 actions. The concrete and
  all-encounter labels selected the same best action on **65.1%** of groups, giving an empirical
  upper-bound/noise reference for the target.
- **First model:** a raw rich-state/action MLP (`train_ooc_next_action.py`), 80/20 split by whole
  decision group. Held-out results on 400 groups: win Brier **0.0716**, win accuracy **90.9%**,
  HP-fraction MAE **0.211**, exact teacher-best action **29.5%**, and best-or-tied **42.8%**.
- **Verdict:** ✅ collector and labels are working; ❌ this first NN is not useful yet. Its action
  ranking is far below the 65.1% concrete-vs-encounter agreement ceiling. The next model should
  reuse/pretrain the large OOC state encoder and use structured action encodings (screen/action
  type, card identity, map child, shop bundle, event/selection target), rather than treating the
  raw 32-bit `GameAction` encoding as a universal action representation. Artifacts:
  `selfplay/ooc_buffer/next_combat_2000.csv` and `selfplay/models/ooc_next_action_2000*`.

### 66l. One-step NN evaluated against multi-checkpoint teacher (2026-07-24)
- **Question:** does a one-next-combat action model transfer to the desired multi-combat utility,
  or is a separate three-checkpoint target required? Reused the existing corrected **four-future,
  three-checkpoint** teacher trace (`futures4_teacher.csv`); no new rollout data was collected.
- **Result:** on 60 teacher decision groups / 201 legal-action rows, the NN score had Spearman
  correlation **0.636** and Pearson correlation **0.513** with the teacher's three-checkpoint
  utility. It selected the exact teacher-best action **56.7%** of the time and a best-or-tied action
  **70.0%** of the time; mean teacher regret was **0.093** utility units.
- **Interpretation:** one-step supervision does transfer to multi-checkpoint action ranking
  reasonably well. This supports directly wiring the NN into the three-checkpoint OOC benchmark;
  a new three-step training dataset is not required merely to test the idea. The result is an
  offline trace check only—the trace has one seed and is not a 64-seed gameplay gate.

### 66m. Repeated next-combat action NN benchmark (2026-07-24)
- **Setup:** paired fair-play A0 runs, 1,000 combat sims, 64 common seeds **126900--126963**.
  The action NN was queried in one batch for every legal OOC action and reapplied at every later
  OOC decision. The run was launched with the requested `futures=4` and `max-checkpoints=3`
  settings; those rollout knobs are metadata here because this deployed NN directly predicts the
  next combat rather than running the old checkpoint oracle.
- **Result:** baseline **14/64 wins (21.9%)**, mean floor **37.05**, mean end HP **7.53**;
  repeated-NN candidate **0/64 wins (0.0%)**, mean floor **19.53**, mean end HP **0.00**.
  Paired candidate-minus-baseline deltas were **−17.52 floors** and **−19.70** on `floor+10×win`;
  the candidate was better on 5 seeds, tied on 1, and worse on 58.
- **Verdict:** ❌ the first action NN does not transfer as a whole-run repeated OOC policy, despite
  its useful offline correlation with the three-checkpoint teacher. This is a deployment-level
  failure, not evidence that four futures or three checkpoints help: greedy next-combat action
  selection compounds errors across drafting, shop, rest, event, and map decisions. Keep the model
  as an offline ranker/diagnostic and do not promote it to the live OOC policy without structured
  action features, calibration, and a conservative gate against the existing policy.
- **Artifacts:** `selfplay/gate/ooc_action_nn_64_f4_c3/{baseline,candidate}.csv`.

### 66n. Server-path sanity check for 66m (2026-07-24)
- The OOC server was live and loaded `selfplay/models/ooc_next_action_2000`; a direct `OA` request
  returned one prediction per submitted action. With the server intentionally unavailable, the NN
  policy fell back to the ordinary baseline path: seed 126900 at 300 sims reached floor **50**.
  With the live OA endpoint, the same seed/budget reached floor **16**. Therefore the 0/64 result in
  66m is caused by the NN's selected actions, not a dead server or silent fallback.
- The earlier **32.75-floor** 4-future/3-checkpoint point in 66j is not the same policy: it used the
  native entity combat predictor inside the old checkpointed all-OOC rollout evaluator over the
  32-seed sweep. It did not use the new action NN or the OA server, and its score was already below
  the 37.31-floor baseline on that block.

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
  per-screen knobs in `apps/one_combat.cpp`; decision log
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

- **Goal** (§81 follow-up 3, decision-log follow-up 1): the 256-seed secondary
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

## §117 Searcher2 rollout-usage diagnostic (searchdiag): first full measurement - known-RNG hallway fights become near-explicit at 30k sims; boss fights stay rollout-dominant in both regimes (2026-08-06, local WSL)

- **What:** diagnostic-only measurement (no policy change, no win-rate claims) of
  how much of each combat the default Searcher2 arm handles via explicit tree
  descent vs random rollout, plus frontier terminality and root-decision
  stability vs budget. New `searchdiag` mode + write-only searcher counters
  (decision log `2026-08-06-searchdiag-rollout-usage.md`; `combat-search.md`
  "rollout-usage diagnostics").
- **Config:** commit `4325c03` + uncommitted searchdiag diff; WSL build;
  `one_combat searchdiag <nSeeds> 1000 0 <out> 2 <seedOff>`; Searcher2; asc 0;
  8 threads; native OOC; policy PUCT on (`build/policy_trees_c.txt`); no
  combat value/PVNet; `STS_ROLLOUT_DEPTH` unset (rollouts play to battle end).
  Fair arm: `STS_FAIR=1`, seeds 0-5. Known-RNG arm: seeds 10,11,13,14,16,17,18,19
  (seed 12 excluded: pre-existing empty-hand EXHAUST_MANY assert, see below).
  Budget-sweep probes {100..30k} on fresh searchers every 2nd decision;
  agent decisions at 1000 sims. **Fair arm is Searcher2 fair, not the
  recommended S3 particle stack** - results are regime-scoped, not comparable
  to gate numbers.
- **Rollout-call fraction by room x budget** (probe rows; n per cell in
  parentheses): fair MONSTER 0.71/0.70/0.69/0.68/0.66/0.64/0.62; fair ELITE
  0.83/0.81/0.80/0.79/0.77/0.74/0.72; fair BOSS 0.92/0.91/0.90/0.90/0.89/0.87/0.86.
  known-RNG MONSTER 0.48/0.45/0.43/0.40/0.33/0.27/0.19; ELITE
  0.71/0.68/0.64/0.58/0.46/0.31/0.18; BOSS 0.91/0.89/0.87/0.84/0.78/0.68/0.55.
  Known-RNG hallway fights become ~80% explicit at 30k sims; bosses stay
  rollout-heavy in both regimes (fair 86%, known-RNG 55% at 30k).
- **Visit-weighted terminal coverage by act x budget:** fair act1
  0.45/0.47/0.50/0.53/0.59/0.64/0.69, act2 0.29/0.32/0.34/0.37/0.43/0.49/0.57,
  act3 0.26/0.28/0.30/0.33/0.38/0.44/0.50; known-RNG act1
  0.51/0.53/0.55/0.57/0.64/0.74/0.85, act2 0.46/0.50/0.55/0.60/0.68/0.76/0.84,
  act3 0.25/0.25/0.27/0.32/0.41/0.53/0.66. Even at 30k sims the MCTS-preferred
  portion of the tree is not fully terminal (fair act3 0.50) - rollouts still
  value most search mass.
- **Agent decisions at 1000 sims (A rows, per room):** fair MONSTER/ELITE/BOSS
  rollFrac 0.69/0.80/0.89, avgRolloutLen 7.4/8.7/12.6, maxTreeDepth
  8.9/8.6/9.6, vtc 0.53/0.32/0.22; known-RNG MONSTER/ELITE/BOSS rollFrac
  0.74/0.76/0.78, avgRolloutLen 12.6/11.6/12.7, maxTreeDepth 11.8/10.3/12.4,
  vtc 0.30/0.27/0.24.
- **Structural finding (regime cost):** fair mode commits one action per
  search, so ~123 decisions/fight vs ~2/fight known-RNG (line replay), i.e.
  ~40x more searches per fight and ~40x more probe cost per seed.
- **NN-leaf relevance:** the data supports the hypothesis that a leaf
  evaluator pays off mostly on boss/long fights (rollout fraction 0.78-0.89,
  avg rollout 12-13 actions, vtc <= 0.24), not on known-RNG hallway fights at
  deep budgets (19% rollout, vtc 0.85). Conditioning NN blending on measured
  rollout length/coverage rather than raw depth is feasible with this schema.
- **By-act view** (`build/sdiag_by_act.csv`, script `build/sdiag_by_act.py`;
  means per regime x act x budget, n per cell): for known-RNG, **act 3 is the
  rollout-heavy zone regardless of room** - rollout fraction at 30k sims: act1
  0.20, act2 0.19, act3 0.39; by room @30k: act1 MONSTER 0.09 / act2 MONSTER
  0.07 / act3 MONSTER 0.37, bosses 0.39-0.67. For fair, room dominates act:
  MONSTER 0.47-0.74, ELITE 0.67-0.79, BOSS 0.83-0.89 at 30k across all acts.
  maxTreeDepth @30k: KR act3 15.7 vs act1 13.6; fair ~12 flat. valueGap (KR)
  grows to 970-1716 HP at 30k vs fair 268-353 - known-RNG root decisions
  become far more conclusive; fair stays tight. stableVsPrev @30k: fair
  0.87-0.95, KR 0.88-1.00.
- **Pre-existing crash re-confirmed:** known-RNG Searcher2 aborts at
  CARD_SELECT EXHAUST_MANY with empty hand (act-1 floor 13 Gremlin Nob, and
  floor 21 Shelled Parasite for seed 12 at 1k sims); fair path unaffected.
  Coverage of the known-RNG arm is therefore seed-restricted.
- **Artifacts:** `build/sdiag_fair.csv(.fights.csv)`, `build/sdiag_kr_arm/s*.csv(.fights.csv)`,
  `build/sdiag_grouped.csv` (grouped means by regime x room x act x deck x
  legal-action bucket x turn x budget), `build/sdiag_by_act.csv`,
  `build/sdiag_by_encounter.csv`,
  `build/sdiag_group.py`, `build/sdiag_by_act.py`, `build/sdiag_by_encounter.py`
  (grouping scripts).
  Cost: fair arm 283s wall (6 seeds); known-RNG ~1 min/seed.

## §118 Root-stability adaptive search (STS_CONV_ROOT) paired gate: candidate point (MIN=500/PATIENCE=500) FALSIFIED — win below flat at 256 paired seeds; adaptive line stopped, defaults stay env-only (2026-08-06, local + GCP)

- **What:** paired benchmark of the §117-era adaptive-budget arm:
  `BattleScumSearcher2::searchToTotalRootStable` (chunked search, root-action
  stability stop) with the budget-neutral per-fight `fightPool` reinvestment
  and the `onlyLegalAction` forced-move shortcut, vs the flat fixed-budget
  arm. Provisional 64-seed local signal was +3.1pp at −9% cpu for
  MIN=500/PATIENCE=500 (plan `plan-searchdiag-adaptive-continuation.md`,
  decision log `2026-08-06-conv-root-stable-search.md`); this entry is the
  required confirmation run and the arbiter verdict.
- **Config (both arms):** commit `99d55dd`; `one_combat bestbench 1000 256 0 0
  <out.csv>`; Searcher2 fair (`STS_FAIR=1`), asc 0, native OOC, policy PUCT on
  (`build/policy_trees_c.txt`), no combat value/PVNet
  (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`). Candidate
  arm adds `STS_CONV_ROOT=1 STS_CONV_ROOT_MIN=500 STS_CONV_ROOT_PATIENCE=500`
  (other knobs default: START=250, GROW=2.0, CHECK=100, SHARE=0.05, VALUE=1.0,
  MAX_FRAC=3.0). Metric formula = producer `bestbench` summary line
  (win% = wins/seeds, avg_floor, avg_hp_end, cpu_sec/run); paired flip counts
  from per-seed `won` columns.
- **128-seed local confirmation (T2, this machine, 12 threads):** flat
  **21.9% / 28 wins** / floor 36.0 / hp 13.1 / cpu 6.66 s·run vs candidate
  **21.1% / 27 wins** / floor 36.3 / hp 10.9 / cpu 6.15 (−7.7%); flips 8 up /
  9 down / 111 same. Delta −0.8pp, within noise → proceeded to the gate per
  plan decision rule (only a >5pp loss would stop at T2).
- **256-seed GCP gate (T3, sts-test, 24 threads):** flat **22.3% / 57 wins** /
  floor 36.0 / hp 12.6 / cpu 8.98 s·run (wall 102 s) vs candidate **19.9% /
  51 wins** / floor 36.1 / hp 10.7 / cpu 7.96 (−11%, wall 90 s). Paired:
  **224 same, 13 candidate-better, 19 flat-better** → delta −6 wins
  (−2.3pp), McNemar-style SE 2.07pp, 95% CI −2.3 ± 4.1pp.
- **Verdict:** ❌ **falsified.** Win < flat with a CI that does not exclude a
  meaningful loss (plan T3 rule: promote only if win ≥ flat with CI excluding
  a meaningful loss AND cpu ≤ flat). The cpu saving (−11%) is real and
  directionally reproducible (T2 −7.7%, T3 −11%, 64-seed −9%), but the 64-seed
  +3.1pp win signal did not survive: 128-seed −0.8pp, gate −2.3pp with 13/19
  flip split. The adaptive line is **stopped**: no default change
  (`g_convRootMinSims`/`g_convRootPatience` stay env-gated opt-in with
  conservative 250 defaults), no promotion to a recorded operating point,
  no baseline-table update. Phase 2 (context-adaptive rollout caps) remains
  parked per plan T6.
- **Artifacts:** per-seed CSVs
  `build/conv_flat_128.csv`, `build/conv_root_128.csv` (local),
  `build/conv_flat_256.csv`, `build/conv_root_256.csv` (copied back from GCP
  `/home/philippherrmann/sts_sweep/build/`); logs `build/conv_{flat,root}_{128,256}.log`.
  Server-side sources synced from local (rsync-copy tree, no commit).
- **Cost:** T2 ~2.5 min/arm wall local; T3 ~100 s/arm wall on GCP.

## §119 Phase 2 (context-adaptive rollout caps, STS_ROLLOUT_CAPS) paired gate: FALSIFIED — caps cut rollout length 18% but lose 5.9pp win; heuristic capped-leaf estimates are net-negative (2026-08-06, local + GCP)

- **What:** paired benchmark of Phase 2 of the adaptive-budget program: replace
  the flat rollout budget (unlimited, `g_maxRolloutDepth=0`) with per-context
  caps — boss encounters, turn 0, and act 2-3 (floors 17..50) capped at 8
  rollout actions each; short late-fight states (monsters alive <= 1) stay
  uncapped so decisive rollouts play to terminal. Leaf evaluation stays the
  heuristic `evaluateLeafState` (combat VNet rejected at the gates, §97).
  Env-gated opt-in: `STS_ROLLOUT_CAPS=1` + `STS_ROLLOUT_CAPS_{BOSS,TURN0,
  ACT23,LATE_ALIVE}` (defaults 8/8/8/1), parsed in `apps/one_combat.cpp::main`
  next to `STS_ROLLOUT_DEPTH`; `rolloutCapForContext` +
  `BattleScumSearcher2::playoutRandom` in
  `src/sim/search/BattleScumSearcher2.cpp`.
- **Before/after searchdiag measurement (fair @3k, 6 seeds 0-5, 24 threads,
  GCP sts-test, per plan T6):** flat baseline `build/sdiag_fair3k_flat.csv`:
  avgRolloutLen 8.76, rolloutDepthCapped 0, rollFrac 0.75, per-room len
  MONSTER 7.1 / ELITE 9.0 / BOSS 12.4, per-act len 7.6/9.5/9.3. Caps arm
  `build/sdiag_fair3k_caps.csv`: avgRolloutLen **7.15 (−18%)**, capped share
  of rollout calls **0.27** (BOSS 0.38, act2 0.33, act3 0.38, act1 0.12),
  rollFrac unchanged 0.75. Late-fight uncapping works: short monster fights
  keep short rollouts.
- **256-seed paired gate (T6 gate, GCP sts-test, 24 threads, same protocol as
  §118):** flat **22.3% / 57 wins** / floor 36.0 / hp 12.6 / cpu 8.64 s·run
  (wall 98 s) vs caps **16.4% / 42 wins** / floor 35.5 / hp 9.6 / cpu 7.97
  (−7.8%, wall 89 s). Paired: **215 same, 13 caps-better, 28 flat-better** →
  delta **−5.9pp (SE 2.3pp, 95% CI −5.9 ± 4.5pp, excludes zero)**.
- **Verdict:** ❌ **falsified.** The caps arm is net-negative with CI
  excluding zero on win rate (−5.9pp) and materially worse on hp (−3.0) and
  floor (−0.5). The ~18% rollout-length cut (and −7.8% cpu) does not pay: the
  heuristic capped-leaf estimate at depth 8 loses more decision quality than
  the saved sims gain, in both long (boss/act 2-3) and short contexts. The
  Phase 2 line is **stopped**: `STS_ROLLOUT_CAPS` stays env-gated opt-in with
  defaults off (no behavior change when unset — verified structurally: the
  context helper returns the flat `g_maxRolloutDepth` path), no promotion, no
  baseline-table update. Phase 3 (policy-guided rollouts) remains parked with
  the other phases (plan §5); the adaptive-budget program's remaining parked
  phases are unaffected by this gate.
- **Artifacts:** per-seed CSVs `build/rlc_flat_256.csv`, `build/rlc_caps_256.csv`
  (copied back from GCP `/home/philippherrmann/sts_sweep/build/`), searchdiag
  CSVs `build/sdiag_fair3k_flat.csv`, `build/sdiag_fair3k_caps.csv` (+
  `.fights.csv`), logs `build/rlc_{flat,caps}_256.log`,
  `build/sdiag_fair3k_{flat,caps}.log`. Code: `rolloutCapForContext` in
  `src/sim/search/BattleScumSearcher2.cpp`, env block in
  `apps/one_combat.cpp::main`.
- **Cost:** ~100 s/arm wall on GCP for the gate; 134-150 s per searchdiag arm.

## §120 Phase 5 (forced-action contraction, STS_FORCED_MOVE) paired gate: decision-neutral, −16% cpu — exact outcome equality on 256 paired seeds; promotion candidate (2026-08-06, GCP)

- **What:** paired benchmark of Phase 5 of the adaptive-budget program: the
  strictly-forced-only contraction — when the live root state has exactly ONE
  legal action (canonical enumeration, `BattleScumSearcher2::onlyLegalAction`),
  commit it directly without searching, instead of spending the flat sim
  budget on a single-edge tree. Narrower than Searcher3's deterministic chain
  compression, which was net-negative (§106). The shortcut previously existed
  only inside the falsified `STS_CONV_ROOT` arm (§118), confounded with the
  root-stability stop; Phase 5 isolates it behind its own env gate
  `STS_FORCED_MOVE=1` (default off), wired in both
  `ScumSearchAgent2::playoutBattleFair` and `playoutBattle` (fair path: fresh
  searcher, skip + takeAction; non-fair path: skip + takeAction + advanceRoot
  to keep the reused subtree).
- **Config (both arms):** commit `99d55dd` + this diff; `one_combat bestbench
  1000 256 0 0 <out.csv>`; Searcher2 fair (`STS_FAIR=1`), asc 0, 24 threads,
  GCP sts-test, native OOC, policy PUCT on (`build/policy_trees_c.txt`), no
  combat value/PVNet (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`).
  Arm 2 adds `STS_FORCED_MOVE=1`.
- **Result (256 paired seeds @1k fair):** flat **22.3% / 57 wins** / floor
  36.0 / hp 12.6 / cpu 8.96 s·run (wall 102.6 s) vs forced **22.3% / 57 wins**
  / floor 36.0 / hp 12.6 / cpu 7.54 (−15.9%, wall 86.6 s). **Per-seed outcome
  equality: 0/256 seeds differ** on won, floor, act, hpEnd, fightsLost,
  deathCombat, or deathEncounter (`build/fm_flat_256.csv` vs
  `build/fm_forced_256.csv`; total sec 2295.0 → 1929.7).
- **Interpretation:** decision-neutral by construction (a single legal action
  is forced in every determinization), verified at 256 seeds with exact
  outcome equality; the cpu saving is real and large (forced moves skip the
  whole search). This also **reinterprets §118**: the STS_CONV_ROOT arm's
  −2.3pp is attributable to the root-stability stop / pool escalation, not to
  the forced-move shortcut, which this gate shows is neutral-or-better.
- **Verdict:** ✅ **promotion candidate — decision-neutral at −16% cpu.**
  Not a win-rate change (none is expected or observed); it is a free cost
  reduction with provably identical outcomes. Promotion rule per plan T5:
  env-only until two independent gates agree; the second gate should re-run
  this pair (any seed count) and also exercise the non-fair path
  (known-RNG bestbench seeds 10,11,13,14,16,17,18,19 — the fair gate covers
  only the fair path; the non-fair `advanceRoot` variant is wired but
  untested at scale).
- **Artifacts:** per-seed CSVs `build/fm_flat_256.csv`, `build/fm_forced_256.csv`
  (copied back from GCP `/home/philippherrmann/sts_sweep/build/`); logs
  `build/fm_{flat,forced}_256.log`. Code: `onlyLegalAction` +
  `g_forcedMoveSkip` (`include/sim/search/BattleScumSearcher2.h`,
  `src/sim/search/BattleScumSearcher2.cpp`), agent wiring
  (`src/sim/search/ScumSearchAgent2.cpp`), env
  (`apps/one_combat.cpp::main`).
- **Cost:** ~90-100 s/arm wall on GCP.

## §121 Phase 5 forced-action contraction: confirmation gate + non-fair scoping + hang fix — default flipped to ON (2026-08-06, local + GCP)

- **What:** second independent gate for the §120 promotion candidate
  (STS_FORCED_MOVE, strictly-forced-only contraction), a known-RNG non-fair
  diagnostic run, and the resulting deployment decision. **Found during the
  known-RNG run: a hang** in the non-fair path (infinite loop at seed 10
  floor 11) and **non-decision-neutrality in the non-fair regime** (3/8
  diagnostic seeds diverged, seed 13 flipped the win) — the persistent
  searcher reuses the tree across decisions, so skipping a forced-node
  search changes later trees and the shared RNG stream. The fair path builds
  a fresh searcher per decision, which is why it stays neutral there.
- **Hang root cause and fix:** the forced skip advanced the root but left the
  cached winning line (`bestActions`/`bestOutcomePlayerHp`) stale; a stale
  `bestOutcomePlayerHp > 0` then sent `stepThroughSolution` on an empty
  action list forever. Fix: clear `bestActions` and reset
  `bestOutcomePlayerHp = -1` on the non-fair forced path
  (`ScumSearchAgent2::playoutBattle`). This also fixed the latent hang in the
  §118 STS_CONV_ROOT non-fair wiring (which the plan noted was untested at
  scale).
- **Scoping decision:** `STS_FORCED_MOVE` is now **fair-path-only**. In
  `playoutBattle` (non-fair) the standalone flag is a no-op — the forced
  shortcut there fires only inside `g_convRootStop` (the falsified §118
  arm). Rationale: non-fair divergence is real (measured) and its cpu saving
  is negligible (non-fair makes ~2 decisions/fight vs ~123 fair), so the
  shortcut's value exists only in the fair regime.
- **Confirmation gate 2 (fair, independent seed block, fixed binary):**
  seeds 126700–126955, `STS_FAIR=1`, @1k, 24 threads, GCP: flat **19.9% /
  floor 36.1 / hp 13.4 / cpu 8.30 s·run** vs forced **19.9% / 36.1 / 13.4 /
  cpu 6.80 (−18.0%)**; **0/256 per-seed outcome diffs** on won/floor/act/
  hpEnd/fightsLost/deathCombat/deathEncounter (`build/fm2b_{flat,forced}_256.csv`,
  total sec 2125.1 → 1741.8).
- **Known-RNG non-fair run (fixed binary):** seeds 10,11,13,14,16,17,18,19
  @1k: flat vs `STS_FORCED_MOVE=1` **0/8 diffs** (flag is a no-op in the
  non-fair path by design; no hang, completes in seconds
  `build/fm2_kr_{flat,forced}.csv`).
- **Verdict:** ✅ **promoted to built-in default ON** (fair path only;
  `g_forcedMoveSkip = true`; `STS_FORCED_MOVE=0` disables). Two independent
  256-seed fair gates agree on exact outcome equality (§120 seeds 0–255,
  §121 seeds 126700–126955) at −16 to −18% cpu, and the non-fair path is
  unchanged byte-for-byte (0/8 diffs) with the hang fixed. All historical
  fair results remain valid (decision-neutral); current-baselines.md notes
  the deployed-config change without touching headline numbers.
- **Artifacts:** `build/fm2b_{flat,forced}_256.csv`, `build/fm2_kr_{flat,forced}.csv`
  (GCP → local), local debug logs `build/fm_dbg*.log` (instrumentation
  removed). Code: `ScumSearchAgent2::playoutBattle` (non-fair scoping +
  bestActions reset), `playoutBattleFair` (unchanged logic, comment updated),
  `g_forcedMoveSkip` default in `BattleScumSearcher2.cpp`, env parse in
  `apps/one_combat.cpp::main`.
- **Cost:** ~90-100 s/arm wall for the fair gate; seconds for the known-RNG
  runs.

## §122 Phase 4 (fair-tree structural fix, STS_LIVE_VALID): S3 instrumented (first measurement), live-valid re-selection implemented in both searchers — S3 direction positive at both budgets but cpu-positive; promotion candidate only (2026-08-06, local + GCP)

- **What:** Phase 4 of the adaptive-budget program. Two parts: (1) Searcher3
  rollout-usage instrumentation (first-ever S3 measurement — searchdiag
  previously refused S3), and (2) the live-valid-biased edge selection fix in
  both searchers: when the PUCT-chosen stored edge is illegal in the current
  determinization, re-select among stored edges valid in THIS world (same
  UCB/PUCT scoring) and continue tree descent; only when no stored edge is
  valid does the sim fall back to a random rollout (the recorded §117
  behavior). Env `STS_LIVE_VALID=1` (default off) in
  `apps/one_combat.cpp::main`; `selectBestValidEdgeToSearch` /
  `selectBestValidEdgePUCT` in
  `src/sim/search/BattleScumSearcher2.cpp` /
  `src/sim/search/BattleScumSearcher3.cpp`.
- **T0 — S3 instrumentation:** `SearchDiagnostics` moved to a shared header
  (`include/sim/search/SearchDiagnostics.h`); `BattleScumSearcher3` gains a
  `diag` member + step() counters (rollout cause split, treeActions,
  maxTreeDepth, simSeconds in search/searchToTotal); `searchdiag` accepts
  S3 with rowtype A only (probeEvery forced 0 — the B-stage probes are S2
  machinery); invariants verified on S2 and S3 rows.
- **T1 — first S3 illegal-stored measurement (fair @3k, 6 seeds, GCP):**
  **S3 default 59.5% of rollout calls are the illegal-stored fallback**
  (MONSTER 70%, ELITE 54%, BOSS 54%); **S3−belief−chain 58.4%** (MONSTER
  71%, ELITE 55%, BOSS 50%) — vs S2's 48% (§117). The fair-tree/
  determinization mismatch is real and WORSE in S3 (particle worlds diverge
  more than single-determinization S2 trees).
- **Fix effect (searchdiag before/after, fair @500):** S2 illegal-share
  0.26 → **0.00**; S3 0.38 → **0.10**; rollout fractions unchanged; both
  searchers keep the diag invariants (0 violations).
- **Paired gates (256 seeds, block 126700+, fair, GCP):**
  - **S2 @1k:** flat 19.9% (51) vs fix 20.3% (52) — **+0.4pp** (SE 2.2pp,
    19 up / 18 down), floor 36.1→36.6, hp 13.4→12.4, cpu **+5.6%**.
  - **S3−bc @1k:** flat 16.8% (43) vs fix 20.3% (52) — **+3.5pp** (SE 2.4pp,
    27 up / 18 down), floor 34.5→35.0, hp 7.0→8.0, cpu **+15.1%**.
  - **S3−bc @3k (recommended operating point):** flat 19.1% (49) vs fix
    **24.6% (63) — +5.5pp (SE 2.6pp, 95% CI +5.5 ± 5.1pp, barely excludes
    zero), flips 35 up / 21 down / 200 same**, floor 37.6→37.0, hp
    7.4→**11.5**, cpu **+7.9%**.
- **Verdict:** ⚠️ **promotion candidate, not promoted.** S3's win direction
  is positive and consistent at both budgets (+3.5pp @1k, +5.5pp @3k with
  hp +4.1), and the structural diagnosis is confirmed (share 0.58→0.10),
  but the plan's T3-style promotion rule requires win ≥ flat with CI
  excluding a meaningful loss **AND cpu ≤ flat** — all three S3/S2 arms
  cost cpu (+5.6 to +15.1%; re-selected descents go deeper, more tree work
  per sim), so the AND clause fails. S2 is neutral at @1k. `STS_LIVE_VALID`
  stays env-gated default off. Recommended next: a second S3 @3k gate
  (any seed block) to firm the CI before any default flip; S2 needs an @3k
  pair if S2 deployment is ever considered (S2's operating point is not the
  current recommendation, §113).
- **Artifacts:** `build/lv_s2_{flat,fix}_256.csv`, `build/lv_s3_{flat,fix}_256.csv`,
  `build/lv_s3_3k_{flat,fix}.csv` (GCP → local), S3 diag CSVs
  `build/sdiag_fair3k_s3.csv`, `build/sdiag_fair3k_s3nobc.csv`, smoke
  `build/sdiag_lv{,_3}_{off,on}.csv`. Code: `SearchDiagnostics.h`,
  `BattleScumSearcher{2,3}.{h,cpp}`, `apps/one_combat.cpp::main`,
  `sdiagMetricsOf3`/`sdiagOnSearchComplete3` in `apps/one_combat.cpp`.
- **Cost:** ~5-25 min/arm wall on GCP (S3 @3k ~13 min/arm).

## §123 STS_LIVE_VALID second independent S3 gate + first S3 forced-move gate: LIVE_VALID PROMOTED to default ON in the fair-S3 path (recorded cpu-trade call); S3 forced-move contraction confirmed decision-neutral 0/256 at −8.5% cpu (2026-08-07, local + GCP)

- **What:** the §122 follow-up (second independent S3 @3k gate for the
  STS_LIVE_VALID promotion candidate) plus the first S3-port gate of the
  promoted forced-move contraction (`BattleScumSearcher3::onlyLegalAction`,
  same §120/§121 design as S2). Three paired arms on a fresh seed block
  (250000–250255), 256 seeds each, fair, @3k, 24 threads on sts-test:
  **ctl** = fair S3 default (forced-move ON, live-valid OFF);
  **fix** = ctl + `STS_LIVE_VALID=1`; **flat** = ctl +
  `STS_FORCED_MOVE=0`. Gates A (live-valid) = ctl vs fix; gate B
  (forced-move) = flat vs ctl.
- **Config (all arms):** commit `588fd6e` + the §123 promotion diff (parse
  block only); `one_combat bestbench 3000 256 0 250000 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=256`; asc 0; native OOC; policy PUCT on
  (`build/policy_trees_c.txt`); no combat value/PVNet
  (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`). Metric
  formula = producer `bestbench` summary (win% = wins/seeds, avg_floor,
  avg_hp_end, cpu_sec/run); paired flips from per-seed outcome columns
  (won/floor/act/hpEnd/fightsLost/deathCombat/deathEncounter, sec excluded).
- **Gate A results (block 250000+):** ctl **16.0% / 41 wins** / floor 35.7 /
  hp 7.1 / cpu 61.85 s·run vs fix **21.9% / 56 wins** / floor 36.8 / hp 10.2
  / cpu 70.88 s·run. Paired: 215/256 outcome-column diffs, won flips 34 up /
  19 down → delta **+5.9pp (SE 0.92pp, 95% CI +5.9 ± 1.8pp, excludes zero)**,
  floor +1.1, hp +3.1, cpu **+14.6%**. This is the second independent gate
  agreeing with §122's S3−bc @3k (+5.5pp, hp +4.1, cpu +7.9%, block 126700+).
  Direction, magnitude, and hp effect are consistent across both gates;
  both CIs exclude a meaningful loss.
- **Gate B results (block 250000+):** flat (STS_FORCED_MOVE=0) **16.0% / 41
  wins** / floor 35.7 / hp 7.1 / cpu 67.60 s·run vs ctl (default forced ON)
  16.0% / 41 wins / floor 35.7 / hp 7.1 / cpu 61.85 s·run. **0/256 per-seed
  outcome diffs on all 8 outcome columns — exact outcome equality**, cpu
  **−8.5%** (smaller than S2's −16-18%, §120/§121, because the S3 searcher
  is constructed before the check: the per-decision particle-belief
  constructor cost is not skipped on forced moves).
- **Verdict — LIVE_VALID: ✅ promoted, default ON in the fair-S3 path.**
  The §122 promotion rule (win ≥ flat with CI excluding a meaningful loss)
  is now satisfied twice independently (+5.5pp and +5.9pp); the cpu clause
  fails both times (+7.9%, +14.6%), so **the recorded cpu-trade call is:**
  accept ~+8 to +15% cpu for a reproducible ~+5 to +6pp win with +3 to +4
  end-HP — the strongest win-rate result of the adaptive-budget program and
  well within the plan's stated envelope ("~+8-10% cpu for a ~+3pp+ win").
  Scoping: default applies only when `STS_FAIR=1` and `STS_SEARCHER3=1`
  (computed after the STS_FAIR/STS_SEARCHER3 env parse in
  `apps/one_combat.cpp::main`); `STS_LIVE_VALID=0` explicitly disables;
  `fairgen` datagen is NOT covered (it forces the regime after the parse) —
  datagen keeps the recorded §117 behavior unless the flag is set
  explicitly (open question: re-run fairgen datagen with the fix to align
  the policy-target distribution). S2 fair stays opt-in (S2 @1k neutral
  +0.4pp at +5.6% cpu, §122; S2 needs an @3k pair if S2 deployment is ever
  considered, §113). Non-fair paths unchanged unless the env flag is set
  explicitly. The §113 headline (44.5% @3k with the full V4 gate stack) was
  measured pre-flip and remains valid as recorded; a re-measurement with
  the full stack + live-valid default is an open follow-up.
- **Verdict — S3 forced-move: ✅ confirmed default ON (fair S3).** 0/256
  exact per-seed outcome equality at −8.5% cpu on the same standard as
  §120/§121; the port is decision-neutral in the particle regime as
  predicted. Local 8-seed pre-gate smoke: 0/8 diffs at −16%.
- **Artifacts:** `build/lv2_s3_{ctl,fix}_256.csv`, `build/fm3_s3_flat_256.csv`
  (GCP → local; logs `build/lv2_s3_{ctl,fix}_256.log`,
  `build/fm3_s3_flat_256.log` on sts-test), local smoke
  `build/fm3_s3_{flat,forced}_8.csv`, `build/smoke_lv_{default,explicit,lv0}.csv`.
  Code: `BattleScumSearcher3::onlyLegalAction`
  (`include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`), agent wiring
  (`src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`), default
  (`apps/one_combat.cpp::main`). Decision logs:
  `2026-08-07-s3-forced-move.md`, `2026-08-07-live-valid-promotion.md`.
- **Cost:** 3 arms × ~12 min wall parallel on GCP (24 threads each,
  oversubscribed 3×); ~2 min/arm local at 8 seeds.
## §124 Winrate-wave baseline re-measurement + S3 feature-ablation re-derivation on the live-valid default binary (2026-08-07, local + GCP)

- **What:** the winrate-wave (§124-numbered) baseline wave
  (`docs/knowledge-base/plan-winrate-ideas-2026-08-07.md`): re-measure the
  recorded §113/§115 references (44.5% @3k/256p, 37.5% @1k/64p) on the
  current binary (HEAD 7b1a8d2, live-valid + forced-move defaults ON, §123)
  — the §123 flip happened after the references were measured — and
  re-derive the §106 S3 feature-ablation deltas (belief/chain), which §113
  invalidated and §115 flagged for re-derivation.
- **Config (all arms):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0` + full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`); block 126700–126955 (256
  seeds); asc 0; native OOC; policy PUCT on (`build/policy_trees_c.txt`);
  no combat value/PVNet; `bestbench` at 12 or 24 threads on sts-test.
- **Results (256 paired seeds, block 126700):**
  - **@1k/64p (S3−belief−chain, current binary): 37.9% / 40.2 floor / 21.9
    hp / 20.34 cpu-s·run** (`build/b2c_1k_64p.csv`) vs recorded reference
    37.5% (`honest_p64_1k_256.csv`): **−0.4pp (CI [−6.6,+5.9]), flips 36/35 —
    the §123 defaults are decision-neutral on the full stack @1k/64p.**
  - **@1k/256p: 41.4%** (`b3c_1k_256p.csv`) vs 64p: +3.5pp (CI [−10.2,+3.1],
    n.s.) — particles still flat-ish within noise on the new binary.
  - **@3k/256p: 46.9% / 42.9 floor / 26.1 hp / 35.49 cpu-s·run**
    (`b1c_3k_256p.csv`) vs recorded reference 44.5% (`honest_fix2_3k_256.csv`):
    **+2.3pp (CI [−9.0,+4.3], flips 40/34, n.s. directionally positive)** —
    new @3k headline on the current binary.
  - **@3k/64p: 42.6% / 24.79 cpu-s·run** (`b4_3k_64p.csv`) — 64p is ~2.6×
    cheaper than 256p at 3k with the same win rate as the pre-live-valid
    reference (42.6 vs 44.5, n.s.).
- **Ablation re-derivation (belief+chain ON vs OFF, accidentally clean
  config bug):** the original B1/B2/B3 runs launched without the
  `STS_S3_BELIEF=0 STS_S3_CHAIN=0` exports (config bug, banners read
  `S3-abl=11110`), producing full-S3-feature arms that pair directly with
  the correct S3−belief−chain arms: **belief+chain ON costs −11.3pp @64p
  (26.6 vs 37.9, CI [+5.1,+17.6]) and −12.1pp @256p (29.3 vs 41.4, CI
  [+5.5,+18.8])** — the §106 direction is confirmed with the honest
  enumerator + live-valid defaults, with a LARGER magnitude than the
  invalidated §106 deltas (+8.6/+4.7). The deployed S3−belief−chain config
  is re-confirmed; belief/chain stay off. @3k the same cost appears
  (−9.4pp: full-S3 37.5 vs S3−bc 46.9).
- **Verdict:** the recorded references reproduce on the current binary
  (flat @1k, n.s. +2.3pp @3k) — the §123 cpu-trade call does not transfer
  a loss to the full V4 stack. §115's "particles flat" holds within noise.
  New paired references for future gates: `b2c_1k_64p.csv` (@1k/64p),
  `b1c_3k_256p.csv` (@3k/256p), `b4_3k_64p.csv` (@3k/64p efficient).
- **Artifacts:** `build/{b1c_3k_256p,b2c_1k_64p,b3c_1k_256p,b4_3k_64p}.csv`
  (current binary, correct flags); `build/{b1_3k_256p,b2_1k_64p,b3_1k_256p}.csv`
  (full-S3-feature accidentals, kept as ablation data); logs on sts-test.
- **Cost:** ~2-20 min/arm wall on GCP; one GCP instance preemption killed
  and required relaunches (preemptible instance; no data lost — runs
  truncated before completion were re-run).

## §124a PVNet deployment-speed smoke (phase 6 of plan-value-targets-2026-08-07): conditional leaf gating + visible-state leaf cache implemented; behavior-preserving cache verified; gate pending on the §124 baseline (2026-08-07, local WSL)

- **What:** phase-6 speed work for the PVNet leaf in Searcher3, per
  `docs/knowledge-base/plan-value-targets-2026-08-07.md` (user request;
  a phase-5 value-only trainer draft was reverted in the same session —
  nothing of it remains). Two mechanisms:
  1. `STS_PVNET_COND_{TURN,DEPTH,BOSS}` gate the per-expansion NN leaf
     (`BattleScumSearcher3::pvnetCondAllowed`): failing conditions make the
     sim use the ordinary rollout value only (α=0 for that sim); the NN fires
     for long/unresolved continuations (post-rollout and direct-eval
     `evaluateLeaf` calls stay ungated). Defaults off — behavior preserved.
  2. `STS_PVNET_CACHE` (default ON): PVNet leaf values cached by
     `node.obsHash` at the direct-eval sites (no-legal-action, invalid-edge,
     depth cap), where repeated sims re-evaluate the same visible state.
- **Config (all arms):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64 STS_PVNET=build/v_combat_pvnet.txt`
  (α=1.0 default), `./build/one_combat bestbench 300 8 0 0 <out.csv>`, 12
  threads, seeds 0-7, asc 0, local WSL; full V4 OOC gate stack on (native
  OOC). Model `build/v_combat_pvnet.txt` (d128 h256 hds4 L2 nq11, Jul 26).
- **Results (8 seeds @300 sims — smoke only, not a gate):**
  | arm | win% | avg_floor | cpu_sec/run | note |
  |---|---|---|---|---|
  | cache ON (default) | 0.0 | 25.8 | 44.7 | reference |
  | `STS_PVNET_CACHE=0` | 0.0 | 25.8 | 44.5 | per-seed rows identical (only `sec` differs) |
  | `STS_PVNET_COND_DEPTH=2` | 0.0 | 28.9 | 69.3 | outcomes differ (gate fires) |
  | `STS_PVNET_COND_TURN=3` | 12.5 | 36.6 | 77.5 | outcomes differ (gate fires) |
  | `STS_PVNET_COND_BOSS=1` | 0.0 | 30.5 | 64.0 | outcomes differ (gate fires) |
  cpu differences between gated arms track run depth (deeper runs = more
  decisions = more search), not per-sim cost; timing conclusions require the
  real gate. All knobs print in the `[PVNet alpha = ...]` banner.
- **Verification:** cache-on vs cache-off per-seed outcomes identical
  (sorted-by-seed, all non-`sec` columns) — cache is behavior-preserving;
  `ctest` 5/5; `searchdiag 2 300 0` runs clean with `STS_PVNET_COND_TURN=3`.
- **Deferred (recorded reasons):** batched NN leaf calls (leaf evals are on
  effectively unique states — batching needs a `step()`/`backpropagate`
  restructure for BLAS-efficiency-only gain); GBM/MLP distillation (phase-5
  training line); rollout-skip at α=1.0 (observed `playoutRandom` still runs
  and its terminal value is discarded by the α=1.0 blend — wasted compute —
  but removing it changes `bestActionSequence` semantics; candidate knob).
- **Artifacts:** `build/pv6_cache_{on,off}.csv`, `build/pv6_cond_{depth,turn,boss}.csv`,
  `build/pv6_sdiag.csv`, logs `build/pv6_*.log`. Code:
  `BattleScumSearcher3.{h,cpp}` (`pvnetCondAllowed`, `evaluateLeaf` cache,
  blend-site gate), `apps/one_combat.cpp` env parse. Decision log:
  `2026-08-07-pvnet-deployment-speed.md`.
- **Next:** paired 256-seed gate @1k/64p vs the §124 baseline (winrate wave
  B1-B4 not yet recorded on GCP), then @3k if positive; pre-registered null
  at both budgets closes the PVNet leaf line (winrate-plan §4.3 rule).

## §125 Winrate-wave Wave-1/2 gates: cPUCT sweep, STS_S3_EXPAND, TERM_WIN+cpsi — all null or negative; the leaf-evaluator line flips POSITIVE with a fresh honest-data vnet (§126) (2026-08-07, local + GCP)

- **What:** the winrate-wave gated items that do not involve the vnet
  (`docs/knowledge-base/plan-winrate-ideas-2026-08-07.md` §3.3/§4.1/§4.2).
  All arms: full V4 gate stack, S3−belief−chain, block 126700 (unless noted),
  asc 0, fair, paired with `paired_analysis.py` vs the §124 references.
- **cPUCT sweep (STS_CPUCT; §3.3):** 128-seed local probe @1k/64p:
  cPUCT 1.0 → 21.1%, 1.5 → 28.9%, **2.5 (default) → 39.1%**, 4.0 → 40.6%,
  6.0 → **42.2%** — monotone, higher exploration better (consistent with
  §26's UCB > PUCT at deep budgets). Gate 1 (256 seeds, block 126700):
  cPUCT=6.0 **42.2% vs 2.5 37.9% = +4.3pp (CI [−10.9,+2.3])**. Gate 2
  (fresh block 250000, paired control): 6.0 **39.8% vs 38.7% = +1.1pp
  (CI [−8.2,+5.9])**. Both n.s. → **not promotable; the cPUCT line is
  closed** (direction consistent but sub-significant at 256 seeds twice;
  `g_cPuct` default stays 2.5). Artifacts: `build/cpuct_*_128.csv`,
  `build/cpuct_{4,6}_256.csv`, `build/cpuct2_{2_5,6}_256.csv`.
- **STS_S3_EXPAND (§4.1, new code):** when no stored edge is valid in the
  current determinization (the live-valid residual, ~5.4% of rollouts at
  the deployed point), enumerate the live state's legal actions into the
  tree (action-keyed, priors on the new edges only, cap 32) instead of a
  random rollout; env `STS_S3_EXPAND=1`, `STS_S3_EXPAND_MAX` (default 32),
  requires live-valid semantics. searchdiag (6 seeds @3k/64p, deployed
  stack): illegal-stored share 0.054 → **0.0**, treeActions +10%. Gates:
  @1k/64p **35.5% vs 37.9% = −2.3pp (CI [−2.7,+7.4], flips 18/24, 16%
  discordant)**; @3k/64p **44.1% vs 42.6% = +1.5pp (CI [−6.6,+3.5], flips
  23/19)**. Mixed null at both budgets → **falsified, line closed per the
  pre-registered rule; the env stays opt-in** (`build/s3exp_{1k_64p,3k_64p}.csv`).
- **TERM_WIN + C_psi evaluator (§4.2):** the §110/§116 follow-up — terminal
  victory leaves priced with the counter-sensitive C_psi next-fight model
  (`STS_TERM_WIN=1 STS_TERM_WIN_EVAL=cpsi STS_CPSI_NN=build/v_combat_cpsi.txt`)
  instead of the counter-insensitive win tree (§110: 0 splits on counter
  features). @1k/64p: **29.3% vs 37.9% = −8.6pp (CI [+2.0,+15.2],
  SIGNIFICANT, flips 28/50) at 3.7× cpu (73.83 vs 20.34 cpu-s·run)** — the
  cross-combat setup pricing is decisively negative at the efficient point;
  **falsified, line closed** (the §116 win-tree variant was null; the cpsi
  variant is negative). Artifact `build/termcpsi_1k_64p.csv`.
- **Recording note:** the §124 config-bug accidentals (§124) double as the
  clean ablation data; this entry's arms were all verified by their
  `S3-abl[b,p,c,l,crn]=01010` banners.


## §126 Fresh honest-data combat V_combat leaf (STS_VNET, α=0.3): THREE significant gates (+12.5/+12.1/+12.5pp) — PROMOTED to default ON in the fair-S3 path (recorded cpu-trade call); §97's rejection reversed (2026-08-07, local + GCP)

- **What:** the winrate-wave boss-leaf item (§4.3 of
  `docs/knowledge-base/plan-winrate-ideas-2026-08-07.md`), reframed by the
  evidence: a NEW combat value net trained on fresh honest trajectories,
  applied UNCONDITIONALLY at a LOW blend weight. §97's rejection (old
  1,500-tree vnet, old-era data, α0.3/0.5 under the pre-§113 stack) does not
  transfer: the boss-only conditioning idea was tested first (flat, see
  below) and the unconditional fresh model is strongly positive.
- **New labels:** `combatgen` 1,500 seeds @1k sims with the current honest
  searcher (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0`,
  live-valid default ON; heuristic-OOC run loop — `runCombatGenSeed`), seeds
  0-1499 → `build/vcombat_honest.csv`: **287,517 rows, 16,337 fights, 733
  features** (~3.5 min on GCP). `train_value_combat.py` (XGBoost, val-rmse
  7.99 endHp, scaling probe positive on Demon Form/Feel No Pain/etc.) →
  `export_combat_model.py` → **`build/v_combat_honest.txt`: 804 trees, 733
  features, base_score 25.97**.
- **New code:** `STS_VNET_COND_BOSS` / `STS_VNET_COND_ACT3` gate the vnet
  leaf to rollout-dominant contexts (boss fights / act 3, §117) via
  `vnetCondAllowed` (S3 `step()` leaf capture + `evaluateLeaf`); both unset
  = always on, byte-identical to pre-conditioning behavior.
- **Gates (256 seeds each, full V4 gate stack, S3−belief−chain, fair, asc 0;**
  vnet = `STS_VNET=build/v_combat_honest.txt`):
  | arm | config | win% | paired vs | Δ (95% CI) | flips | cpu |
  |---|---|---|---:|---:|---:|---:|
  | gate 1 @1k/64p | α=0.3 | **50.4%** | B2c 37.9% | **+12.5 [+5.5,+19.5]** | 60/28 | 41.2 s·run |
  | gate 2 @1k/64p (block 250000+) | α=0.3 | **50.8%** | ctl 38.7% | **+12.1 [+4.7,+19.5]** | 65/34 | 49.8 (contended) |
  | win point @3k/64p | α=0.3 | **55.1%** | B4 42.6% | **+12.5 [+6.2,+18.8]** | 52/20 | 85.5 (contended) |
  | @1k/64p | α=0.5 | 43.4% | B2c 37.9% | +5.5 [+1.2,+12.5] | 47/33 | 43.9 |
  | @3k/64p | α=0.5 | 47.7% | B4 42.6% | +5.1 [−11.7,+2.0] | 47/34 | 87.3 (contended) |
  | @1k/64p | α=0.7 | 43.8% | B2c 37.9% | +5.9 [−1.2,+12.9] | 47/31 | 42.6 |
  | @1k/64p | α=0.3 + cond-boss | 38.7% | B2c 37.9% | +0.8 [−5.5,+3.9] | 20/18 | 38.1 |
  | @1k/64p | α=0.5 + cond-boss | 38.3% | B2c 37.9% | +0.4 [−4.7,+3.9] | 17/16 | 39.2 |
  The α curve is monotone down (12.5 → 5.5 → 5.9 pp from α0.3 → 0.5 → 0.7
  at 1k): a noisy-but-right leaf blended lightly is the operating point.
  **Boss-only conditioning KILLS the benefit** (flat at both α, 13-15%
  discordance) — the vnet's value is spread across all rollout-heavy
  contexts, not just bosses.
- **Verdict: ✅ PROMOTED — default ON in the fair-S3 path.** Three
  independent significant gates (two blocks × @1k/64p, plus the @3k/64p win
  point) at α=0.3; the §123-style two-gate rule is exceeded. **Recorded
  cpu-trade call:** accept ~2-2.4× cpu (43.9-49.8 vs ~20 cpu-s·run at 1k;
  contended 3k reads inflated) for a reproducible **~+12pp win, +2-3 floor,
  +4-6 end HP** — the strongest win-rate result of the project (honest
  top: 55.1% @3k/64p vs the pre-vnet 46.9%). Scope mirrors the live-valid
  default: fires only when `STS_FAIR=1` and `STS_SEARCHER3=1` after the
  env parse; `STS_VNET` unset → default model `build/v_combat_honest.txt`
  at α=0.3; any explicit `STS_VNET=…` overrides (e.g. `STS_VNET=1` → the
  legacy `build/v_combat_trees.txt` 100-tree model at α=0.5, or
  `STS_VNET=<missing-path>` → load failure → vnet off, usable as a disable).
  `fairgen` datagen is not covered (regime forced after parse);
  `combatgen` IS covered (envs set during parse) — future combat datagen
  includes the vnet by default, aligning the label distribution with the
  deployed leaf.
- **Known caveats:** the model is trained on the heuristic-OOC run
  distribution (combatgen's own loop, not the V4 gate stack); the transfer
  to the gate-stack distribution is measured empirically (it works) but a
  gate-stack-distribution retrain is the natural follow-up. S2 fair and
  non-fair paths unchanged (env-only). The vnet leaf adds ~0.2-0.3 ms per
  blended leaf eval (804 trees).
- **Artifacts:** `build/vcombat_honest.csv` (1 GB, ignored),
  `build/v_combat_honest.{json,txt,val.csv}`, per-seed gate CSVs
  `build/vnet_{all_a03_1k,all_a05_1k,all_a07_1k,boss_a03_1k,boss_a05_1k,a03_3k,all_a05_3k}.csv`,
  `build/vnet2_{ctl,a03}_250k.csv`; code `vnetCondAllowed`,
  `g_vnetCondBossOnly`/`g_vnetCondAct3` (`BattleScumSearcher3.cpp`,
  `apps/one_combat.cpp`). Model sha256 in
  `docs/knowledge-base/evaluation/current-baselines.md`.
- **Cost:** datagen ~3.5 min + training ~10 min + export on the desktop;
  each 256-seed arm ~7-30 min wall on GCP.
## §124b Prior-guided S3 rollouts (STS_S3_ROLLOUT_POLICY): implemented opt-in; smoke fires, ~2.4× cpu; paired 256-seed gate pending vs the §126 vnet default (2026-08-07, local WSL)

- **What:** revives the parked §119 "Phase 3 (policy-guided rollouts)": with
  `STS_S3_ROLLOUT_POLICY=1`, `BattleScumSearcher3::playoutRandom` samples
  rollout actions from the **GBM policy prior** (`computeEdgePriors` — the
  same distribution PUCT priors use, `build/policy_trees_c.txt` auto-loaded)
  instead of the static `rolloutWeight` heuristic (ATTACK=8/POWER=3/other=2/
  END_TURN+POTION=1 — the rollout was never truly uniform; this replaces the
  hand-authored bias with the learned prior). Restricted to the GBM policy
  net (`g_usePolicyNet && loaded()`, not shadowed by a PVNet policy head) —
  a PVNet-head forward per rollout step would cost ~14-18× a sim. Default
  off; the heuristic branch is untouched, so unset = byte-identical.
  Rationale: with the §126 vnet leaf (α=0.3) the rollout outcome carries 70%
  of the leaf blend — rollout quality matters more than pre-vnet.
- **Config (smoke):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64` (vnet α=0.3 default ON; no PVNet),
  `./build/one_combat bestbench 300 8 0 0 <out.csv>`, seeds 0-7.
- **Results (8 seeds @300 sims — smoke only):**
  | arm | win% | avg_floor | cpu_sec/run |
  |---|---|---|---|
  | control (heuristic rollout) | 12.5 | 38.2 | 7.5 |
  | `STS_S3_ROLLOUT_POLICY=1` | 25.0 | 44.0 | 18.2 |
  Outcomes differ on most seeds (won differs on seed 6); banner prints
  `[S3 rollout-policy = ON]`. 2.4× cpu = per-step GBM prior evals; win-rate
  deltas are 8-seed noise, not evidence. `ctest` 5/5.
- **Pre-registered gate (pending, GCP):** paired 256-seed @1k/64p on the
  §126 config vs `build/vnet_all_a03_1k.csv` (50.4%); then @3k if positive.
  Known risk: prior-guided rollouts may collapse rollout diversity and make
  Q estimates self-consistent but overconfident — a null or negative closes
  the line. A temperature/mixture knob with the heuristic is the obvious
  follow-up if the pure-prior version collapses.
- **Artifacts:** `build/pri0_{ctl,pol}.csv` + logs. Code:
  `BattleScumSearcher3::playoutRandom` (`src/sim/search/BattleScumSearcher3.cpp`),
  `apps/one_combat.cpp` env parse, header extern. Decision log:
  `2026-08-07-prior-guided-rollouts.md`. KB: `combat-search.md` (rollout
  section).
## §124c Prior-guided S3 rollouts — paired 256-seed gate: SIGNIFICANTLY NEGATIVE (−7.0pp) — line closed (2026-08-07, GCP sts-test)

- **What:** the §124b pre-registered gate for `STS_S3_ROLLOUT_POLICY=1`
  (rollout actions sampled from the GBM policy prior instead of the static
  `rolloutWeight` heuristic). Pre-registered rule: null or negative closes
  the line (diversity-collapse risk was the known failure mode).
- **Config (both arms):** full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, vnet α=0.3 default ON,
  block 126700–126955 (256), asc 0, 24 threads; policy arm adds
  `STS_S3_ROLLOUT_POLICY=1`. Commit 3f04e82 + the §124b source sync
  (BattleScumSearcher3.{h,cpp}, one_combat.cpp).
- **Results (paired, `paired_analysis.py`):**
  | metric | control (heuristic rollout) | policy-prior rollout | delta |
  |---|---|---:|---:|
  | win | **50.4%** (129/256) | **43.4%** (111/256) | **−7.0pp, 95% CI [−13.7, −0.4]** |
  | avg floor | 44.1 | 42.8 | −1.3 (CI [−2.6, 0.0]) |
  | avg HP end | 29.4 | 22.7 | −6.7 |
  | cpu-s/run | 30.5 | 83.8 | +2.7× (mostly uncontended reads) |
  Discordant 76/256 (30%): control-only 47, policy-only 29.
- **Sanity:** the control arm reproduces the §126 reference exactly (50.4%,
  129/256 — same block/config), so the pairing is clean. Banner confirms
  `[S3 rollout-policy = ON]` on the policy arm.
- **Verdict: ❌ falsified, line closed per the pre-registered rule.** The GBM
  prior — trained on older-policy visit distributions — actively HURTS
  rollouts: −7.0pp significant at 2.7× cpu. No @3k re-gate (pre-registered:
  only if positive). The env stays opt-in (no behavior change unset);
  follow-ups (temperature/mixture with the heuristic) are NOT pursued unless
  the prior is retrained on current-stack data (the §126-vnet-era policy
  prior v2 line in winrate-plan §3.4 is the natural prerequisite).
- **Artifacts:** `build/pri1_ctl_256.csv` (control; md5
  4106e1deb6a76e094a87b70ba9c9ea64), `build/pri1_pol_256.csv` (policy arm;
  md5 4ef1416c17a1790d0dfb16c3942dd760), logs on sts-test
  `build/pri1_{ctl,pol}_256.log`; local smoke `build/pri0_{ctl,pol}.csv`
  (§124b). KB: `combat-search.md` (prior-guided rollouts section updated to
  the verdict). Decision log: `2026-08-07-prior-guided-rollouts.md` (verdict
  appended).
## §127 Policy prior v2 pipeline (winrate-plan §3.4+§3.5): fairgen datagen (1000 seeds, vnet-α0.3-aligned, 22-action-feature producer) + v2 prior trained + policystats bug fix; paired gate pending (2026-08-07, GCP + local)

- **What:** the merged §3.4/§3.5 pipeline. Datagen: `fairgen 1000 1000 0 0.3
  build/fair34_{v,p,o}.csv 400000` on GCP with `STS_LIVE_VALID=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64` **plus explicit
  `STS_VNET=build/v_combat_honest.txt STS_VNET_ALPHA=0.3`** (recorded
  deviation: §3.4 predates the §126 promotion; aligns the policy rows with the
  deployed controller; without the alpha the explicit env defaults to the
  legacy 0.5). Producer is the §3.5 22-action-feature build (1766 state + 22
  action): `aSelectSize, aSelTotalCost, aSelAtk/Skl/Pow, aSelUpgraded,
  aSelPlayOrder, aSelObtainWeight` appended after the original 14 (PVNet
  first-14 and old model-nfeat paths unaffected). Output: 225,057 value +
  933,458 policy (1793 cols) + 21,319 ooc rows in 431s; CSVs pulled to
  `build/fair34_{v,p,o}.csv`.
- **Training:** `train_policy.py build/fair34_p.csv build/policy_v2.json
  build/policy_trees_c_v2.txt` (100 trees, 751 non-constant features, GPU) —
  in-sample top1 0.544, visit-share 0.477.
- **Policystats bug found + fixed (pre-existing, not introduced here):** the
  mode stored the action block only in `act` (the optional PVNet comparison)
  and never into `feat`, so the GBM `predictVec` path always saw zeroed action
  features → uniform per-group softmax (CE == gbmEntropy) for every policy
  model. Fixed: action block now also fills `feat`; `actionN` is derived from
  the actual CSV header (14 pre-§3.5, 22 since) instead of the current
  producer count, so old and new CSVs both analyze. This is the first honest
  offline prior comparison the tool has produced.
- **Offline comparison (both models, all 933,458 rows of the new data):**
  | metric | tracked `policy_trees_c.txt` | v2 `policy_trees_c_v2.txt` |
  |---|---|---:|
  | top1 agreement | 0.5522 | 0.5454 |
  | CE | 1.3327 | **1.2397** |
  | KL | 0.6209 | **0.5279** |
  | regret (1 − p\*) | 0.5192 | 0.5225 |
  | gbmEntropy | 1.4359 | 1.3072 |
  v2 clearly better on CE/KL (≈0.09), tied on top1/regret. Note: tracked was
  trained on old-distribution rows, so this overstates v2's edge; the paired
  gate decides.
- **Gate (running on GCP):** two arms @1k/64p, block 126700, full V4 stack +
  vnet default: control (default tracked prior) vs `STS_POLICY=
  build/policy_trees_c_v2.txt`; provenance verified via `/proc/PID/environ`.
  Pre-registered (§3.4): a null closes the prior-v2 line.
- **Artifacts:** `build/fair34_{v,p,o}.csv` (3.4 GB p CSV, 822 MB v, local +
  sts-test), `build/policy_trees_c_v2.txt` (179 KB; sha256 recorded at gate
  close), `build/policy_v2.json`, `build/ptrain_v2.log`, GCP logs
  `build/fair34.log`, `build/pri2_{ctl,v2}_256.log`. Code:
  `combatFillActionFeatures` (§3.5 features), policystats fix
  (`apps/one_combat.cpp`). Decision log:
  `2026-08-07-policy-prior-v2-pipeline.md`.
- **Gate verdict (appended, 2026-08-07): ❌ NULL — line closed per the
  pre-registered rule.** Paired 256-seed @1k/64p, block 126700, full V4 stack
  + vnet default: v2 prior **48.4% vs tracked 50.4% = −2.0pp (95% CI
  [−8.2,+4.3])**, floor −1.5 (CI [−2.9,−0.1]), HP −4.2, cpu equal (73.8 vs
  75.7 s/run). Discordant 71/256 (tracked-only 38, v2-only 33). Control
  reproduced the §126 reference exactly (129/256 = 50.4%) — clean pairing.
  The better offline CE/KL (−0.09) does not transfer to the deployed PUCT
  stack — the same pattern as §124c (prior-guided rollouts): prior-quality
  improvements measured offline do not translate online at this configuration.
  v2 artifact kept for reference (`build/policy_trees_c_v2.txt`, 100 trees,
  751 feats, sha256 30ea8598…). No @3k re-gate (pre-registered: only if
  positive).
## §128 Value-only utility-distribution model (plan-value-targets phase 5): trained on the §3.4 fairgen rows; ~4× better win calibration than the tracked PVNet on the same held-out rows (2026-08-07, local)

- **What:** phase 5 of `docs/knowledge-base/plan-value-targets-2026-08-07.md`:
  a value-only transformer (same 14-token encoder as CombatPVNet, NO policy
  head) predicting a 51-bin categorical over the MCTS terminal utility
  R = 0 on loss, 50 + endHp on win (bin 0 = loss; bins 1-50 = endHp/maxHp
  fraction on wins, mapped by maxHp at inference). Loss = CE; win prob =
  1 − p(bin 0); EV = Σ p_b·(50 + maxHp·mid_b). New trainer
  `train_combat_utility.py` + eval `eval_combat_utility.py`; native export
  format `combat_utility_v1` (encoder section identical to `combat_pvnet_v1`,
  single `util` head) with Python-side loader support added to
  `combat_pvnet_parity.py`. No C++ integration (deployment is not part of
  this phase; the vnet owns the leaf, §126).
- **Data:** `build/fair34_v.csv` (225,057 rows, §127 datagen: vnet-era,
  live-valid, current controller, rich labels). 12 epochs, D=128, 2 layers,
  4 heads, AdamW 1e-4, batch 1024, GPU (RTX 3060 Ti); held-out val CE 2.69
  (ln(51)=3.93 random). Checkpoint selection = val-seed CE (sibling
  ranking/regret later). Artifacts: `build/v_combat_utility.txt`
  (combat_utility_v1), `build/train_utility5.log`,
  `build/eval_utility_fair34.json`.
- **Results (same 30,000 held-out val rows of fair34_v.csv, seed%100<20):**
  | metric | tracked PVNet `v_combat_pvnet.txt` (old fair_v data) | utility model (fresh data, 51-bin) |
  |---|---|---:|
  | win Brier | 0.2505 | **0.0647** |
  | win ECE | 0.3298 | **0.0688** |
  | death BCE | 2.2076 | **0.2287** |
  | bin CE | — | 2.6917 |
  | EV MAE (terminal scale) | — | 13.3 |
  - **Finding 1 (distribution gap):** the tracked PVNet is badly
    miscalibrated on the new distribution — 0.2505 Brier / 0.33 ECE vs its
    0.107/0.002 recorded on its own (old, weaker-controller) training data.
    Direct evidence for the phase-2-4 premise of the value-targets plan.
  - **Finding 2 (target+data):** fresh data + direct terminal-utility
    distribution beats the old-data win/quantile reconstruction ~4× Brier,
    ~5× ECE, ~10× death BCE on identical rows. Caveat: data and target
    changed together — a clean target-only ablation (same data) and the
    shared-encoder variant (does policy sharing hurt value?) are follow-ups.
- **Scope note:** nothing deployed changes; the PVNet and VNet artifacts are
  untouched. The phase's purpose is offline research that informs the next
  vnet retrain (the §126 gate-stack-distribution follow-up, in progress by
  another agent): the fresh-data + direct-target recipe is transferable to
  GBM training (`train_value_combat.py`).
- **Deferred:** shared-encoder variant (needs the dual-CSV policy pass),
  C++ `CombatPVNet::load`/`leafValue` support for `combat_utility_v1`
  (only useful when a deployment gate exists), sibling-ranking eval (needs
  phase-2/3 data).
- **Artifacts:** `build/v_combat_utility.txt`, `build/v_combat_utility_smoke.txt`,
  `build/eval_utility_fair34.json`, `build/eval_pvnet_fair34.json` (PVNet
  reference on the same rows), logs. Code: `train_combat_utility.py`,
  `eval_combat_utility.py`, `combat_pvnet_parity.py` (utility-format
  parsing). Decision log: `2026-08-07-value-only-utility-net.md`.

## §129 Gate-stack-distribution vnet retrain (STS_DATAGEN_GATES): NULL vs the deployed model at both operating points; the α optimum shifts 0.3→0.5, confirming better calibration but no replacement (2026-08-07, local + GCP)

- **What:** the §126 follow-up — retrain the combat value leaf on labels from
  the DEPLOYED run-level distribution (V4 one-ply gate stack) instead of
  `combatgen`'s heuristic-OOC loop, and gate whether the gate-stack model
  replaces the deployed honest-data model. New code: `STS_DATAGEN_GATES=1`
  routes `runCombatGenSeed`'s OOC decisions through the same opt-in one-ply
  gate chain as `bestbench` (`datagenGateStack` dispatch + the card-reward
  gate in the REWARDS branch; each gate self-guards on its env flag + model
  load; unset behavior verified byte-identical on 10 seeds).
- **New labels:** `combatgen` 1,500 seeds @1k sims (fresh offset 1500-2999)
  with the gates ON (plus the §126 vnet default, which combatgen covers) →
  `build/vcombat_gated.csv`: **499,089 rows, ~1.74× the heuristic-OOC set
  (gated runs survive longer → more fights)**. Trained (val-rmse 10.83
  endHp — higher than the heuristic set's 7.99, reflecting the harder
  long-run label distribution; scaling probe positive on all tested
  powers) → exported `build/v_combat_gated.txt`: **738 features, 733 trees,
  base_score 36.41, sha256 `5322c9f1…`**.
- **Gates (256 seeds, block 126700, full V4 gate stack, S3−belief−chain,
  64p, fair; paired vs the no-vnet §124 references and vs the deployed
  honest model's best points):**
  | arm | win% | vs no-vnet | vs deployed (honest α0.3) |
  |---|---|---|---|
  | @1k/64p α0.3 | 46.1% | +8.2pp (CI [+0.8,+15.6]) | **−4.3pp (CI [−10.9,+2.3])** |
  | @1k/64p α0.5 | **53.1%** | +15.2pp (CI [+8.2,+22.3]) | **+2.7pp (CI [−9.4,+3.5])** |
  | @1k/64p α0.7 | 47.3% | +9.4pp | −3.1pp |
  | @3k/64p α0.3 | 52.7% | +10.1pp | −2.4pp |
  | @3k/64p α0.5 | **52.0%** | +9.4pp (CI [+2.0,+16.4]) | **−3.1pp (CI [−3.5,+9.4])** |
  The gated model's α optimum shifts UP (0.5 vs the honest model's 0.3) —
  consistent with better calibration on the deployment distribution — but at
  its own optimum it does not beat the deployed model: **−4.3pp @1k/α0.3,
  +2.7pp @1k/α0.5, −3.1pp @3k/α0.5 — all n.s., direction mixed.**
- **Verdict: NULL for replacement — the deployed honest-data model
  (`build/v_combat_honest.txt` @α0.3) STAYS.** Both models strongly beat
  no-vnet at both operating points (the §126 result is robust to the label
  distribution); the gate-stack retrain adds nothing significant and is
  not promoted. `STS_DATAGEN_GATES` stays opt-in (useful if datagen
  distribution alignment is wanted for other labels).
- **Artifacts:** `build/vcombat_gated.csv` (ignored),
  `build/v_combat_gated.{json,txt,val.csv}`, per-seed gate CSVs
  `build/gv_{a03_1k,a05_1k,a07_1k,a03_3k,a05_3k_final}.csv` (the α0.5 @3k
  arm was resumed mid-run at 24 threads: 171+81+4 gap seeds merged by seed —
  a kill/restart resume pattern that works because `bestbench` rows are
  per-seed and seed-order-independent; issue 46's append-without-dedup
  applies). Code: `datagenGateStack`, `g_datagenGates`
  (`apps/one_combat.cpp`, `runCombatGenSeed`).
- **Cost:** datagen ~40 min local (12 threads); training + export ~15 min
  local; gates ~3×22 min + 2×45 min (8 threads) + 1×4 min resume (24
  threads) on GCP.

## §130 5.2 counter-aware OOC pricing — CLOSED on evidence, no retrain gate (2026-08-07, local diagnostic only)

- **What:** plan `plan-winrate-ideas-2026-08-07.md` §5.2 (counter-aware OOC
  pricing): the deployed win tree has zero counter-relic sensitivity (§110:
  0/1,060 splits on the eight counter features despite all being among its
  448 selected features), and the plan proposed fixing it by (a) retraining
  the win GBM on a corpus with populated counter columns, or (b) a C_psi
  next-fight survival term for rest/event decisions. Closed **without** a
  retrain gate by user decision after the diagnostic below.
- **Diagnostic (this session, read-only):** the fresh deployed combat vnet
  (`build/v_combat_honest.txt`, 804 trees, 287,517 honest `combatgen` rows)
  assigns the counter features ~0.01% of total split gain (Happy Flower
  0.0047%, Incense Burner 0.0073%, Ink Bottle 0.0009%; Nunchaku/Pen Nib/
  Sundial/Panache below that) — and its training data HAD real counter
  variance: happyFlowerCtr 0-2 (6,075 nonzero rows), incenseBurnerCtr 0-5
  (3,086), inkBottleCtr 0-9 (3,577), nunchakuCtr 0-9 (7,879), penNibCtr
  −1..8 (7,160), sundialCtr 0-2 (2,677), panacheCtr −5..5 (148); only
  inserterCtr was constant 0 (correctly — Inserter is a Defect-only relic
  and the agent plays Ironclad).
- **Evidence chain (four independent readings):** (1) §110 win tree
  0/1,060 splits; (2) this diagnostic — a second, fresh-data GBM also
  reads no signal in counters conditional on HP/gold/potions/deck; (3)
  §116 — the controlled forced-Happy-Flower benchmark found no winrate or
  stall-behavior benefit from counter-aligned play; (4) §125 — the
  counter-SENSITIVE evaluator (C_psi) applied at the combat leaf was
  significantly NEGATIVE (−8.6pp, CI [+2.0,+15.2]).
- **Verdict:** the counter-insensitivity is the models correctly reading
  "no signal", not a data artifact; OOC decisions (rest vs upgrade, events,
  shop, pathing) barely depend on counter state, and the in-combat
  energy-tick signal the counters carry is already visible to the deployed
  combat vnet (§126). The §110 open question ("counter pricing requires a
  counter-aware terminal model") is answered negatively for the OOC side;
  the combat-side counter-pricing line was already closed (§116, §125).
  **5.2 closed; no retrain gate, no code change, nothing deployed.**
- **Artifacts:** none (diagnostic only; computed from the tracked
  `build/v_combat_honest.txt` JSON and `build/vcombat_honest.csv`).
- **Cost:** ~15 min local, read-only.

## §131 Target-vs-data ablation (phase-5 follow-up): fresh data is the big lever (2.7×), the 51-bin utility target still adds 31% on identical data (2026-08-07, local)

- **What:** isolates the two changes conflated in §128. Trained the
  old-style PVNet (win/death/quantile/potion/turns heads, shared encoder) on
  the SAME fresh rows as the §128 utility model (`train_combat_pvnet.py` on
  `build/fair34_v.csv` + `build/fair34_p.csv`, 10 epochs, batch 1024, best
  val 1.487 → `build/v_pvnet_fresh.txt`). Trainer fixed for the §3.5
  22-action-feature policy CSV (slices the first 14 for the PVNet action
  encoder, mirroring the eval/parity scripts).
- **Results (identical 30,000 held-out val rows of fair34_v.csv):**
  | metric | old PVNet (old fair_v data) | fresh PVNet (fresh data, old target) | utility 51-bin (fresh data, new target) |
  |---|---|---:|---:|
  | win Brier | 0.2505 | 0.0940 | **0.0647** |
  | win ECE | 0.3298 | 0.0987 | **0.0688** |
  | death BCE | 2.2076 | 5.2731 | **0.2287** |
  - Data effect: fresh-data-only retrain 0.2505 → 0.0940 Brier (2.7×) —
    the distribution-gap finding (§128) stands; training on the current
    controller's rows is the bigger lever.
  - Target effect: the 51-bin terminal-utility head on IDENTICAL data still
    beats the win/quantile heads: 0.0940 → 0.0647 Brier (−31%), ECE −30%.
  - The fresh PVNet's separate death head collapsed (death BCE 5.27, predicts
    ≈0 death always) while its win head is fine — the utility head gets death
    probability for free from bin 0 (0.2287) — evidence for the single-head
    design.
- **Interplay with §129 (gate-stack vnet retrain, NULL):** the parallel
  session's fresh-data retrain kept the endHp-regression target and did NOT
  replace the deployed vnet — so on the GBM side a data-only retrain is
  already exhausted. This ablation shows the target change is a separate,
  measurable lever (31% Brier on identical transformer rows) — the untested
  combination is a GBM with a distribution/quantile target over
  R = 0 | 50+endHp instead of endHp regression (`train_value_combat.py`
  endHp target; `train_combat_cpsi.py` already uses fraction targets).
  Same GBM architecture, better target — the cheap deployable path.
- **Artifacts:** `build/v_pvnet_fresh.txt`, `build/eval_pvnet_fresh.json`,
  `build/train_pvnet_fresh.log`. Decision log:
  `2026-08-07-value-only-utility-net.md` (appended).

## §132 Target experiment on the GBM leaf: quantile regression on the terminal utility R vs raw endHp — same rows, same model class; EV on-scale (10.1 vs 45.9) (2026-08-07, local)

- **What:** the §131-recommended deployable test: does the target change
  (not the model) transfer to the GBM? Two 9-quantile XGBoost models
  (τ=0.1..0.9, 150 rounds, depth 6, `reg:quantileerror`) on the SAME rows
  as the deployed vnet (`build/vcombat_honest.csv`, 287k rows, same
  GroupShuffleSplit val 0.15/random_state 0), differing only in label:
  utility_R = won ? 50+endHp : 0 vs raw endHp. The R target also cleans the
  493 abandoned-fight rows (loss with endHp>0 in the old target). A 51-class
  softprob port would cost ~50× the trees; 9 quantiles of R is the cheap
  distributional equivalent (low quantiles = death mass, P(win) ≈
  mean(q_τ > 0)).
- **Results (val, 43k rows; deployed model evaluated on the identical rows):**
  | model | EV-MAE vs R | win Brier (from quantiles) |
  |---|---|---:|
  | deployed vnet (endHp regression, 804 trees) | 45.90 | — |
  | quantile endHp (old target, 9×150 trees) | 45.89 | 0.0739 |
  | **quantile utility_R (new target, 9×150 trees)** | **10.10** | 0.0851 |
  - The utility target's mean-of-quantiles is directly on the leaf's terminal
    scale; both endHp variants miss R by ~50·P(win) ≈ 46 — the scale
    mismatch the deployed stack compensates via the α-blend and
    rank-sensitivity (and the §123 HP-scale saga).
  - Win-prob-from-quantiles is slightly worse for the R target (0.085 vs
    0.074) — the endHp quantiles split the 0 boundary marginally better;
    the leaf would use EV (and optionally CVaR) directly, not this coarse
    win estimate.
  - Quantile coverage well calibrated for both (L2 ≈ 0.02).
- **Interpretation:** the §128/§131 finding (direct utility target beats
  the reconstructed target) transfers to the deployable GBM class. The
  deployed vnet's endHp prediction is ≈46 HP off the utility scale; an
  EV-on-scale leaf could allow a higher α (cf. §129: gated model's α
  optimum shifted 0.3→0.5 with better calibration).
- **Next (deployment experiment, not run):** export the 9 quantile tree sets
  in a C++-consumable format + `leafValue` = mean-of-quantiles (± CVaR risk
  term), α sweep, paired 256-seed gate vs the deployed vnet §126 config.
  Tree cost: 9×150 ≈ 1350 trees ≈ 1.7× the deployed 804-tree eval —
  acceptable at the §126 cpu-trade bar.
- **Artifacts:** `build/vcombat_q{,_150}_results.json`, `train_vcombat_quantile.py`.
  Decision log: `2026-08-07-vnet-target-experiment.md`.
## §133 Rollout-leaf estimator experiments A1/A4 (STS_S3_ROLLOUT_K, STS_S3_ROLLOUT_TURN_STOP): implemented opt-in with structural-equality check; gates held for the §131/§132 leaf-net verdict (2026-08-07, local WSL)

- **What:** two opt-in Searcher3 rollout-leaf estimators (plan: A1 + A4 of the
  rollout-ideas session; gates deferred per the split decision until the
  other session's leaf-net verdict lands, because both arms modify the same
  α-blend leaf the new net would redeploy):
  - **A1 (`STS_S3_ROLLOUT_K`, default 1):** run K independent rollouts from
    the same pre-rollout leaf state and average their outcomes; backprop once
    (single visit). Reduces rollout-outcome variance without changing PUCT
    visit counts or tree exploration. `BattleScumSearcher3::multiRollout`
    (`src/sim/search/BattleScumSearcher3.cpp`), used at both rollout sites in
    `step()` (leaf-expansion blend site and the fair-illegal-stored-edge
    fallback). The first rollout's actions go into `actionStack` so
    `bestActionSequence` stays replayable; caller `state` is left unmutated
    (each rollout runs on its own `BattleContext` copy).
  - **A4 (`STS_S3_ROLLOUT_TURN_STOP=N`, default 0):** stop the rollout after
    N completed player turns (turn boundary = `bc.turn` increment inside the
    END_TURN action chain, `BattleContext::afterMonsterTurns`); the
    non-terminal endpoint is then evaluated by the learned leaf, giving
    `α·VNet(s0) + (1−α)·VNet(s1)` — an n-step bootstrap, distinct from the
    §119 capped-rollout gate (which used the pre-vnet heuristic endpoint on
    Searcher2).
- **Verification (local smoke, 8 seeds @300 sims + searchdiag3, 2 seeds
  @300):** structural equality — `STS_S3_ROLLOUT_K=1` reproduces the unset
  arm byte-identically on all 8 seeds (all game columns); behavior fires —
  K=2 rolloutActions ≈ 2.03× control (1,946,275 → 3,952,264; per-leaf
  rollouts independent, 7/8 seeds' outcomes differ); turn-stop=1 collapses
  avgRolloutLen 13.94 → 2.50 (rolloutActions 232,681) and differs on 8/8
  seeds. `ctest` 5/5. Artifacts: `build/rk_{ctl,k1b,k2b,ts1}_8.csv`,
  `build/rk_sd_{ctl,k2b,ts1}.csv`. Banner + BEST-stack provenance:
  `S3-rollK=` / `S3-turnStop=`.
- **Pre-registered gates (pending, GCP):** paired 256-seed @1k/64p on the
  §126 config vs `build/vnet_all_a03_1k.csv` (50.4%): (1) K=2 @500 sims
  (equal rollout-action budget — the deployment question), (2) K=2 @1000 only
  if (1) is positive/neutral (same tree size, ~2× cpu), (3) turn-stop N=1
  @1k (and an equal-CPU reinvestment arm if positive/neutral). Gate ordering
  after the §131/§132 leaf-net verdict: a promoted net re-bases the pairing.
  Decision log: `2026-08-07-rollout-leaf-estimators.md`.
- **Gate verdicts (appended, 2026-08-07, GCP sts-test):** the §131/§132
  quantile-R leaf was **SIGNIFICANTLY NEGATIVE at every α — deployed vnet
  STAYS** (see the second §133 entry), so the pairing baseline is unchanged
  (`build/vnet_all_a03_1k.csv`, 50.4% @1k/64p). Three paired 256-seed gates
  ran (block 126700–126955, full V4 stack, S3−belief−chain/64p, fair, asc 0,
  24 threads, vnet α0.3 default ON):
  | arm | config | win% | Δ vs ctl (95% CI) | floor Δ | HP Δ | cpu-s/run |
  |---|---|---|---:|---:|---:|---:|
  | A1 gate 1 | K=2 @500 sims (equal rollout budget) | 49.2% | −1.2 [−7.4,+5.1] | −0.5 | −4.0 | 16.8 (−59%) |
  | A1 gate 2 | K=2 @1000 sims (equal tree size) | 48.4% | −2.0 [−8.2,+4.7] | −0.1 | −2.3 | 32.4 (−21%) |
  | A4 gate | turn-stop N=1 @1k | 34.0% | **−16.4 [−23.0,−9.4]** | −2.4 [−3.9,−1.0] | −10.9 | 33.6 (−18%) |
  | A1 gate 3 | K=10 @100 sims (equal rollout budget, extreme) | 35.5% | **−14.8 [−21.1,−8.2]** | −3.5 [−5.0,−2.1] | −10.3 | 7.7 (−81%) |
  Discordance 69/256 (27%), 71/256 (28%), 90/256 (35%), 80/256 (31%) respectively.
- **A1 verdict: ❌ NULL — line closed.** Averaged K-rollouts are neutral at
  both operating points (slightly negative direction, CIs span zero): at
  equal rollout-action budget the variance reduction roughly offsets the
  halved tree (−1.2pp), and at equal tree size there is no measurable gain
  (−2.0pp; K=2 also died in 8 more combat fights, 111→119, at −21% wall
  time — fewer decisions per run, consistent with slightly worse play, not
  a speedup from variance reduction). The user-requested extreme point
  K=10 @100 sims (equal rollout budget, 10× smaller tree) is
  **SIGNIFICANTLY NEGATIVE: −14.8pp (CI [−21.1,−8.2])** — tree size
  dominates: reducing the search tree 10× while holding rollout work
  constant collapses win rate, so the α0.3 blend's 70% rollout share is not
  variance-bound at this operating point and variance reduction does not
  pay for lost tree traversals at any tested ratio. Pre-registered K=4 not
  run (only if K=2 positive). Env stays opt-in.
- **A4 verdict: ❌ FALSIFIED — line closed.** One turn + VNet bootstrap is
  significantly worse than the full terminal rollout: −16.4pp (CI excludes
  zero), floor −2.4 (CI excludes zero), HP −10.9, and cpu barely drops
  (−18% — the endpoint vnet evals dominate, not the skipped rollout
  actions). This is the second falsification of the short-rollout family
  (§119 caps −5.9pp with the pre-vnet heuristic endpoint; this is worse
  because the rollout here is ~1 turn long, avgRolloutLen 2.50 in the
  local smoke, vs §119's 8-action caps). Long-horizon terminal grounding
  through the full rollout is load-bearing for the leaf blend; per the
  pre-registered decision tree, B1 (turn-beam) must continue across turns.
  Env stays opt-in.

## §133 Quantile-R GBM leaf (target experiment, §132 deployment gate): SIGNIFICANTLY NEGATIVE at every α — deployed vnet stays; offline EV calibration does not transfer (2026-08-07, GCP)

- **What:** the §132-recommended deployment gate for the quantile-R GBM
  leaf: `combat_quantile_v1` native format (9 tree sets, τ=0.1..0.9, 150
  rounds, depth 6, over R = won ? 50+endHp : 0), C++ loader +
  `predictQuantileEV` (mean of quantiles, on the terminal scale; dispatch in
  `CombatValueNet::predictVec`, so no searcher changes), parity PASS vs
  Python (max diff 0.0005, `vnettest` on 1999 val rows). Trained on the same
  rows as the deployed vnet (`build/vcombat_honest.csv`); val EV-MAE vs R
  10.10, quantile coverage L2 0.022 (vs 45.90 for the deployed endHp model).
- **Gates (256 seeds, block 126700, full V4 stack, S3−belief−chain/64p,
  paired vs the §126 deployed-vnet control `build/vnet_all_a03_1k.csv`,
  50.4% — reproduced twice on this block, §124c/§127):**
  | arm | win% | Δ (95% CI) | floor Δ | HP Δ | cpu-s/run |
  |---|---|---:|---:|---:|---:|
  | quantile-R α0.3 | 37.5% | −12.9pp [−19.9, −6.2] | −2.4 | −5.5 | 68.5 |
  | quantile-R α0.5 | 40.2% | −10.2pp [−17.2, −3.1] | −3.4 | −6.0 | 85.6 |
  | quantile-R α0.7 | 32.0% | −18.4pp [−25.4, −11.3] | −3.7 | −11.0 | 80.9 |
  All three SIGNIFICANTLY negative, at 1.7-2× the deployed cpu
  (41.2 s/run). The α curve is inverted vs §129's gated model (which
  improved with α 0.3→0.5): here higher α is worse — the EV-on-scale
  leaf's in-tree ranking is worse than the deployed endHp model's, and
  heavier blending makes it worse.
- **Verdict: ❌ line closed; the deployed honest-data vnet (§126)
  STAYS.** The §132 offline finding (EV-MAE 10.1 vs 45.9) does not
  transfer — the third consecutive offline≠online falsification
  (§124c prior-guided rollouts, §127 prior v2, now the target
  experiment). Hypothesis: the deployed endHp model's under-scaled value
  blended at α0.3 acts as a ranking-friendly prior over the rollout's
  terminal scale; the "correctly scaled" EV value is not better at ranking
  tree states, and the mean-of-9-quantiles estimator is crude for the
  bimodal R distribution (90% wins). The transformer 51-bin CE model
  (§128/§131) remains the best offline value signal but has no
  deployable GBM port yet; the §126 vnet-retrain line (data side) stays
  as recorded.
- **Artifacts:** `build/v_combat_quantile.txt` (kept as reference), gate CSVs
  `build/vq_{a03,a05,a07}_256.csv`, logs on sts-test, parity
  `/tmp/vq_parity.csv`. Code: `CombatValueNet::load`/`predictQuantileEV`
  (`src/sim/search/CombatValueNet.{h,cpp}`), `combat_quantile_v1` exporter
  `train_export_vcombat_quantile.py`. Decision log:
  `2026-08-07-vnet-target-experiment.md` (verdict appended).

## §134 Audit of §132/§133 + faithful target-only ablation on the direct utility-R GBM: §132 was NOT a target-only test; a same-recipe direct-R model is ALSO SIGNIFICANTLY NEGATIVE at α0.1 — deployed vnet stays; tooling hardened (2026-08-07, local)

- **What:** a methodological audit of the §132/§133 records (user-requested),
  tooling hardening, and one narrowly scoped follow-up that tests the §132
  target hypothesis without its confounds. The §133 deployment verdict is
  preserved; §132's offline narrative is corrected by this addendum (historical
  rows above are NOT silently rewritten).
- **§132 audit (confounds found):** §132 claimed "same rows, same model class —
  differing only in label". That is not what was implemented:
  `train_vcombat_quantile.py` / `train_export_vcombat_quantile.py` replaced the
  deployed recipe (`train_value_combat.py`, depth 8, eta 0.05,
  early-stopping up to 1500 rounds, weighted squared error, 804 exported
  trees) with nine unweighted `reg:quantileerror` models (depth 6, eta 0.1,
  fixed 150 rounds, 1350 trees). So the §132 comparison confounded target
  with recipe/capacity/objective-class. The headline "EV on-scale (10.1 vs
  45.9)" is also partly a scale artifact: an end-HP predictor is ~50·P(win) ≈
  46 off the R = 0 | 50+endHp scale by construction, so its MAE vs R is a
  scale mismatch, not evidence it ranks search states worse. The
  mean-of-9-quantiles is a coarse numerical approximation of the expectation,
  especially for the bimodal R distribution. None of this invalidates the
  §133 online gate — the quantile leaf was rejected on paired gameplay, which
  is independent of the offline EV-MAE framing.
- **§133 audit (verdict preserved, wording scoped):** the quantile deployment
  gate itself is decisive for the implemented candidate: native/Python parity
  was checked, the fair Searcher3 config matched the §126 control, and the
  recorded α values were all significantly negative. The claim "every α" is
  scoped to **the three tested α (0.3, 0.5, 0.7)** — not a statement about all
  possible α. The A1 rollout verdict is also narrower than the §133 text
  implied: `BattleScumSearcher3::multiRollout` copies one `BattleContext`
  (including all simulator RNG streams) for every replicate, so the K rollouts
  are independent action-policy samples conditional on **copied simulator
  RNG**, NOT fully independent environment samples; the null verdict applies
  to this correlated same-leaf estimator, not to variance-reduction schemes in
  general.
- **Tooling hardening (same change):**
  - `paired_analysis.py` is now strict and deterministic: pairing is by seed
    only, duplicate seeds or unequal seed sets are hard errors, bootstrap CIs
    use one fixed-seed NumPy generator per report (repeated analysis of the
    same inputs → identical intervals), and `--allow-partial` is an explicit
    diagnostic-only escape with a loud warning (never a promotion gate).
    Self-test `python3 paired_analysis.py --self-test`; registered as CTest
    `paired_analysis_selftest` (`CMakeLists.txt`).
  - `one_combat vnettest` is now an asserting parity check: it validates that
    the model and CSV open, that the header is exactly the canonical combat
    features followed by `pyPred`, rejects empty/malformed/short/extra-column
    rows, requires every feature and `pyPred` cell to be a complete finite
    numeric token (no trailing junk, no NaN/Inf — previously `std::stof`/
    `std::stod` accepted trailing junk and a NaN `pyPred` silently compared as
    in-tolerance), rejects a feature whose value overflows the native float
    feature vector (finite doubles beyond float range become Inf on
    conversion), rejects a non-finite native prediction or prediction
    difference (a malformed model can predict Inf/NaN; `std::max` ignores NaN
    so the row previously compared as in-tolerance and printed PASS), rejects
    a non-finite or negative tolerance argument, takes
    an absolute tolerance (default 0.001), and returns nonzero when
    max|diff| exceeds it. Regression coverage:
    `vnettest_selftest.py --self-test` (CTest `vnettest_selftest`,
    `CMakeLists.txt`) asserts a non-finite native prediction (MLP whose finite
    tokens overflow float in the hidden layer), a float-overflow feature, and
    out-of-tolerance evidence all exit nonzero while clean finite parity
    evidence exits 0.
  - `bestbench` mode staleness guard (issue 46 producer side): the first
    verification round's strict analysis rejected the gate CSV because
    `bestbench` had appended the same 256-row block twice (append-without-dedup
    trap). The `bestbench` mode handler in `apps/one_combat.cpp::main` now
    exits nonzero with a clear message when the results file already contains
    any requested seed, instead of silently doubling rows; disjoint batch
    appends (self-play gates) are unaffected, and the stale CSV was deleted so
    the verification gate regenerates it cleanly.
  - `train_value_combat.py` gained an opt-in target selector:
    `VCOMBAT_TARGET=endhp|utility_r` (default `endhp` — unset behavior trains
    the identical end-HP objective as before) and `VCOMBAT_WIN_BONUS`
    (default 50); `utility_r` labels R = 0 on a loss (even an abandoned fight
    with positive current HP) and win_bonus+endHp on a win. Rows, fight-group
    split, critical-state weights, feature filtering, XGBoost parameters,
    early stopping, and device selection are identical between targets; the
    trainer now reports val RMSE/MAE against BOTH endHp and utility R and
    writes a sidecar `<model>_metrics.json` (target semantics, win bonus,
    row/fight counts, split seed, features, params, best iteration, metrics).
- **Faithful target-only ablation (the corrected §132 test):** two fresh
  models trained on the same 287,517-row / 16,337-fight
  `build/vcombat_honest.csv` artifact with the identical canonical recipe,
  differing ONLY in the label, same device (CUDA) and package environment:
  | model | target | trees exported | val RMSE vs endHp | val MAE vs endHp | val RMSE vs R | val MAE vs R | best_iter |
  |---|---|---|---:|---:|---:|---:|---:|
  | `build/v_combat_control_endhp.txt` | endHp | 1500 | 7.88 | 5.58 | 48.59 | 45.82 | 1479 |
  | `build/v_combat_utility_direct.txt` | utility R | 611 | 45.87 | 43.58 | 15.35 | 9.73 | 570 |
  The control is the same-recipe end-HP arm (val RMSE 7.88 vs the recorded
  7.99 for the deployed §126 model — the small delta is consistent with
  CUDA-vs-GCP-device tree differences; sha256 of the deployed
  `v_combat_honest.txt` is `e69d64cf…`). The utility-R model fits R (MAE 9.73
  vs the quantile-R's 10.10 on the same rows — the two are comparable now,
  same recipe family, no 50·P(win) scale gap). Offline metrics are
  diagnostics only — the dataset is on-policy trajectory states, so
  regression error does not establish MCTS action-ranking quality.
- **Native parity:** `export_combat_model.py` (standard `nfeat` single-ensemble
  format; quantile aggregation is NOT part of this ablation) →
  `build/v_combat_utility_direct.txt` (sha256 `a81404b5…`),
  `build/v_combat_control_endhp.txt` (sha256 `9c1b6061…`); asserting
  `one_combat vnettest` PASSES for both (max|diff| 1.2e-4 / 1.6e-4 vs tol
  0.001, 200 val rows each). Both arms were trained/exported/parity-checked in
  the same local CUDA environment and package set; the fresh end-HP control
  retrain is deterministic (same `best_iter` 1479, same val RMSE 7.88, same
  exported-tree sha256 `9c1b6061…` as the first run), and the sidecars
  (`v_combat_control_endhp_metrics.json` vs
  `v_combat_utility_direct_metrics.json`) confirm identical rows (287,517),
  fights (16,337), split (GroupShuffleSplit test_size 0.15 random_state 0),
  feature list, XGBoost params (depth 8, eta 0.05, subsample 0.8,
  colsample 0.7, min_child_weight 20, max_bin 256), 1500 boost rounds, early
  stopping 40, and device (cuda) — the label is the only recipe difference.
- **Gate (pre-registered α0.1 first, because R is on the larger terminal
  scale):** 256 paired seeds, block 126700–126955 (exactly the §126 control's
  seeds), full V4 gate stack, `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, vnet =
  `STS_VNET=build/v_combat_utility_direct.txt STS_VNET_ALPHA=0.1`, asc 0,
  1000 sims, native OOC ON. Startup banner printed `[V_combat leaf value ON:
  build/v_combat_utility_direct.txt, 611 trees, alpha 0.1]` (candidate
  observed loaded and used). Strict paired analysis
  (`python3 paired_analysis.py build/vnet_all_a03_1k.csv
  build/v_combat_utility_direct_a01_256.csv deployed utility-direct-a01`):
  | metric | deployed (§126 control) | utility-direct α0.1 | Δ (95% CI) |
  |---|---|---:|---:|
  | win% | 50.4% | **38.3%** | **−12.1pp [−18.8, −5.1]** |
  | avg floor | 44.1 | 41.1 | −3.0 [−4.5, −1.4] |
  | avg HP end | 29.4 | 24.3 | −5.0 |
  Discordant 83/256 (32%), deployed-only 57 vs candidate-only 26. Local
  cpu_sec/run 17.5 (12 threads, 379 s wall); cpu figures are machine-dependent
  and the independent verification re-run provides the authoritative cpu
  comparison.
- **Verdict: ❌ line closed — the direct utility-R GBM is SIGNIFICANTLY
  NEGATIVE at its pre-registered first operating point α0.1 (95% CI excludes
  zero below).** Per the pre-registered rule, α0.3 is NOT tested and the
  deployed `build/v_combat_honest.txt` STAYS. The §132 hypothesis
  (same-model-class target change transfers online) is therefore falsified
  even when the recipe is held fixed and the label is fit directly — the
  fourth consecutive offline≠online falsification (§124c, §127, §133
  quantile, now §134). Combined with §133's α curve (heavier blending worse),
  the evidence says the deployed endHp leaf's ranking behavior is not
  reproduced by a correctly scaled R-expectation leaf at any tested blend.
  No promotion; no alpha-0.3 test; no disjoint-block confirmation run (only
  required if the first gate had been non-negative).
- **Recording notes:** the §133 revalidation under the strict analyzer
  reproduces the recorded point estimates exactly on all three recorded α
  values, each on the exact 256-seed block 126700–126955 (identical seed sets
  on both sides, no duplicates): quantile α0.3 50.4% vs 37.5% (−12.9pp),
  α0.5 50.4% vs 40.2% (−10.2pp), α0.7 50.4% vs 32.0% (−18.4pp). CI bounds
  differ slightly from the originally recorded unseeded bootstrap (e.g. α0.3
  upper bound −6.2 → −5.9, α0.7 upper bound −11.3 → −10.9) because the
  bootstrap is now deterministic. The B1 'beam' idea in
  `docs/knowledge-base/plan-rollout-experiments-2026-08-07.md` was NOT
  implemented: as written it simultaneously requires beam pruning and forbids
  scoring partial beam states, which is not a complete algorithm; it needs a
  revised spec before any implementation.
- **Artifacts (ignored build outputs, not promoted):**
  `build/v_combat_utility_direct.{json,txt,val.csv,_metrics.json}`,
  `build/v_combat_control_endhp.{json,txt,val.csv,_metrics.json}`,
  train logs `/tmp/opencode/train_utility_direct.log`,
  `/tmp/opencode/train_control_endhp.log`, local gate CSV
  `/tmp/opencode/utility_direct_a01_256_local.csv`; the verification-run gate
  CSV `build/v_combat_utility_direct_a01_256.csv` is produced by the
  orchestrator's independent run. Code: `train_value_combat.py`
  (VCOMBAT_TARGET/VCOMBAT_WIN_BONUS), `export_combat_model.py`,
  `apps/one_combat.cpp::main` (vnettest), `paired_analysis.py`. Decision log:
  `2026-08-07-experiment-132-133-audit.md`.

## §135 Leaf-state diagnostic infrastructure: measure the §126-vs-§134 gap on actual Searcher3 leaf states (2026-08-08, local — infrastructure only, no gameplay result)

- **What:** the handover cycle's diagnostics for "why does the deployed end-HP
  vnet beat the direct utility-R vnet online (§126 +12.1pp vs §134 −12.1pp)
  despite fitting its target worse offline (val MAE 9.73 vs 45.82)". This
  entry records the TOOLING, not a verdict — the task explicitly forbids a new
  model before the diagnostics exist. The measurement cycle runs next; its
  results will be appended here.
- **Implemented:**
  - `search::g_onS3LeafQuery` / `S3LeafDiagnostic` (thread_local, nullptr by
    default) fire at the Searcher3 leaf-expansion blend site in
    `BattleScumSearcher3::step` — the states the learned leaf actually scores.
    The leaf identity is the leaf state's own `visibleHash` (computed inside
    the hook guard; `cur->obsHash` would be the PARENT's, which predates the
    committed action). Defaults byte-identical when unset.
  - `one_combat leafdiag NSEEDS SIMS ASC OUTFILE [SEEDOFFSET]`: per-stratum
    reservoir (10 strata: 3 HP bands × 3 difficulties + 1 deep-tree;
    `STS_LEAFDIAG_PER_STRATUM` default 50/seed, `STS_LEAFDIAG_DEEP_DEPTH`
    default 20) of leaf states with canonical combat features + deployed
    end-HP prediction + `STS_DIAG_VNET2` secondary prediction (never read by
    the search) + raw/blended rollout evals + provenance + per-fight labels.
    Sampling deterministic per seed (row SET reproducible; row order follows
    seed completion order like fairGen).
  - `one_combat leafref INFILE OUTFILE HIGH_BUDGET_SIMS NSEEDSREF ASC
    [REPLAY_SIMS]`: deterministic replay of the recorded decisions; the
    regenerated leaves match the recorded ones by obsHash (smoke: 450/450);
    each recorded leaf gets a FRESH high-budget Searcher3 root mean evaluation
    with per-group CRN reseeding (rng+belief+particles from one group seed).
    Reference value = `root.evaluationSum/simulationCount` — documented as an
    approximation (`referenceValue`), never ground truth. The per-group CRN
    reseeding gives PARTIALLY shared determinization draws only (the
    belief/particle shuffle prefix consumes a state-dependent number of RNG
    draws, so the streams diverge after the prefix). The reference search runs
    with the same learned-leaf environment as the leafdiag run (deployed
    `STS_VNET` @ configured alpha), so the reference is NOT model-free — run
    the sensitivity checks (rank vs `rawRolloutEval`, or a leafref run with
    `STS_VNET` pointed at a missing path) before drawing the central verdict.
    Replay config (particles, `STS_VNET`+alpha, OOC env arms, ascension) must
    match the leafdiag run; a mismatch shows as a re-capture WARNING.
  - `one_combat rollouttrace INFILE OUTFILE NSEEDSREF ASC [REPLAY_SIMS]`:
    actual search-policy rollout state sequences per recorded leaf
    (`search::g_onRolloutStep` fires inside `playoutRandom` after every
    executed action); same config-match requirement as leafref.
  - leafdiag CSV provenance carries the encounter as its UPPER_CASE enum NAME
    (`encounterName` column); numeric `encounter`/`turn` encodings live in the
    canonical feature block only (no duplicate columns). The 10 capture strata
    have no dedicated disagreement/close-decision stratum (raw |endHp − utilityR|
    is dominated by the +50-on-win scale offset); disagreement is stratified
    post-hoc in `tools/leaf_ranking.py`.
  - Analysis: `tools/leaf_ranking.py` (within-group pairwise ranking
    accuracy / top-1 / regret / MAE-RMSE-Pearson-Spearman / stratified,
    deterministic bootstrap CIs, `--self-test` works under `python3 -I`),
    `tools/leaf_distribution_shift.py` (per-feature KS + held-out logistic
    classifier combatgen-vs-search-leaf, ROC-AUC, `--write-ood`),
    `tools/leaf_split_check.py` (fight-level vs seed-level validation split
    for both targets, §134 recipe), `tools/leaf_smoothness.py` (delta-V
    smoothness/shaping per model).
- **Local smoke validation (not evidence of any gameplay effect):**
  - `leafdiag 4 300 0` (STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
    STS_S3_CHAIN=0 STS_S3_PARTICLES=32, STS_VNET=build/v_combat_honest.txt,
    STS_DIAG_VNET2=build/v_combat_utility_direct.txt): 1755 rows, 1783 cols
    (13 provenance + 1766 features + 4 model/rollout cols); identical row SET
    across reruns.
  - `bestbench 1000 8 0 0` twice (deployed default): game-outcome columns
    byte-identical (cpu_sec is wall-time and varies) — default behavior
    unchanged.
  - `leafref` (high-budget 400, replay 300): 450/450 recorded leaves
    regenerated and matched by obsHash; join to leafdiag keys 1:1.
  - `rollouttrace`: 450 trajectories × ~9.3 steps with both predictions.
  - `tools/*.py` self-tests pass; CTest 8/8; `vnettest` parity on the §134
    direct-R model passes.
  - 16-seed leafdiag smoke: `leafdiag 16 1000 0 build/leafdiag_16.csv` →
    7590 rows.
- **Known constraint:** the leafdiag/leafref/rollouttrace run distribution is
  the heuristic-OOC (native floor/win) run distribution unless the V4 gate
  env arms are also set — the recorded §126/§134 gates used the full V4 gate
  stack, so a gate-matching diagnostic dataset must set the same OOC env arms.
  Probing OOC arms (STS_OOC_ACTION_NN, STS_BOSS_DRAFT, M1/M2, STS_DATAGEN_GATES)
  MUST NOT be enabled during capture (their inner probe battles pollute the
  dataset).
- **Verdict: NONE (infrastructure only).** No model change, no default change,
  no promotion; the deployed `build/v_combat_honest.txt` @α0.3 stays, and
  §133/§134 candidates stay rejected. Next step: run the diagnostics on a
  gate-sized dataset and record the hypothesis verdict here.
- **Decision log:** `2026-08-08-leaf-state-diagnostics.md`.

## §135a Leaf-state diagnostics: gate-matching measurement (2026-08-08, local — diagnostic evidence, no gameplay promotion)

- **Dataset:** 64 seeds (126700–126763), 1000 sims, asc 0, 12 threads, local
  (no GCP). Full gate-matching env: `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
  `STS_VNET=build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3` (deployed §126
  regime), `STS_DIAG_VNET2=build/v_combat_utility_direct.txt` (§134 direct-R,
  diagnostics only), `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC gate arms
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, MARGIN=1.0). Probing OOC arms OFF.
- **Artifacts (build/, git-ignored):** `leafdiag_gate_64.csv` (288,537 leaf
  rows, 142s), `leafref_gate_64_4k.csv` (287,211 reference rows, high-budget
  4000 sims × 128 particles, per-group CRN reseeding, replay 1000 — matched
  100%, no re-capture WARNINGs, 3367s), `rollouttrace_gate_64.csv` (3,341,845
  rows, 150s), `leafdiag_gate_64_ood.csv`, JSON summaries
  `leaf_ranking_gate_64{,_ood,_rawrollout}.json`,
  `leaf_distribution_shift_gate_64.json`, `leaf_split_check_gate_64.json`,
  `leaf_smoothness_gate_64.json`.
- **Ranking vs high-budget reference (Task 3; reference is vnet-influenced,
  see caveat):** endHp Pearson 0.758 / Spearman 0.769 / MAE 31.2 vs utilityR
  Pearson 0.806 / Spearman 0.820 / MAE 21.5 (own scales, not comparable
  directly — utilityR fits the reference better in correlation). Within-group
  pairwise accuracy: **endHp 0.719 [0.717,0.722] vs utilityR 0.711
  [0.708,0.714]** (+0.8pp, CIs disjoint); top-1: 0.359 vs 0.336 (+2.3pp);
  regret 7.253 [7.076,7.424] vs 7.597 [7.419,7.768]. Disagree-high stratum
  (|Δ| ≥ 50): 0.734 vs 0.720. Deep-tree stratum (d≥15): 0.798 vs 0.779.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref):** pairwise 0.725 [0.722,0.728] vs 0.719 [0.715,0.722], top-1 0.333
  vs 0.316, regret 14.50 vs 15.16 — same direction, so the endHp ranking
  advantage is NOT an artifact of the vnet-influenced reference.
- **Distribution shift (Task 4):** held-out logistic classifier
  combatgen-vs-search-leaf: **ROC-AUC 0.9998** (60k×60k rows, test ~1/3) —
  near-perfect separation; the search-leaf regime is essentially entirely
  outside the `vcombat_honest.csv` training distribution (OOD flagging: only
  37 decision groups classified in-dist, 3046 OOD, rest na). Top separating
  features by standardized |coef| (correlation, NOT causal): r116 (+4.87),
  maxHp (+2.74), gold (+2.07), nSklAvail (−1.92), dr25 (+1.88), ds25 (+1.87).
- **Split-sensitivity (Task 5):** fight-split vs seed-split diagnostic
  retrains (canonical §134 recipe): endhp val MAE 5.581 → 5.536 (−0.045);
  utility_r 9.730 → 9.173 (−0.557). The fight-level split is NOT optimistic —
  seed-level validation is, if anything, slightly easier for the deployed
  models (deployed endHp val MAE 5.589 fight vs 3.930 seed). The offline
  story was not inflated by same-run fight leakage.
- **Smoothness/shaping (Task 6):** endHp lag-1 autocorrelation 0.549 vs
  utilityR 0.502 (endHp smoother); near-death steps: endHp mean ΔV −1.094 /
  std 3.227 vs utilityR −2.457 / 8.571; but utilityR is MORE sign-consistent
  on raw surface progress (progSign 0.459 vs 0.432, negOnHpLoss 0.247 vs
  0.221, strUp 0.442 vs 0.416). Shaping evidence is MIXED — smoothness yes,
  sign-consistency no.
- **Verdict (diagnostic, not causal):** the dominant, unambiguous finding is
  massive train-vs-search covariate shift (AUC 0.9998). Within the OOD
  search-leaf regime the deployed endHp model ranks slightly better (pairwise
  +0.8pp, top-1 +2.3pp, regret −0.34) despite correlating worse with the
  high-budget reference (Spearman 0.769 vs 0.820). The online gap (−12.1pp) is
  far larger than any measured ranking difference (≤2.3pp top-1), so the
  ranking hypothesis alone cannot explain the §134 collapse; covariate shift
  (or its interaction with the blend scale) is the primary suspect. Next
  experiment (per the handover decision point, covariate-shift branch):
  retrain the existing model class on a mixture of combatgen + actual
  leafdiag states with SEPARATE on-policy and search-leaf holdouts, and test
  search-leaf ranking improvement before any gameplay gate.
- **Caveats:** the leafref reference searcher itself used the deployed endHp
  leaf (vnet-influenced reference) — mitigated by the rawRolloutEval
  cross-check above; OOD in-dist groups are few (n=37) so the ood=id stratum
  is anecdotal; delta-V scales differ across models (only scale-free
  comparisons valid); classifier feature weights are correlational.
- **Decision log:** `2026-08-08-leaf-state-diagnostics.md` (results
  addendum).

## §135b B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT): implemented opt-in with structural-equality check; paired 256-seed gate PENDING (2026-08-08, local WSL)

- **What:** the B1 line from `plan-rollout-experiments-2026-08-07.md` §2
  (user-approved scorer-(b) design; the §134 audit flagged the original B1
  spec as incomplete — pruning needs intermediate scores — so the revised
  spec scores COMPLETE turns only and prunes between turns by first-N
  truncation). At PLAYER_NORMAL states during the Searcher3 rollout, the
  per-action weighted random pick is replaced by a deterministic beam search
  over card/potion sequences to END_TURN; the best-scored complete turn is
  executed and the rollout continues to the next hand (multi-turn
  continuation is mandatory per the A4 falsification, §133).
- **Implementation:**
  - `turnBeamSearch` (file-scope static, `src/sim/search/
    BattleScumSearcher3.cpp`): BFS to END_TURN, depth = hand size (≤10),
    width `STS_S3_TURN_BEAM_WIDTH` (default 8), pruned between depths by
    first-N truncation (deterministic enumeration order, no intermediate
    scoring). Every beam state spawns an END_TURN candidate scored after the
    monster turn resolves on a copy (common-random-numbers for free).
    CARD_SELECT-producing sequences are dropped; lethal sequences captured as
    +1000 candidates; `turnBeamSearch` never returns empty (depth-0 END_TURN
    candidate).
  - `scoreCompleteTurn(pre, post, powersPlayed, potionsUsed)`:
    `S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
    − w5·potion_use`; ΔHP_player = effective (HP+block) loss clamped ≥0;
    setup = strength+dex+focus deltas + powers played; terminal outcomes
    ±1000. Weights `STS_S3_TURN_SCORE_W1..W5` defaults
    1.0/1.0/50.0/10.0/30.0 (educated guesses, pre-registered). Hand-authored
    rollout heuristic (same class as `rolloutWeight`), NOT a learning
    objective.
  - `playoutRandom` branch (gated `g_s3TurnRollout &&
    inputState == PLAYER_NORMAL`): executes the best sequence, fires
    `g_onRolloutStep` after each action, honors `g_s3RolloutTurnStop` (A4)
    after the beam's END_TURN. Non-PLAYER_NORMAL states keep the weighted
    pick; unset/`=0` is byte-identical pre-B1.
  - Env parsed in `apps/one_combat.cpp::main`; BEST stack banner prints
    `S3-turnBeam=ON/off` (only in the Searcher3 arm of the banner).
- **Local smoke (2026-08-08):**
  - Structural equality: `bestbench 300 8 0 126700` with `STS_FAIR=1
    STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
    unset vs `STS_S3_TURN_ROLLOUT=0` → per-seed game-outcome columns
    (won/floor/act/hpEnd/maxHp/fightsLost/deathCombat/deathEncounter)
    identical (only the wall-time `sec` column varies); logs identical
    modulo cpu.
  - Turn-beam smoke: same config + `STS_S3_TURN_ROLLOUT=1
    STS_S3_TURN_BEAM_WIDTH=8` → runs to completion on 8 seeds @300 sims, no
    crash/hang/assert (win 25.0% vs control 37.5% on 8 seeds — NOT
    evidence, smoke only). Cost ~16× control at 300 sims (55.9 vs 3.45
    cpu-sec/run) — the beam's CPU cost is the known B1 risk; B1c (VNet on
    the final 2–4 beam survivors) is parked for that contingency.
  - `ctest` 8/8 pass; `git diff --check` clean.
- **Gate (DONE 2026-08-08, GCP sts-test):** paired 256-seed @1k/64p, block
  126700–126955, asc 0, 24 threads, full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), vnet default ON α0.3,
  vs the §126 control `build/vnet_all_a03_1k.csv` (50.4%):
  `bestbench 1000 256 0 126700 build/b1_turn_beam_1k_256.csv` with
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64 STS_S3_TURN_ROLLOUT=1 STS_S3_TURN_BEAM_WIDTH=8`;
  analysis `paired_analysis.py build/vnet_all_a03_1k.csv
  build/b1_turn_beam_1k_256.csv ctl cand`; banner confirmed
  `S3-turnBeam=ON` + `[S3 turn-beam rollout ON: width=8 scorer
  w1..w5=1/1/50/10/30]` + vnet default load.
- **Gate result (paired_analysis.py, 256 seeds):**
  | metric | control (§126 vnet) | turn-beam B1 | delta |
  |---|---|---:|---:|
  | win | **50.4%** (129/256) | **46.9%** (120/256) | **−3.5pp, 95% CI [−10.2, +3.1]** |
  | avg floor | 44.1 | 43.9 | −0.1 (CI [−1.3, +1.1]) |
  | avg HP end | 29.4 | 25.3 | −4.0 |
  | cpu-s/run | 41.17 | 383.45 | +9.3× |
  Discordant 75/256 (29%): ctl-only 42, cand-only 33. Wall 4523.7 s
  (75.4 min). Artifacts: `build/b1_turn_beam_1k_256.csv` (md5
  6028f837224b845e63254d91062f767f), server log
  `build/b1_turn_beam_1k_256.log` on sts-test.
- **Verdict: ❌ null (not significant), line parked.** −3.5pp with CI crossing
  zero and no floor/HP benefit at 9.3× CPU closes the B1 hand-authored-scorer
  design (the decision log pre-registered the gate as arbiter; risk list
  included mis-ranking and lower-index bias). No default change; env stays
  opt-in default-off. B1c (VNet on final 2–4 beam survivors) is NOT unlocked
  — the cost contingency was premised on a positive signal; a VNet-scored
  beam would only add cost. A2 (dynamic α by rollout length) conditions on
  the L distribution B1 reshapes — with B1 parked, run A2 only if a
  lightweight rollout-shape diagnostic shows the premise still holds.
- **Decision log:** `2026-08-08-turn-beam-rollout.md`.

## §136 Self-play relabeling (5.7.3, handoff plan `plan-selfplay-relabeling-2026-08-07.md`): Phase-0 verification smoke — full S3+vnet datagen stack verified, schema/labels OK, trainer/export chain OK; Phases 1–3 (GCP datagen, GPU training, paired gate) PENDING manual follow-up (2026-08-08, local WSL)

- **What:** Phase 0 of the 5.7.3 handoff plan — verify (a) the
  `strategicgen2` Tier-B label producer runs with the CURRENT deployed combat
  controller (fair S3−belief−chain + live-valid + the §126 vnet default) and
  emits the trainer-consumable schema, and (b) the `train_strategic_tok.py` →
  `export_strategic_tok.py` chain works end-to-end before the 1,500-seed GCP
  datagen. **No C++ code changes** (verified: `strategicgen2` main-run OOC and
  branch continuation are heuristic by design — `apps/one_combat.cpp`
  `runStrategicGenSeed2`/`finishOocCounterfactual`; branch battles use the
  configured searcher, so the §5 envs alone select the deployed controller).
- **Provenance (Phase 0):** local WSL (12 threads), HEAD 2e6f894,
  `./build/one_combat strategicgen2 10 1000 0 build/sp_smoke_phase0.csv
  300000` with `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1` (branch defaults: `STRATEGIC_BRANCH_FIGHTS=3`,
  `STRATEGIC_BRANCH_SIMS=150,100,50`, `STRATEGIC_BRANCH_FUTURES=1`);
  seeds 300000–300009 (fresh range, no overlap with recorded ranges).
- **Verified banner (startup, no vnet warning):** `[Searcher3 engine ON]`,
  `[live-valid edge re-selection ON (fair S3 default, §123)]`,
  `[S3 ablation: belief=off]`, `[S3 ablation: chain=off]`,
  `[V_combat leaf default ON: build/v_combat_honest.txt, 804 trees, alpha 0.3
  (fair S3, §126)]`; **no** `[strategicgen2 WARNING: STS_VNET not loaded]`
  (the `!search::g_useVNet` guard, apps/one_combat.cpp:7454). The S3-abl
  banner (`S3-abl[b,p,c,l,crn]=01010`) is a bestbench banner; for
  `strategicgen2` the per-flag ablation lines above are the equivalent
  evidence.
- **Schema (validated with pandas):** 1017 state columns between `chosen`
  and `won` (exact `richRow` contract the trainer validates); last 4 columns
  exactly `labelWon,labelHp,labelFloor,labelBootstrap`. Rows: **6,244 total
  / 10 seeds = 380–771 rows/seed (mean 624)** — consistent with the §104
  scale estimate (~809k rows / 1,295 seeds). `STRATEGIC_SAMPLE_ALL=1` →
  **100% labelWon coverage** (6,244/6,244), spread 0..1 with 2,363 distinct
  values (real variance, not constant).
- **Preliminary label diagnostic (smoke-scale only, NOT a gate — 10 seeds,
  §104-style filter: groups with ≥2 finite labels AND exactly one chosen
  row): argmax(labelWon) vs `chosen` agreement 34.1% strict / 46.0% in-set**
  (1,055 valid groups; in-set = chosen inside the tied argmax set), with
  per-screen spread matching the old-corpus pattern (EVENT 41.4/50.0 n=58,
  MAP 51.9/56.3 n=158, REST 50.0/59.7 n=72, REWARDS 29.5/45.1 n=628, SHOP
  15.7/15.7 n=51; TREASURE/CARD_SELECT/BOSS_RELIC omitted, n<50). The old
  corpus read 38.0% strict / 58.1% in-set (§104); the smoke numbers are
  consistent, so the new labels behave like the old ones. (A 37.2% strict
  figure recorded earlier the same day came from an experimental
  deferred-branch parallelization that was reverted — see the second-pass
  follow-up below; the numbers here are from the exact serial path the GCP
  datagen will use.) Recompute on the full 1,500-seed set per the plan (§5
  Step-1 diagnostic); informative, not a gate.
- **Trainer/export chain (Phase 0c):** 2-epoch CPU slice of the smoke CSV
  (`STRAT_DEVICE=cpu STRAT_EPOCHS=2`, rung 4, 6,244 rows / 10 seeds / 1,555
  decisions, **1,554 groups with exactly one chosen row, all with a valid
  policy action** — the policy-target head is exercised: policy_top1
  0.44→0.42, q_top1 ~0.20, val_pol_ce 1.5204) → `build/tok_smoke.pt.pt` +
  `_metrics.json`; export with `export_strategic_tok.py build/tok_smoke.pt
  build/ooc_strategic_tok_smoke.native` → **32 numpy-vs-PyTorch parity checks
  passed** (max err logit 3.87e-08, value 8.92e-08, Q 1.66e-07); the
  exported native loads in `one_combat` (`[OOC one-ply strategic TOK net ON:
  card rewards gated at margin 1]` with the full gate stack + vnet default +
  `S3-abl[...]=01010` at 64p on a 2-seed @100-sim bestbench smoke). The
  smoke .native lives under ignored `build/` — it is NOT a candidate artifact
  and must not be committed to `selfplay/models/` (2-epoch CPU checkpoint,
  rung 4 default topology).
- **Discrepancies found (plan-vs-repo, recorded for the follow-up session):**
  (1) `train_strategic_tok.py` writes `OUT + ".pt"`, so `export_strategic_tok.py`
  must receive the ACTUAL checkpoint path (e.g. `build/tok_control.pt.pt`
  when the trainer OUT was `build/tok_control.pt`); the plan's Phase-2
  command as written would silently fall back to the exporter's random
  selftest. (2) The training environment is the repo venv (`.venv/bin/python`,
  torch 2.5.1+cu121); the system `python3` lacks torch. (3) `ctest` passes
  8/8 at this HEAD — the plan's "known CRLF selfplay_syntax failure" does not
  reproduce (the parallel agent's fixes landed since the plan was written).
- **Status:** Phases 1–3 PENDING (manual GCP follow-up per the plan
  protocol): 1,500-seed datagen on sts-test (seeds 300000–301499, three
  500-seed chunks, `OMP_NUM_THREADS=24`, same envs), control retrain on
  `build/strategic_tierb.csv` + candidate retrain on
  `build/strategic_sp_1500.csv` (GPU, rung 4, 40 epochs, same recipe),
  paired 256-seed gate on block 126700–126955 @1k/64p vs
  `build/vnet_all_a03_1k.csv` (50.4%). Pre-registered verdict rule
  unchanged: candidate ≥ control with CI excluding a meaningful loss →
  promotion path; null → 5.7.3 closed as a distribution lever.
- **Artifacts (ignored):** `build/sp_smoke.csv` (6,244 rows, clean
  regeneration — an earlier duplicated 12,488-row copy from re-running
  `strategicgen2` without truncating the file was discarded), plus
  `build/sp_smoke_phase0.csv` (6,244 rows),
  `build/tok_smoke.pt.pt` / `_tok_state.bin` / `_metrics.json`,
  `build/ooc_strategic_tok_smoke.native` (smoke export, 807,432 bytes),
  `build/smoke_gate_phase0.csv` (2-seed load smoke). All git-ignored under
  `build/`; the smoke .native is NOT a candidate artifact (2-epoch CPU smoke
  checkpoint, rung 4 default topology) and is kept OUT of the git-tracked
  `selfplay/models/` directory.
- **Follow-up (same day, verification-fix session):** (a) discrepancy (2)
  above is resolved — the venv's torch 2.5.1+cu121 stack was copied into the
  user site (`~/.local/lib/python3.12/site-packages`), so the plain-`python3`
  trainer/export smoke commands now pass (`STRAT_DEVICE=cpu STRAT_EPOCHS=2
  python3 train_strategic_tok.py build/sp_smoke.csv build/tok_smoke.pt` → 2
  epochs, metrics byte-identical to the venv run; `python3 export_strategic_tok.py
  build/tok_smoke.pt selfplay/models/ooc_strategic_tok_smoke.native` → 32
  parity checks, max err 1.66e-07; `build/tok_smoke.pt` is kept as a symlink
  to the trainer's real `build/tok_smoke.pt.pt` so the exporter exercises the
  trained checkpoint rather than its random selftest fallback). (b) The
  plan's 1-seed @100-sim schema-validation check
  (`strategicgen2 1 100 0 build/sp_smoke_header.csv 300010`, 60 s budget)
  cannot complete on this machine: measured 166.2 s for 1 seed (dominated by
  the per-decision branch-fight contract — 3 fights × 150/100/50 sims,
  `STRATEGIC_BRANCH_FUTURES=1`, the §84-optimal defaults the plan mandates
  keeping; 12 OMP threads but a single seed uses one core). The schema it
  would validate is already verified by the 10-seed smoke above (1017 state
  cols + Tier-B suffix + 100% labelWon coverage), so no datagen code or
  default was changed for it — the timeout is a verification-budget mismatch,
  not a producer defect.
- **Follow-up (same day, verification-fix session, second pass — REVERTED):**
  an experimental `runStrategicGenSeed2` change deferred sampled decisions'
  branch battles to a post-run `#pragma omp taskgroup` when `nSeeds <
  threads` (spare team threads). It was NOT structurally guaranteed
  byte-identical to the serial path: in deferred mode the thread-local
  `t_curPath` stays set through the main loop, so the main-run OOC policy
  (`serverCardRewardPolicy`/`restWinPolicy`/`upgradeSelectWinPolicy` via
  `vFeatCsv`→`richRow`) sees real `pv*` features, whereas the serial path
  nulls it after the first branch eval (`pv*`=0); the floor/win nets consume
  `pv*` features, so `chosen` rows can flip on unverified seeds. Byte-identity
  was only spot-checked (1–3 seeds @100 sims), and the diagnostics recorded
  from that run (37.2% strict agreement) did NOT match the serial path
  (34.1/46.0 above). Per review, **the change was fully reverted —
  `apps/one_combat.cpp` is byte-identical to HEAD** (no C++ changes, per the
  plan's explicit constraint); the smoke above was regenerated with the exact
  serial code the GCP datagen will use, and the `build/sp_smoke.csv` training
  input was truncated before re-running (no duplicated rows; the trainer now
  sees 1,554 valid policy groups instead of 0). The 1-seed @100-sim 60
  s-budget mismatch (follow-up (b) above) stands as a recorded verification
  limitation: the schema is already proven by the 10-seed smoke, so no code
  change is justified. Per-seed reproducibility re-verified: serial 1-thread
  reruns of seed 300000 are byte-identical; the 10-seed file differs across
  runs only in seed-block ordering (dynamic OMP schedule), not content.
- **Follow-up (same day, recovery-fix session — reversion verified complete):**
  the second-pass reversion described above is now actually true in the tree:
  `git diff apps/one_combat.cpp` is empty (the deferred-branch
  parallelization is fully removed, so the plan's no-C++-change constraint
  holds). `build/sp_smoke.csv` was truncated and the 10-seed smoke re-run from
  scratch on the serial path (315 s wall @12 threads) → 6,244 rows, 380–771
  rows/seed, 100% labelWon coverage, 2,363 distinct labelWon, and per-seed
  rows byte-identical to the original Phase-0 serial file; the §104-style
  diagnostic reproduces the recorded numbers exactly (34.1% strict / 46.0%
  in-set on 1,055 groups; per-screen EVENT 41.4/50.0, MAP 51.9/56.3, REST
  50.0/59.7, REWARDS 29.5/45.1, SHOP 15.7/15.7). The 2-epoch CPU
  trainer/export smokes were re-run on the clean slice with identical metrics
  (1,554 valid policy groups, policy_top1 0.44→0.42, q_top1 ~0.20, val_pol_ce
  1.5204; export 32 parity checks, max err 1.66e-07) → the smoke .native now
  exists only under ignored `build/ooc_strategic_tok_smoke.native`; the copy
  that had accumulated in git-tracked `selfplay/models/` was removed (it must
  not be committed; only the Phase-2/3 control/candidate .native files ship).
- **Decision log:** `2026-08-08-selfplay-relabeling.md`.

## §136 Frontier-leaf corpus + empirical relabeling (frontiergen/leafrelabel): infrastructure implemented with local smoke verification, no gameplay result yet (2026-08-08, local)

- **What:** phases 2-3 of the plan "Combat-value targets" (`.ai/20260808-120025`):
  (2) `one_combat frontiergen` captures Searcher3 frontier-leaf states as
  versioned binary `BattleContext` snapshots (`include/combat/BattleContextBinary.h`,
  `sts::serializeBattleContext`/`deserializeBattleContext`; round-trip contract =
  `combatExtractFeatures` identity, verified by the new `battlecontext_roundtrip`
  unit-test subcommand registered in CTest) at the THREE S3 frontier sites —
  the leaf-expansion blend site always fires when `search::g_onS3LeafQuery` is
  set; the fair illegal-stored-edge rollout fallback and the depth-cap direct
  eval fire ONLY under `search::g_s3LeafQueryAllSites` (thread_local, default
  false), which ONLY frontiergen sets, so leafdiag/leafref/rollouttrace keep
  the historical single-site corpus (`S3LeafDiagnostic::frontierType` 0/1/2 and
  `rolloutSteps` record the site + rollout length) — and (3) `one_combat
  leafrelabel` restores each leaf and runs a FRESH high-budget Searcher3
  recording every terminal evaluation (`evaluateTerminal` made virtual;
  `TerminalRecordingSearcher` records won/endHp per terminal eval) → empirical
  P(win), HP|win mean/quantiles; plus a CRN sibling pass (one Belief + particle
  set from the parent visible state, `installSharedParticles`, sibling actions
  enumerated with the searcher's OWN contract `search::enumerateActionsForNode`
  — potions included) at a separate sibling budget. leaf.csv/sibling.csv
  self-document the denominator: `totalTerminals` counts ONLY terminal evals
  and a `nonTerminal` column (= budget − totalTerminals, clamped ≥ 0) reports
  sims without one (prune-as-dead / non-terminal depth-cap/rollout-cap evals).
  Phase-4 analysis scaffold: `tools/leaf_ranking.py --frontier` (pairwise
  ranking accuracy / top-1 / Spearman / regret of the deployed leaf model's
  `modelPred` vs the teacher pWin, stratified, deterministic bootstrap CIs;
  Brier/ECE only with a probability-scale `--prob-col`).
- **Regime forced by both modes:** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_LIVE_VALID=1` (deployed fair-S3 datagen regime; live-valid
  set explicitly — datagen is not covered by the parse-time default, §123).
- **Corpus dedup:** per-seed at capture time (first kept, `duplicateCount`
  incremented) AND corpus-wide at flush time under the critical section — a
  visible state already written by an earlier-flushed seed is dropped without
  re-serialization (counted in the run summary, 0 in the 8-seed smoke); parent
  marker rows (frontierType=-1) are not deduped.
- **Local smoke (this entry, no gameplay claim):**
  - `cmake --build build -j` clean; `./build/test battlecontext_roundtrip` PASS
    (seeds 0..3 x JAW_WORM/CULTIST/GREMLIN_NOB/SLIME_BOSS after several executed
    turns; feature-byte + 6 RNG streams + decision-state fields identical);
    `ctest --test-dir build --output-on-failure` 9/9 PASS.
  - `STS_S3_PARTICLES=16 STS_FRONTIERGEN_PER_STRATUM=10 ./build/one_combat
    frontiergen 8 300 0 build/frontier_smoke.csv 0 smoke` → 963 CSV rows
    (828 leaf rows + 135 parent marker rows), 99 rows with duplicateCount>0
    (dedup by obsHash verified), all 11 strata filled
    (s0-8=80, s9=28, s10=80; 0 cross-seed duplicates dropped),
    `build/frontier_smoke_smoke.csv` + `build/frontier_smoke_smoke.bin`
    (751 KB; blob offsets point at the blob DATA after the 4-byte length
    prefix). NOTE: the illegal-fallback/depth-cap sites did not fire in the
    smoke (small trees at 300 sims; depth cap needs 100-level descents) — the
    type-1/2 strata are expected to populate in the batch corpus (long boss
    fights at higher budgets).
  - `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 ./build/one_combat
    leafrelabel build/frontier_smoke_smoke.csv build/frontier_smoke_smoke.bin
    build/leaf_smoke.csv build/sibling_smoke.csv 5000 5 16` → 5 leaf rows
    (pWin in [0,1], totalTerminals == 5000 == high budget, nonTerminal 0) + 15
    sibling rows (matching leafObsHash, distinct siblingObsHash,
    totalTerminals == 3000, nonTerminal 0, modelPred = deployed vnet
    prediction on the endHp scale; NaN only when no combat value model is
    loaded). Two re-runs on the same inputs are BYTE-IDENTICAL (stability
    criterion: identical pWin/meanHpOnWin).
  - `tools/leaf_ranking.py --frontier --leaf build/leaf_smoke.csv --sibling
    build/sibling_smoke.csv` runs and reports pairwise/top-1/Spearman/regret
    (smoke values: pairwiseAcc 0.667, top1 0.000, Spearman 0.5, regret 0.001 —
    illustrative only, 5 groups; the vnet endHp-scale value is NOT a calibrated
    probability, Brier/ECE correctly reported as not computed);
    `--self-test` PASS.
  - Existing modes re-verified after the review gating fix:
    `one_combat leafdiag 4 300 0 build/ld_smoke.csv` → 1710 rows with the
    UNCHANGED leafdiag schema (no frontierType column); `one_combat leafref
    build/ld_smoke.csv build/ld_ref.csv 3000 4 0 300` re-captured 1710/1710
    recorded leaves (no re-capture WARNING) — leafdiag/leafref/rollouttrace
    behavior is unchanged by the frontiergen extension.
- **Artifacts (local, disposable smokes under build/):**
  `build/frontier_smoke_smoke.{csv,bin}`, `build/leaf_smoke{,2}.csv`,
  `build/sibling_smoke{,2}.csv`, `build/ld_smoke.csv`, `build/ld_ref*.csv`.
- **Not implemented / deferred (recorded in the plan + KB):** per-particle
  terminal-outcome breakdown (`STS_LEAFRELABEL_PARTICLE_BREAKDOWN` — the
  particle id is internal to `step()`); the full phase-3 batch (500-1000
  leaves @10k sims, GCP-parallel) and the phase-4 verdict gate (top-1 ≥ 80% +
  Spearman ≥ 0.7 pre-registered rule) await the batch corpus.
- **Decision log:** `2026-08-08-frontiergen-leafrelabel.md`.

## §137 Covariate-shift mixture retrain (§135a next experiment): combatgen + leafdiag training mixture with SEPARATE on-policy/search-leaf holdouts — mixture does NOT improve held-out search-leaf ranking (pairwise −3.5pp, top-1 −3.9pp, regret +0.78) AND hurts the on-policy fit — branch closed, no gameplay gate (2026-08-08, local)

- **What:** the pre-registered covariate-shift branch experiment from the
  §135a verdict (decision log `2026-08-08-leaf-state-diagnostics.md`):
  retrain the deployed §126 end-HP leaf on a MIXTURE of on-policy combatgen
  states PLUS actual Searcher3 search-leaf states, with separate on-policy
  and search-leaf holdouts, and test whether search-leaf RANKING on held-out
  search-leaf states improves. Diagnostic artifact only — no default change,
  no promotion, no C++ change (the deployed `build/v_combat_honest.txt`
  @α0.3 stays). NO gameplay gate (pre-registered: ranking evidence first).
- **Training data and pre-registered split:**
  - combatgen source `build/vcombat_honest.csv` (287,517 rows, 16,337
    fights, seeds 0-1499): fight-group holdout
    `GroupShuffleSplit(test_size=0.15, random_state=0, groups=(seed,fightIdx))`
    → on-policy val (43,473 rows).
  - search-leaf source `build/leafdiag_gate_64.csv` (288,537 rows, seeds
    126700-126763): ONLY train seeds 126700-126747 (48 seeds, 216,079 rows,
    1,012 fights) enter training/validation, with the same fight-group
    split → search-leaf val (30,316 rows); eval seeds 126748-126763 (16
    seeds, 72,458 rows) held out ENTIRELY — asserted absent from every
    training row (runtime assert; 72,458 eval rows counted and filtered).
  - Mixture training set = 429,807 rows (244,044 combatgen + 185,763
    leafdiag). Labels = fight outcome (`fightWon`→`won`, `fightEndHp`→
    `endHp`), same semantics as combatgen; the leafref reference values are
    vnet-influenced approximations and were NEVER training labels. The
    12 diagnostic/metadata leafdiag columns (decIdx, floor, act,
    encounterName, treeDepth, obsHash, nLegalActions, stratum, endHp_pred,
    utilityR_pred, rawRolloutEval, blendedEval) were dropped.
- **Canonical §126 recipe (byte-identical parameters):**
  `VCOMBAT_TARGET=endhp` (default), device `cuda` (RTX 3060 Ti, local),
  max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
  min_child_weight=20, max_bin=256, num_boost_round=1500,
  early_stopping_rounds=40, critical-state weight formula
  (won/curHp/maxHp/encounter-failure; POLICY_CSV unset → teacher
  disagreement 0). Early stopping signal = the on-policy (combatgen
  holdout) regime, the same stopping signal as §126. Feature filter = the
  canonical combatgen-derived std>1e-9 filter → **733 features, exactly the
  deployed model's feature set** (filtering on the concatenated frame would
  give 750 — differing variance across the 64-seed leafdiag slice — and
  break the "training mixture is the only difference" comparison). Best
  iteration 1349 (of 1500); exported `build/v_combat_mix.txt` = 1,390
  trees, 733 features, base_score 28.04239; sha256
  `0ed6672c…` (txt) / `c1764f63…` (json). Asserting `one_combat vnettest`
  PASS (max|diff| 1.27e-4 vs tol 0.001, 200 rows).
- **Per-regime validation metrics (trainer, `build/v_combat_mix_metrics.json`):**
  | regime | rows | RMSE vs endHp | MAE vs endHp | RMSE vs R | MAE vs R |
  |---|---|---|---:|---:|---:|
  | on-policy val (combatgen holdout) | 43,473 | **8.23** | **5.97** | 48.37 | 45.65 |
  | search-leaf val (leafdiag train-seed holdout) | 30,316 | **15.46** | **11.33** | 49.20 | 46.20 |
  On-policy comparison: the deployed §126 control measured val RMSE 7.88 /
  MAE 5.58 (§134) and §126 recorded val-rmse 7.99 on the SAME combatgen
  holdout split → **the mixture HURTS the on-policy fit** (RMSE +0.35,
  MAE +0.39). The search-leaf val remains much harder than on-policy
  (RMSE 15.46 vs 8.23) even after training on the search-leaf distribution.
- **Search-leaf ranking evaluation (the DECISIVE pre-registered test):**
  re-ran `one_combat leafdiag 16 1000 0 build/leafdiag_mix_eval.csv 126748`
  on the 16 held-out eval seeds @1000 sims asc 0 with EXACTLY the §135a
  gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=build/v_combat_honest.txt`
  @`STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=build/v_combat_mix.txt`,
  `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`).
  The search is unchanged (`STS_DIAG_VNET2` is never read by the searcher)
  so the identical leaves regenerate: 72,458 rows re-captured, and
  **100% of re-captured leaves join `build/leafref_gate_64_4k.csv` by
  (seed, fightIdx, decIdx, obsHash)** — the re-capture sanity check passes
  (identical leaves to §135a, no mismatch). New CSV columns: `endHp_pred` =
  deployed §126 model, `utilityR_pred` = mixture model, on identical leaves.
  `tools/leaf_ranking.py --leafdiag build/leafdiag_mix_eval.csv --leafref
  build/leafref_gate_64_4k.csv --ood build/leafdiag_gate_64_ood.csv --json
  build/leaf_ranking_mix_eval.json` (4,395 decision groups re-captured;
  4,387 contribute pairwise metrics, 890,941 pairs, fixed bootstrap seed
  20260808):
  | metric | deployed endHp | mixture (utilityR_pred) | Δ (mixture − deployed) |
  |---|---|---:|---:|
  | pairwise accuracy | **0.7262 [0.7209, 0.7318]** | 0.6914 [0.6858, 0.6970] | **−3.5pp, CIs disjoint** |
  | top-1 | **0.3686 [0.3545, 0.3823]** | 0.3298 [0.3152, 0.3433] | **−3.9pp, CIs disjoint** |
  | regret | **7.431 [7.088, 7.783]** | 8.209 [7.850, 8.569] | **+0.78 (worse)** |
  | Spearman vs ref | 0.790 | 0.803 | +0.013 (mixture better) |
  | Pearson vs ref | 0.779 | 0.801 | +0.022 |
  | MAE vs ref (own scales) | 31.75 | 28.12 | (not comparable across scales) |
  Note the deployed endHp's held-out numbers (pairwise 0.726, top-1 0.369)
  are consistent with the §135a full-64-seed measurement (0.719 / 0.359),
  confirming the 16-seed eval block is representative.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref; `build/leaf_ranking_mix_eval_rawrollout.json`, 4,085 groups):**
  pairwise 0.7289 [0.7229,0.7350] vs 0.6921 [0.6857,0.6980] (−3.7pp),
  top-1 0.335 vs 0.305, regret 14.47 vs 15.83 — same direction, so the
  mixture's ranking disadvantage is NOT an artifact of the vnet-influenced
  leafref reference.
- **Verdict: ❌ the covariate-shift branch is CLOSED — the mixture does NOT
  improve held-out search-leaf ranking; it makes all three pre-registered
  ranking metrics WORSE (pairwise −3.5pp, top-1 −3.9pp, regret +0.78, all
  CIs disjoint for the accuracies), and it HURTS the on-policy fit (val
  RMSE 8.23 vs 7.88 control, MAE 5.97 vs 5.58).** Pre-registered rule: a
  gameplay gate is a separate follow-up ONLY if ranking improves → **no
  gameplay gate; the deployed §126 vnet stays default.** Notable nuance:
  the mixture correlates with the high-budget reference BETTER than the
  deployed model (Spearman 0.803 vs 0.790, Pearson 0.801 vs 0.779) — the
  same pattern as §134's direct-R model (correlates better, ranks worse) —
  so absolute fit to the (vnet-influenced) reference does not predict
  within-group ranking even when the model is trained ON the search-leaf
  distribution. Training on actual search-leaf states did not make the
  end-HP target rank those states better; the §134 hypothesis space
  (target semantics / ranking-vs-absolute) is not resolved by adding
  search-leaf states to the endHp objective.
- **Artifacts (build/, git-ignored, NOT promoted):**
  `build/v_combat_mix.{json,txt,val.csv,_metrics.json}`,
  `build/leafdiag_mix_eval.csv` (72,458 rows),
  `build/leaf_ranking_mix_eval.json`,
  `build/leaf_ranking_mix_eval_rawrollout.json`, smoke slices
  `build/smoke_{combatgen,leafdiag,mixed}.csv`,
  `build/leafdiag_mix_smoke_2.csv`, `build/v_combat_mix_smoke.*`,
  logs `/tmp/opencode/train_mix_full.log`,
  `/tmp/opencode/leafdiag_mix_eval.log`,
  `/tmp/opencode/leaf_ranking_mix_eval2.log`. Code:
  `tools/train_value_mixture.py` (new; default single-CSV path of
  `train_value_combat.py` is untouched and byte-identical). Decision log:
  `2026-08-08-covariate-shift-mixture.md`.

## §138 Quick partial-data tok retrain + 64-seed feel-run (5.7.3 interim, 2026-08-08, local — INFORMAL smoke, NOT the 5.7.3 gate)

- **What:** while the 3×500-seed GCP datagen (Phase 1) is still running, a
  snapshot of chunk 1 (`build/sp_300000_partial.csv`, 160,276 rows / 302 seeds,
  seeds 300000–3003XX) was pulled and used for a quick V4-token-net retrain and
  a 64-seed paired feel-run. Purpose: exercise the full train/export/gate chain
  end-to-end early; NOT a verdict on 5.7.3.
- **Train (local GPU, .venv, torch 2.5.1+cu121, rung 4, 40 epochs, defaults):**
  `train_strategic_tok.py build/sp_300000_partial.csv build/tok_sp_partial.pt`
  → held-out (31,813 rows / 7,910 groups): `val_pol_ce` 0.559, `policy_top1`
  0.754, `q_top1` 0.288, `margin` 4.75, `value_mae` 4.00. Deployed
  `ooc_strategic_tok_final` metrics for reference (different val split, NOT
  comparable): `val_pol_ce` 0.486, `policy_top1` 0.793, `q_top1` 0.290,
  `margin` 10.32, `value_mae` 10.18. Export:
  `export_strategic_tok.py build/tok_sp_partial.pt.pt
  selfplay/models/ooc_strategic_tok_sp_partial.native` — 32/32 parity checks.
- **64-seed paired feel-run** (seeds 126700–126763, asc 0, 1k sims, fair S3
  −belief−chain, 64p, 12 threads, full V4 gate stack, `STS_OOC_STRATEGIC_MARGIN=1.0`):
  control `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  vs candidate `.../ooc_strategic_tok_sp_partial.native`:
  **deployed 54.7% vs partial 28.1% wins, Δ −26.6pp, 95% CI [−42.2, −10.9]**;
  floor 44.5 vs 39.5 (Δ −5.1 [−8.1, −2.1]); HP end 30.1 vs 15.3;
  discordant 29/64. Runtime ~4.5 min total (bestbench ~2.4s/seed wall @12t).
  CSVs: `build/tok_cmp_{final,sp}_64.csv`; `paired_analysis.py` strict.
- **Interpretation (informal):** the partial model is clearly worse online, but
  it trained on ~20% of the planned corpus (underfitting expected) and the
  plan's §62/§100/§127/§129 pattern (offline gains do not transfer) is
  consistent. This run does NOT close 5.7.3 — the gate requires the same-recipe
  control (old corpus) vs the full 1500-seed candidate + 256-seed paired gate
  + second confirmation block. No default change; deployed artifact untouched.
- **Decision log:** `2026-08-08-selfplay-relabeling.md` (addendum).

**§138 follow-up (same day): 100-epoch retrain on the same partial data.** `STRAT_EPOCHS=100` on `build/sp_300000_partial.csv` → best held-out `val_pol_ce` 0.5454, `policy_top1` 0.766, `margin` 5.54 (vs 40-epoch 0.559/0.754/4.75 — more epochs helps the offline fit). 64-seed paired gate (same seeds/env): 32.8% vs deployed 54.7% (**Δ −21.9pp, CI [−35.9, −7.8]**); vs the 40-epoch arm **+4.7pp, CI [−7.8, +18.8]** (direction only, n.s.). Conclusion: epoch count explains only a small part of the online gap; the data (volume ~20% + label-producer change) dominates. Artifacts: `build/tok_sp_partial_e100.pt.pt`, `build/tok_e100_train.log`, `build/tok_cmp_sp_e100_64.csv`, `selfplay/models/ooc_strategic_tok_sp_partial_e100.native` (32/32 parity).

## §139 Experiment A: Stratified leaf ranking — endHp vs utilityR ranking gap by stratum (2026-08-08, local — diagnostic, no gameplay)

- **What:** Re-analysis of the §135a leafdiag/leafref corpus (288k leaves, 267k
  references, 17,194 decision groups, 16,676 usable) stratified by fight
  outcome, HP band, tree depth, and cross-strata to test the hypothesis that
  the endHp model's ranking advantage concentrates in near-death deep-tree
  states.
- **Method:** Per-group pairwise ranking accuracy (top-1, regret) of pure model
  predictions (no rollout blend) against leafref high-budget references,
  bootstrap CIs (2,000 iterations, fixed seed 20260808) per stratum.
  Standalone script (not `leaf_ranking.py` — the full tool times out on the
  1 GB CSV due to DictReader memory on this machine; a 28 MB column-pre-filtered
  `build/leafdiag_slim.csv` was used).
- **Artifacts:** `build/leaf_ranking_reconfirm.json`
- **Headline results:**

  | Stratum | nGroups | endHp pairAcc | utilR pairAcc | Δpair | Δtop1 |
  |---|---|---:|---:|---:|---:|
  | **all** | 16,676 | 0.7195 [0.7167,0.7224] | 0.7112 [0.7085,0.7141] | **+0.0082** | **+0.0231** |
  | won=1 | 15,651 | 0.7237 | 0.7157 | +0.0080 | +0.0225 |
  | won=0 (lost) | 1,025 | 0.6549 | 0.6428 | **+0.0121** | +0.0322 |
  | hp_low (<30%) | 6,932 | 0.7291 | 0.7252 | **+0.0039** | +0.0113 |
  | hp_mid (30-70%) | 6,582 | 0.7229 | 0.7146 | +0.0083 | +0.0324 |
  | hp_high (≥70%) | 3,162 | 0.6912 | 0.6735 | **+0.0177** | +0.0297 |
  | deep (d≥15) | 381 | 0.7948 | 0.7768 | **+0.0180** | +0.0525 |
  | mid_depth | 14,364 | 0.7163 | 0.7091 | +0.0072 | +0.0236 |
  | shallow (d<5) | 1,931 | 0.7282 | 0.7143 | +0.0140 | +0.0135 |
  | **low_deep** | 60 | 0.8074 | 0.8068 | **+0.0006** | **−0.0500** |
  | low_shallow | 887 | 0.7430 | 0.7396 | +0.0034 | +0.0079 |
  | won_deep | 381 | 0.7948 | 0.7768 | +0.0180 | +0.0525 |
  | lost_low | 727 | 0.6514 | 0.6469 | +0.0045 | +0.0165 |
  | won_low | 6,205 | 0.7382 | 0.7344 | +0.0038 | +0.0106 |

- **Key findings:**
  1. **The gap does NOT concentrate in near-death states** — it is narrowest
     in hp_low (+0.0039, half the overall gap) and effectively zero at
     low_deep (+0.0006, utilityR actually wins top1 by −0.0500). This refutes
     the architect's cliff-edge hypothesis.
  2. **The gap is widest in high-HP (+0.0177, 2.2× overall) and deep-tree
     (+0.0180, 2.2×) states** — complex, information-rich positions where
     ranking is hardest but individual decisions most differentiate the search
     tree.
  3. **The gap is also larger in lost fights (+0.0121) than won (+0.0080)** —
     in fights the agent eventually loses, model ranking quality matters more.
  4. The overall +0.0082 pairwise gap (and +0.0231 top1) still cannot directly
     explain ±12pp win-rate swings without amplification through PUCT
     visit-redistribution dynamics or direct-eval (unblended) sites.
- **Verdict: diagnostic only.** The ranking advantage exists but is small, does
  not concentrate where hypothesized, and cannot directly explain the ±12pp
  online swing. Experiment B (blend sweep) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §140 Experiment B: Blend-α sweep — both models are nearly identical when blended (2026-08-08, local — diagnostic, no gameplay)

- **What:** For 8 α values ∈ [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7], compute
  within-group pairwise ranking accuracy of the BLENDED value
  `α·model_pred + (1−α)·rawRolloutEval` against the leafref high-budget
  reference. Tests whether: (a) endHp achieves peak ranking at α≈0.2–0.3
  (the deployed sweet spot), (b) utilityR ranking degrades monotonically from
  α=0, (c) any α exists where utilityR approaches endHp.
- **Tool:** `tools/leaf_blend_sweep.py` (new, ~180 lines). Reuses existing
  `build/leafdiag_slim.csv` + `build/leafref_gate_64_4k.csv`.
- **Artifacts:** `build/leaf_blend_sweep.json`
- **Headline results:**

  | α | endHp pairAcc | utilR pairAcc | Δpair | endHp top1 | utilR top1 |
  |---:|---|---:|---:|---:|---:|
  | 0.00 | 0.7192 [0.7163,0.7220] | 0.7192 [0.7163,0.7220] | +0.0000 | 0.3970 | 0.3970 |
  | 0.05 | 0.7456 [0.7429,0.7482] | 0.7444 [0.7418,0.7472] | +0.0011 | 0.4290 | 0.4283 |
  | 0.10 | 0.7465 [0.7439,0.7492] | 0.7455 [0.7429,0.7483] | +0.0010 | 0.4294 | 0.4297 |
  | 0.15 | 0.7473 [0.7447,0.7500] | 0.7465 [0.7439,0.7493] | +0.0009 | 0.4307 | 0.4309 |
  | 0.20 | 0.7482 [0.7456,0.7509] | 0.7472 [0.7446,0.7499] | +0.0010 | 0.4310 | 0.4301 |
  | **0.30** | **0.7499 [0.7474,0.7527]** | **0.7486 [0.7459,0.7514]** | **+0.0013** | **0.4311** | **0.4291** |
  | 0.50 | 0.7517 [0.7491,0.7544] | 0.7484 [0.7457,0.7511] | +0.0033 | 0.4275 | 0.4189 |
  | 0.70 | 0.7498 [0.7471,0.7526] | 0.7436 [0.7409,0.7464] | +0.0062 | 0.4177 | 0.3999 |

  α=0 sanity check: both models identical (0.7192) — they share the same
  rawRolloutEval.

- **Key findings:**
  1. **Both models IMPROVE with any blend > 0.** Even utilityR gains from
     blending — it does NOT degrade monotonically. The pure-model ranking
     (Experiment A) understates both models' usefulness.
  2. **At the deployed α=0.3, the models are statistically INDISTINGUISHABLE.**
     endHp 0.7499 [0.7474,0.7527] vs utilityR 0.7486 [0.7459,0.7514] — CIs
     overlap substantially, gap only +0.0013. The pure-model gap of +0.0082
     (Experiment A) collapses because the 70% shared rollout component dominates.
  3. **endHp peaks at α=0.5** (0.7517), not at the deployed α=0.3. The deployed
     sweet spot is below peak ranking — gameplay wins rate, not ranking
     accuracy, determined α=0.3.
  4. **The gap only visibly separates at α≥0.5:** at α=0.5 gap=+0.0033, at
     α=0.7 gap=+0.0062. Heavier model influence favors endHp, consistent with
     the universal α-curve finding (heavier model influence never helps online).
  5. **The ±12pp online win-rate gap CANNOT be explained by per-leaf blended
     ranking quality.** At the deployed α=0.3, the models rank nearly
     identically. The online gap must come from: (a) direct-eval sites where
     the model fires at full weight (depth cap, no rollout blended),
     (b) PUCT range normalization interacting with model scale (endHp [0,~80]
     vs utilityR [0,~150]), (c) visit-redistribution dynamics amplifying small
     value differences through backprop.
  6. **Top-1 accuracy also nearly identical** at moderate α: endHp 0.4311 vs
     utilityR 0.4291 at α=0.3.
- **Verdict: diagnostic — blend ranking parity disproves the ranking-quality
  hypothesis for the deployed α=0.3.** The online gap is NOT caused by better
  leaf ranking in the blended evaluation. The mechanism must involve
  unblended evaluation sites, PUCT value-scale dynamics, or
  visit-redistribution amplification. Experiment C (top-action agreement + per-
  fight outcome correlation) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §141 Experiment C: Top-action agreement — models agree 81% of the time, essentially tied when they disagree (2026-08-08, local — diagnostic, no gameplay)

- **What:** For each of 17,098 decision groups, identify which leaf each model
  picks as "best" (using blended values at deployed α: endHp@0.3, utilityR@0.1)
  and compare against the leafref high-budget reference's choice. Measures
  agreement rate, per-model correctness when they disagree, and stratification
  by fight outcome, HP band, and tree depth.
- **Tool:** `tools/leaf_top_action.py` (new, ~290 lines).
- **Artifacts:** `build/leaf_top_action.json`
- **Headline results:**

  | Metric | Value |
  |---|---:|
  | Total decisions | 17,098 |
  | Models agree on best leaf | 80.9% |
  | endHp matches reference | 44.5% |
  | utilityR matches reference | 44.3% |
  | Both match reference | 39.7% |
  | **Neither matches reference** | **50.9%** |

  **When models disagree (19.1% of decisions):**
  - endHp right: 25.1%, utilityR right: 24.4%, both wrong: 50.4%
  - endHp wins 50.7% of resolvable disagreements — a coin flip
  - Overall endHp advantage: +23 decisions (+0.13pp) out of 17,098

  **Key strata (agreement rate / endHp=ref% / utilR=ref%):**
  - won=1 (83.0% / 45.6% / 45.6%) — identical in won fights
  - won=0 (48.4% / 26.4% / 24.6%) — agreement collapses in lost fights,
    endHp +1.8pp
  - depth=deep (85.9% / 53.7% / 51.2%) — endHp +2.6pp in deep trees
  - hp=mid|depth=deep (87.0% / 53.2% / 50.0%) — endHp +3.2pp
  - hp=low (78.3% / 40.8% / 41.2%) — utilityR +0.4pp in low-HP

  **Per-fight averages:**
  - Won fights (1,309): 12.3 decisions/fight, endHp=ref 53.2%, utilR=ref
    53.1%, models agree 85.4%
  - Lost fights (41): 25.7 decisions/fight, endHp=ref 26.2%, utilR=ref
    25.3%, models agree 49.9%
  - Per-fight winner count: endHp 308, utilityR 330, tie 712

- **Key findings:**
  1. **The two models are effectively IDENTICAL at top-action selection.**
     The models are a coin flip on disagreements, agree 81% of the time,
     and differ by only +23 decisions (+0.13pp) out of 17,098.
  2. **The reference itself is unreliable:** neither model matches it in 50.9%
     of decisions. The high-budget Searcher3 reference is an approximation,
     not ground truth.
  3. **Lost fights are chaotic:** agreement drops from 83% (won) to 48%
     (lost). Top-1 accuracy drops from ~46% to ~26%.
  4. **Deep-tree decisions favor endHp** (+2.6pp, n=391) but sample is small.
  5. **The ±12pp online win-rate gap CANNOT be explained by top-action
     choice.** The models are indistinguishable at ranking (Experiment B)
     AND top-action selection (Experiment C). The gap must come from PUCT
     value-magnitude propagation, visit-redistribution dynamics, or the
     unblended direct-eval sites where the model fires at full weight.
- **Verdict: diagnostic — all three static leaf-analysis hypotheses are
  now closed.** Per-leaf ranking (Exp B), top-action choice (Exp C), and
  cliff-edge concentration (Exp A) all fail to explain the ±12pp gap.
  The remaining causal paths require dynamic search-tree analysis
  (PUCT Q-range normalization, visit-count redistribution, unblended
  evaluation sites).
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §139 Q-head objective experiments on partial 5.7.3 data (2026-08-08, local, offline only — 373,616 rows / 707 seeds of chunk-1+2 partial, batch 2048, 60 epochs unless noted)

- **What:** two cheap trainer experiments on the new-datagen partial data:
  (A) best-epoch selection by `q_top1` instead of `val_pol_ce`
  (`STRAT_SELECT_METRIC=q_top1`); (B) a pairwise labelWon ranking term
  (`STRAT_RANK_LAMBDA=0.1`, margin 1.0, max 16 pairs/group) added to the Q
  MSE loss. Both opt-in envs, defaults unchanged.
- **Results (held-out):**
  | metric | baseline 60ep (early-stop run) | A: select q_top1 (60ep) | B: rank λ=0.1 (60ep) | baseline 200ep (val_pol_ce sel) |
  |---|---|---|---|---|
  | val_pol_ce | 0.5311 | 0.5374 | 0.5303 | 0.5252 |
  | policy_top1 | 0.773 | 0.770 | 0.774 | 0.776 |
  | margin | 5.57 | 7.71 | 5.65 | 6.40 |
  | q_top1 | 0.2899 | **0.3072** | 0.2904 | 0.2864 |
- **Reading:** selection-by-q_top1 directly improves the Q-head ranking
  agreement (+1.7pp vs the matched 60-ep baseline) at a small policy cost
  (−0.3pp top1); the ranking loss at λ=0.1 is flat (+0.1pp q_top1). Tie-heavy
  labelWon limits pair availability (§105). Offline only — no gate; the
  deployed gate uses the Q-head argmax, so a future online comparison would
  be the real judge. Artifacts: `build/tok_new_{200,selq,rank}.pt.pt` +
  `_metrics.json`.

## §142 Direct-eval site share measurement + scale-controlled utilityR gate — PUCT value-scale dynamics confirmed as the ±12pp gap mechanism (2026-08-08, local)

- **What:** (A) Run `searchdiag` on the deployed S3 config (32 seeds, @1k/64p,
  block 126700–126731) to measure the share of leaf evaluations at unblended
  direct-eval sites vs the blend site where α=0.3 blending applies. (B) Gate a
  **rescaled** utilityR model (affine output transform mapping utilityR's
  [0,~150] band to endHp's [0,~80] via base_score ratio 0.4135) against the
  original non-scaled utilityR model, both at α=0.1, 128 paired seeds
  (126700–126827), full V4 gate stack, fair S3−belief−chain/64p.
  Hypothesis from §141: the ±12pp endHp-vs-utilityR online gap comes from
  PUCT value-scale dynamics, not per-leaf ranking or unblended sites;
  if rescaling utilityR to endHp's band closes the gap, the mechanism is
  confirmed.
- **Tool:** `one_combat searchdiag` (rowtype A, S3 instrumented), affine model
  rescaling via Python text replacement on the §134 artifact
  `build/v_combat_utility_direct.txt` → `build/v_combat_utility_scaled.txt`
  (611 trees, base_score 62.82→25.97, leaf values ×0.4135).
- **Artifacts:** `build/sdiag_siteshare_32.csv`,
  `build/util_nonscale_128.csv`, `build/util_scale_128.csv`,
  `build/v_combat_utility_scaled.txt`

### §142a — Direct-eval site share (diagnostic)

- **Results (32 seeds, 9,915 decisions, 14.17M sims):**

  | Site | Count | Share of model evals |
  |---|---|---:|
  | Blended (rolloutLeafCalls, α=0.3) | 8,666,136 | 100.0% |
  | Unblended direct eval (leafDirectEval) | 231 | 0.003% |
  | Illegal-stored-edge share of rollouts | 11.9% | — |

  Only 34/9,915 decisions had any leafDirectEval > 0. `rolloutNoLegal` = 0
  (every rollout runs to terminal). The invariant
  `sims == terminalInTree + rolloutCalls + leafDirectEval` holds to
  within 0.001%.

- **Key finding: unblended direct-eval sites are essentially non-existent.**
  With `STS_ROLLOUT_DEPTH=0`, every rollout terminates — there are no
  depth-cap evals and no-legal-action at the live state almost never occurs.
  The §139–§141 corpus analyzed the only meaningful model-evaluation site
  (the blend site), where the two models are statistically indistinguishable.
  The ±12pp online gap **cannot** come from unblended sites — it must be
  PUCT value-scale dynamics.

### §142b — Scale-controlled utilityR gate

- **Results (128 paired seeds, α=0.1):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Non-scaled utilityR (original) | 36.7% | 40.9 | 24.6 | 19.1 |
  | Scaled utilityR (×0.41, endHp band) | **47.7%** | 42.4 | 24.9 | 20.7 |
  | Δ (scaled − non-scaled) | **+10.9pp** | +1.5 | +0.3 | +1.6 |
  | Deployed endHp @α0.3 (reference) | 56.2% | 44.7 | 31.9 | 27.6 |

  - Δ win 95% CI: **[+1.6pp, +20.3pp]** — statistically significant (CI excludes
    zero). Discordant 42/128 (33%): A-only 14, B-only 28.

- **Key finding: rescaling utilityR to endHp's output band recovers nearly
  all of the §134 −12.1pp gap.** The scaled model at 47.7% trails the
  deployed endHp at 56.2% by −8.5pp, but this is at α=0.1 (utilityR's
  pre-registered operating point) vs endHp's α=0.3 sweet spot. The 10.9pp
  gain from pure affine rescaling confirms the mechanism: both models rank
  leaves nearly identically (§140/§141), but utilityR's larger terminal scale
  ([0,~150]) changes `evalRange = max(1.0, bestValue − minValue)` in PUCT,
  shifting the exploration/exploitation balance and redistributing visit
  counts through backprop. When the scale matches, the ranking signal has
  room to express.

### §142c — Scale × α sweep (32 seeds, diagnostic)

- **What:** Grid sweep over 6 scale factors {0.20, 0.30, 0.41, 0.50, 0.60, 1.00}
  and 5 α values {0.05, 0.10, 0.20, 0.30, 0.50}, 32 seeds each, same full
  V4 gate stack. Scale factors generated by affine leaf-value × base_score
  multiplication on the §134 artifact `build/v_combat_utility_direct.txt`.

- **Results (32 seeds, win%):**

  | scale | α=0.05 | α=0.10 | α=0.20 | α=0.30 | α=0.50 |
  |---:|---:|---:|---:|---:|---:|
  | 0.20 | 28% | 41% | 41% | — | — |
  | 0.30 | 38% | 44% | 41% | — | — |
  | **0.41** | 38% | **50%** | 44% | 25% | 40% |
  | 0.50 | 38% | 31% | 41% | 47% | — |
  | 0.60 | 34% | 38% | 38% | 44% | — |
  | 1.00 | 31% | — | — | 38% | — |

  References: endHp α=0.10 = 39.1% (64 seeds), endHp α=0.30 = 56.2% (128
  seeds).

- **Key finding: peak is at scale≈0.41 (base_score–matched), α≈0.10.**
  Higher α degrades (α=0.50 → 40%). Higher scales at low α are worse than
  non-scaled (s=0.50 α=0.10 = 31% vs s=1.00 α=0.10 = 37% on 128 seeds).
  The sweet spot confirms the PUCT scale-dynamics hypothesis: utilityR's
  output band must match endHp's for the ranking signal to express.

### §142d — Definitive paired gate: scaled utilityR @α=0.10 vs deployed endHp @α=0.30 (128 paired seeds)

- **Results:**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Deployed endHp @α=0.30 | **56.2%** | 44.7 | 31.9 | 27.6 |
  | Scaled utilityR @α=0.10 | 47.7% | 42.4 | 24.9 | 20.7 |
  | Δ (util − endHp) | **−8.6pp** | −2.3 | −7.0 | −6.9 |

  - Δ win 95% CI: [−18.8pp, +0.8pp] — CIs span zero, direction clear.
    Discordant 41/128: A-only 26, B-only 15.

- **Key finding: the rescaled utilityR model does NOT beat the deployed endHp
  model, despite rescaling recovering +10.9pp from the scale mismatch.**
  At its optimal α=0.10 the scaled utilityR (47.7%) trails endHp at its
  optimal α=0.3 (56.2%) by −8.6pp. The better Spearman correlation (0.820 vs
  0.769, §135a) does not translate into a better combat leaf.

- **Verdict: the utilityR objective line is CLOSED.** Three independent
  gates now confirm it: (1) quantile-R α=0.3 −12.9pp (§133), (2) direct-R
  α=0.1 −12.1pp (§134), (3) rescaled direct-R α=0.1 −8.6pp (§142d).
  Rescaling fixes the scale interaction but the underlying value semantics
  (R = 50+endHp on win) rank combat states worse than raw endHp.
  The deployed `build/v_combat_honest.txt` @α=0.3 stays.

### §142e — Summary

- **Unblended direct-eval sites: 0.003% — ruled out.**
- **PUCT value-scale dynamics: CONFIRMED.** +10.9pp from rescaling alone
  (CI [+1.6, +20.3]).
- **UtilityR objective: CLOSED.** Even at matched scale, it trails endHp.
- **Combat-leaf model-improvement line: EXHAUSTED.** Every alternate target
  (quantile-R, direct-R, rescaled-R) has now been gated and lost. The
  remaining open question is whether a new training target derived from the
  frontier-leaf corpus (§136) could differ, but the historical record is
  uniformly negative (§133, §134, §137, §142d).

### §142f — Searchdiag mining: where the S3 search is weakest (diagnostic, no gameplay)

- **What:** Analyze the 32-seed `searchdiag` run from §142a (9,915 decisions,
  14.17M sims, deployed S3 config @1k/64p) for structural weakness patterns.
- **Tool:** manual Python analysis of `build/sdiag_siteshare_32.csv`.

- **Key findings:**

  1. **Act 3 is the weak spot.** Rollout fraction rises from 60% (Act 1) to
     77% (Act 3). Illegal-stored share rises from 7.2% to 19.0%. Tree coverage
     drops from 0.65 to 0.52. Visit share drops from 0.76 to 0.63.

  2. **19% of decisions are near-pure rollouts (visitShare < 0.5):**
     rollout fraction 93-94%, tree coverage ~0.33, average 5-6 legal actions,
     ~17-19 action rollouts. The tree barely exists — concentrated in Acts 2-3
     (20-28% of decisions, vs 13% in Act 1).

  3. **Even confident decisions waste sims.** Decisions with visitShare > 0.9
     (39% of all decisions, tree converged) still have **22.4% illegal-stored
     share** — every 5th tree descent hits an invalid edge and falls back to a
     random rollout.

  4. **25% of decisions are near-ties (value gap < 2):** visitShare only 0.50,
     80% rollout fraction. The search cannot distinguish the top actions —
     prime candidates for more sims or a sharper leaf model.

  5. **Per-encounter hot spots:** Encounter 40 (Act 3 boss) has 29.6% illegal
     share at 0.89 visitShare — very confident, very wasteful. Encounters 38
     and 53 have ~85% rollout fraction and visitShare < 0.5 — almost no tree.

- **Implication for searcher-side experiments:** The illegal-stored-edge path
  burns ~12% of rollouts overall (19% in Act 3). `STS_S3_EXPAND` tried to fix
  this by expanding legal edges but was falsified at −2.3pp (§125). However
  the waste grows with sim budget (§117: 68% at 30k sims in Act 1). A
  lighter-weight alternative — expand into the tree without PUCT on the new
  branch (deterministic descent only) — might avoid the §125 penalty. The
  near-tie decisions (25%, value gap < 2) are also candidates for dynamic sim
  allocation (give more budget when the top actions are close).

## §143 S3 fair forced-move budget pool redirect (STS_S3_POOL_REDIRECT): implemented opt-in; 8-seed smoke only — paired 256-seed gate pending (2026-08-09, local WSL)

- **What:** the §123 forced-move contraction (−8.5% cpu in the S3 fair
  path) discards the sims it saves. This opt-in flag reinvests them: each
  forced decision credits its unspent base sim budget to a per-fight
  `fightPool` (`ScumSearchAgent2::playoutBattleFair`, S3 branch), and each
  non-forced decision spends `baseSims + min(pool, baseSims)` (poolFrac
  1.0). Pure budget redirect — **no stability-based early stopping**: the
  STS_CONV_ROOT stability line (§118, −2.3pp at 256 seeds) is deliberately
  not revived; this isolates the clean forced-move-only sub-case that §118
  never tested. Env: `STS_S3_POOL_REDIRECT=1` (default off), parsed in
  `apps/one_combat.cpp::main` next to `STS_S3_BELIEF`.
- **Config (smoke):** `one_combat bestbench 300 8 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_S3_POOL_REDIRECT=1` for the candidate arm);
  asc 0; fair S3−belief−chain; native OOC; floor=`build/v_rich_trees.txt`,
  win=`build/v_win_trees.txt`; threads 12 (auto). Metric formula = producer
  `bestbench` summary; per-seed outcome columns won/floor/act/hpEnd/maxHp/
  fightsLost/deathCombat/deathEncounter.
- **Parity (required precondition):** unset vs `STS_S3_POOL_REDIRECT=0`
  give per-seed-identical outcomes on all 8 outcome columns (8/8 seeds;
  only the wall-time `sec` column differs) — the flag is decision-neutral
  when off, so the pair can gate against the same reference.
- **Smoke results (8 seeds, 300 sims — noise-dominated, not a gate):**
  candidate ON **25.0%** (2/8 wins) / floor 35.9 / hp 13.2 / cpu_sec/run
  3.73 vs OFF 37.5% (3/8) / floor 35.8 / hp 10.5 / cpu_sec/run 3.50–3.76.
  4/8 seeds change outcome (pool demonstrably engages and shifts
  decisions). cpu_sec/run at 300 sims is dominated by per-run wall-clock
  noise (12 threads), so no cpu claim is made from this smoke.
- **Gate result (64 paired seeds, 2026-08-09, local, same config @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 23.4% win / 39.1 floor / 10.2 HP / 24.7 cpu-s/run.
  **+1.6pp (95% CI [−5.3, +8.4]), 5/64 discordant (8%, 3 up / 2 down),
  cpu 1.11×.** Null at 64 seeds — direction favors candidate but CI spans
  zero heavily; cpu went up (+11%) rather than down, suggesting the pool
  spends extra sims without enough forced-move donations to offset, or
  noise dominates. §118 precedent (pool+stop −2.3pp) makes a pure-redirect
  positive plausible, but 256 paired seeds needed to confirm.
- **Caveat:** the §142 tok-globals change (50→41, de75e6c) prevents loading
  the deployed strategic tok-net model; both control and candidate arm run
  without it (native OOC GBMs only, win% ~21.9, NOT comparable to the §126
  50.4% reference). Paired deltas are internally valid, absolute win% is not.
  Paired 256-seed gate pending (orchestrator, needs tok-net load fix first).

## §144 Mid-rollout visible-state collision frequency in Searcher3 fair play — 0.089% exact collision rate, <1% dead end for rollout TT / path reuse (2026-08-09, local — diagnostic measurement, no gameplay change)

- **What:** first direct measurement of mid-rollout visible-state collision
  frequency under Searcher3 fair play (particle determinization). The §114
  obs-keyed descent failure predicted near-zero collisions (visible states
  diverge at every level) and the `leafCache` comment in
  `BattleScumSearcher3.h` asserted post-rollout states are "effectively
  unique" — both were expectations, never measured. This gates whether
  rollout transposition tables, path reuse, or move-ordering optimizations
  could ever help.
- **Tooling:** the existing `rollouttrace` mode emitted the recorded leaf's
  `obsHash` (deduped per decision by construction, so leaf-level collisions
  are 0 by design) but not per-state hashes. Added a trailing `stateHash`
  column (the row state's OWN `visibleHash`, equal to `obsHash` at step 0)
  to the diagnostic output only — `search::g_onRolloutStep` stays nullptr in
  all normal paths, so default behavior is byte-identical (verified: columns
  1-20 of a 2-seed replay are byte-identical to the §135a
  `rollouttrace_gate_64.csv` rows for those seeds).
- **Dataset:** `rollouttrace` replay of the §135a corpus
  `build/leafdiag_gate_64.csv`, 16 seeds (126700-126715), replay sims 1000,
  asc 0, full gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=
  build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=
  build/v_combat_utility_direct.txt`, V4 OOC gate arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1 + `STS_OOC_STRATEGIC_MARGIN=1.0`);
  100% leaf re-capture, no WARNINGs. Artifact:
  `build/rollout_trace.csv` (830,753 rows, 4,821 searches, 73,354
  trajectories). Run binary = commit 2fb271a + stateHash column; the §142
  (de75e6c) tok-globals change (50→41) and its uncommitted `NGLB 50→41`
  loader follow-up break loading of the deployed tok-net models, so a
  de75e6c-era binary cannot reproduce the §135a gate distribution (0%
  re-capture) — the reference build is the pre-§142 tree.
- **Result (per search = seed,fightIdx,decIdx; exact `visibleHash`):**
  - mid-rollout states (steps ≥ 1): **0.0891%** pooled collision rate
    (756,724 unique / 757,399 states); per-search mean 0.0916%, median 0%,
    max 50% (a 2-state outlier), 198/4,583 searches (4.3%) have any
    collision;
  - all states incl. leaves: 0.1340%;
  - cross-trajectory repeats within a search (same hash in ≥2 trajectories):
    0.139% of mid-rollout states;
  - coarse-feature upper bound (turn/HP/block/energy/strength/hand/draw/
    discard/monSumHp/monMaxHp/incomingDmg/isTerminal projection): 2.84% —
    the extra hashed fields (hand/pile contents, per-monster detail, powers,
    relics) differentiate ~97% of coarse-colliding states, confirming the
    coarse projection massively over-counts.
- **Verdict: DEAD END for rollout TT / path reuse / move-ordering caching.**
  Exact mid-rollout visibleHash collisions are 0.089%, ~11× below the 1%
  threshold; even cross-trajectory repeats (the only TT-usable signal) are
  0.139%. The §114 expectation is now data: under particle determinization
  every rollout step lands in an effectively unique visible state. Do not
  invest in rollout-state caching; the leafCache comment's "effectively
  unique" claim is confirmed.
- **Decision log:** `2026-08-09-rollout-collision-diagnostic.md`.

## §145 S3−belief−chain + canonicalized multiselect actions (STS_MULTISELECT_CANONICAL): implemented opt-in — null at 64 paired seeds (2026-08-09, local WSL)

- **What:** GAMBLE/EXHAUST_MANY multi-select actions enumerate every hand
  subset under the default `all` mode (up to 1023 edges for 10 identical
  cards). `STS_MULTISELECT_CANONICAL=1` canonicalizes each subset mask by
  the selected cards' identity multiset (`id`, upgradeCount, costForTurn,
  freeToPlayOnce, specialData) — the same equivalence the existing
  PLAYER_NORMAL duplicate-card collapse uses — and deduplicates identical
  multisets in `Action::pushMultiSelectActions`. Upgraded/temporarily
  modified copies remain distinct; only genuinely identical selections are
  collapsed. Default off, opt-in.
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_MULTISELECT_CANONICAL=1` for candidate);
  no tok-net (broken by §142, see §143 caveat); native OOC;
  floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`;
  combatVNet=ON @α=0.3; policyNet=ON; PVNet/off; asc 0; threads 12.
- **Parity:** `./build/test cardselect_parity` passes + new
  `cardselect_canonical` test verifies: 1024→256 masks (3 Strikes+3
  Defends+4 distinct, 10-card GAMBLE), 1023→11 (10 identical Strikes),
  [Strike,Strike,Strike+,Defend] keeps {0,1} and {0,2} distinct while
  collapsing {1,2}→{0,2}. `STS_MULTISELECT_CANONICAL=0` is behaviorally
  identical to unset.
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 20.3% win / 39.1 floor / 8.2 HP / 22.0 cpu-s/run.
  **−1.6pp (95% CI [−4.6, +1.5]), 1/64 discordant (2%), cpu 0.99×.**
  Null — 4× branching reduction at GAMBLE states is decision-neutral
  within sampling noise. GAMBLE/EXHAUST_MANY states are rare and the
  current uniform-prior PUCT already dilutes visits harmlessly; the
  expected benefit (more focused search on non-GAMBLE turns) is too small
  to measure at 64 seeds. The parity test is the real win — canonicalization
  preserves correctness under the full cardselect contract.
- **Verdict:** env stays opt-in default-off. Gate pending for larger sample
  (256 seeds) to confirm the null, but the low discordance (1/64) strongly
  suggests zero effect; priority is low.
- **Decision log:** `2026-08-09-multiselect-canonicalization.md`. Code:
  `src/sim/search/Action.cpp::pushMultiSelectActions` (multiSelectCanonical,
  cardIdentityKey, dedup); `apps/test.cpp::testCardSelectCanonical`.

## §146 Searcher2 transposition table (STS_TT) — first-ever benchmark: CATASTROPHIC, 0% win (2026-08-09, local WSL)

- **What:** `g_useTT` / `STS_TT` in `BattleScumSearcher2.cpp` shares value
  statistics (`simulationCount`, `evaluationSum`) across action-order-
  equivalent states via a hash table lookup in `selectBestEdgeToSearch`,
  `selectBestValidEdgeToSearch`, and `evaluateEdge`. Implemented but NEVER
  benchmarked through the entire §99–§135 experiment series.
- **Config:** `one_combat bestbench 1000 32 0 126700 <out.csv>`;
  `STS_FAIR=1` (S2 fair); asc 0; threads 12. Token-net, vnet, etc. not
  relevant (Searcher2-only arm).
- **Results (32 paired seeds, S2-fair @1k):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---|---|---|
  | TT off (control) | **18.8%** | 37.1 | 9.5 | 9.08 |
  | TT on (candidate) | **0.0%** | 20.1 | 0.0 | 3.51 |
  | Δ (on − off) | **−18.8pp** | −17.0 | −9.5 | −5.57 |

  Every single TT-on run died with 0 HP. The TT does make search ~2.6×
  faster per run, but destroys play quality catastrophically.
- **Mechanism (Inference):** plausible causes are (a) hash collisions in
  `battleStateHash`, (b) value statistics shared across states that are
  action-order-equivalent but NOT value-equivalent under fair
  determinization (different enemy intents / residual HP per particle
  world), or (c) stale/incorrect stateHash propagation when the searcher
  reuses subtrees. The TT key includes all RNG streams, which should make
  it exact-match-only — hash collisions are most likely.
- **Verdict: CLOSED.** Do not port the TT to Searcher3 or invest further.
  The TT code stays in the tree (off by default) as a cautionary artifact.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher2.cpp::g_useTT` (36), `battleStateHash` (63),
  `selectBestEdgeToSearch` (501), `selectBestValidEdgeToSearch` (545),
  `evaluateEdge` (496); parsed `STS_TT` in `apps/one_combat.cpp::main`
  (line 9237).

## §147 Dynamic alpha by rollout length (STS_VNET_ALPHA_LEN, A2): implemented opt-in — negative direction at 64 paired seeds (2026-08-09, local WSL)

- **What:** plan-rollout-experiments-2026-08-07.md §3 A2 (dynamic α by
  rollout length). Replaces the flat vnet/pvnet alpha at the leaf blend
  site with a lookup over the rollout action count L. Pre-registered table
  {≤2:0.1, 3–5:0.2, 6–10:0.4, >10:0.6}: short rollout = trustworthy
  terminal → low α (trust rollout); long rollout = noisy → high α (trust
  learned leaf). Applied to both vnet and pvnet blends. Env:
  `STS_VNET_ALPHA_LEN=1` (default off), `STS_VNET_ALPHA_LEN_TABLE`
  overrides the table (format "ceil:alpha,...").
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_VNET_ALPHA_LEN=1` for candidate);
  no tok-net (broken by §142); native OOC; combatVNet=ON @flat α=0.3
  (overridden per-leaf by the table when flag is on); asc 0; threads 12.
- **Parity:** `STS_VNET_ALPHA_LEN=0` vs unset — 8/8 seeds identical
  (confirmed).
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 18.8% win / 38.2 floor / 7.4 HP / 22.5 cpu-s/run.
  **−3.1pp (95% CI [−14.6, +8.3]), 14/64 discordant (22%, 6 up / 8 down),
  cpu 1.01×.** Direction negative, high discordance (22%). Avg rollout
  length ~14 actions → most leaves land in the >10 bucket (α=0.6) — the
  table effectively RAISES α for the dominant case from the calibrated
  optimum 0.3, pushing more weight onto the learned leaf where the
  terminal outcome has already proven load-bearing (§133: "long-horizon
  terminal grounding is load-bearing"). The short-rollout buckets get
  lower α (0.1–0.2) but are too rare to offset.
- **Note on table inversion:** the plan's pre-registered table
  {≤2:0.1,…,>10:0.6} makes α INCREASE with rollout length (trust leaf
  more when rollout is noisy). The task specification during this
  session had the inverse table {≤2:0.6,…,>10:0.2} with opposite
  rationale — the task was an error, and the plan's table was
  implemented. The inverse would make α DECREASE with length, pushing
  the flat-0.3 calibrated optimum toward ~0.2 for the dominant >10
  bucket — directionally even worse.
- **Verdict: negative direction at 64 seeds; env stays opt-in default-off.**
  Table inversion (short→low, long→high) would flip the α direction for the
  dominant long-rollout bucket and is testable as a follow-up, but the
  current negative signal + high discordance makes either variant a weak
  candidate. The flat calibrated α=0.3 is the robust default.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher3.cpp::alphaForRolloutSteps`, `g_vnetAlphaLen`,
  `g_vnetAlphaLenTable`; parsed in `apps/one_combat.cpp::main`.

## §140 Stall-battle hang in the S3 fair battle loop: root-caused and fixed (2026-08-08, local + GCP)

- **Symptom:** datagen seed 300865 (and any seed hitting the same state) never
  completed: the seed's single worker thread spun at ~1 core with zero rows
  written (rows buffer until seed end), no deadlock, all backtraces showing
  normal busy search activity.
- **Root cause:** `ScumSearchAgent2::playoutBattleFair` (and the other three
  battle loops) run `while (bc.outcome == Outcome::UNDECIDED) { search; takeAction; }`
  with **no iteration bound**. StS has no stall timer, so a fight can last
  forever; the S3 search plays such fights defensively (blocks/heals more than
  the boss damages) and never finishes them. Seed 300865 reaches the act-1
  boss (encounter 31, floor 16) — the cheap eval policy dies there instantly,
  the search stalls it forever. ~1/1000 seeds hit a stallable fight, which is
  why 999/1000 datagen seeds completed normally.
- **Fix:** `kMaxBattleDecisions = 1000` stall guard in all four battle loops
  (fair S3, fair S2, non-fair S3, non-fair S2); an exceeded battle is treated
  as `PLAYER_LOSS` with a `[battle-stall]` warning. Normal battles finish in
  well under 100 decisions, so default behavior is unchanged (the counter is
  separate from `decisionIdx`, which seeds the per-decision searcher).
- **Verification:** seed 300865 locally: 3 stall warnings, completes in 245s,
  746 rows, rc=0; on GCP: same, chunk 2 now 500/500 seeds (273,518 rows).
