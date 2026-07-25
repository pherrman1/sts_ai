# Combat Model Plan

Each section starts with the goal from the spec, then current implementation status.

---

## 2.1 Never expose the real RNG state

**What:** `CombatObservation` contains only what a player can know. Search maintains `Particle = HiddenBattleState` and `Belief`. Tree keyed by visible observations. All 6 RNG streams resampled per particle.

**Done:**
- `CombatObservation`, `HiddenBattleState`, `Belief` structs — working
- `BattleScumSearcher3` with conventional tree, 6 RNG streams per particle, observation caching per node
- `ensureObservation()` — computes `CombatObservation` once per node, reuses on subsequent traversals
- `updateBelief()` wired at end-turn boundaries (resamples particles to match observed draws)
- `Random(seed0, seed1)` constructor bug fixed (matched `(uint64_t, int32_t targetCounter)` overload)

**Deferred:**
- Hash-keyed tree (`std::unordered_map<uint64_t, Node>`) — draw pile hash is now order-independent, but conventional tree at 71.9% is simpler. Hash tree remains future optimization for action-order transpositions.

**Finding:** Belief update at end-turn has minimal impact at 1000 sims — uniform particle sampling dominates the weighted approach.

---

## 2.2 Deterministic chain compression

**What:** Compress deterministic actions (play Strike on fixed target) into sequences. Only execute first action, observe result, search again.

**Done:** Inline compression in `step()`. After executing chosen edge, play additional non-drawing, non-targeting cards before rollout (up to 10 steps). Each action validated individually — hand must decrease by exactly 1 (no draws, no weird effects). Stop when stochastic boundary hit.

**Finding:** +3.1pp (68.8% → 71.9%) at 1000 sims. Compression effectively increases search depth per simulation by exploring multiple deterministic card plays in sequence.

---

## 2.3 PUCT selection

**What:** AlphaZero-style policy-guided tree rule: `Q(s,a) + c_puct * P(a|s) * sqrt(N(s)) / (1 + N(s,a))`.

**Done:** Fully working. Formula matches Searcher2: Q normalized by evalRange, smoothing `sum/(visits+1)`, exploit only after first winning line found. Policy priors from production policy net.

---

## 2.4 Dynamic action scoring

**What:** Enumerate legal actions, encode each, score dynamically. No giant fixed output.

**Done:** `enumerateActionsForNode()` handles PLAYER_NORMAL and CARD_SELECT (ARMAMENTS, CODEX, EXHUME, EXHAUST_ONE). 14 canonical action features scored by policy net.

**Missing:** DISCOVERY, DUAL_WIELD, FORETHOUGHT, WARCRY, HEADBUTT, SECRET_TECHNIQUE, SECRET_WEAPON, EXHAUST_MANY, GAMBLE. These access discard/draw piles (order-dependent in determinized ISMCTS state). CODEX was the only safe addition (constant enumeration, no state access). Remaining tasks are low priority for ascension 0 Ironclad — the `default: pickCount` fallback handles them.

**Finding:** Even constant-number tasks like DISCOVERY (3 choices) cause regressions when added to the switch statement. Root cause unclear — possibly jump table misalignment.

---

## 2.5 Combat state representation

**What:** Set/transformer encoder — card encoder shared across zones, separate monster/player/global encoders, attention/pooling.

**Done:**
- `CombatDistNet` transformer: 4 heads × 2 layers, 128-dim embeddings, 256-dim FFN, attention pooling, 5 output heads
- Trained on 155K → 2.8M `distgen` rows, exported (`build/v_combat_dist.txt`)
- Native C++ inference with multi-head self-attention
- BLAS-accelerated matmul via numpy's bundled OpenBLAS (8x speedup)
- Loaded via `STS_DIST_VNET=build/v_combat_dist.txt`

**Performance:** 10.7K sim/s with BLAS (vs 1.3K scalar, vs 140K heuristic).

**Missing:**
- Verify C++ inference vs PyTorch (no parity check)
- Type embedding so transformer distinguishes card vs relic vs monster tokens

---

## 2.6 What the combat value predicts

**What:** Distributional predictions — death probability, win probability, HP quantiles, potion use, turns remaining. Derive scalar from run-level context.

