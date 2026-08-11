# Encounter Marginalization — Session Report

Date: 2026-08-10

Status: **ARCHIVED intermediate snapshot.** Superseded by
`docs/knowledge-base/encounter-marg-final-summary-2026-08-10.md`.

---

## 1. Stack Bridge

Fresh-tree vs obs-stable N=1 reuse on V4, 64 paired seeds (210000–210063):

| Arm | Wins | Delta |
|---|---|---|
| Fresh | 32/64 = 50.0% | — |
| Reuse | 36/64 = 56.2% | +6.2pp |

CI [−4.7, +17.2]. Favorable direction. Adopted reuse as frozen combat controller for new OOC research.

---

## 2. Diagnostic Mode: `strategicmarggen`

New mode in `apps/one_combat.cpp`. Evaluates every candidate action at V4-owned OOC decisions under two regimes:

- **Regime F**: fixed hidden world (same encounters as live run)
- **Regime M**: encounter-marginalized (`resampleRemainingActEncounters` on a detached copy)

All actions in sample `h` share the same hidden world (CRN pairing). K=3 fights, 150/100/50 sim schedule, bootstrap=true — identical to Tier-B continuation contract.

Uses the exact production V4 OOC policy (`stepFrozenV4Ooc`) for source trajectories. Records exact fallback via `stratFingerprint` matching. Records V4 predictions, margin, fired status, executed action, and override flag.

**Output CSV schema:** `seed,decIdx,act,floor,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,continuationSeed,hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,utility,fallbackIdx,fallbackExact,v4ModelIdx,v4Margin,v4Threshold,v4Fired,v4ExecutedIdx,v4Override,richState`

---

## 3. Bugs Fixed (from handoff)

| Bug | Issue | Fix |
|---|---|---|
| 1 | Wrong utility (last-fight probe, not bootstrap) | `evaluateStrategicBranch` helper uses `finishOocCounterfactual(..., bootstrap=true)` — Tier-B contract |
| 2 | F/M used different continuation RNG | Same `continuationSeed` for both regimes per sample. Verified: 0 mismatches |
| 3 | Source trajectory used `stepOutOfCombatPolicy` | `stepFrozenV4Ooc` replicates exact V4 gate stack |
| 4 | Gate ownership hard-coded | Checks `cardRewardCount`, `selectScreenType==UPGRADE`, etc. |
| 5 | Action 0 as fallback | `stratFingerprint`-based exact fallback matching. 92% exactness |
| 6 | `utility > 5` proxy for won | `labelWon` recorded directly from `OocCounterfactualResult` |
| 7 | BATTLE crash | Added BATTLE handling to `stepFrozenV4Ooc` |

---

## 4. Corrected Diagnostic Results (30 seeds, 330 decisions, H=8)

| Metric | Value |
|---|---|
| Best-action changes | **191/330 = 57.9%** |
| Marginal regret (mean) | 3.42 |
| Marginal regret (p75) | 4.89 |
| Marginal regret (max) | 33.50 |
| V4 overrides (exact fallback) | 65 |
| V4 reversals (good→bad) | **7/65 = 10.8%** |
| V4 good both | 31/65 = 47.7% |
| V4 bad both | 16/65 = 24.6% |

**Verdict: PROMOTE.** Encounter marginalization materially changes action rankings and flips ~11% of exact V4 overrides.

---

## 5. Trainer Pipeline (Phase B ready)

- `tools/convert_marg_to_trainer.py` converts diagnostic CSV to M0/M1 trainer-compatible CSVs
- M0 uses fixed-world label averages, M1 uses marginalized label averages
- Both share identical non-label columns (verified invariant)
- `richState` column added to diagnostic output for trainer schema compatibility
- Missing: source terminal outcome (`won/endFloor/endHp` from the source run) — needs addition to C++ diagnostic

---

## 6. Remaining

| Phase | Item | Status |
|---|---|---|
| A2 | Identity marginalization test (M_identity) | Not done |
| A3 | Hidden-resampling test | Not done |
| A4 | Source trajectory parity (8-seed) | Partial (flags differ) |
| A6 | Full gate-stratified diagnostic | 330 decisions done |
| B | Generate M0/M1 with source terminal outcome | Needs C++ addition |
| C | Train M0 vs M1 | Not started |
| D | 64-seed gameplay gate | Not started |

---

## 7. Key artifacts

| What | Where |
|---|---|
| Diagnostic mode | `apps/one_combat.cpp` `strategicMargGen()` (~line 8250) |
| Branch label helper | `apps/one_combat.cpp` `evaluateStrategicBranch()` (~line 8170) |
| V4 OOC step | `apps/one_combat.cpp` `stepFrozenV4Ooc()` (~line 8190) |
| M0/M1 converter | `tools/convert_marg_to_trainer.py` |
| Corrected diagnostic | `/tmp/marg_corrected.csv` (26K rows, 330 decisions) |
| Stack bridge | `build/ooc_bridge_{fresh,reuse}_64_1786313686.csv` |

---

## 8. Verification

```bash
cmake --build build --target one_combat -j4

# Full diagnostic (needs V4 env vars)
env STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
  STS_S3_LIVE_VALID=1 STS_S3_PARTICLES=64 \
  STS_VNET=build/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
  ./build/one_combat strategicmarggen 30 1000 150 3 8 200 /tmp/diag.csv 500000

# Convert to M0/M1
python3 tools/convert_marg_to_trainer.py /tmp/diag.csv /tmp/m0.csv /tmp/m1.csv
```

---

## 9. Central question

> After controlling for continuation RNG, source-policy distribution, target semantics, and exact runtime fallback behavior, does averaging over unknown future encounter identities still change strategic action values enough to improve actual gameplay?

**Answer from diagnostic: Yes — 57.9% of decisions change best action, and 10.8% of exact V4 overrides reverse from beneficial to harmful. This justifies matched M0/M1 training.**
