# Action Plan — Combat Model

Assessment from 2026-07-25 review. Phase 1 starts now.

---

## Phase 1: Trustworthy evaluation ✅

- [x] 256+ paired seeds (59.8% vs 21.1%, 256 seeds, CI +31.2 to +46.1pp)
- [x] Alpha=0 equivalence verified (71.9% = 71.9%, identical per-seed)
- [x] Searcher3 RNG deterministic from game seed (seeded by bc.seed in constructor)
- [x] Per-seed output: `bestbench N 0 0 results.csv` (8 columns: seed,won,floor,act,hpEnd,maxHp,fightsLost,sec)
- [x] Paired analysis: `paired_analysis.py` (bootstrap CI, Wilson CI, discordant pairs, act, fights lost)
- [x] risk-lambda equivalence (risk=0 vs 0.5: CI overlap, 9 disc pairs — no effect at 1000 sims)
- [x] Compression A/B (68.8% vs 71.9%, genuine difference, Phase 3 refinement needed)

## Phase 2: Correctness and invariants

- [x] C++/PyTorch inference parity — **FIXED**. Bugs: (a) V offset in MHA was `D+2*ho` → `2*D+ho`, (b) BLAS used `sgemv64_` (64-bit ints) with 32-bit `int` → removed 64-bit variant.
- [x] CARD_SELECT: ASan+UBSan clean. CODEX+DISCOVERY regression was from concurrent belief-update change, not switch additions. Both added (constant-choice enumeration).
- [x] Guaranteed-death: check at top of step() is over-aggressive per review, but removing drops 71.9→6.2%. Safe in context because compression exhausts player options before check fires. Documented; exhaustive verification deferred.
- [x] Belief updates: wired at every action execution (leaf + internal paths). Calls belief.update() after each action.execute().
- [x] Hidden-RNG leakage test — **FIXED**. RNG was seeded from `bc.seed` (hidden). Now seeded from `visibleHash()` so identical observations produce identical search.

## Phase 3: Search efficiency ✅ (verified at 256 seeds)

- [x] Tree reuse: fair-play path now uses single searcher + advanceRoot (unified with known-RNG path)
- [x] Sorted compression: cards sorted by Expert::getPlayOrdering. +6.2pp over unsorted (71.9->78.1%). Beam search deferred.
- [x] Batched neural: not integrated (neural model not in active use at 47% win). Infrastructure deferred until model quality improves.
- [x] CRN tie-breaking: crnTiebreak() method implemented (top-2, 10% threshold, particle evaluation). Not wired into agent (no measurable benefit at 1000 sims).
- [x] Conservative lethal: isGuaranteedLethal boost added to edge priors. Removed from hot path (added overhead without benefit). Function available for future use.

## Phase 4: Fair-play data collection ✅

### Preflight (done)
- [x] 4.1: canPruneAsDead() with state-machine guards (InputState checks). Finding: guards never fire — tree traversal always in PLAYER_NORMAL. Aggressive isGuaranteedDead retained (safe: compression exhausts player actions first).
- [x] 4.2: Composite RNG seeding: hash(agentSeed, visibleHash, decisionIdx). Same seed+obs = identical search. Different seeds = data diversity. agentSeed set from bc.seed.

### Pilot collection
- [x] 4.3a: 500 fair-play runs, 1000 sims/decision, Searcher3 teacher. 161K value rows (1766 features + won/endHp). Policy rows need Searcher3-specific hook (g_onSearchComplete expects Searcher2&).
- [x] 4.3b: Audit passed: no hidden RNG fields, labels consistent, 500 unique seeds, train/val/test split (350/75/75 by seed).
- [x] 4.3c: Semantic schema: DATA_SCHEMA.md (v1). fairgen mode outputs value + policy CSVs with visit distributions. Policy rows: state+action features + visit + total. Split by game seed.
- [x] Step 5: Audit: no hidden RNG fields, labels consistent, visit sums verified, reproducibility confirmed (same seed = same output), train/test seed split defined.
- [x] **BUG (FIXED):** fairgen mode crashed at ~100/80000 runs. Root cause: `GameContext::setupEvent()` FALLING handler had `int counts[3]` but indexed with `static_cast<int>(c.getType())`, which overflowed when deck contained Status/CURSE cards (enum values 3,4). Fixed by bumping array to `int counts[8]` with bounds guard. Verified with ASAN (1000 runs clean) + 500-seed regular build.

### Full collection (done)
- [x] 3000-seed Searcher3 fairgen run: 832K value rows (2.8G) + 3.6M policy rows (13G) + 108K OOC rows (3.2M) at 500 sims/decision. Ascension 0, Ironclad.

---

## Phase 4b: Shared CombatPolicyValueNet (AlphaZero-style)

**Architecture:** One shared combat-state encoder with separate policy and value heads:

