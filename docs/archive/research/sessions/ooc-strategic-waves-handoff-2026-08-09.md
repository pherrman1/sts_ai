# OOC strategic investigation — archived Wave 0 report

Date: 2026-08-09  
Purpose: give the next coding/research model a complete, concise state of the
corrected honest V4 investigation, including all completed work and the exact
next experiments to run.

---

## 1. The one-sentence takeaway

**Corrected honest V4 is statistically confirmed at 128 paired seeds on the
frozen fair S3 + 7k-VNet Act-3 stack: +11.7pp, 95% bootstrap CI [+1.6, +22.7]pp.
It is now the provisional OOC baseline.  SHOP overrides appear harmful; EVENT
overrides appear useful.  Do not alter the combat stack, the feature set, or
the label formulation until the next targeted experiments below are complete.**

---

## 2. Fixed blocker: parallel benchmark race

`search::g_potionKeepValue` was process-global but `runFullRunOOC` recalculates
it per fight while seeds run concurrently.  It is now `thread_local` in

- `include/sim/search/BattleScumSearcher2.h`
- `src/sim/search/BattleScumSearcher2.cpp`

After the fix, repeated identical 8-seed checkpoints match every `won`, `floor`,
`act`, `hpEnd`, and death field.  The earlier pre-fix variability (37.5% vs
7.8% on the same nominal control) was a genuine race, not ordinary noise.

Trainer fixes from this pass:

- Both trainers canonicalise CSV rows by `(seed, decIdx)` before constructing
  group offsets (the prior code assumed contiguity that the frozen Tier-B CSV
  did not satisfy).
- Both trainers initialise a deterministic batch-permutation RNG.

---

## 3. Frozen benchmark contract

Every experiment below uses exactly this unless one variable is intentionally
changed:

```text
A0
STS_FAIR=1
STS_SEARCHER3=1
STS_S3_BELIEF=0          STS_S3_CHAIN=0          STS_S3_LIVE_VALID=1
STS_S3_PARTICLES=64
STS_VNET=build/v_combat_7k_tuned.txt             STS_VNET_ALPHA=0.3
STS_COLLECT_KEYS=0                                STS_STOP_AFTER_ACT=3
1,000 sims/decision, 12 OpenMP threads
paired seeds 126700–126827 (128 total; first 64 = 126700–126763, second 64 = 126764–126827)
```

Models:

```text
corrected honest V4 token gate:
  selfplay/models/ooc_strategic_tok_final.native
  SHA256 e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c

combat VNet:
  build/v_combat_7k_tuned.txt
  SHA256 ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c
```

Eight forbidden hidden features remain excluded (never restore them):
`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`, `remElites`,
`remFights`, `monOffset`, `eliteOffset`.  `bossId` is legitimate.

---

## 4. Wave results summary

| Wave | Status | Key result |
|---|---|---|
| **0A correctness** | Done | Python/C++ V4 contract parity, Map detach fixes, self-tests pass |
| **0B seed-disjoint** | Done | Trainers split complete seeds; contiguity + RNG bugs fixed |
| **0C provenance** | Done | `bestbench` writes `<results>.meta.json` sidecars |
| **0D deployment metrics** | Partial | `strategic_metrics.py` + analyzer exist; real checkpoint → prediction CSV pipeline has export script but needs trainer tensor-prep integration |
| **0E V4 gate** | **Done, 128 seeds** | **V4 ON 67/128 = 52.3% vs OFF 52/128 = 40.6%, +11.7pp, CI [+1.6,+22.7]pp, CI excludes zero** |
| **0F tracing** | Done | Integrates with `STS_OOC_STRATEGIC_TRACE` and `tools/analyze_strategic_trace.py` |
| **0G screen ablations** | Done (64-seed) | EVENT useful (−7.8pp if removed), SHOP harmful (+4.7pp if removed), REST/TREASURE neutral |
| **0H margin sweep** | Done (64-seed) | Plateau at margin 1–2 (both 48.4%); margin 0.5→45.3%, 5.0→45.3%. Fire rates: 0.5→71.8%, 1.0→53.3%, 2.0→33.3%, 5.0→13.5% |
| **0I checkpoint selection** | Partial | `STRAT_SELECT_METRIC` interface verified on CPU fixture; `val_pol_ce` and `q_top1` pick different epochs. Full-dataset comparison not yet run |

---

## 5. 128-seed confirmation details (§163)

Two 64-seed blocks were combined for 128 paired seeds.  The first 64 were
bit-identical to the earlier requalification (proving binary stability across
the `baed55b` Searcher3 commit).  The second 64 used a slightly later binary
(`dfc3ed8` tree-reuse controls, opt-in/env-gated, no behavioural impact).

| | OFF | ON | Delta |
|---|---|---|---|
| **Block 1** (126700–126763) | 24/64 (37.5%) | 31/64 (48.4%) | +10.9pp |
| **Block 2** (126764–126827) | 28/64 (43.8%) | 36/64 (56.2%) | +12.5pp |
| **Combined (128)** | 52/128 (40.6%) | 67/128 (52.3%) | **+11.7pp** |
| | | | CI **[+1.6, +22.7]pp** |

