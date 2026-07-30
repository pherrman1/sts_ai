# Current experiment state

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

This page is a compact pointer to current recommendations. `EXPERIMENTS.md`
retains the chronological evidence, corrections, and raw artifact references.

## Current documented baseline

The repository's recorded fair-play headline is Ascension 0, native rich floor
and win GBMs for OOC play, policy-guided combat search, and 1,000 combat
simulations: 39/128 wins (30.5%) on seeds 126700--126827
(`README.md`, “Current state”; `EXPERIMENTS.md`, entry 66i;
`apps/one_combat.cpp`, `bestBench` and native model loading in `main`). This is
a recorded benchmark, not a result reproduced during this documentation pass.
Its cited `selfplay/gate/baseline_1000_128/` directory is absent, and entry 66i
describes PUCT/V-combat without pinning every flag or the unavailable combat
model artifact. The seed-block command in AGENTS exercises current defaults but
is not an exact reproduction recipe.

The operating guidance keeps rich floor value for card/shop, win-shaped value
for rest, heuristic pathing, native OOC inference, and policy-guided PUCT
combat (`AGENTS.md`, “Current best known configuration” and “Self-play
operating context”; `apps/one_combat.cpp`, `runFullRunOOC`, native OOC and
policy loading in `main`).

**Discrepancy:** `README.md` “Quick start” still starts `v_server.py`, although
the implementation and later experiment entries make native OOC the serverless
default (`EXPERIMENTS.md`, entries 66g and 66i;
`apps/one_combat.cpp`, `main`). `AGENTS.md` now separates the fair 30.5%
reference from the known-RNG 51.6% history. Treat those results as different
regimes. Also, default `STS_FAIR=1` uses Searcher2 and randomizes only draw
order plus shuffle/card RNG, so “fair” is the project's convention rather than
a complete hidden-state guarantee (`src/sim/search/BattleScumSearcher2.cpp`,
`determinize`).

## Active training/gating configuration

The checked-in self-play snapshot uses 1,000 runs per iteration, 400 deployment
simulations, a 1,000-simulation policy teacher, 600-simulation gates, a maximum
of 500 paired seeds, 99%-style `Z=2.58` bounds, and two-iteration meta/policy
retraining cadence (`selfplay/config.env`, named variables;
`selfplay/loop.sh`, variable initialization and training cadence branches).
Meta and policy use a +0.5 margin; combat value uses -0.5 non-inferiority
(`selfplay/config.env`, `PROMOTE_MARGIN`, `VALUE_MARGIN`).

The bound is `mean +/- 2.58*SE` at each adaptive look; no sequential-look
correction is implemented. `VALUE_MARGIN=-0.5` is applied to every value arm,
although the loop comment describes it as intended only for a latency candidate
(`selfplay/loop.sh`, `gate_stats`, value gate).

`selfplay/state.env` records `ITER=10`, `SEED_OFF=1008002`, and
`RUNS_TOTAL=8002`, but no loop process is running. The core loop buffer,
`current`, candidate, model, log, and gate directories are absent; only the
separate tracked `ooc_buffer/` exists. Since the state file exists, the loop
skips its initialization branch, which also refers to absent
`build/v_combat_fair_trees.txt` and `build/policy_fair_trees_c.txt`. The
snapshot is not runnable bootstrap state (`selfplay/loop.sh`, initialization;
filesystem/process inspection on 2026-07-30).

**Blocking discrepancy:** the meta gate launches candidate V_win/rest server
artifacts while leaving native OOC enabled. `one_combat` then uses fixed native
win trees and disables paired-rest queries, so the current meta gate does not
prove candidate use (`selfplay/loop.sh`, policy environments and
`start_server`; `apps/one_combat.cpp`, native startup and rest queries).

## Documented research direction

