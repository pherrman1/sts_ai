# One-seed baseline/PR #183 runtime comparison

Exactly one full run per arm, seed42/Ironclad A0, 512 OOC MCTS simulations,
10,000 exact-root-budget Silver combat simulations, project-fair combat,
copied noncombat RNG, keys OFF, through Act3 boss or death. Old then new,
sequentially on CPU0, OMP1. Same native combat/V4/floor/win/policy artifacts;
no model training or model swap. Existing fixed-root and historical cohort
artifacts do not provide this revision/budget/seed paired whole-run comparison.

Baseline archived executable: `210f347334898e7c2a85b8af0f30dedc4888ea88`.
PR executable: `bea408a1113b8f4cc9c717a0f1b38d5594b80243`.
The PR run includes the sole-root capability gate; the live model remains unsafe.

| Wall-time measurement | Old | New | Reduction |
| --- | ---: | ---: | ---: |
| Full game (`bestbench` per-seed sec) | 62.3369s | 43.8502s | 29.66% (1.422x) |
| OOC MCTS | 44.448824s | 25.900525s | 41.73% (1.716x) |
| Whole process including startup | 62.499248s | 43.991912s | descriptive |

Both died on floor50/Act3, HP0/maxHP85, combat28/encounter55. All common OOC
counters match exactly: 207 decisions, 148 owned/59fallback, 76,792 completed
simulations, 76,815 attempts, 1,016 discarded, 4,497 successful surrogate samples,
23 support aborts, depth9. All28 complete real-Silver telemetry lines match
exactly, including simulation budgets/tree/reuse/health counters. This evidence
does not include per-action traces or full persistent-state fingerprints, so
aggregate matching is not a new claim of complete trajectory/state parity.
New trivial-root bypasses/locked-root stops/saved simulations are all zero.
New preparation count519/edge samples4,520; remaining samples occur in leaves.
Both exit0; loaded model/configuration banners and metadata are captured.

This one seed is descriptive: it supports a measured runtime reduction for
this workload, not an average speedup or a decision-quality conclusion. Order
was not randomized and no repeated runs or gameplay-quality cohort were added.

[Raw packet](live_ooc_mcts_runtime_pair_2026-09-14.json) includes exact guarded
commands, cleaned/shared environment, source/binary/model hashes, process
receipts, both complete stdout logs, CSV results, configuration metadata and
support-reason JSON. Validation checked one row/seed per arm, equal outcomes,
all common non-timing OOC counters, all real combat telemetry, and zero live
shortcut metrics. No implementation/model/support/default change was made.
