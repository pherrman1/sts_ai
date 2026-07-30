# StS AI project guidance

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Agent operating contract

### Project purpose

This repository builds an inspectable Ironclad agent for *Slay the Spire* on
the `sts_lightspeed` C++ simulator. Combat is controlled by C++ tree search;
run-level choices combine C++ policy code, learned models, and experimental
counterfactual evaluators. The active integration executable is
`one_combat` (`apps/one_combat.cpp`, `main`), and benchmark conclusions belong
in `EXPERIMENTS.md`.

### Repository map

| Path | Responsibility |
| --- | --- |
| `include/`, `src/` | C++ simulator, combat engine, agents, search, and native inference. |
| `apps/` | Executable entry points; `apps/one_combat.cpp` is the active research driver. |
| `bindings/` | The `slaythespire` pybind11 run-level API. |
| `train_*.py`, `export_*.py`, `v_server.py` | Model training, export, and optional Python inference service. |
| `selfplay/` | Resumable data generation, retraining, paired gating, configuration, and local state. |
| `build/` | Build output plus a small set of tracked deployed model artifacts; do not assume every file is generated or every generated file is tracked. |
| `docs/knowledge-base/` | Persistent architecture and operating knowledge; start at `docs/knowledge-base/README.md`. |
| `EXPERIMENTS.md` | Canonical chronological experiment evidence and recommendations. |

### Authoritative sources

1. Executed code and executable behavior are authoritative for implementation.
2. Tests and reproducible benchmark artifacts are authoritative for verified
   behavior, within their stated configuration.
3. `CMakeLists.txt` is authoritative for the current CMake target graph.
4. `selfplay/loop.sh` is authoritative for loop and gate behavior;
   `selfplay/config.env` and `selfplay/state.env` are snapshots, not universal
   defaults.
5. `EXPERIMENTS.md` is authoritative for recorded experimental conclusions,
   but dated claims must be checked against code and artifacts.
6. The knowledge base explains expensive-to-reconstruct relationships. It does
   not override code or tests. If it disagrees with them, update the knowledge
   base in the same change.

### Build and test commands

The configured build uses CMake, C++17, and OpenMP (`CMakeLists.txt`,
`project`, `CMAKE_CXX_STANDARD`, `CMAKE_CXX_FLAGS`):

```bash
cmake -S . -B build
cmake --build build -j
```

The CMake targets are `slaythespire`, `main`, `one_combat`, `test`, and
`small-test` (`CMakeLists.txt`, `pybind11_add_module` and `add_executable`).
There is currently no CTest registration. `test` is a command-dispatch harness
(`apps/test.cpp`, `main`), not an automatic test suite. Use the smallest
relevant manual check, for example:

```bash
./build/test
./build/one_combat speedtest
STS_FAIR=1 ./build/one_combat bestbench 1000 8 0
```

After its target is built, the first command is only an argument/launch smoke
check; the current cached build does not contain `build/test`. The benchmark is
not a unit test and can be expensive. Confirm model-load messages in
`apps/one_combat.cpp` `main`. See
`docs/knowledge-base/architecture/evaluation.md` for evaluation conventions.

**Unverified:** a fresh configure depends on populated `json/` and `pybind11/`
directories, while those paths are not tracked as gitlinks in this checkout.
The existing `build/CMakeCache.txt` is a Linux/WSL Unix Makefiles configuration
using `/usr/bin/c++`; the commands above are not verified as native PowerShell/
MSVC commands. Do not report a clean build unless you actually performed one
in the environment being reported.

### Modification workflow

1. Inspect `git status` and preserve unrelated working-tree changes.
2. Read the relevant knowledge-base pages and the corresponding implementation.
3. State the behavioral success criterion and the cheapest check that proves it.
4. Make surgical changes; combat control stays in C++ unless the binding
   surface is intentionally extended.
5. Rebuild every translation unit affected by shared header-layout changes.
6. Run focused checks first, then a fair, paired benchmark when making a policy
   quality claim.
7. Inspect `git diff`, verify generated artifacts are intentional, and update
   documentation required by the rules below.

### Documentation update rules

Update `docs/knowledge-base/` in the same change when code alters a documented
entry point, data flow, state boundary, RNG rule, invariant, model schema,
artifact format, evaluation protocol, or known discrepancy. Every technical
page must retain a `Last verified` field and a `Relevant code` section. Attach
repository-relative file and symbol provenance to substantial claims. Use the
literal labels **Inference**, **Unverified**, and **Open question** when the
repository does not directly establish a fact.

