# StS AI knowledge base

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

This is the durable orientation layer for coding agents. It records
relationships and hazards that are costly to rediscover, while code and tests
remain authoritative. The CMake target graph is defined in `CMakeLists.txt`;
the active research executable dispatches from `apps/one_combat.cpp` `main`;
and chronological experimental evidence is recorded in `EXPERIMENTS.md`.

## Reading order

1. [Architecture overview](architecture/overview.md)
2. [Combat system](architecture/combat-system.md) or
   [strategic system](architecture/strategic-system.md)
3. [Training and inference](architecture/training-and-inference.md)
4. [Determinism and RNG](behavior/determinism-and-rng.md) and
   [invariants](behavior/invariants.md)
5. [Evaluation](architecture/evaluation.md) and
   [current experiment state](experiments/current-state.md)

The [component index](components/README.md) identifies ownership boundaries.
The [glossary](glossary.md) defines repository-specific terms. Decision and
investigation directories contain templates and maintenance rules; an empty
index means no qualifying durable record has been extracted yet.

## Evidence labels

- An unlabelled statement is directly verified in the cited repository path and
  symbol. Experiment results remain historical evidence unless their artifacts
  and exact runtime configuration are present and were reproduced.
- **Inference:** the implementation strongly suggests the statement, but does
  not state it as a contract.
- **Unverified:** a repository document or comment makes the claim, but it was
  not reproduced during the latest verification.
- **Open question:** the current repository does not settle the issue.

Every substantial claim should cite a repository-relative path and a class,
function, executable, test, script section, or data artifact. Line numbers are
intentionally secondary because this is an active experimental driver.

## Maintenance rules

An agent must update this knowledge base in the same change when it changes a
documented entry point, subsystem boundary, state/data flow, RNG treatment,
invariant, feature schema, training/export/inference contract, artifact format,
evaluation protocol, or a recorded discrepancy. Update
`docs/knowledge-base/experiments/current-state.md` when the recommended
baseline, active gate, or
validity of a headline result changes. Record chronological benchmark evidence
in `EXPERIMENTS.md`, including failures and invalidations.

Do not copy transient metrics into architecture pages. Do not infer historical
rationale. Put unresolved, reproducible diagnoses in `investigations/`; put a
decision in `decisions/` only when repository evidence contains its rationale.

## Relevant code

- `AGENTS.md` — agent operating contract and documentation rules.
- `CMakeLists.txt` — `project`, `pybind11_add_module`, and `add_executable`.
- `apps/one_combat.cpp` — `main`.
- `EXPERIMENTS.md` — numbered experiment entries.
