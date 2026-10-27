# Stage A result (2026-10-26, 256 sources)

Run commit `9ec4944c`, 32 cloud workers (interrupted 2026-10-25 14:42Z by a usage limit at 217/256, resumed
2026-10-26 19:04Z). `verify_campaign.py`: units OK 256, MISSING 0, BAD 0, duplicates 0. 1,429 games, all rc 0; every
fork passes `forks.py check` (`analyze.py` raises otherwise). 219.7 core-h (0.86 per source). Seeds 111378000–111378255
used.

## Pre-registered futility rule: CONTINUE

`analyze.py --stage A` ([analysis-stage-a.json](analysis-stage-a.json)): 256 valid sources, 225 with a root, 391 roots
(225 act 1, 166 act 2), all production picks by `heart1_screen`, one production skip.

| endpoint | keys | τ̂ (spread of relic effects) | mean SE | projected split-half r (1,024) |
|---|---|---|---|---|
| Heart kill | 22 | 0.106 | 0.054 | **0.885** (≥ 0.35 → ask for Stage B) |
| Act-4 arrival | 22 | 0.112 | 0.057 | 0.887 |

Heart kill at these roots: production pick 38.9%, mean of the untaken options 19.4%, skip 12.8% (Act 4: 57.3 / 36.0 /
27.6%). CRN correlation of options within a root 0.36 (Heart), 0.45 (Act 4).

Relic utilities against skip (Heart, pp): Snecko Eye +45, Pandora's Box +42, Coffee Dripper +30, Runic Dome +23, Runic
Cube +22, Fusion Hammer +21, Cursed Key +19 … Tiny House +5, Ectoplasm +4, Velvet Choker +2, Black Blood +2 (SE ≈ 5-6).

## Descriptive, not a gate: the Stage B override on Stage A data

The Stage B gate computed on Stage A's 256 sources only (2-fold cross-fit, same code;
[stageA-override-preview.json](stageA-override-preview.json)). This is a preview, not the pre-registered test.

| table on | overrides fire | Heart gain per source | Act-4 gain per source |
|---|---|---|---|
| Heart | 21.0% of roots | −2.7 pp [−6.6, +1.2] | −5.5 pp [−9.4, −2.0] |
| Act 4 | 16.6% | −2.3 pp [−5.1, 0.0] | −3.1 pp [−6.3, 0.0] |

The production pick is the table's best option at 289 of 391 roots (74%), second at 66, third at 35.

## Reading (inference)

- Boss relics matter a lot, and real-combat forks measure them reproducibly: the opposite of #855's card effects.
- student_sel already picks close to the best relic, and where it departs from the context-free table it is usually
  right (the table's overrides lose). A per-relic table is unlikely to pass Stage B's gate.
