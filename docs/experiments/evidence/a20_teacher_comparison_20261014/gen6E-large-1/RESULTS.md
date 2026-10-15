# Larger calibrated A20 teacher comparison

Exact verdict: **DESCRIPTIVE_COMPARISON_MEASURED**. All 32 prospective sources
completed, supplying **147 matched selected fights**, 5,696 redrawn Silver
forecast fights and 147 exact original-future controls. The excluded canary
passed all six slots. There were no unsupported selected states, invalid
combat rows, control mismatches, cap failures, retries or replacements.

The larger panel does **not resolve a forecast-fidelity difference** between
calibrated CTM, plain2k and gen6 E prior2k. It supplies directional conditional
evidence of a small combat-controller benefit for gen6 E at 2k. The 10k
conditions cost much more, and their incremental benefit over prior2k is
unresolved on the eight-source anchor panel. These are separate conclusions;
none qualifies OOC decision quality, a training teacher, or a default change.

## Identity and executed contract

- Baseline: `55fff33c83c3f5ed559cbf9f6cff17bdb30fe0ca`.
- Reviewed clean producer: `aa10fe8dfb6d4f63ba26f18a755b5f3f3a725117`.
- Binary SHA256: `f3f98d84ef57faba177ebcb3842ece31b65c9524cb168fb3f516b2641e8afa5f`.
- Freeze SHA256: `8e7ff63a781a94013ad79ca9fdb1bcd1525121abfff0ee120dec33c200cbd1aa`.
- Gen6 E: `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
- Calibrated A20 manifest: `00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea`;
  boss survival logit shift−0.18325317250506112. Native FAST/STD weight hashes
  are unchanged from PR #524, but this manifest is different. The pilot's old
  uncalibrated CTM RMSE is not a measurement of this calibrated configuration.
- [Prospective protocol](../PROTOCOL-LARGE.md): canary 97150901;
  main sources 97150910–97150941; anchors 97150910/14/18/22/26/30/34/38.
  A20 Ironclad, V4 OOC policy, OOC MCTS off, no keys, stop after Act 3.
  Plain10k source/reference, prior off. Silver forecasts use 16 paired
  independent futures; prior K8/weight 400/root bonus. CTM expectation is
  analytic; categorical forecasts use 32 samples. Selection is fixed before
  support/outcome filtering, without replacements.
- Four one-thread workers; 1200 CPU/1800 wall seconds/source, at most 33
  attempts including canary. All commands/receipts, environment/model pins,
  progress and CSV checkpoints are preserved. Total process CPU including
  canary: **5,074.70s** (84.58 CPU minutes), cohort 4,616.31s, canary 458.39s.
  Largest source: 918.11s, within the cap. No timing-derived quality claim.

## Coverage

574 source fights were captured;147 met the six chronological selection
slots. Forty-five absent slots were skipped. Supported state counts by source:
4 sources with 2,3 with 3,8 with 4,4 with 5,13 with 6.

| Selected slot | Source clusters |
| --- | ---: |
| Act 1 NORMAL |32|
| Act 1 ELITE |32|
| Act 1 BOSS |28|
| Act 2 ELITE |25|
| Act 2 BOSS |17|
| Act 3 BOSS |13|

The prospective coverage gate passes: 17≥12 Act 2 boss source clusters and 13≥8
Act 3 boss clusters. This is adequate for the stated conditional cross-act
reading, not universal encounter/support coverage. Source trajectories end
with 28 deaths and 4 victories; these are sampling paths under one fixed policy,
not a gameplay A/B or teacher win-rate comparison. All sources remain in the
principal equal-source summary, including early deaths.

## Main panel: 32 sources, 147 fights

Each source first averages its selected fight metrics; sources then receive
equal weight. Nominal95% intervals use 5,000 paired source-cluster bootstrap
resamples, fixed analysis seed 97150999. RMSE is sqrt of aggregated MSE,
not mean source RMSE. All fights/futures/sibling conditions stay with their
source cluster; intervals are not based on 147 iid fights.

| Forecaster | RAW HP RMSE [95% interval] | Death Brier | CPU per forecast |
| --- | ---: | ---: | ---: |
| Calibrated A20 CTM |12.02 [10.44,13.51]|0.04553|0.101ms expectation|
| Plain Silver 2k |11.85 [10.01,13.61]|0.04692|5.116s for16 futures|
| Gen6 E Silver 2k |11.60 [9.69,13.40]|0.04434|5.211s for16 futures|

Paired forecast MSE differences all include zero:
plain2k−CTM−3.92 [−41.27,36.38]; prior2k−CTM−9.86 [−52.41,32.73];
prior2k−plain2k−5.94 [−22.65,9.19], in HP². Death-Brier contrasts also
include zero. Numerical ordering does not establish forecast superiority. Intervals
including zero also do not establish equivalence or noninferiority.

The paired **controller** contrast prior2k−plain2k is:

- RAW HP:+0.796 [0.247,1.348] HP per fight.
- Death probability:−0.921 [−1.784,−0.068] percentage points.
- Search CPU:+0.00597 [0.00248,0.00961] seconds per fight.

Thus gen6 E is a promising 2k controller/reference candidate on this fixed
panel, despite the small pilot's opposite numerical forecast ordering.
These are nominal secondary intervals, without multiplicity correction;
the death bound is close to zero. They do not show increased whole-run wins
or better OOC candidate ranking. The forecast target is the independent
plain10k behavioral reference, whereas controller contrasts compare the two
policies directly under paired alternate futures.

## Anchor panel: 8 predetermined sources, 31 fights

| Forecaster | RAW HP RMSE [95% interval] | CPU per 16-future forecast |
| --- | ---: | ---: |
| Calibrated A20 CTM |11.33 [7.09,15.26]|0.0884ms expectation|
| Plain2k |11.23 [7.95,14.19]|5.288s|
| Gen6 E 2k |8.80 [6.42,10.73]|5.292s|
| Plain10k |9.79 [7.44,11.75]|28.590s|
| Gen6 E 10k |9.36 [7.05,11.06]|29.588s|

Only this subset supports 10k comparisons. Plain10k improves forecast MSE
relative to plain2k:−30.25 [−66.66,−3.08] HP². Prior2k also improves over
plain2k here:−48.61 [−89.91,−17.68] HP². The anchor subset has only **two
Act 2 boss and two Act 3 boss source clusters**, so it lacks the main panel's
later-act coverage. These nominal differences on 8 clusters do not transfer
to the full main panel, whose prior contrast remains unresolved. Prior10k−prior2k forecast MSE is +10.16 [−2.79,21.82] HP²:
no resolved incremental fidelity gain from increasing the prior arm's budget.

Controller HP/death contrasts for either budget increase include zero:
plain10k−plain2k HP+0.520 [−0.336,1.643], death−0.195 [−2.474,2.214]pp;
prior10k−prior2k HP−0.216 [−0.927,0.389], death−0.651 [−2.865,1.369]pp.
The average forecast CPU rises about 5.4×/5.6× on this same subset. This is
not evidence that 10k never helps; the anchor panel remains small.

## Interpretation and next experiment

**Inference:** retain the calibrated CTM as the inexpensive bulk evaluator.
This study finds no resolved main-panel fidelity advantage that justifies
replacing it with repeated native combats. Gen6 E at 2k is now the more
promising selective Silver audit candidate than the pilot suggested. Keep
plain10k as a small reference condition where additional search matters.

The next useful investigation is whether CTM and selective prior2k Silver
rank actual competing OOC continuations differently, and whether those
changes help under a matched CPU budget. This must be a separately reviewed,
prospectively frozen experiment. These combat entries are not an OOC-leaf
training corpus, and this study does not establish compressible leaf targets
or public-input sufficiency for #507/#506.

Silver costs time `playoutBattle` only; CTM expectation/sample costs include
input capture and their respective operation. No exact end-to-end cost ratio
is claimed. Each fight has one original-future reference, so the nominal
intervals retain reference randomness and finite 16-future Silver noise. The
panel is conditional on its fixed source policy and slots. Categorical scores
use unequal Monte Carlo precision (CTM 32 versus Silver 16) and remain
descriptive. Neither earlier attempt is pooled. No training, OOC gameplay
qualification, or model/runtime default promotion took place.

## Checks and preserved evidence

Release one_combat and runtime-probe builds passed. Final affected CTests:
**8/8 PASS**; core analyzer 21 tests and larger analyzer 4 synthetic tests pass.
The synthetic checks cover 16-future main/anchor validation, dependency custody,
paired cluster math/module isolation, and process/worker/integrity failures
stopping dispatch while draining owned jobs. An initial 4/8 CTest run lacked
the separate probe executable; its log is retained, the target was built,
and all 8 checks passed on rerun. Independent implementation/protocol review
passed before the clean source freeze. Independent outcome/scientific and
custody audits passed afterward: all original hashes/jobs/control checks
verified, principal metrics independently recalculated from raw CSVs, every
preregistered bootstrap interval independently reconstructed, and both saved
reports exactly reproduced in memory. See `outcome-review.json`. Full RAW
persistent-state/RNG equality is producer-checked and code-verified; the
retained CSV source/control fields were independently checked.

`freeze.json`, both reports, execution/review records, raw check logs, 314
original top-level output/metadata files in `raw-outputs.tar.gz`, and 13 exact
producer source/tool/protocol files in `frozen-source.tar.gz` accompany this
report. Binary/models and original raw directory remain locally preserved at
`build/a20-teacher-comparison/gen6E-large-1/`, with freeze hashes. CSV features
alone cannot reconstruct full combat entries. The raw original paths are
part of strict custody; do not silently rewrite the freeze to relocate them.

Knowledge impact: experiment evidence/current research and the maintained
opt-in dataset environment interface. Production defaults are unchanged.
