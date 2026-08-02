# StS AI project guidance

Last verified: 2026-08-02 against the current working tree.

## Purpose and required reading

This repository builds an inspectable Ironclad agent for *Slay the Spire* on
the `sts_lightspeed` C++ simulator. Combat is controlled by C++ tree search;
run-level choices combine C++ policy code, learned models, and experimental
counterfactual evaluators. The active integration executable is `one_combat`
(`apps/one_combat.cpp::main`).

Before changing a subsystem, read the
[knowledge-base index](docs/knowledge-base/README.md) and its linked page.
Current benchmark qualification lives only in
[`evaluation/current-baselines.md`](docs/knowledge-base/evaluation/current-baselines.md).
Chronological experiment evidence and decisions live in `EXPERIMENTS.md`.
Decisions made during agent sessions are logged in the
[decision log](docs/knowledge-base/decision-log/README.md); check its recent
entries for context before acting. Dated plans under `docs/archive/` are not
current instructions.

## Authoritative sources

1. Executed code and executable behavior are authoritative for implementation.
2. Tests and reproducible benchmark artifacts are authoritative for verified
   behavior within their stated configuration.
3. `CMakeLists.txt` is authoritative for the current CMake target graph.
4. `selfplay/loop.sh` is authoritative for loop and gate mechanics;
   `selfplay/config.env` and `selfplay/state.env` are snapshots.
5. `EXPERIMENTS.md` is authoritative for recorded experimental evidence, but a
   dated interpretation may be superseded or incompletely reproducible.
6. `docs/knowledge-base/` owns stable current understanding. It explains costly
   relationships but never overrides code or tests.
7. `README.md` is human-facing orientation, not a technical specification.

When sources disagree, follow the higher source and update the stale knowledge
base in the same change. Do not invent rationale; use **Inference**,
**Unverified**, or **Open question**.

## Repository map

| Path | Responsibility |
| --- | --- |
| `include/`, `src/` | C++ simulator, combat engine, agents, search, native inference. |
| `apps/` | Executables; `one_combat.cpp` is the research integration driver. |
| `bindings/` | Run-level pybind11 API, not card-by-card combat control. |
| root `train_*.py`, `export_*.py`, `v_server.py` | Training, export, optional Python inference. |
| `selfplay/` | Generation, retraining, paired gates, snapshots, local state. |
| `build/` | Mixed ignored build output and tracked model artifacts; some are default, others experimental. |
| `docs/knowledge-base/` | Maintained technical knowledge. |
| `EXPERIMENTS.md` | Chronological experiment ledger. |

## Build and focused checks

Training convention: root trainers default to CUDA when available
(`train_strategic.py` prints `device: cuda` at startup; `STRAT_DEVICE=cpu`
forces CPU, `STRAT_DEVICE=cuda` forces GPU). Never start a trainer on CPU by
default — a CPU run on the 134k-row strategic dataset takes many minutes and is
not the intended path on this machine (RTX 3060 Ti). Check the startup
`device:` line before assuming a run is progressing; trainers print epoch
progress only every 10 epochs.

The configured project uses C++17 and global GNU-style OpenMP flags:

```bash
cmake -S . -B build
cmake --build build -j
```

Declared targets are `slaythespire` (built only when CPython development
headers are found), `main`, `one_combat`, `test` (target `unit-test` with
`OUTPUT_NAME test`; the name is reserved by CTest), `small-test`, and
`parity_test`. CTest entries are registered; `ctest` runs the cheap checks.
The `test` binary is a command dispatcher; with no arguments it is only a
launch/argument smoke check.

Use the cheapest check that proves the change, for example:

```bash
./build/test
STS_FAIR=1 ./build/one_combat bestbench 1000 8 0
ctest --test-dir build --output-on-failure
```

Build the relevant target before using these commands. `json/` and `pybind11/`
are gitlinks; a fresh clone requires `git submodule update --init` before the
first configure.

