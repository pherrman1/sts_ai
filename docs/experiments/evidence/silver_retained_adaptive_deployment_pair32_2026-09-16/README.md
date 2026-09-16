# Retained-root adaptive Silver deployment gate (N32)

Date: 2026-09-16
Pre-promotion source SHA: `066264dc25bf2046aecd5ca7a94a8e82d5031e7b`
Release binary SHA-256: `c85579fd22a9c38475a3810062cabd0a15fe6d4bc33c8ea5f9ee0dee5a476eb3`

This is the final paired deployment screen before promoting PR #199's frozen
retained-root adaptive Silver policy. It uses the next unused contiguous block,
seeds 224--255, with the current normal production environment: Ironclad A0,
project-fair Silver, native OOC, four workers, base budget 10,000, allocated
32,768 reuse cap, ordinary boss budgeting, CTM/convergence/OOC MCTS/keys off,
and exact-lock/rho off. Both arms use the same Release executable.

The treatment is exactly:

```text
fresh root or one-action/forced root -> 10,000 new simulations
retained non-forced root -> 500 new simulations
  stop when top-two visit-gap share >= 0.2932885906040268
  otherwise continue the same private root to 10,000
```

## Results

| Measure | Control | Treatment |
|---|---:|---:|
| Wins | 21/32 | 22/32 |
| Mean final floor | 48.28125 | 48.40625 |
| Mean ending HP | 29.34375 | 32.90625 |
| Wall time | 395.72 s | 132.08 s |
| Silver simulations | 202,860,000 | 81,633,000 |
| Decisions | 13,852 | 13,945 |
| Fresh roots | 814 | 812 |
| Retained roots | 13,038 | 13,133 |
| One-action/forced roots | not collected in control summaries | 510 |
| 500-simulation stops | 0 | 6,086 |
| 10k continuations | ordinary 10k/30k room budgets | 7,859 |
| Exact reroots | 7,910 | 9,266 |
| Reroot fallbacks | 5,942 | 4,679 |
| Bridge failure counters | all zero | all zero |

Treatment reduced Silver simulations by **59.7589%** and wall time by
**66.6229%**. Paired wins had four control-only seeds (233, 245, 247, 248)
and five treatment-only seeds (228, 229, 244, 246, 251): one fewer net
control-only win, within the deployment screen. Floor disagreed on 11 pairs
and ending HP on 24 pairs; treatment point estimates were not degraded.

## Invariant validation

- Both result files contain exactly one row for every seed 224--255.
- Control used its ordinary 10k/30k root budgets; no adaptive, exact-lock, or
  rho stop occurred.
- Treatment used only 500 or 10,000 new simulations, with 7,859 continuations.
- All 6,086 treatment 500-stops were retained, non-forced, and had a gap at
  least the threshold; the minimum observed stop gap was `0.293374`.
- All 812 treatment fresh roots and all 510 one-action/forced roots reached
  10,000 simulations.
- Exact-lock and rho counters were zero in both arms.
- Conversion, semantic-resolution, transaction, and knowledge counters were
  zero in both arms.

Classification: **`RETAINED_ADAPTIVE_DEFAULT_GO`**. This N32 result is a
deployment screen, not a formal equivalence proof or superiority claim.

Raw per-arm files are in `control/` and `treatment/`: `results.csv`, its
metadata sidecar, `scaling.csv`, and `run.log` (including `/usr/bin/time -v`).
`paired.csv` and `summary.json` contain the machine-readable pairing and
validation. The benchmark was run through `tools/seed_guard.sh`.
