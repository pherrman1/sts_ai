# StS AI

StS AI is an experimental, inspectable Ironclad agent for *Slay the Spire*,
built on gamerpuppy's `sts_lightspeed` C++ simulator. Combat decisions are made
by native tree search; choices between combats combine C++ policy code, learned
models, and experimental counterfactual evaluators.

The project is outcome-driven: a hand-authored card tier or arbitrary
deck-bloat rule is not the learning objective, and policy ideas are kept or
rejected by reproducible simulator evidence. Some current combat-policy
features still use hand-authored `Expert` play/obtain weights.

## Architecture at a glance

`GameContext` owns the run and its out-of-combat screens. Entering combat creates
a `BattleContext`; `ScumSearchAgent2` then uses Searcher2 by default or the
opt-in Searcher3 particle search. The active integration executable is
`one_combat`, whose `bestbench`, data-generation, tracing, and evaluator modes
are dispatched by `apps/one_combat.cpp::main`.

The default out-of-combat stack loads native floor and win tree models, uses
rich floor value for card/shop choices, win-shaped rest choices, and heuristic
pathing. A compact policy tree guides combat through PUCT when it loads.
Experimental PVNet and checkpoint/OOC networks are opt-in; they are not part
of the default policy merely because their artifacts exist.

See the [architecture overview](docs/knowledge-base/architecture/overview.md)
for the complete runtime boundary.

## Headline benchmark

The primary recorded project-fair reference is historical, not an exact
reproduction of the current checkout: its raw artifact directory is absent and
the experiment entry does not pin every model path and flag. Older, higher
default-Searcher2 **known-RNG** results must not be compared as honest play.
The result, seed block, current tracked artifact identities, and experimental
comparators live only in the
[current-baselines table](docs/knowledge-base/evaluation/current-baselines.md).
Chronological evidence, including rejected ideas, remains in
[`EXPERIMENTS.md`](EXPERIMENTS.md).

## Quick start

The configured build requires CMake, C++17, OpenMP, and populated `json/` and
`pybind11/` source directories:

```bash
cmake -S . -B build
cmake --build build -j
```

Run a small serverless fair-play smoke benchmark after `one_combat` is built:

```bash
STS_FAIR=1 ./build/one_combat bestbench 1000 8 0
```

Check the startup messages for native OOC and policy-model loads. File presence
alone does not prove a model was used.

**Current checkout limitation:** `.gitmodules` names `json/` and `pybind11/`,
but neither path is represented by a tracked gitlink and both root directories
are absent. A fresh configure from this checkout is therefore unverified and
currently lacks its declared dependency sources. The existing cache is a
Linux/WSL Unix Makefiles build using `/usr/bin/c++`; native PowerShell/MSVC has
not been verified. See [build and debugging](docs/knowledge-base/operations/build-and-debugging.md).

## Repository tour

| Location | Purpose |
| --- | --- |
| `include/`, `src/` | Simulator, combat engine, agents, search, and native inference. |
| `apps/one_combat.cpp` | Active research driver and benchmark/data-generation dispatcher. |
| `bindings/` | Run-level `slaythespire` pybind11 API; it does not expose card-by-card combat actions. |
| `train_*.py`, `export_*.py`, `v_server.py` | Training, export, and optional Python inference. |
| `selfplay/` | Resumable generation/training/gating scripts and local snapshots. |
| `docs/knowledge-base/` | Stable current architecture, operations, evaluation, and invariants. |
| `EXPERIMENTS.md` | Chronological experimental evidence and decisions. |
| `AGENTS.md` | Mandatory coding-agent operating contract. |
| `docs/archive/` | Dated plans and schemas retained for provenance, not current truth. |

## Documentation map

Start at the [knowledge-base index](docs/knowledge-base/README.md). The most
useful deeper pages are:

- [combat search](docs/knowledge-base/architecture/combat-search.md);
- [out-of-combat policy](docs/knowledge-base/architecture/out-of-combat.md);
- [training and inference](docs/knowledge-base/architecture/training-and-inference.md);
- [benchmark protocol](docs/knowledge-base/evaluation/benchmark-protocol.md);
- [self-play loop](docs/knowledge-base/operations/selfplay-loop.md);
- [determinism and RNG](docs/knowledge-base/behavior/determinism-and-rng.md).

Use `STS_FAIR=1` for project-fair claims, compare policies on paired common
seeds, and record meaningful benchmark outcomes—including negative and invalid
results—in `EXPERIMENTS.md`.
