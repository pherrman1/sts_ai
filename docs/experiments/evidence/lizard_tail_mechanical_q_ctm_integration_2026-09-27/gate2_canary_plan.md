# Gate 2 canary plan (frozen before collection)

## Purpose and hypothesis

This is an eight-pair whole-run integration canary, not a win-rate
qualification. The treatment should exercise the already-qualified active
Lizard correction inside the gameplay-qualified DeepSets plus standard
Attention Brew-fallback stack without introducing invalid state, RNG drift,
support/accounting errors, or a non-Lizard regression. Existing PR #330 and
PR #351 evidence supplies scientific quality qualification; the eight-pair
outcomes are descriptive only.

## Frozen cohort and arms

- Ascension 0, Act 3 horizon, `STS_FORCE_RELIC=LIZARD_TAIL` in both arms.
- Exactly eight paired seeds: `991000` through `991007`; no replacements or
  extensions.
- Each run: 10,000 project-fair native Silver real-combat simulations and
  2,048 OOC MCTS simulations, with the PR #351 confirmation settings below.
- Control: exact DeepSets candidate payload plus standard Attention Brew
  fallback, `STS_OOC_MCTS_ACTIVE_LIZARD=0`.
- Treatment: byte-identical model/fallback/configuration, with
  `STS_OOC_MCTS_ACTIVE_LIZARD=1`.
- Paired execution order: control then treatment for each seed.
- Every seed command is invoked through `tools/seed_guard.sh` and writes fresh
  result, MCTS trace, and combined process-log paths.

The model inputs are frozen by hash:

- Integration candidate artifact:
  `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`.
- Its DeepSets tensor payload:
  `429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`.
- Standard Attention fallback:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Frozen Lizard manifest and q/r artifact are pinned in this packet's
  `native_parity.json` and source manifests.

## Per-run environment

Use a clean environment (`env -i`) with `HOME=/home/philippherrmann` and
`PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. Set the
following common values in both arms:

```text
OMP_NUM_THREADS=24
STS_COLLECT_KEYS=0
STS_FAIR=1
STS_FORCE_RELIC=LIZARD_TAIL
STS_NATIVE_OOC=1
STS_OOC_MCTS=1
STS_OOC_MCTS_COMBAT_MODEL=/tmp/lizard-integration-gate1/deepsets-lizard-candidate.native
STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_except_smoke_v2.native
STS_OOC_MCTS_CPUCT=1.5
STS_OOC_MCTS_EARLY_STOP=1
STS_OOC_MCTS_GAP_STOP_20=0
STS_OOC_MCTS_LEAF_COMBATS=0
STS_OOC_MCTS_LEAF_POLICY=v4
STS_OOC_MCTS_LEAF_VALUE=native
STS_OOC_MCTS_MAX_DEPTH=32
STS_OOC_MCTS_PRIOR=policy
STS_OOC_MCTS_ROOT_SELECTION=visits
STS_OOC_MCTS_SIMS=2048
STS_OOC_MCTS_TEMPERATURE=1
STS_OOC_MCTS_WIDEN_ALPHA=0.5
STS_OOC_MCTS_WIDEN_K=2
STS_OOC_STRATEGIC_BOSS_RELIC=1
STS_OOC_STRATEGIC_EVENT=1
STS_OOC_STRATEGIC_MARGIN=1.0
STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_TREASURE=1
STS_SILVER_ADAPTIVE=0
STS_SILVER_EXACT_ROOT_BUDGETS=1
STS_SILVER_REUSE_CAP=32768
STS_SILVER_REUSE_CAP_MODE=allocated
STS_SILVER_SEARCH=1
STS_SILVER_TELEMETRY=0
STS_SILVER_VNET_LEAF_DIRECT=0
STS_STOP_AFTER_ACT=3
STS_EXECUTABLE_GIT_SHA=<reviewed source commit SHA>
STS_OOC_MCTS_TRACE=<fresh per-run trace path>
```

The historic PR #351 confirmation manifest pinned `STS_SILVER_TELEMETRY=1`.
Current `main` removed that vendored-backend telemetry under ADR-0022 and
rejects any value except the neutral `0`. The first launch preflight caught
this before `bestbench` began: all 16 startup attempts exited before producing
a result row or sidecar. The frozen gameplay environment therefore keeps the
same PR #351 settings with this one current-main compatibility value set to
`0`; no gameplay seed was consumed by the failed startup attempts.

Set only the arm variable differently:

```text
control:   STS_OOC_MCTS_ACTIVE_LIZARD=0
treatment: STS_OOC_MCTS_ACTIVE_LIZARD=1
```

Each invocation uses:

```text
bash tools/seed_guard.sh build/linux-gcc-release/one_combat bestbench 10000 1 0 <seed> <fresh-result.csv>
```

The exact reviewed source commit, binary SHA-256, resolved artifact paths and
hashes, per-seed trace/log/result paths, and complete environment are frozen in
`gate2_frozen_manifest.json` before seed `991000` starts. No collection begins
until the source worktree is clean at that reviewed commit and those hashes
have been verified.

## Decision rules

All 16 processes must exit successfully and produce exactly one complete
bestbench row and sidecar for the requested seed. Logs must identify the
expected model, fallback, fair native Silver budget, OOC budget, and arm flag.
Treatment must report active Lizard preparations and samples. No selected
eligible active-Lizard state may be rejected as `active_unqualified_lizard`;
the explicitly declared Brew/Fairy/Bloom boundaries remain separately visible.
Reject the integration for any impossible Tail state, invalid HP, NaN, runtime
support/accounting failure outside those predeclared boundaries, RNG/state
contract failure, or new non-Lizard support regression. Report outcomes,
floors, runtime, and counters descriptively; eight-seed win-count differences
do not change the promotion decision. A treatment-only obviously pathological
failure pattern returns for review; it never authorizes automatic cohort
expansion.

The Gate 2 report records all 16 outcomes and Lizard invocation/support
counters. Gate 3 proceeds only if all correctness and completion conditions
above pass.
