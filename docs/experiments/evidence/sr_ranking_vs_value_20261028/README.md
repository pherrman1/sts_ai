# SR head: ranking loss or value loss? What the OOC search consumes, and what the existing heads deliver there (2026-10-28)

**Question** (Philipp, 2026-10-28 21:19Z): for the SR value head, is it more important to rank sibling options or to
have a better value loss? Should we optimise for ranking directly? Analysis plus an offline test on existing data. No
training, no gameplay, no seeds.

## 1. What search reads from the leaf

Read from current `main` (`880cfd6c`):

- **Where.** Production OOC search runs at map roots only (ADR-0061). Card rewards, rest sites, shops and events take
  the student_sel argmax. The leaf therefore matters only through map decisions.
- **How the head enters.** The head is the rollout3 anchor: from a tree leaf the chain plays three more combats, then
  the anchor values the endpoint (`OocGameContextModel::leafAnchorValue`, `apps/one_combat/ooc_mcts_adapter.cpp`).
  The anchor is either the head alone or the logit blend `(1 − w) logit X2-B + w logit head`. The head is never asked
  to order the root's siblings directly.
- **Averaging.** A root child's Q is the mean of backed-up values over chance successors and simulations. Each value
  is either terminal (death 0, Heart kill 1) or an anchor value at a different endpoint state. Two siblings are
  compared through averages of values of *different* states, mixed with terminals.
- **Readers of the absolute scale.**
  - PUCT reads `q + cPuct · prior · √N / (1 + n)` (`src/sim/search/OocMctsPlanner.cpp`). Scaling the leaf's
    differences by k acts like changing cPuct by 1/k.
  - The learned OOC stop reads per-action Q and visits, trained on the X2-B value scale (ADR-0053).
  - The level against the terminals is the implied death price. It was the only leaf change that ever won online:
    M0 +2.15 pp [+0.10, +4.25] (§661). Within an act M0 is a monotone, almost unit-slope transform, so it hardly
    changes any sibling order.
- **The default M0 calibration does not apply to the SR head.** It is applied only to the plain X2-B leaf. With
  `STS_OOC_MCTS_LEAF_HEART1_VALUE` set (head or blend), the anchor stays raw unless `STS_OOC_MCTS_LEAF_CALIBRATION`
  is given explicitly; it then applies on top of the head or blend.
- **What a pure ranking loss pins down.** A within-group pairwise loss (the RankNet term in `distill.py`
  `sr_loss`) is invariant to any per-group offset and only weakly fixes the scale of differences. It constrains
  neither the level against the terminals nor the scale of differences, which are what the averages, PUCT and the
  stop consume.

## 2. Existing evidence

| evidence | what it shows |
|---|---|
| §661 value-level A/B | Level-only change M0: **+2.15 pp**, IMPROVED. The SR_w1 blend, offline +0.025 ranking over X2-B (§644): **−0.6 pp**, NOT_SHOWN. |
| §504, §615 | Offline concordance and online play disagreed in direction, twice. |
| §712 card-rule screen | The SR head's argmax of post-pick states (a pure ranking use) lost −17.6 pp. As a search anchor it beat X2-B by +9.8 pp, but both lost to the prior. |
| §645, §649 | The ranking-selected epochs gain about +0.01 offline; the value stop ended training while ranking still rose. |
| §700, #903 | More data: flat. Cleaner (swkeyed) labels: flat. |
| §707 | Most leading sibling gaps are below 2 pp; per-sample noise is 14–26 pp. |
| §644 README | Map choices are the weakest screen for every evaluator; the blend gains nothing there. |

