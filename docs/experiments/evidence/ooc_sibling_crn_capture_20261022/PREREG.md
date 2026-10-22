# Common-seed sibling recapture for the OOC value head (pre-registration, 2026-10-22)

Written before any source of this campaign ran. Philipp chose this step on 2026-10-22 at 14:51Z, after the
sibling-ranking round (#812, §641): "Erst Neuaufnahme mit gemeinsamen Seeds". He authorized the launch with 32 workers
at 15:34Z. It still needs the independent pre-launch review.

## Why
- The value head's sibling labels come from round 2 (§503). Each root child gets the mean of 64 rollout3 repeats, and
  every child has its own random streams.
- These labels are noisy. Rows of one action with the same public state scatter 1.40× more than the rollout SE
  predicts, and the noise ceiling of the §577 concordance is about 0.81 (§641). The median gap between the best and
  second-best action is 0.016, while a 64-repeat target scatters by about 0.025.
- The sibling-ranking loss brought the head to X2-B's level on round-2 VALIDATION (SR_w1 0.644, mean of three seeds
  0.636, §641). Cleaner labels should help that loss and make the evaluation sharper.
- `STS_OOC_SIBLING_COMMON_SEEDS=1` (§639) gives repeat r of every child of a root the same stream. In its smoke
  (seed 111144997, 18 roots, 32 repeats) the variance of sibling differences fell to 0.36 of independent streams
  (pooled), and the split-half agreement of the action orders rose from 0.687 to 0.737 at 16 repeats per half.

## Design
- **Producer:** [run_unit.sh](run_unit.sh). It is the gen-2 A/B arm A config (§621,
  `az_gen2_ab_20261021/run_unit.sh`) unchanged, plus the sibling capture:
  - student_sel (`cf6bf7fb…`) is the OOC prior and the rollout net, and X2-B is the leaf value;
  - OOC MCTS uses 4096 sims, the learned OOC stop 0.99, 25 % full-budget roots and the fast-root cap 1024;
  - real combats use the learned Silver stop with exact root budgets.
- **Capture:** `STS_OOC_SIBLING_EVERY=1` (every searched root), `_MAX_DEPTH=1` (the root's children), `_MAX_LEAVES=64`,
  `_REPEATS=32`, `_LONG=0`, `_COMMON_SEEDS=1`. The capture runs in a forked child, so play is byte-identical to a run
  without it (#810 smoke). Round 2 used the same settings with every 8th root, 64 repeats and independent streams.
- **Sources:** 320 fresh A20 seeds, 111144512–111144831, reserved by the coordinator (2026-10-22 14:56Z). The smoke
  uses 111144900.
  - The split is fixed now: VALIDATION is seed % 4 == 3 (80 sources) and TRAIN the other 240.
  - There is no CONFIRM split. Round 2's CONFIRM stays sealed.
- **Outputs per source (unit):** `S-<seed>.jsonl.gz` (policy rows; the last row is the outcome),
  `S-<seed>.sib.jsonl.gz`, `S-<seed>.ctm.jsonl.gz`, and the env, log, err and `.done` files (rc, wall, capture rows).
- **Valid source:** rc 0 and an outcome row with `complete` and `integrityPassed`.
  - rc 0 includes the banner checks (learned OOC stop, Act-4 CTM model, the heart1 net, fast-root cap 1024).
  - It also requires every capture row to carry `"commonSeeds": true` and 32 repeats.
  - Invalid sources are reported, not replaced.
- **Campaign:** `tools/cloud/worker.sh` with `schedule queue`, 4 lanes per worker and a 7 h timeout per source.

## Cost (estimate from the smoke)
- The smoke source (seed 111144900, died on floor 46 in Act 3) took 1,732 s: about 1,130 s of play and 600 s of
  capture (73 roots, 2,046 rows). The capture adds about half to the play time.
- The same play config averaged 773 s per game as gen-2 A/B arm A (§621, quoted in §640), and the longest gen-3
  games took about 1 h. So a source costs about 1,200 s on average, or 0.33 core-h.
- 320 sources: about 105 core-h. The longest sources take about 1.5 h, so the campaign needs about 1.5 h on 32 workers
  or 2.5 h on 16, plus about 10 min of setup.
- Data on the share: about 0.85 MB per source gzipped (about 270 MB).

## Analysis (offline; the tools come with the result)
1. **Integrity:** valid sources per split, groups (one root's children with at least 2 actions) and rows.
2. **Label noise on VALIDATION**, against round 2's independent streams:
   - the split-half agreement of sibling orders at 16 vs 16 repeats, and its curve over 2–16 repeats per half;
   - the noise ceiling of the §577 concordance (the #812 `sr_noise.py` model with the common-seed pair variance);
   - hidden-state scatter: rows with the same public state now share streams, so their remaining scatter is hidden
     state.
3. **Re-scoring on the new VALIDATION:** X2-B, M0.3, SR_w0.3, SR_w1 (seeds 0–2) and their blends, with w taken from
   the round-2 TRAIN holdout as in #812. The metrics are §577 concordance with a paired source bootstrap, and regret.
4. **Retraining** the sibling-ranking loss on the new TRAIN (alone and with round-2 TRAIN) is a separate GPU step with
   its own plan and go.
   - Common-seed labels serve ranking and difference losses only.
   - Within a root the shared noise acts like a per-root offset (review C of #810). The per-leaf SD is unchanged, so
     absolute (calibration) targets gain nothing.

## Expectations, stated before the run (descriptive, no gate)
- The split-half agreement at 16 vs 16 repeats is above round 2's at the same repeat count.
- Each evaluator's concordance is higher on the new VALIDATION than on round 2's, and their order is the same
  (X2-B and SR_w1 above M0.3). The producer differs from round 2's (student_sel stack, every root), so the two
  levels are not strictly comparable.

## Not in this plan
- Rollouts that do not end in X2-B (Philipp: maybe afterwards).
- Any training run or online A/B.

## Freeze
- RUN_COMMIT: the commit on `claude/project-thread-nqpi5o` that adds this directory to main `b8902b83` (the result
  records its hash).
- `code_commit` `90eb9f07` (main; the build inputs are identical), binary sha256 `dda76871…`
  (`linux-gcc-release-x86-64-v3`, in the bin-cache).
- Smoke on the frozen binary, seed 111144900 (cloud, 2026-10-22 15:00Z): rc 0, outcome complete and integrity
  passed, 1,732 s, 2,046 capture rows from 73 roots, all with `"commonSeeds": true` and 32 repeats. Split-half
  agreement at 16 vs 16 repeats: 0.683 (one source).
- Authorization: Philipp 2026-10-22 15:34Z, "Merge 812, go with 32 workers". Workers: 32, 4 lanes each.
