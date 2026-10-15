# E3 pre-registration: first counterfactual tranche (draft, 2026-10-07)

## Frozen provenance

- Code: commit 8edf724c (PR #434, independently reviewed). Each thread
  self-builds the `one_combat` release target and records its sha256. Release
  builds are bit-reproducible across cloud containers.
- Teacher: `make_teacher.py` (learned-stop V4 teacher), as in the timing run.
- Command: `run_corpus.sh BIN SHA 8edf724c OUT START 5 4 2 2 1 2 CARD_REWARD,BOSS_RELIC`.
  - Each chunk is 4 parts × 5 seeds, one part per core.
  - Chunks run one after another, each into its own OUT directory.
  - Small parts limit the damage of a Silver stall, since there is no
    per-branch timeout.
- Design: K=2 futures, 2 states per seed (one card reward and one boss relic
  where both exist), GEN=2 (whole run, `finalWon`).
- Seeds: 55000000 to 55000999, which is 1,000 seeds and about 2,000 states.
  - Thread i plays 55000000 + 250·i to + 249.
  - At about 126 CPU-s per state, that is about 70 CPU-hours in total.

## Data rules (fixed before looking)

1. `nextEliteId` and `nextFight0/1/2` are masked to -1 in `.map.csv` and
   `.options.csv` for the primary arm. They encode the redrawn fights the
   label was played under (`semantic_pilot.cpp:94`).
2. If any sibling run is invalid, the whole (state, k) group is dropped.
3. A stalled seed is skipped and listed in STALLED.txt. It is not regenerated
   with other seeds.
4. The split is by source seed: TRAIN 70%, VALIDATION 15%, TEST 15%, by
   sha256 of the seed. TEST stays closed until one final model is chosen.

## Models

- **P0:** X2-B as is, with the four fields masked in the inputs.
- **F2:** the same XGBoost family and hyperparameters as X2-B. Trained on
  #334 TRAIN rows (all rows, with focal rows upweighted as in #432) plus E3
  TRAIN map rows. Four fields masked. Uncentered `finalWon` target.
- **F2-E3only:** the E3 TRAIN map rows only. This is a diagnostic.

## Primary metric (VALIDATION, then TEST once)

- **Selection gain per state:** the mean `finalWon` of the model's argmax
  option minus that of V4's option. Each state is weighted equally, averaged
  over k, and reported per type with a 95% bootstrap CI clustered by source
  seed.
- **Secondary:**
  - NLL and Brier on map rows.
  - Agreement with V4.
  - The rate at which skip is chosen at card rewards.
  - A learning curve at 25/50/100% of E3 TRAIN.
- **Expected signal (timing run):** siblings differ in outcome in 9 of 24
  card-reward futures and in 16 of 24 boss-relic futures.

## Decision rule

1. **Positive:** F2 card-reward selection gain is above 0 with the CI excluding
   0, and NLL is no worse than P0 + 0.005. Then E4, a one-ply online A/B.
2. **Learning curve still rising and CI crossing 0:** propose a second tranche
   of the same size.
3. **Otherwise, negative:** record it in the ledger and stop scaling.
