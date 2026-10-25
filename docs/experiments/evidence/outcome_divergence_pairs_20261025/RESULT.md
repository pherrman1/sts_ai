# Result: outcome-label value head on first-divergence pairs — NO_SIGNAL; children correlate at rho ≈ 0.49

Pre-registration: [PREREG.md](PREREG.md) (commit `fc5b2e2`), code [s0.py](s0.py) (`8427b92`), head frozen and rho
recorded before TEST was read (`3c9fcf5`). Offline, no gameplay seeds, about 15 CPU-minutes on one cloud container.

## Data ([extract.json](extract.json))
2,560 unit tars (§683 1,024 seeds × D/MAP/OFF, §661 1,024 × A/M/S/MS, §676 512 × A/C); 8,192 games, all with
`complete` and `integrityPassed`; no duplicate seeds. 9,728 arm pairs: 1,218 never diverge, 8,510 first-divergence
pairs. TRAIN 4,096 games (679,381 state rows), VALIDATION 2,048 games (339,366 rows); TEST pairs 2,148 from 604 seeds.
Artifact hashes in [artifacts.sha256](artifacts.sha256).

## rho: outcomes of two children of one root under the same seed ([rho.json](rho.json))
| roots | pairs | rho, Heart kill [95% CI] | rho, Act-4 arrival |
| --- | --- | --- | --- |
| all | 8,510 | 0.488 [0.455, 0.520] | 0.512 [0.484, 0.540] |
| act 1 | 6,084 | 0.436 [0.400, 0.471] | 0.472 |
| act 2 | 1,908 | 0.570 [0.514, 0.623] | 0.559 |
| act 3 | 511 | 0.574 [0.486, 0.662] | 0.593 |

Common seeds halve the variance of a whole-game sibling difference (1 − rho ≈ 0.51), much better than the ~0.2 the
plan assumed from §607's act-end copies. Caveat: these roots are where two configurations of the same stack first
disagree, so the children are often close; other roots may correlate less.

## Head G ([fit.json](fit.json))
XGBoost 3.0.2, 239 trees, sha `fa852066…` ([head_G.json](head_G.json)). VALIDATION weighted log loss vs the TRAIN
constant: act 1 0.403 vs 0.438, act 2 0.488 vs 0.549, act 3 0.548 vs 0.714, act 4 0.611 vs 0.944 (descriptive).

## Primary ([test.json](test.json))
**A_h = −1.16 pp [−2.80, +0.40] Heart kills per divergence (2,148 pairs, 604 seeds) → NO_SIGNAL.**
Act-4 arrival −0.05 pp [−1.96, +1.88]. No campaign, arm pair or root act excludes 0 in the head's favour; by root
screen, screen 2 is +2.4 pp [+0.4, +5.0] and screen 1 −10.8 pp [−19.6, −2.8] (16 subgroups, not corrected).
On §683 search-vs-OFF pairs the search's own advantage is D−OFF −3.3 pp [−8.5, +2.0], MAP−OFF −0.6 pp; head minus
search −1.2 pp [−10.2, +7.7] and +0.6 pp [−7.4, +8.6].

## Exploratory, not pre-registered ([explore.json](explore.json), [explore.py](explore.py))
- 1,205 of 2,148 TEST pairs are ties (equal head value). Only 37 have identical features; 612 ties are at map
  roots (screen 5) and 418 at screen 2. The features count rooms above the current row of the whole map, not the
  rooms reachable from the child's node, so after a map choice the two children differ only in mapX, which the head
  does not use. The frozen head is blind to routes by construction.
- On the 943 non-tied pairs A_h is −2.7 pp [−6.4, +0.9]; accuracy on non-tied discordant pairs 0.43 [0.34, 0.52].
- (`headAccuracyDiscordantHeart` in test.json counts ties as wrong; read explore.json's non-tied accuracy instead.)

## Interpretation
- One real outcome per state, on 4,096 training games, teaches the level (log loss well below the constant in every
  act, as in §498/§515) but not which child of a root is better: the head picks the winning child no better than a
  coin, and slightly worse. This matches §502 and §509 with 4× the games of §498. More labels of the same kind (full
  rollouts, one per state) are not the bottleneck at this scale; representation is (here: routes are invisible).
- Cost of a full-rollout sibling referee with the measured rho: rollouts per child for SE 1 pp of a mean advantage
  over R flip roots ≈ 3,800 × 0.51 / R ≈ 1,940 / R. Both children: ≈ 3,900 continuations, ≈ 430 core-h with the
  production policy (≈ 400 s each) or ≈ 210 core-h with student_sel continuations (≈ 190 s), against ≈ 310 core-h
  for a paired 1,024-seed A/B. A paired A/B is itself this referee with one continuation per flip root, so extra
  continuations buy about what extra A/B seeds buy. Under the pre-registered rule (production policy) the referee
  is more expensive than the A/B: the full-rollout label line STOPS.
- Inference: a route-aware head (rooms and fights reachable from the child's node) would be the next offline test;
  TEST here is consumed, so it would be developed on VALIDATION pairs and judged on new paired data (#860's forks or
  a later A/B).

No default, code path or seed block changed.
