# SR head on survival-weighted, keyed sibling labels (plan, 2026-10-28)

Written before any campaign source ran. After §703, Philipp chose "Use it for labels first" (2026-10-28 11:05Z) and asked
for the run size that trains the SR head with the same recipe (11:15Z). It needs his typed go for the capture and for
the GPU step.

## Question
§703's estimator (`swkeyed`: survival weighting plus event-keyed streams) cuts the variance of rollout3 sibling
differences to about 0.2 of today's common-seed estimator at equal CPU, without bias.
- If SR_crn_r2 is retrained on the same groups, with only the label estimator changed, does the head rank siblings
  better?
- §645 and §700 suggest label noise is not what holds this head back (cleaner CRN labels and twice the data were
  both flat). This round tests the remaining noise directly, with everything else held fixed.

## One variable: the label estimator
- **Same games and roots:**
  - Replay all 320 sources of the §644 recapture (seeds 111144512–111144831, used; no new seeds).
  - Today's main cannot replay them: even with every comparability flag, a source drifts at an act-2 elite.
    Engine fixes since 2026-10-22 (live problems 99–101, the Corruption fixes) have no restore flag
    ([SMOKE.md](SMOKE.md)).
  - So the producer is the §644 code commit `90eb9f07`, plus only the swkeyed code, as a backport:
    - commit `d4a4ec3c` (tree `0c09868c`), which is `git am` of [backport_90eb9f07.patch](backport_90eb9f07.patch) on
      `90eb9f07`;
    - the run branch `claude/project-thread-tt1jc5-run` is pushed only after Philipp's go;
    - [run_unit.sh](run_unit.sh) is §644's, plus `STS_OOC_SIBLING_ROLLOUT=${EST:-swkeyed}`.
  - With `EST=base`, the backport replays the sources bit-exactly: policy rows, CTM rows, capture rows and all 32
    repeat values match the original capture.
  - With `EST=swkeyed`, play and the rows stay identical, and only `extra.repeats` change. Its values equal main's
    `015618c` swkeyed values under the restore flags, on the source where main still reproduces.
- **Same labels per row:** 32 rollout3 repeats with common seeds, the same leaf (X2-B without calibration, as in
  §644), and the same cap of 8 rows per action. Only the estimator inside each repeat changes.
- **Same groups:**
  - `crn_groups.py` (data branch `claude/az-gen2-data`, `gen2/value-sr-crn/tools/`) is rerun on the replay.
  - Check: on the old capture it reproduces `crn_train_groups.jsonl.gz` (`dc5b67e0…`).
  - On the replay, the groups, rows, records and X2-B match the old file. Only `target` differs.
  - Groups lost to a failed swkeyed repeat are reported. Expected: about 0.
- **Same recipe:**
  - SR_crn_r2's command with `--seed 1` and `--seed 2` and `--patience 0`, as in §649.
  - Epoch chosen by §649's `pick_epoch.py`.
  - The groups file is the swkeyed CRN TRAIN file plus the unchanged round-2 TRAIN file.
