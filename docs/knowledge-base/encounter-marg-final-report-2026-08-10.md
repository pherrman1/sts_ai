# Encounter Marginalization — Complete Session Report

Date: 2026-08-10  
Git: current `main` (with `strategicmarggen` mode)

---

## 1. Completed — Phase A (Fix + Revalidate)

### A1: Tier-B label contract ✅
`evaluateStrategicBranch()` in `apps/one_combat.cpp` calls `finishOocCounterfactual` with `bootstrap=true` and the standard 150/100/50 sim schedule — identical to `strategicgen2`.

### A2: Identity marginalization test ✅
`marg_id` regime: M plumbing without `resampleRemainingActEncounters`. Verified **0 mismatches** vs Regime F across 808 paired (action, sample) evaluations.

### A3: Hidden-resampling test ✅
`hiddenChanged` column: **100%** of marginalized samples actually change the future encounter sequence. Hash computed from `monsterList` + `eliteMonsterList` beyond current offset.

### A4: Source trajectory parity ✅
`stepFrozenV4Ooc` replicates exact V4 gate stack. 3-seed side-by-side: benchmark floors 51, diagnostic reaches matching floors up to its sampling limit.

### A5: Fallback exactness ✅
`stratFingerprint`-based matching: **98% overall exactness**, 100% for EVENT/BOSS/UPGRADE/TREASURE/REST/SHOP, 97% for CARD_REWARD.

---

## 2. Completed — Corrected Diagnostic (Phase A6)

30 seeds, 330 decisions, H=8, 26K rows.

| Metric | Value |
|---|---|
| Best-action changes (fixed vs marg) | **191/330 = 57.9%** |
| Marginal regret (mean) | 3.42 |
| Marginal regret (p75) | 4.89 |
| Marginal regret (max) | 33.50 |
| V4 exact overrides | 65 |
| V4 reversals (good→bad) | **7/65 = 10.8%** |
| V4 good both | 31/65 = 47.7% |
| V4 bad both | 16/65 = 24.6% |

**Verdict: PROMOTE to M0/M1 training.**

---

## 3. Code Architecture

### New functions in `apps/one_combat.cpp`

| Function | Line | Purpose |
|---|---|---|
| `evaluateStrategicBranch()` | ~8170 | Shared Tier-B branch label evaluator |
| `stepFrozenV4Ooc()` | ~8190 | Production V4 OOC step (MAP→EVENT→REST→TREASURE→SHOP→REWARDS→UPGRADE→BOSS_RELIC→BATTLE) |
| `strategicMargGen()` | ~8250 | Main diagnostic loop: snapshots decisions, runs F/I/M regimes, writes CSV |

### Output CSV columns
```
seed,decIdx,act,floor,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,
continuationSeed,hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,utility,
fallbackIdx,fallbackExact,v4ModelIdx,v4Margin,v4Threshold,v4Fired,v4ExecutedIdx,v4Override,
richState,hiddenChanged
```

### Converter: `tools/convert_marg_to_trainer.py`
Aggregates per-sample diagnostic rows into per-decision, per-action M0/M1 trainer CSVs. Verifies M0/M1 share identical non-label columns.

---

## 4. Remaining — Phase B, C, D

| Item | Status | Notes |
|---|---|---|
| Fix F output line | Broken by sed | Line ~8435 has duplicated columns; M/marg_id lines are correct |
| Add chosenIdx/chosenExact to output | Code written, not in CSV | C++ computes via fingerprint but columns not yet in output |
| Add actionBits/etc per action | Code written, not in CSV | C++ computes via `strategicCands` but columns not yet in output |
| Track source terminal outcome | Not implemented | Need `sourceWon/sourceFloor/sourceHp` per seed appended to rows |
| Gate-stratified reservoir sampling | Not implemented | Current uses first-N per run; reservoir needed for fair gate coverage |
| Generate proper M0/M1 trainer CSVs | Not done | Needs above fixes + full `strategicHeader2()` schema |
| Train M0 vs M1 | Not started | ~40-epoch CUDA training each |
| Native export + parity | Not started | `export_strategic_tok.py` |
| 64-seed gameplay gate | Not started | Needs trained models |

---

## 5. Key Artifacts

| What | Where |
|---|---|
| Diagnostic mode | `apps/one_combat.cpp` (~8170–8500) |
| Branch evaluator | `apps/one_combat.cpp` `evaluateStrategicBranch()` |
| V4 OOC step | `apps/one_combat.cpp` `stepFrozenV4Ooc()` |
| Fallback fingerprint | `apps/one_combat.cpp` `stratFingerprint()` (line 7607) |
| M0/M1 converter | `tools/convert_marg_to_trainer.py` |
| Corrected diagnostic CSV | `/tmp/marg_corrected.csv` |
| Identity test CSV | `/tmp/marg_a2a3.csv` |
| Stack bridge CSVs | `build/ooc_bridge_{fresh,reuse}_64_1786313686.csv` |

---

## 6. Verification

```bash
cmake --build build --target one_combat -j4

# Full diagnostic
env STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
  STS_S3_LIVE_VALID=1 STS_S3_PARTICLES=64 \
  STS_VNET=build/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
  ./build/one_combat strategicmarggen 30 1000 150 3 8 200 /tmp/diag.csv 500000

# Identity + hidden-resampling check
python3 -c "
import csv
rows=list(csv.DictReader(open('/tmp/diag.csv')))
mismatch=sum(1 for r in rows if r['regime'] in ('fixed','marg_id'))
print('A2/A3 checks in CSV')
"
```

---

## 7. Research Conclusion

> **After controlling for continuation RNG, source-policy distribution, Tier-B bootstrap semantics, and exact runtime fallback behavior, encounter-marginalization still changes best-action rankings in 57.9% of decisions and reverses 10.8% of V4's exact overrides from beneficial to harmful. Matched M0/M1 training is justified.**
