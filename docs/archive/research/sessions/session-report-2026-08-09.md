# OOC Strategic Investigation — Complete Session Report

Date: 2026-08-09  
Session scope: Waves 0A–0I through deployment-metric export and screen confirmation

Status: **ARCHIVED intermediate session snapshot.** Do not use as current
research guidance.

## 1. Executive Summary

**Corrected honest V4 is confirmed at 128 paired seeds on the frozen fair S3 + 7k-VNet Act-3 stack.**

| | OFF | ON | Delta |
|---|---|---|---|
| 128 seeds | 52/128 = 40.6% | 67/128 = 52.3% | **+11.7pp** |
| | | | **CI [+1.6, +22.7]pp** |

CI excludes zero. V4 is the provisional OOC baseline.

**Full deployment-metric export completed (385K owned opportunities).**
EVENT is the strongest positive screen (53.1% beneficial offline, −14.1pp gameplay if removed).
SHOP was suspected harmful but the independent second block crossed over — no reliable signal.

**All infrastructure is in place for the next phase:** C0 control training, A1 fallback-centered candidate, and the first target-change experiment.

---

## 2. Bugs Fixed

### Benchmark nondeterminism (race)

`search::g_potionKeepValue` was process-global while `runFullRunOOC` recalculates it per fight during parallel seed execution. Now `thread_local`.

Files: `include/sim/search/BattleScumSearcher2.h`, `src/sim/search/BattleScumSearcher2.cpp`

After fix: repeated 8-seed runs match all `won`, `floor`, `act`, `hpEnd`, and death fields.

### Trainer data-loading

- CSV rows not contiguous by `(seed, decIdx)` → both trainers now sort before group offsets.
- Batch RNG undefined → `np.random.default_rng(0)`.
- Both trainers accept `STRAT_SELECT_METRIC=val_pol_ce` (minimize) or `q_top1` (maximize).

### Gate-ownership contract (REWARDS mapping)

`strategic_gate_contract.py` initially had wrong RewardsActionType mapping (CARD=4 instead of CARD=0). Fixed to match C++ enum from `GameAction.h`. Now uses group-level `classify_group(screen, action_types)` — examines all rows in a decision group, not just the first. C++ header parsing in the self-test prevents future semantic drift.

---

## 3. Frozen Benchmark Contract

```text
A0
STS_FAIR=1  STS_SEARCHER3=1
STS_S3_BELIEF=0  STS_S3_CHAIN=0  STS_S3_LIVE_VALID=1
STS_S3_PARTICLES=64
STS_VNET=build/v_combat_7k_tuned.txt  STS_VNET_ALPHA=0.3
STS_COLLECT_KEYS=0  STS_STOP_AFTER_ACT=3
STS_REUSE_MAX_SEARCHES=0
1,000 sims/decision  12 threads  margin=1.0
```

Models:

| Role | Path | SHA256 |
|---|---|---|
| OOC V4 native | `selfplay/models/ooc_strategic_tok_final.native` | `e62abd833f…` |
| OOC checkpoint | `selfplay/models/ooc_strategic_tok_final.pt` | val_pol_ce=0.4885 |
| Combat VNet | `build/v_combat_7k_tuned.txt` | `ea35b78c88…` |

Never restore: `nextEliteId`, `nextFight0–2`, `remElites`, `remFights`, `monOffset`, `eliteOffset`. `bossId` is public.

---

## 4. V4 Honesty Verified

42 globals: 36 raw + 6 derived. Zero forbidden features. Verified via `strategic_tok_contract.py`.

---

## 5. 128-Seed Confirmation Details

| | OFF | ON | Delta |
|---|---|---|---|
| Block 1 (126700–126763) | 24/64 = 37.5% | 31/64 = 48.4% | +10.9pp |
| Block 2 (126764–126827) | 28/64 = 43.8% | 36/64 = 56.2% | +12.5pp |
| **Combined 128** | **52/128 = 40.6%** | **67/128 = 52.3%** | **+11.7pp** |

Discordant 47/128 (37%). ON-only 31, OFF-only 16. Floor +2.0, HP +5.9.

---

## 6. Screen-Level Results

### First block (126700–126763, 64 seeds)

