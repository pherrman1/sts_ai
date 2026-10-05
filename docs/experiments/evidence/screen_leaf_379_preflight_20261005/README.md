# Issue #379 preflight and sealed DECISION audit

Baseline: `a59d7e47f7fc0faee3015e824b267f6bf2961adc`, verified against remote main.

## Scope and status

TRAIN/VALIDATION custody and public-screen audit PASS. No model was selected or trained, no DECISION TEST numerical rows were parsed, and no gameplay-quality comparison was run. Full S0 requires exact frozen trajectory reconstruction; the CSV is not a complete simulator snapshot. Native screen-leaf inference is not implemented.

`GITHUB_CI_NOT_USED_BILLING_LIMIT`.

## Custody

Corpus SHA-256 `ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00`; 696 TRAIN, 155 VALIDATION, 173 sealed TEST sources. All 1,024 component-manifest and DECISION table hashes match. TEST tables were hashed as opaque bytes only, with zero headers or numerical rows parsed. Full historical corpus validation was not repeated.

X2-B native SHA-256 `a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf`; source UBJ identity `99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd` from its frozen manifest. Native artifact hashed locally; no default changed.

## DECISION audit

| Screen | TRAIN rows | VALIDATION rows | TRAIN row win rate | VALIDATION row win rate |
|---|---:|---:|---:|---:|
| boss_relic | 28,361 | 6,170 | 0.76912 | 0.78088 |
| event | 92,930 | 20,016 | 0.77109 | 0.78552 |
| rest | 124,883 | 27,443 | 0.77288 | 0.78355 |
| rewards | 1,002,326 | 220,331 | 0.77657 | 0.79010 |
| selector | 88,488 | 19,100 | 0.78266 | 0.80377 |
| shop | 122,356 | 25,231 | 0.77420 | 0.79208 |
| treasure | 49,670 | 11,134 | 0.77502 | 0.77834 |

Every screen has all 696/155 sources. Row-weighted win rates are descriptive, not model results. All emitted rows have complete supported enumeration. Event captures omitted for unsupported/incomplete enumeration: 14,370 TRAIN and 3,930 VALIDATION. `rewards` includes public reward screens, not just card choices. See `audit-reviewed.json` for source versus branch counts, candidate distributions, identities, structural variants, bytes per row, and the exact access seal. Initial `audit.json` is preserved; the reviewed report clarifies observed versus captured source counts.

## Current-main timing

Both runs select X2-B explicitly, use one thread, exact 10k Silver and OOC2048 with existing CPU attribution. These different seeds/configurations are separate profiles, not an A/B or a CTM speed comparison.

- `baseline3`: historical seed 12002032 and explicit historical attention CTM. Process CPU 225.67 s, MCTS 170.5306 s, leaf evaluation inclusive 52.9275 s.
- `current-default`: seed 12002033, current default DeepSets + Brew fallback + active-Lizard stack. Process CPU about 102.1 s, MCTS 62.6637 s. This is the current-default baseline to retain for any future matched timing comparison.

| Current-default bucket | Calls | Inclusive CPU s | Exclusive CPU s |
|---|---:|---:|---:|
| mcts | 125 | 62.663420 | 0.728419 |
| evaluate_leaf | 121894 | 33.616922 | 16.981830 |
| leaf_features | 121891 | 0.249580 | 0.249580 |
| leaf_predict | 121891 | 1.186017 | 1.186017 |
| prior_build | 113932 | 10.391274 | 0.193393 |
| combat_prepare | 23227 | 9.401651 | 9.401651 |
| combat_resolve | 23805 | 1.202226 | 1.202226 |
| real_combat | 26 | 39.267332 | 39.267332 |

Inclusive scopes overlap; do not sum them. Projection steps, ownership/fallback and additional counters are retained in the raw MCTS CSV. Two initial startup-only attempts rejected removed historical Silver telemetry/reuse flags before running a seed; their logs and receipts are preserved.

## Exact S0 recovery gate

The frozen DECISION sink retains rich run features, public screen contents and candidates, but not full RNG/pool/map state or executable continuation callbacks. The frozen generator kept its full state and combat action trace in memory. Original frozen producers and models remain available.

The derived exporter is reconstructed with `git archive` in an ignored build directory, without another linked worktree. It wraps original callbacks without changing their bodies and exports full snapshots. The current-main importer maps their identities to current continuation behavior, then calls the actual adapter `evaluateLeaf`. It does not replace S0 with a heuristic.

Estimated VALIDATION reconstruction cost from historical metadata: 44.11 branch core-hours across 5,169 branches; approximately 45.87 core-hours including extrapolated source/setup work, before S0. Hardware and exporter overhead remain unmeasured. Canary source 13001315 is VALIDATION, with 1,774 recorded DECISION states. Its all-seven-CSV exact-parity gate must pass before S0.

Review repaired exclusive snapshot output creation and an inactive Dead Adventurer relic read. Full snapshot roundtrip and all 17 callback-family comparisons passed constructed-state tests. These do not replace replay parity.

Knowledge impact: exact reconstruction and current timing evidence are recorded here; no model qualification, default promotion, or gameplay conclusion.
