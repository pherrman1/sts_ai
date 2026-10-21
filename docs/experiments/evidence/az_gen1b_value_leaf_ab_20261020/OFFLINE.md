# Gen-1b value head as an OOC leaf value: offline numbers (ledger §577)

**Gen 1b's value head ranks sibling leaves better than student_sel's untrained head but clearly worse than X2-B
and than one rollout3. It predicts the run's Heart kill slightly better than X2-B (AUC +0.016, CI includes 0), except in
Act 1.** Zero new game seeds, no fits. Philipp, 2026-10-20 20:34Z, asked for offline numbers first.

## Data (all unseen by gen 1b)
Gen 1b trained on gen-0 seeds 111140712–142375 (§569/§573). Both sets below come from earlier campaigns with other
policies (Arm C / the §497 teacher at 512 sims), so they are out of distribution for gen 1b's training states.
- **§494 sibling groups:** `corpus-train-validation.tar` (`03d29264…`), sources 110164000–047, 21,291 leaves, 777
  multi-action groups, 64 rollout3 repeats per leaf. Same set as §502 (TEST not read).
- **§503 round 2:** TRAIN + VALIDATION deliveries of all 32 workers on the share
  (`/mnt/project-files/heart-outcome-round2/deliveries/wWW/{train,validation}.tar.gz`), 1,408 complete sources,
  330,386 sibling leaves at depth 1 with 64 rollout3 repeats, 11,493 multi-action groups, and each source's observed
  Heart kill (base rate over leaves 0.182). CONFIRM stays sealed (it was spent by §515 anyway; not opened here).

Encoding: the capture records are `heart1-public-record-v2`; the leaf row's act is inserted as `obs.act`, as the native
encoder does. They lack `obs.deck.misc` (Ritual Dagger, Genetic Algorithm: 0 here) and carry Wing Boots' relic data,
not the #638 charges. Value = sigmoid(value logit) from `one_combat heart1score` (binary `193b0000…`, the frozen gen-1b
A/B binary). Weights: gen1b.bin `e6aa044c…`, student_sel.bin `cf6bf7fb…`.

## Sibling ranking (§494 group metrics; target = mean of 64 rollout3; source bootstrap 2,000, RNG 20261017)

| | §494, 777 groups: concordance / regret | Round 2, 11,493 groups: concordance / regret |
| --- | ---: | ---: |
| gen 1b value | 0.541 / 0.0330 | 0.547 / 0.0319 |
| student_sel value (untrained) | 0.514 / 0.0395 | 0.521 / 0.0375 |
| X2-B | 0.601 / 0.0278 | 0.633 / 0.0223 |
| one rollout3 | 0.565 / 0.0305 | 0.590 / 0.0308 |
| (§498 outcome head, §502) | 0.527 / 0.0374 | |

- gen 1b − X2-B concordance: §494 −0.060 [−0.091, −0.029]; round 2 −0.086 [−0.093, −0.077]. Regret +0.005
  [−0.000, +0.011] and +0.010 [+0.008, +0.011].
- gen 1b − one rollout3 concordance: −0.025 [−0.060, +0.011]; round 2 −0.043 [−0.051, −0.034]. Regret about equal
  (+0.002, +0.001).
- By parent screen (round 2): map 0.602 vs X2-B 0.573 (2,279 groups; §494 0.629 vs 0.524) is the only screen where gen
  1b leads. Events 0.504 vs 0.761, card rewards 0.534 vs 0.594, shops 0.555 vs 0.595, rest 0.553 vs 0.638.
- By act (round 2): act 1 0.530 vs 0.659, act 2 0.575 vs 0.625, act 3 0.557 vs 0.582, act 4 0.553 vs 0.545.
- Row-level Pearson with the target: gen 1b 0.47, X2-B 0.58, one rollout3 0.65.

## Observed outcome (round 2 leaves vs the source's Heart kill; source bootstrap)

| | AUC | BCE | mean value |
| --- | ---: | ---: | ---: |
| gen 1b value | 0.710 | 0.471 | 0.302 |
| X2-B | 0.694 | 1.436 | 0.789 |
| 64-rollout3 mean | 0.706 | 1.171 | 0.708 |
| one rollout3 | 0.679 | 1.607 | 0.708 |
| student_sel value | 0.408 | 0.685 | 0.493 |
| constant | | 0.475 | 0.182 |

gen 1b − X2-B AUC +0.016 [−0.003, +0.036]. By act (gen 1b / X2-B): act 1 0.575 / 0.582, act 2 0.742 / 0.710, act 3
0.740 / 0.727, act 4 0.725 / 0.726. X2-B is a win estimate, not a Heart probability, so its BCE is not comparable. Gen
1b over-predicts here (0.30 vs 0.18), and its BCE barely beats the constant: round 2's teacher killed the Heart about
half as often as gen 0's search (§503 13.6% vs §569 25.8%), so the level is policy-dependent.

## Reading (Inference)
- The value head learned what separates winning from losing runs (AUC at X2-B's level, better in acts 2–3), but it does
  not separate one-step alternatives at the same decision, except on the map. This matches §502: heads trained on
  run outcomes, where all states of a run share one label, rank siblings poorly.
- The sibling targets end in X2-B and favour it; the outcome target is the run label gen 1b was trained on and favours
  gen 1b. Neither is ground truth for the online question.
- In the planned online arm the head values rollout3 end states (MAP screens three fights later), not the leaves
  scored here. Sibling order then comes mostly from the rollouts, so the head's weak sibling ranking matters less than
  its state ranking, and the Act-1 weakness and the scale change (mean 0.30 vs 0.79) matter more. §522 (a P(Heart)
  rollout3 end value, NOT_SHOWN with 114 vs 69 act-1 deaths) is the closest precedent.

## Reproduce
`python3 tools/heart1/value_leaf_check.py check <one_combat> offline.json <work> <§494 extracted> <round-2 extracted>
gen1b=gen1b.bin student_sel=student_sel.bin` (≈25 min on one core, mostly `heart1score`). §494 extraction: untar
`corpus-train-validation.tar`, then each `sources/*.tar.gz`. Round 2: untar `*.sib.jsonl` and `*.states.jsonl` from every
delivery's train and validation archives into `train/` and `validation/`.
[offline.json](offline.json).