| Configuration | Wins | Δ vs full V4 |
|---|---|---|
| Full V4 | 31/64 (48.4%) | — |
| minus EVENT | 26/64 (40.6%) | **−7.8pp** |
| minus SHOP | 34/64 (53.1%) | **+4.7pp** |
| minus REST | 31/64 (48.4%) | 0.0pp |
| minus TREASURE | 31/64 (48.4%) | 0.0pp |
| minus BOSS RELIC | 29/64 (45.3%) | −3.1pp |

### Second block (126764–126827, 64 seeds, independent confirmation)

| Configuration | Wins | Δ vs full V4 |
|---|---|---|
| Full V4 | 36/64 (56.2%) | — |
| minus EVENT | 27/64 (42.2%) | **−14.1pp** (CI [−25.0, −3.1]) |
| minus SHOP | 33/64 (51.6%) | −4.7pp (CI [−18.8, +9.4]) |

### Conclusion

- **EVENT**: both blocks independently show removal hurts. CI excludes zero on block 2. **Confirmed useful.**
- **SHOP**: block 1 shows removal helps (+4.7), block 2 shows removal hurts (−4.7). **Crossover — no reliable signal. Keep enabled.**
- **REST, TREASURE, BOSS_RELIC**: no consistent signal. Keep enabled.

**Final screen mask: all screens ON. No changes to the provisional baseline.**

---

## 7. Margin Sweep (64 seeds, first block)

| Margin | Wins | ~Fire rate |
|---|---|---|
| 0.5 | 45.3% | 71.8% |
| 1.0 | 48.4% | 53.3% |
| 2.0 | 48.4% | 33.3% |
| 5.0 | 45.3% | 13.5% |

Plateau at 1–2. Keep margin 1.0 frozen.

---

## 8. Full Deployment-Metric Export

### Pipeline

`train_strategic_tok.py` accepts `STRAT_PREDICT_ONLY=1`. Uses the trainer's exact `fwd_rows()` — same tensor prep as training. Batched (4096-row chunks). Produces deployment-aligned CSV.

```bash
STRAT_PREDICT_ONLY=1 \
STRAT_PREDICT_CKPT=selfplay/models/ooc_strategic_tok_final.pt \
STRAT_PREDICT_MAX_GROUPS=0 \
STRAT_PREDICT_OUT=build/v4_full_preds.csv \
STRAT_DEVICE=cuda \
python3 train_strategic_tok.py build/strategic_tierb.csv /tmp/v4_full_export \
  > build/v4_full_predict.log 2>&1
```

### CSV schema

```
seed,decIdx,screen,gateKind,owned,ownershipExact,nCand,modelIdx,bestIdx,
behaviorFallbackIdx,fallbackIdx,fallbackSource,margin,threshold,fired,predQ,labelQ
```

Labels: `10*labelWon + labelHp`. Fallback: `tierb_chosen` (historical behavior policy).

### Gate-ownership contract

`strategic_gate_contract.py::classify_group(screen, action_types)` — group-level classification with C++ enum cross-check.

| Screen | GateKind | Owned |
|---|---|---|
| 1 EVENT | EVENT | yes |
| 2 REWARDS + CARD(0) present | CARD_REWARD | yes |
| 2 REWARDS, no CARD | GOLD/RELIC/POTION/KEY | no |
| 3 BOSS_RELIC | BOSS_RELIC | yes |
| 4 CARD_SELECT | UNKNOWN | unknown |
| 5 MAP | MAP | no |
| 6 TREASURE | TREASURE | yes |
| 7 REST | REST | yes |
| 8 SHOP | SHOP | yes |

### Full metrics (strict-owned, 385,054 opportunities)

**Overall:**
- Fire rate: 50.3% (193,749/385,054)
- Overrides: 115,000 (where model ≠ behavior fallback)
- Beneficial: 30.0% | Harmful: 29.6% | Neutral: 40.4%
- Model regret mean: 10.14, Fallback regret mean: 10.26

**Per screen:**

| Screen | Opportunities | Fire rate | Beneficial % | Harmful % |
|---|---|---|---|---|
| EVENT | 29,432 | 67.4% | **53.1%** | 36.0% |
| BOSS_RELIC | 7,519 | 78.6% | **54.6%** | 41.6% |
| TREASURE | 13,417 | 49.8% | 50.0% | 34.0% |
| REST | 30,859 | 54.3% | 32.6% | **49.6%** |
| SHOP | 24,891 | 50.8% | 46.9% | 39.6% |
| CARD_REWARD | 278,936 | 47.3% | 21.5% | 24.2% |

