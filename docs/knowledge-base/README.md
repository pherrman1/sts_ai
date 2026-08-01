# StS AI knowledge base

Last verified: 2026-08-02 against the current working tree.

This knowledge base is the maintained technical reference for the repository.
Code and executable behavior remain authoritative; `EXPERIMENTS.md` retains
chronological evidence; `README.md` remains human-facing; and `AGENTS.md`
remains the coding-agent operating contract.

## Reading paths

For architecture:

1. [Overview](architecture/overview.md)
2. [Combat search](architecture/combat-search.md)
3. [Out-of-combat policy](architecture/out-of-combat.md)
4. [Training and inference](architecture/training-and-inference.md)

For evaluation and operation:

1. [Current baselines](evaluation/current-baselines.md)
2. [Benchmark protocol](evaluation/benchmark-protocol.md)
3. [Build and debugging](operations/build-and-debugging.md)
4. [Self-play loop](operations/selfplay-loop.md)

For correctness:

1. [Determinism and RNG](behavior/determinism-and-rng.md)
2. [Invariants](behavior/invariants.md)
3. [Glossary](glossary.md)

For decisions and open questions:

1. [Decision log](decision-log/README.md)
2. [Decision records](decisions/README.md)
3. [Investigations](investigations/README.md)

For known issues:

1. [Issues](issues/README.md) — collected knowledge-base problems sorted by importance

The `decisions/` and `investigations/` indexes define when durable rationale or
a reproducible unresolved diagnosis belongs in a dedicated record. The
`decision-log/` index defines the chronological, session-level record of
decisions made during agent work. Dated plans and superseded schemas are
retained under `docs/archive/` and must not be used as current instructions.

## Evidence labels

- An unlabelled technical statement is directly verified in the cited path and
  symbol.
- **Inference** means implementation evidence supports the statement but does
  not establish it as a contract or causal explanation.
- **Unverified** means a document, comment, or artifact reports the claim, but
  it was not reproduced during the latest verification.
- **Open question** means the repository does not settle the issue.

Substantial claims cite a repository-relative path plus a class, function,
executable, test, script, artifact, or numbered experiment entry. Line numbers
are secondary because the integration driver changes frequently.

## Ownership and maintenance

Update the relevant page in the same change whenever code alters:

- architecture or subsystem boundaries;
- model interfaces, feature order, or artifact formats;
- environment variables or inference precedence;
- training or self-play pipelines;
- benchmark protocols, metrics, or deployed configurations;
- build commands or dependencies;
- RNG behavior or important invariants;
- a documented limitation or discrepancy.

Experimental outcomes—including negative and invalid results—belong in
`EXPERIMENTS.md`. Stable current understanding belongs here. Changing a
headline benchmark or its validity also requires updating
[evaluation/current-baselines.md](evaluation/current-baselines.md); other pages
must link there rather than copy changing numbers.

Decisions made during agent sessions are recorded chronologically in the
[decision log](decision-log/README.md); stable, evidence-backed decisions
belong in `decisions/`.

Every technical page retains Purpose, Current implementation, Important data
flow, Invariants and assumptions, Relevant code, Known limitations, Open
questions when applicable, and Last verified date. Do not infer historical
rationale from the final code shape.

## Relevant sources

- `AGENTS.md` — operating and maintenance contract.
- `CMakeLists.txt` — target graph and language flags.
- `apps/one_combat.cpp::main` — active mode and model dispatcher.
- `EXPERIMENTS.md` — chronological evidence ledger.
