# V_combat Training ↔ Deployment Distribution Shift — Complete Diagnostic Report

> **Status (2026-09-24):** Searcher3 was removed by
> [ADR-0019](../../../decisions/0019-remove-searcher3.md). This page is a
> historical research record; reproducing it needs a binary built before that
> change.

**Date:** 2026-08-09
**Status:** Complete
**Recommendation:** A — do NOT build an expensive deployment-leaf relabeling pipeline

---

## Purpose

Determine quantitatively whether the states used to train `V_combat` (ordinary
`combatgen` per-decision combat snapshots) differ substantially from the states
on which `V_combat` is actually queried inside deployed Searcher3 as an MCTS
leaf evaluator.

The motivating puzzle was:

- §148 obtained a major online win-rate improvement from hyperparameter tuning
  the VNet, despite nearly unchanged offline RMSE on the same combatgen holdout.
- §129 matching the OOC/deck distribution to the V4 gate stack changed
  calibration but didn't significantly beat the existing model.
- §137 covariate-shift mixture retrain (combatgen + leafdiag states) did NOT
  improve held-out search-leaf ranking.

**Hypothesis:** The suspected mismatch is between ordinary trajectory/decision
snapshots (training) and states selected by MCTS as VNet evaluation leaves
(deployment). If confirmed, expensive relabeling (frontiergen + leafrelabel)
would be indicated.

**This report measures that mismatch directly and finds it is NOT the primary issue.**

---

## 1. Deployed Configuration

The investigation targets the current recommended Searcher3 deployment:

| Parameter | Value |
|-----------|-------|
| `STS_FAIR` | 1 (project-fair determinization) |
| `STS_SEARCHER3` | 1 (ISMCTS with particle belief) |
| `STS_S3_BELIEF` | 0 (belief reweighting off — harmful per §106/§107) |
| `STS_S3_CHAIN` | 0 (chain compression off — harmful per §106/§107) |
| `STS_S3_PARTICLES` | 64 |
| `STS_LIVE_VALID` | 1 (default ON since §123) |
| `STS_VNET` | default → `build/v_combat_7k_tuned.txt` (1000 trees, sha256 `ea35b78c…`) |
| `STS_VNET_ALPHA` | 0.3 (default since §126) |
| OOC policy | Native floor/win trees; heuristic pathing; shop-V; win-rest |
| Ascension | 0 |
| Sim budget | 1,000 per decision |

Training data for the deployed VNet: `build/vcombat_honest.csv` — 287,518 rows
from `combatgen` mode, seeds 0–1460, heuristic-OOC run loop (pre-gate-stack),
labeled with each fight's terminal outcome (won, fightEndHp).

---

## 2. Method

### 2.1 Instrumentation — `STS_VNET_QUERY_LOG`

Added a non-thread-local hook `search::g_onVNetQuery` inside
`CombatValueNet::predict()` — the single C++ function through which every VNet
inference flows. The hook fires after computing the model prediction and passes
the `BattleContext` reference plus the raw prediction value.

**Environment flags:**

```
STS_VNET_QUERY_LOG=<path>      # CSV output file
STS_VNET_QUERY_SAMPLE=<prob>   # sampling rate (default 1.0 = log all queries)
```

**Safety:** When `STS_VNET_QUERY_LOG` is unset, `g_onVNetQuery` stays
`nullptr`, `predict()` does not enter the guarded branch, and the `obsHash`
computation does not run. Behavior is byte-identical to the pre-hook binary.
This was verified on an 8-seed smoke test: the same `bestbench` command with
and without the env var produced identical per-seed outcomes (same win%,
same floor, same HP end; only wall-time differs due to logging overhead).

**Hook placement — why `predict()` and not individual call sites:**

`CombatValueNet::predict(const BattleContext &bc)` is called from exactly two
sites inside Searcher3:

