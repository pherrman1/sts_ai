# StS AI knowledge base

Last verified: 2026-09-04 against the current working tree.

This knowledge base is the maintained technical reference for the repository.
Code and executable behavior remain authoritative; `EXPERIMENTS.md` retains
chronological evidence; `README.md` remains human-facing; and `AGENTS.md`
remains the coding-agent operating contract.

## Fast routing

Use the [code map](CODE_MAP.md) for unfamiliar code or subsystem boundaries.
It maps topics to primary files, key symbols, and relevant knowledge-base
pages. For localized, already-understood changes, start with the relevant
code, tests, or docs; follow `AGENTS.md` for task-dependent reading.

## Reading paths

For architecture:

1. [Overview](architecture/overview.md)
2. [Combat search](architecture/combat-search.md)
3. [Out-of-combat policy](architecture/out-of-combat.md)
4. [Training and inference](architecture/training-and-inference.md)

For research status:

1. [Current research](evaluation/current-research.md) — the only maintained
   routing page for active, parked, and closed research lines.
2. [Current baselines](evaluation/current-baselines.md) — qualified executable
   configurations and benchmark references.
3. `EXPERIMENTS.md` — chronological experiment evidence index; historical
   content stored in `docs/experiments/ledger-*.md`.
4. [Research graph](research/README.md) — topic-oriented maintained scientific
   understanding.

For evaluation and operation:

1. [Current baselines](evaluation/current-baselines.md)
2. [Benchmark protocol](evaluation/benchmark-protocol.md)
3. [Environment variables](operations/environment-variables.md)
4. [Self-play loop](operations/selfplay-loop.md) (removed; historical)
5. [Agent context and workflow](operations/agent-context-and-workflow.md) —
   progressive-disclosure workflow, Git procedure, recording rules, and the
   `AGENTS.md` relocation audit.
6. [Repository health](operations/repo-health.md) — bounded inventory and CI
   guard for repository bloat.
7. [Refactor-on-contact candidates](operations/refactor-on-contact.md)
8. [Coding-agent evaluation harness](evaluation/coding-agent-evals.md)
9. [SkillOpt-Sleep pilot](operations/skillopt-sleep.md) — on-demand transcript
   review, bounded skill proposals, and evaluator-gated adoption.
10. [Session retrospective](operations/session-retrospective.md) — manual review
   of recent sessions and routing of small, evidence-backed maintenance.

For correctness:

1. [Determinism and RNG](behavior/determinism-and-rng.md)
2. [Invariants](behavior/invariants.md)
3. [Simulator health monitor](behavior/simulator-health-monitor.md)
4. [Combat potion-generation support](behavior/combat-potion-generation.md)
5. [Glossary](glossary.md)

For decisions and open questions:

1. [Decision records](../../decisions/README.md)
2. [Investigations](investigations/README.md)

For known issues:

1. [Issues](issues/README.md) — collected knowledge-base problems sorted by importance

The `decisions/` and `investigations/` indexes define when durable rationale or
a reproducible unresolved diagnosis belongs in a dedicated record. Historical
session material is available only through Git history when explicitly needed
for provenance. Dated plans and superseded schemas are historical Git records.

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

Decisions made during agent sessions are routed directly to the appropriate
maintained page, ADR, experiment ledger, or investigation; temporary detail
belongs in the PR or commit. Historical session material is available only in
Git history when explicitly needed for provenance.

Every technical page retains Purpose, Current implementation, Important data
flow, Invariants and assumptions, Relevant code, Known limitations, Open
questions when applicable, and Last verified date. Do not infer historical
rationale from the final code shape.

Data-flow sections may use ` ```mermaid ` fenced diagrams (rendered on GitHub)
in addition to the required prose steps. Prefer mermaid for structural flow;
keep an ASCII version when it is a spec contract whose precise alignment
matters (e.g. `ooc-strategic-v4.md`). Mermaid source must keep every
relationship as an explicit edge so the diagram remains LLM-readable.

## Relevant sources

- `AGENTS.md` — operating and maintenance contract.
- `CMakeLists.txt` — target graph and language flags.
- `apps/one_combat.cpp::main` — active mode and model dispatcher.
- `EXPERIMENTS.md` — experiment ledger index; historical evidence in `docs/experiments/ledger-*.md`.
- `docs/knowledge-base/research/` — topic-oriented maintained research understanding.
