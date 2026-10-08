# Post-primary GEN2 diagnosis and one next experiment

The frozen primary remains **LOCAL_CONDITIONAL_INCONCLUSIVE**: −1.17 percentage points, source-cluster 95% interval [−5.47,+3.13]. The separate exploratory analysis most strongly supports **testing whether four selection futures produce unstable winners**. It does not justify training a new model, deploying an old model, or attributing the result to one cause.

All 32 allocated sources, 63 retained states, 246 retained actions and 1,968 valid branches remain present. The implementation and five synthetic weighting tests received independent review before execution. Every interval below is pointwise, exploratory and unadjusted for the multiple diagnostics. The bootstrap resamples complete source clusters. No primary choice or artifact changed.

## Small-K selection and intervention exposure: H10

The frozen rollout rule's apparent selection gain was **+10.55pp**; the independent evaluation gain was **−1.17pp**. The source-balanced difference is **+11.72pp**, with a descriptive interval **[+6.64,+17.19]pp**. This is substantial selection optimism in this finite sample, not proof that sampling noise is the only cause.

The selector changed 19 of 63 decisions across 16 sources. On independent futures, 5 changed decisions improved, 7 tied and 7 worsened. Selection maxima tied at 47 decisions; the actual baseline was retained in 39 of those ties. Seventeen decisions had every retained action win all four evaluation futures—11 CARD and 6 BOSS decisions. Those are finite-sample ceilings, not evidence of true success probability one. Thus both unstable selection and limited informative action exposure matter; the experiment was not wholly inert.

| Family | States / exposed sources | Changed rollout actions | Selection gain | Independent gain | Selection optimism |
|---|---:|---:|---:|---:|---:|
| CARD_REWARD | 32 / 32 | 9 | +9.38pp | 0.00pp | +9.38pp |
| BOSS_RELIC | 31 / 31 | 10 | +11.29pp | −3.23pp | +14.52pp |

These family rows are conditional means over sources exposing that family. They must not be added. Their contributions under the original per-source total-state denominator are +0.39pp for CARD and −1.56pp for BOSS, summing to the frozen −1.17pp.

All seven adverse changed-rollout cases are retained in the machine report, including source610084112 decision55 CARD (selection +25pp, evaluation −50pp), source610084117 decision72 BOSS (+50pp, −50pp), and source610084129 decision32 BOSS (+25pp, −75pp). Each case includes action keys and raw row locators. These coarse four-future values are local diagnostic observations, not precise action values.

## Source heterogeneity remains distinct

At the primary source-weighted level, 21 source increments were zero, 7 negative and 4 positive; observed increments ranged from −37.5pp to +37.5pp. Sources contain different acts, decks and action sets; BOSS states span 18 Act1 and 13 Act2 decisions. One source has only a CARD state, while 31 have both families. The estimates preserve these source weights instead of treating the 1,968 branches as independent runs.

This sample cannot establish that a particular source class reliably benefits. A future larger-K comparison should evaluate both selectors at the **same fresh source states** and retain source-cluster uncertainty. Merely collecting more futures from a few favorable existing states would not resolve this heterogeneity.

## Historical-model mismatch is a separate issue: H11

The old models were not fitted on this tranche. Their selection predictions and frozen choices are preserved; evaluation-MAP predictions were computed only after the primary had finished.

| Model | Source/state/option-balanced bias, prediction minus outcome | CARD bias | BOSS bias | Overall Brier score |
|---|---:|---:|---:|---:|
| P0-s0 | +5.37pp [1.34,9.45] | +1.75pp | +8.31pp [1.71,15.00] | 0.15921 |
| F2-s0 | +3.98pp [−0.30,8.24] | +1.50pp | +5.79pp [−1.37,12.95] | 0.15926 |

The strongest overprediction is in BOSS states, especially P0. This is compatible with historical teacher or feature mismatch and differing case mix. It does **not** isolate temporal model drift or prove that correcting absolute probability bias would improve action ranking. P0 has 18 non-baseline options with a positive selection prediction gap but negative independent gain, and 15 with both positive; F2 has 16 and 18 respectively. Many further contrasts have zero observed independent gain. These options are dependent within states and sources; the report supplies source-balanced sign proportions rather than treating those counts as independent evidence.

The probability bins preserve source/state/option weights, report their weighted mass and raw source/row counts, and leave empty bins explicit. No-state sources are excluded from calibration denominators rather than assigned perfect error. There are no no-state sources in this completed cohort, but the rule is implemented and tested. No model calibration, threshold fitting or model selection was performed.

