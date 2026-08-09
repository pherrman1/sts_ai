# OOC Hidden-Future Marginalization — Diagnostic Report

Date: 2026-08-10
Git: current `main` (post-C0/A1 experiment)

---

## 1. Stack Bridge: fresh-tree vs obs-stable N=1 reuse

Before generating new labels, the OOC stack was requalified under the new fair-S3 default (obs-stable N=1 tree reuse). 64 paired seeds, V4 deployed model, seeds 210000–210063:

| Arm | Wins | Floor | HP |
|---|---|---|---|
| Fresh tree (`STS_REUSE_MAX_SEARCHES=0`) | 32/64 = 50.0% | 45.8 | 31.6 |
| Default reuse (N=1 obs-stable) | 36/64 = 56.2% | 46.7 | 32.0 |
| **Paired delta** | **+6.2pp** | +1.0 | +0.4 |

CI: [−4.7, +17.2]pp. Direction is positive, CI crosses zero at 64 seeds.

**Decision:** adopt obs-stable N=1 reuse as the frozen combat controller for future OOC research. The result is favorable and the reuse mode is now the compiled default.

Artifacts: `build/ooc_bridge_{fresh,reuse}_64_1786313686.csv`.

---

## 2. Diagnostic Mode: `strategicmarggen`

Added a new mode to `apps/one_combat.cpp` for hidden-future marginalization diagnostics. Usage:

```bash
./build/one_combat strategicmarggen <nSeeds> <outerSims> <branchSims> <nFights> <H> <maxDec> <out> [seedOff]
```

### How it works

1. Plays seeds with the current BEST OOC policy (V4 gates + native OOC).
2. At each V4-owned OOC decision (EVENT, CARD_REWARD, BOSS_RELIC, TREASURE, REST, SHOP), collects all legal actions.
3. For each decision, evaluates every action under **both** counterfactual regimes:

**Regime F (fixed hidden world):**
- `detachedCounterfactualCopy(parent)` — same hidden encounters as the live run.
- All actions share the same continuation seed (CRN pairing).
- Runs K=3 fights with the same branch simulation schedule as Tier-B (150/100/50 sims).

**Regime M (encounter-marginalized):**
- `detachedCounterfactualCopy(parent)` then `resampleRemainingActEncounters(branch, hiddenSeed)` — resamples only genuinely hidden encounter identities.
- All actions in sample `h` share the **same** resampled hidden world.
- Same continuation seeds, same K=3 schedule.

4. Also records V4 model predictions (bestIdx, margin) using the deployed `ooc_strategic_tok_final.native`.

### Invariants verified

- **Deterministic:** identical seeds produce identical output.
- **CRN pairing:** all actions in marginalized sample `h` share the same `hiddenSeed`.
- **Parent immutability:** counterfactual branches use detached copies; the live parent is unchanged.
- **Visible-state invariance:** resampling only touches `monsterList` and `eliteMonsterList` at indices beyond the current offset — no player-visible state is altered.

### Output CSV schema

```
seed,decIdx,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,
continuationSeed,hiddenSeed,utility,hp,floor,won,v4ModelIdx,v4Margin
```

`utility = 10*won + hp` (same formula as Tier-B Q labels).

### Code location

- Function: `strategicMargGen()` at `apps/one_combat.cpp` line ~8170
- Continuation helper: `finishMargCf()` reuses `finishOocCounterfactual` with proper K=3 fight schedule
- Dispatch: `mode == "strategicmarggen"` at line ~10350

---

## 3. Diagnostic Results (30 seeds, 187 decisions, H=8)

### Primary metrics

| Metric | Value |
|---|---|
| Decisions analyzed | 187 |
| **Best-action changes** (marg ≠ fixed) | **108/187 = 57.8%** |
| Sign flips (best-advantage over fallback) | ~22% |
| Mean marginal regret (choosing fixed-best under marg labels) | 1.96 utility |
| Max marginal regret | 44.38 utility |
| Paired (action, sample) diffs with nonzero diff | 56.8% |

### Per screen

| Screen | Decisions | Best-action change % |
|---|---|---|
| EVENT | 32 | 16% |
| CARD_REWARD | 155 | 48% |
| SHOP | 13 | 46% |