The current cached build is Linux/WSL Unix Makefiles using `/usr/bin/c++`.
The pybind11 module is skipped with a warning when CPython development headers
are absent; check startup/configure output before assuming `slaythespire`
exists. Do not claim a clean configure or native MSVC build unless you actually
perform it. CMake does not define `build/libsts.a`; do not use old manual
archive-link instructions. More detail:
[`operations/build-and-debugging.md`](docs/knowledge-base/operations/build-and-debugging.md).

## Modification workflow

1. Inspect `git status`; preserve unrelated and ignored experiment data.
2. Read the relevant knowledge-base page and implementation.
3. State the behavioral success criterion and cheapest proving check. State
   assumptions explicitly; when ambiguous, present the interpretations and ask
   rather than picking one silently. If a simpler approach exists, say so.
   When genuinely confused, stop, name what is unclear, and ask.
4. Make the smallest scoped change. No features beyond what was asked, no
   speculative abstractions, no error handling for impossible scenarios.
   Match existing style; do not "improve" adjacent code, comments, or
   formatting; mention unrelated dead code rather than delete it; remove only
   orphans your own change created. Combat control stays in C++ unless the
   binding surface is intentionally extended.
5. Rebuild every translation unit affected by shared header-layout changes.
6. Run focused checks first. For a bug fix, write a reproducing test first when
   feasible. For multi-step tasks, state a brief `step → verify` loop. Use a
   paired project-fair benchmark before making a policy-quality claim.
7. Inspect `git diff`, generated artifacts, paths, symbols, and documentation.

## Critical safety and correctness traps

- Combat loops terminate on `bc.outcome == Outcome::UNDECIDED`; `isBattleOver()`
  is a derived helper equal to `outcome != UNDECIDED`, not an independent flag.
- `STS_FAIR=1` selects the project-fair path, but Searcher2 remains the default
  and randomizes only draw order plus shuffle/card RNG. It is not proof of a
  complete hidden-information model. `STS_SEARCHER3=1` is separate. Searcher3
  samples particles even without `STS_FAIR`; its non-fair path is therefore not
  the same known-RNG regime as non-fair Searcher2.
- Searcher3 particle conditioning and composite seeding are implemented but
  conservative: a reshuffle or insert that contradicts every particle zeroes
  the belief and sample falls back to uniform. See
  [`combat-search.md`](docs/knowledge-base/architecture/combat-search.md)
  and [`determinism-and-rng.md`](docs/knowledge-base/behavior/determinism-and-rng.md).
- `STS_DIST_VNET` and `STS_PVNET` are consumed only by Searcher3. They can print
  successful load messages while default Searcher2 ignores them. `fairgen`
  forces the project-fair Searcher3 regime itself; `STS_FAIR`/`STS_SEARCHER3`
  still gate other modes.
- A model file existing is not evidence it loaded. Verify startup output and
  arm-specific use. The default native floor model is required; a missing
  default policy artifact is silently ignored. The generic native-OOC message
  does not prove the optional win tree loaded; without it, win-rest helpers can
  fall back to server requests.
- Do not treat `bestBench`'s `BEST stack` banner as complete configuration
  provenance; it is emitted from parsed flags and load messages but omits some
  experimental layers.
- Native OOC is the default. `v_server.py` is optional for normal `bestbench`
  but required by some experimental endpoints.
- The self-play meta arm disables native OOC (`STS_NATIVE_OOC=0`) so candidate
  server models own meta decisions; other arms keep native OOC. The loop
  defaults `BIN` to `build/one_combat` (overridable) and refuses to run from an
  inconsistent `state.env` snapshot unless repaired. See
  [`selfplay-loop.md`](docs/knowledge-base/operations/selfplay-loop.md).
- Python bindings do not expose `BattleContext` or `search::Action`.
- `Node`, `Edge`, or searcher layout changes require a clean rebuild of every
  including translation unit; mixed objects are ABI-unsafe.
- Counterfactual `GameContext` copies share `map`; detach before mutation.
- Do not compare project-fair and known-RNG results as one series.
- Compare producer headers with consumers. `paired_analysis.py` validates the
  `bestbench` header before parsing HP/time columns.
- Ignored self-play buffers can be expensive, append/resume-safe, and
  irreproducible. Do not delete them casually.
