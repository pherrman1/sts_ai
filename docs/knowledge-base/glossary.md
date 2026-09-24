# Glossary

Last verified: 2026-09-24 for the Searcher3 removal; 2026-09-07 against commit `82dc3772` and the current working tree.

## Purpose

Define only repository-specific terms whose meaning is shared across
architecture, research, evaluation, and operations. Code/API types, search
algorithms, model names, schemas, benchmark commands, and self-play arm names
remain defined by the owning technical pages routed from the
[code map](CODE_MAP.md).

## Project-wide terms

**Counterfactual** — A copied state on which an alternate legal action is
applied before continuation or future-state scoring.

**Known-RNG** — The Searcher2 non-fair regime (the native default when Silver is disabled), where search starts from
the concrete battle RNG and may reuse its tree across committed actions.
Historical non-fair Searcher3 results (Searcher3 was removed by ADR-0019)
sampled particles and must not be labelled known-RNG without qualification.

**Native OOC** — In-process out-of-combat inference, contrasted with inference
served by `v_server.py`. “Native” does not by itself mean default, loaded, used,
or benchmarked.

**OOC** — Out of combat: run-level decisions made between combats.

**Project-fair / fair play** — The evaluation regime selected by `STS_FAIR=1`.
It commits one root combat action before rebuilding search from the next live
decision. Fair Searcher2 only partially determinizes hidden combat state.
Silver search is always fair.

**Teacher** — A search or counterfactual process whose outputs become training
targets. The name describes provenance, not guaranteed expert quality.

## Invariants and assumptions

- Project-fair and known-RNG results are different benchmark regimes.
- The current baseline is owned only by
  [evaluation/current-baselines.md](evaluation/current-baselines.md).