## Future and post-MAP variability: H13

BOSS post-MAP states vary more across sampled futures than CARD states. The mean within-option eight-future prediction range is 2.17pp for P0 and 3.57pp for F2 on BOSS, versus 0.091pp and 0.195pp on CARD. All 16 prespecified feature columns were present. For example, the source-balanced mean range of the `fmDShop` map feature is 4.90 on BOSS versus 0.25 on CARD; `fmCMonster` ranges are 6.32 versus 0.156. These values retain their original feature units.

However, the mean variance of paired final-outcome differences is **similar**: 0.205 for BOSS and 0.213 for CARD over all eight draws. Greater post-MAP variation therefore does not establish that map uncertainty is the dominant source of outcome noise. It remains entangled with action and future interactions. The all-eight summaries describe dispersion only; they do not replace the independent evaluation endpoint.

## Single best next discriminating experiment — proposal only

Run a **paired K4-versus-K16 selector comparison on fresh BOSS_RELIC source states**, using the same frozen fair teacher and existing sampler. The primary hypothesis is that four selection futures create unstable action rankings and that a modest increase improves the chosen action on independent futures. The competing explanation is that the apparent opportunity is driven by heterogeneous sources, near-ties or teacher/sampler limitations, so greater selection precision yields no independent benefit. Historical P0/F2 calibration cannot cause a difference in this comparison because neither model selects its actions.

Proposed fresh sources are **610084200–610084231**, 32 sources with at most one BOSS_RELIC state each, chosen by the producer's existing deterministic per-type reservoir. Preserve source breadth; do not select sources by previous outcomes, disagreement size or apparent regret. Retain valid no-state sources as zero incremental gain, and stop on any invalid source/branch rather than replace it.

Collect **K=32 coupled futures** per retained action. Freeze one selector from k0–3 and a second from k0–15, with the same baseline-favored tie rule. Save and hash both sets of choices before opening **k16–31**. The single primary endpoint is the equal-source mean paired independent final-win difference **K16 choice minus K4 choice**, with a source-cluster 10,000-replicate interval. Report per-source and per-act contributions descriptively; no subgroup selection, tuning or extension. Compare both choices with the captured baseline descriptively, without adding another promotion rule. A positive local result still requires a separate whole-run policy implementation and fresh qualification.

This is the smallest next comparison proposed here that preserves the current 32-source breadth while directly varying selection precision. It is not claimed to have enough power to qualify a 2pp population gain. One family and one state per source limit the cost. Typical four-option exposure gives 4,096 branches; retain the producer's conservative six-option bound of **6,144 branches**. Observed BOSS continuations cost 7.186 CPU seconds per branch, implying about **8.3 core-hours typical** or **12.4 core-hours at the six-option bound**, including source work before tail allowance. Proposed hard limits are **P4, four hours total wall time, 1,800 seconds per source**, hence at most **16 game-core-hours**, with failures preserved and no automatic extension. These are future proposal limits, not a new campaign authorization or launch.

The result would address small-K selection under the existing sampler. If it remains inconclusive, it would not establish model drift, no useful actions, or that a new architecture is needed. No further GEN2 simulation, training or retuning is launched by this report. The final confirmation cohort remains outside all of this analysis.

## Reproduction and custody

- Reviewed exploratory script: `learning/analyze_gen2_exploratory.py`, SHA256 `a160752d20a65ba85d3dd6c144accb73014137bfc479e7dd297b8be3c4fe5879`.
- Scientific/source review: `audit/gen2_exploratory_source_independent_review.json`, SHA256 `f72a5f83282e4eaa5f0cb782abfab541c564d840247ceeaf584d10c0b8020d40`.
- Full six-table machine report: `learning/gen2_tranche32_3ed9_exploratory.json`, SHA256 `540e5bfba6c58f35c2cfc8d6f81dd431e8b4abedc37e0ed6d5828ca26a29d99d`.
- Ordered invocation with before/after primary hashes: `learning/gen2_tranche32_3ed9/exploratory_invocation.json`, SHA256 `839fa8ada7d75b3214bd8b481669fde96642e35886b7bed751f26aa7bfb1f78f`.
- Independent primary audit: `audit/gen2_tranche32_primary_independent_review.json`, SHA256 `0c95e30824d47544005d8c1edf8c75183b4566ce7d3c3bdfc73ef963b4504b6a`.

The existing sampler retains latent counters and pool membership. These results are conditional on it, not an exact posterior over player-visible information. Only retained legal actions are covered. Old P0/F2 provenance limitations and source-level dependence remain, and the four-source canary is not pooled.
