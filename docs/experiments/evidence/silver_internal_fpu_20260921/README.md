# Silver internal-node finite FPU experiment

Date: 2026-09-21
Experiment implementation SHA: `c9f58c20cd4879584fbe0d78828d33057350d914`
Cohort: frozen `hard64-dev` only; `hard64-holdout` was not used
Snapshot SHA-256: `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`
Regime: isolated Silver replay, fixed budget, adaptive/exact-lock/rho/macro controls off
Threads: `OMP_NUM_THREADS=4`

## Intervention and frozen configuration

The treatment is default-off (`SilverSearchConfig::internalFpuEnabled`) and
was unchanged throughout the experiment. It applies only to non-root,
non-random `PLAYER_NORMAL` nodes with at least two edges and both visited and
unvisited edges:

```text
c_fpu = max(explorationParameter, explorationParameterChance)
parent_mean = parent.evaluationSum / parent.simulationCount
unvisited_score = (parent_mean - c_fpu)
                 + c_fpu * sqrt(log(parent.simulationCount + 1))
```

Roots, `CARD_SELECT`, chance-node DPW, visited-edge UCB, priors, exploration
constants, rollouts, values, transpositions, and RNG behavior remain
unchanged. The fixed configuration was:

```json
{
  "exploration_parameter": 25.0,
  "exploration_parameter_chance": 25.0,
  "chance_widening_c": 3.7028,
  "chance_widening_alpha": 0.52389,
  "end_turn_widening_c": 3.7028,
  "end_turn_widening_alpha": 0.52389,
  "reuse_cap": 32768,
  "reuse_cap_mode": "ALLOCATED",
  "adaptive": false,
  "exact_lock": false,
  "rho": false,
  "contract_mode": "CONTROL"
}
```

Configuration SHA-256: `343bdb898448880e4240ddbd6428a0a50c8f42ac2cf00bc1ed87bf90fa8e14aa`.

## Correctness and freeze boundary

The implementation was independently reviewed before the expensive run; no
blocking search-policy defect was found. The implementation SHA above was
then frozen. The full-combat arms used the replay binary from that frozen
implementation, SHA-256:
`a416d451279cc8d9324240e67f615fff56f52d307b8c14a07a91650ef96d7311`.

Focused checks on the frozen implementation passed:

```text
cmake --build --preset linux-gcc-debug-build -j2 \
  --target silver-search-optimization-test silver-hard-combat-replay silver-bridge-test
ctest --test-dir build/linux-gcc-debug --output-on-failure \
  -R 'silver_search_optimization|silver_bridge_boundary'
```

Result: 2/2 CTest checks passed. The fixture covers flag-off parity, root
exclusion, internal visited-edge selection, eventual unvisited exploration,
`CARD_SELECT`, and chance-node exclusions.

After the full-combat arms were complete, a measurement-only
`--first-decision-only` replay option was added to expose the existing
single-decision diagnostic fields. It does not change FPU/search behavior.
The first-decision probe binary SHA-256 was
`d7a343f6e8e57bb48929443707bb8e63850f4c501fa31a203126a35713dcc722`.

## Execution and provenance

Each case was run as one guarded process using the corresponding one-line
snapshot file. The only arm differences were simulation budget and the
`--internal-fpu` flag:

```text
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl 1000 --arm control
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl 1000 --arm control --internal-fpu
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl 10000 --arm control
OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl 10000 --arm control --internal-fpu
```

The deterministic analyzer verifies 64 unique rows per file, the expected
budget for each file, the exact allowed status set, every result row against
the snapshot's `state_hash`, and arm-specific FPU counter identity: CONTROL
rows must have all FPU counters at zero, while each FPU treatment cohort must
have positive FPU selection opportunities. It joins the paired
`benchmark_seed`, source seed, fight index, snapshot state, source executable
SHA, and pinned Silver SHA. The raw replay rows do not embed the CLI arm/config
flag, so the analyzer does not claim row-level verification of that flag; the
fixed search configuration is recorded separately by its configuration hash.
Raw decompressed-content hashes and these validation results are recorded in
[`frozen_summary.json`](frozen_summary.json).

## Complete full-combat cohort

All four arms completed with 64/64 accepted rows. These are descriptive
whole-combat totals. Once initial root actions differ, nodes, depth, wall time,
and simulations are trajectory-confounded; lower aggregate totals are not
described as a causal FPU efficiency gain.

