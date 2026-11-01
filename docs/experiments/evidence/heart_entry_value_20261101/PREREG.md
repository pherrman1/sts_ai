# All-feature Heart-entry value from paired perturbation labels (stage B): pre-registration

Status: written before any model was fit on the real labels. The only run before freezing is a debug run of
`fit_value.py --permute` (labels shuffled within each base, so no within-base state signal); its numbers are not
reported.

## Question
Philipp (2026-10-31): a value model that sees cross-fight interactions in general, instead of one rule per relic like
the Incense term (§724). Stage A (§731) produced 16,000 Heart fights on 1,000 Heart-entry states: per state a control,
a reseed and 14 single changes, all changes on the control's battle seed. Stage B: does a value on every state field
predict the causal effect of a change on the Heart kill better than the structure of Silver's Shield & Spear win leaf?

## Data
§731's `results/labels.csv` and the variant states `v0..v15.jsonl` from `variants.tar` (share
`/mnt/project-files/heart-entry-perturb`, sha256 ac30cf81…). Offline, no fights, no seeds.

## Features (`fit_value.py`, `Feat`)
Every field act4replay carries: HP, max HP, HP fraction, potion count, capacity, empty slots, count of each potion
type, each relic held, the counter of each counter relic (Incense Burner, Nunchaku, Ink Bottle, Pen Nib, Happy Flower,
Sundial, Lizard Tail, Omamori, Girya; −1 when not held), count of each card and of its upgraded copies, deck size,
upgrade count, Searing Blow upgrade count, and the Silver leaf value L below. Vocabulary from all states (labels not
used).

## Models
- **A** (all-feature): XGBoost logistic, monotone increasing in HP, max HP, HP fraction, potion count, each potion
  type and L. Grid depth {2, 3, 4, 6} × min child weight {5, 20}, eta 0.03, early stopping, chosen by 4-fold CV
  grouped by source seed inside each outer training set.
- **LI** (leaf inputs): the same GBM on HP, max HP, HP fraction, potions (count, capacity, empty slots, each type),
  Lizard Tail and its counter, Mark of the Bloom, Sacred Bark.
- **L** (Silver's S&S win leaf at A20 defaults, `SilverSearcher::evaluateEndState`): L = HP + 2 × max HP + 11 ×
  potions + 0.3 × max HP if a Fairy is held (0.6 with Sacred Bark) + 0.5 × max HP with an unused Lizard Tail (counter 1; the engine gives a spent tail no death save) (no death saves with
  Mark of the Bloom); turn penalty, gold and post-battle healing are the same within a pair and left out. Mapped to a
  kill probability by a logistic fit on the training bases.

## Cross-fitting
5 outer folds by source seed (seed mod 5; all bases of a source seed in one fold). Each fight's prediction comes from
models fit without its source seed.

## Primary
Pairs: every base and change k = 2..15 (14,000). D = won(k) − won(control); D̂_M = p_M(state k) − p_M(control).
Primary statistic: mean of (D − D̂_A)² − (D − D̂_L)², 95% CI by bootstrap over source seeds (10,000, seed 20261101).
- **PASS**: CI upper < 0 (A predicts change effects better than the leaf's structure).
- **WORSE**: CI lower > 0. **NOT_SHOWN**: otherwise.

## Co-reported
A − LI and LI − L on the same statistic (does the gain come from features outside the leaf's inputs, or from
reweighting HP and potions?); each model's squared error against predicting no effect (skill); correlation of D̂ with D;
out-of-fold BCE on all fights, A − L per base; per operator the mean observed D and each model's mean D̂; Incense counter
changes: A's D̂ against §723's table (slope, correlation).

## Decision
- PASS → pre-register stage C: A, refit on all 1,000 bases with the same grid, as Silver's S&S win leaf (in place of
  L, scaled to HP via L's fitted slope) in §724's paired S&S → Heart chain; primary Heart kill on − off. Runs need
  Philipp's go.
- NOT_SHOWN or WORSE → no stage C now; the next step (more labels, observational records with a search indicator, or
  a different model) goes to Philipp.

## Caveats
- Labels come from the research Heart search (learned stop ≤ 10k, Act 4 strong off), as §723/§724.
- Changes are single and drawn from Heart-entry frequencies, so card and relic gains are small and rare per type; the
  model can only learn the interactions these changes cover.
- D is noisy (one change flips the outcome in 13.6% of pairs, §731), so the primary difference is small in absolute
  terms even when one model is clearly better.
