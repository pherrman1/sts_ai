# OOC Strategic Investigation — Final Session Report

Date: 2026-08-09  
Git range: `3feb2a1` through `d38272f` (plus concurrent agent changes to CMakeLists.txt, apps/test.cpp)

---

## 1. What was accomplished

### Phase 1: Bug fixes & infrastructure

| Fix | Files | Detail |
|---|---|---|
| Benchmark nondeterminism | `BattleScumSearcher2.{h,cpp}` | `g_potionKeepValue` made `thread_local` — was process-global race |
| Trainer group contiguity | `train_strategic_tok.py`, `train_strategic.py` | CSV rows sorted by `(seed, decIdx)` before group offsets |
| Trainer batch RNG | Both trainers | `np.random.default_rng(0)` initialized |
| Gate-ownership contract | `strategic_gate_contract.py` | C++ cross-checked `classify_group()`, correct RewardsActionType mapping (CARD=0) |
| Predict-only export pipeline | `train_strategic_tok.py` | `STRAT_PREDICT_ONLY=1` mode, uses exact `fwd_rows()`, batched 4096-row chunks |
| Deployment metrics analyzer | `strategic_metrics.py`, `tools/analyze_strategic_metrics.py` | `--owned-only` filter, per-screen beneficial/harmful rates |
| Parity tests | `tools/predict_parity_test.py` | Q parity, group indexing, label parity, gate contract, checkpoint identity |

### Phase 2: Full V4 deployment metrics

Exported predictions for the deployed V4 (`selfplay/models/ooc_strategic_tok_final.pt`) on the full 3.06M-row Tier-B dataset (385K strict-owned opportunities):

| Metric | Value |
|---|---|
| Fire rate | 50.3% |
| Beneficial overrides | 30.0% |
| Harmful overrides | 29.6% |
| Neutral | 40.4% |
| EVENT beneficial | 53.1% |
| SHOP beneficial (offline) | 46.9% |

### Phase 3: Screen confirmation (independent second block)

Second-block seeds 126764–126827:

| Test | Result | Conclusion |
|---|---|---|
| minus EVENT vs full V4 | −14.1pp (CI excludes 0) | EVENT confirmed useful |
| minus SHOP vs full V4 | −4.7pp (crossover from +4.7pp in block 1) | SHOP NOT harmful — first block was false positive |
| minus REST/TREASURE/BOSS_RELIC | No signal | Keep all enabled |

**Final screen mask: all screens ON, margin 1.0.**

### Phase 4: C0 vs A1 target experiment

C0 = absolute-Q control, A1 = fallback-centered existing labels. Same architecture, same split, same seeds, same epochs (40). Only variable changed: Q target.

**Training results (40 epochs, CUDA):**

| | C0 | A1 |
|---|---|---|
| Checkpoint | `ooc_c0_absolute_best_ce.pt` | `ooc_a1_centered_best_ce.pt` |
| val_pol_ce | 0.5324 (epoch 37) | 0.5147 (epoch 39) |
| best q_top1 | 0.2960 (init) | 0.3082 (epoch 10) |
| Q MAE | 29.7 | 9.3 (expected — centered targets have smaller scale) |

**Offline deployment metrics (strict-owned, full dataset):**

| | C0 | A1 |
|---|---|---|
| Fire rate | 57.7% | 36.0% |
| Beneficial % | 28.5% | 44.1% |
| Harmful % | 28.9% | 37.4% |
| EVENT beneficial | 52.5% | 56.8% |

**Native export:** both passed 32/32 parity checks. SHA256:
- `ooc_c0_absolute.native`: `ae78cfcf51…`
- `ooc_a1_centered.native`: `b099aadb37…`

**64-seed gameplay gate (seeds 200000–200063, frozen S3+7k-VNet Act-3):**

| | C0 | A1 | Delta |
|---|---|---|---|
| Wins | 26/64 = 40.6% | 27/64 = 42.2% | +1.6pp |
| | | | CI [−14.1, +17.2]pp |

**Verdict: FLAT.** Fallback-centering alone does not improve gameplay despite better offline metrics (val_pol_ce, q_top1, beneficial rate). Per the handoff: stop this line.

---

## 2. State of the repository

### Files modified (this session)

| File | Changes |
|---|---|
| `include/sim/search/BattleScumSearcher2.h` | `g_potionKeepValue` → `thread_local` |
| `src/sim/search/BattleScumSearcher2.cpp` | `g_potionKeepValue` → `thread_local` |
| `train_strategic_tok.py` | Predict-only mode, dual checkpoint, `STRAT_Q_TARGET`, split manifest, model seed, group sorting, batch RNG |
| `train_strategic.py` | Group sorting, batch RNG, `STRAT_SELECT_METRIC` |
| `strategic_gate_contract.py` | New: C++ cross-checked gate-kind classifier |
| `tools/analyze_strategic_metrics.py` | `--owned-only` filter |
| `EXPERIMENTS.md` | §§155–165 |
| `docs/knowledge-base/*.md` | Decision logs, handoffs, session reports |

### Files from concurrent agents (unrelated, do not touch)