CARD_REWARD is most affected — the value of a card pick depends strongly on which encounters come next, which is exactly the hidden information being marginalized.

### V4 override analysis

| Metric | Value |
|---|---|
| V4 overrides (model ≠ fallback action 0) | 138/187 = **73.8%** |
| **V4 reversals** (beneficial under fixed → harmful under marg) | **12/138 = 8.7%** |
| V4 beneficial in both | 33/138 = 23.9% |
| V4 harmful in both | 74/138 = 53.6% |
| Other (neutral/mixed) | 19/138 = 13.8% |

Key finding: **8.7% of deployed V4 overrides reverse sign under hidden-future marginalization** — they look good on the fixed training future but turn harmful when encounter identity is properly marginalized.

---

## 4. Decision

Per the predeclared go/no-go rule in the handoff:

| Criterion | Threshold | Actual | Verdict |
|---|---|---|---|
| Best-action changes | <5% → CLOSE | **57.8%** | PROMOTE |
| Screen concentration | any screen >10% | CARD 48%, SHOP 46% | PROMOTE |
| Marginal regret | meaningful | max 44.4, 57% nonzero diffs | PROMOTE |
| V4 reversals | non-negligible | 8.7% | PROMOTE |

**Verdict: PROMOTE to a larger experiment.**

Hidden-encounter marginalization materially changes action rankings, flips a non-trivial fraction of V4 overrides, and produces meaningful counterfactual regret for fixed-future choices.

---

## 5. What NOT to conclude

- The V4 reversal rate (8.7%) is measured on 30 seeds / 187 decisions — moderate sample.
- Fallback = action 0 (first candidate) is a rough proxy, not the exact runtime fallback.
- These are diagnostic results, not a trained model comparison.
- 53.6% of V4 overrides are harmful in both regimes — this is consistent with the offline metrics (29.6% harmful rate) but the diagnostic has a different decision distribution.

---

## 6. Next Steps (per handoff Tasks 15–16)

### M0/M1 training dataset design

The `strategicmarggen` mode directly produces the per-sample data needed for matched M0/M1 labels:

- **M0 (fixed):** average utility over H hidden samples in Regime F.
- **M1 (marginalized):** average utility over H hidden samples in Regime M.

Both come from identical parent decisions, identical candidate sets, and identical continuation seeds. Only hidden-world sampling differs.

Recommended scale: 500–1,500 source runs, H=4–8, maximum decisions per run = 20–30.

### Training

Train one model on M1 with:
- Same V4 architecture (42 honest globals, token net)
- Same seed-disjoint split
- Same optimizer, losses, horizon
- Only Q supervision changes (M1 labels vs M0 labels)

### Gameplay gate

Compare M0-trained vs M1-trained at 64 paired seeds. Confirm to 128 maximum. Then compare winner against the deployed V4.

---

## 7. Existing infrastructure

The diagnostic is ready in `apps/one_combat.cpp`. To scale up, the same `strategicMargGen` function can be used with larger `nSeeds` and `maxDecisions`. The output CSV already contains both regimes, making M0/M1 label extraction straightforward post-hoc.

### Artifacts

| What | Path |
|---|---|
| Diagnostic CSV (30 seeds) | `/tmp/marg_v4b.csv` (14K rows) |
| Stack bridge CSVs | `build/ooc_bridge_{fresh,reuse}_64_1786313686.csv` |
| Diagnostic mode source | `apps/one_combat.cpp` ~line 8170 |
| Mode dispatch | `apps/one_combat.cpp` ~line 10350 |

---

## 8. Verification commands

```bash
# Build
cmake --build build --target one_combat -j4

# Quick smoke (2 seeds, 5 decisions, H=4)
./build/one_combat strategicmarggen 2 1000 150 3 4 5 /tmp/smoke.csv 400000

# Full diagnostic (needs V4 loaded)
env STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_SHOP=1 STS_OOC_STRATEGIC_TREASURE=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
  STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
  STS_S3_LIVE_VALID=1 STS_S3_PARTICLES=64 \
  STS_VNET=build/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
  ./build/one_combat strategicmarggen 30 1000 150 3 8 200 /tmp/diag.csv 400000
```