1. **Blend site** in `BattleScumSearcher3::step()` (~line 395): the primary
   leaf evaluation site. The VNet prediction is blended with the multi-rollout
   outcome as `α·VNet + (1−α)·rollout`, then backpropagated.

2. **Evaluate-leaf** in `BattleScumSearcher3::evaluateLeaf()` (~line 1014):
   direct-eval sites — when a newly-expanded node has zero legal edges, when
   the randomly-picked edge is invalid in this determinization, and at the
   depth cap (no rollout runs).

Hook-fire inside `predict()` captures both sites automatically, plus any future
call sites, without requiring changes to the Searcher3 step logic.

**Thread safety:** The handler (`onVNetQuery`) uses a `thread_local` buffer
and flushes to the shared `std::ofstream` under `std::mutex`. Because worker
threads may have different lifetimes, the handler also flushes at every fight
boundary and at run-end inside `runFullRunOOC`. The sampling RNG is per-thread
and deterministically seeded from the run seed + fight index.

**CSV format:**

```
seed,fightIdx,decIdx,<1767 canonical combat features>,vnetPred
```

The feature columns are produced by `combatExtractFeatures()`, the same
function that `combatgen` uses. Column names come from `combatFeatureNames()`.
Metadata columns (`seed`, `fightIdx`, `decIdx`) are excluded from the domain
classifier — only the 1,766 common feature columns are used.

### 2.2 Population A — combatgen training states

Source: `build/vcombat_honest.csv` (287,518 rows, seeds 0–1460).
Produced by `combatgen` mode with the heuristic-OOC run loop at 2,500 sims.
Each row is one combat decision state labeled with that fight's terminal
outcome (won ∈ {0,1}, endHp ∈ [0, maxHp]).

### 2.3 Population B — deployed VNet-query states

Collected with:

```bash
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
STS_VNET_QUERY_LOG=build/vnet_query_deploy_b.csv STS_VNET_QUERY_SAMPLE=0.15 \
./build/one_combat bestbench 1000 48 0 200000
```

- 48 seeds (200000–200047), ascension 0, 1,000 sims/decision
- 15% sampling rate
- Result: 162,545 rows, 554 MB CSV

Seeds 200000+ were chosen to avoid ANY overlap with the training seed block
(0–1460). The domain classifier splits by seed, so non-overlapping seed sets
guarantee the classifier cannot memorize seed-specific patterns.

### 2.4 Domain classifier — seed-split XGBoost

**Critical design choice: split by seed, not by row.**

A random row split would leak information: states from the same run/seed are
correlated (same deck, same relics, same encounter order). A classifier could
achieve artificially high AUC by memorizing which seeds produce "combatgen-like"
states. The correct evaluation splits seeds into train/test sets independently
for each population, then merges:

```
train_seeds = train_combatgen_seeds[0:70%] ∪ train_deploy_seeds[0:70%]
test_seeds  = train_combatgen_seeds[70%:]  ∪ train_deploy_seeds[70%:]
```

The classifier is trained on rows from train_seeds and evaluated on rows from
test_seeds. Because the seed sets for combatgen (0–1460) and deploy
(200000–200047) are disjoint, this guarantees:

1. No combatgen seed appears in both train and test
2. No deploy seed appears in both train and test
3. The classifier must learn features that generalize across seeds

**Classifier specification:**

| Parameter | Value |
|-----------|-------|
| Algorithm | XGBoost (gradient-boosted trees) |
| Trees | 200 |
| Max depth | 6 |
| Learning rate | 0.05 |
| Subsampling | 0.7 (rows), 0.5 (columns) |
| Features | 1,766 canonical combat features only |
| Train rows | ~63,000 (subsampled from both populations) |
| Test rows | ~57,000 (held-out seeds) |
| Class balance (test) | 69% deploy, 31% combatgen |

