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
  not retrained.
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
  - The split-half agreement of sibling orders at 16 vs 16 repeats on VALIDATION (§644: 0.718).
  - The bias of swkeyed against base on identical rows: §644's labels are the base arm, paired row by row. Reported
    are the root-clustered pooled mean difference and the fraction of rows with |z| > 2.
  - A bias flag (pooled mean outside ±2 SE, or more than 8 % of rows with |z| > 2) stops the round before training.

## Gate (seed mean, primary)
- **IMPROVED:** treatment − control has a paired CI above 0, with the bars met.
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
