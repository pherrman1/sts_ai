# Encounter Marginalization — Phase A Complete, Phase B/C/D Done

Date: 2026-08-10

Status: Final evidence report. Current follow-up routing is maintained in
`docs/knowledge-base/evaluation/current-research.md`.

---

## 1. What was accomplished vs the CLI queue

All 24 items from the handoff. Status at completion:

### Bugs fixed (1–10)

| Bug | Issue | Fixed |
|---|---|---|
| 1 | Wrong utility (last-fight probe, not Tier-B bootstrap) | `evaluateStrategicBranch()` uses `finishOocCounterfactual(bootstrap=true)` |
| 2 | F/M used different continuation RNG | Same `continuationSeed` for both regimes. Verified: 0 mismatches |
| 3 | Source trajectory used heuristic, not V4 | `stepFrozenV4Ooc()` replicates exact V4 gate stack |
| 4 | Gate ownership hard-coded wrong | Checks `cardRewardCount`, `selectScreenType==UPGRADE`. UPGRADE_SELECT included |
| 5 | Action 0 as fallback | `stratFingerprint`-based matching. 98% exactness overall. Per-gate: EVENT 100%, CARD 97%, BOSS/UPGRADE/TREASURE/REST/SHOP 100% |
| 6 | `won` column bogus (`utility > 5` proxy) | `labelWon` recorded directly from `OocCounterfactualResult` |
| 7 | Source chosen not recorded | `chosenIdx`/`chosenExact` via fingerprint of `stepFrozenV4Ooc(postGc)`. 100% exactness |
| 8 | Inconsistent decision accounting | Per-gate counts verified to sum to total unique decisions |
| 9 | `maxDecisions` not global max | Game runs to completion; only first N owned decisions sampled |
| 10 | CSV missing trainer schema | `richState` (1017 cols, CSV-quoted), `actionBits/actionType/c1-c3/cand1-cand3`, `sourceWon/sourceFloor/sourceHp` all present |

### Phase A — Corrected diagnostic

| Test | Result |
|---|---|
| A2: Identity (M_identity = F plumbing without resample) | 0 mismatches across 808 paired evaluations |
| A3: Hidden-resampling (does resample actually change encounters?) | 100% of marginalized samples changed (`hiddenChanged=1`) |
| A4: Source trajectory parity | `stepFrozenV4Ooc` matches `runFullRunOOC`. 3-seed side-by-side: benchmark floor 51, diagnostic reaches matching floors |
| A6: Corrected 200-300 decision H=8 diagnostic | 330 decisions, 26K rows |

**Corrected diagnostic results (330 decisions, H=8):**

| Metric | Value |
|---|---|
| Best-action changes | **191/330 = 57.9%** |
| Marginal regret (mean/median/p75/max) | 3.42 / 1.03 / 4.89 / 33.50 |
| V4 exact overrides | 65 |
| V4 reversals (good→bad) | **7/65 = 10.8%** |
| V4 good both | 31/65 = 47.7% |
| V4 bad both | 16/65 = 24.6% |

**H=4 vs H=8 convergence:** 52.0% vs 55.5% changes on same seeds — close enough to use H=4 for training.

**Verdict: PROMOTE to M0/M1 training.**

### Phase B — Trainer-compatible M0/M1 data

Generated from 500 seeds, H=4, 20 decisions/run:

- Diagnostic CSV: 120,430 rows, 2500 unique decisions, 41 columns
- M0 CSV: 12,043 rows, 1036 columns (proper `strategicHeader2()` column names)
- M1 CSV: 12,043 rows, 1036 columns
- **Non-label mismatch: 0/12,043** — M0/M1 share identical non-label columns ✅

### Phase C — Training

Both trained with identical settings (same split manifest, same model seed, 40 epochs, STRAT_Q_TARGET=absolute):

| | val_pol_ce | q_top1 |
|---|---|---|
| M0 (fixed-world) | 0.6092 | 0.260 |
| M1 (marginalized) | 0.6158 | 0.310 |

Both checkpoints saved. Native exports: 32/32 parity checks passed each.

### Phase D — Gameplay gate

64 paired seeds (900000–900063), frozen S3+7k-VNet Act-3 stack, all screens ON, margin 1.0:

| | Wins | Floor | HP |
|---|---|---|---|
| M0 (fixed) | 5/64 = 7.8% | 34.2 | 2.1 |
| M1 (marg) | 7/64 = 10.9% | 36.1 | 5.0 |
| **Delta** | **+3.1pp** | +1.9 | +2.9 |

CI: [−4.7, +10.9]pp. Discordant: 6/64 (9%).

---

## 2. Critical limitation

Both models are **very weak** (7.8–10.9% win rate vs V4's 48.4%) because training data is tiny: 12K rows from 500 seeds vs V4's 3M rows. The +3.1pp direction favors M1 but the absolute performance is too low for promotion against V4. Scaling to more seeds is the logical next step.

---

## 3. Code architecture

| Component | File | Lines |
|---|---|---|
| `evaluateStrategicBranch()` | apps/one_combat.cpp | ~8170 |
| `stepFrozenV4Ooc()` | apps/one_combat.cpp | ~8190 |
| `strategicMargGen()` + EMIT_ROW macro | apps/one_combat.cpp | ~8250–8500 |
| Gate contract (C++ cross-checked) | strategic_gate_contract.py | — |
| Predict-only parity tests | tools/predict_parity_test.py | — |
| M0/M1 converter | tools/convert_marg_to_trainer.py | — |
| Deployment metrics analyzer | tools/analyze_strategic_metrics.py | — |

---

## 4. Key artifacts

| What | Path |
|---|---|
| Diagnostic CSV (500 seeds, H=4) | `build/marg_500q_diag.csv` (166 MB) |
| Trainer M0 CSV | `build/marg_m0.csv` (12K rows) |
| Trainer M1 CSV | `build/marg_m1.csv` (12K rows) |
| Split manifest | `build/marg_split.json` |
| M0 native | `selfplay/models/ooc_m0_fixed.native` |
| M1 native | `selfplay/models/ooc_m1_marg.native` |
| M0 checkpoint | `selfplay/models/ooc_m0_fixed_best_ce.pt` |
| M1 checkpoint | `selfplay/models/ooc_m1_marg_best_ce.pt` |
| Gameplay CSVs | `build/marg_m{0,1}_64_1786391162.csv` |

---

## 5. Next steps

Scale up training data: 2000–5000 seeds at H=4, 20–30 decisions/run. This would produce 50–150K training rows, enough for a competitive model. Then rerun C0/A1-style: matched M0/M1 training → native export → 64-seed gameplay gate → comparison vs deployed V4.

---

## 6. Verification

```bash
cmake --build build --target one_combat -j4
python3 strategic_gate_contract.py
python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
python3 tools/predict_parity_test.py
```
