# Silver internal-node finite FPU experiment

Date: 2026-09-21
Baseline: `39e91c8f6d33a842ddb378b681aeac681b4670c9` (`origin/main`)
Cohort: frozen `hard64-dev` only; `hard64-holdout` was not used
Snapshot SHA-256: `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`
Regime: isolated Silver replay, fixed budget, adaptive/exact-lock/rho/macro controls off

## Intervention

The treatment flag is default-off (`SilverSearchConfig::internalFpuEnabled`). When enabled, only non-root, non-random `PLAYER_NORMAL` nodes with at least two edges and a mix of visited and unvisited edges use finite FPU for unvisited edges:

```text
c_fpu = max(explorationParameter, explorationParameterChance)
parent_mean = parent.evaluationSum / parent.simulationCount
unvisited_score = (parent_mean - c_fpu)
                 + c_fpu * sqrt(log(parent.simulationCount + 1))
```

Roots, `CARD_SELECT`, chance-node DPW, visited-edge UCB, transpositions, and all default-off behavior remain unchanged.

## Correctness

Focused checks passed:

```text
cmake --build --preset linux-gcc-debug-build -j2 --target silver-search-optimization-test silver-hard-combat-replay silver-bridge-test
ctest --test-dir build/linux-gcc-debug --output-on-failure -R 'silver_search_optimization|silver_bridge_boundary'
```

Result: 2/2 CTest checks passed. The optimization fixture covers flag-off selection parity, root untouched, internal visited-edge selection, eventual unvisited exploration, `CARD_SELECT`, and chance-node exclusions. Replay output includes `first_action_fingerprint`, simulation count, node count, depth sums, search wall time, and all three FPU counters.

## Full 1k DEV screen

All 64 control and 64 FPU rows were accepted. Raw JSONL was retained outside Git:

```text
/tmp/silver_internal_fpu_full_control_1k.jsonl
  SHA-256 c8f0b9990fe234af3ca0a7acddf29f3cd157ffe76c0a4fb63eac150b04c161c1
/tmp/silver_internal_fpu_full_fpu_1k.jsonl
  SHA-256 a1aa2d9080545840afa2f4be5fc2c0d6cad3865497943d97622acd675fe927c8
```

| arm | wins/64 | simulations | nodes | depth sum | chance depth sum | search wall ms |
|---|---:|---:|---:|---:|---:|---:|
| control | 51 | 2,232,000 | 2,063,754 | 12,899,741 | 3,020,027 | 120,741.260 |
| FPU | 50 | 2,172,000 | 1,968,300 | 14,346,649 | 3,363,308 | 114,860.274 |

FPU mechanism totals: 2,697,841 opportunities; 2,433,339 visited-edge selections with an unvisited edge remaining; 264,502 unvisited selections. Primary root actions agreed in 42/64 cases. Changed case IDs:

```text
12100003/20  12100007/17  12100009/22  12100013/20  12100013/25
12100017/21  12100019/23  12100020/17  12100020/21  12100025/21
12100027/18  12100027/20  12100029/5   12100032/13  12100035/18
12100036/16  12100036/21  12100037/22  12100037/28  12100048/26
12100052/14
```

## 10k smoke

The mandated 8-case mechanism smoke completed cleanly for both arms. Raw outputs:

```text
/tmp/silver_internal_fpu_smoke_control_10k.jsonl
  SHA-256 86e248ee42d9eafd7f40c9b2b25713b536ccd24af237c3f55cf6272cc528dd45
/tmp/silver_internal_fpu_smoke_fpu_10k.jsonl
  SHA-256 d82db0bb28266ef9a1d7d4dec98b26d2c420be6125e66f2ee471e2e5126a132a
```

Both arms were 7/8 wins and 8/8 accepted. Control/FPU root actions agreed 8/8. FPU totals were 4,575,821 opportunities, 4,108,545 visited selections with unvisited edges remaining, and 467,276 unvisited selections. FPU used 2,708,398 nodes versus control's 2,609,631, with search wall time 181,198.364 ms versus 176,349.130 ms; depth sum was 26,313,372 versus 21,287,136.

## Execution boundary and decision

The full 64-case 10k arm was not completed. A one-shot multi-case process and the managed seed-guard/process-substitution wrapper intermittently terminated without rows after the clean smoke; independently retried single cases completed (for example, case `12100009/26` in 31.55 s, 270.8 MB RSS, status 0). No partial high-budget rows are admitted as cohort evidence.

Classification: **`INTERNAL_FPU_INCONCLUSIVE`**.

The 1k screen materially exercises the mechanism and shows deeper trees with slightly fewer nodes/wall time but one fewer win and 42/64 root-action agreement. The 8-case 10k smoke is neutral on wins, with higher node count, depth, and wall time for FPU. Because the required full 10k DEV arm was not completed, this does not support promotion or a rejection claim about larger-budget tails. No coefficient tuning, holdout run, gameplay qualification, or default promotion was performed.

Knowledge impact: durable inconclusive Silver allocation result and replay telemetry contract; no production/default behavior changed.