The documented redesign consists of a
1,000-simulation combat teacher, decision-focused combat value weighting,
paired rest-vs-smith targets, and two-iteration cadence (`AGENTS.md`,
“Immediate priority”; `train_value_combat.py`, decision ambiguity and encounter
weighting; `selfplay/loop.sh`, `POLICY_SIMS`, retrain cadence and independent
gates). **Open question:** AGENTS calls this “Iteration 12” while the checked-in
state snapshot says iteration 10; current execution state is not established by
the repository alone.

The immediate prerequisite is repairing and validating the meta gate and loop
bootstrap above. The Iteration 12 name is planning context, not an execution
state established by repository artifacts.

The checkpoint-oracle/distilled OOC direction remains experimental. The native
checkpoint network pipeline exists end to end, but the recorded small-data
full-run gate regressed sharply (`apps/ooc_checkpoint_net.h`,
`OocCheckpointNet`; `train_ooc_checkpoint.py`, top-level trainer;
`export_ooc_checkpoint.py`, top-level exporter; `EXPERIMENTS.md`, entries 67
and 67b). It is not the default policy in `apps/one_combat.cpp` `main` unless
`STS_OOC_CHECKPOINT_NN` is set.

## Recent architectural history

The repository has a short visible history beginning with a large simulator/
research import (`da8c902`). Subsequent commits added safe-death pruning and
composite search RNG (`160abaa`), fair-play data generation and schema work
(`dc2414e`, `dde4b29`, `16e4577`), an event-handler overflow fix (`c03a7ef`),
and the joint PVNet design/training/native inference sequence (`858410d`,
`68e0739`, `541f4b4`, `746e50f`). The current battle reset logic in
`BattleContext::init` predates those later commits in the visible history; it
must not be attributed to `c03a7ef` (`git show c03a7ef`;
`src/combat/BattleContext.cpp`, `BattleContext::init`).

**Unverified:** rationale before the initial import cannot be reconstructed from
this repository's visible git history.

## Remaining high-value gaps

- Repair the self-play bootstrap and prove that each meta arm loads and uses its
  own V_win/rest candidate despite native OOC defaults (`selfplay/loop.sh`,
  startup, `start_server`; `apps/one_combat.cpp`, native OOC startup).
- Establish a bit-reproducible whole-run fair-play test and resolve Searcher3
  seed timing (`src/sim/search/BattleScumSearcher3.cpp`, constructor;
  `src/sim/search/ScumSearchAgent2.cpp`, Searcher3 construction sites).
- Repair the current CSV consumer mismatch in `paired_analysis.py` `load`
  against `apps/one_combat.cpp` `bestBench`.
- Make dependency/bootstrap and build instructions agree with `CMakeLists.txt`;
  the json/pybind11 checkout and `libsts.a` story are currently inconsistent.
- Establish trained-model parity for the distribution/PV path; the existing
  `parity_test.py` top-level program documents a missing original checkpoint.
- Pin the exact deployed model/version/configuration associated with each
  headline benchmark rather than relying on path names and load defaults
  (`apps/one_combat.cpp`, `main`; `EXPERIMENTS.md`, entry 66i).
- Make `runtrace` execute or explicitly label the same policy as `bestbench`;
  it currently logs-but-does-not-use some NN decisions and needs a server for
  draft marginals (`apps/one_combat.cpp`, `runTraceRun`, `tr_logDraft`).
- Define and test the `CombatObservation` equality/hash contract and implement
  or remove the no-op belief update (`src/sim/search/CombatObservation.cpp`).

## Relevant code

- `apps/one_combat.cpp` — `main`, `runFullRunOOC`, `bestBench`.
- `selfplay/loop.sh`, `selfplay/config.env`, `selfplay/state.env` — active loop mechanics and snapshots.
- `train_value_combat.py` and `train_policy.py` — current teacher/student training paths.
- `apps/ooc_checkpoint_net.h` and `train_ooc_checkpoint.py` — experimental OOC checkpoint model.
- `src/sim/search/CombatPVNet.cpp` — newest joint native combat model.
- `EXPERIMENTS.md` — entries 66g, 66i, 67, and 67b.
