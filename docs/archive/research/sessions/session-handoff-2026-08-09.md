# OOC Strategic Investigation — Archived Session Summary & Handoff

Date: 2026-08-09  
Git: `50b5867` / `ecebb0e`

## One-line state

**Honest V4 is confirmed at 128 paired seeds (+11.7pp, CI [+1.6,+22.7]pp).  
The prediction-CSV pipeline is built and self-tested.  
The next step is a full CUDA export of V4 predictions for deployment metrics.**

---

## What was fixed

### Benchmark nondeterminism (race)

`search::g_potionKeepValue` was process-global, but `runFullRunOOC` writes it per fight while seeds run in parallel. Now `thread_local` in:

- `include/sim/search/BattleScumSearcher2.h`
- `src/sim/search/BattleScumSearcher2.cpp`

After the fix, repeated runs match all `won`, `floor`, `act`, `hpEnd`, and death fields.

### Trainer data-loading bugs

- CSV rows were not contiguous by `(seed, decIdx)` — both trainers now sort before building group offsets.
- Batch-permutation RNG was undefined — now `np.random.default_rng(0)`.
- Both `train_strategic.py` and `train_strategic_tok.py` accept `STRAT_SELECT_METRIC=val_pol_ce` (minimize, default) or `q_top1` (maximize).

---

## Frozen benchmark contract

Unless explicitly changed:

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
| OOC V4 | `selfplay/models/ooc_strategic_tok_final.native` | `e62abd83…` |
| OOC checkpoint | `selfplay/models/ooc_strategic_tok_final.pt` | val_pol_ce=0.4885 |
| Combat VNet | `build/v_combat_7k_tuned.txt` | `ea35b78c…` |

Never restore: `nextEliteId`, `nextFight0–2`, `remElites`, `remFights`, `monOffset`, `eliteOffset`. `bossId` is public.

---

## V4 honesty

Verified via `strategic_tok_contract.py`: the 42 globals contain zero forbidden features. The V4 uses only player-visible information — 36 raw columns + 6 derived features.

---

## 128-seed confirmation

| | OFF | ON | Delta |
|---|---|---|---|
| Block 1 (126700–126763) | 24/64 = 37.5% | 31/64 = 48.4% | +10.9pp |
| Block 2 (126764–126827) | 28/64 = 43.8% | 36/64 = 56.2% | +12.5pp |
| **Combined 128** | **52/128 = 40.6%** | **67/128 = 52.3%** | **+11.7pp** |
| | | | **CI [+1.6, +22.7]pp** |

Discordant 47/128 (37%). ON-only 31, OFF-only 16. Floor +2.0, HP +5.9.

**Verdict: V4 is the provisional OOC baseline.**

---

## Screen-level interpretation (64-seed, exploratory)

| Configuration | Wins | vs full V4 |
|---|---|---|
| Full V4 | 31/64 (48.4%) | — |
| minus EVENT | 26/64 (40.6%) | **−7.8pp** |
| minus SHOP | 34/64 (53.1%) | **+4.7pp** |
| minus REST | 31/64 (48.4%) | 0.0pp |
| minus TREASURE | 31/64 (48.4%) | 0.0pp |
| minus BOSS RELIC | 29/64 (45.3%) | −3.1pp |

All CIs cross zero at 64 seeds. Independent second-block confirmation on seeds 126764–126827 is the next gameplay step.

---

## Margin sweep (64-seed)

| Margin | Wins | ~Fire rate (8-seed trace) |
|---|---|---|
| 0.5 | 45.3% | 71.8% |
| 1.0 | 48.4% | 53.3% |
| 2.0 | 48.4% | 33.3% |
| 5.0 | 45.3% | 13.5% |

Margin 1–2 is a small-sample plateau. Keep margin 1.0 frozen.

---

## Prediction-CSV pipeline (built, self-tested)

### Predict-only mode

`train_strategic_tok.py` accepts `STRAT_PREDICT_ONLY=1`. It uses the trainer's
existing `fwd_rows()` — same tensor prep as training. No second encoder.

```bash
STRAT_PREDICT_ONLY=1 \
STRAT_PREDICT_CKPT=selfplay/models/ooc_strategic_tok_final.pt \
STRAT_PREDICT_MAX_GROUPS=0 \
STRAT_PREDICT_OUT=build/v4_full_preds.csv \
STRAT_DEVICE=cuda \
python3 train_strategic_tok.py build/strategic_tierb.csv /tmp/v4_export \
  > build/v4_full_predict.log 2>&1
```

- Batched: 4096-row chunked forward, then group-level aggregation.
- Labels: `10*labelWon + labelHp`.
- Fallback: `tierb_chosen` (historical behavior policy, not current runtime).

### Gate-ownership contract

`strategic_gate_contract.py` — authoritative `classify(screen, actionType, c1)` returning `(GateKind, owned, ownershipExact)`.

Screen ownership for frozen V4:

