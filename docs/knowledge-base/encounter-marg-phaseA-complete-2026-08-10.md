# Encounter Marginalization — Phase A Complete, Phase B Ready

Date: 2026-08-10

---

## Phase A: Fix + Revalidate — DONE

| Task | Status | Key result |
|---|---|---|
| A1: Tier-B label contract | ✅ | `evaluateStrategicBranch()` uses `finishOocCounterfactual(bootstrap=true)` |
| A2: Identity test | ✅ | 0 mismatches F vs marg_id (no other confounds) |
| A3: Hidden-resampling check | ✅ | 100% of marginalized samples actually change encounters |
| A4: Source trajectory parity | ✅ | `stepFrozenV4Ooc()` replicates exact V4 gate stack |
| A5: Fallback exactness | ✅ | 98% overall (100% for most gates, 97% CARD) |
| A6: Corrected diagnostic | ✅ | 57.9% best-action changes, 10.8% V4 reversals |

---

## Phase B: Trainer-Compatible M0/M1 — READY

### What works

The `strategicmarggen` diagnostic now produces 41-column CSV with:
- All Tier-B label columns (`labelWon/labelHp/labelFloor/labelBootstrap`)
- Action metadata (`actionBits/actionType/c1-c3/cand1-cand3`)
- Source chosen action (`chosenIdx/chosenExact` via fingerprint)
- Exact fallback (`fallbackIdx/fallbackExact` via fingerprint)
- V4 predictions (`v4ModelIdx/v4Margin/v4Fired/v4ExecutedIdx/v4Override`)
- Rich state (1017 columns)
- Hidden-resampling tracking (`hiddenChanged`)
- Source terminal outcome (`sourceWon/sourceFloor/sourceHp`)

### Converter

`tools/convert_marg_to_trainer.py` converts diagnostic CSV to M0/M1 trainer-compatible CSVs. Verified: M0/M1 non-label columns are identical.

### M0/M1 generation command

```bash
# Generate diagnostic data (game runs to completion, samples first N owned decisions)
env STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
  STS_S3_LIVE_VALID=1 STS_S3_PARTICLES=64 \
  STS_VNET=build/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
  ./build/one_combat strategicmarggen 500 1000 150 3 4 20 /tmp/marg_train.csv 800000

# Convert to trainer M0/M1 CSVs
python3 tools/convert_marg_to_trainer.py /tmp/marg_train.csv \
  build/marg_m0.csv build/marg_m1.csv
```

### Remaining for production run
- Gate-stratified reservoir sampling (currently first-N per run)
- Verify M0/M1 non-label columns identical (assertion in converter)
- H=4 recommended for training (cost-effective; H=8 convergence check already done)

---

## Phase C/D: Training + Gameplay — Not Started

Commands for C0-style training:

```bash
# M0 training
STRAT_Q_TARGET=absolute STRAT_SPLIT_MANIFEST=build/marg_split.json \
STRAT_EPOCHS=40 STRAT_PATIENCE=0 STRAT_MODEL_SEED=42 \
python3 train_strategic_tok.py build/marg_m0.csv selfplay/models/ooc_m0

# M1 training (same split)
STRAT_Q_TARGET=absolute STRAT_SPLIT_LOAD=build/marg_split.json \
STRAT_EPOCHS=40 STRAT_PATIENCE=0 STRAT_MODEL_SEED=42 \
python3 train_strategic_tok.py build/marg_m1.csv selfplay/models/ooc_m1

# Native export
python3 export_strategic_tok.py selfplay/models/ooc_m0_best_ce.pt selfplay/models/ooc_m0.native
python3 export_strategic_tok.py selfplay/models/ooc_m1_best_ce.pt selfplay/models/ooc_m1.native

# 64-seed gameplay gate
env STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_m0.native [V4 gate flags] \
  STS_FAIR=1 STS_SEARCHER3=1 ... \
  ./build/one_combat bestbench 1000 64 0 <fresh_seeds> /tmp/m0_64.csv
```

---

## Code Architecture

| Function | File | Line | Purpose |
|---|---|---|---|
| `evaluateStrategicBranch()` | apps/one_combat.cpp | ~8170 | Tier-B branch labels |
| `stepFrozenV4Ooc()` | apps/one_combat.cpp | ~8190 | Production V4 OOC step |
| `strategicMargGen()` | apps/one_combat.cpp | ~8250 | Main diagnostic (EMIT_ROW macro) |
| `finishMargCf()` | apps/one_combat.cpp | ~8220 | Thin wrapper around evaluateStrategicBranch |
| `convert_marg_to_trainer.py` | tools/ | — | M0/M1 converter |
| `strategic_gate_contract.py` | root | — | Python gate contract (C++ cross-checked) |

---

## Verification

```bash
cmake --build build --target one_combat -j4
python3 strategic_gate_contract.py
python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
```