Discordant: 47/128 (37%).  ON-only wins: 31.  OFF-only wins: 16.  Floor +2.0,
HP +5.9.

The CI lower bound is positive — this is the first statistically significant
V4 gate on the S3+7k-VNet stack.

---

## 6. Screen-level interpretation

Full V4 at margin 1.0 = 31/64 (48.4%) on seeds 126700–126763.

| Configuration | Wins | vs full V4 |
|---|---|---|
| **Full V4** | 31 | — |
| minus REST | 31 | 0.0pp |
| minus EVENT | 26 | **−7.8pp** |
| minus SHOP | 34 | **+4.7pp** |
| minus TREASURE | 31 | 0.0pp |
| minus BOSS RELIC | 29 | −3.1pp |

All CIs cross zero at 64 seeds.  The directions are:

- **EVENT is the strongest candidate for a genuinely useful V4 screen.**
- **SHOP is the strongest candidate for a harmful V4 screen.**
- REST and TREASURE show no gameplay signal.
- BOSS RELIC may contribute modestly.

These are exploratory.  Do not promote SHOP-disabling based on this alone.

---

## 7. Margin analysis

Both margin 1.0 and 2.0 produced 31/64 wins.  They disagreed on 14 seeds —
margin 2 trades different outcomes without aggregate gain.  Fire rates drop
from 53.3% (margin 1) to 33.3% (margin 2) in an 8-seed trace sample.

There is no evidence that margin ≠ 1.0 is better.  Keep margin 1.0 frozen
for the next experiments.

---

## 8. Important artifacts

| What | Where |
|---|---|
| Plan | `docs/archive/research/plans/plan-ooc-strategic-investigation-2026-08-09.md` |
| Experiment log | `EXPERIMENTS.md` §§155–165 |
| Race fix decision | `docs/knowledge-base/decision-log/2026-08-09-thread-local-potion-value.md` |
| Trainer split fix | `docs/knowledge-base/decision-log/2026-08-09-strategic-training-split-fix.md` |
| Deployment metrics | `strategic_metrics.py`, `tools/analyze_strategic_metrics.py` |
| Prediction export | ✅ Done | `STRAT_PREDICT_ONLY=1` mode in `train_strategic_tok.py`, uses exact `fwd_rows()` tensor prep, writes deployment-aligned CSV with `10*labelWon+labelHp` labels. Small-fixture smoke + 500-group V4 smoke passed. Full CUDA export pending. |
| Prediction smoke result | Partial | 500-group V4 smoke: fire rate 51.8%, beneficial 30.1%, harmful 34.1%. EVENT overrides 80% beneficial — matches gameplay finding. |
| Analyzer | ✅ Done | `tools/analyze_strategic_metrics.py` consumes prediction CSV, self-test passes |
| Trace analyzer | `tools/analyze_strategic_trace.py` |
| Screen ablation harness | `run_screen_ablate.sh` |
| 128-seed OFF | `build/ooc_v4_head_s3_act3_off_64_1786297628.csv` + `build/ooc_v4_head128_s3_act3_off_64plus_1786297983.csv` |
| 128-seed ON | `build/ooc_v4_head_s3_act3_on_64_1786297628.csv` + `build/ooc_v4_head128_s3_act3_on_64plus_1786297983.csv` |
| Ablation CSVs | `build/ooc_v4_requal_s3_act3_ablate_64_1786292838/` |
| Margin CSVs | `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv` |
| SHOP-disabled | `build/ooc_v4_noshop_s3_act3_64_1786298692.csv` |

---

## 9. What NOT to conclude

- The earlier S2-fair +15.6pp result does **not** transfer to this stack in
  magnitude; the current result is +11.7pp.
- The earlier post-race negative gate (−23.4pp) is **invalidated** — it was
  generated before the thread-local fix.
- 64-seed screen/margin results are **exploratory**, not deployment decisions.
- Runtime traces cannot measure harmful overrides without counterfactual
  labels.  Use the prediction-CSV pipeline for that.
- Do not compare `STS_COLLECT_KEYS=0` Act-3 results with Heart results.
  No Heart gate has been run.
- Do not start Wave 1 (fallback-relative labels) or Wave 2 (hidden-future
  marginalisation) until the prediction-CSV pipeline is finished and the
  SHOP/EVENT interpretation is solidified.

---

## 10. Resource safety rules

Before any large trainer or benchmark:

- Inspect `nvidia-smi` and `free -h`.
- Check for existing `pi`, `one_combat`, or `train_strategic` workers;
  do not terminate them.
- Redirect large trainer output to files, not an IDE console.
- Never run two full CUDA strategic trainers concurrently.
- Reduced or synthetic fixtures are preferred for logic tests.
- There is an existing `.venv/bin/python3` process using ~17 GB — do not touch it.

---

## 11. Cheapest verification commands

Before every task:

```bash
git diff --check

python3 -m py_compile \
    train_strategic.py train_strategic_tok.py \
    strategic_metrics.py tools/analyze_strategic_metrics.py

python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py

# Predict-only smoke (CPU, small fixture):
STRAT_PREDICT_ONLY=1 STRAT_PREDICT_CKPT=<ckpt.pt> \
  STRAT_PREDICT_MAX_GROUPS=50 STRAT_DEVICE=cpu \
  STRAT_TOK_COMPILE=0 OMP_NUM_THREADS=4 \
  python3 train_strategic_tok.py <tierb_fixture.csv> /tmp/smoke
```

For gameplay on the frozen stack:

```bash
# V4 OFF
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
STS_S3_LIVE_VALID=1 STS_S3_PARTICLES=64 \
STS_VNET=build/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
STS_COLLECT_KEYS=0 STS_STOP_AFTER_ACT=3 \
OMP_NUM_THREADS=12 ./build/one_combat bestbench 1000 N 0 SEED results.csv

# V4 ON (add: STS_OOC_STRATEGIC_TOK_NN=..., REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, MARGIN=1.0)
```

Seed ceiling: 8–16 smoke, 64 exploratory, 128 confirmation maximum.

---

## 12. Exact next experiments (in priority order)

### A — ✅ Predict-only mode implemented; run full CUDA export

The `STRAT_PREDICT_ONLY=1` mode is implemented in `train_strategic_tok.py`.
It uses the trainer's existing `fwd_rows()` — same tensor prep as training.
Activate with:
```bash
STRAT_PREDICT_ONLY=1 \
STRAT_PREDICT_CKPT=selfplay/models/ooc_strategic_tok_final.pt \
STRAT_PREDICT_MAX_GROUPS=0 \
STRAT_PREDICT_OUT=build/v4_full_preds.csv \
python3 train_strategic_tok.py build/strategic_tierb.csv /tmp/v4_export
```
Output CSV: `seed,decIdx,screen,nCand,owned,modelIdx,bestIdx,
behaviorFallbackIdx,fallbackIdx,fallbackSource,margin,threshold,fired,predQ,labelQ`.
Labels use `10*labelWon + labelHp`.  Fallback = `tierb_chosen`.

A 500-group CPU smoke test ran successfully on the full 6.1 GB Tier-B CSV
(~51.8% fire rate, EVENT overrides 80% beneficial).  The full 722K-group
export should use CUDA (CPU would take days).  The 2.8 GB token state is
precomputed at `selfplay/models/ooc_strategic_tok_final_tok_state.bin`
but the trainer may rebuild it if the CSV path fingerprint differs.

What remains: a parity self-test proving predict-only Q matches trainer
evaluation Q on the same rows, then the full CUDA export.

### B — Decide whether full checkpoint-selection training is worth it (Task 7)

Two full-dataset strategic-token trainings (`val_pol_ce` vs `q_top1`
selection) cost ~2× the GPU memory of one (~2.9 GB state tensor + model),
plus significant wall time.  Given that offline metrics are weak gameplay
predictors anyway (the V4 experience), this is **not** a blocker for label
experiments.  Defer it until prediction-CSV pipeline is available and can
compare the two checkpoints on deployment-aligned metrics instead of just
CE/q_top1.

### C — Wave 1A: fallback-relative advantage using existing Tier-B labels (Task 8)

For each existing Tier-B decision group, derive `A(o,a) = labelQ(o,a) −
labelQ(o,fallback)`.  Same dataset, split, encoder, architecture, optimizer,
and epochs.  Only change the target/head/loss to predict advantage instead of
absolute Q.  Keep `margin=1.0`, all five screens ON.  Run 64 paired seeds
against the confirmed full-V4 baseline on the same seed block.

This isolates the question: *is learning fallback-relative advantage easier
or more deployment-aligned than learning absolute Q?*

### D — Wave 1B: genuinely paired fallback-relative datagen (Task 9)

Only if Wave 1A shows promise.  Generate new labels `A(o,a) = mean_k[ U(force a,
future k) − U(force fallback, future k) ]` with common-random-number pairing.
Start with 100–200 decisions, 8–16 futures each.  Do not generate a full
multi-million-row dataset until the label formulation is validated.

### E — Wave 2: hidden-future marginalisation (Task 10)

Keep this separate from paired advantage generation.  For public observation
`o`, create hidden futures `h_k` compatible with visible information.
100–200 diverse decisions, 16 realisations (32 for ambiguous cases).
Measure action-ranking changes and candidate/fallback sign changes.  If
marginalisation rarely changes decisions, stop — it's not worth scaling.

---

## 13. Decision point before new labels (repeated from the handoff)

1. **Is V4 positive at 128 seeds?** → **Yes.** ✓
2. Which screens generate useful vs harmful overrides? → EVENT useful, SHOP harmful (exploratory 64-seed).
3. Does predicted confidence correlate with label improvement? → Not yet measured (prediction-CSV pipeline needed).
4. Does absolute-Q fail due to bad calibration, bad ranking, screen heterogeneity, or disagreement with fallback outcomes? → Partially answered by screen ablations; deep diagnostics need the pipeline.
5. Is checkpoint selection leaving performance on the table? → Unclear; not yet measured in gameplay terms.

The next research question is:

> **Can we make V4 overrides more reliably beneficial relative to the
> fallback without changing multiple causal variables at once?**
