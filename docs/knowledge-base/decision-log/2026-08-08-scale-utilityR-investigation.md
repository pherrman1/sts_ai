# Decision log — 2026-08-08: utilityR scale investigation + combat-leaf line closure

## Context

Investigation into the best winrate gain area. Five parallel investigators
evaluated: 5.7.3 self-play relabeling, endHp-vs-utilityR online gap,
S3 belief/chain reopening, strategic Q-head q_top1, and frontier-leaf corpus.
Architect recommended starting with the direct-eval site share measurement as
the cheapest discriminator.

## Decisions

### 1. Direct-eval site share measurement (searchdiag 32 seeds)

- **Decision:** Run `one_combat searchdiag` on the deployed S3 config (32 seeds,
  @1k/64p, block 126700–126731) to measure the share of leaf evaluations at
  unblended sites.
- **Rationale:** The §139–§141 diagnostic experiments analyzed only blend-site
  leaves (α=0.3). Unblended direct-eval sites (depth-cap, no-legal-action)
  fire at full model weight and could explain the ±12pp gap if common.
- **Result:** Unblended direct-eval sites are 0.003% of all model evaluations
  (231 out of 8.67M). Only 34/9,915 decisions had any leafDirectEval > 0.
  With `STS_ROLLOUT_DEPTH=0`, every rollout terminates — no depth-cap evals,
  and no-legal-action at the live state almost never occurs.
- **Implication:** The ±12pp gap cannot come from unblended sites. It must be
  PUCT value-scale dynamics (utilityR's [0,~150] band vs endHp's [0,~80]).

### 2. Scale-controlled utilityR experiment

- **Decision:** Rescale the §134 utilityR model (`build/v_combat_utility_direct.txt`,
  611 trees) by the base_score ratio (25.97/62.82 = 0.4135) to match endHp's
  output band, then gate rescaled vs non-scaled at α=0.1 (128 paired seeds).
- **Rationale:** If the ±12pp gap is PUCT scale dynamics, matching the output
  scale should close the gap. The experiment tests whether better reference
  correlation (Spearman 0.820 vs 0.769) can translate online after fixing scale.
- **Result:** Rescaling recovers **+10.9pp** (CI [+1.6, +20.3], significant).
  Non-scaled 36.7% → scaled 47.7%. PUCT value-scale dynamics confirmed as the
  mechanism.

### 3. Scale × α grid sweep (32 seeds)

- **Decision:** Sweep 6 scale factors × 5 α values on 32 seeds each to find
  the optimal operating point.
- **Result:** Peak at scale≈0.41 (base_score–matched), α≈0.10 (50.0% on 32
  seeds). Higher scales at low α degrade (s=0.50 α=0.10 = 31%), higher α
  degrades (s=0.41 α=0.50 = 40%). The sweet spot is narrow and confirms the
  mechanism.

### 4. Definitive gate: scaled utilityR @α=0.10 vs deployed endHp @α=0.30

- **Decision:** 128 paired seeds on block 126700–126827, each model at its
  best operating point.
- **Result:** Deployed endHp 56.2% vs scaled utilityR 47.7% = **−8.6pp**
  (CI [−18.8, +0.8]). The rescaled utilityR does NOT beat endHp.

### 5. UtilityR objective line closure

- **Decision:** Close the utilityR combat-leaf objective line. Three
  independent gates are negative: §133 quantile-R −12.9pp, §134 direct-R
  −12.1pp, §142d rescaled-R −8.6pp. Rescaling fixes the scale interaction
  (+10.9pp recovered) but the value semantics (R = 50+endHp on win) rank
  combat states worse than raw endHp.
- **Deployed model:** `build/v_combat_honest.txt` @α=0.3 stays.

### 6. Combat-leaf model-improvement line exhausted

- **Decision:** Every alternate training target (quantile-R, direct-R,
  rescaled-R) and every training approach (mixture retrain §137, covariate-shift
  targeting) has been gated and lost. The remaining open question is whether a
  frontier-leaf-corpus-derived target (§136) could differ, but the historical
  record is uniformly negative. The research direction pivots to searcher-side
  structural changes — the only thing that has ever produced significant online
  gains in this project (live-valid +5.5pp, vnet leaf +12.5pp).

## Artifacts

- `build/sdiag_siteshare_32.csv` — 9,915 decisions, site-share breakdown
- `build/v_combat_utility_scaled.txt` — rescaled model (scale=0.4135)
- `build/v_combat_util_s{0.20,0.30,0.50,0.60,0.80}.txt` — sweep models
- `build/util_nonscale_128.csv` — non-scaled gate arm
- `build/util_scale_128.csv` — scaled gate arm
- `build/endhp_ref_128.csv` — endHp reference arm
- `build/sw_s*_a*.csv` — 32-seed sweep arms
- `EXPERIMENTS.md` §142 — full recorded entry

## Status

Closed. Combat-leaf model improvements are exhausted. UtilityR line closed.
Next: searchdiag data mining for searcher-side improvement targets, then
pivot to searcher-side structural experiments.
