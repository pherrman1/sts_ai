# Native equivalent-copy reroot: paired 128-seed check (2026-09-25)

Question: does rerooting through a different physical copy of an equivalent
card (ADR-0023, issue #327) change native Silver gameplay or cost?

## Configuration

- Control: `main` `0eed6993` (exported with `git archive`, Release build,
  `one_combat_control_release`).
- Treatment: branch `claude/equivalent-copy-reroot` (Release build,
  `one_combat_treatment`). Binary hashes in `binaries.sha256`.
- Both arms, sequential, 4 threads, local:

```bash
STS_SILVER_ADAPTIVE=1 bash tools/seed_guard.sh \
  <binary> bestbench 1000 128 0 126700 <arm>_126700_128.csv
```

A first control run used a build whose configure had cached an empty build
type (unoptimized). Its result rows were identical to the Release control's,
so only its timings were invalid; the Release control replaced it.

## Result (`paired_summary.py`)

| | control (main) | treatment |
|---|---|---|
| Act-3 wins | 86/128 | 89/128 |
| mean floor | 47.42 | 48.11 |
| mean `sec` per run | 38.36 | 39.30 |

Paired difference +2.3 pp, normal 95% CI [−3.2, +7.9] pp; discordant seeds
8 treatment-only, 5 control-only (McNemar z = +0.83). No detectable gameplay
difference; 2.5% more time per run (the reused branches keep larger retained
graphs; the difference is within run-to-run timing noise of this setup).
The control reproduces §354's treatment (86/128, floor 47.42).
