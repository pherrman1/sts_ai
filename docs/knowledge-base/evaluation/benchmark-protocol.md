# Benchmark protocol

Last verified: 2026-08-26 against the current working tree
tree (strict deterministic paired analysis + asserting vnettest, §134 audit).

## Purpose

Define how whole-run and combat experiments are executed, compared, recorded,
and qualified so fair-play, known-RNG, default, and experimental results cannot
be confused.

## Current implementation

The primary whole-run command is:

```text
one_combat bestbench <sims> <nSeeds> <asc> [seedOffset] [resultsFile]
```

`apps/one_combat.cpp::bestBench` evaluates `runFullRunOOC` over a seed block.
When `resultsFile` is supplied it appends and flushes this header:

```text
seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec
```

Other modes include combat-only, data-generation, `reprobench`, and `runtrace`.
`runtrace` is a debugging policy and does not exactly mirror `runFullRunOOC`.

`STS_FAIR=1` selects the project-fair combat path. Searcher2 remains default;
`STS_SEARCHER3=1` is an independent opt-in. Without `STS_FAIR=1`, default
Searcher2 uses the concrete battle RNG and produces the known-RNG diagnostic
regime. Searcher3 still samples particles without `STS_FAIR`; that flag changes
its per-decision reconstruction/tree-reuse behavior, so the resulting hybrid
must not be grouped with known-RNG Searcher2.

## Important data flow

1. `main` parses environment flags and prints model/search activation.
2. `bestBench` invokes `runFullRunOOC` on each requested seed, using OpenMP
   outer parallelism for multi-seed runs.
3. Per-seed rows are flushed in completion order, so consumers must align by
   `seed`, not row order. When `resultsFile` is supplied, `bestBench` also
   appends one JSON object per invocation to `<resultsFile>.meta.json`; this
   records the explicit objective, argv, seed block, key-collection setting,
   searcher flags, OOC settings, model paths/load status, and timestamp.
4. Aggregate output reports full-run wins, mean final floor, end HP, per-run
   elapsed time, and wall time.
5. Paired comparisons join candidate and baseline rows on identical seeds.
6. Self-play uses per-seed `floor + 100*WIN_WEIGHT*won`; the checked-in
   `WIN_WEIGHT=0.1` makes a win worth 10 floor units
   (`selfplay/loop.sh::gate_stats`; `selfplay/config.env`).

The `bestBench` banner and adjacent source comment are now emitted from the
parsed configuration (skip threshold, rest/win layer, shop-V, path mode, native
OOC, searcher, threads, model paths). The `.meta.json` JSON-lines sidecar is
machine-readable provenance; use it plus observed load messages rather than the
banner alone.  When `STS_SILVER_SEARCH=1` overrides combat selection, the
sidecar explicitly records `config.effectiveCombatBackend="silver"`, the
effective Silver reuse-cap mode and fixed production cap, pinned Silver SHA,
current executable Git SHA, and any scaling-diagnostic output path.  Native
Searcher2/3 fields still describe configuration, not the effective combat
backend in that override regime.

### Treatment canary before a larger cohort

