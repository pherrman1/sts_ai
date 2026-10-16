# §501 — development value-head comparison on the frozen Arm C cache

Pre-registered before any fit. Workstream 1 of the 2026-10-17 plan ("improve the
value model cheaply"). Development evidence only: reused §497 TRAIN/VALIDATION,
no TEST artifact (the §499 TEST is consumed), no encoder forward, no gameplay
seeds, no native integration, no trunk/policy update, no default change.

## Questions

1. **Early weighting.** Does explicitly upweighting act-1 states reduce the
   early-landmark mean bias that §500's equal-state fit left at floor 16, without
   giving up aggregate fit?
2. **Representation information.** Does the frozen Arm C pooled representation
   lose value-relevant public information that a plain scalar/count block
   carries? (Encoder audit below explains why this is a live hypothesis.)
3. **Data.** Does VALIDATION loss still fall with more independent TRAIN sources
   (source-level learning curve), i.e. is the limit data rather than the head?

Alternatives kept open: too few wins (126 TRAIN), checkpoint-selection noise on
reused VALIDATION, and the fixed collector's trajectory distribution.

## Encoder audit (what the frozen representation can see)

Arm C is student C (`student-c-68fe88be.pt`, SHA `53739a43…e020`), silverbot
`network.NN` at daniel-ziegler/sts_lightspeed `84ab3ea`, dim 64, 2 layers,
4 heads. Our native port `apps/one_combat/heart1_policy.cpp` is a parity-tested
port of that commit, so it is read here as the encoder's specification
(`encodeObservation`, `Net::forwardRecord`).

Consumed per state: one token per deck card (id + upgrade), relic (id), potion
slot (id, empty slots included), one fixed-observation token (HP, max HP, gold,
floor, toSelectCount as Fourier scalars; boss, ascension, the three keys and
screen as embeddings), map nodes at or above the current row (room, position,
paths, reachability/aggregates, burning elite), and the offered choices. Keys
are therefore already encoded, as Codex noted.

Not consumed: relic counters (`obs.relics.relic_counters` is recorded but
unused), act (only implied by floor and boss), the public battle encounter and
memory-game slots (§498 already lists these), and any run history.

The value representation cached in §498 is the **mean over all tokens** of the
RMS-normalised final states (`heart1_policy.cpp`, end of `forwardRecord`).
Mean pooling cannot represent set sizes directly (deck size, relic count,
potions held), and the single fixed-observation token carrying HP and gold is
one of dozens of averaged tokens (deck, relics, potion slots, map rows, choices). The policy logits read per-choice tokens,
not this mean, and student C was trained by policy distillation only, so the
pooled vector was never trained to keep value information. **Inference:** a
loss of HP/count information through pooling is plausible; arm C tests it.

## Data and fixed inputs

Same as §500: §498 v2 pooled cache `a066eb69…2a25`, TRAIN 1,080 sources
110180000–110181079 (171,442 states, 126 wins), VALIDATION 360 sources
110181080–110181439 (56,704 states, 47 wins), §498 TRAIN normalisation for the
pooled features, §497 import custody. Arms C/D additionally read the public
record of each development state from the audited TRAIN/VALIDATION archives
(`heart_outcome_value.read_sources`, which refuses any other split), in cache
order, with (seed, index, label, act) bound row by row. SEALED/TEST archives are
hashed by the existing custody check and never opened.

Public block (37 values, `PUBLIC_NAMES` in the tool): HP/100, max HP/100, HP
fraction, gold/500, floor/55, three keys, boss one-hot (10), act one-hot (4),
screen one-hot (10), deck size/30, upgraded cards/10, relics/20, potions held/3,
potion slots/3. Standardised with TRAIN equal-state moments only. No labels,
seeds, RNG, trajectory index or future fields.

## Arms (all fixed now)

Common to every fit: head d → 64 ReLU → 1 with standardisation buffers, output
bias logit(126/1080), AdamW lr 0.001 / weight decay 0.001, minibatch 512 drawn
with replacement from the arm's float64 CPU weights (generator seeded by init),
2,000 updates, VALIDATION visitation BCE every 100 updates, inits 0 and 1,
selection = minimum VALIDATION visitation BCE, then earlier step, then init 0
(§500's rule). CUDA float32, TF32 off, deterministic, 2 CPU threads.

| Arm | Input | TRAIN weight per state |
| --- | --- | --- |
| A `equal` | pooled 64 | equal (exactly §500's visitation arm) |
| B `early` | pooled 64 | equal × 2 for act-1 states, renormalised |
| C `pooled_plus_public` | pooled 64 + public 37 | equal |
| D `public_only` | public 37 | equal |
| Curve | pooled 64 | equal over TRAIN sources in a nested subset |

Learning curve: TRAIN source subsets of 135, 270 and 540 sources, nested within
each of two fixed draws (`numpy.random.default_rng(601+draw).permutation`,
draws 0/1), two inits each; the 1,080-source point is arm A. Normalisation stays
§498's full-TRAIN buffers (feature moments only, no labels). VALIDATION is the
full 360 sources throughout.

Arm A must reproduce §500's selected treatment BCE 0.453411; the result reports
the absolute difference. It is a custody check, not a gate.

Total 14 fits × 2,000 updates. All RNGs are training/statistical, not game seeds.

## Measurements and decision rules

Per arm: TRAIN/VALIDATION visitation and source-balanced BCE, Brier, AUROC,
10-bin calibration; the three §500 landmarks (index 0, first act-1 floor ≥ 8,
first act-1 floor ≥ 16) with counts, scores, mean bias and 10,000-resample
source bootstrap (`heart_outcome_weighting.diagnostics`). Paired VALIDATION
B/C/D − A BCE and Brier deltas with the 10,000-resample source-cluster ratio
bootstrap (`heart_outcome_weighting.compare`, RNG 500).

- **Representation:** `REPRESENTATION_LOSS_SIGNAL` iff C − A visitation BCE has
  point ≤ −0.003 and descriptive 95% upper bound < 0. Otherwise
  `REPRESENTATION_LOSS_NOT_SHOWN`. D is a reference only.
- **Early weighting:** `EARLY_WEIGHTING_SIGNAL` iff all three landmark absolute
  mean biases of B are strictly smaller than A's and B's VALIDATION visitation
  BCE ≤ A's + 0.002. Otherwise `EARLY_WEIGHTING_NOT_SHOWN`.
- **Sources:** `MORE_SOURCES_SIGNAL` iff the mean selected VALIDATION
  visitation BCE of the two 540-source draws exceeds arm A's by ≥ 0.002.
  Otherwise `MORE_SOURCES_NOT_SHOWN`. Descriptive: two draws, reused VALIDATION.

Interpretation fixed now: a representation signal argues for an explicit
scalar/count channel (or later trunk fine-tuning, which can also move the
policy) before more data; a sources signal without it argues that workstream 3's
collection is the main lever; neither signal leaves the head limited by targets
or selection noise at this size. All intervals are descriptive, pointwise, not
adjusted for checkpoint selection or reused VALIDATION. Any candidate needs the
fresh sealed confirmation cohort from workstream 3; none of this qualifies a
search leaf (workstream 2).

## Execution and custody

Runs on Philipp's machine (cache, checkpoint, silverbot `84ab3ea` and GPU are
there) from a clean checkout of the commit carrying this protocol, with
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, under `timeout --signal=TERM
--kill-after=10s 1200s`, into a fresh output root (`exist_ok=False`, no resume,
no retry without a recorded failure). Internal 900 s cap covers archive reading
and fits. `started.json` records identity/custody before any fit; inputs are
re-hashed after. Raw checkpoints/predictions stay in the ignored build root;
compact `result.json` and the report go to this directory.
