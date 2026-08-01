# Benchmark protocol

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

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
   `seed`, not row order.
4. Aggregate output reports full-run wins, mean final floor, end HP, per-run
   elapsed time, and wall time.
5. Paired comparisons join candidate and baseline rows on identical seeds.
6. Self-play uses per-seed `floor + 100*WIN_WEIGHT*won`; the checked-in
   `WIN_WEIGHT=0.1` makes a win worth 10 floor units
   (`selfplay/loop.sh::gate_stats`; `selfplay/config.env`).

The `bestBench` source comment and its `BEST stack` banner are stale and
incomplete: they still describe a server-backed stack, an old skip default, and
optional `restV`, while startup currently defaults to native OOC, skip `-0.5`,
and separate win-rest via `g_restWin=true`. Use parsed flags, load messages, and
the executed branch conditions rather than that banner alone.

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
`mean ± GATE_Z*SE` at adaptive looks. Promotion requires the lower bound to
strictly exceed the arm margin; equality at the margin does not promote; a
hard-cap inconclusive result is rejected. Meta and policy normally use `+0.5`;
the checked-in value snapshot uses `-0.5`, so a sufficiently precise zero-delta
value candidate can qualify.

The repeated looks are not multiplicity-adjusted, so `GATE_Z=2.58` is not a
proven 99% sequential guarantee. In addition, the current meta arm is invalid
because native OOC bypasses its candidate server models. See
[`operations/selfplay-loop.md`](../operations/selfplay-loop.md).

## Known limitations

- The primary fair headline lacks its raw directory and exact complete model/flag
  provenance. Re-running the seed block with current defaults is a new result,
  not an exact reproduction.
- Multi-thread fair-play results have historically failed bit-identical replay;
  no automated whole-run reproducibility test exists.
- `paired_analysis.py::load` reads zero-based column 3 as HP and column 4 as
  seconds, but the current producer stores `act` and `hpEnd` there; seconds is
  column 9. Win and floor still align, HP/timing do not.
- CMake registers no CTest tests; `apps/test.cpp::main` is a manual dispatcher.
- `parity_test.py` is not a valid trained-model parity test as written.
- Experiment ledger entries before the current metadata standard do not all pin
  model hashes or artifacts. Preserve them as historical evidence; do not fill
  missing facts by inference.
- `bestBench`'s own descriptive comment/banner does not fully identify the
  policy that `runFullRunOOC` executes.

## Open questions

- What thread/scheduling configuration is required for bit-reproducible fair
  whole-run evaluation?
- Should gate intervals use a sequentially valid method?
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
