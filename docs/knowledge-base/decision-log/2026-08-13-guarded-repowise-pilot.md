# 2026-08-13 — Guarded RepoWise pilot with Cline and Serena

Date: 2026-08-13
Session/task: Establish keyless structural repository intelligence without a competing knowledge store.

## Decision

Extend the earlier Cline harness + Serena semantic-tooling decision with a guarded RepoWise pilot. Cline remains the interactive harness; Serena remains the preferred live C++/Python symbol and diagnostic layer; RepoWise is a local, derived structural index for architecture, ADR rationale, git/change risk, health, and cautious dead-code signals. Root `decisions/` contains the small initial ADR set that RepoWise may index.

## Rationale

RepoWise is configured with a mock embedder, telemetry disabled, no prose, no LLM decision mining, no hooks, no agent-file generation, and no editor setup. Git-tracked code, tests, raw experiment ledgers, curated KB pages, and ADRs remain authoritative. **Unverified:** RepoWise issue #1390 makes loading pre-existing repository-local `.repowise/*.pkl` unsafe; preflight found no `.repowise/` directory or tracked entries, and the pilot excludes the generated directory from Git. **Unverified:** issue #1117 motivates post-init checks for editor configuration despite opt-outs.

## Alternatives considered

- Use RepoWise-generated graphs for exact code semantics — rejected: Serena's LSP-backed symbol tools are the intended exact semantic source.
- Enable paid prose, embeddings, hooks, or automatic refactoring — rejected: they are unnecessary for the local pilot and would broaden authority/cost.
- Convert the chronological log or experiment ledger into ADRs — rejected: they retain their distinct historical-evidence responsibilities.

## Evidence

- `docs/knowledge-base/decision-log/2026-08-13-cline-serena-workflow.md` — prior Cline/Serena workflow and rejected Serena-memory alternative.
- `.serena/project.yml` — LSP C++/Python configuration and excluded memory/onboarding tools.
- `AGENTS.md` — repository authority hierarchy, approval policy, and record boundaries.
- `decisions/README.md` — durable ADR policy and lifecycle.

## Status and follow-up

- Implemented as a guarded local pilot. Restart PyCharm and confirm the two MCP servers are healthy before relying on them in an interactive task.