**Done:**
- `CombatDistOutcome` struct with all 5 fields
- `riskAdjustedValue(lambda, maxHp, winBonus)` computes `P(win)*(winBonus + E[HP]) - lambda*(E[HP] - CVaR)`
- Distgen data pipeline: 2.8M rows with `endTurn` + per-potion `pUsed` labels
- Model integrated into Searcher3 — when loaded, rollouts skip and every leaf evaluated by transformer
- Win rate: 46.9% (pure neural, 1000 sims) vs 68.8% (heuristic + rollout)

**Deferred:** Retrain with fair-play data. Current model trained on known-RNG `combatgen` data; ISMCTS needs fair-play labels. The V_combat GBM has the same issue — trained on known-RNG data, degrades ISMCTS when blended (alpha sweep showed best at alpha=0, i.e., no blend).

---

## 2.7 Risk-sensitive search

**What:** `U = E[V] - lambda * DownsideRisk(V)`. Distributional value, quantile-based risk scoring.

**Done:**
- `DistStats` per Node tracks `loQ20` and `loQ05` via exponential moving average in `backpropagate`
- PUCT uses risk-adjusted Q: `avg - riskLambda*(avg - loQ05)` when stats are reliable (>3 visits)
- `riskLambda` is configurable (0.5 default)

**Finding:** Risk-sensitive PUCT doesn't move win rate at 1000 sims. The rollout-based search has low outcome variance per node — `loQ05 ≈ avg` so the risk term is near zero. Would matter once a distributional value function produces varied outcomes.

---

## 2.8 Transpositions and dominance pruning

**What:** Visible-state hash. Merge equivalent states. Dominance pruning. Lethal detection.

**Done:**
- `isGuaranteedDead()` wired into `step()` at 4 checkpoints — prunes branches where incoming damage exceeds HP+block, backpropping 0 immediately. This is the largest single win rate driver (+43.8pp vs Searcher2 fair-play).
- `isGuaranteedLethal()` defined (total attack damage in hand vs enemy HP) but not wired.

**Deferred:**
- Dominance pruning — `dominates()` exists but computing child states per edge is too expensive. Needs cheap state comparison.
- Guaranteed lethal boost — `isGuaranteedLethal()` could boost priors of finishing moves. Not wired.

---

## 2.9 Variance reduction (CRN)

**What:** Evaluate root actions under identical hidden-state particles. Sample 128 RNG seeds, apply same set to all root candidates.

**Done:**
- `prepareCRNParticles()` creates 128 shared particles in constructor
- `warmStartRootCRN()` evaluates each root action under all particles

**Finding:** Warm-start approach broke PUCT (15.6% vs 68.8%). Setting `simulationCount=0` (Q only, no visit change) dropped to 3.1%. The CRN prior distorts the exploration-exploitation balance. Post-search tie-breaker design is needed.

---

## Current Performance (256 paired seeds 0..255, asc 0, 1000 sims/decision)

| Metric | Searcher2 fair-play | Searcher3 | Delta |
|---|---|---|---|
| Win rate | 21.1% [16.5-26.5] | 59.8% [53.7-65.6] | +38.7pp [+31.2, +46.1] |
| Avg floor | 36.8 | 41.2 | +4.4 |
| Avg HP end | 9.2 | 22.7 | +13.5 |
| Avg act reached | 2.34 | 2.57 | +0.24 |
| Avg fights lost | 0.79 | 0.36 | -0.42 |
| Avg sec/run | 7.72 | 3.40 | -4.31 |
| Discordant pairs | — | — | 135/256 (53%) |
| S3-only wins: 117, S2-only wins: 18 |

Bare searcher speed: 140K sim/s (heuristic), 10.7K sim/s (dist model + BLAS).

---

## Deferred items

- **Tree reuse between turns.** Searcher2 reuses the search tree via `advanceRoot`. Searcher3's agent integration always rebuilds.
- **Type embedding for transformer tokens.** Card and relic tokens share the same 128d space.
- **Distributional value function.** Needs fair-play combatgen data. V_combat GBM and dist transformer both trained on known-RNG — degrade ISMCTS.
- **CRN at root (2.9).** Needs post-search tie-breaker design.
- **Dominance pruning (2.8).** Needs cheap state comparison.
- **Hash-keyed tree (2.1).** Needs order-independent transposition lookups.
- **Full CARD_SELECT tasks (2.4).** Needs ISMCTS-safe discard/draw pile access.
