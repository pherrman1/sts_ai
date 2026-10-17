# V1 blended Silver leaf, offline gate: FAIL (2026-10-17)

Pre-registration: [PREREG.md](PREREG.md) (written before any blend score). Offline only, no gameplay seeds.

## Inputs

- Corpus: frozen §397 `corpus-450376c8` (archive
  `/mnt/project-files/silver-synthetic-prior/ARCHIVE-silver-synthetic-prior.tar.gz`, sha256 `295fe02d…`).
- Features: `one_combat silversynthfeatures` on main `623a8b60` (binary sha256 `2b94132f…`), 48 units,
  3,064,557 rows, 1,788 policy / 1,766 state features. The archived §397 feature rows were not kept, so V was
  retrained with the unchanged §397 recipe ([scripts/train_v.py](scripts/train_v.py), copied from
  `tools/silver_synth_gates.py train`): `vcont-natpert` 145,000 train / 46,679 val rows, 536 iterations
  (sha256 `aebe4c4a…`); `vroll-natpert` 337,490 / 108,339, 1,447 iterations (`5662000d…`). Models:
  `/mnt/project-files/silver-blend-leaf/models/`.
- Gate: [scripts/blend_gate.py](scripts/blend_gate.py), raw output [blend_gate.json](blend_gate.json).

## Result

α picked on natural validation fold 3 (R1 regret 4.128): vcont blend α = 0.8 (3.720), vroll blend α = 0.7 (3.505).

Natural test fold 4, 2,006 sibling groups from 43 seeds (§397 had 2,007; one root drops on a root-edge mismatch
under the current engine). Differences: mean with seed-clustered 95% bootstrap CI.

| Predictor | Regret | Concordance | − R1 | − R2 |
|---|---:|---:|---|---|
| R1 (one rollout) | 3.989 | 0.6730 | | |
| R2 (two rollouts) | 3.934 | 0.6848 | −0.055 [−0.334, +0.221] | |
| R4 (four rollouts) | 3.637 | 0.6962 | −0.352 [−0.735, +0.040] | |
| V vcont alone | 4.182 | 0.6766 | +0.192 [−0.368, +0.730] | |
| V vroll alone | 3.978 | 0.6834 | −0.011 [−0.528, +0.486] | |
| **B vcont, α 0.8 (primary)** | 3.972 | 0.6887 | **−0.017 [−0.436, +0.377]** | +0.038 [−0.377, +0.483] |
| B vroll, α 0.7 | 3.953 | 0.6930 | −0.037 [−0.397, +0.327] | +0.019 [−0.316, +0.374] |

Perturbed test fold 4 (1,976 groups, secondary): B vcont −0.272 [−0.565, +0.048], B vroll −0.359 [−0.705, −0.017],
R2 −0.156, R4 −0.455 [−0.851, −0.130] vs R1.

- **Gate: FAIL.** Concordance rises (0.6887 vs 0.6730) but the regret CI upper bound is +0.377, not < 0.
- The blend behaves like a second rollout (B − R2 ≈ 0 on both models), not better.
- Sanity: the retrained V alone reproduces §397 within 0.3 regret (vcont − R1 +0.19 now vs +0.37 in §397).
- The gate has little power: even four rollouts are not separated from one on natural test (CI to +0.04).
  The headroom for any leaf-variance reduction on this corpus is about 0.35–0.5 regret. **Inference:** a blended
  leaf would at best match a second rollout, and would only pay if V costs less than one rollout.

Per the pre-registration, FAIL closes V1; no native implementation or gameplay A/B.
