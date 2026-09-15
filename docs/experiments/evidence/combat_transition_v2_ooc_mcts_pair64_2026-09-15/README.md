# Old V2 versus attention-promoted V2, paired OOC MCTS gameplay

## Design

This prospective test compares the previously tracked near-full V2
combat-transition artifact against the attention-HPO survival promotion. The
old arm is source `cde61c85b8a9ad8500cd3ca6e18607ff33bb6e1a`, binary SHA256
`0d3dc088531d3a435f5f12a3acd03edf4b001f07f28de7d8b090ba741d43d0cb`,
and combat model SHA256
`22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`.
The new arm is frozen source `22765a5549db50e23bb1d09d8c8953ef24b4506f`,
binary SHA256
`84c24b32897a5d2dea4d069ee4b1881f3beb498e672a5a910ea78a4a07fc34d0`,
and promoted model SHA256
`e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.

The arms use the same fresh seeds 12002032--12002095, A0 Ironclad,
project-fair RNG, keys off, Searcher2, Act-3 stop, and exact 10,000-Silver
combat searches. OOC MCTS uses 2,048 simulations, policy prior, temperature
1, cPuct 1.5, widening 2/0.5, depth 32, visit selection, early stop, native
leaf value, no leaf combats, V4 leaf policy, and the full one-ply strategic
gate stack with margin 1. The exact configuration and common model hashes are
in `plan.json` and the four phase receipts. Every gameplay producer was routed
through `tools/seed_guard.sh`; the two 64-seed arms exactly exhaust the local
128-seed ceiling.

The arms, seeds and primary decision rule were fixed before launch. The
primary metric is the paired new-minus-old win-rate delta. Improvement or harm
requires the deterministic 200,000-resample percentile 95% interval to exclude
zero. Floor, final HP and runtime are secondary descriptive metrics.

## Results

| Arm | Wins | Mean floor | Mean final HP | Mean sec/run |
|---|---:|---:|---:|---:|
| Old V2 | 49/64 (76.56%) | 48.5938 | 41.6250 | 158.0474 |
| New attention V2 | 49/64 (76.56%) | 48.7656 | 41.9062 | 164.4165 |

The paired outcome is tied: both win 47, both lose 13, old-only wins 2 and
new-only wins 2. The new-minus-old win delta is 0.0 percentage points with
paired bootstrap 95% interval **[-6.25pp, +6.25pp]**. Therefore this test
establishes neither gameplay improvement nor gameplay harm. Mean floor changes
by +0.1719, mean final HP by +0.2813 and observed mean runtime by +6.3691
seconds (+4.03%); these secondary differences are descriptive and were not
promotion criteria.

All 64 expected seeds occur exactly once in both arms and both producer phases
exit successfully. Old/new telemetry contain 64 rows each. Old records 11,167
OOC decisions, 9,073 MCTS-owned decisions, 2,094 fallbacks, 26 unsupported
combats/support aborts and 1,539 discarded simulations. New records 11,198,
9,089, 2,109, 34 and 1,642 respectively. Every support reason is the expected
`smoke_bomb`; both arms record zero continuation-limit aborts. These differing
counts reflect diverging trajectories and do not imply a support regression.

## Interpretation

The attention-promoted default artifact preserves observed gameplay quality
within the resolution of this 64-pair gate, but the interval still permits a
meaningful loss or gain of 6.25 percentage points. This is bounded online
gameplay evidence for the exact tested OOC MCTS profile, not proof of
equivalence, unbiased planning, or a reason to enable live OOC MCTS by
default. It does not change the separate offline/native qualification.

Run `python3 analyze.py` here to revalidate exact pairing and telemetry and to
regenerate `analysis.json` and `manifest.sha256`. `run.py` is the exact
producer runner and preserves the seed-guard invocation and fail-closed phase
checks; `completion.json` records its zero exit, terminal completion marker and
post-run inventory. Raw results, metadata, support telemetry, guarded receipts
and deterministic compressed logs are preserved alongside the preregistered
plan.

Knowledge impact: adds prospective online gameplay evidence for the promoted
default artifact; no runtime configuration or model artifact changes.
