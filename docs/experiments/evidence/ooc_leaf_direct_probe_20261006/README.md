# Online OOC leaf probe: playout leaf vs direct X2-B (2026-10-06)

Code `a68c0c58` adds research-only `STS_OOC_MCTS_LEAF_VALUE=direct`: an
unresolved non-combat leaf is valued by v_win (X2-B) in place instead of the
bounded policy-chain playout to the next MAP. Everything else is the #379
current-default profile configuration (OOC MCTS 2048 sims, exact 10k Silver,
X2-B selected explicitly, act-3 stop). Frozen plan `plan.json`; extension to
512 pairs authorized by Philipp (`plan-512-amendment.json`). Seeds
47000000..47000511, one bestbench process per seed and arm, 10 workers,
all 1,024 runs exit 0. `analyze.py` reproduces `result.json` from the raw
per-run CSVs (`per-seed.csv`).

| 512 paired seeds | A: playout leaf | B: direct X2-B |
|---|---:|---:|
| win rate | 57.0% | 58.4% |
| mean floor | 46.19 | 46.50 |
| seconds per run | 141.5 | 79.6 |

Paired B-A: wins +1.4 pp (95% bootstrap CI -3.3 to +6.1), floor +0.30
(CI -0.45 to +1.04); discordant wins 71 A-only vs 78 B-only. B uses 0.56x
the time per run.

Inference: no detectable strength cost from dropping the playout at equal
simulations, with a large time saving. The playout leaf's offline NLL
advantage (see #379 evidence) does not show up in play at this sample size.
This is descriptive; no default changes. The natural follow-up is an
equal-CPU comparison that spends B's saved time on more OOC simulations.
