# Heart-entry perturbation labels (stage A): result

Pre-registration: [PREREG.md](PREREG.md) (frozen before launch; prelaunch review PASS). Campaign `heart-entry-perturb`,
RUN_COMMIT 60e1d676, code f063e9ff; 16 workers × 4 lanes, 2026-10-31 19:16Z – 11-01 00:35Z (Philipp's go 19:14Z).
`verify_campaign.py`: 1000/1000 units OK, 0 missing, 0 bad, 0 duplicates (worker 10 restarted once and resumed),
16/16 worker DONE files ([results/verify.txt](results/verify.txt)). Analysis: frozen `analyze.py`, output
[results/analysis.json](results/analysis.json) and [results/labels.csv](results/labels.csv) (16,000 fights).
All 1,000 units rc=0, 1,000 bases valid, 699 source seeds, 0 bad rows. CI: bootstrap over source seeds.

## Pre-registered check
Sign checks: HP up +, HP down −, potion added +, potion removed − are **consistent**; card upgraded and max HP up are
**unresolved** (CI includes 0); none INCONSISTENT → **labels usable**, stage B may start.

## Co-reported
| | value |
|---|---|
| control Heart kill | 65.4% [62.0, 68.7] |
| reseed − control kill | −0.7 pp [−3.6, +2.1] |
| outcome flips vs control, reseed only | 20.3% [17.7, 22.9] |
| outcome flips vs control, one change (same seed) | 13.6% [12.4, 14.8] |
| mean effect over all 14,000 changes | −1.0 pp [−2.5, +0.5] |
| CPU | 197 CPU-h (≈ 44 s per fight; estimate was 83 s) |

Effect per operator, kill(variant) − kill(control), pp:

| operator | n | effect [95% CI] |
|---|---|---|
| HP down (5-30% of max) | 1,712 | −7.1 [−9.3, −4.9] |
| potion removed | 810 | −7.2 [−11.1, −3.3] |
| relic removed | 1,323 | −5.0 [−7.1, −2.9] |
| relic counter changed | 1,058 | −2.7 [−5.4, −0.1] |
| max HP down | 651 | −1.7 [−4.9, +1.6] |
| potion swapped | 871 | −0.3 [−3.6, +2.9] |
| card upgraded | 1,280 | +0.3 [−1.8, +2.5] |
| card removed | 1,263 | +0.5 [−2.8, +3.9] |
| relic added | 1,332 | +1.4 [−0.4, +3.1] |
| max HP up | 625 | +2.1 [−1.0, +5.3] |
| card added | 1,252 | +2.2 [−1.2, +5.7] |
| HP up | 823 | +3.8 [+0.6, +7.0] |
| potion added | 1,000 | +5.0 [+1.7, +8.3] |

Incense counter changes against §723's table: n = 92, slope 0.63, correlation 0.24 (same direction, weak at n = 92).

## Reading
- Common battle seeds help: one change flips the outcome in 13.6% of pairs, a reseed alone in 20.3%, so a paired
  label carries less luck than an independent fight on a new seed.
- No sign anomaly like §726: the mean over all changes is about 0, reseed − control is about 0, and every
  operator with a clear effect has the expected sign. Losses (HP, potion, relic) show up clearly; gains of a relic,
  card or max HP are small and not resolved at about 1,000 labels each.
- Single changes move the Heart kill by a few pp against ±50 pp of luck per fight, so a value model needs all
  16,000 labels (and probably the observational records) to learn them.

## Caveats
- Research Heart search (learned stop ≤ 10k, Act 4 strong off), not production's flat 40k.
- Bottled cards, gold and map not carried; relic_add applies no on-pickup effects; 50 potion swaps are no-ops
  (disclosed before launch).
- The Incense comparison uses §723's table from largely the same games.

## Decision
Labels usable (pre-registered). Stage B (all-feature Heart-entry value trained on `labels.csv`, scored on held-out
paired differences against Silver's leaf) gets its own pre-registration before any fitting.
