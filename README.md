# StS AI

This is an experimental AI project for *Slay the Spire*, built on top of
[gamerpuppy's `sts_lightspeed`](https://github.com/gamerpuppy/sts_lightspeed)
simulator. The aim is to build a strong, inspectable Ironclad agent: it plays
combat through search and learns the choices between combats from self-play and
counterfactual experiments.

The project is intentionally outcome-driven. We do not maintain a hand-written
card tier list or deck-bloat rules; a choice should be valuable because it
improves the chance of surviving and winning runs in simulation.

## What is here

The C++ simulator implements the full Ironclad game loop, including combat,
cards, relics, enemies, events, shops, rest sites, maps, and all acts. It is
designed to reproduce game RNG accurately and can also be run interactively in
the console.

On top of that simulator, the project currently has:

- Combat tree search (UCB and policy-guided PUCT), with fair-play
  determinization so hidden future RNG is not treated as known.
- Learned combat values and policy priors to make a limited search budget go
  further.
- Gradient-boosted strategic values for drafting and shops, plus survival- and
  win-oriented values for rest-site decisions.
- A resumable self-play, training, and paired-gating loop, so candidate models
  are compared against the deployed policy on exactly the same seeds.
- Experimental counterfactual tools that ask a more direct question at each
  out-of-combat decision: *how does this deck/state perform against the fights
  it may face next?*

## Current state

The practical baseline is an Ascension 0 Ironclad policy using rich-state
drafting, heuristic map routing, a value-based shop knapsack, a win-rate rest
policy, and policy-guided PUCT combat search. The primary benchmark is now
honest fair play (`STS_FAIR=1`): the current deployed model wins **39/128
runs (30.5%)** at 1,000 combat simulations on the fixed seeds 126700--126827.
The older 51.6%/1,000-simulation figure is a known-RNG result, where simulations
can see future hidden draws, and is retained only as a separate diagnostic.
These are repository-specific benchmarks, not claims about the original game
client.

The newest research direction is evaluating all plausible remaining Act fights
when making a strategic choice. Its score weights likely near-term encounters
more heavily than distant ones and values a safe remaining HP buffer
non-linearly. A card that only helps against a distant boss should therefore not
beat a card that improves common upcoming fights. The direct simulator is
promising but expensive, so its main purpose is to generate better training
targets rather than become the permanent policy by itself.

The detailed evidence, including experiments that did **not** work, lives in
[`EXPERIMENTS.md`](EXPERIMENTS.md). It is the source of truth for decisions
about what is deployed.

## Repository tour

| Location | Purpose |
| --- | --- |
| `apps/one_combat.cpp` | Main experiment driver: combat search, run policy, and strategic counterfactual probes. |
| `src/`, `include/`, `extern/` | The C++ game simulator and dependencies. |
| `train_*.py` | Training scripts for value, policy, and paired-action models. |
| `v_server.py` | Serves Python-trained models to the C++ runner. |
| `selfplay/loop.sh` | Resumable data-generation, training, and gating loop. |
| `selfplay/` | Scripts and local experiment state. Large generated buffers are intentionally git-ignored. |
| `EXPERIMENTS.md` | Canonical experiment log and recommendations. |
| `AGENTS.md` | Project-specific operating notes, evaluation conventions, and safety gotchas. |

## Quick start

You will need a C++17 compiler with OpenMP, Python 3, and the Python packages
used by the training scripts (notably pandas and XGBoost; some experiments use
PyTorch). Clone with submodules, then build the simulator using the project
configuration or your preferred CMake/IDE setup.

```bash
git clone --recurse-submodules git@github.com:pherrman1/sts_ai.git
cd sts_ai
cmake -S . -B build
cmake --build build -j
```

On the current Linux setup, the active experiment executable can be compiled
after the simulator library has been built with:

```bash
g++ -std=c++17 -O2 -w -fopenmp -Iinclude -Iextern \
  apps/one_combat.cpp build/libsts.a -o one_combat.elf
```

Run the model server in one terminal, then launch a small fair-play benchmark in
another:

```bash
python3 v_server.py
```

```bash
STS_FAIR=1 ./one_combat.elf bestbench 1000 32 0
```

The runner prints which models it loaded. Check that output rather than assuming
a benchmark used the intended configuration. The larger reference benchmark is
`bestbench 1000 512 0`; start smaller while developing.

## How we work

The most useful contribution is usually an experiment with a clear causal
question, a small reproducible gate, and a written result. A few conventions
matter:

- Use `STS_FAIR=1` for claims about honest play; known-RNG results are useful
  diagnostics but optimistic.
- Compare policies on paired common seeds. Win rate alone is noisy, so the
  gates also track a dense floor/progress signal and confidence bounds.
- Keep combat control in C++ unless changing the bindings deliberately; Python
  currently owns run-level models, not card-by-card combat actions.
- Do not delete generated self-play buffers casually. They are large,
  append/resume-safe, and expensive to recreate.
- Add meaningful benchmark outcomes to `EXPERIMENTS.md`, including negative
  results. That prevents us from repeating attractive failures.

## Good places to help

The immediate opportunity is making the fight-strength idea cheap enough to
learn from: collect reliable labels from simulated future encounters, train an
amortized model that predicts them, and verify that it improves live
out-of-combat choices. Evaluation infrastructure, simulator correctness,
counterfactual data quality, and reducing search cost are all high-leverage
areas.

If you are new to the codebase, read `AGENTS.md` and the relevant sections of
`EXPERIMENTS.md` before changing a policy. They explain the current baseline,
the conventions behind the numbers, and several traps we have already tested.
