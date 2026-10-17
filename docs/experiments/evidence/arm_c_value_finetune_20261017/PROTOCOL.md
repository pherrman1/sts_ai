# Arm C value head and trunk fine-tune on Heart outcomes — development protocol

Written before any fit. Philipp asked (2026-10-17, thread "Heart outcome collection
round 2") whether the value head of Arm C could be trained too, not only the prior head,
and answered "yes" to the lead's plan; he started this thread with "lets goo".

## Facts this rests on

- Arm C is student C (`student-c-68fe88be.pt`, SHA-256 `53739a43…`; native `studentc.bin`
  `eff2f74f…`), silverbot `NN` dim 64, 2 layers, 4 heads, 272,204 parameters.
  It was distilled on heart1's policy logits only (`h1distill-data/tools/distill.py`,
  `use_value_head=True` but no value loss), so its value head is untrained. §502 measured
  that untrained head at sibling concordance 0.516 (TRAIN+VALIDATION), chance level.
- §498–§501 trained heads on the **frozen** pooled vector. §501 found the frozen
  representation drops value information (adding 37 public scalars cut VALIDATION
  visitation BCE 0.4534 → 0.4298). §502 found every such head ranks sibling leaves
  worse than X2-B (0.507–0.530 vs 0.601). Fine-tuning the trunk is the untested lever.

## Data (no new game seeds)

- Outcome labels: §497 TRAIN (1,080 sources, 171,442 states, 126 Heart kills) and
  VALIDATION (360, 56,704, 47), the audited import `aafe4693…`. §497 TEST is consumed
  (§499) and has no reader. Round-2 (§503) TRAIN/VALIDATION is added in a second stage,
  after its import lands; round-2 CONFIRM stays sealed.
- Sibling ranking: §494 Arm C capture, TRAIN sources 110164000–039 (663 groups) for the
  auxiliary loss, VALIDATION 110164040–047 (114 groups) for evaluation. Targets are the
  64-rollout means; corpus manifest `5a45c78f…`, per-source capture hashes checked.
  §494 TEST (110164048–063) has no reader.

## Model and arms

Initialize from student C. Train every parameter (trunk, value head; policy head too,
held near the original by the guard). Loss per step:

`BCE(value logit, Heart outcome)` on 512 TRAIN states drawn uniformly over states
(equal-state weighting, §500's better arm) `+ 1.0 · KL(original policy ‖ new policy)` on
the same states `+ w · rank`, where `rank` is a pairwise logistic loss on value logits over
sibling leaves of the same parent (≥256 leaves of whole §494 TRAIN groups per step), each
pair weighted by its absolute 64-rollout target gap. Ranking is used instead of
regression because rollout3 targets end in X2-B and are on a different scale than Heart
outcome probability; only their order is distilled.

| Arm | w |
| --- | ---: |
| `outcome` | 0 |
| `rank05` | 0.5 |
| `rank2` | 2.0 |

Fixed: AdamW lr 3e-4, weight decay 0.01, 2,000 steps, one initialization (seed 0), value
bias initialized to logit(TRAIN state rate), evaluation every 100 steps. Deterministic
CUDA float32, TF32 off, `CUBLAS_WORKSPACE_CONFIG=:4096:8`, RTX 3060 Ti.

## Selection and reporting

Per arm, the checkpoint with the lowest §497 VALIDATION visitation BCE (equal-state, the
§500/§501 metric) is selected. For every arm, report at the selected step and as a
trajectory: VALIDATION visitation BCE, Brier and AUROC; §494 VALIDATION sibling
concordance and regret next to X2-B and one rollout3 on the same 114 groups (X2-B 0.621,
rollout3 0.554 there; 0.601 is the 777-group TRAIN+VALIDATION figure, which the rank arms
train on); policy top-1 agreement and KL against the original on VALIDATION states.
References: §500/§501 arm A (frozen pooled, MLP head) 0.45341 and arm C (pooled + public)
0.42983 visitation BCE on the same VALIDATION population.

No arm is promoted. A candidate for the round-2 stage needs VALIDATION visitation BCE
below 0.45341 **and** §494 VALIDATION concordance at least X2-B's on those groups. With 8
sibling sources that concordance is noisy, so it is reported with a source bootstrap and
read as development evidence only. The round-2 stage repeats the chosen arm(s) on §497 +
round-2 TRAIN, selects on both VALIDATION sets, and freezes one candidate; CONFIRM opens
once, only on Philipp's word.

## Non-goals

No native integration, gameplay, default change, RL loop, TEST or CONFIRM opening.