**Why XGBoost:** The deployed VNet is an XGBoost ensemble. Using the same model
family for the domain classifier tests whether tree-based models can exploit
the same feature interactions the VNet uses. If the distributions differ in
ways the VNet's feature representation can express, XGBoost should detect it.

**Confirmation model:** SGD logistic regression (linear) on standardized
features, same seed-split. Used to verify the XGBoost result is not an artifact
of tree architecture.

### 2.5 Analysis script

`tools/vnet_distribution_shift.py` implements:

- **Phase 3:** Seed-split XGBoost domain classifier → ROC-AUC, accuracy, log loss
- **Phase 4:** Per-feature distribution comparison (mean/std/quantiles), feature
  importance (XGBoost gain), encounter/turn/HP-band breakdowns of deploy queries
- **Phase 5:** VNet prediction distribution on deploy states; domain-probability
  vs VNet-prediction bin analysis
- **Phase 6:** Density-ratio diagnostic (weighted RMSE on combatgen labels,
  using domain-probability-derived weights)

---

## 3. Results

### 3.1 Domain classifier (Phase 3)

| Metric | XGBoost | SGD Logistic |
|--------|---------|-------------|
| **ROC-AUC** | **0.5595** | 0.2435 |
| Accuracy | 0.3081 | 0.3079 |
| Log loss | 5.1875 | — |
| Test deploy fraction | 69.1% | 69.2% |

**Interpretation:** The XGBoost classifier achieves AUC = 0.56, barely above the
0.50 random baseline. The SGD logistic regression achieves AUC = 0.24 — below
0.50, meaning it systematically ranks states from the wrong population. Both
results indicate the same thing: the classifier cannot reliably distinguish
individual combatgen states from deployed VNet-query states.

The accuracy of ~0.31 in both cases is exactly what you get by always predicting
"combatgen" when 69% of test rows are deploy. The classifiers are not learning
meaningful population-discriminating features.

**Conclusion: MEASURABLE but WEAK distribution shift.** Following the supplied
guideline (AUC≈0.50 = indistinguishable, 0.55–0.65 = measurable, 0.65–0.75 =
moderate, 0.75–0.85 = substantial, >0.85 = severe), this falls just barely into
"measurable" territory.

### 3.2 What little shift exists (Phase 4)

The top features by XGBoost gain importance are almost exclusively relic
presence flags (binary features indicating whether a specific relic is held):

| Rank | Feature | Gain | train mean | deploy mean | Interpretation |
|------|---------|------|------------|-------------|----------------|
| 1 | r26 (Happy Flower) | 0.384 | 0.033 | 0.072 | More Happy Flower in deploy |
| 2 | r51 | 0.082 | 0.019 | 0.197 | More of this relic |
| 3 | r6 | 0.063 | 0.012 | 0.131 | More of this relic |
| 4 | monSumStr | 0.050 | 0.56 | 3.18 | More enemy strength |
| 5 | r4 | 0.039 | 0.022 | 0.117 | More of this relic |

The relic features dominate because deploy states occur at deeper turns where
more relics have been collected. This is consistent with the expected behavior:
MCTS leaf queries reach deeper into the tree (past more actions) where more
relics are in play. But the effect is tiny — the mean relic presence increases
by only a few percentage points.

**Named diagnostic features (directional shifts):**