| Screen | GateKind | Owned |
|---|---|---|
| 1 EVENT | EVENT | yes |
| 2 REWARDS, actionType=4 | CARD_REWARD | yes |
| 2 REWARDS, actionType≠4 | GOLD/RELIC/POTION/KEY | no |
| 3 BOSS_RELIC | BOSS_RELIC | yes |
| 4 CARD_SELECT | UNKNOWN | unknown |
| 5 MAP | MAP | no |
| 6 TREASURE | TREASURE | yes |
| 7 REST | REST | yes |
| 8 SHOP | SHOP | yes |

### CSV schema

```
seed,decIdx,screen,gateKind,owned,ownershipExact,nCand,modelIdx,bestIdx,
behaviorFallbackIdx,fallbackIdx,fallbackSource,margin,threshold,fired,predQ,labelQ
```

### Analyzer

`tools/analyze_strategic_metrics.py` accepts `--owned-only` to restrict to strict-owned rows. All self-tests pass.

---

## Self-test commands

```bash
git diff --check

python3 -m py_compile \
    train_strategic.py train_strategic_tok.py \
    strategic_metrics.py tools/analyze_strategic_metrics.py \
    strategic_gate_contract.py

python3 tools/analyze_strategic_metrics.py --self-test
python3 strategic_gate_contract.py
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
```

Predict-only smoke (CPU, small fixture):

```bash
STRAT_PREDICT_ONLY=1 STRAT_PREDICT_CKPT=<ckpt.pt> \
  STRAT_PREDICT_MAX_GROUPS=50 STRAT_DEVICE=cpu \
  STRAT_TOK_COMPILE=0 OMP_NUM_THREADS=4 \
  python3 train_strategic_tok.py <tierb_fixture.csv> /tmp/smoke
```

---

## Key artifacts

| What | Where |
|---|---|
| Plan | `docs/archive/research/plans/plan-ooc-strategic-investigation-2026-08-09.md` |
| Wave 0 handoff | `docs/archive/research/sessions/ooc-strategic-waves-handoff-2026-08-09.md` |
| Experiment log | `EXPERIMENTS.md` §§155–165 |
| Race fix decision | `docs/knowledge-base/decision-log/2026-08-09-thread-local-potion-value.md` |
| Trainer split fix | `docs/knowledge-base/decision-log/2026-08-09-strategic-training-split-fix.md` |
| Gate contract | `strategic_gate_contract.py` |
| Deployment metrics | `strategic_metrics.py`, `tools/analyze_strategic_metrics.py` |
| Trace analyzer | `tools/analyze_strategic_trace.py` |
| Screen ablation harness | `run_screen_ablate.sh` |
| Predict-only mode | `train_strategic_tok.py` (`STRAT_PREDICT_ONLY=1`) |
| 128-seed CSVs | `build/ooc_v4_head_s3_act3_*_64_1786297628.csv` + `*_64plus_1786297983.csv` |
| Ablation CSVs | `build/ooc_v4_requal_s3_act3_ablate_64_1786292838/` |
| Margin CSVs | `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv` |
| SHOP-disabled CSV | `build/ooc_v4_noshop_s3_act3_64_1786298692.csv` |
| Full Tier-B CSV | `build/strategic_tierb.csv` (6.1 GB) |
| V4 token state | `selfplay/models/ooc_strategic_tok_final_tok_state.bin` (2.8 GB) |

---

## Immediate execution queue

In order:

1. **Add predict-only parity self-tests.**
   Prove Q from predict-only path matches Q from trainer evaluation on same rows. Test group indexing, label parity, screen contract, and native checkpoint identity.

2. **Run full CUDA prediction export.**
   Use the command above on the full Tier-B dataset. Reports both `--owned-only` and all-decisions views.

3. **Interpret deployment metrics.**
   Per gate-kind override quality, advantage, regret, and margin-binned confidence.

4. **Run independent second-block screen confirmations.**
   Seeds 126764–126827. Full V4 vs minus-SHOP, full V4 vs minus-EVENT. Same frozen binary.

5. **Freeze screen mask.**
   If SHOP-disabled again positive and EVENT-removal again negative, make SHOP-disabled the provisional baseline.

6. **Modify trainer to save best-CE and best-qtop1 from one run.**
   Do not early-stop for one metric before the other can peak.

7. **Train C0 — current-pipeline absolute-Q control.**

8. **Train A1 — fallback-centered EXISTING labels.**

9. **Compare C0 vs A1 offline, then 64 paired gameplay seeds.**

10. **Only then consider new paired datagen or hidden-future marginalization.**

---

## Resource safety

- Check `nvidia-smi`, `free -h`, `pgrep -af 'pi|one_combat|train_strategic'` before large jobs.
- Do not terminate unrelated workers.
- Never run two full strategic CUDA trainers simultaneously.
- Redirect large trainer output to files.
- A ~17 GB `.venv/bin/python3` process exists — do not touch it.
- The `selfplay/` directory contains buffers/models — do not delete casually.