Before launching a decision-bearing multi-arm GCP cohort, encode its frozen
SHA, executable/artifact hashes, common seed/configuration, required
environment, telemetry expectation, and unique outputs in the strict manifest
described in
[`operations/build-and-debugging.md`](../operations/build-and-debugging.md#decision-bearing-gcp-run-preflight).
Run `manifest-check`, hash-verified transfer where needed, and
`exact-sha-preflight`. Launch each arm with `run-manifest`; this makes a missing
required setting or reused output a pre-seed failure rather than a post-run
discovery.

Before an experimental arm grows beyond its smallest smoke, run one fresh
guarded seed using the exact frozen executable, flags, budget, thread regime,
and output schema intended for the cohort. Use new result, sidecar, and log
paths, then validate the artifacts with:

```bash
python3 tools/agent/check_benchmark_canary.py \
  --results <canary.csv> \
  --meta <canary.csv.meta.json> \
  --log <canary.log> \
  --expect-backend silver \
  --expect-seeds 1 \
  --expect-sims <budget> \
  --expect-seed-lo <seed> \
  --expect-asc 0 \
  --expect-threads 24 \
  --expect-fair \
  --expect-searcher3 \
  --binary <one_combat> \
  --expect-binary-sha256 <frozen-binary-sha256> \
  --expect-silver-reuse-cap-mode allocated
```

The validator does not drive seeds. It requires one non-appended metadata
record, the exact seed block and completed row count, the requested simulation
budget, ascension, thread/fair/searcher configuration, and binary hash, the
effective treatment backend, actual Silver
decision/simulation telemetry, and zero conversion, semantic-resolution,
transaction, and knowledge failures. A failed canary blocks the remaining
cohort; fix or explain the provenance/mechanism failure before spending more
seeds. `--expect-executable-sha` is also available for a Git-backed execution
tree; do not rely on that sidecar field alone on the documented non-Git GCP
rsync checkout. CTest runs the validator's synthetic pass/fail self-test.

## Invariants and assumptions

Every recorded benchmark states, where applicable:

- date;
- executable mode and command;
- seed range or exact seed count;
- ascension;
- combat simulations per decision;
- project-fair or known-RNG mode;
- Searcher2 or Searcher3;
- OOC configuration and behavior flags;
- model paths and preferably hashes plus observed load messages;
- thread count;
- metric definition and whether it is combat-only, Act-clear, offline, or a
  full-run result;
- output schema and artifact location.

Use paired common seeds for policy comparisons. Do not compare project-fair and
known-RNG numbers as if they measure the same agent quality. A different
artifact, default flag, source revision, or missing load message is a different
configuration.

Experimental outcomes belong in `EXPERIMENTS.md`. The concise current table
belongs only in [current-baselines.md](current-baselines.md); other current docs
link to it.

## Gate protocol

`selfplay/loop.sh::gate_stats` computes a normal-theory paired mean interval
`mean ± GATE_Z*SE` at adaptive looks. Promotion is allowed only on the final
hard-cap look; earlier "promote" signals are advisory and downgraded to
`continue` (the multiplicity guard against repeated looks). Equality at the
margin does not promote; a hard-cap inconclusive result is rejected. Meta and
policy normally use `+0.5`; a negative value margin is a latency allowance
honored only when `VALUE_MARGIN_LATENCY=1`, otherwise clamped with a warning.

`GATE_Z=2.58` remains nominal per look, not a proven 99% sequential guarantee,
and hard-cap-only promotion costs power (a promotable candidate always pays the
full seed budget). The meta arm runs server-backed with `STS_NATIVE_OOC=0` so
candidate V_win/rest models own meta decisions; candidate use is evidenced by
env plus server port liveness, not a per-decision query log. See
[`operations/selfplay-loop.md`](../operations/selfplay-loop.md).

## Known limitations

- The primary fair headline lacks its raw directory and exact complete model/flag
  provenance. The 2026-08-02 re-measurement of the current default stack on the
  recorded block (`EXPERIMENTS.md` §68) is a new, correctly labelled result,
  not an exact reproduction of §66i.
- Multi-thread fair-play replay is bit-identical on the current code for
  tested configurations (gcc 13, `-O3`, Linux/WSL; `EXPERIMENTS.md` §69), and
  `tools/verify/check_replay.py` probes repeated-seed CSV equality; other compilers,
  sanitizer builds, and machines are unverified.
- `paired_analysis.py` parses by header and asserts the 10-column `bestbench`
  schema, so producer/consumer drift fails loudly; the assertion covers header
  mismatch, not semantic feature drift. Since 2026-08-07 (§134 audit) it is
  also **strict and deterministic**: pairing is by seed only (never row
  order), duplicate seeds in either CSV and unequal seed sets are hard errors
  by default, bootstrap CIs use one fixed-seed NumPy generator per report
  (identical intervals on repeated analysis of the same inputs), and
  `--allow-partial` is an explicit diagnostic-only escape with a loud warning
  that must never be used for a promotion gate. Self-test:
  `python3 paired_analysis.py --self-test` (CTest `paired_analysis_selftest`).
  Producer side (issue 46): `bestbench` appends without dedup, so a stale
  results file silently doubles rows; since 2026-08-07 the `bestbench` mode
  handler fails loudly when the file already contains any requested seed
  (disjoint batch appends, e.g. self-play gates, are unaffected).
- CTest registers parse/syntax checks (`ctest --test-dir build`); the `test`
  dispatcher holds targeted Searcher3 and terminal-flag checks, and
  `small-test isbattleover` covers the terminal-field derivation. Deeper
  integration invariants remain review-enforced. `tools/verify/vnettest_selftest.py
  --self-test` (CTest `vnettest_selftest`) regression-checks the asserting
  parity path: non-finite native predictions, float-overflow features, and
  out-of-tolerance evidence must exit nonzero, clean parity evidence exit 0.
- `parity_test.py` fails loudly when its binary or checkpoint is missing, but
  real trainer/native parity still requires a produced checkpoint.
- Experiment ledger entries before the current metadata standard do not all pin
  model hashes or artifacts. Preserve them as historical evidence; do not fill
  missing facts by inference.
- `bestBench`'s banner omits some experimental layers; startup load messages
  and the executed branch conditions remain the authoritative configuration
  record.

## Open questions

- What thread/scheduling configuration is required for bit-reproducible fair
  whole-run evaluation?
- Should alpha-spending style boundaries replace hard-cap-only gate promotion?
- Should `bestbench` embed revision, flags, and artifact hashes in a sidecar?

## Relevant code

- `apps/one_combat.cpp::bestBench`, `runFullRunOOC`, `main`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattle`, `playoutBattleFair`
- `src/sim/search/BattleScumSearcher2.cpp::determinize`
- `selfplay/loop.sh::gate_stats`, `run_gate_batch`
- `selfplay/config.env`
- `paired_analysis.py::load`, `paired_report`
- `apps/test.cpp::main`
- `parity_test.py`; `apps/parity_test.cpp`
- `EXPERIMENTS.md`