Add a decision note under `docs/knowledge-base/decisions/` only for a decision
whose rationale is present in repository evidence; never reconstruct rationale
from the outcome. Add an investigation note under
`docs/knowledge-base/investigations/` for a reproducible unresolved diagnosis,
and update or close it when evidence changes.

### Experiment-recording rules

Record benchmarked policy/model ideas in `EXPERIMENTS.md`, including negative
and invalidated results. State the exact executable mode, environment flags,
model paths, simulation budget, ascension, seeds, fair/known-RNG mode, output
schema, and artifact location. Use paired common seeds for comparisons.
Clearly separate an offline metric from a full-run result, and never silently
compare fair-play results with known-RNG results.

Update `docs/knowledge-base/experiments/current-state.md` only when the
recommended baseline, active investigation, gate protocol, or validity of a
headline result changes. The chronological detail remains in
`EXPERIMENTS.md`.

### Definition of done

A task is done when requested behavior is implemented, focused checks pass (or
their inability to run is reported), relevant model/data schemas still match,
`git diff` contains only intentional changes, referenced paths and symbols
exist, and required knowledge-base or experiment-log updates are included.
Policy-quality work additionally needs a correctly labelled fair/known-RNG
evaluation with reproducible configuration.

### Prohibited assumptions

- Do not assume `bc.isBattleOver` is the combat-loop terminal condition; use
  `bc.outcome == Outcome::UNDECIDED`.
- Do not assume a model loaded because its file exists; verify runtime output.
- Do not assume `v_server.py` is required: native OOC inference is the current
  default in `apps/one_combat.cpp` `main`.
- Do not assume Python can issue card-by-card combat actions; the binding module
  does not expose `BattleContext` or `search::Action`.
- Do not assume known-RNG results describe honest play.
- Do not assume CSV columns from comments or older scripts match current
  producers; compare producer headers with consumers.
- Do not assume ignored self-play buffers are disposable or reproducible.
- Do not assume a documented `build/libsts.a` target exists in CMake.
- Do not invent design rationale. Record an **Open question** instead.

## Project and architecture

- This project builds an AI for Slay the Spire on gamerpuppy's `sts_lightspeed` C++ simulator.
- The active experimental driver is `apps/one_combat.cpp`; the canonical experiment log is `EXPERIMENTS.md`. Update the log whenever a benchmarked idea changes the evidence or recommendation.
- Combat control (`BattleContext`, `search::Action`, card/target/end-turn decisions) is C++-only. The Python bindings expose strategic/run-level APIs, not step-by-step combat control. Prefer C++ for combat MCTS unless the task explicitly extends `bindings/slaythespire.cpp`.
- No repository dependency lock or environment definition exists. `../.venv`
  is absent in this checkout and in the current default WSL environment. The
  training scripts import pandas, NumPy, XGBoost, scikit-learn, and, for neural
  experiments, PyTorch.

## Current best known configuration (ascension 0)

- Use RICH V2 drafting with card skip threshold `-0.5`, heuristic pathing, shop-V knapsack, win-rate rest policy, and policy-guided PUCT combat.
- Native deployment attempts to load `build/v_rich_trees.txt`,
  `build/v_win_trees.txt`, and `build/policy_trees_c.txt`; the floor model is
  required, while a missing default policy model is silently ignored. PUCT
  defaults to `c_puct=2.5` when a policy/PV model actually loads. Set
  `STS_POLICY=0` only for a deliberate UCB comparison.
- The primary recorded project-fair reference is 39/128 wins (30.5%) at
  1,000 combat sims on seeds 126700--126827. The raw artifact directory cited
  by `EXPERIMENTS.md` is absent, the entry does not pin every model path/flag,
  and it describes a V-combat stack whose exact artifact is unavailable. The
  older 51.6%/1,000-sim and 62.3%/3,000-sim figures are known-RNG results.
  Historical data directly shows PUCT below UCB at 20,000 sims; the claimed
  6,000--10,000 crossover is an interpretation without paired UCB points there.
- `STS_FAIR=1 ./build/one_combat bestbench 1000 128 0 126700` exercises the
  current defaults on the recorded seed block; it is not an exact reproduction
  command for the historical 39/128 result. Native OOC needs no server for
  `bestbench`. Validate every model-load message.

## Immediate priority: repair and then evaluate the stronger-teacher redesign

- The loop implements independent meta/value/policy arms, paired common seeds,
  a dense `floor + 10*win` score under the checked-in `WIN_WEIGHT`, adaptive
  looks up to 500 seeds, and no tie promotion. Its `Z=2.58` intervals are
  nominal normal-theory bounds; repeated looks are not multiplicity-adjusted.