- Resolve and kill an exact server PID. Never use broad `pkill -f v_server.py`.
- Do not introduce a hand-authored card tier or arbitrary deck-bloat penalty as
  the learning objective without an explicit design change. Existing combat
  policy features already include `Expert` play/obtain weights, so do not claim
  the implementation is free of hand-authored guidance.

## Documentation maintenance

Update the relevant knowledge-base page in the same change whenever code alters
architecture, model interfaces, environment variables, training pipelines,
benchmark protocols, deployed configurations, build commands, important
invariants, RNG behavior, schemas, artifact formats, or a documented
limitation. Every technical page must retain:

- Purpose
- Current implementation
- Important data flow
- Invariants and assumptions
- Relevant code
- Known limitations
- Open questions when applicable
- Last verified date

Substantial claims need repository-relative paths plus a class, function,
executable, test, or script name. Experimental outcomes belong in
`EXPERIMENTS.md`; stable current understanding belongs in
`docs/knowledge-base/`. Update the baseline table only when the recommended
configuration, headline validity, or deployed/experimental status changes.

Create durable decision records in `decisions/` only when repository evidence
contains the rationale. Session-level decisions and new facts belong in the
[decision log](docs/knowledge-base/decision-log/README.md) (see "Decision
logging"). Use investigation notes for reproducible unresolved diagnoses, and
update or close them when evidence changes.

## Decision logging

Every agent session that makes a significant choice appends an entry to the
[decision log](docs/knowledge-base/decision-log/README.md) before the session
closes. Log:

- architecture or design choices, including interfaces, schemas, environment
  variables, and deployed configuration;
- process or tooling choices (commands, tools, workflow conventions);
- notable rejected alternatives, with the reason;
- new facts or corrections to prior understanding.

Entry files are `YYYY-MM-DD-<slug>.md` with date, decision, rationale
(labelled **Inference**, **Unverified**, or **Open question** when unverified),
alternatives considered, evidence, and status. Never rewrite an earlier entry;
append or supersede explicitly. When a logged decision stabilizes and its
rationale is supported by repository evidence, distill it into a `decisions/`
record; stable facts belong in the relevant knowledge-base page in the same
change.

## Experiment-recording rules

Record benchmarked policy/model ideas in `EXPERIMENTS.md`, including negative,
inconclusive, and invalidated results. State the date, executable mode,
environment flags, model paths or hashes, simulation budget, ascension, seeds,
thread count, fair/known-RNG regime, searcher, OOC configuration, metric
formula, output schema, and artifact location. Use paired common seeds.
Clearly separate offline metrics, combat-only results, Act-clear metrics, and
full-run outcomes. Never silently compare fair and known-RNG results.

## Definition of done

A task is done when requested behavior is implemented, focused checks pass (or
their inability to run is reported), model/data schemas still agree, `git diff`
contains only intentional changes with every changed line tracing to the
request and no speculative additions, referenced paths and symbols exist, and
required knowledge-base, decision-log, or experiment-log updates are included.
Policy-quality
work additionally requires a reproducible, correctly labelled paired
evaluation. Documentation work additionally requires link/path checks,
`git diff --check`, stale-phrase review, and inspection of the complete diff.

These guidelines bias toward caution over speed; for trivial tasks (typo
fixes, obvious one-liners) use judgment and do not apply full rigor.

## Prohibited assumptions

Do not assume:

- `outcome` (not `isBattleOver()`) is the canonical combat terminal flag;
- a model loaded because its file exists;
- `v_server.py` is required for default native OOC;
- Python can issue card-by-card combat actions;
- known-RNG results describe honest play;
- comments or old scripts match current CSV producers;
- ignored buffers are disposable;
- CMake creates `build/libsts.a`;
- `runtrace` exactly mirrors `runFullRunOOC`;
- `selfplay/state.env` proves a loop is active or resumable;
- a dated “running now,” “current best,” or model-version claim is still current;
- design rationale can be reconstructed from code shape.

When genuinely uncertain, stop and ask rather than proceeding on an
unverified interpretation.
