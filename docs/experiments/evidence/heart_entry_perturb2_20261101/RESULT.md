# Heart-entry perturbation labels, round 2: result

Pre-registration: [PREREG.md](PREREG.md) (prelaunch review PASS). Campaign `heart-entry-perturb2`, RUN_COMMIT
523b2491, code e55f4827, binary b8f0628b; 16 workers × 4 lanes, 2026-11-01 08:36Z – about 22:20Z (Philipp's go
07:20Z). `verify_campaign.py`: 3253/3253 units OK, 0 missing, 0 bad, 0 duplicates, 16/16 worker DONE files
([results/verify.txt](results/verify.txt)). Frozen `analyze.py`, output [results/analysis.json](results/analysis.json),
[results/labels.csv](results/labels.csv) and [results/labels_all.csv](results/labels_all.csv) (both rounds, 4,252
bases, 68,032 fights). CPU 752 CPU-h (estimate 640).

3,252 of 3,253 bases valid, 1,290 source seeds. One unit ended rc=93: its variant 3 (line 1244, global base 2244,
a Distilled Chaos → Fairy potion swap) aborted with "native Silver backend: stall: exceeded 1000 decisions" (battle
seed 111342268), so the whole base is excluded by the frozen rule.

## Pre-registered check
Sign checks: HP up/down, potion added/removed and max HP up **consistent**; card upgraded **unresolved**; none
INCONSISTENT → **labels usable**.

## Co-reported (round 2; §731 in brackets)
| | round 2 | §731 |
|---|---|---|
| control Heart kill | 64.7% [62.5, 67.0] | 65.4% |
| reseed − control kill | −1.8 pp [−3.3, −0.2] | −0.7 pp |
| outcome flips, reseed only | 21.0% | 20.3% |
| outcome flips, one change | 14.4% | 13.6% |
| mean effect over all changes | −1.3 pp [−2.2, −0.5] | −1.0 pp [−2.5, +0.5] |

Effect per operator, kill(variant) − kill(control), pp:

| operator | n | round 2 [95% CI] | §731 |
|---|---|---|---|
| potion removed | 2,681 | −8.1 [−10.0, −6.1] | −7.2 |
| HP down | 5,657 | −7.5 [−8.8, −6.2] | −7.1 |
| relic removed | 4,182 | −5.1 [−6.3, −3.9] | −5.0 |
| max HP down | 2,025 | −2.4 [−4.1, −0.7] | −1.7 |
| card removed | 4,188 | −2.0 [−3.8, −0.2] | +0.5 |
| relic counter changed | 3,436 | −1.7 [−3.4, +0.1] | −2.7 |
| potion swapped | 2,731 | −0.5 [−2.2, +1.2] | −0.3 |
| card upgraded | 4,136 | −0.4 [−1.7, +0.8] | +0.3 |
| card added | 4,239 | −0.2 [−2.0, +1.7] | +2.2 |
| relic added | 4,168 | +1.8 [+0.7, +3.0] | +1.4 |
| max HP up | 2,116 | +2.3 [+0.5, +4.1] | +2.1 |
| potion added | 3,212 | +5.4 [+3.7, +7.1] | +5.0 |
| HP up | 2,757 | +6.1 [+4.2, +7.9] | +3.8 |

Incense counter changes against §723's table: n = 320, slope 0.92, correlation 0.22 (§731: n 92, slope 0.63).

## Reading
- Round 2 replicates §731: every operator with a clear effect has the same sign and a similar size. HP, potion and
  relic losses cost 5-8 pp; potion and HP gains are worth 5-6 pp; relic gains about +2 pp.
- Card changes stay near 0. Removing a card is slightly negative here (−2.0) and slightly positive in §731 (+0.5);
  for a random card the two directions roughly cancel.
- With 3.5x the data, the Incense counter slope against §723 is close to 1 (0.92): the paired labels see the phase
  effect at about its probe size.
- Reseed − control is −1.8 pp with a CI just below 0 (§731: −0.7). The two use different seed blocks, so this is
  either chance or a block difference; it does not touch the paired effects, which share the control's seed.

## Decision
Labels usable (pre-registered). Stage B3 (pre-registered before these labels were read) fits on `labels_all.csv`.
