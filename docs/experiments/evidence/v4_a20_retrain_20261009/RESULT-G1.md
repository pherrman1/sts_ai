# G1 result: V4 constant-input guard at A20

Pre-registration: [PREREG-G1.md](PREREG-G1.md). Code `3971fe8e`, 128 paired seeds
67100000..67100127, both arms exit 0, sidecars in `g1/`.

| Arm | Wins | Mean floor | Reached floor >= 50 | CPU s/run |
|---|---|---|---|---|
| G0 guard off (current V4) | 16/128 (12.5%) | 36.12 | 50 | 13.0 |
| G1 guard on | 12/128 (9.4%) | 34.90 | 40 | 12.0 |

- Rows differing: 94/128, so the +8 ascension input does change A20 play.
- Floor G1 - G0: -1.22, 95% paired bootstrap CI [-3.51, +1.11] (10,000 reps, RNG 20261009).
- Verdict by the frozen rule: **`GUARD_WORSE_OR_UNCLEAR`**. The guard is not adopted;
  G2 uses the current V4 (guard off) as control.
- **Inference:** the untrained ascension shift is not obviously harmful at A20; if anything
  the shifted network plays slightly better. Not shown either way.