- **Blocking discrepancy:** `selfplay/loop.sh` starts `v_server.py` with the
  candidate V_win/rest artifacts, but `one_combat` defaults
  `STS_NATIVE_OOC=1`. Native rest/card/shop inference then uses the fixed
  `build/v_win_trees.txt` and bypasses the candidate server, and paired-rest
  inference is disabled. Do not treat a meta gate or promotion as valid until
  the arm-specific model is demonstrably loaded and exercised.
- The stronger-teacher pieces exist: a 1,000-sim combat teacher,
  decision-focused combat-value weighting, paired rest-vs-smith targets, and
  two-iteration defaults for meta/value/policy retraining. Iteration 12 is only
  a planning label in this guidance, not an execution state established by
  code or artifacts.
- `selfplay/state.env` records iteration 10, but the loop's ignored `current/`,
  buffer, candidate, log, and gate directories are absent. Because the state
  file exists, the initialization branch that populates `current/` is skipped.
  It also names `build/v_combat_fair_trees.txt` and
  `build/policy_fair_trees_c.txt`, neither of which exists in this checkout.
- The snapshot uses 400 deployment sims and 600 gate sims. Meta and policy use
  a +0.5 lower-bound margin. `VALUE_MARGIN=-0.5` is applied to every value
  candidate; the comment calls it latency-oriented, but the code does not
  enforce a latency condition.
- Keep V_floor for card/shop and V_win/paired action values for rest. Prior unified V_win
  card/shop ablations were clear regressions; those decisions need paired/ranking targets before
  another promotion attempt.

## Self-play operating context

- The resumable loop is `selfplay/loop.sh`; dashboard is
  `watch -n2 selfplay/status.sh` in Bash. The loop invokes
  `./one_combat.elf`, not `build/one_combat`, and always launches a Python
  server for its arms. Repair its executable, model, state, marker, and buffer
  preconditions before launch.
- The loop is intended to train and independently gate meta `V_win` + paired
  rest action value, combat value, and policy prior. The meta arm is currently
  bypassed by native OOC as described above. The deployed hybrid keeps V_floor
  for card/shop and uses win-shaped rest policy.
- Keep heuristic pathing while the active `V_win` is forward-map-feature-blind. Enabling `STS_PATH_V` with the old model caused a catastrophic regression. Model-driven events were a wash.
- The snapshot sets `POLICY_WINDOW=1`. **Unverified:** comments in
  `selfplay/loop.sh` estimate larger policy windows at tens of GB, but the
  claimed local 31 GB failure threshold and terminal-specific advice were not
  reproduced in this workspace.
- Do not delete large buffers casually: datagen is append/resume-safe, and a failed training read does not imply data loss. Raw iteration CSVs are not automatically pruned.
- The user does not want hand-authored expert-tier priors or arbitrary deck-bloat penalties in the self-play solution; the model should learn these effects from outcomes.

## Experimental conclusions to preserve

- `EXPERIMENTS.md` records deckbuilding/OOC policy as a repeated whole-run
  bottleneck, rich state value as a drafting improvement, and win-probability
  value as better for rest/survival decisions. These are dated benchmark
  conclusions, not implementation invariants.
- The recorded DeepSets run tied the GBM near 0.75 AUC and did not improve its
  tested full-run gate. That comparison does not prove a data/label ceiling; it
  only fails to support increasing capacity as the next step.
- Dynamic potion saving/hoarding hurt win rate in both known-RNG and fair-play tests. Potion use itself is active; boss deaths are not evidence of potion hoarding.
- Depth-capped combat rollouts with the tested leaf value produced a recorded
  turtle equilibrium and hangs. The current default is uncapped. Rewarding
  enemy-HP progress is a proposed remedy, not a verified sufficient condition.
- Known-RNG combat results are historically optimistic. Use `STS_FAIR=1` for
  the project's fair-play convention and label the regime. Default fair
  Searcher2 randomizes draw order plus shuffle/card RNG only; it is not a
  demonstrated complete hidden-information model.
- Common-random-number rollout drafting was too noisy/expensive online. Prefer amortized learned value functions for drafting.

## Build and safety gotchas

- Use C++17 and OpenMP. The existing CMake cache is a Linux/WSL build using
  `/usr/bin/c++`; `CMakeLists.txt` supplies GNU-style `-fopenmp` globally and
  has not been verified with native MSVC. `selfplay/loop.sh` defaults
  `OMP_NUM_THREADS=12`; that is a loop default, not a benchmarked optimum.
- `BattleContext` combat loops must check
  `bc.outcome == Outcome::UNDECIDED`. In the current implementation
  `isBattleOver` is reset and read but never assigned `true`, so it is not a
  terminal flag.