- `CMakeLists.txt` (trailing whitespace)
- `apps/test.cpp` (semantic card edges tests)
- `src/sim/search/ScumSearchAgent2.cpp` (tree-reuse)
- `include/sim/search/BattleScumSearcher3.h` (tree-reuse)
- `src/sim/search/BattleScumSearcher3.cpp` (tree-reuse)
- `tools/train_deepsets_mcts.py`

---

## 3. Key artifacts

| What | Path | SHA256 |
|---|---|---|
| Deployed V4 native | `selfplay/models/ooc_strategic_tok_final.native` | `e62abd83…` |
| V4 checkpoint | `selfplay/models/ooc_strategic_tok_final.pt` | val_pol_ce=0.4885 |
| V4 full predictions | `build/v4_full_preds.csv` | 85 MB |
| Full Tier-B CSV | `build/strategic_tierb.csv` | 6.1 GB |
| C0 split | `build/c0_split.json` | |
| C0 native | `selfplay/models/ooc_c0_absolute.native` | `ae78cfcf…` |
| A1 native | `selfplay/models/ooc_a1_centered.native` | `b099aadb…` |
| C0 checkpoint (CE) | `selfplay/models/ooc_c0_absolute_best_ce.pt` | |
| A1 checkpoint (CE) | `selfplay/models/ooc_a1_centered_best_ce.pt` | |
| 128-seed V4 CSVs | `build/ooc_v4_head_s3_act3_*_64_1786297628.csv` + `*_64plus_1786297983.csv` | |
| C0/A1 gameplay CSVs | `build/c0_64_1786312068.csv`, `build/a1_64_1786312068.csv` | |

---

## 4. Frozen benchmark contract

```text
A0
STS_FAIR=1  STS_SEARCHER3=1
STS_S3_BELIEF=0  STS_S3_CHAIN=0  STS_S3_LIVE_VALID=1
STS_S3_PARTICLES=64
STS_VNET=build/v_combat_7k_tuned.txt  STS_VNET_ALPHA=0.3
STS_COLLECT_KEYS=0  STS_STOP_AFTER_ACT=3
STS_REUSE_MAX_SEARCHES=0
1,000 sims/decision  12 threads  margin=1.0  all screens ON
```

---

## 5. Self-test commands (all pass)

```bash
git diff --check  # my files only, CMakeLists.txt/apps/test.cpp have other agent's trailing whitespace

python3 -m py_compile \
    train_strategic_tok.py train_strategic.py \
    strategic_metrics.py strategic_gate_contract.py \
    tools/analyze_strategic_metrics.py tools/predict_parity_test.py

python3 strategic_gate_contract.py
python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
python3 tools/predict_parity_test.py
```

---

## 6. Trainer features added

| Feature | Env var | Detail |
|---|---|---|
| Predict-only export | `STRAT_PREDICT_ONLY=1` | Batched, uses `fwd_rows()`, writes deployment CSV |
| Dual checkpoints | Automatic | `_best_ce.pt` + `_best_qtop1.pt` saved independently |
| Q target mode | `STRAT_Q_TARGET=absolute\|fallback_centered` | |
| Split manifest write | `STRAT_SPLIT_MANIFEST=path` | Saves train/val seed JSON |
| Split manifest load | `STRAT_SPLIT_LOAD=path` | Reads train seeds from JSON |
| Model seed | `STRAT_MODEL_SEED=N` | Controls init |
| Centering self-test | Automatic | Validates fallback=0, pairwise diffs, argmax |

---

## 7. What was learned

1. **V4 is genuinely useful** (+11.7pp at 128 seeds, CI excludes zero). Provisional baseline.
2. **EVENT is the strongest positive screen** (53% beneficial offline, −14pp gameplay if removed).
3. **SHOP is NOT clearly harmful** — first-block +4.7pp was a false positive; second block crossed over.
4. **Full offline deployment metrics are now available** for any checkpoint via the predict-only pipeline.
5. **Fallback-centering existing labels does NOT improve gameplay** — offline metrics improved (val_pol_ce, q_top1, beneficial rate) but 64-seed gameplay was flat (+1.6pp, CI crossed zero). Do not scale this approach.
6. **Offline Q metrics are weak gameplay proxies** — the V4 experience (CE=0.4885 vs C0's 0.5324, but V4 was proven useful) and the A1 experience both confirm this.

---

## 8. Next experiment (not started)

Genuinely paired fallback-relative datagen (Wave 1C from the handoff):

```
A(o,a) = mean_k[ U(force a, future_k) − U(force fallback, future_k) ]
```

Candidate and fallback share the same `future_k` (common-random-number pairing). Start with 100–200 decisions, 8–16 futures each. Do not generate millions of rows until the label formulation is validated.

This requires new datagen infrastructure, not just a trainer modification.

---

## 9. Resource safety (always check before large jobs)

```bash
nvidia-smi
free -h
pgrep -af 'pi|one_combat|train_strategic'
```

- Do not terminate unrelated workers.
- Never run two full strategic CUDA trainers simultaneously.
- A ~17 GB `.venv/bin/python3` process exists — do not touch it.
- `selfplay/` directory contains buffers/models — do not delete casually.