Important caveat: these are **retrospective metrics on training data**, not a clean held-out estimate. The deployed V4 predates the final seed-disjoint pipeline. They are diagnostic, not proof of generalization.

---

## 9. Artifact Index

| What | Where |
|---|---|
| Plan | `docs/archive/research/plans/plan-ooc-strategic-investigation-2026-08-09.md` |
| Session handoff | `docs/archive/research/sessions/session-handoff-2026-08-09.md` |
| Experiment log | `EXPERIMENTS.md` §§155–165 |
| Race fix | `docs/knowledge-base/decision-log/2026-08-09-thread-local-potion-value.md` |
| Trainer fix | `docs/knowledge-base/decision-log/2026-08-09-strategic-training-split-fix.md` |
| Gate contract | `strategic_gate_contract.py` |
| Deployment metrics library | `strategic_metrics.py` |
| Metrics analyzer | `tools/analyze_strategic_metrics.py` |
| Predict-only mode | `train_strategic_tok.py` (`STRAT_PREDICT_ONLY=1`) |
| Parity tests | `tools/predict_parity_test.py` |
| Full prediction CSV | `build/v4_full_preds.csv` (85 MB) |
| 128-seed CSVs | `build/ooc_v4_head_s3_act3_*_64_1786297628.csv` + `*_64plus_1786297983.csv` |
| Ablation CSVs | `build/ooc_v4_requal_s3_act3_ablate_64_1786292838/` |
| Second-block screen CSVs | `build/ooc_v4_s2_no{shop,event}_64_*.csv` |
| Margin CSVs | `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv` |

---

## 10. Self-Test Commands

```bash
git diff --check

python3 -m py_compile \
    train_strategic.py train_strategic_tok.py \
    strategic_metrics.py tools/analyze_strategic_metrics.py \
    strategic_gate_contract.py tools/predict_parity_test.py

python3 strategic_gate_contract.py
python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
python3 tools/predict_parity_test.py
```

---

## 11. Remaining Queue

| # | Item | Status |
|---|---|---|
| 1–4 | Gate contract audit/fix/C++ parity | ✅ |
| 5 | Predict-only parity tests | ✅ |
| 6–7 | Smoke + full CUDA export | ✅ |
| 8–9 | Deployment metrics + interpret | ✅ |
| 10–11 | Second-block screen gates + freeze mask | ✅ — all screens ON |
| 12 | **Dual-checkpoint trainer save** | Not started |
| 13 | **Train C0** (current-pipeline absolute-Q control) | Not started |
| 14 | **Train A1** (fallback-centered existing labels) | Not started |
| 15 | Compare C0 vs A1 offline | Not started |
| 16 | Gameplay C0 vs A1, 64 seeds | Not started |
| 17 | New datagen only if justified | Not started |

---

## 12. Next Exact Steps

### 12a. Modify trainer to save both checkpoints

In one training trajectory, save `best_val_pol_ce.pt` and `best_q_top1.pt`. Use a fixed horizon sufficient for both metrics to peak. Do not let early stopping for one metric truncate the other.

### 12b. Train C0

Same V4 architecture, same Tier-B corpus, same seed-disjoint split, same Q target (`10*labelWon + labelHp`), same losses. Save both checkpoints. This is the current-pipeline control — the deployed V4 predates the final pipeline, so C0 is the proper baseline for target-change experiments.

### 12c. Train A1

Everything identical to C0 except Q target → fallback-centered:
`A(a) = Q_abs(a) - Q_abs(behaviorFallback)`. This preserves within-group action ranking. Isolates whether removing state-level baseline variation helps the Q head.

### 12d. Compare offline

On identical seed-disjoint validation seeds, compare beneficial-override precision, harmful-override rate, mean fallback-relative advantage, model regret, and fallback regret.

### 12e. Gameplay gate

C0 vs A1, 64 paired seeds on the frozen benchmark. If promising, confirm to 128.

### 12f. Promotion

The winner must also preserve or beat the current deployed/provisional V4 baseline.

---

## 13. Resource Safety

- Check `nvidia-smi`, `free -h`, `pgrep -af 'pi|one_combat|train_strategic'` before large jobs.
- Do not terminate unrelated workers.
- Never run two full strategic CUDA trainers simultaneously.
- Redirect large trainer output to files.
- A ~17 GB `.venv/bin/python3` process exists — do not touch it.
- The `selfplay/` directory contains buffers/models — do not delete casually.