- If changing layouts in `Node`, `Edge`, or the searcher, recompile every translation unit that includes those headers to avoid ABI/stack corruption.
- Current CMake does not define `build/libsts.a`. Use a clean CMake rebuild after shared-header layout changes; do not mix objects compiled against different `Node`, `Edge`, or searcher layouts.
- Never use `pkill -f v_server.py` or similar broad patterns: they can kill the launching shell. Resolve and kill the exact PID.

## Detailed migrated context

- **Unverified:** historical guidance names
  `~/.codex/imports/claude/sts/memory/`, but `MEMORY.md` is absent in the
  current host and default WSL environments. Do not rely on those notes unless
  the path is restored and inspected.
- Treat dated “running now” statements as historical snapshots. Verify processes, files, model versions, metrics, and line numbers against the workspace before acting.

## Native OOC checkpoint model

- `apps/ooc_checkpoint_net.h`: compact MLP inference (GELU, Linear,
  LayerNorm implemented from scratch). Binary weights are exported by
  `export_ooc_checkpoint.py`. In `runFullRunOOC`, a successfully loaded
  `STS_OOC_CHECKPOINT_NN=<path>` precedes the ordinary policy for legal OOC
  decisions in acts 1--3; it does not cover states outside that act range.
- `train_ooc_checkpoint.py`: trains the model from teacher CSV (checkpoint oracle traces). Predicts meanUtility directly from (state, action bits, screen, act).
- `export_ooc_checkpoint.py`: writes the roughly 1.25 MB binary and performs 32
  synthetic parity samples against the checkpoint loaded in that run. The
  historical log reports about 0.001 maximum error. `OocCheckpointNet::load`
  checks the header and dimensions but not each payload read, so a truncated
  file can still set `ok=true`.

## Run tracing (`runtrace` mode)

- `./build/one_combat runtrace <seed> <sims> <asc>` — per-node human-readable trace of one seed.
- With `STS_OOC_CHECKPOINT_NN=<path>`, `runtrace` prints scores on several OOC
  screens, but it does not mirror `runFullRunOOC`: event and treasure actions
  are logged then executed by the base policy, and boss-relic/other fallthrough
  screens are not scored. Draft logging also queries the server-only `M`
  endpoint and can retry for about five seconds when no server is running.
- Output format per screen:
  - **Draft:** `card_name(V:+marginal NN:score)` per card, `NN: skip=score picks SKIP/CARD [DISAGREE]`
  - **Rest:** `HEAL = score`, `smith:CardName = score`, `DIG/LIFT/TOKE = score`
  - **Upgrade selection:** `[NN upgrade] #N = score` for each legal target
  - **Map/shop/event/treasure:** `[NN <screen>] #N = score`
- Env flags: `STS_STOP_AFTER_ACT=N` to stop after act N; `STS_REFIGHT_FLOOR=N STS_REFIGHT_N=K` to re-fight a specific combat K times.

## Checkpoint oracle (all-OOC combat-strength evaluator)

- Env: `STS_ACT_FIGHT_PROBE_ALL_OOC=1`. In acts 1--3 it scores legal OOC
  actions by simulating or predicting upcoming combats at reached checkpoints,
  weighted by the evaluator's encounter distribution.
- **Unverified historical result (EXPERIMENTS §67b):** `STS_VNET=<native-combat-tree-model> STS_VNET_ALPHA=0.3 STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=50,25,10` used a combat value leaf to make 50/25/10-sim checkpoint MCTS 46× faster than the original §66 oracle and recorded 87.5% versus 50.0% Act-1 clear. The exact model file named in that entry is not present in this checkout.
- Teacher collection: add `STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv` for durable per-action rows.

## Karpathy Guidelines for LLM Coding

### 1. Think Before Coding
- State assumptions explicitly — if uncertain, ask rather than guess.
- Present multiple interpretations when ambiguity exists, don't pick silently.
- Surface tradeoffs; push back when a simpler approach exists.
- Stop when confused — name what's unclear and ask.

### 2. Simplicity First
- Minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked, no abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- If 200 lines could be 50, rewrite it.
- **Test:** Would a senior engineer say this is overcomplicated?

### 3. Surgical Changes
- Touch only what you must. Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken. Match existing style.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
- **Test:** Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
- Define success criteria before starting. Loop until verified.
- Transform "add validation" → "write tests for invalid inputs, then make them pass".
- For multi-step tasks, state: `1. [Step] → verify: [check]`.
- LLMs are good at looping until they meet specific goals — give them verifiable targets.
