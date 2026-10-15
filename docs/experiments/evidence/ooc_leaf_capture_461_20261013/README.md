# §461 — A20 observational leaf capture: one-seed collector PASS

The frozen capture-off/on pilot passed on historical seed **87000000**. All
deterministic results and traces matched, including 136 OOC decision profiles
and 54 floor profiles. The collector produced **286 structurally valid samples
from its first 64 roots**, with no input, evaluation or observer errors.
This establishes collector behavior on this seed, not target stability,
learnability, A20 teacher qualification, or gameplay strength.

## Design and custody

- Question: can #507 record genuine internal leaf input/target pairs without
  changing the search that generated them?
- Producer: independently reviewed `252db2a7bbca2641d074ca3c1b05e4f1b852910b`;
  Release binary SHA-256
  `b4586cfc0e26dcae96d3fe14f0c80beccd297cde87bd986fd69954cf126995e1`.
- Teacher: PR #524 / §458 `combo_liz`, data commit
  `c507cebb000cbb308e9ad833721c85ea357af0f1`. FAST4L, STD2 and candidate manifest
  hashes are in [manifest.json](manifest.json), together with V4, public X2-B
  and native floor-model hashes. Its status remains **NOT_QUALIFIED**.
- A20, Act 3/no keys, fair play, exact-10k native Silver, one worker;
  4096 OOC simulations, widening K=4/alpha=.75, three CTM combats, V4
  prior/continuation, native public X2-B bootstrap, eight public futures.
- Both arms explicitly pin `STS_OOC_SHOP_DECK_SIZE_FIX=0`, planner rollout
  shops and `STS_SILVER_LOOP_GUARD=0`. This is current-source parity using
  the §458 CTM and named historical settings, not a historical replication.
- The single intervention is `STS_OOC_MCTS_LEAF_CAPTURE`; profile/trace
  instrumentation is present in both arms. Output paths differ.
- The [protocol](PROTOCOL.md), exact environments/commands, analyzer and
  runner were frozen before launch by [freeze.json](freeze.json), following
  independent review. Limits were 900 CPU / 1200 wall seconds per arm,
  sequentially. No retries, seed substitutions or additional seeds were run.
  This reused seed is diagnostic and cannot be a future holdout.

## Results

Both arms returned zero and passed the existing benchmark canary validator
for the actual backend, source, binary, ascension, seed, worker count and
budget. The analyzer also verified the loaded CTM identity, effective OOC
policy, six artifact hashes, complete deterministic metadata configuration,
and capture/profile association for every recorded root.

Results/MCTS CSVs, decision/action/support traces and profiles matched after
excluding only the preregistered timing fields. Root selected actions, priors,
visits, Q, checkpoints, work counts and abort status remained in the comparison.
Both trajectories died at floor 51; one paired trajectory is not a quality
comparison. Full machine-readable outcome: [report.json](report.json).

| Measurement | Capture off | Capture on |
|---|---:|---:|
| CPU seconds | 267.779914 | 270.934469 |
| Wall seconds | 267.815354 | 270.948831 |
| Completed OOC decision profiles | 136 | 136 |
| Completed floor profiles | 54 | 54 |
| Captured roots / samples | 0 / 0 | 64 / 286 |

Observed CPU ratio: **1.01178** (+1.18%). This is descriptive only: one pair
with the off arm first, alongside an unrelated Debug test process, does not
estimate a stable overhead distribution. Both arms used one worker.
The uncompressed capture is 4,509,533 bytes.

| Initial leaf slice | Samples |
|---|---:|
| Act 1 / Act 2 / Act 3 | 207 / 79 / 0 |
| Map | 112 |
| Rewards | 111 |
| Rest / shop | 18 / 18 |
| Boss relic / treasure | 10 / 8 |
| Event / card select | 6 / 3 |

All initial boundaries were decision screens. Five evaluations ended terminal;
their targets were binary. 285 samples completed three CTM combats; one ended
after one. All 286 targets were finite and within [0,1], and all recorded roots
completed without aborts. The synthetic tests, rather than this seed, exercise
unsupported targets, invalid inputs and aborted-root invalidation.

## Interpretation and next gate

The collector is usable for bounded research on this selected teacher. The
first-64-root prefix is not a representative training corpus, and these rows
cannot establish target noise: each target is one stochastic rollout sample.
No student was trained, no replay/stability study was run and no default changed.

Map leaves are a practical next family to inspect: they account for 112
observations and avoid reconstructing pending reward/selector callbacks.
An exact replay check must retain the original in-memory model/state ID,
pre-evaluation policy state, full initial state/path and copied RNG. Rebuilding
a captured leaf as root zero changes evaluator semantics. Candidate inputs
still omit visible counters and full map topology; complete or explicitly
restrict the selected input contract before treating it as deployable.
After exact same-state/same-RNG replay passes, independently sampled futures
can test target stability in a separately bounded protocol. Public-conditioned
semantics remain #506's distinct qualification question.

## Raw evidence and reproduction

[raw.tar.gz](raw.tar.gz) preserves the frozen runner/analyzer and raw CSVs,
metadata, logs, traces, profiles, leaf observations, receipts and candidate
manifest under their original `build/issue507-pilot/` layout. Per-file hashes
are in [raw.sha256](raw.sha256). Archive SHA-256:
`44c468d301ede6451cc344997359b034ef8ccd0d004f791cf59c9ab48223e17c`.
The executable and native model binaries are not duplicated in the archive.

The complete original local bundle, including its frozen executable and CTM
binaries, is preserved at
`/home/philippherrmann/.codex/worktrees/d8c5/sts_lightspeed/build/issue507-pilot/run`.
At that checkout, analysis is read-only:

```bash
python3 build/issue507-pilot/analyze.py build/issue507-pilot/run
```

Reanalysis elsewhere needs the same layout and frozen executable (the canary
validator verifies its hash); obtain CTM files from the pinned data commit.
Do not overwrite the preserved run or rerun its game commands. The archive
supports raw-data inspection without launching any game seeds.

Knowledge impact: experiment evidence goes to §461; the current #507 status
is updated in the maintained research page. No model or default promotion.
