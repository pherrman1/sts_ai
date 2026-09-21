# Frozen Silver internal-FPU cohort summary

Implementation SHA: `c9f58c20cd4879584fbe0d78828d33057350d914`
Snapshot SHA-256: `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`
Configuration SHA-256: `343bdb898448880e4240ddbd6428a0a50c8f42ac2cf00bc1ed87bf90fa8e14aa`

## Preregistered primary root metric

| Comparison | Agreement |
|---|---:|
| 1k CONTROL vs 10k CONTROL | 45/64 |
| 1k FPU vs 10k CONTROL | 39/64 |

The 1k CONTROL/FPU root actions disagreed in `22/64` cases.

| Case | Direction relative to 10k CONTROL |
|---|---|
| `12100003/20` | `toward` |
| `12100007/17` | `away` |
| `12100009/22` | `away` |
| `12100009/26` | `away` |
| `12100013/20` | `away` |
| `12100013/25` | `away` |
| `12100017/21` | `both_off` |
| `12100019/23` | `toward` |
| `12100020/17` | `away` |
| `12100020/21` | `away` |
| `12100025/21` | `away` |
| `12100027/18` | `both_off` |
| `12100027/20` | `toward` |
| `12100029/5` | `toward` |
| `12100032/13` | `toward` |
| `12100035/18` | `away` |
| `12100036/16` | `both_off` |
| `12100036/21` | `toward` |
| `12100037/22` | `away` |
| `12100037/28` | `away` |
| `12100048/26` | `away` |
| `12100052/14` | `both_off` |

## Full-combat outcome and trajectory totals

These totals are descriptive only. Once initial root actions differ, nodes, depth, wall time, and simulations are trajectory-confounded and are not interpreted as causal FPU efficiency gains.

| Arm | Accepted | Wins | Simulations | Nodes | Depth | Chance depth | Search wall ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| control_1k | 64/64 | 51/64 | 2,232,000 | 2,063,754 | 12,899,741 | 3,020,027 | 130,546.679 |
| fpu_1k | 64/64 | 50/64 | 2,172,000 | 1,968,300 | 14,346,649 | 3,363,308 | 121,571.444 |
| control_10k | 64/64 | 59/64 | 22,300,000 | 19,756,757 | 165,657,681 | 40,994,876 | 1,348,714.169 |
| fpu_10k | 64/64 | 56/64 | 22,020,000 | 19,345,692 | 179,280,166 | 43,995,679 | 1,310,898.074 |

## First-decision paired efficiency

The first-decision probe excludes the five transactional `CARD_SELECT` roots, which are handled by the transactional replay path. Values below use the 59 common ordinary-root cases and are paired by case.

| Budget | Cases | CONTROL mean nodes | FPU mean nodes | CONTROL mean wall us | FPU mean wall us | Mean FPU minus CONTROL wall us |
|---:|---:|---:|---:|---:|---:|---:|
| 1k | 59/64 | 999.42 | 999.44 | 90739.926 | 91512.401 | 772.475 |
| 10k | 59/64 | 9990.44 | 9970.37 | 915215.958 | 911448.962 | -3766.996 |

First-decision wall time is diagnostic and machine-dependent; it is reported separately from whole-combat totals and is not a production-performance qualification.

## Provenance

- Analyzer validation passed for expected per-file budgets, exact status sets, snapshot state hashes, and arm-specific FPU counter identity (CONTROL counters all zero; FPU treatment opportunities positive).
- The raw replay rows do not embed the CLI flag/configuration; CONTROL/FPU identity is therefore verified from the expected file arm plus its fail-closed counter semantics, while the fixed search configuration is recorded separately by `config_sha256`.
- All four full-combat arms: `OMP_NUM_THREADS=4 bash tools/seed_guard.sh build/linux-gcc-debug/silver_hard_combat_replay CASE.jsonl BUDGET --arm control [--internal-fpu]`.
- First-decision diagnostics used the same command with `--first-decision-only`; this is measurement-only harness output and does not change FPU/search policy.
- Full-combat binary SHA-256: `a416d451279cc8d9324240e67f615fff56f52d307b8c14a07a91650ef96d7311`.
- First-decision binary SHA-256: `d7a343f6e8e57bb48929443707bb8e63850f4c501fa31a203126a35713dcc722`.
- Fixed config hash: `343bdb898448880e4240ddbd6428a0a50c8f42ac2cf00bc1ed87bf90fa8e14aa`.
- Raw compressed JSONL and decompressed-content hashes are recorded in `frozen_summary.json`.
