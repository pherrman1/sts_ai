# #400 Stage 1 evidence: Silver search-parameter heterogeneity screen

Verdict: **`ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED`** under the frozen rule in
[PLAN.md](PLAN.md). See [ledger-06 §369](../../ledger-06.md).

## Provenance

- Code commit `31de6a6d96a752eacd2b919e58ea94d89fc8ff7e` (PR #402). The plan
  commit `8e909402` was docs-only and written before the cohort ran.
- Release `one_combat` SHA-256
  `4eb0df41df02d33f32203e4bf6a7f1066145d26c61be45b2d29e0fd67fe43ff3`,
  frozen copy used for every shard.
- Teacher `native-silver-v4-sp400-31de6a6d` ([teacher.json](teacher.json)):
  exact-10k native Silver, project-fair, V4 gates on, keys off, Ascension 0.
- Environment: [env.sh](env.sh). Launcher: [launch.sh](launch.sh). Four
  shards of 32 seeds on seeds `40000000..40000127`, one CPU each
  (`taskset`, `OMP_NUM_THREADS=1`), all through `tools/seed_guard.sh`, on a
  4-CPU cloud container. Wall time per shard: 162-202 min. Process CPU in total:
  about 11.8 hours.
- An independent review of PR #402 passed before the analysis, with no
  invalidating defect. No shard failed, so no rerun or replacement was needed.

## Files

- `shardK.states.csv`, `shardK.manifest.json` and `shardK.log` are raw
  producer outputs.
- `shardK.arms.csv.gz` is the gzip of the raw `shardK.arms.csv`. The manifest
  hashes refer to the uncompressed file, so gunzip before reproducing.
- `report.json` is the full analysis output.
- `SHA256SUMS` covers everything in this directory.

Reproduce:

```bash
for k in 0 1 2 3; do gunzip -k shard$k.arms.csv.gz; done
python3 tools/analyze_silver_param_screen_400.py shard0 shard1 shard2 shard3 --out report.json
```

## Integrity

- Sources: 128/128 valid and complete.
- Fights captured: 3,380. The control replay reproduced 3,361 of them.
- Exclusions: 19 fights were excluded because the control replay ended in a
  Smoke Bomb escape. One more was excluded because only `c50` escaped there.
- Per-arm invalid rows: control 19, c12 19, c50 20, wa040 19, wa065 19. All of
  them are `escape`.
- Valid paired fights: 3,360, of which 1,679 are DISCOVERY and 1,681 are
  CONFIRMATION.
- The control check compares outcome, terminal HP, post-battle HP and the
  first action. It does not compare the full action sequence.
- CI: Linux GCC is skipped on draft PRs. The local evidence is a Release build,
  7/7 focused ctest, and the 26/26 smoke run.

## Result

The primary result is the adaptive policy minus the best global arm on
CONFIRMATION:

| Quantity | Value |
|---|---|
| Arm picked per cell on DISCOVERY | BOSS-A1 c12, BOSS-A2 c12, BOSS-A3 c50, ELITE-A1 wa065, ELITE-A2 c50, ELITE-A3 wa065, NORMAL-A1 wa065, NORMAL-A2 wa040, NORMAL-A3 control; OTHER cells fell back to global |
| Best global arm (DISCOVERY) | wa065 |
| D = adaptive minus global, signedOutcome per fight | **+0.0044**, 95% CI **[-0.0003, +0.0089]** |
| CPU ratio, adaptive over global | 0.971 |
| Global (wa065) minus control | -0.0032, CI [-0.0074, +0.0012] |

The CI upper bound is below the material threshold of 0.01, so the verdict is
`NOT_JUSTIFIED`.

Descriptive results, all 3,360 fights. Each cell shows the delta against
control with its 95% CI:

| Cell | n | c12 | c50 | wa065 |
|---|---:|---|---|---|
| ALL | 3,360 | -0.004 [-0.007, -0.001] | -0.005 [-0.008, -0.002] | -0.001 [-0.004, +0.002] |
| BOSS-A1 | 128 | +0.038 [+0.006, +0.071] | -0.062 [-0.094, -0.029] | -0.025 [-0.054, +0.002] |
| BOSS-A2 | 124 | +0.017 [-0.027, +0.058] | -0.053 [-0.098, -0.006] | -0.017 [-0.055, +0.018] |
| BOSS-A3 | 119 | -0.047 [-0.093, -0.002] | +0.010 [-0.032, +0.051] | +0.002 [-0.041, +0.049] |
| ELITE-A3 | 254 | -0.023 [-0.040, -0.006] | +0.004 [-0.011, +0.021] | +0.019 [+0.003, +0.035] |

The full per-cell tables, including split, win-rate, potion and CPU columns,
are in `report.json`. Overall CPU ratios against control are c12 0.97,
c50 1.02, wa040 0.95 and wa065 1.03.

## Interpretation

- **Inference:** none of the tested constants beats the current default
  globally. The two exploration arms are slightly worse overall.
- The only directional context pattern is that lower exploration (c12)
  helped the Act-1 boss on the full data. On CONFIRMATION alone that effect
  was +0.027, CI [-0.014, +0.069], so it did not replicate at this size.
- Exploration 50 was clearly worse on Act-1 and Act-2 bosses.
- The gain from choosing constants per context is small, about 0.004
  signedOutcome per fight, or roughly 0.3 HP at 80 max HP. That is below the
  pre-registered materiality threshold.