**Training curves** ([results/training_curves.json](results/training_curves.json); summaries of the §645/§649 runs
and the two #903 runs on `claude/az-gen2-data`):
- From epoch 6 on, the selection-fold value BCE moves with the mean prediction: correlation −0.71, −0.97, −0.85
  (SR_crn_r2 s0/s1/s2) and −0.78, −0.64 (swk s1/s2).
- The selection-fold AUC stays in 0.760–0.772 in every run.
- The mean prediction (0.25–0.31) sits below the mean outcome (0.341) at every epoch.
- So the BCE ≤ 0.570 bar in `pick_epoch.py` mostly filters epochs by level drift. Level drift is what a post-hoc
  calibration removes. It says little about whether the head still discriminates outcomes, which the flat AUC
  answers.

## 3. Offline test: the heads on the common-seed VALIDATION by what search uses

**Data.** The §644 capture, re-extracted and re-filtered with its own tools (578,987 rows, the same count as §644).
VALIDATION = source seed % 4 == 3: 5,587 roots, 80 sources, of which 1,364 roots are map roots.
**Tool.** [tools/sr_scale_eval.py](tools/sr_scale_eval.py), run with one_combat `193b0000…` (§645's binary).
**Heads.** All 11 exported SR heads:
- SR_crn_r2 seeds 0/1/2 at their fold, value-stop and ranking epochs;
- the two #903 swkeyed heads;
- SR_w1.

Weight hashes are in [results/weights.sha256](results/weights.sha256). The scoring reproduces §649: SR_crn_r2_s2_ep20
0.6668 alone and 0.7031 blended.
**Per head**, alone and blended at w 0.1, against two label sets:
- the raw labels (32 rollout3 repeats ending in raw X2-B, as trained);
- M0 labels: the same repeats with non-terminal endpoints re-valued by the A20 default M0, terminals kept, i.e. the
  leaf production uses since ADR-0057.

**Metrics:**
- §577 concordance;
- for sibling differences: the correlation r between predicted and label differences, RMS(predicted difference) /
  RMS(label difference), and the slope of label difference on predicted difference;
- level: mean prediction minus mean label.

Full output: [results/scale.txt](results/scale.txt), [results/scale.json](results/scale.json).
**CIs** are paired source bootstraps against raw X2-B. Against M0 X2-B only point differences are given.

### 3a. Map roots (the only roots production searches)

Concordance; "− X2-B" uses raw X2-B as the control, with the 95 % CI in brackets.

| head | raw labels | − X2-B | M0 labels | − X2-B |
|---|---|---|---|---|
| X2-B | 0.603 | – | 0.591 | – |
| X2-B with M0 | 0.599 | −0.003 | 0.602 | +0.011 [−0.000, +0.023] |
| s2_ep20 (online candidate) | 0.613 | +0.011 [−0.029, +0.049] | 0.604 | +0.013 [−0.024, +0.050] |
| s2_ep20 blend w 0.1 | 0.618 | +0.015 [−0.008, +0.038] | 0.610 | +0.019 [−0.001, +0.038] |
| swk_s1_ep18 blend | 0.613 | +0.011 [−0.016, +0.036] | 0.612 | +0.021 [−0.003, +0.043] |
| swk_s2_ep11 blend | 0.619 | +0.016 [−0.009, +0.039] | 0.615 | +0.023 [+0.001, +0.044] |
| SR_w1 blend (lost online in §661) | 0.604 | +0.001 [−0.018, +0.019] | 0.594 | +0.003 [−0.016, +0.020] |

- At map roots no head and no blend beats X2-B with M0 by more than about 0.01 in point estimate. Against M0 X2-B
  the s2_ep20 blend is +0.008 and the best swk blend +0.013, without CIs.
- The current candidate heads alone (s2_ep20, s1_ep13, both swk heads) are within +0.001 to +0.005 of it.
- The blend gains are three times larger off the map (non-map, raw labels: +0.045 [+0.036, +0.055] for s2_ep20),
  i.e. on roots production does not search.
- The online-loser SR_w1 blend and today's candidate differ by about 0.01–0.015 at map roots. That is the whole
  ranking progress since §661 where it could matter.

### 3b. Level and scale (all VALIDATION roots)

| head | level vs raw labels | level vs M0 labels | r (sibling diffs, M0 labels) | RMS ratio | slope |
|---|---|---|---|---|---|
| X2-B | +0.11 | +0.57 | 0.31 | 0.49 | 0.62 |
| X2-B with M0 | −0.42 | +0.03 | 0.47 | 0.83 | 0.57 |
| s2_ep20 | −0.45 | +0.01 | 0.40 | 2.18 | 0.18 |
| swk_s1_ep18 | −0.44 | +0.02 | 0.39 | 2.40 | 0.16 |
| s2_ep20 blend w 0.1 | +0.05 | +0.50 | 0.34 | 0.79 | 0.43 |

**Level.**
- The heads predict P(Heart kill). Their level matches the M0-ended labels (+0.01 to +0.04) and sits 0.45 below the
  raw labels they are ranked against.
- The blend sits on raw X2-B's level, 0.50 above M0. An online blend arm without an explicit
  `STS_OOC_MCTS_LEAF_CALIBRATION` would undo M0's death price.

**Scale.**
- The heads' sibling differences are 2.2–2.4 times as large as the label differences, with r ≈ 0.39. A calibrated
  predictor would have an RMS ratio near r and a slope near 1. Here the slope is 0.16–0.18: the head's differences
  are about five times too large for what they predict.
- The RankNet term rewards larger differences and nothing penalises them. Over epochs the ratio grows (s1: 1.77 at
  epoch 4, 2.11 at 13; swk 2.40).
- With w 0.1 the blend is mostly a shrinkage of the head's differences, which is why such a small w is optimal.
- As a search anchor, over-dispersed leaf differences act like a lower cPuct and a sharper learned-stop input.

**M0 labels.** Against the production-leaf labels, the heads alone lose some of their non-map ranking:
- s2_ep20 − raw X2-B is −0.014 [−0.027, −0.000] on non-map roots;
- against M0 X2-B (0.706 non-map) the head alone is about −0.015.

The raw labels end in raw X2-B and carry its death price, the miscalibration M0 fixed. A head trained to rank them
learns that price.

## 4. Answer

1. **Not ranking-only.** Search consumes averages of leaf values across different states, mixed with 0/1 terminals,
   read by PUCT and the stop in probability units.
   - A pairwise loss pins neither the level nor the scale of differences.
   - Both demonstrably matter: the level is M0's +2.15 pp, and the scale is 5× over-dispersed today.
   - The one online test of a ranking gain (SR_w1 blend, §661) was negative.
2. **The ranking gains are not where search acts.** At map roots every SR head and blend is within about 0.01–0.02
   of X2-B with M0, with CIs touching 0. The offline progress is on card rewards, rest sites, shops and events,
   which production does not search (ADR-0061).
3. **The BCE cap is the wrong guard, but a value term is needed.** In-training BCE varies with level drift (AUC
   flat). The guard should be calibration-invariant (AUC, or BCE after a per-act refit of the M0 form). The level
   should then be set post hoc with the existing `STS_OOC_MCTS_LEAF_CALIBRATION` (per act a + shared slope b, fitted
   on outcome rows as in §660).

## 5. Options, if the SR head is pursued further

In order of cost. None needs new engine code.

1. **Selection rule (no training, needs the per-epoch checkpoints on Philipp's PC).**
   - Export every saved epoch of the four 20-epoch runs (§649 s1/s2, #903 s1/s2) and score them with this tool.
   - Compare three selection rules on map roots with M0 labels: (i) today's `pick_epoch.py`; (ii) best in-training
     holdout with an AUC floor (≥ fold-epoch AUC − 0.005) instead of the BCE bar; (iii) the epoch with the smallest
     RMS ratio within 0.005 of the best holdout.
   - About 1 h of CPU on the PC plus 1 h in the cloud. It decides whether the 0.570 bar should go.
2. **Labels that end in the production leaf (cloud CPU, existing data).** Rebuild the TRAIN groups' targets with
   M0-ended repeats from the §644 and #903 extracts, as done here for VALIDATION. Retraining on them is option 3's
   GPU run.
3. **A scale-carrying pairwise loss (GPU, about 85 min per seed, needs Philipp's OK).**
   - Replace the RankNet term with a difference regression: per group, squared error between centred predicted
     probabilities and centred labels, weighted by the label precision.
   - Keep value BCE and anchor.
   - Seeds 1–2 on the M0-ended swk groups, scored here.
   - Gates fixed before running, at map roots with M0 labels:
     - concordance ≥ X2-B with M0 + 0.01 with the CI above 0;
     - slope of sibling differences 0.7–1.3;
     - selection-fold AUC ≥ control − 0.005.
4. **Only then an online test.** A map-root A/B against the M0 default, with the calibration set explicitly for the
   SR arm. It needs Philipp's go and seeds.

**Recommendation.**
- Do not tune the ranking loss further, and do not run online tests of the current heads at map roots: the offline
  margin there is about 0.01 with CIs touching 0.
- If Philipp wants to continue with the SR head, option 1 is cheap and settles the selection question.
- Option 3 is the one training run that addresses the measured problem (scale and level, not ranking).
- Otherwise park the SR head. Map-root decisions are where any leaf improvement has to show, and there X2-B with M0
  is not beaten.

## Caveats

- All labels are rollout3 means from the same chain and CTM. Agreement with them is agreement with the search's own
  estimator, not with the true action value (KB `research/ooc/root-quality.md`, B_rel). The #906 campaign measures
  that at card rewards.
- The M0 labels apply M0 post hoc to recorded endpoints (as §707 did). They are not a recapture with M0 active, so
  rollout policies and CTM draws are unchanged.
- The sibling-difference metrics weight roots by their number of action pairs and pool over sources. Concordance
  averages per source as §577 does.
- Head scores at sibling states measure the head where it was trained. In search it values rollout endpoints three
  combats later; nothing here measures it there.

## Reproduce

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/ooc_sibling_crn_capture_20261022 --extract EXT
python3 docs/experiments/evidence/ooc_sibling_crn_capture_20261022/tools/crn_analyze.py rows EXT CRN
ONE_COMBAT=<one_combat 193b0000…> python3 docs/experiments/evidence/sr_ranking_vs_value_20261028/tools/sr_scale_eval.py \
  EXT CRN OUT.json s2_ep20=SR_crn_r2_s2_ep20.bin s1_ep13=SR_crn_r2_s1_ep13.bin swk_s1_ep18=SR_swk_r2_s1_ep18.bin \
  swk_s2_ep11=SR_swk_r2_s2_ep11.bin s0_ep11=SR_crn_r2_ep11.bin s1_ep7=SR_crn_r2_s1_ep7.bin s2_ep9=SR_crn_r2_s2_ep9.bin \
  s1_ep4=SR_crn_r2_s1.bin s2_ep6=SR_crn_r2_s2.bin s0_ep8=SR_crn_r2.bin SR_w1=SR_w1.bin
```

- Weights: `claude/az-gen2-data` `gen2/value-sr-crn/weights/`, `gen2/value-sr-swk/weights/` and
  `gen2/value-sr/weights/SR_w1`.
- Runtime: extraction about 25 min over the share mount; scoring about 2 min per head on 4 cores; the metrics
  about 5 min.