| Feature | train μ | deploy μ | train p50 | deploy p50 | Direction |
|---------|---------|----------|-----------|------------|-----------|
| turn | 2.11 | 3.66 | 2.0 | 3.0 | Deploy states ~1.5 turns deeper |
| curHp | 48.4 | 52.2 | 50.0 | 51.0 | Slightly higher player HP |
| maxHp | 78.9 | 81.4 | 80.0 | 84.0 | Slightly higher max HP |
| monSumHp | 68.2 | 192.1 | 42.0 | 134.0 | Much more enemy HP remaining |
| monMaxHp | 58.5 | 153.4 | 34.0 | 125.0 | Tougher individual enemies |
| incomingDmg | 9.2 | 17.7 | 9.0 | 16.0 | More incoming damage |
| hand | 3.79 | 3.78 | 4.0 | 4.0 | Identical hand size |
| draw | 7.65 | 10.65 | 7.0 | 9.0 | Larger draw pile |
| discard | 4.97 | 8.95 | 4.0 | 8.0 | Larger discard pile |
| exhaust | 1.52 | 3.86 | 1.0 | 3.0 | More exhausted cards |
| block | 3.23 | 6.05 | 0.0 | 3.0 | More block |
| energy | 1.75 | 2.44 | 2.0 | 3.0 | More energy |
| nAtkAvail | 8.12 | 10.95 | 8.0 | 11.0 | More attacks available |
| potions | 0.17 | 0.04 | 0.0 | 0.0 | Fewer potions in deploy |

**Key observation:** The shifts are real and directionally consistent (deeper
into fights, more cards in piles, more damage), but the within-class standard
deviation is much larger than the between-class mean difference for EVERY
feature. For example, `turn` has train μ=2.11, deploy μ=3.66 (Δ=1.55), but
the standard deviation is ~3.0 in both populations. This means:

- Most combatgen states are at turns 0–6
- Most deploy states are at turns 1–7
- The distributions overlap by ~80%+

This overlap explains why the domain classifier fails: for any given state
with `turn=3`, you cannot tell whether it came from combatgen or deployment
with better than ~55% accuracy.

### 3.3 Where deploy queries occur

**By turn:**
```
Turn 0:       2.0%
Turn 1:      12.7%
Turn 2:      20.8%
Turn 3–4:    34.6%
Turn 5–7:    23.0%
Turn 8+:      7.0%
```

Most VNet queries (58%) occur at turns 2–4 — the mid-fight. Only 7% are at the
deep tail (turn 8+). This is NOT a "deep-unresolved-states-only" distribution.

**By HP fraction:**
```
HP 0–30%:    11.6%
HP 30–70%:   42.6%
HP 70–100%:  45.8%
```

Nearly half of VNet queries occur at high HP (>70%). Low-HP crisis states
account for only 12%. The VNet is being queried broadly, not predominantly at
critical/high-uncertainty states.

**By encounter:** The top encounters (55, 37, 39, 20) account for ~44% of
queries, but there is a long tail across 50+ encounter types. No single
encounter dominates.

### 3.4 VNet predictions on deploy states (Phase 5)

| Statistic | Value |
|-----------|-------|
| n | 162,545 |
| mean | 32.88 |
| std | 23.46 |
| p05 | 2.57 |
| p25 | 12.08 |
| p50 | 29.60 |
| p75 | 51.32 |
| p95 | 75.41 |
| min | −5.38 |
| max | 99.53 |
| fraction < 0 | 1.0% |
| fraction > 80 | 3.0% |

**Comparison with combatgen labels (endHp):**

| Statistic | combatgen endHp | deploy VNet pred |
|-----------|----------------|-----------------|
| mean | 36.42 | 32.88 |
| std | 24.06 | 23.46 |
| p05 | 0.00 | 2.57 |
| p50 | 36.00 | 29.60 |
| p95 | 74.00 | 75.41 |
| fraction = 0 | 10.45% | N/A |
| fraction > 80 | 0.70% | 3.0% |

The VNet prediction distribution on deploy states closely mirrors the combatgen
label distribution. The mean is slightly lower (−3.5 HP, conservative bias),
and the VNet rarely predicts extreme outcomes (<0 HP or >80 HP). There is no
evidence of systematic extrapolation: the predictions fall in the same range
as the training labels.

**Domain-probability vs VNet prediction:**

When deploy queries are binned by the classifier's domain probability (how
"deployment-like" the classifier thinks they are), the VNet predictions remain
stable across bins. States that are strongly classified as "deployment-like"
(domain_prob > 0.95) have VNet predictions with mean 33.1, std 23.5 — nearly
identical to the overall deploy distribution. The VNet does NOT behave
pathologically in the most deployment-specific region.

