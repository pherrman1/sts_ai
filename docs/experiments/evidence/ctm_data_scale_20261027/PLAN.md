# CTM data scale and coverage (issue #885): inventory and plan (not run)

Status: **plan only, gated on #884.** Nothing here has been run, no seeds are used, no model is trained. Written
2026-10-27 from main `ed2dcb2` (#875 merged). Philipp's issue #885 asks: only if the CTM audit (#884) establishes a
decision-relevant CTM error, test whether more or better-distributed training data can reduce it, choosing only the
cheapest experiment that separates the leading explanations.

## 1. What the deployed A20 CTM is and what it was trained on

| layer | artifact | trained on | source |
|---|---|---|---|
| base net (fast `pathb-a20` DeepSets + Lizard composition) | `ae785ec2…` (§470 boss shift −0.183 in the manifest) | §443 Stage 1 corpus: 609,883 rows (TRAIN 486,628 / VAL 59,685 / TEST 63,570, source-seed hash split) from 31,995 seeds of `combattransitiongen 10000 20` with the **2026-10-12 deployed-V4 OOC policy** and that day's Silver; Stage 2 on Philipp's RTX 3060 Ti | §443, §470; data branch `claude/ctm-a20-data` |
| HP head fine-tune (A20 default, ADR-0059) | `ctm_finetune_hp_pathb_a20_v1.native` `bdbfafa6…`, manifest `31bb21f7…` | 97,561 real fights of the stage-3 A/B (§661, 1,024 seeds × 4 arms) + 25% of each batch from 112,906 Stage-1 rows; HP head only, CPU minutes (`tools/ctm_finetune.py`) | §672, §679 |
| per-fight calibration (A20 default, ADR-0058/0059) | `ctm_calibration_pathb_a20_ft_hp_v1.json` `8c226f23…` (34 groups: death-logit shift + won-fight HP scale) | the same 97,561 fights | §670, §672 |
| Act-4 survival model (A20 default, ADR-0048) | `models/candidates/ctm_act4_survival_trees.txt` | student-C era Act-4 fights | §527, §534 |

So survival (death) still comes from a net trained on **old OOC policy and old Silver** (§670's untested
explanation for the boss pessimism), corrected by a 34-parameter table. Only the HP head has seen current play.

### Existing evidence on data scale (no comparable 25/50/100% checkpoints exist)

- §672 survival fine-tune: trained on one seed-parity fold (~48.7k fights) it loses to the table (+0.0017 to +0.0026
  log loss); trained on both folds (97.5k) it **ties** the table on the held-out LC games (0.0689 vs 0.0698, CI
  [−0.0038, +0.0019]). "Twice the data helps; not enough to replace the table" — a two-point curve, but the two
  points are scored on different test sets, so it is not a clean learning curve.
- §672 HP head: one fold already gives most of the gain (8.46 → 7.74 MAE); no second point measured.
- §443 Stage 0/1: the A0 production net clamped to ascension 0 failed badly at A20; an A20 corpus fixed it — that is
  a domain shift, not a scale result.
- I searched the ledger and evidence folders for CTM learning curves (`learning curve`, `subsample`, `data scale`,
  `corpus size`): none exist. The only outcome learning curve is for `v_win` (`tools.vwin_outcome_curve`).

## 2. Current-play real-fight rows already on the share (free, no new games)

Every A20 A/B since #654 records each real combat as a `combat_transition_row_v2` row
(`STS_HEART_OUTCOME_CTM_ROWS=1`, teacher `heartoutcomegen-real-combat-learnedstop`). All campaigns below play combat with the same explicit
Silver flags (learned stop `gbt-0cac7cc64364`, exact root budgets, g7f_E root prior w400, reuse cap allocated,
`STS_ACTIVE_POWER_FEATURES=1`); they differ in OOC flags and code SHA. Counted from the verified unit tars on
2026-10-27 (`count.py` in this folder; ~20 min over the share):

| campaign (ledger) | code | after #852 (Act 4 strong) | units (seeds) | real-fight rows by arm | total |
|---|---|---|---|---|---|
| value-level A/B (§661) | `ee43726f` | no | 1,024 | A, M, S, MS | 97,561 (§670) |
| value-leaf-compare LC (§663) | | no | 256 | LC | 6,022 (§670) |
| CTM-calibration guard (§676) | `c38fa53d` | no | 512 | A 11,950 · C 12,236 | 24,186 |
| map-only OOC search (§683) | `a2968186` | no | 1,024 | MAP 24,017 · D 24,096 · OFF 23,236 | 71,349 |
| key rules (§691) | `db216ff0` | yes | 1,024 | R 21,780 · F 23,480 | 45,260 |
| Gumbel Q cap (§693) | `9a37d780` | yes | 512 | A 12,000 · B 11,785 | 23,785 |
| expert-anchored student (§696) | `f526cef9` | yes | 1,025 | A 23,632 · B 23,780 | 47,412 |
| card rule (#874, still running) | `4eb0b3c5` | yes | 230 so far | A 5,218 · B 5,084 · C 4,824 · D 5,262 | 20,388 so far |
| expert replay (2026-10-27) | `e65f2293` | yes | 331 | **none: `expertreplay` does not write CTM rows** | 0 |

About **116k post-#852 rows** (137k with the card-rule rows so far) and **199k pre-#852 rows**: roughly 3.4× the
data §672 fine-tuned on, all from today's or near-today's Silver. That is enough for a 4-point nested learning curve
without one new game. The value-level count is §670's; the others were counted here.

Act-4 combat changed with ADR-0060 (#852, Act 4 strong): campaigns whose code predates #852 have the older Heart and
Shield-and-Spear policy and must be either excluded from Act-4 rows or kept as a separate cohort. Other engine fixes
merged in between (e.g. #868 Calling Bell RNG) change outcomes slightly; code SHA is recorded per campaign.

**Test sets:**
- **Newest on-policy fights:** the card-rule A/B (code `4eb0b3c5`) once it finishes, never used for any fit.
- **OOC-policy shift, free:** the campaigns' arms play different OOC policies with the same combat (rigid vs flexible
  keys, map-only search off vs on, student_sel vs expert-anchored). Training on some arms and testing on held-out
  arms of *other seeds* measures how the error moves under a mild OOC shift. This is a weak proxy for coverage.
- **Branched states (strong coverage test), not free:** arm X of the expert-replay A/B (Baalorlord's OOC decisions,
  then today's Silver) would be the natural "branched" population for item 2, but `one_combat expertreplay` does
  not call the real-combat CTM capture (`apps/one_combat/expert_replay.cpp` includes `heart_outcome_capture.h` but
  never uses it), so those 329 games left no CTM rows. Getting them needs a small capture hook plus a re-run of the
  329 X games (external seeds, about 329 × 493 s ≈ 45 CPU-h, about 1 h on 16 workers): gameplay, so only with
  Philipp's typed go and only if the curve points at coverage.

## 3. Which experiment, and why

#885 lists three alternatives; it asks for the cheapest one that distinguishes the leading explanations.

| explanation for a #884 error | what distinguishes it | cost |
|---|---|---|
| **data scarcity** (too few current-play rows) | held-out error keeps falling from 50% to 100% of the pool, with fixed recipe | **CPU only, ~5 h on one cloud container, no seeds** |
| **coverage** (training states ≠ states the OOC search asks about) | error on held-out OOC-policy arms (free) or branched states (expert-replay X, needs a re-run) ≫ on-policy error at equal fight type, and does not close with more on-policy data | arm split free; branched states need a capture hook + ~45 CPU-h of games (Philipp's go) |
| **capacity / features** | train-fold error ≈ held-out error and the curve is flat; error concentrated in groups the inputs cannot see | falls out of the curve |
| **outcome noise** (single draws per state) | #884's repeated-outcome reference shows the residual is within the outcome variance | falls out of #884 |

**Recommendation: the data-scale learning curve (item 1), with a free held-out-arm split as the coverage column.** It needs no new games, separates scarcity from capacity, and its coverage column tells whether item 2
is worth any gameplay at all. Items 2 (new branched corpus) and 3 (repeated outcomes) are run only if the curve
points to them, and each needs Philipp's typed go, a frozen seed block and a worker count.

## 4. Learning-curve design (frozen before any fit, after #884 reports)

- **Gate:** run only if #884 reports a decision-relevant CTM error (sibling-ranking reversals or paired-delta error
  beyond its reference uncertainty). If #884 says no, this issue stops with this plan.
- **Recipe held fixed:** `tools/ctm_finetune.py` at main, warm start from the §470 fast artifact `ae785ec2…`, the §672
  configurations unchanged: (a) **HP head** (lr 1e-3, ≤ 30 epochs, L2-SP 10, 25% Stage-1 rows per batch) — the
  deployed recipe; (b) **survival encoder + head** (lr 3e-4, ≤ 12 epochs) — the part that still carries old-policy
  survival. Each fit followed by a refit of the per-fight table on its own training rows
  (`tools/ctm_calibration.py fit`), as the deployed pipeline does. Architecture, features and encoding untouched.
- **Training pool:** post-#852 campaigns except the test sets, plus the §661 stage-3 rows (pre-#852; non-Act-4 rows
  only). Split by source seed (all arms of a seed together); nested fractions **12.5 / 25 / 50 / 100%** of the
  training seeds, each with 3 fit seeds (fraction × variant × fit seed = 24 fits). Epochs chosen on ~10% inner
  validation seeds only, as §672.
- **Also scored at every fraction (capacity control):** the table alone on the raw §470 net (34 parameters; it should
  saturate early) and each fit's training-fold error (train–test gap).
- **Test sets (never used for any choice):** (T1) newest on-policy campaign fights; (T2) held-out OOC-policy arms of held-out seeds (e.g. key-rules F and map-only OFF), against the
  same-policy arms of the same seeds; (T3) #884's frozen combat-entry states with
  repeated Silver outcomes, and its OOC sibling pairs.
- **Metrics:** death log loss and calibration (ECE, reliability by decile), signed death bias and won-fight HP
  signed error / MAE per act × room and per boss; on T3 the decision metrics of #884 (paired sibling-delta error,
  ranking reversals vs the repeated-outcome reference). Scored by the C++ runtime (`one_combat ctmscorerows`)
  through research manifests, as §672. 95% source-seed bootstrap (2,000 reps), paired across fractions.
- **Decision rule:**
  - **Data scarcity supported** if 50% → 100% improves T1 death log loss or HP MAE with a paired CI excluding 0
    **and** #884's decision metric on T3 does not get worse. Then the cheap remedy is to keep pooling the CTM rows
    that every A/B already writes (~45k fights per 1,024-seed A/B) and refit periodically — not a dedicated
    collection campaign. Promotion would still need its own pre-registered precision gate (never NLL alone).
  - **Coverage suspected** if the T2 shifted-arm error exceeds the same-policy error by more than the CI, by fight
    group, and the gap does not shrink along the curve. Then the next step is the expert-replay branched test set
    (capture hook + re-run), and only after that item 2 (a matched-budget branched corpus; new seeds; Philipp's go).
  - **Capacity / features** if the curve is flat (50 → 100% CI includes 0) and train ≈ test error. Then more data of
    either kind will not help; the follow-up is a model/feature change, outside #885.
  - **Stop** if none of the three shows a credible gain or if the T3 decision metric does not move.

## 5. Cost (estimate, CPU only)

- Extract and encode ~330k rows from the unit tars into scratch (not onto the share: 50,000-file limit): ~1 h.
- 24 fine-tunes at minutes each on 4 CPUs (§672: "4 CPUs in minutes" at 97k rows): ~2–3 h.
- Export + `ctmscorerows` of each candidate on T1–T3 (~60k rows each): ~1 h.
- Total about **5 h of one cloud container**, no GPU, no new gameplay seeds. A GPU retrain of the full Stage-2 chain
  on the pooled current-play corpus (the "clean retrain" §672 mentions) is **not** part of this plan; it would need
  Philipp's PC GPU go and would only follow a positive curve.

## 6. Not done here, on purpose

- No collection campaign, no new seeds (#885: none before #884's evidence).
- No change to the deployed CTM or any default.
- Items 2 and 3 are conditional alternatives, not a sequence.
