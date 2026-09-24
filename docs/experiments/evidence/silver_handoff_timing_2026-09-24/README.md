# Silver handoff timing and adaptive 128-seed baseline (2026-09-24)

Ledger entry: [§340](../../ledger-06.md#340--silver-handoff-timing-and-adaptive-128-seed-baseline-2026-09-24).

## Command

Executable: `build/linux-gcc-release/one_combat` built from clean commit
`2a602f636edfc37c8fbb85ee1ada32bf09724005`. The container had 4 cores.

```
STS_SILVER_ADAPTIVE=1 STS_SILVER_HANDOFF_TIMING=1 \
  bash tools/seed_guard.sh build/linux-gcc-release/one_combat \
  bestbench 1000 128 0 126700 bestbench_adaptive_126700_128.csv
```

The `1000` sims argument has no effect under `STS_SILVER_ADAPTIVE=1`. Adaptive
Silver searches 500 to 10,000 simulations per decision. The other settings
are the ADR-0018 defaults: Silver fair play, reuse cap 32,768 (`allocated`),
native OOC trees, policy prior auto-load, keys skipped, ascension 0.

## Files

| File | SHA256 |
| --- | --- |
| `bestbench_adaptive_126700_128.csv` | `9cd72765fb5a444df7a1afba4522b61c2c8ceff63906b31ebfb13ccfee30fdad` |
| `bestbench_adaptive_126700_128.csv.meta.json` | `18301724e18b325238fb248caf32cff52dda990fff38f5b0aa93f983ee9a292a` |
| `handoff_summary.json` | `104463e05922ed6fc948bef90443d1c00bce829147e57d4e32a8e6716e39c4cb` |
| `silver_handoff_lines.log.gz` (all 3,245 `[silver-handoff]` lines) | `f95383cf89c772d1c2b46c0a439f3e60443900bdab69b8f80f3c0af82ec270f1` |

`zcat silver_handoff_lines.log.gz | python3 tools/analyze_silver_handoff_timing.py`
reproduces `handoff_summary.json` exactly.
