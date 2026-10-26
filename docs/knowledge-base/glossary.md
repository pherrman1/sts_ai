# Glossary

Last verified: 2026-09-24 for the Searcher2/3 and self-play removals; 2026-09-07 against commit `82dc3772` and the current working tree.

## Purpose

Define only repository-specific terms whose meaning is shared across
architecture, research, evaluation, and operations. Code/API types, search
algorithms, model names, schemas, benchmark commands, and self-play arm names
remain defined by the owning technical pages routed from the
[code map](CODE_MAP.md).

## Project-wide terms

**Counterfactual** — A copied state on which an alternate legal action is
applied before continuation or future-state scoring.

**Known-RNG** — The historical Searcher2 non-fair regime, where search started
from the concrete battle RNG. It no longer exists in the executable
(ADR-0020), except as the research-only `act4replay` arm
`STS_ACT4REPLAY_COMBAT=known` (ADR-0062). Historical non-fair Searcher3 results sampled particles and must
not be labelled known-RNG without qualification.

**Native OOC** — In-process out-of-combat inference, contrasted with inference
served by `v_server.py`. “Native” does not by itself mean default, loaded, used,
or benchmarked.

**OOC** — Out of combat: run-level decisions made between combats.

**Project-fair / fair play** — The regime in which search sees only visible
information and commits one root combat action before searching again from the
next live decision. All current combat (Silver) is project-fair; `STS_FAIR=1`
is accepted for compatibility.

**Teacher** — A search or counterfactual process whose outputs become training
targets. The name describes provenance, not guaranteed expert quality.

## Invariants and assumptions

- Project-fair and known-RNG results are different benchmark regimes.
- The current baseline is owned only by
  [evaluation/current-baselines.md](evaluation/current-baselines.md).
