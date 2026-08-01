# 2026-08-02 — Fixed the knowledge-base issue backlog

Date: 2026-08-02
Session/task: Fix the 30 tracked issues with parallel subagents; benchmark issue 02.

## Decision

Fixed 24 of the 30 tracked knowledge-base issues in one working-tree change,
using five parallel file-disjoint subagents plus orchestrator verification:

- Searcher3 correctness (03, 04, 05, 06, 07, 17): explicit composite seeding,
  belief conditioning, draw-order application, PVNet-only priors, canonical
  observation identity, conservative pruning.
- Self-play loop (01, 11, 13, 14, 15, 30): server-backed meta arm, `$BIN` +
  three-branch bootstrap state machine, cache-key provenance, latency-gated
  value margin, hard-cap-only promotion.
- OOC/apps (18, 20, 21, 23): parsed-config banner, trace guards + diagnostic
  header, `v_server.py` schema comments, fairgen self-enables the fair
  Searcher3 regime.
- Python tooling (09, 19, 22): header-parsing + schema assertion in
  `paired_analysis.py`, wired `parity_test`, CTest registration; plus
  `check_replay.py` for issue 10's probe.
- Small fixes (24, 25, 28): derived `isBattleOver()`, BLAS backend printed at
  load, Expert-feature docs already sufficient.
- Issue 08 fixed by the orchestrator after the subagent wave: checked payload
  reads in `OocCheckpointNet::load`.
- Issue 12 (build foundation) fixed first: `json`/`pybind11` restored as
  gitlinks; the pybind11 module is now guarded on Python dev headers so core
  targets build without them.
- Issue 02: measured the current default fair stack on the recorded block →
  **27/128 (21.1%)** (`EXPERIMENTS.md` §68).
- Deferred: 10 (root cause of replay nondeterminism), 16 (PVNet rerun), 26
  (one_combat refactor), 27 (dependency lock), 29 (binding boundary).

## Rationale

- The repository could not build at all (missing deps); the build foundation
  was a hard prerequisite for every C++ fix.
- File-disjoint groups ran in parallel as subagents; a single shared build dir
  plus orchestrator verification avoided build races.
- The recorded §66i 39/128 reference is not reproducible from tracked
  artifacts; the §68 re-measurement is deliberately labelled a new result, not
  a paired comparison.
- The aggressive `isGuaranteedDead` pruning was removed rather than proven
  because its soundness for card-selection states is not established
  (**Inference**: conservative pruning is safer than an unproven aggressive
  predicate).

## Alternatives considered

- Per-agent build dirs for parallel compilation — rejected: ~3x compile cost
  for marginal wall-time gain; orchestrator builds once after merges.
- Alpha-spending for gate multiplicity — rejected: hard-cap-only promotion is
  simpler and directionally conservative (B chose it; recorded in loop.sh).
- Auto-repair for the stale `state.env` snapshot — rejected: would silently
  discard 10 iterations of history; refuse-with-diagnostics instead.

## Evidence

- All 30 issue entries closed/updated in `docs/knowledge-base/issues/`.
- Focused checks pass: `./build/test` subcommands `seed_contract`, `belief`,
  `drawpile`, `obs_identity`, `prune`; `./build/small-test isbattleover`;
  `ctest` 5/5; `bash -n` selfplay scripts; `check_replay.py --self-test`.
- Known-RNG regression identical to pre-fix baseline (50.0%/45.9/20.6 on 8
  seeds); fair Searcher3 and fair Searcher2 runs complete stably.
- `EXPERIMENTS.md` §68; per-seed artifact `build/bench_2026-08-02_default_fair.csv`.
- KB pages updated in the same change: `combat-search.md`, `determinism-and-rng.md`,
  `invariants.md`, `out-of-combat.md`, `benchmark-protocol.md`,
  `build-and-debugging.md`, `selfplay-loop.md`, `training-and-inference.md`,
  `current-baselines.md`; `AGENTS.md` refreshed.

## Status and follow-up

- Implemented in the working tree; **uncommitted** (gitlinks for `json`/
  `pybind11` are staged; the user commits when ready).
- Open follow-ups: issue 10 root cause, issue 16 rerun, issues 26/27/29, and
  the residual open questions recorded per-page (per-decision meta-arm proof,
  PVNet value-only quirk, baseline bundle sidecar).