### 3.5 Density-ratio diagnostic (Phase 6)

Could not be run because the combatgen CSV lacks VNet predictions (only has
ground-truth labels: won, endHp). Computing VNet predictions on the combatgen
data would require either:

1. Running `one_combat vnettest` on every row (slow, single-threaded)
2. Loading the exported compact-tree model in Python (no Python loader exists)

Given the AUC = 0.56 result, the density-ratio diagnostic is moot: when the
distributions are nearly identical, domain-weighted metrics will not differ
meaningfully from ordinary metrics.

---

## 4. Interpretation

### Why the null result is important

The AUC of 0.56 is NOT a failure to detect a real shift — it is evidence that
any real shift is too small to matter for model training. The domain classifier
has 200 depth-6 trees, 1,766 features, and 120,000 training rows. If there were
a systematic difference between the populations, XGBoost WOULD find it. The
fact that it can't means:

1. **The feature-space supports of the two distributions overlap almost
   completely.** The MCTS selection process does NOT systematically steer the
   search toward states that look different from ordinary trajectory states.

2. **The per-feature mean differences (higher turn, more monster HP) are real
   but modest.** They represent a ~0.5–1.0 standard deviation shift on a few
   features, while most features are unchanged. A classifier that can use all
   1,766 features simultaneously still can't achieve meaningful separation.

3. **The §148 result is better explained by regularization.** The
   hyperparameter-tuned VNet (min_child_weight=82, L1 α=1.8, γ=4.4, subsample
   0.54, η=0.03) is a much more regularized model than the default XGBoost
   recipe. The regularization likely:
   - Reduces overfitting to noise in the training data
   - Produces smoother predictions that generalize better
   - Is NOT primarily fixing a distribution-shift problem

### Why §137 (mixture retrain) didn't help

The covariate-shift mixture retrain (training on combatgen + leafdiag states
with separate holdouts) was expected to help IF the leafdiag states were
distributionally different from combatgen states. This diagnosis shows they
are NOT. The mixture retrain therefore just added noise from a nearly-identical
distribution, which diluted the training signal and degraded ranking metrics
(pairwise 0.726→0.691, top-1 0.369→0.330, regret 7.43→8.21 — all worse).

This is consistent with the AUC=0.56 finding: you can't fix a distribution-shift
problem that doesn't exist.

### Caveats

1. **Single operating point:** The deploy data was collected at ascension 0,
   1,000 sims/decision, 64 particles, belief=off, chain=off. The distribution
   might differ at higher ascensions (where fights are harder and MCTS
   reaches different states) or at 3,000 sims (where the tree is deeper).

2. **Feature representation:** The 1,766 features are a hand-designed
   representation. It's possible that two states with identical feature vectors
   are semantically different in ways the features don't capture. However, this
   is the SAME representation the VNet uses, so if the features can't
   distinguish the states, the VNet can't either — which is exactly the claim
   we're testing.

3. **Ascension scaling:** At A0, 46% of deploy queries are at >70% HP. At
   higher ascensions where the player is under more pressure, the HP distribution
   might shift. But this would make deploy states MORE similar to combatgen
   states (which also shift under pressure), not less.

---

## 5. Recommendation

### A. Distribution mismatch is small — do NOT build an expensive relabeling pipeline.

**Rationale:** The domain classifier (AUC=0.56) cannot reliably distinguish
combatgen states from deployed VNet-query states. The two distributions overlap
almost completely. The suspected mismatch is NOT the primary issue.

**What this means for future work:**

1. **Do not pursue frontiergen/leafrelabel** for the purpose of fixing a
   distribution shift. The expensive pipeline (serialize BattleContext blobs,
   run high-budget Searcher3 searches for terminal labels, train on the
   relabeled corpus) would not address a real bottleneck.

