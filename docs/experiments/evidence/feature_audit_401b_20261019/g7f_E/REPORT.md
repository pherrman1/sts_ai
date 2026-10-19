# #401 Stage 1: grouped permutation importance, Silver combat prior g7f_E

Analysis only, no seeds. Full numbers (all groups, subgroups, single features, CIs, per-source deltas, column mapping, script sha256s) are in `results.json`; scripts in `scripts/`, logs in `logs/`.

## Provenance
- **Artifact:** `models/combat_policy_mlp_g7f_E.txt` (sha256 `c45dcc0a…0934`, v2). The value head comes from `runs/g7f_E/model.pt` on `claude/silver-gen7-act4-data` 0168b72d.
- **Data:** `pack-g7f.npz` (sha256 `bdaf4f68…`).
- **Split:** the trainer's validation fold `r_seed % 5 == 3`: 582,140 roots, 3,504,320 edges, 1,952 (source, seed) clusters.
  - This fold also selected the best epoch (20/25), so the deltas are slightly optimistic.
  - Test fold 4 was not used.

## Parity: PASS
- Val CE 1.2221620, identical to `train.json` (relative difference 4e-8). Top-1 0.5647267, identical.
- Logits are within 1.9e-6 of `model.pt`. Value MSE is 0.0270.
- By source:
  - Window roots (A0, gens 3–6, 502k): CE 1.192.
  - g7a4 roots (A20 Act 4, 80k): CE 1.411.

## Method
- **State groups:** whole roots are permuted jointly, and the embeddings and target-slot features derived from the permuted fields are recomputed.
- **Candidate groups:** roots are permuted within strata of equal candidate count; the visit labels stay with their roots.
- **Repeats and CIs:** 5 repeats per group (spread ≤ 0.0009 CE). CIs are 1,000-resample source-seed cluster bootstraps.

## Ranked groups (Δ policy CE, 95% CI; window / g7a4)
| group | ΔCE [CI] | window / g7a4 | note |
|---|---|---|---|
| candidate card id (embedding) | +0.150 [0.148, 0.152] | 0.160 / 0.082 | top-1 −0.112 |
| monster slots m0–m4 | +0.114 [0.112, 0.115] | 0.122 / 0.060 | intent dmg +0.034, HP +0.034, id +0.030 |
| candidate card attributes | +0.090 [0.089, 0.092] | | |
| candidate action type | +0.086 [0.084, 0.088] | | aIsPotion alone +0.053 |
| candidate targeting | +0.073 [0.072, 0.074] | ≈ equal | target slot alone +0.028 |
| energy | +0.060 | | |
| hand | +0.040 | | |
| player powers | +0.037 | | |
| relics | +0.032 | | |
| HP / block | +0.031 | | value MSE +0.107 (largest value group) |
| encounter | +0.029 | | |
| monster aggregates | +0.027 | | |

## Dead or near-zero
- gold +0.00002 (CI includes 0).
- maxHp +0.00004.
- Pile and hand count columns ≤ 0.001 each; the pile signal sits in the per-card composition.
- relic counters +0.0013.
- ascension +0.002: it is constant within each source, so it only identifies the source.

## Findings (**Inference**)
- **Act 4 leans less on every group.** On the g7a4 roots most group Δs are about 1.5–3× smaller, and CE is worst there. Targeting is about equal in both, and monster Block matters more in Act 4. The prior is less informed in Act 4; a missing Act-4/boss feature is possible.
- **Brittle column:** ex228 (Necronomicurse in exhaust) appears in 0.45% of roots.
  - Permuting it raises value MSE by +0.026, about the size of the whole baseline.
  - It also adds +0.0034 policy CE [0.0015, 0.0073].
  - Clip it or make it presence-only on the next retrain.
- **Interactions:** the six candidate groups sum to 0.41, against 0.53 for permuting the whole candidate block.
- **Removal-ablation candidates** (need a refit; importance alone does not show they are unneeded): gold, maxHp, the four pile/hand count columns, relic counters.
