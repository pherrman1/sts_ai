# 2026-08-08 — Covariate-shift mixture retrain (§135a next experiment): combatgen + leafdiag mixture does NOT improve held-out search-leaf ranking — branch closed, no gameplay gate

Date: 2026-08-08
Session/task: Execute the pre-registered covariate-shift branch experiment
(EXPERIMENTS.md §135a verdict "Next experiment"; decision log
`2026-08-08-leaf-state-diagnostics.md` "Results addendum"): retrain the
deployed §126 end-HP combat value leaf on a MIXTURE of on-policy combatgen
states plus actual Searcher3 search-leaf states, with SEPARATE on-policy and
search-leaf holdouts, and test whether search-leaf RANKING on held-out
search-leaf states improves. Diagnostic artifact only — no default change,
no promotion, no gameplay gate in this task (pre-registered: ranking
evidence first).

## Decision

Train `build/v_combat_mix.txt` (endHp target, canonical §126 recipe,
combatgen-derived 733-feature set) on 429,807 mixture rows = all 287,517
combatgen rows (85% train) + leafdiag train-seed rows (seeds 126700-126747,
48 seeds; 85% train). Leafdiag eval seeds 126748-126763 (16 seeds, 72,458
rows) held out ENTIRELY (runtime-asserted). Holdouts per source by fight
group (seed, fightIdx), GroupShuffleSplit test_size 0.15 random_state 0.

**Verdict: the mixture does NOT improve held-out search-leaf ranking — it
makes all three pre-registered ranking metrics WORSE (pairwise 0.726 →
0.691, −3.5pp disjoint CIs; top-1 0.369 → 0.330, −3.9pp; regret 7.43 →
8.21, +0.78), and it HURTS the on-policy fit (val RMSE 8.23 vs 7.88
deployed control, MAE 5.97 vs 5.58).** Per the pre-registered rule (a
gameplay gate follows ONLY if ranking improves), **no gameplay gate; the
covariate-shift branch is closed; the deployed §126 `v_combat_honest.txt`
@α0.3 stays default.** The mixture model is a diagnostic artifact only.

## Rationale

- The §135a diagnostics found massive train-vs-search covariate shift
  (ROC-AUC 0.9998) as the primary suspect for the §134 online collapse, so
  the natural test was to give the end-HP target actual search-leaf states
  in training. **Inference** — the test is clean: identical leaves on the
  16 eval seeds (100% obsHash re-capture/join to `leafref_gate_64_4k.csv`),
  identical feature set to the deployed model (733 combatgen-derived
  features; the concatenated-frame filter would give 750 and confound the
  comparison), identical canonical recipe, and the training mixture is the
  only difference between the two compared models.
- **Inference** — training on the search-leaf distribution does not fix the
  ranking gap: the mixture correlates with the high-budget reference BETTER
  (Spearman 0.803 vs 0.790, Pearson 0.801 vs 0.779, MAE 28.1 vs 31.7 on own
  scales) yet ranks within decision groups worse — the same
  correlates-better-ranks-worse pattern as §134's direct-R model. Absolute
  fit to the (vnet-influenced) reference does not predict within-group
  ranking, even when the model is trained on the searched states themselves.
- The held-out 16-seed deployed numbers (pairwise 0.726, top-1 0.369)
  reproduce the §135a full-64-seed measurement (0.719 / 0.359), so the eval
  block is representative.

## Alternatives considered

- Filter features on the concatenated mixture frame (750 features) — rejected:
  the leafdiag 64-seed slice has different per-feature variance, and a
  different feature set would make "the training mixture" not the only
  difference vs the deployed model.
- A seed-level leafdiag holdout instead of the fight-group split — rejected:
  the pre-registered split is a fight-group split within the 48 train seeds
  (per-source, not across the concatenated set).
- Use the leafref reference values as training labels — rejected
  (pre-registered): they are vnet-influenced approximations, not ground
  truth; the training label is the fight outcome (fightEndHp/fightWon),
  same semantics as combatgen.
- Run a gameplay gate anyway — rejected: the pre-registered rule requires
  ranking improvement first; ranking got worse.

## Evidence

- `tools/train_value_mixture.py` (new; `train_value_combat.py` untouched):
  mixture training with per-source fight-group splits, eval-seed holdout
  with runtime assert, canonical §126 params, per-regime metrics sidecar.
- Training (local CUDA, RTX 3060 Ti): `build/v_combat_mix.json` +
  `_metrics.json` — rows combatgen 287,517 / leafdiag train-seed 216,079 /
  eval-seed held out 72,458 / train 429,807; best_iter 1349; 733 features.
  Per-regime val: on-policy (43,473) RMSE/MAE vs endHp 8.23/5.97, vs R
  48.37/45.65; search-leaf (30,316) 15.46/11.33, 49.20/46.20.
- Export + parity: `build/v_combat_mix.txt` (1,390 trees, base_score
  28.04239, sha256 `0ed6672c…`), `one_combat vnettest` PASS (max|diff|
  1.27e-4).
- Replay (identical to §135a): `one_combat leafdiag 16 1000 0
  build/leafdiag_mix_eval.csv 126748` with the full §135a gate env and
  `STS_DIAG_VNET2=build/v_combat_mix.txt` → 72,458 rows; 100% join to
  `build/leafref_gate_64_4k.csv` by (seed, fightIdx, decIdx, obsHash).
- Ranking: `tools/leaf_ranking.py` on `build/leafdiag_mix_eval.csv`
  (4,387 groups, 890,941 pairs, bootstrap seed 20260808): deployed endHp
  pairwise 0.7262 [0.7209,0.7318], top-1 0.3686 [0.3545,0.3823], regret
  7.431 [7.088,7.783], Spearman 0.790; mixture pairwise 0.6914
  [0.6858,0.6970], top-1 0.3298 [0.3152,0.3433], regret 8.209
  [7.850,8.569], Spearman 0.803. JSON `build/leaf_ranking_mix_eval.json`.
  Model-free cross-check (rawRolloutEval reference, no leafref, 4,085
  groups): pairwise 0.7289 vs 0.6921 (−3.7pp), top-1 0.335 vs 0.305, regret
  14.47 vs 15.83 — same direction, so the ranking disadvantage is not an
  artifact of the vnet-influenced leafref reference
  (`build/leaf_ranking_mix_eval_rawrollout.json`).
- Full record: EXPERIMENTS.md §137.

## Status and follow-up

- Closed (negative). The covariate-shift branch stays closed: adding
  search-leaf states to the endHp training objective does not improve
  held-out search-leaf ranking and hurts the on-policy fit. No gameplay
  gate scheduled (pre-registered rule). Deployed model and defaults
  unchanged.
- Open (inherited from §135a): what explains the §134 online collapse if
  not the (now ruled-out) search-leaf mixture fix — target semantics
  (end-HP as a shaping/potential function), blend-scale interactions, or
  the vnet-influenced reference bias are the remaining hypotheses;
  ranking-vs-absolute remains unresolved.
