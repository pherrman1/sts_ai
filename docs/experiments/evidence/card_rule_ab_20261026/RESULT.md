# Card-reward rule screen at A20: result (256 seeds, 2026-10-27)

Pre-registration: [PREREG.md](PREREG.md). Run commit `5e27e0ad` (code `4eb0b3c5`, v3 binary `5ae5b712…`),
16 cloud workers, queue schedule, 2026-10-27 10:17Z - 2026-10-28 02:27Z. 254 units were verified by
`verify_campaign.py` (OK 254, BAD 0, one run commit). Units 111387126 and 111387143 each lost three attempts to
dead workers (W16, W15, W07, W05); the author ran both locally with the same frozen binary, inputs and
`run_unit.sh` (all eight arms rc=0, peak ~2.9 GB for two units, so the deaths were not these seeds). Analysis:
`python3 -I analyze.py <units dir> result.json` -> [result.json](result.json).

## Primary: Heart kills (256 paired seeds)

| arm | kills | rate | X - A | 95% CI | X only / A only | McNemar p | verdict |
|---|---|---|---|---|---|---|---|
| A (student_sel) | 72 | 28.1% | | | | | |
| B (SR head argmax) | 27 | 10.5% | -17.6 pp | [-23.4, -12.1] | 8 / 53 | 3e-9 | STOP |
| C (uniform search, X2-B M0 leaf) | 23 | 9.0% | -19.1 pp | [-25.0, -13.3] | 8 / 57 | 3e-10 | STOP |
| D (uniform search, SR leaf) | 48 | 18.8% | -9.4 pp | [-15.6, -2.7] | 23 / 47 | 0.006 | STOP |

## Secondary
- Act-4 arrival: A 41.4%, B 22.7%, C 21.1%, D 33.2% (B-A -18.8 pp, C-A -20.3, D-A -8.2).
- D - B: +8.2 pp kills [+2.7, +13.7]; D - C: +9.8 pp [+4.7, +14.8]. Search on top of the SR head beats the head
  alone, and the SR leaf beats the X2-B M0 leaf, but both remain far below student_sel.
- Kills per Act-4 arrival: A 0.68, B 0.47, C 0.43, D 0.56. Deaths by act (1/2/3/4): A 34/65/51/34,
  B 24/76/98/31, C 36/79/87/31, D 28/61/82/37: the losses come mostly in acts 2-3.
- Mean final floor: A 42.0, B 40.7, C 38.9, D 42.6.

## Mechanism
- First divergence is an act-1 card reward on 245-255 of 256 seeds per contrast.
- Card-rule roots: B 5,784, C 5,553, D 6,008. Picks off the student_sel argmax: B 43%, C 49%, D 38%.
  Skips: B 23%, C 16%, D 23% of card-rule roots (bot default ~12%, Baalorlord 30%, §688).
- Cost (mean wall per game): A 857 s, B 707 s, C 2,233 s (2.6x A), D 2,647 s (3.1x A).

## Reading
All three rules are clear STOPs. Replacing student_sel's card picks with a value head (B) or with a uniform
search that prices options by Q (C, D) loses 9-19 pp Heart kills. Neither the X2-B M0 leaf nor the
SR_crn_r2_s2_ep20 head ranks card options well enough to beat the policy prior. The search's ~1-floor tree plus
rollout3 does not fix this. Searching with the SR leaf (D) is the least bad option, so the leaf carries signal,
but not enough. The higher skip rates of the rules (16-23%) did not help. **Inference:** student_sel's card
prior encodes deck-building knowledge that the value estimates in use today do not capture. A card-reward
evaluator would need a value head trained to separate post-pick states, judged by ranking against real outcomes,
before another play test.