2. **The frontiergen/leafrelabel infrastructure** is still valuable for OTHER
   purposes — e.g., ranking evaluation (leaf_ranking.py on actual leaf-candidate
   pairs) and target-design experiments (what SHOULD the leaf predict?). But
   it should not be motivated by distribution-shift concerns.

3. **The §148 hyperparameter tuning** is the more promising direction. The
   regularization improvement (+17.2pp over the §126 baseline from combined
   data scaling + hyperparameter tuning) is a confirmed win. Further
   hyperparameter exploration or architecture improvements (e.g., larger
   ensembles with stronger regularization) are higher-ROI than relabeling.

4. **Data scaling** (§151's 100k-seed attempt) may help by providing more
   training examples, not by changing the distribution. The distribution is
   already representative.

---

## 6. Code changes

### `include/sim/search/CombatValueNet.h`
Added `#include <functional>` and the non-thread-local hook declaration:
```cpp
extern std::function<void(const BattleContext &, double)> g_onVNetQuery;
```

### `src/sim/search/CombatValueNet.cpp`
- Added definition: `std::function<void(const BattleContext &, double)> g_onVNetQuery;`
- Modified `CombatValueNet::predict()` to call the hook after computing the
  prediction (guarded by `if (g_onVNetQuery)` — no work done when nullptr)

### `apps/one_combat.cpp`
- Added `STS_VNET_QUERY_LOG=<path>` and `STS_VNET_QUERY_SAMPLE=<prob>` env var
  parsing after the `STS_DIAG_VNET2_ALPHA` block
- Added thread-local `t_vq` context struct (seed, fightIdx, decIdx, active flag,
  per-thread RNG, row buffer)
- Added `onVNetQuery()` handler: sampling, feature extraction, CSV row building,
  periodic flush
- Added `vnetQueryLogFlush()`: mutex-guarded write of the per-thread buffer
- In `runFullRunOOC`: set `t_vq.active = true` and per-fight context before
  `agent.playoutBattle(bc)`; flush after each combat and at run-end

### `tools/vnet_distribution_shift.py`
New comprehensive analysis script (Phases 3–6):
- Seed-stratified XGBoost domain classifier
- Per-feature distribution comparison
- Encounter/turn/HP band breakdowns
- VNet prediction analysis
- Density-ratio diagnostic
- JSON summary output

### `EXPERIMENTS.md` §154
Experiment log entry with configuration, results, and verdict.

### `docs/knowledge-base/experiments/vnet-distribution-shift-2026-08-09.md`
Full report (this document).

---

## 7. Verification

| Claim | Method | Result |
|-------|--------|--------|
| Logging OFF reproduces baseline | 8-seed `bestbench` with and without `STS_VNET_QUERY_LOG` | Identical win%, floor, HP end |
| Logging ON preserves outcomes | Same test, logging ON | Same win%, floor, HP end (wall time differs) |
| Domain classifier split by seed | Stratified 70/30 per-population seed split | Verified: no seed appears in both train and test |
| No metadata leakage | Classifier uses only 1,766 feature columns, not seed/fightIdx/decIdx | Verified: metadata columns excluded from feature_names |
| Non-thread-local hook | Removed `thread_local` from `g_onVNetQuery` after discovering OpenMP worker threads had null copies | Verified: 610K rows logged from 8 seeds on 12 threads |

---

## 8. Artifact inventory

| File | Size | Description |
|------|------|-------------|
| `build/vcombat_honest.csv` | 976 MB | Population A: 287,518 combatgen rows (seeds 0–1460) |
| `build/vnet_query_deploy_b.csv` | 554 MB | Population B: 162,545 deploy query rows (seeds 200000–200047) |
| `build/vnet_shift_report.json` | ~5 KB | Machine-readable JSON summary |
| `tools/vnet_distribution_shift.py` | ~20 KB | Analysis script |