- **Not changed:**
  - Round-2 TRAIN groups (8,458 of 23,587; independent streams, so swkeyed does not apply).
  - The game-outcome rows (rows_T1 on Philipp's PC).
  - So the new labels cover 64 % of the ranking groups (15,129 of 23,587) and none of the value rows.

## Arms
- **Control:** SR_crn_r2_s1 and SR_crn_r2_s2 as trained in §649. Their weights are on the data branch, so they are
  not retrained, provided the stack is unchanged:
  - The treatment's `train.log` hash line must match §649's: `distill.py` `40a9d5a3`, `monotone.py` `09efffaf`,
    heart1 `deaba59d`.
  - torch and CUDA versions are recorded.
  - If the PC's torch or CUDA stack differs from 10-23, control seed 1 is retrained on the new stack and compared
    instead.
- **Treatment:** SR_crn_r2_swk_s1 and SR_crn_r2_swk_s2.

## Evaluation (cloud; `crn_eval.py` as in §649)
- **Primary:**
  - The head alone on the common-seed VALIDATION with its §644 labels (80 sources). The evaluation target is
    unchanged.
  - The paired source bootstrap of treatment minus control, as the seed mean.
- **Secondary:**
  - The same scores on the swkeyed VALIDATION labels (a sharper target);
  - the blend with w chosen on the TRAIN holdout;
  - round-2 VALIDATION;
  - the prices check (−3 HP sign ≥ 85 %).
- **Label checks (capture only, before any training):**
  - The split-half agreement of sibling orders at 16 vs 16 repeats on VALIDATION (§644: 0.718), overall and by
    screen. §703 measured only map and rewards; shop, rest and event are about a third of the groups.
  - The bias of swkeyed against base on identical rows: §644's labels are the base arm, paired row by row. Reported
    are the root-clustered pooled mean difference and the fraction of rows with |z| > 2.
  - A bias flag (pooled mean outside ±2 SE, or more than 8 % of rows with |z| > 2) stops the round before training.
  - Groups lost to a failed swkeyed repeat (an error repeat, e.g. `survival_weight_rejection_limit`) are dropped
    from the treatment file by `crn_groups.py`'s rule. Their count is reported. If it exceeds 0.5 % of groups, the
    control is not comparable, and the round stops before training.

## Gate (seed mean, primary)
- **IMPROVED:** all of:
  - the paired source-bootstrap CI of the seed-mean difference is above 0;
  - each seed's difference is positive (swk_s1 − s1 > 0 and swk_s2 − s2 > 0), because the source bootstrap leaves
    out training-seed noise (§649's seed spread is about 0.007);
  - the bars hold for each treatment seed at its picked epoch: −3 HP sign ≥ 85 % in the prices check, and
    `pick_epoch.py`'s selection-fold BCE ≤ 0.570.
- **NOT_SHOWN:** otherwise. This is a negative result for the ledger, and it closes "label noise" as a lever for this
  head.

## Size and cost
- **Capture:** 320 sources, the same as §644.
  - §644 took 119.7 core-h (wall sum).
  - The capture rollouts are about 31 % of a source's wall time (two sources measured), and swkeyed rollouts cost
    1.30× on the same rows (smoke).
  - Expected about 130 core-h, or about 175 on today's slower containers.
  - 32 workers: about 2.5 h (the longest source takes about 1.5 h × 1.3).
  - 16 workers: about 4 h.
- **CPU per label:** 1.30× the base estimator at the same 32 repeats. We match data, not CPU. At 1.30× CPU the
  estimator still gives about 5× the precision (§703).
- **Training:** two runs of about 85 min each on Philipp's GPU, one after the other (§649).
- **Seeds:** none new; replays of 111144512–111144831.
- **Data:** about 220 MB on the share. The claims directory is deleted after the campaign (share file limit).

## Freeze (2026-10-28, after Philipp's "Go with 16 workers" at 15:20Z)
- Pre-launch review PASS (reviewer J, `/mnt/project-files/reviews/pr903-prelaunch-review.md`); its fixes are in this plan.
- **RUN_COMMIT:** the commit on `claude/project-thread-tt1jc5-run` that adds this directory to `d4a4ec3c`. The result
  records its hash.
- **code_commit** `d4a4ec3c` (= `90eb9f07` + [backport_90eb9f07.patch](backport_90eb9f07.patch)); binary sha256
  `382997c2…` (`linux-gcc-release-x86-64-v3`, in the bin-cache).
- **Campaign:** [campaign.manifest](campaign.manifest), with 16 workers, 4 lanes each, a queue schedule and a 7 h
  timeout per source. [units.txt](units.txt) holds the 320 §644 seeds, ordered longest first by their §644 wall time.
- **Share:** `/mnt/project-files/ooc-swkeyed-labels`. Its `claims/` directory is deleted after verification (the
  share's file limit).

## Deviation (2026-10-28, after the capture)
- **Bias rule triggered:** the row-level rule flagged the labels. 8.6 % of rows have |z| > 2 against the §644 labels
  on the same row (limit 8 %). The pooled mean difference passes: −0.00018 ± 0.00028.
- **Diagnosis** (60 sources, `results/`): each row's z conditions on that row's own §644 draws.
  - Rows whose base repeats saw no death come out low (−0.0115).
  - Rows with 3 or more base deaths come out high (+0.011).
  - Overall these cancel. This is the selection artefact §703 saw for sw.
- **Decision:** Philipp chose "Proceed to training" on 2026-10-28 at 19:04Z. The result reports the flag and this
  deviation.
- **Groups:** on the replay, `crn_groups.py` keeps all 15,129 TRAIN groups. They are identical to §644's apart from
  `target`. No group was lost.
- **Data branch:** `claude/az-gen2-data` `gen2/value-sr-swk/` (`975e4e5f`); the groups file's sha256 is `4541dc8a…`.

## Deviation 2: the prices check (written before the treatment weights were scored, 2026-10-28 ~21:40Z)
- §649's prices check data (#812's evaluation directory: perturbed records, `meta.json`, `prices.py`) no longer
  exists: it is not on the share, on Philipp's PC or in git.
- Replacement: [tools/swk_eval.py](tools/swk_eval.py) `--hp3 3000`.
  - It takes the first row of 3,000 VALIDATION groups with curHp > 3, lowers `obs.fixed_observation[0]` (curHp) by
    3, and reports the share of states whose value drops.
  - Calibration on the controls: SR_crn_r2_s1_ep13 84.1 % and s2_ep20 83.7 %. §649's prices check gave them 90.9 %
    and 89.4 %, so the proxy reads about 6 pp lower.
- Bar (replaces "−3 HP sign ≥ 85 %"): each treatment seed's proxy is at most 2 pp below its control seed's proxy.
- The scoring reproduces §649 exactly: SR_crn_r2_s1_ep13 0.6628, s2_ep20 0.6668, X2-B 0.6639 on the common-seed
  VALIDATION.
