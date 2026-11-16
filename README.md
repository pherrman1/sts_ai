# StS AI

**An AlphaZero-style agent that learns to beat the Heart on Ascension 20 with the
Ironclad in *Slay the Spire*, built on a fast C++ game simulator.**

The goal is a full A20 run, from Neow to the Act-4 Heart, played only from what a
human player can see. Search, learned priors, learned stopping rules and learned
value models make the decisions. Ideas stay or go based on reproducible,
paired, preregistered experiments, and failures are recorded as carefully as
successes.

## Current result

On **1,024 paired A20 seeds** in the simulator, with fair play and full runs to
the Heart:

| Configuration | Heart kill rate | Source |
| --- | ---: | --- |
| PPO-trained out-of-combat policy, combat at the A20 default | 31.64% | ledger §775 |
| Same, with the **Gumbel root search** (16k sims, max backup) in every fight | **41.21%** | ledger §775 (+9.57 pp [+6.64, +12.50]) |
| Same, with a learned playout policy inside the combat search | **43.55%** | ledger §815 (+2.34 pp [−0.10, +4.79], borderline, confirmation pending) |

Brackets are 95% paired confidence intervals. "Fair" means the search never
sees hidden information: no future draw order, no live RNG, no intents hidden by
Runic Dome. These are simulator results, not results in the live game. The
Gumbel configurations are research options that are not yet the executable
default; promoting one needs its own gate. The
[experiment ledger](EXPERIMENTS.md) has the full records, including CPU cost,
seed blocks, binaries and raw data.

## How it works

**Simulator.** The engine is a heavily extended fork of gamerpuppy's
[`sts_lightspeed`](https://github.com/gamerpuppy/sts_lightspeed) C++
simulator, with game-rule fixes and an information-set view of each combat
state, so search only uses public knowledge.

**Combat search (Silver).** Every combat decision is searched by Silver, a
chance-aware Monte Carlo graph search adapted from Daniel Ziegler's
[Silver fork](https://github.com/daniel-ziegler/sts_lightspeed) of
`sts_lightspeed` and extended here:

- a **Monte Carlo graph** with transpositions (equal states share one node) and
  explicit chance nodes for draws and random effects;
- **progressive widening** of chance outcomes (draws, random effects) and of
  end-turn actions, so the stochastic tree stays tractable;
- a **Gumbel root** (Gumbel top-k with sequential halving and max backup), the
  biggest single gain in whole runs (§775);
- learned **policy priors** (small MLPs) at the root and in the tree, guided
  playouts, and a calibrated leaf value;
- a **learned stopping rule** that decides how many simulations a decision is
  worth (ADR-0026, ADR-0051).

**Out-of-combat decisions.** Card rewards, shops, rests, events, relics and the
map are played by learned policies (including a PPO-trained policy network) and
by an **out-of-combat MCTS** that plans across combats with a learned combat
transition model. At A20 this search runs on map screens with a full budget
(ADR-0061).

**The loop.** Search produces better targets than the policy that guided it;
those targets train the next priors and value models, which in turn guide
search. The project's path to a stronger agent runs through this
AlphaZero-like loop rather than through hand-written rules.

The [architecture overview](docs/knowledge-base/architecture/overview.md)
describes the runtime boundaries, and the
[combat search](docs/knowledge-base/architecture/combat-search.md) and
[out-of-combat](docs/knowledge-base/architecture/out-of-combat.md) pages hold
the detailed contracts.

## Research methodology

Each change is treated as an experiment with a falsifiable claim:

- **Preregistration.** Before a campaign runs, a PREREG fixes the question,
  arms, seeds, metrics, decision rule and the exact commit, binary and model
  artifacts. A separate reviewer checks it before launch.
- **Paired A/B on common seeds.** Arms play the same seeds, which removes most
  of the run-to-run variance; a seed guard (`tools/seed_guard.sh`) prevents seed
  reuse across experiments.
- **Sequential gates.** Whole-run gates stop early with an SPRT
  (`tools/sprt_gate.py`, ADR-0064), and a recorded control arm can be reused
  once a sentinel replay confirms it is bit-for-bit valid.
- **A ledger that keeps negative results.** [`EXPERIMENTS.md`](EXPERIMENTS.md)
  indexes over 800 numbered entries, positive, null, negative and invalidated
  alike. Results found to be biased (for example by an exploit or leaked
  information) are marked and rerun, not silently dropped.
- **Architecture decision records.** Every default change is justified in an
  ADR under [`decisions/`](decisions/README.md) and linked to its evidence.
- **Independent review.** Implementation and review are kept separate; every
  nontrivial change is reviewed against its diff, tests and raw evidence.

## Quick start

The build needs CMake (3.21+), a C++20 compiler and OpenMP. It is verified on
Linux and WSL with GCC; native MSVC is not verified.

```bash
git clone https://github.com/pherrman1/sts_ai.git
cd sts_ai
git submodule update --init          # json/ and pybind11/
cmake --preset linux-gcc-release
cmake --build build/linux-gcc-release -j
```

A plain `cmake -S . -B build && cmake --build build -j` works too. Run the core
and smoke tests:

```bash
ctest --test-dir build/linux-gcc-release -L smoke
```

Play a small fair benchmark (1,000 sims per decision, 8 seeds, Ascension 20):

```bash
STS_FAIR=1 ./build/linux-gcc-release/one_combat bestbench 1000 8 20
```

Whole runs default to A20 Ironclad with key collection on, ending at the Heart.
Check the startup messages to see which models were loaded; a model file being
present does not mean it was used. More detail is in
[build and debugging](docs/knowledge-base/operations/build-and-debugging.md)
and the [benchmark protocol](docs/knowledge-base/evaluation/benchmark-protocol.md).

## Repository layout

| Location | Contents |
| --- | --- |
| `include/`, `src/` | Simulator, combat engine, Silver search, out-of-combat agents, native inference. |
| `apps/one_combat.cpp` | Main research driver: benchmarks, whole runs, data generation, tracing. |
| `bindings/` | Run-level `slaythespire` pybind11 API. |
| `train_*.py`, `export_*.py` | Training and export of priors, value models and policies. |
| `models/` | Tracked model artifacts used by the executable. |
| `tools/` | Experiment tooling: campaign workers, gates, seed guard, analysis. |
| `tests/` | C++ and Python tests (run through `ctest`). |
| `docs/knowledge-base/` | Maintained reference: architecture, operations, evaluation, invariants. |
| `docs/experiments/` | Ledger shards and per-experiment evidence (PREREG, RESULT, raw data). |
| `decisions/` | Architecture decision records. |
| `AGENTS.md` | Operating contract for coding agents working in this repository. |

## Documentation

Start at the [knowledge-base index](docs/knowledge-base/README.md). Good next
stops:

- [Current research status](docs/knowledge-base/evaluation/current-research.md)
- [Combat search](docs/knowledge-base/architecture/combat-search.md)
- [Out-of-combat policy](docs/knowledge-base/architecture/out-of-combat.md)
- [Training and inference](docs/knowledge-base/architecture/training-and-inference.md)
- [Benchmark protocol](docs/knowledge-base/evaluation/benchmark-protocol.md)
- [Determinism and RNG](docs/knowledge-base/behavior/determinism-and-rng.md)
- [Code map](docs/knowledge-base/CODE_MAP.md)

## License

MIT; see [LICENSE.md](LICENSE.md). Third-party components are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). *Slay the Spire* is a game by
Mega Crit; this project is not affiliated with or endorsed by Mega Crit.
