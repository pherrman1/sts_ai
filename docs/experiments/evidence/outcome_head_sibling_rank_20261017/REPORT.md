# §502 — §498 outcome head as a sibling-leaf ranker (offline)

**HEAD_RANKS_WORSE_THAN_X2B.** On the 777 §494 TRAIN+VALIDATION sibling groups the
frozen §498 head orders sibling leaves worse than the public X2-B and worse than one
scheduled rollout3, measured against 64-rollout means. Zero new game seeds, no fits.
The §494 TEST (16 sources) and the consumed §499 TEST were not read.

## What was measured

- Candidate: §498 selected head `head.json` (`2c478bca…`) on the frozen Arm C student
  (`studentc.bin` `eff2f74f…`), its pooled value-head input exported by
  `one_combat heart1score` (this change). Probability = sigmoid(head(pooled)).
- Groups: §494 native capture `corpus-train-validation.tar` (`03d29264…`, manifest
  match), seeds 110164000–047, every accepted Arm C sibling with 64 rollout3 repeats.
  21,291 leaves, 777 multi-action groups (TRAIN 663, VALIDATION 114, as in §494).
- Metrics: §494's own group metrics (per-source mean of pairwise concordance and
  regret against the 64-rollout mean, then mean over sources); paired source
  bootstrap, 2,000 resamples, RNG 20261017.

## Native parity first

The C++ student forward plus the head reproduces §498's per-source mean validation
probability on all 8 VALIDATION sources of delivery `w00` (1,219 states,
`validation.tar.gz` `006958a4…`, transport SHA256SUMS match): max |diff| 3.9e-9
([parity.json](parity.json)). The result below is not an encoding mismatch.
Choice-less public records (the §497 corpus has some) now return a value instead of
throwing; every runtime caller already skips them before `forward`.

## Result

| TRAIN+VALIDATION, 777 groups | Concordance | Regret |
| --- | ---: | ---: |
| §498 outcome head | 0.527 | 0.0374 |
| X2-B (public) | 0.601 | 0.0278 |
| One scheduled rollout3 | 0.565 | 0.0305 |
| Arm C student's own (untrained) value head | 0.516 | 0.0375 |

Head − X2-B: concordance −0.074 [−0.097, −0.048], regret +0.0096 [+0.0057, +0.0140].
Head − one rollout3: concordance −0.038 [−0.068, −0.007]. Same sign on TRAIN and on
VALIDATION alone ([siblings.json](siblings.json)).

By act, head vs X2-B concordance: act 1 0.504 vs 0.622 (333 groups), act 2 0.529 vs
0.590, act 3 0.569 vs 0.573, act 4 0.624 vs 0.622 (20 groups). By parent screen: card
rewards 0.506 vs 0.584 (317), events 0.452 vs 0.738 (103), map 0.618 vs 0.524 (189;
one rollout3 0.642). Row-level Pearson with the target: head 0.41, X2-B 0.65.

## Addendum: §501 development heads

The four §501 heads (branch `claude/project-thread-q185p8` at `a30643d`, `heads/*.json`,
SHA256SUMS match) were scored the same way. Native parity first: each head's mean
prediction on the first state of all 360 VALIDATION runs matches its §501 start-landmark
mean to ≤3.7e-9 ([start-parity-501-heads.json](start-parity-501-heads.json)), which also
checks the copied public block.

| 777 groups | Concordance | Regret | − X2-B concordance, 95% |
| --- | ---: | ---: | --- |
| §498 head | 0.527 | 0.0374 | [−0.097, −0.048] |
| §501 equal | 0.507 | 0.0393 | [−0.122, −0.063] |
| §501 early | 0.520 | 0.0378 | [−0.112, −0.048] |
| §501 pooled + public | 0.521 | 0.0366 | [−0.105, −0.053] |
| §501 public only | 0.530 | 0.0315 | [−0.099, −0.040] |
| X2-B | 0.601 | 0.0278 | |
| One rollout3 | 0.565 | 0.0305 | |

The pooled+public arm's better VALIDATION BCE (0.4298 vs 0.4534) does not carry over to
sibling ordering; no outcome head comes within 0.04 of X2-B. Full splits and strata:
[siblings-501-heads.json](siblings-501-heads.json).

## Limits

- Targets are means of Arm C rollout3 values, which end in an X2-B evaluation at the
  rollout horizon; they share X2-B's scale and errors and are not observed Heart
  outcomes. They favour X2-B. Still, the head is near chance on act-1 and card-reward
  siblings, where §498/§499 already showed weak early ranking (act-1 AUROC 0.58).
- Labels are rollout surrogates; this does not test gameplay. The head is the
  immutable §498 candidate plus the four §501 heads (addendum); §500 heads are not covered.
- Ranking siblings by observed Heart outcome directly is not affordable: at a 12%
  win rate, separating two siblings by 2 pp needs several hundred full runs each.

**Inference:** a 64-d head on a frozen policy representation, fitted to 1,080 binary
run outcomes, does not resolve one-step sibling differences. Better marginal
calibration would not change this.

## Reproduce

`python3 tools/outcome_head_sibling_check.py parity|siblings <one_combat> <studentc.bin> <dir> <work> [head.json …]`.
Binary built at this branch (Release, GCC 13, `a32bbe72…`, Intel Xeon @ 2.10GHz);
`heart1score` scored 21,291 records in 32.4 s single-threaded including JSON I/O
(≈1.5 ms per leaf, an upper bound on native leaf cost; no in-search timing).

**Knowledge impact:** current research status of observed-outcome leaf candidates;
native public-record parity for the §498 head. No default change.
