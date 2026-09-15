# Paired 500-simulation combat-budget diagnostic

This is a single exact-10,000-simulation Silver arm. Each ordinary or
sequential-selection root searched 500 simulations, recorded a read-only root
summary, and continued the same private tree for 9,500 more simulations. The
CSV therefore contains paired prefix/reference actions rather than separate
gameplay arms.

## Provenance and configuration

- Pasted-request baseline: `cde61c85b8a9ad8500cd3ca6e18607ff33bb6e1a`
- Actual current-main baseline used: `28d39cdb611865518bed68d57b5f0afb6fcee5b5`
- Frozen implementation/executable SHA: `ee7e80a0361e720972b3d43872adfa13c1ef2c2c`
- Seeds: `64..79` (16 fresh paired seeds)
- Character/ascension: Ironclad A0
- RNG: project-fair Silver
- Combat: exact Silver root budgets, base budget 10,000
- Reuse: allocated mode, experimental cap 131072
- Disabled: `STS_SIM_ADAPT`, `STS_SILVER_ADAPTIVE`, `STS_CONVERGE`,
  `STS_CONV_ROOT`, keys, OOC MCTS, and unrelated gameplay treatments
- Native OOC: enabled; Searcher3: disabled; four OpenMP workers

The command was executed through `tools/seed_guard.sh`:

```text
build/linux-gcc-release-ccache/one_combat bestbench 10000 16 0 64 experiments/evidence/combat_budget_diag_2026-09-15/results.csv
```

The benchmark sidecar, collection log, run plan, raw diagnostic CSV, and
machine-readable analysis are kept in this directory.

## Verification

- `cmake --build --preset linux-gcc-release-ccache-build --target silver-bridge-test`: PASS
- `ctest --test-dir build/linux-gcc-release-ccache -R 'silver_bridge_boundary|analyze_combat_budget_diag_selftest' --output-on-failure`: 2/2 PASS
- Fixed-state prefix test: standalone 500 action equals the paired 500 action; checkpoint root statistics are valid.
- Diagnostic OFF/ON canary, seed 42, exact 10k: identical win, floor 51, final HP 45/80, and zero fight losses. The diagnostic ON run emitted 430 decision rows.
- Collection: 16/16 result rows, 7,016 diagnostic rows, all seeds exactly `64..79`, and every row exactly `(500, 10000)`.
- No empty action fingerprints; the checkpoint root-Q gap was unavailable only for roots with an unvisited second action, as represented by its validity field.

## Results

The analyzer uses the first decision row of each combat as the predictor and
defines `500_sufficient` conservatively: every decision row in that combat must
agree with its 10k action.

| Scope | Fights | Stable | Unstable | Per-decision agreement | 500-sufficient rate |
|---|---:|---:|---:|---:|---:|
| Train seeds 64–71 | 193 | 10 | 183 | 77.47% | 5.18% |
| Holdout seeds 72–79 | 205 | 25 | 180 | 80.12% | 12.20% |
| All seeds | 398 | 35 | 363 | 78.82% | 8.79% |

Held-out AUROC/AUPRC for predicting `fight_requires_more` are:

| Diagnostic | AUROC | AUPRC |
|---|---:|---:|
| Q gap | 0.454 | 0.861 |
| Top visit share | 0.484 | 0.879 |
| Second visit share | 0.475 | 0.874 |
| Top/second visit ratio | 0.465 | 0.857 |
| Visit entropy | 0.529 | 0.892 |
| Legal action count | 0.492 | 0.883 |

AUPRC is high only because the unstable class is prevalent (180/205 held-out
fights); it does not indicate useful separation. No threshold selected on the
first eight seeds achieved the required ≤5% false-stop rate at nonzero
coverage, so the unchanged held-out risk/coverage result is zero coverage for
every diagnostic. Held-out unstable fights occurred in hallway, elite, boss,
and other categories; there is no safe category-only exception supporting a
production allocator.

## Decision

`NO_USEFUL_SIGNAL`. The requested simple diagnostics do not predict whether a
combat can safely stop at 500 simulations. Do not train an adaptive-budget NN
or implement an early-stop policy from this experiment.

Smallest next experiment: stop this line unless a separately justified change
targets a different label or a different reference/search regime. If resumed,
first run a fixed-state audit of that changed contract; do not pool or retune
this 16-seed result.

Knowledge impact: experiment evidence only; no production budget, search,
model, RNG, or gameplay default changed.