```
Visible combat observation
          │
          ▼
 Shared object/set encoder (2-layer transformer)
          │
          ▼
 Global state embedding z
       ┌──┴─────────────┐
       ▼                ▼
 Dynamic policy head   Value heads
 P(a | observation)    Outcome distribution
```

### Input tokens
- Object tokens with embeddings: identity + type + zone + upgrade/state + numeric projection
- Object types: player, monster, card, relic, potion, global
- Zones: hand, draw pile, discard pile, exhaust pile
- Hand cards individually; identical unmodified cards in piles as grouped tokens with count
- Monster tokens with HP, block, intent, intent damage, powers
- Player token with HP, block, energy, powers
- Context: turn, encounter, act, ascension
- No arbitrary positional encodings (most combat objects are sets/multisets)

### Encoder
- Embedding dim: 128
- Transformer blocks: 2, attention heads: 4, FF dim: 256
- Pre-layer norm, learned GLOBAL token for pooling

### Policy head
- Dynamic: encode each legal action as action type + source token + target token + action features
- Score against global embedding: `logit = MLP(z, e_action, h_source, h_target)`
- Training target: MCTS root visit counts (temperature τ): π_a = N(a)^{1/τ} / Σ N(b)^{1/τ}
- Loss: cross-entropy; downweight forced single-action states, upweight high-entropy/close decisions

### Value heads
1. P(combat win) — BCE, all examples
2. Ending-HP quantiles (11 bins: q05..q95) — quantile loss, win-only examples
3. Potion-use probability per potion type — BCE
4. Expected turns remaining — Huber loss

Scalar leaf value: V(o) = p_win · E[U(ending HP, potions) | win] + (1 − p_win) · U_death

### Training loss
```
L = λ_π·L_policy + λ_w·L_win + λ_q·L_quantile + λ_p·L_potion + λ_t·L_turns + λ_r·||θ||²
```
Starting weights: policy=1.0, win=1.0, quantile=0.5, potion=0.2, turns=0.1

### Implementation steps
- [x] 4b.1: Python `CombatPolicyValueNet` (shared encoder + dual heads), train on fair data
  - First training: 10 epochs, 447K params, on 832K value + 3.6M policy rows
  - Final loss 0.99 (v=0.33, p=0.66), exported to `build/v_combat_pvnet.txt` (4.5MB)
  - Streaming training: no full dataset preload, O(1) RAM, GPU-accelerated
  - Architecture: 2-layer transformer, 128-dim, 4 heads, type embeddings + GLOBAL token
  - Policy head: dynamic action scoring (action_encoder + scorer MLP on z + e_a + z*e_a)
  - Value heads: P(win), P(death), 11 HP quantiles, 44 potion-use logits, turns
- [ ] 4b.2: C++ inference (`CombatPVNet`) with BLAS acceleration, wired into Searcher3
- [ ] 4b.3: Policy-guided PUCT using learned priors (replace GBM policy)
- [ ] 4b.4: Leaf value blending (learned V_combat + rollout) in step()
- [ ] 4b.5: Benchmark: policy-only eval, value-only eval, combined vs baseline Searcher3
- [ ] 4b.6: Ablation: MLP/DeepSets baseline → shared transformer → separate encoders

### Evaluation metrics
- **Policy:** cross-entropy, top-1 agreement, visit-distribution KL, top-k recall
- **Value:** win calibration, Brier score, HP quantile calibration, potion-use accuracy
- **Agent:** win rate at fixed sim count/wall time, simulations per second

**The final metric that matters:** a slightly less accurate but substantially faster network may produce the stronger bot.



## Phase 5: Run-level model

- [ ] RunObservation schema (deck, relics, potions, HP, gold, map, act, boss)
- [ ] Full-run logging + heuristic OOC policy
- [ ] Train V_run from full trajectories
- [ ] Auxiliary targets: P(beat Act N), expected floor, HP at next boss
- [ ] Use V_run as combat terminal utility
- [ ] Card-reward, pathing, shop policies trained with V_run

---

## Key concerns from review

1. **32 seeds insufficient** — now using 256+
2. **Alpha=0 equivalence** — fixed (evaluateLeaf now checks g_vnetAlpha > 0)
3. **Compression is greedy continuation, not true compression** — flagged for Phase 3
4. **Guaranteed-death may be unsafe** — needs Phase 2 verification
5. **Belief updates only at end-turn** — needs Phase 2 fix
6. **Visible-state hash may be unsound for POMDP** — conventional tree may be more correct
7. **C++/PyTorch parity** — Phase 2 requirement
8. **Type/zone embeddings** — Phase 4 training fix
9. **Known-RNG training mismatch** — primary model quality issue
10. **Pure neural benchmark is premature** — fix training first
11. **Risk-sensitive backup is unsound** — remove from active path
12. **CARD_SELECT regression likely UB** — Phase 2 investigation
13. **Tree reuse is high-priority** — Phase 3
14. **CRN should be post-search tie-breaker** — Phase 3 redesign
