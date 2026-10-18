# Pre-registration: an Act-4 survival model for the A20 CTM (offline gate)

Written 2026-10-18 before any model is fitted and before any TEST row is scored by a candidate. Requested by Philipp
(2026-10-17 23:49Z, "Retrain" on the card "Act-4-CTM mit den 5,467 Act-4-Labels neu trainieren?"), following finding 1
of the CTM audit at A20 (`/mnt/project-files/audit-2026-10-17/ctm-a20.md`). Ledger entry §TBD (§527 reserved).

## Problem
The deployed A20 CTM (calibrated `pathb-a20`, ADR-0033, §470) never saw an Act-4 row. On the TRAIN+VALIDATION rows of
the corpus below it predicts Heart death 0.175 where the teacher dies 0.682 (NLL 1.61 against 0.63 for a constant),
and 0.03 at ≥ 90% HP where the teacher dies 0.42. Shield and Spear: predicted 0.086, observed 0.124. Its win-HP bias
there is small (+1.0 HP on Shield and Spear). These numbers were looked at before this file was written; TEST was not.

## Corpus
- The Act-4 label collection of 2026-10-17 (`/mnt/project-files/ctm-a20/act4-labels/`, FROZEN.txt there: RUN_COMMIT
  `bcf14d34`, `one_combat` `9fd50586…`, A20, learned-stop Silver 10k teacher, student C out of combat, `act4_fork`).
- The eight tars `w01..w08.tar.gz`, each matching the `tar_sha256` in its DONE file; every `out/act4-*.jsonl` outside
  the `aborted-*` directories (400 files). Concatenated in sorted path order: 5,467 rows, sha256 `c095368c…` (the same
  file the gen-7 prior used). 2,913 Shield and Spear rows (encounter 56, death 12.3%) and 2,554 Heart rows (57, death
  68.2%), all `runValid`, no quarantine, no duplicate (seed, encounter).
- Split: the CTM source-seed hash (`SHA256("combat-transition-model-v1:"+seed)`, first 8 bytes big-endian mod 100;
  <80 TRAIN, <90 VALIDATION, else TEST). TRAIN 4,370 (2,329 / 2,041), VALIDATION 537 (286 / 251), TEST 560
  (298 / 262). Both fights of one seed share a split.

## Incumbent
`one_combat ctmscorerows ROWS OUT selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
selfplay/models/combat_transition_near_full_escape_pathb_a20.native 1` at main `2a8420cc`: the deployed calibrated A20
stack with active Lizard (its `p_death` column).

## Candidate (one, fixed here)
- Target: death (`combatOutcome == 2`) in the fight, for encounters SHIELD_AND_SPEAR and THE_HEART only.
- Model: XGBoost 3.4.1 `binary:logistic`, one model for both encounters, `tree_method=hist`, `eta=0.03`,
  `subsample=0.8`, `colsample_bytree=0.5`, `lambda=5`, `seed=527`, 4 threads, up to 3,000 rounds with early stopping
  (100 rounds) on VALIDATION logloss.
- Grid: `max_depth` in {2, 3, 4} × `min_child_weight` in {5, 20}. The cell with the lowest VALIDATION logloss (both
  encounters pooled) is the candidate, trained on TRAIN only, truncated at its best iteration.
- Features, all computed from the row's `predictorInput` (so the runtime can compute them from the same input):
  `heart` (encounter is THE_HEART), `cur_hp`, `max_hp`, `hp_frac` (float32 cur/max), `gold`, `potion_capacity`,
  `potion_count`, `deck_size`, `upgraded`, `card_<id>` (count of each card id), `relic_<id>` (0/1), `potion_<id>`
  (count of each potion id in the belt, empty slots excluded). Relic counters and card misc are not used.

## Criteria on TEST (all must pass), source-seed cluster bootstrap, 2,000 resamples, seed 527, 95% CIs
Computed separately for the Heart rows and the Shield and Spear rows:
1. Survival BCE (per-row NLL of the death outcome), candidate minus incumbent: upper CI < 0.
2. Death bias of the candidate (mean predicted minus observed death): |bias| ≤ 0.05.
3. AUC, candidate minus incumbent: lower CI > −0.03.

Reported, not gating: BCE against the TRAIN death rate per encounter and against an HP-only logistic regression
(`heart`, `cur_hp`, `max_hp`, `hp_frac`, per encounter, fit on TRAIN); death by HP-fraction bucket; and, if the
recorded entry states can be converted, the candidate on the 64 natural Heart entry states of the F1 act4replay audit
(`/mnt/project-files/audit-2026-10-17/f1-act4replay/heart64.jsonl`, 3 replays each at 10k) as a descriptive check of
the shift from `act4_fork` entrants to natural entrants.

## Decision
- TEST is opened once, for the selected candidate. No refit, other grid or feature set is tried on TEST afterwards; a
  FAIL or a partial pass is recorded as is.
- PASS: the model ships opt-in. `STS_CTM_ACT4_SURVIVAL_MODEL=<trees file>` replaces the CTM survival probability of
  SHIELD_AND_SPEAR and THE_HEART (every CTM runtime, so OOC MCTS leaves and `ctmscorerows` alike). The HP, potion and
  relic heads are unchanged. Unset keeps today's behavior. Native parity with the Python model (max |Δp| < 1e-5 on the
  TEST rows, through `ctmscorerows` with active Lizard off) is required before the PR leaves draft. Then an A20 A/B is
  proposed to Philipp; its size, seeds and worker count are his call. A default change is his call after that A/B.
