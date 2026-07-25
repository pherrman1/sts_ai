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

## Phase 4: Fair-play model data

- [ ] Generate fair-play combat data with Searcher3 as teacher
- [ ] Train policy on fair MCTS visit distributions
- [ ] Train value model on fair-play outcome distributions
- [ ] Verify model calibration (rank correlation, death-prob calibration)
- [ ] Hybrid leaf evaluator: alpha*V_network + (1-alpha)*V_short_rollout

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