| arm | wins/64 | simulations | nodes | depth sum | chance depth sum | search wall ms | FPU opportunities | FPU unvisited selections |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| control 1k | 51 | 2,232,000 | 2,063,754 | 12,899,741 | 3,020,027 | 130,546.679 | 0 | 0 |
| FPU 1k | 50 | 2,172,000 | 1,968,300 | 14,346,649 | 3,363,308 | 121,571.444 | 2,697,841 | 264,502 |
| control 10k | 59 | 22,300,000 | 19,756,757 | 165,657,681 | 40,994,876 | 1,348,714.169 | 0 | 0 |
| FPU 10k | 56 | 22,020,000 | 19,345,692 | 179,280,166 | 43,995,679 | 1,310,898.074 | 27,390,379 | 2,807,571 |

The FPU 1k arm recorded 2,433,339 visited-edge selections while an unvisited
edge remained; the FPU 10k arm recorded 24,582,808 such selections. Full raw
JSONL is retained as compressed files under [`raw/`](raw/).

## Preregistered primary root metric

The 10k CONTROL action is a high-budget reference, not ground truth:

| comparison | agreement |
|---|---:|
| 1k CONTROL vs 10k CONTROL | 45/64 |
| 1k FPU vs 10k CONTROL | 39/64 |

The 1k CONTROL/FPU root actions disagreed in 22/64 cases. FPU moved toward the
10k CONTROL action in 6 cases, away in 12 cases, and both 1k actions remained
different from the 10k CONTROL action in 4 cases:

| case | direction |
|---|---|
| `12100003/20` | toward |
| `12100007/17` | away |
| `12100009/22` | away |
| `12100009/26` | away |
| `12100013/20` | away |
| `12100013/25` | away |
| `12100017/21` | both-off |
| `12100019/23` | toward |
| `12100020/17` | away |
| `12100020/21` | away |
| `12100025/21` | away |
| `12100027/18` | both-off |
| `12100027/20` | toward |
| `12100029/5` | toward |
| `12100032/13` | toward |
| `12100035/18` | away |
| `12100036/16` | both-off |
| `12100036/21` | toward |
| `12100037/22` | away |
| `12100037/28` | away |
| `12100048/26` | away |
| `12100052/14` | both-off |

The complete paired per-case table, including selected actions, terminal HP,
all required telemetry, and paired provenance, is
[`frozen_per_case.csv`](frozen_per_case.csv).

## First-decision paired efficiency

The first-decision probe uses the same snapshot, budget, seed, and search
configuration but stops after the first ordinary root search. Five cases begin
at transactional `CARD_SELECT` roots and are therefore excluded from this
ordinary-root diagnostic in both arms; the full-combat replay still includes
all 64 cases.

| budget | paired ordinary roots | CONTROL mean nodes | FPU mean nodes | CONTROL mean wall us | FPU mean wall us | mean FPU minus CONTROL wall us |
|---:|---:|---:|---:|---:|---:|---:|
| 1k | 59/64 | 999.42 | 999.44 | 90,739.926 | 91,512.401 | +772.475 |
| 10k | 59/64 | 9,990.44 | 9,970.37 | 915,215.958 | 911,448.962 | -3,766.996 |

The 1k FPU first decision had 83,539 opportunities and 8,845 unvisited
selections across the 59 ordinary roots. At 10k it had 836,648 opportunities
and 93,018 unvisited selections. First-decision wall time is machine-dependent
diagnostic evidence, not a production-performance qualification.

## Decision and boundary

Classification: **`INTERNAL_FPU_INCONCLUSIVE`**.

The mechanism is materially exercised at both budgets, but the preregistered
primary root metric is mixed and leans against FPU (39/64 versus 45/64), with
12 FPU moves away from the high-budget CONTROL reference and only 6 toward it.
First-decision timing is inconsistent across budgets, and full-combat totals
cannot establish causal efficiency because trajectories diverge. The complete
10k cohort therefore does not support `INTERNAL_FPU_PROMISING` or
`INTERNAL_FPU_REJECTED` under the existing decision rule.

No coefficient tuning, holdout run, gameplay qualification, default promotion,
or search-policy modification was performed. Park this particular FPU
formulation pending a new hypothesis; no holdout spend is justified by this
mixed result.

Knowledge impact: durable complete-cohort inconclusive Silver allocation result,
first-decision telemetry seam, and paired evidence contract; no production or
default behavior changed.
