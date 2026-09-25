# Native Silver one-action-root bypass: paired 128-seed check (2026-09-25)

Question: does committing the sole action of a one-action root without search
(forced End Turn, one-option selection) change native Silver gameplay, and
what does it save?

## Configuration

- Source: `claude/native-singleton-bypass` at `8be126a3`. The binary was built
  from `main` `dd8d3c80` plus that commit's C++ changes, before the commit was
  made (identical code).
- Binary SHA-256: `59a51f2f7c6a31920a1a3085d8f2412c74ebf2b16a4e14133c73b0c372a77c75`,
  Release, 4 threads, local.
- Both arms, same binary, sequential:

```bash
# control: one-action roots searched (previous native behavior)
STS_SILVER_ADAPTIVE=1 STS_SILVER_SEARCH_SINGLETON_ROOTS=1 bash tools/seed_guard.sh \
  one_combat bestbench 1000 128 0 126700 control_126700_128.csv
# treatment: one-action roots committed without search (new default)
STS_SILVER_ADAPTIVE=1 bash tools/seed_guard.sh \
  one_combat bestbench 1000 128 0 126700 treatment_126700_128.csv
```

The logs record the backend banner of each arm.

## Result (`paired_summary.py`)

| | control | treatment |
|---|---|---|
| Act-3 wins | 82/128 | 86/128 |
| mean floor | 47.43 | 47.42 |
| mean `sec` per run | 38.58 | 36.09 |

Paired difference +3.1 pp, normal 95% CI [−1.7, +8.0] pp; discordant seeds
7 treatment-only, 3 control-only (McNemar z = +1.26). No detectable gameplay
difference; 6.5% less time per run.

## Interpretation

Skipping the search does not change the committed action. It changes what the
retained graph holds afterwards and the rollout RNG stream, so outcomes
diverge seed by seed; the paired result shows no loss. The saving matches the
vendored bypass's reported 4.6% fewer simulations and 6.7% lower wall time
(§§351–352). The control win count (82/128) sits between §340's 83/128 and
§348's 86/128, within run-to-run spread.
