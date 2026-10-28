# SR head on swkeyed sibling labels: NOT_SHOWN (2026-10-28)

The plan is in [PLAN.md](PLAN.md), including its two deviations, and the smoke is in [SMOKE.md](SMOKE.md). The
evaluation tool is [tools/swk_eval.py](tools/swk_eval.py).

## Capture
- **Run:** RUN_COMMIT `27c85529` on `claude/project-thread-tt1jc5-run`, code `d4a4ec3c`, binary `382997c2…`.
  - 16 cloud workers, 2026-10-28 15:3x–18:3xZ, 155.8 core-h in total.
  - [results/verify.txt](results/verify.txt): 320/320 units OK, rc 0, 0 bad rows, and 578,987 capture rows (the
    same as §644).
- **Exactness** ([results/compare.json](results/compare.json)):
  - All policy and CTM rows, and every capture row outside `extra.repeats`, match §644 in all 320 sources (0
    mismatches).
  - Every row carries 32 swkeyed repeats, and none were lost.
- **Bias against §644's labels on the same rows:**
  - The pooled mean difference is −0.00018 ± 0.00028 (root-clustered).
  - 8.6 % of rows have |z| > 2: 6.9 % negative and 1.8 % positive. The rule's limit is 8 %, so this is a flag.
  - It is a selection artefact. Rows whose own §644 draws had no death come out low (−0.0115); rows with 3 or
    more come out high (+0.011).
  - Philipp chose to proceed (Deviation 1).
- **Label noise** ([results/noise_by_screen.json](results/noise_by_screen.json)):

  | split | split-half agreement, 16 vs 16 repeats (§644 → swkeyed) | sibling-difference variance per repeat |
  |---|---|---|
  | VALIDATION | 0.718 → 0.829 | 0.160× |
  | TRAIN | 0.718 → 0.829 | 0.153× |

  - By screen (VALIDATION): rewards 0.081×, events 0.120×, card select 0.121×, shop 0.157×, rest 0.220×, map 0.306×,
    boss relic 0.407×.
- **Groups:** `crn_groups.py` keeps all 15,129 TRAIN groups. They are identical to §644's apart from `target`
  (154,010 of 155,368 targets change).
  - Data branch `claude/az-gen2-data` `gen2/value-sr-swk/` (`975e4e5f`; groups sha256 `4541dc8a…`).

## Training
- **Where and how:** Philipp's GPU, §649's SR_crn_r2 command with seeds 1 and 2, 20 epochs, `pick_epoch.py`.
  - The two seeds ran side by side after 21:21 CET (Philipp's OK). The result does not depend on that (§649 plan).
- **Provenance:** distill.py `40a9d5a3…`, monotone.py `09efffaf…` and heart1 `deaba59d…` match §649. torch 2.5.1+cu121
  is unchanged since August, so the §649 controls are reused (PLAN).
- **Weights:** data branch `26f18e23` ([results/weights.sha256](results/weights.sha256)).

| head | picked epoch | in-training holdout (own labels) | selection-fold BCE |
|---|---|---|---|
| SR_crn_r2_s1 (control) | 13 | 0.6665 | 0.565 |
| SR_crn_r2_s2 (control) | 20 | 0.6687 | 0.562 |
| SR_swk_r2_s1 | 18 | 0.6812 | 0.568 |
| SR_swk_r2_s2 | 11 | 0.6719 | 0.559 |

The in-training holdout scores each run against its own labels, so it does not compare across arms.

## Evaluation: head alone on the common-seed VALIDATION with §644's labels (primary)
[results/primary.txt](results/primary.txt). 80 sources and 5,587 groups. X2-B scores 0.6639. The controls reproduce
§649 exactly (0.6628 and 0.6668).

| | head alone | small gaps (< 1.5 pp) | X2-B blend (w from the TRAIN holdout) |
|---|---|---|---|
| control s1 / treatment s1 | 0.6628 / **0.6734** | 0.5929 / 0.5988 | 0.7020 / 0.7050 (w 0.15) |
| control s2 / treatment s2 | 0.6668 / **0.6661** | 0.5955 / 0.5948 | 0.7031 / 0.7025 |
| seed 1, treatment − control | **+0.0106 [+0.0054, +0.0158]** | +0.0059 [+0.0004, +0.0116] | +0.0030 [−0.0025, +0.0080] |
| seed 2, treatment − control | **−0.0007 [−0.0049, +0.0033]** | −0.0007 [−0.0058, +0.0045] | −0.0006 [−0.0047, +0.0033] |
| seed mean | **+0.0050 [+0.0014, +0.0084]** | +0.0026 [−0.0016, +0.0068] | +0.0012 [−0.0029, +0.0048] |

**Bars:**
- Selection BCE ≤ 0.570 holds for both seeds (0.568 and 0.559).
- −3 HP proxy (Deviation 2): control s1 84.1 % vs treatment s1 82.9 % (−1.2 pp); control s2 83.7 % vs treatment s2
  81.7 % (−1.9 pp). Both are within the 2 pp limit, s2 just barely.

## Verdict (pre-registered gate): NOT_SHOWN
- The seed-mean CI is above 0 (+0.0050 [+0.0014, +0.0084]).
- But seed 2's difference is not positive (−0.0007). The pre-launch review added that per-seed condition because the
  source bootstrap leaves out training-seed noise.

## Secondary: the same heads on the swkeyed VALIDATION labels
[results/secondary.txt](results/secondary.txt). The cleaner targets raise every evaluator's concordance (X2-B 0.6669;
heads 0.70–0.71). The arms compare the same way as in the primary:
- **Seed 1:** +0.0107 [+0.0053, +0.0159]; blend +0.0091 [+0.0038, +0.0142].
- **Seed 2:** +0.0003 [−0.0042, +0.0048]; blend −0.0010 [−0.0062, +0.0037].
- **Seed mean:** +0.0055 [+0.0017, +0.0093]; small gaps +0.0081 [+0.0039, +0.0125]; blend +0.0041 [+0.0008, +0.0072].

## Reading
- swkeyed labels are much cleaner: 0.16× the per-repeat sibling-difference variance, and split-half agreement
  0.718 → 0.829. Their mean matches §644's labels.
- Training on them does not reliably improve the head.
  - Seed 1 gains +0.011, about one seed spread of §649. Seed 2 is level.
  - The two seeds also differ in the picked epoch (18 vs 11) against the controls' 13 and 20, so part of seed 1's
    gain may come from the later epoch, not from the labels.
- **Inference:** this agrees with §645 (cleaner CRN labels: flat) and §700 (twice the data: flat). Label noise is not
  what limits this head. The levers left are the objective and recipe (the ranking-vs-value-loss thread), the
  features, and labels that do not end in X2-B.
- The −3 HP proxy falls slightly in both treatment seeds (1–2 pp). That is consistent with more weight on ranking at
  the expense of value shape, but it is not significant at this size.
- No default change. The swkeyed capture and groups stay on the share and the data branch for later recipes.

Seeds: none new; the 320 §644 sources (111144512–111144831) were replayed.
