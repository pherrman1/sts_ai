# G2 result: A20-retrained V4 Q head at A20

Pre-registration: [PREREG-G2.md](PREREG-G2.md). Raw rows and meta: [`g2/`](g2/).

| Arm | Model | Wins /128 | Mean floor | Floor >= 50 | CPU s/run |
|---|---|---|---|---|---|
| C | current V4 (e62abd83) | 14 | 33.39 | 39 | 16.6 |
| T | A20 Q-head retrain (135e5500) | 12 | 32.29 | 32 | 11.6 |

- Primary: T - C mean paired floor = **-1.10**, 95% paired bootstrap CI **[-4.16, +1.96]**
  (10,000 reps, RNG 20261010). 119/128 runs differ.
- Both metas record learned stop gbt-770201c31f7b and the live V4 gates; T meta records
  `oocStrategicTokNet` sha 135e5500, C meta e62abd83.
- A first T launch did not load the gate environment; it was killed and discarded
  before any comparison and rerun with the pre-registered environment.

**Verdict: `NOT_SHOWN`.** No default change.

Interpretation (**Inference**): the offline gain is small (held-out strict Q top-1 0.309 vs
the heuristic chosen action 0.334 on the same labels), so the labels (4.9k decisions, ~4
playouts each, median within-decision floor spread 8) are too thin to teach the Q head
more than the heuristic already knows. Combined with G1, the A20 input mismatch of the
deployed V4 is not a measurable win-rate lever at this sample size.
