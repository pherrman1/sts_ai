# G3 result: V4 Q head retrained on round 1 + round 2 A20 data

Pre-registration: [PREREG-G3.md](PREREG-G3.md) (candidate fixed at `dc2a1b2e` before the gate).
Raw rows and meta: [`g3/`](g3/).

| Arm | Model | Wins /256 | Mean floor | Floor >= 50 | Act-1 deaths | CPU s/run |
|---|---|---|---|---|---|---|
| C | current V4 (e62abd83) | 29 | 35.07 | 88 | 52 | 13.1 |
| T | A20 Q-head retrain, r1+r2 (08d239f9) | 16 | 29.48 | 47 | 70 | 10.1 |

- Primary: T - C mean paired floor = **-5.59**, 95% paired bootstrap CI **[-7.75, -3.38]**
  (10,000 reps, RNG 20261010). 220/256 runs differ; T better on 77, worse on 136.
- Both metas record learned stop gbt-770201c31f7b; tok-net sha e62abd83 (C), 08d239f9 (T).

**Verdict: `RETRAIN_WORSE`.** No default change.

Interpretation (**Inference**): offline the candidate stays below the heuristic it overrides
(strict Q top-1 0.302 vs 0.341), and with margin 1.0 a Q head that is wrong more often than
the heuristic costs floors whenever it fires. Doubling the labels did not raise offline
accuracy (0.309 on round 1 alone, 0.302 on both, different validation sets), so the
one-ply heuristic-continuation labels at about 4 playouts per option look too noisy for
this route at A20, not just too few.
