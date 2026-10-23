# Learned OOC stop on M0's Q scale: still precise, fires more often (offline, 2026-10-23)

**Question.** The learned OOC stop (`models/candidates/ooc_learned_stop_trees.txt`, τ 0.99, §565) was trained on
roots whose leaves end in X2-B. The value-level A/B (`../value_level_ab_20261023/RESULT.md`) found the calibrated
leaf M0 better (+2.15 pp), with the stop firing earlier in every act. PREREG requires the stop checked on M0's Q scale
before M0 could become a default. Does the stop still pick what a longer search would pick when it fires under M0?

**Design.**
- [`run.sh`](run.sh): the A/B's arm A and M stacks (binary `56b29bf8…`, RUN_COMMIT `2b1b269d`), but with every
  searched root at the full 4096 simulations: no learned stop, no fast roots, gap stop off, exact visit lock on, as in
  the stop's training data. `STS_RUN_PROFILE` records each root's checkpoints at 128–2048 simulations.
- Seeds 111370000–111370017, both arms, run in the value-head plan thread's container; smokes 111370018 (A) and
  111370019 (M) are not analysed. All 38 games rc 0, banners as required (M shows `leaf_calibration=`, neither
  arm a learned stop or a fast-root cap).
- [`analyze_stop.py`](analyze_stop.py) uses `tools/ooc_learned_stop.py`'s loader, features and label (is the
  checkpoint's visit leader the full search's choice). Its Python predictor reproduces `one_combat
  ooclearnedstoptest` on 1,470 training checkpoints (max error 2.7e-10).
- It scores the deployed model in two ways:
  - **model level:** predicted P(same) against the observed rate;
  - **rule level:** the deployed fast-root rule. It stops at the first checkpoint of 128/256/512 with p ≥ 0.99 and
    plays its leader, else it plays the leader at 1024.
- Intervals: seed bootstrap.
- Output: [`result.json`](result.json).

**Result** (18 seeds per arm):

| | A: X2-B leaf | M: M0 leaf |
|---|---|---|
| searched roots / checkpoint rows | 1,269 / 6,345 | 1,143 / 5,715 |
| checkpoints with p ≥ 0.99 | 3,409 | 3,364 |
| their precision (leader = full search's choice) | 99.62% [99.12, 99.94] | 99.76% [99.56, 99.94] |
| mean p vs observed rate, all checkpoints | 0.936 vs 0.927 | 0.947 vs 0.945 |
| fast-root rule: roots stopped | 54.0% [50.7, 57.3] | 59.2% [56.3, 62.6] |
| fast-root rule: mean simulations (cap 1024) | 577 | 525 |
| stops whose pick differs from the 1024 leader | 0 of 685 | 0 of 677 |
| 1024 leader = full 4096 search's choice | 94.0% | 94.9% |

- By act, the rule stops at 61 / 56 / 44 / 17% of roots under A and at 65 / 61 / 48 / 31% under M. Precision at
  p ≥ 0.99 is 99.5–100% in every act and arm.
- Under M the model is calibrated overall (0.947 vs 0.945). Under A it is slightly over-confident (0.936 vs 0.927).

**Interpretation.**
- The stop stays as precise on M0's scale as on X2-B's. It fires more often under M0 because M0's searches settle
  earlier, not because the model misreads the new Q gaps.
- When it fires, it never changed a fast root's pick in either arm.
- Same-action proxy only, not a win rate. The A/B already measured M0 with this stop on.

**Decision.** PREREG's stop check for an M0 default passes. The other condition, a confirmation A/B on fresh seeds,
needs Philipp's go. (2026-10-23 14:11Z: Philipp made M0 the A20 default without it,
[ADR-0057](../../../../decisions/0057-ooc-leaf-calibration-a20-default.md).)
